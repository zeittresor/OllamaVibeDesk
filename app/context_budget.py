from __future__ import annotations


def request_token_budget(num_ctx: object, minimum_budget: int = 2048) -> int:
    try:
        context = max(2048, int(num_ctx or 0))
    except (TypeError, ValueError):
        context = 2048
    return int(context * 0.88)


def rollover_output_reserve(num_ctx: object, configured_max_tokens: object) -> int:
    try:
        context = max(2048, int(num_ctx or 0))
    except (TypeError, ValueError):
        context = 2048
    try:
        configured = max(64, int(configured_max_tokens or 0))
    except (TypeError, ValueError):
        configured = 512
    practical_reserve = max(256, min(2048, int(context * 0.20)))
    return min(configured, practical_reserve)


def would_exceed_rollover_budget(
    prompt_tokens: object,
    num_ctx: object,
    configured_max_tokens: object,
    minimum_budget: int = 2048,
) -> bool:
    try:
        prompt = max(0, int(prompt_tokens or 0))
    except (TypeError, ValueError):
        prompt = 0
    projected = prompt + rollover_output_reserve(num_ctx, configured_max_tokens)
    return projected > request_token_budget(num_ctx, minimum_budget)


def estimate_token_count(text: str) -> int:
    # Byte-aware estimate avoids the old severe undercount for CJK, emoji and code.
    import re
    raw = str(text or "")
    return max((len(raw.encode("utf-8")) + 2) // 3, int(len(re.findall(r"\S+", raw)) * 1.4)) if raw else 0


def estimate_chat_payload_tokens(messages: list[dict], system_prompt: str = "") -> int:
    return 16 + estimate_token_count(system_prompt) + sum(12 + estimate_token_count(str(m.get("content", ""))) for m in messages)
