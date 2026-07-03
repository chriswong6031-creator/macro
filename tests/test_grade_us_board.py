"""Tests for scripts/grade_us_board.py — the US Buy Board forward track-record grader.

Covers:
* _merge_into_store: accumulator semantics (never overwrites history, fresh rows win on dedup).
* build_track: never emits empty:true when the store has rows, even when the fresh grading
  pass itself produced zero new rows (the empty:true regression).
* Idempotency: double-merge produces the same count as a single merge.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.grade_us_board import (  # noqa: E402
    _merge_into_store,
    build_track,
    RETRO_PARQUET,
    LEDGER_DIR,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _minimal_grade_df(as_of="2026-01-02", n=3, horizon=5, lane="buy"):
    """Return a tiny graded DataFrame with all columns build_track expects."""
    rows = []
    for i in range(n):
        rows.append({
            "as_of": as_of, "entry_date": "2026-01-05", "rank_by": "test",
            "horizon": horizon, "lane": lane, "position": i,
            "ticker": f"TICK{i}", "sector": "Technology",
            "alpha": float(i + 1) * 0.1, "score": 0.5, "band": "A",
            "composite_z": 1.5, "verdict": "strong", "align_tier": None,
            "urgency": "high", "state": "coiled", "entry_status": "ok",
            "signal_quality": "ok", "validation_status": "ok",
            "vol_squeeze": "yes", "dispersion_state": "low",
            "off_high": -0.05,
            "ret": 0.04 + i * 0.01, "spy_ret": 0.02,
            "excess_spy": 0.02 + i * 0.01,
            "mae_close_excess_spy": -0.01,
            "sector_etf": "XLK", "etf_ret": 0.015,
            "excess_sector": 0.01 + i * 0.01,
            "mae_close_excess_sector": -0.008,
            "donor_state": None, "donor_sector": None,
            "hold_state": None, "hold_days": None,
            "hold_inv": None, "hold_anchor_src": None,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# _merge_into_store tests
# ---------------------------------------------------------------------------

def test_merge_creates_parquet_from_empty_store(tmp_path, monkeypatch):
    """First-ever run: no pre-existing parquet; fresh df becomes the store."""
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", tmp_path)
    monkeypatch.setattr("scripts.grade_us_board.RETRO_PARQUET", tmp_path / "retro_grades.parquet")
    fresh = _minimal_grade_df(n=5)
    result = _merge_into_store(fresh)
    assert len(result) == 5
    assert (tmp_path / "retro_grades.parquet").exists()


def test_merge_accumulates_new_date(tmp_path, monkeypatch):
    """A second run with a new as_of appends; existing rows survive."""
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", tmp_path)
    pq = tmp_path / "retro_grades.parquet"
    monkeypatch.setattr("scripts.grade_us_board.RETRO_PARQUET", pq)

    first = _minimal_grade_df(as_of="2026-01-02", n=4)
    _merge_into_store(first)

    second = _minimal_grade_df(as_of="2026-01-09", n=6)
    result = _merge_into_store(second)
    assert len(result) == 10  # 4 + 6, no overlap
    assert set(result["as_of"].unique()) == {"2026-01-02", "2026-01-09"}


def test_merge_deduplicates_on_key(tmp_path, monkeypatch):
    """Re-grading the same (as_of, ticker, lane, horizon) replaces the stored row."""
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", tmp_path)
    pq = tmp_path / "retro_grades.parquet"
    monkeypatch.setattr("scripts.grade_us_board.RETRO_PARQUET", pq)

    first = _minimal_grade_df(as_of="2026-01-02", n=3)
    _merge_into_store(first)

    # Re-grade same keys with updated excess_spy value
    updated = first.copy()
    updated["excess_spy"] = 0.99
    result = _merge_into_store(updated)
    # De-dup should keep fresh (0.99), not the old value
    assert len(result) == 3
    assert (result["excess_spy"] == 0.99).all()


def test_merge_with_empty_fresh_returns_stored(tmp_path, monkeypatch):
    """The key regression guard: empty fresh pass must return the full store unchanged
    and must NOT rewrite the parquet (so we check the value is preserved)."""
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", tmp_path)
    pq = tmp_path / "retro_grades.parquet"
    monkeypatch.setattr("scripts.grade_us_board.RETRO_PARQUET", pq)

    seed = _minimal_grade_df(n=7)
    _merge_into_store(seed)

    # Now simulate a run that grades 0 new rows
    empty = pd.DataFrame()
    result = _merge_into_store(empty)
    assert len(result) == 7, "store must survive an empty fresh-grading pass"
    # Parquet still holds 7 rows (not overwritten with empty)
    persisted = pd.read_parquet(pq)
    assert len(persisted) == 7


def test_merge_idempotent(tmp_path, monkeypatch):
    """Merging the same fresh df twice yields the same row count as merging once."""
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", tmp_path)
    pq = tmp_path / "retro_grades.parquet"
    monkeypatch.setattr("scripts.grade_us_board.RETRO_PARQUET", pq)

    fresh = _minimal_grade_df(n=4)
    r1 = _merge_into_store(fresh)
    r2 = _merge_into_store(fresh)
    assert len(r1) == len(r2) == 4


# ---------------------------------------------------------------------------
# build_track tests
# ---------------------------------------------------------------------------

def _boards_stub(*as_ofs):
    return [{"as_of": a, "rows": []} for a in as_ofs]


def _names_stub():
    return pd.DataFrame()


def test_build_track_never_empty_with_rows():
    """build_track must not emit empty:true when df has rows — the core regression."""
    df = _minimal_grade_df(n=5)
    track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
    assert "empty" not in track, "build_track emitted empty:true with non-empty df"
    assert track["graded_rows_total"] == 5


def test_build_track_hit_rate_in_range():
    """Hit rate is between 0 and 1; n matches input."""
    df = _minimal_grade_df(n=10, lane="buy")
    track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
    buy_h5 = track["per_horizon"]["h5"]["buy_lane"]["vs_spy"]
    assert 0.0 <= buy_h5["hit_rate"] <= 1.0
    assert buy_h5["n"] == 10


def test_build_track_empty_df_emits_empty_flag():
    """build_track(empty) should emit empty:true — the signal to the caller that
    the store needs to be loaded first."""
    track = build_track(pd.DataFrame(), _boards_stub("2026-01-02"), _names_stub())
    assert track.get("empty") is True


def test_build_track_precision_at_k_present():
    """precision_at_k keys exist for the buy lane at each horizon."""
    df = _minimal_grade_df(n=6, lane="buy")
    track = build_track(df, _boards_stub("2026-01-02"), _names_stub())
    buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
    assert "precision_at_k_board_order_vs_spy" in buy_h5
    assert "precision_at_k_alpha_order_vs_spy" in buy_h5
    # k1 through k5 exist (K_LIST = [1, 3, 5, 10]; only k1..k5 valid with n=6)
    for k in ["k1", "k3", "k5"]:
        assert k in buy_h5["precision_at_k_board_order_vs_spy"], f"{k} missing"
