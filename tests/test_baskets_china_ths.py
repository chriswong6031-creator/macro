"""同花顺 (THS) thematic-baskets pipeline.

Covers the three new pieces of the THS-mirrored China baskets:
  • engine.baskets_china.compute_china_ths_baskets — same compute as the curated path but over the
    THS membership file (so the shared invariants hold: thin baskets skipped, off-cache members in
    `missing`, name_zh display, rel == ret − bench);
  • collectors.china_ths_concepts.to_suffixed — bare A-share code → exchange-suffixed store ticker;
  • scripts.seed_china_ths_baskets._pit_members — snapshot diff → point-in-time added/removed +
    universe filter (first run seeds at SEED; later snapshots date entries/exits genuinely).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from collectors.china_ths_concepts import to_suffixed
from engine import baskets_china as bkc
from scripts import seed_china_ths_baskets as seed

BENCH_SYM = "510300.SS"


# ── collector: exchange-suffix mapping ────────────────────────────────────────
def test_to_suffixed_exchange_mapping():
    assert to_suffixed("600519") == "600519.SS"   # Shanghai main board
    assert to_suffixed("000001") == "000001.SZ"   # Shenzhen main board
    assert to_suffixed("300750") == "300750.SZ"   # ChiNext (Shenzhen)
    assert to_suffixed("688981") == "688981.SS"   # STAR board (Shanghai)
    assert to_suffixed("900957") == "900957.SS"   # Shanghai B-share
    assert to_suffixed("830799") == "830799.BJ"   # Beijing Stock Exchange (8xx)
    assert to_suffixed("920225") == "920225.BJ"   # Beijing Stock Exchange (920xxx, e.g. 利通科技)
    assert to_suffixed(860) == "000860.SZ"        # int input, zero-padded → Shenzhen


# ── engine wrapper: reuses the shared compute over the THS membership ──────────
def _setup_ths(monkeypatch, members):
    idx = pd.date_range("2025-01-02", periods=180, freq="B")
    closes = pd.DataFrame({
        "600000.SS": 100 * (1.001 ** np.arange(180)),
        "000001.SZ": 100 * (1.002 ** np.arange(180)),
        "600519.SS": 100 * (0.999 ** np.arange(180)),
    }, index=idx)
    bench = pd.DataFrame({"close": 4000 * (1.0008 ** np.arange(180)),
                          "volume": np.ones(180)}, index=idx)
    monkeypatch.setattr(bkc, "_closes", lambda: closes)
    monkeypatch.setattr(bkc.store, "read",
                        lambda g, n: bench if (g, n) == ("china", BENCH_SYM) else None)
    monkeypatch.setattr(bkc, "_ths_membership", lambda: {
        "baskets": members, "benchmark": BENCH_SYM,
        "benchmark_label": "CSI 300", "benchmark_label_zh": "沪深300"})
    return bench


def test_compute_ths_baskets_invariants(monkeypatch):
    members = {
        "ths_x": {"name": "Theme X", "name_zh": "白酒概念", "category": "Consumer",
                  "category_zh": "消费", "etf_proxy": None, "created": "2025-01-02",
                  "thesis": "x", "thesis_zh": "甲", "members": [
                      {"ticker": "600000.SS", "added": "2025-01-02", "removed": None, "name_zh": "甲", "rationale": "r"},
                      {"ticker": "000001.SZ", "added": "2025-01-02", "removed": None, "name_zh": "乙", "rationale": "r"},
                      {"ticker": "600519.SS", "added": "2025-01-02", "removed": None, "name_zh": "丙", "rationale": "r"},
                      {"ticker": "999999.SS", "added": "2025-01-02", "removed": None, "name_zh": "丁", "rationale": "r"}]},
        "ths_thin": {"name": "Thin", "category": "Consumer", "created": "2025-01-02", "members": [
            {"ticker": "600000.SS", "added": "2025-01-02"}, {"ticker": "000001.SZ", "added": "2025-01-02"}]},
    }
    bench = _setup_ths(monkeypatch, members)
    out = bkc.compute_china_ths_baskets()
    assert out is not None
    assert [b["id"] for b in out["baskets"]] == ["ths_x"]               # thin (<3 present) skipped
    b = out["baskets"][0]
    assert b["n_members"] == 3 and b["missing"] == ["999999.SS"]        # off-cache member surfaced
    assert b["name_zh"] == "白酒概念" and b["category_zh"] == "消费"
    assert {m["name"] for m in b["members"]} == {"甲", "乙", "丙"}        # display name = name_zh
    br = bench["close"].iloc[-1] / bench["close"].iloc[-21] - 1
    assert abs(b["perf"]["20d"]["rel"] - (b["perf"]["20d"]["ret"] - br)) < 1e-6


def test_ths_degrades_without_membership(monkeypatch):
    monkeypatch.setattr(bkc, "_ths_membership", lambda: None)
    assert bkc.compute_china_ths_baskets() is None


# ── seed: point-in-time membership from snapshot diffs ────────────────────────
def _zh(t, fallback):  # stand-in for the canonical-name lookup
    return fallback


def test_pit_first_run_seeds_at_seed_and_filters_universe():
    """One snapshot (first run): every covered member added at SEED; off-cache names → missing."""
    snaps = [("2026-06-27", {"白酒概念": [
        {"ticker": "600519.SS", "name": "贵州茅台"},
        {"ticker": "000858.SZ", "name": "五粮液"},
        {"ticker": "899999.BJ", "name": "某北交所"}]})]   # outside the price cache
    universe = {"600519.SS", "000858.SZ"}
    members, missing = seed._pit_members("白酒概念", snaps, universe, _zh)
    assert {m["ticker"] for m in members} == {"600519.SS", "000858.SZ"}
    assert all(m["added"] == seed.SEED and m["removed"] is None for m in members)
    assert missing == ["899999.BJ"]


def test_pit_diff_dates_entries_and_exits():
    """Across snapshots: a name first seen later is dated then; a dropped name gets a removed date."""
    snaps = [
        ("2026-06-01", {"T": [{"ticker": "600000.SS", "name": "A"}, {"ticker": "000001.SZ", "name": "B"}]}),
        ("2026-06-15", {"T": [{"ticker": "600000.SS", "name": "A"}, {"ticker": "600519.SS", "name": "C"}]}),
    ]
    universe = {"600000.SS", "000001.SZ", "600519.SS"}
    members, missing = seed._pit_members("T", snaps, universe, _zh)
    by = {m["ticker"]: m for m in members}
    assert by["600000.SS"]["added"] == seed.SEED and by["600000.SS"]["removed"] is None   # present throughout
    assert by["000001.SZ"]["added"] == seed.SEED and by["000001.SZ"]["removed"] == "2026-06-15"  # dropped
    assert by["600519.SS"]["added"] == "2026-06-15" and by["600519.SS"]["removed"] is None       # entered later
    assert missing == []
