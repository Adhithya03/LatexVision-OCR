# ocr_providers.py
# Abstraction layer for OCR providers. Add new providers by implementing OCRProvider.

from __future__ import annotations

import base64
import os
import time
from typing import Any, Dict, List, Optional

# Public constants for API keys and configuration.
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
ENV_GEMINI_API_KEY = "GEMINI_API_KEY"

ENV_OPENROUTER_API_KEY = "OPENROUTER_API_KEY"
DEFAULT_OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4.1-mini")

# NEW: Direct OpenAI support
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
DEFAULT_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")


class ProviderError(Exception):
    pass


class OCRProvider:
    """
    Abstract base class for OCR providers.
    Implementations must provide:
      - provider_id (short id)
      - display_name (human display)
      - create_thread_client() -> Any
      - transcribe(client, image_bytes, prompt) -> str
      - optional: shutdown_client(client)
    """

    provider_id: str = "base"
    display_name: str = "Base Provider"
    is_configurable: bool = False  # ### ADDED: Flag for UI to show model config

    def create_thread_client(self) -> Any:
        raise NotImplementedError

    def transcribe(self, client: Any, image_bytes: bytes, prompt: str) -> str:
        raise NotImplementedError

    def shutdown_client(self, client: Any) -> None:
        # optional
        pass

    def default_concurrency(self) -> int:
        # provider-specific safe parallelism hints
        return 4


# ----- Google Gemini Provider (preserves existing API syntax) -----


class GoogleGeminiProvider(OCRProvider):
    provider_id = "google_gemini"
    display_name = "Google Gemini"
    is_configurable = True  # ### ADDED

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or DEFAULT_GEMINI_MODEL
        self._checked_env = False

    def _ensure_env(self):
        if self._checked_env:
            return
        api_key = os.environ.get(ENV_GEMINI_API_KEY)
        if not api_key:
            raise ProviderError(f"{ENV_GEMINI_API_KEY} not set in environment.")
        self._checked_env = True

    def create_thread_client(self):
        self._ensure_env()
        try:
            from google import genai
        except ImportError:
            raise ProviderError(
                "google-generativeai library not installed. Please run 'pip install google-generativeai'."
            )
        api_key = os.environ.get(ENV_GEMINI_API_KEY)
        return {"client": genai.Client(api_key=api_key)}

    def transcribe(self, client, image_bytes: bytes, prompt: str) -> str:
        from google.genai import types

        genai_client = client["client"]
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(mime_type="image/png", data=image_bytes),
                    types.Part.from_text(text=prompt),
                ],
            )
        ]
        resp = genai_client.models.generate_content(
            model=self.model_name,
            contents=contents,
        )
        text = (getattr(resp, "text", "") or "").strip()
        if not text:
            raise ProviderError("Empty response text from Google Gemini.")
        return text

    def default_concurrency(self) -> int:
        return 6


# ----- OpenRouter.ai Provider -----


class OpenRouterProvider(OCRProvider):
    provider_id = "openrouter"
    display_name = "OpenRouter.ai"
    is_configurable = True  # ### ADDED

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or DEFAULT_OPENROUTER_MODEL
        self._checked_deps = False
        self.extra_headers = {}
        site_url = os.environ.get("OPENROUTER_SITE_URL")
        site_name = os.environ.get("OPENROUTER_SITE_NAME")
        if site_url:
            self.extra_headers["HTTP-Referer"] = site_url
        if site_name:
            self.extra_headers["X-Title"] = site_name

    def _ensure_deps(self):
        if self._checked_deps:
            return
        try:
            import openai  # noqa: F401
        except ImportError:
            raise ProviderError(
                "openai library not installed. Please run 'pip install openai'."
            )
        self._checked_deps = True

    def create_thread_client(self) -> Any:
        self._ensure_deps()
        from openai import OpenAI

        api_key = os.environ.get(ENV_OPENROUTER_API_KEY)
        if not api_key:
            raise ProviderError(
                f"{ENV_OPENROUTER_API_KEY} not set and no fallback key present."
            )

        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        return {"client": client, "headers": self.extra_headers}

    def transcribe(self, client: Any, image_bytes: bytes, prompt: str) -> str:
        openai_client = client["client"]
        headers = client["headers"]
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:image/png;base64,{base64_image}"

        completion = openai_client.chat.completions.create(
            extra_headers=headers,
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                }
            ],
        )
        text = (completion.choices[0].message.content or "").strip()
        if not text:
            raise ProviderError("Empty response text from OpenRouter.ai.")
        return text

    def default_concurrency(self) -> int:
        return 6


# ----- NEW: Direct OpenAI Provider -----


class OpenAIProvider(OCRProvider):
    provider_id = "openai"
    display_name = "OpenAI"
    is_configurable = True

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or DEFAULT_OPENAI_MODEL
        self._checked_deps = False

    def _ensure_deps(self):
        if self._checked_deps:
            return
        try:
            import openai  # noqa: F401
        except ImportError:
            raise ProviderError(
                "openai library not installed. Please run 'pip install openai'."
            )
        self._checked_deps = True

    def create_thread_client(self) -> Any:
        self._ensure_deps()
        from openai import OpenAI

        api_key = os.environ.get(ENV_OPENAI_API_KEY)
        if not api_key:
            raise ProviderError(f"{ENV_OPENAI_API_KEY} not set in environment.")
        client = OpenAI(api_key=api_key)
        return {"client": client}

    def transcribe(self, client: Any, image_bytes: bytes, prompt: str) -> str:
        openai_client = client["client"]
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:image/png;base64,{base64_image}"

        completion = openai_client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                }
            ],
        )
        text = (completion.choices[0].message.content or "").strip()
        if not text:
            raise ProviderError("Empty response text from OpenAI.")
        return text

    def default_concurrency(self) -> int:
        return 6


# ----- Dummy provider (for offline/dev testing) -----
class DummyEchoProvider(OCRProvider):
    provider_id = "dummy_echo"
    display_name = "Dummy Echo (dev)"

    def create_thread_client(self):
        return {"ts": time.time()}

    def transcribe(self, client, image_bytes: bytes, prompt: str) -> str:
        return f"{prompt.strip()}\n[dummy] bytes={len(image_bytes)}"


# ----- Optional Local Tesseract Provider -----
class LocalTesseractProvider(OCRProvider):
    provider_id = "local_tesseract"
    display_name = "Local Tesseract (optional)"

    def __init__(self):
        try:
            import pytesseract  # noqa: F401

            self.available = True
        except ImportError:
            self.available = False

    def create_thread_client(self):
        if not self.available:
            raise ProviderError("pytesseract not installed.")
        return {"ok": True}

    def transcribe(self, client, image_bytes: bytes, prompt: str) -> str:
        if not self.available:
            raise ProviderError("pytesseract not installed.")
        import io

        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        text = (pytesseract.image_to_string(img) or "").strip()
        return text if text else "[illegible]"


# ----- Registry / Factory -----
_REGISTRY: Dict[str, OCRProvider] = {}


def register_provider(p: OCRProvider):
    _REGISTRY[p.provider_id] = p


def get_provider(provider_id: str) -> OCRProvider:
    if provider_id not in _REGISTRY:
        raise ProviderError(f"Unknown provider: {provider_id}")
    return _REGISTRY[provider_id]


def list_providers() -> List[OCRProvider]:
    return list(_REGISTRY.values())


# Register defaults
register_provider(GoogleGeminiProvider())
register_provider(DummyEchoProvider())

# Register OpenAI (direct)
try:
    register_provider(OpenAIProvider())
except Exception:
    pass

# Register OpenRouter (if available/configured)
try:
    register_provider(OpenRouterProvider())
except Exception:
    pass

# Register local Tesseract if available
try:
    _t = LocalTesseractProvider()
    if _t.available:
        register_provider(_t)
except Exception:
    pass
