"""Scaffold a fresh Obsidian vault skeleton inside a project.

`pilot.py init` calls this to lay down the folder structure and starter notes
that the SKILL.md workflow expects (00-Index, 00-IRON-RULES, feature/module
folders, an audit log, a glossary). Idempotent: existing files are never
overwritten, so re-running init on an established vault is safe.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import util

# Folders that hold one-note-per-thing; seeded with a .gitkeep so they survive.
FOLDERS = ["10-Features", "20-Modules", "30-Data-Flows", "50-Audit/Findings", "60-Sessions"]


def derive_project_name(project_root: Path) -> str:
    """Prefer the git remote's repo name, fall back to the folder name."""
    try:
        r = subprocess.run(["git", "-C", str(project_root), "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            leaf = re.split(r"[/:]", r.stdout.strip().removesuffix(".git"))[-1]
            if leaf:
                return leaf
    except (OSError, subprocess.SubprocessError):
        pass
    return project_root.name or "project"


def _index(name: str) -> str:
    return f"""# {name} — Vault Index

The canonical knowledge vault for **{name}**, kept in sync with the code by
Claude Autopilot for Obsidian. This file is the map of the vault and the place
to record the last working state.

## Vault map

| Path | Purpose |
|---|---|
| `00-Index.md` | This file — map + feature overview |
| `00-IRON-RULES.md` | Project-specific non-negotiable rules |
| `01-Architecture.md` | Components, data flow, tech stack |
| `02-Risk-Map.md` | Risk tier per area |
| `03-Build-And-Test.md` | How to build / test / CI state |
| `10-Features/` | One note per user-facing feature |
| `20-Modules/` | One note per code module |
| `30-Data-Flows/` | End-to-end flows spanning features |
| `50-Audit/` | Audit Log + Findings |
| `60-Sessions/` | One note per work session |
| `99-Glossary.md` | Project terminology |

## Features overview

| Slug | Title | Status | Key entry point |
|---|---|---|---|
| _(none yet)_ | | | |
"""


def _iron_rules(name: str) -> str:
    return f"""# Iron Rules — {name}

Non-negotiable rules for this project. Claude Autopilot for Obsidian reads this
file on entry and treats it as overriding its defaults. Add your own below.

## Keep the vault true

- A vault note and the code it documents change **together**, in the same unit
  of work — never "edit the code now, fix the note later".
- Commits that touch code here must list the notes touched in a
  `Vault-updated:` trailer.

## (add project-specific rules here)
"""


def _starter(title: str, blurb: str) -> str:
    return f"# {title}\n\n> {blurb}\n\n_(fill in as the project grows)_\n"


def scaffold(vault_dir: Path, project_name: str) -> list[str]:
    """Create the vault skeleton. Returns the list of newly created paths."""
    created: list[str] = []
    vault_dir.mkdir(parents=True, exist_ok=True)

    for folder in FOLDERS:
        d = vault_dir / folder
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")

    files = {
        "00-Index.md": _index(project_name),
        "00-IRON-RULES.md": _iron_rules(project_name),
        "01-Architecture.md": _starter("Architecture", "Components, data flow and tech stack."),
        "02-Risk-Map.md": _starter("Risk Map", "Risk tier (L1/L2/L3) per top-level area."),
        "03-Build-And-Test.md": _starter("Build & Test", "How to build, how to test, CI state."),
        "50-Audit/Log.md": _starter("Audit Log", "One line per fix or finding, newest first."),
        "99-Glossary.md": _starter("Glossary", "Project-specific terms and acronyms."),
    }
    for rel, content in files.items():
        p = vault_dir / rel
        if not p.exists():
            util.write_text(p, content)
            created.append(rel)
    return created
