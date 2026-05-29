#!/usr/bin/env python3
"""Render the README hero animation: an Obsidian knowledge graph forming like
neural synapses as Claude works.

Nodes (vault notes) fire in one by one; edges (wiki-links) connect via a cyan
synapse pulse that travels from source to target, leaving a glowing trace —
then the whole graph settles into ambient neural activity and loops.

Dev-only tool. Needs Pillow + numpy (not part of the skill runtime). Frames are
rendered with 2x supersampling for crisp glow, then ffmpeg builds a dithered,
palette-optimized GIF:

    python docs/make_demo.py
    # writes docs/frames/*.png, then (if ffmpeg present) docs/demo.gif
"""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# --------------------------------------------------------------------------- #
# Canvas
# --------------------------------------------------------------------------- #
W, H, SS = 900, 506, 2
RW, RH = W * SS, H * SS
N_FRAMES, FPS = 96, 18

BG_TOP = (10, 12, 22)
BG_BOT = (24, 18, 38)
VIOLET = (168, 85, 247)     # node body
HOT = (236, 232, 255)       # node core
CYAN = (34, 211, 238)       # synapse pulse
EDGE = (120, 70, 190)       # connected edge

HERE = Path(__file__).resolve().parent
FRAMES = HERE / "frames"

# --------------------------------------------------------------------------- #
# Graph (normalized coords; t = progress 0..1 when it appears / connects)
# --------------------------------------------------------------------------- #
NODES = {
    "index":    (0.50, 0.50, 15, "00-Index",     0.00),
    "arch":     (0.33, 0.29, 10, "Architecture", 0.10),
    "build":    (0.67, 0.27, 10, "Build & Test", 0.14),
    "glossary": (0.45, 0.20,  8, "Glossary",     0.18),
    "riskmap":  (0.59, 0.15,  8, "Risk-Map",     0.24),
    "auth":     (0.20, 0.54, 10, "auth",         0.20),
    "api":      (0.30, 0.73, 10, "api",          0.26),
    "ui":       (0.50, 0.81,  9, "ui",           0.34),
    "db":       (0.71, 0.64, 10, "db",           0.30),
    "cache":    (0.81, 0.49,  9, "cache",        0.40),
    "ocr":      (0.12, 0.67,  9, "ocr",          0.62),
    "parser":   (0.85, 0.69,  9, "parser",       0.66),
    "sess1":    (0.13, 0.37,  7, "session-1",    0.46),
    "sess2":    (0.87, 0.34,  7, "session-2",    0.58),
    "bugfix":   (0.62, 0.85,  8, "bug-fix",      0.52),
    "guard":    (0.75, 0.86,  8, "guard",        0.72),
}
EDGES = [
    ("index", "arch", 0.12), ("index", "build", 0.16), ("index", "glossary", 0.20),
    ("index", "riskmap", 0.26), ("arch", "auth", 0.24), ("auth", "api", 0.30),
    ("api", "ui", 0.38), ("index", "ui", 0.36), ("build", "db", 0.32),
    ("build", "cache", 0.42), ("db", "cache", 0.45), ("arch", "sess1", 0.48),
    ("ui", "bugfix", 0.54), ("riskmap", "sess2", 0.60), ("build", "sess2", 0.61),
    ("arch", "ocr", 0.64), ("api", "ocr", 0.65), ("db", "parser", 0.68),
    ("bugfix", "guard", 0.74), ("parser", "guard", 0.73),
]
CAPTIONS = [
    (0.00, "Claude reads the vault"),
    (0.22, "edits the code"),
    (0.45, "writes the note in the same turn"),
    (0.68, "links related sessions"),
    (0.86, "the vault stays the source of truth"),
]


def _font(size):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_LABEL = _font(int(11 * SS))
F_TITLE = _font(int(15 * SS))
F_CAP = _font(int(20 * SS))


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def px(node):
    x, y, *_ = NODES[node]
    return x * RW, y * RH


def background():
    col = np.zeros((RH, RW, 3), np.float32)
    for c in range(3):
        col[:, :, c] = np.linspace(BG_TOP[c], BG_BOT[c], RH)[:, None]
    # radial vignette
    yy, xx = np.mgrid[0:RH, 0:RW]
    d = np.sqrt(((xx - RW / 2) / (RW / 2)) ** 2 + ((yy - RH / 2) / (RH / 2)) ** 2)
    col *= (1 - 0.45 * np.clip(d - 0.2, 0, 1))[:, :, None]
    return Image.fromarray(np.clip(col, 0, 255).astype(np.uint8), "RGB")


BG = background()


def scaled(color, k):
    return tuple(int(max(0, min(255, c * k))) for c in color)


def render_frame(f: int) -> Image.Image:
    p = f / (N_FRAMES - 1)
    t = f / FPS

    glow = Image.new("RGB", (RW, RH), 0)            # blurred later -> halo
    gd = ImageDraw.Draw(glow)
    sharp = BG.copy()                                # crisp cores on top
    sd = ImageDraw.Draw(sharp)
    labels = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    ld = ImageDraw.Draw(labels)

    # ---- edges + synapse pulses ----
    for a, b, tc in EDGES:
        if p < tc:
            continue
        ax, ay = px(a)
        bx, by = px(b)
        win = 8 / N_FRAMES                           # connect animation window
        prog = (p - tc) / win
        if prog < 1:                                 # forming: line ramps in
            grow = smooth(prog)
            ex, ey = lerp(ax, bx, grow), lerp(ay, by, grow)
            gd.line([(ax, ay), (ex, ey)], fill=scaled(EDGE, 0.9), width=SS)
            # traveling synapse head
            hx, hy = lerp(ax, bx, grow), lerp(ay, by, grow)
            gd.ellipse([hx - 6 * SS, hy - 6 * SS, hx + 6 * SS, hy + 6 * SS], fill=CYAN)
            sd.ellipse([hx - 2 * SS, hy - 2 * SS, hx + 2 * SS, hy + 2 * SS], fill=HOT)
        else:                                        # settled: dim line + ambient firing
            gd.line([(ax, ay), (bx, by)], fill=scaled(EDGE, 0.5), width=SS)
            sd.line([(ax, ay), (bx, by)], fill=scaled(EDGE, 0.7), width=1)
            phase = (t * 0.6 + hash((a, b)) % 100 / 100.0) % 1.0
            if phase < 0.5:                          # a pulse crosses the synapse
                q = smooth(phase / 0.5)
                hx, hy = lerp(ax, bx, q), lerp(ay, by, q)
                fade = math.sin(phase / 0.5 * math.pi)
                gd.ellipse([hx - 5 * SS, hy - 5 * SS, hx + 5 * SS, hy + 5 * SS],
                           fill=scaled(CYAN, fade))

    # ---- nodes ----
    for name, (nx, ny, size, label, ta) in NODES.items():
        if p < ta:
            continue
        x, y = nx * RW, ny * RH
        r = size * SS
        age = (p - ta) * N_FRAMES                    # frames since appearance
        breathe = 0.78 + 0.22 * math.sin(t * 2.2 + hash(name) % 7)
        # appearance flash + expanding ring
        if age < 10:
            fl = 1 - age / 10
            ring = r + (1 - fl) * 22 * SS
            gd.ellipse([x - ring, y - ring, x + ring, y + ring], outline=scaled(CYAN, fl))
            breathe = lerp(1.4, breathe, age / 10)
        gd.ellipse([x - r * 2.4, y - r * 2.4, x + r * 2.4, y + r * 2.4],
                   fill=scaled(VIOLET, 0.5 * breathe))
        gd.ellipse([x - r, y - r, x + r, y + r], fill=scaled(VIOLET, breathe))
        sd.ellipse([x - r, y - r, x + r, y + r], fill=scaled(VIOLET, breathe))
        cr = r * 0.45
        sd.ellipse([x - cr, y - cr, x + cr, y + cr], fill=HOT)
        # label fades in just after the node
        la = max(0.0, min(1.0, (age - 4) / 8))
        if la > 0:
            ld.text((x + r + 4 * SS, y - 7 * SS), label,
                    font=F_LABEL, fill=(205, 200, 225, int(200 * la)))

    # ---- compose: blurred glow (screen) + sharp cores + labels ----
    halo = glow.filter(ImageFilter.GaussianBlur(SS * 5))
    frame = ImageChops.screen(sharp, halo)
    frame = ImageChops.screen(frame, glow.filter(ImageFilter.GaussianBlur(SS * 2)))
    frame = Image.alpha_composite(frame.convert("RGBA"), labels).convert("RGB")

    # ---- text overlay (title + caption) ----
    td = ImageDraw.Draw(frame)
    td.text((20 * SS, 16 * SS), "Claude Autopilot for Obsidian", font=F_TITLE, fill=(190, 150, 245))
    td.text((20 * SS, 34 * SS), "knowledge graph forming as Claude works",
            font=_font(int(10 * SS)), fill=(120, 120, 150))
    cap = CAPTIONS[0][1]
    for ct, text in CAPTIONS:
        if p >= ct:
            cap = text
    cd = ImageDraw.Draw(frame)
    bbox = cd.textbbox((0, 0), cap, font=F_CAP)
    cw = bbox[2] - bbox[0]
    cd.text(((RW - cw) / 2, RH - 42 * SS), cap, font=F_CAP, fill=(225, 220, 245))

    return frame.resize((W, H), Image.LANCZOS)


def main():
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)
    print(f"Rendering {N_FRAMES} frames at {RW}x{RH} (SS={SS})...")
    for f in range(N_FRAMES):
        render_frame(f).save(FRAMES / f"frame_{f:04d}.png")
    print(f"Frames -> {FRAMES}")

    ffmpeg = shutil.which("ffmpeg")
    out = HERE / "demo.gif"
    if not ffmpeg:
        print("ffmpeg not found; frames written. Build the GIF manually.")
        return
    # Hold the fully-formed graph for 5s (tpad clones the last frame) so it can
    # be read before the loop restarts.
    vf = ("tpad=stop_mode=clone:stop_duration=5,"
          "split[s0][s1];[s0]palettegen=max_colors=160:stats_mode=full[p];"
          "[s1][p]paletteuse=dither=sierra2_4a")
    subprocess.run([ffmpeg, "-y", "-framerate", str(FPS), "-i",
                    str(FRAMES / "frame_%04d.png"), "-vf", vf,
                    "-loop", "0", str(out)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"GIF -> {out}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
