"""Regression tests for the reducer migration.

Phase 1 nodes used to return state['failures'] merged with new entries. With
`Annotated[list, operator.add]` reducers in place, that pattern would double-count.
These tests guard against accidental regression.
"""

from __future__ import annotations

import inspect
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from atforge.data.protocol import OHLCV_COLUMNS
from atforge.graph import nodes as nodes_mod
from atforge.graph.deps import PipelineDeps
from atforge.graph.pipeline import build_pipeline
from atforge.graph.state import PipelineState
from atforge.patterns.pandas_ta import SmaCrossover
from atforge.storage.db import init_db


class _Provider:
    name = "synth"

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        idx = pd.date_range(start=start, end=end, freq="B")
        n = len(idx)
        if symbol == "BAD":
            raise RuntimeError("boom")
        df = pd.DataFrame(
            {
                "open": [100.0] * n,
                "high": [101.0] * n,
                "low": [99.0] * n,
                "close": [100.0 + i * 0.1 for i in range(n)],
                "volume": [10_000] * n,
            },
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
        data_provider=_Provider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        hold_bars=5,
        init_cash=Decimal("100000"),
    )


def test_pipeline_state_uses_reducer_annotations() -> None:
    """`signal_refs`, `backtest_ids`, `failures` must use `operator.add` reducers.

    This is the structural invariant Send API depends on.
    """
    import operator
    from typing import get_type_hints

    # `from __future__ import annotations` defers types to strings; resolve here.
    hints = get_type_hints(PipelineState, include_extras=True)
    for field in ("signal_refs", "backtest_ids", "failures"):
        assert field in hints, f"missing field: {field}"
        meta = getattr(hints[field], "__metadata__", ())
        assert operator.add in meta, f"{field} missing operator.add reducer (got meta={meta})"


def test_no_phase1_pattern_of_merging_state_failures_in_node_returns() -> None:
    """Phase 1 pattern `failures = list(state.get("failures", []))` is forbidden.

    Under reducers it doubles entries every call. Greppable safety net.
    """
    src = inspect.getsource(nodes_mod)
    forbidden = re.compile(r"list\(\s*state\.get\(\s*['\"]failures['\"]")
    matches = forbidden.findall(src)
    assert not matches, f"reducer-incompatible merge of failures found in nodes.py: {matches}"


def test_failures_are_not_double_counted_in_full_pipeline(deps: PipelineDeps) -> None:
    """One BAD symbol -> exactly one failure entry, not multiple."""
    pipeline = build_pipeline(deps)
    run_id = uuid4().hex[:12]
    result = pipeline.invoke(
        {
            "run_id": run_id,
            "universe": ["BAD"],
            "start_iso": date(2024, 1, 1).isoformat(),
            "end_iso": date(2024, 6, 30).isoformat(),
        }
    )
    failures = result.get("failures", [])
    bad_failures = [f for f in failures if f.get("symbol") == "BAD"]
    assert len(bad_failures) == 1, f"BAD reported {len(bad_failures)} times: {bad_failures}"
