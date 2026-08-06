"""Donor-pool synthetic-control invariants (engine/synthetic_control.py + the phase-0 harness).

Fixture-only by construction: CI has no massive_stock_day parquets, so every test here
runs on synthetic factor-model panels. What is pinned is the part a results table cannot
show you —

  * RECOVERY: when the treated series really IS a convex mixture of two donors, the
    solver must return that mixture. This is the one case with a known right answer.
  * INJECTED TREATMENT: a +5% shock planted on the event day must come back out of the
    effect estimate, and must NOT leak into the neighbouring days' tau.
  * POINT-IN-TIME: perturbing every bar at or after t-EMBARGO must leave the fitted
    weights BIT-IDENTICAL. For the index-add family the announcement run-up is the
    effect being measured, so a pre-window that reached to t-1 would fit the donors to
    the leak and quietly estimate it away. This is the test that would catch that.
  * DONOR ADMISSION: each of the four exclusion rules must actually exclude, tested at
    the boundary (+/-21 sessions) so a one-session loosening fails rather than passes.
  * SIMPLEX: weights non-negative and summing to 1 — the constraint that makes them a
    portfolio rather than a regression.
  * NO MANUFACTURED EDGE: the full harness path (donor admission -> pre-screen -> fit ->
    counterfactual -> CAR), run at random dates on a panel with NO treatment anywhere,
    must return zero within its own sampling error. A harness that prints an effect on
    noise cannot be trusted to print a null on real data.

Run: pytest tests/test_synthetic_control.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import synthetic_control as sc  # noqa: E402
from scripts.synthetic_control_phase0 import (  # noqa: E402
    Panel, contamination_map, eligible_placebo_sessions, estimate_events,
)


# ------------------------------------------------------------------ fixtures
def _factor_panel(n_names: int = 120, n_sess: int = 600, seed: int = 11,
                  treat: tuple[int, int, float] | None = None) -> Panel:
    """A no-drift factor-model panel: r_i,t = beta_i * mkt_t + idio_i,t.

    Every name has zero expected return, so any non-zero aggregate effect the harness
    reports on this panel is manufactured by the harness. `treat` optionally plants
    (col, session, shock) — the injected-treatment fixture.
    """
    rng = np.random.default_rng(seed)
    mkt = rng.normal(0.0, 0.010, n_sess)
    beta = rng.uniform(0.6, 1.6, n_names)
    idio = rng.normal(0.0, 0.012, (n_sess, n_names))
    ret = beta[None, :] * mkt[:, None] + idio
    if treat is not None:
        col, sess, shock = treat
        ret[sess, col] += shock
    ret[0, :] = np.nan
    close = 100.0 * np.cumprod(1.0 + np.nan_to_num(ret), axis=0)
    dvol = np.full((n_sess, n_names), 50e6)
    dates = pd.bdate_range("2021-01-04", periods=n_sess)
    return Panel(dates, [f"N{i:03d}" for i in range(n_names)], ret, dvol, close)


def _events(cols, sessions) -> pd.DataFrame:
    return pd.DataFrame({"ticker": [f"N{c:03d}" for c in cols], "col": list(cols),
                         "sess": list(sessions),
                         "date": pd.bdate_range("2021-01-04", periods=600)[list(sessions)]})


# ------------------------------------------------------------------ (a) recovery
def test_solver_recovers_known_convex_mixture():
    """C = 0.6*A + 0.4*B  =>  weights [0.6, 0.4]. The one case with a known answer."""
    rng = np.random.default_rng(3)
    a = rng.normal(0, 0.02, 200)
    b = rng.normal(0, 0.02, 200)
    y = 0.6 * a + 0.4 * b
    w = sc.solve_simplex_ls(y, np.column_stack([a, b]))
    assert np.allclose(w, [0.6, 0.4], atol=1e-4), w


def test_solver_recovers_mixture_among_distractors():
    """The two real ingredients must win against 30 unrelated donors, not be smeared."""
    rng = np.random.default_rng(5)
    a = rng.normal(0, 0.02, 250)
    b = rng.normal(0, 0.02, 250)
    y = 0.6 * a + 0.4 * b
    d = np.column_stack([a, b] + [rng.normal(0, 0.02, 250) for _ in range(30)])
    w = sc.solve_simplex_ls(y, d)
    assert np.allclose(w[:2], [0.6, 0.4], atol=1e-3), w[:2]
    assert w[2:].max() < 1e-4, w[2:].max()


def test_donor_weights_end_to_end_recovers_mixture():
    """The public `donor_weights` entry point, not just the raw solver."""
    rng = np.random.default_rng(9)
    a = rng.normal(0, 0.02, 200)
    b = rng.normal(0, 0.02, 200)
    y = 0.6 * a + 0.4 * b
    d = np.column_stack([a, b] + [rng.normal(0, 0.02, 200) for _ in range(10)])
    w = sc.donor_weights(y, d, method="sc_nnls")
    assert w.shape == (12,)
    assert np.allclose(w[:2], [0.6, 0.4], atol=1e-3), w[:2]


def test_batch_matches_single_problem_solver():
    """The batched solver the study runs must equal the single-problem form it documents."""
    rng = np.random.default_rng(13)
    ys, ds = [], []
    for _ in range(6):
        d = rng.normal(0, 0.02, (120, 12))
        w = rng.dirichlet(np.ones(12))
        ys.append(d @ w + rng.normal(0, 0.001, 120))
        ds.append(d)
    batch = sc.solve_simplex_ls_batch(np.array(ys), np.array(ds))
    for i in range(6):
        one = sc.solve_simplex_ls(ys[i], ds[i])
        assert np.allclose(batch[i], one, atol=1e-8), (i, batch[i] - one)


# ------------------------------------------------------------------ (b) injected treatment
def _multi_event_panel(shock: float, seed: int = 55, n_ev: int = 120):
    """Same panel, `n_ev` treated (name, session) pairs, each carrying `shock` on day 0.

    Averaged over events because a SINGLE event's day-0 tau is dominated by that name's
    idiosyncratic draw (sd ~1.2% here) — a one-event tolerance would either be so wide it
    pins nothing or so tight it fails on noise. Recovery is a statement about the mean.
    """
    rng = np.random.default_rng(seed)
    cols = rng.choice(140, n_ev, replace=False)
    sess = rng.integers(sc.PRE_WINDOW + sc.EMBARGO + 5, 600 - 25, n_ev)
    base = _factor_panel(n_names=140, n_sess=600, seed=seed)
    ret = base.ret.copy()
    if shock:
        ret[sess, cols] += shock
    close = 100.0 * np.cumprod(1.0 + np.nan_to_num(ret), axis=0)
    panel = Panel(base.dates, base.tickers, ret, base.dvol20, close)
    return panel, _events(cols, sess)


def test_injected_treatment_is_recovered():
    """Plant +5% on the event day of 120 treated names; the mean effect must return it."""
    shock = 0.05
    panel, ev = _multi_event_panel(shock)
    est = estimate_events(panel, ev["col"].to_numpy(), ev["sess"].to_numpy(),
                          contamination_map(panel, ev, sc.EVENT_EXCLUSION))
    assert est["_n_live"] > 100, est["_n_live"]
    for key, tol_mult in (("0", 3.0), ("0_5", 3.0), ("0_20", 3.0)):
        v = est["sc_nnls"][:, est["_keys"].index(key)]
        v = v[np.isfinite(v)]
        se = v.std(ddof=1) / np.sqrt(v.size)
        assert abs(v.mean() - shock) < tol_mult * se, (
            f"{key}: recovered {v.mean():.5f} vs planted {shock} "
            f"({abs(v.mean() - shock) / se:.1f} sigma)")


def test_injected_treatment_does_not_leak_into_neighbouring_days():
    """A day-0 shock must not smear onto day 1+. If the pre-window or the counterfactual
    were misaligned by one session this is the test that fails."""
    col, sess, shock = 7, 300, 0.05
    treated = _factor_panel(treat=(col, sess, shock))
    clean = _factor_panel()
    ev = _events([col], [sess])
    cm = contamination_map(treated, ev, sc.EVENT_EXCLUSION)
    a = estimate_events(treated, ev["col"].to_numpy(), ev["sess"].to_numpy(), cm)
    b = estimate_events(clean, ev["col"].to_numpy(), ev["sess"].to_numpy(), cm)
    i0, i5 = a["_keys"].index("0"), a["_keys"].index("0_5")
    # the [0] and [0,5] deltas must both be ~the shock: everything after day 0 is unchanged
    assert abs((a["sc_nnls"][0, i0] - b["sc_nnls"][0, i0]) - shock) < 1e-9
    assert abs((a["sc_nnls"][0, i5] - b["sc_nnls"][0, i5]) - shock) < 1e-9


def test_no_treatment_gives_near_zero_effect():
    """The identical fixture with shock=0 must estimate ~0, so the recovery above is the
    planted shock and not the harness's own bias."""
    panel, ev = _multi_event_panel(0.0)
    est = estimate_events(panel, ev["col"].to_numpy(), ev["sess"].to_numpy(),
                          contamination_map(panel, ev, sc.EVENT_EXCLUSION))
    v = est["sc_nnls"][:, est["_keys"].index("0")]
    v = v[np.isfinite(v)]
    se = v.std(ddof=1) / np.sqrt(v.size)
    assert abs(v.mean()) < 3.0 * se, f"{v.mean():.5f} ({abs(v.mean()) / se:.1f} sigma)"


# ------------------------------------------------------------------ (c) PIT
def test_pit_perturbation_does_not_move_weights():
    """Perturbing EVERY bar at or after t-EMBARGO must leave the weights bit-identical.

    This is the law the index-add family depends on: the announcement run-up starts
    before the effective date, and a pre-window reaching to t-1 would fit the donors to
    the leak and estimate the effect away.
    """
    rng = np.random.default_rng(21)
    n_sess, n_names, t = 400, 60, 300
    ret = rng.normal(0, 0.02, (n_sess, n_names))
    sl = sc.pre_window_slice(t)
    w0 = sc.donor_weights(ret[sl, 0], ret[sl, 1:], method="sc_nnls")

    bad = ret.copy()
    bad[t - sc.EMBARGO:, :] += rng.normal(0, 0.5, bad[t - sc.EMBARGO:, :].shape)
    w1 = sc.donor_weights(bad[sl, 0], bad[sl, 1:], method="sc_nnls")
    assert np.array_equal(w0, w1), "post-embargo data moved the fitted weights"

    # ...and the window really is 120 long, ending at t-6 inclusive
    assert sl.stop == t - sc.EMBARGO
    assert sl.stop - sl.start == sc.PRE_WINDOW
    assert np.arange(n_sess)[sl].max() == t - sc.EMBARGO - 1 == t - 6


def test_pre_window_boundary_is_load_bearing():
    """Mutation guard: moving the window ONE session later (embargo 4 instead of 5) must
    change the fit on data that differs only at t-5. A test that passes under both
    boundaries would not be pinning the embargo at all."""
    rng = np.random.default_rng(22)
    n_sess, n_names, t = 400, 60, 300
    ret = rng.normal(0, 0.02, (n_sess, n_names))
    spiked = ret.copy()
    spiked[t - 5, :] += rng.normal(0, 0.5, n_names)   # the first EMBARGOED session

    sl_ok = sc.pre_window_slice(t)                    # ends t-6 -> spike excluded
    sl_loose = sc.pre_window_slice(t, embargo=4)      # ends t-5 -> spike included
    w_ok = sc.donor_weights(ret[sl_ok, 0], ret[sl_ok, 1:], method="sc_nnls")
    w_ok_spiked = sc.donor_weights(spiked[sl_ok, 0], spiked[sl_ok, 1:], method="sc_nnls")
    w_loose = sc.donor_weights(spiked[sl_loose, 0], spiked[sl_loose, 1:], method="sc_nnls")
    assert np.array_equal(w_ok, w_ok_spiked)          # correct boundary ignores the spike
    assert not np.allclose(w_ok, w_loose)             # loosened boundary does not


# ------------------------------------------------------------------ (d) donor admission
def _admission_inputs(n: int = 8, t_pre: int = 120, seed: int = 31):
    rng = np.random.default_rng(seed)
    pre = rng.normal(0, 0.02, (t_pre, n))
    dvol = np.full(n, 10e6)
    dist = np.full(n, np.inf)
    return pre, dvol, dist


def test_donor_exclusion_drops_the_treated_name():
    pre, dvol, dist = _admission_inputs()
    m = sc.eligible_donors(donor_pre=pre, donor_dvol=dvol, event_distance=dist, treated_col=3)
    assert not m[3] and m.sum() == 7


def test_donor_exclusion_liquidity_floor():
    pre, dvol, dist = _admission_inputs()
    dvol[2] = sc.DVOL_FLOOR - 1.0
    dvol[5] = sc.DVOL_FLOOR
    m = sc.eligible_donors(donor_pre=pre, donor_dvol=dvol, event_distance=dist)
    assert not m[2], "below-floor donor admitted"
    assert m[5], "exactly-at-floor donor refused"


def test_donor_exclusion_coverage_floor():
    pre, dvol, dist = _admission_inputs()
    pre[:13, 4] = np.nan          # 107/120 = 89.2% -> refused
    pre[:12, 6] = np.nan          # 108/120 = 90.0% -> admitted
    m = sc.eligible_donors(donor_pre=pre, donor_dvol=dvol, event_distance=dist)
    assert not m[4], "89% coverage donor admitted"
    assert m[6], "exactly-90% coverage donor refused"


def test_donor_exclusion_event_contamination_at_the_boundary():
    """A donor with its own event 21 sessions away is contaminated; 22 is clean. The
    boundary is what makes a one-session loosening fail."""
    pre, dvol, dist = _admission_inputs()
    dist[1] = sc.EVENT_EXCLUSION          # 21 -> refused
    dist[7] = sc.EVENT_EXCLUSION + 1      # 22 -> admitted
    m = sc.eligible_donors(donor_pre=pre, donor_dvol=dvol, event_distance=dist)
    assert not m[1], "donor with an event at +/-21 admitted"
    assert m[7], "donor with an event at +/-22 refused"


def test_donor_exclusion_drops_a_flat_donor():
    pre, dvol, dist = _admission_inputs()
    pre[:, 0] = 0.0
    m = sc.eligible_donors(donor_pre=pre, donor_dvol=dvol, event_distance=dist)
    assert not m[0], "a donor that never moves cannot be standardized or fitted"


def test_contamination_map_dilates_both_directions():
    """The harness's own contamination map, not just the engine predicate."""
    panel = _factor_panel(n_names=12, n_sess=200)
    ev = _events([3], [100])
    cm = contamination_map(panel, ev, sc.EVENT_EXCLUSION)
    assert cm[100, 3] and cm[100 - sc.EVENT_EXCLUSION, 3] and cm[100 + sc.EVENT_EXCLUSION, 3]
    assert not cm[100 - sc.EVENT_EXCLUSION - 1, 3]
    assert not cm[100 + sc.EVENT_EXCLUSION + 1, 3]
    assert not cm[:, 4].any(), "contamination leaked onto a name with no event"


# ------------------------------------------------------------------ (e) simplex
def test_weights_are_on_the_simplex():
    rng = np.random.default_rng(41)
    d = rng.normal(0, 0.02, (120, 40))
    y = rng.normal(0, 0.02, 120)
    for method in sc.METHODS:
        w = sc.donor_weights(y, d, method=method)
        assert (w >= -1e-12).all(), f"{method} produced a negative weight"
        assert abs(w.sum() - 1.0) < 1e-9, f"{method} weights sum to {w.sum()}"


def test_projection_is_an_exact_simplex_projection():
    rng = np.random.default_rng(43)
    v = rng.normal(0, 3.0, (25, 9))
    p = sc.project_to_simplex(v)
    assert np.allclose(p.sum(axis=1), 1.0)
    assert (p >= 0).all()
    # a point already on the simplex is its own projection
    q = rng.dirichlet(np.ones(9), size=25)
    assert np.allclose(sc.project_to_simplex(q), q, atol=1e-12)


def test_matched_k_is_top_k_of_the_prescreen():
    """The harness fills matched_k from the FIRST MATCHED_K columns of the M-wide
    pre-screen. That is only correct if the pre-screen returns correlation rank order —
    pinned here, because the harness's speed depends on it."""
    rng = np.random.default_rng(47)
    d = rng.normal(0, 0.02, (120, 80))
    y = rng.normal(0, 0.02, 120)
    top_m = sc.prescreen_donors(y, d, m=sc.PRESCREEN_M)
    top_k = sc.prescreen_donors(y, d, m=sc.MATCHED_K)
    assert np.array_equal(top_m[: sc.MATCHED_K], top_k)
    w = sc.donor_weights(y, d, method="matched_k")
    assert np.count_nonzero(w) == sc.MATCHED_K
    assert np.allclose(w[top_k], 1.0 / sc.MATCHED_K)


def test_counterfactual_renormalizes_over_live_donors():
    """A halted donor must not silently shrink the counterfactual toward zero."""
    w = np.array([0.5, 0.5])
    r = np.array([[0.02, 0.02], [0.04, np.nan]])
    path = sc.counterfactual_path(w, r)
    assert np.isclose(path[0], 0.02)
    assert np.isclose(path[1], 0.04), "NaN donor dragged the counterfactual down"


def test_effect_refuses_a_partial_window():
    """A window running past the supplied path must be NaN, not a partial sum presented
    as a full one."""
    out = sc.effect(np.zeros(6), np.zeros(6))
    assert np.isfinite(out["car"]["0"]) and np.isfinite(out["car"]["0_5"])
    assert not np.isfinite(out["car"]["0_20"])


# ------------------------------------------------------------------ (f) no manufactured edge
def test_placebo_machinery_returns_zero_on_a_no_effect_panel():
    """The FULL harness path at random dates on a panel with no treatment anywhere.

    This is the negative control for the whole study: if the harness prints an effect on
    noise, no null it prints on real data can be believed. Scored as a proper test of the
    mean against its own sampling error, not an eyeballed 'close to zero'.
    """
    panel = _factor_panel(n_names=140, n_sess=600, seed=101)
    rng = np.random.default_rng(202)
    cols = rng.integers(0, 140, 240)
    sess = rng.integers(sc.PRE_WINDOW + sc.EMBARGO, 600 - 21, 240)
    ev = _events(cols, sess)
    est = estimate_events(panel, ev["col"].to_numpy(), ev["sess"].to_numpy(),
                          contamination_map(panel, ev, sc.EVENT_EXCLUSION))
    assert est["_n_live"] > 150, est["_n_live"]
    for arm in ("sc_nnls", "matched_k"):
        for key in ("0", "0_5"):
            v = est[arm][:, est["_keys"].index(key)]
            v = v[np.isfinite(v)]
            se = v.std(ddof=1) / np.sqrt(v.size)
            assert abs(v.mean()) < 3.0 * se, (
                f"{arm}/{key} manufactured {v.mean():.5f} on a no-effect panel "
                f"({abs(v.mean()) / se:.1f} sigma)")


def test_placebo_dates_respect_the_guard_band():
    """A placebo date inside the guard band could contain the real effect."""
    panel = _factor_panel(n_names=20, n_sess=600)
    cand = eligible_placebo_sessions(panel, 0, 300)
    assert cand.size > 0
    assert np.abs(cand - 300).min() >= 42
    assert cand.min() >= sc.PRE_WINDOW + sc.EMBARGO
    assert cand.max() <= 600 - 21


def test_estimate_events_refuses_a_thin_donor_pool():
    """Fewer eligible donors than the pre-screen width must yield NO estimate rather
    than a quietly-narrower one."""
    panel = _factor_panel(n_names=30, n_sess=400)      # 30 < PRESCREEN_M = 50
    ev = _events([1], [300])
    est = estimate_events(panel, ev["col"].to_numpy(), ev["sess"].to_numpy(),
                          contamination_map(panel, ev, sc.EVENT_EXCLUSION))
    assert est["_n_live"] == 0
    assert not np.isfinite(est["sc_nnls"]).any()
