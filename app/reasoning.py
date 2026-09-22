from __future__ import annotations

from typing import Any

REASONING_EFFORTS = ("off", "auto", "low", "medium", "high")
OLLAMA_REASONING_LEVELS = ("low", "medium", "high")


def normalize_reasoning_effort(value: object, default: str = "off") -> str:
    """Normalize persisted/UI reasoning values to the supported local set."""
    normalized_default = str(default or "off").strip().lower()
    if normalized_default not in REASONING_EFFORTS:
        normalized_default = "off"

    if isinstance(value, bool):
        return "medium" if value else "off"
    text = str(value or "").strip().lower()
    aliases = {
        "": normalized_default,
        "none": "off",
        "false": "off",
        "disabled": "off",
        "0": "off",
        "true": "medium",
        "enabled": "medium",
        "1": "medium",
        "automatic": "auto",
    }
    text = aliases.get(text, text)
    return text if text in REASONING_EFFORTS else normalized_default


def normalize_model_reasoning_efforts(value: object) -> dict[str, str]:
    """Validate model-specific overrides without allowing unbounded config data."""
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for raw_name, raw_effort in list(value.items())[:512]:
        model_name = str(raw_name or "").strip()
        if not model_name or len(model_name) > 240 or any(char in model_name for char in "\r\n\0"):
            continue
        normalized[model_name] = normalize_reasoning_effort(raw_effort)
    return normalized


def configured_reasoning_effort(config: dict[str, Any] | None, model_name: str) -> str:
    cfg = config if isinstance(config, dict) else {}
    default = normalize_reasoning_effort(cfg.get("reasoning_default_effort", "off"), "off")
    overrides = normalize_model_reasoning_efforts(cfg.get("model_reasoning_efforts", {}))
    return overrides.get(str(model_name or "").strip(), default)


def resolve_reasoning_effort(
    config: dict[str, Any] | None,
    model_name: str,
    *,
    is_code_request: bool = False,
) -> str:
    """Resolve ``auto`` to an actual Ollama level for one concrete request."""
    configured = configured_reasoning_effort(config, model_name)
    if configured == "auto":
        return "medium" if is_code_request else "off"
    return configured


def ollama_think_value(value: object) -> bool | str:
    """Return the native Ollama ``think`` value for a resolved effort."""
    effort = normalize_reasoning_effort(value)
    if effort in OLLAMA_REASONING_LEVELS:
        return effort
    return False
