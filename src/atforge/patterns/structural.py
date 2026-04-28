"""Structural chart patterns (cup-and-handle, H&S, double tops/bottoms).

Phase 1 ships a DOUBLE-BOTTOM stub using scipy.signal.find_peaks. The full
~200 LOC structural suite is finished in Phase 2 alongside evolution — the
interface here is stable so nodes can already target it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from atforge.patterns.base import PatternSignal


class DoubleBottomDetector:
    """Approximate double-bottom detector.

    Heuristic: two troughs of comparable depth separated by a local high.
    Emits a one-bar True signal on the second trough's bar.
    """

    family = "structural"
    name = "DOUBLE_BOTTOM"

    def __init__(self, lookback: int = 60, tolerance_pct: float = 3.0) -> None:
        self._lookback = lookback
        self._tol = tolerance_pct / 100.0

    def detect(self, ohlcv: pd.DataFrame) -> PatternSignal:
        close = ohlcv["close"].to_numpy(dtype=float)
        neg_close = -close
        trough_idx, _ = find_peaks(neg_close, distance=5)
        peak_idx, _ = find_peaks(close, distance=5)

        sig = np.zeros(len(close), dtype=bool)
        for i, t2 in enumerate(trough_idx):
            if i == 0:
                continue
            t1 = trough_idx[i - 1]
            if t2 - t1 > self._lookback or t2 - t1 < 10:
                continue
            depth1, depth2 = close[t1], close[t2]
            if abs(depth1 - depth2) / max(depth1, depth2) > self._tol:
                continue
            mid_peaks = peak_idx[(peak_idx > t1) & (peak_idx < t2)]
            if len(mid_peaks) == 0:
                continue
            sig[t2] = True

        series = pd.Series(sig, index=ohlcv.index, name=self.name, dtype=bool)
        return PatternSignal(pattern_name=self.name, family=self.family, signal=series)
