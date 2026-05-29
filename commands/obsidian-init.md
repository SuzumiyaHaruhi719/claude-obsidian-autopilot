---
description: Read the whole codebase and generate a richly cross-linked Obsidian vault documenting every feature, every supporting module, and how they connect.
argument-hint: "[optional: path to project root — defaults to the current directory]"
allowed-tools: Bash, Glob, Grep, Read, Write, Edit
---

You are reverse-documenting **this codebase** into an Obsidian vault that captures
*how the whole project is actually implemented* — every feature, every module
that supports it, and the wiki-links between them so the vault's graph mirrors
the real dependency structure.

Project root: `$ARGUMENTS` (if empty, use the current working directory).

Work in phases. **Do not invent anything** — every entry point, behavior and
dependency you record must come from a file you actually read. Cite real
`path/to/file.ext:line` references. Prefer being correct and concise over
exhaustive prose.

## Phase 0 — Scaffold the vault

Create the vault at `<project-root>/obsidian/`. If `pilot.py` from the
Claude Autopilot for Obsidian skill is reachable, run `python <path>/pilot.py init`
from the project root to scaffold + register it. Otherwise create the structure yourself:

```
obsidian/
├── 00-Index.md
├── 01-Architecture.md
├── 02-Risk-Map.md
├── 03-Build-And-Test.md
├── 10-Features/
├── 20-Modules/
├── 30-Data-Flows/
├── 50-Audit/Findings/
└── 99-Glossary.md
```

## Phase 1 — Survey

- Identify the stack, package manifests, and **entry points** (mains, servers,
  CLIs, route tables, exported APIs).
- Map the directory tree to responsibilities. Use `Glob`/`Grep` broadly; read
  the files that matter. For a large repo, prioritize `src/`, `apps/`,
  `lib/`, route/handler/service layers, and anything imported widely.
- Draft two lists: **features** (user- or caller-facing capabilities) and
  **modules** (internal code units that features lean on).

## Phase 2 — One note per feature → `10-Features/<slug>.md`

For each feature, write a focused note containing:

- **Summary** — one line: what it does, for whom.
- **Key entry point** — the exact `file.ext:line` where it starts.
- **How it works** — the real control/data flow, in a few steps, citing files.
- **Depends on** — `[[20-Modules/<slug>]]` links for every module it uses, and
  `[[10-Features/<slug>]]` links for sub-features it composes. **Link liberally**
  — these links are what make the graph reflect the implementation.
- **Known issues / TODOs** — anything flagged in the code (TODO, FIXME, hacks).
- **Risk tier** — L1 (privileged / external-facing / security-critical),
  L2 (business logic), or L3 (ancillary).

## Phase 3 — One note per module → `20-Modules/<slug>.md`

Same shape: summary, key entry point, what it exposes, who calls it
(back-links to the features from Phase 2), internal notes worth knowing.

## Phase 4 — Cross-cutting docs

- `30-Data-Flows/<slug>.md` — for each end-to-end flow that spans multiple
  features/modules, trace it step by step with `[[links]]` to each stop.
- `01-Architecture.md` — components, how they communicate, the tech stack.
- `02-Risk-Map.md` — risk tier per top-level area, with rationale.
- `03-Build-And-Test.md` — how to build, how to test, what CI does.
- `99-Glossary.md` — project-specific terms, acronyms, domain nouns.

## Phase 5 — Index

Rewrite `00-Index.md` as the map of content: a short project description plus a
**Features overview table** (Slug · Title · Risk tier · Key entry point), each
row linking to its `10-Features/` note. Group by risk tier.

## Rules

- **Read before you write.** Open the file and confirm the line before citing it.
- **One note per thing**, focused; extract shared concepts rather than repeating.
- **Wiki-link everything related** (`[[...]]`) — features to their modules,
  modules to their callers, flows to their stops. The denser and more accurate
  the links, the better the graph captures the implementation.
- Keep prose tight; tables and bullet lists over paragraphs.
- When you finish, print a short summary: how many features and modules were
  documented, and the path to `00-Index.md`.
