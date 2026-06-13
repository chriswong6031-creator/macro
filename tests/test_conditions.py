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
                  "inflation_nowcast", "risk_appetite"):
        assert block in snap
    assert snap["financial_conditions"]["state"] in ("loose", "neutral", "tight")


def test_recession_score_low_when_calm() -> None:
    snap = conditions_snapshot(_frame())
    assert snap["recession"]["score"] is not None
    assert snap["recession"]["label"] == "low"


def test_recession_score_high_when_sahm_and_inverted() -> None:
    f = _frame(sahm=0.9, recession_prob=70.0, ebp_recession_prob=0.6)
    f["spread_2s10s"] = -1.2
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"]
    snap = conditions_snapshot(f)
    assert snap["recession"]["score"] > 55
    assert snap["recession"]["label"] == "high"


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
    # ramp recession risk up so the latest day jumps a band
    f = _frame(n=300)
    sahm = np.full(300, 0.1)
    sahm[-1] = 0.9
    f["sahm"] = sahm
    rp = np.full(300, 1.0)
    rp[-1] = 80.0
    f["recession_prob"] = rp
    a = conditions_recession_state_change(pd.DataFrame(), f)
    assert a is not None and "->" in a.message


def test_ebp_widening_handles_short_history() -> None:
    f = _frame(n=10)              # too few distinct EBP prints
    assert ebp_widening(pd.DataFrame(), f) is None
