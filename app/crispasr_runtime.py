from __future__ import annotations

import os
import atexit
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from .config import APP_ROOT, APP_DATA_DIR
from .speech_models import SpeechModel


CRISPASR_DIR = APP_DATA_DIR / "speech" / "crispasr"
CRISPASR_RUNTIME_DIR = CRISPASR_DIR / "runtime"
_OWNED_SERVERS: dict[int, tuple[subprocess.Popen, str]] = {}


def stop_owned_crispasr_servers() -> None:
    for port, (process, _backend) in list(_OWNED_SERVERS.items()):
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        _OWNED_SERVERS.pop(port, None)


atexit.register(stop_owned_crispasr_servers)


def find_crispasr_executable(configured_path: object = "") -> Path | None:
    candidates: list[Path] = []
    configured = str(configured_path or "").strip()
    if configured:
        configured_candidate = Path(configured)
        try:
            resolved_candidate = configured_candidate.resolve()
            if resolved_candidate.is_relative_to(APP_ROOT.resolve()) and resolved_candidate.name.casefold() in {"crispasr", "crispasr.exe"}:
                candidates.append(resolved_candidate)
        except OSError:
            pass
    binary = "crispasr.exe" if os.name == "nt" else "crispasr"
    candidates.extend((CRISPASR_RUNTIME_DIR / binary, CRISPASR_DIR / binary))
    if CRISPASR_RUNTIME_DIR.exists():
        candidates.extend(sorted(CRISPASR_RUNTIME_DIR.rglob(binary)))
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


class CrispASRManager:
    def __init__(self, base_url: str, model: SpeechModel, executable_path: object = "") -> None:
        if model.runtime != "crispasr":
            raise ValueError("The selected model is not compatible with CrispASR.")
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.model = model
        self.executable_path = str(executable_path or "").strip()
        self.log_path = CRISPASR_DIR / f"{model.purpose}_{model.model_id}.log"

    @property
    def health_url(self) -> str:
        parsed = urlparse(self.base_url)
        return f"{parsed.scheme}://{parsed.netloc}/health"

    def health_status(self, timeout: float = 1.5) -> dict | None:
        try:
            response = requests.get(self.health_url, timeout=timeout)
            payload = response.json()
            return payload if response.ok and isinstance(payload, dict) and payload.get("status") == "ok" else None
        except Exception:
            return None

    def is_running(self, timeout: float = 1.5) -> bool:
        status = self.health_status(timeout)
        if not status:
            return False
        active_backend = str(status.get("backend", "") or "").strip()
        return not active_backend or active_backend == self.model.backend

    def ensure_server_running(self, log=None, max_wait: int = 300) -> bool:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("Ein externer CrispASR-Server muss manuell gestartet werden.")
        port = parsed.port
        if not port:
            raise RuntimeError("In der lokalen CrispASR-URL fehlt der Port.")

        owned = _OWNED_SERVERS.get(port)
        if owned is not None:
            owned_process, owned_backend = owned
            if owned_process.poll() is not None:
                _OWNED_SERVERS.pop(port, None)
            elif owned_backend != self.model.backend:
                if log:
                    log("CrispASR wechselt auf das kompatible Sprachmodell …")
                owned_process.terminate()
                try:
                    owned_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    owned_process.kill()
                _OWNED_SERVERS.pop(port, None)
                time.sleep(0.5)

        status = self.health_status()
        if status:
            active_backend = str(status.get("backend", "") or "").strip()
            if active_backend and active_backend != self.model.backend:
                raise RuntimeError(
                    f"Am konfigurierten Port läuft CrispASR mit dem inkompatiblen Backend "
                    f"'{active_backend}' statt '{self.model.backend}'. Bitte den fremden Server stoppen oder einen anderen Port verwenden."
                )
            return False
        executable = find_crispasr_executable(self.executable_path)
        if executable is None:
            installer = APP_ROOT / "install_crispasr_windows.bat"
            raise RuntimeError(f"CrispASR ist nicht installiert. Bitte zuerst {installer.name} ausführen.")

        CRISPASR_DIR.mkdir(parents=True, exist_ok=True)
        log_handle = self.log_path.open("a", encoding="utf-8")
        command = [
            str(executable), "--server", "--host", "127.0.0.1", "--port", str(port),
            "--backend", self.model.backend, "-m", self.model.model_argument,
        ]
        environment = os.environ.copy()
        cache_dir = CRISPASR_DIR / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        environment["CRISPASR_CACHE_DIR"] = str(cache_dir)
        environment["CRISPASR_AUTO_DOWNLOAD"] = "1"
        kwargs: dict = {
            "cwd": str(CRISPASR_DIR),
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
            "env": environment,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(command, **kwargs)
        finally:
            log_handle.close()
        _OWNED_SERVERS[port] = (process, self.model.backend)
        started = time.monotonic()
        while time.monotonic() - started < max_wait:
            if self.is_running(timeout=1.0):
                return True
            return_code = process.poll()
            if return_code is not None:
                _OWNED_SERVERS.pop(port, None)
                tail = ""
                try:
                    tail = self.log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
                except OSError:
                    pass
                raise RuntimeError(f"CrispASR wurde mit Code {return_code} beendet.\n\n{tail}")
            if log:
                elapsed = int(time.monotonic() - started)
                log(f"CrispASR lädt das Sprachmodell … {elapsed} s")
            time.sleep(1.0)
        raise RuntimeError("CrispASR wurde nicht rechtzeitig bereit. Beim ersten Start kann der Modelldownload länger dauern.")
