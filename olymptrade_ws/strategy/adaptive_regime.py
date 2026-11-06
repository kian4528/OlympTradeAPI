from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional
import math

from .fct10s import Signal, FCT10sStrategy, StrategyConfig
from .micro_mean_reversion import (
    MicroMeanReversionStrategy,
    MeanReversionConfig,
)
from .volatility_breakout import (
    VolatilitySqueezeBreakoutStrategy,
    BreakoutConfig,
)


@dataclass(frozen=True)
class AdaptiveRegimeConfig:
    pair: str = "EURUSD_OTC"
    window_seconds: float = 20.0
    minimum_ticks: int = 30
    cooldown_seconds: float = 5.0

    trend_threshold: float = 0.00004
    ranging_threshold: float = 0.000025
    maximum_range: float = 0.00030


class AdaptiveRegimeStrategy:
    """
    Experimental market-regime router.

    Selects one of three existing strategies:
      - Micro Mean Reversion
      - Tick Momentum Continuation
      - Volatility Squeeze Breakout

    Does not submit orders.
    """

    def __init__(
        self,
        config: AdaptiveRegimeConfig = AdaptiveRegimeConfig(),
    ):
        self.config = config
        self.prices: deque[tuple[float, float]] = deque()
        self.last_timestamp = 0.0
        self.last_signal_time = 0.0

        self.mean_reversion = MicroMeanReversionStrategy(
            MeanReversionConfig(pair=config.pair)
        )
        self.momentum = FCT10sStrategy(
            StrategyConfig(pair=config.pair)
        )
        self.breakout = VolatilitySqueezeBreakoutStrategy(
            BreakoutConfig(pair=config.pair)
        )

        self.current_regime = "INITIALIZING"
        self.selected_strategy = "NONE"

    def ready(self) -> bool:
        return len(self.prices) >= self.config.minimum_ticks

    def classify_regime(self) -> str:
        values = [price for _, price in self.prices]

        if len(values) < self.config.minimum_ticks:
            return "INITIALIZING"

        first = values[0]
        latest = values[-1]

        if first <= 0:
            return "UNCLEAR"

        movement = (latest - first) / first
        price_range = (max(values) - min(values)) / first

        midpoint = len(values) // 2
        first_half = values[:midpoint]
        second_half = values[midpoint:]

        if len(first_half) < 3 or len(second_half) < 3:
            return "UNCLEAR"

        first_move = (first_half[-1] - first_half[0]) / first_half[0]
        second_move = (
            (second_half[-1] - second_half[0]) / second_half[0]
        )

        # Persistent directional movement.
        if (
            abs(movement) >= self.config.trend_threshold
            and movement * first_move > 0
            and movement * second_move > 0
        ):
            return "TRENDING"

        # Small overall displacement and limited total range.
        if (
            abs(movement) <= self.config.ranging_threshold
            and price_range <= self.config.maximum_range
        ):
            return "RANGING"

        return "UNCLEAR"

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

        # Feed every valid tick to all component strategies.
        # Only the selected strategy may produce an executable signal.
        mean_signal = self.mean_reversion.on_tick(timestamp, price)
        momentum_signal = self.momentum.on_tick(timestamp, price)
        breakout_signal = self.breakout.on_tick(timestamp, price)

        if not self.ready():
            self.current_regime = "INITIALIZING"
            self.selected_strategy = "NONE"
            return None

        regime = self.classify_regime()
        self.current_regime = regime

        if timestamp - self.last_signal_time < self.config.cooldown_seconds:
            return None

        selected_signal = None

        if regime == "RANGING":
            self.selected_strategy = "Micro Mean Reversion"
            selected_signal = mean_signal

        elif regime == "TRENDING":
            self.selected_strategy = "Tick Momentum Continuation"
            selected_signal = momentum_signal

        else:
            # Breakout signals are only eligible when the regime
            # is not clearly ranging or trending.
            self.selected_strategy = "Volatility Squeeze Breakout"
            selected_signal = breakout_signal

        if selected_signal is None:
            return None

        self.last_signal_time = timestamp

        return Signal(
            direction=selected_signal.direction,
            timestamp=selected_signal.timestamp,
            entry_price=selected_signal.entry_price,
            reason=(
                f"Adaptive regime: {regime} | "
                f"{self.selected_strategy} | "
                f"{selected_signal.reason}"
            ),
        )
