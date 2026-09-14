@echo off
title LostFound Backend - port 8000
cd /d C:\Users\33834\Desktop\lost-found-v3\backend
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
echo.
echo Backend exited. Press any key to close.
pause >nul
