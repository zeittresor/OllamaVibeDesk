from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from app.file_utils import atomic_write_text, backup_file
from app.tts_profiles import clamp_int, normalize_voice_style
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
AUDIO_DIR = APP_DATA_DIR / "audio"
CACHE_DIR = APP_DATA_DIR / "cache"
EXPORTS_DIR = APP_DATA_DIR / "exports"
GENERATED_CODE_DIR = APP_DATA_DIR / "generated_code"
DEBUG_LOG_DIR = APP_DATA_DIR / "debug_logs"
SETTINGS_PROFILE_DIR = APP_DATA_DIR / "config_profiles"
KNOWLEDGE_DIR = APP_DATA_DIR / "knowledge_base"
TTS_DIR = APP_DATA_DIR / "tts"
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
    "windows_sapi_rate": 0,
    "windows_sapi_pitch": 3,
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
    "last_model": "",
    "system_prompt": "",
    "auto_answer_enabled": True,
    "read_all_include_names": False,
    "user_display_name": "",
    "assistant_display_name": "",
    "strip_emojis_for_tts": True,
    "chat_max_tokens": 8192,
    "auto_answer_max_rounds": 0,
    "context_message_limit": 8,
    "hardware_auto_context": True,
    "ollama_num_ctx": 16384,
    "auto_answer_short_answers": True,
    "auto_answer_eliza_share": 30,
    "auto_answer_llm_share": 0,
    "auto_answer_llm_model": "",
    "auto_answer_llm_max_tokens": 160,
    "auto_answer_llm_system_prompt": "",
    "user_personality_id": "custom",
    "assistant_personality_id": "custom",
    "auto_answer_llm_include_recent_context": True,
    "auto_answer_phrase_repeat_lookback": 4,
    "rollover_carry_messages": 5,
    "auto_answer_short_instruction_overrides": {},
    "tts_voice_defaults_initialized": False,
    "debug_trace_enabled": False,
    "auto_thinking_for_code_requests": True,
    "auto_answer_use_question_replies_for_all": True,
    "allow_consecutive_auto_answer_dataset_reuse": False,
    "persistent_knowledge_enabled": False,
    "knowledge_source_path": "",
    "knowledge_retrieval_limit": 5,
    "knowledge_auto_capture_chats": True,
}


_BOOL_KEYS = {
    "autoplay_tts", "auto_read_assistant_responses", "auto_read_user_inputs",
    "tts_lexicon_enabled", "windows_sapi_lexicon_enabled", "auto_answer_enabled",
    "read_all_include_names", "strip_emojis_for_tts", "auto_answer_short_answers",
    "hardware_auto_context", "auto_answer_llm_include_recent_context",
    "tts_voice_defaults_initialized", "debug_trace_enabled",
    "auto_thinking_for_code_requests", "auto_answer_use_question_replies_for_all",
    "allow_consecutive_auto_answer_dataset_reuse", "persistent_knowledge_enabled",
    "knowledge_auto_capture_chats",
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
    "chat_max_tokens": (64, 262144),
    "auto_answer_max_rounds": (0, 100000),
    "context_message_limit": (6, 200),
    "ollama_num_ctx": (2048, 262144),
    "auto_answer_eliza_share": (0, 100),
    "auto_answer_llm_share": (0, 100),
    "auto_answer_llm_max_tokens": (32, 8192),
    "auto_answer_phrase_repeat_lookback": (1, 50),
    "rollover_carry_messages": (2, 40),
    "knowledge_retrieval_limit": (1, 12),
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

    for key in _BOOL_KEYS:
        merged[key] = _coerce_bool(merged.get(key), bool(DEFAULT_CONFIG.get(key, False)))
    for key, (minimum, maximum) in _INT_RANGES.items():
        merged[key] = clamp_int(merged.get(key), minimum, maximum, int(DEFAULT_CONFIG[key]))

    merged["ollama_base_url"] = _normalize_http_url(merged.get("ollama_base_url"), DEFAULT_CONFIG["ollama_base_url"])
    merged["tts_base_url"] = _normalize_http_url(merged.get("tts_base_url"), DEFAULT_CONFIG["tts_base_url"])
    merged["crispasr_tts_base_url"] = _normalize_http_url(merged.get("crispasr_tts_base_url"), DEFAULT_CONFIG["crispasr_tts_base_url"])
    merged["asr_base_url"] = _normalize_http_url(merged.get("asr_base_url"), DEFAULT_CONFIG["asr_base_url"])
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
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_CODE_DIR.mkdir(parents=True, exist_ok=True)
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
