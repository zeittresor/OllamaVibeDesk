from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANG_DIR = ROOT / "lang"


def main() -> int:
    files = sorted(LANG_DIR.glob("*.json"))
    if not files:
        print("No language files found")
        return 1
    packs = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in files}
    reference = packs.get("en") or next(iter(packs.values()))
    expected = set(reference)
    failed = False
    for code, pack in packs.items():
        missing = sorted(expected - set(pack))
        extra = sorted(set(pack) - expected)
        if missing or extra:
            failed = True
        untranslated = 0
        if code != "en":
            untranslated = sum(
                1 for key, value in pack.items()
                if key in reference and value == reference[key] and isinstance(value, str) and len(value.strip()) > 2 and key != "app_title"
            )
        print(f"{code}: {len(pack)} keys; missing={len(missing)} extra={len(extra)} english-identical={untranslated}")
        if missing:
            print("  missing:", ", ".join(missing))
        if extra:
            print("  extra:", ", ".join(extra))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
