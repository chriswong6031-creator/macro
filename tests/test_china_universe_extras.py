"""Guard the China A-Share search-universe manual-add hook.

`china.search_universe.extra_tickers`/`extra_names` (config) + the seed/union in
`collectors.china_universe` keep individual A-shares searchable even when they sit
BELOW the Sina top-800 / CSI-1000 cutoff. The seeded name_en/name_zh/sector must win
over (and skip) the flaky yfinance get_info that mislabels small caps — without ever
touching the calibrated breadth/regime universe (china.constituents)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import china_universe as cu  # noqa: E402
from lib import config  # noqa: E402

# The names wired in 2026-06-25 (seven sub-cutoff A-shares: 旗天科技 + the user's
# six-name watchlist) that the Sina top-800 / CSI universe never reaches.
EXPECTED = ["300061.SZ", "301531.SZ", "688508.SS", "300580.SZ",
            "688049.SS", "300470.SZ", "688609.SS"]


class _CountingTicker:
    """yfinance.Ticker stand-in that records every lookup and returns no info, so a
    test can assert the seeded names are NEVER looked up (and never hit the network)."""
    calls: list[str] = []

    def __init__(self, ticker: str) -> None:
        _CountingTicker.calls.append(ticker)

    def get_info(self) -> dict:
        return {}


def _no_network(monkeypatch):
    _CountingTicker.calls = []
    monkeypatch.setattr(cu.yf, "Ticker", _CountingTicker)


def test_config_extras_wired():
    sv = config.load()["china"]["search_universe"]
    tickers = sv.get("extra_tickers") or []
    names = sv.get("extra_names") or {}
    for t in EXPECTED:
        assert t in tickers, f"{t} missing from extra_tickers"
        assert t in names, f"{t} missing from extra_names"
        assert str(names[t].get("name_en") or "").strip(), f"{t} has no seeded name_en"
        assert str(names[t].get("sector") or "").strip(), f"{t} has no seeded sector"


def test_enrich_seed_fills_new_name_without_lookup(monkeypatch):
    _no_network(monkeypatch)
    ad = cu.ChinaUniverseAdapter()
    uni = pd.DataFrame({"name_zh": [""], "mktcap_yi": [108.0]},
                       index=pd.Index(["688508.SS"], name="ticker"))
    seed = {"688508.SS": {"name_en": "Wuxi Chipown Micro-electronics",
                          "name_zh": "芯朋微", "sector": "Technology"}}
    out = ad._enrich(uni, prev=None, seed=seed)
    assert out.at["688508.SS", "name_en"] == "Wuxi Chipown Micro-electronics"
    assert out.at["688508.SS", "sector"] == "Technology"
    # name_zh was empty -> seed fills it; combined display is "English / 中文"
    assert out.at["688508.SS", "name"] == "Wuxi Chipown Micro-electronics / 芯朋微"
    # both fields seeded -> the name never enters the get_info queue
    assert _CountingTicker.calls == []


def test_enrich_seed_only_if_empty(monkeypatch):
    """Seed must not clobber an already-cached value (only-if-empty) — it removes the
    name from the lookup queue, it does not overwrite prior enrichment."""
    _no_network(monkeypatch)
    ad = cu.ChinaUniverseAdapter()
    uni = pd.DataFrame({"name_zh": ["芯朋微"], "mktcap_yi": [108.0]},
                       index=pd.Index(["688508.SS"], name="ticker"))
    prev = pd.DataFrame({"name_en": ["Cached EN"], "sector": ["Financial Services"]},
                        index=pd.Index(["688508.SS"], name="ticker"))
    out = ad._enrich(uni, prev=prev, seed={"688508.SS": {"name_en": "Seed EN", "sector": "Technology"}})
    assert out.at["688508.SS", "name_en"] == "Cached EN"
    assert out.at["688508.SS", "sector"] == "Financial Services"
    assert _CountingTicker.calls == []


def test_fetch_unions_extra_tickers(monkeypatch, tmp_path):
    _no_network(monkeypatch)
    ad = cu.ChinaUniverseAdapter()
    # Redirect EVERY path attr — a missed one (dropped_path, historically) makes
    # fetch() write the repo's real data/china_search/ tree (MM_DATA_GUARD).
    ad.dir, ad.closes_path, ad.members_path, ad.dropped_path = (
        tmp_path, tmp_path / "closes.parquet", tmp_path / "members.parquet",
        tmp_path / "dropped.parquet")

    sina = pd.DataFrame({"name_zh": ["Big A", "Big B"], "mktcap_yi": [1000.0, 900.0]},
                        index=pd.Index(["600000.SS", "000001.SZ"], name="ticker"))
    monkeypatch.setattr(ad, "_sina_universe", lambda: sina)
    monkeypatch.setattr(ad, "_index_constituents", lambda syms: [])

    cols = list(sina.index) + ad.extra_tickers
    idx = pd.bdate_range("2020-01-01", periods=400)
    closes = pd.DataFrame(1.0, index=idx, columns=cols).cumsum()
    monkeypatch.setattr(ad, "_download_closes",
                        lambda tickers, period: closes[[t for t in tickers if t in closes.columns]])

    ad.fetch()
    mb = pd.read_parquet(ad.members_path)
    cl = pd.read_parquet(ad.closes_path)
    for t in ad.extra_tickers:
        assert t in mb.index, f"{t} not unioned into members"
        assert t in cl.columns, f"{t} not unioned into closes"
    # the seeded curation survives the full fetch() path
    assert mb.at["688508.SS", "sector"] == "Technology"
    assert mb.at["688508.SS", "name_en"] == "Wuxi Chipown Micro-electronics"
