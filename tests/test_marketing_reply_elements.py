"""XG-W4b §D — the two-of-five engagement floor and its four prohibitions.

WHAT THIS SUITE PINS, and every test names the requirement it holds:

  1. THE OPERATOR'S CALIBRATION SET, verbatim. His weak example must reject and
     name the failure; his human examples must pass. They are quoted exactly as
     he wrote them, so a later edit argues with him and not with a paraphrase.
     The ONE textual change is the em dash in "Exactly — and the refinancing
     schedule makes it worse", which is a house-banned character
     (`reply_voice._DASH_TELLS`), replaced with a comma.
  2. THE PARENT IS PART OF EVERY FIXTURE. The `reference` element is defined
     RELATIVE TO A POST — that is the whole content of "reacting to one specific
     detail" — so an excerpt with no parent cannot carry one, and pairing each
     line with the post it plainly answers is the honest fixture, not a
     convenience.
  3. `specific_reference` detector by detector, including the direction each one
     must NOT fire in.
  4. The §D.4 short-form exemption: what it rescues, and — the half that
     matters — what it still refuses.
  5. `fact_discipline`'s parent clause, both directions.
  6. The mutation checks §G.5 asks for on this lane's load-bearing rules.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.marketing import reply_critics as rc  # noqa: E402

# ---------------------------------------------------------------------------
# The operator's calibration set (2026-08-02), each line with the post it
# answers. THE PARENTS ARE WRITTEN TO BE ANSWERABLE BY HIS LINE, never to make a
# detector fire: a fixture tuned to the gate proves the gate matches itself.
# ---------------------------------------------------------------------------
Q3 = ("Q3 print is out. Revenue beat, gross margin held, and the inventory line "
      "is up 18% versus the prior quarter. Guidance for Q4 was left unchanged.")

#: (label, parent, reply). Verbatim from the brief.
HUMAN_EXAMPLES: tuple[tuple[str, str, str], ...] = (
    ("point_of_view", Q3,
     "I think people are underestimating how quickly this hits margins. "
     "Revenue might hold up, but the cost side could get ugly."),
    ("specific_detail", Q3,
     "The 18% inventory increase is the part that worries me. Demand can look "
     "fine for another quarter while that quietly builds underneath."),
    ("rhythm_yeah_but", Q3, "Yeah, but that's the problem."),
    ("rhythm_dont_know", Q3, "I don't know. This still feels early."),
    ("rhythm_exactly", "Ten year back to 4.6 and nobody blinked.",
     "Exactly. Especially if yields stay here."),
    ("rhythm_fair_point", Q3,
     "Fair point, although I think the second-order effect matters more."),
    ("micro_emotion_surprised", Q3, "Honestly, that guidance surprised me."),
    ("micro_emotion_frustrating", Q3, "This is the part I find frustrating."),
    ("micro_emotion_cautious", Q3, "I'd be pretty cautious chasing it here."),
    ("i_think_analysis",
     "Consensus has the revenue upside right and the balance sheet is a non-issue.",
     "I think the market is pricing the revenue upside but ignoring the "
     "financing risk"),
    ("i_feel_like_impression",
     "Positioning is clean and this is a demand story, full stop.",
     "I feel like everyone is treating this as a demand story when it's really "
     "a positioning story"),
    ("precise_my_read", "Real money is finally covering the underweight in this name.",
     "My read is that this move is mostly short covering."),
    ("precise_looks_more_like",
     "Multiple has halved and the fundamentals are clearly deteriorating.",
     "This looks more like multiple compression than deteriorating fundamentals."),
    ("precise_leaning", "Setup looks clean here.",
     "I'm leaning bullish, but the entry still looks bad."),
    ("type_direct_reaction", "Headline guidance came in ahead of the street.",
     "That guidance was much weaker than the headline suggests"),
    # The operator wrote an em dash here. It is house-banned copy, so the
    # fixture carries the comma the desk would actually write.
    ("type_agreement_plus", "Leverage is fine, they term the schedule out every year.",
     "Exactly, and the refinancing schedule makes it worse"),
    ("type_disagreement", "Demand is accelerating into next year.",
     "I'm not convinced. Most of that demand looks pulled forward"),
    ("type_question",
     "Thesis holds as long as energy behaves. Oil at $100 is not our base case.",
     "Would this thesis still hold if oil stays above $100?"),
    ("type_humor", "The CEO said AI eleven times on the call and the stock is up 12%.",
     "The market heard 'AI' and temporarily forgot valuation exists"),
    ("type_personal_interpretation", "Everyone is bullish into the print and rightly so.",
     "My first reaction was bullish, but the inventory numbers changed my mind"),
    ("type_compact_explanation",
     "Three cuts still priced with services inflation stickier than last year.",
     "Higher oil -> stickier inflation -> fewer cuts -> lower long-duration "
     "multiples"),
)

#: The operator's WEAK example, verbatim. "The second makes a judgment and
#: COMMITS"; this one does not, and it is the fixture the whole critic exists
#: to reject.
WEAK_EXAMPLE = ("Interesting perspective. This could have significant "
                "implications for the market.")


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


def _ctx(parent: str, cfg: dict, **over) -> dict:
    out = {"account": "kelly", "parent_text": parent, "parent_author": "somequant",
           "numbers_whitelist": [], "corpus": [], "theses": [], "cfg": cfg,
           "family": "human_reaction"}
    out.update(over)
    return out


# ===========================================================================
# 1. THE CALIBRATION SET — the acceptance gate, stated in the operator's words
# ===========================================================================
class TestOperatorCalibrationSet:
    def test_the_weak_example_rejects_and_names_the_failure(self, cfg):
        """PINS: "Interesting perspective..." must not ship, and the reject line
        must say WHY in words an operator can act on."""
        verdict = rc.reply_elements(WEAK_EXAMPLE, _ctx(Q3, cfg))
        assert verdict["verdict"] == "reject"
        reason = verdict["reasons"][0]
        assert reason.startswith("two_of_five: ")
        assert "only 0 of the five" in reason
        # The message names every missing element AND the reason it is missing.
        for element in ("reference", "opinion", "reason", "marker", "opening"):
            assert element in reason

    def test_the_weak_example_carries_no_element_at_all(self, cfg):
        """PINS the diagnosis, not just the verdict: a competent summary is
        elementless, which is the operator's whole point about AI replies."""
        assert rc.elements_present(WEAK_EXAMPLE, _ctx(Q3, cfg)) == {}

    @pytest.mark.parametrize("label,parent,reply",
                             HUMAN_EXAMPLES, ids=[c[0] for c in HUMAN_EXAMPLES])
    def test_every_human_example_clears_the_engagement_floor(
            self, label, parent, reply, cfg):
        """PINS operator item 9 against his own examples: a line a person would
        actually text must never be rejected by the rule that exists to make
        replies sound like a person."""
        verdict = rc.reply_elements(reply, _ctx(parent, cfg))
        assert verdict["verdict"] == "pass", verdict["reasons"]

    @pytest.mark.parametrize("label,parent,reply",
                             HUMAN_EXAMPLES, ids=[c[0] for c in HUMAN_EXAMPLES])
    def test_every_human_example_clears_the_register_laws(
            self, label, parent, reply, cfg):
        """PINS §C the same way. The register critic judges HOW the personal
        register is spent; none of these overspends it."""
        verdict = rc.register_discipline(reply, _ctx(parent, cfg))
        assert verdict["verdict"] == "pass", verdict["reasons"]

    def test_the_short_form_examples_clear_the_WHOLE_roster_once_a_shape_is_stamped(
            self, cfg):
        """PINS §D.4 as LOAD-BEARING, which is acceptance gate 4.

        These three are rejected on HEAD by `persona_label` or by
        `informational_surplus`'s second leg — not by anything this suite added
        — because a short reaction to the parent's own subject carries no
        referent WE brought. With the producer's shape stamp they clear all
        thirteen critics. Without §D.4 the entire short-form half of the shape
        build drafts and then silently abstains.
        """
        cases = [
            ("Real money is finally covering the underweight in this name.",
             "My read is that this move is mostly short covering."),
            ("Multiple has halved and the fundamentals are clearly deteriorating.",
             "This looks more like multiple compression than deteriorating fundamentals."),
            ("Headline guidance came in ahead of the street.",
             "That guidance was much weaker than the headline suggests"),
        ]
        for parent, reply in cases:
            bare = rc.run_critics(reply, _ctx(parent, cfg, account="meagan"))
            assert bare["verdict"] == "reject", (
                reply, "this fixture is only meaningful while HEAD rejects it")
            shaped = rc.run_critics(
                reply, _ctx(parent, cfg, account="meagan", shape="one_line"))
            assert shaped["verdict"] == "pass", (reply, shaped["reasons"])


# ===========================================================================
# 2. specific_reference — the highest-value detector in the brief
# ===========================================================================
class TestSpecificReference:
    def test_a_shared_figure_is_the_evidence(self):
        """PINS detector (1) and the operator's canonical case: the reply names
        the number the poster wrote."""
        evidence = rc.specific_reference(
            "The 18% inventory increase is the part that worries me.", Q3)
        assert evidence and "18%" in evidence

    def test_a_shared_cashtag_is_the_evidence(self):
        """PINS detector (2)."""
        evidence = rc.specific_reference("$NVDA guidance is the tell.",
                                         "Everyone is ignoring what $nvda just said.")
        assert evidence and "NVDA" in evidence.upper()

    def test_a_borrowed_noun_is_the_evidence(self):
        """PINS detector (3)."""
        evidence = rc.specific_reference(
            "The refinancing schedule lands in the same window.",
            "They term the schedule out every year without trouble.")
        assert evidence and "schedule" in evidence

    def test_a_quoted_term_lifted_from_the_parent_is_the_evidence(self):
        """PINS detector (4): quoting their word back IS reacting to a specific
        detail, and it is how the humour register engages a post."""
        evidence = rc.specific_reference(
            "The market heard 'AI' and temporarily forgot valuation exists",
            "The CEO said AI eleven times on the call.")
        assert evidence and "AI" in evidence

    def test_an_extracted_detail_stands_without_a_parent(self):
        """PINS detector (5): `extract_detail` firing is the engagement already
        proved, so it needs no second reading of the parent."""
        assert rc.specific_reference("The second chart is the load bearing one.",
                                     "", detail="second chart")

    # --- the directions it must NOT fire in --------------------------------
    def test_topical_adjacency_is_not_a_reference(self):
        """PINS THE WHOLE POINT. Every draft this desk writes shares market
        vocabulary with every parent; if that counted, the detector would pass
        on 'competent summary' and prove nothing."""
        assert rc.specific_reference(
            "Credit spreads are what settle this, not the equity tape.",
            "Credit spreads keep widening while equities hold.") is None

    def test_a_generic_market_word_is_not_a_borrowed_noun(self):
        """PINS the stoplist: sharing 'guidance' with a post about guidance is
        being on the same beat, not having read it."""
        assert rc.specific_reference("Guidance is the whole question here.",
                                     "Guidance was left unchanged.") is None

    def test_an_empty_parent_yields_no_reference(self):
        """PINS the fail direction: with nothing to reference, the element is
        absent rather than assumed."""
        assert rc.specific_reference("The 18% build is the part that matters.",
                                     "") is None


# ===========================================================================
# 3. The five elements, one at a time
# ===========================================================================
class TestElementDetectors:
    def test_opinion_needs_a_commitment_not_a_modal_maybe(self, cfg):
        """PINS operator item 1: "The second makes a judgment and COMMITS."
        `could` is deliberately not a commitment — his weak example is built
        out of it."""
        assert "opinion" not in rc.elements_present(
            "This could have significant implications.", _ctx(Q3, cfg))
        assert "opinion" in rc.elements_present(
            "My read is that this is positioning.", _ctx(Q3, cfg))

    def test_reason_reads_a_connective_or_a_second_clause_that_adds(self, cfg):
        """PINS element (c) in both of its shapes."""
        assert "reason" in rc.elements_present(
            "Margins hold because the inventory build is still being financed.",
            _ctx(Q3, cfg))
        assert "reason" in rc.elements_present(
            "Higher oil -> stickier inflation -> fewer cuts -> lower multiples",
            _ctx(Q3, cfg))

    def test_marker_reuses_the_warmth_guard_rather_than_forking_it(self, cfg):
        """PINS the module's own one-guard law: element (d) is
        `warmth_markers` plus three named extensions, never a second register
        classifier."""
        draft = "Fair point, and the funding leg moved first."
        assert rc.warmth_markers(draft, {"account": "kelly"})
        assert "marker" in rc.elements_present(draft, _ctx(Q3, cfg))

    def test_opening_and_opinion_may_not_share_a_sentence(self, cfg):
        """MUTATION CHECK (§G.5). Delete the (b)/(e) collision check in
        `elements_present` and this flips from one element to two — a single
        committed clause would buy the floor on its own.

        The two assertions together are what make it a mutation check rather
        than a behaviour test: the (e) DETECTOR fires on this sentence, and the
        element is still absent, so only the collision rule can be suppressing
        it.
        """
        draft = "That reads like credit, not semis."
        assert rc._opening_evidence(rc._sentences(draft)) is not None
        elements = rc.elements_present(draft, _ctx("Semis led the tape.", cfg))
        assert "opinion" in elements
        assert "opening" not in elements


# ===========================================================================
# 4. The four prohibitions (operator item 10)
# ===========================================================================
class TestProhibitions:
    def test_generic_praise_with_nothing_specific_rejects(self, cfg):
        """PINS prohibition 1. W3 kills the LONG bolted-on form; this kills the
        short one, which clears W3 today."""
        verdict = rc.reply_elements(
            "Good point. Well said, this is a great thread and very insightful.",
            _ctx(Q3, cfg))
        assert any(r.startswith("generic_praise: ") for r in verdict["reasons"])

    def test_praise_that_names_the_specific_thing_survives(self, cfg):
        """PINS the fail direction: the prohibition is on praise WITHOUT
        substance, and a rule that killed both would delete `specific_credit`."""
        verdict = rc.reply_elements(
            "Good point, and the 18% inventory build is the part that decides it.",
            _ctx(Q3, cfg))
        assert not any(r.startswith("generic_praise: ") for r in verdict["reasons"])

    def test_a_seven_word_lift_from_the_parent_rejects(self, cfg):
        """PINS prohibition 2, and the gap it closes: jaccard is blind to one
        quoted sentence sitting inside a longer reply."""
        verdict = rc.reply_elements(
            "Right, and the inventory line is up 18% versus the prior quarter, "
            "which is the part that decides the next guide.",
            _ctx(Q3, cfg))
        assert any(r.startswith("parroted_span: ") for r in verdict["reasons"])

    def test_a_repeated_opening_rejects_over_the_window(self, cfg):
        """PINS prohibition 3 AND that it is a WINDOW rule: one reply cannot be
        a repeated opening, so the corpus is what makes it measurable."""
        opener = "Agreed and the part underneath it is credit."
        corpus = [{"account": "kelly", "draft": opener} for _ in range(4)]
        corpus += [{"account": "kelly", "draft": f"Credit widened {n} sessions early."}
                   for n in range(3, 8)]
        verdict = rc.reply_elements(opener, _ctx(Q3, cfg, corpus=corpus))
        assert any(r.startswith("repeated_opening: ") for r in verdict["reasons"])

    def test_the_opening_rule_fails_open_on_a_thin_history(self, cfg):
        """PINS the documented fail direction, same posture as W2: a freshly
        armed account is never blocked by a rolling rule it has no history for."""
        opener = "Agreed and the part underneath it is credit."
        corpus = [{"account": "kelly", "draft": opener} for _ in range(4)]
        verdict = rc.reply_elements(opener, _ctx(Q3, cfg, corpus=corpus))
        assert not any(r.startswith("repeated_opening: ") for r in verdict["reasons"])

    def test_the_question_cap_binds_over_a_window_not_per_reply(self, cfg):
        """PINS prohibition 4 and §H.3's ruling: the cap is a RATE. One reply
        ending on a question is legal; a desk that does it by default is not.

        Both halves are asserted, because a cap that fired on the first
        question mark would kill the `author_question` family outright.
        """
        draft = "Would this thesis still hold if oil stays above 4.6?"
        cold = [{"account": "kelly", "draft": f"Credit widened {n} sessions early."}
                for n in range(3, 13)]
        assert rc.reply_elements(draft, _ctx(Q3, cfg, corpus=cold))["verdict"] == "pass"

        hot = [{"account": "kelly", "draft": "Is credit confirming this?"}
               for _ in range(5)] + cold[:5]
        verdict = rc.reply_elements(draft, _ctx(Q3, cfg, corpus=hot))
        assert any(r.startswith("question_end_share: ") for r in verdict["reasons"])


# ===========================================================================
# 5. §D.4 — the short-form exemption, and what it still refuses
# ===========================================================================
class TestShortFormExemption:
    PARENT = "Inventory is up 18% and nobody seems bothered."

    def test_it_rescues_a_short_reaction_that_named_their_number(self, cfg):
        draft = "My read is that the 18% build is the part that decides this."
        assert rc.short_form_engaged(draft, _ctx(self.PARENT, cfg, shape="one_line"))

    def test_an_absent_shape_fails_CLOSED(self, cfg):
        """PINS the fail direction the spec demands: a producer that forgot to
        stamp the shape gets the STRICT gate, never the lenient one."""
        draft = "My read is that the 18% build is the part that decides this."
        assert rc.short_form_engaged(draft, _ctx(self.PARENT, cfg)) is None

    def test_a_full_shape_gets_no_exemption(self, cfg):
        draft = "My read is that the 18% build is the part that decides this."
        assert rc.short_form_engaged(
            draft, _ctx(self.PARENT, cfg, shape="full")) is None

    def test_no_opinion_no_exemption(self, cfg):
        """MUTATION CHECK (§G.5). Delete the opinion requirement from
        `short_form_engaged` and this restatement — which HAS a reference —
        buys the exemption and `informational_surplus` stops seeing it.

        The second assertion is what makes it a mutation check: the reference
        element is present, so only the opinion clause can be refusing.
        """
        draft = "The 18% inventory build."
        ctx = _ctx(self.PARENT, cfg, shape="one_line")
        assert "reference" in rc.elements_present(draft, ctx)
        assert "opinion" not in rc.elements_present(draft, ctx)
        assert rc.short_form_engaged(draft, ctx) is None

    def test_a_referent_free_opinionless_short_reply_still_rejects_in_every_shape(
            self, cfg):
        """PINS the failure direction §D.4 names explicitly. The exemption must
        not become a hole for growth replies that say nothing."""
        draft = "Honestly this whole thing feels overdone to me right now."
        for shape in ("", "one_line", "fragment_exchange", "full"):
            ctx = _ctx("Nothing here surprises me at all.", cfg, shape=shape)
            assert rc.persona_label(draft, ctx)["verdict"] == "reject", shape

    def test_the_jaccard_leg_of_informational_surplus_still_binds(self, cfg):
        """PINS §D.4's own carve-out: only the SECOND leg is suppressed. A
        restatement is still a restatement in a short shape."""
        parent = "All intercepted and the tape barely moved on it."
        ctx = _ctx(parent, cfg, shape="one_line")
        verdict = rc.informational_surplus("All intercepted and the tape barely moved.", ctx)
        assert verdict["verdict"] == "reject"
        assert any("jaccard" in r for r in verdict["reasons"])


# ===========================================================================
# 6. fact_discipline's parent clause (§D.1's blocker)
# ===========================================================================
class TestFactDisciplineParentClause:
    def test_the_parents_own_figure_is_licensed(self, cfg):
        """PINS the blocker §D.1 opens. Without this the operator's canonical
        specific-reaction reply is unshippable: the parent's number is by
        construction not on OUR own-feed whitelist."""
        verdict = rc.fact_discipline(
            "The 18% inventory increase is the part that worries me.",
            {"numbers_whitelist": [], "parent_text": Q3})
        assert verdict["verdict"] == "pass", verdict["reasons"]

    def test_a_figure_in_neither_the_parent_nor_the_whitelist_still_rejects(self):
        """MUTATION CHECK (§G.5), other direction. Delete the parent clause and
        the first test goes red; widen it to any number and this one does."""
        verdict = rc.fact_discipline(
            "The 19% inventory increase is the part that worries me.",
            {"numbers_whitelist": [], "parent_text": Q3})
        assert verdict["verdict"] == "reject"
        assert "19%" in verdict["reasons"][0]

    def test_the_clause_matches_TOKEN_against_token_never_substring(self):
        """PINS the narrow form. A substring test would let a parent carrying
        '31.55' license a fabricated '1.5', which is worse than the blocker it
        was closing."""
        verdict = rc.fact_discipline(
            "Closer to 1.5 on that leg.",
            {"numbers_whitelist": [], "parent_text": "The basis sat at 31.55 all session."})
        assert verdict["verdict"] == "reject"

    def test_no_parent_means_no_licence(self):
        """PINS that the whitelist stays authoritative when there is nothing to
        quote."""
        verdict = rc.fact_discipline("The 18% build is the tell.",
                                     {"numbers_whitelist": []})
        assert verdict["verdict"] == "reject"


# ===========================================================================
# 7. The exemptions, the scope floor, and the data drop
# ===========================================================================
class TestScopeAndExemptions:
    def test_below_the_unit_floor_the_rule_is_inert(self, cfg):
        """PINS §D.0. A conversational beat is not a substantive reply, and the
        operator's own item-4 examples run five to seven units."""
        assert rc._content_units("Yeah, but that's the problem.") < 6
        assert rc.reply_elements("Yeah, but that's the problem.",
                                 _ctx(Q3, cfg))["verdict"] == "pass"

    def test_quiet_sympathy_is_double_gated(self, cfg):
        """PINS the exemption's shape: either half alone is a hole big enough
        to smuggle an elementless growth reply through."""
        draft = "Sorry to see that, genuinely a rough way for it to land."
        assert rc.reply_elements(
            draft, _ctx("", cfg, relationship_only=True,
                        warmth="quiet_sympathy"))["verdict"] == "pass"
        assert rc.reply_elements(
            draft, _ctx("", cfg, relationship_only=True))["verdict"] == "reject"
        assert rc.reply_elements(
            draft, _ctx("", cfg, warmth="quiet_sympathy"))["verdict"] == "reject"

    def test_a_data_drop_is_exempt_and_a_borrowed_figure_is_not(self, cfg):
        """PINS the second exemption AND its limit. The doctrine's top-ranked
        winning pattern is a checkable figure the post did not have; quoting
        THEIR figure back is a `reference`, which still owes a second element.
        """
        parent = "Equal weight went nowhere today."
        drop = "The index added 0.9% while semis added 2.4% and equal weight closed flat."
        assert rc._data_drop_evidence(drop, {"parent_text": parent})
        assert rc.reply_elements(drop, _ctx(parent, cfg))["verdict"] == "pass"
        # Their number, no view attached: not a drop, and one element short.
        borrowed = "The inventory line is up 18% on that print."
        assert rc._data_drop_evidence(borrowed, {"parent_text": Q3}) is None

    def test_the_dignity_list_no_longer_fires_inside_ordinary_market_words(self):
        """PINS the substring defect this suite surfaced: `duration` contains
        `ratio` and `scope` contains `cope`, and both are mechanism words this
        desk is built to use. A compact chain about long-duration multiples
        came back as a contempt tell."""
        chain = ("Higher oil -> stickier inflation -> fewer cuts -> lower "
                 "long-duration multiples")
        assert rc.dignity(chain, {})["verdict"] == "pass"
        assert rc.dignity("The scope of the guide narrowed.", {})["verdict"] == "pass"
        # And the tells themselves still bind, as whole words.
        assert rc.dignity("ratio this take", {})["verdict"] == "reject"
        assert rc.dignity("cope harder", {})["verdict"] == "reject"


# ===========================================================================
# 8. The roster + the queue's stamp ceremony (§G.7)
# ===========================================================================
class TestRoster:
    def test_both_new_critics_are_in_the_register_and_wired(self):
        for name in ("reply_elements", "register_discipline"):
            assert name in rc.CRITICS
            assert name in rc._CRITIC_FUNCS
        assert len(rc.CRITICS) == 13
        assert set(rc.CRITICS) == set(rc._CRITIC_FUNCS)

    def test_a_stamp_from_the_old_roster_is_refused_by_the_queue(self, tmp_path):
        """PINS §G.7. A producer pinned to the eleven-critic roster has not
        cleared the critics, whatever its stamp says."""
        from engine.marketing import reply_queue as rq  # noqa: PLC0415

        stale = rc.stamp({
            "verdict": "pass", "rejected_by": [],
            "critics": [{"critic": n, "verdict": "pass", "reasons": []}
                        for n in rc.CRITICS
                        if n not in {"reply_elements", "register_discipline"}],
        })
        item = rq.make_item(
            account="kelly",
            target_url="https://x.com/somequant/status/1900000000000000001",
            parent_author="somequant", parent_excerpt=Q3,
            draft="Credit widened 12.5% before equities noticed.",
            tier="relationship", score=0.8, score_components={"author_tier": 0.26},
            critics=stale)
        errors = rq.validate_critic_stamp(item)
        assert any("reply_elements" in e for e in errors)
        assert any("register_discipline" in e for e in errors)


class TestTheOperatorsCalibrationSet:
    """The operator's own examples, verbatim, as the acceptance bar.

    The brief gave one WEAK reply and six HUMAN ones. They are a better test
    than any rule restatement, because they pin the gap rather than my
    description of it. The humor line is here for a second reason: an earlier
    pass "found" it failing and cut a humor exemption into the floor for it —
    the failure was a harness that omitted `parent_text`, the line passes on
    merit (quoted term + verdict), and the exemption was removed. This class is
    what would catch that mistake being made again.
    """

    PARENT = ("Semis have been the whole tape. AI capex is not slowing down and "
              "the market is finally waking up to it. Inventory up 18% though.")

    def _ctx(self, **over):
        # BOTH keys: the critics read `parent_text` (five places), the drafter
        # carries `target`. A ctx with only `target` silently no-ops every
        # parent-dependent check — that is exactly how the phantom above got in.
        ctx = {"account": "sophia", "shape": "one_line", "kind": "reply",
               "target": {"text": self.PARENT}, "parent_text": self.PARENT}
        ctx.update(over)
        return ctx

    def test_the_weak_example_is_rejected_by_name(self):
        weak = ("Interesting perspective. This could have significant "
                "implications for the market.")
        v = rc.reply_elements(weak, self._ctx())
        assert v["verdict"] != "pass"
        assert any("two_of_five" in r for r in v["reasons"]), v["reasons"]

    @pytest.mark.parametrize("draft", [
        "I think people are underestimating how quickly this hits margins. "
        "Revenue might hold up, but the cost side could get ugly.",
        "The 18% inventory increase is the part that worries me. Demand can "
        "look fine for another quarter while that quietly builds underneath.",
        "Yeah, but that's the problem.",
        "Fair point, although I think the second-order effect matters more.",
        "Honestly, that guidance surprised me.",
        "The market heard 'AI' and temporarily forgot valuation exists.",
    ])
    def test_every_human_example_passes(self, draft):
        v = rc.reply_elements(draft, self._ctx())
        assert v["verdict"] == "pass", f"{draft!r} -> {v['reasons']}"

    def test_a_parroted_parent_is_still_rejected(self):
        parrot = ("Semis have been the whole tape and AI capex is not slowing "
                  "down, the market is finally waking up to it.")
        v = rc.reply_elements(parrot, self._ctx())
        assert v["verdict"] != "pass"
        assert any("parroted_span" in r for r in v["reasons"]), v["reasons"]


def test_the_producer_puts_the_parent_text_in_the_critic_ctx():
    """The parent-dependent checks are only as live as this one field.

    `parroted_span`, `specific_reference`, `fact_discipline`, `corpus_near_dup`
    and `short_form_engaged` all read `ctx["parent_text"]` and all degrade
    SILENTLY to a pass when it is absent — no error, no warning, just a guard
    that stops guarding. The producer is the only thing that fills it, so the
    wiring is pinned here rather than trusted.
    """
    import inspect
    from engine.marketing import reply_producer as rp
    src = inspect.getsource(rp)
    assert '"parent_text"' in src, (
        "reply_producer no longer puts parent_text in the critic ctx — five "
        "parent-dependent critics just went dark without failing anything")
