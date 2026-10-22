# PyInstaller spec — build with build.bat
from PyInstaller.utils.hooks import collect_all

datas = [("assets", "assets"), (".env.example", ".")]
binaries = []
hiddenimports = ["pystray._win32", "pynput.keyboard._win32", "pynput.mouse._win32"]

for package in (
    "customtkinter",
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "av",
    "tokenizers",
    "winrt",
    "winocr",
    "_sounddevice_data",
    "_soundfile_data",
    "edge_tts",
    "ddgs",
    "docx",
):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception:
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JinAsghard",
    icon="build/jin.ico",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="JinAsghard", upx=False)
