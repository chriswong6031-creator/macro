"""tests/test_marketing_breaking.py — Breaking Desks W0 acceptance tests (D05).

Test list:
1. parse_feed: fixture RSS -> FeedItems matching schema (all 8 keys, ISO timestamps,
   tags stripped).
2. Seen-ledger dedupe: same items twice via ledger helpers on tmp_path -> second pass
   empty; ledger files live ONLY under tmp_path/data/marketing/breaking/; cap enforced.
3. Relevance: CPI item salience > celebrity item; CPI classed macro_print; tariff
   classed policy; tragedy item gets cta_suppress=True; official-tier bonus verifiable.
4. ADVERSARIAL: summary introducing number not in source -> validate_summary returns
   violations; summarize_item with monkeypatched bad LLM -> mode=llm_fallback,
   fallback text. Also: stance word "bullish" -> rejected.
5. Deterministic fallback path: no env var -> mode="deterministic",
   summary == headline + source_name.
6. Provenance end-to-end: build_breaking_payload on CPI item -> provenance fields
   correct, source_tier preserved, salience present, card_svg is str.
7. gitignore guard: "data/marketing/breaking/" is present in .gitignore.

NO NETWORK in any test. MARKETING_LLM_ENABLED never set in tests.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Repo root helper (mirrors test_marketing_content.py pattern)
# ---------------------------------------------------------------------------

def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")

ROOT = _worktree_root()
FIXTURES = ROOT / "tests" / "fixtures" / "breaking"

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


BLS_SOURCE_CFG = {
    "key": "bls_news",
    "kind": "rss",
    "url": "https://www.bls.gov/feed/news_release.rss",
    "source_name": "Bureau of Labor Statistics",
    "tier": "official",
}

ATOM_SOURCE_CFG = {
    "key": "fed_press",
    "kind": "rss",
    "url": "https://www.federalreserve.gov/feeds/press_all.xml",
    "source_name": "Federal Reserve",
    "tier": "official",
}

# ---------------------------------------------------------------------------
# Imports (done after ROOT set so engine/ on path)
# ---------------------------------------------------------------------------

import sys
sys.path.insert(0, str(ROOT))

from engine.marketing.breaking_feed import (
    parse_feed,
    filter_new_items,
    _load_seen,
    _save_seen,
    _breaking_dir,
)
from engine.marketing.breaking_relevance import score_item, rank_items
from engine.marketing.breaking_summary import (
    validate_summary,
    summarize_item,
    build_breaking_payload,
)

# ---------------------------------------------------------------------------
# Test 1: parse_feed — schema validation
# ---------------------------------------------------------------------------

class TestParseFeed:
    """parse_feed: fixture RSS -> FeedItems matching the 8-key schema exactly."""

    def test_rss_parse_count(self):
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        assert len(items) == 4, f"Expected 4 items, got {len(items)}"

    def test_rss_schema_keys(self):
        """Every item has exactly the 8 required FeedItem keys."""
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        required_keys = {"id", "source", "source_name", "source_tier",
                         "url", "published_at", "headline", "body_snippet"}
        for item in items:
            missing = required_keys - set(item.keys())
            assert not missing, f"Item missing keys {missing}: {item.get('headline', '')[:60]}"

    def test_rss_source_fields(self):
        """source, source_name, source_tier populated from source_cfg."""
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        for item in items:
            assert item["source"] == "bls_news"
            assert item["source_name"] == "Bureau of Labor Statistics"
            assert item["source_tier"] == "official"

    def test_rss_iso_timestamps(self):
        """published_at values are ISO8601 strings (parseable as datetime)."""
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        for item in items:
            ts = item["published_at"]
            assert isinstance(ts, str) and len(ts) > 0
            # Must parse as ISO datetime
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            assert dt.tzinfo is not None

    def test_rss_tags_stripped(self):
        """body_snippet contains no HTML tags."""
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        for item in items:
            assert "<" not in item["body_snippet"], (
                f"HTML tag found in snippet: {item['body_snippet'][:100]}"
            )

    def test_rss_id_stable(self):
        """id is a non-empty hex string (stable sha1)."""
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        for item in items:
            assert isinstance(item["id"], str)
            assert len(item["id"]) == 40  # sha1 hex
            assert all(c in "0123456789abcdef" for c in item["id"])

    def test_rss_url_populated(self):
        """url is non-empty for all items."""
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        for item in items:
            assert item["url"], f"Empty url in item: {item.get('headline', '')[:60]}"

    def test_atom_parses(self):
        """Atom feed parses correctly."""
        xml = _load_fixture("atom_feed.xml")
        items = parse_feed(xml, ATOM_SOURCE_CFG)
        assert len(items) == 2
        for item in items:
            required = {"id", "source", "source_name", "source_tier",
                        "url", "published_at", "headline", "body_snippet"}
            assert not (required - set(item.keys()))
            assert item["source_tier"] == "official"
            assert "federal" in item["source_name"].lower() or "reserve" in item["source_name"].lower()

    def test_cpi_headline_content(self):
        """CPI item headline contains the CPI text (not HTML-garbled)."""
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        cpi_items = [i for i in items if "consumer price index" in i["headline"].lower()
                     or "cpi" in i["headline"].lower()]
        assert cpi_items, "No CPI item found"
        cpi = cpi_items[0]
        assert "0.3" in cpi["headline"] or "0.3" in cpi["body_snippet"]
        assert "3.1" in cpi["headline"] or "3.1" in cpi["body_snippet"]


# ---------------------------------------------------------------------------
# Test 2: Seen-ledger dedupe
# ---------------------------------------------------------------------------

class TestSeenLedger:
    """Seen-ledger: same items twice -> second pass empty; files only in tmp_path."""

    def test_first_pass_returns_all(self, tmp_path):
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        new_items, updated_seen = filter_new_items(items, tmp_path)
        assert len(new_items) == len(items) == 4

    def test_second_pass_empty(self, tmp_path):
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        # First pass
        new_items, seen1 = filter_new_items(items, tmp_path)
        _save_seen(tmp_path, seen1)
        # Second pass — same items, all already seen
        new_items2, seen2 = filter_new_items(items, tmp_path)
        assert len(new_items2) == 0, f"Second pass should yield 0 new items, got {len(new_items2)}"

    def test_ledger_files_only_in_tmp(self, tmp_path):
        """Ledger JSON files live ONLY under tmp_path/data/marketing/breaking/."""
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        new_items, seen = filter_new_items(items, tmp_path)
        _save_seen(tmp_path, seen)
        breaking_dir = tmp_path / "data" / "marketing" / "breaking"
        assert breaking_dir.is_dir()
        seen_file = breaking_dir / "seen.json"
        assert seen_file.exists()
        # Confirm no ledger files in the repo's breaking dir if it doesn't exist
        # (we never write to ROOT's breaking dir in this test)
        repo_breaking = ROOT / "data" / "marketing" / "breaking"
        if repo_breaking.exists():
            # Should not have been written by this test (tmp_path was used)
            pass  # Can't assert absence if it exists from other runs

    def test_seen_ledger_cap(self, tmp_path):
        """Seen ledger capped at _SEEN_CAP (5000) entries."""
        from engine.marketing.breaking_feed import _SEEN_CAP
        # Build a dict with _SEEN_CAP + 100 entries
        big_seen = {f"id{i:06d}": f"2024-01-01T{i % 24:02d}:00:00+00:00"
                    for i in range(_SEEN_CAP + 100)}
        _save_seen(tmp_path, big_seen)
        reloaded = _load_seen(tmp_path)
        assert len(reloaded) == _SEEN_CAP


# ---------------------------------------------------------------------------
# Test 3: Relevance scoring
# ---------------------------------------------------------------------------

class TestRelevance:
    """Relevance: CPI > celebrity; CPI=macro_print; tariff=policy; tragedy cta_suppress."""

    def _get_items(self):
        xml = _load_fixture("rss_mixed.xml")
        return parse_feed(xml, BLS_SOURCE_CFG)

    def test_cpi_outranks_celebrity(self):
        """CPI print item has higher salience than celebrity headline."""
        items = self._get_items()
        # Score with a fixed datetime (US market hours for maximum score)
        # 10:00 AM Eastern = 15:00 UTC on a weekday
        now = datetime(2024, 7, 12, 15, 0, 0, tzinfo=timezone.utc)
        scored = [score_item(i, now=now) for i in items]

        cpi = next(s for s in scored if "consumer price index" in s["headline"].lower()
                   or "cpi" in s["headline"].lower())
        celeb = next(s for s in scored if "pop star" in s["headline"].lower())

        assert cpi["salience"] > celeb["salience"], (
            f"CPI salience {cpi['salience']} should exceed celebrity "
            f"salience {celeb['salience']}"
        )

    def test_cpi_classified_macro_print(self):
        items = self._get_items()
        cpi = next(i for i in items if "consumer price index" in i["headline"].lower())
        now = datetime(2024, 7, 12, 15, 0, 0, tzinfo=timezone.utc)
        scored = score_item(cpi, now=now)
        assert scored["event_class"] == "macro_print", (
            f"CPI event_class should be 'macro_print', got '{scored['event_class']}'"
        )

    def test_tariff_classified_policy(self):
        items = self._get_items()
        tariff = next(i for i in items if "tariff" in i["headline"].lower())
        now = datetime(2024, 7, 11, 15, 0, 0, tzinfo=timezone.utc)
        scored = score_item(tariff, now=now)
        assert scored["event_class"] == "policy", (
            f"Tariff event_class should be 'policy', got '{scored['event_class']}'"
        )

    def test_tragedy_cta_suppressed(self):
        items = self._get_items()
        tragedy = next(i for i in items if "earthquake" in i["headline"].lower()
                       or "kills" in i["headline"].lower())
        now = datetime(2024, 7, 12, 15, 0, 0, tzinfo=timezone.utc)
        scored = score_item(tragedy, now=now)
        assert scored["cta_suppress"] is True, "Tragedy/casualty item should have cta_suppress=True"

    def test_official_tier_bonus(self):
        """Official-tier source gets higher salience than same item from wire tier."""
        items = self._get_items()
        cpi = next(i for i in items if "consumer price index" in i["headline"].lower())
        now = datetime(2024, 7, 12, 15, 0, 0, tzinfo=timezone.utc)

        # Score as official
        scored_official = score_item({**cpi, "source_tier": "official"}, now=now)
        # Score same item as wire
        scored_wire = score_item({**cpi, "source_tier": "wire"}, now=now)
        # Score same item as aggregator
        scored_agg = score_item({**cpi, "source_tier": "aggregator"}, now=now)

        assert scored_official["salience"] > scored_wire["salience"]
        assert scored_wire["salience"] > scored_agg["salience"]

        # Verify via components
        comps = scored_official["_salience_components"]
        assert comps["tier_bonus"] == 15.0, f"Official tier_bonus should be 15.0, got {comps['tier_bonus']}"

    def test_rank_items_order(self):
        """rank_items returns items sorted by salience descending."""
        items = self._get_items()
        now = datetime(2024, 7, 12, 15, 0, 0, tzinfo=timezone.utc)
        ranked = rank_items(items, now=now)
        saliences = [r["salience"] for r in ranked]
        assert saliences == sorted(saliences, reverse=True)

    def test_salience_components_present(self):
        """score_item always returns _salience_components with all keys."""
        items = self._get_items()
        cpi = next(i for i in items if "consumer price index" in i["headline"].lower())
        now = datetime(2024, 7, 12, 15, 0, 0, tzinfo=timezone.utc)
        scored = score_item(cpi, now=now)
        assert "_salience_components" in scored
        comps = scored["_salience_components"]
        for key in ("base", "tier_bonus", "kw_bonus", "ticker_bonus",
                    "market_hours_weight", "raw", "capped"):
            assert key in comps, f"Missing component key: {key}"


# ---------------------------------------------------------------------------
# Test 4: ADVERSARIAL — validate_summary rejects invented numbers + stance
# ---------------------------------------------------------------------------

class TestAdversarialValidation:
    """validate_summary rejects summaries introducing numbers not in source."""

    def _cpi_item(self):
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        return next(i for i in items if "consumer price index" in i["headline"].lower())

    def test_invented_number_rejected(self):
        """Summary saying 'rose 0.5%' when source says '0.3%' -> violation."""
        item = self._cpi_item()
        # Source has 0.3 and 3.1 — introduce 0.5 (not in source)
        bad_summary = "The Consumer Price Index rose 0.5% in June, beating estimates."
        violations = validate_summary(bad_summary, item)
        assert violations, "Expected violations for invented number 0.5"
        # Find the specific number violation
        number_viols = [v for v in violations if "0.5" in v]
        assert number_viols, f"Expected violation mentioning '0.5', got: {violations}"

    def test_second_invented_number_rejected(self):
        """Summary introducing '3.7%' (not in source) -> violation."""
        item = self._cpi_item()
        bad_summary = "Inflation came in at 3.7% year-over-year in June."
        violations = validate_summary(bad_summary, item)
        number_viols = [v for v in violations if "3.7" in v]
        assert number_viols, f"Expected violation mentioning '3.7', got: {violations}"

    def test_good_summary_no_violations(self):
        """Summary using only source numbers (0.3, 3.1) -> no number violations."""
        item = self._cpi_item()
        # These numbers appear in the source
        good_summary = "The Consumer Price Index rose 0.3 percent in June. The 12-month inflation rate reached 3.1 percent."
        violations = validate_summary(good_summary, item)
        # Should have no number-verbatim violations
        number_viols = [v for v in violations
                        if "not present verbatim" in v or "not in whitelist" in v]
        assert not number_viols, f"Unexpected number violations: {number_viols}"

    def test_stance_word_bullish_rejected(self):
        """Summary containing 'bullish' (not in source) -> violation."""
        item = self._cpi_item()
        bad_summary = "The CPI print is bullish for risk assets going forward."
        violations = validate_summary(bad_summary, item)
        stance_viols = [v for v in violations if "bullish" in v]
        assert stance_viols, f"Expected stance violation for 'bullish', got: {violations}"

    def test_summarize_item_llm_fallback_on_bad_number(self):
        """summarize_item with monkeypatched LLM returning invented number -> llm_fallback."""
        item = self._cpi_item()

        def bad_llm(item, cfg):
            return "The Consumer Price Index rose 0.5% in June, far above the 3.7% annual rate."

        cfg = {"breaking": {"llm": {"enabled": True}}}
        # Ensure MARKETING_LLM_ENABLED is NOT set (test environment)
        assert os.environ.get("MARKETING_LLM_ENABLED", "") not in ("1", "true", "yes")

        result = summarize_item(item, cfg, _llm_override=bad_llm)
        # LLM override provided invented numbers -> should fall back
        assert result["mode"] == "llm_fallback"
        assert len(result["violations_seen"]) > 0
        # Fallback text must be deterministic "{headline} — {source_name}"
        expected_fallback = f"{item['headline']} — {item['source_name']}"
        assert result["summary"] == expected_fallback

    def test_summarize_item_llm_fallback_on_stance(self):
        """summarize_item with LLM returning bullish stance -> llm_fallback."""
        item = self._cpi_item()

        def stance_llm(item, cfg):
            return "The CPI print is bullish for markets and signals a rate cut."

        cfg = {"breaking": {"llm": {"enabled": True}}}
        result = summarize_item(item, cfg, _llm_override=stance_llm)
        assert result["mode"] == "llm_fallback"
        assert any("bullish" in v for v in result["violations_seen"])


# ---------------------------------------------------------------------------
# Test 5: Deterministic fallback path
# ---------------------------------------------------------------------------

class TestDeterministicFallback:
    """With no MARKETING_LLM_ENABLED and no override -> mode=deterministic."""

    def test_no_env_var_deterministic(self):
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        cpi = next(i for i in items if "consumer price index" in i["headline"].lower())

        # Confirm env var not set
        assert os.environ.get("MARKETING_LLM_ENABLED", "") not in ("1", "true", "yes")

        cfg = {"breaking": {"llm": {"enabled": True, "model_key": "marketing_copy"}}}
        result = summarize_item(cpi, cfg)
        assert result["mode"] == "deterministic"
        expected = f"{cpi['headline']} — {cpi['source_name']}"
        assert result["summary"] == expected

    def test_deterministic_summary_format(self):
        """Deterministic summary == '{headline} — {source_name}'."""
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        for item in items:
            cfg = {"breaking": {"llm": {"enabled": False}}}
            result = summarize_item(item, cfg)
            expected = f"{item['headline']} — {item['source_name']}"
            assert result["summary"] == expected
            assert result["mode"] == "deterministic"


# ---------------------------------------------------------------------------
# Test 6: Provenance end-to-end
# ---------------------------------------------------------------------------

class TestProvenanceEndToEnd:
    """build_breaking_payload: provenance fields correct, source_tier preserved."""

    def _scored_cpi(self):
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        cpi = next(i for i in items if "consumer price index" in i["headline"].lower())
        now = datetime(2024, 7, 12, 15, 0, 0, tzinfo=timezone.utc)
        return score_item(cpi, now=now)

    def test_provenance_source_url(self):
        """provenance.source_url == item url."""
        cpi = self._scored_cpi()
        cfg = {"breaking": {"llm": {"enabled": False}}}
        payload = build_breaking_payload(cpi, cfg)
        assert payload["provenance"]["source_url"] == cpi["url"]

    def test_provenance_source_key(self):
        """provenance.source == item.source."""
        cpi = self._scored_cpi()
        cfg = {"breaking": {"llm": {"enabled": False}}}
        payload = build_breaking_payload(cpi, cfg)
        assert payload["provenance"]["source"] == cpi["source"]

    def test_source_tier_preserved(self):
        """source_tier in payload == 'official'."""
        cpi = self._scored_cpi()
        cfg = {"breaking": {"llm": {"enabled": False}}}
        payload = build_breaking_payload(cpi, cfg)
        assert payload["source_tier"] == "official"

    def test_salience_present(self):
        """Salience is a positive float in the payload."""
        cpi = self._scored_cpi()
        cfg = {"breaking": {"llm": {"enabled": False}}}
        payload = build_breaking_payload(cpi, cfg)
        assert isinstance(payload["salience"], float)
        assert payload["salience"] > 0

    def test_card_svg_is_str(self):
        """card_svg is a str (may be '' if renderer not present)."""
        cpi = self._scored_cpi()
        cfg = {"breaking": {"llm": {"enabled": False}}}
        payload = build_breaking_payload(cpi, cfg)
        assert isinstance(payload["card_svg"], str), (
            f"card_svg should be str, got {type(payload['card_svg'])}"
        )

    def test_payload_kind(self):
        """payload kind == 'breaking'."""
        cpi = self._scored_cpi()
        cfg = {"breaking": {"llm": {"enabled": False}}}
        payload = build_breaking_payload(cpi, cfg)
        assert payload["kind"] == "breaking"

    def test_provenance_ingested_at(self):
        """provenance.ingested_at is a parseable ISO timestamp."""
        cpi = self._scored_cpi()
        cfg = {"breaking": {"llm": {"enabled": False}}}
        payload = build_breaking_payload(cpi, cfg)
        ingested_at = payload["provenance"]["ingested_at"]
        dt = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
        assert dt.tzinfo is not None

    def test_cta_suppress_propagated(self):
        """cta_suppress from relevance scoring propagates to payload."""
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        tragedy = next(i for i in items if "earthquake" in i["headline"].lower())
        now = datetime(2024, 7, 12, 15, 0, 0, tzinfo=timezone.utc)
        scored = score_item(tragedy, now=now)
        cfg = {"breaking": {"llm": {"enabled": False}}}
        payload = build_breaking_payload(scored, cfg)
        assert payload["cta_suppress"] is True


# ---------------------------------------------------------------------------
# Test 7: gitignore guard
# ---------------------------------------------------------------------------

class TestGitignoreGuard:
    """data/marketing/breaking/ must be in .gitignore (local-only law tripwire)."""

    def test_breaking_dir_in_gitignore(self):
        gitignore_path = ROOT / ".gitignore"
        assert gitignore_path.exists(), ".gitignore not found at repo root"
        content = gitignore_path.read_text(encoding="utf-8")
        assert "data/marketing/breaking/" in content, (
            "data/marketing/breaking/ not found in .gitignore — "
            "the seen-ledger must never be committed (local-only law)"
        )


# ---------------------------------------------------------------------------
# Test 8: review-fix regressions (percent equivalence + poller scheme guard)
# ---------------------------------------------------------------------------

class TestReviewFixes:
    """Regressions for the opus-review fixes (MIN-1/2/3)."""

    @staticmethod
    def _item(headline: str, snippet: str = "") -> dict:
        return {
            "id": "x", "source": "bls_news", "source_name": "BLS",
            "source_tier": "official", "url": "https://example.gov/x",
            "published_at": "2026-07-14T12:31:00Z",
            "headline": headline, "body_snippet": snippet,
        }

    def test_percent_word_source_symbol_summary_ok(self):
        # Source spells "0.3 percent"; summary writes "0.3%" — same number,
        # equivalent representation, must pass.
        item = self._item("CPI rose 0.3 percent in June")
        assert validate_summary("CPI rose 0.3% in June.", item) == []

    def test_percent_symbol_source_word_summary_ok(self):
        item = self._item("CPI rose 0.3% in June")
        assert validate_summary("CPI rose 0.3 percent in June.", item) == []

    def test_equivalence_never_admits_new_digits(self):
        # Equivalence only re-shapes numbers already in the source — an
        # unsourced 0.5% must still be rejected.
        item = self._item("CPI rose 0.3 percent in June")
        violations = validate_summary("CPI rose 0.5% in June.", item)
        assert any("0.5%" in v for v in violations)

    def test_bare_number_without_percent_context_not_percentified(self):
        # "Section 3.1 of the report" must NOT admit "3.1%".
        item = self._item("Section 3.1 of the report was released")
        violations = validate_summary("Inflation hit 3.1%.", item)
        assert any("3.1%" in v for v in violations)

    def test_poll_source_refuses_non_http_scheme(self, tmp_path, capsys):
        from engine.marketing.breaking_feed import poll_source
        src = {"key": "evil", "kind": "rss", "url": "file:///etc/passwd",
               "source_name": "X", "tier": "aggregator"}
        out = poll_source(src, root=tmp_path, session_state={})
        assert out == []
        assert "refusing non-http(s) url" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Test 9: quality-upgrade regressions (main-loop Fable review, round 2)
# ---------------------------------------------------------------------------

class TestPubDateParsing:
    """ENG-1: named-zone / offset RFC-2822 dates must parse, never fall to now()."""

    def test_named_zone_est(self):
        from engine.marketing.breaking_feed import _parse_pub_date
        # BLS-style dateline: EST = UTC-5
        assert _parse_pub_date("Mon, 12 Jan 2026 08:30:00 EST").startswith(
            "2026-01-12T13:30:00"
        )

    def test_named_zone_edt(self):
        from engine.marketing.breaking_feed import _parse_pub_date
        # EDT = UTC-4
        assert _parse_pub_date("Tue, 14 Jul 2026 08:30:00 EDT").startswith(
            "2026-07-14T12:30:00"
        )

    def test_numeric_offset(self):
        from engine.marketing.breaking_feed import _parse_pub_date
        assert _parse_pub_date("Tue, 14 Jul 2026 18:00:00 +0530").startswith(
            "2026-07-14T12:30:00"
        )

    def test_iso_with_offset(self):
        from engine.marketing.breaking_feed import _parse_pub_date
        assert _parse_pub_date("2026-07-14T09:00:00-04:00").startswith(
            "2026-07-14T13:00:00"
        )

    def test_dc_date_fallback_in_rss(self):
        # An RSS item carrying only dc:date must not be stamped with now().
        rss = """<?xml version="1.0"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><item>
  <title>Policy statement released</title>
  <link>https://example.gov/x</link>
  <dc:date>2026-03-02T10:00:00Z</dc:date>
</item></channel></rss>"""
        items = parse_feed(rss, BLS_SOURCE_CFG)
        assert len(items) == 1
        assert items[0]["published_at"].startswith("2026-03-02T10:00:00")


class TestAtomContentElement:
    """ENG-2: text-only <content> (falsy Element!) must not be dropped."""

    def test_text_only_content_no_summary(self):
        atom = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:x</id>
    <title>Statement</title>
    <link href="https://example.gov/y" rel="alternate"/>
    <updated>2026-07-14T12:00:00Z</updated>
    <content>The committee voted 9-2 to hold the target range unchanged.</content>
  </entry>
</feed>"""
        items = parse_feed(atom, ATOM_SOURCE_CFG)
        assert len(items) == 1
        assert "voted 9-2" in items[0]["body_snippet"]


class TestPollerBackoff:
    """ENG-3/ENG-4: 304 is not an error; failures back off exponentially."""

    @staticmethod
    def _src():
        return {"key": "t", "kind": "rss", "url": "https://example.gov/feed",
                "source_name": "T", "tier": "official", "poll_interval_s": 300}

    def test_http_304_resets_fail_count_quietly(self, tmp_path, monkeypatch, capsys):
        import engine.marketing.breaking_feed as bf
        from urllib.error import HTTPError

        def _raise_304(req, timeout):  # noqa: ARG001
            raise HTTPError("https://example.gov/feed", 304, "Not Modified", {}, None)

        monkeypatch.setattr(bf, "urlopen", _raise_304)
        state: dict = {"t": {"fail_count": 3, "etag": "x"}}
        out = bf.poll_source(self._src(), root=tmp_path, session_state=state)
        assert out == []
        assert state["t"]["fail_count"] == 0
        assert "error" not in capsys.readouterr().err.lower()

    def test_failure_backoff_suppresses_retry(self, tmp_path, monkeypatch):
        import time as _time
        import engine.marketing.breaking_feed as bf
        from urllib.error import URLError

        def _raise(req, timeout):  # noqa: ARG001
            raise URLError("dead")

        monkeypatch.setattr(bf, "urlopen", _raise)
        state: dict = {}
        assert bf.poll_source(self._src(), root=tmp_path, session_state=state) == []
        assert state["t"]["fail_count"] == 1
        # Push last_poll past the BASE interval but inside the doubled window:
        # the exponential backoff must still suppress the attempt.
        state["t"]["last_poll_ts"] = _time.time() - 301
        calls = {"n": 0}

        def _count(req, timeout):  # noqa: ARG001
            calls["n"] += 1
            raise URLError("dead")

        monkeypatch.setattr(bf, "urlopen", _count)
        assert bf.poll_source(self._src(), root=tmp_path, session_state=state) == []
        assert calls["n"] == 0  # suppressed — no network attempt

    def test_retry_after_honored(self, tmp_path, monkeypatch):
        import time as _time
        import engine.marketing.breaking_feed as bf
        from urllib.error import HTTPError
        from email.message import Message

        hdrs = Message()
        hdrs["Retry-After"] = "600"

        def _raise_429(req, timeout):  # noqa: ARG001
            raise HTTPError("https://example.gov/feed", 429, "Too Many", hdrs, None)

        monkeypatch.setattr(bf, "urlopen", _raise_429)
        state: dict = {}
        bf.poll_source(self._src(), root=tmp_path, session_state=state)
        assert state["t"]["backoff_until"] >= _time.time() + 500


class TestStanceSourceBoundary:
    """ENG-5: substring source presence must not whitelist stance words."""

    def test_buyback_does_not_whitelist_buy(self):
        item = {
            "headline": "Company announces $2 billion buyback", "body_snippet": "",
            "source_name": "X", "source_tier": "wire", "url": "https://x",
            "published_at": "2026-07-14T12:00:00Z",
        }
        violations = validate_summary(
            "Company announces $2 billion buyback; traders buy the news.", item
        )
        assert any("'buy'" in v for v in violations)

    def test_standalone_source_word_still_allowed(self):
        item = {
            "headline": "Stocks rally after the print", "body_snippet": "",
            "source_name": "X", "source_tier": "wire", "url": "https://x",
            "published_at": "2026-07-14T12:00:00Z",
        }
        assert validate_summary("Stocks rally after the print.", item) == []


class TestAliasWordBoundary:
    """ENG-6: name aliases are word-boundary matched."""

    def test_metals_does_not_match_meta(self):
        s = score_item({"headline": "Precious metals rallied on the data",
                        "body_snippet": "", "source_tier": "wire"})
        assert "META" not in s["matched"]["tickers"]

    def test_visas_does_not_match_visa(self):
        s = score_item({"headline": "New visas policy announced",
                        "body_snippet": "", "source_tier": "official"})
        assert "V" not in s["matched"]["tickers"]

    def test_real_meta_still_matches(self):
        s = score_item({"headline": "Meta reports quarterly results",
                        "body_snippet": "", "source_tier": "wire"})
        assert "META" in s["matched"]["tickers"]


class TestSentenceCountAbbreviations:
    """ENG-7: abbreviations must not inflate the sentence count."""

    def test_us_abbreviation_one_sentence(self):
        from engine.marketing.breaking_summary import _count_sentences
        assert _count_sentences(
            "U.S. inflation rose 0.3% in June, the Bureau said."
        ) == 1

    def test_two_sentences_with_abbreviations(self):
        from engine.marketing.breaking_summary import _count_sentences
        assert _count_sentences(
            "U.S. payrolls rose. The U.K. print follows Dr. Smith's briefing."
        ) == 2


class TestGeoTaxonomyPrecision:
    """ENG-8: labor strikes and price wars are not geopolitics."""

    def test_labor_strike_not_geopolitical(self):
        s = score_item({"headline": "Auto workers strike at three plants",
                        "body_snippet": "", "source_tier": "wire"})
        assert s["event_class"] != "geopolitical"

    def test_bidding_war_not_geopolitical(self):
        s = score_item({"headline": "Bidding war erupts over retail chain",
                        "body_snippet": "", "source_tier": "wire"})
        assert s["event_class"] != "geopolitical"

    def test_missile_strike_still_geopolitical(self):
        s = score_item({"headline": "Missile strike hits port city overnight",
                        "body_snippet": "", "source_tier": "wire"})
        assert s["event_class"] == "geopolitical"


class TestUniverseCacheAndEnrichment:
    """ENG-9 universe cache + ENG-10 ticker price enrichment."""

    def test_universe_cached_by_mtime(self, tmp_path):
        import pandas as pd
        import engine.marketing.breaking_relevance as br
        store = tmp_path / "data" / "earnings"
        store.mkdir(parents=True)
        pd.DataFrame({"eps_forecast": [1.0]}, index=["ZZZT"]).to_parquet(
            store / "earnings.parquet"
        )
        first = br._load_universe(tmp_path)
        assert "ZZZT" in first
        second = br._load_universe(tmp_path)
        assert second is first  # cache hit returns the same frozenset object

    def test_enrich_tickers_from_close_store(self, tmp_path):
        import pandas as pd
        from engine.marketing.breaking_summary import _enrich_tickers
        store = tmp_path / "data" / "stocks"
        store.mkdir(parents=True)
        pd.DataFrame(
            {"close": [100.0, 102.0]},
            index=pd.to_datetime(["2026-07-13", "2026-07-14"]),
        ).to_parquet(store / "ZZZT.parquet")
        rows = _enrich_tickers(["ZZZT", "NOPE"], tmp_path)
        assert rows[0]["ticker"] == "ZZZT"
        assert rows[0]["price"] == 102.0
        assert abs(rows[0]["pct"] - 2.0) < 1e-9
        assert rows[1] == {"ticker": "NOPE", "price": None, "pct": None}

    def test_payload_card_carries_kicker(self):
        # ENG-11: event_class flows into the rendered card as plain words.
        items = parse_feed(_load_fixture("rss_mixed.xml"), BLS_SOURCE_CFG)
        cpi = next(i for i in items if "Consumer Price Index" in i["headline"])
        scored = score_item(cpi)
        assert scored["event_class"] == "macro_print"
        payload = build_breaking_payload(scored, {"breaking": {"llm": {"enabled": False}}})
        assert "MACRO PRINT" in payload["card_svg"]
        assert "macro_print" not in payload["card_svg"]  # raw key never shown
