-- Migration 0004: add equity_json + signals_json to backtest_runs (Track C / R1)
-- These columns persist equity curve + signal markers at backtest time for the
-- dashboard API. NULL for rows written before this migration.

ALTER TABLE backtest_runs ADD COLUMN equity_json TEXT;
ALTER TABLE backtest_runs ADD COLUMN signals_json TEXT;

PRAGMA user_version = 4;
