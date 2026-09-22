# 2.4.1

- Persistierte Themenabschnitte direkt in der linken Chatliste auswählbar.
- Sprung zur gespeicherten Nachrichtenposition, auch nach erneutem Laden.
- Echte Folge-Chats und Vorgänger bleiben separat sichtbar.
- Keine weitere Begrenzung der Titelhistorie auf 64 Einträge.
- Qt-Regressionstest für mehrere Einträge, Auswahl, Scrollposition und Fortsetzen am Gesprächsende.

# Version 2.4.0 — 2026-09-21

- Tokenbudget statt acht Nachrichten als Standard; kein stilles Abschneiden der API-Historie.
- Hintergrundprüfung von Modellgrenze, laufendem Kontext, RAM und NVIDIA-VRAM; konservatives Wachstum, Lastreserve und Pause bei kritischem Speicher.
- Getrennte Steuerung pro Server/Modell, einmaliger OOM-/Kontextfehler-Retry mit kleinerem Kontext.
- Nach Budget übernommene Dialogeinträge und gekennzeichnete, quellenbezogene Übergabeauszüge; Originale bleiben erhalten.
- Dynamische Grundthema-/Schwerpunkttitel mit Nummer, Titelhistorie, Nachrichtenpositionen, Vorgänger-Navigation und Diagnoseansicht per Doppelklick.
- Auto-Answer-Rundenzähler und Anhänge über automatische Übergänge erhalten; Stop setzt geplante Fortsetzungen zurück.
- Auto-Answer-Worker beendet sich bei Abbruch zuverlässig; eigene Modellbudgets und begrenzte Ausgabe.
- Ollama-HTTP-Fehlertexte bleiben für die Speicherdiagnose erhalten; unterbrochene Streams gelten nicht mehr als vollständige Antworten; keine blinde zweite Anfrage bei leerem Stream.
- Native Tokenstatistiken verbessern die modellbezogene Schätzreserve; CJK-/UTF-8-Schätzung korrigiert.
- Neue Defaults: automatische Übernahme, 32k-Obergrenze, kein erzwungener Kurzstil, 512 Token für Auto-Answer-LLM und neutrale Assistentenstimmhöhe. Vorhandene individuelle Einstellungen bleiben bestehen.
- GUI-Limit des Auto-Answer-Modells entspricht jetzt der Konfigurationsgrenze 8192.
- Chatlisten-Cache, vollständige Qt-Integrationstests, klare Teilprüfungsberichte und reproduzierbarer ZIP-Build ohne Benutzerdaten.
- Installer verwendet intakte lokale Pakete wieder, prüft 64-Bit-Python und erhält den Rückgabecode der GUI-Prüfung. Wheelhouse-Build verwendet nur Binärpakete.

# Changelog

## v2.3.0 – 2026-09-01

- Added per-model Ollama Reasoning/Thinking settings: Off, automatic for code, Low, Medium and High.
- Applied the selected model's reasoning level consistently to normal chat and the Auto-Answer LLM path.
- Replaced the narrow Qwen-specific Thinking switch with native Ollama `think` levels for compatible model families.
- Added safe compatibility retries for older Ollama runtimes: level, boolean Thinking, then omission of the unsupported field.
- Added a local Ollama API integration smoke test covering streamed thinking, content and compatibility fallback.
- Added topic-aware automatic continuation titles derived locally from the latest conversation section.
- Added localized, numbered continuation suffixes and persisted parent/index/topic metadata for every rollover chat.
- Fixed premature rollover caused by reserving the full configured maximum response length for every request.
- Added pure context-budget regressions so short prompts no longer create unnecessary follow-up chats.
- Expanded installation verification for the new modules, reasoning controls and API request behavior.

## v2.2.0 – 2026-08-18

- Added separate assistant and user voice profiles, intensity, speaking rate, pitch and volume.
- Added natural, deep/masculine, bright/feminine, narrator, dramatic, robotic, tipsy, comic and whisper profiles.
- Added dependency-free local WAV character effects and VibeVoice fallback modulation.
- Added atomic TTS audio writes, response-type validation and rejection of JSON/HTML error bodies saved as audio.
- Added VibeVoice microphone input through the OpenAI-compatible CrispASR transcription endpoint.
- Added a closed, runtime-verified speech-model catalog: full multilingual VibeVoice ASR, VibeVoice ASR BitNet, Realtime 0.5B GGUF TTS and VibeVoice 1.5B GGUF TTS.
- Added strict task/runtime/backend validation so ASR checkpoints, realtime voice packs and 1.5B TTS are never mixed incompatibly.
- Added a separate CrispASR Windows installer with CPU-legacy default (no AVX2 assumption), plus optional CPU, Vulkan and CUDA variants.
- Restricted the Python VibeVoice wrapper to its supported `microsoft/VibeVoice-Realtime-0.5B` checkpoint.
- Updated VibeVoice setup to use its required separate Python 3.13 environment, with optional winget installation.
- Added safe ZIP extraction, corruption checks, staged wrapper replacement and atomic partial downloads.
- Added central `version.txt` versioning for the app, installer and launcher.
- Reworked the Windows installer to prefer offline wheels, verify package consistency and perform an off-screen GUI startup check before first launch.
- Added `build_wheelhouse.bat` and `tools/verify_installation.py`.
- Added configuration type/range/URL validation and migration for v2.1 profiles.
- Hardened chat-session parsing and filenames against malformed or unsafe stored IDs.
- Improved Ollama response validation and streaming error messages.
- Fixed stop handling between externally generated TTS segments.
- Updated every language pack with the new localizable UI keys.

## v2.1 – 2026-07-21

- Added 20 user and 20 assistant personality presets plus the personality editor.
