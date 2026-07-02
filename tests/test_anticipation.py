"""Anticipation Engine invariants + POINT-IN-TIME guarantee.

The honesty guards are load-bearing: short-horizon direction must read as a coin-flip,
the cone must widen with horizon, display-only legs must never be marked scored without
a GO gate, and the feature engine must have NO look-ahead (truncate-and-recompute ==
full at past dates). Reads the repo data store; skips cleanly if absent.

Run: python3 -m tests.test_anticipation
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import anticipation, forward_dist, velocity, vol_forecast  # noqa: E402

STOCKS = Path("data/stocks")
_NAMES = ["NVDA", "AAPL", "JPM", "XOM"]


def _load(name):
    f = STOCKS / f"{name}.parquet"
    if not f.exists():
        return None
    return pd.read_parquet(f)["close"].dropna()


def _bench():
    f = Path("data/yahoo/SPY.parquet")
    return pd.read_parquet(f)["close"] if f.exists() else None


def test_crps_basic():
    from engine import validation
    assert abs(validation.crps_ensemble([3.0], 5.0) - 2.0) < 1e-9          # point = |x-y|
    assert validation.crps_ensemble([4, 5, 6], 5) < validation.crps_ensemble([0, 5, 10], 5)
    print("ok test_crps_basic")


def test_har_vol_forecasts_forward_vol():
    """Vol IS forecastable — the cone-width anchor must beat noise (R² well > 0)."""
    c = _load("AAPL")
    if c is None:
        print("skip test_har_vol (no data)"); return
    har = vol_forecast.cone_vol_ann(c)
    fwd = vol_forecast.forward_vol_ann(c, 22)
    j = pd.concat([har.rename("h"), fwd.rename("f")], axis=1).dropna()
    r2 = float(j["h"].corr(j["f"]) ** 2)
    assert r2 > 0.1, f"HAR forward-vol R2 too low: {r2}"
    print(f"ok test_har_vol_forecasts_forward_vol (R2={r2:.3f})")


def test_cone_widens_with_horizon():
    c = _load("NVDA")
    if c is None:
        print("skip test_cone_widens (no data)"); return
    a = anticipation.anticipate(c, bench=_bench(), asset="NVDA", gate={})
    widths = []
    for k in ("short", "medium", "long"):
        rq = a["horizons"][k].get("ret_q")
        if rq:
            widths.append(rq["p95"] - rq["p5"])
    assert len(widths) >= 2 and all(np.diff(widths) >= -1e-6), f"cone not widening: {widths}"
    print(f"ok test_cone_widens_with_horizon (widths={[round(w,1) for w in widths]})")


def test_short_direction_is_coinflip():
    c = _load("NVDA")
    if c is None:
        print("skip test_short_coinflip (no data)"); return
    a = anticipation.anticipate(c, bench=_bench(), asset="NVDA", gate={})
    s = a["horizons"]["short"]
    assert s["conviction"] == "TOSS_UP", s["conviction"]
    assert 0.43 <= s["p_up"] <= 0.58, f"p_up outside reliable cap: {s['p_up']}"
    assert s["direction"] == "coin-flip"
    print("ok test_short_direction_is_coinflip")


def test_display_only_until_go():
    c = _load("AAPL")
    if c is None:
        print("skip test_display_only (no data)"); return
    a0 = anticipation.anticipate(c, bench=_bench(), asset="AAPL", gate={})
    assert all(d["display_only"] and not d["scored"] for d in a0["drivers"]), "empty gate must be all display-only"
    a1 = anticipation.anticipate(c, bench=_bench(), asset="AAPL",
                                 gate={"vol_pct": "GO", "neg_trend_vel": "GO"})
    scored = {d["axis"] for d in a1["drivers"] if d["scored"]}
    assert scored <= {"vol_pct", "neg_trend_vel"} and scored, f"gate not honored: {scored}"
    print("ok test_display_only_until_go")


def test_direction_is_display_only():
    c = _load("NVDA")
    if c is None:
        print("skip test_direction_display_only (no data)"); return
    a = anticipation.anticipate(c, bench=_bench(), asset="NVDA", gate={})
    assert a["guards"]["direction"] == "display-only"
    assert "display-only" in a["direction_trust"]
    print("ok test_direction_is_display_only")


def test_macro_overlay_scored_and_widens():
    """Validated macro legs appear as SCORED drivers + a stress/width block; high
    stress widens the cone (width_mult > 1)."""
    c = _load("AAPL")
    if c is None:
        print("skip test_macro_overlay (no data)"); return
    mf = anticipation.macro_legs_frame()
    if mf.empty:
        print("skip test_macro_overlay (no macro data)"); return
    a = anticipation.anticipate(c, bench=_bench(), asset="AAPL", macro_frame=mf,
                                gate={"m_hy_oas": "GO", "m_nfci": "GO"})
    assert "macro" in a and a["macro"]["width_mult"] >= 1.0
    scored_macro = [d for d in a["drivers"] if d["axis"].startswith("m_") and d["scored"]]
    assert scored_macro, "validated macro legs must surface as scored drivers"
    # GEX must never be a macro leg (no history to validate)
    assert not any(d["axis"] == "gex" for d in a["drivers"])
    print(f"ok test_macro_overlay_scored_and_widens (stress {a['macro']['stress_pct']}%, x{a['macro']['width_mult']})")


def test_builder_returns_empty_on_short_series():
    c = pd.Series(np.linspace(100, 110, 50),
                  index=pd.date_range("2024-01-01", periods=50, freq="B"))
    assert anticipation.anticipate(c) == {}
    print("ok test_builder_returns_empty_on_short_series")


def test_point_in_time_no_lookahead():
    """The feature/state engine must use only trailing data: features computed on the
    FULL series, truncated at T, must equal features computed on close[:T] — at dates
    well clear of the truncation edge. A forward window / full-sample fit fails here."""
    c = _load("AAPL")
    if c is None:
        print("skip test_pit (no data)"); return
    bench = _bench()
    T = c.index[-400]                                   # cut 400 bars before the end
    cmp_end = c.index[-520]                             # 120-bar clearance from the edge
    full_legs, full_conf = anticipation._legs(c, bench, None)
    tr_legs, tr_conf = anticipation._legs(c.loc[:T], bench, None)
    a = full_conf.loc[:cmp_end].dropna()
    b = tr_conf.loc[:cmp_end].dropna()
    idx = a.index.intersection(b.index)[-200:]
    diff = (a.loc[idx] - b.loc[idx]).abs()
    rel = diff / a.loc[idx].abs().clip(lower=1e-6)
    assert float(rel.max()) < 0.01, f"look-ahead leak in confluence state: max rel diff {float(rel.max()):.4f}"
    print(f"ok test_point_in_time_no_lookahead (max rel diff {float(rel.max()):.5f})")


def test_net_liquidity_mixed_unit_invariant():
    """Audit #28: net liquidity must be a CONSISTENT-UNITS 3-term billions series
    (WALCL/1000 - RRP - TGA/1000). Two invariants that the OLD /1e6 (trillions)
    construction VIOLATED:

      1. WALCL_bn — the Fed balance sheet, the dominant term — must be the LARGEST-
         magnitude component (>= RRP_bn and >= TGA_bn in median). The old code put
         WALCL in trillions (~6.7) making it SMALLER than a billions-scale RRP (~27),
         which is the mixed-unit tell.
      2. netliq.diff must NOT be (near-)perfectly correlated with -RRP.diff. Under the
         old bug WALCL's daily change was ~1000x too small, so netliq velocity was a
         pure -RRP proxy (corr ~1.0). Fixed, WALCL's balance-sheet trend contributes.
    """
    idx = pd.bdate_range("2000-01-01", "2027-01-01")
    comps = anticipation._net_liquidity_bn(idx)
    win = idx[idx >= idx[-1] - pd.Timedelta(days=365)]
    mw = float(comps["walcl_bn"].reindex(win).median())
    mr = float(comps["rrp_bn"].reindex(win).median())
    mt = float(comps["tga_bn"].reindex(win).median())
    if not (mw > 0):
        print("skip test_net_liquidity_mixed_unit_invariant (no WALCL data)")
        return

    # Invariant 1: WALCL is the dominant (largest) component in correct units.
    assert mw >= mr, f"WALCL_bn ({mw:.0f}) < RRP_bn ({mr:.0f}) — mixed-unit scaling!"
    assert mw >= mt, f"WALCL_bn ({mw:.0f}) < TGA_bn ({mt:.0f}) — mixed-unit scaling!"

    # Invariant 2: netliq velocity is not a pure -RRP proxy.
    d_net = comps["netliq_bn"].reindex(win).diff()
    d_negrrp = (-comps["rrp_bn"].reindex(win).diff())
    corr = float(d_net.corr(d_negrrp))
    assert corr < 0.99, f"netliq.diff is a pure -RRP proxy (corr {corr:.3f}) — WALCL annihilated!"

    # Guard-the-guard: the OLD construction (WALCL /1e6, TGA dropped) MUST fail both.
    old_walcl_tn = comps["walcl_bn"] / 1000.0                 # bn/1000 == the old /1e6 trillions
    old_netliq = old_walcl_tn - comps["rrp_bn"]               # TGA dropped, as before
    assert float(old_walcl_tn.reindex(win).median()) < mr, "old WALCL(trillions) should be < RRP(bn)"
    old_corr = float(old_netliq.reindex(win).diff().corr(d_negrrp))
    assert old_corr > 0.99, f"old netliq should be a pure -RRP proxy (got corr {old_corr:.3f})"
    print(f"ok test_net_liquidity_mixed_unit_invariant "
          f"(WALCL={mw:.0f} RRP={mr:.0f} TGA={mt:.0f} bn; corr new {corr:.2f} vs old {old_corr:.2f})")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"\n{len(fns)} anticipation tests passed.")
