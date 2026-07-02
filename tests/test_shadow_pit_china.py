"""W1-CN China board leakage harness (scripts/shadow_pit_china.py) — invariants.

Follows the tests/test_vector_pit.py discipline: truncated-replay must be point-in-time,
and the harness's own primitives must hold. Reads the repo data store; skips cleanly if
absent (repo-is-the-database).

Run: .venv/bin/python -m pytest tests/test_shadow_pit_china.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

BOARD = config.data_dir() / "china_standout_track" / "board.parquet"
DEEP = config.data_dir() / "china_stocks"


def _have_data() -> bool:
    return BOARD.exists() and DEEP.exists() and any(DEEP.glob("*.parquet"))


# --------------------------------------------------------------------------- primitives
def test_washout_2w_is_point_in_time_on_its_own_plane():
    """Truncating the panel to an earlier date must NOT change the washout flag AT that
    earlier date (no look-ahead) — the PIT guarantee for the board's washout feature."""
    import scripts.shadow_pit_china as h

    # synthetic 3y daily series with a clear oversold→reclaim on the 2W bar
    idx = pd.bdate_range("2022-01-01", periods=780)
    x = np.linspace(0, 6 * np.pi, 780)
    close = pd.Series(100 + 15 * np.sin(x) + np.linspace(0, 20, 780), index=idx)

    cut = pd.Timestamp("2023-06-30")
    flag_full, be_full = h._washout_2w(close, cut)         # computed from history <= cut
    flag_trunc, be_trunc = h._washout_2w(close.loc[:cut], None)  # panel physically ends at cut
    assert flag_full == flag_trunc, "washout flag leaks: differs full-vs-truncated at same asof"
    assert be_full == be_trunc


def test_bucket_end_is_within_the_panel():
    """The persisted bucket_end (true last daily date feeding the final 2W bucket) must be a
    real observation on/before asof — never a future or synthetic date."""
    import scripts.shadow_pit_china as h
    idx = pd.bdate_range("2022-01-01", periods=400)
    close = pd.Series(np.linspace(50, 80, 400) + np.random.RandomState(0).randn(400), index=idx)
    asof = idx[-1]
    _flag, be = h._washout_2w(close, asof)
    if be is not None:
        assert be <= asof
        assert be in close.index


def test_completed_bucket_flag_differs_or_matches_but_is_defined():
    """The completed-vs-live comparison must be computable and boolean (the bucket tax)."""
    import scripts.shadow_pit_china as h
    idx = pd.bdate_range("2022-01-01", periods=500)
    close = pd.Series(100 + 10 * np.sin(np.linspace(0, 8, 500)), index=idx)
    asof = idx[-1]
    live, _ = h._washout_2w(close, asof)
    comp = h._completed_washout_2w(close, asof)
    assert live in (True, False, None)
    assert comp in (True, False, None)


# --------------------------------------------------------------------------- live-data taxes
def test_plane_tax_reproduces_ledger_on_correct_plane():
    if not _have_data():
        print("  skip (no data store)"); return
    import scripts.shadow_pit_china as h
    b = pd.read_parquet(BOARD)
    d = sorted(b["date"].astype(str).unique())[-1]
    pt = h.measure_plane_tax(d)
    if not pt.get("available") or not pt.get("n_names"):
        print("  skip (board/deep-store thin)"); return
    # correct-plane replay must reproduce the live washout ledger flag well (>=0.9) —
    # this is the harness's self-consistency check (seed: 60/60 on correct plane).
    assert pt["ledger_reproduce_rate"] >= 0.9, pt
    # plane tax is a small-but-nonzero row-flip rate; sanity-bound it
    assert 0.0 <= pt["plane_flip_rate"] <= 0.5, pt


def test_bucket_tax_in_sane_range():
    if not _have_data():
        print("  skip (no data store)"); return
    import scripts.shadow_pit_china as h
    b = pd.read_parquet(BOARD)
    d = sorted(b["date"].astype(str).unique())[-1]
    bt = h.measure_bucket_tax(d, sample=200)
    if not bt.get("available"):
        print("  skip (deep store thin)"); return
    assert 0.0 <= bt["completed_vs_live_flip_rate"] <= 0.5, bt
    # bucket_end must be persisted alongside asof
    ex = bt.get("bucket_end_persisted_example") or []
    if ex:
        assert "bucket_end" in ex[0] and "asof" in ex[0]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
