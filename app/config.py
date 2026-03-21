from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = get_app_root()
APP_DATA_DIR = APP_ROOT / "app_data"
CHATS_DIR = APP_DATA_DIR / "chats"
AUDIO_DIR = APP_DATA_DIR / "audio"
CACHE_DIR = APP_DATA_DIR / "cache"
TTS_DIR = APP_DATA_DIR / "tts"
LANG_DIR = APP_ROOT / "lang"
SAPI_LEXICON_PATH = TTS_DIR / "sapi_lexicon.json"
CONFIG_PATH = APP_DATA_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "ollama_base_url": "http://127.0.0.1:11434",
    "tts_backend": "windows_sapi",
    "tts_base_url": "http://127.0.0.1:8880/v1",
    "tts_voice": "",
    "tts_model": "tts-1-hd",
    "tts_format": "wav",
    "autoplay_tts": True,
    "auto_read_assistant_responses": True,
    "windows_sapi_lexicon_enabled": False,
    "windows_sapi_rate": 0,
    "windows_sapi_pitch": 0,
    "windows_sapi_volume": 100,
    "interface_language": "de",
    "theme": "Midnight",
    "last_model": "",
    "system_prompt": "",
}


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
            }
        ]
    }
    SAPI_LEXICON_PATH.write_text(
        json.dumps(default_lexicon, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def ensure_directories() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    LANG_DIR.mkdir(parents=True, exist_ok=True)
    ensure_default_sapi_lexicon()


def load_config() -> Dict[str, Any]:
    ensure_directories()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        return merged
    except Exception:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    ensure_directories()
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )