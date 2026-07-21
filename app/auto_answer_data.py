from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from app.config import APP_ROOT, APP_DATA_DIR
from app.file_utils import atomic_write_text
RESOURCE_DIR = APP_ROOT / "resources" / "auto_answer"
DATA_DIR = APP_DATA_DIR / "auto_answer"
LEGACY_PHRASES_PATH = APP_DATA_DIR / "auto_answer_phrases.json"
LEGACY_QUESTION_REPLIES_PATH = APP_DATA_DIR / "auto_answer_question_replies.json"

KINDS = ("phrases", "topic_words", "question_replies", "eliza")


def normalize_language_code(language_code: str) -> str:
    code = str(language_code or "de").strip().lower().replace("_", "-")
    return code.split("-", 1)[0] or "de"


def data_path(kind: str, language_code: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"Unsupported auto-answer data kind: {kind}")
    return DATA_DIR / kind / f"{normalize_language_code(language_code)}.json"


def resource_path(kind: str, language_code: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"Unsupported auto-answer data kind: {kind}")
    return RESOURCE_DIR / kind / f"{normalize_language_code(language_code)}.json"


def _clean_items(items: Iterable[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def read_list(kind: str, language_code: str, *, fallback_to_english: bool = False) -> list[str]:
    code = normalize_language_code(language_code)
    candidates = [data_path(kind, code), resource_path(kind, code)]
    if fallback_to_english and code != "en":
        candidates.extend([data_path(kind, "en"), resource_path(kind, "en")])
    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict):
            raw = raw.get("items", [])
        if isinstance(raw, list):
            return _clean_items(raw)
    return []


def write_list(kind: str, language_code: str, items: Iterable[object]) -> Path:
    path = data_path(kind, language_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(_clean_items(items), indent=2, ensure_ascii=False))
    return path


def reset_to_default(kind: str, language_code: str) -> Path:
    source = resource_path(kind, language_code)
    target = data_path(kind, language_code)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        atomic_write_text(target, source.read_text(encoding="utf-8"))
    else:
        atomic_write_text(target, "[]\n")
    return target


def available_data_languages() -> list[str]:
    result: set[str] = set()
    for root in (DATA_DIR, RESOURCE_DIR):
        for kind in KINDS:
            directory = root / kind
            if not directory.exists():
                continue
            result.update(path.stem for path in directory.glob("*.json"))
    return sorted(result)


def _migrate_legacy_file() -> None:
    if LEGACY_PHRASES_PATH.exists():
        try:
            legacy = json.loads(LEGACY_PHRASES_PATH.read_text(encoding="utf-8"))
        except Exception:
            legacy = {}
        if isinstance(legacy, dict):
            for kind in ("phrases", "topic_words"):
                mapping = legacy.get(kind, {})
                if not isinstance(mapping, dict):
                    continue
                for code, items in mapping.items():
                    target = data_path(kind, code)
                    if not target.exists() and isinstance(items, list):
                        write_list(kind, code, items)
    if LEGACY_QUESTION_REPLIES_PATH.exists():
        try:
            legacy = json.loads(LEGACY_QUESTION_REPLIES_PATH.read_text(encoding="utf-8"))
        except Exception:
            legacy = {}
        mapping = legacy.get("replies", {}) if isinstance(legacy, dict) else {}
        if isinstance(mapping, dict):
            for code, items in mapping.items():
                target = data_path("question_replies", code)
                if not target.exists() and isinstance(items, list):
                    write_list("question_replies", code, items)


def ensure_auto_answer_data() -> None:
    for kind in KINDS:
        (DATA_DIR / kind).mkdir(parents=True, exist_ok=True)
    _migrate_legacy_file()
    for kind in KINDS:
        source_dir = RESOURCE_DIR / kind
        if not source_dir.exists():
            continue
        for source in source_dir.glob("*.json"):
            target = DATA_DIR / kind / source.name
            if not target.exists():
                atomic_write_text(target, source.read_text(encoding="utf-8"))


def load_bundle(language_code: str) -> tuple[dict, dict]:
    """Return the legacy-compatible shapes used by the existing generator."""
    code = normalize_language_code(language_code)
    # Runtime Auto-Answer data is always language-pure. The immutable resource
    # file of the same language is already used as the fallback for a missing or
    # invalid editable file, so no foreign-language fallback is needed.
    phrases = read_list("phrases", code, fallback_to_english=False)
    topic_words = read_list("topic_words", code, fallback_to_english=False)
    replies = read_list("question_replies", code, fallback_to_english=False)
    eliza = read_list("eliza", code, fallback_to_english=False)
    return (
        {"enabled": True, "phrases": {code: phrases}, "topic_words": {code: topic_words}, "eliza": {code: eliza}},
        {"enabled": True, "replies": {code: replies}},
    )
