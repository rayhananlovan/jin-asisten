from __future__ import annotations

from pathlib import Path

from jin.config import WHISPER_MODEL

_model = None


def _load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _model


def transcribe(audio_path: Path) -> str:
    model = _load_model()
    segments, _info = model.transcribe(str(audio_path), language="id")
    return " ".join(segment.text.strip() for segment in segments).strip()
