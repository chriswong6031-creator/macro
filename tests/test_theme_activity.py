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


def _qevent(tickers, recent_amt, prior_amt, txn="Purchase"):
    """A synthetic Quiver EVENT table: per ticker, one row in the recent 60d window and one
    in the prior window. Columns mirror main's collectors/quiver.py output."""
    base = pd.Timestamp("2026-06-19")
    rows = []
    for tk in tickers:
        rows.append({"Ticker": tk, "Date": (base - pd.Timedelta(days=20)).strftime("%Y-%m-%d"),
                     "Amount": recent_amt, "Range": f"${recent_amt:,.0f}", "Transaction": txn})
        rows.append({"Ticker": tk, "Date": (base - pd.Timedelta(days=90)).strftime("%Y-%m-%d"),
                     "Amount": prior_amt, "Range": f"${prior_amt:,.0f}", "Transaction": txn})
    return pd.DataFrame(rows)


def test_two_sources_fuse_and_missing_source_downweights():
    gc = _qevent(["LMT", "NOC"], 12 * M, 2 * M)   # Quiver gov-contracts event table covers defense only
    out = ta.compute_real_activity(PAYLOAD, sources_data={"usaspending": US, "govcontracts": gc},
                                   news=False, today="2026-06-19")
    assert out["defense"]["n_sources"] == 2
    assert {s["name"] for s in out["defense"]["sources"]} == {"usaspending", "quiver_govcontract"}
    assert out["nuclear_power"]["n_sources"] == 1               # gc covers defense only → down-weighted away


def test_signed_congress_has_no_ratio_accel():
    cong = _qevent(["LMT", "NOC"], 50_000, 10_000, txn="Purchase")   # net-buy, signed
    out = ta.compute_real_activity(PAYLOAD, sources_data={"usaspending": US, "congress": cong},
                                   news=False, today="2026-06-19")
    legs = {s["name"]: s for s in out["defense"]["sources"]}
    assert "congress_netbuy" in legs and legs["congress_netbuy"]["accel"] is None  # signed → no ratio


def test_quiver_metric_recent_vs_prior():
    src = next(s for s in ta.SOURCES if s["name"] == "quiver_govcontract")
    ev = _qevent(["LMT", "NOC"], 5 * M, 1 * M)                  # 5x recent vs prior
    m = ta._quiver_basket_metric(src, ["LMT", "NOC"], today="2026-06-19", event_df=ev)
    assert m is not None and abs(m["accel"] - 5.0) < 1e-6 and m["n_covered"] == 2
    # below the prior floor -> None
    thin = _qevent(["LMT", "NOC"], 1000, 1000)
    assert ta._quiver_basket_metric(src, ["LMT", "NOC"], today="2026-06-19", event_df=thin) is None
    # congress net-buy: a sale flips the sign negative
    csrc = next(s for s in ta.SOURCES if s["name"] == "congress_netbuy")
    sale = _qevent(["LMT", "NOC"], 50_000, 0, txn="Sale")
    cm = ta._quiver_basket_metric(csrc, ["LMT", "NOC"], today="2026-06-19", event_df=sale)
    assert cm is not None and cm["accel"] is None and cm["metric"] < 0    # net selling → negative


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
