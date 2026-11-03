from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import math


@dataclass(frozen=True)
class Signal:
    direction: str
    timestamp: int
    entry_price: float
    reason: str


@dataclass
class PaperTrade:
    direction: str
    entry_price: float
    opened_at: float
    expires_at: float
    signal_time: int


@dataclass(frozen=True)
class StrategyConfig:
    pair: str = "EURUSD_OTC"
    expiry_seconds: int = 5
    window_seconds: float = 12.0
    minimum_ticks: int = 12
    momentum_threshold: float = 0.000015
    volatility_multiplier: float = 0.15
    cooldown_seconds: float = 5.0
    maximum_spread_move: float = 0.0008


class FCT10sStrategy:
    def __init__(self, config: StrategyConfig = StrategyConfig()):
        self.config = config
        self.prices = deque()
        self.last_signal_time = 0.0
        self.last_timestamp = 0.0

    def ready(self) -> bool:
        return len(self.prices) >= self.config.minimum_ticks

    def on_tick(self, timestamp: float, price: float) -> Optional[Signal]:
        if not math.isfinite(timestamp) or not math.isfinite(price) or price <= 0:
            return None

        if timestamp <= self.last_timestamp:
            return None

        self.last_timestamp = timestamp
        self.prices.append((timestamp, price))

        cutoff = timestamp - self.config.window_seconds
        while self.prices and self.prices[0][0] < cutoff:
            self.prices.popleft()

        if not self.ready():
            return None

        if timestamp - self.last_signal_time < self.config.cooldown_seconds:
            return None

        values = [item[1] for item in self.prices]
        first = values[0]
        latest = values[-1]

        if first <= 0:
            return None

        movement = (latest - first) / first
        changes = [
            abs(values[i] - values[i - 1]) / values[i - 1]
            for i in range(1, len(values))
            if values[i - 1] > 0
        ]

        if not changes:
            return None

        average_move = sum(changes) / len(changes)
        if average_move <= 0:
            return None

        if abs(movement) > self.config.maximum_spread_move:
            return None

        threshold = max(
            self.config.momentum_threshold,
            average_move * self.config.volatility_multiplier,
        )

        if abs(movement) < threshold:
            return None

        midpoint = len(values) // 2
        if midpoint < 2:
            return None

        earlier = values[:midpoint]
        later = values[midpoint:]

        first_momentum = (earlier[-1] - earlier[0]) / earlier[0]
        second_momentum = (later[-1] - later[0]) / later[0]

        if movement > 0 and first_momentum > 0 and second_momentum > 0:
            direction = "up"
        elif movement < 0 and first_momentum < 0 and second_momentum < 0:
            direction = "down"
        else:
            return None

        self.last_signal_time = timestamp

        return Signal(
            direction=direction,
            timestamp=int(timestamp),
            entry_price=latest,
            reason="Consistent short-window tick momentum",
        )


def utc_time(timestamp: float) -> str:
    return datetime.fromtimestamp(
        timestamp, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")
