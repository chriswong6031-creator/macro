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


@pytest.mark.parametrize("m,tier", [("US", "event-edge"), ("CA", "context"),
                                    ("CN", "reversal"), ("HK", "screen")])
def test_trust_tiers(m, tier):
    assert ss.trust_tier(m)["tier"] == tier


def test_ca_edge_is_momentum_not_floored():
    # Canada has no event feeds -> momentum at full strength (no confidence floor), labeled prior
    z, present = ss._axis_selection({"alpha": 2.5}, "CA")
    assert present == ["alpha"] and z is not None and z >= 2.0
    assert ss.trust_tier("CA")["tier"] == "context"


# --- v2 EDGE axis: validated event signals drive the rank, momentum is light context ---
def test_edge_is_event_driven_not_momentum():
    # strong SUE + insider but only mild momentum -> still a HIGH edge (events lead)
    rec = {"sue": 2.5, "insider_bps": 40.0, "alpha": 0.2}
    z, present = ss._axis_selection(rec, "US")
    assert {"sue", "insider"} <= set(present)
    assert z is not None and z >= 1.0           # event legs carry it
    assert ss._sel_kind("US", present)[0].startswith("earnings")


def test_momentum_alone_is_weak_edge():
    # momentum-only (no validated event leg) is heavily dampened by the confidence floor:
    # even an extreme alpha cannot manufacture a strong edge on noise.
    rec = {"alpha": 3.0}
    z, present = ss._axis_selection(rec, "US")
    assert present == ["alpha"]
    assert z is not None and z < 1.0            # 0.10*3.0/0.5 = 0.6 — weak, ranks low
    # whereas a real SUE of the same magnitude dominates
    z2, _ = ss._axis_selection({"sue": 3.0}, "US")
    assert z2 > z + 0.5


def test_revision_feeds_edge():
    rec = {"revision_z": 2.0}
    z, present = ss._axis_selection(rec, "US")
    assert "revision" in present and z is not None and z > 0.5


def test_high_edge_low_quality_is_not_neutral():
    # strong event edge (SUE) + ok entry + WEAK quality must read 'leader, weak fundamentals'
    # — never fall through to 'Neutral' (the score-vs-verdict coherence bug we fixed).
    rec = {"sue": 3.0, "alpha": 1.4, "ladder": {"state": "BOTTOM WATCH", "entry": {"urgency": "now"}},
           "tech": {"rsi14": 50, "off_52w_high_pct": -8},
           "factor": {"profitability": -1.5, "quality": -1.2, "value": -0.8, "low_vol": -0.9}}
    p = ss.conviction_profile(rec, "US")
    v = p["verdict"].lower()
    assert "neutral" not in v and "leader" in v and "weak" in v


def test_sue_insider_not_in_quality_axis():
    # they moved to EDGE in v2 — quality is durability (factors/priors) only
    rec = {"sue": 3.0, "insider_bps": 50.0,
           "factor": {"profitability": 0.4, "quality": 0.3, "value": 0.1, "low_vol": 0.0}}
    qz, present, flags = ss._axis_quality(rec, "US")
    assert "sue" not in present and "insider" not in present
    assert "factors" in present


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
    p = ss.conviction_profile({"sue": 3.0, "ladder": {"state": "FRESH BUY",
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


# --- v3: regime-conditional EDGE weighting ----------------------------------
def test_edge_weights_default_is_v2_base():
    # no regime supplied -> byte-identical to the v2 base weights (backward-compatible)
    assert ss._edge_weights(None) == ss._EDGE_W
    assert ss._edge_weights(None)["mom"] == ss._EDGE_W["mom"]


def test_edge_weights_momentum_scales_with_calm():
    # calm tape up-weights momentum; stress pulls it toward zero; the validated event
    # legs (SUE/insider/revision) are NEVER scaled down.
    calm, stress = ss._edge_weights(1.0), ss._edge_weights(0.0)
    assert calm["mom"] > stress["mom"]
    assert calm["mom"] == pytest.approx(ss._MOM_W_CALM)
    assert stress["mom"] == pytest.approx(ss._MOM_W_STRESS)
    for k in ("sue", "insider", "revision"):
        assert calm[k] == stress[k] == ss._EDGE_W[k]


def test_momentum_name_ranks_higher_in_calm_than_stress():
    # a strong-momentum, no-event US name scores a higher EDGE in a calm tape than in
    # stress (the regime tilt) — the central v3 behaviour.
    rec = {"alpha": 2.5}
    z_calm, _ = ss._axis_selection(rec, "US", 1.0)
    z_stress, _ = ss._axis_selection(rec, "US", 0.0)
    z_none, _ = ss._axis_selection(rec, "US", None)
    assert z_calm > z_stress
    assert z_stress is not None and z_calm is not None
    # the v2 default (mom 0.10) sits between the stress floor and the calm ceiling
    assert z_stress <= z_none <= z_calm + 1e-9


def test_regime_does_not_move_a_pure_event_name():
    # a name carried only by SUE (no momentum leg) is regime-invariant — we only scale
    # the momentum leg, never the validated event core.
    rec = {"sue": 2.5}
    z_calm, _ = ss._axis_selection(rec, "US", 1.0)
    z_stress, _ = ss._axis_selection(rec, "US", 0.0)
    assert z_calm == pytest.approx(z_stress)


def test_regime_tilt_banner_states():
    assert ss._regime_tilt("US", 1.0)["state"] == "calm"
    assert ss._regime_tilt("US", 0.0)["state"] == "stress"
    assert ss._regime_tilt("US", 0.5)["state"] == "mixed"
    # ex-US / no-regime -> no banner (only US conditions on the live tape)
    assert ss._regime_tilt("CA", 1.0) is None
    assert ss._regime_tilt("US", None) is None


def test_profile_carries_regime_banner():
    p = ss.conviction_profile(_rec(), "US", ctx={"regime": {"calm": 1.0}})
    assert p["regime"] is not None and p["regime"]["state"] == "calm"
    # no regime in ctx -> no banner, and behaviour unchanged
    assert ss.conviction_profile(_rec(), "US")["regime"] is None


# --- v3.1: SUE is scored FLAT — freshness is DISPLAY-only (the decay was retired because
# real EDGAR filing dates showed it lowered the long-only board; see _PEAD_TAU comment) -----
def test_sue_is_scored_flat_regardless_of_freshness():
    # same SUE magnitude scores identically whether the filing is fresh or stale — the
    # freshness decay no longer perturbs the score (it hurt the long-only top decile on real dates).
    fresh, _ = ss._axis_selection({"sue": 2.0, "sue_fresh_days": 5.0}, "US")
    stale, _ = ss._axis_selection({"sue": 2.0, "sue_fresh_days": 200.0}, "US")
    none_, _ = ss._axis_selection({"sue": 2.0}, "US")
    assert fresh == pytest.approx(stale) == pytest.approx(none_)
    assert not hasattr(ss, "_pead_decay")          # the decay helper is gone


def test_sue_freshness_is_carried_as_display_only():
    # the SUE basis chip's z is flat (freshness-independent) but carries fresh_days for display.
    b_fresh = ss._edge_basis({"sue": 2.0, "sue_fresh_days": 8.0}, "US")
    b_stale = ss._edge_basis({"sue": 2.0, "sue_fresh_days": 180.0}, "US")
    cf = next(x for x in b_fresh if x["leg"] == "sue")
    cs = next(x for x in b_stale if x["leg"] == "sue")
    assert cf["z"] == pytest.approx(cs["z"])       # score identical
    assert cf["fresh_days"] == 8 and cs["fresh_days"] == 180   # but recency is shown
    # no fresh_days key when no filing date is known
    assert "fresh_days" not in next(x for x in ss._edge_basis({"sue": 2.0}, "US") if x["leg"] == "sue")


# --- reshape T1: absolute trend-extension brake (the CASY fix) ----------------
def test_stretch_penalty_bounds_and_monotone():
    assert ss._stretch_penalty(None) is None
    assert ss._stretch_penalty(10.0) == 0.0          # healthy trend, no penalty
    assert ss._stretch_penalty(25.0) == 0.0          # ≤ warn = healthy, untouched (per the data)
    # monotone-decreasing through the stretch zone, floored at -1.2
    assert 0 > ss._stretch_penalty(27.0) > ss._stretch_penalty(30.0) >= ss._stretch_penalty(45.0)
    assert ss._stretch_penalty(80.0) == pytest.approx(-1.2)


def test_overextended_threshold():
    assert ss._overextended({"tech": {"pct_vs_200dma": 31.0}}) is True
    assert ss._overextended({"tech": {"pct_vs_200dma": 12.0}}) is False
    assert ss._overextended({"tech": {}}) is False


def test_overextended_name_is_blocked_and_dont_chase():
    # a CASY-like name: strong momentum, shallow -7% dip, RSI 55, FRESH BUY, +31% over 200dma
    rec = {"alpha": 2.4, "alpha_entry": "intact",
           "ladder": {"state": "FRESH BUY", "label": "BUY ZONE", "dir": "up",
                      "entry": {"urgency": "now"}},
           "tech": {"off_52w_high_pct": -7.0, "rsi14": 55.0, "pct_vs_200dma": 31.3}}
    z, present, blocked = ss._axis_entry(rec)
    assert blocked is True and z is not None and z <= ss._ENTRY_CAP_Z * 1.6 + 1e-9
    assert "over-200dma" in present
    p = ss.conviction_profile(rec, "US")
    assert "don't chase" in p["verdict"].lower() or "chase" in p["verdict"].lower()
    assert any("extended" in c and "200dma" in c for c in p["cautions"])
    assert "buy" not in p["verdict"].lower()


def test_normal_extension_not_blocked():
    # the SAME name only +12% over its 200dma is a healthy trend, not a chase
    rec = {"alpha": 2.4, "alpha_entry": "pullback",
           "ladder": {"state": "RALLY ON", "label": "UPTREND", "dir": "up",
                      "entry": {"urgency": "now"}},
           "tech": {"off_52w_high_pct": -7.0, "rsi14": 55.0, "pct_vs_200dma": 12.0}}
    z, present, blocked = ss._axis_entry(rec)
    assert blocked is False and "over-200dma" not in present


# --- reshape T3: macro/event risk overlay (tax a chase into a stressed tape) ---
def test_aggressiveness_chase_vs_washout():
    assert ss._aggressiveness({"tech": {"pct_vs_200dma": 40.0}}) == pytest.approx(1.0)
    assert ss._aggressiveness({"tech": {"pct_vs_200dma": -18.0}}) == 0.0   # washout
    assert ss._aggressiveness({"tech": {}, "ext": {"grade": "parabolic"}}) >= 0.9


def test_risk_tax_scales_with_stress_and_aggressiveness():
    chase = {"tech": {"pct_vs_200dma": 40.0}}
    wash = {"tech": {"pct_vs_200dma": -18.0}}
    assert ss._risk_tax({"stress": 0.0}, chase) == 0.0          # calm tape -> no tax
    assert ss._risk_tax({"stress": 0.8}, chase) > 0.4           # chase into stress -> taxed
    assert ss._risk_tax({"stress": 0.8}, wash) == 0.0           # washout protected even in stress


def test_calm_overlay_is_a_noop():
    rec = _rec()
    base = ss.conviction_profile(rec, "US")
    calm = ss.conviction_profile(rec, "US", ctx={"risk_overlay": {"stress": 0.0}})
    assert base["composite_z"] == calm["composite_z"] and calm["risk"] is None


def test_stress_vetoes_high_conviction_on_a_chase():
    # strong edge + good entry + moderately extended (aggressive, but <30% so not T1-blocked)
    rec = {"sue": 2.6, "insider_bps": 30.0, "alpha": 1.2,
           "ladder": {"state": "RALLY ON", "label": "UPTREND", "dir": "up",
                      "entry": {"urgency": "now"}},
           "tech": {"off_52w_high_pct": -5.0, "rsi14": 58.0, "pct_vs_200dma": 26.0}}
    calm = ss.conviction_profile(rec, "US", ctx={"risk_overlay": {"stress": 0.0}})
    hot = ss.conviction_profile(rec, "US", ctx={"risk_overlay": {"stress": 0.8}})
    assert "high-conviction" in calm["verdict"].lower()          # calm -> high-conviction
    assert "high-conviction" not in hot["verdict"].lower()       # stress -> vetoed
    assert "elevated-risk" in hot["verdict"].lower()
    assert hot["composite_z"] < calm["composite_z"]              # and taxed
