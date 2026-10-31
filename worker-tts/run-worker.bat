@echo off
rem Start the TTS worker (Windows). Setup first: powershell -ExecutionPolicy Bypass -File worker-tts\setup-worker.ps1
cd /d "%~dp0"
.venv-ml\Scripts\python.exe main.py
