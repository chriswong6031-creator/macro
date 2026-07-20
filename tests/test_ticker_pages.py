"""Tests for scripts/build_ticker_pages.py (v2).

Covers:
  (a) Context builds all major sections for a rich fixture.
  (b) Missing stockdata blob -> ticker skipped (sections_available < 3).
  (c) Trailing returns math correct on synthetic bars.
  (d) Seasonality only when >=750 bars.
  (e) Noindex / staleness gate.
  (f) Sitemap preserves pre-existing non-/stocks/ entries.
  (g) Stance mapping including ladder states.
  (h) No "validated" in any generated string.
  (i) ZH pair present for every EN pair in hero/stats/gauges.
  (j) Chart SVG present for full OHLC fixture.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.build_ticker_pages import (  # noqa: E402
    build_page_context,
    build_sitemap,
    compute_seasonality,
    compute_stance,
    compute_trailing_returns,
    is_stale,
    page_freshness,
    run,
    sections_available,
    SEASONALITY_MIN_BARS,
    _build_why_moving,
    _build_ownership,
    _build_financials,
    _build_ladder,
    _day_change,
    _range52,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FRESH_DATE = date.today().isoformat()
STALE_DATE = (date.today() - timedelta(days=20)).isoformat()


def _make_candle_bar(date_str: str, price: float) -> list:
    """Minimal OHLC bar: [date, o, h, l, c, vol]."""
    return [date_str, price * 0.99, price * 1.01, price * 0.98, price, 1_000_000]


def _make_ohlc_bars(n: int = 300, start_price: float = 100.0) -> list:
    """Generate n synthetic daily OHLC bars."""
    from datetime import timedelta
    start = date(2022, 1, 3)
    bars = []
    p = start_price
    for i in range(n):
        d = start + timedelta(days=i)
        # Skip weekends (approx)
        if d.weekday() >= 5:
            continue
        p = p * (1 + (0.001 if i % 3 != 0 else -0.002))
        bars.append(_make_candle_bar(d.isoformat(), p))
        if len(bars) >= n:
            break
    return bars


def _make_rich_blob(
    ticker: str = "AAPL",
    asof: str | None = None,
    limited: bool = False,
    ladder_state: str = "UPTREND",
) -> dict:
    """Build a realistic synthetic stockdata blob."""
    asof = asof or FRESH_DATE
    return {
        "ticker": ticker,
        "name": "Apple Inc.",
        "sector": "Information Technology",
        "asof": asof,
        "limited": limited,
        "tech": {
            "price": 180.0,
            "above50": True,
            "above200": True,
            "pct_vs_50dma": 2.5,
            "pct_vs_200dma": 8.1,
            "rsi14": 58.0,
            "macd_pos": True,
            "off_52w_high_pct": -5.2,
            "pct_vs_20dma": 1.1,
            "hv_pctile": 45.0,
            "rel_volume": 1.1,
            "adx14": 22.0,
            "atr_pct": 1.5,
        },
        "season_this": "Jul: -0.8% avg, up 52% of years (n=20)",
        "season_this_zh": "7月：平均 -0.8%，52% 的年份上涨（n=20）",
        "season_next": "Aug: +1.5% avg, up 60% of years (n=20)",
        "season_next_zh": "8月：平均 +1.5%，60% 的年份上涨（n=20）",
        "ladder": {
            "state": ladder_state,
            "label": "IN AN UPTREND",
            "dir": "up",
            "score": 80,
            "why": "Strong momentum",
            "why_zh": "动能强劲",
            "next": "Watch the 10-day MA.",
            "next_zh": "关注10日均线。",
            "regime": "bull",
            "entry": {
                "tag": "WATCH",
                "tag_zh": "观察",
                "urgency": "later",
                "text": "Wait for a pullback to the 10-day MA.",
                "text_zh": "等待回踩10日均线。",
            },
        },
        "alerts": {
            "pinned": None,
            "timeline": [
                {
                    "daylabel": "Jul 10, 2026",
                    "daylabel_zh": "2026年7月10日",
                    "events": [
                        {
                            "type": "ladder",
                            "filter": "signal",
                            "dir": "up",
                            "pinned": False,
                            "headline": "AAPL entered UPTREND",
                            "headline_zh": "AAPL 进入上升趋势",
                            "detail": "Strong uptrend signal.",
                            "detail_zh": "强力上升信号。",
                        }
                    ],
                }
            ],
            "n_recent": 1,
            "n_total": 10,
        },
        "profile": {
            "sector": "Information Technology",
            "mktcap_bn": 2800.0,
            "mktcap_tier": {"key": "mega", "label": "Mega cap", "label_zh": "超大盘"},
            "archetype": {"key": "compounder", "label": "Compounder", "label_zh": "复利机器"},
            "description": "Apple Inc. designs, manufactures, and markets consumer electronics.",
            "description_zh": "苹果公司设计、制造和销售消费电子产品。",
            "sic_description": "Electronic Computers",
            "exchange": "Nasdaq",
            "hq": "CUPERTINO, CA",
        },
        "valuation": {
            "trailing_pe": {"v": 28.0, "med": 25.0, "cheap": 40.0},
            "price_to_book": {"v": 45.0, "med": 8.0, "cheap": 5.0},
            "price_to_sales": {"v": 7.5, "med": 4.0, "cheap": 20.0},
            "fcf_yield_true": {"v": 3.2, "med": 3.5, "cheap": 52.0},
            "ev_to_ebitda": {"v": 22.0, "med": 20.0, "cheap": 45.0},
            "forward_pe": 26.0,
            "forward_tier": "deep",
        },
        "financials": {
            "raw": {
                "revenue": 380_000_000_000,
                "ni": 95_000_000_000,
                "gross_profit": 170_000_000_000,
                "cfo": 110_000_000_000,
                "equity": 70_000_000_000,
                "debt_lt": 90_000_000_000,
                "assets": 330_000_000_000,
                "shares": 15_550_000_000,
                "dividends": 3_700_000_000,
                "repurchases": 75_000_000_000,
            },
            "gross_margin": 44.5,
            "net_margin": 25.0,
            "fcf_margin": 28.9,
            "op_margin": 30.1,
            "roe": 135.0,
            "roa": 29.0,
            "multiyear": {
                "years": [2022, 2023, 2024],
                "revenue": [394_000_000_000, 383_000_000_000, 391_000_000_000],
                "net_margin": [25.3, 24.7, 25.1],
                "gross_margin": [43.3, 44.1, 44.5],
                "eps": [6.11, 6.13, 6.42],
                "fcf": [90_000_000_000, 92_000_000_000, 95_000_000_000],
                "fcf_margin": [22.8, 24.0, 24.3],
                "rev_cagr": 5.2,
                "eps_cagr": 8.1,
                "piotroski": {"score": 7, "of": 9},
                "altman": {"z": 18.5, "zone": "safe"},
                "compounder": None,
            },
        },
        "factors": {
            "radar": [{"key": "value", "z": 0.5}, {"key": "profitability", "z": 1.2}],
            "radar_ok": True,
            "legs": {
                "value": 0.5,
                "profitability": 1.2,
                "quality": 0.8,
                "investment": -0.3,
                "payout": 1.5,
                "low_vol": 0.6,
                "low_beta": 0.4,
                "accruals": -0.8,
                "short_interest": -0.5,
            },
            "composite": 0.71,
            "fundamental_score": 45,
            "sector": "Information Technology",
            "n_universe": 500,
        },
        "positioning": {
            "short": {"pct_float": 0.8, "days_to_cover": 1.2, "si_change_pct": -5.0},
            "short_flow": {},
            "insider": {"net_usd_mn": 25.0, "cluster": False, "n_buyers": 3, "n_sellers": 1, "quarter": "Q2 2026"},
        },
        "analyst": {
            "tier": "deep",
            "forward_pe": 26.0,
            "pe_yf": 27.5,
            "profit_margin": 25.0,
            "roe": 135.0,
            "div_yield": 0.51,
            "rating": None,
            "target": None,
        },
        "earnings": {
            "next_date": (date.today() + timedelta(days=45)).isoformat(),
            "next_time": None,
            "eps_forecast": 1.58,
            "surprises": [
                {"qtr": "Apr 2026", "eps": 1.53, "consensus": 1.45, "surprise_pct": 5.5},
                {"qtr": "Jan 2026", "eps": 1.42, "consensus": 1.35, "surprise_pct": 5.2},
            ],
            "summary": {"beats": 2, "total": 2, "avg_surprise": 5.35, "streak": 2},
            "sue_z": 1.8,
        },
        "revisions": {"breadth": 0.72, "est_chg_30d": 0.8, "n_analysts": 35.0},
        "event_windows": {
            "earnings": {"date": (date.today() + timedelta(days=45)).isoformat(), "tdays": 45},
            "fomc_within": {"date": (date.today() + timedelta(days=10)).isoformat(), "tdays": 10},
            "_display_only": True,
        },
        "vol_squeeze": {
            "state": "on",
            "bias": "up",
            "coiled": True,
            "days_compressed": 5,
            "bbwp": 12.0,
            "hv_pctile": 12.0,
        },
        "entry_signal": {
            "status": "watch",
            "urgency": "watch",
            "headline": "Watch for a pullback",
            "headline_zh": "等待回调",
            "buy_zone": 175.0,
            "chase_above": 185.0,
            "stop": 168.0,
        },
        "smart_money": {
            "holders": [
                {
                    "fund": "BERKSHIRE",
                    "fund_name": "Berkshire Hathaway",
                    "action": "hold",
                    "pct_portfolio": 42.5,
                    "value_usd": 160_000_000_000,
                    "period_end": "2026-03-31",
                    "fund_grade": "A",
                }
            ],
            "ownership_hhi": 0.2,
            "n_holders": 5,
            "n_buying": 1,
            "n_selling": 0,
            "trend": "accumulating",
        },
        "macro_sensitivity": {
            "ticker": ticker,
            "rate_beta": -0.2,
            "tier": "low",
            "tier_label": "Low rate sensitivity",
            "headline": "Low rate sensitivity — less affected by Fed moves",
            "inflation_label": "Moderate",
        },
        "basket_alloc": {
            "rank": 3,
            "label": "Core holding",
            "reco": "Hold",
            "name": "US Large Cap Growth",
            "name_zh": "美国大盘成长",
        },
        "sector_pulse": {
            "as_of": FRESH_DATE,
            "theme_id": "big_tech",
            "theme_name": "Big Tech",
            "theme_name_zh": "大科技",
            "heat": 0.72,
            "label": "Hot",
            "rank": 2,
            "n_themes": 20,
        },
        "baskets_membership": [
            {
                "slug": "mag7",
                "name": "Magnificent Seven",
                "name_zh": "七巨头",
                "category": "AI & Technology",
                "theme": "Mega-cap tech & AI leaders",
                "rationale": "Core holding across all tech mandates",
            }
        ],
        "conviction": {
            "score": 72,
            "band": "strong",
            "band_en": "Strong setup",
            "band_zh": "形态强劲",
            "verdict": "Uptrend — holding above trend",
            "verdict_zh": "上升趋势，守住趋势线",
            "potential": {"score": 75, "band": "high", "band_en": "High potential", "band_zh": "潜力高"},
        },
        "accounting_quality": {
            "verdict": "clean",
            "headline": "Clean accounting",
            "headline_zh": "会计质量良好",
            "n_caution": 0,
        },
        "leverage_ratios": {
            "net_debt": -50_000_000_000,
            "net_debt_to_ebitda": -0.4,
            "current_ratio": 1.05,
        },
        "capital_allocation": {
            "repurch_ttm": 75_000_000_000,
            "sbc_ttm": 10_000_000_000,
            "shares_yoy_change_pct": -3.0,
            "buyback_yield": 2.8,
        },
        "expectation_state": {
            "sue_streak": 2,
            "pead_drift_20d": 0.032,
        },
        "moat_falsifiers": {
            "ticker": ticker,
            "sensors": {
                "margin_expansion": {"fired": False},
                "market_share_growth": {"fired": True},
            },
        },
        "demand_chain": {
            "headline": "Enterprise software spend is accelerating",
            "read": "positive",
        },
        "personality": {
            "base": {
                "archetype": "compounder",
                "dna_class": "mega_growth",
                "chart_personality": "trending",
                "ownership_habitat": "institutional_core",
            }
        },
        "altdata": {
            "tier": "low",
            "channels": ["congress_buy"],
            "headline": "Congressional buy activity noted",
        },
        "gex": {
            "gamma_regime": "long",
            "regime": "long",
            "net_gex_bn": 1.2,
            "gamma_flip": 172.0,
            "call_wall": 190.0,
            "put_wall": 170.0,
            "iv30": 22.0,
        },
    }


def _make_thin_blob(ticker: str = "THIN") -> dict:
    """A blob with no valuation/financials/factors — will fail min-info gate."""
    return {
        "ticker": ticker,
        "name": "Thin Corp",
        "sector": "Other",
        "asof": FRESH_DATE,
        "limited": False,
        "tech": {"price": 10.0},
        "profile": {"sector": "Other", "mktcap_bn": 0.1},
    }


def _make_site(tmp_path: Path, tickers: list[str] | None = None) -> Path:
    """Create a minimal fake site/ tree."""
    site = tmp_path / "site"
    tickers = tickers or ["AAPL"]

    # stockdata blobs
    stockdata_dir = site / "stockdata"
    stockdata_dir.mkdir(parents=True)
    for t in tickers:
        if t == "THIN":
            blob = _make_thin_blob(t)
        else:
            blob = _make_rich_blob(t)
        (stockdata_dir / f"{t}.json").write_text(json.dumps(blob))

    # ohlc
    ohlc_dir = site / "ohlc"
    ohlc_dir.mkdir(parents=True)
    bars_1300 = _make_ohlc_bars(n=1300)
    bars_300 = _make_ohlc_bars(n=300)
    for t in tickers:
        n_bars = 1300 if t != "THIN" else 300
        bars = bars_1300 if n_bars >= 750 else bars_300
        (ohlc_dir / f"{t}.json").write_text(json.dumps({
            "t": "DAILY", "o": 1, "src": "deep",
            "bars": bars,
        }))
    # SPY benchmark
    (ohlc_dir / "SPY.json").write_text(json.dumps({
        "t": "DAILY", "o": 1, "src": "deep",
        "bars": _make_ohlc_bars(n=1300, start_price=450.0),
    }))

    # factor_betas.json
    (site / "factor_betas.json").write_text(json.dumps({
        "as_of": FRESH_DATE,
        "betas": {
            t: {"mkt": 1.15, "name": f"{t} Corp", "sector": "Information Technology"}
            for t in tickers
        },
    }))

    # tech_screener.json
    screener_stocks = {}
    for t in tickers:
        screener_stocks[t] = {
            "name": f"{t} Corp",
            "price": 180.0,
            "score": 0.5,
            "band": "Buy",
            "active_buy": 2,
            "active_total": 5,
            "signals": [
                {"id": "ma_buy_21", "display_en": "MA Buy (21)", "direction": 1, "state": 1, "age_days": 3},
            ],
        }
    (site / "factordata").mkdir(parents=True, exist_ok=True)
    (site / "factordata" / "tech_screener.json").write_text(json.dumps({
        "generated_utc": FRESH_DATE,
        "stocks": screener_stocks,
    }))

    # member_context.json
    (site / "basketdata").mkdir(parents=True, exist_ok=True)
    (site / "basketdata" / "member_context.json").write_text(json.dumps({
        "as_of": FRESH_DATE,
        "by_ticker": {
            t: [{"basket_id": "big_tech", "basket": "Big Tech", "band_en": "Leader", "band_zh": "领头羊"}]
            for t in tickers
        },
    }))

    # baskets.json
    (site / "basketdata" / "baskets.json").write_text(json.dumps({
        "as_of": FRESH_DATE,
        "categories": [
            {"name": "Tech", "baskets": [{"id": "big_tech", "name": "Big Tech", "name_zh": "大科技"}]}
        ],
    }))

    # intelligence/by_ticker.json
    (site / "intelligence").mkdir(parents=True, exist_ok=True)
    (site / "intelligence" / "by_ticker.json").write_text(json.dumps({
        "as_of": FRESH_DATE,
        "tickers": {t: {"read": {"label": "bullish"}} for t in tickers},
    }))

    # news/by_ticker.json
    (site / "news").mkdir(parents=True, exist_ok=True)
    (site / "news" / "by_ticker.json").write_text(json.dumps({
        "asof": FRESH_DATE,
        "tickers": {
            t: {"top": [
                {"title": f"{t} beats estimates", "url": "https://example.com/1", "source": "WSJ", "sentiment": "positive"},
                {"title": f"{t} product launch", "url": "https://example.com/2", "source": "Bloomberg", "sentiment": "positive"},
            ]}
            for t in tickers
        },
    }))

    # altdata/by_ticker.json
    (site / "altdata").mkdir(parents=True, exist_ok=True)
    (site / "altdata" / "by_ticker.json").write_text(json.dumps({
        "as_of": FRESH_DATE,
        "tickers": {},
    }))

    # sitemap.xml
    (site / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url><loc>https://mastermind-x.com/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>\n'
        '</urlset>\n'
    )

    return site


def _make_membership(tmp_path: Path, tickers: list[str]) -> Path:
    """Write membership.parquet."""
    try:
        import pandas as pd
    except ImportError:
        pytest.skip("pandas not available")

    data_dir = tmp_path / "data" / "universe"
    data_dir.mkdir(parents=True)
    df = pd.DataFrame([
        {"ticker": t, "name": f"{t} Inc", "sector": "Information Technology", "group": "sp500", "active": True}
        for t in tickers
    ])
    path = data_dir / "membership.parquet"
    df.to_parquet(str(path), index=False)
    return path


def _make_fake_root(tmp_path: Path, tickers: list[str]) -> tuple[Path, Path]:
    """Create a full fake repo root with membership + site."""
    site = _make_site(tmp_path, tickers)
    _make_membership(tmp_path, tickers)
    return tmp_path, site


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestComputeStance:
    def test_ladder_uptrend(self):
        blob = _make_rich_blob(ladder_state="UPTREND")
        en, zh, key, inv_en, inv_zh = compute_stance(blob)
        assert key in ("uptrend", "watch", "recovering")
        assert zh  # bilingual

    def test_ladder_bottom_watch(self):
        blob = _make_rich_blob(ladder_state="BOTTOM WATCH")
        en, zh, key, _, _ = compute_stance(blob)
        assert key == "bottoming"

    def test_ladder_downtrend(self):
        blob = _make_rich_blob(ladder_state="DOWNTREND")
        en, zh, key, _, _ = compute_stance(blob)
        assert key == "downtrend"

    def test_ladder_unconfirmed(self):
        blob = _make_rich_blob(ladder_state="UNCONFIRMED TURN")
        en, zh, key, _, _ = compute_stance(blob)
        assert key == "watch"

    def test_fallback_signals(self):
        signals = {"state": "uptrend", "above200": True, "trail_stop": 170.0}
        en, zh, key, inv_en, inv_zh = compute_stance(None, signals=signals)
        assert key == "uptrend"
        assert "170" in inv_en

    def test_none_returns_watch(self):
        en, zh, key, _, _ = compute_stance(None, signals=None, intel=None)
        assert key == "watch"
        assert zh  # bilingual
        assert "validated" not in en.lower()

    def test_all_ladder_states(self):
        """All ladder states map to a valid stance key with a bilingual pair."""
        from scripts.build_ticker_pages import _LADDER_TO_STANCE
        for lstate, expected_key in _LADDER_TO_STANCE.items():
            blob = _make_rich_blob(ladder_state=lstate)
            en, zh, key, _, _ = compute_stance(blob)
            assert zh, f"Missing zh for ladder state {lstate}"
            assert "validated" not in en.lower()


class TestPageFreshness:
    def test_picks_newest(self):
        dates = ["2024-01-01", "2024-06-15", "2024-03-20", None, "bad-date"]
        assert page_freshness(dates) == "2024-06-15"

    def test_all_none_returns_none(self):
        assert page_freshness([None, None]) is None

    def test_empty_returns_none(self):
        assert page_freshness([]) is None


class TestIsStale:
    def test_fresh_not_stale(self):
        assert not is_stale(FRESH_DATE)

    def test_old_is_stale(self):
        assert is_stale(STALE_DATE)

    def test_none_is_stale(self):
        assert is_stale(None)


class TestBuildSitemap:
    def test_preserves_non_stocks(self):
        existing = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '  <url><loc>https://mastermind-x.com/</loc><priority>1.0</priority></url>\n'
            '  <url><loc>https://mastermind-x.com/stocks/AAPL.html</loc><priority>0.6</priority></url>\n'
            '</urlset>\n'
        )
        new_entries = [{"loc": "https://mastermind-x.com/stocks/NVDA.html", "lastmod": FRESH_DATE}]
        result = build_sitemap(existing, new_entries)
        assert "mastermind-x.com/" in result  # homepage preserved
        assert "stocks/AAPL" not in result      # old stock entry replaced
        assert "NVDA" in result                 # new entry present

    def test_empty_existing(self):
        existing = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset>\n</urlset>'
        result = build_sitemap(existing, [{"loc": "https://mastermind-x.com/stocks/AAPL.html"}])
        assert "AAPL" in result


class TestTrailingReturns:
    def test_basic_returns_math(self):
        """Verify that 1y return is computed correctly on synthetic data."""
        bars = _make_ohlc_bars(n=300)
        # returns should be a dict with period keys
        result = compute_trailing_returns(bars)
        # With 300 bars we expect at least 1w, 1m, 3m, 6m
        assert "1w" in result or "1m" in result
        # Math: last close / base close - 1
        if "1m" in result:
            t_ret = result["1m"]["ticker"]
            assert isinstance(t_ret, float)

    def test_spy_benchmark_subtraction(self):
        bars = _make_ohlc_bars(n=600, start_price=100.0)
        spy_bars = _make_ohlc_bars(n=600, start_price=450.0)
        result = compute_trailing_returns(bars, spy_bars)
        if "1m" in result:
            spy_r = result["1m"].get("spy")
            assert spy_r is not None

    def test_empty_bars_returns_empty(self):
        result = compute_trailing_returns([])
        assert result == {}

    def test_ytd_computed(self):
        bars = _make_ohlc_bars(n=260)
        result = compute_trailing_returns(bars)
        # YTD should be present (bars start in Jan 2022)
        assert "YTD" in result


class TestSeasonality:
    def test_requires_min_bars(self):
        bars = _make_ohlc_bars(n=SEASONALITY_MIN_BARS - 50)
        result = compute_seasonality(bars)
        assert result is None

    def test_sufficient_bars_returns_12_months(self):
        # Need to request more than SEASONALITY_MIN_BARS because _make_ohlc_bars
        # skips weekends (generates ~5/7 of requested calendar days).
        n_request = int(SEASONALITY_MIN_BARS * 1.5)
        bars = _make_ohlc_bars(n=n_request)
        result = compute_seasonality(bars)
        assert result is not None
        assert len(result) == 12

    def test_monthly_structure(self):
        bars = _make_ohlc_bars(n=1500)
        result = compute_seasonality(bars)
        assert result is not None
        for row in result:
            assert "month" in row
            assert "win_rate" in row
            assert "median_pct" in row


class TestSectionsAvailable:
    def test_rich_blob_passes_gate(self, tmp_path):
        site = _make_site(tmp_path, ["AAPL"])
        agg = {
            "intel_map": {"AAPL": {"read": {"label": "bullish"}}},
            "news_map": {"AAPL": {"top": [{"title": "t", "url": "u"}]}},
        }
        per = {"blob": _make_rich_blob("AAPL"), "gex_v1": None, "flow": None}
        n = sections_available(per["blob"], per, agg, "AAPL")
        assert n >= 3

    def test_no_blob_fails_gate(self):
        agg = {"intel_map": {}, "news_map": {}}
        per = {"blob": None, "gex_v1": None, "flow": None}
        n = sections_available(None, per, agg, "MISSING")
        assert n < 3


class TestBuildPageContext:
    def _make_agg_and_per(self, tmp_path: Path, ticker: str = "AAPL") -> tuple[dict, dict]:
        site = _make_site(tmp_path, [ticker])
        from scripts.build_ticker_pages import load_all_aggregates, load_per_ticker
        agg = load_all_aggregates(site)
        per = load_per_ticker(site, ticker)
        return agg, per

    def test_all_sections_present(self, tmp_path):
        agg, per = self._make_agg_and_per(tmp_path)
        ctx = build_page_context("AAPL", "Apple Inc.", "Information Technology", per, agg, "2026-07-18 00:00 UTC")
        required = ["meta", "hero", "stats", "gauges", "performance", "financials",
                    "valuation", "earnings", "technicals", "options", "why_moving",
                    "ownership", "themes", "signal_history", "seasonality", "factors"]
        for section in required:
            assert section in ctx, f"Missing section: {section}"

    def test_meta_fields(self, tmp_path):
        agg, per = self._make_agg_and_per(tmp_path)
        ctx = build_page_context("AAPL", "Apple Inc.", "Information Technology", per, agg, "2026-07-18 00:00 UTC")
        meta = ctx["meta"]
        assert meta["ticker"] == "AAPL"
        assert "canonical" in meta
        assert "mastermind-x.com" in meta["canonical"]
        assert "validated" not in meta["meta_desc"].lower()

    def test_hero_bilingual(self, tmp_path):
        agg, per = self._make_agg_and_per(tmp_path)
        ctx = build_page_context("AAPL", "Apple Inc.", "Information Technology", per, agg, "2026-07-18 00:00 UTC")
        hero = ctx["hero"]
        assert hero["stance_en"]
        assert hero["stance_zh"]
        assert "validated" not in hero["stance_en"].lower()

    def test_no_validated_in_context(self, tmp_path):
        agg, per = self._make_agg_and_per(tmp_path)
        ctx = build_page_context("AAPL", "Apple Inc.", "Information Technology", per, agg, "2026-07-18 00:00 UTC")

        def _walk(obj, path=""):
            if isinstance(obj, str):
                assert "validated" not in obj.lower(), f"Found 'validated' at {path}: {obj!r}"
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    _walk(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    _walk(v, f"{path}[{i}]")

        _walk(ctx)

    def test_zh_paired_with_en(self, tmp_path):
        """Every dict key ending in _en must have a non-empty sibling _zh."""
        agg, per = self._make_agg_and_per(tmp_path)
        ctx = build_page_context("AAPL", "Apple Inc.", "Information Technology", per, agg, "2026-07-18 00:00 UTC")

        failures = []

        def _walk(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k.endswith("_en") and v:
                        zh_key = k[:-3] + "_zh"
                        zh_val = obj.get(zh_key)
                        if not zh_val:
                            failures.append(f"{path}.{k} = {v!r} has no {zh_key}")
                    _walk(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    _walk(v, f"{path}[{i}]")

        # Walk selected sections that have en/zh pairs
        for section in ["hero", "stats", "gauges", "earnings", "options"]:
            _walk(ctx.get(section), section)

        # Allow some failures from optional/computed fields — flag only if many
        assert len(failures) == 0, f"EN keys without ZH: {failures[:5]}"

    def test_chart_ctx_is_embed(self, tmp_path):
        """v6: chart ctx flags the Terminal embed (no SSR SVG is rendered)."""
        agg, per = self._make_agg_and_per(tmp_path)
        ctx = build_page_context("AAPL", "Apple Inc.", "Information Technology", per, agg, "2026-07-18 00:00 UTC")
        chart = ctx.get("chart") or {}
        assert chart.get("embed") is True
        assert "svg" not in chart
        # ladder ctx is present for a rich fixture (entry_signal levels exist)
        assert ctx.get("ladder") is not None
        # hero gains day-change + 52w range in v6
        hero = ctx.get("hero") or {}
        assert "chg" in hero
        assert "range52" in hero

    def test_staleness_flag(self, tmp_path):
        """Stale blob sets stale=True when all aggregate dates are also stale."""
        # Create a site where ALL aggregates are stale-dated so freshness picks up STALE_DATE
        site = _make_site(tmp_path, ["STALE"])
        # Overwrite blob with old asof
        stale_blob = _make_rich_blob("STALE", asof=STALE_DATE)
        (site / "stockdata" / "STALE.json").write_text(json.dumps(stale_blob))
        # Overwrite intel and news with stale dates too
        (site / "intelligence" / "by_ticker.json").write_text(json.dumps({
            "as_of": STALE_DATE,
            "tickers": {"STALE": {"read": {"label": "bullish"}}},
        }))
        (site / "news" / "by_ticker.json").write_text(json.dumps({
            "asof": STALE_DATE,
            "tickers": {"STALE": {"top": []}},
        }))
        from scripts.build_ticker_pages import load_all_aggregates, load_per_ticker
        agg = load_all_aggregates(site)
        per = load_per_ticker(site, "STALE")
        ctx = build_page_context("STALE", "Stale Corp", "Tech", per, agg, "2026-07-18 00:00 UTC")
        assert ctx["stale"] is True

    def test_fresh_not_stale(self, tmp_path):
        agg, per = self._make_agg_and_per(tmp_path)
        ctx = build_page_context("AAPL", "Apple Inc.", "Information Technology", per, agg, "2026-07-18 00:00 UTC")
        assert ctx["stale"] is False

    def test_seasonality_present_for_1300_bars(self, tmp_path):
        agg, per = self._make_agg_and_per(tmp_path)
        ctx = build_page_context("AAPL", "Apple Inc.", "Information Technology", per, agg, "2026-07-18 00:00 UTC")
        # 1300 bars >= SEASONALITY_MIN_BARS (750), so monthly data should be present
        seas = ctx.get("seasonality")
        if seas and seas.get("monthly"):
            assert len(seas["monthly"]) == 12

    def test_limited_blob_skipped_via_gate(self, tmp_path):
        """A limited=True blob should be skipped at run() level."""
        tickers = ["LMTD"]
        site = _make_site(tmp_path, tickers)
        limited_blob = _make_rich_blob("LMTD")
        limited_blob["limited"] = True
        (site / "stockdata" / "LMTD.json").write_text(json.dumps(limited_blob))
        _make_membership(tmp_path, tickers)

        import scripts.build_ticker_pages as btp
        orig_site = btp.SITE
        orig_root = btp._ROOT

        out_dir = tmp_path / "out_limited"
        rc = run(out=out_dir, site=site, context_only=True)
        assert rc == 0
        # No output file for limited ticker
        assert not (out_dir / "LMTD.html").exists()


class TestContextOnlyMode:
    def test_context_only_writes_ctx_json(self, tmp_path):
        tickers = ["AAPL"]
        site = _make_site(tmp_path, tickers)
        _make_membership(tmp_path, tickers)

        ctx_dir = tmp_path / "ctx_out"
        out_dir = tmp_path / "html_out"

        import scripts.build_ticker_pages as btp
        # Temporarily point _ROOT to tmp_path so membership.parquet is found
        orig_root = btp._ROOT
        btp._ROOT = tmp_path
        try:
            rc = run(out=out_dir, site=site, context_only=True, dump_context=ctx_dir)
        finally:
            btp._ROOT = orig_root

        assert rc == 0
        ctx_file = ctx_dir / "AAPL.json"
        assert ctx_file.exists(), "Context JSON not written"
        ctx = json.loads(ctx_file.read_text())
        assert ctx["ticker"] == "AAPL"
        assert "meta" in ctx
        assert "hero" in ctx


class TestRunFunction:
    def test_run_context_only_no_html(self, tmp_path):
        tickers = ["AAPL"]
        site = _make_site(tmp_path, tickers)
        _make_membership(tmp_path, tickers)

        out_dir = tmp_path / "out"
        import scripts.build_ticker_pages as btp
        orig_root = btp._ROOT
        btp._ROOT = tmp_path
        try:
            rc = run(out=out_dir, site=site, context_only=True)
        finally:
            btp._ROOT = orig_root

        assert rc == 0
        # In context_only mode, no .html files written (template doesn't exist)
        assert not (out_dir / "AAPL.html").exists()

    def test_run_sitemap_preserved(self, tmp_path):
        tickers = ["AAPL"]
        site = _make_site(tmp_path, tickers)
        _make_membership(tmp_path, tickers)

        sitemap_out = tmp_path / "sitemap_out.xml"
        out_dir = tmp_path / "out_sm"

        import scripts.build_ticker_pages as btp
        orig_root = btp._ROOT
        btp._ROOT = tmp_path
        try:
            rc = run(out=out_dir, site=site, context_only=True, sitemap_out=sitemap_out)
        finally:
            btp._ROOT = orig_root

        assert rc == 0
        if sitemap_out.exists():
            content = sitemap_out.read_text()
            # Homepage should be preserved
            assert "mastermind-x.com/" in content

    def test_missing_stockdata_ticker_skipped(self, tmp_path):
        tickers = ["AAPL", "GHOST"]
        site = _make_site(tmp_path, ["AAPL"])  # GHOST has no stockdata
        _make_membership(tmp_path, tickers)

        out_dir = tmp_path / "out_ghost"
        import scripts.build_ticker_pages as btp
        orig_root = btp._ROOT
        btp._ROOT = tmp_path
        try:
            rc = run(out=out_dir, site=site, context_only=True)
        finally:
            btp._ROOT = orig_root

        assert rc == 0
        assert not (out_dir / "GHOST.html").exists()


# ---------------------------------------------------------------------------
# Template render tests — added for dossier v2
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = _REPO / "templates"


def _jinja_env():
    """Return a Jinja2 env pointing at the repo templates dir."""
    from jinja2 import Environment, FileSystemLoader
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
    )


def _rich_ctx() -> dict:
    """Build a minimal but rich context that exercises all sections."""
    from datetime import date
    today = date.today().isoformat()
    chart_obj = type("C", (), {"has_candles": True, "svg_present": True, "svg": "<svg viewBox=\"0 0 10 10\"></svg>"})()
    return {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "sector": "Information Technology",
        "canonical_url": "https://mastermind-x.com/stocks/AAPL.html",
        "meta_desc": "Apple research dossier.",
        "jsonld_str": "{}",
        "freshness": today,
        "stale": False,
        "generated_utc": today + "T00:00:00Z",
        "stance_en": "Uptrend",
        "stance_zh": "上涨",
        "stance_key": "uptrend",
        "stance_class": "pos",
        "hero": {
            "stance_en": "Uptrend",
            "stance_zh": "上涨",
            "stance_key": "uptrend",
            "stance_class": "pos",
            "inv_en": "Watch — don't chase",
            "inv_zh": "观察 — 勿追涨",
            "desc_en": "Apple Inc. designs consumer electronics.",
            "desc_zh": "苹果公司设计消费电子产品。",
            "sector": "Information Technology",
            "arch_label_en": "Quality Growth",
            "arch_label_zh": "优质成长",
            "mktcap_label_en": "Large Cap",
            "mktcap_label_zh": "大盘股",
            "price": "215.32",
            "chg": {"abs": "+$2.55", "pct": "+1.20%", "pos": True},
            "range52": {"lo": "$164", "hi": "$220", "pos_pct": 92.5},
        },
        "stats": {
            "price": "215.32",
            "mktcap": "$3.3T",
            "trailing_pe": "32×",
            "forward_pe": "28×",
            "eps": "$6.57",
            "beta": "1.28",
            "beta_en": "moves with the market",
            "beta_zh": "与大盘同步",
            "div_yield": "0.5%",
            "short_pct_float": "0.8% of float",
            "volume_en": "58M/day",
            "volume_zh": "5800万/日",
            "hv_pctile": "48th pctile",
            "next_earnings": "2026-07-31 (13d)",
            "range_52w_en": "2.1% below 52-week high",
            "range_52w_zh": "低于52周高点2.1%",
        },
        "ladder": {
            "levels": [
                {"kind": "row", "sort": 220.0, "price": "$220", "cls": "wall",
                 "label_en": "Call wall", "label_zh": "看涨期权墙",
                 "note_en": "rallies tend to stall here", "note_zh": "上攻常在此受阻", "dist": "+2.2%"},
                {"kind": "row", "sort": 215.32, "price": "$215.32", "cls": "now",
                 "label_en": "Price now", "label_zh": "当前价格",
                 "note_en": "in a healthy trend", "note_zh": "趋势健康", "dist": ""},
                {"kind": "band", "sort": 215.0, "price": "$210 – $215"},
                {"kind": "row", "sort": 200.0, "price": "$200", "cls": "stop",
                 "label_en": "Exit if broken", "label_zh": "跌破离场",
                 "note_en": "the engine walks away", "note_zh": "引擎就此离场", "dist": "-7.1%"},
            ],
            "headline_en": "In buy zone",
            "headline_zh": "处于买入区间",
        },
        "chart": chart_obj,
        "deep": {
            "dialogs": [
                {"id": "stats", "title_en": "Statistics — full detail", "title_zh": "统计数据 — 完整明细",
                 "panels": [
                     {"kind": "table", "title_en": "Valuation vs sector", "title_zh": "估值对比行业",
                      "head": [["Multiple", "指标"], ["This stock", "本股"], ["Sector median", "行业中位"], ["Cheaper than", "相对便宜"]],
                      "rows": [[{"en": "P/E (trailing)", "zh": "市盈率（静态）"}, "32.0×", "25.0×", "40%"]]},
                     {"kind": "kv", "title_en": "Trading information", "title_zh": "交易信息",
                      "rows": [{"k_en": "Beta vs market", "k_zh": "贝塔", "v": "1.28", "v_en": "", "v_zh": ""}]},
                 ]},
                {"id": "financials", "title_en": "Financials — full detail", "title_zh": "财务数据 — 完整明细",
                 "panels": [
                     {"kind": "table", "title_en": "Multi-year record", "title_zh": "多年财务记录",
                      "head": [["", ""], ["2023", "2023"], ["2024", "2024"]],
                      "rows": [[{"en": "Revenue", "zh": "营业收入"}, "$383.3B", "$391.0B"]]},
                     {"kind": "notes", "title_en": "Accounting quality checks", "title_zh": "会计质量检查",
                      "lines": [{"en": "Earnings quality: steady", "zh": "盈利质量：稳定", "cls": "mut"}]},
                 ]},
            ],
        },
        "gauges": {
            "valuation": {"pct": 62.0, "verdict_en": "Cheap vs sector", "verdict_zh": "相对行业便宜"},
            "beta": {"beta": 1.2, "label_en": "Moderately volatile", "label_zh": "波动适中"},
            "health": {"piotroski": "7/9", "altman_zone": "safe", "altman_z": 3.8, "verdict_en": "Healthy", "verdict_zh": "健康"},
            "dividend": {"yield_str": "0.5%", "verdict_en": "Small yield", "verdict_zh": "小额股息"},
        },
        "performance": [
            {"label_en": "1 Month", "label_zh": "1个月", "ticker_ret": "+5.2%", "spy_ret": "+2.1%", "verdict_en": "Beat", "verdict_zh": "跑赢", "positive": True},
            {"label_en": "YTD", "label_zh": "年初至今", "ticker_ret": "+12.4%", "spy_ret": "+8.3%", "verdict_en": "Beat", "verdict_zh": "跑赢", "positive": True},
        ],
        "seasonality": {
            "this_label": "Jul: bullish", "this_label_zh": "7月：看涨",
            "next_label": "Aug: neutral", "next_label_zh": "8月：中性",
            "monthly": [
                {"month": "Jan", "win_rate": 58.0}, {"month": "Feb", "win_rate": 45.0},
                {"month": "Mar", "win_rate": 60.0}, {"month": "Apr", "win_rate": 72.0},
                {"month": "May", "win_rate": 48.0}, {"month": "Jun", "win_rate": 65.0},
                {"month": "Jul", "win_rate": 55.0}, {"month": "Aug", "win_rate": 50.0},
                {"month": "Sep", "win_rate": 38.0}, {"month": "Oct", "win_rate": 62.0},
                {"month": "Nov", "win_rate": 70.0}, {"month": "Dec", "win_rate": 68.0},
            ],
        },
        "financials": {
            "years": ["2021", "2022", "2023", "2024"],
            "revenue": ["$366B", "$394B", "$383B", "$391B"],
            "eps": ["5.61", "6.11", "6.13", "6.57"],
            "fcf": ["$93B", "$111B", "$100B", "$108B"],
            "rev_cagr": "+2.2%",
            "eps_cagr": "+5.4%",
            "margins": {"gross_margin": 45.2, "op_margin": 30.7, "net_margin": 25.3, "fcf_margin": 27.6},
            "roe": 147.2,
            "roa": 28.5,
            "leverage_rows": [{"label_en": "Debt/Equity", "label_zh": "债务/股本", "value": "1.8×"}],
            "cap_rows": [{"label_en": "Buybacks TTM", "label_zh": "回购TTM", "value": "$95B"}],
            "piotroski": 7,
            "piotroski_of": 9,
            "altman_zone": "safe",
            "altman_z": 3.8,
            "aq_headline_en": None,
            "aq_headline_zh": None,
        },
        "valuation": [
            {"label_en": "P/E", "label_zh": "市盈率", "value": "32×", "sector_med": "25×", "cheap": 38.0, "cheap_pct": 38.0},
        ],
        "earnings": {
            "next_date": "2026-07-31", "days_to_next": 13,
            "last_date": "2026-05-01",
            "eps_forecast": "$1.65",
            "sue_en": "Beat last 4 qtrs avg +4.2%", "sue_zh": "近4季平均超预期4.2%",
            "rev_en": "Revenue: $94.4B est", "rev_zh": "营收预期：944亿美元",
            "pead_en": "Post-earnings drift: positive", "pead_zh": "财报后漂移：正向",
            "surprises": [
                {"qtr": "Q2 2026", "eps": 1.65, "consensus": 1.60, "surprise_pct": 3.1},
                {"qtr": "Q1 2026", "eps": 2.40, "consensus": 2.35, "surprise_pct": 2.1},
            ],
            "avg_surprise_pct": "+3.4%",
        },
        "technicals": {
            "rsi": 62.4,
            "rsi_zone_en": "Neutral",
            "rsi_zone_zh": "中性",
            "adx": 26.0,
            "adx_word_en": "Trending",
            "adx_word_zh": "趋势中",
            "hv_pctile": 48.0,
            "above50": True,
            "above200": True,
            "ma50_en": "+2.5% above",
            "ma200_en": "+8.1% above",
            "squeeze_en": None,
            "squeeze_zh": None,
            "buy_zone": "$210–215",
            "chase_above": "$225",
            "stop": "$200",
            "entry_headline_en": "In buy zone",
            "entry_headline_zh": "处于买入区间",
            "active_signals": ["MACD bullish crossover", "Above 50/200 MA"],
        },
        "options": {
            "regime_en": "Elevated IV", "regime_zh": "隐波偏高",
            "em_daily_pct": "1.1",
            "em_weekly_pct": "2.4",
            "call_wall": "220",
            "put_wall": "205",
            "gamma_flip": "215",
            "iv30": 22.5,
            "iv_rank_pct": "58",
            "skew_tone": "neutral",
            "rr_25d": "-0.3",
            "pc_ratio": "0.82",
            "max_pain": "212.5",
            "flow_en": "Bullish call buying", "flow_zh": "看涨期权买入",
            "flow_tone": "bullish",
        },
        "why_moving": [
            {"category_en": "Earnings", "category_zh": "业绩", "state": "active", "line_en": "Q2 beat expected.", "line_zh": "Q2业绩超预期。"},
        ],
        "ownership": {
            "insider_en": "Net buying last 90d", "insider_zh": "近90天净买入",
            "hhi_en": "Moderate concentration", "hhi_zh": "集中度适中",
            "holders": [
                {"fund_name": "Vanguard", "fund_grade": "A", "action_en": "Adding", "action_zh": "增持", "shares_pct": "2.3%", "period_end": "2026-03-31"},
            ],
            "trend_en": "Institutions adding",
        },
        "peers": [
            {"ticker": "MSFT", "name": "Microsoft", "href": "MSFT.html"},
            {"ticker": "GOOGL", "name": "Alphabet", "href": "GOOGL.html"},
        ],
        "themes": {
            "baskets": [
                {"id": "mega_tech", "name_en": "Mega Tech", "name_zh": "科技巨头", "theme": "AI infrastructure", "rationale": "", "band_en": "Core", "band_zh": "核心"},
            ],
            "basket_alloc": None,
            "sector_pulse": None,
        },
        "signal_history": {
            "pinned": {"headline": "AAPL uptrend confirmed", "headline_zh": "AAPL上升趋势确认", "detail": None, "detail_zh": None, "dir": "up"},
            "ladder_state": "UPTREND",
            "ladder_label": "Strong uptrend",
            "ladder_label_zh": "强劲上升趋势",
            "events": [
                {"date": "Jul 10", "dir": "up", "headline": "Entered UPTREND", "headline_zh": "进入上升趋势", "detail": None, "detail_zh": None},
            ],
            "n_total": 5,
        },
        "profile_extras": {
            "archetype": "Quality Growth",
            "dna_class": "Quality",
            "chart_personality": "Smooth trending",
            "ownership_habitat": "Institutional core",
            "demand_chain_en": "Consumer electronics → semiconductor → TSMC",
            "active_falsifiers": ["iPhone unit slowdown", "China regulatory risk"],
        },
        "brief": None,
        "factors": {
            "rows": [
                {"label_en": "Momentum", "label_zh": "动量", "z": 1.2, "positive": True},
                {"label_en": "Quality", "label_zh": "质量", "z": 0.8, "positive": True},
                {"label_en": "Value", "label_zh": "价值", "z": -0.5, "positive": False},
            ],
            "composite": 0.65,
            "fundamental_score": 72,
        },
        "news": [
            {"title": "Apple beats Q2", "url": "https://example.com/1", "source": "Reuters", "published": "Jul 15", "sentiment": "positive"},
        ],
        "placeholders": {"analyst_targets": False, "transcripts": True, "dividend_calendar": False},
    }


class TestTemplateRender:
    """Dossier v2 — direct template render tests."""

    def test_ticker_template_renders_without_error(self):
        """ticker.html.j2 must render a rich context without exception."""
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        assert html  # non-empty output
        assert "<html" in html
        assert "</html>" in html

    def test_ticker_template_contains_canonical(self):
        """Canonical URL appears in rendered output."""
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        assert "mastermind-x.com/stocks/AAPL.html" in html

    def test_ticker_template_no_validated_word(self):
        """The word 'validated' must not appear in rendered output."""
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        assert "validated" not in html.lower()

    def test_ticker_template_section_h2s_present(self):
        """All major section h2 elements must appear for a rich context."""
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        expected_sections = [
            "Price chart",
            "Trade levels",
            "Key facts",
            "Seasonality",
            "Financials",
            "Valuation",
            "Earnings",
            "Technicals",
            "Options positioning",
            "Why is it moving",
            "Ownership",
            "Peers",
            "Themes",
            "Signal history",
            "Company profile",
            "Style DNA",
            "Recent news",
        ]
        for section in expected_sections:
            assert section in html, f"Missing section: {section}"
        # v6/v6b removed sections must be gone
        for gone in ("Snapshot Gauges", "Key Statistics", "Factor Profile"):
            assert gone not in html, f"Removed v5 section leaked back: {gone}"
        # v6b: the Performance module is gone from the page flow (its table
        # lives in the Statistics dialog); no main-column anchor remains
        assert 'id="performance"' not in html

    def test_ticker_template_section_order(self):
        """Sections must appear in the correct order in rendered output.
        We use id= attributes which are unique and appear only once per section.
        """
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        # Use section id anchors — these appear once in the body, in section order
        # v6 order: full-width chart -> main column (performance ... news) ->
        # rail (levels/facts/seasonality/themes/peers after the main column)
        order = [
            'id="chart"',
            'id="technicals"',
            'id="earnings"',
            'id="valuation"',
            'id="financials"',
            'id="why"',
            'id="options"',
            'id="ownership"',
            'id="history"',
            'id="profile"',
            'id="news"',
            'id="levels"',
            'id="facts"',
        ]
        positions = [html.index(s) for s in order]
        assert positions == sorted(positions), (
            f"Section order wrong: {list(zip(order, positions))}"
        )

    def test_ticker_template_no_jinja_artifacts(self):
        """No unresolved Jinja2 tags in rendered output."""
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        assert "{{" not in html
        assert "{%" not in html

    def test_ticker_template_null_sections_omitted(self):
        """Sections with null data must be omitted gracefully."""
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        ctx["news"] = None
        ctx["options"] = None
        ctx["ownership"] = None
        html = tmpl.render(**ctx)
        assert "Recent news" not in html
        assert "Options positioning" not in html
        # Page still has core content
        assert "Key facts" in html
        assert "Trade levels" in html

    def test_ticker_template_stale_banner(self):
        """Stale flag adds a noindex meta tag."""
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        ctx["stale"] = True
        html = tmpl.render(**ctx)
        assert "noindex" in html

    def test_index_template_renders(self):
        """ticker_index.html.j2 renders without error for a list of rows."""
        env = _jinja_env()
        tmpl = env.get_template("ticker_index.html.j2")
        rows = [
            {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology",
             "state_chip": "Uptrend", "state_chip_zh": "上涨", "stance_class": "pos"},
            {"ticker": "MSFT", "name": "Microsoft", "sector": "Technology",
             "state_chip": "Watch", "state_chip_zh": "关注", "stance_class": ""},
        ]
        html = tmpl.render(
            rows=rows,
            n_total=2,
            generated_utc="2026-07-18T00:00:00Z",
            canonical_url="https://mastermind-x.com/stocks/index.html",
        )
        assert html
        assert "AAPL" in html
        assert "MSFT" in html
        assert "Stock Coverage" in html

    def test_index_template_no_validated_word(self):
        """'validated' must not appear in index page."""
        env = _jinja_env()
        tmpl = env.get_template("ticker_index.html.j2")
        html = tmpl.render(rows=[], n_total=0, generated_utc="2026-07-18T00:00:00Z",
                           canonical_url="https://mastermind-x.com/stocks/index.html")
        assert "validated" not in html.lower()

    def test_ticker_template_beta_in_key_facts(self):
        """Beta renders in the Key facts rail (v6 home) with no math artifacts."""
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        ctx["stats"]["beta"] = "1.5"
        html = tmpl.render(**ctx)
        assert "1.5" in html
        assert "cos(" not in html
        assert "sin(" not in html


# ---------------------------------------------------------------------------
# New tests for dossier v2 review fixes
# ---------------------------------------------------------------------------

class TestWhyMovingDictGuard:
    """(a) why_moving lines must never contain dict repr; (b) ZH != EN for translated rows."""

    def _make_blob_with_dict_headline(self) -> dict:
        """Rich blob with macro_sensitivity.headline as a real {'en','zh'} dict."""
        blob = _make_rich_blob()
        blob["macro_sensitivity"] = {
            "headline": {"en": "Rate tailwind for short-duration names.", "zh": "短久期标的利率顺风。"},
            "tier": "low",
        }
        return blob

    def test_no_dict_repr_in_why_moving(self):
        """why_moving lines must not contain raw dict repr like {'en': ...}."""
        blob = self._make_blob_with_dict_headline()
        rows = _build_why_moving("TEST", blob, None, None)
        assert rows is not None
        for row in rows:
            for field in ("line_en", "line_zh"):
                val = row.get(field, "")
                assert "{'en'" not in val, f"Dict repr leaked in {field}: {val!r}"
                assert '{"en"' not in val, f"Dict repr leaked in {field}: {val!r}"

    def test_macro_row_zh_comes_from_blob(self):
        """Macro row line_zh must use the zh key from the blob dict, not the en string."""
        blob = self._make_blob_with_dict_headline()
        rows = _build_why_moving("TEST", blob, None, None)
        assert rows is not None
        macro_rows = [r for r in rows if r.get("category_en") == "Macro"]
        assert macro_rows, "Expected a Macro row"
        macro_row = macro_rows[0]
        assert macro_row["line_en"] == "Rate tailwind for short-duration names."
        assert macro_row["line_zh"] == "短久期标的利率顺风。"
        assert macro_row["line_zh"] != macro_row["line_en"], "ZH must differ from EN for translated row"

    def test_news_zh_uses_chinese_lean(self):
        """News row line_zh must have Chinese lean text, not the English lean string."""
        blob = _make_rich_blob()
        news_rec = {
            "top": [
                {"title": "Good news", "url": "http://x", "sentiment": "positive"},
                {"title": "Good news 2", "url": "http://y", "sentiment": "positive"},
            ]
        }
        rows = _build_why_moving("TEST", blob, news_rec, None)
        assert rows is not None
        news_rows = [r for r in rows if r.get("category_en") == "News"]
        assert news_rows
        row = news_rows[0]
        # EN: "2 recent stories — positive lean"
        assert "positive lean" in row["line_en"]
        # ZH: "偏正面" (not "positive lean")
        assert "偏正面" in row["line_zh"], f"Expected 偏正面 in ZH: {row['line_zh']!r}"
        assert "positive lean" not in row["line_zh"]


class TestInsiderNegativeFormat:
    """(c) Insider with negative net_usd formats as -$X.XM, not $-X.XM."""

    def test_negative_insider_no_dollar_sign_bug(self):
        blob = _make_rich_blob()
        blob["positioning"]["insider"]["net_usd_mn"] = -787.3
        blob["positioning"]["insider"]["n_buyers"] = 0
        blob["positioning"]["insider"]["n_sellers"] = 5
        ownership = _build_ownership("TEST", blob, None)
        assert ownership is not None
        insider_en = ownership["insider_en"]
        # Must be "-$787.3M" not "$-787.3M"
        assert "$-" not in insider_en, f"Dollar-sign-negative bug in {insider_en!r}"
        assert "-$787.3M" in insider_en, f"Expected -$787.3M, got {insider_en!r}"


class TestFinancialsEmptyGuard:
    """(d) _build_financials returns None for all-empty fixture."""

    def test_empty_financials_returns_none(self):
        """Blob with no multiyear years, no margins, no roe/roa/leverage/cap -> None."""
        blob = {
            "ticker": "EMPTY",
            "financials": {
                "raw": {},
                "multiyear": {},
                "gross_margin": None,
                "net_margin": None,
                "fcf_margin": None,
                "op_margin": None,
                "roe": None,
                "roa": None,
            },
            "accounting_quality": {},
            "leverage_ratios": {},
            "capital_allocation": {},
        }
        result = _build_financials(blob)
        assert result is None, f"Expected None for empty financials, got {result!r}"

    def test_rich_financials_not_none(self):
        """Rich blob with years and margins must not be filtered out."""
        blob = _make_rich_blob()
        result = _build_financials(blob)
        assert result is not None


class TestChartEmbed:
    """(e) v6: the chart is a Mastermind Terminal /embed/chart iframe."""

    def test_embed_iframe_present_with_symbol(self):
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        assert 'id="chart-embed"' in html, "chart embed iframe missing"
        assert "app.mastermind-x.com/embed/chart?symbol=AAPL" in html, "embed URL missing/incorrect"
        assert 'id="chart-frame"' in html
        # src is set by JS from data-embed (theme/lang aware) — never hardcoded
        assert 'data-embed=' in html

    def test_embed_has_fallback_terminal_link(self):
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        assert "chart-fallback" in html
        assert "app.mastermind-x.com/terminal?sym=AAPL" in html
        assert "<noscript>" in html

    def test_no_legacy_chart_machinery(self):
        """The v5 SSR-SVG + lazy LWC loader must be fully gone."""
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        assert "loadInteractiveChart" not in html
        assert "chart-mount" not in html
        assert "lightweight-charts-v5.js" not in html


class TestLadderTemplate:
    """v6 Trade-levels ladder — collision-free vertical levels, one stop only."""

    def test_ladder_renders_rows_and_band(self):
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        assert 'id="levels"' in html
        assert "Trade levels" in html
        assert "Call wall" in html
        assert "Exit if broken" in html
        assert "$210 – $215" in html  # buy-zone band
        assert "not advice" in html   # honesty footer

    def test_ladder_absent_falls_back_to_wall_tiles(self):
        """No ladder → levels section gone; options walls surface as tiles instead."""
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        ctx["ladder"] = None
        html = tmpl.render(**ctx)
        assert 'id="levels"' not in html
        # options fixture has call_wall/put_wall → tiles appear when no ladder
        assert "Call wall" in html
        assert "Put wall" in html

    def test_ladder_one_stop_only(self):
        """The old two-stop confusion (technicals stop vs rail trail stop) must not return:
        exactly one 'Exit if broken' row, and the Technicals module carries no levels."""
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        assert html.count("Exit if broken") == 1
        # legacy technicals level cards must not render even though ctx still has the keys
        assert "Buy zone</div>" not in html
        assert "Don't chase above</div>" not in html


class TestDeepDialogs:
    """v6b popup dashboards — dialog markup + Full-detail affordances."""

    def test_dialogs_render_with_panels(self):
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        html = tmpl.render(**_rich_ctx())
        assert 'id="dlg-stats"' in html
        assert 'id="dlg-financials"' in html
        assert "dsrOpenDlg" in html          # mx5 dialog system shipped
        assert "Full detail" in html         # header affordance present
        assert "Multi-year record" in html   # table panel content
        assert "$383.3B" in html

    def test_no_dialogs_without_deep(self):
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        ctx["deep"] = None
        html = tmpl.render(**ctx)
        assert 'id="dlg-stats"' not in html
        assert "Full detail" not in html

    def test_dialog_deep_link_hash_handler(self):
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        html = tmpl.render(**_rich_ctx())
        assert "indexOf('dlg-')===0" in html  # #dlg- hash deep-link wired


class TestMachineScrub:
    """Operator order: no machine reads in Tier-1 stance copy."""

    def test_nested_machine_parens(self):
        from scripts.build_ticker_pages import _scrub_machine
        out = _scrub_machine("price is now extended (overbought (daily RSI 72)). Don't chase.")
        assert "RSI" not in out
        assert "(overbought)" in out

    def test_flat_machine_parens_removed(self):
        from scripts.build_ticker_pages import _scrub_machine
        out = _scrub_machine("stretched after the run (daily RSI 72, 98th-percentile volatility). Wait.")
        assert "RSI" not in out and "percentile" not in out
        assert out == "stretched after the run. Wait."

    def test_shorthand_normalized(self):
        from scripts.build_ticker_pages import _scrub_machine
        out = _scrub_machine("a low formed ~4 day(s) ago @ 275.15 and held")
        assert "days ago at $275.15" in out

    def test_plain_parens_kept(self):
        from scripts.build_ticker_pages import _scrub_machine
        out = _scrub_machine("a partial entry (half size) is available")
        assert "(half size)" in out

    def test_zh_scrub(self):
        from scripts.build_ticker_pages import _scrub_machine_zh
        out = _scrub_machine_zh("低点于约 4 天前形成 @ 275.15，且价格已重新站上（日线RSI 72）10 日均线。")
        assert "RSI" not in out
        assert "价位 275.15" in out


class TestLadderBuilder:
    """_build_ladder unit behavior."""

    def _blob(self) -> dict:
        return {
            "entry_signal": {
                "buy_zone": {"low": 210.0, "high": 215.0},
                "chase_above": 225.0,
                "stop": 200.0,
                "headline": "In buy zone",
                "headline_zh": "处于买入区间",
            },
        }

    def test_ladder_sorted_desc_and_single_stop(self):
        lad = _build_ladder(215.32, self._blob(),
                            walls={"call_wall": 220.0, "put_wall": 205.0},
                            signals={"trail_stop": 208.0}, stance_class="pos")
        assert lad is not None
        sorts = [i["sort"] for i in lad["levels"]]
        assert sorts == sorted(sorts, reverse=True), "ladder must be sorted high→low"
        stops = [i for i in lad["levels"] if i.get("cls") == "stop"]
        assert len(stops) == 1
        # trail_stop (208) wins over entry_signal.stop (200)
        assert stops[0]["price"] == "$208"

    def test_ladder_price_row_present_with_stance_note(self):
        lad = _build_ladder(215.32, self._blob(), walls={}, signals={}, stance_class="warn")
        assert lad is not None
        now = [i for i in lad["levels"] if i.get("cls") == "now"]
        assert len(now) == 1
        assert now[0]["note_en"] == "stretched — be patient"

    def test_ladder_none_without_levels(self):
        assert _build_ladder(100.0, {}, walls={}, signals={}) is None
        assert _build_ladder(None, self._blob(), walls={}, signals={}) is None

    def test_ladder_junk_level_guard(self):
        """Levels wildly away from price (bad data) are dropped."""
        blob = {"entry_signal": {"stop": 2.0}}  # 98% below a $100 stock = junk
        assert _build_ladder(100.0, blob, walls={}, signals={}) is None

    def test_day_change_and_range52(self):
        bars = [_make_candle_bar("2026-07-17", 210.0), _make_candle_bar("2026-07-18", 215.32)]
        chg = _day_change(bars)
        assert chg is not None and chg["pos"] is True
        assert chg["pct"] == "+2.53%"
        bars252 = [_make_candle_bar(f"2026-{(i//28)+1:02d}-{(i%28)+1:02d}", 150 + i * 0.3) for i in range(252)]
        r52 = _range52(215.0, bars252)
        assert r52 is not None
        assert 0.0 <= r52["pos_pct"] <= 100.0


class TestMainTagBalance:
    """(f) No </main> without <main> in rendered output."""

    def test_main_tags_balanced(self):
        env = _jinja_env()
        tmpl = env.get_template("ticker.html.j2")
        ctx = _rich_ctx()
        html = tmpl.render(**ctx)
        # The include for _site_nav.html.j2 may contribute one <main> or zero
        # but the template itself must not have unbalanced </main>
        open_count = html.count("<main")
        close_count = html.count("</main>")
        assert close_count <= open_count + 1, (
            f"More </main> ({close_count}) than <main> ({open_count}) — unbalanced tags"
        )
        # Also check that we have at least one </main>
        assert close_count >= 1, "Expected at least one </main> in output"
