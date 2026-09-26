from __future__ import annotations

import math
import os
import sys
import uuid
import wave
from array import array
from pathlib import Path


POSTPRODUCTION_SUFFIX = "_postproduction"
MAX_INPUT_BYTES = 256 * 1024 * 1024


class AudioPostproductionError(RuntimeError):
    pass


def _strength(value: object) -> float:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(0, min(100, number)) / 100.0


def _sample(samples: array, frame: int, channel: int, channels: int, frame_count: int) -> float:
    if frame < 0 or frame >= frame_count:
        return 0.0
    return float(samples[frame * channels + channel])


def _clamp_sample(value: float) -> int:
    return max(-32768, min(32767, int(round(value))))


def postproduction_output_path(source_path: Path) -> Path:
    source = Path(source_path)
    return source.with_name(f"{source.stem}{POSTPRODUCTION_SUFFIX}.wav")


def render_postproduction_copy(
    source_path: Path,
    *,
    chorus: int = 0,
    echo: int = 0,
    vocoder: int = 0,
    reverb: int = 0,
) -> Path:
    """Render a separate 16-bit PCM WAV while leaving the source untouched."""
    source = Path(source_path)
    if source.suffix.lower() != ".wav" or not source.is_file():
        raise AudioPostproductionError("Audio postproduction requires an existing WAV file.")
    if source.stat().st_size > MAX_INPUT_BYTES:
        raise AudioPostproductionError("The WAV file is too large for safe local postproduction.")

    try:
        with wave.open(str(source), "rb") as reader:
            params = reader.getparams()
            if params.sampwidth != 2 or params.comptype != "NONE" or params.nchannels not in {1, 2}:
                raise AudioPostproductionError("Only mono/stereo 16-bit PCM WAV files are supported.")
            raw_frames = reader.readframes(params.nframes)
    except AudioPostproductionError:
        raise
    except (OSError, wave.Error) as exc:
        raise AudioPostproductionError(f"The WAV file could not be read: {exc}") from exc

    samples = array("h")
    samples.frombytes(raw_frames)
    if sys.byteorder != "little":
        samples.byteswap()
    channels = params.nchannels
    frame_count = len(samples) // channels
    if frame_count <= 0:
        raise AudioPostproductionError("The WAV file contains no audio frames.")

    chorus_mix = _strength(chorus)
    echo_mix = _strength(echo)
    vocoder_mix = _strength(vocoder)
    reverb_mix = _strength(reverb)
    rate = params.framerate
    echo_delay = max(1, int(rate * 0.22))
    reverb_delays = (max(1, int(rate * 0.043)), max(1, int(rate * 0.079)), max(1, int(rate * 0.127)))
    tail_frames = max(echo_delay if echo_mix else 0, reverb_delays[-1] if reverb_mix else 0)
    output_frames = frame_count + tail_frames
    rendered = array("h")

    for frame in range(output_frames):
        chorus_delay = int(rate * (0.018 + 0.004 * math.sin(2.0 * math.pi * 0.75 * frame / rate)))
        carrier = math.sin(2.0 * math.pi * 52.0 * frame / rate)
        for channel in range(channels):
            dry = _sample(samples, frame, channel, channels, frame_count)
            value = dry
            if chorus_mix:
                delayed = _sample(samples, frame - chorus_delay, channel, channels, frame_count)
                value += delayed * 0.42 * chorus_mix
                value *= 1.0 / (1.0 + 0.24 * chorus_mix)
            if echo_mix:
                value += _sample(samples, frame - echo_delay, channel, channels, frame_count) * 0.48 * echo_mix
            if reverb_mix:
                value += _sample(samples, frame - reverb_delays[0], channel, channels, frame_count) * 0.22 * reverb_mix
                value += _sample(samples, frame - reverb_delays[1], channel, channels, frame_count) * 0.15 * reverb_mix
                value += _sample(samples, frame - reverb_delays[2], channel, channels, frame_count) * 0.10 * reverb_mix
            if vocoder_mix:
                robotic = value * (0.34 + 0.66 * carrier)
                value = value * (1.0 - vocoder_mix) + robotic * vocoder_mix
            rendered.append(_clamp_sample(value))

    if sys.byteorder != "little":
        rendered.byteswap()
    output = postproduction_output_path(source)
    temp = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp.wav")
    try:
        with wave.open(str(temp), "wb") as writer:
            writer.setnchannels(params.nchannels)
            writer.setsampwidth(params.sampwidth)
            writer.setframerate(params.framerate)
            writer.setcomptype(params.comptype, params.compname)
            writer.writeframes(rendered.tobytes())
        os.replace(temp, output)
    except (OSError, wave.Error) as exc:
        temp.unlink(missing_ok=True)
        raise AudioPostproductionError(f"The postprocessed WAV file could not be written: {exc}") from exc
    return output
