from __future__ import annotations

import asyncio
import subprocess
import threading
import uuid

import edge_tts
import pygame

from jin.config import AUDIO_DIR, JIN_PITCH, JIN_RATE, JIN_VOICE, ensure_dirs

_LOCK = threading.Lock()


def _init_mixer() -> None:
    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=512)


def _run_async(coro) -> None:
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


def _chunks(text: str, limit: int = 220) -> list[str]:
    parts: list[str] = []
    current = ""
    for piece in text.replace("\n", " ").split(" "):
        if not piece:
            continue
        trial = f"{current} {piece}".strip()
        if len(trial) > limit and current:
            parts.append(current)
            current = piece
        else:
            current = trial
    if current:
        parts.append(current)
    return parts or [text]


def _speak_windows(text: str) -> None:
    """Offline fallback via Windows SAPI when edge-tts is rejected."""
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate = -2; "
        "$s.Speak([Console]::In.ReadToEnd())"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        input=text,
        text=True,
        encoding="utf-8",
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )


def speak(text: str) -> None:
    spoken = " ".join(text.strip().split())
    if not spoken:
        return
    ensure_dirs()
    with _LOCK:
        _init_mixer()
        pygame.mixer.stop()
        for chunk in _chunks(spoken):
            output_path = AUDIO_DIR / f"jin-{uuid.uuid4().hex}.mp3"
            try:
                _run_async(
                    edge_tts.Communicate(
                        chunk,
                        JIN_VOICE,
                        rate=JIN_RATE,
                        pitch=JIN_PITCH,
                    ).save(str(output_path))
                )
            except Exception:
                output_path.unlink(missing_ok=True)
                _speak_windows(chunk)
                continue
            pygame.mixer.music.stop()
            if hasattr(pygame.mixer.music, "unload"):
                pygame.mixer.music.unload()
            pygame.mixer.music.load(str(output_path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.delay(80)
            pygame.mixer.music.stop()
            if hasattr(pygame.mixer.music, "unload"):
                pygame.mixer.music.unload()
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
