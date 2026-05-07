"""A2 multi-agent pipeline nodes.

Replaces the single `mutate_strategies` node with four sequential nodes:

  explorer_node → exploiter_node → critic_node → aggregate_node

Phase 6 status:
  - explorer_node  : fully wired — calls deps.mutators, tags proposals with role/generation
  - exploiter_node : stub (returns empty proposals; role-specific LLM wired in Phase 8)
  - critic_node    : stub (accepts all; tool-using critic logic wired in Phase 7)
  - aggregate_node : fully wired — filters vetoed proposals, upserts survivors, emits mutations

State contract:
  - proposed_mutations reducer (operator.add): explorer + exploiter append independently
  - vetoed_mutations reducer (operator.add): critic appends per-proposal veto dicts
  - Both carry a `generation` int so aggregate_node can filter correctly in a multi-loop run
  - mutations reducer (operator.add): aggregate_node appends; ratchet_node reads this

Fingerprint format (stable dedup key):
  f"{parent_strategy_id}:{json.dumps(child_config, sort_keys=True)}"
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import structlog

from atforge.evolution.registry import build_detector_from_config
from atforge.graph.deps import PipelineDeps
from atforge.graph.events import EvtMutationProposed, EvtNodeDone, EvtNodeStart
from atforge.graph.state import PipelineState
from atforge.llm.tracing import trace_node
from atforge.storage.db import connect, txn
from atforge.storage.repo import get_top_strategies_for_generation, upsert_strategy

log = structlog.get_logger(__name__)


def _make_fingerprint(parent_strategy_id: int, child_config: dict[str, Any]) -> str:
    """Stable dedup key: parent_id + canonical JSON of child config."""
    return f"{parent_strategy_id}:{json.dumps(child_config, sort_keys=True)}"


def _proposals_from_mutators(
    deps: PipelineDeps,
    run_id: str,
    generation: int,
    role: str,
) -> list[dict[str, Any]]:
    """Shared helper: query top parents, call all deps.mutators, wrap as proposal dicts."""
    proposals: list[dict[str, Any]] = []

    with connect(deps.db_path) as conn:
        parents = get_top_strategies_for_generation(
            conn,
            run_id=run_id,
            generation=generation,
            limit=deps.top_n_parents,
        )

    if not parents:
        return proposals

    for mutator in deps.mutators:
        try:
            raw_proposals = mutator.propose(parents, k=deps.top_n_parents)
        except Exception:
            continue

        if deps.event_bus:
            deps.event_bus.emit(EvtMutationProposed(mutator.name, len(raw_proposals)))

        log.info(
            "agent_proposed",
            role=role,
            mutator=mutator.name,
            n=len(raw_proposals),
            generation=generation,
        )

        for pm in raw_proposals:
            proposals.append(
                {
                    "generation": generation,
                    "parent_strategy_id": pm.parent_strategy_id,
                    "child_config": pm.child_config,
                    "reasoning": pm.reasoning,
                    "role": role,
                    "fingerprint": _make_fingerprint(pm.parent_strategy_id, pm.child_config),
                }
            )

    return proposals


# ─── explorer_node ────────────────────────────────────────────────────────────


def make_explorer_node(deps: PipelineDeps) -> Callable[[PipelineState], dict[str, Any]]:
    """Propose novel mutations using deps.mutators at elevated exploration temperature.

    Phase 6: calls existing deps.mutators (same as old mutate_strategies).
    Phase 8: replaced with role_configs["explorer"]-configured ResearchAgentMutator
             at temperature=0.9 with novelty-focused system prompt.
    """

    def explorer_node(state: PipelineState) -> dict[str, Any]:
        generation = state.get("generation", 0)
        max_gen = state.get("max_generations", 1)

        if generation + 1 >= max_gen:
            return {"proposed_mutations": []}

        run_id = state["run_id"]
        bus = deps.event_bus
        t0 = time.monotonic()

        if bus:
            bus.emit(EvtNodeStart("explorer_node", generation))

        with trace_node(
            "explorer_node",
            enabled=deps.tracing_enabled,
            metadata={"generation": generation, "role": "explorer"},
        ):
            proposals = _proposals_from_mutators(deps, run_id, generation, role="explorer")

        log.info("explorer_node_done", generation=generation, n_proposals=len(proposals))
        if bus:
            bus.emit(EvtNodeDone("explorer_node", generation, (time.monotonic() - t0) * 1000))

        return {"proposed_mutations": proposals}

    return explorer_node


# ─── exploiter_node ───────────────────────────────────────────────────────────


def make_exploiter_node(deps: PipelineDeps) -> Callable[[PipelineState], dict[str, Any]]:
    """Refine top performers using a low-temperature, exploitation-focused agent.

    Phase 6 stub: returns empty proposals. Fully wired in Phase 8 with
    role_configs["exploiter"] (temperature=0.4, refinement system prompt).
    """

    def exploiter_node(state: PipelineState) -> dict[str, Any]:
        # Phase 6: no-op — Phase 8 wires this with role-specific ResearchAgentMutator
        log.debug("exploiter_node_stub", generation=state.get("generation", 0))
        return {"proposed_mutations": []}

    return exploiter_node


# ─── critic_node ──────────────────────────────────────────────────────────────


def make_critic_node(deps: PipelineDeps) -> Callable[[PipelineState], dict[str, Any]]:
    """Review each proposal and hard-veto poor candidates before backtest (compute saver).

    Phase 6 stub: accepts all proposals (returns empty vetoed_mutations).
    Phase 7: runs tool-using critic agent per proposal; uses query_strategy_lineage
    to detect already-failed directions; logs vetoes to experiments table.
    """

    def critic_node(state: PipelineState) -> dict[str, Any]:
        generation = state.get("generation", 0)
        n_proposals = len(state.get("proposed_mutations", []))
        # Phase 6: accept everything — critic logic added in Phase 7
        log.debug("critic_node_stub", generation=generation, n_proposals=n_proposals)
        return {"vetoed_mutations": []}

    return critic_node


# ─── aggregate_node ───────────────────────────────────────────────────────────


def make_aggregate_node(deps: PipelineDeps) -> Callable[[PipelineState], dict[str, Any]]:
    """Filter vetoed proposals, upsert surviving child strategies, write to mutations reducer.

    This node is the bridge between the multi-agent proposal phase and the existing
    ratchet_node/advance_generation machinery. Its output is format-compatible with
    the old mutate_strategies node so all downstream nodes are unchanged.

    Filtering: proposals are matched to veto records by fingerprint. Only proposals
    from the current generation are processed — old generations' proposals accumulated
    in the reducer are ignored.
    """

    def aggregate_node(state: PipelineState) -> dict[str, Any]:
        generation = state.get("generation", 0)
        bus = deps.event_bus
        t0 = time.monotonic()

        all_proposals: list[dict[str, Any]] = state.get("proposed_mutations", [])
        all_vetoed: list[dict[str, Any]] = state.get("vetoed_mutations", [])

        # Filter to current generation only — reducer accumulates across loop iterations
        current_proposals = [p for p in all_proposals if p.get("generation") == generation]
        vetoed_fps = {
            v["fingerprint"]
            for v in all_vetoed
            if v.get("generation") == generation and "fingerprint" in v
        }

        survivors = [p for p in current_proposals if p["fingerprint"] not in vetoed_fps]

        if not survivors:
            log.info(
                "aggregate_node_no_survivors",
                generation=generation,
                n_proposals=len(current_proposals),
                n_vetoed=len(vetoed_fps),
            )
            return {"mutations": []}

        if bus:
            bus.emit(EvtNodeStart("aggregate_node", generation))

        new_mutations: list[dict[str, Any]] = []

        with trace_node(
            "aggregate_node",
            enabled=deps.tracing_enabled,
            metadata={"generation": generation, "n_survivors": len(survivors)},
        ):
            for proposal in survivors:
                try:
                    det = build_detector_from_config(proposal["child_config"])
                    with connect(deps.db_path) as conn, txn(conn):
                        child_sid = upsert_strategy(
                            conn,
                            name=det.name,
                            family=det.family,
                            params=proposal["child_config"],
                        )
                    new_mutations.append(
                        {
                            "generation": generation,
                            "parent_strategy_id": proposal["parent_strategy_id"],
                            "child_strategy_id": child_sid,
                            "mutator": proposal.get("role", "explorer"),
                            "mutation_json": json.dumps(proposal["child_config"], sort_keys=True),
                            "reasoning": proposal.get("reasoning", ""),
                        }
                    )
                except Exception as exc:
                    log.warning(
                        "aggregate_upsert_failed",
                        fingerprint=proposal.get("fingerprint"),
                        error=str(exc),
                    )
                    continue

        log.info(
            "aggregate_node_done",
            generation=generation,
            n_survivors=len(survivors),
            n_mutations=len(new_mutations),
        )
        if bus:
            bus.emit(EvtNodeDone("aggregate_node", generation, (time.monotonic() - t0) * 1000))

        return {"mutations": new_mutations}

    return aggregate_node
