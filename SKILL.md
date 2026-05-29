---
name: claude-autopilot-for-obsidian
description: >-
  Keep an Obsidian vault as the single source of truth for a codebase while
  Claude works. Use when the user has an Obsidian vault tied to a project and
  wants notes kept in sync with code changes, when they ask to "update the
  vault", "sync notes", reference an Obsidian knowledge base, or when working in
  a repo that has a configured vault. Handles reading vault context before
  changes, writing structured notes alongside code edits, archiving
  conversations, and git-syncing the vault — cross-platform (macOS/Linux/Windows).
---

# Claude Autopilot for Obsidian

A **dynamic, config-driven workflow** for treating an Obsidian vault as the
single source of truth for a codebase. It replaces hardcoded, OS-specific shell
hooks with one cross-platform Python toolkit plus the decision rules below.

There are two layers. The **automatic layer** (git sync, conversation
archiving, index rebuilds, session cross-linking) runs as Claude Code hooks —
you do not invoke it. The **semantic layer** below is *your* job: deciding which
notes a change touches and keeping them honest.

## When this skill applies

Check `OBSIDIAN_PILOT_CONFIG` or `~/.claude/obsidian-pilot.config.json`. Each
`vault` entry maps a knowledge-vault directory to a code project. If the project
you are working in matches a configured vault, this workflow is in force.

**If the project has no vault yet, creating one is the first step of the
workflow — not a reason to stop.** When you are doing real work in a project
(not a throwaway scratch dir) and no vault is registered for it, set one up:

```bash
python pilot.py init   # run from the project root
```

This scaffolds a vault at `<project>/obsidian` (index, iron-rules, feature /
module / audit folders), points conversation archives at `~/Documents` (outside
the repo), and registers the project. Confirm with the user first if creating
files would be surprising; otherwise just do it and tell them. Only skip
creation when the user declines or the directory clearly is not a real project.

## The one rule that matters

> **A vault note and the code it documents change together, in the same unit of
> work — never "edit code now, fix the note later."** The vault is the source of
> truth; if it lags the code, the knowledge chain is broken.

Practically: before you finish a task that changed code, ask "which vault note
now describes something that is no longer true?" and fix it in the same turn.

## Read before you change

0. **No vault for this project yet?** Create one with `python pilot.py init`
   (see above) before proceeding, so there is somewhere to record the change.
1. On entering a project with a vault, read its index (`00-Index.md` or
   `_INDEX.md`) first — it is the map plus the last-session state.
2. Before editing a feature/module, read its existing note (e.g.
   `10-Features/<slug>.md`, `20-Modules/<slug>.md`) for entry points, known
   issues and prior decisions. Do not duplicate what is already recorded.

## Write as you change — note mapping

| What you changed in code | Vault note to update in the same turn |
| --- | --- |
| A feature's behavior | `10-Features/<slug>.md` (entry points, recent change, known issues) |
| A module's internals | `20-Modules/<slug>.md` |
| Fixed a bug / added a guard | new `50-Audit/Findings/<slug>.md` + one line in `50-Audit/Log.md` |
| Architecture / deps / ports / build | `01-Architecture.md` or `03-Build-And-Test.md` |
| Risk surface (new entry point, etc.) | `02-Risk-Map.md` |
| New term or acronym | `99-Glossary.md` |
| Added/removed a feature | the Features table in the index |

Folder names are conventions, not law — match whatever structure the existing
vault uses. If the vault is empty, propose this layout before populating it.

## Commit discipline

When you commit code changes that touched a configured vault, include a
`Vault-updated:` trailer listing the note paths you wrote. An empty trailer on a
code change means the note step was skipped — call that out rather than committing.

## What runs automatically (do not duplicate by hand)

The hooks installed by `pilot.py install` already handle, on their own schedule:

- **Pull** the vault on session start and on vault-related prompts.
- **Archive** each conversation to the Agent-History folder as readable Markdown
  (secrets redacted; archives stay local unless the user opted into pushing).
- **Rebuild** the Agent-History `_INDEX.md` and **cross-link** related sessions.
- **Push** the vault — only if the user enabled `auto_push`.

So: do not manually copy transcripts, rebuild indexes, or `git push` the vault
unless the user explicitly asks. Your focus is the *content* of knowledge notes.

## Helpful commands

```bash
python pilot.py init       # scaffold <project>/obsidian + register the vault
python pilot.py status     # show resolved config + recent sync log
python pilot.py doctor     # verify git, paths, remotes
python pilot.py sync       # manual pull+push now
python pilot.py install    # (re)register the lifecycle hooks
```

## Project-specific hard rules

A vault may define its own non-negotiable rules in a `00-IRON-RULES.md` at its
root (e.g. "always read the latest screenshot when a bug is reported"). If that
file exists, read it on entry and treat it as overriding these defaults.
