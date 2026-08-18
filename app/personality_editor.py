from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config import PERSONALITIES_ASSISTANT_DIR, PERSONALITIES_USER_DIR
from app.personalities import (
    DEFAULT_PARAMETERS,
    Personality,
    delete_custom_personality,
    load_personalities,
    load_personality,
    localized_text,
    personality_origin,
    safe_personality_id,
    save_custom_personality,
)


class PersonalityEditorDialog(QDialog):
    """Editor for built-in presets, user overrides, and additional JSON personalities."""

    def __init__(
        self,
        language_code: str,
        t: Callable[[str, str], str],
        initial_role: str = "user",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.language_code = (language_code or "en").strip().lower()
        self.t = t
        self.current_personality: Optional[Personality] = None
        self.current_is_new = False
        self.changed = False

        self.setWindowTitle(self.t("personality_editor_title", "Character / personality editor"))
        self.resize(1120, 760)
        self.setMinimumSize(920, 650)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top = QHBoxLayout()
        top.addWidget(QLabel(self.t("personality_editor_role", "Role")))
        self.role_combo = QComboBox()
        self.role_combo.addItem(self.t("personality_role_user", "User / Auto-Answer speaker"), "user")
        self.role_combo.addItem(self.t("personality_role_assistant", "Responding LLM"), "assistant")
        role_index = self.role_combo.findData(initial_role if initial_role in {"user", "assistant"} else "user")
        self.role_combo.setCurrentIndex(max(0, role_index))
        self.role_combo.currentIndexChanged.connect(self.reload_list)
        top.addWidget(self.role_combo)
        self.origin_label = QLabel()
        self.origin_label.setObjectName("SubtleLabel")
        top.addWidget(self.origin_label, 1)
        self.open_folder_btn = QPushButton(self.t("personality_editor_open_folder", "Open custom folder"))
        self.open_folder_btn.clicked.connect(self.open_custom_folder)
        top.addWidget(self.open_folder_btn)
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(12)

        left = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self.load_selected)
        left.addWidget(self.list_widget, 1)
        list_buttons = QGridLayout()
        self.new_btn = QPushButton(self.t("personality_editor_new", "New"))
        self.new_btn.clicked.connect(self.new_personality)
        self.duplicate_btn = QPushButton(self.t("personality_editor_duplicate", "Duplicate"))
        self.duplicate_btn.clicked.connect(self.duplicate_personality)
        self.import_btn = QPushButton(self.t("personality_editor_import", "Import JSON …"))
        self.import_btn.clicked.connect(self.import_json)
        self.export_btn = QPushButton(self.t("personality_editor_export", "Export JSON …"))
        self.export_btn.clicked.connect(self.export_json)
        list_buttons.addWidget(self.new_btn, 0, 0)
        list_buttons.addWidget(self.duplicate_btn, 0, 1)
        list_buttons.addWidget(self.import_btn, 1, 0)
        list_buttons.addWidget(self.export_btn, 1, 1)
        left.addLayout(list_buttons)
        body.addLayout(left, 1)

        editor_widget = QWidget()
        editor = QVBoxLayout(editor_widget)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setSpacing(8)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("my_personality")
        form.addRow(self.t("personality_editor_id", "File ID"), self.id_edit)
        self.name_edit = QLineEdit()
        form.addRow(self.t("personality_editor_name", "Display name"), self.name_edit)
        self.gender_combo = QComboBox()
        self.gender_combo.addItem(self.t("personality_gender_female", "Female"), "female")
        self.gender_combo.addItem(self.t("personality_gender_male", "Male"), "male")
        self.gender_combo.addItem(self.t("personality_gender_neutral", "Neutral"), "neutral")
        form.addRow(self.t("personality_editor_gender", "Gender / presentation"), self.gender_combo)
        self.tone_edit = QLineEdit()
        self.tone_edit.setPlaceholderText(self.t("personality_editor_tone_placeholder", "e.g. analytical and warm"))
        form.addRow(self.t("personality_editor_tone", "Tone"), self.tone_edit)
        editor.addLayout(form)

        editor.addWidget(QLabel(self.t("personality_editor_description", "Description")))
        self.description_edit = QPlainTextEdit()
        self.description_edit.setMaximumHeight(85)
        editor.addWidget(self.description_edit)

        parameters_label = QLabel(self.t("personality_editor_parameters", "Character parameters (0–100)"))
        parameters_label.setObjectName("SubtleLabel")
        editor.addWidget(parameters_label)
        parameters_grid = QGridLayout()
        self.parameter_spins: dict[str, QSpinBox] = {}
        parameter_keys = (
            ("formality", "personality_parameter_formality", "Formality"),
            ("verbosity", "personality_parameter_verbosity", "Verbosity"),
            ("empathy", "personality_parameter_empathy", "Empathy"),
            ("humor", "personality_parameter_humor", "Humor"),
            ("assertiveness", "personality_parameter_assertiveness", "Assertiveness"),
            ("curiosity", "personality_parameter_curiosity", "Curiosity"),
            ("creativity", "personality_parameter_creativity", "Creativity"),
        )
        for index, (key, translation_key, default_label) in enumerate(parameter_keys):
            row, col = divmod(index, 2)
            cell = QHBoxLayout()
            label = QLabel(self.t(translation_key, default_label))
            spin = QSpinBox()
            spin.setRange(0, 100)
            spin.setSingleStep(5)
            spin.setValue(int(DEFAULT_PARAMETERS[key]))
            self.parameter_spins[key] = spin
            cell.addWidget(label, 1)
            cell.addWidget(spin)
            parameters_grid.addLayout(cell, row, col)
        editor.addLayout(parameters_grid)

        editor.addWidget(QLabel(self.t("personality_editor_system_prompt", "System / personality prompt")))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText(self.t("personality_editor_prompt_placeholder", "Describe the character, priorities, communication style, and boundaries."))
        editor.addWidget(self.prompt_edit, 1)

        action_row = QHBoxLayout()
        self.save_btn = QPushButton(self.t("personality_editor_save", "Save as custom JSON"))
        self.save_btn.setObjectName("AccentButton")
        self.save_btn.clicked.connect(self.save_personality)
        self.delete_btn = QPushButton(self.t("personality_editor_delete", "Delete custom file / restore built-in"))
        self.delete_btn.clicked.connect(self.delete_personality)
        action_row.addWidget(self.save_btn)
        action_row.addWidget(self.delete_btn)
        action_row.addStretch(1)
        editor.addLayout(action_row)
        body.addWidget(editor_widget, 3)
        root.addLayout(body, 1)

        bottom = QHBoxLayout()
        hint = QLabel(self.t(
            "personality_editor_hint",
            "Built-in presets stay untouched. Saving a built-in creates an editable override in app_data/personalities.",
        ))
        hint.setWordWrap(True)
        hint.setObjectName("SubtleLabel")
        bottom.addWidget(hint, 1)
        close_btn = QPushButton(self.t("close", "Close"))
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

        self.reload_list()

    def current_role(self) -> str:
        return str(self.role_combo.currentData() or "user")

    def _gender_label(self, value: str) -> str:
        return {
            "female": self.t("personality_gender_female", "Female"),
            "male": self.t("personality_gender_male", "Male"),
            "neutral": self.t("personality_gender_neutral", "Neutral"),
        }.get(value, value)

    def _origin_label(self, role: str, personality_id: str) -> str:
        origin = personality_origin(role, personality_id)
        return {
            "builtin": self.t("personality_origin_builtin", "Built-in"),
            "custom": self.t("personality_origin_custom", "Custom"),
            "override": self.t("personality_origin_override", "Custom override of built-in"),
            "missing": self.t("personality_origin_missing", "Not saved"),
        }.get(origin, origin)

    def reload_list(self, preferred_id: str = "") -> None:
        role = self.current_role()
        selected_id = preferred_id
        if not selected_id and self.list_widget.currentItem() is not None:
            selected_id = str(self.list_widget.currentItem().data(0x0100) or "")
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        target_row = -1
        for index, personality in enumerate(load_personalities(role)):
            label = f"{personality.localized_name(self.language_code)} · {self._gender_label(personality.gender)}"
            item = QListWidgetItem(label)
            item.setData(0x0100, personality.personality_id)
            item.setToolTip(personality.localized_description(self.language_code))
            self.list_widget.addItem(item)
            if personality.personality_id == selected_id:
                target_row = index
        self.list_widget.blockSignals(False)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(target_row if target_row >= 0 else 0)
        else:
            self.new_personality()

    def load_selected(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem] = None) -> None:
        if current is None:
            return
        personality_id = str(current.data(0x0100) or "")
        personality = load_personality(self.current_role(), personality_id)
        if personality is None:
            return
        self.current_personality = personality
        self.current_is_new = False
        self.id_edit.setText(personality.personality_id)
        self.id_edit.setReadOnly(True)
        self.name_edit.setText(personality.localized_name(self.language_code))
        self.description_edit.setPlainText(personality.localized_description(self.language_code))
        self.prompt_edit.setPlainText(personality.localized_prompt(self.language_code))
        gender_index = self.gender_combo.findData(personality.gender)
        self.gender_combo.setCurrentIndex(max(0, gender_index))
        parameters = personality.parameters
        self.tone_edit.setText(str(parameters.get("tone", "") or ""))
        for key, spin in self.parameter_spins.items():
            spin.setValue(int(parameters.get(key, DEFAULT_PARAMETERS[key])))
        self.origin_label.setText(
            self.t("personality_editor_origin_value", "Origin: {origin}").format(
                origin=self._origin_label(personality.role, personality.personality_id)
            )
        )

    def new_personality(self) -> None:
        self.list_widget.clearSelection()
        self.current_personality = None
        self.current_is_new = True
        self.id_edit.clear()
        self.id_edit.setReadOnly(False)
        self.name_edit.clear()
        self.description_edit.clear()
        self.prompt_edit.clear()
        self.gender_combo.setCurrentIndex(max(0, self.gender_combo.findData("neutral")))
        self.tone_edit.setText(str(DEFAULT_PARAMETERS["tone"]))
        for key, spin in self.parameter_spins.items():
            spin.setValue(int(DEFAULT_PARAMETERS[key]))
        self.origin_label.setText(self.t("personality_origin_new", "New custom personality"))
        self.name_edit.setFocus()

    def duplicate_personality(self) -> None:
        if self.current_personality is None:
            return
        base = self.current_personality
        self.current_is_new = True
        self.current_personality = None
        new_id = safe_personality_id(base.personality_id + "_copy")
        existing = {item.personality_id for item in load_personalities(self.current_role())}
        suffix = 2
        candidate = new_id
        while candidate in existing:
            candidate = safe_personality_id(f"{new_id}_{suffix}")
            suffix += 1
        self.id_edit.setReadOnly(False)
        self.id_edit.setText(candidate)
        self.name_edit.setText(self.t("personality_copy_name", "{name} (copy)").format(name=base.localized_name(self.language_code)))
        self.origin_label.setText(self.t("personality_origin_new", "New custom personality"))

    def _localized_replacement(self, original: Any, text: str) -> Any:
        if isinstance(original, dict):
            updated = dict(original)
            updated[self.language_code] = text.strip()
            return updated
        return text.strip()

    def _personality_from_fields(self) -> Personality:
        personality_id = safe_personality_id(self.id_edit.text())
        if not personality_id:
            personality_id = safe_personality_id(self.name_edit.text())
            self.id_edit.setText(personality_id)
        if not personality_id:
            raise ValueError(self.t("personality_editor_error_id", "Please enter a valid file ID or display name."))
        name = self.name_edit.text().strip()
        prompt = self.prompt_edit.toPlainText().strip()
        if not name:
            raise ValueError(self.t("personality_editor_error_name", "Please enter a display name."))
        if not prompt:
            raise ValueError(self.t("personality_editor_error_prompt", "Please enter a personality prompt."))
        original = self.current_personality
        name_value: Any = name
        description_value: Any = self.description_edit.toPlainText().strip()
        prompt_value: Any = prompt
        if original is not None:
            name_value = self._localized_replacement(original.name, name)
            description_value = self._localized_replacement(original.description, self.description_edit.toPlainText())
            prompt_value = self._localized_replacement(original.system_prompt, prompt)
        parameters = {key: spin.value() for key, spin in self.parameter_spins.items()}
        parameters["tone"] = self.tone_edit.text().strip() or "balanced"
        return Personality(
            personality_id=personality_id,
            role=self.current_role(),
            name=name_value,
            gender=str(self.gender_combo.currentData() or "neutral"),
            description=description_value,
            parameters=parameters,
            system_prompt=prompt_value,
        )

    def save_personality(self) -> None:
        try:
            personality = self._personality_from_fields()
            save_custom_personality(personality)
        except Exception as exc:
            QMessageBox.warning(
                self,
                self.t("personality_editor_save_failed_title", "Personality could not be saved"),
                str(exc),
            )
            return
        self.changed = True
        self.current_is_new = False
        self.reload_list(personality.personality_id)
        QMessageBox.information(
            self,
            self.t("personality_editor_saved_title", "Personality saved"),
            self.t("personality_editor_saved_text", "The personality was saved as an individual JSON file."),
        )

    def delete_personality(self) -> None:
        personality_id = self.id_edit.text().strip()
        if not personality_id:
            return
        origin = personality_origin(self.current_role(), personality_id)
        if origin == "builtin":
            QMessageBox.information(
                self,
                self.t("personality_editor_builtin_delete_title", "Built-in preset"),
                self.t("personality_editor_builtin_delete_text", "Built-in files are protected. Duplicate the preset or save an override first."),
            )
            return
        if origin not in {"custom", "override"}:
            return
        answer = QMessageBox.question(
            self,
            self.t("personality_editor_delete_title", "Delete custom personality"),
            self.t("personality_editor_delete_text", "Delete the custom JSON file? A built-in preset with the same ID will become visible again."),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if delete_custom_personality(self.current_role(), personality_id):
            self.changed = True
            self.reload_list(personality_id)

    def import_json(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            self.t("personality_editor_import_title", "Import personality JSON"),
            "",
            self.t("json_files_filter", "JSON files (*.json);;All files (*)"),
        )
        imported = 0
        last_id = ""
        for raw_path in file_paths:
            try:
                data = json.loads(Path(raw_path).read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("JSON root is not an object")
                role = str(data.get("role", self.current_role()) or self.current_role()).strip().lower()
                if role not in {"user", "assistant"}:
                    raise ValueError("Unsupported role")
                personality = Personality(
                    personality_id=safe_personality_id(str(data.get("id", "") or Path(raw_path).stem)),
                    role=role,
                    name=data.get("name", Path(raw_path).stem),
                    gender=str(data.get("gender", "neutral") or "neutral"),
                    description=data.get("description", ""),
                    parameters=data.get("parameters", DEFAULT_PARAMETERS.copy()),
                    system_prompt=data.get("system_prompt", ""),
                )
                if not localized_text(personality.system_prompt, self.language_code):
                    raise ValueError("Missing system_prompt")
                save_custom_personality(personality)
                imported += 1
                if role == self.current_role():
                    last_id = personality.personality_id
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    self.t("personality_editor_import_failed_title", "Import failed"),
                    self.t("personality_editor_import_failed_text", "Could not import {file}:\n{error}").format(file=raw_path, error=exc),
                )
        if imported:
            self.changed = True
            self.reload_list(last_id)

    def export_json(self) -> None:
        if self.current_personality is None and not self.id_edit.text().strip():
            return
        try:
            personality = self._personality_from_fields()
        except Exception as exc:
            QMessageBox.warning(
                self,
                self.t("personality_editor_export_failed_title", "Export failed"),
                str(exc),
            )
            return
        default_path = f"{personality.personality_id}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.t("personality_editor_export_title", "Export personality JSON"),
            default_path,
            self.t("json_files_filter", "JSON files (*.json);;All files (*)"),
        )
        if not file_path:
            return
        try:
            Path(file_path).write_text(
                json.dumps(personality.to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                self.t("personality_editor_export_failed_title", "Export failed"),
                str(exc),
            )

    def open_custom_folder(self) -> None:
        path = PERSONALITIES_USER_DIR if self.current_role() == "user" else PERSONALITIES_ASSISTANT_DIR
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
