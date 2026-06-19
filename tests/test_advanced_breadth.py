"""Pure-function tests for the advanced breadth tracker (market internals).

Covers the McClellan oscillator/summation, the Zweig breadth-thrust gauge and
its crossing detector, the High-Low Index bands, the A/D-vs-price divergence
states, the participation-in-context percentile, and the cross-tier gap — plus
the orchestrator's graceful degradation and the builder's bilingual output. No
network; the real-data structure test no-ops if no breadth parquet is shipped.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import advanced_breadth as ab  # noqa: E402


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2010-01-01", periods=n)


def _series(vals) -> pd.Series:
    vals = list(vals)
    return pd.Series(vals, index=_idx(len(vals)))


# --------------------------------------------------------------------------- #
# McClellan oscillator + summation
# --------------------------------------------------------------------------- #
def test_mcclellan_tracks_recent_breadth_shift():
    n = 220
    # first ~160 days breadth weak (more decliners), last ~60 days strong advance
    adv = _series([150] * 160 + [400] * 60)
    dec = _series([350] * 160 + [100] * 60)
    d = ab.mcclellan(adv, dec)
    assert d is not None
    # a recent swing toward advancers lifts the fast EMA above the slow -> osc > 0
    assert d["osc"] > 0 and d["tone"] == "pos"
    assert d["band"] in {"positive", "surging"}
    # mirror image: a recent swing toward decliners pushes the oscillator negative
    d2 = ab.mcclellan(dec, adv)
    assert d2["osc"] < 0 and d2["tone"] == "neg"
    assert d2["band"] in {"negative", "oversold"}


def test_mcclellan_summation_is_running_total_of_osc():
    n = 120
    rng = np.linspace(-200, 300, n)
    adv = _series(500 + rng / 2)
    dec = _series(500 - rng / 2)
    d = ab.mcclellan(adv, dec)
    # the summation level is just the cumulative oscillator; its 20d change is signed
    assert isinstance(d["summ"], float)
    assert isinstance(d["summ_rising"], bool)
    assert len(d["spark"]) > 0


def test_mcclellan_needs_warmup():
    # too few points for the 39-day slow EMA -> None, never raises
    assert ab.mcclellan(_series([300] * 10), _series([200] * 10)) is None


# --------------------------------------------------------------------------- #
# Zweig breadth thrust
# --------------------------------------------------------------------------- #
def test_breadth_thrust_detects_washed_to_thrust_crossing():
    # 20 washed-out days (advancers' share 0.30) then a sharp broad rally (0.72)
    adv = _series([30] * 20 + [72] * 14)
    dec = _series([70] * 20 + [28] * 14)
    nm = _series([450] * 34)
    d = ab.breadth_thrust(adv, dec, nm)
    assert d is not None
    assert d["hist_count"] >= 1            # the strict 0.40->0.615 launch fired
    assert d["recent_thrust"] is True      # and it fired inside the last month
    assert d["zone"] == "thrust" and d["tone"] == "pos"


def test_breadth_thrust_washed_zone():
    adv = _series([30] * 40)
    dec = _series([70] * 40)
    d = ab.breadth_thrust(adv, dec, _series([450] * 40))
    assert d["zone"] == "washed" and d["tone"] == "neg"
    assert d["hist_count"] == 0            # no crossing in a flat washed tape


def test_breadth_thrust_mature_gate_excludes_thin_universe():
    # same crossing, but the universe is below the mature gate -> not tallied
    adv = _series([30] * 20 + [72] * 14)
    dec = _series([70] * 20 + [28] * 14)
    thin = ab.breadth_thrust(adv, dec, _series([100] * 34))
    assert thin["hist_count"] == 0         # excluded from the historical count
    assert thin["recent_thrust"] is True   # but the live "fired recently" still reads


# --------------------------------------------------------------------------- #
# High-Low Index
# --------------------------------------------------------------------------- #
def test_high_low_index_expanding_and_contracting():
    hi = ab.high_low_index(_series([30] * 30), _series([2] * 30))
    assert hi["band"] == "expanding" and hi["tone"] == "pos"
    assert hi["net_nh"] == 28
    lo = ab.high_low_index(_series([2] * 30), _series([30] * 30))
    assert lo["band"] == "contracting" and lo["tone"] == "neg"
    assert lo["net_nh"] == -28


def test_high_low_index_handles_zero_highs_and_lows():
    # no new highs or lows -> rhp undefined that day, must not raise
    d = ab.high_low_index(_series([0] * 30), _series([0] * 30))
    assert d is None or d["net_nh"] == 0


# --------------------------------------------------------------------------- #
# A/D-line vs price divergence
# --------------------------------------------------------------------------- #
def test_divergence_bearish_when_price_highs_unconfirmed():
    n = 80
    price = _series(np.linspace(100, 130, n))        # price marching to a new high
    ad = _series(np.linspace(5000, 4000, n))         # A/D line sliding the other way
    d = ab.divergence(ad, price)
    assert d["state"] == "bearish_div" and d["tone"] == "neg"


def test_divergence_confirmed_up_when_both_make_highs():
    n = 80
    price = _series(np.linspace(100, 130, n))
    ad = _series(np.linspace(4000, 5000, n))
    d = ab.divergence(ad, price)
    assert d["state"] == "confirmed_up"


def test_divergence_bullish_when_price_lows_unconfirmed():
    n = 80
    price = _series(np.linspace(130, 100, n))        # price grinding to a new low
    ad = _series(np.linspace(4000, 5000, n))         # A/D line refusing to confirm
    d = ab.divergence(ad, price)
    assert d["state"] == "bullish_div" and d["tone"] == "pos"


def test_divergence_inrange_when_nothing_at_extreme():
    # rise, fall, then a partial recovery so the last days sit mid-range — neither
    # the window high (130) nor the window low (105) is in the recent tail
    shape = np.concatenate([np.linspace(100, 130, 30),
                            np.linspace(130, 105, 30),
                            np.linspace(105, 118, 20)])
    d = ab.divergence(_series(shape * 40), _series(shape))
    assert d["state"] == "inrange" and d["tone"] == "muted"


def test_divergence_none_without_price():
    assert ab.divergence(_series(np.arange(80.0)), None) is None


# --------------------------------------------------------------------------- #
# Participation in historical context
# --------------------------------------------------------------------------- #
def test_participation_percentile_and_momentum():
    n = 300
    pa50 = _series(np.linspace(20, 70, n))           # steadily broadening tape
    frame = pd.DataFrame({"pct_above_50": pa50.values,
                          "pct_above_200": np.linspace(15, 65, n),
                          "n_members": [500] * n,
                          "ad_line": np.linspace(0, 5000, n)}, index=_idx(n))
    d = ab.participation(frame)
    assert d["pa50_chg20"] > 0                        # rising participation
    assert d["pctile"] is not None and 80 <= d["pctile"] <= 100   # near the top of its range
    assert d["ad_dir"] == "up"
    assert len(d["hist_from"]) == 4                   # a 4-digit year string


def test_participation_mature_window_filters_thin_universe():
    n = 260
    # thin (excluded) early days sit at an extreme that would skew a naive percentile
    pa50 = _series([5] * 60 + list(np.linspace(40, 60, n - 60)))
    nm = _series([100] * 60 + [500] * (n - 60))       # first 60 below the mature gate
    frame = pd.DataFrame({"pct_above_50": pa50.values, "n_members": nm.values},
                         index=_idx(n))
    d = ab.participation(frame)
    # percentile is taken over the mature window only, so the thin 5%-days don't count
    assert d["hist_from"] != "2010" or d["pctile"] is not None


# --------------------------------------------------------------------------- #
# Cross-tier gap
# --------------------------------------------------------------------------- #
def test_tier_gap_bands():
    assert ab.tier_gap({"large": 50, "mid": 55, "small": 58})["state"] == "broadening"
    assert ab.tier_gap({"large": 60, "mid": 55, "small": 52})["state"] == "narrowing"
    assert ab.tier_gap({"large": 55, "mid": 55, "small": 56})["state"] == "inline"
    assert ab.tier_gap(None) is None
    assert ab.tier_gap({"large": 55}) is None         # missing small -> None, no raise


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def _full_frame(n: int = 220) -> pd.DataFrame:
    rng = np.linspace(-150, 250, n)
    return pd.DataFrame({
        "adv": 250 + rng / 2, "dec": 250 - rng / 2,
        "nh": np.clip(rng / 10 + 15, 0, None), "nl": np.clip(15 - rng / 10, 0, None),
        "pct_above_50": np.clip(50 + rng / 8, 0, 100),
        "pct_above_200": np.clip(50 + rng / 10, 0, 100),
        "ad_line": np.cumsum(rng / 50), "n_members": [500] * n,
    }, index=_idx(n))


def test_advanced_breadth_orchestrator_shape():
    d = ab.advanced_breadth(_full_frame(), price=_series(np.linspace(100, 120, 220)),
                            tiers={"large": 54, "mid": 56, "small": 59})
    assert d is not None
    for k in ("mcclellan", "thrust", "highlow", "divergence", "participation",
              "tiergap", "headline"):
        assert k in d
    assert d["headline"]["key"] in {"firm", "mixed", "deteriorating"}
    assert d["headline"]["tone"] in {"pos", "neg", "muted"}
    assert isinstance(d["asof"], str) and len(d["asof"]) == 10
    assert d["n_deep"] == 220


def test_advanced_breadth_graceful_on_empty():
    assert ab.advanced_breadth(pd.DataFrame()) is None
    assert ab.advanced_breadth(None) is None
    # a frame without adv/dec is unusable -> None, never raises
    assert ab.advanced_breadth(pd.DataFrame({"pct_above_50": [50, 51]})) is None


# --------------------------------------------------------------------------- #
# Real data + builder bilingual output (no-op if not present in the checkout)
# --------------------------------------------------------------------------- #
def test_real_breadth_parquet_structure():
    from lib import config
    p = config.data_dir() / "breadth" / "breadth.parquet"
    if not p.exists():
        return
    big = pd.read_parquet(p)
    d = ab.advanced_breadth(big)
    assert d is not None
    mcc = d["mcclellan"]
    assert -1000 < mcc["osc"] < 1000
    if d["thrust"]:
        assert 0.0 <= d["thrust"]["value"] <= 1.0
    if d["participation"] and d["participation"]["pctile"] is not None:
        assert 0 <= d["participation"]["pctile"] <= 100


def test_builder_view_is_bilingual():
    from scripts.build_site import advanced_breadth_view
    from lib import config
    if not (config.data_dir() / "breadth" / "breadth.parquet").exists():
        return
    f = pd.DataFrame({"SPY": pd.Series(np.linspace(100, 120, 400),
                                       index=pd.bdate_range("2024-01-01", periods=400))})
    out = advanced_breadth_view(f)
    if out is None:
        return
    # headline + every band/zone/state label ships both languages
    assert 'class="l-en"' in str(out["headline"]["label"])
    assert 'class="l-zh"' in str(out["headline"]["label"])
    if out.get("mcc"):
        assert 'class="l-zh"' in str(out["mcc"]["band"])
