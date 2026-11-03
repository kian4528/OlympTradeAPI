import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from getpass import getpass

from olymptrade_ws.core.client import OlympTradeClient
from olymptrade_ws.strategy.fct10s import FCT10sStrategy, StrategyConfig
from olymptrade_ws.olympconfig import parameters

logging.disable(logging.CRITICAL)

PAIR = "EURUSD_OTC"
STAKE = 1
EXPIRY_SECONDS = 5
CATEGORY = "digital"
STATS_FILE = Path("nightshift_stats.json")


class Dashboard:
    def __init__(self):
        self.rows = {}

    def update(self, row, value):
        if self.rows.get(row) == value:
            return
        self.rows[row] = value
        sys.stdout.write(f"\033[{row};1H\033[2K{value}")
        sys.stdout.flush()

    def start(self):
        sys.stdout.write("\033[2J\033[H\033[?25l")
        sys.stdout.flush()
        self.update(1, "NIGHTSHIFT | AUTOMATED DEMO")
        self.update(2, "━" * 48)
        self.update(4, f"PAIR       {PAIR}")
        self.update(5, f"ACCOUNT    DEMO | STAKE {STAKE} USD")
        self.update(6, f"EXPIRY     {EXPIRY_SECONDS} SECONDS")
        self.update(8, "SESSION")
        self.update(9, "Price      --")
        self.update(10, "Ticks      0")
        self.update(11, "Signal     Waiting for setup")
        self.update(12, "Trade      IDLE")
        self.update(14, "PERFORMANCE")
        self.update(15, "Trades     0")
        self.update(16, "Wins       0     Losses 0     Draws 0")
        self.update(17, "Win rate   0.0%")
        self.update(18, "Net P/L    +0.00 USD")
        self.update(20, "Last close NONE")
        self.update(22, "Ctrl+C to stop")

    def close(self):
        sys.stdout.write("\033[?25h\n")
        sys.stdout.flush()


class Runner:
    def __init__(self):
        self.client = None
        self.dashboard = Dashboard()
        self.strategy = FCT10sStrategy(
            StrategyConfig(pair=PAIR, expiry_seconds=EXPIRY_SECONDS)
        )
        self.ticks = 0
        self.order_lock = asyncio.Lock()
        self.active_order = False
        self.uncertain_order = False
        self.order_task = None
        self.stats = self.load_stats()

    def load_stats(self):
        default = {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "net": 0.0,
            "closed_ids": [],
            "last_close": "NONE",
        }
        try:
            if STATS_FILE.exists():
                data = json.loads(STATS_FILE.read_text())
                for key in default:
                    if key in data:
                        default[key] = data[key]
        except (OSError, ValueError, TypeError):
            pass
        return default

    def save_stats(self):
        temp = STATS_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(self.stats, indent=2))
        temp.replace(STATS_FILE)

    def refresh_stats(self):
        s = self.stats
        rate = (s["wins"] / s["trades"] * 100) if s["trades"] else 0
        self.dashboard.update(15, f"Trades     {s['trades']}")
        self.dashboard.update(
            16,
            f"Wins       {s['wins']}     Losses {s['losses']}     Draws {s['draws']}",
        )
        self.dashboard.update(17, f"Win rate   {rate:.1f}%")
        self.dashboard.update(18, f"Net P/L    {s['net']:+.2f} USD")
        self.dashboard.update(20, f"Last close {s['last_close']}")

    @staticmethod
    def event_data(message):
        data = message.get("d", [])
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    async def on_interim(self, message):
        for item in self.event_data(message):
            status = item.get("status", "in progress")
            self.dashboard.update(12, f"Trade      {str(status).upper()}")

    async def on_accepted(self, message):
        self.active_order = True
        self.dashboard.update(12, "Trade      ACCEPTED | OPEN")

    async def on_closed(self, message):
        for item in self.event_data(message):
            trade_id = item.get("id")
            if trade_id is not None and str(trade_id) in self.stats["closed_ids"]:
                continue

            status = str(item.get("status", "")).lower()
            try:
                change = float(item.get("balance_change", 0) or 0)
            except (TypeError, ValueError):
                change = 0.0

            if status not in ("win", "loss", "draw"):
                if change > 0:
                    status = "win"
                elif change < 0:
                    status = "loss"
                else:
                    status = "draw"

            self.stats["trades"] += 1
            self.stats["net"] += change

            if status == "win":
                self.stats["wins"] += 1
            elif status == "loss":
                self.stats["losses"] += 1
            else:
                self.stats["draws"] += 1

            if trade_id is not None:
                self.stats["closed_ids"].append(str(trade_id))

            self.stats["last_close"] = (
                f"{status.upper()} | {change:+.2f} USD"
            )
            self.save_stats()
            self.refresh_stats()

        self.active_order = False
        self.uncertain_order = False
        self.dashboard.update(12, "Trade      CLOSED | READY")

    async def submit_signal(self, signal):
        async with self.order_lock:
            if self.active_order or self.uncertain_order:
                return

            if self.client.account_group != "demo":
                self.uncertain_order = True
                self.dashboard.update(12, "Trade      HALTED | DEMO CHECK FAILED")
                return

            self.active_order = True
            self.dashboard.update(
                11,
                f"Signal     {signal.direction.upper()} @ {signal.entry_price:.5f}",
            )
            self.dashboard.update(12, "Trade      SUBMITTING")

            try:
                result = await self.client.trade.place_order(
                    pair=PAIR,
                    amount=STAKE,
                    direction=signal.direction,
                    duration=EXPIRY_SECONDS,
                    account_id=self.client.account_id,
                    group="demo",
                    category=CATEGORY,
                    timestamp=signal.timestamp * 1000,
                )
            except Exception as exc:
                self.uncertain_order = True
                self.dashboard.update(
                    12, f"Trade      UNCERTAIN | {type(exc).__name__}"
                )
                self.dashboard.update(22, "HALTED: check demo account before restart")
                return

            if result is None:
                self.uncertain_order = True
                self.dashboard.update(12, "Trade      UNCERTAIN | NO CONFIRMATION")
                self.dashboard.update(22, "HALTED: check demo account before restart")
                return

            self.dashboard.update(12, "Trade      SENT | WAITING FOR BROKER")

    async def on_tick(self, message):
        for item in self.event_data(message):
            if item.get("p") != PAIR:
                continue
            try:
                timestamp = float(item["t"])
                price = float(item["q"])
            except (KeyError, TypeError, ValueError):
                continue
            if timestamp <= 0 or price <= 0:
                continue

            self.ticks += 1
            self.dashboard.update(9, f"Price      {price:.5f}")
            self.dashboard.update(10, f"Ticks      {self.ticks}")

            if self.active_order or self.uncertain_order:
                continue

            signal = self.strategy.on_tick(timestamp, price)
            if signal is None:
                continue

            if self.order_task is None or self.order_task.done():
                self.order_task = asyncio.create_task(
                    self.submit_signal(signal)
                )

    async def run(self):
        token = os.environ.get("OLYMPTRADE_ACCESS_TOKEN")
        if not token:
            token = getpass("Access token: ").strip()
        if not token:
            raise SystemExit("An access token is required.")

        self.dashboard.start()
        self.refresh_stats()
        self.client = OlympTradeClient(access_token=token)
        started = False

        callbacks = [
            (parameters.E_TICK_UPDATE, self.on_tick),
            (parameters.E_TRADE_UPDATE_INTERIM, self.on_interim),
            (parameters.E_TRADE_ACCEPTED, self.on_accepted),
            (parameters.E_TRADE_CLOSED, self.on_closed),
        ]

        try:
            await self.client.start()
            started = True
            await self.client.initialize_session()

            if self.client.account_group != "demo" or not self.client.account_id:
                raise RuntimeError("Verified demo account required.")

            for event_code, callback in callbacks:
                self.client.register_callback(event_code, callback)

            await self.client.market.subscribe_ticks(PAIR)
            self.dashboard.update(
                22, f"DEMO ACTIVE | ACCOUNT {self.client.account_id} | Ctrl+C to stop"
            )

            while True:
                await asyncio.sleep(0.5)

        finally:
            if self.order_task and not self.order_task.done():
                self.order_task.cancel()
                await asyncio.gather(self.order_task, return_exceptions=True)

            if started:
                for event_code, callback in callbacks:
                    self.client.unregister_callback(event_code, callback)
                await self.client.stop()

            self.dashboard.close()


if __name__ == "__main__":
    try:
        asyncio.run(Runner().run())
    except KeyboardInterrupt:
        pass
