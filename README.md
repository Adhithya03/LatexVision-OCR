# PDF OCR Tool 📄🔮

<img width="1158" height="931" alt="image" src="https://github.com/user-attachments/assets/0bba0d52-7bab-43a5-a864-70ea6c8c827b" />

A specialized OCR application for scientific and technical documents. It strictly enforces LaTeX formatting for math and uses LLMs (Gemini, OpenAI) for high-precision transcription.

## 🚀 Key Features

*   **Strict LaTeX Enforcement**: All math is wrapped in `$...$` or `$$...$$` delimiters.
*   **Literal Transcription**: Preserves formatting, tables, and lists. No summarization.
*   **Provider Agnostic**: Supports Google Gemini, OpenAI, and OpenRouter.
*   **Parallel Processing**: Multi-threaded rendering and concurrent API requests.
*   **GUI Interface**: Python Tkinter UI with Dark Mode support.

## 🛠️ Requirements

*   Python 3.8+
*   `pypdfium2`, `google-genai`, `openai`, `Pillow` (see `requirements.txt`)

## ⚙️ Setup & Usage

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    *   `GEMINI_API_KEY` (Default: `gemini-2.5-flash-lite`)
    *   `OPENAI_API_KEY` (Default: `gpt-4.1-mini`)
    *   `OPENROUTER_API_KEY` (Default: `openai/gpt-4.1-mini`)

3.  **Run**:
    ```bash
    python "PDF OCR APP.py"
    ```

## 🏗️ Technical Overview

*   **`PDF OCR APP.py`** (Frontend)
    *   Launches the Tkinter GUI and manages UI state.
    *   Contains `STRICT_OCR_PROMPT_TEMPLATE`, the system prompt engineered for literal transcription.

*   **`ocr_worker.py`** (Orchestration)
    *   `OCRWorker`: Manages a Producer-Consumer pipeline.
    *   *Producer*: Renders PDF pages to PNG using `pypdfium2`.
    *   *Consumers*: Worker pool executing concurrent API requests with exponential backoff.

*   **`ocr_providers.py`** (Backend)
    *   Implements an abstraction layer for different LLM providers.
    *   Centralizes API client initialization and model defaults.
