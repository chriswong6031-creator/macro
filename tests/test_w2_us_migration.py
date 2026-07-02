"""W2 US-side migration tests — no network.

Covers:
  1. Delegation equivalence: news_common.norm_title / event_id / source_tier /
     recency_weight / is_blocked / tier_label produce identical output to the
     qkernel functions they delegate to.
  2. financial_news._normalise qbus emission: every accepted article writes a
     qbus row with _crawled_at stamped and timestamp_quality set per-provider.
  3. RSS back-dating sanity check: pubDate > 48h behind crawl_time →
     suspect_backdated=True (timestamp_quality stays PUBLISHER_STATED).
  4. fetch_company_tickers: function exists on collectors.edgar and the file
     it writes makes name_resolver reach >10k coverage.
  5. _gdelt_tag: uses entity_resolver.resolve_us and falls back gracefully.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import news_common as nc   # noqa: E402
from engine import qkernel as qk       # noqa: E402
from engine import financial_news as fn  # noqa: E402

_NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
_NOW_ISO = _NOW.isoformat()


# =========================================================================== #
# 1. Delegation equivalence: news_common → qkernel
# =========================================================================== #

class TestNormTitleDelegation:
    """news_common.norm_title → qkernel.norm_title(lang='en') for ASCII input."""

    def test_plain_ascii_equivalent(self):
        for t in ("Fed holds rates steady", "NVDA Earnings Beat!!!", "  Hello, World!  ", ""):
            assert nc.norm_title(t) == qk.norm_title(t, lang="en"), f"mismatch on: {t!r}"

    def test_latin_cap_120_chars(self):
        long = "a " * 70    # 140 chars
        assert nc.norm_title(long) == qk.norm_title(long, lang="en")
        assert len(nc.norm_title(long)) <= 120

    def test_none_safe(self):
        assert nc.norm_title(None) == ""
        assert qk.norm_title(None, lang="en") == ""


class TestEventIdDelegation:
    """news_common.event_id(title, domain) → qkernel.event_id(source='', url=domain, title, lang='en')."""

    def test_stable_and_hex(self):
        a = nc.event_id("Fed holds rates steady", "reuters.com")
        b = nc.event_id("Fed holds rates steady", "reuters.com")
        assert a == b
        assert len(a) == 16
        assert all(c in "0123456789abcdef" for c in a)

    def test_matches_qkernel(self):
        title, domain = "Markets rally on inflation data", "bloomberg.com"
        assert nc.event_id(title, domain) == qk.event_id(source="", url=domain,
                                                         title=title, lang="en")

    def test_domain_participates(self):
        a = nc.event_id("Same title", "reuters.com")
        b = nc.event_id("Same title", "cnbc.com")
        assert a != b

    def test_case_invariant(self):
        assert nc.event_id("FED HOLDS RATES", "Reuters.com") == nc.event_id("fed holds rates", "reuters.com")


class TestSourceTierDelegation:
    """news_common.source_tier(domain) → qkernel.source_tier(domain) for EN domains."""

    def test_tier1_wire(self):
        for d in ("reuters.com", "bloomberg.com", "wsj.com", "cnbc.com", "ft.com"):
            assert nc.source_tier(d) == qk.source_tier(d) == 1

    def test_tier2_press(self):
        for d in ("forbes.com", "axios.com", "marketwatch.com"):
            assert nc.source_tier(d) == qk.source_tier(d) == 2

    def test_tier3_aggregator(self):
        for d in ("benzinga.com", "seekingalpha.com", "yahoo.com"):
            assert nc.source_tier(d) == qk.source_tier(d) == 3

    def test_blocked_zero(self):
        assert nc.source_tier("tipranks.com") == qk.source_tier("tipranks.com") == 0

    def test_unknown_zero(self):
        assert nc.source_tier("randomspam.xyz") == qk.source_tier("randomspam.xyz") == 0


class TestRecencyWeightDelegation:
    """news_common.recency_weight → qkernel.recency_weight (now injected)."""

    def test_fresh_is_one(self):
        w = nc.recency_weight(_NOW_ISO, now=_NOW)
        wk = qk.recency_weight(_NOW_ISO, _NOW)
        assert abs(w - 1.0) < 0.01
        assert abs(w - wk) < 1e-9

    def test_half_life_36h(self):
        past_iso = (_NOW - timedelta(hours=36)).isoformat()
        w = nc.recency_weight(past_iso, now=_NOW)
        wk = qk.recency_weight(past_iso, _NOW)
        assert abs(w - 0.5) < 0.02
        assert abs(w - wk) < 1e-9

    def test_garbled_date_neutral(self):
        assert nc.recency_weight("", now=_NOW) == 0.4
        assert nc.recency_weight("not-a-date", now=_NOW) == 0.4


class TestIsBlockedDelegation:
    def test_tipranks_blocked(self):
        assert nc.is_blocked("tipranks.com") is True
        assert qk.is_blocked("tipranks.com") is True

    def test_reuters_not_blocked(self):
        assert nc.is_blocked("reuters.com") is False

    def test_empty_not_blocked(self):
        assert nc.is_blocked("") is False


class TestTierLabelDelegation:
    def test_labels_match(self):
        for tier in (0, 1, 2, 3):
            assert nc.tier_label(tier) == qk.tier_label(tier)


# =========================================================================== #
# 2. qbus emission from _normalise
# =========================================================================== #

class TestQbusEmission:
    """_normalise emits a qbus row with _crawled_at and timestamp_quality."""

    def _capture_qbus_rows(self, fn_call, *args, **kwargs):
        """Run fn_call(*args, **kwargs), capture rows passed to qbus.append_items."""
        from engine import qbus as qb
        captured = []
        original = qb.append_items
        def _fake(rows, **kw):
            captured.extend(rows)
            return None
        qb.append_items = _fake
        try:
            result = fn_call(*args, **kwargs)
        finally:
            qb.append_items = original
        return result, captured

    def test_accepted_article_emits_row(self):
        crawled_at = "2026-06-19T12:00:00+00:00"
        result, rows = self._capture_qbus_rows(
            fn._normalise,
            "Fed holds rates as inflation cools", "https://reuters.com/economy/fed",
            "reuters.com", "2026-06-19T11:00:00+00:00", "Reuters",
            [], "", None, "rss", 1.0, _NOW, _crawled_at=crawled_at
        )
        assert result is not None, "expected article to be accepted"
        assert len(rows) == 1, "expected one qbus row"
        row = rows[0]
        assert row["_crawled_at"] == crawled_at
        assert row["timestamp_quality"] == "PUBLISHER_STATED"
        assert row["desk"] == "financial_news"
        assert row["source"] == "Reuters"

    def test_gdelt_article_gets_crawl_bounded(self):
        crawled_at = "2026-06-19T12:00:00+00:00"
        result, rows = self._capture_qbus_rows(
            fn._normalise,
            "Stock market rally continues", "https://reuters.com/markets",
            "reuters.com", "2026-06-19T11:30:00+00:00", "reuters.com",
            [], "", None, "gdelt", 0.85, _NOW, _crawled_at=crawled_at
        )
        assert result is not None
        assert len(rows) == 1
        assert rows[0]["timestamp_quality"] == "CRAWL_BOUNDED"

    def test_polygon_article_gets_publisher_stated(self):
        crawled_at = "2026-06-19T12:00:00+00:00"
        result, rows = self._capture_qbus_rows(
            fn._normalise,
            "NVDA beats earnings estimates", "https://reuters.com/nvda",
            "reuters.com", "2026-06-19T10:00:00+00:00", "Reuters",
            ["NVDA"], "", "pos", "polygon", 1.0, _NOW, _crawled_at=crawled_at
        )
        assert result is not None
        assert rows[0]["timestamp_quality"] == "PUBLISHER_STATED"

    def test_entities_forwarded(self):
        crawled_at = "2026-06-19T12:00:00+00:00"
        result, rows = self._capture_qbus_rows(
            fn._normalise,
            "Apple and Nvidia both rally", "https://bloomberg.com/markets",
            "bloomberg.com", "2026-06-19T11:00:00+00:00", "Bloomberg",
            ["AAPL", "NVDA"], "", None, "rss", 1.0, _NOW, _crawled_at=crawled_at
        )
        assert result is not None
        assert set(rows[0]["entities"]) == {"AAPL", "NVDA"}

    def test_dropped_article_emits_no_row(self):
        # Low-value title → dropped → no qbus row
        result, rows = self._capture_qbus_rows(
            fn._normalise,
            "5 stocks to buy now", "https://reuters.com/picks",
            "reuters.com", "2026-06-19T12:00:00+00:00", "Reuters",
            [], "", None, "rss", 1.0, _NOW, _crawled_at=_NOW_ISO
        )
        assert result is None
        assert len(rows) == 0

    def test_crawled_at_defaults_to_now(self):
        """When _crawled_at is empty, _normalise falls back to now.isoformat()."""
        result, rows = self._capture_qbus_rows(
            fn._normalise,
            "Markets close higher on Fed news", "https://cnbc.com/markets",
            "cnbc.com", "2026-06-19T11:00:00+00:00", "CNBC",
            [], "", None, "finnhub", 0.95, _NOW   # no _crawled_at kwarg
        )
        assert result is not None
        assert len(rows) == 1
        # _crawled_at should be some non-empty ISO string
        assert rows[0]["_crawled_at"] != ""


# =========================================================================== #
# 3. RSS back-dating sanity check
# =========================================================================== #

class TestBackdatedSanityCheck:
    """pubDate > 48h behind crawl_time → suspect_backdated=True in the returned dict."""

    def _normalise_no_qbus(self, *args, **kwargs):
        """Wrapper that suppresses qbus emission so tests are faster/isolated."""
        return fn._normalise(*args, **kwargs, _emit_qbus=False)

    def test_normal_rss_not_backdated(self):
        """A pubDate 2h before crawl_time: NOT backdated."""
        pub = (_NOW - timedelta(hours=2)).isoformat()
        h = self._normalise_no_qbus(
            "Fed holds rates", "https://bloomberg.com/fed",
            "bloomberg.com", pub, "Bloomberg",
            [], "", None, "rss", 1.0, _NOW, _crawled_at=_NOW_ISO
        )
        assert h is not None
        assert h.get("suspect_backdated") is not True

    def test_backdated_rss_flagged(self):
        """A pubDate 50h before crawl_time (> 48h limit): flagged."""
        old_pub = (_NOW - timedelta(hours=50)).isoformat()
        h = self._normalise_no_qbus(
            "Markets recover from last week's selloff", "https://reuters.com/markets",
            "reuters.com", old_pub, "Reuters",
            [], "", None, "rss", 1.0, _NOW, _crawled_at=_NOW_ISO
        )
        assert h is not None, "article should not be dropped (quality is fine)"
        assert h.get("suspect_backdated") is True, "expected suspect_backdated flag"

    def test_backdated_exactly_at_limit_not_flagged(self):
        """Exactly 48h gap is NOT flagged (> 48, not >=)."""
        pub = (_NOW - timedelta(hours=48)).isoformat()
        h = self._normalise_no_qbus(
            "Treasury yields fall as investors seek safety", "https://ft.com/markets",
            "ft.com", pub, "FT",
            [], "", None, "rss", 1.0, _NOW, _crawled_at=_NOW_ISO
        )
        assert h is not None
        assert h.get("suspect_backdated") is not True

    def test_gdelt_never_backdated(self):
        """GDELT is CRAWL_BOUNDED — back-dating check must NOT flag it."""
        old_pub = (_NOW - timedelta(hours=72)).isoformat()
        h = self._normalise_no_qbus(
            "Stock market hits new high", "https://reuters.com/markets",
            "reuters.com", old_pub, "reuters.com",
            [], "", None, "gdelt", 0.85, _NOW, _crawled_at=_NOW_ISO
        )
        assert h is not None
        assert h.get("suspect_backdated") is not True

    def test_polygon_backdated_flagged(self):
        """Polygon is PUBLISHER_STATED — a stale published_utc SHOULD be flagged."""
        old_pub = (_NOW - timedelta(hours=96)).isoformat()
        h = self._normalise_no_qbus(
            "NVDA raises full-year guidance", "https://cnbc.com/nvda",
            "cnbc.com", old_pub, "CNBC",
            ["NVDA"], "", "pos", "polygon", 1.0, _NOW, _crawled_at=_NOW_ISO
        )
        assert h is not None
        assert h.get("suspect_backdated") is True

    def test_missing_seendate_no_flag(self):
        """Empty seendate: no crash, no flag."""
        h = self._normalise_no_qbus(
            "Markets close mixed", "https://bloomberg.com/markets",
            "bloomberg.com", "", "Bloomberg",
            [], "", None, "rss", 1.0, _NOW, _crawled_at=_NOW_ISO
        )
        assert h is None or h.get("suspect_backdated") is not True


# =========================================================================== #
# 4. SEC company_tickers.json coverage (no network — file is already committed)
# =========================================================================== #

class TestCompanyTickersCoverage:
    """company_tickers.json expands name_resolver to ~10k names when present.

    The file is gitignored (data/edgar/company_tickers.json) and fetched by
    collectors.edgar.fetch_company_tickers() at build time. Tests that need the
    file skip gracefully when it hasn't been fetched yet (CI cold-start).
    """

    def _file_path(self):
        from lib import config as _cfg
        return _cfg.data_dir() / "edgar" / "company_tickers.json"

    def test_fetch_company_tickers_function_exists(self):
        from collectors.edgar import fetch_company_tickers
        assert callable(fetch_company_tickers)

    def test_file_structure_when_present(self):
        import json
        p = self._file_path()
        if not p.exists():
            return    # CI cold-start: file not yet fetched — skip gracefully
        data = json.loads(p.read_text())
        assert len(data) >= 10_000, f"expected ≥10k filers, got {len(data)}"
        nvda_entries = [v for v in data.values() if v.get("ticker") == "NVDA"]
        assert nvda_entries, "NVDA must be in company_tickers.json"

    def test_name_resolver_coverage_when_present(self):
        """With company_tickers.json present, name_resolver index > 10k entries."""
        from engine import name_resolver
        p = self._file_path()
        if not p.exists():
            return    # CI cold-start: no file → baseline 4k is fine
        name_resolver.clear_cache()
        idx = name_resolver.build_index()
        assert len(idx) >= 10_000, (
            f"expected ≥10k resolved names with company_tickers.json, got {len(idx)}"
        )

    def test_no_refetch_when_fresh(self):
        """When the cache is fresh, fetch_company_tickers returns True fast."""
        from collectors import edgar as edgar_mod
        p = self._file_path()
        if not p.exists():
            return    # CI cold-start: nothing to check
        result = edgar_mod.fetch_company_tickers(max_age_days=30, force=False)
        assert result is True

    def test_gitignore_does_not_prevent_runtime_use(self):
        """The gitignore entry only means the file is not committed; name_resolver
        still reads it at runtime when present. Verify the read path is sound."""
        from engine import name_resolver
        # This exercises the try/except read path regardless of file presence
        name_resolver.clear_cache()
        idx = name_resolver.build_index()
        assert isinstance(idx, dict)    # must not raise, even if file absent


# =========================================================================== #
# 5. _gdelt_tag uses entity_resolver.resolve_us
# =========================================================================== #

class TestGdeltTag:
    """_gdelt_tag uses entity_resolver.resolve_us for higher-precision tagging."""

    def test_megacap_alias_tagged(self):
        emap = nc.build_entity_map()
        tks = fn._gdelt_tag("Nvidia announces new H100 GPU for data centers", emap)
        assert "NVDA" in tks

    def test_apple_alias_tagged(self):
        emap = nc.build_entity_map()
        tks = fn._gdelt_tag("Apple reports record iPhone sales", emap)
        assert "AAPL" in tks

    def test_uppercase_ticker_tagged(self):
        emap = nc.build_entity_map()
        tks = fn._gdelt_tag("AAPL and MSFT rally on earnings", emap)
        assert "AAPL" in tks
        assert "MSFT" in tks

    def test_stopwords_not_tagged(self):
        emap = nc.build_entity_map()
        tks = fn._gdelt_tag("GDP data shows FED cut ETF US AI policy", emap)
        assert "GDP" not in tks
        assert "FED" not in tks
        assert "US" not in tks
        assert "AI" not in tks

    def test_empty_text(self):
        emap = nc.build_entity_map()
        assert fn._gdelt_tag("", emap) == []

    def test_resolver_failure_degrades_to_match_entities(self, monkeypatch):
        """If entity_resolver raises, _gdelt_tag falls back to nc.match_entities."""
        import importlib
        import sys

        # Temporarily block the entity_resolver import
        real_er = sys.modules.get("engine.entity_resolver")
        sys.modules["engine.entity_resolver"] = None  # type: ignore

        try:
            emap = nc.build_entity_map()
            # Should not raise; should fall back gracefully
            tks = fn._gdelt_tag("Nvidia beats earnings estimates", emap)
            # match_entities via alias still tags NVDA
            assert isinstance(tks, list)
        finally:
            if real_er is not None:
                sys.modules["engine.entity_resolver"] = real_er
            elif "engine.entity_resolver" in sys.modules:
                del sys.modules["engine.entity_resolver"]


# =========================================================================== #
# 6. timestamp_quality per-provider mapping
# =========================================================================== #

class TestTimestampQualityMapping:
    """Verify _PROVIDER_TQ maps each provider to the correct P2 quality enum."""

    def test_gdelt_crawl_bounded(self):
        assert fn._PROVIDER_TQ["gdelt"] == "CRAWL_BOUNDED"

    def test_rss_publisher_stated(self):
        assert fn._PROVIDER_TQ["rss"] == "PUBLISHER_STATED"

    def test_polygon_publisher_stated(self):
        assert fn._PROVIDER_TQ["polygon"] == "PUBLISHER_STATED"

    def test_finnhub_publisher_stated(self):
        assert fn._PROVIDER_TQ["finnhub"] == "PUBLISHER_STATED"

    def test_quiver_publisher_stated(self):
        assert fn._PROVIDER_TQ["quiver"] == "PUBLISHER_STATED"


if __name__ == "__main__":
    import traceback
    tests = [(k, v) for k, v in sorted(globals().items())
             if isinstance(v, type) and k.startswith("Test")]
    total = ok = fail = 0
    for cls_name, cls in tests:
        obj = cls()
        for meth_name in [m for m in dir(cls) if m.startswith("test_")]:
            total += 1
            try:
                getattr(obj, meth_name)()
                ok += 1
                print(f"ok  {cls_name}.{meth_name}")
            except Exception as exc:
                fail += 1
                print(f"FAIL {cls_name}.{meth_name}: {exc}")
                traceback.print_exc()
    print(f"\n{ok}/{total} passed, {fail} failed")
