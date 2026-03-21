from __future__ import annotations

import base64
import locale
import os
import subprocess
from pathlib import Path
from typing import List, Tuple

import requests


class TTSClient:
    def __init__(
        self,
        backend: str,
        base_url: str,
        voice: str,
        model: str,
        audio_format: str = 'wav',
        windows_sapi_rate: int = 0,
        windows_sapi_pitch: int = 0,
        windows_sapi_volume: int = 100,
        windows_sapi_language: str = 'de-DE',
    ) -> None:
        self.backend = (backend or 'disabled').strip()
        self.base_url = base_url.rstrip('/')
        self.voice = (voice or '').strip()
        self.model = model
        self.audio_format = audio_format.lower().strip() or 'wav'
        self.windows_sapi_rate = int(windows_sapi_rate)
        self.windows_sapi_pitch = int(windows_sapi_pitch)
        self.windows_sapi_volume = int(windows_sapi_volume)
        self.windows_sapi_language = windows_sapi_language or 'de-DE'

    def enabled(self) -> bool:
        return self.backend in {'vibevoice_openai', 'windows_sapi'}

    @staticmethod
    def make_sapi_voice_id(name: str) -> str:
        return f"sapi::{name.strip()}"

    @staticmethod
    def make_onecore_voice_id(voice_id: str) -> str:
        return f"onecore::{voice_id.strip()}"

    @staticmethod
    def parse_windows_voice(value: str) -> tuple[str, str]:
        raw = (value or '').strip()
        if raw.startswith('onecore::'):
            return 'onecore', raw.split('::', 1)[1]
        if raw.startswith('sapi::'):
            return 'sapi', raw.split('::', 1)[1]
        return 'sapi', raw

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
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Sta', '-EncodedCommand', encoded],
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

    def _list_windows_oncore_voices(self) -> List[tuple[str, str]]:
        script = r"""
$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'
try {
    $cat = New-Object -ComObject SAPI.SpObjectTokenCategory
    $cat.SetId('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices')
    $tokens = $cat.EnumerateTokens()
    for ($i = 0; $i -lt $tokens.Count; $i++) {
        $tok = $tokens.Item($i)
        $desc = $tok.GetDescription()
        if ([string]::IsNullOrWhiteSpace($desc)) { $desc = $tok.Id }
        Write-Output ($desc + "`t" + $tok.Id)
    }
}
catch {
    exit 0
}
"""
        result = self._run_powershell(script, timeout=60)
        if result.returncode != 0:
            return []
        items: List[tuple[str, str]] = []
        for line in result.stdout_text.splitlines():
            parts = [part.strip() for part in line.split('	')]
            if len(parts) >= 2 and parts[1]:
                items.append((parts[1], parts[0]))
        return items

    def list_voice_entries(self) -> List[Tuple[str, str]]:
        if self.backend == 'windows_sapi':
            entries: List[Tuple[str, str]] = []
            seen = set()
            for name in self._list_windows_sapi_voices():
                value = self.make_sapi_voice_id(name)
                label = f"{name} [Desktop SAPI]"
                entries.append((value, label))
                seen.add(('sapi', name.casefold()))
            for voice_id, label in self._list_windows_oncore_voices():
                key = ('onecore', voice_id.casefold())
                if key in seen:
                    continue
                entries.append((self.make_onecore_voice_id(voice_id), f"{label} [Windows Voice]"))
                seen.add(key)
            return entries

        return [(voice, voice) for voice in self.list_voices()]

    def list_voices(self) -> List[str]:
        if self.backend == 'windows_sapi':
            return [label for _value, label in self.list_voice_entries()]

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
        voice_type, voice_value = self.parse_windows_voice(self.voice)
        if voice_type == 'onecore':
            return self._synthesize_windows_oncore_to_file(text, output_path, voice_value)

        env = {
            'OVD_TTS_TEXT': text,
            'OVD_TTS_OUT': str(output_path),
            'OVD_TTS_VOICE': voice_value or '',
            'OVD_TTS_RATE': str(self.windows_sapi_rate),
            'OVD_TTS_PITCH': str(self.windows_sapi_pitch),
            'OVD_TTS_VOLUME': str(self.windows_sapi_volume),
            'OVD_TTS_LANG': self.windows_sapi_language,
        }
        script = r"""
$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
Add-Type -AssemblyName System.Security
$text = $env:OVD_TTS_TEXT
$out = $env:OVD_TTS_OUT
$voice = $env:OVD_TTS_VOICE
$lang = if ([string]::IsNullOrWhiteSpace($env:OVD_TTS_LANG)) { 'de-DE' } else { $env:OVD_TTS_LANG }
$rate = 0
$pitch = 0
$volume = 100
[int]::TryParse($env:OVD_TTS_RATE, [ref]$rate) | Out-Null
[int]::TryParse($env:OVD_TTS_PITCH, [ref]$pitch) | Out-Null
[int]::TryParse($env:OVD_TTS_VOLUME, [ref]$volume) | Out-Null
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
    $tts.Rate = [Math]::Max(-10, [Math]::Min(10, $rate))
    $tts.Volume = [Math]::Max(0, [Math]::Min(100, $volume))
    $parent = Split-Path -Parent $out
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $tts.SetOutputToWaveFile($out)
    $escaped = [System.Security.SecurityElement]::Escape($text)
    $pitchPct = [Math]::Max(-50, [Math]::Min(50, $pitch * 5))
    $pitchAttr = if ($pitchPct -ge 0) { "+${pitchPct}%" } else { "${pitchPct}%" }
    $ssmlInner = "<prosody pitch='$pitchAttr'>$escaped</prosody>"
    if (-not [string]::IsNullOrWhiteSpace($voice)) {
        $voiceEsc = [System.Security.SecurityElement]::Escape($voice)
        $ssmlInner = "<voice name='$voiceEsc'>$ssmlInner</voice>"
    }
    $ssml = "<speak version='1.0' xml:lang='$lang' xmlns='http://www.w3.org/2001/10/synthesis'>$ssmlInner</speak>"
    try {
        $tts.SpeakSsml($ssml)
    }
    catch {
        $tts.Speak($text)
    }
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

    def _synthesize_windows_oncore_to_file(self, text: str, output_path: Path, voice_id: str) -> Path:
        env = {
            'OVD_TTS_TEXT': text,
            'OVD_TTS_OUT': str(output_path),
            'OVD_TTS_VOICE_ID': voice_id,
            'OVD_TTS_RATE': str(self.windows_sapi_rate),
            'OVD_TTS_PITCH': str(self.windows_sapi_pitch),
            'OVD_TTS_VOLUME': str(self.windows_sapi_volume),
            'OVD_TTS_LANG': self.windows_sapi_language,
        }
        script = r"""
$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'
$text = $env:OVD_TTS_TEXT
$out = $env:OVD_TTS_OUT
$voiceId = $env:OVD_TTS_VOICE_ID
$rate = 0
$pitch = 0
$volume = 100
[int]::TryParse($env:OVD_TTS_RATE, [ref]$rate) | Out-Null
[int]::TryParse($env:OVD_TTS_PITCH, [ref]$pitch) | Out-Null
[int]::TryParse($env:OVD_TTS_VOLUME, [ref]$volume) | Out-Null
if ([string]::IsNullOrWhiteSpace($text)) { throw 'Kein Text zum Vorlesen übergeben.' }
if ([string]::IsNullOrWhiteSpace($out)) { throw 'Kein Ausgabe-Pfad übergeben.' }
$parent = Split-Path -Parent $out
if (-not [string]::IsNullOrWhiteSpace($parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
try {
    $cat = New-Object -ComObject SAPI.SpObjectTokenCategory
    $cat.SetId('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices')
    $tokens = $cat.EnumerateTokens()
    $token = $null
    for ($i = 0; $i -lt $tokens.Count; $i++) {
        $candidate = $tokens.Item($i)
        if ($candidate.Id -eq $voiceId) {
            $token = $candidate
            break
        }
    }
    if ($null -eq $token) { throw "Windows-Voice nicht gefunden: $voiceId" }

    $voice = New-Object -ComObject SAPI.SpVoice
    $stream = New-Object -ComObject SAPI.SpFileStream
    try {
        $voice.Voice = $token
        $voice.Rate = [Math]::Max(-10, [Math]::Min(10, $rate))
        $voice.Volume = [Math]::Max(0, [Math]::Min(100, $volume))
        $stream.Open($out, 3, $false)
        $voice.AudioOutputStream = $stream
        $speakText = $text
        $flags = 0
        if ($pitch -ne 0) {
            $escaped = $text.Replace('&', '&amp;').Replace('<', '&lt;').Replace('>', '&gt;')
            $sapiPitch = [Math]::Max(-10, [Math]::Min(10, $pitch))
            $speakText = "<pitch absmiddle='$sapiPitch'>$escaped</pitch>"
            $flags = 8
        }
        try {
            $null = $voice.Speak($speakText, $flags)
        }
        catch {
            if ($flags -ne 0) {
                $null = $voice.Speak($text, 0)
            }
            else {
                throw
            }
        }
        try { $voice.WaitUntilDone(30000) | Out-Null } catch {}
        try { $voice.AudioOutputStream = $null } catch {}
        try { $stream.Close() } catch {}
        Write-Output '__OVD_OK__'
        exit 0
    }
    finally {
        try { $voice.AudioOutputStream = $null } catch {}
        try { $stream.Close() } catch {}
    }
}
catch {
    Write-Error $_
    exit 1
}
"""
        result = self._run_powershell(script, extra_env=env, timeout=600)
        stdout = (result.stdout_text or '').strip()
        stderr = (result.stderr_text or '').strip()
        file_ok = output_path.exists() and output_path.stat().st_size > 44
        success_marker = '__OVD_OK__' in stdout
        if not file_ok and result.returncode != 0:
            msg = (stderr or stdout or 'Unbekannter PowerShell-Fehler').strip()
            raise RuntimeError(f'Windows-Voice-Erzeugung fehlgeschlagen: {msg}')
        if not file_ok:
            msg = (stderr or stdout or 'Windows-Voice hat keine gültige WAV-Datei erzeugt.').strip()
            raise RuntimeError(f'Windows-Voice-Erzeugung fehlgeschlagen: {msg}')
        if result.returncode != 0 and not success_marker:
            msg = (stderr or stdout or 'Unbekannter PowerShell-Fehler').strip()
            raise RuntimeError(f'Windows-Voice-Erzeugung fehlgeschlagen: {msg}')
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
