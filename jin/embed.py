from __future__ import annotations

import hashlib
import json
import struct
import urllib.error
import urllib.request

import numpy as np

from jin.config import EMBED_DIM, EMBED_MODEL, OLLAMA_URL

_EMBED_OK: bool | None = None


def _tokenize(text: str) -> list[str]:
    raw = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return [tok for tok in raw.split() if len(tok) >= 2]


def lexical_embed(text: str, dim: int = EMBED_DIM) -> np.ndarray:
    """Hashing trick — works offline if Ollama embed model belum ada."""
    vec = np.zeros(dim, dtype=np.float32)
    tokens = _tokenize(text)
    if not tokens:
        return vec
    blob = " ".join(tokens)
    grams = tokens + [blob[i : i + 3] for i in range(max(0, len(blob) - 2))]
    for gram in grams:
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = float(np.linalg.norm(vec))
    if norm > 1e-8:
        vec /= norm
    return vec


def _ollama_embed(text: str) -> np.ndarray | None:
    global _EMBED_OK
    prompt = text.strip()
    if not prompt:
        return None
    payloads = [
        ("/api/embed", {"model": EMBED_MODEL, "input": prompt}),
        ("/api/embeddings", {"model": EMBED_MODEL, "prompt": prompt}),
    ]
    for path, body in payloads:
        request = urllib.request.Request(
            f"{OLLAMA_URL}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        vector = data.get("embedding")
        if vector is None and isinstance(data.get("embeddings"), list) and data["embeddings"]:
            vector = data["embeddings"][0]
        if not isinstance(vector, list) or not vector:
            continue
        arr = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(arr))
        if norm > 1e-8:
            arr = arr / norm
        _EMBED_OK = True
        return arr
    _EMBED_OK = False
    return None


def embed(text: str) -> np.ndarray:
    vector = _ollama_embed(text)
    if vector is not None:
        return vector
    return lexical_embed(text)


def embed_ready() -> bool:
    return bool(_EMBED_OK)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        # Different backends (ollama vs lexical) — compare via lexical of both sides impossible;
        # pad/truncate to shared min length as last resort.
        n = min(a.size, b.size)
        if n == 0:
            return 0.0
        a = a[:n]
        b = b[:n]
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na < 1e-8 or nb < 1e-8:
            return 0.0
        a = a / na
        b = b / nb
    return float(np.dot(a, b))


def pack(vector: np.ndarray) -> bytes:
    arr = np.asarray(vector, dtype=np.float32).ravel()
    return struct.pack(f"<I{arr.size}f", arr.size, *arr.tolist())


def unpack(blob: bytes) -> np.ndarray:
    if not blob or len(blob) < 4:
        return np.zeros(EMBED_DIM, dtype=np.float32)
    (size,) = struct.unpack_from("<I", blob, 0)
    values = struct.unpack_from(f"<{size}f", blob, 4)
    return np.asarray(values, dtype=np.float32)
