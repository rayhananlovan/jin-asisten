from __future__ import annotations

import re
import threading
from datetime import datetime

import customtkinter as ctk
from PIL import Image

from jin import db, dialogs, health, settings
from jin.actions import windows_toast
from jin.config import (
    HOTKEY,
    JIN_CLIPBOARD,
    JIN_CONFIRM,
    JIN_IMAGE,
    JIN_SPEAK,
    JIN_TRAY,
    JIN_WAKE,
    MOOD_IMAGES,
    OWNER_CALL,
)
from jin.history_ui import HistoryWindow
from jin.hotkey import GlobalHotkey
from jin.llm import reply
from jin.logs import log
from jin.magic import current_form, cycle_form, looks_like_code, new_clipboard_text
from jin.mini import MiniWindow
from jin.smart import code_shadow, save_context, start_window_watcher
from jin.recorder import MicRecorder
from jin.settings_ui import SettingsWindow
from jin.stt import transcribe
from jin.tray import JinTray
from jin.tts import speak
from jin.wake import WakeListener
from jin import memory as jin_memory

BG = "#010805"
PANEL = "#03140a"
GREEN = "#39ff6a"
DIM = "#1a8f3d"
BORDER = "#1dff4a"
MONO = "Consolas"
WAKE_RE = re.compile(
    r"^(he[iy]\s+|halo\s+|hai\s+)?((jin|asghard)\s+)+",
    re.IGNORECASE,
)


class JinApp(ctk.CTk):
    def __init__(self, start_minimized: bool = False) -> None:
        super().__init__()
        self.title("JIN ASGHARD - v1.0")
        self._fit_to_screen()
        self.configure(fg_color=BG)

        ctk.set_appearance_mode("dark")
        db.init_db()
        self.conversation_id = db.start_conversation()
        self.recorder = MicRecorder()
        self.busy = False
        self.speak_enabled = JIN_SPEAK
        self.mood = "idle"
        self._mood_photos: dict[str, ctk.CTkImage] = {}
        self._jin_label = None
        self._pulse_on = False
        self._wake: WakeListener | None = None
        self._idle_dir = 1
        self._idle_pad = 8
        self._started = datetime.now()
        self._guard_count = 0
        self._pending = ""
        self._clip_offer_at = 0.0
        self._drag_x = 0
        self.shell = None
        self.clipboard_enabled = JIN_CLIPBOARD
        self.close_to_tray = JIN_TRAY
        self._tray: JinTray | None = None
        self._tray_hint_shown = False
        self._settings_win: SettingsWindow | None = None
        self._history_win: HistoryWindow | None = None
        self._stream_text = ""
        self._stream_queued = False
        self.confirm_enabled = JIN_CONFIRM
        self._hotkey: GlobalHotkey | None = None
        self._mini: MiniWindow | None = None
        self.mini_mode = False
        self.report_callback_exception = self._on_tk_error

        self._build()
        self._boot()
        self._start_wake()
        self._start_tray()
        self._start_hotkey(HOTKEY)
        start_window_watcher()
        self.after(4000, self._poll_reminders)
        self.after(400, self._idle_float)
        self.after(60_000, self._guardian)
        self.after(2500, self._poll_clipboard)
        self.after(3500, self._run_health_check)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if start_minimized and self._tray is not None:
            self.withdraw()
        elif db.get_setting("mini_mode") == "1":
            self.after(300, self.enter_mini)

    def _fit_to_screen(self) -> None:
        """860 logical px is taller than a 1080p screen at 125% scaling; shrink to fit."""
        scale = ctk.ScalingTracker.get_window_scaling(self)
        screen_height = int(self.winfo_screenheight() / scale)
        height = max(600, min(860, screen_height - 110))
        self.geometry(f"540x{height}+40+20")
        self.minsize(500, min(780, height))

    def _build(self) -> None:
        self.shell = ctk.CTkFrame(self, fg_color=BG, border_color=BORDER, border_width=2, corner_radius=18)
        self.shell.pack(fill="both", expand=True, padx=10, pady=10)

        title = ctk.CTkFrame(self.shell, fg_color=BG, height=42)
        title.pack(fill="x", padx=12, pady=(10, 0))
        title.pack_propagate(False)

        dots = ctk.CTkFrame(title, fg_color="transparent")
        dots.pack(side="left", padx=(8, 0))
        for color in ("#ff5f56", "#ffbd2e", "#27c93f"):
            ctk.CTkLabel(dots, text="●", text_color=color, font=ctk.CTkFont(size=14), width=16).pack(side="left")

        ctk.CTkLabel(
            title,
            text="JIN ASGHARD - v1.0",
            text_color=DIM,
            font=ctk.CTkFont(family=MONO, size=12),
        ).pack(side="left", expand=True)

        self.speak_switch = ctk.CTkSwitch(
            title,
            text="SUARA",
            command=self._toggle_speak,
            progress_color=GREEN,
            fg_color="#12331c",
            font=ctk.CTkFont(family=MONO, size=11),
            text_color=GREEN,
            width=70,
        )
        self.speak_switch.pack(side="right", padx=8)
        if self.speak_enabled:
            self.speak_switch.select()

        for text, command in (("⚙", self.open_settings), ("☰", self.open_history), ("▭", self.enter_mini)):
            ctk.CTkButton(
                title,
                text=text,
                width=32,
                height=28,
                fg_color=BG,
                hover_color="#0a2a14",
                border_color=DIM,
                border_width=1,
                text_color=GREEN,
                font=ctk.CTkFont(size=14),
                command=command,
            ).pack(side="right", padx=(0, 4))

        bottom = ctk.CTkFrame(self.shell, fg_color=PANEL, border_color=GREEN, border_width=2, corner_radius=10)
        bottom.pack(side="bottom", fill="x", padx=18, pady=(0, 14))

        hint = ctk.CTkLabel(
            bottom,
            text="lampu=mic  |  dada=catatan  |  geser=wujud  |  kanan=radar",
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=11),
        )
        hint.pack(fill="x", padx=12, pady=(8, 0))

        row = ctk.CTkFrame(bottom, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(4, 10))

        self.input = ctk.CTkEntry(
            row,
            placeholder_text="ketik pesan ke jin asghard...",
            placeholder_text_color=DIM,
            height=44,
            fg_color=BG,
            border_color=GREEN,
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=14),
        )
        self.input.pack(side="left", fill="x", expand=True, padx=(4, 6))
        self.input.bind("<Return>", lambda _event: self.send_text())

        self.mic_button = ctk.CTkButton(
            row,
            text="MIC",
            width=70,
            height=44,
            fg_color=BG,
            hover_color="#0a2a14",
            border_color=GREEN,
            border_width=1,
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            command=self.toggle_mic,
        )
        self.mic_button.pack(side="left", padx=(0, 6))

        self.send_button = ctk.CTkButton(
            row,
            text="KIRIM",
            width=84,
            height=44,
            fg_color=GREEN,
            hover_color="#73ff96",
            text_color="#021108",
            font=ctk.CTkFont(family=MONO, size=12, weight="bold"),
            command=self.send_text,
        )
        self.send_button.pack(side="left", padx=(0, 4))

        status = ctk.CTkFrame(self.shell, fg_color=PANEL, border_color=GREEN, border_width=1, corner_radius=8, height=36)
        status.pack(side="bottom", fill="x", padx=18, pady=(0, 8))
        status.pack_propagate(False)
        self.status_dot = ctk.CTkLabel(
            status,
            text="●  JIN ASGHARD: ACTIVE",
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=13),
        )
        self.status_dot.pack(side="left", padx=12)

        self.log = ctk.CTkTextbox(
            self.shell,
            height=110,
            fg_color=BG,
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=13),
            border_width=0,
            wrap="word",
            activate_scrollbars=False,
        )
        self.log.pack(fill="x", padx=22, pady=(8, 6))
        self.log.configure(state="disabled")

        line = ctk.CTkFrame(self.shell, fg_color=DIM, height=1)
        line.pack(fill="x", padx=24, pady=(0, 8))

        self.stage = ctk.CTkFrame(self.shell, fg_color=BG, border_color=DIM, border_width=1, corner_radius=14)
        self.stage.pack(fill="both", expand=True, padx=16, pady=(0, 4))

        self._load_moods()
        if "idle" in self._mood_photos:
            self._jin_label = ctk.CTkLabel(self.stage, text="", image=self._mood_photos["idle"], cursor="hand2")
            self._jin_label.pack(pady=(8, 4))
            self._jin_label.bind("<Button-1>", self._on_jin_press)
            self._jin_label.bind("<ButtonRelease-1>", self._on_jin_release)
            self._jin_label.bind("<Button-3>", lambda _event: self._run_radar())
        else:
            self._jin_label = ctk.CTkLabel(
                self.stage,
                text="[ JIN ASGHARD ]",
                text_color=GREEN,
                font=ctk.CTkFont(family=MONO, size=24, weight="bold"),
            )
            self._jin_label.pack(pady=24)

        self.mood_label = ctk.CTkLabel(
            self.stage,
            text="IDLE  •  klik jin untuk bicara",
            text_color=DIM,
            font=ctk.CTkFont(family=MONO, size=11),
        )
        self.mood_label.pack()

        bubble = ctk.CTkFrame(
            self.stage,
            fg_color=PANEL,
            border_color=GREEN,
            border_width=2,
            corner_radius=12,
        )
        bubble.pack(fill="x", padx=36, pady=(6, 10))
        ctk.CTkLabel(bubble, text="▲", text_color=GREEN, font=ctk.CTkFont(size=12), height=12).pack()
        self.bubble = ctk.CTkLabel(
            bubble,
            text=f"HADIR, {OWNER_CALL.upper()}",
            text_color=GREEN,
            font=ctk.CTkFont(family=MONO, size=14, weight="bold"),
            wraplength=320,
            justify="center",
            padx=12,
            pady=8,
        )
        self.bubble.pack(fill="x", padx=8, pady=(0, 10))

    def _load_moods(self) -> None:
        for name, path in MOOD_IMAGES.items():
            src = path if path.exists() else JIN_IMAGE
            if not src.exists():
                continue
            image = Image.open(src)
            image.thumbnail((240, 280))
            self._mood_photos[name] = ctk.CTkImage(
                light_image=image,
                dark_image=image,
                size=image.size,
            )

    def _set_mood(self, mood: str) -> None:
        self.mood = mood
        photo = self._mood_photos.get(mood) or self._mood_photos.get("idle")
        if photo is not None and self._jin_label is not None:
            self._jin_label.configure(image=photo)
        form = current_form().upper()
        labels = {
            "idle": f"{form}  •  lampu=mic  dada=catat  geser=wujud",
            "listen": "LISTENING  •  tekan STOP jika selesai",
            "think": "THINKING  •  meracik mantra",
            "speak": "SPEAKING  •  jin sedang bicara",
        }
        self.mood_label.configure(text=labels.get(mood, mood.upper()))
        glow = {
            "idle": {"tenang": "#3cffde", "nyentrik": DIM, "serius": "#d4b45a"}.get(current_form(), DIM),
            "listen": "#3cffde",
            "think": "#d4ff3c",
            "speak": GREEN,
        }.get(mood, DIM)
        self.stage.configure(border_color=glow)
        self._apply_form_shell()

    def _greeting(self) -> str:
        hour = datetime.now().hour
        if hour < 11:
            return f"Pagi, {OWNER_CALL}. Jin Asghard hadir."
        if hour < 15:
            return f"Siang, {OWNER_CALL}. Siap perintah."
        if hour < 18:
            return f"Sore, {OWNER_CALL}. Ada yang mau dikabulkan?"
        return f"Malam, {OWNER_CALL}. Jin Asghard jaga laptop."

    def _boot(self) -> None:
        lines = [
            "[BOOT] JIN ASGHARD kernel loaded...",
            "[OK]",
            "[INIT] radar / memory / screen / volume / form / code ONLINE",
            "[BIND] bilang 'Jin' untuk summon + klik jin",
            "[READY] System ONLINE",
        ]
        for index, line in enumerate(lines):
            self.after(260 * index, lambda text=line: self._log(text))
        self.after(260 * len(lines) + 400, self._boot_hello)
        self.after(1200, self._boot_memory)

    def _boot_memory(self) -> None:
        try:
            jin_memory.start_backfill_async()
            count = db.embedding_count()
            self._log(f"[MEMORY] semantic index {count} jejak (backfill jalan)")
        except Exception as exc:
            self._log(f"[WARN] memory: {exc}")

    def _boot_hello(self) -> None:
        hello = self._greeting()
        self._log(f"[JIN] {hello}")
        self.bubble.configure(text=hello.upper())
        if self.speak_enabled:
            self._set_mood("speak")
            threading.Thread(target=self._speak_boot, args=(hello,), daemon=True).start()

    def _speak_boot(self, text: str) -> None:
        try:
            speak(text)
        except Exception as exc:
            self.after(0, lambda: self._log(f"[WARN] suara: {exc}"))
        finally:
            self.after(0, lambda: self._set_mood("idle"))

    def _log(self, text: str, persist: bool = True) -> None:
        if not persist:
            pass
        elif text.startswith(("[WARN]", "[ERROR]")):
            log.warning(text)
        else:
            log.info(text)
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _toggle_speak(self) -> None:
        self.speak_enabled = bool(self.speak_switch.get())
        if self.speak_enabled:
            self._log("[SPELL] suara nyala terus")

    def _set_status(self, text: str) -> None:
        self.status_dot.configure(text=f"●  {text}")

    def _lock(self, locked: bool) -> None:
        self.busy = locked
        state = "disabled" if locked else "normal"
        self.input.configure(state=state)
        self.send_button.configure(state=state)
        if not self.recorder.recording:
            self.mic_button.configure(state=state)
        if locked:
            self._set_status("JIN: THINKING...")
            self._set_mood("think")
        else:
            self._set_status("JIN: ACTIVE")
            if not self.recorder.recording:
                self._set_mood("idle")

    def send_text(self) -> None:
        if self.busy:
            return
        text = self.input.get().strip()
        if not text:
            return
        self.input.delete(0, "end")
        self._handle_user_text(text)

    def summon(self, command: str = "") -> None:
        if self.mini_mode and self._mini is not None:
            self._mini.deiconify()
            self._mini.lift()
        else:
            self.deiconify()
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(500, lambda: self.attributes("-topmost", False))
        self._log("[SPELL] asghard summoned")
        if self._wake is not None:
            self._wake.nudge_cooldown(2.5)
        cleaned = (command or "").strip()
        if cleaned:
            if not self.busy:
                self._handle_user_text(cleaned)
            return
        if not self.busy:
            self.toggle_mic()

    def _start_wake(self) -> None:
        if not JIN_WAKE:
            self._log("[WARN] wake word mati (JIN_WAKE=0)")
            return
        try:
            self._wake = WakeListener(
                on_wake=lambda cmd: self.after(0, lambda c=cmd: self.summon(c)),
                is_blocked=lambda: self.busy or self.recorder.recording,
            )
            self._wake.start()
            self._log("[BIND] wake word: Jin / Asghard")
        except Exception as exc:
            self._log(f"[WARN] wake gagal: {exc}")

    def toggle_mic(self) -> None:
        if self.busy and not self.recorder.recording:
            return
        if not self.recorder.recording:
            try:
                self.recorder.start()
            except Exception:
                log.exception("Mic gagal dibuka")
                self._fail("Mic tidak bisa dipakai, bos. Cek apakah mic tercolok dan diizinkan di Windows.")
                return
            self.mic_button.configure(text="STOP", fg_color="#3a1010", border_color="#ff5f56", text_color="#ff5f56")
            self._set_status("JIN: LISTENING...")
            self._set_mood("listen")
            return

        self.mic_button.configure(text="MIC", fg_color=BG, border_color=GREEN, text_color=GREEN)
        self._lock(True)
        self._set_status("JIN: TRANSCRIBE...")
        threading.Thread(target=self._finish_recording, daemon=True).start()

    def _clean_heard(self, text: str) -> str:
        cleaned = WAKE_RE.sub("", text).strip(" ,.")
        return cleaned or text

    def _finish_recording(self) -> None:
        try:
            path = self.recorder.stop()
            text = self._clean_heard(transcribe(path))
        except Exception:
            log.exception("Transkripsi gagal")
            self.after(0, lambda: self._fail("Suaranya gagal kuubah jadi teks, bos. Coba lagi."))
            return
        if not text:
            self.after(0, lambda: self._fail("Suara tidak ketangkap. Coba lagi."))
            return
        self.after(0, lambda: self._handle_user_text(text, already_locked=True))

    def _handle_user_text(self, text: str, already_locked: bool = False) -> None:
        text = self._clean_heard(text)
        if self._pending == "istirahat" and re.fullmatch(r"(ya|iya|oke|ok|boleh|ingatkan)", text, re.I):
            text = "ingatkan saya istirahat dalam 50 menit"
            self._pending = ""
        elif self._pending == "clipboard" and re.fullmatch(r"(tidak|ga|gak|skip)", text, re.I):
            self._pending = ""
            self._log("[SPELL] clipboard diabaikan")
            self.bubble.configure(text="BAIK, BOS REHAN.")
            return
        self._log(f"> {text}")
        db.add_message(self.conversation_id, "user", text)
        if not already_locked:
            self._lock(True)
        self._set_status("JIN: THINKING...")
        self._set_mood("think")
        threading.Thread(target=self._think_and_reply, daemon=True).start()

    def _think_and_reply(self) -> None:
        try:
            history = db.recent_messages(self.conversation_id)

            def on_tool(name: str, args: dict) -> None:
                self.after(0, lambda n=name: self._log(f"[SPELL] {n}"))
                if name in {"set_form", "mantra"}:
                    self.after(0, self._apply_form_shell)

            text = reply(
                history,
                on_tool=on_tool,
                on_token=self._on_token,
                confirm=self._confirm if self.confirm_enabled else None,
            )
            db.add_message(self.conversation_id, "assistant", text)
        except RuntimeError as exc:
            # Raised on purpose with a readable message (e.g. Ollama not running).
            log.warning("Reply gagal: %s", exc)
            message = str(exc)
            self.after(0, lambda: self._fail(message))
            return
        except Exception:
            log.exception("Reply gagal")
            self.after(
                0,
                lambda: self._fail(
                    f"Ada yang gagal waktu menjalankan perintah itu, {OWNER_CALL}. Detailnya kucatat di log."
                ),
            )
            return

        def show() -> None:
            self._stream_text = ""
            self._log(f"[JIN] {text}")
            self.bubble.configure(text=text.upper() if len(text) < 80 else text)
            if self.speak_enabled:
                self._set_status("JIN: SPEAKING...")
                self._set_mood("speak")
                threading.Thread(target=self._speak, args=(text,), daemon=True).start()
            else:
                self._lock(False)

        self.after(0, show)

    def _on_token(self, text_so_far: str) -> None:
        """Called from the worker thread; coalesce updates into one Tk call at a time."""
        self._stream_text = text_so_far
        if not self._stream_queued:
            self._stream_queued = True
            self.after(60, self._flush_stream)

    def _flush_stream(self) -> None:
        self._stream_queued = False
        text = self._stream_text
        if text:
            self.bubble.configure(text=text if len(text) <= 280 else "…" + text[-280:])
            self._set_status("JIN: MENJAWAB...")

    def _speak(self, text: str) -> None:
        try:
            speak(text)
        except Exception as exc:
            self.after(0, lambda: self._log(f"[WARN] suara gagal: {exc}"))
            self.after(0, lambda: self._set_status(f"JIN: VOICE FAIL"))
        finally:
            self.after(0, lambda: self._lock(False))

    def _fail(self, message: str) -> None:
        """Show a readable error in the bubble; full details live in the log file."""
        self._lock(False)
        self.mic_button.configure(text="MIC", fg_color=BG, border_color=GREEN, text_color=GREEN)
        self._set_status("JIN: ERROR")
        self._log(f"[ERROR] {message.splitlines()[0]}")
        self.bubble.configure(text=message)

    def _on_tk_error(self, exc_type, exc, tb) -> None:
        log.error("Error di UI", exc_info=(exc_type, exc, tb))
        self._fail(f"Ada yang macet di tampilan, {OWNER_CALL}. Detailnya kucatat di log.")

    def _confirm(self, question: str) -> bool:
        """Called from the worker thread; blocks until the user answers on the Tk thread."""
        answered = threading.Event()
        result = {"ok": False}

        def ask() -> None:
            try:
                self._set_status("JIN: MINTA IZIN...")
                result["ok"] = dialogs.ask(self, question)
            finally:
                self._set_status("JIN: THINKING...")
                answered.set()

        self.after(0, ask)
        answered.wait()
        self.after(0, lambda: self._log(f"[IZIN] {'lanjut' if result['ok'] else 'dibatalkan'}"))
        return result["ok"]

    def _run_health_check(self) -> None:
        def work() -> None:
            try:
                checks = health.run_checks()
            except Exception:
                log.exception("Cek kesehatan gagal")
                return
            self.after(0, lambda: self._show_health(checks))

        threading.Thread(target=work, daemon=True).start()

    def _show_health(self, checks: list) -> None:
        bad = health.problems(checks)
        for check in checks:
            if check.status != health.OK:
                self._log(f"[CEK] {check.name}: {check.detail}")
        if not bad:
            self._log("[CEK] semua sistem siap")
            return
        names = ", ".join(check.name for check in bad)
        message = f"{len(bad)} hal perlu dicek: {names}. Bilang 'cek sistem' untuk detail."
        if not self.busy:
            self.bubble.configure(text=message)
        self._toast(message)

    def _toast(self, body: str, important: bool = False) -> None:
        """In mini mode the bubble already sits where Windows toasts appear, so show it there instead."""
        if self.mini_mode and not important:
            if not self.busy:
                self.bubble.configure(text=body)
            return
        windows_toast("Jin Asghard", body)

    def _poll_reminders(self) -> None:
        try:
            due = db.due_reminders()
        except Exception:
            due = []
        for item in due:
            db.complete_reminder(item["id"])
            self._fire_reminder(item["text"])
        self.after(5000, self._poll_reminders)

    def _fire_reminder(self, text: str) -> None:
        self._log(f"[REMINDER] {text}")
        self.bubble.configure(text=f"PENGINGAT: {text}")
        self._set_status("JIN: REMINDER")
        self._set_mood("speak")
        self._toast(f"{OWNER_CALL}, {text}", important=True)
        if self.speak_enabled:
            threading.Thread(target=self._speak_reminder, args=(text,), daemon=True).start()
        else:
            self.after(2500, lambda: self._set_mood("idle"))

    def _speak_reminder(self, text: str) -> None:
        try:
            speak(f"{OWNER_CALL}, pengingat. {text}")
        except Exception:
            pass
        finally:
            self.after(0, lambda: self._set_mood("idle"))

    def _apply_form_shell(self) -> None:
        if self.shell is None:
            return
        colors = {"tenang": "#3cffde", "nyentrik": GREEN, "serius": "#d4b45a"}
        self.shell.configure(border_color=colors.get(current_form(), GREEN))

    def _idle_float(self) -> None:
        if self._jin_label is not None and self.mood == "idle":
            self._idle_pad += self._idle_dir
            if self._idle_pad >= 14 or self._idle_pad <= 6:
                self._idle_dir *= -1
            self._jin_label.pack_configure(pady=(self._idle_pad, 4))
        self.after(180, self._idle_float)

    def _guardian(self) -> None:
        hours = (datetime.now() - self._started).total_seconds() / 3600
        if hours >= 2 * (self._guard_count + 1):
            self._guard_count += 1
            message = f"{OWNER_CALL}, sudah {self._guard_count * 2} jam di laptop. Istirahat sebentar."
            self._log(f"[GUARD] {message}")
            self._toast(message)
            if self.speak_enabled and not self.busy:
                threading.Thread(target=self._speak_reminder, args=(message,), daemon=True).start()
        shadow = code_shadow()
        if shadow and not self.busy:
            self._pending = "istirahat"
            self._log(f"[SHADOW] {shadow}")
            self.bubble.configure(text=shadow)
            self._toast(shadow)
            if self.speak_enabled:
                threading.Thread(target=self._speak_reminder, args=(shadow,), daemon=True).start()
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        if now.hour == 7 and db.get_setting("morning_radar_day") != today:
            if not self.busy:
                db.set_setting("morning_radar_day", today)
                self._handle_user_text("radar pagi")
        self.after(60_000, self._guardian)

    def _on_jin_press(self, event) -> None:
        self._drag_x = event.x

    def _on_jin_release(self, event) -> None:
        dx = event.x - self._drag_x
        if abs(dx) > 48:
            result = cycle_form(1 if dx > 0 else -1)
            self._log(f"[SPELL] {result}")
            self._apply_form_shell()
            self._set_mood("idle")
            self.bubble.configure(text=result.upper())
            return
        width = max(event.widget.winfo_width(), 1)
        height = max(event.widget.winfo_height(), 1)
        nx = event.x / width
        ny = event.y / height
        if ny >= 0.72 and nx <= 0.65:
            self.toggle_mic()
            return
        if 0.28 <= ny <= 0.70 and 0.20 <= nx <= 0.84:
            self._quick_note()

    def _quick_note(self) -> None:
        if self.busy:
            return
        try:
            import pyperclip

            text = (pyperclip.paste() or "").strip()
        except Exception:
            text = ""
        if len(text) >= 4:
            self._handle_user_text(f"catat: {text[:800]}")
            return
        self.bubble.configure(text="CATATAN CEPAT. KETIK LALU KIRIM.")
        self.input.focus_set()

    def _poll_clipboard(self) -> None:
        if self.clipboard_enabled and not self.busy and not self.recorder.recording:
            text = new_clipboard_text()
            if text:
                now = datetime.now().timestamp()
                if now - self._clip_offer_at > 12:
                    self._clip_offer_at = now
                    self._offer_clipboard(text)
        self.after(1600, self._poll_clipboard)

    def _offer_clipboard(self, text: str) -> None:
        save_context({"clipboard": text[:2000], "result": text[:280], "topic": "clipboard"})
        if looks_like_code(text):
            lines = len([line for line in text.splitlines() if line.strip()])
            self._log(f"[CLIP] kode disalin ({lines} baris)")
            return
        self._pending = "clipboard"
        preview = text.replace("\n", " ")[:80]
        message = f"Bos copy teks: {preview}. Ringkas, terjemah, atau catat?"
        self._log(f"[CLIP] {preview}", persist=False)
        self.bubble.configure(text=message)
        self._toast("Teks tersalin. Ringkas, terjemah, atau catat?")
        if self.speak_enabled:
            threading.Thread(
                target=self._speak_reminder,
                args=("Bos Rehan menyalin teks. Ringkas, terjemah, atau catat?",),
                daemon=True,
            ).start()

    def _run_radar(self) -> None:
        if self.busy or self.recorder.recording:
            return
        self._handle_user_text("radar")

    def _start_tray(self) -> None:
        try:
            self._tray = JinTray(
                on_show=lambda: self.after(0, self.show_window),
                on_mic=lambda: self.after(0, self.summon),
                on_mini=lambda: self.after(0, self.enter_mini),
                on_history=lambda: self.after(0, self.open_history),
                on_settings=lambda: self.after(0, self.open_settings),
                on_quit=lambda: self.after(0, self.quit_app),
            )
            self._tray.start()
        except Exception as exc:
            self._tray = None
            self._log(f"[WARN] tray gagal: {exc}")

    def _start_hotkey(self, combo: str) -> None:
        if self._hotkey is not None:
            self._hotkey.stop()
            self._hotkey = None
        if not combo.strip():
            return
        try:
            self._hotkey = GlobalHotkey(combo, lambda: self.after(0, self.summon))
            self._hotkey.start()
            self._log(f"[BIND] tombol pintas: {combo}")
        except Exception as exc:
            self._log(f"[WARN] tombol pintas '{combo}' gagal: {exc}")

    def show_window(self) -> None:
        if self.mini_mode:
            self.exit_mini()
            return
        self.deiconify()
        self.lift()
        self.focus_force()

    def enter_mini(self) -> None:
        if self._mini is None or not self._mini.winfo_exists():
            self._mini = MiniWindow(self)
        self.mini_mode = True
        db.set_setting("mini_mode", "1")
        self.withdraw()
        self._mini.deiconify()
        self._mini.lift()

    def exit_mini(self) -> None:
        self.mini_mode = False
        db.set_setting("mini_mode", "0")
        if self._mini is not None and self._mini.winfo_exists():
            self._mini.withdraw()
        self.show_window()

    def open_settings(self) -> None:
        self.show_window()
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.focus_force()
            return
        self._settings_win = SettingsWindow(self, on_applied=self._apply_settings)

    def open_history(self) -> None:
        self.show_window()
        if self._history_win is not None and self._history_win.winfo_exists():
            self._history_win.focus_force()
            self._history_win.refresh()
            return
        self._history_win = HistoryWindow(self)

    def _apply_settings(self, values: dict[str, str]) -> None:
        self.clipboard_enabled = values.get("JIN_CLIPBOARD", "1") != "0"
        self.close_to_tray = values.get("JIN_TRAY", "1") != "0"
        self.confirm_enabled = values.get("JIN_CONFIRM", "1") != "0"
        self._start_hotkey(values.get("JIN_HOTKEY", ""))
        self._log("[SPELL] pengaturan disimpan")

    def _on_close(self) -> None:
        if self.close_to_tray and self._tray is not None:
            self.withdraw()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self._tray.notify("Jin tetap jalan di tray. Klik kanan ikon untuk keluar.")
            return
        self.quit_app()

    def quit_app(self) -> None:
        if self._wake is not None:
            try:
                self._wake.stop()
            except Exception:
                pass
        if self._hotkey is not None:
            self._hotkey.stop()
        if self._tray is not None:
            self._tray.stop()
        self.destroy()

    def restart(self) -> None:
        settings.restart()
        self.quit_app()
