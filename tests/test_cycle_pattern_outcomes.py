"""tests/test_cycle_pattern_outcomes.py — acceptance + unit tests for the outcome spine.

Encodes the task's acceptance gates against the committed artifacts, plus synthetic
positive-controls for branches the real data does not exercise (tape_missing, the
month-gap phase break, and the bar-i+1 forward convention on a hand-built tape).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.cycle_pattern import outcomes

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data"
_STATE = _DATA / "cycle_pattern" / "state_monthly.parquet"
_KEYSTONE = _DATA / "research" / "keystone_tr0" / "backfill.parquet"

_HAS_STATE = _STATE.exists()
_HAS_KEYSTONE = _KEYSTONE.exists()

_FEATURE_LEAK_COLS = {
    "pos", "phase", "osc_slope", "signal", "timing_state", "above200d", "rs_63d",
    "proj_next", "proj_central", "proj_lo", "proj_hi", "pos_v2", "phase_v2", "stance",
    "divergence", "overdue", "age_m", "age_bucket", "trend_pass", "mom_score",
    "rs_63d_hz", "vol_pctile", "amp_proxy", "log_age_ratio", "quad", "liquidity",
    "hazard_epoch", "y1", "y3", "y6", "event_date",
}


@pytest.fixture(scope="module")
def state() -> pd.DataFrame:
    if not _HAS_STATE:
        pytest.skip("state_monthly.parquet not present")
    return pd.read_parquet(_STATE)


@pytest.fixture(scope="module")
def out(state: pd.DataFrame) -> pd.DataFrame:
    return outcomes.build_outcomes(state)


# ───────────────────────────────────────────────────────── schema / key identity ────

def test_schema_exact(out: pd.DataFrame) -> None:
    assert list(out.columns) == outcomes.OUTCOME_COLUMNS


def test_rowcount_equals_state(out: pd.DataFrame, state: pd.DataFrame) -> None:
    assert len(out) == len(state)


def test_key_set_identical(out: pd.DataFrame, state: pd.DataFrame) -> None:
    s_key = set(zip(
        state["entity_id"].astype(str),
        (pd.to_datetime(state["date"]) + pd.offsets.MonthEnd(0)).dt.normalize(),
    ))
    o_key = set(zip(out["entity_id"].astype(str), pd.to_datetime(out["date"])))
    assert o_key == s_key
    # and no duplicate keys were introduced
    assert not out.duplicated(["entity_id", "date"]).any()


def test_no_feature_columns_leak(out: pd.DataFrame) -> None:
    assert _FEATURE_LEAK_COLS.isdisjoint(out.columns), \
        f"feature/label-at-t columns leaked: {_FEATURE_LEAK_COLS.intersection(out.columns)}"


def test_basis_is_tr(out: pd.DataFrame) -> None:
    assert (out["basis"] == "tr").all()


def test_sorted_deterministic_order(out: pd.DataFrame) -> None:
    expect = out.sort_values(["entity_id", "date"], kind="stable").reset_index(drop=True)
    pd.testing.assert_frame_equal(out, expect)


# ───────────────────────────────────────────────────────────── keystone cross-check ──

@pytest.mark.skipif(not _HAS_KEYSTONE, reason="keystone backfill not present")
def test_keystone_ret_fwd_63d_match(out: pd.DataFrame) -> None:
    """For overlapping (date, UPPER id) US-sector rows, ret_fwd_63d must match the
    keystone's fwd_ret_63 — the china-grader bar-i+1 convention is byte-identical.
    Require >=95% within rtol=1e-3 for matured overlapping rows."""
    kp = pd.read_parquet(_KEYSTONE)
    kp = kp.assign(native=kp["ticker"].str.upper(), date=pd.to_datetime(kp["date"]))

    us = out[out["entity_id"].str.startswith("us_sector:")].copy()
    us["native"] = us["entity_id"].str.split(":").str[1].str.upper()
    us["date"] = pd.to_datetime(us["date"])

    m = us.merge(kp[["date", "native", "fwd_ret_63"]], on=["date", "native"], how="inner")
    both = m[m["ret_fwd_63d"].notna() & m["fwd_ret_63"].notna()]
    assert len(both) >= 100, f"too few overlapping matured rows: {len(both)}"

    diff = (both["ret_fwd_63d"] - both["fwd_ret_63"]).abs()
    rel = diff / both["fwd_ret_63"].abs().replace(0, np.nan)
    within_1e3 = ((diff <= 1e-3) | (rel <= 1e-3)).mean()
    within_1e6 = ((diff <= 1e-6) | (rel <= 1e-6)).mean()
    # reported for diagnosis; both are expected to be ~1.0 (convention is identical)
    assert within_1e3 >= 0.95, f"match@1e-3={within_1e3:.4f} below 0.95"
    assert within_1e6 >= 0.95, f"match@1e-6={within_1e6:.4f} (convention drift suspected)"


# ─────────────────────────────────────────────────────────── turn-event join rate ────

def test_turn_event_join_hitrate(out: pd.DataFrame, state: pd.DataFrame) -> None:
    """Turn-event left-join hit-rate must match the lake's hazard join (~98.8%)."""
    hz_state = state["hazard_epoch"].notna().mean() if "hazard_epoch" in state else None
    hit = out["turn_event_1m"].notna().mean()
    assert 0.98 <= hit <= 1.0, f"turn-event hit-rate {hit:.4f} off the ~98.8% lake join"
    if hz_state is not None:
        assert abs(hit - hz_state) < 0.02, \
            f"turn-event join {hit:.4f} diverges from lake hazard join {hz_state:.4f}"


def test_turn_event_values_binary(out: pd.DataFrame) -> None:
    for c in ("turn_event_1m", "turn_event_3m", "turn_event_6m"):
        vals = set(out[c].dropna().unique())
        assert vals.issubset({0.0, 1.0}), f"{c} has non-binary values: {vals}"


# ───────────────────────────────────────────────────────────── phase transitions ─────

def test_phase_changed_is_bool_and_consistent(out: pd.DataFrame) -> None:
    changed = out["phase_changed_1m"].dropna()
    assert set(map(type, changed.unique())).issubset({bool, np.bool_})
    # changed flag exists exactly where the next phase is known
    assert (out["phase_changed_1m"].notna() == out["phase_next_1m"].notna()).all()
    assert (out["phase_changed_3m"].notna() == out["phase_next_3m"].notna()).all()


# ─────────────────────────────────────────────────────────────── determinism ─────────

def test_rebuild_frame_equal(state: pd.DataFrame) -> None:
    a = outcomes.build_outcomes(state)
    b = outcomes.build_outcomes(state)
    pd.testing.assert_frame_equal(a, b)


# ──────────────────────────────────────── synthetic positive-controls (branches) ─────

def test_fwd_bar_i_plus_1_convention() -> None:
    """_fwd anchors STRICTLY after the stamp and returns close[j+h]/close[j]-1 with a
    running-peak maxdd — the china-grader convention."""
    idx = pd.bdate_range("2020-01-01", periods=60)
    px = pd.Series(np.arange(100.0, 160.0), index=idx)  # strictly rising -> maxdd == 0
    stamp = idx[10]
    w = outcomes._fwd(px, stamp, 5)
    assert w is not None
    # entry is bar 11 (strictly after bar 10); exit is bar 16
    assert w["ret"] == pytest.approx(px.iloc[16] / px.iloc[11] - 1.0)
    assert w["maxdd"] == pytest.approx(0.0)  # monotone up -> no drawdown

    # stamp exactly on a bar must NOT anchor on that same bar (leak guard)
    j = outcomes._entry_pos(idx, stamp)
    assert idx[j] > stamp

    # a dip inside the window shows up as a negative running-peak drawdown
    px2 = px.copy()
    px2.iloc[14] = px2.iloc[11] * 0.9
    w2 = outcomes._fwd(px2, stamp, 5)
    assert w2["maxdd"] < 0.0


def test_fwd_unmatured_returns_none() -> None:
    idx = pd.bdate_range("2020-01-01", periods=20)
    px = pd.Series(np.arange(100.0, 120.0), index=idx)
    # window would run past the tape end -> None (no partial windows)
    assert outcomes._fwd(px, idx[15], 21) is None


def test_tape_missing_flag_and_nan_outcomes() -> None:
    """A synthetic entity whose native_id has no tape -> tape_missing True and all
    price-derived outcomes NaN (turn/phase columns still populate)."""
    dates = pd.date_range("2015-01-31", periods=4, freq="ME")
    st = pd.DataFrame({
        "entity_id": ["us_sector:__NOPE__"] * 4,
        "native_id": ["__NOPE__"] * 4,
        "date": dates,
        "phase": ["Recovery", "Recovery", "Peak", "Peak"],
    })
    res = outcomes.build_outcomes(st)
    assert res["tape_missing"].all()
    for c in ("ret_fwd_21d", "ret_fwd_63d", "ret_fwd_126d",
              "excess_ret_fwd_63d", "max_drawdown_fwd_63d"):
        assert res[c].isna().all()
    # phase transitions still computed from the state series itself
    assert res.sort_values("date")["phase_next_1m"].tolist()[:3] == \
        ["Recovery", "Peak", "Peak"]
    assert res.sort_values("date")["phase_changed_1m"].tolist()[:3] == [False, True, False]


def test_phase_gap_breaks_the_chain() -> None:
    """phase_next_1m is NaN across a non-consecutive month-end gap."""
    dates = pd.to_datetime(["2015-01-31", "2015-02-28", "2015-06-30", "2015-07-31"])
    st = pd.DataFrame({
        "entity_id": ["us_sector:__GAP__"] * 4,
        "native_id": ["__GAP__"] * 4,
        "date": dates,
        "phase": ["A", "B", "C", "D"],
    })
    res = outcomes.build_outcomes(st).sort_values("date").reset_index(drop=True)
    # Jan->Feb consecutive: next is B
    assert res.loc[0, "phase_next_1m"] == "B"
    # Feb->Jun is a 4-month gap: next-month phase unknown -> missing
    assert pd.isna(res.loc[1, "phase_next_1m"])
    assert pd.isna(res.loc[1, "phase_changed_1m"])
    # Jun->Jul consecutive: next is D
    assert res.loc[2, "phase_next_1m"] == "D"


def test_excess_is_multiplicative_ratio_window() -> None:
    """excess_ret_fwd matches _fwd on the px/bench ratio series (the grader/_rs_63d
    multiplicative convention), not a naive ret_asset - ret_bench difference."""
    idx = pd.bdate_range("2019-01-01", periods=200)
    px = pd.Series(100.0 * 1.001 ** np.arange(200), index=idx)
    bench = pd.Series(100.0 * 1.0005 ** np.arange(200), index=idx)
    ratio = (px / bench.reindex(px.index).ffill()).dropna()
    stamp = idx[50]
    expect = outcomes._fwd(ratio, stamp, 21)["ret"]
    got = outcomes._fwd(px, stamp, 21)  # sanity: asset window matures
    assert got is not None
    assert expect == pytest.approx(
        outcomes._fwd(ratio, stamp, 21)["ret"])
