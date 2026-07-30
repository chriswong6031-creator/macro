"""Tests for the systemic-stress block (OFR FSI decomposition + commercial-paper
spreads) in engine/conditions.py. Engineered frames + graceful degradation.
See research/DATA_SIGNAL_EXPANSION_2026.md."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.conditions import conditions_snapshot  # noqa: E402


def _frame(n: int = 1400, fsi_recent: float = 2.0, **overrides) -> pd.DataFrame:
    """A feature frame carrying the OFR FSI + CP-spread inputs. Long calm history
    then a recent move so percentile/state/trend are exercised. FUNDING is the
    largest functional leg, so it should be named the leading driver when stressed."""
    idx = pd.bdate_range("2019-01-02", periods=n)
    rng = np.arange(n, dtype=float)
    base = -1.0 + 0.2 * np.sin(rng / 30)            # calm baseline (FSI < 0)
    fsi = pd.Series(base, index=idx)
    fsi.iloc[-30:] = fsi_recent                       # recent regime
    f = pd.DataFrame(index=idx)
    f["ofr_fsi"] = fsi
    for col, mult in (("ofr_fsi_credit", 0.5), ("ofr_fsi_equity", 0.3),
                      ("ofr_fsi_safe", 0.1), ("ofr_fsi_funding", 0.8),
                      ("ofr_fsi_vol", 0.2), ("ofr_fsi_us", 0.6),
                      ("ofr_fsi_oae", 0.2), ("ofr_fsi_em", 0.4)):
        f[col] = fsi * mult
    f["aa_cp_90d"] = 5.00                              # 90d AA CP
    f["a2p2_cp_90d"] = 5.30                            # A2/P2 spread = 30bp
    # bill leg = us3m_bill (DTB3, discount basis) — basis-matched to the CP legs.
    # NOT us3m (DGS3MO, bond-equivalent): the two were one alias until 2026-07-30.
    f["us3m_bill"] = 4.80                              # CP-bill spread = 20bp
    for k, v in overrides.items():
        f[k] = v
    return f


def test_block_populates_with_decomposition() -> None:
    ss = conditions_snapshot(_frame())["systemic_stress"]
    assert ss["ofr_fsi"] is not None
    assert ss["state"] in ("calm", "normal", "elevated", "acute")
    assert ss["trend"] in ("rising", "easing")
    assert set(ss["functional"]) >= {"credit", "equity_valuation", "safe_assets",
                                     "funding", "volatility"}
    assert set(ss["regional"]) == {"united_states", "other_advanced", "emerging_markets"}
    # CP spreads computed in basis points
    assert abs(ss["a2p2_spread_bps"] - 30.0) < 1.0
    assert abs(ss["cp_bill_spread_bps"] - 20.0) < 1.0


def test_names_leading_channel_when_stressed() -> None:
    ss = conditions_snapshot(_frame(fsi_recent=3.0))["systemic_stress"]
    assert ss["state"] in ("elevated", "acute")
    # funding is the largest leg -> it is named the driver
    assert ss["leading_driver_key"] == "funding"
    assert "Funding" in ss["leading_driver"]


def test_no_driver_named_when_calm() -> None:
    # FSI below its long-run average -> nothing is "driving" calm (honest gating)
    ss = conditions_snapshot(_frame(fsi_recent=-1.5))["systemic_stress"]
    assert ss["state"] == "calm"
    assert ss["leading_driver"] is None


def test_degrades_without_ofr_or_cp() -> None:
    # a bare frame with no OFR / CP columns: block present, all-None, never crashes
    idx = pd.bdate_range("2023-01-02", periods=100)
    f = pd.DataFrame({"nfci": np.full(100, -0.3)}, index=idx)
    ss = conditions_snapshot(f)["systemic_stress"]
    assert ss["ofr_fsi"] is None
    assert ss["functional"] == {} and ss["regional"] == {}
    assert ss["leading_driver"] is None
    assert ss["a2p2_spread_bps"] is None and ss["cp_bill_spread_bps"] is None
