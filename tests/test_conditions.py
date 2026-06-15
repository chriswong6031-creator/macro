"""Tests for the complementary conditions/nowcast/risk-appetite layer
(engine/conditions.py) and its alert rules. Engineered frames + graceful
degradation. See research/QUANT_FACTOR_EXPANSION.md."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.alerts import (  # noqa: E402
    conditions_recession_state_change,
    ebp_widening,
    nfci_tightening,
    sahm_trigger,
)
from engine.conditions import conditions_frame, conditions_snapshot  # noqa: E402


def _frame(n: int = 400, **overrides) -> pd.DataFrame:
    """A plausible feature frame with all conditions inputs present."""
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.arange(n, dtype=float)
    spy = 400 + np.cumsum(np.sin(rng / 9) * 0.4)        # gently wiggling equity
    f = pd.DataFrame(index=idx)
    f["SPY"] = spy
    f["vix"] = 16 + 3 * np.sin(rng / 30)
    f["vix3m"] = 18 + 2 * np.sin(rng / 30)
    f["skew"] = 130 + 8 * np.sin(rng / 40)
    f["us10y"] = 4.0 + 0.3 * np.sin(rng / 50)
    f["hy_oas"] = 3.5 + 0.4 * np.sin(rng / 45)
    f["copper_gold"] = 0.18 + 0.01 * np.sin(rng / 35)
    f["dxy"] = 103 + 2 * np.sin(rng / 60)
    f["spread_2s10s"] = 0.2 + 0.2 * np.sin(rng / 70)
    f["term_premium_10y"] = 0.4
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"]
    f["nfci"] = -0.4 + 0.1 * np.sin(rng / 25)
    f["anfci"] = -0.2
    f["nfci_risk"] = -0.5
    f["nfci_credit"] = -0.05
    f["nfci_leverage"] = 0.4
    f["stlfsi"] = -0.8
    f["sahm"] = 0.10
    f["recession_prob"] = 1.0
    f["ebp"] = -0.3
    f["ebp_recession_prob"] = 0.08
    f["wei"] = 2.5
    f["gdpnow"] = 2.8
    # high-frequency real-activity / labor nowcast inputs
    f["initial_claims"] = 220 + 5 * np.sin(rng / 20)
    f["initial_claims_4wk"] = 222 + 3 * np.sin(rng / 25)
    f["continued_claims"] = 1800 + 20 * np.sin(rng / 30)
    f["indeed_postings"] = 120 - rng * 0.01
    f["indeed_new_postings"] = 118 - rng * 0.01
    f["news_sentiment"] = 0.05 * np.sin(rng / 15)
    f["sticky_cpi"] = 0.30      # monthly %
    f["flex_cpi"] = 0.50
    f["median_cpi"] = 3.5
    f["umich_infl_exp"] = 3.0
    for k, v in overrides.items():
        f[k] = v
    return f


# --- conditions engine -------------------------------------------------------

def test_snapshot_has_all_blocks() -> None:
    snap = conditions_snapshot(_frame())
    for block in ("financial_conditions", "recession", "growth_nowcast",
                  "labor_nowcast", "inflation_nowcast", "risk_appetite"):
        assert block in snap
    assert snap["financial_conditions"]["state"] in ("loose", "neutral", "tight")


def test_labor_nowcast_block_populates() -> None:
    snap = conditions_snapshot(_frame())
    lab = snap["labor_nowcast"]
    assert lab["initial_claims_4wk"] is not None
    assert lab["continued_claims"] is not None
    assert lab["claims_trend"] in ("rising", "falling")
    assert lab["indeed_trend"] in ("rising", "falling")
    assert lab["read"] in ("labor cooling", "labor firm", "labor mixed")
    # SF Fed news sentiment surfaces in the risk-appetite read, not the roro composite
    assert "news_sentiment" in snap["risk_appetite"]
    assert snap["risk_appetite"]["news_sentiment_state"] in ("optimistic", "pessimistic")


def test_labor_reads_cooling_when_claims_surge_and_demand_falls() -> None:
    # claims +30% over the trailing year, Indeed postings sliding hard
    n = 400
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.arange(n, dtype=float)
    surge = np.where(rng < n - 252, 200.0, 200.0 + (rng - (n - 252)) * 0.30)
    f = _frame(n=n)
    f["initial_claims_4wk"] = pd.Series(surge, index=idx)
    f["initial_claims"] = pd.Series(surge, index=idx)
    f["indeed_postings"] = pd.Series(130 - rng * 0.15, index=idx)  # steep demand fade (>5%/3m)
    snap = conditions_snapshot(f)
    lab = snap["labor_nowcast"]
    assert lab["claims_trend"] == "rising"
    assert lab["indeed_trend"] == "falling"
    assert lab["read"] == "labor cooling"


def test_recession_score_low_when_calm() -> None:
    snap = conditions_snapshot(_frame())
    assert snap["recession"]["score"] is not None
    assert snap["recession"]["label"] == "low"


def test_recession_score_high_when_sahm_and_inverted() -> None:
    f = _frame(sahm=0.9, recession_prob=70.0, ebp_recession_prob=0.6)
    f["spread_2s10s"] = -1.2
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"]
    # a real recession has jobless claims surging too — keep the (now-wired) claims
    # leg consistent so it supports rather than dilutes the high read
    rng = np.arange(len(f), dtype=float)
    surge = np.where(rng < len(f) - 252, 200.0, 200.0 + (rng - (len(f) - 252)) * 0.45)
    f["initial_claims_4wk"] = pd.Series(surge, index=f.index)
    snap = conditions_snapshot(f)
    assert snap["recession"]["score"] > 55
    assert snap["recession"]["label"] == "high"


def test_claims_is_primary_labor_leg_and_replaces_sahm() -> None:
    # Validated claims leg is LIVE and PRIMARY: surging claims raise recession_risk
    # vs flat, surface as a 'claims' component, and REPLACE the Sahm leg (Sahm is the
    # fallback, so it is absent from the composite while claims is present).
    n = 400
    rng = np.arange(n, dtype=float)
    flat = _frame(n=n)                                   # default ~flat claims
    surged = _frame(n=n)
    surge = np.where(rng < n - 252, 200.0, 200.0 + (rng - (n - 252)) * 0.50)
    surged["initial_claims_4wk"] = pd.Series(surge, index=surged.index)
    base = conditions_snapshot(flat)["recession"]
    hot = conditions_snapshot(surged)["recession"]
    assert "claims" in hot["components"]
    assert "sahm" not in hot["components"]               # claims replaces Sahm in the score
    assert hot["score"] > base["score"]


def test_sahm_is_fallback_when_claims_feed_absent() -> None:
    # graceful degradation: with no claims columns, Sahm carries the labor leg
    f = _frame().drop(columns=["initial_claims_4wk", "initial_claims"])
    comp = conditions_snapshot(f)["recession"]["components"]
    assert "claims" not in comp
    assert "sahm" in comp


def test_term_premium_adjusted_curve_flags_false_inversion() -> None:
    # raw curve inverted but a big term premium lifts the adjusted slope positive
    f = _frame()
    f["spread_2s10s"] = -0.3
    f["term_premium_10y"] = 0.6
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"]
    note = conditions_snapshot(f)["recession"]["curve_note"]
    assert "not a recession signal" in note


def test_vol_target_scalar_bounded() -> None:
    fr = conditions_frame(_frame())
    s = fr["vol_target_scalar"].dropna()
    assert (s >= 0.5).all() and (s <= 1.5).all()


def test_vrp_and_corr_present() -> None:
    fr = conditions_frame(_frame())
    assert "vrp" in fr and fr["vrp"].notna().any()
    assert "stock_bond_corr" in fr and fr["stock_bond_corr"].notna().any()


def test_graceful_when_inputs_missing() -> None:
    # only SPY present — everything else absent; must not crash, returns Nones
    idx = pd.bdate_range("2023-01-02", periods=120)
    f = pd.DataFrame({"SPY": np.linspace(400, 420, 120)}, index=idx)
    snap = conditions_snapshot(f)
    assert snap["recession"]["score"] is None
    assert snap["financial_conditions"]["nfci"] is None


# --- conditions alert rules --------------------------------------------------

def test_sahm_trigger_fires_on_cross() -> None:
    f = _frame(n=10)
    f["sahm"] = [0.2] * 9 + [0.55]
    a = sahm_trigger(pd.DataFrame(), f)
    assert a is not None and a.severity == "act"


def test_sahm_trigger_silent_below() -> None:
    f = _frame(n=10, sahm=0.2)
    assert sahm_trigger(pd.DataFrame(), f) is None


def test_nfci_tightening_fires_on_cross() -> None:
    f = _frame(n=10)
    f["nfci"] = [0.1] * 9 + [0.8]      # crosses the default 0.65 threshold
    a = nfci_tightening(pd.DataFrame(), f)
    assert a is not None and a.severity == "warn"


def test_recession_band_change_fires() -> None:
    # ramp recession risk up so the latest day jumps a band — claims (now the PRIMARY
    # labor leg) and the NY-Fed prob both spike on the final day
    f = _frame(n=300)
    ic = np.full(300, 200.0)
    ic[-1] = 320.0                       # +60% y/y on the last day -> claims leg ~1
    f["initial_claims_4wk"] = pd.Series(ic, index=f.index)
    f["initial_claims"] = pd.Series(ic, index=f.index)
    rp = np.full(300, 1.0)
    rp[-1] = 80.0
    f["recession_prob"] = rp
    a = conditions_recession_state_change(pd.DataFrame(), f)
    assert a is not None and "->" in a.message


def test_ebp_widening_handles_short_history() -> None:
    f = _frame(n=10)              # too few distinct EBP prints
    assert ebp_widening(pd.DataFrame(), f) is None


# --- complacency / hidden-fragility gauge (DISPLAY-ONLY mirror of capitulation) -
def _fragile_frame(n: int = 600) -> pd.DataFrame:
    """A 'calm but fragile' tape: VIX drifting to multi-year lows + steep
    contango (calm surface) while SPY presses its highs on THINNING breadth and
    HY credit quietly widens (weak internals)."""
    f = _frame(n)
    rng = np.arange(n, dtype=float)
    f["SPY"] = 300 + np.cumsum(np.full(n, 0.25)) + np.sin(rng / 9) * 0.3   # rising to a high
    f["vix"] = np.linspace(34, 12, n) + np.sin(rng / 15) * 0.5             # fear -> cheap
    f["vix3m"] = f["vix"] + 4.0                                            # steep contango
    f["pct_above_200"] = np.linspace(85, 45, n) + np.sin(rng / 12) * 1.5   # thinning tape
    hy = np.full(n, 3.0)
    hy[-30:] = 3.0 + np.arange(30) * 0.03                                  # widening last ~6wk
    f["hy_oas"] = hy
    return f


def test_snapshot_has_complacency_block() -> None:
    comp = conditions_snapshot(_frame())["complacency"]
    for k in ("calm", "fragility", "warning", "strong", "state",
              "vix_low", "contango", "breadth_div", "credit_widen"):
        assert k in comp, k
    assert comp["state"] in ("hidden_fragility", "watch", "calm", "neutral")


def test_complacency_warns_on_calm_over_weak_internals() -> None:
    comp = conditions_snapshot(_fragile_frame())["complacency"]
    assert comp["calm"] == 2 and comp["fragility"] == 2     # both sides lit
    assert comp["vix_low"] and comp["contango"]
    assert comp["breadth_div"] and comp["credit_widen"]
    assert comp["warning"] and comp["strong"]
    assert comp["state"] == "hidden_fragility"


def test_complacency_calm_alone_is_not_a_warning() -> None:
    # calm surface (low VIX + contango) but internals CONFIRM: breadth rising,
    # credit tightening -> no fragility legs, so no warning fires.
    f = _fragile_frame()
    rng = np.arange(len(f), dtype=float)
    f["pct_above_200"] = np.linspace(45, 88, len(f)) + np.sin(rng / 12)     # broadening
    f["hy_oas"] = np.linspace(4.2, 3.0, len(f))                            # tightening
    comp = conditions_snapshot(f)["complacency"]
    assert comp["calm"] >= 1 and comp["fragility"] == 0
    assert not comp["warning"] and not comp["strong"]
    assert comp["state"] == "calm"


def test_complacency_graceful_without_breadth_or_credit() -> None:
    # no breadth feed and no HY OAS -> fragility legs simply absent, never crash.
    f = _frame()
    f = f.drop(columns=[c for c in ("hy_oas",) if c in f.columns])
    assert "pct_above_200" not in f.columns
    comp = conditions_snapshot(f)["complacency"]
    assert comp["fragility"] is None            # no fragility legs computed
    assert not comp["warning"]
    assert comp["state"] in ("calm", "neutral")


def test_complacency_is_display_only_never_scored() -> None:
    # The load-bearing invariant: no SCORING surface may read the complacency
    # columns — not the quad (regime.py), not the axes, not the macro-risk score.
    root = Path(__file__).resolve().parent.parent
    axes_src = (root / "engine" / "axes.py").read_text()
    regime_src = (root / "engine" / "regime.py").read_text()
    cond_src = (root / "engine" / "conditions.py").read_text()
    mrs_region = cond_src[cond_src.index("def _macro_risk_legs"):]   # the MRS surface
    for src in (axes_src, regime_src, mrs_region):
        assert "complacency" not in src
        assert "complacency_calm" not in src and "complacency_fragility" not in src
