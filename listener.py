import wave
import io
import threading
import numpy as np
import speech_recognition as sr
import keyboard

import sys

try:
    import soundcard as sc
    SOUNDCARD_AVAILABLE = True
except ImportError:
    SOUNDCARD_AVAILABLE = False
    print("[WARN] soundcard not installed. Only mic will be used.")

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    try:
        import pyaudiowpatch as pyaudio
        sys.modules['pyaudio'] = pyaudio
        PYAUDIO_AVAILABLE = True
    except ImportError:
        PYAUDIO_AVAILABLE = False


SAMPLE_RATE = 16000
CHUNK_SIZE  = 1024
CHANNELS    = 1


class VoiceListener:
    """
    Hold F9 → records BOTH mic + speaker simultaneously
    Release F9 → mixes, transcribes, fires on_question callback
    """

    def __init__(self, on_question, on_status=None, on_audio=None, on_f9_press=None, on_f9_release=None):
        self.on_question = on_question
        self.on_status   = on_status or (lambda s: None)
        self.on_audio    = on_audio
        self.on_f9_press = on_f9_press
        self.on_f9_release = on_f9_release
        self.recording   = False
        self._lock       = threading.Lock()

        self._mic_frames     = []
        self._speaker_frames = []
        self._mic_stream     = None

        # Pre-init PyAudio ONCE at startup (fast from here on)
        if PYAUDIO_AVAILABLE:
            import pyaudio
            self._pa     = pyaudio.PyAudio()
            self._FORMAT = pyaudio.paInt16
        else:
            self._pa = None

        # Pre-find the loopback device ONCE at startup
        self._loopback_device    = None
        self._loopback_dev_name  = None
        self._init_loopback()

    def _init_loopback(self):
        """Find and store the current default speaker loopback device."""
        if not SOUNDCARD_AVAILABLE:
            return
        try:
            spk_name = str(sc.default_speaker().name)
            if spk_name == self._loopback_dev_name:
                return  # Same device, no need to re-init
            self._loopback_device   = sc.get_microphone(id=spk_name, include_loopback=True)
            self._loopback_dev_name = spk_name
            print(f"[Loopback] Device: {spk_name}")
        except Exception as e:
            self._loopback_device   = None
            self._loopback_dev_name = None
            print(f"[Loopback] Not available: {e}")

    def start(self):
        keyboard.on_press_key('f9',   self._on_press)
        keyboard.on_release_key('f9', self._on_release)
        keyboard.wait()

    # ─── Key Events ───────────────────────────────────────────────────────────

    def _on_press(self, _):
        if self.on_f9_press and self.on_f9_press():
            return  # Handled externally
            
        with self._lock:
            if not self.recording:
                # Check if audio device changed (e.g. plugged in headphones)
                self._init_loopback()

                self.recording       = True
                self._mic_frames     = []
                self._speaker_frames = []

                spk_label = "Mic+Speaker" if self._loopback_device else "Mic only"
                self.on_status(f'🔴 Recording [{spk_label}]… release F9 when done')

                # Thread 1: Mic
                threading.Thread(target=self._record_mic, daemon=True).start()

                # Thread 2: Speaker loopback (only if device found)
                if self._loopback_device:
                    threading.Thread(target=self._record_speaker, daemon=True).start()

    def _on_release(self, _):
        if self.on_f9_release and self.on_f9_release():
            return  # Handled externally
            
        with self._lock:
            if self.recording:
                self.recording = False
                # Do NOT close the mic stream here. It causes a C-level segfault
                # if the recording thread is currently blocking on stream.read().
                # The recording thread will clean up its own stream.

        # Transcribe in background thread (no timer delay)
        threading.Thread(target=self._process_and_transcribe, daemon=True).start()

    # ─── Mic Recording ────────────────────────────────────────────────────────

    def _record_mic(self):
        try:
            mic = sc.default_microphone()
            with mic.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as recorder:
                while self.recording:
                    chunk = recorder.record(numframes=CHUNK_SIZE)
                    pcm = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                    self._mic_frames.append(pcm)
        except Exception as e:
            self.on_status(f"❌ Mic Error: {e}")
        finally:
            # Cleanly close the stream from the thread that opened it
            if self._mic_stream:
                try:
                    self._mic_stream.stop_stream()
                    self._mic_stream.close()
                except Exception:
                    pass
                self._mic_stream = None

    # ─── Speaker Loopback ─────────────────────────────────────────────────────

    def _record_speaker(self):
        try:
            with self._loopback_device.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
                while self.recording:
                    chunk = recorder.record(numframes=CHUNK_SIZE)
                    pcm   = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                    self._speaker_frames.append(pcm)
        except Exception as e:
            print(f"[Loopback record error] {e}")

    # ─── Mix + Transcribe ─────────────────────────────────────────────────────

    def _process_and_transcribe(self):
        if not self._mic_frames and not self._speaker_frames:
            self.on_status('❓ Nothing recorded — try again (Hold F9)')
            return

        self.on_status('⏳ Processing audio…')
        try:
            mic_np = np.frombuffer(b''.join(self._mic_frames), dtype=np.int16).astype(np.float32) if self._mic_frames else np.array([], dtype=np.float32)
            spk_np = np.frombuffer(b''.join(self._speaker_frames), dtype=np.int16).astype(np.float32) if self._speaker_frames else np.array([], dtype=np.float32)

            if len(mic_np) > 0 and len(spk_np) > 0:
                min_len = min(len(mic_np), len(spk_np))
                mixed   = ((mic_np[:min_len] * 0.6) + (spk_np[:min_len] * 0.8)) / 2.0
            elif len(mic_np) > 0:
                mixed = mic_np
            elif len(spk_np) > 0:
                mixed = spk_np
            else:
                mixed = np.zeros(16000, dtype=np.float32)

            mixed_int16 = np.clip(mixed, -32767, 32767).astype(np.int16)

            buf = io.BytesIO()
            wf  = wave.open(buf, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(mixed_int16.tobytes())
            wf.close()
            buf.seek(0)
            
            audio_bytes = buf.read()
            buf.seek(0)
            
            def fallback_stt():
                self.on_status('⏳ Native audio failed. Falling back to STT…')
                try:
                    recognizer = sr.Recognizer()
                    with sr.AudioFile(buf) as source:
                        audio_data = recognizer.record(source)
                    text = recognizer.recognize_google(audio_data)
                    if text.strip():
                        self.on_status('✅ Got it! Sending to AI…')
                        self.on_question(text.strip())
                    else:
                        self.on_status('❓ Could not understand — try again')
                except Exception as e:
                    self.on_status(f'❌ STT fallback error: {e}')

            if self.on_audio:
                self.on_status('✅ Sending native audio directly to AI…')
                self.on_audio(audio_bytes, fallback_stt)
            else:
                # If no on_audio callback, just use STT
                fallback_stt()

        except sr.UnknownValueError:
            self.on_status('❓ Could not understand — try again (Hold F9)')
        except sr.RequestError as e:
            self.on_status(f'❌ STT error: {e}')
        except Exception as e:
            self.on_status(f'❌ Error: {e}')
