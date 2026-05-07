"""Step 9 — detector config registry round-trip tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atforge.evolution.registry import (
    _detector_to_config,
    build_detector_from_config,
    detector_params_json,
)
from atforge.patterns.composition import AndDetector, OrDetector
from atforge.patterns.pandas_ta import RsiOversoldReclaim, SmaCrossover
from atforge.patterns.talib_cdl import TalibCdlDetector


def _tiny_ohlcv(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    rng = np.random.default_rng(42)
    close = 100 + rng.normal(0, 1, n).cumsum()
    return pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.3, n),
            "high": close + rng.uniform(0.1, 0.8, n),
            "low": close - rng.uniform(0.1, 0.8, n),
            "close": close,
            "volume": rng.integers(1_000, 10_000, n).astype(float),
        },
        index=idx,
    )


OHLCV = _tiny_ohlcv()


@pytest.mark.parametrize(
    "det",
    [
        SmaCrossover(fast=5, slow=20),
        SmaCrossover(fast=10, slow=30),
        RsiOversoldReclaim(period=14, oversold=30),
        RsiOversoldReclaim(period=7, oversold=25),
        TalibCdlDetector("CDLENGULFING"),
        TalibCdlDetector("CDLHAMMER", direction="bullish"),
    ],
)
def test_roundtrip_leaf_detector(det):
    cfg = _detector_to_config(det)
    restored = build_detector_from_config(cfg)
    assert restored.name == det.name
    assert restored.family == det.family
    sig_orig = det.detect(OHLCV).signal
    sig_rest = restored.detect(OHLCV).signal
    pd.testing.assert_series_equal(sig_orig, sig_rest)


def test_roundtrip_and_detector():
    det = AndDetector(
        left=SmaCrossover(5, 20),
        right=TalibCdlDetector("CDLENGULFING"),
    )
    cfg = _detector_to_config(det)
    restored = build_detector_from_config(cfg)
    assert restored.name == det.name
    pd.testing.assert_series_equal(
        det.detect(OHLCV).signal,
        restored.detect(OHLCV).signal,
    )


def test_roundtrip_or_detector():
    det = OrDetector(
        left=SmaCrossover(5, 20),
        right=RsiOversoldReclaim(14, 30),
    )
    cfg = _detector_to_config(det)
    restored = build_detector_from_config(cfg)
    assert restored.name == det.name
    pd.testing.assert_series_equal(
        det.detect(OHLCV).signal,
        restored.detect(OHLCV).signal,
    )


def test_roundtrip_nested_composite():
    """Two levels of nesting — AndDetector whose left child is itself an OrDetector."""
    inner = OrDetector(SmaCrossover(5, 20), RsiOversoldReclaim(14, 30))
    outer = AndDetector(inner, TalibCdlDetector("CDLHAMMER"))
    cfg = _detector_to_config(outer)
    restored = build_detector_from_config(cfg)
    assert restored.name == outer.name
    pd.testing.assert_series_equal(
        outer.detect(OHLCV).signal,
        restored.detect(OHLCV).signal,
    )


def test_detector_params_json_is_stable():
    """Same detector always yields same JSON string (sort_keys=True guarantees order)."""
    det = SmaCrossover(fast=5, slow=20)
    assert detector_params_json(det) == detector_params_json(det)
    import json

    cfg = json.loads(detector_params_json(det))
    assert cfg == {"fast": 5, "slow": 20, "type": "sma_crossover"}


def test_unknown_detector_type_raises():
    class Alien:
        name = "alien"
        family = "indicator"

        def detect(self, _): ...

    with pytest.raises(TypeError, match="unknown detector type"):
        _detector_to_config(Alien())


def test_unknown_config_type_raises():
    with pytest.raises(ValueError, match="unknown detector type"):
        build_detector_from_config({"type": "quantum_oscillator"})
