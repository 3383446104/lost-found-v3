@echo off
title LostFound Frontend - port 5173
cd /d C:\Users\33834\Desktop\lost-found-v3\frontend
C:\Users\33834\.workbuddy\binaries\node\versions\22.22.2-3\node.exe node_modules\vite\bin\vite.js > C:\Users\33834\Desktop\lost-found-v3\logs\vite_bat.log 2>&1
echo.
echo Frontend exited (see log). Press any key to close.
pause >nul
