import os
import sys

# pythonw.exe and the windowed .exe have no console; libraries that write to it would crash.
if sys.stdout is None or sys.stderr is None:
    _devnull = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = sys.stdout or _devnull
    sys.stderr = sys.stderr or _devnull
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# winrt ships an old msvcp140.dll (14.29); if it loads first, ctranslate2 (Whisper)
# crashes with an access violation. Loading ctranslate2 first pins the system copy.
import ctranslate2  # noqa: E402, F401

from jin import logs  # noqa: E402

logs.setup()

from jin.app import JinApp  # noqa: E402


if __name__ == "__main__":
    app = JinApp(start_minimized="--minimized" in sys.argv)
    app.mainloop()
