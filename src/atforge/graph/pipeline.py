from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from atforge.graph.deps import PipelineDeps
from atforge.graph.nodes import (
    make_detect_patterns,
    make_fetch_data,
    make_load_universe,
    make_rank,
)
from atforge.graph.nodes_a2 import (
    make_aggregate_node,
    make_critic_node,
    make_exploiter_node,
    make_explorer_node,
)
from atforge.graph.nodes_phase2 import (
    make_advance_generation,
    make_loop_decision,
    make_ratchet_node,
    make_run_backtest_dispatcher,
    make_run_backtest_one,
)
from atforge.graph.state import PipelineState


def build_pipeline(deps: PipelineDeps):
    """Compile the A2 multi-agent pipeline.

    Layout: load_universe -> fetch_data -> detect_patterns
              -> [Send] run_backtest_one (parallel fan-out)
              -> ratchet (no-op on gen=0, scores on gen=1+)
              -> rank
              -> explorer_node   (propose mutations — full in Phase 6, role-LLM in Phase 8)
              -> exploiter_node  (refine top performers — stub in Phase 6, wired in Phase 8)
              -> critic_node     (hard-veto bad proposals — stub in Phase 6, wired in Phase 7)
              -> aggregate_node  (filter vetoed, upsert survivors, write to mutations reducer)
              -> loop_decision
                   continue: -> advance_generation -> detect_patterns (loop)
                   stop:     -> END
    """
    deps.ensure_dirs()

    g: StateGraph = StateGraph(PipelineState)
    g.add_node("load_universe", make_load_universe(deps))
    g.add_node("fetch_data", make_fetch_data(deps))
    g.add_node("detect_patterns", make_detect_patterns(deps))
    g.add_node("run_backtest_one", make_run_backtest_one(deps))
    g.add_node("ratchet", make_ratchet_node(deps))
    g.add_node("rank", make_rank(deps))
    g.add_node("explorer_node", make_explorer_node(deps))
    g.add_node("exploiter_node", make_exploiter_node(deps))
    g.add_node("critic_node", make_critic_node(deps))
    g.add_node("aggregate_node", make_aggregate_node(deps))
    g.add_node("advance_generation", make_advance_generation(deps))

    g.add_edge(START, "load_universe")
    g.add_edge("load_universe", "fetch_data")
    g.add_edge("fetch_data", "detect_patterns")
    g.add_conditional_edges(
        "detect_patterns",
        make_run_backtest_dispatcher(),
        ["run_backtest_one"],
    )
    g.add_edge("run_backtest_one", "ratchet")
    g.add_edge("ratchet", "rank")
    g.add_edge("rank", "explorer_node")
    g.add_edge("explorer_node", "exploiter_node")
    g.add_edge("exploiter_node", "critic_node")
    g.add_edge("critic_node", "aggregate_node")
    g.add_conditional_edges(
        "aggregate_node",
        make_loop_decision(),
        {"continue": "advance_generation", "stop": END},
    )
    g.add_edge("advance_generation", "detect_patterns")

    return g.compile()
