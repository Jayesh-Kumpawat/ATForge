// Hand-written from FastAPI Pydantic schemas in src/atforge/api/schemas/

export interface components {
  schemas: {
    // common
    ErrorDetail: {
      code: string;
      message: string;
      details: Record<string, unknown> | null;
    };
    ErrorResponse: {
      error: components["schemas"]["ErrorDetail"];
    };
    HealthResponse: {
      status: string;
      db: string;
    };
    // runs
    RunSummary: {
      run_id: string;
      started_at: string | null;
      finished_at: string | null;
      status: "running" | "done" | "failed" | "unknown";
      n_symbols: number | null;
      max_generations: number | null;
      current_generation: number | null;
      n_backtests: number;
      n_failures: number;
    };
    RunListResponse: {
      runs: components["schemas"]["RunSummary"][];
      total: number;
      limit: number;
      offset: number;
    };
    EventEnvelope: {
      event_id: number;
      run_id: string;
      ts_ms: number;
      event_type: string;
      generation: number | null;
      payload: Record<string, unknown>;
    };
    // strategies
    MetricsSummary: {
      best_sharpe: number | null;
      best_sortino: number | null;
      avg_win_rate: number | null;
      max_drawdown: number | null;
      n_backtests: number;
    };
    StrategyListItem: {
      strategy_id: number;
      name: string;
      family: string;
      generation: number;
      parent_strategy_id: number | null;
      best_sharpe: number | null;
      best_sortino: number | null;
      avg_win_rate: number | null;
      n_backtests: number;
    };
    StrategyListResponse: {
      strategies: components["schemas"]["StrategyListItem"][];
      total: number;
      page: number;
      page_size: number;
    };
    StrategyDetail: {
      strategy_id: number;
      name: string;
      family: string;
      params: Record<string, unknown>;
      description: string | null;
      parent_strategy_id: number | null;
      created_at: string | null;
      metrics_summary: components["schemas"]["MetricsSummary"];
    };
    BacktestRow: {
      run_id: string;
      symbol: string;
      generation: number;
      n_trades: number;
      sharpe: number | null;
      sortino: number | null;
      win_rate: number | null;
      max_drawdown: number | null;
      cagr: number | null;
    };
    BacktestListResponse: {
      strategy_id: number;
      backtests: components["schemas"]["BacktestRow"][];
    };
    LineageNode: {
      strategy_id: number;
      name: string;
      generation: number;
      mutator: string | null;
      accepted: boolean | null;
      sharpe: number | null;
    };
    LineageResponse: {
      strategy_id: number;
      ancestors: components["schemas"]["LineageNode"][];
      descendants: components["schemas"]["LineageNode"][];
    };
    ReasoningEntry: {
      run_id: string;
      generation: number;
      mutator: string;
      parent_strategy_id: number | null;
      reasoning: string;
      accepted: boolean;
      delta_sharpe: number | null;
    };
    ReasoningResponse: {
      strategy_id: number;
      entries: components["schemas"]["ReasoningEntry"][];
    };
    EquityPoint: {
      t: number;
      equity: number;
      drawdown: number;
    };
    EquityResponse: {
      strategy_id: number;
      symbol: string;
      run_id: string;
      initial_capital: number;
      points: components["schemas"]["EquityPoint"][];
    };
    OHLCVBar: {
      t: number;
      o: number;
      h: number;
      l: number;
      c: number;
      v: number;
    };
    SignalMarker: {
      t: number;
      type: "entry" | "exit";
      price: number;
    };
    SignalsResponse: {
      strategy_id: number;
      symbol: string;
      run_id: string;
      bars: components["schemas"]["OHLCVBar"][];
      signals: components["schemas"]["SignalMarker"][];
    };
    // stats
    FamilyCount: { family: string; count: number };
    StatsResponse: {
      n_runs: number;
      n_strategies: number;
      n_backtests: number;
      n_experiments: number;
      best_sharpe: number | null;
      families: components["schemas"]["FamilyCount"][];
    };
    // rankings / evolution / timeline
    RankingRow: {
      backtest_id: number;
      symbol: string;
      strategy_id: number;
      strategy_name: string;
      family: string;
      generation: number;
      n_trades: number;
      sharpe: number | null;
      sortino: number | null;
      cagr: number | null;
      win_rate: number | null;
      max_drawdown: string | null;
      total_return: string | null;
    };
    RunRankingsResponse: {
      run_id: string;
      rankings: components["schemas"]["RankingRow"][];
    };
    ExperimentRow: {
      experiment_id: number;
      generation: number;
      mutator: string | null;
      accepted: number | null;
      delta_sharpe: number | null;
      reasoning: string | null;
      composite_score: string | null;
      mutation_json: string | null;
      created_at: string | null;
      parent_name: string | null;
      child_name: string | null;
      parent_strategy_id: number | null;
      child_strategy_id: number | null;
    };
    GenerationSharpe: {
      generation: number;
      best_sharpe: number | null;
      n_backtests: number;
    };
    RunEvolutionResponse: {
      run_id: string;
      experiments: components["schemas"]["ExperimentRow"][];
      sharpe_progression: components["schemas"]["GenerationSharpe"][];
    };
    TimelineResponse: {
      run_id: string;
      events: components["schemas"]["EventEnvelope"][];
    };
  };
}
