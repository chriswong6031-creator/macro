"""Partial-pooling engine — the four hard safety properties (Masterplan §W4, audit #13/#19).

These are the load-bearing invariants the closed loop rests on:
  1. SIGN-SAFETY   — a wrong-sign leg's pooled weight goes BELOW equal-weight (can go negative
     edge), never floored at an optimistic prior.
  2. TRUST-REGION  — no single weight moves more than MAX_STEP per update.
  3. COLD-START    — n=0 everywhere → equal weights (the honest prior), never a crash.
  4. ARMING        — the predicate needs enough effective events AND pooled-beats-equal on a
     held-out tail BY A PRE-REGISTERED MARGIN, with a positive held-out edge; co-firing events
     collapse to one effective observation.
"""
from __future__ import annotations

from engine import pooling


# --- 1. SIGN-SAFETY: a reliably-wrong leg loses influence (shrinks toward/below zero) ------ #
def test_wrong_sign_leg_pooled_edge_goes_negative():
    # 'bad' consistently WRONG (negative signed outcomes), 'good' consistently right.
    outcomes = {
        "good": [0.03, 0.04, 0.02, 0.05, 0.03, 0.04, 0.03, 0.02, 0.04, 0.03],
        "bad":  [-0.03, -0.04, -0.02, -0.05, -0.03, -0.04, -0.03, -0.02, -0.04, -0.03],
    }
    members = pooling.member_stats_from_outcomes(outcomes)
    edges = pooling.pooled_edges(members)
    assert edges["bad"] < 0, "a wrong-sign leg must keep a NEGATIVE pooled edge (shrink toward zero, not optimism)"
    assert edges["good"] > 0
    assert edges["good"] > edges["bad"]


def test_wrong_sign_leg_underweighted_vs_equal():
    outcomes = {
        "good": [0.03, 0.04, 0.02, 0.05, 0.03, 0.04, 0.03, 0.02, 0.04, 0.03],
        "bad":  [-0.03, -0.04, -0.02, -0.05, -0.03, -0.04, -0.03, -0.02, -0.04, -0.03],
    }
    members = pooling.member_stats_from_outcomes(outcomes)
    w = pooling.pooled_weights(members)
    assert w["bad"] < 0.5 < w["good"], "the wrong-sign leg must be UNDER the equal weight, the right one OVER"
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_wrong_sign_leg_can_hit_floor():
    # with a hard floor of 0 a badly-wrong leg is driven to (near) zero weight
    outcomes = {"good": [0.1] * 20, "bad": [-0.1] * 20}
    w = pooling.pooled_weights(pooling.member_stats_from_outcomes(outcomes), floor=0.0)
    assert w["bad"] < w["good"]
    assert w["bad"] >= 0.0


# --- 2. TRUST-REGION: bounded step per update --------------------------------------------- #
def test_trust_region_caps_each_step():
    current = {"a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}
    target = {"a": 1.0, "b": 0.0, "c": 0.0, "d": 0.0}   # wants to slam everything to 'a'
    stepped = pooling.trust_region_step(current, target, max_step=0.10)
    # no key moved more than max_step (pre-renorm bound); post-renorm still bounded-ish
    for k in current:
        assert abs(stepped[k] - current[k]) <= 0.10 + 1e-6, f"{k} moved more than max_step"
    assert abs(sum(stepped.values()) - 1.0) < 1e-9


def test_trust_region_moves_toward_target():
    current = {"a": 0.5, "b": 0.5}
    target = {"a": 0.9, "b": 0.1}
    stepped = pooling.trust_region_step(current, target, max_step=0.10)
    assert stepped["a"] > current["a"] and stepped["b"] < current["b"]


# --- 3. COLD-START: n=0 → equal weights, no crash ----------------------------------------- #
def test_cold_start_all_zero_n_gives_equal_weights():
    outcomes = {"a": [], "b": [], "c": []}
    members = pooling.member_stats_from_outcomes(outcomes)
    w = pooling.pooled_weights(members)
    assert all(abs(v - 1 / 3) < 1e-9 for v in w.values()), "n=0 everywhere must fall back to equal weights"
    edges = pooling.pooled_edges(members)
    assert all(abs(e) < 1e-9 for e in edges.values()), "no data → zero edge (the honest prior)"


def test_cold_start_empty_members_no_crash():
    assert pooling.pooled_weights([]) == {}
    assert pooling.pooled_edges([]) == {}
    assert pooling.trust_region_step({}, {}) == {}


def test_single_thin_member_shrinks_toward_family():
    # n=1 member borrows almost entirely from the family mean (kills the min-n cliff)
    outcomes = {"rich": [0.03] * 30, "thin": [0.5]}   # thin has one lucky huge outcome
    members = pooling.member_stats_from_outcomes(outcomes)
    edges = pooling.pooled_edges(members)
    # the thin member's raw mean is 0.5 but its pooled edge is pulled far down toward the
    # family/global prior — it does NOT get to keep 0.5 on n=1.
    assert edges["thin"] < 0.5, "a thin member must shrink toward the family, not keep its lucky mean"


# --- 4. ARMING PREDICATE ------------------------------------------------------------------ #
def _events(keys_outcomes, start="2026-01-01"):
    """Build ordered event dicts. keys_outcomes: list of (key, outcome, event_key?)."""
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    out = []
    for i, item in enumerate(keys_outcomes):
        key, oc = item[0], item[1]
        ek = item[2] if len(item) > 2 else f"{key}:{i}"
        out.append({"key": key, "outcome": oc, "event_key": ek,
                    "as_of": (d0 + dt.timedelta(days=i)).isoformat()})
    return out


def test_arming_blocks_below_min_family_n():
    ev = _events([("a", 0.02), ("b", -0.01), ("a", 0.03)])   # only 3 events
    st = pooling.arming(ev, min_family_n=12)
    assert st.armed is False
    assert st.n_eff < 12
    assert "accruing" in st.reason


def test_arming_collapses_cofiring_events():
    # 20 rows but all share ONE event_key → n_eff == 1, must stay unarmed
    ev = [{"key": "a", "outcome": 0.02, "event_key": "same_8k", "as_of": "2026-01-01"}
          for _ in range(20)]
    st = pooling.arming(ev, min_family_n=12)
    assert st.n_eff == 1, "co-firing on one event must collapse to a single effective observation"
    assert st.armed is False


def test_arming_requires_pooled_beats_equal_out_of_sample():
    # 'a' consistently right, 'b' consistently wrong, across many distinct events. Pooling
    # up-weights 'a' → beats equal weight on the held-out tail → arms.
    seq = []
    for i in range(30):
        seq.append(("a", 0.03))
        seq.append(("b", -0.03))
    ev = _events(seq)
    st = pooling.arming(ev, min_family_n=12)
    assert st.n_eff >= 12
    assert st.pooled_beats_equal is True
    assert st.armed is True
    assert st.heldout_edge_pooled > st.heldout_edge_equal


def test_arming_holds_when_pooling_no_better_than_equal():
    # both legs identically mediocre → pooling can't beat equal weight → not armed even with n.
    seq = []
    for i in range(30):
        seq.append(("a", 0.01))
        seq.append(("b", 0.01))
    ev = _events(seq)
    st = pooling.arming(ev, min_family_n=12)
    assert st.n_eff >= 12
    assert st.armed is False, "with no separable edge, pooling must NOT arm (no free-fit)"


def test_arm_status_to_dict_is_json_shaped():
    st = pooling.arming(_events([("a", 0.02)]), min_family_n=12)
    d = st.to_dict()
    assert set(d) >= {"armed", "n_eff", "need_n", "reason"}
    import json
    json.dumps(d)   # must be serialisable


# --- 5. THE PRE-REGISTERED ARMING MARGIN (2026-07-25) ------------------------------------- #
# Arming the live desk-weight vector is a PROMOTION to authority — the same class of decision
# as calibration_hub._PROMOTE_MARGIN — so a hair's-breadth held-out lift must not buy one.
# Measured on the live spine, the old bare `pooled > equal` predicate armed on margins down to
# 3e-18 (machine epsilon) while BOTH held-out edges were negative. These tests pin the fix.

def test_arming_refuses_a_1e5_margin():
    """THE HEADLINE REGRESSION. 'a' beats 'b' by a whisker, so pooling tilts a hair toward it
    and the OLD predicate (a bare `ep > ee` float comparison) armed the live weight path on a
    margin of ~1e-5. A margin that small is inside the pure-noise band — it is not evidence."""
    seq = [pair for _ in range(30) for pair in (("a", 0.025), ("b", 0.020))]
    st = pooling.arming(_events(seq), min_family_n=12)

    # the OLD predicate's condition still holds — pooled IS nominally ahead...
    assert st.pooled_beats_equal is True, "precondition: this is a case the old predicate armed"
    assert 0 < st.margin < 1e-4, f"precondition: hair-thin margin, got {st.margin:.3e}"
    # ...and that is exactly what must no longer be enough.
    assert st.armed is False, "a ~1e-5 held-out margin must NOT arm the live weight vector"
    assert st.margin < st.margin_required
    assert "bar" in st.reason


def test_arming_refuses_float_dust():
    """The degenerate limit of the same defect. Two legs separated by 2bp leave a held-out
    margin of ~1e-10 — still strictly positive, so the old `ep > ee` still fired. On the live
    spine this bottomed out at 3e-18, i.e. machine epsilon. It must never arm."""
    seq = [pair for _ in range(30) for pair in (("a", 0.02002), ("b", 0.02000))]
    st = pooling.arming(_events(seq), min_family_n=12)

    assert st.pooled_beats_equal is True, "precondition: strictly positive, the old bar's test"
    assert 0 < st.margin < 1e-8, f"precondition: float dust, got {st.margin:.3e}"
    assert st.armed is False


def test_arming_refuses_when_heldout_edge_is_negative_in_both_weightings():
    """SIGN GATE. 'a' loses 1%, 'b' loses 12% — pooling correctly tilts toward the less-bad leg
    and clears the margin floor comfortably. It still must NOT arm: pooled_weights yields a
    CONVEX allocation (it cannot go short), so a negative held-out edge means every allocation
    over this family loses out-of-sample. Losing less than equal-weight is not an edge."""
    seq = [pair for _ in range(30) for pair in (("a", -0.01), ("b", -0.12))]
    st = pooling.arming(_events(seq), min_family_n=12)

    assert st.heldout_edge_pooled < 0 and st.heldout_edge_equal < 0
    assert st.heldout_edge_pooled > st.heldout_edge_equal, "precondition: pooled loses LESS"
    assert st.margin >= st.margin_required, "precondition: isolates the sign gate, not the margin"
    assert st.armed is False, "a negative held-out edge must never arm, however big the margin"
    assert "not an edge" in st.reason


def test_arming_refuses_vacuous_single_member_family():
    """With ONE contributing member the pooled and equal-weight vectors are the SAME allocation,
    so the margin is identically zero and 'pooled did not beat equal' is arithmetic, not
    evidence. The predicate must say so rather than report a passed test."""
    st = pooling.arming(_events([("solo", 0.02 + 0.001 * i) for i in range(30)]),
                        min_family_n=12)
    assert st.armed is False
    assert st.heldout_n >= pooling.ARM_MIN_HELDOUT_N, "precondition: the tail is big enough"
    assert "vacuous" in st.reason


def test_arming_refuses_a_heldout_tail_too_thin_to_decide():
    """n_eff clears MIN_FAMILY_N but the held-out tail is 4 events — a weighted-mean comparison
    over four observations cannot decide anything, whatever margin it happens to produce."""
    st = pooling.arming(_events([("a", 0.02), ("b", 0.021)] * 6), min_family_n=12)
    assert st.n_eff >= 12
    assert st.heldout_n < pooling.ARM_MIN_HELDOUT_N
    assert st.armed is False
    assert "too thin" in st.reason


def test_arming_bar_stays_reachable_by_a_real_edge():
    """The opposite failure mode, guarded: a bar the tanh-bounded tilt can NEVER clear would
    make `armed` unreachable while still reading as evidence-based. A cleanly separated family
    at desk-scale outcomes must still arm."""
    seq = [pair for _ in range(30) for pair in (("right", 0.05), ("wrong", -0.05))]
    st = pooling.arming(_events(seq), min_family_n=12)
    assert st.armed is True, "a family with a REAL edge must still be able to arm"
    assert st.heldout_edge_pooled > 0
    assert st.margin >= st.margin_required


def test_arming_bars_are_pre_registered():
    """The constants are the contract (the sibling of calibration_hub._PROMOTE_MARGIN). If a
    future change relaxes one, that is a deliberate re-registration — not a silent edit."""
    assert pooling.ARM_MIN_MARGIN == 0.0005
    assert pooling.ARM_MIN_MARGIN_REL == 0.03
    assert pooling.ARM_MIN_HELDOUT_N == 8
    assert pooling.ARM_MIN_MEMBERS == 2
    assert pooling.ARM_REQUIRE_POSITIVE_EDGE is True
    # the relative bar rides on the tail's own outcome scale, so the floor stays meaningful
    # whatever units the caller's endpoint uses.
    seq = [pair for _ in range(30) for pair in (("a", 0.10), ("b", -0.10))]
    st = pooling.arming(_events(seq), min_family_n=12)
    tail_scale = 0.10
    assert abs(st.margin_required - pooling.ARM_MIN_MARGIN_REL * tail_scale) < 1e-9


def test_arm_status_reports_distance_to_arming():
    """The armory report must show HOW FAR from arming, not just that it is held."""
    seq = [pair for _ in range(30) for pair in (("a", 0.025), ("b", 0.020))]
    d = pooling.arming(_events(seq), min_family_n=12).to_dict()
    assert set(d) >= {"margin", "margin_required", "heldout_n", "need_heldout_n"}
    assert d["margin_required"] > 0 and d["heldout_n"] > 0
    import json
    json.dumps(d)
