"""Obsidian Autopilot — cross-platform Claude Code ↔ Obsidian automation.

A single, config-driven, pure-stdlib Python package that replaces a pile of
per-OS shell hooks. Works identically on macOS, Linux and Windows.

Sub-modules:
    util       low-level helpers (paths, logging, locking, atomic writes)
    config     discovery + schema + defaults for the user config file
    gitsync    throttled, lock-protected git pull/push of the vault
    archive    transcript -> readable Markdown (+ raw JSONL) with secret redaction
    organize   rebuild the Agent-History _INDEX.md map-of-content
    linker     fingerprint sessions and cross-link related ones
    installer  register/remove the hooks in Claude's settings.json
"""

__version__ = "1.0.0"
