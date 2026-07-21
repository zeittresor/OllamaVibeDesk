from __future__ import annotations

import random
import re
from typing import Iterable

from app.auto_answer_data import normalize_language_code
from app.language_profiles import reflect_fragment


def result(text: str = "", source_kind: str = "", source_key: str = "") -> dict:
    return {
        "text": str(text or "").strip(),
        "source_kind": str(source_kind or "").strip(),
        "source_key": str(source_key or "").strip(),
    }


def normalize_compare_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).casefold()


def expand_phrase_templates(phrases: Iterable[str], topic_words: Iterable[str], rng: random.Random | None = None) -> list[tuple[str, str]]:
    """Render one independently randomized candidate per phrase template.

    Each template gets the same weight, regardless of how many @@@ placeholders it
    contains. Multiple placeholders use different topic words whenever possible.
    """
    randomizer = rng or random
    unique_topics: list[str] = []
    seen_topics: set[str] = set()
    for raw in topic_words:
        word = str(raw or "").strip()
        normalized = normalize_compare_text(word)
        if not normalized or normalized in seen_topics:
            continue
        seen_topics.add(normalized)
        unique_topics.append(word)

    templates = [str(item or "").strip() for item in phrases if str(item or "").strip()]
    randomizer.shuffle(templates)
    expanded: list[tuple[str, str]] = []
    for template in templates:
        placeholder_count = template.count("@@@")
        if placeholder_count <= 0:
            expanded.append((template, template))
            continue
        if not unique_topics:
            expanded.append((template.replace("@@@", "…"), template))
            continue
        if len(unique_topics) >= placeholder_count:
            selected = randomizer.sample(unique_topics, placeholder_count)
        else:
            selected = list(unique_topics)
            while len(selected) < placeholder_count:
                selected.append(randomizer.choice(unique_topics))
            randomizer.shuffle(selected)
        rendered = template
        for topic in selected:
            rendered = rendered.replace("@@@", topic, 1)
        expanded.append((rendered, template))
    return expanded


def unique_candidates(
    candidates: Iterable[tuple[str, str]],
    blocked_recent: Iterable[str],
    blocked_source_keys: Iterable[str] | None = None,
    allow_consecutive_dataset_reuse: bool = False,
    rng: random.Random | None = None,
) -> list[tuple[str, str]]:
    randomizer = rng or random
    blocked = {normalize_compare_text(item) for item in blocked_recent if normalize_compare_text(item)}
    blocked_sources = {str(item or "").strip() for item in (blocked_source_keys or []) if str(item or "").strip()}
    shuffled = list(candidates)
    randomizer.shuffle(shuffled)
    output: list[tuple[str, str]] = []
    seen_texts: set[str] = set()
    for phrase, source_key in shuffled:
        cleaned = str(phrase or "").strip()
        normalized = normalize_compare_text(cleaned)
        key = str(source_key or "").strip()
        if not cleaned or not normalized or normalized in blocked or normalized in seen_texts:
            continue
        if key and not allow_consecutive_dataset_reuse and key in blocked_sources:
            continue
        seen_texts.add(normalized)
        output.append((cleaned, key))
    return output



def is_question_text(text: str) -> bool:
    cleaned = str(text or "").rstrip()
    return bool(cleaned) and cleaned.endswith(("?", "？", "؟"))

def _question_replies(question_reply_data: dict | None, language_code: str) -> list[str]:
    if not isinstance(question_reply_data, dict):
        return []
    replies_map = question_reply_data.get("replies")
    if not isinstance(replies_map, dict):
        return []
    code = normalize_language_code(language_code)
    return [str(item).strip() for item in replies_map.get(code, []) if str(item).strip()]


def generate_from_clean_text(
    cleaned_source: str,
    language_code: str,
    phrase_data: dict | None = None,
    question_reply_data: dict | None = None,
    recent_generated_user_messages: list[str] | None = None,
    recent_dataset_source_keys: list[str] | None = None,
    eliza_share_percent: int = 30,
    use_question_replies_for_all: bool = True,
    allow_consecutive_dataset_reuse: bool = False,
    source_mode: str = "auto",
    rng: random.Random | None = None,
) -> dict:
    randomizer = rng or random
    cleaned = re.sub(r"\s+", " ", str(cleaned_source or "")).strip()
    fragment = cleaned[:180].strip(" .!?…:;,-") or cleaned[:180]
    code = normalize_language_code(language_code)

    phrases: list[str] = []
    topic_words: list[str] = []
    eliza_templates: list[str] = []
    if isinstance(phrase_data, dict):
        phrases_map = phrase_data.get("phrases")
        if isinstance(phrases_map, dict):
            phrases = [str(item).strip() for item in phrases_map.get(code, []) if str(item).strip()]
        topic_map = phrase_data.get("topic_words")
        if isinstance(topic_map, dict):
            # No foreign-language fallback for topic words.
            topic_words = [str(item).strip() for item in topic_map.get(code, []) if str(item).strip()]
        eliza_map = phrase_data.get("eliza")
        if isinstance(eliza_map, dict):
            reflected = reflect_fragment(fragment, code)
            for raw in eliza_map.get(code, []):
                template = str(raw or "").strip()
                if not template:
                    continue
                try:
                    template = template.format(fragment=reflected)
                except (KeyError, ValueError):
                    pass
                eliza_templates.append(template)

    blocked_recent = recent_generated_user_messages or []
    blocked_source_keys = recent_dataset_source_keys or []
    question_replies = _question_replies(question_reply_data, code)
    question_candidates = unique_candidates(
        [(reply, f"question_reply::{reply}") for reply in question_replies],
        blocked_recent,
        blocked_source_keys,
        allow_consecutive_dataset_reuse,
        rng=randomizer,
    )
    if is_question_text(cleaned) and question_candidates:
        selected_text, selected_key = randomizer.choice(question_candidates)
        return result(selected_text, "question_reply", selected_key)

    phrase_pool = [
        (text_value, f"phrase::{source_key}")
        for text_value, source_key in expand_phrase_templates(phrases, topic_words, rng=randomizer)
    ]
    if use_question_replies_for_all:
        phrase_pool.extend((reply, f"question_reply::{reply}") for reply in question_replies)
    phrase_candidates = unique_candidates(
        phrase_pool,
        blocked_recent,
        blocked_source_keys,
        allow_consecutive_dataset_reuse,
        rng=randomizer,
    )

    mode = str(source_mode or "auto").strip().lower()
    if mode == "eliza":
        return result(randomizer.choice(eliza_templates), "eliza", "") if eliza_templates else result()
    if mode == "phrases":
        if phrase_candidates:
            selected_text, selected_key = randomizer.choice(phrase_candidates)
            kind = "question_reply" if selected_key.startswith("question_reply::") else "phrase"
            return result(selected_text, kind, selected_key)
        return result(randomizer.choice(eliza_templates), "eliza", "") if eliza_templates else result()

    eliza_share = max(0, min(100, int(eliza_share_percent or 0)))
    use_eliza = not phrase_candidates or randomizer.randint(1, 100) <= eliza_share
    if use_eliza and eliza_templates:
        return result(randomizer.choice(eliza_templates), "eliza", "")
    if phrase_candidates:
        selected_text, selected_key = randomizer.choice(phrase_candidates)
        kind = "question_reply" if selected_key.startswith("question_reply::") else "phrase"
        return result(selected_text, kind, selected_key)
    return result(randomizer.choice(eliza_templates), "eliza", "") if eliza_templates else result()
