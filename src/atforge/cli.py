from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from rich.console import Console
from rich.table import Table

from atforge.config import settings
from atforge.data.cache import CachedProvider
from atforge.data.chain import FallbackDataProvider
from atforge.data.protocol import DataProvider
from atforge.data.providers.jugaad import JugaadProvider
from atforge.data.providers.openchart import OpenchartProvider
from atforge.data.providers.yfinance import YFinanceProvider
from atforge.evolution.types import RatchetThresholds
from atforge.graph.deps import PipelineDeps
from atforge.graph.events import EventBus, EvtPipelineDone, EvtPipelineStart
from atforge.graph.pipeline import build_pipeline
from atforge.graph.role_config import load_role_configs
from atforge.llm.registry import build_default_registry
from atforge.llm.router import complete_with_fallback
from atforge.llm.types import LlmRequest
from atforge.monitor import PipelineMonitor
from atforge.patterns.pandas_ta import RsiOversoldReclaim, SmaCrossover
from atforge.patterns.talib_cdl import CDL_PATTERNS, TalibCdlDetector
from atforge.storage.db import connect, init_db
from atforge.storage.repo import top_rankings

app = typer.Typer(add_completion=False, no_args_is_help=True, help="ATForge CLI")
console = Console()


def _build_default_provider() -> DataProvider:
    settings.ensure_dirs()
    providers: list[DataProvider] = []
    # Openchart can fail to initialize if NSE symbol list download breaks; try in order.
    for ctor in (OpenchartProvider, JugaadProvider, YFinanceProvider):
        try:
            providers.append(ctor())
        except Exception as exc:
            console.print(f"[yellow]warn[/] skipping {ctor.__name__}: {exc}")
    if not providers:
        raise RuntimeError("no data providers could be initialized")
    return CachedProvider(FallbackDataProvider(providers), settings.cache_dir)


def _default_detectors() -> tuple:
    cdl_dets = tuple(TalibCdlDetector(p) for p in CDL_PATTERNS)
    return (
        *cdl_dets,
        SmaCrossover(fast=20, slow=50),
        SmaCrossover(fast=10, slow=30),
        RsiOversoldReclaim(period=14, oversold=30),
    )


@app.command()
def pipeline(
    universe: Annotated[str, typer.Option(help="Universe name, e.g. 'nifty50'")] = "nifty50",
    lookback: Annotated[str, typer.Option(help="Lookback, e.g. '10y', '5y', '1y'")] = "10y",
    symbols: Annotated[
        str | None,
        typer.Option(help="Comma-separated symbols override (skips universe)"),
    ] = None,
    max_generations: Annotated[
        int, typer.Option(help="Max evolution generations (1=initial run only, no loop)")
    ] = 1,
    mutators: Annotated[
        str, typer.Option(help="Comma-separated mutator names: param_delta,composition")
    ] = "param_delta,composition",
    top_n_parents: Annotated[
        int, typer.Option(help="Top-N strategies to use as parents for mutation")
    ] = 5,
    llm_priority: Annotated[
        str, typer.Option(help="Comma-separated LLM provider priority")
    ] = "gemini,groq,openrouter",
    enable_ollama: Annotated[bool, typer.Option(help="Enable local Ollama provider")] = False,
    dry_run: Annotated[
        bool, typer.Option(help="Skip experiment DB writes (ratchet logs only)")
    ] = False,
    live: Annotated[bool, typer.Option(help="Show Rich live monitor during pipeline run")] = False,
) -> None:
    """Run the full Phase 2a pipeline end-to-end with optional LLM evolution."""
    from atforge.data.universe import load_nifty50

    end = date.today()
    start = _apply_lookback(end, lookback)

    if symbols:
        syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    elif universe == "nifty50":
        syms = load_nifty50()
    else:
        raise typer.BadParameter(f"unknown universe {universe!r}")

    settings.ensure_dirs()
    _configure_langfuse_env()
    init_db(settings.db_path)

    priority = [p.strip() for p in llm_priority.split(",") if p.strip()]
    mutator_list, llm_router = _build_mutators(
        mutator_names=[m.strip() for m in mutators.split(",") if m.strip()],
        llm_priority=priority,
        enable_ollama=enable_ollama,
    )

    effective_max_gen = 1 if dry_run else max_generations
    tracing_enabled = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
    bus = EventBus() if live else None

    role_configs = load_role_configs()  # auto-discovers atforge.yaml in cwd

    deps = PipelineDeps(
        data_provider=_build_default_provider(),
        detectors=_default_detectors(),
        ohlcv_cache_dir=settings.cache_dir / "ohlcv",
        signal_cache_dir=settings.cache_dir / "signals",
        db_path=settings.db_path,
        init_cash=Decimal("100000"),
        mutators=tuple(mutator_list),
        top_n_parents=top_n_parents,
        ratchet_thresholds=RatchetThresholds(
            min_delta_sharpe=settings.ratchet_min_delta_sharpe,
            min_delta_sortino=settings.ratchet_min_delta_sortino,
            max_drawdown_tol=settings.ratchet_max_drawdown_tol,
            min_n_trades=settings.ratchet_min_n_trades,
            max_symbol_regression=settings.ratchet_max_symbol_regression,
        ),
        tracing_enabled=tracing_enabled,
        event_bus=bus,
        llm_router=llm_router,
        role_configs=role_configs,
    )
    graph = build_pipeline(deps)
    run_id = uuid4().hex[:12]

    monitor: PipelineMonitor | None = None
    if bus is not None:
        bus.emit(
            EvtPipelineStart(run_id=run_id, n_symbols=len(syms), max_generations=effective_max_gen)
        )
        monitor = PipelineMonitor(bus, run_id=run_id, max_generations=effective_max_gen)
        monitor.start()
    else:
        console.print(
            f"[green]run[/] {run_id} symbols={len(syms)} window={start}..{end} "
            f"max_gen={effective_max_gen} mutators={mutators}"
        )

    result = graph.invoke(
        {
            "run_id": run_id,
            "universe": syms,
            "start_iso": start.isoformat(),
            "end_iso": end.isoformat(),
            "max_generations": effective_max_gen,
        }
    )

    n_backtests = len(result.get("backtest_ids", []))
    n_failures = len(result.get("failures", []))

    if bus is not None:
        bus.emit(EvtPipelineDone(run_id=run_id, n_backtests=n_backtests, n_failures=n_failures))
    if monitor is not None:
        monitor.stop()

    if bus is None:
        console.print(f"[green]done[/] run={run_id} backtests={n_backtests} failures={n_failures}")

    _print_rankings(settings.db_path, run_id=run_id, limit=20)


@app.command()
def experiments(
    run: Annotated[str, typer.Option(help="run_id to inspect")] = "",
    limit: Annotated[int, typer.Option(help="Max rows to show")] = 20,
) -> None:
    """Show experiment log (LLM mutations + ratchet verdicts) for a run."""
    with connect(settings.db_path) as conn:
        where = "WHERE run_id=?" if run else ""
        params = (run, limit) if run else (limit,)
        rows = conn.execute(
            f"""
            SELECT e.experiment_id, e.generation, e.mutator, e.accepted, e.delta_sharpe,
                   s_parent.name AS parent_name, s_child.name AS child_name, e.reasoning
            FROM experiments e
            LEFT JOIN strategies s_parent ON s_parent.strategy_id = e.parent_strategy_id
            LEFT JOIN strategies s_child ON s_child.strategy_id = e.child_strategy_id
            {where}
            ORDER BY e.created_at DESC LIMIT ?
            """,
            params,
        ).fetchall()

    if not rows:
        console.print("[yellow]no experiments found[/]")
        return

    table = Table(title="Experiments")
    for col in ["id", "gen", "mutator", "accepted", "Δsharpe", "parent", "child", "reason"]:
        table.add_column(col)
    for r in rows:
        table.add_row(
            str(r["experiment_id"]),
            str(r["generation"]),
            r["mutator"] or "-",
            "✓" if r["accepted"] == 1 else ("✗" if r["accepted"] == 0 else "?"),
            f"{r['delta_sharpe']:.3f}" if r["delta_sharpe"] is not None else "-",
            r["parent_name"] or "-",
            r["child_name"] or "-",
            (r["reasoning"] or "")[:40],
        )
    console.print(table)


@app.command()
def rank(
    top: Annotated[int, typer.Option(help="How many rows to show")] = 20,
    run: Annotated[str | None, typer.Option(help="Filter to a specific run_id")] = None,
) -> None:
    """Show top-ranked backtests from the DB."""
    _print_rankings(settings.db_path, run_id=run, limit=top)


@app.command()
def inspect(run_id: str) -> None:
    """Print run metadata + failure summary for a given run_id."""
    with connect(settings.db_path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            console.print(f"[red]no run {run_id}[/]")
            raise typer.Exit(code=1)
        n_bts = conn.execute(
            "SELECT COUNT(*) c, SUM(success) s FROM backtest_runs WHERE run_id=?", (run_id,)
        ).fetchone()
    console.print(dict(row))
    console.print(f"backtests={n_bts['c']} successful={n_bts['s'] or 0}")


def _print_rankings(db_path: Path, *, run_id: str | None, limit: int) -> None:
    with connect(db_path) as conn:
        rows = top_rankings(conn, limit=limit, run_id=run_id)

    if not rows:
        console.print("[yellow]no successful backtests yet[/]")
        return

    table = Table(title=f"Top {len(rows)} backtests" + (f" (run {run_id})" if run_id else ""))
    for col in ["symbol", "strategy", "trades", "sharpe", "cagr", "max_dd", "win_rate"]:
        table.add_column(col)

    for r in rows:
        table.add_row(
            r["symbol"],
            r["strategy_name"],
            str(r["n_trades"]),
            f"{r['sharpe']:.2f}" if r["sharpe"] is not None else "-",
            f"{r['cagr']:.2%}" if r["cagr"] is not None else "-",
            (r["max_drawdown"] or "-"),
            f"{r['win_rate']:.1%}" if r["win_rate"] is not None else "-",
        )
    console.print(table)


def _build_mutators(
    mutator_names: list[str],
    llm_priority: list[str],
    enable_ollama: bool,
) -> tuple[list, object]:
    """Build mutator instances. Returns (mutators, llm_router | None)."""

    eff_settings = settings.model_copy(update={"enable_ollama": enable_ollama})
    registry = build_default_registry(eff_settings)
    priority = llm_priority + (["ollama"] if enable_ollama else [])
    chain = registry.chain(priority)

    if not chain:
        console.print(
            "[yellow]warn[/] no LLM providers configured — skipping mutators (set API keys in .env)"
        )
        return [], None

    tracing_enabled = bool(settings.langfuse_public_key and settings.langfuse_secret_key)

    def llm_router(req: LlmRequest):
        return complete_with_fallback(
            req, registry=registry, priority=priority, tracing_enabled=tracing_enabled
        )

    mutators = []
    from atforge.evolution.mutators.composition import CompositionMutator
    from atforge.evolution.mutators.param_delta import ParamDeltaMutator

    for name in mutator_names:
        if name == "param_delta":
            mutators.append(ParamDeltaMutator(llm_router))
        elif name == "composition":
            mutators.append(CompositionMutator(llm_router))
        elif name == "research":
            from atforge.evolution.mutators.research_agent import ResearchAgentMutator

            mutators.append(ResearchAgentMutator(llm_router, db_path=settings.db_path))
        else:
            console.print(f"[yellow]warn[/] unknown mutator {name!r} — skipping")

    return mutators, llm_router


def _configure_langfuse_env() -> None:
    """Push Langfuse keys from pydantic-settings into os.environ.

    pydantic-settings reads .env into the settings object but does NOT write to
    os.environ. Langfuse's get_client() reads os.environ directly, so without
    this the tracing client initializes disabled even when keys are set in .env.
    """
    import os

    if settings.langfuse_public_key:
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    if settings.langfuse_secret_key:
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)


def _apply_lookback(end: date, lookback: str) -> date:
    lookback = lookback.strip().lower()
    if lookback.endswith("y"):
        years = int(lookback[:-1])
        return end.replace(year=end.year - years)
    if lookback.endswith("m"):
        months = int(lookback[:-1])
        year = end.year + (end.month - months - 1) // 12
        month = (end.month - months - 1) % 12 + 1
        return end.replace(year=year, month=month, day=min(end.day, 28))
    if lookback.endswith("d"):
        days = int(lookback[:-1])
        return end - timedelta(days=days)
    raise typer.BadParameter(f"lookback must end in y/m/d, got {lookback!r}")


if __name__ == "__main__":
    app()
