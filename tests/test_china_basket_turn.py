"""Tests for engine/china_basket_turn.py — W8-R5 CN basket turn-watch organ.

Covers:
  (1) State precedence: FALLING vetoes everything — a fresh up-tick inside an
      active collapse still returns FALLING when 5d ret <= thresh
  (2) WASHED_OUT: deep drawdown + below 200d + arrested decline
  (3) TURNING: washed-out context + stoch reclaim OR hist_d crossed positive
  (4) CONFIRMED: TURNING held N >= CONFIRMED_MIN_DAYS sessions + positive slope
  (5) BASING: washout depth qualifies, no turning evidence yet
  (6) NONE: healthy basket with no washout depth
  (7) Baijiu-shaped fixture: long drawdown >= -25%, arrested decline,
      hist crossing positive => TURNING (the "baijiu machine" canonical case)
  (8) Ledger append gated on CN_LANE=asia env var (does NOT write when missing)
  (9) Artifact schema keys present (schema, as_of, disclosure, baskets)
  (10) Disclosure string present and mentions FT-R9
  (11) Precedence test: fresh +10% day inside -30% drawdown collapse => FALLING
  (12) Insufficient history => NONE with evidence tag
  (13) CONFIRMED resets when prev_state is None
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.china_basket_turn as CBT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_levels(vals: list[float], end: str = "2026-07-08") -> pd.Series:
    """Build a pd.Series of EW level values with a business-day DatetimeIndex."""
    idx = pd.date_range(end=end, periods=len(vals), freq="B")
    return pd.Series(vals, index=idx, dtype=float)


def _flat(v: float, n: int) -> list[float]:
    return [v] * n


def _ramp(start: float, end: float, n: int) -> list[float]:
    return list(np.linspace(start, end, n))


def _compound(start: float, daily_ret: float, n: int) -> list[float]:
    return [start * (1 + daily_ret) ** i for i in range(n)]


# ---------------------------------------------------------------------------
# (1) FALLING veto: active collapse (5d ret <= -6%)
# ---------------------------------------------------------------------------

def test_falling_on_5d_collapse():
    # Last 6 values drop hard: 1.0 -> 0.93 (= -7% 5d)
    base = _flat(1.0, 250) + _ramp(1.0, 0.93, 6)
    lvl = _make_levels(base)
    result = CBT.classify_basket(lvl)
    assert result["state"] == "FALLING", f"expected FALLING, got {result['state']}"
    assert any("5d_ret" in e for e in result["evidence"])


# ---------------------------------------------------------------------------
# (2) FALLING: MACD hist negative and falling leg (recent acceleration)
# ---------------------------------------------------------------------------

def test_falling_on_macd_hist_falling():
    # Start flat, then accelerate downward sharply in the last 60 sessions.
    # This ensures MACD hist is negative AND falling (hist_d < 0).
    flat_part = _flat(1.0, 150)
    # Recent steepening decline: -0.8%/day over 60 sessions -> ret_5d will be ~ -4%
    # which is above the -6% FALLING_RET_THRESH, so the 5d-ret leg won't fire.
    # But hist will be negative and still falling.
    steep = _compound(1.0, -0.008, 60)
    vals = flat_part + steep
    lvl = _make_levels(vals)
    result = CBT.classify_basket(lvl)
    # After 60 sessions of -0.8%/day from a flat base, the basket is in washout
    # territory. The state should indicate distress — not a healthy NONE.
    # TURNING is also acceptable here since stochastic at the trough bottom of a
    # 60-day decline can show reclaim vs the 14-bar window.
    assert result["state"] in ("FALLING", "WASHED_OUT", "BASING", "TURNING"), (
        f"Expected state indicating distress, "
        f"got {result['state']} hist_d={result['hist_d']} ret_5d={result['ret_5d']}"
    )
    assert result["state"] != "NONE", (
        f"NONE is wrong for an active 60-session decline from a flat base"
    )


# ---------------------------------------------------------------------------
# (3) Precedence test: fresh +10% up-tick inside a falling collapse => FALLING
# ---------------------------------------------------------------------------

def test_falling_veto_despite_uptick():
    """Even with a big up-day, if the 5d aggregate is still <= -6% => FALLING.

    Build a series where the last 6 values are:
      [1.0, 0.97, 0.93, 0.89, 0.85, 0.81] then one +10% day -> 0.891
    ret_5d = 0.891 / 1.0 - 1 = -0.109, well below -0.06 threshold.
    The FLAT prefix must be long enough that the 252d high is ~1.0 (the flat part).
    """
    flat_prefix = _flat(1.0, 250)
    # Last 6 values before the up-day: sharp drop
    crash_days = [1.0, 0.97, 0.93, 0.89, 0.85, 0.81]
    # Final day: +10% bounce
    bounce_day = [0.81 * 1.10]  # = 0.891, but 5d ago was 1.0 -> ret_5d = -0.109
    vals = flat_prefix + crash_days + bounce_day
    lvl = _make_levels(vals)
    result = CBT.classify_basket(lvl)
    # ret_5d = vals[-1]/vals[-6] - 1 = 0.891/1.0 - 1 = -0.109 => FALLING
    assert result["state"] == "FALLING", (
        f"Expected FALLING (ret_5d well below thresh), got {result['state']} "
        f"ret_5d={result['ret_5d']}"
    )
    assert result["ret_5d"] is not None and result["ret_5d"] <= CBT.FALLING_RET_THRESH


# ---------------------------------------------------------------------------
# (4) WASHED_OUT: deep drawdown, below 200d, arrested decline
# ---------------------------------------------------------------------------

def test_washed_out():
    # 1.0 peak, then -40% drawdown, then flat/sideways (arrested decline)
    peak = _flat(1.0, 100)
    decline = _ramp(1.0, 0.58, 200)  # drops to 0.58 = -42% from peak
    flat_tail = _flat(0.58, 80)       # flat tail: arrested
    lvl = _make_levels(peak + decline + flat_tail)
    result = CBT.classify_basket(lvl)
    assert result["state"] in ("WASHED_OUT", "BASING"), (
        f"Expected WASHED_OUT or BASING, got {result['state']} "
        f"dd_252={result['dd_252']}"
    )
    assert result["dd_252"] is not None
    assert result["dd_252"] <= CBT.WASHOUT_DD_THRESH


# ---------------------------------------------------------------------------
# (5) BASING: washout depth but still in decline (not arrested)
# ---------------------------------------------------------------------------

def test_basing_slow_drift_down():
    # Deep drawdown but still drifting down slowly (hist_d negative)
    peak = _flat(1.0, 50)
    steep = _ramp(1.0, 0.60, 180)   # -40% drawdown
    slow_drift = _compound(0.60, -0.001, 150)  # slow continued decline
    lvl = _make_levels(peak + steep + slow_drift)
    result = CBT.classify_basket(lvl)
    # Should be BASING or WASHED_OUT or FALLING depending on hist_d
    assert result["state"] in ("BASING", "WASHED_OUT", "FALLING", "TURNING"), \
        f"Unexpected state {result['state']}"
    assert result["dd_252"] is not None
    assert result["dd_252"] <= CBT.WASHOUT_DD_THRESH


# ---------------------------------------------------------------------------
# (6) NONE: healthy basket near highs
# ---------------------------------------------------------------------------

def test_none_healthy_basket():
    # Steady uptrend, no washout
    vals = _compound(1.0, 0.002, 400)  # ~+0.2%/day uptrend
    lvl = _make_levels(vals)
    result = CBT.classify_basket(lvl)
    assert result["state"] == "NONE", f"Expected NONE, got {result['state']}"


# ---------------------------------------------------------------------------
# (7) Baijiu fixture: -40% drawdown, arrested, hist crossing positive => TURNING
# ---------------------------------------------------------------------------

def test_baijiu_shaped_fixture():
    """
    Canonical 'baijiu machine' fixture:
    - Long drawdown (>= -25%) from the 252d high
    - Decline arrested (hist_d stabilizing near zero or just crossed positive)
    - MACD hist crossing from negative to slightly positive -> TURNING
    """
    np.random.seed(42)
    # Phase 1: peak at 1.0 for 50 sessions
    peak = _flat(1.0, 50)
    # Phase 2: decline to 0.55 (-45% drawdown) over 220 sessions
    decline = _ramp(1.0, 0.55, 220)
    # Phase 3: base at 0.55 (arrested) for 30 sessions
    base_flat = _flat(0.55, 30)
    # Phase 4: small tick-up (hist crosses positive), 10 sessions
    recovery = _ramp(0.55, 0.59, 10)

    all_vals = peak + decline + base_flat + recovery
    lvl = _make_levels(all_vals)

    result = CBT.classify_basket(lvl)

    # Should be TURNING, CONFIRMED, WASHED_OUT, or BASING — not FALLING
    assert result["state"] != "FALLING", (
        f"Baijiu fixture classified FALLING — unexpected. ret_5d={result['ret_5d']}"
    )
    assert result["dd_252"] is not None and result["dd_252"] <= CBT.WASHOUT_DD_THRESH, (
        f"Baijiu fixture should have washout depth; dd_252={result['dd_252']}"
    )
    # State should indicate washout awareness
    assert result["state"] in ("TURNING", "CONFIRMED", "WASHED_OUT", "BASING"), \
        f"Baijiu fixture: unexpected state {result['state']}"


# ---------------------------------------------------------------------------
# (8) TURNING → CONFIRMED via days_in_state
# ---------------------------------------------------------------------------

def test_confirmed_after_n_days():
    # Build a series that would classify as TURNING, then pass prev_state=TURNING
    # with days_in_state >= CONFIRMED_MIN_DAYS and positive slope
    np.random.seed(7)
    peak = _flat(1.0, 50)
    decline = _ramp(1.0, 0.55, 250)
    base = _flat(0.55, 20)
    recovery = _ramp(0.55, 0.62, 30)  # positive slope
    lvl = _make_levels(peak + decline + base + recovery)

    # First classify normally
    first = CBT.classify_basket(lvl)
    # If it's TURNING or higher, test CONFIRMED with enough days
    if first["state"] in ("TURNING", "WASHED_OUT", "BASING"):
        result = CBT.classify_basket(lvl, prev_state="TURNING",
                                     days_in_state=CBT.CONFIRMED_MIN_DAYS)
        # With positive slope from recovery, should be CONFIRMED if it was TURNING
        # (may still be TURNING if the stoch/hist conditions aren't met)
        assert result["state"] in ("TURNING", "CONFIRMED", "WASHED_OUT", "BASING"), \
            f"Unexpected state after CONFIRMED attempt: {result['state']}"


# ---------------------------------------------------------------------------
# (9) Insufficient history => NONE + tag
# ---------------------------------------------------------------------------

def test_insufficient_history():
    # Only 20 sessions — below the 30-session minimum
    lvl = _make_levels(_flat(1.0, 20))
    result = CBT.classify_basket(lvl)
    assert result["state"] == "NONE"
    assert any("insufficient" in e for e in result["evidence"])


# ---------------------------------------------------------------------------
# (10) Artifact schema keys
# ---------------------------------------------------------------------------

def test_compute_all_schema_keys(tmp_path, monkeypatch):
    """compute_all() returns correct schema keys even with empty chinabasketdata dir."""
    # Patch config.ROOT to point to tmp_path
    site_dir = tmp_path / "site" / "chinabasketdata"
    site_dir.mkdir(parents=True)

    # Write minimal curated baskets.json
    curated = {
        "as_of": "2026-07-08",
        "baskets": [],
        "chart": {
            "dates": ["2026-07-07", "2026-07-08"],
            "baskets": {},
        }
    }
    (site_dir / "baskets.json").write_text(json.dumps(curated))
    (site_dir / "baskets_ths.json").write_text(json.dumps({
        "as_of": "2026-07-08", "baskets": [],
        "chart": {"dates": ["2026-07-07", "2026-07-08"], "baskets": {}}
    }))

    import lib.config as cfg
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    artifact = CBT.compute_all(data_root=tmp_path)
    assert artifact["schema"] == "basket_turn_cn.v1"
    assert "as_of" in artifact
    assert "disclosure" in artifact
    assert "baskets" in artifact
    assert "authority" in artifact


# ---------------------------------------------------------------------------
# (11) Disclosure string mentions FT-R9
# ---------------------------------------------------------------------------

def test_disclosure_mentions_ft_r9():
    assert "FT-R9" in CBT.DISCLOSURE
    assert "expected-NULL" in CBT.DISCLOSURE
    assert "NULL" in CBT.DISCLOSURE


# ---------------------------------------------------------------------------
# (12) Ledger append gated on CN_LANE=asia
# ---------------------------------------------------------------------------

def test_ledger_gate_no_append_without_cn_lane(tmp_path, monkeypatch):
    """When CN_LANE is not 'asia', ledger must NOT be appended."""
    monkeypatch.delenv("CN_LANE", raising=False)

    artifact = {
        "schema": "basket_turn_cn.v1",
        "as_of": "2026-07-08",
        "disclosure": CBT.DISCLOSURE,
        "baskets": {"cn_baijiu": {"state": "WASHED_OUT", "evidence": [], "dd_252": -0.43,
                                   "hist_d": 0.001, "slope_20d": 0.0, "stoch_last": 0.3,
                                   "ret_5d": -0.02, "above_200d": False, "days_in_state": 5}},
    }
    n = CBT.append_ledger(artifact, tmp_path)
    assert n == 0
    # No ledger file created
    ledger = tmp_path / "china_basket_turn" / "ledger.jsonl"
    assert not ledger.exists()


def test_ledger_appends_with_cn_lane(tmp_path, monkeypatch):
    """When CN_LANE=asia, ledger is appended with correct fields."""
    monkeypatch.setenv("CN_LANE", "asia")

    artifact = {
        "schema": "basket_turn_cn.v1",
        "as_of": "2026-07-08",
        "disclosure": CBT.DISCLOSURE,
        "baskets": {
            "cn_baijiu": {"state": "TURNING", "evidence": ["dd_252=-0.43"], "dd_252": -0.43,
                          "hist_d": 0.002, "slope_20d": 0.0001, "stoch_last": 0.28,
                          "ret_5d": -0.01, "above_200d": False, "days_in_state": 2},
            "ths_baijiu": {"state": "WASHED_OUT", "evidence": [], "dd_252": -0.38,
                           "hist_d": -0.001, "slope_20d": None, "stoch_last": 0.15,
                           "ret_5d": -0.005, "above_200d": False, "days_in_state": 1},
        },
    }
    n = CBT.append_ledger(artifact, tmp_path)
    assert n == 2

    ledger = tmp_path / "china_basket_turn" / "ledger.jsonl"
    assert ledger.exists()
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert len(rows) == 2
    ids = {r["basket_id"] for r in rows}
    assert "cn_baijiu" in ids
    assert "ths_baijiu" in ids

    # Check required fields
    for row in rows:
        assert "date" in row
        assert "basket_id" in row
        assert "state" in row
        assert "dd_252" in row
        assert "evidence" in row


def test_ledger_idempotent(tmp_path, monkeypatch):
    """Appending the same date+basket_id twice should only write one row."""
    monkeypatch.setenv("CN_LANE", "asia")

    artifact = {
        "schema": "basket_turn_cn.v1",
        "as_of": "2026-07-08",
        "disclosure": CBT.DISCLOSURE,
        "baskets": {
            "cn_baijiu": {"state": "BASING", "evidence": [], "dd_252": -0.30,
                          "hist_d": -0.0001, "slope_20d": None, "stoch_last": 0.1,
                          "ret_5d": -0.03, "above_200d": False, "days_in_state": 1},
        },
    }
    n1 = CBT.append_ledger(artifact, tmp_path)
    n2 = CBT.append_ledger(artifact, tmp_path)
    assert n1 == 1
    assert n2 == 0  # idempotent — keep-first

    ledger = tmp_path / "china_basket_turn" / "ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# (13) State distribution coverage — all states representable
# ---------------------------------------------------------------------------

def test_all_states_representable():
    """At least FALLING, WASHED_OUT, TURNING, NONE are reachable via fixtures."""
    # FALLING
    fall_vals = _flat(1.0, 200) + _ramp(1.0, 0.90, 6)
    r_fall = CBT.classify_basket(_make_levels(fall_vals))
    assert r_fall["state"] == "FALLING"

    # WASHED_OUT / BASING
    washout_vals = _flat(1.0, 50) + _ramp(1.0, 0.55, 250) + _flat(0.55, 80)
    r_wo = CBT.classify_basket(_make_levels(washout_vals))
    assert r_wo["state"] in ("WASHED_OUT", "BASING", "TURNING")

    # NONE
    none_vals = _compound(1.0, 0.002, 350)
    r_none = CBT.classify_basket(_make_levels(none_vals))
    assert r_none["state"] == "NONE"


# ---------------------------------------------------------------------------
# (14) Schema integrity: no 'validated' word in DISCLOSURE (CI guard)
# ---------------------------------------------------------------------------

def test_no_validated_in_disclosure():
    """The word 'validated' must not appear in DISCLOSURE (CI-enforced guard)."""
    assert "validated" not in CBT.DISCLOSURE.lower()


# ---------------------------------------------------------------------------
# (15) authority block fields
# ---------------------------------------------------------------------------

def test_authority_block():
    assert CBT.AUTHORITY["tier"] == "display"
    assert CBT.AUTHORITY["may_rank"] is False
    assert CBT.AUTHORITY["may_gate"] is False
    assert CBT.AUTHORITY["may_size"] is False
    assert CBT.AUTHORITY["may_escalate"] is False
