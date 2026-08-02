"""XG-W4b §E — the persona INTERNAL MODEL, the familiarity ladder, and the
producer wiring the anti-sameness rotation has been missing since it shipped.

WHAT EACH BLOCK PINS, so a later edit knows what it is breaking:

  TestOverlayLoader        the loader returns the spec's shape for a seeded desk
                           and SAFE DEFAULTS for an unseeded one, and raises on
                           the one field that can fabricate a real person's life.
  TestTheFence             `persona_model` is not a persona-spec reader, and the
                           advisory `lexicon.avoid` has not become a second ban
                           list outside the adjudicated seam.
  TestResponseMix          six weights per desk, each row summing to 1.0, the
                           four-employee mean landing on the operator's
                           distribution, and the committed config not drifting
                           from the code rows that back it up.
  TestFamiliarityLadder    the tier for every rung, PER TIER, including the two
                           fail-closed directions (a decline, a stale contact).
  TestTierPolicy           what each tier changes in the draft — the table the
                           drafter lane consumes.
  TestToneAmR1Gate         the sharpest rule in §E: a claim about a shared past
                           is unavailable unless it is checkable from our store.
  TestRelationStageScale   the `relationship_stage` feature scored every real
                           row at zero, and the census that refutes it.
  TestProducerRotationWiring
                           THE PIN THAT GOES RED AGAINST MAIN: `recent_warmth`
                           and `recent_tails` actually reach `draft_reply`, the
                           queue item persists them, and the window breaks a
                           warmth repeat the empty window allows.

Stdlib + pyyaml only (marketing-engine CI lane). No network, no LLM.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import persona_memory as pmem  # noqa: E402
from engine.marketing import persona_model as pm  # noqa: E402
from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_drafter as rd  # noqa: E402
from engine.marketing import reply_producer as rp  # noqa: E402
from engine.marketing import reply_queue as rq  # noqa: E402
from engine.marketing import reply_score as rs  # noqa: E402

NOW = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)
EMPLOYEES = ("sophia", "kelly", "cici", "meagan")
EVIDENCE_DESKS = ("flagship", "founder")

#: The operator's brief, verbatim: "APPROXIMATE TARGET DISTRIBUTION: 30% short
#: reactions, 25% analytical additions, 15% agreement with nuance, 15%
#: disagreement, 10% genuine questions, 5% humor."
OPERATOR_TARGET = {
    "short_reaction": 0.30, "analytical_addition": 0.25,
    "agreement_nuance": 0.15, "disagreement": 0.15,
    "question": 0.10, "humor": 0.05,
}

#: The MEASURED four-employee mean of the shipped tables (§B.3 states these
#: same six numbers). Pinned exactly so a row edit has to restate the fleet
#: consequence rather than hide inside a tolerance band.
EMPLOYEE_MEAN = {
    "short_reaction": 0.300, "analytical_addition": 0.265,
    "agreement_nuance": 0.160, "disagreement": 0.135,
    "question": 0.080, "humor": 0.060,
}


@pytest.fixture(autouse=True)
def _clean_caches():
    """Every test that writes an overlay into a tmp root needs a cold cache."""
    pm.clear_model_cache()
    rd.clear_warmth_cache()
    yield
    pm.clear_model_cache()
    rd.clear_warmth_cache()


@pytest.fixture(scope="module")
def marketing_cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


def _write_overlay(root: Path, account: str, payload: dict) -> Path:
    d = root / "config" / "marketing" / "persona_models"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{account}.yml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


# ===========================================================================
# The overlay loader
# ===========================================================================
class TestOverlayLoader:
    def test_a_seeded_desk_returns_the_spec_shape(self):
        """§F.1: every field the API declares is populated for a seeded desk."""
        m = pm.load_model("kelly", root=ROOT)
        assert m.source == "model.yml"
        assert m.account == "kelly"
        assert len(m.beliefs) >= 3
        assert "credit confirms equity, never the reverse" in m.beliefs
        assert "denominator" in m.expertise
        assert m.uncertainties and m.challenges
        assert m.confidence.hedge_rate == pytest.approx(0.18)
        assert m.confidence.unhedged_verdict_ok is True
        assert m.confidence.sentence_units_p50 == 9
        assert m.confidence.sentence_units_p90 == 18
        assert "denominator" in m.lexicon.prefer
        assert "sentiment" in m.lexicon.avoid
        assert m.permitted_experience == ()
        assert m.tone_pool("familiar") and m.tone_pool("regular")
        assert m.tone_pool("stranger") == () and m.tone_pool("acquainted") == ()

    @pytest.mark.parametrize("account", EMPLOYEES)
    def test_every_employee_desk_carries_an_overlay(self, account):
        """Four desks, four files. A desk with no model has no register to be
        consistent with, which is the state this whole section exists to end."""
        assert pm.model_path(account, ROOT).exists()
        m = pm.load_model(account, root=ROOT)
        assert m.source == "model.yml", f"{account} silently fell back to the default"
        assert m.beliefs and m.expertise and m.uncertainties and m.challenges

    @pytest.mark.parametrize("account", EVIDENCE_DESKS)
    def test_an_unseeded_desk_returns_safe_defaults_and_no_tone(self, account):
        """The flagship and the founder get NO overlay, and the absence IS the
        rule: §5's register map lists "anything warm" in their Never column, so
        "an evidence desk does not do familiarity" is expressed by having no
        pool to draw from rather than by another exclusion table."""
        m = pm.load_model(account, root=ROOT)
        assert m.source == "default"
        assert m.beliefs == () and m.expertise == () and m.challenges == ()
        assert m.confidence.hedge_rate == pytest.approx(0.08)
        assert m.confidence.unhedged_verdict_ok is True
        for tier in pm.FAMILIARITY_TIERS:
            assert m.tone_pool(tier) == ()

    def test_an_absent_account_never_raises(self, tmp_path):
        """`load_model` is called on every draft; absence is not an error."""
        assert pm.load_model("nobody", root=tmp_path).source == "default"
        assert pm.load_model("", root=tmp_path).source == "default"

    def test_a_non_empty_permitted_experience_RAISES(self, tmp_path):
        """AM-R1, the highest-risk field in the brief.

        The operator's rule is absolute: never invent trades, employment,
        locations, relationships or firsthand experience. The field exists so
        that licensing one is a deliberate, reviewable act — so a YAML edit
        alone must FAIL, and the error must name what else has to change or it
        is a raise an operator routes around.

        MUTATION CHECK: delete the raise in `load_model` and this goes green
        while a desk silently gains a biography.
        """
        _write_overlay(tmp_path, "kelly", {
            "schema": pm.MODEL_SCHEMA, "account": "kelly",
            "permitted_experience": ["traded this setup in 2019"],
        })
        with pytest.raises(ValueError) as exc:
            pm.load_model("kelly", root=tmp_path)
        msg = str(exc.value)
        assert "permitted_experience" in msg
        assert "MUST stay empty" in msg
        # Names the OTHER half of the change, not just the complaint.
        assert "canon" in msg and "AM-R1" in msg

    def test_every_shipped_hedge_rate_sits_under_the_critic_ceiling(self):
        """§E.2: the drafter's target must sit STRICTLY under the critic's
        rolling uncertainty-marker cap, or the desk aims at its own rejection."""
        for account in EMPLOYEES + EVIDENCE_DESKS:
            rate = pm.load_model(account, root=ROOT).confidence.hedge_rate
            assert rate < pm.HEDGE_RATE_CEILING, (
                f"{account}: hedge_rate {rate} is at or above the critic's "
                f"ceiling {pm.HEDGE_RATE_CEILING}")

    def test_a_hedge_rate_at_the_ceiling_RAISES(self, tmp_path):
        """MUTATION CHECK for the rule above: a clamp instead of a raise would
        let the YAML keep lying about what the desk is aiming for."""
        _write_overlay(tmp_path, "kelly", {
            "schema": pm.MODEL_SCHEMA, "account": "kelly",
            "confidence": {"hedge_rate": pm.HEDGE_RATE_CEILING},
        })
        with pytest.raises(ValueError, match="hedge_rate"):
            pm.load_model("kelly", root=tmp_path)

    def test_an_unreadable_overlay_falls_back_and_ANNOUNCES_IT(self, tmp_path, capsys):
        """A partially-read overlay would give a desk half a personality and no
        warning. The annotation must START THE LINE — a logger would emit
        "WARNING ::warning …" and GitHub would drop it silently (house law)."""
        d = tmp_path / "config" / "marketing" / "persona_models"
        d.mkdir(parents=True, exist_ok=True)
        (d / "kelly.yml").write_text("beliefs: [unclosed\n  - broken", encoding="utf-8")
        m = pm.load_model("kelly", root=tmp_path)
        assert m.source == "default" and m.beliefs == ()
        out = capsys.readouterr().out
        hit = [ln for ln in out.splitlines() if "persona_model_unreadable" in ln]
        assert hit, out
        assert hit[0].startswith("::"), f"annotation not at column zero: {hit[0]!r}"

    def test_clear_model_cache_actually_drops_the_cache(self, tmp_path):
        """A cache a test cannot drop is a cache that answers for the previous
        test's overlay — the exact one-revision bug the warmth build shipped."""
        _write_overlay(tmp_path, "kelly", {
            "schema": pm.MODEL_SCHEMA, "account": "kelly", "beliefs": ["one"]})
        assert pm.load_model("kelly", root=tmp_path).beliefs == ("one",)
        _write_overlay(tmp_path, "kelly", {
            "schema": pm.MODEL_SCHEMA, "account": "kelly", "beliefs": ["two"]})
        assert pm.load_model("kelly", root=tmp_path).beliefs == ("one",), "cache not warm"
        pm.clear_model_cache()
        assert pm.load_model("kelly", root=tmp_path).beliefs == ("two",)


# ===========================================================================
# The fence, and the promise that `avoid` is advisory
# ===========================================================================
class TestTheFence:
    def test_persona_model_is_not_a_persona_spec_reader(self):
        """The overlay is an ADDITIONAL layer beside `expression_dial`, never a
        replacement for it. Reuses the roster guard's own predicate rather than
        a re-derived one, so a widening of the detector reaches this too."""
        import importlib.util  # noqa: PLC0415

        spec = importlib.util.spec_from_file_location(
            "_personas_guard", ROOT / "tests" / "test_marketing_personas.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for rel in ("engine/marketing/persona_model.py",):
            blob = (ROOT / rel).read_text(encoding="utf-8")
            assert not mod._references_persona_specs(blob), (
                f"{rel} reaches the frozen persona spec layer — the fence "
                "allows exactly the adjudicated readers and this is not one")

    def test_the_avoid_list_has_not_become_a_second_ban_list(self):
        """`lexicon.avoid` is ADVISORY and may never reject a draft.

        Pinned as a REACHABILITY fact rather than a behavioural one, because a
        behavioural test ("a draft with every avoid token still passes") would
        be satisfied by luck the day a word also sits on a frozen ban list. If
        no critic and no dial can see this module, `avoid` cannot reject.

        MUTATION CHECK: add `from engine.marketing import persona_model` to
        reply_critics.py and this goes red.
        """
        for rel in ("engine/marketing/reply_critics.py",
                    "engine/marketing/expression_dial.py"):
            blob = (ROOT / rel).read_text(encoding="utf-8")
            assert "persona_model" not in blob, (
                f"{rel} now reads the persona MODEL overlay. The bans live in "
                "the frozen voice_codex; an advisory preference list that can "
                "reject is a second ban list outside the adjudicated seam.")


# ===========================================================================
# The response mixture
# ===========================================================================
class TestResponseMix:
    def test_every_row_carries_the_six_types_and_sums_to_one(self):
        for account, row in pm.DEFAULT_RESPONSE_MIX.items():
            assert set(row) == set(pm.RESPONSE_TYPES), account
            assert sum(row.values()) == pytest.approx(1.0, abs=1e-9), account

    def test_the_four_employee_mean_is_exactly_the_number_the_spec_states(self):
        """§B.3's falsifiable claim: per-persona variation WITHOUT drifting the
        fleet mix.

        Pinned as the EXACT mean rather than as a tolerance, so any future edit
        to a persona row has to restate what it did to the fleet number instead
        of sliding inside a band.
        """
        for kind, stated in EMPLOYEE_MEAN.items():
            mean = sum(pm.DEFAULT_RESPONSE_MIX[a][kind] for a in EMPLOYEES) / len(EMPLOYEES)
            assert mean == pytest.approx(stated, abs=1e-9), kind

    def test_the_fleet_mean_tracks_the_operators_distribution(self):
        """…and the mean is close to the operator's brief on every bucket.

        THE TOLERANCE IS 0.02, NOT THE 0.015 THE SPEC'S PROSE CLAIMS, and the
        difference is a measured correction rather than a loosening. The spec
        says the employee mean matches 30/25/15/15/10/5 "to within a point and a
        half on every bucket"; five buckets do, and `question` does not — the
        four question weights (0.08 / 0.06 / 0.08 / 0.10) average 0.08 against a
        0.10 target, which is two points. The tables are the frozen cross-lane
        contract and are shipped verbatim; the prose was off by half a point on
        one bucket, and stating that here is cheaper than a table nobody can
        reconcile with its own description.
        """
        worst = max(abs(EMPLOYEE_MEAN[k] - t) for k, t in OPERATOR_TARGET.items())
        assert worst <= 0.02 + 1e-9, f"worst-bucket drift is now {worst:.3f}"
        assert abs(EMPLOYEE_MEAN["question"] - OPERATOR_TARGET["question"]) == \
            pytest.approx(0.02, abs=1e-9), (
            "`question` is the widest bucket at two points; if that stops being "
            "true the tolerance above should tighten with it")

    def test_no_two_employee_desks_share_a_row(self):
        """"Percentages SHOULD VARY BY PERSONA" — four desks cycling one
        distribution in lockstep is the bot-farm signature, not a persona."""
        rows = [tuple(pm.DEFAULT_RESPONSE_MIX[a][k] for k in pm.RESPONSE_TYPES)
                for a in EMPLOYEES]
        assert len(set(rows)) == len(rows)

    def test_the_committed_config_does_not_drift_from_the_code_rows(self, marketing_cfg):
        """The code rows are the source of truth and the config is the operator's
        copy of them. Two tables that can disagree is how a "tuned" mix silently
        becomes whichever one the reader happened to open."""
        cfg_rows = (((marketing_cfg.get("reply_desk") or {})
                     .get("response_mix") or {}).get("accounts") or {})
        assert cfg_rows, "config/marketing.yml carries no reply_desk.response_mix"
        for account, row in cfg_rows.items():
            code = pm.DEFAULT_RESPONSE_MIX.get(account)
            assert code is not None, f"{account} is in config but not in code"
            for kind, weight in row.items():
                assert code[kind] == pytest.approx(float(weight)), (account, kind)

    def test_a_partial_override_layers_onto_the_code_row(self):
        """Tuning one bucket must not silently zero the other five."""
        cfg = {"reply_desk": {"response_mix": {"accounts": {"cici": {"humor": 0.30}}}}}
        mix = pm.response_mix("cici", cfg=cfg)
        assert mix["humor"] > pm.response_mix("cici")["humor"]
        assert all(mix[k] > 0 for k in pm.RESPONSE_TYPES)
        assert sum(mix.values()) == pytest.approx(1.0)

    def test_a_zero_weight_bucket_never_divides_by_zero(self):
        """The flagship's `humor: 0.00` is a real zero (the humor family sits
        above its reply dial), not a placeholder."""
        mix = pm.response_mix("flagship")
        assert mix["humor"] == 0.0
        assert sum(mix.values()) == pytest.approx(1.0)

    def test_an_all_zero_override_falls_back_rather_than_dividing_by_zero(self):
        cfg = {"reply_desk": {"response_mix": {"accounts": {
            "kelly": {k: 0.0 for k in pm.RESPONSE_TYPES}}}}}
        mix = pm.response_mix("kelly", cfg=cfg)
        assert sum(mix.values()) == pytest.approx(1.0)

    def test_an_unknown_response_type_warns_at_line_start(self, capsys):
        cfg = {"reply_desk": {"response_mix": {"accounts": {
            "kelly": {"sarcasm": 0.5}}}}}
        pm.response_mix("kelly", cfg=cfg)
        hit = [ln for ln in capsys.readouterr().out.splitlines()
               if "response_mix_unknown_type" in ln]
        assert hit and hit[0].startswith("::")

    def test_an_unknown_account_gets_the_default_row(self):
        assert pm.response_mix("nobody") == pytest.approx(
            pm.response_mix("_default"))


# ===========================================================================
# The familiarity ladder — pinned PER TIER
# ===========================================================================
def _rel(handle="somequant", *, stage="", touches=1, days_ago=1):
    return {handle: {
        "handle": handle, "topics": ["credit spreads", "capex"], "stage": stage,
        "touches": touches,
        "last_contact": (NOW - timedelta(days=days_ago)).isoformat(),
    }}


class TestFamiliarityLadder:
    @pytest.mark.parametrize("stage,touches,expected", [
        # rung 2 — nothing recorded
        ("", 0, "stranger"),
        # rung 5 — the residual
        ("", 1, "acquainted"),
        ("cold", 2, "acquainted"),
        ("engaged", 2, "acquainted"),      # engaged but under 3 touches
        # rung 4
        ("engaged", 3, "familiar"),
        ("engaged", 7, "familiar"),
        # rung 3 — either leg is sufficient
        ("engaged", 8, "regular"),
        ("reciprocal", 1, "regular"),
    ])
    def test_the_ladder_per_rung(self, stage, touches, expected):
        """Every rung of §E.4, one case each, with a RECENT contact so the
        recency demotion is not silently doing the work."""
        got = pm.familiarity("kelly", "somequant",
                             relations=_rel(stage=stage, touches=touches),
                             now=NOW, root=ROOT)
        assert got == expected, f"stage={stage!r} touches={touches}"

    def test_a_declined_author_is_a_stranger(self):
        """Rung 1, and a SAFETY property rather than a tone choice: someone who
        declined engagement gets our most neutral register regardless of how
        many times we have spoken."""
        rel = _rel(stage="declined", touches=40, days_ago=0)
        assert pm.familiarity("kelly", "somequant", relations=rel,
                              now=NOW, root=ROOT) == "stranger"
        assert pm.is_declined(rel["somequant"]) is True

    def test_a_declined_author_suppresses_EVERY_warmth_move(self):
        """The other half of rung 1, and it needs its own assertion: `stranger`
        still admits three impersonal moves, and a decline admits none."""
        assert pm.tier_policy("stranger")["warmth_moves"] != ()
        assert pm.tier_policy("regular", declined=True)["warmth_moves"] == ()
        assert pm.tier_policy("regular", declined=True)["tone_available"] is False

    def test_a_stale_contact_demotes_exactly_one_tier(self):
        """§E.4 rung 6. A "regular" we have not spoken to in three months is a
        "familiar", and pretending otherwise is the same class of claim as
        inventing the conversation."""
        fresh = _rel(stage="reciprocal", touches=9, days_ago=1)
        stale = _rel(stage="reciprocal", touches=9,
                     days_ago=pm.RECENCY_DEMOTE_DAYS + 1)
        assert pm.familiarity("kelly", "somequant", relations=fresh,
                              now=NOW, root=ROOT) == "regular"
        assert pm.familiarity("kelly", "somequant", relations=stale,
                              now=NOW, root=ROOT) == "familiar"

    def test_an_unparsable_last_contact_demotes_FAIL_CLOSED(self):
        rel = _rel(stage="reciprocal", touches=9)
        rel["somequant"]["last_contact"] = "sometime last spring"
        assert pm.familiarity("kelly", "somequant", relations=rel,
                              now=NOW, root=ROOT) == "familiar"

    def test_an_absent_store_makes_every_handle_a_stranger(self, tmp_path):
        """§E.5, stated rather than discovered: relations.jsonl is written only
        on the M1 approval path and no desk has one, so this layer ships INERT
        and warms as approvals accumulate."""
        assert pm.familiarity("kelly", "anyone", now=NOW, root=tmp_path) == "stranger"
        assert pm.familiarity("kelly", "", now=NOW, root=tmp_path) == "stranger"

    def test_the_handle_is_matched_case_and_at_insensitively(self):
        rel = _rel(handle="somequant", stage="reciprocal", touches=9)
        assert pm.familiarity("kelly", "@SomeQuant", relations=rel,
                              now=NOW, root=ROOT) == "regular"

    def test_the_ladder_only_speaks_the_stores_own_vocabulary(self):
        """A tier derived from a stage `record_relation` would refuse to write
        is a tier that can never occur. Every stage this ladder branches on has
        to be inside the closed set."""
        for stage in ("declined", "reciprocal", "engaged"):
            assert stage in pmem.RELATION_STAGES


class TestTierPolicy:
    def test_every_named_move_is_a_real_warmth_move(self):
        """A policy table naming a move the register does not have is a table
        that narrows nothing."""
        for tier, moves in pm.TIER_WARMTH_MOVES.items():
            for move in moves:
                assert move in rd.WARMTH_MOVES, f"{tier}: {move}"

    def test_the_ladder_is_cumulative_and_pinned_per_tier(self):
        """§E.4's table, tier by tier, so a later edit argues from the row."""
        p = {t: pm.tier_policy(t) for t in pm.FAMILIARITY_TIERS}
        # stranger — impersonal only. Nothing here claims a shared past.
        assert "wry_solidarity" not in p["stranger"]["warmth_moves"]
        assert "specific_credit" not in p["stranger"]["warmth_moves"]
        assert "flat_confession" not in p["stranger"]["warmth_moves"]
        assert "verdict_first" in p["stranger"]["warmth_moves"]
        # acquainted — crediting a detail presumes we read them, not that we
        # know them.
        assert "specific_credit" in p["acquainted"]["warmth_moves"]
        assert "concede_and_hold" in p["acquainted"]["warmth_moves"]
        assert "wry_solidarity" not in p["acquainted"]["warmth_moves"]
        # familiar — a wry aside needs a shared frustration.
        assert "wry_solidarity" in p["familiar"]["warmth_moves"]
        assert "flat_confession" not in p["familiar"]["warmth_moves"]
        # regular — you admit you were wrong to people you know.
        assert "flat_confession" in p["regular"]["warmth_moves"]
        # strictly cumulative up the ladder
        for lo, hi in zip(pm.FAMILIARITY_TIERS, pm.FAMILIARITY_TIERS[1:]):
            assert set(p[lo]["warmth_moves"]) < set(p[hi]["warmth_moves"]), (lo, hi)

    def test_callback_is_unavailable_below_familiar(self):
        """Reaching back to a position we took in front of THIS author is a
        stranger quoting himself when there is no history."""
        assert "callback" in pm.tier_policy("stranger")["blocked_families"]
        assert "callback" in pm.tier_policy("acquainted")["blocked_families"]
        assert pm.tier_policy("familiar")["blocked_families"] == frozenset()
        assert pm.tier_policy("regular")["blocked_families"] == frozenset()

    def test_the_shape_boost_appears_only_where_the_spec_names_it(self):
        assert pm.tier_policy("stranger")["shape_boost"] == {}
        assert pm.tier_policy("acquainted")["shape_boost"] == {}
        assert pm.tier_policy("familiar")["shape_boost"] == {"fragment_exchange": 1.4}
        assert pm.tier_policy("regular")["shape_boost"] == {
            "one_line": 1.4, "fragment_exchange": 1.4}

    def test_quiet_sympathy_survives_every_tier(self):
        """It is `relationship_only` and shape-gated to a personal setback, and
        it is the one reply that is not a growth reply. At M0 every curated
        author is a `stranger` here, so a familiarity gate on it would withhold
        the sympathy line from exactly the person whose bad week earned it."""
        for tier in pm.FAMILIARITY_TIERS:
            assert "quiet_sympathy" in pm.tier_policy(tier)["warmth_moves"]

    def test_an_unknown_tier_falls_to_the_coldest_rung(self):
        assert pm.tier_policy("bff")["tier"] == "stranger"


# ===========================================================================
# The AM-R1 gate on relationship tone
# ===========================================================================
class TestToneAmR1Gate:
    PARENT = "Credit spreads widened again while capex guidance held flat."

    def _row(self, *, days_ago=2, topics=("credit spreads",), stage="reciprocal"):
        return {"handle": "somequant", "topics": list(topics), "stage": stage,
                "touches": 9,
                "last_contact": (NOW - timedelta(days=days_ago)).isoformat()}

    def test_the_happy_path_returns_a_swept_pool(self):
        got = pm.tone_prefixes("kelly", "regular", parent_text=self.PARENT,
                               relations_row=self._row(), now=NOW, root=ROOT)
        assert got, "a recent, topic-matched regular should have a register"
        assert set(got) <= set(pm.load_model("kelly", root=ROOT).tone_pool("regular"))

    @pytest.mark.parametrize("tier", ["stranger", "acquainted"])
    def test_tone_is_unavailable_below_familiar(self, tier):
        assert pm.tone_prefixes("kelly", tier, parent_text=self.PARENT,
                                relations_row=self._row(), now=NOW, root=ROOT) == []

    def test_tone_needs_contact_inside_the_window(self):
        """"you flagged this one already" is a CLAIM ABOUT THE PAST, and an
        unverified claim about a shared history is the same class of
        fabrication as an invented lunch. Fourteen days is what makes "last
        week" mean last week.

        MUTATION CHECK: delete the `TONE_PREFIX_MAX_AGE_DAYS` comparison in
        `tone_prefixes` and this goes green while the desk starts claiming a
        conversation from six months ago.
        """
        stale = self._row(days_ago=pm.TONE_PREFIX_MAX_AGE_DAYS + 1)
        assert pm.tone_prefixes("kelly", "regular", parent_text=self.PARENT,
                                relations_row=stale, now=NOW, root=ROOT) == []
        fresh = self._row(days_ago=pm.TONE_PREFIX_MAX_AGE_DAYS - 1)
        assert pm.tone_prefixes("kelly", "regular", parent_text=self.PARENT,
                                relations_row=fresh, now=NOW, root=ROOT) != []

    def test_tone_needs_a_topic_that_overlaps_THIS_parent(self):
        """"the one you kept pointing at" has to point at something.

        MUTATION CHECK: delete the topic-overlap clause and this goes green
        while a shared-history claim fires on an unrelated post.
        """
        off = self._row(topics=("japanese equities",))
        assert pm.tone_prefixes("kelly", "regular", parent_text=self.PARENT,
                                relations_row=off, now=NOW, root=ROOT) == []

    def test_a_generic_word_is_not_a_topic_overlap(self):
        """A gate that fires because both sides contain "market" is no gate."""
        off = self._row(topics=("the market",))
        assert pm.tone_prefixes("kelly", "regular",
                                parent_text="The market moved today.",
                                relations_row=off, now=NOW, root=ROOT) == []

    def test_a_missing_row_and_a_declined_author_both_fail_closed(self):
        assert pm.tone_prefixes("kelly", "regular", parent_text=self.PARENT,
                                relations_row=None, now=NOW, root=ROOT) == []
        assert pm.tone_prefixes("kelly", "regular", parent_text=self.PARENT,
                                relations_row=self._row(stage="declined"),
                                now=NOW, root=ROOT) == []

    def test_an_unseeded_desk_has_no_tone_however_familiar(self):
        assert pm.tone_prefixes("flagship", "regular", parent_text=self.PARENT,
                                relations_row=self._row(), now=NOW, root=ROOT) == []

    def test_no_tone_pool_carries_lol_or_an_author_name(self):
        """Two copy rules pinned rather than reviewed. `_DIGNITY_TOKENS` already
        carries `lmao` and `lol no`; a bare `lol` is one edit from a contempt
        tell, and the operator's own example survives its removal intact. The
        name rule is `fabrication`'s, and a tone prefix is the one place a
        builder is tempted to break it."""
        probes = ("somequant", "Sarah", "Chen", "asiadesk")
        for account in EMPLOYEES:
            for tier in pm.FAMILIARITY_TIERS:
                for line in pm.load_model(account, root=ROOT).tone_pool(tier):
                    assert not re.search(r"\blol\b", line, re.I), (account, line)
                    assert "@" not in line, (account, line)
                    for probe in probes:
                        assert rd.author_name_hits(line, probe) == [], (account, line)

    def test_every_shipped_tone_line_survives_its_own_personas_guards(self):
        """The same sweep the warmth openers and the doorway tails run — one
        guard, three callers. A line that trips it is not a style choice, it is
        copy the persona's own codex just rejected."""
        for account in EMPLOYEES:
            for tier in ("familiar", "regular"):
                pool = pm.load_model(account, root=ROOT).tone_pool(tier)
                assert pool, f"{account}/{tier} has no tone copy at all"
                for line in pool:
                    assert rd._copy_clears_persona_guards(
                        account, line, f"tone::{tier}::{line}", ROOT), (account, line)


# ===========================================================================
# reply_score — the relationship_stage feature that scored every real row at 0
# ===========================================================================
class TestRelationStageScale:
    def test_every_stage_the_store_can_hold_is_scored(self):
        """THE PIN THAT WOULD HAVE CAUGHT THE ORIGINAL DEFECT.

        `_STAGE_SCALE` was written against a vocabulary that was never built
        (`seen`/`liked`/`replied`/`recurring`), while `record_relation` validates
        against the closed set `{"", cold, engaged, reciprocal, declined}` and
        refuses anything else. So `.get(stage, 0.0)` returned the default for
        every row the store will ever hold and the feature was dead weight at
        any weight — invisible, because 0.0 is also the honest answer for an
        ABSENT store, which is the state the desk is in today.
        """
        missing = sorted(set(pmem.RELATION_STAGES) - set(rs._STAGE_SCALE))
        assert missing == [], (
            f"stages the ledger can hold but the scorer cannot see: {missing}")

    def test_the_two_production_writers_stages_are_both_scored(self):
        """A CENSUS OVER THE CALLERS, not over the table. `reply_export` records
        `engaged` when a send is confirmed and `reply_producer` records
        `reciprocal` when the author answers; those two words are the entire
        live vocabulary and neither was in the table."""
        written: set[str] = set()
        for rel in ("engine/marketing/reply_export.py",
                    "engine/marketing/reply_producer.py"):
            blob = (ROOT / rel).read_text(encoding="utf-8")
            written |= set(re.findall(r'stage=["\']([a-z_]+)["\']', blob))
        assert written, "no production caller writes a relation stage any more"
        for stage in written:
            assert stage in rs._STAGE_SCALE, f"{stage!r} is written but not scored"
            assert stage in pmem.RELATION_STAGES

    def test_an_answered_reply_outranks_a_one_way_send_which_outranks_cold(self):
        assert rs._STAGE_SCALE["reciprocal"] > rs._STAGE_SCALE["engaged"] > rs._STAGE_SCALE["cold"]

    def test_a_decline_is_the_lowest_rung_and_never_negative(self):
        """The ranking prior stays in [0, 1]; the real "do not approach" rule is
        the warmth suppression in `persona_model`, not a number a re-weighting
        could flip."""
        assert rs._STAGE_SCALE["declined"] == 0.0

    def test_the_feature_moves_when_a_real_row_is_present(self):
        """The end-to-end consequence: with a `reciprocal` row the scorer's
        `relationship_stage` component is non-zero. On the old table it was
        0.0 and identical to an absent store."""
        target = {"kind": "author_post", "author": "somequant",
                  "author_tier": "relationship", "text": "credit spreads widened",
                  "created_at": (NOW - timedelta(minutes=10)).strftime(
                      "%Y-%m-%dT%H:%M:%SZ"), "reply_count": 3}
        cold = rs.score_target(target, now=NOW, relations={})
        warm = rs.score_target(target, now=NOW,
                               relations={"somequant": {"stage": "reciprocal"}})
        assert cold["components"]["relationship_stage"] == 0.0
        assert warm["components"]["relationship_stage"] > 0.0
        assert warm["score"] > cold["score"]


# ===========================================================================
# THE PRODUCER WIRING — the pins that go RED against main
# ===========================================================================
PARENT = "Hyperscaler capex keeps climbing but credit spreads are widening."

#: Distinct gifts per tick. With one gift the near-dup critic kills every
#: follow-up draft and the rotation test would measure nothing.
GIFTS = (
    ("IG spreads widened 12.5% this week while capex guidance held.", "12.5%"),
    ("Breadth thinned 7.1% as the equal-weight index lagged.", "7.1%"),
    ("Buyback authorisations fell 9.3% against last quarter.", "9.3%"),
    ("Net issuance climbed 4.8% into the refinancing window.", "4.8%"),
    ("Inventory days stretched 6.2% across the supplier set.", "6.2%"),
    ("Dealer inventory turned 5.5% heavier into the auction.", "5.5%"),
)


class _StubProvider:
    source_tier = "x_reply"
    billed = True

    def __init__(self, targets):
        self._targets = list(targets)

    def fetch(self, *, session_state, offline=False, wire_spend_usd=None,
              accounts=None, now=None):
        return [] if offline else list(self._targets)


def _target(sid: str, *, account: str = "kelly", author: str = "somequant") -> dict:
    return {
        "kind": "author_post", "status_id": sid, "thread_root_id": sid,
        "url": f"https://x.com/{author}/status/{sid}", "author": author,
        "author_tier": "relationship", "beats": ["credit", "capex"],
        "text": PARENT,
        "created_at": (NOW - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reply_count": 3, "like_count": 40, "retweet_count": 4, "view_count": 900,
        "account": account, "mechanism": "credit", "subject": "capex",
    }


@pytest.fixture()
def armed_cfg() -> dict:
    cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
    cfg["reply_desk"]["producer"]["enabled"] = True
    return cfg


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "reply_targets.yml").write_text(
        "accounts:\n"
        "  kelly:\n"
        "    beats: [credit, capex]\n"
        "    authors:\n"
        "      - handle: somequant\n"
        "        tier: relationship\n",
        encoding="utf-8")
    return tmp_path


def _facts_for(gift: str, number: str):
    def _f(_account, _target):
        return {"facts": [{"id": "f", "text": gift, "salience": 1.0,
                           "numbers": [number]}],
                "numbers_whitelist": [number]}
    return _f


def _run_ticks(cfg, repo, store, n: int) -> list[dict]:
    """`n` producer ticks, one target each, a different gift every time."""
    for i in range(n):
        gift, number = GIFTS[i % len(GIFTS)]
        rp.run_producer(
            cfg=cfg, press_cfg={}, root=repo, store=store,
            now=NOW + timedelta(minutes=i), facts_for=_facts_for(gift, number),
            provider=_StubProvider([_target(f"190000000000000{i:04d}")]),
        )
    return rq.read_items(store)


class TestProducerRotationWiring:
    def test_the_queue_item_persists_the_rotation_axes(self, armed_cfg, repo, store=None):
        """RED ON MAIN. `make_item` never wrote `warmth` or `tail`, so the two
        anti-sameness axes the last two builds shipped had nothing to read back
        and reset on every producer run. A rotation axis the producer cannot
        read back is an axis that resets every night."""
        store = repo / "store"
        items = _run_ticks(armed_cfg, repo, store, 2)
        assert items, "the producer enqueued nothing — the wiring test is vacuous"
        for item in items:
            assert "warmth" in item, "queue item carries no warmth"
            assert "tail" in item, "queue item carries no tail"
            assert item.get("familiarity") in pm.FAMILIARITY_TIERS
            # Additive under the unchanged schema: an item carrying these is
            # still valid, and an already-queued item without them still is too.
            assert rq.validate_item(item) == []

    def test_the_second_tick_supplies_a_NON_EMPTY_window(self, armed_cfg, repo,
                                                         monkeypatch):
        """RED ON MAIN, and the load-bearing assertion of this whole block.

        Measured on HEAD: `recent_warmth`, `recent_tails`, `has_thesis` and
        `tier` were `None` on EVERY call the producer ever made, so only the
        stable hash ran live and both LRUs drew from an empty history.

        MUTATION CHECK: drop `recent_warmth=recent_warmth` from the
        `draft_reply` call in `_produce_once` and this goes red.
        """
        store = repo / "store"
        calls: list[dict] = []
        original = rd.draft_reply

        def _spy(**kwargs):
            calls.append({k: kwargs.get(k) for k in
                          ("recent_families", "recent_warmth", "recent_tails",
                           "has_thesis", "tier")})
            return original(**kwargs)

        monkeypatch.setattr(rd, "draft_reply", _spy)
        items = _run_ticks(armed_cfg, repo, store, 3)
        assert len(items) >= 2, "not enough enqueued drafts to prove a read-back"
        assert len(calls) >= 2

        # `tier` and `has_thesis` are threaded on EVERY call, from the first.
        for call in calls:
            assert call["tier"] == "relationship", "queue tier never reached the drafter"
            assert call["has_thesis"] is False, "has_thesis never reached the drafter"
            assert isinstance(call["recent_warmth"], list)
            assert isinstance(call["recent_tails"], list)

        # …and the windows are non-empty once there is history to read.
        assert any(c["recent_warmth"] for c in calls[1:]), (
            "the warmth LRU is still drawing from an empty history")
        assert calls[-1]["recent_warmth"] == [
            str(i["warmth"]) for i in items if i.get("warmth")][:len(calls[-1]["recent_warmth"])], (
            "the window does not match what was actually enqueued")

    def test_the_window_breaks_a_warmth_REPEAT_the_empty_window_allows(
            self, armed_cfg, repo):
        """RED ON MAIN — the behavioural half.

        `rotate_warmth(None, allowed=pool)` returns the first UNSEEN entry, and
        every entry is unseen when the window is empty, so an empty window
        always returns `pool[0]`. Measured on HEAD with the shipped tables that
        collapsed kelly's fourteen-family register onto exactly TWO warmth moves
        (`concede_and_hold` on eight families, `verdict_first` on six).

        This replays each enqueued draft's warmth selection with the EMPTY
        window HEAD supplied and asserts the two sequences differ — i.e. the
        wiring demonstrably suppressed at least one repeat that today's code
        allows.
        """
        store = repo / "store"
        items = _run_ticks(armed_cfg, repo, store, len(GIFTS))
        wired = [i.get("warmth") for i in items]
        assert len(items) >= 3, f"only {len(items)} drafts enqueued — too few to measure"

        shape = rd.classify_parent({"text": PARENT})
        has_detail = bool(rd.extract_detail(PARENT))
        head = [
            rd._select_warmth("kelly", family=str(i.get("family")),
                              parent_shape=shape, root=repo,
                              recent_warmth=None, has_thesis=False,
                              has_detail=has_detail, tier="relationship")
            for i in items
        ]
        assert wired != head, (
            "the supplied window changed nothing: wired="
            f"{wired} empty-window={head}")
        assert len(set(w for w in wired if w)) >= len(set(h for h in head if h)), (
            "the window narrowed the register instead of widening it: "
            f"wired={wired} empty-window={head}")

    def test_two_drafts_in_ONE_tick_advance_the_window(self, armed_cfg, repo):
        """The queue read-back cannot cover an in-tick collision: an item is
        only visible to `_recent_values` on the NEXT tick, so two targets in the
        same tick would read the same pre-tick history."""
        store = repo / "store"

        # A DIFFERENT gift per target, keyed on the status id. With one gift the
        # near-dup critic kills the second draft first and the test would pass
        # while proving nothing about the in-tick window — the same reason
        # `test_one_conversation_one_owner_still_binds` splits its facts.
        def _facts(_account, target):
            idx = 0 if str(target.get("status_id", "")).endswith("901") else 1
            gift, number = GIFTS[idx]
            return {"facts": [{"id": f"f{idx}", "text": gift, "salience": 1.0,
                               "numbers": [number]}],
                    "numbers_whitelist": [number]}

        rp.run_producer(
            cfg=armed_cfg, press_cfg={}, root=repo, store=store, now=NOW,
            facts_for=_facts,
            provider=_StubProvider([_target("1900000000000000901"),
                                    _target("1900000000000000902")]),
        )
        items = rq.read_items(store)
        assert len(items) == 2, (
            "both in-tick drafts must reach the queue or this measures nothing")
        assert len({i.get("warmth") for i in items}) > 1 or \
               len({i.get("tail") for i in items}) > 1, (
            "two drafts in one tick drew the same warmth AND the same doorway")

    def test_the_critic_ctx_carries_the_warmth_context(self, armed_cfg, repo,
                                                       monkeypatch):
        """RED ON MAIN. `persona_label` and the element critic both carry a
        `quiet_sympathy` exemption DOUBLE-gated on `relationship_only` AND
        `warmth`; a ctx supplying neither made it unreachable, and a ctx
        supplying only one would make it a hole."""
        store = repo / "store"
        seen: list[dict] = []
        original = rc.screen

        def _spy(draft, ctx):
            seen.append(dict(ctx))
            return original(draft, ctx)

        monkeypatch.setattr(rc, "screen", _spy)
        _run_ticks(armed_cfg, repo, store, 1)
        assert seen, "no draft reached the critics"
        ctx = seen[0]
        assert "warmth" in ctx
        assert "relationship_only" in ctx and isinstance(ctx["relationship_only"], bool)
        assert ctx.get("familiarity") in pm.FAMILIARITY_TIERS
        assert ctx.get("tier") == "relationship"
        assert ctx.get("tone_prefixes") == [], "M0 has no relation ledger to draw on"

    def test_recent_values_skips_the_absences(self, armed_cfg, repo):
        """`warmth=None` ("no move was admissible") and `tail=""` ("closed on
        nothing") are legal OUTCOMES, not uses. Counting them as recent would
        push a real move out of the window to make room for an absence."""
        store = repo / "store"
        _run_ticks(armed_cfg, repo, store, 3)
        window = rp._recent_warmth(store, "kelly", 20)
        assert all(window), window
        assert rp._recent_tails(store, "kelly", 20) == [
            str(i["tail"]) for i in rq.read_items(store) if i.get("tail")]

    def test_the_wiring_survives_an_unreadable_queue(self, tmp_path):
        """A window we cannot read is an empty window, never an exception: the
        producer must degrade to today's behaviour rather than losing the tick."""
        assert rp._recent_warmth(tmp_path / "nope", "kelly", 20) == []
        assert rp._recent_tails(tmp_path / "nope", "kelly", 20) == []


def test_the_shape_lane_reads_the_response_mix_from_ONE_table():
    """DRIFT ALARM across the lane seam.

    §F.2 declares `reply_shape.DEFAULT_RESPONSE_MIX` and §F.1 has
    `persona_model.response_mix` read it — a cycle if both own a table. The
    resolution is one table here and an alias there. If the shape module exists
    and publishes its own copy, the two must agree; a silent divergence would
    make the measured mix depend on which module the reader opened.
    """
    try:
        from engine.marketing import reply_shape as rsh  # noqa: PLC0415
    except ImportError:
        pytest.skip("reply_shape has not landed in this tree yet")
    table = getattr(rsh, "DEFAULT_RESPONSE_MIX", None)
    if table is None:
        pytest.skip("reply_shape publishes no response mix table")
    for account, row in pm.DEFAULT_RESPONSE_MIX.items():
        assert account in table, f"{account} missing from reply_shape's copy"
        for kind, weight in row.items():
            assert table[account][kind] == pytest.approx(weight), (account, kind)
