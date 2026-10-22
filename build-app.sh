#!/bin/sh
# Build a stand-alone app with PyInstaller: dist/Retro Launcher.app on macOS,
# dist/retro-launcher/ on Linux. (Windows: build-app.bat.)
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -q -e .; }
.venv/bin/pip install -q pyinstaller || exit 1
NAME=retro-launcher
[ "$(uname -s)" = Darwin ] && NAME="Retro Launcher"
ICON=retro_launcher/assets/icon.png
[ "$(uname -s)" = Darwin ] && ICON=retro_launcher/assets/icon.icns
.venv/bin/pyinstaller --noconfirm --clean --windowed --name "$NAME" --icon "$ICON" \
    --osx-bundle-identifier com.geekychris.retrolauncher \
    --add-data "retro_launcher/assets:retro_launcher/assets" launch.py
