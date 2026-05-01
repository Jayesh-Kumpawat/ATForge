from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd
import structlog

from atforge.backtest.engine import run_backtest
from atforge.data.universe import load_nifty50
from atforge.evolution.registry import _detector_to_config, build_detector_from_config
from atforge.graph.deps import PipelineDeps
from atforge.graph.state import PipelineState, SignalRef
from atforge.storage.db import connect, txn
from atforge.storage.repo import (
    insert_backtest_result,
    insert_pattern_signal,
    insert_run,
    upsert_strategy,
)

log = structlog.get_logger(__name__)

NodeFn = Callable[[PipelineState], dict[str, Any]]


def make_load_universe(deps: PipelineDeps) -> NodeFn:
    def load_universe(state: PipelineState) -> dict[str, Any]:
        universe = state.get("universe") or load_nifty50()
        with connect(deps.db_path) as conn, txn(conn):
            insert_run(conn, state["run_id"])
        # Seed detector configs for generation 0 from deps if not already in state.
        result: dict[str, Any] = {"universe": universe}
        if not state.get("detector_configs"):
            result["detector_configs"] = [_detector_to_config(d) for d in deps.detectors]
        return result

    return load_universe


def make_fetch_data(deps: PipelineDeps) -> NodeFn:
    def fetch_data(state: PipelineState) -> dict[str, Any]:
        start = date.fromisoformat(state["start_iso"])
        end = date.fromisoformat(state["end_iso"])
        refs: dict[str, str] = {}
        new_failures: list[dict[str, Any]] = []

        deps.ohlcv_cache_dir.mkdir(parents=True, exist_ok=True)

        for symbol in state.get("universe", []):
            try:
                df = deps.data_provider.fetch_ohlcv(symbol, start, end)
                path = deps.ohlcv_cache_dir / f"{_safe(symbol)}_{state['run_id']}.parquet"
                df.to_parquet(path)
                refs[symbol] = str(path)
            except Exception as exc:
                log.warning("fetch_data_failed", symbol=symbol, error=str(exc))
                new_failures.append({"node": "fetch_data", "symbol": symbol, "reason": str(exc)})

        return {"data_refs": refs, "failures": new_failures}

    return fetch_data


def make_detect_patterns(deps: PipelineDeps) -> NodeFn:
    def detect_patterns(state: PipelineState) -> dict[str, Any]:
        new_refs: list[SignalRef] = []
        new_failures: list[dict[str, Any]] = []
        deps.signal_cache_dir.mkdir(parents=True, exist_ok=True)

        generation = state.get("generation", 0)
        # Resolve detectors from state configs (set by load_universe or advance_generation).
        detector_configs = state.get("detector_configs") or [
            _detector_to_config(d) for d in deps.detectors
        ]

        with connect(deps.db_path) as conn, txn(conn):
            for symbol, ohlcv_path in state.get("data_refs", {}).items():
                try:
                    df = pd.read_parquet(ohlcv_path)
                except Exception as exc:
                    new_failures.append(
                        {"node": "detect_patterns", "symbol": symbol, "reason": f"read: {exc}"}
                    )
                    continue

                for cfg in detector_configs:
                    try:
                        det = build_detector_from_config(cfg)
                        sig = det.detect(df)
                    except Exception as exc:
                        new_failures.append(
                            {
                                "node": "detect_patterns",
                                "symbol": symbol,
                                "detector": cfg.get("type", "unknown"),
                                "reason": str(exc),
                            }
                        )
                        continue

                    strategy_id = upsert_strategy(
                        conn,
                        name=det.name,
                        family=det.family,
                        params=cfg,
                    )
                    n = int(sig.signal.sum())
                    first_date, last_date = _first_last_signal_dates(sig.signal)

                    signal_id = insert_pattern_signal(
                        conn,
                        run_id=state["run_id"],
                        strategy_id=strategy_id,
                        symbol=symbol,
                        n_signals=n,
                        first_date=first_date,
                        last_date=last_date,
                        generation=generation,
                    )

                    sig_path = (
                        deps.signal_cache_dir
                        / f"{_safe(symbol)}_{det.name}_g{generation}_{state['run_id']}.parquet"
                    )
                    sig.signal.to_frame(name="signal").to_parquet(sig_path)

                    new_refs.append(
                        SignalRef(
                            symbol=symbol,
                            strategy_name=det.name,
                            strategy_id=strategy_id,
                            signal_id=signal_id,
                            signal_parquet=str(sig_path),
                            ohlcv_parquet=ohlcv_path,
                            generation=generation,
                        )
                    )

        return {"signal_refs": new_refs, "failures": new_failures}

    return detect_patterns


def make_run_backtest(deps: PipelineDeps) -> NodeFn:
    def run_backtest_node(state: PipelineState) -> dict[str, Any]:
        new_backtest_ids: list[int] = []
        new_failures: list[dict[str, Any]] = []

        with connect(deps.db_path) as conn, txn(conn):
            for ref in state.get("signal_refs", []):
                try:
                    ohlcv = pd.read_parquet(ref["ohlcv_parquet"])
                    sig = pd.read_parquet(ref["signal_parquet"])["signal"].astype(bool)
                except Exception as exc:
                    new_failures.append(
                        {
                            "node": "run_backtest",
                            "symbol": ref["symbol"],
                            "strategy": ref["strategy_name"],
                            "reason": f"read: {exc}",
                        }
                    )
                    continue

                result = run_backtest(
                    ohlcv,
                    sig,
                    symbol=ref["symbol"],
                    pattern_name=ref["strategy_name"],
                    init_cash=deps.init_cash,
                    hold_bars=deps.hold_bars,
                    fees=deps.fees,
                    slippage=deps.slippage,
                )
                bid = insert_backtest_result(
                    conn,
                    run_id=state["run_id"],
                    signal_id=ref["signal_id"],
                    strategy_id=ref["strategy_id"],
                    result=result,
                    hold_bars=deps.hold_bars,
                    fees=deps.fees,
                    slippage=deps.slippage,
                    init_cash=deps.init_cash,
                )
                new_backtest_ids.append(bid)
                if not result.success:
                    new_failures.append(
                        {
                            "node": "run_backtest",
                            "symbol": ref["symbol"],
                            "strategy": ref["strategy_name"],
                            "reason": result.reason,
                        }
                    )

        return {"backtest_ids": new_backtest_ids, "failures": new_failures}

    return run_backtest_node


def make_rank(deps: PipelineDeps) -> NodeFn:
    from atforge.storage.repo import finish_run, top_rankings

    def rank(state: PipelineState) -> dict[str, Any]:
        with connect(deps.db_path) as conn:
            rows = top_rankings(conn, limit=20, run_id=state["run_id"])
        status = "success" if rows else "partial"
        with connect(deps.db_path) as conn, txn(conn):
            finish_run(
                conn,
                state["run_id"],
                status=status,
                notes=f"top_n={len(rows)} failures={len(state.get('failures', []))}",
            )
        log.info("pipeline_ranked", run_id=state["run_id"], top_n=len(rows))
        return {}

    return rank


def _safe(symbol: str) -> str:
    return symbol.replace("&", "_").replace("/", "_")


def _first_last_signal_dates(signal: pd.Series) -> tuple[str | None, str | None]:
    hits = signal[signal]
    if len(hits) == 0:
        return None, None
    return hits.index[0].date().isoformat(), hits.index[-1].date().isoformat()
