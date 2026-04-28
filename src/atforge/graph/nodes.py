from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd
import structlog

from atforge.backtest.engine import run_backtest
from atforge.data.universe import load_nifty50
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


def _append_failure(state: PipelineState, entry: dict[str, Any]) -> list[dict[str, Any]]:
    out = list(state.get("failures", []))
    out.append(entry)
    return out


def make_load_universe(deps: PipelineDeps) -> NodeFn:
    def load_universe(state: PipelineState) -> dict[str, Any]:
        universe = state.get("universe") or load_nifty50()
        with connect(deps.db_path) as conn, txn(conn):
            insert_run(conn, state["run_id"])
        return {"universe": universe}

    return load_universe


def make_fetch_data(deps: PipelineDeps) -> NodeFn:
    def fetch_data(state: PipelineState) -> dict[str, Any]:
        start = date.fromisoformat(state["start_iso"])
        end = date.fromisoformat(state["end_iso"])
        refs: dict[str, str] = {}
        failures = list(state.get("failures", []))

        deps.ohlcv_cache_dir.mkdir(parents=True, exist_ok=True)

        for symbol in state.get("universe", []):
            try:
                df = deps.data_provider.fetch_ohlcv(symbol, start, end)
                path = deps.ohlcv_cache_dir / f"{_safe(symbol)}_{state['run_id']}.parquet"
                df.to_parquet(path)
                refs[symbol] = str(path)
            except Exception as exc:
                log.warning("fetch_data_failed", symbol=symbol, error=str(exc))
                failures.append({"node": "fetch_data", "symbol": symbol, "reason": str(exc)})

        return {"data_refs": refs, "failures": failures}

    return fetch_data


def make_detect_patterns(deps: PipelineDeps) -> NodeFn:
    def detect_patterns(state: PipelineState) -> dict[str, Any]:
        refs: list[SignalRef] = []
        failures = list(state.get("failures", []))
        deps.signal_cache_dir.mkdir(parents=True, exist_ok=True)

        with connect(deps.db_path) as conn, txn(conn):
            for symbol, ohlcv_path in state.get("data_refs", {}).items():
                try:
                    df = pd.read_parquet(ohlcv_path)
                except Exception as exc:
                    failures.append(
                        {"node": "detect_patterns", "symbol": symbol, "reason": f"read: {exc}"}
                    )
                    continue

                for det in deps.detectors:
                    try:
                        sig = det.detect(df)
                    except Exception as exc:
                        failures.append(
                            {
                                "node": "detect_patterns",
                                "symbol": symbol,
                                "detector": det.name,
                                "reason": str(exc),
                            }
                        )
                        continue

                    strategy_id = upsert_strategy(
                        conn,
                        name=det.name,
                        family=det.family,
                        params={},
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
                    )

                    sig_path = (
                        deps.signal_cache_dir
                        / f"{_safe(symbol)}_{det.name}_{state['run_id']}.parquet"
                    )
                    sig.signal.to_frame(name="signal").to_parquet(sig_path)

                    refs.append(
                        SignalRef(
                            symbol=symbol,
                            strategy_name=det.name,
                            strategy_id=strategy_id,
                            signal_id=signal_id,
                            signal_parquet=str(sig_path),
                            ohlcv_parquet=ohlcv_path,
                        )
                    )

        return {"signal_refs": refs, "failures": failures}

    return detect_patterns


def make_run_backtest(deps: PipelineDeps) -> NodeFn:
    def run_backtest_node(state: PipelineState) -> dict[str, Any]:
        backtest_ids: list[int] = []
        failures = list(state.get("failures", []))

        with connect(deps.db_path) as conn, txn(conn):
            for ref in state.get("signal_refs", []):
                try:
                    ohlcv = pd.read_parquet(ref["ohlcv_parquet"])
                    sig = pd.read_parquet(ref["signal_parquet"])["signal"].astype(bool)
                except Exception as exc:
                    failures.append(
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
                backtest_ids.append(bid)
                if not result.success:
                    failures.append(
                        {
                            "node": "run_backtest",
                            "symbol": ref["symbol"],
                            "strategy": ref["strategy_name"],
                            "reason": result.reason,
                        }
                    )

        return {"backtest_ids": backtest_ids, "failures": failures}

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
