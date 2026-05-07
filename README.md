# 👻 ShadowMind — Stealth AI Interview Assistant

**ShadowMind** is a discreet, desktop-based AI assistant designed to help during interviews and coding challenges. It listens to audio, reads selected text, and provides real-time answers from Gemini AI in a floating window that is **completely invisible to screen-sharing software**.

---

## ✨ Key Features

- 👻 **Screen-Share Invisible:** Uses native Windows APIs to hide the app window from Zoom, Google Meet, Microsoft Teams, OBS, and screenshots.
- 🎙️ **Voice Capture (F9):** Push-to-talk recording. Hold F9 while the interviewer speaks, and the AI will transcribe and answer.
- 📋 **Instant Text Capture (Alt+T):** Highlight a coding question on your screen and press `Alt+T`. The app instantly reads it and provides a solution.
- 🤖 **Gemini 2.5 Flash:** Powered by Google's latest high-speed AI for near-instant responses.
- ⌨️ **Stealth Hotkeys:** 
    - `Alt+A`: Hide/Show the assistant window instantly.
    - `Alt+T`: Read highlighted text on screen.
    - `F9`: Hold to record audio from your microphone.
    - `Ctrl+Q`: Safety exit (kills all background processes).

---

## 🚀 Getting Started

### 1. Prerequisites
- **Windows 10/11** (Required for screen-hiding feature)
- **Python 3.8+**
- **Gemini API Key:** Get a free key at [aistudio.google.com](https://aistudio.google.com/app/apikey)

### 2. Installation

1. Clone this repository or download the files.
2. Open a terminal in the project folder and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *Note: If `pyaudio` fails to install, try `pip install pipwin` followed by `pipwin install pyaudio`.*

### 3. Running ShadowMind

Simply double-click `run.bat` or run the script manually:
```bash
python main.py
```
On first launch, you will be prompted to enter your Gemini API Key. It will be saved locally in `config.json`.

---

## 🎮 How to Use (Stealth Mode)

1. **Start the app** before your interview.
2. Press **`Alt+A`** to hide the window. It is now running silently in the background.
3. When a question is asked:
    - **Verbal:** Hold **`F9`** while they speak, then release.
    - **Written/Code:** Highlight the text with your mouse and press **`Alt+T`**.
4. Wait 2 seconds, then press **`Alt+A`** to reveal the answer.
5. Use the **📋 Copy** button in the UI to copy the AI's code/answer to your clipboard.
6. Press **`Alt+A`** again to vanish.

---

## 🛡️ Disclaimer
This tool is intended for educational purposes and personal productivity. Please use ShadowMind ethically and in accordance with the rules and policies of your interviewers or institutions.
