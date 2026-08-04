"""tests/test_marketing_relay_hygiene.py — THE SOURCE'S PAGE IS NOT OUR POST.

Fixture-driven; ZERO live network, ZERO live LLM.

THE LIVE POSTS. ForexLive/InvestingLive was armed as a `tier: wire` RSS feed on
2026-08-03 (#4352). In its first ~30 hours it produced FOUR outbox items and
THREE carried a defect — every one of them the source's own page conventions
relayed verbatim:

  1. ob-2026-08-04-5b059eea4a  (posted to @mastermindx001)
     "More info on this - South Korea core inflation hits 2-1/2 year high
      despite headline cooling -- wire reports"
     A DANGLING REFERENCE. "More info on this -" is their headline prefix for a
     follow-up to their own earlier post; off their site "this" points nowhere.

  2. ob-2026-08-03-7d40131982
     "investingLive Americas FX news wrap 31 Jul; It's a wrap for the month of
      July -- wire reports"
     THE PUBLISHER'S BRAND in our body. The de-handling law screens "@handles",
     so a bare brand walked through — and the configured display name is
     "ForexLive" while the site now writes "investingLive", so even a
     display-name check would have missed it.

  3. ob-2026-08-03-fffec5dc90
     "China private survey July manufacturing PMI 50.9 (expected 51.5, prior
      51.7)" + "On the wires: I'll have more to come on this separately,
      details etc."
     THEIR AUTHOR'S FIRST PERSON as our line 2, promising a follow-up we were
     never going to write — and it passed the restatement gate as ADDITIVE,
     because that gate counts lexically novel tokens and filler is novel.

WHAT IS PINNED, and the mutation each pin is armed against:
  1. The pointer is SCRUBBED, not dropped — the story survives, and the
     publisher's original headline survives as `headline_source`.
  2. A scrub may never empty a headline or leave a fragment.
  3. Prose that merely CONTAINS a marker word ("more information reaches the
     market slowly") is untouched — the separator is what makes it a pointer.
  4. Furniture DROPS: calendars, house wraps, "what are the main events".
  5. A DATE is not a market reading — the escape that rescues "Markets wrap:
     S&P closes -1.8%" must not rescue "...wrap 3 Aug".
  6. The brand check reads the URL HOST, so a rebrand needs no config edit.
  7. First person and page-artifact references are caught in headline AND body.
  8. The deterministic lead scan skips a first sentence that does not fit
     instead of discarding the whole paragraph — and never truncates one.
  9. restatement_verdict calls filler what it is.
 10. End-to-end: the exact live post text cannot be reconstructed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
sys.path.insert(0, str(ROOT))

from engine.marketing import breaking_summary as bs  # noqa: E402
from engine.marketing import garbage_gate as gg  # noqa: E402
from engine.marketing import relay_hygiene as rh  # noqa: E402
from engine.marketing import wire_format as wf  # noqa: E402

# The three live defects, verbatim.
LIVE_POINTER = ("More info on this - South Korea core inflation hits 2-1/2 year "
                "high despite headline cooling")
LIVE_BRANDED_WRAP = ("investingLive Americas FX news wrap 31 Jul; It's a wrap for "
                     "the month of July")
LIVE_FIRST_PERSON = "I'll have more to come on this separately, details etc."
LIVE_CHINA_HEAD = ("China private survey July manufacturing PMI 50.9 "
                   "(expected 51.5, prior 51.7)")


# ── 1-3. The scrub: repair, don't delete ─────────────────────────────────────

class TestScrub:
    def test_live_pointer_is_scrubbed_to_the_real_story(self):
        cleaned, marks = rh.scrub_headline(LIVE_POINTER)
        assert cleaned == ("South Korea core inflation hits 2-1/2 year high "
                           "despite headline cooling")
        assert "lead_pointer" in marks

    def test_clean_item_keeps_the_publishers_original_headline(self):
        """An edit to someone else's words has to be visible from the outbox."""
        res = rh.clean_item({"headline": LIVE_POINTER, "source_name": "ForexLive"})
        assert res["scrubbed"] is True
        assert res["item"]["headline_source"] == LIVE_POINTER
        assert res["item"]["headline"] != LIVE_POINTER
        assert res["drop"] == ""      # the story survives

    @pytest.mark.parametrize("text", [
        "ICYMI - More on this - Fed holds rates steady at 4.25%",
        "More info on this: Japan CPI accelerates to 3.1% in July",
        "Read more — Germany factory orders fall 2.4% in June",
    ])
    def test_stacked_and_varied_pointers_collapse(self, text):
        cleaned, marks = rh.scrub_headline(text)
        assert marks
        assert not cleaned.lower().startswith(("icymi", "more info", "more on", "read more"))
        assert len(cleaned.split()) >= 4

    def test_a_scrub_never_empties_a_headline(self):
        """A headline that is ONLY a pointer is handed back untouched — the DROP
        path owns it. If these two rules could hand each other an empty string
        the lane would emit a bald attribution clause."""
        for bare in ("More info on this", "ICYMI", "More on this -"):
            cleaned, marks = rh.scrub_headline(bare)
            assert cleaned == bare
            assert marks == []
            assert rh.headline_is_furniture(bare) == "bare_pointer"

    def test_a_scrub_never_leaves_a_fragment(self):
        cleaned, marks = rh.scrub_headline("More info on this - here")
        assert cleaned == "More info on this - here"
        assert marks == []

    @pytest.mark.parametrize("prose", [
        "More information reaches the market slowly, ECB study finds",
        "Investors read more into the dot plot than the Fed intended",
        "This is the last chance, Trump says",
    ])
    def test_prose_that_merely_contains_a_marker_is_untouched(self, prose):
        """THE SEPARATOR IS THE RULE. Without it these are sentences, not
        pointers, and a scrub here would rewrite real headlines."""
        cleaned, marks = rh.scrub_headline(prose)
        assert cleaned == prose
        assert marks == []


# ── 4-6. Furniture drops ──────────────────────────────────────────────────────

class TestFurniture:
    @pytest.mark.parametrize("headline", [
        "What are the main events for today?",
        "Economic and event calendar in Asia Tuesday, August 4, 2026 - a light one",
        "Market moving news for Asian trading on 3 August: Oil slumps on Trump's Iran claims",
    ])
    def test_house_furniture_drops(self, headline):
        assert rh.headline_is_furniture(headline).startswith("furniture:")

    def test_a_date_is_not_a_market_reading(self):
        """REGRESSION. The escape used to be a bare `\\d` search, and every dated
        house post walked through it — all three headlines above carry digits."""
        dated = "investingLive Americas FX news wrap 3 Aug"
        assert rh.headline_is_furniture(dated, source_name="ForexLive",
                                        url="https://investinglive.com/news/x")
        assert not rh._MARKET_FIGURE_RE.search("calendar in Asia Tuesday, August 4, 2026")

    def test_a_wrap_carrying_a_real_reading_survives(self):
        """The escape has to keep working: an unbranded wrap with a print in its
        title is a story, and over-dropping is how a hygiene rule eats the wire."""
        assert rh.headline_is_furniture("Markets wrap: S&P closes -1.8%") == ""

    def test_the_brand_check_reads_the_url_host(self):
        """Config says "ForexLive"; the site writes "investingLive" and
        forexlive.com 301s to investinglive.com. Matching the display name alone
        missed every branded wrap the feed produced."""
        assert rh.self_brand_hit(LIVE_BRANDED_WRAP, "ForexLive") == ""
        assert rh.self_brand_hit(
            LIVE_BRANDED_WRAP, "ForexLive",
            url="https://investinglive.com/news/x") == "investinglive"

    def test_live_branded_wrap_drops_end_to_end(self):
        res = rh.clean_item({
            "headline": LIVE_BRANDED_WRAP, "source_name": "ForexLive",
            "url": "https://investinglive.com/news/investinglive-americas-fx-news-wrap",
        })
        assert res["drop"].startswith("branded_furniture:")

    def test_a_branded_wrap_is_furniture_even_with_a_print(self):
        """Their masthead, their number, their editorial line — the market-figure
        escape must never rescue a column that carries someone else's brand."""
        assert rh.headline_is_furniture(
            "investingLive markets wrap: S&P closes -1.8%",
            source_name="ForexLive", url="https://investinglive.com/x",
        ).startswith("branded_furniture:")


# ── 7. Somebody else's voice ─────────────────────────────────────────────────

class TestForeignVoice:
    def test_live_first_person_body_is_a_defect(self):
        assert "first_person" in rh.body_defects(LIVE_FIRST_PERSON)

    @pytest.mark.parametrize("text,slug", [
        ("Trump is on TruthSocial (I assume it is not the $100,000 one)", "first_person"),
        ("As noted in the screenshot, the calendar is light", "page_artifact"),
        ("See the chart below for the breakdown", "page_artifact"),
        ("Stay tuned for the full breakdown", "first_person"),
    ])
    def test_page_voice_markers(self, text, slug):
        assert slug in rh.body_defects(text)

    @pytest.mark.parametrize("clean", [
        "The Bank of Korea resumed hiking last month and flagged more to come",
        "The SNB signalled more to come after the July cut",
        "US inflation numbers have been fantastic, Hassett said",
        "Prior month 53.3, prices paid 71.1",
        "Investors read more into the dot plot than the Fed intended",
    ])
    def test_ordinary_wire_prose_is_clean(self, clean):
        """OVER-DROPPING IS THE FAILURE MODE OF A HYGIENE RULE.

        The first two fixtures are the ones that caught a real over-fire while
        this module was being written: "flagged more to come" is a central bank
        signalling further hikes — a genuine story that the marker list would
        have deleted to fix a cosmetic defect. A promise is the AUTHOR'S only
        when it stands as its own clause; with a verb in front of it the subject
        is whoever the sentence is about."""
        assert rh.body_defects(clean) == []

    def test_the_authors_own_promise_still_fires(self):
        """...and the narrowing must not disarm the live defect it was for."""
        assert "author_promise" in rh.body_defects("More to come on this separately.")
        assert "author_promise" in rh.body_defects("Details below. More to come.")


# ── 8. The lead scan: skip, never truncate ───────────────────────────────────

class TestLeadScan:
    #: The real ForexLive snippet. Sentence 1 is 274 chars against a 200 cap, so
    #: the old first-sentence-or-nothing rule discarded the WHOLE paragraph and
    #: relayed the raw RSS title instead. On the live feed that bit 12 of 25.
    RICH_SNIPPET = (
        "The undershoot on both headline and monthly CPI is likely to be read as "
        "giving the Bank of Korea some breathing room, even as the vice finance "
        "minister's comments on persistent upward pressures suggest policymakers "
        "are not treating the softer print as a green light to ease. Core CPI rose "
        "at its fastest pace in two and a half years. With the central bank having "
        "only just resumed hiking, that matters."
    )

    def test_a_long_first_sentence_no_longer_discards_the_paragraph(self):
        lead = bs._det_lead_sentence({
            "headline": "South Korea core inflation hits 2-1/2 year high",
            "body_snippet": self.RICH_SNIPPET,
        })
        assert lead == "Core CPI rose at its fastest pace in two and a half years."

    def test_the_scan_never_truncates(self):
        """Cutting at a clause boundary is how a conditional loses its condition.
        Whatever comes back must be a WHOLE sentence from the source."""
        lead = bs._det_lead_sentence({
            "headline": "X", "body_snippet": self.RICH_SNIPPET,
        })
        assert lead in self.RICH_SNIPPET
        assert lead.endswith((".", "!", "?"))

    def test_the_scan_skips_the_sources_own_page_voice(self):
        """The one path that puts SOURCE PROSE into a post is the one path that
        has to screen for prose written to a page we are not on."""
        lead = bs._det_lead_sentence({
            "headline": LIVE_CHINA_HEAD,
            "body_snippet": LIVE_FIRST_PERSON + " Caixin PMI beat consensus by 0.6.",
        })
        assert "I'll" not in lead
        assert lead == "Caixin PMI beat consensus by 0.6."

    def test_no_usable_sentence_still_returns_empty(self):
        assert bs._det_lead_sentence({"headline": "X", "body_snippet": ""}) == ""
        assert bs._det_lead_sentence({"headline": "X", "body_snippet": "Too short."}) == ""


# ── 9. Novelty is not substance ──────────────────────────────────────────────

class TestRestatementSubstance:
    def test_the_live_filler_line_no_longer_reads_as_additive(self):
        """REGRESSION, the exact live pair. Six novel tokens, zero overlap with
        line 1 — the gate called it additive and shipped it."""
        verdict = wf.restatement_verdict(
            LIVE_CHINA_HEAD, f"On the wires: {LIVE_FIRST_PERSON}",
            opener="On the wires:",
        )
        assert verdict["restates"] is True
        assert "page voice" in verdict["reason"]

    def test_the_short_form_drops_the_filler_line(self):
        shape = wf.wire_post_shape(
            LIVE_CHINA_HEAD, f"On the wires: {LIVE_FIRST_PERSON}",
            opener="On the wires:",
        )
        assert shape["shape"] == "short_form"
        assert "more to come" not in shape["body"].lower()

    def test_a_line_of_pure_filler_is_not_additive(self):
        verdict = wf.restatement_verdict(
            "US ISM Manufacturing PMI for July 55.6 versus 54.0 estimate",
            "More details here soon, full story below.",
        )
        assert verdict["restates"] is True

    def test_a_real_second_datum_is_still_additive(self):
        """The gate must keep passing what it exists to pass."""
        verdict = wf.restatement_verdict(
            "US ISM Manufacturing PMI for July 55.6 versus 54.0 estimate",
            "Prior month 53.3; prices paid 71.1, the highest since March.",
        )
        assert verdict["restates"] is False


# ── 10. End to end ───────────────────────────────────────────────────────────

class TestTheLivePostCannotBeRebuilt:
    def test_the_exact_posted_string_is_unreachable(self):
        """The one that reached the timeline on 2026-08-04, byte for byte."""
        item = {
            "id": "50a333cb", "source": "forexlive_news", "source_name": "ForexLive",
            "source_tier": "wire", "event_class": "macro_print",
            "corroboration_class": "hearsay",
            "url": ("https://investinglive.com/news/more-info-on-this-south-korea-"
                    "core-inflation-hits-2-1-2-year-high-despite-headline-cooling/"),
            "headline": LIVE_POINTER, "body_snippet": TestLeadScan.RICH_SNIPPET,
        }
        scrubbed = gg.scrub(item)
        assert scrubbed["drop"] == ""
        cleaned = scrubbed["item"]
        assert not cleaned["headline"].lower().startswith("more info")

        from engine.marketing import source_authority as sa
        from engine.marketing.press_corroboration import corroboration_decision
        decision = corroboration_decision(cleaned, corroborated_sources=1,
                                          window_ok=False)
        resolved = sa.resolve_attribution(cleaned, decision)
        # No masthead a reader would know -> no credit clause at all.
        assert resolved["attribution"] == ""
        assert resolved["tier"] == "unnamed"
        # ...and the item is a published print, so it still posts.
        assert resolved["gate"] != "digest"

        body = bs._deterministic_summary(cleaned).rsplit(" -- ", 1)[0]
        shape = wf.wire_post_shape(cleaned["headline"], body, opener="",
                                   attribution=resolved["attribution"])
        posted = shape["body"] if shape["shape"] == "short_form" else shape["headline"]
        assert "More info on this" not in posted
        assert "wire reports" not in posted


# ── 11. The last gate: the queue is not a bypass ─────────────────────────────

class TestTheQueueIsNotABypass:
    """THE MEASUREMENT THAT FORCED THIS SCREEN (2026-08-04).

    The outbox held 308 queued items reaching back ELEVEN days, and content laws
    run at COMPOSE time. Five of those items still carried a foreign "@handle"
    banned on 2026-08-02 — the generator fix never touched them, because a fix to
    the writer cannot reach copy already written. The relay laws in this file
    would have had exactly the same blind spot.

    Fixing the generator fixes tomorrow's posts. Only a last gate fixes the
    queue, and the queue is what reaches the timeline.
    """

    def test_the_live_post_is_caught_at_post_time_too(self):
        from engine.marketing.copywriter import queued_relay_violations
        v = queued_relay_violations(f"{LIVE_POINTER} -- wire reports")
        assert v and "lead_pointer" in v[0]

    def test_a_queue_vintage_handle_is_caught(self):
        """The five that were still sitting in the queue on 2026-08-04."""
        from engine.marketing.copywriter import queued_relay_violations
        v = queued_relay_violations(
            "GOLD ROSE 0.6% TO $4,070 -- @FirstSquawk reporting")
        assert v and "foreign handle" in v[0]

    def test_a_clean_wire_post_passes(self):
        from engine.marketing.copywriter import queued_relay_violations
        assert queued_relay_violations(
            "US ISM Manufacturing PMI for July 55.6 versus 54.0 estimate") == []

    def test_the_screen_is_scoped_to_relayed_lanes_only(self):
        """THE MOST DANGEROUS PROPERTY OF THIS CHANGE, pinned.

        Our own desks write in the first person deliberately — "I'd rather wait"
        is the house voice the operator approved on 2026-07-30, and 46 queued
        items carried it. These rules ask "was this written for a reader on
        somebody else's page", which is only a defect when it CAME from somebody
        else's page. Pointed at content_studio or weekend_levels this screen
        would quarantine the marketing voice wholesale.

        So the allowlist is the safety property, and an unknown provenance is
        NOT screened. Both halves are asserted: the house voice DOES trip the
        raw rule (which is why scoping is required, not optional), and the
        publisher's allowlist does not contain the lanes that write it.
        """
        from engine.marketing.copywriter import queued_relay_violations
        house = ("$AAPL into the week\n\nUp at 52-week highs. Nothing broken "
                 "here, and I'd rather wait.")
        assert queued_relay_violations(house), \
            "if this ever passes, the scoping test below is measuring nothing"

        src = (ROOT / "scripts" / "marketing_publisher.py").read_text(encoding="utf-8")
        import re as _re
        block = _re.search(r"_RELAYED_PROVENANCES:[^=]*=\s*frozenset\(\{(.*?)\}\)",
                           src, _re.S)
        assert block, "the publisher's relay-lane allowlist went missing"
        allow = block.group(1)
        for own_lane in ("content_studio", "weekend_levels", "claude_rewrite",
                         "publisher_live_movers"):
            assert own_lane not in allow, (
                f"{own_lane} writes in the house voice and must never be "
                "screened by the relay rules")
        assert "press_lane" in allow
