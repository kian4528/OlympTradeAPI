import asyncio
import logging
import os
import sys
import time
from getpass import getpass

from olymptrade_ws.core.client import OlympTradeClient
from olymptrade_ws.strategy.fct10s import FCT10sStrategy, StrategyConfig

logging.disable(logging.CRITICAL)

PAIR = "EURUSD_OTC"
STAKE = 1.00
EXPIRY_SECONDS = 5


class Dashboard:
    def __init__(self):
        self.fields = {}
        self.started = False

    def update(self, key, value, row):
        value = str(value)
        if self.fields.get(key) == value:
            return
        self.fields[key] = value
        sys.stdout.write(f"\033[{row};1H\033[2K{value}")
        sys.stdout.flush()

    def start(self):
        sys.stdout.write("\033[2J\033[H\033[?25l")
        sys.stdout.flush()
        self.started = True
        self.update("title", "NIGHTSHIFT | FCT-5S", 1)
        self.update("line", "=" * 52, 2)
        self.update("pair", f"Instrument       {PAIR}", 4)
        self.update("stake", f"Stake            ${STAKE:.2f}", 5)
        self.update("expiry", f"Expiry           {EXPIRY_SECONDS}s", 6)
        self.update("mode", "Execution        DEMO VERIFICATION REQUIRED", 7)
        self.update("orders", "Order submission LOCKED", 8)
        self.update("separator", "-" * 52, 10)
        self.update("price", "Latest price     --", 11)
        self.update("ticks", "Ticks            0", 12)
        self.update("signal", "Latest signal    --", 13)
        self.update("position", "Position         NONE", 14)
        self.update("record", "Results          0W / 0L / 0D", 15)
        self.update("status", "Status           Connecting", 17)
        self.update("footer", "Press Ctrl+C to stop", 19)

    def close(self):
        if self.started:
            sys.stdout.write("\033[?25h\n")
            sys.stdout.flush()


class Runner:
    def __init__(self):
        self.strategy = FCT10sStrategy(
            StrategyConfig(pair=PAIR, expiry_seconds=EXPIRY_SECONDS)
        )
        self.client = None
        self.dashboard = Dashboard()
        self.latest_price = None
        self.open_trade = None
        self.ticks = 0
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.last_signal = "--"

    async def on_tick(self, message):
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
            self.dashboard.update(
                "price", f"Latest price     {price:.5f}", 11
            )
            self.dashboard.update(
                "ticks", f"Ticks            {self.ticks}", 12
            )

            signal = self.strategy.on_tick(timestamp, price)
            if signal is not None and self.open_trade is None:
                self.open_trade = {
                    "direction": signal.direction,
                    "entry": price,
                    "opened": time.monotonic(),
                    "expires": time.monotonic() + EXPIRY_SECONDS,
                }
                self.last_signal = (
                    f"{signal.direction.upper()} | {signal.reason}"
                )
                self.dashboard.update(
                    "signal", f"Latest signal    {self.last_signal[:100]}", 13
                )
                self.dashboard.update(
                    "position",
                    f"Position         {signal.direction.upper()} @ {price:.5f}",
                    14,
                )

            await self.check_expiry()

    async def check_expiry(self):
        trade = self.open_trade
        if trade is None or time.monotonic() < trade["expires"]:
            return
        if self.latest_price is None:
            return

        exit_price = self.latest_price
        if trade["direction"] == "up":
            result = (
                "WIN" if exit_price > trade["entry"]
                else "LOSS" if exit_price < trade["entry"]
                else "DRAW"
            )
        else:
            result = (
                "WIN" if exit_price < trade["entry"]
                else "LOSS" if exit_price > trade["entry"]
                else "DRAW"
            )

        if result == "WIN":
            self.wins += 1
        elif result == "LOSS":
            self.losses += 1
        else:
            self.draws += 1

        self.dashboard.update(
            "record",
            f"Results          {self.wins}W / {self.losses}L / {self.draws}D",
            15,
        )
        self.dashboard.update("position", f"Position         {result}", 14)
        self.open_trade = None

    async def run(self):
        token = os.environ.get("OLYMPTRADE_ACCESS_TOKEN")
        if not token:
            token = getpass("Access token: ").strip()
        if not token:
            raise SystemExit("An access token is required.")

        self.client = OlympTradeClient(access_token=token)
        started = False
        registered = False
        self.dashboard.start()

        try:
            await self.client.start()
            started = True
            await self.client.initialize_session()
            self.client.register_callback(1, self.on_tick)
            registered = True
            await self.client.market.subscribe_ticks(PAIR)

            self.dashboard.update(
                "status", f"Status           Live feed active | {PAIR}", 17
            )
            while True:
                await self.check_expiry()
                await asyncio.sleep(0.1)

        finally:
            if started:
                if registered:
                    self.client.unregister_callback(1, self.on_tick)
                await self.client.stop()
            self.dashboard.close()


if __name__ == "__main__":
    try:
        asyncio.run(Runner().run())
    except KeyboardInterrupt:
        pass
