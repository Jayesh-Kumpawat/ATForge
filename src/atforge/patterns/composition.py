from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from atforge.patterns.base import PatternDetector, PatternSignal

COMPOSITE_FAMILY = "composite"


@dataclass(frozen=True, slots=True)
class AndDetector:
    """Bitwise AND of two child detectors. Fires only when both children fire on the same bar."""

    left: PatternDetector
    right: PatternDetector

    @property
    def name(self) -> str:
        return f"AND({self.left.name},{self.right.name})"

    @property
    def family(self) -> str:
        return COMPOSITE_FAMILY

    def detect(self, ohlcv: pd.DataFrame) -> PatternSignal:
        ls = self.left.detect(ohlcv).signal
        rs = self.right.detect(ohlcv).signal
        combined = (ls & rs).astype(bool)
        combined.name = self.name
        return PatternSignal(pattern_name=self.name, family=self.family, signal=combined)


@dataclass(frozen=True, slots=True)
class OrDetector:
    """Bitwise OR of two child detectors. Fires when either child fires on a given bar."""

    left: PatternDetector
    right: PatternDetector

    @property
    def name(self) -> str:
        return f"OR({self.left.name},{self.right.name})"

    @property
    def family(self) -> str:
        return COMPOSITE_FAMILY

    def detect(self, ohlcv: pd.DataFrame) -> PatternSignal:
        ls = self.left.detect(ohlcv).signal
        rs = self.right.detect(ohlcv).signal
        combined = (ls | rs).astype(bool)
        combined.name = self.name
        return PatternSignal(pattern_name=self.name, family=self.family, signal=combined)
