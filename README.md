# PDF OCR Tool

A specialized OCR application designed for scientific and technical documents. It strictly enforces LaTeX formatting for mathematical expressions and uses LLMs (Gemini, OpenAI) for high-precision transcription.

## Key Features

*   **Strict LaTeX Enforcement**: All math is wrapped in `$...$` or `$$...$$`.
*   **Literal Transcription**: Preserves original formatting, tables, and lists. No summarization or "fixing".
*   **Provider Agnostic**: Supports Google Gemini, OpenAI, and OpenRouter.
*   **Concurrent Processing**: Multi-threaded rendering and API requests for speed.
*   **GUI**: Python Tkinter interface with dark mode and real-time logs.

## Requirements

*   Python 3.8+
*   `pypdfium2`, `google-genai`, `openai`, `Pillow` (see `requirements.txt`)

## Configuration & Usage

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Set Environment Variables** (API Keys):
    *   `GEMINI_API_KEY` (Default model: `gemini-2.5-flash-lite`)
    *   `OPENAI_API_KEY` (Default model: `gpt-4.1-mini`)
    *   `OPENROUTER_API_KEY` (Default model: `openai/gpt-4.1-mini`)
    
    *Note: Default models can be overridden via `GEMINI_MODEL`, `OPENAI_MODEL`, etc.*

3.  **Run the Application**:
    ```bash
    python "PDF OCR APP.py"
    ```

## Technical Overview

The project consists of three main modules:

*   **`PDF OCR APP.py`** (Frontend)
    *   **Entry Point**: Launches the Tkinter GUI.
    *   **Settings**: Manages inputs for file paths, page ranges, DPI, and concurrency.
    *   **Prompting**: Defines the `STRICT_OCR_PROMPT_TEMPLATE` which instructs the LLM to behave as a literal transcriber and enforce LaTeX rules.

*   **`ocr_worker.py`** (Orchestration)
    *   **`OCRWorker`**: A threaded class managing the OCR pipeline.
    *   **Producer-Consumer**:
        *   *Producer*: Renders PDF pages to PNG images using `pypdfium2`.
        *   *Consumers*: A pool of worker threads sending concurrent requests to the selected API provider.
    *   **Robustness**: Implements retry logic with exponential backoff for API failures.

*   **`ocr_providers.py`** (Backend)
    *   **`OCRProvider`**: Abstract base class defining the interface (`create_thread_client`, `transcribe`).
    *   **Implementations**:
        *   `GoogleGeminiProvider`: Uses `google-genai` SDK.
        *   `OpenAIProvider`: Direct OpenAI integration.
        *   `OpenRouterProvider`: OpenAI-compatible interface for OpenRouter.
    *   **Configuration**: Central place for default model constants and API client initialization.