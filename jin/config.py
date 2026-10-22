from pathlib import Path
import os
import shutil
import sys

from dotenv import load_dotenv

FROZEN = getattr(sys, "frozen", False)
# Bundled read-only files (assets) vs. writable user files (.env, data).
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
APP_HOME = Path(sys.executable).resolve().parent / "userdata" if FROZEN else ROOT
APP_HOME.mkdir(parents=True, exist_ok=True)
ENV_PATH = APP_HOME / ".env"
if not ENV_PATH.exists() and (ROOT / ".env.example").exists():
    shutil.copyfile(ROOT / ".env.example", ENV_PATH)
load_dotenv(ENV_PATH)

DATA_DIR = APP_HOME / "data"
AUDIO_DIR = DATA_DIR / "audio"
ASSETS_DIR = ROOT / "assets"
JIN_IMAGE = ASSETS_DIR / "jin.png"
DB_PATH = DATA_DIR / "jin.db"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b").strip() or "qwen2.5:7b"
VISION_MODEL = os.getenv("JIN_VISION_MODEL", "qwen2.5vl:3b").strip() or "qwen2.5vl:3b"
EMBED_MODEL = os.getenv("JIN_EMBED_MODEL", "nomic-embed-text").strip() or "nomic-embed-text"
EMBED_DIM = int(os.getenv("JIN_EMBED_DIM", "384") or "384")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny").strip() or "tiny"
OWNER_NAME = os.getenv("OWNER_NAME", "Rehan").strip() or "Rehan"
OWNER_CALL = os.getenv("OWNER_CALL", "bos Rehan").strip() or "bos Rehan"
JIN_VOICE = os.getenv("JIN_VOICE", "id-ID-ArdiNeural").strip() or "id-ID-ArdiNeural"
JIN_RATE = os.getenv("JIN_RATE", "-22%").strip() or "-22%"
JIN_PITCH = os.getenv("JIN_PITCH", "-50Hz").strip() or "-50Hz"
JIN_SPEAK = os.getenv("JIN_SPEAK", "1").strip() != "0"
JIN_WAKE = os.getenv("JIN_WAKE", "1").strip() != "0"
JIN_CLIPBOARD = os.getenv("JIN_CLIPBOARD", "1").strip() != "0"
JIN_TRAY = os.getenv("JIN_TRAY", "1").strip() != "0"
WAKE_WORDS = [
    part.strip().lower()
    for part in os.getenv("JIN_WAKE_WORDS", "jin,asghard").split(",")
    if part.strip()
] or ["jin", "asghard"]
# Legacy; wake word replaces keyboard summon.
HOTKEY = os.getenv("JIN_HOTKEY", "").strip()
PROJECTS_DIR = Path(
    os.getenv("JIN_PROJECTS_DIR", "").strip() or str(Path.home() / "Documents" / "JinProjects")
).expanduser()

MOOD_IMAGES = {
    "idle": ASSETS_DIR / "jin-idle.png",
    "listen": ASSETS_DIR / "jin-listen.png",
    "think": ASSETS_DIR / "jin-think.png",
    "speak": ASSETS_DIR / "jin-speak.png",
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
