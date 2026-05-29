"""Low-level, OS-agnostic helpers: paths, logging, locking, atomic writes.

Every function here is pure stdlib and behaves the same on macOS, Linux and
Windows. No `powershell.exe`, no `bash`, no shelling out for things Python can
do natively.
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def claude_home() -> Path:
    """Return Claude Code's config dir (~/.claude), honouring CLAUDE_CONFIG_DIR."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def state_dir() -> Path:
    """Where the pilot keeps its own locks, logs and stamp files."""
    d = claude_home() / "obsidian-pilot"
    d.mkdir(parents=True, exist_ok=True)
    return d


def expand(p: str | os.PathLike) -> Path:
    """Expand ~ and environment variables, return an absolute Path."""
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()


# --------------------------------------------------------------------------- #
# Time
# --------------------------------------------------------------------------- #
def now_local_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# Logging — one rotating-ish line-oriented log per component
# --------------------------------------------------------------------------- #
def log(component: str, msg: str) -> None:
    """Append a timestamped line to <state>/<component>.log. Never raises."""
    try:
        line = f"{now_local_str()} | {component} | {msg}\n"
        (state_dir() / f"{component}.log").open("a", encoding="utf-8").write(line)
    except Exception:
        pass  # logging must never break a hook


def debug(msg: str) -> None:
    """Print to stderr only when OBSIDIAN_PILOT_DEBUG is set."""
    if os.environ.get("OBSIDIAN_PILOT_DEBUG"):
        print(f"[obsidian-pilot] {msg}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Atomic, BOM-free UTF-8 writes (Obsidian + git both dislike BOMs)
# --------------------------------------------------------------------------- #
def write_text(path: str | os.PathLike, text: str) -> None:
    """Atomically write UTF-8 (no BOM) via a temp file + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)  # atomic on all three platforms


def read_text(path: str | os.PathLike) -> str:
    return Path(path).read_text(encoding="utf-8")


def read_json(path: str | os.PathLike, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: str | os.PathLike, obj) -> None:
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Cross-platform throttle + lock (replaces the .lock / .last file dance the
# original PowerShell hooks reimplemented five times over).
# --------------------------------------------------------------------------- #
def throttled(stamp_name: str, seconds: int) -> bool:
    """Return True if a stamp younger than `seconds` exists (i.e. skip work)."""
    stamp = state_dir() / stamp_name
    if stamp.exists() and (time.time() - stamp.stat().st_mtime) < seconds:
        return True
    return False


def touch(stamp_name: str) -> None:
    (state_dir() / stamp_name).write_text(str(now_utc_ms()), encoding="utf-8")


@contextmanager
def lock(lock_name: str, stale_seconds: int = 600):
    """Best-effort cross-process lock. Reclaims locks older than stale_seconds.

    Yields True if the lock was acquired, False if another holder is active
    (caller should then no-op). Never blocks.
    """
    lock_file = state_dir() / lock_name
    if lock_file.exists():
        age = time.time() - lock_file.stat().st_mtime
        if age < stale_seconds:
            yield False
            return
        # stale — reclaim
        try:
            lock_file.unlink()
        except OSError:
            pass
    try:
        lock_file.write_text(str(os.getpid()), encoding="utf-8")
        yield True
    finally:
        try:
            lock_file.unlink()
        except OSError:
            pass
