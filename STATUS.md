# Status

**Last updated:** 2026-08-27

## Current phase

Implementation complete for all four products (Spot, USDS-M Futures, COIN-M Futures,
Options); tested end-to-end against a local mock Binance server. **Not yet run against
real Binance** -- see "Known gaps / risks" below, this is the one thing standing
between "implemented" and "done."

## Done

- Documentation/governance scaffold (thesis, scope, architecture, AGENTS.md,
  changelog/status, requirements workflow).
- Full collector implementation:
  - Storage: SQLite WAL, single writer, decimal-as-text throughout, `raw_events`
    safety net, `instruments`/`instrument_snapshots` history split.
  - Rate limiting: REST weight token bucket reconciled against Binance's own
    `X-MBX-USED-WEIGHT-1M` header, 429/418 backoff via `Retry-After`, WS
    connection-attempt throttling, proactive reconnect before the ~24h forced cutoff.
  - Spot, USDS-M, COIN-M connectors sharing one framework (`src/connectors/market.py`):
    trades, aggTrades, bookTicker, 24h ticker, klines, depth snapshot+sync+resync
    (true SUBSCRIBE/UNSUBSCRIBE, no unnecessary resync on target-set changes),
    instrument metadata (incl. margin-tradable flag), funding rate, open interest,
    liquidations, mark price.
  - Options connector: raw-fidelity-only (see its docstring), disabled by default
    pending live wire-format verification.
  - Every trade/aggTrade row carries `buyer_maker` and a derived `taker_side`
    (BUY/SELL) so side is always explicit, not just inferable.
  - Every row carries `product` + `symbol` so Spot/USDM/COINM/Options data for the
    same underlying symbol is always distinguishable.
  - `config/settings.yaml` capability registry: each product independently
    enable-able, depth top-N/ranking/refresh configurable, rate-limit budgets
    configurable.
  - `src/main.py` entrypoint, `src/audit.py` CLI for the correctness audit report.
- 41 automated tests (unit + a full pipeline integration test against
  `tests/mock_binance.py`, a local protocol-faithful stand-in for Binance) -- all
  passing. Caught and fixed three real bugs in the process (see `CHANGELOG.md`).
- Per-run database files (`data/market_<run_id>.db`, one per start/stop cycle) and
  `scripts/collector.sh start|stop|status|tail` for running detached in the
  background -- see `docs/requirements/2026-08-27-per-run-db-and-background-run-scripts/`.

## Known gaps / risks

- **This sandbox cannot reach Binance.** `api.binance.com`/`stream.binance.com`
  return 403 through the environment's egress proxy (org policy), and the proxy does
  not support WebSocket upgrades at all regardless of host (confirmed via its own
  status/README endpoint). Every test in this repo therefore runs against a local
  mock, not the real exchange. **Before relying on this for real data collection**,
  run it from a machine with normal internet access: `pip install -r requirements.txt`,
  then `python -m src.main` (or `scripts/collector.sh start` to run it detached), and
  watch `data/market_<run_id>.db` fill in. If anything about Binance's real wire
  format differs from what's implemented here, that will surface immediately as parse
  errors / `db_write_failure` system_events -- check those first.
- Once running live, generate the audit report with `python -m src.audit` and read it
  per `docs/THESIS.md` #8 before trusting the dataset -- especially depth resync
  counts and stale-stream detection.
- Options normalized tables are not implemented (raw-fidelity only, disabled by
  default) -- confirm the current Options wire format against Binance's live docs and
  add normalizers following `connectors/common.py`'s pattern before enabling it.
- Rate-limit budgets in `config/settings.yaml` are conservative defaults; re-verify
  them against Binance's current documented limits periodically. The limiter
  self-corrects against the server's reported used-weight, which bounds the damage
  from a stale default, but doesn't replace checking the docs.
- No code, tests, or CI ran against real Binance -- the 72-hour clean-run acceptance
  criterion in both `docs/requirements/2026-08-27-phase1-spot-collector/` and
  `docs/requirements/2026-08-27-futures-and-options-collectors/` is still open.

## Next

1. Run the collector from an environment with real network access; watch for parse
   errors or `db_write_failure`/`rest_failure` system_events in the first few minutes,
   since those would indicate the real wire format drifted from what's implemented.
2. Once stable, let it run 24-72h and generate the audit report (`python -m src.audit`).
3. Mark both requirement folders' trackers Done once the live run confirms clean
   collection, and update `docs/requirements/README.md`'s index accordingly.
4. Confirm Options' current public API surface against live Binance docs and decide
   whether to add normalizers and enable it.
