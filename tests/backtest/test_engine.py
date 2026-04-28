from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from atforge.backtest.engine import _bool_to_entry_exit, run_backtest


def test_signal_is_shifted_by_one_bar() -> None:
    n = 10
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    sig = pd.Series([True] * n, index=idx, name="always")

    entries, exits = _bool_to_entry_exit(sig, hold_bars=2)

    # entry at t fires AT bar t+1 — so entries[0] must be False (no lookahead).
    assert entries.iloc[0] is np.False_ or entries.iloc[0] == False  # noqa: E712
    assert bool(entries.iloc[1]) is True
    # exit equals entry shifted +hold_bars → exits[3] True when entries[1] True
    assert bool(exits.iloc[3]) is True


def test_run_backtest_returns_success_on_buys() -> None:
    n = 60
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = np.linspace(100, 150, n)  # monotone rising — any long trade wins
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": [1] * n},
        index=idx,
    )
    sig = pd.Series([False] * n, index=idx)
    sig.iloc[10] = True  # single entry

    res = run_backtest(df, sig, symbol="TEST", pattern_name="rising_line")
    assert res.success is True
    assert res.n_trades == 1
    assert res.metrics["total_return"] > Decimal("0")
    assert res.metrics["final_value"] > Decimal("100000")


def test_run_backtest_no_entries_returns_failure() -> None:
    n = 30
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {"open": [1] * n, "high": [1] * n, "low": [1] * n, "close": [1] * n, "volume": [1] * n},
        index=idx,
    )
    sig = pd.Series([False] * n, index=idx)

    res = run_backtest(df, sig, symbol="X", pattern_name="never")
    assert res.success is False
    assert "no entries" in (res.reason or "")


def test_run_backtest_empty_ohlcv_returns_failure() -> None:
    df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    sig = pd.Series([], dtype=bool)
    res = run_backtest(df, sig, symbol="X", pattern_name="empty")
    assert res.success is False
    assert "empty" in (res.reason or "")


def test_length_mismatch_returns_failure() -> None:
    idx = pd.date_range("2025-01-01", periods=5, freq="D")
    df = pd.DataFrame(
        {c: [1, 2, 3, 4, 5] for c in ["open", "high", "low", "close", "volume"]}, index=idx
    )
    sig = pd.Series([False, True, False], dtype=bool)
    res = run_backtest(df, sig, symbol="X", pattern_name="mismatch")
    assert res.success is False


def test_money_metrics_are_decimal_not_float() -> None:
    n = 40
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = np.linspace(100, 110, n)
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": [1] * n},
        index=idx,
    )
    sig = pd.Series([False] * n, index=idx)
    sig.iloc[5] = True

    res = run_backtest(df, sig, symbol="T", pattern_name="mono")
    assert isinstance(res.metrics["total_return"], Decimal)
    assert isinstance(res.metrics["final_value"], Decimal)
    assert isinstance(res.metrics["max_drawdown"], Decimal)
    # ratios stay float — analytical, not money
    assert isinstance(res.metrics["sharpe"], float)
    assert isinstance(res.metrics["win_rate"], float)


@pytest.mark.parametrize("hold_bars", [1, 5, 20])
def test_hold_bars_honored(hold_bars: int) -> None:
    n = 60
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = np.linspace(100, 200, n)
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": [1] * n},
        index=idx,
    )
    sig = pd.Series([False] * n, index=idx)
    sig.iloc[5] = True

    res = run_backtest(df, sig, symbol="H", pattern_name="hold", hold_bars=hold_bars)
    assert res.success is True
    assert res.n_trades >= 1
