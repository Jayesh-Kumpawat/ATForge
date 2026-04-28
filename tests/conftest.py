from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def tiny_ohlcv() -> pd.DataFrame:
    """60-row synthetic daily OHLCV frame with a mild uptrend + noise.

    Columns: open, high, low, close, volume. Index: tz-naive daily DatetimeIndex.
    """
    rng = np.random.default_rng(seed=42)
    n = 60
    start = date(2025, 1, 1)
    idx = pd.DatetimeIndex([start + timedelta(days=i) for i in range(n)])

    close = 100 + np.cumsum(rng.normal(0.2, 1.0, size=n))
    open_ = close + rng.normal(0, 0.5, size=n)
    high = np.maximum(open_, close) + rng.uniform(0.1, 1.0, size=n)
    low = np.minimum(open_, close) - rng.uniform(0.1, 1.0, size=n)
    volume = rng.integers(10_000, 100_000, size=n)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    d = tmp_path / "cache"
    d.mkdir()
    return d


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"
