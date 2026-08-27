# Agent Rules

Binding rules for anyone — human or AI — making changes in this repository. These are
not suggestions; follow them in order.

## 1. Read the goal before touching anything

Before making any change, read `docs/THESIS.md` (why this project exists and the
decisions already made) and `docs/SCOPE.md` (the enforced boundary). If you're picking
up an existing requirement folder, also read its `REQUIREMENTS.md` and `DESIGN.md`.

## 2. Scope guard — never widen the project

Never add anything on `docs/SCOPE.md`'s 🔴 list (ML, trading strategies, behavior
classification, autonomous trading agents, feature engineering for models,
backtesting, order execution, arbitrage/trading decisions, "Trade DNA"-style
fingerprinting) — regardless of how the request is phrased, who asks, or how small it
sounds. This project stops at "the market's public data is durably and verifiably in
the database." If a request would cross that line, say so and stop instead of
implementing it.

Corollary: no authenticated Binance access, ever. Public REST/WebSocket only.

## 3. Modularity — independent modules, tightly connected only through explicit contracts

Each product connector (Spot, USDⓈ-M, COIN-M, Options) is its own module: own
WebSocket/REST clients, own reconnect/resync logic, own payload mapping. Modules never
import each other's internals. The only allowed coupling points are:

- the shared envelope shape pushed onto the internal queue,
- the single DB writer and the schema it writes to,
- the capability registry config.

If you find yourself reaching into another module's internals to make something work,
that's a sign the contract is wrong — fix the contract, don't bypass it.

## 4. Spec-driven workflow — requirement → design → tasks → tracker

For every new unit of work:

1. Create `docs/requirements/<YYYY-MM-DD>-<short-kebab-slug>/` (see
   `docs/requirements/README.md` for the exact convention).
2. Write `REQUIREMENTS.md` (what and why, checked against `docs/SCOPE.md`) and
   `DESIGN.md` (how) **before** writing code.
3. Break the design into `TASKS.md`.
4. Create `TRACKER.md` with one checkbox per task, and tick items off live as you
   complete them — not batched at the end of the session.
5. Never retroactively widen an old requirement folder's scope — open a new folder.
6. Add the new folder to the index table in `docs/requirements/README.md`.

## 5. Changelog and status discipline

- **Always read `CHANGELOG.md` first**, before making any code change, to know what
  the current state and most recent decisions are.
- **Always append an entry to `CHANGELOG.md`** describing what changed and why, as part
  of the same change — not a follow-up.
- **Always update `STATUS.md`** to reflect the new state (current phase, what's done,
  what's next) as part of the same change.

## 6. Keep the docs in sync with the code

If a change alters a module boundary, a table shape, a data flow, or the tech stack,
update `docs/ARCHITECTURE.md` in the same change. A design doc that describes a system
that no longer exists is worse than no design doc.

## 7. End-of-task self code review

Before marking a task's checkbox complete in `TRACKER.md`, review your own diff against
this checklist and **fix what you find yourself** — don't just report it and stop:

1. **Scope**: Does this change do anything not required by this folder's
   `REQUIREMENTS.md`, or anything on `docs/SCOPE.md`'s 🔴 list? Remove it.
2. **Correctness**: Trace each new code path against real Binance payload shapes and
   edge cases — reconnects, gaps, empty payloads, rate limits, malformed messages.
3. **Data integrity**: Are prices/quantities/IDs stored as text/exact decimal, never
   float? Is the raw payload preserved in `raw_events` regardless of normalization?
4. **Resilience**: Does every network/WebSocket call have reconnect + backoff? Does
   depth handling detect gaps and resync from a fresh snapshot rather than silently
   continuing on stale state?
5. **Boundaries**: Does this module talk to others only through the queue/registry/DB
   contracts (rule 3), not by importing internals?
6. **Docs sync**: Does `DESIGN.md` / `docs/ARCHITECTURE.md` still accurately describe
   the system after this change? Update it if not (rule 6).
7. **Tests**: Is there at least one test exercising the new behavior, including a
   failure path (a gap, a disconnect, a malformed payload)?

Fix every issue you find, then update `CHANGELOG.md`, `STATUS.md`, and this folder's
`TRACKER.md` in the same commit. Only then check the task off.

## 8. Recommended tooling: Ponytail

[Ponytail](https://github.com/DietrichGebert/ponytail) is a Claude Code plugin that
enforces the same discipline rule 7 already asks for: before writing new code, check
whether it needs to exist, whether it's already in the codebase, whether stdlib/native
platform features cover it, and only then write the minimal code required. It directly
reinforces this project's "no premature abstraction, no speculative code" stance and is
recommended for whoever implements the connectors in `src/`.

It is not installed automatically — enable it once per Claude Code session/environment
with:

```
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

It is a session-level tool, not a repo dependency — it has no entry in `requirements.txt`
or equivalent and does not affect what ships in `src/`.
