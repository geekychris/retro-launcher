#!/bin/sh
# Start the launcher (macOS / Linux). First run makes .venv and installs pygame-ce.
# Arguments pass through, e.g. ./run.sh --windowed   ./run.sh --launch 3do
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv && .venv/bin/pip install -q -e . || exit 1
fi
exec .venv/bin/python -m retro_launcher "$@"
