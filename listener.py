import pyaudio
import wave
import io
import threading
import speech_recognition as sr
import keyboard


class VoiceListener:
    """
    Hold F9 → records mic audio
    Release F9 → transcribes with Google STT → fires on_question callback
    """

    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    def __init__(self, on_question, on_status=None):
        self.on_question = on_question
        self.on_status = on_status or (lambda s: None)
        self.recording = False
        self.frames = []
        self._lock = threading.Lock()
        self.audio = pyaudio.PyAudio()
        self.stream = None

    def start(self):
        """Block forever, listening for F9 press/release."""
        keyboard.on_press_key('f9', self._on_press)
        keyboard.on_release_key('f9', self._on_release)
        keyboard.wait()  # runs in a daemon thread → safe

    # ─── Key Events ───────────────────────────────────────────────────────────

    def _on_press(self, _):
        with self._lock:
            if not self.recording:
                self.recording = True
                self.frames = []
                self.on_status('🔴  Recording…  (release F9 when done)')
                self.stream = self.audio.open(
                    format=self.FORMAT,
                    channels=self.CHANNELS,
                    rate=self.RATE,
                    input=True,
                    frames_per_buffer=self.CHUNK
                )
                t = threading.Thread(target=self._record_loop, daemon=True)
                t.start()

    def _on_release(self, _):
        with self._lock:
            if self.recording:
                self.recording = False
                if self.stream:
                    try:
                        self.stream.stop_stream()
                        self.stream.close()
                    except Exception:
                        pass
                    self.stream = None

                if self.frames:
                    self.on_status('⏳  Transcribing…')
                    captured = list(self.frames)
                    t = threading.Thread(target=self._transcribe,
                                        args=(captured,), daemon=True)
                    t.start()

    # ─── Recording Loop ───────────────────────────────────────────────────────

    def _record_loop(self):
        while self.recording:
            try:
                data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                self.frames.append(data)
            except Exception:
                break

    # ─── Transcription ────────────────────────────────────────────────────────

    def _transcribe(self, frames):
        buf = io.BytesIO()
        wf = wave.open(buf, 'wb')
        wf.setnchannels(self.CHANNELS)
        wf.setsampwidth(self.audio.get_sample_size(self.FORMAT))
        wf.setframerate(self.RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        buf.seek(0)

        recognizer = sr.Recognizer()
        try:
            with sr.AudioFile(buf) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language='hi-IN')
            if text.strip():
                self.on_status('✅  Got it! Sending to AI…')
                self.on_question(text.strip())
        except sr.UnknownValueError:
            self.on_status('❓  Could not understand – try again (Hold F9)')
        except sr.RequestError as e:
            self.on_status(f'❌  STT error: {e}')
        except Exception as e:
            self.on_status(f'❌  Error: {e}')
