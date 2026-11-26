@echo off
cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
cd backend
echo Backend PLI: http://127.0.0.1:8000  (dokumentasi: /docs)
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
