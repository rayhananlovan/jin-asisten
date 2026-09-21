from __future__ import annotations

import ctypes
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab

from jin import db
from jin.config import DATA_DIR, OWNER_CALL, ensure_dirs

FORMS = ("tenang", "nyentrik", "serius")
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF


def _key(vk: int) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


def screenshot() -> Path:
    ensure_dirs()
    folder = DATA_DIR / "screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"layar-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    image = ImageGrab.grab()
    image.save(path)
    desktop = Path.home() / "Desktop" / path.name
    try:
        image.save(desktop)
        return desktop
    except OSError:
        return path


def read_screen() -> str:
    path = screenshot()
    text = ""
    try:
        import winocr
        from PIL import Image
        import asyncio

        image = Image.open(path)
        result = asyncio.run(winocr.recognize_pil(image))
        text = getattr(result, "text", "") or str(result)
    except Exception:
        text = ""
    if text.strip():
        return f"Screenshot: {path}\nTulisan di layar:\n{text.strip()[:2500]}"
    return (
        f"Layar sudah kuambil, {OWNER_CALL}. File: {path}\n"
        "Huruf di layar belum kebaca (OCR opsional). Bisa kuceritakan dari screenshot itu kalau bos tempel teksnya."
    )


def clipboard_get() -> str:
    try:
        import pyperclip

        value = pyperclip.paste()
        return value.strip() or "Clipboard kosong."
    except Exception as exc:
        return f"Clipboard gagal dibaca: {exc}"


_clip_ignore = False
_clip_last = ""


def mark_clip_write() -> None:
    global _clip_ignore
    _clip_ignore = True


def new_clipboard_text() -> str | None:
    global _clip_ignore, _clip_last
    try:
        import pyperclip

        value = pyperclip.paste()
    except Exception:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if _clip_ignore:
        _clip_ignore = False
        _clip_last = text
        return None
    if not text or text == _clip_last:
        return None
    if len(text) < 12 or len(text) > 4000:
        _clip_last = text
        return None
    _clip_last = text
    return text


def clipboard_set(text: str) -> str:
    import pyperclip

    mark_clip_write()
    pyperclip.copy(text)
    return f"Clipboard diisi ({len(text)} karakter)."


def paste_to_last_window(text: str) -> str:
    import pyperclip
    from pynput.keyboard import Controller, Key

    mark_clip_write()
    pyperclip.copy(text)
    keyboard = Controller()
    time.sleep(0.2)
    keyboard.press(Key.alt)
    keyboard.press(Key.tab)
    keyboard.release(Key.tab)
    keyboard.release(Key.alt)
    time.sleep(0.35)
    keyboard.press(Key.ctrl)
    keyboard.press("v")
    keyboard.release("v")
    keyboard.release(Key.ctrl)
    return f"Teks sudah kutempel di jendela sebelumnya, {OWNER_CALL}."


def volume(action: str) -> str:
    action = action.lower().strip()
    if action in {"mute", "bisukan", "senyap"}:
        _key(VK_VOLUME_MUTE)
        return "Volume di-mute."
    if action in {"up", "naik", "besar"}:
        for _ in range(4):
            _key(VK_VOLUME_UP)
        return "Volume dinaikkan."
    if action in {"down", "turun", "kecil"}:
        for _ in range(4):
            _key(VK_VOLUME_DOWN)
        return "Volume diturunkan."
    return "Pakai: naik, turun, atau mute."


def lock_pc() -> str:
    subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"], close_fds=True)
    return f"Laptop dikunci. Sampai jumpa, {OWNER_CALL}."


def set_form(name: str) -> str:
    key = name.lower().strip()
    aliases = {
        "tenang": "tenang",
        "calm": "tenang",
        "nyentrik": "nyentrik",
        "fun": "nyentrik",
        "serius": "serius",
        "serious": "serius",
        "kerja": "serius",
    }
    form = aliases.get(key)
    if not form:
        return "Wujud yang tersedia: tenang, nyentrik, serius."
    db.set_setting("form", form)
    return f"Wujud Jin diganti ke {form}."


def current_form() -> str:
    return db.get_setting("form", "nyentrik") or "nyentrik"


def cycle_form(delta: int = 1) -> str:
    current = current_form()
    index = FORMS.index(current) if current in FORMS else 1
    return set_form(FORMS[(index + delta) % len(FORMS)])


def daily_radar() -> str:
    now = datetime.now()
    hari = HARI[now.weekday()]
    lines = [
        f"Radar {hari}, {now.strftime('%d/%m/%Y %H:%M')}",
        f"Wujud: {current_form()}",
    ]
    reminders = db.list_reminders()
    if reminders:
        lines.append("Pengingat:")
        lines.extend(f"- {item['fire_at']} {item['text']}" for item in reminders[:5])
    else:
        lines.append("Pengingat: kosong")
    notes = db.list_notes(limit=3)
    if notes:
        lines.append("Catatan terakhir:")
        lines.extend(f"- {note['title']}" for note in notes)
    memories = db.list_memories(limit=4)
    if memories:
        lines.append("Ingatan:")
        lines.extend(f"- {item['fact']}" for item in memories)
    return "\n".join(lines)


def save_memory(fact: str) -> str:
    if not fact.strip():
        return "Tidak ada yang diingat."
    item = db.save_memory(fact)
    return f"Kuingat #{item['id']}: {item['fact']}"


def list_memories() -> str:
    items = db.list_memories()
    if not items:
        return "Belum ada ingatan jangka panjang."
    return "\n".join(f"#{item['id']} {item['fact']}" for item in items)
