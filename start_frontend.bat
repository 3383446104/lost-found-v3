@echo off
title LostFound Frontend - port 5173
cd /d "C:\Users\33834\Desktop\lost-found-v3\frontend"
echo ==========================================
echo  Frontend starting:  http://localhost:5173
echo  Keep this window open - closing it stops
echo  the frontend server.
echo ==========================================
echo.
"C:\Users\33834\.workbuddy\binaries\node\versions\22.22.2-3\node.exe" node_modules\vite\bin\vite.js
echo.
echo Frontend exited. Press any key to close.
pause >nul
