from __future__ import annotations

import struct
import sys
import wave
from array import array
from pathlib import Path

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QObject
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices


class MicrophoneRecorder(QObject):
    """Record with Qt Multimedia and write a portable PCM16 WAV file."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._source: QAudioSource | None = None
        self._buffer: QBuffer | None = None
        self._bytes = QByteArray()
        self._format: QAudioFormat | None = None

    @property
    def recording(self) -> bool:
        return self._source is not None

    def start(self) -> None:
        if self.recording:
            return
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            raise RuntimeError("Kein verfügbares Mikrofon gefunden.")

        requested = QAudioFormat()
        requested.setSampleRate(16000)
        requested.setChannelCount(1)
        requested.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        audio_format = requested if device.isFormatSupported(requested) else device.preferredFormat()
        if not audio_format.isValid() or audio_format.sampleFormat() == QAudioFormat.SampleFormat.Unknown:
            raise RuntimeError("Das Mikrofon stellt kein unterstütztes Audioformat bereit.")

        self._bytes.clear()
        self._buffer = QBuffer(self._bytes, self)
        if not self._buffer.open(QIODevice.OpenModeFlag.WriteOnly):
            self._buffer = None
            raise RuntimeError("Der Aufnahmepuffer konnte nicht geöffnet werden.")
        self._format = audio_format
        self._source = QAudioSource(device, audio_format, self)
        self._source.start(self._buffer)

    def stop(self, target: Path) -> Path:
        if not self.recording or self._buffer is None or self._format is None:
            raise RuntimeError("Es läuft keine Mikrofonaufnahme.")
        source = self._source
        buffer = self._buffer
        audio_format = self._format
        self._source = None
        self._buffer = None
        self._format = None
        source.stop()
        buffer.close()
        raw = bytes(self._bytes)
        source.deleteLater()
        buffer.deleteLater()
        if not raw:
            raise RuntimeError("Das Mikrofon hat keine Audiodaten geliefert.")

        pcm = self._to_pcm16(raw, audio_format)
        if not pcm:
            raise RuntimeError("Die Mikrofonaufnahme konnte nicht konvertiert werden.")
        output = Path(target).with_suffix(".wav")
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_name(f".{output.name}.recording.tmp.wav")
        try:
            with wave.open(str(temp), "wb") as wav:
                wav.setnchannels(max(1, audio_format.channelCount()))
                wav.setsampwidth(2)
                wav.setframerate(max(8000, audio_format.sampleRate()))
                wav.writeframes(pcm)
            temp.replace(output)
        finally:
            temp.unlink(missing_ok=True)
        return output

    def cancel(self) -> None:
        if self._source is not None:
            self._source.stop()
            self._source.deleteLater()
        if self._buffer is not None:
            self._buffer.close()
            self._buffer.deleteLater()
        self._source = None
        self._buffer = None
        self._format = None
        self._bytes.clear()

    @staticmethod
    def _to_pcm16(raw: bytes, audio_format: QAudioFormat) -> bytes:
        sample_format = audio_format.sampleFormat()
        if sample_format == QAudioFormat.SampleFormat.Int16:
            usable = len(raw) - (len(raw) % 2)
            return raw[:usable]

        values = array("h")
        if sample_format == QAudioFormat.SampleFormat.UInt8:
            values.extend((int(value) - 128) * 256 for value in raw)
        elif sample_format == QAudioFormat.SampleFormat.Int32:
            usable = len(raw) - (len(raw) % 4)
            integers = array("i")
            integers.frombytes(raw[:usable])
            if sys.byteorder != "little":
                integers.byteswap()
            values.extend(max(-32768, min(32767, value >> 16)) for value in integers)
        elif sample_format == QAudioFormat.SampleFormat.Float:
            usable = len(raw) - (len(raw) % 4)
            for (value,) in struct.iter_unpack("<f", raw[:usable]):
                values.append(max(-32768, min(32767, int(max(-1.0, min(1.0, value)) * 32767))))
        else:
            return b""
        if sys.byteorder != "little":
            values.byteswap()
        return values.tobytes()
