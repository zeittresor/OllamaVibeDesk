from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.config import APP_DATA_DIR, APP_ROOT
from app.file_utils import atomic_write_text


RESOURCE_DIR = APP_ROOT / "resources" / "auto_answer" / "guidance"
DATA_DIR = APP_DATA_DIR / "auto_answer" / "guidance"
OVERRIDE_DIR = APP_DATA_DIR / "auto_answer" / "guidance_overrides"
STANDARD_PRESET_ID = "standard"
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class GuidancePreset:
    preset_id: str
    name: str


def normalize_language_code(language_code: str) -> str:
    code = str(language_code or "de").strip().lower().replace("_", "-")
    return code.split("-", 1)[0] or "de"


def normalize_preset_id(value: object) -> str:
    preset_id = str(value or STANDARD_PRESET_ID).strip().lower()
    return preset_id if SAFE_ID.fullmatch(preset_id) else STANDARD_PRESET_ID


def _catalog_path(language_code: str, *, editable: bool) -> Path:
    root = DATA_DIR if editable else RESOURCE_DIR
    return root / f"{normalize_language_code(language_code)}.json"


def _clean_items(items: Iterable[object]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in items:
        value = str(raw or "").strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def ensure_guidance_data() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OVERRIDE_DIR.mkdir(parents=True, exist_ok=True)
    if not RESOURCE_DIR.is_dir():
        return
    for source in RESOURCE_DIR.glob("*.json"):
        target = DATA_DIR / source.name
        if not target.exists():
            atomic_write_text(target, source.read_text(encoding="utf-8"))


def load_catalog(language_code: str) -> dict:
    code = normalize_language_code(language_code)
    for path in (_catalog_path(code, editable=True), _catalog_path(code, editable=False)):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(raw, dict):
            continue
        templates = _clean_items(raw.get("templates", [])) if isinstance(raw.get("templates"), list) else []
        presets: list[dict] = []
        seen_ids: set[str] = set()
        for item in raw.get("presets", []) if isinstance(raw.get("presets"), list) else []:
            if not isinstance(item, dict):
                continue
            preset_id = normalize_preset_id(item.get("id"))
            name = str(item.get("name", "") or "").strip()
            if preset_id == STANDARD_PRESET_ID or preset_id in seen_ids or not name:
                continue
            seen_ids.add(preset_id)
            presets.append({"id": preset_id, "name": name})
        if templates and presets:
            return {
                "templates": templates,
                "presets": presets,
                "llm_instruction": str(raw.get("llm_instruction", "") or "").strip(),
            }
    return {"templates": [], "presets": [], "llm_instruction": ""}


def load_presets(language_code: str) -> list[GuidancePreset]:
    return [GuidancePreset(item["id"], item["name"]) for item in load_catalog(language_code)["presets"]]


def preset_name(language_code: str, preset_id: str) -> str:
    wanted = normalize_preset_id(preset_id)
    return next((item.name for item in load_presets(language_code) if item.preset_id == wanted), "")


def _override_path(language_code: str, preset_id: str) -> Path:
    code = normalize_language_code(language_code)
    safe_id = normalize_preset_id(preset_id)
    return OVERRIDE_DIR / code / f"{safe_id}.json"


def guidance_phrases(language_code: str, preset_id: str) -> list[str]:
    safe_id = normalize_preset_id(preset_id)
    if safe_id == STANDARD_PRESET_ID:
        return []
    override = _override_path(language_code, safe_id)
    if override.is_file():
        try:
            raw = json.loads(override.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                items = _clean_items(raw)
                if items:
                    return items
        except (OSError, ValueError, TypeError):
            pass
    catalog = load_catalog(language_code)
    goal = next((item["name"] for item in catalog["presets"] if item["id"] == safe_id), "")
    if not goal:
        return []
    return _clean_items(template.replace("{goal}", goal) for template in catalog["templates"])


def write_guidance_phrases(language_code: str, preset_id: str, phrases: Iterable[object]) -> Path:
    safe_id = normalize_preset_id(preset_id)
    if safe_id == STANDARD_PRESET_ID:
        raise ValueError("The standard mode has no guidance phrases")
    cleaned = _clean_items(phrases)
    if not cleaned:
        raise ValueError("At least one guidance phrase is required")
    target = _override_path(language_code, safe_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, json.dumps(cleaned, indent=2, ensure_ascii=False))
    return target


def reset_guidance_phrases(language_code: str, preset_id: str) -> None:
    _override_path(language_code, preset_id).unlink(missing_ok=True)


def guidance_llm_instruction(language_code: str, preset_id: str, strength: int) -> str:
    safe_id = normalize_preset_id(preset_id)
    strength = max(0, min(100, int(strength or 0)))
    if safe_id == STANDARD_PRESET_ID or strength <= 0:
        return ""
    catalog = load_catalog(language_code)
    goal = next((item["name"] for item in catalog["presets"] if item["id"] == safe_id), "")
    template = str(catalog.get("llm_instruction", "") or "")
    if not goal or not template:
        return ""
    return template.replace("{goal}", goal).replace("{strength}", str(strength))
