"""Tests for the Quiver alt-data collector + engine (no network)."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from collectors import quiver
from engine import altdata
from lib import config


# --------------------------------------------------------------- coercion helpers
def test_usd_range_and_scalar():
    assert altdata._usd("$1,001 - $15,000") == pytest.approx(8000.5)
    assert altdata._usd("48395.4") == pytest.approx(48395.4)
    assert altdata._usd("$1,000,001 - $5,000,000") == pytest.approx(3000000.5)
    assert math.isnan(altdata._usd("nan"))
    assert math.isnan(altdata._usd(None))


def test_f_and_s_and_side():
    assert altdata._f("$1,234.5") == pytest.approx(1234.5)
    assert math.isnan(altdata._f("None"))
    assert altdata._s("nan") is None
    assert altdata._s("  AAPL ") == "AAPL"
    assert altdata._side("Purchase") == "buy"
    assert altdata._side("Sale (Full)") == "sell"
    assert altdata._side("Exchange") is None


# --------------------------------------------------------------- collector merge
class _DummyAdapter(quiver.QuiverAdapter):
    name = "quiver_test"
    dataset = "t_set"
    endpoint = "/beta/live/x"
    key_cols = ("Ticker", "Date", "Transaction")


def test_merge_is_append_only_and_dedups(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    a = _DummyAdapter()

    first = pd.DataFrame([
        {"Ticker": "ABC", "Date": "2026-06-01", "Transaction": "Purchase", "Note": "v1"},
        {"Ticker": "XYZ", "Date": "2026-06-01", "Transaction": "Sale", "Note": "v1"},
    ])
    added, total = a._merge(first)
    assert (added, total) == (2, 2)
    seen0 = pd.read_parquet(a._table_path())["_first_seen"].iloc[0]

    # re-fetch the SAME ABC row (a correction "v2") + one genuinely new row
    second = pd.DataFrame([
        {"Ticker": "ABC", "Date": "2026-06-01", "Transaction": "Purchase", "Note": "v2"},
        {"Ticker": "QQQ", "Date": "2026-06-02", "Transaction": "Purchase", "Note": "v1"},
    ])
    added2, total2 = a._merge(second)
    assert added2 == 1 and total2 == 3            # only QQQ is new
    out = pd.read_parquet(a._table_path())
    abc = out[out["Ticker"] == "ABC"].iloc[0]
    assert abc["Note"] == "v1"                    # keep='first' -> PIT record preserved
    assert abc["_first_seen"] == seen0            # first-seen latency stamp is stable


def test_snapshot_feed_keys_on_collected(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    class _Snap(quiver.QuiverAdapter):
        name = "quiver_snaptest"; dataset = "snap"; endpoint = "/x"
        snapshot = True; key_cols = ("Ticker", "_collected")

    s = _Snap()
    df = pd.DataFrame([{"Ticker": "BB", "Count": "10"}])
    added, total = s._merge(df)
    assert added == total == 1
    assert "_collected" in pd.read_parquet(s._table_path()).columns


# --------------------------------------------------------------- engine signals
def _patch_reads(monkeypatch, tables: dict):
    monkeypatch.setattr(altdata, "_read", lambda ds: tables.get(ds))


def test_political_netflow(monkeypatch):
    congress = pd.DataFrame([
        {"Ticker": "AAA", "TransactionDate": "2026-06-10", "Transaction": "Purchase",
         "Representative": "Rep A", "BioGuideID": "A1", "Party": "R", "Range": "$1,001 - $15,000"},
        {"Ticker": "AAA", "TransactionDate": "2026-06-11", "Transaction": "Purchase",
         "Representative": "Rep B", "BioGuideID": "B2", "Party": "D", "Range": "$15,001 - $50,000"},
        {"Ticker": "AAA", "TransactionDate": "2026-06-12", "Transaction": "Sale",
         "Representative": "Rep C", "BioGuideID": "C3", "Party": "R", "Range": "$1,001 - $15,000"},
    ])
    _patch_reads(monkeypatch, {"congress": congress})
    res = altdata.political_netflow(window_days=3650)
    top = res["buys"][0]
    assert top["ticker"] == "AAA"
    assert top["buys"] == 2 and top["sells"] == 1 and top["net"] == 1
    assert top["members"] == 3
    assert top["est_usd"] > 0


def test_convergence_scores_distinct_channels():
    signals = {
        "political": {"buys": [{"ticker": "EFX", "net": 3, "members": 2}]},
        "gov_contracts": [{"ticker": "EFX", "total_usd": 1_000_000}],
        "trump": [{"ticker": "EFX", "side": "buy", "company": "EQUIFAX"}],
        "lobbying": [], "insiders": {"buys": []}, "offexchange": [],
        "cnbc": [], "inst_13f": {"adds": []},
    }
    rows = altdata.convergence(signals)
    assert rows and rows[0]["ticker"] == "EFX"
    assert rows[0]["score"] == 3
    assert set(rows[0]["channel_list"]) == {"congress_buy", "gov_contract", "trump_buy"}


def test_convergence_ignores_single_channel():
    signals = {"political": {"buys": [{"ticker": "ONE", "net": 1, "members": 1}]},
               "gov_contracts": [], "trump": [], "lobbying": [], "insiders": {"buys": []},
               "offexchange": [], "cnbc": [], "inst_13f": {"adds": []}}
    assert altdata.convergence(signals) == []
