# SPDX-License-Identifier: MIT
"""Draw the app icon: retro_launcher/assets/icon.png (1024 px), plus
icon.icns (macOS, needs iconutil) and icon.ico (Windows).

    .venv/bin/python tools/make_icon.py
"""
import io
import os
import shutil
import struct
import subprocess
import sys
import tempfile

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "retro_launcher", "assets")
SS = 4                      # supersampling factor
N = 1024 * SS
ACCENTS = ["#ff8a3d", "#4fa8ff", "#ff4f6d", "#ffd23f"]   # the four machines' cards


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def s(v):
    return int(v * SS)


def blurred(layer, factor=24):
    """A soft copy of `layer`: shrink it, then scale it back up."""
    w, h = layer.get_size()
    small = pygame.transform.smoothscale(layer, (max(1, w // factor), max(1, h // factor)))
    return pygame.transform.smoothscale(small, (w, h))


def soft(dst, draw_fn, factor=24):
    """Draw with `draw_fn` on a clear layer, blur it and blend it onto dst."""
    layer = pygame.Surface(dst.get_size(), pygame.SRCALPHA)
    draw_fn(layer)
    dst.blit(blurred(layer, factor), (0, 0))


def draw():
    img = pygame.Surface((N, N), pygame.SRCALPHA)
    art = pygame.Surface((N, N), pygame.SRCALPHA)

    # sky: deep violet to near black
    horizon = s(610)
    for y in range(N):
        t = y / horizon if y < horizon else 1.0
        c = lerp((40, 12, 84), (12, 6, 34), t ** 0.8) if y < horizon else (9, 5, 26)
        pygame.draw.line(art, c + (255,), (0, y), (N, y))

    # stars
    import random
    rnd = random.Random(7)
    stars = pygame.Surface((N, N), pygame.SRCALPHA)
    for _ in range(70):
        x, y = rnd.randrange(N), rnd.randrange(s(40), horizon - s(60))
        r = rnd.choice((SS, SS, 2 * SS))
        pygame.draw.circle(stars, (200, 190, 255, rnd.randrange(90, 220)), (x, y), r)
    art.blit(stars, (0, 0))

    # sun with the classic cut stripes
    cx, cy, rad = N // 2, s(470), s(250)
    sun = pygame.Surface((N, N), pygame.SRCALPHA)
    top, bot = (255, 214, 92), (255, 60, 140)
    for y in range(cy - rad, cy + rad):
        t = (y - (cy - rad)) / (2 * rad)
        half = int((rad * rad - (y - cy) ** 2) ** 0.5)
        pygame.draw.line(sun, lerp(top, bot, t) + (255,), (cx - half, y), (cx + half, y))
    gap_y, gap_h = cy + s(10), s(10)
    while gap_y < cy + rad:
        pygame.draw.rect(sun, (0, 0, 0, 0), (0, gap_y, N, gap_h))
        gap_y += s(44)
        gap_h += s(5)
    # glow behind the sun
    soft(art, lambda l: pygame.draw.circle(l, (255, 70, 150, 190), (cx, cy), rad + s(30)), 160)
    art.blit(sun, (0, 0))

    # ground below the horizon (covers the bottom of the sun)
    pygame.draw.rect(art, (9, 5, 26, 255), (0, horizon, N, N - horizon))

    # perspective grid
    grid = (255, 70, 200)
    vx = N // 2
    for i in range(-14, 15):
        x_bottom = vx + i * s(150)
        pygame.draw.line(art, grid + (200,), (vx + i * s(18), horizon), (x_bottom, N), s(4))
    y, step = horizon, s(14)
    while y < N:
        pygame.draw.line(art, grid + (200,), (0, int(y)), (N, int(y)), s(4))
        step *= 1.38
        y += step
    pygame.draw.line(art, (255, 150, 230, 255), (0, horizon), (N, horizon), s(7))

    # play arrow in the middle of the sun
    tri_c = (cx + s(18), cy - s(10))
    h = s(150)
    pts = [(tri_c[0] - h * 0.55, tri_c[1] - h * 0.62),
           (tri_c[0] - h * 0.55, tri_c[1] + h * 0.62),
           (tri_c[0] + h * 0.70, tri_c[1])]
    shadow = [(x + s(10), y + s(14)) for x, y in pts]
    soft(art, lambda l: pygame.draw.polygon(l, (70, 0, 60, 170), shadow), 40)
    pygame.draw.polygon(art, (255, 255, 255, 255), pts)

    # the four machines as dots on the ground
    dot_y = s(830)
    xs = [N // 2 + int((i - 1.5) * s(150)) for i in range(len(ACCENTS))]

    def dot_glow(l):
        for x, a in zip(xs, ACCENTS):
            pygame.draw.circle(l, rgb(a) + (230,), (x, dot_y), s(52))
    soft(art, dot_glow, 96)
    hi = pygame.Surface((N, N), pygame.SRCALPHA)
    for x, a in zip(xs, ACCENTS):
        pygame.draw.circle(art, rgb(a) + (255,), (x, dot_y), s(40))
        pygame.draw.circle(hi, (255, 255, 255, 150), (x - s(12), dot_y - s(14)), s(11))
    art.blit(hi, (0, 0))

    # rounded-square mask (macOS icon grid: 824 px body inside 1024)
    body = pygame.Rect(s(100), s(100), s(824), s(824))
    mask = pygame.Surface((N, N), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), body, border_radius=s(185))
    scaled = pygame.transform.smoothscale(art, body.size)
    framed = pygame.Surface((N, N), pygame.SRCALPHA)
    framed.blit(scaled, body.topleft)
    framed.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    # thin light rim
    rim = pygame.Surface((N, N), pygame.SRCALPHA)
    pygame.draw.rect(rim, (255, 150, 230, 110), body, s(3), border_radius=s(185))
    framed.blit(rim, (0, 0))
    # soft drop shadow
    soft(img, lambda l: pygame.draw.rect(l, (0, 0, 0, 120), body.move(0, s(12)),
                                         border_radius=s(185)), 96)
    img.blit(framed, (0, 0))
    return pygame.transform.smoothscale(img, (1024, 1024))


def png_bytes(surf):
    buf = io.BytesIO()
    pygame.image.save(surf, buf, "icon.png")
    return buf.getvalue()


def write_ico(icon, path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    """An .ico with PNG-compressed images (Windows Vista and later)."""
    blobs = [png_bytes(pygame.transform.smoothscale(icon, (n, n))) for n in sizes]
    out = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    for n, b in zip(sizes, blobs):
        out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(b), offset)
        offset += len(b)
    with open(path, "wb") as f:
        f.write(out + b"".join(blobs))


def write_icns(icon, path):
    if not shutil.which("iconutil"):
        print("iconutil not found (macOS only): skipping", path)
        return
    with tempfile.TemporaryDirectory() as d:
        iset = os.path.join(d, "icon.iconset")
        os.mkdir(iset)
        for n in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = n * scale
                name = "icon_%dx%d%s.png" % (n, n, "@2x" if scale == 2 else "")
                pygame.image.save(pygame.transform.smoothscale(icon, (px, px)),
                                  os.path.join(iset, name))
        subprocess.run(["iconutil", "-c", "icns", iset, "-o", path], check=True)


def main():
    pygame.init()
    icon = draw()
    os.makedirs(ASSETS, exist_ok=True)
    png = os.path.join(ASSETS, "icon.png")
    pygame.image.save(icon, png)
    write_ico(icon, os.path.join(ASSETS, "icon.ico"))
    write_icns(icon, os.path.join(ASSETS, "icon.icns"))
    print("wrote", os.path.normpath(png), "+ .ico, .icns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
