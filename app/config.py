from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from app.file_utils import atomic_write_text, backup_file
from app.tts_profiles import clamp_int, normalize_voice_style
from app.reasoning import normalize_model_reasoning_efforts, normalize_reasoning_effort
from app.speech_models import (
    PYTHON_REALTIME_TTS_MODEL,
    normalize_vibevoice_asr_model,
    normalize_vibevoice_tts_model,
)


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = get_app_root()
APP_DATA_DIR = APP_ROOT / "app_data"
CHATS_DIR = APP_DATA_DIR / "chats"
CACHE_DIR = APP_DATA_DIR / "cache"
DEBUG_LOG_DIR = APP_DATA_DIR / "debug_logs"
SETTINGS_PROFILE_DIR = APP_DATA_DIR / "config_profiles"
KNOWLEDGE_DIR = APP_DATA_DIR / "knowledge_base"
TTS_DIR = APP_DATA_DIR / "tts"
ATTACHMENTS_DIR = APP_DATA_DIR / "attachments"
OUTPUTS_DIR = APP_ROOT / "OUTPUTS"
AUDIO_DIR = OUTPUTS_DIR / "audio" / "tts"
VOICE_INPUT_DIR = OUTPUTS_DIR / "audio" / "recordings"
EXPORTS_DIR = OUTPUTS_DIR / "chat_exports"
GENERATED_CODE_DIR = OUTPUTS_DIR / "code_blocks"
PROJECTS_DIR = OUTPUTS_DIR / "projects"
PROJECT_WORKSPACES_DIR = PROJECTS_DIR / "workspaces"
LANG_DIR = APP_ROOT / "lang"
THEMES_DIR = APP_ROOT / "themes"
AUTO_ANSWER_DIR = APP_DATA_DIR / "auto_answer"
AUTO_ANSWER_PHRASES_DIR = AUTO_ANSWER_DIR / "phrases"
AUTO_ANSWER_TOPIC_WORDS_DIR = AUTO_ANSWER_DIR / "topic_words"
AUTO_ANSWER_QUESTION_REPLIES_DIR = AUTO_ANSWER_DIR / "question_replies"
PERSONALITIES_RESOURCE_DIR = APP_ROOT / "resources" / "personalities"
PERSONALITIES_DIR = APP_DATA_DIR / "personalities"
PERSONALITIES_USER_DIR = PERSONALITIES_DIR / "user"
PERSONALITIES_ASSISTANT_DIR = PERSONALITIES_DIR / "assistant"
SAPI_LEXICON_PATH = TTS_DIR / "sapi_lexicon.json"
CONFIG_PATH = APP_DATA_DIR / "config.json"
PREFERRED_OLLAMA_MODEL = "hf.co/mradermacher/Huihui-Qwen3.8-27B-abliterated-GGUF:Q3_K_M"

DEFAULT_CONFIG: Dict[str, Any] = {
    "ollama_base_url": "http://127.0.0.1:11434",
    "ollama_executable_path": "",
    "tts_backend": "windows_sapi",
    "tts_base_url": "http://127.0.0.1:8880/v1",
    "tts_voice": "",
    "tts_model": "tts-1-hd",
    "vibevoice_model_path": PYTHON_REALTIME_TTS_MODEL,
    "vibevoice_crisp_tts_model": "vibevoice_realtime_0_5b",
    "crispasr_tts_base_url": "http://127.0.0.1:8881/v1",
    "crispasr_executable_path": "",
    "tts_format": "wav",
    "autoplay_tts": True,
    "auto_read_assistant_responses": True,
    "auto_read_user_inputs": True,
    "tts_lexicon_enabled": True,
    "windows_sapi_lexicon_enabled": True,
    "tts_user_voice": "",
    "tts_assistant_style": "natural",
    "tts_user_style": "natural",
    "tts_assistant_style_intensity": 65,
    "tts_user_style_intensity": 65,
    "audio_postproduction_enabled": False,
    "audio_postproduction_chorus": 0,
    "audio_postproduction_echo": 0,
    "audio_postproduction_vocoder": 0,
    "audio_postproduction_reverb": 0,
    "windows_sapi_rate": 0,
    "windows_sapi_pitch": 0,
    "windows_sapi_volume": 100,
    "windows_sapi_user_rate": 0,
    "windows_sapi_user_pitch": 0,
    "windows_sapi_user_volume": 100,
    "asr_backend": "disabled",
    "asr_base_url": "http://127.0.0.1:8882/v1",
    "asr_model": "vibevoice_asr_7b",
    "asr_language": "auto",
    "interface_language": "de",
    "theme": "Midnight",
    "last_model": PREFERRED_OLLAMA_MODEL,
    "system_prompt": "",
    "auto_answer_enabled": True,
    "read_all_include_names": False,
    "user_display_name": "",
    "assistant_display_name": "",
    "strip_emojis_for_tts": True,
    "chat_max_tokens": 65536,
    "auto_answer_max_rounds": 0,
    "context_message_limit": 0,
    "hardware_auto_context": True,
    "context_policy_version": 24,
    "ollama_num_ctx": 32768,
    "auto_answer_short_answers": False,
    "auto_answer_eliza_share": 15,
    "auto_answer_llm_share": 50,
    "auto_answer_llm_model": "",
    "auto_answer_llm_max_tokens": 512,
    "auto_answer_llm_system_prompt": "",
    "user_personality_id": "custom",
    "assistant_personality_id": "custom",
    "auto_answer_llm_include_recent_context": True,
    "auto_answer_context_restart_enabled": False,
    "auto_answer_context_review_percent": 78,
    "auto_answer_context_hard_percent": 92,
    "auto_answer_phrase_repeat_lookback": 4,
    "rollover_carry_messages": 0,
    "auto_answer_short_instruction_overrides": {},
    "tts_voice_defaults_initialized": False,
    "debug_trace_enabled": False,
    "auto_thinking_for_code_requests": True,
    "reasoning_default_effort": "auto",
    "model_reasoning_efforts": {},
    "reasoning_settings_model": "",
    "auto_answer_use_question_replies_for_all": True,
    "allow_consecutive_auto_answer_dataset_reuse": False,
    "auto_answer_guidance_preset": "standard",
    "auto_answer_guidance_strength": 65,
    "auto_answer_guidance_apply_to_phrases": True,
    "auto_answer_guidance_apply_to_llm": True,
    "persistent_knowledge_enabled": False,
    "knowledge_source_path": "",
    "knowledge_retrieval_limit": 5,
    "knowledge_auto_capture_chats": True,
    "sidebar_width": 320,
    "sidebar_hidden": False,
    "plugin_commandline_enabled": False,
    "plugin_powershell_enabled": False,
    "plugin_vision_enabled": False,
    "plugin_webcam_enabled": False,
    "plugin_sensors_enabled": False,
    "plugin_location_enabled": False,
    "plugin_web_enabled": False,
    "plugin_printer_enabled": False,
    "plugin_3d_printer_enabled": False,
    "plugin_robotics_enabled": False,
    "plugin_commandline_policy": "ask",
    "plugin_powershell_policy": "ask",
    "plugin_sensors_policy": "ask",
    "plugin_location_policy": "ask",
    "plugin_vision_policy": "ask",
    "plugin_webcam_policy": "ask",
    "plugin_web_policy": "ask",
    "plugin_printer_policy": "ask",
    "plugin_3d_printer_policy": "ask",
    "plugin_robotics_policy": "ask",
    "plugin_3d_printer_url": "http://127.0.0.1:5000",
    "plugin_3d_printer_api_key": "",
    "plugin_robotics_url": "http://127.0.0.1:8765",
}


_BOOL_KEYS = {
    "autoplay_tts", "auto_read_assistant_responses", "auto_read_user_inputs",
    "tts_lexicon_enabled", "windows_sapi_lexicon_enabled", "auto_answer_enabled",
    "read_all_include_names", "strip_emojis_for_tts", "auto_answer_short_answers",
    "hardware_auto_context", "auto_answer_llm_include_recent_context",
    "auto_answer_context_restart_enabled",
    "tts_voice_defaults_initialized", "debug_trace_enabled",
    "auto_thinking_for_code_requests", "auto_answer_use_question_replies_for_all",
    "allow_consecutive_auto_answer_dataset_reuse", "persistent_knowledge_enabled",
    "auto_answer_guidance_apply_to_phrases", "auto_answer_guidance_apply_to_llm",
    "audio_postproduction_enabled",
    "knowledge_auto_capture_chats",
    "sidebar_hidden", "plugin_commandline_enabled", "plugin_powershell_enabled",
    "plugin_vision_enabled", "plugin_webcam_enabled", "plugin_sensors_enabled", "plugin_location_enabled",
    "plugin_web_enabled", "plugin_printer_enabled", "plugin_3d_printer_enabled", "plugin_robotics_enabled",
}

_INT_RANGES = {
    "windows_sapi_rate": (-10, 10),
    "windows_sapi_pitch": (-10, 10),
    "windows_sapi_volume": (0, 100),
    "windows_sapi_user_rate": (-10, 10),
    "windows_sapi_user_pitch": (-10, 10),
    "windows_sapi_user_volume": (0, 100),
    "tts_assistant_style_intensity": (0, 100),
    "tts_user_style_intensity": (0, 100),
    "audio_postproduction_chorus": (0, 100),
    "audio_postproduction_echo": (0, 100),
    "audio_postproduction_vocoder": (0, 100),
    "audio_postproduction_reverb": (0, 100),
    "chat_max_tokens": (64, 1000000),
    "auto_answer_max_rounds": (0, 100000),
    "context_message_limit": (0, 10000),
    "ollama_num_ctx": (2048, 262144),
    "auto_answer_eliza_share": (0, 100),
    "auto_answer_llm_share": (0, 100),
    "auto_answer_llm_max_tokens": (32, 8192),
    "auto_answer_context_review_percent": (50, 90),
    "auto_answer_context_hard_percent": (60, 99),
    "auto_answer_phrase_repeat_lookback": (1, 50),
    "auto_answer_guidance_strength": (0, 100),
    "rollover_carry_messages": (0, 200),
    "knowledge_retrieval_limit": (1, 12),
    "sidebar_width": (230, 800),
}


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().casefold()
    if text in {"1", "true", "yes", "on", "ja"}:
        return True
    if text in {"0", "false", "no", "off", "nein", ""}:
        return False
    return default


def _normalize_http_url(value: object, default: str) -> str:
    text = str(value or "").strip().rstrip("/")
    try:
        parsed = urlparse(text)
    except ValueError:
        return default
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return default
    return text


def normalize_config(data: object) -> Dict[str, Any]:
    """Migrate and validate persisted settings without discarding future keys."""
    incoming = data if isinstance(data, dict) else {}
    merged: Dict[str, Any] = DEFAULT_CONFIG.copy()
    merged.update(incoming)
    # Migrate only legacy automatic defaults; explicit custom limits remain intact.
    if incoming.get("context_policy_version") != 24 and _coerce_bool(incoming.get("hardware_auto_context", True), True):
        if incoming.get("context_message_limit") == 8:
            merged["context_message_limit"] = 0
        if incoming.get("rollover_carry_messages") == 5:
            merged["rollover_carry_messages"] = 0
    merged["context_policy_version"] = 24

    for key in _BOOL_KEYS:
        merged[key] = _coerce_bool(merged.get(key), bool(DEFAULT_CONFIG.get(key, False)))
    for plugin in ('commandline', 'powershell', 'sensors', 'location', 'vision', 'webcam',
                   'web', 'printer', '3d_printer', 'robotics'):
        key = f'plugin_{plugin}_policy'
        value = str(merged.get(key, 'ask') or 'ask').strip().lower()
        allowed = {'ask', 'deny', 'allow'}
        if plugin in {'printer', '3d_printer', 'robotics'}:
            allowed.add('allow_unattended')
        merged[key] = value if value in allowed else 'ask'
    for key, (minimum, maximum) in _INT_RANGES.items():
        merged[key] = clamp_int(merged.get(key), minimum, maximum, int(DEFAULT_CONFIG[key]))

    merged["ollama_base_url"] = _normalize_http_url(merged.get("ollama_base_url"), DEFAULT_CONFIG["ollama_base_url"])
    merged["tts_base_url"] = _normalize_http_url(merged.get("tts_base_url"), DEFAULT_CONFIG["tts_base_url"])
    merged["crispasr_tts_base_url"] = _normalize_http_url(merged.get("crispasr_tts_base_url"), DEFAULT_CONFIG["crispasr_tts_base_url"])
    merged["asr_base_url"] = _normalize_http_url(merged.get("asr_base_url"), DEFAULT_CONFIG["asr_base_url"])
    merged["plugin_3d_printer_url"] = _normalize_http_url(
        merged.get("plugin_3d_printer_url"), DEFAULT_CONFIG["plugin_3d_printer_url"])
    merged["plugin_robotics_url"] = _normalize_http_url(
        merged.get("plugin_robotics_url"), DEFAULT_CONFIG["plugin_robotics_url"])
    api_key = str(merged.get("plugin_3d_printer_api_key", "") or "").strip()
    merged["plugin_3d_printer_api_key"] = api_key[:512] if not any(char in api_key for char in "\r\n\0") else ""
    backend = str(merged.get("tts_backend", "disabled") or "disabled").strip()
    merged["tts_backend"] = backend if backend in {"disabled", "windows_sapi", "vibevoice_openai", "crispasr_openai"} else "disabled"
    asr_backend = str(merged.get("asr_backend", "disabled") or "disabled").strip()
    merged["asr_backend"] = asr_backend if asr_backend in {"disabled", "crispasr_vibevoice"} else "disabled"
    merged["tts_assistant_style"] = normalize_voice_style(merged.get("tts_assistant_style"))
    merged["tts_user_style"] = normalize_voice_style(merged.get("tts_user_style"))
    model_path = str(merged.get("vibevoice_model_path", DEFAULT_CONFIG["vibevoice_model_path"]) or "").strip()
    if not model_path or any(char in model_path for char in "\r\n\0"):
        model_path = PYTHON_REALTIME_TTS_MODEL
    # The bundled Python streaming wrapper loads this exact architecture only.
    # Alternative VibeVoice models are exposed through the CrispASR catalog.
    if model_path != PYTHON_REALTIME_TTS_MODEL:
        model_path = PYTHON_REALTIME_TTS_MODEL
    merged["vibevoice_model_path"] = model_path
    merged["vibevoice_crisp_tts_model"] = normalize_vibevoice_tts_model(merged.get("vibevoice_crisp_tts_model"))
    if merged["tts_backend"] == "crispasr_openai":
        crisp_default_voice = "default" if merged["vibevoice_crisp_tts_model"] == "vibevoice_1_5b" else "Emma"
        for voice_key in ("tts_voice", "tts_user_voice"):
            voice_value = str(merged.get(voice_key, "") or "").strip()
            if not voice_value or voice_value.startswith(("sapi::", "onecore::")):
                merged[voice_key] = crisp_default_voice
    merged["asr_model"] = normalize_vibevoice_asr_model(merged.get("asr_model"))
    asr_language = str(merged.get("asr_language", "auto") or "auto").strip().lower()
    merged["asr_language"] = asr_language if re.fullmatch(r"auto|[a-z]{2,3}", asr_language) else "auto"
    if merged["asr_model"] == "vibevoice_asr_bitnet" and merged["asr_language"] not in {"auto", "en", "zh", "fr", "it", "ko", "pt", "vi"}:
        merged["asr_language"] = "auto"
    executable_path = str(merged.get("crispasr_executable_path", "") or "").strip()
    merged["crispasr_executable_path"] = "" if any(char in executable_path for char in "\r\n\0") else executable_path

    # v2.2 exposed only a code-specific Thinking checkbox. Preserve that
    # behavior as the new per-model "auto" default when migrating old files.
    if "reasoning_default_effort" not in incoming:
        legacy_auto = _coerce_bool(incoming.get("auto_thinking_for_code_requests", True), True)
        merged["reasoning_default_effort"] = "auto" if legacy_auto else "off"
    else:
        merged["reasoning_default_effort"] = normalize_reasoning_effort(
            merged.get("reasoning_default_effort"), DEFAULT_CONFIG["reasoning_default_effort"]
        )
    merged["model_reasoning_efforts"] = normalize_model_reasoning_efforts(
        merged.get("model_reasoning_efforts", {})
    )
    reasoning_settings_model = str(merged.get("reasoning_settings_model", "") or "").strip()
    merged["reasoning_settings_model"] = (
        reasoning_settings_model if len(reasoning_settings_model) <= 240
        and not any(char in reasoning_settings_model for char in "\r\n\0") else ""
    )
    guidance_preset = str(merged.get("auto_answer_guidance_preset", "standard") or "standard").strip().lower()
    merged["auto_answer_guidance_preset"] = (
        guidance_preset if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", guidance_preset) else "standard"
    )

    # v2.1 only had one set of SAPI controls. Preserve it for the assistant and
    # initialize the user role independently when loading older profiles.
    if "windows_sapi_user_rate" not in incoming:
        merged["windows_sapi_user_rate"] = 0
    if "windows_sapi_user_pitch" not in incoming:
        merged["windows_sapi_user_pitch"] = 0
    if "windows_sapi_user_volume" not in incoming:
        merged["windows_sapi_user_volume"] = merged["windows_sapi_volume"]

    if "tts_lexicon_enabled" not in incoming:
        merged["tts_lexicon_enabled"] = _coerce_bool(
            incoming.get("windows_sapi_lexicon_enabled", DEFAULT_CONFIG["tts_lexicon_enabled"]),
            bool(DEFAULT_CONFIG["tts_lexicon_enabled"]),
        )
    merged["windows_sapi_lexicon_enabled"] = bool(merged["tts_lexicon_enabled"])
    if "tts_user_voice" not in incoming:
        merged["tts_user_voice"] = str(incoming.get("tts_voice", "") or "")

    # ELIZA + LLM may never exceed 100%; random phrases receive the remainder.
    eliza = int(merged["auto_answer_eliza_share"])
    llm = int(merged["auto_answer_llm_share"])
    if eliza + llm > 100:
        merged["auto_answer_llm_share"] = max(0, 100 - eliza)
    # The deterministic safety limit must always remain above the point at
    # which the optional model review begins.
    review_percent = int(merged["auto_answer_context_review_percent"])
    hard_percent = int(merged["auto_answer_context_hard_percent"])
    merged["auto_answer_context_hard_percent"] = max(review_percent + 5, hard_percent)
    return merged


def ensure_default_sapi_lexicon() -> None:
    if SAPI_LEXICON_PATH.exists():
        return

    default_lexicon = {
        "enabled": True,
        "language": "de-DE",
        "entries": [
            {
                "type": "word",
                "from": "GUI",
                "to": "G U I",
                "case_sensitive": False
            },
            {
                "type": "word",
                "from": "TTS",
                "to": "T T S",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "PyQt6",
                "to": "Pei Kju Ti sechs",
                "case_sensitive": False
            },
            {
                "type": "word",
                "from": "Ollama",
                "to": "Olama",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "z. b.",
                "to": "zum beispiel",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "z.B.",
                "to": "zum beispiel",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "d. h.",
                "to": "das heißt",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "d.h.",
                "to": "das heißt",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "u. a.",
                "to": "unter anderem",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "u.a.",
                "to": "unter anderem",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "usw.",
                "to": "und so weiter",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "ca.",
                "to": "circa",
                "case_sensitive": False
            },
            {
                "type": "phrase",
                "from": "bzw.",
                "to": "beziehungsweise",
                "case_sensitive": False
            }
        ]
    }
    atomic_write_text(
        SAPI_LEXICON_PATH,
        json.dumps(default_lexicon, indent=2, ensure_ascii=False),
    )



def ensure_default_auto_answer_phrases() -> None:
    from app.auto_answer_data import ensure_auto_answer_data
    ensure_auto_answer_data()


def ensure_default_auto_answer_question_replies() -> None:
    from app.auto_answer_data import ensure_auto_answer_data
    ensure_auto_answer_data()


def ensure_directories() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    VOICE_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_CODE_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    (PROJECTS_DIR / "zips").mkdir(parents=True, exist_ok=True)
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    LANG_DIR.mkdir(parents=True, exist_ok=True)
    THEMES_DIR.mkdir(parents=True, exist_ok=True)
    AUTO_ANSWER_PHRASES_DIR.mkdir(parents=True, exist_ok=True)
    AUTO_ANSWER_TOPIC_WORDS_DIR.mkdir(parents=True, exist_ok=True)
    AUTO_ANSWER_QUESTION_REPLIES_DIR.mkdir(parents=True, exist_ok=True)
    PERSONALITIES_USER_DIR.mkdir(parents=True, exist_ok=True)
    PERSONALITIES_ASSISTANT_DIR.mkdir(parents=True, exist_ok=True)
    output_readme = OUTPUTS_DIR / "README.txt"
    if not output_readme.exists():
        atomic_write_text(output_readme, (
            "OllamaVibeDesk-Ausgaben\n"
            "========================\n\n"
            "code_blocks/       einzeln erkannte, abgeschlossene Codeblöcke\n"
            "projects/zips/     zusammengehörige, versionierte Projektarchive\n"
            "projects/workspaces/ durch lokale Werkzeuge erzeugte Projektdateien\n"
            "audio/tts/         erzeugte Sprachausgabe und Nachbearbeitungen\n"
            "audio/recordings/  bewusst gestartete Mikrofonaufnahmen\n"
            "chat_exports/      exportierte Chat-Dokumente\n\n"
            "Interne Daten wie Chats, Einstellungen und Wissensquellen verbleiben in app_data.\n"
            "Ausgaben älterer Versionen werden nicht automatisch verschoben oder gelöscht.\n"
        ))
    ensure_default_sapi_lexicon()
    ensure_default_auto_answer_phrases()
    ensure_default_auto_answer_question_replies()


def load_config() -> Dict[str, Any]:
    ensure_directories()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return normalize_config(DEFAULT_CONFIG)

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return normalize_config(data)
    except Exception:
        backup_file(CONFIG_PATH, label="invalid")
        save_config(DEFAULT_CONFIG)
        return normalize_config(DEFAULT_CONFIG)


def save_config(config: Dict[str, Any]) -> None:
    ensure_directories()
    atomic_write_text(
        CONFIG_PATH,
        json.dumps(normalize_config(config), indent=2, ensure_ascii=False),
    )
