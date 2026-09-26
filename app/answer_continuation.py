"""Finish Ollama replies that hit the generation limit without exporting partial code."""
from __future__ import annotations

import re
from typing import Callable

from app.context_budget import estimate_chat_payload_tokens, request_token_budget


MAX_CONTINUATIONS = 10


def unclosed_code_fence(text: str) -> bool:
    marker = ""
    width = 0
    for line in str(text or "").splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if not match:
            continue
        run, tail = match.groups()
        if not marker:
            marker, width = run[0], len(run)
        elif run[0] == marker and len(run) >= width and not tail.strip():
            marker, width = "", 0
    return bool(marker)


def _append_without_repetition(previous: str, addition: str) -> str:
    for size in range(min(len(previous), len(addition), 1200), 2, -1):
        if previous.endswith(addition[:size]):
            return addition[size:]
    return addition


def _has_visible_answer(answer: str) -> bool:
    clean = re.sub(r"<think>.*?</think>|<think>.*$", "", answer,
                   flags=re.IGNORECASE | re.DOTALL)
    return bool(clean.strip())


def _continuation_request(messages: list[dict], system_prompt: str, answer: str,
                          num_ctx: int, configured_tokens: int, language: str) -> tuple[list[dict], int] | None:
    budget = request_token_budget(num_ctx)
    latest_user = next((str(item.get("content", "")) for item in reversed(messages)
                        if item.get("role") == "user"), "")
    if len(latest_user) > 1800:
        latest_user = latest_user[:850] + "\n[…]\n" + latest_user[-850:]
    paths = re.findall(r"(?im)^\s*(?:File|Datei):\s*([^\n]{1,180})", answer)
    files = "\n".join(paths[-20:])
    instruction = (
        "Setze die abgeschnittene Antwort exakt an der letzten Stelle fort. "
        "Wiederhole keinen Code und keine bereits ausgegebenen Dateien. "
        "Schließe Codeblöcke erst nach vollständigem Dateiinhalt. "
        "Gib ausschließlich den fortlaufenden Antworttext aus."
        if language == "de" else
        "Continue the cut-off answer at its exact final character. Do not repeat code "
        "or files already emitted. Close code fences only when a file is complete. "
        "Output only the continuation."
    )
    # The last output fragment and file names preserve the working position.
    # Reduce the fragment until the next reply has a useful output budget.
    for tail_chars in (3600, 2600, 1700, 1000, 500):
        prompt = f"Original task:\n{latest_user}\nFiles already named:\n{files}\n\n{instruction}"
        history = [{"role": "assistant", "content": answer[-tail_chars:]},
                   {"role": "user", "content": prompt}]
        room = budget - estimate_chat_payload_tokens(history, system_prompt)
        if room >= 256:
            return history, max(64, min(configured_tokens, room))
    return None


def stream_complete_answer(client, model: str, messages: list[dict], system_prompt: str,
                           max_tokens: int, num_ctx: int, think: str | bool | None,
                           emit: Callable[[dict], None], cancelled: Callable[[], bool],
                           language: str = "de", initial_response: dict | None = None,
                           max_continuations: int = MAX_CONTINUATIONS) -> tuple[str, bool]:
    """Emit an answer and return (visible text, incomplete). Never hide exhaustion."""
    answer = ""
    reason = ""
    if initial_response is not None:
        first = initial_response.get("message", {}) or {}
        content = str(first.get("content", "") or "")
        thinking = str(first.get("thinking", "") or "")
        if content or thinking:
            emit({"content": content, "thinking": thinking})
        answer = content
        reason = str(initial_response.get("done_reason", "") or "")
        stats = {key: initial_response[key] for key in
                 ("prompt_eval_count", "eval_count", "done_reason") if key in initial_response}
        if stats:
            emit({"stats": stats})
    else:
        for payload in client.stream_chat(model, messages, system_prompt,
                                          options={"num_predict": max_tokens, "num_ctx": num_ctx},
                                          think=think):
            if cancelled():
                return answer, False
            answer += str(payload.get("content", "") or "")
            if payload.get("stats"):
                reason = str(payload["stats"].get("done_reason", "") or "")
            emit(payload)

    for _ in range(max_continuations):
        if cancelled():
            return answer, False
        if not _has_visible_answer(answer):
            return answer, False
        if reason != "length" and not unclosed_code_fence(answer):
            return answer, False
        prepared = _continuation_request(messages, system_prompt, answer, num_ctx, max_tokens, language)
        if prepared is None:
            emit({"incomplete": True})
            return answer, True
        followup_messages, followup_tokens = prepared
        fragment = ""
        next_reason = ""
        for payload in client.stream_chat(model, followup_messages, system_prompt,
                                          options={"num_predict": followup_tokens, "num_ctx": num_ctx},
                                          think=False):
            if cancelled():
                return answer, False
            fragment += str(payload.get("content", "") or "")
            if payload.get("stats"):
                next_reason = str(payload["stats"].get("done_reason", "") or "")
                emit({"stats": payload["stats"]})
        extension = _append_without_repetition(answer, fragment)
        if not extension.strip():
            emit({"incomplete": True})
            return answer, True
        answer += extension
        emit({"content": extension, "thinking": ""})
        reason = next_reason
    if reason == "length" or unclosed_code_fence(answer):
        emit({"incomplete": True})
        return answer, True
    return answer, False
