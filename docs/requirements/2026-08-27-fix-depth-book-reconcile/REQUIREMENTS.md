# Requirements: Fix depth↔bookTicker reconciliation

**Opened:** 2026-08-27  
**Scope check:** Validation correctness only (`docs/SCOPE.md`).

## Why

Smoke checklist marked reconciliations 🟡 PARTIAL with "missing bookTicker or
empty book" even though Spot/Futures bookTicker and depth both filled. Cause:
the check used the latest `depth_snapshots` row by id, which was often Options
REST depth — Options has no `book_ticker` stream.

## What

Reconcile top-of-book only for products that expose bookTicker
(SPOT / USDM_FUTURES / COINM_FUTURES). Skip Options depth for this check
(document as N/A, not PARTIAL failure).

## Acceptance

- Unit test: Options-only latest snapshot does not force PARTIAL when Spot depth+book exist
- CHANGELOG / STATUS updated
