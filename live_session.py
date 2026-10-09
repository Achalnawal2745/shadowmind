"""
Gemini Live WebSocket Session — Persistent audio streaming with text-only responses.

Opens a WebSocket connection to Gemini's Live API. Continuously streams
mic + speaker audio and receives text answers in real-time.
"""

import asyncio
import threading
import queue
import io
import wave
import numpy as np
import time

try:
    import soundcard as sc
    SOUNDCARD_AVAILABLE = True
except ImportError:
    SOUNDCARD_AVAILABLE = False

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    try:
        import pyaudiowpatch as pyaudio
        import sys
        sys.modules['pyaudio'] = pyaudio
        PYAUDIO_AVAILABLE = True
    except ImportError:
        PYAUDIO_AVAILABLE = False

from google import genai
from google.genai import types

SAMPLE_RATE = 16000
CHUNK_DURATION_MS = 250  # Send audio every 250ms
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)  # 4000 samples per chunk

LIVE_MODELS = [
    "gemini-3.8-live",
    "gemini-3.1-flash-live-preview",
    "gemini-2.5-flash-native-audio-latest",
    "gemini-2.5-flash-native-audio-preview-12-2025",
]

SYSTEM_PROMPT = """Your name is Shadow. You are a senior technical interviewer and assistant. 
- If specifically asked who you are or what your name is, identify yourself as Shadow.
- Otherwise, never mention your name.
- LANGUAGE RULE: Always detect the language of the user's message and reply in the EXACT same language. If they write in Hindi, reply in Hindi. If Hinglish, reply in Hinglish. If English, reply in English. Never switch languages unless the user does.
- When given an interview question:
- Give a direct, confident answer in first person.
- Use short bullet points for technical questions.
- ALWAYS wrap code snippets in standard markdown code blocks (```python, ```cpp, etc.).
- Keep explanation text under 120 words (code does not count towards this limit).
- Start answering immediately — no preamble.
"""


class LiveSession:
    """Manages a persistent WebSocket connection to Gemini Live API."""

    def __init__(self, api_keys, on_text, on_status):
        """
        Args:
            api_keys: List of Gemini API key strings.
            on_text: Callback(text_chunk: str) — called when AI sends text.
            on_status: Callback(status: str) — called to update UI status.
        """
        self.api_keys = [k for k in api_keys if k and k.strip()]
        self.on_text = on_text
        self.on_status = on_status

        self._active = False
        self._loop = None
        self._thread = None
        self._session = None
        self._audio_queue = asyncio.Queue()

        # Audio capture threads
        self._recording = False
        self._talking = False  # Push-to-talk: True when F9 held
        self._mic_thread = None
        self._speaker_thread = None

        # Loopback device
        self._loopback_device = None
        self._init_loopback()

    def _init_loopback(self):
        if not SOUNDCARD_AVAILABLE:
            return
        try:
            spk_name = str(sc.default_speaker().name)
            self._loopback_device = sc.get_microphone(id=spk_name, include_loopback=True)
            print(f"[Live] Loopback device: {spk_name}")
        except Exception as e:
            self._loopback_device = None
            print(f"[Live] Loopback not available: {e}")

    @property
    def is_active(self):
        return self._active

    def start(self):
        """Start the Live WebSocket session in a background thread."""
        if self._active:
            return
        self._active = True
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the Live session and all audio capture."""
        self._active = False
        self._recording = False
        self._talking = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def start_talking(self):
        """Called when F9 is pressed — start capturing and streaming audio."""
        if not self._active or not self._session or self._talking:
            return
        self._talking = True
        # Start audio capture threads if not already running
        if not self._recording:
            self._recording = True
            self._start_audio_capture()
        self.on_status('🔴 Live — Recording... (release F9 when done)')
        print("[Live] F9 pressed — streaming audio")

    def stop_talking(self):
        """Called when F9 is released — stop capturing, let Gemini respond."""
        if not self._talking:
            return
        self._talking = False
        self.on_status('⚡ Live — Thinking...')
        print("[Live] F9 released — waiting for response")
        # Notify the async loop that the turn is complete
        if self._loop and self._active:
            self._loop.call_soon_threadsafe(
                self._audio_queue.put_nowait,
                ('turn_complete', None)
            )

    def _run_event_loop(self):
        """Runs the asyncio event loop in a dedicated thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session_loop())
        except Exception as e:
            print(f"[Live] Event loop error: {e}")
            self.on_status(f"❌ Live session error: {e}")
        finally:
            self._active = False
            self._recording = False
            # Clean up any pending tasks
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            try:
                self._loop.close()
            except Exception:
                pass

    async def _session_loop(self):
        """Try each API key and model until one connects, then stream."""
        for api_key in self.api_keys:
            for model_id in LIVE_MODELS:
                if not self._active:
                    return
                try:
                    self.on_status(f"🔌 Connecting to {model_id.split('/')[-1]}...")
                    print(f"[Live] Trying {model_id} with key ...{api_key[-6:]}")

                    client = genai.Client(api_key=api_key)

                    config = types.LiveConnectConfig(
                        response_modalities=["AUDIO"],
                        system_instruction=SYSTEM_PROMPT,
                        output_audio_transcription=types.AudioTranscriptionConfig(),
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name="Aoede"
                                )
                            )
                        ),
                    )

                    async with client.aio.live.connect(
                        model=model_id,
                        config=config,
                    ) as session:
                        self._session = session
                        self.on_status(f"🟢 Live connected — Hold F9 to speak!")
                        print(f"[Live] ✅ Connected to {model_id}")

                        # DON'T auto-start audio — wait for F9 (push-to-talk)
                        # Run sender and receiver concurrently
                        await asyncio.gather(
                            self._send_audio_loop(session),
                            self._receive_text_loop(session),
                        )

                    # If we reach here, session ended cleanly
                    if not self._active:
                        return
                        
                except Exception as e:
                    print(f"[Live] {model_id} failed: {e}")
                    self._recording = False
                    continue

        # All models/keys exhausted
        self.on_status("❌ Live: All models failed")
        self._active = False

    def _start_audio_capture(self):
        """Start mic and speaker capture threads."""
        self._mic_thread = threading.Thread(target=self._capture_mic, daemon=True)
        self._mic_thread.start()

        if self._loopback_device:
            self._speaker_thread = threading.Thread(target=self._capture_speaker, daemon=True)
            self._speaker_thread.start()

    def _capture_mic(self):
        """Capture mic audio and put PCM chunks into the async queue."""
        try:
            mic = sc.default_microphone()
            print(f"[Live] Mic capture started: {SAMPLE_RATE}Hz")
            chunk_count = 0
            with mic.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
                while self._recording and self._active:
                    try:
                        chunk = recorder.record(numframes=CHUNK_SIZE)
                        pcm = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                        chunk_count += 1
                        if chunk_count % 40 == 0:
                            pass # print(f"[Live] Mic capture alive ({chunk_count} chunks)")
                        if self._loop and self._active:
                            self._loop.call_soon_threadsafe(
                                self._audio_queue.put_nowait,
                                ('mic', pcm)
                            )
                    except Exception:
                        break
        except Exception as e:
            print(f"[Live] Mic capture error: {e}")

    def _capture_speaker(self):
        """Capture speaker loopback and put PCM chunks into the async queue."""
        try:
            with self._loopback_device.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
                while self._recording and self._active:
                    chunk = recorder.record(numframes=CHUNK_SIZE)
                    pcm = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                    if self._loop and self._active:
                        self._loop.call_soon_threadsafe(
                            self._audio_queue.put_nowait,
                            ('spk', pcm)
                        )
        except Exception as e:
            print(f"[Live] Speaker capture error: {e}")

    async def _send_audio_loop(self, session):
        """Mix mic + speaker audio and send to the WebSocket."""
        mic_buf = bytearray()
        spk_buf = bytearray()

        # We'll send mixed audio every CHUNK_DURATION_MS
        send_interval = CHUNK_DURATION_MS / 1000.0
        last_send = time.time()

        while self._active and self._recording:
            try:
                turn_complete_requested = False
                
                # Drain all available audio from the queue
                while not self._audio_queue.empty():
                    try:
                        source, data = self._audio_queue.get_nowait()
                        if source == 'turn_complete':
                            turn_complete_requested = True
                        elif source == 'mic':
                            mic_buf.extend(data)
                        elif source == 'spk':
                            spk_buf.extend(data)
                    except asyncio.QueueEmpty:
                        break

                now = time.time()
                
                if turn_complete_requested:
                    await session.send(end_of_turn=True)
                    mic_buf.clear()
                    spk_buf.clear()
                    last_send = now
                    continue

                if now - last_send >= send_interval:
                    if self._talking and (len(mic_buf) > 0 or len(spk_buf) > 0):
                        # Mix mic and speaker
                        mic_np = np.frombuffer(bytes(mic_buf), dtype=np.int16).astype(np.float32) if len(mic_buf) > 0 else np.array([], dtype=np.float32)
                        spk_np = np.frombuffer(bytes(spk_buf), dtype=np.int16).astype(np.float32) if len(spk_buf) > 0 else np.array([], dtype=np.float32)

                        if len(mic_np) > 0 and len(spk_np) > 0:
                            min_len = min(len(mic_np), len(spk_np))
                            mixed = ((mic_np[:min_len] * 0.6) + (spk_np[:min_len] * 0.8)) / 2.0
                        elif len(mic_np) > 0:
                            mixed = mic_np
                        elif len(spk_np) > 0:
                            mixed = spk_np
                        else:
                            mixed = np.zeros(CHUNK_SIZE, dtype=np.float32)

                        mixed_int16 = np.clip(mixed, -32767, 32767).astype(np.int16)
                        pcm_bytes = mixed_int16.tobytes()

                        # Send raw PCM to Gemini Live
                        await session.send_realtime_input(
                            audio=types.Blob(data=pcm_bytes, mime_type=f"audio/pcm;rate={SAMPLE_RATE}")
                        )

                    # Always clear buffers so they don't grow infinitely when not talking
                    mic_buf.clear()
                    spk_buf.clear()
                    last_send = now

                await asyncio.sleep(0.05)  # 50ms poll

            except Exception as e:
                print(f"[Live] Send error: {e}")
                break

    async def _receive_text_loop(self, session):
        """Receive transcribed text responses from the Live API and forward to the UI."""
        try:
            while self._active:
                try:
                    # session.receive() is an async generator
                    async for response in session.receive():
                        if not self._active:
                            return

                        if response.server_content:
                            sc = response.server_content
                            
                            # Log what we're receiving for debugging
                            if getattr(sc, 'interrupted', False):
                                print("[Live] Gemini interrupted!")
                            
                            # 1. Check for standard text parts
                            if sc.model_turn and sc.model_turn.parts:
                                for part in sc.model_turn.parts:
                                    if part.text:
                                        self.on_text(part.text)
                                        print(f"[Live recv text] {part.text}")
                                        
                            # 2. Check for audio transcription text (since modality is AUDIO)
                            if getattr(sc, 'output_transcription', None):
                                t = sc.output_transcription
                                if t.text:
                                    self.on_text(t.text)
                                    print(f"[Live recv transcript] {t.text}")

                            # Check if turn is complete
                            if sc.turn_complete:
                                self.on_text("\n\n")
                                print("[Live] Gemini finished its turn.")

                except Exception as e:
                    if self._active:
                        print(f"[Live] Receive error: {e}")
                    break
        except Exception as e:
            print(f"[Live] Receive loop error: {e}")
