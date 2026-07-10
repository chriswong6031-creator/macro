"""OpenFIGI CUSIP→ticker master: match-picking + cache load + smart_money merge."""
from __future__ import annotations

import pandas as pd

import collectors.openfigi as of
import engine.smart_money as sm


def test_pick_prefers_us_composite_equity():
    matches = [
        {"ticker": "NVDA", "exchCode": "UN", "marketSector": "Equity"},
        {"ticker": "NVDA", "exchCode": "US", "marketSector": "Equity"},   # composite
        {"ticker": "NVDA", "exchCode": "GR", "marketSector": "Equity"},   # foreign
    ]
    assert of._pick(matches)["ticker"] == "NVDA"


def test_pick_normalizes_share_class_slash():
    assert of._pick([{"ticker": "BRK/A", "exchCode": "US",
                      "marketSector": "Equity"}])["ticker"] == "BRK-A"


def test_pick_prefers_equity_over_other_sectors():
    matches = [{"ticker": "ZZZ", "exchCode": "US", "marketSector": "Corp"},
               {"ticker": "ABC", "exchCode": "US", "marketSector": "Equity"}]
    assert of._pick(matches)["ticker"] == "ABC"


def test_pick_empty_or_tickerless():
    assert of._pick([]) is None
    assert of._pick([{"exchCode": "US", "marketSector": "Equity"}]) is None


def test_load_cusip_ticker_drops_empties(tmp_path, monkeypatch):
    p = tmp_path / "cusip_ticker.parquet"
    pd.DataFrame({"cusip": ["aaa", "BBB", "CCC"],
                  "ticker": ["x", "", "ZZ"]}).to_parquet(p)
    monkeypatch.setattr(of, "_cache_path", lambda: p)
    m = of.load_cusip_ticker()
    assert m == {"AAA": "X", "CCC": "ZZ"}          # uppercased, empty BBB dropped


def test_full_cusip_map_seed_overrides_openfigi(tmp_path, monkeypatch):
    p = tmp_path / "cusip_ticker.parquet"
    pd.DataFrame({"cusip": ["AAA", "CCC"], "ticker": ["FIGI_A", "ZZ"]}).to_parquet(p)
    monkeypatch.setattr(of, "_cache_path", lambda: p)
    monkeypatch.setattr(sm, "cusip_ticker_seed", lambda: {"AAA": "SEEDWIN"})
    mapping, meta = sm.full_cusip_map()
    assert mapping["AAA"] == "SEEDWIN"              # hand-verified seed wins on conflict
    assert mapping["CCC"] == "ZZ"                   # OpenFIGI-only entry kept
    assert meta["openfigi_entries"] >= 2            # OpenFIGI contributed entries
    assert meta["ark_seed_entries"] >= 1            # seed contributed entries


def test_full_cusip_map_degrades_without_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(of, "_cache_path", lambda: tmp_path / "nope.parquet")
    monkeypatch.setattr(sm, "cusip_ticker_seed", lambda: {"AAA": "X"})
    mapping, meta = sm.full_cusip_map()             # returns (dict, meta) always
    assert mapping == {"AAA": "X"}                  # no cache -> just the seed
    assert meta["openfigi_entries"] == 0            # OpenFIGI contributed nothing
    assert meta["ark_seed_entries"] == 1            # seed contributed 1 entry
