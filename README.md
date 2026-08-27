# Binance Market Observatory

A public-data-only collector for Binance market data (Spot, Margin metadata, USDⓈ-M
Futures, COIN-M Futures, Options), storing everything durably and faithfully in SQL for
future research. No API keys, no account access, no trading logic — see `docs/THESIS.md`
for the full reasoning and `docs/SCOPE.md` for the enforced boundary.

## Start here

| Document | Purpose |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Rules for anyone (human or AI) working in this repo — read this first |
| [`docs/THESIS.md`](docs/THESIS.md) | Why this project exists, and every architectural decision made so far |
| [`docs/SCOPE.md`](docs/SCOPE.md) | Enforced in-scope / modify-on-sight / never-add checklist |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Living technical design: components, data flow, schema shape |
| [`docs/requirements/`](docs/requirements/) | Spec-driven work log — one folder per requirement (requirements → design → tasks → tracker) |
| [`CHANGELOG.md`](CHANGELOG.md) | What changed and why, most recent first |
| [`STATUS.md`](STATUS.md) | Current phase, what's done, what's next |

## Current status

Pre-implementation — the documentation/governance scaffold is in place; no collector
code exists yet. See `STATUS.md` for details and `docs/requirements/2026-08-27-phase1-spot-collector/`
for the next unit of work (the Spot collector, Phase 1 of the build order in
`docs/THESIS.md` §9).

## Working in this repo

1. Read `AGENTS.md` and `CHANGELOG.md` before making any change.
2. Every unit of work gets its own folder under `docs/requirements/` — see
   `docs/requirements/README.md` for the convention.
3. Nothing on `docs/SCOPE.md`'s 🔴 list gets built here, ever.
