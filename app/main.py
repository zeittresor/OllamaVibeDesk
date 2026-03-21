from __future__ import annotations

import html
import re
import os
import json
import subprocess
import sys
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

import markdown
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, QSize, QUrl
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
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
        on_copy: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.message = message
        self.is_assistant = is_assistant
        self.on_read_aloud = on_read_aloud
        self.on_copy = on_copy
        self.setObjectName("BubbleWidget")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        align_container = QWidget()
        align_layout = QVBoxLayout(align_container)
        align_layout.setContentsMargins(0, 0, 0, 0)
        align_layout.setSpacing(6)

        self.card = QFrame()
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        meta = QLabel(
            ("Assistent" if is_assistant else "Du") + " · " + pretty_timestamp(message.created_at)
        )
        meta.setObjectName("SubtleLabel")
        card_layout.addWidget(meta)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFrameShape(QFrame.Shape.NoFrame)
        self.browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self.browser.document().setDocumentMargin(0)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        self.browser.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.browser.setMinimumHeight(56)
        self.set_content(message.content)
        card_layout.addWidget(self.browser)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch()

        if self.on_copy is not None:
            copy_btn = QPushButton("Kopieren")
            copy_btn.clicked.connect(lambda: self.on_copy(self.message.content))
            actions.addWidget(copy_btn)

        if is_assistant and self.on_read_aloud is not None:
            speak_btn = QPushButton("Vorlesen")
            speak_btn.clicked.connect(lambda: self.on_read_aloud(self.message))
            actions.addWidget(speak_btn)

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
            outer.addSpacing(42)
            align_layout.addWidget(self.card)
            outer.addWidget(align_container)
            outer.addStretch()
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
            outer.addStretch()
            align_layout.addWidget(self.card)
            outer.addWidget(align_container)
            outer.addSpacing(42)

    def set_content(self, text: str) -> None:
        self.message.content = text
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
        doc = self.browser.document()
        target_height = int(doc.size().height()) + 16
        self.browser.setMinimumHeight(max(56, target_height))
        self.browser.setMaximumHeight(max(120, target_height + 8))


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
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Windows-SAPI Aussprache-Lexikon bearbeiten")
        self.setModal(True)
        self.resize(760, 560)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Die JSON-Datei wird direkt aus dem App-Ordner geladen. "
            "Unterstützt werden Einträge vom Typ 'word' und 'phrase'."
        )
        info.setWordWrap(True)
        info.setObjectName("SubtleLabel")
        layout.addWidget(info)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText('{\n  "enabled": true,\n  "language": "de-DE",\n  "entries": []\n}')
        layout.addWidget(self.editor, 1)

        buttons = QHBoxLayout()
        self.reset_btn = QPushButton("Standard wiederherstellen")
        self.reset_btn.clicked.connect(self.reset_to_default)
        buttons.addWidget(self.reset_btn)
        buttons.addStretch()

        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Speichern")
        save_btn.setObjectName("AccentButton")
        save_btn.clicked.connect(self.save_and_accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

        self.load_current()

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
            "Standard wiederherstellen",
            "Soll das Aussprache-Lexikon auf die Standardwerte zurückgesetzt werden?",
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
            QMessageBox.warning(self, "Leeres Lexikon", "Die JSON-Datei darf nicht leer sein.")
            return
        try:
            data = json.loads(raw)
        except Exception as exc:
            QMessageBox.critical(self, "Ungültiges JSON", f"Die Datei ist kein gültiges JSON.\n\n{exc}")
            return
        if not isinstance(data, dict):
            QMessageBox.critical(self, "Ungültiges Format", "Die oberste Ebene der Datei muss ein JSON-Objekt sein.")
            return
        if "entries" in data and not isinstance(data.get("entries"), list):
            QMessageBox.critical(self, "Ungültiges Format", "'entries' muss eine Liste sein.")
            return
        ensure_directories()
        SAPI_LEXICON_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent: Optional[QWidget] = None, open_tts_setup_callback: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setModal(True)
        self.resize(680, 520)
        self.config = config.copy()
        self.open_tts_setup_callback = open_tts_setup_callback

        root = QVBoxLayout(self)

        def add_row(label_text: str, widget: QWidget) -> None:
            row = QVBoxLayout()
            label = QLabel(label_text)
            label.setObjectName("SubtleLabel")
            row.addWidget(label)
            row.addWidget(widget)
            root.addLayout(row)

        self.ollama_url = QLineEdit(self.config["ollama_base_url"])
        add_row("Ollama Base URL", self.ollama_url)

        self.tts_backend = QComboBox()
        self.tts_backend.addItem("disabled", "disabled")
        self.tts_backend.addItem("windows_sapi (integrierte Windows-Stimmen)", "windows_sapi")
        self.tts_backend.addItem("vibevoice_openai (lokaler Wrapper)", "vibevoice_openai")
        backend_value = self.config.get("tts_backend", "disabled")
        backend_index = max(0, self.tts_backend.findData(backend_value))
        self.tts_backend.setCurrentIndex(backend_index)
        add_row("TTS Backend", self.tts_backend)

        self.tts_hint = QLabel()
        self.tts_hint.setObjectName("SubtleLabel")
        self.tts_hint.setWordWrap(True)
        root.addWidget(self.tts_hint)

        self.tts_url = QLineEdit(self.config["tts_base_url"])
        add_row("TTS Base URL", self.tts_url)

        self.tts_voice = QComboBox()
        self.tts_voice.setEditable(True)
        self.tts_voice.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        add_row("TTS Stimme", self.tts_voice)

        self.tts_model = QLineEdit(self.config["tts_model"])
        add_row("TTS Modell", self.tts_model)

        self.autoplay = QCheckBox("Audio nach dem Erzeugen direkt abspielen")
        self.autoplay.setChecked(bool(self.config.get("autoplay_tts", True)))
        root.addWidget(self.autoplay)

        self.auto_read_responses = QCheckBox("Jede neue Assistent-Antwort automatisch vorlesen")
        self.auto_read_responses.setChecked(bool(self.config.get("auto_read_assistant_responses", True)))
        self.auto_read_responses.setToolTip("Wenn aktiv, wird nach jeder neuen Assistent-Antwort automatisch TTS erzeugt und abgespielt.")
        root.addWidget(self.auto_read_responses)

        self.windows_sapi_lexicon = QCheckBox("Windows-SAPI Aussprache-Optimierung verwenden")
        self.windows_sapi_lexicon.setChecked(bool(self.config.get("windows_sapi_lexicon_enabled", False)))
        self.windows_sapi_lexicon.setToolTip("Wendet vor dem Vorlesen ein lokales JSON-Lexikon auf den bereinigten Text an.")
        root.addWidget(self.windows_sapi_lexicon)

        sapi_tools_row = QHBoxLayout()
        sapi_tools_row.addStretch()
        self.edit_sapi_lexicon_btn = QPushButton("Lexikon bearbeiten …")
        self.edit_sapi_lexicon_btn.clicked.connect(self.edit_sapi_lexicon)
        sapi_tools_row.addWidget(self.edit_sapi_lexicon_btn)
        root.addLayout(sapi_tools_row)

        self.system_prompt = QPlainTextEdit(self.config.get("system_prompt", ""))
        self.system_prompt.setPlaceholderText("Optionaler System-Prompt für neue Anfragen")
        self.system_prompt.setFixedHeight(110)
        add_row("System-Prompt", self.system_prompt)

        tts_tools_row = QHBoxLayout()
        tts_tools_row.addStretch()
        self.open_tts_setup_btn = QPushButton("VibeVoice-Setup öffnen …")
        self.open_tts_setup_btn.clicked.connect(self.open_tts_setup)
        tts_tools_row.addWidget(self.open_tts_setup_btn)
        root.addLayout(tts_tools_row)

        self.tts_backend.currentIndexChanged.connect(self.refresh_tts_voice_options)
        self.refresh_tts_voice_options()

        buttons = QHBoxLayout()
        buttons.addStretch()
        save_btn = QPushButton("Speichern")
        save_btn.setObjectName("AccentButton")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        root.addLayout(buttons)

    def current_tts_backend(self) -> str:
        return (self.tts_backend.currentData() or self.tts_backend.currentText() or "disabled").strip()

    def refresh_tts_voice_options(self) -> None:
        backend = self.current_tts_backend()
        current_voice = self.tts_voice.currentText().strip() or self.config.get("tts_voice", "")
        hint = ""
        default_voice = "Emma"
        voices: list[str] = []

        if backend == "windows_sapi":
            hint = "Verwendet die in Windows installierten Systemstimmen. Kein externer Download nötig. Optional kann ein lokales Aussprache-Lexikon vor dem Vorlesen angewendet werden."
            default_voice = ""
        elif backend == "vibevoice_openai":
            hint = "Benötigt den lokalen VibeVoice-Wrapper. Laut Wrapper-README: Python 3.13, ffmpeg und beim ersten Start zusätzlicher Modelldownload."
            default_voice = "Emma"
        else:
            hint = "TTS ist deaktiviert."

        try:
            client = TTSClient(
                backend=backend,
                base_url=self.tts_url.text().strip() or self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"),
                voice=current_voice or self.config.get("tts_voice", default_voice),
                model=self.tts_model.text().strip() or self.config.get("tts_model", "tts-1-hd"),
                audio_format=self.config.get("tts_format", "wav"),
            )
            voices = client.list_voices()
        except Exception as exc:
            if backend == "windows_sapi":
                hint += f" Stimmen konnten gerade nicht gelesen werden: {exc}"
            elif backend == "vibevoice_openai":
                hint += " Der Wrapper scheint aktuell nicht zu laufen oder ist noch nicht eingerichtet."

        self.tts_hint.setText(hint)
        self.tts_voice.blockSignals(True)
        self.tts_voice.clear()
        for voice in voices:
            self.tts_voice.addItem(voice)
        final_voice = current_voice or self.config.get("tts_voice", default_voice)
        if final_voice:
            if self.tts_voice.findText(final_voice) == -1:
                self.tts_voice.addItem(final_voice)
            self.tts_voice.setCurrentText(final_voice)
        self.tts_voice.blockSignals(False)
        if hasattr(self, "open_tts_setup_btn"):
            self.open_tts_setup_btn.setVisible(backend == "vibevoice_openai")
        if hasattr(self, "windows_sapi_lexicon"):
            sapi_visible = backend == "windows_sapi"
            self.windows_sapi_lexicon.setVisible(sapi_visible)
            self.edit_sapi_lexicon_btn.setVisible(sapi_visible)

    def open_tts_setup(self) -> None:
        if self.open_tts_setup_callback is None:
            QMessageBox.information(self, "TTS-Setup", "Der TTS-Setup-Assistent ist hier nicht verfügbar.")
            return
        self.open_tts_setup_callback()

    def edit_sapi_lexicon(self) -> None:
        dialog = LexiconEditorDialog(self)
        dialog.exec()

    def get_config(self) -> dict:
        data = self.config.copy()
        data["ollama_base_url"] = self.ollama_url.text().strip()
        data["tts_backend"] = self.current_tts_backend()
        data["tts_base_url"] = self.tts_url.text().strip()
        voice_value = self.tts_voice.currentText().strip()
        if data["tts_backend"] == "windows_sapi":
            data["tts_voice"] = voice_value
            data["tts_format"] = "wav"
        else:
            data["tts_voice"] = voice_value or "Emma"
        data["tts_model"] = self.tts_model.text().strip() or "tts-1-hd"
        data["autoplay_tts"] = self.autoplay.isChecked()
        data["auto_read_assistant_responses"] = self.auto_read_responses.isChecked()
        data["windows_sapi_lexicon_enabled"] = self.windows_sapi_lexicon.isChecked()
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
    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.store = SessionStore()
        self.sessions = self.store.list_sessions()
        self.current_session: Optional[ChatSession] = None
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[ChatWorker] = None
        self.current_assistant_bubble: Optional[BubbleWidget] = None
        self.current_assistant_text = ""

        self.setWindowTitle("OllamaVibeDesk")
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

        title = QLabel("OllamaVibeDesk")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        subtitle = QLabel("Lokale Chats · portable Daten · optionale WAV-Ausgabe")
        subtitle.setObjectName("SubtleLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        buttons = QHBoxLayout()
        new_btn = QPushButton("Neuer Chat")
        new_btn.setObjectName("AccentButton")
        new_btn.clicked.connect(self.create_new_session)
        del_btn = QPushButton("Löschen")
        del_btn.setObjectName("DangerButton")
        del_btn.clicked.connect(self.delete_current_session)
        buttons.addWidget(new_btn)
        buttons.addWidget(del_btn)
        layout.addLayout(buttons)

        self.session_list = QListWidget()
        self.session_list.itemClicked.connect(self._on_session_clicked)
        layout.addWidget(self.session_list, 1)

        hint = QLabel(
            "Rechtsklick im Chat auf Antwortblasen ist nicht nötig — jede Assistent-Antwort hat direkt Aktionen."
        )
        hint.setWordWrap(True)
        hint.setObjectName("SubtleLabel")
        layout.addWidget(hint)

        return frame

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("HeaderBar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)

        self.status_label = QLabel("Status: prüfe Ollama …")
        self.status_label.setObjectName("SubtleLabel")
        layout.addWidget(self.status_label)

        layout.addStretch()

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(280)
        self.model_combo.currentTextChanged.connect(self._model_changed)
        layout.addWidget(QLabel("Modell"))
        layout.addWidget(self.model_combo)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(sorted(THEMES.keys()))
        self.theme_combo.setCurrentText(self.config.get("theme", "Midnight"))
        self.theme_combo.currentTextChanged.connect(self.apply_theme)
        layout.addWidget(QLabel("Theme"))
        layout.addWidget(self.theme_combo)

        refresh_btn = QPushButton("Modelle neu laden")
        refresh_btn.clicked.connect(self.refresh_models)
        layout.addWidget(refresh_btn)

        settings_btn = QPushButton("Einstellungen")
        settings_btn.clicked.connect(self.show_settings)
        layout.addWidget(settings_btn)

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
        self.input_box.setPlaceholderText("Nachricht schreiben …  (Strg+Enter zum Senden)")
        self.input_box.setFixedHeight(120)
        layout.addWidget(self.input_box)

        buttons = QHBoxLayout()
        left_hint = QLabel("Ollama wird lokal angesprochen. Antworten werden gestreamt.")
        left_hint.setObjectName("SubtleLabel")
        buttons.addWidget(left_hint)
        buttons.addStretch()

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_generation)
        self.stop_btn.setEnabled(False)

        send_btn = QPushButton("Senden")
        send_btn.setObjectName("AccentButton")
        send_btn.clicked.connect(self.send_message)

        buttons.addWidget(self.stop_btn)
        buttons.addWidget(send_btn)
        layout.addLayout(buttons)

        return frame

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
            title="Neue Unterhaltung",
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
            "Chat löschen",
            f"Soll \"{self.current_session.title}\" wirklich gelöscht werden?",
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
            is_assistant=(message.role == "assistant"),
            on_read_aloud=self.read_aloud_message,
            on_copy=self.copy_text,
        )
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        return bubble

    def copy_text(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Text in die Zwischenablage kopiert.", 2500)

    def refresh_models(self) -> None:
        base_url = self.config.get("ollama_base_url", "http://127.0.0.1:11434").strip()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        try:
            client = OllamaClient(base_url)
            models = client.get_models()
            if not models:
                self.status_label.setText("Status: Ollama erreichbar, aber keine Modelle gefunden.")
            else:
                self.model_combo.addItems(models)
                last_model = self.config.get("last_model", "").strip()
                if last_model and last_model in models:
                    self.model_combo.setCurrentText(last_model)
                self.status_label.setText(f"Status: Ollama erreichbar · {len(models)} Modell(e)")
        except Exception as exc:
            self.status_label.setText(f"Status: Ollama nicht erreichbar · {exc}")
        finally:
            self.model_combo.blockSignals(False)

    def _model_changed(self, model_name: str) -> None:
        self.config["last_model"] = model_name.strip()
        save_config(self.config)
        if self.current_session is not None:
            self.current_session.model_name = model_name.strip()
            self.store.save(self.current_session)
            self.refresh_sessions_ui()

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
            QMessageBox.warning(self, "Läuft bereits", "Es läuft bereits eine Antwortgenerierung.")
            return
        if not self.current_session:
            self.create_new_session()

        user_message = ChatMessage.now("user", text)
        self.current_session.messages.append(user_message)
        self.input_box.clear()

        if self.current_session.title == "Neue Unterhaltung":
            self.current_session.title = text[:48] + ("…" if len(text) > 48 else "")
        self.current_session.model_name = self.model_combo.currentText().strip()
        self.store.save(self.current_session)
        self.refresh_sessions_ui()

        self.add_message_bubble(user_message)

        assistant_message = ChatMessage.now("assistant", "")
        self.current_session.messages.append(assistant_message)
        self.current_assistant_bubble = self.add_message_bubble(assistant_message)
        self.current_assistant_text = ""

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
        self.statusBar().showMessage('Antwort abgeschlossen.', 2500)

    def on_worker_failed(self, message: str) -> None:
        self.stop_btn.setEnabled(False)
        if self.current_assistant_bubble is not None:
            error_text = f"Fehler bei der Ollama-Anfrage:\n\n{message}"
            self.current_assistant_bubble.set_content(error_text)
        if self.current_session and self.current_session.messages:
            self.current_session.messages[-1].content = f"Fehler bei der Ollama-Anfrage:\n\n{message}"
            self.store.save(self.current_session)
        self.statusBar().showMessage("Ollama-Anfrage fehlgeschlagen.", 4000)

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
            self.statusBar().showMessage("Abbruch angefordert …", 2000)
        self.stop_btn.setEnabled(False)

    def scroll_to_bottom(self) -> None:
        bar = self.chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def read_aloud_message(self, message: ChatMessage, show_disabled_message: bool = True, allow_autoplay: bool = True) -> None:
        backend = self.config.get("tts_backend", "disabled")
        if backend == "disabled":
            if show_disabled_message:
                QMessageBox.information(
                    self,
                    "TTS deaktiviert",
                    "TTS ist deaktiviert. Aktiviere in den Einstellungen z. B. 'windows_sapi' oder 'vibevoice_openai'.",
                )
            return

        original_text = message.content.strip()
        text = markdown_to_tts_text(original_text)
        if backend == "windows_sapi" and self.config.get("windows_sapi_lexicon_enabled", False):
            text = apply_sapi_lexicon(text, load_sapi_lexicon())
        if not text:
            QMessageBox.information(self, "Leere Nachricht", "Diese Nachricht enthält keinen vorlesbaren Text.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = AUDIO_DIR / f"{timestamp}_{uuid.uuid4().hex[:8]}.{self.config.get('tts_format', 'wav')}"
        client = TTSClient(
            backend=backend,
            base_url=self.config.get("tts_base_url", "http://127.0.0.1:8880/v1"),
            voice=self.config.get("tts_voice", "Emma"),
            model=self.config.get("tts_model", "tts-1-hd"),
            audio_format=self.config.get("tts_format", "wav"),
        )

        try:
            path = client.synthesize_to_file(text, target)
            message.audio_path = str(path)
            if self.current_session:
                self.store.save(self.current_session)
            self.statusBar().showMessage(f"Audio gespeichert: {path.name}", 5000)

            if allow_autoplay and self.config.get("autoplay_tts", True) and path.suffix.lower() == ".wav":
                self.try_play_wav(path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "TTS-Fehler",
                f"Die Audioerzeugung ist fehlgeschlagen:\n\n{exc}",
            )

    def try_play_wav(self, path: Path) -> None:
        try:
            if sys.platform.startswith('win'):
                import winsound
                try:
                    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                except Exception:
                    os.startfile(str(path))
            else:
                self.statusBar().showMessage(
                    f'Audio gespeichert unter {path}. Automatisches Abspielen ist hier nicht implementiert.',
                    6000,
                )
        except Exception as exc:
            self.statusBar().showMessage(f'Audio wurde gespeichert, Playback schlug fehl: {exc}', 6000)

    def show_settings(self) -> None:
        dialog = SettingsDialog(self.config, self, self.show_tts_setup)
        if dialog.exec():
            self.config = dialog.get_config()
            save_config(self.config)
            self.apply_theme(self.config.get("theme", self.theme_combo.currentText()))
            self.refresh_models()
            self.statusBar().showMessage("Einstellungen gespeichert.", 2500)

    def show_tts_setup(self) -> None:
        dialog = TTSSetupDialog(self.config, self)
        dialog.exec()

    def closeEvent(self, event) -> None:
        if self.worker is not None:
            self.worker.cancel()
        if self.current_session is not None:
            self.store.save(self.current_session)
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