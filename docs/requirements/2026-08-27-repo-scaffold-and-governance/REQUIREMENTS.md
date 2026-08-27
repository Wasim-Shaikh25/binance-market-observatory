# Requirement: Repo Scaffold & Governance

**Opened:** 2026-08-27
**Status:** Done

## Why

Before any collector code is written, the project needs a durable record of what it is
and is not for, and a process that keeps future work (by humans or agents) inside that
boundary. Without this, the project risks drifting into a general-purpose
trading/analytics platform (the exact failure mode the project's thesis exists to avoid).

## What is needed

1. A detailed thesis document capturing the project's purpose, scope, and the specific
   architectural decisions already made (instrument snapshots, raw-events safety net,
   depth sync, capability registry, decimal-as-text, SQLite single-writer, build order).
2. An explicit, enforceable scope guard (in/modify/never-add lists).
3. A living architecture document describing components, data flow, and repo layout.
4. `AGENTS.md` — binding rules for any agent (human or AI) working in this repo:
   scope guard, modularity rule, the requirement→design→tasks→tracker workflow,
   changelog/status discipline, and an end-of-task self code-review prompt.
5. Root `CHANGELOG.md` and `STATUS.md`, established from the start so the discipline of
   maintaining them exists before there's any code to change.
6. The `docs/requirements/` workflow itself (this folder is its first example), plus a
   stub for the next real requirement (Phase 1 Spot collector) so the tracker discipline
   has something concrete to point at next.

## Out of scope for this requirement

- Any actual collector code, connectors, or database schema implementation — that is
  `2026-08-27-phase1-spot-collector`.
- Any tooling/dependency choice beyond naming Python as the default implementation
  language in `ARCHITECTURE.md` (locked for real in the Phase 1 design doc).

## Acceptance criteria

- [x] `docs/THESIS.md` exists and covers scope, principles, data model decisions, storage
      architecture, capability registry, health/audit philosophy, and build order.
- [x] `docs/SCOPE.md` exists with explicit in/modify/never-add lists.
- [x] `docs/ARCHITECTURE.md` exists and describes components, data flow, and target
      repo layout.
- [x] `AGENTS.md` exists at repo root with the rules listed above and the code-review
      prompt.
- [x] `CHANGELOG.md` and `STATUS.md` exist at repo root.
- [x] `docs/requirements/README.md` documents the workflow and indexes existing folders.
- [x] A `2026-08-27-phase1-spot-collector` requirement folder exists with
      REQUIREMENTS/DESIGN/TASKS/TRACKER, tasks not yet started.
- [x] Root `README.md` links all of the above so a new reader/agent can navigate from it.
