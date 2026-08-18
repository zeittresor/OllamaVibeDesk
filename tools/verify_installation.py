from __future__ import annotations

import argparse
import ast
import ctypes
import importlib
import json
import os
import runpy
import sys
import tempfile
import wave
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate_sources() -> None:
    required = [
        ROOT / "version.txt",
        ROOT / "requirements.txt",
        ROOT / "app" / "main.py",
        ROOT / "app" / "config.py",
        ROOT / "app" / "tts_client.py",
        ROOT / "app" / "asr_client.py",
        ROOT / "app" / "audio_recorder.py",
        ROOT / "app" / "crispasr_runtime.py",
        ROOT / "app" / "speech_models.py",
        ROOT / "run_windows.bat",
        ROOT / "install_crispasr_windows.bat",
        ROOT / "tools" / "install_crispasr.ps1",
    ]
    for path in required:
        check(path.is_file(), f"Required file is missing: {path.relative_to(ROOT)}")

    version = (ROOT / "version.txt").read_text(encoding="utf-8").strip()
    parts = version.split(".")
    check(len(parts) == 3 and all(part.isdigit() for part in parts), "version.txt must contain a semantic X.Y.Z version")

    for path in sorted(ROOT.joinpath("app").glob("*.py")) + sorted(ROOT.joinpath("tools").glob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    language_files = sorted(ROOT.joinpath("lang").glob("*.json"))
    check(len(language_files) >= 2, "No language packs were found")
    packs = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in language_files}
    check("de" in packs and "en" in packs, "German and English language packs are required")
    expected_keys = set(packs["en"])
    for code, pack in packs.items():
        check(set(pack) == expected_keys, f"Language pack {code} has a different key set")

    for path in ROOT.joinpath("themes").glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    for path in ROOT.joinpath("resources").rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))

    assistant_presets = list(ROOT.joinpath("resources", "personalities", "assistant").glob("*.json"))
    user_presets = list(ROOT.joinpath("resources", "personalities", "user").glob("*.json"))
    check(len(assistant_presets) == 20, "Exactly 20 assistant personality presets are required")
    check(len(user_presets) == 20, "Exactly 20 user personality presets are required")


def validate_dependencies() -> None:
    for module_name in ("PyQt6", "requests", "markdown", "psutil"):
        importlib.import_module(module_name)
    from app.config import DEFAULT_CONFIG, normalize_config
    from app.tts_profiles import VOICE_STYLE_IDS
    from app.tts_client import TTSClient
    from app.tts_setup import VibeVoiceManager
    from app.speech_models import VIBEVOICE_ASR_MODELS, VIBEVOICE_TTS_MODELS, get_vibevoice_asr_model, get_vibevoice_tts_model
    from app.version import VERSION

    check(len(VOICE_STYLE_IDS) >= 8, "Voice style catalog is incomplete")
    check(normalize_config({"tts_backend": "invalid"})["tts_backend"] == "disabled", "Config validation failed")
    check(VERSION == (ROOT / "version.txt").read_text(encoding="utf-8").strip(), "Runtime version differs from version.txt")
    check(bool(DEFAULT_CONFIG.get("vibevoice_model_path")), "Default VibeVoice model path is missing")
    check(len(VIBEVOICE_ASR_MODELS) == 2 and len(VIBEVOICE_TTS_MODELS) == 2, "Verified VibeVoice model catalog is incomplete")
    check(get_vibevoice_asr_model("vibevoice_asr_7b").purpose == "asr", "Full VibeVoice ASR route is invalid")
    check(get_vibevoice_tts_model("vibevoice_1_5b").backend == "vibevoice-1.5b", "VibeVoice 1.5B TTS route is invalid")
    incompatible_rejected = False
    try:
        get_vibevoice_tts_model("vibevoice_asr_bitnet")
    except ValueError:
        incompatible_rejected = True
    check(incompatible_rejected, "An ASR model was accepted by the TTS catalog")

    with tempfile.TemporaryDirectory(prefix="ovd_verify_") as temp_dir:
        wav_path = Path(temp_dir) / "voice_style.wav"
        with wave.open(str(wav_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * 1600)
        client = TTSClient(
            backend="disabled",
            base_url="http://127.0.0.1:8880/v1",
            voice="",
            model="tts-1",
            windows_sapi_rate=3,
            windows_sapi_pitch=2,
            voice_style="robotic",
            voice_style_intensity=80,
        )
        client._apply_wav_voice_style(wav_path, external_backend=True)
        with wave.open(str(wav_path), "rb") as handle:
            check(handle.getnframes() > 0 and handle.getframerate() == 16000, "Local voice-style processing produced an invalid WAV")

        unsafe_zip = Path(temp_dir) / "unsafe.zip"
        extract_dir = Path(temp_dir) / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(unsafe_zip, "w") as archive:
            archive.writestr("../escaped.txt", "blocked")
        blocked = False
        try:
            with zipfile.ZipFile(unsafe_zip, "r") as archive:
                VibeVoiceManager._safe_extract_zip(archive, extract_dir)
        except RuntimeError:
            blocked = True
        check(blocked and not Path(temp_dir).joinpath("escaped.txt").exists(), "Unsafe ZIP traversal was not blocked")


def validate_gui() -> bool:
    if sys.platform.startswith("linux"):
        try:
            ctypes.CDLL("libEGL.so.1")
        except OSError:
            print("[SKIP] GUI construction (the Linux test host has no libEGL; Windows installer verification still requires GUI success)")
            return False
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from app.config import DEFAULT_CONFIG
    from app.main import SettingsDialog

    app = QApplication.instance() or QApplication([])
    config = dict(DEFAULT_CONFIG)
    config["tts_backend"] = "disabled"
    dialog = SettingsDialog(config, model_names=[])
    check(dialog.windowTitle() != "", "Settings dialog has no title")
    check(dialog.scroll.widgetResizable(), "Settings dialog is not responsive")
    check(dialog.tts_assistant_style.count() >= 8, "Assistant voice styles are missing from the GUI")
    check(dialog.tts_user_style.count() >= 8, "User voice styles are missing from the GUI")
    check(dialog.crispasr_tts_model.count() == 2, "Compatible CrispASR TTS choices are missing")
    check(dialog.asr_model.count() == 2, "Compatible VibeVoice ASR choices are missing")
    dialog.close()
    app.processEvents()
    return True


def validate_core_smoke() -> None:
    namespace = runpy.run_path(str(ROOT / "tests" / "smoke_core.py"))
    check(namespace["main"]() == 0, "Core smoke test failed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an OllamaVibeDesk source tree or completed installation.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--source-only", action="store_true", help="Validate only files, Python syntax and JSON assets.")
    mode.add_argument("--quick", action="store_true", help="Validate files and installed imports without constructing the GUI.")
    args = parser.parse_args()

    validate_sources()
    print("[OK] Source files, syntax, translations and resources")
    if not args.source_only:
        validate_dependencies()
        print("[OK] Installed Python dependencies and runtime configuration")
    if not args.source_only and not args.quick:
        validate_core_smoke()
        print("[OK] Core runtime smoke test")
        if validate_gui():
            print("[OK] Off-screen GUI construction and voice controls")
    print("OllamaVibeDesk installation verification passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
