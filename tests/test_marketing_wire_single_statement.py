"""A wire-relay post ships ONE statement, never the same sentence twice.

Operator defect, verified live 2026-08-02: the POST TEXT (not the card — that
half was fixed the same day) still printed the statement twice:

    GOLD ROSE ABOUT 0.6% TO AROUND $4,070 AN OUNCE AFTER TRUMP SAID FRESH IRAN
    TALKS WOULD BEGIN LATER MONDAY, RAISING HOPES

    New this hour: GOLD ROSE ABOUT 0.6% TO AROUND $4,070 AN OUNCE AFTER ...

The cause chain, end to end: an X-relay item arrives with ``headline =
snippet[:120]`` and ``body_snippet`` = the same snippet
(press_providers.TwitterApiIoProvider.parse_tweets); the deterministic
summarizer's echo guard (breaking_summary._det_lead_sentence) rejects the lead
for restating the headline and _deterministic_summary falls back to
``"{headline} -- {source}"`` — the headline again; outbox.compose_text then
joins ``headline + blank line + body``. The guard built to stop the doubled
post was the thing producing it.

THE FIX, pinned here in three layers:

  1. breaking_summary.headline_earns_its_line — the post-text sibling of
     summary_earns_the_card (same containment measure, same threshold).
  2. wire_format.clamp_for_x rung 0 — when the body already says the headline,
     the headline line is dropped regardless of length and the post ships as
     ONE statement: the BODY, which keeps the opener, the corroboration credit
     and the tape stamp, and is the exact string the news rail displays.
     (Dropping the body instead would discard all three for a bare relay.)
  3. breaking_summary._det_lead_sentence truncation carve-out — when the
     headline is a TRUNCATION of the lead (the snippet[:120] shape), the lead
     is the same statement COMPLETED, so it is relayed; the old rejection
     preferred the cut-off form over the complete sentence in the packet.

The end-to-end fixtures are the REAL posts (@FirstSquawk gold,
@financialjuice S. Korea trade balance), ingested through the REAL parser so
the shape under test is the shape production sees. Every pin below was
mutation-checked: the production change reverted, the test observed to FAIL,
the change restored.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from engine.marketing import wire_format as wf
from engine.marketing.breaking_summary import (
    _det_lead_sentence,
    headline_earns_its_line,
    summarize_item,
)
from engine.marketing.press_providers import TwitterApiIoProvider

ROOT = Path(__file__).resolve().parent.parent

# ── The real posts (@mastermindx001 relays, 2026-08-02/03) ───────────────────

GOLD_TWEET = (
    "GOLD ROSE ABOUT 0.6% TO AROUND $4,070 AN OUNCE AFTER TRUMP SAID FRESH "
    "IRAN TALKS WOULD BEGIN LATER MONDAY, RAISING HOPES"
)
KOREA_TWEET = (
    "S. KOREAN TRADE BALANCE PRELIM ACTUAL 30.32B (FORECAST 29.487B, "
    "PREVIOUS 36.09B) $MACRO"
)

# The operator's named GOOD case (post = the terms, card/headline = the quote):
# two genuinely different statements that must BOTH keep shipping.
TRUTH_HEAD = (
    "The U.S.A. is locked and loaded and ready to go against the Islamic "
    "Republic of Iran, at levels of Military Terror, Strength, and Power not "
    "previously seen."
)
TRUTH_BODY = (
    "The U.S. has agreed to cancel a planned attack on Iran after being asked "
    "to hold off while deal parameters are negotiated. -- on Truth Social"
)

# A single-sentence tweet LONGER than the 120-char headline slice — the shape
# where the echo guard used to prefer the truncation over the full sentence.
LONG_TWEET = GOLD_TWEET + " OF DE-ESCALATION ACROSS THE GULF REGION."
assert len(GOLD_TWEET) == 120, "fixture drift: gold tweet is the exact slice"
assert len(LONG_TWEET) > 120


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — the predicate
# ─────────────────────────────────────────────────────────────────────────────

class TestHeadlineEarnsItsLine:
    def test_the_relay_echo_pair_earns_nothing(self):
        """headline == the statement inside the body: the doubled-post shape."""
        body = f"New this hour: {GOLD_TWEET} -- wire reports"
        assert headline_earns_its_line(GOLD_TWEET, body) is False

    def test_a_truncated_headline_still_earns_nothing(self):
        """headline = snippet[:120] against a body carrying the full sentence."""
        body = f"Now crossing. {LONG_TWEET} -- wire reports"
        assert headline_earns_its_line(LONG_TWEET[:120], body) is False

    def test_two_genuinely_different_statements_both_earn_their_place(self):
        assert headline_earns_its_line(TRUTH_HEAD, TRUTH_BODY) is True

    def test_empty_sides(self):
        # No headline -> no line to earn; no body -> the headline is the post.
        assert headline_earns_its_line("", TRUTH_BODY) is False
        assert headline_earns_its_line(TRUTH_HEAD, "") is True
        assert headline_earns_its_line("", "") is False


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — the clamp's redundancy rung
# ─────────────────────────────────────────────────────────────────────────────

class TestClampShipsOneStatement:
    def test_a_restating_pair_ships_the_body_alone_even_under_cap(self):
        """THE DEFECT: the doubled gold post was 277 chars — it FIT, and it
        shipped doubled. The rung is about redundancy, not length."""
        body = f"New this hour: {GOLD_TWEET} -- wire reports"
        joined = f"{GOLD_TWEET}\n\n{body}"
        assert len(joined) <= wf.X_POST_MAX_CHARS, "fixture drift: must fit"
        out = wf.clamp_for_x(GOLD_TWEET, body)
        assert out["text"] == body
        assert out["clamped"] is True
        assert "one statement" in out["reason"]

    def test_the_statement_appears_exactly_once(self):
        body = f"On the tape: {KOREA_TWEET} -- wire reports"
        out = wf.clamp_for_x(KOREA_TWEET, body)
        assert out["text"].count("30.32B") == 1
        assert out["text"].count("$MACRO") == 1

    def test_two_distinct_statements_still_ship_joined(self):
        """The rung must not blanket-drop every headline: the good case keeps
        both halves (this is the pin that fails if the predicate's direction
        is ever inverted)."""
        head = "Fed holds rates steady at the July meeting"
        body = ("Policymakers left the target range untouched and flagged "
                "supply, not demand, as the binding constraint. -- Reuters "
                "reporting")
        out = wf.clamp_for_x(head, body)
        assert out["text"] == f"{head}\n\n{body}"
        assert out["clamped"] is False

    def test_a_restating_pair_with_an_over_cap_body_still_trims_to_sentences(self):
        """Rung 0 hands over to the existing body-only rungs, not to a bypass:
        an over-cap restating body still lands on the whole-sentence trim with
        its attribution tail intact."""
        s1 = ("Gold rose about 0.6% to around $4,070 an ounce after fresh "
              "talks were announced for later Monday in the Gulf.")
        s2 = ("Dealers in three hubs described positioning as light into the "
              "session, with the metal holding its overnight range so far.")
        s3 = ("Options desks reported steady two-way flow through the morning "
              "with no unusual size in either direction on the day.")
        body = f"{s1} {s2} {s3} -- wire reports"
        assert len(body) > wf.X_POST_MAX_CHARS
        out = wf.clamp_for_x(s1[:120], body, attribution="wire reports")
        assert out["text"], "the trim rung must still produce a post"
        assert len(out["text"]) <= wf.X_POST_MAX_CHARS
        assert out["text"].endswith(" -- wire reports")
        assert out["text"].count("$4,070") == 1

    def test_a_headline_only_item_still_ships(self):
        out = wf.clamp_for_x(GOLD_TWEET, "")
        assert out["text"] == GOLD_TWEET
        assert out["clamped"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3 — the truncation carve-out in the echo guard
# ─────────────────────────────────────────────────────────────────────────────

class TestTruncationRepair:
    def _item(self, tweet: str) -> dict:
        """The exact X-relay packet shape parse_tweets builds."""
        return {"headline": tweet[:120], "body_snippet": tweet,
                "source_name": "Newswire"}

    def test_the_lead_completes_a_truncated_headline(self):
        """The packet carries the COMPLETE sentence; the relay must prefer it
        over the [:120] slice instead of falling back to the cut-off form."""
        lead = _det_lead_sentence(self._item(LONG_TWEET))
        assert lead == LONG_TWEET
        assert lead.endswith("ACROSS THE GULF REGION.")

    def test_the_deterministic_summary_carries_the_complete_sentence(self):
        result = summarize_item(
            self._item(LONG_TWEET), {"breaking": {"llm": {"enabled": False}}})
        assert result["mode"] == "deterministic"
        assert result["summary"] == f"{LONG_TWEET} -- Newswire"

    def test_a_mid_word_cut_is_also_repaired(self):
        tweet = GOLD_TWEET + " OF CALM RETURNING TO THE REGION SOON."
        item = {"headline": tweet[:126], "body_snippet": tweet,
                "source_name": "Newswire"}
        assert not tweet[:126].endswith(("HOPES", ".")), \
            "fixture drift: the slice must cut mid-clause"
        assert _det_lead_sentence(item) == tweet

    def test_a_trailing_period_is_an_echo_not_a_completion(self):
        """The pre-existing pin's shape, guarded here against THIS change: a
        body that adds only terminal punctuation gains nothing, so the echo
        guard still sends it back to the headline relay."""
        item = {"headline": "Treasury secretary says tariffs stay in place",
                "body_snippet": "Treasury secretary says tariffs stay in place.",
                "source_name": "Reuters"}
        assert _det_lead_sentence(item) == ""
        result = summarize_item(item, {"breaking": {"llm": {"enabled": False}}})
        assert result["summary"] == \
            "Treasury secretary says tariffs stay in place -- Reuters"

    def test_a_genuinely_different_headline_is_not_a_prefix(self):
        """An RSS item whose title differs from its body must not be caught by
        the carve-out — the ordinary lead path already handles it."""
        item = {"headline": "Fed holds rates steady",
                "body_snippet": "Policymakers left the target range untouched "
                                "and flagged supply, not demand, as the "
                                "binding constraint this year.",
                "source_name": "Reuters"}
        assert _det_lead_sentence(item) == item["body_snippet"]


# ─────────────────────────────────────────────────────────────────────────────
# End to end — the REAL posts, through the REAL parser and the REAL tick
# ─────────────────────────────────────────────────────────────────────────────

def _parse_relay(handle: str, text: str, tid: str) -> dict:
    """Ingest one real tweet through TwitterApiIoProvider.parse_tweets so the
    item under test carries the exact production shape (headline=snippet[:120],
    body_snippet=snippet, de-handled display name, x_handle intact)."""
    provider = TwitterApiIoProvider(
        {"handles": [{"handle": handle, "tier": "fast",
                      "corroboration_class": "hearsay"}],
         "poll_tiers": {"fast": 75}},
        spend_cap_usd=75.0,
    )
    items, _since = provider.parse_tweets(
        {"status": "success", "has_next_page": False,
         "tweets": [{"id": tid, "text": text,
                     "createdAt": "Mon Aug 03 00:12:00 +0000 2026"}]},
        {"handle": handle, "corroboration_class": "hearsay"},
        since_id=None,
    )
    assert len(items) == 1
    return items[0]


def _press_tick(items: list[dict]) -> dict:
    """Drive the real press tick (dry run), floors lowered so the fixtures
    genuinely reach emission — a skipped fixture is not a pin. The salience
    floors and the Gift-Grip-Proof gate are relevance/quality POLICY, not the
    copy shape under test, so the floors drop to zero and the value gate runs
    in shadow (verdicts still stamped, nothing blocked)."""
    from engine.marketing.press_lane import run_press_tick

    now = datetime(2026, 8, 3, 1, 0, tzinfo=timezone.utc)
    press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
    marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
    press_cfg.setdefault("wire", {})["flagship_salience_floor"] = 0.0
    press_cfg["wire"]["flagship_top_k_per_day"] = 50
    press_cfg["wire"]["rail_salience_floor"] = 0.0
    marketing_cfg.setdefault("value_gate", {})["enforce"] = False
    return run_press_tick(
        items, root=str(ROOT), now=now, cfg=marketing_cfg,
        press_cfg=press_cfg, state={}, seen_ids=set(), dry_run=True,
    )


class TestLivePostsShipOneStatement:
    def test_the_gold_relay_ships_once_and_uncredited(self):
        """THE CREDIT REQUIREMENT WAS RETIRED, 2026-08-04 (operator citation law).

        This test used to assert " -- " was present: every single-source item
        carried "-- wire reports", so a credit clause was universal. The operator
        ruling ended that — there is no masthead called Wire, and an X relay is
        someone else's account, so an unrecognisable source now gets NO credit
        rather than an anonymous one.

        The item still SHIPS: a gold price and a direction are checkable off the
        tape without trusting the relay (source_authority.self_evident). What is
        pinned here is the single-statement shape, which is what this file is
        for, plus the new invariant — no invented credit, no foreign handle.
        """
        item = _parse_relay("FirstSquawk", GOLD_TWEET, "1955000000000000001")
        res = _press_tick([item])
        emitted = [e for e in res["emitted"] if e.get("kind") == "breaking"]
        assert emitted, f"the gold relay must emit; skipped={res['skipped']}"
        for e in emitted:
            text = e["text"]
            # ONE statement — the doubled form carried it twice.
            assert text.count("RAISING HOPES") == 1, text
            assert text.count("GOLD ROSE ABOUT 0.6%") == 1, text
            # One paragraph: no headline line stacked over the body.
            assert "\n\n" not in text, text
            # No anonymous credit, and no handle — the two strings this lane
            # has actually shipped and must never ship again.
            assert "wire reports" not in text, text
            assert "@" not in text, text
            assert e["source"].get("citation_tier") == "unnamed", e["source"]
            # ...and the redundancy decision left an audit trail. It is the SHAPE
            # field now, not x_clamp: without the credit clause the composed post
            # no longer crosses 280, so the clamp never runs and has nothing to
            # record. The property that matters — this shipped as one statement
            # and we can say why — is unchanged.
            assert e["source"].get("post_shape") == "short_form", e["source"]
            assert e["source"].get("post_shape_reason"), e["source"]

    def test_the_korea_relay_ships_once(self):
        item = _parse_relay("financialjuice", KOREA_TWEET, "1955000000000000002")
        res = _press_tick([item])
        emitted = [e for e in res["emitted"] if e.get("kind") == "breaking"]
        assert emitted, f"the Korea relay must emit; skipped={res['skipped']}"
        for e in emitted:
            text = e["text"]
            assert text.count("30.32B") == 1, text
            assert text.count("$MACRO") == 1, text
            assert "\n\n" not in text, text

    def test_the_post_is_the_rail_text(self):
        """One string everywhere: the emitted post and the news-rail entry are
        the same statement — the property the body-only shape restores."""
        item = _parse_relay("FirstSquawk", GOLD_TWEET, "1955000000000000003")
        res = _press_tick([item])
        emitted = [e for e in res["emitted"] if e.get("kind") == "breaking"]
        assert emitted
        rail = {r["id"]: r for r in res.get("rail", [])}
        for e in emitted:
            fid = e["source"]["feed_item_id"]
            assert fid in rail
            assert rail[fid]["en"] == e["text"]

    def test_a_two_part_story_still_ships_both_halves(self):
        """Anti-blanket, end to end: an item whose body genuinely ADDS (the RSS
        title+description shape) keeps the joined form."""
        item = {
            "id": "distinct-1",
            "source": "wire_rss",
            "source_name": "Newswire",
            "source_tier": "aggregator",
            "url": "https://example.invalid/distinct-1",
            "published_at": "2026-08-03T00:12:02Z",
            # Carries a READING (2026-08-04). An uncreditable single source with
            # no checkable figure is now a digest item — correctly, since it has
            # nothing but its own say-so behind it — and a bare "Fed holds rates
            # steady" was that shape. Real FOMC wire copy carries the range, so
            # this fixture is closer to the traffic as well as reachable.
            "headline": "Fed holds rates steady at 4.25%-4.50% at the July meeting",
            "body_snippet": "Policymakers left the target range untouched and "
                            "flagged supply, not demand, as the binding "
                            "constraint this year.",
            "corroboration_class": "hearsay",
        }
        res = _press_tick([item])
        emitted = [e for e in res["emitted"] if e.get("kind") == "breaking"]
        assert emitted, f"the distinct item must emit; skipped={res['skipped']}"
        for e in emitted:
            text = e["text"]
            assert "\n\n" in text, text
            assert text.startswith("Fed holds rates steady"), text
            assert "target range untouched" in text, text
