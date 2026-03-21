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
from datetime import datetime
from time import monotonic
from pathlib import Path
from typing import Callable, List, Optional

import markdown
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, QSize, QUrl, QTimer
from PyQt6.QtGui import QAction, QCursor, QDesktopServices, QFont, QTextOption
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

from app.config import AUDIO_DIR, CHATS_DIR, SAPI_LEXICON_PATH, load_config, save_config, ensure_directories
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

        if is_assistant and self.on_read_aloud is not None:
            speak_btn = QPushButton(self.translate("read_aloud_button", "Vorlesen"))
            speak_btn.clicked.connect(lambda: self.on_read_aloud(self.message))
            actions.addWidget(speak_btn)

        if is_assistant and self.on_stop_audio is not None:
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
        safe_text = text if self.is_assistant else html.escape(text)
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
        self.browser.setHtml(css + html_text)
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
        self.setWindowTitle(self.t("lexicon_editor_title", "Windows-SAPI Aussprache-Lexikon bearbeiten"))
        self.setModal(True)
        self.resize(760, 560)

        layout = QVBoxLayout(self)

        info = QLabel(self.t("lexicon_info", "Die JSON-Datei wird direkt aus dem App-Ordner geladen. Unterstützt werden Einträge vom Typ 'word' und 'phrase'."))
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


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent: Optional[QWidget] = None, open_tts_setup_callback: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.config = config.copy()
        self.translations = load_language_pack(self.config.get("interface_language", "de"))
        self.open_tts_setup_callback = open_tts_setup_callback
        self.setWindowTitle(self.t("settings_title", "Einstellungen"))
        self.setModal(True)
        self.resize(700, 680)

        root = QVBoxLayout(self)

        def add_row(label_text: str, widget: QWidget) -> None:
            row = QVBoxLayout()
            label = QLabel(label_text)
            label.setObjectName("SubtleLabel")
            row.addWidget(label)
            row.addWidget(widget)
            root.addLayout(row)

        self.interface_language = QComboBox()
        for code, display_name in available_languages():
            self.interface_language.addItem(display_name, code)
        current_lang = self.config.get("interface_language", "de")
        idx_lang = max(0, self.interface_language.findData(current_lang))
        self.interface_language.setCurrentIndex(idx_lang)
        add_row(self.t("interface_language_label", "Sprache der Oberfläche"), self.interface_language)

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
        root.addWidget(self.tts_hint)

        self.tts_url = QLineEdit(self.config["tts_base_url"])
        add_row(self.t("tts_base_url_label", "TTS Base URL"), self.tts_url)

        self.tts_voice = QComboBox()
        self.tts_voice.setEditable(True)
        self.tts_voice.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        add_row(self.t("tts_voice_label", "Sprecher / Stimme"), self.tts_voice)

        self.tts_model = QLineEdit(self.config["tts_model"])
        add_row(self.t("tts_model_label", "TTS Modell"), self.tts_model)

        self.autoplay = QCheckBox(self.t("autoplay_label", "Audio nach dem Erzeugen direkt abspielen"))
        self.autoplay.setChecked(bool(self.config.get("autoplay_tts", True)))
        root.addWidget(self.autoplay)

        self.auto_read_responses = QCheckBox(self.t("auto_read_label", "Jede neue Assistent-Antwort automatisch vorlesen"))
        self.auto_read_responses.setChecked(bool(self.config.get("auto_read_assistant_responses", True)))
        self.auto_read_responses.setToolTip(self.t("auto_read_tooltip", "Wenn aktiv, wird nach jeder neuen Assistent-Antwort automatisch TTS erzeugt und abgespielt."))
        root.addWidget(self.auto_read_responses)

        self.sapi_group = QFrame()
        sapi_layout = QVBoxLayout(self.sapi_group)
        sapi_layout.setContentsMargins(0, 8, 0, 0)
        sapi_title = QLabel(self.t("windows_sapi_group_title", "Windows-SAPI Feinabstimmung"))
        sapi_title.setObjectName("SubtleLabel")
        sapi_layout.addWidget(sapi_title)

        self.windows_sapi_lexicon = QCheckBox(self.t("sapi_lexicon_label", "Windows-SAPI Aussprache-Optimierung verwenden"))
        self.windows_sapi_lexicon.setChecked(bool(self.config.get("windows_sapi_lexicon_enabled", False)))
        self.windows_sapi_lexicon.setToolTip(self.t("sapi_lexicon_tooltip", "Wendet vor dem Vorlesen ein lokales JSON-Lexikon auf den bereinigten Text an."))
        sapi_layout.addWidget(self.windows_sapi_lexicon)

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

        sapi_tools_row = QHBoxLayout()
        sapi_tools_row.addStretch()
        self.edit_sapi_lexicon_btn = QPushButton(self.t("edit_lexicon", "Lexikon bearbeiten …"))
        self.edit_sapi_lexicon_btn.clicked.connect(self.edit_sapi_lexicon)
        sapi_tools_row.addWidget(self.edit_sapi_lexicon_btn)
        sapi_layout.addLayout(sapi_tools_row)
        root.addWidget(self.sapi_group)

        self.system_prompt = QPlainTextEdit(self.config.get("system_prompt", ""))
        self.system_prompt.setPlaceholderText(self.t("system_prompt_placeholder", "Optionaler System-Prompt für neue Anfragen"))
        self.system_prompt.setFixedHeight(110)
        add_row(self.t("system_prompt_label", "System-Prompt"), self.system_prompt)

        tts_tools_row = QHBoxLayout()
        tts_tools_row.addStretch()
        self.open_tts_setup_btn = QPushButton(self.t("vibevoice_setup_open", "VibeVoice-Setup öffnen …"))
        self.open_tts_setup_btn.clicked.connect(self.open_tts_setup)
        tts_tools_row.addWidget(self.open_tts_setup_btn)
        root.addLayout(tts_tools_row)

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

    def _current_voice_value(self) -> str:
        idx = self.tts_voice.currentIndex()
        current_text = self.tts_voice.currentText().strip()
        if idx >= 0 and current_text == self.tts_voice.itemText(idx):
            data = self.tts_voice.itemData(idx)
            if isinstance(data, str) and data.strip():
                return data.strip()
        return current_text

    def refresh_tts_voice_options(self) -> None:
        backend = self.current_tts_backend()
        current_voice = self._current_voice_value() or self.config.get("tts_voice", "")
        hint = ""
        default_voice = "Emma"
        voice_entries: list[tuple[str, str]] = []

        if backend == "windows_sapi":
            hint = self.t("tts_hint_windows_sapi", "Verwendet Windows-Desktop-SAPI und zusätzlich erkannte Windows-/OneCore-Stimmen. Kein externer Download nötig.")
            default_voice = ""
        elif backend == "vibevoice_openai":
            hint = self.t("tts_hint_vibevoice", "Benötigt den lokalen VibeVoice-Wrapper.")
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
        self.tts_voice.blockSignals(True)
        self.tts_voice.clear()
        for value, label in voice_entries:
            self.tts_voice.addItem(label, value)
        final_voice = current_voice or self.config.get("tts_voice", default_voice)
        if final_voice:
            selected_index = -1
            for i in range(self.tts_voice.count()):
                item_data = self.tts_voice.itemData(i)
                item_text = self.tts_voice.itemText(i)
                if item_data == final_voice:
                    selected_index = i
                    break
                if backend == "windows_sapi" and not str(final_voice).startswith(("sapi::", "onecore::")):
                    if item_data == TTSClient.make_sapi_voice_id(final_voice) or item_text.startswith(final_voice + " "):
                        selected_index = i
                        break
                if item_text == final_voice:
                    selected_index = i
                    break
            if selected_index >= 0:
                self.tts_voice.setCurrentIndex(selected_index)
            else:
                self.tts_voice.addItem(final_voice, final_voice)
                self.tts_voice.setCurrentText(final_voice)
        self.tts_voice.blockSignals(False)
        sapi_visible = backend == "windows_sapi"
        self.sapi_group.setVisible(sapi_visible)
        self.open_tts_setup_btn.setVisible(backend == "vibevoice_openai")

    def open_tts_setup(self) -> None:
        if self.open_tts_setup_callback is None:
            QMessageBox.information(self, self.t("tts_setup_unavailable_title", "TTS-Setup"), self.t("tts_setup_unavailable_text", "Der TTS-Setup-Assistent ist hier nicht verfügbar."))
            return
        self.open_tts_setup_callback()

    def edit_sapi_lexicon(self) -> None:
        dialog = LexiconEditorDialog(self.config.get("interface_language", "de"), self)
        dialog.exec()

    def get_config(self) -> dict:
        data = self.config.copy()
        data["interface_language"] = (self.interface_language.currentData() or "de").strip()
        data["theme"] = (self.theme_combo.currentText().strip() or "Midnight")
        data["ollama_base_url"] = self.ollama_url.text().strip()
        data["tts_backend"] = self.current_tts_backend()
        data["tts_base_url"] = self.tts_url.text().strip()
        voice_value = self._current_voice_value()
        if data["tts_backend"] == "windows_sapi":
            data["tts_voice"] = voice_value
            data["tts_format"] = "wav"
        else:
            data["tts_voice"] = voice_value or "Emma"
        data["tts_model"] = self.tts_model.text().strip() or "tts-1-hd"
        data["autoplay_tts"] = self.autoplay.isChecked()
        data["auto_read_assistant_responses"] = self.auto_read_responses.isChecked()
        data["windows_sapi_lexicon_enabled"] = self.windows_sapi_lexicon.isChecked()
        data["windows_sapi_rate"] = int(self.sapi_rate_slider.value())
        data["windows_sapi_pitch"] = int(self.sapi_pitch_slider.value())
        data["windows_sapi_volume"] = int(self.sapi_volume_slider.value())
        data["system_prompt"] = self.system_prompt.toPlainText().strip()
        return data


class TTSActionWorker(QObject):
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, base_url: str, action: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.action = action

    def run(self) -> None:
        manager = VibeVoiceManager(self.base_url)
        try:
            if self.action == "auto_setup":
                success, message = manager.auto_setup(self.log.emit)
                self.finished.emit(success, message)
            elif self.action == "install":
                manager.install_or_update(self.log.emit)
                self.finished.emit(True, "VibeVoice-Setup abgeschlossen.")
            elif self.action == "install_ffmpeg":
                manager.install_ffmpeg_via_winget(self.log.emit)
                self.finished.emit(True, "FFmpeg-Installation abgeschlossen oder übersprungen.")
            elif self.action == "start":
                manager.start_server(self.log.emit)
                self.finished.emit(True, "Startversuch abgeschlossen.")
            elif self.action == "stop":
                manager.stop_server(self.log.emit)
                self.finished.emit(True, "Stoppsignal abgeschlossen.")
            else:
                self.finished.emit(False, f"Unbekannte Aktion: {self.action}")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class TTSSetupDialog(QDialog):
    def __init__(self, config: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("TTS-Setup-Assistent")
        self.resize(860, 680)
        self.setModal(True)
        self.config = config
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[TTSActionWorker] = None

        root = QVBoxLayout(self)
        info = QLabel(
            "Dieser Assistent bündelt die automatische VibeVoice-Einrichtung. Er prüft den Status, "
            "überspringt FFmpeg, wenn es bereits vorhanden ist, lädt den Wrapper herunter und richtet "
            "ihn soweit möglich ein. Wichtig: Der eigentliche Modelldownload beginnt erst, wenn der "
            "Wrapper erfolgreich laufen kann. Laut Wrapper-README braucht dieser Weg Python 3.13, "
            "ffmpeg und beim ersten echten Start zusätzlich etwa 2 GB Modelle und ~22 MB Stimmen. "
            "Für einen sofort nutzbaren Offline-Fallback gibt es in den Einstellungen auch 'windows_sapi' "
            "mit integrierten Windows-Stimmen."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        self.status_label = QLabel()
        self.status_label.setObjectName("SubtleLabel")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        button_row = QHBoxLayout()
        self.auto_setup_btn = QPushButton("Automatisch prüfen & einrichten")
        self.auto_setup_btn.setObjectName("AccentButton")
        self.auto_setup_btn.clicked.connect(lambda: self.start_action("auto_setup"))
        self.start_btn = QPushButton("Server starten")
        self.start_btn.clicked.connect(lambda: self.start_action("start"))
        self.stop_btn = QPushButton("Server stoppen")
        self.stop_btn.clicked.connect(lambda: self.start_action("stop"))
        button_row.addWidget(self.auto_setup_btn)
        button_row.addWidget(self.start_btn)
        button_row.addWidget(self.stop_btn)
        root.addLayout(button_row)

        path_row = QHBoxLayout()
        self.open_folder_btn = QPushButton("TTS-Ordner öffnen")
        self.open_folder_btn.clicked.connect(self.open_tts_folder)
        self.open_log_btn = QPushButton("Log öffnen")
        self.open_log_btn.clicked.connect(self.open_log_file)
        path_row.addWidget(self.open_folder_btn)
        path_row.addWidget(self.open_log_btn)
        path_row.addStretch()
        root.addLayout(path_row)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("Hier erscheinen Status- und Setup-Meldungen …")
        root.addWidget(self.log_box, 1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Schließen")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

        self.refresh_status()

    def manager(self) -> VibeVoiceManager:
        return VibeVoiceManager(self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"))

    def append_log(self, text: str) -> None:
        self.log_box.appendPlainText(text)
        bar = self.log_box.verticalScrollBar()
        bar.setValue(bar.maximum())

    def refresh_status(self) -> None:
        status = self.manager().status()
        lines = [
            f"Backend-URL: {status.base_url}",
            f"Health: {'OK' if status.health_ok else 'nicht erreichbar'}",
            f"ffmpeg in PATH: {'ja' if status.ffmpeg_found else 'nein'}",
            f"Wrapper-Dateien vorhanden: {'ja' if status.repo_present else 'nein'}",
            f"Wrapper-venv vorhanden: {'ja' if status.venv_present else 'nein'}",
            f"PID-Datei/Prozess aktiv: {'ja' if status.pid_running else 'nein'}",
            f"Repo-Ordner: {status.repo_dir}",
            f"Modelle-Ordner: {status.models_dir}",
            f"Logdatei: {status.log_path}",
        ]
        if status.health_ok:
            lines.append(f"Health-Antwort: {status.health_message}")
        else:
            lines.append(f"Letzter Health-Fehler: {status.health_message}")
        self.status_label.setText("\n".join(lines))

    def set_busy(self, busy: bool) -> None:
        for btn in [self.auto_setup_btn, self.start_btn, self.stop_btn, self.open_folder_btn, self.open_log_btn]:
            btn.setEnabled(not busy)

    def start_action(self, action: str) -> None:
        if self.worker_thread is not None:
            QMessageBox.information(self, "Bitte warten", "Es läuft bereits eine TTS-Setup-Aktion.")
            return
        self.append_log("")
        self.append_log(f"=== Aktion: {action} ===")
        self.set_busy(True)

        self.worker_thread = QThread(self)
        self.worker = TTSActionWorker(self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"), action)
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
        if success:
            self.parent().statusBar().showMessage(message, 4000) if self.parent() and hasattr(self.parent(), 'statusBar') else None
        else:
            self.parent().statusBar().showMessage(message, 6000) if self.parent() and hasattr(self.parent(), 'statusBar') else None
            QMessageBox.information(self, "TTS-Setup", message)

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
            QMessageBox.information(self, "Noch kein Log", "Die Logdatei existiert noch nicht. Starte den Server einmal, dann wird sie angelegt.")


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

        self.setWindowTitle(self.t("app_title", "OllamaVibeDesk"))
        self.audio_error_signal.connect(self._on_audio_error)
        self.audio_status_signal.connect(self._on_audio_status)
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
        layout.addWidget(self.input_box)

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
        self.settings_btn.setText(self.t("settings_button", "Einstellungen"))
        self.input_box.setPlaceholderText(self.t("composer_placeholder", "Nachricht schreiben …  (Strg+Enter zum Senden)"))
        self.composer_hint.setText(self.t("composer_hint", "Ollama wird lokal angesprochen. Antworten werden gestreamt."))
        self.stop_btn.setText(self.t("stop_button", "Stop"))
        self.send_btn.setText(self.t("send_button", "Senden"))
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
            on_read_aloud=self.read_aloud_message if message.role == "assistant" else None,
            on_stop_audio=self.stop_audio_playback if message.role == "assistant" else None,
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

    def send_message(self) -> None:
        text = self.input_box.toPlainText().strip()
        if not text:
            return
        if self.worker_thread is not None:
            QMessageBox.warning(self, self.t("already_running_title", "Läuft bereits"), self.t("already_running_message", "Es läuft bereits eine Antwortgenerierung."))
            return
        if not self.current_session:
            self.create_new_session()

        user_message = ChatMessage.now("user", text)
        self.current_session.messages.append(user_message)
        self.input_box.clear()

        if self.current_session.title == self.t("new_conversation", "Neue Unterhaltung"):
            self.current_session.title = text[:48] + ("…" if len(text) > 48 else "")
        self.current_session.model_name = self.model_combo.currentText().strip()
        self.store.save(self.current_session)
        self.refresh_sessions_ui()

        self.add_message_bubble(user_message)

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
        if assistant_message is not None and self.config.get("auto_read_assistant_responses", True):
            self.read_aloud_message(assistant_message, show_disabled_message=False, allow_autoplay=True)
        self.statusBar().showMessage(self.t("answer_finished", "Antwort abgeschlossen."), 2500)

    def on_worker_failed(self, message: str) -> None:
        self.stop_btn.setEnabled(False)
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
        backend = self.config.get("tts_backend", "disabled")
        original_text = message.content.strip()
        text = markdown_to_tts_text(original_text)
        if backend == "windows_sapi" and self.config.get("windows_sapi_lexicon_enabled", False):
            text = apply_sapi_lexicon(text, load_sapi_lexicon())
        return text.strip()

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
            voice=self.config.get("tts_voice", ""),
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

    def _on_audio_error(self, message: str) -> None:
        self.statusBar().showMessage(self.t("audio_failed", "Sprachausgabe fehlgeschlagen.") + f" {message}", 7000)
        QMessageBox.warning(
            self,
            self.t("tts_error_title", "TTS-Fehler"),
            self.t("tts_error_message", "Die Sprachausgabe ist fehlgeschlagen:") + f"\n\n{message}",
        )

    def _on_audio_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 3000)

    def current_sapi_language_tag(self) -> str:
        code = (self.config.get("interface_language", "de") or "de").lower()
        if code.startswith("en"):
            return "en-US"
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

        if backend == "windows_sapi":
            self.stop_audio_playback(silent=True)
            self.statusBar().showMessage(self.t("audio_preparing", "Sprachausgabe wird vorbereitet …"), 2500)
            self._start_windows_sapi_sentence_playback(message, start_sentence_index=0)
            self.statusBar().showMessage(self.t("audio_playback_started", "Sprachausgabe gestartet."), 2500)
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = AUDIO_DIR / f"{timestamp}_{uuid.uuid4().hex[:8]}.{self.config.get('tts_format', 'wav')}"
        client = TTSClient(
            backend=backend,
            base_url=self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"),
            voice=self.config.get("tts_voice", "Emma"),
            model=self.config.get("tts_model", "tts-1-hd"),
            audio_format=self.config.get("tts_format", "wav"),
            windows_sapi_rate=int(self.config.get("windows_sapi_rate", 0)),
            windows_sapi_pitch=int(self.config.get("windows_sapi_pitch", 0)),
            windows_sapi_volume=int(self.config.get("windows_sapi_volume", 100)),
            windows_sapi_language=self.current_sapi_language_tag(),
        )

        try:
            path = client.synthesize_to_file(text, target)
            message.audio_path = str(path)
            if self.current_session:
                self.store.save(self.current_session)
            self.statusBar().showMessage(self.t("audio_saved", "Audio gespeichert: {name}").format(name=path.name), 5000)

            self.current_audio_message = message
            self.current_audio_backend = backend
            if allow_autoplay and self.config.get("autoplay_tts", True) and path.suffix.lower() == ".wav":
                self.try_play_wav(path)
        except Exception as exc:
            QMessageBox.critical(self, "TTS-Fehler", f"Die Audioerzeugung ist fehlgeschlagen:\n\n{exc}")

    def stop_audio_playback(self, silent: bool = False, preserve_state: bool = False) -> None:
        stoppable = False
        had_audio = self.current_audio_message is not None
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

            lang_changed = old_lang != self.config.get("interface_language", "de")
            theme_changed = old_theme != self.config.get("theme", "Midnight")
            tts_keys = {
                "tts_backend", "tts_base_url", "tts_voice", "tts_model", "tts_format",
                "autoplay_tts", "auto_read_assistant_responses",
                "windows_sapi_lexicon_enabled", "windows_sapi_rate",
                "windows_sapi_pitch", "windows_sapi_volume"
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
