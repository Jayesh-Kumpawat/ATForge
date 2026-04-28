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
from atforge.graph.deps import PipelineDeps
from atforge.graph.pipeline import build_pipeline
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
) -> None:
    """Run the full Phase 1 pipeline end-to-end."""
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
    init_db(settings.db_path)

    deps = PipelineDeps(
        data_provider=_build_default_provider(),
        detectors=_default_detectors(),
        ohlcv_cache_dir=settings.cache_dir / "ohlcv",
        signal_cache_dir=settings.cache_dir / "signals",
        db_path=settings.db_path,
        init_cash=Decimal("100000"),
    )
    graph = build_pipeline(deps)
    run_id = uuid4().hex[:12]

    console.print(f"[green]run[/] {run_id} symbols={len(syms)} window={start}..{end}")
    result = graph.invoke(
        {
            "run_id": run_id,
            "universe": syms,
            "start_iso": start.isoformat(),
            "end_iso": end.isoformat(),
        }
    )
    console.print(
        f"[green]done[/] run={run_id} backtests={len(result.get('backtest_ids', []))} "
        f"failures={len(result.get('failures', []))}"
    )
    _print_rankings(settings.db_path, run_id=run_id, limit=20)


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
