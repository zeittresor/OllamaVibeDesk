"""Small, dependency-free language heuristic for local conversations.

The application language controls labels and settings.  Response language is a
separate concern: when a conversation contains several user messages, the
language with the strongest repeated natural-language evidence wins.  Code,
URLs and generated Auto-Answer messages are deliberately ignored.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Iterable


LANGUAGE_NAMES = {
    "de": "Deutsch",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "hi": "हिन्दी",
    "it": "Italiano",
    "ja": "日本語",
    "ko": "한국어",
    "nl": "Nederlands",
    "pl": "Polski",
    "pt": "Português",
    "ru": "Русский",
    "zh": "中文",
}

_WORD_RE = re.compile(r"[^\W\d_][\w'’À-ÿА-Яа-яЁё一-龯ぁ-ゖァ-ヺ가-힣]+", re.UNICODE)
_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_URL_RE = re.compile(r"https?://\S+|\b(?:[\w.-]+\.(?:com|de|org|net|io|dev|ai))(?:/\S*)?", re.IGNORECASE)
_MARKUP_RE = re.compile(r"<[^>]+>|\b(?:File|Datei|Project|Projekt):\s*[^\n]+", re.IGNORECASE)

# These are intentionally common function words rather than a full language
# model.  A few repeated markers are substantially more reliable than guessing
# from a single technical word such as "Model" or "Code".
_MARKERS = {
    "de": {"der", "die", "das", "den", "dem", "des", "und", "oder", "aber", "ich", "du", "wir", "nicht", "ist", "sind", "bitte", "eine", "ein", "für", "mit", "auch", "noch", "wie", "dass", "kann", "soll", "wird", "werden", "nun", "wenn", "weil", "bei", "auf", "aus", "zur", "zum"},
    "en": {"the", "and", "or", "but", "i", "you", "we", "not", "is", "are", "please", "a", "an", "for", "with", "also", "still", "how", "that", "can", "should", "will", "when", "because", "from", "this", "it", "to", "of", "in"},
    "es": {"el", "la", "los", "las", "y", "o", "pero", "yo", "tú", "tu", "nosotros", "no", "es", "son", "por", "con", "también", "cómo", "que", "puede", "debe", "será", "cuando", "porque", "para", "una", "un", "en"},
    "fr": {"le", "la", "les", "un", "une", "et", "ou", "mais", "je", "tu", "nous", "ne", "pas", "est", "sont", "pour", "avec", "aussi", "comment", "que", "peut", "doit", "quand", "parce", "dans", "sur", "de", "des"},
    "it": {"il", "lo", "la", "i", "gli", "le", "un", "una", "e", "o", "ma", "io", "tu", "noi", "non", "è", "sono", "per", "con", "anche", "come", "che", "può", "deve", "quando", "perché", "di", "del", "nel"},
    "nl": {"de", "het", "een", "en", "of", "maar", "ik", "jij", "wij", "niet", "is", "zijn", "voor", "met", "ook", "hoe", "dat", "kan", "moet", "zal", "wanneer", "omdat", "van", "in", "op"},
    "pt": {"o", "a", "os", "as", "um", "uma", "e", "ou", "mas", "eu", "você", "nós", "não", "é", "são", "para", "com", "também", "como", "que", "pode", "deve", "quando", "porque", "de", "do", "da", "em"},
    "pl": {"i", "lub", "ale", "ja", "ty", "my", "nie", "jest", "są", "proszę", "dla", "z", "ze", "także", "jak", "że", "może", "powinien", "kiedy", "ponieważ", "na", "do", "w"},
}
_FOLDED_MARKERS = {
    language: {unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode().casefold() for word in words}
    for language, words in _MARKERS.items()
}


def _text_of(item: object) -> tuple[str, str, bool]:
    if isinstance(item, dict):
        role = str(item.get("role", "") or "").casefold()
        text = str(item.get("display_content") or item.get("content") or "")
        return role, text, bool(item.get("generated", False))
    role = str(getattr(item, "role", "") or "").casefold()
    text = str(getattr(item, "display_content", None) or getattr(item, "content", "") or "")
    return role, text, bool(getattr(item, "generated", False))


def _natural_text(text: str) -> str:
    value = _CODE_RE.sub(" ", str(text or ""))
    value = _URL_RE.sub(" ", value)
    value = _MARKUP_RE.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def _script_language(text: str) -> tuple[str, float] | None:
    if re.search(r"[ぁ-ゖァ-ヺー]", text):
        return "ja", 8.0
    if re.search(r"[가-힣]", text):
        return "ko", 8.0
    if re.search(r"[一-龯]", text):
        return "zh", 8.0
    if re.search(r"[А-Яа-яЁё]", text):
        return "ru", 8.0
    if re.search(r"[ऀ-ॿ]", text):
        return "hi", 8.0
    return None


def detect_primary_language(items: Iterable[object], fallback: str = "de") -> str:
    """Return the dominant user-written language, with newest-message ties.

    Only explicit user messages count.  Generated Auto-Answer text, assistant
    replies, fenced code and URLs cannot silently change the answer language.
    """
    fallback = str(fallback or "de").strip().lower().split("-", 1)[0]
    if fallback not in LANGUAGE_NAMES:
        fallback = "de"
    scores: dict[str, float] = defaultdict(float)
    latest: dict[str, int] = {}
    for index, item in enumerate(items):
        role, raw, generated = _text_of(item)
        if role != "user" or generated:
            continue
        text = _natural_text(raw)
        if len(text) < 6:
            continue
        script = _script_language(text)
        if script is not None:
            language, score = script
            scores[language] += score + min(4.0, len(text) / 120.0)
            latest[language] = index
            continue
        words = _WORD_RE.findall(text.casefold())
        if not words:
            continue
        folded_words = [unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode() for word in words]
        for language, markers in _FOLDED_MARKERS.items():
            matches = sum(word in markers for word in folded_words)
            if matches:
                # Long messages contain more evidence, but do not swamp a
                # later equally clear language by raw character count.
                scores[language] += matches * (1.0 + min(0.45, len(words) / 120.0))
                latest[language] = index
        # Distinguish common Latin languages where function words are sparse.
        if re.search(r"[äöüß]", text.casefold()):
            scores["de"] += 1.5
            latest["de"] = index
        if re.search(r"[¿¡ñ]", text.casefold()):
            scores["es"] += 1.5
            latest["es"] = index
        if re.search(r"[àâçéèêëîïôùûüÿœ]", text.casefold()):
            scores["fr"] += 0.8
            latest["fr"] = index
    if not scores:
        return fallback
    # A result needs two markers or a distinctive-script score.  This avoids
    # switching a German chat merely because a user typed one English noun.
    ranked = sorted(scores, key=lambda code: (scores[code], latest.get(code, -1)), reverse=True)
    winner = ranked[0]
    if scores[winner] < 2.0 and winner not in {"ja", "ko", "zh", "ru", "hi"}:
        return fallback
    return winner if winner in LANGUAGE_NAMES else fallback


def language_name(language_code: str) -> str:
    code = str(language_code or "de").strip().lower().split("-", 1)[0]
    return LANGUAGE_NAMES.get(code, LANGUAGE_NAMES["de"])
