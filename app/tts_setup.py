from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import requests

from .config import APP_DATA_DIR, CACHE_DIR

GITHUB_ZIP_URL = "https://codeload.github.com/marhensa/vibevoice-realtime-openai-api/zip/refs/heads/main"
OFFICIAL_VIBEVOICE_VOICE_BASE = "https://raw.githubusercontent.com/microsoft/VibeVoice/main/demo/voices/streaming_model"
OFFICIAL_VIBEVOICE_VOICE_FILES = [
    "de-Spk0_man.pt",
    "de-Spk1_woman.pt",
    "en-Carter_man.pt",
    "en-Davis_man.pt",
    "en-Emma_woman.pt",
    "en-Frank_man.pt",
    "en-Grace_woman.pt",
    "en-Mike_man.pt",
    "fr-Spk0_man.pt",
    "fr-Spk1_woman.pt",
    "in-Samuel_man.pt",
    "it-Spk0_woman.pt",
    "it-Spk1_man.pt",
    "jp-Spk0_man.pt",
    "jp-Spk1_woman.pt",
    "kr-Spk0_woman.pt",
    "kr-Spk1_man.pt",
    "nl-Spk0_man.pt",
    "nl-Spk1_woman.pt",
    "pl-Spk0_man.pt",
    "pl-Spk1_woman.pt",
    "pt-Spk0_woman.pt",
    "pt-Spk1_man.pt",
    "sp-Spk0_woman.pt",
    "sp-Spk1_man.pt",
]


@dataclass
class TTSStatus:
    base_url: str
    health_ok: bool
    health_message: str
    ffmpeg_found: bool
    repo_present: bool
    venv_present: bool
    pid_running: bool
    repo_dir: str
    models_dir: str
    log_path: str


class VibeVoiceManager:
    def __init__(self, base_url: str, translate: Optional[Callable[[str, str], str]] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._translate = translate or (lambda key, default='': default or key)
        self.root_dir = APP_DATA_DIR / "tts" / "vibevoice_openai"
        self.repo_dir = self.root_dir / "repo"
        self.models_dir = self.root_dir / "models"
        self.log_path = self.root_dir / "server.log"
        self.pid_path = self.root_dir / "server.pid"
        self.repo_zip_path = CACHE_DIR / "vibevoice_openai_api_main.zip"

    def t(self, key: str, default: str) -> str:
        return self._translate(key, default)

    def ensure_dirs(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def wrapper_script(self) -> Path:
        return self.repo_dir / "vibevoice_realtime_openai_api.py"

    def venv_python(self) -> Path:
        if os.name == "nt":
            return self.repo_dir / ".venv" / "Scripts" / "python.exe"
        return self.repo_dir / ".venv" / "bin" / "python"

    def ffmpeg_found(self) -> bool:
        return shutil.which("ffmpeg") is not None

    def parse_host_port(self) -> tuple[str, int]:
        parsed = urlparse(self.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return host, port

    def healthcheck(self, timeout: float = 3.0) -> tuple[bool, str]:
        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        try:
            response = requests.get(f"{root}/health", timeout=timeout)
            response.raise_for_status()
            body = response.text.strip()[:300]
            return True, body or self.t("vv_health_ok", "ok")
        except Exception as exc:
            return False, str(exc)

    def wait_until_healthy(self, log: Callable[[str], None], max_wait: int = 120, poll_seconds: float = 2.0) -> tuple[bool, str]:
        last_msg = ''
        steps = max(1, int(max_wait / poll_seconds))
        for index in range(steps):
            ok, msg = self.healthcheck(timeout=min(5.0, poll_seconds + 1.0))
            last_msg = msg
            if ok:
                waited = int(index * poll_seconds)
                log(self.t("vv_health_ready_after", "TTS-Server ist bereit nach {seconds} s: {message}").format(seconds=waited, message=msg))
                return True, msg
            time.sleep(poll_seconds)
        log(self.t("vv_health_wait_timeout", "TTS-Server wurde innerhalb von {seconds} s nicht bereit. Letzte Meldung: {message}").format(seconds=max_wait, message=last_msg or self.t("vv_unknown", "unbekannt")))
        return False, last_msg

    def ensure_server_running(self, log: Callable[[str], None], max_wait: int = 120) -> bool:
        ok, msg = self.healthcheck(timeout=2.0)
        if ok:
            log(self.t("vv_server_already", "TTS-Server antwortet bereits."))
            return False
        log(self.t("vv_autostart_needed", "VibeVoice ist noch nicht erreichbar. Automatischer Start wird versucht …"))
        self.start_server(log)
        ok, msg = self.healthcheck(timeout=2.0)
        if ok:
            return True
        ok, _msg = self.wait_until_healthy(log, max_wait=max_wait, poll_seconds=2.0)
        if ok:
            return True
        raise RuntimeError(self.t("vv_autostart_failed", "Der lokale VibeVoice-Server konnte nicht rechtzeitig gestartet werden. Bitte VibeVoice-Setup öffnen und die Logdatei prüfen."))

    def status(self) -> TTSStatus:
        self.ensure_dirs()
        health_ok, health_msg = self.healthcheck()
        return TTSStatus(
            base_url=self.base_url,
            health_ok=health_ok,
            health_message=health_msg,
            ffmpeg_found=self.ffmpeg_found(),
            repo_present=self.wrapper_script().exists(),
            venv_present=self.venv_python().exists(),
            pid_running=self.is_pid_running(),
            repo_dir=str(self.repo_dir),
            models_dir=str(self.models_dir),
            log_path=str(self.log_path),
        )

    def _decode_output(self, data: bytes | None) -> str:
        if not data:
            return ''
        for enc in ('utf-8', 'cp1252', 'cp850', 'latin-1'):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode('utf-8', errors='replace')

    def is_pid_running(self) -> bool:
        if not self.pid_path.exists():
            return False
        try:
            pid = int(self.pid_path.read_text(encoding="utf-8").strip())
        except Exception:
            return False
        if os.name == "nt":
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True,
                    text=False,
                    timeout=10,
                )
            except Exception:
                return False
            stdout = self._decode_output(result.stdout)
            stderr = self._decode_output(result.stderr)
            haystack = f"{stdout}\n{stderr}"
            return str(pid) in haystack
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def install_ffmpeg_via_winget(self, log: Callable[[str], None]) -> None:
        if self.ffmpeg_found():
            log(self.t("vv_ffmpeg_skip", "FFmpeg ist bereits in PATH vorhanden. winget wird übersprungen."))
            return
        if os.name != "nt":
            raise RuntimeError(self.t("vv_ffmpeg_windows_only", "Die automatische FFmpeg-Installation ist hier nur für Windows per winget vorgesehen."))
        if shutil.which("winget") is None:
            raise RuntimeError(self.t("vv_ffmpeg_no_winget", "winget wurde nicht gefunden. Bitte FFmpeg manuell installieren und ffmpeg.exe in PATH bringen."))
        cmd = [
            "winget", "install", "--id", "Gyan.FFmpeg", "-e",
            "--accept-source-agreements", "--accept-package-agreements",
        ]
        self.run_command(cmd, APP_DATA_DIR, log)
        if self.ffmpeg_found():
            log(self.t("vv_ffmpeg_found", "FFmpeg wurde gefunden."))

    def download_repo_zip(self, log: Callable[[str], None]) -> Path:
        self.ensure_dirs()
        log(self.t("vv_download_repo", "Downloade Wrapper-Archiv: {url}").format(url=GITHUB_ZIP_URL))
        with requests.get(GITHUB_ZIP_URL, stream=True, timeout=60) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", "0") or "0")
            downloaded = 0
            with open(self.repo_zip_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        percent = downloaded * 100 // total
                        log(
                            self.t("vv_download_progress", "Archivdownload: {percent}% ({downloaded} / {total} MB)").format(percent=percent, downloaded=downloaded // 1024 // 1024, total=total // 1024 // 1024)
                        )
        log(self.t("vv_archive_saved", "Archiv gespeichert: {path}").format(path=self.repo_zip_path))
        return self.repo_zip_path

    def extract_repo(self, archive_path: Path, log: Callable[[str], None]) -> None:
        self.ensure_dirs()
        if self.repo_dir.exists():
            log(self.t("vv_replace_wrapper_dir", "Vorhandenes Wrapper-Verzeichnis wird ersetzt …"))
            shutil.rmtree(self.repo_dir, ignore_errors=True)
        with tempfile.TemporaryDirectory(prefix="vibevoice_extract_") as tmpdir:
            tmp = Path(tmpdir)
            log(self.t("vv_extract_archive", "Entpacke Wrapper-Archiv …"))
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(tmp)
            candidates = [p for p in tmp.iterdir() if p.is_dir()]
            if not candidates:
                raise RuntimeError(self.t("vv_missing_root", "Das Archiv enthielt kein erwartetes Hauptverzeichnis."))
            source_root = candidates[0]
            shutil.copytree(source_root, self.repo_dir)
        log(self.t("vv_extracted_to", "Wrapper entpackt nach: {path}").format(path=self.repo_dir))
        if not self.wrapper_script().exists():
            raise RuntimeError(self.t("vv_missing_startfile", "Die Startdatei vibevoice_realtime_openai_api.py wurde nach dem Entpacken nicht gefunden."))

    def voices_dir(self) -> Path:
        return self.models_dir / "voices"

    def local_voice_files(self) -> list[str]:
        voices_dir = self.voices_dir()
        if not voices_dir.exists():
            return []
        return sorted({path.name for path in voices_dir.glob("*.pt")}, key=str.casefold)

    def official_voice_files(self) -> list[str]:
        return list(OFFICIAL_VIBEVOICE_VOICE_FILES)

    def missing_official_voice_files(self) -> list[str]:
        installed = {name.casefold() for name in self.local_voice_files()}
        return [name for name in self.official_voice_files() if name.casefold() not in installed]

    def download_official_voice_presets(self, log: Callable[[str], None]) -> tuple[int, int]:
        self.ensure_dirs()
        voices_dir = self.voices_dir()
        voices_dir.mkdir(parents=True, exist_ok=True)
        all_files = self.official_voice_files()
        missing = self.missing_official_voice_files()
        if not missing:
            log(self.t("vv_voice_download_skip", "All official VibeVoice voice presets are already present."))
            return len(all_files), 0

        log(self.t("vv_voice_download_start", "Downloading additional official VibeVoice voice presets …"))
        log(self.t("vv_voice_download_summary", "Missing voice presets: {count} of {total}.").format(count=len(missing), total=len(all_files)))
        downloaded = 0
        for index, filename in enumerate(missing, start=1):
            url = f"{OFFICIAL_VIBEVOICE_VOICE_BASE}/{filename}"
            target = voices_dir / filename
            log(self.t("vv_voice_download_file", "Voice preset {index}/{total}: {filename}").format(index=index, total=len(missing), filename=filename))
            with requests.get(url, stream=True, timeout=120) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", "0") or "0")
                current = 0
                with open(target, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 128):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        current += len(chunk)
                        if total:
                            percent = int(current * 100 / total)
                            log(self.t("vv_voice_download_progress", "Voice preset download {filename}: {percent}%").format(filename=filename, percent=percent))
            if not target.exists() or target.stat().st_size == 0:
                raise RuntimeError(self.t("vv_voice_download_invalid", "The downloaded voice preset is invalid: {filename}").format(filename=filename))
            downloaded += 1
            log(self.t("vv_voice_download_done_file", "Saved voice preset: {filename}").format(filename=filename))

        log(self.t("vv_voice_download_done", "Additional official voice presets downloaded: {count}. Please restart the wrapper so the new voices are scanned.").format(count=downloaded))
        return len(all_files), downloaded

    def compatibility_note(self) -> str:
        current = sys.version.split()[0]
        if sys.version_info[:2] == (3, 13):
            return self.t("vv_py313_ok", "Python {version} erkannt. Das passt zur empfohlenen Wrapper-Version.").format(version=current)
        return self.t("vv_py313_note", "Hinweis: Der Wrapper nennt in seiner README Python 3.13 als empfohlenen Weg. Aktuell verwendet OllamaVibeDesk jedoch Python {version}. Die App versucht das Setup trotzdem mit der aktuellen Python-Version. Das kann funktionieren, ist aber nicht der offiziell empfohlene Pfad. Falls es dabei Probleme gibt, nutze vorerst 'windows_sapi' als Fallback oder richte den Wrapper später mit Python 3.13 ein.").format(version=current)

    def create_venv(self, log: Callable[[str], None]) -> None:
        if not self.repo_dir.exists():
            raise RuntimeError(self.t("vv_repo_not_ready", "Das Wrapper-Repository wurde noch nicht eingerichtet."))
        note = self.compatibility_note()
        log(note)
        if self.venv_python().exists():
            log(self.t("vv_venv_exists", "Wrapper-venv existiert bereits."))
            return
        py = sys.executable
        log(self.t("vv_create_venv", "Erstelle Python-venv für den Wrapper mit der aktuellen Python-Version …"))
        self.run_command([py, "-m", "venv", ".venv"], self.repo_dir, log)

    def install_requirements(self, log: Callable[[str], None]) -> None:
        python = self.venv_python()
        if not python.exists():
            raise RuntimeError(self.t("vv_venv_missing", "Wrapper-venv fehlt."))
        req = self.repo_dir / "requirements.txt"
        if not req.exists():
            raise RuntimeError(self.t("vv_requirements_missing", "requirements.txt wurde im Wrapper nicht gefunden."))
        log(self.t("vv_upgrade_pip", "Installiere/aktualisiere pip …"))
        self.run_command([str(python), "-m", "pip", "install", "--upgrade", "pip"], self.repo_dir, log)
        log(self.t("vv_install_requirements", "Installiere Wrapper-Abhängigkeiten … das kann eine Weile dauern."))
        self.run_command([str(python), "-m", "pip", "install", "-r", str(req)], self.repo_dir, log)

    def install_or_update(self, log: Callable[[str], None]) -> None:
        self.ensure_dirs()
        if not self.ffmpeg_found():
            log("Hinweis: ffmpeg wurde in PATH nicht gefunden. Der Wrapper nennt ffmpeg als Voraussetzung.")
        archive = self.download_repo_zip(log)
        self.extract_repo(archive, log)
        self.create_venv(log)
        self.install_requirements(log)
        self.download_official_voice_presets(log)
        note = self.compatibility_note()
        log(self.t("vv_setup_done", "Setup abgeschlossen. {note} Beim ersten Serverstart können zusätzliche Modelldateien und Stimmen lokal geladen werden.").format(note=note))

    def auto_setup(self, log: Callable[[str], None]) -> tuple[bool, str]:
        self.ensure_dirs()
        status = self.status()
        log(self.t("vv_status_backend", "Backend-URL: {value}").format(value=status.base_url))
        log(self.t("vv_status_health", "Health: {value}").format(value=(self.t("ok", "OK") if status.health_ok else self.t("not_reachable", "nicht erreichbar"))))
        log(self.t("vv_status_ffmpeg", "ffmpeg in PATH: {value}").format(value=(self.t("yes", "ja") if status.ffmpeg_found else self.t("no", "nein"))))
        log(self.t("vv_status_repo", "Wrapper-Dateien vorhanden: {value}").format(value=(self.t("yes", "ja") if status.repo_present else self.t("no", "nein"))))
        log(self.t("vv_status_venv", "Wrapper-venv vorhanden: {value}").format(value=(self.t("yes", "ja") if status.venv_present else self.t("no", "nein"))))

        if not status.ffmpeg_found:
            log(self.t("vv_ffmpeg_missing_try", "FFmpeg fehlt. Versuche Installation via winget …"))
            self.install_ffmpeg_via_winget(log)
        else:
            log(self.t("vv_ffmpeg_present_skip", "FFmpeg ist bereits vorhanden. Überspringe winget."))

        archive = self.download_repo_zip(log)
        self.extract_repo(archive, log)
        self.create_venv(log)
        self.install_requirements(log)
        self.download_official_voice_presets(log)
        msg = self.t("vv_auto_done", "Automatisches Setup abgeschlossen. {note} Beim ersten Serverstart können zusätzliche Modelldateien und Stimmen lokal geladen werden.").format(note=self.compatibility_note())
        log(msg)
        return True, msg

    def start_server(self, log: Callable[[str], None]) -> None:
        self.ensure_dirs()
        if self.healthcheck(timeout=2.0)[0]:
            log(self.t("vv_server_already", "TTS-Server antwortet bereits."))
            return
        script = self.wrapper_script()
        python = self.venv_python()
        if not script.exists():
            raise RuntimeError(self.t("vv_server_not_installed", "Wrapper ist nicht installiert. Bitte zuerst installieren oder das automatische Setup ausführen."))
        if not python.exists():
            raise RuntimeError(self.t("vv_server_no_venv", "Wrapper-venv fehlt. Bitte zuerst installieren."))

        _host, port = self.parse_host_port()
        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        env = os.environ.copy()
        env["MODELS_DIR"] = str(self.models_dir)
        env.setdefault("VIBEVOICE_DEVICE", "cuda")
        env.setdefault("CFG_SCALE", "1.25")
        env.setdefault("PYTHONUTF8", "1")

        self.root_dir.mkdir(parents=True, exist_ok=True)
        log_handle = open(self.log_path, "a", encoding="utf-8")
        log_handle.write("\n" + ("=" * 80) + "\n")
        log_handle.write(f"Start {time.strftime('%Y-%m-%d %H:%M:%S')} -> {root}\n")
        log_handle.flush()

        cmd = [str(python), str(script), "--port", str(port)]
        log(self.t("vv_start_server", "Starte lokalen TTS-Server: {cmd}").format(cmd=" ".join(cmd)))
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        process = subprocess.Popen(
            cmd,
            cwd=self.repo_dir,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        self.pid_path.write_text(str(process.pid), encoding="utf-8")
        log(self.t("vv_started_pid", "Prozess gestartet mit PID {pid}.").format(pid=process.pid))
        log(self.t("vv_first_start_download", "Wenn dies der erste Start ist, kann nun ein längerer Modelldownload beginnen."))
        log(self.t("vv_models_expected", "Modelle werden erwartet unter: {path}").format(path=self.models_dir))

        for second in range(1, 16):
            ok, msg = self.healthcheck(timeout=2.0)
            if ok:
                log(self.t("vv_health_after_seconds", "TTS-Server antwortet bereits nach {seconds} s: {message}").format(seconds=second, message=msg))
                return
            time.sleep(1)
        log(self.t("vv_no_health_yet", "Noch keine Health-Antwort. Das ist beim ersten Start möglich, während Modelle heruntergeladen oder initialisiert werden."))
        log(self.t("vv_check_log", "Bitte bei Bedarf die Logdatei prüfen: {path}").format(path=self.log_path))

    def stop_server(self, log: Callable[[str], None]) -> None:
        if not self.pid_path.exists():
            raise RuntimeError(self.t("vv_no_pid", "Keine gespeicherte PID gefunden."))
        try:
            pid = int(self.pid_path.read_text(encoding="utf-8").strip())
        except Exception as exc:
            raise RuntimeError(self.t("vv_invalid_pid", "Ungültige PID-Datei: {error}").format(error=exc)) from exc
        if os.name == "nt":
            self.run_command(["taskkill", "/PID", str(pid), "/T", "/F"], self.root_dir, log, check=False)
        else:
            os.kill(pid, 15)
        time.sleep(1)
        self.pid_path.unlink(missing_ok=True)
        log(self.t("vv_stop_pid", "Beende TTS-Server PID {pid}.").format(pid=pid))

    def run_command(
        self,
        cmd: list[str],
        cwd: Path,
        log: Callable[[str], None],
        check: bool = True,
    ) -> None:
        log(">> " + " ".join(cmd))
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            bufsize=0,
        )
        assert process.stdout is not None
        buffer = b''
        while True:
            chunk = process.stdout.readline()
            if not chunk:
                break
            buffer += chunk
            line = None
            for encoding in ('utf-8', 'cp1252', 'cp850'):
                try:
                    line = buffer.decode(encoding)
                    buffer = b''
                    break
                except UnicodeDecodeError:
                    continue
            if line is None:
                continue
            line = line.rstrip('\r\n')
            if line:
                log(line)
        if buffer:
            leftover = buffer.decode('utf-8', errors='replace').rstrip('\r\n')
            if leftover:
                log(leftover)
        code = process.wait()
        if check and code != 0:
            raise RuntimeError(self.t("vv_command_failed", "Befehl fehlgeschlagen mit Exit-Code {code}: {cmd}").format(code=code, cmd=" ".join(cmd)))
