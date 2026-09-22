from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ollama_client import OllamaClient


class _Handler(BaseHTTPRequestHandler):
    requests_seen: ClassVar[list[dict]] = []

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - HTTP handler API
        length = int(self.headers.get("Content-Length", "0") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.requests_seen.append(payload)
        think = payload.get("think", "missing")
        if isinstance(think, str):
            self._send_json(400, {"error": 'invalid think value (boolean required by this test runtime)'})
            return
        if payload.get("stream", True):
            body = (
                json.dumps({"message": {"thinking": "checked", "content": ""}}) + "\n" +
                json.dumps({"message": {"content": "ready"}, "done": True}) + "\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._send_json(200, {"message": {"content": "off-ready"}, "done": True})


def main() -> int:
    _Handler.requests_seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        client = OllamaClient(base_url)
        chunks = list(client.stream_chat("test-model", [{"role": "user", "content": "test"}], think="high"))
        assert [request.get("think", "missing") for request in _Handler.requests_seen[:2]] == ["high", True]
        assert "".join(chunk.get("thinking", "") for chunk in chunks) == "checked"
        assert "".join(chunk.get("content", "") for chunk in chunks) == "ready"

        result = client.chat_once("test-model", [{"role": "user", "content": "test"}], think="off")
        assert result == "off-ready"
        assert _Handler.requests_seen[-1].get("think", "missing") is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    print("Ollama reasoning API smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
