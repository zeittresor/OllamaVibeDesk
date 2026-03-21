from __future__ import annotations

import json
from pathlib import Path
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
    for candidate in [code or '', 'de', 'en']:
        if not candidate:
            continue
        path = LANG_DIR / f'{candidate}.json'
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
            except Exception:
                continue
    return {}
