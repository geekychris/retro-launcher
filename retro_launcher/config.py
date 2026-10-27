# SPDX-License-Identifier: MIT
"""Settings: the defaults, the TOML file that overrides them, and how a
platform's command templates turn into argument lists.

Templates are split into words first (shell rules, so quote a word with
spaces) and each word is then expanded, so a path with spaces in a
[platforms.X.paths] entry stays one argument. In a word:

  {name}        a path from the platform's [paths] table, or one of
                {home} {python} {config_dir} (paths can use each other)
  {helper}      as a whole word: python -m retro_launcher.hooks
  ?fullscreen:  word prefix: keep the word only when the emulator is set to
                run fullscreen (?windowed: for the opposite)

Each platform also has a [workbench] table for Power Engineer mode: the
developer tools that go with the machine (its devbench web UI, MCP endpoint,
debugger). `url` is checked to tell whether the workbench is up, `start` is
the command that brings it up (empty: launching the machine does), and each
`links` entry is "Label|kind|target", kind being open (a browser), copy (to
the clipboard) or run (a command, through your login shell).
"""
import copy
import os
import shutil
import sys

from . import tomlio
from .procs import split

APP = "retro-launcher"
MAC = sys.platform == "darwin"
WINDOWS = sys.platform.startswith("win")
HOME = os.path.expanduser("~")
FROZEN = getattr(sys, "frozen", False)      # a PyInstaller build


def python_exe():
    """A Python for scripts the launch steps run ({python})."""
    if not FROZEN:
        return sys.executable
    return shutil.which("python3") or shutil.which("python") or "python3"


def helper_argv():
    """{helper}: this program's hooks commands."""
    if FROZEN:
        return [sys.executable, "--hooks"]
    return [sys.executable, "-m", "retro_launcher.hooks"]


def config_dir():
    if WINDOWS:
        return os.path.join(os.environ.get("APPDATA", HOME), "RetroLauncher")
    if MAC:
        return os.path.join(HOME, "Library", "Application Support", "RetroLauncher")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), APP)


def default_config_path():
    return os.path.join(config_dir(), "config.toml")


def _which(name, *candidates):
    for c in candidates:
        if c and os.path.exists(os.path.expanduser(c)):
            return os.path.expanduser(c)
    return shutil.which(name) or name


# Where the sister projects live (one folder holding amiga_mcp,
# atari_st_games, hatari_augmented and 3do_dev); override with
# RETRO_PROJECTS or in the config.
PROJECTS = os.environ.get("RETRO_PROJECTS", "~/code/claude_world")


def defaults():
    if MAC:
        qemu_display = "cocoa,full-screen=on,zoom-to-fit=on,show-cursor=on"
        hatari = "{hatari_root}/build/src/Hatari.app/Contents/MacOS/Hatari"
    elif WINDOWS:
        qemu_display = "sdl,full-screen=on"
        hatari = "{hatari_root}/build/src/hatari.exe"
    else:
        qemu_display = "gtk,full-screen=on,zoom-to-fit=on"
        hatari = "{hatari_root}/build/src/hatari"
    amikit = "/Applications/AmiKit.app/Contents/SharedSupport/prefix/drive_c/AmiKit"
    return {
        "general": {
            "fullscreen": True,
            "boot_to_selector": True,
            "while_playing": "background",
            "stop_others_on_launch": False,
            "autostart": "",
            "projects": PROJECTS,
            "engineer_mode": False,
        },
        "platforms": {
            "amiga68k": {
                "enabled": True,
                "title": "Classic Amiga",
                "subtitle": "68k  ·  AmigaOS 3.x  ·  FS-UAE",
                "accent": "#ff8a3d",
                "selector_label": "Game Launcher (DH2:Dev)",
                "plain_label": "Workbench desktop",
                "emulator_fullscreen": False,
                "boot_to_selector": "default",
                "cwd": "",
                "paths": {
                    "fsuae": _which("fs-uae", "~/.amiga-devbench/fs-uae",  # amiga_mcp's patched build
                                    "/opt/homebrew/bin/fs-uae", "/usr/local/bin/fs-uae"),
                    "fsuae_config": "~/Documents/FS-UAE/Configurations/AmiKit-Debug.fs-uae",
                    "dev_dir": amikit + "/Dropbox/Dev",
                    "amiga_mcp": "{projects}/amiga_mcp",
                },
                "selector_command": "{fsuae} {fsuae_config} ?fullscreen:--fullscreen=1",
                "plain_command": "{fsuae} {fsuae_config} ?fullscreen:--fullscreen=1",
                "prepare_selector": ["{helper} flag off {dev_dir}/launcher.skip"],
                "prepare_plain": ["{helper} flag on {dev_dir}/launcher.skip"],
                "env": {},
                "env_fullscreen": {},
                "process_match": "{fsuae}",
                "workbench": {
                    "url": "http://localhost:3001/",
                    "start": "{amiga_mcp}/scripts/start.sh 68k",
                    "links": [
                        "DevBench web UI|open|http://localhost:3001/",
                        "MCP endpoint for Claude|copy|http://localhost:3001/mcp",
                        "FS-UAE debugger (patched build)|open|http://localhost:8765/",
                    ],
                },
            },
            "amigaos4": {
                "enabled": True,
                "title": "AmigaOS 4.1",
                "subtitle": "PowerPC  ·  Sam460ex  ·  QEMU",
                "accent": "#4fa8ff",
                "selector_label": "Game Launcher (DH1:launcher.list)",
                "plain_label": "Workbench desktop",
                "emulator_fullscreen": False,
                "boot_to_selector": "default",
                "cwd": "",
                "paths": {
                    "amiga_mcp": "{projects}/amiga_mcp",
                    "start_script": "{amiga_mcp}/scripts/start-qemu-os4.sh",
                    "os4_dir": "~/AmigaOS4",
                    "dev_hdf": "{os4_dir}/amigaos4-dev.hdf",
                    "xdftool": _which("xdftool"),
                },
                "selector_command": "{start_script}",
                "plain_command": "{start_script}",
                "prepare_selector": ["{helper} hdf-flag off {dev_hdf} launcher.skip --xdftool {xdftool}"],
                "prepare_plain": ["{helper} hdf-flag on {dev_hdf} launcher.skip --xdftool {xdftool}"],
                "env": {"OS4_DIR": "{os4_dir}"},
                "env_fullscreen": {"DISPLAY_ARG": qemu_display},
                "process_match": "qemu-system-ppc",
                "workbench": {
                    "url": "http://localhost:3000/",
                    "start": "{amiga_mcp}/scripts/start.sh os4",
                    "links": [
                        "DevBench web UI|open|http://localhost:3000/",
                        "MCP endpoint for Claude|copy|http://localhost:3000/mcp",
                        "QEMU monitor (HMP)|copy|nc 127.0.0.1 2348",
                    ],
                },
            },
            "atari": {
                "enabled": True,
                "title": "Atari ST · Falcon",
                "subtitle": "68000 / 68030 / 68060  ·  EmuTOS  ·  Hatari",
                "accent": "#ff4f6d",
                "selector_label": "ST Launcher (switches ST / Falcon)",
                "plain_label": "GEM desktop (C: = games drive)",
                "emulator_fullscreen": False,
                "boot_to_selector": "default",
                "cwd": "",
                "paths": {
                    "atari_root": "{projects}/atari_st_games",
                    "hatari_root": "{projects}/hatari_augmented",
                    "hatari": hatari,
                    "tos": "{hatari_root}/roms/emutos/emutos-1024k-1.4/etos1024k.img",
                    "drive": "{atari_root}/st_launcher/build/drive",
                    "machine": "ste",
                    "gui_python": "{python}",
                },
                "selector_command": "{python} {atari_root}/st_launcher/make_drive.py --no-build --run "
                                    "--machine {machine} ?fullscreen:--hatari-arg=--fullscreen",
                "plain_command": "{hatari} --agent-port 7777 --agent-rom-dir {hatari_root}/roms "
                                 "--tos {tos} --confirm-quit off --machine ste --memsize 4 "
                                 "--monitor rgb --dsp none --ttram 0 --natfeats on "
                                 "--harddrive {drive} ?fullscreen:--fullscreen",
                "prepare_selector": [],
                "prepare_plain": [],
                "env": {"HATARI": "{hatari}"},
                "env_fullscreen": {},
                "process_match": "{hatari}",
                "workbench": {
                    "url": "http://localhost:7777/",
                    "start": "",
                    "links": [
                        "Hatari debugger GUI|run|{gui_python} {hatari_root}/tools/agent/hatari_gui.py",
                        "Agent API (JSON)|open|http://localhost:7777/",
                    ],
                },
            },
            "3do": {
                "enabled": True,
                "title": "3DO",
                "subtitle": "ARM60  ·  Opera core  ·  tdo",
                "accent": "#ffd23f",
                "selector_label": "Arcade disc (every game)",
                "plain_label": "Single disc: {game}",
                "emulator_fullscreen": False,
                "boot_to_selector": "default",
                "cwd": "{root}",
                "paths": {
                    "root": "{projects}/3do_dev",
                    "tdo": "{root}/.venv/bin/tdo" if not WINDOWS else "{root}/.venv/Scripts/tdo.exe",
                    "bios": "panafz10.bin",
                    "scale": "3",
                    "arcade": "{root}/projects/arcade/build/arcade.iso",
                    "game": "{root}/projects/planet_chomp/build/planet_chomp.iso",
                },
                "selector_command": "{tdo} --bios {bios} run --scale {scale} ?fullscreen:--fullscreen {arcade}",
                "plain_command": "{tdo} --bios {bios} run --scale {scale} ?fullscreen:--fullscreen {game}",
                "prepare_selector": [],
                "prepare_plain": [],
                "env": {},
                "env_fullscreen": {},
                "process_match": "{tdo} --bios",
                "workbench": {
                    "url": "http://localhost:3330/",
                    "start": "{tdo} devbench --port 3330",
                    "links": [
                        "3DO DevBench web UI|open|http://localhost:3330/",
                        "MCP server for Claude (stdio)|copy|{tdo} mcp",
                    ],
                },
            },
        },
    }


ORDER = ["amiga68k", "amigaos4", "atari", "3do"]

COMMENTS = {
    "general": """Retro Launcher settings. Edit here or in the launcher (press C).
fullscreen          the launcher itself fills the screen
boot_to_selector    default for every platform: boot straight into the
                    platform's own game selector
while_playing       "background": this menu stays open behind the emulator;
                    "hide": it disappears until the emulator quits
autostart           a platform key (amiga68k, amigaos4, atari, 3do) to
                    launch as soon as the launcher opens; "" for none
projects            folder holding amiga_mcp, atari_st_games, ...
                    ({projects} in the paths below)
engineer_mode       Power Engineer mode: the menu also shows each machine's
                    developer workbenches (P toggles it)""",
    "platforms.amiga68k": """Command words: {name} = a [paths] entry, {helper} = python -m
retro_launcher.hooks, ?fullscreen:WORD = WORD only when
emulator_fullscreen is on (?windowed: the opposite).
boot_to_selector: "default" (follow [general]), "on" or "off".
prepare_*: commands run, in order, before the emulator starts.
process_match: text in a running process's command line that means
this emulator is already running.
[workbench]: Power Engineer mode. url = checked to see whether it's up;
start = command that brings it up ("" = launching the machine does);
links = "Label|kind|target", kind open (browser), copy (clipboard) or
run (a command, through your login shell).""",
}


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path=None):
        self.path = path or default_config_path()
        self.data = defaults()
        self.error = ""
        if os.path.exists(self.path):
            try:
                self.data = merge(self.data, tomlio.load(self.path))
            except Exception as e:  # a broken file shouldn't stop the launcher
                self.error = "%s: %s" % (self.path, e)
            # replaced by while_playing
            if self.general.pop("minimize_on_launch", None) is not None:
                self.save()
        else:
            self.save()

    @property
    def general(self):
        return self.data["general"]

    def platform(self, key):
        return self.data["platforms"][key]

    def keys(self):
        ks = [k for k in ORDER if k in self.data["platforms"]]
        return ks + [k for k in self.data["platforms"] if k not in ks]

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(tomlio.dumps(self.data, COMMENTS))
        os.replace(tmp, self.path)

    def reset(self):
        self.data = defaults()

    # ---- expansion ----

    def variables(self, key):
        p = self.platform(key)
        v = {"home": HOME, "python": python_exe(), "config_dir": config_dir(),
             "projects": self.general.get("projects", PROJECTS)}
        v.update({k: str(x) for k, x in p.get("paths", {}).items()})
        return v

    def expand(self, key, text, variables=None, depth=0):
        v = variables or self.variables(key)
        out, i = [], 0
        while i < len(text):
            c = text[i]
            if c == "{":
                j = text.find("}", i)
                name = text[i + 1:j] if j > 0 else ""
                if name in v and depth < 8:
                    out.append(self.expand(key, v[name], v, depth + 1))
                    i = j + 1
                    continue
            out.append(c)
            i += 1
        s = "".join(out)
        if s.startswith("~"):
            s = os.path.expanduser(s)
        return s

    def selector_mode(self, key):
        b = str(self.platform(key).get("boot_to_selector", "default")).lower()
        if b in ("on", "true", "yes", "1"):
            return True
        if b in ("off", "false", "no", "0"):
            return False
        return bool(self.general.get("boot_to_selector", True))

    def argv(self, key, template, fullscreen):
        v = self.variables(key)
        out = []
        for word in split(template):
            if word.startswith("?fullscreen:"):
                if not fullscreen:
                    continue
                word = word[len("?fullscreen:"):]
            elif word.startswith("?windowed:"):
                if fullscreen:
                    continue
                word = word[len("?windowed:"):]
            if word == "{helper}":
                out += helper_argv()
                continue
            out.append(self.expand(key, word, v))
        return out

    def plan(self, key, selector=None):
        """Everything needed to launch platform `key`: (prepare, argv, cwd, env)."""
        p = self.platform(key)
        sel = self.selector_mode(key) if selector is None else selector
        fs = bool(p.get("emulator_fullscreen"))
        which = "selector" if sel else "plain"
        prepare = [self.argv(key, s, fs) for s in p.get("prepare_" + which, [])]
        argv = self.argv(key, p.get(which + "_command", ""), fs)
        env = dict(os.environ)
        # the helper must be importable whatever the cwd
        pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env["PYTHONPATH"] = pkg_parent + os.pathsep + env.get("PYTHONPATH", "")
        tables = [p.get("env", {})] + ([p.get("env_fullscreen", {})] if fs else [])
        for t in tables:
            for k, val in t.items():
                env[k] = self.expand(key, str(val))
        cwd = self.expand(key, p.get("cwd", "")) or None
        return prepare, argv, cwd, env

    def label(self, key, selector):
        p = self.platform(key)
        text = p.get("selector_label" if selector else "plain_label", "")
        v = self.variables(key)
        if not selector and "{game}" in text and "game" in v:
            return text.replace("{game}", os.path.basename(self.expand(key, v["game"])))
        return self.expand(key, text, v)

    def check_paths(self, key):
        """[(name, expanded, exists)] for every [paths] entry that looks like a path."""
        out = []
        for name, raw in self.platform(key).get("paths", {}).items():
            val = self.expand(key, str(raw))
            if "/" not in val and "\\" not in val:
                # a plain word: a program on PATH, or a setting like "ste"
                out.append((name, val, True if shutil.which(val) else None))
                continue
            path = val
            cwd = self.expand(key, self.platform(key).get("cwd", ""))
            if not os.path.isabs(path) and cwd:
                path = os.path.join(cwd, path)
            out.append((name, val, os.path.exists(path)))
        return out

    # ---- Power Engineer mode ----

    def workbench(self, key):
        """(health url, start argv or None) for a platform's developer workbench."""
        wb = self.platform(key).get("workbench", {}) or {}
        url = self.expand(key, str(wb.get("url", "")))
        start = str(wb.get("start", "")).strip()
        return url, (self.argv(key, start, False) if start else None)

    def workbench_links(self, key):
        """[(label, kind, target)] with the target expanded; kind is open, copy or run.
        A run target comes back as an argument list."""
        out = []
        for entry in (self.platform(key).get("workbench", {}) or {}).get("links", []):
            parts = [x.strip() for x in str(entry).split("|", 2)]
            if len(parts) != 3 or parts[1] not in ("open", "copy", "run"):
                continue
            label, kind, target = parts
            if kind == "run":
                out.append((label, kind, self.argv(key, target, False)))
            else:
                out.append((label, kind, " ".join(self.expand(key, w) for w in target.split(" "))))
        return out
