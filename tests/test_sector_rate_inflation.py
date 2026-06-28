"""Tests for the display-only per-sector rate/inflation sensitivity overlay.

Covers the channel-split math + gating, graceful degradation, bilingual output, the
tie to the transmission foundation's READ_DRIVERS, and — the load-bearing one — the
DISPLAY-ONLY invariant: the sector HEAT score path never sees the overlay.
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd

from engine import rate_inflation_transmission as rit
from engine import sector_rate_inflation as sri


def _synthetic_frame(n: int = 800) -> pd.DataFrame:
    """A driver-bearing feature frame (mirrors test_rate_inflation_transmission)."""
    idx = pd.bdate_range("2019-01-01", periods=n)
    rng = np.random.default_rng(7)
    walk = lambda base, vol: base + np.cumsum(rng.normal(0, vol, n))  # noqa: E731
    f = pd.DataFrame(index=idx)
    f["us10y"] = walk(3.5, 0.03)
    f["us10y_real"] = walk(1.5, 0.03)
    f["breakeven_10y"] = f["us10y"] - f["us10y_real"]
    f["breakeven_5y5y"] = walk(2.3, 0.02)
    f["spread_2s10s"] = walk(0.2, 0.02)
    f["curve_tp_adj"] = f["spread_2s10s"] + walk(0.1, 0.01)
    f["rate_expectations_proxy"] = walk(-0.3, 0.02)
    f["core_pce_yoy"] = walk(3.0, 0.01)
    f["core_pce_3m_ann"] = f["core_pce_yoy"] + walk(0.0, 0.02)
    f["infl_exp_5y"] = walk(2.4, 0.005)
    return f


# --------------------------------------------------------------------------- #
# channel definition is tied to the foundation
# --------------------------------------------------------------------------- #
def test_channels_partition_the_foundation_read_drivers():
    rate, infl = set(sri.RATE_DRIVERS), set(sri.INFL_DRIVERS)
    # the two channels are disjoint and together are EXACTLY the foundation's live
    # read-drivers (so the overlay can never drift away from the calibrated matrix,
    # and the excluded raw LEVEL drivers stay excluded here too)
    assert rate.isdisjoint(infl)
    assert rate | infl == set(rit.READ_DRIVERS)
    # the sign anchors are a subset of their channel
    assert set(sri.RATE_SIGN_ORDER) <= rate
    assert set(sri.INFL_SIGN_ORDER) <= infl


# --------------------------------------------------------------------------- #
# the per-channel aggregation math + gating
# --------------------------------------------------------------------------- #
def _mat(cells: dict) -> dict:
    return {drv: {"assets": {"XT": c}} for drv, c in cells.items()}


def test_channel_aggregates_only_robust_cells():
    mat = _mat({
        "real10y_chg63": {"ic": -0.20, "verdict": "CONFIRMED"},
        "nom10y_chg63": {"ic": -0.10, "verdict": "DIRECTIONAL"},
        "curve_tp_adj": {"ic": 0.50, "verdict": "CONTEXT"},     # dropped: CONTEXT
        "policy_gap": {"ic": 0.02, "verdict": "CONFIRMED"},     # dropped: |ic| < min_ic
    })
    act = {k: 2.5 for k in sri.RATE_DRIVERS}  # fully activated at the z-cap
    ch = sri._channel(mat, act, "XT", sri.RATE_DRIVERS, sri.RATE_SIGN_ORDER,
                      min_ic=0.04, z_cap=2.5, cut=0.06, ic_strong=0.10)
    # contribution at z == z_cap equals the IC; only the two robust cells count
    assert ch["net"] == -0.30
    assert ch["verdict"] == "headwind"
    assert ch["strength"] == "strong"          # max|ic| 0.20 >= ic_strong
    assert ch["sign"] == -1                      # real10y_chg63 negative => rate-sensitive
    assert ch["measured"] is True
    assert {p["driver"] for p in ch["drivers"]} == {"real10y_chg63", "nom10y_chg63"}
    assert "curve_tp_adj" not in {p["driver"] for p in ch["drivers"]}


def test_channel_measured_but_quiet_is_neutral():
    mat = _mat({"real10y_chg63": {"ic": -0.20, "verdict": "CONFIRMED"}})
    act = {"real10y_chg63": 0.1}                 # barely activated
    ch = sri._channel(mat, act, "XT", sri.RATE_DRIVERS, sri.RATE_SIGN_ORDER,
                      min_ic=0.04, z_cap=2.5, cut=0.06, ic_strong=0.10)
    assert ch["measured"] is True and ch["verdict"] == "neutral"
    assert ch["strength"] == "strong"            # a real measured link, just quiet now


def test_channel_tailwind_sign_and_cap():
    mat = _mat({"corepce_gap": {"ic": 0.15, "verdict": "CONFIRMED"}})
    act = {"corepce_gap": 9.9}                    # extreme z must be capped at z_cap
    ch = sri._channel(mat, act, "XT", sri.INFL_DRIVERS, sri.INFL_SIGN_ORDER,
                      min_ic=0.04, z_cap=2.5, cut=0.06, ic_strong=0.10)
    assert ch["net"] == 0.15 and ch["verdict"] == "tailwind"   # capped => contribution == ic
    assert ch["sign"] == 1


def test_channel_unmeasured_when_all_context():
    mat = _mat({"real10y_chg63": {"ic": -0.20, "verdict": "CONTEXT"},
                "policy_gap": {"ic": -0.30, "verdict": "UNMEASURED"}})
    act = {k: 2.0 for k in sri.RATE_DRIVERS}
    ch = sri._channel(mat, act, "XT", sri.RATE_DRIVERS, sri.RATE_SIGN_ORDER,
                      min_ic=0.04, z_cap=2.5, cut=0.06, ic_strong=0.10)
    assert ch["measured"] is False and ch["net"] == 0.0
    assert ch["strength"] == "weak" and ch["sign"] == 0 and ch["drivers"] == []


# --------------------------------------------------------------------------- #
# end-to-end shape against the real calibration matrix
# --------------------------------------------------------------------------- #
def test_sector_channels_shape_and_bilingual():
    res = sri.sector_channels(_synthetic_frame())
    if not res:
        return  # no calibration matrix in this environment — math is covered above
    assert set(res) == set(sri.SECTOR_TICKERS)
    for tkr, r in res.items():
        assert r["ticker"] == tkr
        assert isinstance(r["covered"], bool)
        for chan in ("rate", "inflation"):
            ch = r[chan]
            assert ch["verdict"] in {"headwind", "tailwind", "neutral"}
            assert ch["strength"] in {"strong", "moderate", "weak"}
            assert np.isfinite(ch["net"])
            assert ch["chip"]["en"] and ch["chip"]["zh"]
            assert ch["tip"]["en"] and ch["tip"]["zh"]
            assert ch["tone"] in {"pos", "neg", "muted"}
            assert ch["arrow"] in {"▲", "▼", "·"}
            # a shown chip is always a measured one
            assert ch["show"] == ch["measured"]
            # only READ_DRIVERS may ever contribute
            for p in ch["drivers"]:
                assert p["driver"] in rit.READ_DRIVERS
                assert p["label"]["en"] and p["label"]["zh"]
        assert r["summary"]["en"] and r["summary"]["zh"]


def test_uncovered_sectors_degrade_to_not_measured():
    res = sri.sector_channels(_synthetic_frame())
    if not res:
        return
    # XLC / XLI / XLY are not in the calibrated matrix → honestly "not measured"
    for tkr in ("XLC", "XLI", "XLY"):
        r = res[tkr]
        assert r["covered"] is False
        assert r["rate"]["measured"] is False and r["inflation"]["measured"] is False
        assert r["any_shown"] is False
        assert "not measured" in r["rate"]["chip"]["en"]


# --------------------------------------------------------------------------- #
# graceful degradation
# --------------------------------------------------------------------------- #
def test_empty_calibration_returns_empty():
    assert sri.sector_channels(_synthetic_frame(), cal={}) == {}
    assert sri.sector_channels(_synthetic_frame(), cal={"meta": {}}) == {}


def test_disabled_returns_empty():
    assert sri.sector_channels(_synthetic_frame(), cfg={"enabled": False}) == {}


def test_missing_drivers_never_raises():
    # almost-empty frame: build_drivers yields mostly-NaN columns → no activations,
    # so every channel reads not-measured but the call must not raise
    idx = pd.bdate_range("2022-01-01", periods=120)
    f = pd.DataFrame(index=idx)
    f["us10y"] = 4.0
    f["us10y_real"] = 2.0
    f["breakeven_10y"] = 2.0
    res = sri.sector_channels(f)
    if res:
        assert all(not r["any_shown"] for r in res.values())


# --------------------------------------------------------------------------- #
# THE display-only invariant — the heat score never sees the overlay
# --------------------------------------------------------------------------- #
def test_heat_score_path_never_references_the_overlay():
    from engine import playbook, technicals
    pb_src = inspect.getsource(playbook.build_playbook)
    # the overlay IS attached to each sector record …
    assert '"rate_inflation": ri_map.get(t)' in pb_src
    # … but it is never fed into the heat-score call (_score_components)
    for line in pb_src.splitlines():
        if "_score_components" in line:
            assert "rate_inflation" not in line
    # and the heat-score function itself knows nothing about the overlay
    assert "rate_inflation" not in inspect.getsource(technicals._score_components)
    # the scoring leaves (heat = technicals; macro-beta dampener = conditions) must
    # not import the display-only overlay at all
    from engine import conditions
    for mod in (technicals, conditions):
        assert "sector_rate_inflation" not in inspect.getsource(mod)
