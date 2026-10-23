from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from jin.config import DB_PATH, ensure_dirs


def _connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                fire_at TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                vector BLOB NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(source_type, source_id)
            );
            """
        )


def start_conversation() -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (created_at) VALUES (?)",
            (now,),
        )
        return int(cur.lastrowid)


def add_message(conversation_id: int, role: str, content: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (conversation_id, role, content, now),
        )
        message_id = int(cur.lastrowid)
    if role == "user":
        try:
            from jin import memory as jin_memory

            jin_memory.index_later("message", message_id, content)
        except Exception:
            pass
    return message_id


def recent_messages(conversation_id: int, limit: int = 24) -> list[dict[str, str]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()
    items = [{"role": row["role"], "content": row["content"]} for row in rows]
    items.reverse()
    return items


def search_messages(query: str = "", limit: int = 300) -> list[dict]:
    """Newest first. Empty query returns the latest messages."""
    sql = "SELECT id, conversation_id, role, content, created_at FROM messages"
    params: list = []
    if query.strip():
        sql += " WHERE content LIKE ?"
        params.append(f"%{query.strip()}%")
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def save_note(content: str, title: str = "") -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    title = title.strip() or content.strip()[:40]
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO notes (title, content, created_at) VALUES (?, ?, ?)",
            (title, content.strip(), now),
        )
        note_id = int(cur.lastrowid)
    blob = f"{title}\n{content.strip()}".strip()
    try:
        from jin import memory as jin_memory

        jin_memory.index_later("note", note_id, blob)
    except Exception:
        pass
    return {"id": note_id, "title": title, "content": content.strip()}


def list_notes(query: str = "", limit: int = 12) -> list[dict]:
    with _connect() as conn:
        if query.strip():
            like = f"%{query.strip()}%"
            rows = conn.execute(
                """
                SELECT id, title, content, created_at
                FROM notes
                WHERE title LIKE ? OR content LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (like, like, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, title, content, created_at
                FROM notes
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def add_reminder(text: str, fire_at: datetime) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    fire_value = fire_at.isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (text, fire_at, done, created_at) VALUES (?, ?, 0, ?)",
            (text.strip(), fire_value, now),
        )
        return {"id": int(cur.lastrowid), "text": text.strip(), "fire_at": fire_value}


def list_reminders(include_done: bool = False, limit: int = 12) -> list[dict]:
    with _connect() as conn:
        if include_done:
            rows = conn.execute(
                """
                SELECT id, text, fire_at, done
                FROM reminders
                ORDER BY fire_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, text, fire_at, done
                FROM reminders
                WHERE done = 0
                ORDER BY fire_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def due_reminders(now: datetime | None = None) -> list[dict]:
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, text, fire_at
            FROM reminders
            WHERE done = 0 AND fire_at <= ?
            ORDER BY fire_at ASC
            """,
            (stamp,),
        ).fetchall()
    return [dict(row) for row in rows]


def complete_reminder(reminder_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,))


def save_memory(fact: str) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    fact = fact.strip()
    with _connect() as conn:
        rows = conn.execute("SELECT id, fact FROM memories ORDER BY id DESC LIMIT 40").fetchall()
        low = fact.lower()
        for row in rows:
            existing = str(row["fact"]).lower()
            if low == existing or low in existing or existing in low:
                return {"id": int(row["id"]), "fact": row["fact"], "duplicate": True}
        cur = conn.execute(
            "INSERT INTO memories (fact, created_at) VALUES (?, ?)",
            (fact, now),
        )
        memory_id = int(cur.lastrowid)
    try:
        from jin import memory as jin_memory

        jin_memory.index_later("memory", memory_id, fact)
    except Exception:
        pass
    return {"id": memory_id, "fact": fact}


def list_memories(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, fact, created_at
            FROM memories
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def memory_prompt(limit: int = 12) -> str:
    items = list(reversed(list_memories(limit)))
    if not items:
        return ""
    lines = [f"- {item['fact']}" for item in items]
    return "Ingatan jangka panjang tentang bos Rehan:\n" + "\n".join(lines)


def upsert_embedding(source_type: str, source_id: int, text: str, vector: bytes) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO embeddings (source_type, source_id, text, vector, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_type, source_id) DO UPDATE SET
                text = excluded.text,
                vector = excluded.vector,
                created_at = excluded.created_at
            """,
            (source_type, source_id, text.strip(), vector, now),
        )


def list_embeddings(limit: int = 5000) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, source_type, source_id, text, vector, created_at
            FROM embeddings
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def embedding_count() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM embeddings").fetchone()
    return int(row["n"] if row else 0)


def iter_index_sources() -> list[dict]:
    """All notes, memories, and user messages worth embedding."""
    items: list[dict] = []
    with _connect() as conn:
        for row in conn.execute("SELECT id, fact, created_at FROM memories ORDER BY id ASC"):
            items.append(
                {
                    "source_type": "memory",
                    "source_id": int(row["id"]),
                    "text": str(row["fact"]),
                    "created_at": row["created_at"],
                }
            )
        for row in conn.execute(
            "SELECT id, title, content, created_at FROM notes ORDER BY id ASC"
        ):
            text = f"{row['title']}\n{row['content']}".strip()
            items.append(
                {
                    "source_type": "note",
                    "source_id": int(row["id"]),
                    "text": text,
                    "created_at": row["created_at"],
                }
            )
        for row in conn.execute(
            """
            SELECT id, content, created_at
            FROM messages
            WHERE role = 'user'
            ORDER BY id ASC
            """
        ):
            items.append(
                {
                    "source_type": "message",
                    "source_id": int(row["id"]),
                    "text": str(row["content"]),
                    "created_at": row["created_at"],
                }
            )
    return items


def get_setting(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
