@echo off
setlocal
cd /d "%~dp0.."
echo === PLI - Instalasi lokal untuk Windows ===

where python >nul 2>nul
if errorlevel 1 (
  echo Python belum terpasang. Unduh Python 3.11+ dari https://www.python.org/downloads/
  echo Saat instalasi, centang "Add Python to PATH".
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js belum terpasang. Unduh Node.js 20+ dari https://nodejs.org/
  exit /b 1
)

if not exist .venv (
  echo Membuat virtual environment Python...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo Menginstal paket Python...
python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist .env (
  echo Membuat file .env dari contoh...
  copy /Y .env.example .env >nul
  echo PENTING: ubah PLI_SECRET_KEY di file .env sebelum dipakai bersama siswa.
)

echo Menginstal paket frontend...
cd /d "%~dp0..\frontend"
call npm install

echo Membuat database, migrasi, dan akun demo...
cd /d "%~dp0..\backend"
python -m alembic upgrade head
python -m app.db.init_db

echo === Selesai ===
echo Buka file data\demo_credentials.txt untuk melihat akun demo.
echo Jalankan scripts\run-all.bat untuk menyalakan aplikasi.
endlocal
