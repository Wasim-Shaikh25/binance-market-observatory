"""Status vocabulary for the data-capture validation report.

Mandatory distinctions — never collapse these into a single boolean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_PUBLICLY_AVAILABLE = "NOT_PUBLICLY_AVAILABLE"
    NO_DATA = "NO_DATA"


STATUS_GLYPH = {
    Status.PASS: "✅",
    Status.PARTIAL: "🟡",
    Status.FAIL: "🔴",
    Status.NOT_IMPLEMENTED: "⚪",
    Status.NOT_PUBLICLY_AVAILABLE: "⚫",
    Status.NO_DATA: "🔵",
}


@dataclass
class CheckResult:
    section: str
    item: str
    status: Status
    evidence: str
    details: dict[str, Any] = field(default_factory=dict)

    def line(self) -> str:
        return f"{STATUS_GLYPH[self.status]} **{self.status.value}** — {self.item}: {self.evidence}"


def combine_status(statuses: list[Status]) -> Status:
    """Roll up child checks: FAIL > PARTIAL > NO_DATA > NOT_IMPLEMENTED >
    NOT_PUBLICLY_AVAILABLE > PASS (empty → NOT_IMPLEMENTED)."""
    if not statuses:
        return Status.NOT_IMPLEMENTED
    priority = [
        Status.FAIL,
        Status.PARTIAL,
        Status.NO_DATA,
        Status.NOT_IMPLEMENTED,
        Status.NOT_PUBLICLY_AVAILABLE,
        Status.PASS,
    ]
    for p in priority:
        if p in statuses:
            return p
    return Status.PASS


def combine_summary(statuses: list[Status]) -> Status:
    """Roll up for section summaries: ignore NOT_IMPLEMENTED /
    NOT_PUBLICLY_AVAILABLE when any actionable status exists, so Options-off
    or documented upstream gaps don't hide Spot/Futures PASS.

    Mixed PASS + FAIL/NO_DATA across products → PARTIAL.
    """
    if not statuses:
        return Status.NOT_IMPLEMENTED
    actionable = [
        s
        for s in statuses
        if s not in (Status.NOT_IMPLEMENTED, Status.NOT_PUBLICLY_AVAILABLE)
    ]
    if not actionable:
        return combine_status(statuses)
    if Status.FAIL in actionable and Status.PASS in actionable:
        return Status.PARTIAL
    if Status.NO_DATA in actionable and Status.PASS in actionable:
        return Status.PARTIAL
    return combine_status(actionable)
