from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable

_CONTINUATION_WORDS = (
    "fortsetzung|continuation|continued|suite|continuacion|continuación|continuação|"
    "vervolg|kontynuacja|продолжение|continuazione|続き|계속|जारी"
)
_CONTINUATION_RE = re.compile(
    rf"\s*(?:[-–—·:]\s*)?[\[(]?\s*(?:{_CONTINUATION_WORDS})(?:\s+(\d+))?\s*[\])]?\s*$",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[^\W\d_][\w+#.-]{2,}", re.UNICODE)

# A compact multilingual list is sufficient here: the title extractor only
# needs to suppress conversational glue, not perform linguistic analysis.
_STOPWORDS = {
    "aber", "auch", "bitte", "dann", "dass", "dein", "deine", "dem", "den", "der", "des", "die", "dies", "diese",
    "doch", "ein", "eine", "einem", "einen", "einer", "eigentlich", "für", "ganz", "gern", "gerne", "hat", "haben",
    "hier", "ich", "immer", "ist", "kann", "können", "mal", "mehr", "mit", "muss", "noch", "oder", "schon", "sein",
    "sich", "sind", "soll", "sollte", "über", "und", "uns", "von", "wenn", "werden", "wie", "wieder", "wir", "wäre",
    "also", "aktuell", "allgemeine", "bekommen", "bisher", "etwas", "vielleicht", "wirklich", "jeweils", "neuen", "neue", "neuer", "neues",
    "sollten", "zuerst", "unterstützen", "optimieren", "optimiere", "sprechen",
    "about", "after", "again", "and", "are", "been", "before", "but", "can", "could", "for", "from", "have",
    "into", "just", "more", "not", "please", "should", "that", "the", "their", "then", "there", "these", "this", "those",
    "through", "use", "using", "very", "want", "was", "were", "what", "when", "which", "will", "with", "would", "you", "your",
    "chat", "chats", "conversation", "unterhaltung", "antwort", "response", "message", "nachricht", "modell", "model", "models",
    "assistant", "assistent", "user", "benutzer", "funktion", "functions", "feature", "features", "option", "optionen", "settings",
    "pero", "para", "con", "que", "une", "pour", "avec", "mais", "voor", "een", "het", "nie", "oraz", "dla",
}


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


_FOLDED_STOPWORDS = {_fold(word) for word in _STOPWORDS}


def strip_continuation_suffix(title: str) -> str:
    cleaned = str(title or "").strip()
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        cleaned = _CONTINUATION_RE.sub("", cleaned).strip(" -–—·:")
    return cleaned


def infer_continuation_index(title: str, stored_index: object = 0) -> int:
    try:
        index = max(0, int(stored_index or 0))
    except (TypeError, ValueError):
        index = 0
    match = _CONTINUATION_RE.search(str(title or ""))
    if not match:
        return index
    try:
        title_index = int(match.group(1)) if match.group(1) else 1
    except (TypeError, ValueError):
        title_index = 1
    return max(index, title_index)


def _message_fields(message: object) -> tuple[str, str, bool]:
    if isinstance(message, dict):
        role = str(message.get("role", "") or "")
        text = str((message.get("content") if role == "assistant" else message.get("display_content") or message.get("content")) or "")
        generated = bool(message.get("generated", False))
        return role, text, generated
    role = str(getattr(message, "role", "") or "")
    text = str((getattr(message, "content", "") if role == "assistant" else getattr(message, "display_content", None) or getattr(message, "content", "")) or "")
    generated = bool(getattr(message, "generated", False))
    return role, text, generated


def _clean_text(value: str) -> str:
    text = re.sub(r"```.*?```|~~~.*?~~~", " ", str(value or ""), flags=re.DOTALL)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"\([^()]*(?:additional instruction|zusatzprompt|hidden instruction)[^()]*\)", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def infer_topic_title(messages: Iterable[object], fallback_title: str = "", max_length: int = 54) -> str:
    recent = list(messages)[-6:]
    token_scores: dict[str, float] = defaultdict(float)
    display_forms: dict[str, str] = {}
    first_positions: dict[str, int] = {}
    position = 0

    for message_index, message in enumerate(recent):
        role, raw_text, generated = _message_fields(message)
        text = _clean_text(raw_text)
        if not text:
            continue
        recency = 0.55 ** (len(recent) - message_index - 1)
        occurrences = defaultdict(int)
        role_weight = 1.35 if role == "user" else 1.0
        if generated and role == "user":
            role_weight *= 0.72
        for token in _TOKEN_RE.findall(text):
            variants = [token]
            if "-" in token:
                variants.extend(part for part in token.split("-") if len(part) >= 3)
            for variant in variants:
                folded = _fold(variant).strip(".-")
                if len(folded) < 3 or folded in _FOLDED_STOPWORDS or folded.isdigit():
                    continue
                # Repeated, recent topic words naturally outrank one-off filler.
                occurrences[folded] += 1
                if occurrences[folded] > 2:
                    continue
                token_scores[folded] += recency * role_weight * (1.12 if len(folded) >= 7 else 1.0)
                display_forms.setdefault(folded, variant.strip(".-"))
                first_positions.setdefault(folded, position)
            position += 1

    if not token_scores:
        return strip_continuation_suffix(fallback_title)[:max_length].strip()

    ranked = sorted(token_scores, key=lambda item: (-token_scores[item], first_positions.get(item, 0)))
    selected: list[str] = []
    for folded in ranked:
        if any(folded.startswith(existing) or existing.startswith(folded) for existing in selected):
            continue
        selected.append(folded)
        if len(selected) >= 2:
            break
    selected.sort(key=lambda item: first_positions.get(item, 0))

    title = " · ".join(display_forms[item] for item in selected).strip()
    fallback = strip_continuation_suffix(fallback_title).strip()
    if len(title) < 4:
        title = fallback
    if len(title) > max_length:
        title = title[: max(1, max_length - 1)].rstrip(" -–—·:,.!") + "…"
    return title or fallback or "Conversation"


def build_continuation_title(
    messages: Iterable[object],
    previous_title: str,
    continuation_index: int,
    suffix_template: str = " (Continuation {number})",
    max_length: int = 76,
) -> tuple[str, str]:
    number = max(1, int(continuation_index or 1))
    suffix = str(suffix_template or " (Continuation {number})").format(number=number)
    topic_limit = max(18, max_length - len(suffix))
    topic = infer_topic_title(messages, previous_title, topic_limit)
    title = f"{topic}{suffix}"
    if len(title) > max_length:
        topic = topic[: max(1, topic_limit - 1)].rstrip(" -–—·:,.!") + "…"
        title = f"{topic}{suffix}"
    return title, topic
