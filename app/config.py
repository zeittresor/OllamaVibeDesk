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
GENERATED_CODE_DIR = APP_DATA_DIR / "generated_code"
DEBUG_LOG_DIR = APP_DATA_DIR / "debug_logs"
SETTINGS_PROFILE_DIR = APP_DATA_DIR / "config_profiles"
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
    "auto_read_user_inputs": False,
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
    "strip_emojis_for_tts": True,
    "chat_max_tokens": 512,
    "auto_answer_max_rounds": 0,
    "context_message_limit": 8,
    "auto_answer_short_answers": True,
    "auto_answer_eliza_share": 30,
    "auto_answer_phrase_repeat_lookback": 1,
    "rollover_carry_messages": 5,
    "auto_answer_short_instruction_overrides": {},
    "tts_voice_defaults_initialized": False,
    "debug_trace_enabled": False,
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
    default_data = {
        "enabled": True,
        "phrases": {
            "de": [
                "und hättest du konkrete verbesserungsvorschläge",
                "und bezogen auf die aktuellen krisen auf der welt wie beurteilst du das",
                "unglaublich, das ist ja heftig",
                "kannst du das noch etwas weiter ausführen",
                "welche folgen könnte das langfristig haben",
                "und wenn du das in die richtung @@@ weiter denkst ?",
                "und im bezug auf @@@ ?",
                "und was würde das bei @@@ verändern ?",
                "erstell deine bisherige sichtweise mal bitte mit python als code mit GUI (ohne mich nach details zu fragen) die nicht nur rein textbasierend verdeutlicht was du meinst (gern mit extra funktionen die dir relevant erscheinen und den requirements als kommentar im code ohne dafür eine extra datei zu erstellen). komme anschliessend bitte zurück zu mir auf die ebene auf der wir und jetzt gerade unterhalten"
            ],
            "en": [
                "and would you have concrete suggestions for improvement",
                "and in light of the current crises in the world, how do you see that",
                "wow, that is intense",
                "could you expand on that a bit more",
                "what long-term consequences could that have",
                "and what if you think that further in the direction of @@@?",
                "and in relation to @@@?",
                "and what would that change about @@@?",
                "please create your current point of view as Python code with a GUI (without asking me for details) so that it illustrates what you mean in a way that is not purely text-based, including any extra functions you consider relevant and the requirements as comments in the code without creating a separate file for them. Afterwards, please return to the level on which we are talking right now"
            ],
            "fr": [
                "et aurais-tu des propositions d'amélioration concrètes",
                "et par rapport aux crises actuelles dans le monde, comment vois-tu cela",
                "incroyable, c'est intense",
                "peux-tu développer un peu plus",
                "quelles conséquences cela pourrait-il avoir à long terme",
                "et si tu poussais cela davantage dans la direction de @@@ ?",
                "et par rapport à @@@ ?",
                "et qu'est-ce que cela changerait concernant @@@ ?",
                "merci de créer ton point de vue actuel en code Python avec une interface graphique (sans me demander de détails), de manière à illustrer ce que tu veux dire autrement que par du simple texte, avec volontiers des fonctions supplémentaires que tu juges pertinentes et les requirements en commentaire dans le code sans créer de fichier séparé. Ensuite, reviens s'il te plaît au niveau sur lequel nous parlons en ce moment"
            ],
            "es": [
                "y tendrías propuestas concretas de mejora",
                "y respecto a las crisis actuales del mundo, cómo lo valoras",
                "increíble, eso es fuerte",
                "podrías profundizar un poco más",
                "qué consecuencias podría tener a largo plazo",
                "y si lo pensaras más en la dirección de @@@ ?",
                "y con respecto a @@@ ?",
                "y qué cambiaría eso en relación con @@@ ?",
                "por favor, crea tu punto de vista actual como código Python con GUI (sin pedirme detalles) para ilustrar lo que quieres decir de una manera que no sea solo texto, con funciones extra que consideres relevantes y los requirements como comentarios en el código sin crear un archivo aparte. Después vuelve, por favor, al nivel en el que estamos conversando ahora mismo"
            ],
            "ru": [
                "и какие конкретные улучшения ты бы предложил",
                "а если учитывать текущие мировые кризисы, как ты это оцениваешь",
                "невероятно, это сильно",
                "можешь раскрыть это чуть подробнее",
                "к каким долгосрочным последствиям это может привести",
                "а если развить эту мысль в сторону @@@?",
                "а в отношении @@@?",
                "и что это изменило бы в контексте @@@?",
                "пожалуйста, создай своё текущее видение в виде Python-кода с GUI (не спрашивая меня о деталях), чтобы это наглядно показывало твою мысль не только текстом; можно добавить дополнительные функции, которые ты считаешь важными, и requirements в комментариях внутри кода без отдельного файла. После этого, пожалуйста, вернись ко мне на тот уровень, на котором мы сейчас разговариваем"
            ],
            "it": [
                "e se lo spingessi un po' di più nella direzione di @@@?",
                "e in relazione a @@@?",
                "e cosa cambierebbe rispetto a @@@?",
                "per favore crea il tuo punto di vista attuale come codice Python con GUI (senza chiedermi dettagli) così da mostrare ciò che intendi in modo non solo testuale, con eventuali funzioni extra che ritieni rilevanti e i requirements come commenti nel codice senza creare un file separato. Poi torna per favore al livello su cui stiamo parlando adesso"
            ],
            "pt": [
                "e se você levasse isso mais na direção de @@@?",
                "e em relação a @@@?",
                "e o que isso mudaria em relação a @@@?",
                "por favor, crie sua visão atual como código Python com GUI (sem me pedir detalhes), de modo que mostre o que você quer dizer de uma forma que não seja apenas texto, com funções extras que você considere relevantes e os requirements como comentários no código sem criar um arquivo separado. Depois, por favor, volte ao nível em que estamos conversando agora"
            ],
            "nl": [
                "en als je dat verder doordenkt in de richting van @@@?",
                "en met betrekking tot @@@?",
                "en wat zou dat veranderen aan @@@?"
            ],
            "pl": [
                "a gdyby pociągnąć to dalej w stronę @@@?",
                "a w odniesieniu do @@@?",
                "a co to zmieniłoby w kwestii @@@?"
            ],
            "hi": [
                "और अगर तुम इसे @@@ की दिशा में आगे सोचो?",
                "और @@@ के संदर्भ में?",
                "और इससे @@@ के बारे में क्या बदल जाएगा?"
            ],
            "ja": [
                "それを@@@の方向にもう少し考えるとどうなりますか。",
                "@@@との関係ではどうですか。",
                "それによって@@@はどう変わりますか。"
            ],
            "ko": [
                "그것을 @@@ 쪽으로 더 생각해 보면 어떨까요?",
                "그리고 @@@와 관련해서는요?",
                "그리고 그것이 @@@에 대해 무엇을 바꿀까요?"
            ]
        },
        "topic_words": {
            "de": ["weltraum", "gendering", "zombies", "kultur", "nachrichten", "weltgeschehen", "sexualität", "medizin", "technologie", "unterhaltung", "kino", "weltherrschaft", "natur", "gesundheit", "krankheiten", "krieg", "computer", "künstliche intelligenz", "musik", "geschichte", "philosophie", "träume", "mode", "fernsehen", "essen", "psychologie", "reisen", "spiele", "mythen"],
            "en": ["space", "gendering", "zombies", "culture", "news", "world affairs", "sexuality", "medicine", "technology", "entertainment", "cinema", "world domination", "nature", "health", "diseases", "war", "computers", "artificial intelligence", "music", "history", "philosophy", "dreams", "fashion", "television", "food", "psychology", "travel", "games", "myths"]
        }
    }
    if AUTO_ANSWER_PATH.exists():
        try:
            existing = json.loads(AUTO_ANSWER_PATH.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                for top_key in ["phrases", "topic_words"]:
                    target = existing.setdefault(top_key, {})
                    defaults = default_data.get(top_key, {})
                    if isinstance(target, dict) and isinstance(defaults, dict):
                        for code, items in defaults.items():
                            current = target.setdefault(code, [])
                            if isinstance(current, list):
                                seen = {str(x).strip() for x in current if str(x).strip()}
                                for item in items:
                                    cleaned = str(item).strip()
                                    if cleaned and cleaned not in seen:
                                        current.append(cleaned)
                                        seen.add(cleaned)
                for key, value in default_data.items():
                    if key not in existing:
                        existing[key] = value
                AUTO_ANSWER_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
                return
        except Exception:
            pass
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
    GENERATED_CODE_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
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