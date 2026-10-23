from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jin import db
from jin.config import OWNER_CALL

EXPORT_DIR = Path.home() / "Documents" / "Jin"


def local_time(stamp: str) -> str:
    """Messages are stored in UTC, notes in local time; show both as local."""
    try:
        value = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return stamp or ""
    if value.tzinfo is not None:
        value = value.astimezone()
    return value.strftime("%d/%m/%Y %H:%M")


def notes_markdown(query: str = "") -> str:
    notes = db.list_notes(query, limit=100_000)
    lines = ["# Catatan Jin Asghard", ""]
    for note in reversed(notes):
        lines += [f"## {note['title']}", f"*{local_time(note['created_at'])}*", "", note["content"], ""]
    if not notes:
        lines.append("_Belum ada catatan._")
    return "\n".join(lines)


def chats_markdown(query: str = "") -> str:
    messages = list(reversed(db.search_messages(query, limit=100_000)))
    title = f"# Riwayat obrolan Jin Asghard{f' — {query}' if query else ''}"
    lines = [title, ""]
    current = None
    for message in messages:
        if message["conversation_id"] != current:
            current = message["conversation_id"]
            lines += ["", f"## Sesi {current} — {local_time(message['created_at'])}", ""]
        who = OWNER_CALL if message["role"] == "user" else "Jin"
        lines += [f"**{who}** ({local_time(message['created_at'])[-5:]}): {message['content']}", ""]
    if not messages:
        lines.append("_Tidak ada obrolan yang cocok._")
    return "\n".join(lines)


def _write(name: str, body: str, target: Path | None) -> Path:
    path = target or EXPORT_DIR / f"{name}-{datetime.now().strftime('%Y%m%d-%H%M')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def export_notes(target: Path | None = None) -> str:
    path = _write("jin-catatan", notes_markdown(), target)
    return f"Catatan diekspor ke {path}"


def export_chats(query: str = "", target: Path | None = None) -> str:
    path = _write("jin-obrolan", chats_markdown(query), target)
    return f"Riwayat obrolan diekspor ke {path}"
