import wave
import io
import threading
import numpy as np
import speech_recognition as sr
import keyboard

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
    PYAUDIO_AVAILABLE = False


SAMPLE_RATE = 16000
CHUNK_SIZE  = 1024
CHANNELS    = 1


class VoiceListener:
    """
    Hold F9 → records BOTH mic + speaker audio simultaneously
    Release F9 → mixes both, transcribes with Google STT → fires on_question callback
    """

    def __init__(self, on_question, on_status=None):
        self.on_question = on_question
        self.on_status   = on_status or (lambda s: None)
        self.recording   = False
        self._lock       = threading.Lock()

        self._mic_frames     = []
        self._speaker_frames = []

        # PyAudio for mic
        if PYAUDIO_AVAILABLE:
            import pyaudio
            self._pa     = pyaudio.PyAudio()
            self._FORMAT = pyaudio.paInt16
        self._mic_stream = None

    def start(self):
        """Block forever, listening for F9 press/release."""
        keyboard.on_press_key('f9',   self._on_press)
        keyboard.on_release_key('f9', self._on_release)
        keyboard.wait()

    # ─── Key Events ───────────────────────────────────────────────────────────

    def _on_press(self, _):
        with self._lock:
            if not self.recording:
                self.recording       = True
                self._mic_frames     = []
                self._speaker_frames = []
                self.on_status('🔴 Recording [Mic + Speaker]…  release F9 when done')

                # Thread 1: Mic recording
                threading.Thread(target=self._record_mic, daemon=True).start()

                # Thread 2: Speaker loopback (only if soundcard is available)
                if SOUNDCARD_AVAILABLE:
                    threading.Thread(target=self._record_speaker, daemon=True).start()

    def _on_release(self, _):
        with self._lock:
            if self.recording:
                self.recording = False

                # Close mic stream
                if self._mic_stream:
                    try:
                        self._mic_stream.stop_stream()
                        self._mic_stream.close()
                    except Exception:
                        pass
                    self._mic_stream = None

                # Small wait so both threads finish their last chunk
                threading.Timer(0.2, self._process_and_transcribe).start()

    # ─── Mic Recording ────────────────────────────────────────────────────────

    def _record_mic(self):
        try:
            import pyaudio
            self._mic_stream = self._pa.open(
                format=self._FORMAT,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE
            )
            while self.recording:
                try:
                    data = self._mic_stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    self._mic_frames.append(data)
                except Exception:
                    break
        except Exception as e:
            self.on_status(f"❌ Mic Error: {e}")

    # ─── Speaker (Loopback) Recording ─────────────────────────────────────────

    def _record_speaker(self):
        try:
            loopback = sc.get_microphone(
                id=str(sc.default_speaker().name),
                include_loopback=True
            )
            with loopback.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
                while self.recording:
                    chunk = recorder.record(numframes=CHUNK_SIZE)
                    # float32 → int16 PCM bytes
                    pcm = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                    self._speaker_frames.append(pcm)
        except Exception as e:
            # Silently fail — mic alone will still work
            print(f"[Speaker Loopback] {e}")

    # ─── Mix + Transcribe ─────────────────────────────────────────────────────

    def _process_and_transcribe(self):
        if not self._mic_frames:
            self.on_status('❓ Nothing recorded — try again (Hold F9)')
            return

        self.on_status('⏳ Mixing & Transcribing…')

        try:
            # Convert mic frames to numpy int16
            mic_np = np.frombuffer(b''.join(self._mic_frames), dtype=np.int16).astype(np.float32)

            if self._speaker_frames:
                # Convert speaker frames to numpy int16
                spk_np = np.frombuffer(b''.join(self._speaker_frames), dtype=np.int16).astype(np.float32)

                # Match lengths (trim longer one)
                min_len = min(len(mic_np), len(spk_np))
                mic_np  = mic_np[:min_len]
                spk_np  = spk_np[:min_len]

                # Mix: average both signals (prevents clipping)
                mixed = ((mic_np * 0.6) + (spk_np * 0.8)) / 2.0
            else:
                # Speaker capture failed, use mic only
                mixed = mic_np

            # Clip and convert back to int16
            mixed_int16 = np.clip(mixed, -32767, 32767).astype(np.int16)

            # Write to WAV buffer
            buf = io.BytesIO()
            wf  = wave.open(buf, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(mixed_int16.tobytes())
            wf.close()
            buf.seek(0)

            # Send to Google STT
            recognizer = sr.Recognizer()
            with sr.AudioFile(buf) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            if text.strip():
                self.on_status('✅ Got it! Sending to AI…')
                self.on_question(text.strip())
            else:
                self.on_status('❓ Could not understand — try again')

        except sr.UnknownValueError:
            self.on_status('❓ Could not understand — try again (Hold F9)')
        except sr.RequestError as e:
            self.on_status(f'❌ STT error: {e}')
        except Exception as e:
            self.on_status(f'❌ Error: {e}')
