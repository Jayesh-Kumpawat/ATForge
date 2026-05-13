from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pandas as pd
import structlog
import vectorbt as vbt

from atforge.backtest.metrics import compute_metrics

log = structlog.get_logger(__name__)

DEFAULT_INIT_CASH = Decimal("100000")
DEFAULT_HOLD_BARS = 10


@dataclass(frozen=True, slots=True)
class BacktestResult:
    success: bool
    pattern_name: str
    symbol: str
    metrics: dict[str, Decimal | int | float] = field(default_factory=dict)
    n_trades: int = 0
    reason: str | None = None
    equity_json: str | None = None    # JSON array of {t, equity, drawdown} points
    signals_json: str | None = None   # JSON array of {t, type, price} markers


def _extract_equity_json(portfolio: Any, ohlcv: pd.DataFrame) -> str:
    value = portfolio.value()
    dd = portfolio.drawdown()
    return json.dumps([
        {"t": int(ts.timestamp() * 1000), "equity": round(float(v), 4), "drawdown": round(float(d), 6)}
        for ts, v, d in zip(value.index, value, dd)
    ])


def _extract_signals_json(entries: pd.Series, exits: pd.Series, ohlcv: pd.DataFrame) -> str:
    close = ohlcv["close"]
    markers: list[dict[str, Any]] = []
    for ts in entries.index[entries]:
        if ts in close.index:
            markers.append({"t": int(ts.timestamp() * 1000), "type": "entry", "price": float(close[ts])})
    for ts in exits.index[exits]:
        if ts in close.index:
            markers.append({"t": int(ts.timestamp() * 1000), "type": "exit", "price": float(close[ts])})
    markers.sort(key=lambda x: x["t"])
    return json.dumps(markers)


def _bool_to_entry_exit(signal: pd.Series, hold_bars: int) -> tuple[pd.Series, pd.Series]:
    """Shift entry signal +1 bar (no lookahead), then build exit as entry shifted +hold_bars."""
    shifted = signal.shift(1, fill_value=False).astype(bool)
    shifted.name = f"{signal.name or 'entry'}_shifted"
    exits = shifted.shift(hold_bars, fill_value=False).astype(bool)
    return shifted, exits


def run_backtest(
    ohlcv: pd.DataFrame,
    signal: pd.Series,
    *,
    symbol: str,
    pattern_name: str,
    init_cash: Decimal = DEFAULT_INIT_CASH,
    hold_bars: int = DEFAULT_HOLD_BARS,
    fees: float = 0.0003,
    slippage: float = 0.0005,
) -> BacktestResult:
    """Run a vectorbt backtest with mandatory +1 bar signal shift.

    Returns `BacktestResult(success=False, reason=...)` on any failure rather
    than raising — worker nodes must never propagate exceptions (CLAUDE.md rule).
    """
    try:
        if len(ohlcv) == 0:
            return BacktestResult(False, pattern_name, symbol, reason="empty ohlcv")
        if len(signal) != len(ohlcv):
            return BacktestResult(
                False, pattern_name, symbol, reason="signal/ohlcv length mismatch"
            )

        entries, exits = _bool_to_entry_exit(signal, hold_bars=hold_bars)
        if not entries.any():
            return BacktestResult(False, pattern_name, symbol, reason="no entries after shift")

        portfolio = vbt.Portfolio.from_signals(
            close=ohlcv["close"],
            entries=entries,
            exits=exits,
            init_cash=float(init_cash),
            fees=fees,
            slippage=slippage,
            freq="1D",
        )

        metrics = compute_metrics(portfolio)
        trades = portfolio.trades.records_readable
        n_trades = len(trades)

        try:
            equity_json = _extract_equity_json(portfolio, ohlcv)
            signals_json = _extract_signals_json(entries, exits, ohlcv)
        except Exception:
            equity_json = None
            signals_json = None

        return BacktestResult(
            success=True,
            pattern_name=pattern_name,
            symbol=symbol,
            metrics=metrics,
            n_trades=n_trades,
            equity_json=equity_json,
            signals_json=signals_json,
        )
    except Exception as exc:
        log.warning(
            "backtest_failed",
            symbol=symbol,
            pattern=pattern_name,
            error=str(exc),
        )
        return BacktestResult(False, pattern_name, symbol, reason=f"{type(exc).__name__}: {exc}")


def portfolio_for_debug(
    ohlcv: pd.DataFrame,
    signal: pd.Series,
    *,
    hold_bars: int = DEFAULT_HOLD_BARS,
    init_cash: Decimal = DEFAULT_INIT_CASH,
) -> Any:
    """Escape hatch — return the raw vectorbt Portfolio. Tests only."""
    entries, exits = _bool_to_entry_exit(signal, hold_bars=hold_bars)
    return vbt.Portfolio.from_signals(
        close=ohlcv["close"],
        entries=entries,
        exits=exits,
        init_cash=float(init_cash),
        freq="1D",
    )
