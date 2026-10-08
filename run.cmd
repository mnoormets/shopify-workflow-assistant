@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m uvicorn backend.api:app --host 127.0.0.1 --port 8770
