"""Partial-pooling engine — the four hard safety properties (Masterplan §W4, audit #13/#19).

These are the load-bearing invariants the closed loop rests on:
  1. SIGN-SAFETY   — a wrong-sign leg's pooled weight goes BELOW equal-weight (can go negative
     edge), never floored at an optimistic prior.
  2. TRUST-REGION  — no single weight moves more than MAX_STEP per update.
  3. COLD-START    — n=0 everywhere → equal weights (the honest prior), never a crash.
  4. ARMING        — the predicate needs enough effective events AND pooled-beats-equal on a
     held-out tail; co-firing events collapse to one effective observation.
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
