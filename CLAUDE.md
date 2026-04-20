# ATForge — Agentic Trading Forge

Self-improving multi-agent trading strategy tournament for NSE/BSE Indian equities.

## Language and tools
- Python 3.12 only. No other languages.
- Always use `uv run` to execute Python. Never use bare `python` or `pip`.
- Add dependencies with `uv add`. Never use `pip install`.
- Run tests with `uv run pytest`.

## What not to do
- NEVER commit .env or any file containing API keys or secrets.
- NEVER use float for financial values. Use decimal.Decimal.
- NEVER put large data (DataFrames, OHLCV arrays) into LangGraph GraphState.

## Stack
- LangGraph 1.1.x for orchestration
- pyribs for MAP-Elites quality-diversity optimization
- VectorBT for backtesting
- jugaad-data + yfinance for NSE historical data
- Angel One SmartAPI for live data and execution
- Pydantic v2 for all data models
- Langfuse v3 for observability
- Gemini 2.0 Flash (free) as primary runtime LLM
- Groq Llama 3.3 as secondary runtime LLM

## Market constraints
- NSE only, fty 50 universe, daily EOD timeframe
- No intraday strategies
- SEBI static IP mandate applies for SmartAPI orders (April 1, 2026)
