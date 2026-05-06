"""System prompts and initial-message builders for the ResearchAgentMutator ReAct loop."""

from __future__ import annotations

_PROPOSAL_SCHEMA = (
    '{"proposal_type": "sma_param_delta" | "rsi_param_delta", '
    '"sma": {"fast": <int 2-50>, "slow": <int 10-200 and > fast>, "reasoning": "<one sentence>"} | null, '
    '"rsi": {"period": <int 2-50>, "oversold": <int 10-45>, "reasoning": "<one sentence>"} | null, '
    '"research_summary": "<≤2 sentence summary of findings>", '
    '"confidence": <float 0.0-1.0>}'
)

RESEARCH_SYSTEM = (
    "You are a quantitative analyst with read-only access to an ATForge strategy database "
    "for NSE Indian equities (daily bars). "
    "Your task: use the available tools to research past strategy performance, then propose ONE mutation "
    "to improve the given strategy's risk-adjusted returns. "
    "Think step by step — check what has been tried before, identify unexplored regions of the parameter space, "
    "then propose a mutation that has not yet been tried and is likely to improve Sharpe. "
    "When done researching, emit ONLY a valid JSON object matching this schema — no markdown fences, no extra text:\n"
    f"{_PROPOSAL_SCHEMA}"
)

RESEARCH_FINAL_TURN = (
    "You have reached the iteration limit. "
    "Based on your research, emit your final ResearchProposal JSON now — "
    "valid JSON only, no markdown fences, no extra text."
)


def research_initial_message(
    strategy_id: int,
    strategy_name: str,
    detector_type: str,
    params: dict,
    mean_sharpe: float,
    mean_sortino: float,
    n_trades: int,
) -> str:
    param_str = ", ".join(f"{k}={v}" for k, v in params.items() if k != "type")
    return (
        f"Strategy to improve: ID={strategy_id}, name='{strategy_name}', "
        f"type={detector_type}, params=({param_str}).\n"
        f"Current performance: Sharpe={mean_sharpe:.3f}, Sortino={mean_sortino:.3f}, trades={n_trades}.\n"
        f"\n"
        f"Suggested research steps:\n"
        f"1. query_top_strategies — see what parameters perform best overall.\n"
        f"2. query_strategy_lineage (strategy_id={strategy_id}) — see what mutations were already tried.\n"
        f"3. query_pattern_performance (strategy_id={strategy_id}) — find which symbols this strategy "
        f"struggles on, to guide parameter direction.\n"
        f"4. Propose new parameters that have not been tried and target the identified weaknesses.\n"
        f"\n"
        f"Emit final ResearchProposal JSON when research is complete."
    )
