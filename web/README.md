# ATForge Web Dashboard (Track C)

Read-only Next.js dashboard for ATForge. Six screens, run-first navigation:
Overview, Monitor (live SSE), Runs, Run Detail, Strategies, Strategy Detail.

## Run

Backend (from repo root):
```bash
uv run python -m atforge.api.main          # serves http://localhost:8000
```

Frontend (from `web/`):
```bash
export PATH="$HOME/Library/pnpm/bin:$PATH"
./node_modules/.bin/next dev                # serves http://localhost:3000
```

## Build / typecheck

```bash
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/next build
```

## Environment

- `NEXT_PUBLIC_API_URL` — backend base URL (default `http://localhost:8000`).
- `NEXT_PUBLIC_LANGFUSE_HOST` — optional; enables "open full trace in Langfuse" links on agent timeline events.

## Architecture

`web/` is fully deletable without affecting the pipeline. Design system lives in
`src/components/primitives/`; screens compose primitives only. See
`docs/superpowers/specs/2026-05-16-track-c-frontend-redesign.md`.
