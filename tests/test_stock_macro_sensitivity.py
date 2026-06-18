"""Unit tests for engine/stock_macro_sensitivity.py — the display-only per-stock
rate / inflation read.

These lock the honest semantics: the rate-beta SE is the closed form reconstructed from
the exposure export; the duration bucket is ANCHORED on the sector ETF (the name's own
beta only refines/flags it); the live-regime read flips correctly with duration × rate
direction; the inflation label is the structural archetype/sector classification; and the
mandatory single-name caveat is on every payload. Nothing here is ever scored.
"""
import math

import pytest

from engine import stock_macro_sensitivity as ms


# --------------------------------------------------------------------------- #
# standard error (closed form)
# --------------------------------------------------------------------------- #
def test_beta_se_closed_form():
    # SE = idio_vol / (factor_vol_rates * sqrt(n))
    rec = {"rates": -0.3, "idio_vol": 0.16, "n": 250}
    se = ms.beta_se(rec, 0.0944)
    assert se == pytest.approx(0.16 / (0.0944 * math.sqrt(250)), rel=1e-9)


def test_beta_se_degrades_to_none():
    assert ms.beta_se({"rates": 0.1, "idio_vol": 0.1, "n": 0}, 0.09) is None   # n<=0
    assert ms.beta_se({"rates": 0.1, "idio_vol": None, "n": 250}, 0.09) is None  # no idio
    assert ms.beta_se({"rates": None, "idio_vol": 0.1, "n": 250}, 0.09) is None  # no beta
    assert ms.beta_se({"rates": 0.1, "idio_vol": 0.1, "n": 250}, None) is None   # no factor vol
    assert ms.beta_se({}, 0.09) is None


# --------------------------------------------------------------------------- #
# per-name precision tier
# --------------------------------------------------------------------------- #
def test_rate_beta_tier_thresholds():
    assert ms.rate_beta_tier(3.0) == "high"        # t >= 2.5
    assert ms.rate_beta_tier(2.5) == "high"
    assert ms.rate_beta_tier(2.0) == "medium"      # 1.5 <= t < 2.5
    assert ms.rate_beta_tier(1.5) == "medium"
    assert ms.rate_beta_tier(1.0) == "low"         # t < 1.5
    assert ms.rate_beta_tier(None) == "low"        # no SE => can't assess precision


# --------------------------------------------------------------------------- #
# bucket from a single signed beta (dead-band + precision gate)
# --------------------------------------------------------------------------- #
def test_bucket_from_beta():
    assert ms._bucket_from_beta(0.30, 3.0) == "long"     # strong +, precise
    assert ms._bucket_from_beta(-0.30, 3.0) == "short"   # strong -, precise
    assert ms._bucket_from_beta(0.05, 3.0) == "neutral"  # inside dead-band
    assert ms._bucket_from_beta(0.30, 1.0) == "neutral"  # below precision gate
    assert ms._bucket_from_beta(None, 3.0) == "neutral"
    assert ms._bucket_from_beta(0.30, None) == "neutral"


# --------------------------------------------------------------------------- #
# duration bucket — sector anchor, name refinement, fallbacks
# --------------------------------------------------------------------------- #
def test_duration_anchors_on_sector():
    # name beta is noisy/neutral but the sector ETF reads clearly long
    d = ms.duration_bucket(name_beta=-0.05, name_t=0.5, sector_beta=0.32, sector_t=3.5)
    assert d["bucket"] == "long" and d["src"] == "sector" and d["diverges"] is False


def test_duration_flags_high_precision_divergence():
    # sector reads long, but the name's OWN beta is high-precision and points short
    d = ms.duration_bucket(name_beta=-0.4, name_t=3.0, sector_beta=0.30, sector_t=3.0)
    assert d["bucket"] == "long"        # sector still anchors the headline
    assert d["diverges"] is True        # ...but we flag the divergence


def test_duration_uses_name_when_sector_neutral_and_name_precise():
    d = ms.duration_bucket(name_beta=0.35, name_t=3.0, sector_beta=0.02, sector_t=0.3)
    assert d["bucket"] == "long" and d["src"] == "name"


def test_duration_macro_beta_fallback():
    # no sector ETF beta, name too noisy → fall back to sector_macro_beta sign
    d = ms.duration_bucket(name_beta=0.05, name_t=0.4, sector_beta=None, sector_t=None,
                           sector_macro_beta_val=0.6)
    assert d["bucket"] == "long" and d["src"] == "macro_beta"
    d2 = ms.duration_bucket(name_beta=0.05, name_t=0.4, sector_beta=None, sector_t=None,
                            sector_macro_beta_val=0.0)
    assert d2["bucket"] == "neutral" and d2["src"] == "fallback"


# --------------------------------------------------------------------------- #
# live-regime head/tailwind
# --------------------------------------------------------------------------- #
def test_regime_read_long_duration():
    rising = {"regime": "restrictive", "direction": "rising"}
    falling = {"regime": "accommodative", "direction": "falling"}
    assert ms.regime_read("long", rising, True) == "headwind"
    assert ms.regime_read("long", falling, True) == "tailwind"
    assert ms.regime_read("long", {"direction": "stable"}, True) == "neutral"


def test_regime_read_short_duration_is_mirror():
    rising = {"regime": "restrictive", "direction": "rising"}
    assert ms.regime_read("short", rising, True) == "tailwind"
    assert ms.regime_read("short", {"direction": "falling"}, True) == "headwind"


def test_regime_read_dormant_chain_is_neutral():
    # rates have a direction but the real-rate transmission chain is NOT live -> dormant
    rising = {"regime": "restrictive", "direction": "rising"}
    assert ms.regime_read("long", rising, False) == "neutral"
    assert ms.regime_read("short", rising, False) == "neutral"


def test_regime_read_none_without_state():
    assert ms.regime_read("long", None, False) is None
    assert ms.regime_read("neutral", {"direction": "rising"}, True) == "neutral"


# --------------------------------------------------------------------------- #
# inflation label (structural)
# --------------------------------------------------------------------------- #
def test_inflation_label():
    assert ms.inflation_label("quality_compounder", "Energy") == "hedge"
    assert ms.inflation_label("deep_value", "Industrials") == "hedge"          # value tilt
    assert ms.inflation_label("mixed", "Information Technology", sector_oil_beta=0.25) == "hedge"
    assert ms.inflation_label("high_beta_momentum", "Information Technology") == "negative"
    assert ms.inflation_label("dividend_defensive", "Utilities") == "neutral"
    assert ms.inflation_label(None, "Health Care") == "neutral"


# --------------------------------------------------------------------------- #
# assess() integration
# --------------------------------------------------------------------------- #
def _ctx(betas, **kw):
    base = dict(betas=betas, factor_vol_rates=0.09, rate_persist=0.36,
                rate_state={"regime": "restrictive", "direction": "rising", "real_10y": 2.1},
                infl_state={"regime": "above target", "direction": "re-accelerating"},
                real_rate_active=True, calibrated=True)
    base.update(kw)
    return ms.Context(**base)


def test_assess_long_duration_headwind():
    betas = {
        "KO": {"rates": 0.23, "idio_vol": 0.15, "n": 250},
        "XLP": {"rates": 0.20, "idio_vol": 0.10, "n": 250},   # staples sector anchor
    }
    r = ms.assess("KO", "Consumer Staples", "dividend_defensive", _ctx(betas))
    assert r is not None
    assert r["duration"] == "long"
    assert r["regime"] == "headwind"
    assert r["sector_etf"] == "XLP"
    # bilingual + mandatory caveat on every payload
    assert r["headline"]["en"] and r["headline"]["zh"]
    assert r["caveat"]["en"].startswith("Single-name secondary betas are noisy")
    assert "单一个股" in r["caveat"]["zh"]
    # SE / t-stat carried with the rate beta
    assert r["rate_beta_se"] is not None and r["t_stat"] is not None


def test_assess_short_duration_tailwind_and_hedge():
    betas = {
        "XOM": {"rates": -0.66, "idio_vol": 0.18, "n": 250, "oil": 0.29},
        "XLE": {"rates": -0.60, "idio_vol": 0.16, "n": 250, "oil": 0.25},
    }
    r = ms.assess("XOM", "Energy", "deep_value", _ctx(betas))
    assert r["duration"] == "short" and r["regime"] == "tailwind"
    assert r["inflation"] == "hedge"


def test_assess_growth_name_is_duration_neutral_negative_infl():
    # tech name: own orthogonal rate beta absorbed by the growth factor -> sector neutral
    betas = {
        "NVDA": {"rates": -0.05, "idio_vol": 0.24, "n": 250, "oil": 0.0},
        "XLK": {"rates": -0.06, "idio_vol": 0.10, "n": 250, "oil": 0.01},
    }
    r = ms.assess("NVDA", "Information Technology", "high_beta_momentum", _ctx(betas))
    assert r["duration"] == "neutral"
    assert r["inflation"] == "negative"


def test_assess_scope_gates():
    betas = {"AAPL": {"rates": -0.1, "idio_vol": 0.2, "n": 250}}
    # non-GICS sector (ETF/commodity/crypto) -> out of scope
    assert ms.assess("AAPL", "ETF / macro", "mixed", _ctx(betas)) is None
    # not in the exposure universe -> no chip
    assert ms.assess("ZZZZ", "Information Technology", "mixed", _ctx(betas)) is None
    # no sector at all
    assert ms.assess("AAPL", None, "mixed", _ctx(betas)) is None


def test_assess_regime_omitted_without_transmission():
    betas = {
        "KO": {"rates": 0.23, "idio_vol": 0.15, "n": 250},
        "XLP": {"rates": 0.20, "idio_vol": 0.10, "n": 250},
    }
    ctx = _ctx(betas, rate_state=None, real_rate_active=False, calibrated=False)
    r = ms.assess("KO", "Consumer Staples", "dividend_defensive", ctx)
    assert r is not None
    assert r["regime"] is None           # degrades gracefully
    assert r["regime_label"] is None
    assert r["duration"] == "long"       # duration + tier still present
    assert r["caveat"]["en"]             # caveat always present
