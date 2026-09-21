from __future__ import annotations

import re
import threading
from datetime import datetime
from queue import Empty, Queue

from jin import db
from jin import embed as emb

_LABEL = {
    "memory": "fakta",
    "note": "catatan",
    "message": "obrolan",
}

_SKIP_MESSAGE = re.compile(
    r"^(?:"
    r"radar(?:\s+pagi)?|fokus|pulang|briefing|"
    r"volume\b|kunci\s+(?:laptop|pc)|screenshot|baca\s+layar|"
    r"(?:tolong\s+)?(?:buka|install|pip|npm)\b|"
    r"mode\s+\w+|wujud\s+\w+|catat\s*:|ingat\s*:"
    r")",
    re.IGNORECASE,
)

_STOP = {
    "yang",
    "yang",
    "apa",
    "ini",
    "itu",
    "dan",
    "atau",
    "untuk",
    "dengan",
    "dari",
    "pada",
    "kah",
    "nya",
    "aku",
    "saya",
    "kamu",
    "bos",
    "jin",
    "soal",
    "tentang",
    "mengenai",
}


def _keywords(text: str) -> set[str]:
    raw = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return {tok for tok in raw.split() if len(tok) >= 3 and tok not in _STOP}

_QUEUE: Queue[tuple[str, int, str]] = Queue()
_WORKER_STARTED = False
_LOCK = threading.Lock()


def _worth_indexing(source_type: str, text: str) -> bool:
    blob = (text or "").strip()
    if len(blob) < 8:
        return False
    if source_type == "message" and _SKIP_MESSAGE.match(blob):
        return False
    if source_type == "message" and len(blob) < 12:
        return False
    return True


def index_now(source_type: str, source_id: int, text: str) -> bool:
    if not _worth_indexing(source_type, text):
        return False
    vector = emb.embed(text)
    db.upsert_embedding(source_type, source_id, text.strip()[:2000], emb.pack(vector))
    return True


def _worker() -> None:
    while True:
        try:
            source_type, source_id, text = _QUEUE.get(timeout=1.0)
        except Empty:
            continue
        try:
            index_now(source_type, source_id, text)
        except Exception:
            pass
        finally:
            _QUEUE.task_done()


def _ensure_worker() -> None:
    global _WORKER_STARTED
    with _LOCK:
        if _WORKER_STARTED:
            return
        thread = threading.Thread(target=_worker, daemon=True, name="jin-memory")
        thread.start()
        _WORKER_STARTED = True


def index_later(source_type: str, source_id: int, text: str) -> None:
    if not _worth_indexing(source_type, text):
        return
    _ensure_worker()
    _QUEUE.put((source_type, int(source_id), text))


def backfill(limit: int = 800) -> int:
    """Index existing notes/memories/messages that belum ada di embeddings."""
    existing = {(row["source_type"], int(row["source_id"])) for row in db.list_embeddings()}
    added = 0
    for item in db.iter_index_sources():
        key = (item["source_type"], int(item["source_id"]))
        if key in existing:
            continue
        if index_now(item["source_type"], int(item["source_id"]), item["text"]):
            added += 1
        if added >= limit:
            break
    return added


def start_backfill_async() -> None:
    def run() -> None:
        try:
            backfill()
        except Exception:
            pass

    threading.Thread(target=run, daemon=True, name="jin-memory-backfill").start()


def _recency_boost(created_at: str) -> float:
    if not created_at:
        return 0.0
    try:
        stamp = created_at.replace("Z", "+00:00")
        when = datetime.fromisoformat(stamp)
        if when.tzinfo is not None:
            when = when.replace(tzinfo=None)
        age_hours = max(0.0, (datetime.now() - when).total_seconds() / 3600.0)
    except ValueError:
        return 0.0
    # 1.0 for now → ~0 after ~14 days
    return max(0.0, 1.0 - (age_hours / (24.0 * 14.0)))


def recall(query: str, limit: int = 6, min_score: float | None = None) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []
    rows = db.list_embeddings()
    if not rows:
        return []
    qvec = emb.embed(q)
    # Ollama vectors cluster Indonesian chat tightly — need a higher floor.
    if min_score is None:
        min_score = 0.50 if emb.embed_ready() else 0.22
    scored: list[dict] = []
    for row in rows:
        try:
            vec = emb.unpack(row["vector"])
        except Exception:
            continue
        sim = emb.cosine(qvec, vec)
        kind = row["source_type"]
        type_boost = {"memory": 0.05, "note": 0.03, "message": 0.0}.get(kind, 0.0)
        q_keys = _keywords(q)
        t_keys = _keywords(str(row["text"]))
        overlap = (len(q_keys & t_keys) / max(1, len(q_keys))) if q_keys else 0.0
        score = (
            0.72 * sim
            + 0.12 * _recency_boost(str(row.get("created_at") or ""))
            + 0.12 * overlap
            + type_boost
        )
        if kind == "message" and overlap < 0.15:
            score -= 0.10
        if emb.embed_ready():
            floor = {"memory": min_score - 0.04, "note": min_score - 0.02, "message": min_score + 0.06}.get(
                kind, min_score
            )
        else:
            floor = min_score if kind != "message" else max(min_score, 0.28)
        if score < floor and sim < floor:
            continue
        scored.append(
            {
                "source_type": kind,
                "source_id": int(row["source_id"]),
                "text": str(row["text"]).strip(),
                "created_at": row.get("created_at") or "",
                "score": round(float(score), 4),
                "similarity": round(float(sim), 4),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)

    # Keep only near the best match — cuts Indonesian-chat embedding noise.
    if scored:
        best = scored[0]["score"]
        gap = 0.06 if emb.embed_ready() else 0.12
        scored = [item for item in scored if item["score"] >= best - gap]

    # Deduplicate near-identical text.
    seen: set[str] = set()
    unique: list[dict] = []
    for item in scored:
        key = re.sub(r"\s+", " ", item["text"].lower())[:160]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def format_hits(hits: list[dict]) -> str:
    if not hits:
        return "Tidak ada ingatan relevan."
    lines = []
    for item in hits:
        label = _LABEL.get(item["source_type"], item["source_type"])
        when = str(item.get("created_at") or "")[:16].replace("T", " ")
        snippet = item["text"].replace("\n", " ").strip()
        if len(snippet) > 220:
            snippet = snippet[:217] + "..."
        stamp = f" ({when})" if when else ""
        lines.append(f"- [{label}]{stamp} {snippet}")
    return "\n".join(lines)


def recall_prompt(query: str, limit: int = 6) -> str:
    """System context: sticky recent facts + semantic hits for this question."""
    parts: list[str] = []
    sticky = list(reversed(db.list_memories(limit=5)))
    if sticky:
        parts.append(
            "Fakta inti tentang bos Rehan:\n"
            + "\n".join(f"- {item['fact']}" for item in sticky)
        )
    hits = recall(query, limit=limit) if query.strip() else []
    # Drop hits that already appear in sticky facts.
    sticky_text = {item["fact"].strip().lower() for item in sticky}
    filtered = [h for h in hits if h["text"].strip().lower() not in sticky_text]
    if filtered:
        backend = "embedding Ollama" if emb.embed_ready() else "pencarian lokal"
        parts.append(
            f"Ingatan relevan untuk pertanyaan ini ({backend}):\n" + format_hits(filtered)
        )
    elif not sticky:
        return ""
    return "\n\n".join(parts)


def remember_query(query: str) -> str:
    hits = recall(query, limit=8, min_score=0.42 if emb.embed_ready() else 0.12)
    if not hits:
        return f"Belum ada ingatan yang nyambung ke '{query}'."
    return f"Yang kuingat soal '{query}':\n{format_hits(hits)}"
