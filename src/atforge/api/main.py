"""uvicorn entrypoint: `uv run python -m atforge.api.main`."""
from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "atforge.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
