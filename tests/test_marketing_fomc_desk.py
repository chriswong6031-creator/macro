"""tests/test_marketing_fomc_desk.py — FOMC statement-diff desk (XG-W4b).

Program: research/MARKETING_X_ENGINE_CODEX_QUALITY_AND_FASTLANES_MASTERPLAN_2026_08_08.md
(W4b — the FOMC fast lane).

FIXTURE-DRIVEN, ZERO LIVE NETWORK, ZERO LIVE LLM. The two statements under
`data/fomc/statements/` are REAL Federal Reserve text, collected during the build
and committed as both the live baseline the lane reads on 2026-09-16 and this
suite's fixtures. `tests/fixtures/fomc/monetary20260729a.htm` is the real press
release page, nav and all, so the extractor is proven against the thing it will
actually be handed rather than against a hand-built lookalike.

Every provider-path test monkeypatches engine.llm_auth.build_providers /
make_call, and the env flag is set through monkeypatch so it cannot leak into
another suite. Import closure is stdlib + pyyaml: the thin marketing-engine CI
lane has no `anthropic` package, so a module-level import of it in any fomc_*
module would turn this file red at COLLECTION. Test 16 pins that mechanically.

Covers:
  1.  The differ on the REAL July-2026 vs June-2026 pair: 6 verbatim, the vote,
      the reserves verb, the added dissent sentence.
  2.  Coalescing: the vote reads as one phrase, not four fragments.
  3.  Highlight ranking: the vote outranks a wording change (the tier-0 bug).
  4.  Decision-fact extraction, including all three dissenters past their
      middle initials.
  5.  Refusal: every fact is None on a mangled statement; nothing is guessed.
  6.  Extraction from the real page drops 44 paragraphs of site navigation.
  7.  Extraction refuses a page shape it does not recognise.
  8.  The calendar is READ from event_calendar and the fallback is pinned equal.
  9.  Card SVG: well-formed XML, carries the diff highlights, no <script>.
  10. Card: the analysis is never half-drawn, and `fit` reports what was drawn.
  11. Writer: a clean draft validates and produces mode "llm".
  12. Writer: a draft with an invented number takes ONE repair turn -> llm_repair.
  13. Writer: total provider failure -> fallback_provider, and disarmed -> "off".
  14. Enqueue shape: immediate, event_class fomc, both desks in fallback mode.
  15. Trigger: idempotent (a second firing for the same meeting no-ops).
  16. Import closure + GH annotations start the line.
  17. config/marketing.yml ships the fomc_desk block.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
sys.path.insert(0, str(ROOT))

from engine.marketing import fomc_desk, fomc_diff, fomc_statements  # noqa: E402

JULY = "2026-07-29"
JUNE = "2026-06-17"
PAGE_FIXTURE = ROOT / "tests" / "fixtures" / "fomc" / "monetary20260729a.htm"

NOW = datetime(2026, 7, 29, 18, 5, tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def july() -> list[str]:
    paragraphs = fomc_statements.read_statement(JULY, ROOT)
    assert paragraphs, f"the committed {JULY} statement seed is missing"
    return paragraphs


@pytest.fixture(scope="module")
def june() -> list[str]:
    paragraphs = fomc_statements.read_statement(JUNE, ROOT)
    assert paragraphs, f"the committed {JUNE} statement seed is missing"
    return paragraphs


@pytest.fixture(scope="module")
def diff(june, july) -> dict:
    return fomc_diff.diff_statements(june, july)


@pytest.fixture(scope="module")
def facts(july) -> dict:
    return fomc_diff.extract_facts(july)


@pytest.fixture
def desk_cfg() -> dict:
    return {
        "fomc_desk": {
            "enabled": True,
            "accounts": {"analysis": "flagship", "relay": "mastermind_news"},
            "llm": {"enabled": True},
        },
    }


@pytest.fixture
def seeded_root(tmp_path: Path) -> Path:
    """A repo-shaped temp root carrying ONLY the June baseline.

    July is therefore diffable but not yet collected, which is the state the lane
    is in at 14:00 ET on a decision day.

    Paths come from fomc_statements.STORE_DIR rather than a literal, so relocating
    the store cannot leave this fixture pointing at a directory that no longer
    exists (it did, once — the store moved under data/marketing/ so the press-wire
    workflow's sparse checkout could actually see it).
    """
    store = tmp_path / fomc_statements.STORE_DIR
    store.mkdir(parents=True)
    shutil.copyfile(ROOT / fomc_statements.STORE_DIR / f"{JUNE}.txt",
                    store / f"{JUNE}.txt")
    return tmp_path


@pytest.fixture(scope="module")
def july_page() -> str:
    assert PAGE_FIXTURE.exists(), f"missing page fixture {PAGE_FIXTURE}"
    return PAGE_FIXTURE.read_text(encoding="utf-8", errors="replace")


@pytest.fixture
def hosted_card(monkeypatch):
    """Make the diff card HOSTED, which the flagship post requires.

    Not a convenience: since the M6 fix an unhosted card SKIPS the flagship (the
    analysis lives only on the card, so a hook with no card is a post about
    nothing). There is no R2 credential in a test, and no Chrome in the thin CI
    lane, so any test that expects the flagship to ship must arrange its
    precondition explicitly rather than depend on the environment.
    """
    from engine.marketing import media_publish

    monkeypatch.setattr(
        media_publish, "publish_card",
        lambda svg, **kw: {
            "svg_path": f"data/marketing/outbox/media/{kw.get('as_of')}/"
                        f"{kw.get('chart_id')}.svg",
            "media_png_path": f"data/marketing/outbox/media/{kw.get('as_of')}/"
                              f"{kw.get('chart_id')}.png",
            "media_render": "svg_raster",
            "media_url": f"https://cdn.example.com/{kw.get('chart_id')}.png",
        })


# ─────────────────────────────────────────────────────────────────────────────
# 1-3. The differ, on real text
# ─────────────────────────────────────────────────────────────────────────────

def test_real_july_vs_june_diff(diff):
    """The actual 2026-07-29 vs 2026-06-17 diff, asserted on its real content."""
    # Nine sentences now, eight last meeting, six carried over word for word.
    assert diff["current_sentences"] == 9
    assert diff["prior_sentences"] == 8
    assert diff["unchanged_count"] == 6
    assert diff["changed_count"] == 2
    assert diff["removed_sentences"] == []

    # The vote moved and the reserves verb moved. Nothing else was reworded.
    removed = " | ".join(diff["removed_phrases"])
    added = " | ".join(diff["added_phrases"])
    assert "12" in removed and "0" in removed
    assert "9" in added and "3" in added
    assert "reaffirmed" in removed
    assert "is continuing" in added

    # The dissent block is an ADDITION: it did not exist in June.
    assert len(diff["added_sentences"]) == 1
    assert diff["added_sentences"][0].startswith("Voting against the monetary policy")
    assert "Beth M. Hammack" in diff["added_sentences"][0]


def test_vote_change_coalesces_into_one_phrase(diff):
    """"12 - 0" -> "9 - 3" is ONE change, not four fragments.

    The dash between the numbers is unchanged, so a raw opcode walk reports
    removed ["12","0"] / added ["9","3"] and the card asks the reader to
    reassemble a vote count. Pinning the coalesced form pins the fix.
    """
    vote_rows = [r for r in diff["changed"]
                 if any("12" in p for p in r["removed"])]
    assert len(vote_rows) == 1
    row = vote_rows[0]
    assert len(row["removed"]) == 1, row["removed"]
    assert len(row["added"]) == 1, row["added"]
    assert re.fullmatch(r"12\s*[-–—]\s*0", row["removed"][0]), row["removed"][0]
    assert re.fullmatch(r"9\s*[-–—]\s*3", row["added"][0]), row["added"][0]


def test_vote_change_outranks_a_wording_change(diff):
    """The most consequential edit ranks FIRST.

    Regression pin for the ranking bug: the words that changed in the vote line
    are only digits, so a ranker scoring changed-words-only gave the vote 0.00 and
    filed it below "reaffirmed" -> "is continuing".
    """
    rows = fomc_diff.highlights(diff, limit=6)
    assert rows, "the real diff must produce highlights"
    top = rows[0]
    assert top["kind"] == "changed"
    assert top["tier"] == 0
    assert "12" in top["removed_text"] and "9" in top["added_text"]
    # The wording change is present but subordinate.
    tiers = {r["tier"] for r in rows}
    assert 0 in tiers
    wording = [r for r in rows if "reaffirmed" in r["removed_text"]]
    assert wording and wording[0]["tier"] > 0


def test_highlights_respect_the_limit(diff):
    assert len(fomc_diff.highlights(diff, limit=2)) == 2
    assert len(fomc_diff.highlights(diff, limit=0)) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4-5. Facts: extraction, and refusal
# ─────────────────────────────────────────────────────────────────────────────

def test_decision_facts_from_the_real_statement(facts):
    assert facts["target_range"] == "3-1/2 to 3-3/4 percent"
    assert facts["action"] == "maintain"
    assert facts["vote"] == {"for": 9, "against": 3}
    assert facts["unanimous"] is False
    assert facts["dissent_preference"] == "raise"
    assert facts["dissent_size"] == "1/4"
    assert fomc_diff.decision_line(facts) == (
        "Fed held the federal funds target range at 3-1/2 to 3-3/4 percent")


def test_dissenters_survive_their_middle_initials(facts):
    """All THREE names, each whole.

    Regression pin: the first implementation captured the name blob with a
    period-excluding character class and returned ["Beth M"] — one dissenter of
    three, with her surname cut off, on a flagship post about interest rates.
    """
    assert facts["dissenters"] == [
        "Beth M. Hammack", "Neel Kashkari", "Lorie K. Logan"]


def test_unanimous_vote_reads_as_unanimous_with_no_dissenters(june):
    facts = fomc_diff.extract_facts(june)
    assert facts["vote"] == {"for": 12, "against": 0}
    assert facts["unanimous"] is True
    # ABSENCE IS NOT A CLAIM: no "Voting against" sentence yields None, never [].
    assert facts["dissenters"] is None
    assert facts["dissent_preference"] is None


def test_facts_refuse_rather_than_guess_on_a_mangled_statement():
    """Every field None. A partial regex match may not become a rate."""
    mangled = [
        "The Committee met and discussed the economy at some length.",
        "Rates were considered. The federal funds rate was on the agenda.",
        "Several participants spoke about percent and about points.",
    ]
    facts = fomc_diff.extract_facts(mangled)
    assert facts["target_range"] is None
    assert facts["action"] is None
    assert facts["vote"] is None
    assert facts["dissenters"] is None
    assert facts["dissent_preference"] is None
    assert facts["dissent_size"] is None
    assert facts["unanimous"] is None
    assert fomc_diff.decision_line(facts) is None
    # And the deterministic relay refuses too, rather than posting half a fact.
    assert fomc_desk.deterministic_relay(facts) is None


@pytest.mark.parametrize(("sentence", "expect"), [
    # 2026-07-29, the committed seed.
    ("The Committee decided to maintain the target range for the federal funds "
     "rate at 3-1/2 to 3-3/4 percent, in support of the dual mandate.",
     ("maintain", "3-1/2 to 3-3/4 percent")),
    # A CUT, with the size clause between the anchor and the range (2024-09-18).
    ("the Committee decided to lower the target range for the federal funds rate "
     "by 1/2 percentage point to 4-3/4 to 5 percent.",
     ("lower", "4-3/4 to 5 percent")),
    # A HIKE with no size clause (2022-06-15 shape).
    ("the Committee decided to raise the target range for the federal funds rate "
     "to 1-1/2 to 1-3/4 percent.",
     ("raise", "1-1/2 to 1-3/4 percent")),
    # THE ZERO BOUND: a BARE FRACTION as the upper bound (the ZIRP wording).
    ("the Committee decided to lower the target range for the federal funds rate "
     "to 0 to 1/4 percent.",
     ("lower", "0 to 1/4 percent")),
    # The older "decided today to ..." construction.
    ("the Committee decided today to lower the target range for the federal "
     "funds rate to 1 to 1-1/4 percent.",
     ("lower", "1 to 1-1/4 percent")),
])
def test_action_and_range_across_real_fomc_wordings(sentence, expect):
    """Historical wordings extract the RIGHT numbers, or none at all.

    A refusal is the designed answer for an unrecognised sentence; a WRONG rate on
    a flagship post about interest rates is the defect. Each row here is a real
    construction from the archive.
    """
    facts = fomc_diff.extract_facts([sentence])
    assert (facts["action"], facts["target_range"]) == expect


def test_unrecognised_construction_refuses_the_whole_decision():
    """An unlisted verb AND an unlisted clause both refuse. That is the design.

    "decided to keep the target range ... unchanged at X to Y percent" is not a
    wording the modern archive uses, and neither the verb list nor the
    target-range anchor is widened to admit it: the anchor allows exactly one
    optional intervening clause (the "by 1/4 percentage point" of a cut or hike),
    because every extra thing it is allowed to skip is another way for it to
    match across text it should not. The cost is a desk that no-ops on a wording
    it has never seen. The alternative cost is a wrong interest rate on the
    flagship, which is not a trade this lane makes.
    """
    facts = fomc_diff.extract_facts([
        "the Committee decided to keep the target range for the federal funds "
        "rate unchanged at 3-1/2 to 3-3/4 percent."])
    assert facts["action"] is None
    assert facts["target_range"] is None
    assert fomc_diff.decision_line(facts) is None
    assert fomc_desk.deterministic_relay(facts) is None


def test_range_is_never_read_off_the_dissenters_preferred_range():
    """The range is the COMMITTEE'S, even when a dissent names another one.

    NOT VACUOUS: the second paragraph contains a full, well-formed
    "target range for the federal funds rate ... at 2 to 2-1/4 percent" — the exact
    string the old document-wide search would match. The surviving mutation the
    first version of this test missed was "search the whole statement instead of
    the decision sentence", because its distractor said "interest rate on reserve
    balances", which the anchor never matched in the first place.
    """
    paragraphs = [
        "The Committee decided to maintain the target range for the federal funds "
        "rate at 3-1/2 to 3-3/4 percent, in support of the dual mandate.",
        "Voting against this action was Loretta J. Mester, who preferred to "
        "maintain the target range for the federal funds rate at 2 to 2-1/4 "
        "percent.",
    ]
    facts = fomc_diff.extract_facts(paragraphs)
    assert facts["target_range"] == "3-1/2 to 3-3/4 percent"
    assert facts["action"] == "maintain"
    assert "2 to 2-1/4" not in str(fomc_diff.decision_line(facts))
    assert "2 to 2-1/4" not in str(fomc_desk.deterministic_relay(facts))


def test_comma_form_cut_reads_the_committees_range_not_the_dissenters():
    """2020-03-03: the comma form, with a dissent range sitting right after it.

    Both halves of the M1 fix are load-bearing here. Without the comma in the
    pattern the decision sentence is unreadable; without decision-sentence scoping
    the search then lands on Mester's preferred 2 to 2-1/4 percent and the relay
    ships the rate the Committee voted against.
    """
    paragraphs = [
        "The Committee decided to lower the target range for the federal funds "
        "rate by 1/2 percentage point, to 1 to 1-1/4 percent.",
        "Voting against this action was Loretta J. Mester, who preferred to "
        "maintain the target range for the federal funds rate at 2 to 2-1/4 "
        "percent.",
    ]
    facts = fomc_diff.extract_facts(paragraphs)
    assert facts["action"] == "lower"
    assert facts["target_range"] == "1 to 1-1/4 percent"
    assert fomc_diff.decision_line(facts) == (
        "Fed lowered the federal funds target range to 1 to 1-1/4 percent")


def test_action_and_range_never_come_from_different_sentences():
    """Two fields describing one decision come from one sentence, or from neither."""
    # A statement whose decision sentence has an unreadable range: BOTH refuse,
    # rather than pairing this action with some other sentence's number.
    facts = fomc_diff.extract_facts([
        "The Committee decided to lower the target range for the federal funds "
        "rate to a level it will announce separately.",
        "The previous target range for the federal funds rate was at 4 to 4-1/4 "
        "percent.",
    ])
    assert facts["action"] == "lower"
    assert facts["target_range"] is None
    assert fomc_diff.decision_line(facts) is None
    assert fomc_desk.deterministic_relay(facts) is None


# ── The 2019-09-18 blocker: a MIXED dissent block ────────────────────────────

MIXED_DISSENT = [
    "In light of the implications of global developments for the economic "
    "outlook, the Committee decided to lower the target range for the federal "
    "funds rate to 1-3/4 to 2 percent.",
    "Voting against this action were Esther L. George and Eric S. Rosengren, who "
    "preferred to maintain the target range at 2 to 2-1/4 percent; and James "
    "Bullard, who preferred at this meeting to lower the target for the federal "
    "funds rate by 1/2 percentage point to 1-1/2 to 1-3/4 percent.",
]


def test_mixed_dissent_never_attributes_a_borrowed_preference():
    """THE B2 BLOCKER, pinned on the real 2019-09-18 wording.

    Before the per-clause parser this returned dissenters=['James Bullard'] with
    preference='maintain' and size='1/2' — because the names capture stopped at the
    first ", who" while the preference and size searches ran over the WHOLE block.
    The relay then read "Bullard preferred to maintain by 1/2 point", crediting a
    named Federal Reserve official on a stance-free wire account with the exact
    opposite of his actual vote. He wanted a DEEPER cut.
    """
    facts = fomc_diff.extract_facts(MIXED_DISSENT)
    # All three names, none dropped.
    assert facts["dissenters"] == [
        "Esther L. George", "Eric S. Rosengren", "James Bullard"]
    # FAIL CLOSED: the groups disagree, so no single direction is claimed.
    assert facts["dissent_preference"] is None
    assert facts["dissent_size"] is None
    # The per-group truth is preserved and correctly bound.
    assert facts["dissent_groups"] == [
        {"names": ["Esther L. George", "Eric S. Rosengren"],
         "preference": "maintain", "size": None},
        {"names": ["James Bullard"], "preference": "lower", "size": "1/2"},
    ]
    # And the wire says only what is proven.
    relay = fomc_desk.deterministic_relay(facts)
    assert relay == ("Fed lowered the federal funds target range to 1-3/4 to 2 "
                     "percent. George, Rosengren and Bullard dissented.")
    assert "maintain" not in relay
    assert "Bullard preferred" not in relay


def test_mixed_dissent_card_names_them_without_a_direction(diff):
    """The card may not paper over an unprovable direction either."""
    from engine.marketing import fomc_card

    facts = fomc_diff.extract_facts(MIXED_DISSENT)
    svg = fomc_card.render_fomc_card(
        date_str="2019-09-18", decision_line=fomc_diff.decision_line(facts),
        analysis_paragraphs=["A paragraph.", "Another paragraph."],
        highlights=[], facts=facts, unchanged_count=None, prior_date=None,
    )
    drawn = " ".join((el.text or "") for el in ET.fromstring(svg).iter()
                     if el.tag.endswith("text"))
    for surname in ("George", "Rosengren", "Bullard"):
        assert surname in drawn, surname
    assert "George, Rosengren, Bullard dissented" in drawn
    # NO DIRECTION IS ATTRIBUTED TO THEM: the groups disagree, so any single one
    # would be a lie about at least one of the three names on the card. Scoped to
    # the dissent phrasing — the hero legitimately says the Fed "lowered".
    assert "wanted to" not in drawn
    assert "Bullard wanted" not in drawn
    for claim in ("dissenters wanted to maintain", "wanted to lower",
                  "wanted to maintain"):
        assert claim not in drawn, claim


def test_single_group_dissent_still_states_its_direction(facts):
    """Fail-closed must not mean fail-silent: one group, one direction, stated."""
    assert facts["dissent_preference"] == "raise"
    assert facts["dissent_size"] == "1/4"
    assert facts["dissent_groups"] == [{
        "names": ["Beth M. Hammack", "Neel Kashkari", "Lorie K. Logan"],
        "preference": "raise", "size": "1/4"}]


def test_roster_colon_form_does_not_null_every_dissent_fact():
    """"were:" used to be cut by the sentence splitter into a 5-word fragment."""
    facts = fomc_diff.extract_facts([
        "The Committee decided to maintain the target range for the federal funds "
        "rate at 3-1/2 to 3-3/4 percent.",
        "Voting against the action were: Charles L. Evans and Narayana "
        "Kocherlakota, who preferred to lower the target range by 1/4 percentage "
        "point.",
    ])
    assert facts["dissenters"] == ["Charles L. Evans", "Narayana Kocherlakota"]
    assert facts["dissent_preference"] == "lower"
    assert facts["dissent_size"] == "1/4"


def test_dissent_with_no_preference_clause_claims_none():
    facts = fomc_diff.extract_facts([
        "The Committee decided to maintain the target range for the federal funds "
        "rate at 0 to 1/4 percent.",
        "Voting against this action was Jeffrey M. Lacker.",
    ])
    assert facts["dissenters"] == ["Jeffrey M. Lacker"]
    assert facts["dissent_preference"] is None
    assert fomc_desk.deterministic_relay(facts) == (
        "Fed held the federal funds target range at 0 to 1/4 percent. "
        "Lacker dissented.")


def test_vote_line_accepts_an_eleven_one():
    """"by an 11-1 vote" — the archive's own article."""
    facts = fomc_diff.extract_facts(
        ["The Committee approved the statement by an 11-1 vote:"])
    assert facts["vote"] == {"for": 11, "against": 1}


def test_singular_dissent_wording():
    """"Voting against this action was <one name>." """
    facts = fomc_diff.extract_facts([
        "The Committee decided to maintain the target range for the federal funds "
        "rate at 3-1/2 to 3-3/4 percent.",
        "Voting against this action was Esther L. George, who preferred to raise "
        "the target range by 1/4 percentage point at this meeting."])
    assert facts["dissenters"] == ["Esther L. George"]
    assert facts["dissent_preference"] == "raise"
    assert facts["dissent_size"] == "1/4"


def test_vote_line_accepts_every_dash_the_fed_typesets():
    for dash in ("-", "–", "—", " – ", " - "):
        facts = fomc_diff.extract_facts(
            [f"The Committee approved the statement by a 9{dash}3 vote:"])
        assert facts["vote"] == {"for": 9, "against": 3}, dash


def test_deterministic_relay_states_the_facts_and_nothing_else(facts):
    text = fomc_desk.deterministic_relay(facts)
    assert text == ("Fed held the federal funds target range at 3-1/2 to 3-3/4 "
                    "percent. Vote 9-3. Hammack, Kashkari and Logan preferred to "
                    "raise by 1/4 point.")
    assert len(text) <= fomc_desk.POST_MAX_CHARS
    # Wire register: no first person, no judgement, no hype.
    for tell in ("we ", "I ", "our ", "hawkish", "dovish", "!", "#"):
        assert tell not in text


def test_deterministic_relay_drops_whole_sentences_to_fit():
    """A wire post is never cut mid-surname.

    `parts` is ordered decision, vote, dissent; over budget, the LAST sentence is
    dropped rather than sliced, because a shorter true relay beats a truncated one
    and the decision sentence alone is a complete wire item.
    """
    crowded = {
        "action": "lower", "target_range": "3-1/4 to 3-1/2 percent",
        "vote": {"for": 7, "against": 5}, "unanimous": False,
        "dissent_preference": "maintain", "dissent_size": "1/4",
        "dissenters": [f"Governor Nameveryverylong{i} Surnameveryverylong{i}"
                       for i in range(9)],
    }
    text = fomc_desk.deterministic_relay(crowded)
    assert text is not None
    assert len(text) <= fomc_desk.POST_MAX_CHARS
    assert text.endswith(".")
    assert "Fed lowered the federal funds target range to 3-1/4 to 3-1/2 percent." \
        in text
    assert "Surnameveryverylong8" not in text, "the dissent sentence was dropped whole"


def test_facts_refuse_on_empty_input():
    for empty in ([], [""], None):
        facts = fomc_diff.extract_facts(empty)
        assert all(v is None for v in facts.values()), facts


def test_sentence_split_is_initial_aware():
    """A middle initial is not a sentence boundary."""
    text = ("Voting against the monetary policy action were Beth M. Hammack, "
            "Neel Kashkari, and Lorie K. Logan. The vote stands.")
    assert fomc_diff.split_sentences(text) == [
        "Voting against the monetary policy action were Beth M. Hammack, "
        "Neel Kashkari, and Lorie K. Logan.",
        "The vote stands.",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 6-8. The collector
# ─────────────────────────────────────────────────────────────────────────────

def test_extractor_drops_site_navigation_from_the_real_page(july_page, july):
    """The real page carries 44 paragraphs of nav above the statement."""
    all_paragraphs = re.findall(r"<p[^>]*>", july_page)
    assert len(all_paragraphs) > 40, "the fixture should be the FULL page"
    extracted = fomc_statements.extract_statement(july_page)
    assert extracted == july, "extraction must equal the committed seed"
    assert len(extracted) == 5
    joined = " ".join(extracted)
    for nav in ("Regulatory and Policy Resources", "Micro Data Reference Manual",
                "An official website", "For media inquiries",
                "Implementation Note issued", "Board of Governors"):
        assert nav not in joined, f"navigation leaked: {nav}"
    assert extracted[0].startswith("The Federal Open Market Committee approved")


def test_extractor_refuses_an_unrecognised_page():
    assert fomc_statements.extract_statement("") == []
    assert fomc_statements.extract_statement("not html at all") == []
    # No article container -> refuse rather than parse the navigation.
    assert fomc_statements.extract_statement(
        "<html><body><p>Home</p><p>About us</p></body></html>") == []
    # Article container, but nothing that names the Committee -> refuse.
    assert fomc_statements.extract_statement(
        '<div id="article"><div class="heading col-xs-12 col-sm-8"></div>'
        '<div class="col-xs-12 col-sm-8"><p>One</p><p>Two</p></div></div>') == []


def test_calendar_is_read_from_event_calendar_and_the_fallback_is_pinned():
    """ONE transcription of the Fed calendar, with the local copy pinned to it.

    engine/event_calendar.py already carries the 2026 decision dates (and feeds
    the dashboard calendar and the factor-era phase classifier off them). This
    module reads that list; the literal fallback exists only for a checkout where
    the import fails, so a 2027 refresh that touches one and not the other must
    fail HERE rather than silently split the calendar in two.
    """
    from engine.event_calendar import _FOMC

    assert list(fomc_statements._FOMC_2026_FALLBACK) == [d for d, _sep in _FOMC]
    dates = fomc_statements.decision_dates(2026)
    assert dates == sorted(dates)
    # Remaining 2026 meetings as of the build: Sep 15-16, Oct 27-28, Dec 8-9.
    # The DECISION day is the second day of each.
    for decision_day in ("2026-09-16", "2026-10-28", "2026-12-09"):
        assert decision_day in dates
        assert fomc_statements.is_decision_day(decision_day)
    # The first day of a meeting is not a decision day.
    assert not fomc_statements.is_decision_day("2026-09-15")
    assert fomc_statements.STATEMENT_RELEASE_ET == "14:00"


def test_prior_decision_date_and_url():
    assert fomc_statements.prior_decision_date(JULY) == JUNE
    assert fomc_statements.prior_decision_date("2026-09-16") == JULY
    assert fomc_statements.statement_url("2026-09-16") == (
        "https://www.federalreserve.gov/newsevents/pressreleases/"
        "monetary20260916a.htm")
    assert fomc_statements.statement_url("nonsense") is None


def test_seeded_store_and_ledger_agree():
    """The committed ledger describes the committed statements."""
    rows = {r["date"]: r for r in fomc_statements.ledger_rows(ROOT)}
    for date_str in (JUNE, JULY):
        assert date_str in rows, f"{date_str} missing from the ledger"
        row = rows[date_str]
        text = fomc_statements.statement_text(
            fomc_statements.read_statement(date_str, ROOT))
        assert row["sha"] == fomc_statements.statement_sha(text)
        assert row["paragraphs"] == len(
            fomc_statements.read_statement(date_str, ROOT))
        assert row["url"].endswith(".htm")
    assert fomc_statements.is_collected(JULY, ROOT)


def test_collect_writes_the_store_but_not_the_ledger(tmp_path, july_page):
    """The ledger row is the DESK's record of a finished firing, not a fetch.

    Written at the end of a firing, so a crash mid-firing leaves no row and the
    next 5-minute tick retries instead of remembering a post that never happened.
    """
    got = fomc_statements.collect(JULY, root=tmp_path, html_text=july_page,
                                  now=NOW)
    assert got and got["date"] == JULY
    assert fomc_statements.read_statement(JULY, tmp_path) == got["paragraphs"]
    assert fomc_statements.ledger_rows(tmp_path) == []
    assert not fomc_statements.is_collected(JULY, tmp_path)

    fomc_statements.record_collection(got, root=tmp_path, extra={"mode": "test"})
    assert fomc_statements.is_collected(JULY, tmp_path)


def test_collect_refuses_an_unreadable_page(tmp_path, capsys):
    assert fomc_statements.collect(
        JULY, root=tmp_path, html_text="<html><p>nope</p></html>") is None
    out = capsys.readouterr().out
    assert any(line.startswith("::warning title=fomc-statement-unreadable")
               for line in out.splitlines())


# ─────────────────────────────────────────────────────────────────────────────
# 9-10. The card
# ─────────────────────────────────────────────────────────────────────────────

def test_card_svg_is_well_formed_and_carries_the_diff(diff, facts, july):
    """Structure only. NOTHING here rasterizes: no Chrome in the CI lane."""
    from engine.marketing import fomc_card

    rows = fomc_desk.card_highlights(diff, facts, july, limit=6)
    fit: dict = {}
    svg = fomc_card.render_fomc_card(
        date_str=JULY,
        decision_line=fomc_diff.decision_line(facts),
        analysis_paragraphs=["First short paragraph about the hold.",
                             "Second short paragraph about the vote."],
        highlights=rows, facts=facts,
        unchanged_count=diff["unchanged_count"], prior_date=JUNE, fit=fit,
    )
    root = ET.fromstring(svg)          # well-formed, or this raises
    assert root.tag.endswith("svg")
    assert root.get("width") == str(fomc_card.CARD_W)
    assert root.get("height") == str(fomc_card.CARD_H)
    assert "<script" not in svg.lower()

    texts = [(el.text or "") for el in root.iter()
             if el.tag.endswith("text") and el.text]
    joined = " ".join(texts)
    # The decision, the vote, the desk furniture and the diff.
    assert "FOMC STATEMENT" in joined
    assert "JULY 29, 2026" in joined
    assert "VOTE 9-3" in joined
    assert "WHAT CHANGED" in joined
    assert "6 sentences unchanged" in joined
    assert "3-1/2 to 3-3/4 percent" in joined
    # The removed phrase and the added phrase both drawn.
    assert any("12-0" in t for t in texts), texts
    assert any("9-3" in t and "12" not in t for t in texts), texts
    assert "is continuing" in joined and "reaffirmed" in joined
    # Dissenters are named in PLAIN WORDS beside the chip, never as a raw slug.
    assert "Hammack" in joined and "Kashkari" in joined and "Logan" in joined


def test_card_never_emits_a_house_banned_dash(diff, facts, july):
    """The Fed types "9 – 3"; our surfaces may not carry a spaced en dash."""
    from engine.marketing import fomc_card

    svg = fomc_card.render_fomc_card(
        date_str=JULY, decision_line=fomc_diff.decision_line(facts),
        analysis_paragraphs=["A paragraph."],
        highlights=fomc_diff.highlights(diff, limit=6), facts=facts,
        unchanged_count=diff["unchanged_count"], prior_date=JUNE,
    )
    drawn = " ".join((el.text or "") for el in ET.fromstring(svg).iter()
                     if el.tag.endswith("text"))
    for dash in ("—", "–", " - "):
        assert dash not in drawn, f"card drew a banned dash: {dash!r}"


def test_card_reports_what_it_drew_and_never_half_draws_a_paragraph(diff, facts, july):
    """`fit` is the out-param the desk reads to warn on a dropped paragraph."""
    from engine.marketing import fomc_card

    rows = fomc_desk.card_highlights(diff, facts, july, limit=6)
    fit: dict = {}
    fomc_card.render_fomc_card(
        date_str=JULY, decision_line=fomc_diff.decision_line(facts),
        analysis_paragraphs=["Short one.", "Short two.", "Short three."],
        highlights=rows, facts=facts,
        unchanged_count=diff["unchanged_count"], prior_date=JUNE, fit=fit,
    )
    assert fit["paragraphs_supplied"] == 3
    assert fit["paragraphs_drawn"] == 3
    assert fit["body_size"] >= 28.0
    assert 0 < fit["highlight_lines_drawn"] <= fomc_card.MAX_HIGHLIGHT_LINES

    # A wildly over-long analysis is truncated by WHOLE paragraphs, and says so.
    fat = ["word " * 120] * 6
    fit2: dict = {}
    fomc_card.render_fomc_card(
        date_str=JULY, decision_line=fomc_diff.decision_line(facts),
        analysis_paragraphs=fat, highlights=rows, facts=facts,
        unchanged_count=diff["unchanged_count"], prior_date=JUNE, fit=fit2,
    )
    assert fit2["paragraphs_supplied"] == 6
    assert 1 <= fit2["paragraphs_drawn"] < 6


def test_card_without_provable_facts_still_renders(diff):
    """No decision line, no vote: the card degrades, it does not blow up."""
    from engine.marketing import fomc_card

    svg = fomc_card.render_fomc_card(
        date_str=JULY, decision_line=None,
        analysis_paragraphs=["Only prose here."], highlights=[], facts={},
        unchanged_count=None, prior_date=None,
    )
    ET.fromstring(svg)
    assert "VOTE" not in svg


def test_card_drops_the_dissent_sentence_that_the_chip_already_states(diff, facts, july):
    """No card says the same thing twice.

    The chip prints "Hammack, Kashkari, Logan wanted to raise by 1/4 point"; the
    Fed's own dissent sentence underneath it is the same fact in worse English,
    and on the first render probe it also overran three lines and clipped
    mid-word.
    """
    plain = fomc_diff.highlights(diff, limit=6)
    assert any(r["kind"] == "added" for r in plain), "baseline: the row exists"
    trimmed = fomc_desk.card_highlights(diff, facts, july, limit=6)
    assert not any(str(r.get("added_text", "")).startswith("Voting against")
                   for r in trimmed)
    # And the lines it would have taken go to the real changes.
    assert len(trimmed) == 2
    assert {r["kind"] for r in trimmed} == {"changed"}


# ─────────────────────────────────────────────────────────────────────────────
# 11-13. The writer
# ─────────────────────────────────────────────────────────────────────────────

CLEAN_ANALYSIS = [
    "The rate did not move, and neither did most of the statement. Six of the "
    "nine sentences are carried over word for word.",
    "What moved is the committee itself. June passed 12-0. July passed 9-3, and "
    "all three dissenters wanted the target range 1/4 point higher, not lower.",
    "One phrase of policy language moved with them. The reserves sentence went "
    "from reaffirmed to is continuing.",
]
CLEAN_HOOK = ("Fed held at 3-1/2 to 3-3/4 percent and barely touched the "
              "statement. The vote did the moving. 12-0 became 9-3, and all "
              "three dissenters wanted a hike, not a cut.")
CLEAN_RELAY = ("The Federal Open Market Committee held the target range for the "
               "federal funds rate at 3-1/2 to 3-3/4 percent. The vote was 9-3. "
               "Hammack, Kashkari and Logan preferred to raise the range by 1/4 "
               "percentage point.")


def _reply(analysis: list[str], hook: str, relay: str) -> str:
    return ("ANALYSIS\n" + "\n\n".join(analysis) + "\n\nHOOK\n" + hook
            + "\n\nRELAY\n" + relay + "\n")


CLEAN_REPLY = _reply(CLEAN_ANALYSIS, CLEAN_HOOK, CLEAN_RELAY)
DIRTY_REPLY = _reply(
    CLEAN_ANALYSIS + ["Traders now price a 70 percent chance of a cut."],
    CLEAN_HOOK, CLEAN_RELAY)


@pytest.fixture
def sheet(diff, facts, june, july) -> dict:
    rows = fomc_desk.card_highlights(diff, facts, july, limit=6)
    return fomc_desk.build_fact_sheet(
        date_str=JULY, prior_date=JUNE, current_paragraphs=july,
        prior_paragraphs=june, diff=diff, facts=facts, highlight_rows=rows,
    )


def _stub_waterfall(monkeypatch, replies: list[str]) -> dict:
    """Point llm_auth at a canned reply sequence. Returns a call counter."""
    from engine import llm_auth

    calls = {"n": 0}

    def _providers(cfg, **kwargs):
        calls["cfg"] = cfg
        return [{"name": "stub", "client": object(), "model": "stub-1"}]

    def _call(providers, call_fn, *, context=""):
        idx = calls["n"]
        calls["n"] += 1
        calls.setdefault("contexts", []).append(context)
        if idx >= len(replies):
            return None, "exhausted", None
        return replies[idx], None, "stub"

    monkeypatch.setattr(llm_auth, "build_providers", _providers)
    monkeypatch.setattr(llm_auth, "make_call", _call)
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    return calls


def test_prompt_contract(sheet):
    """The prompt states every law the validator enforces."""
    system = fomc_desk.build_system_prompt()
    for label in ("ANALYSIS", "HOOK", "RELAY"):
        assert f"\n{label}\n" in system
    assert "traces to the material you were given" in system
    assert "No em dashes" in system
    assert "No hashtags" in system
    assert "No advice" in system
    assert "WIRE REGISTER" in system
    assert str(fomc_desk.POST_MAX_CHARS) in system

    user = fomc_desk.build_user_message(sheet)
    # The diff, the facts and BOTH statements verbatim.
    assert "carried over VERBATIM: 6" in user
    assert "3-1/2 to 3-3/4 percent" in user
    assert "reaffirmed" in user and "is continuing" in user
    assert "Beth M. Hammack" in user
    assert "ALLOWED NUMBERS" in user
    for number in ("12-0", "9-3", "1/4", "3-1/2", "3-3/4"):
        assert f"  {number}" in user, number


def test_writer_clean_draft_validates(monkeypatch, sheet):
    calls = _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    out = fomc_desk.write_copy(sheet, cfg={"fomc_desk": {"llm": {"enabled": True}}})
    assert out["mode"] == "llm"
    assert calls["n"] == 1, "a clean draft must not pay for a repair turn"
    assert len(out["analysis"]) == 3
    assert out["hook"] == CLEAN_HOOK
    assert out["relay"] == CLEAN_RELAY
    assert not any(out["violations"].values())
    # The lane's own usage attribution, so ai_costs can see this desk.
    assert calls["cfg"]["usage_lane"] == "marketing-fomc"
    assert calls["cfg"]["provider_order"][0] == "codex"
    assert calls["cfg"]["codex_source_model"] == "gpt-5.6-sol"


def test_writer_takes_exactly_one_repair_turn(monkeypatch, sheet):
    calls = _stub_waterfall(monkeypatch, [DIRTY_REPLY, CLEAN_REPLY])
    out = fomc_desk.write_copy(sheet, cfg={"fomc_desk": {"llm": {"enabled": True}}})
    assert out["mode"] == "llm_repair"
    assert calls["n"] == 2
    assert calls["contexts"] == ["fomc_desk", "fomc_desk_repair"]
    assert not any(out["violations"].values())


def test_writer_gives_up_after_one_repair(monkeypatch, sheet):
    calls = _stub_waterfall(monkeypatch, [DIRTY_REPLY, DIRTY_REPLY])
    out = fomc_desk.write_copy(sheet, cfg={"fomc_desk": {"llm": {"enabled": True}}})
    assert calls["n"] == 2, "strictly ONE repair turn"
    assert out["mode"] in ("fallback_validation", "partial")
    assert out["violations"]["analysis"], "the analysis violation must be named"


def test_writer_disarmed_makes_no_call(monkeypatch, sheet):
    calls = _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    out = fomc_desk.write_copy(sheet, cfg={"fomc_desk": {"llm": {"enabled": False}}})
    assert out["mode"] == "off"
    assert calls["n"] == 0
    # And the env flag alone is not enough either.
    monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
    out2 = fomc_desk.write_copy(sheet, cfg={"fomc_desk": {"llm": {"enabled": True}}})
    assert out2["mode"] == "off"
    assert calls["n"] == 0


def test_writer_total_provider_failure(monkeypatch, sheet, capsys):
    from engine import llm_auth

    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_auth, "build_providers", lambda cfg, **kw: [])
    out = fomc_desk.write_copy(sheet, cfg={"fomc_desk": {"llm": {"enabled": True}}})
    assert out["mode"] == "fallback_provider"
    assert out["analysis"] == [] and out["hook"] == ""
    lines = capsys.readouterr().out.splitlines()
    assert any(ln.startswith("::warning title=fomc_desk_mute") for ln in lines), lines


def test_writer_survives_a_raising_provider(monkeypatch, sheet):
    from engine import llm_auth

    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_auth, "build_providers",
                        lambda cfg, **kw: [{"name": "stub", "client": object(),
                                            "model": "m"}])

    def _boom(*a, **k):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(llm_auth, "make_call", _boom)
    out = fomc_desk.write_copy(sheet, cfg={"fomc_desk": {"llm": {"enabled": True}}})
    assert out["mode"] == "fallback_provider"


def test_validator_rejects_an_invented_number(sheet):
    parsed = fomc_desk.parse_sections(DIRTY_REPLY)
    violations = fomc_desk.validate_copy(parsed, sheet)
    assert any("70" in v for v in violations["analysis"]), violations["analysis"]
    # The hook and the relay were clean and must be reported clean.
    assert violations["hook"] == []
    assert violations["relay"] == []


def test_validator_rejects_a_stance_on_the_wire_relay(sheet):
    parsed = fomc_desk.parse_sections(_reply(
        CLEAN_ANALYSIS, CLEAN_HOOK,
        "Fed held at 3-1/2 to 3-3/4 percent on a 9-3 vote. We read the three "
        "dissents as hawkish."))
    violations = fomc_desk.validate_copy(parsed, sheet)
    assert violations["relay"], "a first-person read is a stance"
    assert violations["analysis"] == []


def test_stance_screen_matches_whole_words_not_substrings(sheet):
    """"four" is not "our", and "week" is not "we".

    Regression pin: the screen space-padded its tells and tested `in`, so "our "
    matched inside "four " and a clean relay containing the word "four" was
    rejected as a first-person stance. That silently downgrades a good model relay
    to the template, which is a quality loss nothing else would have reported.
    """
    innocent = ("The Federal Open Market Committee held the target range for the "
                "federal funds rate at 3-1/2 to 3-3/4 percent. The vote was 9-3. "
                "Four members spoke this week about myriad shocks.")
    parsed = fomc_desk.parse_sections(_reply(CLEAN_ANALYSIS, CLEAN_HOOK, innocent))
    stance = [v for v in fomc_desk.validate_copy(parsed, sheet)["relay"]
              if "no stance" in v]
    assert stance == [], stance

    # And the real tells still fire, as whole words.
    for guilty in ("We read the vote as hawkish.", "Our view is that it means a pause.",
                   "I am watching the range."):
        text = ("The Committee held the target range at 3-1/2 to 3-3/4 percent on "
                f"a 9-3 vote. {guilty}")
        parsed = fomc_desk.parse_sections(_reply(CLEAN_ANALYSIS, CLEAN_HOOK, text))
        assert [v for v in fomc_desk.validate_copy(parsed, sheet)["relay"]
                if "no stance" in v], guilty


def test_validator_requires_the_relay_to_state_range_and_vote(sheet):
    parsed = fomc_desk.parse_sections(_reply(
        CLEAN_ANALYSIS, CLEAN_HOOK, "The Federal Reserve made a decision today."))
    violations = fomc_desk.validate_copy(parsed, sheet)
    assert any("target range" in v for v in violations["relay"])
    assert any("vote" in v for v in violations["relay"])


def test_validator_rejects_hashtags_exclamations_and_overlong_copy(sheet):
    parsed = fomc_desk.parse_sections(_reply(
        CLEAN_ANALYSIS, "Fed held at 3-1/2 to 3-3/4 percent! #FOMC", CLEAN_RELAY))
    violations = fomc_desk.validate_copy(parsed, sheet)
    assert any("hashtag" in v for v in violations["hook"])
    assert any("exclamation" in v for v in violations["hook"])

    long_hook = "Fed held at 3-1/2 to 3-3/4 percent. " * 20
    parsed2 = fomc_desk.parse_sections(_reply(CLEAN_ANALYSIS, long_hook, CLEAN_RELAY))
    assert any("maximum is 280" in v
               for v in fomc_desk.validate_copy(parsed2, sheet)["hook"])


def test_validator_rejects_advice_and_forecasts(sheet):
    parsed = fomc_desk.parse_sections(_reply(
        ["We expect a cut at the next meeting.", "You should buy duration here."],
        CLEAN_HOOK, CLEAN_RELAY))
    violations = fomc_desk.validate_copy(parsed, sheet)["analysis"]
    assert any("forecast" in v for v in violations), violations
    assert any("advice" in v for v in violations), violations


def test_validator_enforces_the_paragraph_budget(sheet):
    one = fomc_desk.parse_sections(_reply([CLEAN_ANALYSIS[0]], CLEAN_HOOK, CLEAN_RELAY))
    assert any("minimum is 2" in v
               for v in fomc_desk.validate_copy(one, sheet)["analysis"])
    five = fomc_desk.parse_sections(
        _reply(CLEAN_ANALYSIS + CLEAN_ANALYSIS, CLEAN_HOOK, CLEAN_RELAY))
    assert any("maximum is 4" in v
               for v in fomc_desk.validate_copy(five, sheet)["analysis"])


def test_parse_sections_is_tolerant_of_labels_and_quotes():
    parsed = fomc_desk.parse_sections(
        "ANALYSIS:\nFirst para.\n\nSecond para.\n\nhook:\n\"A hook line.\"\n\n"
        " RELAY \nA relay line.\n")
    assert parsed["analysis"] == ["First para.", "Second para."]
    assert parsed["hook"] == "A hook line."
    assert parsed["relay"] == "A relay line."


def test_parse_sections_of_garbage_yields_empties():
    parsed = fomc_desk.parse_sections("I cannot help with that request.")
    assert parsed == {"analysis": [], "hook": "", "relay": ""}


def test_untraceable_numbers_folds_the_feds_dash():
    corpus = "by a 9 – 3 vote at 3-1/2 to 3-3/4 percent by 1/4 percentage point"
    assert fomc_desk.untraceable_numbers("9-3 and 3-1/2 and 1/4", corpus) == []
    assert fomc_desk.untraceable_numbers("a 70 percent chance", corpus) == ["70"]
    # A compound the corpus GAVE us may be decomposed: "the vote was 9 to 3".
    assert fomc_desk.untraceable_numbers("the vote was 9 to 3", corpus) == []


def test_traceability_is_token_boundary_not_substring(sheet):
    """Single digits must not ride inside a longer corpus number.

    SURVIVING MUTATION THE OLD TESTS MISSED: `token in normalized_corpus`. Under
    substring containment 14 of the integers 0-99 passed free — "7" and "9" inside
    the fact sheet's own header date "2026-07-29", "5" inside a "3-1/2", and so on.
    Every integer below is absent from the July material as a TOKEN, and each one
    is a substring of something in it.
    """
    corpus = fomc_desk.fact_sheet_text(sheet)
    # Multi-digit inventions, each a substring of something in the material.
    for invented in ("70", "45", "26", "20", "07", "29", "202"):
        assert fomc_desk.untraceable_numbers(f"a level of {invented}", corpus), \
            f"{invented} passed the traceability guard"
    # SINGLE DIGITS TOO. Surviving mutation this closes: "skip tokens shorter than
    # two characters", which is the cheapest way to make the whole guard blind to
    # the numbers most likely to be fabricated in a rate post. 5 and 7 appear
    # nowhere in the July material once the header dates are excluded.
    for invented in ("5", "7"):
        assert fomc_desk.untraceable_numbers(f"about {invented} percent", corpus), \
            f"single digit {invented} passed the traceability guard"
    # The control: digits the material really does contain still pass.
    for supported in ("9", "3", "12", "1/4", "3-1/2"):
        assert fomc_desk.untraceable_numbers(f"{supported} here", corpus) == [], \
            supported


def test_iso_header_dates_do_not_donate_numbers(sheet):
    """The fact sheet's own YYYY-MM-DD header is excluded from the corpus.

    Otherwise our bookkeeping launders numbers the statement never contained.
    """
    corpus = fomc_desk.fact_sheet_text(sheet)
    assert "2026-07-29" in corpus, "the header really is in the text"
    assert fomc_desk.untraceable_numbers("2026", corpus) == ["2026"]
    # And the prompt advertises exactly what the validator enforces.
    allowed = fomc_desk.build_user_message(sheet).split("ALLOWED NUMBERS")[1]
    assert "2026-07-29" not in allowed
    assert "2026-06-17" not in allowed


def test_spelled_out_counts_must_trace_in_a_quantitative_use(sheet):
    """"Nine of twelve members" is a claim about a vote count and must trace."""
    corpus = fomc_desk.fact_sheet_text(sheet)
    # 7 and 11 are nowhere in the July material.
    assert fomc_desk.untraceable_numbers("seven of eleven members agreed", corpus)
    # 6 and 9 are (unchanged=6, sentences=9), so this is fine.
    assert fomc_desk.untraceable_numbers("six of nine sentences", corpus) == []
    # ORDINARY ENGLISH IS NOT AUDITED: "one phrase" is not a quantitative use, and
    # flagging it would cost a repair turn on correct copy.
    assert fomc_desk.untraceable_numbers(
        "One phrase of policy language moved with them", corpus) == []


def test_forecast_tells_catch_the_market_pricing_family(sheet):
    """Measured misses. The statement never says what anything is priced at."""
    for guilty in (
        "Traders had priced a deeper move.",
        "Options pricing implies a move by December.",
        "There is a chance of another hold.",
        "We see a 12 percent chance of a hike.",
        "Markets expect the range to move.",
        "Futures are pricing in a hold.",
    ):
        parsed = fomc_desk.parse_sections(_reply(
            [CLEAN_ANALYSIS[0], guilty], CLEAN_HOOK, CLEAN_RELAY))
        violations = fomc_desk.validate_copy(parsed, sheet)["analysis"]
        assert any("forecast" in v for v in violations), guilty


def test_forecast_tells_apply_to_the_hook_as_well_as_the_analysis(sheet):
    parsed = fomc_desk.parse_sections(_reply(
        CLEAN_ANALYSIS,
        "Fed held at 3-1/2 to 3-3/4 percent. Markets expect a cut next.",
        CLEAN_RELAY))
    assert any("forecast" in v
               for v in fomc_desk.validate_copy(parsed, sheet)["hook"])


def test_relay_presence_guards_are_not_vacuous_on_single_digits():
    """A single-digit head or vote is a substring of nearly any number.

    SURVIVING MUTATION: substring matching in the range/vote presence checks. With
    a ZIRP range whose head is "0" and a vote of 9, a relay naming neither still
    contains a "0" and a "9" inside other numbers, so `in` passed it.
    """
    facts = {"target_range": "0 to 1/4 percent", "action": "maintain",
             "vote": {"for": 9, "against": 0}, "unanimous": False,
             "dissenters": None, "dissent_preference": None, "dissent_size": None,
             "dissent_groups": None}
    sheet = fomc_desk.build_fact_sheet(
        date_str=JULY, prior_date=JUNE, current_paragraphs=[], prior_paragraphs=[],
        diff={}, facts=facts, highlight_rows=[])
    parsed = fomc_desk.parse_sections(_reply(
        ["Paragraph one here.", "Paragraph two here."],
        "A hook line about the decision.",
        "The Committee acted on 90 different considerations and 109 pages."))
    violations = fomc_desk.validate_copy(parsed, sheet)["relay"]
    assert any("target range" in v for v in violations), violations
    assert any("vote" in v for v in violations), violations


# ─────────────────────────────────────────────────────────────────────────────
# 14-15. Firing: enqueue shape, routing fallback, idempotency
# ─────────────────────────────────────────────────────────────────────────────

def test_fire_enqueues_both_desks_in_routing_fallback_mode(
    monkeypatch, seeded_root, desk_cfg, july_page, hosted_card,
):
    """Both posts, both desks, immediate rail, event_class fomc.

    "Fallback mode" = no `wire_routing.classes` in the config, i.e. the world
    before the sibling W3 lane declares an `fomc` class. This desk must route
    itself there.
    """
    _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    report = fomc_desk.fire(date_str=JULY, root=seeded_root, cfg=desk_cfg,
                            now=NOW, html_text=july_page)
    assert report["fired"] is True
    assert report["mode"] == "llm"
    assert report["accounts"] == {"analysis": "flagship",
                                 "relay": "mastermind_news",
                                 "source": "config"}
    assert len(report["emitted"]) == 2

    by_role = {i["fomc_role"]: i for i in report["emitted"]}
    assert set(by_role) == {"analysis", "relay"}
    for role, item in by_role.items():
        assert item["kind"] == "breaking"
        assert item["scheduled_at"] == "immediate"
        assert item["immediate"] is True
        assert item["event_class"] == "fomc"
        assert item["provenance"] == "fomc_desk"
        assert item["fomc_date"] == JULY
        assert item["as_of"] == "2026-07-29"
        assert item["status"] == "queued"
        assert item["source"]["kind"] == "fomc_statement"
        assert item["source"]["url"].endswith("monetary20260729a.htm")
        assert 0 < len(item["text"]) <= fomc_desk.POST_MAX_CHARS
        assert "#" not in item["text"] and "!" not in item["text"]

    analysis, relay = by_role["analysis"], by_role["relay"]
    assert analysis["account"] == "flagship"
    assert relay["account"] == "mastermind_news"
    # The hook is the post body; the analysis itself rides on the card.
    assert analysis["text"] == CLEAN_HOOK
    assert analysis["media"] and analysis["media"][0]["kind"] == "chart_svg"
    assert analysis["media"][0]["chart_id"] == f"fomc-{JULY}"
    # A relay is text only: the wire states the decision, it does not illustrate it.
    assert relay["media"] == []

    # The items really are in the queue, not just returned.
    from engine.marketing import outbox

    queued = {i["id"] for i in outbox.read_items_all(seeded_root)}
    assert {i["id"] for i in report["emitted"]} <= queued


def test_fire_is_idempotent_per_meeting(monkeypatch, seeded_root, desk_cfg,
                                       july_page, hosted_card):
    """Second firing for the same meeting no-ops. One meeting, one firing."""
    _stub_waterfall(monkeypatch, [CLEAN_REPLY, CLEAN_REPLY, CLEAN_REPLY])
    first = fomc_desk.fire(date_str=JULY, root=seeded_root, cfg=desk_cfg,
                           now=NOW, html_text=july_page)
    assert first["fired"] is True

    second = fomc_desk.fire(date_str=JULY, root=seeded_root, cfg=desk_cfg,
                            now=NOW, html_text=july_page)
    assert second["fired"] is False
    assert second["reason"] == "already_fired"
    assert second["emitted"] == []

    from engine.marketing import outbox

    assert len(outbox.read_items_all(seeded_root)) == 2, "no second pair of posts"


STATEMENT_ITEM = {
    "id": "fed-1", "source": "fed_press", "source_name": "Federal Reserve",
    "source_tier": "official",
    "url": ("https://www.federalreserve.gov/newsevents/pressreleases/"
            "monetary20260729a.htm"),
    "published_at": "2026-07-29T18:00:00Z",
    "headline": "Federal Reserve issues FOMC statement",
}


def test_maybe_fire_trigger_and_its_idempotency(
    monkeypatch, seeded_root, desk_cfg, july_page, hosted_card,
):
    """The press-tick seam fires once, then never again for this meeting."""
    _stub_waterfall(monkeypatch, [CLEAN_REPLY, CLEAN_REPLY])
    monkeypatch.setattr(fomc_statements, "fetch_page", lambda url, **kw: july_page)

    first = fomc_desk.maybe_fire([dict(STATEMENT_ITEM)], root=seeded_root,
                                 cfg=desk_cfg, now=NOW)
    assert first and first["fired"] is True
    assert fomc_desk.maybe_fire([dict(STATEMENT_ITEM)], root=seeded_root,
                                cfg=desk_cfg, now=NOW) is None


def test_maybe_fire_keeps_scanning_past_an_out_of_scope_item(
    monkeypatch, seeded_root, desk_cfg, july_page, hosted_card,
):
    """An archive item AHEAD of the live statement must not cost the meeting.

    SURVIVING MUTATION THIS CLOSES: `return None` in the item-rejection branch. The
    Fed's feed is not ordered for our convenience and it carries archive links and
    reissues beside the fresh release, so the first statement-shaped item in a batch
    is routinely not the one we want. Bailing out on it loses the meeting entirely.

    Written against the REJECTION branch on purpose. The sibling
    `already_collected` branch also continues, but that one is defensive rather
    than observable: exactly one meeting is ever in a tick's scope (the two
    candidate dates can never both be decision days, since a meeting's decision day
    is its second), so every item resolving in a tick resolves to the SAME date and
    "already collected" is true for all of them or none. Asserting a difference
    there would be a test of nothing.
    """
    _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    monkeypatch.setattr(fomc_statements, "fetch_page", lambda url, **kw: july_page)

    ahead = [
        # An archive link to a past meeting, statement-shaped and first in line.
        {"source": "fed_press",
         "headline": "Federal Reserve issues FOMC statement",
         "url": ("https://www.federalreserve.gov/newsevents/pressreleases/"
                 "monetary20260617a.htm")},
        # A statement-shaped item with no date in its URL at all.
        {"source": "fed_press",
         "headline": "Federal Reserve issues FOMC statement",
         "url": "https://www.federalreserve.gov/newsevents/pressreleases.htm"},
    ]
    # The dateless item resolves to today, so put the live one first among the
    # DATED items and prove the archive link does not stop the walk.
    report = fomc_desk.maybe_fire([ahead[0], dict(STATEMENT_ITEM)],
                                  root=seeded_root, cfg=desk_cfg, now=NOW)
    assert report is not None, "the archive item must not end the scan"
    assert report["fired"] is True
    assert report["date"] == JULY
    assert len(report["emitted"]) == 2


def test_a_stale_url_on_a_real_decision_day_is_rejected(
    monkeypatch, seeded_root, desk_cfg, july_page,
):
    """A 2019 archive URL arriving on 2026-07-29 must not be posted as today.

    SURVIVING MUTATION THE OLD TEST MISSED: dating from the clock while fetching
    the ITEM's url. The old `meeting_date_for` fell back to the clock whenever the
    URL date was not a decision day, and `fire` then fetched the item's URL — so a
    2019 statement was stored as 2026-07-29.txt, diffed against June 2026, and
    posted as today's decision, consuming the meeting's one firing.
    """
    fetched: list[str] = []

    def _fetch(url, **kw):
        fetched.append(url)
        return july_page

    _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    monkeypatch.setattr(fomc_statements, "fetch_page", _fetch)

    stale = {
        "source": "fed_press",
        "headline": "Federal Reserve issues FOMC statement",
        "url": ("https://www.federalreserve.gov/newsevents/pressreleases/"
                "monetary20190918a.htm"),
    }
    assert fomc_desk.is_statement_release(stale), "it IS statement-shaped"
    assert fomc_desk.resolve_meeting(stale, now=NOW) is None
    assert fomc_desk.maybe_fire([stale], root=seeded_root, cfg=desk_cfg,
                                now=NOW) is None
    assert fetched == [], "nothing may be fetched for a rejected item"
    assert not fomc_statements.is_collected(JULY, seeded_root)
    assert fomc_statements.read_statement(JULY, seeded_root) == []


def test_a_dateless_url_is_fetched_from_the_canonical_url(monkeypatch, seeded_root,
                                                          desk_cfg, july_page,
                                                          hosted_card):
    """When the clock dates the item, the fetch uses OUR url, never the item's."""
    fetched: list[str] = []

    def _fetch(url, **kw):
        fetched.append(url)
        return july_page

    _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    monkeypatch.setattr(fomc_statements, "fetch_page", _fetch)
    item = {"source": "fed_press",
            "headline": "Federal Reserve issues FOMC statement",
            "url": "https://www.federalreserve.gov/newsevents/pressreleases.htm"}
    report = fomc_desk.maybe_fire([item], root=seeded_root, cfg=desk_cfg, now=NOW)
    assert report and report["fired"] is True
    assert fetched == [fomc_statements.statement_url(JULY)]


def test_release_dates_use_new_york_not_a_fixed_offset():
    """14:00 ET is 18:00 UTC under EDT. Sep and Oct 2026 are both EDT.

    SURVIVING MUTATION: a hardcoded UTC-5. It gives the wrong ET date for every
    EDT meeting whenever the two calendars disagree, which is what a flat offset
    cannot know.
    """
    # 2026-09-16 18:05 UTC is 14:05 EDT: the September decision day resolves.
    edt_tick = datetime(2026, 9, 16, 18, 5, tzinfo=timezone.utc)
    assert fomc_desk._et_candidate_dates(edt_tick)[0] == "2026-09-16"

    # THE DIVERGENCE. 2026-09-17 04:30 UTC is 00:30 EDT on the 17th, so the
    # September meeting is OVER. A flat UTC-5 reads it as 23:30 on the 16th and
    # would still call that a decision day — the desk would treat a closed meeting
    # as live. This is the assertion a hardcoded offset cannot pass.
    after_edt_midnight = datetime(2026, 9, 17, 4, 30, tzinfo=timezone.utc)
    dates = fomc_desk._et_candidate_dates(after_edt_midnight)
    assert dates[0] == "2026-09-17", dates
    assert "2026-09-16" not in dates, dates
    assert fomc_desk.resolve_meeting(
        {"source": "fed_press", "headline": "Federal Reserve issues FOMC statement",
         "url": "https://www.federalreserve.gov/newsevents/pressreleases.htm"},
        now=after_edt_midnight) is None

    # EST side, where the two agree: the retry window still names December's day.
    est_tick = datetime(2026, 12, 10, 0, 30, tzinfo=timezone.utc)
    assert "2026-12-09" in fomc_desk._et_candidate_dates(est_tick)


def test_trigger_predicate_is_narrow():
    """Only the Fed's own statement release fires this desk."""
    statement = {
        "source": "fed_press",
        "headline": "Federal Reserve issues FOMC statement",
        "url": ("https://www.federalreserve.gov/newsevents/pressreleases/"
                "monetary20260729a.htm"),
    }
    assert fomc_desk.is_statement_release(statement)
    assert fomc_desk.meeting_date_for(statement, now=NOW) == JULY

    # A URL-only match still fires: the release-letter path names its own date.
    assert fomc_desk.is_statement_release({
        "source": "fed_press", "headline": "Federal Reserve press release",
        "url": ("https://www.federalreserve.gov/newsevents/pressreleases/"
                "monetary20260916a.htm")})

    # Not the Fed's feed, not this desk's event, even with a matching headline.
    assert not fomc_desk.is_statement_release({
        "source": "cnbc_top", "headline": "Fed issues FOMC statement"})
    # The MINUTES are a different release three weeks later.
    assert not fomc_desk.is_statement_release({
        "source": "fed_press",
        "headline": "Minutes of the Federal Open Market Committee, June 16-17, 2026",
        "url": "https://www.federalreserve.gov/monetarypolicy/fomcminutes20260617.htm"})
    # A speech is not a statement.
    assert not fomc_desk.is_statement_release({
        "source": "fed_press",
        "headline": "Speech by Chair Powell on the economic outlook",
        "url": "https://www.federalreserve.gov/newsevents/speech/powell20260801a.htm"})
    assert not fomc_desk.is_statement_release({})

    # A statement-shaped item on a NON-decision day yields no meeting date.
    assert fomc_desk.meeting_date_for(
        {"source": "fed_press", "headline": "Federal Reserve issues FOMC statement",
         "url": "https://www.federalreserve.gov/newsevents/pressreleases/"
                "monetary20260801a.htm"},
        now=datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc)) is None


def test_maybe_fire_is_inert_when_disabled(seeded_root, july_page):
    cfg = {"fomc_desk": {"enabled": False, "llm": {"enabled": False}}}
    item = {"source": "fed_press", "headline": "Federal Reserve issues FOMC statement",
            "url": ("https://www.federalreserve.gov/newsevents/pressreleases/"
                    "monetary20260729a.htm")}
    assert fomc_desk.maybe_fire([item], root=seeded_root, cfg=cfg, now=NOW) is None
    assert fomc_statements.ledger_rows(seeded_root) == []


def test_llm_failure_skips_the_flagship_but_still_relays(
    monkeypatch, seeded_root, desk_cfg, july_page, capsys,
):
    """THE NO-FALLBACK SPLIT, end to end.

    A mute waterfall must not produce a templated house read; it must produce the
    templated WIRE relay and nothing else.
    """
    from engine import llm_auth

    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_auth, "build_providers", lambda cfg, **kw: [])
    report = fomc_desk.fire(date_str=JULY, root=seeded_root, cfg=desk_cfg,
                            now=NOW, html_text=july_page)
    assert report["fired"] is True
    assert report["mode"] == "fallback_provider"
    assert len(report["emitted"]) == 1
    only = report["emitted"][0]
    assert only["fomc_role"] == "relay"
    assert only["account"] == "mastermind_news"
    assert only["event_class"] == "fomc"
    # The deterministic relay states the decision, the range and the vote.
    assert "3-1/2 to 3-3/4 percent" in only["text"]
    assert "9-3" in only["text"]
    assert len(only["text"]) <= fomc_desk.POST_MAX_CHARS

    lines = capsys.readouterr().out.splitlines()
    assert any(ln.startswith("::warning title=fomc-analysis-skipped")
               for ln in lines), lines


def test_partial_copy_ships_the_clean_relay_and_skips_the_analysis(
    monkeypatch, seeded_root, desk_cfg, july_page,
):
    """A draft whose analysis invented a number keeps its clean relay."""
    _stub_waterfall(monkeypatch, [DIRTY_REPLY, DIRTY_REPLY])
    report = fomc_desk.fire(date_str=JULY, root=seeded_root, cfg=desk_cfg,
                            now=NOW, html_text=july_page)
    assert report["fired"] is True
    roles = {i["fomc_role"] for i in report["emitted"]}
    assert roles == {"relay"}, "the flagship analysis must not ship"
    assert report["emitted"][0]["text"] == CLEAN_RELAY


def test_no_prior_statement_stores_the_baseline_and_posts_nothing(
    monkeypatch, tmp_path, desk_cfg, july_page, capsys,
):
    """A diff desk with no baseline has no product, and says so.

    The statement is still stored, so the NEXT meeting has its baseline: the desk
    seeds itself rather than needing a backfill.
    """
    _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    report = fomc_desk.fire(date_str=JULY, root=tmp_path, cfg=desk_cfg,
                            now=NOW, html_text=july_page)
    assert report["fired"] is False
    assert report["reason"] == "no_prior_statement"
    assert report["emitted"] == []
    assert fomc_statements.read_statement(JULY, tmp_path), "baseline still stored"
    assert fomc_statements.is_collected(JULY, tmp_path), "and marked done"
    lines = capsys.readouterr().out.splitlines()
    assert any(ln.startswith("::warning title=fomc-no-baseline") for ln in lines)


def test_dry_run_writes_no_queue_and_no_store(
    monkeypatch, seeded_root, desk_cfg, july_page, hosted_card,
):
    """`--dry-run` must not enqueue, claim the meeting, OR touch the store.

    SURVIVING MUTATION THE OLD TEST MISSED: collect() wrote the store
    unconditionally. The press wire has a --dry-run mode, so a read-only rehearsal
    was overwriting the very file the NEXT meeting diffs against.
    """
    _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    report = fomc_desk.fire(date_str=JULY, root=seeded_root, cfg=desk_cfg,
                            now=NOW, html_text=july_page, dry_run=True)
    assert report["fired"] is True
    assert len(report["emitted"]) == 2

    from engine.marketing import outbox

    assert outbox.read_items_all(seeded_root) == []
    assert not fomc_statements.is_collected(JULY, seeded_root), \
        "a dry run may not consume the one firing this meeting gets"
    assert fomc_statements.read_statement(JULY, seeded_root) == [], \
        "a dry run may not write the store"
    assert fomc_statements.ledger_rows(seeded_root) == []
    # And the June baseline it read is byte-identical to the committed seed.
    assert fomc_statements.read_statement(JUNE, seeded_root) == \
        fomc_statements.read_statement(JUNE, ROOT)


def test_dry_run_on_a_missing_baseline_writes_nothing_either(
    monkeypatch, tmp_path, desk_cfg, july_page,
):
    """The no_prior_statement path also has a ledger write to suppress."""
    _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    report = fomc_desk.fire(date_str=JULY, root=tmp_path, cfg=desk_cfg, now=NOW,
                            html_text=july_page, dry_run=True)
    assert report["reason"] == "no_prior_statement"
    assert fomc_statements.ledger_rows(tmp_path) == []
    assert fomc_statements.read_statement(JULY, tmp_path) == []


def test_a_broken_renderer_skips_the_flagship_but_the_relay_STILL_SHIPS(
    monkeypatch, seeded_root, desk_cfg, july_page, capsys,
):
    """M5. "A picture may degrade, never block" — structurally, not by inspection.

    SURVIVING MUTATION THE OLD TEST ENSHRINED: the old test asserted
    fired=False, i.e. it pinned the DEFECT while its own docstring claimed the
    opposite. An exception in the card path propagated past the relay emit and
    killed both posts.
    """
    _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    from engine.marketing import fomc_card

    def _boom(**kwargs):
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr(fomc_card, "render_fomc_card", _boom)
    report = fomc_desk.fire(date_str=JULY, root=seeded_root, cfg=desk_cfg,
                            now=NOW, html_text=july_page)
    assert report["fired"] is True, "the relay must still go out"
    assert [i["fomc_role"] for i in report["emitted"]] == ["relay"]
    assert report["emitted"][0]["account"] == "mastermind_news"
    assert report["emitted"][0]["text"] == CLEAN_RELAY
    lines = capsys.readouterr().out.splitlines()
    assert any(ln.startswith("::warning title=fomc-analysis-post-failed")
               for ln in lines), lines


def test_an_unhosted_card_skips_the_flagship_but_the_relay_STILL_SHIPS(
    monkeypatch, seeded_root, desk_cfg, july_page, capsys,
):
    """M6. A hook with no card is a post about nothing, and loses the analysis."""
    _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    from engine.marketing import media_publish

    # publish_card succeeds locally but cannot reach R2 — the real failure shape.
    monkeypatch.setattr(
        media_publish, "publish_card",
        lambda svg, **kw: {"svg_path": "data/marketing/outbox/media/x.svg",
                           "media_png_path": "data/marketing/outbox/media/x.png",
                           "media_render": "svg_raster", "media_url": None})
    report = fomc_desk.fire(date_str=JULY, root=seeded_root, cfg=desk_cfg,
                            now=NOW, html_text=july_page)
    assert report["fired"] is True
    assert report["card_hosted"] is False
    assert [i["fomc_role"] for i in report["emitted"]] == ["relay"]
    lines = capsys.readouterr().out.splitlines()
    assert any(ln.startswith("::warning title=fomc-card-unhosted") for ln in lines)


def test_a_hosted_card_ships_the_flagship(monkeypatch, seeded_root, desk_cfg,
                                          july_page):
    """The positive control for the two tests above."""
    _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    from engine.marketing import media_publish

    monkeypatch.setattr(
        media_publish, "publish_card",
        lambda svg, **kw: {"svg_path": "data/marketing/outbox/media/x.svg",
                           "media_png_path": "data/marketing/outbox/media/x.png",
                           "media_render": "svg_raster",
                           "media_url": "https://cdn.example.com/x.png"})
    report = fomc_desk.fire(date_str=JULY, root=seeded_root, cfg=desk_cfg,
                            now=NOW, html_text=july_page)
    assert report["card_hosted"] is True
    by_role = {i["fomc_role"]: i for i in report["emitted"]}
    assert set(by_role) == {"analysis", "relay"}
    assert by_role["analysis"]["media"][0]["media_url"] == \
        "https://cdn.example.com/x.png"


# ─────────────────────────────────────────────────────────────────────────────
# The environment this lane actually runs in
# ─────────────────────────────────────────────────────────────────────────────

def test_press_wire_workflow_covers_the_store():
    """The press-wire workflow must be able to READ and WRITE the desk's store.

    THE BLOCKER THIS PINS. `.github/workflows/marketing-press-wire.yml` runs this
    desk on ubuntu with a SPARSE CHECKOUT, every 5 minutes, and stages only its own
    paths. The store originally lived at `data/fomc/`, which is in neither list. On
    the live 2026-09-16 firing that means: the baseline statement and the ledger are
    not on disk, so every tick reads [] and refuses for `no_prior_statement`;
    federalreserve.gov is fetched 288 times; every collected file is discarded at
    job end, so the NEXT meeting has no baseline either; and the ledger never
    survives a tick, so "one firing per meeting" is not true.

    None of that is visible from inside the module, and no unit test with a
    tmp_path root can see it — which is exactly why this string-level check on the
    YAML exists.
    """
    workflow = (ROOT / ".github" / "workflows" / "marketing-press-wire.yml")
    text = workflow.read_text(encoding="utf-8")
    store_root = fomc_statements.STORE_ROOT.as_posix()   # data/marketing/fomc

    # READ: some prefix of the store root is in the sparse-checkout cone.
    cone = text.split("sparse-checkout: |", 1)[1].split("token:", 1)[0]
    cone_paths = [ln.strip() for ln in cone.splitlines() if ln.strip()]
    assert any(store_root == p or store_root.startswith(p.rstrip("/") + "/")
               for p in cone_paths), (
        f"{store_root} is outside the sparse cone {cone_paths}: the desk would "
        "read no baseline and no ledger on the runner")

    # WRITE: the store root (or a prefix of it) is staged for commit.
    staged = re.findall(r"git add (\S+)", text)
    assert any(store_root == p or store_root.startswith(p.rstrip("/") + "/")
               for p in staged), (
        f"{store_root} is never staged ({staged}): everything the desk collects "
        "is discarded when the job ends")

    # And the store is NOT at the old, uncovered location.
    assert not (ROOT / "data" / "fomc").exists(), \
        "the pre-relocation store is still on disk"


def test_committed_store_is_where_the_module_says_it_is():
    for date_str in (JUNE, JULY):
        path = ROOT / fomc_statements.STORE_DIR / f"{date_str}.txt"
        assert path.exists(), path
    assert (ROOT / fomc_statements.LEDGER_PATH).exists()


# ─────────────────────────────────────────────────────────────────────────────
# Routing: tolerant of the sibling W3 lane
# ─────────────────────────────────────────────────────────────────────────────

def test_routing_falls_back_to_config_when_fomc_is_undeclared():
    cfg = {"fomc_desk": {"accounts": {"analysis": "flagship",
                                      "relay": "mastermind_news"}},
           "wire_routing": {"default": "flagship",
                            "classes": {"macro_print": "mastermind_news"}}}
    resolved = fomc_desk.resolve_accounts(cfg)
    assert resolved["analysis"] == "flagship"
    assert resolved["relay"] == "mastermind_news"
    assert resolved["source"] == "config"


def test_routing_defers_to_wire_routing_once_fomc_is_declared(monkeypatch):
    """When the sibling lane declares the class, its answer wins for the relay."""
    from engine.marketing import wire_routing

    seen: dict = {}

    def _route(event_class, *, cfg, root=None, refinement=""):
        seen[(event_class, refinement)] = True
        return "wire_desk_x"

    monkeypatch.setattr(wire_routing, "route", _route)
    cfg = {"fomc_desk": {"accounts": {"analysis": "flagship",
                                      "relay": "mastermind_news"}},
           "wire_routing": {"classes": {"fomc": "wire_desk_x"}}}
    resolved = fomc_desk.resolve_accounts(cfg)
    assert resolved["relay"] == "wire_desk_x"
    assert resolved["source"] == "wire_routing"
    # No `fomc.analysis` refinement declared -> the house read stays put.
    assert resolved["analysis"] == "flagship"
    assert ("fomc", "") in seen


def test_routing_honours_an_analysis_refinement(monkeypatch):
    from engine.marketing import wire_routing

    monkeypatch.setattr(
        wire_routing, "route",
        lambda ec, *, cfg, root=None, refinement="":
            "house_desk" if refinement == "analysis" else "wire_desk")
    cfg = {"fomc_desk": {},
           "wire_routing": {"classes": {"fomc.analysis": "house_desk",
                                        "fomc.relay": "wire_desk"}}}
    resolved = fomc_desk.resolve_accounts(cfg)
    assert resolved["analysis"] == "house_desk"
    assert resolved["relay"] == "wire_desk"


def test_routing_never_asks_about_an_undeclared_class(monkeypatch):
    """route() is only called for a class routing has been SEEN to declare.

    That is what keeps this desk out of the unknown-class park/redirect path in a
    module it does not own.
    """
    from engine.marketing import wire_routing

    def _never(*a, **k):
        raise AssertionError("route() must not be called for an undeclared class")

    monkeypatch.setattr(wire_routing, "route", _never)
    fomc_desk.resolve_accounts(
        {"wire_routing": {"classes": {"geopolitical": "mastermind_news"}}})


def test_colliding_desks_keep_only_the_analysis(
    monkeypatch, seeded_root, july_page, capsys, hosted_card,
):
    """One desk does not post the same fact twice in two registers."""
    _stub_waterfall(monkeypatch, [CLEAN_REPLY])
    cfg = {"fomc_desk": {"enabled": True,
                         "accounts": {"analysis": "flagship", "relay": "flagship"},
                         "llm": {"enabled": True}}}
    report = fomc_desk.fire(date_str=JULY, root=seeded_root, cfg=cfg, now=NOW,
                            html_text=july_page)
    assert [i["fomc_role"] for i in report["emitted"]] == ["analysis"]
    lines = capsys.readouterr().out.splitlines()
    assert any(ln.startswith("::notice title=fomc-relay-collapsed") for ln in lines)


# ─────────────────────────────────────────────────────────────────────────────
# 16-17. Mechanical guards
# ─────────────────────────────────────────────────────────────────────────────

FOMC_MODULES = ("fomc_statements", "fomc_diff", "fomc_desk", "fomc_card")


def test_no_heavy_import_at_module_level():
    """The thin marketing CI lane has no anthropic/pandas. Keep collection green."""
    forbidden = {"anthropic", "pandas", "numpy", "pyarrow", "boto3", "requests",
                 "PIL", "jinja2", "matplotlib"}
    for name in FOMC_MODULES:
        source = (ROOT / "engine" / "marketing" / f"{name}.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:      # TOP LEVEL only — lazy imports are the point
            if isinstance(node, ast.Import):
                roots = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                roots = {(node.module or "").split(".")[0]}
            else:
                continue
            assert not (roots & forbidden), f"{name}.py imports {roots & forbidden}"


def test_gh_annotations_start_the_line():
    """`::warning` must be a bare print at column 0, never through a logger.

    Every logger in this repo prefixes the line, so `log.warning("::warning ...")`
    emits `WARNING ::warning ...` and GitHub silently drops it. See
    tests/test_gh_annotation_line_start.py — this is the module-local pin.
    """
    pattern = re.compile(r'(log|logger|logging)\s*\.\s*\w+\s*\(\s*f?["\']::')

    def _leading_literal(node: ast.AST) -> str:
        """The literal text an f-string/concatenation STARTS with ("" if unknown)."""
        while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            node = node.left
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr) and node.values:
            first = node.values[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return first.value
        return ""

    for name in FOMC_MODULES:
        source = (ROOT / "engine" / "marketing" / f"{name}.py").read_text(
            encoding="utf-8")
        assert not pattern.search(source), f"{name}.py routes an annotation via a logger"
        found = 0
        # AST, not a regex. The first version of this guard matched
        # `print\(\s*f?"::[^;]*?\)\n` and read the first `)` INSIDE a multi-line
        # argument as the end of the call, so it reported a missing flush on a
        # print that had one. A guard that cries wolf gets deleted, and then the
        # real defect ships.
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "print"
                    and node.args):
                continue
            if not _leading_literal(node.args[0]).startswith("::"):
                continue
            found += 1
            kwargs = {kw.arg for kw in node.keywords}
            assert "flush" in kwargs, (
                f"{name}.py line {node.lineno}: annotation print without "
                "flush=True (stdout is block-buffered when piped in CI)")
            assert "file" not in kwargs, (
                f"{name}.py line {node.lineno}: an annotation must go to stdout")
        if name in ("fomc_statements", "fomc_desk", "fomc_card"):
            assert found > 0, f"{name}.py should emit at least one annotation"


def test_config_ships_the_fomc_desk_block():
    cfg = yaml.safe_load(
        (ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
    block = cfg["fomc_desk"]
    assert block["enabled"] is True
    assert block["accounts"] == {"analysis": "flagship",
                                 "relay": "mastermind_news"}
    llm = block["llm"]
    assert llm["enabled"] is True
    assert llm["provider_order"] == ["codex", "oauth", "anthropic", "deepseek"]
    assert llm["codex_source_model"] == "gpt-5.6-sol"
    assert llm["codex_reasoning_effort"] == "medium"
    assert llm["usage_lane"] == "marketing-fomc"
    # The desk block must not have been parked inside a sibling lane's section.
    assert "fomc_desk" not in json.dumps(cfg.get("wire_routing") or {})
    assert "fomc_desk" not in json.dumps(cfg.get("copywriter") or {})
    assert "fomc_desk" not in json.dumps(cfg.get("breaking") or {})


def test_press_lane_calls_the_desk_fail_soft():
    """The seam exists, is wrapped, and honours --dry-run."""
    source = (ROOT / "engine" / "marketing" / "press_lane.py").read_text(
        encoding="utf-8")
    assert "fomc_desk as _fomc" in source
    assert "_fomc.maybe_fire(" in source
    assert "dry_run=dry_run" in source.split("_fomc.maybe_fire(")[1][:200]
    # Wrapped: the call sits inside a try whose except cannot escape.
    seam = source.split("FOMC STATEMENT-DIFF DESK")[1][:2000]
    assert "try:" in seam and "except Exception" in seam
    assert "::warning title=fomc-desk-seam" in seam
