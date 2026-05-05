"""Phase 2a graph nodes: Send-API parallel backtest worker + dispatcher + evolution nodes.

The dispatcher returns one `Send` per `signal_ref` so workers run in parallel; each
`run_backtest_one` worker handles a single signal. Reducer fields on `PipelineState`
(`backtest_ids`, `failures`, `mutations`) merge per-worker emissions deterministically.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import pandas as pd
import structlog
from langgraph.types import Send

from atforge.backtest.engine import run_backtest
from atforge.evolution.ratchet import build_evaluation_result, judge_mutation
from atforge.evolution.registry import build_detector_from_config
from atforge.graph.deps import PipelineDeps
from atforge.graph.events import (
    EvtBacktestDone,
    EvtGenerationDone,
    EvtMutationProposed,
    EvtNodeDone,
    EvtNodeStart,
    EvtRatchetVerdict,
)
from atforge.graph.state import PipelineState
from atforge.llm.tracing import trace_node
from atforge.storage.db import connect, txn
from atforge.storage.repo import (
    get_top_strategies_for_generation,
    insert_backtest_result,
    insert_experiment,
    upsert_strategy,
)

log = structlog.get_logger(__name__)


def make_run_backtest_dispatcher() -> Callable[[PipelineState], list[Send]]:
    """Return a function that fans out one Send per `signal_ref` to `run_backtest_one`."""

    def dispatcher(state: PipelineState) -> list[Send]:
        run_id = state["run_id"]
        return [
            Send("run_backtest_one", {"ref": ref, "run_id": run_id})
            for ref in state.get("signal_refs", [])
        ]

    return dispatcher


def make_run_backtest_one(deps: PipelineDeps) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Per-signal worker. Reads its parquets, runs vectorbt, writes one backtest_runs row."""

    def run_backtest_one(state: dict[str, Any]) -> dict[str, Any]:
        ref = state["ref"]
        run_id = state["run_id"]
        generation = ref.get("generation", 0)
        symbol = ref["symbol"]
        strategy = ref["strategy_name"]
        bus = deps.event_bus
        new_backtest_ids: list[int] = []
        new_failures: list[dict[str, Any]] = []

        with trace_node(
            "run_backtest_one",
            enabled=deps.tracing_enabled,
            metadata={"symbol": symbol, "strategy": strategy, "generation": generation},
        ):
            try:
                ohlcv = pd.read_parquet(ref["ohlcv_parquet"])
                sig = pd.read_parquet(ref["signal_parquet"])["signal"].astype(bool)
            except Exception as exc:
                log.warning(
                    "backtest_read_failed", symbol=symbol, strategy=strategy, error=str(exc)
                )
                new_failures.append(
                    {
                        "node": "run_backtest",
                        "symbol": symbol,
                        "strategy": strategy,
                        "reason": f"read: {exc}",
                    }
                )
                if bus:
                    bus.emit(EvtBacktestDone(symbol=symbol, strategy=strategy, success=False))
                return {"backtest_ids": new_backtest_ids, "failures": new_failures}

            result = run_backtest(
                ohlcv,
                sig,
                symbol=symbol,
                pattern_name=strategy,
                init_cash=deps.init_cash,
                hold_bars=deps.hold_bars,
                fees=deps.fees,
                slippage=deps.slippage,
            )

            with connect(deps.db_path) as conn, txn(conn):
                bid = insert_backtest_result(
                    conn,
                    run_id=run_id,
                    signal_id=ref["signal_id"],
                    strategy_id=ref["strategy_id"],
                    result=result,
                    hold_bars=deps.hold_bars,
                    fees=deps.fees,
                    slippage=deps.slippage,
                    init_cash=deps.init_cash,
                    generation=generation,
                )

            new_backtest_ids.append(bid)
            sharpe_raw = result.metrics.get("sharpe") if result.success else None
            sharpe = float(sharpe_raw) if sharpe_raw is not None else None
            if bus:
                bus.emit(
                    EvtBacktestDone(
                        symbol=symbol, strategy=strategy, success=result.success, sharpe=sharpe
                    )
                )

            if not result.success:
                log.warning(
                    "backtest_failed", symbol=symbol, strategy=strategy, reason=result.reason
                )
                new_failures.append(
                    {
                        "node": "run_backtest",
                        "symbol": symbol,
                        "strategy": strategy,
                        "reason": result.reason,
                    }
                )
            else:
                log.info(
                    "backtest_ok",
                    symbol=symbol,
                    strategy=strategy,
                    sharpe=sharpe,
                    generation=generation,
                )

        return {"backtest_ids": new_backtest_ids, "failures": new_failures}

    return run_backtest_one


def make_ratchet_node(deps: PipelineDeps) -> Callable[[PipelineState], dict[str, Any]]:
    """Compare current-generation children to previous-generation parents.

    On generation=0 (no prior mutations), this is a no-op.
    On generation=N≥1, reads state["mutations"] for N-1, compares via DB, writes experiments.
    """

    def ratchet_node(state: PipelineState) -> dict[str, Any]:
        generation = state.get("generation", 0)
        if generation == 0:
            return {}

        run_id = state["run_id"]
        prev_gen = generation - 1
        bus = deps.event_bus
        t0 = time.monotonic()

        pending = [m for m in state.get("mutations", []) if m.get("generation") == prev_gen]
        if not pending:
            return {}

        log.info("ratchet_node_start", generation=generation, n_pending=len(pending))
        if bus:
            bus.emit(EvtNodeStart("ratchet_node", generation))

        thresholds = deps.ratchet_thresholds
        n_accepted = 0

        with (
            trace_node(
                "ratchet_node",
                enabled=deps.tracing_enabled,
                metadata={"generation": generation, "n_pending": len(pending)},
            ),
            connect(deps.db_path) as conn,
        ):
            for mutation in pending:
                parent_er = build_evaluation_result(
                    conn,
                    strategy_id=mutation["parent_strategy_id"],
                    run_id=run_id,
                    generation=prev_gen,
                )
                child_er = build_evaluation_result(
                    conn,
                    strategy_id=mutation["child_strategy_id"],
                    run_id=run_id,
                    generation=generation,
                )
                if parent_er is None or child_er is None:
                    continue

                verdict = judge_mutation(parent_er, child_er, thresholds)
                if verdict.accepted:
                    n_accepted += 1

                log.info(
                    "ratchet_verdict",
                    accepted=verdict.accepted,
                    delta_sharpe=round(verdict.delta_sharpe, 4),
                    reason=verdict.reasoning,
                    generation=generation,
                )

                if bus:
                    # Resolve names from DB for display
                    parent_name = mutation.get("mutator", "?")
                    child_row = conn.execute(
                        "SELECT name FROM strategies WHERE strategy_id=?",
                        (mutation["child_strategy_id"],),
                    ).fetchone()
                    child_name = child_row["name"] if child_row else "?"
                    bus.emit(
                        EvtRatchetVerdict(
                            parent_name=parent_name,
                            child_name=child_name,
                            accepted=verdict.accepted,
                            delta_sharpe=verdict.delta_sharpe,
                            reason=verdict.reasoning,
                        )
                    )

                with txn(conn):
                    insert_experiment(
                        conn,
                        run_id=run_id,
                        generation=generation,
                        parent_strategy_id=mutation["parent_strategy_id"],
                        child_strategy_id=mutation["child_strategy_id"],
                        mutator=mutation["mutator"],
                        mutation_json=mutation["mutation_json"],
                        accepted=1 if verdict.accepted else 0,
                        delta_sharpe=verdict.delta_sharpe,
                        composite_score_json=json.dumps(verdict.composite_score),
                        reasoning=verdict.reasoning,
                    )

        log.info(
            "ratchet_node_done", generation=generation, n_accepted=n_accepted, n_total=len(pending)
        )
        if bus:
            bus.emit(EvtNodeDone("ratchet_node", generation, (time.monotonic() - t0) * 1000))
            bus.emit(
                EvtGenerationDone(
                    generation=generation,
                    n_backtests=len(state.get("backtest_ids", [])),
                    n_accepted=n_accepted,
                )
            )
        return {}

    return ratchet_node


def make_mutate_strategies(deps: PipelineDeps) -> Callable[[PipelineState], dict[str, Any]]:
    """Propose mutations for the next generation from top-N current-generation parents.

    Skips if generation >= max_generations (no more loops needed).
    Registers proposed child strategies in DB and returns mutation records in state.
    """

    def mutate_strategies(state: PipelineState) -> dict[str, Any]:
        generation = state.get("generation", 0)
        max_gen = state.get("max_generations", 1)

        if generation + 1 >= max_gen:
            return {}

        run_id = state["run_id"]
        bus = deps.event_bus
        new_mutations: list[dict[str, Any]] = []
        t0 = time.monotonic()

        if bus:
            bus.emit(EvtNodeStart("mutate_strategies", generation))

        with trace_node(
            "mutate_strategies",
            enabled=deps.tracing_enabled,
            metadata={"generation": generation},
        ):
            with connect(deps.db_path) as conn:
                parents = get_top_strategies_for_generation(
                    conn,
                    run_id=run_id,
                    generation=generation,
                    limit=deps.top_n_parents,
                )

            if not parents:
                log.info("mutate_strategies_no_parents", generation=generation)
                if bus:
                    bus.emit(
                        EvtNodeDone("mutate_strategies", generation, (time.monotonic() - t0) * 1000)
                    )
                return {}

            log.info("mutate_strategies_start", generation=generation, n_parents=len(parents))

            for mutator in deps.mutators:
                try:
                    proposals = mutator.propose(parents, k=deps.top_n_parents)
                except Exception:
                    continue
                if bus:
                    bus.emit(EvtMutationProposed(mutator.name, len(proposals)))
                log.info(
                    "mutator_proposed",
                    mutator=mutator.name,
                    n=len(proposals),
                    generation=generation,
                )
                for proposal in proposals:
                    try:
                        det = build_detector_from_config(proposal.child_config)
                        with connect(deps.db_path) as conn, txn(conn):
                            child_sid = upsert_strategy(
                                conn,
                                name=det.name,
                                family=det.family,
                                params=proposal.child_config,
                            )
                        new_mutations.append(
                            {
                                "generation": generation,
                                "parent_strategy_id": proposal.parent_strategy_id,
                                "child_strategy_id": child_sid,
                                "mutator": proposal.mutator,
                                "mutation_json": json.dumps(proposal.child_config, sort_keys=True),
                                "reasoning": proposal.reasoning,
                            }
                        )
                    except Exception:
                        continue

        log.info("mutate_strategies_done", generation=generation, n_mutations=len(new_mutations))
        if bus:
            bus.emit(EvtNodeDone("mutate_strategies", generation, (time.monotonic() - t0) * 1000))
        return {"mutations": new_mutations}

    return mutate_strategies


def make_advance_generation(deps: PipelineDeps) -> Callable[[PipelineState], dict[str, Any]]:
    """Increment generation counter and set detector_configs to child strategy configs.

    Reads accepted children from state["mutations"] for the current generation.
    Falls back to all proposed children if none were accepted (keeps evolution alive).
    """

    def advance_generation(state: PipelineState) -> dict[str, Any]:
        generation = state.get("generation", 0)
        run_id = state["run_id"]

        # Collect child strategy IDs proposed at end of current generation
        current_gen_mutations = [
            m for m in state.get("mutations", []) if m.get("generation") == generation
        ]

        if not current_gen_mutations:
            return {"generation": generation + 1}

        # Prefer accepted children; fall back to all proposed if none accepted
        accepted_sids: list[int] = []
        with connect(deps.db_path) as conn:
            for m in current_gen_mutations:
                row = conn.execute(
                    "SELECT accepted FROM experiments WHERE run_id=? AND child_strategy_id=? AND generation=?",
                    (run_id, m["child_strategy_id"], generation + 1),
                ).fetchone()
                if row and row["accepted"] == 1:
                    accepted_sids.append(m["child_strategy_id"])

        candidate_sids = accepted_sids or [m["child_strategy_id"] for m in current_gen_mutations]

        # Build detector configs from child strategy params_json
        new_configs: list[dict[str, Any]] = []
        with connect(deps.db_path) as conn:
            for sid in candidate_sids:
                row = conn.execute(
                    "SELECT params_json FROM strategies WHERE strategy_id=?", (sid,)
                ).fetchone()
                if row:
                    try:
                        cfg = json.loads(row["params_json"])
                        if cfg.get("type"):  # valid detector config
                            new_configs.append(cfg)
                    except (json.JSONDecodeError, KeyError):
                        pass

        return {
            "generation": generation + 1,
            "detector_configs": new_configs or state.get("detector_configs", []),
        }

    return advance_generation


def make_loop_decision() -> Callable[[PipelineState], str]:
    """Return 'continue' if another generation should run, else 'stop'."""

    def loop_decision(state: PipelineState) -> str:
        generation = state.get("generation", 0)
        max_gen = state.get("max_generations", 1)
        # continue only if advancing would stay within max_generations
        return "continue" if generation + 1 < max_gen else "stop"

    return loop_decision
