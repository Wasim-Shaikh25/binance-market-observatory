"""Order book depth snapshot + WebSocket sync + gap-detection resync, per
docs/THESIS.md #5.4. This is product-agnostic: Spot, USDS-M, and COIN-M all
document the same procedure (buffer diffs, fetch a REST snapshot, discard
buffered diffs that predate it, verify update-ID continuity from then on,
and restart from a fresh snapshot the moment continuity breaks). COIN-M/
USDS-M additionally carry a `pu` (previous final update ID) field that lets
continuity be checked without relying on strict `U == prev_u + 1`; both
checks are supported here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DepthLevel:
    price: str
    qty: str


class DepthSyncTracker:
    """One instance per symbol. Not thread-safe; intended for single-task use."""

    def __init__(self, symbol: str, use_pu: bool = False):
        self.symbol = symbol
        self.use_pu = use_pu  # futures streams carry `pu`; spot does not
        self.last_update_id: Optional[int] = None
        self.bids: dict[str, str] = {}
        self.asks: dict[str, str] = {}
        self.synced = False
        self._buffer: list[dict] = []

    def buffer(self, event: dict) -> None:
        """Call for every depth-diff event received before a snapshot has
        been applied (or while resyncing)."""
        self._buffer.append(event)

    def apply_snapshot(self, last_update_id: int, bids: list[list[str]], asks: list[list[str]]) -> bool:
        """Apply a REST snapshot and replay buffered diffs. Returns True if
        synced (or waiting cleanly for the next live event); False if the
        snapshot could not be bridged and a fresh fetch is required."""
        self.last_update_id = last_update_id
        self.bids = {p: q for p, q in bids if float(q) > 0}
        self.asks = {p: q for p, q in asks if float(q) > 0}
        self.synced = False
        pending = [e for e in self._buffer if e["final_update_id"] > last_update_id]
        self._buffer.clear()
        first = True
        for event in pending:
            skip_check = first
            if first:
                first = False
                # Binance: first processed event needs U <= lastUpdateId+1 <= u.
                if not (event["first_update_id"] <= last_update_id + 1 <= event["final_update_id"]):
                    # Snapshot is stale vs the buffered stream — restore events
                    # for a retry and drop the broken book state.
                    self._buffer = pending
                    self.last_update_id = None
                    self.bids = {}
                    self.asks = {}
                    return False
            result = self.apply_update(event, _skip_pu_check_once=skip_check)
            if result != "ok":
                idx = pending.index(event)
                self._buffer = pending[idx:]
                self.last_update_id = None
                self.bids = {}
                self.asks = {}
                return False
        self.synced = True
        return True

    def apply_update(self, event: dict, _skip_pu_check_once: bool = False) -> str:
        """Returns 'ok', 'buffered' (no snapshot yet), or 'resync_needed'."""
        if self.last_update_id is None:
            self.buffer(event)
            return "buffered"

        if event["final_update_id"] <= self.last_update_id:
            return "ok"  # stale event, already covered by current state

        if not _skip_pu_check_once:
            if self.use_pu:
                if event.get("prev_final_update_id") != self.last_update_id:
                    self.synced = False
                    return "resync_needed"
            else:
                if event["first_update_id"] != self.last_update_id + 1:
                    self.synced = False
                    return "resync_needed"

        for price, qty in event["bids"]:
            if float(qty) == 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = qty
        for price, qty in event["asks"]:
            if float(qty) == 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = qty

        self.last_update_id = event["final_update_id"]
        self.synced = True
        return "ok"

    def reset(self) -> None:
        self.last_update_id = None
        self.bids = {}
        self.asks = {}
        self.synced = False
        self._buffer.clear()
