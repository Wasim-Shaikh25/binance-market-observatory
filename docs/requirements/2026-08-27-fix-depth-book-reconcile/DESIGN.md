# Design

`check_reconcile_depth_book` walks recent `depth_snapshots` for
`product IN ('SPOT','USDM_FUTURES','COINM_FUTURES')` and pairs each with the
latest `book_ticker` for that product/symbol. First usable pair is scored
(±0.2% relative). If none exist → `NO_DATA`. Options depth is never used here.
