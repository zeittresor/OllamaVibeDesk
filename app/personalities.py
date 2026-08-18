from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from app.config import (
    PERSONALITIES_ASSISTANT_DIR,
    PERSONALITIES_RESOURCE_DIR,
    PERSONALITIES_USER_DIR,
)
from app.file_utils import atomic_write_text

CUSTOM_PERSONALITY_ID = "custom"
VALID_ROLES = {"user", "assistant"}
VALID_GENDERS = {"female", "male", "neutral"}
DEFAULT_PARAMETERS: Dict[str, Any] = {
    "tone": "balanced",
    "formality": 50,
    "verbosity": 50,
    "empathy": 50,
    "humor": 25,
    "assertiveness": 50,
    "curiosity": 60,
    "creativity": 50,
}

LANGUAGE_NAMES = {
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "hi": "Hindi",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ru": "Russian",
}


@dataclass
class Personality:
    personality_id: str
    role: str
    name: Any
    gender: str = "neutral"
    description: Any = ""
    parameters: Dict[str, Any] = field(default_factory=lambda: DEFAULT_PARAMETERS.copy())
    system_prompt: Any = ""
    source_path: Optional[Path] = None
    built_in: bool = False

    def localized_name(self, language_code: str) -> str:
        return localized_text(self.name, language_code) or self.personality_id

    def localized_description(self, language_code: str) -> str:
        return localized_text(self.description, language_code)

    def localized_prompt(self, language_code: str) -> str:
        return localized_text(self.system_prompt, language_code)

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "id": self.personality_id,
            "role": self.role,
            "name": self.name,
            "gender": self.gender if self.gender in VALID_GENDERS else "neutral",
            "description": self.description,
            "parameters": normalized_parameters(self.parameters),
            "system_prompt": self.system_prompt,
        }


def localized_text(value: Any, language_code: str) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    language_code = (language_code or "en").strip().lower()
    for key in (language_code, "en", "de"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
    for item in value.values():
        if isinstance(item, str) and item.strip():
            return item.strip()
    return ""


def normalized_parameters(raw: Any) -> Dict[str, Any]:
    result = DEFAULT_PARAMETERS.copy()
    if isinstance(raw, dict):
        tone = str(raw.get("tone", result["tone"]) or result["tone"]).strip()
        result["tone"] = tone[:80] or "balanced"
        for key in ("formality", "verbosity", "empathy", "humor", "assertiveness", "curiosity", "creativity"):
            try:
                result[key] = max(0, min(100, int(raw.get(key, result[key]))))
            except (TypeError, ValueError):
                pass
    return result


def safe_personality_id(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_-")
    return value[:80]


def _role_custom_dir(role: str) -> Path:
    if role == "user":
        return PERSONALITIES_USER_DIR
    if role == "assistant":
        return PERSONALITIES_ASSISTANT_DIR
    raise ValueError(f"Unsupported personality role: {role}")


def _role_resource_dir(role: str) -> Path:
    if role not in VALID_ROLES:
        raise ValueError(f"Unsupported personality role: {role}")
    return PERSONALITIES_RESOURCE_DIR / role


def ensure_personality_directories() -> None:
    # Packaged presets are read-only resources. Only user-owned directories are
    # created at runtime so installed applications also work from protected paths.
    for path in (PERSONALITIES_USER_DIR, PERSONALITIES_ASSISTANT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _personality_from_data(data: Any, source_path: Path, built_in: bool) -> Optional[Personality]:
    if not isinstance(data, dict):
        return None
    role = str(data.get("role", "") or "").strip().lower()
    personality_id = safe_personality_id(str(data.get("id", "") or source_path.stem))
    if role not in VALID_ROLES or not personality_id or personality_id == CUSTOM_PERSONALITY_ID:
        return None
    gender = str(data.get("gender", "neutral") or "neutral").strip().lower()
    if gender not in VALID_GENDERS:
        gender = "neutral"
    prompt = data.get("system_prompt", "")
    if not localized_text(prompt, "en"):
        return None
    return Personality(
        personality_id=personality_id,
        role=role,
        name=data.get("name", personality_id),
        gender=gender,
        description=data.get("description", ""),
        parameters=normalized_parameters(data.get("parameters", {})),
        system_prompt=prompt,
        source_path=source_path,
        built_in=built_in,
    )


def _load_directory(path: Path, role: str, built_in: bool) -> Iterable[Personality]:
    if not path.exists():
        return []
    found: list[Personality] = []
    for file_path in sorted(path.glob("*.json")):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        personality = _personality_from_data(data, file_path, built_in)
        if personality is not None and personality.role == role:
            found.append(personality)
    return found


def load_personalities(role: str) -> list[Personality]:
    role = str(role or "").strip().lower()
    if role not in VALID_ROLES:
        return []
    ensure_personality_directories()
    merged: dict[str, Personality] = {}
    for item in _load_directory(_role_resource_dir(role), role, True):
        merged[item.personality_id] = item
    for item in _load_directory(_role_custom_dir(role), role, False):
        # A custom file with the same ID intentionally overrides a built-in preset.
        merged[item.personality_id] = item
    return sorted(merged.values(), key=lambda item: item.localized_name("en").casefold())


def load_personality(role: str, personality_id: str) -> Optional[Personality]:
    personality_id = safe_personality_id(personality_id)
    if not personality_id or personality_id == CUSTOM_PERSONALITY_ID:
        return None
    for item in load_personalities(role):
        if item.personality_id == personality_id:
            return item
    return None


def render_personality_prompt(personality: Personality, language_code: str) -> str:
    base = personality.localized_prompt(language_code).strip()
    if not base:
        return ""
    parameters = normalized_parameters(personality.parameters)
    # Runtime instructions live in the regular language packs instead of being
    # embedded as language-dependent strings in Python.
    from app.i18n import load_language_pack

    language_code = (language_code or "en").strip().lower()
    pack = load_language_pack(language_code)
    language_name = str(pack.get("language_name") or LANGUAGE_NAMES.get(language_code) or language_code)
    if personality.role == "user":
        role_instruction = pack.get(
            "personality_runtime_user_role_instruction",
            "You are producing the next message as the human user, not as the assistant.",
        )
    else:
        role_instruction = pack.get(
            "personality_runtime_assistant_role_instruction",
            "You are the responding assistant in the conversation.",
        )
    tuning_template = pack.get(
        "personality_runtime_tuning",
        "Treat these character values as tendencies from 0 to 100, not rigid quotas: formality={formality}, verbosity={verbosity}, empathy={empathy}, humor={humor}, assertiveness={assertiveness}, curiosity={curiosity}, creativity={creativity}. Tone: {tone}.",
    )
    tuning = str(tuning_template).format(**parameters)
    language_instruction = str(pack.get(
        "personality_runtime_language_instruction",
        "Use {language} unless the conversation explicitly requires another language.",
    )).format(language=language_name)
    return f"{base}\n\n{role_instruction}\n{tuning}\n{language_instruction}".strip()


def resolve_configured_personality_prompt(config: dict, role: str, language_code: str) -> str:
    if role == "user":
        personality_id = str(config.get("user_personality_id", CUSTOM_PERSONALITY_ID) or CUSTOM_PERSONALITY_ID)
        custom_prompt = str(config.get("auto_answer_llm_system_prompt", "") or "").strip()
    elif role == "assistant":
        personality_id = str(config.get("assistant_personality_id", CUSTOM_PERSONALITY_ID) or CUSTOM_PERSONALITY_ID)
        custom_prompt = str(config.get("system_prompt", "") or "").strip()
    else:
        raise ValueError(f"Unsupported personality role: {role}")

    if personality_id == CUSTOM_PERSONALITY_ID:
        return custom_prompt
    personality = load_personality(role, personality_id)
    if personality is None:
        return custom_prompt
    return render_personality_prompt(personality, language_code) or custom_prompt


def save_custom_personality(personality: Personality) -> Path:
    ensure_personality_directories()
    if personality.role not in VALID_ROLES:
        raise ValueError("Invalid role")
    personality.personality_id = safe_personality_id(personality.personality_id)
    if not personality.personality_id or personality.personality_id == CUSTOM_PERSONALITY_ID:
        raise ValueError("Invalid personality ID")
    target = _role_custom_dir(personality.role) / f"{personality.personality_id}.json"
    atomic_write_text(target, json.dumps(personality.to_dict(), indent=2, ensure_ascii=False))
    return target


def delete_custom_personality(role: str, personality_id: str) -> bool:
    personality_id = safe_personality_id(personality_id)
    if role not in VALID_ROLES or not personality_id:
        return False
    target = _role_custom_dir(role) / f"{personality_id}.json"
    if not target.exists():
        return False
    target.unlink()
    return True


def personality_origin(role: str, personality_id: str) -> str:
    custom = _role_custom_dir(role) / f"{safe_personality_id(personality_id)}.json"
    built_in = _role_resource_dir(role) / f"{safe_personality_id(personality_id)}.json"
    if custom.exists() and built_in.exists():
        return "override"
    if custom.exists():
        return "custom"
    if built_in.exists():
        return "builtin"
    return "missing"
