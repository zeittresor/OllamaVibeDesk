"""Installer model offer against a local fake Ollama API; no network download."""
from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DEFAULT_CONFIG, PREFERRED_OLLAMA_MODEL, normalize_config
from app.main import TOKEN_PRESET_VALUES, format_token_value
from tools import optional_default_model


class FakeOllama(BaseHTTPRequestHandler):
    models: set[str] = set()
    pulls = 0

    def log_message(self, *_args):
        pass

    def do_GET(self):
        assert self.path == '/api/tags'
        body = json.dumps({'models': [{'name': model} for model in self.models]}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        assert self.path == '/api/pull'
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert payload == {'model': PREFERRED_OLLAMA_MODEL, 'stream': True}
        self.__class__.pulls += 1
        self.__class__.models.add(PREFERRED_OLLAMA_MODEL)
        body = b'{"status":"downloading","total":10,"completed":10}\n{"status":"success"}\n'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class DefaultModelTests(unittest.TestCase):
    def test_defaults_and_user_settings(self):
        self.assertEqual(DEFAULT_CONFIG['last_model'], PREFERRED_OLLAMA_MODEL)
        self.assertEqual(DEFAULT_CONFIG['chat_max_tokens'], 65536)
        self.assertEqual((DEFAULT_CONFIG['auto_answer_eliza_share'],
                          DEFAULT_CONFIG['auto_answer_llm_share']), (15, 50))
        self.assertEqual(TOKEN_PRESET_VALUES[-1], 1000000)
        self.assertEqual(format_token_value(1000000), '1M')
        configured = normalize_config({'last_model': 'existing:local', 'chat_max_tokens': 1000000,
                                       'auto_answer_eliza_share': 5, 'auto_answer_llm_share': 25})
        self.assertEqual(configured['last_model'], 'existing:local')
        self.assertEqual(configured['chat_max_tokens'], 1000000)
        self.assertEqual((configured['auto_answer_eliza_share'], configured['auto_answer_llm_share']), (5, 25))

    def test_offer_only_pulls_after_confirmation_and_if_missing(self):
        FakeOllama.models = {'existing:local'}
        FakeOllama.pulls = 0
        server = ThreadingHTTPServer(('127.0.0.1', 0), FakeOllama)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            for action, expected in (('--check', 1), ('--pull', 0), ('--check', 0), ('--pull', 0)):
                with self.subTest(action=action, expected=expected), patch.object(sys, 'argv', ['offer', action, '--base-url', url]):
                    self.assertEqual(optional_default_model.main(), expected)
            self.assertEqual(FakeOllama.pulls, 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_remote_ollama_is_never_used_by_installer(self):
        with patch.object(sys, 'argv', ['offer', '--pull', '--base-url', 'https://other.example:11434']):
            self.assertEqual(optional_default_model.main(), 2)


if __name__ == '__main__':
    unittest.main()
