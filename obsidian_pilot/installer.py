"""Register / remove the autopilot hooks in Claude Code's settings.json.

Cross-platform: detects the right Python launcher, writes absolute paths, and
merges into existing hook arrays without clobbering unrelated hooks. A single
dispatcher (`pilot.py <event>`) is registered per lifecycle event — one process
per event instead of the original three-to-six spawned shells per prompt.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from . import util

# event -> pilot subcommand
HOOK_EVENTS = {
    "SessionStart": "session-start",
    "UserPromptSubmit": "prompt",
    "Stop": "stop",
}
_SUBCMDS = set(HOOK_EVENTS.values())


def _is_pilot_command(command: str) -> bool:
    """True if a hook command string is one of ours.

    Matched structurally (``pilot.py <our-subcommand>``) rather than by a magic
    string, so it stays correct even if the repo directory is renamed.
    """
    if "pilot.py" not in command:
        return False
    return command.rsplit(None, 1)[-1].strip('"') in _SUBCMDS


def _python_exe() -> str:
    return sys.executable or shutil.which("python3") or shutil.which("python") or "python3"


def _pilot_entry() -> Path:
    # pilot.py sits at the repo root, one level above this package.
    return (Path(__file__).resolve().parent.parent / "pilot.py")


def _command(subcmd: str) -> str:
    return f'"{_python_exe()}" "{_pilot_entry()}" {subcmd}'


def _settings_path() -> Path:
    return util.claude_home() / "settings.json"


def install() -> str:
    settings_file = _settings_path()
    settings = util.read_json(settings_file, default={}) or {}
    hooks = settings.setdefault("hooks", {})

    for event, subcmd in HOOK_EVENTS.items():
        arr = hooks.setdefault(event, [])
        # Drop any prior pilot entries (idempotent re-install).
        for group in arr:
            group["hooks"] = [h for h in group.get("hooks", [])
                              if not _is_pilot_command(h.get("command", ""))]
        arr[:] = [g for g in arr if g.get("hooks")]
        arr.append({"matcher": "", "hooks": [
            {"type": "command", "command": _command(subcmd)}
        ]})

    # Back up before writing.
    if settings_file.exists():
        util.write_text(settings_file.with_suffix(".json.pilot-bak"),
                        util.read_text(settings_file))
    util.write_json(settings_file, settings)
    return f"installed hooks into {settings_file}"


def uninstall() -> str:
    settings_file = _settings_path()
    settings = util.read_json(settings_file, default={}) or {}
    hooks = settings.get("hooks", {})
    removed = 0
    for event in HOOK_EVENTS:
        arr = hooks.get(event, [])
        for group in arr:
            before = len(group.get("hooks", []))
            group["hooks"] = [h for h in group.get("hooks", [])
                              if not _is_pilot_command(h.get("command", ""))]
            removed += before - len(group["hooks"])
        hooks[event] = [g for g in arr if g.get("hooks")]
    util.write_json(settings_file, settings)
    return f"removed {removed} autopilot hook(s) from {settings_file}"
