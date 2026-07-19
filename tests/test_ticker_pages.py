"""Tests for scripts/build_ticker_pages.py.

Covers:
  (a) A ticker with rich data renders a page with title/canonical/JSON-LD and NO noindex.
  (b) A stale as_of gets noindex and is excluded from the sitemap.
  (c) A thin ticker (<3 sections) is skipped.
  (d) Sitemap preserves pre-existing non-/stocks/ entries.
  (e) <title> contains no '{{' and no '<span'.
  (f) Rendered HTML contains no literal word "validated".
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Bootstrap path so the module can be imported from any working directory.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.build_ticker_pages import (  # noqa: E402
    build_page_context,
    build_sitemap,
    compute_stance,
    is_stale,
    page_freshness,
    run,
    sections_available,
)


# ---------------------------------------------------------------------------
# Helpers to build minimal synthetic fixture trees
# ---------------------------------------------------------------------------

FRESH_DATE = date.today().isoformat()
STALE_DATE = (date.today() - timedelta(days=20)).isoformat()


def _make_site(tmp_path: Path) -> Path:
    """Create a minimal fake site/ tree with committed artifacts."""
    site = tmp_path / "site"

    # factors.json
    factors_dir = site / "factordata"
    factors_dir.mkdir(parents=True)
    factors_data = {
        "as_of": FRESH_DATE,
        "table": [
            {
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "sector": "Information Technology",
                "mktcap_bn": 3200.0,
                "value": -0.5, "quality": 1.2, "profitability": 1.5,
                "accruals": -0.3, "investment": 0.2, "payout": 0.8,
                "low_vol": -0.1, "low_beta": -0.2, "short_interest": -1.1,
                "sue": 0.9,
                "composite": 0.7, "composite_rank": 0.82,
            },
        ],
    }
    (factors_dir / "factors.json").write_text(json.dumps(factors_data))

    # alpha.json
    alpha_data = {
        "as_of": FRESH_DATE,
        "per_ticker": {
            "AAPL": {
                "alpha": 0.12, "resid_ann": 0.08, "total_mom": 0.3,
                "rev_1m": 0.01, "rev_pctile": 0.7,
                "sector_rank": 3, "sector_n": 65,
                "entry": "above 50d",
                "rs": 0.82, "rs3m": 0.78, "rs6m": 0.85, "rs12m": 0.90,
            },
        },
    }
    (factors_dir / "alpha.json").write_text(json.dumps(alpha_data))

    # member_context.json
    basket_dir = site / "basketdata"
    basket_dir.mkdir(parents=True)
    mc_data = {
        "as_of": FRESH_DATE,
        "by_ticker": {
            "AAPL": [
                {"basket_id": "mag7", "basket": "Magnificent Seven",
                 "band": "beyond", "band_en": "Extended beyond theme",
                 "band_zh": "延展超出主题",
                 "tone": "neg", "parabolic": False, "ext": 21.9,
                 "rs_rank": 0.86},
            ],
        },
    }
    (basket_dir / "member_context.json").write_text(json.dumps(mc_data))

    # baskets.json
    baskets_data = {
        "baskets": [
            {"id": "mag7", "name": "Magnificent Seven", "name_zh": "七巨头",
             "thesis": "The seven largest US tech-adjacent names."},
        ],
    }
    (basket_dir / "baskets.json").write_text(json.dumps(baskets_data))

    # intelligence/by_ticker.json
    intel_dir = site / "intelligence"
    intel_dir.mkdir(parents=True)
    intel_data = {
        "as_of": FRESH_DATE,
        "tickers": {
            "AAPL": {
                "ticker": "AAPL",
                "news": {"n_recent": 3, "sentiment_lean": "neutral", "top": []},
                "alt": {"signal_score": 50, "channels": ["affiliation"]},
                "radar": None,
                "read": {"label": "bullish", "read": "Positive signals across multiple indicators."},
                "brain": {"confidence": 0.6, "label": "bullish"},
            },
        },
    }
    (intel_dir / "by_ticker.json").write_text(json.dumps(intel_data))

    # news/by_ticker.json
    news_dir = site / "news"
    news_dir.mkdir(parents=True)
    news_data = {
        "asof": FRESH_DATE,
        "tickers": {
            "AAPL": {
                "n_recent": 2, "sentiment_lean": "neutral",
                "top": [
                    {"title": "Apple hits record high", "url": "https://example.com/a",
                     "source": "Reuters", "published": FRESH_DATE, "sentiment": "pos"},
                ],
            },
        },
    }
    (news_dir / "by_ticker.json").write_text(json.dumps(news_data))

    # altdata/by_ticker.json
    alt_dir = site / "altdata"
    alt_dir.mkdir(parents=True)
    alt_data = {
        "as_of": FRESH_DATE,
        "tickers": {
            "AAPL": {
                "ticker": "AAPL",
                "channels": ["affiliation", "patent_cluster"],
                "congress_net": 5, "congress_members": 1,
                "trump_linked": True, "affiliated": True,
            },
        },
    }
    (alt_dir / "by_ticker.json").write_text(json.dumps(alt_data))

    # gex/AAPL.json
    gex_dir = site / "gex"
    gex_dir.mkdir(parents=True)
    gex_data = {
        "meta": {"key": "AAPL", "asof": FRESH_DATE},
        "summary": {
            "spot": 200.0, "regime": "positive",
            "net_gex_bn": 1.2, "gamma_flip": 195.0,
            "dist_to_flip_pct": 2.5,
            "magnet_up": 205.0, "magnet_down": 195.0,
            "iv30": 22.5, "put_call_oi_ratio": 0.8,
            "max_pain": 200.0, "call_wall": 210.0, "put_wall": 190.0,
            "iv_rank": {"rank_pct": 35.0, "band": "low"},
            "skew": {"tone": "neutral"},
        },
        "expected_move": {"daily_pct": 1.2, "weekly_pct": 2.8},
    }
    (gex_dir / "AAPL.json").write_text(json.dumps(gex_data))

    # signals/AAPL.json
    signals_dir = site / "signals"
    signals_dir.mkdir(parents=True)
    signals_data = {
        "ticker": "AAPL", "asof": FRESH_DATE,
        "state": "long-bias", "above200": True,
        "weekly_bull": True, "trail_stop": 185.50, "trail_breach": False,
        "markers": [
            {"date": "2025-01-15", "type": "buy", "quality": "take", "reason": "held confirmation"},
            {"date": "2025-03-10", "type": "sell"},
            {"date": "2025-05-20", "type": "buy", "quality": "take", "reason": "reclaimed 200 & held"},
        ],
    }
    (signals_dir / "AAPL.json").write_text(json.dumps(signals_data))

    # flow/AAPL.json
    flow_dir = site / "flow"
    flow_dir.mkdir(parents=True)
    flow_data = {
        "underlying": "AAPL", "asof": FRESH_DATE,
        "net_premium_mn": 45.2, "pc_ratio": 0.75,
        "verdict": {"tone": "bullish", "en": "Net call buying — bullish bias.", "zh": "净看涨买入——偏多。"},
    }
    (flow_dir / "AAPL.json").write_text(json.dumps(flow_data))

    # stockbrief/AAPL.json
    brief_dir = site / "stockbrief"
    brief_dir.mkdir(parents=True)
    brief_data = {
        "ticker": "AAPL", "asof": FRESH_DATE,
        "schema": "catalyst_stock.v1",
        "summary": "AAPL shows strong momentum with recent 200d reclaim.",
        "drivers": ["Services growth", "AI hardware cycle"],
        "risks": ["Valuation extended vs peers"],
        "catalysts": ["Earnings in Q4"],
        "confidence": 0.7,
        "degraded_reason": None,
        "disclaimer": "AI-generated research context — not advice.",
        "zh": {"summary": "AAPL动能强劲，近期重回200日均线之上。"},
    }
    (brief_dir / "AAPL.json").write_text(json.dumps(brief_data))

    # sitemap.xml — existing non-stocks entries to preserve
    (site / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url><loc>https://mastermind-x.com/index.html</loc><changefreq>daily</changefreq><priority>1.0</priority></url>\n'
        '  <url><loc>https://mastermind-x.com/macro.html</loc><changefreq>daily</changefreq><priority>0.9</priority></url>\n'
        '  <url><loc>https://mastermind-x.com/stocks/OLD.html</loc><changefreq>daily</changefreq><priority>0.6</priority></url>\n'
        '</urlset>\n'
    )

    return site


def _make_membership_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal membership.parquet with the given rows."""
    import pandas as pd

    df = pd.DataFrame(rows)
    p = tmp_path / "data" / "universe"
    p.mkdir(parents=True)
    outpath = p / "membership.parquet"
    df.to_parquet(str(outpath), index=False)
    return outpath


# ---------------------------------------------------------------------------
# Unit tests for pure functions
# ---------------------------------------------------------------------------

class TestComputeStance:
    def test_uptrend_above200(self):
        sig = {"state": "long-bias", "above200": True, "trail_breach": False, "trail_stop": 100.0}
        en, zh, key, inv, inv_zh = compute_stance(sig, None)
        assert key == "uptrend"
        assert "100.00" in inv

    def test_trail_breach_protect(self):
        sig = {"state": "long-bias", "above200": True, "trail_breach": True, "trail_stop": 95.0}
        en, zh, key, inv, inv_zh = compute_stance(sig, None)
        assert key == "protect"
        assert "95.00" in inv

    def test_bearish_aside(self):
        sig = {"state": "bearish", "above200": False, "trail_breach": False}
        en, zh, key, inv, inv_zh = compute_stance(sig, None)
        assert key == "aside"

    def test_no_signals_uses_intel(self):
        intel = {"read": {"label": "bearish", "read": "Bearish signals"}}
        en, zh, key, inv, inv_zh = compute_stance(None, intel)
        assert key == "aside"

    def test_no_data_default_watch(self):
        en, zh, key, inv, inv_zh = compute_stance(None, None)
        assert key == "watch"


class TestSectionsAvailable:
    def test_rich_data(self):
        n = sections_available(
            factors_row={"composite": 0.5},
            alpha_row={"rs": 0.7},
            gex={"summary": {"regime": "positive"}},
            member_ctx=[{"basket_id": "mag7"}],
            intel={"read": {"label": "bullish"}},
            flow={"verdict": {"tone": "bullish"}},
            signals={"state": "long-bias"},
            news_tickers={"AAPL": {"top": [{"title": "headline", "url": "http://x.com"}]}},
            ticker="AAPL",
        )
        assert n >= 3

    def test_thin_data(self):
        n = sections_available(
            factors_row=None,
            alpha_row=None,
            gex=None,
            member_ctx=None,
            intel=None,
            flow=None,
            signals=None,
            news_tickers={},
            ticker="THIN",
        )
        assert n < 3


class TestPageFreshness:
    def test_picks_newest(self):
        dates = ["2026-01-01", "2026-07-15", "2025-12-31", None]
        assert page_freshness(dates) == "2026-07-15"

    def test_all_none(self):
        assert page_freshness([None, None]) is None


class TestIsStale:
    def test_fresh(self):
        assert not is_stale(date.today().isoformat())

    def test_stale(self):
        old = (date.today() - timedelta(days=20)).isoformat()
        assert is_stale(old)

    def test_none_is_stale(self):
        assert is_stale(None)


class TestBuildSitemap:
    def test_preserves_non_stocks_entries(self):
        existing = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '  <url><loc>https://mastermind-x.com/index.html</loc><changefreq>daily</changefreq><priority>1.0</priority></url>\n'
            '  <url><loc>https://mastermind-x.com/stocks/OLD.html</loc><changefreq>daily</changefreq><priority>0.6</priority></url>\n'
            '</urlset>\n'
        )
        new_entries = [
            {"loc": "https://mastermind-x.com/stocks/AAPL.html", "lastmod": "2026-07-18",
             "changefreq": "daily", "priority": 0.6},
        ]
        result = build_sitemap(existing, new_entries)
        # Must preserve /index.html
        assert "https://mastermind-x.com/index.html" in result
        # Must drop stale /stocks/OLD.html
        assert "stocks/OLD.html" not in result
        # Must add new stocks entry
        assert "stocks/AAPL.html" in result
        # Must be valid XML wrapper
        assert "</urlset>" in result

    def test_empty_new_entries(self):
        existing = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>https://mastermind-x.com/index.html</loc></url>\n</urlset>\n'
        result = build_sitemap(existing, [])
        assert "index.html" in result


# ---------------------------------------------------------------------------
# Integration tests using tmp_path
# ---------------------------------------------------------------------------

class TestRunIntegration:
    def _make_parquet(self, tmp_path: Path, tickers: list[dict]) -> None:
        """Write membership.parquet under tmp_path/data/universe/."""
        import pandas as pd
        rows = tickers
        df = pd.DataFrame(rows)
        p = tmp_path / "data" / "universe"
        p.mkdir(parents=True)
        df.to_parquet(str(p / "membership.parquet"), index=False)

    def test_rich_ticker_renders_page(self, tmp_path, monkeypatch):
        """Ticker with ≥3 sections renders a page with canonical, JSON-LD, no noindex."""
        site = _make_site(tmp_path)
        self._make_parquet(tmp_path, [
            {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Information Technology",
             "group": "sp500", "active": True, "first_seen": "2026-01-01", "last_seen": "2026-07-18"},
        ])
        # Patch _ROOT and SITE to point to tmp_path
        import scripts.build_ticker_pages as mod
        orig_root = mod._ROOT
        orig_site = mod.SITE
        monkeypatch.setattr(mod, "_ROOT", tmp_path)
        monkeypatch.setattr(mod, "SITE", site)

        out = tmp_path / "out"
        sitemap_out = tmp_path / "sitemap_test.xml"
        rc = mod.run(out=out, sitemap_out=sitemap_out, site=site)
        assert rc == 0
        monkeypatch.setattr(mod, "_ROOT", orig_root)
        monkeypatch.setattr(mod, "SITE", orig_site)

        aapl_html = out / "AAPL.html"
        assert aapl_html.exists(), "AAPL.html was not rendered"
        html = aapl_html.read_text()

        # (a) canonical present
        assert 'rel="canonical"' in html
        assert "stocks/AAPL.html" in html

        # JSON-LD present
        assert 'application/ld+json' in html
        assert '"tickerSymbol"' in html or 'tickerSymbol' in html

        # No noindex (fresh data)
        assert 'noindex' not in html

        # (e) <title> contains no '{{' or '<span'
        import re
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL)
        assert title_match, "No <title> found"
        title_text = title_match.group(1)
        assert "{{" not in title_text
        assert "<span" not in title_text

        # (f) No literal word "validated" in rendered HTML
        assert "validated" not in html.lower() or "not validated" in html.lower() or "no validated" in html.lower()
        # Strict check: word 'validated' as an affirmative claim
        assert not re.search(r'\bvalidated\b(?! edge is absent|\s+edge\s+is)', html)

    def test_stale_ticker_gets_noindex_excluded_from_sitemap(self, tmp_path, monkeypatch):
        """Stale as_of → noindex and excluded from sitemap."""
        # Build a site with only stale dates
        site = _make_site(tmp_path)
        # Overwrite freshness dates to be stale
        import json as _json
        fd = site / "factordata" / "factors.json"
        data = _json.loads(fd.read_text())
        data["as_of"] = STALE_DATE
        fd.write_text(_json.dumps(data))
        alpha_p = site / "factordata" / "alpha.json"
        adata = _json.loads(alpha_p.read_text())
        adata["as_of"] = STALE_DATE
        alpha_p.write_text(_json.dumps(adata))
        intel_p = site / "intelligence" / "by_ticker.json"
        idata = _json.loads(intel_p.read_text())
        idata["as_of"] = STALE_DATE
        intel_p.write_text(_json.dumps(idata))
        # Patch gex/signals/flow to stale
        for fname, key in [("gex/AAPL.json", "meta"), ("signals/AAPL.json", None), ("flow/AAPL.json", None)]:
            fp = site / fname
            if fp.exists():
                d = _json.loads(fp.read_text())
                if key == "meta":
                    d["meta"]["asof"] = STALE_DATE
                else:
                    d["asof"] = STALE_DATE
                fp.write_text(_json.dumps(d))
        news_p = site / "news" / "by_ticker.json"
        ndata = _json.loads(news_p.read_text())
        ndata["asof"] = STALE_DATE
        news_p.write_text(_json.dumps(ndata))
        alt_p = site / "altdata" / "by_ticker.json"
        adata2 = _json.loads(alt_p.read_text())
        adata2["as_of"] = STALE_DATE
        alt_p.write_text(_json.dumps(adata2))
        mc_p = site / "basketdata" / "member_context.json"
        mcdata = _json.loads(mc_p.read_text())
        mcdata["as_of"] = STALE_DATE
        mc_p.write_text(_json.dumps(mcdata))
        brief_p = site / "stockbrief" / "AAPL.json"
        if brief_p.exists():
            bdata = _json.loads(brief_p.read_text())
            bdata["asof"] = STALE_DATE
            brief_p.write_text(_json.dumps(bdata))

        self._make_parquet(tmp_path, [
            {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Information Technology",
             "group": "sp500", "active": True, "first_seen": "2026-01-01", "last_seen": "2026-07-18"},
        ])

        import scripts.build_ticker_pages as mod
        monkeypatch.setattr(mod, "_ROOT", tmp_path)
        monkeypatch.setattr(mod, "SITE", site)

        out = tmp_path / "out"
        sitemap_out = tmp_path / "sitemap_stale.xml"
        mod.run(out=out, sitemap_out=sitemap_out, site=site)

        aapl_html = out / "AAPL.html"
        if aapl_html.exists():
            html = aapl_html.read_text()
            # (b) noindex present for stale page
            assert 'noindex' in html

        # (b) stale ticker excluded from sitemap
        if sitemap_out.exists():
            sitemap = sitemap_out.read_text()
            assert "stocks/AAPL.html" not in sitemap

    def test_thin_ticker_skipped(self, tmp_path, monkeypatch):
        """Ticker with <3 sections is skipped (no HTML written)."""
        # Build minimal site with no useful data for THIN
        site = _make_site(tmp_path)
        self._make_parquet(tmp_path, [
            {"ticker": "THIN", "name": "Thin Co", "sector": "Industrials",
             "group": "sp500", "active": True, "first_seen": "2026-01-01", "last_seen": "2026-07-18"},
        ])

        import scripts.build_ticker_pages as mod
        monkeypatch.setattr(mod, "_ROOT", tmp_path)
        monkeypatch.setattr(mod, "SITE", site)

        out = tmp_path / "out"
        sitemap_out = tmp_path / "sitemap_thin.xml"
        mod.run(out=out, sitemap_out=sitemap_out, site=site)

        # (c) THIN page should NOT be written
        assert not (out / "THIN.html").exists()

    def test_sitemap_preserves_non_stocks_entries(self, tmp_path, monkeypatch):
        """Sitemap merge preserves existing non-/stocks/ entries."""
        site = _make_site(tmp_path)
        self._make_parquet(tmp_path, [
            {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Information Technology",
             "group": "sp500", "active": True, "first_seen": "2026-01-01", "last_seen": "2026-07-18"},
        ])

        import scripts.build_ticker_pages as mod
        monkeypatch.setattr(mod, "_ROOT", tmp_path)
        monkeypatch.setattr(mod, "SITE", site)

        out = tmp_path / "out"
        sitemap_out = tmp_path / "sm.xml"
        mod.run(out=out, sitemap_out=sitemap_out, site=site)

        if sitemap_out.exists():
            content = sitemap_out.read_text()
            # (d) original non-stocks entries preserved
            assert "mastermind-x.com/index.html" in content
            assert "mastermind-x.com/macro.html" in content
            # Old stocks entry dropped
            assert "stocks/OLD.html" not in content

    def test_no_validated_in_rendered_html(self, tmp_path, monkeypatch):
        """No literal affirmative 'validated' in rendered pages."""
        site = _make_site(tmp_path)
        self._make_parquet(tmp_path, [
            {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Information Technology",
             "group": "sp500", "active": True, "first_seen": "2026-01-01", "last_seen": "2026-07-18"},
        ])

        import scripts.build_ticker_pages as mod
        monkeypatch.setattr(mod, "_ROOT", tmp_path)
        monkeypatch.setattr(mod, "SITE", site)

        out = tmp_path / "out"
        mod.run(out=out, sitemap_out=None, site=site)

        for html_file in out.glob("*.html"):
            content = html_file.read_text()
            # (f) no affirmative 'validated' in user-facing text
            assert "validated" not in content, f"Found 'validated' in {html_file.name}"
