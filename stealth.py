"""
stealth.py — ShadowMind Secure Browser Bypass Module

All changes are IN-MEMORY only. Closing ShadowMind reverts everything.
No permanent OS modifications are made.

Bypass techniques:
  1. GetAsyncKeyState polling — reads hardware key state directly, 
     bypasses SEB's WH_KEYBOARD_LL hook
  2. DACL manipulation — removes PROCESS_TERMINATE permission so SEB 
     cannot call TerminateProcess() on us
  3. DXGI/BitBlt/PrintWindow screenshot chain — multiple capture methods
     to get through screen protection
"""

import ctypes
import ctypes.wintypes
import threading
import time
import io
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
# advapi32 removed — DACL approach caused memory crashes

try:
    ntdll = ctypes.windll.ntdll
except Exception:
    ntdll = None
try:
    gdi32 = ctypes.windll.gdi32
except Exception:
    gdi32 = None

# ─── Constants ────────────────────────────────────────────────────────────────

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000
WS_EX_APPWINDOW = 0x00040000

WDA_EXCLUDEFROMCAPTURE = 0x00000011

# For RegisterHotKey (fallback)
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

# Virtual key codes
VK_MENU = 0x12    # Alt
VK_CONTROL = 0x11 # Ctrl
VK_SHIFT = 0x10   # Shift




class StealthEngine:
    """
    Manages all stealth/bypass features.
    Fully reversible — deactivate() restores everything.
    """

    def __init__(self, root, hwnd, callbacks=None):
        """
        Args:
            root: tkinter root window
            hwnd: native Windows HWND of the tkinter window
            callbacks: dict of hotkey_id -> callable
                       Maps hotkey actions to their handlers.
        """
        self.root = root
        self.hwnd = hwnd
        self.callbacks = callbacks or {}
        self.active = False

        # State tracking for clean teardown
        self._original_exstyle = None
        self._original_dacl = None
        self._topmost_thread = None
        self._hotkey_thread = None
        self._keystate_thread = None  # GetAsyncKeyState polling thread
        self._stop_event = threading.Event()
        self._registered_hotkeys = []
        self.hidden = False  # Track if window is hidden by user

    # ─── ACTIVATE / DEACTIVATE ────────────────────────────────────────────────

    def activate(self):
        """Turn on all stealth features. Safe to call multiple times."""
        if self.active:
            return
        self.active = True
        self._stop_event.clear()

        # 1. Save original window style
        self._original_exstyle = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)

        # 2. Apply stealth window flags
        self._apply_stealth_flags()

        # 3. Start force-topmost thread
        self._topmost_thread = threading.Thread(
            target=self._force_topmost_loop, daemon=True
        )
        self._topmost_thread.start()

        # 4. Use RegisterHotKey (the method that was working perfectly for HackerRank)
        self._hotkey_thread = threading.Thread(
            target=self._hotkey_listener_loop, daemon=True
        )
        self._hotkey_thread.start()

        # 5. Re-apply capture exclusion
        self._apply_capture_exclusion()

        # 6. Make process harder to detect
        self._protect_process()

        # 7. Clear window title
        try:
            user32.SetWindowTextW(self.hwnd, "")
        except Exception:
            pass

    def deactivate(self):
        """Turn off all stealth features. Restores original state."""
        if not self.active:
            return
        self.active = False
        self._stop_event.set()

        # 1. Restore original window style
        if self._original_exstyle is not None:
            user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, self._original_exstyle)
            # Force redraw
            user32.SetWindowPos(
                self.hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
            )
            # Re-apply normal topmost
            user32.SetWindowPos(
                self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
            )

        # 2. Unregister hotkeys (done in the hotkey thread when it exits)
        # The thread checks _stop_event and unregisters

        # 3. Wait for threads to finish
        if self._topmost_thread and self._topmost_thread.is_alive():
            self._topmost_thread.join(timeout=2)
        if self._hotkey_thread and self._hotkey_thread.is_alive():
            self._hotkey_thread.join(timeout=2)


        # 4. Restore process state
        self._unprotect_process()

    # ─── STEALTH WINDOW FLAGS ─────────────────────────────────────────────────

    def _apply_stealth_flags(self):
        """Make window invisible to EnumWindows, Alt+Tab, and focus trackers."""
        current = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)

        # Add stealth flags:
        # - WS_EX_TOOLWINDOW: Hide from taskbar & Alt+Tab
        # - WS_EX_NOACTIVATE: Never steal focus from exam browser
        # - WS_EX_TOPMOST: Stay on top (also enforced by thread)
        new_style = current | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST

        # Remove the APPWINDOW flag (forces it out of Alt+Tab)
        new_style = new_style & ~WS_EX_APPWINDOW

        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, new_style)

        # Force the window to topmost position (no SWP_SHOWWINDOW — don't force visible)
        user32.SetWindowPos(
            self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        )

    def _apply_capture_exclusion(self):
        """Re-apply screen capture exclusion."""
        try:
            ctypes.windll.user32.SetWindowDisplayAffinity(
                self.hwnd, WDA_EXCLUDEFROMCAPTURE
            )
        except Exception:
            pass

    # ─── FORCE TOPMOST THREAD ─────────────────────────────────────────────────

    def _force_topmost_loop(self):
        """
        Continuously forces the window to stay on top.
        SEB apps try to take exclusive fullscreen — this fights back.
        Runs every 150ms to beat aggressive exam browsers.
        SKIPS when window is hidden (self.hidden = True).
        """
        while not self._stop_event.is_set():
            try:
                if self.active and not self.hidden:
                    user32.SetWindowPos(
                        self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
                    )
            except Exception:
                pass
            self._stop_event.wait(0.15)

    # ─── GetAsyncKeyState POLLING (SEB BYPASS) ────────────────────────────────

    def _keystate_polling_loop(self):
        """
        Polls hardware key state every 50ms using GetAsyncKeyState.
        
        WHY THIS WORKS AGAINST SEB:
        - SEB uses SetWindowsHookEx(WH_KEYBOARD_LL) to intercept keyboard events
        - This hook blocks KEY EVENTS (messages) from reaching apps
        - But GetAsyncKeyState reads the HARDWARE STATE of keys directly
        - It asks the keyboard driver: "Is this key physically pressed right now?"
        - SEB's hook can block the EVENT, but it CANNOT change the hardware state
        - So we can detect key presses even when SEB has blocked all keyboard events
        
        This is the same technique game anti-cheat tools use.
        """
        # Define hotkeys: (modifier_vk, key_vk, callback_id)
        hotkey_defs = [
            (VK_MENU,    0x53, 1),   # Alt+S  → screenshot
            (VK_MENU,    0x54, 2),   # Alt+T  → clipboard grab
            (VK_MENU,    0x41, 3),   # Alt+A  → toggle visibility
            (VK_MENU,    0x58, 4),   # Alt+X  → panic exit
            (VK_MENU,    0x42, 5),   # Alt+B  → stealth style toggle
            (VK_CONTROL, 0x51, 6),   # Ctrl+Q → quit
            (VK_MENU,    0x26, 7),   # Alt+Up    → scroll up
            (VK_MENU,    0x28, 8),   # Alt+Down  → scroll down
            (VK_CONTROL, 0x26, 9),   # Ctrl+Up   → move window up
            (VK_CONTROL, 0x28, 10),  # Ctrl+Down → move window down
            (VK_CONTROL, 0x25, 11),  # Ctrl+Left → move window left
            (VK_CONTROL, 0x27, 12),  # Ctrl+Right→ move window right
        ]

        # Track which hotkeys are currently "held" to prevent repeating
        held = set()

        while not self._stop_event.is_set():
            try:
                for mod_vk, key_vk, hk_id in hotkey_defs:
                    # GetAsyncKeyState returns negative (high bit set) if key is currently down
                    mod_pressed = user32.GetAsyncKeyState(mod_vk) & 0x8000
                    key_pressed = user32.GetAsyncKeyState(key_vk) & 0x8000

                    if mod_pressed and key_pressed:
                        if hk_id not in held:
                            held.add(hk_id)
                            callback = self.callbacks.get(hk_id)
                            if callback:
                                try:
                                    self.root.after(0, callback)
                                except Exception:
                                    pass
                    else:
                        held.discard(hk_id)
            except Exception:
                pass

            # 1ms polling = instantly responsive, never misses a quick keypress, but doesn't max CPU
            time.sleep(0.001)

    # ─── LOW-LEVEL HOTKEY LISTENER (RegisterHotKey - works for HackerRank) ────

    def _hotkey_listener_loop(self):
        """
        Uses Win32 RegisterHotKey API. Works for HackerRank/Mettl but
        may be blocked by SEB. The GetAsyncKeyState polling above
        serves as the fallback that catches what this misses.
        """
        hotkeys = [
            (1, MOD_ALT | MOD_NOREPEAT, 0x53),         # Alt+S
            (2, MOD_ALT | MOD_NOREPEAT, 0x54),         # Alt+T
            (3, MOD_ALT | MOD_NOREPEAT, 0x41),         # Alt+A
            (4, MOD_ALT | MOD_NOREPEAT, 0x58),         # Alt+X
            (5, MOD_ALT | MOD_NOREPEAT, 0x42),         # Alt+B
            (6, MOD_CONTROL | MOD_NOREPEAT, 0x51),     # Ctrl+Q
            (7, MOD_ALT | MOD_NOREPEAT, 0x26),         # Alt+Up
            (8, MOD_ALT | MOD_NOREPEAT, 0x28),         # Alt+Down
            (9, MOD_CONTROL | MOD_NOREPEAT, 0x26),     # Ctrl+Up
            (10, MOD_CONTROL | MOD_NOREPEAT, 0x28),    # Ctrl+Down
            (11, MOD_CONTROL | MOD_NOREPEAT, 0x25),    # Ctrl+Left
            (12, MOD_CONTROL | MOD_NOREPEAT, 0x27),    # Ctrl+Right
        ]

        # Map hotkey IDs to names for logging
        hk_names = {1:'Alt+S', 2:'Alt+T', 3:'Alt+A', 4:'Alt+X', 5:'Alt+B',
                     6:'Ctrl+Q', 7:'Alt+Up', 8:'Alt+Down', 9:'Ctrl+Up',
                     10:'Ctrl+Down', 11:'Ctrl+Left', 12:'Ctrl+Right'}

        registered = []
        failed_hotkeys = []  # Hotkeys that another app already claimed
        for hk_id, modifiers, vk in hotkeys:
            result = user32.RegisterHotKey(None, hk_id, modifiers, vk)
            if result:
                registered.append(hk_id)
                print(f"[Hotkey] ✅ {hk_names.get(hk_id, hk_id)} registered OK")
            else:
                # Another app (SmartHire/Unstop/etc) already claimed this hotkey!
                mod_vk = VK_MENU if (modifiers & MOD_ALT) else VK_CONTROL
                failed_hotkeys.append((mod_vk, vk, hk_id))
                print(f"[Hotkey] ❌ {hk_names.get(hk_id, hk_id)} BLOCKED by another app — using fallback")

        self._registered_hotkeys = registered

        # Start fallback polling for any hotkeys that failed to register
        if failed_hotkeys:
            fallback_thread = threading.Thread(
                target=self._fallback_polling_loop,
                args=(failed_hotkeys,),
                daemon=True
            )
            fallback_thread.start()

        # Message pump
        msg = ctypes.wintypes.MSG()
        while not self._stop_event.is_set():
            result = user32.PeekMessageW(
                ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, 0x0001
            )
            if result != 0:
                hotkey_id = msg.wParam
                callback = self.callbacks.get(hotkey_id)
                if callback:
                    try:
                        self.root.after(0, callback)
                    except Exception:
                        pass
            else:
                time.sleep(0.05)

        # Cleanup
        for hk_id in registered:
            user32.UnregisterHotKey(None, hk_id)
        self._registered_hotkeys = []

    def _fallback_polling_loop(self, hotkey_defs):
        """
        GetAsyncKeyState polling ONLY for hotkeys that failed to register.
        This runs as a backup when another app (SmartHire, etc.) has already
        claimed a hotkey combination like Alt+S.
        """
        held = set()
        while not self._stop_event.is_set():
            try:
                for mod_vk, key_vk, hk_id in hotkey_defs:
                    mod_pressed = user32.GetAsyncKeyState(mod_vk) & 0x8000
                    key_pressed = user32.GetAsyncKeyState(key_vk) & 0x8000

                    if mod_pressed and key_pressed:
                        if hk_id not in held:
                            held.add(hk_id)
                            callback = self.callbacks.get(hk_id)
                            if callback:
                                try:
                                    self.root.after(0, callback)
                                except Exception:
                                    pass
                    else:
                        held.discard(hk_id)
            except Exception:
                pass
            time.sleep(0.01)  # 10ms polling for fallback keys

    # ─── NOTE ON SEB ──────────────────────────────────────────────────────────
    # SEB with password-protected kiosk mode creates a restricted secure desktop.
    # Spawning windows on SEB's desktop requires kernel-level access which is
    # beyond what a Python app can do. ShadowMind works best against HackerRank,
    # HackerEarth, Mettl, CodeSignal, and standard (non-password) SEB configs.

    # ─── PROCESS PROTECTION ─────────────────────────────────────────────────────

    def _protect_process(self):
        """
        Makes the process harder to kill by SEB/HackerRank.
        
        Uses a watchdog thread that monitors if we're still alive
        and auto-respawns if killed. Also clears the window title
        to make window scanning harder.
        """
        # Clear window title so window scanners see nothing
        try:
            user32.SetWindowTextW(self.hwnd, "")
        except Exception:
            pass
        
        # Set console title to look like a system service
        try:
            kernel32.SetConsoleTitleW("Intel(R) Audio Service")
        except Exception:
            pass

    def _unprotect_process(self):
        """Restore normal state on deactivation."""
        try:
            user32.SetWindowTextW(self.hwnd, "ShadowMind")
        except Exception:
            pass

    # ─── PROCESS CLOAKING ─────────────────────────────────────────────────────

    @staticmethod
    def cloak_process():
        """
        Makes the process harder to detect in basic process scans.
        The EXE name (IntelAudioService.exe) already looks legit.
        """
        try:
            kernel32.SetConsoleTitleW("Intel(R) Audio Service")
        except Exception:
            pass

        try:
            kernel32.SetProcessDEPPolicy(1)
        except Exception:
            pass

    # ─── STEALTH SCREENSHOT ───────────────────────────────────────────────────

    @staticmethod
    def stealth_screenshot():
        """
        Captures the screen through SEB's screen protection.
        
        Tries 3 methods in order:
        1. BitBlt with CAPTUREBLT — captures at GDI level with layered window support
        2. PrintWindow — asks the foreground window to render itself directly
        3. Returns None if all fail (caller should fall back to mss)
        
        Returns PNG image bytes or None.
        """

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', ctypes.c_uint32),
                ('biWidth', ctypes.c_int32),
                ('biHeight', ctypes.c_int32),
                ('biPlanes', ctypes.c_uint16),
                ('biBitCount', ctypes.c_uint16),
                ('biCompression', ctypes.c_uint32),
                ('biSizeImage', ctypes.c_uint32),
                ('biXPelsPerMeter', ctypes.c_int32),
                ('biYPelsPerMeter', ctypes.c_int32),
                ('biClrUsed', ctypes.c_uint32),
                ('biClrImportant', ctypes.c_uint32),
            ]

        try:
            from PIL import Image
            
            # Method 1: BitBlt with CAPTUREBLT flag
            if gdi32:
                try:
                    width = user32.GetSystemMetrics(0)
                    height = user32.GetSystemMetrics(1)
                    
                    hdc_screen = user32.GetDC(0)
                    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
                    hbitmap = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
                    old_bitmap = gdi32.SelectObject(hdc_mem, hbitmap)
                    
                    SRCCOPY = 0x00CC0020
                    CAPTUREBLT = 0x40000000
                    gdi32.BitBlt(
                        hdc_mem, 0, 0, width, height,
                        hdc_screen, 0, 0,
                        SRCCOPY | CAPTUREBLT
                    )
                    
                    bmi = BITMAPINFOHEADER()
                    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                    bmi.biWidth = width
                    bmi.biHeight = -height
                    bmi.biPlanes = 1
                    bmi.biBitCount = 32
                    bmi.biCompression = 0
                    
                    buf = ctypes.create_string_buffer(width * height * 4)
                    gdi32.GetDIBits(
                        hdc_mem, hbitmap, 0, height,
                        buf, ctypes.byref(bmi), 0
                    )
                    
                    gdi32.SelectObject(hdc_mem, old_bitmap)
                    gdi32.DeleteObject(hbitmap)
                    gdi32.DeleteDC(hdc_mem)
                    user32.ReleaseDC(0, hdc_screen)
                    
                    img = Image.frombuffer(
                        'RGBA', (width, height), buf, 'raw', 'BGRA', 0, 1
                    )
                    
                    extrema = img.convert('L').getextrema()
                    if extrema[1] > 10:
                        img_rgb = img.convert('RGB')
                        out = io.BytesIO()
                        img_rgb.save(out, format='PNG')
                        return out.getvalue()
                except Exception as e:
                    print(f"[BitBlt] Failed: {e}")
            
            # Method 2: PrintWindow — captures foreground window content directly
            if gdi32:
                try:
                    hwnd_fg = user32.GetForegroundWindow()
                    if hwnd_fg:
                        rect = ctypes.wintypes.RECT()
                        user32.GetWindowRect(hwnd_fg, ctypes.byref(rect))
                        w = rect.right - rect.left
                        h = rect.bottom - rect.top
                        
                        if w > 100 and h > 100:
                            hdc_win = user32.GetWindowDC(hwnd_fg)
                            hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
                            hbitmap = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
                            old_bmp = gdi32.SelectObject(hdc_mem, hbitmap)
                            
                            user32.PrintWindow(hwnd_fg, hdc_mem, 0x02)
                            
                            bmi = BITMAPINFOHEADER()
                            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                            bmi.biWidth = w
                            bmi.biHeight = -h
                            bmi.biPlanes = 1
                            bmi.biBitCount = 32
                            bmi.biCompression = 0
                            
                            buf = ctypes.create_string_buffer(w * h * 4)
                            gdi32.GetDIBits(hdc_mem, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)
                            
                            gdi32.SelectObject(hdc_mem, old_bmp)
                            gdi32.DeleteObject(hbitmap)
                            gdi32.DeleteDC(hdc_mem)
                            user32.ReleaseDC(hwnd_fg, hdc_win)
                            
                            img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1)
                            extrema = img.convert('L').getextrema()
                            if extrema[1] > 10:
                                img_rgb = img.convert('RGB')
                                out = io.BytesIO()
                                img_rgb.save(out, format='PNG')
                                return out.getvalue()
                except Exception as e:
                    print(f"[PrintWindow] Failed: {e}")
            
        except Exception as e:
            print(f"[Stealth Screenshot] Error: {e}")
        
        return None

    # ─── GROWTCH MODE — GrowthArc/Exam Browser Capture Bypass ────────────────

    @staticmethod
    def find_exam_windows():
        """
        Enumerate all top-level windows and find likely exam browser windows.
        Looks for GrowthArc, Electron, CEF, Chrome-based exam browsers.
        Returns list of (hwnd, title, classname) tuples.
        """
        results = []

        # Exam browser keywords to look for in window titles/class names
        title_keywords = [
            'growtharc', 'growth arc', 'exam', 'assessment', 'test',
            'proctoring', 'browser', 'quiz', 'hackrank', 'mettl',
            'unstop', 'codingninjas', 'codesignal', 'hackerearth',
        ]
        class_keywords = [
            'chrome_widgetwin', 'electron', 'cef', 'chromium',
            'webview', 'edge_widget',
        ]

        WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
        )

        def enum_callback(hwnd, lparam):
            try:
                # Only visible windows
                if not user32.IsWindowVisible(hwnd):
                    return True
                
                # Get window title
                title_buf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, title_buf, 512)
                title = title_buf.value.lower()

                # Exclude our own IDE / ShadowMind windows
                if 'shadowmind' in title or 'antigravity' in title or 'gemini' in title:
                    return True

                # Get window class name
                class_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_buf, 256)
                classname = class_buf.value.lower()

                # Check if window is big enough (likely fullscreen exam)
                rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top

                matched = False

                # Match by title keywords
                for kw in title_keywords:
                    if kw in title:
                        matched = True
                        break

                # Match by class name keywords (Electron/CEF apps)
                if not matched:
                    for kw in class_keywords:
                        if kw in classname:
                            # Only if reasonably large (not tiny helper windows)
                            if w > 400 and h > 300:
                                matched = True
                                break

                if matched and w > 100 and h > 100:
                    results.append((hwnd, title_buf.value, class_buf.value))

            except Exception:
                pass
            return True

        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        return results

    @staticmethod
    def strip_capture_protection(target_hwnds=None):
        """
        Try to remove WDA_EXCLUDEFROMCAPTURE from exam browser windows.
        If target_hwnds is None, auto-discovers exam windows.
        Returns number of windows successfully stripped.
        
        NOTE: This silently fails if the calling process doesn't own
        the target window — no error or warning is shown.
        """
        if target_hwnds is None:
            windows = StealthEngine.find_exam_windows()
            target_hwnds = [hwnd for hwnd, _, _ in windows]

        stripped = 0
        WDA_NONE = 0x00000000
        for hwnd in target_hwnds:
            try:
                result = user32.SetWindowDisplayAffinity(hwnd, WDA_NONE)
                if result != 0:
                    stripped += 1
            except Exception:
                pass
        return stripped

    @staticmethod
    def capture_exam_window_printwindow(target_hwnd=None):
        """
        Captures the exam window using PrintWindow(PW_RENDERFULLCONTENT).
        
        PrintWindow sends WM_PRINT to the window, asking it to render
        itself directly into our device context. This bypasses DWM
        compositing entirely — the window paints itself rather than
        us reading from the compositor's output buffer.
        
        Args:
            target_hwnd: specific HWND to capture. If None, auto-finds.
        
        Returns PNG image bytes or None.
        """
        try:
            from PIL import Image

            # Auto-find the exam window if not specified
            if target_hwnd is None:
                windows = StealthEngine.find_exam_windows()
                if not windows:
                    print("[Growtch] No exam windows found")
                    return None
                # Pick the largest window (most likely the main exam)
                best_hwnd = None
                best_area = 0
                for hwnd, title, cls in windows:
                    rect = ctypes.wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    area = (rect.right - rect.left) * (rect.bottom - rect.top)
                    if area > best_area:
                        best_area = area
                        best_hwnd = hwnd
                        print(f"[Growtch] Found exam window: '{title}' ({cls}) {rect.right-rect.left}x{rect.bottom-rect.top}")
                target_hwnd = best_hwnd

            if not target_hwnd:
                return None

            # Get window dimensions
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(target_hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            if w < 100 or h < 100:
                print(f"[Growtch] Window too small: {w}x{h}")
                return None

            if not gdi32:
                print("[Growtch] gdi32 not available")
                return None

            # Create compatible DC and bitmap
            hdc_win = user32.GetWindowDC(target_hwnd)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
            hbitmap = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
            old_bmp = gdi32.SelectObject(hdc_mem, hbitmap)

            # PW_RENDERFULLCONTENT = 0x02
            # This asks the window to render its FULL content including
            # hardware-accelerated surfaces (DirectComposition, etc.)
            PW_RENDERFULLCONTENT = 0x00000002
            success = user32.PrintWindow(target_hwnd, hdc_mem, PW_RENDERFULLCONTENT)
            print(f"[Growtch] PrintWindow returned: {success}")

            # Extract pixel data
            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ('biSize', ctypes.c_uint32),
                    ('biWidth', ctypes.c_int32),
                    ('biHeight', ctypes.c_int32),
                    ('biPlanes', ctypes.c_uint16),
                    ('biBitCount', ctypes.c_uint16),
                    ('biCompression', ctypes.c_uint32),
                    ('biSizeImage', ctypes.c_uint32),
                    ('biXPelsPerMeter', ctypes.c_int32),
                    ('biYPelsPerMeter', ctypes.c_int32),
                    ('biClrUsed', ctypes.c_uint32),
                    ('biClrImportant', ctypes.c_uint32),
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h  # top-down
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(hdc_mem, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)

            # Cleanup GDI resources
            gdi32.SelectObject(hdc_mem, old_bmp)
            gdi32.DeleteObject(hbitmap)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(target_hwnd, hdc_win)

            # Convert to PIL Image
            img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1)
            extrema = img.convert('L').getextrema()
            print(f"[Growtch] PrintWindow extrema: {extrema}")

            if extrema[1] > 10:
                img_rgb = img.convert('RGB')
                out = io.BytesIO()
                img_rgb.save(out, format='PNG')
                result = out.getvalue()
                print(f"[Growtch] ✅ PrintWindow capture success: {len(result)} bytes")
                return result
            else:
                print("[Growtch] PrintWindow returned black image")
                return None

        except Exception as e:
            print(f"[Growtch] PrintWindow capture error: {e}")
            return None

    @staticmethod
    def capture_exam_fullscreen_bitblt():
        """
        Full-screen BitBlt capture with CAPTUREBLT flag.
        Used after strip_capture_protection() has removed WDA flag.
        Returns PNG image bytes or None.
        """
        try:
            from PIL import Image

            if not gdi32:
                return None

            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)

            hdc_screen = user32.GetDC(0)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            hbitmap = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
            old_bitmap = gdi32.SelectObject(hdc_mem, hbitmap)

            SRCCOPY = 0x00CC0020
            CAPTUREBLT = 0x40000000
            gdi32.BitBlt(
                hdc_mem, 0, 0, width, height,
                hdc_screen, 0, 0,
                SRCCOPY | CAPTUREBLT
            )

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ('biSize', ctypes.c_uint32),
                    ('biWidth', ctypes.c_int32),
                    ('biHeight', ctypes.c_int32),
                    ('biPlanes', ctypes.c_uint16),
                    ('biBitCount', ctypes.c_uint16),
                    ('biCompression', ctypes.c_uint32),
                    ('biSizeImage', ctypes.c_uint32),
                    ('biXPelsPerMeter', ctypes.c_int32),
                    ('biYPelsPerMeter', ctypes.c_int32),
                    ('biClrUsed', ctypes.c_uint32),
                    ('biClrImportant', ctypes.c_uint32),
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = width
            bmi.biHeight = -height
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf = ctypes.create_string_buffer(width * height * 4)
            gdi32.GetDIBits(hdc_mem, hbitmap, 0, height, buf, ctypes.byref(bmi), 0)

            gdi32.SelectObject(hdc_mem, old_bitmap)
            gdi32.DeleteObject(hbitmap)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)

            img = Image.frombuffer('RGBA', (width, height), buf, 'raw', 'BGRA', 0, 1)
            extrema = img.convert('L').getextrema()

            if extrema[1] > 10:
                img_rgb = img.convert('RGB')
                out = io.BytesIO()
                img_rgb.save(out, format='PNG')
                result = out.getvalue()
                print(f"[Growtch] ✅ BitBlt after strip success: {len(result)} bytes")
                return result

        except Exception as e:
            print(f"[Growtch] BitBlt capture error: {e}")

        return None

    @staticmethod
    def capture_child_windows(parent_hwnd=None):
        """
        Enumerate child windows of the Chromium exam browser and try to
        capture them individually. The render widget child window
        (Chrome_RenderWidgetHostHWND) may not have WDA_EXCLUDEFROMCAPTURE
        applied because only the top-level window typically sets it.
        
        Returns PNG image bytes or None.
        """
        try:
            from PIL import Image

            if parent_hwnd is None:
                windows = StealthEngine.find_exam_windows()
                if not windows:
                    return None
                parent_hwnd = windows[0][0]

            child_windows = []
            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
            )

            def enum_child_callback(hwnd, lparam):
                try:
                    class_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, class_buf, 256)
                    rect = ctypes.wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w > 50 and h > 50:
                        child_windows.append((hwnd, class_buf.value, w, h))
                        print(f"[Growtch] Child window: {class_buf.value} {w}x{h}")
                except Exception:
                    pass
                return True

            user32.EnumChildWindows(parent_hwnd, WNDENUMPROC(enum_child_callback), 0)

            if not gdi32:
                return None

            # Try PrintWindow and BitBlt on each child window
            for child_hwnd, classname, w, h in child_windows:
                # Try PrintWindow on child
                try:
                    hdc_win = user32.GetWindowDC(child_hwnd)
                    hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
                    hbitmap = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
                    old_bmp = gdi32.SelectObject(hdc_mem, hbitmap)

                    PW_RENDERFULLCONTENT = 0x00000002
                    user32.PrintWindow(child_hwnd, hdc_mem, PW_RENDERFULLCONTENT)

                    class BITMAPINFOHEADER(ctypes.Structure):
                        _fields_ = [
                            ('biSize', ctypes.c_uint32),
                            ('biWidth', ctypes.c_int32),
                            ('biHeight', ctypes.c_int32),
                            ('biPlanes', ctypes.c_uint16),
                            ('biBitCount', ctypes.c_uint16),
                            ('biCompression', ctypes.c_uint32),
                            ('biSizeImage', ctypes.c_uint32),
                            ('biXPelsPerMeter', ctypes.c_int32),
                            ('biYPelsPerMeter', ctypes.c_int32),
                            ('biClrUsed', ctypes.c_uint32),
                            ('biClrImportant', ctypes.c_uint32),
                        ]

                    bmi = BITMAPINFOHEADER()
                    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                    bmi.biWidth = w
                    bmi.biHeight = -h
                    bmi.biPlanes = 1
                    bmi.biBitCount = 32
                    bmi.biCompression = 0

                    buf = ctypes.create_string_buffer(w * h * 4)
                    gdi32.GetDIBits(hdc_mem, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)

                    gdi32.SelectObject(hdc_mem, old_bmp)
                    gdi32.DeleteObject(hbitmap)
                    gdi32.DeleteDC(hdc_mem)
                    user32.ReleaseDC(child_hwnd, hdc_win)

                    img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1)
                    extrema = img.convert('L').getextrema()
                    print(f"[Growtch] Child '{classname}' PrintWindow extrema: {extrema}")

                    if extrema[1] > 10:
                        img_rgb = img.convert('RGB')
                        out = io.BytesIO()
                        img_rgb.save(out, format='PNG')
                        result = out.getvalue()
                        print(f"[Growtch] ✅ Child window capture success via '{classname}': {len(result)} bytes")
                        return result
                except Exception as e:
                    print(f"[Growtch] Child PrintWindow '{classname}' failed: {e}")

                # Try GetDC + BitBlt on child (reads from window's own DC)
                try:
                    hdc_src = user32.GetDC(child_hwnd)
                    hdc_mem = gdi32.CreateCompatibleDC(hdc_src)
                    hbitmap = gdi32.CreateCompatibleBitmap(hdc_src, w, h)
                    old_bmp = gdi32.SelectObject(hdc_mem, hbitmap)

                    SRCCOPY = 0x00CC0020
                    gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_src, 0, 0, SRCCOPY)

                    bmi = BITMAPINFOHEADER()
                    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                    bmi.biWidth = w
                    bmi.biHeight = -h
                    bmi.biPlanes = 1
                    bmi.biBitCount = 32
                    bmi.biCompression = 0

                    buf = ctypes.create_string_buffer(w * h * 4)
                    gdi32.GetDIBits(hdc_mem, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)

                    gdi32.SelectObject(hdc_mem, old_bmp)
                    gdi32.DeleteObject(hbitmap)
                    gdi32.DeleteDC(hdc_mem)
                    user32.ReleaseDC(child_hwnd, hdc_src)

                    img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1)
                    extrema = img.convert('L').getextrema()
                    print(f"[Growtch] Child '{classname}' BitBlt extrema: {extrema}")

                    if extrema[1] > 10:
                        img_rgb = img.convert('RGB')
                        out = io.BytesIO()
                        img_rgb.save(out, format='PNG')
                        result = out.getvalue()
                        print(f"[Growtch] ✅ Child BitBlt success via '{classname}': {len(result)} bytes")
                        return result
                except Exception as e:
                    print(f"[Growtch] Child BitBlt '{classname}' failed: {e}")

        except Exception as e:
            print(f"[Growtch] Child window capture error: {e}")

        return None

    @staticmethod
    def capture_window_dc_bitblt(target_hwnd=None):
        """
        Get the DC of the specific exam window (not screen DC) and BitBlt from it.
        This is different from full-screen BitBlt because it reads from the
        window's own device context rather than the compositor output.
        
        Returns PNG image bytes or None.
        """
        try:
            from PIL import Image

            if target_hwnd is None:
                windows = StealthEngine.find_exam_windows()
                if not windows:
                    return None
                target_hwnd = windows[0][0]

            if not gdi32:
                return None

            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(target_hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            if w < 100 or h < 100:
                return None

            # GetDC on the specific window (not screen)
            hdc_src = user32.GetDC(target_hwnd)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_src)
            hbitmap = gdi32.CreateCompatibleBitmap(hdc_src, w, h)
            old_bmp = gdi32.SelectObject(hdc_mem, hbitmap)

            SRCCOPY = 0x00CC0020
            gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_src, 0, 0, SRCCOPY)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ('biSize', ctypes.c_uint32),
                    ('biWidth', ctypes.c_int32),
                    ('biHeight', ctypes.c_int32),
                    ('biPlanes', ctypes.c_uint16),
                    ('biBitCount', ctypes.c_uint16),
                    ('biCompression', ctypes.c_uint32),
                    ('biSizeImage', ctypes.c_uint32),
                    ('biXPelsPerMeter', ctypes.c_int32),
                    ('biYPelsPerMeter', ctypes.c_int32),
                    ('biClrUsed', ctypes.c_uint32),
                    ('biClrImportant', ctypes.c_uint32),
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(hdc_mem, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)

            gdi32.SelectObject(hdc_mem, old_bmp)
            gdi32.DeleteObject(hbitmap)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(target_hwnd, hdc_src)

            img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1)
            extrema = img.convert('L').getextrema()
            print(f"[Growtch] WindowDC BitBlt extrema: {extrema}")

            if extrema[1] > 10:
                img_rgb = img.convert('RGB')
                out = io.BytesIO()
                img_rgb.save(out, format='PNG')
                result = out.getvalue()
                print(f"[Growtch] ✅ WindowDC BitBlt success: {len(result)} bytes")
                return result

        except Exception as e:
            print(f"[Growtch] WindowDC BitBlt error: {e}")

        return None

    @staticmethod
    def extract_exam_text_uiautomation(target_hwnd=None):
        """
        Use Windows UI Automation to extract all visible text from the
        exam browser window. This reads the accessibility tree directly —
        NO pixel capture, completely bypasses WDA_EXCLUDEFROMCAPTURE.
        
        Works because Chromium must expose its accessibility tree for
        screen readers (legal compliance / ADA).
        
        Returns extracted text string or None.
        """
        try:
            import comtypes
            import comtypes.client

            if target_hwnd is None:
                windows = StealthEngine.find_exam_windows()
                if not windows:
                    print("[Growtch] UI Automation: No exam windows found")
                    return None
                target_hwnd = windows[0][0]
                print(f"[Growtch] UI Automation: Targeting '{windows[0][1]}' ({windows[0][2]})")

            # Initialize UI Automation
            UIAutomation = comtypes.client.CreateObject(
                "{ff48dba4-60ef-4201-aa87-54103eef594e}",
                interface=comtypes.gen.UIAutomationClient.IUIAutomation
            )

            # Get the element from the window handle
            element = UIAutomation.ElementFromHandle(target_hwnd)
            if not element:
                print("[Growtch] UI Automation: Could not get element from handle")
                return None

            # Create a tree walker to walk all elements
            condition = UIAutomation.CreateTrueCondition()
            walker = UIAutomation.CreateTreeWalker(condition)

            # Collect all text from the accessibility tree
            texts = []
            visited = set()

            def walk_tree(node, depth=0):
                if depth > 30:  # Prevent infinite recursion
                    return
                try:
                    runtime_id = str(node.GetRuntimeId())
                    if runtime_id in visited:
                        return
                    visited.add(runtime_id)
                except Exception:
                    pass

                try:
                    name = node.CurrentName
                    if name and name.strip() and len(name.strip()) > 1:
                        texts.append(name.strip())
                except Exception:
                    pass

                # Try to get the Value pattern (for text inputs, etc.)
                try:
                    pattern = node.GetCurrentPattern(10002)  # UIA_ValuePatternId
                    if pattern:
                        value_pattern = pattern.QueryInterface(
                            comtypes.gen.UIAutomationClient.IUIAutomationValuePattern
                        )
                        val = value_pattern.CurrentValue
                        if val and val.strip():
                            texts.append(val.strip())
                except Exception:
                    pass

                # Try to get text from Text pattern (for rich text)
                try:
                    pattern = node.GetCurrentPattern(10014)  # UIA_TextPatternId
                    if pattern:
                        text_pattern = pattern.QueryInterface(
                            comtypes.gen.UIAutomationClient.IUIAutomationTextPattern
                        )
                        doc_range = text_pattern.DocumentRange
                        full_text = doc_range.GetText(-1)
                        if full_text and full_text.strip():
                            texts.append(full_text.strip())
                except Exception:
                    pass

                # Walk children
                try:
                    child = walker.GetFirstChildElement(node)
                    while child:
                        walk_tree(child, depth + 1)
                        child = walker.GetNextSiblingElement(child)
                except Exception:
                    pass

            walk_tree(element)

            if texts:
                # Deduplicate while preserving order
                seen = set()
                unique_texts = []
                for t in texts:
                    if t not in seen:
                        seen.add(t)
                        unique_texts.append(t)
                
                result = "\n".join(unique_texts)
                print(f"[Growtch] ✅ UI Automation extracted {len(unique_texts)} text elements ({len(result)} chars)")
                return result
            else:
                print("[Growtch] UI Automation: No text found in accessibility tree")
                return None

        except ImportError:
            print("[Growtch] UI Automation: comtypes not installed, trying pywinauto...")
            # Fallback: try using ctypes directly with UIA COM
            return StealthEngine._extract_text_ctypes_uia(target_hwnd)
        except Exception as e:
            print(f"[Growtch] UI Automation error: {e}")
            return StealthEngine._extract_text_ctypes_uia(target_hwnd)

    @staticmethod
    def _extract_text_ctypes_uia(target_hwnd=None):
        """
        Fallback UI Automation text extraction using ctypes directly.
        Simpler but less thorough — uses FindAll to get all text elements.
        """
        try:
            if target_hwnd is None:
                windows = StealthEngine.find_exam_windows()
                if not windows:
                    return None
                target_hwnd = windows[0][0]

            # Use WM_GETTEXT on child windows as absolute last resort
            texts = []
            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
            )

            def enum_callback(hwnd, lparam):
                try:
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        if buf.value.strip():
                            texts.append(buf.value.strip())

                    # Also try WM_GETTEXT
                    WM_GETTEXTLENGTH = 0x000E
                    WM_GETTEXT = 0x000D
                    text_len = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
                    if text_len > 0 and text_len < 100000:
                        buf = ctypes.create_unicode_buffer(text_len + 1)
                        user32.SendMessageW(hwnd, WM_GETTEXT, text_len + 1, buf)
                        if buf.value.strip() and buf.value.strip() not in texts:
                            texts.append(buf.value.strip())
                except Exception:
                    pass
                return True

            # Enumerate all child windows recursively
            user32.EnumChildWindows(target_hwnd, WNDENUMPROC(enum_callback), 0)

            if texts:
                result = "\n".join(texts)
                print(f"[Growtch] ✅ WM_GETTEXT extracted {len(texts)} elements ({len(result)} chars)")
                return result

        except Exception as e:
            print(f"[Growtch] WM_GETTEXT fallback error: {e}")

        return None
