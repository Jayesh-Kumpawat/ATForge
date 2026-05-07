"""Phase 8 — per-role config + YAML + exploiter wiring tests.

Covers:
  - AgentRoleConfig has llm_priority (tuple[str,...]) and model (str|None) fields
  - Default AgentRoleConfig fields have correct defaults
  - load_role_configs() returns defaults when no atforge.yaml exists
  - load_role_configs() overrides fields from atforge.yaml
  - YAML system_prompt overrides the default
  - exploiter_node calls ResearchAgentMutator (not just stub) when llm_router+role_config present
  - explorer_node uses role_config temperature and max_iterations when available
  - default_role_configs() returns all three roles
"""

from __future__ import annotations

import json
import textwrap
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from atforge.backtest.engine import BacktestResult
from atforge.data.protocol import OHLCV_COLUMNS
from atforge.graph.deps import AgentRoleConfig, PipelineDeps
from atforge.graph.nodes_a2 import make_exploiter_node
from atforge.llm.types import LlmRequest, LlmResponse
from atforge.patterns.pandas_ta import SmaCrossover
from atforge.storage.db import connect, init_db, txn
from atforge.storage.repo import (
    insert_backtest_result,
    insert_pattern_signal,
    insert_run,
    upsert_strategy,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


class _SyntheticProvider:
    name = "synth"

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        idx = pd.date_range(start=start, end=end, freq="B")
        n = len(idx)
        rng = np.random.default_rng(seed=42)
        close = 100 + rng.normal(0, 1.5, n).cumsum()
        close = close - close.min() + 101
        df = pd.DataFrame(
            {
                "open": close + rng.normal(0, 0.5, n),
                "high": close + rng.uniform(0.1, 1.0, n),
                "low": close - rng.uniform(0.1, 1.0, n),
                "close": close,
                "volume": rng.integers(10_000, 100_000, n).astype(float),
            },
            index=idx,
        )
        df = df[list(OHLCV_COLUMNS)]
        df.index.name = "date"
        return df


def _sma_research_llm():
    """LLM that returns a valid ResearchProposal for sma_param_delta."""
    payload = json.dumps(
        {
            "proposal_type": "sma_param_delta",
            "sma": {"fast": 10, "slow": 25, "reasoning": "wider windows reduce noise"},
            "rsi": None,
            "research_summary": "lineage shows fast=5,slow=15 tried, moving to wider params",
            "confidence": 0.75,
        }
    )

    def _router(req: LlmRequest) -> LlmResponse:
        return LlmResponse(
            text=payload,
            model="mock",
            provider="mock",
            input_tokens=5,
            output_tokens=20,
            latency_ms=1,
        )

    return _router


def _seed_gen0(db_path: Path, run_id: str) -> int:
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)
        sid = upsert_strategy(
            conn,
            name="SMA_5x15_bullish",
            family="indicator",
            params={"type": "sma_crossover", "fast": 5, "slow": 15},
        )
        sig_id = insert_pattern_signal(
            conn,
            run_id=run_id,
            strategy_id=sid,
            symbol="RELIANCE",
            n_signals=5,
            first_date=None,
            last_date=None,
            generation=0,
        )
        bt = BacktestResult(
            symbol="RELIANCE",
            pattern_name="SMA_5x15_bullish",
            success=True,
            reason="ok",
            n_trades=8,
            metrics={
                "sharpe": 1.2,
                "sortino": 1.5,
                "total_return": Decimal("0.12"),
                "final_value": Decimal("112000"),
                "max_drawdown": Decimal("0.08"),
                "cagr": 0.12,
                "win_rate": 0.6,
            },
        )
        insert_backtest_result(
            conn,
            run_id=run_id,
            signal_id=sig_id,
            strategy_id=sid,
            result=bt,
            hold_bars=5,
            fees=0.0003,
            slippage=0.0005,
            init_cash=Decimal("100000"),
            generation=0,
        )
    return sid


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "db.sqlite"
    init_db(p)
    return p


# ─── AgentRoleConfig field extensions ────────────────────────────────────────


def test_agent_role_config_has_llm_priority_field():
    """AgentRoleConfig.llm_priority should be a tuple with empty default."""
    cfg = AgentRoleConfig(
        role="explorer",
        temperature=0.9,
        max_iterations=4,
        system_prompt="explore",
    )
    assert hasattr(cfg, "llm_priority"), "llm_priority field missing from AgentRoleConfig"
    assert cfg.llm_priority == (), "default llm_priority must be empty tuple"


def test_agent_role_config_has_model_field():
    """AgentRoleConfig.model should default to None."""
    cfg = AgentRoleConfig(
        role="critic",
        temperature=0.3,
        max_iterations=3,
        system_prompt="criticize",
    )
    assert hasattr(cfg, "model"), "model field missing from AgentRoleConfig"
    assert cfg.model is None


def test_agent_role_config_accepts_llm_priority_and_model():
    """AgentRoleConfig accepts llm_priority and model values."""
    cfg = AgentRoleConfig(
        role="explorer",
        temperature=0.9,
        max_iterations=4,
        system_prompt="explore",
        llm_priority=("gemini", "groq"),
        model="gemini-2.5-flash",
    )
    assert cfg.llm_priority == ("gemini", "groq")
    assert cfg.model == "gemini-2.5-flash"


def test_agent_role_config_is_still_frozen():
    """Adding new fields must not break frozen constraint."""
    cfg = AgentRoleConfig(
        role="exploiter",
        temperature=0.4,
        max_iterations=4,
        system_prompt="exploit",
        llm_priority=("gemini",),
    )
    with pytest.raises((AttributeError, TypeError)):
        cfg.temperature = 0.9  # type: ignore[misc]


# ─── default_role_configs() ──────────────────────────────────────────────────


def test_default_role_configs_returns_all_three_roles():
    """default_role_configs() must return explorer, exploiter, and critic entries."""
    from atforge.graph.role_config import default_role_configs

    configs = default_role_configs()
    assert "explorer" in configs, "explorer missing from default role configs"
    assert "exploiter" in configs, "exploiter missing from default role configs"
    assert "critic" in configs, "critic missing from default role configs"


def test_default_role_configs_correct_temperatures():
    """Default temperatures: explorer=0.9, exploiter=0.4, critic=0.3."""
    from atforge.graph.role_config import default_role_configs

    configs = default_role_configs()
    assert configs["explorer"].temperature == 0.9
    assert configs["exploiter"].temperature == 0.4
    assert configs["critic"].temperature == 0.3


# ─── load_role_configs() from YAML ───────────────────────────────────────────


def test_load_role_configs_returns_defaults_when_no_yaml(tmp_path: Path):
    """load_role_configs(path) returns defaults when file does not exist."""
    from atforge.graph.role_config import load_role_configs

    absent = tmp_path / "no_such_file.yaml"
    configs = load_role_configs(absent)
    assert "explorer" in configs
    assert "critic" in configs


def test_load_role_configs_overrides_temperature_from_yaml(tmp_path: Path):
    """YAML temperature override replaces default."""
    from atforge.graph.role_config import load_role_configs

    yaml_content = textwrap.dedent("""\
        roles:
          explorer:
            temperature: 0.95
          exploiter:
            temperature: 0.35
    """)
    yaml_path = tmp_path / "atforge.yaml"
    yaml_path.write_text(yaml_content)

    configs = load_role_configs(yaml_path)
    assert configs["explorer"].temperature == 0.95
    assert configs["exploiter"].temperature == 0.35
    # critic not in YAML — should still be present with defaults
    assert "critic" in configs
    assert configs["critic"].temperature == 0.3


def test_load_role_configs_overrides_system_prompt_from_yaml(tmp_path: Path):
    """YAML system_prompt override replaces default."""
    from atforge.graph.role_config import load_role_configs

    yaml_content = textwrap.dedent("""\
        roles:
          critic:
            system_prompt: "Custom critic prompt for this project."
    """)
    yaml_path = tmp_path / "atforge.yaml"
    yaml_path.write_text(yaml_content)

    configs = load_role_configs(yaml_path)
    assert configs["critic"].system_prompt == "Custom critic prompt for this project."


def test_load_role_configs_overrides_llm_priority_from_yaml(tmp_path: Path):
    """YAML llm_priority list becomes a tuple on AgentRoleConfig."""
    from atforge.graph.role_config import load_role_configs

    yaml_content = textwrap.dedent("""\
        roles:
          explorer:
            llm_priority: [gemini, groq, openrouter]
    """)
    yaml_path = tmp_path / "atforge.yaml"
    yaml_path.write_text(yaml_content)

    configs = load_role_configs(yaml_path)
    assert configs["explorer"].llm_priority == ("gemini", "groq", "openrouter")


def test_load_role_configs_overrides_model_from_yaml(tmp_path: Path):
    """YAML model field sets model override on AgentRoleConfig."""
    from atforge.graph.role_config import load_role_configs

    yaml_content = textwrap.dedent("""\
        roles:
          exploiter:
            model: gemini-2.5-flash-8b
    """)
    yaml_path = tmp_path / "atforge.yaml"
    yaml_path.write_text(yaml_content)

    configs = load_role_configs(yaml_path)
    assert configs["exploiter"].model == "gemini-2.5-flash-8b"


# ─── exploiter_node full wiring ──────────────────────────────────────────────


def test_exploiter_node_returns_proposals_when_llm_router_provided(db_path: Path, tmp_path: Path):
    """Phase 8: exploiter_node calls ResearchAgentMutator when llm_router is set."""
    run_id = uuid4().hex[:12]
    _seed_gen0(db_path, run_id)

    from atforge.evolution.research_prompts import EXPLOITER_SYSTEM_PROMPT

    exploiter_cfg = AgentRoleConfig(
        role="exploiter",
        temperature=0.4,
        max_iterations=2,
        system_prompt=EXPLOITER_SYSTEM_PROMPT,
    )

    test_deps = PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        top_n_parents=3,
        llm_router=_sma_research_llm(),
        role_configs={"exploiter": exploiter_cfg},
    )

    node = make_exploiter_node(test_deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "max_generations": 2,
        }
    )

    proposals = result.get("proposed_mutations", [])
    assert len(proposals) >= 1, "exploiter_node should return proposals when llm_router is set"
    assert all(p["role"] == "exploiter" for p in proposals)


def test_exploiter_node_still_noop_without_llm_router(tmp_path: Path, db_path: Path):
    """exploiter_node without llm_router returns empty proposals (backward compat)."""
    test_deps = PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        # no llm_router
    )

    node = make_exploiter_node(test_deps)
    result = node({"run_id": "x", "generation": 0, "max_generations": 2})
    assert result.get("proposed_mutations", []) == []
