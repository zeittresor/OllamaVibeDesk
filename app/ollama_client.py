from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional

import requests

from app.reasoning import ollama_think_value
from app.plugin_tools import encode_image


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
        think: bool | str | None = False,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        payload = {
            'model': model,
            'messages': messages,
            'stream': stream,
            'keep_alive': keep_alive,
        }
        if think is not None:
            payload['think'] = think if isinstance(think, bool) else ollama_think_value(think)
        if options:
            payload['options'] = options
        if tools:
            payload['tools'] = tools
        clean_messages = []
        for entry in messages:
            copy = dict(entry)
            paths = copy.pop('images_paths', [])
            if paths:
                copy['images'] = [encode_image(path) for path in paths]
            clean_messages.append(copy)
        payload['messages'] = ([{'role': 'system', 'content': system_prompt.strip()}] if system_prompt.strip() else []) + clean_messages
        return payload

    @staticmethod
    def _response_error_text(response: requests.Response) -> str:
        try:
            data = response.json()
        except Exception:
            data = None
        if isinstance(data, dict):
            for key in ('error', 'message', 'detail'):
                value = data.get(key)
                if value:
                    return str(value)
        return str(getattr(response, 'text', '') or '')[:2000]

    @classmethod
    def _is_thinking_compatibility_error(cls, response: requests.Response) -> bool:
        if int(getattr(response, 'status_code', 0) or 0) not in {400, 404, 422, 500}:
            return False
        text = cls._response_error_text(response).lower()
        return any(word in text for word in ('think', 'thinking', 'reasoning')) and any(
            word in text for word in ('unsupported', 'not support', 'invalid', 'boolean', 'unknown field', 'cannot unmarshal', 'must be'))

    @staticmethod
    def _think_fallback_attempts(think: bool | str | None) -> list[bool | str | None]:
        if isinstance(think, str) and think.strip().lower() in {'low', 'medium', 'high'}:
            # Older Ollama releases and some model templates only understand a
            # boolean. If that is unsupported too, omit the field entirely.
            return [think.strip().lower(), True, None]
        if think is True:
            return [True, None]
        if think is False:
            return [False, None]
        return [None]

    def _post_with_thinking_fallback(
        self,
        payload: dict,
        *,
        stream: bool,
        timeout: tuple[int, int],
    ) -> requests.Response:
        original_think = payload.get('think') if 'think' in payload else None
        attempts = self._think_fallback_attempts(original_think)
        last_response: requests.Response | None = None
        for attempt_index, think_value in enumerate(attempts):
            request_payload = dict(payload)
            if think_value is None:
                request_payload.pop('think', None)
            else:
                request_payload['think'] = think_value
            response = requests.post(
                self._url('/api/chat'),
                json=request_payload,
                stream=stream,
                timeout=timeout,
            )
            last_response = response
            if response.status_code < 400:
                return response
            has_fallback = attempt_index + 1 < len(attempts)
            if not has_fallback or not self._is_thinking_compatibility_error(response):
                return response
            response.close()
        if last_response is None:  # Defensive; attempts always contains one item.
            raise RuntimeError('Ollama request could not be created')
        return last_response

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

    def chat_response(self, model: str, messages: List[dict], system_prompt: str = '',
                      options: Optional[dict] = None, timeout: int = 600,
                      think: bool | str | None = False, tools: Optional[list[dict]] = None) -> dict:
        payload = self._payload(model, messages, system_prompt, options=options, stream=False, think=think, tools=tools)
        response = self._post_with_thinking_fallback(payload, stream=False, timeout=(10, timeout))
        try:
            if response.status_code >= 400:
                raise RuntimeError(f"Ollama HTTP {response.status_code}: {self._response_error_text(response)}")
            data = response.json()
        finally:
            response.close()
        if not isinstance(data, dict) or data.get('error'):
            raise RuntimeError(f"Ollama error: {data.get('error') if isinstance(data, dict) else 'invalid response'}")
        return data

    def chat_once(
        self,
        model: str,
        messages: List[dict],
        system_prompt: str = '',
        keep_alive: str = '10m',
        options: Optional[dict] = None,
        timeout: int = 600,
        think: bool | str | None = False,
    ) -> str:
        payload = self._payload(model, messages, system_prompt, keep_alive, options, stream=False, think=think)
        response = self._post_with_thinking_fallback(payload, stream=False, timeout=(10, timeout))
        try:
            if response.status_code >= 400:
                raise RuntimeError(f"Ollama HTTP {response.status_code}: {self._response_error_text(response)}")
            data = response.json()
        finally:
            response.close()
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
        think: bool | str | None = False,
    ) -> Iterable[dict]:
        payload = self._payload(model, messages, system_prompt, keep_alive, options, stream=True, think=think)
        emitted_any = False
        completed = False

        response = self._post_with_thinking_fallback(payload, stream=True, timeout=(10, timeout))
        with response:
            if response.status_code >= 400:
                raise RuntimeError(f"Ollama HTTP {response.status_code}: {self._response_error_text(response)}")
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
                    completed = True
                    stats = {k: data[k] for k in ('prompt_eval_count', 'eval_count', 'total_duration', 'load_duration', 'done_reason') if k in data}
                    if stats:
                        yield {'content': '', 'thinking': '', 'stats': stats}
                    break
        if not completed:
            raise RuntimeError("Ollama stream ended before completion; any partial answer has been kept.")
        if not emitted_any:
            raise RuntimeError("Ollama returned no answer content.")
