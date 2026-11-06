from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional
import math

from .fct10s import Signal


@dataclass(frozen=True)
class BreakoutConfig:
    pair: str = "EURUSD_OTC"

    window_seconds: float = 20.0
    squeeze_seconds: float = 8.0
    minimum_ticks: int = 24

    compression_ratio: float = 0.55
    maximum_squeeze_range: float = 0.00012

    breakout_buffer: float = 0.000015
    confirmation_ticks: int = 2

    maximum_breakout_distance: float = 0.0008
    setup_timeout: float = 12.0
    cooldown_seconds: float = 5.0


class VolatilitySqueezeBreakoutStrategy:
    """
    Experimental volatility squeeze breakout strategy.

    Detects a compressed price range, arms its boundaries,
    and waits for a confirmed breakout.

    Generates Signal objects only. Order execution remains
    the responsibility of Nightshift's existing runner.
    """

    def __init__(
        self,
        config: BreakoutConfig = BreakoutConfig(),
    ):
        self.config = config
        self.prices: deque[tuple[float, float]] = deque()

        self.last_timestamp = 0.0
        self.last_signal_time = 0.0

        self.armed = False
        self.upper_boundary = 0.0
        self.lower_boundary = 0.0
        self.armed_at = 0.0

        self.candidate_direction: Optional[str] = None
        self.confirmation_count = 0

    def ready(self) -> bool:
        return len(self.prices) >= self.config.minimum_ticks

    def reset_setup(self) -> None:
        self.armed = False
        self.upper_boundary = 0.0
        self.lower_boundary = 0.0
        self.armed_at = 0.0
        self.candidate_direction = None
        self.confirmation_count = 0

    def detect_squeeze(self, timestamp: float) -> bool:
        values = list(self.prices)

        split_time = timestamp - self.config.squeeze_seconds
        recent = [
            price for tick_time, price in values
            if tick_time >= split_time
        ]
        earlier = [
            price for tick_time, price in values
            if tick_time < split_time
        ]

        if len(recent) < 6 or len(earlier) < 6:
            return False

        reference = recent[-1]
        if reference <= 0:
            return False

        recent_range = (max(recent) - min(recent)) / reference
        earlier_range = (max(earlier) - min(earlier)) / reference

        if earlier_range <= 0:
            return False

        if recent_range > self.config.maximum_squeeze_range:
            return False

        if recent_range > earlier_range * self.config.compression_ratio:
            return False

        self.upper_boundary = max(recent)
        self.lower_boundary = min(recent)
        self.armed_at = timestamp
        self.armed = True

        return True

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

        if self.armed and (
            timestamp - self.armed_at > self.config.setup_timeout
        ):
            self.reset_setup()

        if not self.armed:
            self.detect_squeeze(timestamp)

        if not self.armed:
            return None

        if price > self.upper_boundary + self.config.breakout_buffer:
            direction = "up"
        elif price < self.lower_boundary - self.config.breakout_buffer:
            direction = "down"
        else:
            self.candidate_direction = None
            self.confirmation_count = 0
            return None

        distance = (
            abs(price - (
                self.upper_boundary
                if direction == "up"
                else self.lower_boundary
            ))
            / price
        )

        if distance > self.config.maximum_breakout_distance:
            self.reset_setup()
            return None

        if direction == self.candidate_direction:
            self.confirmation_count += 1
        else:
            self.candidate_direction = direction
            self.confirmation_count = 1

        if self.confirmation_count < self.config.confirmation_ticks:
            return None

        signal = Signal(
            direction=direction,
            timestamp=int(timestamp),
            entry_price=price,
            reason=(
                f"Volatility squeeze confirmed by "
                f"{self.confirmation_count} consecutive "
                f"{direction.upper()} breakout ticks"
            ),
        )

        self.last_signal_time = timestamp
        self.reset_setup()

        return signal
