from __future__ import annotations

import ctypes
import json
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

from jin import db
from jin.config import OWNER_CALL

SKIP_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "AppData",
    "Windows",
}
TEXT_EXT = {".txt", ".md", ".json", ".py", ".csv", ".log", ".ini", ".env", ".xml", ".html"}
CODE_RE = re.compile(r"visual studio code|\bvs code\b|\bcursor\b", re.IGNORECASE)
_WATCH_STARTED = False
_LAST_APP = ""
_APP_LOCK = threading.Lock()
_CODE_SINCE: datetime | None = None
_CODE_ALERTED = False


def load_context() -> dict:
    raw = db.get_setting("last_context", "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def save_context(update: dict) -> None:
    ctx = load_context()
    ctx.update({key: value for key, value in update.items() if value})
    db.set_setting("last_context", json.dumps(ctx, ensure_ascii=False))


def remember_action(name: str, args: dict, result: str) -> None:
    snippet = result.strip().replace("\n", " ")[:280]
    if name == "search_google":
        save_context(
            {
                "topic": str(args.get("query") or ""),
                "search": str(args.get("query") or ""),
                "result": snippet,
            }
        )
    elif name == "open_item":
        save_context({"opened": str(args.get("name") or ""), "topic": str(args.get("name") or "")})
    elif name in {"open_vscode", "resume_coding", "create_folder"}:
        path = str(args.get("path") or args.get("hint") or args.get("name") or "")
        if path:
            save_context({"workspace": path, "project": path, "topic": Path(path).name, "opened": "vscode"})
        save_context({"result": snippet})
    elif name in {"search_files", "read_file"}:
        save_context({"file": str(args.get("query") or args.get("path") or ""), "topic": snippet[:80], "result": snippet})
    elif name == "save_note":
        save_context({"note": str(args.get("text") or ""), "result": snippet})
    elif name == "set_reminder":
        save_context({"reminder": str(args.get("text") or ""), "topic": str(args.get("text") or "")})
    else:
        save_context({"result": snippet})


def resolve_references(text: str) -> str:
    ctx = load_context()
    topic = ctx.get("topic") or ctx.get("search") or ctx.get("opened") or ctx.get("file") or ""
    result = ctx.get("result") or topic
    opened = ctx.get("file") or ctx.get("opened") or topic
    if not topic and not result:
        return text

    resolved = text
    resolved = re.sub(
        r"\b(catat(?:kan|in)?|simpan catatan)\s+(itu|hasilnya|yang tadi|tadi itu|yang barusan)\b",
        f"catat: {result}",
        resolved,
        flags=re.IGNORECASE,
    )
    resolved = re.sub(
        r"\bbuka\s+(itu|yang tadi|file itu|itu tadi|yang barusan)\b",
        f"buka {opened}",
        resolved,
        flags=re.IGNORECASE,
    )
    resolved = re.sub(
        r"\b(cari(?:kan)?|google(?:kan)?)\s+(itu|yang tadi|itu tadi)\b",
        f"cari {topic}",
        resolved,
        flags=re.IGNORECASE,
    )
    resolved = re.sub(
        r"\bingatkan(?:\s+saya)?(?:\s+untuk)?\s+(itu|yang tadi|hasilnya)\b",
        f"ingatkan {topic}",
        resolved,
        flags=re.IGNORECASE,
    )
    if resolved == text and re.fullmatch(
        r"(itu|yang tadi|tadi|hasilnya|itu tadi|yang barusan)",
        text.strip(),
        flags=re.IGNORECASE,
    ):
        resolved = topic or result
    return resolved


def context_prompt() -> str:
    ctx = load_context()
    app = last_app_title()
    lines = ["Konteks laptop sekarang:"]
    if app:
        lines.append(f"- Jendela kerja terakhir (bukan Jin): {app}")
    if ctx.get("topic"):
        lines.append(f"- Topik terakhir: {ctx['topic']}")
    if ctx.get("result"):
        lines.append(f"- Hasil terakhir: {ctx['result'][:240]}")
    if ctx.get("opened"):
        lines.append(f"- Terakhir dibuka: {ctx['opened']}")
    if ctx.get("file"):
        lines.append(f"- File terakhir: {ctx['file']}")
    if len(lines) == 1:
        return ""
    lines.append(
        "Kalau bos Rehan bilang 'itu', 'yang tadi', atau 'hasilnya', maksudnya konteks di atas."
    )
    return "\n".join(lines)


def foreground_title() -> str:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return (buf.value or "").strip()


def last_app_title() -> str:
    with _APP_LOCK:
        return _LAST_APP


def start_window_watcher() -> None:
    global _WATCH_STARTED
    if _WATCH_STARTED:
        return
    _WATCH_STARTED = True
    threading.Thread(target=_watch_windows, daemon=True).start()


def _watch_windows() -> None:
    global _LAST_APP, _CODE_SINCE, _CODE_ALERTED
    while True:
        title = foreground_title()
        upper = title.upper()
        if title and "ASGHARD" not in upper:
            with _APP_LOCK:
                _LAST_APP = title
            if CODE_RE.search(title):
                if _CODE_SINCE is None:
                    _CODE_SINCE = datetime.now()
                _maybe_remember_ide_project(title)
            else:
                _CODE_SINCE = None
                _CODE_ALERTED = False
        threading.Event().wait(1.5)


def _maybe_remember_ide_project(title: str) -> None:
    """Parse 'file - folder - Visual Studio Code' and remember folder if known on disk."""
    parts = [part.strip() for part in re.split(r"\s+[-—]\s+", title) if part.strip()]
    if len(parts) < 2:
        return
    # Last segment is usually the app name.
    candidates = parts[:-1]
    folder_hint = candidates[-1] if candidates else ""
    if not folder_hint or len(folder_hint) < 2:
        return
    if re.search(r"\.(py|ts|tsx|js|jsx|go|rs|java|cs|json|md)$", folder_hint, re.I):
        folder_hint = candidates[-2] if len(candidates) >= 2 else folder_hint
    try:
        from jin import codehelp

        path = codehelp.resolve_project(folder_hint)
        if path and path.exists():
            ctx = load_context()
            if ctx.get("workspace") == str(path.resolve()):
                return
            codehelp.remember_project(path)
    except Exception:
        return


def _search_roots() -> list[Path]:
    home = Path.home()
    roots = [home / "Desktop", home / "Documents", home / "Downloads", Path("D:\\jin-asisten")]
    return [path for path in roots if path.exists()]


def search_files(query: str, limit: int = 8) -> str:
    needle = query.strip().lower()
    if not needle:
        return "Query file kosong."
    hits: list[Path] = []
    for root in _search_roots():
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")]
            depth = Path(dirpath).relative_to(root).parts
            if len(depth) > 3:
                dirnames[:] = []
                continue
            for name in filenames:
                if needle in name.lower():
                    hits.append(Path(dirpath) / name)
                    if len(hits) >= limit:
                        break
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break
    if not hits:
        return f"Tidak ketemu file bernama mirip '{query}' di Desktop/Documents/Downloads."
    save_context({"file": str(hits[0]), "topic": hits[0].name})
    lines = [f"{index}. {path}" for index, path in enumerate(hits, start=1)]
    return "File ketemu:\n" + "\n".join(lines)


def read_file(path: str) -> str:
    target = Path(os.path.expandvars(path)).expanduser()
    if not target.exists() and load_context().get("file"):
        target = Path(load_context()["file"])
    if not target.exists():
        found = search_files(path, limit=1)
        ctx = load_context().get("file")
        if ctx:
            target = Path(ctx)
        else:
            return found
    if target.suffix.lower() in {".pdf", ".docx", ".doc"} or target.suffix.lower() in TEXT_EXT:
        try:
            body = extract_any(target)
        except Exception as exc:
            return f"Gagal baca file: {exc}"
        if not body:
            return f"File ketemu tapi isinya kosong/tidak terbaca: {target}"
        save_context({"file": str(target), "topic": target.name, "result": body[:240]})
        return f"{target}\n\n{body[:6000]}"
    return f"File ketemu tapi belum bisa kubaca: {target}"


def laptop_context() -> str:
    app = last_app_title() or foreground_title() or "(tidak ketahuan)"
    ctx = load_context()
    return (
        f"Jendela kerja: {app}\n"
        f"Topik terakhir: {ctx.get('topic') or '-'}\n"
        f"File terakhir: {ctx.get('file') or '-'}"
    )


def absorb_facts(text: str) -> list[str]:
    rules = [
        (r"(?:saya|aku)\s+kerja(?:nya)?(?:\s+di)?\s+(.+)", "Bos Rehan kerja di {}"),
        (r"(?:saya|aku)\s+tinggal di\s+(.+)", "Bos Rehan tinggal di {}"),
        (r"(?:saya|aku)\s+suka\s+(.+)", "Bos Rehan suka {}"),
        (r"nama saya\s+(.+)", "Nama bos adalah {}"),
        (r"panggil aku\s+(.+)", "Panggil bos Rehan sebagai {}"),
        (r"besok\s+(?:saya|aku)\s+(.+)", "Rencana besok: {}"),
        (r"jangan\s+(?:pernah\s+)?(.+)", "Jangan {}"),
        (
            r"(?:lagi|sedang)\s+(?:kerja(?:in|kan)?|ngerjain|mengerjakan)\s+(?:proyek\s+|project\s+)?(.+)",
            "Bos Rehan lagi kerjakan proyek: {}",
        ),
        (
            r"(?:proyek|project)\s+(?:saya|aku|ku)?\s*(?:yang\s+)?(?:baru|sekarang)?\s*(?:adalah|=|:)?\s*(.+)",
            "Proyek bos Rehan: {}",
        ),
    ]
    saved: list[str] = []
    blob = text.strip()
    if re.search(r"\b(cari|buka chrome|volume|kunci laptop|screenshot)\b", blob, re.I):
        return saved
    for pattern, template in rules:
        match = re.search(pattern, blob, flags=re.IGNORECASE)
        if not match:
            continue
        fact = template.format(match.group(1).strip(" .,!"))
        if len(fact) < 8 or len(fact) > 180:
            continue
        item = db.save_memory(fact)
        if not item.get("duplicate"):
            saved.append(item["fact"])
    return saved


def code_shadow() -> str | None:
    global _CODE_ALERTED
    if _CODE_ALERTED or _CODE_SINCE is None:
        return None
    minutes = (datetime.now() - _CODE_SINCE).total_seconds() / 60
    if minutes < 50:
        return None
    _CODE_ALERTED = True
    return (
        f"Masih di kode sudah {int(minutes)} menit, {OWNER_CALL}. "
        "Mau kuingatkan istirahat 50 menit lagi?"
    )


def yesterday_files(limit: int = 6) -> str:
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    end = start + timedelta(days=1)
    hits: list[tuple[float, Path]] = []
    for root in _search_roots():
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")]
            try:
                depth = Path(dirpath).relative_to(root).parts
            except ValueError:
                continue
            if len(depth) > 2:
                dirnames[:] = []
                continue
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if start.timestamp() <= mtime < end.timestamp():
                    hits.append((mtime, path))
    hits.sort(reverse=True)
    if not hits:
        return "Tidak ada file yang diubah kemarin di Desktop/Documents/Downloads."
    lines = [str(path) for _mtime, path in hits[:limit]]
    return "\n".join(lines)


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = [(page.extract_text() or "") for page in reader.pages[:25]]
    return "\n".join(parts).strip()


def _extract_docx(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()


def extract_any(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in {".docx", ".doc"}:
        if suffix == ".doc":
            return "File .doc lama. Simpan ulang sebagai .docx agar bisa kubaca."
        return _extract_docx(path)
    if suffix in TEXT_EXT:
        return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _filename_from_title(title: str) -> str:
    match = re.search(r"([^\\/:*?\"<>|\r\n]+\.(pdf|docx|doc|txt|md|html))", title, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def summarize_active() -> str:
    title = last_app_title() or foreground_title()
    name = _filename_from_title(title)
    if not name:
        head = re.split(r"\s+[-—]\s+", title, maxsplit=1)[0].strip()
        if "." in head:
            name = head
    if name:
        search_files(name, limit=1)
        file_path = load_context().get("file")
        if file_path and Path(file_path).exists():
            body = extract_any(Path(file_path))
            if body:
                save_context({"result": body[:280], "topic": Path(file_path).name})
                return f"Sumber: {file_path}\n\n{body[:8000]}"
    if re.search(r"chrome|edge|firefox|brave", title, flags=re.IGNORECASE):
        page = re.sub(
            r"\s+[-—]\s+(Google Chrome|Microsoft Edge|Firefox|Brave).*$",
            "",
            title,
            flags=re.IGNORECASE,
        )
        from jin.magic import read_screen

        screen = read_screen()
        return (
            f"Halaman web: {page}\n\nIsi layar:\n{screen[:5000]}\n\n"
            "Ringkas ini untuk bos Rehan, singkat dan jelas."
        )
    clip = load_context().get("clipboard") or ""
    if clip:
        return f"Teks clipboard:\n{clip}\n\nRingkas untuk bos Rehan."
    return f"Jendela aktif: {title or '-'}\nTidak ketemu PDF/Word. Coba 'baca layar'."
