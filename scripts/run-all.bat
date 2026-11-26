@echo off
cd /d "%~dp0.."
start "PLI Backend" cmd /k "%~dp0run-backend.bat"
start "PLI Frontend" cmd /k "%~dp0run-frontend.bat"
echo Backend dan frontend dibuka di jendela terpisah.
echo Tutup kedua jendela tersebut untuk menghentikan aplikasi.
