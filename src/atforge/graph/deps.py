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
class AgentRoleConfig:
    """Per-role configuration for A2 multi-agent nodes.

    Phase 6: used by explorer/exploiter/critic to configure LLM behaviour.
    Phase 8 will wire llm_priority and model overrides from CLI/YAML.
    """

    role: str  # "explorer" | "exploiter" | "critic"
    temperature: float  # exploration level — 0.9 explorer, 0.4 exploiter
    max_iterations: int  # ReAct loop bound
    system_prompt: str  # role-specific system prompt injected at call time


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

    # A2 multi-agent role configs — empty dict = use Phase 6 defaults in each node.
    # Phase 8 will populate from CLI flags / atforge.yaml.
    role_configs: dict[str, AgentRoleConfig] = field(default_factory=dict)

    def ensure_dirs(self) -> None:
        self.ohlcv_cache_dir.mkdir(parents=True, exist_ok=True)
        self.signal_cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
