# OllamaVibeDesk

Modern offline-first PyQt6 desktop GUI for a **local Ollama** instance, with **theme support**, **chat history**, **automatic chat**, **streaming responses**, and optional **local TTS playback/export** through a **VibeVoice compatible server**.


## Main features

- real Ollama integration via local API
- streamed assistant output
- model list refresh from the local Ollama API
- persistent chat sessions stored **inside the app folder**
- theme switching
- cancel/stop generation
- per-message **Vorlesen** action for assistant replies by voice
- optional WAV export via a local TTS endpoint
- Windows installer and launcher batch files
- no cloud requirement for normal chat usage once local services are present
- multiple interface language support (currently: DE/EN/ES/FR/HI/IT/JA/KO/NL/PL/PT/RU)
- different voice output speakers for human and AI (as Sapi or VibeVoice Speakers)
- automatic VibeVoice server setup included
- auto answer function to act like the human based of the ELIZA algorythm to automaticly continue a chat dialog
- Automatic Python code GUI program generation based on the current content of the conversation (sometimes) :-)

## Example with voice output (german language)

<img width="1416" height="945" alt="grafik" src="https://github.com/user-attachments/assets/ec2a2fc3-176a-46d1-9edd-a8e971a1d764" />

https://github.com/user-attachments/assets/e954e451-ed6e-4a08-b72f-f3dca99c49dd

Note: Using VibeVoice Mode takes some time to generate a voice output in contrast to the use of the default Windows Sapi.

## Folder layout

- `install_windows.bat` – creates a local virtual environment and installs Python packages for the GUI
- `run_windows.bat` – starts the GUI from the local venv
- `requirements.txt` – Python requirements for the GUI
- `app/` – application source
- `app_data/` – created on first run; contains config, chats, audio, cache, optional TTS helper data

## Requirements

- Windows 10/11
- Python 3.10+ for the GUI
- A running local Ollama instance
- One or more Ollama models already pulled locally

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


## Source

https://github.com/zeittresor/OllamaVibeDesk/
