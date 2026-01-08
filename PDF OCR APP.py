from __future__ import annotations
import os
import platform
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

import pypdfium2 as pdfium

from ocr_worker import OCRWorker
from ocr_providers import list_providers, get_provider, DEFAULT_GEMINI_MODEL

APP_TITLE = "PDF OCR"
APP_WIDTH = 1500
APP_HEIGHT = 900

STRICT_OCR_PROMPT_TEMPLATE = r"""YOU ARE A LITERAL TRANSCRIBER (OCR). Output what is on the page, not what you think it means.
DO NOT solve, simplify, correct, explain, or “improve” the content.

========================================
0) NON‑NEGOTIABLE CORE DIRECTIVE (ZERO TOLERANCE): LaTeX FOR ALL MATH TOKENS
========================================
Every mathematical item MUST be inside LaTeX delimiters.

HARD RULE:
- Any math expression, equation, inequality, fraction, integral, summation, subscript/superscript
- Any single variable (e.g., V, I, R, t, x, y, z)
- Any Greek letter (e.g., α, β, ω, π)
- Any operator/symbol when used mathematically (e.g., =, +, −, ×, /, ∠, ∞, √, %, °)
MUST be wrapped in LaTeX:
- Inline: $...$
- Display (standalone line): $$...$$

If unsure whether something is “math”: PUT IT IN $...$.

Units rule (to avoid plain-text symbols):
- Write quantities like $10\,\mathrm{V}$, $5\,\Omega$, $50\,\mathrm{Hz}$, $3\,\mathrm{A}$, $1\,\mathrm{s}$.

ABSOLUTE FAILURE CONDITION:
- Any plain-text math token appearing outside $...$ / $$...$$ (including a lone “=”, “+”, “ω”, “π”, etc.).

========================================
1) OUTPUT FORMAT (MUST MATCH)
========================================
- Transcribe exactly ONE page.
- Preserve the original line breaks, indentation, bullets, and spacing as much as plain text allows.
- Read order: top-to-bottom, left-to-right. If there are columns: finish column 1 fully, then column 2.
- After the final line of transcription, output EXACTLY one line containing:
-----
- No blank lines before or after that delimiter.
- No extra headers (no “Page 1”, no commentary, no apologies).

========================================
2) WHAT TO TRANSCRIBE (STRICT LITERALITY)
========================================
- Keep original capitalization, punctuation, and abbreviations.
- Do not rewrite sentences.
- Do not expand symbols into words unless the page itself does.
- Do not “correct” typos from the source.

Hyphenation / line-break artifacts:
- If a word is hyphenated at the end of a line in the source, keep it exactly as shown.

========================================
3) TABLES
========================================
- Simple grid tables (clear rows/columns, no merged cells) → use GitHub-flavored Markdown table.
- Complex/unclear tables → preserve spacing in plain text (do NOT force a Markdown table).
- Inside Markdown tables: escape any literal pipe character as \|.
- All math inside tables still obeys Rule 0 (LaTeX-wrap everything mathematical).

========================================
4) FIGURES & DIAGRAMS (ANTI-TIKZ / ANTI-RECONSTRUCTION HARD RULES)
========================================
You must NEVER recreate drawings.

FORBIDDEN OUTPUT (instant failure):
- Any TikZ / CircuitTikZ / LaTeX drawing code (e.g., \begin{tikzpicture}, \begin{circuitikz})
- Any ASCII art diagram recreation
- Any “redrawn” schematic, waveform, or plot
- Any attempt to algorithmically describe geometry with coordinates

Allowed handling:

4A) NON-GRAPH DIAGRAMS (circuits, block diagrams, phasors, logic sketches)
- Do NOT redraw.
- Instead, write a short, plain-language component/connection description.
- Keep it minimal and literal. List only what is visibly present.
- Include labels/values exactly as printed (LaTeX-wrap all math tokens).
- If a connection is unclear: write “[illegible connection]”.

Recommended format (use only if needed; do NOT add extra titles beyond what’s printed):
- “Figure: [printed figure label/title if present]”
- Then 1–6 short lines describing elements, e.g.:
  - “Circuit: [component] between [node labels]; [component] in series with [component]; source labeled $V_s$ …”
(Do not exceed what the page shows.)

4B) GRAPHS / PLOTS / WAVEFORMS (Bode, time plots, characteristics, spectra, any axes)
CAPTION-ONLY RULE:
- Transcribe ONLY the printed figure number and/or caption/title OUTSIDE the plot area.
- STRICTLY DO NOT transcribe anything inside the plot area:
  - no axis labels, no tick values, no units on axes, no legends, no curve labels, no annotations.
- If the graph has no caption/title outside the plot area: SKIP THE GRAPH ENTIRELY.

========================================
5) ILLEGIBLE CONTENT
========================================
- If a word/symbol is unreadable: write “[illegible]”.
- If only part is unreadable: keep the readable part and insert “[illegible]” at the correct position.
- Do not guess.

========================================
6) FINAL SELF-CHECK (DO NOT PRINT THIS CHECKLIST)
========================================
Before outputting, verify:
1) Math Integrity: ZERO plain-text math tokens exist outside $...$ or $$...$$.
2) Diagram Rule: No TikZ/CircuitTikZ/ASCII art/redraw content exists.
3) Graph Purge: No text from inside any plot area is included.
4) Delimiter: Exactly one final line “-----”, with no blank line before/after.

EXECUTE NOW."""



def now_ts():
    import datetime
    return datetime.datetime.now().strftime("%H:%M:%S")


def parse_page_ranges(spec: str, total_pages: int):
    """
    Parse a range string like:
      - "all", "", "*" => all pages
      - "1-3,5,7-" => [1,2,3,5,7..total]
    Returns a sorted list of 1-based page numbers within [1, total_pages].
    Raises ValueError on invalid input.
    """
    if not spec or spec.strip().lower() in ("all", "*"):
        return list(range(1, total_pages + 1))

    pages = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_s, end_s = token.split("-", 1)
            start = int(start_s) if start_s.strip() else 1
            end = int(end_s) if end_s.strip() else total_pages
            if start > end:
                start, end = end, start
            if start < 1 or end > total_pages:
                raise ValueError(f"Range {token} out of bounds (1..{total_pages})")
            pages.update(range(start, end + 1))
        else:
            page = int(token)
            if page < 1 or page > total_pages:
                raise ValueError(f"Page {page} out of bounds (1..{total_pages})")
            pages.add(page)
    return sorted(pages)


class OCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.worker = None

        # cache for computing "all" end page
        self._cached_pdf_path = None
        self._total_pages = None

        # Styles
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Sub.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("Accent.TButton", font=("Segoe UI", 10))

        # Top header
        header = ttk.Frame(root, padding=(12, 12, 12, 6))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        self.dark_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(header, text="Dark", variable=self.dark_mode, command=self.toggle_theme).pack(side="right")

        # Inputs
        f_top = ttk.LabelFrame(root, text="Input & Settings", padding=12)
        f_top.pack(fill="x", padx=10, pady=(0, 6))

        # Row 0: PDF
        ttk.Label(f_top, text="PDF file:").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        self.pdf_var = tk.StringVar()
        self.pdf_entry = ttk.Entry(f_top, textvariable=self.pdf_var, width=90)
        self.pdf_entry.grid(row=0, column=1, sticky="we", padx=(0, 6), pady=4)
        ttk.Button(f_top, text="Browse...", command=self.browse_pdf).grid(row=0, column=2, pady=4)

        # Row 1: Output + Auto name
        ttk.Label(f_top, text="Output file:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        self.out_var = tk.StringVar()
        self.out_entry = ttk.Entry(f_top, textvariable=self.out_var, width=90)
        self.out_entry.grid(row=1, column=1, sticky="we", padx=(0, 6), pady=4)
        ttk.Button(f_top, text="Browse...", command=self.browse_out).grid(row=1, column=2, pady=4)
        self.auto_name_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_top, text="Auto name", variable=self.auto_name_var, command=self._prefill_output).grid(row=1, column=3, sticky="w", padx=(6, 0), pady=4)

        # Row 2: Pages, DPI
        ttk.Label(f_top, text="Pages (e.g., 1-3,5,7- or 'all'):").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=4)
        self.pages_var = tk.StringVar(value="all")
        self.pages_entry = ttk.Entry(f_top, textvariable=self.pages_var, width=40)
        self.pages_entry.grid(row=2, column=1, sticky="w", padx=(0, 6), pady=4)
        self.pages_entry.bind("<KeyRelease>", lambda e: self._prefill_output())

        ttk.Label(f_top, text="DPI:").grid(row=2, column=2, sticky="e", padx=(6, 6))
        self.dpi_var = tk.StringVar(value="300")
        ttk.Entry(f_top, textvariable=self.dpi_var, width=8).grid(row=2, column=3, sticky="w", padx=(0, 6))

        # Row 3: Provider, Concurrency
        ttk.Label(f_top, text="Provider:").grid(row=3, column=0, sticky="w", padx=(0, 6), pady=4)
        self.provider_var = tk.StringVar()
        providers = list_providers()
        self.provider_map = {p.display_name: p.provider_id for p in providers}
        self.provider_combo = ttk.Combobox(f_top, textvariable=self.provider_var, values=list(self.provider_map.keys()), state="readonly", width=38)
        default_name = next((p.display_name for p in providers if p.provider_id == "openrouter"), providers[0].display_name)
        self.provider_combo.set(default_name)
        self.provider_combo.grid(row=3, column=1, sticky="w", padx=(0, 6), pady=4)

        ttk.Label(f_top, text="Parallel requests:").grid(row=3, column=2, sticky="e", padx=(6, 6))
        self.conc_var = tk.StringVar(value="7")
        ttk.Entry(f_top, textvariable=self.conc_var, width=8).grid(row=3, column=3, sticky="w", padx=(0, 6))

        # Row 4: Model name (Google only)
        self.model_frame = ttk.Frame(f_top)
        self.model_frame.grid(row=4, column=0, columnspan=4, sticky="we", pady=(8, 2))
        ttk.Label(self.model_frame, text="Model (Google):", style="Sub.TLabel").pack(side="left")
        self.model_var = tk.StringVar(value=DEFAULT_GEMINI_MODEL)
        self.model_entry = ttk.Entry(self.model_frame, textvariable=self.model_var, width=40)
        self.model_entry.pack(side="left", padx=(8, 0))

        f_top.columnconfigure(1, weight=1)

        # Buttons
        f_btn = ttk.Frame(root, padding=(10, 4, 10, 6))
        f_btn.pack(fill="x")
        self.start_btn = ttk.Button(f_btn, text="Start OCR", command=self.start_ocr, style="Accent.TButton")
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(f_btn, text="Cancel", command=self.cancel_ocr, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self.open_out_btn = ttk.Button(f_btn, text="Open Output Folder", command=self.open_output_folder)
        self.open_out_btn.pack(side="left", padx=(8, 0))
        ttk.Button(f_btn, text="Clear Log", command=self.clear_log).pack(side="right")
        ttk.Button(f_btn, text="Copy Log", command=self.copy_log).pack(side="right", padx=(0, 8))

        # Log
        f_log = ttk.LabelFrame(root, text="Log", padding=8)
        f_log.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.log_text = ScrolledText(f_log, wrap="word", height=18, font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)

        # Status & Progress
        f_status = ttk.Frame(root, padding=(10, 0, 10, 10))
        f_status.pack(fill="x")
        self.status_var = tk.StringVar(value="Idle")
        self.status_label = ttk.Label(f_status, textvariable=self.status_var)
        self.status_label.pack(anchor="w", pady=(0, 6))
        self.pb_overall = ttk.Progressbar(f_status, orient="horizontal", mode="determinate", length=600)
        self.pb_overall.pack(fill="x")

        # Events
        self.pdf_entry.bind("<FocusOut>", lambda e: (self._refresh_total_pages(), self._prefill_output()))
        self.pdf_entry.bind("<KeyRelease>", lambda e: self._prefill_output())
        self.provider_combo.bind("<<ComboboxSelected>>", self._provider_changed)
        self._provider_changed()

    # ---------- Theming ----------
    def toggle_theme(self):
        style = ttk.Style()
        if self.dark_mode.get():
            bg = "#1e1e1e"
            fg = "#e6e6e6"
            style.configure(".", background=bg, foreground=fg)
            style.configure("TEntry", fieldbackground="#2b2b2b")
            self.log_text.config(bg="#1f1f1f", fg="#d0d0d0", insertbackground="#ffffff")
            self.root.configure(bg=bg)
        else:
            try:
                style.theme_use("clam")
            except Exception:
                pass
            style.configure(".", background="", foreground="")
            style.configure("TEntry", fieldbackground="")
            self.log_text.config(bg="white", fg="black", insertbackground="black")
            self.root.configure(bg="")

    def _provider_changed(self, *args):
        pid = self.provider_map.get(self.provider_var.get())
        if pid == "google_gemini":
            self.model_frame.grid()
        else:
            self.model_frame.grid_remove()

    # ---------- Logging / Status ----------
    def log(self, msg: str):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def clear_log(self):
        self.log_text.delete("1.0", "end")

    def copy_log(self):
        text = self.log_text.get("1.0", "end").strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    def update_status(self, text: str):
        self.status_var.set(text)
        self.root.update_idletasks()

    def update_overall_progress(self, value, maximum=None):
        if maximum is not None:
            self.pb_overall["maximum"] = maximum
        self.pb_overall["value"] = value
        self.root.update_idletasks()

    # ---------- Auto naming helpers ----------
    def _safe_filename(self, name: str) -> str:
        import re
        name = name.strip().replace(" ", "_")
        return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", name)

    def _refresh_total_pages(self):
        path = self.pdf_var.get().strip()
        if path == self._cached_pdf_path:
            return
        if not path or not os.path.isfile(path):
            self._cached_pdf_path = None
            self._total_pages = None
            return
        try:
            pdf = pdfium.PdfDocument(path)
            self._total_pages = len(pdf)
            self._cached_pdf_path = path
        except Exception:
            self._cached_pdf_path = None
            self._total_pages = None

    def _compute_template_out_name(self) -> str:
        # book_Name
        pdf_path = self.pdf_var.get().strip()
        if not pdf_path:
            return "ocr_output.md"
        book_name = os.path.splitext(os.path.basename(pdf_path))[0]
        book_name = self._safe_filename(book_name) or "book"

        # compute page start/end from spec
        pages_spec = (self.pages_var.get() or "").strip().lower()
        total = self._total_pages or 1
        try:
            pages = parse_page_ranges(pages_spec, total)
            if pages:
                start = min(pages)
                end = max(pages)
            else:
                start, end = 1, total
        except Exception:
            start, end = 1, total

        fname = f"{book_name}-{start}-to-{end}.md"
        folder = os.path.dirname(pdf_path) or "."
        return os.path.join(folder, fname)

    def _default_out_name(self):
        # Backwards-compat, but route to template
        return os.path.basename(self._compute_template_out_name())

    def _prefill_output(self):
        self._refresh_total_pages()
        if self.auto_name_var.get() or not self.out_var.get().strip():
            self.out_var.set(self._compute_template_out_name())

    # ---------- File dialogs ----------
    def browse_pdf(self):
        path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf")],
        )
        if path:
            self.pdf_var.set(path)
            self._refresh_total_pages()
            self._prefill_output()

    def browse_out(self):
        path = filedialog.asksaveasfilename(
            title="Save Output As",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt")],
            initialfile=os.path.basename(self._compute_template_out_name()),
        )
        if path:
            self.out_var.set(path)

    # ---------- Run / Cancel ----------
    def start_ocr(self):
        if self.worker is not None:
            return
        pdf_path = self.pdf_var.get().strip()
        out_path = self.out_var.get().strip()
        pages_spec = self.pages_var.get().strip()
        dpi_str = self.dpi_var.get().strip()
        conc_str = self.conc_var.get().strip()
        pid = self.provider_map.get(self.provider_var.get())

        if not pdf_path or not os.path.isfile(pdf_path):
            messagebox.showwarning("Missing PDF", "Please select a valid PDF file.")
            return

        try:
            dpi = int(dpi_str)
            if dpi < 72 or dpi > 600:
                raise ValueError
        except Exception:
            messagebox.showwarning("Invalid DPI", "Please enter a DPI between 72 and 600 (e.g., 300).")
            return

        try:
            concurrency = int(conc_str)
            if concurrency < 1 or concurrency > 16:
                raise ValueError
        except Exception:
            messagebox.showwarning("Invalid Concurrency", "Please enter a parallel request count between 1 and 16 (e.g., 6).")
            return

        try:
            pdf = pdfium.PdfDocument(pdf_path)
            total_pages = len(pdf)
        except Exception as e:
            messagebox.showerror("PDF Error", f"Failed to open PDF: {e}")
            return

        try:
            pages = parse_page_ranges(pages_spec, total_pages)
        except Exception as e:
            messagebox.showwarning("Page Range Error", str(e))
            return

        if not out_path:
            out_path = self._compute_template_out_name()
            self.out_var.set(out_path)

        try:
            provider = get_provider(pid)
            if provider.provider_id == "google_gemini" and hasattr(provider, "model_name"):
                provider.model_name = self.model_var.get().strip() or provider.model_name
        except Exception as e:
            messagebox.showerror("Provider Error", str(e))
            return

        self.log(f"[{now_ts()}] Starting OCR with {provider.display_name}")
        self.log(f"[{now_ts()}] PDF: {pdf_path}")
        self.log(f"[{now_ts()}] Pages: {pages}")
        self.log(f"[{now_ts()}] DPI: {dpi}")
        self.log(f"[{now_ts()}] Parallel requests: {concurrency}")
        self.log(f"[{now_ts()}] Output: {out_path}")
        if getattr(provider, "model_name", None):
            self.log(f"[{now_ts()}] Model: {provider.model_name}")

        try:
            self.worker = OCRWorker(
                app_ref=self,
                provider=provider,
                pdf_path=pdf_path,
                out_path=out_path,
                pages=pages,
                dpi=dpi,
                strict_prompt_template=STRICT_OCR_PROMPT_TEMPLATE,
                concurrency=concurrency,
                max_attempts=2,
                backoff_base=1.5,
            )
        except Exception as e:
            messagebox.showerror("Init Error", str(e))
            self.worker = None
            return

        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.update_status("Starting...")
        self.update_overall_progress(0, maximum=len(pages))
        self.worker.start()

    def cancel_ocr(self):
        if self.worker:
            self.worker.cancelled = True
            self.update_status("Cancelling...")

    def on_worker_done(self):
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.worker = None

    def open_output_folder(self):
        path = self.out_var.get().strip()
        if not path:
            messagebox.showinfo("Open Output", "No output path selected yet.")
            return
        folder = os.path.dirname(os.path.abspath(path)) or "."
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif system == "Darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')
        except Exception as e:
            messagebox.showerror("Open Folder Error", str(e))


def main():
    root = tk.Tk()
    app = OCRApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
