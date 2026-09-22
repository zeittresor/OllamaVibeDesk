"""Conservative request-time policy. Estimates are limits, never an OOM guarantee."""
from __future__ import annotations

import math
import subprocess
from urllib.parse import urlparse
import requests

GIB = 1024 ** 3


def is_local_endpoint(url: str) -> bool:
    return urlparse(url).hostname in {"localhost", "127.0.0.1", "::1"}


def collect_runtime(base_url: str, model: str) -> dict:
    """Run outside the Qt thread. Missing probes degrade to bounded defaults."""
    result = {"local": is_local_endpoint(base_url), "model": model, "running": {}, "info": {}}
    for path, payload, key in (("/api/ps", None, "running"), ("/api/show", {"model": model}, "info")):
        try:
            with (requests.get(base_url.rstrip('/') + path, timeout=(2, 3)) if payload is None else
                  requests.post(base_url.rstrip('/') + path, json=payload, timeout=(2, 3))) as response:
                response.raise_for_status()
                data = response.json()
            if key == "running":
                names = {model, model + ":latest"}
                data = next((m for m in data.get("models", []) if m.get("name") in names or m.get("model") in names), {})
            result[key] = data
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            pass
    if result["local"]:
        try:
            import psutil
            ram = psutil.virtual_memory()
            result.update(ram_total=ram.total, ram_available=ram.available)
        except Exception:
            pass
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"],
                text=True, timeout=2, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stderr=subprocess.DEVNULL,
            )
            result["gpus"] = [tuple(float(v.strip()) * 1024 ** 2 for v in line.split(','))
                              for line in output.strip().splitlines()]
        except Exception:
            result["gpus"] = []
    return result


def model_limits(info: dict) -> tuple[int, int]:
    """Native context and pessimistic F16 KV bytes/token; unknown architectures don't grow."""
    data = info.get("model_info", {}) or {}
    arch = data.get("general.architecture", "")
    def field(name):
        try:
            return max(0, int(data.get(f"{arch}.{name}", 0) or 0))
        except (ValueError, TypeError):
            return 0
    native = field("context_length")
    layers, heads, kv_heads, embedding = (field(k) for k in
        ("block_count", "attention.head_count", "attention.head_count_kv", "embedding_length"))
    key = field("attention.key_length") or (embedding // heads if heads else 0)
    value = field("attention.value_length") or key
    # Recurrent/MLA architectures cannot be sized reliably from these generic fields.
    known = arch in {"llama", "qwen2", "qwen3", "gemma", "gemma2", "gemma3", "mistral", "phi3"}
    kv = math.ceil(layers * kv_heads * (key + value) * 2 * 1.5) if known else 0
    return native, kv


def choose_context(snapshot: dict, demand: int, ceiling: int = 32768,
                   previous: int = 0, failure_cap: int = 0, automatic: bool = True) -> dict:
    native, kv = model_limits(snapshot.get("info", {}))
    cap = max(2048, int(ceiling))
    if native:
        cap = min(cap, native)
    if failure_cap:
        cap = min(cap, failure_cap)
    running = snapshot.get("running", {}) or {}
    loaded_ctx = max(0, int(running.get("context_length", 0) or 0))
    baseline = min(cap, previous or loaded_ctx or 4096)
    limit = cap if not automatic else baseline
    reason = "manual" if not automatic else "conservative"
    ram_total = snapshot.get("ram_total", 0)
    ram_free = snapshot.get("ram_available", 0)
    ram_reserve = max(2 * GIB, ram_total * .15)
    pressure = bool(snapshot.get("local") and ram_total and ram_free < ram_reserve)
    gpus = snapshot.get("gpus", [])
    gpu_loaded = int(running.get("size_vram", 0) or 0) > 0
    if snapshot.get("local") and gpu_loaded:
        pressure |= any(free < max(.75 * GIB, total * .08) for total, free in gpus)
    # Only grow a loaded, measured model. Initial model weight/runtime allocations
    # and remote or ambiguous multi-GPU placement must not be guessed from local RAM.
    if automatic and snapshot.get("local") and loaded_ctx and kv and ram_total:
        ram_tokens = loaded_ctx + int((ram_free - ram_reserve - .5 * GIB) / kv)
        if gpu_loaded:
            if len(gpus) == 1:
                total, free = gpus[0]
                gpu_tokens = loaded_ctx + int((free - max(GIB, total * .12) - .5 * GIB) / kv)
                limit = min(cap, ram_tokens, gpu_tokens)
                reason = "measured_ram_vram"
        else:
            limit = min(cap, ram_tokens)
            reason = "measured_ram"
    if pressure:
        limit = min(limit, max(2048, baseline // 2))
        reason = "memory_pressure"
    blocked = bool(snapshot.get("local") and ((ram_total and ram_free < max(.5 * GIB, ram_total * .02)) or (pressure and limit < min(2048, cap))))
    limit = max(min(2048, cap), min(cap, limit))
    if automatic:
        # Grow in bounded steps only when the prompt needs the space; hold stable
        # after success to avoid reloading the model for every short response.
        wanted = max(baseline, int(math.ceil(max(1, demand) / 2048)) * 2048)
        chosen = min(limit, wanted, max(4096, baseline * 2))
    else:
        chosen = limit
    return {"num_ctx": int(chosen), "reason": reason, "pressure": pressure, "blocked": blocked,
            "native_limit": native, "kv_bytes_per_token_estimated": kv,
            "ram_available": ram_free, "ram_reserve": int(ram_reserve) if ram_total else 0,
            "gpus": gpus, "local": bool(snapshot.get("local"))}


def is_memory_error(message: str) -> bool:
    text = str(message).lower()
    return any(part in text for part in ("out of memory", "out-of-memory", "cuda error: out",
        "cannot allocate memory", "failed to allocate", "unable to allocate", "not enough memory",
        "requires more system memory", "insufficient memory", "cuda malloc", "cudamalloc"))
