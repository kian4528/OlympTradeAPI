import asyncio
import json
import math
import os
import time
from pathlib import Path
from getpass import getpass

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from olymptrade_ws.core.client import OlympTradeClient
from olymptrade_ws.strategy.fct10s import FCT10sStrategy, StrategyConfig
from olymptrade_ws.strategy.tick_recorder import TickRecorder
from olymptrade_ws.strategy.micro_mean_reversion import (
    MicroMeanReversionStrategy,
    MeanReversionConfig,
)
from olymptrade_ws.strategy.volatility_breakout import (
    VolatilitySqueezeBreakoutStrategy,
    BreakoutConfig,
)
from olymptrade_ws.strategy.adaptive_regime import (
    AdaptiveRegimeStrategy,
    AdaptiveRegimeConfig,
)
from olymptrade_ws.strategy.vwap_reversal import (
    VWAPDeviationReversalStrategy,
    VWAPReversalConfig,
)
from olymptrade_ws.strategy.support_resistance import (
    SupportResistanceRejectionStrategy,
    SupportResistanceConfig,
)
from olymptrade_ws.strategy.rsi_divergence import (
    RSIDivergenceStrategy,
    RSIDivergenceConfig,
)

from olymptrade_ws.olympconfig import parameters

DEFAULT_STAKE = 1.0
DEFAULT_EXPIRY_SECONDS = 5
CATEGORY = "digital"
INVENTORY_FILE = Path("data/fixed_time_assets.json")

STRATEGIES = {
    "1": {
        "name": "Micro Mean Reversion",
        "mode": "DEMO ORDERS",
    },
    "2": {
        "name": "Tick Momentum Continuation",
        "mode": "DEMO ORDERS",
    },
    "3": {
        "name": "Volatility Squeeze Breakout",
        "mode": "DEMO ORDERS",
    },
    "4": {
        "name": "Adaptive Regime",
        "mode": "DEMO ORDERS",
    },
    "5": {
        "name": "Tick-Weighted VWAP Deviation Reversal",
        "mode": "DEMO ORDERS",
    },
    "6": {
        "name": "Support & Resistance Rejection",
        "mode": "DEMO ORDERS",
    },
    "7": {
        "name": "RSI Divergence",
        "mode": "DEMO ORDERS",
    },
}


class Dashboard:
    def __init__(self):
        self.console = Console()
        self.rows = {}
        self.history = []
        self.live = None
        self.pair = ""
        self.stats = {}
        self._last_render_at = 0.0
        self._render_interval = 0.25

    def update(self, row, value):
        self.rows[row] = str(value)
        self.render()

    def add_trade(self, pair, status, change, direction):
        self.history.insert(0, {
            "pair": pair,
            "status": status.upper(),
            "change": change,
            "direction": direction.upper(),
        })
        self.history = self.history[:8]
        self.render()

    def render(self, force=False):
        now = time.monotonic()
        if not force and now - self._last_render_at < self._render_interval:
            return
        self._last_render_at = now

        session = Table.grid(expand=True, padding=(0, 1))
        session.add_column(style="bright_white", width=15)
        session.add_column(ratio=1)

        session.add_row("Instrument", Text(self.rows.get(4, "--"), style="bright_white"))
        session.add_row("Strategy", Text(self.rows.get(7, "--"), style="bright_white"))
        session.add_row("Mode", Text(self.rows.get(8, "--"), style="bright_white"))
        session.add_row("Account", Text(self.rows.get(5, "--"), style="bright_white"))
        session.add_row("Expiry", Text(self.rows.get(6, "--"), style="bright_white"))
        session.add_row("Price", Text(self.rows.get(9, "--"), style="bold white"))
        session.add_row("Ticks", Text(self.rows.get(10, "--"), style="bright_white"))
        session.add_row("Signal", Text(self.rows.get(11, "--"), style="bright_white"))

        trade_text = self.rows.get(12, "Trade      IDLE")
        trade_style = "white"
        if "UNCERTAIN" in trade_text or "HALTED" in trade_text:
            trade_style = "yellow"
        elif "LOSS" in trade_text:
            trade_style = "bold red"
        elif "WIN" in trade_text or "PROFIT" in trade_text:
            trade_style = "bold green"
        elif "DRAW" in trade_text or "AT ENTRY" in trade_text:
            trade_style = "white"
        elif "ACCEPTED" in trade_text or "SENT" in trade_text or "OPEN" in trade_text:
            trade_style = "cyan"

        session.add_row("Trade", Text(trade_text, style=trade_style))
        remaining_text = self.rows.get(13, "--")
        remaining_style = "bold red" if "AWAITING" in remaining_text else "white"
        session.add_row("Remaining", Text(remaining_text, style=remaining_style))

        s = self.stats
        total = s["trades"]
        rate = s["wins"] / total * 100 if total else 0

        performance = Table.grid(expand=True, padding=(0, 1))
        performance.add_column(style="bright_white", width=15)
        performance.add_column(ratio=1)

        performance.add_row("Trades", Text(str(total), style="bright_white"))
        performance.add_row("Wins", Text(str(s["wins"]), style="bold green"))
        performance.add_row("Losses", Text(str(s["losses"]), style="bold red"))
        performance.add_row("Draws", Text(str(s["draws"]), style="bold yellow"))
        performance.add_row("Win rate", Text(f"{rate:.1f}%", style="bright_white"))

        net_style = "green" if s["net"] > 0 else "red" if s["net"] < 0 else "white"
        performance.add_row(
            "Net P/L",
            Text(f"{s['net']:+.2f} USD", style=f"bold {net_style}"),
        )

        history = Table(box=box.SIMPLE_HEAD, expand=True, show_lines=False)
        history.add_column("Instrument", style="bright_white")
        history.add_column("Direction", style="bright_white")
        history.add_column("Result")
        history.add_column("P/L", justify="right")

        for item in self.history:
            status = item["status"]
            style = {
                "WIN": "bold green",
                "LOSS": "bold red",
                "DRAW": "bold yellow",
            }.get(status, "white")

            change = item["change"]
            amount_style = "green" if change > 0 else "red" if change < 0 else "yellow"

            history.add_row(
                item["pair"],
                item["direction"],
                Text(status, style=style),
                Text(f"{change:+.2f}", style=amount_style),
            )

        if not self.history:
            history.add_row("--", "--", "Waiting", "--")

        layout = Group(
            Panel(
                session,
                title="[bold bright_cyan]NIGHTSHIFT[/bold bright_cyan] [bright_white]AUTOMATED DEMO[/bright_white]",
                border_style="cyan",
            ),
            Panel(
                performance,
                title="[bold]SESSION PERFORMANCE[/bold]",
                border_style="blue",
            ),
            Panel(
                history,
                title="[bold]RECENT TRADES[/bold]",
                border_style="magenta",
            ),
            Text(self.rows.get(22, "Ctrl+C to stop"), style="bright_white"),
        )

        if self.live:
            self.live.update(layout)

    def start(self, pair, stats, strategy_name, mode, stake, expiry_seconds):
        self.pair = pair
        self.stats = stats

        self.rows = {
            4: pair,
            5: f"DEMO | STAKE {stake:.2f} USD",
            6: f"{expiry_seconds} seconds",
            7: strategy_name,
            8: mode,
            9: "Price      --",
            10: "Ticks      0",
            11: "Waiting for setup",
            12: "Trade      IDLE",
            13: "--",
            22: "DEMO ACTIVE | Ctrl+C to stop",
        }

        self.live = Live(
            console=self.console,
            refresh_per_second=4,
            screen=False,
        )
        self.live.start()
        self.render(force=True)

    def set_stats(self, stats):
        self.stats = stats
        self.render()

    def close(self):
        if self.live:
            self.live.stop()
            self.live = None


class Runner:
    def __init__(self):
        self.client = None
        self.dashboard = Dashboard()
        self.pair = None
        self.strategy = None
        self.strategy_name = ""
        self.strategy_mode = ""
        self.signal_only = False
        self.stake = DEFAULT_STAKE
        self.expiry_seconds = DEFAULT_EXPIRY_SECONDS
        self.inventory_messages = []
        self.ticks = 0
        self.order_lock = asyncio.Lock()
        self.active_order = False
        self.uncertain_order = False
        self.order_opened_at = None
        self.pending_entry_price = None
        self.pending_direction = None
        self.open_entry_price = None
        self.open_direction = None
        self.order_task = None
        self.stats = self.load_stats()
        self.recorder = None

    def load_stats(self):
        # Statistics are intentionally reset on every program launch.
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "net": 0.0,
            "closed_ids": set(),
            "last_close": "NONE",
        }

    def refresh_stats(self):
        self.dashboard.set_stats(self.stats)

    @staticmethod
    def event_data(message):
        data = message.get("d", [])
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    async def on_inventory(self, message):
        self.inventory_messages.append(message.get("d"))

    @staticmethod
    def is_locked(value):
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "locked")
        return bool(value)

    def get_currency_instruments(self):
        data = json.loads(INVENTORY_FILE.read_text())
        instruments = []

        for item in data.get("assets", []):
            durations = item.get("allowed_durations", [])
            if self.is_locked(item.get("locked")):
                continue
            if self.is_locked(item.get("locked_trading")):
                continue

            instruments.append({
                "id": str(item["id"]),
                "title": str(item.get("title") or item["id"]),
                "group": str(item.get("group", "unknown")),
                "profitability": float(item["profitability"]),
                "allowed_durations": durations,
                "locked": False,
                "locked_trading": False,
            })

        return sorted(
            instruments,
            key=lambda item: (-item["profitability"], item["title"].casefold()),
        )

    def choose_currency(self, instruments):
        if not instruments:
            raise RuntimeError("No eligible Fixed Time assets found.")

        table = Table(
            title="[bold bright_cyan]FIXED TIME ASSETS | 5-SECOND EXPIRY[/bold bright_cyan]",
            box=box.ROUNDED,
        )
        table.add_column("#", justify="right", style="bold")
        table.add_column("Instrument", style="bright_white")
        table.add_column("Payout", justify="right", style="green")
        table.add_column("Group", style="bright_blue")
        table.add_column("ID", style="bright_blue")

        for index, item in enumerate(instruments, 1):
            table.add_row(
                str(index),
                item["title"],
                f"{item['profitability']:.1f}%",
                item["group"],
                item["id"],
            )

        self.dashboard.console.print(table)

        while True:
            answer = self.dashboard.console.input(
                f"[bold bright_cyan]Select asset (1-{len(instruments)}): [/bold bright_cyan]"
            ).strip()

            try:
                choice = int(answer)
            except ValueError:
                self.dashboard.console.print("[red]Enter a valid number.[/red]")
                continue

            if 1 <= choice <= len(instruments):
                return instruments[choice - 1]

            self.dashboard.console.print("[red]Selection outside the listed range.[/red]")

    def choose_trade_settings(self, selected):
        raw_durations = selected.get("allowed_durations", [])
        allowed = sorted({
            int(value) for value in raw_durations
            if str(value).strip().isdigit() and int(value) > 0
        })

        if not allowed:
            raise RuntimeError(
                f"No supported trade durations listed for {selected['title']}."
            )

        default_duration = (
            DEFAULT_EXPIRY_SECONDS
            if DEFAULT_EXPIRY_SECONDS in allowed
            else allowed[0]
        )

        choices = ", ".join(str(value) for value in allowed)
        while True:
            raw = self.dashboard.console.input(
                f"[bold bright_cyan]Trade duration in seconds "
                f"({choices}; default {default_duration}): [/bold bright_cyan]"
            ).strip()

            try:
                duration = int(raw) if raw else default_duration
                if duration not in allowed:
                    raise ValueError
                break
            except ValueError:
                self.dashboard.console.print(
                    f"[red]Choose one of the supported durations: {choices}.[/red]"
                )

        while True:
            raw = self.dashboard.console.input(
                "[bold bright_cyan]Stake in USD (default 1.00): [/bold bright_cyan]"
            ).strip()
            try:
                stake = float(raw) if raw else DEFAULT_STAKE
                if not math.isfinite(stake) or stake <= 0:
                    raise ValueError
                break
            except ValueError:
                self.dashboard.console.print(
                    "[red]Enter a valid positive stake amount.[/red]"
                )

        self.expiry_seconds = duration
        self.stake = round(stake, 2)

        self.dashboard.console.print(
            f"[green]Selected: {self.expiry_seconds}s expiry | "
            f"${self.stake:.2f} stake[/green]"
        )

        self.dashboard.console.file.write(chr(27) + "[3J" + chr(27) + "[2J" + chr(27) + "[H")
        self.dashboard.console.file.flush()

    def choose_strategy(self):
        table = Table(
            title="[bold bright_cyan]NIGHTSHIFT STRATEGY SELECTOR[/bold bright_cyan]",
            box=box.ROUNDED,
        )
        table.add_column("#", justify="right", style="bold")
        table.add_column("Strategy", style="bold bright_cyan")
        table.add_column("Execution", style="yellow")

        for key, item in STRATEGIES.items():
            table.add_row(key, item["name"], item["mode"])

        self.dashboard.console.print(table)

        while True:
            answer = self.dashboard.console.input(
                "[bold bright_cyan]Select strategy (1-7): [/bold bright_cyan]"
            ).strip()

            if answer in STRATEGIES:
                return answer

            self.dashboard.console.print("[red]Choose a strategy from 1 to 7.[/red]")

    def on_accepted(self, message):
        self.open_entry_price = self.pending_entry_price
        self.open_direction = self.pending_direction
        self.pending_entry_price = None
        self.pending_direction = None
        self.active_order = True
        self.order_opened_at = asyncio.get_running_loop().time()
        self.dashboard.update(12, "Trade      ACCEPTED | OPEN")
        self.dashboard.update(13, f"{self.expiry_seconds:02d}s remaining")

    def on_closed(self, message):
        for item in self.event_data(message):
            trade_id = item.get("id")
            if (
                trade_id is not None
                and str(trade_id) in self.stats["closed_ids"]
            ):
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
                self.stats["closed_ids"].add(str(trade_id))

            self.stats["last_close"] = f"{status.upper()} | {change:+.2f} USD"

            direction = str(item.get("dir", item.get("direction", "--")))
            self.dashboard.add_trade(
                self.pair,
                status,
                change,
                direction,
            )
            self.refresh_stats()

        self.active_order = False
        self.uncertain_order = False
        self.order_opened_at = None
        self.pending_entry_price = None
        self.pending_direction = None
        self.open_entry_price = None
        self.open_direction = None
        self.dashboard.update(13, "--")
        result_label = self.stats["last_close"].split("|")[0].strip()
        self.dashboard.update(12, f"Trade      CLOSED | {result_label}")

    async def submit_signal(self, signal):
        async with self.order_lock:
            if self.active_order or self.uncertain_order:
                return

            if self.client.account_group != "demo":
                self.uncertain_order = True
                self.dashboard.update(
                    12, "Trade      HALTED | DEMO CHECK FAILED"
                )
                return

            self.pending_entry_price = float(signal.entry_price)
            self.pending_direction = str(signal.direction).lower()
            self.active_order = True
            self.dashboard.update(
                11,
                f"{signal.direction.upper()} @ {signal.entry_price:.5f}",
            )
            self.dashboard.update(12, "Trade      SUBMITTING")

            try:
                result = await self.client.trade.place_order(
                    pair=self.pair,
                    amount=self.stake,
                    direction=signal.direction,
                    duration=self.expiry_seconds,
                    account_id=self.client.account_id,
                    group="demo",
                    category=CATEGORY,
                    timestamp=signal.timestamp * 1000,
                )
            except Exception as exc:
                self.uncertain_order = True
                self.dashboard.update(
                    12,
                    f"Trade      UNCERTAIN | {type(exc).__name__}: {str(exc)[:90]}",
                )
                self.dashboard.update(
                    22, "HALTED: check demo account before restart"
                )
                return

            if result is None:
                self.uncertain_order = True
                self.dashboard.update(
                    12, "Trade      UNCERTAIN | NO CONFIRMATION"
                )
                self.dashboard.update(
                    22, "HALTED: check demo account before restart"
                )
                return

            self.dashboard.update(
                12, "Trade      SENT | WAITING FOR BROKER"
            )

    def on_tick(self, message):
        for item in self.event_data(message):
            if str(item.get("p", "")) != self.pair:
                continue

            try:
                timestamp = float(item["t"])
                price = float(item["q"])
            except (KeyError, TypeError, ValueError):
                continue

            if timestamp <= 0 or price <= 0:
                continue

            self.ticks += 1
            if self.recorder:
                self.recorder.record_tick(
                    self.pair, timestamp, price, self.strategy_name
                )
            self.dashboard.update(9, f"{price:.5f}")
            self.dashboard.update(10, str(self.ticks))

            if (
                self.active_order
                and self.order_opened_at is not None
                and self.open_entry_price is not None
                and self.open_direction in ("up", "down")
            ):
                entry = self.open_entry_price

                if price == entry:
                    live_status = "AT ENTRY"
                elif (
                    self.open_direction == "up" and price > entry
                ) or (
                    self.open_direction == "down" and price < entry
                ):
                    live_status = "IN PROFIT"
                else:
                    live_status = "IN LOSS"

                self.dashboard.update(
                    12,
                    f"Trade      ACCEPTED | {live_status} (INDICATIVE)",
                )

            if self.active_order or self.uncertain_order:
                continue

            signal = self.strategy.on_tick(timestamp, price)
            if signal is None:
                continue

            if self.recorder:
                self.recorder.record_signal(
                    self.pair,
                    signal.timestamp,
                    signal.entry_price,
                    self.strategy_name,
                    signal.direction,
                    signal.reason,
                )

            self.dashboard.update(
                11,
                f"{signal.direction.upper()} @ {signal.entry_price:.5f}",
            )

            if self.signal_only:
                self.dashboard.update(
                    12,
                    f"SIGNAL ONLY | {signal.reason[:65]}",
                )
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

        self.client = OlympTradeClient(access_token=token)
        started = False

        callbacks = [
            (parameters.E_TICK_UPDATE, self.on_tick),
            (parameters.E_TRADE_ACCEPTED, self.on_accepted),
            (parameters.E_TRADE_CLOSED, self.on_closed),
        ]

        try:
            await self.client.start()
            started = True
            await self.client.initialize_session()

            if (
                self.client.account_group != "demo"
                or not isinstance(self.client.account_id, int)
                or self.client.account_id <= 0
            ):
                raise RuntimeError("Verified demo account required.")

            instruments = self.get_currency_instruments()
            selected = self.choose_currency(instruments)
            self.pair = selected["id"]

            strategy_choice = self.choose_strategy()
            self.choose_trade_settings(selected)

            if strategy_choice == "1":
                self.strategy = MicroMeanReversionStrategy(
                    MeanReversionConfig(pair=self.pair)
                )
            elif strategy_choice == "2":
                self.strategy = FCT10sStrategy(
                    StrategyConfig(
                        pair=self.pair,
                        expiry_seconds=self.expiry_seconds,
                    )
                )
            elif strategy_choice == "3":
                self.strategy = VolatilitySqueezeBreakoutStrategy(
                    BreakoutConfig(pair=self.pair)
                )
            elif strategy_choice == "4":
                self.strategy = AdaptiveRegimeStrategy(
                    AdaptiveRegimeConfig(pair=self.pair)
                )
            elif strategy_choice == "5":
                self.strategy = VWAPDeviationReversalStrategy(
                    VWAPReversalConfig(pair=self.pair)
                )
            elif strategy_choice == "6":
                self.strategy = SupportResistanceRejectionStrategy(
                    SupportResistanceConfig(pair=self.pair)
                )
            elif strategy_choice == "7":
                self.strategy = RSIDivergenceStrategy(
                    RSIDivergenceConfig(pair=self.pair)
                )
            else:
                raise ValueError("Invalid strategy selection.")

            self.strategy_name = STRATEGIES[strategy_choice]["name"]
            self.strategy_mode = STRATEGIES[strategy_choice]["mode"]
            self.signal_only = False

            self.dashboard.start(
                selected["title"],
                self.stats,
                self.strategy_name,
                self.strategy_mode,
                self.stake,
                self.expiry_seconds,
            )

            self.recorder = TickRecorder()
            self.dashboard.update(
                22, f"RECORDING TICKS | {self.recorder.file_path}"
            )

            for event_code, callback in callbacks:
                self.client.register_callback(event_code, callback)

            await self.client.market.subscribe_ticks(self.pair)

            self.dashboard.update(
                22,
                f"DEMO ACTIVE | ACCOUNT {self.client.account_id} | Ctrl+C to stop",
            )

            while True:
                if self.active_order and self.order_opened_at is not None:
                    elapsed = asyncio.get_running_loop().time() - self.order_opened_at
                    remaining = max(0, self.expiry_seconds - elapsed)
                    if remaining > 0:
                        self.dashboard.update(13, f"{remaining:04.1f}s remaining")
                    else:
                        self.dashboard.update(13, "00.0s | AWAITING CLOSURE")
                await asyncio.sleep(0.25)

        finally:
            if self.order_task and not self.order_task.done():
                self.order_task.cancel()
                await asyncio.gather(
                    self.order_task, return_exceptions=True
                )

            if started:
                for event_code, callback in callbacks:
                    self.client.unregister_callback(event_code, callback)

                await self.client.stop()

            if self.recorder:
                self.recorder.close()
                self.recorder = None

            self.dashboard.close()


if __name__ == "__main__":
    try:
        asyncio.run(Runner().run())
    except KeyboardInterrupt:
        pass
