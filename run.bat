@echo off
rem Start the launcher (Windows). First run makes .venv and installs pygame-ce.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv || python -m venv .venv
    .venv\Scripts\pip install -q -e . || exit /b 1
)
.venv\Scripts\python -m retro_launcher %*
