# Design: Repo Scaffold & Governance

## Approach

Pure documentation/process scaffold — no code. Files are organized so that "read this
first" has one obvious answer at each level:

- Root `README.md`: entry point, links everything else.
- Root `AGENTS.md`: rules an agent must follow, read before making changes.
- Root `CHANGELOG.md` / `STATUS.md`: what happened / where things stand, read before
  making changes (per `AGENTS.md`).
- `docs/THESIS.md`: why the project exists and the decisions already made — the
  authority for "is this in scope" when `SCOPE.md`'s checklist isn't enough context.
- `docs/SCOPE.md`: fast enforced checklist, derived from the thesis.
- `docs/ARCHITECTURE.md`: living technical design, updated alongside code.
- `docs/requirements/<date>-<slug>/`: per-requirement work log
  (REQUIREMENTS → DESIGN → TASKS → TRACKER), this folder being the first instance.

## Folder naming convention

`docs/requirements/<YYYY-MM-DD>-<short-kebab-slug>/`, e.g.
`2026-08-27-phase1-spot-collector`. Date-prefixed so folders sort chronologically in a
plain directory listing; slug so a human can tell what it's about without opening it.

## Why two requirement folders land in this change

This change itself is a requirement (governance scaffold) and is dogfit through the
same workflow it defines — proving the workflow works before asking anyone else to
follow it. A second, stub folder for Phase 1 (Spot collector) is created alongside it,
populated with a real requirements/design/task breakdown but with `TRACKER.md` entirely
unchecked, so the next unit of work has a concrete on-ramp instead of starting from a
blank `docs/requirements/`.

## Interfaces / contracts introduced

- The **envelope contract** connectors must emit into the internal queue (documented in
  `ARCHITECTURE.md` §1) — not implemented yet, but named now so Phase 1's design doc
  has a fixed target instead of inventing it from scratch.
- The **requirement folder shape** (REQUIREMENTS/DESIGN/TASKS/TRACKER, in that file
  order) — the contract between "a unit of work" and the tracker/changelog discipline
  in `AGENTS.md`.

## Non-goals

- No source layout (`src/`, `config/`, `tests/`) is created yet — `ARCHITECTURE.md`
  explicitly defers that to when Phase 1 implementation begins, to avoid empty
  speculative scaffolding sitting unused in the repo.
