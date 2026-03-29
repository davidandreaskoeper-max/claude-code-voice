#!/usr/bin/env python3
"""
TTS MCP-Server for Claude Code
Supports two engines:
  - edge-tts (Microsoft Neural Voices, requires internet)
  - piper (fully local, offline)

Setup:
  1. pip install edge-tts        (for edge engine)
     pip install piper-tts       (for piper engine)
  2. For piper: download a voice model (see README)
  3. Add to .mcp.json:
     {"mcpServers": {"tts-server": {"command": "python", "args": ["path/to/tts_mcp_server.py"]}}}
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave

# ── UTF-8 Encoding for Windows (Fix: Umlauts ü/ö/ä/ß) ──
sys.stdin = open(sys.stdin.fileno(), mode='r', encoding='utf-8', buffering=1)
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

# ── Configuration ──
TTS_ENGINE = "piper"              # "edge" = Edge-TTS (internet), "piper" = Piper (local)

# Edge-TTS settings
EDGE_VOICE = "de-DE-KatjaNeural"  # Microsoft Neural Voice
EDGE_RATE = "+20%"                # Speech speed
EDGE_VOLUME = "+0%"               # Volume offset

# Piper settings
PIPER_MODEL = r"path\to\de_DE-thorsten-high.onnx"  # ← Change to your model path
PIPER_SPEED = 0.85                # Lower = faster (1.0 = normal)

TEMP_DIR = tempfile.gettempdir()

_tts_lock = threading.Lock()
_piper_voice = None


def _get_piper_voice():
    """Lazy-load Piper voice (once)."""
    global _piper_voice
    if _piper_voice is None:
        from piper.voice import PiperVoice
        sys.stderr.write(f"Loading Piper model: {PIPER_MODEL}\n")
        _piper_voice = PiperVoice.load(PIPER_MODEL)
        sys.stderr.write("Piper model loaded.\n")
    return _piper_voice


def _play_audio(filepath):
    """Play audio via Windows PowerShell MediaPlayer and wait for completion."""
    try:
        ps_script = f'''
Add-Type -AssemblyName presentationCore
$player = New-Object System.Windows.Media.MediaPlayer
$player.Open([System.Uri]::new("{filepath}"))
Start-Sleep -Milliseconds 600
$player.Play()
while (-not $player.NaturalDuration.HasTimeSpan) {{
    Start-Sleep -Milliseconds 100
}}
$total = $player.NaturalDuration.TimeSpan.TotalMilliseconds
while ($player.Position.TotalMilliseconds -lt ($total - 50)) {{
    Start-Sleep -Milliseconds 200
}}
Start-Sleep -Milliseconds 300
$player.Close()
'''
        subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            timeout=60
        )
    except Exception as e:
        sys.stderr.write(f"Playback error: {e}\n")
    finally:
        try:
            os.remove(filepath)
        except OSError:
            pass


def _speak_edge(text, audio_path):
    """TTS with Edge-TTS (internet required)."""
    import edge_tts

    async def generate():
        communicate = edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE, volume=EDGE_VOLUME)
        await communicate.save(audio_path)

    asyncio.run(generate())


def _speak_piper(text, audio_path):
    """TTS with Piper (fully local)."""
    from piper.config import SynthesisConfig
    voice = _get_piper_voice()
    config = SynthesisConfig(length_scale=PIPER_SPEED)
    with wave.open(audio_path, 'wb') as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=config)


def _speak_thread(text):
    """Generate TTS audio + play it (runs in separate thread)."""
    with _tts_lock:
        try:
            ext = ".mp3" if TTS_ENGINE == "edge" else ".wav"
            audio_path = os.path.join(TEMP_DIR, f"tts_{int(time.time()*1000)}{ext}")

            if TTS_ENGINE == "edge":
                _speak_edge(text, audio_path)
            else:
                _speak_piper(text, audio_path)

            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                _play_audio(audio_path)
            else:
                sys.stderr.write("TTS: Empty audio file generated\n")

        except Exception as e:
            sys.stderr.write(f"TTS error: {e}\n")


def handle_message(msg):
    """Process MCP JSON-RPC message."""
    method = msg.get('method', '')
    msg_id = msg.get('id')

    if method == 'initialize':
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "tts-server", "version": "3.0.0"}
            }
        }

    if method == 'notifications/initialized':
        return None

    if method == 'tools/list':
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [{
                    "name": "speak",
                    "description": (
                        "Speaks text aloud through the speakers. "
                        "Use this tool to read responses to the user. "
                        "Summarize in 1-3 short sentences. "
                        "Do NOT read code, SQL, JSON, or long lists — only the key message."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The text to speak (max 3 sentences)"
                            }
                        },
                        "required": ["text"]
                    }
                }]
            }
        }

    if method == 'tools/call':
        params = msg.get('params', {})
        tool_name = params.get('name', '')
        args = params.get('arguments', {})

        if tool_name == 'speak':
            text = args.get('text', '')
            # Ensure UTF-8 encoding (Windows encoding fix)
            text = text.encode('utf-8').decode('utf-8')
            if text:
                t = threading.Thread(target=_speak_thread, args=(text,), daemon=True)
                t.start()
                time.sleep(0.1)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Spoken: {text[:80]}..."}]
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "No text to speak."}]
                    }
                }

    if method == 'ping':
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }

    return None


def main():
    if TTS_ENGINE == "piper":
        engine_label = f"Piper (local, {os.path.basename(PIPER_MODEL)})"
    else:
        engine_label = f"Edge-TTS ({EDGE_VOICE})"
    sys.stderr.write(f"TTS MCP-Server v3.0 started — Engine: {engine_label}\n")

    # Pre-load Piper model at startup (no delay on first speak)
    if TTS_ENGINE == "piper":
        try:
            _get_piper_voice()
        except Exception as e:
            sys.stderr.write(f"Could not load Piper model: {e}\n")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
            response = handle_message(msg)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as e:
            sys.stderr.write(f"JSON error: {e}\n")
        except Exception as e:
            sys.stderr.write(f"Error: {e}\n")


if __name__ == "__main__":
    main()
