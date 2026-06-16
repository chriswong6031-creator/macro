"""Tests for the unified Conviction Profile engine (engine/stock_score.py).

The load-bearing invariants are the HONESTY ones: a name fighting its tape can
never read "Buy"; HK never reads "Buy"; parabolic is a penalty not a reward;
missing legs are recorded, never silently neutral.
"""
import math

import pandas as pd
import pytest

from engine import stock_score as ss


# --- builders ---------------------------------------------------------------
def _rec(**kw):
    base = {
        "ticker": "TST", "name": "Test Co", "sector": "Technology",
        "alpha": 2.0, "alpha_entry": "pullback",
        "ladder": {"state": "RALLY ON", "label": "UPTREND", "dir": "up",
                   "eq_dir": "up", "entry": {"urgency": "now"}},
        "tech": {"off_52w_high_pct": -6.0, "rsi14": 55.0},
        "ext": {"grade": "in-trend", "ext_z": 0.3},
        "sector_rs": {"pct": 80.0}, "basket": {"rel20": 4.0},
        "factor": {"value": 0.5, "profitability": 0.8, "quality": 0.6, "low_vol": 0.2},
        "sue": 1.5, "insider_bps": 20.0, "accounting": {"verdict": "clean"},
    }
    base.update(kw)
    return base


def _verb(rec, market="US", ctx=None):
    return ss.conviction_profile(rec, market, ctx=ctx)["verdict"].lower()


# --- the cycle hard-block invariant (the mismatch fix) ----------------------
@pytest.mark.parametrize("state", ["DECLINE", "ROLLING OVER", "TOP WATCH"])
def test_downtrend_never_says_buy(state):
    rec = _rec(ladder={"state": state, "label": "DOWNTREND", "dir": "down",
                       "eq_dir": "down", "entry": {"urgency": "exit"}})
    p = ss.conviction_profile(rec, "US")
    assert "buy" not in p["verdict"].lower()
    assert "add" not in p["verdict"].lower()
    assert p["cycle_blocked"] is True
    # a strong name in a bad tape => "strong ... wait" language
    assert "wait" in p["verdict"].lower() or "hold" in p["verdict"].lower()
    # entry axis is capped
    assert p["axes"]["entry"]["z"] <= ss._ENTRY_CAP_Z + 1e-9


def test_exit_urgency_blocks_even_in_uptrend_state():
    rec = _rec(ladder={"state": "RALLY ON", "label": "UPTREND", "dir": "up",
                       "eq_dir": "up", "entry": {"urgency": "exit"}})
    p = ss.conviction_profile(rec, "US")
    assert p["cycle_blocked"] is True
    assert "buy" not in p["verdict"].lower()


# --- parabolic is a penalty, never a reward ---------------------------------
def test_parabolic_penalised_and_not_chased():
    rec = _rec(ext={"grade": "parabolic", "ext_z": 2.6}, tech={"off_52w_high_pct": -1.0, "rsi14": 82.0})
    p = ss.conviction_profile(rec, "US")
    v = p["verdict"].lower()
    assert "chase" in v or "extended" in v or "wait" in v
    assert any("parabolic" in c for c in p["cautions"])


def test_parabolic_entry_axis_below_intrend():
    base = ss.conviction_profile(_rec(), "US")["axes"]["entry"]["z"]
    para = ss.conviction_profile(_rec(ext={"grade": "parabolic", "ext_z": 2.6}), "US")["axes"]["entry"]["z"]
    assert para < base


# --- HK never says buy; screen language -------------------------------------
def test_hk_never_buys():
    for st in ["RALLY ON", "FRESH BUY", "DECLINE"]:
        rec = _rec(rs_z=2.2, alpha=None,
                   ladder={"state": st, "label": st, "dir": "up", "entry": {"urgency": "now"}})
        v = _verb(rec, "HK")
        assert "buy" not in v
    tt = ss.trust_tier("HK")
    assert tt["tier"] == "screen"


def test_hk_strong_rs_is_a_screen_standout():
    rec = _rec(rs_z=2.4, alpha=None)
    v = _verb(rec, "HK")
    assert "screen" in v or "standout" in v


# --- accounting warn downgrades a leader ------------------------------------
def test_accounting_warn_flags_leader():
    rec = _rec(accounting={"verdict": "warn"})
    p = ss.conviction_profile(rec, "US")
    assert "accounting" in p["verdict"].lower()
    assert any("accounting" in c for c in p["cautions"])


# --- the constructive cases -------------------------------------------------
def test_high_conviction_when_all_aligned():
    p = ss.conviction_profile(_rec(), "US")
    assert "high-conviction" in p["verdict"].lower()
    assert p["score"] is not None and p["score"] >= 50


def test_leader_poor_entry():
    # strong selection, bad entry (extended, near high, hot RSI) but NOT cycle-blocked
    rec = _rec(alpha_entry="extended", tech={"off_52w_high_pct": -1.0, "rsi14": 70.0},
               ladder={"state": "RALLY ON", "label": "UPTREND", "dir": "up",
                       "eq_dir": "up", "entry": {"urgency": "hold"}})
    v = _verb(rec, "US")
    assert "poor entry" in v or "wait" in v


# --- missing legs: provenance, no silent neutral, no crash ------------------
def test_sparse_name_does_not_crash_and_records_provenance():
    rec = {"ticker": "X", "name": "Sparse", "sector": "Energy",
           "alpha": 1.2, "ladder": {"state": "FRESH BUY", "entry": {"urgency": "now"}}}
    p = ss.conviction_profile(rec, "US")
    assert p["score"] is not None
    assert "alpha" in p["provenance"]["present"]
    # quality axis absent -> not present, recorded
    assert p["axes"]["quality"]["z"] is None
    assert p["n_axes"] >= 1


def test_empty_rec_is_safe():
    p = ss.conviction_profile({"ticker": "Z"}, "US")
    assert p["score"] is None
    assert p["n_axes"] == 0
    assert p["verdict"]  # still emits a verb


# --- bilingual + trust tiers ------------------------------------------------
def test_bilingual_fields_present():
    p = ss.conviction_profile(_rec(), "CN")
    assert p["verdict_zh"] and p["band_zh"]
    assert p["axes"]["selection"]["kind_zh"]


@pytest.mark.parametrize("m,tier", [("US", "context"), ("CA", "context"),
                                    ("CN", "reversal"), ("HK", "screen")])
def test_trust_tiers(m, tier):
    assert ss.trust_tier(m)["tier"] == tier


def test_us_go_flag_promotes_trust_tier():
    assert ss.trust_tier("US", gate_go=True)["tier"] == "validated"


# --- CN selection is reversal-led -------------------------------------------
def test_cn_selection_uses_reversal():
    rec = _rec(rev_z=2.0, alpha=0.1)
    z, present = ss._axis_selection(rec, "CN")
    assert "rev_z" in present
    assert z is not None and z > 0.5
    assert ss._sel_kind("CN", present)[0] == "mean-reversion"


def test_cn_alpha_fallback_is_recorded_and_labelled_honestly():
    # the common A-share case: no reversal watch entry, only residual momentum.
    # the contributing leg MUST be recorded (provenance) and NOT mislabelled reversal.
    rec = {"alpha": 1.5, "rev_z": None}
    z, present = ss._axis_selection(rec, "CN")
    assert z is not None and "alpha" in present and "rev_z" not in present
    assert ss._sel_kind("CN", present)[0] == "residual momentum"
    p = ss.conviction_profile(rec, "CN")
    assert "alpha" in p["provenance"]["present"]          # not silently absorbed


def test_parabolic_gets_specific_dont_chase_verdict():
    rec = _rec(ext={"grade": "parabolic", "ext_z": 2.6},
               tech={"off_52w_high_pct": -1.0, "rsi14": 82.0})
    assert "chase" in ss.conviction_profile(rec, "US")["verdict"].lower()


def test_absent_entry_is_unknown_not_poor():
    # strong selection, NO entry legs at all -> 'entry unknown', never asserts 'poor entry'
    p = ss.conviction_profile({"alpha": 2.0, "ladder": {"state": "FRESH BUY",
                              "entry": {"urgency": "zzz"}}}, "US")
    v = p["verdict"].lower()
    assert "unknown" in v and "poor entry" not in v


# --- panel helpers ----------------------------------------------------------
def test_sector_neutral_z_centers_within_sector():
    s = pd.Series([1, 2, 3, 4, 5, 6, 10, 20, 30, 40, 50, 60], dtype=float)
    sec = pd.Series(["A"] * 6 + ["B"] * 6, index=s.index)
    z = ss.sector_neutral_z(s, sec, min_sector=6)
    # within each sector the mean z is ~0
    assert abs(z[:6].mean()) < 1e-6
    assert abs(z[6:].mean()) < 1e-6


def test_score_percentiles_monotone():
    z = pd.Series([-2.0, -0.5, 0.0, 0.5, 2.0])
    p = ss.score_percentiles(z)
    assert list(p) == sorted(p)
    assert p.iloc[-1] == 100.0


def test_logistic_monotone_and_bounded():
    assert ss._logistic_0_100(-5) < ss._logistic_0_100(0) < ss._logistic_0_100(5)
    assert 0 <= ss._logistic_0_100(-10) <= 100
    assert ss._logistic_0_100(None) is None
