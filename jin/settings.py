from __future__ import annotations

import subprocess
import sys
import winreg
from pathlib import Path

from jin.config import ENV_PATH, FROZEN, ROOT

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "JinAsghard"


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env(updates: dict[str, str]) -> None:
    """Update keys in .env in place, keeping comments and unknown keys."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    pending = {key: str(value).replace("\n", " ").strip() for key, value in updates.items()}
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in pending:
                out.append(f"{key}={pending.pop(key)}")
                continue
        out.append(line)
    out.extend(f"{key}={value}" for key, value in pending.items())
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def launch_command(minimized: bool = False) -> list[str]:
    if FROZEN:
        cmd = [sys.executable]
    else:
        python = Path(sys.executable)
        windowless = python.with_name("pythonw.exe")
        cmd = [str(windowless if windowless.exists() else python), str(ROOT / "main.py")]
    if minimized:
        cmd.append("--minimized")
    return cmd


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _RUN_NAME)
        return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            command = subprocess.list2cmdline(launch_command(minimized=True))
            winreg.SetValueEx(key, _RUN_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, _RUN_NAME)
            except FileNotFoundError:
                pass


def restart() -> None:
    subprocess.Popen(launch_command(), close_fds=True, cwd=str(ROOT))
