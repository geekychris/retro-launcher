# SPDX-License-Identifier: MIT
"""Render the launcher's screens for the docs, off-screen (SDL's dummy video
driver), into docs/images/. Reads your config but never saves it, and
launches nothing; statuses (RUNNING, MISSING, ...) are live.

    .venv/bin/python tools/docshots.py [--size 1600x900]
"""
import argparse
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from retro_launcher import app as appmod  # noqa: E402
from retro_launcher import config as cfgmod  # noqa: E402
from retro_launcher.procs import UrlWatcher, find_processes  # noqa: E402

cfgmod.Config.save = lambda self: None      # screenshots must not change the config

OUT = os.path.join(ROOT, "docs", "images")


def shot(cfg_path, size, name, setup, frames=150):
    """One screenshot: a fresh App, `setup(app)`, then `frames` frames."""
    a = appmod.App(cfg_path=cfg_path, windowed=True)
    a.display = pygame.display.set_mode(size)
    a.make_canvas()

    def prepare(app):
        app.art_time = 1e12          # keep the first screenshot on each card
        # running emulators, now rather than at the watcher's first poll
        app.watcher.found = {k: find_processes(p) for k, p in app.watcher.patterns.items()}
        setup(app)

    path = os.path.join(OUT, name + ".png")
    try:
        a.run(snapshot=(path, frames, prepare))
    except SystemExit:
        pass
    a.watcher.stop()
    a.health.stop()
    print("wrote", os.path.relpath(path, ROOT))


def select(key):
    def setup(app):
        app.sel = app.visible_keys().index(key)
    return setup


def engineer(key):
    """Power Engineer mode on `key`, with the workbenches' live up/down states."""
    def setup(app):
        app.engineer = True
        app.refresh_watcher()
        app.health.up = {u: UrlWatcher.answers(u) for u in app.health.urls}
        app.sel = app.visible_keys().index(key)
    return setup


def settings(tab, row=0, action=None):
    def setup(app):
        app.mode = "settings"
        s = app.settings
        s.tab = [k for k, _ in s.tabs()].index(tab)
        s.row = row
        if action:
            s.action(action, tab)
    return setup


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--size", default="1600x900")
    ap.add_argument("--config", default=cfgmod.default_config_path(),
                    help="config to show (default: yours; it isn't changed)")
    a = ap.parse_args()
    size = tuple(int(v) for v in a.size.lower().split("x"))
    os.makedirs(OUT, exist_ok=True)

    cfg_path = a.config
    keys = ["amiga68k", "amigaos4", "atari", "3do"]
    for k in keys:
        shot(cfg_path, size, "menu-" + k, select(k))

    def plain(app):
        app.sel = app.visible_keys().index("atari")
        app.toggle_boot("atari")     # in memory only: saving is off
    shot(cfg_path, size, "menu-plain-boot", plain)

    def stop_confirm(app):
        app.sel = app.visible_keys().index("amiga68k")
        app.stop("amiga68k")         # first press only asks for a second one
    shot(cfg_path, size, "menu-stop-confirm", stop_confirm)

    def log(app):
        app.sel = app.visible_keys().index("3do")
        ln = app.launches["3do"]
        app.log_view = ("Log: " + ln.log_path, ln.tail(40) or ["(no log yet)"])
    shot(cfg_path, size, "menu-log", log)

    for k in keys:
        shot(cfg_path, size, "engineer-" + k, engineer(k))

    shot(cfg_path, size, "settings-general", settings("general", 2))
    for k in keys:
        shot(cfg_path, size, "settings-" + k, settings(k, 3))
    shot(cfg_path, size, "settings-preview-amigaos4",
         settings("amigaos4", action="Preview commands"))
    shot(cfg_path, size, "settings-preview-atari",
         settings("atari", action="Preview commands"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
