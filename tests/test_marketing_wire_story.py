"""tests/test_marketing_wire_story.py — D1 acceptance: ONE EVENT, ONE POST.

Fixture-driven; ZERO live network, ZERO live LLM (MARKETING_LLM_ENABLED is never
set, so the summarizer stays on its deterministic path). Import closure is
stdlib + pyyaml so the thin marketing-engine CI lane stays green.

THE INCIDENT THESE FIXTURES ARE COPIED FROM (@mastermindx001, 2026-08-02). Four
posts inside one hour off ONE John Williams appearance, two off ONE Switzerland
CPI release, and — found in the outbox, not the screenshots — the same Williams
sentence twice because one feed sent CAPS and another sent title case. The
headlines below are the operator's, verbatim.

Every assertion names the defect it pins:

  D1-a  four headlines off one speech are ONE story        (speaker anchor)
  D1-b  two sub-prints of one release are ONE story        (indicator anchor)
  D1-c  a different indicator family SURVIVES              (the anti-over-collapse
                                                            constraint — a lane
                                                            that eats stories is
                                                            the same defect class)
  D1-d  CAPS vs title case is ONE story, on NORMALISATION
        alone, before any clustering runs
  D1-e  unrelated stories an hour apart BOTH emit          (window + anchor)
  D1-f  every suppression is COUNTED and WARNED at line
        start, and names the sibling it merged into

MUTATION CHECK (see TestTheGateIsLoadBearing): flipping `wire.story.enabled` to
false is the pre-fix code path, and it restores all four posts. Every end-to-end
assertion here is red under that flip.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
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

from engine.marketing import wire_story as ws  # noqa: E402
from engine.marketing.press_lane import run_press_tick  # noqa: E402

NOW = datetime(2026, 8, 2, 14, 30, tzinfo=timezone.utc)

# ── The operator's four Williams headlines, verbatim ─────────────────────────
WILLIAMS = (
    "Fed's Williams: central bank very committed to returning inflation to 2%",
    "Fed's Williams: rate policy still well positioned to reach 2% inflation",
    "Fed's Williams sees inflation coming down in H2 and more next year",
    "Fed's Williams: If inflation is not on track to 2%, action is appropriate - Sources",
)

# The pair that shipped twice because two feeds disagreed about capitalisation.
CAPS = "FED'S WILLIAMS: RATE POLICY STILL WELL POSITIONED TO REACH 2% INFLATION"
TITLE = "Fed's Williams: rate policy still well positioned to reach 2% inflation"

# Two sub-prints of ONE Switzerland release, plus the German print that must live.
CH_CORE = "Switzerland CPI Core YoY (Jul): 0.7% vs 0.6% prev"
CH_HICP = "Switzerland CPI EU-Harmonized MoM (Jul): -0.1% vs 0.2% prev"
DE_RETAIL = "Germany Retail Sales MoM (Jun): 1.0% vs -1.6% prev"


def _item(iid: str, headline: str, *, source: str | None = None,
          now: datetime = NOW, **extra) -> dict:
    row = {
        "id": iid,
        "source": source or iid,
        "source_name": source or iid,
        "source_tier": "wire",
        "url": f"https://wire.example/{iid}",
        "published_at": now.isoformat(),
        "headline": headline,
        # A REAL PACKET, not an echo of its own headline (W2E, 2026-08-11): a
        # body that repeats the headline leaves the deterministic summarizer with
        # nothing to relay, and compose-or-drop now refuses that item rather than
        # posting the provider's sentence. These tests are about STORY COLLAPSE,
        # so the packet has to survive long enough to claim a story.
        "body_snippet": f"{headline}. The release landed on schedule and the "
                        f"desk logged it against the prior print.",
        "corroboration_class": "hearsay",
    }
    row.update(extra)
    return row


def _press_cfg(**story) -> dict:
    return {"satire_blocklist": [],
            "wire": {"flagship_top_k_per_day": 10,
                     "flagship_salience_floor": 10.0,
                     "voice": {"enabled": False},
                     "tape": {"enabled": False},
                     "story": story}}


def _marketing_cfg() -> dict:
    return {"breaking": {"salience_threshold": 60, "llm": {"enabled": False},
                         "scoring": {}, "garbage_gate": {"enabled": True}}}


def _run(items, tmp_path, *, state=None, now=NOW, press_cfg=None):
    return run_press_tick(
        items, root=tmp_path, now=now, cfg=_marketing_cfg(),
        press_cfg=press_cfg or _press_cfg(),
        state=state if state is not None else {},
        seen_ids=set(), dry_run=True,
    )


def _emitted_feed_ids(result) -> list[str]:
    """Feed ids of the items that actually reached the queue."""
    return [str((row.get("source") or {}).get("feed_item_id", ""))
            for row in result["emitted"]]


# ═════════════════════════════════════════════════════════════════════════════
# 1. NORMALISATION — the CAPS duplicate must die here, before any clustering
# ═════════════════════════════════════════════════════════════════════════════

class TestNormalisation:
    def test_caps_and_title_case_are_one_string(self):
        """D1-d. The duplicate pair collapses on NORMALISATION ALONE.

        This is the assertion that pins the two-cases-one-sentence half of the
        incident: it does not touch the speaker parser, the topic map, the
        ledger or the window. If only this line held, that duplicate could not
        have shipped.
        """
        assert ws.normalize_headline(CAPS) == ws.normalize_headline(TITLE)

    def test_the_trailing_source_clause_is_stripped(self):
        """Williams #4 ends '- Sources' and its siblings do not."""
        assert ws.normalize_headline("Fed to act if needed - Sources") == \
            ws.normalize_headline("Fed to act if needed")
        assert ws.normalize_headline("ECB holds (Reuters)") == \
            ws.normalize_headline("ECB holds")
        assert ws.normalize_headline("Trade deal near -- @FirstSquawk") == \
            ws.normalize_headline("Trade deal near")

    def test_curly_punctuation_folds_to_ascii(self):
        assert ws.normalize_headline("Fed’s Williams — on track") == \
            ws.normalize_headline("Fed's Williams - on track")

    def test_leading_wire_furniture_is_stripped(self):
        """One feed shouts BREAKING where its sibling does not."""
        assert ws.normalize_headline("BREAKING: Gold hits a record") == \
            ws.normalize_headline("Gold hits a record")
        assert ws.normalize_headline("UPDATE 1: Gold hits a record") == \
            ws.normalize_headline("Gold hits a record")

    def test_normalisation_does_not_merge_different_sentences(self):
        """The floor under all of it: normalisation is not similarity."""
        assert ws.normalize_headline(CH_CORE) != ws.normalize_headline(DE_RETAIL)


# ═════════════════════════════════════════════════════════════════════════════
# 2. THE STORY KEY — speaker / indicator / text anchors
# ═════════════════════════════════════════════════════════════════════════════

class TestStoryKey:
    def test_the_four_williams_headlines_are_one_story(self):
        """D1-a. Four feed ids, one appearance, one key.

        Note WHAT would break this: headline #2 leads on rate policy and the
        other three lead on inflation, so a topic map that split rates from
        inflation would re-open the defect at exactly one post.
        """
        keys = {ws.story_key({"headline": h}).key for h in WILLIAMS}
        assert len(keys) == 1, keys
        assert keys == {"story:speaker:fed/williams:monetary"}

    def test_the_caps_pair_is_one_story(self):
        """D1-d, at the key layer as well as the normalisation layer."""
        assert ws.story_key({"headline": CAPS}).key == \
            ws.story_key({"headline": TITLE}).key

    def test_the_switzerland_subprints_are_one_story(self):
        """D1-b. Core YoY and the EU-harmonized MoM are one release."""
        a = ws.story_key({"headline": CH_CORE})
        b = ws.story_key({"headline": CH_HICP})
        assert a.key == b.key == "story:print:ch:cpi"
        assert a.basis == "indicator"

    def test_the_demonym_is_the_same_country(self):
        """'Swiss CPI' and 'Switzerland CPI' are one release, not two."""
        assert ws.story_key({"headline": "Swiss CPI YoY Jul 0.2%"}).key == \
            ws.story_key({"headline": CH_CORE}).key

    def test_german_retail_sales_survives_the_swiss_release(self):
        """D1-c. THE ANTI-OVER-COLLAPSE CONSTRAINT.

        A key that ate this would 'fix' the incident by deleting the day's news,
        which is the same class of defect wearing the opposite sign.
        """
        assert ws.story_key({"headline": DE_RETAIL}).key != \
            ws.story_key({"headline": CH_CORE}).key

    def test_two_speakers_are_two_stories(self):
        assert ws.story_key({"headline": WILLIAMS[0]}).key != ws.story_key(
            {"headline": "Fed's Bostic: labor market cooling as payrolls "
                         "and unemployment soften"}).key

    def test_one_speaker_two_topics_are_two_stories(self):
        assert ws.story_key({"headline": WILLIAMS[0]}).key != ws.story_key(
            {"headline": "Fed's Williams: new tariffs will lift import prices"}).key

    def test_the_institution_article_does_not_fork_the_key(self):
        """'the Fed's Powell' and 'Fed's Powell' are one man."""
        assert ws.story_key({"headline": "The Fed's Powell: rates stay restrictive"}).key == \
            ws.story_key({"headline": "Fed's Powell: rates stay restrictive"}).key

    def test_a_speaker_with_no_topic_family_falls_back_to_text(self):
        """Deliberate: collapsing everything an official said for 90 minutes
        would eat real stories, so an unrecognised topic degrades to identity."""
        key = ws.story_key({"headline": "Fed's Williams to speak at 3pm in Albany"})
        assert key.basis == "text"

    def test_a_country_possessive_is_not_a_speaker(self):
        """'Switzerland's CPI print' must not resolve to a speaker named CPI."""
        key = ws.story_key({"headline": "Switzerland's CPI print lands at 0.7%"})
        assert key.basis == "indicator" and key.anchor == "ch"

    def test_wire_furniture_is_not_a_speaker(self):
        assert ws.story_key({"headline": "BREAKING: gold hits a record"}).basis == "text"

    def test_a_blank_headline_never_collapses(self):
        """An empty key is 'do not collapse'. The failure mode of a blank key is
        one story silently eating the whole feed."""
        assert ws.story_key({"headline": ""}).key == ""
        assert ws.story_key({}).key == ""

    def test_the_key_is_explainable(self):
        key = ws.story_key({"headline": WILLIAMS[0]})
        assert "fed/williams" in key.explain() and "90min" in key.explain()


# ═════════════════════════════════════════════════════════════════════════════
# 3. THE LEDGER — first-wins, windows, and the counted suppression
# ═════════════════════════════════════════════════════════════════════════════

class TestLedger:
    def test_first_wins_within_a_tick(self):
        state: dict = {}
        ledger = ws.StoryLedger(state)
        assert ledger.consider({"headline": WILLIAMS[0]}, now=NOW, item_id="w0") is None
        for i, headline in enumerate(WILLIAMS[1:], start=1):
            dupe = ledger.consider({"headline": headline}, now=NOW, item_id=f"w{i}")
            assert dupe is not None
            assert dupe["merged_into"] == "w0"
            assert dupe["reason"] == "story_dupe"

    def test_a_within_tick_collapse_is_not_settled(self):
        """D1: a carrier that has not emitted yet may still be refused, so its
        siblings must come back next tick rather than be buried in `seen`."""
        ledger = ws.StoryLedger({})
        ledger.consider({"headline": WILLIAMS[0]}, now=NOW, item_id="w0")
        dupe = ledger.consider({"headline": WILLIAMS[1]}, now=NOW, item_id="w1")
        assert dupe["story_kind"] == "tick"
        assert dupe["settled"] is False

    def test_a_claimed_story_suppresses_later_ticks_and_is_settled(self):
        state: dict = {}
        first = ws.StoryLedger(state)
        first.consider({"headline": WILLIAMS[0]}, now=NOW, item_id="w0")
        first.claim({"headline": WILLIAMS[0]}, now=NOW, item_id="w0")

        later = ws.StoryLedger(state)
        dupe = later.consider({"headline": WILLIAMS[2]}, now=NOW + timedelta(minutes=20),
                              item_id="w2")
        assert dupe is not None
        assert dupe["story_kind"] == "posted" and dupe["settled"] is True
        assert dupe["merged_into"] == "w0"

    def test_an_unclaimed_story_is_still_open_next_tick(self):
        """THE REASON THE CLAIM SITS AT THE EMISSION AND NOT AT THE RESERVATION.

        The carrier was refused downstream (story lock, copy properties, outbox
        dedupe). Nothing posted, so the story must still be available.
        """
        state: dict = {}
        ws.StoryLedger(state).consider({"headline": WILLIAMS[0]}, now=NOW, item_id="w0")
        later = ws.StoryLedger(state)
        assert later.consider({"headline": WILLIAMS[1]},
                              now=NOW + timedelta(minutes=2), item_id="w1") is None

    def test_beyond_the_window_the_story_reopens(self):
        state: dict = {}
        ledger = ws.StoryLedger(state)
        ledger.claim({"headline": WILLIAMS[0]}, now=NOW, item_id="w0")
        later = ws.StoryLedger(state)
        assert later.consider({"headline": WILLIAMS[0]},
                              now=NOW + timedelta(minutes=91), item_id="w9") is None

    def test_inside_the_window_the_story_is_shut(self):
        state: dict = {}
        ws.StoryLedger(state).claim({"headline": WILLIAMS[0]}, now=NOW, item_id="w0")
        later = ws.StoryLedger(state)
        assert later.consider({"headline": WILLIAMS[0]},
                              now=NOW + timedelta(minutes=89), item_id="w9") is not None

    def test_the_window_is_config_driven(self):
        state: dict = {}
        cfg = {"speaker_window_min": 5}
        ws.StoryLedger(state, cfg=cfg).claim({"headline": WILLIAMS[0]}, now=NOW,
                                             item_id="w0")
        later = ws.StoryLedger(state, cfg=cfg)
        assert later.consider({"headline": WILLIAMS[0]},
                              now=NOW + timedelta(minutes=6), item_id="w9") is None

    def test_suppression_is_counted_in_persisted_state(self):
        """D1-f. Twelve nights of mover posts died in a `continue` that counted
        nothing; a collapse nobody can count is that bug with a nicer name."""
        state: dict = {}
        ledger = ws.StoryLedger(state)
        for i, headline in enumerate(WILLIAMS):
            ledger.consider({"headline": headline}, now=NOW, item_id=f"w{i}")
        tally = state["wire_story_suppressed"]
        assert tally["total"] == 3
        assert tally["keys"]["story:speaker:fed/williams:monetary"] == 3
        assert tally["day"] == "2026-08-02"

    def test_the_warning_starts_the_line_and_names_the_key(self, capsys):
        """D1-f + house law: a ::warning emitted through a logger is prefixed and
        GitHub silently drops it. Five shipped dead that way."""
        ledger = ws.StoryLedger({})
        for i, headline in enumerate(WILLIAMS):
            ledger.consider({"headline": headline}, now=NOW, item_id=f"w{i}")
        assert ledger.warn() == 3
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "story-collapsed" in ln]
        assert lines, "the collapse must be annotated"
        for line in lines:
            assert line.startswith("::warning title=press-lane-story-collapsed")
        assert "story:speaker:fed/williams:monetary" in lines[0]
        assert "3 wire item(s)" in lines[0]

    def test_a_quiet_tick_says_nothing(self, capsys):
        ledger = ws.StoryLedger({})
        ledger.consider({"headline": WILLIAMS[0]}, now=NOW, item_id="w0")
        assert ledger.warn() == 0
        assert "story-collapsed" not in capsys.readouterr().out

    def test_many_keys_roll_up_rather_than_spam(self, capsys):
        ledger = ws.StoryLedger({}, cfg={"max_warn_keys": 2})
        for i in range(4):
            head = f"Company {i} beats on revenue and raises its outlook"
            ledger.consider({"headline": head}, now=NOW, item_id=f"a{i}")
            ledger.consider({"headline": head}, now=NOW, item_id=f"b{i}")
        ledger.warn()
        out = capsys.readouterr().out
        assert out.count("::warning title=press-lane-story-collapsed::") == 2
        assert "::warning title=press-lane-story-collapsed-more::" in out

    def test_the_state_stays_json_persistable(self):
        """The daemon writes this dict out and commits the census."""
        state: dict = {}
        ledger = ws.StoryLedger(state)
        ledger.consider({"headline": WILLIAMS[0]}, now=NOW, item_id="w0")
        ledger.claim({"headline": WILLIAMS[0]}, now=NOW, item_id="w0")
        ledger.consider({"headline": WILLIAMS[1]}, now=NOW, item_id="w1")
        json.dumps(state)

    def test_prune_drops_stories_past_the_longest_window(self):
        state: dict = {}
        ledger = ws.StoryLedger(state)
        ledger.claim({"headline": WILLIAMS[0]}, now=NOW, item_id="w0")
        assert ledger.prune(NOW + timedelta(hours=1)) == 0
        assert ledger.prune(NOW + timedelta(hours=12)) == 1
        assert state["wire_stories"] == {}

    def test_the_story_ledger_is_capped(self):
        state: dict = {}
        ledger = ws.StoryLedger(state, cfg={"max_stories": 5})
        for i in range(20):
            ledger.claim({"headline": f"Company {i} beats on revenue"},
                         now=NOW + timedelta(seconds=i), item_id=f"c{i}")
        assert len(state["wire_stories"]) == 5

    def test_the_tally_key_space_is_capped(self):
        state: dict = {}
        ledger = ws.StoryLedger(state, cfg={"max_tally_keys": 3})
        for i in range(10):
            head = f"Company {i} beats on revenue and raises its outlook"
            ledger.consider({"headline": head}, now=NOW, item_id=f"a{i}")
            ledger.consider({"headline": head}, now=NOW, item_id=f"b{i}")
        assert len(state["wire_story_suppressed"]["keys"]) == 3
        assert state["wire_story_suppressed"]["total"] == 10

    def test_a_text_key_is_bounded_and_still_readable(self):
        """The key lands in a git-tracked state file, a skip row and a ::warning
        line, so a raw headline key would put a full sentence in all three."""
        key = ws.story_key({"headline": "A" * 400}).key
        assert len(key) < 70
        assert key.startswith("story:text:")
        # Two headlines sharing a long prefix must still be two stories.
        assert ws.story_key({"headline": "X" * 60 + " one"}).key != \
            ws.story_key({"headline": "X" * 60 + " two"}).key

    def test_a_saturated_ledger_fits_the_committed_cursors_ceiling(self):
        """scripts/marketing_press_wire.save_cursors writes every non-underscore
        state key into the COMMITTED cursors.json — whole, 288 times a day, under
        a 256 KB ceiling whose trim can only drop the SCORING_KEYS enrichment
        stores, never a correctness key like this one. So the bound has to hold
        on its own, against pathological headlines.
        """
        state: dict = {}
        ledger = ws.StoryLedger(state)
        for i in range(2000):
            head = (f"Some quite long wire headline about company {i} beating on "
                    f"revenue and raising its full-year outlook amid tariffs")
            when = NOW + timedelta(seconds=i)
            ledger.claim({"headline": head}, now=when, item_id=f"item-id-{i}")
            ledger.consider({"headline": head}, now=when, item_id=f"other-{i}")
        body = json.dumps(state, indent=2, sort_keys=True)
        assert len(state["wire_stories"]) == 300
        assert len(body.encode("utf-8")) < 120_000, len(body.encode("utf-8"))

    def test_disabled_is_a_real_switch(self):
        ledger = ws.StoryLedger({}, cfg={"enabled": False})
        ledger.consider({"headline": WILLIAMS[0]}, now=NOW, item_id="w0")
        assert ledger.consider({"headline": WILLIAMS[1]}, now=NOW,
                               item_id="w1") is None


# ═════════════════════════════════════════════════════════════════════════════
# 4. END TO END through run_press_tick — the operator's actual batch
# ═════════════════════════════════════════════════════════════════════════════

class TestTheIncidentBatch:
    def test_four_williams_headlines_emit_once(self, tmp_path):
        """D1-a end to end. THIS IS THE POST THAT SHIPPED FOUR TIMES."""
        items = [_item(f"w{i}", h, source=f"feed{i}")
                 for i, h in enumerate(WILLIAMS)]
        result = _run(items, tmp_path)
        assert len(result["emitted"]) == 1, _emitted_feed_ids(result)
        collapsed = [row for row in result["skipped"]
                     if row["reason"] == "story_dupe"]
        assert len(collapsed) == 3
        assert {row["id"] for row in collapsed} == {"w1", "w2", "w3"}

    def test_the_survivor_is_the_strongest_admissible_member(self, tmp_path):
        """Placement proof: the gate runs AFTER the salience sort, so a weaker
        member listed FIRST by the poller cannot claim the story and starve a
        stronger one — deterministically, on every tick, for the whole window.

        The two differ only in source tier (aggregator 33.0 vs official 42.0),
        which is exactly the shape the incident had: one speech relayed by
        several desks of unequal standing.
        """
        weak = _item("weak", WILLIAMS[0], source="feedA", source_tier="aggregator")
        strong = _item("strong", WILLIAMS[1], source="feedB", source_tier="official")
        result = _run([weak, strong], tmp_path)
        assert _emitted_feed_ids(result) == ["strong"]
        assert [row["id"] for row in result["skipped"]
                if row["reason"] == "story_dupe"] == ["weak"]

    def test_the_switzerland_pair_collapses_and_germany_survives(self, tmp_path):
        """D1-b + D1-c, in one batch. 'TWO FUCKING POSTS ON SWITZERLAND CPI'."""
        items = [_item("ch-core", CH_CORE, source="feed1"),
                 _item("ch-hicp", CH_HICP, source="feed2"),
                 _item("de-retail", DE_RETAIL, source="feed3")]
        result = _run(items, tmp_path)
        assert sorted(_emitted_feed_ids(result)) == ["ch-core", "de-retail"]
        collapsed = [row for row in result["skipped"] if row["reason"] == "story_dupe"]
        assert [row["id"] for row in collapsed] == ["ch-hicp"]
        assert collapsed[0]["merged_into"] == "ch-core"
        assert collapsed[0]["story_key"] == "story:print:ch:cpi"

    def test_the_caps_pair_emits_once(self, tmp_path):
        """D1-d end to end — the duplicate that was only visible in the outbox."""
        items = [_item("caps", CAPS, source="feed1"),
                 _item("title", TITLE, source="feed2")]
        result = _run(items, tmp_path)
        assert len(result["emitted"]) == 1
        assert [row["reason"] for row in result["skipped"]] == ["story_dupe"]

    def test_two_unrelated_fed_stories_an_hour_apart_both_emit(self, tmp_path):
        """D1-e. The gate must not become a volume cap on the Fed."""
        state: dict = {}
        first = _run([_item("f1", WILLIAMS[1], source="feed1")], tmp_path, state=state)
        second = _run(
            [_item("f2", "Fed's Bostic: labor market cooling as payrolls and "
                         "unemployment soften", source="feed2",
                   now=NOW + timedelta(hours=1))],
            tmp_path, state=state, now=NOW + timedelta(hours=1))
        assert _emitted_feed_ids(first) == ["f1"]
        assert _emitted_feed_ids(second) == ["f2"], second["skipped"]

    def test_the_same_story_next_tick_is_suppressed_and_marked_seen(self, tmp_path):
        """A settled collapse stops the item being re-ingested on all 288 of the
        day's remaining ticks — the same discipline as the copy-refusal branch."""
        state: dict = {}
        first = _run([_item("w0", WILLIAMS[0], source="feed1")], tmp_path, state=state)
        assert len(first["emitted"]) == 1
        second = run_press_tick(
            [_item("w1", WILLIAMS[1], source="feed2",
                   now=NOW + timedelta(minutes=10))],
            root=tmp_path, now=NOW + timedelta(minutes=10), cfg=_marketing_cfg(),
            press_cfg=_press_cfg(), state=state,
            seen_ids=set(first["_seen"]), dry_run=True,
        )
        assert second["emitted"] == []
        row = next(r for r in second["skipped"] if r["reason"] == "story_dupe")
        assert row["settled"] is True
        assert "w1" in second["_seen"]

    def test_the_collapse_is_annotated_at_line_start(self, tmp_path, capsys):
        """D1-f end to end."""
        items = [_item(f"w{i}", h, source=f"feed{i}")
                 for i, h in enumerate(WILLIAMS)]
        _run(items, tmp_path)
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "press-lane-story-collapsed" in ln]
        assert lines and lines[0].startswith("::warning title=")
        assert "story:speaker:fed/williams:monetary" in lines[0]

    def test_the_emitted_item_records_the_story_it_claimed(self, tmp_path):
        """Explainability, both ends: the survivor names its key and the
        suppressed rows name the survivor."""
        items = [_item(f"w{i}", h, source=f"feed{i}")
                 for i, h in enumerate(WILLIAMS)]
        result = _run(items, tmp_path)
        claimed = (result["emitted"][0].get("source") or {}).get("wire_story") or {}
        assert claimed["story_key"] == "story:speaker:fed/williams:monetary"
        assert claimed["basis"] == "speaker"
        survivor = _emitted_feed_ids(result)[0]
        for row in result["skipped"]:
            if row["reason"] == "story_dupe":
                assert row["merged_into"] == survivor
                assert row["story_key"] == claimed["story_key"]
                assert "one event, one post" in row["detail"]

    def test_a_collapsed_item_does_not_charge_a_desk_budget(self, tmp_path):
        """Placement proof: the gate runs BEFORE routing, so a suppressed item is
        never counted against a desk and never shows up in the headroom census as
        a dropped item. It was not dropped for want of headroom."""
        state: dict = {}
        items = [_item(f"w{i}", h, source=f"feed{i}")
                 for i, h in enumerate(WILLIAMS)]
        _run(items, tmp_path, state=state)
        assert sum(state["wire_day_counts"]["counts"].values()) == 1
        assert int(state.get("wire_headroom", {}).get("exhausted", 0)) == 0

    def test_the_ledger_survives_the_state_round_trip(self, tmp_path):
        state: dict = {}
        items = [_item(f"w{i}", h, source=f"feed{i}")
                 for i, h in enumerate(WILLIAMS)]
        _run(items, tmp_path, state=state)
        assert state["wire_stories"], "the claim must persist for the next tick"
        assert state["wire_story_suppressed"]["total"] == 3
        json.dumps(state)


# ═════════════════════════════════════════════════════════════════════════════
# 5. THE MUTATION CHECK — this gate is what stands between the operator and
#    four posts. Turning it off must restore the defect, exactly.
# ═════════════════════════════════════════════════════════════════════════════

class TestTheGateIsLoadBearing:
    def test_disabling_the_gate_restores_all_four_posts(self, tmp_path):
        """PRE-FIX BEHAVIOUR, ON PURPOSE.

        `wire.story.enabled: false` is the code path that existed before this
        change: `_emission_key` collapses mirrors and nothing else, so four feed
        ids are four posts. Every end-to-end assertion above is red under this
        flip, which is what makes them evidence rather than decoration.
        """
        items = [_item(f"w{i}", h, source=f"feed{i}")
                 for i, h in enumerate(WILLIAMS)]
        result = _run(items, tmp_path, press_cfg=_press_cfg(enabled=False))
        assert len(result["emitted"]) == 4
        assert not [row for row in result["skipped"] if row["reason"] == "story_dupe"]

    def test_the_shipped_config_has_the_gate_armed(self):
        """A default-off safety gate is a safety gate nobody has."""
        import yaml
        cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text(
            encoding="utf-8"))
        story = ((cfg.get("wire") or {}).get("story") or {})
        assert story.get("enabled") is True
        assert int(story["speaker_window_min"]) > 0
        assert int(story["indicator_window_min"]) > 0

    def test_an_unavailable_clustering_module_degrades_loudly(self, capsys):
        """Fail-soft is not free here: reaching it means the defect is live, so
        it must be annotated rather than silent."""
        from engine.marketing import press_lane as pl

        # A window that is not a number: resolve_cfg keeps operator values
        # verbatim, so the failure surfaces on the first prune.
        ledger = pl._story_ledger({}, wire_cfg={"story": {"text_window_min": "soon"}},
                                  now=NOW)
        assert ledger.consider({"headline": WILLIAMS[0]}, now=NOW,
                               item_id="w0") is None
        out = capsys.readouterr().out
        assert out.startswith("::warning title=press-lane-story-clustering-unavailable")


if __name__ == "__main__":   # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
