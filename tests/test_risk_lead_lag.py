"""Risk-gauge honesty layer (research/RISK_FLIP_2026-06-22.md).

On 2026-06-22 the downstream risk read flipped to "all clear" one session before a
real vol event. Root cause: every gauge feeding the classifier is coincident/lagging,
the one leading gauge (breadth divergence) was firewalled, and the contract carried no
freshness stamp. These tests lock in the fixes:

  • `lead_lag` tags on the five risk gauges (so the bot can discount coincident gauges)
  • `drawdown_risk` tagged lagging; since the PIT re-measure (#887, audit #39) its low
    band is a MEASURED conditional prob BELOW the base rate (~10% vs ~19%), carried with
    a measured-basis stat_passport — no longer a bare base-rate read
  • `complacency.breadth_div` promoted to a ONE-WAY risk-OFF caution, firewall preserved
  • a `freshness` stamp that flags the Juneteenth-stale 06-18→06-22 window
  • a replay assertion: the 06-22 fragile state no longer prints an unqualified all-clear
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import dislocation as dz  # noqa: E402
from engine.conditions import conditions_snapshot  # noqa: E402
from engine.run import freshness_stamp  # noqa: E402


# --- frame helpers (mirrors tests/test_conditions.py) ------------------------
def _frame(n: int = 400, **overrides) -> pd.DataFrame:
    """A plausible feature frame with all conditions inputs present (calm tape)."""
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.arange(n, dtype=float)
    f = pd.DataFrame(index=idx)
    f["SPY"] = 400 + np.cumsum(np.sin(rng / 9) * 0.4)
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
    f["initial_claims"] = 220 + 5 * np.sin(rng / 20)
    f["initial_claims_4wk"] = 222 + 3 * np.sin(rng / 25)
    f["continued_claims"] = 1800 + 20 * np.sin(rng / 30)
    f["indeed_postings"] = 120 - rng * 0.01
    f["indeed_new_postings"] = 118 - rng * 0.01
    f["news_sentiment"] = 0.05 * np.sin(rng / 15)
    f["sticky_cpi"] = 0.30
    f["flex_cpi"] = 0.50
    f["median_cpi"] = 3.5
    f["umich_infl_exp"] = 3.0
    for k, v in overrides.items():
        f[k] = v
    return f


def _fragile_frame(n: int = 600) -> pd.DataFrame:
    """The 2026-06-22 'calm but fragile' state: cheap VIX + contango (calm surface)
    while SPY presses its high on a THINNING tape (breadth divergence)."""
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


# --- lead_lag tags on the five gauges ----------------------------------------
def test_lead_lag_tags_present_on_all_five_gauges() -> None:
    snap = conditions_snapshot(_frame())
    assert snap["systemic_stress"]["lead_lag"] == "coincident"
    assert snap["drawdown_risk"]["lead_lag"] == "lagging"
    assert snap["risk_appetite"]["vix_term_lead_lag"] == "coincident"
    assert snap["complacency"]["lead_lag"] == "leading"
    # dislocation gauge — minimal calm tape
    idx = pd.date_range("2025-01-01", periods=400, freq="B")
    f = pd.DataFrame({"SPY": pd.Series(range(400), index=idx, dtype=float) + 100})
    dsnap = dz.snapshot(f)
    assert dsnap["lead_lag"] == "coincident"
    assert dsnap["verdict"] == "calm"          # the labeling did not change the verdict


# --- drawdown_risk: low band is a measured prob below base, still tagged lagging ---
def test_drawdown_low_band_is_flagged_base_rate_not_forward_prob() -> None:
    # the gauge needs ~570+ rows to populate (5y z-lookback + 10y expanding pctile)
    dr = conditions_snapshot(_frame(700))["drawdown_risk"]
    assert dr["band"] == "low"
    assert dr["lead_lag"] == "lagging"
    # since #887 the low band no longer equals base: it is a measured conditional
    # probability BELOW the base rate (PIT frame, claims leg), so the base-rate
    # relabel is retired — the honesty now travels via the measured stat_passport.
    assert dr["is_base_rate"] is False
    assert dr["dd10_prob_informative"] is True
    assert dr["dd10_prob_pct"] < dr["base_rate_pct"]
    assert dr["stat_passport"]["basis"] == "measured"
    assert "lagging" in dr["label"].lower()
    assert dr["label_zh"]                        # bilingual label present
    assert "macro/credit" in dr["basis"].lower()


def test_drawdown_band_flags_are_internally_consistent() -> None:
    """is_base_rate is retired (always False); dd10_prob_informative mirrors band presence."""
    for f in (_frame(), _fragile_frame(), _frame(700)):
        dr = conditions_snapshot(f)["drawdown_risk"]
        band = dr["band"]
        assert dr["is_base_rate"] is False
        assert dr["dd10_prob_informative"] == (band is not None)


def test_drawdown_elevated_band_marks_probability_informative() -> None:
    """Force the macro/credit composite into a high percentile at the tail and confirm
    the conditional probability is then marked informative (NOT the base rate)."""
    f = _frame(700)
    n = len(f)
    for col, base, spike in (("nfci", -0.4, 2.5), ("ebp", -0.3, 3.0), ("hy_oas", 3.5, 9.0)):
        s = np.full(n, base)
        s[-40:] = np.linspace(base, spike, 40)         # sharp tail spike vs ~5y history
        f[col] = s
    dr = conditions_snapshot(f)["drawdown_risk"]
    assert dr["band"] in ("elevated", "high", "extreme"), dr["band"]
    assert dr["is_base_rate"] is False
    assert dr["dd10_prob_informative"] is True
    assert dr["dd10_prob_pct"] > dr["base_rate_pct"]


# --- complacency.breadth_div -> one-way risk-OFF caution ----------------------
def test_breadth_div_promoted_to_one_way_caution() -> None:
    comp = conditions_snapshot(_fragile_frame())["complacency"]
    assert comp["breadth_div"] is True
    assert comp["breadth_div_caution"] is True
    assert comp["caution"] is True
    assert comp["caution_reason"]                # english reason present
    assert comp["caution_reason_zh"]             # bilingual reason present


def test_caution_is_one_way_off_when_breadth_confirms() -> None:
    # calm surface but breadth BROADENING -> no divergence -> caution stays OFF
    f = _fragile_frame()
    rng = np.arange(len(f), dtype=float)
    f["pct_above_200"] = np.linspace(45, 88, len(f)) + np.sin(rng / 12)
    comp = conditions_snapshot(f)["complacency"]
    assert comp["breadth_div"] is False
    assert comp["breadth_div_caution"] is False
    assert comp["caution"] is False
    assert comp["caution_reason"] is None


def test_breadth_div_caution_never_contaminates_scoring_surfaces() -> None:
    """The promotion is a CONTRACT caution only — it must not leak into the validated
    quad / axes / macro-risk score (the firewall is preserved)."""
    root = Path(__file__).resolve().parent.parent
    axes_src = (root / "engine" / "axes.py").read_text()
    regime_src = (root / "engine" / "regime.py").read_text()
    cond_src = (root / "engine" / "conditions.py").read_text()
    mrs_region = cond_src[cond_src.index("def _macro_risk_legs"):]
    for src in (axes_src, regime_src, mrs_region):
        assert "breadth_div_caution" not in src
        assert "caution_reason" not in src


# --- freshness / staleness guard ---------------------------------------------
def test_freshness_fresh_when_asof_is_build_day() -> None:
    fr = freshness_stamp("2026-06-23", now="2026-06-23")
    assert fr["age_sessions"] == 0
    assert fr["stale"] is False
    assert fr["asof"] == "2026-06-23" and fr["built_at"].endswith("Z")


def test_freshness_prior_session_is_not_stale_by_default() -> None:
    # intraday before tonight's post-close build: asof = prior session, age 1 -> OK
    fr = freshness_stamp("2026-06-22", now="2026-06-23")   # Mon -> Tue
    assert fr["age_sessions"] == 1
    assert fr["stale"] is False


def test_freshness_flags_the_juneteenth_0618_to_0622_window() -> None:
    """The actual incident: a 2026-06-18 contract consumed on 2026-06-22 must read STALE."""
    fr = freshness_stamp("2026-06-18", now="2026-06-22")   # Thu -> Mon, Fri = Juneteenth
    assert fr["age_days"] == 4
    assert fr["age_sessions"] >= 2
    assert fr["stale"] is True


# --- replay regression: 06-22 no longer prints an unqualified all-clear -------
def _replay_0622_frame(n: int = 700) -> pd.DataFrame:
    """Faithful replay of the real 2026-06-22 state: calm surface (cheap VIX + contango)
    + breadth divergence (SPY at its high on a thinning tape) but BENIGN credit, so the
    macro/credit drawdown gauge correctly reads LOW (band='low', the base-rate case)."""
    f = _frame(n)
    rng = np.arange(n, dtype=float)
    f["SPY"] = 300 + np.cumsum(np.full(n, 0.25)) + np.sin(rng / 9) * 0.3   # rising to a high
    f["vix"] = np.linspace(30, 16, n) + np.sin(rng / 15) * 0.5             # cheap, calm
    f["vix3m"] = f["vix"] + 3.0                                            # contango
    f["pct_above_200"] = np.linspace(85, 45, n) + np.sin(rng / 12) * 1.5   # thinning tape
    f["hy_oas"] = 3.0 + 0.1 * np.sin(rng / 40)                            # benign credit
    return f


def test_replay_0622_does_not_print_unqualified_all_clear() -> None:
    """Acceptance: replaying the 2026-06-22 state, the coincident/lagging gauges still
    read calm — but the contract is no longer an unqualified all-clear. (a) drawdown_risk
    is tagged lagging and its low read is a measured conditional prob below base with a
    measured-basis passport (post-#887), and (b) the leading breadth-divergence caution
    fires."""
    snap = conditions_snapshot(_replay_0622_frame())
    dr, comp = snap["drawdown_risk"], snap["complacency"]
    # (a) the lagging gauge no longer masquerades as a forward all-clear
    assert dr["band"] == "low"
    assert dr["lead_lag"] == "lagging"
    assert dr["is_base_rate"] is False and dr["dd10_prob_informative"] is True
    assert dr["dd10_prob_pct"] < dr["base_rate_pct"]
    assert dr["stat_passport"]["basis"] == "measured"
    # (b) at least one honest caution is raised even while the surface reads calm
    assert comp["breadth_div"] is True and comp["caution"] is True
    # and the contract that day is stale-flagged through the holiday window
    assert freshness_stamp("2026-06-18", now="2026-06-22")["stale"] is True


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
