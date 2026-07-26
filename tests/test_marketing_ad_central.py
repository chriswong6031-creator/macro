"""tests/test_marketing_ad_central.py — the Ad Central spine.

Every acceptance gate in `research/AD_CENTRAL_MASTERPLAN.md` §0 that CAN be
executed IS executed here.  Deleting one of these tests is deleting the gate it
enforces, so each is named for its gate:

    G-A  money never moves without three independent arms
    G-B  denominators are assignment-time
    G-C  the null is the control, and it is printed
    G-D  n-floor before any verdict
    G-E  the primary metric is frozen at arena creation
    G-F  every claim carries a passport
    G-G  determinism — no RNG in the spine
    G-H  budget conservation

Monte Carlo appears in this file only as an *oracle* for the quadrature, seeded
so the suite stays deterministic.  The engine itself draws nothing.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from engine.marketing import (
    ad_allocator,
    ad_arena,
    ad_central,
    ad_creative,
    ad_matrix,
    ad_stats,
)
from engine.marketing.ad_stats import Arm


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()


# ═══════════════════════════════════════════════════════════════════════════
# ad_creative
# ═══════════════════════════════════════════════════════════════════════════

def _creative(**kw):
    base = dict(
        opportunity_id="opp-1", format_id="reddit_promoted",
        angle="Rates moved and most dashboards still show yesterday.",
        hook="The 20bp yield spike already re-ranked the sectors",
        proof="Every call carries its evidence and its invalidation.",
        cta="See what changed",
    )
    base.update(kw)
    return ad_creative.build(**base)


def test_creative_id_is_deterministic_G_G():
    a = _creative()
    b = _creative()
    assert a.creative_id == b.creative_id
    assert a.as_dict() == b.as_dict()
    # A changed dimension is a different creative.
    assert _creative(hook="Something else entirely").creative_id != a.creative_id


def test_creative_refuses_over_limit_rather_than_truncating():
    """A headline that does not fit is not a shorter headline — it is a different claim."""
    c = _creative(format_id="google_search")   # headline_max=30
    assert c.status == "refused"
    assert any(r.startswith("headline_over_limit") for r in c.refusals)
    # The copy survives on the refused object so the console can show what was rejected.
    assert c.headline == "The 20bp yield spike already re-ranked the sectors"


def test_creative_fits_within_limits_when_short_enough():
    c = _creative(format_id="google_search", angle="Sectors re-ranked.",
                  hook="Yields spiked 20bp", proof="Evidence on every call.", cta="")
    assert c.status == "draft", c.refusals
    assert len(c.headline) <= ad_creative.FORMATS["google_search"].headline_max
    assert len(c.body) <= ad_creative.FORMATS["google_search"].body_max


def test_creative_requires_a_claim_passport_G_F():
    """A factual/directional/causal claim without a passport is refused at BUILD time."""
    for claim_type in ("factual", "directional", "causal"):
        c = _creative(claim_type=claim_type)
        assert c.status == "refused"
        assert f"missing_claim_passport:{claim_type}" in c.refusals
        # With a passport it builds.
        ok = _creative(claim_type=claim_type, claim_passport_id="clm-001")
        assert ok.status == "draft", ok.refusals
    # A pure positioning line asserts nothing checkable and needs no passport.
    assert _creative(claim_type="promotional").status == "draft"


def test_creative_refuses_ci_forbidden_vocabulary():
    c = _creative(proof="Our signals are validated by 10 years of history.")
    assert c.status == "refused"
    assert "forbidden_copy:validated" in c.refusals


def test_creative_refuses_missing_media_where_the_placement_needs_it():
    c = _creative(format_id="meta_feed", angle="Sectors re-ranked.",
                  hook="Yields spiked 20bp", proof="Evidence included.", cta="See more")
    assert "media_required_on:meta_feed" in c.refusals
    ok = _creative(format_id="meta_feed", angle="Sectors re-ranked.",
                   hook="Yields spiked 20bp", proof="Evidence included.",
                   cta="See more", media_ref="card-1.png")
    assert ok.status == "draft", ok.refusals


def test_creative_destination_carries_the_creative_id_as_utm_content():
    """This is the whole attribution join — `attribution.py` keys on utm_content."""
    from engine.marketing.links import is_tagged_canonical
    c = _creative(base_url="https://mastermind-x.com/")
    assert is_tagged_canonical(c.destination, base_url="https://mastermind-x.com/")
    assert f"utm_content={c.creative_id}" in c.destination


def test_creative_unknown_format_is_refused_not_crashed():
    c = _creative(format_id="tiktok_dance")
    assert c.status == "refused"
    assert c.refusals == ["unknown_format:tiktok_dance"]


# ═══════════════════════════════════════════════════════════════════════════
# ad_matrix
# ═══════════════════════════════════════════════════════════════════════════

_ANGLES = ["Rates moved and your dashboard lagged.",
           "Most screeners tell you what happened, never what it means.",
           "Positioning shifted before the headline printed."]
_HOOKS = ["The 20bp yield spike re-ranked every sector",
          "Three sectors flipped while you were in a meeting",
          "Yesterday's leaders are today's laggards"]
_PROOFS = ["Every conclusion ships with its evidence and its invalidation.",
           "Timestamped calls, graded afterwards, kept on the record.",
           "Cross-asset context, not a single-ticker guess."]
_CTAS = ["See what changed", "Read the breakdown"]


def _fan(**kw):
    base = dict(
        opportunity_id="opp-1", formats=["reddit_promoted"],
        angles=_ANGLES, hooks=_HOOKS, proofs=_PROOFS, ctas=_CTAS,
    )
    base.update(kw)
    return ad_matrix.fan_out(**base)


def test_matrix_is_deterministic_G_G():
    assert _fan().as_dict() == _fan().as_dict()


def test_matrix_keeps_only_distinct_creatives():
    m = _fan()
    assert len(m.creatives) > 1
    assert m.distinctness["flags"] == 0, m.distinctness["flagged_pairs"]
    assert m.distinctness["max_similarity"] <= ad_matrix.DEFAULT_JACCARD_CEILING


def test_matrix_drops_near_duplicates_and_says_so():
    """Two near-identical hooks must not both be bought."""
    m = _fan(hooks=["The 20bp yield spike re-ranked every sector",
                    "The 20bp yield spike re-ranked every sector today"],
             angles=_ANGLES[:1], proofs=_PROOFS[:1], ctas=_CTAS[:1])
    assert m.counts["dropped_near_dup"] >= 1
    assert any(d["cause"] == "near_dup" for d in m.dropped)


def test_matrix_cap_still_varies_every_axis():
    """A raw itertools.product order would spend the whole cap on angle #1."""
    m = _fan(max_creatives=6)
    assert len(m.creatives) <= 6
    for axis in ("angle", "hook", "proof"):
        assert m.coverage[axis]["levels_surviving"] > 1, (
            f"cap collapsed {axis} to one level — the test cannot learn about it"
        )


def test_matrix_reports_refusals_rather_than_silently_shrinking():
    m = _fan(formats=["google_search"])       # every hook here is over 30 chars
    assert m.counts["kept"] == 0
    assert m.counts["dropped_refused"] > 0
    assert all(d["cause"] == "refused" for d in m.dropped)


def test_matrix_spreads_a_cap_across_placements():
    m = _fan(formats=["reddit_promoted", "x_promoted"], max_creatives=6,
             media_ref="card.png")
    assert m.coverage["formats"]["surviving"] == 2


def test_matrix_passport_rides_the_level_that_asserts():
    m = _fan(proofs=[{"level_id": "P0", "text": "Sector rotation followed the spike.",
                      "claim_type": "directional", "claim_passport_id": "clm-77"}],
             angles=_ANGLES[:1], hooks=_HOOKS[:1], ctas=_CTAS[:1])
    assert len(m.creatives) == 1
    assert m.creatives[0].claim_passport_id == "clm-77"
    assert m.creatives[0].claim_type == "directional"


def test_matrix_refuses_a_directional_level_with_no_passport_G_F():
    m = _fan(proofs=[{"level_id": "P0", "text": "Sector rotation followed the spike.",
                      "claim_type": "directional"}],
             angles=_ANGLES[:1], hooks=_HOOKS[:1], ctas=_CTAS[:1])
    assert m.counts["kept"] == 0
    assert any("missing_claim_passport" in d for row in m.dropped for d in row["detail"])


# ═══════════════════════════════════════════════════════════════════════════
# ad_stats — the maths
# ═══════════════════════════════════════════════════════════════════════════

def test_beta_cdf_matches_closed_form():
    # Beta(2,3) CDF at 0.5 is exactly 11/16.
    assert ad_stats.beta_cdf(0.5, 2, 3) == pytest.approx(0.6875, abs=1e-10)
    # Beta(1,1) is uniform.
    assert ad_stats.beta_cdf(0.3, 1, 1) == pytest.approx(0.3, abs=1e-10)
    assert ad_stats.beta_cdf(0.0, 3, 4) == 0.0
    assert ad_stats.beta_cdf(1.0, 3, 4) == 1.0


def test_beta_ppf_inverts_the_cdf():
    assert ad_stats.beta_ppf(0.5, 5, 5) == pytest.approx(0.5, abs=1e-9)
    for q in (0.05, 0.25, 0.75, 0.95):
        x = ad_stats.beta_ppf(q, 3, 7)
        assert ad_stats.beta_cdf(x, 3, 7) == pytest.approx(q, abs=1e-9)


def test_prob_best_is_a_probability_vector():
    pb = ad_stats.prob_best([(11, 91), (11, 91), (11, 91)])
    assert sum(pb) == pytest.approx(1.0, abs=1e-9)
    assert all(p == pytest.approx(1 / 3, abs=1e-6) for p in pb)
    # A dominant arm takes nearly all of it.
    pb2 = ad_stats.prob_best([(200, 800), (20, 980)])
    assert pb2[0] > 0.999


def test_prob_greater_is_symmetric_at_a_tie():
    assert ad_stats.prob_greater(5, 5, 5, 5) == pytest.approx(0.5, abs=1e-6)


def test_quadrature_matches_a_seeded_monte_carlo_oracle():
    """The convolution must agree with sampling — MC lives here, never in the engine."""
    a1, b1, a2, b2 = 31, 471, 21, 481
    lo, hi = ad_stats.difference_interval(a1, b1, a2, b2, level=0.90)
    rng = random.Random(20260726)
    draws = sorted(rng.betavariate(a1, b1) - rng.betavariate(a2, b2) for _ in range(200_000))
    mc_lo = draws[int(0.05 * len(draws))]
    mc_hi = draws[int(0.95 * len(draws))]
    assert lo == pytest.approx(mc_lo, abs=2e-3)
    assert hi == pytest.approx(mc_hi, abs=2e-3)

    pg = ad_stats.prob_greater(a1, b1, a2, b2)
    mc_pg = sum(1 for _ in range(100_000)
                if rng.betavariate(a1, b1) > rng.betavariate(a2, b2)) / 100_000
    assert pg == pytest.approx(mc_pg, abs=1e-2)


def test_analysis_is_deterministic_G_G():
    arms = [Arm("control", assigned=800, converted=32, is_control=True),
            Arm("v1", assigned=800, converted=55)]
    a = ad_stats.analyze(arms, primary_metric="signup_rate").as_dict()
    b = ad_stats.analyze(arms, primary_metric="signup_rate").as_dict()
    assert a == b


# ═══════════════════════════════════════════════════════════════════════════
# ad_stats — the laws
# ═══════════════════════════════════════════════════════════════════════════

def test_below_the_n_floor_no_arm_is_declared_G_D():
    arms = [Arm("control", assigned=40, converted=1, is_control=True),
            Arm("v1", assigned=40, converted=9)]      # a huge apparent lift
    r = ad_stats.analyze(arms, primary_metric="signup_rate", n_floor=100)
    assert r.verdict == "seeding"
    assert r.winner_arm_id is None
    assert "40" in r.plain and "100" in r.plain      # says how far it has to go


def test_a_true_null_is_a_printed_verdict_not_an_empty_panel_G_C():
    arms = [Arm("control", assigned=500, converted=25, is_control=True),
            Arm("v1", assigned=500, converted=28)]
    r = ad_stats.analyze(arms, primary_metric="signup_rate", n_floor=100)
    assert r.verdict == "null"
    assert r.winner_arm_id is None
    assert r.plain.strip()
    assert "real null" in r.plain            # distinguishes "no effect" from "no data"
    assert r.control_arm_id == "control"     # the null IS the control, not 0.5


def test_the_comparison_is_against_the_control_not_one_half_G_C():
    """A 40% vs 41% test must read as a null, even though both are miles from 0.5."""
    arms = [Arm("control", assigned=4000, converted=1600, is_control=True),
            Arm("v1", assigned=4000, converted=1640)]
    r = ad_stats.analyze(arms, primary_metric="signup_rate", n_floor=100)
    assert r.verdict in ("null", "equivalent")
    assert r.winner_arm_id is None
    v1 = next(a for a in r.arms if a.arm_id == "v1")
    assert v1.diff_pp == pytest.approx(1.0, abs=0.2)      # vs control, in points


def test_a_real_winner_separates():
    arms = [Arm("control", assigned=2000, converted=80, is_control=True),
            Arm("v1", assigned=2000, converted=140)]
    r = ad_stats.analyze(arms, primary_metric="signup_rate", n_floor=100)
    assert r.verdict == "separated"
    assert r.winner_arm_id == "v1"
    v1 = next(a for a in r.arms if a.arm_id == "v1")
    assert v1.diff_pp_low > 0            # the interval excludes zero
    assert v1.prob_best >= 0.95


def test_equivalence_is_a_finding_not_a_shortfall():
    arms = [Arm("control", assigned=200_000, converted=10_000, is_control=True),
            Arm("v1", assigned=200_000, converted=10_050)]
    r = ad_stats.analyze(arms, primary_metric="signup_rate", n_floor=100)
    assert r.verdict == "equivalent"
    assert r.winner_arm_id is None
    assert "worth chasing" in r.plain
    assert "too small to matter" in r.plain


def test_a_losing_variant_never_becomes_the_winner():
    arms = [Arm("control", assigned=3000, converted=180, is_control=True),
            Arm("v1", assigned=3000, converted=100)]
    r = ad_stats.analyze(arms, primary_metric="signup_rate", n_floor=100)
    assert r.winner_arm_id is None
    assert r.verdict == "null"


def test_posterior_mean_and_raw_ratio_are_both_reported():
    """The reader must be able to see the prior's pull, not just its effect."""
    arms = [Arm("control", assigned=100, converted=0, is_control=True),
            Arm("v1", assigned=100, converted=10)]
    r = ad_stats.analyze(arms, primary_metric="signup_rate", n_floor=100)
    control = next(a for a in r.arms if a.arm_id == "control")
    assert control.observed_rate == 0.0
    assert control.rate > 0.0                    # Beta(1,1) never asserts impossibility
    assert r.prior == {"alpha": 1.0, "beta": 1.0}


def test_conversions_cannot_exceed_assignments():
    arm = Arm("x", assigned=10, converted=999)
    a, b = arm.posterior(1.0, 1.0)
    assert a == 11.0 and b == 1.0                # clamped, not negative-beta


def test_a_stop_decision_on_a_secondary_metric_is_refused_G_E():
    arms = [Arm("control", assigned=2000, converted=80, is_control=True),
            Arm("v1", assigned=2000, converted=140)]
    r = ad_stats.analyze(arms, primary_metric="click_rate")     # NOT the frozen metric
    with pytest.raises(ad_stats.FrozenMetricViolation):
        ad_stats.decide(r, frozen_primary_metric="signup_rate")
    # On the frozen metric it decides normally.
    r2 = ad_stats.analyze(arms, primary_metric="signup_rate")
    assert ad_stats.decide(r2, frozen_primary_metric="signup_rate")["stop"] is True


# ═══════════════════════════════════════════════════════════════════════════
# ad_arena
# ═══════════════════════════════════════════════════════════════════════════

def _arena(**kw):
    base = dict(
        arena_id="arena-1", hypothesis="Does the proof line beat the promise line?",
        plane="owned", unit="visitor", primary_metric="signup_rate",
        creative_ids=["adc-aaa", "adc-bbb", "adc-ccc"],
        control_creative_id="adc-aaa",
    )
    base.update(kw)
    return ad_arena.create(**base)


def test_assignment_is_stable_and_stateless_G_G():
    a = _arena()
    for unit in ("v-1", "v-2", "v-99"):
        assert ad_arena.assign(a, unit) == ad_arena.assign(a, unit)
    # A different arena reshuffles the same visitor — tests do not correlate.
    b = _arena(arena_id="arena-2")
    reassigned = sum(1 for i in range(300) if ad_arena.assign(a, f"v-{i}") != ad_arena.assign(b, f"v-{i}"))
    assert reassigned > 100


def test_assignment_is_roughly_balanced():
    a = _arena()
    counts: dict[str, int] = {}
    for i in range(6000):
        counts[ad_arena.assign(a, f"v-{i}")] = counts.get(ad_arena.assign(a, f"v-{i}"), 0) + 1
    assert set(counts) == set(a.arm_creative_ids)
    for cid, n in counts.items():
        assert 1700 < n < 2300, f"{cid} got {n} of 6000"


def test_holdout_is_independent_of_the_arm_draw():
    """Without the per-purpose salt, held-out units would all come from one arm's band."""
    a = _arena(holdout=0.2)
    held = [f"v-{i}" for i in range(4000) if ad_arena.assign(a, f"v-{i}") == ad_arena.HOLDOUT]
    assert 650 < len(held) < 950               # ~20%
    # What those units WOULD have seen is spread across every arm.
    no_holdout = _arena(holdout=0.0)
    would_see = {ad_arena.assign(no_holdout, u) for u in held}
    assert would_see == set(a.arm_creative_ids)


def test_frozen_weights_survive_a_budget_shift_G_G():
    """The allocator moves money, never assignment — a visitor must not flip arms."""
    a = _arena()
    before = {f"v-{i}": ad_arena.assign(a, f"v-{i}") for i in range(200)}
    a.envelope_usd = 500.0                     # a budget change, mid-flight
    after = {f"v-{i}": ad_arena.assign(a, f"v-{i}") for i in range(200)}
    assert before == after


# ── tally: where G-B lives ─────────────────────────────────────────────────

def _rows(arena_id, pairs):
    return [{"arena_id": arena_id, "unit_key": u, "creative_id": c} for u, c in pairs]


def test_denominator_is_assignments_not_survivors_G_B():
    """The losing arm bleeds units before converting; the verdict must not flip.

    A join written against the outcome table would compute arm B as 40/500 = 8%
    and crown it over arm A's 5%. The intention-to-treat denominator is 1000 for
    both, so B is 4% and correctly loses.
    """
    a = _arena(creative_ids=["A", "B"], control_creative_id="A")
    assignments = _rows("arena-1", [(f"a{i}", "A") for i in range(1000)]
                        + [(f"b{i}", "B") for i in range(1000)])
    outcomes = ([{"arena_id": "arena-1", "unit_key": f"a{i}", "metric": "signup_rate",
                  "value": 1.0} for i in range(50)]
                + [{"arena_id": "arena-1", "unit_key": f"b{i}", "metric": "signup_rate",
                    "value": 1.0} for i in range(40)])
    t = ad_arena.tally(a, assignments, outcomes)
    by_id = {arm.arm_id: arm for arm in t.arms}
    assert by_id["A"].assigned == 1000 and by_id["A"].converted == 50
    assert by_id["B"].assigned == 1000 and by_id["B"].converted == 40

    r = ad_arena.readout(a, t)
    assert r["winner_arm_id"] != "B"
    # And the survivor-conditioned number that would have crowned B is 8%.
    assert 40 / 500 > 50 / 1000


def test_an_outcome_without_an_assignment_is_an_anomaly_not_a_conversion_G_B():
    a = _arena(creative_ids=["A", "B"], control_creative_id="A")
    assignments = _rows("arena-1", [(f"a{i}", "A") for i in range(100)]
                        + [(f"b{i}", "B") for i in range(100)])
    outcomes = [{"arena_id": "arena-1", "unit_key": "ghost-1", "metric": "signup_rate"},
                {"arena_id": "arena-1", "unit_key": "ghost-2", "metric": "signup_rate"},
                {"arena_id": "arena-1", "unit_key": "a0", "metric": "signup_rate"}]
    t = ad_arena.tally(a, assignments, outcomes)
    assert sum(arm.converted for arm in t.arms) == 1
    assert t.anomalies["outcome_without_assignment"] == 2


def test_one_unit_converting_twice_counts_once():
    a = _arena(creative_ids=["A"], control_creative_id="A")
    assignments = _rows("arena-1", [("u1", "A"), ("u2", "A")])
    outcomes = [{"arena_id": "arena-1", "unit_key": "u1", "metric": "signup_rate"}] * 9
    t = ad_arena.tally(a, assignments, outcomes)
    assert t.arms[0].assigned == 2 and t.arms[0].converted == 1


def test_outcomes_on_another_metric_do_not_count():
    a = _arena(creative_ids=["A"], control_creative_id="A")
    assignments = _rows("arena-1", [("u1", "A")])
    outcomes = [{"arena_id": "arena-1", "unit_key": "u1", "metric": "click_rate"}]
    t = ad_arena.tally(a, assignments, outcomes)
    assert t.arms[0].converted == 0
    assert t.anomalies["outcome_other_metric"] == 1


def test_rows_from_another_arena_are_ignored():
    a = _arena(creative_ids=["A"], control_creative_id="A")
    assignments = (_rows("arena-1", [("u1", "A")]) + _rows("arena-OTHER", [("u2", "A")]))
    outcomes = [{"arena_id": "arena-OTHER", "unit_key": "u2", "metric": "signup_rate"}]
    t = ad_arena.tally(a, assignments, outcomes)
    assert t.arms[0].assigned == 1 and t.arms[0].converted == 0


def test_a_conflicting_reassignment_keeps_the_first_and_flags_it():
    a = _arena(creative_ids=["A", "B"], control_creative_id="A")
    assignments = _rows("arena-1", [("u1", "A"), ("u1", "B")])
    t = ad_arena.tally(a, assignments, [])
    by_id = {arm.arm_id: arm for arm in t.arms}
    assert by_id["A"].assigned == 1 and by_id["B"].assigned == 0
    assert t.anomalies["conflicting_assignment"] == 1


def test_holdout_is_tallied_separately_from_the_arms():
    a = _arena(creative_ids=["A"], control_creative_id="A", holdout=0.5)
    assignments = _rows("arena-1", [("u1", "A"), ("u2", ad_arena.HOLDOUT)])
    outcomes = [{"arena_id": "arena-1", "unit_key": "u2", "metric": "signup_rate"}]
    t = ad_arena.tally(a, assignments, outcomes)
    assert t.arms[0].assigned == 1 and t.arms[0].converted == 0
    assert t.holdout_assigned == 1 and t.holdout_converted == 1


def test_creatives_ledger_roundtrip(tmp_path):
    m = _fan(max_creatives=3)
    assert ad_arena.save_creatives(m.creatives, root=tmp_path) == len(m.creatives)
    loaded = ad_arena.load_creatives(root=tmp_path)
    assert set(loaded) == {c.creative_id for c in m.creatives}
    assert loaded[m.creatives[0].creative_id]["headline"] == m.creatives[0].headline
    # Re-saving the same creative is harmless — ids are stable, latest row wins.
    ad_arena.save_creatives(m.creatives, root=tmp_path)
    assert len(ad_arena.load_creatives(root=tmp_path)) == len(m.creatives)


def test_a_verdict_names_the_ad_not_its_id(tmp_path):
    """`adc-d50a1a888439 is ahead by 3pp` tells an operator nothing."""
    arms = [Arm("A", creative_id="A", assigned=2000, converted=80, is_control=True,
                label="Know what changed and why it matters"),
            Arm("B", creative_id="B", assigned=2000, converted=140,
                label="Every call shows its evidence")]
    r = ad_stats.analyze(arms, primary_metric="signup_rate", n_floor=100)
    assert r.verdict == "separated"
    assert "Every call shows its evidence" in r.plain
    assert "adc-" not in r.plain
    # Without a label it falls back to the id rather than printing nothing.
    bare = [Arm("A", assigned=2000, converted=80, is_control=True),
            Arm("B", assigned=2000, converted=140)]
    assert "B" in ad_stats.analyze(bare, primary_metric="signup_rate").plain


def test_tally_picks_up_stored_headlines_automatically(tmp_path):
    m = _fan(max_creatives=2)
    ad_arena.save_creatives(m.creatives, root=tmp_path)
    ids = [c.creative_id for c in m.creatives]
    arena = _arena(creative_ids=ids, control_creative_id=ids[0])
    ad_arena.record_assignment(arena.arena_id, "u1", ids[0], root=tmp_path)
    t = ad_arena.tally_from_ledgers(arena, root=tmp_path)
    assert t.arms[0].label == m.creatives[0].headline
    assert t.arms[0].name == m.creatives[0].headline


def test_guardrail_breach_halts_and_a_healthy_metric_does_not():
    a = _arena(guardrails={"refund_rate": 0.10, "unsubscribe_rate": 0.02})
    assert ad_arena.check_guardrails(a, {"refund_rate": 0.04}) == []
    breaches = ad_arena.check_guardrails(a, {"refund_rate": 0.18, "unsubscribe_rate": 0.01})
    assert len(breaches) == 1
    assert breaches[0]["guardrail"] == "refund_rate"
    assert breaches[0]["action"] == "halt"


def test_ledger_roundtrip(tmp_path):
    a = _arena()
    assert ad_arena.save_arena(a, root=tmp_path)
    assert ad_arena.record_assignment("arena-1", "u1", "adc-aaa", root=tmp_path)
    assert ad_arena.record_outcome("arena-1", "u1", "signup_rate", root=tmp_path)

    loaded = ad_arena.load_arenas(root=tmp_path)
    assert len(loaded) == 1 and loaded[0].arena_id == "arena-1"
    assert loaded[0].primary_metric == "signup_rate"

    t = ad_arena.tally_from_ledgers(loaded[0], root=tmp_path)
    by_id = {arm.arm_id: arm for arm in t.arms}
    assert by_id["adc-aaa"].assigned == 1 and by_id["adc-aaa"].converted == 1


def test_the_latest_arena_row_wins(tmp_path):
    ad_arena.save_arena(_arena(), root=tmp_path)
    running = _arena()
    running.status = "running"
    ad_arena.save_arena(running, root=tmp_path)
    loaded = ad_arena.load_arenas(root=tmp_path)
    assert len(loaded) == 1 and loaded[0].status == "running"


def test_a_malformed_ledger_line_does_not_blank_the_panel(tmp_path):
    ad_arena.save_arena(_arena(), root=tmp_path)
    path = tmp_path / ad_arena.DEFAULT_LEDGER_DIR / ad_arena.ARENAS_FILE
    with path.open("a", encoding="utf-8") as f:
        f.write("{not json at all\n")
        f.write(json.dumps({"hypothesis": "no arena_id here"}) + "\n")
    assert len(ad_arena.load_arenas(root=tmp_path)) == 1


# ═══════════════════════════════════════════════════════════════════════════
# ad_allocator
# ═══════════════════════════════════════════════════════════════════════════

def _armed(**kw):
    base = dict(daily_envelope_usd=60.0, paid_enabled=True, operator_armed=True)
    base.update(kw)
    return ad_allocator.AllocatorConfig(**base)


_MATURE = [Arm("control", assigned=800, converted=32, is_control=True),
           Arm("v1", assigned=800, converted=55),
           Arm("v2", assigned=800, converted=40)]


def test_every_arm_of_the_triple_gate_blocks_spend_on_its_own_G_A():
    for off, expect in (
        ({"paid_enabled": False}, "paid_enabled_false"),
        ({"daily_envelope_usd": 0.0}, "envelope_zero"),
        ({"operator_armed": False}, "operator_not_armed"),
    ):
        plan = ad_allocator.allocate(_MATURE, _armed(**off))
        assert plan.dry_run is True
        assert expect in plan.blocked_by
    # All three on ⇒ and only then ⇒ it is live.
    assert ad_allocator.allocate(_MATURE, _armed()).dry_run is False


def test_a_dry_run_still_produces_the_plan_it_would_have_executed():
    live = ad_allocator.allocate(_MATURE, _armed())
    dry = ad_allocator.allocate(_MATURE, _armed(paid_enabled=False))
    assert dry.dry_run and not live.dry_run
    assert [a.amount_usd for a in dry.allocations] == [a.amount_usd for a in live.allocations]


def test_allocation_is_deterministic_G_G():
    a = ad_allocator.allocate(_MATURE, _armed()).as_dict()
    b = ad_allocator.allocate(_MATURE, _armed()).as_dict()
    assert a == b


def test_budget_conservation_holds_across_many_shapes_G_H():
    """Invariant over randomised posteriors — the seed is in the TEST, not the engine."""
    rng = random.Random(20260726)
    for _ in range(120):
        k = rng.randint(2, 9)
        arms = [Arm(f"a{i}", assigned=rng.randint(0, 3000),
                    converted=rng.randint(0, 200), is_control=(i == 0))
                for i in range(k)]
        for arm in arms:
            arm.converted = min(arm.converted, arm.assigned)
        cfg = _armed(
            daily_envelope_usd=rng.choice([5.0, 20.0, 60.0, 250.0]),
            per_arm_daily_cap_usd=rng.choice([5.0, 20.0, 100.0]),
            min_daily_usd=rng.choice([0.0, 1.0, 5.0]),
        )
        plan = ad_allocator.allocate(arms, cfg)
        total = sum(a.amount_usd for a in plan.allocations)
        assert total <= cfg.daily_envelope_usd + 1e-9, "envelope breached"
        assert plan.allocated_usd == pytest.approx(total, abs=0.011)
        assert plan.unallocated_usd >= -1e-9
        for a in plan.allocations:
            assert a.amount_usd <= cfg.per_arm_daily_cap_usd + 1e-9, "per-arm cap breached"
            if a.amount_usd > 0:
                assert a.amount_usd >= cfg.min_daily_usd - 1e-9, "funded below platform minimum"


def test_an_arm_below_the_n_floor_keeps_an_exploration_share():
    """Winner-take-all on a young arm is how a bandit locks onto noise."""
    arms = [Arm("control", assigned=3000, converted=150, is_control=True),
            Arm("v1", assigned=3000, converted=290),
            Arm("newcomer", assigned=12, converted=0)]
    plan = ad_allocator.allocate(arms, _armed(per_arm_daily_cap_usd=100.0))
    newcomer = next(a for a in plan.allocations if a.arm_id == "newcomer")
    assert newcomer.amount_usd > 0, "a young arm was starved before it could defend itself"
    assert newcomer.status != "retired"


def test_a_young_arm_is_never_killed_for_a_bad_start():
    arms = [Arm("control", assigned=3000, converted=300, is_control=True),
            Arm("unlucky", assigned=30, converted=0)]
    assert ad_allocator.kill_candidates(arms, _armed()) == {}


def test_a_mature_loser_is_retired_and_the_control_never_is():
    arms = [Arm("control", assigned=3000, converted=300, is_control=True),
            Arm("loser", assigned=3000, converted=30)]
    killed = ad_allocator.kill_candidates(arms, _armed())
    assert "loser" in killed and "control" not in killed
    plan = ad_allocator.allocate(arms, _armed())
    assert plan.retired == ["loser"]
    assert next(a for a in plan.allocations if a.arm_id == "loser").amount_usd == 0.0


def test_the_better_arm_gets_the_bigger_budget():
    """Budget follows P(best). No platform minimum here, so every arm keeps a share."""
    plan = ad_allocator.allocate(
        _MATURE, _armed(per_arm_daily_cap_usd=100.0, min_daily_usd=0.0))
    amounts = {a.arm_id: a.amount_usd for a in plan.allocations}
    assert amounts["v1"] > amounts["v2"] > amounts["control"]
    # Probability matching, not proportional-to-rate: a 6.9% arm against a 5.0% arm
    # at n=800 takes far more than 6.9/5.0 of the money, because the question the
    # budget answers is "which is best", not "which converts faster".
    assert amounts["v1"] / max(amounts["v2"], 1e-9) > 3.0


def test_a_platform_minimum_concentrates_rather_than_dusting_the_field():
    """The same standings on a real platform floor: fund the leader, pause the dust.

    v2 would draw $3.37 and the control $0.25 of a $60 day. Both are below the $5
    floor, and an ad funded below the floor does not run — so they are paused with
    a reason rather than "funded" at a level that buys nothing.
    """
    plan = ad_allocator.allocate(_MATURE, _armed(per_arm_daily_cap_usd=100.0,
                                                 min_daily_usd=5.0))
    funded = [a for a in plan.allocations if a.amount_usd > 0]
    assert [a.arm_id for a in funded] == ["v1"]
    paused = {a.arm_id: a for a in plan.allocations if a.amount_usd == 0}
    assert set(paused) == {"v2", "control"}
    for a in paused.values():
        assert a.status == "paused_below_minimum"
        assert "minimum" in a.reason
    # Paused is not retired — neither arm has been ruled out, only defunded today.
    assert plan.retired == []


def test_a_thin_envelope_pauses_arms_instead_of_dusting_them():
    arms = [Arm("control", assigned=300, converted=12, is_control=True)] + [
        Arm(f"v{i}", assigned=300, converted=10 + i) for i in range(1, 12)]
    plan = ad_allocator.allocate(arms, _armed(daily_envelope_usd=20.0, min_daily_usd=5.0))
    funded = [a for a in plan.allocations if a.amount_usd > 0]
    assert funded, "a $20 envelope should still fund the leaders"
    assert all(a.amount_usd >= 5.0 for a in funded)
    assert any(a.status == "paused_below_minimum" for a in plan.allocations)
    assert any("platform minimum" in n for n in plan.notes)


def test_a_zero_envelope_reports_standings_rather_than_noise():
    """The default state ships at $0 — it must read as idle, not broken."""
    plan = ad_allocator.allocate(_MATURE, ad_allocator.AllocatorConfig())
    assert plan.dry_run and plan.allocated_usd == 0.0
    assert all(a.status == "unfunded" for a in plan.allocations)
    assert plan.allocations[0].arm_id == "v1"          # best arm first
    assert "no daily budget" in " ".join(plan.notes).lower()


def test_plan_summary_speaks_plainly():
    dry = ad_allocator.plan_summary(ad_allocator.allocate(_MATURE, ad_allocator.AllocatorConfig()))
    assert "Rehearsal" in dry
    assert "the daily budget is zero" in dry
    for slug in ("paid_enabled_false", "envelope_zero", "operator_not_armed", "dry_run"):
        assert slug not in dry
    live = ad_allocator.plan_summary(ad_allocator.allocate(_MATURE, _armed()))
    assert "ads funded" in live and "$" in live


def test_no_live_arms_is_handled():
    plan = ad_allocator.allocate([Arm("x", status="retired")], _armed())
    assert plan.allocations == []
    assert plan.unallocated_usd == 60.0


# ═══════════════════════════════════════════════════════════════════════════
# contracts
# ═══════════════════════════════════════════════════════════════════════════

def _schema(name: str) -> dict:
    return json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text())


def _assert_contract(row: dict, schema: dict, *, allow_null: tuple[str, ...] = ()):
    """Required fields present, enums honoured — no jsonschema dep in the CI pack."""
    for field in schema["required"]:
        assert field in row, f"missing required field {field}"
        if field not in allow_null:
            assert row[field] not in (None, ""), f"empty required field {field}"
    for field, spec in schema["properties"].items():
        if field not in row or row[field] is None:
            continue
        if "enum" in spec:
            assert row[field] in spec["enum"], f"{field}={row[field]!r} outside enum"
        if "const" in spec:
            assert row[field] == spec["const"], f"{field}={row[field]!r} != const"


def test_a_built_creative_satisfies_its_contract():
    schema = _schema("marketing_ad_creative")
    for c in (_creative(), _creative(format_id="google_search"),        # draft + refused
              _creative(format_id="tiktok_dance")):                     # unknown format
        _assert_contract(c.as_dict(), schema)
    assert _creative().as_dict()["creative_id"].startswith("adc-")


def test_a_created_arena_satisfies_its_contract():
    schema = _schema("marketing_ad_arena")
    _assert_contract(_arena().as_dict(), schema)
    _assert_contract(_arena(plane="paid", unit="impression", holdout=0.1).as_dict(), schema)


def test_the_contracts_agree_with_the_code_they_describe():
    """A contract that drifts from its module is documentation, not a contract."""
    arena_schema = _schema("marketing_ad_arena")
    assert arena_schema["properties"]["schema"]["const"] == ad_arena.SCHEMA
    assert set(arena_schema["properties"]["unit"]["enum"]) == set(ad_arena.UNITS)
    assert set(arena_schema["properties"]["status"]["enum"]) == set(ad_arena.STATUSES)

    creative_schema = _schema("marketing_ad_creative")
    planes = set(creative_schema["properties"]["plane"]["enum"]) - {"unknown"}
    assert planes == set(ad_creative.PLANES)
    assert set(creative_schema["properties"]["plane"]["enum"]) >= {
        f.plane for f in ad_creative.FORMATS.values()}


# ═══════════════════════════════════════════════════════════════════════════
# ad_central — the facade
# ═══════════════════════════════════════════════════════════════════════════

def test_the_shipped_config_resolves_and_is_armed_off_G_A():
    """The repo's real config/marketing.yml, not a fixture."""
    from engine.marketing.state import _load_cfg
    resolved = ad_central.resolve(_load_cfg(ROOT))
    assert resolved["paid_enabled"] is False
    assert resolved["envelope"]["daily_usd"] == 0
    assert resolved["arena"]["n_floor"] == 100
    assert resolved["envelope"]["per_arm_daily_cap_usd"] == 20
    gate = ad_central.gate_state(resolved)
    assert gate["spend_permitted"] is False
    assert set(gate["blocked_by"]) == {"paid_enabled_false", "envelope_zero",
                                       "operator_not_armed"}


def test_a_missing_config_block_falls_back_to_safe_defaults():
    resolved = ad_central.resolve({})
    assert resolved["paid_enabled"] is False
    assert resolved["envelope"]["daily_usd"] == 0.0
    assert ad_central.gate_state(resolved)["spend_permitted"] is False


def test_the_gate_explanation_avoids_slugs():
    plain = ad_central.gate_state(ad_central.resolve({}))["plain"]
    for slug in ("paid_enabled_false", "envelope_zero", "operator_not_armed"):
        assert slug not in plain
    assert "All three" in plain


def test_state_on_an_empty_tree_is_honest_not_broken(tmp_path):
    s = ad_central.state(tmp_path, cfg={})
    assert s["ok"] is True
    assert s["counts"]["arenas"] == 0
    assert "No split tests yet" in s["plain"]


def test_state_end_to_end(tmp_path):
    arena = ad_arena.create(
        arena_id="hero-copy-1",
        hypothesis="Does leading with the receipt beat leading with the promise?",
        plane="owned", unit="visitor", primary_metric="signup_rate",
        creative_ids=["adc-promise", "adc-receipt"],
        control_creative_id="adc-promise",
    )
    arena.status = "running"
    ad_arena.save_arena(arena, root=tmp_path)
    for i in range(600):
        cid = ad_arena.assign(arena, f"v-{i}")
        ad_arena.record_assignment(arena.arena_id, f"v-{i}", cid, root=tmp_path)
        # A real effect: the receipt line converts about twice as often.
        rate = 12 if cid == "adc-receipt" else 25
        if i % rate == 0:
            ad_arena.record_outcome(arena.arena_id, f"v-{i}", "signup_rate", root=tmp_path)

    s = ad_central.state(tmp_path, cfg={})
    assert s["ok"] is True
    assert s["counts"]["arenas"] == 1
    row = s["arenas"][0]
    assert row["arena"]["arena_id"] == "hero-copy-1"
    assert row["readout"]["verdict"] in ("separated", "null", "seeding")
    assert row["headline"].strip()
    assert row["budget"]["dry_run"] is True          # nothing armed, nothing spent
    assert row["budget"]["allocated_usd"] == 0.0
    total_assigned = sum(a["assigned"] for a in row["readout"]["arms"])
    assert total_assigned == 600                     # every unit accounted for


def test_the_shipped_seed_arena_is_a_real_two_armed_test():
    """Guards the committed pre-registration in data/marketing/ad_central/.

    A one-armed "split test" is not a split test — an earlier draft silently lost
    an arm to the hero's 64-character limit and still saved.
    """
    arenas = ad_arena.load_arenas(root=ROOT)
    if not arenas:
        pytest.skip("no seeded arena in this tree")
    creatives = ad_arena.load_creatives(root=ROOT)
    schema = _schema("marketing_ad_arena")
    for a in arenas:
        _assert_contract(a.as_dict(), schema)
        assert len(a.arm_creative_ids) >= 2, f"{a.arena_id} has fewer than two ads"
        assert a.control_creative_id in a.arm_creative_ids
        assert a.primary_metric, f"{a.arena_id} has no pre-registered primary metric"
        for cid in a.arm_creative_ids:
            assert cid in creatives, f"{a.arena_id} arm {cid} has no stored copy"
            row = creatives[cid]
            fmt = ad_creative.FORMATS.get(row["format_id"])
            assert fmt is not None
            assert len(row["headline"]) <= fmt.headline_max
            assert len(row["body"]) <= fmt.body_max
            assert row["status"] != "refused", f"{cid} was seeded already refused"


def test_the_shipped_seed_renders_a_panel():
    s = ad_central.state(ROOT)
    assert s["ok"] is True
    assert s["gate"]["spend_permitted"] is False
    for row in s["arenas"]:
        assert row["headline"].strip()
        assert row["budget"]["dry_run"] is True
        for arm in row["readout"]["arms"]:
            assert arm["label"], "the console would print a raw adc- id here"


def test_state_never_raises_on_a_corrupt_tree(tmp_path):
    d = tmp_path / ad_arena.DEFAULT_LEDGER_DIR
    d.mkdir(parents=True)
    (d / ad_arena.ARENAS_FILE).write_text("garbage\n{\n", encoding="utf-8")
    s = ad_central.state(tmp_path, cfg={})
    assert s["ok"] is True
    assert s["counts"]["arenas"] == 0
