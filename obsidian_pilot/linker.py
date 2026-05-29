"""Cross-link related sessions inside each archived conversation note.

Ported from `link-related-sessions.ps1`. Builds a lightweight fingerprint per
session (referenced file paths + top keywords + cwd), scores peers against the
current session, and writes the top matches into a marker-delimited
`## Related Sessions` block — idempotently, so re-runs replace rather than
duplicate. CJK text contributes via shared file paths since the tokenizer is
ASCII-word based.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import util
from .config import ArchiveCfg

START = "<!-- related:start -->"
END = "<!-- related:end -->"
_PATH_RE = re.compile(r"(?i)[a-z]:\\[\w\-.\\]+|/[\w\-./]+\.[a-z0-9]{1,6}")
_WORD_RE = re.compile(r"[a-z][a-z0-9_\-]{3,}")
_STOP = set("""the a an and or but if then of to in on for with is are was were be been
it this that these those you we they he she as at by from my your our can could should
would will do does did have has had not no yes so use using please want need make get run
code file files""".split())


def _fingerprint(jsonl: Path, cwd: str) -> dict:
    files: set[str] = set()
    counts: dict[str, int] = {}
    if jsonl and jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") not in ("user", "assistant"):
                continue
            content = (e.get("message") or {}).get("content")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        text += "\n" + str(b.get("text", ""))
                    elif b.get("type") == "tool_use" and b.get("input"):
                        text += "\n" + json.dumps(b["input"], ensure_ascii=False)
            if not text:
                continue
            for m in _PATH_RE.findall(text):
                files.add(m)
            for w in _WORD_RE.findall(text.lower()):
                if w not in _STOP:
                    counts[w] = counts.get(w, 0) + 1
    top = sorted(counts, key=counts.get, reverse=True)[:25]
    return {"cwd": cwd, "files": sorted(files), "keywords": top,
            "mtime": jsonl.stat().st_mtime if (jsonl and jsonl.exists()) else 0}


def _score(cur: dict, peer: dict) -> float:
    s = 0.0
    if peer["cwd"] and cur["cwd"] and peer["cwd"].lower() == cur["cwd"].lower():
        s += 5.0
    cur_files = {f.lower() for f in cur["files"]}
    cur_kw = {k.lower() for k in cur["keywords"]}
    s += min(sum(f.lower() in cur_files for f in peer["files"]), 8) * 1.5
    s += min(sum(k.lower() in cur_kw for k in peer["keywords"]), 10) * 0.5
    return s


def link(session_id: str, cwd: str, cfg: ArchiveCfg) -> str:
    if not cfg.enabled or not cfg.dir or not session_id:
        return "disabled"
    short = session_id[:8]
    cur_md = next(iter(cfg.dir.glob(f"*_{short}.md")), None)
    if not cur_md:
        return "current note not archived yet"
    cur_jsonl = next(iter(cfg.dir.glob(f"*_{short}.raw.jsonl")), None)
    cur_fp = _fingerprint(cur_jsonl, cwd)

    scored = []
    for jsonl in cfg.dir.glob("*.raw.jsonl"):
        sid = jsonl.name.replace(".raw.jsonl", "").split("_")[-1]
        if sid == short:
            continue
        peer_md = next(iter(cfg.dir.glob(f"*_{sid}.md")), None)
        if not peer_md:
            continue
        peer_cwd = ""
        for h in util.read_text(peer_md).splitlines()[:30]:
            hm = re.match(r"^cwd:\s*(.+)$", h)
            if hm:
                peer_cwd = hm.group(1).strip()
                break
        sc = _score(cur_fp, _fingerprint(jsonl, peer_cwd))
        if sc > 0:
            scored.append((sc, jsonl.stat().st_mtime, peer_md.stem))

    scored.sort(reverse=True)
    top = scored[:5]

    lines = [START, "## Related Sessions", ""]
    if top:
        lines += [f"- [[{stem}]] (score {round(sc, 1)})" for sc, _, stem in top]
    else:
        lines.append("_No related sessions yet._")
    lines += ["", END]
    block = "\n".join(lines)

    md = util.read_text(cur_md)
    pat = re.compile(re.escape(START) + r"[\s\S]*?" + re.escape(END))
    md = pat.sub(lambda _m: block, md, count=1) if pat.search(md) \
        else md.rstrip("\n") + "\n\n" + block + "\n"
    util.write_text(cur_md, md)
    return f"linked {len(top)} related sessions"
