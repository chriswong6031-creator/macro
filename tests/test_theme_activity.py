"""Multi-source theme real-activity fuser tests (hermetic — injected frames, news off)."""
from __future__ import annotations

import pandas as pd

from engine import theme_activity as ta


def _wide(spec, n_complete=15):
    """spec: {ticker: (baseline, recent)} -> wide month x ticker frame (+LAG trailing months)."""
    cols = {tk: [b] * (n_complete - 3) + [r] * 3 + [b] * ta.LAG_MONTHS for tk, (b, r) in spec.items()}
    idx = pd.date_range(end="2026-05-01", periods=n_complete + ta.LAG_MONTHS, freq="MS")
    return pd.DataFrame(cols, index=idx)


def _payload(baskets):
    return {"as_of": "2026-06-19",
            "baskets": [{"id": bid, "name": bid, "members": [{"symbol": s} for s in mem]}
                        for bid, mem in baskets]}


M = 1e6
US = _wide({"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M),     # defense accelerating
            "BWXT": (25 * M, 5 * M), "OKLO": (25 * M, 5 * M)})   # nuclear cooling
PAYLOAD = _payload([("defense", ["LMT", "NOC"]), ("nuclear_power", ["BWXT", "OKLO"])])


def test_single_source_fused_equals_source_z():
    out = ta.compute_real_activity(PAYLOAD, sources_data={"usaspending": US}, news=False)
    assert set(out) == {"defense", "nuclear_power"}
    d = out["defense"]
    assert d["n_sources"] == 1
    assert d["fused_accel"] > ta.ACCEL_UP and d["obs_dir"] == 1
    assert out["nuclear_power"]["fused_accel"] < ta.ACCEL_DOWN and out["nuclear_power"]["obs_dir"] == -1
    assert abs(d["fused_obs_z"] - d["sources"][0]["z"]) < 1e-9   # one leg → fused = that leg's z
    assert d["primary"]["n_covered"] == 2


def test_two_sources_fuse_and_missing_source_downweights():
    gc = _wide({"LMT": (2 * M, 12 * M), "NOC": (2 * M, 12 * M)})   # gov-contract covers defense only
    out = ta.compute_real_activity(PAYLOAD, sources_data={"usaspending": US, "quiver_govcontract": gc}, news=False)
    assert out["defense"]["n_sources"] == 2
    assert {s["name"] for s in out["defense"]["sources"]} == {"usaspending", "quiver_govcontract"}
    assert out["nuclear_power"]["n_sources"] == 1               # gc absent → simply down-weighted away


def test_signed_source_has_no_ratio_accel():
    cong = _wide({"LMT": (-1 * M, 5 * M), "NOC": (-1 * M, 5 * M)})  # congress net-buy flips positive
    out = ta.compute_real_activity(PAYLOAD, sources_data={"usaspending": US, "congress_netbuy": cong}, news=False)
    legs = {s["name"]: s for s in out["defense"]["sources"]}
    assert "congress_netbuy" in legs and legs["congress_netbuy"]["accel"] is None  # signed → no ratio


def test_hard_source_required_news_alone_does_not_qualify():
    out = ta.compute_real_activity(_payload([("crypto", ["COIN", "MSTR"])]),
                                   sources_data={"usaspending": US}, news=False)
    assert "crypto" not in out          # no spend source + news off → excluded


def test_empty_returns_empty():
    assert ta.compute_real_activity({"baskets": []}, sources_data={"usaspending": US}, news=False) == {}
    assert ta.compute_real_activity(PAYLOAD, sources_data={"usaspending": pd.DataFrame()}, news=False) == {}


def test_robust_z_winsorised():
    z = ta.robust_z([1.0, 2.0, 3.0, 4.0, 1e6])
    assert max(z) == z[-1] and abs(z[-1]) <= ta.Z_CLAMP + 1e-9
    assert ta.robust_z([5.0]) == [0.0]
