@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Jalankan start.bat sekali dulu untuk membuat .venv.
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat
pip install -q -r requirements.txt pyinstaller

if not exist build mkdir build
python -c "from PIL import Image; Image.open('assets/jin.png').save('build/jin.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

tasklist /FI "IMAGENAME eq JinAsghard.exe" | find /I "JinAsghard.exe" >nul
if not errorlevel 1 (
  echo Menutup Jin yang sedang jalan supaya file exe bisa diganti ...
  taskkill /IM JinAsghard.exe /F >nul
  timeout /t 2 /nobreak >nul
)

echo Membangun dist\JinAsghard\JinAsghard.exe ...
python -m PyInstaller jin.spec --noconfirm --clean
if errorlevel 1 (
  echo Build PyInstaller gagal.
  pause
  exit /b 1
)

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
  echo Membuat installer ...
  "%ISCC%" installer.iss
  if errorlevel 1 (
    echo Installer gagal dibuat.
    pause
    exit /b 1
  )
  echo Selesai: dist\JinAsghard-Setup-1.0.0.exe
) else (
  echo Inno Setup 6 belum terpasang, jadi installer dilewati.
  echo Aplikasi siap dipakai di: dist\JinAsghard\JinAsghard.exe
  echo Untuk installer: pasang Inno Setup dari https://jrsoftware.org/isdl.php lalu jalankan build.bat lagi.
)
pause
