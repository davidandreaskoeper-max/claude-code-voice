"""
Voice Input for Claude Code — Push-to-Talk with faster-whisper

Usage:
  1. F9 HOLD    → Recording
  2. F9 RELEASE → Text is pasted into terminal (without Enter) — review it!
  3. F9 TAP     → Enter = send (< 0.5s)
  4. F9 HOLD    → New recording (instead of confirm)

Everything with one key, no need to reach for the keyboard.

Start:  python voice_input.py
Stop:   Ctrl+C
"""

import numpy as np
import sounddevice as sd
import pyautogui
import pyperclip
import time
import io
import wave
import sys
import threading
from faster_whisper import WhisperModel
from pynput import keyboard

# -- Configuration ---------------------------------------------------------
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = 'int16'
CHUNK_SIZE = 1280                # ~80ms at 16kHz

# ⚠️ CHANGE THIS to your microphone device number!
# Run: python -c "import sounddevice; print(sounddevice.query_devices())"
AUDIO_DEVICE = None              # None = system default, or set to device number

WHISPER_MODEL = "small"          # tiny/base/small/medium/large-v3
WHISPER_DEVICE = "cpu"           # "cuda" if NVIDIA GPU available
WHISPER_COMPUTE = "int8"         # "float16" for GPU
WHISPER_LANGUAGE = "de"          # Language code (de/en/fr/es/...)

PTT_KEY = keyboard.Key.f9       # Push-to-Talk key (change as needed)

ENABLE_BEEP = True               # Audio feedback on start/stop
RING_BUFFER_SECONDS = 1          # Pre-roll buffer (captures audio BEFORE keypress)

# Sound feedback
BEEP_START_FREQ = 800
BEEP_START_DUR = 0.1
BEEP_STOP_FREQ = 1000
BEEP_STOP_DUR = 0.08


class PreInitMicrophone:
    """Microphone stream that opens at startup and stays open permanently.

    Keeps a ring buffer with the last N seconds of audio,
    so nothing is lost when F9 is pressed.
    """

    def __init__(self, device, sample_rate, channels, chunk_size, ring_seconds):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size

        # Ring buffer: captures the last N seconds
        ring_samples = int(sample_rate * ring_seconds)
        self.ring_buffer = np.zeros(ring_samples, dtype=np.int16)
        self.ring_pos = 0

        # Recording state
        self.is_recording = False
        self.recorded_frames = []
        self._lock = threading.Lock()

        # Open stream and start IMMEDIATELY (pre-init)
        self.stream = sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype=DTYPE,
            blocksize=chunk_size,
            device=device,
            callback=self._audio_callback
        )
        self.stream.start()

    def _audio_callback(self, indata, frames, time_info, status):
        """Called for EVERY audio chunk (runs permanently)."""
        audio = indata.flatten().astype(np.int16)

        # Always fill ring buffer (even when not recording)
        n = len(audio)
        end = self.ring_pos + n
        if end <= len(self.ring_buffer):
            self.ring_buffer[self.ring_pos:end] = audio
        else:
            first = len(self.ring_buffer) - self.ring_pos
            self.ring_buffer[self.ring_pos:] = audio[:first]
            self.ring_buffer[:n - first] = audio[first:]
        self.ring_pos = end % len(self.ring_buffer)

        # If recording active: collect frames
        with self._lock:
            if self.is_recording:
                self.recorded_frames.append(audio.tobytes())

    def start_recording(self):
        """Start recording — instant, no delay."""
        with self._lock:
            # Pre-roll: insert ring buffer as first frames
            ring_ordered = np.concatenate([
                self.ring_buffer[self.ring_pos:],
                self.ring_buffer[:self.ring_pos]
            ])
            self.recorded_frames = [ring_ordered.tobytes()]
            self.is_recording = True

    def stop_recording(self):
        """Stop recording, return audio."""
        with self._lock:
            self.is_recording = False
            frames = self.recorded_frames
            self.recorded_frames = []
        return frames

    def close(self):
        """Close stream."""
        self.stream.stop()
        self.stream.close()


class VoiceInput:
    """Main class: Push-to-Talk with Pre-Init Stream + faster-whisper."""

    def __init__(self):
        self.mic = None
        self.model = None
        self.is_ptt_held = False
        self.running = True
        self.last_injection = 0
        self.DEBOUNCE_SECONDS = 2.0
        # F9 debounce against Logitech double-signal
        self.f9_already_processed = False
        # Confirm tap: after insertion, system waits for short F9 tap
        self.awaiting_confirm = False
        self.f9_press_time = 0
        self.TAP_THRESHOLD = 0.5  # seconds: shorter = tap (confirm), longer = new recording

    def init(self):
        """Initialize everything at startup (pre-init)."""
        print("\n  ========================================")
        print("  Claude Code Voice Input v3.2")
        print("  Push-to-Talk + Pre-Init Stream")
        print("  ========================================")

        # 1. Load faster-whisper model
        print(f"  Loading Whisper model '{WHISPER_MODEL}'...")
        t0 = time.time()
        self.model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE
        )
        print(f"  Whisper loaded in {time.time() - t0:.1f}s")

        # 2. Open microphone stream (PRE-INIT — stays open permanently)
        device_str = AUDIO_DEVICE if AUDIO_DEVICE is not None else "default"
        print(f"  Opening microphone (Device {device_str})...")
        self.mic = PreInitMicrophone(
            device=AUDIO_DEVICE,
            sample_rate=SAMPLE_RATE,
            channels=CHANNELS,
            chunk_size=CHUNK_SIZE,
            ring_seconds=RING_BUFFER_SECONDS
        )
        print("  Microphone stream running (pre-init active)")

        print(f"  Hold {PTT_KEY}    = record")
        print(f"  Release {PTT_KEY} = paste text (review!)")
        print(f"  Tap {PTT_KEY}     = send (Enter)")
        print(f"  Ring buffer: {RING_BUFFER_SECONDS}s pre-roll")
        print(f"  Language:    {WHISPER_LANGUAGE}")
        print("  Quit:        Ctrl+C")
        print("  ========================================")
        print(f"\n  Ready! Hold {PTT_KEY} to speak.\n")

    def beep(self, frequency, duration):
        """Short beep tone as feedback."""
        if not ENABLE_BEEP:
            return
        try:
            t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
            tone = np.sin(2 * np.pi * frequency * t) * 0.3
            sd.play(tone.astype(np.float32), SAMPLE_RATE)
            sd.wait()
        except Exception:
            pass

    def audio_to_wav(self, frames):
        """Convert audio frames to WAV buffer."""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(frames))
        wav_buffer.seek(0)
        return wav_buffer

    def transcribe(self, frames):
        """Transcribe audio with faster-whisper."""
        if not frames:
            return None

        wav_buffer = self.audio_to_wav(frames)

        wav_buffer.seek(0)
        audio_data = np.frombuffer(wav_buffer.read(), dtype=np.int16)
        # Skip WAV header (44 bytes)
        header_samples = 22  # 44 bytes / 2 bytes per sample
        if len(audio_data) > header_samples:
            audio_data = audio_data[header_samples:]
        audio_float = audio_data.astype(np.float32) / 32768.0

        segments, info = self.model.transcribe(
            audio_float,
            language=WHISPER_LANGUAGE,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        text = " ".join(text_parts).strip()
        return text if text else None

    def inject_to_terminal(self, text):
        """Paste text into active terminal via Clipboard + Ctrl+V (WITHOUT Enter)."""
        now = time.time()
        if now - self.last_injection < self.DEBOUNCE_SECONDS:
            print("  Debounce -- skipped")
            return
        print(f"  Pasting: \"{text}\"")
        try:
            pyperclip.copy(text)
            time.sleep(0.3)
            pyautogui.hotkey('ctrl', 'v')
            self.last_injection = time.time()
            self.awaiting_confirm = True
            print(f"  Pasted! Tap {PTT_KEY} to send")
        except Exception as e:
            print(f"  Paste failed: {e}")

    def confirm_send(self):
        """Press Enter — send the text."""
        print("  [SEND] Enter!")
        self.awaiting_confirm = False
        pyautogui.press('enter')

    def on_ptt_press(self):
        """F9 pressed — start recording immediately (with debounce)."""
        if self.f9_already_processed:
            return  # Ignore Logitech double-signal
        self.f9_already_processed = True
        self.f9_press_time = time.time()

        # Always start recording (on tap it's discarded, on hold it's used)
        self.is_ptt_held = True
        self.beep(BEEP_START_FREQ, BEEP_START_DUR)
        self.mic.start_recording()
        print("  [REC] Recording...")

    def on_ptt_release(self):
        """F9 released — Tap = Confirm, Hold = Transcribe."""
        hold_duration = time.time() - self.f9_press_time

        # Reset debounce after 1 second
        threading.Timer(1.0, self._reset_f9).start()

        # SHORT TAP (< 0.5s)
        if hold_duration < self.TAP_THRESHOLD:
            self.is_ptt_held = False
            self.mic.stop_recording()

            if self.awaiting_confirm:
                self.confirm_send()
            else:
                print(f"  Too short -- discarded. (Hold {PTT_KEY} longer to record)")
            return

        # LONG HOLD (>= 0.5s): Stop recording + transcribe
        if not self.is_ptt_held:
            return
        self.is_ptt_held = False
        self.awaiting_confirm = False
        frames = self.mic.stop_recording()
        self.beep(BEEP_STOP_FREQ, BEEP_STOP_DUR)
        print("  [STOP] Processing...")

        def process():
            text = self.transcribe(frames)
            if text:
                print(f"  Recognized: \"{text}\"")
                self.inject_to_terminal(text)
            else:
                print("  No text recognized.")
                print(f"\n  Ready! Hold {PTT_KEY} to speak.\n")

        threading.Thread(target=process, daemon=True).start()

    def _reset_f9(self):
        """Release F9 lock (after timer)."""
        self.f9_already_processed = False

    def run(self):
        """Main loop with keyboard listener."""
        self.init()

        def on_press(key):
            if key == PTT_KEY:
                self.on_ptt_press()

        def on_release(key):
            if key == PTT_KEY:
                self.on_ptt_release()

        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                pass

        self.mic.close()
        print("\n  Done.")


# -- Main -----------------------------------------------------------------
if __name__ == "__main__":
    app = VoiceInput()
    app.run()
