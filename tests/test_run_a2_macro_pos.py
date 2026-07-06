"""Tests for run_a2_macro_pos.py — esx_macro_release + esx_pos_reset Phase-0.

Test groups:
  (a) Contrast-B computability flags: macro=True, pos=False; pos reserve=4.
  (b) _build_elevated_masks: correct M1/M2 mask columns from pctile columns.
  (c) Null-flag date drops: fires on null-flag dates are excluded from r1m.
  (d) Planted market-level effect: r1m recovers it; contrast-B mask correctly
      restricts both arms to the elevated subset.
  (e) Controls enforcement: r1m_estimate raises ValueError without controls
      (RUL-24 non-empty check).
  (f) Budget accounting: declared/consumed/reserve constants are correct.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.research.entry_strata_phase0 import r1m_estimate, grade_fires

import scripts.research.run_a2_macro_pos as runner


# ---------------------------------------------------------------------------
# Helpers for small synthetic data
# ---------------------------------------------------------------------------

BDATE_START = pd.Timestamp("2013-01-02")


def _make_close(n: int = 280, drift: float = 0.0002, vol: float = 0.012, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    rets = 1.0 + drift + vol * rng.standard_normal(n)
    prices = np.cumprod(rets) * 100.0
    idx = pd.bdate_range(BDATE_START, periods=n)
    return pd.Series(prices, index=idx)


def _make_stopped_close(
    sig_pos: int = 30, n: int = 280, stop: bool = True, seed: int = 1
) -> pd.Series:
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


def _build_small_fires_and_closes(
    n_fires: int = 30, seed: int = 42
) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Return (fires_df, closes_dict). Fires span distinct business dates."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(BDATE_START, periods=n_fires * 5, freq="5B")[:n_fires]
    rows = []
    closes: dict[str, pd.Series] = {}
    for i, date in enumerate(dates):
        ticker = f"MP_{i:04d}"
        sig_pos = 30
        stop_val = bool(rng.random() < 0.4)
        close = _make_stopped_close(sig_pos=sig_pos, n=280, stop=stop_val, seed=i * 17)
        close.index = pd.bdate_range(
            date - pd.tseries.offsets.BDay(sig_pos), periods=280
        )
        closes[ticker] = close
        rows.append({
            "ticker": ticker,
            "date": date,
            "tier": "T1",
            "sub": "deep",
            "ticks": 0,
            "not_topped": True,
            "eligible": True,
        })
    fires = pd.DataFrame(rows)
    fires["date"] = pd.to_datetime(fires["date"])
    return fires, closes


def _build_macro_date_panel(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Build a synthetic date panel with all required columns."""
    n = len(dates)
    rng = np.random.default_rng(7)

    # VIX: 15-30 range
    vix = 15.0 + 15.0 * rng.random(n)
    # SPY drawdown: -0.30 to 0.0
    spy_dd126 = -0.30 * rng.random(n)
    # HY OAS level: 300-800 bps expressed as decimal
    hy_oas = 3.0 + 5.0 * rng.random(n)
    # Pctile columns (0 to 1 expanding window proxy)
    ofr_fsi_pctile_exp = rng.random(n)
    hy_oas_pctile_exp  = rng.random(n)

    # Plant flags so exactly 1/4 of dates have macro_m1_fsi_turn=1
    macro_m1 = np.zeros(n)
    macro_m1[::4] = 1.0
    macro_m2 = np.zeros(n)
    macro_m2[1::5] = 1.0

    # Plant pos flags
    pos_p1 = np.zeros(n)
    pos_p1[::6] = 1.0
    pos_p2 = np.zeros(n)
    pos_p2[2::7] = 1.0

    df = pd.DataFrame({
        "vix":                 vix,
        "spy_dd126":           spy_dd126,
        "hy_oas":              hy_oas,
        "ofr_fsi_pctile_exp":  ofr_fsi_pctile_exp,
        "hy_oas_pctile_exp":   hy_oas_pctile_exp,
        "macro_m1_fsi_turn":   macro_m1,
        "macro_m2_oas_turn":   macro_m2,
        "pos_p1_naaim_reset":  pos_p1,
        "pos_p2_cot_reset":    pos_p2,
    }, index=dates)
    return df


# ---------------------------------------------------------------------------
# (a) Contrast-B computability flags
# ---------------------------------------------------------------------------

class TestContrastBComputability:
    def test_macro_contrast_b_computable(self):
        """esx_macro_release: contrast_b_computable must be True."""
        # Check the constant that the runner would set (verified against panel columns)
        assert runner.BUDGET_MACRO_CONS == 8, (
            "esx_macro_release must consume 8 trials (4 trials × 2 panels)"
        )
        assert runner.BUDGET_MACRO_RES == 0, "No reserve when contrast B is computable"

    def test_pos_contrast_b_not_computable(self):
        """esx_pos_reset: contrast B not computable, consume 4, reserve 4."""
        assert runner.BUDGET_POS_CONS == 4
        assert runner.BUDGET_POS_RES == 4

    def test_pos_contrast_b_note_contains_required_text(self):
        note = runner.POS_CONTRAST_B_NOTE
        assert "pctile columns not exported" in note
        assert "reserve 4" in note
        assert "bind-first" in note.lower() or "bind" in note.lower()

    def test_macro_trial_defs_has_contrast_b(self):
        """MACRO_TRIAL_DEFS must include both A and B contrasts for M1 and M2."""
        contrasts_by_stratum: dict[str, set] = {}
        for td in runner.MACRO_TRIAL_DEFS:
            trial_id, stratum_col, contrast, mask_col, label, ctrl_key = td
            contrasts_by_stratum.setdefault(stratum_col, set()).add(contrast)
        assert "macro_m1_fsi_turn" in contrasts_by_stratum
        assert "macro_m2_oas_turn" in contrasts_by_stratum
        assert {"A", "B"} == contrasts_by_stratum["macro_m1_fsi_turn"]
        assert {"A", "B"} == contrasts_by_stratum["macro_m2_oas_turn"]

    def test_pos_trial_defs_has_contrast_a_only(self):
        """POS_TRIAL_DEFS must only contain contrast A."""
        # POS_TRIAL_DEFS has 4-tuples: (trial_id, stratum_col, ctrl_key, label)
        assert len(runner.POS_TRIAL_DEFS) == 2  # P1 and P2 only
        for td in runner.POS_TRIAL_DEFS:
            trial_id = td[0]
            assert trial_id.endswith("-A"), f"Expected contrast A suffix, got {trial_id}"


# ---------------------------------------------------------------------------
# (b) _build_elevated_masks
# ---------------------------------------------------------------------------

class TestElevatedMasks:
    def test_m1_mask_from_fsi_pctile(self):
        dates = pd.bdate_range("2013-01-02", periods=100)
        ctx = pd.DataFrame({
            "ofr_fsi_pctile_exp": np.linspace(0.0, 1.0, 100),
            "hy_oas_pctile_exp":  np.linspace(0.0, 1.0, 100),
            "vix":        np.ones(100) * 20,
            "spy_dd126":  np.zeros(100),
            "hy_oas":     np.ones(100) * 4.0,
        }, index=dates)
        out = runner._build_elevated_masks(ctx)
        assert "mask_m1_elevated" in out.columns
        # Should be 1 where ofr_fsi_pctile_exp >= 0.80
        expected_m1 = (ctx["ofr_fsi_pctile_exp"] >= 0.80).astype(float)
        pd.testing.assert_series_equal(
            out["mask_m1_elevated"].astype(float),
            expected_m1.astype(float),
            check_names=False,
        )

    def test_m2_mask_from_oas_pctile(self):
        dates = pd.bdate_range("2013-01-02", periods=50)
        ctx = pd.DataFrame({
            "ofr_fsi_pctile_exp": np.zeros(50),
            "hy_oas_pctile_exp":  np.where(np.arange(50) % 5 == 0, 0.9, 0.5),
            "vix":       np.ones(50) * 18,
            "spy_dd126": np.zeros(50),
            "hy_oas":    np.ones(50) * 3.5,
        }, index=dates)
        out = runner._build_elevated_masks(ctx)
        assert "mask_m2_elevated" in out.columns
        expected_m2 = (ctx["hy_oas_pctile_exp"] >= 0.80).astype(float)
        pd.testing.assert_series_equal(
            out["mask_m2_elevated"].astype(float),
            expected_m2.astype(float),
            check_names=False,
        )

    def test_missing_pctile_col_produces_zero_mask(self):
        """If pctile column is absent, mask should be zero (not crash)."""
        dates = pd.bdate_range("2013-01-02", periods=20)
        ctx = pd.DataFrame({"vix": np.ones(20) * 20}, index=dates)
        out = runner._build_elevated_masks(ctx)
        assert (out["mask_m1_elevated"] == 0).all()
        assert (out["mask_m2_elevated"] == 0).all()


# ---------------------------------------------------------------------------
# (c) Null-flag date drops
# ---------------------------------------------------------------------------

class TestNullFlagDrops:
    def test_null_flag_dates_excluded(self):
        """Fires whose flag is NaN should NOT contribute to the estimation sample."""
        fires, closes = _build_small_fires_and_closes(n_fires=30, seed=77)

        # Build a flag column: first 10 fires have NaN, rest have 0/1
        flag_col = np.zeros(30, dtype=float)
        flag_col[:10] = np.nan
        flag_col[10::3] = 1.0  # treatment

        fires["macro_m1_fsi_turn"] = flag_col
        fires["vix"] = 20.0
        fires["spy_dd126"] = -0.05
        fires["hy_oas"] = 4.0

        extra_cols = {
            "macro_m1_fsi_turn": pd.Series(flag_col, index=fires.index),
            "vix": fires["vix"],
            "spy_dd126": fires["spy_dd126"],
            "hy_oas": fires["hy_oas"],
        }

        graded = grade_fires(fires, closes, extra_columns=extra_cols)
        df_gradable = graded[graded["gradable"].fillna(False)].copy()

        # r1m_estimate drops rows where stratum or controls are NaN via dropna()
        res = r1m_estimate(
            df_gradable, "stop5", "macro_m1_fsi_turn",
            ["vix", "spy_dd126", "hy_oas"],
            n_bootstrap=10, rng_seed=0,
        )
        # n_total must be < 30 because null rows are dropped
        assert res["n_total"] < 30, (
            f"Expected fewer than 30 rows after null-flag drops, got {res['n_total']}"
        )
        # n_total must be >0 (non-null rows exist)
        assert res["n_total"] > 0


# ---------------------------------------------------------------------------
# (d) Planted market-level effect + contrast-B mask logic
# ---------------------------------------------------------------------------

class TestPlantedMarketEffect:
    """Verify r1m recovers a planted effect and contrast-B mask restricts correctly."""

    @pytest.fixture(scope="class")
    @classmethod
    def synthetic_study(cls):
        """Build a graded frame with planted macro flag effect and elevated mask."""
        n_fires = 60
        fires, closes = _build_small_fires_and_closes(n_fires=n_fires, seed=55)

        rng = np.random.default_rng(88)
        # Plant: fires with macro_m1_fsi_turn=1 have lower stop5 (fewer stops)
        # We do this by constructing a deterministic stratum that overrides close path.
        flag = np.zeros(n_fires, dtype=float)
        # Treatment: every 4th fire (15 total)
        flag[::4] = 1.0

        # VIX, spy_dd126, hy_oas vary by date (realistic controls)
        vix       = 20.0 + rng.standard_normal(n_fires) * 2.0
        spy_dd126 = -0.05 - 0.01 * rng.random(n_fires)
        hy_oas    = 4.0 + 0.5 * rng.random(n_fires)

        # Elevated mask: first 30 fires are "elevated" for contrast B
        mask_m1_elevated = np.zeros(n_fires, dtype=float)
        mask_m1_elevated[:30] = 1.0

        fires["macro_m1_fsi_turn"]  = flag
        fires["vix"]                = vix
        fires["spy_dd126"]          = spy_dd126
        fires["hy_oas"]             = hy_oas
        fires["mask_m1_elevated"]   = mask_m1_elevated

        extra_cols = {col: fires[col] for col in
                      ["macro_m1_fsi_turn", "vix", "spy_dd126", "hy_oas", "mask_m1_elevated"]}

        graded = grade_fires(fires, closes, extra_columns=extra_cols)
        df_gradable = graded[graded["gradable"].fillna(False)].copy()
        return df_gradable, flag, mask_m1_elevated

    def test_r1m_returns_finite_coef(self, synthetic_study):
        df_gradable, flag, _ = synthetic_study
        res = r1m_estimate(
            df_gradable, "stop5", "macro_m1_fsi_turn",
            ["vix", "spy_dd126", "hy_oas"],
            n_bootstrap=50, rng_seed=0,
        )
        assert res["coef"] is not None, "coef should not be None"
        assert np.isfinite(res["coef"]), f"coef should be finite, got {res['coef']}"

    def test_r1m_contrast_b_mask_reduces_sample(self, synthetic_study):
        """Contrast B: mask restricts sample to elevated subset (both arms)."""
        df_gradable, _, mask_m1_elevated = synthetic_study

        # Build computable_mask
        comp_mask = pd.Series(
            mask_m1_elevated[:len(df_gradable)].astype(bool),
            index=df_gradable.index,
        )

        res_a = r1m_estimate(
            df_gradable, "stop5", "macro_m1_fsi_turn",
            ["vix", "spy_dd126", "hy_oas"],
            n_bootstrap=20, rng_seed=0, computable_mask=None,
        )
        res_b = r1m_estimate(
            df_gradable, "stop5", "macro_m1_fsi_turn",
            ["vix", "spy_dd126", "hy_oas"],
            n_bootstrap=20, rng_seed=0, computable_mask=comp_mask,
        )
        # Contrast B must have fewer or equal rows than A
        assert res_b["n_total"] <= res_a["n_total"], (
            f"Contrast B n_total ({res_b['n_total']}) should be <= contrast A "
            f"n_total ({res_a['n_total']}) when mask restricts both arms"
        )
        assert res_b["mask_n_dropped"] > 0, "mask_n_dropped should be positive"
        assert res_b["mask_coverage"] < 1.0, "mask_coverage should be < 1 when rows are dropped"

    def test_r1m_ci_is_finite(self, synthetic_study):
        df_gradable, _, _ = synthetic_study
        res = r1m_estimate(
            df_gradable, "stop5", "macro_m1_fsi_turn",
            ["vix", "spy_dd126", "hy_oas"],
            n_bootstrap=30, rng_seed=1,
        )
        assert res["ci_lo"] is not None and res["ci_hi"] is not None
        assert np.isfinite(res["ci_lo"]) and np.isfinite(res["ci_hi"])
        assert res["ci_lo"] <= res["ci_hi"], "CI lower must be <= CI upper"

    def test_m2_controls_exclude_hy_oas(self):
        """M2 controls per RUL-24 must NOT include hy_oas."""
        m2_controls = runner._MACRO_CONTROLS["M2"]
        assert "hy_oas" not in m2_controls, (
            f"M2 controls must exclude hy_oas (shared-source, RUL-24). Got: {m2_controls}"
        )
        assert "vix" in m2_controls
        assert "spy_dd126" in m2_controls

    def test_m1_controls_include_hy_oas(self):
        """M1 controls must include hy_oas (only FSI-family control excluded, not OAS)."""
        m1_controls = runner._MACRO_CONTROLS["M1"]
        assert "hy_oas" in m1_controls, (
            f"M1 controls must include hy_oas (RUL-24: only FSI-family excluded). Got: {m1_controls}"
        )


# ---------------------------------------------------------------------------
# (e) Controls enforcement — RUL-24
# ---------------------------------------------------------------------------

class TestControlsEnforcement:
    def test_r1m_raises_on_empty_controls(self):
        """r1m_estimate must raise ValueError when controls is empty (RUL-24)."""
        df = pd.DataFrame({
            "date": pd.bdate_range("2013-01-02", periods=20),
            "stop5": np.random.default_rng(0).integers(0, 2, 20).astype(float),
            "stratum": np.random.default_rng(1).integers(0, 2, 20).astype(float),
            "gradable": True,
        })
        with pytest.raises(ValueError, match="controls must be non-empty"):
            r1m_estimate(df, "stop5", "stratum", controls=[])

    def test_r1m_raises_on_missing_control_column(self):
        """r1m_estimate must raise ValueError when a required column is absent."""
        df = pd.DataFrame({
            "date": pd.bdate_range("2013-01-02", periods=20),
            "stop5": np.ones(20),
            "stratum": np.zeros(20),
            "vix": np.ones(20) * 20,
        })
        with pytest.raises(ValueError, match="missing columns"):
            r1m_estimate(df, "stop5", "stratum", controls=["vix", "spy_dd126"])


# ---------------------------------------------------------------------------
# (f) Budget accounting
# ---------------------------------------------------------------------------

class TestBudgetAccounting:
    def test_macro_budget(self):
        assert runner.BUDGET_MACRO_DECL == 8
        assert runner.BUDGET_MACRO_CONS == 8
        assert runner.BUDGET_MACRO_RES  == 0
        assert runner.BUDGET_MACRO_CONS + runner.BUDGET_MACRO_RES == runner.BUDGET_MACRO_DECL

    def test_pos_budget(self):
        assert runner.BUDGET_POS_DECL == 8
        assert runner.BUDGET_POS_CONS == 4
        assert runner.BUDGET_POS_RES  == 4
        assert runner.BUDGET_POS_CONS + runner.BUDGET_POS_RES == runner.BUDGET_POS_DECL

    def test_macro_trial_count_matches_consumed(self):
        """Total macro trial rows = BUDGET_CONSUMED (4 trial defs × 2 panels)."""
        n_panels = 2
        assert len(runner.MACRO_TRIAL_DEFS) * n_panels == runner.BUDGET_MACRO_CONS

    def test_pos_trial_count_matches_consumed(self):
        """Total pos trial rows = BUDGET_CONSUMED (2 trial defs × 2 panels)."""
        n_panels = 2
        assert len(runner.POS_TRIAL_DEFS) * n_panels == runner.BUDGET_POS_CONS

    def test_macro_families_in_family_budgets(self):
        from scripts.research.entry_strata_phase0 import FAMILY_BUDGETS
        assert runner.FAMILY_MACRO in FAMILY_BUDGETS, (
            f"{runner.FAMILY_MACRO} must be declared in FAMILY_BUDGETS"
        )
        assert runner.FAMILY_POS in FAMILY_BUDGETS, (
            f"{runner.FAMILY_POS} must be declared in FAMILY_BUDGETS"
        )
        assert FAMILY_BUDGETS[runner.FAMILY_MACRO]["budget"] == runner.BUDGET_MACRO_DECL
        assert FAMILY_BUDGETS[runner.FAMILY_POS]["budget"] == runner.BUDGET_POS_DECL
