# Design: Complete Data Validation Checklist

## Modules

- `src/validation/inventory.py` — declared feed inventory (product × data type):
  public availability (from known Binance public surface), implementation flags,
  config enablement.
- `src/validation/checks.py` — async SQL/schema checks producing structured
  `CheckResult` objects (status + evidence).
- `src/validation/report.py` — renders markdown report + matrix.
- `src/validate.py` — CLI entrypoint (mirrors `src/audit.py`).

## Status rules (mandatory)

| Status | Meaning |
|---|---|
| PASS | Implemented, receiving, stored, integrity OK for configured scope |
| PARTIAL | Some coverage / integrity issues / configured subset only |
| FAIL | Should work but malfunctioning (errors, broken integrity) |
| NOT_IMPLEMENTED | Code/config does not collect this |
| NOT_PUBLICLY_AVAILABLE | Binance does not expose via public REST/WS we support |
| NO_DATA | Feed healthy but zero events in window (e.g. liquidations) |

Never mark PASS merely because `COUNT(*) > 0`.

## Check pipeline order

Discover → inventory vs public surface → implementation → config → incoming →
stored → raw payload samples → timestamps → duplicates → sequence/gaps →
coverage tiers → reconciliations (trades↔candles, depth↔bookTicker where
feasible) → reconnect/REST health → DB/schema integrity → storage growth →
final report.

## Honesty constraints

- Smoke/list mode → coverage is PARTIAL vs full-universe intent until a full run.
- Options disabled → NOT_IMPLEMENTED (not FAIL).
- `book_ticker` has no Binance event timestamp → document, do not fabricate.
- Funding from markPrice stream is **estimated/current**, not settled history.
- No RSI/VWAP/behavior scores in the report.
