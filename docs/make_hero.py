#!/usr/bin/env python3
"""Render the animated README hero banner (docs/hero.gif).

A wide title card: the project name + tagline + OS line on the left, a glowing
Obsidian-style synapse cluster on the right whose nodes breathe and whose edges
fire travelling cyan pulses — on a seamless loop (all motion is periodic in the
frame count, so frame 0 == frame N).

    python docs/make_hero.py     # writes docs/hero.gif

Dev-only. Needs Pillow + numpy + ffmpeg.
"""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H, SS = 1280, 460, 2
RW, RH = W * SS, H * SS
N_FRAMES, FPS = 48, 16

BG_TOP = (10, 12, 22)
BG_BOT = (26, 18, 42)
VIOLET = (168, 85, 247)
HOT = (236, 232, 255)
CYAN = (34, 211, 238)
EDGE = (120, 70, 190)

HERE = Path(__file__).resolve().parent

# Decorative graph clustered on the right; some nodes bleed off-canvas.
NODES = [
    (0.72, 0.50, 17), (0.86, 0.28, 11), (0.93, 0.58, 12), (0.78, 0.80, 10),
    (0.62, 0.30, 9), (0.66, 0.74, 9), (1.00, 0.40, 10), (0.84, 0.52, 8),
    (0.97, 0.82, 9), (0.58, 0.55, 7), (0.90, 0.12, 8),
]
EDGES = [
    (0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (1, 6), (2, 6), (2, 8),
    (1, 10), (3, 5), (0, 7), (7, 2), (4, 9), (5, 9), (3, 8),
]


def _font(size, *names):
    for name in names + ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def scaled(c, k):
    return tuple(int(max(0, min(255, v * k))) for v in c)


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def background():
    col = np.zeros((RH, RW, 3), np.float32)
    for c in range(3):
        col[:, :, c] = np.linspace(BG_TOP[c], BG_BOT[c], RH)[:, None]
    yy, xx = np.mgrid[0:RH, 0:RW]
    d = np.sqrt(((xx - RW * 0.8) / (RW * 0.7)) ** 2 + ((yy - RH / 2) / (RH * 0.8)) ** 2)
    col *= (1 - 0.4 * np.clip(d - 0.1, 0, 1))[:, :, None]
    return Image.fromarray(np.clip(col, 0, 255).astype(np.uint8), "RGB")


BG = background()
F_KICK = _font(int(15 * SS), "segoeuib.ttf", "arialbd.ttf")
F_TITLE = _font(int(50 * SS), "segoeuib.ttf", "arialbd.ttf")
F_TAG = _font(int(22 * SS))
F_OS = _font(int(18 * SS), "segoeuib.ttf", "arialbd.ttf")


def px(i):
    x, y, _ = NODES[i]
    return x * RW, y * RH


def text_layer():
    """The static left-hand text block, drawn once."""
    img = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lx = 70 * SS
    d.ellipse([lx, 70 * SS, lx + 16 * SS, 86 * SS], outline=CYAN, width=SS)
    d.text((lx + 26 * SS, 64 * SS), "CLAUDE CODE  ×  OBSIDIAN", font=F_KICK, fill=(150, 120, 210))
    d.text((lx, 92 * SS), "Claude Autopilot", font=F_TITLE, fill=(238, 232, 252))
    d.text((lx, 150 * SS), "for Obsidian", font=F_TITLE, fill=(238, 232, 252))
    d.text((lx, 232 * SS), "Your vault, kept as the single source of",
           font=F_TAG, fill=(176, 170, 200))
    d.text((lx, 262 * SS), "truth for your code — automatically.",
           font=F_TAG, fill=(176, 170, 200))
    d.rectangle([lx, 320 * SS, lx + 150 * SS, 323 * SS], fill=VIOLET)
    d.text((lx, 340 * SS), "macOS   ·   Linux   ·   Windows", font=F_OS, fill=(120, 200, 220))
    badge = "pure-Python  ·  zero-deps"
    bb = d.textbbox((0, 0), badge, font=F_KICK)
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    bx, by = lx, 380 * SS
    d.rounded_rectangle([bx, by, bx + bw + 24 * SS, by + bh + 16 * SS],
                        radius=10 * SS, outline=(120, 90, 170), width=SS)
    d.text((bx + 12 * SS, by + 7 * SS), badge, font=F_KICK, fill=(190, 160, 230))
    return img


TEXT = text_layer()


def render_frame(f):
    u = f / N_FRAMES  # 0..1 loop coordinate (periodic)
    glow = Image.new("RGB", (RW, RH), 0)
    gd = ImageDraw.Draw(glow)
    sharp = BG.copy()
    sd = ImageDraw.Draw(sharp)

    for k, (a, b) in enumerate(EDGES):
        ax, ay = px(a)
        bx, by = px(b)
        gd.line([(ax, ay), (bx, by)], fill=scaled(EDGE, 0.55), width=SS)
        sd.line([(ax, ay), (bx, by)], fill=scaled(EDGE, 0.7), width=1)
        # two pulses per loop, offset per edge -> seamless, lively
        ph = (u * 2 + k * 0.137) % 1.0
        if ph < 0.5:
            q = smooth(ph / 0.5)
            hx, hy = ax + (bx - ax) * q, ay + (by - ay) * q
            fade = math.sin(ph / 0.5 * math.pi)
            gd.ellipse([hx - 5 * SS, hy - 5 * SS, hx + 5 * SS, hy + 5 * SS], fill=scaled(CYAN, fade))

    for i, (nx, ny, size) in enumerate(NODES):
        x, y, r = nx * RW, ny * RH, size * SS
        br = 0.78 + 0.22 * math.sin(2 * math.pi * u + i)  # periodic breathe
        gd.ellipse([x - r * 2.6, y - r * 2.6, x + r * 2.6, y + r * 2.6], fill=scaled(VIOLET, 0.45 * br))
        gd.ellipse([x - r, y - r, x + r, y + r], fill=scaled(VIOLET, br))
        sd.ellipse([x - r, y - r, x + r, y + r], fill=scaled(VIOLET, br))
        cr = r * 0.45
        sd.ellipse([x - cr, y - cr, x + cr, y + cr], fill=HOT)

    halo = glow.filter(ImageFilter.GaussianBlur(SS * 6))
    img = ImageChops.screen(sharp, halo)
    img = ImageChops.screen(img, glow.filter(ImageFilter.GaussianBlur(SS * 2)))
    img = Image.alpha_composite(img.convert("RGBA"), TEXT).convert("RGB")
    return img.resize((W, H), Image.LANCZOS)


def main():
    frames = HERE / "_hero"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True)
    for f in range(N_FRAMES):
        render_frame(f).save(frames / f"f_{f:04d}.png")
    out = HERE / "hero.gif"
    vf = ("split[s0][s1];[s0]palettegen=max_colors=160:stats_mode=full[p];"
          "[s1][p]paletteuse=dither=sierra2_4a")
    subprocess.run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(frames / "f_%04d.png"),
                    "-vf", vf, "-loop", "0", str(out)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(frames)
    print(f"hero.gif  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
