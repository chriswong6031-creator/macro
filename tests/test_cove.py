"""CoVe entailment gate (engine/cove.py) — numeric fabrication detector.

A brief that only cites numbers present in the computed fields passes; one that invents a
level/score is flagged. Unit-aware (%, bps) and rounding-tolerant; advisory fail-rate.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cove import entailment_gate, extract_numbers, verify_claims  # noqa: E402

STATE = {
    "macro": {"vix": 19.2, "quad": "Q1", "macro_risk": {"score": 0.11}},
    "forex": {"dxy": 104.3, "real_yield_10y": 1.85},
    "bonds": {"hy_oas_bps": 320, "curve_10y2y": -0.45},
}


def test_extract_numbers_with_units():
    nums = extract_numbers("VIX 19.2, HY at 320 bps, equities -2.5%, dollar up 1,250")
    vals = {round(v, 3): u for (_r, v, u) in nums}
    assert vals[19.2] == "" and vals[320.0] == "bps" and vals[-2.5] == "pct"
    assert 1250.0 in vals                                     # thousands separator parsed


def test_supported_numbers_pass():
    text = "Q1 with VIX at 19.2 and DXY 104.3; macro-risk score 0.11, real yields 1.85%."
    rep = verify_claims(text, STATE)
    assert rep["fail_rate"] == 0.0 and rep["unsupported"] == 0


def test_fabricated_number_is_flagged():
    text = "VIX spiked to 28 and DXY collapsed to 99.1 — risk-off."   # neither in state
    rep = verify_claims(text, STATE)
    assert rep["unsupported"] >= 2
    assert "28" in rep["unsupported_values"]
    assert rep["fail_rate"] > 0.5


def test_percent_and_bps_unit_matching():
    # state stores 0.11 (fraction) and 320 (bps) — citing them in %/bps form must still match
    rep = verify_claims("macro-risk 11%, HY spread 320 bps", STATE)
    assert rep["fail_rate"] == 0.0


def test_gate_routes_to_review_when_fabrication_spikes():
    good = entailment_gate("VIX 19.2, DXY 104.3", STATE)
    bad = entailment_gate("VIX 28, DXY 99, curve -1.2, score 0.9", STATE)
    assert good["pass"] is True
    assert bad["pass"] is False and bad["fail_rate"] > 0.34


def test_gate_passes_text_with_no_numbers_and_never_raises():
    assert entailment_gate("Liquidity is contracting; watch the curve.", STATE)["pass"] is True
    assert entailment_gate("VIX 19.2", None)["pass"] is True            # no fields → no crash
    assert verify_claims("", STATE)["n_numbers"] == 0
