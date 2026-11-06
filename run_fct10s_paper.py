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
EXPIRY_SECONDS = 10
HISTORY_COUNT = 600


class PaperRunner:
    def __init__(self):
        self.strategy = FCT10sStrategy(
            StrategyConfig(
                pair=PAIR,
                expiry_seconds=EXPIRY_SECONDS,
            )
        )
        self.latest_price = None
        self.open_trade = None
        self.closed_trades = 0
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.ignored = 0
        self.received_ticks = 0
        self.client = None
        self.stop_event = asyncio.Event()

    def on_tick(self, message):
        data = message.get("d", [])
        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            self.ignored += 1
            return

        for item in data:
            if not isinstance(item, dict) or item.get("p") != PAIR:
                continue

            try:
                timestamp = float(item["t"])
                price = float(item["q"])
            except (KeyError, TypeError, ValueError):
                self.ignored += 1
                continue

            if timestamp > 100_000_000_000:
                timestamp /= 1000.0

            if price <= 0:
                self.ignored += 1
                continue

            self.received_ticks += 1
            self.latest_price = price

            if self.received_ticks == 1:
                print(f"\nFirst live tick: {price:.5f} | {utc_time(timestamp)}")
            elif self.received_ticks % 100 == 0:
                print(f"Ticks: {self.received_ticks} | Price: {price:.5f}")

            signal = self.strategy.on_tick(timestamp, price)
            if signal is not None:
                self.open_paper_trade(signal)

            self.check_expiry()

    def open_paper_trade(self, signal):
        if self.open_trade is not None:
            return

        now = time.monotonic()
        self.open_trade = PaperTrade(
            direction=signal.direction,
            entry_price=self.latest_price,
            opened_at=now,
            expires_at=now + EXPIRY_SECONDS,
            signal_time=signal.timestamp,
        )

        print()
        print("NIGHTSHIFT | PAPER TRADE")
        print(f"Instrument: {PAIR}")
        print(f"Direction: {signal.direction.upper()}")
        print(f"Entry: {self.latest_price:.5f}")
        print(f"Stake reference: ${STAKE:.2f}")
        print(f"Expiry: {EXPIRY_SECONDS}s")
        print(f"Signal: {signal.reason}")
        print(f"Time: {utc_time(signal.timestamp)}")

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

        self.closed_trades += 1
        if result == "WIN":
            self.wins += 1
        elif result == "LOSS":
            self.losses += 1
        else:
            self.draws += 1

        print()
        print(f"Paper result: {result}")
        print(f"Entry: {trade.entry_price:.5f} | Exit: {exit_price:.5f}")
        print(f"Record: {self.wins}W / {self.losses}L / {self.draws}D")

        self.open_trade = None

    async def load_startup_history(self):
        print("Loading historical M5 candles...")
        m5 = await self.client.market.get_candles(
            PAIR,
            size=300,
            count=HISTORY_COUNT,
        )

        print("Loading historical M15 candles...")
        m15 = await self.client.market.get_candles(
            PAIR,
            size=900,
            count=HISTORY_COUNT,
        )

        m5_count, m15_count = self.strategy.load_history(
            m5,
            m15,
            now=time.time(),
        )

        required = max(
            self.strategy.config.minimum_candles,
            self.strategy.config.ema_slow + 2,
            self.strategy.config.atr_period + 2,
        )

        print(f"M5 candles: {m5_count} | M15 candles: {m15_count}")
        if m5_count < required or m15_count < required:
            raise RuntimeError("Insufficient historical candles.")

        print("Strategy warm-up: READY")

    async def run(self):
        token = os.environ.get("OLYMPTRADE_ACCESS_TOKEN")
        if not token:
            token = getpass("Access token: ").strip()

        if not token:
            raise SystemExit("An access token is required.")

        self.client = OlympTradeClient(access_token=token)
        started = False
        callback_registered = False

        try:
            print()
            print("NIGHTSHIFT | FCT-1R")
            print(f"Instrument: {PAIR}")
            print(f"Stake reference: ${STAKE:.2f}")
            print(f"Expiry: {EXPIRY_SECONDS} seconds")
            print("Mode: PAPER")
            print("Order placement: DISABLED")
            print()

            await self.client.start()
            started = True
            await self.client.initialize_session()
            await self.load_startup_history()

            self.client.register_callback(1, self.on_tick)
            callback_registered = True
            await self.client.market.subscribe_ticks(PAIR)

            print(f"Live subscription: {PAIR}")
            print("Strategy running. Press Ctrl+C to stop.")

            await self.stop_event.wait()

        finally:
            if started:
                if callback_registered:
                    self.client.unregister_callback(1, self.on_tick)
                await self.client.stop()

            print()
            print("NIGHTSHIFT SESSION CLOSED")
            print(f"Ticks: {self.received_ticks}")
            print(f"Results: {self.wins}W / {self.losses}L / {self.draws}D")


if __name__ == "__main__":
    runner = PaperRunner()
    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        pass
