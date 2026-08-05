"""Unit gates for the ROC-extremes measurement battery (research/shadow tier).

Everything here runs on SYNTHETIC series. The battery's own numbers come from the real
store, but a defect in a detector would produce a confident wrong verdict rather than an
error, so the detectors are pinned here on frames whose answer is known by construction —
fast, store-free, and runnable on a CI box that carries no ``data/``.

Four things are pinned, and they fail for different reasons on purpose.

1. **MATCHED MUST-FIRE / MUST-NOT-FIRE PAIRS.** Every detector gets a fixture that must
   fire and a sibling that must not, where the sibling differs in EXACTLY ONE leg
   (extension without the uptrend; washout without the stabilization; burst without the
   preceding 63d low; a rest that breaks; a roc12 extreme far from the 63d high). Each
   pair asserts that the shared leg is still TRUE in the must-not case — otherwise the
   fixture would prove only that some unrelated thing changed.

2. **BACKWARD-ONLY STAMPING.** ``burst_events`` is re-run on a series whose bars after a
   cutoff have been mutated; every event stamped at or before the cutoff must be
   identical. Section 3 is the positive control that keeps section 2 honest: a
   deliberately lookahead-contaminated variant of the same detector must FAIL that check.
   Without the positive control the invariance assertion could pass on any detector.

3. **VISIBILITY.** A leg that never fires must report 0, and an arm below MIN_CELL must
   produce a printed explanation — a silent skip is the failure mode these guard.

4. **THE RULER.** The matched-set delta and the event/control disjoining are pinned on
   hand-computable inputs. ``disjoin`` exists because the first real run produced a grain
   delta of EXACTLY +0.000: cells that were both an event and a control entered the delta
   as exact zeros and dragged the median to zero.

Run: python3 -m pytest tests/test_roc_extremes_battery.py -q
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BATTERY = ROOT / "research" / "prophet_us_audit" / "roc_extremes_battery.py"


def _load():
    """Import the research instrument by path (it lives outside any package).

    The module must have NO import-time side effects — no chdir, no store read — or this
    import would fail on a runner with no data/.
    """
    spec = importlib.util.spec_from_file_location("roc_extremes_battery", BATTERY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load()

SURGE = [0.03] * 12          # a 12-session run that pins roc12 at the top of its history
BURST_CYCLE = [0.04] * 5 + [-0.0095] * 20   # arms the burst-mover leg (p97 of roc5 ~ +21%)


def _px(rets) -> pd.Series:
    px = 100.0 * np.cumprod(1.0 + np.asarray(rets, dtype=float))
    return pd.Series(px, index=pd.bdate_range("2016-01-03", periods=len(px)))


def _frame(rets, name: str = "T") -> pd.DataFrame:
    return _px(rets).to_frame(name)


def _cycled(n: int) -> list[float]:
    r = [0.0]
    while len(r) < n:
        r += BURST_CYCLE
    return r[:n]


def _burst_rets(*, off_a_bottom: bool = True, rest: str = "hold",
                tail: float = 0.0, tail_len: int = 60) -> list[float]:
    """A burst-mover base, then a decline (or a rise), then a 5-session burst, then a rest."""
    r = _cycled(321)
    r += ([-0.006] * 70) if off_a_bottom else ([0.004] * 70)
    r += [0.05] * 5                                   # the burst
    if rest == "hold":
        r += [-0.01, 0.0, 0.01, 0.10]                 # rests inside the band, then leaves it
    elif rest == "break":
        r += [-0.20, 0.0, 0.0, 0.0]                   # gives back > 61.8% of the burst
    elif rest == "none":
        r += [0.06, 0.07, 0.08, 0.09, 0.10, 0.0]      # roc5 keeps making new highs
    r += [tail] * tail_len
    return r


def _burst_cells(ev: dict) -> set[tuple[str, int, int]]:
    arms = ("fire", "control_break", "control_no_rest", "control_no_rest_close_variant")
    return {(a, int(r["b1"]), int(r["event"])) for a in arms for r in ev[a]}


# ─────────────────────────────────────────────────────────────────────────────
# 1. percentile warm-up
# ─────────────────────────────────────────────────────────────────────────────
def test_pct_rank_min_periods_is_honored():
    """No percentile before min_periods observations — the warm-up is not a soft hint."""
    s = pd.Series(np.arange(400.0))
    p = R.pct_rank(s, 252, 126)
    assert p.iloc[:125].isna().all(), "a percentile appeared before min_periods"
    assert pd.notna(p.iloc[125]), "no percentile at exactly min_periods observations"
    # and the window is TRAILING: a rising series always ranks at the top of its own window
    assert float(p.iloc[300]) == pytest.approx(1.0)


def test_roll_q_min_periods_is_honored():
    s = pd.Series(np.arange(400.0))
    q = R.roll_q(s, 252, 0.97, 126)
    assert q.iloc[:125].isna().all()
    assert pd.notna(q.iloc[125])


# ─────────────────────────────────────────────────────────────────────────────
# 2. S-ROCX-TOP — extension WITH the uptrend vs the same extension WITHOUT it
# ─────────────────────────────────────────────────────────────────────────────
def test_rocx_top_fires_on_an_extension_inside_an_uptrend():
    C = _frame([0.0] + [0.002] * 460 + SURGE + [0.0] * 20)
    L = R.rocx_top_legs(C)
    bar = C.shape[0] - 21                       # the last surge session
    assert float(L["roc12_pctile"].iloc[bar, 0]) >= 0.95
    assert bool(L["legs"]["close_above_sma50"].iloc[bar, 0])
    assert bool(L["legs"]["sma50_rising_10"].iloc[bar, 0])
    assert bool(L["fire"].iloc[bar, 0])
    assert bool(L["fire_severe"].iloc[bar, 0])


def test_rocx_top_does_not_fire_on_extension_without_an_uptrend():
    """MATCHED must-not-fire: the SAME surge after a decline, so SMA50 is not rising.

    The percentile leg is asserted TRUE here on purpose — that is what makes this a
    single-leg contrast rather than a fixture that changed everything at once.
    """
    C = _frame([0.0] + [0.002] * 400 + [-0.015] * 60 + SURGE + [0.0] * 20)
    L = R.rocx_top_legs(C)
    bar = C.shape[0] - 21
    assert float(L["roc12_pctile"].iloc[bar, 0]) >= 0.95, "the extension leg must still be on"
    assert not bool(L["legs"]["sma50_rising_10"].iloc[bar, 0])
    assert not bool(L["fire"].iloc[bar, 0])
    assert not bool(L["fire_severe"].iloc[bar, 0])


def test_rocx_top_severe_variant_is_a_subset_of_the_primary():
    C = _frame([0.0] + [0.002] * 460 + SURGE + [0.0] * 20)
    L = R.rocx_top_legs(C)
    a = L["fire_severe"].to_numpy()
    b = L["fire"].to_numpy()
    assert not bool((a & ~b).any()), "a severe fire that is not also a p95 fire"


def test_rocx_top_control_band_is_disjoint_from_the_fire_band():
    C = _frame(_cycled(500) + SURGE + [0.0] * 20)
    L = R.rocx_top_legs(C)
    both = L["fire"].to_numpy() & L["control"].to_numpy()
    assert not bool(both.any()), "a bar is both an S-ROCX-TOP event and its own control"


# ─────────────────────────────────────────────────────────────────────────────
# 3. S-ROCW-GRAIN — washout WITH stabilization vs the same washout WITHOUT it
# ─────────────────────────────────────────────────────────────────────────────
def _saw(n: int) -> list[float]:
    r = [0.0]
    while len(r) < n:
        r += [0.01] * 10 + [-0.01] * 10
    return r[:n]


def _in_window(events, lo: int, hi: int) -> list[int]:
    return [int(e) for (_s, e, _low) in events if lo <= e <= hi]


# a 21-session washout, then a small bounce that clears the PRIOR CLOSE but stays far
# below the max of the prior five — the bar that separates a real stabilization from a
# single green day inside a decline.
WASHOUT = [-0.02] * 21 + [0.005, -0.005, -0.005]


def test_washout_fires_on_the_first_stabilization_bar():
    base = _saw(400)
    r = base + WASHOUT + [0.05] + [0.0] * 40
    bounce_bar = len(base) + 21            # up vs the prior close, still deep in the hole
    stab_bar = len(base) + len(WASHOUT)    # the injected +5% session
    px = _px(r)
    assert float(px.iloc[bounce_bar]) > float(px.iloc[bounce_bar - 1])
    assert float(px.iloc[bounce_bar]) < float(px.iloc[bounce_bar - 5:bounce_bar].max())
    ev = R.washout_events(px)
    hits = _in_window(ev["fire"], len(base), len(r) - 1)
    assert len(hits) == 1, f"expected exactly one injected washout event, got {hits}"
    assert hits[0] == stab_bar, (
        "the event must be the bar that cleared the prior FIVE closes; stamping the "
        f"single green day at {bounce_bar} means the lookback is not 5 sessions")
    assert float(px.iloc[stab_bar]) > float(px.iloc[stab_bar - 5:stab_bar].max())


def test_washout_does_not_fire_without_a_stabilization_inside_21_sessions():
    """MATCHED must-not-fire: same washout, but the decline simply continues.

    The step-1 leg is asserted to still fire, so the contrast is the stabilization step
    alone; and the events OUTSIDE the injected window must be identical in both fixtures,
    which proves the difference comes from the injection and not from a shifted history.
    """
    base = _saw(400)
    ok = base + WASHOUT + [0.05] + [0.0] * 40
    no = base + WASHOUT + [-0.01] * 30 + [0.0] * 20
    ev_ok = R.washout_events(_px(ok))
    ev_no = R.washout_events(_px(no))
    assert ev_no["n_step1_deep"] > 0, "the washout leg must still be on"
    assert _in_window(ev_no["fire"], 400, 466) == []
    before_ok = _in_window(ev_ok["fire"], 0, 399)
    before_no = _in_window(ev_no["fire"], 0, 399)
    assert before_ok == before_no, "the shared history must produce identical events"


def test_washout_controls_come_from_the_milder_decline_band():
    r = _saw(400) + WASHOUT + [0.05] + [0.0] * 40
    ev = R.washout_events(_px(r))
    assert ev["n_step1_mild"] > 0, "the control step-1 leg is dead — it must print, not vanish"
    fire_cells = {e for (_s, e, _l) in ev["fire"]}
    ctrl_cells = {e for (_s, e, _l) in ev["control"]}
    # overlap is legal at this grain (that is why disjoin() exists) but the arms must not
    # be the same set, or the control is not a control
    assert ctrl_cells != fire_cells


# ─────────────────────────────────────────────────────────────────────────────
# 4. S-BURST-RHYTHM — the burst / rest / break / no-rest grammar
# ─────────────────────────────────────────────────────────────────────────────
def test_burst_fires_after_a_rest_that_held():
    s = _px(_burst_rets(off_a_bottom=True, rest="hold"))
    ev = R.burst_events(s, s * 0.995)
    assert len(ev["fire"]) == 1, f"expected one burst fire, got {ev['fire']}"
    row = ev["fire"][0]
    assert row["event"] > row["b1"], "the fire must be stamped AFTER the B1 bar"
    assert 3 <= int(row["k"]) <= 6, "the fire is the session after a 2-5 session rest"
    assert ev["control_break"] == [] and ev["control_no_rest"] == []


def test_burst_does_not_fire_without_a_recent_63d_low():
    """MATCHED must-not-fire: identical burst and rest, but the run is NOT off a bottom."""
    s = _px(_burst_rets(off_a_bottom=False, rest="hold"))
    ev = R.burst_events(s, s * 0.995)
    assert ev["n_mover_bars"] > 0, "the burst-mover leg must still be on"
    assert ev["n_recent_low_bars"] == 0, "the 63d-low leg is what must be absent here"
    assert ev["n_b1_bars"] == 0
    assert ev["fire"] == []


def test_burst_rest_that_breaks_lands_in_control_arm_a_not_the_fire_arm():
    s = _px(_burst_rets(off_a_bottom=True, rest="break"))
    ev = R.burst_events(s, s * 0.995)
    assert ev["n_b1_bars"] > 0, "the B1 leg must still be on"
    assert ev["fire"] == [], "a rest that gave back >61.8% is not a fire"
    assert len(ev["control_break"]) == 1
    assert ev["control_break"][0]["event"] > ev["control_break"][0]["b1"]


def test_burst_no_rest_lands_in_control_arm_b():
    s = _px(_burst_rets(off_a_bottom=True, rest="none"))
    ev = R.burst_events(s, s * 0.995)
    assert ev["fire"] == [], "a burst that never rested is not a fire"
    assert len(ev["control_no_rest"]) == 1
    row = ev["control_no_rest"][0]
    assert row["event"] == row["b1"] + 6, "arm (b) is stamped the session after session 5"


# ─────────────────────────────────────────────────────────────────────────────
# 5. backward-only stamping + the positive control that keeps it honest
# ─────────────────────────────────────────────────────────────────────────────
def _mutate_after(s: pd.Series, cutoff: int, factor: float) -> pd.Series:
    out = s.copy()
    out.iloc[cutoff + 1:] = out.iloc[cutoff + 1:] * factor
    return out


def _lookahead_burst_events(close, low, peek: int = 3) -> dict:
    """A DELIBERATELY contaminated detector: it keeps a fire only if the price is higher
    `peek` bars LATER. Nothing but the future decides which events survive — exactly the
    W8 intersection-lookahead defect, in miniature."""
    ev = dict(R.burst_events(close, low))
    c = np.asarray(close, dtype=float)
    ev["fire"] = [r for r in ev["fire"]
                  if r["event"] + peek < len(c) and c[r["event"] + peek] > c[r["event"]]]
    return ev


def test_burst_stamping_is_backward_only():
    """Mutate every bar after a cutoff: no event stamped at or before it may move."""
    rets = _burst_rets(off_a_bottom=True, rest="hold", tail=0.01, tail_len=60)
    s = _px(rets)
    fires = R.burst_events(s, s * 0.995)["fire"]
    assert fires, "fixture must produce a fire to have anything to pin"
    cutoff = int(fires[0]["event"])
    for factor in (0.5, 1.8):
        s2 = _mutate_after(s, cutoff, factor)
        before = {c for c in _burst_cells(R.burst_events(s, s * 0.995)) if c[2] <= cutoff}
        after = {c for c in _burst_cells(R.burst_events(s2, s2 * 0.995)) if c[2] <= cutoff}
        assert before == after, (
            f"mutating bars after {cutoff} changed an event stamped at or before it "
            f"(factor={factor}): {before ^ after}")
        assert before, "the invariance check compared two empty sets — it proves nothing"


def test_the_backward_only_check_can_see_a_lookahead():
    """POSITIVE CONTROL. The same assertion, run against a detector that peeks forward,
    must FAIL. Without this the test above would pass on any implementation."""
    rets = _burst_rets(off_a_bottom=True, rest="hold", tail=0.01, tail_len=60)
    s = _px(rets)
    cutoff = int(R.burst_events(s, s * 0.995)["fire"][0]["event"])
    s2 = _mutate_after(s, cutoff, 0.5)
    before = {(r["b1"], r["event"]) for r in _lookahead_burst_events(s, s * 0.995)["fire"]
              if r["event"] <= cutoff}
    after = {(r["b1"], r["event"]) for r in _lookahead_burst_events(s2, s2 * 0.995)["fire"]
             if r["event"] <= cutoff}
    assert before != after, (
        "the lookahead detector survived the invariance check — the check is vacuous and "
        "cannot be used as evidence that the real detector is backward-only")


def test_rocx_top_legs_are_backward_only():
    """Same invariance, panel form: mutating the tail cannot change earlier fires."""
    C = _frame([0.0] + [0.002] * 460 + SURGE + [0.0] * 60)
    cutoff = C.shape[0] - 61
    C2 = C.copy()
    C2.iloc[cutoff + 1:, 0] = C2.iloc[cutoff + 1:, 0] * 0.6
    a = R.rocx_top_legs(C)["fire"].to_numpy()[:cutoff + 1]
    b = R.rocx_top_legs(C2)["fire"].to_numpy()[:cutoff + 1]
    assert bool(a.any()), "no fires before the cutoff — the check would be vacuous"
    assert np.array_equal(a, b)


# ─────────────────────────────────────────────────────────────────────────────
# 6. S-ROC12-TERM — the extreme at the highs vs the same extreme far below them
# ─────────────────────────────────────────────────────────────────────────────
def test_roc12_term_fires_at_an_extreme_near_the_63d_high():
    C = _frame(_cycled(420) + SURGE + [0.0] * 20)
    L = R.roc12_term_legs(C)
    bar = C.shape[0] - 21
    assert bool(L["legs"]["burst_mover_p97_roc5_ge_15pct"].iloc[bar, 0])
    assert bool(L["legs"]["within_5pct_of_63d_high"].iloc[bar, 0])
    assert bool(L["legs"]["roc12_ge_own_p99"].iloc[bar, 0])
    assert bool(L["fire"].iloc[bar, 0])


def test_roc12_term_does_not_fire_far_from_the_63d_high():
    """MATCHED must-not-fire: the same roc12 extreme, 20%+ below a recent 63d high."""
    C = _frame(_cycled(420) + [0.012] * 40 + [-0.03] * 20 + SURGE + [0.0] * 20)
    L = R.roc12_term_legs(C)
    bar = C.shape[0] - 21
    assert bool(L["legs"]["roc12_ge_own_p99"].iloc[bar, 0]), "the extreme leg must still be on"
    assert not bool(L["legs"]["within_5pct_of_63d_high"].iloc[bar, 0])
    assert not bool(L["fire"].iloc[bar, 0])


# ─────────────────────────────────────────────────────────────────────────────
# 7. visibility — a dead leg prints zero, a thin arm prints an explanation
# ─────────────────────────────────────────────────────────────────────────────
def test_leg_counts_reports_a_dead_leg_as_zero_not_as_a_missing_key():
    """A monotone decline can never satisfy the uptrend legs.

    Those legs must appear with 0 BESIDE a live leg. A results file that simply omits
    them reads as 'not applicable' when the truth is 'never fired', which is the whole
    failure mode this guards.
    """
    C = _frame([0.0] + [-0.002] * 500)
    L = R.rocx_top_legs(C)
    counts = R.leg_counts(L["legs"])
    assert set(counts) == set(L["legs"]), "leg_counts dropped a leg"
    assert counts["close_above_sma50"] == 0
    assert counts["sma50_rising_10"] == 0
    assert counts["uptrend_both_legs"] == 0
    assert counts["roc12_pctile_ge_0.95"] > 0, "the fixture must keep a live leg beside the dead"
    assert all(isinstance(v, int) for v in counts.values())


def test_leg_counts_is_zero_not_empty_when_every_leg_is_dead():
    dead = {k: pd.DataFrame(False, index=range(50), columns=["A", "B"])
            for k in ("leg_one", "leg_two", "leg_three")}
    counts = R.leg_counts(dead)
    assert set(counts) == set(dead), "a dead leg vanished from the count instead of printing 0"
    assert all(v == 0 for v in counts.values())


def test_thin_note_explains_instead_of_skipping():
    note = R.thin_note("control arm (b)", 3, "five strictly-rising roc5 readings are rare")
    assert note is not None and "n=3" in note and "rare" in note
    assert R.thin_note("healthy arm", R.MIN_CELL, "not needed") is None


# ─────────────────────────────────────────────────────────────────────────────
# 8. the ruler
# ─────────────────────────────────────────────────────────────────────────────
def test_matched_delta_subtracts_the_same_session_control_median():
    ev_vals = np.array([0.10, 0.20, 0.30])
    ev_ri = np.array([0, 1, 2])
    ct_vals = np.array([0.01, 0.03, 0.05, 0.20])       # session 0 -> median 0.03
    ct_ri = np.array([0, 0, 0, 1])                      # session 1 -> median 0.20
    d, ok = R.matched_delta(ev_vals, ev_ri, ct_vals, ct_ri, 3)
    assert ok.tolist() == [True, True, False], "an event with no same-session control must drop"
    assert d[0] == pytest.approx(0.07)
    assert d[1] == pytest.approx(0.00)


def test_disjoin_drops_control_cells_that_are_also_events():
    """The defect the first real run surfaced: shared cells enter the delta as exact 0."""
    ev = (np.array([1, 2, 3]), np.array([0, 0, 1]))
    ct = (np.array([1, 4, 3]), np.array([0, 0, 1]))     # (1,0) and (3,1) are also events
    (cri, cci), keep, removed = R.disjoin(ev, ct, n_cols=8)
    assert removed == 2
    assert cri.tolist() == [4] and cci.tolist() == [0]
    assert keep.tolist() == [False, True, False]


def test_disjoin_is_a_noop_when_the_arms_are_already_disjoint():
    ev = (np.array([1, 2]), np.array([0, 0]))
    ct = (np.array([5, 6]), np.array([0, 1]))
    (cri, _cci), _keep, removed = R.disjoin(ev, ct, n_cols=8)
    assert removed == 0 and cri.tolist() == [5, 6]


def test_block_boot_ci_is_none_below_min_cell_and_deterministic_above():
    rng = np.random.default_rng(0)
    v = rng.normal(1.0, 1.0, 600)
    keys = np.repeat(np.arange(20), 30)
    assert R.block_boot_ci(v[:5], keys[:5], 50, 1) is None
    a = R.block_boot_ci(v, keys, 200, 7)
    b = R.block_boot_ci(v, keys, 200, 7)
    assert a["ci95"] == b["ci95"], "the bootstrap must be seed-deterministic"
    assert a["blocks"] == 20
    lo, hi = a["ci95"]
    assert lo < 1.0 < hi, "a CI that excludes the true median of a clean fixture"


def test_block_boot_ci_drops_non_finite_values():
    v = np.concatenate([np.ones(200), np.full(50, np.nan)])
    keys = np.repeat(np.arange(25), 10)
    out = R.block_boot_ci(v, keys, 100, 3)
    assert out["ci95"] == [1.0, 1.0]


def test_verdict_labels_follow_the_ci():
    assert R._verdict_from_ci(100, [0.2, 0.9], 0.5)[0] == "POSITIVE"
    assert R._verdict_from_ci(100, [-0.9, -0.2], -0.5)[0] == "NEGATIVE"
    assert R._verdict_from_ci(100, [-0.9, 0.2], -0.1)[0] == "NULL"
    assert R._verdict_from_ci(5, [0.2, 0.9], 0.5)[0] == "THIN"
    assert R._verdict_from_ci(100, None, 0.5)[0] == "THIN"


# ─────────────────────────────────────────────────────────────────────────────
# 9. the fences the module is built around
# ─────────────────────────────────────────────────────────────────────────────
def test_module_docstring_carries_the_kill_fences_and_the_tier_statement():
    doc = (R.__doc__ or "").lower()
    for token in ("research / shadow", "zero authority", "pss-f1", "pss-f3", "pss-f4",
                  "row 78", "row 120", "row 116", "row 109", "pm4", "backward-only"):
        assert token in doc, f"the kill-fence/tier docstring lost: {token}"
    assert str(R.RHO_FENCE) in doc


def test_ext_z_matches_the_engine_construction():
    """The redundancy read must be measured against px/SMA200-1 z-scored over 252d, not
    against a lookalike — a different normalization would move the PM4 fence."""
    rng = np.random.default_rng(11)
    C = _frame(np.concatenate([[0.0], rng.normal(0.0005, 0.02, 600)]))
    z = R.ext_z(C)
    ext = C / C.rolling(200, min_periods=100).mean() - 1.0
    want = ((ext - ext.rolling(252, min_periods=120).mean())
            / ext.rolling(252, min_periods=120).std().replace(0, np.nan))
    pd.testing.assert_frame_equal(z, want)
    assert z.iloc[:99].isna().all().all()
