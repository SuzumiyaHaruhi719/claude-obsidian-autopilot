"""Render a session transcript into readable Markdown (+ raw JSONL backup).

Ported from the original `save-conversation.ps1`, plus a key security upgrade:
**secret redaction**. The original pushed full tool-results — which routinely
contain API keys, tokens and file contents — straight to GitHub. Here archives
stay local by default (see gitsync's managed .gitignore) and, when
`redact_secrets` is on, common credential shapes are masked before writing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import util
from .config import ArchiveCfg

MAX_BLOCK = 4000  # truncate giant tool inputs/results, as the original did

# Conservative secret patterns — masked as «REDACTED:<kind>».
_SECRET_PATTERNS = [
    ("aws-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----[\s\S]*?-----END[^\n]*-----")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("generic-secret", re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{12,}")),
]


def redact(text: str) -> str:
    if not text:
        return text
    for kind, pat in _SECRET_PATTERNS:
        text = pat.sub(f"«REDACTED:{kind}»", text)
    return text


def _truncate(s: str) -> str:
    return s if len(s) <= MAX_BLOCK else s[:MAX_BLOCK] + "\n... [truncated]"


def _iter_entries(transcript: Path):
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _latest_todos(entries: list[dict]):
    todos = None
    for e in entries:
        if e.get("type") != "assistant":
            continue
        for block in (e.get("message", {}).get("content") or []):
            if isinstance(block, dict) and block.get("type") == "tool_use" \
               and block.get("name") == "TodoWrite":
                todos = (block.get("input") or {}).get("todos")
    return todos


def _render_block(block: dict, cfg: ArchiveCfg, out: list[str]) -> None:
    bt = block.get("type")
    if bt == "text":
        out.append(redact(block.get("text", "")) + "\n")
    elif bt == "thinking" and cfg.include_thinking:
        out.append("> [!note] Thinking")
        for ln in redact(block.get("thinking", "")).split("\n"):
            out.append(f"> {ln}")
        out.append("")
    elif bt == "tool_use":
        out.append(f"**Tool call: `{block.get('name')}`**\n")
        out.append("```json")
        try:
            j = json.dumps(block.get("input", {}), indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            j = "[unserializable input]"
        out.append(_truncate(redact(j)))
        out.append("```\n")
    elif bt == "tool_result":
        out.append("**Tool result:**\n")
        out.append("```")
        rc = block.get("content")
        if isinstance(rc, str):
            s = rc
        elif isinstance(rc, list):
            parts = [b.get("text", "") if isinstance(b, dict) and b.get("type") == "text"
                     else json.dumps(b, ensure_ascii=False) for b in rc]
            s = "\n".join(parts)
        else:
            s = json.dumps(rc, ensure_ascii=False)
        out.append(_truncate(redact(s)))
        out.append("```\n")


def save(transcript_path: str, session_id: str, cwd: str, cfg: ArchiveCfg) -> Path | None:
    """Write <archive>/<date>_<shortid>.md and .raw.jsonl. Returns the md path."""
    if not cfg.enabled or not cfg.dir:
        return None
    transcript = Path(transcript_path) if transcript_path else None
    if not transcript or not transcript.exists():
        return None

    cfg.dir.mkdir(parents=True, exist_ok=True)
    short = (session_id or "unknown")[:8]
    base = f"{util.today_str()}_{short}"
    md_path = cfg.dir / f"{base}.md"
    raw_path = cfg.dir / f"{base}.raw.jsonl"

    # Byte-perfect backup first (crash-resistant). Stays local — gitignored.
    try:
        raw_path.write_bytes(transcript.read_bytes())
    except OSError:
        pass

    entries = list(_iter_entries(transcript))
    out: list[str] = [
        "---",
        f"session_id: {session_id}",
        f"cwd: {cwd}",
        f"updated: {util.now_local_str()}",
        f"source: {transcript}",
        "tags: [claude-code, agent-history]",
        "---", "",
        f"# Agent Conversation — {util.today_str()} — {short}", "",
    ]

    todos = _latest_todos(entries)
    if todos:
        out += ["## Session TODO List (final state)", ""]
        mark = {"completed": "x", "in_progress": "/"}
        for t in todos:
            out.append(f"- [{mark.get(t.get('status'), ' ')}] "
                       f"{t.get('content') or t.get('activeForm') or '(no content)'}")
        out.append("")

    turn = 0
    for e in entries:
        if e.get("type") not in ("user", "assistant"):
            continue
        turn += 1
        msg = e.get("message") or {}
        ts = f" @ {e['timestamp']}" if e.get("timestamp") else ""
        out += [f"## Turn {turn} — {e['type']}{ts}", ""]
        content = msg.get("content")
        if isinstance(content, str):
            out.append(redact(content) + "\n")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    _render_block(block, cfg, out)

    util.write_text(md_path, "\n".join(out))
    return md_path
