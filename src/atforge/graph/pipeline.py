from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from atforge.graph.deps import PipelineDeps
from atforge.graph.nodes import (
    make_detect_patterns,
    make_fetch_data,
    make_load_universe,
    make_rank,
)
from atforge.graph.nodes_phase2 import (
    make_advance_generation,
    make_loop_decision,
    make_mutate_strategies,
    make_ratchet_node,
    make_run_backtest_dispatcher,
    make_run_backtest_one,
)
from atforge.graph.state import PipelineState


def build_pipeline(deps: PipelineDeps):
    """Compile the Phase 2a pipeline.

    Layout: load_universe -> fetch_data -> detect_patterns
              -> [Send] run_backtest_one (parallel fan-out)
              -> ratchet (no-op on gen=0, scores on gen=1+)
              -> rank
              -> mutate_strategies
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
    g.add_node("mutate_strategies", make_mutate_strategies(deps))
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
    g.add_edge("rank", "mutate_strategies")
    g.add_conditional_edges(
        "mutate_strategies",
        make_loop_decision(),
        {"continue": "advance_generation", "stop": END},
    )
    g.add_edge("advance_generation", "detect_patterns")

    return g.compile()
