#!/usr/bin/env python3
"""
TTS MCP-Server for Claude Code
Uses edge-tts (Microsoft Neural Voices) for natural speech output.

Setup:
  1. pip install edge-tts
  2. Add to .mcp.json:
     {"mcpServers": {"tts-server": {"command": "python", "args": ["path/to/tts_mcp_server.py"]}}}
  3. Add speak() instructions to CLAUDE.md (see README)
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

import edge_tts

# ── Configuration ──
VOICE = "de-DE-KatjaNeural"  # Microsoft Neural Voice (German, female)
RATE = "+20%"                 # Speech speed (1.2x)
VOLUME = "+0%"                # Volume offset
TEMP_DIR = tempfile.gettempdir()

_tts_lock = threading.Lock()


def _play_mp3(filepath):
    """Play MP3 via Windows PowerShell MediaPlayer and wait for completion."""
    try:
        ps_script = f'''
Add-Type -AssemblyName presentationCore
$player = New-Object System.Windows.Media.MediaPlayer
$player.Open([System.Uri]::new("{filepath}"))
Start-Sleep -Milliseconds 600
$player.Play()
# Wait for NaturalDuration to become available
while (-not $player.NaturalDuration.HasTimeSpan) {{
    Start-Sleep -Milliseconds 100
}}
$total = $player.NaturalDuration.TimeSpan.TotalMilliseconds
# Wait until playback finished
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


def _speak_thread(text):
    """Generate TTS audio + play it (runs in separate thread)."""
    with _tts_lock:
        try:
            mp3_path = os.path.join(TEMP_DIR, f"tts_{int(time.time()*1000)}.mp3")

            async def generate():
                communicate = edge_tts.Communicate(text, VOICE, rate=RATE, volume=VOLUME)
                await communicate.save(mp3_path)

            asyncio.run(generate())

            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
                _play_mp3(mp3_path)
            else:
                sys.stderr.write("TTS: Empty MP3 generated\n")

        except Exception as e:
            sys.stderr.write(f"TTS error: {e}\n")


def handle_message(msg):
    """Process MCP JSON-RPC message."""
    method = msg.get('method', '')
    msg_id = msg.get('id')

    # Initialize
    if method == 'initialize':
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "tts-server", "version": "2.0.0"}
            }
        }

    # Initialized notification
    if method == 'notifications/initialized':
        return None

    # List tools
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

    # Call tool
    if method == 'tools/call':
        params = msg.get('params', {})
        tool_name = params.get('name', '')
        args = params.get('arguments', {})

        if tool_name == 'speak':
            text = args.get('text', '')
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

    # Ping
    if method == 'ping':
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    # Unknown method
    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }

    return None


# ── MCP stdio Loop ──
def main():
    sys.stderr.write(f"TTS MCP-Server v2.0 started (Voice: {VOICE}, Rate: {RATE})\n")

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
