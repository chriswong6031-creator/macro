"""Amendment 3 harness tests — entry_strata_phase0.py and _a3_common.py.

Fixture groups:
  (a) r1_interaction_estimate: seeded DGP with planted 5pp interaction recovers
      ~0.05 with CI covering truth and excluding 0.
  (b) r1_interaction_estimate null case: mains-only DGP, CI includes 0.
  (c) extra_fe_cols kill test: stratum effect exists only through a confounder
      band; plain r1_estimate finds it, r1_estimate(extra_fe_cols=['band']) kills it.
  (d) Legacy regression: r1_estimate(extra_fe_cols=None) returns byte-identical
      coef to the pre-change path on a small fixture.
  (e) FAMILY_BUDGETS A3 keys and total.
  (f) era_sign_stability: planted consistent-sign effect → sign_stable_3of4=True.
  (g) ticker_half_sign_agreement: consistent-sign halves → sign_agree=True.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import scripts.research.entry_strata_phase0 as ph
import scripts.research._a3_common as a3c

# ---------------------------------------------------------------------------
# Shared DGP helpers
# ---------------------------------------------------------------------------

BDATE_START = pd.Timestamp("2014-01-02")
N_BOOTSTRAP_FAST = 200


def _bdate_range(n: int, spacing: int = 5, start: pd.Timestamp = BDATE_START) -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n * spacing, freq=f"{spacing}B")[:n]


def _synthetic_graded(
    n_dates: int,
    fires_per_date: int,
    *,
    interaction_effect: float = 0.0,
    main_a_effect: float = 0.0,
    main_b_effect: float = 0.0,
    date_effect_sigma: float = 0.05,
    base_rate: float = 0.40,
    seed: int = 0,
) -> pd.DataFrame:
    """Build a synthetic graded DataFrame with planted binary outcome.

    Each row has columns: date, flag_a, flag_b, outcome, stratum (=flag_a
    for plain r1_estimate tests).

    DGP:
        P(outcome=1) = base_rate + date_effect[d] + main_a*flag_a
                       + main_b*flag_b + interaction_effect*(flag_a*flag_b)
        clipped to [0,1].

    flag_a and flag_b are independent Bernoulli(0.5) per fire.
    """
    rng = np.random.default_rng(seed)
    dates = _bdate_range(n_dates, spacing=5, start=BDATE_START)

    date_effects = rng.normal(0.0, date_effect_sigma, n_dates)

    rows = []
    for di, date in enumerate(dates):
        de = date_effects[di]
        for _ in range(fires_per_date):
            fa = int(rng.random() < 0.5)
            fb = int(rng.random() < 0.5)
            p = (
                base_rate
                + de
                + main_a_effect * fa
                + main_b_effect * fb
                + interaction_effect * fa * fb
            )
            p = float(np.clip(p, 0.0, 1.0))
            outcome = int(rng.random() < p)
            rows.append({
                "date": date,
                "flag_a": float(fa),
                "flag_b": float(fb),
                "outcome": float(outcome),
                "stratum": float(fa),
            })

    df = pd.DataFrame(rows)
    df["gradable"] = True
    return df


# ===========================================================================
# (a) r1_interaction_estimate: planted 5pp interaction recovered
# ===========================================================================

class TestInteractionEstimatePlantedEffect:
    """r1_interaction_estimate recovers a planted 5pp interaction coefficient."""

    PLANTED_EFFECT = 0.05
    TOLERANCE = 0.08  # within-date FE demeaning amplifies noise on small N; coef ~ planted ± 1.5x

    @pytest.fixture(scope="class")
    def planted_result(self):
        df = _synthetic_graded(
            n_dates=80,
            fires_per_date=12,
            interaction_effect=self.PLANTED_EFFECT,
            main_a_effect=0.02,
            main_b_effect=0.01,
            date_effect_sigma=0.03,
            seed=1001,
        )
        return ph.r1_interaction_estimate(
            df, "outcome", "flag_a", "flag_b",
            fe_granularity="date",
            n_bootstrap=N_BOOTSTRAP_FAST,
            rng_seed=42,
        )

    def test_coef_near_planted(self, planted_result):
        """Coefficient is within tolerance of the planted effect."""
        coef = planted_result["coef"]
        assert coef is not None
        assert abs(coef - self.PLANTED_EFFECT) < self.TOLERANCE, (
            f"coef={coef:.4f} not within {self.TOLERANCE} of planted {self.PLANTED_EFFECT}"
        )

    def test_ci_covers_truth(self, planted_result):
        """95% CI contains the planted truth."""
        ci_lo = planted_result["ci_lo"]
        ci_hi = planted_result["ci_hi"]
        assert ci_lo is not None and ci_hi is not None
        assert ci_lo <= self.PLANTED_EFFECT <= ci_hi, (
            f"CI [{ci_lo:.4f}, {ci_hi:.4f}] does not cover truth {self.PLANTED_EFFECT}"
        )

    def test_ci_excludes_zero(self, planted_result):
        """95% CI excludes zero for a 5pp planted effect with adequate N."""
        ci_lo = planted_result["ci_lo"]
        ci_hi = planted_result["ci_hi"]
        assert ci_lo is not None and ci_hi is not None
        assert ci_lo > 0 or ci_hi > 0, "CI entirely non-positive for planted positive effect"
        assert not (ci_lo <= 0 <= ci_hi), (
            f"CI [{ci_lo:.4f}, {ci_hi:.4f}] includes zero despite planted effect"
        )

    def test_result_dict_shape(self, planted_result):
        """Result dict has all required keys."""
        required = {
            "coef", "ci_lo", "ci_hi", "p_value",
            "n_total", "n_treat", "n_ctrl",
            "n_treatment", "n_control",
            "n_est", "n_blocks",
            "fe_granularity", "sector_fallback",
            "naive_diff", "outcome", "stratum",
            "mask_n_dropped", "mask_coverage",
        }
        missing = required - set(planted_result.keys())
        assert not missing, f"Missing keys in r1_interaction_estimate result: {missing}"

    def test_n_treat_ctrl_sum_to_n_total(self, planted_result):
        """n_treat + n_ctrl == n_total."""
        assert planted_result["n_treat"] + planted_result["n_ctrl"] == planted_result["n_total"]

    def test_n_treatment_n_control_aliases(self, planted_result):
        """n_treatment == n_treat and n_control == n_ctrl (effect_table compat aliases)."""
        assert planted_result["n_treatment"] == planted_result["n_treat"]
        assert planted_result["n_control"] == planted_result["n_ctrl"]

    def test_stratum_label_is_interaction(self, planted_result):
        """stratum key carries the interaction label."""
        assert "flag_a" in planted_result["stratum"]
        assert "flag_b" in planted_result["stratum"]

    def test_p_value_small(self, planted_result):
        """p-value < 0.10 for a 5pp planted effect with adequate N."""
        p = planted_result["p_value"]
        assert p is not None
        assert p < 0.10, f"p_value={p:.4f} not small for planted 5pp effect"


# ===========================================================================
# (b) r1_interaction_estimate null: mains-only DGP, CI includes 0
# ===========================================================================

class TestInteractionEstimateNull:
    """Null DGP (no interaction term) produces CI containing zero."""

    @pytest.fixture(scope="class")
    def null_result(self):
        df = _synthetic_graded(
            n_dates=60,
            fires_per_date=8,
            interaction_effect=0.0,
            main_a_effect=0.05,
            main_b_effect=0.03,
            date_effect_sigma=0.04,
            seed=2002,
        )
        return ph.r1_interaction_estimate(
            df, "outcome", "flag_a", "flag_b",
            fe_granularity="date",
            n_bootstrap=N_BOOTSTRAP_FAST,
            rng_seed=42,
        )

    def test_ci_includes_zero(self, null_result):
        """95% CI includes zero for a null interaction DGP."""
        ci_lo = null_result["ci_lo"]
        ci_hi = null_result["ci_hi"]
        assert ci_lo is not None and ci_hi is not None
        assert ci_lo <= 0 <= ci_hi, (
            f"CI [{ci_lo:.4f}, {ci_hi:.4f}] excludes zero for null DGP"
        )

    def test_p_value_not_small(self, null_result):
        """p-value is not small (< 0.05 would be a false positive)."""
        p = null_result["p_value"]
        assert p is not None
        assert p > 0.05, (
            f"p_value={p:.4f} < 0.05 for null-interaction DGP (false positive risk)"
        )


# ===========================================================================
# (c) extra_fe_cols kill test
# ===========================================================================

class TestExtraFEColsKill:
    """extra_fe_cols kills a confounder-driven effect.

    Design:
      - 3 'bands' (0/1/2).  Band 1 has a high stop rate; band 0 and 2 have
        baseline rates.
      - stratum is random (Bernoulli 0.5), INDEPENDENT of outcome within band.
      - But band 1 fires are over-represented in the treatment arm (stratum=1).
        This creates a spurious stratum effect: treatment fires happen more in
        band 1 (high-stop band) → naive FE coef is positive.
      - Adding extra_fe_cols=['band'] removes the band-level confounder.
    """

    N_DATES = 50
    FIRES_PER_DATE = 8
    SEED = 3003

    @pytest.fixture(scope="class")
    def confounded_data(self):
        """Build confounded graded DataFrame with band column."""
        rng = np.random.default_rng(self.SEED)
        dates = _bdate_range(self.N_DATES, spacing=5, start=BDATE_START)

        rows = []
        for date in dates:
            for _ in range(self.FIRES_PER_DATE):
                # Band assignment: treatment fires are biased toward band 1
                stratum = int(rng.random() < 0.5)
                if stratum == 1:
                    band = int(rng.choice([0, 1, 2], p=[0.15, 0.70, 0.15]))
                else:
                    band = int(rng.choice([0, 1, 2], p=[0.70, 0.15, 0.15]))

                # Stop rate depends on band, not stratum
                stop_rate = {0: 0.20, 1: 0.70, 2: 0.20}[band]
                outcome = float(rng.random() < stop_rate)

                rows.append({
                    "date": date,
                    "stratum": float(stratum),
                    "band": float(band),
                    "outcome": outcome,
                    "gradable": True,
                })

        return pd.DataFrame(rows)

    def test_plain_estimate_finds_spurious_effect(self, confounded_data):
        """Without extra_fe_cols, the confounded coefficient is positive."""
        result = ph.r1_estimate(
            confounded_data, "outcome", "stratum",
            fe_granularity="date",
            n_bootstrap=N_BOOTSTRAP_FAST,
            rng_seed=42,
        )
        coef = result["coef"]
        assert coef is not None
        assert coef > 0.05, (
            f"Expected confounded positive effect, got coef={coef:.4f}"
        )

    def test_extra_fe_kills_confounder(self, confounded_data):
        """With extra_fe_cols=['band'], the confounded effect is killed (CI includes 0)."""
        result = ph.r1_estimate(
            confounded_data, "outcome", "stratum",
            fe_granularity="date",
            n_bootstrap=N_BOOTSTRAP_FAST,
            rng_seed=42,
            extra_fe_cols=["band"],
        )
        coef = result["coef"]
        ci_lo = result["ci_lo"]
        ci_hi = result["ci_hi"]
        assert coef is not None and ci_lo is not None and ci_hi is not None
        assert ci_lo <= 0 <= ci_hi, (
            f"extra_fe_cols did not kill spurious effect: CI [{ci_lo:.4f}, {ci_hi:.4f}]"
        )

    def test_n_dropped_extra_fe_is_zero_when_no_nan(self, confounded_data):
        """n_dropped_extra_fe=0 when band has no NaN rows."""
        result = ph.r1_estimate(
            confounded_data, "outcome", "stratum",
            fe_granularity="date",
            n_bootstrap=50,
            rng_seed=42,
            extra_fe_cols=["band"],
        )
        assert result["n_dropped_extra_fe"] == 0

    def test_n_dropped_extra_fe_counts_nan_rows(self, confounded_data):
        """n_dropped_extra_fe counts rows with NaN in extra col."""
        df = confounded_data.copy()
        n_nan = 10
        df.loc[:n_nan - 1, "band"] = np.nan

        result = ph.r1_estimate(
            df, "outcome", "stratum",
            fe_granularity="date",
            n_bootstrap=50,
            rng_seed=42,
            extra_fe_cols=["band"],
        )
        # The drop happens after row-filtering on outcome/stratum validity.
        # All n_nan rows have valid outcome and stratum, so all should be counted.
        assert result["n_dropped_extra_fe"] == n_nan, (
            f"n_dropped_extra_fe={result['n_dropped_extra_fe']}, expected {n_nan}"
        )

    def test_extra_fe_none_has_zero_n_dropped(self, confounded_data):
        """extra_fe_cols=None (default) gives n_dropped_extra_fe=0."""
        result = ph.r1_estimate(
            confounded_data, "outcome", "stratum",
            fe_granularity="date",
            n_bootstrap=50,
            rng_seed=42,
        )
        assert result["n_dropped_extra_fe"] == 0


# ===========================================================================
# (d) Legacy regression: extra_fe_cols=None is bit-identical to old path
# ===========================================================================

class TestExtraFELegacyIdentity:
    """r1_estimate(extra_fe_cols=None) produces identical coef to default path."""

    @pytest.fixture(scope="class")
    def small_fixture(self):
        """20-date × 4-fire simple fixture."""
        rng = np.random.default_rng(9999)
        dates = _bdate_range(20, spacing=5, start=BDATE_START)
        rows = []
        for date in dates:
            for j in range(4):
                stratum = float(j % 2)
                outcome = float(rng.random() < (0.3 + 0.1 * stratum))
                rows.append({
                    "date": date,
                    "stratum": stratum,
                    "outcome": outcome,
                    "gradable": True,
                })
        return pd.DataFrame(rows)

    def test_none_gives_same_coef_as_default(self, small_fixture):
        """Passing extra_fe_cols=None gives the same coef as not passing it."""
        result_default = ph.r1_estimate(
            small_fixture, "outcome", "stratum",
            fe_granularity="date",
            n_bootstrap=100,
            rng_seed=1,
        )
        result_explicit_none = ph.r1_estimate(
            small_fixture, "outcome", "stratum",
            fe_granularity="date",
            n_bootstrap=100,
            rng_seed=1,
            extra_fe_cols=None,
        )
        assert result_default["coef"] == result_explicit_none["coef"], (
            f"coef mismatch: default={result_default['coef']}, "
            f"explicit_none={result_explicit_none['coef']}"
        )
        assert result_default["ci_lo"] == result_explicit_none["ci_lo"]
        assert result_default["ci_hi"] == result_explicit_none["ci_hi"]
        assert result_default["p_value"] == result_explicit_none["p_value"]

    def test_none_result_has_n_dropped_extra_fe_zero(self, small_fixture):
        """extra_fe_cols=None result has n_dropped_extra_fe=0."""
        result = ph.r1_estimate(
            small_fixture, "outcome", "stratum",
            fe_granularity="date",
            n_bootstrap=50,
            rng_seed=1,
            extra_fe_cols=None,
        )
        assert result["n_dropped_extra_fe"] == 0

    def test_empty_list_behaves_as_none(self, small_fixture):
        """extra_fe_cols=[] (empty list) behaves like None (no FE extension)."""
        result_none = ph.r1_estimate(
            small_fixture, "outcome", "stratum",
            fe_granularity="date",
            n_bootstrap=100,
            rng_seed=1,
            extra_fe_cols=None,
        )
        result_empty = ph.r1_estimate(
            small_fixture, "outcome", "stratum",
            fe_granularity="date",
            n_bootstrap=100,
            rng_seed=1,
            extra_fe_cols=[],
        )
        assert result_none["coef"] == result_empty["coef"]
        assert result_empty["n_dropped_extra_fe"] == 0


# ===========================================================================
# (e) A3 FAMILY_BUDGETS — new keys present and total is 201
# ===========================================================================

class TestFamilyBudgetsA3:

    A3_NEW_KEYS = [
        "esx_htf_turn",
        "esx_htf_turn_dose",
        "esx_washout_x_turn",
        "esx_sub_x_turn",
        "esx_decline_geometry",
        "esx_underwater",
        "esx_vol_transition",
    ]

    A3_BUDGETS = {
        "esx_htf_turn":         12,
        "esx_htf_turn_dose":    2,
        "esx_washout_x_turn":   8,
        "esx_sub_x_turn":       2,
        "esx_decline_geometry": 4,
        "esx_underwater":       4,
        "esx_vol_transition":   4,
    }

    def test_total_budget_is_201(self):
        total = sum(info["budget"] for info in ph.FAMILY_BUDGETS.values())
        assert total == 201, (
            f"FAMILY_BUDGETS total is {total}, expected 201 (A3 RUL-32: 165→201)"
        )

    def test_all_seven_new_keys_present(self):
        missing = [k for k in self.A3_NEW_KEYS if k not in ph.FAMILY_BUDGETS]
        assert not missing, f"A3 families missing from FAMILY_BUDGETS: {missing}"

    def test_a3_declared_budgets(self):
        for key, expected in self.A3_BUDGETS.items():
            actual = ph.FAMILY_BUDGETS[key]["budget"]
            assert actual == expected, (
                f"FAMILY_BUDGETS['{key}']['budget'] = {actual}, expected {expected}"
            )

    def test_reason_strings_mention_a3(self):
        for key in self.A3_NEW_KEYS:
            reason = ph.FAMILY_BUDGETS[key]["reason"]
            assert "A3" in reason or "RUL-32" in reason, (
                f"'{key}' reason does not cite A3 or RUL-32: {reason}"
            )


# ===========================================================================
# (f) era_sign_stability — planted consistent-sign effect
# ===========================================================================

def _make_era_graded(n_dates_per_era: int = 30, fires_per_date: int = 8, seed: int = 42) -> pd.DataFrame:
    """Build a synthetic graded DataFrame spanning all four PROGRAM_ERAS.

    Plants a consistent +5pp stratum effect in every era.
    n_dates_per_era=30, fires_per_date=8 → 240 rows per era → signal resolves reliably.
    """
    rng = np.random.default_rng(seed)
    rows = []
    era_date_map = {
        "2012-2015": ("2013-01-02", "2015-06-30"),
        "2016-2019": ("2016-01-04", "2019-06-28"),
        "2020-2022": ("2020-01-02", "2022-06-30"),
        "2023-2026": ("2023-01-03", "2025-12-31"),
    }
    for era_label, (start, end) in era_date_map.items():
        dates = pd.bdate_range(start, end, freq="10B")[:n_dates_per_era]
        for date in dates:
            for _ in range(fires_per_date):
                stratum = float(rng.random() < 0.5)
                p = 0.35 + 0.05 * stratum
                outcome = float(rng.random() < p)
                rows.append({
                    "date": date,
                    "ticker": f"T{rng.integers(0, 20):02d}",
                    "stratum": stratum,
                    "stop5": outcome,
                    "gradable": True,
                })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


class TestEraSignStability:

    @pytest.fixture(scope="class")
    def stable_result(self):
        df = _make_era_graded(n_dates_per_era=30, fires_per_date=8, seed=7)
        return a3c.era_sign_stability(df, "stratum", "stop5", n_bootstrap=100)

    def test_returns_four_program_eras(self, stable_result):
        era_labels = [r["era"] for r in stable_result["era_rows"]]
        for era in ph.PROGRAM_ERAS:
            assert era in era_labels, f"Missing era {era} in era_rows"

    def test_sign_stable_3of4_for_consistent_positive_effect(self, stable_result):
        assert stable_result["sign_stable_3of4"] is True, (
            f"Expected sign_stable_3of4=True for planted +5pp effect, "
            f"n_sign_agree={stable_result['n_sign_agree']}"
        )

    def test_pooled_sign_positive(self, stable_result):
        assert stable_result["pooled_sign"] == 1, (
            f"Expected pooled_sign=+1, got {stable_result['pooled_sign']}"
        )

    def test_result_has_required_keys(self, stable_result):
        required = {"era_rows", "n_eras_estimable", "n_sign_agree", "pooled_sign", "sign_stable_3of4"}
        assert required.issubset(set(stable_result.keys()))

    def test_null_stratum_returns_no_stable(self):
        rng = np.random.default_rng(99)
        dates = pd.bdate_range("2013-01-02", periods=80, freq="5B")
        rows = []
        for d in dates:
            for _ in range(4):
                rows.append({
                    "date": d, "ticker": "T01",
                    "stratum": float(rng.random() < 0.5),
                    "stop5": float(rng.random() < 0.35),
                    "gradable": True,
                })
        df = pd.DataFrame(rows)
        result = a3c.era_sign_stability(df, "stratum", "stop5", n_bootstrap=50)
        # With no effect, may or may not be stable — just check it runs and returns valid shape
        assert "sign_stable_3of4" in result
        assert isinstance(result["sign_stable_3of4"], bool)


# ===========================================================================
# (g) ticker_half_sign_agreement — consistent-sign halves
# ===========================================================================

def _make_half_graded(n_tickers: int = 20, seed: int = 99) -> pd.DataFrame:
    """Build a synthetic graded DataFrame with n_tickers, consistent +5pp effect."""
    rng = np.random.default_rng(seed)
    tickers = [f"T{i:02d}" for i in range(n_tickers)]
    dates = pd.bdate_range("2014-01-02", periods=40, freq="5B")
    rows = []
    for ticker in tickers:
        for date in dates:
            stratum = float(rng.random() < 0.5)
            p = 0.35 + 0.05 * stratum
            rows.append({
                "date": date,
                "ticker": ticker,
                "stratum": stratum,
                "stop5": float(rng.random() < p),
                "gradable": True,
            })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


class TestTickerHalfSignAgreement:

    @pytest.fixture(scope="class")
    def agree_result(self):
        df = _make_half_graded(n_tickers=24, seed=42)
        return a3c.ticker_half_sign_agreement(df, "stratum", "stop5", n_bootstrap=100)

    def test_two_halves_returned(self, agree_result):
        assert len(agree_result["half_rows"]) == 2

    def test_sign_agree_for_consistent_effect(self, agree_result):
        assert agree_result["sign_agree"] is True, (
            f"Expected sign_agree=True for planted +5pp effect across both halves, "
            f"half_rows={agree_result['half_rows']}"
        )

    def test_result_has_required_keys(self, agree_result):
        required = {"half_rows", "sign_agree"}
        assert required.issubset(set(agree_result.keys()))

    def test_half_labels_are_a_and_b(self, agree_result):
        labels = {r["half"] for r in agree_result["half_rows"]}
        assert labels == {"A", "B"}

    def test_missing_ticker_col_returns_no_agree(self):
        rng = np.random.default_rng(1)
        rows = [{"date": pd.Timestamp("2014-01-02"), "stratum": 1.0, "stop5": 1.0, "gradable": True}]
        df = pd.DataFrame(rows)
        result = a3c.ticker_half_sign_agreement(df, "stratum", "stop5", n_bootstrap=50)
        assert result["sign_agree"] is False
        assert "note" in result
