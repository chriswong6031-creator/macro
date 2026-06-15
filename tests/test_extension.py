"""Unit tests for engine/extension.py — the display-only extension / exhaustion axis.

These lock the validated semantics: ext_z is own-history extension, the parabolic flag is
the >2σ tail, valuation-vs-own-history reads the right tail, and the cohort gauge tiers.
None of this is ever scored — see reports/top-picks-freshness-phase0.md.
"""
import numpy as np
import pandas as pd
import pytest

from engine.extension import (cohort_stretch, extension_signals, grade,
                              valuation_vs_history)


def _dates(n):
    return pd.bdate_range("2022-01-03", periods=n)


def test_grade_thresholds():
    assert grade(2.5, 0.99) == "parabolic"      # >2σ own-history extension
    assert grade(2.0, 0.5) == "parabolic"
    assert grade(1.4, 0.7) == "stretched"
    assert grade(1.0, 0.99) == "stretched"
    assert grade(0.2, 0.95) == "intrend"        # near highs, not stretched
    assert grade(0.2, 0.50) == "steady"         # not stretched, not near highs
    assert grade(None, 0.9) == "na"
    assert grade(float("nan"), 0.9) == "na"


def test_extension_signals_parabolic_vs_steady():
    n = 320
    idx = _dates(n)
    # STEADY: a gentle compounding uptrend → moderate, in-trend extension
    steady = pd.Series(100 * (1.0008) ** np.arange(n), index=idx)
    # SPIKE: flat for most of the window, then a sharp late run-up → high ext_z, near highs
    base = np.concatenate([np.full(n - 25, 100.0),
                           100 * (1.05) ** np.arange(1, 26)])
    spike = pd.Series(base, index=idx)
    closes = pd.DataFrame({"STEADY": steady, "SPIKE": spike})

    out = extension_signals(closes)
    assert {"STEADY", "SPIKE"} <= set(out)
    # the late spike is far more extended vs its own history than the steady grinder
    assert out["SPIKE"]["ext_z"] > out["STEADY"]["ext_z"]
    assert out["SPIKE"]["ext_z"] >= 2.0 and out["SPIKE"]["parabolic"] is True
    assert out["SPIKE"]["grade"] == "parabolic"
    # both are pressing their 52-week highs (monotone up to the end)
    assert out["SPIKE"]["near_52wh"] > 0.99
    assert 0.0 < out["STEADY"]["near_52wh"] <= 1.0
    # steady grinder is not flagged parabolic
    assert out["STEADY"]["parabolic"] is False


def test_extension_signals_skips_short_history():
    closes = pd.DataFrame({"NEW": pd.Series(range(50), index=_dates(50), dtype=float)})
    assert extension_signals(closes) == {}            # < the rolling minimums → omitted
    assert extension_signals(pd.DataFrame()) == {}


def test_valuation_vs_history_richest_when_price_runs_up():
    n = 300
    idx = _dates(n)
    # price triples over the window → current earnings yield is the lowest it's been
    price = pd.Series(np.linspace(50, 150, n), index=idx)
    closes = pd.DataFrame({"RICH": price})
    panel = pd.DataFrame({"ticker": ["RICH"], "asof_date": [pd.Timestamp("2021-06-01")],
                          "ni": [1_000_000.0], "shares": [1_000_000.0]})  # EPS = 1.0, constant
    out = valuation_vs_history(closes, panel)
    assert "RICH" in out
    assert out["RICH"]["ey_pctile"] <= 10            # richest decile of its own history
    assert out["RICH"]["val_label"] == "richest"


def test_valuation_vs_history_cheap_when_price_falls():
    n = 300
    idx = _dates(n)
    price = pd.Series(np.linspace(150, 50, n), index=idx)   # price falls → EY rises → cheap
    closes = pd.DataFrame({"CHEAP": price})
    panel = pd.DataFrame({"ticker": ["CHEAP"], "asof_date": [pd.Timestamp("2021-06-01")],
                          "ni": [1_000_000.0], "shares": [1_000_000.0]})
    out = valuation_vs_history(closes, panel)
    assert out["CHEAP"]["ey_pctile"] >= 66
    assert out["CHEAP"]["val_label"] == "cheap"


def test_valuation_vs_history_degrades_gracefully():
    assert valuation_vs_history(pd.DataFrame(), pd.DataFrame()) == {}
    # ticker with no fundamentals row is simply absent
    closes = pd.DataFrame({"X": pd.Series(range(300), index=_dates(300), dtype=float)})
    assert valuation_vs_history(closes, pd.DataFrame(
        {"ticker": [], "asof_date": [], "ni": [], "shares": []})) == {}


def test_cohort_stretch_tiers():
    assert cohort_stretch([{"ext_z": 0.0}] * 3)["state"] == "na"      # too few names
    normal = [{"ext_z": 0.0, "grade": "steady", "near_52wh": 0.7} for _ in range(20)]
    assert cohort_stretch(normal)["state"] == "normal"
    stretched = [{"ext_z": 1.5, "grade": "stretched", "near_52wh": 0.99} for _ in range(20)]
    s = cohort_stretch(stretched)
    assert s["state"] == "stretched"
    assert s["pct_stretched"] == 100 and s["n"] == 20


def test_extension_signals_never_returns_nan_fields():
    out = extension_signals(pd.DataFrame(
        {"A": pd.Series(100 * (1.001) ** np.arange(320), index=_dates(320))}))
    for v in out.values():
        assert not (isinstance(v["ext_z"], float) and np.isnan(v["ext_z"]))
        assert v["grade"] in {"intrend", "steady", "stretched", "parabolic"}
