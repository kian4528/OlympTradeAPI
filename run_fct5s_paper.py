import asyncio
import os
import time
from getpass import getpass

from olymptrade_ws.core.client import OlympTradeClient
from olymptrade_ws.strategy.fct10s import (
    FCT10sStrategy,
    PaperTrade,
    StrategyConfig,
    utc_time,
)

PAIR = "EURUSD_OTC"
STAKE = 1.00
EXPIRY_SECONDS = 5


class Runner:
    def __init__(self):
        self.strategy = FCT10sStrategy(
            StrategyConfig(pair=PAIR, expiry_seconds=EXPIRY_SECONDS)
        )
        self.client = None
        self.latest_price = None
        self.open_trade = None
        self.stop_event = asyncio.Event()
        self.ticks = 0
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.last_result_time = 0.0

    def on_tick(self, message):
        data = message.get("d", [])
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return

        for item in data:
            if not isinstance(item, dict) or item.get("p") != PAIR:
                continue
            try:
                timestamp = float(item["t"])
                price = float(item["q"])
            except (KeyError, TypeError, ValueError):
                continue

            if timestamp > 100_000_000_000:
                timestamp /= 1000.0
            if price <= 0:
                continue

            self.ticks += 1
            self.latest_price = price

            signal = self.strategy.on_tick(timestamp, price)
            if signal is not None and self.open_trade is None:
                self.open_paper_trade(signal)

            self.check_expiry()

            if self.ticks % 100 == 0:
                print(f"Ticks: {self.ticks} | {PAIR}: {price:.5f}")

    def open_paper_trade(self, signal):
        now = time.monotonic()
        self.open_trade = PaperTrade(
            direction=signal.direction,
            entry_price=self.latest_price,
            opened_at=now,
            expires_at=now + EXPIRY_SECONDS,
            signal_time=signal.timestamp,
        )
        print()
        print(f"SIGNAL: {signal.direction.upper()} | {PAIR}")
        print(f"Entry: {self.latest_price:.5f}")
        print(f"Stake reference: ${STAKE:.2f} | Expiry: {EXPIRY_SECONDS}s")
        print(f"Reason: {signal.reason}")

    def check_expiry(self):
        trade = self.open_trade
        if trade is None or time.monotonic() < trade.expires_at:
            return
        if self.latest_price is None:
            return

        exit_price = self.latest_price
        if trade.direction == "up":
            result = "WIN" if exit_price > trade.entry_price else "LOSS" if exit_price < trade.entry_price else "DRAW"
        else:
            result = "WIN" if exit_price < trade.entry_price else "LOSS" if exit_price > trade.entry_price else "DRAW"

        if result == "WIN":
            self.wins += 1
        elif result == "LOSS":
            self.losses += 1
        else:
            self.draws += 1

        print(f"RESULT: {result} | Entry: {trade.entry_price:.5f} | Exit: {exit_price:.5f}")
        print(f"Record: {self.wins}W / {self.losses}L / {self.draws}D")
        self.open_trade = None
        self.last_result_time = time.monotonic()

    async def run(self):
        token = os.environ.get("OLYMPTRADE_ACCESS_TOKEN")
        if not token:
            token = getpass("Access token: ").strip()
        if not token:
            raise SystemExit("An access token is required.")

        self.client = OlympTradeClient(access_token=token)
        started = False
        registered = False

        try:
            print()
            print("NIGHTSHIFT | FCT-5S")
            print(f"Instrument: {PAIR}")
            print(f"Stake reference: ${STAKE:.2f}")
            print(f"Expiry: {EXPIRY_SECONDS} seconds")
            print("Mode: PAPER")
            print("Broker orders: DISABLED")
            print()

            await self.client.start()
            started = True
            await self.client.initialize_session()
            self.client.register_callback(1, self.on_tick)
            registered = True
            await self.client.market.subscribe_ticks(PAIR)

            print(f"Live subscription active: {PAIR}")
            print("Strategy running. Press Ctrl+C to stop.")
            await self.stop_event.wait()

        finally:
            if started:
                if registered:
                    self.client.unregister_callback(1, self.on_tick)
                await self.client.stop()

            print()
            print("NIGHTSHIFT SESSION CLOSED")
            print(f"Ticks: {self.ticks}")
            print(f"Results: {self.wins}W / {self.losses}L / {self.draws}D")


if __name__ == "__main__":
    try:
        asyncio.run(Runner().run())
    except KeyboardInterrupt:
        pass
