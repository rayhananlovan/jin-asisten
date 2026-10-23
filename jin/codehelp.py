from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

from jin import db
from jin import smart
from jin.config import PROJECTS_DIR

_CODE_CANDIDATES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
    os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe"),
    "code",
]
_CURSOR_CANDIDATES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\cursor\Cursor.exe"),
    "cursor",
]

_SAFE_FOLDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,80}$")
_SAFE_PKG = re.compile(r"^[A-Za-z0-9@/_.\-\[\]<>=!~^,]+$")
_SHELL_BAD = re.compile(r"[|&;`$<>\n]")
_PROJECT_MARKERS = (
    ".git",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "composer.json",
    "pom.xml",
)
_HISTORY_KEY = "project_history"
_HISTORY_LIMIT = 24


def find_code() -> str | None:
    for candidate in _CODE_CANDIDATES:
        mapped = Path(os.path.expandvars(candidate)).expanduser()
        if mapped.exists():
            return str(mapped)
        found = shutil.which(candidate)
        if found:
            return found
    return None


def find_editor() -> tuple[str, str] | None:
    code = find_code()
    if code:
        return code, "VS Code"
    for candidate in _CURSOR_CANDIDATES:
        mapped = Path(os.path.expandvars(candidate)).expanduser()
        if mapped.exists():
            return str(mapped), "Cursor"
        found = shutil.which(candidate)
        if found:
            return found, "Cursor"
    return None


def _workspace_from_context() -> Path | None:
    ctx = smart.load_context()
    for key in ("workspace", "project", "file", "opened"):
        raw = (ctx.get(key) or "").strip()
        if not raw or raw.lower() in {"vscode", "code", "cursor"}:
            continue
        path = Path(os.path.expandvars(raw)).expanduser()
        if path.is_file():
            path = path.parent
        if path.is_dir():
            return path
    return None


def _load_history() -> list[dict]:
    raw = db.get_setting(_HISTORY_KEY, "")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data:
        if isinstance(item, dict) and item.get("path"):
            out.append(item)
        elif isinstance(item, str):
            out.append({"path": item, "name": Path(item).name})
    return out


def _save_history(items: list[dict]) -> None:
    db.set_setting(_HISTORY_KEY, json.dumps(items[:_HISTORY_LIMIT], ensure_ascii=False))


def remember_project(path: Path | str) -> None:
    folder = Path(path).expanduser()
    if folder.is_file():
        folder = folder.parent
    if not folder.is_dir():
        return
    entry = {
        "path": str(folder.resolve()),
        "name": folder.name,
        "last_used": datetime.now().isoformat(timespec="seconds"),
    }
    history = [item for item in _load_history() if item.get("path") != entry["path"]]
    history.insert(0, entry)
    _save_history(history)
    smart.save_context(
        {
            "workspace": entry["path"],
            "project": entry["path"],
            "opened": "vscode",
            "topic": folder.name,
        }
    )


def _looks_like_project(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    for marker in _PROJECT_MARKERS:
        if (folder / marker).exists():
            return True
    if any(folder.glob("*.sln")):
        return True
    for pattern in ("*.py", "*.ts", "*.tsx", "*.js", "*.go", "*.rs"):
        if any(folder.glob(pattern)):
            return True
    return False


def _scan_recent_projects(limit: int = 10) -> list[Path]:
    roots = [
        PROJECTS_DIR,
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home() / "source",
        Path.home() / "projects",
        Path.home() / "dev",
        Path("D:/"),
    ]
    scored: list[tuple[float, Path]] = []
    seen: set[str] = set()

    def consider(child: Path) -> None:
        if not child.is_dir() or child.name.startswith("."):
            return
        name = child.name.lower()
        if name in {
            "windows",
            "program files",
            "program files (x86)",
            "$recycle.bin",
            "system volume information",
            "users",
            "perflogs",
            "node_modules",
            ".git",
            ".venv",
            "venv",
            "__pycache__",
        }:
            return
        if not _looks_like_project(child):
            return
        try:
            key = str(child.resolve()).lower()
        except OSError:
            return
        if key in seen:
            return
        seen.add(key)
        try:
            mtime = child.stat().st_mtime
        except OSError:
            return
        scored.append((mtime, child))

    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            consider(child)
        if root == Path("D:/"):
            continue
        for child in children:
            if not child.is_dir() or child.name.startswith("."):
                continue
            try:
                nested_list = list(child.iterdir())
            except OSError:
                continue
            for nested in nested_list:
                consider(nested)

    scored.sort(reverse=True)
    return [path for _mtime, path in scored[:limit]]


def resolve_project(hint: str = "", *, strict: bool = False) -> Path | None:
    """Find a project folder.

    If hint is non-empty, only return a path that matches that hint
    (unless strict=False and you want legacy fallback — use fallback=True).
    Empty hint → last workspace / history / recent.
    """
    raw = (hint or "").strip().strip('"').strip("'")
    raw = re.sub(
        r"^(?:yang\s+)?(?:kemarin|dulu|sebelumnya|terakhir|project|proyek|projek)\s*",
        "",
        raw,
        flags=re.I,
    ).strip()
    # Drop trailing noise: "saya kemarin", "yang tadi"
    raw = re.sub(
        r"\s+(?:saya|aku)(?:\s+yang)?(?:\s+(?:kemarin|dulu|sebelumnya|terakhir))?$",
        "",
        raw,
        flags=re.I,
    ).strip()
    raw = re.sub(
        r"\s+yang\s+(?:kemarin|dulu|sebelumnya|terakhir|tadi)$",
        "",
        raw,
        flags=re.I,
    ).strip()

    if raw and not _SHELL_BAD.search(raw):
        direct = Path(os.path.expandvars(raw)).expanduser()
        if direct.exists():
            return direct.parent if direct.is_file() else direct
        alt = (PROJECTS_DIR / raw).expanduser()
        if alt.exists():
            return alt
        needle = raw.lower()
        tokens = [t for t in re.split(r"\s+", needle) if len(t) > 1]

        def _name_match(path: Path) -> bool:
            name = path.name.lower()
            if name == needle or needle in name or name in needle:
                return True
            if tokens and all(token in name for token in tokens):
                return True
            return False

        for item in _load_history():
            path = Path(str(item.get("path") or ""))
            if path.exists() and _name_match(path):
                return path
        for path in _scan_recent_projects(24):
            if _name_match(path):
                return path
        # Hint given but nothing matched — do NOT open an unrelated project.
        if strict or raw:
            return None

    ctx = _workspace_from_context()
    if ctx and ctx.exists():
        return ctx

    for item in _load_history():
        path = Path(str(item.get("path") or ""))
        if path.exists() and path.is_dir():
            return path

    recent = _scan_recent_projects(1)
    return recent[0] if recent else None


def _launch_editor(binary: str, *args: str) -> None:
    """Start VS Code/Cursor reliably on Windows (detached from Jin)."""
    cmd = [binary, *[str(a) for a in args if str(a)]]
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        # start.exe avoids parent-console quirks with GUI apps
        subprocess.Popen(
            ["cmd", "/c", "start", "", "/B", *cmd],
            close_fds=True,
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    subprocess.Popen(
        cmd,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def open_vscode(path: str = "") -> str:
    editor = find_editor()
    if not editor:
        return "VS Code / Cursor tidak ketemu. Install salah satunya atau pastikan di PATH."

    binary, label = editor
    target = (path or "").strip().strip('"').strip("'")
    if not target:
        _launch_editor(binary)
        return f"{label} dibuka."

    if _SHELL_BAD.search(target):
        return "Path itu tidak aman."

    folder = Path(os.path.expandvars(target)).expanduser()
    if not folder.exists():
        alt = (PROJECTS_DIR / target).expanduser()
        if alt.exists():
            folder = alt
        else:
            resolved = resolve_project(target, strict=True)
            if resolved and resolved.exists():
                folder = resolved
            else:
                known = list_known_projects(5)
                return (
                    f"Folder/project tidak ketemu: {target}\n"
                    f"Coba path lengkap, atau sebut nama yang lebih pendek.\n{known}"
                )

    _launch_editor(binary, str(folder.resolve()))
    if folder.is_file():
        remember_project(folder.parent)
        return f"{label} membuka file: {folder.name}"
    remember_project(folder)
    return f"{label} membuka folder: {folder}"


def create_folder(name: str, parent: str = "", open_in_vscode: bool = True) -> str:
    raw = (name or "").strip().strip('"').strip("'")
    if not raw:
        return "Nama folder kosong."
    if _SHELL_BAD.search(raw) or ".." in raw:
        return "Nama folder tidak aman."

    candidate = Path(os.path.expandvars(raw)).expanduser()
    if candidate.is_absolute() or raw.startswith(("~", ".", "\\", "/")) or ":" in raw[:3]:
        folder = candidate
        if _SHELL_BAD.search(str(folder)):
            return "Path folder tidak aman."
    else:
        if not _SAFE_FOLDER.match(raw):
            return "Nama folder hanya huruf/angka/spasi/titik/strip."
        base = (parent or "").strip().strip('"').strip("'")
        if base:
            if _SHELL_BAD.search(base) or ".." in base:
                return "Folder induk tidak aman."
            root = Path(os.path.expandvars(base)).expanduser()
        else:
            root = PROJECTS_DIR
        root.mkdir(parents=True, exist_ok=True)
        folder = root / raw

    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"Gagal buat folder: {exc}"

    remember_project(folder)
    lines = [f"Folder siap: {folder}"]
    if open_in_vscode:
        lines.append(open_vscode(str(folder)))
    return "\n".join(lines)


def _detect_manager(workspace: Path, manager: str) -> str:
    key = (manager or "auto").strip().lower()
    if key in {"pip", "npm", "yarn", "pnpm"}:
        return key
    if (workspace / "package.json").exists():
        return "npm"
    if (workspace / "pyproject.toml").exists() or (workspace / "requirements.txt").exists():
        return "pip"
    if any(workspace.glob("*.py")):
        return "pip"
    return "pip"


def _split_packages(packages: str) -> list[str]:
    parts = re.split(r"[\s,]+", packages.strip())
    out: list[str] = []
    for part in parts:
        item = part.strip()
        if not item:
            continue
        if item.lower() in {"pip", "install", "npm", "library", "lib", "paket", "package", "packages"}:
            continue
        if not _SAFE_PKG.match(item) or _SHELL_BAD.search(item):
            raise ValueError(f"Nama paket tidak aman: {item}")
        out.append(item)
    return out


def install_library(packages: str, path: str = "", manager: str = "auto") -> str:
    try:
        pkgs = _split_packages(packages or "")
    except ValueError as exc:
        return str(exc)
    if not pkgs:
        return "Paket kosong. Contoh: install library requests flask"

    raw_path = (path or "").strip().strip('"').strip("'")
    if raw_path:
        if _SHELL_BAD.search(raw_path) or ".." in Path(raw_path).parts:
            return "Path project tidak aman."
        workspace = Path(os.path.expandvars(raw_path)).expanduser()
        if workspace.is_file():
            workspace = workspace.parent
    else:
        workspace = _workspace_from_context() or PROJECTS_DIR

    if not workspace.exists():
        try:
            workspace.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"Folder project tidak ada dan gagal dibuat: {exc}"

    kind = _detect_manager(workspace, manager)
    if kind == "pip":
        cmd = ["python", "-m", "pip", "install", *pkgs]
    elif kind == "npm":
        cmd = ["npm", "install", *pkgs]
    elif kind == "yarn":
        cmd = ["yarn", "add", *pkgs]
    else:
        cmd = ["pnpm", "add", *pkgs]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=600,
            shell=False,
        )
    except FileNotFoundError:
        return f"Perintah `{cmd[0]}` tidak ketemu di PATH."
    except subprocess.TimeoutExpired:
        return "Install terlalu lama (timeout 10 menit)."

    remember_project(workspace)
    smart.save_context({"topic": " ".join(pkgs)})
    tail = (proc.stdout or proc.stderr or "").strip()
    if len(tail) > 1200:
        tail = tail[-1200:]
    status = "berhasil" if proc.returncode == 0 else f"gagal (kode {proc.returncode})"
    return (
        f"Install {kind} ({status}) di {workspace}:\n"
        f"$ {' '.join(cmd)}\n"
        f"{tail or '(tanpa output)'}"
    )


def _run_git(workspace: Path, args: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError:
        return 1, ""
    except subprocess.TimeoutExpired:
        return 1, "(git timeout)"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, out


def git_snapshot(workspace: Path) -> str:
    if not (workspace / ".git").exists():
        return "Bukan repo git (tidak ada .git)."
    lines: list[str] = []
    code, branch = _run_git(workspace, ["rev-parse", "--abbrev-ref", "HEAD"])
    if code == 0 and branch:
        lines.append(f"Branch: {branch}")
    code, status = _run_git(workspace, ["status", "--short", "--branch"])
    if code == 0 and status:
        short = "\n".join(status.splitlines()[:25])
        lines.append("git status:\n" + short)
    else:
        lines.append("git status gagal / kosong.")
    code, changed = _run_git(
        workspace,
        ["log", "-5", "--pretty=format:%h %ad %s", "--date=short"],
    )
    if code == 0 and changed:
        lines.append("Commit terakhir:\n" + changed)
    code, names = _run_git(workspace, ["diff", "--name-only", "HEAD"])
    if code == 0 and names.strip():
        files = names.splitlines()[:12]
        lines.append("File berubah vs HEAD:\n- " + "\n- ".join(files))
    return "\n".join(lines)


def open_project_terminal(workspace: Path) -> str:
    wt = shutil.which("wt")
    try:
        if wt:
            subprocess.Popen([wt, "-d", str(workspace)], close_fds=True)
            return f"Windows Terminal dibuka di {workspace}"
        subprocess.Popen(
            ["cmd.exe", "/k", f"cd /d {workspace}"],
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            close_fds=True,
        )
        return f"CMD dibuka di {workspace}"
    except OSError as exc:
        return f"Terminal gagal dibuka: {exc}"


def ensure_deps(workspace: Path) -> str:
    notes: list[str] = []

    if (workspace / "package.json").exists() and not (workspace / "node_modules").exists():
        notes.append("node_modules belum ada → npm install...")
        try:
            proc = subprocess.run(
                ["npm", "install"],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=600,
                shell=False,
            )
            tail = (proc.stdout or proc.stderr or "").strip()[-800:]
            status = "ok" if proc.returncode == 0 else f"gagal ({proc.returncode})"
            notes.append(f"npm install: {status}\n{tail or '(tanpa output)'}")
        except FileNotFoundError:
            notes.append("npm tidak ketemu di PATH.")
        except subprocess.TimeoutExpired:
            notes.append("npm install timeout.")

    req = workspace / "requirements.txt"
    if req.exists():
        venv_python = None
        for candidate in (
            workspace / ".venv" / "Scripts" / "python.exe",
            workspace / "venv" / "Scripts" / "python.exe",
        ):
            if candidate.exists():
                venv_python = candidate
                break
        marker = workspace / ".venv" / ".jin_deps_ok"
        if venv_python is None:
            notes.append("Python venv belum ada → buat .venv + install requirements...")
            try:
                subprocess.run(
                    ["python", "-m", "venv", ".venv"],
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    shell=False,
                    check=False,
                )
                venv_python = workspace / ".venv" / "Scripts" / "python.exe"
            except Exception as exc:
                notes.append(f"Gagal buat venv: {exc}")
                venv_python = None
        if venv_python and venv_python.exists():
            if marker.exists():
                notes.append("Deps Python: sudah pernah diinstall (.jin_deps_ok).")
            else:
                notes.append("pip install -r requirements.txt...")
                try:
                    proc = subprocess.run(
                        [str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"],
                        cwd=str(workspace),
                        capture_output=True,
                        text=True,
                        timeout=600,
                        shell=False,
                    )
                    tail = (proc.stdout or proc.stderr or "").strip()[-800:]
                    if proc.returncode == 0:
                        try:
                            marker.parent.mkdir(parents=True, exist_ok=True)
                            marker.write_text("ok", encoding="utf-8")
                        except OSError:
                            pass
                        notes.append(f"pip: ok\n{tail or '(tanpa output)'}")
                    else:
                        notes.append(f"pip: gagal ({proc.returncode})\n{tail or '(tanpa output)'}")
                except subprocess.TimeoutExpired:
                    notes.append("pip install timeout.")
        elif req.exists() and venv_python is None:
            notes.append("requirements.txt ada tapi venv gagal dibuat — lewati pip.")

    if not notes:
        return "Deps: sudah terlihat siap (atau tidak ada package.json / requirements.txt)."
    return "\n".join(notes)


def list_known_projects(limit: int = 8) -> str:
    history = _load_history()
    lines = []
    for item in history[:limit]:
        path = item.get("path") or ""
        when = (item.get("last_used") or "")[:16].replace("T", " ")
        mark = "ok" if Path(path).exists() else "missing"
        lines.append(f"[{mark}] {item.get('name') or Path(path).name} — {path} ({when})")
    if not lines:
        recent = _scan_recent_projects(limit)
        if not recent:
            return "Belum ada jejak project. Buka folder di VS Code sekali, atau buat folder lewat Jin."
        return "Project terbaru di disk:\n" + "\n".join(f"- {p}" for p in recent)
    return "Project yang Jin ingat:\n" + "\n".join(lines)


_SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "secrets.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
}


def _resolve_repo(path: str = "") -> Path | None:
    workspace = resolve_project(path) if (path or "").strip() else resolve_project("")
    if workspace is None:
        return None
    folder = workspace if workspace.is_dir() else workspace.parent
    # Walk up for .git
    cur = folder
    for _ in range(6):
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return folder if (folder / ".git").exists() else None


def _ollama_commit_title(diff_blob: str) -> str:
    from jin.config import OLLAMA_MODEL, OLLAMA_URL

    prompt = (
        "Tulis SATU baris commit message untuk perubahan di bawah.\n"
        "Aturan: max 72 karakter, gaya imperative singkat (contoh: add wake word listener), "
        "boleh Indonesia atau Inggris, tanpa tanda kutip, tanpa penjelasan lain.\n\n"
        f"{diff_blob[:6000]}"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": "Kamu penulis commit message. Jawab hanya satu baris."},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.2},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = ((data.get("message") or {}).get("content") or "").strip()
    line = text.splitlines()[0].strip().strip('"').strip("'")
    line = re.sub(r"^(commit\s*message\s*:|pesan\s*:)\s*", "", line, flags=re.I)
    return line[:72]


def _heuristic_commit_title(names: list[str], status: str) -> str:
    basenames = [Path(name).name for name in names if name]
    if not basenames:
        if "??" in status:
            return "add untracked project files"
        return "update project files"
    focus = basenames[:3]
    joined = ", ".join(focus)
    if len(basenames) > 3:
        joined += f" (+{len(basenames) - 3})"
    # Guess verb from status letters
    if re.search(r"^\?\?", status, re.M) and not re.search(r"^[MADRCU]", status, re.M):
        return f"add {joined}"[:72]
    if re.search(r"\.py\b", " ".join(basenames)):
        return f"update {joined}"[:72]
    return f"update {joined}"[:72]


def _make_commit_message(repo: Path) -> str:
    code, status = _run_git(repo, ["status", "--short"])
    code, names = _run_git(repo, ["diff", "--name-only", "HEAD"])
    name_list = [line.strip() for line in (names or "").splitlines() if line.strip()]
    if not name_list:
        name_list = [
            line[3:].strip() if len(line) > 3 else line
            for line in (status or "").splitlines()
            if line.strip()
        ]
    _c, staged = _run_git(repo, ["diff", "--cached", "--stat"])
    _c, unstaged = _run_git(repo, ["diff", "--stat"])
    patch = ""
    if name_list:
        _c, patch = _run_git(repo, ["diff", "HEAD", "--", *name_list[:20]], timeout=40)
    blob = "\n".join(
        [
            "STATUS:\n" + (status or "")[:1500],
            "STAGED STAT:\n" + (staged or "(kosong)"),
            "UNSTAGED STAT:\n" + (unstaged or "(kosong)"),
            "DIFF:\n" + (patch or "")[:4500],
        ]
    )
    try:
        title = _ollama_commit_title(blob)
    except Exception:
        title = ""
    if not title or len(title) < 3:
        title = _heuristic_commit_title(name_list, status or "")
    return title[:72]


def draft_commit_message(path: str = "") -> str:
    repo = _resolve_repo(path)
    if repo is None:
        return "Bukan repo git / project belum ketemu."
    code, status = _run_git(repo, ["status", "--short"])
    if code != 0:
        return "Gagal baca git status."
    if not status.strip():
        return "Working tree bersih — tidak ada yang di-commit."
    title = _make_commit_message(repo)
    remember_project(repo)
    return f"Draft commit message:\n{title}\n\nRepo: {repo}\nPerubahan:\n{status}"


def git_commit(path: str = "", message: str = "", add_all: bool = True) -> str:
    repo = _resolve_repo(path)
    if repo is None:
        return (
            "Bukan repo git. Jalankan `git init` di folder project dulu, "
            "atau buka project yang sudah ada .git."
        )
    code, status = _run_git(repo, ["status", "--short"])
    if code != 0:
        return "Gagal baca git status."
    if not status.strip():
        return "Tidak ada perubahan untuk di-commit."

    if add_all:
        code, out = _run_git(repo, ["add", "-A"], timeout=60)
        if code != 0:
            return f"git add gagal:\n{out}"
        for name in _SENSITIVE_NAMES:
            _run_git(repo, ["reset", "HEAD", "--", name])

    code, staged_names = _run_git(repo, ["diff", "--cached", "--name-only"])
    staged = [line for line in (staged_names or "").splitlines() if line.strip()]
    if not staged:
        return (
            "Tidak ada file di staging (mungkin hanya file sensitif seperti .env). "
            "Tidak commit."
        )

    msg = (message or "").strip()
    if not msg:
        msg = _make_commit_message(repo)
    msg = msg.splitlines()[0].strip().strip('"').strip("'")[:72]
    if len(msg) < 3:
        msg = _heuristic_commit_title(staged, status)

    code, out = _run_git(repo, ["commit", "-m", msg], timeout=60)
    if code != 0:
        return f"git commit gagal:\n{out}"

    code, head = _run_git(repo, ["rev-parse", "--short", "HEAD"])
    remember_project(repo)
    return (
        f"Commit berhasil di {repo.name}\n"
        f"Message: {msg}\n"
        f"Hash: {head or '?'}\n"
        f"Files: {len(staged)}"
    )


def git_push(path: str = "", remote: str = "origin", set_upstream: bool = True) -> str:
    repo = _resolve_repo(path)
    if repo is None:
        return "Bukan repo git / project belum ketemu."
    code, branch = _run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    if code != 0 or not branch or branch == "HEAD":
        return "Branch tidak ketahuan. Buat/checkout branch dulu."

    rem = (remote or "origin").strip() or "origin"
    code, remotes = _run_git(repo, ["remote"])
    if rem not in (remotes or "").splitlines():
        return (
            f"Remote `{rem}` belum ada.\n"
            "Tambah dulu: git remote add origin <url>\n"
            f"Remotes sekarang: {remotes or '(kosong)'}"
        )

    args = ["push"]
    if set_upstream:
        args += ["-u", rem, branch]
    else:
        args += [rem, branch]
    code, out = _run_git(repo, args, timeout=180)
    if code != 0:
        return f"git push gagal:\n{out}"
    remember_project(repo)
    return f"Push berhasil: {rem}/{branch}\n{out or '(ok)'}"


def git_status(path: str = "") -> str:
    repo = _resolve_repo(path)
    if repo is None:
        return "Bukan repo git / project belum ketemu."
    remember_project(repo)
    return f"Repo: {repo}\n{git_snapshot(repo)}"


def git_pull(path: str = "", remote: str = "origin") -> str:
    """Fast-forward only, so a pull never creates merge commits or conflicts."""
    repo = _resolve_repo(path)
    if repo is None:
        return "Bukan repo git / project belum ketemu."
    code, branch = _run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    if code != 0 or not branch or branch == "HEAD":
        return "Branch tidak ketahuan. Checkout branch dulu."
    rem = (remote or "origin").strip() or "origin"
    code, remotes = _run_git(repo, ["remote"])
    if rem not in (remotes or "").splitlines():
        return f"Remote `{rem}` belum ada di {repo.name}. Remotes: {remotes or '(kosong)'}"

    _code, before = _run_git(repo, ["rev-parse", "--short", "HEAD"])
    code, out = _run_git(repo, ["pull", "--ff-only", rem, branch], timeout=180)
    remember_project(repo)
    if code != 0:
        low = out.lower()
        if "would be overwritten" in low or "local changes" in low:
            reason = "Ada perubahan lokal yang bentrok dengan update. Commit atau stash dulu."
        elif "not possible to fast-forward" in low or "diverging" in low or "divergent" in low:
            reason = "Branch lokal dan remote sudah bercabang. Perlu merge/rebase manual."
        elif "could not read" in low or "authentication" in low or "permission denied" in low:
            reason = "Gagal login ke remote. Cek akses git."
        elif "couldn't find remote ref" in low:
            reason = f"Branch `{branch}` belum ada di {rem}."
        else:
            reason = "Pull gagal."
        return f"{reason}\n\n{out[-800:]}"

    _code, after = _run_git(repo, ["rev-parse", "--short", "HEAD"])
    if before == after:
        return f"{repo.name} ({branch}) sudah paling baru. Tidak ada update dari {rem}."
    _code, log = _run_git(repo, ["log", "--pretty=format:%h %s", f"{before}..{after}"])
    _code, stat = _run_git(repo, ["diff", "--shortstat", before, after])
    commits = [line for line in (log or "").splitlines() if line.strip()]
    lines = [
        f"Pull berhasil di {repo.name} ({branch}): {len(commits)} commit baru.",
        (stat or "").strip(),
        "Commit baru:",
        *[f"- {line}" for line in commits[:10]],
    ]
    if len(commits) > 10:
        lines.append(f"- ...dan {len(commits) - 10} lagi")
    return "\n".join(line for line in lines if line)


def git_commit_and_push(
    path: str = "",
    message: str = "",
    remote: str = "origin",
) -> str:
    committed = git_commit(path=path, message=message, add_all=True)
    if not committed.lower().startswith("commit berhasil"):
        return committed
    pushed = git_push(path=path or str(_resolve_repo(path) or ""), remote=remote)
    return committed + "\n\n" + pushed


def resume_coding(hint: str = "", install_deps: bool = True, open_terminal: bool = True) -> str:
    """Clone coding session: buka project → git → deps → terminal."""
    workspace = resolve_project(hint)
    if workspace is None:
        return (
            "Belum ketemu project untuk dilanjutkan.\n"
            "Buka folder sekali lewat `buka vs code di ...` / `buat folder ...`, "
            "atau sebut namanya: `lanjut project namafolder`.\n"
            + list_known_projects(5)
        )
    if not workspace.exists():
        return f"Project hilang dari disk: {workspace}"

    remember_project(workspace)
    lines = [
        f"Melanjutkan session coding: {workspace.name}",
        f"Path: {workspace}",
        open_vscode(str(workspace)),
        git_snapshot(workspace),
    ]
    if install_deps:
        lines.append(ensure_deps(workspace))
    if open_terminal:
        lines.append(open_project_terminal(workspace))

    try:
        fact = f"Bos Rehan lanjut coding di project {workspace.name} ({workspace})"
        item = db.save_memory(fact)
        if not item.get("duplicate"):
            from jin import memory as jin_memory

            jin_memory.index_later("memory", int(item["id"]), fact)
    except Exception:
        pass

    return "\n\n".join(lines)
