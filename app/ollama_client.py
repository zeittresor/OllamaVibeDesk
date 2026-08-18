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
        raw_models = data.get('models', []) if isinstance(data, dict) else []
        models = [str(item.get('name', '')).strip() for item in raw_models if isinstance(item, dict) and item.get('name')]
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
        think: bool = False,
    ) -> dict:
        payload = {
            'model': model,
            'messages': messages,
            'stream': stream,
            'keep_alive': keep_alive,
            'think': bool(think),
        }
        if options:
            payload['options'] = options
        if system_prompt.strip():
            payload['messages'] = [{'role': 'system', 'content': system_prompt.strip()}] + messages
        return payload

    @staticmethod
    def _extract_parts(data: dict) -> tuple[str, str]:
        message = data.get('message') or {}
        content_parts = [
            message.get('content', ''),
            data.get('response', ''),
        ]
        thinking_parts = [
            message.get('thinking', ''),
            data.get('thinking', ''),
        ]
        content = ''.join(part for part in content_parts if isinstance(part, str) and part)
        thinking = ''.join(part for part in thinking_parts if isinstance(part, str) and part)
        return content, thinking

    def chat_once(
        self,
        model: str,
        messages: List[dict],
        system_prompt: str = '',
        keep_alive: str = '10m',
        options: Optional[dict] = None,
        timeout: int = 600,
        think: bool = False,
    ) -> str:
        payload = self._payload(model, messages, system_prompt, keep_alive, options, stream=False, think=think)
        response = requests.post(
            self._url('/api/chat'),
            json=payload,
            timeout=(10, timeout),
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get('error'):
            raise RuntimeError(f"Ollama error: {data.get('error')}")
        content, _thinking = self._extract_parts(data)
        return content.strip()

    def stream_chat(
        self,
        model: str,
        messages: List[dict],
        system_prompt: str = '',
        keep_alive: str = '10m',
        options: Optional[dict] = None,
        timeout: int = 600,
        think: bool = False,
    ) -> Iterable[dict]:
        payload = self._payload(model, messages, system_prompt, keep_alive, options, stream=True, think=think)
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
                try:
                    data = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    preview = str(raw_line)[:240]
                    raise RuntimeError(f"Ollama returned an invalid streaming response: {preview}") from exc
                if not isinstance(data, dict):
                    continue
                if data.get('error'):
                    raise RuntimeError(f"Ollama error: {data.get('error')}")
                content, thinking = self._extract_parts(data)
                if content or thinking:
                    emitted_any = True
                    yield {'content': content, 'thinking': thinking}
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
                think=think,
            )
            if fallback:
                yield {'content': fallback, 'thinking': ''}
