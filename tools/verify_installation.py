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
import unittest
from pathlib import Path
from unittest.mock import patch

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
        ROOT / "app" / "reasoning.py",
        ROOT / "app" / "chat_titles.py",
        ROOT / "app" / "context_budget.py",
        ROOT / "app" / "project_archives.py",
        ROOT / "app" / "plugin_tools.py",
        ROOT / "app" / "conversation_language.py",
        ROOT / "app" / "adaptive_context.py",
        ROOT / "app" / "continuity.py",
        ROOT / "app" / "guidance_presets.py",
        ROOT / "app" / "audio_postproduction.py",
        ROOT / "app" / "answer_continuation.py",
        ROOT / "tests" / "test_context_policy.py",
        ROOT / "tests" / "test_project_plugins.py",
        ROOT / "tests" / "test_knowledge_wiki.py",
        ROOT / "tests" / "test_guidance_presets.py",
        ROOT / "tests" / "test_audio_postproduction.py",
        ROOT / "tests" / "test_answer_continuation.py",
        ROOT / "tests" / "smoke_gui_continuity.py",
        ROOT / "tools" / "build_release.py",
        ROOT / "tools" / "optional_default_model.py",
        ROOT / "tools" / "prepare_tiddlywiki.py",
        ROOT / "tests" / "test_optional_default_model.py",
        ROOT / "tests" / "smoke_ollama_api.py",
        ROOT / "run_windows.bat",
        ROOT / "install_crispasr_windows.bat",
        ROOT / "tools" / "install_crispasr.ps1",
    ]
    for path in required:
        check(path.is_file(), f"Required file is missing: {path.relative_to(ROOT)}")

    version = (ROOT / "version.txt").read_text(encoding="utf-8").strip()
    parts = version.split(".")
    check(len(parts) == 3 and all(part.isdigit() for part in parts), "version.txt must contain a semantic X.Y.Z version")
    main_source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    check("window.showMaximized()" in main_source, "The main application does not start maximized")
    check("def reset_chat_context" in main_source and "token_counter_label" in main_source,
          "Persistent token counter or manual context restart is missing")
    models_source = (ROOT / "app" / "models.py").read_text(encoding="utf-8")
    check("token_input_total" in models_source and "project_checkpoint" in models_source,
          "Token/project continuation metadata is not persisted")
    archives_source = (ROOT / "app" / "project_archives.py").read_text(encoding="utf-8")
    check("def restore_project_archive" in archives_source,
          "Safe project restoration for manual context restart is missing")
    config_source = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
    check('OUTPUTS_DIR = APP_ROOT / "OUTPUTS"' in config_source, "User outputs are not rooted in OUTPUTS")
    check('KNOWLEDGE_DIR = APP_DATA_DIR / "knowledge_base"' in config_source, "Knowledge storage must remain internal")

    for path in sorted(ROOT.joinpath("app").glob("*.py")) + sorted(ROOT.joinpath("tools").glob("*.py")) + sorted(ROOT.joinpath("tests").glob("*.py")):
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
    check(len(assistant_presets) == 35, "Exactly 35 assistant personality presets are required")
    check(len(user_presets) == 35, "Exactly 35 user personality presets are required")

    guidance_files = sorted(ROOT.joinpath("resources", "auto_answer", "guidance").glob("*.json"))
    check(len(guidance_files) == len(language_files), "A conversation-guidance catalog is missing")
    expected_guidance_ids = None
    for path in guidance_files:
        catalog = json.loads(path.read_text(encoding="utf-8"))
        ids = [str(item.get("id", "")) for item in catalog.get("presets", [])]
        check(len(ids) == 25 and len(set(ids)) == 25, f"Guidance catalog {path.stem} must contain 25 unique presets")
        check(len(catalog.get("templates", [])) >= 8, f"Guidance catalog {path.stem} has too few phrase templates")
        expected_guidance_ids = expected_guidance_ids or ids
        check(ids == expected_guidance_ids, f"Guidance catalog {path.stem} has a different preset set")


def validate_dependencies() -> None:
    for module_name in ("PyQt6", "requests", "markdown", "psutil"):
        importlib.import_module(module_name)
    from app.config import DEFAULT_CONFIG, normalize_config
    from app.ollama_client import OllamaClient
    from app.plugin_tools import PHYSICAL_CONFIRMATION_TOOLS, tool_schemas
    from app.speech_models import (
        VIBEVOICE_ASR_MODELS,
        VIBEVOICE_TTS_MODELS,
        get_vibevoice_asr_model,
        get_vibevoice_tts_model,
    )
    from app.tts_client import TTSClient
    from app.tts_profiles import VOICE_STYLE_IDS
    from app.tts_setup import VibeVoiceManager
    from app.version import VERSION
    from PyQt6.QtPositioning import QGeoPositionInfoSource

    check(len(VOICE_STYLE_IDS) >= 8, "Voice style catalog is incomplete")
    check(QGeoPositionInfoSource is not None, "Qt Positioning for optional local location tools is unavailable")
    check(normalize_config({'plugin_location_policy': 'unknown'})['plugin_location_policy'] == 'ask', "Invalid plugin policy was not reset")
    check(normalize_config({'plugin_printer_policy': 'allow_unattended'})['plugin_printer_policy'] == 'allow_unattended',
          "Unattended device permission cannot be saved")
    check(normalize_config({'plugin_location_policy': 'allow_unattended'})['plugin_location_policy'] == 'ask',
          "Unattended device permission leaked into another plugin")
    check(DEFAULT_CONFIG['auto_answer_context_restart_enabled'] is False
          and DEFAULT_CONFIG['auto_answer_context_review_percent'] == 78
          and DEFAULT_CONFIG['auto_answer_context_hard_percent'] == 92,
          "Autonomous Auto Answer context restart defaults are unsafe or incomplete")
    optional_tools = {item['function']['name'] for item in tool_schemas(normalize_config({
        'plugin_web_enabled': True, 'plugin_printer_enabled': True,
        'plugin_3d_printer_enabled': True, 'plugin_robotics_enabled': True,
    }))}
    check({'search_web', 'fetch_web_page', 'get_print_queue', 'print_file', 'submit_3d_print',
           'send_robot_command', 'emergency_stop_robot'} <= optional_tools,
          "Optional research, print, 3D-print or robotics tools are missing")
    check({'print_file', 'submit_3d_print', 'send_robot_command'} <= PHYSICAL_CONFIRMATION_TOOLS,
          "Physical output tools do not require a current confirmation")
    check(normalize_config({"tts_backend": "invalid"})["tts_backend"] == "disabled", "Config validation failed")
    check((ROOT / "version.txt").read_text(encoding="utf-8").strip() == VERSION, "Runtime version differs from version.txt")
    check(bool(DEFAULT_CONFIG.get("vibevoice_model_path")), "Default VibeVoice model path is missing")
    check(len(VIBEVOICE_ASR_MODELS) == 2 and len(VIBEVOICE_TTS_MODELS) == 2, "Verified VibeVoice model catalog is incomplete")
    check(get_vibevoice_asr_model("vibevoice_asr_7b").purpose == "asr", "Full VibeVoice ASR route is invalid")
    check(get_vibevoice_tts_model("vibevoice_1_5b").backend == "vibevoice-1.5b", "VibeVoice 1.5B TTS route is invalid")
    ollama_client = OllamaClient("http://127.0.0.1:11434")
    check(ollama_client._payload("qwen3:8b", [], think="high")["think"] == "high", "Reasoning level was not preserved")
    check(ollama_client._payload("qwen3:8b", [], think="off")["think"] is False, "Reasoning off was not preserved")
    check(ollama_client._think_fallback_attempts("low") == ["low", True, None], "Reasoning compatibility fallback is invalid")
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
            raise RuntimeError("GUI verification requires libEGL on Linux; install it or use --quick for explicitly limited checks") from None
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if sys.platform.startswith("win") and os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        # The Qt wheel no longer bundles a fonts directory. Its headless
        # platform can load the real Windows fonts instead of using missing
        # Qt defaults (which also distort widget size calculations).
        windows_fonts = Path(os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "C:/Windows") / "Fonts"
        if windows_fonts.is_dir():
            os.environ.setdefault("QT_QPA_FONTDIR", str(windows_fonts))
    from PyQt6.QtWidgets import QApplication

    from app import config as config_module
    from app.config import DEFAULT_CONFIG, PREFERRED_OLLAMA_MODEL
    from app.main import SettingsDialog
    from app.personality_editor import PersonalityEditorDialog

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
    check(dialog.reasoning_default_effort.count() == 5, "Default reasoning levels are missing")
    check(dialog.reasoning_model_effort.count() == 6, "Per-model reasoning overrides are incomplete")
    check(dialog.chat_max_tokens.value() == 65536 and dialog.chat_max_tokens.maximum() == 1000000,
          "Default or maximum reply token limit is incorrect")
    dialog.chat_max_tokens_slider.setValue(dialog.chat_max_tokens_slider.maximum())
    check(dialog.chat_max_tokens.value() == 1000000 and dialog.chat_max_tokens_slider_value.text() == '1M',
          "One-million-token slider setting is not connected to the input")
    check(dialog.auto_answer_eliza_share.value() == 15 and dialog.auto_answer_llm_share.value() == 50,
          "Auto Answer mix does not match the fresh-install defaults")
    dialog.context_limit.setValue(8)
    dialog.context_defaults_btn.click()
    check(dialog.context_limit.value() == 0 and dialog.rollover_carry_messages.value() == 0, "Adaptive defaults button failed")
    check(not dialog.auto_answer_short_answers.isChecked(), "Discussion defaults still force short replies")
    check(not dialog.audio_postproduction_enabled.isChecked()
          and not dialog.audio_postproduction_controls.isEnabled(),
          "Audio postproduction must be disabled on a fresh installation")
    check(dialog.auto_answer_guidance_preset.count() == 26,
          "Standard mode plus 25 conversation-guidance presets are not available")
    editor = PersonalityEditorDialog("de", lambda key, default: default, initial_role="assistant")
    check(editor.list_widget.count() == 35 and editor.parameter_spins["sensuality"].value() == 0,
          "New personality presets or optional character controls are missing")
    editor.parameter_spins["professionalism"].setValue(80)
    editor.parameter_spins["sensuality"].setValue(45)
    edited = editor._personality_from_fields()
    check(edited.parameters["professionalism"] == 80 and edited.parameters["sensuality"] == 45,
          "The character editor lost the additional parameter values")
    editor.close()
    dialog.assistant_personality_combo.setCurrentIndex(dialog.assistant_personality_combo.findData("valentina_charming_companion"))
    check("35/100" in dialog.system_prompt.toPlainText(),
          "An enabled optional character value is absent from the assistant prompt preview")
    dialog.assistant_personality_combo.setCurrentIndex(dialog.assistant_personality_combo.findData("ada_analytical_scientist"))
    check("romantisch" not in dialog.system_prompt.toPlainText().lower()
          and "flirt" not in dialog.system_prompt.toPlainText().lower(),
          "An inactive optional character value leaked into the assistant prompt preview")
    dialog.user_personality_combo.setCurrentIndex(dialog.user_personality_combo.findData("petra_charming_conversationalist"))
    check("30/100" in dialog.auto_answer_llm_system_prompt.toPlainText(),
          "An enabled optional character value is absent from the simulated user prompt preview")
    check(dialog.auto_answer_guidance_preset.currentData() == "standard"
          and dialog.auto_answer_guidance_strength.value() == 65,
          "Conversation-guidance defaults would alter existing Auto Answer behavior")
    check(not dialog.auto_answer_guidance_strength.isEnabled(),
          "Guidance strength must be inactive in standard mode")
    check(not dialog.auto_answer_context_restart.isChecked()
          and dialog.auto_answer_context_review_percent.value() == 78
          and dialog.auto_answer_context_hard_percent.value() == 92,
          "Autonomous context restart GUI defaults are incorrect")
    dialog.auto_answer_guidance_preset.setCurrentIndex(
        dialog.auto_answer_guidance_preset.findData("programming_tasks")
    )
    check(dialog.auto_answer_guidance_strength.isEnabled()
          and dialog.edit_guidance_phrases_btn.isEnabled(),
          "Selecting a guidance preset did not enable its controls")
    dialog.close()
    app.processEvents()
    first_model = 'deepseek-r1:14b'
    saved_settings = dict(DEFAULT_CONFIG, last_model=first_model, tts_backend='disabled')
    choices = [first_model, PREFERRED_OLLAMA_MODEL]
    edit = SettingsDialog(saved_settings, model_names=choices)
    check(edit.reasoning_model.currentText() == first_model, 'Initial reasoning model is incorrect')
    edit.reasoning_model.setCurrentText(PREFERRED_OLLAMA_MODEL)
    edit.reasoning_model_effort.setCurrentIndex(edit.reasoning_model_effort.findData('high'))
    check(edit.reasoning_model_effort.currentData() == 'high', 'Reasoning level could not be changed')
    check('GPT-OSS' not in edit.reasoning_model.toolTip() and 'GPT-OSS' not in edit.reasoning_model_effort.toolTip(),
          'Reasoning explanation still names an unrelated model')
    changed = edit.get_config()
    edit.auto_answer_guidance_preset.setCurrentIndex(
        edit.auto_answer_guidance_preset.findData("advanced_gui")
    )
    edit.auto_answer_guidance_strength.setValue(80)
    edit.audio_postproduction_enabled.setChecked(True)
    edit.audio_postproduction_chorus.setValue(25)
    edit.audio_postproduction_echo.setValue(45)
    edit.audio_postproduction_vocoder.setValue(15)
    edit.audio_postproduction_reverb.setValue(35)
    changed = edit.get_config()
    check(changed['reasoning_settings_model'] == PREFERRED_OLLAMA_MODEL
          and changed['model_reasoning_efforts'][PREFERRED_OLLAMA_MODEL] == 'high',
          'Reasoning model or level was lost when saving the dialog')
    check(changed['auto_answer_guidance_preset'] == 'advanced_gui'
          and changed['auto_answer_guidance_strength'] == 80,
          'Conversation-guidance settings were lost when saving the dialog')
    check(changed['audio_postproduction_enabled']
          and changed['audio_postproduction_echo'] == 45,
          'Audio postproduction settings were lost when saving the dialog')
    edit.close()
    with tempfile.TemporaryDirectory(prefix='ovd_settings_') as config_dir:
        with patch.object(config_module, 'CONFIG_PATH', Path(config_dir) / 'config.json'), \
             patch.object(config_module, 'ensure_directories', lambda: None):
            config_module.save_config(changed)
            reloaded = config_module.load_config()
    reopened = SettingsDialog(reloaded, model_names=choices)
    check(reopened.reasoning_model.currentText() == PREFERRED_OLLAMA_MODEL
          and reopened.reasoning_model_effort.currentData() == 'high',
          'Saved reasoning model and level did not survive reopening the settings')
    check(reopened.auto_answer_guidance_preset.currentData() == 'advanced_gui'
          and reopened.auto_answer_guidance_strength.value() == 80,
          'Saved conversation-guidance preset did not survive reopening the settings')
    check(reopened.audio_postproduction_enabled.isChecked()
          and reopened.audio_postproduction_echo.value() == 45,
          'Saved audio postproduction settings did not survive reopening the settings')
    imported = dict(changed, reasoning_settings_model=first_model,
                    model_reasoning_efforts={first_model: 'low', PREFERRED_OLLAMA_MODEL: 'high'})
    reopened.apply_config_to_widgets(imported)
    check(reopened.reasoning_model.currentText() == first_model
          and reopened.reasoning_model_effort.currentData() == 'low',
          'Loading a settings profile did not restore the selected model')
    reopened.close()
    app.processEvents()
    namespace = runpy.run_path(str(ROOT / "tests" / "smoke_gui_continuity.py"))
    check(namespace["main"]() == 0, "Main-window continuity integration test failed")
    return True


def validate_core_smoke() -> None:
    namespace = runpy.run_path(str(ROOT / "tests" / "smoke_core.py"))
    check(namespace["main"]() == 0, "Core smoke test failed")


def validate_ollama_api_smoke() -> None:
    namespace = runpy.run_path(str(ROOT / "tests" / "smoke_ollama_api.py"))
    check(namespace["main"]() == 0, "Ollama reasoning API smoke test failed")


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
        namespace = runpy.run_path(str(ROOT / "tests" / "test_context_policy.py"))
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(namespace["ContextPolicyTests"])
        check(unittest.TextTestRunner().run(suite).wasSuccessful(), "Adaptive context regression tests failed")
        plugins = runpy.run_path(str(ROOT / "tests" / "test_project_plugins.py"))
        plugin_suite = unittest.defaultTestLoader.loadTestsFromTestCase(plugins["ProjectPluginTests"])
        check(unittest.TextTestRunner().run(plugin_suite).wasSuccessful(), "Project archive and plugin regression tests failed")
        knowledge = runpy.run_path(str(ROOT / "tests" / "test_knowledge_wiki.py"))
        knowledge_suite = unittest.defaultTestLoader.loadTestsFromTestCase(knowledge["KnowledgeWikiTests"])
        check(unittest.TextTestRunner().run(knowledge_suite).wasSuccessful(), "Portable knowledge and wiki regression tests failed")
        offer = runpy.run_path(str(ROOT / "tests" / "test_optional_default_model.py"))
        offer_suite = unittest.defaultTestLoader.loadTestsFromTestCase(offer["DefaultModelTests"])
        check(unittest.TextTestRunner().run(offer_suite).wasSuccessful(), "Optional model installer checks failed")
        guidance = runpy.run_path(str(ROOT / "tests" / "test_guidance_presets.py"))
        guidance_suite = unittest.defaultTestLoader.loadTestsFromTestCase(guidance["GuidancePresetTests"])
        check(unittest.TextTestRunner().run(guidance_suite).wasSuccessful(), "Conversation-guidance regression tests failed")
        postproduction = runpy.run_path(str(ROOT / "tests" / "test_audio_postproduction.py"))
        postproduction_suite = unittest.defaultTestLoader.loadTestsFromTestCase(postproduction["AudioPostproductionTests"])
        check(unittest.TextTestRunner().run(postproduction_suite).wasSuccessful(), "Audio postproduction regression tests failed")
        completion = runpy.run_path(str(ROOT / "tests" / "test_answer_continuation.py"))
        completion_suite = unittest.defaultTestLoader.loadTestsFromTestCase(completion["AnswerContinuationTests"])
        check(unittest.TextTestRunner().run(completion_suite).wasSuccessful(), "Answer continuation regression tests failed")
        language = runpy.run_path(str(ROOT / "tests" / "test_conversation_language.py"))
        language_suite = unittest.defaultTestLoader.loadTestsFromTestCase(language["ConversationLanguageTests"])
        check(unittest.TextTestRunner().run(language_suite).wasSuccessful(), "Conversation-language regression tests failed")
        validate_ollama_api_smoke()
        print("[OK] Ollama reasoning request and compatibility fallback")
        if validate_gui():
            print("[OK] Off-screen GUI construction and voice controls")
    print("OllamaVibeDesk " + ("source-only validation" if args.source_only else "quick import validation (GUI not tested)" if args.quick else "full installation verification") + " passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1) from None
