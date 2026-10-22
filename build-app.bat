@echo off
rem Build dist\retro-launcher\retro-launcher.exe with PyInstaller.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe ( py -3 -m venv .venv & .venv\Scripts\pip install -q -e . )
.venv\Scripts\pip install -q pyinstaller || exit /b 1
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name retro-launcher --icon retro_launcher\assets\icon.ico ^
    --add-data "retro_launcher/assets;retro_launcher/assets" launch.py
