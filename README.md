# LaTeXVision OCR 🔮📄

**LatexVision OCR** is a powerful, high-precision OCR tool designed specifically for scientific and technical documents. It leverages state-of-the-art AI models (Google Gemini, OpenAI, OpenRouter) to transcribe PDFs into clean, structured Markdown, with a non-negotiable focus on **perfect LaTeX math formatting**.

Ideal for digitizing engineering textbooks, research papers, and complex mathematical notes.

## ✨ Features

- **Strict LaTeX Math Enforcement**: Automatically detects mathematical expressions (variables, equations, units) and wraps them in standard LaTeX delimiters (`$...$` and `$$...$$`). No more broken plain-text math!
- **AI-Powered Accuracy**: Uses large language models (LLMs) to ensure context-aware transcription that beats traditional OCR on complex layouts.
- **Provider Agnostic**: Switch seamlessly between:
  - **Google Gemini** (Recommended for speed/cost)
  - **OpenAI** (GPT-4o/mini)
  - **OpenRouter** (Access to Claude, Llama, etc.)
- **Parallel Processing**: Multi-threaded worker pipeline to transcribe pages concurrently, maximizing throughput.
- **Smart Formatting**:
  - Preserves tables as GitHub-flavored Markdown.
  - Intelligently summarizes complex diagrams (anti-hallucination).
  - Skips internal plot text to keep output clean.
- **GUI Interface**: User-friendly Dark/Light mode interface built with Tkinter.

## 🛠️ Requirements

- **Python 3.8+**
- An API Key for your chosen provider:
  - `GEMINI_API_KEY` (Google)
  - `OPENAI_API_KEY` (OpenAI)
  - `OPENROUTER_API_KEY` (OpenRouter)

## 📦 Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/LatexVision-OCR.git
    cd LatexVision-OCR
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## 🚀 Usage

1.  **Set your API Key(s)** (Environment variables or system-wide):
    On Windows (PowerShell):
    ```powershell
    $env:GEMINI_API_KEY="your_key_here"
    ```
    On Mac/Linux:
    ```bash
    export GEMINI_API_KEY="your_key_here"
    ```

2.  **Run the App:**
    ```bash
    python "PDF OCR APP.py"
    ```

3.  **In the App:**
    - **Select PDF**: Choose your source file.
    - **Pages**: Enter range (e.g., `1-10`, `5,8,12`, or `all`).
    - **Provider**: Select your AI provider (default: Google Gemini).
    - **Concurrency**: Adjust parallel threads based on your rate limits.
    - **Start OCR**: Watch the log as pages are transcribed in real-time!

## 📝 Configuration

The application allows various configurations via the UI:
- **DPI**: Adjust render quality (default 300).
- **Dark Mode**: Toggle for visual comfort.
- **Strict Mode**: The underlying prompt is engineered to reject hallucinations and strictly adhere to "Literal Transcription" rules.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

[MIT License](LICENSE)
