from __future__ import annotations

import ctypes
import ctypes.wintypes

import customtkinter as ctk
from PIL import Image

from jin.config import JIN_IMAGE

BG = "#010805"
PANEL = "#03140a"
GREEN = "#39ff6a"
DIM = "#1a8f3d"
MONO = "Consolas"
WIDTH, HEIGHT = 340, 104


def work_area() -> tuple[int, int, int, int]:
    """Screen area without the taskbar, in physical pixels."""
    rect = ctypes.wintypes.RECT()
    spi_getworkarea = 0x0030
    ctypes.windll.user32.SystemParametersInfoW(spi_getworkarea, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right, rect.bottom


class MiniWindow(ctk.CTkToplevel):
    """Small always-on-top bubble that mirrors the main window's bubble and status."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=BG)
        self._drag = (0, 0)

        frame = ctk.CTkFrame(self, fg_color=PANEL, border_color=GREEN, border_width=2, corner_radius=14)
        frame.pack(fill="both", expand=True)

        self.face = None
        if JIN_IMAGE.exists():
            image = Image.open(JIN_IMAGE)
            image.thumbnail((64, 80))
            self.face = ctk.CTkLabel(
                frame,
                text="",
                image=ctk.CTkImage(light_image=image, dark_image=image, size=image.size),
                cursor="hand2",
            )
            self.face.pack(side="left", padx=(10, 4), pady=8)
            self.face.bind("<Button-1>", lambda _event: app.toggle_mic())

        middle = ctk.CTkFrame(frame, fg_color="transparent")
        middle.pack(side="left", fill="both", expand=True, pady=8)
        self.status = ctk.CTkLabel(middle, text="", text_color=DIM, font=ctk.CTkFont(family=MONO, size=10), anchor="w")
        self.status.pack(fill="x")
        self.text = ctk.CTkLabel(
            middle,
            text="",
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=11, weight="bold"),
            wraplength=190,
            justify="left",
            anchor="nw",
        )
        self.text.pack(fill="both", expand=True)

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(side="right", padx=(4, 10), pady=8)
        self.mic = self._button(buttons, "MIC", app.toggle_mic)
        self.mic.pack(pady=(0, 6))
        self._button(buttons, "⤢", app.exit_mini).pack()

        for widget in (frame, middle, self.status, self.text):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)
            widget.bind("<Double-Button-1>", lambda _event: app.exit_mini())

        self._place_default()
        self._sync()

    def _button(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            width=48,
            height=30,
            fg_color=BG,
            hover_color="#0a2a14",
            border_color=GREEN,
            border_width=1,
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=11, weight="bold"),
            command=command,
        )

    def _place_default(self) -> None:
        scale = ctk.ScalingTracker.get_window_scaling(self)
        _left, _top, right, bottom = work_area()
        x = right - int(WIDTH * scale) - 16
        y = bottom - int(HEIGHT * scale) - 16
        self.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    def _start_drag(self, event) -> None:
        self._drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _on_drag(self, event) -> None:
        self.geometry(f"+{event.x_root - self._drag[0]}+{event.y_root - self._drag[1]}")

    def _sync(self) -> None:
        if not self.winfo_exists():
            return
        text = str(self.app.bubble.cget("text") or "")
        if len(text) > 120:
            text = "…" + text[-120:]
        self.text.configure(text=text)
        self.status.configure(text=str(self.app.status_dot.cget("text") or "").replace("●", "").strip())
        recording = self.app.recorder.recording
        self.mic.configure(
            text="STOP" if recording else "MIC",
            text_color="#ff5f56" if recording else GREEN,
            border_color="#ff5f56" if recording else GREEN,
        )
        self.after(300, self._sync)
