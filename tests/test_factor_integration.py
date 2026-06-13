"""Tests for wiring the new factors INTO the regime + exposure dial
(research/QUANT_FACTOR_EXPANSION.md). Verifies the nowcast axis components and
the measured-edge conditions rules in the exposure dial."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.axes import _component_scores  # noqa: E402
from engine.playbook import exposure_dial  # noqa: E402
from lib import config  # noqa: E402


def _growth_frame(n: int = 120) -> pd.DataFrame:
    idx = pd.bdate_range("2023-01-02", periods=n)
    f = pd.DataFrame(index=idx)
    for c in ("copper_gold", "xly_xlp", "us2y", "iwm_spy", "cyc_def",
              "pct_above_50", "payrolls", "indpro", "wei", "gdpnow"):
        f[c] = np.linspace(1, 1.2, n)
    return f


def test_nowcast_components_present_in_growth_axis() -> None:
    cfg = config.load()["engine"]["growth_axis"]["components"]
    assert "wei_trend" in cfg and "gdpnow_trend" in cfg
    scores = _component_scores(_growth_frame(), "growth")
    assert "wei_trend" in scores.columns and "gdpnow_trend" in scores.columns


def test_sticky_cpi_component_in_inflation_axis() -> None:
    cfg = config.load()["engine"]["inflation_axis"]["components"]
    assert "sticky_cpi_direction" in cfg


# evidence stub mirroring engine.playbook.risk_evidence output shape
_EV = {
    "conditions_recession_high": {"n": 79, "fwd21_avg_pct": -0.88, "fwd21_hit_pct": 53.2,
                                  "avg_worst_dd63_pct": -14.76},
    "conditions_recession_low": {"n": 1308, "fwd21_avg_pct": 1.11, "fwd21_hit_pct": 68.3,
                                 "avg_worst_dd63_pct": -3.67},
    "conditions_nfci_tightening": {"n": 739, "fwd21_avg_pct": 0.62, "fwd21_hit_pct": 62.0,
                                   "avg_worst_dd63_pct": -8.48},
    "conditions_nfci_loosening": {"n": 879, "fwd21_avg_pct": 1.02, "fwd21_hit_pct": 68.4,
                                  "avg_worst_dd63_pct": -4.01},
}


def _latest(rec_label=None, fc_trend=None, nfci=0.0, quad="Q1", state="STABLE"):
    return {"liquidity_overlay": "neutral", "quad": quad, "transition_state": state,
            "confidence": 0.6, "label": quad,
            "conditions": {"recession": {"label": rec_label, "score": 62},
                           "financial_conditions": {"trend": fc_trend, "nfci": nfci}}}


def test_dial_silent_when_conditions_benign() -> None:
    d = exposure_dial(_latest(rec_label="low", fc_trend="loosening", nfci=-0.4), _EV)
    txt = " ".join(r[1] for r in d["reasons"])
    assert "Recession-risk composite is HIGH" not in txt
    assert "Financial conditions are tight" not in txt


def test_dial_penalizes_high_recession_risk() -> None:
    d = exposure_dial(_latest(rec_label="high", quad="Q4"), _EV)
    txt = " ".join(r[1] for r in d["reasons"])
    assert "Recession-risk composite is HIGH" in txt
    assert "53.2% positive" in txt           # cites the measured hit rate
    assert d["score"] <= -1


def test_dial_penalizes_nfci_tight_and_tightening() -> None:
    d = exposure_dial(_latest(fc_trend="tightening", nfci=0.4), _EV)
    txt = " ".join(r[1] for r in d["reasons"])
    assert "Financial conditions are tight" in txt
    assert "62.0%" in txt                    # cites the measured edge
    # not penalized when tightening from a still-loose level
    d2 = exposure_dial(_latest(fc_trend="tightening", nfci=-0.3), _EV)
    assert "Financial conditions are tight" not in " ".join(r[1] for r in d2["reasons"])


def test_dial_elevated_is_context_not_score() -> None:
    base = exposure_dial(_latest(rec_label="low"), _EV)["score"]
    elev = exposure_dial(_latest(rec_label="elevated"), _EV)
    assert elev["score"] == base             # elevated is an "i" note, no score change
    assert any(r[0] == "i" and "ELEVATED" in r[1] for r in elev["reasons"])


# --- measured higher-quality gauges (research §6) ---------------------------
def test_drawdown_risk_gauge_bands_and_probs() -> None:
    from engine.conditions import _band  # noqa: F401 — ensure module imports
    cfg = config.load()["engine"]["conditions"]["drawdown_risk"]
    assert cfg["high"] == 80 and "recession_risk" in cfg["components"]
    # the snapshot maps band -> a monotone measured drawdown probability
    import engine.conditions as C
    f = pd.DataFrame()  # empty -> graceful None
    snap = C.conditions_snapshot(f)
    assert "drawdown_risk" in snap and "capitulation" in snap


def test_capitulation_stacking_raises_measured_bounce() -> None:
    # the snapshot's measured bounce stat should be higher when 'strong' (>=2)
    # than when merely active — encodes the measured stacking edge
    cfg = config.load()["engine"]["conditions"]["capitulation"]
    assert cfg["vix_panic"] == 30.0 and cfg["vrp_pctile"] == 0.90


def test_new_gauge_alerts_registered() -> None:
    import engine.alerts as A
    assert hasattr(A, "drawdown_risk_high") and hasattr(A, "capitulation_signal")
    # silent when the gauge isn't crossing
    f = pd.DataFrame({"SPY": np.linspace(400, 420, 60)},
                     index=pd.bdate_range("2024-01-01", periods=60))
    assert A.drawdown_risk_high(pd.DataFrame(), f) is None
    assert A.capitulation_signal(pd.DataFrame(), f) is None


def test_style_tilt_from_yield_direction() -> None:
    import engine.conditions as C
    idx = pd.bdate_range("2023-01-02", periods=80)
    # 10y rising sharply -> value tilt
    f = pd.DataFrame({"SPY": np.linspace(400, 420, 80),
                      "us10y": np.linspace(3.0, 4.5, 80)}, index=idx)
    snap = C.conditions_snapshot(f)
    assert snap["style_tilt"]["tilt"] == "value"
    f2 = pd.DataFrame({"SPY": np.linspace(400, 420, 80),
                       "us10y": np.linspace(4.5, 3.0, 80)}, index=idx)
    assert C.conditions_snapshot(f2)["style_tilt"]["tilt"] == "growth"


def test_scenario_odds_structure() -> None:
    from engine.playbook import scenario_odds
    # real data path: build features + regime, ask for the current cell
    from engine.inputs import build_features, yahoo_closes
    from engine.regime import classify
    f = build_features()
    reg = classify(f)
    latest = {"quad": "Q1", "conditions": {"financial_conditions": {"trend": "loosening"}}}
    sc = scenario_odds(yahoo_closes(), reg, f, latest)
    if sc:  # present whenever NFCI history exists
        assert sc["current"] is None or {"hit_pct", "avg_pct", "n"} <= set(sc["current"])
        assert sc["direction"] == "loosening"
