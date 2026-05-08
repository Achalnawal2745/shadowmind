# ShadowMind: AI-Powered Stealth Assistant 🕵️‍♂️🛡️

ShadowMind is a high-performance, invisible AI assistant designed for support during technical interviews. It leverages Gemini 2.5 Flash to provide real-time code solutions, explanations, and multimodal analysis while remaining completely hidden from proctoring software and screen-capture tools.

## 🚀 Key Features

*   **👻 Hardware Stealth**: Uses OS-level `SetWindowDisplayAffinity` to make the assistant window **completely invisible** to screenshots, screen sharing (Zoom/Teams), and recording software.
*   **⌨️ Hotkey-First Design**: Move, scroll, and capture text without ever clicking the app. Chrome/Exam window **never loses focus**.
*   **🧠 Conversation Memory**: Remembers previous questions and answers in the same session. Ask follow-up questions like *"elaborate on that"* or *"fix the bug in that code"*.
*   **📸 Multimodal Capture**: Capture any part of your screen (`Alt+S`) or highlight text (`Alt+T`) and get instant analysis.
*   **🎨 Rich UI Output**: Renders beautiful code blocks (Green/Consolas), bold text, and bullet points for easy scanning.
*   **📜 Auto-History**: Saves every exchange into a local `history.md` file for post-interview review.
*   **🚨 Panic Button**: A dedicated hotkey to instantly kill the process and wipe sensitive files.

## ⌨️ Global Hotkeys

| Hotkey | Action |
|--------|--------|
| **`Alt + A`** | Toggle Visibility (Show/Hide App) |
| **`Alt + T`** | **Capture Selected Text** (Auto-copies and sends to AI) |
| **`Alt + S`** | **Capture Screen** (Sends screenshot + instruction to AI) |
| **`F9`** | **Voice Input** (Push-to-talk mic input) |
| **`Ctrl + Arrows`** | **Move Window** (Moves app without clicking/focus loss) |
| **`Alt + Arrows`** | **Scroll Answer** (Scrolls output without clicking) |
| **`Alt + X`** | **PANIC BUTTON** (Instantly kills app & deletes evidence) |
| **`Ctrl + Q`** | Safe Exit |

## 🛠️ Setup

1.  **Install Requirements**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Get API Key**:
    Get a free Gemini API key from [Google AI Studio](https://aistudio.google.com/).
3.  **Run**:
    ```bash
    python main.py
    ```

## 🛡️ Stealth Best Practices

*   **Positioning**: Move the app directly below your webcam using `Ctrl + Arrows`. This ensures your eye movement looks natural while reading answers.
*   **Text over Images**: Use `Alt + T` whenever possible. It's faster and uses less API quota than screenshots.
*   **Whisper**: If using `F9`, speak very softly or whisper to avoid detection by proctoring mic-monitoring.

---
*Disclaimer: This tool is intended for educational and preparation purposes only. Use responsibly.*
