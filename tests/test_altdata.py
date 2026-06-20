"""Tests for the Quiver alt-data collector + engine (no network)."""
from __future__ import annotations

import math
from datetime import date

import pandas as pd
import pytest

from collectors import quiver
from engine import altdata, altdata_alerts, altdata_ledger, altdata_signals
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


# --------------------------------------------------------------- per-ticker substrate
def test_by_ticker_inversion(monkeypatch):
    monkeypatch.setattr(altdata_signals, "_write", lambda out: None)
    feed = {"as_of": "2026-06-19", "signals": {
        "political": {"buys": [{"ticker": "EFX", "net": 2, "members": 2}]},
        "gov_contracts": [{"ticker": "EFX", "total_usd": 1_000_000}],
        "trump": [{"ticker": "EFX", "side": "buy"},
                  {"ticker": "BKNG", "side": "buy"}, {"ticker": "BKNG", "side": "sell"}],
        "lobbying": [], "insiders": {"buys": []}, "offexchange": [],
        "inst_13f": {"adds": []}, "cnbc": [], "corporate_donors": [{"ticker": "EFX", "total_usd": 50000}],
    }}
    out = altdata_signals.build(feed)
    efx = out["tickers"]["EFX"]
    # congress + gov_contract + trump = 3 real channels; the donor row is recorded but
    # must NOT count toward the score (else it would be 4)
    assert efx["convergence_score"] == 3
    assert set(efx["channels"]) == {"congress_buy", "gov_contract", "trump"}
    assert efx["trump_linked"] is True
    assert efx["donor_usd"] == 50000
    # a Trump buy+sell round-trip on one name is ONE channel, not two
    bkng = out["tickers"]["BKNG"]
    assert bkng["convergence_score"] == 1 and bkng["channels"] == ["trump"]


# --------------------------------------------------------------- alert change-detection
def test_alerts_fire_on_enter_only(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    bt = {"as_of": "2026-06-19", "tickers": {
        "EFX": {"convergence_score": 2, "channels": ["gov_contract", "trump"], "trump_linked": True},
        "NVDA": {"convergence_score": 2, "channels": ["13f_add", "darkpool_accum"], "trump_linked": False},
        "AAA": {"convergence_score": 1, "channels": ["congress_buy"], "trump_linked": False},
    }}
    fired1 = altdata_alerts.rebuild(bt)
    assert len(fired1) == 2                                    # EFX + NVDA; AAA below MIN_SCORE
    assert any(e["severity"] == "high" and "EFX" in e["headline"] for e in fired1)  # trump-linked => high
    assert any(e["severity"] == "medium" and "NVDA" in e["headline"] for e in fired1)

    assert altdata_alerts.rebuild(bt) == []                   # unchanged -> nothing new

    bt2 = {"as_of": "2026-06-19", "tickers": dict(bt["tickers"])}
    bt2["tickers"]["NVDA"] = {"convergence_score": 3, "channels": ["13f_add", "darkpool_accum", "congress_buy"], "trump_linked": False}
    fired3 = altdata_alerts.rebuild(bt2)                       # score increase -> re-fires
    assert len(fired3) == 1 and "NVDA" in fired3[0]["headline"]


# --------------------------------------------------------------- falsifiable ledger
def test_ledger_logs_scorable_and_scores(tmp_path, monkeypatch):
    import json
    idx = pd.date_range("2026-01-01", "2026-05-01", freq="B")
    n = len(idx)

    def fake_closes(tk, root):  # WIN beats SPY; LOSE lags; PRIV has no price
        if tk == "SPY":
            return pd.Series([100 * (1 + 0.05 * i / n) for i in range(n)], index=idx)
        if tk == "WIN":
            return pd.Series([50 * (1 + 0.20 * i / n) for i in range(n)], index=idx)
        if tk == "LOSE":
            return pd.Series([50 * (1 - 0.15 * i / n) for i in range(n)], index=idx)
        return None
    # one patch covers build (via _level_asof) AND score (via the scorer's reads)
    monkeypatch.setattr(altdata_ledger._desk, "_close_series", fake_closes)

    bt = {"as_of": "2026-01-02", "tickers": {
        "WIN": {"convergence_score": 2, "channels": ["congress_buy", "trump"], "trump_linked": True},
        "LOSE": {"convergence_score": 2, "channels": ["insider_buy", "gov_contract"], "trump_linked": False},
        "PRIV": {"convergence_score": 3, "channels": ["a", "b", "c"], "trump_linked": False},
    }}
    new = altdata_ledger.build_theses(bt, root=tmp_path, today=date(2026, 1, 2))
    assert {r["ticker"] for r in new} == {"WIN", "LOSE"}       # PRIV unscorable -> skipped
    assert all(r["lean"] == "overweight" and r["conviction"] == "low" for r in new)

    # vintage dedupe — same day, windows still active -> nothing new
    assert altdata_ledger.build_theses(bt, root=tmp_path, today=date(2026, 1, 2)) == []

    # score once the window has elapsed (check_by ~2026-04-03; data runs to 2026-05-01)
    track = altdata_ledger.score(root=tmp_path, today=date(2026, 5, 2))
    assert track["scored_total"] == 2
    scored = [json.loads(l) for l in (tmp_path / "data" / "altdata" / "scored.jsonl").read_text().splitlines()]
    outcome = {r["id"].split("-")[-2]: r["outcome"] for r in scored}
    assert outcome["WIN"] == "hit" and outcome["LOSE"] == "miss"
    assert track["overall"]["hit_rate"] == 0.5
