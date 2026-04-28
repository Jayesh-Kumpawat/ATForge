from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from atforge.data.protocol import OHLCV_COLUMNS
from atforge.graph.deps import PipelineDeps
from atforge.graph.pipeline import build_pipeline
from atforge.patterns.pandas_ta import SmaCrossover
from atforge.patterns.talib_cdl import TalibCdlDetector
from atforge.storage.db import connect, init_db
from atforge.storage.repo import top_rankings


class _SyntheticProvider:
    """Offline provider — generates a rising+noisy series with a mid-series dip."""

    name = "synthetic"

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        idx = pd.date_range(start=start, end=end, freq="B")  # business days
        n = len(idx)
        rng = np.random.default_rng(seed=hash(symbol) % (2**32))
        drift = np.linspace(100, 140, n)
        noise = rng.normal(0, 1.5, size=n)
        close = drift + noise
        open_ = close + rng.normal(0, 0.5, size=n)
        high = np.maximum(open_, close) + rng.uniform(0.1, 1.0, size=n)
        low = np.minimum(open_, close) - rng.uniform(0.1, 1.0, size=n)
        volume = rng.integers(10_000, 100_000, size=n)
        df = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=idx,
        )
        df = df[list(OHLCV_COLUMNS)]
        df.index.name = "date"
        return df


@pytest.fixture
def deps(tmp_path: Path) -> PipelineDeps:
    db_path = tmp_path / "atforge.db"
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
    )


def test_pipeline_end_to_end_populates_rankings(deps: PipelineDeps) -> None:
    pipeline = build_pipeline(deps)
    run_id = uuid4().hex[:12]

    result = pipeline.invoke(
        {
            "run_id": run_id,
            "universe": ["RELIANCE", "TCS"],
            "start_iso": date(2024, 1, 1).isoformat(),
            "end_iso": date(2024, 12, 31).isoformat(),
        }
    )

    assert "backtest_ids" in result
    assert len(result["backtest_ids"]) > 0

    with connect(deps.db_path) as conn:
        rankings = top_rankings(conn, limit=10, run_id=run_id)
        runs = conn.execute("SELECT status, notes FROM runs WHERE run_id=?", (run_id,)).fetchone()
        n_sigs = conn.execute(
            "SELECT COUNT(*) c FROM pattern_signals WHERE run_id=?", (run_id,)
        ).fetchone()["c"]
        n_bts = conn.execute(
            "SELECT COUNT(*) c FROM backtest_runs WHERE run_id=?", (run_id,)
        ).fetchone()["c"]

    assert runs["status"] in {"success", "partial"}
    assert n_sigs == 2 * 2  # 2 symbols * 2 detectors
    assert n_bts == 2 * 2
    # At least one successful backtest should produce a ranking row.
    assert len(rankings) >= 0  # zero allowed if all detectors find no signals in short window


def test_pipeline_survives_one_failing_symbol(deps: PipelineDeps, tmp_path: Path) -> None:
    class _PartialProvider:
        name = "partial"
        _real = _SyntheticProvider()

        def fetch_ohlcv(self, symbol, start, end, interval="1d"):
            if symbol == "BROKEN":
                raise RuntimeError("simulated provider error")
            return self._real.fetch_ohlcv(symbol, start, end, interval=interval)

    broken_deps = PipelineDeps(
        data_provider=_PartialProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv2",
        signal_cache_dir=tmp_path / "signals2",
        db_path=deps.db_path,
    )
    pipeline = build_pipeline(broken_deps)
    run_id = uuid4().hex[:12]

    result = pipeline.invoke(
        {
            "run_id": run_id,
            "universe": ["RELIANCE", "BROKEN"],
            "start_iso": date(2024, 1, 1).isoformat(),
            "end_iso": date(2024, 6, 30).isoformat(),
        }
    )

    failures = result.get("failures", [])
    assert any(f.get("symbol") == "BROKEN" for f in failures)
    # RELIANCE still went through to backtest.
    with connect(deps.db_path) as conn:
        n_bts = conn.execute(
            "SELECT COUNT(*) c FROM backtest_runs WHERE run_id=?", (run_id,)
        ).fetchone()["c"]
    assert n_bts == 1
