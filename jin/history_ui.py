from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from jin import archive, db
from jin.config import OWNER_CALL

BG = "#010805"
PANEL = "#03140a"
GREEN = "#39ff6a"
DIM = "#1a8f3d"
MONO = "Consolas"
CHATS, NOTES = "OBROLAN", "CATATAN"


class HistoryWindow(ctk.CTkToplevel):
    def __init__(self, master) -> None:
        super().__init__(master)
        self.title("Riwayat Jin Asghard")
        self.geometry("620x680")
        self.configure(fg_color=BG)

        self.tabs = ctk.CTkSegmentedButton(
            self,
            values=[CHATS, NOTES],
            selected_color=GREEN,
            selected_hover_color="#73ff96",
            unselected_color=PANEL,
            text_color="#021108",
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            command=lambda _value: self.refresh(),
        )
        self.tabs.set(CHATS)
        self.tabs.pack(fill="x", padx=14, pady=(14, 6))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 6))
        self.query = ctk.CTkEntry(
            row,
            placeholder_text="cari kata...",
            placeholder_text_color=DIM,
            fg_color=BG,
            border_color=GREEN,
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=13),
        )
        self.query.pack(side="left", fill="x", expand=True)
        self.query.bind("<Return>", lambda _event: self.refresh())
        self._button(row, "CARI", self.refresh, filled=True).pack(side="left", padx=(6, 0))

        self.view = ctk.CTkTextbox(
            self,
            fg_color=PANEL,
            border_color=DIM,
            border_width=1,
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=12),
            wrap="word",
        )
        self.view.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=14, pady=(0, 14))
        self.count = ctk.CTkLabel(bottom, text="", text_color=DIM, font=ctk.CTkFont(family=MONO, size=11))
        self.count.pack(side="left")
        self._button(bottom, "EKSPOR KE MARKDOWN", self.export, filled=False).pack(side="right")
        self.refresh()
        self.after(100, self.query.focus_set)

    def _button(self, parent, text: str, command, filled: bool) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            fg_color=GREEN if filled else BG,
            text_color="#021108" if filled else GREEN,
            hover_color="#73ff96" if filled else "#0a2a14",
            border_color=GREEN,
            border_width=0 if filled else 1,
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            command=command,
        )

    def refresh(self) -> None:
        query = self.query.get().strip()
        lines: list[str] = []
        if self.tabs.get() == CHATS:
            messages = db.search_messages(query, limit=300)
            for message in messages:
                who = OWNER_CALL.upper() if message["role"] == "user" else "JIN"
                lines.append(f"[{archive.local_time(message['created_at'])}] {who}\n{message['content']}\n")
            total = f"{len(messages)} pesan" + (" (300 terbaru)" if len(messages) == 300 else "")
        else:
            notes = db.list_notes(query, limit=500)
            for note in notes:
                lines.append(
                    f"#{note['id']}  {note['title']}\n[{archive.local_time(note['created_at'])}]\n{note['content']}\n"
                )
            total = f"{len(notes)} catatan"
        self.view.configure(state="normal")
        self.view.delete("1.0", "end")
        self.view.insert("1.0", "\n".join(lines) or "Tidak ada yang cocok.")
        self.view.configure(state="disabled")
        self.count.configure(text=total)

    def export(self) -> None:
        notes = self.tabs.get() == NOTES
        name = "jin-catatan.md" if notes else "jin-obrolan.md"
        archive.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.asksaveasfilename(
            parent=self,
            initialdir=str(archive.EXPORT_DIR),
            initialfile=name,
            defaultextension=".md",
            filetypes=[("Markdown", "*.md")],
        )
        if not chosen:
            return
        query = self.query.get().strip()
        target = Path(chosen)
        if notes:
            target.write_text(archive.notes_markdown(query), encoding="utf-8")
        else:
            target.write_text(archive.chats_markdown(query), encoding="utf-8")
        messagebox.showinfo("Riwayat", f"Tersimpan di:\n{target}", parent=self)
