@echo off
title LostFound Frontend - port 5173
cd /d C:\Users\33834\Desktop\lost-found-v3\frontend
echo 正在启动前端，浏览器访问 http://localhost:5173
echo （本窗口保持打开；关闭本窗口即停止前端服务）
echo.
C:\Users\33834\.workbuddy\binaries\node\versions\22.22.2-3\node.exe node_modules\vite\bin\vite.js
echo.
echo Frontend exited. Press any key to close.
pause >nul
