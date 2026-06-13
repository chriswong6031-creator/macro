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
