# Requirements: Complete Data Validation Checklist

**Opened:** 2026-08-27  
**Scope check:** In scope — data availability, integrity, completeness, timestamps,
synchronization, provenance, and storage correctness only. No trading/ML/signals
(see `docs/SCOPE.md` 🔴 list).

## Why

A future researcher must be able to answer: for any supported symbol and timestamp
in the collection period, **exactly what public data we captured, what we did not,
and why**. Row counts alone are not enough.

## What

Implement a validation engine that inspects a run database (+ config) and produces
`BINANCE_DATA_CAPTURE_REPORT.md` with mandatory statuses:

`PASS | PARTIAL | FAIL | NOT_IMPLEMENTED | NOT_PUBLICLY_AVAILABLE | NO_DATA`

For every planned feed, determine separately:

1. Publicly available on Binance (documented inventory; honest when unknown)
2. Implemented in this codebase
3. Connector configured/enabled
4. Receiving / stored
5. Integrity (timestamps, decimals-as-text, duplicates, gaps, raw↔normalized)

Do **not** invent substitutes for missing feeds. Do **not** compute trading features.

## Acceptance

- CLI: `python -m src.validate [--db PATH] [--config PATH] [--out PATH]`
- Report answers the five questions (intend / Binance exposes / we collected /
  trustworthy / missing)
- Validation matrix filled for Spot, Margin metadata, USDS-M, COIN-M, Options
- Runs cleanly against an existing smoke/capture DB
- At least one unit test covering status classification helpers
