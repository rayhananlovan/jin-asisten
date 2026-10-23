from __future__ import annotations

import asyncio
import json
import os
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from jin.config import DATA_DIR, EMBED_MODEL, JIN_VOICE, OLLAMA_MODEL, OLLAMA_URL, VISION_MODEL

OK, INFO, WARN, FAIL = "ok", "info", "warn", "fail"
MIN_FREE_GB = 2.0


@dataclass
class Check:
    status: str
    name: str
    detail: str


def _ollama() -> list[Check]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return [Check(FAIL, "Ollama", "tidak jalan. Buka aplikasi Ollama dulu.")]
    names = {str(item.get("name") or "") for item in data.get("models") or []}

    def has(model: str) -> bool:
        return (model if ":" in model else f"{model}:latest") in names

    checks = [Check(OK, "Ollama", "jalan")]
    for label, model, missing in (
        ("Otak", OLLAMA_MODEL, FAIL),
        ("Memori", EMBED_MODEL, WARN),
        ("Vision", VISION_MODEL, INFO),
    ):
        if has(model):
            checks.append(Check(OK, label, model))
        else:
            checks.append(Check(missing, label, f"{model} belum terpasang. Jalankan: ollama pull {model}"))
    return checks


def _mic() -> Check:
    try:
        import sounddevice

        device = sounddevice.query_devices(kind="input")
        return Check(OK, "Mic", str(device["name"]))
    except Exception:
        return Check(FAIL, "Mic", "tidak ada mic yang bisa dipakai.")


def _ocr() -> Check:
    try:
        from winrt.windows.media.ocr import OcrEngine

        languages = [lang.language_tag for lang in OcrEngine.available_recognizer_languages]
    except Exception:
        return Check(WARN, "OCR", "Windows OCR tidak tersedia. `baca layar` tidak bisa membaca tulisan.")
    if not languages:
        return Check(WARN, "OCR", "belum ada bahasa OCR di Windows.")
    if not any(tag.lower().startswith("id") for tag in languages):
        return Check(
            INFO,
            "OCR",
            f"{', '.join(languages)} saja. Tambah bahasa Indonesia di Settings Windows > Language agar teks Indonesia lebih akurat.",
        )
    return Check(OK, "OCR", ", ".join(languages))


def _voice() -> Check:
    async def first_chunk() -> bool:
        import edge_tts

        async for chunk in edge_tts.Communicate("ok", JIN_VOICE).stream():
            if chunk.get("type") == "audio":
                return True
        return False

    try:
        if asyncio.run(asyncio.wait_for(first_chunk(), timeout=8)):
            return Check(OK, "Suara", JIN_VOICE)
    except Exception:
        pass
    return Check(WARN, "Suara", "suara online gagal. Jin pakai suara cadangan Windows dulu.")


def _editor() -> Check:
    from jin.codehelp import find_editor

    editor = find_editor()
    if editor:
        return Check(OK, "Editor", editor[1])
    return Check(WARN, "Editor", "VS Code / Cursor tidak ketemu.")


def _disks() -> list[Check]:
    models = os.getenv("OLLAMA_MODELS", "").strip() or str(Path.home() / ".ollama" / "models")
    places = {"Data Jin": DATA_DIR, "Model Ollama": Path(models), "Sistem": Path(os.getenv("SystemDrive", "C:") + "\\")}
    checks: list[Check] = []
    seen: set[str] = set()
    for label, path in places.items():
        drive = (Path(path).drive or str(path)[:2]).upper()
        if drive in seen:
            continue
        seen.add(drive)
        try:
            free_gb = shutil.disk_usage(f"{drive}\\").free / 1024**3
        except OSError:
            continue
        status = OK if free_gb >= MIN_FREE_GB else WARN
        detail = f"{drive} sisa {free_gb:.1f} GB"
        if status == WARN:
            detail += " — hampir penuh"
        checks.append(Check(status, f"Disk {label}", detail))
    return checks


def run_checks() -> list[Check]:
    checks = _ollama()
    checks.append(_mic())
    checks.append(_ocr())
    checks.append(_voice())
    checks.append(_editor())
    checks.extend(_disks())
    return checks


def problems(checks: list[Check]) -> list[Check]:
    return [check for check in checks if check.status in {WARN, FAIL}]


def format_report(checks: list[Check]) -> str:
    marks = {OK: "✓", INFO: "i", WARN: "!", FAIL: "✗"}
    lines = [f"{marks[check.status]} {check.name}: {check.detail}" for check in checks]
    bad = problems(checks)
    head = "Semua sistem siap." if not bad else f"{len(bad)} hal perlu dicek."
    return head + "\n" + "\n".join(lines)


def check_system() -> str:
    return format_report(run_checks())
