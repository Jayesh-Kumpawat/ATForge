from __future__ import annotations

from typing import TypedDict


class SignalRef(TypedDict):
    symbol: str
    strategy_name: str
    strategy_id: int
    signal_id: int
    signal_parquet: str
    ohlcv_parquet: str


class PipelineState(TypedDict, total=False):
    run_id: str
    universe: list[str]
    start_iso: str
    end_iso: str
    data_refs: dict[str, str]
    signal_refs: list[SignalRef]
    backtest_ids: list[int]
    failures: list[dict]
