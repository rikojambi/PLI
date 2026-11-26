@echo off
cd /d "%~dp0..\frontend"
echo Frontend PLI: http://localhost:5173
call npm run dev
