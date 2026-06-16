"""Unit tests for the IPO Radar — collectors/ipo_calendar.py + engine/ipo_radar.py.

Lock the display-only semantics (see research/IPO_RADAR.md): the calendar parses
Nasdaq's offer terms + flags SPACs, the window read bands risk appetite, and NOTHING
here is ever scored or consumed by a scoring module. No network, no real data: the
collector parse is fed a synthetic Nasdaq-shaped dict and the engine reads are
monkeypatched / passed synthetic frames.
"""
import pathlib
from datetime import timedelta

import pandas as pd
import pytest

import collectors.ipo_calendar as ic
import collectors.ipo_prospectus as ipro
import engine.ipo_lockup as il
import engine.ipo_radar as ir


# --------------------------------------------------------------------------- #
# collector parse (pure)
# --------------------------------------------------------------------------- #
def test_num_date_range_helpers():
    assert ic._num("$74,999,999,925") == 74999999925.0
    assert ic._num("135.00") == 135.0
    assert ic._num("") is None and ic._num(None) is None
    assert ic._date_iso("6/12/2026") == "2026-06-12"
    assert ic._date_iso("") is None and ic._date_iso(None) is None
    assert ic._price_range("14.00-16.00") == (14.0, 16.0, 15.0)
    assert ic._price_range("18.00") == (18.0, 18.0, 18.0)
    assert ic._price_range(None) == (None, None, None)


def test_is_spac_heuristic():
    assert ic._is_spac("JAB Acquisition Corp I", "JABRU", 10.0) is True   # name match
    assert ic._is_spac("Foo Holdings", "FOOU", 10.0) is True              # $10 unit ticker
    assert ic._is_spac("Foo Holdings", "FOOU", 20.0) is False             # unit but not $10
    assert ic._is_spac("SPACE EXPLORATION TECHNOLOGIES CORP", "SPCX", 135.0) is False
    assert ic._is_spac("Parabilis Medicines, Inc.", "PBLS", 20.0) is False


def _nasdaq_payload():
    return {"data": {
        "priced": {"rows": [
            {"dealID": "1", "proposedTickerSymbol": "spcx",
             "companyName": "SPACE EXPLORATION TECHNOLOGIES CORP", "proposedExchange": "NASDAQ",
             "proposedSharePrice": "135.00", "sharesOffered": "555,555,555",
             "pricedDate": "6/12/2026", "dollarValueOfSharesOffered": "$74,999,999,925"},
            {"dealID": "2", "proposedTickerSymbol": "JABRU", "companyName": "JAB Acquisition Corp I",
             "proposedSharePrice": "10.00", "sharesOffered": "15,000,000",
             "pricedDate": "6/10/2026", "dollarValueOfSharesOffered": "$150,000,000"},
        ]},
        "upcoming": {"upcomingTable": {"rows": [
            {"dealID": "3", "proposedTickerSymbol": "KARD", "companyName": "Kardigan, Inc.",
             "proposedSharePrice": "14.00-16.00", "sharesOffered": "23,333,334",
             "expectedPriceDate": "6/18/2026", "dollarValueOfSharesOffered": "$429,333,344"},
        ]}},
        "filed": {"rows": [
            {"dealID": "4", "proposedTickerSymbol": "SAMOU",
             "companyName": "Samos Energy Acquisition Corp", "filedDate": "6/12/2026",
             "dollarValueOfSharesOffered": "$230,000,000"},
        ]},
        "withdrawn": {"rows": [
            {"dealID": "5", "proposedTickerSymbol": None, "companyName": "Club Versante",
             "filedDate": "7/15/2025", "withdrawDate": "6/11/2026",
             "dollarValueOfSharesOffered": "$21,562,500"},
        ]},
    }}


def test_rows_from_month_parses_all_sections():
    rows = {r["deal_id"]: r for r in ic._rows_from_month(_nasdaq_payload())}
    assert set(rows) == {"1", "2", "3", "4", "5"}

    spcx = rows["1"]
    assert spcx["ticker"] == "SPCX" and spcx["status"] == "priced"
    assert spcx["offer_price"] == 135.0                      # single price = final offer
    assert spcx["shares"] == 555555555.0
    assert spcx["offer_value_usd"] == 74999999925.0
    assert spcx["priced_date"] == "2026-06-12" and spcx["is_spac"] is False

    assert rows["2"]["is_spac"] is True                      # JAB Acquisition Corp ($10 unit)

    kard = rows["3"]
    assert kard["status"] == "upcoming"
    assert kard["offer_price"] is None                       # a range, not a final price
    assert (kard["range_low"], kard["range_high"], kard["range_mid"]) == (14.0, 16.0, 15.0)
    assert kard["expected_date"] == "2026-06-18"

    assert rows["4"]["status"] == "filed" and rows["4"]["is_spac"] is True
    assert rows["5"]["status"] == "withdrawn" and rows["5"]["withdraw_date"] == "2026-06-11"


# --------------------------------------------------------------------------- #
# engine — window read (monkeypatched market reads)
# --------------------------------------------------------------------------- #
def _vix(level):
    return pd.Series([level], index=[pd.Timestamp("2026-06-15")])


def test_window_open_when_appetite_broad(monkeypatch):
    monkeypatch.setattr(ir, "_rs", lambda num, den, lookback=63: 0.05)   # all RS legs constructive
    monkeypatch.setattr(ir, "_close", lambda t: _vix(15.0) if t == "^VIX" else None)
    w = ir.window_context(risk_score=20.0)
    assert w["band"] == "OPEN"
    assert w["constructive"] == w["n_legs"] and w["hostile"] == 0


def test_window_shut_when_appetite_absent(monkeypatch):
    monkeypatch.setattr(ir, "_rs", lambda num, den, lookback=63: -0.05)
    monkeypatch.setattr(ir, "_close", lambda t: _vix(35.0) if t == "^VIX" else None)
    w = ir.window_context(risk_score=85.0)
    assert w["band"] == "SHUT"
    assert w["hostile"] >= max(2, w["n_legs"] * 0.5)


def test_window_handles_missing_data(monkeypatch):
    monkeypatch.setattr(ir, "_rs", lambda num, den, lookback=63: None)
    monkeypatch.setattr(ir, "_close", lambda t: None)
    w = ir.window_context(risk_score=None)
    assert w["band"] == "unknown" and w["legs"] == [] and w["n_legs"] == 0


# --------------------------------------------------------------------------- #
# engine — deal calendar views (synthetic frame)
# --------------------------------------------------------------------------- #
def _cal():
    today = pd.Timestamp.now("UTC").normalize()

    def iso(days):
        return (today - timedelta(days=days)).strftime("%Y-%m-%d")

    cols = ["ticker", "company", "exchange", "status", "offer_price", "range_low",
            "range_high", "range_mid", "shares", "offer_value_usd", "priced_date",
            "expected_date", "filed_date", "withdraw_date", "is_spac"]

    def row(**kw):
        r = {c: None for c in cols}
        r.update(kw)
        return r

    data = {
        "r1": row(ticker="AAA", company="Alpha Co", exchange="NYSE", status="priced",
                  offer_price=20.0, offer_value_usd=2e8, priced_date=iso(5), is_spac=False),
        "r2": row(ticker="SPCU", company="Spac Acquisition Corp", status="priced",
                  offer_price=10.0, offer_value_usd=1.5e8, priced_date=iso(20), is_spac=True),
        "r3": row(ticker="OLD", company="Old Co", status="priced",
                  offer_price=15.0, offer_value_usd=1e8, priced_date=iso(400), is_spac=False),
        "r4": row(ticker="UPC", company="Upcoming Co", status="upcoming",
                  range_low=14.0, range_high=16.0, offer_value_usd=3e8,
                  expected_date=iso(-3), is_spac=False),
        "r5": row(ticker=None, company="Pulled Co", status="withdrawn",
                  withdraw_date=iso(10), is_spac=False),
    }
    df = pd.DataFrame.from_dict(data, orient="index")
    df.index.name = "deal_id"
    return df


def test_recent_listings_window_and_fields(monkeypatch):
    monkeypatch.setattr(ir, "_close", lambda t: None)        # no since-offer data
    rec = ir.recent_listings(_cal(), days=120)
    tickers = [r["ticker"] for r in rec]
    assert "AAA" in tickers and "SPCU" in tickers and "OLD" not in tickers   # 400d aged out
    aaa = next(r for r in rec if r["ticker"] == "AAA")
    assert aaa["days_since"] == 5 and aaa["size_band"] == "mid" and aaa["since_offer"] is None
    assert next(r for r in rec if r["ticker"] == "SPCU")["is_spac"] is True


def test_pipeline_stats_counts_and_froth():
    p = ir.pipeline_stats(_cal())
    assert p["available"] is True
    assert p["priced_90d"] == 2 and p["operating_90d"] == 1 and p["spac_90d"] == 1
    assert p["spac_pct_90d"] == 50 and p["pace"] == "quiet"
    assert p["upcoming_n"] == 1


def test_upcoming_listings():
    up = ir.upcoming_listings(_cal())
    assert len(up) == 1 and up[0]["ticker"] == "UPC"
    assert up[0]["range_low"] == 14.0 and up[0]["range_high"] == 16.0


def test_size_band_thresholds():
    assert ir._size_band(75e9) == "mega"
    assert ir._size_band(4e8) == "large"
    assert ir._size_band(1.5e8) == "mid"
    assert ir._size_band(5e7) == "small"
    assert ir._size_band(None) is None


def test_calendar_views_degrade_on_empty():
    empty = pd.DataFrame()
    assert ir.recent_listings(empty) == []
    assert ir.upcoming_listings(empty) == []
    assert ir.pipeline_stats(empty) == {"available": False}


# --------------------------------------------------------------------------- #
# the never-scored invariant
# --------------------------------------------------------------------------- #
def test_scored_flag_is_false():
    assert ir.SCORED is False
    snap = ir.radar_snapshot(risk_score=None)
    assert snap["scored"] is False
    assert "pop" in snap["disclaimer"].lower()
    assert isinstance(snap["window"]["legs"], list)


def test_not_imported_by_any_scoring_module():
    """ipo_radar/ipo_lockup must never feed a scored axis/regime/allocation — assert
    the core scoring modules don't import them."""
    root = pathlib.Path(ir.__file__).parent
    for mod in ("axes.py", "conditions.py", "regime.py", "equity_alloc.py"):
        src = (root / mod).read_text()
        assert "ipo_radar" not in src, f"engine/{mod} must not import ipo_radar"
        assert "ipo_lockup" not in src, f"engine/{mod} must not import ipo_lockup"


# --------------------------------------------------------------------------- #
# Phase 2 — lock-up prospectus parse + overhang engine
# --------------------------------------------------------------------------- #
def test_parse_lockup_days_prefers_canonical_over_early_release():
    # modern lock-ups bury an early-release "after 90 days" next to the word lock-up;
    # the canonical length phrasing must win → 180
    txt = ("The common stock is subject to a lock-up agreement. Each holder agrees to a "
           "lock-up period of 180 days after the date of this prospectus. The lock-up may "
           "be released early after 90 days if the closing price exceeds 133% of the offer.")
    assert ipro.parse_lockup_days(txt) == 180
    assert ipro.parse_lockup_days("subject to a 90-day lock-up") == 90
    assert ipro.parse_lockup_days("no lock-up language with a number here") is None
    assert ipro.parse_lockup_days("nothing relevant") is None


def _lockcal():
    today = pd.Timestamp.now("UTC").normalize()

    def iso(days):
        return (today - timedelta(days=days)).strftime("%Y-%m-%d")

    cols = ["ticker", "company", "status", "priced_date", "is_spac", "offer_value_usd"]

    def row(**kw):
        r = {c: None for c in cols}
        r.update(kw)
        return r

    data = {
        "a": row(ticker="FRESH", company="Fresh Co", status="priced",
                 priced_date=iso(10), is_spac=False, offer_value_usd=2e8),       # +170d → locked
        "b": row(ticker="APPR", company="Approaching Co", status="priced",
                 priced_date=iso(160), is_spac=False, offer_value_usd=1e8),      # +20d → approaching
        "c": row(ticker="OVER", company="Overhang Co", status="priced",
                 priced_date=iso(195), is_spac=False, offer_value_usd=1e8),      # -15d → just-expired
        "d": row(ticker="OLDX", company="Old Co", status="priced",
                 priced_date=iso(900), is_spac=False, offer_value_usd=1e8),      # way past
        "e": row(ticker="SPCU", company="Spac Acquisition Corp", status="priced",
                 priced_date=iso(160), is_spac=True, offer_value_usd=1e8),       # SPAC → excluded
    }
    df = pd.DataFrame.from_dict(data, orient="index")
    df.index.name = "deal_id"
    return df


def test_lockup_rows_status_excludes_spacs_and_uses_confirmed_days():
    cal = _lockcal()
    lk = pd.DataFrame({"lockup_days": [90]}, index=pd.Index(["APPR"], name="ticker"))
    rows = {r["ticker"]: r for r in il.lockup_rows(cal, lk, lookback_days=300)}
    assert "SPCU" not in rows                       # SPACs excluded
    assert "OLDX" not in rows                       # outside lookback
    assert rows["FRESH"]["status"] == "locked"
    assert rows["OVER"]["status"] == "just-expired" and rows["OVER"]["days_to"] < 0
    # APPR has a prospectus-confirmed 90d lock-up → expiry = priced(160d ago)+90 = 70d ago
    assert rows["APPR"]["lockup_days"] == 90 and rows["APPR"]["source"] == "confirmed"
    assert rows["FRESH"]["lockup_days"] == 180 and rows["FRESH"]["source"] == "estimate"


def test_actionable_tickers_targets_the_window():
    cal = _lockcal()
    act = il.actionable_tickers(cal)               # 180d-estimate expiry within [-30,+45]
    assert "APPR" in act and "OVER" in act
    assert "FRESH" not in act and "OLDX" not in act


def test_lockup_summary_counts():
    s = il.summary(il.lockup_rows(_lockcal(), None))
    assert s["approaching"] >= 1 and s["just_expired"] >= 1
    assert s["next_ticker"] in ("APPR", "FRESH")   # soonest upcoming expiry


def test_ipo_lockup_scored_flag_false():
    assert il.SCORED is False
    assert il.lockup_rows(pd.DataFrame()) == []     # degrades on empty
