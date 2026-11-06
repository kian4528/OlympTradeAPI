from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


class TickRecorder:
    """
    Session-based market-data recorder.

    Records ticks and strategy signals only.
    Does not record orders, trade outcomes, or performance history.
    Creates a separate CSV file for each program session.
    """

    def __init__(
        self,
        directory: str = "data/tick_sessions",
        flush_every: int = 64,
    ):
        if (
            not isinstance(flush_every, int)
            or isinstance(flush_every, bool)
            or flush_every < 1
        ):
            raise ValueError("flush_every must be a positive integer")

        self.directory = Path(directory)
        self.flush_every = flush_every
        self._pending_records = 0
        self.directory.mkdir(parents=True, exist_ok=True)

        session_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_id = session_time
        self.file_path = self.directory / f"ticks_{session_time}.csv"

        self.lock = Lock()
        self.closed = False

        self.file = self.file_path.open(
            "w",
            newline="",
            encoding="utf-8",
        )

        self.writer = csv.DictWriter(
            self.file,
            fieldnames=[
                "session_id",
                "record_type",
                "received_utc",
                "timestamp",
                "asset",
                "price",
                "strategy",
                "direction",
                "reason",
            ],
        )

        self.writer.writeheader()
        self.file.flush()

    def _write(self, record: dict) -> None:
        with self.lock:
            if self.closed:
                return

            self.writer.writerow(record)
            self._pending_records += 1
            if (
                self._pending_records >= self.flush_every
                or record["record_type"] == "signal"
            ):
                self.file.flush()
                self._pending_records = 0

    def record_tick(
        self,
        asset: str,
        timestamp: float,
        price: float,
        strategy: str = "",
    ) -> None:
        self._write({
            "session_id": self.session_id,
            "record_type": "tick",
            "received_utc": datetime.now(timezone.utc).isoformat(),
            "timestamp": timestamp,
            "asset": asset,
            "price": price,
            "strategy": strategy,
            "direction": "",
            "reason": "",
        })

    def record_signal(
        self,
        asset: str,
        timestamp: float,
        price: float,
        strategy: str,
        direction: str,
        reason: str,
    ) -> None:
        self._write({
            "session_id": self.session_id,
            "record_type": "signal",
            "received_utc": datetime.now(timezone.utc).isoformat(),
            "timestamp": timestamp,
            "asset": asset,
            "price": price,
            "strategy": strategy,
            "direction": direction,
            "reason": reason,
        })

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return

            self.file.flush()
            self.file.close()
            self.closed = True

    def __enter__(self) -> "TickRecorder":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
