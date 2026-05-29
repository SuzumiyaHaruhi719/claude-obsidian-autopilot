"""Rebuild the Agent-History `_INDEX.md` map-of-content and backfill frontmatter.

Ported from `organize-vault.ps1`. Groups archived sessions by project (derived
from the git remote or the cwd leaf), orders projects by recent activity, tags
trivial (<2 user-turn) sessions as `stub`, and writes a single MOC index.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import util
from .config import ArchiveCfg

_FM_RE = re.compile(r"^﻿?---\r?\n([\s\S]*?)\r?\n---\r?\n?")
_FM_ORDER = ["session_id", "short_id", "project", "cwd", "started",
             "updated", "source", "summary", "tags"]


def _parse_fm(text: str) -> tuple[dict, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if km:
            fm[km.group(1)] = km.group(2)
    return fm, text[m.end():]


def _serialize_fm(fm: dict) -> str:
    out = ["---"]
    seen = set()
    for k in _FM_ORDER:
        if k in fm:
            out.append(f"{k}: {fm[k]}")
            seen.add(k)
    for k, v in fm.items():
        if k not in seen:
            out.append(f"{k}: {v}")
    out.append("---\n")
    return "\n".join(out)


def _derive_project(cwd: str) -> str:
    if not cwd:
        return "unknown"
    p = Path(cwd)
    if p.exists():
        try:
            r = subprocess.run(["git", "-C", str(p), "remote", "get-url", "origin"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                leaf = re.split(r"[/:]", r.stdout.strip().removesuffix(".git"))[-1]
                if leaf:
                    return leaf
        except (OSError, subprocess.SubprocessError):
            pass
    return p.name or "unknown"


def _scan_jsonl(jsonl: Path):
    first_prompt, user_turns = "", 0
    if not jsonl.exists():
        return first_prompt, user_turns
    for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("type") != "user":
            continue
        content = (e.get("message") or {}).get("content")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text":
                    text = b.get("text", "")
                    break
        text = re.sub(r"<system-reminder>[\s\S]*?</system-reminder>", "", text).strip()
        if text:
            user_turns += 1
            if not first_prompt:
                first_prompt = text
    return first_prompt, user_turns


def _truncate_line(s: str, n: int = 120) -> str:
    s = re.sub(r"\s{2,}", " ", s.replace("\n", " ").replace("\r", " ")).strip()
    if len(s) > n:
        s = s[:n - 1] + "…"
    if re.search(r'[:#"]', s) or s[:1] in "->|":
        s = '"' + s.replace('"', '\\"') + '"'
    return s


def rebuild(cfg: ArchiveCfg, force: bool = False, throttle_sec: int = 1800) -> str:
    if not cfg.enabled or not cfg.dir or not cfg.dir.exists():
        return "archive dir absent"
    if not force and util.throttled("organize.last", throttle_sec):
        return "throttled"
    util.touch("organize.last")

    entries = []
    for md in sorted(cfg.dir.glob("*.md")):
        if md.name == "_INDEX.md":
            continue
        base = md.stem
        jsonl = cfg.dir / f"{base}.raw.jsonl"
        fm, body = _parse_fm(util.read_text(md))
        changed = False

        short_id = base.split("_")[-1] if "_" in base else ""
        if short_id and "short_id" not in fm:
            fm["short_id"] = short_id; changed = True
        if not fm.get("project"):
            fm["project"] = _derive_project(fm.get("cwd", "")); changed = True

        first, turns = _scan_jsonl(jsonl)
        if not fm.get("summary") and first:
            fm["summary"] = _truncate_line(first); changed = True

        tags = []
        raw_tags = fm.get("tags", "")
        if raw_tags:
            inner = raw_tags.strip().strip("[]")
            tags = [t.strip().strip("\"'") for t in inner.split(",") if t.strip()]
        has_stub = "stub" in tags
        if turns < 2 and not has_stub:
            tags.append("stub"); changed = True
        elif turns >= 2 and has_stub:
            tags = [t for t in tags if t != "stub"]; changed = True
        if tags:
            fm["tags"] = "[" + ", ".join(tags) + "]"

        if changed:
            util.write_text(md, _serialize_fm(fm) + body)

        entries.append({
            "base": base, "project": fm.get("project", "unknown"),
            "short_id": fm.get("short_id", short_id),
            "summary": (fm.get("summary", "") or "").strip('"'),
            "mtime": md.stat().st_mtime,
            "date": base.split("_")[0] if "_" in base else "",
            "stub": "stub" in tags,
        })

    # Group by project, order projects by most-recent activity.
    by_project: dict[str, list] = {}
    for e in entries:
        by_project.setdefault(e["project"], []).append(e)
    order = sorted(by_project.items(),
                   key=lambda kv: max(x["mtime"] for x in kv[1]), reverse=True)

    out = ["---", "tags: [agent-history, index]",
           f"updated: {util.now_local_str()}", "---", "",
           "# Agent History — Map of Content", "",
           f"_{len(entries)} sessions across {len(order)} projects. "
           f"Last refreshed {util.now_local_str()}. "
           "Sessions tagged `stub` had fewer than 2 user turns._", ""]
    for project, sessions in order:
        out += [f"## {project}", ""]
        for e in sorted(sessions, key=lambda x: x["mtime"], reverse=True):
            summary = f" — {e['summary']}" if e["summary"] else ""
            stub = " `[stub]`" if e["stub"] else ""
            out.append(f"- {e['date']} · `{e['short_id']}`{stub}{summary} — [[{e['base']}]]")
        out.append("")

    util.write_text(cfg.dir / "_INDEX.md", "\n".join(out))
    util.log("organize", f"rebuilt index: {len(entries)} sessions, {len(order)} projects")
    return f"indexed {len(entries)} sessions"
