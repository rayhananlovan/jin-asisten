from __future__ import annotations

from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from jin.config import AUDIO_DIR, ensure_dirs

SAMPLE_RATE = 16_000


class MicRecorder:
    def __init__(self) -> None:
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self.recording = False

    def start(self) -> None:
        if self.recording:
            return
        self._chunks = []
        self.recording = True
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._on_audio,
        )
        self._stream.start()

    def _on_audio(self, indata, frames, time, status) -> None:  # noqa: ANN001, ARG002
        if self.recording:
            self._chunks.append(indata.copy())

    def stop(self) -> Path:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.recording = False
        if not self._chunks:
            raise RuntimeError("Tidak ada suara yang terekam. Coba bicara lebih dekat ke mic.")
        ensure_dirs()
        audio = np.concatenate(self._chunks, axis=0)
        output_path = AUDIO_DIR / "user-input.wav"
        sf.write(output_path, audio, SAMPLE_RATE)
        return output_path
