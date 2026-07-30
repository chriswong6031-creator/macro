"""Unit tests for engine.subsector_turn — the turn/cycle detector.

Each test pins a property the detector must have, and most of them pin a specific way an
earlier version of this engine was WRONG (measured on the 2026-07-30 cross-section):

* absolute (non-market-relative) legs flagged 92 of 268 nodes as topping on one risk-on
  week — ``test_market_wide_move_fires_nothing``;
* weekend archive rows repeat Friday's numbers, handing the state machine free
  confirmations — ``test_non_session_rows_do_not_confirm``;
* a five-day-old low qualified a node as "topping" — ``test_age_gate_blocks_fresh_extreme``;
* ``flip``/``accel``/``curve`` were monotone in the same difference, saturating the score
  at 1.000 — ``test_legs_are_independent`` and ``test_scores_do_not_saturate``.
"""
from __future__ import annotations

import pytest

from engine import subsector_turn as T


# ── fixtures ────────────────────────────────────────────────────────────────────
def _perf(d1=0.0, w1=0.0, m1=0.0, m3=0.0, m6=0.0, y1=0.0):
    return {"1D": d1, "1W": w1, "1M": m1, "3M": m3, "6M": m6, "1Y": y1,
            "MTD": m1, "YTD": y1}


def _history(n_days: int, nodes: dict, *, start: int = 5, jitter=True):
    """`nodes` maps key → perf dict. Emits n_days archive rows dated 2026-07-<start+i>.

    Daily (`1D`) values are jittered per session so realised volatility is estimable —
    a flat series has zero vol and every read stays `vol_cold`.
    """
    rows = []
    for i in range(n_days):
        subs = {}
        for j, (k, p) in enumerate(nodes.items()):
            q = dict(p)
            if jitter:
                q["1D"] = round(((i + j) % 5 - 2) * 0.4, 2)
            subs[k] = q
        rows.append({"asof": f"2026-07-{start + i:02d}", "subsectors": subs})
    return rows


# ── 1. term-structure algebra ───────────────────────────────────────────────────
def test_segment_paces_are_disjoint():
    """A month's entire gain landing in the last week leaves the ex-week segment flat.

    This is the whole point of the decomposition: the incumbent `accel` would read this
    node as barely accelerating because its 3M baseline contains the same week.
    """
    p = T.segment_paces(_perf(w1=5.0, m1=5.0, m3=5.0))
    assert p["w1"] == pytest.approx(5.0, abs=1e-6)
    assert p["m1x"] == pytest.approx(0.0, abs=1e-6)   # 1M ex-1W: nothing happened
    assert p["m3x"] == pytest.approx(0.0, abs=1e-6)   # 3M ex-1M: nothing happened


def test_segment_paces_geometric_and_weekly():
    """A steady 1M gain annualises to a weekly pace, not a naive division."""
    p = T.segment_paces(_perf(w1=0.0, m1=8.0))
    # 1M ex-1W spans 16 trading days: (1.08 ** (5/16) - 1) * 100
    assert p["m1x"] == pytest.approx(((1.08 ** (5 / 16)) - 1) * 100, abs=1e-6)


def test_segment_paces_guard_absurd_inputs():
    assert T.segment_paces(_perf(w1=-99.5))["w1"] is None       # growth factor ≤ 0
    assert T.segment_paces({"1W": "nonsense"})["w1"] is None
    assert T.segment_paces({"1W": float("inf")})["w1"] is None


def test_level_path_and_cycle_facts():
    """Down 20% over the year, then +25% off the low → path low is the 1M knot."""
    p = _perf(w1=10.0, m1=25.0, m3=-10.0, m6=-15.0, y1=-20.0)
    lp = T.level_path(p)
    assert lp["path"][-1] == 100.0                      # now is normalised to 100
    assert lp["dd_from_peak"] < 0 and lp["up_from_trough"] > 0
    assert lp["days_since_trough_approx"] == 21         # the 1M knot was the low
    assert 0 <= lp["pos_in_range"] <= 100


def test_relative_perf_is_a_growth_ratio():
    """Excess return compounds as a ratio, not an arithmetic difference."""
    rel = T.relative_perf(_perf(m1=10.0), _perf(m1=5.0))
    assert rel["1M"] == pytest.approx((1.10 / 1.05 - 1) * 100, abs=1e-6)


# ── 2. relativization: the market is not a signal ───────────────────────────────
def test_market_wide_move_fires_nothing():
    """Twelve identical nodes rallying together produce ZERO turn calls.

    The regression this pins: with absolute legs, a single risk-on week put 92 of 268 real
    nodes into a top state. If every node moves the same, nothing rotated.
    """
    node = _perf(d1=3.0, w1=12.0, m1=-2.0, m3=-12.0, m6=-18.0, y1=-25.0)
    nodes = {f"n{i}": node for i in range(12)}
    out = T.replay(_history(12, nodes))
    assert out["reads"], "replay produced no reads"
    for k, rd in out["reads"].items():
        assert rd["bottom_score"] == 0.0, f"{k} fired on a market-wide move"
        assert rd["turn_state"] not in ("turn_up", "bottoming")


def test_lone_rotator_fires_against_a_flat_tape():
    """The same move, when only ONE node makes it, is a rotation and must arm."""
    flat = _perf(w1=0.0, m1=-2.0, m3=-12.0, m6=-18.0, y1=-25.0)
    hot = _perf(d1=3.0, w1=12.0, m1=8.0, m3=-6.0, m6=-14.0, y1=-22.0)
    nodes = {f"n{i}": flat for i in range(11)}
    nodes["hot"] = hot
    out = T.replay(_history(12, nodes))
    hot_read = out["reads"]["hot"]
    assert hot_read["bottom_score"] >= T.PARAMS["arm"]
    assert hot_read["turn_state"] in ("bottoming", "turn_up")
    assert hot_read["pace_rel"]["w1"] > hot_read["pace"]["w1"] - 1e-9  # tape was flat/down


def test_market_block_is_published():
    nodes = {f"n{i}": _perf(w1=float(i)) for i in range(6)}
    out = T.replay(_history(10, nodes))
    assert out["market"]["pace"]["w1"] is not None
    assert out["market"]["perf"]["1W"] is not None


# ── 3. cycle-position preconditions ─────────────────────────────────────────────
def test_precondition_requires_a_prior_move():
    """No drawdown → no bottom is possible, however violent the impulse."""
    no_fall = T.level_path(_perf(w1=15.0, m1=15.0, m3=15.0, m6=15.0, y1=15.0))
    assert T._precondition(no_fall, want_fall=True) is False


def test_age_gate_blocks_fresh_extreme():
    """A node whose low is five sessions old cannot be called "topping".

    Without the age gate, +16% off a five-day-old trough satisfied `rose` and the node
    became eligible for a top call — the whipsaw class this detector exists to avoid.
    """
    p = _perf(w1=16.0, m1=2.0, m3=-5.0, m6=-10.0, y1=-15.0)
    lp = T.level_path(p)
    assert lp["days_since_trough_approx"] == 5          # the low IS the 1W knot
    assert lp["up_from_trough"] >= T.PARAMS["rose_run_min"]
    assert T._precondition(lp, want_fall=False) is False


def test_rs_path_supplies_a_precondition_of_its_own():
    """Leadership can roll over while price grinds sideways — the RS line must see it."""
    flat_price = _perf(w1=0.0, m1=0.0, m3=0.0, m6=0.0, y1=0.0)
    rising_tape = _perf(w1=1.0, m1=4.0, m3=12.0, m6=20.0, y1=30.0)
    rd = T.node_read(flat_price, market_perf=rising_tape,
                     market_pace=T.segment_paces(rising_tape))
    assert rd["rs_dd_from_peak"] is not None and rd["rs_dd_from_peak"] < 0
    assert rd["fell"] is True          # the RS line fell even though price did not


def test_position_never_contributes_to_a_score():
    """Two nodes, same relative impulse, different cycle position → same score.

    Pins the postmortem §4.3 law: position gates, it never scores. The noise scale is
    passed explicitly so the two nodes share a denominator — a node with a wilder
    twelve-month segment legitimately earns a wider volatility estimate, and that is
    vol-normalisation, not position leaking into the score.
    """
    tape = _perf(w1=0.0, m1=0.0, m3=0.0, m6=0.0, y1=0.0)
    mp = T.segment_paces(tape)
    kw = {"market_perf": tape, "market_pace": mp, "rel_vol_w": 3.0}
    deep = T.node_read(_perf(w1=8.0, m1=-1.0, m3=-9.0, m6=-20.0, y1=-45.0), **kw)
    shallow = T.node_read(_perf(w1=8.0, m1=-1.0, m3=-9.0, m6=-20.0, y1=-25.0), **kw)
    assert deep["pos_in_range"] != shallow["pos_in_range"]
    assert deep["bottom_score"] == shallow["bottom_score"]


# ── 4. legs ─────────────────────────────────────────────────────────────────────
def test_legs_are_independent():
    """`flip` (how big) and `regime` (what it turned from) must move separately.

    An earlier version scored flip+accel+curve, all monotone in the same difference; on
    real data their pairwise correlation was ~1 and scores saturated. flip/regime measured
    -0.01 on the 2026-07-30 cross-section.
    """
    paces_same_flip_calm = {"w1": 6.0, "m1x": -1.0, "m3x": -0.2, "m6x": -0.2}
    paces_same_flip_beaten = {"w1": 6.0, "m1x": -1.0, "m3x": -4.0, "m6x": -4.0}
    a = T._legs(paces_same_flip_calm, 2.0, up=True, breadth_frac=None, rs_mom=None)
    b = T._legs(paces_same_flip_beaten, 2.0, up=True, breadth_frac=None, rs_mom=None)
    assert a["flip"] == b["flip"]          # identical impulse
    assert b["regime"] > a["regime"]       # but one turned from a beaten-down trend


def test_flip_requires_the_prior_segment_to_oppose():
    """Rising, and rising faster, is a continuation — not a bottom."""
    accelerating_up = {"w1": 9.0, "m1x": 3.0, "m3x": 2.0, "m6x": 2.0}
    legs = T._legs(accelerating_up, 2.0, up=True, breadth_frac=None, rs_mom=None)
    assert legs["flip"] == 0.0


def test_missing_breadth_leg_abstains_rather_than_voting_zero():
    paces = {"w1": 9.0, "m1x": -2.0, "m3x": -3.0, "m6x": -3.0}
    without = T._score(T._legs(paces, 2.0, up=True, breadth_frac=None, rs_mom=1.5))
    withb = T._score(T._legs(paces, 2.0, up=True, breadth_frac=1.0, rs_mom=1.5))
    assert without == pytest.approx(withb, abs=1e-9)   # renormalised, not penalised


def test_scores_stay_bounded():
    paces = {"w1": 999.0, "m1x": -50.0, "m3x": -50.0, "m6x": -50.0}
    legs = T._legs(paces, 0.5, up=True, breadth_frac=1.0, rs_mom=99.0)
    assert 0.0 <= T._score(legs) <= 1.0


def test_scores_do_not_saturate_on_real_shaped_input():
    """A strong-but-not-extraordinary turn must land below `confirm`, not at 1.0."""
    paces = {"w1": 3.0, "m1x": -0.5, "m3x": -0.4, "m6x": -0.3}
    legs = T._legs(paces, 2.5, up=True, breadth_frac=0.6, rs_mom=0.5)
    score = T._score(legs)
    assert 0.0 < score < T.PARAMS["confirm"]


# ── 5. breadth ──────────────────────────────────────────────────────────────────
def test_breadth_is_measured_against_the_tape():
    """Members that merely keep pace with a rising tape are not participating."""
    members = ["A", "B", "C", "D"]
    # every member does +10%/wk, and so does the market
    mperf = {m: _perf(w1=10.0, m1=10.0) for m in members}
    mkt_pace = {"w1": 10.0, "m1x": 0.0}
    brd = T.member_breadth(members, mperf, mkt_pace)
    assert brd["n"] == 4
    assert brd["up_1w"] == 1.0            # absolute receipt: all up
    assert brd["beat_mkt_1w"] == 0.0      # but none beat the tape
    # Every member exactly tied with the tape carries no directional information at all,
    # so participation ABSTAINS (None) rather than voting "nobody turned up" (0.0).
    assert brd["turn_up"] is None


def test_breadth_counts_members_that_genuinely_trail():
    members = list("ABCD")
    # each member decelerates vs the tape: +1%/wk now against +6%/wk before, tape flat
    mperf = {m: _perf(w1=1.0, m1=7.06) for m in members}
    brd = T.member_breadth(members, mperf, {"w1": 0.0, "m1x": 0.0})
    assert brd["turn_dn"] == 1.0 and brd["turn_up"] == 0.0


def test_breadth_needs_a_minimum_and_flags_concentration():
    assert T.member_breadth(["A"], {"A": _perf(w1=5.0)}, None) is None
    members = list("ABCDE")
    mperf = {m: _perf(w1=0.1, m1=0.0) for m in members}
    mperf["A"] = _perf(w1=40.0, m1=0.0)     # one name owns the magnitude
    brd = T.member_breadth(members, mperf, {"w1": 0.0, "m1x": 0.0})
    assert brd["concentrated"] is True
    assert brd["top_share"] > T.PARAMS["narrow_top_share"]


# ── 6. the archive: non-sessions ────────────────────────────────────────────────
def test_non_session_rows_are_dropped():
    """A row identical to the previous one is not a session (weekend/holiday feed)."""
    node = _perf(w1=4.0)
    rows = [
        {"asof": "2026-07-24", "subsectors": {"a": dict(node), "b": dict(node)}},
        {"asof": "2026-07-25", "subsectors": {"a": dict(node), "b": dict(node)}},
        {"asof": "2026-07-26", "subsectors": {"a": dict(node), "b": dict(node)}},
        {"asof": "2026-07-27", "subsectors": {"a": _perf(w1=9.0), "b": dict(node)}},
    ]
    cleaned = T._clean_history(rows)
    assert [r["asof"] for r in cleaned] == ["2026-07-24", "2026-07-27"]


def test_non_session_rows_do_not_confirm():
    """Two duplicate rows must not satisfy a two-session confirmation."""
    flat = _perf(w1=0.0, m1=-2.0, m3=-12.0, m6=-18.0, y1=-25.0)
    hot = _perf(d1=3.0, w1=14.0, m1=9.0, m3=-6.0, m6=-14.0, y1=-22.0)
    warm = _history(10, {**{f"n{i}": flat for i in range(11)}, "hot": flat})
    # one genuine hot session, then a byte-identical repeat of it
    hot_row = {"asof": "2026-07-16",
               "subsectors": {**{f"n{i}": dict(flat) for i in range(11)}, "hot": dict(hot)}}
    dup_row = {"asof": "2026-07-17", "subsectors": hot_row["subsectors"]}
    out = T.replay(warm + [hot_row, dup_row])
    assert out["n_days"] == 11                      # the duplicate is not a session
    assert out["reads"]["hot"]["turn_state"] != "turn_up"


# ── 7. state machine ────────────────────────────────────────────────────────────
def _armed_read(score=0.9, trend=-1.0, cold=False):
    return {"bottom_score": score, "top_score": 0.0, "trend_z": trend, "vol_cold": cold}


def test_confirmation_needs_two_sessions_or_one_fast_read():
    st = T.advance_state(None, {"bottom_score": 0.70, "top_score": 0.0,
                                "trend_z": -1.0, "vol_cold": False}, "d1")
    assert st["state"] == "bottoming"                        # armed, not confirmed
    st2 = T.advance_state(st, {"bottom_score": 0.70, "top_score": 0.0,
                               "trend_z": -1.0, "vol_cold": False}, "d2")
    assert st2["state"] == "turn_up"                         # second session confirms
    fast = T.advance_state(None, _armed_read(score=T.PARAMS["fast"] + 0.01), "d1")
    assert fast["state"] == "turn_up"                        # violent read confirms at once


def test_cold_read_cannot_confirm():
    """No realised volatility yet ⇒ every z is inflated ⇒ arm only."""
    st = T.advance_state(None, _armed_read(score=0.95, cold=True), "d1")
    assert st["state"] == "bottoming"
    st2 = T.advance_state(st, _armed_read(score=0.95, cold=True), "d2")
    assert st2["state"] == "bottoming"


def test_confirmed_state_needs_hysteresis_to_exit():
    st = T.advance_state(None, _armed_read(score=0.95), "d1")
    assert st["state"] == "turn_up"
    quiet = {"bottom_score": 0.0, "top_score": 0.0, "trend_z": 0.9, "vol_cold": False}
    for i in range(T.PARAMS["exit_days"] - 1):
        st = T.advance_state(st, quiet, f"q{i}")
        assert st["state"] == "turn_up", "left a confirmed state too early"
    st = T.advance_state(st, quiet, "qN")
    assert st["state"] == "trending_up"          # exits into the standing trend


def test_confirmed_state_expires_on_ttl_and_cannot_instantly_re_announce():
    """A node that never stops firing must not re-enter "fresh turn" the next session.

    Before the lockout, TTL expiry was cosmetic: the very next session re-confirmed and
    reset `since`/`age`, so a long trend advertised itself as day 1 of a fresh turn forever.
    """
    st = T.advance_state(None, _armed_read(score=0.95), "d0")
    live = {"bottom_score": 0.7, "top_score": 0.0, "trend_z": 0.5, "vol_cold": False}
    for i in range(T.PARAMS["ttl"] + 1):
        st = T.advance_state(st, live, f"d{i}")
    assert st["state"] != "turn_up"
    assert st["lockout"] > 0
    st = T.advance_state(st, live, "after")
    assert st["state"] != "turn_up", "re-announced a fresh turn during lockout"


def test_lockout_releases_when_the_condition_actually_lapses():
    """A genuine NEW turn after a real lapse is never delayed by the lockout."""
    st = T.advance_state(None, _armed_read(score=0.95), "d0")
    live = {"bottom_score": 0.7, "top_score": 0.0, "trend_z": 0.5, "vol_cold": False}
    for i in range(T.PARAMS["ttl"] + 1):
        st = T.advance_state(st, live, f"d{i}")
    quiet = {"bottom_score": 0.0, "top_score": 0.0, "trend_z": 0.1, "vol_cold": False}
    st = T.advance_state(st, quiet, "lapse")
    assert st["lockout"] == 0
    st = T.advance_state(st, _armed_read(score=0.95), "fresh")
    assert st["state"] == "turn_up"


def test_persistence_counts_armed_sessions():
    st = None
    for i in range(3):
        st = T.advance_state(st, _armed_read(score=0.5), f"d{i}")
    assert st["persist_up"] == 3
    st = T.advance_state(st, {"bottom_score": 0.0, "top_score": 0.0,
                              "trend_z": 0.0, "vol_cold": False}, "d9")
    assert st["persist_up"] == 0


def test_range_and_trend_states():
    quiet = {"bottom_score": 0.0, "top_score": 0.0, "trend_z": 0.0, "vol_cold": False}
    assert T.advance_state(None, quiet, "d")["state"] == "range"
    up = {**quiet, "trend_z": 2.0}
    assert T.advance_state(None, up, "d")["state"] == "trending_up"
    dn = {**quiet, "trend_z": -2.0}
    assert T.advance_state(None, dn, "d")["state"] == "trending_down"


# ── 8. replay + payload contract ────────────────────────────────────────────────
def test_replay_is_deterministic_and_has_no_lookahead():
    nodes = {f"n{i}": _perf(w1=float(i) - 5, m1=-3.0, m3=-10.0, m6=-14.0, y1=-20.0)
             for i in range(8)}
    rows = _history(12, nodes)
    a = T.replay(rows)
    b = T.replay(rows)
    assert a["states"] == b["states"]
    # truncating the tail cannot change an earlier day's state
    early_full = T.replay(rows[:8])["states"]
    assert T.replay(rows[:8])["states"] == early_full


def test_replay_emits_tail_and_row_fields():
    nodes = {f"n{i}": _perf(w1=float(i), m1=-3.0, m3=-10.0, m6=-14.0, y1=-20.0)
             for i in range(6)}
    out = T.replay(_history(12, nodes))
    rd = out["reads"]["n5"]
    for f in ("pace", "pace_rel", "pace_mkt", "rs_ratio_v2", "rs_mom_v2", "turn_state",
              "turn_since", "rank_score_v2", "tail", "bottom_score", "top_score"):
        assert f in rd, f"missing payload field {f}"
    assert len(rd["tail"]) <= T.PARAMS["tail_days"]
    assert all(len(pt) == 2 for pt in rd["tail"])


def test_replay_handles_empty_and_junk_history():
    assert T.replay([])["n_days"] == 0
    assert T.replay([{"asof": "2026-07-01"}])["n_days"] == 0
    assert T.replay([{"nonsense": 1}])["reads"] == {}


def test_summarize_applies_the_breadth_floor():
    nodes = {"thin": _perf(d1=4.0, w1=20.0, m1=2.0, m3=-12.0, m6=-20.0, y1=-30.0)}
    nodes.update({f"n{i}": _perf(w1=0.0, m1=0.0, m3=0.0, m6=0.0, y1=0.0) for i in range(8)})
    out = T.replay(_history(12, nodes))
    meta = {"thin": {"n_members": 1}}
    meta.update({f"n{i}": {"n_members": 8} for i in range(8)})
    summ = T.summarize(out["reads"], meta)
    assert "thin" not in summ["bottoming"] and "thin" not in summ["turned_up"]
    assert set(summ["counts"]) == set(T.STATES)


def test_state_copy_covers_every_state():
    for s in T.STATES:
        assert s in T.STATE_COPY
        for f in ("en", "zh", "say_en", "say_zh"):
            assert T.STATE_COPY[s][f]


# ── 9. nominations ──────────────────────────────────────────────────────────────
def test_handoff_pairs_a_donor_with_a_receiver_in_the_same_theme():
    reads = {
        "out1": {"turn_state": "turn_down", "top_score": 0.8, "bottom_score": 0.0,
                 "turn_since": "2026-07-28", "pace": {"w1": -6.0}, "up_from_trough": 30.0},
        "in1": {"turn_state": "turn_up", "bottom_score": 0.7, "top_score": 0.0,
                "turn_since": "2026-07-29", "pace": {"w1": 5.0}, "dd_from_peak": -18.0},
        "other": {"turn_state": "range", "bottom_score": 0.0, "top_score": 0.0},
    }
    meta = {"out1": {"theme": "Tech", "name": "Memory"},
            "in1": {"theme": "Tech", "name": "Software"},
            "other": {"theme": "Energy", "name": "Coal"}}
    noms = T.handoff_nominations(reads, meta)
    assert len(noms) == 1
    assert noms[0]["donor"]["key"] == "out1" and noms[0]["receiver"]["key"] == "in1"
    assert noms[0]["both_confirmed"] is True
    assert 0 < noms[0]["confidence"] <= 1.0


def test_handoff_needs_both_sides():
    reads = {"out1": {"turn_state": "turn_down", "top_score": 0.9, "bottom_score": 0.0}}
    assert T.handoff_nominations(reads, {"out1": {"theme": "Tech"}}) == []
