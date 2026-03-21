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
from typing import Callable
from urllib.parse import urlparse

import requests

from .config import APP_DATA_DIR, CACHE_DIR

GITHUB_ZIP_URL = "https://codeload.github.com/marhensa/vibevoice-realtime-openai-api/zip/refs/heads/main"


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
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.root_dir = APP_DATA_DIR / "tts" / "vibevoice_openai"
        self.repo_dir = self.root_dir / "repo"
        self.models_dir = self.root_dir / "models"
        self.log_path = self.root_dir / "server.log"
        self.pid_path = self.root_dir / "server.pid"
        self.repo_zip_path = CACHE_DIR / "vibevoice_openai_api_main.zip"

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
            return True, body or "ok"
        except Exception as exc:
            return False, str(exc)

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

    def is_pid_running(self) -> bool:
        if not self.pid_path.exists():
            return False
        try:
            pid = int(self.pid_path.read_text(encoding="utf-8").strip())
        except Exception:
            return False
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return str(pid) in result.stdout
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def install_ffmpeg_via_winget(self, log: Callable[[str], None]) -> None:
        if self.ffmpeg_found():
            log("FFmpeg ist bereits in PATH vorhanden. winget wird übersprungen.")
            return
        if os.name != "nt":
            raise RuntimeError("Die automatische FFmpeg-Installation ist hier nur für Windows per winget vorgesehen.")
        if shutil.which("winget") is None:
            raise RuntimeError("winget wurde nicht gefunden. Bitte FFmpeg manuell installieren und ffmpeg.exe in PATH bringen.")
        cmd = [
            "winget", "install", "--id", "Gyan.FFmpeg", "-e",
            "--accept-source-agreements", "--accept-package-agreements",
        ]
        self.run_command(cmd, APP_DATA_DIR, log)
        if self.ffmpeg_found():
            log("FFmpeg wurde gefunden.")

    def download_repo_zip(self, log: Callable[[str], None]) -> Path:
        self.ensure_dirs()
        log(f"Downloade Wrapper-Archiv: {GITHUB_ZIP_URL}")
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
                            f"Archivdownload: {percent}% "
                            f"({downloaded // 1024 // 1024} / {total // 1024 // 1024} MB)"
                        )
        log(f"Archiv gespeichert: {self.repo_zip_path}")
        return self.repo_zip_path

    def extract_repo(self, archive_path: Path, log: Callable[[str], None]) -> None:
        self.ensure_dirs()
        if self.repo_dir.exists():
            log("Vorhandenes Wrapper-Verzeichnis wird ersetzt …")
            shutil.rmtree(self.repo_dir, ignore_errors=True)
        with tempfile.TemporaryDirectory(prefix="vibevoice_extract_") as tmpdir:
            tmp = Path(tmpdir)
            log("Entpacke Wrapper-Archiv …")
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(tmp)
            candidates = [p for p in tmp.iterdir() if p.is_dir()]
            if not candidates:
                raise RuntimeError("Das Archiv enthielt kein erwartetes Hauptverzeichnis.")
            source_root = candidates[0]
            shutil.copytree(source_root, self.repo_dir)
        log(f"Wrapper entpackt nach: {self.repo_dir}")
        if not self.wrapper_script().exists():
            raise RuntimeError("Die Startdatei vibevoice_realtime_openai_api.py wurde nach dem Entpacken nicht gefunden.")

    def compatibility_note(self) -> str:
        current = sys.version.split()[0]
        if sys.version_info[:2] == (3, 13):
            return f"Python {current} erkannt. Das passt zur empfohlenen Wrapper-Version."
        return (
            "Hinweis: Der Wrapper nennt in seiner README Python 3.13 als empfohlenen Weg. "
            f"Aktuell verwendet OllamaVibeDesk jedoch Python {current}. "
            "Die App versucht das Setup trotzdem mit der aktuellen Python-Version. "
            "Das kann funktionieren, ist aber nicht der offiziell empfohlene Pfad. "
            "Falls es dabei Probleme gibt, nutze vorerst 'windows_sapi' als Fallback oder richte den Wrapper später mit Python 3.13 ein."
        )

    def create_venv(self, log: Callable[[str], None]) -> None:
        if not self.repo_dir.exists():
            raise RuntimeError("Das Wrapper-Repository wurde noch nicht eingerichtet.")
        note = self.compatibility_note()
        log(note)
        if self.venv_python().exists():
            log("Wrapper-venv existiert bereits.")
            return
        py = sys.executable
        log("Erstelle Python-venv für den Wrapper mit der aktuellen Python-Version …")
        self.run_command([py, "-m", "venv", ".venv"], self.repo_dir, log)

    def install_requirements(self, log: Callable[[str], None]) -> None:
        python = self.venv_python()
        if not python.exists():
            raise RuntimeError("Wrapper-venv fehlt.")
        req = self.repo_dir / "requirements.txt"
        if not req.exists():
            raise RuntimeError("requirements.txt wurde im Wrapper nicht gefunden.")
        log("Installiere/aktualisiere pip …")
        self.run_command([str(python), "-m", "pip", "install", "--upgrade", "pip"], self.repo_dir, log)
        log("Installiere Wrapper-Abhängigkeiten … das kann eine Weile dauern.")
        self.run_command([str(python), "-m", "pip", "install", "-r", str(req)], self.repo_dir, log)

    def install_or_update(self, log: Callable[[str], None]) -> None:
        self.ensure_dirs()
        if not self.ffmpeg_found():
            log("Hinweis: ffmpeg wurde in PATH nicht gefunden. Der Wrapper nennt ffmpeg als Voraussetzung.")
        archive = self.download_repo_zip(log)
        self.extract_repo(archive, log)
        self.create_venv(log)
        self.install_requirements(log)
        log(
            "Setup abgeschlossen. "
            + self.compatibility_note()
            + " Beim ersten Serverstart können zusätzliche Modelldateien und Stimmen lokal geladen werden."
        )

    def auto_setup(self, log: Callable[[str], None]) -> tuple[bool, str]:
        self.ensure_dirs()
        status = self.status()
        log(f"Backend-URL: {status.base_url}")
        log(f"Health: {'OK' if status.health_ok else 'nicht erreichbar'}")
        log(f"ffmpeg in PATH: {'ja' if status.ffmpeg_found else 'nein'}")
        log(f"Wrapper-Dateien vorhanden: {'ja' if status.repo_present else 'nein'}")
        log(f"Wrapper-venv vorhanden: {'ja' if status.venv_present else 'nein'}")

        if not status.ffmpeg_found:
            log("FFmpeg fehlt. Versuche Installation via winget …")
            self.install_ffmpeg_via_winget(log)
        else:
            log("FFmpeg ist bereits vorhanden. Überspringe winget.")

        archive = self.download_repo_zip(log)
        self.extract_repo(archive, log)
        self.create_venv(log)
        self.install_requirements(log)
        msg = (
            "Automatisches Setup abgeschlossen. "
            + self.compatibility_note()
            + " Beim ersten Serverstart können zusätzliche Modelldateien und Stimmen lokal geladen werden."
        )
        log(msg)
        return True, msg

    def start_server(self, log: Callable[[str], None]) -> None:
        self.ensure_dirs()
        if self.healthcheck(timeout=2.0)[0]:
            log("TTS-Server antwortet bereits.")
            return
        script = self.wrapper_script()
        python = self.venv_python()
        if not script.exists():
            raise RuntimeError('Wrapper ist nicht installiert. Bitte zuerst "Installieren/Aktualisieren" ausführen.')
        if not python.exists():
            raise RuntimeError("Wrapper-venv fehlt. Bitte zuerst installieren.")

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
        log("Starte lokalen TTS-Server: " + " ".join(cmd))
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
        log(f"Prozess gestartet mit PID {process.pid}.")
        log("Wenn dies der erste Start ist, kann nun ein längerer Modelldownload beginnen.")
        log(f"Modelle werden erwartet unter: {self.models_dir}")

        for second in range(1, 16):
            ok, msg = self.healthcheck(timeout=2.0)
            if ok:
                log(f"TTS-Server antwortet bereits nach {second} s: {msg}")
                return
            time.sleep(1)
        log("Noch keine Health-Antwort. Das ist beim ersten Start möglich, während Modelle heruntergeladen oder initialisiert werden.")
        log(f"Bitte bei Bedarf die Logdatei prüfen: {self.log_path}")

    def stop_server(self, log: Callable[[str], None]) -> None:
        if not self.pid_path.exists():
            raise RuntimeError("Keine gespeicherte PID gefunden.")
        try:
            pid = int(self.pid_path.read_text(encoding="utf-8").strip())
        except Exception as exc:
            raise RuntimeError(f"Ungültige PID-Datei: {exc}") from exc
        if os.name == "nt":
            self.run_command(["taskkill", "/PID", str(pid), "/T", "/F"], self.root_dir, log, check=False)
        else:
            os.kill(pid, 15)
        time.sleep(1)
        self.pid_path.unlink(missing_ok=True)
        log(f"Beende TTS-Server PID {pid}.")

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
            raise RuntimeError("Befehl fehlgeschlagen mit Exit-Code %s: %s" % (code, " ".join(cmd)))
