# ocr_worker.py
# Threaded OCR pipeline that is provider-agnostic.

from __future__ import annotations
import io
import os
import time
import queue
import threading
from typing import List, Dict

import pypdfium2 as pdfium
from PIL import Image

from ocr_providers import OCRProvider, ProviderError


def now_ts():
    import datetime
    return datetime.datetime.now().strftime("%H:%M:%S")


def pdf_page_to_png_bytes(pdf_doc, page_index_zero_based: int, dpi: int = 300) -> bytes:
    """
    Render a single PDF page to PNG bytes using pypdfium2.
    dpi: target DPI (scale = dpi/72).
    """
    page = pdf_doc[page_index_zero_based]
    scale = float(dpi) / 72.0
    bitmap = page.render(scale=scale)
    pil_img = bitmap.to_pil()  # RGBA
    bitmap.close()
    pil_img = pil_img.convert("RGB")  # better OCR compatibility
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def build_prompt_for_page(page_num: int, template: str) -> str:
    return template.replace("{PAGE_NUM}", str(page_num))


class OCRWorker(threading.Thread):
    def __init__(
        self,
        app_ref,
        provider: OCRProvider,
        pdf_path: str,
        out_path: str,
        pages: List[int],
        dpi: int,
        strict_prompt_template: str,
        concurrency: int = 6,
        max_attempts: int = 2,
        backoff_base: float = 1.5,
    ):
        super().__init__(daemon=True)
        self.app = app_ref
        self.provider = provider
        self.pdf_path = pdf_path
        self.out_path = out_path
        self.pages = list(pages)
        self.dpi = dpi
        self.cancelled = False
        self.concurrency = max(1, int(concurrency))
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.strict_prompt_template = strict_prompt_template

        self._q: "queue.Queue" = queue.Queue(maxsize=self.concurrency * 2)
        self._results: Dict[int, str] = {}
        self._results_lock = threading.Lock()
        self._write_cond = threading.Condition()

    # UI hooks
    def log(self, msg):
        self.app.log(msg)

    def update_status(self, text):
        self.app.update_status(text)

    def update_overall_progress(self, value, maximum=None):
        self.app.update_overall_progress(value, maximum)

    # Provider request with retries
    def _transcribe_with_retries(self, client, image_bytes: bytes, prompt: str) -> str:
        attempt = 1
        while attempt <= self.max_attempts and not self.cancelled:
            try:
                text = self.provider.transcribe(client, image_bytes, prompt)
                text = (text or "").strip()
                if not text:
                    raise ProviderError("Empty response text.")
                return text
            except Exception as e:
                if attempt == self.max_attempts or self.cancelled:
                    raise
                sleep_s = self.backoff_base ** attempt
                self.log(f"[{now_ts()}] Retry {attempt}/{self.max_attempts - 1} after error: {e}. Backing off {sleep_s:.1f}s")
                time.sleep(sleep_s)
                attempt += 1
        raise ProviderError("Cancelled or max attempts exceeded.")

    def _producer(self, pdf: pdfium.PdfDocument):
        for page_num in self.pages:
            if self.cancelled:
                break
            try:
                png_bytes = pdf_page_to_png_bytes(pdf, page_num - 1, dpi=self.dpi)
                prompt = build_prompt_for_page(page_num, self.strict_prompt_template)
            except Exception as e:
                open_tag = f"<page{page_num}>"
                close_tag = f"</page{page_num}>"
                text_to_write = f"{open_tag}\n[error] Render failed: {e}\n{close_tag}"
                with self._results_lock:
                    self._results[page_num] = text_to_write
                with self._write_cond:
                    self._write_cond.notify()
                continue

            while not self.cancelled:
                try:
                    self._q.put((page_num, png_bytes, prompt), timeout=0.25)
                    break
                except queue.Full:
                    continue

        # Signal consumers to exit
        for _ in range(self.concurrency):
            while True:
                try:
                    self._q.put(None, timeout=0.25)
                    break
                except queue.Full:
                    if self.cancelled:
                        break

    def _consumer(self, worker_id: int):
        client = None
        try:
            client = self.provider.create_thread_client()
        except Exception as e:
            self.log(f"[{now_ts()}] Worker-{worker_id} failed to init provider client: {e}")

        while not self.cancelled:
            try:
                item = self._q.get(timeout=0.25)
            except queue.Empty:
                if self.cancelled:
                    break
                continue

            if item is None:
                self._q.task_done()
                break

            page_num, png_bytes, prompt = item
            try:
                if client is None:
                    raise ProviderError("Provider client not initialized.")
                text = self._transcribe_with_retries(client, png_bytes, prompt)
            except Exception as e:
                text = f"<page{page_num}>\n[error] OCR failed: {e}\n</page{page_num}>"

            open_tag = f"<page{page_num}>"
            close_tag = f"</page{page_num}>"
            if open_tag in text and close_tag in text:
                start_i = text.find(open_tag)
                end_i = text.rfind(close_tag) + len(close_tag)
                text_to_write = text[start_i:end_i]
            else:
                text_to_write = f"{open_tag}\n{text}\n{close_tag}"

            with self._results_lock:
                self._results[page_num] = text_to_write

            with self._write_cond:
                self._write_cond.notify()

            self._q.task_done()

        try:
            if client is not None:
                self.provider.shutdown_client(client)
        except Exception:
            pass

    def run(self):
        start_time = time.time()
        try:
            self.log(f"[{now_ts()}] Opening PDF: {self.pdf_path}")
            pdf = pdfium.PdfDocument(self.pdf_path)
            total = len(self.pages)
            self.update_overall_progress(0, maximum=total)
            self.log(f"[{now_ts()}] Concurrency: {self.concurrency} (parallel requests)")

            os.makedirs(os.path.dirname(self.out_path) or ".", exist_ok=True)

            with open(self.out_path, "w", encoding="utf-8", newline="\n") as out_f:
                prod_thread = threading.Thread(target=self._producer, args=(pdf,), daemon=True, name="producer")
                cons_threads = [
                    threading.Thread(target=self._consumer, args=(i + 1,), daemon=True, name=f"worker-{i+1}")
                    for i in range(self.concurrency)
                ]
                prod_thread.start()
                for t in cons_threads:
                    t.start()

                written = 0
                write_index = 0
                last_status_ts = 0
                start_ts = start_time

                while written < total and not self.cancelled:
                    with self._write_cond:
                        self._write_cond.wait(timeout=0.25)

                    while write_index < total:
                        pg = self.pages[write_index]
                        with self._results_lock:
                            result = self._results.pop(pg, None)
                        if result is None:
                            break
                        out_f.write(result)
                        out_f.write("\n\n")
                        out_f.flush()
                        write_index += 1
                        written = write_index
                        self.update_overall_progress(written)

                    now = time.time()
                    if now - last_status_ts > 0.5:
                        elapsed = now - start_ts
                        rate = (written / elapsed) if elapsed > 0 else 0.0
                        remaining = max(0, total - written)
                        eta_s = remaining / rate if rate > 0 else 0.0
                        self.update_status(f"Written {written}/{total} • {rate:.2f} pg/s • ETA {eta_s:.1f}s (parallel {self.concurrency})")
                        last_status_ts = now

                prod_thread.join(timeout=2.0)
                for t in cons_threads:
                    t.join(timeout=2.0)

            elapsed = time.time() - start_time
            if not self.cancelled:
                self.update_status(f"Done. Wrote: {self.out_path}")
                self.log(f"[{now_ts()}] Finished in {elapsed:.1f}s. Output: {self.out_path}")
            else:
                self.update_status(f"Cancelled. Partial output saved: {self.out_path}")
                self.log(f"[{now_ts()}] Cancelled after {elapsed:.1f}s. Partial output at {self.out_path}")

        except Exception as e:
            self.update_status("Error")
            self.log(f"[{now_ts()}] ERROR: {e}")
        finally:
            self.app.on_worker_done()
