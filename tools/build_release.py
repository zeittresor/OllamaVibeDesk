"""Reproducible source ZIP. Runtime data, credentials and environments are excluded."""
from __future__ import annotations
import argparse
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'release')
    parser.add_argument('--source-only', action='store_true', help='Only syntax/assets; does not certify installation.')
    args = parser.parse_args()
    command = [sys.executable, str(ROOT/'tools/verify_installation.py')]
    if args.source_only: command.append('--source-only')
    subprocess.run(command, cwd=ROOT, check=True)
    version = (ROOT/'version.txt').read_text().strip()
    name = f'OllamaVibeDesk_v{version}'
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / (name+'.zip')
    temp = target.with_suffix('.zip.tmp')
    paths = []
    for folder in ('app','tools','tests','resources','lang','themes'):
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.pyo'})
    paths.extend(p for p in ROOT.iterdir() if p.is_file() and (p.suffix.lower() in {'.md','.bat','.txt'}))
    try:
        with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for path in sorted(set(paths)):
                item = zipfile.ZipInfo(name+'/'+path.relative_to(ROOT).as_posix(), (2026,9,21,0,0,0))
                item.compress_type = zipfile.ZIP_DEFLATED
                item.external_attr = 0o100644 << 16
                archive.writestr(item, path.read_bytes())
        with zipfile.ZipFile(temp) as archive:
            if archive.testzip(): raise RuntimeError('ZIP integrity failure')
            assert not any('/app_data/' in p or '/.venv/' in p for p in archive.namelist())
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {target.name}\n')
    print(f'{target}\nSHA-256: {digest}\nFiles: {len(paths)}')
    return 0

if __name__ == '__main__': raise SystemExit(main())
