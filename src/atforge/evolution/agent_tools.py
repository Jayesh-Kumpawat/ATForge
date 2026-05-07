"""Research agent tool definitions — ToolSpec + handler pairs for the ReAct loop.

Each ToolDefinition wraps an existing repo read function. The agent_runner dispatches
tool calls by name, passing args dict + open sqlite3 connection to the handler.

Adding a new tool: add a ToolDefinition to the list in build_research_tools().
No other changes needed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from atforge.llm.types import ToolSpec
from atforge.storage.repo import (
    get_experiments_for_run,
    get_mutation_tree,
    get_pattern_symbol_breakdown,
    get_strategy,
    top_rankings,
)


@dataclass(frozen=True)
class ToolDefinition:
    spec: ToolSpec
    handler: Callable[[dict[str, Any], sqlite3.Connection], dict[str, Any]]


def build_research_tools() -> list[ToolDefinition]:
    """Return the 5 read-only research tools available to the ResearchAgentMutator."""
    return [
        ToolDefinition(
            spec=ToolSpec(
                name="query_top_strategies",
                description=(
                    "Best-performing strategies (highest Sharpe per symbol-strategy pair) "
                    "across all generations. Use to see what already works before proposing mutations."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "run_id": {
                            "type": "string",
                            "description": "Filter to a specific run. Omit to query all runs.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max rows to return.",
                            "default": 10,
                        },
                    },
                },
            ),
            handler=lambda args, conn: {
                "strategies": top_rankings(
                    conn,
                    limit=int(args.get("limit", 10)),
                    run_id=args.get("run_id"),
                )
            },
        ),
        ToolDefinition(
            spec=ToolSpec(
                name="query_strategy_details",
                description="Full config and metadata for a single strategy by ID.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "strategy_id": {
                            "type": "integer",
                            "description": "The strategy_id to look up.",
                        },
                    },
                    "required": ["strategy_id"],
                },
            ),
            handler=lambda args, conn: {"strategy": get_strategy(conn, int(args["strategy_id"]))},
        ),
        ToolDefinition(
            spec=ToolSpec(
                name="query_strategy_lineage",
                description=(
                    "Mutation tree rooted at a strategy — all descendants created by past mutations. "
                    "Use to check if a mutation direction has already been tried and whether it was accepted."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "strategy_id": {
                            "type": "integer",
                            "description": "Root strategy ID.",
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "Traversal depth limit.",
                            "default": 3,
                        },
                    },
                    "required": ["strategy_id"],
                },
            ),
            handler=lambda args, conn: {
                "lineage": get_mutation_tree(
                    conn,
                    int(args["strategy_id"]),
                    int(args.get("max_depth", 3)),
                )
            },
        ),
        ToolDefinition(
            spec=ToolSpec(
                name="query_pattern_performance",
                description=(
                    "Per-symbol breakdown of a strategy's performance — avg/best Sharpe, "
                    "avg Sortino, trade count. Use to identify which symbols the strategy "
                    "works on vs. which it struggles with."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "strategy_id": {
                            "type": "integer",
                            "description": "Strategy to analyze.",
                        },
                    },
                    "required": ["strategy_id"],
                },
            ),
            handler=lambda args, conn: {
                "breakdown": get_pattern_symbol_breakdown(conn, int(args["strategy_id"]))
            },
        ),
        ToolDefinition(
            spec=ToolSpec(
                name="query_recent_experiments",
                description=(
                    "Ratchet verdicts for a run — which mutations were accepted or rejected and why. "
                    "Use to avoid repeating mutations that already failed."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "run_id": {
                            "type": "string",
                            "description": "Run to fetch experiments for.",
                        },
                        "accepted_only": {
                            "type": "boolean",
                            "description": "If true, return only accepted mutations.",
                            "default": False,
                        },
                    },
                    "required": ["run_id"],
                },
            ),
            handler=lambda args, conn: {
                "experiments": [
                    e
                    for e in get_experiments_for_run(conn, args["run_id"])
                    if not args.get("accepted_only") or e["accepted"] == 1
                ]
            },
        ),
    ]
