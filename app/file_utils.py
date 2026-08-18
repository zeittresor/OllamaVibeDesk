from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write a text file atomically in the destination directory.

    The temporary file lives beside the target so os.replace stays atomic on the
    same filesystem. This avoids half-written config/session JSON after a crash.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write binary data atomically beside the destination file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def backup_file(path: Path, *, label: str = "corrupt") -> Path | None:
    source = Path(path)
    if not source.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = source.with_name(f"{source.stem}.{label}.{stamp}{source.suffix}")
    try:
        shutil.copy2(source, backup)
        return backup
    except Exception:
        return None
