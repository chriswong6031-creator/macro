"""同花顺 (THS) thematic-baskets pipeline.

Covers the three new pieces of the THS-mirrored China baskets:
  • engine.baskets_china.compute_china_ths_baskets — same compute as the curated path but over the
    THS membership file (so the shared invariants hold: thin baskets skipped, off-cache members in
    `missing`, name_zh display, rel == ret − bench);
  • collectors.china_ths_concepts.to_suffixed — bare A-share code → exchange-suffixed store ticker;
  • scripts.seed_china_ths_baskets._pit_members — snapshot diff → point-in-time added/removed +
    universe filter (first run seeds at SEED; later snapshots date entries/exits genuinely);
  • scripts.build_baskets_china_ths.split_for_page — the page-weight split that moves member rows
    and per-basket level history out of the document into the fetched hydrate payload.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from collectors.china_ths_concepts import to_suffixed
from engine import baskets_china as bkc
from scripts import build_baskets_china_ths as bts
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


def test_pit_truncated_latest_snapshot_fabricates_no_exits():
    """A shrunken latest snapshot (truncated scrape) must NOT mark the missing tail as removed —
    every ever-seen member is carried forward as active (removed=None)."""
    full = [{"ticker": f"6000{i:02d}.SS", "name": str(i)} for i in range(10)]   # 10-name board
    trunc = full[:3]                                                            # scrape truncated to 3
    snaps = [("2026-06-27", {"T": full}), ("2026-06-30", {"T": trunc})]
    universe = {m["ticker"] for m in full}
    members, _ = seed._pit_members("T", snaps, universe, _zh)
    assert len(members) == 10                                    # all 10 retained
    assert all(m["removed"] is None for m in members)            # none fabricated as exits


def test_pit_genuine_exit_survives_when_board_holds_size():
    """A single drop with the board otherwise intact (size above the shrink floor) is a real exit."""
    prev = [{"ticker": f"6000{i:02d}.SS", "name": str(i)} for i in range(10)]
    latest = prev[1:] + [{"ticker": "600099.SS", "name": "new"}]   # drop one, add one → size holds
    snaps = [("2026-06-27", {"T": prev}), ("2026-06-30", {"T": latest})]
    universe = {m["ticker"] for m in prev} | {"600099.SS"}
    members, _ = seed._pit_members("T", snaps, universe, _zh)
    by = {m["ticker"]: m for m in members}
    assert by["600000.SS"]["removed"] == "2026-06-30"           # the genuine drop is dated
    assert by["600099.SS"]["added"] == "2026-06-30" and by["600099.SS"]["removed"] is None


# ── builder: page-weight split (heavy planes → fetched hydrate payload) ───────
def _split_fixture():
    """Two baskets with member lists of different lengths + a level series each."""
    data = {
        "as_of": "2026-08-02",
        "categories": ["Consumer", "Tech"],
        "baskets": [
            {"id": "ths_a", "name": "A", "category": "Consumer", "n_members": 3,
             "perf": {"20d": {"ret": 0.05, "rel": 0.01}},
             "members": [{"ticker": "600000.SS", "name": "甲"},
                         {"ticker": "000001.SZ", "name": "乙"},
                         {"ticker": "600519.SS", "name": "丙"}]},
            {"id": "ths_b", "name": "B", "category": "Tech", "n_members": 2,
             "perf": {"20d": {"ret": -0.02, "rel": -0.03}},
             "members": [{"ticker": "300750.SZ", "name": "丁"},
                         {"ticker": "688981.SS", "name": "戊"}]},
        ],
    }
    chart = {"dates": ["2026-07-31", "2026-08-01"], "bench": [100.0, 101.0],
             "baskets": {"ths_a": [100.0, 103.0], "ths_b": [100.0, 98.0]}}
    return data, chart


def test_split_for_page_moves_heavy_planes_out_of_the_document():
    data, chart = _split_fixture()
    slim_data, slim_chart, _ = bts.split_for_page(data, chart)

    # the two heavy planes are gone from what the page inlines …
    assert all("members" not in b for b in slim_data["baskets"])
    assert slim_chart["baskets"] == {}
    assert slim_data["hydrate"] == "chinabasketdata/baskets_ths_hydrate.json"
    # … while the summary planes still ship inline for first paint
    assert slim_chart["dates"] == chart["dates"] and slim_chart["bench"] == chart["bench"]
    assert slim_data["as_of"] == "2026-08-02" and slim_data["categories"] == ["Consumer", "Tech"]
    assert set(slim_data) == set(data) | {"hydrate"}
    assert [b["n_members"] for b in slim_data["baskets"]] == [3, 2]
    assert [b["perf"] for b in slim_data["baskets"]] == [b["perf"] for b in data["baskets"]]


def test_split_for_page_conserves_every_row_and_series():
    data, chart = _split_fixture()
    _, _, hydrate = bts.split_for_page(data, chart)

    assert hydrate["schema"] == "ths_hydrate.v1" and hydrate["as_of"] == "2026-08-02"
    assert hydrate["members"] == {b["id"]: b["members"] for b in data["baskets"]}
    assert (sum(len(v) for v in hydrate["members"].values())
            == sum(len(b["members"]) for b in data["baskets"]) == 5)   # no thinning
    assert hydrate["chart_baskets"] == chart["baskets"]


def test_split_for_page_does_not_mutate_its_inputs():
    """The freeze / latest.json / turn-annotation blocks downstream read the FULL objects."""
    data, chart = _split_fixture()
    bts.split_for_page(data, chart)

    assert [len(b["members"]) for b in data["baskets"]] == [3, 2]
    assert "hydrate" not in data
    assert chart["baskets"] == {"ths_a": [100.0, 103.0], "ths_b": [100.0, 98.0]}


# ── collector: complete-or-fail member paging ─────────────────────────────────
def test_concept_members_raises_on_truncation(monkeypatch):
    """A mid-pagination HTTP failure that survives the fresh-cookie retry raises ThsTruncated
    instead of returning the partial rows collected so far."""
    import collectors.china_ths_concepts as ths

    class _Resp:
        def __init__(self, status, text=""):
            self.status_code, self.text = status, text

    page1 = ("<table><tr><th>代码</th><th>名称</th></tr>"
             + "".join(f"<tr><td>60000{i}</td><td>n{i}</td></tr>" for i in range(10)) + "</table>")

    class _Sess:
        def get(self, url, timeout=0):
            return _Resp(200, page1) if "/page/1/" in url else _Resp(401)   # page 2 blocked, always

    monkeypatch.setattr(ths, "_PAGE_PAUSE", 0)
    monkeypatch.setattr(ths, "time", type("T", (), {"sleep": staticmethod(lambda *_: None)}))
    monkeypatch.setattr(ths, "_session", lambda *a, **k: _Sess())   # fresh-cookie retry stays offline
    import pytest
    with pytest.raises(ths.ThsTruncated):
        ths.concept_members("999999", _Sess())
