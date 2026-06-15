"""Treasury auction-absorption engine tests (DISPLAY-ONLY leaf).

Synthetic + deterministic. Locks: term->tenor reopening mapping, causal-z
no-look-ahead, stress orientation (low bid-to-cover/indirect + high dealer => high
stress = weak demand), regime band mapping, and the snapshot contract — including
context_only=True, the invariant that this read is NEVER scored or propagated. A
real-data smoke skips cleanly if the cached parquet is absent.

Run: python -m tests.test_auction_stress
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import treasury_auctions as TA  # noqa: E402
from engine import auction_stress as A  # noqa: E402
from lib import config  # noqa: E402

CFG = config.load()["auction_stress"]


def _synth(n_per_tenor=40, tenors=(2, 5, 10, 30), seed=0, soft_tail=False) -> pd.DataFrame:
    """Calm baseline auctions; soft_tail makes the LAST 10y auction weak."""
    rng = np.random.default_rng(seed)
    d0 = pd.Timestamp("2014-01-01")
    rows = []
    for ti, t in enumerate(tenors):
        for k in range(n_per_tenor):
            ind = 0.65 + rng.normal(0, 0.03)
            dlr = 0.12 + rng.normal(0, 0.02)
            rows.append({
                "cusip": f"{t}-{k}", "type": "Note", "term": f"{t}-Year",
                "auction_date": d0 + pd.Timedelta(days=28 * k + ti), "tenor": t,
                "btc": 2.5 + rng.normal(0, 0.1), "accepted": 1.0, "offering": 4e10,
                "high_yield": 4.0, "indirect_share": ind, "dealer_share": dlr,
                "direct_share": 1 - ind - dlr,
            })
    df = pd.DataFrame(rows)
    if soft_tail:
        idx = df[df["tenor"] == 10].sort_values("auction_date").index[-1]
        df.loc[idx, ["btc", "indirect_share", "dealer_share"]] = [1.8, 0.42, 0.32]
    return df


# --- term -> tenor -----------------------------------------------------------
def test_term_to_tenor_reopenings():
    tn = CFG["tenors"]
    assert TA._term_to_tenor("9-Year 11-Month", tn) == 10
    assert TA._term_to_tenor("29-Year 10-Month", tn) == 30
    assert TA._term_to_tenor("19-Year 10-Month", tn) == 20
    assert TA._term_to_tenor("7-Year", tn) == 7
    assert TA._term_to_tenor("2-Year", tn) == 2
    assert TA._term_to_tenor("4-Week", tn) is None       # a bill: nearest tenor too far
    assert TA._term_to_tenor("", tn) is None


# --- stress orientation ------------------------------------------------------
def test_stress_orientation():
    """A weak auction (low bid-to-cover/indirect, high dealer) => high positive stress;
    the baseline calm auctions sit near zero."""
    fr = A.auction_frame(_synth(soft_tail=True))
    last10 = fr[fr["tenor"] == 10].sort_values("auction_date").iloc[-1]
    assert last10["stress"] > 0.7, last10["stress"]        # clearly weak demand
    # demand_z in the snapshot is the negation -> clearly negative for that tenor
    snap = A.auction_snapshot(fr)
    tile10 = next(t for t in snap["tenors"] if t["tenor"] == 10)
    assert tile10["soft"] is True and tile10["demand_z"] < -0.5


# --- causal: truncation must not change earlier rows -------------------------
def test_causal_no_lookahead():
    df = _synth(seed=3)
    full = A.auction_frame(df).set_index("cusip")["stress"]
    cut = A.auction_frame(df.sort_values("auction_date").iloc[:100]).set_index("cusip")["stress"]
    common = full.index.intersection(cut.index)
    a = full.loc[common].dropna()
    b = cut.loc[common].reindex(a.index)
    assert len(a) > 20
    assert np.allclose(a.to_numpy(), b.to_numpy(), rtol=1e-9, atol=1e-9, equal_nan=True)


# --- regime bands ------------------------------------------------------------
def test_regime_bands():
    assert A._regime(-1.0, CFG) == "firm"
    assert A._regime(0.0, CFG) == "smooth"
    assert A._regime(0.7, CFG) == "watch"
    assert A._regime(1.5, CFG) == "stressed"
    assert A._regime(None, CFG) is None
    assert A._regime(float("nan"), CFG) is None


# --- snapshot contract + the never-scored invariant --------------------------
def test_snapshot_contract():
    snap = A.auction_snapshot(_synth(soft_tail=True))
    for k in ["as_of", "context_only", "composite_z", "regime", "tenors", "supply",
              "recent", "verdict_en", "verdict_zh", "span", "n_auctions"]:
        assert k in snap, k
    assert snap["context_only"] is True               # invariant: display-only, never scored
    assert snap["regime"] in {"firm", "smooth", "watch", "stressed", None}
    assert snap["tenors"] and all("btc" in t for t in snap["tenors"])
    assert snap["supply"]["coupon_gross_bn"] is not None
    assert snap["verdict_zh"] and snap["verdict_zh"] != snap["verdict_en"]
    # the leaf must NOT expose any scoring/axes contract
    assert not any(k in snap for k in ("axes", "score", "drivers_for", "health_score"))


def test_empty_is_graceful():
    assert A.auction_frame(pd.DataFrame()).empty
    assert A.auction_snapshot(pd.DataFrame()) is None


# --- real-data smoke ---------------------------------------------------------
def test_real_data_smoke():
    df = TA.load_results()
    if df is None or df.empty:
        print("  (skip auction-stress real-data smoke: no cached parquet)")
        return
    snap = A.auction_snapshot()
    assert snap and snap["as_of"]
    assert snap["regime"] in {"firm", "smooth", "watch", "stressed", None}
    assert snap["context_only"] is True
    print(f"  real data: {snap['n_auctions']} auctions, regime={snap['regime']} "
          f"z={snap['composite_z']} as_of={snap['as_of']}")


if __name__ == "__main__":
    for fn in [test_term_to_tenor_reopenings, test_stress_orientation, test_causal_no_lookahead,
               test_regime_bands, test_snapshot_contract, test_empty_is_graceful,
               test_real_data_smoke]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all auction-stress tests passed")
