"""tests/test_options_hub_oi_suite.py — hermetic tests for the R3 OI suite
(engine/options_hub.compute_oi_time / compute_max_pain / compute_oi_change /
compute_oi_change_cross + the builder's upload guard).

All frames are synthetic — no parquet reads. Max-pain expectations are
hand-computed intrinsic payouts (documented inline) so a regression in the
minimization is caught by arithmetic, not by another run of the same code.

Coverage:
  oi_time    — call/put/total sums per session; 18-month window cut; future rows
               excluded; honest empty on empty frame.
  max_pain   — hand-computed argmin; tie broken toward spot; expired expirations
               excluded; curve carries the max-pain strike even when the ±20%
               window trims it; by_strike aggregates across expirations with the
               uncut count disclosed.
  oi_change  — |ΔOI| magnitude ranking (reductions survive), pct null for new
               contracts, expired contracts excluded, EOD mid join, disclosed
               unchanged-vintage empty, honest empty without a prev session.
  cross      — magnitude-ranked merge across roots, top-N cap.
  guard      — _oi_suite_upload_ok truth table (compute-empty over a non-empty
               store suppresses; a genuinely empty store publishes).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.options_hub import (  # noqa: E402
    compute_oi_time,
    compute_max_pain,
    compute_oi_change,
    compute_oi_change_cross,
)

ASOF = "2026-07-30"


def _oi_rows(rows):
    """rows: (date, expiration, strike, right, open_interest)."""
    return pd.DataFrame(
        rows, columns=["date", "expiration", "strike", "right", "open_interest"]
    )


# ── oi_time ───────────────────────────────────────────────────────────────────

def test_oi_time_sums_calls_and_puts_per_session():
    df = _oi_rows([
        ("2026-07-29", "2026-08-21", 100.0, "C", 10),
        ("2026-07-29", "2026-08-21", 100.0, "P", 4),
        ("2026-07-30", "2026-08-21", 100.0, "C", 12),
        ("2026-07-30", "2026-09-18", 110.0, "C", 3),
        ("2026-07-30", "2026-08-21", 100.0, "P", 5),
    ])
    out = compute_oi_time(df, ASOF, "SPY")
    assert out["schema"] == "options_hub.oi_time/v1"
    assert out["oi_date"] == "t-1"
    assert out["history"] == [
        {"date": "2026-07-29", "call_oi": 10, "put_oi": 4, "total_oi": 14},
        {"date": "2026-07-30", "call_oi": 15, "put_oi": 5, "total_oi": 20},
    ]
    assert out["coverage"] == {"n_days": 2, "since": "2026-07-29"}


def test_oi_time_window_cuts_old_and_future_rows():
    df = _oi_rows([
        ("2024-06-01", "2026-08-21", 100.0, "C", 99),  # > 18 months back — out
        ("2026-07-30", "2026-08-21", 100.0, "C", 7),
        ("2026-08-05", "2026-09-18", 100.0, "C", 88),  # after asof — out
    ])
    out = compute_oi_time(df, ASOF, "SPY", months=18)
    assert [r["date"] for r in out["history"]] == ["2026-07-30"]
    assert out["window_months"] == 18


def test_oi_time_empty_frame_is_honest_empty():
    out = compute_oi_time(pd.DataFrame(), ASOF, "ZZZT")
    assert out["history"] == [] and out["coverage"]["n_days"] == 0


# ── max_pain ──────────────────────────────────────────────────────────────────

def test_max_pain_hand_computed_argmin():
    # One expiration, strikes 90/100/110. Calls: 50 OI @ 100 + 1 OI @ 90.
    # Puts: 100 OI @ 100 + 1 OI @ 110. Payout ($, ×100 mult) per settle:
    #   90:  calls 0                    + puts 100·10·100 + 1·20·100 = 102,000
    #   100: calls 1·10·100             + puts 1·10·100              =   2,000  ← max pain
    #   110: calls 50·10·100 + 1·20·100 + puts 0                     =  52,000
    oi = _oi_rows([
        (ASOF, "2026-08-21", 90.0, "C", 1),    # listed strike, negligible OI
        (ASOF, "2026-08-21", 100.0, "C", 50),
        (ASOF, "2026-08-21", 100.0, "P", 100),
        (ASOF, "2026-08-21", 110.0, "P", 1),
    ])
    out = compute_max_pain(oi, ASOF, "SPY", spot_ref=100.0)
    assert out["schema"] == "options_hub.max_pain/v1"
    assert len(out["expiries"]) == 1
    row = out["expiries"][0]
    assert row["exp"] == "2026-08-21"
    assert row["max_pain"] == 100.0
    assert row["call_oi"] == 51 and row["put_oi"] == 101
    curve = {c["strike"]: c for c in row["curve"]}
    # Hand-checked values incl. the 1-OI wings:
    #   settle 90: put payout = (100·10 + 1·20)·100 = 102,000 → 0.10 $mn (2dp)
    assert curve[90.0]["put_value_mn"] == 0.1
    assert curve[90.0]["call_value_mn"] == 0.0
    assert curve[100.0]["value_mn"] == 0.0
    assert row["curve_full_n"] == 3


def test_max_pain_tie_breaks_toward_spot_and_drops_expired():
    # Strikes 90/100/110: call 10 OI @ 90, put 10 OI @ 110, put 1 OI @ 100.
    # Payout ($, ×100 mult) per candidate settle — hand-computed:
    #   90:  call 0            + 10·(110−90)·100 + 1·(100−90)·100 = 21,000
    #   100: 10·(100−90)·100   + 10·(110−100)·100 + 0             = 20,000
    #   110: 10·(110−90)·100   + 0                + 0             = 20,000
    # → an exact 2-way tie between 100 and 110; spot 104 picks 100 (dist 4 < 6).
    # The same-day expiration must be excluded entirely (exp > asof law).
    oi = _oi_rows([
        (ASOF, "2026-08-21", 90.0, "C", 10),
        (ASOF, "2026-08-21", 100.0, "P", 1),
        (ASOF, "2026-08-21", 110.0, "P", 10),
        (ASOF, ASOF, 100.0, "C", 500),          # expires today — excluded
    ])
    out = compute_max_pain(oi, ASOF, "SPY", spot_ref=104.0)
    assert [r["exp"] for r in out["expiries"]] == ["2026-08-21"]
    assert out["expiries"][0]["max_pain"] == 100.0


def test_max_pain_curve_always_carries_the_argmin_strike():
    # Puts 100 OI @ 200; strikes [100, 200]. Payout: settle 100 → 1,000,000;
    # settle 200 → 0 ⇒ max pain 200, far outside spot(100)'s ±20% window.
    oi = _oi_rows([
        (ASOF, "2026-08-21", 100.0, "P", 1),
        (ASOF, "2026-08-21", 200.0, "P", 100),
    ])
    out = compute_max_pain(oi, ASOF, "SPY", spot_ref=100.0)
    row = out["expiries"][0]
    assert row["max_pain"] == 200.0
    assert 200.0 in [c["strike"] for c in row["curve"]], (
        "the argmin strike must be drawable even when the ±20% window trims it")


def test_max_pain_by_strike_aggregates_across_expirations():
    oi = _oi_rows([
        (ASOF, "2026-08-21", 100.0, "C", 10),
        (ASOF, "2026-09-18", 100.0, "C", 5),
        (ASOF, "2026-09-18", 100.0, "P", 7),
        (ASOF, "2026-08-21", 110.0, "P", 3),
    ])
    out = compute_max_pain(oi, ASOF, "SPY", spot_ref=100.0)
    ladder = {r["strike"]: r for r in out["by_strike"]}
    assert ladder[100.0] == {"strike": 100.0, "call_oi": 15, "put_oi": 7}
    assert ladder[110.0] == {"strike": 110.0, "call_oi": 0, "put_oi": 3}
    assert out["by_strike_full_n"] == 2
    assert out["expiries_full_n"] == 2


def test_max_pain_empty_and_all_expired_are_honest_empty():
    assert compute_max_pain(pd.DataFrame(), ASOF, "ZZZT", None)["expiries"] == []
    expired = _oi_rows([(ASOF, "2026-07-30", 100.0, "C", 10)])
    out = compute_max_pain(expired, ASOF, "SPY", 100.0)
    assert out["expiries"] == [] and out["by_strike"] == []


# ── oi_change ─────────────────────────────────────────────────────────────────

def _chg_frames():
    prev = _oi_rows([
        ("2026-07-29", "2026-08-21", 100.0, "C", 100),  # A: rises to 150
        ("2026-07-29", "2026-08-21", 110.0, "P", 100),  # B: closes to 0
        ("2026-07-29", "2026-09-18", 120.0, "C", 40),   # E: unchanged
        ("2026-07-29", "2026-07-30", 90.0, "P", 500),   # D: expires today
    ])
    cur = _oi_rows([
        (ASOF, "2026-08-21", 100.0, "C", 150),
        (ASOF, "2026-09-18", 120.0, "C", 40),
        (ASOF, "2026-08-21", 105.0, "C", 30),           # C: brand new
        (ASOF, "2026-07-30", 90.0, "P", 0),
    ])
    return cur, prev


def test_oi_change_rows_pct_and_exclusions():
    cur, prev = _chg_frames()
    eod = pd.DataFrame({
        "expiration": ["2026-08-21"], "strike": [100.0], "right": ["C"],
        "bid_eod": [1.0], "ask_eod": [2.0],
    })
    out = compute_oi_change(cur, prev, eod, ASOF, "2026-07-29", "SPY")
    assert out["schema"] == "options_hub.oi_change/v1"
    assert out["prev_session"] == "2026-07-29"
    rows = {(r["exp"], r["strike"], r["right"]): r for r in out["rows"]}
    # A: +50 on 100 prev → +50.0%, mid (1+2)/2
    a = rows[("2026-08-21", 100.0, "C")]
    assert a["d_oi"] == 50 and a["d_oi_pct"] == 50.0 and a["mid"] == 1.5
    assert a["oi"] == 150 and a["oi_prev"] == 100 and a["dte"] == 22
    # B: closed to zero → −100 magnitude ranks FIRST (reductions survive)
    b = rows[("2026-08-21", 110.0, "P")]
    assert b["d_oi"] == -100 and b["d_oi_pct"] == -100.0 and b["mid"] is None
    assert out["rows"][0] is not None and out["rows"][0]["d_oi"] == -100
    # C: new contract → pct null
    c = rows[("2026-08-21", 105.0, "C")]
    assert c["oi_prev"] == 0 and c["d_oi_pct"] is None
    # E unchanged and D expired never appear
    assert ("2026-09-18", 120.0, "C") not in rows
    assert ("2026-07-30", 90.0, "P") not in rows
    assert out["coverage"]["n_contracts_changed"] == 3


def test_oi_change_top_n_is_magnitude_ranked():
    cur, prev = _chg_frames()
    out = compute_oi_change(cur, prev, None, ASOF, "2026-07-29", "SPY", top_n=1)
    assert len(out["rows"]) == 1
    assert out["rows"][0]["d_oi"] == -100  # |−100| beats |+50| and |+30|


def test_oi_change_unchanged_vintage_is_disclosed_not_stale():
    same = _oi_rows([(ASOF, "2026-08-21", 100.0, "C", 100)])
    prev = _oi_rows([("2026-07-29", "2026-08-21", 100.0, "C", 100)])
    out = compute_oi_change(same, prev, None, ASOF, "2026-07-29", "SPY")
    assert out["rows"] == [] and "note" in out


def test_oi_change_missing_prev_session_is_honest_empty():
    cur, _ = _chg_frames()
    out = compute_oi_change(cur, pd.DataFrame(), None, ASOF, None, "SPY")
    assert out["rows"] == [] and out["prev_session"] is None and "note" not in out


def test_oi_change_cross_merges_and_caps_by_magnitude():
    rows = [
        {"root": "SPY", "d_oi": 50},
        {"root": "QQQ", "d_oi": -80},
        {"root": "NVDA", "d_oi": 10},
    ]
    out = compute_oi_change_cross(rows, ASOF, roots_n=3, top_n=2)
    assert out["scope"] == "cross_root" and out["roots_n"] == 3
    assert [r["root"] for r in out["rows"]] == ["QQQ", "SPY"]


# ── builder upload guard ──────────────────────────────────────────────────────

def test_oi_suite_upload_guard_truth_table():
    from scripts.build_options_hub_nightly import _oi_suite_upload_ok
    assert _oi_suite_upload_ok([{"x": 1}], True) is True     # data → publish
    assert _oi_suite_upload_ok([], True) is False            # anomaly → last-good
    assert _oi_suite_upload_ok([], False) is True            # empty store → honest empty
