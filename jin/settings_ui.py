from __future__ import annotations

from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

import os

from jin import settings
from jin.config import (
    APP_HOME,
    HOTKEY,
    JIN_CLIPBOARD,
    JIN_CONFIRM,
    JIN_PITCH,
    JIN_RATE,
    JIN_TRAY,
    JIN_VOICE,
    JIN_WAKE,
    OLLAMA_MODEL,
    OWNER_CALL,
    OWNER_NAME,
    PROJECTS_DIR,
    VISION_MODEL,
    WAKE_WORDS,
)
from jin.hotkey import to_pynput
from jin.logs import LOG_DIR
from jin.magic import _installed_models

BG = "#010805"
PANEL = "#03140a"
GREEN = "#39ff6a"
DIM = "#1a8f3d"
MONO = "Consolas"
VOICES = ["id-ID-ArdiNeural", "id-ID-GadisNeural"]
# Keys that only take effect after Jin restarts.
RESTART_KEYS = {
    "OWNER_NAME",
    "OWNER_CALL",
    "OLLAMA_MODEL",
    "JIN_VISION_MODEL",
    "JIN_VOICE",
    "JIN_RATE",
    "JIN_PITCH",
    "JIN_WAKE",
    "JIN_WAKE_WORDS",
    "JIN_PROJECTS_DIR",
}


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, on_applied: Callable[[dict[str, str]], None]) -> None:
        super().__init__(master)
        self.title("Pengaturan Jin Asghard")
        self.geometry("520x720")
        self.configure(fg_color=BG)
        self.transient(master)
        self.after(100, self.grab_set)
        self._on_applied = on_applied
        current = settings.read_env()
        models = _installed_models()

        def value(key: str, default: str) -> str:
            return current.get(key) or default

        body = ctk.CTkScrollableFrame(self, fg_color=PANEL, border_color=GREEN, border_width=1)
        body.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        self._fields: dict[str, Callable[[], str]] = {}

        self._section(body, "IDENTITAS")
        self._entry(body, "OWNER_NAME", "Nama pemilik", value("OWNER_NAME", OWNER_NAME))
        self._entry(body, "OWNER_CALL", "Panggilan", value("OWNER_CALL", OWNER_CALL))

        self._section(body, "OTAK (OLLAMA)")
        self._combo(body, "OLLAMA_MODEL", "Model chat", value("OLLAMA_MODEL", OLLAMA_MODEL), models)
        self._combo(
            body,
            "JIN_VISION_MODEL",
            "Model vision (pahami layar)",
            value("JIN_VISION_MODEL", VISION_MODEL),
            sorted(set(models + ["qwen2.5vl:3b", "qwen2.5vl:7b", "llava:7b"])),
        )

        self._section(body, "SUARA")
        self._combo(body, "JIN_VOICE", "Suara", value("JIN_VOICE", JIN_VOICE), VOICES)
        self._entry(body, "JIN_RATE", "Kecepatan (mis. -22%)", value("JIN_RATE", JIN_RATE))
        self._entry(body, "JIN_PITCH", "Nada (mis. -50Hz)", value("JIN_PITCH", JIN_PITCH))

        self._section(body, "PANGGILAN SUARA")
        self._switch(body, "JIN_WAKE", "Dengarkan kata panggil", value("JIN_WAKE", "1" if JIN_WAKE else "0"))
        self._entry(
            body,
            "JIN_WAKE_WORDS",
            "Kata panggil (pisah koma)",
            value("JIN_WAKE_WORDS", ",".join(WAKE_WORDS)),
        )
        self._entry(
            body,
            "JIN_HOTKEY",
            "Tombol pintas panggil Jin (mis. ctrl+alt+j, win+j; kosong = mati)",
            current.get("JIN_HOTKEY", HOTKEY),
        )

        self._section(body, "KERJA")
        self._folder(body, "JIN_PROJECTS_DIR", "Folder project", value("JIN_PROJECTS_DIR", str(PROJECTS_DIR)))
        self._switch(
            body,
            "JIN_CLIPBOARD",
            "Tawarkan ringkas/terjemah saat copy teks",
            value("JIN_CLIPBOARD", "1" if JIN_CLIPBOARD else "0"),
        )
        self._switch(
            body,
            "JIN_CONFIRM",
            "Minta izin sebelum commit, push, install, kunci laptop",
            value("JIN_CONFIRM", "1" if JIN_CONFIRM else "0"),
        )

        self._section(body, "APLIKASI")
        self._switch(body, "JIN_TRAY", "Tombol tutup = sembunyi ke tray", value("JIN_TRAY", "1" if JIN_TRAY else "0"))
        self._autostart = ctk.CTkSwitch(
            body,
            text="Jalan otomatis saat Windows menyala",
            progress_color=GREEN,
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=12),
        )
        self._autostart.pack(anchor="w", padx=12, pady=6)
        if settings.autostart_enabled():
            self._autostart.select()

        self._label(body, f"Folder data: {APP_HOME}")
        folders = ctk.CTkFrame(body, fg_color="transparent")
        folders.pack(fill="x", padx=12, pady=(2, 10))
        for text, folder in (("BUKA FOLDER DATA", APP_HOME), ("BUKA LOG", LOG_DIR)):
            ctk.CTkButton(
                folders,
                text=text,
                fg_color=BG,
                border_color=DIM,
                border_width=1,
                text_color=GREEN,
                hover_color="#0a2a14",
                font=ctk.CTkFont(family=MONO, size=11),
                command=lambda path=folder: os.startfile(path),  # noqa: S606
            ).pack(side="left", padx=(0, 6))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkButton(
            row,
            text="BATAL",
            fg_color=BG,
            border_color=GREEN,
            border_width=1,
            text_color=GREEN,
            hover_color="#0a2a14",
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            command=self.destroy,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            row,
            text="SIMPAN",
            fg_color=GREEN,
            text_color="#021108",
            hover_color="#73ff96",
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            command=self._save,
        ).pack(side="right")

    def _label(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text, text_color=DIM, font=ctk.CTkFont(family=MONO, size=11)).pack(
            anchor="w", padx=12, pady=(6, 0)
        )

    def _section(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=f"── {text}",
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
        ).pack(anchor="w", padx=8, pady=(14, 2))

    def _entry(self, parent, key: str, label: str, value: str) -> None:
        self._label(parent, label)
        entry = ctk.CTkEntry(parent, fg_color=BG, border_color=DIM, text_color=GREEN, font=ctk.CTkFont(family=MONO, size=12))
        entry.insert(0, value)
        entry.pack(fill="x", padx=12, pady=(2, 4))
        self._fields[key] = lambda: entry.get().strip()

    def _combo(self, parent, key: str, label: str, value: str, options: list[str]) -> None:
        self._label(parent, label)
        combo = ctk.CTkComboBox(
            parent,
            values=options or [value],
            fg_color=BG,
            border_color=DIM,
            button_color=DIM,
            text_color=GREEN,
            dropdown_fg_color=PANEL,
            dropdown_text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=12),
        )
        combo.set(value)
        combo.pack(fill="x", padx=12, pady=(2, 4))
        self._fields[key] = lambda: combo.get().strip()

    def _switch(self, parent, key: str, label: str, value: str) -> None:
        switch = ctk.CTkSwitch(
            parent,
            text=label,
            progress_color=GREEN,
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=12),
        )
        if value.strip() != "0":
            switch.select()
        switch.pack(anchor="w", padx=12, pady=6)
        self._fields[key] = lambda: "1" if switch.get() else "0"

    def _folder(self, parent, key: str, label: str, value: str) -> None:
        self._label(parent, label)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(2, 4))
        entry = ctk.CTkEntry(row, fg_color=BG, border_color=DIM, text_color=GREEN, font=ctk.CTkFont(family=MONO, size=12))
        entry.insert(0, value)
        entry.pack(side="left", fill="x", expand=True)

        def browse() -> None:
            chosen = filedialog.askdirectory(parent=self, initialdir=entry.get() or None)
            if chosen:
                entry.delete(0, "end")
                entry.insert(0, chosen)

        ctk.CTkButton(
            row,
            text="...",
            width=40,
            fg_color=BG,
            border_color=DIM,
            border_width=1,
            text_color=GREEN,
            hover_color="#0a2a14",
            command=browse,
        ).pack(side="left", padx=(6, 0))
        self._fields[key] = lambda: entry.get().strip()

    def _save(self) -> None:
        before = settings.read_env()
        updates = {key: getter() for key, getter in self._fields.items()}
        if updates.get("JIN_HOTKEY"):
            try:
                to_pynput(updates["JIN_HOTKEY"])
            except ValueError as exc:
                messagebox.showerror("Pengaturan", f"Tombol pintas tidak valid:\n{exc}", parent=self)
                return
        try:
            settings.write_env(updates)
            settings.set_autostart(bool(self._autostart.get()))
        except OSError as exc:
            messagebox.showerror("Pengaturan", f"Gagal menyimpan pengaturan:\n{exc}", parent=self)
            return
        changed = {key: value for key, value in updates.items() if before.get(key, "") != value}
        self._on_applied(updates)
        needs_restart = any(key in RESTART_KEYS for key in changed)
        self.destroy()
        if needs_restart and messagebox.askyesno(
            "Pengaturan",
            "Tersimpan. Sebagian perubahan baru berlaku setelah Jin dibuka ulang.\nBuka ulang sekarang?",
        ):
            self.master.restart()
