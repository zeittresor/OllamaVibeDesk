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
EXPORTS_DIR = APP_DATA_DIR / "exports"
TTS_DIR = APP_DATA_DIR / "tts"
LANG_DIR = APP_ROOT / "lang"
SAPI_LEXICON_PATH = TTS_DIR / "sapi_lexicon.json"
AUTO_ANSWER_PATH = APP_DATA_DIR / "auto_answer_phrases.json"
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
    "tts_lexicon_enabled": True,
    "windows_sapi_lexicon_enabled": True,
    "tts_user_voice": "",
    "windows_sapi_rate": 0,
    "windows_sapi_pitch": 0,
    "windows_sapi_volume": 100,
    "interface_language": "de",
    "theme": "Midnight",
    "last_model": "",
    "system_prompt": "",
    "auto_answer_enabled": False,
    "read_all_include_names": False,
    "user_display_name": "",
    "assistant_display_name": "",
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
    SAPI_LEXICON_PATH.write_text(
        json.dumps(default_lexicon, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )



def ensure_default_auto_answer_phrases() -> None:
    if AUTO_ANSWER_PATH.exists():
        return

    default_data = {
        "enabled": True,
        "phrases": {
            "de": [
                "und hättest du konkrete verbesserungsvorschläge",
                "und bezogen auf die aktuellen krisen auf der welt wie beurteilst du das",
                "unglaublich, das ist ja heftig",
                "kannst du das noch etwas weiter ausführen",
                "welche folgen könnte das langfristig haben"
            ],
            "en": [
                "and would you have concrete suggestions for improvement",
                "and in light of the current crises in the world, how do you see that",
                "wow, that is intense",
                "could you expand on that a bit more",
                "what long-term consequences could that have"
            ],
            "fr": [
                "et aurais-tu des propositions d'amélioration concrètes",
                "et par rapport aux crises actuelles dans le monde, comment vois-tu cela",
                "incroyable, c'est intense",
                "peux-tu développer un peu plus",
                "quelles conséquences cela pourrait-il avoir à long terme"
            ],
            "es": [
                "y tendrías propuestas concretas de mejora",
                "y respecto a las crisis actuales del mundo, cómo lo valoras",
                "increíble, eso es fuerte",
                "podrías profundizar un poco más",
                "qué consecuencias podría tener a largo plazo"
            ],
            "ru": [
                "и какие конкретные улучшения ты бы предложил",
                "а если учитывать текущие мировые кризисы, как ты это оцениваешь",
                "невероятно, это сильно",
                "можешь раскрыть это чуть подробнее",
                "к каким долгосрочным последствиям это может привести"
            ]
        }
    }
    AUTO_ANSWER_PATH.write_text(
        json.dumps(default_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

def ensure_directories() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    LANG_DIR.mkdir(parents=True, exist_ok=True)
    ensure_default_sapi_lexicon()
    ensure_default_auto_answer_phrases()


def load_config() -> Dict[str, Any]:
    ensure_directories()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        if "tts_lexicon_enabled" not in data:
            merged["tts_lexicon_enabled"] = bool(data.get("windows_sapi_lexicon_enabled", DEFAULT_CONFIG["tts_lexicon_enabled"]))
        merged["windows_sapi_lexicon_enabled"] = bool(merged.get("tts_lexicon_enabled", True))
        if "tts_user_voice" not in data:
            merged["tts_user_voice"] = data.get("tts_voice", "")
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