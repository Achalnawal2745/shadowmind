import tkinter as tk
from tkinter import simpledialog
import ctypes
import threading
import queue

from listener import VoiceListener
from ai_client import GeminiClient
from config import load_config, save_config


class GhostAssistant:
    def __init__(self):
        self.config = load_config()
        self.message_queue = queue.Queue()
        self.setup_ui()
        self.hide_from_capture()
        self.setup_assistant()

    # ─── UI ───────────────────────────────────────────────────────────────────

    def setup_ui(self):
        self.root = tk.Tk()
        self.root.title("ShadowMind")
        self.root.overrideredirect(True)          # no title bar
        self.root.attributes('-topmost', True)    # always on top
        self.root.attributes('-alpha', 0.93)
        self.root.wm_attributes('-toolwindow', True)  # hide from taskbar
        self.root.configure(bg='#0d0d1a')

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 440, 320
        self.root.geometry(f'{w}x{h}+{sw - w - 20}+{sh - h - 60}')

        self._build_ui()
        self._make_draggable()

    def _build_ui(self):
        # ── Header ──
        hdr = tk.Frame(self.root, bg='#1a1a2e', height=34)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        hdr.bind('<Button-1>', self.start_drag)
        hdr.bind('<B1-Motion>', self.drag)

        tk.Label(hdr, text='👻  ShadowMind', bg='#1a1a2e',
                 fg='#a78bfa', font=('Segoe UI', 10, 'bold')).pack(side='left', padx=10, pady=6)

        self.status_lbl = tk.Label(hdr, text='Hold F9 to capture',
                                   bg='#1a1a2e', fg='#6b7280', font=('Segoe UI', 8))
        self.status_lbl.pack(side='right', padx=10)

        # ── Question strip ──
        qf = tk.Frame(self.root, bg='#111827')
        qf.pack(fill='x', padx=0)
        tk.Label(qf, text='Q:', bg='#111827', fg='#6b7280',
                 font=('Segoe UI', 8, 'bold')).pack(side='left', padx=(10, 4), pady=5)
        self.q_lbl = tk.Label(qf, text='—', bg='#111827', fg='#9ca3af',
                              font=('Segoe UI', 8), wraplength=300, justify='left', anchor='w')
        self.q_lbl.pack(side='left', pady=5, fill='x', expand=True)

        self.copy_btn = tk.Button(qf, text="📋 Copy", bg='#1f2937', fg='#9ca3af', bd=0, font=('Segoe UI', 7), cursor='hand2', command=self.copy_all)
        self.copy_btn.pack(side='right', padx=10, pady=2)

        tk.Frame(self.root, bg='#1f2937', height=1).pack(fill='x')

        # ── Answer area ──
        af = tk.Frame(self.root, bg='#0d0d1a')
        af.pack(fill='both', expand=True, padx=12, pady=(10, 6))

        self.answer = tk.Text(af, bg='#0d0d1a', fg='#e2e8f0',
                              font=('Segoe UI', 10), wrap='word',
                              relief='flat', bd=0, cursor='arrow',
                              state='disabled', spacing2=3,
                              selectbackground='#1a1a2e')
        self.answer.pack(fill='both', expand=True)
        self.answer.bind("<Control-c>", self._copy_text)

        # colour tags
        self.answer.tag_config('normal', foreground='#e2e8f0')

        # ── Manual Text Input ──
        inf = tk.Frame(self.root, bg='#0d0d1a')
        inf.pack(fill='x', padx=12, pady=(0, 6))
        self.manual_entry = tk.Entry(inf, bg='#1f2937', fg='#e2e8f0',
                                     insertbackground='white', relief='flat', font=('Segoe UI', 9))
        self.manual_entry.pack(fill='x', ipady=3, padx=2)
        self.manual_entry.bind('<Return>', self.submit_manual)
        self.manual_entry.insert(0, " Type question here & press Enter...")
        self.manual_entry.bind("<FocusIn>", lambda args: self.manual_entry.delete('0', 'end') if "Type question" in self.manual_entry.get() else None)

        # ── Footer ──
        ft = tk.Frame(self.root, bg='#0a0a14', height=22)
        ft.pack(fill='x')
        ft.pack_propagate(False)
        tk.Label(ft, text='F9: mic  │  Alt+T: read text  │  Alt+A: hide  │  Ctrl+Q: quit',
                 bg='#0a0a14', fg='#374151', font=('Segoe UI', 7)).pack(pady=3)

    def _copy_text(self, event=None):
        try:
            selected = self.answer.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.root.clipboard_clear()
            self.root.clipboard_append(selected)
            self.root.update()
        except tk.TclError:
            pass
        return "break"

    def copy_all(self):
        text = self.answer.get("1.0", "end-1c")
        if text.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(text.strip())
            self.root.update()
            self.copy_btn.config(text="✅ Copied!")
            self.root.after(2000, lambda: self.copy_btn.config(text="📋 Copy"))

    def submit_manual(self, event=None):
        text = self.manual_entry.get().strip()
        if text and "Type question" not in text:
            self.manual_entry.delete(0, 'end')
            self.on_question(text)

    def _make_draggable(self):
        self.root.bind('<Button-1>', self.start_drag)
        self.root.bind('<B1-Motion>', self.drag)

    def start_drag(self, e):
        self._dx, self._dy = e.x, e.y

    def drag(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f'+{x}+{y}')

    # ─── Windows Capture Exclusion ────────────────────────────────────────────

    def hide_from_capture(self):
        """Make this window invisible to screen share / capture tools."""
        self.root.update()
        try:
            hwnd = int(self.root.wm_frame(), 16)
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            if result == 0:
                # Fallback to get_parent
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
                if result == 0:
                    print("[WARN] SetWindowDisplayAffinity failed completely.")
        except Exception as e:
            print(f"[WARN] Error setting display affinity: {e}")

    # ─── Assistant Setup ──────────────────────────────────────────────────────

    def setup_assistant(self):
        if not self.config.get('api_key'):
            self.ask_api_key()

        self.gemini = GeminiClient(self.config.get('api_key', ''))
        self.listener = VoiceListener(
            on_question=self.on_question,
            on_status=self.on_status
        )

        t = threading.Thread(target=self.listener.start, daemon=True)
        t.start()

        # global hotkeys (non-blocking)
        try:
            import keyboard
            keyboard.add_hotkey('alt+a', self.toggle_visibility)
            keyboard.add_hotkey('ctrl+q', self.quit)
            keyboard.add_hotkey('alt+t', lambda: self.message_queue.put(('grab_clipboard', None)))
        except Exception as e:
            print(f"[WARN] Hotkeys unavailable: {e}")

        self.root.after(80, self.process_queue)

    def ask_api_key(self):
        key = simpledialog.askstring(
            "First-time setup",
            "Enter your Gemini API key:\n(Free key → aistudio.google.com)",
            parent=self.root
        )
        if key and key.strip():
            self.config['api_key'] = key.strip()
            save_config(self.config)

    # ─── Callbacks (from threads → queue) ────────────────────────────────────

    def on_question(self, text):
        self.message_queue.put(('question', text))

    def on_status(self, text):
        self.message_queue.put(('status', text))

    # ─── Queue processor (main thread) ───────────────────────────────────────

    def process_queue(self):
        try:
            while True:
                kind, data = self.message_queue.get_nowait()
                if kind == 'question':
                    self._show_question(data)
                    self._start_streaming(data)
                elif kind == 'chunk':
                    self._append_chunk(data)
                elif kind == 'status':
                    self.status_lbl.config(text=data)
                elif kind == 'done':
                    self.status_lbl.config(text='F9: mic  │  Alt+T: read text')
                elif kind == 'grab_clipboard':
                    import keyboard
                    import pyperclip
                    import time
                    
                    pyperclip.copy('')
                    self.status_lbl.config(text='⌛ Wait...')
                    
                    # Tiny delay to ensure user has released the Alt+T keys
                    time.sleep(0.2)
                    
                    # Force release of modifiers just in case
                    keyboard.release('alt')
                    keyboard.release('t')
                    
                    # Send Copy
                    keyboard.press_and_release('ctrl+c')
                    
                    self.status_lbl.config(text='📋 Reading text...')
                    self.root.after(600, self._read_clipboard_and_send)
        except queue.Empty:
            pass
        self.root.after(80, self.process_queue)

    def _read_clipboard_and_send(self):
        import pyperclip
        try:
            text = pyperclip.paste()
            if text and len(text.strip()) > 1:
                self.on_question(text.strip())
            else:
                self.status_lbl.config(text='❌ No text found - try again')
        except Exception:
            self.status_lbl.config(text='❌ Selection error')

    def _show_question(self, text):
        short = text[:90] + '…' if len(text) > 90 else text
        self.q_lbl.config(text=short)
        self.answer.config(state='normal')
        self.answer.delete('1.0', 'end')
        self.answer.config(state='disabled')
        self.status_lbl.config(text='⚡ Thinking…')

    def _append_chunk(self, chunk):
        self.answer.config(state='normal')
        self.answer.insert('end', chunk, 'normal')
        self.answer.see('end')
        self.answer.config(state='disabled')

    def _start_streaming(self, question):
        def run():
            try:
                for chunk in self.gemini.stream(question):
                    self.message_queue.put(('chunk', chunk))
            except Exception as e:
                self.message_queue.put(('chunk', f'\n[Error: {e}]'))
            finally:
                self.message_queue.put(('done', None))
        threading.Thread(target=run, daemon=True).start()

    # ─── Window Controls ──────────────────────────────────────────────────────

    def toggle_visibility(self):
        if self.root.state() == 'withdrawn':
            self.root.deiconify()
        else:
            self.root.withdraw()

    def quit(self, event=None):
        import os
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()


if __name__ == '__main__':
    app = GhostAssistant()
    app.run()
