from src.validation.status import Status, combine_status, combine_summary
from src.validation.inventory import FEEDS


def test_combine_status_priority():
    assert combine_status([Status.PASS, Status.FAIL]) == Status.FAIL
    assert combine_status([Status.PASS, Status.PARTIAL]) == Status.PARTIAL
    assert combine_status([Status.PASS]) == Status.PASS
    assert combine_status([]) == Status.NOT_IMPLEMENTED


def test_combine_summary_ignores_not_implemented_when_pass_exists():
    assert combine_summary([Status.PASS, Status.NOT_IMPLEMENTED]) == Status.PASS
    assert combine_summary([Status.PARTIAL, Status.NOT_PUBLICLY_AVAILABLE]) == Status.PARTIAL
    assert combine_summary([Status.NOT_IMPLEMENTED]) == Status.NOT_IMPLEMENTED


def test_inventory_includes_core_products():
    products = {f.product for f in FEEDS}
    assert {"SPOT", "USDM_FUTURES", "COINM_FUTURES", "OPTIONS", "MARGIN"} <= products
    opts = [f for f in FEEDS if f.product == "OPTIONS"]
    assert opts
    by_type = {f.data_type: f.implemented for f in opts}
    assert by_type["instruments"] and by_type["trades"] and by_type["ticker"] and by_type["iv_greeks"]
    assert by_type["book"] and by_type["open_interest"]
    assert any(f.product == "EXCHANGE" and f.data_type == "system_status" and f.implemented for f in FEEDS)
    assert any(
        f.product == "EXCHANGE" and f.data_type == "rest_backfill_provenance" and f.implemented for f in FEEDS
    )
