from src.depth_sync import DepthSyncTracker


def diff(first, final, bids=(), asks=(), pu=None):
    e = {"first_update_id": first, "final_update_id": final, "bids": list(bids), "asks": list(asks)}
    if pu is not None:
        e["prev_final_update_id"] = pu
    return e


def test_buffers_updates_until_snapshot_applied():
    t = DepthSyncTracker("btcusdt")
    assert t.apply_update(diff(1, 5)) == "buffered"
    assert not t.synced


def test_snapshot_then_continuous_updates_stay_synced():
    t = DepthSyncTracker("btcusdt")
    t.apply_snapshot(100, bids=[["10.0", "1.0"]], asks=[["10.1", "1.0"]])
    assert t.synced
    assert t.apply_update(diff(101, 105, bids=[["10.0", "2.0"]])) == "ok"
    assert t.bids["10.0"] == "2.0"
    assert t.last_update_id == 105


def test_gap_triggers_resync_needed():
    t = DepthSyncTracker("btcusdt")
    t.apply_snapshot(100, bids=[["10.0", "1.0"]], asks=[["10.1", "1.0"]])
    # Skips ahead: first_update_id should have been 101, not 110 -> gap.
    assert t.apply_update(diff(110, 115)) == "resync_needed"
    assert not t.synced


def test_zero_quantity_removes_price_level():
    t = DepthSyncTracker("btcusdt")
    t.apply_snapshot(100, bids=[["10.0", "1.0"]], asks=[])
    t.apply_update(diff(101, 102, bids=[["10.0", "0"]]))
    assert "10.0" not in t.bids


def test_stale_event_before_snapshot_is_ignored():
    t = DepthSyncTracker("btcusdt")
    t.apply_snapshot(100, bids=[["10.0", "1.0"]], asks=[])
    assert t.apply_update(diff(90, 95)) == "ok"
    assert t.last_update_id == 100  # unchanged, event was stale


def test_futures_pu_continuity_check():
    t = DepthSyncTracker("btcusdt", use_pu=True)
    t.apply_snapshot(100, bids=[], asks=[])
    assert t.apply_update(diff(101, 105, pu=100)) == "ok"
    # pu must equal the previous final_update_id (105); wrong pu -> gap.
    assert t.apply_update(diff(106, 110, pu=999)) == "resync_needed"


def test_buffered_events_replayed_after_snapshot_arrives():
    t = DepthSyncTracker("btcusdt")
    t.apply_update(diff(95, 100))  # buffered, no snapshot yet
    t.apply_update(diff(101, 105, bids=[["10.0", "3.0"]]))  # also buffered
    t.apply_snapshot(100, bids=[["10.0", "1.0"]], asks=[])
    assert t.synced
    assert t.last_update_id == 105
    assert t.bids["10.0"] == "3.0"


def test_buffered_first_event_may_start_before_snapshot_id_per_binance_spec():
    # Binance's documented rule: the first processed event only needs
    # U <= lastUpdateId+1 <= u, not U == lastUpdateId+1 exactly.
    t = DepthSyncTracker("btcusdt")
    t.apply_update(diff(98, 103, bids=[["10.0", "9.0"]]))  # buffered, U=98 < 101
    t.apply_snapshot(100, bids=[["10.0", "1.0"]], asks=[])
    assert t.synced
    assert t.last_update_id == 103
    assert t.bids["10.0"] == "9.0"


def test_reset_clears_state():
    t = DepthSyncTracker("btcusdt")
    t.apply_snapshot(100, bids=[["10.0", "1.0"]], asks=[])
    t.reset()
    assert t.last_update_id is None
    assert t.bids == {}
    assert not t.synced
