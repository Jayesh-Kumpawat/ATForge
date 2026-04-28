-- ATForge SQLite schema. WAL + JSON1 + FTS5 enabled via db.py.
-- Money-side values (Decimal) stored as TEXT; ratios as REAL.

CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,   -- ISO-8601
    finished_at     TEXT,
    universe_hash   TEXT,
    status          TEXT NOT NULL CHECK (status IN ('running','success','partial','failed')),
    notes           TEXT             -- free-form
);

CREATE TABLE IF NOT EXISTS strategies (
    strategy_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    family          TEXT NOT NULL,   -- 'candlestick' | 'indicator' | 'structural'
    params_json     TEXT NOT NULL,   -- JSON1
    description     TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE (name, params_json)
);

CREATE TABLE IF NOT EXISTS pattern_signals (
    signal_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    strategy_id     INTEGER NOT NULL REFERENCES strategies(strategy_id),
    symbol          TEXT NOT NULL,
    n_signals       INTEGER NOT NULL,
    first_date      TEXT,
    last_date       TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_run ON pattern_signals(run_id);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON pattern_signals(symbol);

CREATE TABLE IF NOT EXISTS backtest_runs (
    backtest_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    signal_id       INTEGER REFERENCES pattern_signals(signal_id),
    strategy_id     INTEGER NOT NULL REFERENCES strategies(strategy_id),
    symbol          TEXT NOT NULL,
    success         INTEGER NOT NULL CHECK (success IN (0,1)),
    reason          TEXT,
    n_trades        INTEGER NOT NULL DEFAULT 0,

    -- Money-side: TEXT storing str(Decimal)
    total_return    TEXT,
    final_value     TEXT,
    max_drawdown    TEXT,

    -- Ratios: REAL
    sharpe          REAL,
    sortino         REAL,
    cagr            REAL,
    win_rate        REAL,

    -- Config snapshot
    hold_bars       INTEGER,
    fees            REAL,
    slippage        REAL,
    init_cash       TEXT,

    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_backtest_run ON backtest_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_backtest_symbol ON backtest_runs(symbol);
CREATE INDEX IF NOT EXISTS idx_backtest_strategy ON backtest_runs(strategy_id);
CREATE INDEX IF NOT EXISTS idx_backtest_sharpe ON backtest_runs(sharpe DESC)
    WHERE success = 1;

-- Phase 2 experiment log; included now so schema is stable.
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id       INTEGER REFERENCES experiments(experiment_id),
    strategy_id     INTEGER REFERENCES strategies(strategy_id),
    mutation_json   TEXT,             -- proposed delta
    accepted        INTEGER CHECK (accepted IN (0,1)),
    delta_sharpe    REAL,
    reasoning       TEXT,
    created_at      TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS strategy_search USING fts5(
    name,
    description,
    reasoning,
    content=''
);
