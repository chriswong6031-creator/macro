"""Tests for scripts/grade_us_board.py — the US Buy Board forward track-record grader.

Covers:
* _merge_into_store: accumulator semantics (never overwrites history, fresh rows win on dedup).
* build_track: never emits empty:true when the store has rows, even when the fresh grading
  pass itself produced zero new rows (the empty:true regression).
* Idempotency: double-merge produces the same count as a single merge.
* W0.1 B-b: parity harness (old vs new grading), 63d lane, spine columns, survivorship,
  vector stamp PIT, schema-union with legacy parquet.
"""
import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.grade_us_board import (  # noqa: E402
    _merge_into_store,
    _backfill_regime_stamps,
    _backfill_archetype,
    _archetype_pit,
    _excess_close_path_mae,
    _hit_stats,
    _live_definition,
    _norm_definition,
    build_track,
    grade_boards,
    RETRO_PARQUET,
    LEDGER_DIR,
    HORIZONS,
    _REGIME_STAMP_COLS,
    _RETIRED_LEDGER_COLS,
)
from engine import us_board_rank as ubr  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _minimal_grade_df(as_of="2026-01-02", n=3, horizon=5, lane="buy"):
    """Return a tiny graded DataFrame with all columns build_track expects."""
    tiers = ["T1", "T2", "T3", "T4"]
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
            # W0.2b — tier_cascade column (None on pre-schema boards; cycled through T1-T4 here
            # so that _slice_table(buy, "tier_cascade", "excess_spy") exercises real strata).
            "tier_cascade": tiers[i % len(tiers)],
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
    """Re-grading the same (as_of, ticker, lane, horizon) yields ONE row, and does not
    restate its price-derived measurement.

    INVERTED 2026-08-06. This asserted `excess_spy` took the fresh value, which is the
    behaviour that let a re-based breadth cache silently rewrite published returns: 75
    shipped rows moved on a re-run, 19 materially. Dedup-to-one-row is still the
    contract; the measurement is now write-once (see _FROZEN_PRICE_COLS)."""
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", tmp_path)
    pq = tmp_path / "retro_grades.parquet"
    monkeypatch.setattr("scripts.grade_us_board.RETRO_PARQUET", pq)

    first = _minimal_grade_df(as_of="2026-01-02", n=3)
    _merge_into_store(first)
    # each seeded row carries a DIFFERENT excess_spy, so compare per ticker rather than
    # against one scalar — a scalar comparison would pass on a single-row fixture and
    # hide a merge that collapsed every row onto the same value.
    original = first.set_index("ticker")["excess_spy"]

    updated = first.copy()
    updated["excess_spy"] = 0.99
    result = _merge_into_store(updated)
    assert len(result) == 3, "dedup must still collapse to one row per key"
    got = result.set_index("ticker")["excess_spy"]
    assert got.reindex(original.index).equals(original), (
        "a published excess return was restated by a re-grade")


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

# build_track applies the file's ONE era rule (G3 2026-08-06): rows dated before
# LEDGER_HISTORY_FROM describe the 120-name broad-screen board, not the product that
# ships today, and are excluded here exactly as emit_ledger already excluded them.
# These fixtures therefore date IN-ERA. The date is a fixed constant, not a
# wall-clock offset, so it cannot expire; the exclusion itself is pinned separately
# in TestOneEraRule below.
_IN_ERA = "2026-06-30"
_PRE_ERA = "2026-06-16"


def _boards_stub(*as_ofs):
    return [{"as_of": a, "rows": []} for a in as_ofs]


def _names_stub():
    return pd.DataFrame()


def test_build_track_never_empty_with_rows():
    """build_track must not emit empty:true when df has rows — the core regression."""
    df = _minimal_grade_df(as_of=_IN_ERA, n=5)
    track = build_track(df, _boards_stub(_IN_ERA), _names_stub())
    assert "empty" not in track, "build_track emitted empty:true with non-empty df"
    assert track["graded_rows_total"] == 5


def test_build_track_hit_rate_in_range():
    """Hit rate is between 0 and 1; n matches input."""
    df = _minimal_grade_df(as_of=_IN_ERA, n=10, lane="buy")
    track = build_track(df, _boards_stub(_IN_ERA), _names_stub())
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
    df = _minimal_grade_df(as_of=_IN_ERA, n=6, lane="buy")
    track = build_track(df, _boards_stub(_IN_ERA), _names_stub())
    buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
    assert "precision_at_k_board_order_vs_spy" in buy_h5
    assert "precision_at_k_alpha_order_vs_spy" in buy_h5
    # k1 through k5 exist (K_LIST = [1, 3, 5, 10]; only k1..k5 valid with n=6)
    for k in ["k1", "k3", "k5"]:
        assert k in buy_h5["precision_at_k_board_order_vs_spy"], f"{k} missing"


# ---------------------------------------------------------------------------
# W0.2b — tier_cascade in graded record + by_tier_cascade stratification
# ---------------------------------------------------------------------------

def test_graded_df_carries_tier_cascade():
    """W0.2b: tier_cascade emitted into the graded record so retro_grades.parquet
    stores the field (previously captured in _row_features but never in the rec dict)."""
    df = _minimal_grade_df(n=4, lane="buy")
    # _minimal_grade_df now cycles through T1-T4 for tier_cascade
    assert "tier_cascade" in df.columns
    assert set(df["tier_cascade"].dropna()) <= {"T1", "T2", "T3", "T4"}


def test_build_track_by_tier_cascade_present():
    """W0.2b: build_track emits by_tier_cascade in the buy_lane block so downstream
    consumers can stratify graded results by T1/T2/T3/T4 cascade tier."""
    df = _minimal_grade_df(as_of=_IN_ERA, n=4, lane="buy")
    track = build_track(df, _boards_stub(_IN_ERA), _names_stub())
    buy_h5 = track["per_horizon"]["h5"]["buy_lane"]
    assert "by_tier_cascade" in buy_h5, "by_tier_cascade missing from buy_lane output"
    # the strata should be non-empty (the df has T1/T2/T3/T4 with n=1 each)
    assert len(buy_h5["by_tier_cascade"]) > 0


def test_by_tier_cascade_hit_stats_are_bounded():
    """W0.2b: per-tier hit_rate in by_tier_cascade is between 0 and 1 (sanity)."""
    df = _minimal_grade_df(as_of=_IN_ERA, n=8, lane="buy")
    track = build_track(df, _boards_stub(_IN_ERA), _names_stub())
    by_tier = track["per_horizon"]["h5"]["buy_lane"]["by_tier_cascade"]
    for tier, stats in by_tier.items():
        if "hit_rate" in stats:
            assert 0.0 <= stats["hit_rate"] <= 1.0, (
                f"tier {tier} hit_rate={stats['hit_rate']} out of bounds")


# ---------------------------------------------------------------------------
# W0.1 B-b — parity harness: _excess_close_path_mae vs old _close_path_mae
# ---------------------------------------------------------------------------

def _make_price_series(n=30, start="2026-01-02"):
    """Monotone rising + dip series for parity testing."""
    idx = pd.bdate_range(start, periods=n)
    vals = [100.0] + [100.0 * (1.01**i) for i in range(1, n)]
    vals[5] = 95.0   # dip at bar 5
    vals[8] = 93.0   # deeper dip at bar 8
    return pd.Series(vals, index=idx)


def _old_close_path_mae(name_ser, bench_ser, entry_pos, h):
    """Reference implementation of the deleted _close_path_mae (for parity check)."""
    if entry_pos + h >= len(name_ser):
        return None
    np0 = name_ser.iloc[entry_pos]
    bp0 = bench_ser.iloc[entry_pos]
    if pd.isna(np0) or pd.isna(bp0) or np0 <= 0 or bp0 <= 0:
        return None
    worst = 0.0
    for j in range(1, h + 1):
        npj = name_ser.iloc[entry_pos + j]
        bpj = bench_ser.iloc[entry_pos + j]
        if pd.isna(npj) or pd.isna(bpj):
            continue
        exc = (npj / np0 - 1.0) - (bpj / bp0 - 1.0)
        worst = min(worst, exc)
    return float(worst)


def test_parity_excess_mae_matches_old_implementation():
    """Parity: _excess_close_path_mae (new) == old _close_path_mae at same fill position.

    The old code used entry_pos = _pos_after(index, as_of) which equals fill_index
    (same next-bar convention). This test verifies the mathematical equivalence.
    """
    from engine.grading import fill_index
    name_ser = _make_price_series()
    spy_ser = pd.Series([100.0 * (1.005**i) for i in range(30)],
                        index=name_ser.index)

    as_of = name_ser.index[0]  # signal on bar 0 -> fill on bar 1
    fill = fill_index(name_ser, as_of)
    assert fill is not None, "fill_index returned None unexpectedly"

    parity_table = []
    for h in [5, 10, 21]:
        old_val = _old_close_path_mae(name_ser, spy_ser, fill, h)
        new_val = _excess_close_path_mae(name_ser, spy_ser, fill, h)
        diff = abs(old_val - new_val) if (old_val is not None and new_val is not None) else None
        parity_table.append({"metric": f"mae_close_excess_spy h={h}", "n": 1,
                              "max_abs_diff": diff, "divergent_rows": 0 if diff == 0.0 else 1,
                              "reason": "identical window semantics"})
        assert diff is not None, f"h={h}: both should return a float"
        assert diff < 1e-12, (
            f"h={h}: parity FAIL — old={old_val:.8f} new={new_val:.8f} diff={diff:.2e}")

    # Print parity table (visible in pytest -s output; also captured in PR body)
    print("\nPARITY TABLE — mae_close_excess (old _close_path_mae vs new _excess_close_path_mae):")
    print(f"{'metric':<35} {'n':>4} {'max_abs_diff':>14} {'divergent_rows':>15} reason")
    for row in parity_table:
        print(f"{row['metric']:<35} {row['n']:>4} {row['max_abs_diff']:>14.2e} "
              f"{row['divergent_rows']:>15} {row['reason']}")


def test_parity_forward_return_matches_old_fwd_ret():
    """Parity: engine.grading.forward_metrics fwd_ret == old _fwd_ret logic.

    Old _fwd_ret: close[entry_pos + h] / close[entry_pos] - 1.
    New forward_metrics: close[fill+h] / close[fill] - 1 (fill = entry_pos here).
    """
    from engine.grading import fill_index, forward_metrics
    ser = _make_price_series()
    as_of = ser.index[0]
    fill = fill_index(ser, as_of)

    # Old implementation inline
    def _old_fwd_ret(series, entry_pos, h):
        if entry_pos + h >= len(series):
            return None
        p0 = series.iloc[entry_pos]
        p1 = series.iloc[entry_pos + h]
        if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
            return None
        return float(p1 / p0 - 1.0)

    parity_table = []
    fwd = forward_metrics(ser, as_of, horizons=(5, 10, 21))
    for h in [5, 10, 21]:
        old_val = _old_fwd_ret(ser, fill, h)
        new_val = fwd.get(f"fwd_ret_{h}")
        diff = abs(old_val - new_val) if (old_val is not None and new_val is not None) else None
        parity_table.append({"metric": f"fwd_ret h={h}", "n": 1,
                              "max_abs_diff": diff, "divergent_rows": 0 if diff == 0.0 else 1,
                              "reason": "identical fill + window"})
        assert diff is not None
        assert diff < 1e-12, f"h={h}: parity FAIL old={old_val} new={new_val}"

    print("\nPARITY TABLE — fwd_ret (old _fwd_ret vs engine.grading.forward_metrics):")
    print(f"{'metric':<25} {'n':>4} {'max_abs_diff':>14} {'divergent_rows':>15} reason")
    for row in parity_table:
        print(f"{row['metric']:<25} {row['n']:>4} {row['max_abs_diff']:>14.2e} "
              f"{row['divergent_rows']:>15} {row['reason']}")


# ---------------------------------------------------------------------------
# W0.1 B-b — 63d lane maturation
# ---------------------------------------------------------------------------

def _minimal_grade_df_with_h63(as_of="2026-01-02", n=3, lane="buy"):
    """Return a graded DataFrame with horizon=63 rows."""
    rows = [
        {
            "as_of": as_of, "entry_date": "2026-04-01", "rank_by": "test",
            "horizon": 63, "lane": lane, "position": i,
            "ticker": f"TICK{i}", "sector": "Technology",
            "alpha": 0.1, "score": 0.5, "band": "A",
            "composite_z": 1.5, "verdict": "strong", "align_tier": None,
            "urgency": "high", "state": "coiled", "entry_status": "ok",
            "signal_quality": "ok", "validation_status": "ok",
            "vol_squeeze": "yes", "dispersion_state": "low",
            "off_high": -0.05,
            "ret": 0.08 + i * 0.01, "spy_ret": 0.04,
            "excess_spy": 0.04 + i * 0.01,
            "mae_close_excess_spy": -0.02,
            "sector_etf": "XLK", "etf_ret": 0.03,
            "excess_sector": 0.02 + i * 0.01,
            "mae_close_excess_sector": -0.01,
            "donor_state": None, "donor_sector": None,
            "hold_state": None, "hold_days": None,
            "hold_inv": None, "hold_anchor_src": None,
            "tier_cascade": "T1",
            "fwd_mfe_63": 0.12 + i * 0.01,
            "terminal_state_clean15_126": None,
            "terminal_state_clean8_21": None,
            "post_cushion_breach": None,
            "rate_pressure": None, "quad_hard_label": None,
            "fused_risk_label": None, "vol_regime": None,
            "risk_radar_state": None, "regime_vector_degraded": None,
            "vector_asof": None, "staleness_hours": None,
            "archetype": None,
        }
        for i in range(n)
    ]
    return pd.DataFrame(rows)


def test_63d_lane_in_horizons():
    """W0.1 B-b: HORIZONS now includes 63."""
    assert 63 in HORIZONS, f"63 missing from HORIZONS={HORIZONS}"
    assert HORIZONS == [5, 10, 21, 63], f"unexpected HORIZONS={HORIZONS}"


def test_63d_lane_graded_in_build_track():
    """W0.1 B-b: build_track processes h63 rows and emits per_horizon.h63 block."""
    df = _minimal_grade_df_with_h63(as_of=_IN_ERA, n=4, lane="buy")
    track = build_track(df, _boards_stub(_IN_ERA), _names_stub())
    assert "h63" in track.get("per_horizon", {}), "h63 block missing from per_horizon"
    h63_block = track["per_horizon"]["h63"]
    assert h63_block.get("overall_vs_spy", {}).get("n", 0) == 4


def test_63d_lane_merge_into_store(tmp_path, monkeypatch):
    """W0.1 B-b: h63 rows accumulate correctly via _merge_into_store."""
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", tmp_path)
    pq = tmp_path / "retro_grades.parquet"
    monkeypatch.setattr("scripts.grade_us_board.RETRO_PARQUET", pq)

    df63 = _minimal_grade_df_with_h63(n=3, lane="buy")
    result = _merge_into_store(df63)
    assert len(result) == 3
    assert set(result["horizon"].unique()) == {63}


# ---------------------------------------------------------------------------
# W0.1 B-b — spine column threading
# ---------------------------------------------------------------------------

def _grade_df_with_spine(n=4, as_of="2026-01-02", horizon=5):
    """Return a graded DataFrame with all W0.1 B-b spine columns populated."""
    rows = []
    for i in range(n):
        rows.append({
            "as_of": as_of, "entry_date": "2026-01-05", "rank_by": "test",
            "horizon": horizon, "lane": "buy", "position": i,
            "ticker": f"TICK{i}", "sector": "Technology",
            "alpha": 0.1, "score": 0.5, "band": "A",
            "composite_z": 1.5, "verdict": "strong", "align_tier": None,
            "urgency": "high", "state": "coiled", "entry_status": "ok",
            "signal_quality": "ok", "validation_status": "ok",
            "vol_squeeze": "yes", "dispersion_state": "low",
            "off_high": -0.05,
            "ret": 0.04, "spy_ret": 0.02,
            "excess_spy": 0.02,
            "mae_close_excess_spy": -0.01,
            "sector_etf": "XLK", "etf_ret": 0.015,
            "excess_sector": 0.01,
            "mae_close_excess_sector": -0.008,
            "donor_state": None, "donor_sector": None,
            "hold_state": None, "hold_days": None,
            "hold_inv": None, "hold_anchor_src": None,
            "tier_cascade": "T1",
            f"fwd_mfe_{horizon}": 0.08,
            "terminal_state_clean15_126": "CUSHIONED",
            "terminal_state_clean8_21": "STOPPED",
            "post_cushion_breach": True if i % 2 == 0 else False,
            "rate_pressure": "rising",
            "quad_hard_label": "Q2",
            "fused_risk_label": "risk-on",
            "vol_regime": "low",
            "risk_radar_state": "green",
            "regime_vector_degraded": False,
            "vector_asof": "2026-01-02",
            "staleness_hours": 0.0,
            # species_id is NOT here: retired 2026-08-04, so a graded frame no longer
            # carries it (see the retirement tests below)
            "archetype": "COILED",
        })
    return pd.DataFrame(rows)


def test_spine_columns_present_in_graded_df():
    """W0.1 B-b: all spine columns are present in a graded DataFrame."""
    df = _grade_df_with_spine(n=4, horizon=5)
    for col in [
        "fwd_mfe_5", "terminal_state_clean15_126", "terminal_state_clean8_21",
        "post_cushion_breach", "rate_pressure", "quad_hard_label",
        "fused_risk_label", "vol_regime", "risk_radar_state",
        "regime_vector_degraded", "vector_asof", "staleness_hours",
        "archetype",
    ]:
        assert col in df.columns, f"spine column {col!r} missing"


# NOTE 2026-08-04: the former test_species_id_always_null pinned species_id as a
# permanently-null spine column.  The column is retired (no species uniquely binds this
# ledger, so it could never populate) and its replacement pins the retirement itself, at
# the two places that can resurrect it: the rec dict and the store-merge carry path.


def test_archetype_from_payload():
    """W0.1 B-b §3.4: archetype carries the value from the board row payload."""
    df = _grade_df_with_spine(n=4, horizon=5)
    assert (df["archetype"] == "COILED").all(), "archetype should match board row payload"


def test_terminal_state_values_valid():
    """W0.1 B-b: terminal_state columns contain valid TerminalState strings or None."""
    from engine.grading import TerminalState
    valid = {TerminalState.STOPPED, TerminalState.DEAD_MONEY,
             TerminalState.CUSHIONED, TerminalState.CLEAN_LIFTOFF, None}
    df = _grade_df_with_spine(n=4, horizon=5)
    for val in df["terminal_state_clean15_126"]:
        assert val in valid or pd.isna(val), f"invalid terminal_state_clean15_126: {val!r}"
    for val in df["terminal_state_clean8_21"]:
        assert val in valid or pd.isna(val), f"invalid terminal_state_clean8_21: {val!r}"


def test_post_cushion_breach_is_bool_or_none():
    """W0.1 B-b: post_cushion_breach is bool or None (never a float or string)."""
    df = _grade_df_with_spine(n=4, horizon=5)
    for val in df["post_cushion_breach"]:
        assert val is None or isinstance(val, (bool, np.bool_)), (
            f"post_cushion_breach should be bool or None, got {type(val)}")


# ---------------------------------------------------------------------------
# W0.1 B-b — schema-union with legacy parquet
# ---------------------------------------------------------------------------

def _minimal_legacy_df(as_of="2026-01-01", n=3):
    """Legacy parquet row (pre B-b) — no spine columns."""
    rows = []
    for i in range(n):
        rows.append({
            "as_of": as_of, "entry_date": "2026-01-02", "rank_by": "test",
            "horizon": 5, "lane": "buy", "position": i,
            "ticker": f"OLD{i}", "sector": "Financials",
            "alpha": 0.05, "score": 0.4, "band": "B",
            "composite_z": 0.8, "verdict": "ok", "align_tier": None,
            "urgency": "low", "state": "recovering", "entry_status": "ok",
            "signal_quality": "ok", "validation_status": "ok",
            "vol_squeeze": None, "dispersion_state": None,
            "off_high": -0.1,
            "ret": 0.03, "spy_ret": 0.02,
            "excess_spy": 0.01,
            "mae_close_excess_spy": -0.005,
            "sector_etf": "XLF", "etf_ret": 0.015,
            "excess_sector": 0.005,
            "mae_close_excess_sector": -0.003,
            "donor_state": None, "donor_sector": None,
            "hold_state": None, "hold_days": None,
            "hold_inv": None, "hold_anchor_src": None,
            "tier_cascade": None,
        })
    return pd.DataFrame(rows)


def test_schema_union_legacy_rows_get_nulls(tmp_path, monkeypatch):
    """W0.1 B-b: legacy rows in the store get null spine columns; new rows get values."""
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", tmp_path)
    pq = tmp_path / "retro_grades.parquet"
    monkeypatch.setattr("scripts.grade_us_board.RETRO_PARQUET", pq)

    # Seed the store with a legacy (pre-B-b) frame (no spine columns)
    legacy = _minimal_legacy_df(as_of="2026-01-01", n=3)
    legacy.to_parquet(pq, index=False)

    # Merge new rows that have the spine columns
    fresh = _grade_df_with_spine(n=2, as_of="2026-01-10", horizon=5)
    result = _merge_into_store(fresh)

    assert len(result) == 5, "legacy + fresh should be 5 rows total"
    # Spine columns should now exist in the merged frame
    assert "fwd_mfe_5" in result.columns, "fwd_mfe_5 missing after schema-union"
    assert "terminal_state_clean15_126" in result.columns

    # Legacy rows (OLD0/OLD1/OLD2) should have null spine values
    legacy_rows = result[result["ticker"].str.startswith("OLD")]
    assert legacy_rows["fwd_mfe_5"].isna().all(), "legacy rows should have null fwd_mfe_5"
    assert legacy_rows["terminal_state_clean15_126"].isna().all()

    # New rows should have non-null spine values
    new_rows = result[result["ticker"].str.startswith("TICK")]
    assert new_rows["fwd_mfe_5"].notna().all(), "new rows should have non-null fwd_mfe_5"


def test_schema_union_freezes_prices_but_still_accrues_annotations(tmp_path, monkeypatch):
    """W0.1 B-b schema-union still works; the PRICE half of the row is now write-once.

    INVERTED 2026-08-06 (was: fresh replaces the stored row wholesale). `fwd_mfe_5` is
    computed off the close panel, and the panel is re-based in place, so replacing it on
    every run restates history. Annotations must still land, or the regime/archetype
    backfills stop reaching historical rows."""
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", tmp_path)
    pq = tmp_path / "retro_grades.parquet"
    monkeypatch.setattr("scripts.grade_us_board.RETRO_PARQUET", pq)

    first = _grade_df_with_spine(n=2, as_of="2026-01-02", horizon=5)
    _merge_into_store(first)
    original_mfe = float(first["fwd_mfe_5"].iloc[0])

    second = first.copy()
    second["fwd_mfe_5"] = 0.99                       # price-derived  -> frozen
    second["archetype"] = "coiled"                   # annotation     -> accrues
    result = _merge_into_store(second)

    assert len(result) == 2, "dedup should yield 2 rows"
    assert (result["fwd_mfe_5"] == original_mfe).all(), (
        "a price-derived spine column was restated")
    assert (result["archetype"] == "coiled").all(), (
        "annotations must still reach historical rows")


# ---------------------------------------------------------------------------
# W0.1 B-b — resolve_series survivorship path
# ---------------------------------------------------------------------------

def test_resolve_series_uses_dead_prices_when_live_absent():
    """W0.1 B-b: resolve_series returns the dead-name terminal when live cache is None."""
    from engine.grading import resolve_series

    idx = pd.bdate_range("2026-01-02", periods=10)
    dead_ser = pd.Series([1.0] * 10, index=idx)
    dead_prices = {"DELISTED": dead_ser}

    result = resolve_series("DELISTED", None, dead_prices=dead_prices)
    assert result is not None, "resolve_series should return dead series when live is None"
    assert len(result) == 10


def test_resolve_series_appends_dead_tail_to_live():
    """W0.1 B-b: resolve_series extends live series with dead-name terminal tail."""
    from engine.grading import resolve_series

    live_idx = pd.bdate_range("2026-01-02", periods=5)
    live_ser = pd.Series([100.0, 99.0, 98.0, 95.0, 90.0], index=live_idx)

    # Dead tail: 3 more bars after live ends
    dead_idx = pd.bdate_range("2026-01-09", periods=3)
    dead_ser = pd.Series([0.01, 0.01, 0.0], index=dead_idx)  # imputed terminal
    dead_prices = {"DELISTED": dead_ser}

    result = resolve_series("DELISTED", live_ser, dead_prices=dead_prices)
    assert result is not None
    assert len(result) == 8, f"expected 5+3=8 bars, got {len(result)}"
    assert result.iloc[-1] == 0.0, "last bar should be the imputed terminal (0.0)"


def test_survivorship_block_active_dead_store():
    """W0.1 B-b: _survivorship_block reports dead_store_active=True when store has tickers."""
    from scripts.grade_us_board import _survivorship_block
    import pandas as pd

    # Mock load_dead_prices to return 2 tickers
    with mock.patch("scripts.grade_us_board.load_dead_prices",
                    return_value={"DEAD1": pd.Series([0.0]), "DEAD2": pd.Series([0.0])}):
        names = pd.DataFrame({"ALIVE": [1.0, 1.1, 1.2]})
        boards = [{"as_of": "2026-01-02", "rows": [
            {"ticker": "ALIVE"}, {"ticker": "DEAD1"}, {"ticker": "MISSING"},
        ]}]
        block = _survivorship_block(boards, names)

    assert block["dead_store_active"] is True
    assert block["dead_store_tickers"] == 2
    # MISSING has no price anywhere → counts as skipped
    assert block["n_skipped_no_price"] == 1
    # DEAD1 is in dead store → recovered
    assert block["n_recovered_by_dead_store"] == 1


def test_grade_boards_uses_resolve_series(tmp_path):
    """W0.1 B-b: grade_boards routes through resolve_series to pick up dead-name prices."""
    from scripts.grade_us_board import grade_boards

    idx = pd.bdate_range("2026-01-02", periods=80)
    # A name that is in the dead store but NOT in the broad cache
    dead_ser = pd.Series([100.0 * (1.01**i) for i in range(80)], index=idx)
    spy_ser = pd.Series([100.0 * (1.005**i) for i in range(80)], index=idx)

    names_df = pd.DataFrame(dtype=float, index=idx)  # empty — no live names
    etfs_df = pd.DataFrame({"SPY": spy_ser}, index=idx)

    board = {
        "as_of": idx[0].date().isoformat(),
        "rank_by": "test",
        "rows": [{
            "ticker": "DEAD_NAME", "lane": "buy", "position": 0, "sector": "Technology",
            "alpha": 0.1, "score": 0.5, "band": "A", "composite_z": 1.0,
            "verdict": "ok", "align_tier": None, "urgency": "high",
            "state": "recovering", "entry_status": "ok", "act_level": 3,
            "signal_quality": "ok", "validation_status": "ok",
            "vol_squeeze": None, "dispersion_state": None,
            "spot_sector_etf": None, "off_high": -0.1,
            "coiled": False, "coiled_star": False, "coiled_cohort": None,
            "coiled_fire": False, "coiled_fire_ticks": None,
            "donor_state": None, "donor_sector": None,
            "hold_state": None, "hold_days": None, "hold_inv": None,
            "hold_anchor_src": None,
            "lane": "buy", "arbiter_note": None,
            "postcross_based": False, "postcross_armed": None,
            "postcross_shaken": False, "postcross_ticks": None,
            "insider_cluster": False, "gex_confirm_verdict": None,
            "altdata_conv_gte2": False, "sue_fresh": False,
            "news_burst": False, "smartmoney_add": False,
            "has_stop_guidance": False, "confluence_k": 0,
            "tier_cascade": None, "label": None, "trust_tier": None,
            "signal_last_type": None, "archetype": None,
        }],
    }

    with mock.patch("scripts.grade_us_board.load_dead_prices",
                    return_value={"DEAD_NAME": dead_ser}):
        with mock.patch("scripts.grade_us_board.get_vector_for_date",
                        return_value={k: None for k in [
                            "rate_pressure", "quad_hard_label", "fused_risk_label",
                            "vol_regime", "risk_radar_state", "regime_vector_degraded",
                            "vector_asof", "staleness_hours"]}):
            df = grade_boards([board], names_df, etfs_df)

    # DEAD_NAME should have been graded via the dead store (not skipped)
    assert len(df) > 0, "DEAD_NAME should have been graded via dead store"
    assert "DEAD_NAME" in df["ticker"].values, "DEAD_NAME missing from graded rows"
    assert df.attrs.get("skipped_no_price", 0) == 0, "DEAD_NAME should NOT be counted as skipped"


# ---------------------------------------------------------------------------
# W0.1 B-b — regime_vector PIT stamp + unstamped count
# ---------------------------------------------------------------------------

def test_regime_stamp_present_in_graded_df():
    """W0.1 B-b §3.4: regime stamp columns are present in the graded DataFrame."""
    df = _grade_df_with_spine(n=4, horizon=5)
    for col in _REGIME_STAMP_COLS:
        assert col in df.columns, f"regime stamp column {col!r} missing"


def test_backfill_regime_stamps_fills_null_rows():
    """W0.1 B-b: _backfill_regime_stamps fills rows where vector_asof is not None."""
    # Build a df with null regime stamps
    df = _grade_df_with_spine(n=3, as_of="2026-01-02", horizon=5)
    for col in _REGIME_STAMP_COLS:
        df[col] = None

    # Mock get_vector_for_date to return a stamped vector
    mock_stamp = {
        "rate_pressure": "rising",
        "quad_hard_label": "Q2",
        "fused_risk_label": "risk-on",
        "vol_regime": "low",
        "risk_radar_state": "green",
        "regime_vector_degraded": False,
        "vector_asof": "2026-01-02",
        "staleness_hours": 0.0,
    }
    with mock.patch("scripts.grade_us_board.get_vector_for_date", return_value=mock_stamp):
        result_df, n_stamped = _backfill_regime_stamps(df)

    assert n_stamped == 3, f"expected 3 newly stamped, got {n_stamped}"
    assert (result_df["rate_pressure"] == "rising").all()
    assert (result_df["vector_asof"] == "2026-01-02").all()


def test_backfill_regime_stamps_skips_uncovered_dates():
    """W0.1 B-b: _backfill_regime_stamps does NOT stamp rows where vector_asof is None."""
    df = _grade_df_with_spine(n=2, as_of="2020-01-02", horizon=5)
    for col in _REGIME_STAMP_COLS:
        df[col] = None

    # Mock: vector not available for this date
    null_stamp = {k: None for k in [
        "rate_pressure", "quad_hard_label", "fused_risk_label",
        "vol_regime", "risk_radar_state", "regime_vector_degraded",
        "vector_asof", "staleness_hours",
    ]}
    with mock.patch("scripts.grade_us_board.get_vector_for_date", return_value=null_stamp):
        result_df, n_stamped = _backfill_regime_stamps(df)

    assert n_stamped == 0, "should not stamp when vector_asof is None"
    assert result_df["rate_pressure"].isna().all()


def test_backfill_does_not_overwrite_existing_non_null():
    """W0.1 B-b: _backfill_regime_stamps only fills rows where ALL stamps are null.
    Constructs the test frame manually so that the partial-null situation (some rows
    stamped, some not) is representable without dtype coercion issues."""
    # Build two sub-frames: stamped (rows 0,1) and unstamped (rows 2,3)
    stamped_rows = [
        {
            "as_of": "2026-01-02", "entry_date": "2026-01-05", "rank_by": "test",
            "horizon": 5, "lane": "buy", "position": i,
            "ticker": f"TICK{i}", "sector": "Technology",
            "ret": 0.04, "spy_ret": 0.02, "excess_spy": 0.02,
            "mae_close_excess_spy": -0.01,
            "sector_etf": "XLK", "etf_ret": 0.015, "excess_sector": 0.01,
            "mae_close_excess_sector": -0.008,
            "rate_pressure": "rising",
            "quad_hard_label": "Q2",
            "fused_risk_label": "risk-on",
            "vol_regime": "low",
            "risk_radar_state": "green",
            "regime_vector_degraded": "false",  # string to avoid bool dtype
            "vector_asof": "2026-01-02",
            "staleness_hours": 0.0,
            "alpha": 0.1, "score": 0.5, "band": "A", "composite_z": 1.5,
            "verdict": "strong", "align_tier": None, "urgency": "high",
            "state": "coiled", "entry_status": "ok", "act_level": None,
            "signal_quality": "ok", "validation_status": "ok",
            "vol_squeeze": "yes", "dispersion_state": "low", "off_high": -0.05,
            "donor_state": None, "donor_sector": None,
            "hold_state": None, "hold_days": None, "hold_inv": None,
            "hold_anchor_src": None, "tier_cascade": "T1",
            "fwd_mfe_5": 0.08, "terminal_state_clean15_126": "CUSHIONED",
            "terminal_state_clean8_21": "STOPPED", "post_cushion_breach": True,
            "archetype": None,
        }
        for i in range(2)
    ]
    unstamped_rows = [
        {
            "as_of": "2026-01-02", "entry_date": "2026-01-05", "rank_by": "test",
            "horizon": 5, "lane": "buy", "position": i + 2,
            "ticker": f"TICK{i+2}", "sector": "Technology",
            "ret": 0.04, "spy_ret": 0.02, "excess_spy": 0.02,
            "mae_close_excess_spy": -0.01,
            "sector_etf": "XLK", "etf_ret": 0.015, "excess_sector": 0.01,
            "mae_close_excess_sector": -0.008,
            "rate_pressure": None,
            "quad_hard_label": None,
            "fused_risk_label": None,
            "vol_regime": None,
            "risk_radar_state": None,
            "regime_vector_degraded": None,
            "vector_asof": None,
            "staleness_hours": None,
            "alpha": 0.1, "score": 0.5, "band": "A", "composite_z": 1.5,
            "verdict": "strong", "align_tier": None, "urgency": "high",
            "state": "coiled", "entry_status": "ok", "act_level": None,
            "signal_quality": "ok", "validation_status": "ok",
            "vol_squeeze": "yes", "dispersion_state": "low", "off_high": -0.05,
            "donor_state": None, "donor_sector": None,
            "hold_state": None, "hold_days": None, "hold_inv": None,
            "hold_anchor_src": None, "tier_cascade": "T1",
            "fwd_mfe_5": 0.08, "terminal_state_clean15_126": "CUSHIONED",
            "terminal_state_clean8_21": "STOPPED", "post_cushion_breach": None,
            "archetype": None,
        }
        for i in range(2)
    ]
    df = pd.concat([pd.DataFrame(stamped_rows), pd.DataFrame(unstamped_rows)],
                   ignore_index=True)

    mock_stamp = {
        "rate_pressure": "flat", "quad_hard_label": "Q1",
        "fused_risk_label": "neutral", "vol_regime": "medium",
        "risk_radar_state": "yellow", "regime_vector_degraded": False,
        "vector_asof": "2026-01-02", "staleness_hours": 0.0,
    }
    with mock.patch("scripts.grade_us_board.get_vector_for_date", return_value=mock_stamp):
        result_df, n_stamped = _backfill_regime_stamps(df)

    assert n_stamped == 2, f"only 2 null rows should be stamped, got {n_stamped}"
    # Rows 0,1 keep their original stamp (rate_pressure="rising")
    assert result_df.loc[0, "rate_pressure"] == "rising"
    assert result_df.loc[1, "rate_pressure"] == "rising"
    # Rows 2,3 get the new stamp
    assert result_df.loc[2, "rate_pressure"] == "flat"
    assert result_df.loc[3, "rate_pressure"] == "flat"


# ---------------------------------------------------------------------------
# 2026-08-04 — species_id retirement + archetype wiring
# ---------------------------------------------------------------------------

_ARCH_ASOF = "engine.neuralweb.context_api.archetype_asof"


def _archetype_boards(as_of, *, payload_archetype):
    """One board date, one row, with the payload archetype under test."""
    return [{
        "as_of": as_of, "rank_by": "test",
        "rows": [{
            "ticker": "ARCH", "lane": "buy", "position": 0, "sector": "Technology",
            "spot_sector_etf": None, "archetype": payload_archetype,
        }],
    }]


def _run_grade_boards(boards):
    """Grade `boards` against a synthetic 80-bar price history (no wall clock)."""
    idx = pd.bdate_range("2026-01-02", periods=80)
    names_df = pd.DataFrame(
        {"ARCH": pd.Series([100.0 * (1.01 ** i) for i in range(80)], index=idx)}, index=idx)
    etfs_df = pd.DataFrame(
        {"SPY": pd.Series([100.0 * (1.005 ** i) for i in range(80)], index=idx)}, index=idx)
    with mock.patch("scripts.grade_us_board.load_dead_prices", return_value={}), \
         mock.patch("scripts.grade_us_board.get_vector_for_date",
                    return_value={k: None for k in _REGIME_STAMP_COLS}):
        return grade_boards(boards, names_df, etfs_df)


# ── species_id retirement ────────────────────────────────────────────────────

def test_graded_frame_carries_no_retired_column(monkeypatch):
    """The rec dict no longer emits species_id (retired 2026-08-04)."""
    monkeypatch.setattr(_ARCH_ASOF, lambda ticker, date, root=None: None)
    df = _run_grade_boards(_archetype_boards("2026-01-02", payload_archetype=None))
    assert not df.empty, "harness produced no matured rows"
    for col in _RETIRED_LEDGER_COLS:
        assert col not in df.columns, f"retired column {col!r} is still written by grade_boards"


def test_merge_drops_retired_column_from_legacy_store(tmp_path, monkeypatch):
    """The store-merge carry path sheds species_id — by NAME, not by null-ness.

    The seeded value is NON-NULL on purpose: a drop implemented as "remove all-null
    columns" would pass with a null seed and leave the real store untouched.
    """
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", tmp_path)
    pq = tmp_path / "retro_grades.parquet"
    monkeypatch.setattr("scripts.grade_us_board.RETRO_PARQUET", pq)

    legacy = _minimal_grade_df(as_of="2026-01-01", n=3)
    legacy["species_id"] = "S-LEGACY"
    legacy.to_parquet(pq, index=False)

    result = _merge_into_store(_minimal_grade_df(as_of="2026-01-10", n=2))

    assert len(result) == 5, "legacy + fresh rows must both survive the drop"
    assert "species_id" not in result.columns, "retired column survived the merge"
    assert "species_id" not in pd.read_parquet(pq).columns, "retired column was written back"


def test_merge_empty_fresh_also_sheds_retired_column(tmp_path, monkeypatch):
    """A night that matures no new rows returns the store — it must be shed there too."""
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", tmp_path)
    pq = tmp_path / "retro_grades.parquet"
    monkeypatch.setattr("scripts.grade_us_board.RETRO_PARQUET", pq)

    legacy = _minimal_grade_df(as_of="2026-01-01", n=3)
    legacy["species_id"] = "S-LEGACY"
    legacy.to_parquet(pq, index=False)

    result = _merge_into_store(pd.DataFrame())

    assert len(result) == 3, "the empty-fresh path must still return the accumulated store"
    assert "species_id" not in result.columns, (
        "the fresh.empty early return handed a retired column downstream"
    )


# ── archetype: payload first, else PIT ───────────────────────────────────────

def test_archetype_pit_returns_store_label(monkeypatch):
    monkeypatch.setattr(_ARCH_ASOF, lambda ticker, date, root=None: "rate_sensitive")
    assert _archetype_pit("AAPL", "2026-07-01") == "rate_sensitive"


def test_archetype_pit_none_when_reader_finds_nothing(monkeypatch):
    monkeypatch.setattr(_ARCH_ASOF, lambda ticker, date, root=None: None)
    assert _archetype_pit("NOSUCH", "2026-07-01") is None


def test_archetype_payload_wins_over_pit(monkeypatch):
    """A payload archetype is authoritative — the PIT store is the fallback, not an override."""
    monkeypatch.setattr(_ARCH_ASOF, lambda ticker, date, root=None: "STORE_ARCH")
    df = _run_grade_boards(_archetype_boards("2026-01-02", payload_archetype="PAYLOAD_ARCH"))
    assert not df.empty
    assert (df["archetype"] == "PAYLOAD_ARCH").all()


def test_archetype_falls_back_to_pit_when_payload_absent(monkeypatch):
    """The payload has never carried the field, so this is the leg that populates it."""
    seen = []

    def _fake(ticker, date, root=None):
        seen.append((ticker, date))
        return "STORE_ARCH"

    monkeypatch.setattr(_ARCH_ASOF, _fake)
    df = _run_grade_boards(_archetype_boards("2026-01-02", payload_archetype=None))
    assert not df.empty
    assert (df["archetype"] == "STORE_ARCH").all()
    # PIT: the lookup date is the board's own as_of, never a wall clock
    assert seen and all(d == "2026-01-02" for _t, d in seen), seen


# ── archetype backfill over existing rows ────────────────────────────────────

def test_backfill_archetype_fills_only_null_rows(monkeypatch):
    """Fill-null-only, per-row PIT, and a name the store cannot classify stays null."""
    seen = []

    def _fake(ticker, date, root=None):
        seen.append((ticker, date))
        return {"COVERED": "STORE_ARCH"}.get(ticker)

    monkeypatch.setattr(_ARCH_ASOF, _fake)

    df = pd.DataFrame([
        {"as_of": "2026-01-02", "ticker": "COVERED", "lane": "buy", "horizon": 5,
         "archetype": None},
        {"as_of": "2026-01-02", "ticker": "PINNED", "lane": "buy", "horizon": 5,
         "archetype": "PAYLOAD_ARCH"},
        {"as_of": "2026-01-09", "ticker": "UNKNOWN", "lane": "buy", "horizon": 5,
         "archetype": None},
    ])

    out, n_filled = _backfill_archetype(df)

    assert n_filled == 1, f"only the covered null row should fill, got {n_filled}"
    assert out.at[0, "archetype"] == "STORE_ARCH"
    assert out.at[1, "archetype"] == "PAYLOAD_ARCH", "a non-null archetype was overwritten"
    assert pd.isna(out.at[2, "archetype"]), "an uncovered name must stay null, never guessed"
    # the non-null row is never even queried; each queried row uses its OWN as_of
    assert ("PINNED", "2026-01-02") not in seen
    assert ("COVERED", "2026-01-02") in seen
    assert ("UNKNOWN", "2026-01-09") in seen


def test_backfill_archetype_is_idempotent(monkeypatch):
    """A second pass over the same frame fills nothing (no churn, no rewrite)."""
    monkeypatch.setattr(_ARCH_ASOF, lambda ticker, date, root=None: "STORE_ARCH")
    df = pd.DataFrame([
        {"as_of": "2026-01-02", "ticker": "COVERED", "lane": "buy", "horizon": 5,
         "archetype": None},
    ])
    out1, n1 = _backfill_archetype(df)
    out2, n2 = _backfill_archetype(out1)
    assert (n1, n2) == (1, 0)
    assert out2.at[0, "archetype"] == "STORE_ARCH"


def test_backfill_archetype_noop_without_the_column():
    """A legacy frame with no archetype column is left alone (schema-union owns that)."""
    df = pd.DataFrame([{"as_of": "2026-01-02", "ticker": "T", "lane": "buy", "horizon": 5}])
    out, n = _backfill_archetype(df)
    assert n == 0
    assert "archetype" not in out.columns


# ── disclosed null eras: the hole that must NOT be repaired by backfilling ────
#
# data/us_board_ledger/snapshots.jsonl has no rows for 2026-08-03..08-06. That
# looks exactly like an outage someone should fix, and the obvious fix — backfill
# the dates — is the WRONG action, because the board published on those days but
# ranked on factors frozen at 2026-07-31.
#
# scripts/build_stock_library.py:3850 ranks by alpha
# (`rank_setups(cand, as_of=alpha_asof, rank_by="alpha", ...)`), and every
# site/factordata/alpha.json revision from 2026-07-31T20:35Z to 2026-08-06T16:36Z
# carries as_of=2026-07-31 — one distinct value across the whole window. So those
# boards ordered names by six-day-stale factors while pricing entry zones off
# current data. Grading them would teach Prophet from that hybrid.
#
# Operator adjudication 2026-08-07: disclosed null era, no graded entries. These
# tests are what make the disclosure load-bearing rather than prose — filling the
# window turns them red and forces a conscious decision.

import json as _json  # noqa: E402

_LEDGER_DIR = Path(__file__).resolve().parents[1] / "data" / "us_board_ledger"
_DISCLOSED_GAPS = _LEDGER_DIR / "disclosed_gaps.json"
_SNAPSHOTS = _LEDGER_DIR / "snapshots.jsonl"


def _gaps() -> list[dict]:
    doc = _json.loads(_DISCLOSED_GAPS.read_text())
    assert doc.get("schema_version"), "disclosed_gaps.json must carry a schema_version"
    return doc.get("gaps") or []


def _snapshot_dates() -> set[str]:
    out = set()
    for line in _SNAPSHOTS.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.add(str(_json.loads(line).get("as_of"))[:10])
        except Exception:  # noqa: BLE001 — a malformed line is not this test's subject
            continue
    return out


def test_the_disclosed_null_era_is_declared_with_its_reason():
    """A gap with no stated reason is indistinguishable from an unnoticed outage."""
    gaps = _gaps()
    assert gaps, "disclosed_gaps.json lists no gaps — did the file get truncated?"
    frozen = [g for g in gaps if g.get("id") == "us-board-frozen-alpha-2026-08"]
    assert frozen, "the 2026-08 frozen-alpha era must stay declared"
    g = frozen[0]
    assert g["gradeable"] is False
    assert g["backfillable"] is False
    assert g["missing_trading_days"] == [
        "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"
    ]
    # the reason must name the MECHANISM, not just assert badness
    assert "rank_by" in g["why_not_gradeable"] or "alpha" in g["why_not_gradeable"]
    assert g["adjudication"]["by"] == "operator"


def test_no_graded_rows_were_backfilled_into_a_disclosed_null_era():
    """THE load-bearing assertion: the hole must stay a hole.

    If a future session 'repairs' the gap by backfilling snapshots for those dates,
    this goes red. That is the point — the window is not missing data, it is data
    that must not be graded, and reopening it needs a NEW board_definition era (a
    re-ranked board is a different admission rule from the one that published).
    """
    dates = _snapshot_dates()
    for g in _gaps():
        if g.get("gradeable") is not False:
            continue
        intruders = sorted(set(g["missing_trading_days"]) & dates)
        assert not intruders, (
            f"snapshots.jsonl now carries rows for {intruders}, which sit inside the "
            f"disclosed null era {g['id']!r} ({g['headline']}). Those days are not "
            f"gradeable: {g['why_not_gradeable'][:160]}... If this backfill is "
            f"deliberate, it needs a NEW board_definition era stamp and this gap "
            f"record must be amended in the same change — do not just delete the test."
        )


def test_the_disclosed_window_is_still_absent_from_the_ledger():
    """Guards the guard: if snapshots.jsonl ever loses its 07-31 anchor the test above
    could pass vacuously against an empty file."""
    dates = _snapshot_dates()
    assert len(dates) >= 17, f"snapshots.jsonl shrank to {len(dates)} dates — read it before trusting the gap assertions"
    assert "2026-07-31" in dates, "the pre-gap anchor date is missing; the ledger changed shape"


# ---------------------------------------------------------------------------
# ERA PARTITION — us_prophet_v1 -> v2 (2026-08-10)
# ---------------------------------------------------------------------------
class TestErasAreNeverPooled:
    """`build_track` must never sum two board_definitions into one headline aggregate.

    WHY THIS IS A TEST AND NOT A CONVENTION.  The reclaim-veto conditional waiver
    (research/RECLAIM_VETO_CONDITIONAL_PREREG.md §4 Arm P, ratified 2026-08-10) changed
    what the US board ADMITS, so `engine.us_board_rank.BOARD_DEFINITION` moved
    us_prophet_v1 -> us_prophet_v2 and the two are different products.  The stamp already
    rode on every graded row as `rank_by`, and the old aggregates DISCLOSED the mixture
    (`rank_by_of_matured_boards`) without undoing it — a footnote, not a fence.  The
    prereg's sentence "their forward ledgers never pool" has to be true in code at ship
    time; these assertions are that.

    THE FIXTURE IS BUILT TO MAKE POOLING VISIBLE: every v1 row is a winner and every v2 row
    is a loser, so a pooled headline reads 0.6 on this frame while neither era does.  A
    reimplementation that narrows or drops the partition cannot pass these by accident.
    """

    _V1, _V2 = "us_prophet_v1", "us_prophet_v2"
    _V2_DATE = "2026-07-15"

    @classmethod
    def _mixed(cls, n_v1=6, n_v2=4):
        """One graded frame carrying two eras: v1 all winners, v2 all losers."""
        v1 = _minimal_grade_df(as_of=_IN_ERA, n=n_v1, lane="buy")
        v1["rank_by"] = cls._V1
        v1["excess_spy"] = 0.05                        # every v1 row beats SPY
        v1["excess_sector"] = 0.04
        v2 = _minimal_grade_df(as_of=cls._V2_DATE, n=n_v2, lane="buy")
        v2["rank_by"] = cls._V2
        v2["excess_spy"] = -0.05                       # every v2 row loses to SPY
        v2["excess_sector"] = -0.04
        return pd.concat([v1, v2], ignore_index=True)

    @classmethod
    def _track(cls, **kw):
        return build_track(cls._mixed(**kw),
                           _boards_stub(_IN_ERA, cls._V2_DATE), _names_stub())

    # -- the partition exists and is complete --------------------------------
    def test_two_eras_produce_two_independent_aggregate_blocks(self):
        track = self._track()
        got = [d["board_definition"] for d in track["definitions"]]
        assert got == [self._V1, self._V2], (
            f"expected both eras, ordered by first graded date: {got}")
        by_def = {d["board_definition"]: d for d in track["definitions"]}
        assert by_def[self._V1]["graded_rows_total"] == 6
        assert by_def[self._V2]["graded_rows_total"] == 4
        assert by_def[self._V1]["graded_dates"] == [_IN_ERA]
        assert by_def[self._V2]["graded_dates"] == [self._V2_DATE]

    def test_each_eras_hit_rate_is_its_own(self):
        """The fixture's whole point: 1.0 and 0.0, never the 0.6 a pool would report."""
        by_def = {d["board_definition"]: d for d in self._track()["definitions"]}
        v1 = by_def[self._V1]["per_horizon"]["h5"]["buy_lane"]["vs_spy"]
        v2 = by_def[self._V2]["per_horizon"]["h5"]["buy_lane"]["vs_spy"]
        assert (v1["hit_rate"], v1["n"]) == (1.0, 6)
        assert (v2["hit_rate"], v2["n"]) == (0.0, 4)
        assert v1["hit_rate"] != v2["hit_rate"], "fixture no longer separates the eras"

    def test_every_block_discloses_only_its_own_stamp(self):
        """`rank_by_of_matured_boards` inside an era block must name exactly that era — a
        block listing both stamps is a pooled block wearing a partition's label."""
        for d in self._track()["definitions"]:
            listed = d["per_horizon"]["h5"]["buy_lane"]["rank_by_of_matured_boards"]
            assert listed == [d["board_definition"]], (d["board_definition"], listed)

    # -- the headline is ONE era, and provably not the pool -------------------
    def test_the_headline_is_the_live_era_not_a_pool(self):
        track = self._track()
        assert track["era_scope"]["board_definition"] == ubr.BOARD_DEFINITION
        assert track["era_scope"]["pooled"] is False
        assert track["era_scope"]["headline_is_superseded"] is False
        assert track["era_scope"]["definitions_present"] == [self._V1, self._V2]
        live = next(d for d in track["definitions"]
                    if d["board_definition"] == ubr.BOARD_DEFINITION)
        assert track["per_horizon"] == live["per_horizon"], (
            "the top-level block must BE one era's block, not a recomputation over both")

    def test_narrowing_the_partition_would_red_this(self):
        """THE MUTATION PIN.  Compute what a pooled headline WOULD say and require the
        published one to differ, in both `n` and `hit_rate`.  Widen the headline slice back
        to the whole frame — the pre-2026-08-10 behaviour — and this fails immediately,
        which is the only way a "never pool" rule survives the next refactor."""
        df = self._mixed()
        track = build_track(df, _boards_stub(_IN_ERA, self._V2_DATE), _names_stub())
        published = track["per_horizon"]["h5"]["buy_lane"]["vs_spy"]
        pooled = _hit_stats(df[(df["horizon"] == 5) & (df["lane"] == "buy")], "excess_spy")
        assert (pooled["n"], pooled["hit_rate"]) == (10, 0.6), (
            f"the pooled counterfactual stopped being distinguishable: {pooled}")
        assert published["n"] != pooled["n"], (
            f"the headline counts {published['n']} rows and a pool counts {pooled['n']} — "
            "they must not be the same number, or the eras are being summed")
        assert published["hit_rate"] != pooled["hit_rate"], (
            f"headline hit_rate {published['hit_rate']} equals the pooled "
            f"{pooled['hit_rate']} — the partition is not doing anything")
        assert (published["n"], published["hit_rate"]) == (4, 0.0)

    def test_the_era_row_counts_are_a_true_partition(self):
        """Every graded row lands in exactly one block: no double-counting, no orphans."""
        track = self._track()
        assert sum(d["graded_rows_total"] for d in track["definitions"]) == \
            track["graded_rows_total"] == 10
        assert all(d["graded_rows_total"] < track["graded_rows_total"]
                   for d in track["definitions"]), "an era block swallowed the whole frame"

    # -- the awkward states, stated rather than papered over ------------------
    def test_a_pre_bump_frame_publishes_the_superseded_era_and_says_so(self):
        """The nights between an era bump and its first matured row: the live block does
        not exist yet, so the headline is the newest era PRESENT — labelled superseded,
        never silently passed off as the current board's record."""
        df = _minimal_grade_df(as_of=_IN_ERA, n=5, lane="buy")
        df["rank_by"] = self._V1
        track = build_track(df, _boards_stub(_IN_ERA), _names_stub())
        assert track["era_scope"]["board_definition"] == self._V1
        assert track["era_scope"]["live_board_definition"] == ubr.BOARD_DEFINITION
        assert track["era_scope"]["headline_is_superseded"] is True
        assert track["era_scope"]["pooled"] is False

    def test_a_null_stamp_does_not_open_a_phantom_era(self):
        """A null/NaN/'None' `rank_by` IS the legacy era.  Left unnormalised it opens its
        own 'nan' block and splits one era's sample in two — the exact defect
        engine.cn_prophet_audit.norm_definition exists to prevent."""
        for raw in (None, float("nan"), "", "None", "nan", "legacy"):
            assert _norm_definition(raw) == "legacy", raw
        assert _norm_definition("us_prophet_v1") == "us_prophet_v1"
        assert _norm_definition("alpha") == "alpha", (
            "'alpha' is the US board's real pre-ranker stamp, not a null spelling")

    def test_the_live_stamp_is_read_from_the_producer(self):
        """A hand-copied literal here would point the headline at a dead era the day the
        constant next moves — the #4509 shape."""
        assert _live_definition() == ubr.BOARD_DEFINITION
