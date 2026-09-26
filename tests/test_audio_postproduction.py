from __future__ import annotations

import math
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.audio_postproduction import (
    AudioPostproductionError,
    postproduction_output_path,
    render_postproduction_copy,
)


class AudioPostproductionTests(unittest.TestCase):
    @staticmethod
    def _write_tone(path: Path, *, sample_width: int = 2) -> None:
        rate = 16000
        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(sample_width)
            writer.setframerate(rate)
            if sample_width == 2:
                samples = array("h", [int(9000 * math.sin(2 * math.pi * 220 * frame / rate)) for frame in range(rate // 4)])
                writer.writeframes(samples.tobytes())
            else:
                writer.writeframes(bytes([128] * (rate // 4)))

    def test_effects_create_separate_wav_without_modifying_original(self):
        with tempfile.TemporaryDirectory(prefix="ovd_postproduction_") as temp_dir:
            source = Path(temp_dir) / "voice.wav"
            self._write_tone(source)
            original = source.read_bytes()
            output = render_postproduction_copy(source, chorus=45, echo=55, vocoder=30, reverb=40)
            self.assertEqual(output, postproduction_output_path(source))
            self.assertEqual(output.name, "voice_postproduction.wav")
            self.assertEqual(source.read_bytes(), original)
            self.assertTrue(output.is_file())
            self.assertNotEqual(output.read_bytes(), original)
            with wave.open(str(source), "rb") as before, wave.open(str(output), "rb") as after:
                self.assertEqual((after.getnchannels(), after.getsampwidth(), after.getframerate()),
                                 (before.getnchannels(), before.getsampwidth(), before.getframerate()))
                self.assertGreater(after.getnframes(), before.getnframes())
            self.assertFalse(list(Path(temp_dir).glob("*.tmp.wav")))

    def test_zero_effects_still_create_requested_separate_copy(self):
        with tempfile.TemporaryDirectory(prefix="ovd_postproduction_zero_") as temp_dir:
            source = Path(temp_dir) / "voice.wav"
            self._write_tone(source)
            output = render_postproduction_copy(source)
            self.assertTrue(output.is_file())
            with wave.open(str(source), "rb") as before, wave.open(str(output), "rb") as after:
                self.assertEqual(after.getnframes(), before.getnframes())

    def test_unsupported_wav_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory(prefix="ovd_postproduction_invalid_") as temp_dir:
            source = Path(temp_dir) / "voice.wav"
            self._write_tone(source, sample_width=1)
            with self.assertRaises(AudioPostproductionError):
                render_postproduction_copy(source, echo=50)
            self.assertFalse(postproduction_output_path(source).exists())


if __name__ == "__main__":
    unittest.main()
