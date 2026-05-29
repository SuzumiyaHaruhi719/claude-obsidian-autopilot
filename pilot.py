#!/usr/bin/env python3
"""Obsidian Autopilot - single entry point for hooks and the CLI.

Usage (as a Claude Code hook, registered automatically by `install`):
    pilot.py session-start      # SessionStart  : pull vaults + rebuild index
    pilot.py prompt             # UserPromptSubmit: smart-pull + link + organize
    pilot.py stop               # Stop          : archive transcript + (opt) push

Usage (as a CLI, for humans):
    pilot.py install            # register the three hooks in settings.json
    pilot.py uninstall          # remove them
    pilot.py status             # show resolved config + last log lines
    pilot.py doctor             # check git, python, paths, remotes
    pilot.py sync               # pull + push all vaults now (manual)
    pilot.py init               # write a starter config file if none exists

Hook events read a JSON payload on stdin (Claude Code's hook contract). The CLI
verbs take no stdin. Every path is read from the config file, so the same
script runs unmodified on macOS, Linux and Windows.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from obsidian_pilot import archive, config, gitsync, installer, linker, organize, util


# --------------------------------------------------------------------------- #
# stdin payload (hook contract)
# --------------------------------------------------------------------------- #
def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}


# --------------------------------------------------------------------------- #
# Lifecycle handlers
# --------------------------------------------------------------------------- #
def on_session_start(cfg: config.Config, _payload: dict) -> None:
    for v in cfg.vaults:
        gitsync.pull(v, cfg, force=True)
    organize.rebuild(cfg.archive, force=True, throttle_sec=cfg.organize_throttle_sec)


def on_prompt(cfg: config.Config, payload: dict) -> None:
    prompt = (payload.get("prompt") or "")
    # Smart pull: only hit the network if the prompt looks vault-related.
    for v in cfg.vaults:
        pattern = "|".join(re.escape(k) for k in v.pull_keywords)
        if pattern and re.search(pattern, prompt, re.IGNORECASE):
            gitsync.pull(v, cfg)
    if cfg.link_sessions:
        linker.link(payload.get("session_id", ""), payload.get("cwd", ""), cfg.archive)
    if cfg.organize:
        organize.rebuild(cfg.archive, throttle_sec=cfg.organize_throttle_sec)


def on_stop(cfg: config.Config, payload: dict) -> None:
    archive.save(payload.get("transcript_path", ""), payload.get("session_id", ""),
                 payload.get("cwd", ""), cfg.archive)
    if cfg.archive.push or any(v.auto_push for v in cfg.vaults):
        for v in cfg.vaults:
            gitsync.push(v, cfg)


# --------------------------------------------------------------------------- #
# CLI verbs
# --------------------------------------------------------------------------- #
def cli_status(cfg: config.Config) -> None:
    if not cfg.loaded:
        print(f"No config found. Run `python pilot.py init` to create one at:\n"
              f"  {config.config_path()}")
        return
    print(f"Config: {config.config_path()}\n")
    for v in cfg.vaults:
        print(f"  vault {v.name!r}: {v.path}")
        print(f"    git_root={v.git_root}  auto_pull={v.auto_pull}  auto_push={v.auto_push}")
    a = cfg.archive
    print(f"\n  archive: enabled={a.enabled} push={a.push} redact={a.redact_secrets}\n"
          f"           dir={a.dir}")
    log = util.state_dir() / "sync.log"
    if log.exists():
        print("\nRecent sync log:")
        for line in log.read_text(encoding="utf-8").splitlines()[-8:]:
            print(f"  {line}")


def cli_doctor(cfg: config.Config) -> None:
    ok = True

    def check(label, cond, hint=""):
        nonlocal ok
        ok = ok and cond
        print(f"  [{'OK' if cond else 'XX'}] {label}" + (f"  -> {hint}" if not cond and hint else ""))

    print("obsidian-pilot doctor\n")
    check("python >= 3.8", sys.version_info >= (3, 8))
    git = subprocess.run(["git", "--version"], capture_output=True, text=True)
    check("git available", git.returncode == 0, "install git")
    check("config file present", cfg.loaded, "run `pilot.py init`")
    for v in cfg.vaults:
        check(f"vault {v.name!r} path exists", v.path.exists(), str(v.path))
        check(f"vault {v.name!r} is a git repo", (v.git_root / ".git").exists(), str(v.git_root))
    print("\n" + ("All good." if ok else "Some checks failed — see hints above."))


def cli_init() -> None:
    dest = config.config_path()
    if dest.exists():
        print(f"Config already exists: {dest}")
        return
    example = Path(__file__).resolve().parent / "config.example.json"
    util.write_text(dest, util.read_text(example))
    print(f"Wrote starter config: {dest}\nEdit it, then run `python pilot.py install`.")


def cli_sync(cfg: config.Config) -> None:
    for v in cfg.vaults:
        print(f"{v.name}: pull -> {gitsync.pull(v, cfg, force=True)}")
        print(f"{v.name}: push -> {gitsync.push(v, cfg)}")


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
HOOK_VERBS = {"session-start": on_session_start, "prompt": on_prompt, "stop": on_stop}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    verb = sys.argv[1]

    try:
        cfg = config.load()
        if verb in HOOK_VERBS:
            HOOK_VERBS[verb](cfg, _read_payload())
        elif verb == "install":
            print(installer.install())
        elif verb == "uninstall":
            print(installer.uninstall())
        elif verb == "status":
            cli_status(cfg)
        elif verb == "doctor":
            cli_doctor(cfg)
        elif verb == "init":
            cli_init()
        elif verb == "sync":
            cli_sync(cfg)
        else:
            print(__doc__)
            return 2
    except Exception as e:  # hooks must never crash a Claude session
        util.log("pilot", f"{verb} error: {e}")
        util.debug(f"{verb} error: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
