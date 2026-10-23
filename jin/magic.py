from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import io
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab

from jin import db
from jin.config import DATA_DIR, OLLAMA_URL, OWNER_CALL, VISION_MODEL, ensure_dirs

FORMS = ("tenang", "nyentrik", "serius")
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF


def _key(vk: int) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


def _save_shot(image, to_desktop: bool) -> Path:
    ensure_dirs()
    folder = DATA_DIR / "screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"layar-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    image.save(path)
    if to_desktop:
        desktop = Path.home() / "Desktop" / path.name
        try:
            image.save(desktop)
            return desktop
        except OSError:
            pass
    return path


def screenshot() -> Path:
    return _save_shot(ImageGrab.grab(all_screens=True), to_desktop=True)


def _foreground_bbox() -> tuple[int, int, int, int] | None:
    """Physical-pixel bounds of the foreground window, without the drop shadow."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd or user32.IsIconic(hwnd):
        return None
    rect = ctypes.wintypes.RECT()
    dwmwa_extended_frame_bounds = 9
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd,
        dwmwa_extended_frame_bounds,
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if result != 0:
        return None
    if rect.right - rect.left < 80 or rect.bottom - rect.top < 80:
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def capture_work_window():
    """Focus the window behind Jin, grab only that window, then return to Jin."""
    from jin import smart

    switched = False
    try:
        if smart.last_app_title():
            _alt_tab()
            switched = True
        bbox = _foreground_bbox() if switched else None
        image = ImageGrab.grab(bbox=bbox, all_screens=True)
    finally:
        if switched:
            try:
                _alt_tab()
            except Exception:
                pass
    return image


def _alt_tab() -> None:
    """Switch to the previous window (usually the work app behind Jin)."""
    from pynput.keyboard import Controller, Key

    keyboard = Controller()
    keyboard.press(Key.alt)
    keyboard.press(Key.tab)
    keyboard.release(Key.tab)
    keyboard.release(Key.alt)
    time.sleep(0.45)


def _ocr_image(image) -> tuple[str, str]:
    """Return (text, error). Tries Windows OCR in id then en."""
    errors: list[str] = []
    try:
        from winocr import recognize_pil_sync
    except Exception as exc:
        return "", f"winocr belum terpasang ({exc})"

    for lang in ("id", "en"):
        try:
            result = recognize_pil_sync(image, lang)
            if isinstance(result, dict):
                text = str(result.get("text") or "")
            else:
                text = getattr(result, "text", "") or str(result)
            if text.strip():
                return text.strip(), ""
        except Exception as exc:
            errors.append(f"{lang}: {exc}")
    return "", "; ".join(errors) or "OCR kosong"


def read_screen() -> str:
    """OCR the work window (not Jin)."""
    from jin import smart

    path: Path | None = None
    text = ""
    err = ""
    try:
        image = capture_work_window()
        path = _save_shot(image, to_desktop=False)
        text, err = _ocr_image(image)
    except Exception as exc:
        err = str(exc)

    if path and text.strip():
        smart.save_context({"result": text[:280], "topic": "isi layar"})
        return f"Screenshot: {path}\nTulisan di layar:\n{text.strip()[:4000]}"
    where = str(path) if path else "(gagal ambil screenshot)"
    hint = f" ({err})" if err else ""
    return (
        f"Layar sudah kuambil, {OWNER_CALL}. File: {where}\n"
        f"Huruf di layar belum kebaca{hint}. "
        "Pasang `winocr` + Windows OCR (id/en), atau tempel teksnya ke clipboard lalu bilang 'ringkas'."
    )


def _installed_models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return []
    return [str(item.get("name") or "") for item in data.get("models") or []]


def _has_model(name: str) -> bool:
    wanted = name if ":" in name else f"{name}:latest"
    return any(model == wanted for model in _installed_models())


def describe_screen(question: str = "") -> str:
    """Let a local vision model look at the work window; fall back to OCR."""
    from jin import smart

    if not _has_model(VISION_MODEL):
        return (
            f"Model vision '{VISION_MODEL}' belum terpasang, jadi aku cuma bisa baca tulisannya.\n"
            f"Pasang sekali lewat: ollama pull {VISION_MODEL}\n\n" + read_screen()
        )
    image = capture_work_window()
    path = _save_shot(image, to_desktop=False)
    small = image.convert("RGB")
    small.thumbnail((1280, 1280))
    buffer = io.BytesIO()
    small.save(buffer, format="PNG")
    prompt = (
        "Kamu melihat screenshot jendela kerja di laptop. Jelaskan singkat dalam bahasa Indonesia "
        "apa yang sedang terbuka dan apa isinya. Kalau ada pesan error, sebutkan errornya, "
        "kemungkinan penyebab, dan cara memperbaikinya."
    )
    if question.strip():
        prompt += f"\nPertanyaan bos: {question.strip()}"
    payload = {
        "model": VISION_MODEL,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64.b64encode(buffer.getvalue()).decode("ascii")],
            }
        ],
        "options": {"temperature": 0.2},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as exc:
        return f"Model vision gagal dipanggil ({exc}).\n\n" + read_screen()
    text = str((data.get("message") or {}).get("content") or "").strip()
    if not text:
        return "Model vision tidak memberi jawaban.\n\n" + read_screen()
    smart.save_context({"result": text[:280], "topic": "isi layar"})
    return f"Screenshot: {path}\nPenjelasan layar:\n{text[:4000]}"


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


_CODE_HINTS = re.compile(
    r"</?[a-zA-Z][\w-]*(\s[^>]*)?>|\b(def|class|import|from|return|function|const|let|var|"
    r"public|private|async|await)\b|[{};]\s*$|=>|\$\w+|^\s*(#include|<\?php|```)",
    re.MULTILINE,
)


def looks_like_code(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    hits = sum(1 for line in lines if _CODE_HINTS.search(line))
    symbols = sum(text.count(ch) for ch in "{}<>;=()[]")
    return hits >= max(1, len(lines) // 3) or symbols / max(len(text), 1) > 0.06


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
