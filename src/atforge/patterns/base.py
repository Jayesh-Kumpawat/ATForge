from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd


@dataclass(frozen=True, slots=True)
class PatternSignal:
    """Output of a PatternDetector — a named boolean entry signal aligned to OHLCV index."""

    pattern_name: str
    family: str  # "candlestick" | "indicator" | "structural"
    signal: pd.Series  # bool-typed, same index as input OHLCV

    def __post_init__(self) -> None:
        if self.signal.dtype != bool:
            raise ValueError(f"signal must be bool-typed, got {self.signal.dtype}")


@runtime_checkable
class PatternDetector(Protocol):
    name: str
    family: str

    def detect(self, ohlcv: pd.DataFrame) -> PatternSignal: ...
