from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from atforge.graph.deps import PipelineDeps
from atforge.graph.nodes import (
    make_detect_patterns,
    make_fetch_data,
    make_load_universe,
    make_rank,
    make_run_backtest,
)
from atforge.graph.state import PipelineState


def build_pipeline(deps: PipelineDeps):
    """Compile the Phase 1 linear graph.

    Phase 2 will swap this for a Send-API fan-out — node bodies already operate
    per-item so fan-out changes only the wiring here.
    """
    deps.ensure_dirs()

    g: StateGraph = StateGraph(PipelineState)
    g.add_node("load_universe", make_load_universe(deps))
    g.add_node("fetch_data", make_fetch_data(deps))
    g.add_node("detect_patterns", make_detect_patterns(deps))
    g.add_node("run_backtest", make_run_backtest(deps))
    g.add_node("rank", make_rank(deps))

    g.add_edge(START, "load_universe")
    g.add_edge("load_universe", "fetch_data")
    g.add_edge("fetch_data", "detect_patterns")
    g.add_edge("detect_patterns", "run_backtest")
    g.add_edge("run_backtest", "rank")
    g.add_edge("rank", END)

    return g.compile()
