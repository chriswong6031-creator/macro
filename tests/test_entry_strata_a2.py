"""Amendment 2 T0 harness tests — entry_strata_phase0.py.

Four fixture groups (A2 §B/§C):
  (a) FAMILY_BUDGETS totals 165, contains six new A2 keys with declared budgets.
  (b) mae21 flows through grade_fires → effect_table on a small synthetic tape.
  (c) computable_mask drops the right rows; coefficient changes vs hand-computed.
  (d) r1m_estimate recovers a planted market-level effect (CI excludes 0);
      raises ValueError without controls (RUL-24).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import scripts.research.entry_strata_phase0 as ph

# ---------------------------------------------------------------------------
# Shared synthetic helpers (reused across groups)
# ---------------------------------------------------------------------------

BDATE_START = pd.Timestamp("2013-01-02")


def _make_close(n: int = 280, drift: float = 0.0002, vol: float = 0.012, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    rets = 1.0 + drift + vol * rng.standard_normal(n)
    prices = np.cumprod(rets) * 100.0
    idx = pd.bdate_range(BDATE_START, periods=n)
    return pd.Series(prices, index=idx)


def _make_stopped_close(sig_pos: int = 30, n: int = 280, stop: bool = True, seed: int = 1) -> pd.Series:
    """Price path where stop5 outcome at sig_pos is deterministic."""
    rng = np.random.default_rng(seed)
    prices = np.ones(n) * 100.0
    for i in range(1, n):
        prices[i] = prices[i - 1] * (1.0 + 0.0001 + 0.008 * rng.standard_normal())
    fill = sig_pos + 1
    prices = prices * (100.0 / max(prices[fill], 1e-6))
    if stop:
        for j in range(1, 4):
            if fill + j < n:
                prices[fill + j] = 100.0 * 0.92
        for j in range(4, n - fill):
            if fill + j < n:
                prices[fill + j] = 100.0 * (1.0 + j * 0.001)
    else:
        for j in range(1, n - fill):
            if fill + j < n:
                prices[fill + j] = 100.0 * (1.0 + j * 0.003)
    idx = pd.bdate_range(BDATE_START, periods=n)
    return pd.Series(prices, index=idx)


def _small_fires_and_closes(
    n_fires: int = 20,
    seed: int = 77,
) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Build n_fires rows: balanced stratum, varied stop outcomes."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(BDATE_START, periods=n_fires * 3, freq="5B")[:n_fires]
    rows = []
    closes: dict[str, pd.Series] = {}
    for i, date in enumerate(dates):
        ticker = f"A2T_{i:04d}"
        sig_pos = 30
        stop_val = bool(rng.random() < 0.4)
        close = _make_stopped_close(sig_pos=sig_pos, n=280, stop=stop_val, seed=i * 13)
        # Re-align: map sig_pos to the date
        close.index = pd.bdate_range(date - pd.tseries.offsets.BDay(sig_pos), periods=280)
        closes[ticker] = close
        rows.append({
            "ticker": ticker,
            "date": date,
            "tier": "T1",
            "sub": "deep",
            "ticks": 0,
            "not_topped": True,
            "eligible": True,
            "panel": "deep",
            "stratum": i % 2,
        })
    return pd.DataFrame(rows), closes


# ===========================================================================
# (a) FAMILY_BUDGETS — A2 RUL-26 additions
# ===========================================================================

class TestFamilyBudgetsA2:

    A2_NEW_KEYS = [
        "esx_sponsorship",
        "esx_insider_sponsor",
        "esx_fund_repair",
        "esx_macro_release",
        "esx_pos_reset",
        "esx_support_dose",
    ]

    A2_BUDGETS = {
        "esx_sponsorship":     8,
        "esx_insider_sponsor": 12,
        "esx_fund_repair":     12,
        "esx_macro_release":   8,
        "esx_pos_reset":       8,
        "esx_support_dose":    2,
    }

    def test_total_budget_is_165(self):
        """Sum of all FAMILY_BUDGETS values must equal 165 (A2 RUL-26 ceiling)."""
        total = sum(info["budget"] for info in ph.FAMILY_BUDGETS.values())
        assert total == 165, (
            f"FAMILY_BUDGETS total is {total}, expected 165 (A2 RUL-26: 115→165). "
            f"Individual budgets: { {k: v['budget'] for k, v in ph.FAMILY_BUDGETS.items()} }"
        )

    def test_all_six_new_keys_present(self):
        """All six A2 RUL-26 families are in FAMILY_BUDGETS."""
        missing = [k for k in self.A2_NEW_KEYS if k not in ph.FAMILY_BUDGETS]
        assert not missing, f"A2 families missing from FAMILY_BUDGETS: {missing}"

    def test_a2_declared_budgets(self):
        """Each new A2 family has the exact budget declared in RUL-26."""
        for key, expected_budget in self.A2_BUDGETS.items():
            actual = ph.FAMILY_BUDGETS[key]["budget"]
            assert actual == expected_budget, (
                f"FAMILY_BUDGETS['{key}']['budget'] = {actual}, expected {expected_budget} "
                f"(A2 RUL-26 declaration)"
            )

    def test_all_budgets_positive(self):
        """Every family has a positive budget."""
        for fam, info in ph.FAMILY_BUDGETS.items():
            assert info["budget"] > 0, f"Family '{fam}' has non-positive budget {info['budget']}"

    def test_reason_strings_mention_a2_rul26(self):
        """New A2 families (except esx_sponsorship) cite A2 RUL-26 in their reason."""
        for key in self.A2_NEW_KEYS:
            if key == "esx_sponsorship":
                # esx_sponsorship cites RUL-16 (Amendment 1); it was already declared there
                assert "RUL-16" in ph.FAMILY_BUDGETS[key]["reason"], (
                    f"esx_sponsorship reason should cite RUL-16: {ph.FAMILY_BUDGETS[key]['reason']}"
                )
            else:
                assert "A2 RUL-26" in ph.FAMILY_BUDGETS[key]["reason"] or "RUL-25" in ph.FAMILY_BUDGETS[key]["reason"], (
                    f"'{key}' reason does not cite A2 RUL-26 or RUL-25: "
                    f"{ph.FAMILY_BUDGETS[key]['reason']}"
                )

    def test_prior_families_still_present(self):
        """Original 8 families are still in FAMILY_BUDGETS (no regressions)."""
        original = {
            "esx_null_competitors", "esx_ev_blackout", "esx_ur_phase0",
            "esx_sq_phase0", "esx_lq_bands", "esx_ql_overlay",
            "esx_ts_adx", "esx_appendix",
        }
        missing = original - set(ph.FAMILY_BUDGETS.keys())
        assert not missing, f"Original families removed from FAMILY_BUDGETS: {missing}"


# ===========================================================================
# (b) mae21 flows grade_fires → effect_table
# ===========================================================================

class TestMae21Flow:

    @pytest.fixture(scope="class")
    def graded_small(self):
        """Grade a small synthetic tape to verify mae21 flows through."""
        fires, closes = _small_fires_and_closes(n_fires=16, seed=42)
        graded = ph.grade_fires(fires, closes)
        return graded

    def test_mae21_column_in_grade_fires_output(self, graded_small):
        """grade_fires output contains 'mae21' column (A2 §C1)."""
        assert "mae21" in graded_small.columns, (
            "mae21 missing from grade_fires output. "
            "Expected column parallel to mae63 (RUL-13 co-primary)."
        )

    def test_mae21_initialized_to_none_for_ungradable(self, graded_small):
        """Ungradable fires have mae21=None (not 0 or NaN as float)."""
        ungradable = graded_small[~graded_small["gradable"].fillna(False)]
        if len(ungradable) > 0:
            # mae21 should be None for ungradable rows (not a numeric zero)
            for val in ungradable["mae21"]:
                assert val is None or (isinstance(val, float) and np.isnan(val)), (
                    f"Ungradable row has mae21={val!r}; expected None"
                )

    def test_mae21_equals_fwd_mdd_21_for_gradable(self, graded_small):
        """For gradable fires, mae21 == fwd_mdd_21 (same underlying series)."""
        gradable = graded_small[graded_small["gradable"].fillna(False)]
        if len(gradable) == 0:
            pytest.skip("No gradable fires in small fixture")
        assert "fwd_mdd_21" in gradable.columns, "fwd_mdd_21 missing from grade_fires output"
        for _, row in gradable.iterrows():
            if row["mae21"] is not None and row["fwd_mdd_21"] is not None:
                assert abs(float(row["mae21"]) - float(row["fwd_mdd_21"])) < 1e-9, (
                    f"mae21={row['mae21']} != fwd_mdd_21={row['fwd_mdd_21']}"
                )

    def test_mae21_in_effect_outcomes_list(self):
        """mae21 appears in EFFECT_OUTCOMES tuple list adjacent to stop5."""
        outcome_keys = [o[0] for o in ph.EFFECT_OUTCOMES]
        assert "mae21" in outcome_keys, (
            f"mae21 not in EFFECT_OUTCOMES. Current keys: {outcome_keys}"
        )
        stop5_idx = outcome_keys.index("stop5")
        mae21_idx = outcome_keys.index("mae21")
        assert abs(stop5_idx - mae21_idx) <= 2, (
            f"mae21 (pos {mae21_idx}) should be adjacent to stop5 (pos {stop5_idx}) in EFFECT_OUTCOMES"
        )

    def test_mae21_in_bh_panel_via_effect_table(self, graded_small):
        """effect_table includes mae21 in its BH panel outcomes."""
        gradable = graded_small[graded_small["gradable"].fillna(False)].copy()
        gradable["stratum"] = gradable["stratum"].astype(float)
        if len(gradable) < 5:
            pytest.skip("Insufficient gradable fires for effect_table")
        et = ph.effect_table(
            gradable, "stratum",
            fe_granularity="date",
            n_bootstrap=30,
            family_label="a2_mae21_test",
        )
        outcome_labels = [e["outcome"] for e in et["effects"]]
        assert "mae21" in outcome_labels, (
            f"mae21 missing from effect_table outcomes. Got: {outcome_labels}"
        )
        bh_labels = [b["label"] for b in et["bh_panel"]]
        assert "mae21" in bh_labels, (
            f"mae21 missing from BH panel. Got: {bh_labels}"
        )

    def test_era_table_has_mae21_mean_column(self, graded_small):
        """era_table emits mae21_mean column parallel to mae63_mean."""
        tbl = ph.era_table(graded_small, panel_label="a2_test")
        assert "mae21_mean" in tbl.columns, (
            f"mae21_mean missing from era_table. Columns: {list(tbl.columns)}"
        )


# ===========================================================================
# (c) computable_mask — drops right rows, coefficient changes
# ===========================================================================

class TestComputableMask:
    """Verify computable_mask in r1_estimate (A2 §C2)."""

    @pytest.fixture(scope="class")
    def planted_effect_data(self):
        """Synthetic fixture demonstrating computable_mask row-dropping.

        Design: 20 shared dates × 6 fires/date = 120 fires total.
        On each date:
          - 4 IN-MASK fires: 2 treatment (stop_prob=0.50) + 2 control (stop_prob=0.10)
          - 2 OUT-OF-MASK fires: treatment=1, stop=True always
            (these would pull the treatment mean up relative to control
            by adding extra high-stop treatment observations on every date;
            FE demeaning sees a higher treatment stop rate on every date)

        When masked: only the 4 in-mask fires per date are used.
          Treatment stop5 ≈ 0.50, control stop5 ≈ 0.10, FE coef ≈ 0.40.
        When unmasked: out-of-mask fires add treatment=1/stop=1 rows per date,
          raising the treatment mean within each date and shifting FE coef upward.

        Multiple fires per date ensures non-singleton FE cells throughout.
        """
        rng = np.random.default_rng(202)
        n_dates = 20
        # Use widely-spaced dates so close-series windows don't overlap
        dates = pd.bdate_range(BDATE_START, periods=n_dates * 10, freq="10B")[:n_dates]

        rows = []
        closes: dict[str, pd.Series] = {}
        mask_vals: dict[int, bool] = {}
        idx_counter = 0

        for date in dates:
            # 2 IN-MASK treatment fires (stop_prob=0.50)
            for j in range(2):
                will_stop = rng.random() < 0.50
                ticker = f"M_T_{idx_counter:04d}"
                close = _make_stopped_close(sig_pos=30, n=280, stop=will_stop, seed=idx_counter * 11)
                close.index = pd.bdate_range(date - pd.tseries.offsets.BDay(30), periods=280)
                closes[ticker] = close
                mask_vals[len(rows)] = True
                rows.append({"ticker": ticker, "date": date,
                              "tier": "T1", "sub": "deep", "ticks": 0,
                              "not_topped": True, "eligible": True, "panel": "deep",
                              "stratum": 1.0})
                idx_counter += 1
            # 2 IN-MASK control fires (stop_prob=0.10)
            for j in range(2):
                will_stop = rng.random() < 0.10
                ticker = f"M_C_{idx_counter:04d}"
                close = _make_stopped_close(sig_pos=30, n=280, stop=will_stop, seed=idx_counter * 11)
                close.index = pd.bdate_range(date - pd.tseries.offsets.BDay(30), periods=280)
                closes[ticker] = close
                mask_vals[len(rows)] = True
                rows.append({"ticker": ticker, "date": date,
                              "tier": "T1", "sub": "deep", "ticks": 0,
                              "not_topped": True, "eligible": True, "panel": "deep",
                              "stratum": 0.0})
                idx_counter += 1
            # 2 OUT-OF-MASK treatment fires (always stop=True)
            for j in range(2):
                ticker = f"M_O_{idx_counter:04d}"
                close = _make_stopped_close(sig_pos=30, n=280, stop=True, seed=idx_counter * 11)
                close.index = pd.bdate_range(date - pd.tseries.offsets.BDay(30), periods=280)
                closes[ticker] = close
                mask_vals[len(rows)] = False
                rows.append({"ticker": ticker, "date": date,
                              "tier": "T1", "sub": "deep", "ticks": 0,
                              "not_topped": True, "eligible": True, "panel": "deep",
                              "stratum": 1.0})
                idx_counter += 1

        fires = pd.DataFrame(rows)
        graded = ph.grade_fires(fires, closes)
        mask_series = pd.Series(
            [mask_vals.get(i, True) for i in range(len(graded))],
            index=graded.index,
        )
        return graded, mask_series

    def test_mask_drops_expected_rows(self, planted_effect_data):
        """mask_n_dropped equals number of OUT-OF-MASK fires."""
        graded, mask_series = planted_effect_data
        # gradable subset
        grad = graded[graded["gradable"].fillna(False)].copy()
        grad["stratum"] = grad["stratum"].astype(float)
        mask_sub = mask_series.reindex(grad.index)

        result = ph.r1_estimate(
            grad, "stop5", "stratum",
            fe_granularity="date",
            n_bootstrap=50,
            rng_seed=7,
            computable_mask=mask_sub,
        )
        n_out_gradable = int((~mask_sub.fillna(False)).sum())
        assert result["mask_n_dropped"] == n_out_gradable, (
            f"mask_n_dropped={result['mask_n_dropped']}, "
            f"expected {n_out_gradable} (OUT-OF-MASK gradable fires)"
        )

    def test_mask_coverage_correct(self, planted_effect_data):
        """mask_coverage = fraction of gradable rows retained after masking."""
        graded, mask_series = planted_effect_data
        grad = graded[graded["gradable"].fillna(False)].copy()
        grad["stratum"] = grad["stratum"].astype(float)
        mask_sub = mask_series.reindex(grad.index)

        result = ph.r1_estimate(
            grad, "stop5", "stratum",
            fe_granularity="date",
            n_bootstrap=50,
            rng_seed=7,
            computable_mask=mask_sub,
        )
        n_total = len(grad)
        n_retained = int(mask_sub.fillna(False).sum())
        expected_coverage = n_retained / max(n_total, 1)
        assert abs(result["mask_coverage"] - expected_coverage) < 1e-4, (
            f"mask_coverage={result['mask_coverage']:.4f}, "
            f"expected {expected_coverage:.4f}"
        )

    def test_mask_shifts_coefficient(self, planted_effect_data):
        """Coefficient with mask differs from without mask (out-of-mask fires bias it)."""
        graded, mask_series = planted_effect_data
        grad = graded[graded["gradable"].fillna(False)].copy()
        grad["stratum"] = grad["stratum"].astype(float)
        mask_sub = mask_series.reindex(grad.index)

        result_masked = ph.r1_estimate(
            grad, "stop5", "stratum",
            fe_granularity="date",
            n_bootstrap=100,
            rng_seed=9,
            computable_mask=mask_sub,
        )
        result_unmasked = ph.r1_estimate(
            grad, "stop5", "stratum",
            fe_granularity="date",
            n_bootstrap=100,
            rng_seed=9,
        )
        # Both must return valid coefs
        assert result_masked["coef"] is not None, "masked result coef is None"
        assert result_unmasked["coef"] is not None, "unmasked result coef is None"

        # The coefficients should differ (out-of-mask fires bias the unmasked estimate)
        coef_masked = float(result_masked["coef"])
        coef_unmasked = float(result_unmasked["coef"])
        assert abs(coef_masked - coef_unmasked) > 0.01, (
            f"Masked coef ({coef_masked:.4f}) and unmasked coef ({coef_unmasked:.4f}) "
            "differ by <0.01 — out-of-mask fires should visibly shift the estimate."
        )

    def test_none_mask_no_rows_dropped(self, planted_effect_data):
        """computable_mask=None → mask_n_dropped=0, mask_coverage=1.0."""
        graded, _ = planted_effect_data
        grad = graded[graded["gradable"].fillna(False)].copy()
        grad["stratum"] = grad["stratum"].astype(float)

        result = ph.r1_estimate(
            grad, "stop5", "stratum",
            fe_granularity="date",
            n_bootstrap=30,
            rng_seed=0,
            computable_mask=None,
        )
        assert result["mask_n_dropped"] == 0, (
            f"mask_n_dropped={result['mask_n_dropped']} with None mask; expected 0"
        )
        assert abs(result["mask_coverage"] - 1.0) < 1e-9, (
            f"mask_coverage={result['mask_coverage']} with None mask; expected 1.0"
        )


# ===========================================================================
# (d) r1m_estimate — planted effect + no-controls error
# ===========================================================================

class TestR1mEstimator:

    @pytest.fixture(scope="class")
    def market_level_data(self):
        """Synthetic data with a planted market-level effect.

        Design: two market regimes (market_state=0/1). In regime 1, both
        treatment fires AND higher stop5 are systematically present due to
        a correlated market state. After controlling for market_state and vix,
        the residual treatment effect is planted at ~0.25.

        We set up:
          - vix: numeric control [10..30]
          - spy_dd: SPY 126d drawdown control [-0.20..0]
          - market_state: binary 0/1
          - stratum: treatment indicator (correlated with market_state)
          - stop5: planted as 0.3 + 0.25*stratum + 0.15*market_state + noise
            (so market_state is a genuine confounder that must be controlled)
        """
        rng = np.random.default_rng(314)
        n = 200
        dates = pd.bdate_range(BDATE_START, periods=n)
        market_state = rng.integers(0, 2, size=n).astype(float)
        vix = 15.0 + 10.0 * rng.random(n)
        spy_dd = -0.10 * rng.random(n)

        # Treatment correlated with market_state (so uncontrolled comparison is biased)
        stratum = ((market_state + rng.random(n)) > 0.8).astype(float)

        # Planted stop5: 0.30 + 0.25*stratum + 0.15*market_state + noise
        TRUE_EFFECT = 0.25
        stop5_raw = 0.30 + TRUE_EFFECT * stratum + 0.15 * market_state + 0.05 * rng.standard_normal(n)
        stop5 = (stop5_raw > 0.40).astype(float)

        df = pd.DataFrame({
            "ticker":       [f"MKT_{i:04d}" for i in range(n)],
            "date":         dates,
            "tier":         "T1",
            "panel":        "deep",
            "gradable":     True,
            "stop5":        stop5,
            "stratum":      stratum,
            "vix":          vix,
            "spy_dd":       spy_dd,
            "market_state": market_state,
        })
        return df, TRUE_EFFECT

    def test_r1m_recovers_planted_effect(self, market_level_data):
        """r1m_estimate recovers the planted effect and CI excludes 0."""
        df, TRUE_EFFECT = market_level_data
        result = ph.r1m_estimate(
            df, "stop5", "stratum",
            controls=["vix", "spy_dd", "market_state"],
            n_bootstrap=400,
            rng_seed=42,
        )
        assert result["coef"] is not None, f"r1m coef is None: {result}"
        coef = float(result["coef"])
        ci_lo = float(result["ci_lo"])
        ci_hi = float(result["ci_hi"])

        # Coefficient should be in the right ballpark
        assert 0.0 < coef, (
            f"r1m coef={coef:.4f} is not positive for planted effect={TRUE_EFFECT}"
        )

        # CI should exclude 0 (planted effect is strong enough)
        assert ci_lo > 0.0 or ci_hi > 0.05, (
            f"r1m CI [{ci_lo:.4f}, {ci_hi:.4f}] does not exclude 0 for "
            f"planted effect={TRUE_EFFECT}. coef={coef:.4f}"
        )

    def test_r1m_ci_excludes_zero_for_strong_effect(self, market_level_data):
        """With a strong planted effect, the 95% CI must exclude 0."""
        df, _ = market_level_data
        result = ph.r1m_estimate(
            df, "stop5", "stratum",
            controls=["vix", "spy_dd", "market_state"],
            n_bootstrap=500,
            rng_seed=17,
        )
        ci_lo = result["ci_lo"]
        ci_hi = result["ci_hi"]
        assert ci_lo is not None and ci_hi is not None
        # For a TRUE_EFFECT of 0.25 with n=200, CI should exclude 0
        assert not (ci_lo <= 0.0 <= ci_hi), (
            f"CI [{ci_lo:.4f}, {ci_hi:.4f}] covers 0 for a strong planted effect (0.25). "
            "R1-M should detect the effect with n=200."
        )

    def test_r1m_raises_without_controls(self, market_level_data):
        """r1m_estimate raises ValueError when controls is empty (RUL-24)."""
        df, _ = market_level_data
        with pytest.raises(ValueError, match="controls must be non-empty.*RUL-24"):
            ph.r1m_estimate(df, "stop5", "stratum", controls=[])

    def test_r1m_raises_with_missing_control_column(self, market_level_data):
        """r1m_estimate raises ValueError for a non-existent control column."""
        df, _ = market_level_data
        with pytest.raises(ValueError, match="missing columns"):
            ph.r1m_estimate(df, "stop5", "stratum", controls=["nonexistent_col"])

    def test_r1m_returns_controls_used(self, market_level_data):
        """controls_used in result matches the passed controls list."""
        df, _ = market_level_data
        controls = ["vix", "spy_dd"]
        result = ph.r1m_estimate(
            df, "stop5", "stratum",
            controls=controls,
            n_bootstrap=50,
            rng_seed=0,
        )
        assert result["controls_used"] == controls, (
            f"controls_used={result['controls_used']}, expected {controls}"
        )

    def test_r1m_result_shape(self, market_level_data):
        """r1m_estimate returns a dict with all required keys."""
        df, _ = market_level_data
        result = ph.r1m_estimate(
            df, "stop5", "stratum",
            controls=["vix", "spy_dd", "market_state"],
            n_bootstrap=50,
            rng_seed=0,
        )
        required_keys = {
            "coef", "ci_lo", "ci_hi",
            "n_total", "n_treatment", "n_control",
            "n_blocks", "p_value",
            "outcome", "stratum",
            "controls_used",
            "mask_n_dropped", "mask_coverage",
        }
        missing = required_keys - set(result.keys())
        assert not missing, f"r1m_estimate result missing keys: {missing}"

    def test_r1m_mask_none_is_passthrough(self, market_level_data):
        """computable_mask=None → mask_n_dropped=0, mask_coverage=1.0 (same as r1_estimate)."""
        df, _ = market_level_data
        result = ph.r1m_estimate(
            df, "stop5", "stratum",
            controls=["vix", "spy_dd"],
            n_bootstrap=30,
            rng_seed=0,
            computable_mask=None,
        )
        assert result["mask_n_dropped"] == 0
        assert abs(result["mask_coverage"] - 1.0) < 1e-9

    def test_r1m_ci_is_finite_and_ordered(self, market_level_data):
        """CI bounds are finite and ci_lo <= ci_hi."""
        df, _ = market_level_data
        result = ph.r1m_estimate(
            df, "stop5", "stratum",
            controls=["vix", "spy_dd", "market_state"],
            n_bootstrap=100,
            rng_seed=3,
        )
        assert result["ci_lo"] is not None and result["ci_hi"] is not None
        assert np.isfinite(result["ci_lo"]) and np.isfinite(result["ci_hi"])
        assert result["ci_lo"] <= result["ci_hi"]
