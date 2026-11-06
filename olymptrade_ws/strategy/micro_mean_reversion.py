from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional
import math

from .fct10s import Signal


@dataclass(frozen=True)
class MeanReversionConfig:
    pair: str = "EURUSD_OTC"
    window_seconds: float = 15.0
    minimum_ticks: int = 20
    displacement_threshold: float = 0.00008
    reversal_confirmation: float = 0.000015
    exhaustion_ratio: float = 0.65
    cooldown_seconds: float = 5.0
    maximum_displacement: float = 0.0008


class MicroMeanReversionStrategy:
    """
    Experimental short-horizon mean-reversion signal generator.

    A signal requires:
      1. Price displacement from the rolling mean.
      2. Evidence that the latest move is losing strength.
      3. A confirmed move back toward the rolling mean.

    This class generates signals only. It does not submit orders.
    """

    def __init__(
        self,
        config: MeanReversionConfig = MeanReversionConfig(),
    ):
        self.config = config
        self.prices: deque[tuple[float, float]] = deque()
        self.last_timestamp = 0.0
        self.last_signal_time = 0.0

    def ready(self) -> bool:
        return len(self.prices) >= self.config.minimum_ticks

    def on_tick(
        self,
        timestamp: float,
        price: float,
    ) -> Optional[Signal]:

        if (
            not math.isfinite(timestamp)
            or not math.isfinite(price)
            or timestamp <= self.last_timestamp
            or price <= 0
        ):
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
        latest = values[-1]
        reference = sum(values) / len(values)

        if reference <= 0:
            return None

        displacement = (latest - reference) / reference
        distance = abs(displacement)

        if distance < self.config.displacement_threshold:
            return None

        if distance > self.config.maximum_displacement:
            return None

        midpoint = len(values) // 2
        if midpoint < 3:
            return None

        earlier = values[:midpoint]
        recent = values[midpoint:]

        earlier_move = abs(earlier[-1] - earlier[0]) / earlier[0]
        recent_move = abs(recent[-1] - recent[0]) / recent[0]

        if earlier_move <= 0:
            return None

        if recent_move > earlier_move * self.config.exhaustion_ratio:
            return None

        previous = values[-2]
        reversal = (latest - previous) / previous

        if displacement > 0:
            if reversal > -self.config.reversal_confirmation:
                return None
            direction = "down"
            reason = "Positive displacement, exhaustion and downward reversal"
        else:
            if reversal < self.config.reversal_confirmation:
                return None
            direction = "up"
            reason = "Negative displacement, exhaustion and upward reversal"

        self.last_signal_time = timestamp

        return Signal(
            direction=direction,
            timestamp=int(timestamp),
            entry_price=latest,
            reason=reason,
        )
