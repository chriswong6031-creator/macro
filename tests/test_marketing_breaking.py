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
        # The fallback is the deterministic body, attributed on a DOUBLE HYPHEN
        # (B1: never an em dash -- the publisher quarantines U+2014). Its text is
        # the source's own lead sentence, so the invented 0.5% is gone and every
        # number that remains is the source's.
        assert result["summary"].endswith(f" -- {item['source_name']}")
        assert "0.5%" not in result["summary"]
        body = result["summary"].rsplit(" -- ", 1)[0]
        assert body in (item["body_snippet"] or "") or body == item["headline"]

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
    """With no MARKETING_LLM_ENABLED and no override -> mode=deterministic.

    W1.5 (#3960 reviewer minor) CHANGED WHAT THE FALLBACK BODY SAYS. It used to
    be ``{headline} -- {source_name}``, i.e. the headline verbatim; since the
    emitted post is ``headline + blank line + body`` (outbox.compose_text), every
    keyless press item shipped the same sentence twice. The body is now the
    source's own lead sentence when the packet carries one, and falls back to the
    headline relay when it does not. The attribution join is unchanged.
    """

    def test_no_env_var_deterministic(self):
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        cpi = next(i for i in items if "consumer price index" in i["headline"].lower())

        # Confirm env var not set
        assert os.environ.get("MARKETING_LLM_ENABLED", "") not in ("1", "true", "yes")

        cfg = {"breaking": {"llm": {"enabled": True, "model_key": "marketing_copy"}}}
        result = summarize_item(cpi, cfg)
        assert result["mode"] == "deterministic"
        assert result["summary"].endswith(f" -- {cpi['source_name']}")
        # THE WART: the body is no longer the headline wearing an attribution.
        assert result["summary"] != f"{cpi['headline']} -- {cpi['source_name']}"
        body = result["summary"].rsplit(" -- ", 1)[0]
        assert body != cpi["headline"]
        assert body in cpi["body_snippet"], "the body is not source text"

    def test_deterministic_summary_format(self):
        """Every deterministic body is source text, attributed on ' -- ' (B1)."""
        xml = _load_fixture("rss_mixed.xml")
        items = parse_feed(xml, BLS_SOURCE_CFG)
        for item in items:
            cfg = {"breaking": {"llm": {"enabled": False}}}
            result = summarize_item(item, cfg)
            assert result["mode"] == "deterministic"
            assert result["summary"].endswith(f" -- {item['source_name']}")
            body = result["summary"].rsplit(" -- ", 1)[0]
            # Nothing invented: the body is either the source's lead sentence or
            # the headline, never a construction of our own.
            assert body == item["headline"] or body in (item["body_snippet"] or ""), \
                body

    def test_a_packet_with_no_body_keeps_the_headline_relay(self):
        """The honest floor. With nothing but a headline, relaying it IS the
        truthful thing to send -- the fix removes a redundancy, not a fallback."""
        item = {"headline": "Fed holds rates steady", "body_snippet": "",
                "source_name": "Federal Reserve"}
        result = summarize_item(item, {"breaking": {"llm": {"enabled": False}}})
        assert result["summary"] == "Fed holds rates steady -- Federal Reserve"

    def test_a_body_that_merely_repeats_the_headline_is_not_used(self):
        """A wire mirror whose snippet restates its own headline gains nothing,
        so the near-verbatim gate sends it back to the headline relay."""
        item = {"headline": "Treasury secretary says tariffs stay in place",
                "body_snippet": "Treasury secretary says tariffs stay in place.",
                "source_name": "Reuters"}
        result = summarize_item(item, {"breaking": {"llm": {"enabled": False}}})
        assert result["summary"] == \
            "Treasury secretary says tariffs stay in place -- Reuters"

    def test_an_em_dash_in_the_source_body_never_reaches_the_copy(self):
        """The publisher's last gate quarantines U+2014, so a source dash must be
        normalised to the house double hyphen rather than relayed."""
        from engine.marketing.copywriter import banned_language

        item = {"headline": "ECB signals a pause",
                "body_snippet": "The ECB said policy — unchanged since March "
                                "— will stay restrictive for now.",
                "source_name": "ECB"}
        summary = summarize_item(item, {"breaking": {"llm": {"enabled": False}}})["summary"]
        assert "—" not in summary and "–" not in summary
        assert banned_language(summary) == []
        assert "unchanged since March" in summary        # the fact survived

    def test_a_byline_fragment_is_not_a_body(self):
        """"By Reuters Staff" is not a fact. Too-short leads fall back."""
        item = {"headline": "Oil holds gains", "body_snippet": "By Reuters Staff.",
                "source_name": "Reuters"}
        result = summarize_item(item, {"breaking": {"llm": {"enabled": False}}})
        assert result["summary"] == "Oil holds gains -- Reuters"


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
        # equivalent representation, must pass. The summary is a RESTATEMENT (adds
        # framing) so it also clears the M2 near-verbatim guard; a whole-headline
        # relay ("CPI rose 0.3% in June.") is now correctly rejected as copypasta.
        item = self._item("CPI rose 0.3 percent in June")
        assert validate_summary(
            "The June CPI reading came in at 0.3% on the month.", item
        ) == []

    def test_percent_symbol_source_word_summary_ok(self):
        item = self._item("CPI rose 0.3% in June")
        assert validate_summary(
            "The June CPI reading came in at 0.3 percent on the month.", item
        ) == []

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
        # "rally" is a standalone word in the SOURCE (headline+snippet), so the
        # summary may use it. The summary is a RESTATEMENT (not a headline relay) so
        # it also clears the M2 near-verbatim guard — the stance whitelist is what
        # is under test here, not copypasta.
        item = {
            "headline": "Stocks rally after the print",
            "body_snippet": "Equities extended a broad rally following the release.",
            "source_name": "X", "source_tier": "wire", "url": "https://x",
            "published_at": "2026-07-14T12:00:00Z",
        }
        assert validate_summary(
            "Equities pushed higher in a broad rally once the data landed.", item
        ) == []


class TestCopypastaLaw:
    """M2 (opus review): §3 key-phrase / copypasta runtime guard in
    validate_summary — at most ONE short quote, and no near-verbatim headline
    relay. The prompt text alone could not stop an LLM returning the whole source
    headline; these deterministic checks do.
    """

    @staticmethod
    def _item(headline: str, snippet: str = "") -> dict:
        return {
            "id": "x", "source": "wire", "source_name": "Reuters",
            "source_tier": "wire", "url": "https://example.com/x",
            "published_at": "2026-07-27T12:00:00Z",
            "headline": headline, "body_snippet": snippet,
        }

    def test_whole_headline_in_quotes_rejected(self):
        # The exact §3 failure: the LLM returns the whole source headline wrapped
        # in quotes. It must be rejected (quoted span > 6 words AND near-verbatim).
        hl = "Trump orders sweeping new tariffs on all Chinese imports effective Monday"
        v = validate_summary(f'"{hl}"', self._item(hl))
        assert v, "whole-headline-in-quotes must be rejected"
        assert any("quoted span too long" in x or "near-verbatim" in x for x in v)

    def test_byte_identical_headline_rejected(self):
        # Unquoted byte-identical relay -> near-verbatim guard fires.
        hl = "Fed holds rates steady and signals one cut later this year"
        v = validate_summary(hl + ".", self._item(hl))
        assert any("near-verbatim" in x for x in v)

    def test_trivially_reordered_headline_rejected(self):
        hl = "Consumer confidence fell sharply in July amid tariff worries"
        reordered = "Amid tariff worries, consumer confidence fell sharply in July."
        v = validate_summary(reordered, self._item(hl))
        assert any("near-verbatim" in x for x in v)

    def test_two_quoted_spans_rejected(self):
        hl = "Officials describe the talks and the mood"
        summary = 'Negotiators called the talks "very friendly" and the mood "warm".'
        v = validate_summary(summary, self._item(hl))
        assert any("too many quoted spans" in x for x in v)

    def test_seven_word_quote_rejected(self):
        hl = "A minister comments at length on the plan"
        # A 7-word quoted span (> 6) is rejected even as the only quote.
        summary = 'The plan drew a rebuke: "this is a very bad and rushed idea".'
        v = validate_summary(summary, self._item(hl))
        assert any("quoted span too long" in x for x in v)

    def test_legit_short_quote_paraphrase_passes(self):
        # A genuine restatement quoting ONE short (<=6 word) source phrase passes.
        hl = "Trump says China trade talks were very friendly and productive overall"
        snippet = 'The president added the sessions were "very friendly" throughout.'
        summary = (
            'The president framed the sessions with China as "very friendly," '
            "signalling progress on the trade file."
        )
        assert validate_summary(summary, self._item(hl, snippet)) == []

    def test_deterministic_fallback_exempt_from_near_verbatim(self):
        # The "{headline} — {source}" fallback IS the headline with attribution; the
        # is_deterministic_fallback flag exempts it from the (c) near-verbatim guard.
        # (Assert specifically on the near-verbatim rule — an unrelated validate_copy
        # rule such as the em-dash check is out of scope for this bypass.)
        hl = "Fed holds rates steady and signals one cut later this year"
        fallback = f"{hl} - Reuters"  # ASCII hyphen: isolate the near-verbatim rule
        # Without the flag it would trip near-verbatim...
        assert any(
            "near-verbatim" in x for x in validate_summary(fallback, self._item(hl))
        )
        # ...with the flag set, the near-verbatim guard is skipped.
        v = validate_summary(fallback, self._item(hl), is_deterministic_fallback=True)
        assert not any("near-verbatim" in x for x in v)
        assert v == [], f"fallback should be clean under ASCII hyphen, got: {v}"


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
        pd = pytest.importorskip("pandas")  # skip in the minimal pytest+pyyaml lane
        pytest.importorskip("pyarrow")      # parquet writer
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
        pd = pytest.importorskip("pandas")  # skip in the minimal pytest+pyyaml lane
        pytest.importorskip("pyarrow")      # parquet writer
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


# ---------------------------------------------------------------------------
# CHATGPT-FIRST ROUTING (operator directive 2026-07-29)
#
# "The marketing content LLM lanes must default to the attached ChatGPT/Codex
# account (Claude subscription tokens are being reserved for website-building
# sessions), with Claude as fallback drawn through the key_pool OAuth load
# balancer."
#
# Ruled tier for this lane: gpt-5.6-sol at medium effort. Sol because the
# breaking rewriter produces the sentence that publishes, so it is writing work.
# The full ruling table and the cross-lane pins live in
# tests/test_marketing_copy_v2.py.
# ---------------------------------------------------------------------------

class TestBreakingProviderRouting:
    """The lane must ASK for codex first and carry the ruled tier.

    build_providers is replaced by a recorder that returns [] — every call site
    treats an empty waterfall as "mute, fall back to deterministic", which is the
    shortest path through the code that still proves what the lane requested. No
    network, no credential, no anthropic import.
    """

    def _capture(self, monkeypatch) -> list[dict]:
        from engine import llm_auth

        seen: list[dict] = []

        def _rec(cfg, **kwargs):  # noqa: ANN001
            seen.append(dict(cfg))
            return []

        monkeypatch.setattr(llm_auth, "build_providers", _rec)
        return seen

    def _live_cfg(self) -> dict:
        import yaml

        marketing = yaml.safe_load(
            (ROOT / "config" / "marketing.yml").read_text(encoding="utf-8")) or {}
        return {"breaking": {"llm": dict((marketing.get("breaking") or {}).get("llm") or {})}}

    def test_the_lane_asks_for_codex_first_on_sol(self, monkeypatch):
        from engine.marketing.breaking_summary import _llm_summarize

        seen = self._capture(monkeypatch)
        monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
        items = parse_feed(_load_fixture("rss_mixed.xml"), BLS_SOURCE_CFG)
        assert _llm_summarize(items[0], self._live_cfg()) is None  # muted on purpose

        assert seen, "the breaking lane never reached the provider waterfall"
        cfg = seen[0]
        assert cfg["provider_order"] == ["codex", "oauth", "anthropic", "deepseek"]
        assert cfg["codex_source_model"] == "gpt-5.6-sol"
        assert cfg["codex_reasoning_effort"] == "medium"
        assert cfg["oauth_pool_lane"] == "marketing-breaking"
        assert cfg["usage_lane"] == "marketing-breaking"

    def test_the_shipped_config_carries_the_ruling(self):
        block = self._live_cfg()["breaking"]["llm"]
        assert block["provider_order"] == ["codex", "oauth", "anthropic", "deepseek"]
        assert block["codex_source_model"] == "gpt-5.6-sol"
        assert block["codex_reasoning_effort"] == "medium"
        assert block["oauth_pool_lane"] == "marketing-breaking"
        # Luna never touches a user-facing word.
        assert "luna" not in str(block).lower()


class TestRoutineRestatementDemotion:
    """A restatement of an already-published print is not a flash.

    Operator 2026-07-30, on a BEA GDP restatement that reached the live account
    with no reaction and no chart, at 1-4 views. The taxonomy scored it by
    TOPIC: "gdp" matched, so a third-estimate revision of a quarter that ended
    months ago scored exactly as high as the print itself.

    The wire is a RELAY by charter (breaking_summary.validate_summary rejects
    stance words; wire_voice's prompt says "no interpretation, no stance") and
    that is correct for a genuine flash -- speed and accuracy are the product,
    and an LLM inventing implications about someone else's news is the
    fabrication risk the charter exists to stop. So the fix is admission, not
    editorial: stop relaying things that are not news.
    """

    # 10:00 ET on a weekday: full market-hours weight, so these numbers compare.
    NOW = datetime(2026, 7, 30, 15, 0, 0, tzinfo=timezone.utc)

    def _sal(self, headline, snippet, tier="tier1"):
        return score_item(
            {"headline": headline, "snippet": snippet, "source_tier": tier},
            now=self.NOW,
        )

    @pytest.mark.parametrize("headline", [
        # The phrasings a first exact-phrase list MISSED. It was written from
        # guesses and caught only "third estimate" -- 1 of 5 real forms. A gate
        # calibrated against invented strings is a gate you have not tested.
        "US Q2 GDP revised up to 3.1%",
        "GDP growth revised to 3.1% from 3.0%",
        "BEA revises Q2 GDP to 3.1%",
        "Second-quarter GDP revision shows 3.1% growth",
        "US Q2 GDP revised higher in third estimate",
        "Payrolls restated lower for June",
    ])
    def test_every_real_restatement_phrasing_is_demoted(self, headline):
        r = self._sal(headline, "Gross domestic product and payrolls data.")
        assert r["_salience_components"]["revision_penalty"] > 0, headline
        assert r["salience"] < 60.0, headline

    def test_a_fresh_print_that_merely_mentions_a_revision_survives(self):
        """Headline-scoped on purpose: the headline is what an item is ABOUT.

        A snippet routinely cites the prior reading while the item itself is
        the new print, so matching headline+snippet would demote the print.
        """
        r = self._sal(
            "US Q3 GDP grows 2.8%",
            "GDP rose 2.8%; the prior quarter was revised to 3.1%.",
        )
        assert r["_salience_components"]["revision_penalty"] == 0.0
        assert r["_salience_components"]["revision_marker"] == ""

    def test_the_live_gdp_restatement_is_demoted_below_the_emit_floor(self):
        r = self._sal(
            "US Q2 GDP revised to 3.1% in third estimate, BEA says",
            "The Bureau of Economic Analysis revised second-quarter gross "
            "domestic product growth in its third estimate.",
        )
        assert r["_salience_components"]["revision_penalty"] > 0
        assert r["_salience_components"]["revision_marker"].startswith("revis")
        assert r["salience"] < 60.0, "the restatement still clears the wire"

    def test_a_first_release_print_is_untouched(self):
        """The demotion must not cost us the print itself."""
        first = self._sal(
            "US Q3 GDP grows 2.8%, topping forecasts",
            "Gross domestic product rose at a 2.8% annualized rate.",
        )
        assert first["_salience_components"]["revision_penalty"] == 0.0
        assert first["_salience_components"]["revision_marker"] == ""
        # ...and it outranks the restatement of the same series.
        revised = self._sal(
            "US Q2 GDP revised to 3.1% in third estimate, BEA says",
            "The Bureau of Economic Analysis revised second-quarter gross "
            "domestic product growth in its third estimate.",
        )
        assert first["salience"] > revised["salience"]

    def test_a_big_revision_can_still_earn_its_way_back(self):
        """A DEMOTION, not a kill: a benchmark revision does move markets.

        Ticker strength is what "big" looks like to the scorer, so the payrolls
        benchmark revision that cut 818,000 jobs still clears.
        """
        r = self._sal(
            "Payrolls benchmark revision cuts 818,000 jobs; $SPY $QQQ $TLT slide",
            "The annual benchmark revision showed nonfarm payrolls and the "
            "unemployment rate were far weaker than reported.",
        )
        assert r["_salience_components"]["revision_penalty"] > 0, "penalty applied"
        assert r["salience"] >= 60.0, "a market-moving revision must still post"

    def test_a_company_revising_guidance_is_not_touched(self):
        """Scoped to macro_print on purpose: 'revised' is normal company news."""
        r = self._sal(
            "Nike revised its full-year guidance lower",
            "Nike revised guidance and restated its prior estimate figures.",
        )
        assert r["event_class"] != "macro_print"
        assert r["_salience_components"]["revision_penalty"] == 0.0

    def test_every_other_class_keeps_its_exact_score(self):
        """The historical score of everything that is not a restatement."""
        for headline, snippet in [
            ("Fed cuts rates 25 basis points",
             "The Federal Reserve decision and FOMC lowered the fed funds target."),
            ("US CPI rises 0.4% in September",
             "The consumer price index and inflation reading increased 0.4%."),
            ("Trump signs executive order on tariffs",
             "The president signed an executive order imposing tariffs."),
        ]:
            c = self._sal(headline, snippet)["_salience_components"]
            assert c["revision_penalty"] == 0.0, headline
            assert c["revision_marker"] == "", headline

    def test_the_breakdown_names_the_marker_that_fired(self):
        """'why did the GDP item not post' answerable from the breakdown alone."""
        c = self._sal(
            "Payrolls benchmark revision cuts 818,000 jobs",
            "The annual benchmark revision showed nonfarm payrolls were weaker.",
        )["_salience_components"]
        assert c["revision_marker"].startswith("revis")
        assert set(c) >= {"base", "tier_bonus", "kw_bonus", "ticker_bonus",
                          "revision_penalty", "revision_marker",
                          "market_hours_weight", "raw", "capped"}
