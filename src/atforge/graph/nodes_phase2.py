"""Phase 2a graph nodes: Send-API parallel backtest worker + dispatcher + evolution nodes.

The dispatcher returns one `Send` per `signal_ref` so workers run in parallel; each
`run_backtest_one` worker handles a single signal. Reducer fields on `PipelineState`
(`backtest_ids`, `failures`, `mutations`) merge per-worker emissions deterministically.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pandas as pd
from langgraph.types import Send

from atforge.backtest.engine import run_backtest
from atforge.evolution.ratchet import build_evaluation_result, judge_mutation
from atforge.evolution.registry import build_detector_from_config
from atforge.graph.deps import PipelineDeps
from atforge.graph.state import PipelineState
from atforge.storage.db import connect, txn
from atforge.storage.repo import (
    get_top_strategies_for_generation,
    insert_backtest_result,
    insert_experiment,
    upsert_strategy,
)


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
        new_backtest_ids: list[int] = []
        new_failures: list[dict[str, Any]] = []

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
            return {"backtest_ids": new_backtest_ids, "failures": new_failures}

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

    return run_backtest_one


def make_ratchet_node(deps: PipelineDeps) -> Callable[[PipelineState], dict[str, Any]]:
    """Compare current-generation children to previous-generation parents.

    On generation=0 (no prior mutations), this is a no-op.
    On generation=N≥1, reads state["mutations"] for N-1, compares via DB, writes experiments.
    """

    def ratchet_node(state: PipelineState) -> dict[str, Any]:
        generation = state.get("generation", 0)
        if generation == 0:
            return {}  # nothing to compare on first pass

        run_id = state["run_id"]
        prev_gen = generation - 1

        # Find mutations proposed at end of the previous generation
        pending = [m for m in state.get("mutations", []) if m.get("generation") == prev_gen]
        if not pending:
            return {}

        thresholds = deps.ratchet_thresholds

        with connect(deps.db_path) as conn:
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

        # Only mutate if there's a next generation to run
        if generation + 1 >= max_gen:
            return {}

        run_id = state["run_id"]
        new_mutations: list[dict[str, Any]] = []

        with connect(deps.db_path) as conn:
            parents = get_top_strategies_for_generation(
                conn,
                run_id=run_id,
                generation=generation,
                limit=deps.top_n_parents,
            )

        if not parents:
            return {}

        for mutator in deps.mutators:
            try:
                proposals = mutator.propose(parents, k=deps.top_n_parents)
            except Exception:
                continue
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
                            "mutation_json": json.dumps(
                                proposal.child_config, sort_keys=True
                            ),
                            "reasoning": proposal.reasoning,
                        }
                    )
                except Exception:
                    continue

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
