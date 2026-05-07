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

from atforge.evolution.agent_runner import run_react_loop
from atforge.evolution.agent_tools import build_research_tools
from atforge.evolution.mutators.research_agent import ResearchAgentMutator
from atforge.evolution.prompts import CriticVerdict
from atforge.evolution.registry import build_detector_from_config
from atforge.evolution.research_prompts import (
    CRITIC_SYSTEM_PROMPT,
    critic_initial_message,
)
from atforge.graph.deps import AgentRoleConfig, PipelineDeps
from atforge.graph.events import EvtCriticVerdict, EvtMutationProposed, EvtNodeDone, EvtNodeStart
from atforge.graph.state import PipelineState
from atforge.llm.tracing import score_current_observation, trace_node
from atforge.storage.db import connect, txn
from atforge.storage.repo import (
    get_top_strategies_for_generation,
    insert_experiment,
    upsert_strategy,
)

log = structlog.get_logger(__name__)


def _make_fingerprint(parent_strategy_id: int, child_config: dict[str, Any]) -> str:
    """Stable dedup key: parent_id + canonical JSON of child config."""
    return f"{parent_strategy_id}:{json.dumps(child_config, sort_keys=True)}"


def _proposals_from_mutator(
    deps: PipelineDeps,
    run_id: str,
    generation: int,
    role: str,
    mutator: Any,
) -> list[dict[str, Any]]:
    """Call a single mutator and wrap results as proposal dicts."""
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

    try:
        raw_proposals = mutator.propose(parents, k=deps.top_n_parents)
    except Exception:
        return proposals

    if deps.event_bus:
        deps.event_bus.emit(EvtMutationProposed(mutator.name, len(raw_proposals)))

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
            tags=["explorer"],
        ):
            proposals = _proposals_from_mutators(deps, run_id, generation, role="explorer")

        log.info("explorer_node_done", generation=generation, n_proposals=len(proposals))
        if bus:
            bus.emit(EvtNodeDone("explorer_node", generation, (time.monotonic() - t0) * 1000))

        return {"proposed_mutations": proposals}

    return explorer_node


# ─── exploiter_node ───────────────────────────────────────────────────────────


def make_exploiter_node(deps: PipelineDeps) -> Callable[[PipelineState], dict[str, Any]]:
    """Refine top performers using a low-temperature, exploitation-focused ResearchAgentMutator.

    Phase 8: when llm_router is present, builds a ResearchAgentMutator using the
    "exploiter" role config (temperature=0.4, refinement system prompt) and queries
    top parents directly — independent of deps.mutators.

    When llm_router is None, returns empty proposals (backward compat with Phase 6 stub).
    """

    def exploiter_node(state: PipelineState) -> dict[str, Any]:
        generation = state.get("generation", 0)
        max_gen = state.get("max_generations", 1)

        if generation + 1 >= max_gen or deps.llm_router is None:
            log.debug(
                "exploiter_node_skip",
                generation=generation,
                reason="at_max_gen" if generation + 1 >= max_gen else "no_llm_router",
            )
            return {"proposed_mutations": []}

        from atforge.evolution.research_prompts import EXPLOITER_SYSTEM_PROMPT

        role_cfg: AgentRoleConfig = deps.role_configs.get(
            "exploiter",
            AgentRoleConfig(
                role="exploiter",
                temperature=0.4,
                max_iterations=4,
                system_prompt=EXPLOITER_SYSTEM_PROMPT,
            ),
        )

        run_id = state["run_id"]
        bus = deps.event_bus
        t0 = time.monotonic()

        if bus:
            bus.emit(EvtNodeStart("exploiter_node", generation))

        with trace_node(
            "exploiter_node",
            enabled=deps.tracing_enabled,
            metadata={"generation": generation, "role": "exploiter"},
            tags=["exploiter"],
        ):
            exploiter_mutator = ResearchAgentMutator(
                deps.llm_router,
                db_path=deps.db_path,
                model=role_cfg.model,
                temperature=role_cfg.temperature,
                max_iterations=role_cfg.max_iterations,
                system_prompt_override=role_cfg.system_prompt,
                event_bus=deps.event_bus,
            )
            proposals = _proposals_from_mutator(
                deps, run_id, generation, role="exploiter", mutator=exploiter_mutator
            )

        log.info("exploiter_node_done", generation=generation, n_proposals=len(proposals))
        if bus:
            bus.emit(EvtNodeDone("exploiter_node", generation, (time.monotonic() - t0) * 1000))

        return {"proposed_mutations": proposals}

    return exploiter_node


# ─── critic_node ──────────────────────────────────────────────────────────────


def _parse_critic_verdict(raw: str | None) -> CriticVerdict | None:
    """Parse critic LLM output to CriticVerdict. Returns None on any failure."""
    if not raw:
        return None
    from atforge.evolution.mutators._utils import _brace_match, _strip_fences

    text = _strip_fences(raw)
    try:
        import json as _json

        data = _json.loads(text)
    except Exception:
        extracted = _brace_match(text)
        if not extracted:
            return None
        try:
            import json as _json

            data = _json.loads(extracted)
        except Exception:
            return None
    try:
        return CriticVerdict.model_validate(data)
    except Exception:
        return None


def make_critic_node(deps: PipelineDeps) -> Callable[[PipelineState], dict[str, Any]]:
    """Review each proposal and hard-veto poor candidates before backtest (compute saver).

    Phase 7: tool-using critic agent per proposal. Uses query_strategy_lineage
    to detect already-failed directions. Vetoed proposals logged to experiments
    with mutator='critic_veto', accepted=0, child_strategy_id=NULL.

    When llm_router is None (no LLM configured), falls back to Phase 6 stub: accept all.
    On LLM failure for any proposal: safe default is accept (never block on LLM error).
    """

    def critic_node(state: PipelineState) -> dict[str, Any]:
        generation = state.get("generation", 0)
        run_id = state["run_id"]

        all_proposals: list[dict[str, Any]] = state.get("proposed_mutations", [])
        current_proposals = [p for p in all_proposals if p.get("generation") == generation]

        if not current_proposals or deps.llm_router is None:
            log.debug(
                "critic_node_skip",
                generation=generation,
                n_proposals=len(current_proposals),
                reason="no proposals" if not current_proposals else "no llm_router",
            )
            return {"vetoed_mutations": []}

        role_cfg: AgentRoleConfig = deps.role_configs.get(
            "critic",
            AgentRoleConfig(
                role="critic",
                temperature=0.3,
                max_iterations=3,
                system_prompt=CRITIC_SYSTEM_PROMPT,
            ),
        )

        tools = build_research_tools()
        vetoed: list[dict[str, Any]] = []

        with trace_node(
            "critic_node",
            enabled=deps.tracing_enabled,
            metadata={"generation": generation, "role": "critic"},
            tags=["critic"],
        ):
            with connect(deps.db_path) as conn:
                for proposal in current_proposals:
                    parent_sid = proposal["parent_strategy_id"]
                    child_config = proposal["child_config"]
                    fingerprint = proposal["fingerprint"]

                    raw = run_react_loop(
                        deps.llm_router,
                        tools,
                        role_cfg.system_prompt,
                        critic_initial_message(proposal),
                        conn,
                        max_iterations=role_cfg.max_iterations,
                        event_bus=deps.event_bus,
                        role="critic",
                        parent_strategy_id=parent_sid,
                        temperature=role_cfg.temperature,
                        trace_name="critic_agent",
                    )

                    verdict = _parse_critic_verdict(raw)

                    # Emit verdict event regardless of outcome
                    if deps.event_bus:
                        deps.event_bus.emit(
                            EvtCriticVerdict(
                                parent_strategy_id=parent_sid,
                                fingerprint=fingerprint,
                                verdict=verdict.verdict if verdict else "accept",
                                reason=verdict.reason if verdict else "parse_failed_safe_accept",
                            )
                        )

                    if verdict and verdict.verdict == "veto":
                        veto_record = {
                            "generation": generation,
                            "parent_strategy_id": parent_sid,
                            "child_config": child_config,
                            "fingerprint": fingerprint,
                            "veto_reason": verdict.reason,
                            "role": "critic",
                        }
                        vetoed.append(veto_record)

                        try:
                            with txn(conn):
                                insert_experiment(
                                    conn,
                                    run_id=run_id,
                                    generation=generation,
                                    parent_strategy_id=parent_sid,
                                    child_strategy_id=None,
                                    mutator="critic_veto",
                                    mutation_json=json.dumps(child_config, sort_keys=True),
                                    accepted=0,
                                    delta_sharpe=0.0,
                                    composite_score_json=json.dumps({"critic_veto": 1.0}),
                                    reasoning=verdict.reason,
                                )
                        except Exception as exc:
                            log.warning(
                                "critic_veto_log_failed",
                                fingerprint=fingerprint,
                                error=str(exc),
                            )

            veto_rate = len(vetoed) / len(current_proposals) if current_proposals else 0.0
            score_current_observation(
                "veto_rate",
                veto_rate,
                enabled=deps.tracing_enabled,
                comment=f"{len(vetoed)}/{len(current_proposals)} vetoed",
            )

        log.info(
            "critic_node_done",
            generation=generation,
            n_proposals=len(current_proposals),
            n_vetoed=len(vetoed),
        )
        return {"vetoed_mutations": vetoed}

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
