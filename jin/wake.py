from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable

import numpy as np
import sounddevice as sd
import soundfile as sf

from jin.config import AUDIO_DIR, WAKE_WORDS, ensure_dirs
from jin.stt import transcribe

SAMPLE_RATE = 16_000
BLOCK = 1024
ENERGY_ON = 0.012
ENERGY_OFF = 0.006
MIN_SPEECH_SEC = 0.45
MAX_SPEECH_SEC = 4.5
SILENCE_END_SEC = 0.55
COOLDOWN_SEC = 2.2

_PREFIX = r"(?:he[iy]\s+|halo\s+|hai\s+|oy+\s+|oi+\s+|eh\s+)?"


class WakeListener:
    """Background mic: hear wake word → summon Jin (optionally with a command)."""

    def __init__(
        self,
        on_wake: Callable[[str], None],
        is_blocked: Callable[[], bool],
    ) -> None:
        self._on_wake = on_wake
        self._is_blocked = is_blocked
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._words = tuple(w.lower().strip() for w in WAKE_WORDS if w.strip())
        self._cooldown_until = 0.0
        alts = "|".join(re.escape(w) for w in self._words) or "jin"
        self._wake_re = re.compile(
            rf"^{_PREFIX}(?:(?:{alts})\b(?:\s+asghard)?|asghard\b)",
            re.IGNORECASE,
        )
        self._wake_only_re = re.compile(
            rf"^{_PREFIX}(?:(?:{alts})\b(?:\s+asghard)?|asghard\b)\s*$",
            re.IGNORECASE,
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not self._words:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="jin-wake")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def nudge_cooldown(self, seconds: float = COOLDOWN_SEC) -> None:
        self._cooldown_until = time.monotonic() + seconds

    def _busy(self) -> bool:
        return self._is_blocked() or time.monotonic() < self._cooldown_until

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._busy():
                time.sleep(0.12)
                continue
            try:
                self._listen_session()
            except Exception:
                time.sleep(0.6)

    def _listen_session(self) -> None:
        speech: list[np.ndarray] = []
        hearing = False
        silence = 0.0
        spoken = 0.0
        # Hold the mic only while wake is allowed; release for MIC / busy.
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK,
        ) as stream:
            while not self._stop.is_set() and not self._busy():
                try:
                    data, _overflowed = stream.read(BLOCK)
                except Exception:
                    time.sleep(0.05)
                    continue

                chunk = np.asarray(data, dtype=np.float32).reshape(-1)
                if chunk.size == 0:
                    continue
                energy = float(np.sqrt(np.mean(np.square(chunk))))
                dt = chunk.size / SAMPLE_RATE

                if not hearing:
                    if energy >= ENERGY_ON:
                        hearing = True
                        speech = [chunk.copy()]
                        spoken = dt
                        silence = 0.0
                    continue

                speech.append(chunk.copy())
                spoken += dt
                if energy < ENERGY_OFF:
                    silence += dt
                else:
                    silence = 0.0

                if spoken >= MAX_SPEECH_SEC or (
                    silence >= SILENCE_END_SEC and spoken >= MIN_SPEECH_SEC
                ):
                    audio = np.concatenate(speech, axis=0)
                    speech.clear()
                    hearing = False
                    silence = 0.0
                    spoken = 0.0
                    self._maybe_fire(audio)

    def _maybe_fire(self, audio: np.ndarray) -> None:
        if self._busy():
            return
        if float(np.sqrt(np.mean(np.square(audio)))) < ENERGY_OFF:
            return
        ensure_dirs()
        path = AUDIO_DIR / "wake-snippet.wav"
        try:
            sf.write(path, audio, SAMPLE_RATE)
            text = (transcribe(path) or "").strip()
        except Exception:
            return
        if not text:
            return
        command = self._extract_command(text)
        if command is None:
            return
        self.nudge_cooldown()
        try:
            self._on_wake(command)
        except Exception:
            pass

    def _extract_command(self, text: str) -> str | None:
        lower = text.lower().strip()
        if self._wake_only_re.match(lower):
            return ""
        matched = self._wake_re.match(lower)
        if not matched:
            return None
        return text[matched.end() :].strip(" ,.")
