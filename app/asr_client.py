from __future__ import annotations

import json
from pathlib import Path

import requests


class ASRClient:
    """OpenAI-compatible speech-to-text client with strict response checks."""

    def __init__(self, base_url: str, model: str, language: str = "auto") -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.model = str(model or "").strip()
        self.language = str(language or "auto").strip().lower() or "auto"

    def transcribe(self, audio_path: Path, timeout: int = 1800) -> str:
        path = Path(audio_path)
        if not path.is_file() or path.stat().st_size <= 44:
            raise RuntimeError("Die Mikrofonaufnahme ist leer oder keine gültige WAV-Datei.")
        if not self.base_url.startswith(("http://", "https://")):
            raise RuntimeError("Die ASR-URL ist ungültig.")

        data = {"model": self.model, "response_format": "json"}
        if self.language != "auto":
            data["language"] = self.language
        with path.open("rb") as handle:
            response = requests.post(
                f"{self.base_url}/audio/transcriptions",
                data=data,
                files={"file": (path.name, handle, "audio/wav")},
                timeout=timeout,
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            preview = response.text[:800].strip()
            raise RuntimeError(f"ASR-Anfrage fehlgeschlagen ({response.status_code}): {preview}") from exc

        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Das ASR-Backend lieferte keine gültige JSON-Antwort.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Das ASR-Backend lieferte ein unerwartetes Antwortformat.")
        error = payload.get("error")
        if error:
            if isinstance(error, dict):
                error = error.get("message") or json.dumps(error, ensure_ascii=False)
            raise RuntimeError(f"ASR-Backendfehler: {error}")
        text = payload.get("text")
        if not isinstance(text, str):
            raise RuntimeError("Die ASR-Antwort enthält kein Textfeld.")
        return text.strip()
