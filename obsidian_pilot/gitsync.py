"""Throttled, lock-protected git pull/push for a vault.

Improvements over the original PowerShell pair:
  * One implementation, three platforms (subprocess + git, no shell quirks).
  * **No blind `git add -A`.** Staging is scoped to configured content paths,
    and a managed .gitignore block keeps conversation archives + secrets out of
    the push unless the user explicitly opts in.
  * Pull is `--rebase --autostash` so local edits and Obsidian-sync edits from
    other machines never require a force-push.
  * Lock + throttle live in one place (util), not copy-pasted per script.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import util
from .config import Config, VaultCfg

# Managed .gitignore block. Everything between the markers is owned by the
# pilot and rewritten on each push; users can add their own lines elsewhere.
GITIGNORE_START = "# >>> obsidian-pilot (managed) >>>"
GITIGNORE_END = "# <<< obsidian-pilot (managed) <<<"

# Patterns that should never be committed regardless of settings.
ALWAYS_IGNORE = [
    "*.secret", "*.key", "*.pem", ".env", ".env.*",
    ".credentials.json",
]


def _git(git_root: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(git_root), *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _is_repo(git_root: Path) -> bool:
    return (git_root / ".git").exists()


def pull(vault: VaultCfg, cfg: Config, force: bool = False) -> str:
    """Pull the vault. Throttled + locked. Returns a short status string."""
    if not vault.auto_pull:
        return "pull disabled"
    if not _is_repo(vault.git_root):
        return "not a git repo"

    stamp = f"pull-{vault.name}.last"
    if not force and util.throttled(stamp, cfg.pull_throttle_sec):
        return "throttled"

    with util.lock(f"pull-{vault.name}.lock", stale_seconds=120) as got:
        if not got:
            return "another pull in flight"
        r = _git(vault.git_root, "pull", "--rebase", "--autostash", "origin", "HEAD")
        if r.returncode == 0:
            util.touch(stamp)
            util.log("sync", f"[{vault.name}] pull ok")
            return "pull ok"
        util.log("sync", f"[{vault.name}] pull failed: {r.stderr.strip()}")
        return f"pull failed: {r.stderr.strip()[:120]}"


def _managed_gitignore_lines(cfg: Config, vault: VaultCfg) -> list[str]:
    lines = list(ALWAYS_IGNORE)
    # Keep conversation archives local unless the user opted into pushing them.
    if cfg.archive.enabled and not cfg.archive.push and cfg.archive.dir:
        try:
            rel = cfg.archive.dir.relative_to(vault.git_root)
            lines.append(f"{rel.as_posix()}/")
        except ValueError:
            pass  # archive lives outside the repo — nothing to ignore
    # Raw transcripts are never useful to push and may hold secrets.
    lines.append("*.raw.jsonl")
    return lines


def _ensure_gitignore(vault: VaultCfg, cfg: Config) -> None:
    gi = vault.git_root / ".gitignore"
    existing = util.read_text(gi) if gi.exists() else ""
    block = "\n".join([GITIGNORE_START, *_managed_gitignore_lines(cfg, vault), GITIGNORE_END])

    if GITIGNORE_START in existing and GITIGNORE_END in existing:
        pre = existing.split(GITIGNORE_START)[0].rstrip("\n")
        post = existing.split(GITIGNORE_END)[1].lstrip("\n")
        new = "\n".join(p for p in [pre, block, post] if p) + "\n"
    else:
        new = (existing.rstrip("\n") + "\n\n" if existing.strip() else "") + block + "\n"
    if new != existing:
        util.write_text(gi, new)


def push(vault: VaultCfg, cfg: Config) -> str:
    """Commit configured paths and push. Pulls first to avoid force-pushes."""
    if not vault.auto_push:
        return "push disabled"
    if not _is_repo(vault.git_root):
        return "not a git repo"

    with util.lock(f"push-{vault.name}.lock", stale_seconds=600) as got:
        if not got:
            return "another push in flight"

        _ensure_gitignore(vault, cfg)

        # Scope staging. Empty push_paths => stage tracked changes across the
        # repo, but .gitignore (managed above) keeps archives/secrets out.
        targets = vault.push_paths or ["."]
        add = _git(vault.git_root, "add", "--", *targets)
        if add.returncode != 0:
            util.log("sync", f"[{vault.name}] add failed: {add.stderr.strip()}")
            return "add failed"

        staged = _git(vault.git_root, "diff", "--cached", "--name-only").stdout.strip()
        if not staged:
            return "nothing to commit"
        n = len(staged.splitlines())

        msg = f"chore(vault): autopilot sync {util.now_local_str()} ({n} files)"
        commit = _git(vault.git_root, "commit", "-m", msg)
        if commit.returncode != 0:
            util.log("sync", f"[{vault.name}] commit failed: {commit.stderr.strip()}")
            return "commit failed"

        pull(vault, cfg, force=True)  # rebase onto remote before pushing
        pr = _git(vault.git_root, "push", "origin", "HEAD")
        if pr.returncode != 0:
            util.log("sync", f"[{vault.name}] push failed: {pr.stderr.strip()}")
            return f"push failed: {pr.stderr.strip()[:120]}"
        util.log("sync", f"[{vault.name}] pushed {n} files")
        return f"pushed {n} files"
