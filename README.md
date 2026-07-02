# ShadowMind: AI-Powered Stealth Assistant 🕵️‍♂️🛡️

ShadowMind is a high-performance, invisible AI assistant designed for support during technical interviews. It leverages Gemini 2.5 Flash as a primary driver, with dynamic, multi-tier fallback rotation to Groq and OpenRouter to ensure 100% uptime even under heavy rate limits or server outages. It is engineered to remain completely hidden from proctoring software and screen-capture tools.

## 🚀 Key Features

*   **👻 Hardware Stealth**: Uses OS-level `SetWindowDisplayAffinity` to make the assistant window **completely invisible** to screenshots, screen sharing (Zoom/Teams), and recording software.
*   **🔄 API Key Rotation & Uptime Fallbacks**: Automatically shifts to backup free models (like Qwen, Gemma, and Nemotron) on **Groq** and **OpenRouter** if your primary Gemini key hits rate limits (429) or traffic blocks. Rotation happens instantly and silently with no delays.
*   **🛠️ Stealth Compilation (Process Hiding)**: Includes built-in support to compile the app into a single, standalone system-masked executable (`IntelAudioService.exe`) with a hidden console window to bypass process-name blacklists used by downloadable proctors (like Unstop SmartHire).
*   **⌨️ Hotkey-First Design**: Move, scroll, and capture text without ever clicking the app. Chrome/Exam window **never loses focus**.
*   **🧠 Conversation Memory**: Remembers previous questions and answers in the same session. Ask follow-up questions like *"elaborate on that"* or *"fix the bug in that code"*.
*   **📸 Multimodal Capture**: Capture any part of your screen (`Alt+S`) or highlight text (`Alt+T`) and get instant analysis.
*   **🎨 Rich UI Output**: Renders beautiful code blocks (Green/Consolas), bold text, and bullet points for easy scanning.
*   **📜 Auto-History**: Saves every exchange into a local `history.md` file for post-interview review.
*   **🚨 Panic Button**: A dedicated hotkey (`Alt + X`) to instantly kill the process, clear the clipboard, and delete all trace files (`history.md` and screenshot cache).

## ⌨️ Global Hotkeys

| Hotkey | Action |
|--------|--------|
| **`Alt + A`** | Toggle Visibility (Show/Hide App) |
| **`Alt + T`** | **Capture Selected Text** (Auto-copies and sends to AI) |
| **`Alt + S`** | **Capture Screen** (Sends screenshot + instruction to AI) |
| **`F9`** | **Voice Input** (Push-to-talk mic + speaker input) |
| **`Ctrl + Arrows`** | **Move Window** (Moves app without clicking/focus loss) |
| **`Alt + Arrows`** | **Scroll Answer** (Scrolls output without clicking) |
| **`Alt + B`** | **Ultra-Stealth Toggle** (Transparent / Dim Mode) |
| **`Alt + X`** | **PANIC BUTTON** (Instantly kills app & deletes evidence) |
| **`Ctrl + Q`** | Safe Exit |

## 🛠️ Setup

1.  **Install Requirements**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Add API Keys** (in `config.json`):
    Add your API keys to the configuration file. Groq and OpenRouter keys are optional fallback backups:
    ```json
    {
      "api_key": "YOUR_GEMINI_API_KEY",
      "groq_api_key": "OPTIONAL_GROQ_API_KEY",
      "openrouter_api_key": "OPTIONAL_OPENROUTER_API_KEY"
    }
    ```
3.  **Compile to Stealth Binary (Optional)**:
    If running under downloadable proctoring software, run the build script to compile the python script into a system-masked executable:
    ```bash
    build_exe.bat
    ```
    This creates `dist\IntelAudioService.exe`. Move `config.json` into the `dist/` directory next to it, and double click the executable to run it headlessly in the background.
4.  **Run directly (Developer Mode)**:
    If you don't need process hiding, just run:
    ```bash
    run.bat
    ```

## 🛡️ Stealth Best Practices

*   **Positioning**: Move the app directly below your webcam using `Ctrl + Arrows`. This ensures your eye movement looks natural while reading answers.
*   **Text over Images**: Use `Alt + T` whenever possible. It's faster and uses less API quota than screenshots.
*   **Whisper**: If using `F9`, speak very softly or whisper to avoid detection by proctoring mic-monitoring.
*   **Process Masking**: When facing strict proctors (like Unstop SmartHire), compile the binary using `build_exe.bat` and fully quit Telegram/Discord from the system tray taskbar before starting your test.

---
*Disclaimer: This tool is intended for educational and preparation purposes only. Use responsibly.*
