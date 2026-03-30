from __future__ import annotations

import html
import re
import os
import json
import subprocess
import sys
import traceback
import uuid
import threading
import random
from datetime import datetime
from time import monotonic
from pathlib import Path
from typing import Callable, List, Optional

import markdown
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, QSize, QUrl, QTimer, QMarginsF
from PyQt6.QtGui import QAction, QCursor, QDesktopServices, QFont, QFontMetrics, QTextOption, QTextDocument, QPageLayout, QPageSize, QShortcut, QKeySequence
from PyQt6.QtPrintSupport import QPrinter

from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import AUDIO_DIR, CHATS_DIR, EXPORTS_DIR, GENERATED_CODE_DIR, DEBUG_LOG_DIR, SETTINGS_PROFILE_DIR, SAPI_LEXICON_PATH, AUTO_ANSWER_PATH, AUTO_ANSWER_QUESTION_REPLY_PATH, DEFAULT_CONFIG, load_config, save_config, ensure_directories
from app.models import ChatMessage, ChatSession
from app.ollama_client import OllamaClient
from app.themes import THEMES
from app.tts_client import TTSClient
from app.tts_setup import VibeVoiceManager
from app.i18n import available_languages, load_language_pack


def markdown_to_tts_text(text: str) -> str:
    if not text:
        return ''

    cleaned = text.replace('\r\n', '\n').replace('\r', '\n')

    code_block_found = False

    def _strip_code_block(match: re.Match) -> str:
        nonlocal code_block_found
        code_block_found = True
        return '\nCodeblock ausgelassen.\n'

    cleaned = re.sub(r"```.*?```", _strip_code_block, cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"~~~.*?~~~", _strip_code_block, cleaned, flags=re.DOTALL)

    # Markdown links/images -> keep visible label only
    cleaned = re.sub(r"!\[([^\]]*)\]\([^)]*\)", lambda m: (m.group(1) or '').strip(), cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]*\)", lambda m: m.group(1).strip(), cleaned)

    # Raw URLs are usually noisy in TTS
    cleaned = re.sub(r"https?://\S+", '', cleaned)

    # Headings / blockquotes / bullets / numbered lists
    cleaned = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", '', cleaned)
    cleaned = re.sub(r"(?m)^\s*>+\s*", '', cleaned)
    cleaned = re.sub(r"(?m)^\s*[-*+]\s+", '• ', cleaned)
    cleaned = re.sub(r"(?m)^\s*\d+[.)]\s+", '', cleaned)

    # Table separators and markdown emphasis markers
    cleaned = re.sub(r"(?m)^\s*\|?\s*:?[-]{2,}:?\s*(\|\s*:?[-]{2,}:?\s*)+\|?\s*$", '', cleaned)
    cleaned = cleaned.replace('|', ' ')
    cleaned = re.sub(r"([*_~`])\1*", '', cleaned)

    # Footnote/citation-like markers such as [1], [12], [Quelle], sandbox:/...
    cleaned = re.sub(r"(?:sandbox:/\S+)", '', cleaned)
    cleaned = re.sub(r"(?<!\w)\[(?:\d+|Quelle|Quellen|source|sources?)\](?!\w)", '', cleaned, flags=re.IGNORECASE)

    # HTML leftovers
    cleaned = re.sub(r"<[^>]+>", ' ', cleaned)
    cleaned = html.unescape(cleaned)

    # Normalize bullets and whitespace for better speech flow
    cleaned = cleaned.replace('•', '\n- ')
    cleaned = re.sub(r"[ \t]+", ' ', cleaned)
    cleaned = re.sub(r"\n{3,}", '\n\n', cleaned)

    lines = []
    for raw_line in cleaned.split('\n'):
        line = raw_line.strip(' \t-')
        if not line:
            continue
        # skip lines that are only punctuation/symbols
        if re.fullmatch(r"[\W_]+", line):
            continue
        lines.append(line)

    cleaned = '\n'.join(lines).strip()
    if code_block_found and 'Codeblock ausgelassen.' not in cleaned:
        cleaned = (cleaned + '\n\nCodeblock ausgelassen.').strip() if cleaned else 'Codeblock ausgelassen.'

    return cleaned


def split_tts_sentences(text: str) -> List[str]:
    if not text:
        return []

    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    parts: List[str] = []
    for block in normalized.split('\n'):
        block = block.strip()
        if not block:
            continue
        chunk_parts = re.split(r'(?<=[.!?…:;])\s+|(?<=\))\s+', block)
        for part in chunk_parts:
            part = part.strip()
            if part:
                parts.append(part)
    return parts or [normalized.strip()]


def load_sapi_lexicon() -> dict:
    ensure_directories()
    try:
        return json.loads(SAPI_LEXICON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": False, "language": "de-DE", "entries": []}


def apply_sapi_lexicon(text: str, lexicon: dict | None) -> str:
    if not text or not isinstance(lexicon, dict):
        return text

    if lexicon.get("enabled", True) is False:
        return text

    entries = lexicon.get("entries")
    if not isinstance(entries, list):
        return text

    normalized_entries = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        source = str(item.get("from", "")).strip()
        target = str(item.get("to", "")).strip()
        if not source:
            continue
        entry_type = str(item.get("type", "word")).strip().lower()
        case_sensitive = bool(item.get("case_sensitive", False))
        normalized_entries.append({
            "type": entry_type if entry_type in {"word", "phrase"} else "word",
            "from": source,
            "to": target,
            "case_sensitive": case_sensitive,
        })

    normalized_entries.sort(key=lambda e: (0 if e["type"] == "phrase" else 1, -len(e["from"])))

    result = text
    for entry in normalized_entries:
        source = entry["from"]
        target = entry["to"]
        flags = 0 if entry["case_sensitive"] else re.IGNORECASE
        if entry["type"] == "phrase":
            pattern = re.escape(source)
        else:
            pattern = rf"\b{re.escape(source)}\b"
        try:
            result = re.sub(pattern, target, result, flags=flags)
        except re.error:
            continue

    result = re.sub(r"[ \t]+", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def message_content_to_html(text: str, is_assistant: bool) -> str:
    safe_text = text if is_assistant else html.escape(text)
    html_text = markdown.markdown(safe_text, extensions=["fenced_code", "tables"])
    css = """
    <style>
        body { font-family: 'Segoe UI', 'Inter', sans-serif; line-height: 1.5; margin: 0; padding: 0 0 8px 0; }
        p { margin: 0 0 0.72em 0; }
        p:last-child { margin-bottom: 0.15em; }
        pre { background: rgba(0,0,0,0.22); padding: 10px; border-radius: 10px; overflow-x: auto; }
        code { background: rgba(0,0,0,0.16); padding: 2px 4px; border-radius: 6px; }
        a { color: #7ab3ff; text-decoration: none; }
        ul, ol { margin-top: 0.3em; margin-bottom: 0.55em; }
        li:last-child { margin-bottom: 0.15em; }
        table { border-collapse: collapse; margin-bottom: 0.55em; }
        th, td { padding: 4px 8px; }
    </style>
    """
    return css + html_text


def load_auto_answer_data() -> dict:
    ensure_directories()
    try:
        return json.loads(AUTO_ANSWER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": True, "phrases": {"de": []}}


def load_auto_answer_question_reply_data() -> dict:
    ensure_directories()
    try:
        return json.loads(AUTO_ANSWER_QUESTION_REPLY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": True, "replies": {"de": []}}


def default_role_names(language_code: str) -> tuple[str, str]:
    code = (language_code or "de").lower()
    mapping = {
        "de": ("Du", "Assistent"),
        "en": ("You", "Assistant"),
        "fr": ("Vous", "Assistant"),
        "es": ("Tú", "Asistente"),
        "ru": ("Вы", "Ассистент"),
    }
    return mapping.get(code, mapping["en"])


TOKEN_PRESET_VALUES = [64, 128, 256, 512, 1024, 2048, 4096, 8192]
AUTO_ANSWER_ROLLOVER_FALLBACK_LIMIT = 40
AUTO_ANSWER_ROLLOVER_CARRY_MESSAGES = 5
AUTO_ANSWER_ROLLOVER_TOKEN_BUDGET_FACTOR = 8
APP_VERSION = "v1.0"
APP_TITLE_BASE = f"OllamaVibeDesk {APP_VERSION}"
APP_TITLE_DATE = datetime.now().strftime("%Y-%m-%d")
AUTO_ANSWER_ROLLOVER_TOKEN_MIN_BUDGET = 2048


def nearest_token_preset_index(value: int) -> int:
    target = max(1, int(value or TOKEN_PRESET_VALUES[0]))
    return min(range(len(TOKEN_PRESET_VALUES)), key=lambda i: abs(TOKEN_PRESET_VALUES[i] - target))


def format_token_value(value: int) -> str:
    amount = max(1, int(value or 0))
    if amount >= 1024 and amount % 1024 == 0:
        return f"{amount // 1024}k"
    if amount >= 1024:
        return f"{amount / 1024:.1f}k"
    return str(amount)


def default_auto_answer_short_instruction(language_code: str) -> str:
    code = (language_code or "de").lower()
    if code.startswith("de"):
        return "Bitte antworte jeweils kurz, nur zusammenfassend und ohne Aufzählungen."
    if code.startswith("fr"):
        return "Veuillez répondre brièvement, uniquement de manière synthétique et sans listes."
    if code.startswith("es"):
        return "Por favor, responde siempre de forma breve, solo resumiendo y sin listas."
    if code.startswith("ru"):
        return "Пожалуйста, отвечай кратко, только в виде сжатого резюме и без списков."
    if code.startswith("it"):
        return "Per favore rispondi sempre in modo breve, solo riassuntivo e senza elenchi."
    if code.startswith("pt"):
        return "Por favor, responda sempre de forma breve, apenas resumida e sem listas."
    if code.startswith("nl"):
        return "Beantwoord alstublieft steeds kort, alleen samenvattend en zonder opsommingen."
    if code.startswith("pl"):
        return "Proszę odpowiadać krótko, wyłącznie podsumowująco i bez list."
    if code.startswith("hi"):
        return "कृपया हमेशा संक्षेप में, केवल सार रूप में और बिना सूचियों के उत्तर दें।"
    if code.startswith("ja"):
        return "回答は毎回、短く、要約だけで、箇条書きなしでお願いします。"
    if code.startswith("ko"):
        return "항상 짧고 요약만 하며 목록 없이 답변해 주세요."
    return "Please answer briefly, only in summary form, and without bullet lists."


def auto_answer_short_instruction(config: dict | None, language_code: str) -> str:
    code = (language_code or "de").lower()
    overrides = {}
    if isinstance(config, dict):
        raw = config.get("auto_answer_short_instruction_overrides", {})
        if isinstance(raw, dict):
            overrides = raw
    custom = str(overrides.get(code, "") or "").strip()
    if not custom and "-" in code:
        custom = str(overrides.get(code.split("-", 1)[0], "") or "").strip()
    return custom or default_auto_answer_short_instruction(code)

def hidden_auto_answer_system_instruction(language_code: str, instruction: str) -> str:
    text = str(instruction or "").strip()
    if not text:
        return ""
    code = (language_code or "de").lower()
    if code.startswith("de"):
        return f"Wichtige versteckte Zusatzanweisung nur für die direkt nächste Antwort. Nicht erwähnen oder zitieren. Diese Stilvorgabe hat Vorrang: {text}"
    if code.startswith("fr"):
        return f"Instruction cachée importante pour la prochaine réponse uniquement. Ne la mentionnez pas et ne la citez pas. Cette consigne de style est prioritaire : {text}"
    if code.startswith("es"):
        return f"Instrucción oculta importante solo para la siguiente respuesta. No la menciones ni la cites. Esta pauta de estilo tiene prioridad: {text}"
    if code.startswith("ru"):
        return f"Важная скрытая инструкция только для следующего ответа. Не упоминай и не цитируй её. Это стилевое указание имеет приоритет: {text}"
    if code.startswith("it"):
        return f"Importante istruzione nascosta solo per la prossima risposta. Non menzionarla e non citarla. Questa indicazione di stile ha priorità: {text}"
    if code.startswith("pt"):
        return f"Instrução oculta importante apenas para a próxima resposta. Não a mencione nem a cite. Esta diretriz de estilo tem prioridade: {text}"
    if code.startswith("nl"):
        return f"Belangrijke verborgen instructie alleen voor het eerstvolgende antwoord. Noem of citeer die niet. Deze stijlrichtlijn heeft voorrang: {text}"
    if code.startswith("pl"):
        return f"Ważna ukryta instrukcja tylko dla najbliższej odpowiedzi. Nie wspominaj o niej i jej nie cytuj. To zalecenie stylu ma pierwszeństwo: {text}"
    if code.startswith("hi"):
        return f"केवल अगली प्रतिक्रिया के लिए महत्वपूर्ण छिपा निर्देश। इसका उल्लेख या उद्धरण न करें। यह शैली-निर्देश प्राथमिक है: {text}"
    if code.startswith("ja"):
        return f"次の回答にだけ適用する重要な非表示指示です。言及したり引用したりしないでください。この文体指示を優先してください。{text}"
    if code.startswith("ko"):
        return f"다음 답변에만 적용되는 중요한 숨김 지시입니다. 언급하거나 인용하지 마세요. 이 문체 지시를 우선하세요: {text}"
    return f"Important hidden instruction for the next answer only. Do not mention or quote it. This style instruction takes priority: {text}"


def hidden_auto_answer_user_suffix(language_code: str, instruction: str) -> str:
    text = str(instruction or "").strip()
    if not text:
        return ""
    code = (language_code or "de").lower()
    if code.startswith("de"):
        return f"Zusatzanweisung nur für deine direkt nächste Antwort: {text}"
    if code.startswith("fr"):
        return f"Consigne supplémentaire pour votre prochaine réponse uniquement : {text}"
    if code.startswith("es"):
        return f"Instrucción adicional solo para tu siguiente respuesta: {text}"
    if code.startswith("ru"):
        return f"Дополнительная инструкция только для твоего следующего ответа: {text}"
    if code.startswith("it"):
        return f"Istruzione aggiuntiva solo per la tua prossima risposta: {text}"
    if code.startswith("pt"):
        return f"Instrução adicional apenas para a tua próxima resposta: {text}"
    if code.startswith("nl"):
        return f"Extra instructie alleen voor je eerstvolgende antwoord: {text}"
    if code.startswith("pl"):
        return f"Dodatkowa instrukcja tylko do twojej następnej odpowiedzi: {text}"
    if code.startswith("hi"):
        return f"केवल आपकी अगली प्रतिक्रिया के लिए अतिरिक्त निर्देश: {text}"
    if code.startswith("ja"):
        return f"次の回答だけに対する追加指示です: {text}"
    if code.startswith("ko"):
        return f"다음 답변에만 대한 추가 지시입니다: {text}"
    return f"Additional instruction for your next answer only: {text}"


def append_hidden_instruction_to_user_text(user_text: str, instruction: str) -> str:
    base = str(user_text or "").rstrip()
    extra = str(instruction or "").strip()
    if not extra:
        return base
    if not base:
        return f"({extra})."
    return f"{base} ({extra})."


def message_visible_content(message: ChatMessage) -> str:
    display = getattr(message, "display_content", None)
    if display is None:
        return message.content
    return display





def estimate_token_count(text: str) -> int:
    raw = str(text or "")
    if not raw:
        return 0
    words = len(re.findall(r"\S+", raw))
    by_chars = max(1, (len(raw) + 3) // 4)
    by_words = max(1, int(words * 1.35))
    return max(by_chars, by_words)


def estimate_chat_payload_tokens(messages: list[dict], system_prompt: str = "") -> int:
    total = estimate_token_count(system_prompt)
    for item in messages:
        total += 8
        total += estimate_token_count(str(item.get("content", "") or ""))
    return total


def is_context_overflow_error(message: str) -> bool:
    hay = str(message or "").lower()
    needles = [
        'context length', 'maximum context length', 'prompt too long', 'input too long',
        'token limit', 'too many tokens', 'more than the context window', 'context window',
        'num_ctx', 'truncate', 'requested tokens exceed', 'llm context', 'ctx'
    ]
    return any(needle in hay for needle in needles)


def iter_code_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    pattern = re.compile(r"```([A-Za-z0-9_+.#-]*)[ 	]*\n(.*?)```", re.DOTALL)
    for match in pattern.finditer(str(text or "")):
        language = (match.group(1) or "").strip()
        code = match.group(2) or ""
        if code.strip():
            blocks.append((language, code.rstrip() + "\n"))
    return blocks


def code_extension_for_language(language: str, code: str) -> tuple[str, str]:
    lang = (language or "").strip().lower()
    mapping = {
        'python': ('python', 'py'), 'py': ('python', 'py'),
        'c#': ('csharp', 'cs'), 'cs': ('csharp', 'cs'), 'csharp': ('csharp', 'cs'),
        'html': ('html', 'htm'), 'htm': ('html', 'htm'),
        'php': ('php', 'php'),
        'javascript': ('javascript', 'js'), 'js': ('javascript', 'js'),
        'typescript': ('typescript', 'ts'), 'ts': ('typescript', 'ts'),
        'json': ('json', 'json'),
        'yaml': ('yaml', 'yml'), 'yml': ('yaml', 'yml'),
        'xml': ('xml', 'xml'), 'css': ('css', 'css'), 'sql': ('sql', 'sql'),
        'bash': ('bash', 'sh'), 'sh': ('bash', 'sh'), 'zsh': ('bash', 'sh'),
        'powershell': ('powershell', 'ps1'), 'ps1': ('powershell', 'ps1'),
        'java': ('java', 'java'), 'kotlin': ('kotlin', 'kt'), 'swift': ('swift', 'swift'),
        'go': ('go', 'go'), 'rust': ('rust', 'rs'), 'cpp': ('cpp', 'cpp'), 'c++': ('cpp', 'cpp'),
        'c': ('c', 'c'), 'ruby': ('ruby', 'rb'), 'perl': ('perl', 'pl'), 'lua': ('lua', 'lua'),
        'r': ('r', 'r'), 'dart': ('dart', 'dart'), 'scala': ('scala', 'scala'), 'objective-c': ('objectivec', 'm'),
    }
    if lang in mapping:
        return mapping[lang]
    sample = (code or '').lstrip()[:200].lower()
    if sample.startswith('<?php'):
        return ('php', 'php')
    if sample.startswith('<!doctype html') or sample.startswith('<html'):
        return ('html', 'htm')
    if sample.startswith('using system') or 'namespace ' in sample:
        return ('csharp', 'cs')
    if sample.startswith('import ') or sample.startswith('from ') or 'def ' in sample:
        return ('python', 'py')
    return ((lang or 'text').replace('#', 'sharp').replace('+', 'plus'), 'txt')


def save_generated_code_blocks(text: str) -> list[Path]:
    blocks = iter_code_blocks(text)
    saved: list[Path] = []
    if not blocks:
        return saved
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    for index, (language, code) in enumerate(blocks, 1):
        folder_name, ext = code_extension_for_language(language, code)
        target_dir = GENERATED_CODE_DIR / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)
        base_name = f'{timestamp}_{index:03d}'
        path = target_dir / f'{base_name}.{ext}'
        collision = 1
        while path.exists():
            collision += 1
            path = target_dir / f'{base_name}_{collision:02d}.{ext}'
        path.write_text(code, encoding='utf-8')
        saved.append(path)
    return saved


class DebugTraceLogger:
    def __init__(self, enabled: bool = False) -> None:
        self.run_id = uuid.uuid4().hex
        self.path = DEBUG_LOG_DIR / f"debug_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{self.run_id[:8]}.jsonl"
        self.enabled = False
        if enabled:
            self.set_enabled(True)

    def set_enabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        created = False
        if enabled and not self.path.exists():
            DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
            self.path.touch()
            created = True
        self.enabled = enabled
        return created

    def write(self, event: str, payload: dict | None = None) -> None:
        if not self.enabled:
            return
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "run_id": self.run_id,
            "event": str(event or "event"),
            "payload": payload or {},
        }
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


def resolve_tts_voice_config_defaults(config: dict) -> tuple[dict, bool]:
    data = dict(config)
    backend = (data.get("tts_backend", "disabled") or "disabled").strip()
    changed = False

    if backend == "vibevoice_openai":
        voice = str(data.get("tts_voice", "") or "").strip()
        user_voice = str(data.get("tts_user_voice", "") or "").strip()
        if not voice or voice.startswith(("sapi::", "onecore::")):
            voice = "Emma"
        if not user_voice or user_voice.startswith(("sapi::", "onecore::")):
            user_voice = voice
        if data.get("tts_voice") != voice:
            data["tts_voice"] = voice
            changed = True
        if data.get("tts_user_voice") != user_voice:
            data["tts_user_voice"] = user_voice
            changed = True
        if not bool(data.get("tts_voice_defaults_initialized", False)):
            data["tts_voice_defaults_initialized"] = True
            changed = True
        return data, changed

    if backend != "windows_sapi":
        return data, changed

    try:
        client = TTSClient(
            backend=backend,
            base_url=str(data.get("tts_base_url", "http://127.0.0.1:8880/v1") or "http://127.0.0.1:8880/v1").strip(),
            voice=str(data.get("tts_voice", "") or "").strip(),
            model=str(data.get("tts_model", "tts-1-hd") or "tts-1-hd").strip() or "tts-1-hd",
            audio_format=str(data.get("tts_format", "wav") or "wav").strip() or "wav",
            windows_sapi_rate=int(data.get("windows_sapi_rate", 0) or 0),
            windows_sapi_pitch=int(data.get("windows_sapi_pitch", 0) or 0),
            windows_sapi_volume=int(data.get("windows_sapi_volume", 100) or 100),
        )
        entries = client.list_voice_entries()
    except Exception:
        return data, changed

    if not entries:
        return data, changed

    language_code = (data.get("interface_language", "de") or "de").strip()
    defaults_initialized = bool(data.get("tts_voice_defaults_initialized", False))
    original_voice = str(data.get("tts_voice", "") or "").strip()
    original_user_voice = str(data.get("tts_user_voice", "") or "").strip()

    voice = original_voice or pick_preferred_windows_voice(entries, language_code, "assistant")
    if original_user_voice and (defaults_initialized or original_user_voice != original_voice):
        user_voice = original_user_voice
    else:
        user_voice = pick_preferred_windows_voice(entries, language_code, "user", avoid_value=voice) or voice

    if data.get("tts_voice") != voice:
        data["tts_voice"] = voice
        changed = True
    if data.get("tts_user_voice") != user_voice:
        data["tts_user_voice"] = user_voice
        changed = True
    if not defaults_initialized:
        data["tts_voice_defaults_initialized"] = True
        changed = True

    return data, changed


def _normalize_compare_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def _expand_auto_answer_phrase_templates(phrases: list[str], topic_words: list[str]) -> list[str]:
    expanded: list[str] = []
    clean_topics = [str(word or "").strip() for word in topic_words if str(word or "").strip()]
    unique_topics: list[str] = []
    seen_topics: set[str] = set()
    for word in clean_topics:
        normalized = _normalize_compare_text(word)
        if not normalized or normalized in seen_topics:
            continue
        seen_topics.add(normalized)
        unique_topics.append(word)

    for phrase in phrases:
        cleaned = str(phrase or "").strip()
        if not cleaned:
            continue
        if "@@@" not in cleaned:
            expanded.append(cleaned)
            continue
        if not unique_topics:
            expanded.append(cleaned.replace("@@@", "…"))
            continue
        pool = unique_topics[:]
        random.shuffle(pool)
        for topic in pool[: min(4, len(pool))]:
            expanded.append(cleaned.replace("@@@", topic))
    return expanded



def _unique_auto_answer_phrases(phrases: list[str], blocked_recent: list[str]) -> list[str]:
    blocked = {_normalize_compare_text(item) for item in blocked_recent if _normalize_compare_text(item)}
    result: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        cleaned = str(phrase or "").strip()
        normalized = _normalize_compare_text(cleaned)
        if not cleaned or not normalized or normalized in blocked or normalized in seen:
            continue
        seen.add(normalized)
        result.append(cleaned)
    return result


def resolve_display_name(config: dict, role: str) -> str:
    user_default, assistant_default = default_role_names(config.get("interface_language", "de"))
    if role == "assistant":
        return (config.get("assistant_display_name", "") or "").strip() or assistant_default
    return (config.get("user_display_name", "") or "").strip() or user_default

def strip_emojis_and_symbols(text: str) -> str:
    if not text:
        return ''
    text = re.sub(r'[🇦-🇿🌀-🫿☀-➿️‍]+', ' ', text)
    text = re.sub(r'(?::|;|=|8)[\-^]?[)(DPpOo/\|]', ' ', text)
    text = re.sub(r'<3', ' ', text)
    return re.sub(r'\s{2,}', ' ', text).strip()


def preferred_windows_voice_candidates(language_code: str, role: str) -> list[str]:
    code = (language_code or 'de').lower()
    if code.startswith('de'):
        return ['Katja', 'Hedda', 'Zira'] if role == 'assistant' else ['Michael', 'Stefan', 'Karsten']
    if code.startswith('en'):
        return ['Zira', 'Grace', 'Emma'] if role == 'assistant' else ['David', 'Mark', 'Mike']
    if code.startswith('fr'):
        return ['Hortense', 'Julie'] if role == 'assistant' else ['Paul', 'Claude']
    if code.startswith('es'):
        return ['Helena', 'Laura'] if role == 'assistant' else ['Pablo', 'Jorge']
    if code.startswith('it'):
        return ['Elsa'] if role == 'assistant' else ['Cosimo']
    if code.startswith('ru'):
        return ['Irina'] if role == 'assistant' else ['Pavel']
    return ['Katja', 'Hedda'] if role == 'assistant' else ['Michael', 'Stefan']


def pick_preferred_windows_voice(entries: list[tuple[str, str]], language_code: str, role: str, avoid_value: str = '') -> str:
    if not entries:
        return ''
    candidates = preferred_windows_voice_candidates(language_code, role)
    for cand in candidates:
        for value, label in entries:
            if avoid_value and value == avoid_value:
                continue
            hay = f"{value} {label}".lower()
            if cand.lower() in hay:
                return value
    for value, _label in entries:
        if not avoid_value or value != avoid_value:
            return value
    return entries[0][0]


def _reflect_fragment_de(fragment: str) -> str:
    replacements = [
        (r"\bdeine\b", "meine"),
        (r"\bdein\b", "mein"),
        (r"\bdeiner\b", "meiner"),
        (r"\bdeinem\b", "meinem"),
        (r"\bdeinen\b", "meinen"),
        (r"\bdu\b", "ich"),
        (r"\bdich\b", "mich"),
        (r"\bdir\b", "mir"),
        (r"\bich\b", "du"),
        (r"\bmir\b", "dir"),
        (r"\bmich\b", "dich"),
        (r"\bmein\b", "dein"),
        (r"\bmeine\b", "deine"),
    ]
    out = fragment
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def _reflect_fragment_en(fragment: str) -> str:
    replacements = [
        (r"\byour\b", "my"),
        (r"\byours\b", "mine"),
        (r"\byou\b", "I"),
        (r"\byourself\b", "myself"),
        (r"\bme\b", "you"),
        (r"\bmy\b", "your"),
        (r"\bmine\b", "yours"),
        (r"\bi\b", "you"),
    ]
    out = fragment
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def _question_reply_candidates(question_reply_data: dict | None, language_code: str) -> list[str]:
    code = (language_code or "de").lower()
    if not isinstance(question_reply_data, dict):
        return []
    replies_map = question_reply_data.get("replies")
    if not isinstance(replies_map, dict):
        return []
    replies = [str(x).strip() for x in replies_map.get(code, []) if str(x).strip()]
    if not replies and code != "en":
        replies = [str(x).strip() for x in replies_map.get("en", []) if str(x).strip()]
    return replies


def generate_auto_answer(
    source_text: str,
    language_code: str,
    phrase_data: dict | None = None,
    question_reply_data: dict | None = None,
    recent_generated_user_messages: list[str] | None = None,
    eliza_share_percent: int = 60,
    use_question_replies_for_all: bool = True,
) -> str:
    cleaned = markdown_to_tts_text(source_text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "das" if (language_code or "de").startswith("de") else "that"
    fragment = cleaned[:180].strip(" .!?…:;,-") or cleaned[:180]
    code = (language_code or "de").lower()
    phrases: list[str] = []
    topic_words: list[str] = []
    if isinstance(phrase_data, dict):
        phrases_map = phrase_data.get("phrases")
        if isinstance(phrases_map, dict):
            phrases = [str(x).strip() for x in phrases_map.get(code, []) if str(x).strip()]
            if not phrases and code != "en":
                phrases = [str(x).strip() for x in phrases_map.get("en", []) if str(x).strip()]
        topic_words_map = phrase_data.get("topic_words")
        if isinstance(topic_words_map, dict):
            topic_words = [str(x).strip() for x in topic_words_map.get(code, []) if str(x).strip()]
            if not topic_words and code != "en":
                topic_words = [str(x).strip() for x in topic_words_map.get("en", []) if str(x).strip()]

    if code.startswith("de"):
        reflected = _reflect_fragment_de(fragment)
        templates = [
            "Das ist interessant. Erzähl bitte weiter.",
            f"Warum denkst du {reflected}?",
            "Hast du dabei Bedenken?",
            "Und wie betrachtest du das kritisch?",
            "Interessant — wie könnte sich das noch entwickeln?",
        ]
    elif code.startswith("fr"):
        reflected = fragment
        templates = [
            "C'est intéressant. Continue, s'il te plaît.",
            f"Pourquoi penses-tu {reflected} ?",
            "As-tu des réserves à ce sujet ?",
            "Et comment le considérerais-tu de manière critique ?",
            "Intéressant — comment cela pourrait-il encore évoluer ?",
        ]
    elif code.startswith("es"):
        reflected = fragment
        templates = [
            "Eso es interesante. Sigue, por favor.",
            f"¿Por qué piensas {reflected}?",
            "¿Tienes dudas al respecto?",
            "¿Y cómo lo valorarías de manera crítica?",
            "Interesante — ¿cómo crees que podría evolucionar?",
        ]
    elif code.startswith("ru"):
        reflected = fragment
        templates = [
            "Это интересно. Расскажи дальше.",
            f"Почему ты так думаешь: {reflected}?",
            "Есть ли у тебя опасения по этому поводу?",
            "А как ты смотришь на это критически?",
            "Интересно — как, по-твоему, это может развиваться дальше?",
        ]
    else:
        reflected = _reflect_fragment_en(fragment)
        templates = [
            "That is interesting. Please tell me more.",
            f"Why do you think {reflected}?",
            "Do you have concerns about that?",
            "And how do you look at that critically?",
            "Interesting — how do you think this might develop further?",
        ]

    blocked_recent = recent_generated_user_messages or []
    question_reply_candidates = _question_reply_candidates(question_reply_data, code)
    is_question = cleaned.rstrip().endswith("?")
    if is_question and question_reply_candidates:
        return random.choice(question_reply_candidates).strip()
    phrase_pool = _expand_auto_answer_phrase_templates(phrases, topic_words)
    if use_question_replies_for_all and question_reply_candidates:
        phrase_pool.extend(question_reply_candidates)
    phrase_candidates = _unique_auto_answer_phrases(phrase_pool, blocked_recent)
    eliza_candidates = [t for t in templates if t.strip()]
    eliza_share = max(0, min(100, int(eliza_share_percent or 0)))

    use_eliza = not phrase_candidates or random.randint(1, 100) <= eliza_share
    if use_eliza and eliza_candidates:
        return random.choice(eliza_candidates).strip()
    if phrase_candidates:
        return random.choice(phrase_candidates).strip()
    return random.choice(eliza_candidates).strip() if eliza_candidates else ""


def pretty_timestamp(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return value


class SessionStore:
    def __init__(self) -> None:
        ensure_directories()

    def _path(self, session_id: str) -> Path:
        return CHATS_DIR / f"{session_id}.json"

    def list_sessions(self) -> List[ChatSession]:
        sessions: List[ChatSession] = []
        for path in sorted(CHATS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions.append(ChatSession.from_dict(data))
            except Exception:
                continue
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def save(self, session: ChatSession) -> None:
        session.updated_at = datetime.now().isoformat(timespec="seconds")
        self._path(session.session_id).write_text(
            json.dumps(session.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()


class BubbleWidget(QFrame):
    def __init__(
        self,
        message: ChatMessage,
        is_assistant: bool,
        on_read_aloud: Optional[Callable[[ChatMessage], None]] = None,
        on_stop_audio: Optional[Callable[[], None]] = None,
        on_copy: Optional[Callable[[str], None]] = None,
        translate: Optional[Callable[[str, Optional[str]], str]] = None,
        role_label: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.message = message
        self.is_assistant = is_assistant
        self.on_read_aloud = on_read_aloud
        self.on_stop_audio = on_stop_audio
        self.on_copy = on_copy
        self.translate = translate or (lambda key, default=None: default or key)
        self.role_label = role_label or ((self.translate("assistant_label", "Assistent") if is_assistant else self.translate("you_label", "Du")))
        self.setObjectName("BubbleWidget")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.card = QFrame()
        self.card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.card.setMaximumWidth(1120 if is_assistant else 820)
        self.card.setMinimumWidth(500 if is_assistant else 300)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        self.meta_label = QLabel(self.role_label + " · " + pretty_timestamp(message.created_at))
        meta = self.meta_label
        meta.setObjectName("SubtleLabel")
        card_layout.addWidget(meta)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFrameShape(QFrame.Shape.NoFrame)
        self.browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.browser.document().setDocumentMargin(0)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        self.browser.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.browser.setMinimumHeight(56)
        try:
            self.browser.document().documentLayout().documentSizeChanged.connect(lambda _size: self._update_browser_height())
        except Exception:
            pass
        card_layout.addWidget(self.browser)

        self.loading_box = QWidget()
        loading_layout = QVBoxLayout(self.loading_box)
        loading_layout.setContentsMargins(0, 4, 0, 0)
        loading_layout.setSpacing(8)

        self.loading_label = QLabel(self.translate(
            "assistant_loading_default",
            "Waiting for the selected model and first tokens…"
        ))
        self.loading_label.setWordWrap(True)
        loading_layout.addWidget(self.loading_label)

        self.loading_elapsed_label = QLabel(self.translate("assistant_loading_elapsed", "Elapsed: 0 s"))
        self.loading_elapsed_label.setObjectName("SubtleLabel")
        loading_layout.addWidget(self.loading_elapsed_label)

        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedHeight(10)
        loading_layout.addWidget(self.loading_bar)

        self.loading_timer = QTimer(self)
        self.loading_timer.setInterval(250)
        self.loading_timer.timeout.connect(self._refresh_loading_elapsed)
        self.loading_started_at: float | None = None
        self.loading_box.setVisible(False)
        card_layout.addWidget(self.loading_box)

        self.set_content(message_visible_content(message))

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch()

        if self.on_copy is not None:
            copy_btn = QPushButton(self.translate("copy_button", "Kopieren"))
            copy_btn.clicked.connect(lambda: self.on_copy(message_visible_content(self.message)))
            actions.addWidget(copy_btn)

        if self.on_read_aloud is not None:
            speak_btn = QPushButton(self.translate("read_aloud_button", "Vorlesen"))
            speak_btn.clicked.connect(lambda: self.on_read_aloud(self.message))
            actions.addWidget(speak_btn)

        if self.on_stop_audio is not None:
            stop_audio_btn = QPushButton(self.translate("stop_audio_button", "Audio stoppen"))
            stop_audio_btn.clicked.connect(self.on_stop_audio)
            actions.addWidget(stop_audio_btn)

        card_layout.addLayout(actions)

        if is_assistant:
            self.card.setStyleSheet(
                """
                QFrame {
                    background: #1c2430;
                    border: 1px solid #2f3d52;
                    border-left: 4px solid #6ea8ff;
                    border-radius: 16px;
                }
                """
            )
            outer.addSpacing(20)
            outer.addWidget(self.card, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            outer.addStretch(1)
        else:
            self.card.setStyleSheet(
                """
                QFrame {
                    background: #243752;
                    border: 1px solid #41638f;
                    border-radius: 16px;
                }
                """
            )
            outer.addStretch(1)
            outer.addWidget(self.card, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            outer.addSpacing(20)

    def set_loading(self, active: bool, model_name: str = "", switched_model: bool = False) -> None:
        if not self.is_assistant:
            return

        if active:
            if switched_model and model_name:
                self.loading_label.setText(
                    self.translate(
                        "assistant_loading_switched",
                        "Switching to model '{model}'. Ollama may need a moment to load it before the first tokens arrive."
                    ).format(model=model_name)
                )
            elif model_name:
                self.loading_label.setText(
                    self.translate(
                        "assistant_loading_model",
                        "Waiting for model '{model}' and the first tokens…"
                    ).format(model=model_name)
                )
            else:
                self.loading_label.setText(
                    self.translate("assistant_loading_default", "Waiting for the selected model and first tokens…")
                )
            self.loading_started_at = monotonic()
            self._refresh_loading_elapsed()
            self.loading_box.setVisible(True)
            self.browser.setVisible(False)
            self.loading_timer.start()
        else:
            self.loading_timer.stop()
            self.loading_box.setVisible(False)
            self.browser.setVisible(True)

    def _refresh_loading_elapsed(self) -> None:
        if self.loading_started_at is None:
            seconds = 0
        else:
            seconds = max(0, int(monotonic() - self.loading_started_at))
        self.loading_elapsed_label.setText(
            self.translate("assistant_loading_elapsed", "Elapsed: {seconds} s").format(seconds=seconds)
        )

    def _update_card_width(self) -> None:
        try:
            available = max(320, self.width() - 56)
            if self.is_assistant:
                target = min(1520, max(560, int(available * 0.78)))
                target = min(target, available)
                self.card.setMinimumWidth(target)
                self.card.setMaximumWidth(target)
            else:
                target = min(980, max(300, int(available * 0.58)))
                target = min(target, available)
                self.card.setMinimumWidth(280)
                self.card.setMaximumWidth(target)
        except Exception:
            pass

    def _update_browser_height(self) -> None:
        try:
            self._update_card_width()
            doc = self.browser.document()
            width = max(160, self.browser.viewport().width())
            doc.setTextWidth(width)
            height = int(doc.size().height()) + 28
            height = max(56, height)
            self.browser.setMinimumHeight(height)
            self.browser.setMaximumHeight(height)
            self.browser.updateGeometry()
            self.card.updateGeometry()
            self.updateGeometry()
        except Exception:
            pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._update_browser_height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_browser_height)

    def set_role_label(self, value: str) -> None:
        self.role_label = value or self.role_label
        self.meta_label.setText(self.role_label + " · " + pretty_timestamp(self.message.created_at))

    def set_content(self, text: str) -> None:
        if self.is_assistant:
            self.message.content = text
        else:
            self.message.display_content = text
        has_visible_text = bool(text.strip())
        if self.is_assistant and has_visible_text:
            self.set_loading(False)
        self.browser.setHtml(message_content_to_html(text, self.is_assistant))
        self._update_browser_height()
        QTimer.singleShot(0, self._update_browser_height)


class ChatWorker(QObject):
    chunk = pyqtSignal(str)
    finished = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, base_url: str, model_name: str, messages: List[dict], system_prompt: str, max_tokens: int = 512) -> None:
        super().__init__()
        self.base_url = base_url
        self.model_name = model_name
        self.messages = messages
        self.system_prompt = system_prompt
        self.max_tokens = int(max_tokens or 512)
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            client = OllamaClient(self.base_url)
            for text in client.stream_chat(
                model=self.model_name,
                messages=self.messages,
                system_prompt=self.system_prompt,
                options={"num_predict": self.max_tokens} if self.max_tokens > 0 else None,
            ):
                if self._cancel_requested:
                    break
                self.chunk.emit(text)
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class LexiconEditorDialog(QDialog):
    def __init__(self, language_code: str = "de", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.translations = load_language_pack(language_code)
        self.setWindowTitle(self.t("lexicon_editor_title", "TTS Aussprache-Lexikon bearbeiten"))
        self.setModal(True)
        self.resize(760, 560)

        layout = QVBoxLayout(self)

        info = QLabel(self.t("lexicon_info", "Die JSON-Datei wird direkt aus dem App-Ordner geladen. Unterstützt werden Einträge vom Typ 'word' und 'phrase'. Das Lexikon wird für Windows-SAPI und VibeVoice auf den bereinigten Vorlesetext angewendet."))
        info.setWordWrap(True)
        info.setObjectName("SubtleLabel")
        layout.addWidget(info)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("""{
  \"enabled\": true,
  \"language\": \"de-DE\",
  \"entries\": []
}""")
        layout.addWidget(self.editor, 1)

        buttons = QHBoxLayout()
        self.reset_btn = QPushButton(self.t("reset_default", "Standard wiederherstellen"))
        self.reset_btn.clicked.connect(self.reset_to_default)
        buttons.addWidget(self.reset_btn)
        buttons.addStretch()

        cancel_btn = QPushButton(self.t("cancel", "Abbrechen"))
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton(self.t("save", "Speichern"))
        save_btn.setObjectName("AccentButton")
        save_btn.clicked.connect(self.save_and_accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

        self.load_current()

    def t(self, key: str, default: Optional[str] = None) -> str:
        return self.translations.get(key, default or key)

    def load_current(self) -> None:
        ensure_directories()
        try:
            content = SAPI_LEXICON_PATH.read_text(encoding="utf-8")
        except Exception:
            ensure_directories()
            content = SAPI_LEXICON_PATH.read_text(encoding="utf-8")
        self.editor.setPlainText(content)

    def reset_to_default(self) -> None:
        reply = QMessageBox.question(
            self,
            self.t("reset_confirm_title", "Standard wiederherstellen"),
            self.t("reset_confirm_text", "Soll das Aussprache-Lexikon auf die Standardwerte zurückgesetzt werden?"),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if SAPI_LEXICON_PATH.exists():
            SAPI_LEXICON_PATH.unlink()
        ensure_directories()
        self.load_current()

    def save_and_accept(self) -> None:
        raw = self.editor.toPlainText().strip()
        if not raw:
            QMessageBox.warning(self, self.t("empty_lexicon_title", "Leeres Lexikon"), self.t("empty_lexicon_text", "Die JSON-Datei darf nicht leer sein."))
            return
        try:
            data = json.loads(raw)
        except Exception as exc:
            QMessageBox.critical(self, self.t("invalid_json_title", "Ungültiges JSON"), self.t("invalid_json_text", "Die Datei ist kein gültiges JSON.\n\n{error}").format(error=exc))
            return
        if not isinstance(data, dict):
            QMessageBox.critical(self, self.t("invalid_format_title", "Ungültiges Format"), self.t("invalid_format_root", "Die oberste Ebene der Datei muss ein JSON-Objekt sein."))
            return
        if "entries" in data and not isinstance(data.get("entries"), list):
            QMessageBox.critical(self, self.t("invalid_format_title", "Ungültiges Format"), self.t("invalid_format_entries", "'entries' muss eine Liste sein."))
            return
        ensure_directories()
        SAPI_LEXICON_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.accept()




class AutoAnswerPhrasesDialog(QDialog):
    def __init__(self, language_code: str = "de", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.translations = load_language_pack(language_code)
        self.setWindowTitle(self.t("auto_answer_editor_title", "Automatische Antwortsätze bearbeiten"))
        self.setModal(True)
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        info = QLabel(self.t("auto_answer_editor_info", "Die JSON-Datei wird direkt aus dem App-Ordner geladen. Unter 'phrases' können pro Sprache zusätzliche Sätze hinterlegt werden, die ergänzend zum ELIZA-Modus verwendet werden."))
        info.setWordWrap(True)
        info.setObjectName("SubtleLabel")
        layout.addWidget(info)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("""{
  "enabled": true,
  "phrases": {
    "de": ["und hättest du konkrete verbesserungsvorschläge"],
    "en": ["and would you have concrete suggestions for improvement"]
  }
}""")
        layout.addWidget(self.editor, 1)

        buttons = QHBoxLayout()
        self.reset_btn = QPushButton(self.t("reset_default", "Standard wiederherstellen"))
        self.reset_btn.clicked.connect(self.reset_to_default)
        buttons.addWidget(self.reset_btn)
        buttons.addStretch()

        cancel_btn = QPushButton(self.t("cancel", "Abbrechen"))
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton(self.t("save", "Speichern"))
        save_btn.setObjectName("AccentButton")
        save_btn.clicked.connect(self.save_and_accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)
        self.load_current()

    def t(self, key: str, default: Optional[str] = None) -> str:
        return self.translations.get(key, default or key)

    def load_current(self) -> None:
        ensure_directories()
        self.editor.setPlainText(AUTO_ANSWER_PATH.read_text(encoding="utf-8"))

    def reset_to_default(self) -> None:
        reply = QMessageBox.question(
            self,
            self.t("reset_confirm_title", "Standard wiederherstellen"),
            self.t("reset_confirm_text", "Soll das Aussprache-Lexikon auf die Standardwerte zurückgesetzt werden?")
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if AUTO_ANSWER_PATH.exists():
            AUTO_ANSWER_PATH.unlink()
        ensure_directories()
        self.load_current()

    def save_and_accept(self) -> None:
        raw = self.editor.toPlainText().strip()
        if not raw:
            QMessageBox.warning(self, self.t("empty_auto_answer_title", "Leere Datei"), self.t("empty_auto_answer_text", "Die JSON-Datei darf nicht leer sein."))
            return
        try:
            data = json.loads(raw)
        except Exception as exc:
            QMessageBox.critical(self, self.t("invalid_json_title", "Ungültiges JSON"), self.t("invalid_json_text", "Die Datei ist kein gültiges JSON.\n\n{error}").format(error=exc))
            return
        if not isinstance(data, dict):
            QMessageBox.critical(self, self.t("invalid_format_title", "Ungültiges Format"), self.t("invalid_format_root", "Die oberste Ebene der Datei muss ein JSON-Objekt sein."))
            return
        ensure_directories()
        AUTO_ANSWER_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.accept()


class AutoAnswerQuestionRepliesDialog(QDialog):
    def __init__(self, language_code: str = "de", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.translations = load_language_pack(language_code)
        self.setWindowTitle(self.t("auto_answer_question_replies_editor_title", "Antwortliste für Fragen bearbeiten"))
        self.setModal(True)
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        info = QLabel(self.t("auto_answer_question_replies_editor_info", "Die JSON-Datei wird direkt aus dem App-Ordner geladen. Unter 'replies' können pro Sprache kurze Reaktionen hinterlegt werden, die verwendet werden, wenn die LLM eine Frage stellt. Optional können diese Antworten auch zusätzlich im normalen Auto-Answer-Pool mitverwendet werden."))
        info.setWordWrap(True)
        info.setObjectName("SubtleLabel")
        layout.addWidget(info)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("""{
  "enabled": true,
  "replies": {
    "de": ["Ja.", "Nein.", "Klingt gut."]
  }
}""")
        layout.addWidget(self.editor, 1)

        buttons = QHBoxLayout()
        self.reset_btn = QPushButton(self.t("reset_default", "Standard wiederherstellen"))
        self.reset_btn.clicked.connect(self.reset_to_default)
        buttons.addWidget(self.reset_btn)
        buttons.addStretch()

        cancel_btn = QPushButton(self.t("cancel", "Abbrechen"))
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton(self.t("save", "Speichern"))
        save_btn.setObjectName("AccentButton")
        save_btn.clicked.connect(self.save_and_accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)
        self.load_current()

    def t(self, key: str, default: Optional[str] = None) -> str:
        return self.translations.get(key, default or key)

    def load_current(self) -> None:
        ensure_directories()
        self.editor.setPlainText(AUTO_ANSWER_QUESTION_REPLY_PATH.read_text(encoding="utf-8"))

    def reset_to_default(self) -> None:
        reply = QMessageBox.question(
            self,
            self.t("reset_confirm_title", "Standard wiederherstellen"),
            self.t("reset_confirm_text", "Soll das Aussprache-Lexikon auf die Standardwerte zurückgesetzt werden?")
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if AUTO_ANSWER_QUESTION_REPLY_PATH.exists():
            AUTO_ANSWER_QUESTION_REPLY_PATH.unlink()
        ensure_directories()
        self.load_current()

    def save_and_accept(self) -> None:
        raw = self.editor.toPlainText().strip()
        if not raw:
            QMessageBox.warning(self, self.t("empty_question_replies_title", "Leere Datei"), self.t("empty_question_replies_text", "Die JSON-Datei darf nicht leer sein."))
            return
        try:
            data = json.loads(raw)
        except Exception as exc:
            QMessageBox.critical(self, self.t("invalid_json_title", "Ungültiges JSON"), self.t("invalid_json_text", "Die Datei ist kein gültiges JSON.\n\n{error}").format(error=exc))
            return
        if not isinstance(data, dict):
            QMessageBox.critical(self, self.t("invalid_format_title", "Ungültiges Format"), self.t("invalid_format_root", "Die oberste Ebene der Datei muss ein JSON-Objekt sein."))
            return
        ensure_directories()
        AUTO_ANSWER_QUESTION_REPLY_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.accept()


class AutoAnswerShortPromptDialog(QDialog):
    def __init__(self, config: dict, language_code: str = "de", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self.language_code = (language_code or "de").strip() or "de"
        self.translations = load_language_pack(self.language_code)
        self.setWindowTitle(self.t("auto_answer_short_prompt_dialog_title", "Zusatzprompt für kurze Auto-Answer-Antworten"))
        self.setModal(True)
        self.resize(720, 420)

        layout = QVBoxLayout(self)

        language_name = next((name for code, name in available_languages() if code == self.language_code), self.language_code)
        info = QLabel(
            self.t(
                "auto_answer_short_prompt_dialog_info",
                "Dieser Zusatzprompt wird unsichtbar an das LLM weitergegeben: beim ersten Nutzerbeitrag eines Chats und nach einem automatischen Folge-Chat noch einmal für den nächsten Nutzerbeitrag. Er gilt für die aktuell gewählte Oberflächensprache: {language}.",
            ).format(language=language_name)
        )
        info.setWordWrap(True)
        info.setObjectName("SubtleLabel")
        layout.addWidget(info)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(default_auto_answer_short_instruction(self.language_code))
        self.editor.setPlainText(auto_answer_short_instruction(self.config, self.language_code))
        layout.addWidget(self.editor, 1)

        buttons = QHBoxLayout()
        self.reset_btn = QPushButton(self.t("reset_default", "Standard wiederherstellen"))
        self.reset_btn.clicked.connect(self.reset_to_default)
        buttons.addWidget(self.reset_btn)
        buttons.addStretch()

        cancel_btn = QPushButton(self.t("cancel", "Abbrechen"))
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton(self.t("save", "Speichern"))
        save_btn.setObjectName("AccentButton")
        save_btn.clicked.connect(self.save_and_accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

    def t(self, key: str, default: Optional[str] = None) -> str:
        return self.translations.get(key, default or key)

    def reset_to_default(self) -> None:
        self.editor.setPlainText(default_auto_answer_short_instruction(self.language_code))

    def save_and_accept(self) -> None:
        value = self.editor.toPlainText().strip()
        if not value:
            value = default_auto_answer_short_instruction(self.language_code)
        overrides = dict(self.config.get("auto_answer_short_instruction_overrides", {}) or {})
        overrides[self.language_code] = value
        self.config["auto_answer_short_instruction_overrides"] = overrides
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent: Optional[QWidget] = None, open_tts_setup_callback: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.config = config.copy()
        self.translations = load_language_pack(self.config.get("interface_language", "de"))
        self.open_tts_setup_callback = open_tts_setup_callback
        self.setWindowTitle(self.t("settings_title", "Einstellungen"))
        self.setModal(True)
        self.resize(900, 820)
        self.setMinimumSize(860, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(self.scroll, 1)

        self.content = QWidget()
        self.content.setMinimumWidth(800)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(12)
        self.scroll.setWidget(self.content)

        def add_row(label_text: str, widget: QWidget) -> QWidget:
            container = QWidget()
            row = QVBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            label = QLabel(label_text)
            label.setObjectName("SubtleLabel")
            row.addWidget(label)
            row.addWidget(widget)
            self.content_layout.addWidget(container)
            return container

        self.interface_language = QComboBox()
        for code, display_name in available_languages():
            self.interface_language.addItem(display_name, code)
        current_lang = self.config.get("interface_language", "de")
        idx_lang = max(0, self.interface_language.findData(current_lang))
        self.interface_language.setCurrentIndex(idx_lang)
        add_row(self.t("interface_language_label", "Sprache der Oberfläche"), self.interface_language)
        self.interface_language.currentIndexChanged.connect(self._refresh_name_placeholders)
        self.interface_language.currentIndexChanged.connect(self.refresh_tts_voice_options)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(sorted(THEMES.keys()))
        self.theme_combo.setCurrentText(self.config.get("theme", "Midnight"))
        add_row(self.t("theme_label", "Theme"), self.theme_combo)

        self.ollama_url = QLineEdit(self.config["ollama_base_url"])
        add_row(self.t("ollama_base_url_label", "Ollama Base URL"), self.ollama_url)

        self.tts_backend = QComboBox()
        self.tts_backend.addItem(self.t("tts_backend_disabled", "disabled"), "disabled")
        self.tts_backend.addItem(self.t("tts_backend_windows_sapi", "windows_sapi (integrierte Windows-Stimmen)"), "windows_sapi")
        self.tts_backend.addItem(self.t("tts_backend_vibevoice", "vibevoice_openai (lokaler Wrapper)"), "vibevoice_openai")
        backend_value = self.config.get("tts_backend", "disabled")
        backend_index = max(0, self.tts_backend.findData(backend_value))
        self.tts_backend.setCurrentIndex(backend_index)
        add_row(self.t("tts_backend_label", "TTS Backend"), self.tts_backend)

        tts_tools_row = QHBoxLayout()
        self.open_tts_setup_btn = QPushButton(self.t("vibevoice_setup_open", "Open VibeVoice setup …"))
        self.open_tts_setup_btn.clicked.connect(self.open_tts_setup)
        tts_tools_row.addWidget(self.open_tts_setup_btn)
        tts_tools_row.addStretch(1)
        self.content_layout.addLayout(tts_tools_row)

        self.tts_hint = QLabel()
        self.tts_hint.setObjectName("SubtleLabel")
        self.tts_hint.setWordWrap(True)
        self.content_layout.addWidget(self.tts_hint)

        self.tts_url = QLineEdit(self.config["tts_base_url"])
        add_row(self.t("tts_base_url_label", "TTS Base URL"), self.tts_url)

        self.tts_voice = QComboBox()
        self.tts_voice.setEditable(False)
        self.tts_voice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.tts_voice.setMinimumContentsLength(28)
        self.tts_voice_row = add_row(self.t("tts_voice_label", "Sprecher / Stimme (Assistent)"), self.tts_voice)

        self.user_tts_voice = QComboBox()
        self.user_tts_voice.setEditable(False)
        self.user_tts_voice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.user_tts_voice.setMinimumContentsLength(28)
        self.user_tts_voice_row = add_row(self.t("tts_user_voice_label", "Sprecher / Stimme (Benutzer)"), self.user_tts_voice)

        self.tts_model = QComboBox()
        self.tts_model.setEditable(True)
        self.tts_model.addItems(["tts-1-hd", "tts-1"])
        current_tts_model = str(self.config.get("tts_model", "tts-1-hd") or "tts-1-hd")
        if self.tts_model.findText(current_tts_model) < 0:
            self.tts_model.addItem(current_tts_model)
        self.tts_model.setCurrentText(current_tts_model)
        self.tts_model.setToolTip(self.t("tts_model_tooltip", "Relevant only for VibeVoice/OpenAI-compatible TTS backends. In most cases you can leave this at 'tts-1-hd'."))
        self.tts_model_row = add_row(self.t("tts_model_label", "TTS model"), self.tts_model)

        self.autoplay = QCheckBox(self.t("autoplay_label", "Audio nach dem Erzeugen direkt abspielen"))
        self.autoplay.setChecked(bool(self.config.get("autoplay_tts", True)))
        self.content_layout.addWidget(self.autoplay)

        self.auto_read_responses = QCheckBox(self.t("auto_read_label", "Jede neue Assistent-Antwort automatisch vorlesen"))
        self.auto_read_responses.setChecked(bool(self.config.get("auto_read_assistant_responses", True)))
        self.auto_read_responses.setToolTip(self.t("auto_read_tooltip", "Wenn aktiv, wird nach jeder neuen Assistent-Antwort automatisch TTS erzeugt und abgespielt."))
        self.content_layout.addWidget(self.auto_read_responses)

        self.auto_read_user_inputs = QCheckBox(self.t("auto_read_user_inputs_label", "Eigene manuell gesendete Texte nach dem Senden automatisch vorlesen"))
        self.auto_read_user_inputs.setChecked(bool(self.config.get("auto_read_user_inputs", True)))
        self.auto_read_user_inputs.setToolTip(self.t("auto_read_user_inputs_tooltip", "Wenn aktiv, werden manuell eingegebene Benutzertexte direkt nach der Übergabe an das LLM automatisch vorgelesen."))
        self.content_layout.addWidget(self.auto_read_user_inputs)

        self.read_all_include_names = QCheckBox(self.t("read_all_include_names_label", "Bei 'Alles vorlesen' Sprecher-Namen mit vorlesen"))
        self.read_all_include_names.setChecked(bool(self.config.get("read_all_include_names", False)))
        self.content_layout.addWidget(self.read_all_include_names)

        user_default_name, assistant_default_name = default_role_names(self.config.get("interface_language", "de"))
        self.user_display_name = QLineEdit((self.config.get("user_display_name", "") or "").strip())
        self.user_display_name.setPlaceholderText(user_default_name)
        add_row(self.t("user_display_name_label", "Anzeigename für dich"), self.user_display_name)

        self.assistant_display_name = QLineEdit((self.config.get("assistant_display_name", "") or "").strip())
        self.assistant_display_name.setPlaceholderText(assistant_default_name)
        add_row(self.t("assistant_display_name_label", "Anzeigename für den Assistenten"), self.assistant_display_name)

        auto_answer_row = QHBoxLayout()
        auto_answer_info = QLabel(self.t("auto_answer_settings_hint", "Bearbeite zusätzliche automatische Antwortsätze für den ELIZA-Modus."))
        auto_answer_info.setObjectName("SubtleLabel")
        auto_answer_info.setWordWrap(True)
        auto_answer_row.addWidget(auto_answer_info, 1)
        self.edit_auto_answer_btn = QPushButton(self.t("edit_auto_answer_phrases", "Auto-Answer-Sätze bearbeiten …"))
        self.edit_auto_answer_btn.clicked.connect(self.edit_auto_answer_phrases)
        auto_answer_row.addWidget(self.edit_auto_answer_btn)
        self.content_layout.addLayout(auto_answer_row)

        question_replies_row = QHBoxLayout()
        question_replies_info = QLabel(self.t("auto_answer_question_replies_settings_hint", "Bearbeite kurze Reaktionen für den Fall, dass die LLM eine Frage stellt."))
        question_replies_info.setObjectName("SubtleLabel")
        question_replies_info.setWordWrap(True)
        question_replies_row.addWidget(question_replies_info, 1)
        self.edit_auto_answer_question_replies_btn = QPushButton(self.t("edit_auto_answer_question_replies", "Antwortliste für Fragen bearbeiten …"))
        self.edit_auto_answer_question_replies_btn.clicked.connect(self.edit_auto_answer_question_replies)
        question_replies_row.addWidget(self.edit_auto_answer_question_replies_btn)
        self.content_layout.addLayout(question_replies_row)

        self.auto_answer_use_question_replies_for_all = QCheckBox(self.t("auto_answer_use_question_replies_for_all_label", "Frage-Antwort-Liste auch für normale Auto-Answer-Antworten mitverwenden"))
        self.auto_answer_use_question_replies_for_all.setChecked(bool(self.config.get("auto_answer_use_question_replies_for_all", True)))
        self.auto_answer_use_question_replies_for_all.setToolTip(self.t("auto_answer_use_question_replies_for_all_tooltip", "Wenn aktiv, dürfen die Antworten aus auto_answer_question_replies.json nicht nur bei Fragen, sondern zusätzlich auch im normalen Auto-Answer-Pool vorkommen. Bei echten Fragen wird diese Liste weiterhin bevorzugt verwendet."))
        self.content_layout.addWidget(self.auto_answer_use_question_replies_for_all)

        lexicon_row = QHBoxLayout()
        self.tts_lexicon = QCheckBox(self.t("tts_lexicon_label", "TTS Aussprache-Lexikon verwenden"))
        self.tts_lexicon.setChecked(bool(self.config.get("tts_lexicon_enabled", self.config.get("windows_sapi_lexicon_enabled", True))))
        self.tts_lexicon.setToolTip(self.t("tts_lexicon_tooltip", "Wendet vor dem Vorlesen ein lokales JSON-Lexikon auf den bereinigten Text an."))
        lexicon_row.addWidget(self.tts_lexicon, 1)
        self.edit_sapi_lexicon_btn = QPushButton(self.t("edit_lexicon", "Lexikon bearbeiten …"))
        self.edit_sapi_lexicon_btn.clicked.connect(self.edit_sapi_lexicon)
        lexicon_row.addWidget(self.edit_sapi_lexicon_btn)
        self.content_layout.addLayout(lexicon_row)

        self.strip_emojis = QCheckBox(self.t("strip_emojis_label", "Keine Emojis mit vorlesen"))
        self.strip_emojis.setChecked(bool(self.config.get("strip_emojis_for_tts", True)))
        self.strip_emojis.setToolTip(self.t("strip_emojis_tooltip", "Entfernt Emojis und einfache Emoticons aus dem Vorlesetext, bevor TTS erzeugt wird."))
        self.content_layout.addWidget(self.strip_emojis)

        short_answers_row = QHBoxLayout()
        self.auto_answer_short_answers = QCheckBox(self.t("auto_answer_short_answers_label", "Kurze Antworten im Auto-Answer-Modus"))
        self.auto_answer_short_answers.setChecked(bool(self.config.get("auto_answer_short_answers", True)))
        self.auto_answer_short_answers.setToolTip(self.t("auto_answer_short_answers_tooltip", "Fügt unsichtbar einen Zusatzhinweis hinzu: beim ersten Nutzerbeitrag eines Chats und nach einem automatischen Folge-Chat noch einmal für den nächsten Nutzerbeitrag, damit das Modell kurz und zusammenfassend antwortet."))
        short_answers_row.addWidget(self.auto_answer_short_answers, 1)
        self.edit_auto_answer_short_prompt_btn = QPushButton(self.t("edit_auto_answer_short_prompt", "Zusatzprompt bearbeiten …"))
        self.edit_auto_answer_short_prompt_btn.clicked.connect(self.edit_auto_answer_short_prompt)
        short_answers_row.addWidget(self.edit_auto_answer_short_prompt_btn)
        self.content_layout.addLayout(short_answers_row)

        self.debug_trace_enabled = QCheckBox(self.t("debug_trace_enabled_label", "Detailliertes Debug-Log schreiben"))
        self.debug_trace_enabled.setChecked(bool(self.config.get("debug_trace_enabled", False)))
        self.debug_trace_enabled.setToolTip(self.t("debug_trace_enabled_tooltip", "Schreibt eine zusätzliche JSONL-Debugdatei in app_data/debug_logs mit Chat-Verlauf, geschätzten Tokenwerten, Request-Daten, Folge-Chat-Wechseln und den dabei aktiven Einstellungen. Diese Datei kann später zur Fehlersuche geschickt werden."))
        self.content_layout.addWidget(self.debug_trace_enabled)

        limits_frame = QFrame()
        limits_layout = QVBoxLayout(limits_frame)
        limits_layout.setContentsMargins(0, 8, 0, 0)
        limits_layout.setSpacing(8)
        limits_title = QLabel(self.t("limits_group_title", "Antwort- und Auto-Answer-Grenzen"))
        limits_title.setObjectName("SubtleLabel")
        limits_layout.addWidget(limits_title)

        token_label_row = QHBoxLayout()
        token_label_row.addWidget(QLabel(self.t("chat_max_tokens_label", "Maximale Antwortlänge (Tokens)")), 1)
        self.chat_max_tokens = QSpinBox()
        self.chat_max_tokens.setRange(TOKEN_PRESET_VALUES[0], TOKEN_PRESET_VALUES[-1])
        self.chat_max_tokens.setSingleStep(64)
        self.chat_max_tokens.setValue(int(self.config.get("chat_max_tokens", 1024) or 1024))
        self.chat_max_tokens.setToolTip(self.t("chat_max_tokens_tooltip", "Begrenzt die maximale Antwortlänge des LLM. Kleinere Werte können lange Auto-Answer-Schleifen stabiler machen."))
        token_label_row.addWidget(self.chat_max_tokens)
        limits_layout.addLayout(token_label_row)

        token_slider_row = QHBoxLayout()
        token_slider_hint = QLabel(self.t("chat_max_tokens_slider_hint", "Typische Schritte"))
        token_slider_hint.setObjectName("SubtleLabel")
        token_slider_row.addWidget(token_slider_hint)
        self.chat_max_tokens_slider = QSlider(Qt.Orientation.Horizontal)
        self.chat_max_tokens_slider.setRange(0, len(TOKEN_PRESET_VALUES) - 1)
        self.chat_max_tokens_slider.setPageStep(1)
        self.chat_max_tokens_slider.setSingleStep(1)
        self.chat_max_tokens_slider.setTickInterval(1)
        self.chat_max_tokens_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.chat_max_tokens_slider.setValue(nearest_token_preset_index(self.chat_max_tokens.value()))
        token_slider_row.addWidget(self.chat_max_tokens_slider, 1)
        self.chat_max_tokens_slider_value = QLabel()
        self.chat_max_tokens_slider_value.setMinimumWidth(70)
        self.chat_max_tokens_slider_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        token_slider_row.addWidget(self.chat_max_tokens_slider_value)
        limits_layout.addLayout(token_slider_row)

        self._chat_tokens_syncing = False
        self.chat_max_tokens.valueChanged.connect(self._sync_chat_tokens_slider_from_spinbox)
        self.chat_max_tokens_slider.valueChanged.connect(self._sync_chat_tokens_spinbox_from_slider)
        self._update_chat_tokens_slider_label(self.chat_max_tokens.value())

        rounds_row = QHBoxLayout()
        rounds_row.addWidget(QLabel(self.t("auto_answer_rounds_label", "Maximale Auto-Answer-Runden (0 = unbegrenzt)")), 1)
        self.auto_answer_rounds = QSpinBox()
        self.auto_answer_rounds.setRange(0, 999)
        self.auto_answer_rounds.setValue(int(self.config.get("auto_answer_max_rounds", 0) or 0))
        self.auto_answer_rounds.setToolTip(self.t("auto_answer_rounds_tooltip", "Begrenzt, wie oft Auto Answer hintereinander antworten darf. 0 bedeutet unbegrenzt."))
        rounds_row.addWidget(self.auto_answer_rounds)
        limits_layout.addLayout(rounds_row)

        eliza_label = QLabel(self.t("auto_answer_eliza_share_label", "ELIZA-Anteil gegenüber Standardsätzen"))
        eliza_label.setObjectName("SubtleLabel")
        limits_layout.addWidget(eliza_label)
        eliza_slider_row = QHBoxLayout()
        self.auto_answer_eliza_share = QSlider(Qt.Orientation.Horizontal)
        self.auto_answer_eliza_share.setRange(0, 100)
        self.auto_answer_eliza_share.setSingleStep(5)
        self.auto_answer_eliza_share.setPageStep(10)
        self.auto_answer_eliza_share.setTickInterval(10)
        self.auto_answer_eliza_share.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.auto_answer_eliza_share.setValue(int(self.config.get("auto_answer_eliza_share", 30) or 30))
        eliza_slider_row.addWidget(self.auto_answer_eliza_share, 1)
        self.auto_answer_eliza_share_value = QLabel()
        self.auto_answer_eliza_share_value.setMinimumWidth(118)
        self.auto_answer_eliza_share_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        eliza_slider_row.addWidget(self.auto_answer_eliza_share_value)
        limits_layout.addLayout(eliza_slider_row)

        def _refresh_eliza_share_label(value: int) -> None:
            self.auto_answer_eliza_share_value.setText(f"ELIZA {int(value)}% / {100 - int(value)}% Pool")

        _refresh_eliza_share_label(self.auto_answer_eliza_share.value())
        self.auto_answer_eliza_share.valueChanged.connect(_refresh_eliza_share_label)

        phrase_repeat_row = QHBoxLayout()
        phrase_repeat_row.addWidget(QLabel(self.t("auto_answer_phrase_repeat_lookback_label", "Wie viele letzte Auto-Answer-Benutzertexte nicht wiederholt werden dürfen")), 1)
        self.auto_answer_phrase_repeat_lookback = QSpinBox()
        self.auto_answer_phrase_repeat_lookback.setRange(0, 50)
        self.auto_answer_phrase_repeat_lookback.setValue(int(self.config.get("auto_answer_phrase_repeat_lookback", 4) or 4))
        self.auto_answer_phrase_repeat_lookback.setToolTip(self.t("auto_answer_phrase_repeat_lookback_tooltip", "Bei Standardsätzen werden die letzten automatisch erzeugten Benutzertexte berücksichtigt. Wenn nicht genug verschiedene Standardsätze übrig bleiben, wird automatisch ELIZA verwendet."))
        phrase_repeat_row.addWidget(self.auto_answer_phrase_repeat_lookback)
        limits_layout.addLayout(phrase_repeat_row)

        context_row = QHBoxLayout()
        context_row.addWidget(QLabel(self.t("context_limit_label", "Kontextfenster für Antworten (Nachrichten)")), 1)
        self.context_limit = QSpinBox()
        self.context_limit.setRange(6, 200)
        self.context_limit.setValue(int(self.config.get("context_message_limit", 8) or 8))
        self.context_limit.setToolTip(self.t("context_limit_tooltip", "Nur die letzten N Nachrichten werden an das Modell gesendet. Das kann längere Auto-Answer-Gespräche stabiler machen."))
        context_row.addWidget(self.context_limit)
        limits_layout.addLayout(context_row)

        rollover_row = QHBoxLayout()
        rollover_row.addWidget(QLabel(self.t("rollover_carry_messages_label", "Letzte Dialogeinträge für Folge-Chat")), 1)
        self.rollover_carry_messages = QSpinBox()
        self.rollover_carry_messages.setRange(2, 40)
        self.rollover_carry_messages.setValue(int(self.config.get("rollover_carry_messages", AUTO_ANSWER_ROLLOVER_CARRY_MESSAGES) or AUTO_ANSWER_ROLLOVER_CARRY_MESSAGES))
        self.rollover_carry_messages.setToolTip(self.t("rollover_carry_messages_tooltip", "Wie viele der letzten Chat-Einträge beim automatischen Folge-Chat übernommen werden. Falls der Kontext trotzem zu groß wäre, wird zusätzlich automatisch weiter gekürzt."))
        rollover_row.addWidget(self.rollover_carry_messages)
        limits_layout.addLayout(rollover_row)

        self.content_layout.addWidget(limits_frame)

        self.sapi_group = QFrame()
        sapi_layout = QVBoxLayout(self.sapi_group)
        sapi_layout.setContentsMargins(0, 8, 0, 0)
        sapi_title = QLabel(self.t("windows_sapi_group_title", "Windows-SAPI Feinabstimmung"))
        sapi_title.setObjectName("SubtleLabel")
        sapi_layout.addWidget(sapi_title)

        self.sapi_rate_slider, self.sapi_rate_label_value = self._make_slider_row(
            sapi_layout,
            self.t("sapi_rate_label", "Sprechgeschwindigkeit"),
            -10,
            10,
            int(self.config.get("windows_sapi_rate", 0)),
            self.t("sapi_value_default", "Standard"),
        )
        self.sapi_pitch_slider, self.sapi_pitch_label_value = self._make_slider_row(
            sapi_layout,
            self.t("sapi_pitch_label", "Tonhöhe"),
            -10,
            10,
            int(self.config.get("windows_sapi_pitch", 0)),
            self.t("sapi_value_default", "Standard"),
        )
        self.sapi_volume_slider, self.sapi_volume_label_value = self._make_slider_row(
            sapi_layout,
            self.t("sapi_volume_label", "Lautstärke"),
            0,
            100,
            int(self.config.get("windows_sapi_volume", 100)),
            None,
        )
        self.content_layout.addWidget(self.sapi_group)

        self.system_prompt = QPlainTextEdit(self.config.get("system_prompt", ""))
        self.system_prompt.setPlaceholderText(self.t("system_prompt_placeholder", "Optionaler System-Prompt für neue Anfragen"))
        self.system_prompt.setFixedHeight(110)
        add_row(self.t("system_prompt_label", "System-Prompt"), self.system_prompt)

        profile_row = QHBoxLayout()
        profile_info = QLabel(self.t("settings_profile_hint", "Konfigurationen laden oder speichern, inklusive System-Prompt und Zusatzprompt-Einstellungen."))
        profile_info.setObjectName("SubtleLabel")
        profile_info.setWordWrap(True)
        profile_row.addWidget(profile_info, 1)
        self.load_settings_profile_btn = QPushButton(self.t("load_settings_profile", "Konfiguration laden …"))
        self.load_settings_profile_btn.clicked.connect(self.load_settings_profile)
        profile_row.addWidget(self.load_settings_profile_btn)
        self.save_settings_profile_btn = QPushButton(self.t("save_settings_profile", "Konfiguration speichern …"))
        self.save_settings_profile_btn.clicked.connect(self.save_settings_profile)
        profile_row.addWidget(self.save_settings_profile_btn)
        self.content_layout.addLayout(profile_row)

        self.content_layout.addStretch(1)

        self.tts_backend.currentIndexChanged.connect(self.refresh_tts_voice_options)
        self.refresh_tts_voice_options()

        buttons = QHBoxLayout()
        buttons.addStretch()
        save_btn = QPushButton(self.t("save", "Speichern"))
        save_btn.setObjectName("AccentButton")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(self.t("cancel", "Abbrechen"))
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        root.addLayout(buttons)

    def t(self, key: str, default: Optional[str] = None) -> str:
        return self.translations.get(key, default or key)

    def _make_slider_row(self, parent_layout: QVBoxLayout, title: str, minimum: int, maximum: int, value: int, zero_label: Optional[str]) -> tuple[QSlider, QLabel]:
        label = QLabel(title)
        label.setObjectName("SubtleLabel")
        parent_layout.addWidget(label)
        row = QHBoxLayout()
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        value_label = QLabel()
        value_label.setMinimumWidth(70)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        def refresh(v: int) -> None:
            if zero_label is not None and v == 0:
                value_label.setText(zero_label)
            else:
                value_label.setText(str(v))

        refresh(value)
        slider.valueChanged.connect(refresh)
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        parent_layout.addLayout(row)
        return slider, value_label

    def _update_chat_tokens_slider_label(self, value: int) -> None:
        if not hasattr(self, "chat_max_tokens_slider_value"):
            return
        nearest_value = TOKEN_PRESET_VALUES[nearest_token_preset_index(value)]
        label = format_token_value(nearest_value)
        if nearest_value != int(value):
            label += f" (~ {value})"
        self.chat_max_tokens_slider_value.setText(label)

    def _sync_chat_tokens_slider_from_spinbox(self, value: int) -> None:
        self._update_chat_tokens_slider_label(value)
        if getattr(self, "_chat_tokens_syncing", False) or not hasattr(self, "chat_max_tokens_slider"):
            return
        self._chat_tokens_syncing = True
        try:
            self.chat_max_tokens_slider.setValue(nearest_token_preset_index(value))
        finally:
            self._chat_tokens_syncing = False

    def _sync_chat_tokens_spinbox_from_slider(self, index: int) -> None:
        if getattr(self, "_chat_tokens_syncing", False) or not hasattr(self, "chat_max_tokens"):
            return
        preset_value = TOKEN_PRESET_VALUES[max(0, min(index, len(TOKEN_PRESET_VALUES) - 1))]
        self._chat_tokens_syncing = True
        try:
            self.chat_max_tokens.setValue(preset_value)
            self._update_chat_tokens_slider_label(preset_value)
        finally:
            self._chat_tokens_syncing = False

    def current_tts_backend(self) -> str:
        return (self.tts_backend.currentData() or self.tts_backend.currentText() or "disabled").strip()

    def _combo_value(self, combo: QComboBox) -> str:
        idx = combo.currentIndex()
        current_text = combo.currentText().strip()
        if idx >= 0 and current_text == combo.itemText(idx):
            data = combo.itemData(idx)
            if isinstance(data, str) and data.strip():
                return data.strip()
        return current_text

    def _current_voice_value(self) -> str:
        return self._combo_value(self.tts_voice)

    def _current_user_voice_value(self) -> str:
        return self._combo_value(self.user_tts_voice)

    def _apply_voice_selection(self, combo: QComboBox, voice_entries: list[tuple[str, str]], final_voice: str, backend: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        for value, label in voice_entries:
            combo.addItem(label, value)
        if final_voice:
            selected_index = -1
            for i in range(combo.count()):
                item_data = combo.itemData(i)
                item_text = combo.itemText(i)
                if item_data == final_voice or item_text == final_voice:
                    selected_index = i
                    break
                if backend == "windows_sapi" and not str(final_voice).startswith(("sapi::", "onecore::")):
                    if item_data == TTSClient.make_sapi_voice_id(final_voice) or item_text.startswith(final_voice + " "):
                        selected_index = i
                        break
            if selected_index >= 0:
                combo.setCurrentIndex(selected_index)
            else:
                combo.addItem(final_voice, final_voice)
                combo.setCurrentText(final_voice)
        combo.blockSignals(False)

    def refresh_tts_voice_options(self) -> None:
        backend = self.current_tts_backend()
        current_voice = self._current_voice_value() or self.config.get("tts_voice", "")
        current_user_voice = self._current_user_voice_value() or self.config.get("tts_user_voice", "") or current_voice
        if backend == "vibevoice_openai":
            if str(current_voice).startswith(("sapi::", "onecore::")):
                current_voice = ""
            if str(current_user_voice).startswith(("sapi::", "onecore::")):
                current_user_voice = ""
        hint = ""
        default_voice = "Emma"
        voice_entries: list[tuple[str, str]] = []

        if backend == "windows_sapi":
            hint = self.t("tts_hint_windows_sapi", "Verwendet Windows-Desktop-SAPI und zusätzlich erkannte Windows-/OneCore-Stimmen. Kein externer Download nötig.")
            default_voice = ""
        elif backend == "vibevoice_openai":
            hint = self.t("tts_hint_vibevoice", "Benötigt den lokalen VibeVoice-Wrapper. Stimmen aus app_data/tts/vibevoice_openai/models/voices werden zusätzlich erkannt; falls sie nur als lokale Datei erscheinen, den Wrapper einmal neu starten. Zusätzliche offizielle Presets werden beim VibeVoice-Install/Update automatisch mitgeladen.")
            default_voice = "Emma"
        else:
            hint = self.t("tts_hint_disabled", "TTS ist deaktiviert.")

        try:
            client = TTSClient(
                backend=backend,
                base_url=self.tts_url.text().strip() or self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"),
                voice=current_voice or self.config.get("tts_voice", default_voice),
                model=self.tts_model.currentText().strip() or self.config.get("tts_model", "tts-1-hd"),
                audio_format=self.config.get("tts_format", "wav"),
            )
            voice_entries = client.list_voice_entries()
        except Exception as exc:
            if backend == "windows_sapi":
                hint += " " + self.t("tts_windows_voices_error", "Stimmen konnten gerade nicht gelesen werden: {error}").format(error=exc)
            elif backend == "vibevoice_openai":
                hint += " " + self.t("tts_wrapper_not_running", "Der Wrapper scheint aktuell nicht zu laufen oder ist noch nicht eingerichtet.")

        self.tts_hint.setText(hint)
        config_voice = self.config.get("tts_voice", default_voice)
        config_user_voice = self.config.get("tts_user_voice", "") or config_voice
        if backend == "vibevoice_openai" and str(config_voice).startswith(("sapi::", "onecore::")):
            config_voice = default_voice
        if backend == "vibevoice_openai" and str(config_user_voice).startswith(("sapi::", "onecore::")):
            config_user_voice = config_voice
        if backend == "windows_sapi" and voice_entries:
            language_code = (self.interface_language.currentData() or self.config.get("interface_language", "de") or "de").strip()
            if not str(config_voice).strip():
                config_voice = pick_preferred_windows_voice(voice_entries, language_code, "assistant")
            if not str(config_user_voice).strip() or str(config_user_voice).strip() == str(config_voice).strip():
                config_user_voice = pick_preferred_windows_voice(voice_entries, language_code, "user", avoid_value=str(config_voice))
        final_voice = current_voice or config_voice
        final_user_voice = current_user_voice or config_user_voice
        self._apply_voice_selection(self.tts_voice, voice_entries, final_voice, backend)
        self._apply_voice_selection(self.user_tts_voice, voice_entries, final_user_voice, backend)
        visible = backend != "disabled"
        self.tts_voice_row.setVisible(visible)
        self.user_tts_voice_row.setVisible(visible)
        self.tts_model_row.setVisible(backend == "vibevoice_openai")
        self.sapi_group.setVisible(backend == "windows_sapi")
        self.open_tts_setup_btn.setVisible(backend == "vibevoice_openai")

    def open_tts_setup(self) -> None:
        if self.open_tts_setup_callback is None:
            QMessageBox.information(self, self.t("tts_setup_unavailable_title", "TTS-Setup"), self.t("tts_setup_unavailable_text", "Der TTS-Setup-Assistent ist hier nicht verfügbar."))
            return
        self.open_tts_setup_callback()

    def edit_sapi_lexicon(self) -> None:
        dialog = LexiconEditorDialog(self.config.get("interface_language", "de"), self)
        dialog.exec()

    def edit_auto_answer_phrases(self) -> None:
        dialog = AutoAnswerPhrasesDialog(self.current_settings_language_code(), self)
        dialog.exec()

    def edit_auto_answer_question_replies(self) -> None:
        dialog = AutoAnswerQuestionRepliesDialog(self.current_settings_language_code(), self)
        dialog.exec()

    def current_settings_language_code(self) -> str:
        return (self.interface_language.currentData() or self.config.get("interface_language", "de") or "de").strip() or "de"

    def edit_auto_answer_short_prompt(self) -> None:
        dialog = AutoAnswerShortPromptDialog(self.config, self.current_settings_language_code(), self)
        dialog.exec()

    def _refresh_name_placeholders(self) -> None:
        lang = (self.interface_language.currentData() or self.config.get("interface_language", "de") or "de").strip()
        user_default, assistant_default = default_role_names(lang)
        self.user_display_name.setPlaceholderText(user_default)
        self.assistant_display_name.setPlaceholderText(assistant_default)

    def _set_combo_data_value(self, combo: QComboBox, value: str, fallback_index: int = 0) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else fallback_index)

    def _set_combo_text_value(self, combo: QComboBox, value: str) -> None:
        if combo.findText(value) < 0 and combo.isEditable() and value:
            combo.addItem(value)
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.isEditable():
            combo.setCurrentText(value)

    def apply_config_to_widgets(self, profile_data: dict) -> None:
        merged = DEFAULT_CONFIG.copy()
        merged.update(profile_data or {})
        if "tts_lexicon_enabled" not in merged:
            merged["tts_lexicon_enabled"] = bool(merged.get("windows_sapi_lexicon_enabled", True))
        merged["windows_sapi_lexicon_enabled"] = bool(merged.get("tts_lexicon_enabled", True))
        if not merged.get("tts_user_voice"):
            merged["tts_user_voice"] = merged.get("tts_voice", "")

        self.config = merged
        self.translations = load_language_pack(merged.get("interface_language", "de"))

        self._set_combo_data_value(self.interface_language, merged.get("interface_language", "de"), 0)
        self._set_combo_text_value(self.theme_combo, str(merged.get("theme", "Midnight") or "Midnight"))
        self.ollama_url.setText(str(merged.get("ollama_base_url", DEFAULT_CONFIG["ollama_base_url"]) or DEFAULT_CONFIG["ollama_base_url"]))
        self._set_combo_data_value(self.tts_backend, merged.get("tts_backend", "disabled"), 0)
        self.tts_url.setText(str(merged.get("tts_base_url", DEFAULT_CONFIG["tts_base_url"]) or DEFAULT_CONFIG["tts_base_url"]))
        self._set_combo_text_value(self.tts_model, str(merged.get("tts_model", DEFAULT_CONFIG["tts_model"]) or DEFAULT_CONFIG["tts_model"]))

        self.autoplay.setChecked(bool(merged.get("autoplay_tts", True)))
        self.auto_read_responses.setChecked(bool(merged.get("auto_read_assistant_responses", True)))
        self.auto_read_user_inputs.setChecked(bool(merged.get("auto_read_user_inputs", DEFAULT_CONFIG["auto_read_user_inputs"])))
        self.read_all_include_names.setChecked(bool(merged.get("read_all_include_names", False)))
        self.user_display_name.setText(str(merged.get("user_display_name", "") or ""))
        self.assistant_display_name.setText(str(merged.get("assistant_display_name", "") or ""))
        self.tts_lexicon.setChecked(bool(merged.get("tts_lexicon_enabled", True)))
        self.strip_emojis.setChecked(bool(merged.get("strip_emojis_for_tts", True)))
        self.auto_answer_short_answers.setChecked(bool(merged.get("auto_answer_short_answers", True)))
        self.auto_answer_use_question_replies_for_all.setChecked(bool(merged.get("auto_answer_use_question_replies_for_all", True)))
        self.debug_trace_enabled.setChecked(bool(merged.get("debug_trace_enabled", False)))
        self.chat_max_tokens.setValue(int(merged.get("chat_max_tokens", DEFAULT_CONFIG["chat_max_tokens"]) or DEFAULT_CONFIG["chat_max_tokens"]))
        self.auto_answer_rounds.setValue(int(merged.get("auto_answer_max_rounds", DEFAULT_CONFIG["auto_answer_max_rounds"]) or DEFAULT_CONFIG["auto_answer_max_rounds"]))
        self.auto_answer_eliza_share.setValue(int(merged.get("auto_answer_eliza_share", DEFAULT_CONFIG["auto_answer_eliza_share"]) or DEFAULT_CONFIG["auto_answer_eliza_share"]))
        self.auto_answer_phrase_repeat_lookback.setValue(int(merged.get("auto_answer_phrase_repeat_lookback", DEFAULT_CONFIG["auto_answer_phrase_repeat_lookback"]) or DEFAULT_CONFIG["auto_answer_phrase_repeat_lookback"]))
        self.context_limit.setValue(int(merged.get("context_message_limit", DEFAULT_CONFIG["context_message_limit"]) or DEFAULT_CONFIG["context_message_limit"]))
        self.rollover_carry_messages.setValue(int(merged.get("rollover_carry_messages", DEFAULT_CONFIG["rollover_carry_messages"]) or DEFAULT_CONFIG["rollover_carry_messages"]))
        self.sapi_rate_slider.setValue(int(merged.get("windows_sapi_rate", 0) or 0))
        self.sapi_pitch_slider.setValue(int(merged.get("windows_sapi_pitch", DEFAULT_CONFIG["windows_sapi_pitch"]) or DEFAULT_CONFIG["windows_sapi_pitch"]))
        self.sapi_volume_slider.setValue(int(merged.get("windows_sapi_volume", 100) or 100))
        self.system_prompt.setPlainText(str(merged.get("system_prompt", "") or ""))

        self._refresh_name_placeholders()
        self.tts_voice.clear()
        self.user_tts_voice.clear()
        self.refresh_tts_voice_options()

    def save_settings_profile(self) -> None:
        ensure_directories()
        default_name = SETTINGS_PROFILE_DIR / f"ollamavibedesk_profile_{datetime.now():%Y%m%d-%H%M%S}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.t("save_settings_profile_dialog_title", "Konfiguration speichern"),
            str(default_name),
            self.t("json_files_filter", "JSON-Dateien (*.json);;Alle Dateien (*)"),
        )
        if not file_path:
            return
        profile_data = self.get_config()
        try:
            Path(file_path).write_text(json.dumps(profile_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, self.t("save_settings_profile_failed_title", "Konfiguration konnte nicht gespeichert werden"), self.t("save_settings_profile_failed_text", "Die Konfiguration konnte nicht gespeichert werden.\n\n{error}").format(error=exc))
            return
        QMessageBox.information(self, self.t("save_settings_profile_done_title", "Konfiguration gespeichert"), self.t("save_settings_profile_done_text", "Die Konfiguration wurde gespeichert:\n{path}").format(path=file_path))

    def load_settings_profile(self) -> None:
        ensure_directories()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.t("load_settings_profile_dialog_title", "Konfiguration laden"),
            str(SETTINGS_PROFILE_DIR),
            self.t("json_files_filter", "JSON-Dateien (*.json);;Alle Dateien (*)"),
        )
        if not file_path:
            return
        try:
            raw = Path(file_path).read_text(encoding="utf-8")
            profile_data = json.loads(raw)
        except Exception as exc:
            QMessageBox.critical(self, self.t("load_settings_profile_failed_title", "Konfiguration konnte nicht geladen werden"), self.t("load_settings_profile_failed_text", "Die Konfiguration konnte nicht geladen werden.\n\n{error}").format(error=exc))
            return
        if not isinstance(profile_data, dict):
            QMessageBox.warning(self, self.t("load_settings_profile_invalid_title", "Ungültige Konfiguration"), self.t("load_settings_profile_invalid_text", "Die Datei enthält kein JSON-Objekt mit Einstellungen."))
            return
        self.apply_config_to_widgets(profile_data)
        QMessageBox.information(self, self.t("load_settings_profile_done_title", "Konfiguration geladen"), self.t("load_settings_profile_done_text", "Die Konfiguration wurde in den Dialog übernommen. Mit Speichern wird sie aktiv.\n{path}").format(path=file_path))

    def get_config(self) -> dict:
        data = self.config.copy()
        data["interface_language"] = (self.interface_language.currentData() or "de").strip()
        data["theme"] = (self.theme_combo.currentText().strip() or "Midnight")
        data["ollama_base_url"] = self.ollama_url.text().strip()
        data["tts_backend"] = self.current_tts_backend()
        data["tts_base_url"] = self.tts_url.text().strip()
        voice_value = self._current_voice_value()
        user_voice_value = self._current_user_voice_value()
        if data["tts_backend"] == "windows_sapi":
            data["tts_voice"] = voice_value
            data["tts_user_voice"] = user_voice_value or voice_value
            data["tts_format"] = "wav"
        else:
            data["tts_voice"] = voice_value or "Emma"
            data["tts_user_voice"] = user_voice_value or data["tts_voice"]
        data["tts_model"] = self.tts_model.currentText().strip() or "tts-1-hd"
        data["autoplay_tts"] = self.autoplay.isChecked()
        data["auto_read_assistant_responses"] = self.auto_read_responses.isChecked()
        data["auto_read_user_inputs"] = self.auto_read_user_inputs.isChecked()
        data["read_all_include_names"] = self.read_all_include_names.isChecked()
        data["user_display_name"] = self.user_display_name.text().strip()
        data["assistant_display_name"] = self.assistant_display_name.text().strip()
        data["tts_lexicon_enabled"] = self.tts_lexicon.isChecked()
        data["windows_sapi_lexicon_enabled"] = data["tts_lexicon_enabled"]
        data["strip_emojis_for_tts"] = self.strip_emojis.isChecked()
        data["auto_answer_short_answers"] = self.auto_answer_short_answers.isChecked()
        data["auto_answer_use_question_replies_for_all"] = self.auto_answer_use_question_replies_for_all.isChecked()
        data["debug_trace_enabled"] = self.debug_trace_enabled.isChecked()
        data["chat_max_tokens"] = int(self.chat_max_tokens.value())
        data["auto_answer_max_rounds"] = int(self.auto_answer_rounds.value())
        data["auto_answer_eliza_share"] = int(self.auto_answer_eliza_share.value())
        data["auto_answer_phrase_repeat_lookback"] = int(self.auto_answer_phrase_repeat_lookback.value())
        data["context_message_limit"] = int(self.context_limit.value())
        data["rollover_carry_messages"] = int(self.rollover_carry_messages.value())
        data["windows_sapi_rate"] = int(self.sapi_rate_slider.value())
        data["windows_sapi_pitch"] = int(self.sapi_pitch_slider.value())
        data["windows_sapi_volume"] = int(self.sapi_volume_slider.value())
        data["tts_voice_defaults_initialized"] = True
        data["system_prompt"] = self.system_prompt.toPlainText().strip()
        return data


class TTSActionWorker(QObject):
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, base_url: str, action: str, translations: dict[str, str] | None = None) -> None:
        super().__init__()
        self.base_url = base_url
        self.action = action
        self.translations = translations or {}

    def t(self, key: str, default: str) -> str:
        return self.translations.get(key, default)

    def run(self) -> None:
        manager = VibeVoiceManager(self.base_url, self.t)
        try:
            if self.action == "auto_setup":
                success, message = manager.auto_setup(self.log.emit)
                self.finished.emit(success, message)
            elif self.action == "install":
                manager.install_or_update(self.log.emit)
                self.finished.emit(True, self.t("tts_setup_auto_done", "VibeVoice-Setup abgeschlossen."))
            elif self.action == "install_ffmpeg":
                manager.install_ffmpeg_via_winget(self.log.emit)
                self.finished.emit(True, self.t("tts_setup_ffmpeg_done", "FFmpeg-Installation abgeschlossen oder übersprungen."))
            elif self.action == "start":
                ok, msg = manager.start_server_and_wait(self.log.emit, max_wait=120)
                if ok:
                    self.finished.emit(True, self.t("tts_setup_start_done", "VibeVoice server is ready.") + (f" ({msg})" if msg else ""))
                else:
                    self.finished.emit(False, self.t("tts_setup_start_failed", "VibeVoice server did not become ready in time.") + (f" ({msg})" if msg else ""))
            elif self.action == "stop":
                manager.stop_server(self.log.emit)
                self.finished.emit(True, self.t("tts_setup_stop_done", "Stoppsignal abgeschlossen."))
            elif self.action == "download_voices":
                _total, downloaded = manager.download_official_voice_presets(self.log.emit)
                self.finished.emit(True, self.t("tts_setup_download_voices_done", "Additional voice presets downloaded: {count}.").format(count=downloaded))
            else:
                self.finished.emit(False, self.t("tts_setup_unknown_action", "Unbekannte Aktion: {action}").format(action=self.action))
        except Exception as exc:
            self.finished.emit(False, str(exc))


class TTSSetupDialog(QDialog):
    def __init__(self, config: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self.translations = load_language_pack(self.config.get("interface_language", "de"))
        self.setWindowTitle(self.t("tts_setup_title", "TTS-Setup-Assistent"))
        self.resize(860, 700)
        self.setModal(True)
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[TTSActionWorker] = None
        self._busy_action: str = ""
        self._elapsed_seconds = 0

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._tick_elapsed)

        root = QVBoxLayout(self)
        info = QLabel(self.t("tts_setup_info", "Dieser Assistent bündelt die automatische VibeVoice-Einrichtung."))
        info.setWordWrap(True)
        root.addWidget(info)

        self.status_label = QLabel()
        self.status_label.setObjectName("SubtleLabel")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.current_step_label = QLabel(self.t("tts_setup_status_ready", "Bereit."))
        self.current_step_label.setObjectName("SubtleLabel")
        self.current_step_label.setWordWrap(True)
        root.addWidget(self.current_step_label)

        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        progress_row.addWidget(self.progress_bar, 1)
        self.elapsed_label = QLabel(self.t("tts_setup_elapsed", "Verstrichen: {seconds} s").format(seconds=0))
        self.elapsed_label.setObjectName("SubtleLabel")
        progress_row.addWidget(self.elapsed_label)
        root.addLayout(progress_row)

        button_row = QHBoxLayout()
        self.auto_setup_btn = QPushButton(self.t("tts_setup_btn_auto", "VibeVoice install / update"))
        self.auto_setup_btn.setObjectName("AccentButton")
        self.auto_setup_btn.clicked.connect(lambda: self.start_action("auto_setup"))
        self.start_btn = QPushButton(self.t("tts_setup_btn_start", "Start server"))
        self.start_btn.clicked.connect(lambda: self.start_action("start"))
        self.stop_btn = QPushButton(self.t("tts_setup_btn_stop", "Server stoppen"))
        self.stop_btn.clicked.connect(lambda: self.start_action("stop"))
        button_row.addWidget(self.auto_setup_btn)
        button_row.addWidget(self.start_btn)
        button_row.addWidget(self.stop_btn)
        root.addLayout(button_row)

        path_row = QHBoxLayout()
        self.open_folder_btn = QPushButton(self.t("tts_setup_btn_open_folder", "TTS-Ordner öffnen"))
        self.open_folder_btn.clicked.connect(self.open_tts_folder)
        self.open_log_btn = QPushButton(self.t("tts_setup_btn_open_log", "Log öffnen"))
        self.open_log_btn.clicked.connect(self.open_log_file)
        path_row.addWidget(self.open_folder_btn)
        path_row.addWidget(self.open_log_btn)
        path_row.addStretch()
        root.addLayout(path_row)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText(self.t("tts_setup_log_placeholder", "Hier erscheinen Status- und Setup-Meldungen …"))
        root.addWidget(self.log_box, 1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton(self.t("tts_setup_close", "Schließen"))
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

        self.refresh_status()

    def t(self, key: str, default: Optional[str] = None) -> str:
        return self.translations.get(key, default or key)

    def manager(self) -> VibeVoiceManager:
        return VibeVoiceManager(self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"), self.t)

    def append_log(self, text: str) -> None:
        self.log_box.appendPlainText(text)
        self._update_progress_from_log(text)
        bar = self.log_box.verticalScrollBar()
        bar.setValue(bar.maximum())

    def refresh_status(self) -> None:
        status = self.manager().status()
        yes = self.t("yes", "ja")
        no = self.t("no", "nein")
        health_text = self.t("ok", "OK") if status.health_ok else self.t("not_reachable", "nicht erreichbar")
        lines = [
            self.t("tts_setup_status_backend", "Backend-URL: {value}").format(value=status.base_url),
            self.t("tts_setup_status_health", "Health: {value}").format(value=health_text),
            self.t("tts_setup_status_ffmpeg", "ffmpeg in PATH: {value}").format(value=yes if status.ffmpeg_found else no),
            self.t("tts_setup_status_repo", "Wrapper-Dateien vorhanden: {value}").format(value=yes if status.repo_present else no),
            self.t("tts_setup_status_venv", "Wrapper-venv vorhanden: {value}").format(value=yes if status.venv_present else no),
            self.t("tts_setup_status_pid", "PID-Datei/Prozess aktiv: {value}").format(value=yes if status.pid_running else no),
            self.t("tts_setup_status_repo_dir", "Repo-Ordner: {value}").format(value=status.repo_dir),
            self.t("tts_setup_status_models_dir", "Modelle-Ordner: {value}").format(value=status.models_dir),
            self.t("tts_setup_status_log", "Logdatei: {value}").format(value=status.log_path),
        ]
        if status.health_ok:
            lines.append(self.t("tts_setup_status_health_reply", "Health-Antwort: {value}").format(value=status.health_message))
        else:
            lines.append(self.t("tts_setup_status_health_error", "Letzter Health-Fehler: {value}").format(value=status.health_message))
        self.status_label.setText("\n".join(lines))

    def _set_progress(self, value: int, step_text: Optional[str] = None) -> None:
        value = max(0, min(100, value))
        if value < self.progress_bar.value() and self.worker_thread is not None:
            value = self.progress_bar.value()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(value)
        if step_text:
            self.current_step_label.setText(self.t("tts_setup_current_step", "Aktueller Schritt: {step}").format(step=step_text))

    def _update_progress_from_log(self, text: str) -> None:
        lower = text.lower()
        percent_match = re.search(r"(\d{1,3})%", text)
        if "backend-url" in lower or "backend url" in lower or lower.startswith("health:"):
            self._set_progress(8, self.t("tts_setup_progress_checking", "Status wird geprüft …"))
        if "ffmpeg" in lower:
            self._set_progress(max(self.progress_bar.value(), 15), self.t("tts_setup_progress_ffmpeg", "FFmpeg wird geprüft …"))
        if "download" in lower or "wrapper archive" in lower or "wrapper-archiv" in lower:
            if percent_match:
                pct = int(percent_match.group(1))
                self._set_progress(20 + int(pct * 0.30), self.t("tts_setup_progress_download", "Wrapper-Archiv wird heruntergeladen …"))
            else:
                self._set_progress(max(self.progress_bar.value(), 20), self.t("tts_setup_progress_download", "Wrapper-Archiv wird heruntergeladen …"))
        if "voice preset" in lower or "voice presets" in lower or "stimmenpaket" in lower or "zusätzliche stimmen" in lower:
            if percent_match:
                pct = int(percent_match.group(1))
                self._set_progress(max(self.progress_bar.value(), 86 + int(pct * 0.10)), self.t("tts_setup_progress_voices", "Zusätzliche Stimmen werden heruntergeladen …"))
            else:
                self._set_progress(max(self.progress_bar.value(), 86), self.t("tts_setup_progress_voices", "Zusätzliche Stimmen werden heruntergeladen …"))
        if "entpack" in lower or "extract" in lower:
            self._set_progress(max(self.progress_bar.value(), 58), self.t("tts_setup_progress_extract", "Archiv wird entpackt …"))
        if "venv" in lower:
            self._set_progress(max(self.progress_bar.value(), 70), self.t("tts_setup_progress_venv", "Python-Umgebung wird vorbereitet …"))
        if "requirements" in lower or "pip" in lower or "abhängigkeiten" in lower or "dependencies" in lower:
            self._set_progress(max(self.progress_bar.value(), 82), self.t("tts_setup_progress_requirements", "Abhängigkeiten werden installiert …"))
        if "starte lokalen tts-server" in lower or "starting local tts server" in lower or "prozess gestartet" in lower or "process started" in lower:
            self._set_progress(max(self.progress_bar.value(), 92), self.t("tts_setup_progress_starting", "Server wird gestartet …"))
        if "beende tts-server" in lower or "stopping tts server" in lower:
            self._set_progress(max(self.progress_bar.value(), 92), self.t("tts_setup_progress_stopping", "Server wird gestoppt …"))
        if "abgeschlossen" in lower or "finished" in lower or "antwortet bereits" in lower or "responded after" in lower:
            self._set_progress(max(self.progress_bar.value(), 95), self.t("tts_setup_progress_finalizing", "Final checks …"))

    def _tick_elapsed(self) -> None:
        self._elapsed_seconds += 1
        self.elapsed_label.setText(self.t("tts_setup_elapsed", "Verstrichen: {seconds} s").format(seconds=self._elapsed_seconds))

    def set_busy(self, busy: bool) -> None:
        for btn in [self.auto_setup_btn, self.start_btn, self.stop_btn, self.open_folder_btn, self.open_log_btn]:
            btn.setEnabled(not busy)
        if busy:
            self._elapsed_seconds = 0
            self.elapsed_label.setText(self.t("tts_setup_elapsed", "Verstrichen: {seconds} s").format(seconds=0))
            self.elapsed_timer.start()
            self.progress_bar.setValue(3)
        else:
            self.elapsed_timer.stop()

    def start_action(self, action: str) -> None:
        if self.worker_thread is not None:
            QMessageBox.information(self, self.t("tts_setup_running_title", "Bitte warten"), self.t("tts_setup_running_text", "Es läuft bereits eine TTS-Setup-Aktion."))
            return
        action_name = {
            "auto_setup": self.t("tts_setup_action_auto", "VibeVoice install / update"),
            "start": self.t("tts_setup_action_start", "Serverstart"),
            "stop": self.t("tts_setup_action_stop", "Server stoppen"),
            "install": self.t("tts_setup_action_install", "Installieren / Aktualisieren"),
            "download_voices": self.t("tts_setup_action_download_voices", "Additional voice presets"),
        }.get(action, action)
        self.append_log("")
        self.append_log(self.t("tts_setup_action_header", "=== Aktion: {action} ===").format(action=action_name))
        self.current_step_label.setText(self.t("tts_setup_current_step", "Aktueller Schritt: {step}").format(step=action_name))
        self.progress_bar.setValue(5)
        self.set_busy(True)

        self.worker_thread = QThread(self)
        self.worker = TTSActionWorker(self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"), action, self.translations)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_action_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.cleanup_worker)
        self.send_btn.setEnabled(False)
        self.worker_thread.start()

    def on_action_finished(self, success: bool, message: str) -> None:
        self.append_log(message)
        self.refresh_status()
        self.set_busy(False)
        self.progress_bar.setValue(100 if success else max(self.progress_bar.value(), 1))
        if success:
            self.current_step_label.setText(self.t("tts_setup_ready_to_start", "VibeVoice installation / update completed. You can now start the VibeVoice server."))
        if success:
            self.parent().statusBar().showMessage(message, 4000) if self.parent() and hasattr(self.parent(), 'statusBar') else None
        else:
            self.parent().statusBar().showMessage(message, 6000) if self.parent() and hasattr(self.parent(), 'statusBar') else None
            QMessageBox.information(self, self.t("tts_setup_message_title", "TTS-Setup"), message)

    def cleanup_worker(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None

    def open_tts_folder(self) -> None:
        path = self.manager().root_dir
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_log_file(self) -> None:
        log_path = self.manager().log_path
        if log_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path)))
        else:
            QMessageBox.information(self, self.t("tts_setup_no_log_title", "Noch kein Log"), self.t("tts_setup_no_log_text", "Die Logdatei existiert noch nicht. Starte den Server einmal, dann wird sie angelegt."))


class MainWindow(QMainWindow):
    audio_error_signal = pyqtSignal(str)
    audio_status_signal = pyqtSignal(str)
    audio_feedback_signal = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.config, config_changed = resolve_tts_voice_config_defaults(self.config)
        if config_changed:
            save_config(self.config)
        self.translations = load_language_pack(self.config.get("interface_language", "de"))
        self.store = SessionStore()
        self.sessions = self.store.list_sessions()
        self.current_session: Optional[ChatSession] = None
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[ChatWorker] = None
        self.current_assistant_bubble: Optional[BubbleWidget] = None
        self.current_assistant_text = ""
        self.current_playback_stoppable = False
        self.current_audio_message: Optional[ChatMessage] = None
        self.current_audio_backend = ''
        self.current_audio_text = ''
        self.current_audio_sentences: List[str] = []
        self.current_audio_sentence_index = 0
        self.audio_generation_id = 0
        self.audio_stop_requested = False
        self.audio_playback_thread: Optional[threading.Thread] = None
        self.last_requested_model = (self.config.get("last_model", "") or "").strip()
        self.pending_auto_answer_source = ""
        self.pending_auto_submit_message: Optional[ChatMessage] = None
        self.auto_answer_waiting_for_user_audio = False
        self.auto_answer_rounds_current = 0
        self.current_request_consumes_rollover_short_instruction = False
        self.context_retry_in_progress = False
        self.last_saved_code_paths: list[Path] = []
        self.debug_logger = DebugTraceLogger(bool(self.config.get("debug_trace_enabled", False)))
        self.debug_runtime_prompt_tokens = 0
        self.debug_runtime_completion_tokens = 0
        self.debug_runtime_requests = 0
        self.debug_session_totals: dict[str, dict[str, int]] = {}
        self.current_request_debug_info: dict = {}

        self.setWindowTitle(self._window_title_text())
        self.audio_error_signal.connect(self._on_audio_error)
        self.audio_status_signal.connect(self._on_audio_status)
        self.audio_feedback_signal.connect(self._on_audio_feedback)
        self._tts_feedback_token = 0
        self._tts_feedback_elapsed_seconds = 0
        self.auto_answer_timer = QTimer(self)
        self.auto_answer_timer.setSingleShot(True)
        self.auto_answer_timer.timeout.connect(self._on_auto_answer_timer)
        self.tts_feedback_timer = QTimer(self)
        self.tts_feedback_timer.setInterval(1000)
        self.tts_feedback_timer.timeout.connect(self._tick_tts_feedback_elapsed)
        self.resize(1420, 920)
        self.setMinimumSize(QSize(1180, 720))
        self.apply_theme(self.config.get("theme", "Midnight"))

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(18)
        self.setCentralWidget(root)

        self.sidebar = self._build_sidebar()
        root_layout.addWidget(self.sidebar, 0)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(14)

        self.header = self._build_header()
        center_layout.addWidget(self.header)

        self.chat_surface = self._build_chat_surface()
        center_layout.addWidget(self.chat_surface, 1)

        self.composer = self._build_composer()
        center_layout.addWidget(self.composer, 0)

        root_layout.addWidget(center, 1)

        self.refresh_sessions_ui()
        self.refresh_models()
        if self.sessions:
            self.open_session(self.sessions[0].session_id)
        else:
            self.create_new_session()

        self._set_request_feedback("idle")
        self._set_tts_feedback('idle')
        self._debug_log("app_started", {
            "log_path": str(self.debug_logger.path),
            "config": self._debug_config_snapshot(),
            "sessions_found": len(self.sessions),
            "platform": sys.platform,
        })

    def t(self, key: str, default: Optional[str] = None) -> str:
        return self.translations.get(key, default or key)

    def _window_title_text(self) -> str:
        return f"{self.t('app_title', APP_TITLE_BASE)} - {APP_TITLE_DATE}"

    def reload_language_pack(self) -> None:
        self.translations = load_language_pack(self.config.get("interface_language", "de"))
    def _debug_config_snapshot(self) -> dict:
        return {
            "interface_language": self.config.get("interface_language", "de"),
            "theme": self.config.get("theme", "Midnight"),
            "model": self.model_combo.currentText().strip() if hasattr(self, "model_combo") else self.config.get("last_model", ""),
            "auto_answer_enabled": bool(self.config.get("auto_answer_enabled", True)),
            "auto_answer_short_answers": bool(self.config.get("auto_answer_short_answers", True)),
            "auto_answer_eliza_share": int(self.config.get("auto_answer_eliza_share", 30) or 30),
            "auto_answer_phrase_repeat_lookback": int(self.config.get("auto_answer_phrase_repeat_lookback", 4) or 4),
            "auto_answer_max_rounds": int(self.config.get("auto_answer_max_rounds", 0) or 0),
            "chat_max_tokens": int(self.config.get("chat_max_tokens", 1024) or 1024),
            "context_message_limit": int(self.config.get("context_message_limit", 8) or 8),
            "rollover_carry_messages": int(self.config.get("rollover_carry_messages", AUTO_ANSWER_ROLLOVER_CARRY_MESSAGES) or AUTO_ANSWER_ROLLOVER_CARRY_MESSAGES),
            "tts_backend": self.config.get("tts_backend", "disabled"),
            "auto_read_assistant_responses": bool(self.config.get("auto_read_assistant_responses", True)),
            "auto_read_user_inputs": bool(self.config.get("auto_read_user_inputs", False)),
            "debug_trace_enabled": bool(self.config.get("debug_trace_enabled", False)),
        }

    def _debug_current_chat_token_estimate(self) -> int:
        return estimate_chat_payload_tokens(self.session_messages_for_api(), self.request_system_prompt())

    def _debug_runtime_totals(self) -> dict:
        return {
            "requests": int(self.debug_runtime_requests),
            "prompt_tokens_estimated": int(self.debug_runtime_prompt_tokens),
            "completion_tokens_estimated": int(self.debug_runtime_completion_tokens),
            "tokens_estimated_total": int(self.debug_runtime_prompt_tokens + self.debug_runtime_completion_tokens),
        }

    def _debug_current_session_totals(self) -> dict:
        if not self.current_session:
            return {"requests": 0, "prompt_tokens_estimated": 0, "completion_tokens_estimated": 0, "tokens_estimated_total": 0}
        stats = self.debug_session_totals.get(self.current_session.session_id, {})
        prompt = int(stats.get("prompt_tokens_estimated", 0) or 0)
        completion = int(stats.get("completion_tokens_estimated", 0) or 0)
        return {
            "requests": int(stats.get("requests", 0) or 0),
            "prompt_tokens_estimated": prompt,
            "completion_tokens_estimated": completion,
            "tokens_estimated_total": prompt + completion,
        }

    def _debug_log(self, event: str, extra: dict | None = None) -> None:
        if not getattr(self, "debug_logger", None):
            return
        payload = {
            "session": {
                "session_id": self.current_session.session_id if self.current_session else None,
                "title": self.current_session.title if self.current_session else None,
                "message_count": len(self.current_session.messages) if self.current_session else 0,
                "reapply_short_instruction_after_rollover": bool(getattr(self.current_session, "reapply_short_instruction_after_rollover", False)) if self.current_session else False,
            },
            "current_chat_tokens_estimated": self._debug_current_chat_token_estimate() if self.current_session else 0,
            "runtime_totals": self._debug_runtime_totals(),
            "session_totals": self._debug_current_session_totals(),
            "config": self._debug_config_snapshot(),
        }
        if extra:
            payload.update(extra)
        self.debug_logger.write(event, payload)


    def apply_theme(self, theme_name: str) -> None:
        theme_name = theme_name if theme_name in THEMES else "Midnight"
        self.config["theme"] = theme_name
        save_config(self.config)
        QApplication.instance().setStyleSheet(THEMES[theme_name])

    def _build_sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Sidebar")
        frame.setFixedWidth(320)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.sidebar_title = QLabel(self.t("app_title", APP_TITLE_BASE))
        self.sidebar_title.setObjectName("TitleLabel")
        layout.addWidget(self.sidebar_title)

        self.sidebar_subtitle = QLabel(self.t("sidebar_subtitle", "Lokale Chats · portable Daten · optionale WAV-Ausgabe"))
        self.sidebar_subtitle.setObjectName("SubtleLabel")
        self.sidebar_subtitle.setWordWrap(True)
        layout.addWidget(self.sidebar_subtitle)

        buttons = QHBoxLayout()
        self.new_chat_btn = QPushButton(self.t("new_chat", "Neuer Chat"))
        self.new_chat_btn.setObjectName("AccentButton")
        self.new_chat_btn.clicked.connect(self.create_new_session)
        self.delete_chat_btn = QPushButton(self.t("delete_chat_button", "Löschen"))
        self.delete_chat_btn.setObjectName("DangerButton")
        self.delete_chat_btn.clicked.connect(self.delete_current_session)
        buttons.addWidget(self.new_chat_btn)
        buttons.addWidget(self.delete_chat_btn)
        layout.addLayout(buttons)

        self.session_list = QListWidget()
        self.session_list.itemClicked.connect(self._on_session_clicked)
        layout.addWidget(self.session_list, 1)

        self.sidebar_hint = QLabel(self.t("chat_actions_hint", "Jede Assistent-Antwort hat direkt Aktionen für Kopieren, Vorlesen und Stoppen."))
        self.sidebar_hint.setWordWrap(True)
        self.sidebar_hint.setObjectName("SubtleLabel")
        self.sidebar_hint.setVisible(False)

        return frame

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("HeaderBar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self.status_label = QLabel(self.t("status_checking", "Checking Ollama status …"))
        self.status_label.setObjectName("SubtleLabel")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.status_label.setMaximumWidth(180)
        self.status_label.setToolTip("")
        layout.addWidget(self.status_label)

        layout.addStretch()

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(210)
        self.model_combo.setMaximumWidth(260)
        self.model_combo.currentTextChanged.connect(self._model_changed)
        self.model_label = QLabel(self.t("model_label", "Modell"))
        layout.addWidget(self.model_label)
        layout.addWidget(self.model_combo)

        self.refresh_models_btn = QPushButton(self.t("refresh_models", "Modelle neu laden"))
        self.refresh_models_btn.clicked.connect(self.refresh_models)
        self.refresh_models_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.refresh_models_btn)

        self.read_all_btn = QPushButton(self.t("read_all_button", "Alles vorlesen"))
        self.read_all_btn.clicked.connect(self.read_aloud_conversation)
        self.read_all_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.read_all_btn)

        self.audio_stop_header_btn = QPushButton(self.t("stop_audio_button", "Audio stoppen"))
        self.audio_stop_header_btn.clicked.connect(self.stop_audio_playback)
        self.audio_stop_header_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.audio_stop_header_btn)

        self.export_pdf_btn = QPushButton(self.t("export_pdf_button", "Chat exportieren"))
        self.export_pdf_btn.clicked.connect(self.export_current_chat_pdf)
        self.export_pdf_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.export_pdf_btn)

        self.settings_btn = QPushButton(self.t("settings_button", "Einstellungen"))
        self.settings_btn.clicked.connect(self.show_settings)
        self.settings_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.settings_btn)

        return frame

    def _set_header_status(self, raw_text: str) -> None:
        text = raw_text.strip()
        metrics = QFontMetrics(self.status_label.font())
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(120, self.status_label.maximumWidth() - 8))
        self.status_label.setText(elided)
        self.status_label.setToolTip(text)

    def _build_chat_surface(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("ChatSurface")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)

        self.chat_host = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_host)
        self.chat_layout.setContentsMargins(8, 8, 8, 8)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_host)
        layout.addWidget(self.chat_scroll)

        return frame

    def _build_composer(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("ComposerFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.input_box = QPlainTextEdit()
        self.input_box.setPlaceholderText(self.t("composer_placeholder", "Nachricht schreiben …  (Strg+Enter zum Senden)"))
        self.input_box.setFixedHeight(120)
        self.input_box.textChanged.connect(self._on_input_text_changed)
        layout.addWidget(self.input_box)

        self.send_shortcut_return = QShortcut(QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Return), self.input_box)
        self.send_shortcut_return.activated.connect(self.send_message)
        self.send_shortcut_enter = QShortcut(QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Enter), self.input_box)
        self.send_shortcut_enter.activated.connect(self.send_message)

        self.composer_state_label = QLabel(self.t("composer_state_idle", "Bereit."))
        self.composer_state_label.setObjectName("SubtleLabel")
        self.composer_state_label.setWordWrap(True)
        layout.addWidget(self.composer_state_label)

        self.tts_feedback_frame = QFrame()
        self.tts_feedback_frame.setObjectName("TTSFeedbackFrame")
        tts_feedback_layout = QHBoxLayout(self.tts_feedback_frame)
        tts_feedback_layout.setContentsMargins(8, 6, 8, 6)
        tts_feedback_layout.setSpacing(8)
        self.tts_feedback_label = QLabel(self.t("tts_feedback_idle", "Bereit für Sprachausgabe."))
        self.tts_feedback_label.setObjectName("SubtleLabel")
        self.tts_feedback_label.setWordWrap(True)
        tts_feedback_layout.addWidget(self.tts_feedback_label, 1)
        self.tts_feedback_bar = QProgressBar()
        self.tts_feedback_bar.setMinimumWidth(180)
        self.tts_feedback_bar.setMaximumWidth(260)
        self.tts_feedback_bar.setTextVisible(False)
        self.tts_feedback_bar.setRange(0, 0)
        tts_feedback_layout.addWidget(self.tts_feedback_bar)
        self.tts_feedback_elapsed_label = QLabel(self.t("tts_feedback_elapsed", "TTS: {seconds} s").format(seconds=0))
        self.tts_feedback_elapsed_label.setObjectName("SubtleLabel")
        tts_feedback_layout.addWidget(self.tts_feedback_elapsed_label)
        self.tts_feedback_frame.hide()
        layout.addWidget(self.tts_feedback_frame)

        self.auto_answer_checkbox = QCheckBox(self.t("auto_answer_checkbox", "Auto Answer (ELIZA)"))
        self.auto_answer_checkbox.setChecked(bool(self.config.get("auto_answer_enabled", True)))
        self.auto_answer_checkbox.toggled.connect(self._on_auto_answer_toggled)
        layout.addWidget(self.auto_answer_checkbox)

        buttons = QHBoxLayout()
        self.composer_hint = QLabel(self.t("composer_hint", "Ollama wird lokal angesprochen. Antworten werden gestreamt."))
        self.composer_hint.setObjectName("SubtleLabel")
        buttons.addWidget(self.composer_hint)
        buttons.addStretch()

        self.stop_btn = QPushButton(self.t("stop_button", "Stop"))
        self.stop_btn.clicked.connect(self.stop_generation)
        self.stop_btn.setEnabled(False)

        self.send_btn = QPushButton(self.t("send_button", "Senden"))
        self.send_btn.setObjectName("AccentButton")
        self.send_btn.clicked.connect(self.send_message)

        buttons.addWidget(self.stop_btn)
        buttons.addWidget(self.send_btn)
        layout.addLayout(buttons)

        return frame

    def refresh_ui_texts(self) -> None:
        self.setWindowTitle(self._window_title_text())
        self.sidebar_title.setText(self.t("app_title", APP_TITLE_BASE))
        self.sidebar_subtitle.setText(self.t("sidebar_subtitle", "Lokale Chats · portable Daten · optionale WAV-Ausgabe"))
        self.new_chat_btn.setText(self.t("new_chat", "Neuer Chat"))
        self.delete_chat_btn.setText(self.t("delete_chat_button", "Löschen"))
        self.sidebar_hint.setText(self.t("chat_actions_hint", "Jede Assistent-Antwort hat direkt Aktionen für Kopieren, Vorlesen und Stoppen."))
        self.model_label.setText(self.t("model_label", "Modell"))
        self.refresh_models_btn.setText(self.t("refresh_models", "Modelle neu laden"))
        self.read_all_btn.setText(self.t("read_all_button", "Alles vorlesen"))
        self.audio_stop_header_btn.setText(self.t("stop_audio_button", "Audio stoppen"))
        self.export_pdf_btn.setText(self.t("export_pdf_button", "Chat exportieren"))
        self.settings_btn.setText(self.t("settings_button", "Einstellungen"))
        self.input_box.setPlaceholderText(self.t("composer_placeholder", "Nachricht schreiben …  (Strg+Enter zum Senden)"))
        self.composer_hint.setText(self.t("composer_hint", "Ollama wird lokal angesprochen. Antworten werden gestreamt."))
        if self.worker_thread is None:
            self.composer_state_label.setText(self.t("composer_state_idle", "Bereit."))
        if hasattr(self, 'tts_feedback_elapsed_label') and not self.tts_feedback_frame.isVisible():
            self.tts_feedback_label.setText(self.t("tts_feedback_idle", "Bereit für Sprachausgabe."))
            self.tts_feedback_elapsed_label.setText(self.t("tts_feedback_elapsed", "TTS: {seconds} s").format(seconds=0))
        self.stop_btn.setText(self.t("stop_button", "Stop"))
        self.send_btn.setText(self.t("send_button", "Senden"))
        self.auto_answer_checkbox.setText(self.t("auto_answer_checkbox", "Auto Answer (ELIZA)"))
        current_session_id = self.current_session.session_id if self.current_session else None
        if current_session_id:
            self.open_session(current_session_id)
        self.refresh_models()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.send_message()
            return
        super().keyPressEvent(event)

    def _set_request_feedback(self, state: str) -> None:
        mapping = {
            "idle": self.t("composer_state_idle", "Bereit."),
            "sent": self.t("composer_state_sent", "Anfrage gesendet … Antwort wird vorbereitet."),
            "waiting": self.t("composer_state_waiting", "LLM antwortet … erste Tokens werden erwartet."),
            "streaming": self.t("composer_state_streaming", "LLM antwortet gerade …"),
            "finished": self.t("composer_state_finished", "Antwort abgeschlossen."),
            "failed": self.t("composer_state_failed", "Antwort fehlgeschlagen."),
        }
        if hasattr(self, "composer_state_label"):
            self.composer_state_label.setText(mapping.get(state, mapping["idle"]))

    def _flush_chat_ui(self) -> None:
        try:
            self.chat_host.adjustSize()
            self.chat_host.updateGeometry()
            self.chat_scroll.widget().updateGeometry()
            QApplication.processEvents()
        except Exception:
            pass
        QTimer.singleShot(0, self.scroll_to_bottom)

    def _tick_tts_feedback_elapsed(self) -> None:
        self._tts_feedback_elapsed_seconds += 1
        if hasattr(self, 'tts_feedback_elapsed_label'):
            self.tts_feedback_elapsed_label.setText(self.t("tts_feedback_elapsed", "TTS: {seconds} s").format(seconds=self._tts_feedback_elapsed_seconds))

    def _set_tts_feedback(self, state: str, text: str = "", determinate: bool = False, value: int = 0, autohide_ms: int = 0) -> None:
        if not hasattr(self, 'tts_feedback_frame'):
            return
        if state == 'idle':
            self.tts_feedback_timer.stop()
            self.tts_feedback_frame.hide()
            self.tts_feedback_label.setText(self.t("tts_feedback_idle", "Bereit für Sprachausgabe."))
            self.tts_feedback_elapsed_label.setText(self.t("tts_feedback_elapsed", "TTS: {seconds} s").format(seconds=0))
            self.tts_feedback_bar.setRange(0, 0)
            return
        self._tts_feedback_token += 1
        token = self._tts_feedback_token
        self.tts_feedback_frame.show()
        self.tts_feedback_label.setText(text or self.t("tts_feedback_idle", "Bereit für Sprachausgabe."))
        if determinate:
            self.tts_feedback_bar.setRange(0, 100)
            self.tts_feedback_bar.setValue(max(0, min(100, int(value))))
        else:
            self.tts_feedback_bar.setRange(0, 0)
        if state == 'start':
            self._tts_feedback_elapsed_seconds = 0
            self.tts_feedback_elapsed_label.setText(self.t("tts_feedback_elapsed", "TTS: {seconds} s").format(seconds=0))
            self.tts_feedback_timer.start()
        elif state in {'done', 'error'}:
            self.tts_feedback_timer.stop()
            if autohide_ms:
                QTimer.singleShot(autohide_ms, lambda tok=token: self._hide_tts_feedback_if_current(tok))
        else:
            if not self.tts_feedback_timer.isActive():
                self.tts_feedback_timer.start()

    def _hide_tts_feedback_if_current(self, token: int) -> None:
        if token == self._tts_feedback_token:
            self._set_tts_feedback('idle')

    def _on_audio_feedback(self, state: str, message: str) -> None:
        if state == 'checking':
            self._set_tts_feedback('start', message or self.t("tts_feedback_checking", "Prüfe lokalen VibeVoice-Server …"), determinate=False)
        elif state == 'generating':
            self._set_tts_feedback('busy', message or self.t("tts_feedback_generating", "Sprachausgabe wird erzeugt …"), determinate=False)
        elif state == 'playing':
            self._set_tts_feedback('busy', message or self.t("tts_feedback_playing", "Sprachausgabe wird abgespielt …"), determinate=False)
        elif state == 'busy':
            self._set_tts_feedback('busy', message or self.t("tts_feedback_generating", "Sprachausgabe wird erzeugt …"), determinate=False)
        elif state == 'done':
            self._set_tts_feedback('done', message or self.t("audio_finished", "Sprachausgabe beendet."), determinate=True, value=100, autohide_ms=1600)
        elif state == 'error':
            self._set_tts_feedback('error', message or self.t("audio_failed", "Sprachausgabe fehlgeschlagen."), determinate=True, value=100, autohide_ms=2600)
        else:
            self._set_tts_feedback('idle')

    def _on_session_clicked(self, item: QListWidgetItem) -> None:
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id:
            self.open_session(session_id)

    def refresh_sessions_ui(self) -> None:
        self.session_list.clear()
        self.sessions = self.store.list_sessions()
        for session in self.sessions:
            item = QListWidgetItem(session.title)
            item.setData(Qt.ItemDataRole.UserRole, session.session_id)
            item.setToolTip(f"{session.title}\n{pretty_timestamp(session.updated_at)}")
            self.session_list.addItem(item)

    def create_new_session(self) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        session = ChatSession(
            session_id=uuid.uuid4().hex,
            title=self.t("new_conversation", "Neue Unterhaltung"),
            created_at=now,
            updated_at=now,
            model_name=self.model_combo.currentText().strip(),
        )
        self.store.save(session)
        self.refresh_sessions_ui()
        self.open_session(session.session_id)
        self._debug_log("session_created", {"new_session_id": session.session_id, "new_session_title": session.title})

    def delete_current_session(self) -> None:
        if not self.current_session:
            return
        reply = QMessageBox.question(
            self,
            self.t("delete_chat_title", "Chat löschen"),
            self.t("delete_chat_text", 'Soll „{title}“ wirklich gelöscht werden?').format(title=self.current_session.title),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        session_id = self.current_session.session_id
        deleted_title = self.current_session.title
        self.store.delete(session_id)
        self._debug_log("session_deleted", {"deleted_session_id": session_id, "deleted_session_title": deleted_title})
        self.current_session = None
        self.refresh_sessions_ui()
        if self.sessions:
            self.open_session(self.sessions[0].session_id)
        else:
            self.create_new_session()

        self._set_request_feedback("idle")
        self._set_tts_feedback('idle')

    def open_session(self, session_id: str) -> None:
        target = None
        for session in self.store.list_sessions():
            if session.session_id == session_id:
                target = session
                break
        if target is None:
            return
        self.current_session = target
        self.current_assistant_bubble = None
        self.current_assistant_text = ""

        self.clear_chat_layout()
        for message in target.messages:
            self.add_message_bubble(message)
        self._flush_chat_ui()

        for i in range(self.session_list.count()):
            item = self.session_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == session_id:
                self.session_list.setCurrentItem(item)
                break
        self._set_request_feedback("idle")
        self._set_tts_feedback('idle')
        self._debug_log("session_opened", {"opened_session_id": session_id, "opened_session_title": target.title})

    def clear_chat_layout(self) -> None:
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_message_bubble(self, message: ChatMessage) -> BubbleWidget:
        bubble = BubbleWidget(
            message=message,
            is_assistant=message.role == "assistant",
            on_read_aloud=self.read_aloud_message,
            on_stop_audio=self.stop_audio_playback,
            on_copy=self.copy_text,
            translate=self.t,
            role_label=resolve_display_name(self.config, message.role),
        )
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        return bubble

    def refresh_visible_bubble_role_labels(self) -> None:
        for i in range(self.chat_layout.count()):
            widget = self.chat_layout.itemAt(i).widget()
            if isinstance(widget, BubbleWidget):
                widget.set_role_label(resolve_display_name(self.config, widget.message.role))

    def copy_text(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(self.t("copied_to_clipboard", "Text in die Zwischenablage kopiert."), 2500)

    def refresh_models(self) -> None:
        self.model_combo.blockSignals(True)
        current_text = self.model_combo.currentText().strip()
        self.model_combo.clear()
        try:
            client = OllamaClient(self.config.get("ollama_base_url", "http://127.0.0.1:11434").strip())
            models = client.get_models()
            if not models:
                self._set_header_status(self.t("status_ollama_ok_no_models", "Ollama reachable, but no models were found."))
            else:
                self.model_combo.addItems(models)
                last_model = self.config.get("last_model", "").strip() or current_text
                if last_model and last_model in models:
                    self.model_combo.setCurrentText(last_model)
                self._set_header_status(self.t("status_ollama_ok_models", "Ollama reachable · {count} model(s)").format(count=len(models)))
        except Exception as exc:
            self._set_header_status(self.t("status_ollama_not_reachable", "Ollama offline · {error}").format(error=exc))
        finally:
            self.model_combo.blockSignals(False)

    def _model_changed(self, model_name: str) -> None:
        self.config["last_model"] = model_name.strip()
        save_config(self.config)
        if self.current_session is not None:
            self.current_session.model_name = model_name.strip()
            self.store.save(self.current_session)
            self.refresh_sessions_ui()
        if model_name.strip():
            self.statusBar().showMessage(
                self.t(
                    "model_changed_hint",
                    "Model changed to '{model}'. The next answer may take a moment while Ollama loads it."
                ).format(model=model_name.strip()),
                4500,
            )

    def _auto_answer_recent_generated_user_messages(self) -> list[str]:
        if not self.current_session:
            return []
        lookback = max(0, int(self.config.get("auto_answer_phrase_repeat_lookback", 4) or 0))
        if lookback <= 0:
            return []
        items = [
            message_visible_content(message)
            for message in self.current_session.messages
            if message.role == "user" and bool(getattr(message, "generated", False)) and (message_visible_content(message) or "").strip()
        ]
        return items[-lookback:]

    def _session_rollover_threshold(self) -> int:
        limit = int(self.config.get("context_message_limit", AUTO_ANSWER_ROLLOVER_FALLBACK_LIMIT) or AUTO_ANSWER_ROLLOVER_FALLBACK_LIMIT)
        return max(6, limit)

    def _rollover_carry_message_count(self) -> int:
        configured = int(self.config.get("rollover_carry_messages", AUTO_ANSWER_ROLLOVER_CARRY_MESSAGES) or AUTO_ANSWER_ROLLOVER_CARRY_MESSAGES)
        return max(2, configured)

    def _request_token_budget(self) -> int:
        max_tokens = max(1, int(self.config.get("chat_max_tokens", 1024) or 1024))
        return max(AUTO_ANSWER_ROLLOVER_TOKEN_MIN_BUDGET, max_tokens * AUTO_ANSWER_ROLLOVER_TOKEN_BUDGET_FACTOR)

    def _would_exceed_request_budget(self, messages: list[dict], system_prompt: str) -> bool:
        projected = estimate_chat_payload_tokens(messages, system_prompt) + max(0, int(self.config.get("chat_max_tokens", 1024) or 1024))
        return projected > self._request_token_budget()

    def _clone_message_for_rollover(self, msg: ChatMessage) -> ChatMessage:
        return ChatMessage(
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at,
            generated=bool(getattr(msg, "generated", False)),
            audio_path=msg.audio_path,
            display_content=getattr(msg, "display_content", None),
        )

    def _trim_carry_messages_to_budget(self, messages: list[ChatMessage], system_prompt: str) -> tuple[list[ChatMessage], bool]:
        trimmed = list(messages)
        shortened = False
        while len(trimmed) > 2:
            payload = [{"role": item.role, "content": item.content} for item in trimmed if item.role in {"user", "assistant"}]
            if not self._would_exceed_request_budget(payload, system_prompt):
                break
            shortened = True
            trimmed = trimmed[1:]
            while trimmed and trimmed[0].role == "assistant" and len(trimmed) > 1:
                trimmed = trimmed[1:]
        return trimmed, shortened

    def _ensure_safe_session_capacity(self, additional_messages: int = 0, auto_answer_only: bool = False, pending_messages: list[dict] | None = None, system_prompt: str = "") -> bool:
        if not self.current_session:
            return False
        if auto_answer_only and not self.auto_answer_checkbox.isChecked():
            return False
        threshold = self._session_rollover_threshold()
        current_count = len(self.current_session.messages)
        exceeds_count = current_count + max(0, int(additional_messages or 0)) > threshold
        exceeds_budget = bool(pending_messages) and self._would_exceed_request_budget(pending_messages, system_prompt)
        if not exceeds_count and not exceeds_budget:
            return False
        carry_count = min(self._rollover_carry_message_count(), max(2, current_count))
        carry_messages = [
            self._clone_message_for_rollover(msg)
            for msg in self.current_session.messages[-carry_count:]
            if msg.role in {"user", "assistant"}
        ]
        if not carry_messages:
            return False
        carry_messages, shortened = self._trim_carry_messages_to_budget(carry_messages, system_prompt)
        if not carry_messages:
            return False
        old_title = self.current_session.title
        now = datetime.now().isoformat(timespec="seconds")
        continuation_suffix = self.t("continuation_suffix", " (Fortsetzung)")
        new_title = old_title if old_title.endswith(continuation_suffix) else f"{old_title}{continuation_suffix}"
        session = ChatSession(
            session_id=uuid.uuid4().hex,
            title=new_title,
            created_at=now,
            updated_at=now,
            model_name=self.model_combo.currentText().strip(),
            messages=carry_messages,
            reapply_short_instruction_after_rollover=True,
        )
        self.store.save(session)
        self.refresh_sessions_ui()
        self.open_session(session.session_id)
        status_key = "chat_rollover_trimmed_message" if shortened else "chat_rollover_message"
        status_default = "Ein neuer Folge-Chat wurde mit den letzten Nachrichten geöffnet, damit das Gespräch stabil weiterlaufen kann."
        if shortened:
            status_default = "Ein neuer Folge-Chat wurde geöffnet. Dabei wurden automatisch nur so viele letzte Nachrichten übernommen, dass der Kontext stabil weiterlaufen kann."
        self.statusBar().showMessage(self.t(status_key, status_default), 5000)
        self._debug_log("session_rollover", {
            "reason": {"message_count_exceeded": bool(exceeds_count), "token_budget_exceeded": bool(exceeds_budget)},
            "threshold_message_limit": int(threshold),
            "carry_count_requested": int(carry_count),
            "carry_count_final": len(carry_messages),
            "carry_messages_shortened": bool(shortened),
            "new_session_id": session.session_id,
            "new_session_title": session.title,
        })
        return True

    def _current_auto_answer_short_instruction(self) -> str:
        return auto_answer_short_instruction(self.config, self.config.get("interface_language", "de"))

    def _should_apply_auto_answer_short_instruction(self) -> bool:
        return self.auto_answer_checkbox.isChecked() and bool(self.config.get("auto_answer_short_answers", True))

    def _request_message_items(self) -> list[ChatMessage]:
        if not self.current_session:
            return []
        items = [item for item in self.current_session.messages if item.role in {"user", "assistant"}]
        if items and items[-1].role == "assistant" and not (items[-1].content or "").strip():
            items = items[:-1]
        return items

    def _session_requires_rollover_short_instruction_reapply(self) -> bool:
        return bool(self.current_session and getattr(self.current_session, "reapply_short_instruction_after_rollover", False))

    def _should_embed_short_instruction_in_next_user_message(self) -> bool:
        if not self._should_apply_auto_answer_short_instruction():
            return False
        if self._session_requires_rollover_short_instruction_reapply():
            return True
        items = self._request_message_items()
        return not any(item.role == "assistant" for item in items)

    def _build_user_message_content(self, text: str) -> tuple[str, str, bool]:
        visible_text = str(text or "").strip()
        short_instruction = self._current_auto_answer_short_instruction().strip()
        should_embed = bool(visible_text) and self._should_embed_short_instruction_in_next_user_message() and bool(short_instruction)
        stored_content = append_hidden_instruction_to_user_text(visible_text, short_instruction) if should_embed else visible_text
        return stored_content, visible_text, should_embed

    def request_system_prompt(self) -> str:
        return str(self.config.get("system_prompt", "") or "").strip()

    def session_messages_for_api(self) -> List[dict]:
        if not self.current_session:
            return []
        raw_items = self._request_message_items()
        messages = [{"role": item.role, "content": item.content} for item in raw_items]
        limit = int(self.config.get("context_message_limit", 8) or 8)
        if limit > 0 and len(messages) > limit:
            messages = messages[-limit:]
        return messages


    def _on_input_text_changed(self) -> None:
        if self.input_box.toPlainText().strip() and self.auto_answer_timer.isActive():
            self.auto_answer_timer.stop()
            self.pending_auto_answer_source = ""

    def _on_auto_answer_toggled(self, checked: bool) -> None:
        self.config["auto_answer_enabled"] = bool(checked)
        save_config(self.config)
        self.auto_answer_rounds_current = 0
        if not checked:
            self.auto_answer_timer.stop()
            self.pending_auto_answer_source = ""
            self.pending_auto_submit_message = None
            self.auto_answer_waiting_for_user_audio = False
            self.statusBar().showMessage(self.t("auto_answer_disabled", "Auto Answer deaktiviert."), 2500)
        else:
            self.statusBar().showMessage(self.t("auto_answer_enabled", "Auto Answer aktiviert."), 2500)
        self._debug_log("auto_answer_toggled", {"checked": bool(checked)})

    def _append_user_message(self, text: str, generated: bool = False) -> ChatMessage:
        if not self.current_session:
            self.create_new_session()
        self._ensure_safe_session_capacity(additional_messages=2, auto_answer_only=True)
        stored_content, visible_text, embedded_short_instruction = self._build_user_message_content(text)
        user_message = ChatMessage.now("user", stored_content, generated=generated, display_content=visible_text)
        if generated:
            self.auto_answer_rounds_current += 1
        else:
            self.auto_answer_rounds_current = 0
        if embedded_short_instruction and self.current_session is not None and self.current_session.reapply_short_instruction_after_rollover:
            self.current_session.reapply_short_instruction_after_rollover = False
        self.current_session.messages.append(user_message)
        if self.current_session.title == self.t("new_conversation", "Neue Unterhaltung"):
            self.current_session.title = visible_text[:48] + ("…" if len(visible_text) > 48 else "")
        self.current_session.model_name = self.model_combo.currentText().strip()
        self.store.save(self.current_session)
        self.refresh_sessions_ui()
        bubble = self.add_message_bubble(user_message)
        try:
            bubble.show()
        except Exception:
            pass
        self._flush_chat_ui()
        self._debug_log("user_message_appended", {
            "generated": bool(generated),
            "visible_content": visible_text,
            "stored_content": stored_content,
            "hidden_instruction_embedded": bool(embedded_short_instruction),
            "message_created_at": user_message.created_at,
        })
        return user_message

    def _begin_assistant_request(self) -> None:
        system_prompt = self.request_system_prompt()
        preview_messages = self.session_messages_for_api()
        self._ensure_safe_session_capacity(
            additional_messages=1,
            auto_answer_only=True,
            pending_messages=preview_messages,
            system_prompt=system_prompt,
        )
        system_prompt = self.request_system_prompt()
        selected_model = self.model_combo.currentText().strip()
        previous_model = (self.last_requested_model or "").strip()
        assistant_message = ChatMessage.now("assistant", "")
        self.current_session.messages.append(assistant_message)
        self.current_assistant_bubble = self.add_message_bubble(assistant_message)
        if self.current_assistant_bubble is not None:
            self.current_assistant_bubble.set_loading(True, selected_model, switched_model=bool(previous_model and previous_model != selected_model))
            try:
                self.current_assistant_bubble.show()
            except Exception:
                pass
        self.current_assistant_text = ""
        self.last_requested_model = selected_model

        messages = self.session_messages_for_api()
        request_prompt_tokens = estimate_chat_payload_tokens(messages, system_prompt)
        self.current_request_debug_info = {
            "prepared_at": datetime.now().isoformat(timespec="seconds"),
            "messages": messages,
            "system_prompt": system_prompt,
            "request_prompt_tokens_estimated": request_prompt_tokens,
            "response_max_tokens": int(self.config.get("chat_max_tokens", 1024) or 1024),
            "request_total_budget_estimated": request_prompt_tokens + int(self.config.get("chat_max_tokens", 1024) or 1024),
        }
        self.current_request_consumes_rollover_short_instruction = False
        self._debug_log("request_prepared", {"request": dict(self.current_request_debug_info)})
        self._set_request_feedback("sent")
        self._flush_chat_ui()
        self.start_worker(messages, system_prompt)
        self.stop_btn.setEnabled(True)
        self._set_request_feedback("waiting")

    def _schedule_auto_answer(self, source_text: str) -> None:
        if not self.auto_answer_checkbox.isChecked():
            return
        if self.worker_thread is not None:
            return
        if self.input_box.toPlainText().strip():
            return
        max_rounds = int(self.config.get("auto_answer_max_rounds", 0) or 0)
        if max_rounds > 0 and self.auto_answer_rounds_current >= max_rounds:
            self.statusBar().showMessage(self.t("auto_answer_limit_reached", "Auto-Answer-Limit erreicht. Schreibe selbst weiter oder erhöhe das Limit in den Einstellungen."), 5000)
            return
        self.pending_auto_answer_source = source_text or ""
        self.auto_answer_timer.start(1200)
        self.statusBar().showMessage(self.t("auto_answer_scheduled", "Automatische Antwort wird vorbereitet …"), 2000)

    def _on_auto_answer_timer(self) -> None:
        if not self.auto_answer_checkbox.isChecked():
            return
        if self.worker_thread is not None:
            return
        if self.input_box.toPlainText().strip():
            return
        phrase_data = load_auto_answer_data()
        question_reply_data = load_auto_answer_question_reply_data()
        if isinstance(phrase_data, dict) and phrase_data.get("enabled", True) is False:
            return
        auto_text = generate_auto_answer(
            self.pending_auto_answer_source,
            self.config.get("interface_language", "de"),
            phrase_data,
            question_reply_data,
            recent_generated_user_messages=self._auto_answer_recent_generated_user_messages(),
            eliza_share_percent=int(self.config.get("auto_answer_eliza_share", 30) or 30),
            use_question_replies_for_all=bool(self.config.get("auto_answer_use_question_replies_for_all", True)),
        )
        if not auto_text:
            return
        self._debug_log("auto_answer_generated", {
            "source_text": self.pending_auto_answer_source,
            "generated_text": auto_text,
        })
        self.pending_auto_answer_source = ""
        message = self._append_user_message(auto_text, generated=True)
        self.pending_auto_submit_message = message
        self.auto_answer_waiting_for_user_audio = True
        if self.config.get("tts_backend", "disabled") == "disabled":
            self.auto_answer_waiting_for_user_audio = False
            self.pending_auto_submit_message = None
            self._begin_assistant_request()
            return
        self.read_aloud_message(message, show_disabled_message=False, allow_autoplay=True)

    def send_message(self) -> None:
        text = self.input_box.toPlainText().strip()
        if not text:
            return
        if self.worker_thread is not None:
            QMessageBox.warning(self, self.t("already_running_title", "Läuft bereits"), self.t("already_running_message", "Es läuft bereits eine Antwortgenerierung."))
            return
        self.auto_answer_timer.stop()
        self.pending_auto_answer_source = ""
        self.pending_auto_submit_message = None
        self.auto_answer_waiting_for_user_audio = False
        self.input_box.clear()
        user_message = self._append_user_message(text)
        self._begin_assistant_request()
        if self.config.get("auto_read_user_inputs", False) and self.config.get("tts_backend", "disabled") != "disabled":
            self.read_aloud_message(user_message, show_disabled_message=False, allow_autoplay=True)

    def start_worker(self, messages: List[dict], system_prompt: str) -> None:
        self.worker_thread = QThread(self)
        self.worker = ChatWorker(
            base_url=self.config.get("ollama_base_url", "http://127.0.0.1:11434").strip(),
            model_name=self.model_combo.currentText().strip(),
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=int(self.config.get("chat_max_tokens", 1024) or 1024),
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.chunk.connect(self.on_worker_chunk)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.failed.connect(self.on_worker_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.cleanup_worker)
        self.send_btn.setEnabled(False)
        self.worker_thread.start()

    def on_worker_chunk(self, text: str) -> None:
        self.current_assistant_text += text
        if self.current_assistant_bubble is not None:
            self.current_assistant_bubble.set_content(self.current_assistant_text)
        self._set_request_feedback("streaming")
        self._flush_chat_ui()

    def on_worker_finished(self) -> None:
        self.stop_btn.setEnabled(False)
        self.send_btn.setEnabled(True)
        self.context_retry_in_progress = False
        final_text = self.current_assistant_text.strip()
        if not final_text:
            final_text = 'Keine Textantwort von Ollama empfangen. Bitte Modell/Prompt prüfen oder erneut senden.'
            if self.current_assistant_bubble is not None:
                self.current_assistant_bubble.set_content(final_text)
        assistant_message = None
        if self.current_session and self.current_session.messages:
            self.current_session.messages[-1].content = final_text
            assistant_message = self.current_session.messages[-1]
            self.store.save(self.current_session)
            self.refresh_sessions_ui()
        self.last_saved_code_paths = save_generated_code_blocks(final_text)
        auto_read = assistant_message is not None and self.config.get("auto_read_assistant_responses", True) and self.config.get("tts_backend", "disabled") != "disabled"
        if assistant_message is not None and auto_read:
            self.read_aloud_message(assistant_message, show_disabled_message=False, allow_autoplay=True)
        if self.auto_answer_checkbox.isChecked() and not self.input_box.toPlainText().strip():
            if auto_read:
                self.pending_auto_answer_source = final_text
            else:
                self._schedule_auto_answer(final_text)
        self.current_request_consumes_rollover_short_instruction = False
        self._set_request_feedback("finished")
        self._flush_chat_ui()
        completion_tokens = estimate_token_count(final_text)
        prompt_tokens = int(self.current_request_debug_info.get("request_prompt_tokens_estimated", 0) or 0)
        self.debug_runtime_requests += 1
        self.debug_runtime_prompt_tokens += prompt_tokens
        self.debug_runtime_completion_tokens += completion_tokens
        if self.current_session is not None:
            stats = self.debug_session_totals.setdefault(self.current_session.session_id, {"requests": 0, "prompt_tokens_estimated": 0, "completion_tokens_estimated": 0})
            stats["requests"] = int(stats.get("requests", 0) or 0) + 1
            stats["prompt_tokens_estimated"] = int(stats.get("prompt_tokens_estimated", 0) or 0) + prompt_tokens
            stats["completion_tokens_estimated"] = int(stats.get("completion_tokens_estimated", 0) or 0) + completion_tokens
        self._debug_log("request_finished", {
            "request": dict(self.current_request_debug_info),
            "assistant_text": final_text,
            "completion_tokens_estimated": completion_tokens,
            "saved_code_paths": [str(path) for path in self.last_saved_code_paths],
            "auto_read_assistant": bool(auto_read),
        })
        self.current_request_debug_info = {}
        if self.last_saved_code_paths:
            self.statusBar().showMessage(self.t("code_blocks_saved_status", "{count} Codeblock/Codeblöcke wurden zusätzlich im Unterordner generated_code gespeichert.").format(count=len(self.last_saved_code_paths)), 5000)
        else:
            self.statusBar().showMessage(self.t("answer_finished", "Antwort abgeschlossen."), 2500)

    def on_worker_failed(self, message: str) -> None:
        self.stop_btn.setEnabled(False)
        self.send_btn.setEnabled(True)
        retry_context = self.auto_answer_checkbox.isChecked() and not self.context_retry_in_progress and is_context_overflow_error(message)
        if retry_context and self.current_session is not None and self.current_session.messages and self.current_session.messages[-1].role == "assistant" and not (self.current_session.messages[-1].content or "").strip():
            self._debug_log("request_failed_context_retry", {"error": message, "request": dict(self.current_request_debug_info)})
            self.current_session.messages.pop()
            if self.current_assistant_bubble is not None:
                try:
                    self.current_assistant_bubble.setParent(None)
                    self.current_assistant_bubble.deleteLater()
                except Exception:
                    pass
                self.current_assistant_bubble = None
            self.context_retry_in_progress = True
            self._ensure_safe_session_capacity(
                additional_messages=1,
                auto_answer_only=True,
                pending_messages=self.session_messages_for_api(),
                system_prompt=self.request_system_prompt(),
            )
            self.store.save(self.current_session)
            self.refresh_sessions_ui()
            self.statusBar().showMessage(self.t("context_retry_status", "Kontextgrenze erkannt. Es wird automatisch mit einem Folge-Chat weitergemacht …"), 5000)
            self._begin_assistant_request()
            return
        self.context_retry_in_progress = False
        self.auto_answer_timer.stop()
        self.pending_auto_answer_source = ""
        self.pending_auto_submit_message = None
        self.auto_answer_waiting_for_user_audio = False
        if self.current_assistant_bubble is not None:
            error_text = f"Fehler bei der Ollama-Anfrage:\n\n{message}"
            self.current_assistant_bubble.set_content(error_text)
        if self.current_session and self.current_session.messages:
            self.current_session.messages[-1].content = f"Fehler bei der Ollama-Anfrage:\n\n{message}"
            self.store.save(self.current_session)
        self._debug_log("request_failed", {"error": message, "request": dict(self.current_request_debug_info)})
        self.current_request_debug_info = {}
        self.current_request_consumes_rollover_short_instruction = False
        self._set_request_feedback("failed")
        self._flush_chat_ui()
        self.statusBar().showMessage(self.t("ollama_failed", "Ollama-Anfrage fehlgeschlagen."), 4000)


    def cleanup_worker(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None

    def stop_generation(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.statusBar().showMessage(self.t("abort_requested", "Abbruch angefordert …"), 2000)
        self.stop_btn.setEnabled(False)

    def scroll_to_bottom(self) -> None:
        bar = self.chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _prepare_tts_text(self, message: ChatMessage) -> str:
        original_text = message_visible_content(message).strip()
        text = markdown_to_tts_text(original_text)
        if self.config.get("tts_lexicon_enabled", self.config.get("windows_sapi_lexicon_enabled", True)):
            text = apply_sapi_lexicon(text, load_sapi_lexicon())
        if self.config.get("strip_emojis_for_tts", True):
            text = strip_emojis_and_symbols(text)
        return text.strip()

    def _tts_voice_for_message(self, message: ChatMessage) -> str:
        if message.role == "user":
            return (self.config.get("tts_user_voice", "") or self.config.get("tts_voice", "")).strip()
        return (self.config.get("tts_voice", "")).strip()

    def _conversation_segments(self) -> List[dict]:
        segments: List[dict] = []
        if not self.current_session:
            return segments
        include_names = bool(self.config.get("read_all_include_names", False))
        for message in self.current_session.messages:
            text = self._prepare_tts_text(message)
            if not text:
                continue
            if include_names:
                speaker = resolve_display_name(self.config, message.role)
                text = f"{speaker}: {text}".strip()
            segments.append({
                "role": message.role,
                "text": text,
                "voice": self._tts_voice_for_message(message),
            })
        return segments

    def _clear_audio_state(self) -> None:
        self.current_playback_stoppable = False
        self.current_audio_message = None
        self.current_audio_backend = ''
        self.current_audio_text = ''
        self.current_audio_sentences = []
        self.current_audio_sentence_index = 0
        self.audio_stop_requested = False
        self.audio_playback_thread = None

    def _start_windows_sapi_sentence_playback(self, message: ChatMessage, start_sentence_index: int = 0) -> None:
        text = self._prepare_tts_text(message)
        if not text:
            QMessageBox.information(self, self.t("empty_message_title", "Leere Nachricht"), self.t("empty_message_message", "Diese Nachricht enthält keinen vorlesbaren Text."))
            return

        sentences = split_tts_sentences(text)
        if not sentences:
            QMessageBox.information(self, self.t("empty_message_title", "Leere Nachricht"), self.t("empty_message_message", "Diese Nachricht enthält keinen vorlesbaren Text."))
            return

        start_sentence_index = max(0, min(start_sentence_index, len(sentences) - 1))
        self.audio_stop_requested = False
        self.audio_generation_id += 1
        generation_id = self.audio_generation_id
        self.current_audio_message = message
        self.current_audio_backend = 'windows_sapi'
        self.current_audio_text = text
        self.current_audio_sentences = sentences
        self.current_audio_sentence_index = start_sentence_index

        client = TTSClient(
            backend='windows_sapi',
            base_url=self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"),
            voice=self._tts_voice_for_message(message),
            model=self.config.get("tts_model", "tts-1-hd"),
            audio_format='wav',
            windows_sapi_rate=int(self.config.get("windows_sapi_rate", 0)),
            windows_sapi_pitch=int(self.config.get("windows_sapi_pitch", 3)),
            windows_sapi_volume=int(self.config.get("windows_sapi_volume", 100)),
            windows_sapi_language=self.current_sapi_language_tag(),
        )

        def worker_run(gen_id: int, start_idx: int) -> None:
            try:
                if not sys.platform.startswith('win'):
                    raise RuntimeError('Windows-SAPI ist nur unter Windows verfügbar.')
                import winsound
                for idx in range(start_idx, len(sentences)):
                    if gen_id != self.audio_generation_id:
                        return
                    self.current_audio_sentence_index = idx
                    target = AUDIO_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{idx:03d}.wav"
                    path = client.synthesize_to_file(sentences[idx], target)
                    if gen_id != self.audio_generation_id:
                        return
                    message.audio_path = str(path)
                    self.current_playback_stoppable = True
                    try:
                        winsound.PlaySound(str(path), winsound.SND_FILENAME)
                    except Exception as play_exc:
                        raise RuntimeError(f'Windows-Audiowiedergabe fehlgeschlagen: {play_exc}')
                    finally:
                        self.current_playback_stoppable = False
                    if self.audio_stop_requested:
                        if gen_id == self.audio_generation_id:
                            self._clear_audio_state()
                            self.audio_status_signal.emit(self.t("audio_stopped", "Audio gestoppt."))
                        return
                    if gen_id != self.audio_generation_id:
                        return
                if gen_id == self.audio_generation_id:
                    self._clear_audio_state()
                    self.audio_feedback_signal.emit('done', self.t("audio_finished", "Sprachausgabe beendet."))
                    self.audio_status_signal.emit(self.t("audio_finished", "Sprachausgabe beendet."))
            except Exception as exc:
                self.current_playback_stoppable = False
                if gen_id == self.audio_generation_id:
                    self._clear_audio_state()
                    self.audio_error_signal.emit(str(exc))

        self.audio_playback_thread = threading.Thread(target=worker_run, args=(generation_id, start_sentence_index), daemon=True)
        self.audio_playback_thread.start()

    def _start_external_segments_playback(self, segments: List[dict], backend: str, primary_message: Optional[ChatMessage] = None) -> None:
        self.audio_stop_requested = False
        self.audio_generation_id += 1
        generation_id = self.audio_generation_id
        self.current_audio_message = primary_message
        self.current_audio_backend = backend
        self.current_audio_text = "\n".join(segment.get("text", "") for segment in segments)
        self.current_audio_sentences = []
        self.current_audio_sentence_index = 0

        def worker_run(gen_id: int) -> None:
            try:
                if not sys.platform.startswith('win'):
                    raise RuntimeError('Automatisches Playback ist hier nur unter Windows vollständig implementiert.')
                import winsound
                total_segments = max(1, sum(1 for seg in segments if str(seg.get('text', '')).strip()))
                processed_segments = 0
                for index, segment in enumerate(segments):
                    if gen_id != self.audio_generation_id:
                        return
                    text = str(segment.get("text", "")).strip()
                    if not text:
                        continue
                    processed_segments += 1
                    voice = str(segment.get("voice", "")).strip()
                    target = AUDIO_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{index:03d}.wav"
                    progress_text = self.t("tts_feedback_generating_segment", "Sprachausgabe wird erzeugt … Segment {current}/{total}").format(current=processed_segments, total=total_segments)
                    self.audio_feedback_signal.emit('generating', progress_text)
                    client = TTSClient(
                        backend=backend,
                        base_url=self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"),
                        voice=voice or self.config.get("tts_voice", "Emma"),
                        model=self.config.get("tts_model", "tts-1-hd"),
                        audio_format='wav',
                        windows_sapi_rate=int(self.config.get("windows_sapi_rate", 0)),
                        windows_sapi_pitch=int(self.config.get("windows_sapi_pitch", 3)),
                        windows_sapi_volume=int(self.config.get("windows_sapi_volume", 100)),
                        windows_sapi_language=self.current_sapi_language_tag(),
                    )
                    path = client.synthesize_to_file(text, target)
                    if gen_id != self.audio_generation_id:
                        return
                    self.audio_feedback_signal.emit('playing', self.t("tts_feedback_playing_segment", "Sprachausgabe wird abgespielt … Segment {current}/{total}").format(current=processed_segments, total=total_segments))
                    self.current_playback_stoppable = True
                    try:
                        winsound.PlaySound(str(path), winsound.SND_FILENAME)
                    except Exception as play_exc:
                        raise RuntimeError(f'Windows-Audiowiedergabe fehlgeschlagen: {play_exc}')
                    finally:
                        self.current_playback_stoppable = False
                    if primary_message is not None:
                        primary_message.audio_path = str(path)
                if gen_id == self.audio_generation_id:
                    self._clear_audio_state()
                    self.audio_feedback_signal.emit('done', self.t("audio_finished", "Sprachausgabe beendet."))
                    self.audio_status_signal.emit(self.t("audio_finished", "Sprachausgabe beendet."))
            except Exception as exc:
                self.current_playback_stoppable = False
                if gen_id == self.audio_generation_id:
                    self._clear_audio_state()
                    self.audio_error_signal.emit(str(exc))

        self.audio_playback_thread = threading.Thread(target=worker_run, args=(generation_id,), daemon=True)
        self.audio_playback_thread.start()

    def read_aloud_conversation(self) -> None:
        backend = self.config.get("tts_backend", "disabled")
        if backend == "disabled":
            QMessageBox.information(self, self.t("tts_disabled_title", "TTS deaktiviert"), self.t("tts_disabled_message", "TTS ist deaktiviert."))
            return
        segments = self._conversation_segments()
        if not segments:
            QMessageBox.information(self, self.t("empty_message_title", "Leere Nachricht"), self.t("empty_message_message", "Diese Nachricht enthält keinen vorlesbaren Text."))
            return
        self.stop_audio_playback(silent=True)
        if backend == "vibevoice_openai":
            manager = VibeVoiceManager(self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"), self.t)
            try:
                prep = self.t("vibevoice_autostart_prepare", "Prüfe lokalen VibeVoice-Server …")
                self.statusBar().showMessage(prep, 0)
                self.audio_feedback_signal.emit('checking', prep)
                QApplication.processEvents()
                def _autostart_log(msg: str) -> None:
                    self.statusBar().showMessage(msg, 0)
                    self.audio_feedback_signal.emit('generating', msg)
                    QApplication.processEvents()
                started = manager.ensure_server_running(_autostart_log, max_wait=120)
                if started:
                    self.statusBar().showMessage(self.t("vibevoice_autostart_ready", "VibeVoice wurde automatisch gestartet."), 3500)
            except Exception as exc:
                QMessageBox.critical(self, self.t("tts_error_title", "TTS-Fehler"), self.t("vibevoice_autostart_failed_ui", "Der lokale VibeVoice-Server konnte nicht automatisch gestartet werden:") + f"\n\n{exc}")
                return
        if backend == "windows_sapi":
            self._start_windows_sapi_segments_playback(segments)
        else:
            self._start_external_segments_playback(segments, backend)
        self.statusBar().showMessage(self.t("audio_playback_started", "Sprachausgabe gestartet."), 2500)

    def _start_windows_sapi_segments_playback(self, segments: List[dict]) -> None:
        self.audio_stop_requested = False
        self.audio_generation_id += 1
        generation_id = self.audio_generation_id
        self.current_audio_message = None
        self.current_audio_backend = 'windows_sapi'
        self.current_audio_text = "\n".join(segment.get("text", "") for segment in segments)
        self.current_audio_sentences = []
        self.current_audio_sentence_index = 0

        def worker_run(gen_id: int) -> None:
            try:
                if not sys.platform.startswith('win'):
                    raise RuntimeError('Windows-SAPI ist nur unter Windows verfügbar.')
                import winsound
                total_sentences = 0
                for seg in segments:
                    seg_text = str(seg.get('text', '')).strip()
                    if seg_text:
                        total_sentences += max(1, len(split_tts_sentences(seg_text)))
                total_sentences = max(1, total_sentences)
                sentence_counter = 0
                for segment in segments:
                    if gen_id != self.audio_generation_id:
                        return
                    text = str(segment.get("text", "")).strip()
                    if not text:
                        continue
                    client = TTSClient(
                        backend='windows_sapi',
                        base_url=self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"),
                        voice=str(segment.get("voice", "")).strip(),
                        model=self.config.get("tts_model", "tts-1-hd"),
                        audio_format='wav',
                        windows_sapi_rate=int(self.config.get("windows_sapi_rate", 0)),
                        windows_sapi_pitch=int(self.config.get("windows_sapi_pitch", 3)),
                        windows_sapi_volume=int(self.config.get("windows_sapi_volume", 100)),
                        windows_sapi_language=self.current_sapi_language_tag(),
                    )
                    for sentence in split_tts_sentences(text):
                        if gen_id != self.audio_generation_id:
                            return
                        self.current_audio_sentence_index = sentence_counter
                        sentence_counter += 1
                        target = AUDIO_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{sentence_counter:03d}.wav"
                        self.audio_feedback_signal.emit('generating', self.t("tts_feedback_generating_sentence", "Sprachausgabe wird erzeugt … Satz {current}/{total}").format(current=sentence_counter, total=total_sentences))
                        path = client.synthesize_to_file(sentence, target)
                        if gen_id != self.audio_generation_id:
                            return
                        self.audio_feedback_signal.emit('playing', self.t("tts_feedback_playing_sentence", "Sprachausgabe wird abgespielt … Satz {current}/{total}").format(current=sentence_counter, total=total_sentences))
                        self.current_playback_stoppable = True
                        try:
                            winsound.PlaySound(str(path), winsound.SND_FILENAME)
                        except Exception as play_exc:
                            raise RuntimeError(f'Windows-Audiowiedergabe fehlgeschlagen: {play_exc}')
                        finally:
                            self.current_playback_stoppable = False
                        if self.audio_stop_requested:
                            if gen_id == self.audio_generation_id:
                                self._clear_audio_state()
                                self.audio_status_signal.emit(self.t("audio_stopped", "Audio gestoppt."))
                            return
                if gen_id == self.audio_generation_id:
                    self._clear_audio_state()
                    self.audio_status_signal.emit(self.t("audio_finished", "Sprachausgabe beendet."))
            except Exception as exc:
                self.current_playback_stoppable = False
                if gen_id == self.audio_generation_id:
                    self._clear_audio_state()
                    self.audio_error_signal.emit(str(exc))

        self.audio_playback_thread = threading.Thread(target=worker_run, args=(generation_id,), daemon=True)
        self.audio_playback_thread.start()

    def export_current_chat_pdf(self) -> None:
        if not self.current_session or not self.current_session.messages:
            QMessageBox.information(self, self.t("export_pdf_button", "Chat exportieren"), self.t("empty_message_message", "Diese Nachricht enthält keinen vorlesbaren Text."))
            return
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r'[^A-Za-z0-9._-]+', '_', self.current_session.title).strip('_') or 'chat_export'
        default_path = EXPORTS_DIR / f"{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        selected_path, _ = QFileDialog.getSaveFileName(self, self.t("export_pdf_button", "Chat exportieren"), str(default_path), 'PDF (*.pdf)')
        if not selected_path:
            return
        if not selected_path.lower().endswith('.pdf'):
            selected_path += '.pdf'

        body_parts = [
            "<html><head><meta charset='utf-8'><style>",
            "body { font-family: 'Segoe UI', sans-serif; color: #1b2330; }",
            ".cover { margin-bottom: 24px; }",
            ".title { font-size: 22pt; font-weight: 700; color: #243752; margin-bottom: 6px; }",
            ".meta { color: #52627a; font-size: 9pt; margin-bottom: 14px; }",
            ".msg { border: 1px solid #ccd7e6; border-radius: 12px; padding: 12px 14px; margin: 10px 0 16px 0; }",
            ".msg.user { background: #eef4ff; }",
            ".msg.assistant { background: #f6f8fb; border-left: 4px solid #6ea8ff; }",
            ".msgmeta { font-size: 9pt; color: #52627a; margin-bottom: 8px; }",
            "p { margin: 0 0 8px 0; } ul,ol { margin-top: 4px; } code { background: #eef2f7; padding: 1px 4px; border-radius: 4px; } pre { background: #eef2f7; padding: 8px; border-radius: 8px; }",
            "</style></head><body>",
        ]
        body_parts.append(f"<div class='cover'><div class='title'>{html.escape(self.current_session.title)}</div><div class='meta'>{html.escape(self.t('model_label', 'Modell'))}: {html.escape(self.current_session.model_name or self.model_combo.currentText().strip())}<br>{html.escape(self.t('export_pdf_created', 'Exportiert am'))}: {html.escape(pretty_timestamp(datetime.now().isoformat(timespec='seconds')))}</div></div>")
        for message in self.current_session.messages:
            role_label = resolve_display_name(self.config, message.role)
            msg_class = 'assistant' if message.role == 'assistant' else 'user'
            rendered = markdown.markdown(message.content if message.role == 'assistant' else html.escape(message_visible_content(message)), extensions=['fenced_code', 'tables'])
            body_parts.append(f"<div class='msg {msg_class}'><div class='msgmeta'>{html.escape(role_label)} · {html.escape(pretty_timestamp(message.created_at))}</div>{rendered}</div>")
        body_parts.append('</body></html>')
        html_doc = ''.join(body_parts)

        document = QTextDocument()
        document.setHtml(html_doc)
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(selected_path)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageMargins(QMarginsF(16, 16, 16, 16), QPageLayout.Unit.Millimeter)
        document.print(printer)
        self.statusBar().showMessage(self.t('export_pdf_done', 'PDF exportiert: {path}').format(path=selected_path), 5000)

    def _on_audio_error(self, message: str) -> None:
        self.audio_feedback_signal.emit('error', self.t("audio_failed", "Sprachausgabe fehlgeschlagen."))
        self.statusBar().showMessage(self.t("audio_failed", "Sprachausgabe fehlgeschlagen.") + f" {message}", 7000)
        waiting_submit = self.pending_auto_submit_message is not None and self.auto_answer_waiting_for_user_audio
        pending_source = bool(self.pending_auto_answer_source)
        QMessageBox.warning(
            self,
            self.t("tts_error_title", "TTS-Fehler"),
            self.t("tts_error_message", "Die Sprachausgabe ist fehlgeschlagen:") + f"\n\n{message}",
        )
        if waiting_submit and self.worker_thread is None:
            self.auto_answer_waiting_for_user_audio = False
            self.pending_auto_submit_message = None
            self._begin_assistant_request()
        elif pending_source:
            source = self.pending_auto_answer_source
            self.pending_auto_answer_source = ""
            self._schedule_auto_answer(source)

    def _on_audio_status(self, message: str) -> None:
        if message == self.t("audio_finished", "Sprachausgabe beendet."):
            self.audio_feedback_signal.emit('done', message)
        elif message == self.t("audio_stopped", "Audio gestoppt."):
            self.audio_feedback_signal.emit('done', message)
        self.statusBar().showMessage(message, 3000)
        finished_msg = self.t("audio_finished", "Sprachausgabe beendet.")
        if message == finished_msg:
            if self.pending_auto_submit_message is not None and self.auto_answer_waiting_for_user_audio and self.worker_thread is None:
                self.auto_answer_waiting_for_user_audio = False
                self.pending_auto_submit_message = None
                self._begin_assistant_request()
                return
            if self.pending_auto_answer_source and self.auto_answer_checkbox.isChecked() and not self.input_box.toPlainText().strip():
                source = self.pending_auto_answer_source
                self.pending_auto_answer_source = ""
                self._schedule_auto_answer(source)


    def current_sapi_language_tag(self) -> str:
        code = (self.config.get("interface_language", "de") or "de").lower()
        if code.startswith("en"):
            return "en-US"
        if code.startswith("fr"):
            return "fr-FR"
        if code.startswith("es"):
            return "es-ES"
        if code.startswith("ru"):
            return "ru-RU"
        return "de-DE"

    def read_aloud_message(self, message: ChatMessage, show_disabled_message: bool = True, allow_autoplay: bool = True) -> None:
        backend = self.config.get("tts_backend", "disabled")
        if backend == "disabled":
            if show_disabled_message:
                QMessageBox.information(self, self.t("tts_disabled_title", "TTS deaktiviert"), self.t("tts_disabled_message", "TTS ist deaktiviert."))
            return

        text = self._prepare_tts_text(message)
        if not text:
            QMessageBox.information(self, self.t("empty_message_title", "Leere Nachricht"), self.t("empty_message_message", "Diese Nachricht enthält keinen vorlesbaren Text."))
            return

        self.stop_audio_playback(silent=True)

        if backend == "windows_sapi":
            self.statusBar().showMessage(self.t("audio_preparing", "Sprachausgabe wird vorbereitet …"), 2500)
            self._start_windows_sapi_sentence_playback(message, start_sentence_index=0)
            self.statusBar().showMessage(self.t("audio_playback_started", "Sprachausgabe gestartet."), 2500)
            return

        if backend == "vibevoice_openai":
            manager = VibeVoiceManager(self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"), self.t)
            try:
                prep = self.t("vibevoice_autostart_prepare", "Prüfe lokalen VibeVoice-Server …")
                self.statusBar().showMessage(prep, 0)
                self.audio_feedback_signal.emit('checking', prep)
                QApplication.processEvents()
                def _autostart_log(msg: str) -> None:
                    self.statusBar().showMessage(msg, 0)
                    self.audio_feedback_signal.emit('generating', msg)
                    QApplication.processEvents()
                started = manager.ensure_server_running(_autostart_log, max_wait=120)
                if started:
                    self.statusBar().showMessage(self.t("vibevoice_autostart_ready", "VibeVoice wurde automatisch gestartet."), 3500)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    self.t("tts_error_title", "TTS-Fehler"),
                    self.t("vibevoice_autostart_failed_ui", "Der lokale VibeVoice-Server konnte nicht automatisch gestartet werden:") + f"\n\n{exc}",
                )
                return

        segment = {"role": message.role, "text": text, "voice": self._tts_voice_for_message(message)}
        self._start_external_segments_playback([segment], backend, primary_message=message)
        self.statusBar().showMessage(self.t("audio_playback_started", "Sprachausgabe gestartet."), 2500)

    def stop_audio_playback(self, silent: bool = False, preserve_state: bool = False) -> None:
        stoppable = False
        had_audio = self.current_audio_message is not None or self.audio_playback_thread is not None or bool(self.current_audio_backend)
        deferred_windows_sapi_stop = (
            had_audio
            and self.current_audio_backend == 'windows_sapi'
            and self.audio_playback_thread is not None
            and self.audio_playback_thread.is_alive()
            and not preserve_state
        )
        if deferred_windows_sapi_stop:
            self.audio_stop_requested = True
            self.current_playback_stoppable = False
            stoppable = True
        else:
            if had_audio:
                self.audio_generation_id += 1
            try:
                if sys.platform.startswith('win') and self.current_playback_stoppable:
                    import winsound
                    try:
                        winsound.PlaySound(None, winsound.SND_PURGE)
                    except Exception:
                        winsound.PlaySound(None, 0)
                    stoppable = True
                    self.current_playback_stoppable = False
            except Exception:
                stoppable = False

            if not preserve_state and had_audio:
                self._clear_audio_state()

        if not silent:
            if deferred_windows_sapi_stop:
                msg = self.t("audio_stop_after_sentence", "Audio stoppt nach dem aktuellen Satz.")
                self.audio_feedback_signal.emit('busy', msg)
                self.statusBar().showMessage(msg, 3000)
            elif stoppable or had_audio:
                msg = self.t("audio_stopped", "Audio gestoppt.")
                self.audio_feedback_signal.emit('done', msg)
                self.statusBar().showMessage(msg, 2500)
            else:
                self.statusBar().showMessage(self.t("audio_stop_not_available", "Das aktuelle Playback lässt sich nicht direkt stoppen."), 4000)

        if not preserve_state and had_audio and not deferred_windows_sapi_stop:
            if self.pending_auto_submit_message is not None and self.auto_answer_waiting_for_user_audio and self.worker_thread is None:
                self.auto_answer_waiting_for_user_audio = False
                self.pending_auto_submit_message = None
                self._begin_assistant_request()
            elif self.pending_auto_answer_source and self.auto_answer_checkbox.isChecked() and not self.input_box.toPlainText().strip():
                source = self.pending_auto_answer_source
                self.pending_auto_answer_source = ""
                self._schedule_auto_answer(source)

    def try_play_wav(self, path: Path) -> None:
        try:
            self.stop_audio_playback(silent=True)
            if sys.platform.startswith('win'):
                import winsound
                try:
                    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                    self.current_playback_stoppable = True
                except Exception:
                    os.startfile(str(path))
                    self.current_playback_stoppable = False
            else:
                self.current_playback_stoppable = False
                self.statusBar().showMessage(self.t("audio_saved_manual_playback", 'Audio gespeichert unter {path}. Automatisches Abspielen ist hier nicht implementiert.').format(path=path), 6000)
        except Exception as exc:
            self.current_playback_stoppable = False
            self.statusBar().showMessage(self.t("audio_saved_playback_failed", 'Audio wurde gespeichert, Playback schlug fehl: {error}').format(error=exc), 6000)

    def show_settings(self) -> None:
        dialog = SettingsDialog(self.config, self, self.show_tts_setup)
        if dialog.exec():
            old_config = dict(self.config)
            old_lang = old_config.get("interface_language", "de")
            old_theme = old_config.get("theme", "Midnight")

            self.config = dialog.get_config()
            self.config, _ = resolve_tts_voice_config_defaults(self.config)
            debug_log_created = self.debug_logger.set_enabled(bool(self.config.get("debug_trace_enabled", False)))
            save_config(self.config)
            self.auto_answer_checkbox.setChecked(bool(self.config.get("auto_answer_enabled", True)))

            lang_changed = old_lang != self.config.get("interface_language", "de")
            theme_changed = old_theme != self.config.get("theme", "Midnight")
            tts_keys = {
                "tts_backend", "tts_base_url", "tts_voice", "tts_model", "tts_format",
                "autoplay_tts", "auto_read_assistant_responses", "auto_read_user_inputs",
                "tts_user_voice", "tts_lexicon_enabled", "windows_sapi_lexicon_enabled", "windows_sapi_rate",
                "windows_sapi_pitch", "windows_sapi_volume", "read_all_include_names",
                "user_display_name", "assistant_display_name", "strip_emojis_for_tts",
                "chat_max_tokens", "auto_answer_max_rounds", "auto_answer_short_answers",
                "auto_answer_eliza_share", "auto_answer_phrase_repeat_lookback",
                "context_message_limit", "tts_voice_defaults_initialized"
            }
            tts_changed = any(old_config.get(k) != self.config.get(k) for k in tts_keys)
            restarted_tts = False

            if theme_changed:
                self.apply_theme(self.config.get("theme", "Midnight"))

            if lang_changed:
                self.reload_language_pack()
                self.refresh_ui_texts()

            self.refresh_visible_bubble_role_labels()

            if self.current_session is not None:
                self.current_session.model_name = self.model_combo.currentText().strip()
                self.store.save(self.current_session)

            if tts_changed and self.current_audio_message is not None:
                replay_message = self.current_audio_message
                if self.current_audio_backend == "windows_sapi":
                    resume_sentence_index = self.current_audio_sentence_index
                    self.stop_audio_playback(silent=True, preserve_state=True)
                    if self.config.get("tts_backend", "disabled") == "windows_sapi":
                        QTimer.singleShot(0, lambda m=replay_message, idx=resume_sentence_index: self._start_windows_sapi_sentence_playback(m, start_sentence_index=idx))
                        self.statusBar().showMessage(self.t("tts_resumed_after_settings", "Laufende Sprachausgabe mit neuen Einstellungen am aktuellen Satz fortgesetzt."), 4000)
                    elif self.config.get("tts_backend", "disabled") != "disabled":
                        QTimer.singleShot(0, lambda m=replay_message: self.read_aloud_message(m, show_disabled_message=False, allow_autoplay=True))
                        self.statusBar().showMessage(self.t("tts_restarted_after_settings", "Laufende Sprachausgabe mit neuen Einstellungen neu gestartet."), 3500)
                    else:
                        self._clear_audio_state()
                        self.statusBar().showMessage(self.t("audio_stopped", "Audio gestoppt."), 2500)
                    restarted_tts = True
                elif self.current_playback_stoppable:
                    self.stop_audio_playback(silent=True)
                    if self.config.get("tts_backend", "disabled") != "disabled":
                        QTimer.singleShot(0, lambda m=replay_message: self.read_aloud_message(m, show_disabled_message=False, allow_autoplay=True))
                        self.statusBar().showMessage(self.t("tts_restarted_after_settings", "Laufende Sprachausgabe mit neuen Einstellungen neu gestartet."), 3500)
                    else:
                        self.statusBar().showMessage(self.t("audio_stopped", "Audio gestoppt."), 2500)
                    restarted_tts = True

            self._debug_log("settings_saved", {"debug_log_created": bool(debug_log_created), "old_config": old_config, "new_config": self._debug_config_snapshot()})
            if not restarted_tts:
                if self.config.get("debug_trace_enabled", False):
                    self.statusBar().showMessage(self.t("debug_trace_enabled_status", "Debug-Log aktiv: {path}").format(path=str(self.debug_logger.path)), 5000)
                else:
                    msg_key = "language_changed" if lang_changed else "settings_saved"
                    default_msg = "Sprache der Oberfläche geändert." if msg_key == "language_changed" else "Einstellungen gespeichert."
                    self.statusBar().showMessage(self.t(msg_key, default_msg), 2500)

    def show_tts_setup(self) -> None:
        dialog = TTSSetupDialog(self.config, self)
        dialog.exec()

    def closeEvent(self, event) -> None:
        if self.worker is not None:
            self.worker.cancel()
        if self.current_session is not None:
            self.store.save(self.current_session)
        self.stop_audio_playback(silent=True)
        super().closeEvent(event)


def main() -> int:
    ensure_directories()
    app = QApplication(sys.argv)
    app.setApplicationName("OllamaVibeDesk")
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    try:
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception:
        traceback.print_exc()
        QMessageBox.critical(
            None,
            "Startfehler",
            "Die Anwendung konnte nicht gestartet werden.\n\n"
            + traceback.format_exc(),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
