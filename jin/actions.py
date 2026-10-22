from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

from jin import codehelp
from jin import db
from jin import magic
from jin import memory as jin_memory
from jin import smart
from jin.config import OWNER_CALL
from jin.when import extract_reminder, parse_when

APP_ALIASES = {
    "notepad": ["notepad.exe"],
    "catatan": ["notepad.exe"],
    "kalkulator": ["calc.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "file": ["explorer.exe"],
    "folder": ["explorer.exe"],
    "cmd": ["cmd.exe"],
    "terminal": ["wt.exe", "cmd.exe"],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "browser": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ],
    "vscode": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        "code",
    ],
    "vs code": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        "code",
    ],
    "visual studio code": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        "code",
    ],
    "code": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        "code",
    ],
    "spotify": [
        os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
    ],
    "whatsapp": [
        os.path.expandvars(r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe"),
    ],
    "desktop": [str(Path.home() / "Desktop")],
    "desktops": [str(Path.home() / "Desktop")],
    "dokumen": [str(Path.home() / "Documents")],
    "documents": [str(Path.home() / "Documents")],
    "download": [str(Path.home() / "Downloads")],
    "downloads": [str(Path.home() / "Downloads")],
}


def _unsafe(value: str) -> bool:
    return bool(re.search(r"[|&;`$<>\n]", value))


def search_google(query: str, open_browser: bool = False) -> str:
    query = query.strip()
    if not query:
        return "Query kosong."
    google_url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
    lines = [f"Google: {google_url}"]
    try:
        from ddgs import DDGS

        try:
            hits = DDGS().text(query, region="id-id", max_results=5, backend="google")
        except Exception:
            hits = DDGS().text(query, region="id-id", max_results=5)
        if not hits:
            lines.append("Tidak ada ringkasan hasil. Buka tautan Google di atas.")
        for index, hit in enumerate(hits, start=1):
            title = hit.get("title") or "(tanpa judul)"
            url = hit.get("href") or ""
            snippet = hit.get("body") or ""
            lines.append(f"{index}. {title}\n   {snippet}\n   {url}")
    except Exception as exc:
        lines.append(f"Ringkasan gagal ({exc}). Tetap bisa buka Google.")
    if open_browser:
        webbrowser.open(google_url)
        lines.append("Halaman Google sudah dibuka di browser.")
    return "\n".join(lines)


def save_note(text: str, title: str = "") -> str:
    if not text.strip():
        return "Catatan kosong, tidak disimpan."
    note = db.save_note(text, title=title)
    return f"Catatan #{note['id']} disimpan: {note['title']}"


def list_notes(query: str = "") -> str:
    notes = db.list_notes(query)
    if not notes:
        return "Belum ada catatan." if not query else f"Tidak ada catatan untuk '{query}'."
    lines = []
    for note in notes:
        lines.append(f"#{note['id']} {note['title']} ({note['created_at']})\n{note['content']}")
    return "\n\n".join(lines)


def set_reminder(text: str, when: str = "") -> str:
    blob = f"{text} {when}".strip()
    extracted = extract_reminder(blob)
    if extracted:
        task, fire_at = extracted
    else:
        fire_at = parse_when(when or blob)
        task = text.strip() or "pengingat"
        if fire_at is None:
            return (
                "Waktunya belum kebaca. Contoh: "
                "'ingatkan saya minum air dalam 5 menit' atau 'ingatkan rapat jam 15:00'."
            )
    item = db.add_reminder(task, fire_at)
    nice = fire_at.strftime("%d/%m %H:%M")
    return f"Pengingat #{item['id']} diset jam {nice}: {item['text']}"


def list_reminders() -> str:
    items = db.list_reminders()
    if not items:
        return "Tidak ada pengingat aktif."
    lines = []
    for item in items:
        lines.append(f"#{item['id']} {item['fire_at']} — {item['text']}")
    return "\n".join(lines)


def open_item(name: str) -> str:
    name = name.strip().strip('"').strip("'")
    if not name:
        return "Tidak ada yang bisa dibuka."
    if _unsafe(name):
        return "Nama itu tidak aman untuk dibuka."
    if name.lower().startswith(("http://", "https://")):
        webbrowser.open(name)
        return f"Browser dibuka: {name}"

    if name.lower().startswith("google "):
        return search_google(name[7:].strip(), open_browser=True)
    if name.lower() in {"google", "google.com"}:
        webbrowser.open("https://www.google.com")
        return "Google dibuka di browser."

    key = name.lower().strip()
    if key in {"vscode", "vs code", "visual studio code", "code"}:
        return codehelp.open_vscode()
    candidates = APP_ALIASES.get(key, [])
    path = Path(os.path.expandvars(name)).expanduser()
    if path.exists():
        os.startfile(path)  # noqa: S606
        return f"Dibuka: {path}"

    for candidate in candidates:
        mapped = Path(os.path.expandvars(candidate)).expanduser()
        if mapped.exists():
            os.startfile(mapped)  # noqa: S606
            return f"Dibuka: {mapped.name}"
        found = shutil.which(candidate)
        if found:
            subprocess.Popen([found], close_fds=True)
            return f"Dibuka: {found}"

    found = shutil.which(name)
    if found:
        subprocess.Popen([found], close_fds=True)
        return f"Dibuka: {found}"

    return f"Tidak ketemu '{name}'. Coba path lengkap, atau nama seperti chrome, notepad, desktop."


def windows_toast(title: str, body: str) -> None:
    def esc(value: str) -> str:
        return value.replace("'", "''")[:180]

    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        f"$n.BalloonTipTitle = '{esc(title)}'; "
        f"$n.BalloonTipText = '{esc(body)}'; "
        "$n.Visible = $true; "
        "$n.ShowBalloonTip(8000); "
        "Start-Sleep -Seconds 8; "
        "$n.Dispose();"
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        close_fds=True,
    )


def run_mantra(name: str) -> str:
    key = name.lower().strip()
    if key == "fokus":
        return "\n".join(
            [
                magic.set_form("serius"),
                magic.volume("turun"),
                magic.daily_radar(),
            ]
        )
    if key in {"lanjut", "kerja", "coding"}:
        return "\n".join(
            [
                magic.set_form("serius"),
                codehelp.resume_coding(""),
            ]
        )
    if key == "pulang":
        def _lock_later() -> None:
            time.sleep(7)
            magic.lock_pc()

        threading.Thread(target=_lock_later, daemon=True).start()
        return f"Selamat pulang, {OWNER_CALL}. Laptop terkunci sebentar lagi."
    return "Mantra yang dikenal: fokus, lanjut/kerja, pulang."


def morning_brief() -> str:
    radar = magic.daily_radar()
    weather = search_google("cuaca Jambi hari ini", False)
    files = smart.yesterday_files()
    return f"{radar}\n\nCuaca Jambi:\n{weather}\n\nFile yang diubah kemarin:\n{files}"


def execute(name: str, args: dict) -> str:
    result = _execute(name, args)
    smart.remember_action(name, args, result)
    return result


def _execute(name: str, args: dict) -> str:
    if name == "search_google":
        return search_google(str(args.get("query") or ""), bool(args.get("open_browser")))
    if name == "save_note":
        return save_note(str(args.get("text") or ""), str(args.get("title") or ""))
    if name == "list_notes":
        return list_notes(str(args.get("query") or ""))
    if name == "set_reminder":
        return set_reminder(str(args.get("text") or ""), str(args.get("when") or ""))
    if name == "list_reminders":
        return list_reminders()
    if name == "open_item":
        target = str(args.get("name") or "")
        opened = open_item(target)
        if opened.startswith("Tidak ketemu") and target:
            found = smart.search_files(target, limit=1)
            ctx = smart.load_context().get("file")
            if ctx:
                return open_item(ctx)
            return found
        return opened
    if name == "search_files":
        return smart.search_files(str(args.get("query") or ""))
    if name == "read_file":
        return smart.read_file(str(args.get("path") or args.get("query") or ""))
    if name == "laptop_context":
        return smart.laptop_context()
    if name == "read_screen":
        return magic.read_screen()
    if name == "describe_screen":
        return magic.describe_screen(str(args.get("question") or ""))
    if name == "clipboard_get":
        return magic.clipboard_get()
    if name == "clipboard_set":
        return magic.clipboard_set(str(args.get("text") or ""))
    if name == "paste_last_window":
        return magic.paste_to_last_window(str(args.get("text") or ""))
    if name == "volume":
        return magic.volume(str(args.get("action") or ""))
    if name == "lock_pc":
        return magic.lock_pc()
    if name == "set_form":
        return magic.set_form(str(args.get("name") or ""))
    if name == "daily_radar":
        return magic.daily_radar()
    if name == "save_memory":
        return magic.save_memory(str(args.get("fact") or ""))
    if name == "list_memories":
        return magic.list_memories()
    if name == "screenshot":
        path = magic.screenshot()
        return f"Screenshot disimpan: {path}"
    if name == "mantra":
        return run_mantra(str(args.get("name") or ""))
    if name == "summarize_active":
        return smart.summarize_active()
    if name == "translate_clip":
        text = magic.clipboard_get()
        if text.startswith("Clipboard"):
            text = smart.load_context().get("clipboard") or text
        return f"Terjemahkan ke bahasa Indonesia, singkat:\n{text}"
    if name == "morning_brief":
        return morning_brief()
    if name == "open_vscode":
        return codehelp.open_vscode(str(args.get("path") or ""))
    if name == "create_folder":
        return codehelp.create_folder(
            str(args.get("name") or ""),
            str(args.get("parent") or ""),
            bool(args.get("open_in_vscode", True)),
        )
    if name == "install_library":
        return codehelp.install_library(
            str(args.get("packages") or args.get("package") or ""),
            str(args.get("path") or ""),
            str(args.get("manager") or "auto"),
        )
    if name == "recall_memory":
        return jin_memory.remember_query(str(args.get("query") or ""))
    if name == "resume_coding":
        return codehelp.resume_coding(
            str(args.get("hint") or args.get("project") or args.get("path") or ""),
            bool(args.get("install_deps", True)),
            bool(args.get("open_terminal", True)),
        )
    if name == "list_projects":
        return codehelp.list_known_projects()
    if name == "draft_commit":
        return codehelp.draft_commit_message(str(args.get("path") or args.get("hint") or ""))
    if name == "git_commit":
        return codehelp.git_commit(
            str(args.get("path") or args.get("hint") or ""),
            str(args.get("message") or ""),
            bool(args.get("add_all", True)),
        )
    if name == "git_push":
        return codehelp.git_push(
            str(args.get("path") or args.get("hint") or ""),
            str(args.get("remote") or "origin"),
            bool(args.get("set_upstream", True)),
        )
    if name == "git_commit_and_push":
        return codehelp.git_commit_and_push(
            str(args.get("path") or args.get("hint") or ""),
            str(args.get("message") or ""),
            str(args.get("remote") or "origin"),
        )
    return f"Tool tidak dikenal: {name}"


def match_intent(text: str) -> tuple[str, dict] | None:
    raw = text.strip()
    lower = raw.lower().strip()

    if re.fullmatch(r"fokus|mantra fokus", lower):
        return "mantra", {"name": "fokus"}
    if re.fullmatch(r"pulang|mantra pulang", lower):
        return "mantra", {"name": "pulang"}
    if re.fullmatch(r"(?:mantra\s+)?(?:lanjut|kerja|coding)", lower):
        return "mantra", {"name": "lanjut"}
    if re.match(
        r"^(?:tolong\s+)?(?:lanjut(?:kan)?(?:\s+(?:coding|koding|ngoding|session|sesi|project|proyek))?"
        r"|siap\s+(?:coding|ngoding)|clone\s+session)"
        r"(?:\s+(.+))?$",
        raw,
        re.I,
    ):
        hint_m = re.match(
            r"^(?:tolong\s+)?(?:lanjut(?:kan)?(?:\s+(?:coding|koding|ngoding|session|sesi|project|proyek))?"
            r"|siap\s+(?:coding|ngoding)|clone\s+session)"
            r"(?:\s+(.+))?$",
            raw,
            re.I,
        )
        hint = (hint_m.group(1) if hint_m else "") or ""
        hint = hint.strip()
        # "lanjut kemarin" / "lanjutkan yang kemarin" → empty hint (resolve last project)
        if re.fullmatch(r"(?:yang\s+)?(?:kemarin|dulu|sebelumnya|terakhir)", hint, re.I):
            hint = ""
        return "resume_coding", {"hint": hint, "install_deps": True, "open_terminal": True}
    if re.match(r"^(?:daftar|lihat|tampilkan)\s+project(?:s)?$", lower):
        return "list_projects", {}
    # git commit / push
    if re.match(
        r"^(?:tolong\s+)?(?:commit(?:\s+dan\s+push)?|git\s+commit(?:\s+and\s+push)?|commitkan|push(?:\s+ke\s+remote)?)\b",
        lower,
    ):
        do_push = bool(re.search(r"\bpush\b", lower))
        only_push = bool(re.match(r"^(?:tolong\s+)?(?:git\s+)?push\b", lower)) and not re.search(
            r"\bcommit\b", lower
        )
        msg_m = re.search(
            r"(?:pesan|message|msg|judul)\s*[:\-]\s*(.+)$",
            raw,
            re.I,
        )
        message = msg_m.group(1).strip() if msg_m else ""
        path_m = re.search(r"\s+(?:di|di\s+project|di\s+proyek)\s+(.+)$", raw, re.I)
        path = ""
        if path_m and not msg_m:
            path = path_m.group(1).strip()
            path = re.sub(r"\s+(?:pesan|message|msg|judul)\s*[:\-].*$", "", path, flags=re.I).strip()
        if only_push:
            return "git_push", {"path": path, "remote": "origin"}
        if do_push:
            return "git_commit_and_push", {"path": path, "message": message, "remote": "origin"}
        return "git_commit", {"path": path, "message": message, "add_all": True}
    if re.match(
        r"^(?:tolong\s+)?(?:draft\s+commit|ringkas\s+commit|buatkan\s+pesan\s+commit|usulkan\s+commit)\b",
        lower,
    ):
        return "draft_commit", {"path": ""}
    if re.match(
        r"^(?:tolong\s+|coba\s+)?(?:ringkas(?:kan)?|rangkum(?:kan)?)"
        r"(?:\s+(?:ini|jendela|halaman|pdf|dokumen|clipboard|layar|yang\s+terbuka))?$",
        lower,
    ):
        return "summarize_active", {}
    if re.fullmatch(r"terjemah(kan)?|translate", lower):
        return "translate_clip", {}
    if re.fullmatch(r"radar pagi|briefing pagi", lower):
        return "morning_brief", {}
    if lower in {"catat", "catetin"} and smart.load_context().get("clipboard"):
        return "save_note", {"text": smart.load_context()["clipboard"]}
    if re.match(r"^(lihat|tampilkan|daftar)\s+catatan", lower):
        return "list_notes", {"query": ""}
    if re.match(r"^(lihat|tampilkan|daftar)\s+pengingat", lower):
        return "list_reminders", {}
    if re.match(r"^(radar|briefing|hari ini|laporan hari)\b", lower):
        return "daily_radar", {}
    if re.match(r"^(jendela (apa|aktif)|lagi ngapain|kerjaan apa)\b", lower):
        return "laptop_context", {}
    describe = re.match(
        r"^(?:tolong\s+|coba\s+)?(?:"
        r"(?:jelaskan|jelasin|pahami|analisa|analisis|terangkan)\s+(?:apa\s+(?:yang\s+)?(?:ada\s+)?di\s+)?"
        r"(?:isi\s+)?layar(?:\s+(?:ini|saya))?"
        r"|(?:layar|error)\s+ini\s+(?:error\s+)?(?:apa|kenapa|maksudnya\s+apa)"
        r"|kenapa\s+(?:error|eror)\s+(?:ini|di\s+layar)"
        r"|apa\s+yang\s+terjadi\s+di\s+layar"
        r")\s*[,:\-]?\s*(.*)$",
        raw,
        re.I,
    )
    if describe:
        return "describe_screen", {"question": (describe.group(1) or "").strip() or raw}
    if re.match(
        r"^(?:tolong\s+|coba\s+)?(?:baca(?:in)?|lihat|ocr|bacakan)\s+"
        r"(?:isi\s+)?(?:layar|screen)(?:\s+saya)?(?:\s+yang\s+(?:sedang\s+)?(?:dibuka|terbuka))?$",
        lower,
    ) or re.match(
        r"^(?:tolong\s+|coba\s+)?(?:apa\s+(?:yang\s+)?(?:ada\s+)?di\s+layar|"
        r"isi\s+layar(?:\s+saya)?|lihat\s+apa\s+yang\s+(?:aku|saya)\s+buka)$",
        lower,
    ):
        return "read_screen", {}
    if re.match(
        r"^(?:tolong\s+|coba\s+)?(?:screenshot|jepret\s+layar|ambil\s+(?:screenshot|gambar\s+layar))",
        lower,
    ):
        return "screenshot", {}
    file_search = re.match(
        r"^(?:tolong\s+|coba\s+)?(?:cari\s+(?:file|dokumen|berkas)|cari\s+di\s+laptop)\s+(.+)$",
        raw,
        re.I,
    )
    if file_search:
        return "search_files", {"query": file_search.group(1).strip()}
    read = re.match(
        r"^(?:tolong\s+|coba\s+)?"
        r"(?:baca(?:in)?(?:\s+isi)?|buka|isi(?:\s+dari)?)\s+"
        r"(?:file|dokumen|berkas)\s+(.+)$",
        raw,
        re.I,
    )
    if read:
        return "read_file", {"path": read.group(1).strip()}
    read_path = re.match(
        r"^(?:tolong\s+|coba\s+)?baca(?:in)?\s+"
        r"((?:[A-Za-z]:[\\/]|\\\\|~[\\/]|\.{1,2}[\\/]).+)$",
        raw,
        re.I,
    )
    if read_path:
        return "read_file", {"path": read_path.group(1).strip()}
    if re.match(r"^(kunci laptop|lock laptop|kunci pc)\b", lower):
        return "lock_pc", {}
    if re.match(r"^volume\s+(naik|turun|mute|bisukan|besar|kecil)\b", lower):
        return "volume", {"action": lower.split()[-1]}
    if re.match(r"^(naikkan|kecilkan|besarkan)\s+volume", lower):
        return "volume", {"action": "naik" if "naik" in lower or "besar" in lower else "turun"}
    if re.match(r"^bisukan\s+volume|^mute\b", lower):
        return "volume", {"action": "mute"}
    form = re.match(r"^(?:mode|wujud)\s+(tenang|nyentrik|serius|kerja)\b", lower)
    if form:
        return "set_form", {"name": form.group(1)}
    memory = re.match(r"^(?:ingat(?:\s+bahwa)?|simpan ingatan)\s*[:\-]\s*(.+)$", raw, re.I)
    if memory:
        return "save_memory", {"fact": memory.group(1).strip()}
    recall = re.match(
        r"^(?:apa yang kamu ingat|ingat(?:kah)?(?:\s+soal|\s+tentang)?|cari ingatan|recall)\s+"
        r"(?:soal|tentang|ttg|mengenai)?\s*[:\- ]*(.+)$",
        raw,
        re.I,
    )
    if recall:
        return "recall_memory", {"query": recall.group(1).strip()}
    if re.match(
        r"^(?:proyek|project)\s+(?:yang\s+)?(?:kemarin|dulu|sebelumnya|terakhir)\??$",
        lower,
    ):
        return "recall_memory", {"query": "proyek kemarin project terakhir"}
    if re.match(r"^(apa yang kamu ingat|lihat ingatan|daftar ingatan|ingatan kamu)\s*$", lower):
        return "list_memories", {}
    clip = re.match(r"^(?:baca|lihat)\s+clipboard$", lower)
    if clip:
        return "clipboard_get", {}
    paste = re.match(r"^(?:tempelkan|tempel|ketik(?:kan)?)\s+(.+)$", raw, re.I)
    if paste and "catat" not in lower:
        return "paste_last_window", {"text": paste.group(1).strip()}

    note = re.match(r"^(?:tolong\s+)?(?:catat(?:kan|in)?|simpan catatan)\s*[:\- ]\s*(.+)$", raw, re.I)
    if note:
        return "save_note", {"text": note.group(1).strip()}

    reminder = re.search(r"\bingatkan\b", lower) and parse_when(lower)
    if reminder:
        return "set_reminder", {"text": raw, "when": raw}

    vscode_open = re.match(
        r"^(?:tolong\s+)?(?:buka|jalankan)\s+(?:vs\s*code|visual\s+studio\s+code|code)"
        r"(?:\s+(?:di|folder|project|proyek|projek)\s+(.+))?$",
        raw,
        re.I,
    )
    if vscode_open:
        path = (vscode_open.group(1) or "").strip()
        return "open_vscode", {"path": path}

    # "buka project pajak jambi" / "buka projek ... kemarin" → VS Code, bukan open_item
    buka_project = re.match(
        r"^(?:tolong\s+)?(?:buka|jalankan)\s+"
        r"(?:(?:di\s+)?(?:vs\s*code|visual\s+studio\s+code|code|cursor)\s+)?"
        r"(?:project|projek|folder|repo)\s+(.+)$",
        raw,
        re.I,
    )
    if buka_project:
        hint = buka_project.group(1).strip()
        hint = re.sub(
            r"\s+(?:lalu|terus|dan|,|;)\s+.*$",
            "",
            hint,
            flags=re.I,
        ).strip()
        hint = re.sub(
            r"\s+(?:saya|aku)(?:\s+yang)?(?:\s+(?:kemarin|dulu|sebelumnya|terakhir))?$",
            "",
            hint,
            flags=re.I,
        ).strip()
        hint = re.sub(
            r"\s+yang\s+(?:kemarin|dulu|sebelumnya|terakhir|tadi)$",
            "",
            hint,
            flags=re.I,
        ).strip()
        return "open_vscode", {"path": hint}

    make_folder = re.match(
        r"^(?:tolong\s+)?(?:buat(?:kan)?|bikin|create)\s+(?:folder|direktori|project|proyek)\s+"
        r"(.+?)(?:\s+(?:di\s+)?(?:vs\s*code|visual\s+studio\s+code|code))?$",
        raw,
        re.I,
    )
    if make_folder:
        name = make_folder.group(1).strip().strip('"').strip("'")
        name = re.sub(
            r"\s+(?:di\s+)?(?:vs\s*code|visual\s+studio\s+code|code|desktop|dokumen|documents)$",
            "",
            name,
            flags=re.I,
        ).strip()
        parent = ""
        if re.search(r"\bdesktop\b", lower):
            parent = str(Path.home() / "Desktop")
        elif re.search(r"\b(dokumen|documents)\b", lower):
            parent = str(Path.home() / "Documents")
        return "create_folder", {"name": name, "parent": parent, "open_in_vscode": True}

    install = re.match(
        r"^(?:tolong\s+)?(?:(?:pip|npm|yarn|pnpm)\s+install|install(?:\s+(?:library|lib|paket|package|packages))?)\s+(.+)$",
        raw,
        re.I,
    )
    if install:
        blob = install.group(1).strip()
        manager = "auto"
        if re.match(r"^pip\s+install\b", lower):
            manager = "pip"
        elif re.match(r"^npm\s+install\b", lower):
            manager = "npm"
        elif re.match(r"^yarn\s+", lower):
            manager = "yarn"
        elif re.match(r"^pnpm\s+", lower):
            manager = "pnpm"
        path = ""
        path_m = re.search(r"\s+(?:di|di\s+folder|di\s+project|di\s+proyek)\s+(.+)$", blob, re.I)
        packages = blob
        if path_m:
            path = path_m.group(1).strip()
            packages = blob[: path_m.start()].strip()
        packages = re.sub(r"^(library|lib|paket|package|packages)\s+", "", packages, flags=re.I)
        return "install_library", {"packages": packages, "path": path, "manager": manager}

    opened = re.match(r"^(?:tolong\s+)?buka\s+(.+)$", raw, re.I)
    if opened:
        return "open_item", {"name": opened.group(1).strip()}

    search = re.match(
        r"^(?:tolong\s+)?(?:cari(?:kan)?|google(?:kan)?|search(?:ing)?)\s+(?:di\s+google\s+)?[:\- ]*(.+)$",
        raw,
        re.I,
    )
    if search:
        query = search.group(1).strip()
        query = re.sub(r"^(di\s+)?google\s+", "", query, flags=re.I).strip()
        open_browser = "google" in lower or "browser" in lower
        return "search_google", {"query": query, "open_browser": open_browser}

    return None


def match_intents(text: str) -> list[tuple[str, dict]]:
    cleaned = re.sub(
        r"^(he[iy]\s+|halo\s+|hai\s+)?((jin|asghard)\s+)*",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    ).strip(" ,.")
    cleaned = re.sub(
        r"^(?:tolong(?:lah)?|coba|mohon)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip(" ,.")
    cleaned = smart.resolve_references(cleaned)
    if not cleaned:
        return []
    if re.search(r",|;|\bdan\b|\blalu\b|\bterus\b", cleaned, flags=re.IGNORECASE):
        parts = [
            part.strip(" .")
            for part in re.split(r"\s*(?:,|;|\blalu\b|\bterus\b|\bdan\b)\s*", cleaned, flags=re.IGNORECASE)
            if part.strip(" .")
        ]
    else:
        parts = [cleaned]
    found: list[tuple[str, dict]] = []
    for part in parts:
        one = match_intent(part)
        if one:
            found.append(one)
    if not found:
        one = match_intent(cleaned) or match_intent(text)
        if one:
            found.append(one)
    return found


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_google",
            "description": "Cari informasi di Google/internet. Pakai jika bos minta cari, google, atau info terkini.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "open_browser": {
                        "type": "boolean",
                        "description": "True jika bos minta buka Google di browser.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "Simpan catatan di laptop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "Lihat catatan yang sudah disimpan.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set pengingat. when contoh: 'dalam 5 menit' atau 'jam 15:00'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "when": {"type": "string"},
                },
                "required": ["text", "when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "Lihat pengingat aktif.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_item",
            "description": "Buka aplikasi, folder, file, atau URL di laptop. Contoh: chrome, notepad, desktop, D:\\folder",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_screen",
            "description": (
                "Ambil screenshot jendela kerja (bukan Jin) dan baca tulisannya via OCR. "
                "Pakai jika bos minta baca/lihat layar, isi layar, atau apa yang sedang terbuka."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_screen",
            "description": (
                "Lihat jendela kerja dengan model vision lokal lalu jelaskan isinya. "
                "Pakai jika bos minta jelaskan/pahami layar, atau tanya arti error yang tampil."
            ),
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Ambil screenshot dan simpan ke Desktop (tanpa OCR).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_get",
            "description": "Baca isi clipboard.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_set",
            "description": "Isi clipboard dengan teks.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "paste_last_window",
            "description": "Tempel teks ke jendela sebelumnya (Alt+Tab lalu paste).",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "volume",
            "description": "Atur volume laptop. action: naik, turun, mute.",
            "parameters": {
                "type": "object",
                "properties": {"action": {"type": "string"}},
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lock_pc",
            "description": "Kunci laptop Windows.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_form",
            "description": "Ganti wujud Jin: tenang, nyentrik, atau serius.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "daily_radar",
            "description": "Radar harian: waktu, pengingat, catatan, ingatan.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Simpan fakta jangka panjang tentang bos Rehan.",
            "parameters": {
                "type": "object",
                "properties": {"fact": {"type": "string"}},
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memories",
            "description": "Lihat ingatan jangka panjang.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": (
                "Cari file menurut nama di Desktop, Documents, Downloads, folder project, "
                "dan workspace terakhir."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Baca isi file di laptop: teks (.txt/.md/.py/.json/dll), PDF, atau Word (.docx). "
                "path boleh nama file atau path lengkap."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "query": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "laptop_context",
            "description": "Lihat jendela kerja terakhir dan topik/file terakhir.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mantra",
            "description": "Mantra kerja. name: fokus, lanjut/kerja (clone coding session), atau pulang.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_active",
            "description": "Ringkas PDF, Word, halaman web, atau jendela yang sedang dibuka.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "morning_brief",
            "description": "Radar pagi: cuaca Jambi, pengingat, file kemarin.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_vscode",
            "description": (
                "Buka VS Code/Cursor. path boleh kosong, path folder, atau nama project "
                "(contoh: 'pajak jambi'). Pakai untuk 'buka project/projek/folder …'."
            ),
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": (
                "Buat folder project baru (default di Documents/JinProjects) "
                "dan buka di VS Code. name = nama folder."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "parent": {"type": "string", "description": "Folder induk opsional."},
                    "open_in_vscode": {"type": "boolean"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_library",
            "description": (
                "Install library di folder project (pip/npm). "
                "packages contoh: 'requests flask' atau 'express'. "
                "path opsional; kalau kosong pakai project terakhir / JinProjects."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "packages": {"type": "string"},
                    "path": {"type": "string"},
                    "manager": {
                        "type": "string",
                        "description": "auto | pip | npm | yarn | pnpm",
                    },
                },
                "required": ["packages"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": (
                "Cari ingatan semantik dari catatan, fakta, dan obrolan lama. "
                "Pakai jika bos tanya proyek kemarin, fakta lama, atau 'ingat soal ...'."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resume_coding",
            "description": (
                "Lanjutkan session coding: buka project terakhir/disebut di VS Code, "
                "cek git status + file berubah, install deps jika belum, buka terminal. "
                "Pakai untuk 'lanjut kemarin', 'lanjut coding', 'siap ngoding'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hint": {
                        "type": "string",
                        "description": "Nama/path project opsional. Kosong = project terakhir.",
                    },
                    "install_deps": {"type": "boolean"},
                    "open_terminal": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": "Lihat daftar project coding yang Jin ingat.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_commit",
            "description": "Ringkas git diff jadi usulan nama/pesan commit (tanpa commit).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": (
                "Commit perubahan di project aktif. "
                "Kalau message kosong, Jin meringkas diff jadi nama commit. "
                "Pakai untuk 'commit' / 'commitkan'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "message": {"type": "string"},
                    "add_all": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_push",
            "description": "Push branch aktif ke remote (default origin).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "remote": {"type": "string"},
                    "set_upstream": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit_and_push",
            "description": (
                "Commit (pesan auto dari ringkasan diff jika kosong) lalu push. "
                "Pakai untuk 'commit dan push'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "message": {"type": "string"},
                    "remote": {"type": "string"},
                },
            },
        },
    },
]


def describe_call(name: str, args: dict) -> str:
    return f"{name} {json.dumps(args, ensure_ascii=False)}"
