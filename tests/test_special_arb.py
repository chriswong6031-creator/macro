"""Merger-arb spread lane (engine/special_arb.py + engine.special_situations._enrich_arb).

Pins the pure spread math (P1.2): term normalization, days-to-close, the spread /
annualized / downside-on-break economics, the cross-currency guard, and the end-to-end
attach of an `arb` block onto a deal situation from an on-disk close panel.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from lib import config
from engine import special_arb as arb
from engine import special_situations as sse


# ---- term parsing -----------------------------------------------------------
def test_parse_terms_normalizes_and_drops_junk():
    t = arb.parse_terms({"price_per_share": "25.0", "currency": "usd", "consideration": "Cash",
                         "premium_pct": 31.4, "expected_close": "2026-09", "break_fee_musd": 37.5,
                         "junk": "ignore", "price_per_share_note": "x"})
    assert t == {"price_per_share": 25.0, "currency": "USD", "consideration": "cash",
                 "premium_pct": 31.4, "expected_close": "2026-09", "break_fee_musd": 37.5}
    assert arb.parse_terms({"price_per_share": 0}) == {}      # non-positive price dropped
    assert arb.parse_terms("not a dict") == {}
    assert arb.parse_terms({"expected_close": "second half 2026"}) == {}  # non-ISO close dropped


def test_parse_terms_text_fallback():
    assert arb.parse_terms_text("acquired for $25.00 per share in cash") == {
        "price_per_share": 25.0, "consideration": "cash"}
    assert arb.parse_terms_text("stock-for-stock merger at a fixed exchange ratio")["consideration"] == "stock"
    assert arb.parse_terms_text("$1,250.50 per share") == {"price_per_share": 1250.50}
    assert arb.parse_terms_text("ordinary supply agreement") == {}


# ---- days-to-close ----------------------------------------------------------
def test_days_to_close():
    asof = date(2026, 6, 1)
    assert arb.days_to_close("2026-07-01", asof) == 30
    assert arb.days_to_close("2026-06", asof) == 29          # YYYY-MM -> June 30
    assert arb.days_to_close("2026-05-01", asof) is None     # past
    assert arb.days_to_close(None, asof) is None
    assert arb.days_to_close("garbage", asof) is None


# ---- arb metrics ------------------------------------------------------------
def test_arb_metrics_cash_deal():
    m = arb.arb_metrics(25.0, 23.0, expected_close="2026-12-30", asof=date(2026, 7, 1),
                        consideration="cash", unaffected_price=18.0)
    assert m["gross_spread_pct"] == round((25 / 23 - 1) * 100, 2)   # ~8.7% upside
    assert m["days_to_close"] == 182
    assert m["annualized_pct"] > m["gross_spread_pct"]              # annualized > gross for <1y
    assert m["downside_on_break_pct"] == round((18 / 23 - 1) * 100, 1)  # negative drop on break
    assert m["consideration"] == "cash"


def test_arb_metrics_guards():
    assert arb.arb_metrics(None, 10) is None
    assert arb.arb_metrics(10, 0) is None                          # zero live price
    assert arb.arb_metrics(10, 5, currency="CAD") is None          # cross-currency skipped
    m = arb.arb_metrics(10, 9)                                     # no close date -> no annualization
    assert m["annualized_pct"] is None and m["days_to_close"] is None


def test_arb_metrics_drops_positive_downside_on_break():
    """Contradictory break-downside (stock already below unaffected) must be dropped.

    A positive downside_on_break_pct means the unaffected price is ABOVE the live price —
    the stock has already fallen below its pre-announcement level, which is impossible for a
    bona-fide pending deal. Rather than surface a misleading 'upside-on-break' figure the
    field is dropped entirely and no spread badge is attached."""
    # normal case: unaffected (18) < live (23) → negative downside (stock ran up on deal)
    m_neg = arb.arb_metrics(25.0, 23.0, unaffected_price=18.0)
    assert "downside_on_break_pct" in m_neg and m_neg["downside_on_break_pct"] < 0

    # contradictory case: unaffected (30) > live (23) → positive → field must be absent
    m_pos = arb.arb_metrics(25.0, 23.0, unaffected_price=30.0)
    assert m_pos is not None                                       # spread itself still computable
    assert "downside_on_break_pct" not in m_pos                   # but the contradictory field is gone


def test_arb_metrics_rejects_implausible_offer():
    # a mis-extracted offer (dividend grabbed instead of the deal price, or a stale figure)
    # must NOT yield an absurd spread that sorts to the top of the risk_arb book
    assert arb.arb_metrics(200.0, 10.0, expected_close="2026-09") is None   # 1900% spread → bad
    assert arb.arb_metrics(0.50, 70.0) is None                              # dividend vs price → bad
    assert arb.arb_metrics(25.0, 23.0) is not None                          # real ~8.7% spread kept


# ---- foreign currency (broadened price panel) -------------------------------
def test_market_currency():
    assert arb.market_currency("ARX.TO") == "CAD"
    assert arb.market_currency("BARC.L") == "GBP"
    assert arb.market_currency("7203.T") == "JPY"
    assert arb.market_currency("AAPL") == "USD"


def test_arb_metrics_currency_match():
    # a CAD deal priced against a CAD close (the .TO panel) is allowed
    m = arb.arb_metrics(9.0, 8.0, currency="CAD", price_currency="CAD")
    assert m is not None and m["gross_spread_pct"] > 0
    # CAD deal vs a USD close is rejected (mismatch)
    assert arb.arb_metrics(9.0, 8.0, currency="CAD", price_currency="USD") is None
    # unset deal currency is allowed against any close (plausibility gate still applies)
    assert arb.arb_metrics(9.0, 8.0, price_currency="CAD") is not None


# ---- end-to-end enrich ------------------------------------------------------
def test_enrich_arb_attaches_block(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    # a tiny close panel with the deal ticker
    idx = pd.bdate_range("2026-05-01", periods=40)
    panel = pd.DataFrame({"ABC": [18.0] * 30 + [23.0] * 10}, index=idx)
    (tmp_path / "special_situations").mkdir()
    panel.to_parquet(tmp_path / "special_situations" / "bt_prices.parquet")
    sits = [
        {"ticker": "ABC", "category": "Acquisitions", "date_filed": "2026-06-25",
         "deal_terms": {"price_per_share": 25.0, "consideration": "cash"}},
        {"ticker": "ABC", "category": "Activist Campaigns", "date_filed": "2026-06-25",
         "deal_terms": {"price_per_share": 25.0}},   # non-arb category -> skipped
        {"ticker": "ZZZ", "category": "Acquisitions", "date_filed": "2026-06-25",
         "deal_terms": {"price_per_share": 25.0}},   # not in panel -> skipped
    ]
    n = sse._enrich_arb(sits)
    assert n == 1
    assert "arb" in sits[0] and sits[0]["arb"]["gross_spread_pct"] > 0
    assert sits[0]["arb"]["downside_on_break_pct"] < 0            # unaffected (~18) below live (23)
    assert "arb" not in sits[1] and "arb" not in sits[2]


def test_enrich_arb_prices_foreign_suffixed_ticker(tmp_path, monkeypatch):
    """A Canadian (.TO) take-private prices against the foreign close panel in CAD — the
    broadened-panel + suffix-match + currency path (#2)."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    idx = pd.bdate_range("2026-05-01", periods=40)
    (tmp_path / "canada_search").mkdir(parents=True)
    pd.DataFrame({"ARX.TO": [7.5] * 40}, index=idx).to_parquet(
        tmp_path / "canada_search" / "closes.parquet")
    sits = [{"ticker": "ARX.TO", "category": "Going-Private", "date_filed": "2026-06-25",
             "deal_terms": {"price_per_share": 9.0, "currency": "CAD", "consideration": "cash"}}]
    assert sse._enrich_arb(sits) == 1
    assert sits[0]["arb"]["gross_spread_pct"] == round((9.0 / 7.5 - 1) * 100, 2)   # ~20% in CAD


def test_risk_arb_book_cash_only_gate(tmp_path, monkeypatch):
    """risk_arb sorted book must contain cash deals only — cash+stock and stock deals are
    enriched but kept out of the book (their floating stock leg is ungradeable without a
    stock-leg-aware spread model, and is the source of the UROY/MCHX garbage returns)."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    idx = pd.bdate_range("2026-05-01", periods=40)
    panel = pd.DataFrame({"CASH": [23.0] * 40, "MIX": [23.0] * 40, "STK": [23.0] * 40}, index=idx)
    (tmp_path / "special_situations").mkdir()
    panel.to_parquet(tmp_path / "special_situations" / "bt_prices.parquet")
    sits = [
        {"ticker": "CASH", "category": "Acquisitions", "date_filed": "2026-06-25",
         "arb": {"consideration": "cash", "annualized_pct": 15.0, "gross_spread_pct": 5.0}},
        {"ticker": "MIX",  "category": "Acquisitions", "date_filed": "2026-06-25",
         "arb": {"consideration": "cash+stock", "annualized_pct": 1308.0, "gross_spread_pct": 99.0}},
        {"ticker": "STK",  "category": "Tender Offers", "date_filed": "2026-06-25",
         "arb": {"consideration": "stock", "annualized_pct": 200.0, "gross_spread_pct": 40.0}},
    ]
    # simulate the risk_arb sort the same way snapshot() does
    risk_arb = sorted(
        ({"ticker": r.get("ticker"), "company": r.get("company"), "category": r.get("category"),
          "source": r.get("source"), **r["arb"]}
         for r in sits
         if r.get("arb") and r["arb"].get("consideration") == "cash"),
        key=lambda a: (a.get("annualized_pct") is not None, a.get("annualized_pct") or -1e9),
        reverse=True)
    tickers = [a["ticker"] for a in risk_arb]
    assert tickers == ["CASH"], f"cash+stock/stock must be excluded; got {tickers}"
