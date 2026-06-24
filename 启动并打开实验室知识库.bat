@echo off
setlocal
cd /d "%~dp0"
echo Starting Lab RAG server...
start "Lab RAG Server" /min python server.py
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8765/index.html"
endlocal
