"""Unit tests for the per-leg not-topped veto isolation classifier.

Synthetic series and hand-built truth tables only — no repo data, no network.

Every test here is written to be able to SEE its failure. Where a test asserts an
absence ("the leg never fires below its warm-up", "no leg is dead"), it also asserts the
matching presence ("the leg DOES fire above it", "the alarm DOES name a zeroed leg"), so
a classifier that silently produced nothing would fail rather than pass vacuously.

Four claims are pinned:

  1. the sole-blocker predicate is EXACT — checked against the complete 16-row truth
     table of (stoch_ob, stoch_bear, macd_bear, tier_reachable), not a spot sample;
  2. removing a leg admits its sole-blocker cohort and NOTHING else (the identity the
     forfeiture pricing rests on);
  3. `macd_bear` cannot fire below its 232-bar warm-up (NaN < NaN is False), so the
     corrected slice must exclude those rows on the CONTROL side, where the fail-open
     actually lands;
  4. the fire-count diagnostic exposes a leg that never fires.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _load():
    """Import the instrument by path (it lives outside any package)."""
    cwd = os.getcwd()
    spec = importlib.util.spec_from_file_location(
        "veto_leg_isolation", Path(__file__).resolve().parent / "veto_leg_isolation.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # module chdir()s to REPO at import
    os.chdir(cwd)
    return mod


VLI = _load()


# --------------------------------------------------------------- fixtures --
def _walk(n=400, drift=0.0015, vol=0.014, seed=7, start_px=100.0,
          start="2022-01-03") -> pd.Series:
    """A drifting random walk — the minimum realistic fixture.

    A NOISELESS ramp is degenerate and must not be used: with no down-moves the Wilder
    RSI pins to a constant, StochRSI's (r-lo)/(hi-lo) divides by zero, and every
    oscillator leg goes NaN. That produces an all-dead panel that looks exactly like a
    broken classifier — the opposite of what these tests are for.
    """
    rng = np.random.default_rng(seed)
    r = drift + vol * rng.standard_normal(n)
    idx = pd.bdate_range(start, periods=n)
    return pd.Series(start_px * np.exp(np.cumsum(r)), index=idx)


#: the legs the truth-table fixture carries (the tier sub-legs are a build_panels
#: concern, not a cohort-algebra one).
GRID_LEGS = ("stoch_ob", "stoch_bear", "macd_bear", "tier_reachable", "eligible")


def _truth_table() -> dict:
    """The complete (ob, sb, mb, reach) grid as a one-column panels dict.

    The 16-row grid is TILED across both sides of the 232-bar warm-up, so every cohort —
    including the warm-up-restricted cuts — has at least one populated row on each side.
    A single-sided grid would leave `CONTROL:admitted_macd3_evaluated` empty and turn the
    partition assertions into vacuous passes.
    """
    grid = [(bool(a), bool(b), bool(c), bool(d))
            for a in (0, 1) for b in (0, 1) for c in (0, 1) for d in (0, 1)]
    rows = grid + grid
    bar_vals = ([VLI.MACD3_WARMUP + 10] * len(grid)) + ([VLI.MACD3_WARMUP - 10] * len(grid))
    ob = np.array([[r[0]] for r in rows])
    sb = np.array([[r[1]] for r in rows])
    mb = np.array([[r[2]] for r in rows])
    reach = np.array([[r[3]] for r in rows])
    bars = np.array([[b] for b in bar_vals])
    idx = pd.bdate_range("2024-01-01", periods=len(rows))
    mk = lambda a: pd.DataFrame(a, index=idx, columns=["T"])   # noqa: E731
    return {
        "stoch_ob": mk(ob), "stoch_bear": mk(sb), "macd_bear": mk(mb),
        "tier_reachable": mk(reach),
        "eligible": mk(~(ob | sb | mb) & reach),
        "bars": mk(bars),
        "has_px": mk(np.ones_like(ob, dtype=bool)),
        "_rows": rows,
    }


# ------------------------------------------------ 1. the predicate is exact --
def test_sole_blocker_predicate_matches_the_full_truth_table():
    p = _truth_table()
    rows = p["_rows"]
    coh = VLI._cohorts(p)

    want_ob = np.array([[a and not b and not c and d] for a, b, c, d in rows])
    want_sb = np.array([[b and not a and not c and d] for a, b, c, d in rows])
    want_mb = np.array([[c and not a and not b and d] for a, b, c, d in rows])
    want_ctl = np.array([[(not a) and (not b) and (not c) and d] for a, b, c, d in rows])

    np.testing.assert_array_equal(coh["SOLE:stoch_ob"], want_ob)
    np.testing.assert_array_equal(coh["SOLE:stoch_bear"], want_sb)
    np.testing.assert_array_equal(coh["SOLE:macd_bear"], want_mb)
    np.testing.assert_array_equal(coh["CONTROL:admitted"], want_ctl)

    # NON-VACUITY: each cohort must actually be populated on this grid, or the equality
    # assertions above would pass against four empty arrays.
    for k in ("SOLE:stoch_ob", "SOLE:stoch_bear", "SOLE:macd_bear", "CONTROL:admitted"):
        assert int(coh[k].sum()) > 0, f"{k} is empty on the truth table — test is vacuous"


def test_a_leg_firing_alongside_a_sibling_is_not_a_sole_blocker():
    """The predicate must be SOLE, not merely 'this leg fired'. Every co-firing row is
    excluded from every sole cohort."""
    p = _truth_table()
    coh = VLI._cohorts(p)
    ob = p["stoch_ob"].to_numpy()
    sb = p["stoch_bear"].to_numpy()
    mb = p["macd_bear"].to_numpy()
    co_firing = ((ob & sb) | (ob & mb) | (sb & mb))
    assert int(co_firing.sum()) > 0                      # the grid contains such rows
    for k in ("SOLE:stoch_ob", "SOLE:stoch_bear", "SOLE:macd_bear"):
        assert int((coh[k] & co_firing).sum()) == 0, f"{k} admits a co-firing row"


def test_the_three_sole_cohorts_are_pairwise_disjoint():
    coh = VLI._cohorts(_truth_table())
    a, b, c = (coh["SOLE:stoch_ob"], coh["SOLE:stoch_bear"], coh["SOLE:macd_bear"])
    assert int((a & b).sum()) == 0
    assert int((a & c).sum()) == 0
    assert int((b & c).sum()) == 0
    assert int((a & coh["CONTROL:admitted"]).sum()) == 0


# ---------------------------------------- 2. the forfeiture-pricing identity --
def test_removing_macd_bear_admits_exactly_the_sole_cohort_and_nothing_else():
    p = _truth_table()
    coh = VLI._cohorts(p)
    ob, sb, reach = (p["stoch_ob"].to_numpy(), p["stoch_bear"].to_numpy(),
                     p["tier_reachable"].to_numpy())
    # recompute eligibility with macd_bear switched OFF, from first principles
    elig_without = (~(ob | sb)) & reach
    added = elig_without & ~coh["CONTROL:admitted"]
    np.testing.assert_array_equal(added, coh["SOLE:macd_bear"])
    np.testing.assert_array_equal(coh["UNION:board_without_macd_bear"], elig_without)
    assert int(added.sum()) > 0            # non-vacuity: the grid does add rows


# ------------------------------------------------ 3. the warm-up fail-open ----
def test_admitted_control_splits_cleanly_at_the_warmup():
    p = _truth_table()
    coh = VLI._cohorts(p)
    ctl = coh["CONTROL:admitted"]
    warm = coh["CONTROL:admitted_macd3_evaluated"]
    fail = coh["CONTROL:admitted_macd3_FAILOPEN"]
    np.testing.assert_array_equal(warm | fail, ctl)      # partition
    assert int((warm & fail).sum()) == 0                 # disjoint
    assert int(warm.sum()) > 0 and int(fail.sum()) > 0   # both halves populated
    bars = p["bars"].to_numpy()
    assert bool((bars[fail] < VLI.MACD3_WARMUP).all())
    assert bool((bars[warm] >= VLI.MACD3_WARMUP).all())


def test_a_name_below_the_warmup_is_excluded_from_the_corrected_slice():
    p = _truth_table()
    coh = VLI._cohorts(p)
    bars = p["bars"].to_numpy()
    for k in ("CONTROL:admitted_macd3_evaluated", "SOLE:macd_bear_macd3_evaluated"):
        sel = coh[k]
        if int(sel.sum()) == 0:
            continue
        assert bool((bars[sel] >= VLI.MACD3_WARMUP).all()), \
            f"{k} carries a row below the {VLI.MACD3_WARMUP}-bar warm-up"
    assert int(coh["CONTROL:admitted_macd3_evaluated"].sum()) > 0


def test_macd_bear_reads_false_wherever_its_operands_are_unknown():
    """THE FAIL-OPEN, measured on a real series rather than quoted from the comment.

    NaN < NaN is False, so wherever the 3D RSI-MACD is not yet computable `macd_bear`
    reads 'not bearish' rather than 'not knowable'. That is the whole defect, and it is
    also why the SOLE:macd_bear cohort is automatically clean while the ADMITTED control
    is not.

    The last three assertions are what stop this passing vacuously: there must BE an
    unknown prefix, the leg must eventually become knowable, and it must actually fire
    somewhere once it is.
    """
    legs = VLI._name_legs(_walk(n=400))
    mb, known = legs["macd_bear"], legs["macd3_known"]

    assert not bool((mb & ~known).any()), "macd_bear fired where its operands are NaN"
    assert bool((~known).any()), "no unknown prefix on the fixture — test is vacuous"
    assert bool(known[-1]), "leg never becomes knowable — test is vacuous"
    assert bool(mb[known].any()), "macd_bear never fires where knowable — test is vacuous"


def test_the_232_bar_warmup_constant_is_the_engine_s_own_measurement():
    """Pin the constant by REPRODUCING the engine's stated method (l.54-59): truncate to
    N trailing daily bars on a pure business-day index (its worst-case basis) and ask
    whether the leg is non-NaN at the final bar. 232 must be the smallest such N.

    Reading the constant off the engine is not enough — a drifted warm-up would be
    imported silently. This test fails loudly if the leg's real requirement moves.
    """
    w = VLI.MACD3_WARMUP
    assert w == VLI.ct.LEG_WARMUP_BARS["m3_s3"]          # read, never restated
    c = _walk(n=w + 60, seed=5)                          # bdate_range = no holidays
    assert isinstance(c.index, pd.DatetimeIndex)

    def _known_at(n: int) -> bool:
        return bool(VLI._name_legs(c.iloc[-n:])["macd3_known"][-1])

    assert not _known_at(w - 1), f"3D RSI-MACD computable on only {w - 1} bars"
    assert _known_at(w), f"3D RSI-MACD still NaN on {w} bars"
    assert all(_known_at(n) for n in (w + 1, w + 5, w + 20)), \
        "warm-up is not monotone above the floor"


def test_the_failopen_band_sits_between_the_floor_and_the_warmup():
    """The band the packet quantifies is [MIN_HISTORY, 232) — non-empty on both the
    current floor and the pre-#4558 floor. If either range closed, the packet's
    contamination section would be about nothing."""
    assert VLI.ct.MIN_HISTORY < VLI.MACD3_WARMUP
    assert VLI.ct.YOUNG_HISTORY_BARS < VLI.MACD3_WARMUP
    assert VLI.ct.MIN_HISTORY <= VLI.ct.YOUNG_HISTORY_BARS


# ---------------------------------------------- 4. the dead-leg diagnostic ----
def test_dead_leg_alarm_names_a_leg_that_never_fires():
    p = _truth_table()
    diag = VLI.leg_diagnostics(p, legs=GRID_LEGS)
    assert diag["dead_legs"] == [], f"unexpected dead legs on the grid: {diag['dead_legs']}"

    # MUTATION: zero one leg and confirm the alarm SEES it. Without this the empty-list
    # assertion above would also pass on an alarm that can never fire.
    p["macd_bear"] = pd.DataFrame(np.zeros_like(p["macd_bear"].to_numpy(), dtype=bool),
                                  index=p["bars"].index, columns=["T"])
    diag2 = VLI.leg_diagnostics(p, legs=GRID_LEGS)
    assert "macd_bear" in diag2["dead_legs"]
    assert diag2["fire_counts_name_days"]["macd_bear"] == 0
    assert diag2["names_firing_at_least_once"]["macd_bear"] == 0


def test_every_veto_leg_is_covered_by_the_diagnostic():
    """A leg missing from DIAG_LEGS is invisible to the dead-leg alarm, so the alarm
    could not see it die."""
    for leg in ("stoch_ob", "stoch_bear", "macd_bear", "tier_reachable", "eligible"):
        assert leg in VLI.DIAG_LEGS


# ------------------------------------- 5. the factorisation the cohorts rest on --
def test_eligibility_factorises_into_veto_times_tier_reachable():
    legs = VLI._name_legs(_walk(n=400, seed=11))
    np.testing.assert_array_equal(
        legs["eligible"], legs["not_topped"] & legs["tier_reachable"])
    # DISCRIMINATION: tier_reachable must differ from eligible somewhere, otherwise the
    # equality above is trivially true and the counterfactual "switch the veto off"
    # would be a no-op.
    assert int((legs["tier_reachable"] & ~legs["eligible"]).sum()) > 0


def test_inline_legs_reproduce_the_production_tier_stream():
    """The claim the whole instrument rests on, pinned rather than asserted."""
    c = _walk(n=400, seed=3)
    legs = VLI._name_legs(c)
    st = VLI.ct.tier_stream(c)
    assert not st.empty, "tier_stream returned nothing — the comparison would be vacuous"
    nt = st["not_topped"].reindex(c.index).fillna(False).to_numpy().astype(bool)
    el = st["eligible"].reindex(c.index).fillna(False).to_numpy().astype(bool)
    np.testing.assert_array_equal(legs["not_topped"], nt)
    np.testing.assert_array_equal(legs["eligible"], el)
    assert int(el.sum()) > 0, "no eligible day on the fixture — the comparison is weak"


# ------------------------------------------------------------- 6. house traps --
def test_numpy_bool_is_true_trap():
    """`x is True` on a numpy bool is ALWAYS False (memory:
    numpy-bool-is-true-deadens-a-feature-leg). Every truth test in the instrument goes
    through bool()/==, so a numpy-typed leg is never silently dropped."""
    v = VLI._cohorts(_truth_table())["SOLE:macd_bear"].any()
    assert (v is True) is False           # the trap itself
    assert bool(v) is True                # the idiom the instrument uses


def test_stats_block_thin_flag_and_loser_threshold():
    ex = np.array([-5.0, -4.0, 1.0, 2.0, 3.0])
    blk = VLI.stats_block(ex, ex, ["A", "A", "B", "B", "C"])
    assert blk["n"] == 5 and blk["names"] == 3
    assert blk["thin"] is True and "n=5" in blk["thin_note"]
    assert blk["loser_rate_pct"] == pytest.approx(40.0)      # two rows below -3pp
    assert VLI.LOSER_PP == -3.0                              # the STATED definition
    big = np.zeros(50)
    assert "thin" not in VLI.stats_block(big, big, ["A"] * 50)


def test_half_split_reports_unrunnable_on_a_single_date():
    """A cohort drawn from one session cannot be half-split; saying 'stable' there would
    be a vacuous pass."""
    d = [pd.Timestamp("2026-01-05")] * 6
    out = VLI.half_split(d, np.zeros(6), np.zeros(6), ["A"] * 6)
    assert "UNRUNNABLE" in out["note"]
