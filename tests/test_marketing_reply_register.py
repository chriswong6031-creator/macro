"""XG-W4b §C — the register laws, and the prompt-vs-critic contract.

WHAT THIS SUITE PINS:

  1. Uncertainty discipline: ONE marker is conversation, two is a model hedging,
     and "occasional" is a RATE over a window rather than a wish.
  2. The operator's own I-think / I-feel-like / precise-alternative ladder,
     executable.
  3. That contractions and fragments are LAWFUL — a guard test, because the
     corpus's median winner is eleven words and a gate that quietly preferred
     complete sentences would drag the desk back to the memo register.
  4. That manufactured typos reject, including the elongation regex's one
     genuine trap.
  5. The three anti-polish measures, each with the false-positive direction that
     shaped it pinned alongside.
  6. THE PROMPT-VS-CRITIC INTROSPECTION. Every rule the two new critics enforce
     is stated in `reply_voice`'s system prompt, and every rule the prompt
     states has a live code site that can actually reject. A prompt that asks
     for what the validator bans is the defect this repo has fixed twice this
     week; this is the structural version of not doing it a third time.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_voice as rv  # noqa: E402

PARENT = "Hyperscaler capex keeps climbing but credit spreads are widening."

#: A three-sentence paragraph at 14/14/13 content units: uniform, complete,
#: uncontracted, and carrying no conversational register anywhere. This is what
#: "excessively polished" means once it is measurable.
MEMO = (
    "The revenue line came in comfortably ahead of the published consensus for "
    "the quarter. The margin story is what really decides the multiple from "
    "here on this name. The market has not repriced the financing schedule "
    "sitting underneath the guide yet."
)


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


def _ctx(cfg: dict, **over) -> dict:
    out = {"account": "kelly", "parent_text": PARENT, "parent_author": "somequant",
           "numbers_whitelist": [], "corpus": [], "theses": [], "cfg": cfg,
           "family": "human_reaction"}
    out.update(over)
    return out


def _corpus(n: int, draft: str, account: str = "kelly") -> list[dict]:
    return [{"account": account, "draft": draft} for _ in range(n)]


def _reasons(verdict: dict, rule: str) -> list[str]:
    return [r for r in verdict["reasons"] if r.startswith(f"{rule}: ")]


# ===========================================================================
# 1. §C.1 — uncertainty-marker discipline
# ===========================================================================
class TestUncertaintyDiscipline:
    def test_one_marker_is_conversation(self, cfg):
        """PINS operator item 3: "ONE marker, NEVER stacked hedges, OCCASIONAL
        use only." One is explicitly fine."""
        draft = "I could be wrong, but the funding leg is what settles this."
        assert rc.register_discipline(draft, _ctx(cfg))["verdict"] == "pass"

    def test_two_markers_reject_as_stacking(self, cfg):
        """PINS R1."""
        draft = "I could be wrong, and it feels like the funding leg is the tell."
        verdict = rc.register_discipline(draft, _ctx(cfg))
        assert _reasons(verdict, "uncertainty_stacking")

    def test_a_marker_that_contains_another_is_counted_once(self, cfg):
        """PINS the containment guard. Without it a single phrase that happens
        to contain a shorter marker reads as two, and R1 rejects a compliant
        reply for stacking a hedge on itself."""
        assert len(rc._uncertainty_hits("I'm not fully convinced by the capex read.")) == 1

    def test_hedging_is_capped_as_a_RATE_over_a_window(self, cfg):
        """PINS R2, and that "occasional" is measured rather than asserted.
        Both directions: the same draft passes against a dry history and
        rejects against a hedged one."""
        draft = "I could be wrong, but the funding leg is what settles this."
        dry = _corpus(10, "Credit widened four sessions before equities did.")
        assert rc.register_discipline(draft, _ctx(cfg, corpus=dry))["verdict"] == "pass"

        hedged = _corpus(5, "Hard to say what the capex line does next.") + dry[:5]
        verdict = rc.register_discipline(draft, _ctx(cfg, corpus=hedged))
        assert _reasons(verdict, "hedge_share")

    def test_the_rate_rule_fails_OPEN_on_a_thin_history(self, cfg):
        """PINS the documented fail direction. Same posture and the same real
        cost W2 records: a freshly armed account may hedge its first few
        replies, and the mitigation is supply side, never a gate that blocks the
        lane at arming."""
        draft = "I could be wrong, but the funding leg is what settles this."
        thin = _corpus(5, "Hard to say what the capex line does next.")
        assert rc.register_discipline(draft, _ctx(cfg, corpus=thin))["verdict"] == "pass"

    def test_a_hedge_may_not_ride_a_confession(self, cfg):
        """PINS R3: "I was wrong, though I could be wrong" reads as neither."""
        draft = "I was wrong on the funding call, though I could be wrong again."
        verdict = rc.register_discipline(draft, _ctx(cfg))
        assert _reasons(verdict, "hedge_on_confession")

    def test_a_clean_confession_is_untouched(self, cfg):
        """PINS the fail direction: owning a changed mind in public is a
        FEATURE (constitution §6.3), so the rule must bite the hedge and not
        the admission."""
        draft = "I was wrong on the funding call. Credit led it, not capex."
        assert rc.register_discipline(draft, _ctx(cfg))["verdict"] == "pass"


# ===========================================================================
# 2. §C.2 — the I-think ladder
# ===========================================================================
class TestTheIThinkLadder:
    def test_i_feel_like_is_legal_for_an_impression(self, cfg):
        """PINS T2 with the operator's own sentence: "I feel like" is for what
        the room believes."""
        draft = ("I feel like everyone is treating this as a demand story when "
                 "it's really a positioning story")
        assert rc.register_discipline(draft, _ctx(cfg))["verdict"] == "pass"

    def test_i_feel_like_in_front_of_an_analytical_claim_rejects(self, cfg):
        """PINS T2's other half, with the spec's own counterexample."""
        draft = "I feel like the refinancing schedule lands in the third quarter."
        verdict = rc.register_discipline(draft, _ctx(cfg))
        assert _reasons(verdict, "i_feel_like_scope")

    def test_the_precise_alternatives_are_uncapped(self, cfg):
        """PINS T3 as the PREFERRED rung. The operator ranks "My read is" and
        "This looks more like" above "I think", so nothing here may cap them —
        their absence from `register_discipline` is the policy, and this test is
        what makes the absence deliberate rather than an oversight."""
        draft = "My read is that this looks more like compression than demand."
        heavy = _corpus(20, "My read is that credit leads this one.")
        assert rc.register_discipline(draft, _ctx(cfg, corpus=heavy))["verdict"] == "pass"

    def test_i_think_is_capped_as_a_share(self, cfg):
        """PINS T1: "I think" is analysis-legal but it is seasoning, not the
        meal."""
        draft = "I think the funding leg is what settles this one."
        dry = _corpus(10, "Credit widened four sessions before equities did.")
        assert rc.register_discipline(draft, _ctx(cfg, corpus=dry))["verdict"] == "pass"

        heavy = _corpus(6, "I think capex is downstream of credit here.") + dry[:6]
        verdict = rc.register_discipline(draft, _ctx(cfg, corpus=heavy))
        assert _reasons(verdict, "i_think_share")

    def test_i_think_may_not_become_the_habitual_OPENING(self, cfg):
        """PINS the operator's mustache sentence, executable: "if every reply
        starts with them the account sounds like an LLM wearing a human
        mustache." The opening cap is separate from the share cap because a
        desk can be under the share and still open the same way every time."""
        draft = "I think the funding leg is what settles this one."
        corpus = (_corpus(3, "I think capex is downstream of credit here.")
                  + _corpus(9, "Credit widened four sessions before equities did."))
        verdict = rc.register_discipline(draft, _ctx(cfg, corpus=corpus))
        assert _reasons(verdict, "i_think_openings")


# ===========================================================================
# 3. §C.3 — contractions and fragments LAWFUL, typos FORBIDDEN
# ===========================================================================
class TestContractionsFragmentsTypos:
    CONTRACTED = ("Honestly the funding leg isn't the story here, because it's "
                  "the inventory build that hasn't been priced.")
    FRAGMENTS = "Credit widened first. That is the whole story."

    def test_a_contracted_reply_clears_ALL_THIRTEEN_critics(self, cfg):
        """PINS §C.3's guard requirement. Three contractions, full roster, no
        rejection — because `_TOKEN_RE` keeps the apostrophe inside the token
        and no critic may penalise a contraction."""
        assert self.CONTRACTED.count("'") == 3
        verdict = rc.run_critics(self.CONTRACTED, _ctx(cfg, account="meagan"))
        assert verdict["verdict"] == "pass", verdict["reasons"]
        assert len(verdict["critics"]) == 13

    def test_a_two_fragment_reply_clears_ALL_THIRTEEN_critics(self, cfg):
        """PINS that the content-unit floor is a WHOLE-REPLY floor, not a
        per-sentence one. A later edit that made it per-sentence would delete
        the entire fragment_exchange shape, so this pins the current behaviour
        deliberately."""
        assert [rc._content_units(s) for s in rc._sentences(self.FRAGMENTS)] == [3, 5]
        assert rc._content_units(self.FRAGMENTS) >= rc.MIN_CONTENT_UNITS
        verdict = rc.run_critics(self.FRAGMENTS, _ctx(
            cfg, account="meagan",
            parent_text="Equities held all session and nobody flinched."))
        assert verdict["verdict"] == "pass", verdict["reasons"]

    def test_a_manufactured_misspelling_rejects(self, cfg):
        """PINS §C.3's closed list. The deterministic path never writes one;
        this exists because a model told to sound human will."""
        verdict = rc.register_discipline(
            "the funding leg is definately the part that decides this", _ctx(cfg))
        assert _reasons(verdict, "artificial_typos")

    def test_a_stretched_word_rejects(self, cfg):
        verdict = rc.register_discipline("that guide was sooo much weaker than the print",
                                         _ctx(cfg))
        assert _reasons(verdict, "artificial_typos")

    def test_the_elongation_regex_does_not_fire_inside_a_round_number(self, cfg):
        """PINS THE TRAP. The `\\w`-based form of this regex matches "1,000"
        (three zeroes in a row) and would have rejected every reply carrying a
        round thousand — a silent, permanent tax on the data-drop pattern the
        doctrine ranks first."""
        assert rc._ELONGATION_RE.search("the 1,000 level held") is None
        verdict = rc.register_discipline("Support at the 1,000 level held all session.",
                                         _ctx(cfg))
        assert not _reasons(verdict, "artificial_typos")

    def test_a_missing_apostrophe_is_NOT_a_typo_tell(self, cfg):
        """PINS the rule that was considered and REJECTED. Kelly's lowercase
        register legitimately writes "dont", and a gate that fires on a pinned
        voice is a gate that gets overridden."""
        verdict = rc.register_discipline("dont think credit has priced this yet",
                                         _ctx(cfg))
        assert not _reasons(verdict, "artificial_typos")


# ===========================================================================
# 4. §C.4 — the anti-polish measures
# ===========================================================================
class TestAntiPolish:
    def test_a_uniform_paragraph_rejects_as_metronome_prose(self, cfg):
        """PINS P1 against the spec's own calibration shape."""
        units = rc._sentence_units(MEMO)
        assert len(units) == 3 and min(units) > 4
        verdict = rc.register_discipline(MEMO, _ctx(cfg))
        assert _reasons(verdict, "metronome_prose")

    def test_the_same_paragraph_rejects_as_a_memo(self, cfg):
        """PINS P2: three complete, uncontracted, paragraph-length sentences
        with nothing conversational in them."""
        assert _reasons(rc.register_discipline(MEMO, _ctx(cfg)), "memo_prose")

    def test_the_operators_two_sentence_example_is_exempt(self, cfg):
        """PINS the sentence-count gate. A one- or two-sentence reply cannot be
        over-polished; it can only be short, which is the goal."""
        draft = ("The 18% inventory increase is the part that worries me. Demand "
                 "can look fine for another quarter while that quietly builds "
                 "underneath.")
        verdict = rc.register_discipline(draft, _ctx(cfg))
        assert not _reasons(verdict, "metronome_prose")
        assert not _reasons(verdict, "memo_prose")

    def test_three_SHORT_uniform_sentences_are_the_winning_register_not_polish(self, cfg):
        """PINS THE FALSE-POSITIVE DIRECTION THAT SHAPED BOTH RULES, and it is
        the deviation from the spec that this build makes deliberately.

        `_sentences` splits on the newline between the drafter's gift and its
        doorway, so a 27-unit reply of SHORT sentences counts as three. Measured
        over 972 deterministic renders on HEAD, uniformity alone rejects the
        drafter's own output — down to 9/10/9 content units — and the marker
        conjunct alone rejects the flagship and founder house shape, whose §5
        register map forbids them a warmth marker at all. Both rules therefore
        require paragraph-scale sentences. This fixture is the exact flagship
        render that forced it.
        """
        draft = ("Equal weight closed flat while the index added 0.9% and semis "
                 "added 2.4%.\n\nThe tape has a view on breadth. It has not taken "
                 "one on credit.")
        assert rc._sentence_units(draft) == [13, 7, 7]
        verdict = rc.register_discipline(draft, _ctx(cfg, account="flagship"))
        assert verdict["verdict"] == "pass", verdict["reasons"]

    def test_two_balanced_clauses_reject(self, cfg):
        """PINS P3, deliberately narrow: one such construction is a sentence a
        person writes, two in a reply under sixty words is a rhythm."""
        draft = ("It is not just the guide but the financing behind it. And it's "
                 "not demand, it's positioning.")
        assert _reasons(rc.register_discipline(draft, _ctx(cfg)), "balanced_clause_tell")

    def test_one_balanced_clause_survives(self, cfg):
        draft = "It is not just the guide but the financing behind it."
        assert not _reasons(rc.register_discipline(draft, _ctx(cfg)),
                            "balanced_clause_tell")


# ===========================================================================
# 5. THE PROMPT-VS-CRITIC CONTRACT
# ===========================================================================
#: One fixture per rule id: (draft, ctx overrides). The map is what turns the
#: shared id list from a mirrored constant into a proof — a mirrored guard test
#: passes on broken code, so every id must be shown to have a live code site
#: that can actually reject.
_RULE_FIXTURES: dict[str, tuple[str, dict]] = {
    "uncertainty_stacking": (
        "I could be wrong, and it feels like the funding leg is the tell.", {}),
    "hedge_share": (
        "I could be wrong, but the funding leg is what settles this.",
        {"corpus": (_corpus(6, "Hard to say what the capex line does next.")
                    + _corpus(6, "Credit widened before equities did."))}),
    "hedge_on_confession": (
        "I was wrong on the funding call, though I could be wrong again.", {}),
    "i_feel_like_scope": (
        "I feel like the refinancing schedule lands in the third quarter.", {}),
    "i_think_share": (
        "The funding leg, I think, is what settles this one.",
        {"corpus": (_corpus(6, "I think capex is downstream of credit here.")
                    + _corpus(6, "Credit widened before equities did."))}),
    "i_think_openings": (
        "I think the funding leg is what settles this one.",
        {"corpus": (_corpus(3, "I think capex is downstream of credit.")
                    + _corpus(9, "Credit widened before equities did."))}),
    "artificial_typos": (
        "the funding leg is definately the part that decides this", {}),
    "metronome_prose": (MEMO, {}),
    "memo_prose": (MEMO, {}),
    "balanced_clause_tell": (
        "It is not just the guide but the financing behind it. And it's not "
        "demand, it's positioning.", {}),
    "two_of_five": (
        "Interesting perspective. This could have significant implications for "
        "the market.", {}),
    "generic_praise": (
        "Good point. Well said, this is a great thread and worth the read.", {}),
    "parroted_span": (
        "Right, and hyperscaler capex keeps climbing but credit spreads are "
        "widening, which is the part that decides the next guide.", {}),
    "repeated_opening": (
        "Agreed and the part underneath it is credit.",
        {"corpus": (_corpus(4, "Agreed and the part underneath it is credit.")
                    + _corpus(6, "Credit widened before equities did."))}),
    "question_end_share": (
        "Would this thesis still hold if funding stays here?",
        {"corpus": (_corpus(5, "Is credit confirming this?")
                    + _corpus(5, "Credit widened before equities did."))}),
}


class TestPromptCriticContract:
    def test_the_prompt_states_exactly_the_rules_the_critics_enforce(self):
        """PINS §F.7's whole point. A prompt that asks for what the validator
        bans burns the repair turn and reads as "the model is bad at this";
        a critic rule the prompt never states is a rejection the model could
        not have avoided. Both are impossible while these two sets are equal."""
        assert {rule for rule, _law in rv.REGISTER_LAWS} == set(rc.REGISTER_RULE_IDS)
        assert len(rv.REGISTER_LAWS) == len(rc.REGISTER_RULE_IDS)

    @pytest.mark.parametrize("rule,law", rv.REGISTER_LAWS,
                             ids=[r for r, _ in rv.REGISTER_LAWS])
    def test_every_law_actually_reaches_the_model(self, rule, law):
        """PINS that the constant is not a decoration: each sentence must be in
        the prompt the provider is handed, including the store-augmented form."""
        assert law in rv.SYSTEM_PROMPT
        assert law in rv.system_prompt(None, ROOT)

    @pytest.mark.parametrize("rule", rc.REGISTER_RULE_IDS)
    def test_every_rule_id_has_a_live_code_site_that_rejects(self, rule, cfg):
        """MUTATION-PROOFING FOR THE CONTRACT ITSELF. Comparing two constants is
        a mirrored guard and passes on broken code; this drives each id through
        the critics and requires a real rejection carrying that id."""
        assert rule in _RULE_FIXTURES, (
            f"{rule!r} is in REGISTER_RULE_IDS with no fixture proving it can fire")
        draft, over = _RULE_FIXTURES[rule]
        ctx = _ctx(cfg, **over)
        reasons = (rc.reply_elements(draft, ctx)["reasons"]
                   + rc.register_discipline(draft, ctx)["reasons"])
        assert any(r.startswith(f"{rule}: ") for r in reasons), (rule, reasons)

    def test_hard_law_ten_is_in_the_prompt(self):
        """PINS §C.3's real enforcement for the model path."""
        assert "Never misspell anything on purpose" in rv.SYSTEM_PROMPT
        assert "worse than a dull reply" in rv.SYSTEM_PROMPT


# ===========================================================================
# 6. reply_voice threading (§F.7)
# ===========================================================================
class TestVoiceValidatorThreading:
    def test_the_validator_runs_the_two_new_critics(self, cfg):
        """PINS that a model rewrite faces the SAME laws downstream will. A
        rejection here costs one phrasing attempt; the same text passing here
        and failing in `run_critics` costs the whole item."""
        bad = "I could be wrong, and it feels like the funding leg is the tell."
        violations = rv.validate_reply_copy(
            bad, draft="Credit widened first. That is the whole story.",
            parent_text=PARENT, account="kelly", family="human_reaction")
        assert any(v.startswith("register_discipline: uncertainty_stacking")
                   for v in violations), violations

    def test_the_validator_enforces_the_engagement_floor(self):
        violations = rv.validate_reply_copy(
            "Interesting perspective. This could have significant implications "
            "for the market.",
            draft="Credit widened first. That is the whole story.",
            parent_text=PARENT, account="kelly", family="human_reaction")
        assert any(v.startswith("reply_elements: two_of_five") for v in violations)

    def test_the_shape_reaches_the_critics_ctx(self, monkeypatch):
        """PINS §F.7's shape threading. `short_form_engaged` fails CLOSED on an
        absent shape, so a validator that dropped the stamp would judge a
        model's `one_line` rewrite by the gift-led proxy and reject it for the
        very thing that makes it a one-liner."""
        seen: list[dict] = []
        original = rc.reply_elements
        monkeypatch.setattr(
            rc, "reply_elements",
            lambda draft, ctx: (seen.append(dict(ctx)), original(draft, ctx))[1])
        rv.validate_reply_copy(
            "My read is that the 18% build is the part that decides this.",
            draft="Credit widened first. That is the whole story.",
            parent_text="Inventory is up 18% and nobody seems bothered.",
            account="meagan", family="human_reaction", shape="one_line")
        assert seen and seen[0]["shape"] == "one_line"
        assert seen[0]["parent_text"] == "Inventory is up 18% and nobody seems bothered."

    def test_the_parents_own_figure_is_no_longer_rejected_by_the_voice_gate(self):
        """PINS THE INVERSION §D.1 CAUSES HERE. The prompt now asks the model to
        react to a specific figure in the post; this gate used to reject exactly
        that, because it deliberately withheld the parent's numbers on the
        grounds that `fact_discipline` would kill them anyway. That critic now
        licenses them, so withholding here would punish the obedience the prompt
        asks for. A figure in NEITHER the parent nor the whitelist still fails.
        """
        parent = "Inventory is up 18% and nobody seems bothered."
        common = dict(draft="Credit widened first. That is the whole story.",
                      parent_text=parent, account="meagan", family="human_reaction",
                      shape="one_line")
        assert rv.validate_reply_copy(
            "My read is that the 18% build is the part that decides this.",
            **common) == []
        assert rv.validate_reply_copy(
            "My read is that the 19% build is the part that decides this.",
            **common) != []

    def test_the_shape_budget_is_printed_as_a_hard_instruction(self):
        """PINS that a shape budget the sampler chose actually reaches the
        model, rather than living only in the renderer."""
        msg = rv.build_user_message(
            draft="Credit widened first.", family="human_reaction", account="kelly",
            parent_text=PARENT, shape="one_line",
            shape_spec={"label": "one committed sentence", "max_units": 14,
                        "max_chars": 100, "max_sentences": 1, "doorway": False})
        assert "SHAPE: one_line" in msg
        assert "14 content units maximum" in msg
        assert "HARD limit" in msg
        assert "Do NOT add a closing line" in msg

    def test_no_shape_means_no_shape_block(self):
        """PINS the absent-input direction: the prompt says nothing it cannot
        substantiate."""
        msg = rv.build_user_message(
            draft="Credit widened first.", family="human_reaction", account="kelly",
            parent_text=PARENT)
        assert "SHAPE:" not in msg
