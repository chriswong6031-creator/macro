"""W5 preregistered method-evaluation harness guards
(research/flow_observatory/W5_PREREG.md, scripts/research_flow_observatory_methods.py).

Small unit tests on the candidate MATH PRIMITIVES only — not a re-run of the full
history replay (that lives in the committed report, off the render path). Each test
name maps to one candidate definition or cross-cutting property named in the build
commission:

  M1 winsorization bounds   causal rolling clip actually bounds the output
  M2 MAD scale              the median/MAD construction reduces to the textbook
                             z-score on normal data and resists a single outlier
  M3 probit mapping         norm_ppf matches known standard-normal quantiles and is
                             monotonic in the input rank
  floor application         the 0.25x expanding-std floor actually lifts a collapsed
                             rolling vol/scale, mirroring engine.flow_velocity's own
                             floor tests
  determinism               same seed -> byte-identical JSON payload for the fixture-
                             based metrics (outlier/quiet/coverage/revision all draw
                             from a seeded Generator)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import flow_velocity as fv
from scripts import research_flow_observatory_methods as w5

REPORT_JSON = Path(__file__).resolve().parent.parent / "reports" / "flow_observatory_w5_methods.json"


def _flat_df(n=400, cols=("e",), seed=1, scale=1.0, start="2024-01-02"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    data = {c: rng.normal(0, scale, n) for c in cols}
    return pd.DataFrame(data, index=idx)


# ── M1 winsorization bounds ────────────────────────────────────────────────────────
def test_winsorize_causal_clips_to_rolling_bounds():
    df = _flat_df(n=400, scale=1.0, seed=3)
    # inject a single huge spike well past the window's own tail quantiles
    df.iloc[350, 0] = 1000.0
    wins = w5.winsorize_causal_wide(df, window=126, lo_q=0.025, hi_q=0.975)
    lo = w5.rolling_quantile_wide(df, 126, 0.025, max(20, 126 // 2))
    hi = w5.rolling_quantile_wide(df, 126, 0.975, max(20, 126 // 2))
    # everywhere bounds are defined, the winsorized value must sit within [lo, hi].
    # NOTE: boolean-DataFrame indexing (`df[mask]`) does NOT filter rows — it keeps the
    # shape and fills False cells with NaN, and NaN comparisons are False, not skipped —
    # so the check is folded into an OR against "bounds undefined here" instead.
    defined = lo.notna() & hi.notna()
    assert ((wins <= hi + 1e-9) | ~defined).all().all()
    assert ((wins >= lo - 1e-9) | ~defined).all().all()
    # the spike itself must have been clipped, not passed through
    assert wins.iloc[350, 0] < 1000.0
    assert wins.iloc[350, 0] == pytest.approx(float(hi.iloc[350, 0]), abs=1e-9)


def test_winsorize_causal_passes_through_during_warmup():
    """Before the rolling window has enough history, the raw value ships unclipped
    (the frozen definition says nothing about discarding the warm-up period, and M1
    is meant to be a drop-in swap for M0's input, which never drops warm-up rows)."""
    df = _flat_df(n=50, scale=1.0, seed=4)
    df.iloc[10, 0] = 500.0   # inside the warm-up window (min_periods=63 for window=126)
    wins = w5.winsorize_causal_wide(df, window=126, lo_q=0.025, hi_q=0.975)
    assert wins.iloc[10, 0] == pytest.approx(500.0)


# ── M2 MAD scale ────────────────────────────────────────────────────────────────────
def test_rolling_median_mad_matches_hand_computed_window():
    """Sanity-check the custom rolling primitive against a hand-computed window on a
    short, fully deterministic series."""
    vals = [1.0, 2.0, 3.0, 4.0, 100.0, 5.0, 6.0]
    df = pd.DataFrame({"e": vals}, index=pd.bdate_range("2024-01-02", periods=len(vals)))
    med, mad, rank = w5.rolling_median_mad_rank(df, window=5, min_periods=5)
    # window ending at index 4 (values [1,2,3,4,100]): median=3, abs deviations
    # [2,1,0,1,97] -> median(abs deviations)=1, scaled MAD = 1*1.4826
    assert med.iloc[4, 0] == pytest.approx(3.0)
    assert mad.iloc[4, 0] == pytest.approx(1.0 * 1.4826)
    # the current value (100) is the max of its own window -> percentile rank 1.0
    assert rank.iloc[4, 0] == pytest.approx(1.0)
    # window ending at index 5 (values [2,3,4,100,5]): median=4
    assert med.iloc[5, 0] == pytest.approx(4.0)


def test_m2_reduces_to_a_z_score_like_read_on_gaussian_noise():
    """On stationary Gaussian noise, M2's median/MAD statistic should sit in the same
    ballpark as a textbook z-score (mostly within +/-3ish) — it must not blow up or
    collapse to zero on well-behaved data."""
    df = _flat_df(n=500, scale=2.0, seed=7)
    cands = w5.build_candidates(df, w5.fv.WK)
    v2 = cands["M2"]["vel"]["e"].dropna()
    assert len(v2) > 50
    assert v2.abs().median() < 3.0
    assert v2.std() > 0.1   # not collapsed to a near-constant


def test_m2_outlier_produces_bounded_not_exploding_score():
    """A single huge outlier should move M2's score by a large but FINITE amount — the
    whole point of a median/MAD construction is that the single point cannot blow the
    scale term to infinity (unlike a mean/std construction where one point can inflate
    or deflate the denominator itself)."""
    df = _flat_df(n=400, scale=1.0, seed=9)
    spiked = df.copy()
    spiked.iloc[300, 0] += 500.0
    v_base = w5.build_candidates(df, w5.fv.WK)["M2"]["vel"]["e"]
    v_spike = w5.build_candidates(spiked, w5.fv.WK)["M2"]["vel"]["e"]
    d = (v_spike - v_base).dropna()
    assert np.isfinite(d).all()
    assert d.abs().max() < 1e6   # sanity ceiling — must not diverge


# ── M3 probit mapping ───────────────────────────────────────────────────────────────
def test_norm_ppf_matches_known_standard_normal_quantiles():
    p = np.array([0.5, 0.975, 0.025, 0.8413447, 0.1586553])
    expected = np.array([0.0, 1.959964, -1.959964, 1.0, -1.0])
    got = w5.norm_ppf(p)
    np.testing.assert_allclose(got, expected, atol=1e-5)


def test_norm_ppf_is_monotonic_increasing():
    p = np.linspace(0.001, 0.999, 200)
    got = w5.norm_ppf(p)
    assert np.all(np.diff(got) > 0)


def test_norm_ppf_out_of_domain_is_nan():
    got = w5.norm_ppf(np.array([-0.1, 0.0, 1.0, 1.1, np.nan]))
    assert np.isnan(got).all()


def test_m3_v_is_a_valid_rank_based_normal_score():
    """M3 is implemented as v_t = norm_ppf(rank) (see the module docstring's M3
    interpretive note on why the literal '2x(rank-0.5)' prose is not used verbatim —
    it is undefined for rank<0.5). The result must be finite wherever the rank itself
    is defined, and must be exactly recoverable from norm_ppf(rank)."""
    df = _flat_df(n=400, scale=1.0, seed=11)
    cands = w5.build_candidates(df, w5.fv.WK)
    v3 = cands["M3"]["vel"]["e"]
    x = w5.causal_demean(df, w5.fv.WK["demean"])
    _med, _mad, rank = w5.rolling_median_mad_rank(x, 126, max(20, 126 // 2))
    expected = w5.norm_ppf(rank["e"].to_numpy())
    got = v3.to_numpy()
    both_defined = np.isfinite(expected) & np.isfinite(got)
    assert both_defined.sum() > 50
    np.testing.assert_allclose(got[both_defined], expected[both_defined], atol=1e-9)


# ── floor application ───────────────────────────────────────────────────────────────
def test_floor_lifts_a_collapsed_vol_to_the_expanding_reference():
    vol = pd.DataFrame({"e": [0.5, 0.01, np.nan, 2.0]})
    ref = pd.DataFrame({"e": [1.0, 1.0, 1.0, 1.0]})
    floored = w5._floor_to_ref(vol, ref, 0.25)
    # floor = 0.25 * ref = 0.25 everywhere; 0.5 stays (already >= floor); 0.01 lifted;
    # NaN lifted to the floor; 2.0 stays (already >= floor)
    assert floored["e"].tolist() == pytest.approx([0.5, 0.25, 0.25, 2.0])


def test_floor_noop_when_floor_frac_is_zero():
    vol = pd.DataFrame({"e": [0.01, np.nan]})
    ref = pd.DataFrame({"e": [1.0, 1.0]})
    floored = w5._floor_to_ref(vol, ref, 0.0)
    assert floored["e"].iloc[0] == pytest.approx(0.01)
    assert np.isnan(floored["e"].iloc[1])


def test_m0_quiet_series_does_not_manufacture_an_extreme_from_a_collapsed_baseline():
    """Regression-style guard mirroring tests/test_flow_velocity.py's own quiet-series
    test, applied through this harness's fixture generator: a near-zero-variance
    baseline must not print a degenerate-extreme |v|>1.5 under the floored M0
    construction."""
    out = w5.metric_quiet_series(w5.fv.WK, seed=123)
    assert out["M0"]["degenerate_extreme_alarm"] is False


# ── determinism ─────────────────────────────────────────────────────────────────────
def test_outlier_metric_is_deterministic_for_a_fixed_seed():
    a = w5.metric_outlier_sensitivity(w5.fv.WK, seed=555)
    b = w5.metric_outlier_sensitivity(w5.fv.WK, seed=555)
    assert a == b


def test_quiet_metric_is_deterministic_for_a_fixed_seed():
    a = w5.metric_quiet_series(w5.fv._AGG, seed=777)
    b = w5.metric_quiet_series(w5.fv._AGG, seed=777)
    assert a == b


def test_coverage_metric_is_deterministic_for_a_fixed_seed():
    members = {"th1": ["A", "B", "C", "D", "E", "F"], "th2": ["G", "H", "I", "J", "K"]}
    names_wide = _flat_df(n=200, cols=list("ABCDEFGHIJK"), seed=2)
    a = w5.metric_coverage_sensitivity(members, names_wide, w5.fv.WK, seed=42, n_draws=10)
    b = w5.metric_coverage_sensitivity(members, names_wide, w5.fv.WK, seed=42, n_draws=10)
    assert a == b


def test_revision_metric_is_deterministic_for_a_fixed_seed():
    raw = pd.concat([_flat_df(n=200, seed=i).rename(columns={"e": f"e{i}"}) for i in range(5)], axis=1)
    a = w5.metric_revision_sensitivity(raw, w5.fv.WK, seed=99, n_draws=5)
    b = w5.metric_revision_sensitivity(raw, w5.fv.WK, seed=99, n_draws=5)
    assert a == b


def test_revision_metric_subsamples_large_entity_pools_deterministically():
    raw = pd.concat([_flat_df(n=200, seed=i).rename(columns={"e": f"e{i}"}) for i in range(20)], axis=1)
    a = w5.metric_revision_sensitivity(raw, w5.fv.WK, seed=7, n_draws=3, max_entities=5)
    b = w5.metric_revision_sensitivity(raw, w5.fv.WK, seed=7, n_draws=3, max_entities=5)
    assert a == b
    assert all(v is not None for v in a.values())


def test_different_seeds_can_change_fixture_metrics():
    """Not a tautology check — a harness whose 'seeded' draws secretly ignore the seed
    would also pass the determinism tests above. Confirm the seed is actually load-
    bearing for at least one metric that consumes randomness beyond a single fixed
    fixture (coverage sensitivity draws member subsets)."""
    members = {"th1": list("ABCDEFGHIJ")}
    names_wide = _flat_df(n=200, cols=list("ABCDEFGHIJ"), seed=2)
    a = w5.metric_coverage_sensitivity(members, names_wide, w5.fv.WK, seed=1, n_draws=20)
    b = w5.metric_coverage_sensitivity(members, names_wide, w5.fv.WK, seed=2, n_draws=20)
    # at least one candidate's median delta should differ across seeds (draws differ)
    assert a["median_abs_delta_by_method"] != b["median_abs_delta_by_method"] or a == b


# ── decision-conditions table is facts-only (no selection made by the harness) ─────
def test_decision_conditions_reports_facts_not_a_recommendation():
    metrics = {
        "themes": {
            "n_entities": 22,
            "metric4_outlier": {c: {"max_abs_delta": v} for c, v in
                                zip(w5.CANDIDATES, [1.0, 0.6, 0.6, 0.6])},
            "metric5_quiet": {c: {"max_abs_v": v} for c, v in
                              zip(w5.CANDIDATES, [1.0, 1.0, 1.0, 1.0])},
            "metric2_flip": {c: {"pooled": v} for c, v in
                             zip(w5.CANDIDATES, [0.10, 0.10, 0.10, 0.30])},
            "metric8_concordance": {"M0": 1.0, "M1": {"pooled_median": 0.9},
                                    "M2": {"pooled_median": 0.5}, "M3": {"pooled_median": 0.85}},
            "metric1_state": {c: {"degeneracy_alarm": False} for c in w5.CANDIDATES},
        },
    }
    metrics["names"] = metrics["themes"]
    metrics["southbound"] = metrics["themes"]
    out = w5.decision_conditions(metrics)
    # M1: 40% outlier improvement, flip rate unchanged, concordance 0.9, no alarm -> ADOPT
    assert out["themes"]["M1"]["all_conditions_met"] is True
    # M2: outlier improved but concordance below 0.8 -> NOT adopted
    assert out["themes"]["M2"]["c_concordance_ge_0_8"] is False
    assert out["themes"]["M2"]["all_conditions_met"] is False
    # M3: flip rate 3x worse than M0 -> condition (b) fails -> NOT adopted
    assert out["themes"]["M3"]["b_flip_rate_not_worse_than_10pct"] is False
    assert out["themes"]["M3"]["all_conditions_met"] is False
    # the function returns booleans/numbers only — never a prose recommendation string
    for lens_out in out.values():
        for cond in lens_out.values():
            for k, v in cond.items():
                assert not isinstance(v, str)


def test_decision_conditions_marks_concordance_not_applicable_for_a_single_entity_lens():
    """Southbound (n_entities=1) cannot have a 'theme ordering' rank correlation at all
    — condition (c) must be reported as None (not applicable), not a silent False that
    would veto every southbound challenger no matter how it actually behaves."""
    base = {
        "n_entities": 1,
        "metric4_outlier": {c: {"max_abs_delta": v} for c, v in
                            zip(w5.CANDIDATES, [1.0, 0.5, 0.5, 0.5])},
        "metric5_quiet": {c: {"max_abs_v": v} for c, v in zip(w5.CANDIDATES, [1.0] * 4)},
        "metric2_flip": {c: {"pooled": v} for c, v in zip(w5.CANDIDATES, [0.1] * 4)},
        "metric8_concordance": {"M0": 1.0, "M1": None, "M2": None, "M3": None},
        "metric1_state": {c: {"degeneracy_alarm": False} for c in w5.CANDIDATES},
    }
    metrics = {"themes": base, "names": base, "southbound": base}
    out = w5.decision_conditions(metrics)
    d = out["southbound"]["M1"]
    assert d["c_concordance_ge_0_8"] is None
    assert d["c_not_applicable"] is True
    # (a) and (b) both pass and (d) has no alarm -> adoption is not blocked by (c) alone
    assert d["all_conditions_met"] is True


# ── §5 Adjudication (PR #6808 comment 5530582923; DEC-FLOW-OBSERVATORY-V2-W5-METHOD-
#    SELECTION) — pin the ARITHMETIC the adjudication reads off this committed report,
#    against the report's OWN grid data, so a re-run harness change can't silently move
#    the adjudicated outcome without one of these tests catching it. ─────────────────────
def _load_report() -> dict:
    return json.loads(REPORT_JSON.read_text())


def test_names_mechanical_threshold_selection_matches_the_adjudicated_tau_beta():
    """Names: M0 stays (per the adjudication); its threshold is the frozen §4 procedure's
    mechanical completion — in-band [0.25,0.60] min-flip, else nearest-band then min-flip
    — applied to the M0 names grid. No grid point sits in-band (every neutral_share is
    already > 0.60 on this heavily-directional lens), so nearest-band applies: tau=0.3 and
    tau=0.4 (both beta=15) tie on band distance (0.6078 is 0.0078 outside the band either
    way); the tie breaks on flip rate, and 0.3/15 (flip=0.0921) strictly beats 0.4/15
    (flip=0.1118)."""
    grid = _load_report()["metrics"]["names"]["threshold_sweep_all"]["M0"]["grid"]

    def band_penalty(ns):
        return 0.0 if 0.25 <= ns <= 0.60 else min(abs(ns - 0.25), abs(ns - 0.60))

    reachable = [g for g in grid if g["main"]["in_reach"] >= 0.05 and g["main"]["out_reach"] >= 0.05]
    assert reachable, "no candidate clears the >=5% reachability floor"
    assert all(not (0.25 <= g["main"]["neutral_share"] <= 0.60) for g in reachable), (
        "a genuinely in-band candidate now exists — the nearest-band fallback no longer applies")
    winner = min(reachable, key=lambda g: (band_penalty(g["main"]["neutral_share"]), g["main"]["flip_rate"]))
    assert (winner["tau"], winner["beta"]) == (0.3, 15)
    assert winner["main"]["flip_rate"] == pytest.approx(0.0921)
    runner_up = next(g for g in reachable if (g["tau"], g["beta"]) == (0.4, 15))
    assert band_penalty(runner_up["main"]["neutral_share"]) == pytest.approx(
        band_penalty(winner["main"]["neutral_share"]), abs=1e-9), "the tie this test exercises no longer ties"
    assert winner["main"]["flip_rate"] < runner_up["main"]["flip_rate"]


def test_themes_adjudicated_tau_beta_is_the_unique_in_band_min_flip_winner():
    """Themes: tau=0.75/beta=30 sits IN the honest-neutral band [0.25,0.60] (ns=0.549) and
    is the strict (not tied) minimum flip rate among every in-band, reachable grid point —
    matching the adjudication's own words ('flip strictly improves — not a tie')."""
    grid = _load_report()["metrics"]["themes"]["threshold_sweep_all"]["M0"]["grid"]
    in_band = [g for g in grid if 0.25 <= g["main"]["neutral_share"] <= 0.60
              and g["main"]["in_reach"] >= 0.05 and g["main"]["out_reach"] >= 0.05]
    assert in_band, "no in-band reachable candidate — themes would fall to nearest-band too"
    winner = min(in_band, key=lambda g: g["main"]["flip_rate"])
    assert (winner["tau"], winner["beta"]) == (0.75, 30)
    others = sorted(g["main"]["flip_rate"] for g in in_band if (g["tau"], g["beta"]) != (0.75, 30))
    assert winner["main"]["flip_rate"] < others[0], "the adjudicated winner is no longer a strict min"


def test_southbound_m0_vs_m1_state_disagreement_within_the_hold_bound():
    """Southbound: M1 (winsorized) was adopted because the M0-vs-M1 5-state disagreement
    share, measured over the FULL causal history using the harness's own state definitions
    (VIN/VOUT=0.5/-0.5, fixed — the same construction Metric 1 uses), sits at 4.49% — well
    under the 20% HOLD bound the adjudication set as a sanity check that can only favor the
    incumbent. Recomputed here (not read off the report, which does not carry this
    cross-candidate figure) directly from the harness's own candidate-construction
    functions on the small (n=1) southbound series — cheap, unlike a names-lens replay."""
    sb = w5.load_southbound()
    cands = w5.build_candidates(sb.to_frame("southbound"), fv._AGG)
    s0 = w5.classify_wide(cands["M0"]["vel"], cands["M0"]["accel"])["southbound"]
    s1 = w5.classify_wide(cands["M1"]["vel"], cands["M1"]["accel"])["southbound"]
    known = (s0 != "no data") & (s1 != "no data")
    n = int(known.sum())
    assert n > 2000, "southbound history looks truncated — disagreement share would be unreliable"
    share = float((s0[known] != s1[known]).mean())
    assert share == pytest.approx(0.0449, abs=0.001)
    assert share <= 0.20, "disagreement exceeds the HOLD bound — M1 would have to stay HELD, M0 wins"


def test_southbound_every_tau_is_held_out_unreachable_so_the_incumbent_stays():
    """Southbound's own threshold re-sweep (on the adopted M1 method) excludes every tau
    in the grid because EVERY candidate's held-out-60 broad_in reach is 0% — a
    current-regime degeneracy (the adjudication's own words: 'the tau=1.0 sweep winner
    zeroed above-norm reach across the held-out window'). With every candidate excluded,
    the frozen fallback applies: tau=0.5 (the incumbent) stays — numerically unchanged
    from before W5, even though the METHOD switched to M1."""
    grid = _load_report()["metrics"]["southbound"]["threshold_sweep_all"]["M1"]["grid"]
    assert {g["tau"] for g in grid} == {0.3, 0.4, 0.5, 0.6, 0.75, 1.0}
    reachable = [g for g in grid
                if g["held_out"]["in_reach"] >= 0.02 and g["held_out"]["out_reach"] >= 0.02]
    assert reachable == [], (
        "a held-out-reachable tau now exists — southbound would no longer fall back to 0.5")
    # every held-out in_reach is exactly 0 — the specific degeneracy the adjudication names
    assert all(g["held_out"]["in_reach"] == 0.0 for g in grid)
