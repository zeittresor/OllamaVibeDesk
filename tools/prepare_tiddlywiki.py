"""Validate or atomically download the optional offline TiddlyWiki template."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import requests

DEFAULT_URL = "https://tiddlywiki.com/empty.html"
MAX_BYTES = 20 * 1024 * 1024
MIN_BYTES = 100_000


def valid_template_bytes(data: bytes) -> bool:
    if not (MIN_BYTES <= len(data) <= MAX_BYTES):
        return False
    sample = data.lower()
    return b"tiddlywiki-tiddler-store" in sample and (b"$:/boot/boot.js" in sample or b"$:/boot" in sample)


def valid_template(path: Path) -> bool:
    try:
        return valid_template_bytes(Path(path).read_bytes())
    except OSError:
        return False


def prepare_template(target: Path, url: str = DEFAULT_URL) -> tuple[bool, str]:
    target = Path(target)
    if valid_template(target):
        return True, "The cached TiddlyWiki template is valid."
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    try:
        with requests.get(url, stream=True, timeout=(10, 30)) as response:
            response.raise_for_status()
            total = 0
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=128 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError("TiddlyWiki download exceeds the safety limit")
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        if not valid_template(temporary):
            raise ValueError("Downloaded file is not a valid TiddlyWiki template")
        temporary.replace(target)
        return True, "Blank TiddlyWiki template cached successfully."
    except (OSError, ValueError, requests.RequestException) as exc:
        temporary.unlink(missing_ok=True)
        return False, f"The optional TiddlyWiki template could not be prepared: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()
    success, message = prepare_template(args.target, args.url)
    print(message)
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
