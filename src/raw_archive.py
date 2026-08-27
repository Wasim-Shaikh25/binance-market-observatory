"""Streaming NDJSON + zstd raw archive (evidence store).

One collector run writes one archive file by default (`rotate: none`).
Optional `rotate: hour` opens a new file each UTC hour.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from .models import Envelope, resolve_source_type

logger = logging.getLogger(__name__)


class RawArchiveWriter:
    def __init__(self, path_template: str, rotate: str = "none"):
        self._path_template = path_template
        self._rotate = rotate
        self._raw_fh = None
        self._writer = None
        self._current_path: str | None = None
        self._current_hour: str | None = None
        self._lines = 0

    def _resolved_path(self) -> str:
        if self._rotate == "hour":
            hour = datetime.now(timezone.utc).strftime("%Y%m%dT%H")
            base = self._path_template
            if base.endswith(".ndjson.zst"):
                return base[: -len(".ndjson.zst")] + f"_{hour}.ndjson.zst"
            return f"{base}_{hour}"
        return self._path_template

    def _open_if_needed(self) -> None:
        path = self._resolved_path()
        hour = datetime.now(timezone.utc).strftime("%Y%m%dT%H") if self._rotate == "hour" else ""
        if self._writer is not None and path == self._current_path and (
            self._rotate != "hour" or hour == self._current_hour
        ):
            return
        self.close()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        try:
            import zstandard as zstd
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("zstandard package required for raw_archive sink") from exc
        self._raw_fh = open(path, "wb")
        self._writer = zstd.ZstdCompressor(level=3).stream_writer(self._raw_fh)
        self._current_path = path
        self._current_hour = hour
        logger.info("Raw archive opened: %s", path)

    def append(self, env: Envelope) -> None:
        self._open_if_needed()
        assert self._writer is not None
        line_obj = {
            "product": env.product,
            "symbol": env.symbol,
            "stream_name": env.stream_name,
            "source_endpoint": env.source_endpoint,
            "source_type": resolve_source_type(env),
            "schema_version": env.schema_version,
            "observed_at": env.observed_at,
            "kind": env.kind,
            "payload": env.payload,
        }
        data = (json.dumps(line_obj, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        self._writer.write(data)
        self._lines += 1

    def close(self) -> None:
        if self._writer is not None:
            try:
                self._writer.flush(complete_frame=True)  # type: ignore[call-arg]
            except TypeError:
                self._writer.flush()
            try:
                self._writer.close()
            finally:
                if self._raw_fh is not None:
                    self._raw_fh.close()
                logger.info("Raw archive closed: %s lines=%s", self._current_path, self._lines)
        self._writer = None
        self._raw_fh = None
        self._current_path = None
