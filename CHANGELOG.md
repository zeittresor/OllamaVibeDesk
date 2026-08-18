# Changelog

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
