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
import json

from atforge.storage.repo import (
    get_best_sharpe_per_generation,
    get_experiments_for_run,
    top_rankings,
)

st.set_page_config(page_title="ATForge", page_icon="📈", layout="wide")

_SIGNAL_FILL = [
    "rgba(63,185,80,0.15)",
    "rgba(56,139,253,0.15)",
    "rgba(210,153,34,0.15)",
    "rgba(188,77,212,0.15)",
    "rgba(248,81,73,0.15)",
]
_SIGNAL_MARKER = ["#3fb950", "#388bfd", "#d2991a", "#bc4dd4", "#f85149"]

_HOLD_BARS = 10

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


@st.cache_data(ttl=30)
def load_experiments(run_id: str) -> pd.DataFrame:
    if not settings.db_path.exists():
        return pd.DataFrame()
    with connect(settings.db_path) as conn:
        rows = get_experiments_for_run(conn, run_id)
    return pd.DataFrame(rows)


@st.cache_data(ttl=30)
def load_sharpe_progression(run_id: str) -> pd.DataFrame:
    if not settings.db_path.exists():
        return pd.DataFrame()
    with connect(settings.db_path) as conn:
        rows = get_best_sharpe_per_generation(conn, run_id)
    return pd.DataFrame(rows)


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


def _short_label(label: str) -> str:
    """CDLENGULFING_bullish -> ENG  |  SMA_20_50 -> SMA  |  RSI_reclaim -> RSI"""
    clean = label.replace("CDL", "").upper()
    return clean[:4].rstrip("_")


def overlay_signal(
    fig: go.Figure,
    ohlcv: pd.DataFrame,
    signal: pd.Series,
    label: str,
    fill_color: str,
    marker_color: str,
    show_hold_window: bool = False,
    show_labels: bool = True,
) -> int:
    hit_dates = signal[signal].index
    if len(hit_dates) == 0:
        return 0

    # Triangle markers below each signal candle
    prices = ohlcv.loc[ohlcv.index.isin(hit_dates), "low"] * 0.985
    fig.add_trace(go.Scatter(
        x=prices.index,
        y=prices.values,
        mode="markers",
        marker=dict(symbol="triangle-up", size=11, color=marker_color),
        name=label,
    ))

    idx = ohlcv.index
    for d in hit_dates:
        if d not in idx:
            continue
        pos = idx.get_loc(d)

        # Highlight signal candle
        fig.add_vrect(
            x0=d, x1=d + pd.Timedelta(days=1),
            fillcolor=fill_color, opacity=1.0, line_width=0,
            layer="below",
        )

        # Optional: shade the simulated hold window (T+1 to T+hold_bars)
        if show_hold_window:
            end_pos = min(pos + _HOLD_BARS, len(idx) - 1)
            end_d = idx[end_pos]
            fig.add_vrect(
                x0=d + pd.Timedelta(days=1), x1=end_d + pd.Timedelta(days=1),
                fillcolor=fill_color, opacity=0.5, line_width=0,
                layer="below",
            )

        # Optional: annotation label above candle
        if show_labels:
            high = ohlcv.loc[d, "high"] if d in ohlcv.index else prices.get(d, 0)
            fig.add_annotation(
                x=d, y=high,
                text=_short_label(label),
                showarrow=True, arrowhead=2, arrowcolor=marker_color,
                ax=0, ay=-28,
                font=dict(size=9, color=marker_color),
                bgcolor="rgba(0,0,0,0.5)",
                borderpad=2,
            )

    return len(hit_dates)


# ── sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.title("📈 ATForge")
st.sidebar.caption("Phase 2a — Evolution Loop")

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

tab_names = ["🏆 Rankings", "📊 OHLCV + Signals", "🔄 Run History", "🗄️ DB Stats", "🧬 Evolution"]
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
        disp = df[["symbol", "generation", "strategy_name", "family", "n_trades", "sharpe", "sortino", "cagr", "win_rate", "max_drawdown", "total_return"]].copy()
        disp["sharpe"] = disp["sharpe"].apply(lambda x: f"{x:.2f}" if x is not None else "-")
        disp["sortino"] = disp["sortino"].apply(lambda x: f"{x:.2f}" if x is not None else "-")
        disp["cagr"] = disp["cagr"].apply(lambda x: f"{float(x):.1%}" if x is not None else "-")
        disp["win_rate"] = disp["win_rate"].apply(lambda x: f"{float(x):.1%}" if x is not None else "-")
        disp = disp.rename(columns={
            "strategy_name": "strategy", "n_trades": "trades", "generation": "gen",
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
            # OHLCV stats + display options
            with col1:
                last = ohlcv["close"].iloc[-1]
                first = ohlcv["close"].iloc[0]
                pct = (last - first) / first * 100
                st.metric("Last close", f"₹{last:,.2f}", f"{pct:+.1f}% period")
                st.metric("Rows", f"{len(ohlcv):,}")
                st.metric("Cache", ohlcv_path.parent.name)
                st.divider()
                show_hold = st.checkbox(f"Show hold window ({_HOLD_BARS} bars)", value=False)
                show_labels = st.checkbox("Show pattern labels", value=True)

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

                total_signals = 0
                for i, label in enumerate(selected_strats):
                    fill_color = _SIGNAL_FILL[i % len(_SIGNAL_FILL)]
                    marker_color = _SIGNAL_MARKER[i % len(_SIGNAL_MARKER)]
                    try:
                        sig_df = pd.read_parquet(strategy_labels[label])
                        sig = sig_df["signal"].astype(bool)
                        if not isinstance(sig.index, pd.DatetimeIndex):
                            sig.index = pd.DatetimeIndex(sig.index)
                        sig = sig.loc[str(start_d):str(end_d)] if len(date_range) == 2 else sig
                        # suppress labels if too many signals (visual clutter)
                        n_hits = overlay_signal(
                            fig, ohlcv, sig, label,
                            fill_color, marker_color,
                            show_hold_window=show_hold,
                            show_labels=show_labels and (total_signals + int(sig.sum()) <= 30),
                        )
                        total_signals += n_hits
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

# ── tab 5: evolution ──────────────────────────────────────────────────────────

with tabs[4]:
    st.header("Evolution & Ratchet Verdicts")

    runs_df_evo = load_runs()
    if runs_df_evo.empty:
        st.info("No runs found. Run the pipeline first.")
    else:
        evo_run = st.selectbox(
            "Select run",
            runs_df_evo["run_id"].tolist(),
            format_func=lambda r: f"{r} ({runs_df_evo.loc[runs_df_evo['run_id']==r, 'started_at'].iloc[0][:16]})",
            key="evo_run_select",
        )

        exp_df = load_experiments(evo_run)
        prog_df = load_sharpe_progression(evo_run)

        if exp_df.empty:
            st.info(
                "No evolution data for this run — it was a single-pass baseline run "
                "(max_generations=1). Run with `--max-generations 2+` to see mutations."
            )
        else:
            n_accepted = int(exp_df["accepted"].sum())
            n_rejected = len(exp_df) - n_accepted

            # ── top metrics ──
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total mutations", len(exp_df))
            m2.metric("Accepted ✓", n_accepted)
            m3.metric("Rejected ✗", n_rejected)
            best_delta = exp_df["delta_sharpe"].max()
            m4.metric("Best Δsharpe", f"{best_delta:+.3f}" if best_delta is not None else "-")

            st.divider()

            # ── charts row ──
            c_left, c_right = st.columns([3, 2])

            with c_left:
                if not prog_df.empty:
                    bar_fig = go.Figure(go.Bar(
                        x=[f"Gen {g}" for g in prog_df["generation"]],
                        y=prog_df["best_sharpe"].astype(float),
                        marker_color="#3fb950",
                        text=prog_df["best_sharpe"].apply(lambda v: f"{float(v):.2f}"),
                        textposition="outside",
                    ))
                    bar_fig.update_layout(
                        title="Best Sharpe per Generation",
                        yaxis_title="Sharpe",
                        margin=dict(l=0, r=0, t=40, b=0),
                        height=300,
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        yaxis=dict(gridcolor="#2d333b"),
                    )
                    st.plotly_chart(bar_fig, use_container_width=True)

            with c_right:
                pie_fig = go.Figure(go.Pie(
                    labels=["Accepted", "Rejected"],
                    values=[n_accepted, n_rejected],
                    marker_colors=["#3fb950", "#f85149"],
                    hole=0.4,
                    textinfo="label+percent",
                ))
                pie_fig.update_layout(
                    title="Ratchet Verdicts",
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=300,
                    paper_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                )
                st.plotly_chart(pie_fig, use_container_width=True)

            st.divider()

            # ── generation filter ──
            gens = sorted(exp_df["generation"].unique().tolist())
            gen_options = ["All"] + [str(g) for g in gens]
            gen_filter = st.selectbox("Filter by generation", gen_options, key="evo_gen_filter")
            filtered = exp_df if gen_filter == "All" else exp_df[exp_df["generation"] == int(gen_filter)]

            # ── mutations table ──
            st.subheader("Mutation Log")
            tbl = filtered[[
                "generation", "mutator", "parent_name", "child_name",
                "delta_sharpe", "accepted", "reasoning", "composite_score",
            ]].copy()

            tbl["accepted"] = tbl["accepted"].apply(lambda v: "✓" if v else "✗")
            tbl["delta_sharpe"] = tbl["delta_sharpe"].apply(
                lambda v: f"{float(v):+.3f}" if v is not None else "-"
            )
            tbl["reasoning"] = tbl["reasoning"].apply(
                lambda v: (v[:90] + "…") if v and len(v) > 90 else (v or "-")
            )

            def _fmt_score(raw: str | None) -> str:
                if not raw:
                    return "-"
                try:
                    d = json.loads(raw)
                    parts = [f"Δsh={d.get('delta_sharpe', '?'):.2f}" if isinstance(d.get('delta_sharpe'), float) else "",
                             f"Δso={d.get('delta_sortino', '?'):.2f}" if isinstance(d.get('delta_sortino'), float) else "",
                             f"dd={d.get('dd_ratio', '?'):.2f}" if isinstance(d.get('dd_ratio'), float) else "",
                             f"n={d.get('child_n_trades', '?')}"]
                    return " | ".join(p for p in parts if p)
                except Exception:
                    return raw[:60]

            tbl["composite_score"] = tbl["composite_score"].apply(_fmt_score)
            tbl = tbl.rename(columns={
                "generation": "gen", "parent_name": "parent", "child_name": "child",
                "delta_sharpe": "Δsharpe", "composite_score": "scores",
            })
            st.dataframe(tbl, use_container_width=True, hide_index=True)
