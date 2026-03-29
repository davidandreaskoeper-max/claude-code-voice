# Claude Code Voice I/O

**Sprachsteuerung für Claude Code** — Diktieren per Push-to-Talk, Antworten per Sprachausgabe.

> **Spracheingabe (STT):** Läuft vollständig lokal mit faster-whisper — deine Diktate verlassen niemals den Rechner.
>
> **Sprachausgabe (TTS):** Drei Engines zur Wahl:
> - **F5-TTS** (empfohlen) — komplett lokal, GPU-beschleunigt, Voice Cloning (klone jede Stimme mit 10s Audio!)
> - **Piper** — komplett lokal, CPU, sehr schnell, aber nur vorgefertigte Stimmen
> - **Edge-TTS** — beste Qualität (Microsoft Neural Voices), braucht aber Internet

---

## Was ist das?

Zwei Python-Skripte, die Claude Code um Sprach-Ein- und Ausgabe erweitern:

| Komponente | Datei | Funktion |
|---|---|---|
| **Voice Input** | `voice_input.py` | Push-to-Talk (F9) → faster-whisper → Text ins Terminal |
| **Voice Output** | `tts_mcp_server.py` | MCP-Server → edge-tts → Sprachausgabe über Lautsprecher |

### So funktioniert's

```
Du (F9 halten + sprechen) → Whisper → Text wird eingefügt → F9 tippen = absenden
                                                                          ↓
Claude antwortet → MCP speak() Tool → edge-tts → Katja Neural → Lautsprecher
```

### Features

**Voice Input (Push-to-Talk):**
- **F9 halten** = Aufnahme läuft
- **F9 loslassen** = Text wird eingefügt (zum Prüfen, kein auto-Enter)
- **F9 kurz tippen** = Enter drücken (abfeuern)
- Pre-Init Mikrofon-Stream (kein Delay beim ersten Tastendruck)
- 1-Sekunde Ring-Buffer (fängt Audio VOR dem Tastendruck auf)
- Beep-Feedback bei Start/Stop
- Logitech-Doppelsignal-Entprellung

**Voice Output (TTS):**
- Microsoft Katja Neural (deutsch, natürlich klingend)
- Sprechgeschwindigkeit einstellbar (Standard: 1.2x)
- Läuft als MCP-Server — Claude Code ruft `speak()` automatisch auf
- Kein API-Key nötig (edge-tts ist kostenlos)

---

## Voraussetzungen

- **Windows 10/11** (getestet auf Windows 11 Pro)
- **Python 3.10+**
- **Claude Code** (CLI, Desktop App oder IDE Extension)
- Ein Mikrofon (USB-Headset, Speakerphone, etc.)

---

## Warum nicht Claude Code's eingebautes /voice?

| Problem | Details |
|---|---|
| Natives Audio-Modul fehlt | Windows npm-Paket unvollständig |
| 4 Sekunden Delay | Stream-Init erst beim Tastendruck |
| Cloud-STT | Nicht DSGVO-konform |
| Kein Zwei-Schritt-Modus | Kein Prüfen vor dem Absenden |

Diese Lösung behebt alle vier Probleme.

---

## Getestet mit

| Hardware | Modell |
|---|---|
| Mikrofon/Speakerphone | AnkerWork S600 |
| Maus | Logitech MX Master 3s |
| GPU | NVIDIA RTX 5080 16GB |
| CPU | AMD Ryzen 9 9900X |
| OS | Windows 11 Pro |

> F9-Mapping über Logitech Options+: Daumentaste → F9 Tastenkürzel

---

## Installation

### 1. Dependencies installieren

```bash
# Voice Input
pip install faster-whisper pynput sounddevice numpy pyautogui pyperclip

# Voice Output — wähle eine Engine:
pip install edge-tts      # Option A: Edge-TTS (braucht Internet, beste Qualität)
pip install piper-tts     # Option B: Piper (komplett offline, CPU)
                          # Option C: F5-TTS (komplett offline, GPU, Voice Cloning) → siehe Schritt 2
```

> Beim ersten Start wird das Whisper-Modell "small" (~460 MB) heruntergeladen und gecacht.

### 2. (Nur für F5-TTS) Python 3.11 venv + CUDA Setup

F5-TTS benötigt Python < 3.12 und eine NVIDIA GPU. Setup als isolierte Umgebung:

```bash
# Python 3.11 installieren (parallel zu bestehender Version)
pip install uv
uv python install 3.11

# Venv erstellen
uv python find 3.11  # → gibt den Pfad zurück
<python3.11-pfad> -m venv D:\Assets\f5tts_env

# Aktivieren und Pakete installieren
D:\Assets\f5tts_env\Scripts\activate
pip install torch torchaudio --extra-index-url https://download.pytorch.org/whl/cu128
pip install f5-tts
```

**FFmpeg Shared Build** (benötigt von torchcodec):
- Download: https://github.com/GyanD/codexffmpeg/releases (`ffmpeg-X.X-full_build-shared.zip`)
- Entpacken und Pfad in `f5tts_worker.py` unter `FFMPEG_DIR` eintragen

**Voice Sample** für Voice Cloning:
- 10-15 Sekunden Audio der gewünschten Stimme als WAV/MP3
- Pfad in `f5tts_worker.py` unter `REFERENCE_AUDIO` eintragen
- Tipp: Mit Edge-TTS ein Katja-Sample generieren und klonen!

Beim ersten Start lädt F5-TTS das Modell automatisch herunter (~1.5 GB).

### 3. (Nur für Piper) Voice-Modell herunterladen

```python
from piper.download_voices import download_voice
from pathlib import Path

download_voice('de_DE-thorsten-high', Path('./piper-voices'))
```

Das lädt `de_DE-thorsten-high.onnx` (~108 MB) herunter. Verfügbare deutsche Stimmen:

| Voice | Qualität | Geschlecht |
|---|---|---|
| `de_DE-thorsten-high` | **Hoch (empfohlen)** | Männlich |
| `de_DE-thorsten-medium` | Mittel | Männlich |
| `de_DE-kerstin-low` | Niedrig | Weiblich |
| `de_DE-ramona-low` | Niedrig | Weiblich |
| `de_DE-thorsten_emotional-medium` | Mittel | Männlich (emotional) |

### 4. Audio-Device ermitteln

```python
import sounddevice as sd
print(sd.query_devices())
```

Notiere die **Nummer** deines Mikrofons (z.B. `8`).

### 4. Voice Input konfigurieren

In `voice_input.py` anpassen:

```python
AUDIO_DEVICE = 8          # ← Deine Mikrofon-Nummer
WHISPER_MODEL = "small"   # tiny/base/small/medium/large
WHISPER_DEVICE = "cpu"    # "cuda" falls NVIDIA GPU vorhanden
WHISPER_COMPUTE = "int8"  # "float16" für GPU
PTT_KEY = keyboard.Key.f9 # Beliebige Taste
```

### 6. TTS-Engine wählen

In `tts_mcp_server.py` anpassen:

```python
TTS_ENGINE = "f5tts"    # "f5tts" = lokal + GPU + Voice Cloning (empfohlen)
                        # "piper" = lokal + CPU
                        # "edge"  = Microsoft Neural Voices (Internet)

# F5-TTS-Einstellungen (nur bei TTS_ENGINE = "f5tts")
F5TTS_PYTHON = r"D:\Assets\f5tts_env\Scripts\python.exe"  # ← Python 3.11 venv
F5TTS_WORKER = r"D:\Assets\f5tts_worker.py"                # ← Worker-Skript

# Piper-Einstellungen (nur bei TTS_ENGINE = "piper")
PIPER_MODEL = r"path\to\de_DE-thorsten-high.onnx"  # ← Pfad zum Modell
PIPER_SPEED = 0.85                                   # Kleiner = schneller

# Edge-TTS-Einstellungen (nur bei TTS_ENGINE = "edge")
EDGE_VOICE = "de-DE-KatjaNeural"
EDGE_RATE = "+30%"
```

### 7. MCP-Server registrieren

Erstelle `.mcp.json` in deinem Claude Code Arbeitsverzeichnis:

```json
{
  "mcpServers": {
    "tts-server": {
      "command": "python",
      "args": ["C:/pfad/zu/tts_mcp_server.py"]
    }
  }
}
```

> **Windows-Tipp:** Falls `"python"` nicht funktioniert, den vollen Pfad verwenden:
> `"C:\\Users\\DEIN_USER\\AppData\\Local\\Python\\pythonXXX\\python.exe"`

### 8. CLAUDE.md konfigurieren

Damit Claude Code automatisch vorliest, füge in deine `CLAUDE.md` ein:

```markdown
## Sprachausgabe

Wenn der Anwender per Sprache kommuniziert (erkennbar an natürlicher Sprache),
rufe IMMER das `speak` Tool auf:

1. Fasse die Antwort in 1-3 kurzen Sätzen zusammen
2. Rufe `speak()` mit der Zusammenfassung auf
3. Schreibe danach die ausführliche Antwort als Text

Was NICHT vorlesen: Code-Blöcke, SQL, JSON, Diffs, lange Listen.
Was vorlesen: Zahlen, Ergebnisse, Statusmeldungen, Kurzantworten.
```

### 9. Starten

**Terminal 1 — Voice Input:**
```bash
python voice_input.py
```

**Terminal 2 — Claude Code:**
```bash
claude
```

Der TTS-Server startet automatisch über MCP wenn Claude Code startet.

---

## Verwendung

1. **Diktieren:** F9 gedrückt halten und sprechen. Beim Loslassen erscheint der transkribierte Text im Claude Code Prompt.
2. **Prüfen:** Text lesen — stimmt alles?
3. **Absenden:** F9 kurz antippen (< 0.5 Sekunden) = Enter.
4. **Antwort hören:** Claude antwortet per Text UND Sprache automatisch.

### Tastenbelegung

| Aktion | Taste |
|---|---|
| Aufnehmen | F9 halten (> 0.5s) |
| Text einfügen | F9 loslassen |
| Absenden (Enter) | F9 kurz tippen (< 0.5s) |

> Die Taste ist in `PTT_KEY` konfigurierbar. Funktioniert auch mit Maus-Seitentasten über Logitech/Razer Software → F9 Mapping.

---

## Konfiguration

### TTS-Stimme ändern

In `tts_mcp_server.py`:

```python
VOICE = "de-DE-KatjaNeural"  # Deutsche Stimme (weiblich)
RATE = "+20%"                 # Geschwindigkeit
VOLUME = "+0%"                # Lautstärke
```

Verfügbare deutsche Stimmen:
- `de-DE-KatjaNeural` (weiblich, Standard)
- `de-DE-ConradNeural` (männlich)
- `de-DE-AmalaNeural` (weiblich)
- `de-DE-KillianNeural` (männlich)

Alle Stimmen auflisten: `edge-tts --list-voices`

### Whisper-Modell

| Modell | Größe | Geschwindigkeit | Qualität |
|---|---|---|---|
| `tiny` | ~75 MB | Sehr schnell | Grundlegend |
| `base` | ~140 MB | Schnell | OK |
| `small` | ~460 MB | Mittel | **Gut (empfohlen)** |
| `medium` | ~1.5 GB | Langsam | Sehr gut |
| `large-v3` | ~3 GB | Sehr langsam | Exzellent |

> Mit NVIDIA GPU (`WHISPER_DEVICE = "cuda"`, `WHISPER_COMPUTE = "float16"`) sind auch `medium` und `large` praxistauglich.

---

## Windows-Autostart (optional)

Damit Voice Input bei Windows-Start automatisch läuft:

1. Erstelle `voice_input.bat` (mit Duplikat-Schutz):
```batch
@echo off
:: Prevent duplicate instances
tasklist /FI "WINDOWTITLE eq VoiceInput" 2>NUL | find /I "python.exe" >NUL && (
    echo Voice Input already running, skipping.
    exit /b
)
:: IMPORTANT: Use full Python path, NOT just "python" (Windows Store alias conflict!)
start /MIN "VoiceInput" "C:\full\path\to\python.exe" "-u" "C:\path\to\voice_input.py"
```

2. Lege die `.bat` in den Startup-Ordner:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```

---

## Architektur

```
┌─────────────────────────────────────────────────────────┐
│                    Claude Code (Terminal)                │
│                                                         │
│  ┌──────────────┐              ┌──────────────────────┐ │
│  │  User Prompt  │◄── Ctrl+V ──│  frau_mueller_voice  │ │
│  │              │              │  (Push-to-Talk F9)   │ │
│  │              │              │  faster-whisper STT  │ │
│  └──────┬───────┘              └──────────────────────┘ │
│         │                                               │
│         ▼                                               │
│  ┌──────────────┐   MCP stdio   ┌──────────────────┐   │
│  │  Claude LLM  │──────────────►│  tts_mcp_server  │   │
│  │              │  speak(text)  │  edge-tts (Katja) │   │
│  └──────────────┘               └────────┬─────────┘   │
│                                          │              │
│                                          ▼              │
│                                    🔊 Lautsprecher      │
└─────────────────────────────────────────────────────────┘
```

**Voice Input** läuft als eigenständiger Prozess neben Claude Code. Er überwacht F9, nimmt Audio auf, transkribiert lokal mit faster-whisper und fügt den Text per Clipboard ins Terminal ein.

**Voice Output** läuft als MCP-Server innerhalb von Claude Code. Wenn Claude das `speak()` Tool aufruft, generiert edge-tts eine MP3-Datei und spielt sie über PowerShell MediaPlayer ab.

---

## Troubleshooting

| Problem | Lösung |
|---|---|
| F9 reagiert nicht / Diktat stumm | Prüfen ob **zwei** Voice-Prozesse laufen: `tasklist \| findstr python` — zwei Instanzen blockieren sich gegenseitig. Alle killen, eine neu starten. |
| Windows Store Python startet zweite Instanz | Windows hat einen `python.exe` Alias in WindowsApps. Immer den **vollen Pfad** zum richtigen Python verwenden. Alias deaktivieren: Windows-Einstellungen → Apps → Erweiterte App-Einstellungen → App-Ausführungsaliase → Python deaktivieren. |
| `speak()` wird nicht aufgerufen | `/mcp` prüfen → tts-server muss "connected" zeigen |
| TTS-Server "failed" | Vollen Python-Pfad in `.mcp.json` verwenden |
| Kein Audio bei Aufnahme | `AUDIO_DEVICE` Nummer prüfen (`sd.query_devices()`) |
| Whisper erkennt nichts | VAD filtert Stille — lauter/näher sprechen |
| Text wird nicht eingefügt | Claude Code Terminal muss im Vordergrund sein |
| Logitech-Doppelklick | Entprellung ist eingebaut (1s Sperre nach Release) |
| Edge-TTS Timeout | Internetverbindung nötig (edge-tts nutzt Microsoft-Server) |

---

## Bekannte Einschränkungen

- **Windows only** — `pyautogui` und PowerShell MediaPlayer sind Windows-spezifisch. macOS/Linux-Portierung möglich (PRs willkommen).
- **Edge-TTS braucht Internet** — Nur relevant bei `TTS_ENGINE = "edge"`. Mit `TTS_ENGINE = "piper"` ist alles 100% offline. [Piper TTS](https://github.com/rhasspy/piper) ist eingebaut und bereit.
- **Whisper "small" auf CPU** — Transkription dauert ~1-3 Sekunden. Mit GPU deutlich schneller.

---

## Lizenz

MIT License — siehe [LICENSE](LICENSE).

---

## Credits

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — Schnelle Whisper-Implementierung
- [edge-tts](https://github.com/rany2/edge-tts) — Microsoft Edge TTS API
- [Claude Code](https://claude.ai/code) — Anthropic's CLI für Claude
- [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) — Standard für Tool-Integration
