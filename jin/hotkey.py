from __future__ import annotations

from typing import Callable

from pynput import keyboard

_MODIFIERS = {"ctrl": "<ctrl>", "alt": "<alt>", "shift": "<shift>", "win": "<cmd>", "cmd": "<cmd>"}


def to_pynput(combo: str) -> str:
    """'ctrl+alt+j' -> '<ctrl>+<alt>+j'; 'win+f9' -> '<cmd>+<f9>'."""
    parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
    if not parts:
        raise ValueError("Tombol pintas kosong.")
    out = []
    for part in parts:
        if part in _MODIFIERS:
            out.append(_MODIFIERS[part])
        elif len(part) == 1:
            out.append(part)
        else:
            out.append(f"<{part.strip('<>')}>")
    if not any(part.startswith("<") and part in _MODIFIERS.values() for part in out):
        raise ValueError("Pakai minimal satu dari ctrl, alt, shift, atau win.")
    keyboard.HotKey.parse("+".join(out))
    return "+".join(out)


class GlobalHotkey:
    def __init__(self, combo: str, on_press: Callable[[], None]) -> None:
        self._listener = keyboard.GlobalHotKeys({to_pynput(combo): on_press})
        self._listener.daemon = True

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        try:
            self._listener.stop()
        except Exception:
            pass
