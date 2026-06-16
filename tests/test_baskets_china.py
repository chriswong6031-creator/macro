"""China thematic-baskets engine (engine.baskets_china.compute_china_baskets).

The A-share analogue of test_baskets — equal-weight, point-in-time dated membership over
the china_search cache, benchmarked to the CSI 300 (沪深300) read from the china store
group. Reuses the shared level/return/perf math from engine.baskets, so the same
invariants must hold: thin baskets skipped, members outside the cache surfaced in
`missing`, removed members drop from the latest roster, rel == ret − benchmark at a
horizon, the CHART matrix is well-formed, late-listing members are flagged `partial`,
and the bilingual fields (name_zh / category_zh / thesis_zh / benchmark label) are carried.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import baskets_china as bkc

BENCH_SYM = "510300.SS"


def _mem(baskets):
    return {"baskets": baskets, "benchmark": BENCH_SYM,
            "benchmark_label": "CSI 300", "benchmark_label_zh": "沪深300"}


def _setup(monkeypatch, members):
    idx = pd.date_range("2025-01-02", periods=180, freq="B")
    closes = pd.DataFrame({
        "600000.SS": 100 * (1.001 ** np.arange(180)),
        "000001.SZ": 100 * (1.002 ** np.arange(180)),
        "600519.SS": 100 * (0.999 ** np.arange(180)),
        "300750.SZ": 100 * (1.0005 ** np.arange(180)),
    }, index=idx)
    bench = pd.DataFrame({"close": 4000 * (1.0008 ** np.arange(180)),
                          "volume": np.ones(180)}, index=idx)
    monkeypatch.setattr(bkc, "_closes", lambda: closes)
    monkeypatch.setattr(bkc.store, "read",
                        lambda g, n: bench if (g, n) == ("china", BENCH_SYM) else None)
    monkeypatch.setattr(bkc, "_membership", lambda: _mem(members))
    return closes, bench, idx


def test_pit_membership_missing_chart_and_rel(monkeypatch):
    members = {
        "t1": {"name": "Theme One", "name_zh": "主题一", "category": "Tech", "category_zh": "科技",
               "etf_proxy": None, "created": "2025-01-02", "thesis": "x", "thesis_zh": "甲", "members": [
                   {"ticker": "600000.SS", "added": "2025-01-02", "removed": None, "name_zh": "甲", "rationale": "ra"},
                   {"ticker": "000001.SZ", "added": "2025-01-02", "removed": None, "name_zh": "乙", "rationale": "rb"},
                   {"ticker": "600519.SS", "added": "2025-01-02", "removed": None, "name_zh": "丙", "rationale": "rc"},
                   {"ticker": "999999.SS", "added": "2025-01-02", "removed": None, "rationale": "rx"}]},  # not in cache
        "thin": {"name": "Too Thin", "category": "Tech", "created": "2025-01-02", "members": [
            {"ticker": "600000.SS", "added": "2025-01-02"}, {"ticker": "000001.SZ", "added": "2025-01-02"}]},
    }
    _, bench, idx = _setup(monkeypatch, members)
    out = bkc.compute_china_baskets()
    assert out is not None
    assert [b["id"] for b in out["baskets"]] == ["t1"]                  # thin (<3 present) skipped
    b = out["baskets"][0]
    assert b["n_members"] == 3 and b["missing"] == ["999999.SS"]        # off-cache member surfaced
    assert {m["symbol"] for m in b["members"]} == {"600000.SS", "000001.SZ", "600519.SS"}
    assert {m["name"] for m in b["members"]} == {"甲", "乙", "丙"}        # member display name = name_zh
    assert all(m.get("last") is not None for m in b["members"])         # enriched with last price
    # rel == ret − benchmark over the same (level-based) 20d window
    br = bench["close"].iloc[-1] / bench["close"].iloc[-21] - 1
    assert abs(b["perf"]["20d"]["rel"] - (b["perf"]["20d"]["ret"] - br)) < 1e-6
    # CHART matrix well-formed
    c = out["chart"]
    assert len(c["dates"]) == 180 and len(c["bench"]) == 180
    assert "t1" in c["baskets"] and len(c["baskets"]["t1"]) == 180
    assert c["baskets"]["t1"][-1] is not None


def test_bilingual_and_benchmark_fields(monkeypatch):
    members = {"t1": {"name": "Banks", "name_zh": "银行", "category": "Financials", "category_zh": "金融",
                      "thesis": "en", "thesis_zh": "中", "created": "2025-01-02", "members": [
                          {"ticker": "600000.SS", "added": "2025-01-02"},
                          {"ticker": "000001.SZ", "added": "2025-01-02"},
                          {"ticker": "600519.SS", "added": "2025-01-02"}]}}
    _setup(monkeypatch, members)
    out = bkc.compute_china_baskets()
    assert out["benchmark_label"] == "CSI 300" and out["benchmark_label_zh"] == "沪深300"
    assert out["categories"] == ["Financials"] and out["categories_zh"] == ["金融"]
    b = out["baskets"][0]
    assert b["name_zh"] == "银行" and b["category_zh"] == "金融" and b["thesis_zh"] == "中"
    assert out["story"]["leader_zh"] == "银行"                           # story carries the zh name


def test_removed_member_drops_from_latest(monkeypatch):
    members = {"t1": {"name": "Theme", "category": "Tech", "created": "2025-01-02", "members": [
        {"ticker": "600000.SS", "added": "2025-01-02"}, {"ticker": "000001.SZ", "added": "2025-01-02"},
        {"ticker": "600519.SS", "added": "2025-01-02"},
        {"ticker": "300750.SZ", "added": "2025-01-02", "removed": "2025-03-01"}]}}
    _setup(monkeypatch, members)
    b = bkc.compute_china_baskets()["baskets"][0]
    assert {m["symbol"] for m in b["members"]} == {"600000.SS", "000001.SZ", "600519.SS"} and b["n_members"] == 3


def test_reference_market_adjusted(monkeypatch):
    members = {"t1": {"name": "T", "category": "Tech", "created": "2025-01-02", "etf_proxy": "512760.SS",
                      "etf_proxy_note": "半导体ETF", "members": [
                          {"ticker": "600000.SS", "added": "2025-01-02"}, {"ticker": "000001.SZ", "added": "2025-01-02"},
                          {"ticker": "600519.SS", "added": "2025-01-02"}]}}
    _, bench, idx = _setup(monkeypatch, members)
    rng = np.random.default_rng(0)
    etf = pd.DataFrame({"close": 50 * np.cumprod(1 + rng.normal(0, 0.01, 180))}, index=idx)
    monkeypatch.setattr(bkc.store, "read", lambda g, n: bench if n == BENCH_SYM else (etf if n == "512760.SS" else None))
    b = bkc.compute_china_baskets()["baskets"][0]
    assert b["reference"] is not None
    assert b["reference"]["label"] == "512760.SS"                       # china-group sector ETF proxy
    assert "corr" in b["reference"] and "rel_corr" in b["reference"]    # absolute + market-adjusted


def test_late_listing_flagged_partial(monkeypatch):
    """A member whose tape starts well after the series start (a recent A-share IPO / STAR-board
    listing) is flagged short-history `partial` from its first tape, not silently treated as full."""
    idx = pd.date_range("2024-01-01", periods=400, freq="B")
    closes = pd.DataFrame({
        "600000.SS": 100 * (1.0010 ** np.arange(400)),
        "000001.SZ": 100 * (1.0005 ** np.arange(400)),
        "600519.SS": 100 * (1.0008 ** np.arange(400)),
        "688981.SS": np.r_[[np.nan] * 300, 50 * (1.002 ** np.arange(100))],  # IPO — only the last 100 days have tape
    }, index=idx)
    bench = pd.DataFrame({"close": 4000 * (1.0006 ** np.arange(400)), "volume": np.ones(400)}, index=idx)
    monkeypatch.setattr(bkc, "_closes", lambda: closes)
    monkeypatch.setattr(bkc.store, "read", lambda g, n: bench if (g, n) == ("china", BENCH_SYM) else None)
    members = {"t": {"name": "T", "category": "X", "created": "2024-01-01", "members": [
        {"ticker": "600000.SS", "added": "2024-01-01"}, {"ticker": "000001.SZ", "added": "2024-01-01"},
        {"ticker": "600519.SS", "added": "2024-01-01"}, {"ticker": "688981.SS", "added": "2024-01-01"}]}}
    monkeypatch.setattr(bkc, "_membership", lambda: _mem(members))
    b = bkc.compute_china_baskets()["baskets"][0]
    partial = {p["symbol"] for p in b["partial"]}
    assert "688981.SS" in partial                                       # late-listing IPO flagged
    assert "600000.SS" not in partial and "600519.SS" not in partial    # full-history names are not


def test_degrades_without_membership(monkeypatch):
    monkeypatch.setattr(bkc, "_membership", lambda: None)
    assert bkc.compute_china_baskets() is None
