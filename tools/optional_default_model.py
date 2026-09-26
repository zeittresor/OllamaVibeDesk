"""Offer the preferred model only on a reachable local Ollama installation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

from app.config import PREFERRED_OLLAMA_MODEL, load_config
from app.ollama_client import OllamaClient


def local_ollama_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'} or not parsed.port:
        raise ValueError('The model offer requires a local Ollama HTTP endpoint.')
    return value.rstrip('/')


def installed(base_url: str) -> bool:
    return PREFERRED_OLLAMA_MODEL.casefold() in {
        name.casefold() for name in OllamaClient(base_url).get_models()
    }


def pull(base_url: str) -> None:
    if installed(base_url):
        print('The recommended model is already installed.', flush=True)
        return
    print(f'Downloading {PREFERRED_OLLAMA_MODEL} (about 13.5 GB) ...', flush=True)
    last_progress = -5
    with requests.post(base_url + '/api/pull', json={'model': PREFERRED_OLLAMA_MODEL, 'stream': True},
                       stream=True, timeout=(8, 180)) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            event = json.loads(line)
            if event.get('error'):
                raise RuntimeError(str(event['error']))
            total = int(event.get('total') or 0)
            if total:
                percent = min(100, int(100 * int(event.get('completed') or 0) / total))
                if percent >= last_progress + 5:
                    print(f'Model download: {percent}%', flush=True)
                    last_progress = percent
            elif event.get('status'):
                print(f"Model: {event['status']}", flush=True)
    if not installed(base_url):
        raise RuntimeError('The download finished, but Ollama did not list the model.')
    print('The recommended model is ready.', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--pull', action='store_true')
    parser.add_argument('--base-url', default='')
    args = parser.parse_args()
    if args.check == args.pull:
        parser.error('Specify exactly one of --check or --pull.')
    try:
        url = local_ollama_url(args.base_url or load_config()['ollama_base_url'])
        if args.check:
            present = installed(url)
            print('Recommended model present.' if present else 'Recommended model missing.')
            return 0 if present else 1
        pull(url)
        return 0
    except (ValueError, RuntimeError, requests.RequestException, json.JSONDecodeError) as exc:
        print(f'Recommended model unavailable: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
