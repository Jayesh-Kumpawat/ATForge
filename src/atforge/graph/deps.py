from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from atforge.data.protocol import DataProvider
from atforge.patterns.base import PatternDetector


@dataclass(frozen=True)
class PipelineDeps:
    data_provider: DataProvider
    detectors: tuple[PatternDetector, ...]
    ohlcv_cache_dir: Path
    signal_cache_dir: Path
    db_path: Path
    hold_bars: int = 10
    init_cash: Decimal = field(default_factory=lambda: Decimal("100000"))
    fees: float = 0.0003
    slippage: float = 0.0005

    def ensure_dirs(self) -> None:
        self.ohlcv_cache_dir.mkdir(parents=True, exist_ok=True)
        self.signal_cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
