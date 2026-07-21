from __future__ import annotations

import json
import re
from functools import lru_cache

from app.config import APP_ROOT

PROFILE_DIR = APP_ROOT / "resources" / "language_profiles"

_DEFAULT_PROFILE = {
    "sapi_language_tag": "en-US",
    "assistant_voice_candidates": [],
    "user_voice_candidates": [],
    "reflection_rules": [],
}


def normalize_language_code(language_code: str) -> str:
    code = str(language_code or "en").strip().lower().replace("_", "-")
    return code.split("-", 1)[0] or "en"


@lru_cache(maxsize=32)
def load_language_profile(language_code: str) -> dict:
    code = normalize_language_code(language_code)
    profile = dict(_DEFAULT_PROFILE)
    candidates = [PROFILE_DIR / f"{code}.json"]
    if code != "en":
        candidates.append(PROFILE_DIR / "en.json")
    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict):
            profile.update(raw)
            break
    profile["language_code"] = code
    return profile


def sapi_language_tag(language_code: str) -> str:
    return str(load_language_profile(language_code).get("sapi_language_tag") or "en-US")


def preferred_voice_candidates(language_code: str, role: str) -> list[str]:
    profile = load_language_profile(language_code)
    key = "assistant_voice_candidates" if role == "assistant" else "user_voice_candidates"
    raw = profile.get(key, [])
    return [str(item).strip() for item in raw if str(item).strip()] if isinstance(raw, list) else []


def reflect_fragment(fragment: str, language_code: str) -> str:
    result = str(fragment or "")
    raw_rules = load_language_profile(language_code).get("reflection_rules", [])
    if not isinstance(raw_rules, list):
        return result
    # Placeholders prevent a replacement performed early in the list from being
    # matched again by a later rule (e.g. "du" -> "ich" -> "you").
    placeholders: dict[str, str] = {}
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            continue
        source = str(raw_rule.get("from", "") or "").strip()
        target = str(raw_rule.get("to", "") or "").strip()
        if not source:
            continue
        token = f"__OVD_REFLECT_{index}__"
        flags = 0 if bool(raw_rule.get("case_sensitive", False)) else re.IGNORECASE
        pattern = re.escape(source)
        if bool(raw_rule.get("word", True)):
            pattern = rf"\b{pattern}\b"
        try:
            result, count = re.subn(pattern, token, result, flags=flags)
        except re.error:
            continue
        if count:
            placeholders[token] = target
    for token, target in placeholders.items():
        result = result.replace(token, target)
    return result
