from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeechModel:
    model_id: str
    runtime: str
    backend: str
    model_argument: str
    purpose: str
    label: str
    languages: str
    voice_mode: str = "none"


# This catalog is deliberately closed. Every entry below is documented by the
# runtime that loads it. An arbitrary Hugging Face/GGUF identifier must not be
# routed to a merely similar architecture.
VIBEVOICE_TTS_MODELS: tuple[SpeechModel, ...] = (
    SpeechModel(
        model_id="vibevoice_realtime_0_5b",
        runtime="crispasr",
        backend="vibevoice-tts",
        model_argument="auto",
        purpose="tts",
        label="VibeVoice Realtime 0.5B (GGUF, preset voices)",
        languages="en, zh",
        voice_mode="preset",
    ),
    SpeechModel(
        model_id="vibevoice_1_5b",
        runtime="crispasr",
        backend="vibevoice-1.5b",
        model_argument="auto",
        purpose="tts",
        label="VibeVoice 1.5B (GGUF, generic voice / WAV cloning)",
        languages="en, zh",
        voice_mode="reference_wav",
    ),
)

VIBEVOICE_ASR_MODELS: tuple[SpeechModel, ...] = (
    SpeechModel(
        model_id="vibevoice_asr_7b",
        runtime="crispasr",
        backend="vibevoice",
        model_argument="auto",
        purpose="asr",
        label="VibeVoice ASR 7B (GGUF, multilingual incl. German)",
        languages="50+ languages including de, en, fr, es, it, ja, ko, pt, ru, zh",
    ),
    SpeechModel(
        model_id="vibevoice_asr_bitnet",
        runtime="crispasr",
        backend="vibevoice-bitnet",
        model_argument="auto",
        purpose="asr",
        label="VibeVoice ASR BitNet (GGUF/TQ2_0, ~1.6 GB)",
        languages="en, zh, fr, it, ko, pt, vi",
    ),
)

PYTHON_REALTIME_TTS_MODEL = "microsoft/VibeVoice-Realtime-0.5B"


def _find_model(models: tuple[SpeechModel, ...], model_id: object) -> SpeechModel:
    value = str(model_id or "").strip()
    for model in models:
        if model.model_id == value:
            return model
    raise ValueError(f"Unsupported or incompatible speech model: {value or '<empty>'}")


def get_vibevoice_tts_model(model_id: object) -> SpeechModel:
    return _find_model(VIBEVOICE_TTS_MODELS, model_id)


def get_vibevoice_asr_model(model_id: object) -> SpeechModel:
    return _find_model(VIBEVOICE_ASR_MODELS, model_id)


def normalize_vibevoice_tts_model(model_id: object) -> str:
    try:
        return get_vibevoice_tts_model(model_id).model_id
    except ValueError:
        return VIBEVOICE_TTS_MODELS[0].model_id


def normalize_vibevoice_asr_model(model_id: object) -> str:
    try:
        return get_vibevoice_asr_model(model_id).model_id
    except ValueError:
        return VIBEVOICE_ASR_MODELS[0].model_id
