@echo off
cd /d "%~dp0"

where ollama >nul 2>nul
if errorlevel 1 (
  echo Jin tidak butuh API key. Yang diperlukan: Ollama di laptop.
  echo.
  echo Install dulu: https://ollama.com/download
  echo Setelah terpasang, jalankan start.bat lagi.
  start https://ollama.com/download
  pause
  exit /b 1
)

echo Mengunduh otak Jin qwen2.5:7b kalau belum ada...
ollama pull qwen2.5:7b
if errorlevel 1 (
  echo Gagal menarik model Ollama. Cek internet, lalu coba lagi.
  pause
  exit /b 1
)

echo Mengunduh memori semantik nomic-embed-text kalau belum ada...
ollama pull nomic-embed-text
if errorlevel 1 (
  echo Peringatan: embed model gagal diunduh. Jin tetap jalan dengan pencarian lokal.
)

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist ".env" (
  copy .env.example .env
)

python main.py
