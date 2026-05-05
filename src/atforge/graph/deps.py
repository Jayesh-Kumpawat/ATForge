from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atforge.data.protocol import DataProvider
from atforge.evolution.types import Mutator, RatchetThresholds
from atforge.patterns.base import PatternDetector

if TYPE_CHECKING:
    pass


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

    # Phase 2a — evolution
    mutators: tuple[Mutator, ...] = field(default_factory=tuple)
    ratchet_thresholds: RatchetThresholds = field(default_factory=RatchetThresholds)
    top_n_parents: int = 5

    # Observability — both optional, off by default so existing tests need no changes
    tracing_enabled: bool = False
    event_bus: Any | None = None  # EventBus | None (Any avoids frozen-dataclass issues)

    def ensure_dirs(self) -> None:
        self.ohlcv_cache_dir.mkdir(parents=True, exist_ok=True)
        self.signal_cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
