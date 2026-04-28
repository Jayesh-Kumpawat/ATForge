# Backtest Engine — `src/atforge/backtest/`

## What this module does

Runs vectorbt backtests on OHLCV + signal pairs. Returns structured results with metrics. Never raises — returns `success=False` instead (CLAUDE.md hard rule for worker nodes).

## Key abstractions

### `BacktestResult` (`engine.py`)
Frozen dataclass. All outputs flow through here.

```python
@dataclass(frozen=True, slots=True)
class BacktestResult:
    success: bool
    pattern_name: str
    symbol: str
    metrics: dict[str, Decimal | int | float]  # see compute_metrics
    n_trades: int = 0
    reason: str | None = None   # set on failure
```

### `_bool_to_entry_exit(signal, hold_bars)` (`engine.py`)
**The most important function in the engine.**

Implements the +1 bar signal shift that prevents lookahead bias:
```python
shifted = signal.shift(1, fill_value=False).astype(bool)
exits = shifted.shift(hold_bars, fill_value=False).astype(bool)
```

Signal fires on bar T → entry executes at open of bar T+1. Exit fires `hold_bars` after entry.

Why `fill_value=False` not `.fillna(False)`: pandas deprecated the fillna downcasting pattern in newer versions. `fill_value` parameter avoids the FutureWarning.

### `run_backtest(ohlcv, signal, ...)` (`engine.py`)
Main entry point. Calls `_bool_to_entry_exit`, then `vbt.Portfolio.from_signals`.

```python
run_backtest(
    ohlcv,         # pd.DataFrame with OHLCV columns
    signal,        # pd.Series[bool] — raw pattern signal, NOT pre-shifted
    symbol="RELIANCE",
    pattern_name="CDLENGULFING_bullish",
    init_cash=Decimal("100000"),
    hold_bars=10,
    fees=0.0003,   # 0.03% per trade (NSE typical)
    slippage=0.0005,
)
```

Failure modes that return `success=False`:
- Empty OHLCV
- Signal/OHLCV length mismatch
- No entries after shift (signal fires only on last bar → shift eliminates it)
- Any vectorbt exception

### `portfolio_for_debug(ohlcv, signal, ...)` (`engine.py`)
Returns raw `vbt.Portfolio` object. Tests and dashboard only — not used in pipeline.

## Metrics (`metrics.py`)

`compute_metrics(portfolio)` extracts from vectorbt Portfolio:

| Metric | Type | Notes |
|---|---|---|
| `total_return` | `Decimal` | Portfolio return vs initial cash |
| `final_value` | `Decimal` | Portfolio value at end |
| `max_drawdown` | `Decimal` | Max peak-to-trough drawdown |
| `sharpe` | `float` | Annualized Sharpe ratio |
| `sortino` | `float` | Annualized Sortino ratio |
| `cagr` | `float` | Compound annual growth rate |
| `win_rate` | `float` | Fraction of trades profitable |

**Money values are Decimal, ratios are float.** This is a hard project rule.

`_safe_decimal(x)`: converts any vectorbt output to Decimal safely. Handles `None`, `NaN`, `inf` → `Decimal(0)`. Uses `Decimal(str(float_value))` to avoid binary representation drift.

## Configuration defaults

```python
DEFAULT_INIT_CASH = Decimal("100000")   # ₹1 lakh starting capital
DEFAULT_HOLD_BARS = 10                   # hold 10 trading days
fees = 0.0003                           # 0.03% per leg
slippage = 0.0005                       # 0.05% per leg
freq = "1D"                             # always daily
```

## Key invariants

- **Never raise from `run_backtest`** — catch all exceptions, return `BacktestResult(success=False, reason=...)`.
- **Always shift signals +1 bar** — vectorbt has no built-in lookahead guard.
- **`freq="1D"` always** — vectorbt needs this for correct annualization of Sharpe/CAGR.
- **Float for vectorbt, Decimal at storage boundary** — OHLCV and signal math uses float64; Decimal conversion happens in `compute_metrics`.

## Tests

```
tests/backtest/test_engine.py  — signal shift (no-lookahead proof), Decimal type enforcement,
                                  hold_bars honored, empty/mismatch failure cases
```
