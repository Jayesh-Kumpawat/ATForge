# ATForge Documentation

Complete, code-accurate documentation of the ATForge backend (`src/atforge/`). Written 2026-05-18 by reading every source file end to end. The web dashboard (`web/`) is intentionally out of scope.

## Reading order

Read top to bottom the first time. After that, jump straight to the doc you need.

| # | Doc | Read it when you want to know... |
|---|---|---|
| 1 | [01_OVERVIEW.md](01_OVERVIEW.md) | What ATForge is, the pipeline shape, how one run lives and dies, the module map |
| 2 | [02_EXECUTION_FLOW.md](02_EXECUTION_FLOW.md) | The complete trace — `main.py` to every node, function by function, what each reads/writes |
| 3 | [03_AGENTS_AND_TOOLS.md](03_AGENTS_AND_TOOLS.md) | How the multi-agent layer works — explorer/exploiter/critic, the ReAct loop, tool calling, the 5 research tools |
| 4 | [04_DESIGN_DECISIONS.md](04_DESIGN_DECISIONS.md) | *Why* it is built this way — every architecture choice, the trade-off, the rejected alternative |
| 5 | [05_DATA_MODEL.md](05_DATA_MODEL.md) | The SQLite schema, the `PipelineState` shape, the key dataclasses |

If you only read one: **02_EXECUTION_FLOW.md**. It is the spine — everything else hangs off it.

## How these docs are organized

- **01, 02, 03** describe *how the system works* — behavior, control flow, data movement.
- **04** describes *why* — it never repeats mechanics, only motivation and trade-offs.
- **05** is pure *reference* — look things up, do not read straight through.

Each doc uses `file.py:function` and `file.py:line` references so you can jump to the exact code.

## Scope and honesty

- **Backend only.** `src/atforge/` plus root `main.py`, `cli.py` lives at `src/atforge/cli.py`, and `atforge.yaml`. The `web/` Next.js dashboard and `dashboard.py` Streamlit app are not documented here.
- **Code is the source of truth.** Where a module `CLAUDE.md` disagrees with the code, these docs follow the code and flag the drift. Known drifts as of 2026-05-18 are listed in [04_DESIGN_DECISIONS.md](04_DESIGN_DECISIONS.md#appendix-doc-vs-code-drift-found-2026-05-18).
- **Dead code is labeled.** Two factory functions (`nodes.py:make_run_backtest`, `nodes_phase2.py:make_mutate_strategies`) exist but are never wired into the compiled graph. They are called out where relevant.

## Keeping docs current

These docs were rebuilt from scratch because the previous set (`docs/INTERNALS.md`, `docs/DESIGN.md`, `docs/MEMORY.md`, root `ARCHITECTURE.md` — now in `docs/archive/`) drifted: updates were additive and never reconciled with deletions or behavior changes.

To avoid repeating that:
- After any change to the pipeline graph, a node, the ratchet, the agent layer, or the schema — update the matching doc in the **same commit** as the code.
- The `/update-docs` skill maps changed files to doc sections. Its lookup table points at the old `INTERNALS.md`/`DESIGN.md` and must be repointed at this doc set before it is useful again.
- The `graphify-out/` knowledge graph (`graph.html`, `graph.json`, `GRAPH_REPORT.md`) is a navigational aid, regenerated with `/graphify`. It is not authoritative — this doc set is.

## Module `CLAUDE.md` files

Each `src/atforge/*/CLAUDE.md` is Claude Code's working memory for that module. They are detailed and mostly accurate, but they are *instructions for an AI editor*, not user documentation, and they drift. Treat this `docs/` set as the canonical human reference; treat `CLAUDE.md` files as a fast in-context summary when editing that module.
