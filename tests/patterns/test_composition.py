from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from atforge.patterns.base import PatternDetector, PatternSignal
from atforge.patterns.composition import COMPOSITE_FAMILY, AndDetector, OrDetector


@dataclass(frozen=True, slots=True)
class _FixedSignalDetector:
    name: str
    family: str
    pattern: list[bool]

    def detect(self, ohlcv: pd.DataFrame) -> PatternSignal:
        sig = pd.Series(self.pattern, index=ohlcv.index, dtype=bool, name=self.name)
        return PatternSignal(pattern_name=self.name, family=self.family, signal=sig)


def _detector(name: str, pattern: list[bool]) -> _FixedSignalDetector:
    return _FixedSignalDetector(name=name, family="indicator", pattern=pattern)


def test_and_detector_satisfies_protocol(tiny_ohlcv: pd.DataFrame) -> None:
    a = _detector("A", [True] * len(tiny_ohlcv))
    b = _detector("B", [True] * len(tiny_ohlcv))
    det = AndDetector(left=a, right=b)
    assert isinstance(det, PatternDetector)
    assert det.family == COMPOSITE_FAMILY


def test_and_detector_logical_and(tiny_ohlcv: pd.DataFrame) -> None:
    n = len(tiny_ohlcv)
    a = _detector("A", [True, False, True] + [False] * (n - 3))
    b = _detector("B", [True, True, False] + [False] * (n - 3))
    out = AndDetector(left=a, right=b).detect(tiny_ohlcv)
    assert out.signal.dtype == bool
    assert out.signal.iloc[0]
    assert not out.signal.iloc[1]
    assert not out.signal.iloc[2]
    assert not out.signal.iloc[3:].any()


def test_or_detector_logical_or(tiny_ohlcv: pd.DataFrame) -> None:
    n = len(tiny_ohlcv)
    a = _detector("A", [True, False, False] + [False] * (n - 3))
    b = _detector("B", [False, True, False] + [False] * (n - 3))
    out = OrDetector(left=a, right=b).detect(tiny_ohlcv)
    assert out.signal.iloc[0]
    assert out.signal.iloc[1]
    assert not out.signal.iloc[2]


def test_and_detector_preserves_index(tiny_ohlcv: pd.DataFrame) -> None:
    a = _detector("A", [True] * len(tiny_ohlcv))
    b = _detector("B", [False] * len(tiny_ohlcv))
    out = AndDetector(left=a, right=b).detect(tiny_ohlcv)
    assert out.signal.index.equals(tiny_ohlcv.index)


def test_deterministic_name() -> None:
    a = _detector("CDLENGULFING_bullish", [True])
    b = _detector("SMA_20x50_bullish", [True])
    and_det = AndDetector(left=a, right=b)
    or_det = OrDetector(left=a, right=b)
    assert and_det.name == "AND(CDLENGULFING_bullish,SMA_20x50_bullish)"
    assert or_det.name == "OR(CDLENGULFING_bullish,SMA_20x50_bullish)"


def test_nested_composition(tiny_ohlcv: pd.DataFrame) -> None:
    n = len(tiny_ohlcv)
    a = _detector("A", [True] * n)
    b = _detector("B", [False, True] + [False] * (n - 2))
    c = _detector("C", [True, True] + [False] * (n - 2))

    inner = OrDetector(left=a, right=b)
    outer = AndDetector(left=inner, right=c)

    assert outer.name == "AND(OR(A,B),C)"
    out = outer.detect(tiny_ohlcv)
    assert out.signal.iloc[0]
    assert out.signal.iloc[1]
    assert not out.signal.iloc[2:].any()


def test_signal_is_bool_dtype(tiny_ohlcv: pd.DataFrame) -> None:
    a = _detector("A", [True] * len(tiny_ohlcv))
    b = _detector("B", [False] * len(tiny_ohlcv))
    out = AndDetector(left=a, right=b).detect(tiny_ohlcv)
    assert out.signal.dtype == bool


def test_post_init_rejects_non_bool() -> None:
    """Sanity check — PatternSignal.__post_init__ guards dtype, so composition can't smuggle floats through."""
    idx = pd.date_range("2025-01-01", periods=3)
    with pytest.raises(ValueError, match="bool-typed"):
        PatternSignal(
            pattern_name="bad", family="indicator", signal=pd.Series([1.0, 0.0, 1.0], index=idx)
        )
