# SPDX-License-Identifier: MIT
"""The full-screen launcher: pick a machine, boot its emulator."""
import functools
import glob
import math
import os
import random
import subprocess
import sys
import time
import webbrowser

# macOS: a fullscreen window without a Space of its own, so hiding it while
# an emulator runs doesn't leave an empty black Space in front of it.
os.environ.setdefault("SDL_VIDEO_MAC_FULLSCREEN_SPACES", "0")
# ...and one an emulator's window can come in front of, which doesn't
# minimise itself when it loses focus.
os.environ.setdefault("SDL_ALLOW_TOPMOST", "0")
os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")

import pygame

from . import config as cfgmod
from .procs import (Launch, UrlWatcher, Watcher, copy_text, descendants, focus_pids, kill_pids,
                    spawn_detached)

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
ART_DIRS = {"amiga68k": "amiga68k", "amigaos4": "amigaos4", "atari": "atari", "3do": "3do"}

INK = (236, 240, 248)
DIM = (150, 160, 182)
FAINT = (92, 102, 128)
PANEL = (16, 20, 34)
OK = (90, 220, 140)
BAD = (255, 92, 92)
WARN = (255, 196, 70)

FONT_BOLD = "futura,avenirnextcondensed,avenirnext,helveticaneue,segoeui,dejavusans,arial"
FONT_BODY = "avenirnext,helveticaneue,segoeui,dejavusans,arial"
FONT_MONO = "menlo,consolas,dejavusansmono,couriernew"


def hexcolor(s, default=(120, 160, 255)):
    try:
        s = s.lstrip("#")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return default


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Fonts:
    def __init__(self):
        self.cache = {}

    def get(self, kind, size, bold=False):
        k = (kind, size, bold)
        if k not in self.cache:
            name = {"bold": FONT_BOLD, "body": FONT_BODY, "mono": FONT_MONO}[kind]
            try:
                self.cache[k] = pygame.font.SysFont(name, size, bold=bold)
            except Exception:
                self.cache[k] = pygame.font.Font(None, size)
        return self.cache[k]


def fit_text(font, text, width):
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text + "…")[0] > width:
        text = text[:-1]
    return text + "…"


def fit_font(fonts, kind, size, text, width, min_size=12):
    """The largest font (up to size) that fits text in width."""
    while size > min_size and fonts.get(kind, size).size(text)[0] > width:
        size -= 2
    return fonts.get(kind, size)


def mark(surface, center, ok, size, color):
    """A drawn tick or cross (fonts don't all have the glyphs)."""
    x, y = center
    k = size / 2
    w = max(2, int(size / 7))
    if ok:
        pts = [(x - k, y), (x - k / 3, y + k * 0.7), (x + k, y - k * 0.7)]
        pygame.draw.lines(surface, color, False, pts, w)
    else:
        pygame.draw.line(surface, color, (x - k * 0.7, y - k * 0.7), (x + k * 0.7, y + k * 0.7), w)
        pygame.draw.line(surface, color, (x - k * 0.7, y + k * 0.7), (x + k * 0.7, y - k * 0.7), w)


def chevron(surface, center, size, color):
    x, y = center
    k = size / 2
    pygame.draw.lines(surface, color, False, [(x - k / 2, y - k), (x + k / 2, y), (x - k / 2, y + k)],
                      max(2, int(size / 6)))


def cover(img, w, h):
    iw, ih = img.get_size()
    k = max(w / iw, h / ih)
    s = pygame.transform.smoothscale(img, (max(1, int(iw * k)), max(1, int(ih * k))))
    r = s.get_rect(center=(w // 2, h // 2))
    out = pygame.Surface((w, h))
    out.blit(s, r)
    return out


def blur(img, factor=10):
    w, h = img.get_size()
    small = pygame.transform.smoothscale(img, (max(1, w // factor), max(1, h // factor)))
    return pygame.transform.smoothscale(small, (w, h))


def rounded(surface, radius):
    """A copy of surface with rounded corners (per-pixel alpha)."""
    w, h = surface.get_size()
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
    out = surface.convert_alpha()
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return out


@functools.lru_cache(maxsize=64)
def shadow(w, h, radius, spread, alpha=150):
    s = pygame.Surface((w + spread * 4, h + spread * 4), pygame.SRCALPHA)
    pygame.draw.rect(s, (0, 0, 0, alpha), (spread * 2, spread * 2, w, h), border_radius=radius)
    return blur(s, max(2, spread // 2))


@functools.lru_cache(maxsize=16)
def glow_rect(w, h, rad, acc):
    g = pygame.Surface((w + 40, h + 40), pygame.SRCALPHA)
    pygame.draw.rect(g, acc + (110,), (10, 10, w + 20, h + 20), border_radius=rad + 8)
    return blur(g, 6)


def fmt_time(sec):
    sec = int(sec)
    return "%d:%02d:%02d" % (sec // 3600, sec // 60 % 60, sec % 60) if sec >= 3600 \
        else "%d:%02d" % (sec // 60, sec % 60)


def open_in_editor(path):
    try:
        if cfgmod.WINDOWS:
            os.startfile(path)  # noqa: S606 - the user's own config file
        elif cfgmod.MAC:
            subprocess.Popen(["open", "-t", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError:
        pass


# ---------------------------------------------------------------- settings

class Field:
    def __init__(self, label, get, set_, kind="text", choices=None, help="", check=None):
        self.label, self.get, self.set, self.kind = label, get, set_, kind
        self.choices, self.help, self.check = choices or [], help, check


class Settings:
    """The config screen: a tab per platform plus General."""

    SEP = " ;; "

    def __init__(self, app):
        self.app = app
        self.tab = 0
        self.row = 0
        self.scroll = 0
        self.editing = None       # (field, text, cursor)
        self.message = ""
        self.preview = None
        self.rects = []           # (rect, action)

    @property
    def cfg(self):
        return self.app.cfg

    def tabs(self):
        return [("general", "General")] + [(k, self.cfg.platform(k).get("title", k))
                                           for k in self.cfg.keys()]

    def fields(self):
        key = self.tabs()[self.tab][0]
        cfg = self.cfg
        out = []
        if key == "general":
            g = cfg.general
            out = [
                Field("Launcher fullscreen", lambda: g.get("fullscreen"),
                      lambda v: (g.__setitem__("fullscreen", v), self.app.apply_fullscreen()),
                      "bool", help="This menu fills the screen (F toggles it too)"),
                Field("Boot into game selectors", lambda: g.get("boot_to_selector"),
                      lambda v: g.__setitem__("boot_to_selector", v), "bool",
                      help="Default for every machine; each one can override it"),
                Field("While playing", lambda: g.get("while_playing", "background"),
                      lambda v: g.__setitem__("while_playing", v), "choice",
                      choices=["background", "hide"],
                      help="background: this menu stays open behind the emulator; "
                           "hide: it disappears. Either way it comes back when the emulator quits"),
                Field("Stop others on launch", lambda: g.get("stop_others_on_launch"),
                      lambda v: g.__setitem__("stop_others_on_launch", v), "bool",
                      help="Starting one machine stops the emulators this launcher started"),
                Field("Autostart machine", lambda: g.get("autostart", ""),
                      lambda v: g.__setitem__("autostart", v), "choice",
                      choices=[""] + cfg.keys(),
                      help="Launch this machine as soon as the launcher opens"),
                Field("Power Engineer mode", lambda: g.get("engineer_mode", False),
                      lambda v: (g.__setitem__("engineer_mode", v), self.app.set_engineer(v)), "bool",
                      help="Show each machine's developer workbenches on the menu (P toggles it)"),
                Field("Projects folder", lambda: g.get("projects", ""),
                      lambda v: g.__setitem__("projects", v), "text",
                      help="{projects}: the folder holding amiga_mcp, atari_st_games, 3do_dev ...",
                      check=lambda v: os.path.isdir(os.path.expanduser(v))),
                Field("Open config file in editor", None, None, "action",
                      help=cfg.path),
                Field("Reset everything to defaults", None, None, "action",
                      help="Press Enter twice"),
            ]
            return key, out
        p = cfg.platform(key)

        def setter(k):
            return lambda v: p.__setitem__(k, v)

        def lst(k, label):
            return Field(label, lambda: self.SEP.join(p.get(k, [])),
                         lambda v: p.__setitem__(k, [s.strip() for s in v.split(self.SEP.strip())
                                                     if s.strip()]),
                         "text", help="Commands run first, in order; separate them with ;;")

        out = [
            Field("Show on the menu", lambda: p.get("enabled", True), setter("enabled"), "bool"),
            Field("Boot into", lambda: p.get("boot_to_selector", "default"), setter("boot_to_selector"),
                  "choice", choices=["default", "on", "off"],
                  help="default = General setting; on = %s; off = %s" % (
                      cfg.label(key, True), cfg.label(key, False))),
            Field("Emulator fullscreen", lambda: p.get("emulator_fullscreen", False),
                  setter("emulator_fullscreen"), "bool",
                  help="Adds the ?fullscreen: words and env_fullscreen settings"),
        ]
        for name in list(p.get("paths", {})):
            out.append(Field("  " + name, (lambda n=name: p["paths"].get(n, "")),
                             (lambda v, n=name: p["paths"].__setitem__(n, v)), "text",
                             help="{%s}" % name, check=("path", key, name)))
        out += [
            Field("Selector command", lambda: p.get("selector_command", ""), setter("selector_command"),
                  help="Run when booting into the game selector"),
            Field("Plain command", lambda: p.get("plain_command", ""), setter("plain_command"),
                  help="Run when the selector is off"),
            lst("prepare_selector", "Before selector boot"),
            lst("prepare_plain", "Before plain boot"),
            Field("Working folder", lambda: p.get("cwd", ""), setter("cwd")),
            Field("Running-process match", lambda: p.get("process_match", ""), setter("process_match"),
                  help="Text in a process command line that means this emulator is running"),
            Field("Workbench URL", lambda: p.setdefault("workbench", {}).get("url", ""),
                  lambda v: p.setdefault("workbench", {}).__setitem__("url", v),
                  help="Power Engineer mode: checked to tell whether the workbench is up"),
            Field("Workbench start", lambda: p.setdefault("workbench", {}).get("start", ""),
                  lambda v: p.setdefault("workbench", {}).__setitem__("start", v),
                  help="Command that brings the workbench up (empty: launching the machine does)"),
            Field("Workbench links", lambda: self.SEP.join(p.setdefault("workbench", {}).get("links", [])),
                  lambda v: p.setdefault("workbench", {}).__setitem__(
                      "links", [x.strip() for x in v.split(self.SEP.strip()) if x.strip()]),
                  help="Label|open|url, Label|copy|text or Label|run|command; separate with ;;"),
            Field("Title", lambda: p.get("title", ""), setter("title")),
            Field("Subtitle", lambda: p.get("subtitle", ""), setter("subtitle")),
            Field("Accent colour", lambda: p.get("accent", ""), setter("accent")),
            Field("Selector label", lambda: p.get("selector_label", ""), setter("selector_label")),
            Field("Plain label", lambda: p.get("plain_label", ""), setter("plain_label")),
            Field("Preview commands", None, None, "action", help="Show what will run"),
            Field("Show last log", None, None, "action"),
            Field("Reset this machine to defaults", None, None, "action", help="Press Enter twice"),
        ]
        return key, out

    # ---- input ----

    def commit(self, field, value):
        field.set(value)
        self.cfg.save()
        self.app.refresh_watcher()
        self.message = "Saved"

    def activate(self, field, key):
        if field.kind == "bool":
            self.commit(field, not field.get())
        elif field.kind == "choice":
            ch = field.choices
            cur = field.get()
            self.commit(field, ch[(ch.index(cur) + 1) % len(ch)] if cur in ch else ch[0])
        elif field.kind == "text":
            text = str(field.get() or "")
            self.editing = [field, text, len(text)]
            pygame.key.start_text_input()
        elif field.kind == "action":
            self.action(field.label, key)

    def action(self, label, key):
        if label.startswith("Open config"):
            self.cfg.save()
            open_in_editor(self.cfg.path)
            self.message = "Opened " + self.cfg.path
        elif label.startswith("Reset"):
            if self.message != "Press Enter again to reset":
                self.message = "Press Enter again to reset"
                return
            if key == "general":
                self.cfg.reset()
            else:
                self.cfg.data["platforms"][key] = cfgmod.defaults()["platforms"][key]
            self.cfg.save()
            self.app.refresh_watcher()
            self.message = "Reset to defaults"
        elif label.startswith("Preview"):
            lines = []
            for sel in (True, False):
                prep, argv, cwd, env = self.cfg.plan(key, sel)
                lines.append(("Game selector" if sel else "Plain boot") + ":")
                for a in prep:
                    lines.append("  prepare: " + " ".join(cfgmod_quote(x) for x in a))
                lines.append("  run: " + " ".join(cfgmod_quote(x) for x in argv))
                if cwd:
                    lines.append("  in: " + cwd)
                lines.append("")
            self.preview = ("Commands for " + self.cfg.platform(key).get("title", key), lines)
        elif label.startswith("Show last log"):
            self.preview = ("Log: " + self.app.launches[key].log_path,
                            self.app.launches[key].tail(40) or ["(no log yet)"])

    def key(self, ev):
        key, fields = self.fields()
        if self.preview:
            if ev.type == pygame.KEYDOWN:
                self.preview = None
            return
        if self.editing:
            return self.edit_key(ev)
        if ev.type != pygame.KEYDOWN:
            return
        k = ev.key
        if k in (pygame.K_ESCAPE, pygame.K_c, pygame.K_BACKSPACE):
            self.app.mode = "menu"
        elif k in (pygame.K_UP, pygame.K_w):
            self.row = (self.row - 1) % len(fields)
        elif k in (pygame.K_DOWN, pygame.K_s):
            self.row = (self.row + 1) % len(fields)
        elif k in (pygame.K_LEFT, pygame.K_a) or (k == pygame.K_TAB and ev.mod & pygame.KMOD_SHIFT):
            self.tab = (self.tab - 1) % len(self.tabs())
            self.row = self.scroll = 0
        elif k in (pygame.K_RIGHT, pygame.K_d, pygame.K_TAB):
            self.tab = (self.tab + 1) % len(self.tabs())
            self.row = self.scroll = 0
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.activate(fields[self.row], key)
            return
        if not self.message.startswith("Press Enter again"):
            pass
        else:
            self.message = ""

    def edit_key(self, ev):
        f, text, cur = self.editing
        if ev.type == pygame.TEXTINPUT:
            text = text[:cur] + ev.text + text[cur:]
            cur += len(ev.text)
        elif ev.type == pygame.KEYDOWN:
            k = ev.key
            meta = ev.mod & (pygame.KMOD_CTRL | pygame.KMOD_META)
            if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                pygame.key.stop_text_input()
                self.editing = None
                self.commit(f, text)
                return
            if k == pygame.K_ESCAPE:
                pygame.key.stop_text_input()
                self.editing = None
                self.message = "Not changed"
                return
            if k == pygame.K_BACKSPACE and cur > 0:
                text, cur = text[:cur - 1] + text[cur:], cur - 1
            elif k == pygame.K_DELETE:
                text = text[:cur] + text[cur + 1:]
            elif k == pygame.K_LEFT:
                cur = max(0, cur - 1)
            elif k == pygame.K_RIGHT:
                cur = min(len(text), cur + 1)
            elif k in (pygame.K_HOME,) or (meta and k == pygame.K_a):
                cur = 0
            elif k in (pygame.K_END,) or (meta and k == pygame.K_e):
                cur = len(text)
            elif meta and k == pygame.K_u:
                text, cur = "", 0
            elif meta and k == pygame.K_v:
                paste = clipboard_text()
                text = text[:cur] + paste + text[cur:]
                cur += len(paste)
        self.editing = [f, text, cur]

    def click(self, pos, double):
        for rect, act in self.rects:
            if rect.collidepoint(pos):
                kind, val = act
                if kind == "tab":
                    self.tab, self.row, self.scroll = val, 0, 0
                elif kind == "row":
                    key, fields = self.fields()
                    if self.row == val or double:
                        self.row = val
                        self.activate(fields[val], key)
                    self.row = val
                elif kind == "back":
                    self.app.mode = "menu"
                return

    def wheel(self, dy):
        _, fields = self.fields()
        self.row = max(0, min(len(fields) - 1, self.row - dy))

    # ---- drawing ----

    def draw(self, screen):
        F = self.app.fonts
        W, H = screen.get_size()
        u = H / 1000
        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((6, 8, 16, 238))
        screen.blit(veil, (0, 0))
        self.rects = []
        pad = int(60 * u)
        title = F.get("bold", int(54 * u)).render("SETTINGS", True, INK)
        screen.blit(title, (pad, pad))
        hint = F.get("body", int(20 * u)).render(
            "Up/Down choose  ·  Left/Right or Tab section  ·  Enter change  ·  Esc back"
            "      saved to " + self.cfg.path,
            True, DIM)
        screen.blit(hint, (pad, pad + title.get_height() + int(4 * u)))

        tabs = self.tabs()
        x, y = pad, pad + int(120 * u)
        tf = F.get("bold", int(26 * u))
        key, fields = self.fields()
        for i, (k, name) in enumerate(tabs):
            acc = INK if k == "general" else hexcolor(self.cfg.platform(k).get("accent"))
            surf = tf.render(name.upper(), True, (10, 12, 20) if i == self.tab else acc)
            r = pygame.Rect(x, y, surf.get_width() + int(36 * u), surf.get_height() + int(14 * u))
            if i == self.tab:
                pygame.draw.rect(screen, acc, r, border_radius=r.h // 2)
            else:
                pygame.draw.rect(screen, mix(PANEL, acc, 0.12), r, border_radius=r.h // 2)
            screen.blit(surf, surf.get_rect(center=r.center))
            self.rects.append((r, ("tab", i)))
            x = r.right + int(14 * u)

        top = y + int(80 * u)
        panel = pygame.Rect(pad, top, W - 2 * pad, H - top - int(110 * u))
        pygame.draw.rect(screen, (14, 17, 30), panel, border_radius=int(18 * u))
        pygame.draw.rect(screen, (40, 46, 70), panel, 1, border_radius=int(18 * u))
        rh = int(52 * u)
        visible = max(1, (panel.h - int(20 * u)) // rh)
        self.row = min(self.row, len(fields) - 1)
        if self.row < self.scroll:
            self.scroll = self.row
        if self.row >= self.scroll + visible:
            self.scroll = self.row - visible + 1
        lf = F.get("body", int(24 * u))
        vf = F.get("mono", int(21 * u))
        labw = int(panel.w * 0.28)
        acc = INK if key == "general" else hexcolor(self.cfg.platform(key).get("accent"))
        for n, i in enumerate(range(self.scroll, min(len(fields), self.scroll + visible))):
            f = fields[i]
            ry = panel.y + int(10 * u) + n * rh
            r = pygame.Rect(panel.x + int(10 * u), ry, panel.w - int(20 * u), rh - int(6 * u))
            self.rects.append((r, ("row", i)))
            sel = i == self.row
            if sel:
                pygame.draw.rect(screen, mix((14, 17, 30), acc, 0.18), r, border_radius=int(10 * u))
                pygame.draw.rect(screen, acc, r, 2, border_radius=int(10 * u))
            lab = lf.render(f.label, True, INK if sel else DIM)
            screen.blit(lab, (r.x + int(16 * u), r.centery - lab.get_height() // 2))
            vx = r.x + labw
            vw = r.right - vx - int(60 * u)
            if f.kind == "action":
                chevron(screen, (vx + int(8 * u), r.centery), int(18 * u), acc)
                continue
            if self.editing and self.editing[0] is f:
                self.draw_edit(screen, vf, pygame.Rect(vx, r.y + 4, vw, r.h - 8), acc)
                continue
            val = f.get()
            if f.kind == "bool":
                on = bool(val)
                sw = pygame.Rect(vx, r.centery - int(14 * u), int(56 * u), int(28 * u))
                pygame.draw.rect(screen, acc if on else (60, 66, 90), sw, border_radius=sw.h // 2)
                knob = sw.h - 6
                kx = sw.right - knob - 3 if on else sw.x + 3
                pygame.draw.rect(screen, INK, (kx, sw.y + 3, knob, knob), border_radius=knob // 2)
                t = lf.render("on" if on else "off", True, INK if on else DIM)
                screen.blit(t, (sw.right + int(12 * u), r.centery - t.get_height() // 2))
                continue
            text = str(val) if val not in (None, "") else ("(none)" if f.kind == "choice" else "")
            col = INK
            ok = None
            if f.check:
                if isinstance(f.check, tuple):
                    _, pk, name = f.check
                    for nm, expanded, exists in self.cfg.check_paths(pk):
                        if nm == name:
                            ok = exists
                            if expanded != text:
                                text = text + "   →  " + expanded
                else:
                    ok = f.check(text)
            s = vf.render(fit_text(vf, text, vw), True, col)
            screen.blit(s, (vx, r.centery - s.get_height() // 2))
            if ok is not None:
                mark(screen, (r.right - int(30 * u), r.centery), ok, int(20 * u), OK if ok else BAD)
        # scroll indicator
        if len(fields) > visible:
            bar_h = panel.h * visible / len(fields)
            by = panel.y + (panel.h - bar_h) * self.scroll / max(1, len(fields) - visible)
            pygame.draw.rect(screen, (70, 78, 110), (panel.right - 8, by, 4, bar_h), border_radius=2)

        f = fields[self.row]
        foot = f.help or ""
        if self.editing:
            foot = "Typing: Enter saves, Esc cancels, Ctrl/Cmd-V pastes, Ctrl/Cmd-U clears"
        s = F.get("body", int(22 * u)).render(fit_text(F.get("body", int(22 * u)), foot, W - 2 * pad),
                                              True, DIM)
        screen.blit(s, (pad, panel.bottom + int(18 * u)))
        if self.message:
            m = F.get("bold", int(22 * u)).render(self.message, True, WARN if "again" in self.message else OK)
            screen.blit(m, (W - pad - m.get_width(), panel.bottom + int(18 * u)))
        if self.cfg.error:
            e = F.get("body", int(20 * u)).render(fit_text(F.get("body", int(20 * u)),
                                                           "Config error: " + self.cfg.error, W - 2 * pad),
                                                  True, BAD)
            screen.blit(e, (pad, panel.bottom + int(52 * u)))
        if self.preview:
            draw_text_box(screen, F, self.preview[0], self.preview[1], acc)

    def draw_edit(self, screen, font, rect, acc):
        _, text, cur = self.editing
        pygame.draw.rect(screen, (4, 6, 12), rect, border_radius=6)
        pygame.draw.rect(screen, acc, rect, 2, border_radius=6)
        pre = font.size(text[:cur])[0]
        off = max(0, pre - (rect.w - 24))
        clip = screen.get_clip()
        screen.set_clip(rect.inflate(-8, -4))
        s = font.render(text, True, INK)
        screen.blit(s, (rect.x + 10 - off, rect.centery - s.get_height() // 2))
        if int(time.time() * 2) % 2 == 0:
            cx = rect.x + 10 - off + pre
            pygame.draw.line(screen, acc, (cx, rect.y + 6), (cx, rect.bottom - 6), 2)
        screen.set_clip(clip)


def cfgmod_quote(s):
    return s if s and all(c not in s for c in " \"'") else '"%s"' % s


def clipboard_text():
    try:
        t = pygame.scrap.get_text() if hasattr(pygame.scrap, "get_text") else ""
        return (t or "").replace("\r", "").replace("\n", " ")
    except Exception:
        return ""


def draw_text_box(screen, F, title, lines, acc):
    W, H = screen.get_size()
    u = H / 1000
    box = pygame.Rect(int(W * 0.08), int(H * 0.12), int(W * 0.84), int(H * 0.76))
    sh = shadow(box.w, box.h, int(18 * u), int(16 * u))
    screen.blit(sh, (box.x - int(32 * u), box.y - int(24 * u)))
    pygame.draw.rect(screen, (10, 12, 22), box, border_radius=int(18 * u))
    pygame.draw.rect(screen, acc, box, 2, border_radius=int(18 * u))
    tf = F.get("bold", int(30 * u))
    screen.blit(tf.render(fit_text(tf, title, box.w - 60), True, acc), (box.x + 30, box.y + 24))
    mf = F.get("mono", int(19 * u))
    y = box.y + int(80 * u)
    lh = mf.get_linesize()
    for line in lines[-max(1, (box.bottom - y - 50) // lh):]:
        screen.blit(mf.render(fit_text(mf, line, box.w - 60), True, INK), (box.x + 30, y))
        y += lh
    s = F.get("body", int(20 * u)).render("any key to close", True, DIM)
    screen.blit(s, (box.right - s.get_width() - 30, box.bottom - s.get_height() - 18))


# ---------------------------------------------------------------- the app

class App:
    def __init__(self, cfg_path=None, windowed=False, autostart=None):
        self.cfg = cfgmod.Config(cfg_path)
        pygame.init()
        pygame.display.set_caption("Retro Launcher")
        try:
            pygame.display.set_icon(pygame.image.load(os.path.join(ASSETS, "icon.png")))
        except Exception:
            pass
        try:
            pygame.scrap.init()
        except Exception:
            pass
        pygame.joystick.init()
        self.pads = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
        self.fonts = Fonts()
        self.force_windowed = windowed
        self.screen = None
        self.apply_fullscreen()
        self.clock = pygame.time.Clock()
        self.mode = "menu"
        self.settings = Settings(self)
        self.sel = 0
        self.sel_anim = 0.0
        self.toast, self.toast_until = "", 0.0
        self.confirm_stop = None
        self.log_view = None
        self.hidden = False
        self.away = False
        self.last_click = (0, None)
        self.axis_dir, self.axis_next = 0, 0.0
        logs = os.path.join(cfgmod.config_dir(), "logs")
        self.launches = {k: Launch(k, os.path.join(logs, k + ".log")) for k in self.cfg.keys()}
        self.art = self.load_art()
        self.art_index = {k: 0 for k in self.cfg.keys()}
        self.art_time = time.time()
        self.backdrops = {}
        self.cards_cache = {}
        self.rects = []
        self.stars = [(random.random(), random.random(), random.random()) for _ in range(140)]
        self.watcher = Watcher({})
        self.health = UrlWatcher()
        self.engineer = bool(self.cfg.general.get("engineer_mode", False))
        self.wb_pending = {}        # key -> deadline: open the workbench once it answers
        self.refresh_watcher()
        auto = autostart if autostart is not None else self.cfg.general.get("autostart", "")
        if auto in self.cfg.keys():
            self.sel = self.visible_keys().index(auto) if auto in self.visible_keys() else 0
            self.pending_autostart = auto
        else:
            self.pending_autostart = None

    # ---- setup ----

    def apply_fullscreen(self):
        full = self.cfg.general.get("fullscreen", True) and not self.force_windowed
        if full:
            self.display = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            info = pygame.display.Info()
            w = min(1600, int(info.current_w * 0.8)) if info.current_w > 0 else 1280
            self.display = pygame.display.set_mode((w, int(w * 9 / 16)), pygame.RESIZABLE)
        self.make_canvas()
        pygame.mouse.set_visible(True)
        self.backdrops = {}
        self.cards_cache = {}

    def make_canvas(self):
        # Draw on an opaque canvas: some display surfaces carry an alpha
        # channel, and translucent layers would replace pixels, not blend.
        self.screen = pygame.Surface(self.display.get_size(), 0, 24)
        self.backdrops, self.cards_cache = {}, {}

    def load_art(self):
        art = {}
        for k in self.cfg.keys():
            folder = self.cfg.platform(k).get("artwork") or os.path.join(ASSETS, ART_DIRS.get(k, k))
            files = sorted(glob.glob(os.path.join(os.path.expanduser(folder), "*.png")) +
                           glob.glob(os.path.join(os.path.expanduser(folder), "*.jpg")))
            imgs = []
            for f in files:
                try:
                    imgs.append(pygame.image.load(f).convert())
                except pygame.error:
                    pass
            if not imgs:
                s = pygame.Surface((640, 480))
                s.fill(mix((10, 12, 20), hexcolor(self.cfg.platform(k).get("accent")), 0.3))
                imgs = [s]
            art[k] = imgs
        return art

    def refresh_watcher(self):
        pats = {}
        for k in self.cfg.keys():
            pat = self.cfg.platform(k).get("process_match", "")
            pats[k] = self.cfg.expand(k, pat) if pat else ""
        self.watcher.patterns = pats
        urls = []
        if self.engineer:
            for k in self.visible_keys():
                url, _ = self.cfg.workbench(k)
                urls += [url] + [t for _, kind, t in self.cfg.workbench_links(k)
                                 if kind == "open" and t.startswith("http")]
        self.health.urls = [u for i, u in enumerate(urls) if u and u not in urls[:i]]
        self.backdrops = {}
        self.cards_cache = {}

    def visible_keys(self):
        return [k for k in self.cfg.keys() if self.cfg.platform(k).get("enabled", True)]

    # ---- state ----

    def status(self, key):
        """(state, text) for a platform."""
        ln = self.launches[key]
        ext = self.watcher.found.get(key, [])
        if ln.state == "preparing":
            return "busy", ln.message.upper()
        if ln.state == "running":
            return "running", "RUNNING  " + fmt_time(ln.uptime())
        if ext:
            return "running", "RUNNING  (started elsewhere)"
        if ln.state == "failed":
            return "failed", "FAILED: " + ln.message
        missing = [n for n, _, ok in self.cfg.check_paths(key) if ok is False]
        if missing:
            return "missing", "MISSING: " + ", ".join(missing)
        return "ready", "READY"

    def say(self, text, secs=3.5):
        self.toast, self.toast_until = text, time.time() + secs

    def launch(self, key, selector=None):
        st, _ = self.status(key)
        if st == "running":
            self.switch_to(key)
            return
        if st == "busy":
            self.say("%s is starting" % self.cfg.platform(key)["title"])
            return
        if self.cfg.general.get("stop_others_on_launch"):
            for k, ln in self.launches.items():
                if k != key and ln.alive:
                    ln.stop()
        prepare, argv, cwd, env = self.cfg.plan(key, selector)
        if not argv:
            self.say("No command set for this machine (C to configure)")
            return
        sel = self.cfg.selector_mode(key) if selector is None else selector
        self.launches[key].start(prepare, argv, cwd, env)
        self.say("Starting %s — %s" % (self.cfg.platform(key)["title"], self.cfg.label(key, sel)))
        self.launch_time = time.time()
        self.launched_key = key

    def emulator_pids(self, key):
        """The running emulator's processes: what the watcher saw, then
        everything under the process this launcher started."""
        ln = self.launches[key]
        pids = list(self.watcher.found.get(key, []))
        if ln.state == "running" and ln.proc:
            pids += [p for p in descendants(ln.proc.pid) if p not in pids]
        return pids

    def switch_to(self, key):
        """Bring a running emulator's window to the front."""
        title = self.cfg.platform(key)["title"]
        pids = self.emulator_pids(key)
        if self.go_away(key, pids):
            self.launched_key = key
            self.launch_time = time.time()
        else:
            self.say("%s is running, but its window couldn't be brought forward" % title, 5)

    def stop(self, key):
        ln = self.launches[key]
        ext = self.watcher.found.get(key, [])
        if not ln.alive and not ext:
            self.say("Nothing to stop")
            return
        if self.confirm_stop != key:
            self.confirm_stop = key
            self.say("Press S again to stop %s (unsaved work in it is lost)"
                     % self.cfg.platform(key)["title"], 4)
            return
        self.confirm_stop = None
        if ln.alive:
            ln.stop()
        if ext:
            kill_pids(ext)
        self.say("Stopping %s" % self.cfg.platform(key)["title"])

    def toggle_boot(self, key):
        p = self.cfg.platform(key)
        cur = self.cfg.selector_mode(key)
        default = bool(self.cfg.general.get("boot_to_selector", True))
        new = not cur
        p["boot_to_selector"] = "default" if new == default else ("on" if new else "off")
        self.cfg.save()
        self.say("%s boots into: %s" % (p["title"], self.cfg.label(key, new)))

    # ---- Power Engineer mode ----

    def set_engineer(self, on):
        self.engineer = bool(on)
        self.cfg.general["engineer_mode"] = self.engineer
        self.cfg.save()
        self.refresh_watcher()

    def toggle_engineer(self):
        self.set_engineer(not self.engineer)
        self.say("Power Engineer mode: workbenches shown (O opens one)" if self.engineer
                 else "Player mode")

    def workbench_up(self, key):
        url, _ = self.cfg.workbench(key)
        return self.health.up.get(url) if url else None

    def link_action(self, key, link):
        label, kind, target = link
        if kind == "open":
            webbrowser.open(target)
            self.say("Opened %s" % label)
        elif kind == "copy":
            self.say(("Copied: %s" % target) if copy_text(target) else "Couldn't copy %s" % target, 5)
        elif kind == "run":
            log = os.path.join(cfgmod.config_dir(), "logs", key + "-workbench.log")
            try:
                spawn_detached(target, self.cfg.general.get("projects") and
                               os.path.expanduser(self.cfg.general["projects"]), log)
                self.say("Started %s" % label)
            except OSError as e:
                self.say("%s: %s" % (label, e), 6)

    def open_workbench(self, key, idx=0):
        """Do a workbench link (the first: the main one). If the workbench
        isn't up yet, start it (or the machine) and do it once it answers."""
        links = self.cfg.workbench_links(key)
        title = self.cfg.platform(key)["title"]
        if not links:
            self.say("%s has no workbench set (C to configure)" % title)
            return
        link = links[min(idx, len(links) - 1)]
        url, start = self.cfg.workbench(key)
        needs_up = link[1] in ("open", "run") and url
        if not needs_up or self.health.up.get(url) or UrlWatcher.answers(url):
            self.link_action(key, link)
            return
        if key in self.wb_pending:
            self.say("%s workbench is starting…" % title)
            return
        if start:
            log = os.path.join(cfgmod.config_dir(), "logs", key + "-workbench.log")
            cwd = self.cfg.expand(key, self.cfg.platform(key).get("cwd", "")) or None
            try:
                spawn_detached(start, cwd, log)
            except OSError as e:
                self.say("Couldn't start the workbench: %s" % e, 6)
                return
        else:
            self.launch(key)
        self.wb_pending[key] = (time.time() + 240, idx)
        self.say("Starting the %s workbench… it opens when it's up" % title, 6)

    def poll_workbenches(self):
        for key, (deadline, idx) in list(self.wb_pending.items()):
            url, _ = self.cfg.workbench(key)
            if self.health.up.get(url):
                del self.wb_pending[key]
                self.link_action(key, self.cfg.workbench_links(key)[idx])
            elif time.time() > deadline:
                del self.wb_pending[key]
                self.say("%s workbench didn't come up (L for the log)" % self.cfg.platform(key)["title"], 6)

    # ---- window hide/show while an emulator runs ----

    def window(self):
        try:
            return pygame.Window.from_display_module()
        except Exception:
            return None

    def hide_window(self):
        if self.hidden:
            return
        win = self.window()
        if win and (sys.platform == "darwin" or self.display.get_flags() & pygame.FULLSCREEN):
            # macOS won't un-minimise a background app's window, and a
            # minimised fullscreen window leaves a black screen: hide it
            win.hide()
        elif win:
            win.minimize()
        else:
            pygame.display.iconify()
        self.hidden = True

    def show_window(self):
        win = self.window()
        if win:
            win.show()
            win.restore()
            try:
                win.focus()
            except Exception:
                pass
        # the OS won't let a background app raise itself; ask it to
        focus_pids([os.getpid()])
        self.hidden = False

    def go_away(self, key, pids=None):
        """Send the player to a running emulator: bring its window to the
        front, leaving this menu open behind it (or hidden, if set)."""
        hide = self.cfg.general.get("while_playing", "background") == "hide"
        if hide:
            self.hide_window()
        if focus_pids(self.emulator_pids(key) if pids is None else pids):
            self.away = True
            return True
        if hide:
            self.show_window()
        return False

    def come_back(self):
        if self.hidden:
            self.show_window()
        else:
            focus_pids([os.getpid()])
        self.away = False

    def manage_visibility(self):
        key = getattr(self, "launched_key", None)
        if key is None:
            return
        ln = self.launches[key]
        # an emulator started elsewhere counts until the process watcher loses it
        running = ln.alive or bool(self.watcher.found.get(key))
        if not self.away and ln.state == "running" and time.time() - self.launch_time > 1.5:
            self.go_away(key)
            self.away = True        # even if no window was found: don't retry every frame
        elif self.away and not running and time.time() - self.launch_time > 3:
            self.come_back()
            self.launched_key = None
            if ln.state == "failed":
                self.say("%s: %s (L for the log)" % (self.cfg.platform(key)["title"], ln.message), 6)

    # ---- input ----

    def move(self, d):
        keys = self.visible_keys()
        if keys:
            self.sel = (self.sel + d) % len(keys)
            self.confirm_stop = None

    def current(self):
        keys = self.visible_keys()
        if not keys:
            return None
        self.sel = min(self.sel, len(keys) - 1)
        return keys[self.sel]

    def menu_key(self, ev):
        if self.log_view:
            self.log_view = None
            return True
        k = ev.key
        key = self.current()
        if k in (pygame.K_LEFT, pygame.K_a, pygame.K_UP, pygame.K_w):
            self.move(-1)
        elif k in (pygame.K_RIGHT, pygame.K_d, pygame.K_DOWN, pygame.K_TAB):
            self.move(1)
        elif k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6):
            n = k - pygame.K_1
            if n < len(self.visible_keys()):
                self.sel = n
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE) and key:
            alt = ev.mod & (pygame.KMOD_SHIFT | pygame.KMOD_ALT)
            self.launch(key, (not self.cfg.selector_mode(key)) if alt else None)
        elif k == pygame.K_b and key:
            self.toggle_boot(key)
        elif k == pygame.K_s and key:
            self.stop(key)
        elif k == pygame.K_l and key:
            ln = self.launches[key]
            lines = ln.tail(40) or ["(no log yet)"]
            wlog = os.path.join(os.path.dirname(ln.log_path), key + "-workbench.log")
            if self.engineer and os.path.exists(wlog):
                with open(wlog, encoding="utf-8", errors="replace") as f:
                    lines = lines + ["", "-- workbench log: " + wlog] + f.read().splitlines()[-20:]
            self.log_view = ("Log: " + ln.log_path, lines)
        elif k == pygame.K_p:
            self.toggle_engineer()
        elif k == pygame.K_o and key:
            if self.engineer:
                self.open_workbench(key)
            else:
                self.say("Press P for Power Engineer mode first")
        elif k == pygame.K_c:
            self.mode = "settings"
        elif k == pygame.K_f:
            self.cfg.general["fullscreen"] = not self.cfg.general.get("fullscreen", True)
            self.force_windowed = False
            self.cfg.save()
            self.apply_fullscreen()
        elif k in (pygame.K_ESCAPE, pygame.K_q):
            return False
        return True

    def pad_event(self, ev):
        """Gamepads: d-pad / stick move, A launch, X boot mode, Y log, B stop, Start settings."""
        if ev.type == pygame.JOYHATMOTION:
            x, y = ev.value
            d = x or -y
            if d:
                return self.synth(pygame.K_RIGHT if d > 0 else pygame.K_LEFT)
        elif ev.type == pygame.JOYBUTTONDOWN:
            b = ev.button
            mapping = {0: pygame.K_RETURN, 1: pygame.K_ESCAPE if self.mode == "settings" or self.log_view
                       else pygame.K_s, 2: pygame.K_b, 3: pygame.K_l, 6: pygame.K_c, 7: pygame.K_c,
                       9: pygame.K_c}
            if b in mapping:
                return self.synth(mapping[b])
        elif ev.type == pygame.JOYAXISMOTION and ev.axis in (0, 1):
            d = 0 if abs(ev.value) < 0.6 else (1 if ev.value > 0 else -1)
            if d != self.axis_dir:
                self.axis_dir = d
                if d:
                    if self.mode == "settings":
                        return self.synth((pygame.K_RIGHT if d > 0 else pygame.K_LEFT) if ev.axis == 0
                                          else (pygame.K_DOWN if d > 0 else pygame.K_UP))
                    return self.synth(pygame.K_RIGHT if d > 0 else pygame.K_LEFT)
        elif ev.type == pygame.JOYDEVICEADDED:
            self.pads = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
        return True

    def synth(self, key):
        ev = pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="")
        if self.mode == "settings":
            if self.settings.preview:
                self.settings.preview = None
                return True
            self.settings.key(ev)
            return True
        return self.menu_key(ev)

    def menu_click(self, pos, double):
        if self.log_view:
            self.log_view = None
            return True
        for rect, act in self.rects:
            if rect.collidepoint(pos):
                kind, val = act
                if kind == "card":
                    idx = self.visible_keys().index(val)
                    if idx == self.sel or double:
                        self.sel = idx
                        self.launch(val)
                    self.sel = idx
                elif kind == "boot":
                    self.toggle_boot(val)
                elif kind == "link":
                    self.open_workbench(val[0], val[1])
                elif kind == "button":
                    return self.menu_key(pygame.event.Event(pygame.KEYDOWN, key=val, mod=0, unicode=""))
                return True
        return True

    # ---- drawing ----

    def backdrop(self, key, idx):
        W, H = self.screen.get_size()
        ck = (key, idx, W, H)
        if ck not in self.backdrops:
            img = cover(self.art[key][idx % len(self.art[key])], W, H)
            b = blur(img, 14)
            dark = pygame.Surface((W, H), pygame.SRCALPHA)
            for y in range(0, H, 4):
                t = y / H
                a = int(160 + 80 * t)
                pygame.draw.rect(dark, (6, 8, 18, min(245, a)), (0, y, W, 4))
            b.blit(dark, (0, 0))
            if len(self.backdrops) > 12:
                self.backdrops.clear()
            self.backdrops[ck] = b
        return self.backdrops[ck]

    def draw_background(self, key, t):
        W, H = self.screen.get_size()
        acc = hexcolor(self.cfg.platform(key).get("accent"))
        idx = self.art_index[key]
        self.screen.blit(self.backdrop(key, idx), (0, 0))
        # perspective floor grid
        horizon = int(H * 0.70)
        grid = pygame.Surface((W, H - horizon), pygame.SRCALPHA)
        gh = H - horizon
        col = acc + (60,)
        for i in range(-16, 17):
            x0 = W / 2 + i * W * 0.035
            x1 = W / 2 + i * W * 0.22
            pygame.draw.aaline(grid, col, (x0, 0), (x1, gh))
        phase = (t * 0.25) % 1.0
        for j in range(14):
            z = ((j + phase) / 14) ** 2
            pygame.draw.line(grid, acc + (int(25 + 60 * z),), (0, int(z * gh)), (W, int(z * gh)))
        self.screen.blit(grid, (0, horizon))
        # stars
        for sx, sy, sp in self.stars:
            tw = 0.5 + 0.5 * math.sin(t * (1 + 2 * sp) + sp * 20)
            c = int(90 + 140 * tw * sp)
            self.screen.set_at((int(sx * W), int(sy * horizon * 0.95)), (c, c, min(255, c + 30)))

    def card_surface(self, key, w, h, idx):
        ck = (key, w, h, idx)
        if ck in self.cards_cache:
            return self.cards_cache[ck]
        img = cover(self.art[key][idx % len(self.art[key])], w, h)
        surf = rounded(img, max(6, w // 28))
        if len(self.cards_cache) > 40:
            self.cards_cache.clear()
        self.cards_cache[ck] = surf
        return surf

    def draw_menu(self, t):
        W, H = self.screen.get_size()
        u = H / 1000
        keys = self.visible_keys()
        F = self.fonts
        self.rects = []
        key = self.current()
        if not key:
            self.screen.fill((8, 10, 18))
            s = F.get("bold", int(40 * u)).render("No machines enabled — press C", True, INK)
            self.screen.blit(s, s.get_rect(center=(W // 2, H // 2)))
            return
        self.draw_background(key, t)
        acc = hexcolor(self.cfg.platform(key).get("accent"))

        # header
        pad = int(56 * u)
        title = F.get("bold", int(64 * u)).render("RETRO LAUNCHER", True, INK)
        gk = ("title", int(64 * u), acc)
        if gk not in self.cards_cache:
            g = F.get("bold", int(64 * u)).render("RETRO LAUNCHER", True, acc).convert_alpha()
            self.cards_cache[gk] = blur(g, 4)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            self.screen.blit(self.cards_cache[gk], (pad + dx, pad + dy))
        self.screen.blit(title, (pad, pad))
        sub = F.get("body", int(24 * u)).render(
            "POWER ENGINEER  —  each machine with its developer workbench" if self.engineer else
            "Amiga · AmigaOS 4 · Atari · 3DO  —  pick a machine and boot it", True, acc if self.engineer else DIM)
        self.screen.blit(sub, (pad + 4, pad + title.get_height()))
        clock = F.get("bold", int(34 * u)).render(time.strftime("%H:%M"), True, DIM)
        self.screen.blit(clock, (W - pad - clock.get_width(), pad + int(10 * u)))

        # cards
        n = len(keys)
        cols = n if W / H > 1.25 or n <= 2 else 2
        rows = math.ceil(n / cols)
        gap = int(34 * u)
        area_top = int(H * 0.20)
        area_bot = H - int((330 if self.engineer else 150) * u)
        cw = (W - 2 * pad - (cols - 1) * gap) / cols
        ch_img = cw * 0.75
        info_h = int(190 * u)
        ch = ch_img + info_h
        maxh = (area_bot - area_top - (rows - 1) * gap) / rows
        if ch > maxh:
            k = maxh / ch
            cw *= k
            ch_img *= k
            ch = maxh
        total_w = cols * cw + (cols - 1) * gap
        x0 = (W - total_w) / 2
        y0 = area_top + (area_bot - area_top - (rows * ch + (rows - 1) * gap)) / 2
        self.sel_anim += (self.sel - self.sel_anim) * 0.25
        for i, k in enumerate(keys):
            r_, c_ = divmod(i, cols)
            cx = x0 + c_ * (cw + gap)
            cy = y0 + r_ * (ch + gap)
            focus = max(0.0, 1 - abs(self.sel_anim - i))
            self.draw_card(k, cx, cy, cw, ch_img, ch, focus, i == self.sel, t, u)
        if self.engineer:
            self.draw_workbench_panel(key, pygame.Rect(pad, area_bot + int(26 * u), W - 2 * pad,
                                                       H - int(118 * u) - area_bot - int(26 * u)), acc, u)

        # footer buttons
        boot = self.cfg.selector_mode(key)
        st, _ = self.status(key)
        btns = [("ENTER", "Stop" if False else "Launch", pygame.K_RETURN),
                ("B", "Boot: " + ("selector" if boot else "plain"), pygame.K_b),
                ("S", "Stop", pygame.K_s), ("L", "Log", pygame.K_l),
                ("C", "Settings", pygame.K_c), ("F", "Fullscreen", pygame.K_f),
                ("P", "Player" if self.engineer else "Engineer", pygame.K_p),
                ("ESC", "Quit", pygame.K_ESCAPE)]
        if st == "running":
            btns[0] = ("ENTER", "Switch to it", pygame.K_RETURN)
        if self.engineer:
            btns.insert(1, ("O", "Workbench", pygame.K_o))
            btns = [b for b in btns if b[2] != pygame.K_f]      # room for it: F still works
        bf = F.get("bold", int(20 * u))
        lf = F.get("body", int(22 * u))
        items = []
        for cap, lab, kk in btns:
            a = bf.render(cap, True, (10, 12, 20))
            b = lf.render(lab, True, INK)
            items.append((a, b, kk))
        wtot = sum(a.get_width() + b.get_width() + int(56 * u) for a, b, _ in items)
        x = (W - wtot) / 2
        y = H - int(82 * u)
        for a, b, kk in items:
            kr = pygame.Rect(x, y, a.get_width() + int(18 * u), int(34 * u))
            pygame.draw.rect(self.screen, acc if kk == pygame.K_RETURN else (200, 206, 222), kr,
                             border_radius=int(8 * u))
            self.screen.blit(a, a.get_rect(center=kr.center))
            self.screen.blit(b, (kr.right + int(10 * u), kr.centery - b.get_height() // 2))
            full = pygame.Rect(kr.x, kr.y, kr.w + b.get_width() + int(16 * u), kr.h)
            self.rects.append((full, ("button", kk)))
            x = full.right + int(40 * u)
        if self.pads:
            ph = F.get("body", int(18 * u)).render(
                "Gamepad: A launch · X boot mode · B stop · Y log · Start settings", True, FAINT)
            self.screen.blit(ph, ph.get_rect(center=(W // 2, H - int(26 * u))))

    def draw_card(self, key, x, y, w, h_img, h, focus, selected, t, u):
        p = self.cfg.platform(key)
        acc = hexcolor(p.get("accent"))
        F = self.fonts
        lift = int(14 * u * focus)
        x, y, w, h_img, h = int(x), int(y) - lift, int(w), int(h_img), int(h)
        rad = max(8, int(22 * u))
        # shadow + glow
        sh = shadow(w, h, rad, int(18 * u), 170)
        self.screen.blit(sh, (x - int(36 * u), y - int(28 * u)))
        if selected:
            pulse = 0.6 + 0.4 * math.sin(t * 3)
            g = glow_rect(w, h, rad, acc)
            g.set_alpha(int(255 * pulse))
            self.screen.blit(g, (x - 20, y - 20))
        body = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, mix(PANEL, acc, 0.10 + 0.08 * focus), body, border_radius=rad)
        # artwork, cross-fading between screenshots on the selected card
        inset = max(6, int(12 * u))
        iw, ih = w - 2 * inset, h_img - inset
        idx = self.art_index[key] if selected else 0
        img = self.card_surface(key, iw, ih, idx)
        self.screen.blit(img, (x + inset, y + inset))
        if selected and len(self.art[key]) > 1:
            fade = min(1.0, max(0.0, (time.time() - self.art_time - 3.6) / 0.6))
            if fade > 0:
                nxt = self.card_surface(key, iw, ih, idx + 1).copy()
                nxt.set_alpha(int(255 * fade))
                self.screen.blit(nxt, (x + inset, y + inset))
        if not selected:
            veil = pygame.Surface((iw, ih), pygame.SRCALPHA)
            pygame.draw.rect(veil, (6, 8, 16, int(120 * (1 - focus))), (0, 0, iw, ih),
                             border_radius=max(6, iw // 28))
            self.screen.blit(veil, (x + inset, y + inset))
        pygame.draw.rect(self.screen, acc if selected else (60, 66, 92), body, 3 if selected else 1,
                         border_radius=rad)
        if self.engineer:
            # the workbench's state, on the artwork
            up = self.workbench_up(key)
            starting = key in self.wb_pending
            wf = F.get("bold", int(16 * u))
            ws = wf.render("WORKBENCH " + ("STARTING" if starting else "UP" if up else "OFF"), True, (10, 12, 20))
            wr = pygame.Rect(0, 0, ws.get_width() + int(20 * u), ws.get_height() + int(6 * u))
            wr.bottomleft = (x + inset + int(10 * u), y + inset + ih - int(10 * u))
            pygame.draw.rect(self.screen, WARN if starting else (OK if up else (150, 156, 176)), wr,
                             border_radius=wr.h // 2)
            self.screen.blit(ws, ws.get_rect(center=wr.center))
        self.rects.append((body, ("card", key)))
        # text
        ty = y + h_img + int(14 * u)
        tx = x + inset + int(8 * u)
        tw = w - 2 * inset - int(16 * u)
        title = p.get("title", key).upper()
        nf = fit_font(F, "bold", int(40 * u), title, tw)
        name = nf.render(fit_text(nf, title, tw), True, INK)
        self.screen.blit(name, (tx, ty))
        ty += name.get_height()
        sf = fit_font(F, "body", int(20 * u), p.get("subtitle", ""), tw, int(14 * u))
        sub = sf.render(fit_text(sf, p.get("subtitle", ""), tw), True, acc)
        self.screen.blit(sub, (tx, ty))
        ty += sub.get_height() + int(12 * u)
        # boot mode line (click to toggle)
        sel_mode = self.cfg.selector_mode(key)
        bm = F.get("body", int(19 * u))
        icon = int(14 * u)
        lab = self.cfg.label(key, sel_mode)
        s = bm.render(fit_text(bm, lab, tw - icon - 10), True, INK if sel_mode else DIM)
        r = s.get_rect(topleft=(tx + icon + int(10 * u), ty))
        cy = r.centery
        if sel_mode:
            pygame.draw.polygon(self.screen, acc, [(tx, cy - icon // 2), (tx + icon, cy), (tx, cy + icon // 2)])
        else:
            pygame.draw.rect(self.screen, DIM, (tx, cy - icon // 2 + 1, icon - 2, icon - 2))
        self.screen.blit(s, r)
        r.x = tx
        self.rects.insert(0, (r.inflate(10, 8), ("boot", key)))
        ty += s.get_height() + int(10 * u)
        # status pill
        st, text = self.status(key)
        col = {"running": OK, "busy": WARN, "failed": BAD, "missing": BAD, "ready": (170, 180, 205)}[st]
        pf = F.get("bold", int(18 * u))
        ps = pf.render(fit_text(pf, text, tw - 24), True, (10, 12, 20))
        pr = pygame.Rect(tx, ty, ps.get_width() + int(22 * u), ps.get_height() + int(8 * u))
        if pr.bottom < y + h - 4:
            pygame.draw.rect(self.screen, col, pr, border_radius=pr.h // 2)
            self.screen.blit(ps, ps.get_rect(center=pr.center))
    def draw_workbench_panel(self, key, box, acc, u):
        """Power Engineer mode: the selected machine's developer workbench."""
        if box.h < int(60 * u):
            return
        F = self.fonts
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, PANEL + (225,), panel.get_rect(), border_radius=int(16 * u))
        self.screen.blit(panel, box.topleft)
        pygame.draw.rect(self.screen, acc, box, 2, border_radius=int(16 * u))
        x, y = box.x + int(24 * u), box.y + int(14 * u)
        title = self.cfg.platform(key).get("title", key).upper()
        hs = F.get("bold", int(26 * u)).render("DEVELOPER WORKBENCH  ·  " + title, True, acc)
        self.screen.blit(hs, (x, y))
        url, start = self.cfg.workbench(key)
        up = self.workbench_up(key)
        if key in self.wb_pending:
            state, col = "starting…", WARN
        elif up:
            state, col = "up  ·  " + url, OK
        else:
            state, col = "not running  ·  O starts it" if (start or url) else "", DIM
        ss = F.get("body", int(20 * u)).render(state, True, col)
        self.screen.blit(ss, (box.right - int(24 * u) - ss.get_width(), y + (hs.get_height() - ss.get_height()) // 2))
        y += hs.get_height() + int(10 * u)
        rf, mf, tf = F.get("body", int(22 * u)), F.get("mono", int(18 * u)), F.get("bold", int(16 * u))
        row_h = int(38 * u)
        tags = {"open": "OPEN", "copy": "COPY", "run": "RUN"}
        for i, (label, kind, target) in enumerate(self.cfg.workbench_links(key)):
            if y + row_h > box.bottom - int(8 * u):
                break
            row = pygame.Rect(box.x + int(12 * u), y, box.w - int(24 * u), row_h - int(4 * u))
            if row.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(self.screen, mix(PANEL, acc, 0.22), row, border_radius=int(8 * u))
            cy = row.centery
            dot = self.health.up.get(target) if kind == "open" else (up if kind == "run" else None)
            dcol = OK if dot else ((110, 118, 142) if dot is False else FAINT)
            pygame.draw.circle(self.screen, dcol, (row.x + int(16 * u), cy), max(3, int(6 * u)))
            ls = rf.render(label, True, INK)
            self.screen.blit(ls, (row.x + int(34 * u), cy - ls.get_height() // 2))
            tag = tf.render(tags[kind], True, (10, 12, 20))
            tr = pygame.Rect(0, 0, tag.get_width() + int(20 * u), tag.get_height() + int(6 * u))
            tr.midright = (row.right - int(10 * u), cy)
            pygame.draw.rect(self.screen, acc if i == 0 else (200, 206, 222), tr, border_radius=tr.h // 2)
            self.screen.blit(tag, tag.get_rect(center=tr.center))
            text = " ".join(target) if isinstance(target, list) else target
            tx = row.x + int(34 * u) + max(ls.get_width() + int(24 * u), int(380 * u))
            ts = mf.render(fit_text(mf, text, tr.x - tx - int(16 * u)), True, DIM)
            self.screen.blit(ts, (tx, cy - ts.get_height() // 2))
            self.rects.insert(0, (row, ("link", (key, i))))
            y += row_h

    def draw_overlays(self, t):
        W, H = self.screen.get_size()
        u = H / 1000
        if time.time() < self.toast_until and self.toast:
            f = self.fonts.get("bold", int(26 * u))
            s = f.render(fit_text(f, self.toast, int(W * 0.8)), True, INK)
            r = s.get_rect(center=(W // 2, int(H * 0.165)))
            box = r.inflate(int(48 * u), int(22 * u))
            pygame.draw.rect(self.screen, (12, 14, 26), box, border_radius=box.h // 2)
            key = self.current()
            acc = hexcolor(self.cfg.platform(key).get("accent")) if key else INK
            pygame.draw.rect(self.screen, acc, box, 2, border_radius=box.h // 2)
            self.screen.blit(s, r)
        if self.log_view:
            key = self.current()
            draw_text_box(self.screen, self.fonts, self.log_view[0], self.log_view[1],
                          hexcolor(self.cfg.platform(key).get("accent")) if key else INK)

    # ---- main loop ----

    def run(self, snapshot=None):
        """snapshot: (png path, frames, setup callable) renders and saves a frame, for tests."""
        running = True
        t0 = time.time()
        frames = 0
        if snapshot and snapshot[2]:
            snapshot[2](self)
        if self.pending_autostart:
            self.launch(self.pending_autostart)
        while running:
            now = time.time()
            t = now - t0
            if now - self.art_time > 4.2:
                key = self.current()
                if key:
                    self.art_index[key] = (self.art_index[key] + 1) % len(self.art[key])
                self.art_time = now
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type in (pygame.VIDEORESIZE, pygame.WINDOWSIZECHANGED):
                    self.display = pygame.display.get_surface()
                    if self.display.get_size() != self.screen.get_size():
                        self.make_canvas()
                elif ev.type in (pygame.JOYHATMOTION, pygame.JOYBUTTONDOWN, pygame.JOYAXISMOTION,
                                 pygame.JOYDEVICEADDED):
                    running = self.pad_event(ev) is not False
                elif self.mode == "settings":
                    if ev.type in (pygame.KEYDOWN, pygame.TEXTINPUT):
                        self.settings.key(ev)
                    elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                        double = now - self.last_click[0] < 0.35
                        self.last_click = (now, ev.pos)
                        if self.settings.preview:
                            self.settings.preview = None
                        else:
                            self.settings.click(ev.pos, double)
                    elif ev.type == pygame.MOUSEWHEEL:
                        self.settings.wheel(ev.y)
                elif ev.type == pygame.KEYDOWN:
                    running = self.menu_key(ev)
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    double = now - self.last_click[0] < 0.35
                    self.last_click = (now, ev.pos)
                    running = self.menu_click(ev.pos, double) is not False
                elif ev.type == pygame.MOUSEWHEEL:
                    self.move(-ev.y)
            self.manage_visibility()
            if self.wb_pending:
                self.poll_workbenches()
            if self.hidden:
                self.clock.tick(4)
                continue
            if self.away and not pygame.key.get_focused():
                fps = 10            # behind an emulator: keep animating, gently
            else:
                fps = 60
            if self.mode == "settings":
                key = self.current()
                if key:
                    self.draw_background(key, t)
                self.settings.draw(self.screen)
            else:
                self.draw_menu(t)
            self.draw_overlays(t)
            self.display.blit(self.screen, (0, 0))
            pygame.display.flip()
            self.clock.tick(fps)
            frames += 1
            if snapshot and frames >= snapshot[1]:
                pygame.image.save(self.screen, snapshot[0])
                running = False
        self.watcher.stop()
        self.health.stop()
        pygame.quit()
