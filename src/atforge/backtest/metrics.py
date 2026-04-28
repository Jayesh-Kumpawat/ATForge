from __future__ import annotations

import math
from decimal import Decimal
from typing import Any


def _safe_decimal(x: Any) -> Decimal:
    """Money-side values cross the storage boundary as Decimal (CLAUDE.md rule).

    NaN/inf → Decimal(0). Float → str → Decimal to avoid binary-repr drift.
    """
    if x is None:
        return Decimal(0)
    try:
        f = float(x)
    except (TypeError, ValueError):
        return Decimal(0)
    if math.isnan(f) or math.isinf(f):
        return Decimal(0)
    return Decimal(str(f))


def compute_metrics(portfolio: Any) -> dict[str, Decimal | float | int]:
    """Extract canonical metric set from a vectorbt Portfolio.

    Returns:
        sharpe, sortino, max_drawdown, cagr, win_rate, total_return, final_value.
        Money-side values (total_return, final_value, max_drawdown) are Decimal.
        Ratios (sharpe, sortino, win_rate, cagr) are float — purely analytical.
    """
    total_return = _safe_decimal(portfolio.total_return())
    max_dd = _safe_decimal(portfolio.max_drawdown())
    final_value = _safe_decimal(portfolio.value().iloc[-1])

    def _as_float(x: Any) -> float:
        try:
            f = float(x)
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return f

    sharpe = _as_float(portfolio.sharpe_ratio())
    sortino = _as_float(portfolio.sortino_ratio())
    cagr = _as_float(portfolio.annualized_return())

    trades = portfolio.trades
    try:
        win_rate = _as_float(trades.win_rate())
    except Exception:
        win_rate = 0.0

    return {
        "total_return": total_return,
        "final_value": final_value,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "cagr": cagr,
        "win_rate": win_rate,
    }
