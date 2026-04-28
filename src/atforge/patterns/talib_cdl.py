from __future__ import annotations

import talib

from atforge.patterns.base import PatternSignal

CDL_PATTERNS: tuple[str, ...] = (
    "CDLENGULFING",
    "CDLHAMMER",
    "CDLMORNINGSTAR",
    "CDLEVENINGSTAR",
    "CDLSHOOTINGSTAR",
    "CDLDOJI",
    "CDLHANGINGMAN",
    "CDL3WHITESOLDIERS",
    "CDL3BLACKCROWS",
    "CDLDARKCLOUDCOVER",
)


class TalibCdlDetector:
    """Wraps a single TA-Lib CDL* function as a PatternDetector.

    TA-Lib CDL* functions return integers: +100 bullish, -100 bearish, 0 none.
    Phase 1 treats any non-zero same-direction reading as a signal when
    `direction=\"bullish\"` or `\"bearish\"`.
    """

    family = "candlestick"

    def __init__(self, cdl_name: str, direction: str = "bullish") -> None:
        if cdl_name not in CDL_PATTERNS and not cdl_name.startswith("CDL"):
            raise ValueError(f"not a CDL pattern: {cdl_name}")
        if direction not in {"bullish", "bearish"}:
            raise ValueError(f"direction must be 'bullish' or 'bearish', got {direction!r}")
        fn = getattr(talib, cdl_name, None)
        if fn is None:
            raise ValueError(f"TA-Lib has no function {cdl_name!r}")
        self._fn = fn
        self._cdl_name = cdl_name
        self._direction = direction
        self.name = f"{cdl_name}_{direction}"

    def detect(self, ohlcv) -> PatternSignal:
        import pandas as pd

        raw = self._fn(
            ohlcv["open"].to_numpy(dtype=float),
            ohlcv["high"].to_numpy(dtype=float),
            ohlcv["low"].to_numpy(dtype=float),
            ohlcv["close"].to_numpy(dtype=float),
        )
        sig = raw > 0 if self._direction == "bullish" else raw < 0
        series = pd.Series(sig, index=ohlcv.index, name=self.name, dtype=bool)
        return PatternSignal(pattern_name=self.name, family=self.family, signal=series)
