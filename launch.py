# SPDX-License-Identifier: MIT
"""Entry script for PyInstaller (and `python launch.py`)."""
import sys

from retro_launcher.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
