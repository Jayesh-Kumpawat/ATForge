"""Phase 2a integration test — synthetic provider + mocked LLM, 2 generations.

Verifies end-to-end:
  - gen=0 backtests written
  - mutate_strategies proposes children (mocked LLM)
  - gen=1 backtests written for child configs
  - ratchet writes experiments with accepted IN (0,1)
  - no exceptions raised throughout
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from atforge.data.protocol import OHLCV_COLUMNS
from atforge.evolution.mutators.param_delta import ParamDeltaMutator
from atforge.graph.deps import PipelineDeps
from atforge.graph.pipeline import build_pipeline
from atforge.llm.types import LlmRequest, LlmResponse
from atforge.patterns.pandas_ta import SmaCrossover
from atforge.patterns.talib_cdl import TalibCdlDetector
from atforge.storage.db import connect, init_db


class _SyntheticProvider:
    name = "synth"

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        idx = pd.date_range(start=start, end=end, freq="B")
        n = len(idx)
        rng = np.random.default_rng(seed=abs(hash(symbol)) % (2**32))
        close = 100.0 + rng.normal(0, 1.5, n).cumsum()
        close = close - close.min() + 101.0
        df = pd.DataFrame(
            {
                "open": close + rng.normal(0, 0.5, n),
                "high": close + rng.uniform(0.1, 1.5, n),
                "low": close - rng.uniform(0.1, 1.5, n),
                "close": close,
                "volume": rng.integers(10_000, 100_000, n).astype(float),
            },
            index=idx,
        )
        df = df[list(OHLCV_COLUMNS)]
        df.index.name = "date"
        return df


def _mock_llm(fast: int = 8, slow: int = 22):
    payload = json.dumps({"fast": fast, "slow": slow, "reasoning": "integration test mutation"})

    def _router(req: LlmRequest) -> LlmResponse:
        return LlmResponse(
            text=payload, model="mock", provider="mock", input_tokens=5, output_tokens=15, latency_ms=1
        )

    return _router


@pytest.fixture
def phase2_deps(tmp_path: Path) -> PipelineDeps:
    db_path = tmp_path / "db.sqlite"
    init_db(db_path)
    return PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(
            SmaCrossover(fast=5, slow=15),
            TalibCdlDetector("CDLENGULFING"),
        ),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        hold_bars=5,
        init_cash=Decimal("100000"),
        mutators=(ParamDeltaMutator(_mock_llm(fast=8, slow=22)),),
        top_n_parents=3,
    )


def test_phase2a_two_generation_pipeline(phase2_deps: PipelineDeps) -> None:
    """Full 2-generation run: backtests + mutations + ratchet verdicts all present."""
    pipeline = build_pipeline(phase2_deps)
    run_id = uuid4().hex[:12]

    pipeline.invoke(
        {
            "run_id": run_id,
            "universe": ["RELIANCE", "TCS"],
            "start_iso": date(2024, 1, 1).isoformat(),
            "end_iso": date(2024, 12, 31).isoformat(),
            "max_generations": 2,
        }
    )

    with connect(phase2_deps.db_path) as conn:
        gen0_count = conn.execute(
            "SELECT COUNT(*) c FROM backtest_runs WHERE run_id=? AND generation=0", (run_id,)
        ).fetchone()["c"]
        gen1_count = conn.execute(
            "SELECT COUNT(*) c FROM backtest_runs WHERE run_id=? AND generation=1", (run_id,)
        ).fetchone()["c"]
        exp_rows = conn.execute(
            "SELECT accepted, delta_sharpe, composite_score FROM experiments WHERE run_id=?",
            (run_id,),
        ).fetchall()
        run_status = conn.execute(
            "SELECT status FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()["status"]

    # Generation 0: 2 symbols * 2 detectors = 4 backtests (SMA fires + CDL varies)
    assert gen0_count >= 2, f"expected gen=0 backtests, got {gen0_count}"
    # Generation 1: loop fired, child config backtested
    assert gen1_count >= 1, f"gen=1 backtests missing — loop did not fire (got {gen1_count})"
    # Ratchet wrote experiment rows
    assert len(exp_rows) >= 1, "no experiment rows — ratchet did not run"
    for row in exp_rows:
        assert row["accepted"] in (0, 1), f"invalid accepted value: {row['accepted']}"
        assert row["composite_score"] is not None, "composite_score should be JSON string"
    # Run completed without error
    assert run_status in ("success", "partial"), f"run status: {run_status}"


def test_phase2a_single_generation_no_loop(phase2_deps: PipelineDeps) -> None:
    """max_generations=1 → no loop, no gen=1 backtests, no experiments."""
    pipeline = build_pipeline(phase2_deps)
    run_id = uuid4().hex[:12]

    pipeline.invoke(
        {
            "run_id": run_id,
            "universe": ["RELIANCE"],
            "start_iso": date(2024, 1, 1).isoformat(),
            "end_iso": date(2024, 12, 31).isoformat(),
            "max_generations": 1,
        }
    )

    with connect(phase2_deps.db_path) as conn:
        gen1_count = conn.execute(
            "SELECT COUNT(*) c FROM backtest_runs WHERE run_id=? AND generation=1", (run_id,)
        ).fetchone()["c"]
        exp_count = conn.execute(
            "SELECT COUNT(*) c FROM experiments WHERE run_id=?", (run_id,)
        ).fetchone()["c"]

    assert gen1_count == 0, f"gen=1 rows present but loop should not have fired: {gen1_count}"
    assert exp_count == 0, f"experiment rows present but ratchet should not have run: {exp_count}"


def test_phase2a_failures_do_not_poison_pipeline(phase2_deps: PipelineDeps) -> None:
    """A failing provider symbol still lets the rest of the run complete."""

    class _PartialProvider:
        name = "partial"

        def fetch_ohlcv(self, symbol, start, end, interval="1d"):
            if symbol == "BAD":
                raise RuntimeError("simulated fetch failure")
            return _SyntheticProvider().fetch_ohlcv(symbol, start, end, interval)

    import dataclasses

    deps = dataclasses.replace(phase2_deps, data_provider=_PartialProvider())
    pipeline = build_pipeline(deps)
    run_id = uuid4().hex[:12]

    result = pipeline.invoke(
        {
            "run_id": run_id,
            "universe": ["RELIANCE", "BAD"],
            "start_iso": date(2024, 1, 1).isoformat(),
            "end_iso": date(2024, 6, 30).isoformat(),
            "max_generations": 1,
        }
    )

    failures = result.get("failures", [])
    bad_failures = [f for f in failures if f.get("symbol") == "BAD"]
    good_bts = [bid for bid in result.get("backtest_ids", [])]

    assert len(bad_failures) == 1, f"BAD failure not exactly 1: {bad_failures}"
    assert len(good_bts) >= 1, "RELIANCE backtests should have run"
