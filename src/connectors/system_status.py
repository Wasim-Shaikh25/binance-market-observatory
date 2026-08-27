"""Public Binance exchange system-status poller (`/sapi/v1/system/status`).

No API key required for this endpoint. Writes normalized `exchange_status`
rows plus raw_events via the shared queue.
"""

from __future__ import annotations

import asyncio
import logging

from ..binance_client import RestClient
from ..models import Envelope
from ..storage import log_system_event
from .market import ConnectorContext

logger = logging.getLogger(__name__)

SYSTEM_STATUS_PATH = "/sapi/v1/system/status"
DEFAULT_REST_BASE = "https://api.binance.com"


async def system_status_loop(rest: RestClient, ctx: ConnectorContext, poll_minutes: int = 5) -> None:
    while True:
        try:
            data = await rest.get_json(SYSTEM_STATUS_PATH, weight=1)
            await ctx.queue.put(
                Envelope(
                    product="EXCHANGE",
                    stream_name="systemStatus",
                    source_endpoint=rest._base_url + SYSTEM_STATUS_PATH,
                    kind="exchange_status",
                    payload={"status": data.get("status"), "msg": data.get("msg"), "raw": data},
                    symbol=None,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("system status poll failed")
            await log_system_event(ctx.db, "rest_failure", detail=f"system_status: {exc}", product="EXCHANGE")
        await asyncio.sleep(max(poll_minutes, 1) * 60)
