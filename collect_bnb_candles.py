import asyncio
import csv
import logging
import os
import time
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path

from olymptrade_ws.core.client import OlympTradeClient
from olymptrade_ws.olympconfig import parameters

logging.disable(logging.CRITICAL)

PAIR = "EURUSD"
OUTPUT = Path("data/eurusd_1m.csv")
FIELDS = ["timestamp", "open", "high", "low", "close", "tick_count"]


def parse_epoch(value):
    value = float(value)
    if value > 100_000_000_000:
        value /= 1000.0
    if not 1_500_000_000 <= value <= 4_200_000_000:
        raise ValueError("Unexpected timestamp")
    return value


class Collector:
    def __init__(self):
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        if not OUTPUT.exists() or OUTPUT.stat().st_size == 0:
            with OUTPUT.open("w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDS).writeheader()

        self.current = None
        self.ticks = 0
        self.ignored = 0

    def save(self, candle):
        row = {
            "timestamp": candle["minute"].isoformat(timespec="seconds"),
            "open": f'{candle["open"]:.10g}',
            "high": f'{candle["high"]:.10g}',
            "low": f'{candle["low"]:.10g}',
            "close": f'{candle["close"]:.10g}',
            "tick_count": candle["tick_count"],
        }
        with OUTPUT.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
            f.flush()
            os.fsync(f.fileno())

        print(
            f'Saved {row["timestamp"]} UTC | '
            f'O={row["open"]} H={row["high"]} '
            f'L={row["low"]} C={row["close"]} '
            f'ticks={row["tick_count"]}',
            flush=True,
        )

    def on_tick(self, message):
        data = message.get("d")
        items = [data] if isinstance(data, dict) else (
            [x for x in data if isinstance(x, dict)]
            if isinstance(data, list) else []
        )

        for item in items:
            if item.get("p") != PAIR:
                continue

            try:
                price = float(item["q"])
                epoch = parse_epoch(item["t"])
                minute = datetime.fromtimestamp(
                    int(epoch // 60) * 60, timezone.utc
                )
                if price <= 0:
                    raise ValueError("Invalid price")
            except (KeyError, TypeError, ValueError, OverflowError):
                self.ignored += 1
                continue

            if self.current and minute < self.current["minute"]:
                self.ignored += 1
                continue

            self.ticks += 1

            if self.current is None or minute > self.current["minute"]:
                if self.current:
                    self.save(self.current)

                self.current = {
                    "minute": minute,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "tick_count": 1,
                }
            else:
                self.current["high"] = max(self.current["high"], price)
                self.current["low"] = min(self.current["low"], price)
                self.current["close"] = price
                self.current["tick_count"] += 1

    def finish(self):
        if self.current:
            self.save(self.current)
            self.current = None


async def main():
    token = getpass("OlympTrade access token (hidden): ").strip()
    if not token:
        print("No token entered.")
        return

    client = OlympTradeClient(token, log_raw_messages=False)
    collector = Collector()
    started = False

    async def on_tick(message):
        collector.on_tick(message)

    client.register_callback(parameters.E_TICK_UPDATE, on_tick)

    try:
        print(f"Connecting for {PAIR}...")
        await client.start()
        started = True
        await client.initialize_session()

        print(f"Subscribing to {PAIR} ticks...")
        await client.market.subscribe_ticks(PAIR)

        print(f"Collecting candles into {OUTPUT}")
        print("Press Ctrl+C to stop safely.")

        while True:
            await asyncio.sleep(1)

    finally:
        client.unregister_callback(parameters.E_TICK_UPDATE, on_tick)

        if started:
            await client.stop()

        collector.finish()

        print("EURUSD ticks:", collector.ticks)
        print("Ignored records:", collector.ignored)
        print("CSV:", OUTPUT.resolve())
        print("Collector stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
