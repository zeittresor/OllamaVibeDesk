from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional

import requests


class OllamaClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip('/')

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def get_models(self) -> List[str]:
        response = requests.get(self._url('/api/tags'), timeout=8)
        response.raise_for_status()
        data = response.json()
        models = [item.get('name', '') for item in data.get('models', []) if item.get('name')]
        return sorted(models)

    def status(self) -> Dict[str, str]:
        try:
            models = self.get_models()
            return {
                'ok': 'true',
                'message': f"Ollama erreichbar ({len(models)} Modelle)",
            }
        except Exception as exc:
            return {
                'ok': 'false',
                'message': f"Ollama nicht erreichbar: {exc}",
            }

    def _payload(
        self,
        model: str,
        messages: List[dict],
        system_prompt: str = '',
        keep_alive: str = '10m',
        options: Optional[dict] = None,
        stream: bool = True,
    ) -> dict:
        payload = {
            'model': model,
            'messages': messages,
            'stream': stream,
            'keep_alive': keep_alive,
            'think': False,
        }
        if options:
            payload['options'] = options
        if system_prompt.strip():
            payload['messages'] = [{'role': 'system', 'content': system_prompt.strip()}] + messages
        return payload

    @staticmethod
    def _extract_text(data: dict) -> str:
        message = data.get('message') or {}
        parts = [
            message.get('content', ''),
            data.get('response', ''),
            message.get('thinking', ''),
            data.get('thinking', ''),
        ]
        return ''.join(part for part in parts if isinstance(part, str) and part)

    def chat_once(
        self,
        model: str,
        messages: List[dict],
        system_prompt: str = '',
        keep_alive: str = '10m',
        options: Optional[dict] = None,
        timeout: int = 600,
    ) -> str:
        payload = self._payload(model, messages, system_prompt, keep_alive, options, stream=False)
        response = requests.post(
            self._url('/api/chat'),
            json=payload,
            timeout=(10, timeout),
        )
        response.raise_for_status()
        data = response.json()
        return self._extract_text(data).strip()

    def stream_chat(
        self,
        model: str,
        messages: List[dict],
        system_prompt: str = '',
        keep_alive: str = '10m',
        options: Optional[dict] = None,
        timeout: int = 600,
    ) -> Iterable[str]:
        payload = self._payload(model, messages, system_prompt, keep_alive, options, stream=True)
        emitted_any = False

        with requests.post(
            self._url('/api/chat'),
            json=payload,
            stream=True,
            timeout=(10, timeout),
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                data = json.loads(raw_line)
                text = self._extract_text(data)
                if text:
                    emitted_any = True
                    yield text
                if data.get('done'):
                    break

        if not emitted_any:
            fallback = self.chat_once(
                model=model,
                messages=messages,
                system_prompt=system_prompt,
                keep_alive=keep_alive,
                options=options,
                timeout=timeout,
            )
            if fallback:
                yield fallback
