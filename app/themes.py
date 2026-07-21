from __future__ import annotations

import json

from app.config import THEMES_DIR


def load_themes() -> dict[str, str]:
    result: dict[str, str] = {}
    if THEMES_DIR.exists():
        for path in sorted(THEMES_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            name = str(data.get("name") or path.stem).strip()
            qss = str(data.get("qss") or "").strip()
            if name and qss:
                result[name] = qss
    if not result:
        result["Dark"] = "QWidget { background: #111318; color: #f2f4f7; }"
    return result


THEMES = load_themes()
