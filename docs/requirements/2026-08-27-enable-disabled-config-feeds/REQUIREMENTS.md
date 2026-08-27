# Requirements: Enable remaining disabled feeds in config

**Opened:** 2026-08-27  
**Scope check:** Capability registry only — no new analytics (`docs/SCOPE.md`).

## Why

Smoke checklist reported NOT_IMPLEMENTED for candle intervals not listed in
`kline_intervals`. Production `settings.yaml` still had Options `enabled: false`.

## What

1. Smoke: collect `1m, 5m, 15m, 1h, 4h, 1d` for Spot / USDS-M / COIN-M / Options.
2. Production settings: enable Options with a small `symbol_list` (not full-universe
   REST poll — that would blow rate limits) and the same kline set.

## Acceptance

- Configs updated; CHANGELOG / STATUS / requirements index updated
