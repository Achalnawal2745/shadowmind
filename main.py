import tkinter as tk
from tkinter import simpledialog, messagebox
import ctypes
import threading
import queue
import time
import os
import keyboard
import pyperclip
import mss
import io

from listener import VoiceListener
from ai_client import GeminiClient
from config import load_config, save_config
from stealth import StealthEngine


class GhostAssistant:
    def __init__(self):
        import sys
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.config = load_config()
        self.message_queue = queue.Queue()
        self.current_stream_id = 0  # Used to cancel old requests
        self._current_question = ""   # Tracks active question for history
        self._answer_buffer = []       # Buffers chunks for history saving
        self.setup_ui()
        self.hide_from_capture()
        self.setup_assistant()

    # ─── UI ───────────────────────────────────────────────────────────────────

    def setup_ui(self):
        try:
            # Fix Windows DPI scaling shrinking bug
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.root = tk.Tk()
        self.root.title("ShadowMind")
        self.root.overrideredirect(True)          # no title bar
        self.root.attributes('-topmost', True)    # always on top
        self.root.attributes('-alpha', 0.93)
        self.root.wm_attributes('-toolwindow', True)  # hide from taskbar
        self.root.configure(bg='#0d0d1a')

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 550, 400
        self.root.geometry(f'{w}x{h}+{sw - w - 20}+{sh - h - 60}')
        self.root.resizable(False, False)
        self.root.pack_propagate(False)
        self.root.minsize(w, h)

        self._build_ui()
        self._make_draggable()

    def _build_ui(self):
        # ── Master Container ──
        self.main_container = tk.Frame(self.root, bg='#0d0d1a', width=550, height=400)
        self.main_container.pack(fill='both', expand=True)
        self.main_container.pack_propagate(False) # Strict lock on contents
        
        # ── Header ──
        hdr = tk.Frame(self.main_container, bg='#1a1a2e', height=34)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        hdr.bind('<Button-1>', self.start_drag)
        hdr.bind('<B1-Motion>', self.drag)

        tk.Label(hdr, text='👻  ShadowMind', bg='#1a1a2e',
                 fg='#a78bfa', font=('Segoe UI', 10, 'bold')).pack(side='left', padx=10, pady=6)

        # ── ℹ️ Info button ──
        self.info_btn = tk.Button(
            hdr, text='ℹ️', bg='#1a1a2e', fg='#6b7280',
            font=('Segoe UI', 9), relief='flat', bd=0, cursor='hand2',
            activebackground='#2d2d4e', activeforeground='#a78bfa',
            command=self.show_stealth_info
        )
        self.info_btn.pack(side='right', padx=(0, 6), pady=4)

        # ── 🛡️ Super Stealth toggle button ──
        self.stealth_btn = tk.Button(
            hdr, text='🛡️ Super Stealth', bg='#1f2937', fg='#9ca3af',
            font=('Segoe UI', 8, 'bold'), relief='flat', bd=0, cursor='hand2',
            activebackground='#374151', activeforeground='#a78bfa',
            command=self.toggle_super_stealth
        )
        self.stealth_btn.pack(side='right', padx=(0, 4), pady=4)

        self.status_lbl = tk.Label(hdr, text='ShadowMind Active │ Alt+X: Panic',
                                   bg='#1a1a2e', fg='#6b7280', font=('Segoe UI', 8))
        self.status_lbl.pack(side='right', padx=10)

        # ── Question strip ──
        qf = tk.Frame(self.main_container, bg='#111827', height=28)
        qf.pack(fill='x', padx=0)
        qf.pack_propagate(False)
        tk.Label(qf, text='Q:', bg='#111827', fg='#6b7280',
                 font=('Segoe UI', 8, 'bold')).pack(side='left', padx=(10, 4), pady=4)
        self.q_lbl = tk.Label(qf, text='—', bg='#111827', fg='#9ca3af',
                              font=('Segoe UI', 8), anchor='w')
        self.q_lbl.pack(side='left', pady=4, fill='x', expand=True)

        self.copy_btn = tk.Button(qf, text="📋 Copy", bg='#1f2937', fg='#9ca3af', bd=0, font=('Segoe UI', 7), cursor='hand2', command=self.copy_all)
        self.copy_btn.pack(side='right', padx=10, pady=2)

        tk.Frame(self.main_container, bg='#1f2937', height=1).pack(fill='x')

        # ── Footer ──
        ft = tk.Frame(self.main_container, bg='#0a0a14', height=22)
        ft.pack(side='bottom', fill='x')
        ft.pack_propagate(False)
        tk.Label(ft, text='F9: mic+speaker │ Alt+T: text │ Alt+S: screen │ Alt+B: Stealth │ Alt+X: PANIC',
                 bg='#0a0a14', fg='#4b5563', font=('Segoe UI', 7)).pack(pady=3)

        # ── Manual Text Input ──
        inf = tk.Frame(self.main_container, bg='#0d0d1a')
        inf.pack(side='bottom', fill='x', padx=12, pady=(0, 6))
        self.manual_entry = tk.Entry(inf, bg='#1f2937', fg='#e2e8f0',
                                     insertbackground='white', relief='flat', font=('Segoe UI', 9))
        self.manual_entry.pack(fill='x', ipady=3, padx=2)
        self.manual_entry.bind('<Return>', self.submit_manual)
        self.manual_entry.insert(0, " Type question here & press Enter...")
        self.manual_entry.bind("<FocusIn>", lambda args: self.manual_entry.delete('0', 'end') if "Type question" in self.manual_entry.get() else None)
        self.manual_entry.bind("<Button-1>", lambda args: (self.manual_entry.focus_force(), self.manual_entry.delete('0', 'end') if "Type question" in self.manual_entry.get() else None))

        # ── Answer area ──
        af = tk.Frame(self.main_container, bg='#0d0d1a')
        af.pack(side='top', fill='both', expand=True, padx=12, pady=(10, 6))

        self.answer = tk.Text(af, bg='#0d0d1a', fg='#e2e8f0',
                              font=('Segoe UI', 10), wrap='word',
                              relief='flat', bd=0, cursor='arrow',
                              state='disabled', spacing2=3,
                              selectbackground='#1a1a2e')
        self.answer.pack(fill='both', expand=True)
        self.answer.bind("<Control-c>", self._copy_text)

        # ── Text formatting tags ──
        self.answer.tag_config('normal',      foreground='#e2e8f0', font=('Segoe UI', 10))
        self.answer.tag_config('bold',        foreground='#ffffff', font=('Segoe UI', 10, 'bold'))
        self.answer.tag_config('header',      foreground='#a78bfa', font=('Segoe UI', 12, 'bold'))
        self.answer.tag_config('bullet',      foreground='#7dd3fc', font=('Segoe UI', 10))
        self.answer.tag_config('inline_code', foreground='#fbbf24', font=('Consolas', 9),
                               background='#1e293b')
        self.answer.tag_config('code_block',  foreground='#86efac', font=('Consolas', 9),
                               background='#0f172a', lmargin1=12, lmargin2=12,
                               spacing1=4, spacing3=4)
        self.answer.tag_config('code_lang',   foreground='#475569', font=('Consolas', 8),
                               background='#0f172a')
        self.answer.tag_config('current_word', background='#fbbf24', foreground='#0d0d1a')  # Yellow teleprompter highlight

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
        # Extract all configured Gemini keys
        gemini_keys = []
        if self.config.get('api_key'):
            gemini_keys.append(self.config.get('api_key').strip())
        
        for i in range(1, 10):
            for k_name in [f'gemini_api_key_{i}', f'gemini_key_{i}', f'api_key_{i}']:
                val = self.config.get(k_name)
                if val and isinstance(val, str) and val.strip() and val.strip() not in gemini_keys:
                    gemini_keys.append(val.strip())

        if not gemini_keys and not self.config.get('groq_api_key') and not self.config.get('openrouter_api_key'):
            self.ask_api_key()

        self.gemini = GeminiClient(
            gemini_key=gemini_keys,
            groq_key=self.config.get('groq_api_key', ''),
            openrouter_key=self.config.get('openrouter_api_key', '')
        )

        self.listener = VoiceListener(
            on_question=self.on_question,
            on_status=self.on_status
        )

        t = threading.Thread(target=self.listener.start, daemon=True)
        t.start()

        self.ghost_mode = False
        self._super_stealth_active = False
        self._stealth_engine = None
        self._keyboard_hotkey_handles = []  # Track handles for unhooking

        # global hotkeys (non-blocking) — used in normal mode
        self._register_keyboard_hotkeys()

        # Cloak the process name at startup (always active, harmless)
        StealthEngine.cloak_process()

        self.root.after(80, self.process_queue)

    def _register_keyboard_hotkeys(self):
        """Register all hotkeys using the keyboard library (normal mode)."""
        self._keyboard_hotkey_handles = []
        try:
            import keyboard
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('alt+a', self.toggle_visibility))
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('ctrl+q', self.quit))
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('alt+t', lambda: self.message_queue.put(('grab_clipboard', None))))
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('alt+s', lambda: self.message_queue.put(('grab_screenshot', None))))
            
            # Safe Movement Hotkeys
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('ctrl+up', lambda: self.move_window(0, -50)))
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('ctrl+down', lambda: self.move_window(0, 50)))
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('ctrl+left', lambda: self.move_window(-50, 0)))
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('ctrl+right', lambda: self.move_window(50, 0)))
            
            # Safe Scrolling Hotkeys
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('alt+up', lambda: self.scroll_answer(-3)))
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('alt+down', lambda: self.scroll_answer(3)))
            
            # Ultra Stealth Toggle
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('alt+b', self.toggle_stealth_style))

            # THE PANIC BUTTON
            self._keyboard_hotkey_handles.append(
                keyboard.add_hotkey('alt+x', self.panic_exit))

        except Exception as e:
            print(f"[WARN] Hotkeys unavailable: {e}")

    def _unregister_keyboard_hotkeys(self):
        """Remove all keyboard library hotkeys (used when Super Stealth takes over)."""
        try:
            import keyboard
            for handle in self._keyboard_hotkey_handles:
                try:
                    keyboard.remove_hotkey(handle)
                except Exception:
                    pass
            self._keyboard_hotkey_handles = []
        except Exception:
            pass

    def scroll_answer(self, units):
        # Thread-safe UI update
        self.root.after(0, lambda: self.answer.yview_scroll(units, "units"))

    def move_window(self, dx, dy):
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f'+{x}+{y}')

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
        # Automatically attach any typed instruction to voice (F9) or clipboard (Alt+T) requests
        try:
            user_instruction = self.manual_entry.get().strip()
            if user_instruction and user_instruction != "Type question here & press Enter...":
                text = f"USER SPECIFIC INSTRUCTION: {user_instruction}\n\nPlease fulfill the instruction using the context below:\n{text}"
                self.manual_entry.delete(0, 'end')
        except Exception:
            pass
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
                    # Re-render with live markdown on every chunk (ChatGPT style)
                    self._answer_buffer.append(data)
                    self._render_markdown(''.join(self._answer_buffer))
                    self.root.update_idletasks()
                    self.root.after(25, self.process_queue)
                    return
                elif kind == 'status':
                    self.status_lbl.config(text=data)
                elif kind == 'done':
                    self.status_lbl.config(text='F9/Alt+T/Alt+S active │ Alt+X: Panic')
                    self._save_history()
                elif kind == 'grab_screenshot':
                    self.on_status('📸 Capturing screen...')
                    self._take_screenshot_and_send()
                elif kind == 'grab_clipboard':
                    now = time.time()
                    if hasattr(self, '_last_req_time') and now - self._last_req_time < 1.0:
                        continue
                    self._last_req_time = now

                    initial_text = ""
                    try:
                        initial_text = pyperclip.paste()
                    except Exception:
                        pass
                    
                    self._initial_clipboard_text = initial_text
                    pyperclip.copy('')
                    self.status_lbl.config(text='📋 Reading selection...')

                    def _do_grab():
                        try:
                            u32 = ctypes.windll.user32
                            KEYUP = 0x0002
                            
                            # Give user a tiny fraction of a second to lift their fingers
                            time.sleep(0.15)
                            
                            # Force release all common modifier keys just in case
                            u32.keybd_event(0x12, 0, KEYUP, 0)  # Alt up
                            u32.keybd_event(0x11, 0, KEYUP, 0)  # Ctrl up
                            u32.keybd_event(0x10, 0, KEYUP, 0)  # Shift up
                            u32.keybd_event(0x54, 0, KEYUP, 0)  # T up
                            
                            time.sleep(0.1) # Wait for OS to register release
                            
                            # Press Ctrl+C using hardware events
                            u32.keybd_event(0x11, 0, 0, 0)      # Ctrl down
                            time.sleep(0.02)
                            u32.keybd_event(0x43, 0, 0, 0)      # C down
                            time.sleep(0.05)
                            u32.keybd_event(0x43, 0, KEYUP, 0)  # C up
                            time.sleep(0.02)
                            u32.keybd_event(0x11, 0, KEYUP, 0)  # Ctrl up
                        except Exception as e:
                            print(f"[Grab Error] {e}")

                    threading.Thread(target=_do_grab, daemon=True).start()
                    self._poll_attempts = 0
                    self.root.after(350, self._poll_clipboard_and_send)
        except queue.Empty:
            pass
        self.root.after(30, self.process_queue)

    def _poll_clipboard_and_send(self):
        import pyperclip
        try:
            text = pyperclip.paste()
            if text and len(text.strip()) > 1:
                self.on_question(text.strip())
                return
        except Exception:
            pass

        self._poll_attempts += 1
        if self._poll_attempts < 10:
            self.root.after(100, self._poll_clipboard_and_send)
        else:
            # Fallback to pre-existing clipboard text if user used Ctrl+C manually
            fallback = getattr(self, '_initial_clipboard_text', '')
            if fallback and len(fallback.strip()) > 1:
                self.on_question(fallback.strip())
            else:
                self.status_lbl.config(text='❌ No text selected - select text & try Alt+T')

    def toggle_stealth_style(self):
        """Toggle between Normal and Ultra-Stealth (transparent/gray) mode."""
        if not hasattr(self, '_is_ultra_stealth'): self._is_ultra_stealth = False
        self._is_ultra_stealth = not self._is_ultra_stealth
        
        if self._is_ultra_stealth:
            self.root.attributes('-alpha', 0.4) # Very transparent
            self.answer.config(fg='#4b5563')   # Dim gray text
            self.on_status("🕵️ Stealth Mode ON")
        else:
            self.root.attributes('-alpha', 0.93)
            self.answer.config(fg='#e2e8f0')   # Normal bright text
            self.on_status("👁️ Normal Mode ON")

    def panic_exit(self):
        """Instantly close and delete sensitive evidence."""
        try:
            # Deactivate stealth first
            if self._stealth_engine:
                self._stealth_engine.deactivate()
        except:
            pass
        try:
            import pyperclip
            pyperclip.copy('') # Clear clipboard
            # Delete files
            for f in ['history.md', 'last_screenshot_seen_by_ai.png']:
                path = os.path.join(self.base_dir, f)
                if os.path.exists(path):
                    os.remove(path)
        except:
            pass
        os._exit(0) # Force kill immediately

    def _save_history(self):
        try:
            question = self._current_question
            answer = ''.join(self._answer_buffer).strip()
            if not answer or not question:
                return
            import datetime
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            history_path = os.path.join(self.base_dir, 'history.md')
            with open(history_path, 'a', encoding='utf-8') as f:
                f.write(f"\n---\n**[{ts}]**\n\n**Q:** {question}\n\n**A:** {answer}\n")
        except Exception as e:
            print(f"[History] Save error: {e}")

    def _show_question(self, text):
        self._current_question = text  # Save full question for AI & history
        self._answer_buffer = []       # Reset answer buffer
        clean_preview = text.replace('\n', ' ').strip()
        short = (clean_preview[:75] + '...') if len(clean_preview) > 75 else clean_preview
        self.q_lbl.config(text=short)
        self.answer.config(state='normal')
        self.answer.delete('1.0', 'end')
        self.answer.config(state='disabled')
        self.status_lbl.config(text='⚡ Thinking…')
        self.answer.see('1.0')  # Anchor to top
        self._force_geometry()

    def _append_chunk(self, chunk):
        self._answer_buffer.append(chunk)  # Buffer for history
        self.answer.config(state='normal')
        # Remove previous highlight
        self.answer.tag_remove('current_word', '1.0', 'end')
        # Insert the new chunk
        self.answer.insert('end', chunk, 'normal')
        # Highlight the last word just inserted (teleprompter effect)
        end_idx = self.answer.index('end-1c')
        words = chunk.strip().split()
        if words:
            last_word = words[-1]
            search_start = f'end-{len(chunk)+1}c'
            pos = self.answer.search(last_word, search_start, stopindex='end', regexp=False)
            if pos:
                word_end = f'{pos}+{len(last_word)}c'
                self.answer.tag_add('current_word', pos, word_end)
        self.answer.config(state='disabled')
        self._force_geometry()

    def _render_markdown(self, text):
        """Re-render the full answer with rich markdown formatting."""
        import re
        self.answer.config(state='normal')
        self.answer.delete('1.0', 'end')

        in_code_block = False
        code_lines = []
        code_lang = ''

        lines = text.split('\n')
        for i, line in enumerate(lines):
            # ── Fenced code block start/end ──
            if line.strip().startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    code_lang = line.strip()[3:].strip()
                    if code_lang:
                        self.answer.insert('end', f' {code_lang}\n', 'code_lang')
                else:
                    in_code_block = False
                    full_code = '\n'.join(code_lines)

                    # ── Embed a "Copy Code" button above code block ──
                    def make_copy_cmd(code=full_code):
                        def _copy():
                            self.root.clipboard_clear()
                            self.root.clipboard_append(code)
                            self.root.update()
                        return _copy

                    btn = tk.Button(
                        self.answer,
                        text='📋 Copy Code',
                        command=make_copy_cmd(),
                        bg='#1e293b', fg='#94a3b8',
                        font=('Segoe UI', 7),
                        relief='flat', bd=0,
                        cursor='hand2',
                        padx=6, pady=1,
                        activebackground='#334155',
                        activeforeground='#e2e8f0'
                    )
                    self.answer.insert('end', '\n')
                    self.answer.window_create('end', window=btn)
                    self.answer.insert('end', '\n')
                    self.answer.insert('end', full_code + '\n', 'code_block')
                    code_lines = []
                    code_lang = ''
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            # ── Header ──
            if re.match(r'^#{1,3}\s+', line):
                clean = re.sub(r'^#{1,3}\s+', '', line)
                self._insert_inline(clean + '\n', default_tag='header')
                continue

            # ── Bullet point ──
            if re.match(r'^[-*•]\s+', line):
                self.answer.insert('end', '  • ', 'bullet')
                rest = re.sub(r'^[-*•]\s+', '', line)
                self._insert_inline(rest + '\n')
                continue

            # ── Normal line with inline formatting ──
            self._insert_inline(line + '\n')

        # Flush unclosed code block
        if code_lines:
            self.answer.insert('end', '\n'.join(code_lines) + '\n', 'code_block')

        self.answer.see('1.0')  # Ensure we stay at the top after re-rendering
        self.answer.config(state='disabled')

    def _insert_inline(self, text, default_tag='normal'):
        """Insert a line of text, applying bold and inline code tags."""
        import re
        # Pattern: **bold** or `inline code`
        pattern = re.compile(r'(\*\*.+?\*\*|`.+?`)')
        parts = pattern.split(text)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                self.answer.insert('end', part[2:-2], 'bold')
            elif part.startswith('`') and part.endswith('`'):
                self.answer.insert('end', part[1:-1], 'inline_code')
            else:
                self.answer.insert('end', part, default_tag)
        
    def _force_geometry(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 550, 400
        # If it moved, we want to keep its current X/Y, just force WxH.
        current_x = self.root.winfo_x()
        current_y = self.root.winfo_y()
        self.root.geometry(f'{w}x{h}+{current_x}+{current_y}')

    def _start_streaming(self, question, image_bytes=None):
        self.current_stream_id += 1
        my_stream_id = self.current_stream_id

        def run():
            import time
            retries = 2
            for attempt in range(retries + 1):
                try:
                    for chunk in self.gemini.stream(question, image_bytes=image_bytes):
                        if self.current_stream_id != my_stream_id:
                            return # Cancelled by a newer request!
                        self.message_queue.put(('chunk', chunk))
                    
                    if self.current_stream_id == my_stream_id:
                        self.message_queue.put(('done', None))
                    return # Success!
                except Exception as e:
                    if self.current_stream_id != my_stream_id:
                        return # Cancelled
                    if "429" in str(e) and attempt < retries:
                        self.message_queue.put(('chunk', f"\n[Rate limit hit, retrying in 2s... attempt {attempt+1}]"))
                        time.sleep(2)
                        continue
                    self.message_queue.put(('chunk', f'\n[Error: {e}]'))
                    break
            
            if self.current_stream_id == my_stream_id:
                self.message_queue.put(('done', None))
        threading.Thread(target=run, daemon=True).start()

    def _take_screenshot_and_send(self):
        try:
            from PIL import Image
            import io
            img_bytes = None

            # Method 1: Standard mss capture (works on most apps)
            print("[Screenshot] Trying mss capture...")
            try:
                with mss.MSS() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    
                    extrema = img.convert('L').getextrema()
                    print(f"[Screenshot] mss extrema: {extrema}")
                    if extrema[1] > 10:
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        img_bytes = buf.getvalue()
                        print(f"[Screenshot] mss success: {len(img_bytes)} bytes")
            except Exception as e:
                print(f"[Screenshot] mss failed: {e}")

            # Method 2: Stealth BitBlt/PrintWindow (bypasses some screen protection)
            if not img_bytes:
                print("[Screenshot] mss was black, trying stealth capture...")
                stealth_bytes = StealthEngine.stealth_screenshot()
                if stealth_bytes:
                    img_bytes = stealth_bytes
                    print(f"[Screenshot] Stealth success: {len(img_bytes)} bytes")
                else:
                    print("[Screenshot] Stealth also failed/black")

            if not img_bytes:
                self.on_status("⚠️ Screen capture blocked - try Alt+T instead")
                print("[Screenshot] ALL methods failed")
                return

            # Save a copy so the user can verify what was captured
            screenshot_path = os.path.join(self.base_dir, "last_screenshot_seen_by_ai.png")
            with open(screenshot_path, "wb") as f:
                f.write(img_bytes)

            self._show_question("📸 Screen captured! Sending to AI...")
            
            # Check if user typed a specific instruction in the text box
            user_instruction = self.manual_entry.get().strip()
            
            if user_instruction and user_instruction != "Type question here & press Enter...":
                prompt = (
                    f"USER SPECIFIC INSTRUCTION: {user_instruction}\n\n"
                    "Please analyze the attached screen capture strictly following the user instruction above. "
                    "If it involves solving a problem, provide the direct answer/code first."
                )
                self.manual_entry.delete(0, 'end') 
            else:
                prompt = (
                    "Analyze this screen capture. "
                    "If it contains a coding problem, interview question, or technical task, "
                    "solve it immediately. Provide the direct answer or code first, followed by a very brief, concise explanation. "
                    "If it is just a diagram or generic image, explain what it is briefly."
                )
            
            self._start_streaming(prompt, image_bytes=img_bytes)
        except Exception as e:
            print(f"[Screenshot] Exception: {e}")
            self.on_status(f"❌ Screenshot failed: {e}")

    # ─── Super Stealth Toggle ─────────────────────────────────────────────────

    def toggle_super_stealth(self):
        """Toggle Super Stealth mode — enables SEB bypass."""
        if self._super_stealth_active:
            # ── DEACTIVATE ──
            self._super_stealth_active = False
            if self._stealth_engine:
                self._stealth_engine.deactivate()
                self._stealth_engine = None

            # Re-register keyboard library hotkeys (normal mode)
            self._register_keyboard_hotkeys()

            self.stealth_btn.config(
                text='🛡️ Super Stealth', bg='#1f2937', fg='#9ca3af'
            )
            self.on_status('🛡️ Super Stealth OFF — Normal mode')
        else:
            # ── ACTIVATE ──
            self._super_stealth_active = True

            # IMPORTANT: Remove keyboard library hotkeys first!
            # Otherwise both keyboard lib AND RegisterHotKey fire = double toggle
            self._unregister_keyboard_hotkeys()

            # Get the real HWND
            self.root.update()
            try:
                hwnd = int(self.root.wm_frame(), 16)
            except Exception:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())

            # Define hotkey callbacks (matching IDs in stealth.py)
            callbacks = {
                1: lambda: self.message_queue.put(('grab_screenshot', None)),  # Alt+S
                2: lambda: self.message_queue.put(('grab_clipboard', None)),   # Alt+T
                3: self.toggle_visibility,                                      # Alt+A
                4: self.panic_exit,                                             # Alt+X
                5: self.toggle_stealth_style,                                   # Alt+B
                6: self.quit,                                                   # Ctrl+Q
                7: lambda: self.scroll_answer(-3),                              # Alt+Up
                8: lambda: self.scroll_answer(3),                               # Alt+Down
                9: lambda: self.move_window(0, -50),                            # Ctrl+Up
                10: lambda: self.move_window(0, 50),                            # Ctrl+Down
                11: lambda: self.move_window(-50, 0),                           # Ctrl+Left
                12: lambda: self.move_window(50, 0),                            # Ctrl+Right
            }

            self._stealth_engine = StealthEngine(
                root=self.root, hwnd=hwnd, callbacks=callbacks
            )
            self._stealth_engine.activate()

            self.stealth_btn.config(
                text='🛡️ STEALTH ON', bg='#065f46', fg='#34d399'
            )
            self.on_status('🛡️ Super Stealth ON — Hidden from scanners!')

    def show_stealth_info(self):
        """Show info popup explaining Super Stealth mode."""
        info_text = (
            "🛡️ SUPER STEALTH MODE\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Click the '🛡️ Super Stealth' button to activate\n"
            "Secure Browser (SEB) bypass mode.\n\n"
            "WHAT IT DOES:\n"
            "• Forces window to stay ON TOP of SEB fullscreen\n"
            "• Uses low-level OS hotkeys that SEB can't block\n"
            "• Hides window from Alt+Tab and taskbar\n"
            "• Window never steals focus from exam browser\n"
            "• Invisible to screen capture and recording\n\n"
            "HOW TO USE:\n"
            "1. Open ShadowMind FIRST\n"
            "2. Click '🛡️ Super Stealth' to activate\n"
            "3. Then open the SEB/exam browser\n"
            "4. Use hotkeys normally (Alt+S, Alt+T, etc.)\n\n"
            "⚠️ SAFE: Closing ShadowMind removes ALL hooks.\n"
            "Nothing is permanently changed on your system.\n\n"
            "HOTKEYS (work even with SEB open):\n"
            "  Alt+S  → Screenshot & solve\n"
            "  Alt+T  → Grab selected text\n"
            "  Alt+A  → Show/Hide window\n"
            "  Alt+B  → Ultra transparent mode\n"
            "  Alt+X  → Panic exit (kills everything)\n"
            "  Alt+↑↓ → Scroll answer\n"
            "  Ctrl+↑↓←→ → Move window"
        )
        messagebox.showinfo("ShadowMind — Super Stealth Info", info_text)

    # ─── Window Controls ──────────────────────────────────────────────────────

    def toggle_visibility(self):
        if self.root.state() == 'withdrawn':
            # SHOW the window
            self.root.deiconify()
            if self._stealth_engine:
                self._stealth_engine.hidden = False
        else:
            # HIDE the window
            self.root.withdraw()
            if self._stealth_engine:
                self._stealth_engine.hidden = True

    def quit(self, event=None):
        import os
        # Clean up stealth engine before quitting
        try:
            if self._stealth_engine:
                self._stealth_engine.deactivate()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

    def run(self):
        try:
            # Auto-activate Super Stealth if launched with --stealth flag
            # (happens when desktop monitor respawns us on SEB's desktop)
            import sys
            if '--stealth' in sys.argv:
                self.root.after(1000, self.toggle_super_stealth)
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()


if __name__ == '__main__':
    app = GhostAssistant()
    app.run()
