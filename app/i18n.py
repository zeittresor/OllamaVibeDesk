from __future__ import annotations

import json
from typing import Dict, List, Tuple

from app.config import LANG_DIR


def available_languages() -> List[Tuple[str, str]]:
    items: List[Tuple[str, str]] = []
    if LANG_DIR.exists():
        for path in sorted(LANG_DIR.glob('*.json')):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            display = data.get('language_name') or path.stem
            items.append((path.stem, str(display)))
    if not items:
        items = [('de', 'Deutsch')]
    items.sort(key=lambda x: (x[0] != 'de', x[1].lower()))
    return items


def load_language_pack(code: str) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    base_path = LANG_DIR / 'en.json'
    if base_path.exists():
        try:
            data = json.loads(base_path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                merged.update({str(k): str(v) for k, v in data.items()})
        except Exception:
            pass
    selected = (code or '').strip()
    if selected:
        path = LANG_DIR / f'{selected}.json'
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, dict):
                    merged.update({str(k): str(v) for k, v in data.items()})
            except Exception:
                pass
    if not merged:
        fallback = LANG_DIR / 'de.json'
        if fallback.exists():
            try:
                data = json.loads(fallback.read_text(encoding='utf-8'))
                if isinstance(data, dict):
                    merged.update({str(k): str(v) for k, v in data.items()})
            except Exception:
                pass
    return merged
