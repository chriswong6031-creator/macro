"""tests/test_marketing_reply_warmth.py — the warmth register acceptance suite.

Program: X Growth reply desk, the WARMTH BUILD (2026-08-01).
Doctrine: research/MARKETING_REPLY_DOCTRINE_BY_FABLE.md §12 (the warmth
amendment), grounded in the winning-reply corpus.

WHAT THIS SUITE IS FOR. The operator's complaint was that machine-written
replies come out "completely analytical and cold", and the census found the
cause: every entry in ``reply_drafter.FAMILIES`` is an analytical move, so
nothing in the register could carry warmth, delight, curiosity or shared
frustration. ``WARMTH_MOVES`` is the second rotation axis that closes that gap.

THE LOAD-BEARING TESTS ARE THE NEGATIVE ONES. It is easy to add warm copy; the
claims worth pinning are that our OWN guards clear every sanctioned opener (a
warmth phrase that trips ``banned_language`` or the expression dial is a defect,
not a style), that a move which is WRONG for the parent shape is unavailable,
that a move that is out of character for a persona cannot reach her, that
rotation cannot let one move harden into a tell, and that a fabricated
biography rejects with the offending sentence quoted.

Fixture-driven; ZERO network, ZERO LLM. Import closure is stdlib + pyyaml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import expression_dial as ed  # noqa: E402
from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_drafter as rd  # noqa: E402
from engine.marketing import reply_voice as rv  # noqa: E402
from engine.marketing.copywriter import banned_language  # noqa: E402

#: The four real named humans. The flagship and the founder are branded desks
#: and are deliberately absent from the warm register (charter §2 amendment 3).
EMPLOYEES = ("sophia", "kelly", "cici", "meagan")

PARENT = "Strong session today, breadth looked fine to me and the tape held up."
GIFT = "Equal weight closed flat while the index added 0.9% and semis added 2.4%."
WHITELIST = ["0.9%", "2.4%"]
TARGET = {"subject": "the tape", "mechanism": "breadth",
          "text": PARENT, "author": "somequant"}
FACTS = {"facts": [{"id": "f1", "text": GIFT, "salience": 1.0}],
         "numbers_whitelist": WHITELIST}


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


def _ctx(account: str, **over) -> dict:
    out = {"subject": "the tape", "mechanism": "breadth",
           "account": account, "detail": "breadth"}
    out.update(over)
    return out


def _critic_ctx(account: str, cfg: dict, **over) -> dict:
    out = {"account": account, "parent_text": PARENT, "parent_author": "somequant",
           "numbers_whitelist": WHITELIST, "corpus": [], "theses": [], "cfg": cfg,
           "family": "missing_variable"}
    out.update(over)
    return out


# ===========================================================================
# 1. The register itself — shape, vocabulary, and our own guards
# ===========================================================================
class TestRegisterShape:
    def test_the_register_is_not_empty_and_covers_the_named_moves(self):
        """The eight moves the doctrine amendment names, enumerated BY HAND.

        Parametrising over ``WARMTH_MOVES`` would compare the module against
        itself and stay green if a move were deleted.
        """
        assert set(rd.WARMTH_MOVES) == {
            "concede_and_hold", "flat_confession", "verdict_first",
            "specific_credit", "wry_solidarity", "concrete_image",
            "open_curiosity", "quiet_sympathy",
        }

    @pytest.mark.parametrize("move", sorted(rd.WARMTH_MOVES))
    def test_every_move_declares_a_complete_spec(self, move):
        spec = rd.WARMTH_MOVES[move]
        assert spec["label"] and spec["does"]
        assert spec["fuse"] in ("conjunction", "standalone")
        assert int(spec["dial_floor"]) in (1, 2)
        assert spec["fits"], "a move with no parent shape can never be selected"
        assert spec["openers"], "a move with no register copy is decorative"

    @pytest.mark.parametrize("move", sorted(rd.WARMTH_MOVES))
    def test_fits_and_wrong_when_use_the_closed_shape_vocabulary(self, move):
        """A typo in `fits` is a move that silently never fires."""
        spec = rd.WARMTH_MOVES[move]
        for shape in tuple(spec["fits"]) + tuple(spec.get("wrong_when") or ()):
            assert shape in rd.PARENT_SHAPES, f"{move}: unknown parent shape {shape!r}"

    @pytest.mark.parametrize("move", sorted(rd.WARMTH_MOVES))
    def test_no_move_fits_a_sensitive_event(self, move):
        """We do not borrow distribution from a tragedy, warmly or otherwise."""
        assert "sensitive_event" not in rd.WARMTH_MOVES[move]["fits"]

    @pytest.mark.parametrize("move", sorted(rd.WARMTH_MOVES))
    def test_families_ok_names_real_families(self, move):
        fams = rd.WARMTH_MOVES[move].get("families_ok")
        if fams is None:
            return
        for fam in fams:
            assert fam in rd.FAMILIES, f"{move}: unknown family {fam!r}"


class TestOurOwnGuardsClearEveryOpener:
    """ACCEPTANCE GATE. A warmth phrase that trips our own guards is a defect.

    Every opener is run against the three gates the shipped copy has to clear
    downstream, for the persona it is granted to. An opener that fails one of
    these would not be a style choice: it would cost a whole queue item at
    critic time, silently, forever.
    """

    @pytest.mark.parametrize("move,account,opener", [
        (move, account, opener)
        for move, spec in sorted(rd.WARMTH_MOVES.items())
        for account, openers in sorted((spec.get("openers") or {}).items())
        for opener in openers
    ])
    def test_opener_clears_the_house_ban_the_dial_and_am_r1(self, move, account, opener):
        probe = opener.replace("{detail}", "breadth")
        assert banned_language(probe) == [], f"{move}/{account}: house ban"
        assert ed.am_r1_hits(probe) == [], f"{move}/{account}: AM-R1"
        assert ed.violations("", probe, account=account, kind="reply",
                             include_house_bans=False) == [], f"{move}/{account}: dial"

    @pytest.mark.parametrize("move,account,opener", [
        (move, account, opener)
        for move, spec in sorted(rd.WARMTH_MOVES.items())
        for account, openers in sorted((spec.get("openers") or {}).items())
        for opener in openers
    ])
    def test_every_sanctioned_opener_carries_a_warmth_marker(self, move, account, opener):
        """THE GENERATOR AND THE GATE MUST AGREE.

        The drafter offers this opener and `warmth_register` decides whether the
        reply that carries it is warm. An opener the marker classes cannot see
        produces a reply that is warm to a reader and COLD to W1, so a long
        reply carrying our own sanctioned register would be rejected for
        coldness. This caught four openers on the first run.
        """
        probe = opener.replace("{detail}", "breadth")
        marks = rc.warmth_markers(probe, {"account": account})
        assert marks, f"{move}/{account}: {opener!r} carries no warmth marker"

    def test_the_live_guard_sweep_is_what_decides_availability(self):
        """MUTATION CHECK: the sweep must actually gate, not merely run.

        Adding a token to a persona's codex `banned` list has to withdraw the
        offending opener with no code change here — that is the mechanism that
        keeps the persona specs canonical rather than decorative.
        """
        assert rd.openers_for("kelly", "verdict_first")
        rd.clear_warmth_cache()
        codex = ed.codex_for("kelly")
        patched = type(codex)(
            account=codex.account, persona_kind=codex.persona_kind,
            dial_profile=codex.dial_profile, declared=codex.declared,
            emoji_policy=codex.emoji_policy, emoji_signature=codex.emoji_signature,
            banned=codex.banned + ("whole story",), zh=codex.zh,
        )
        real = ed.codex_for
        try:
            ed.codex_for = lambda account, root=None: (  # type: ignore[assignment]
                patched if account == "kelly" else real(account, root=root))
            rd.clear_warmth_cache()
            assert rd.openers_for("kelly", "verdict_first") == []
        finally:
            ed.codex_for = real  # type: ignore[assignment]
            rd.clear_warmth_cache()

    def test_no_opener_carries_an_exclamation_for_a_desk_that_bans_them(self):
        """Sophia's codex pins "zero exclamations" and it is absolute."""
        for spec in rd.WARMTH_MOVES.values():
            for account, openers in (spec.get("openers") or {}).items():
                if account == "meagan":
                    continue  # the one desk with an exclamation budget
                assert all("!" not in o for o in openers), account

    def test_cici_zh_gloss_openers_use_parentheses(self):
        """Verified LIVE against the shipped guard, not asserted from doctrine.

        A comma-appositive gloss is rejected by the expression dial as
        untranslated Chinese; only the parenthetical form passes. Every cici
        opener carrying a zh term must therefore use parentheses.
        """
        comma_form = "The overnight version is simpler, 结构性行情, a market that only moves in one place:"
        hits = ed.violations("", comma_form, account="cici", kind="reply",
                             include_house_bans=False)
        assert any("untranslated Chinese" in h for h in hits), (
            "the guard that makes this rule real has stopped firing")
        for spec in rd.WARMTH_MOVES.values():
            for opener in (spec.get("openers") or {}).get("cici") or ():
                if rd._CJK_RE.search(opener):
                    assert ed.violations("", opener, account="cici", kind="reply",
                                         include_house_bans=False) == []

    def test_a_zh_opener_is_withheld_from_a_non_zh_desk(self):
        """A Chinese phrase on Meagan's account is a defect, not a language choice."""
        for account in ("sophia", "kelly", "meagan"):
            for move in rd.warmth_moves_for(account, parent_shape="analysis_claim",
                                            family="reframe"):
                for opener in rd.openers_for(account, move):
                    assert not rd._CJK_RE.search(opener), (account, move)


class TestChangeMarkerWiring:
    def test_flat_confession_opener_contains_a_change_marker(self):
        """HARD WIRING, not a style note.

        `position_consistency` rejects a draft that contradicts an open thesis
        unless the draft carries a literal `_CHANGE_MARKERS` phrase — and a
        confession is BY CONSTRUCTION that contradiction. An opener phrased "I
        read this backwards" would trip the very critic the move exists to
        satisfy.
        """
        spec = rd.WARMTH_MOVES["flat_confession"]
        assert spec.get("needs_change_marker") is True
        for account, openers in (spec["openers"] or {}).items():
            for opener in openers:
                low = opener.lower()
                assert any(m in low for m in rc._CHANGE_MARKERS), (account, opener)

    def test_a_confession_survives_position_consistency_on_a_contradicted_thesis(self, cfg):
        theses = [{"subject": "breadth", "direction": "widening", "status": "open"}]
        gift = "Breadth is narrowing on every measure we run."
        draft = rd.compose("correction", gift, _ctx("kelly"), warmth="flat_confession")
        verdict = rc.position_consistency(draft, {"account": "kelly", "theses": theses})
        assert verdict["verdict"] == "pass", verdict["reasons"]
        # ... and the same claim WITHOUT the confession is what the critic kills.
        plain = rd.compose("correction", gift, _ctx("kelly"))
        assert rc.position_consistency(
            plain, {"account": "kelly", "theses": theses})["verdict"] == "reject"


# ===========================================================================
# 2. Composition — the fusion law
# ===========================================================================
class TestComposition:
    def test_compose_without_warmth_is_byte_for_byte_what_it_was(self):
        """Every pre-existing compose test must still pass unchanged."""
        assert rd.compose("missing_variable", GIFT, _ctx("kelly")) == \
            rd.compose("missing_variable", GIFT, _ctx("kelly"), warmth=None)

    def test_compose_fuses_conjunction_openers_without_a_full_stop(self):
        """THE LAW: warmth is fused into the clause that delivers the gift."""
        out = rd.compose("missing_variable", GIFT, _ctx("sophia"),
                         warmth="concede_and_hold")
        assert out.startswith("Fair, and the harder part is that equal weight")
        head = out.split("\n")[0]
        assert ". " not in head.split("equal weight")[0], head

    def test_compose_decap_preserves_tickers_and_proper_nouns(self):
        """The highest-probability ship-breaking bug in the whole build.

        A conjunction fuse decapitalises the gift because it is CONTINUING a
        sentence. Getting it wrong ships "fair, and the harder part is that
        nVIDIA...", which is a typo with our name on it.
        """
        for gift, keep in [
            ("$NVDA closed 2.4% lower.", "$NVDA"),
            ("NVIDIA guidance held.", "NVIDIA"),
            ("Powell kept policy tight.", "Powell"),
            ("EURUSD held its range.", "EURUSD"),
            ("S&P breadth stayed flat.", "S&P"),
            ("Fed guidance did not move.", "Fed"),
        ]:
            out = rd.compose("compression", gift, _ctx("sophia"),
                             warmth="concede_and_hold")
            assert keep in out, out
        # ... while an ordinary word IS lowercased, or the fuse did nothing.
        assert "that equal weight" in rd.compose(
            "compression", GIFT, _ctx("sophia"), warmth="concede_and_hold")

    def test_a_standalone_opener_never_manufactures_a_referent_free_sentence(self):
        """The colon join is deliberate, not cosmetic.

        Appending a period to "i was wrong about this one" (6 units, no
        referent) would manufacture exactly the opening sentence W3 exists to
        kill — our own register rejected by our own critic for obeying our own
        law.
        """
        out = rd.compose("correction", GIFT, _ctx("kelly"), warmth="flat_confession")
        assert out.startswith("i was wrong about this one: ")
        head = rc._sentences(out)[0]
        assert rc._referents(head), head

    def test_the_composer_budget_and_the_critic_bar_cannot_drift(self):
        """Two constants for one law is two chances to disagree.

        `compose` refuses at build time and `warmth_register` (W3) refuses at
        gate time; if they drift, the drafter either ships a shape the gate
        kills or refuses one the gate would allow.
        """
        assert rd.MAX_WARMTH_OPENER_UNITS == int(
            rc.DEFAULT_THRESHOLDS["warmth_opener_units"])

    def test_an_over_budget_standalone_opener_raises(self):
        """A composer that silently ships the bolted-on shape is worse than a
        loud build failure."""
        with pytest.raises(ValueError, match="bolted-on|content units"):
            rd.fuse_warmth(
                "Great point, really appreciate you laying this out so clearly.",
                GIFT, fuse="standalone")

    def test_the_families_canned_affect_line_is_replaced_not_stacked(self):
        """Two concessions in one reply is the theatre the move warns about."""
        out = rd.compose("acknowledgment_plus_one", GIFT, _ctx("kelly"),
                         warmth="specific_credit")
        assert "Agreed, with one addition." not in out
        assert out.startswith("the breadth line is the load bearing one.")

    def test_specific_credit_is_unavailable_when_detail_extraction_is_empty(self):
        """No generic fallback: the generic fallback IS the losing pattern."""
        assert rd.extract_detail("nice") == ""
        assert "specific_credit" not in rd.warmth_moves_for(
            "kelly", parent_shape="analysis_claim", family="missing_variable",
            has_detail=False)
        # ... and compose refuses to fill the slot with nothing.
        assert rd.compose("missing_variable", GIFT, _ctx("kelly", detail=""),
                          warmth="specific_credit") == \
            rd.compose("missing_variable", GIFT, _ctx("kelly", detail=""))

    def test_extract_detail_prefers_a_referent_carrying_noun(self):
        """A credit opener is a full sentence, so its detail must be a referent
        or the sentence trips both W3 and persona_label."""
        detail = rd.extract_detail("the second chart shows breadth rolling over")
        assert detail == "breadth"
        assert rc._referents(f"the {detail} line is the load bearing one.")


# ===========================================================================
# 3. Rotation — no move may harden into a tell
# ===========================================================================
class TestRotation:
    def test_rotate_warmth_is_least_recently_used(self):
        pool = ["verdict_first", "concede_and_hold", "concrete_image"]
        assert rd.rotate_warmth(["verdict_first", "concede_and_hold"],
                                allowed=pool) == "concrete_image"
        assert rd.rotate_warmth(["concrete_image", "verdict_first"],
                                allowed=pool) == "concede_and_hold"

    def test_rotate_warmth_returns_none_rather_than_ignoring_an_empty_pool(self):
        """An empty pool means every move was found WRONG for this parent.

        Falling back to the full register would ship the exact off-shape warmth
        the fitness rules exist to prevent, so None (no warmth) is the answer.
        """
        assert rd.rotate_warmth(["verdict_first"], allowed=[]) is None

    def test_a_warmth_move_cannot_repeat_inside_its_window(self):
        """Drive the real rotation over a run and assert nothing takes over.

        This is the anti-tell property, and it is why the LRU key is the LAST
        use rather than the first: keyed on the first use, this same loop
        produced a 6-to-1 spread across a five-move pool while every individual
        pick still looked like rotation.
        """
        pool = rd.warmth_moves_for("kelly", parent_shape="analysis_claim",
                                   family="reframe", has_detail=True, has_thesis=True)
        assert len(pool) >= 3
        recent: list[str] = []
        seen: list[str] = []
        for _ in range(len(pool) * 4):
            move = rd.rotate_warmth(recent[-20:], allowed=pool)
            assert move is not None
            seen.append(move)
            recent.append(move)
        assert set(seen) == set(pool)
        assert max(seen.count(m) for m in pool) - min(seen.count(m) for m in pool) <= 1
        # No move repeats before the whole pool has been spent, in ANY window.
        for start in range(len(seen) - len(pool) + 1):
            window = seen[start:start + len(pool)]
            assert len(set(window)) == len(pool), window

    def test_the_warmth_lru_is_independent_of_the_family_lru(self):
        """Two independent LRUs is what stops one PAIRING becoming a signature.

        With the family LRU pinned to one value, the warmth axis must keep
        rotating; a single LRU over the product would not.
        """
        pool = rd.warmth_moves_for("kelly", parent_shape="analysis_claim",
                                   family="reframe", has_detail=True, has_thesis=True)
        recent_families = ["reframe"] * 20
        recent_warmth: list[str] = []
        picks = []
        for _ in range(len(pool)):
            fam = rd.rotate_family(recent_families, allowed=["reframe"])
            move = rd.rotate_warmth(recent_warmth, allowed=pool)
            picks.append((fam, move))
            recent_warmth.append(move)
        assert {f for f, _ in picks} == {"reframe"}
        assert len({m for _, m in picks}) == len(pool)


# ===========================================================================
# 4. Fitness + availability gates
# ===========================================================================
class TestFitnessGate:
    @pytest.mark.parametrize("text,shape", [
        ("We got hacked last night and the fix is going out now.", "personal_setback"),
        ("We just shipped the new screener.", "personal_win"),
        ("BREAKING: payrolls come in at 145k.", "wire_or_headline"),
        ("This chart is the one that matters.", "chart_post"),
        ("Full thread on the funding side below.", "resource_or_thread"),
        ("Actually, that is not right about the curve.", "correction_of_someone_else"),
        ("Nobody understands how insane this positioning is.", "hot_take"),
        ("Rates will be lower by year-end.", "prediction"),
        ("What is everyone doing with duration here?", "question_to_the_room"),
        ("Breadth looked fine to me today.", "analysis_claim"),
        ("There were casualties reported at the site.", "sensitive_event"),
    ])
    def test_classify_parent_is_deterministic_and_in_vocabulary(self, text, shape):
        assert rd.classify_parent(text) == shape
        assert shape in rd.PARENT_SHAPES

    def test_classify_parent_returns_none_only_for_no_text(self):
        assert rd.classify_parent("") is None
        assert rd.classify_parent({"text": ""}) is None
        assert rd.classify_parent({"text": "anything at all here"}) == "analysis_claim"

    def test_a_move_wrong_for_the_parent_shape_is_unavailable(self):
        """`concede_and_hold` on a data post has no position to concede."""
        assert "concede_and_hold" in rd.warmth_moves_for(
            "kelly", parent_shape="analysis_claim", family="reframe")
        assert "concede_and_hold" not in rd.warmth_moves_for(
            "kelly", parent_shape="data_post", family="reframe")

    def test_no_warmth_move_at_all_reaches_a_sensitive_event(self):
        for account in EMPLOYEES:
            assert rd.warmth_moves_for(account, parent_shape="sensitive_event",
                                       family="reframe", tier="relationship",
                                       has_detail=True, has_thesis=True) == []

    def test_quiet_sympathy_is_the_only_move_on_a_personal_setback(self):
        pool = rd.warmth_moves_for("meagan", parent_shape="personal_setback",
                                   family="human_reaction", tier="relationship",
                                   has_detail=True, has_thesis=True)
        assert pool == ["quiet_sympathy"]

    def test_quiet_sympathy_needs_the_relationship_tier(self):
        assert rd.warmth_moves_for("meagan", parent_shape="personal_setback",
                                   family="human_reaction", tier="conversion") == []

    def test_flat_confession_is_unavailable_without_an_open_thesis(self):
        """AM-R1 applied to our own reasoning history: we do not invent having
        been wrong any more than we invent having been anywhere."""
        assert "flat_confession" not in rd.warmth_moves_for(
            "kelly", parent_shape="analysis_claim", family="correction",
            has_thesis=False)
        assert "flat_confession" in rd.warmth_moves_for(
            "kelly", parent_shape="analysis_claim", family="correction",
            has_thesis=True)

    def test_a_move_outside_families_ok_is_unavailable(self):
        assert "wry_solidarity" in rd.warmth_moves_for(
            "kelly", parent_shape="hot_take", family="reframe")
        assert "wry_solidarity" not in rd.warmth_moves_for(
            "kelly", parent_shape="hot_take", family="author_question")

    def test_wry_solidarity_is_withdrawn_when_the_target_would_be_a_person(self):
        """The TARGET is what separates the move from the WSJ/SBF antipattern."""
        assert rd._targets_a_person("you keep saying this every cycle") is True
        assert rd._targets_a_person("this gets rediscovered every cycle") is False
        assert rd._targets_a_person("this gets rediscovered every cycle",
                                    parent_author="cycle") is False  # common word
        assert rd._targets_a_person("northman has a point here",
                                    parent_author="NorthmanTrader") is True


class TestDialFloorIsWired:
    """`dial_floor` is DECLARED and dead in FAMILIES. Here it must be alive."""

    def test_families_dial_floor_is_still_the_dead_field_this_replaces(self):
        """Pins the asymmetry the build is built on, so a later edit that wires
        FAMILIES.dial_floor has to come here and say so."""
        assert all("dial_floor" in spec for spec in rd.FAMILIES.values())

    def test_the_flagship_is_offered_no_warmth_at_all(self):
        """Charter §2 amendment 3: the flagship stays an evidence desk."""
        assert rc.reply_dial_for("flagship") == 1
        for family in rd.FAMILIES:
            assert rd.warmth_moves_for("flagship", parent_shape="analysis_claim",
                                       family=family, has_detail=True,
                                       has_thesis=True, tier="relationship") == []

    def test_dial_floor_two_moves_are_withheld_from_a_dial_one_desk(self):
        """MUTATION CHECK. Granting the flagship every opener must still leave
        it only the dial-floor-1 moves — otherwise `dial_floor` is decorative
        here too and the flagship's silence proves nothing but missing copy.
        """
        patched = {}
        for move, spec in rd.WARMTH_MOVES.items():
            openers = dict(spec.get("openers") or {})
            openers["flagship"] = ("This is the part that matters",)
            patched[move] = {**spec, "openers": openers}
        real = rd.WARMTH_MOVES
        try:
            rd.WARMTH_MOVES = patched  # type: ignore[assignment]
            rd.clear_warmth_cache()
            pool = set(rd.warmth_moves_for(
                "flagship", parent_shape="analysis_claim", family=None,
                has_detail=True, has_thesis=True, tier="relationship"))
        finally:
            rd.WARMTH_MOVES = real  # type: ignore[assignment]
            rd.clear_warmth_cache()
        assert pool, "the mutation did not take"
        assert all(rd.WARMTH_MOVES[m]["dial_floor"] == 1 for m in pool), sorted(pool)
        assert "flat_confession" not in pool and "wry_solidarity" not in pool

    def test_an_employee_desk_reaches_the_dial_two_moves(self):
        assert rc.reply_dial_for("kelly") == 2
        pool = rd.warmth_moves_for("kelly", parent_shape="analysis_claim",
                                   family="reframe", has_thesis=True)
        assert any(rd.WARMTH_MOVES[m]["dial_floor"] == 2 for m in pool)


# ===========================================================================
# 5. Four desks, four registers — the operator's actual ask
# ===========================================================================
class TestPerPersonaDistinctness:
    def test_the_same_fact_produces_four_register_distinct_replies(self, cfg):
        """ASSERTED ON DISTINCTNESS, NOT ON VIBES.

        One market fact, one parent, one reasoning family. The four employee
        desks must produce four different opening registers — that is the whole
        product claim, and a build that quietly gave them one voice would pass
        every other test in this file.
        """
        drafts = {}
        for account in EMPLOYEES:
            out = rd.draft_reply(account=account, target=TARGET, facts=FACTS,
                                 family="reframe", has_thesis=True, cfg=cfg)
            drafts[account] = out["draft"]
            assert out["warmth"], f"{account} drafted cold"
        assert len(set(drafts.values())) == 4, drafts
        # Distinct in the OPENING clause specifically, not merely somewhere.
        heads = {a: d.split("\n")[0][:40] for a, d in drafts.items()}
        assert len(set(heads.values())) == 4, heads
        # And every one of them clears the full critic roster.
        for account, draft in drafts.items():
            verdict = rc.run_critics(draft, _critic_ctx(account, cfg, family="reframe"))
            assert verdict["verdict"] == "pass", (account, verdict["reasons"])

    def test_a_move_out_of_character_is_unavailable_to_that_persona(self):
        """The §4 grounding, one assertion per exclusion.

        kelly: terse dry register makes sympathy read as sarcastic.
        cici:  "bright, worldly" — world-weariness is off-register.
        meagan: her codex requires the playful line THEN the useful one, so a
                bare verdict is off-shape.
        """
        assert rd.openers_for("kelly", "quiet_sympathy") == []
        assert rd.warmth_moves_for("kelly", parent_shape="personal_setback",
                                   family="human_reaction", tier="relationship") == []
        assert rd.openers_for("cici", "wry_solidarity") == []
        assert "wry_solidarity" not in rd.warmth_moves_for(
            "cici", parent_shape="hot_take", family="reframe")
        assert rd.openers_for("meagan", "verdict_first") == []
        assert "verdict_first" not in rd.warmth_moves_for(
            "meagan", parent_shape="analysis_claim", family="reframe")

    def test_every_employee_reaches_at_least_three_moves_on_a_plain_claim(self):
        """A desk with one move has a tell, not a register."""
        for account in EMPLOYEES:
            pool = rd.warmth_moves_for(account, parent_shape="analysis_claim",
                                       family=None, has_detail=True, has_thesis=True)
            assert len(pool) >= 3, (account, pool)


# ===========================================================================
# 6. The drafter seam
# ===========================================================================
class TestDrafterSeam:
    def test_warmth_is_composed_deterministically_before_the_model_runs(self, monkeypatch, cfg):
        """ACCEPTANCE GATE 1: a muted model must still produce a WARM reply.

        This is the whole difference between the warmth build and a prompt
        tweak. With the LLM disarmed there is no phrasing pass at all, and the
        draft still has to carry the move.
        """
        monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
        out = rd.draft_reply(account="kelly", target=TARGET, facts=FACTS,
                             family="reframe", has_thesis=True, cfg=cfg)
        assert out["voice"]["mode"] == "off"
        assert out["warmth"] and rc.warmth_markers(out["draft"], {"account": "kelly"})

    def test_an_empty_gift_is_still_an_abstention(self, cfg):
        """A warmth move may never manufacture a reply out of nothing."""
        out = rd.draft_reply(account="kelly", target=TARGET,
                             facts={"facts": [], "numbers_whitelist": []}, cfg=cfg)
        assert out["draft"] == "" and out["warmth"] is None

    def test_the_sympathy_exception_is_the_only_giftless_reply(self, cfg):
        out = rd.draft_reply(
            account="meagan",
            target={"text": "We got hacked last night, fix is going out now.",
                    "author": "somefounder"},
            facts={"facts": [], "numbers_whitelist": []},
            tier="relationship", cfg=cfg)
        assert out["warmth"] == "quiet_sympathy"
        assert out["draft"] == "that is a rough one. hope the rebuild is quick"
        assert out["components"]["relationship_only"] is True
        # ... and it is unavailable on the conversion tier, where it would be a
        # referent-free growth reply.
        assert rd.draft_reply(
            account="meagan",
            target={"text": "We got hacked last night, fix is going out now.",
                    "author": "somefounder"},
            facts={"facts": [], "numbers_whitelist": []},
            tier="conversion", cfg=cfg)["draft"] == ""

    def test_quiet_sympathy_never_contains_the_parent_author_name(self, cfg):
        """A first name implies a relationship we have not established."""
        for account in ("meagan", "cici", "sophia"):
            for opener in rd.openers_for(account, "quiet_sympathy"):
                assert rd.author_name_hits(opener, "Niall Ferguson") == []
                assert rd.author_name_hits(opener, "Jon") == []

    def test_the_family_pool_prefers_a_family_the_register_can_warm(self, cfg):
        """A family this parent admits no move for drafts an item the gate
        kills — an abstention nobody can see. The rotation avoids it."""
        out = rd.draft_reply(account="kelly", target=TARGET, facts=FACTS,
                             has_thesis=True, cfg=cfg)
        assert out["warmth"] is not None
        assert rd.warmth_moves_for("kelly", parent_shape=out["parent_shape"],
                                   family=out["family"], has_thesis=True,
                                   has_detail=True)


# ===========================================================================
# 7. The anti-cold critic (W1/W2/W3)
# ===========================================================================
class TestWarmthRegisterCritic:
    def test_the_critic_is_in_the_register_and_wired(self):
        assert "warmth_register" in rc.CRITICS
        assert "warmth_register" in rc._CRITIC_FUNCS

    def test_w1_kills_a_twelve_unit_cold_printout(self, cfg):
        cold = ("Equal weight closed flat while the index added 0.9% and semis "
                "added 2.4%. The price move is the reaction. Breadth is the test.")
        verdict = rc.run_critics(cold, _critic_ctx("kelly", cfg))
        assert "warmth_register" in verdict["rejected_by"]
        assert any("cold printout" in r for r in verdict["reasons"])

    def test_w1_spares_a_terse_data_drop(self, cfg):
        """CALIBRATED AGAINST THE WINNERS. The corpus's best analytical replies
        are 3 to 5 units; killing those would contradict the strongest measured
        effect in the data."""
        for terse in ("Support at 900-925", "Actually closer to 2.4%",
                      "Equal weight closed flat."):
            assert rc.warmth_register(terse, _critic_ctx("kelly", cfg))["verdict"] == "pass"

    def test_w1_is_inert_for_the_flagship_and_the_founder(self, cfg):
        cold = ("Equal weight closed flat while the index added 0.9% and semis "
                "added 2.4%. The price move is the reaction. Breadth is the test.")
        for account in ("flagship", "founder"):
            assert rc.warmth_register(cold, _critic_ctx(account, cfg))["verdict"] == "pass"

    def test_w2_kills_a_cold_run_but_not_the_first_cold_reply(self, cfg):
        short = "Semis added 2.4%, equal weight flat."
        assert rc.warmth_register(short, _critic_ctx("kelly", cfg))["verdict"] == "pass"
        cold_run = [{"account": "kelly", "draft": "Equal weight flat, index up."}] * 10
        verdict = rc.warmth_register(short, _critic_ctx("kelly", cfg, corpus=cold_run))
        assert verdict["verdict"] == "reject"
        assert any("cold register" in r for r in verdict["reasons"])
        warm_run = [{"account": "kelly",
                     "draft": "honestly the breadth read is the whole story"}] * 10
        assert rc.warmth_register(
            short, _critic_ctx("kelly", cfg, corpus=warm_run))["verdict"] == "pass"

    def test_w2_is_scoped_to_the_account_not_the_fleet(self, cfg):
        short = "Semis added 2.4%, equal weight flat."
        other = [{"account": "cici", "draft": "Equal weight flat, index up."}] * 10
        assert rc.warmth_register(
            short, _critic_ctx("kelly", cfg, corpus=other))["verdict"] == "pass"

    def test_w2_is_inert_below_min_history(self, cfg):
        """PINS THE DELIBERATE OPEN FAIL so a later "hardening" PR has to argue.

        Making an empty history reject would block the lane at arming, which is
        exactly the failure class that kept this desk dark. The mitigation is
        supply side (the drafter offers a move from item one), not gate side.
        """
        short = "Semis added 2.4%, equal weight flat."
        thin = [{"account": "kelly", "draft": "Equal weight flat."}] * 3
        assert rc.warmth_register(
            short, _critic_ctx("kelly", cfg, corpus=thin))["verdict"] == "pass"

    def test_w3_kills_a_bolted_on_praise_sentence(self, cfg):
        bolted = ("Great point, really appreciate you laying this out so clearly. "
                  + GIFT)
        verdict = rc.warmth_register(bolted, _critic_ctx("kelly", cfg))
        assert verdict["verdict"] == "reject"
        assert any("bolted-on warmth" in r for r in verdict["reasons"])

    def test_w3_spares_a_short_appreciation_and_every_sanctioned_opener(self, cfg):
        assert rc.warmth_register("Much appreciated: " + GIFT,
                                  _critic_ctx("kelly", cfg))["verdict"] == "pass"
        for account in EMPLOYEES:
            for move in rd.WARMTH_MOVES:
                for opener in rd.openers_for(account, move):
                    text = rd.fuse_warmth(
                        opener.replace("{detail}", "breadth"), GIFT,
                        fuse=str(rd.WARMTH_MOVES[move]["fuse"]))
                    verdict = rc.warmth_register(text, _critic_ctx(account, cfg))
                    assert verdict["verdict"] == "pass", (account, move, verdict["reasons"])

    def test_the_calibration_fixture_still_passes(self, cfg):
        """biancoresearch's cold Fed-vote correction: 18 likes, 0.0067 eng/view.

        A winning reply, and the reason W3 is scoped to warmth ABOUT THE THREAD
        rather than to any long referent-free opening sentence. If a marker-list
        or threshold edit reddens this, the edit is wrong, not the reply.
        """
        text = ("The idea that the Fed has 12 independent voters is far fetched. "
                "The Board votes as a bloc and the regional presidents rotate, so "
                "the guidance has not really changed.")
        verdict = rc.warmth_register(text, _critic_ctx("kelly", cfg))
        assert verdict["verdict"] == "pass", verdict["reasons"]

    def test_the_kill_switch_disarms_the_whole_critic(self, cfg):
        cold = ("Equal weight closed flat while the index added 0.9% and semis "
                "added 2.4%. The price move is the reaction. Breadth is the test.")
        off = {**cfg, "reply_desk": {**cfg["reply_desk"], "warmth": {"enabled": False}}}
        assert rc.warmth_register(cold, _critic_ctx("kelly", off))["verdict"] == "pass"

    def test_the_thresholds_are_config_keys_not_constants(self, cfg):
        """Charter §8. A bar hardcoded past `_threshold` cannot be tuned."""
        for key in ("warmth_min_units", "warmth_window", "warmth_min_history",
                    "warmth_share_floor", "warmth_opener_units"):
            assert key in rc.DEFAULT_THRESHOLDS
        loose = {**cfg, "reply_desk": {**cfg["reply_desk"],
                                       "critic_thresholds": {"warmth_min_units": 99}}}
        cold = ("Equal weight closed flat while the index added 0.9% and semis "
                "added 2.4%. The price move is the reaction. Breadth is the test.")
        assert rc.warmth_register(cold, _critic_ctx("kelly", loose))["verdict"] == "pass"


class TestWarmthMarkers:
    def test_stance_verbs_and_am_r1_transaction_verbs_are_disjoint(self):
        """A "stance" that is really a position claim would launder AM-R1."""
        transaction = (
            "bought", "sold", "shorted", "longed", "own", "hold", "holding",
            "added", "trimmed", "entered", "exited", "long", "short",
            "made", "lost", "filled", "stopped",
        )
        assert set(rc._STANCE_VERBS) & set(transaction) == set()
        for verb in rc._STANCE_VERBS:
            probe = f"I {verb} the breadth read here."
            assert ed.am_r1_hits(probe) == [], probe

    def test_class_a_needs_the_verb_in_the_same_clause(self):
        assert rc.warmth_markers("I keep coming back to breadth")
        assert not rc.warmth_markers(
            "We closed the file. Breadth data was published and then reviewed.")

    def test_class_c_reads_the_signature_from_the_live_codex(self):
        assert any(m.startswith("C:") for m in
                   rc.warmth_markers("breadth is the read \U0001F50D", {"account": "kelly"}))
        # ... and another desk's glyph is not this desk's register.
        assert not any(m.startswith("C:") for m in
                       rc.warmth_markers("breadth is the read \U0001F50D", {"account": "meagan"}))

    def test_markers_name_what_was_found(self):
        """A rejection must name what was missing, never assert a mood."""
        marks = rc.warmth_markers("honestly the breadth read is the whole story")
        assert all(m[:2] in ("A:", "B:", "C:") for m in marks)
        assert "B:honestly" in marks


# ===========================================================================
# 8. The fabrication critic (AM-R1)
# ===========================================================================
class TestFabricationCritic:
    def test_the_critic_is_in_the_register_and_wired(self):
        assert "fabrication" in rc.CRITICS
        assert "fabrication" in rc._CRITIC_FUNCS

    @pytest.mark.parametrize("draft,why", [
        ("I bought the dip here, breadth is still flat.", "position"),
        ("I met with a source at the Treasury, breadth is still flat.", "experience"),
        ("This platform changed my life, breadth is still flat.", "testimonial"),
        ("Back at my desk now, breadth is still flat.", "circumstance"),
        ("my third coffee says breadth is still flat.", "routine"),
        ("Rough week for me, breadth is still flat.", "feeling"),
        ("Over here in Hong Kong breadth is still flat.", "presence"),
        ("I am on my second espresso, breadth is still flat.", "routine"),
    ])
    def test_a_fabricated_biography_rejects_with_the_sentence_quoted(self, draft, why):
        verdict = rc.fabrication(draft, {"account": "kelly"})
        assert verdict["verdict"] == "reject", (why, draft)
        # THE SENTENCE, not the pattern: a reject an operator cannot act on is
        # a reject that gets overridden.
        assert any(draft.split(".")[0] in r for r in verdict["reasons"]), verdict
        assert any("AM-R1" in r for r in verdict["reasons"])

    @pytest.mark.parametrize("draft", [
        "the part I cannot settle from here is whether breadth follows.",
        "I had this wrong: breadth never followed the index up.",
        "I keep coming back to the breadth read on this one.",
        "the breadth line is the load bearing one.",
        "that is a rough one. hope the rebuild is quick",
        "We will be told this was obvious afterwards: breadth stayed flat.",
    ])
    def test_lawful_first_person_analysis_is_spared(self, draft):
        """The asymmetry the whole register rests on: a predicate about her
        THINKING is lawful, a predicate about her CIRCUMSTANCES is not."""
        assert rc.fabrication(draft, {"account": "kelly"})["verdict"] == "pass"

    def test_every_sanctioned_opener_is_spared(self):
        for move, spec in rd.WARMTH_MOVES.items():
            for account, openers in (spec.get("openers") or {}).items():
                for opener in openers:
                    probe = opener.replace("{detail}", "breadth")
                    verdict = rc.fabrication(probe, {"account": account})
                    assert verdict["verdict"] == "pass", (move, account, verdict["reasons"])

    def test_the_parent_authors_first_name_rejects(self):
        verdict = rc.fabrication("Niall, breadth is still flat here.",
                                 {"account": "kelly", "parent_author": "Niall Ferguson"})
        assert verdict["verdict"] == "reject"
        assert any("first-name" in r for r in verdict["reasons"])

    def test_a_handle_that_is_an_ordinary_word_does_not_ban_vocabulary(self):
        assert rc.fabrication("the market read is flat",
                              {"account": "kelly", "parent_author": "market"})["verdict"] == "pass"

    def test_the_critic_binds_on_a_codex_less_account(self):
        """THE REASON THIS IS NOT LEFT TO `vocab`.

        `vocab` reaches AM-R1 only through `expression_dial.violations`, which
        returns [] for an account with no codex — the flagship. So the one gate
        between a real name and a fabricated claim was absent for part of the
        roster.
        """
        assert ed.codex_for("flagship") is None
        assert ed.violations("", "I bought the dip here.", account="flagship",
                             kind="reply", include_house_bans=False) == []
        assert rc.fabrication("I bought the dip here.",
                              {"account": "flagship"})["verdict"] == "reject"

    def test_an_unloadable_detector_holds_the_draft_rather_than_passing_it(self, monkeypatch):
        """A gate we cannot load is not a gate that passed."""
        import builtins
        real_import = builtins.__import__

        def _boom(name, *a, **k):
            if name == "engine.marketing.expression_dial":
                raise ImportError("no dial")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", _boom)
        verdict = rc.fabrication("breadth is flat", {"account": "kelly"})
        assert verdict["verdict"] == "reject"


class TestPersonaLabelExemption:
    def test_the_exemption_is_double_gated(self, cfg):
        sympathy = "that is a rough one. hope the rebuild is quick"
        assert rc.persona_label(sympathy, {})["verdict"] == "reject"
        assert rc.persona_label(sympathy, {"relationship_only": True})["verdict"] == "reject"
        assert rc.persona_label(sympathy, {"warmth": "quiet_sympathy"})["verdict"] == "reject"
        assert rc.persona_label(sympathy, {"relationship_only": True,
                                           "warmth": "quiet_sympathy"})["verdict"] == "pass"

    def test_the_exemption_cannot_launder_a_growth_reply(self):
        """Another warmth move with the flag set must still need a referent."""
        assert rc.persona_label("that is the whole story",
                                {"relationship_only": True,
                                 "warmth": "verdict_first"})["verdict"] == "reject"


# ===========================================================================
# 9. The phrasing prompt + the repair turn
# ===========================================================================
class TestVoicePrompt:
    def test_the_system_prompt_carries_the_warmth_law_and_the_journalist_test(self):
        prompt = rv.SYSTEM_PROMPT
        assert "WHAT WARMTH IS AND IS NOT" in prompt
        assert "FUSED INTO THE CLAUSE" in prompt
        assert "could a journalist print this as a fact about her" in prompt
        assert "THE BRIGHT LINE" in prompt
        # Both columns, so the model is told what warmth IS, not only what it is not.
        assert "LAWFUL" in prompt and "FORBIDDEN" in prompt

    def test_the_user_turn_states_the_warmth_move_as_an_intent(self):
        msg = rv.build_user_message(
            draft="that is the whole story: breadth stayed flat.",
            family="compression", account="kelly", parent_text=PARENT,
            warmth="verdict_first", warmth_spec=rd.WARMTH_MOVES["verdict_first"])
        assert "WARMTH MOVE: verdict_first" in msg
        assert rd.WARMTH_MOVES["verdict_first"]["does"][:30] in msg

    def test_no_warmth_move_means_no_warmth_block(self):
        msg = rv.build_user_message(draft="x", family="compression",
                                    account="kelly", parent_text=PARENT)
        assert "WARMTH MOVE" not in msg

    def test_a_repair_turn_names_the_failures_and_nothing_else(self):
        msg = rv.build_user_message(
            draft="x", family="compression", account="kelly", parent_text=PARENT,
            violations=["reply_value: 70 words — the bar is 60"])
        assert "YOUR PREVIOUS REPLY WAS REJECTED" in msg
        # The dash tell is stripped: echoing it back would burn the repair turn
        # on a defect the gate itself supplied.
        assert "—" not in msg

    def test_validate_reply_copy_rejects_a_life_fact_and_keeps_the_fallback(self):
        """ACCEPTANCE GATE: warmth never costs us the deterministic fallback."""
        violations = rv.validate_reply_copy(
            "Back at my desk, and equal weight closed flat.",
            draft="that is the whole story: equal weight closed flat.",
            numbers_whitelist=WHITELIST, parent_text=PARENT, account="kelly",
            family="compression")
        assert any("fabrication" in v for v in violations)

    def test_validate_reply_copy_rejects_a_cold_rewrite(self):
        """A model that politely deletes the warmth move has handed back the
        cold version, and the WARM deterministic draft must ship instead."""
        violations = rv.validate_reply_copy(
            "Equal weight closed flat while the index added 0.9% and semis added "
            "2.4%. The price move is the reaction and breadth is the test.",
            draft="that is the whole story: equal weight closed flat.",
            numbers_whitelist=WHITELIST, parent_text=PARENT, account="kelly",
            family="compression")
        assert any("warmth_register" in v for v in violations)
