from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional
import math

from .fct10s import Signal


@dataclass(frozen=True)
class RSIDivergenceConfig:
    pair: str = "EURUSD_OTC"
    window_seconds: float = 45.0
    minimum_ticks: int = 40
    rsi_period: int = 14
    minimum_price_change: float = 0.00002
    minimum_rsi_difference: float = 3.0
    confirmation_move: float = 0.000015
    cooldown_seconds: float = 5.0


class RSIDivergenceStrategy:
    """Experimental two-window RSI divergence signal generator."""

    def __init__(self, config: RSIDivergenceConfig = RSIDivergenceConfig()):
        self.config = config
        self.prices: deque[tuple[float, float]] = deque()
        self.last_timestamp = 0.0
        self.last_signal_time = 0.0

    @staticmethod
    def calculate_rsi(values: list[float], period: int) -> Optional[float]:
        if len(values) < period + 1:
            return None

        changes = [
            values[i] - values[i - 1]
            for i in range(1, len(values))
        ]
        recent = changes[-period:]
        gains = sum(max(change, 0.0) for change in recent) / period
        losses = sum(max(-change, 0.0) for change in recent) / period

        if losses == 0:
            return 100.0 if gains > 0 else 50.0

        rs = gains / losses
        return 100.0 - (100.0 / (1.0 + rs))

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

        if len(self.prices) < max(
            self.config.minimum_ticks,
            (self.config.rsi_period + 1) * 2,
        ):
            return None

        if timestamp - self.last_signal_time < self.config.cooldown_seconds:
            return None

        values = [value for _, value in self.prices]
        midpoint = len(values) // 2

        if midpoint < self.config.rsi_period + 1:
            return None

        first = values[:midpoint]
        second = values[midpoint:]

        first_rsi = self.calculate_rsi(first, self.config.rsi_period)
        second_rsi = self.calculate_rsi(second, self.config.rsi_period)

        if first_rsi is None or second_rsi is None:
            return None

        first_low = min(first)
        second_low = min(second)
        first_high = max(first)
        second_high = max(second)

        previous = values[-2]
        reversal = (price - previous) / previous

        bullish = (
            second_low < first_low - self.config.minimum_price_change
            and second_rsi > first_rsi + self.config.minimum_rsi_difference
            and reversal >= self.config.confirmation_move
        )

        bearish = (
            second_high > first_high + self.config.minimum_price_change
            and second_rsi < first_rsi - self.config.minimum_rsi_difference
            and reversal <= -self.config.confirmation_move
        )

        if bullish:
            direction = "up"
            reason = "Bullish RSI divergence with upward confirmation"
        elif bearish:
            direction = "down"
            reason = "Bearish RSI divergence with downward confirmation"
        else:
            return None

        self.last_signal_time = timestamp
        return Signal(
            direction=direction,
            timestamp=int(timestamp),
            entry_price=price,
            reason=reason,
        )
