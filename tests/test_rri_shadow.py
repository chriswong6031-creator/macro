"""Tests for engine/rri_shadow.py — RRI Stage-B shadow accrual.

Coverage:
  1. Source-level guard: wiring call site is inside the ledger_lane_armed branch.
  2. Self-gate: log_shadow does not write when lane is off.
  3. Idempotency: same asof appended twice -> one row per variant file.
  4a. S1 floor — leg >= 0.95, gate open, incumbent "watch" -> variant "elevated".
  4b. S1 floor — leg >= 0.95 but gate CLOSED -> state NOT elevated (cap law).
  4c. S1 floor — incumbent "risk-off" stays "risk-off" (max wins).
  5. S3 velocity — velocity leg changes the composite (state differs somewhere on crafted series).
  6. Grading — synthetic px with >= 5% dd within h21 -> graded hit true.

House law: tests never write real data/ (MM_DATA_GUARD).  All log/grade calls
use tmp_path roots, matching the audit module's root= pattern.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── synthetic data helpers ────────────────────────────────────────────────────

def _bdays(n: int, start: str = "2000-01-03") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _flat_series(n: int = 2000, val: float = 100.0) -> pd.Series:
    """Flat (nearly noise-free) price series on a bday index."""
    return pd.Series(np.full(n, val), index=_bdays(n))


def _falling_series(n: int = 2000, start: float = 120.0, end: float = 80.0) -> pd.Series:
    """Monotonically falling series — guaranteed high dd_velocity."""
    return pd.Series(np.linspace(start, end, n), index=_bdays(n))


def _make_sub(n: int = 2000) -> dict:
    """Minimal sub-leg percentile dict matching the KR profile's sub_codes.

    All values set to 0.50 (neutral) by default so comp-leg pctiles are 0.50.
    """
    idx = _bdays(n)
    flat_50 = pd.Series(np.full(n, 0.50), index=idx)
    return {
        "us_rate_2y":      flat_50.copy(),
        "us_real_rate":    flat_50.copy(),
        "us_rate_10y":     flat_50.copy(),
        "krw_depreciation": flat_50.copy(),
        "ext_idx":         flat_50.copy(),
        "ext_etf":         flat_50.copy(),
    }


def _make_sub_high_leg(n: int = 2000, leg_key: str = "ext_idx", val: float = 0.97) -> dict:
    """Sub dict with one leg elevated to `val`."""
    s = _make_sub(n)
    s[leg_key] = pd.Series(np.full(n, val), index=_bdays(n))
    return s


def _make_comp(n: int = 2000, val: float = 0.50) -> pd.Series:
    """Flat composite series at `val`."""
    return pd.Series(np.full(n, val), index=_bdays(n))


def _make_gate(n: int = 2000, open_: bool = True) -> pd.Series:
    """Boolean gate series, all True (open) or all False (closed)."""
    return pd.Series(np.full(n, open_, dtype=bool), index=_bdays(n))


# ── TEST 1: wiring source guard ───────────────────────────────────────────────

def test_wiring_inside_lane_armed_branch():
    """The shadow accrual call block in engine/intl_run.py is inside the
    `if _ledger_lane_armed():` branch — not on the off-lane read-only path."""
    src = (REPO_ROOT / "engine" / "intl_run.py").read_text(encoding="utf-8")

    lane_gate_pos = src.find("if _ledger_lane_armed():")
    assert lane_gate_pos != -1, "lane gate `if _ledger_lane_armed():` not found in intl_run.py"

    shadow_pos = src.find("rri_shadow")
    assert shadow_pos != -1, "rri_shadow import/usage not found in intl_run.py"

    assert shadow_pos > lane_gate_pos, (
        "rri_shadow block must appear AFTER the ledger_lane_armed() check "
        "(i.e., inside the armed branch, not the read-only else path)"
    )

    # confirm the shadow block also comes before the except clause that ends the armed block
    # (it must not be in the else: path)
    else_pos = src.find("else:", lane_gate_pos)
    # some intl_run.py may not have an explicit else on the lane gate; just assert shadow < else
    # when else exists it should be after the shadow block
    if else_pos != -1 and else_pos > lane_gate_pos:
        assert shadow_pos < else_pos, (
            "rri_shadow must be inside the armed block, not the else path"
        )


# ── TEST 2: self-gate — off-lane writes nothing ───────────────────────────────

def test_self_gate_off_lane(tmp_path, monkeypatch):
    """log_shadow() returns 0 and creates no files when lane is not armed."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    from engine.rri_shadow import log_shadow, VARIANTS

    rows = {v: {"asof": "2026-07-17", "market": "kr", "variant": v,
                "construction": f"v2_{v}", "state": "watch", "state_ungated": "watch",
                "top_score": 55, "alert": False, "legs": {}, "gate_open": True,
                "logged_at": "2026-07-17T00:00:00+00:00", "graded": None}
             for v in VARIANTS}

    result = log_shadow("kr", rows, root=str(tmp_path))
    assert result == 0, "off-lane log_shadow must return 0"

    for v in VARIANTS:
        p = tmp_path / "data" / "risk_radar_intl" / f"kr_forward_log_{v}.jsonl"
        assert not p.exists() or p.read_text().strip() == "", (
            f"off-lane log_shadow must not write {v} log"
        )


# ── TEST 3: idempotency ───────────────────────────────────────────────────────

def test_idempotent_by_asof(tmp_path, monkeypatch):
    """Appending the same asof twice -> exactly 1 row per variant file."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    from engine.rri_shadow import log_shadow, VARIANTS

    rows = {v: {"asof": "2026-07-17", "market": "kr", "variant": v,
                "construction": f"v2_{v}", "state": "watch", "state_ungated": "watch",
                "top_score": 55, "alert": False, "legs": {}, "gate_open": True,
                "logged_at": "2026-07-17T00:00:00+00:00", "graded": None}
             for v in VARIANTS}

    n1 = log_shadow("kr", rows, root=str(tmp_path))
    n2 = log_shadow("kr", rows, root=str(tmp_path))  # same asof → idempotent

    assert n1 == len(VARIANTS), f"first write should append {len(VARIANTS)} rows, got {n1}"
    assert n2 == 0, f"second write of same asof should be no-op, got {n2}"

    for v in VARIANTS:
        p = tmp_path / "data" / "risk_radar_intl" / f"kr_forward_log_{v}.jsonl"
        assert p.exists(), f"log file for {v} must exist"
        file_rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        assert len(file_rows) == 1, f"{v}: expected 1 row, got {len(file_rows)}"
        assert file_rows[0]["asof"] == "2026-07-17"


# ── TEST 4a: S1 floor — leg high + gate open → elevated ──────────────────────

def test_s1_floor_leg_high_gate_open():
    """S1 any95: when a comp-leg pctile >= 0.95 and gate is open, incumbent
    state 'watch' should be floored to 'elevated'."""
    from engine.rri_shadow import _s1_any95_state

    # extension leg at 0.96 (> 0.95 threshold), gate open, incumbent = "watch"
    comp_leg_pcts = {"rateshock": 0.50, "fx": 0.40, "extension": 0.96}
    result = _s1_any95_state(
        incumbent_state="watch",
        incumbent_state_ungated="watch",
        comp_leg_pcts=comp_leg_pcts,
        gate_open=True,
    )
    assert result == "elevated", (
        f"S1 floor: leg=0.96 >= 0.95, gate_open=True, incumbent='watch' -> 'elevated'; got '{result}'"
    )


# ── TEST 4b: S1 floor — leg high but gate CLOSED → cap law unchanged ──────────

def test_s1_floor_gate_closed_no_escalation():
    """S1 any95: when gate is CLOSED, the floor must not fire even if a leg is >= 0.95.
    Incumbent state 'watch' stays 'watch' (not elevated) — the gate-closed cap law
    is unchanged by the S1 construction.
    """
    from engine.rri_shadow import _s1_any95_state

    comp_leg_pcts = {"rateshock": 0.50, "fx": 0.40, "extension": 0.96}
    result = _s1_any95_state(
        incumbent_state="watch",
        incumbent_state_ungated="elevated",  # ungated would be elevated but gate is closed
        comp_leg_pcts=comp_leg_pcts,
        gate_open=False,
    )
    # gate closed: the incumbent gated state is already correctly capped to "watch",
    # and the S1 floor must NOT fire (gate_open=False)
    assert result == "watch", (
        f"S1 floor must not fire when gate_open=False; got '{result}'"
    )


# ── TEST 4c: S1 floor — incumbent risk-off stays risk-off ────────────────────

def test_s1_floor_incumbent_risk_off_stays():
    """S1 floor never demotes: if incumbent is already 'risk-off', it must stay
    'risk-off' regardless of leg values (max of current and floor)."""
    from engine.rri_shadow import _s1_any95_state

    comp_leg_pcts = {"rateshock": 0.97, "fx": 0.60, "extension": 0.97}
    result = _s1_any95_state(
        incumbent_state="risk-off",
        incumbent_state_ungated="risk-off",
        comp_leg_pcts=comp_leg_pcts,
        gate_open=True,
    )
    assert result == "risk-off", (
        f"Incumbent 'risk-off' must stay 'risk-off' through S1 floor (max wins); got '{result}'"
    )


# ── TEST 4d: S1 floor — legs all below 0.95 → no change ─────────────────────

def test_s1_floor_legs_below_threshold_no_change():
    """S1 floor must not fire when all legs are below 0.95."""
    from engine.rri_shadow import _s1_any95_state

    comp_leg_pcts = {"rateshock": 0.80, "fx": 0.70, "extension": 0.88}
    result = _s1_any95_state(
        incumbent_state="watch",
        incumbent_state_ungated="watch",
        comp_leg_pcts=comp_leg_pcts,
        gate_open=True,
    )
    assert result == "watch", (
        f"S1 floor must not fire when max(leg_pctiles)=0.88 < 0.95; got '{result}'"
    )


# ── TEST 5: S3 velocity changes the composite ────────────────────────────────

def test_s3_velocity_changes_composite(monkeypatch):
    """The velocity leg produces a different composite series vs. the incumbent on a
    falling price series (where dd_velocity will be high).  On a synthetic falling
    market, the s3_ret10 state should differ from the incumbent state at some point
    — or at minimum, the composite series values differ.
    """
    from engine import risk_radar_intl as rri
    from engine.rri_shadow import _build_s3_composite, shadow_snapshot
    from lib import store

    # 3000 flat then 500 steadily falling sessions (strong dd_velocity)
    n_flat = 3000
    n_fall = 500
    n_total = n_flat + n_fall
    idx = pd.bdate_range("1993-01-04", periods=n_total)
    flat_px = np.full(n_flat, 100.0)
    fall_px = np.linspace(100.0, 50.0, n_fall)  # -50% cumulative fall
    bench_prices = np.concatenate([flat_px, fall_px])
    bench_df = pd.DataFrame({"close": bench_prices}, index=idx)

    # Synthetic store — rates/FX flat
    rate_df = pd.DataFrame({"us2y": np.full(n_total, 2.0), "close": np.full(n_total, 2.0)},
                            index=idx)
    dxy_df = pd.DataFrame({"close": np.full(n_total, 100.0)}, index=idx)
    fx_df = pd.DataFrame({"close": np.full(n_total, 100.0)}, index=idx)

    def fake_read(group, name, **kwargs):
        if group == "fred":
            return rate_df
        if group == "yahoo" and name == "DX-Y.NYB":
            return dxy_df
        if group in ("intl", "intl_etf"):
            return bench_df
        if group == "yahoo":
            return fx_df
        return None

    monkeypatch.setattr(store, "read", fake_read)

    B, sub, comp, gate = rri.composite_series(rri.KR_PROFILE)
    assert B is not None and comp is not None, "composite_series must succeed with synthetic data"

    # Build the s3 composite with velocity
    comp_v3, _ = _build_s3_composite(B, sub, rri.KR_PROFILE, ret_window=10)
    assert comp_v3 is not None, "_build_s3_composite must produce a series on synthetic data"

    # The two composites must differ somewhere (velocity adds information during the fall)
    comp_aligned = comp.reindex(comp_v3.index).dropna()
    comp_v3_aligned = comp_v3.reindex(comp_aligned.index).dropna()
    idx_common = comp_aligned.index.intersection(comp_v3_aligned.index)
    if len(idx_common) > 0:
        diff_abs = (comp_aligned.loc[idx_common] - comp_v3_aligned.loc[idx_common]).abs()
        assert diff_abs.max() > 1e-6, (
            "S3 composite must differ from incumbent composite on a falling series "
            f"(max diff={diff_abs.max():.2e})"
        )


# ── TEST 6: shadow_snapshot schema ───────────────────────────────────────────

def test_shadow_snapshot_schema(monkeypatch):
    """shadow_snapshot returns a dict with all 3 variants, each with the required
    schema fields when given valid synthetic (B, sub, comp, gate) inputs.
    """
    from engine import risk_radar_intl as rri
    from engine.rri_shadow import shadow_snapshot, VARIANTS
    from lib import store

    n = 2000
    idx = pd.bdate_range("1993-01-04", periods=n)
    bench_df = pd.DataFrame({"close": np.full(n, 100.0)}, index=idx)
    rate_df = pd.DataFrame({"us2y": np.full(n, 2.0), "close": np.full(n, 2.0)}, index=idx)
    dxy_df = pd.DataFrame({"close": np.full(n, 100.0)}, index=idx)
    fx_df = pd.DataFrame({"close": np.full(n, 100.0)}, index=idx)

    def fake_read(group, name, **kwargs):
        if group == "fred":
            return rate_df
        if group == "yahoo" and name == "DX-Y.NYB":
            return dxy_df
        if group in ("intl", "intl_etf"):
            return bench_df
        if group == "yahoo":
            return fx_df
        return None

    monkeypatch.setattr(store, "read", fake_read)

    B, sub, comp, gate = rri.composite_series(rri.KR_PROFILE)
    if B is None:
        pytest.skip("composite_series returned None on synthetic data — skip schema test")

    rows = shadow_snapshot(rri.KR_PROFILE, B, sub, comp, gate)

    assert isinstance(rows, dict), "shadow_snapshot must return a dict"
    required_keys = {"asof", "market", "variant", "construction", "state",
                     "state_ungated", "top_score", "alert", "legs", "gate_open",
                     "logged_at", "graded"}

    for variant in VARIANTS:
        assert variant in rows, f"shadow_snapshot must include variant '{variant}'"
        row = rows[variant]
        missing = required_keys - set(row.keys())
        assert not missing, f"variant {variant} missing keys: {missing}"
        assert row["construction"] == f"v2_{variant}", (
            f"construction must be 'v2_{variant}'; got {row['construction']!r}"
        )
        assert row["graded"] is None, "new rows must have graded=None"
        assert isinstance(row["alert"], bool)
        assert isinstance(row["gate_open"], bool)
        assert isinstance(row["legs"], dict)
        assert row["market"] == "kr"


# ── TEST 7: grading — known drawdown hit ─────────────────────────────────────

def test_grading_hit(tmp_path, monkeypatch):
    """A synthetic px series with a >= 5% drawdown within h21 of the as-of
    yields graded.any_dd5_within_h21 == True."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    from engine.rri_shadow import log_shadow, _grade_shadow_entry, VARIANTS

    # Build a price series where from index 100 there's a -10% drop by bar 110
    n = 300
    idx = pd.bdate_range("2000-01-03", periods=n)
    prices = np.full(n, 100.0)
    prices[105:116] = 85.0   # -15% drop starting after bar 100, well within h21

    px = pd.Series(prices, index=idx)

    # as-of = bar 100 (0-indexed), base_px = px[99] = 100.0
    asof_ts = idx[99]
    asof_str = str(asof_ts.date())

    entry = {
        "asof": asof_str,
        "market": "kr",
        "variant": "s1_any95",
        "state": "elevated",
        "alert": True,
        "graded": None,
    }

    result = _grade_shadow_entry(entry, px)
    assert result is not None, "_grade_shadow_entry must return a graded dict when h21 has matured"
    assert result["any_dd5_within_h21"] is True, (
        f"Expected any_dd5_within_h21=True given -15% drop; got {result}"
    )
    assert result["outcome"] == "true_positive", (
        f"Elevated alert + drawdown hit must be 'true_positive'; got {result['outcome']}"
    )
    # h21 fwd_dd should be around -15%
    h21_dd = result["fwd_dd"]["h21"]
    assert h21_dd is not None and h21_dd <= -0.05, (
        f"h21 dd should be <= -5%; got {h21_dd}"
    )


# ── TEST 8: grading — no drawdown → false_positive for alert ─────────────────

def test_grading_no_drawdown(monkeypatch):
    """A rising price series with no drawdown -> any_dd5_within_h21=False and
    alert 'elevated' grades as 'false_positive'."""
    from engine.rri_shadow import _grade_shadow_entry

    n = 200
    idx = pd.bdate_range("2000-01-03", periods=n)
    prices = np.linspace(100.0, 130.0, n)  # gently rising, no dip
    px = pd.Series(prices, index=idx)

    entry = {"asof": str(idx[5].date()), "market": "kr", "variant": "s1_any95",
             "state": "elevated", "alert": True, "graded": None}

    result = _grade_shadow_entry(entry, px)
    assert result is not None
    assert result["any_dd5_within_h21"] is False
    assert result["outcome"] == "false_positive"


# ── TEST 9: grade_shadow round-trip ──────────────────────────────────────────

def test_grade_shadow_roundtrip(tmp_path, monkeypatch):
    """Full round-trip: log a shadow row then grade it with a known drawdown bench.
    Verifies grade_shadow reads the file, grades the row, and writes it back.
    """
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    from engine import risk_radar_intl as rri
    from engine.rri_shadow import log_shadow, grade_shadow, VARIANTS

    # 300-bar bench with a -10% drop from bar 100
    n = 300
    idx = pd.bdate_range("2000-01-03", periods=n)
    prices = np.full(n, 100.0)
    prices[110:125] = 88.0   # -12% within h21
    px = pd.Series(prices, index=idx)
    bench_df = pd.DataFrame({"close": px}, index=idx)

    asof_str = str(idx[99].date())

    rows = {v: {"asof": asof_str, "market": "kr", "variant": v,
                "construction": f"v2_{v}", "state": "elevated", "state_ungated": "elevated",
                "top_score": 85, "alert": True, "legs": {}, "gate_open": True,
                "logged_at": "2026-07-17T00:00:00+00:00", "graded": None}
             for v in VARIANTS}

    n_logged = log_shadow("kr", rows, root=str(tmp_path))
    assert n_logged == len(VARIANTS)

    # Patch _bench in risk_radar_intl_audit to return our synthetic bench
    import engine.risk_radar_intl_audit as _rra
    monkeypatch.setattr(_rra, "_bench", lambda profile: px)

    n_graded = grade_shadow("kr", root=str(tmp_path))
    assert n_graded == len(VARIANTS), (
        f"Expected {len(VARIANTS)} rows graded; got {n_graded}"
    )

    # Verify the graded rows on disk
    for v in VARIANTS:
        p = tmp_path / "data" / "risk_radar_intl" / f"kr_forward_log_{v}.jsonl"
        file_rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        assert len(file_rows) == 1
        g = file_rows[0]["graded"]
        assert g is not None, f"{v}: row should be graded"
        assert g["any_dd5_within_h21"] is True, f"{v}: expected hit, got {g}"


# ── TEST 10: grade_shadow off-lane no-op ─────────────────────────────────────

def test_grade_shadow_off_lane(tmp_path, monkeypatch):
    """grade_shadow returns 0 and does not write when lane is not armed."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    from engine.rri_shadow import grade_shadow
    result = grade_shadow("kr", root=str(tmp_path))
    assert result == 0, f"off-lane grade_shadow must return 0; got {result}"


# ── TEST 11: MARKETS constant matches scope ───────────────────────────────────

def test_markets_constant():
    """MARKETS must be the 7 new-market profiles exactly (cn/hk/ca excluded)."""
    from engine.rri_shadow import MARKETS

    expected = {"kr", "jp", "tw", "in", "au", "gb", "ez"}
    assert set(MARKETS) == expected, (
        f"MARKETS must be the 7 new-market profiles; got {set(MARKETS)}"
    )
    forbidden = {"cn", "hk", "ca"}
    assert not forbidden & set(MARKETS), (
        "cn/hk/ca are byte-frozen and must NOT be in MARKETS"
    )


# ── TEST 12: VARIANTS constant ────────────────────────────────────────────────

def test_variants_constant():
    """VARIANTS must contain exactly the 3 ACCRUE candidates."""
    from engine.rri_shadow import VARIANTS

    assert set(VARIANTS) == {"s1_any95", "s3_ret10", "s3_ret21"}, (
        f"VARIANTS mismatch; got {set(VARIANTS)}"
    )
