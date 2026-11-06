from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional
import math

from .fct10s import Signal


@dataclass(frozen=True)
class SupportResistanceConfig:
    pair: str = "EURUSD_OTC"
    window_seconds: float = 30.0
    minimum_ticks: int = 35
    level_tolerance: float = 0.000025
    rejection_confirmation: float = 0.00002
    minimum_tests: int = 2
    cooldown_seconds: float = 5.0


class SupportResistanceRejectionStrategy:
    """Experimental repeated-level rejection signal generator."""

    def __init__(
        self,
        config: SupportResistanceConfig = SupportResistanceConfig(),
    ):
        self.config = config
        self.prices: deque[tuple[float, float]] = deque()
        self.last_timestamp = 0.0
        self.last_signal_time = 0.0

    def _find_level(self, values: list[float], mode: str):
        tolerance = self.config.level_tolerance
        candidates = sorted(values)

        best_level = None
        best_tests = 0

        for candidate in candidates:
            tests = sum(
                1 for value in values
                if abs(value - candidate) <= tolerance
            )

            if tests > best_tests:
                best_level = candidate
                best_tests = tests

        if best_tests < self.config.minimum_tests:
            return None, best_tests

        return best_level, best_tests

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

        values = [value for _, value in self.prices]
        history = values[:-1]

        if len(history) < 3:
            return None

        support, support_tests = self._find_level(history, "support")
        resistance, resistance_tests = self._find_level(history, "resistance")

        previous = values[-2]
        tolerance = self.config.level_tolerance
        confirmation = self.config.rejection_confirmation

        if (
            support is not None
            and support_tests >= self.config.minimum_tests
            and abs(previous - support) <= tolerance
            and price - previous >= confirmation
            and price > support
        ):
            direction = "up"
            reason = "Repeated support tests followed by confirmed upward rejection"

        elif (
            resistance is not None
            and resistance_tests >= self.config.minimum_tests
            and abs(previous - resistance) <= tolerance
            and previous - price >= confirmation
            and price < resistance
        ):
            direction = "down"
            reason = "Repeated resistance tests followed by confirmed downward rejection"

        else:
            return None

        self.last_signal_time = timestamp

        return Signal(
            direction=direction,
            timestamp=int(timestamp),
            entry_price=price,
            reason=reason,
        )
