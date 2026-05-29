"""Config discovery, schema and sane defaults.

The whole point of this rewrite: **nothing is hardcoded**. The original setup
baked `C:\\Users\\Thomas\\Documents\\Obsidian\\WTATC` into six different scripts.
Here every path and toggle lives in one JSON file, discovered in this order:

    1. $OBSIDIAN_PILOT_CONFIG                (explicit override)
    2. ~/.claude/obsidian-pilot.config.json  (default, next to settings.json)

If no config exists, the pilot runs in a safe no-op mode and logs a hint, so a
fresh install never crashes a session.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import util

CONFIG_ENV = "OBSIDIAN_PILOT_CONFIG"
DEFAULT_CONFIG_NAME = "obsidian-pilot.config.json"

# Default keywords that make a UserPromptSubmit hook decide a vault pull is
# worth the network round-trip. Bilingual on purpose (zh + en).
DEFAULT_PULL_KEYWORDS = [
    "obsidian", "vault", "agent history", "implementation", "note", "notes",
    "笔记", "库", "知识库", "历史", "存档",
]


def config_path() -> Path:
    env = os.environ.get(CONFIG_ENV)
    if env:
        return util.expand(env)
    return util.claude_home() / DEFAULT_CONFIG_NAME


@dataclass
class VaultCfg:
    name: str
    path: Path                 # the knowledge-vault directory Claude reads/writes
    git_root: Path             # where git runs (often == path, may be a parent)
    auto_pull: bool = True
    auto_push: bool = False    # SECURITY: opt-in. Off by default.
    pull_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_PULL_KEYWORDS))
    push_paths: list[str] = field(default_factory=list)  # relative; empty = whole git_root minus ignores


@dataclass
class ArchiveCfg:
    enabled: bool = True
    dir: Path | None = None        # default: <first vault git_root>/Agent History
    push: bool = False             # SECURITY: archives stay LOCAL unless explicitly enabled
    include_thinking: bool = True
    redact_secrets: bool = True


@dataclass
class Config:
    vaults: list[VaultCfg] = field(default_factory=list)
    archive: ArchiveCfg = field(default_factory=ArchiveCfg)
    organize: bool = True
    organize_throttle_sec: int = 1800
    link_sessions: bool = True
    pull_throttle_sec: int = 30
    loaded: bool = True            # False => no config file found (safe no-op mode)

    @property
    def primary(self) -> VaultCfg | None:
        return self.vaults[0] if self.vaults else None


def _as_path(v, fallback: Path | None = None) -> Path | None:
    if v in (None, ""):
        return fallback
    return util.expand(v)


def load() -> Config:
    """Load and validate the config. Returns a safe no-op Config if absent."""
    raw = util.read_json(config_path(), default=None)
    if raw is None:
        cfg = Config()
        cfg.loaded = False
        return cfg

    vaults: list[VaultCfg] = []
    for v in raw.get("vaults", []):
        path = _as_path(v.get("path"))
        if path is None:
            util.log("config", f"vault {v.get('name')!r} missing 'path' — skipped")
            continue
        git_root = _as_path(v.get("git_root"), fallback=path)
        vaults.append(VaultCfg(
            name=v.get("name") or path.name,
            path=path,
            git_root=git_root,
            auto_pull=bool(v.get("auto_pull", True)),
            auto_push=bool(v.get("auto_push", False)),
            pull_keywords=v.get("pull_keywords") or list(DEFAULT_PULL_KEYWORDS),
            push_paths=v.get("push_paths") or [],
        ))

    a = raw.get("archive", {})
    archive_dir = _as_path(a.get("dir"))
    if archive_dir is None and vaults:
        archive_dir = vaults[0].git_root / "Agent History"
    archive = ArchiveCfg(
        enabled=bool(a.get("enabled", True)),
        dir=archive_dir,
        push=bool(a.get("push", False)),
        include_thinking=bool(a.get("include_thinking", True)),
        redact_secrets=bool(a.get("redact_secrets", True)),
    )

    org = raw.get("organize", {})
    return Config(
        vaults=vaults,
        archive=archive,
        organize=bool(org.get("enabled", True)),
        organize_throttle_sec=int(org.get("throttle_seconds", 1800)),
        link_sessions=bool(raw.get("link_sessions", {}).get("enabled", True)),
        pull_throttle_sec=int(raw.get("pull_throttle_seconds", 30)),
        loaded=True,
    )
