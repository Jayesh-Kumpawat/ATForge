# ATForge — Design Decisions

The *why* behind the codebase. Read this when a rule in CLAUDE.md seems arbitrary.
For *what* happens at runtime, see [INTERNALS.md](INTERNALS.md).

> **Verified against code:** 2026-05-05.
> Section tags: `<!-- section:invariants -->`, `<!-- section:architecture -->`, `<!-- section:errors -->`, `<!-- section:llm -->`

---

## Contents

1. [Core invariants — rules and why they exist](#1-core-invariants)
2. [Architecture decisions](#2-architecture-decisions)
3. [Error taxonomy and debugging](#3-error-taxonomy-and-debugging)
4. [LLM robustness pipeline](#4-llm-robustness-pipeline)

---

## 1. Core invariants

<!-- section:invariants -->

These are CLAUDE.md rules explained. Violating them causes real bugs.

---

### Use `Decimal`, never `float`, for financial values

**Rule:** `max_drawdown` in `BacktestResult` and `EvaluationResult` is `Decimal`. Every financial value stored in the DB goes in as `str(Decimal(...))`.

**Why:**
```python
>>> 0.1 + 0.2
0.30000000000000004

>>> Decimal("0.1") + Decimal("0.2")
Decimal('0.3')
```

Float arithmetic accumulates rounding errors. In backtesting, drawdown and PnL are summed across hundreds of trades. Small float errors compound. The ratchet's Gate 3 checks `child_dd / parent_dd <= 1.10` — if both values have float drift, a child that is actually at exactly 1.10× could be wrongly accepted or rejected.

**Where it applies:**
- `BacktestResult.metrics["max_drawdown"]` — stored as `Decimal`
- `EvaluationResult.max_drawdown` — `Decimal`
- `RatchetVerdict.dd_ratio` — `float` OK here (analytical ratio, not money)
- `strategies.params_json` — no Decimal here; these are indicator parameters (integers/floats are fine for `fast`, `slow`, `period`)

---

### `json.dumps(sort_keys=True)` on all `DetectorConfig`

**Rule:** Every `json.dumps` call on a `DetectorConfig` must use `sort_keys=True`. This is a correctness requirement, not style.

**Why:**  
`strategies` table has `UNIQUE (name, params_json)`. This constraint is the deduplication mechanism — running the same pipeline twice doesn't create duplicate strategy rows.

Python dicts preserve insertion order since 3.7. But insertion order differs between code paths:

```python
# In cli.py, building from constructor kwargs:
{"type": "sma_crossover", "fast": 10, "slow": 25}

# After LLM proposes and we parse JSON:
{"fast": 10, "slow": 25, "type": "sma_crossover"}   # LLM orders alphabetically
```

Without `sort_keys=True`, these produce different JSON strings → different `params_json` → `upsert_strategy` creates TWO rows for the same logical strategy → downstream Sharpe comparisons become meaningless.

`detector_params_json()` in `registry.py` enforces this automatically. Always use it instead of raw `json.dumps` on configs.

---

### Shift entry signals +1 bar in vectorbt

**Rule:** Before passing signal Series to vectorbt, shift it forward by 1 bar: `sig = sig.shift(1).fillna(False)`.

**Why — lookahead bias:**
```
Day 1: CDL_HAMMER fires → signal=True
Day 1: vectorbt enters position at Day 1's CLOSE price

Problem: you cannot know a CDL_HAMMER fired until Day 1 closes.
         You cannot trade at Day 1's close price after seeing it.
         In reality you trade Day 2's OPEN.
```

Without the shift, backtest returns look better than live trading will ever produce. The +1 bar shift means: "I see the signal at Day 1 close, I enter at Day 2 open (approximated by Day 2 close in daily data)." This is conservative but honest.

The shift happens inside `backtest/engine.py`, not in the signal detection or graph nodes. Callers don't need to shift manually.

---

### Never put DataFrames or Portfolio objects in `PipelineState`

**Rule:** State holds only IDs and file paths. Never actual DataFrames.

**Why — LangGraph checkpointing:**

LangGraph serializes the entire state at each node boundary (for HITL interrupts, retries, and persistence). A OHLCV DataFrame for one symbol is ~250 rows × 6 columns. Across 50 Nifty symbols × multiple generations, that's megabytes of data being serialized and deserialized repeatedly.

With 26 parallel `run_backtest_one` workers, LangGraph merges their return dicts 26 times. If those dicts contained DataFrames, each merge would deep-copy large arrays.

**Instead:** Nodes write data to disk (parquet) or DB, store the path/ID in state. Any node that needs the data reads from disk. This is explicit I/O with a clear audit trail.

---

### `return {"backtest_ids": [new_id]}` — delta only from reducer nodes

**Rule:** Nodes that write to reducer fields must return only their new delta, not the full accumulated list.

**Why:**

LangGraph applies `operator.add(existing_list, returned_list)`. If node returns the full list:

```python
# existing state: backtest_ids = [1, 2, 3]
# node returns:   {"backtest_ids": [1, 2, 3, 4]}   ← WRONG

# LangGraph does: operator.add([1,2,3], [1,2,3,4]) = [1,2,3,1,2,3,4]
# → duplicated IDs, queries return double results, ratchet scores are wrong
```

Correct:
```python
# node returns: {"backtest_ids": [4]}   ← only what THIS node produced
# LangGraph does: operator.add([1,2,3], [4]) = [1,2,3,4]
```

---

### Never raise from worker nodes

**Rule:** `fetch_data`, `detect_patterns`, `run_backtest_one` must catch all exceptions and append to `failures`. Never `raise`.

**Why:**

An unhandled exception in a LangGraph node aborts the entire graph. If `run_backtest_one` raises for one signal, all 25 other workers' results are lost. The graph cannot continue.

The pattern:
```python
try:
    result = do_something()
except Exception as exc:
    failures.append({"node": "run_backtest", "symbol": symbol, "reason": str(exc)})
    return {"backtest_ids": [], "failures": failures}
```

Failures accumulate in `state["failures"]` and are visible in the final `inspect` command. A run that partially fails is better than a run that aborts.

---

### `ratchet_node` is a no-op at generation 0

**Rule:** `ratchet_node` checks `if generation == 0: return {}`.

**Why:**

At gen=0, there are no mutations and no parent/child pairs. `state["mutations"]` may not even exist yet. The ratchet compares gen=1 children to gen=0 parents — it requires both to have backtest results. Trying to run at gen=0 would find no pending mutations and do nothing anyway, but the guard makes this explicit and avoids unnecessary DB queries.

---

## 2. Architecture decisions

<!-- section:architecture -->

### Node factory pattern — closures over `deps`

All nodes are closures returned by factory functions:

```python
def make_ratchet_node(deps: PipelineDeps) -> Callable[[PipelineState], dict]:
    def ratchet_node(state: PipelineState) -> dict:
        ...
        thresholds = deps.ratchet_thresholds   # ← captured from outer scope
        ...
    return ratchet_node
```

**Why not classes or globals?**

- **Testability:** Tests create `PipelineDeps` with synthetic providers, mock LLM routers, in-memory SQLite. The node closure is unchanged — tests inject through `deps`, not through mocking globals.
- **Purity:** Each node is a pure function of `(state, deps)`. The same state + same deps always produces the same output.
- **LangGraph compatibility:** LangGraph expects `Callable[[State], dict]`. Closures satisfy this without any class overhead.

---

### `deps.detectors` vs `state["detector_configs"]` — why two representations

`deps.detectors` is a tuple of live `PatternDetector` objects (class instances with `.detect()` methods).

`state["detector_configs"]` is a list of plain dicts (`DetectorConfig` TypedDicts) that serialize to JSON.

**Why both exist:**

LangGraph state must be JSON-serializable (for checkpointing). `PatternDetector` objects are not serializable. So the graph stores the config dict, and nodes call `build_detector_from_config(cfg)` to reconstruct a live detector when needed.

`deps.detectors` is only used once — in `load_universe` to seed `state["detector_configs"]` for gen=0. After that, all generations use configs from state (mutated by LLM proposals).

**Round-trip guarantee:**
```python
det = SmaCrossover(fast=10, slow=25)
cfg = _detector_to_config(det)
# → {"type": "sma_crossover", "fast": 10, "slow": 25}

reconstructed = build_detector_from_config(cfg)
# → SmaCrossover(fast=10, slow=25)
# same .detect() output, same .name, same .family
```

---

### LangGraph `Send` API vs manual parallelism (threading/asyncio)

**Why `Send`, not `concurrent.futures.ThreadPoolExecutor`?**

| | Send API | ThreadPoolExecutor |
|---|---|---|
| State merge | automatic via reducers | manual, error-prone |
| Checkpointing | LangGraph handles | would bypass graph |
| HITL interrupts (Phase 3) | compatible | not compatible |
| Error isolation | node-level | requires careful try/except wiring |
| Debugging | LangGraph traces | custom logging only |

The `Send` API is more lines of code upfront (dispatcher + worker factory) but buys correct reducer-based merging and full Phase 3 compatibility for free.

---

### SQLite over PostgreSQL

**Why SQLite?**

- Zero infrastructure — no server process, no Docker, no connection pooling
- WAL mode supports concurrent readers + one writer — sufficient for the fan-out pattern (26 workers briefly serialize on writes)
- JSON1 extension enables `json_extract()` queries on `params_json`
- FTS5 enables text search over strategy descriptions
- The entire DB is a single file — trivial to back up, ship, or inspect with `datasette`

At Phase 1-2 scale (thousands of rows), SQLite is faster than PostgreSQL for read-heavy queries because it avoids network round-trips.

**When this changes:** Phase 4, if running multiple pipeline instances in parallel (different run_ids). At that point, WAL still handles it unless write throughput becomes a bottleneck.

---

### Langfuse for observability

Every LLM call goes through `llm/tracing.py:trace_node` context manager, which creates a Langfuse span. This gives you:

- Which LLM provider was used (Gemini / Groq / OpenRouter)
- Latency per call
- Token usage
- Input prompt and output response
- Which node called it (`trace_name="param_delta_sma"` etc.)

**Why Langfuse over raw logging?**  
structlog gives you structured text logs, which are good for node-level events. Langfuse gives you an LLM-native trace UI where you can see multi-turn conversation context, compare runs, and catch regressions in response quality. They serve different purposes — both run simultaneously.

---

## 3. Error taxonomy and debugging

<!-- section:errors -->

### Failure types and where they accumulate

All failures flow into `state["failures"]` via reducer. See them with:
```bash
uv run python main.py inspect --run <run_id>
```

| Failure node | Common cause | Log key | Action |
|---|---|---|---|
| `fetch_data` | Provider rate limit or symbol not found | `fetch_data_failed` | Check `.env` API keys; try `--llm-priority groq` |
| `detect_patterns` | TA-Lib import error or bad OHLCV shape | `detect_patterns_failed` | Check `ta-lib` installation; verify OHLCV has OHLCV columns |
| `run_backtest` | Zero signals → vectorbt error | `backtest_failed` | Expected for rare patterns; not a bug |
| `run_backtest` | Parquet file missing | `backtest_read_failed` | Check `data/cache/signals/` exists and is writable |
| LLM parse | Malformed JSON from LLM | `param_delta_parse_failed` | Mutation silently dropped; reduce temperature or check provider |

---

### Diagnosing "no mutations proposed"

Symptom: gen=1 `detector_configs` falls back to gen=0 configs (all 13) because `current_gen_mutations` is empty.

Root causes:
1. **All LLM calls failed** — check Langfuse dashboard or grep logs for `param_delta_parse_failed`
2. **No eligible parents** — `get_top_strategies_for_generation` returned empty. Means all gen=0 backtests failed. Check `state["failures"]`.
3. **All parents are CDL type** — `ParamDeltaMutator` skips CDL configs. If your top-5 are all CDL patterns, `param_delta` produces nothing. `composition` still runs. Use `--mutators composition` alone in this case.

---

### Diagnosing "ratchet accepts nothing"

Symptom: All 5 experiments rows show `accepted=0`. `advance_generation` falls back to all proposed children anyway (evolution stays alive), but no child "won."

Root causes:
1. **Sharpe delta too small** — check `delta_sharpe` column in experiments. If consistently ~0.01-0.03, LLM is proposing timid mutations. The default threshold is 0.05. Lower it: `RATCHET_MIN_DELTA_SHARPE=0.02`
2. **Too few trades** — AND compositions are aggressive filters. `n_trades` can drop below 5. Use `RATCHET_MIN_N_TRADES=3` to relax.
3. **Per-symbol regression** — common with AND compositions that work on one symbol but filter too aggressively on another. Check `worst_symbol_regression` in the JSON composite_score.

---

### Diagnosing LLM JSON truncation

Symptom: Log shows `param_delta_parse_failed` with `json.JSONDecodeError: Unterminated string`.

This was a real bug (fixed May 2026). Root cause: Gemini 2.5 Flash uses thinking tokens that consume `maxOutputTokens` budget. With `max_tokens=256`, thinking consumed ~246 tokens, leaving 10 for actual output → JSON truncated mid-field.

**Fix already applied** (`evolution/mutators/param_delta.py`):
- `max_tokens=1024` in all `LlmRequest` calls
- `thinkingConfig: {thinkingBudget: 0}` in `GeminiProvider._build_body` — disables thinking entirely
- Prompt constrains `reasoning` to `"<one sentence>"` — keeps output compact

If you see truncation again, first check: did someone lower `max_tokens` back to a small value?

---

### Diagnosing "experiment rows missing after ratchet"

Symptom: `experiments` table has fewer rows than expected after a gen=1 ratchet run.

The ratchet skips a mutation pair if either `build_evaluation_result` returns `None`:

```python
if parent_er is None or child_er is None:
    continue   # ← no experiments row written
```

`build_evaluation_result` returns `None` when `backtest_runs` has no successful rows for `(strategy_id, run_id, generation)`. This means the child backtest either never ran or all runs failed.

Check: does `backtest_runs` have rows with `strategy_id={child_sid}` and `generation=1`? If not, `detect_patterns` or `run_backtest_one` failed for that child.

---

### Reading the structlog output

Key log events and what they mean:

```
backtest_ok symbol=RELIANCE strategy=SMA_CROSS_10_25 sharpe=0.82 generation=0
→ Backtest succeeded. Sharpe value is from BacktestResult.metrics["sharpe"].

backtest_failed symbol=TCS strategy=CDL_DOJI reason=n_trades=0
→ vectorbt ran but found zero trades. Not an error — pattern rare in this period.

mutate_strategies_start generation=0 n_parents=5
→ Top-5 parents retrieved from DB. Mutation LLM calls starting.

mutator_proposed mutator=param_delta n=3 generation=0
→ ParamDelta proposed 3 mutations (3 eligible parents: 2 SMA + 1 RSI).

ratchet_verdict accepted=True delta_sharpe=0.06 reason=accepted generation=1
→ Child passed all 5 gates. Will be written to experiments as accepted=1.

ratchet_verdict accepted=False delta_sharpe=0.03 reason=sharpe_delta=0.030<0.05 generation=1
→ Gate 1 failed. Sharpe improvement insufficient.
```

---

## 4. LLM robustness pipeline

<!-- section:llm -->

### The three-layer parse stack

Every LLM response goes through three layers before it is used:

```
Raw LLM text (may have fences, preamble, truncation)
         │
         ▼ Layer 1: _strip_fences()
         Removes ```json ... ``` markdown code fences.
         LLMs sometimes wrap JSON in fences despite the system prompt saying not to.
         │
         ▼ try json.loads()
         If succeeds → Layer 3 (Pydantic)
         If JSONDecodeError →
         │
         ▼ Layer 2: _brace_match()
         Scans for the outermost { ... } block.
         Handles cases where LLM prepended a sentence before the JSON.
         e.g. "Here is the JSON: {...}" → extracts "{...}"
         │
         ▼ try json.loads() on extracted block
         If succeeds → Layer 3
         If fails → log warning, return None (mutation silently dropped)
         │
         ▼ Layer 3: Pydantic model_validate()
         Validates types, ranges, and cross-field constraints.
         e.g. SmaParamsDelta: fast must be < slow; both in valid ranges.
         If fails → log warning, return None
```

**Why silent drops instead of raising?**

Mutations are best-effort. A failed LLM call for one parent should not abort the mutation node for all other parents. The evolution loop is statistical — one dropped proposal doesn't derail the run. Silent drops + structured logging means you can see the failure rate in Langfuse without crashing the pipeline.

---

### Pydantic constraints on LLM responses

```python
class SmaParamsDelta(BaseModel):
    fast: int = Field(ge=2, le=50)
    slow: int = Field(ge=10, le=200)
    reasoning: str

    @model_validator(mode="after")
    def fast_lt_slow(self) -> SmaParamsDelta:
        if self.fast >= self.slow:
            raise ValueError(f"fast ({self.fast}) must be < slow ({self.slow})")
        return self
```

**Why the cross-field validator?**

LLMs commonly make this mistake — especially when nudging parameters. If parent has `fast=10, slow=25` and LLM proposes `fast=15, slow=12`, vectorbt produces nonsense (negative position: buying when fast crosses above slow that is already below). The Pydantic validator catches this before any DB write.

---

### System prompt discipline

All prompts in `evolution/prompts.py` open with:

> "Reply ONLY with a valid JSON object — no markdown fences, no extra text."

This is the first line of defense. Layer 1 (`_strip_fences`) and Layer 2 (`_brace_match`) exist because some models comply inconsistently. The three-layer stack is defensive coding against models that partially follow instructions.

---

### Provider fallback chain

```
Request → llm/router.py:complete_with_fallback()
            │
            │  [if request.tools is set: filter to supports_tools=True providers only]
            │
            ├─ Try gemini (1500 RPD free, primary)
            │    └─ On error (rate limit, API down) →
            ├─ Try groq (burst, fast inference)
            │    └─ On error →
            ├─ Try openrouter (diversity, 20+ models)
            │    └─ On error →
            ├─ Try cerebras (fast inference, Llama 3.3 70B)
            │    └─ On error →
            ├─ Try nvidia (NIM free tier, OpenAI-compat)
            │    └─ On error →
            └─ Try ollama (local, unlimited, opt-in via --enable-ollama)
                 └─ On error → raise (all providers exhausted)
```

Priority order is configured via `--llm-priority` CLI flag or `settings.llm_provider_priority`. Default: `["gemini", "groq", "openrouter", "cerebras", "nvidia"]`. All providers are traced through Langfuse — you can see which provider served each request and its latency.

**Tool-calling filter:** When `LlmRequest.tools` is set (multi-turn agent calls), the router filters the chain to providers with `supports_tools=True` before attempting any. All five providers above implement `OpenAICompatProvider` (Groq, OpenRouter, Cerebras, NVIDIA) or native function-calling (Gemini) and expose `supports_tools=True`. A `LlmExhausted` is raised immediately if no tool-capable providers remain in the chain.

**Why not always use the cheapest provider?**

Gemini 2.5 Flash (primary) has the best instruction-following for structured JSON output on these prompts — tested empirically. Groq's models are faster but less consistent on the cross-field constraint (fast < slow). The priority order reflects observed quality, not just cost.

---

*Tags for update-docs skill: invariants, architecture, errors, llm*
