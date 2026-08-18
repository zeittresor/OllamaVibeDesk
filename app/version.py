from __future__ import annotations

from pathlib import Path


VERSION_FILE = Path(__file__).resolve().parent.parent / "version.txt"
FALLBACK_VERSION = "2.2.0"


def read_version() -> str:
    """Return the normalized application version from the central version file."""
    try:
        value = VERSION_FILE.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return FALLBACK_VERSION
    if value.lower().startswith("v"):
        value = value[1:].strip()
    parts = value.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return FALLBACK_VERSION
    return ".".join(str(int(part)) for part in parts)


VERSION = read_version()
DISPLAY_VERSION = f"v{VERSION}"
