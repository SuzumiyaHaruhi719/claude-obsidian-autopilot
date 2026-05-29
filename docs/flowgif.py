#!/usr/bin/env python3
"""Animated flow-diagram engine — renders the README's flowcharts as looping
GIFs in the same neural look as the hero: violet glowing boxes wired by directed
edges, with cyan synapse pulses that travel along the arrows in sequence, so the
flow visibly "executes" and then loops.

    python docs/flowgif.py            # render every diagram -> docs/*.gif
    python docs/flowgif.py workflow   # render just one

Dev-only. Needs Pillow + numpy + ffmpeg.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SS = 2
HERE = Path(__file__).resolve().parent

BG_TOP = (10, 12, 22)
BG_BOT = (24, 18, 38)
VIOLET = (168, 85, 247)
HOT = (236, 232, 255)
CYAN = (34, 211, 238)
EDGE = (118, 78, 180)
TEXT = (228, 224, 246)
GREEN = (52, 211, 153)
RED = (244, 113, 116)

KIND_COLOR = {"node": VIOLET, "accent": CYAN, "good": GREEN, "danger": RED,
              "decision": (192, 132, 252)}


def _font(size, *names):
    for name in names + ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def scaled(c, k):
    return tuple(int(max(0, min(255, v * k))) for v in c)


def background(RW, RH, focus):
    col = np.zeros((RH, RW, 3), np.float32)
    for c in range(3):
        col[:, :, c] = np.linspace(BG_TOP[c], BG_BOT[c], RH)[:, None]
    yy, xx = np.mgrid[0:RH, 0:RW]
    d = np.sqrt(((xx - RW * focus[0]) / (RW * 0.75)) ** 2 +
                ((yy - RH * focus[1]) / (RH * 0.8)) ** 2)
    col *= (1 - 0.4 * np.clip(d - 0.15, 0, 1))[:, :, None]
    return Image.fromarray(np.clip(col, 0, 255).astype(np.uint8), "RGB")


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def border_point(box, toward):
    """Point where the line center->toward exits the box rectangle."""
    cx, cy, hw, hh = box["px"]
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    tx = hw / abs(dx) if dx else 1e9
    ty = hh / abs(dy) if dy else 1e9
    t = min(tx, ty)
    return cx + dx * t, cy + dy * t


def draw_arrow(d, p, q, color, width):
    d.line([p, q], fill=color, width=width)
    ang = math.atan2(q[1] - p[1], q[0] - p[0])
    s = 7 * SS
    for off in (2.6, -2.6):
        d.line([q, (q[0] - s * math.cos(ang - off / 6), q[1] - s * math.sin(ang - off / 6))],
               fill=color, width=width)


def dashed(d, p, q, color, width, dash=10 * SS, gap=8 * SS):
    total = math.hypot(q[0] - p[0], q[1] - p[1])
    if total == 0:
        return
    ux, uy = (q[0] - p[0]) / total, (q[1] - p[1]) / total
    s = 0.0
    while s < total:
        e = min(s + dash, total)
        d.line([(p[0] + ux * s, p[1] + uy * s), (p[0] + ux * e, p[1] + uy * e)],
               fill=color, width=width)
        s += dash + gap


def render(name, spec):
    W, H = spec["size"]
    RW, RH = W * SS, H * SS
    N, FPS = spec.get("frames", 54), spec.get("fps", 16)
    bg = background(RW, RH, spec.get("focus", (0.5, 0.5)))

    boxes = {b["id"]: dict(b) for b in spec["boxes"]}
    for b in boxes.values():
        cx, cy, w, h = b["cx"] * RW, b["cy"] * RH, b["w"] * RW / 2, b["h"] * RH / 2
        b["px"] = (cx, cy, w, h)
    edges = spec["edges"]

    maxord = max((e.get("order", i) for i, e in enumerate(edges)), default=0)
    DUR = 0.13
    def tstart(e, i):
        o = e.get("order", i)
        return 0.08 + (0.74 * o / maxord if maxord else 0.0)

    appear = {bid: 1.0 for bid in boxes}
    for i, e in enumerate(edges):
        ts = tstart(e, i)
        appear[e["a"]] = min(appear[e["a"]], ts)
        appear[e["b"]] = min(appear[e["b"]], ts + DUR)
    if appear:
        first = min(appear.values())
        for k in appear:
            if appear[k] <= first + 1e-6:
                appear[k] = 0.04

    f_lab = _font(int(spec.get("label", 11) * SS))
    f_edge = _font(int(9 * SS))
    f_title = _font(int(15 * SS), "segoeuib.ttf", "arialbd.ttf")

    frames_dir = HERE / "_fl" / name
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    for f in range(N):
        p = f / (N - 1)
        t = f / FPS
        glow = Image.new("RGB", (RW, RH), 0)
        gd = ImageDraw.Draw(glow)
        sharp = bg.copy()
        sd = ImageDraw.Draw(sharp)

        # ---- edges ----
        for i, e in enumerate(edges):
            a, b = boxes[e["a"]], boxes[e["b"]]
            ac, bc = (a["px"][0], a["px"][1]), (b["px"][0], b["px"][1])
            pa = border_point(a, bc)
            pb = border_point(b, ac)
            ts = tstart(e, i)
            if p < ts:
                continue
            prog = (p - ts) / DUR
            col = scaled(EDGE, 0.85)
            if e.get("dashed"):
                dashed(gd, pa, pb, scaled(EDGE, 0.55), SS)
                dashed(sd, pa, pb, scaled(EDGE, 0.7), 1)
            else:
                if prog < 1:
                    hx = pa[0] + (pb[0] - pa[0]) * smooth(prog)
                    hy = pa[1] + (pb[1] - pa[1]) * smooth(prog)
                    gd.line([pa, (hx, hy)], fill=col, width=SS)
                    gd.ellipse([hx - 6 * SS, hy - 6 * SS, hx + 6 * SS, hy + 6 * SS], fill=CYAN)
                    sd.ellipse([hx - 2 * SS, hy - 2 * SS, hx + 2 * SS, hy + 2 * SS], fill=HOT)
                else:
                    draw_arrow(gd, pa, pb, scaled(EDGE, 0.6), SS)
                    draw_arrow(sd, pa, pb, scaled(EDGE, 0.8), 1)
                    ph = (t * 0.55 + (i * 0.27)) % 1.0
                    if ph < 0.5:
                        q = smooth(ph / 0.5)
                        hx, hy = pa[0] + (pb[0] - pa[0]) * q, pa[1] + (pb[1] - pa[1]) * q
                        gd.ellipse([hx - 5 * SS, hy - 5 * SS, hx + 5 * SS, hy + 5 * SS],
                                   fill=scaled(CYAN, math.sin(ph / 0.5 * math.pi)))
            if e.get("label") and prog > 0.4:
                mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
                sd.text((mx + 4 * SS, my - 12 * SS), e["label"], font=f_edge, fill=(150, 150, 180))

        # ---- boxes ----
        for bid, b in boxes.items():
            if p < appear[bid]:
                continue
            cx, cy, hw, hh = b["px"]
            color = KIND_COLOR.get(b.get("kind", "node"), VIOLET)
            age = (p - appear[bid]) * N
            br = 0.78 + 0.22 * math.sin(t * 2.0 + hash(bid) % 7)
            if age < 9:
                fl = 1 - age / 9
                ring = 10 * SS * (1 - fl)
                gd.rounded_rectangle([cx - hw - ring, cy - hh - ring, cx + hw + ring, cy + hh + ring],
                                     radius=14 * SS, outline=scaled(CYAN, fl), width=SS)
                br = max(br, 1.2 * fl + br * (1 - fl))
            rad = 13 * SS
            gd.rounded_rectangle([cx - hw, cy - hh, cx + hw, cy + hh], radius=rad,
                                 fill=scaled(color, 0.42 * br))
            sd.rounded_rectangle([cx - hw, cy - hh, cx + hw, cy + hh], radius=rad,
                                 fill=(34, 26, 54), outline=scaled(color, br), width=2 * SS)
            # text (centered, multi-line)
            lines = b["text"].split("\n")
            lh = (f_lab.getbbox("Ay")[3] - f_lab.getbbox("Ay")[1]) + 4 * SS
            ty = cy - lh * len(lines) / 2
            for ln in lines:
                w = sd.textlength(ln, font=f_lab)
                sd.text((cx - w / 2, ty), ln, font=f_lab, fill=TEXT)
                ty += lh

        halo = glow.filter(ImageFilter.GaussianBlur(SS * 5))
        frame = ImageChops.screen(sharp, halo)
        frame = ImageChops.screen(frame, glow.filter(ImageFilter.GaussianBlur(SS * 2)))
        fd = ImageDraw.Draw(frame)
        if spec.get("title"):
            fd.text((22 * SS, 16 * SS), spec["title"], font=f_title, fill=(190, 150, 245))
        for lx, ly, txt, sz, col in spec.get("captions", []):
            fd.text((lx * RW, ly * RH), txt, font=_font(int(sz * SS), "segoeuib.ttf"), fill=col)
        if p > 0.88:
            frame = Image.blend(frame, bg, smooth((p - 0.88) / 0.12))
        frame.resize((W, H), Image.LANCZOS).save(frames_dir / f"f_{f:04d}.png")

    out = HERE / f"{name}.gif"
    vf = ("split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=full[p];"
          "[s1][p]paletteuse=dither=sierra2_4a")
    subprocess.run(["ffmpeg", "-y", "-framerate", str(FPS), "-i",
                    str(frames_dir / "f_%04d.png"), "-vf", vf, "-loop", "0", str(out)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(frames_dir)
    print(f"{name}.gif  ({out.stat().st_size // 1024} KB)")


# --------------------------------------------------------------------------- #
# Diagram specifications
# --------------------------------------------------------------------------- #
def _b(id, cx, cy, text, kind="node", w=0.21, h=0.15):
    return {"id": id, "cx": cx, "cy": cy, "text": text, "kind": kind, "w": w, "h": h}


DIAGRAMS = {
    "layers": {
        "size": (900, 440), "focus": (0.85, 0.5),
        "captions": [(0.04, 0.12, "Semantic layer — Claude", 12, (200, 170, 250)),
                     (0.04, 0.60, "Automatic layer — hooks", 12, (120, 200, 220))],
        "boxes": [
            _b("s1", 0.20, 0.30, "Read\nthe note", w=0.17, h=0.17),
            _b("s2", 0.42, 0.30, "Write\nthe note", w=0.17, h=0.17),
            _b("s3", 0.64, 0.30, "Commit\nVault-updated:", w=0.19, h=0.17),
            _b("a1", 0.16, 0.78, "Pull", "accent", w=0.13, h=0.16),
            _b("a2", 0.34, 0.78, "Archive", "accent", w=0.14, h=0.16),
            _b("a3", 0.53, 0.78, "Index +\nlink", "accent", w=0.15, h=0.16),
            _b("a4", 0.71, 0.78, "Push", "accent", w=0.13, h=0.16),
            _b("v", 0.90, 0.54, "Vault\nsource of\ntruth", "good", w=0.16, h=0.30),
        ],
        "edges": [
            {"a": "s1", "b": "s2", "order": 0}, {"a": "s2", "b": "s3", "order": 1},
            {"a": "s3", "b": "v", "order": 2},
            {"a": "a1", "b": "a2", "order": 0}, {"a": "a2", "b": "a3", "order": 1},
            {"a": "a3", "b": "a4", "order": 2}, {"a": "a4", "b": "v", "order": 3},
        ],
    },
    "lifecycle": {
        "size": (900, 430), "title": "Automatic layer — lifecycle hooks",
        "boxes": [
            _b("p1", 0.20, 0.34, "Session\nstart", "accent", w=0.17, h=0.17),
            _b("p2", 0.50, 0.34, "Each\nprompt", "accent", w=0.17, h=0.17),
            _b("p3", 0.80, 0.34, "Session\nend", "accent", w=0.17, h=0.17),
            _b("a1", 0.20, 0.78, "Pull vault +\nrebuild index", w=0.22, h=0.18),
            _b("a2", 0.50, 0.78, "Smart-pull +\nlink sessions", w=0.22, h=0.18),
            _b("a3", 0.80, 0.78, "Archive chat +\noptional push", w=0.22, h=0.18),
        ],
        "edges": [
            {"a": "p1", "b": "p2", "order": 0}, {"a": "p2", "b": "p3", "order": 1},
            {"a": "p1", "b": "a1", "order": 0}, {"a": "p2", "b": "a2", "order": 1},
            {"a": "p3", "b": "a3", "order": 2},
        ],
    },
    "workflow": {
        "size": (920, 520), "title": "The one rule: code and notes change together",
        "boxes": [
            _b("q", 0.18, 0.28, "Vault for\nthis project?", "decision", w=0.20, h=0.18),
            _b("c", 0.50, 0.28, "Create it\npilot.py init", "accent", w=0.21, h=0.18),
            _b("r", 0.82, 0.28, "Read the\nnote first", w=0.20, h=0.18),
            _b("e", 0.82, 0.72, "Edit the\ncode", w=0.20, h=0.18),
            _b("w", 0.50, 0.72, "Write the note\nsame turn", w=0.22, h=0.18),
            _b("m", 0.18, 0.72, "Commit\nVault-updated:", w=0.21, h=0.18),
        ],
        "edges": [
            {"a": "q", "b": "c", "order": 0, "label": "if none"},
            {"a": "c", "b": "r", "order": 1}, {"a": "r", "b": "e", "order": 2},
            {"a": "e", "b": "w", "order": 3}, {"a": "w", "b": "m", "order": 4},
        ],
    },
    "init": {
        "size": (900, 420), "title": "python pilot.py init",
        "focus": (0.25, 0.5),
        "boxes": [
            _b("i", 0.16, 0.50, "init\n(in project)", "accent", w=0.18, h=0.22),
            _b("v", 0.62, 0.20, "<project>/obsidian\nvault skeleton", w=0.30, h=0.18),
            _b("a", 0.62, 0.50, "~/Documents\narchives (outside)", w=0.30, h=0.18),
            _b("c", 0.62, 0.80, "config: vault\nregistered", w=0.30, h=0.18),
        ],
        "edges": [
            {"a": "i", "b": "v", "order": 0}, {"a": "i", "b": "a", "order": 0},
            {"a": "i", "b": "c", "order": 0},
        ],
    },
    "obsidian-init": {
        "size": (940, 430), "title": "/obsidian-init — auto-document a codebase",
        "boxes": [
            _b("cmd", 0.13, 0.50, "/obsidian-init", "accent", w=0.17, h=0.20),
            _b("scan", 0.37, 0.50, "Claude reads\nthe codebase", w=0.20, h=0.22),
            _b("feat", 0.66, 0.27, "Features\nnotes", w=0.18, h=0.18),
            _b("mod", 0.66, 0.73, "Modules\nnotes", w=0.18, h=0.18),
            _b("idx", 0.89, 0.50, "Index +\nArchitecture\n+ Data-Flows", "good", w=0.18, h=0.26),
        ],
        "edges": [
            {"a": "cmd", "b": "scan", "order": 0}, {"a": "scan", "b": "feat", "order": 1},
            {"a": "scan", "b": "mod", "order": 1},
            {"a": "feat", "b": "mod", "order": 2, "label": "[[links]]"},
            {"a": "feat", "b": "idx", "order": 3}, {"a": "mod", "b": "idx", "order": 3},
        ],
    },
    "security": {
        "size": (960, 360), "title": "Security — archives stay local, secrets redacted",
        "boxes": [
            _b("t", 0.12, 0.45, "Conversation\ntranscript", w=0.17, h=0.26),
            _b("r", 0.34, 0.45, "Redact\nsecrets", "danger", w=0.15, h=0.26),
            _b("m", 0.54, 0.45, "Markdown\n+ JSONL", w=0.15, h=0.26),
            _b("l", 0.75, 0.45, "Stays\nLOCAL", "good", w=0.15, h=0.26),
            _b("g", 0.93, 0.45, "GitHub", "accent", w=0.12, h=0.22),
        ],
        "edges": [
            {"a": "t", "b": "r", "order": 0}, {"a": "r", "b": "m", "order": 1},
            {"a": "m", "b": "l", "order": 2},
            {"a": "l", "b": "g", "order": 3, "dashed": True, "label": "opt-in only"},
        ],
    },
}


if __name__ == "__main__":
    which = sys.argv[1:] or list(DIAGRAMS)
    for name in which:
        render(name, DIAGRAMS[name])
