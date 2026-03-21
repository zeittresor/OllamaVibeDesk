from __future__ import annotations

import base64
import locale
import os
import subprocess
from pathlib import Path
from typing import List

import requests


class TTSClient:
    def __init__(self, backend: str, base_url: str, voice: str, model: str, audio_format: str = 'wav') -> None:
        self.backend = (backend or 'disabled').strip()
        self.base_url = base_url.rstrip('/')
        self.voice = voice
        self.model = model
        self.audio_format = audio_format.lower().strip() or 'wav'

    def enabled(self) -> bool:
        return self.backend in {'vibevoice_openai', 'windows_sapi'}

    def _decode_output(self, data: bytes) -> str:
        if not data:
            return ''
        candidates = []
        pref = locale.getpreferredencoding(False)
        if pref:
            candidates.append(pref)
        candidates += ['utf-8', 'cp1252', 'cp850', 'latin-1']
        seen = set()
        for enc in candidates:
            key = enc.lower()
            if key in seen:
                continue
            seen.add(key)
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode('utf-8', errors='replace')

    def _run_powershell(self, script: str, extra_env: dict[str, str] | None = None, timeout: int = 300):
        if os.name != 'nt':
            raise RuntimeError("Das Backend 'windows_sapi' ist nur unter Windows verfügbar.")
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded],
            capture_output=True,
            text=False,
            env=env,
            timeout=timeout,
        )
        result.stdout_text = self._decode_output(result.stdout)
        result.stderr_text = self._decode_output(result.stderr)
        return result

    def _list_windows_sapi_voices(self) -> List[str]:
        script = r"""
Add-Type -AssemblyName System.Speech
$tts = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $tts.GetInstalledVoices() |
        ForEach-Object { $_.VoiceInfo.Name } |
        Sort-Object -Unique |
        ForEach-Object { Write-Output $_ }
}
finally {
    $tts.Dispose()
}
"""
        result = self._run_powershell(script, timeout=60)
        if result.returncode != 0:
            msg = (result.stderr_text or result.stdout_text or 'Unbekannter PowerShell-Fehler').strip()
            raise RuntimeError(f'Windows-TTS-Stimmen konnten nicht gelesen werden: {msg}')
        return [line.strip() for line in result.stdout_text.splitlines() if line.strip()]

    def list_voices(self) -> List[str]:
        if self.backend == 'windows_sapi':
            return self._list_windows_sapi_voices()

        if self.backend != 'vibevoice_openai':
            return []

        response = requests.get(f'{self.base_url}/audio/voices', timeout=10)
        response.raise_for_status()
        data = response.json()
        voices: List[str] = []

        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    voices.append(item)
                elif isinstance(item, dict):
                    name = item.get('name') or item.get('voice')
                    if name:
                        voices.append(name)
        elif isinstance(data, dict):
            items = data.get('data') or data.get('voices') or []
            for item in items:
                if isinstance(item, str):
                    voices.append(item)
                elif isinstance(item, dict):
                    name = item.get('name') or item.get('voice')
                    if name:
                        voices.append(name)

        return sorted(set(voices))

    def _synthesize_windows_sapi_to_file(self, text: str, output_path: Path) -> Path:
        if os.name != 'nt':
            raise RuntimeError("Das Backend 'windows_sapi' ist nur unter Windows verfügbar.")
        if output_path.suffix.lower() != '.wav':
            output_path = output_path.with_suffix('.wav')

        output_path.parent.mkdir(parents=True, exist_ok=True)
        env = {
            'OVD_TTS_TEXT': text,
            'OVD_TTS_OUT': str(output_path),
            'OVD_TTS_VOICE': self.voice or '',
        }
        script = r"""
Add-Type -AssemblyName System.Speech
$text = $env:OVD_TTS_TEXT
$out = $env:OVD_TTS_OUT
$voice = $env:OVD_TTS_VOICE
if ([string]::IsNullOrWhiteSpace($text)) { throw 'Kein Text zum Vorlesen übergeben.' }
if ([string]::IsNullOrWhiteSpace($out)) { throw 'Kein Ausgabe-Pfad übergeben.' }
$tts = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    if (-not [string]::IsNullOrWhiteSpace($voice)) {
        $available = $tts.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }
        if ($available -contains $voice) {
            $tts.SelectVoice($voice)
        }
    }
    $parent = Split-Path -Parent $out
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $tts.SetOutputToWaveFile($out)
    $tts.Speak($text)
    $tts.SetOutputToNull()
    Write-Output 'OK'
}
finally {
    $tts.Dispose()
}
"""
        result = self._run_powershell(script, extra_env=env, timeout=600)
        if result.returncode != 0:
            msg = (result.stderr_text or result.stdout_text or 'Unbekannter PowerShell-Fehler').strip()
            raise RuntimeError(f'Windows-TTS-Erzeugung fehlgeschlagen: {msg}')
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError('Windows-TTS hat keine gültige WAV-Datei erzeugt.')
        return output_path

    def synthesize_to_file(self, text: str, output_path: Path) -> Path:
        if self.backend == 'windows_sapi':
            return self._synthesize_windows_sapi_to_file(text, output_path)

        if self.backend != 'vibevoice_openai':
            raise RuntimeError('TTS backend is disabled.')

        payload = {
            'model': self.model,
            'input': text,
            'voice': self.voice,
            'response_format': self.audio_format,
            'format': self.audio_format,
        }

        response = requests.post(
            f'{self.base_url}/audio/speech',
            json=payload,
            timeout=300,
        )
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return output_path
