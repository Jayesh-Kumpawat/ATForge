# Pattern Detection — `src/atforge/patterns/`

## What this module does

Detects chart patterns in OHLCV data and emits boolean entry signals. Each detector is an independent, stateless object that takes a DataFrame and returns a `PatternSignal`.

## Key abstractions

### `PatternSignal` (`base.py`)
Frozen dataclass. Holds the result of one detector run on one symbol.

```python
@dataclass(frozen=True)
class PatternSignal:
    pattern_name: str
    family: str           # "candlestick" | "indicator" | "structural"
    signal: pd.Series     # dtype=bool, same index as OHLCV input
```

`__post_init__` rejects non-bool signal dtype — `True` on signal bar, `False` otherwise. No NaN, no floats.

### `PatternDetector` Protocol (`base.py`)
```python
class PatternDetector(Protocol):
    name: str
    family: str
    def detect(self, ohlcv: pd.DataFrame) -> PatternSignal: ...
```

Any object matching this shape is a valid detector. No ABC inheritance.

## Detectors

### `TalibCdlDetector` (`talib_cdl.py`)
Wraps TA-Lib `CDL*` functions. TA-Lib returns integers: `+100` bullish, `-100` bearish, `0` none.

```python
TalibCdlDetector("CDLENGULFING", direction="bullish")  # signal when raw > 0
TalibCdlDetector("CDLENGULFING", direction="bearish")  # signal when raw < 0
```

Available patterns (10): `CDLENGULFING`, `CDLHAMMER`, `CDLMORNINGSTAR`, `CDLEVENINGSTAR`, `CDLSHOOTINGSTAR`, `CDLDOJI`, `CDLHANGINGMAN`, `CDL3WHITESOLDIERS`, `CDL3BLACKCROWS`, `CDLDARKCLOUDCOVER`

**TA-Lib native C library required**: `brew install ta-lib` before `uv sync`. Python wrapper links `libta_lib.dylib` at runtime.

### `SmaCrossover` (`pandas_ta.py`)
Fast SMA crosses above slow SMA → bullish signal on crossover bar only (not all bars where fast > slow).

```python
SmaCrossover(fast=20, slow=50)   # "SMA_20x50_bullish"
SmaCrossover(fast=10, slow=30)   # "SMA_10x30_bullish"
```

Uses pandas rolling mean — no external library. Cross detection: `(fast > slow) & (fast.shift(1) <= slow.shift(1))`.

### `RsiOversoldReclaim` (`pandas_ta.py`)
RSI crosses back above oversold threshold — mean-reversion long signal.

```python
RsiOversoldReclaim(period=14, oversold=30)  # "RSI_14_reclaim_30"
```

Uses `pandas_ta_classic.rsi`. Uses `pandas-ta-classic` (NOT `pandas-ta` — that package has a supply chain compromise risk, see CONTEXT.md).

### `DoubleBottomDetector` (`structural.py`)
Phase 1 stub. Uses `scipy.signal.find_peaks` on negated close prices to find troughs, then checks for two comparable troughs with a local peak between them.

Emits `True` on the second trough bar. Parameters: `lookback=60` bars, `tolerance_pct=3.0` (troughs must be within 3% depth of each other).

Full structural suite (cup-and-handle, H&S, double tops) completes in Phase 2.

## Default detector set (13 total)

Set up in `cli.py::_default_detectors()`:
- 10 TA-Lib CDL patterns (bullish direction)
- `SmaCrossover(20, 50)`, `SmaCrossover(10, 30)`
- `RsiOversoldReclaim(14, 30)`

## Key invariants

- Signals are raw — they are NOT shifted here. The backtest engine shifts +1 bar.
- Signal index must match the OHLCV input index exactly.
- Detectors must be stateless — no mutable state, safe to reuse across symbols.

## Composition detectors (`composition.py`)

`AndDetector(left, right)` and `OrDetector(left, right)` combine two detectors via `&` / `|` on their signal Series. Satisfy the `PatternDetector` Protocol structurally — no inheritance.

```python
from atforge.patterns.composition import AndDetector, OrDetector

combined = AndDetector(SmaCrossover(5, 20), RsiOversoldReclaim(14, 30))
signal = combined.detect(ohlcv_df)
# signal.signal = sma_signal & rsi_signal
# signal.pattern_name = "AND(SMA_5x20_bullish,RSI_14_reclaim_30)"
```

**Deterministic naming**: `name = f"{op}({left.name},{right.name})"`. This feeds `upsert_strategy` whose UNIQUE constraint is `(name, params_json)` — stable names are required for dedup.

**Serialization**: `evolution/registry.py` converts these to/from `DetectorConfig` dicts:
```python
{"type": "and", "left": {"type": "sma_crossover", ...}, "right": {"type": "rsi_oversold", ...}}
```
Always serialized with `sort_keys=True` — UNIQUE constraint depends on stable key ordering.

`CompositionMutator` (in `evolution/mutators/composition.py`) generates these via LLM-guided pairwise combination of top-N parents. Max nesting depth 2 prevents signal explosion (AND of AND of AND...).

## Tests

```
tests/patterns/test_detectors.py   — PatternSignal dtype guard, SMA/RSI smoke tests, DoubleBottom stub
tests/patterns/test_composition.py — AndDetector, OrDetector signal logic, name format
```
