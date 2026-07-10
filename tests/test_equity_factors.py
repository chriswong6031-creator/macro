"""Cross-sectional equity factor engine tests (engine/equity_factors.py).
Pure-function checks on the winsorized z-score so they run without the EDGAR
cache; one integration check that runs only if a real cache exists.
See research/QUANT_FACTOR_EXPANSION.md."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.equity_factors import _rank_leg_weights, _winsor_z, compute_factors  # noqa: E402
from lib import config  # noqa: E402


# --------------------------------------------------------------------------- #
# Audit #25 firewall — the board RANK key may only consume scorecard-passing legs.
# --------------------------------------------------------------------------- #
def _scorecard(**legs):
    return {"factors": {k: dict(zip(("mean_ic", "ic_ir", "survives_fdr"), v))
                        for k, v in legs.items()}}


def test_rank_leg_weights_excludes_negative_ic_legs():
    # investment (-0.003) and low_vol (-0.021) are anti-predictive FDR-failers — they must NOT
    # appear in the rank key; positive-IC legs survive, IC-weighted; the FDR survivor leads.
    sc = _scorecard(value=(0.0184, 0.223, False), quality=(0.0042, 0.073, False),
                    profitability=(0.0141, 0.12, False), investment=(-0.0029, -0.036, False),
                    payout=(0.0247, 0.298, True), low_vol=(-0.0209, -0.093, False))
    legs = ["value", "quality", "profitability", "investment", "payout", "low_vol"]
    w = _rank_leg_weights(legs, sc)
    assert "investment" not in w and "low_vol" not in w      # negative-IC excluded
    assert set(w) == {"value", "quality", "profitability", "payout"}
    assert all(v > 0 for v in w.values())                    # sign constraint: strictly positive
    assert w["payout"] > w["value"]                          # FDR survivor gets the bonus


def test_rank_key_never_contains_a_negative_ic_leg_property():
    # Property guard: for ANY scorecard, no leg with mean_ic <= 0 can enter the rank key.
    import random
    rng = random.Random(0)
    legs = [f"f{i}" for i in range(8)]
    for _ in range(200):
        sc = _scorecard(**{l: (rng.uniform(-0.05, 0.05), rng.uniform(-0.3, 0.3),
                              rng.random() < 0.2) for l in legs})
        w = _rank_leg_weights(legs, sc)
        for leg in w:
            assert sc["factors"][leg]["mean_ic"] > 0         # invariant: no anti-predictive leg


def test_rank_leg_weights_empty_when_no_scorecard():
    # No scorecard -> no leg qualifies -> caller falls back to the display composite out of rank.
    assert _rank_leg_weights(["value", "low_vol"], {}) == {}
    assert _rank_leg_weights(["value"], {"factors": {"value": {"mean_ic": None}}}) == {}


def test_winsor_z_centers_and_clips() -> None:
    # a tight cluster + one far outlier: the outlier's raw z exceeds the cap
    s = pd.Series([float(x) for x in range(50)] + [10000.0])
    z = _winsor_z(s, 3.0)
    assert abs(z.iloc[:50].mean()) < 1.0              # bulk roughly centered
    assert z.max() <= 3.0 and z.min() >= -3.0         # clipped to the cap
    assert z.iloc[-1] == 3.0                           # far outlier pinned at the cap


def test_winsor_z_handles_degenerate() -> None:
    z = _winsor_z(pd.Series([5.0, 5.0, 5.0]), 3.0)     # zero variance
    assert z.isna().all()
    z2 = _winsor_z(pd.Series([np.inf, 1.0, 2.0, 3.0]), 3.0)  # inf scrubbed
    assert np.isfinite(z2.dropna()).all()


# --------------------------------------------------------------------------- #
# Split-staleness guard — EDGAR cover-page shares vs the Polygon reference.
# A post-split price times pre-split filing shares understated mktcap by the
# split ratio (BKNG 25:1 2026-04-06 -> profile.mktcap_bn ~25x low).
# --------------------------------------------------------------------------- #
def _ref_parquet(tmp_path, monkeypatch, shares: dict) -> None:
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    p = tmp_path / "sp500_heatmap"
    p.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"shares": pd.Series(shares, dtype=float)})
    df.index.name = "ticker"
    df["asof"] = "2026-07-10"
    df.to_parquet(p / "reference.parquet")


def test_reconcile_shares_overrides_stale_split_counts(tmp_path, monkeypatch) -> None:
    from engine.equity_factors import _reconcile_shares
    _ref_parquet(tmp_path, monkeypatch, {
        "BKNG": 774.9e6,   # 25:1 split — filing count is 25x low
        "KLAC": 1.306e9,   # 10:1 split
        "AAPL": 14.8e9,    # within band of the filing count -> EDGAR kept
        "META": 2.52e9,    # EDGAR serves no share count -> filled
        "RSPLT": 1.0e6,    # 1:10 reverse split — filing count is 10x HIGH
    })
    edgar = pd.Series({"BKNG": 31.0e6, "KLAC": 130.6e6, "AAPL": 14.7e9,
                       "META": np.nan, "RSPLT": 1.0e7, "NOREF": 5.0e8})
    out = _reconcile_shares(edgar)
    assert out["BKNG"] == 774.9e6                     # stale split count replaced
    assert out["KLAC"] == 1.306e9
    assert out["RSPLT"] == 1.0e6                      # reverse split replaced too
    assert out["META"] == 2.52e9                      # missing filing count filled
    assert out["AAPL"] == 14.7e9                      # small drift keeps the filing
    assert out["NOREF"] == 5.0e8                      # not in reference -> untouched


def test_reconcile_shares_noop_without_reference(tmp_path, monkeypatch) -> None:
    from engine.equity_factors import _reconcile_shares
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)  # no reference.parquet
    edgar = pd.Series({"BKNG": 31.0e6, "META": np.nan})
    out = _reconcile_shares(edgar)
    assert out["BKNG"] == 31.0e6 and pd.isna(out["META"])


def test_reconcile_shares_survives_broken_reference(tmp_path, monkeypatch) -> None:
    from engine.equity_factors import _reconcile_shares
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    p = tmp_path / "sp500_heatmap"
    p.mkdir(parents=True)
    (p / "reference.parquet").write_bytes(b"not a parquet")
    edgar = pd.Series({"BKNG": 31.0e6})
    assert _reconcile_shares(edgar)["BKNG"] == 31.0e6


def test_compute_factors_shape_if_cache_present() -> None:
    cache = config.data_dir() / "edgar" / "fundamentals.parquet"
    if not cache.exists():
        return  # no live cache in this environment — pure-function tests cover the math
    r = compute_factors()
    assert r is not None
    assert r["n"] > 100
    assert "value" in r["factors"] and "low_vol" in r["factors"]
    # every leaderboard entry is well-formed
    for x in r["composite_top"][:5]:
        assert {"ticker", "name", "sector", "z"} <= set(x)
    # leadership spreads are finite numbers
    for L in r["leadership"]:
        assert isinstance(L["spread_pct"], float)
    # composite is bounded by the winsor cap on each leg (mean of clipped z's)
    cap = config.load()["edgar"]["factors"]["winsor_z"]
    for x in r["composite_top"] + r["composite_bottom"]:
        assert -cap <= x["z"] <= cap
    # audit #25: the RANK composite (composite_top/bottom) draws only from scorecard-passing
    # legs; the display composite is kept separately + badged.
    assert "rank_legs" in r and "composite_display_top" in r and "fdr_badges" in r
    from engine.equity_factors import _load_ic_scorecard
    facs = (_load_ic_scorecard().get("factors") or {})
    for leg in r["rank_legs"]:
        assert facs.get(leg, {}).get("mean_ic", 0) > 0       # no anti-predictive leg in rank key
