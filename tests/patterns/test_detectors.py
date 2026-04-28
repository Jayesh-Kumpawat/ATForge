from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atforge.patterns.base import PatternDetector, PatternSignal
from atforge.patterns.pandas_ta import RsiOversoldReclaim, SmaCrossover
from atforge.patterns.structural import DoubleBottomDetector
from atforge.patterns.talib_cdl import CDL_PATTERNS, TalibCdlDetector


def test_base_signal_rejects_non_bool() -> None:
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    bad = pd.Series([1, 0, 1], index=idx)
    with pytest.raises(ValueError):
        PatternSignal(pattern_name="x", family="indicator", signal=bad)


def test_talib_detector_protocol_conformance(tiny_ohlcv) -> None:
    det = TalibCdlDetector("CDLENGULFING")
    assert isinstance(det, PatternDetector)
    out = det.detect(tiny_ohlcv)
    assert isinstance(out, PatternSignal)
    assert out.signal.index.equals(tiny_ohlcv.index)
    assert out.signal.dtype == bool


def test_talib_rejects_unknown_cdl() -> None:
    with pytest.raises(ValueError):
        TalibCdlDetector("NOT_A_PATTERN")


def test_talib_rejects_bad_direction(tiny_ohlcv) -> None:
    with pytest.raises(ValueError):
        TalibCdlDetector("CDLENGULFING", direction="sideways")


def test_all_cdl_patterns_loadable() -> None:
    for p in CDL_PATTERNS:
        TalibCdlDetector(p)


def test_sma_crossover_emits_bool_signal(tiny_ohlcv) -> None:
    det = SmaCrossover(fast=5, slow=10)
    out = det.detect(tiny_ohlcv)
    assert out.signal.dtype == bool
    assert out.signal.index.equals(tiny_ohlcv.index)
    assert out.family == "indicator"


def test_sma_rejects_fast_ge_slow() -> None:
    with pytest.raises(ValueError):
        SmaCrossover(fast=20, slow=20)


def test_rsi_oversold_reclaim_runs(tiny_ohlcv) -> None:
    det = RsiOversoldReclaim(period=5, oversold=30)
    out = det.detect(tiny_ohlcv)
    assert out.signal.dtype == bool
    assert len(out.signal) == len(tiny_ohlcv)


def test_double_bottom_detects_on_synthetic_w_shape() -> None:
    n = 80
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = np.concatenate(
        [
            np.linspace(100, 90, 20),
            np.linspace(90, 100, 20),
            np.linspace(100, 90, 20),
            np.linspace(90, 110, 20),
        ]
    )
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.full(n, 10_000, dtype=int),
        },
        index=idx,
    )
    out = DoubleBottomDetector(lookback=60, tolerance_pct=5.0).detect(df)
    assert out.signal.any(), "expected at least one double-bottom signal on W shape"
