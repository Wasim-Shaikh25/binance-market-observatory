# Status

**Last updated:** 2026-08-27

## Current phase

Pre-implementation. The documentation/governance scaffold is complete; no collector
code exists yet.

## Done

- Thesis, scope guard, and living architecture doc (`docs/THESIS.md`, `docs/SCOPE.md`,
  `docs/ARCHITECTURE.md`).
- Agent rules with a scope guard, modularity rule, spec-driven workflow, and an
  end-of-task self code-review prompt (`AGENTS.md`).
- Changelog/status discipline established (this file, `CHANGELOG.md`).
- Requirements workflow established (`docs/requirements/`), with:
  - `2026-08-27-repo-scaffold-and-governance` — **Done**.
  - `2026-08-27-phase1-spot-collector` — **Not started** (drafted, ready to pick up).

## Next

Pick up `docs/requirements/2026-08-27-phase1-spot-collector/`:
1. Lock the open decisions in its `DESIGN.md` (libraries, batch size, registry schema,
   kline intervals).
2. Scaffold `src/`, `config/`, `tests/` per `docs/ARCHITECTURE.md` §7.
3. Work through its `TASKS.md` / `TRACKER.md` in order.
4. Target: a 72-hour clean Spot-only run with a written audit report before Phase 2
   (USDⓈ-M Futures) begins.

## Known gaps / risks

- Options' current public API/stream surface has not been re-verified against Binance's
  live docs as of this scaffold — confirm at the start of the Options phase
  (`THESIS.md` §9, Phase 4).
- No code, tests, or CI exist yet — everything in `src/`, `config/`, `tests/` is
  planned, not built.
