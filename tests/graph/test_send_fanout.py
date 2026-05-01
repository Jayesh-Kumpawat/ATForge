"""Send-API fan-out tests.

After Step 8: `detect_patterns -> [Send] run_backtest_one (parallel) -> rank`.

Verifies:
  - one Send per signal_ref
  - parallel workers each emit a single backtest row
  - per-worker failures don't poison sibling workers
"""

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


class _SyntheticProvider:
    name = "synth"

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        idx = pd.date_range(start=start, end=end, freq="B")
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
    db_path = tmp_path / "db.sqlite"
    init_db(db_path)
    return PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(
            SmaCrossover(fast=5, slow=15),
            TalibCdlDetector("CDLENGULFING"),
            TalibCdlDetector("CDLHAMMER"),
        ),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        hold_bars=5,
        init_cash=Decimal("100000"),
    )


def test_send_dispatcher_emits_one_send_per_signal_ref() -> None:
    """The dispatcher returns one Send per signal_ref so workers run in parallel."""
    from langgraph.types import Send

    from atforge.graph.nodes_phase2 import make_run_backtest_dispatcher

    dispatcher = make_run_backtest_dispatcher()
    sends = dispatcher(
        {
            "run_id": "abc",
            "signal_refs": [
                {
                    "symbol": "RELIANCE",
                    "strategy_name": "S",
                    "strategy_id": 1,
                    "signal_id": 11,
                    "signal_parquet": "/x.parquet",
                    "ohlcv_parquet": "/y.parquet",
                    "generation": 0,
                },
                {
                    "symbol": "TCS",
                    "strategy_name": "S",
                    "strategy_id": 1,
                    "signal_id": 12,
                    "signal_parquet": "/x2.parquet",
                    "ohlcv_parquet": "/y2.parquet",
                    "generation": 0,
                },
            ],
        }
    )

    assert isinstance(sends, list)
    assert len(sends) == 2
    for s in sends:
        assert isinstance(s, Send)
        assert s.node == "run_backtest_one"
        assert "ref" in s.arg
        assert s.arg["run_id"] == "abc"


def test_send_dispatcher_returns_empty_list_when_no_signals() -> None:
    """Empty signal_refs -> no Sends -> graph still terminates."""
    from atforge.graph.nodes_phase2 import make_run_backtest_dispatcher

    dispatcher = make_run_backtest_dispatcher()
    sends = dispatcher({"run_id": "abc", "signal_refs": []})
    assert sends == []


def test_full_pipeline_runs_backtests_via_send_fanout(deps: PipelineDeps) -> None:
    """End-to-end check: 2 symbols * 3 detectors = 6 backtest rows after fan-out."""
    pipeline = build_pipeline(deps)
    run_id = uuid4().hex[:12]
    pipeline.invoke(
        {
            "run_id": run_id,
            "universe": ["RELIANCE", "TCS"],
            "start_iso": date(2024, 1, 1).isoformat(),
            "end_iso": date(2024, 12, 31).isoformat(),
        }
    )
    with connect(deps.db_path) as conn:
        n = conn.execute(
            "SELECT COUNT(*) c FROM backtest_runs WHERE run_id=?", (run_id,)
        ).fetchone()["c"]
    assert n == 2 * 3, f"expected 6 backtest rows from fan-out, got {n}"


def test_one_failing_signal_does_not_poison_others(deps: PipelineDeps, tmp_path: Path) -> None:
    """A worker hitting a missing parquet path emits a failure entry. Siblings still write rows."""
    from atforge.graph.nodes_phase2 import make_run_backtest_one

    deps.signal_cache_dir.mkdir(parents=True, exist_ok=True)
    deps.ohlcv_cache_dir.mkdir(parents=True, exist_ok=True)

    # Build an OHLCV parquet for the "good" worker.
    idx = pd.date_range("2024-01-01", periods=50, freq="B")
    df = pd.DataFrame(
        {
            "open": [100.0] * 50,
            "high": [101.0] * 50,
            "low": [99.0] * 50,
            "close": [100.0 + i * 0.1 for i in range(50)],
            "volume": [10_000] * 50,
        },
        index=idx,
    )
    ohlcv_path = tmp_path / "good.parquet"
    df.to_parquet(ohlcv_path)
    sig_path = tmp_path / "sig.parquet"
    pd.DataFrame({"signal": [True, False] * 25}, index=idx).to_parquet(sig_path)

    # Set up an empty run_id row so FK constraints hold.
    from atforge.storage.db import connect, txn
    from atforge.storage.repo import insert_run, upsert_strategy

    run_id = uuid4().hex[:12]
    with connect(deps.db_path) as conn, txn(conn):
        insert_run(conn, run_id)
        sid = upsert_strategy(conn, name="S", family="indicator", params={})
        from atforge.storage.repo import insert_pattern_signal

        sig_id = insert_pattern_signal(
            conn,
            run_id=run_id,
            strategy_id=sid,
            symbol="GOOD",
            n_signals=10,
            first_date=None,
            last_date=None,
        )

    worker = make_run_backtest_one(deps)

    # Good worker payload.
    good_state = {
        "run_id": run_id,
        "ref": {
            "symbol": "GOOD",
            "strategy_name": "S",
            "strategy_id": sid,
            "signal_id": sig_id,
            "signal_parquet": str(sig_path),
            "ohlcv_parquet": str(ohlcv_path),
            "generation": 0,
        },
    }
    bad_state = {
        "run_id": run_id,
        "ref": {
            "symbol": "BAD",
            "strategy_name": "S",
            "strategy_id": sid,
            "signal_id": sig_id,
            "signal_parquet": "/does/not/exist.parquet",
            "ohlcv_parquet": "/does/not/exist.parquet",
            "generation": 0,
        },
    }

    good_out = worker(good_state)
    bad_out = worker(bad_state)

    assert len(good_out.get("backtest_ids", [])) == 1
    assert good_out.get("failures", []) == [] or all(
        f.get("symbol") == "GOOD" for f in good_out.get("failures", [])
    )

    # Bad worker emits a failure entry, no backtest_id, no exception raised.
    assert bad_out.get("backtest_ids", []) == []
    assert len(bad_out.get("failures", [])) == 1
    assert bad_out["failures"][0]["symbol"] == "BAD"
