# validation/

Data-capture validation: availability, integrity, timestamps, provenance, storage
correctness — **not** trading interpretation.

| Path | Purpose |
|---|---|
| `script/` | Probes, validators, audit/smoke helpers |
| `report/` | Generated validation/audit reports |

Primary entrypoints (library code stays in `src/`):

```bash
python -m src.validate --out validation/report/BINANCE_DATA_CAPTURE_REPORT.md
python -m src.audit --out validation/report/audit_report.md
python validation/script/run_validation.py
```

See `AGENTS.md` rule 8.
