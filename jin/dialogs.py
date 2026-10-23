from __future__ import annotations

import customtkinter as ctk

BG = "#010805"
PANEL = "#03140a"
GREEN = "#39ff6a"
DIM = "#1a8f3d"
MONO = "Consolas"


class ConfirmDialog(ctk.CTkToplevel):
    """Modal yes/no. Not transient: the main window may be hidden in tray or mini mode."""

    def __init__(self, master, question: str) -> None:
        super().__init__(master)
        self.title("Konfirmasi Jin")
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.result = False

        frame = ctk.CTkFrame(self, fg_color=PANEL, border_color=GREEN, border_width=2, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(
            frame,
            text="JIN MINTA IZIN",
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=13, weight="bold"),
        ).pack(pady=(12, 4))
        ctk.CTkLabel(
            frame,
            text=question,
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=12),
            wraplength=380,
            justify="left",
        ).pack(padx=16, pady=(4, 12))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(pady=(0, 12))
        ctk.CTkButton(
            row,
            text="BATAL (Esc)",
            fg_color=BG,
            border_color=GREEN,
            border_width=1,
            text_color=GREEN,
            hover_color="#0a2a14",
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            command=self._no,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            row,
            text="LANJUTKAN (Enter)",
            fg_color=GREEN,
            text_color="#021108",
            hover_color="#73ff96",
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            command=self._yes,
        ).pack(side="left", padx=6)

        self.bind("<Return>", lambda _event: self._yes())
        self.bind("<Escape>", lambda _event: self._no())
        self.protocol("WM_DELETE_WINDOW", self._no)
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")
        self.after(50, self._grab)

    def _grab(self) -> None:
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass

    def _yes(self) -> None:
        self.result = True
        self.destroy()

    def _no(self) -> None:
        self.result = False
        self.destroy()


def ask(master, question: str) -> bool:
    dialog = ConfirmDialog(master, question)
    master.wait_window(dialog)
    return dialog.result
