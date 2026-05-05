"""PipelineMonitor — Rich live terminal display for pipeline runs.

Runs in a background daemon thread. Pipeline nodes emit events into EventBus;
monitor drains and renders them in real time using rich.live.Live.

Usage:
    bus = EventBus()
    monitor = PipelineMonitor(bus, run_id="abc123", max_generations=3)
    monitor.start()
    graph.invoke(...)
    monitor.stop()
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from atforge.graph.events import (
    EventBus,
    EvtBacktestDone,
    EvtGenerationDone,
    EvtMutationProposed,
    EvtNodeDone,
    EvtNodeStart,
    EvtPipelineDone,
    EvtPipelineStart,
    EvtRatchetVerdict,
)


@dataclass
class _BacktestRow:
    symbol: str
    strategy: str
    success: bool
    sharpe: float | None


@dataclass
class _RatchetRow:
    parent_name: str
    child_name: str
    accepted: bool
    delta_sharpe: float
    reason: str


@dataclass
class _State:
    run_id: str = ""
    max_generations: int = 1
    current_node: str = "starting"
    generation: int = 0
    elapsed_start: float = field(default_factory=time.monotonic)

    backtests: list[_BacktestRow] = field(default_factory=list)
    mutations: dict[str, int] = field(default_factory=dict)  # mutator → count
    verdicts: list[_RatchetRow] = field(default_factory=list)
    gen_summaries: list[str] = field(default_factory=list)

    done: bool = False
    final_n_backtests: int = 0
    final_n_failures: int = 0


class PipelineMonitor:
    """Background thread that renders a Rich live display from EventBus events."""

    def __init__(self, bus: EventBus, run_id: str, max_generations: int) -> None:
        self._bus = bus
        self._state = _State(run_id=run_id, max_generations=max_generations)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._bus.close()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _run(self) -> None:
        with Live(self._render(), refresh_per_second=4, vertical_overflow="visible") as live:
            while not self._stop_event.is_set():
                events = self._bus.drain(timeout=0.1)
                for evt in events:
                    self._handle(evt)
                live.update(self._render())
                if self._state.done:
                    break
            # Final render
            live.update(self._render())

    def _handle(self, evt: object) -> None:
        s = self._state
        if isinstance(evt, EvtPipelineStart):
            s.run_id = evt.run_id
            s.max_generations = evt.max_generations
        elif isinstance(evt, EvtNodeStart):
            s.current_node = evt.node_name
            s.generation = evt.generation
        elif isinstance(evt, EvtNodeDone):
            pass
        elif isinstance(evt, EvtBacktestDone):
            s.backtests.append(_BacktestRow(evt.symbol, evt.strategy, evt.success, evt.sharpe))
        elif isinstance(evt, EvtMutationProposed):
            s.mutations[evt.mutator] = s.mutations.get(evt.mutator, 0) + evt.n_proposals
        elif isinstance(evt, EvtRatchetVerdict):
            s.verdicts.append(
                _RatchetRow(
                    evt.parent_name, evt.child_name, evt.accepted, evt.delta_sharpe, evt.reason
                )
            )
        elif isinstance(evt, EvtGenerationDone):
            s.gen_summaries.append(
                f"Gen {evt.generation}: {evt.n_backtests} backtests, {evt.n_accepted}/{len(s.verdicts)} mutations accepted"
            )
        elif isinstance(evt, EvtPipelineDone):
            s.done = True
            s.final_n_backtests = evt.n_backtests
            s.final_n_failures = evt.n_failures
            s.current_node = "done"

    def _render(self) -> Panel:
        s = self._state
        elapsed = time.monotonic() - s.elapsed_start
        elapsed_str = f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}"

        header = Text.assemble(
            ("ATForge Pipeline Monitor", "bold cyan"),
            "  ",
            ("run=", "dim"),
            (s.run_id or "?", "yellow"),
            "  ",
            ("gen=", "dim"),
            (f"{s.generation}/{s.max_generations}", "green"),
            "  ",
            ("node=", "dim"),
            (s.current_node, "bold white"),
            "  ",
            (f"[{elapsed_str}]", "dim"),
        )

        sections: list[object] = [header, Text("")]

        # Backtest progress
        recent = s.backtests[-15:]  # last 15 to avoid overwhelming display
        n_ok = sum(1 for b in s.backtests if b.success)
        n_fail = len(s.backtests) - n_ok

        bt_table = Table(box=None, padding=(0, 1), show_header=True, header_style="bold dim")
        bt_table.add_column("Symbol", style="cyan", width=12)
        bt_table.add_column("Strategy", style="white", width=28)
        bt_table.add_column("", width=3)
        bt_table.add_column("Sharpe", style="yellow", width=8)
        for b in recent:
            mark = "[green]✓[/]" if b.success else "[red]✗[/]"
            sharpe_str = f"{b.sharpe:.3f}" if b.sharpe is not None else "-"
            bt_table.add_row(b.symbol, b.strategy[:27], mark, sharpe_str)

        sections.append(
            Panel(
                bt_table,
                title=f"Backtests  [green]{n_ok} ok[/] [red]{n_fail} fail[/] [dim](showing last {len(recent)})[/]",
                border_style="dim",
            )
        )

        # Mutations + ratchet
        if s.mutations or s.verdicts:
            mut_lines = [f"  [cyan]{k}[/]: {v} proposals" for k, v in s.mutations.items()]
            n_acc = sum(1 for v in s.verdicts if v.accepted)
            n_rej = len(s.verdicts) - n_acc

            verd_table = Table(box=None, padding=(0, 1), show_header=False)
            verd_table.add_column("", width=3)
            verd_table.add_column("Child", style="white", width=28)
            verd_table.add_column("Δsharpe", style="yellow", width=10)
            verd_table.add_column("Reason", style="dim", width=30)
            for v in s.verdicts[-8:]:
                mark = "[green]✓[/]" if v.accepted else "[red]✗[/]"
                sign = "+" if v.delta_sharpe >= 0 else ""
                verd_table.add_row(
                    mark, v.child_name[:27], f"{sign}{v.delta_sharpe:.4f}", v.reason[:30]
                )

            evo_content = Group(
                Text("\n".join(mut_lines) if mut_lines else "  (none yet)", no_wrap=False),
                Text(""),
                verd_table,
            )
            sections.append(
                Panel(
                    evo_content,
                    title=f"Evolution  [green]{n_acc} accepted[/] [red]{n_rej} rejected[/]",
                    border_style="dim",
                )
            )

        # Generation summaries
        if s.gen_summaries:
            sections.append(Text("  " + " │ ".join(s.gen_summaries), style="dim"))

        if s.done:
            sections.append(
                Text(
                    f"\n  [bold green]Pipeline complete[/]  "
                    f"backtests={s.final_n_backtests}  failures={s.final_n_failures}  {elapsed_str}",
                    no_wrap=False,
                )
            )

        return Panel(Group(*sections), border_style="cyan", title="[bold]ATForge[/]")
