from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class SignalRef(TypedDict, total=False):
    symbol: str
    strategy_name: str
    strategy_id: int
    signal_id: int
    signal_parquet: str
    ohlcv_parquet: str
    generation: int
    parent_strategy_id: int | None


class PipelineState(TypedDict, total=False):
    run_id: str
    universe: list[str]
    start_iso: str
    end_iso: str

    # Generation tracking (Phase 2a, default 0/1 when omitted by callers).
    generation: int
    max_generations: int

    # Last-writer-wins (single producer per pass; no reducer needed).
    data_refs: dict[str, str]
    # Detector configs for the current generation. Set once by load_universe (gen=0)
    # or advance_generation (gen=1+). Not reducer-merged — single producer.
    detector_configs: list[dict[str, Any]]

    # Reducer-merged: nodes return only their own delta. Send API workers append in parallel.
    signal_refs: Annotated[list[SignalRef], operator.add]
    backtest_ids: Annotated[list[int], operator.add]
    failures: Annotated[list[dict], operator.add]
    # Mutation records accumulated across generations (generation, parent/child strategy_ids, etc.)
    mutations: Annotated[list[dict[str, Any]], operator.add]
