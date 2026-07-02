"""Tests for engine.vol_shock_scorecard — the forward vol-shock risk gauge.

Covers: full-input fusion, the points-sum-to-score invariant, graceful
renormalization when factors drop out, all-missing -> hidden card, the
never-raises contract on malformed input, the capped/young factor rules, and the
forward-outcome log roundtrip (append -> resolve -> track_record).
"""
from __future__ import annotations

import pytest

from engine import vol_shock_scorecard as vss


def _full_latest() -> dict:
    """A representative latest.json-shaped dict with every leading factor present."""
    return {
        "date": "2026-06-18",
        "market_gamma": {  # sibling S2's first-class field
            "regime": "short", "spot_vs_flip_pct": -0.5,
            "net_gex_bn": -2.0, "gamma_flip": 7461.0,
        },
        "cross_asset": {"asof": "2026-06-18", "absorption_pctile_5y": 0.94},
        "dislocation": {"asof": "2026-06-18", "inputs": {"vix": 16.4, "vix_term": 0.98}},
        "turning_point": {"present": False, "state": "normal",
                          "drivers": {"one_factor": True}},
        "conditions": {
            "complacency": {"state": "watch", "warning": True, "breadth_div": True},
            "drawdown_risk": {"score": 13.8, "band": "low"},
            "risk_appetite": {"vrp_pctile": 0.13, "skew_pctile": 0.50,
                              "vrp_state": "normal", "vix_term": 0.98},
        },
    }


def _vs_sentiment() -> dict:
    return {
        "vol_regime": {"term_ratio": 0.98, "vrp_state": "normal", "skew": 146.7},
        "put_call": {"equity_pct_in_hist": 0.1, "n_obs": 200, "young": False},
    }


# --------------------------------------------------------------------------- #
# Full-input fusion + invariants
# --------------------------------------------------------------------------- #
def test_full_input_score():
    # Audit #29: dealer_gamma is DISPLAY-ONLY (weight 0) while data/gex/gate.json is closed, so
    # only 8 of 9 factors are AVAILABLE (score-bearing) by default. The dealer_gamma row is still
    # present + computed, just gated out of the weighted mean.
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    assert snap is not None
    assert snap["score"] is not None
    assert 0 <= snap["score"] <= 100
    assert snap["band"] in ("low", "elevated", "high", "extreme")
    assert snap["n_available"] == 8          # 9 factors, dealer_gamma gated out (assumption sign)
    assert snap["why"] and snap["why_zh"]
    # every active factor carries the display contract
    for f in snap["factors"]:
        assert set(("key", "label", "label_zh", "value", "points", "weight",
                    "available", "sub", "color", "note")) <= set(f)
    # the dealer_gamma row is present, gated out, and carries an assumption passport
    dg = next(f for f in snap["factors"] if f["key"] == "dealer_gamma")
    assert dg["gated_out"] is True and dg["weight"] == 0.0 and dg["available"] is False
    assert dg["passport"]["basis"] == "assumption"
    assert dg["passport"]["verdict"] == "display-only"


def test_full_input_score_with_gate_open(monkeypatch):
    # With the gate OPEN the dealer_gamma factor rejoins the weighted mean (all 9 available).
    monkeypatch.setattr(vss, "_gex_gate_scored", lambda: True)
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    assert snap["n_available"] == 9
    dg = next(f for f in snap["factors"] if f["key"] == "dealer_gamma")
    assert dg["gated_out"] is False and dg["weight"] > 0 and dg["available"] is True
    assert dg["passport"]["verdict"] == "scored"


def test_points_sum_to_score():
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    total = sum(f["points"] for f in snap["factors"] if f["available"] and f["points"])
    # points are rounded to 1dp; the sum reconstructs the headline within rounding
    assert abs(total - snap["score"]) <= 0.5


def test_dealer_gamma_subscore_computed_even_when_gated_out():
    """The dealer_gamma SUB-score is still computed for display (short-gamma near the flip reads
    high) even though it is gated out of the weighted mean."""
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    dg = next(f for f in snap["factors"] if f["key"] == "dealer_gamma")
    assert dg["gated_out"] is True           # not scored while gate closed
    assert dg["sub"] >= 75                    # short gamma + near flip still shown


def test_short_gamma_raises_vs_long_gamma():
    base = _full_latest()
    long_g = {**base, "market_gamma": {"regime": "long", "spot_vs_flip_pct": 5.0,
                                       "net_gex_bn": 5.0, "gamma_flip": 7000.0}}
    s_short = vss.snapshot(base, vol_sentiment=_vs_sentiment())
    s_long = vss.snapshot(long_g, vol_sentiment=_vs_sentiment())
    dg_short = next(f for f in s_short["factors"] if f["key"] == "dealer_gamma")["sub"]
    dg_long = next(f for f in s_long["factors"] if f["key"] == "dealer_gamma")["sub"]
    assert dg_short > dg_long


# --------------------------------------------------------------------------- #
# Graceful degradation / renormalization
# --------------------------------------------------------------------------- #
def test_missing_one_factor_renormalizes():
    latest = _full_latest()
    latest.pop("cross_asset")           # drop the heaviest-weighted leading factor
    snap = vss.snapshot(latest, vol_sentiment=_vs_sentiment())
    assert snap["score"] is not None
    conc = next(f for f in snap["factors"] if f["key"] == "concentration")
    assert conc["available"] is False
    assert conc["points"] is None
    # remaining points still reconstruct the (renormalized) headline
    total = sum(f["points"] for f in snap["factors"] if f["available"] and f["points"])
    assert abs(total - snap["score"]) <= 0.5


@pytest.mark.parametrize("drop", [
    "cross_asset", "market_gamma", "turning_point", "conditions",
])
def test_each_factor_drop_is_graceful(drop):
    latest = _full_latest()
    latest.pop(drop, None)
    snap = vss.snapshot(latest, vol_sentiment=_vs_sentiment())
    assert snap is not None
    # still a valid renormalized score as long as >=1 factor remains
    if snap["n_available"]:
        assert 0 <= snap["score"] <= 100


def test_all_missing_hides_card(monkeypatch):
    # disable the side-car disk fallbacks so "no factors" is truly hermetic
    monkeypatch.setattr(vss, "_site_dir", lambda: None)
    snap = vss.snapshot({"date": "2026-06-18"})   # no factor sub-trees at all
    assert snap is not None                        # contract shell still returned
    assert snap["score"] is None
    assert snap["band"] is None
    assert snap["n_available"] == 0


def test_empty_and_none_inputs():
    assert vss.snapshot(None) is None
    assert vss.snapshot({}) is None
    assert vss.snapshot([]) is None  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Factor-specific rules
# --------------------------------------------------------------------------- #
def test_put_call_young_downweighted():
    young = {"vol_regime": {"term_ratio": 0.9},
             "put_call": {"equity_pct_in_hist": 0.1, "n_obs": 10, "young": True}}
    snap = vss.snapshot(_full_latest(), vol_sentiment=young)
    pc = next(f for f in snap["factors"] if f["key"] == "put_call")
    base_w = vss.DEFAULTS["weights"]["put_call"]
    assert pc["weight"] < base_w        # effective weight reduced
    assert "young" in pc["note"]


def test_turning_point_capped():
    latest = _full_latest()
    latest["turning_point"] = {"present": True, "state": "fragile"}
    snap = vss.snapshot(latest, vol_sentiment=_vs_sentiment())
    tp = next(f for f in snap["factors"] if f["key"] == "turning_point")
    assert tp["sub"] <= vss.DEFAULTS["turning_point_cap"]


# --------------------------------------------------------------------------- #
# Never-raises contract on malformed input
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [
    {"date": "x", "cross_asset": "not-a-dict"},
    {"date": "x", "cross_asset": {"absorption_pctile_5y": "oops"}},
    {"date": "x", "conditions": {"risk_appetite": None, "complacency": []}},
    {"date": "x", "market_gamma": {"regime": 123, "spot_vs_flip_pct": "nan"}},
    {"date": "x", "turning_point": "broken", "dislocation": 5},
])
def test_never_raises_on_malformed(bad):
    # must not raise, must return a dict with the contract keys
    snap = vss.snapshot(bad)
    assert isinstance(snap, dict)
    assert "score" in snap and "factors" in snap


# --------------------------------------------------------------------------- #
# Forward-outcome log roundtrip
# --------------------------------------------------------------------------- #
def test_forward_log_roundtrip(tmp_path):
    p = tmp_path / "log.jsonl"
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    assert vss.append_log(snap, _full_latest(), path=p) is True
    assert vss.append_log(snap, _full_latest(), path=p) is False  # idempotent per date

    # forward path that triggers the VIX-jump HIT: anchor VIX 16.4 -> high 30 (>1.4x)
    dates = ["2026-06-18"] + [f"2026-06-{d}" for d in range(19, 30)]  # >= horizon ahead
    spy_closes = {d: 100.0 for d in dates}
    spy_closes["2026-06-25"] = 90.0           # -10% drawdown intraday window too
    vix_highs = {d: 16.0 for d in dates}
    vix_highs["2026-06-24"] = 30.0            # VIX jump 30/16.4 = 1.83x >= 1.4x
    n = vss.resolve(spy_closes, vix_highs, path=p)
    assert n == 1

    tr = vss.track_record(path=p)
    assert tr["n"] == 1
    assert tr["hit_rate"] == 1.0
    assert "by_band" in tr


def test_resolve_not_matured_is_skipped(tmp_path):
    p = tmp_path / "log.jsonl"
    snap = vss.snapshot(_full_latest(), vol_sentiment=_vs_sentiment())
    vss.append_log(snap, _full_latest(), path=p)
    # only 3 forward days available (< horizon 10) => not matured => unresolved
    spy_closes = {"2026-06-18": 100.0, "2026-06-19": 100.0,
                  "2026-06-20": 100.0, "2026-06-21": 100.0}
    assert vss.resolve(spy_closes, {}, path=p) == 0
    assert vss.track_record(path=p)["n"] == 0
