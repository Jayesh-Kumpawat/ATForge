from __future__ import annotations

import pandas as pd

from atforge.patterns.base import PatternSignal


class SmaCrossover:
    """Fast SMA crosses above slow SMA → bullish entry signal.

    Classic indicator pattern. Slow/fast windows in trading days.
    """

    family = "indicator"

    def __init__(self, fast: int = 20, slow: int = 50) -> None:
        if fast >= slow:
            raise ValueError("fast must be < slow")
        self._fast = fast
        self._slow = slow
        self.name = f"SMA_{fast}x{slow}_bullish"

    def detect(self, ohlcv: pd.DataFrame) -> PatternSignal:
        close = ohlcv["close"]
        fast = close.rolling(self._fast).mean()
        slow = close.rolling(self._slow).mean()
        cross_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
        sig = cross_up.fillna(False).astype(bool)
        sig.name = self.name
        return PatternSignal(pattern_name=self.name, family=self.family, signal=sig)


class RsiOversoldReclaim:
    """RSI crosses back above oversold threshold — mean-reversion long signal."""

    family = "indicator"

    def __init__(self, period: int = 14, oversold: int = 30) -> None:
        self._period = period
        self._oversold = oversold
        self.name = f"RSI_{period}_reclaim_{oversold}"

    def detect(self, ohlcv: pd.DataFrame) -> PatternSignal:
        import pandas_ta_classic as ta

        rsi = ta.rsi(ohlcv["close"], length=self._period)
        reclaim = (rsi > self._oversold) & (rsi.shift(1) <= self._oversold)
        sig = reclaim.fillna(False).astype(bool)
        sig.name = self.name
        return PatternSignal(pattern_name=self.name, family=self.family, signal=sig)
