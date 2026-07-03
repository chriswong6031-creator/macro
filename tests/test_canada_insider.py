"""Canada insider engine tests (engine/canada_insider.py).

Pure-function checks on the classification + summarisation (no network / no cache):
open-market text -> buy/sell, issuer rows excluded as company buybacks, the trailing
window filters old filings, the lean is computed from value-then-shares, and
insider_map reads the long-form transactions store (migrating the legacy JSON-blob
cache) and degrades to empty without one. CONTEXT, not a validated signal."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import canada_insider as ci  # noqa: E402


def test_row_action_classifies_open_market_only():
    assert ci._row_action("Acquisition in the public market at price 15.88 per share") == "buy"
    assert ci._row_action("Disposition in the public market at price 199.71 per share") == "sell"
    # not open-market -> dropped from the lean
    assert ci._row_action("Redemption, retraction, cancelation, repurchase") == "other"
    assert ci._row_action("Exercise of options") == "other"
    assert ci._row_action("") == "other"


def test_role_and_company_classification():
    assert ci._role("Director of Issuer") == "Director"
    assert ci._role("Senior Officer of Issuer") == "Officer"
    assert ci._role("10% Security Holder of Issuer") == "10% owner"
    assert ci._role("Issuer") == "Issuer"
    # the company itself (a buyback), not a person
    assert ci._is_company("Issuer") is True
    assert ci._is_company("Director of Issuer") is False


def test_normalize_df_maps_yfinance_columns():
    df = pd.DataFrame({
        "Shares": [1000, 500],
        "Value": [15880.0, None],
        "Text": ["Acquisition in the public market at price 15.88 per share",
                 "Disposition in the public market"],
        "Insider": ["Di Bert (John)", "Smith Jane"],
        "Position": ["Senior Officer of Issuer", "Director of Issuer"],
        "Start Date": pd.to_datetime(["2026-05-29", "2026-05-20"]),
    })
    rows = ci._normalize_df(df)
    assert len(rows) == 2
    assert rows[0]["action"] == "buy" and rows[0]["role"] == "Officer"
    assert rows[0]["personal"] is True and rows[0]["value"] == 15880.0
    assert rows[1]["action"] == "sell" and rows[1]["value"] is None
    assert ci._normalize_df(None) == [] and ci._normalize_df(pd.DataFrame()) == []


def _row(date, action, *, personal=True, shares=None, value=None, insider="X", role="Director"):
    text = ("Acquisition in the public market" if action == "buy"
            else "Disposition in the public market" if action == "sell" else "Exercise")
    return {"date": date, "insider": insider, "role": role,
            "personal": personal, "action": action, "shares": shares, "value": value}


def test_summarize_excludes_issuer_and_options_and_old_filings():
    now = pd.Timestamp("2026-06-21")
    rows = [
        _row("2026-06-10", "buy", shares=1000, value=20000, insider="A"),
        _row("2026-06-05", "buy", shares=500, value=10000, insider="B"),
        _row("2026-05-01", "sell", shares=300, value=6000, insider="C"),
        # excluded: a company buyback (not personal)
        _row("2026-06-12", "buy", shares=99999, value=9e9, personal=False, insider="ISSUER"),
        # excluded: an option exercise (action='other')
        _row("2026-06-12", "other", shares=4000, insider="A"),
        # excluded: outside the 180d window
        _row("2025-01-01", "buy", shares=8000, value=1e6, insider="D"),
    ]
    s = ci._summarize(rows, window_days=180, now=now)
    assert s["n_buys"] == 2 and s["n_sells"] == 1
    assert s["distinct_buyers"] == 2          # A, B (not the issuer)
    assert s["buy_value"] == 30000 and s["sell_value"] == 6000
    assert s["net_value"] == 24000
    assert s["lean"] == "buying"
    assert len(s["recent"]) == 3              # only the in-window personal open-market rows
    assert s["recent"][0]["date"] == "2026-06-10"   # most recent first


def test_summarize_lean_falls_back_to_shares_when_value_absent():
    now = pd.Timestamp("2026-06-21")
    rows = [_row("2026-06-10", "sell", shares=5000, insider="A"),
            _row("2026-06-09", "buy", shares=1000, insider="B")]
    s = ci._summarize(rows, now=now)
    assert s["net_value"] is None             # no dollar values present
    assert s["net_shares"] == -4000 and s["lean"] == "selling"


def test_summarize_none_when_no_open_market_personal_rows():
    now = pd.Timestamp("2026-06-21")
    assert ci._summarize([], now=now) is None
    # only an issuer buyback + an option exercise -> nothing to show
    rows = [_row("2026-06-10", "buy", personal=False), _row("2026-06-10", "other")]
    assert ci._summarize(rows, now=now) is None


def test_insider_map_empty_without_cache(tmp_path, monkeypatch):
    # patch BOTH stores: with only CACHE patched, _load_transactions() falls back
    # to migrating the real data/canada_insider/insider.parquet on this machine
    monkeypatch.setattr(ci, "CACHE", tmp_path / "missing.parquet")
    monkeypatch.setattr(ci, "_LEGACY_CACHE", tmp_path / "missing_legacy.parquet")
    assert ci.insider_map() == {}


def test_insider_map_reads_cache(tmp_path, monkeypatch):
    cache = tmp_path / "transactions.parquet"
    monkeypatch.setattr(ci, "CACHE", cache)
    monkeypatch.setattr(ci, "_LEGACY_CACHE", tmp_path / "missing_legacy.parquet")
    # a fresh in-window buy so the summary is non-empty regardless of run date
    recent = (pd.Timestamp.now() - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    row = {**_row(recent, "buy", shares=1000, value=20000, insider="A"), "ticker": "RY.TO"}
    pd.DataFrame([row]).to_parquet(cache, index=False)
    m = ci.insider_map()
    assert "RY.TO" in m and m["RY.TO"]["lean"] == "buying"
    assert m["RY.TO"]["asof"] == recent  # asof = latest transaction date


def test_insider_map_migrates_legacy_blob_cache(tmp_path, monkeypatch):
    import json
    cache = tmp_path / "transactions.parquet"
    legacy = tmp_path / "insider.parquet"
    monkeypatch.setattr(ci, "CACHE", cache)
    monkeypatch.setattr(ci, "_LEGACY_CACHE", legacy)
    recent = (pd.Timestamp.now() - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    payload = json.dumps([_row(recent, "buy", shares=1000, value=20000, insider="A")])
    pd.DataFrame([{"ticker": "RY.TO", "payload": payload, "asof": recent}]).to_parquet(legacy)
    m = ci.insider_map()
    assert "RY.TO" in m and m["RY.TO"]["lean"] == "buying"
    assert cache.exists()  # migration persisted the long-form store
