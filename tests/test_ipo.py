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
import engine.ipo_hk as ihk
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
        for layer in ("ipo_radar", "ipo_lockup", "ipo_hk"):
            assert layer not in src, f"engine/{mod} must not import {layer}"


def test_price_revision_partial_adjustment():
    assert ir.price_revision(40, 31, 34)["label"] == "above-range"     # strong demand
    assert ir.price_revision(34, 31, 34)["label"] == "top-half"
    assert ir.price_revision(31.5, 31, 34)["label"] == "bottom-half"
    assert ir.price_revision(28, 31, 34)["label"] == "below-range"     # weak demand
    assert round(ir.price_revision(40, 31, 34)["pct"], 3) == 0.231
    assert ir.price_revision(34, float("nan"), float("nan")) is None   # NaN guard
    assert ir.price_revision(34, 34, 34) is None                       # flat = no real range
    assert ir.price_revision(None, 31, 34) is None


def test_revision_gate_coverage():
    """The display-only 'Demand (vs range)' column is gated on real marketed-range
    coverage — it stays hidden until MORE than REV_MIN_COVERAGE recent deals carry a
    revision (the range accrues only for deals seen pre-pricing), and prints an honest
    N-of-M either way. A null here never blocks anything — it gates a context column."""
    rev = {"label": "top-half", "pct": 0.02}
    # below the floor → hidden, coverage counted honestly against the full total
    few = [{"revision": rev}] * 5 + [{"revision": None}] * 20
    assert ir.revision_gate(few) == {"coverage": 5, "total": 25, "show": False}
    # exactly at the floor → still hidden (must EXCEED, not merely meet, the floor)
    assert ir.revision_gate([{"revision": rev}] * ir.REV_MIN_COVERAGE)["show"] is False
    # above the floor → shown
    many = [{"revision": rev}] * (ir.REV_MIN_COVERAGE + 1) + [{"revision": None}] * 3
    g = ir.revision_gate(many)
    assert g["coverage"] == ir.REV_MIN_COVERAGE + 1 and g["show"] is True
    # empty degrades cleanly (never raises, never shows)
    assert ir.revision_gate([]) == {"coverage": 0, "total": 0, "show": False}


def test_ipo_hk_backdrop_shape_and_not_scored():
    assert ihk.SCORED is False
    b = ihk.hk_backdrop()
    assert {"available", "legs", "verdict"} <= set(b)
    assert isinstance(b["legs"], list)
    assert b["verdict"] in ("receptive", "mixed", "poor", "unavailable")
    if b["available"]:
        for l in b["legs"]:
            assert l["state"] in ("constructive", "neutral", "cautious")


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


# --------------------------------------------------------------------------- #
# flagship-revamp additions — coverage disclosure, hardening, view-models
# --------------------------------------------------------------------------- #
def test_never_scored_invariant_intact():
    """All three display engines stay never-scored; the persisted snapshot must
    carry no score/axis/regime/allocation key (it is a display card only)."""
    assert ir.SCORED is False and il.SCORED is False and ihk.SCORED is False
    import json
    from lib import config
    p = config.data_dir() / "regime" / "ipo_latest.json"
    if p.exists():
        d = json.loads(p.read_text())
        for k in d:
            assert not any(bad in k.lower() for bad in ("score", "axis", "regime", "alloc"))


def test_window_context_has_coverage_keys(monkeypatch):
    monkeypatch.setattr(ir, "_rs", lambda num, den, lookback=63: 0.05)
    monkeypatch.setattr(ir, "_close", lambda t: _vix(15.0) if t == "^VIX" else None)
    w = ir.window_context(risk_score=20.0)
    assert w["n_expected"] == 6
    assert w["low_confidence"] == (w["n_legs"] < 5)
    # full 6-leg read here → not low confidence
    assert w["n_legs"] == 6 and w["low_confidence"] is False


def test_pipeline_stats_withdraw_rate_and_froth_flags():
    p = ir.pipeline_stats(_cal())
    assert "withdraw_rate_90d" in p and "froth_flags" in p
    # _cal(): 1 withdrawn @10d + 2 priced @<=90d → 1/(1+2) ≈ 33%
    assert p["withdraw_rate_90d"] == 33
    assert isinstance(p["froth_flags"], list)
    # 50% SPAC share ≥40 → 'spac'; 33% withdraw ≥20 → 'pulled'; 2 priced <45 → no 'pace'
    assert "spac" in p["froth_flags"] and "pulled" in p["froth_flags"]
    assert "pace" not in p["froth_flags"]


def test_pipeline_excludes_future_dated_priced_date():
    """A future-dated priced_date (bad feed row) must not count as a listing."""
    cal = _cal().copy()
    # add a future-priced row (days_since = -3) — should be rejected by the 0<=dsl clamp
    future = pd.Timestamp.now("UTC").normalize() + timedelta(days=3)
    cal.loc["rf"] = {c: None for c in cal.columns}
    cal.loc["rf", "ticker"] = "FUT"
    cal.loc["rf", "status"] = "priced"
    cal.loc["rf", "priced_date"] = future.strftime("%Y-%m-%d")
    cal.loc["rf", "is_spac"] = False
    cal.loc["rf", "offer_value_usd"] = 2e8
    p = ir.pipeline_stats(cal)
    assert p["priced_90d"] == 2          # AAA + SPCU only; FUT rejected
    rec = ir.recent_listings(cal, days=120)
    assert "FUT" not in [r["ticker"] for r in rec]


def test_is_spac_nan_becomes_not_spac_after_fillna():
    """A NaN is_spac must resolve to not-SPAC (bool(nan) is truthy, and .astype(bool)
    on a NaN raises on modern pandas — the fillna(False) is what makes both paths safe)."""
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

    df = pd.DataFrame.from_dict({
        "n": row(ticker="NANX", company="NaN Co", status="priced",
                 priced_date=iso(5), offer_value_usd=2e8, is_spac=float("nan")),
        "s": row(ticker="SPCU", company="Spac Acquisition Corp", status="priced",
                 priced_date=iso(20), offer_value_usd=1.5e8, is_spac=True),
    }, orient="index")
    df.index.name = "deal_id"
    # is_spac column is object dtype here (bool + NaN mix) — the realistic post-concat shape
    assert df["is_spac"].dtype == object
    p = ir.pipeline_stats(df)
    assert p["spac_90d"] == 1 and p["operating_90d"] == 1     # NaN → operating, not SPAC
    rec = ir.recent_listings(df, days=120)
    nanx = next(r for r in rec if r["ticker"] == "NANX")
    assert nanx["is_spac"] is False                           # scalar path NaN-safe too


# ---- build_ipo view-model builders (pure) ---------------------------------- #
import scripts.build_ipo as bi


def test_avoid_builds_three_items_on_hot_data():
    after = {"verdict": "trails"}
    pipe = {"froth_flags": ["spac", "pulled"], "spac_pct_90d": 51, "withdraw_rate_90d": 16}
    lk = {"approaching": 27, "just_expired": 4, "next_days": 0,
          "next_ticker": "EQPT", "next_date": "2026-07-22", "next_size_usd": 7.47e8}
    av = bi._build_avoid(after, pipe, lk, "2026-07-22")
    assert len(av["items"]) >= 3
    for it in av["items"]:
        assert it["title_en"] and it["title_zh"]
        assert "tone" in it and it["tone"] in ("red", "warn", "calm")
    # next_days==0 → the lock-up item is red (into the cliff)
    lock = next(i for i in av["items"] if "un-lock" in i["title_en"])
    assert lock["tone"] == "red"


def test_avoid_calm_when_nothing_urgent():
    av = bi._build_avoid({"verdict": "tracks"}, {"froth_flags": []},
                         {"approaching": 0, "just_expired": 0}, "2026-07-22")
    assert len(av["items"]) == 1 and av["items"][0]["tone"] == "calm"


def test_changed_emits_band_flip_item():
    prior = {"window_band": "SHUT", "verdict": "trails", "spac_pct_90d": 20,
             "next_lockup": "AAA", "lockups_approaching": 5}
    win = {"band": "OPEN"}
    after = {"verdict": "trails"}
    pipe = {"spac_pct_90d": 20}
    lk = {"next_ticker": "AAA", "approaching": 5}
    ch = bi._build_changed(prior, win, after, pipe, lk)
    assert ch["has_prior"] is True
    assert any("OPEN" in i["en"] and "SHUT" in i["en"] for i in ch["items"])
    band_item = next(i for i in ch["items"] if "OPEN" in i["en"])
    assert band_item["tone"] == "up"        # flip to OPEN reads constructive


def test_changed_defensive_on_missing_prior():
    assert bi._build_changed(None, {"band": "OPEN"}, {}, {}, {}) == {"has_prior": False, "items": []}
    assert bi._build_changed({}, {"band": "OPEN"}, {}, {}, {}) == {"has_prior": False, "items": []}


def test_lockup_timeline_shape_and_clamp():
    rows = [
        {"ticker": "EQPT", "company": "Eq Co", "expiry_date": "2026-07-22",
         "days_to": 0, "size_usd": 7.47e8, "status": "approaching", "source": "confirmed"},
        {"ticker": "OLD", "company": "Old", "expiry_date": "2026-01-01",
         "days_to": -200, "size_usd": 1e8, "status": "expired", "source": "estimate"},  # out of window
        {"ticker": "NAN", "company": "Nan", "expiry_date": "2026-09-01",
         "days_to": 40, "size_usd": float("nan"), "status": "locked", "source": "estimate"},
    ]
    tl = bi._build_lockup_timeline(rows, {"approaching": 27, "just_expired": 4,
                                          "confirmed": 48, "next_ticker": "EQPT",
                                          "next_date": "2026-07-22", "next_days": 0,
                                          "next_size_usd": 7.47e8})
    assert tl["horizon_days"] == 120
    tickers = [m["ticker"] for m in tl["markers"]]
    assert "EQPT" in tickers and "OLD" not in tickers      # -200d rejected
    for m in tl["markers"]:
        assert 0.0 <= m["pos_frac"] <= 1.0
    nanm = next(m for m in tl["markers"] if m["ticker"] == "NAN")
    assert nanm["size_bucket"] == "sm"                     # NaN size → sm bucket
    eqpt = next(m for m in tl["markers"] if m["ticker"] == "EQPT")
    assert eqpt["size_bucket"] == "lg" and eqpt["confirmed"] is True
    assert tl["next"]["ticker"] == "EQPT" and tl["approaching"] == 27


def test_chart_aftermarket_is_svg_not_plotly():
    out = bi._chart_aftermarket()
    assert out is None or ("<svg" in out and "plotly" not in out.lower())


def test_hk_vm_each_leg_has_note_zh():
    vm = bi._hk_vm()
    if vm.get("available"):
        for leg in vm["legs"]:
            assert leg.get("note_zh")            # bilingual note on every HK leg
        assert "stance_en" in vm and "stance_zh" in vm


# --------------------------------------------------------------------------- #
# Null contract — non-finite sentinels must never reach user-visible HTML
# (Wave-2 bug: site/ipo.html rendered "Range $nan-nan" / "Size $nan" because the
# engine returns raw pandas row cells, which surface float NaN — not None — for a
# missing offer_price/size_usd/range_low/range_high. `_finite()` + `_usd()`/`_pct()`
# are the producing-boundary fix; these tests render the FULL page template with
# planted sentinels and assert none of them leak into the rendered HTML.)
# --------------------------------------------------------------------------- #
import re

_NUMERIC_SENTINEL_RE = re.compile(r"(?<![a-zA-Z])(nan|-?inf)(?![a-zA-Z])", re.IGNORECASE)
# ^ word-boundary-aware: catches a bare "nan"/"inf"/"-inf" token but not "infrastructure",
# "Infineon", or any other prose word that merely CONTAINS the letters. Scoped further
# below to just the numeric-cell fragments we pulled out of the rendered page (the offer/
# size/range table cells and the AVOID-panel lock-up sentence), never the full-page HTML,
# because the page's disclaimers/footers legitimately contain "infrastructure"-like prose.


def _finite_sentinel_free(fragment: str) -> None:
    m = _NUMERIC_SENTINEL_RE.search(fragment)
    assert m is None, f"non-finite sentinel {m.group(0)!r} leaked into: {fragment!r}"


def test_finite_helper_normalizes_every_non_finite_shape():
    """_finite(): None passes through; NaN/NaT/pd.NA/+-inf all normalize to None;
    a real number (including 0) passes through unchanged."""
    assert bi._finite(None) is None
    assert bi._finite(float("nan")) is None
    assert bi._finite(pd.NA) is None
    assert bi._finite(pd.NaT) is None
    assert bi._finite(float("inf")) is None
    assert bi._finite(float("-inf")) is None
    assert bi._finite(0) == 0 and bi._finite(0.0) == 0.0
    assert bi._finite(21.5) == 21.5


def test_usd_and_pct_are_non_finite_safe_and_preserve_zero():
    for bad in (None, float("nan"), pd.NA, pd.NaT, float("inf"), float("-inf")):
        assert bi._usd(bad) == "—", f"_usd({bad!r}) leaked a sentinel"
        assert bi._pct(bad) == "—", f"_pct({bad!r}) leaked a sentinel"
    # a legitimate 0 is a REAL value, never the null glyph
    assert bi._usd(0) == "$0"
    assert bi._pct(0) == "+0.0%"
    assert bi._usd(3.5e8) == "$350M"


# ---- fixtures: one row per non-finite shape, plus a valid value and a real 0 --- #
def _recent_row(ticker, offer_price, size_usd, since_offer=None, **extra):
    row = {
        "ticker": ticker, "company": f"{ticker} Co", "exchange": "NASDAQ",
        "offer_price": offer_price, "size_usd": size_usd,
        "size_band": None, "priced_date": "2026-08-10", "days_since": 3,
        "is_spac": False, "since_offer": since_offer, "revision": None,
    }
    row.update(extra)
    return row


def _upcoming_row(ticker, range_low, range_high, size_usd, **extra):
    row = {
        "ticker": ticker, "company": f"{ticker} Co", "exchange": "NASDAQ",
        "range_low": range_low, "range_high": range_high, "size_usd": size_usd,
        "size_band": None, "expected_date": "2026-08-20", "is_spac": False,
    }
    row.update(extra)
    return row


def _synthetic_snap():
    recent = [
        _recent_row("NANX", float("nan"), float("nan"), since_offer=float("nan")),
        _recent_row("NAX2", pd.NA, pd.NA, since_offer=pd.NA),
        _recent_row("NAT1", pd.NaT, pd.NaT, since_offer=pd.NaT),
        _recent_row("INFX", float("inf"), float("-inf"), since_offer=float("inf")),
        _recent_row("NONX", None, None, since_offer=None),
        _recent_row("ZERX", 0.0, 0.0, since_offer=0.0),
        _recent_row("REAL", 21.5, 3.5e8, since_offer=0.125),
    ]
    upcoming = [
        _upcoming_row("RBOTH", float("nan"), float("nan"), float("nan")),   # both missing
        _upcoming_row("RLOWO", 18.0, float("nan"), 2e8),                    # low only
        _upcoming_row("RHIGO", float("nan"), 22.0, 2e8),                    # high only
        _upcoming_row("RFULL", 14.0, 16.0, 4e8),                            # complete range
        _upcoming_row("RNONE", None, None, None),                          # both None
        _upcoming_row("RZERO", 0.0, 5.0, 0.0),                             # legit 0 bound + 0 size
        _upcoming_row("RINF", float("inf"), float("-inf"), float("inf")),  # +-inf both sides
        _upcoming_row("RPDNA", pd.NA, pd.NA, pd.NA),                       # pandas NA both sides
    ]
    win = {"band": "MIXED", "constructive": 1, "hostile": 1, "n_legs": 2,
           "n_expected": 6, "low_confidence": True, "legs": []}
    after = {
        "rows": [
            {"ticker": "IPO", "label": "Renaissance IPO ETF",
             "1y": float("nan"), "3y": 0.0, "5y": 0.15},
            {"ticker": "SPY", "label": "S&P 500", "1y": 0.10, "3y": 0.30, "5y": 0.55},
        ],
        "verdict": "tracks", "ipo_5y": 0.15, "spy_5y": 0.20, "gap_5y": -0.05,
    }
    pipe = {
        "available": True, "froth_flags": [], "median_op_size_90d": float("nan"),
        "pace": "quiet", "priced_90d": 2, "spac_pct_90d": 10, "upcoming_n": len(upcoming),
    }
    return {
        "window": win, "aftermarket": after, "pipeline": pipe,
        "recent": recent, "upcoming": upcoming,
        "built": "2026-08-19T00:00:00Z", "as_of": "2026-08-19",
    }


def _render_ipo_html(monkeypatch, tmp_path):
    """Drive the REAL bi.build() pipeline end to end (same code path as production —
    window/aftermarket/pipeline view-models, the recent/upcoming loops with the fix
    under test, hero/avoid/changed builders, and the real ipo.html.j2 render) with
    every non-engine dependency stubbed out, and the output redirected to tmp_path —
    never into site/. Returns the rendered HTML string."""
    snap = _synthetic_snap()
    monkeypatch.setattr(bi.ir, "radar_snapshot", lambda **kw: snap)
    monkeypatch.setattr(bi, "_risk_score_from_spvector", lambda: None)
    monkeypatch.setattr(bi, "_lockup_vm", lambda: {"rows": [], "summary": {}, "raw": []})
    monkeypatch.setattr(bi, "_hk_vm", lambda: {"available": False})
    monkeypatch.setattr(bi, "_chart_aftermarket", lambda: None)
    monkeypatch.setattr("collectors.ipo_calendar.fetch_ipo_calendar", lambda: None)
    monkeypatch.setattr(bi.config, "data_dir", lambda: tmp_path)

    captured = {}

    def _fake_write_page(path, html, **kw):
        out = tmp_path / "ipo.html"
        out.write_text(html)
        captured["html"] = html
        return out

    monkeypatch.setattr(bi, "write_page", _fake_write_page)
    bi.build()
    return captured["html"]


def test_ipo_full_render_has_no_non_finite_sentinel(monkeypatch, tmp_path):
    """Render the FULL ipo.html.j2 page with every non-finite shape planted in the
    recent-listings and upcoming-deals rows, then scan just the numeric table/card
    cells (offer price, size, range) for a leaked nan/inf sentinel."""
    html = _render_ipo_html(monkeypatch, tmp_path)
    assert html.strip().startswith("<!DOCTYPE") or html.strip().startswith("<!doctype")

    # scope the assertion to the numeric cells, not the whole page (the disclaimer
    # prose legitimately contains "infrastructure"-shaped words elsewhere on the site,
    # and this page's own copy uses words like "informs"/"finalized" nearby)
    for tkr in ("NANX", "NAX2", "NAT1", "INFX", "NONX", "ZERX", "REAL"):
        # pull the row's <tr>...</tr> for the recent-listings table
        m = re.search(rf"<b[^>]*>{tkr}</b>.*?</tr>", html, re.DOTALL)
        assert m, f"row for {tkr} not found in rendered recent-listings table"
        _finite_sentinel_free(m.group(0))

    for tkr in ("RBOTH", "RLOWO", "RHIGO", "RFULL", "RNONE", "RZERO", "RINF", "RPDNA"):
        m = re.search(rf'<div class="d-tkr">{tkr}.*?</div>\s*</div>', html, re.DOTALL)
        assert m, f"card for {tkr} not found in rendered upcoming-deals grid"
        _finite_sentinel_free(m.group(0))


def test_ipo_range_never_fabricates_missing_side(monkeypatch, tmp_path):
    """Both bounds missing -> the house em-dash null. Exactly one bound known -> the
    ONE real bound is shown honestly, never a fabricated/estimated other side."""
    html = _render_ipo_html(monkeypatch, tmp_path)

    def _range_text(tkr):
        # the "k" label span wraps the bilingual t() macro output
        # (<span class="l-en">Range</span><span class="l-zh">...</span>), so match
        # loosely on "Range" appearing anywhere inside the k-span
        m = re.search(
            rf'<div class="d-tkr">{tkr}.*?<span class="k">[^<]*<span class="l-en">Range</span>'
            rf'.*?<span class="v">(.*?)</span>',
            html, re.DOTALL)
        assert m, f"Range row for {tkr} not found"
        return m.group(1)

    assert _range_text("RBOTH") == "—"                 # both missing -> null
    assert _range_text("RLOWO") == "$18"                # only low known -> honest single bound
    assert "–" not in _range_text("RLOWO")              # never fabricate the high side
    assert _range_text("RHIGO") == "$22"                # only high known -> honest single bound
    assert "–" not in _range_text("RHIGO")
    assert _range_text("RFULL") == "$14–16"             # complete range renders both sides
    assert _range_text("RNONE") == "—"
    assert _range_text("RINF") == "—"                   # +-inf both sides -> null, not a range
    assert _range_text("RPDNA") == "—"


def test_ipo_zero_survives_as_real_value_not_null(monkeypatch, tmp_path):
    """A legitimate 0 (offer price / size / range bound) must render as a real zero,
    never silently promoted to the missing-data em-dash."""
    html = _render_ipo_html(monkeypatch, tmp_path)

    m = re.search(r"<b[^>]*>ZERX</b>.*?</tr>", html, re.DOTALL)
    assert m
    row_html = m.group(0)
    assert "$0.00" in row_html          # offer_price=0 -> real "$0.00", not "—"
    assert "$0" in row_html             # size_usd=0 -> real "$0"

    m = re.search(r'<div class="d-tkr">RZERO.*?</div>\s*</div>', html, re.DOTALL)
    assert m
    card_html = m.group(0)
    assert "$0" in card_html            # size_usd=0 on the upcoming card -> real "$0"
    # range: low=0.0, high=5.0 -> "$0–5" (0 is a real bound, not the em-dash)
    rng = re.search(
        r'<span class="k">[^<]*<span class="l-en">Range</span>.*?<span class="v">(.*?)</span>',
        card_html, re.DOTALL)
    assert rng and rng.group(1) == "$0–5"
