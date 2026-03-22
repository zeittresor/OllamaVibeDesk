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
from PyQt6.QtGui import QAction, QCursor, QDesktopServices, QFont, QTextOption, QTextDocument, QPageLayout, QPageSize
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
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import AUDIO_DIR, CHATS_DIR, EXPORTS_DIR, SAPI_LEXICON_PATH, AUTO_ANSWER_PATH, load_config, save_config, ensure_directories
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
        body { font-family: 'Segoe UI', 'Inter', sans-serif; line-height: 1.45; }
        p { margin: 0 0 0.7em 0; }
        pre { background: rgba(0,0,0,0.22); padding: 10px; border-radius: 10px; overflow-x: auto; }
        code { background: rgba(0,0,0,0.16); padding: 2px 4px; border-radius: 6px; }
        a { color: #7ab3ff; text-decoration: none; }
        ul, ol { margin-top: 0.3em; }
    </style>
    """
    return css + html_text


def load_auto_answer_data() -> dict:
    ensure_directories()
    try:
        return json.loads(AUTO_ANSWER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": True, "phrases": {"de": []}}


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


def resolve_display_name(config: dict, role: str) -> str:
    user_default, assistant_default = default_role_names(config.get("interface_language", "de"))
    if role == "assistant":
        return (config.get("assistant_display_name", "") or "").strip() or assistant_default
    return (config.get("user_display_name", "") or "").strip() or user_default


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


def generate_auto_answer(source_text: str, language_code: str, phrase_data: dict | None = None) -> str:
    cleaned = markdown_to_tts_text(source_text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "das" if (language_code or "de").startswith("de") else "that"
    fragment = cleaned[:180].strip(" .!?…:;,-") or cleaned[:180]
    code = (language_code or "de").lower()
    phrases = []
    if isinstance(phrase_data, dict):
        phrases_map = phrase_data.get("phrases")
        if isinstance(phrases_map, dict):
            phrases = [str(x).strip() for x in phrases_map.get(code, []) if str(x).strip()]
            if not phrases and code != "en":
                phrases = [str(x).strip() for x in phrases_map.get("en", []) if str(x).strip()]

    if code.startswith("de"):
        reflected = _reflect_fragment_de(fragment)
        templates = [
            f"Das ist interessant. Erzähl bitte weiter.",
            f"Warum denkst du {reflected}?",
            f"Hast du dabei Bedenken?",
            f"Und wie betrachtest du das kritisch?",
            f"Interessant — wie könnte sich das noch entwickeln?",
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

    candidates = [t for t in templates if t.strip()]
    if phrases:
        candidates.extend(phrases)
    return random.choice(candidates).strip()


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
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.message = message
        self.is_assistant = is_assistant
        self.on_read_aloud = on_read_aloud
        self.on_stop_audio = on_stop_audio
        self.on_copy = on_copy
        self.translate = translate or (lambda key, default=None: default or key)
        self.setObjectName("BubbleWidget")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.card = QFrame()
        self.card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.card.setMaximumWidth(980 if is_assistant else 760)
        self.card.setMinimumWidth(460 if is_assistant else 280)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        meta = QLabel(
            (self.translate("assistant_label", "Assistent") if is_assistant else self.translate("you_label", "Du"))
            + " · "
            + pretty_timestamp(message.created_at)
        )
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

        self.set_content(message.content)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch()

        if self.on_copy is not None:
            copy_btn = QPushButton(self.translate("copy_button", "Kopieren"))
            copy_btn.clicked.connect(lambda: self.on_copy(self.message.content))
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
                target = min(1400, max(520, int(available * 0.72)))
                target = min(target, available)
                self.card.setMinimumWidth(target)
                self.card.setMaximumWidth(target)
            else:
                target = min(900, max(280, int(available * 0.52)))
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
            height = int(doc.size().height()) + 14
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

    def set_content(self, text: str) -> None:
        self.message.content = text
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

    def __init__(self, base_url: str, model_name: str, messages: List[dict], system_prompt: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.model_name = model_name
        self.messages = messages
        self.system_prompt = system_prompt
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


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent: Optional[QWidget] = None, open_tts_setup_callback: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.config = config.copy()
        self.translations = load_language_pack(self.config.get("interface_language", "de"))
        self.open_tts_setup_callback = open_tts_setup_callback
        self.setWindowTitle(self.t("settings_title", "Einstellungen"))
        self.setModal(True)
        self.resize(760, 760)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(self.scroll, 1)

        self.content = QWidget()
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

        self.tts_hint = QLabel()
        self.tts_hint.setObjectName("SubtleLabel")
        self.tts_hint.setWordWrap(True)
        self.content_layout.addWidget(self.tts_hint)

        self.tts_url = QLineEdit(self.config["tts_base_url"])
        add_row(self.t("tts_base_url_label", "TTS Base URL"), self.tts_url)

        self.tts_voice = QComboBox()
        self.tts_voice.setEditable(True)
        self.tts_voice.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.tts_voice_row = add_row(self.t("tts_voice_label", "Sprecher / Stimme (Assistent)"), self.tts_voice)

        self.user_tts_voice = QComboBox()
        self.user_tts_voice.setEditable(True)
        self.user_tts_voice.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.user_tts_voice_row = add_row(self.t("tts_user_voice_label", "Sprecher / Stimme (Benutzer)"), self.user_tts_voice)

        self.tts_model = QLineEdit(self.config["tts_model"])
        add_row(self.t("tts_model_label", "TTS Modell"), self.tts_model)

        self.autoplay = QCheckBox(self.t("autoplay_label", "Audio nach dem Erzeugen direkt abspielen"))
        self.autoplay.setChecked(bool(self.config.get("autoplay_tts", True)))
        self.content_layout.addWidget(self.autoplay)

        self.auto_read_responses = QCheckBox(self.t("auto_read_label", "Jede neue Assistent-Antwort automatisch vorlesen"))
        self.auto_read_responses.setChecked(bool(self.config.get("auto_read_assistant_responses", True)))
        self.auto_read_responses.setToolTip(self.t("auto_read_tooltip", "Wenn aktiv, wird nach jeder neuen Assistent-Antwort automatisch TTS erzeugt und abgespielt."))
        self.content_layout.addWidget(self.auto_read_responses)

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

        lexicon_row = QHBoxLayout()
        self.tts_lexicon = QCheckBox(self.t("tts_lexicon_label", "TTS Aussprache-Lexikon verwenden"))
        self.tts_lexicon.setChecked(bool(self.config.get("tts_lexicon_enabled", self.config.get("windows_sapi_lexicon_enabled", True))))
        self.tts_lexicon.setToolTip(self.t("tts_lexicon_tooltip", "Wendet vor dem Vorlesen ein lokales JSON-Lexikon auf den bereinigten Text an."))
        lexicon_row.addWidget(self.tts_lexicon, 1)
        self.edit_sapi_lexicon_btn = QPushButton(self.t("edit_lexicon", "Lexikon bearbeiten …"))
        self.edit_sapi_lexicon_btn.clicked.connect(self.edit_sapi_lexicon)
        lexicon_row.addWidget(self.edit_sapi_lexicon_btn)
        self.content_layout.addLayout(lexicon_row)

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

        tts_tools_row = QHBoxLayout()
        tts_tools_row.addStretch()
        self.open_tts_setup_btn = QPushButton(self.t("vibevoice_setup_open", "VibeVoice-Setup öffnen …"))
        self.open_tts_setup_btn.clicked.connect(self.open_tts_setup)
        tts_tools_row.addWidget(self.open_tts_setup_btn)
        self.content_layout.addLayout(tts_tools_row)
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
            hint = self.t("tts_hint_vibevoice", "Benötigt den lokalen VibeVoice-Wrapper. Stimmen aus app_data/tts/vibevoice_openai/models/voices werden zusätzlich erkannt; falls sie nur als lokale Datei erscheinen, den Wrapper einmal neu starten. Zusätzliche offizielle Presets können im VibeVoice-Setup heruntergeladen werden.")
            default_voice = "Emma"
        else:
            hint = self.t("tts_hint_disabled", "TTS ist deaktiviert.")

        try:
            client = TTSClient(
                backend=backend,
                base_url=self.tts_url.text().strip() or self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"),
                voice=current_voice or self.config.get("tts_voice", default_voice),
                model=self.tts_model.text().strip() or self.config.get("tts_model", "tts-1-hd"),
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
        final_voice = current_voice or config_voice
        final_user_voice = current_user_voice or config_user_voice
        self._apply_voice_selection(self.tts_voice, voice_entries, final_voice, backend)
        self._apply_voice_selection(self.user_tts_voice, voice_entries, final_user_voice, backend)
        visible = backend != "disabled"
        self.tts_voice_row.setVisible(visible)
        self.user_tts_voice_row.setVisible(visible)
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
        dialog = AutoAnswerPhrasesDialog(self.config.get("interface_language", "de"), self)
        dialog.exec()

    def _refresh_name_placeholders(self) -> None:
        lang = (self.interface_language.currentData() or self.config.get("interface_language", "de") or "de").strip()
        user_default, assistant_default = default_role_names(lang)
        self.user_display_name.setPlaceholderText(user_default)
        self.assistant_display_name.setPlaceholderText(assistant_default)

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
        data["tts_model"] = self.tts_model.text().strip() or "tts-1-hd"
        data["autoplay_tts"] = self.autoplay.isChecked()
        data["auto_read_assistant_responses"] = self.auto_read_responses.isChecked()
        data["read_all_include_names"] = self.read_all_include_names.isChecked()
        data["user_display_name"] = self.user_display_name.text().strip()
        data["assistant_display_name"] = self.assistant_display_name.text().strip()
        data["tts_lexicon_enabled"] = self.tts_lexicon.isChecked()
        data["windows_sapi_lexicon_enabled"] = data["tts_lexicon_enabled"]
        data["windows_sapi_rate"] = int(self.sapi_rate_slider.value())
        data["windows_sapi_pitch"] = int(self.sapi_pitch_slider.value())
        data["windows_sapi_volume"] = int(self.sapi_volume_slider.value())
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
                manager.start_server(self.log.emit)
                self.finished.emit(True, self.t("tts_setup_start_done", "Startversuch abgeschlossen."))
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
        self.auto_setup_btn = QPushButton(self.t("tts_setup_btn_auto", "Automatisch prüfen & einrichten"))
        self.auto_setup_btn.setObjectName("AccentButton")
        self.auto_setup_btn.clicked.connect(lambda: self.start_action("auto_setup"))
        self.download_voices_btn = QPushButton(self.t("tts_setup_btn_download_voices", "Additional voices …"))
        self.download_voices_btn.clicked.connect(lambda: self.start_action("download_voices"))
        self.start_btn = QPushButton(self.t("tts_setup_btn_start", "Server starten"))
        self.start_btn.clicked.connect(lambda: self.start_action("start"))
        self.stop_btn = QPushButton(self.t("tts_setup_btn_stop", "Server stoppen"))
        self.stop_btn.clicked.connect(lambda: self.start_action("stop"))
        button_row.addWidget(self.auto_setup_btn)
        button_row.addWidget(self.download_voices_btn)
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
            self._set_progress(100, self.t("tts_setup_progress_finalizing", "Abschluss …"))

    def _tick_elapsed(self) -> None:
        self._elapsed_seconds += 1
        self.elapsed_label.setText(self.t("tts_setup_elapsed", "Verstrichen: {seconds} s").format(seconds=self._elapsed_seconds))

    def set_busy(self, busy: bool) -> None:
        for btn in [self.auto_setup_btn, self.download_voices_btn, self.start_btn, self.stop_btn, self.open_folder_btn, self.open_log_btn]:
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
            "auto_setup": self.t("tts_setup_action_auto", "Automatisches Setup"),
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
        self.worker_thread.start()

    def on_action_finished(self, success: bool, message: str) -> None:
        self.append_log(message)
        self.refresh_status()
        self.set_busy(False)
        self.progress_bar.setValue(100 if success else max(self.progress_bar.value(), 1))
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

    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
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
        self.audio_playback_thread: Optional[threading.Thread] = None
        self.last_requested_model = (self.config.get("last_model", "") or "").strip()
        self.pending_auto_answer_source = ""
        self.pending_auto_submit_message: Optional[ChatMessage] = None
        self.auto_answer_waiting_for_user_audio = False

        self.setWindowTitle(self.t("app_title", "OllamaVibeDesk"))
        self.audio_error_signal.connect(self._on_audio_error)
        self.audio_status_signal.connect(self._on_audio_status)
        self.auto_answer_timer = QTimer(self)
        self.auto_answer_timer.setSingleShot(True)
        self.auto_answer_timer.timeout.connect(self._on_auto_answer_timer)
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

    def t(self, key: str, default: Optional[str] = None) -> str:
        return self.translations.get(key, default or key)

    def reload_language_pack(self) -> None:
        self.translations = load_language_pack(self.config.get("interface_language", "de"))

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

        self.sidebar_title = QLabel(self.t("app_title", "OllamaVibeDesk"))
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

        self.status_label = QLabel(self.t("status_checking", "Status: prüfe Ollama …"))
        self.status_label.setObjectName("SubtleLabel")
        layout.addWidget(self.status_label)

        layout.addStretch()

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(280)
        self.model_combo.currentTextChanged.connect(self._model_changed)
        self.model_label = QLabel(self.t("model_label", "Modell"))
        layout.addWidget(self.model_label)
        layout.addWidget(self.model_combo)

        self.refresh_models_btn = QPushButton(self.t("refresh_models", "Modelle neu laden"))
        self.refresh_models_btn.clicked.connect(self.refresh_models)
        layout.addWidget(self.refresh_models_btn)

        self.read_all_btn = QPushButton(self.t("read_all_button", "Alles vorlesen"))
        self.read_all_btn.clicked.connect(self.read_aloud_conversation)
        layout.addWidget(self.read_all_btn)

        self.audio_stop_header_btn = QPushButton(self.t("stop_audio_button", "Audio stoppen"))
        self.audio_stop_header_btn.clicked.connect(self.stop_audio_playback)
        layout.addWidget(self.audio_stop_header_btn)

        self.export_pdf_btn = QPushButton(self.t("export_pdf_button", "Chat exportieren"))
        self.export_pdf_btn.clicked.connect(self.export_current_chat_pdf)
        layout.addWidget(self.export_pdf_btn)

        self.settings_btn = QPushButton(self.t("settings_button", "Einstellungen"))
        self.settings_btn.clicked.connect(self.show_settings)
        layout.addWidget(self.settings_btn)

        return frame

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

        self.auto_answer_checkbox = QCheckBox(self.t("auto_answer_checkbox", "Auto Answer (ELIZA)"))
        self.auto_answer_checkbox.setChecked(bool(self.config.get("auto_answer_enabled", False)))
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
        self.setWindowTitle(self.t("app_title", "OllamaVibeDesk"))
        self.sidebar_title.setText(self.t("app_title", "OllamaVibeDesk"))
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
        self.store.delete(session_id)
        self.current_session = None
        self.refresh_sessions_ui()
        if self.sessions:
            self.open_session(self.sessions[0].session_id)
        else:
            self.create_new_session()

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
        self.scroll_to_bottom()

        for i in range(self.session_list.count()):
            item = self.session_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == session_id:
                self.session_list.setCurrentItem(item)
                break

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
        )
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        return bubble

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
                self.status_label.setText(self.t("status_ollama_ok_no_models", "Status: Ollama erreichbar, aber keine Modelle gefunden."))
            else:
                self.model_combo.addItems(models)
                last_model = self.config.get("last_model", "").strip() or current_text
                if last_model and last_model in models:
                    self.model_combo.setCurrentText(last_model)
                self.status_label.setText(self.t("status_ollama_ok_models", "Status: Ollama erreichbar · {count} Modell(e)").format(count=len(models)))
        except Exception as exc:
            self.status_label.setText(self.t("status_ollama_not_reachable", "Status: Ollama nicht erreichbar · {error}").format(error=exc))
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

    def session_messages_for_api(self) -> List[dict]:
        if not self.current_session:
            return []
        return [
            {"role": item.role, "content": item.content}
            for item in self.current_session.messages
            if item.role in {"user", "assistant"}
        ]

    def _on_input_text_changed(self) -> None:
        if self.input_box.toPlainText().strip() and self.auto_answer_timer.isActive():
            self.auto_answer_timer.stop()
            self.pending_auto_answer_source = ""

    def _on_auto_answer_toggled(self, checked: bool) -> None:
        self.config["auto_answer_enabled"] = bool(checked)
        save_config(self.config)
        if not checked:
            self.auto_answer_timer.stop()
            self.pending_auto_answer_source = ""
            self.pending_auto_submit_message = None
            self.auto_answer_waiting_for_user_audio = False
            self.statusBar().showMessage(self.t("auto_answer_disabled", "Auto Answer deaktiviert."), 2500)
        else:
            self.statusBar().showMessage(self.t("auto_answer_enabled", "Auto Answer aktiviert."), 2500)

    def _append_user_message(self, text: str) -> ChatMessage:
        if not self.current_session:
            self.create_new_session()
        user_message = ChatMessage.now("user", text)
        self.current_session.messages.append(user_message)
        if self.current_session.title == self.t("new_conversation", "Neue Unterhaltung"):
            self.current_session.title = text[:48] + ("…" if len(text) > 48 else "")
        self.current_session.model_name = self.model_combo.currentText().strip()
        self.store.save(self.current_session)
        self.refresh_sessions_ui()
        self.add_message_bubble(user_message)
        self.scroll_to_bottom()
        return user_message

    def _begin_assistant_request(self) -> None:
        selected_model = self.model_combo.currentText().strip()
        previous_model = (self.last_requested_model or "").strip()
        assistant_message = ChatMessage.now("assistant", "")
        self.current_session.messages.append(assistant_message)
        self.current_assistant_bubble = self.add_message_bubble(assistant_message)
        if self.current_assistant_bubble is not None:
            self.current_assistant_bubble.set_loading(True, selected_model, switched_model=bool(previous_model and previous_model != selected_model))
        self.current_assistant_text = ""
        self.last_requested_model = selected_model

        messages = self.session_messages_for_api()[:-1]
        self.start_worker(messages)
        self.stop_btn.setEnabled(True)
        self.scroll_to_bottom()

    def _schedule_auto_answer(self, source_text: str) -> None:
        if not self.auto_answer_checkbox.isChecked():
            return
        if self.worker_thread is not None:
            return
        if self.input_box.toPlainText().strip():
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
        if isinstance(phrase_data, dict) and phrase_data.get("enabled", True) is False:
            return
        auto_text = generate_auto_answer(self.pending_auto_answer_source, self.config.get("interface_language", "de"), phrase_data)
        if not auto_text:
            return
        self.pending_auto_answer_source = ""
        message = self._append_user_message(auto_text)
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
        self._append_user_message(text)
        self._begin_assistant_request()

    def start_worker(self, messages: List[dict]) -> None:
        self.worker_thread = QThread(self)
        self.worker = ChatWorker(
            base_url=self.config.get("ollama_base_url", "http://127.0.0.1:11434").strip(),
            model_name=self.model_combo.currentText().strip(),
            messages=messages,
            system_prompt=self.config.get("system_prompt", ""),
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.chunk.connect(self.on_worker_chunk)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.failed.connect(self.on_worker_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.cleanup_worker)
        self.worker_thread.start()

    def on_worker_chunk(self, text: str) -> None:
        self.current_assistant_text += text
        if self.current_assistant_bubble is not None:
            self.current_assistant_bubble.set_content(self.current_assistant_text)
        self.scroll_to_bottom()

    def on_worker_finished(self) -> None:
        self.stop_btn.setEnabled(False)
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
        auto_read = assistant_message is not None and self.config.get("auto_read_assistant_responses", True) and self.config.get("tts_backend", "disabled") != "disabled"
        if assistant_message is not None and auto_read:
            self.read_aloud_message(assistant_message, show_disabled_message=False, allow_autoplay=True)
        if self.auto_answer_checkbox.isChecked() and not self.input_box.toPlainText().strip():
            if auto_read:
                self.pending_auto_answer_source = final_text
            else:
                self._schedule_auto_answer(final_text)
        self.statusBar().showMessage(self.t("answer_finished", "Antwort abgeschlossen."), 2500)

    def on_worker_failed(self, message: str) -> None:
        self.stop_btn.setEnabled(False)
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
        original_text = message.content.strip()
        text = markdown_to_tts_text(original_text)
        if self.config.get("tts_lexicon_enabled", self.config.get("windows_sapi_lexicon_enabled", True)):
            text = apply_sapi_lexicon(text, load_sapi_lexicon())
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
            windows_sapi_pitch=int(self.config.get("windows_sapi_pitch", 0)),
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
                    if gen_id != self.audio_generation_id:
                        return
                if gen_id == self.audio_generation_id:
                    self._clear_audio_state()
                    self.audio_status_signal.emit(self.t("audio_finished", "Sprachausgabe beendet."))
            except Exception as exc:
                self.current_playback_stoppable = False
                if gen_id == self.audio_generation_id:
                    self._clear_audio_state()
                    self.audio_error_signal.emit(str(exc))

        self.audio_playback_thread = threading.Thread(target=worker_run, args=(generation_id, start_sentence_index), daemon=True)
        self.audio_playback_thread.start()

    def _start_external_segments_playback(self, segments: List[dict], backend: str, primary_message: Optional[ChatMessage] = None) -> None:
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
                for index, segment in enumerate(segments):
                    if gen_id != self.audio_generation_id:
                        return
                    text = str(segment.get("text", "")).strip()
                    if not text:
                        continue
                    voice = str(segment.get("voice", "")).strip()
                    target = AUDIO_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{index:03d}.wav"
                    client = TTSClient(
                        backend=backend,
                        base_url=self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"),
                        voice=voice or self.config.get("tts_voice", "Emma"),
                        model=self.config.get("tts_model", "tts-1-hd"),
                        audio_format='wav',
                        windows_sapi_rate=int(self.config.get("windows_sapi_rate", 0)),
                        windows_sapi_pitch=int(self.config.get("windows_sapi_pitch", 0)),
                        windows_sapi_volume=int(self.config.get("windows_sapi_volume", 100)),
                        windows_sapi_language=self.current_sapi_language_tag(),
                    )
                    path = client.synthesize_to_file(text, target)
                    if gen_id != self.audio_generation_id:
                        return
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
                self.statusBar().showMessage(self.t("vibevoice_autostart_prepare", "Prüfe lokalen VibeVoice-Server …"), 0)
                QApplication.processEvents()
                def _autostart_log(msg: str) -> None:
                    self.statusBar().showMessage(msg, 0)
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
                        windows_sapi_pitch=int(self.config.get("windows_sapi_pitch", 0)),
                        windows_sapi_volume=int(self.config.get("windows_sapi_volume", 100)),
                        windows_sapi_language=self.current_sapi_language_tag(),
                    )
                    for sentence in split_tts_sentences(text):
                        if gen_id != self.audio_generation_id:
                            return
                        self.current_audio_sentence_index = sentence_counter
                        sentence_counter += 1
                        target = AUDIO_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{sentence_counter:03d}.wav"
                        path = client.synthesize_to_file(sentence, target)
                        if gen_id != self.audio_generation_id:
                            return
                        self.current_playback_stoppable = True
                        try:
                            winsound.PlaySound(str(path), winsound.SND_FILENAME)
                        except Exception as play_exc:
                            raise RuntimeError(f'Windows-Audiowiedergabe fehlgeschlagen: {play_exc}')
                        finally:
                            self.current_playback_stoppable = False
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
            rendered = markdown.markdown(message.content if message.role == 'assistant' else html.escape(message.content), extensions=['fenced_code', 'tables'])
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
                self.statusBar().showMessage(self.t("vibevoice_autostart_prepare", "Prüfe lokalen VibeVoice-Server …"), 0)
                QApplication.processEvents()
                def _autostart_log(msg: str) -> None:
                    self.statusBar().showMessage(msg, 0)
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
            if stoppable or had_audio:
                self.statusBar().showMessage(self.t("audio_stopped", "Audio gestoppt."), 2500)
            else:
                self.statusBar().showMessage(self.t("audio_stop_not_available", "Das aktuelle Playback lässt sich nicht direkt stoppen."), 4000)

        if not preserve_state and had_audio:
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
            save_config(self.config)
            self.auto_answer_checkbox.setChecked(bool(self.config.get("auto_answer_enabled", False)))

            lang_changed = old_lang != self.config.get("interface_language", "de")
            theme_changed = old_theme != self.config.get("theme", "Midnight")
            tts_keys = {
                "tts_backend", "tts_base_url", "tts_voice", "tts_model", "tts_format",
                "autoplay_tts", "auto_read_assistant_responses",
                "tts_user_voice", "tts_lexicon_enabled", "windows_sapi_lexicon_enabled", "windows_sapi_rate",
                "windows_sapi_pitch", "windows_sapi_volume", "read_all_include_names",
                "user_display_name", "assistant_display_name"
            }
            tts_changed = any(old_config.get(k) != self.config.get(k) for k in tts_keys)
            restarted_tts = False

            if theme_changed:
                self.apply_theme(self.config.get("theme", "Midnight"))

            if lang_changed:
                self.reload_language_pack()
                self.refresh_ui_texts()

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

            if not restarted_tts:
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
