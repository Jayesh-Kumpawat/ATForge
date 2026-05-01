-- 0002_phase2a.sql
-- Extends Phase 1 schema for Phase 2a evolution loop:
--   * generation tracking on pattern_signals + backtest_runs
--   * widens experiments table for parent/child genealogy + composite scoring

ALTER TABLE pattern_signals ADD COLUMN generation INTEGER NOT NULL DEFAULT 0;
ALTER TABLE backtest_runs   ADD COLUMN generation INTEGER NOT NULL DEFAULT 0;

ALTER TABLE experiments ADD COLUMN run_id              TEXT;
ALTER TABLE experiments ADD COLUMN generation          INTEGER NOT NULL DEFAULT 0;
ALTER TABLE experiments ADD COLUMN parent_strategy_id  INTEGER REFERENCES strategies(strategy_id);
ALTER TABLE experiments ADD COLUMN child_strategy_id   INTEGER REFERENCES strategies(strategy_id);
ALTER TABLE experiments ADD COLUMN composite_score     TEXT;
ALTER TABLE experiments ADD COLUMN mutator             TEXT;

CREATE INDEX IF NOT EXISTS idx_exp_run_gen     ON experiments(run_id, generation);
CREATE INDEX IF NOT EXISTS idx_bt_strategy_gen ON backtest_runs(strategy_id, generation);

PRAGMA user_version = 2;
