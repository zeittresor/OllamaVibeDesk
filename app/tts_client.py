from __future__ import annotations

import base64
import locale
import math
import os
import subprocess
import sys
import wave
from array import array
from pathlib import Path
from typing import List, Tuple

import requests

from .config import TTS_DIR
from .file_utils import atomic_write_bytes
from .tts_profiles import effective_voice_controls, normalize_voice_style


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
        voice_style: str = 'natural',
        voice_style_intensity: int = 65,
    ) -> None:
        self.backend = (backend or 'disabled').strip()
        self.base_url = base_url.rstrip('/')
        self.voice = (voice or '').strip()
        self.model = model
        self.audio_format = audio_format.lower().strip() or 'wav'
        self.voice_style = normalize_voice_style(voice_style)
        (
            self.windows_sapi_rate,
            self.windows_sapi_pitch,
            self.windows_sapi_volume,
            self.audio_effect,
            self.voice_style_intensity,
        ) = effective_voice_controls(
            self.voice_style,
            voice_style_intensity,
            windows_sapi_rate,
            windows_sapi_pitch,
            windows_sapi_volume,
        )
        self.windows_sapi_language = windows_sapi_language or 'de-DE'

    def enabled(self) -> bool:
        return self.backend in {'vibevoice_openai', 'crispasr_openai', 'windows_sapi'}

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
        run_kwargs = {
            'capture_output': True,
            'text': False,
            'env': env,
            'timeout': timeout,
        }
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 6
            run_kwargs['startupinfo'] = startupinfo
            run_kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        result = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Sta', '-EncodedCommand', encoded],
            **run_kwargs,
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

    @staticmethod
    def _language_name_from_code(code: str) -> str:
        mapping = {
            'de': 'German',
            'en': 'English',
            'fr': 'French',
            'in': 'Hindi',
            'it': 'Italian',
            'jp': 'Japanese',
            'kr': 'Korean',
            'nl': 'Dutch',
            'pl': 'Polish',
            'pt': 'Portuguese',
            'sp': 'Spanish',
        }
        return mapping.get((code or '').lower(), (code or '').upper())

    @staticmethod
    def _vibevoice_meta_from_stem(stem: str) -> dict:
        value = (stem or '').strip()
        meta = {
            'value': value,
            'display': value,
            'language_code': '',
            'language_name': '',
            'gender': '',
        }
        if not value:
            return meta

        # Official extra presets: de-Spk0_man, en-Carter_man, ...
        import re
        m = re.match(r'^(?P<lang>[a-z]{2})-(?P<name>.+?)_(?P<gender>man|woman)$', value, flags=re.IGNORECASE)
        if m:
            lang = m.group('lang').lower()
            name = m.group('name').strip()
            gender = m.group('gender').lower()
            meta.update({
                'display': name,
                'language_code': lang,
                'language_name': TTSClient._language_name_from_code(lang),
                'gender': 'male' if gender == 'man' else 'female',
            })
            return meta

        # Known built-in aliases exposed by wrapper API.
        alias_map = {
            'carter': ('en', 'English', 'male'),
            'davis': ('en', 'English', 'male'),
            'emma': ('en', 'English', 'female'),
            'frank': ('en', 'English', 'male'),
            'grace': ('en', 'English', 'female'),
            'mike': ('en', 'English', 'male'),
            'samuel': ('in', 'Hindi', 'male'),
        }
        info = alias_map.get(value.casefold())
        if info:
            meta.update({
                'language_code': info[0],
                'language_name': info[1],
                'gender': info[2],
            })
        return meta

    @classmethod
    def _vibevoice_label(cls, value: str, *, local_only: bool = False) -> str:
        meta = cls._vibevoice_meta_from_stem(value)
        parts = [meta['display'] or value]
        extras = []
        if meta['language_name']:
            extras.append(meta['language_name'])
        elif meta['language_code']:
            extras.append(meta['language_code'].upper())
        if meta['gender']:
            extras.append(meta['gender'])
        if extras:
            parts.append('— ' + ', '.join(extras))
        if local_only:
            parts.append('[local file — restart wrapper]')
        return ' '.join(parts).strip()

    def _list_local_vibevoice_voices(self) -> List[str]:
        voices_dir = TTS_DIR / 'vibevoice_openai' / 'models' / 'voices'
        if not voices_dir.exists():
            return []
        voices: List[str] = []
        for path in sorted(voices_dir.glob('*.pt')):
            stem = path.stem.strip()
            if stem:
                voices.append(stem)
        return sorted(set(voices), key=str.casefold)

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

        if self.backend == 'vibevoice_openai':
            entries: List[Tuple[str, str]] = []
            seen = set()
            api_voices: List[str] = []
            try:
                api_voices = self.list_voices()
            except Exception:
                api_voices = []
            for voice in api_voices:
                key = voice.casefold()
                if key in seen:
                    continue
                entries.append((voice, self._vibevoice_label(voice)))
                seen.add(key)

            for voice in self._list_local_vibevoice_voices():
                key = voice.casefold()
                if key in seen:
                    continue
                entries.append((voice, self._vibevoice_label(voice, local_only=True)))
                seen.add(key)

            return entries

        if self.backend == 'crispasr_openai':
            voices = []
            try:
                voices = self.list_voices()
            except Exception:
                pass
            if not voices:
                voices = ['default']
            return [(voice, voice) for voice in voices]

        return [(voice, voice) for voice in self.list_voices()]

    def list_voices(self) -> List[str]:
        if self.backend == 'windows_sapi':
            return [label for _value, label in self.list_voice_entries()]

        if self.backend not in {'vibevoice_openai', 'crispasr_openai'}:
            return []

        endpoints = [f'{self.base_url}/audio/voices']
        if self.backend == 'crispasr_openai':
            endpoints = [f'{self.base_url}/voices']
        response = None
        for endpoint in endpoints:
            try:
                candidate = requests.get(endpoint, timeout=3 if self.backend == 'crispasr_openai' else 10)
                candidate.raise_for_status()
                response = candidate
                break
            except requests.RequestException:
                continue
        if response is None:
            raise RuntimeError('Das TTS-Backend ist nicht erreichbar oder stellt keine Stimmenliste bereit.')
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

        local_voices = self._list_local_vibevoice_voices() if self.backend == 'vibevoice_openai' else []
        return sorted(set(voices + local_voices), key=str.casefold)

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

    @staticmethod
    def _clamp_sample(value: float | int) -> int:
        return max(-32768, min(32767, int(value)))

    def _apply_wav_voice_style(self, output_path: Path, *, external_backend: bool) -> Path:
        """Apply conservative local effects without adding another dependency.

        System.Speech already handles rate, pitch and volume natively. The
        VibeVoice wrapper currently accepts a speed field but does not implement
        it, so WAV resampling is used there. Character effects are applied for
        both backends and silently skipped for unsupported WAV encodings.
        """
        if output_path.suffix.lower() != '.wav' or not output_path.exists():
            return output_path
        needs_external_controls = external_backend and (
            self.windows_sapi_rate != 0
            or self.windows_sapi_pitch != 0
            or self.windows_sapi_volume != 100
        )
        if self.audio_effect == 'none' and not needs_external_controls:
            return output_path

        try:
            with wave.open(str(output_path), 'rb') as source:
                params = source.getparams()
                if params.sampwidth != 2 or params.comptype != 'NONE' or params.nchannels < 1:
                    return output_path
                raw_frames = source.readframes(params.nframes)
        except (OSError, wave.Error):
            return output_path

        samples = array('h')
        samples.frombytes(raw_frames)
        if sys.byteorder != 'little':
            samples.byteswap()
        channels = params.nchannels
        frame_count = len(samples) // channels
        if frame_count <= 1:
            return output_path

        intensity = self.voice_style_intensity / 100.0
        speed_factor = 1.0
        if external_backend:
            speed_factor *= 2.0 ** (self.windows_sapi_rate / 20.0)
            speed_factor *= 2.0 ** (self.windows_sapi_pitch / 48.0)
            speed_factor = max(0.65, min(1.55, speed_factor))
        output_frames = max(1, int(frame_count / speed_factor))
        styled = array('h')
        effect = self.audio_effect
        wobble_depth = max(1.0, params.framerate * 0.0025 * intensity)
        wobble_period = max(1.0, params.framerate * 0.7)
        echo_frames = max(1, int(params.framerate * 0.045))
        gain = (self.windows_sapi_volume / 100.0) if external_backend else 1.0
        noise_state = 0x13579BDF

        for out_frame in range(output_frames):
            source_position = out_frame * speed_factor
            if effect == 'tipsy':
                source_position += math.sin(out_frame * 2.0 * math.pi / wobble_period) * wobble_depth
            source_frame = max(0, min(frame_count - 1, int(source_position)))
            for channel in range(channels):
                value = float(samples[source_frame * channels + channel]) * gain
                if effect == 'robotic':
                    carrier_period = max(2, params.framerate // 34)
                    carrier = 1.0 if (out_frame % carrier_period) < (carrier_period // 2) else 0.34
                    value *= (1.0 - 0.48 * intensity) + (0.48 * intensity * carrier)
                    echo_source = source_frame - echo_frames
                    if echo_source >= 0:
                        value += samples[echo_source * channels + channel] * 0.16 * intensity
                elif effect == 'tipsy':
                    echo_source = source_frame - (echo_frames * 3)
                    if echo_source >= 0:
                        value += samples[echo_source * channels + channel] * 0.13 * intensity
                elif effect == 'whisper':
                    noise_state = (1103515245 * noise_state + 12345) & 0x7FFFFFFF
                    noise = ((noise_state / 0x7FFFFFFF) * 2.0 - 1.0) * 520.0 * intensity
                    value = value * (1.0 - 0.18 * intensity) + noise
                elif effect == 'presence':
                    value *= 1.0 + 0.08 * intensity
                elif effect == 'comic':
                    value *= 1.0 + 0.04 * intensity
                styled.append(self._clamp_sample(value))

        if sys.byteorder != 'little':
            styled.byteswap()
        temp_path = output_path.with_name(f'.{output_path.name}.styled.tmp.wav')
        try:
            with wave.open(str(temp_path), 'wb') as destination:
                destination.setparams(params)
                destination.writeframes(styled.tobytes())
            os.replace(temp_path, output_path)
        except (OSError, wave.Error):
            temp_path.unlink(missing_ok=True)
        return output_path

    def synthesize_to_file(self, text: str, output_path: Path) -> Path:
        if self.backend == 'windows_sapi':
            path = self._synthesize_windows_sapi_to_file(text, output_path)
            return self._apply_wav_voice_style(path, external_backend=False)

        if self.backend not in {'vibevoice_openai', 'crispasr_openai'}:
            raise RuntimeError('TTS backend is disabled.')

        payload = {
            'model': self.model,
            'input': text,
            'response_format': self.audio_format,
            'format': self.audio_format,
            # Kept for OpenAI API compatibility. The currently supported local
            # wrapper accepts this field even though it does not apply it yet.
            'speed': 1.0,
        }
        if self.backend != 'crispasr_openai' or self.voice.casefold() not in {'', 'auto', 'default'}:
            payload['voice'] = self.voice

        response = requests.post(
            f'{self.base_url}/audio/speech',
            json=payload,
            timeout=1200,
        )
        response.raise_for_status()
        content = response.content
        content_type = (response.headers.get('Content-Type') or '').split(';', 1)[0].strip().lower()
        if not content or len(content) < 44:
            raise RuntimeError('Das TTS-Backend hat keine gültigen Audiodaten geliefert.')
        if content_type in {'application/json', 'text/plain', 'text/html'}:
            preview = self._decode_output(content[:500]).strip()
            raise RuntimeError(f'Das TTS-Backend lieferte statt Audio eine Fehlermeldung: {preview}')
        if self.audio_format == 'wav' and not content.startswith((b'RIFF', b'RF64')):
            raise RuntimeError('Das TTS-Backend lieferte keine gültige WAV-Datei.')

        output_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(output_path, content)
        return self._apply_wav_voice_style(output_path, external_backend=True)
