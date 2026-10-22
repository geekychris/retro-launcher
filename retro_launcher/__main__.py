# SPDX-License-Identifier: MIT
"""python -m retro_launcher [--windowed] [--config FILE] [--launch KEY] [--print KEY]"""
import argparse
import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--hooks"]:                 # the frozen app's {helper}
        from .hooks import main as hooks_main
        return hooks_main(argv[1:])
    ap = argparse.ArgumentParser(prog="retro_launcher",
                                 description="Full-screen launcher for the Amiga, AmigaOS 4, "
                                             "Atari ST and 3DO emulators.")
    ap.add_argument("--config", help="settings file (default: the per-user config.toml)")
    ap.add_argument("--windowed", action="store_true", help="start in a window this time")
    ap.add_argument("--launch", metavar="KEY", help="boot this machine straight away "
                    "(amiga68k, amigaos4, atari, 3do)")
    ap.add_argument("--print", metavar="KEY", dest="show",
                    help="print the commands a launch would run, and exit")
    ap.add_argument("--plain", action="store_true", help="with --print: the non-selector boot")
    a = ap.parse_args(argv)
    if a.show:
        from .config import Config
        cfg = Config(a.config)
        prep, argv_, cwd, _ = cfg.plan(a.show, False if a.plain else None)
        for p in prep:
            print("prepare:", " ".join(p))
        print("run:", " ".join(argv_))
        if cwd:
            print("cwd:", cwd)
        print("config:", cfg.path)
        return 0
    from .app import App
    App(a.config, windowed=a.windowed, autostart=a.launch).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
