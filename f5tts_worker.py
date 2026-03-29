"""
F5-TTS Worker — runs in Python 3.11 venv with CUDA
Receives text via stdin, generates audio, returns WAV path via stdout.

Requires:
  - Python 3.11 venv with: torch (CUDA), f5-tts, ffmpeg shared DLLs
  - A reference audio file for voice cloning
  - See README for setup instructions

Start: D:\\Assets\\f5tts_env\\Scripts\\python.exe f5tts_worker.py
"""

import sys
import os
import time
import tempfile

# UTF-8 for Windows
sys.stdin = open(sys.stdin.fileno(), mode='r', encoding='utf-8', buffering=1)
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

# ── Configuration ──
REFERENCE_AUDIO = r"D:\Assets\katja_reference.mp3"  # ← Your voice sample (10-15 seconds)
REFERENCE_TEXT = (
    "Guten Tag, mein Name ist Katja. Ich bin die Sprachassistentin der Kanzlei Köper. "
    "Ich helfe Ihnen gerne bei allen Fragen rund um Ihre Akte und informiere Sie über "
    "aktuelle Fristen und Termine."
)
SPEED = 1.3          # 1.0 = normal, 1.3 = 30% faster
NFE_STEP = 32        # Quality (higher = better, slower)
TEMP_DIR = tempfile.gettempdir()

# ffmpeg shared DLLs must be in PATH (required by torchcodec)
FFMPEG_DIR = r"D:\Assets\ffmpeg-8.1-full_build-shared\bin"  # ← Adjust to your ffmpeg path
if os.path.isdir(FFMPEG_DIR):
    os.environ["PATH"] = FFMPEG_DIR + ";" + os.environ.get("PATH", "")

sys.stderr.write("F5-TTS Worker: Loading model...\n")
t0 = time.time()

from f5_tts.api import F5TTS

tts = F5TTS(device="cuda")

sys.stderr.write(f"F5-TTS Worker: Model loaded in {time.time() - t0:.1f}s (CUDA)\n")
sys.stderr.write(f"F5-TTS Worker: Reference = {REFERENCE_AUDIO}\n")
sys.stderr.write(f"F5-TTS Worker: Speed = {SPEED}x\n")
sys.stderr.write("F5-TTS Worker: Ready. Waiting for text via stdin...\n")

# ── Main loop ──
for line in sys.stdin:
    text = line.strip()
    if not text:
        continue

    try:
        wav_path = os.path.join(TEMP_DIR, f"f5tts_{int(time.time()*1000)}.wav")

        tts.infer(
            ref_file=REFERENCE_AUDIO,
            ref_text=REFERENCE_TEXT,
            gen_text=text,
            file_wave=wav_path,
            speed=SPEED,
            nfe_step=NFE_STEP,
            remove_silence=True,
            show_info=lambda x: None,
        )

        print(wav_path, flush=True)
        sys.stderr.write(f"F5-TTS: \"{text[:60]}\" -> {wav_path}\n")

    except Exception as e:
        sys.stderr.write(f"F5-TTS error: {e}\n")
        print("ERROR", flush=True)
