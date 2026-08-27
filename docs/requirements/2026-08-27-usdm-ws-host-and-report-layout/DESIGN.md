# Design

## USDM WebSocket host

- Change `config/settings.yaml` and `config/smoke_settings.yaml`
  `usdm_futures.ws_base_url` → `wss://fstream.binancefuture.com`
- Keep REST on `https://fapi.binance.com` (unchanged; REST was fine).
- Document in connector comment / ARCHITECTURE if WS hosts are listed.

## Folder layout (AGENTS.md rule)

```
research/
  script/   # ad-hoc research / analysis scripts (no trading systems)
  report/   # outputs from research scripts
validation/
  script/   # probes, validation runners wrapping src.validate / src.audit
  report/   # BINANCE_DATA_CAPTURE_REPORT.md, audit reports, probe notes
```

Collector runtime code stays in `src/`. Ops scripts like `scripts/collector.sh` stay
in `scripts/`. Market databases stay in `data/`.

## Validate CLI

Default `--out` → `validation/report/BINANCE_DATA_CAPTURE_REPORT.md`.
Default audit `--out` → `validation/report/audit_report.md`.
