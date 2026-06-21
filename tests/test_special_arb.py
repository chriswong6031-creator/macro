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
