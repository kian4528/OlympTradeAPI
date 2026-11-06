from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional
import math

from .fct10s import Signal


@dataclass(frozen=True)
class VWAPReversalConfig:
    pair: str = "EURUSD_OTC"
    window_seconds: float = 20.0
    minimum_ticks: int = 30
    deviation_threshold: float = 0.00008
    maximum_deviation: float = 0.0008
    confirmation_move: float = 0.000015
    cooldown_seconds: float = 5.0


class VWAPDeviationReversalStrategy:
    """Experimental equal-weighted tick-average deviation reversal."""

    def __init__(self, config: VWAPReversalConfig = VWAPReversalConfig()):
        self.config = config
        self.prices: deque[tuple[float, float]] = deque()
        self.last_timestamp = 0.0
        self.last_signal_time = 0.0

    def on_tick(self, timestamp: float, price: float) -> Optional[Signal]:
        if not math.isfinite(timestamp) or not math.isfinite(price):
            return None
        if timestamp <= self.last_timestamp or price <= 0:
            return None

        self.last_timestamp = timestamp
        self.prices.append((timestamp, price))

        cutoff = timestamp - self.config.window_seconds
        while self.prices and self.prices[0][0] < cutoff:
            self.prices.popleft()

        if len(self.prices) < self.config.minimum_ticks:
            return None
        if timestamp - self.last_signal_time < self.config.cooldown_seconds:
            return None

        values = [p for _, p in self.prices]
        average = sum(values) / len(values)
        if average <= 0:
            return None

        deviation = (price - average) / average
        if abs(deviation) < self.config.deviation_threshold:
            return None
        if abs(deviation) > self.config.maximum_deviation:
            return None

        previous = values[-2]
        reversal = (price - previous) / previous

        if deviation > 0 and reversal <= -self.config.confirmation_move:
            direction = "down"
            reason = "Price above tick-weighted average with downward reversal"
        elif deviation < 0 and reversal >= self.config.confirmation_move:
            direction = "up"
            reason = "Price below tick-weighted average with upward reversal"
        else:
            return None

        self.last_signal_time = timestamp
        return Signal(
            direction=direction,
            timestamp=int(timestamp),
            entry_price=price,
            reason=reason,
        )
