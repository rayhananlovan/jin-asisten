from __future__ import annotations

import threading
from typing import Callable

import pystray
from PIL import Image, ImageDraw

from jin.config import JIN_IMAGE


def _icon_image() -> Image.Image:
    if JIN_IMAGE.exists():
        image = Image.open(JIN_IMAGE).convert("RGBA")
        image.thumbnail((64, 64))
        canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        canvas.paste(image, ((64 - image.width) // 2, (64 - image.height) // 2), image)
        return canvas
    canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).ellipse((4, 4, 60, 60), fill=(57, 255, 106, 255))
    return canvas


class JinTray:
    """System tray icon. Callbacks run on the pystray thread; marshal to Tk yourself."""

    def __init__(
        self,
        on_show: Callable[[], None],
        on_mic: Callable[[], None],
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Tampilkan Jin", lambda: on_show(), default=True),
            pystray.MenuItem("Dengarkan (mic)", lambda: on_mic()),
            pystray.MenuItem("Pengaturan", lambda: on_settings()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Keluar", lambda: on_quit()),
        )
        self._icon = pystray.Icon("JinAsghard", _icon_image(), "Jin Asghard", menu)

    def start(self) -> None:
        threading.Thread(target=self._icon.run, daemon=True).start()

    def notify(self, message: str) -> None:
        try:
            self._icon.notify(message, "Jin Asghard")
        except Exception:
            pass

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:
            pass
