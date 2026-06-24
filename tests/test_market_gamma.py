"""Tests for scripts.build_site.market_gamma_view — the market dealer-gamma vol-regime
note derived from the validated index GEX store. Pure/deterministic; the regime side
must match engine.gex_engine._gamma_flip (spot >= flip -> long, else short)."""
import numpy as np
import pandas as pd

from scripts.build_site import market_gamma_view


def _gex(net_gex_bn, flip, spot, spot_vs_flip_pct):
    return pd.DataFrame(
        {"net_gex_bn": [net_gex_bn], "flip_strike": [flip], "spot": [spot],
         "spot_vs_flip_pct": [spot_vs_flip_pct]},
        index=pd.to_datetime(["2026-06-13"]))


def test_short_gamma_below_flip():
    v = market_gamma_view(_gex(17.7, 8100, 7394.3, -8.71))
    assert v["regime"] == "short"                  # spot below flip -> dealers amplify
    assert v["spot_vs_flip_pct"] == -8.7
    assert v["flip"] == 8100 and v["spot"] == 7394
    assert v["net_gex_bn"] == 18                    # rounded
    assert v["asof"] == "2026-06-13"
    # contract aliases co-located with the FE key, all the same value (FE uses `flip`,
    # the contract/downstream bot reads `gamma_flip` / `flip_strike`)
    assert v["gamma_flip"] == 8100 and v["flip_strike"] == 8100


def test_long_gamma_above_flip():
    v = market_gamma_view(_gex(25.0, 5000, 5150.0, 3.0))
    assert v["regime"] == "long"                    # spot above flip -> dealers dampen


def test_at_flip_is_long():
    # spot exactly at flip (0%) -> long (engine uses S >= flip)
    assert market_gamma_view(_gex(1.0, 5000, 5000.0, 0.0))["regime"] == "long"


def test_uses_flip_side_not_net_sign():
    # net_gex POSITIVE but spot BELOW flip -> regime is SHORT (flip side wins, the
    # engine's authoritative regime) — not "long" off the net-$ sign
    assert market_gamma_view(_gex(50.0, 8100, 7400.0, -8.6))["regime"] == "short"


def test_none_and_empty_and_nan_are_graceful():
    assert market_gamma_view(None) is None
    assert market_gamma_view(pd.DataFrame()) is None
    assert market_gamma_view(_gex(10.0, 5000, 5000.0, np.nan)) is None
