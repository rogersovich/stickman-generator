@echo off
title Stickman Generator - Backup Cloud R2 to Google Drive
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup.ps1" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [INFO] Script selesai dengan kode status: %ERRORLEVEL%
)

echo.
echo Tekan sembarang tombol untuk menutup jendela ini...
pause >nul
