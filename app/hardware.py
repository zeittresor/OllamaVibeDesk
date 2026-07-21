from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class HardwareProfile:
    cpu_threads: int
    ram_gb: float
    gpu_name: str
    vram_gb: float
    recommended_num_ctx: int
    recommended_parallelism: int

    def to_dict(self) -> dict:
        return asdict(self)


def _ram_gb() -> float:
    try:
        import psutil  # optional
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    if platform.system() == "Windows":
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
                text=True,
                timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).strip()
            return round(int(out) / (1024 ** 3), 1)
        except Exception:
            return 0.0
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        return round((page_size * pages) / (1024 ** 3), 1)
    except Exception:
        return 0.0


def _nvidia_info() -> tuple[str, float]:
    try:
        kwargs = {"text": True, "timeout": 4}
        if platform.system() == "Windows":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            **kwargs,
        )
        first = out.splitlines()[0]
        name, memory_mb = [part.strip() for part in first.rsplit(",", 1)]
        return name, round(float(memory_mb) / 1024.0, 1)
    except Exception:
        return "", 0.0




def _windows_gpu_info() -> tuple[str, float]:
    if platform.system() != "Windows":
        return "", 0.0
    command = (
        "$gpu = Get-CimInstance Win32_VideoController | "
        "Sort-Object AdapterRAM -Descending | Select-Object -First 1; "
        'if ($gpu) { "$($gpu.Name)|$($gpu.AdapterRAM)" }'
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", command],
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).strip()
        if not out:
            return "", 0.0
        name, raw_bytes = (out.split("|", 1) + [""])[:2]
        # WMI AdapterRAM is occasionally missing or capped. It is only a fallback
        # when vendor tools such as nvidia-smi are unavailable.
        vram = round(max(0, int(raw_bytes or 0)) / (1024 ** 3), 1)
        return name.strip(), vram
    except Exception:
        return "", 0.0

def _recommended_num_ctx(ram_gb: float, vram_gb: float) -> int:
    # Conservative defaults: context KV cache grows quickly and models vary greatly.
    if vram_gb >= 24 or ram_gb >= 64:
        return 32768
    if vram_gb >= 16 or ram_gb >= 32:
        return 16384
    if vram_gb >= 8 or ram_gb >= 16:
        return 8192
    if ram_gb >= 8:
        return 4096
    return 2048


def detect_hardware() -> HardwareProfile:
    threads = max(1, int(os.cpu_count() or 1))
    ram = _ram_gb()
    gpu_name, vram = _nvidia_info()
    if not gpu_name:
        gpu_name, vram = _windows_gpu_info()
    recommended = _recommended_num_ctx(ram, vram)
    parallelism = 2 if (vram >= 16 or ram >= 32) and threads >= 8 else 1
    return HardwareProfile(
        cpu_threads=threads,
        ram_gb=ram,
        gpu_name=gpu_name,
        vram_gb=vram,
        recommended_num_ctx=recommended,
        recommended_parallelism=parallelism,
    )
