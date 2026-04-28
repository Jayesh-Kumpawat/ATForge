# ATForge — Project Context

## What we are building
 
An automated self-improving multi-agent trading strategy and research system for NSE Indian equities. Both a portfolio
project demonstrating frontier AI engineering AND eventually a real trading system.

The system:
1. Downloads historical daily price data for Nifty 50 stocks
2. Detects chart patterns in that data programmatically
3. Backtests how those patterns performed historically
4. Stores all results with full reasoning in a knowledge base
5. Uses LLMs to suggest improvements to pattern detection and parameters
6. Learns from its own history — queries past experiments to inform new ones
7. Presents ranked strategies with reasoning for human review and approval
8. Eventually executes approved trades via broker API (much later phase)

The human (me) understands everything the system does at all times.
The system is flexible for human-in-the-loop intervention at any point.

## Vision — what the final product looks like

A self-improving research assistant that runs overnight, tries hundreds of
strategy variations, learns what works in different market conditions, and
presents me with a ranked portfolio of strategies each morning — with full
reasoning, backtest proof, and a one-click approval flow before any trade
executes. Over weeks and months, the system builds institutional memory of
what has been tried, what worked, what failed, and why.

## Tool choices with reasoning

### NSE Historical Data: openchart (primary) + jugaad-data + yfinance
- openchart uses NSE's charting backend (not scraping) — more reliable
- jugaad-data as bhavcopy-based fallback, covers data from ~1995
- yfinance for split/dividend-adjusted prices (the only free source)
- All three are free. nsepy and nsetools are dead — do not use.

### Backtesting: vectorbt (open source 0.28.4)
- Free, MIT licensed, extremely fast (~1M simulations in ~20s)
- Best vectorized programmatic interface for hundreds of automated backtests
- OSS branch is in maintenance mode but API is frozen and stable
- Always pass freq="1D", always shift signals +1 bar for lookahead prevention
- backtesting.py as secondary for single-strategy deep dives with Bokeh plots

### Chart Pattern Detection: TA-Lib + pandas-ta-classic + custom code
- TA-Lib 0.6.x has ARM64 wheels — installs cleanly on Apple Silicon
- 61 candlestick CDL* patterns + standard indicators
- pandas-ta-classic (xgboosted fork, active) — NOT pandas-ta (supply chain risk)
- scipy.signal.find_peaks + ~200 LOC custom code for structural patterns
  (cup-and-handle, head-and-shoulders, double tops — no library covers these well)
- VLM chart analysis is anecdotal not benchmarked — use as secondary validator only

### Runtime LLMs: Gemini 2.5 Flash + Groq + OpenRouter (all free)
- CRITICAL: Claude Pro is the pair-programmer (interactive Claude Code sessions)
  It CANNOT be used programmatically for the automated loop (blocked April 4, 2026)
- Gemini 2.5 Flash: 1,500 RPD free — primary workhorse for strategy evolution
- Groq: fast inference for burst tasks
- OpenRouter: 20+ free models for diversity checks
- Local Ollama (Qwen2.5-Coder 14B) as unlimited free fallback for batch/overnight
- Combined free stack gives ~5,000 requests/day — enough for hundreds of generations

### Orchestration: LangGraph 1.1.x
- Start with minimal linear graph in Phase 1 (no parallelism yet)
- Add Send API fan-out, HITL interrupts, conditional routing in Phase 2
- Portfolio value: most sought-after agentic framework in 2026 job market
- Keep each node as a pure function taking TypedDict state — clean and testable

### Structured Storage: SQLite (WAL mode + JSON1 + FTS5)
- Handles 10K+ writes/sec — vastly more than needed
- Backtest results, strategy configs, experiment history all in one file
- FTS5 for text search over strategy descriptions and reasoning

### Vector Search: Qdrant Cloud (free tier)
- 1GB free, metadata filtering, clean Python SDK
- Stores strategy embeddings for "find similar strategies" queries
- Portfolio recognition — interviewers know Qdrant

### Observability: Langfuse Cloud (free Hobby tier)
- 50k observations/month free — plenty for Phase 1-2
- Purpose-built for LLM agent tracing (traces, spans, scores)
- Zero infrastructure — no Docker containers to manage
- Portfolio recognition — industry standard for LLM observability
- Can self-host later if needed

### Broker: Protocol pattern with free data sources
- DataProvider Protocol interface — swap brokers by writing a new adapter
- Phase 1: openchart/jugaad-data/yfinance behind the protocol (no broker needed)
- Phase 2+: Zerodha Kite Personal (free for orders) + Dhan API (free for data)
- SEBI static IP mandate applies for order placement from April 1, 2026

### Evolutionary Search: OpenEvolve + AutoResearch ratchet
- OpenEvolve (open source AlphaEvolve replica) for population + mutation engine
- Karpathy's AutoResearch ratchet for per-strategy acceptance criterion
  (try mutation → measure → commit if improved → revert if not)
- Island-based diversity management
- QuantEvolve-style feature-map grid as Phase 2 addition if diversity collapses

### Diversity (Phase 2+): pyribs
- Only add when/if simple evolution shows diversity collapse
- MAP-Elites grid over (holding period, max drawdown, strategy family)
- Custom LLM mutation emitter

## Constraints
- Python only
- Free tools only (already paying for Claude Pro, no more spend)
- NSE Nifty 50 universe, daily EOD data only for Phase 1
- Human approval required before any trade executes
- macOS with M-series chip (Apple Silicon)
- Has Zerodha Kite account (not Angel One)

## Build phases

### Phase 1 — Foundation
Data pipeline + pattern detection + backtesting + results storage + basic
LangGraph graph (linear chain). Goal: download Nifty 50 data, detect patterns,
backtest them, store results, show rankings.

### Phase 2 — Evolution
LLM-powered strategy mutation + OpenEvolve integration + AutoResearch ratchet +
knowledge base queries (Qdrant RAG) + parallel backtesting via LangGraph Send API.

### Phase 3 — HITL & Execution
Telegram/web approval flow + paper trading wrapper + Kite Personal integration + walk-forward validation gates + statistical significance testing.

### Phase 4 — Scale & Polish
Multi-strategy portfolio management + regime-aware strategy selection +
Langfuse custom dashboards + GitHub repo cleanup + technical writeup.
