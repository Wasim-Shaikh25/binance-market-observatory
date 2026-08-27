# Requirements: Options book/OI + source_type provenance

**Opened:** 2026-08-27  
**Why:** Close the remaining checklist NOT_IMPLEMENTED cells that are publicly
available and in scope. No trading/ML. Does not claim a 72h wall-clock run.

## In scope

1. Options order book via public REST `GET /eapi/v1/depth` → `depth_snapshots`
   (REST poll snapshots; WS depth not required given Options WS delivers 0 frames here)
2. Options open interest via public REST `GET /eapi/v1/openInterest` →
   `open_interest` with `product=OPTIONS`
3. Provenance: `raw_events.source_type` distinguishing `websocket` | `rest_poll` |
   `rest_backfill` (latter reserved for future gap-fill; live REST polls use `rest_poll`)

## Out of scope

- Authenticated endpoints
- Fabricating Options WS traffic
- Full historical REST backfill job (column + contract only; no gap-fill crawler yet)
- Exchange announcements (still not publicly machine-readable)
- 72-hour continuous run
