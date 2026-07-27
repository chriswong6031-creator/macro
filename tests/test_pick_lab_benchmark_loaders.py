"""The HK/CN pick-lab benchmark loaders must actually return a series.

WHY THIS EXISTS
---------------
`engine/pick_lab/profile.py` resolved its store with::

    try:
        from engine.data_store import store   # type: ignore[import]
        df = store.read("hk", "^HSI")
        ...
    except Exception:
        return None

`engine.data_store` has never existed — the store module is `lib.store` — so the
ImportError fired on every call and BOTH `_hk_benchmark_loader` and
`_cn_benchmark_loader` returned None unconditionally, forever.  The HK and CN
excess-return rulers therefore graded with no benchmark on every run.

Nothing caught it.  The only tests touching these loaders were::

    assert callable(HK_PROFILE.benchmark_loader)     # test_pick_lab_hk_core.py
    assert callable(CN_PROFILE.benchmark_loader)     # test_pick_lab_cn_core.py

`callable()` is true of a function that unconditionally returns None, so the
assertion passed for as long as the defect existed — the same shape as the
`isinstance(result, bool)` assertions that let macro#3779's freshness SLAs return
"fresh" for every input.

These tests assert on the returned VALUES, against a store the test populates, so
a repointed/renamed/removed store module fails here instead of degrading a live
ruler into a permanent null.

Run:
    python -m pytest tests/test_pick_lab_benchmark_loaders.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from engine.pick_lab.profile import (
    CN_PROFILE,
    HK_PROFILE,
    _cn_benchmark_loader,
    _hk_benchmark_loader,
)


def _closes(n: int = 40, start: str = "2026-05-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame({"close": [100.0 + i for i in range(n)]}, index=idx)


@pytest.fixture()
def store_root(tmp_path, monkeypatch) -> Path:
    """Point lib.store at an empty tmp data dir (lib.store._path calls data_dir())."""
    import lib.config

    monkeypatch.setattr(lib.config, "data_dir", lambda: tmp_path)
    return tmp_path


def _write(root: Path, group: str, filename: str, df: pd.DataFrame) -> None:
    d = root / group
    d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(d / filename)


# ---------------------------------------------------------------------------
# The load actually happens
# ---------------------------------------------------------------------------

def test_hk_benchmark_loader_returns_hsi_closes(store_root):
    """^HSI is stored as hk/_HSI.parquet (lib.store._path maps '^' → '_')."""
    df = _closes()
    _write(store_root, "hk", "_HSI.parquet", df)

    s = _hk_benchmark_loader()

    assert s is not None, "HK benchmark loader returned None with ^HSI present in the store"
    assert isinstance(s, pd.Series)
    assert isinstance(s.index, pd.DatetimeIndex)
    assert len(s) == len(df)
    assert s.iloc[0] == pytest.approx(100.0)
    assert s.iloc[-1] == pytest.approx(100.0 + len(df) - 1)
    assert s.is_monotonic_increasing, "series must be sorted by date"


def test_cn_benchmark_loader_returns_csi300_closes(store_root):
    df = _closes()
    _write(store_root, "china", "510300.SS.parquet", df)

    s = _cn_benchmark_loader()

    assert s is not None, "CN benchmark loader returned None with 510300.SS present in the store"
    assert isinstance(s, pd.Series)
    assert isinstance(s.index, pd.DatetimeIndex)
    assert len(s) == len(df)
    assert s.iloc[-1] == pytest.approx(100.0 + len(df) - 1)


# ---------------------------------------------------------------------------
# The profiles expose the working loaders (not merely *a* callable)
# ---------------------------------------------------------------------------

def test_hk_profile_benchmark_loader_loads(store_root):
    _write(store_root, "hk", "_HSI.parquet", _closes())
    assert HK_PROFILE.benchmark_loader is not None
    assert HK_PROFILE.benchmark_loader() is not None, (
        "HK_PROFILE.benchmark_loader is callable but yields no series — "
        "callable() alone cannot tell a working loader from a permanent null"
    )


def test_cn_profile_benchmark_loader_loads(store_root):
    _write(store_root, "china", "510300.SS.parquet", _closes())
    assert CN_PROFILE.benchmark_loader is not None
    assert CN_PROFILE.benchmark_loader() is not None, (
        "CN_PROFILE.benchmark_loader is callable but yields no series"
    )


# ---------------------------------------------------------------------------
# The documented degrade path still degrades (fail-open contract intact)
# ---------------------------------------------------------------------------

def test_loaders_return_none_when_series_absent(store_root):
    """Empty store → None.  This is the contract; the bug was that it was the ONLY outcome."""
    assert _hk_benchmark_loader() is None
    assert _cn_benchmark_loader() is None
