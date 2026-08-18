from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceStyle:
    style_id: str
    rate_delta: int = 0
    pitch_delta: int = 0
    volume_delta: int = 0
    effect: str = "none"


# These presets deliberately stay backend-independent. Windows SAPI receives
# native rate/pitch values; VibeVoice WAV output gets a conservative local
# post-processing effect where its OpenAI-compatible wrapper lacks controls.
VOICE_STYLES: dict[str, VoiceStyle] = {
    "natural": VoiceStyle("natural"),
    "masculine": VoiceStyle("masculine", rate_delta=-1, pitch_delta=-4),
    "feminine": VoiceStyle("feminine", rate_delta=1, pitch_delta=4),
    "narrator": VoiceStyle("narrator", rate_delta=-2, pitch_delta=-2, volume_delta=2),
    "dramatic": VoiceStyle("dramatic", rate_delta=-1, pitch_delta=-1, volume_delta=4, effect="presence"),
    "robotic": VoiceStyle("robotic", rate_delta=-1, pitch_delta=-1, effect="robotic"),
    "tipsy": VoiceStyle("tipsy", rate_delta=-3, pitch_delta=-2, effect="tipsy"),
    "comic": VoiceStyle("comic", rate_delta=2, pitch_delta=5, effect="comic"),
    "whisper": VoiceStyle("whisper", rate_delta=-2, pitch_delta=1, volume_delta=-18, effect="whisper"),
}

VOICE_STYLE_IDS = tuple(VOICE_STYLES)


def clamp_int(value: object, minimum: int, maximum: int, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def normalize_voice_style(value: object) -> str:
    style_id = str(value or "natural").strip().lower()
    return style_id if style_id in VOICE_STYLES else "natural"


def effective_voice_controls(
    style_id: object,
    intensity: object,
    base_rate: object,
    base_pitch: object,
    base_volume: object,
) -> tuple[int, int, int, str, int]:
    """Return rate, pitch, volume, effect and normalized intensity."""
    normalized_style = normalize_voice_style(style_id)
    style = VOICE_STYLES[normalized_style]
    normalized_intensity = clamp_int(intensity, 0, 100, 65)
    factor = normalized_intensity / 100.0
    rate = clamp_int(round(clamp_int(base_rate, -10, 10) + style.rate_delta * factor), -10, 10)
    pitch = clamp_int(round(clamp_int(base_pitch, -10, 10) + style.pitch_delta * factor), -10, 10)
    volume = clamp_int(round(clamp_int(base_volume, 0, 100, 100) + style.volume_delta * factor), 0, 100, 100)
    return rate, pitch, volume, style.effect, normalized_intensity
