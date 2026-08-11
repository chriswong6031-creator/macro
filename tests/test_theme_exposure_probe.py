"""GMI W2 — pure-math pins for the exposure-decomposition probe.

Fixture-only: every input below is synthetic and every expectation is a closed form or a
constant. Nothing here reads `data/`, so the suite is reproducible on a runner that cannot
see the local-only stores the probe itself reads, and nothing here can age — no assertion
is a function of the wall clock (a test whose fixtures age is a scheduled red).

The functions pinned here are the ones a wrong answer would travel through silently: the
beta estimator and its causal shift, the ex-self basket return, the share denominator
(including the zero-denominator month that must NEVER become a division), the coverage
floor, the era label on backcast rows, and the small-N Spearman with ties.

Run: TZ=UTC python -m pytest tests/test_theme_exposure_probe.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

from engine.cn_global_beta import _causal_beta as INCUMBENT_CAUSAL_BETA
from scripts.probe_theme_exposure_axes import (
    BETA_ID,
    BETA_MINP,
    BETA_WIN,
    BOOTSTRAP_BLOCK,
    CN_LHB_ID,
    COVERAGE_FLOOR,
    OBSERVED_ERA_FROM,
    active_members,
    block_bootstrap_median_ci,
    causal_beta_pair,
    cell_abstains,
    corr_cell_from_beta_rows,
    coverage_fraction,
    draft_verdicts,
    era_for_month,
    ex_self_returns,
    h2_reading,
    h3_reading,
    monthly_count,
    shares_from_magnitudes,
    spearman_exact,
    spearman_rho,
    vasicek_shrink,
    window_overlap_sessions,
)

DATES = pd.date_range("2024-01-01", periods=200, freq="B")


def _synthetic_pair(slope: float = 2.5, seed: int = 7):
    """x, y = a + slope*x + deterministic noise. Seeded — the fixture never varies."""
    rng = np.random.default_rng(seed)
    x = pd.Series(rng.normal(0.0, 0.01, len(DATES)), index=DATES)
    y = pd.Series(0.0003 + slope * x.values + rng.normal(0.0, 0.002, len(DATES)), index=DATES)
    return x, y


def _ols_slope(y: pd.Series, x: pd.Series) -> float:
    return float(np.cov(y.values, x.values, ddof=1)[0, 1] / np.var(x.values, ddof=1))


# =====================================================================================
# trading_beta.v0 — the estimator, its window, and its causal shift
# =====================================================================================
class TestCausalBeta:
    def test_matches_the_closed_form_ols_slope_over_the_prior_window(self):
        x, y = _synthetic_pair()
        beta = causal_beta_pair(y, x)
        i = 120
        # .shift(1) means the value stamped at i is computed from rows [i-BETA_WIN, i-1].
        win_y, win_x = y.iloc[i - BETA_WIN:i], x.iloc[i - BETA_WIN:i]
        assert len(win_x) == BETA_WIN
        assert beta.iloc[i] == pytest.approx(_ols_slope(win_y, win_x), rel=1e-12)

    def test_recovers_the_true_slope_when_the_relationship_is_exact(self):
        x = pd.Series(np.linspace(-0.05, 0.05, len(DATES)), index=DATES)
        y = 3.25 * x
        assert causal_beta_pair(y, x).iloc[150] == pytest.approx(3.25, rel=1e-9)

    def test_is_causally_shifted_so_the_stamp_day_cannot_enter_its_own_estimate(self):
        x, y = _synthetic_pair()
        i = 120
        base = causal_beta_pair(y, x).iloc[i]

        same_day = y.copy()
        same_day.iloc[i] = same_day.iloc[i] + 10.0        # the stamp day itself
        assert causal_beta_pair(same_day, x).iloc[i] == pytest.approx(base, rel=1e-12)

        prior_day = y.copy()
        prior_day.iloc[i - 1] = prior_day.iloc[i - 1] + 10.0   # the last day IN the window
        assert causal_beta_pair(prior_day, x).iloc[i] != pytest.approx(base, rel=1e-6)

    def test_min_overlap_gate_returns_nan_below_the_floor(self):
        x, y = _synthetic_pair()
        beta = causal_beta_pair(y, x)
        # position i is computed from i-1 back; fewer than BETA_MINP prior rows -> NaN
        assert np.isnan(beta.iloc[BETA_MINP - 1])
        assert np.isfinite(beta.iloc[BETA_MINP + 1])

    def test_mirrors_the_incumbent_cn_global_beta_construction(self):
        """The probe must not re-decide the house beta; only specialise x per member."""
        x, y = _synthetic_pair()
        incumbent = INCUMBENT_CAUSAL_BETA(pd.DataFrame({"m": y}), x, BETA_WIN, BETA_MINP)["m"]
        ours = causal_beta_pair(y, x, BETA_WIN, BETA_MINP)
        pd.testing.assert_series_equal(ours, incumbent, check_names=False)


class TestExSelfBasketReturn:
    def test_excludes_the_member_itself(self):
        idx = DATES[:2]
        R = pd.DataFrame({"A": [0.01, 0.02], "B": [0.03, 0.04], "C": [0.05, 0.06]}, index=idx)
        X = ex_self_returns(R)
        assert X.loc[idx[0], "A"] == pytest.approx((0.03 + 0.05) / 2)
        assert X.loc[idx[0], "B"] == pytest.approx((0.01 + 0.05) / 2)
        assert X.loc[idx[1], "C"] == pytest.approx((0.02 + 0.04) / 2)

    def test_is_equal_weight_over_the_members_that_actually_traded(self):
        idx = DATES[:1]
        R = pd.DataFrame({"A": [0.01], "B": [np.nan], "C": [0.05], "D": [0.09]}, index=idx)
        X = ex_self_returns(R)
        assert X.loc[idx[0], "A"] == pytest.approx((0.05 + 0.09) / 2)   # B is not a zero
        assert np.isnan(X.loc[idx[0], "B"])

    def test_undefined_when_fewer_than_two_members_traded(self):
        idx = DATES[:1]
        R = pd.DataFrame({"A": [0.01], "B": [np.nan]}, index=idx)
        assert np.isnan(ex_self_returns(R).loc[idx[0], "A"])

    def test_identical_members_give_beta_exactly_one(self):
        """Closed form: if every member moves alike, cov(r, r)/var(r) == 1."""
        r = pd.Series(np.linspace(-0.03, 0.03, len(DATES)), index=DATES)
        R = pd.DataFrame({c: r for c in ("A", "B", "C", "D")})
        X = ex_self_returns(R)
        assert causal_beta_pair(R["A"], X["A"]).iloc[150] == pytest.approx(1.0, rel=1e-9)

    def test_the_beta_identity_holds(self):
        """beta == corr * sd_own / sd_ex_self — the factorisation the report leans on."""
        rng = np.random.default_rng(11)
        R = pd.DataFrame({c: rng.normal(0, 0.02, len(DATES)) for c in "ABCDE"}, index=DATES)
        X = ex_self_returns(R)
        i = 150
        beta = causal_beta_pair(R["A"], X["A"]).iloc[i]
        corr = R["A"].rolling(BETA_WIN, min_periods=BETA_MINP).corr(X["A"]).shift(1).iloc[i]
        sd_o = R["A"].rolling(BETA_WIN, min_periods=BETA_MINP).std().shift(1).iloc[i]
        sd_x = X["A"].rolling(BETA_WIN, min_periods=BETA_MINP).std().shift(1).iloc[i]
        assert beta == pytest.approx(corr * sd_o / sd_x, rel=1e-9)


class TestCorrCompanionProjection:
    """The post-prereg companion is a PROJECTION of the beta cell, never a re-estimation."""

    def _rows(self):
        rows = [
            dict(month="2026-07", node_id="co:us:A", symbol="A", value=1.2,
                 corr_to_ex_self=0.8, sd_own_daily=0.03, sd_ex_self_daily=0.02,
                 era="reconstruction", in_universe=True, stamp_session="2026-07-31"),
            dict(month="2026-07", node_id="co:us:B", symbol="B", value=np.nan,
                 corr_to_ex_self=np.nan, sd_own_daily=np.nan, sd_ex_self_daily=np.nan,
                 era="reconstruction", in_universe=False, stamp_session="2026-07-31"),
        ]
        diags = [dict(month="2026-07", n_members=2, n_values=1, coverage=0.5,
                      no_events=False, era="reconstruction", stamp_session="2026-07-31")]
        return rows, diags

    def test_carries_the_corr_term_through_as_the_cell_value(self):
        cell = corr_cell_from_beta_rows(*self._rows())
        by_sym = {r["symbol"]: r for r in cell["rows"]}
        assert by_sym["A"]["value"] == pytest.approx(0.8)
        assert by_sym["A"]["month"] == "2026-07"
        assert by_sym["A"]["era"] == "reconstruction"

    def test_a_missing_corr_is_not_counted_as_a_value(self):
        cell = corr_cell_from_beta_rows(*self._rows())
        d = cell["diags"][0]
        assert d["n_values"] == 1 and d["n_members"] == 2
        assert d["coverage"] == pytest.approx(0.5)

    def test_preserves_the_month_and_membership_grid_of_the_frozen_cell(self):
        rows, diags = self._rows()
        cell = corr_cell_from_beta_rows(rows, diags)
        assert len(cell["rows"]) == len(rows)
        assert [d["month"] for d in cell["diags"]] == [d["month"] for d in diags]
        assert all(d["no_events"] is False for d in cell["diags"])


class TestVasicekShrink:
    def test_pulls_toward_the_cross_sectional_mean(self):
        b = pd.Series({"A": 0.4, "B": 1.6})
        s = vasicek_shrink(b, 0.5)
        assert s["A"] == pytest.approx(0.5 * 0.4 + 0.5 * 1.0)
        assert s["B"] == pytest.approx(0.5 * 1.6 + 0.5 * 1.0)

    def test_compresses_dispersion_which_is_why_it_is_display_only(self):
        b = pd.Series({"A": 0.2, "B": 1.0, "C": 1.8})
        assert vasicek_shrink(b, 0.66).std() < b.std()

    def test_weight_of_one_is_a_passthrough(self):
        b = pd.Series({"A": 0.2, "B": 1.8})
        pd.testing.assert_series_equal(vasicek_shrink(b, 1.0), b)


# =====================================================================================
# attention_share.* — the share denominator
# =====================================================================================
class TestShares:
    def test_shares_sum_to_one(self):
        shares, denom = shares_from_magnitudes(pd.Series({"A": 3.0, "B": 5.0, "C": 2.0}))
        assert denom == pytest.approx(10.0)
        assert shares.sum() == pytest.approx(1.0)
        assert shares["B"] == pytest.approx(0.5)

    def test_zeros_are_values_not_missing(self):
        """LHB rule: a member with no appearances holds share 0.0 and stays in the index."""
        mags = pd.Series({"A": 0.0, "B": 4.0, "C": 0.0, "D": 1.0})
        shares, denom = shares_from_magnitudes(mags)
        assert denom == pytest.approx(5.0)
        assert list(shares.index) == ["A", "B", "C", "D"]
        assert shares["A"] == 0.0 and shares["C"] == 0.0
        assert shares.sum() == pytest.approx(1.0)

    def test_zero_denominator_is_no_events_never_a_division(self):
        shares, denom = shares_from_magnitudes(pd.Series({"A": 0.0, "B": 0.0}))
        assert shares is None
        assert denom == 0.0

    def test_missing_is_dropped_not_zero_filled(self):
        shares, _ = shares_from_magnitudes(pd.Series({"A": 2.0, "B": np.nan, "C": 2.0}))
        assert "B" not in shares.index          # absent from the universe != measured at zero
        assert shares.sum() == pytest.approx(1.0)

    def test_negative_magnitudes_are_refused(self):
        with pytest.raises(ValueError):
            shares_from_magnitudes(pd.Series({"A": 1.0, "B": -0.5}))

    def test_empty_input_is_no_events(self):
        shares, denom = shares_from_magnitudes(pd.Series(dtype=float))
        assert shares is None and denom == 0.0


class TestMonthlyAppearanceCount:
    def test_counts_distinct_ticker_days_not_rows(self):
        """A dragon-tiger name listed under two reasons on one day is ONE appearance."""
        df = pd.DataFrame({
            "ticker": ["000001.SZ", "000001.SZ", "000001.SZ", "000002.SZ"],
            "date": ["2026-07-01", "2026-07-01", "2026-07-02", "2026-07-05"],
        })
        out = monthly_count(df, "ticker", "date")
        assert out["2026-07"]["000001.SZ"] == 2.0
        assert out["2026-07"]["000002.SZ"] == 1.0

    def test_splits_on_month_boundaries(self):
        df = pd.DataFrame({"ticker": ["A", "A"], "date": ["2026-07-31", "2026-08-01"]})
        out = monthly_count(df, "ticker", "date")
        assert out["2026-07"]["A"] == 1.0 and out["2026-08"]["A"] == 1.0


# =====================================================================================
# H1 — the coverage floor
# =====================================================================================
class TestCoverageFloor:
    def test_coverage_fraction(self):
        assert coverage_fraction(7, 10) == pytest.approx(0.70)
        assert coverage_fraction(0, 9) == 0.0

    def test_abstains_strictly_below_the_floor(self):
        assert COVERAGE_FLOOR == 0.70
        assert cell_abstains(0.69) is True
        assert cell_abstains(0.6999) is True

    def test_does_not_abstain_at_or_above_the_floor(self):
        assert cell_abstains(0.70) is False
        assert cell_abstains(0.71) is False
        assert cell_abstains(1.0) is False

    def test_undefined_coverage_abstains_fail_closed(self):
        assert cell_abstains(float("nan")) is True
        assert cell_abstains(None) is True

    def test_no_members_is_undefined_and_abstains(self):
        cov = coverage_fraction(0, 0)
        assert np.isnan(cov)
        assert cell_abstains(cov) is True

    def test_a_cell_of_all_zero_shares_still_has_full_coverage(self):
        """Zeros are values: 15 members all at zero is coverage 1.0, not 0.0."""
        assert coverage_fraction(15, 15) == 1.0
        assert cell_abstains(coverage_fraction(15, 15)) is False


# =====================================================================================
# §4 — era labelling on backcast rows
# =====================================================================================
class TestEraLabelling:
    def test_backcast_months_are_reconstruction(self):
        assert OBSERVED_ERA_FROM == "2026-08-11"
        for m in ("2023-06", "2024-01", "2025-12", "2026-07"):
            assert era_for_month(m) == "reconstruction"

    def test_the_month_containing_the_belief_stamp_is_still_reconstruction(self):
        """2026-08 STARTS on the 1st, before the graph's first belief — the whole monthly
        cross-section rides reconstruction membership, not a partially-observed era."""
        assert era_for_month("2026-08") == "reconstruction"

    def test_only_a_month_starting_after_the_stamp_is_observed(self):
        assert era_for_month("2026-09") == "observed"
        assert era_for_month("2027-02") == "observed"

    def test_boundary_is_the_month_start_not_the_month_end(self):
        assert era_for_month("2026-08", observed_from="2026-08-01") == "observed"
        assert era_for_month("2026-08", observed_from="2026-08-02") == "reconstruction"


# =====================================================================================
# Inference — small-N Spearman, ties, exact vs Monte Carlo
# =====================================================================================
class TestSpearman:
    def test_perfect_monotone_has_rho_one_and_the_exact_two_sided_p(self):
        rho, p, method = spearman_exact([1, 2, 3, 4, 5], [10, 20, 30, 40, 50])
        assert rho == pytest.approx(1.0)
        assert method.startswith("exact-permutation")
        assert p == pytest.approx(2.0 / 120.0)      # identity + full reversal, of 5! = 120

    def test_perfect_inverse_gives_the_same_two_sided_p(self):
        _, p_up, _ = spearman_exact([1, 2, 3, 4, 5], [10, 20, 30, 40, 50])
        rho, p_dn, _ = spearman_exact([1, 2, 3, 4, 5], [50, 40, 30, 20, 10])
        assert rho == pytest.approx(-1.0)
        assert p_dn == pytest.approx(p_up)

    def test_ties_use_average_ranks_and_match_scipy(self):
        x = [1, 1, 2, 3, 5, 5, 5]
        y = [2, 3, 3, 4, 9, 1, 4]
        rho, p, method = spearman_exact(x, y)
        assert rho == pytest.approx(float(sps.spearmanr(x, y).statistic))
        assert method.startswith("exact-permutation")
        assert 0.0 < p <= 1.0

    def test_a_fully_tied_vector_is_undefined_not_zero(self):
        rho, p, method = spearman_exact([1, 2, 3, 4], [7, 7, 7, 7])
        assert np.isnan(rho) and np.isnan(p)
        assert "undefined-constant" in method

    def test_n_below_three_is_undefined(self):
        rho, p, method = spearman_exact([1, 2], [3, 4])
        assert np.isnan(rho) and np.isnan(p)
        assert "undefined-n<3" in method

    def test_smallest_possible_cross_section_still_enumerates_exactly(self):
        rho, p, method = spearman_exact([1, 2, 3], [1, 2, 3])
        assert rho == pytest.approx(1.0)
        assert p == pytest.approx(2.0 / 6.0)        # 3! = 6 pairings
        assert "perms=6" in method

    def test_exact_below_the_threshold_and_monte_carlo_above_it(self):
        rng = np.random.default_rng(3)
        _, _, m_small = spearman_exact(list(range(9)), list(rng.permutation(9)))
        _, _, m_big = spearman_exact(list(range(12)), list(rng.permutation(12)))
        assert m_small.startswith("exact-permutation")
        assert m_big.startswith("mc-permutation")

    def test_the_monte_carlo_p_is_deterministic(self):
        rng = np.random.default_rng(5)
        x, y = list(range(14)), list(rng.permutation(14))
        assert spearman_exact(x, y)[1] == spearman_exact(x, y)[1]

    def test_the_monte_carlo_p_is_never_zero(self):
        """Add-one correction: a permutation p of exactly 0 would be a false certainty."""
        _, p, _ = spearman_exact(list(range(20)), list(range(20)))
        assert p > 0.0

    def test_rho_only_helper_agrees_with_the_full_form_including_ties(self):
        x = [3, 1, 4, 1, 5, 9, 2, 6]
        y = [2, 7, 1, 8, 2, 8, 1, 8]
        assert spearman_rho(x, y) == pytest.approx(spearman_exact(x, y)[0])

    def test_rho_only_helper_is_undefined_on_short_or_constant_input(self):
        assert np.isnan(spearman_rho([1, 2], [3, 4]))
        assert np.isnan(spearman_rho([1, 2, 3], [4, 4, 4]))

    def test_length_mismatch_is_refused(self):
        with pytest.raises(ValueError):
            spearman_exact([1, 2, 3], [1, 2])


class TestBlockBootstrap:
    def test_is_deterministic(self):
        s = [np.linspace(0.1, 0.9, 12), np.linspace(0.2, 0.8, 9)]
        assert block_bootstrap_median_ci(s) == block_bootstrap_median_ci(s)

    def test_interval_brackets_the_pooled_median(self):
        rng = np.random.default_rng(2)
        s = [rng.uniform(0.2, 0.8, 30), rng.uniform(0.3, 0.9, 25)]
        lo, hi, n = block_bootstrap_median_ci(s)
        med = float(np.median(np.concatenate(s)))
        assert lo <= med <= hi
        assert lo < hi                                   # a real width, not a point
        assert n == 55

    def test_a_series_no_longer_than_the_block_cannot_be_resampled(self):
        """Degenerate by construction: one block placement means every draw is the original."""
        s = [np.array([0.4, 0.6]), np.array([0.8])]
        lo, hi, n = block_bootstrap_median_ci(s, block=BOOTSTRAP_BLOCK)
        assert lo == hi == pytest.approx(float(np.median(np.concatenate(s))))
        assert n == 3

    def test_empty_input_is_undefined(self):
        lo, hi, n = block_bootstrap_median_ci([])
        assert np.isnan(lo) and np.isnan(hi) and n == 0

    def test_non_finite_pairs_are_dropped_not_treated_as_zero(self):
        lo, hi, n = block_bootstrap_median_ci([np.array([0.5, np.nan, 0.7, np.nan])])
        assert n == 2


# =====================================================================================
# §3 — the frozen threshold readings
# =====================================================================================
class TestActiveMembers:
    """The dead-member window is HALF-OPEN: [valid_from, valid_to)."""

    COLS = ["edge_id", "type", "src", "dst", "valid_from", "valid_to", "belief_time"]

    def _lb(self):
        rows = [
            ("e1", "MEMBER_OF", "co:us:LIVE", "basket:b", "2023-05-09", None, "2026-08-11"),
            ("e2", "MEMBER_OF", "co:us:DEAD", "basket:b", "2023-05-09", "2026-06-18",
             "2026-08-11"),
            ("e3", "MEMBER_OF", "co:us:OTHER", "basket:zzz", "2023-05-09", None, "2026-08-11"),
        ]
        return pd.DataFrame(rows, columns=self.COLS)

    def test_open_ended_member_is_always_active_after_its_start(self):
        assert active_members(self._lb(), ["basket:b"], "2026-08-31") == ["co:us:LIVE"]

    def test_closed_member_is_included_strictly_before_valid_to(self):
        got = active_members(self._lb(), ["basket:b"], "2026-06-17")
        assert got == ["co:us:DEAD", "co:us:LIVE"]

    def test_the_window_is_half_open_so_valid_to_itself_is_excluded(self):
        """The exit date is the first day OUT — not the last day in."""
        assert active_members(self._lb(), ["basket:b"], "2026-06-18") == ["co:us:LIVE"]

    def test_member_absent_before_its_valid_from(self):
        assert active_members(self._lb(), ["basket:b"], "2023-05-08") == []

    def test_other_baskets_are_not_pulled_in(self):
        assert "co:us:OTHER" not in active_members(self._lb(), ["basket:b"], "2026-08-31")

    def test_a_union_slot_takes_the_union_of_its_baskets(self):
        got = active_members(self._lb(), ["basket:b", "basket:zzz"], "2026-08-31")
        assert got == ["co:us:LIVE", "co:us:OTHER"]


class TestDraftVerdictRules:
    """The two rules W4 inherits directly — pinned so neither can drift silently."""

    def _cells(self, cid=BETA_ID, cov=1.0, tie=0.2, pct_nonzero=0.9):
        """One computable US slot and one computable CN slot for the given construction."""
        out = {}
        slots = (("us_mature_broad", "cn_mature") if cid == BETA_ID else ("cn_mature",))
        for slot in slots:
            rows, diags = [], []
            for i in range(6):
                m = f"2026-0{i + 1}"
                rows.append(dict(month=m, node_id="co:x:A", symbol="A", value=1.0))
                diags.append(dict(month=m, n_members=1, n_values=1, coverage=cov,
                                  no_events=False, era="reconstruction",
                                  modal_tie_mass=tie, pct_nonzero=pct_nonzero))
            out[(slot, cid)] = dict(
                rows=rows, diags=diags, coverage=cov, abstain=cell_abstains(cov),
                graded_months=[d["month"] for d in diags], no_events_months=[])
        return out

    def _h3(self, us_reading, cn_reading, cid=BETA_ID, us_med=0.9, cn_med=0.9):
        def mk(reading, med):
            return dict(n_slots=1, n_pairs=5, median_rho=med, reading=reading,
                        lag3_pairs=3, lag3_median=0.8, lag3_overlap_sessions=None,
                        per_slot_lag3={})
        return {cid: dict(reading="POOLED-VALUE-THAT-MUST-NOT-BE-USED", median_rho=0.99,
                          per_slot=[dict(slot="cn_mature", n_pairs=5, median=cn_med),
                                    dict(slot="us_mature_broad", n_pairs=5, median=us_med)],
                          companion_lag3_median=0.8, companion_lag3_pairs=3,
                          per_market={"us": mk(us_reading, us_med),
                                      "cn": mk(cn_reading, cn_med)})}

    def _row(self, verdicts, market, cid=BETA_ID):
        return next(v for v in verdicts
                    if v["construction"] == cid and v["market"] == market)

    def test_noise_demotes_to_computable_but_unstable(self):
        v = draft_verdicts(self._cells(), self._h3("STABLE (x)", "NOISE (median rho 0.2 < 0.3)"))
        assert self._row(v, "cn")["verdict"] == "COMPUTABLE-BUT-UNSTABLE"

    def test_weakly_stable_demotes_the_same_way_noise_does(self):
        """The 0.30-0.60 band must never reach an unqualified MEASURABLE-NOW."""
        v = draft_verdicts(self._cells(),
                           self._h3("STABLE (x)", "WEAKLY-STABLE (median rho 0.450)"))
        assert self._row(v, "cn")["verdict"] == "COMPUTABLE-BUT-UNSTABLE"

    def test_stable_keeps_measurable_now(self):
        v = draft_verdicts(self._cells(), self._h3("STABLE (x)", "STABLE (median rho 0.9)"))
        assert self._row(v, "cn")["verdict"] == "MEASURABLE-NOW"

    def test_the_h3_reading_is_taken_PER_MARKET_not_pooled(self):
        """A CN NOISE must not drag the US row down, and vice versa."""
        v = draft_verdicts(self._cells(),
                           self._h3("STABLE (median rho 0.9)", "NOISE (median rho 0.2 < 0.3)"))
        assert self._row(v, "us")["verdict"] == "MEASURABLE-NOW"
        assert self._row(v, "cn")["verdict"] == "COMPUTABLE-BUT-UNSTABLE"
        # and the pooled value must be ignored entirely
        assert "POOLED-VALUE-THAT-MUST-NOT-BE-USED" not in self._row(v, "us")["basis"]

    def test_coverage_floor_still_outranks_the_stability_rule(self):
        v = draft_verdicts(self._cells(cov=0.1),
                           self._h3("STABLE (x)", "STABLE (median rho 0.9)"))
        assert self._row(v, "cn")["verdict"] == "BLOCKED-ON-INGESTION"

    def test_beta_basis_carries_the_quarterly_horizon_caveat(self):
        v = draft_verdicts(self._cells(), self._h3("STABLE (a)", "STABLE (b)"))
        assert "~quarterly horizon" in self._row(v, "cn")["basis"]

    def test_lhb_basis_leads_with_the_price_selected_universe(self):
        v = draft_verdicts(self._cells(cid=CN_LHB_ID),
                           self._h3("NOISE (a)", "NOISE (b)", cid=CN_LHB_ID),
                           lhb_price_share=0.9838)
        basis = self._row(v, "cn", cid=CN_LHB_ID)["basis"]
        assert basis.startswith("PRICE-SELECTED UNIVERSE")
        assert "98.4%" in basis
        assert "refusal family" in basis

    def test_economic_share_warns_against_ready_pending_data(self):
        v = draft_verdicts(self._cells(), self._h3("STABLE (x)", "STABLE (y)"))
        econ = next(x for x in v if x["construction"] == "economic_share")
        assert econ["verdict"] == "BLOCKED-ON-INGESTION"
        assert "ready-pending-data" in econ["basis"]


class TestWindowOverlap:
    """The lag-k companion's windows are measured, never assumed disjoint."""

    def test_identical_stamps_share_the_whole_window(self):
        assert window_overlap_sessions(100, 100) == BETA_WIN

    def test_overlap_falls_linearly_with_the_stamp_gap(self):
        assert window_overlap_sessions(100, 110) == BETA_WIN - 10
        assert window_overlap_sessions(110, 100) == BETA_WIN - 10   # symmetric

    def test_windows_are_disjoint_only_once_the_gap_reaches_the_window(self):
        assert window_overlap_sessions(0, BETA_WIN) == 0
        assert window_overlap_sessions(0, BETA_WIN + 50) == 0

    def test_a_three_month_gap_can_still_overlap(self):
        """~63 sessions a quarter, so a 3-month pair is NOT guaranteed disjoint."""
        assert window_overlap_sessions(0, 55) > 0


class TestFrozenReadings:
    def test_h2_redundant_above_the_ceiling(self):
        assert h2_reading([0.93, 0.95, 0.97]).startswith("REDUNDANT")

    def test_h2_measurably_disagree_needs_both_conditions(self):
        assert h2_reading([0.2, 0.45, 0.6]).startswith("MEASURABLY-DISAGREE")

    def test_h2_partially_distinct_when_no_slot_clears_the_second_condition(self):
        # median 0.60 <= 0.70, but no slot at or below 0.50 -> not "measurably disagree"
        assert h2_reading([0.55, 0.60, 0.65]).startswith("PARTIALLY-DISTINCT")

    def test_h2_is_vacuous_with_no_computable_slot(self):
        assert h2_reading([]).startswith("VACUOUS")

    def test_h3_depth_gate_outranks_the_effect_size(self):
        assert h3_reading(0.99, 2).startswith("UNDERPOWERED-BY-DEPTH")
        assert h3_reading(0.01, 1).startswith("UNDERPOWERED-BY-DEPTH")

    def test_h3_thresholds(self):
        assert h3_reading(0.75, 10).startswith("STABLE")
        assert h3_reading(0.60, 10).startswith("STABLE")          # floor is inclusive
        assert h3_reading(0.45, 10).startswith("WEAKLY-STABLE")
        assert h3_reading(0.29, 10).startswith("NOISE")
        assert h3_reading(-0.4, 10).startswith("NOISE")
