# OllamaVibeDesk

Modern offline-first PyQt6 desktop GUI for a **local Ollama** instance, with **automatic answer function**, **different speakers**, **streaming responses**, and optional **local TTS playback/export** through Windows SAPI or a **VibeVoice compatible build-in server**.

<img width="1423" height="950" alt="grafik" src="https://github.com/user-attachments/assets/b4770dc2-2e9e-413f-a9c7-c1d1d44a0533" />


## Main features

- real Ollama integration via local API
- streamed assistant output
- Support for Vibevoice ASR Input
- Optional Audio Postprocessing
- Different Characters (for the User Auto-Answers and/or LLM Personality)
- model list refresh from the local Ollama API
- persistent chat sessions stored **inside the app folder**
- theme switching
- cancel/stop generation
- per-message **Vorlesen** action for assistant replies by voice
- optional WAV export via a local TTS endpoint
- Windows installer and launcher batch files
- no cloud requirement for normal chat usage once local services are present
- multiple language support (currently: german, english, french, spanish, russian and some more..)
- different voice output speakers for human and AI
- auto answer function to act like the human based of the ELIZA algorythm to automaticly continue a chat dialog
- automatic code generating based upon the dialogs in the auto-answer mode (Python, c#, php, html, what ever..) (in subfolder ..\app_data\generated_code)
- automaticly switching to "thinking" mode in advanced questions like for code generation, jokes, abstract questions..
- short- and longterm "brain" function added to be available for ANY chat as a knowledge source (base is a local working wiki or something similar if unavailable)
- RAG function added to add/remove/change/view/modify external knowledge bases
- Function to add media files and data files to be analysed by a selected LLM added
- Buttons added in Settings for the "Brain" and Buttons in Chat windows to view generated output code and to view the current "Brain Memory".
  
<img width="451" height="277" alt="ovv_v1_16b" src="https://github.com/user-attachments/assets/1a9844f9-fe1c-47d5-838c-afcbde55120c" />
  

Note: Using VibeVoice Mode takes some time to generate a voice output in contrast to the use of the default Windows Sapi.

## Basic usage instructions / Notes

Make sure you have installed the requirements (Ollama, Python 3.13 (also works using 3.12.9), might be PIP if you dont have it already, GIT).

Start Ollama (!) and close / minimize the GUI, make sure you have at least one model to use if you dont have any get a model using the ollama gui, suggestion: Dolphin3 or Qwen3.5:9b

Extract the archive (or clone the repository) to a new folder ex. c:\AI\OllamaVibeDesk and start the install_windows.bat it will install all the required files (for the base setup). 

If you dont break it it should start the GUI automaticly after installation (in the other case start the GUI using run_windows.bat)

If you a from germany and want native german language you dont have to do anything for a first test, just go to the prompt field and enter something like "erstell ein 3d Maze erkundungs-Spiel das man mit WSAD und der maus steuern kann aus der ego perspektive" then press send (or ctrl/strg + enter) and listen to the endless automatic dialog.

If you are from a different country or want a different language go to settings (einstellungen) and select language (sprache) to select it. (save the config after that). Now back in the Main window enter something in the prompt box like "How old is the Towerwatch in London."

How ever that all is just the base version (takes ~ 240 mb at all) but if you want to use MS Vibevoice change the speaker mode in settings and change it from TTS/SaPi to Vibevoice.

The App is including a local working VibeVoice Server and is able to get all the requirements including optional voice models for different languages (male/female) in a simple oneclick build-in installer (VibeVoice setup) to make it finally work offline.

Note: Make sure to start the VibeVoice Server after the installation.

The Full installation including vibevoice is taking ~ 3 GB in total (just wait the setup to complete the installation procedure). Note using vibevoice it might take MUCH longer to generate a single Answer / question in VibeVoice quality because the full answer will be sent to the model to render a wave file of it first to get more human like context language. (i have tested this using different systems, it also work using a gen3 (yes, i really mean a intel Gen 3 CPU from 2012) intel i5 / nvidia rtx 4xxx)). You can diable the network connection now if you like and have fun listen to it.

Note: Even if the auto-answer mode is active you can send a prompt of your own to the current dialog, it will be used as the next prompt after the current and the ELIZA / Random Answer mode continue to work after that. Btw. if a dialog is getting too long the App will automaticly switch to a new chat but it will take some dialogs from the previous chat to new one that holds the context straight in flow (there are many options in the settings to modify the behave).

btw. the idea and description for the new project https://github.com/zeittresor/dark_matrix (Firefox Matrix-Syle extension working locally) is 99% created by the output of a (single) whole night while sleeping :-)

## Requirements

- Windows 10/11
- Python 3.10+ for the GUI
- A running local Ollama instance
- One or more Ollama models already pulled locally

## Folder layout

- `install_windows.bat` – creates a local virtual environment and installs Python packages for the GUI
- `run_windows.bat` – starts the GUI from the local venv
- `requirements.txt` – Python requirements for the GUI
- `app/` – application source
- `app_data/` – created on first run; contains config, chats, audio, cache, optional TTS helper data

## Install

Double-click:

`install_windows.bat`

Then start with:

`run_windows.bat`

## Ollama setup

Default base URL:

`http://127.0.0.1:11434`

The app reads models from Ollama and lets you pick one from the dropdown.

## TTS / "Vorlesen"

The GUI supports these modes:

- **Microsoft SAPI-compatible**
- **Microsoft VibeVoice OpenAI-compatible**
- **Disabled**

If you enable `vibevoice_openai`, the GUI talks to a local endpoint like:

`http://127.0.0.1:8880/v1`

Generated audio is stored in:

`app_data/audio/`

## New: TTS setup assistant

The setup assistant is now opened from **Einstellungen** so the main header stays cleaner.

The assistant can:

- run one combined automatic setup flow (status check, FFmpeg check, wrapper download, setup where possible)
- download the VibeVoice OpenAI-compatible wrapper into `app_data/tts/vibevoice_openai/`
- create a dedicated wrapper venv when the Python version is suitable
- install wrapper requirements
- start and stop the wrapper server
- open the TTS folder and its log file

### Important behavior

- The GUI itself still does **not** embed VibeVoice directly.
- It manages a **separate local wrapper server** for cleaner isolation.
- On the **first actual server start**, the wrapper may download model files and voice presets into the local models folder. This can take quite a while.
- The setup assistant writes server output to:
  - `app_data/tts/vibevoice_openai/server.log`

## Expected local wrapper paths

- wrapper repo: `app_data/tts/vibevoice_openai/repo/`
- wrapper models: `app_data/tts/vibevoice_openai/models/`
- wrapper log: `app_data/tts/vibevoice_openai/server.log`

## Data placement

To respect low-space system drives and portable usage, the app stores its own data **next to the application**:

- config: `app_data/config.json`
- chat history: `app_data/chats/`
- audio files: `app_data/audio/`
- cache env vars: `HF_HOME`, `TRANSFORMERS_CACHE` point into `app_data/cache/` when launched through `run_windows.bat`
- TTS helper files: `app_data/tts/`

## Practical notes for VibeVoice on Windows

The currently targeted wrapper expects a fairly specific environment. In practice that means:

- Python 3.13 is recommended/expected for the wrapper itself
- `ffmpeg` should be available
- an NVIDIA GPU / CUDA-capable setup is the intended fast path
- first-run model downloads can be large

The assistant tries to make that visible and less confusing, but depending on the machine, manual adjustments may still be necessary.

For a zero-download local fallback, switch the TTS backend in **Einstellungen** to `windows_sapi`.


## Stability notes in this build

- Ollama chat now forces `think: false` by default for a simpler chat flow with thinking-capable models.
- If the streaming endpoint returns no visible text, the GUI performs one non-stream fallback request instead of leaving an empty bubble.
- Windows SAPI helper calls now decode PowerShell output more defensively on Windows systems with non-UTF-8 console output.
- After `install_windows.bat`, the GUI auto-starts after 10 seconds unless you cancel it.


## Windows-SAPI Aussprache-Optimierung

Wenn in den Einstellungen das Backend `windows_sapi` aktiv ist, kann optional die Checkbox **Windows-SAPI Aussprache-Optimierung verwenden** aktiviert werden.

Dann wird vor dem Vorlesen das lokale JSON-Lexikon unter `app_data/tts/sapi_lexicon.json` auf den bereits bereinigten TTS-Text angewendet. So lassen sich problematische Wörter, Abkürzungen oder Produktnamen gezielt anders aussprechen lassen.

Beispiel-Eintrag:

```json
{
  "type": "word",
  "from": "Ollama",
  "to": "Olama",
  "case_sensitive": false
}
```

Unterstützt werden `word` (ganze Wörter) und `phrase` (ganze Wortfolgen).

Changelog#

2.4.1#

Persistierte Themenabschnitte direkt in der linken Chatliste auswählbar.
Sprung zur gespeicherten Nachrichtenposition, auch nach erneutem Laden.
Echte Folge-Chats und Vorgänger bleiben separat sichtbar.
Keine weitere Begrenzung der Titelhistorie auf 64 Einträge.
Qt-Regressionstest für mehrere Einträge, Auswahl, Scrollposition und Fortsetzen am Gesprächsende.

Version 2.4.0 — 2026-09-21#

Tokenbudget statt acht Nachrichten als Standard; kein stilles Abschneiden der API-Historie.
Hintergrundprüfung von Modellgrenze, laufendem Kontext, RAM und NVIDIA-VRAM; konservatives Wachstum, Lastreserve und Pause bei kritischem Speicher.
Getrennte Steuerung pro Server/Modell, einmaliger OOM-/Kontextfehler-Retry mit kleinerem Kontext.
Nach Budget übernommene Dialogeinträge und gekennzeichnete, quellenbezogene Übergabeauszüge; Originale bleiben erhalten.
Dynamische Grundthema-/Schwerpunkttitel mit Nummer, Titelhistorie, Nachrichtenpositionen, Vorgänger-Navigation und Diagnoseansicht per Doppelklick.
Auto-Answer-Rundenzähler und Anhänge über automatische Übergänge erhalten; Stop setzt geplante Fortsetzungen zurück.
Auto-Answer-Worker beendet sich bei Abbruch zuverlässig; eigene Modellbudgets und begrenzte Ausgabe.
Ollama-HTTP-Fehlertexte bleiben für die Speicherdiagnose erhalten; unterbrochene Streams gelten nicht mehr als vollständige Antworten; keine blinde zweite Anfrage bei leerem Stream.
Native Tokenstatistiken verbessern die modellbezogene Schätzreserve; CJK-/UTF-8-Schätzung korrigiert.
Neue Defaults: automatische Übernahme, 32k-Obergrenze, kein erzwungener Kurzstil, 512 Token für Auto-Answer-LLM und neutrale Assistentenstimmhöhe. Vorhandene individuelle Einstellungen bleiben bestehen.
GUI-Limit des Auto-Answer-Modells entspricht jetzt der Konfigurationsgrenze 8192.
Chatlisten-Cache, vollständige Qt-Integrationstests, klare Teilprüfungsberichte und reproduzierbarer ZIP-Build ohne Benutzerdaten.
Installer verwendet intakte lokale Pakete wieder, prüft 64-Bit-Python und erhält den Rückgabecode der GUI-Prüfung. Wheelhouse-Build verwendet nur Binärpakete.

v2.3.0 – 2026-09-01#

Added per-model Ollama Reasoning/Thinking settings: Off, automatic for code, Low, Medium and High.
Applied the selected model's reasoning level consistently to normal chat and the Auto-Answer LLM path.
Replaced the narrow Qwen-specific Thinking switch with native Ollama think levels for compatible model families.
Added safe compatibility retries for older Ollama runtimes: level, boolean Thinking, then omission of the unsupported field.
Added a local Ollama API integration smoke test covering streamed thinking, content and compatibility fallback.
Added topic-aware automatic continuation titles derived locally from the latest conversation section.
Added localized, numbered continuation suffixes and persisted parent/index/topic metadata for every rollover chat.
Fixed premature rollover caused by reserving the full configured maximum response length for every request.
Added pure context-budget regressions so short prompts no longer create unnecessary follow-up chats.
Expanded installation verification for the new modules, reasoning controls and API request behavior.

v2.2.0 – 2026-08-18#

Added separate assistant and user voice profiles, intensity, speaking rate, pitch and volume.
Added natural, deep/masculine, bright/feminine, narrator, dramatic, robotic, tipsy, comic and whisper profiles.
Added dependency-free local WAV character effects and VibeVoice fallback modulation.
Added atomic TTS audio writes, response-type validation and rejection of JSON/HTML error bodies saved as audio.
Added VibeVoice microphone input through the OpenAI-compatible CrispASR transcription endpoint.
Added a closed, runtime-verified speech-model catalog: full multilingual VibeVoice ASR, VibeVoice ASR BitNet, Realtime 0.5B GGUF TTS and VibeVoice 1.5B GGUF TTS.
Added strict task/runtime/backend validation so ASR checkpoints, realtime voice packs and 1.5B TTS are never mixed incompatibly.
Added a separate CrispASR Windows installer with CPU-legacy default (no AVX2 assumption), plus optional CPU, Vulkan and CUDA variants.
Restricted the Python VibeVoice wrapper to its supported microsoft/VibeVoice-Realtime-0.5B checkpoint.
Updated VibeVoice setup to use its required separate Python 3.13 environment, with optional winget installation.
Added safe ZIP extraction, corruption checks, staged wrapper replacement and atomic partial downloads.
Added central version.txt versioning for the app, installer and launcher.
Reworked the Windows installer to prefer offline wheels, verify package consistency and perform an off-screen GUI startup check before first launch.
Added build_wheelhouse.bat and tools/verify_installation.py.
Added configuration type/range/URL validation and migration for v2.1 profiles.
Hardened chat-session parsing and filenames against malformed or unsafe stored IDs.
Improved Ollama response validation and streaming error messages.
Fixed stop handling between externally generated TTS segments.
Updated every language pack with the new localizable UI keys.

v2.1 – 2026-07-21#

Added 20 user and 20 assistant personality presets plus the personality editor.

## Source

https://github.com/zeittresor/OllamaVibeDesk/
