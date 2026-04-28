"""ATForge Phase 1 — Streamlit dashboard.

Run with: uv run streamlit run dashboard.py
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from atforge.config import settings
from atforge.storage.db import connect, init_db
from atforge.storage.repo import top_rankings

st.set_page_config(page_title="ATForge", page_icon="📈", layout="wide")

# ── helpers ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_rankings(run_id: str | None = None, limit: int = 50) -> pd.DataFrame:
    if not settings.db_path.exists():
        return pd.DataFrame()
    with connect(settings.db_path) as conn:
        rows = top_rankings(conn, limit=limit, run_id=run_id or None)
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def load_runs() -> pd.DataFrame:
    if not settings.db_path.exists():
        return pd.DataFrame()
    with connect(settings.db_path) as conn:
        rows = conn.execute(
            "SELECT run_id, started_at, finished_at, status, notes FROM runs ORDER BY started_at DESC"
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


@st.cache_data(ttl=60)
def available_ohlcv() -> dict[str, Path]:
    """Return {symbol: latest_parquet_path} from CachedProvider cache."""
    cache_root = settings.cache_dir
    result: dict[str, Path] = {}
    for p in cache_root.rglob("*.parquet"):
        # CachedProvider key: cache_dir/{provider}/{symbol}/{interval}/{range}.parquet
        parts = p.parts
        try:
            symbol = parts[-3]  # symbol is 3 levels up from file
            if symbol.isupper() and len(symbol) <= 20:
                # keep latest file per symbol
                if symbol not in result or p.stat().st_mtime > result[symbol].stat().st_mtime:
                    result[symbol] = p
        except (IndexError, OSError):
            continue
    return result


@st.cache_data(ttl=60)
def available_signals() -> dict[str, list[Path]]:
    """Return {symbol: [signal_parquet_paths]} from pipeline signals cache."""
    sig_dir = settings.cache_dir / "signals"
    if not sig_dir.exists():
        return {}
    result: dict[str, list[Path]] = {}
    for p in sig_dir.glob("*.parquet"):
        # Filename: {symbol}_{strategy_name}_{run_id}.parquet
        symbol = p.stem.split("_")[0].upper()
        result.setdefault(symbol, []).append(p)
    return result


def parse_strategy_from_path(p: Path) -> str:
    """Extract strategy name from signal parquet filename."""
    # e.g. RELIANCE_CDLENGULFING_bullish_abc123.parquet
    stem = p.stem
    parts = stem.split("_")
    # strip last part (run_id, 12 chars hex)
    if len(parts) > 1 and len(parts[-1]) == 12:
        parts = parts[:-1]
    # strip first part (symbol)
    if len(parts) > 1:
        parts = parts[1:]
    return "_".join(parts)


def candlestick_fig(ohlcv: pd.DataFrame, symbol: str) -> go.Figure:
    fig = go.Figure(data=[go.Candlestick(
        x=ohlcv.index,
        open=ohlcv["open"],
        high=ohlcv["high"],
        low=ohlcv["low"],
        close=ohlcv["close"],
        name=symbol,
        increasing_line_color="#26a641",
        decreasing_line_color="#cf222e",
    )])
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        margin=dict(l=0, r=0, t=30, b=0),
        height=420,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#2d333b"),
        yaxis=dict(gridcolor="#2d333b"),
    )
    return fig


def overlay_signal(fig: go.Figure, ohlcv: pd.DataFrame, signal: pd.Series, label: str) -> None:
    hit_dates = signal[signal].index
    if len(hit_dates) == 0:
        return
    prices = ohlcv.loc[ohlcv.index.isin(hit_dates), "low"] * 0.99
    fig.add_trace(go.Scatter(
        x=prices.index,
        y=prices.values,
        mode="markers",
        marker=dict(symbol="triangle-up", size=10, color="#3fb950"),
        name=label,
    ))


# ── sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.title("📈 ATForge")
st.sidebar.caption("Phase 1 — Foundation")

db_ok = settings.db_path.exists()
st.sidebar.markdown(
    f"DB: {'✅' if db_ok else '❌ not found'} `{settings.db_path.name}`"
)

if not db_ok:
    st.warning(
        f"No database at `{settings.db_path}`. "
        "Run `uv run python main.py pipeline --symbols RELIANCE --lookback 1y` first."
    )
    st.stop()

tab_names = ["🏆 Rankings", "📊 OHLCV + Signals", "🔄 Run History", "🗄️ DB Stats"]
tabs = st.tabs(tab_names)

# ── tab 1: rankings ───────────────────────────────────────────────────────────

with tabs[0]:
    st.header("Top Backtest Rankings")

    runs_df = load_runs()
    run_filter = st.selectbox(
        "Filter by run",
        ["All runs"] + (runs_df["run_id"].tolist() if not runs_df.empty else []),
        format_func=lambda r: r if r == "All runs" else f"{r} ({runs_df.loc[runs_df['run_id']==r, 'started_at'].iloc[0][:10] if not runs_df.empty else ''})",
    )
    top_n = st.slider("Show top N", 5, 100, 30)

    selected_run = None if run_filter == "All runs" else run_filter
    df = load_rankings(run_id=selected_run, limit=top_n)

    if df.empty:
        st.info("No successful backtests found. Run the pipeline first.")
    else:
        # Format for display
        disp = df[["symbol", "strategy_name", "family", "n_trades", "sharpe", "sortino", "cagr", "win_rate", "max_drawdown", "total_return"]].copy()
        disp["sharpe"] = disp["sharpe"].apply(lambda x: f"{x:.2f}" if x is not None else "-")
        disp["sortino"] = disp["sortino"].apply(lambda x: f"{x:.2f}" if x is not None else "-")
        disp["cagr"] = disp["cagr"].apply(lambda x: f"{float(x):.1%}" if x is not None else "-")
        disp["win_rate"] = disp["win_rate"].apply(lambda x: f"{float(x):.1%}" if x is not None else "-")
        disp = disp.rename(columns={
            "strategy_name": "strategy", "n_trades": "trades",
            "win_rate": "win%", "total_return": "return", "max_drawdown": "max_dd"
        })
        st.dataframe(disp, use_container_width=True, hide_index=True)

        # Mini bar chart of top 10 by Sharpe
        chart_df = df.head(10).copy()
        chart_df["label"] = chart_df["symbol"] + " / " + chart_df["strategy_name"]
        fig = go.Figure(go.Bar(
            x=chart_df["label"],
            y=chart_df["sharpe"].astype(float),
            marker_color="#3fb950",
        ))
        fig.update_layout(
            title="Top 10 — Sharpe Ratio",
            xaxis_tickangle=-35,
            margin=dict(l=0, r=0, t=40, b=80),
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

# ── tab 2: OHLCV + signals ────────────────────────────────────────────────────

with tabs[1]:
    st.header("OHLCV Chart + Pattern Signals")

    ohlcv_map = available_ohlcv()
    sig_map = available_signals()

    if not ohlcv_map:
        st.info(
            "No OHLCV parquet files found in cache. "
            "Run `uv run python main.py pipeline --symbols RELIANCE --lookback 1y` first."
        )
    else:
        col1, col2 = st.columns([1, 3])
        with col1:
            symbol = st.selectbox("Symbol", sorted(ohlcv_map.keys()))

        ohlcv_path = ohlcv_map[symbol]
        try:
            ohlcv = pd.read_parquet(ohlcv_path)
            if not isinstance(ohlcv.index, pd.DatetimeIndex):
                ohlcv.index = pd.DatetimeIndex(ohlcv.index)
        except Exception as e:
            st.error(f"Failed to load OHLCV: {e}")
            st.stop()

        # Date range filter
        min_d = ohlcv.index.min().date()
        max_d = ohlcv.index.max().date()
        with col1:
            default_start = max(min_d, max_d.replace(year=max_d.year - 1))
            date_range = st.date_input(
                "Date range",
                value=(default_start, max_d),
                min_value=min_d,
                max_value=max_d,
            )

        if len(date_range) == 2:
            start_d, end_d = date_range
            ohlcv = ohlcv.loc[str(start_d):str(end_d)]

        if ohlcv.empty:
            st.warning("No data in selected date range.")
        else:
            # OHLCV stats
            with col1:
                last = ohlcv["close"].iloc[-1]
                first = ohlcv["close"].iloc[0]
                pct = (last - first) / first * 100
                st.metric("Last close", f"₹{last:,.2f}", f"{pct:+.1f}% period")
                st.metric("Rows", f"{len(ohlcv):,}")
                st.metric("Cache", ohlcv_path.parent.name)

            fig = candlestick_fig(ohlcv, symbol)

            # Overlay available signals for this symbol
            sig_paths = sig_map.get(symbol, [])
            if sig_paths:
                with col2:
                    strategy_labels = {parse_strategy_from_path(p): p for p in sig_paths}
                    selected_strats = st.multiselect(
                        "Overlay pattern signals",
                        sorted(strategy_labels.keys()),
                        default=sorted(strategy_labels.keys())[:2] if strategy_labels else [],
                    )

                for label in selected_strats:
                    try:
                        sig_df = pd.read_parquet(strategy_labels[label])
                        sig = sig_df["signal"].astype(bool)
                        if not isinstance(sig.index, pd.DatetimeIndex):
                            sig.index = pd.DatetimeIndex(sig.index)
                        sig = sig.loc[str(start_d):str(end_d)] if len(date_range) == 2 else sig
                        overlay_signal(fig, ohlcv, sig, label)
                        n_hits = int(sig.sum())
                        st.caption(f"▲ {label}: {n_hits} signals in range")
                    except Exception as e:
                        st.warning(f"Could not load signal {label}: {e}")

            st.plotly_chart(fig, use_container_width=True)

            # Volume bar chart
            vol_fig = go.Figure(go.Bar(
                x=ohlcv.index,
                y=ohlcv["volume"],
                marker_color="#388bfd",
                name="Volume",
            ))
            vol_fig.update_layout(
                height=150,
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                xaxis=dict(gridcolor="#2d333b"),
                yaxis=dict(gridcolor="#2d333b", tickformat=".2s"),
            )
            st.plotly_chart(vol_fig, use_container_width=True)

# ── tab 3: run history ────────────────────────────────────────────────────────

with tabs[2]:
    st.header("Pipeline Run History")

    runs_df = load_runs()
    if runs_df.empty:
        st.info("No runs yet.")
    else:
        for _, row in runs_df.iterrows():
            with connect(settings.db_path) as conn:
                counts = conn.execute(
                    "SELECT COUNT(*) total, SUM(success) ok FROM backtest_runs WHERE run_id=?",
                    (row["run_id"],)
                ).fetchone()
            total = counts["total"] or 0
            ok = counts["ok"] or 0

            status_icon = {"success": "✅", "running": "⏳", "partial": "⚠️", "failed": "❌"}.get(row["status"], "❓")
            with st.expander(f"{status_icon} `{row['run_id']}` — {row['started_at'][:16]}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Status", row["status"])
                c2.metric("Backtests", total)
                c3.metric("Successful", ok)
                if row["notes"]:
                    st.caption(row["notes"])
                if row["finished_at"]:
                    st.caption(f"Finished: {row['finished_at'][:16]}")

# ── tab 4: db stats ───────────────────────────────────────────────────────────

with tabs[3]:
    st.header("Database Stats")
    st.caption(f"`{settings.db_path}`")

    with connect(settings.db_path) as conn:
        tables = ["runs", "strategies", "pattern_signals", "backtest_runs", "experiments"]
        for t in tables:
            n = conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]  # noqa: S608
            st.metric(t, f"{n:,}")

        st.divider()
        st.subheader("Strategy breakdown")
        rows = conn.execute(
            "SELECT family, COUNT(*) n FROM strategies GROUP BY family ORDER BY n DESC"
        ).fetchall()
        if rows:
            st.dataframe(pd.DataFrame([dict(r) for r in rows]), hide_index=True)

        st.subheader("Backtest success rate by symbol")
        rows = conn.execute(
            """
            SELECT symbol,
                   COUNT(*) total,
                   SUM(success) ok,
                   ROUND(AVG(sharpe), 2) avg_sharpe
            FROM backtest_runs
            GROUP BY symbol
            ORDER BY avg_sharpe DESC NULLS LAST
            LIMIT 20
            """
        ).fetchall()
        if rows:
            st.dataframe(pd.DataFrame([dict(r) for r in rows]), hide_index=True)

    st.divider()
    st.subheader("Cache stats")
    cache_dir = settings.cache_dir
    if cache_dir.exists():
        pfiles = list(cache_dir.rglob("*.parquet"))
        total_mb = sum(p.stat().st_size for p in pfiles) / 1e6
        st.metric("Parquet files", len(pfiles))
        st.metric("Cache size", f"{total_mb:.1f} MB")
        st.caption(f"Location: `{cache_dir}`")
    else:
        st.info("Cache directory not created yet.")
