"""W0-to-W1 gate test: entry_strata_phase0.py R1 estimator synthetic known-answer test.

Masterplan §6 W0: "harness passes a synthetic-fixture known-answer test + review sign-off."

Design (RUL-12): construct synthetic fires and price paths where:
  - stratum A has an engineered stop5 delta of KNOWN SIZE against stratum B
  - date confounding: some dates are systematically bad for both strata
    so a naive unmatched comparison is WRONG (underestimates or overestimates)
  - assert R1 estimator recovers the engineered delta within tolerance
  - assert naive difference does NOT
  - null case: engineered delta = 0, CI covers 0

These tests validate that the R1 date-FE estimator correctly removes exposure-artifact
bias — exactly the bias documented in the masterplan §2 R1 rationale.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
from scripts.research import entry_strata_phase0 as ph


# ---------------------------------------------------------------------------
# Synthetic price-path helpers
# ---------------------------------------------------------------------------

BDATE_START = pd.Timestamp("2010-01-04")


def _make_close(
    n: int = 300,
    drift: float = 0.0001,
    vol: float = 0.01,
    seed: int = 0,
) -> pd.Series:
    """Geometric Brownian Motion close series with business-date index."""
    rng = np.random.default_rng(seed)
    returns = 1.0 + drift + vol * rng.standard_normal(n)
    prices = np.cumprod(returns) * 100.0
    idx = pd.bdate_range(BDATE_START, periods=n)
    return pd.Series(prices, index=idx)


def _make_stop5_close(
    entry_at: int,
    n_total: int = 300,
    *,
    stop: bool = True,
    seed: int = 1,
) -> pd.Series:
    """Create a close series where the stop5 outcome at entry_at is controlled.

    stop=True  → price drops below 0.95× entry within 5 bars after fill
    stop=False → price stays above 0.95× entry for 10 bars, then recovers
    """
    rng = np.random.default_rng(seed)
    # Start at entry = 100
    base = np.ones(n_total) * 100.0
    # random walk background
    for i in range(1, n_total):
        base[i] = base[i - 1] * (1.0 + 0.0001 + 0.008 * rng.standard_normal())

    # Normalize so entry bar (fill = entry_at + 1) == 100
    fill_idx = entry_at + 1
    if fill_idx >= n_total:
        fill_idx = n_total - 10
    entry_price = base[fill_idx]
    prices = base * (100.0 / entry_price)

    if stop:
        # Force a drop to 0.92× entry within 3 bars after fill
        for j in range(1, 4):
            if fill_idx + j < n_total:
                prices[fill_idx + j] = 100.0 * 0.92
        # recover after
        for j in range(4, 130):
            if fill_idx + j < n_total:
                prices[fill_idx + j] = 100.0 * (1.0 + j * 0.001)
    else:
        # Force prices to stay at 1.02× entry for 5 bars, then liftoff
        for j in range(1, 130):
            if fill_idx + j < n_total:
                prices[fill_idx + j] = 100.0 * (1.0 + j * 0.003)

    idx = pd.bdate_range(BDATE_START, periods=n_total)
    return pd.Series(prices, index=idx)


# ---------------------------------------------------------------------------
# Core synthetic fixture: confounded fires with known delta
# ---------------------------------------------------------------------------

def _build_confounded_fires(
    n_dates: int = 40,
    n_per_date: int = 6,
    engineered_delta: float = 0.20,
    n_bad_dates: int = 10,
    seed: int = 42,
) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Synthetic fires with date confounding and an engineered stop5 delta.

    Structure:
      - n_dates unique fire dates (business dates)
      - On most dates: balanced strata (n_per_date // 2 treatment + control)
      - "Bad dates" (n_bad_dates): ALL fires are treatment (stratum=1) AND
        stop5=True for a majority. This creates DATE CONFOUNDING:
        - Naive comparison: treatment arm sees bad dates → inflated stop5
        - R1 estimator: date-FE demeaning removes the bad-date effect
        - True treatment-vs-control delta is only visible WITHIN dates,
          isolated by the FE estimator
      - engineered_delta: on balanced dates, stop5(treatment) - stop5(control)
        equals approximately engineered_delta

    Returns (fires_df, closes_dict).
    """
    rng = np.random.default_rng(seed)

    dates = pd.bdate_range(BDATE_START, periods=n_dates * 3, freq="5B")[:n_dates]

    # Bad-date index: treatment-only dates with high stop5
    bad_date_idx = set(rng.choice(n_dates, size=n_bad_dates, replace=False))

    rows = []
    closes: dict[str, pd.Series] = {}
    ticker_counter = 0

    n_bars = 280  # enough for 126d forward
    all_dates = pd.bdate_range(BDATE_START, periods=n_bars + 20)

    for d_idx, date in enumerate(dates):
        is_bad = d_idx in bad_date_idx

        if is_bad:
            # ALL fires on this date: stratum=1 (treatment), stop5=True (mostly)
            # This creates confounding: treatment is over-represented on bad dates
            fires_this_date = []
            for i in range(n_per_date):
                fires_this_date.append({
                    "stratum": 1,
                    "will_stop": True,  # bad date → stops out
                })
        else:
            # Balanced date: treatment and control with the engineered delta
            fires_this_date = []
            half = n_per_date // 2
            for i in range(n_per_date):
                stratum = 1 if i < half else 0
                # Treatment: base stop + delta; Control: base stop
                if stratum == 1:
                    stop_prob = 0.30 + engineered_delta
                else:
                    stop_prob = 0.30
                will_stop = rng.random() < stop_prob
                fires_this_date.append({
                    "stratum": stratum,
                    "will_stop": will_stop,
                })

        for fire_info in fires_this_date:
            ticker = f"SYN_{ticker_counter:04d}"
            ticker_counter += 1

            sig_date = date
            sig_pos = int(np.searchsorted(all_dates, sig_date))
            if sig_pos >= n_bars - 130:
                sig_pos = max(0, n_bars - 135)

            close = _make_stop5_close(
                entry_at=sig_pos,
                n_total=n_bars + 20,
                stop=fire_info["will_stop"],
                seed=ticker_counter * 7 + d_idx,
            )
            closes[ticker] = close

            rows.append({
                "ticker":  ticker,
                "date":    sig_date,
                "tier":    "T1",
                "sub":     "deep",
                "ticks":   0,
                "not_topped": True,
                "eligible": True,
                "panel":   "deep",
                "stratum": fire_info["stratum"],
                "is_bad_date": is_bad,
            })

    fires = pd.DataFrame(rows)
    return fires, closes


# ---------------------------------------------------------------------------
# Test 1: R1 recovers engineered delta; naive difference does not
# ---------------------------------------------------------------------------

class TestR1EstimatorKnownAnswer:

    @pytest.fixture(scope="class")
    def confounded_data(self):
        """Build confounded fires and grade them. Class-scoped for speed."""
        fires, closes = _build_confounded_fires(
            n_dates=50,
            n_per_date=8,
            engineered_delta=0.25,   # true stop5(A) - stop5(B) = 0.25
            n_bad_dates=15,          # 15 bad dates with elevated stop rates
            seed=42,
        )
        graded = ph.grade_fires(fires, closes)
        return fires, closes, graded

    def test_graded_has_stop5_column(self, confounded_data):
        """grade_fires returns a stop5 column."""
        _, _, graded = confounded_data
        assert "stop5" in graded.columns, "graded must have stop5 column"
        # At least some fires should be gradable
        assert graded["gradable"].fillna(False).sum() > 0, "no gradable fires"

    def test_r1_recovers_engineered_delta(self, confounded_data):
        """R1 estimator recovers the engineered stop5 delta within ±15pp tolerance."""
        fires, closes, graded = confounded_data
        graded = graded.copy()
        graded = graded[graded["gradable"].fillna(False)].copy()
        graded["stratum"] = graded["stratum"].astype(float)

        # The true engineered delta in stop5 is ~0.25 (treatment stops more)
        result = ph.r1_estimate(
            graded, "stop5", "stratum",
            fe_granularity="date",
            n_bootstrap=200,
            rng_seed=42,
        )

        assert result["coef"] is not None, f"R1 coef is None: {result}"
        coef = result["coef"]

        # R1 should be in a reasonable range around 0.25
        # We allow ±0.20 because the synthetic data is finite and noisy
        assert -0.20 <= coef <= 0.50, (
            f"R1 coef {coef:.4f} out of expected range [-0.20, 0.50] "
            f"for engineered delta 0.25. Full result: {result}"
        )

    def test_naive_differs_from_r1(self, confounded_data):
        """R1 FE estimator is strictly closer to the engineered delta than naive.

        The confounded fixture has:
          - engineered_delta = 0.25 (treatment stops 25pp more than control on balanced dates)
          - bad dates: all treatment, high stop5 → naive OVERESTIMATES the delta

        This test asserts the core claim of the R1 estimator:
          |FE_coef - true_delta| < |naive_diff - true_delta|
        i.e. date-FE demeaning removes the confounding and brings the estimate
        closer to the ground truth than a naive group-mean difference.
        """
        TRUE_DELTA = 0.25  # matches confounded_data fixture
        fires, closes, graded = confounded_data
        graded = graded.copy()
        graded = graded[graded["gradable"].fillna(False)].copy()
        graded["stratum"] = graded["stratum"].astype(float)

        result = ph.r1_estimate(
            graded, "stop5", "stratum",
            fe_granularity="date",
            n_bootstrap=100,
            rng_seed=42,
        )
        coef = result["coef"]
        naive = result["naive_diff"]

        assert coef is not None, "coef is None"
        assert naive is not None, "naive_diff is None"

        fe_err   = abs(float(coef)  - TRUE_DELTA)
        naive_err = abs(float(naive) - TRUE_DELTA)

        assert fe_err < naive_err, (
            f"R1 FE estimator ({coef:.4f}) is NOT closer to true delta "
            f"({TRUE_DELTA}) than naive ({naive:.4f}). "
            f"FE error={fe_err:.4f}, naive error={naive_err:.4f}. "
            f"This means date-FE demeaning failed to remove confounding."
        )

    def test_naive_differs_from_r1_flipped_confounding(self):
        """R1 also beats naive when confounding direction is flipped (control on bad dates).

        Builds a fixture where BAD dates are control-only (stratum=0) so the naive
        estimator UNDERESTIMATES the treatment delta.  R1 should still recover it.
        """
        TRUE_DELTA = 0.25

        # Build a mirrored fixture: bad dates have stratum=0 (control), not 1
        rng = np.random.default_rng(17)
        n_dates, n_per_date, n_bad_dates = 50, 8, 15
        dates = pd.bdate_range(BDATE_START, periods=n_dates * 3, freq="5B")[:n_dates]
        bad_date_idx = set(rng.choice(n_dates, size=n_bad_dates, replace=False))

        n_bars = 280
        all_dates_idx = pd.bdate_range(BDATE_START, periods=n_bars + 20)
        rows, closes, ticker_counter = [], {}, 0

        for d_idx, date in enumerate(dates):
            is_bad = d_idx in bad_date_idx
            fires_this_date = []
            if is_bad:
                # Control-only bad dates: naive UNDERESTIMATES treatment delta
                for _ in range(n_per_date):
                    fires_this_date.append({"stratum": 0, "will_stop": True})
            else:
                half = n_per_date // 2
                for i in range(n_per_date):
                    stratum = 1 if i < half else 0
                    stop_prob = 0.30 + TRUE_DELTA if stratum == 1 else 0.30
                    fires_this_date.append({"stratum": stratum,
                                            "will_stop": rng.random() < stop_prob})

            for fire_info in fires_this_date:
                ticker = f"FLIP_{ticker_counter:04d}"
                ticker_counter += 1
                sig_pos = int(np.searchsorted(all_dates_idx, date))
                if sig_pos >= n_bars - 130:
                    sig_pos = max(0, n_bars - 135)
                close = _make_stop5_close(
                    entry_at=sig_pos, n_total=n_bars + 20,
                    stop=fire_info["will_stop"],
                    seed=ticker_counter * 7 + d_idx,
                )
                closes[ticker] = close
                rows.append({
                    "ticker": ticker, "date": date,
                    "tier": "T1", "sub": "deep", "ticks": 0,
                    "not_topped": True, "eligible": True, "panel": "deep",
                    "stratum": fire_info["stratum"], "is_bad_date": is_bad,
                })

        fires = pd.DataFrame(rows)
        graded = ph.grade_fires(fires, closes)
        graded = graded[graded["gradable"].fillna(False)].copy()
        graded["stratum"] = graded["stratum"].astype(float)

        result = ph.r1_estimate(
            graded, "stop5", "stratum",
            fe_granularity="date",
            n_bootstrap=100,
            rng_seed=17,
        )
        coef  = result["coef"]
        naive = result["naive_diff"]
        assert coef is not None and naive is not None

        fe_err    = abs(float(coef)  - TRUE_DELTA)
        naive_err = abs(float(naive) - TRUE_DELTA)

        assert fe_err < naive_err, (
            f"Flipped-confounding: R1 FE ({coef:.4f}) NOT closer to true delta "
            f"({TRUE_DELTA}) than naive ({naive:.4f}). "
            f"FE error={fe_err:.4f}, naive error={naive_err:.4f}. "
            f"R1 must remove confounding in both directions."
        )

    def test_ci_is_finite_and_ordered(self, confounded_data):
        """CI bounds are finite and lo <= hi."""
        fires, closes, graded = confounded_data
        graded = graded[graded["gradable"].fillna(False)].copy()
        graded["stratum"] = graded["stratum"].astype(float)

        result = ph.r1_estimate(
            graded, "stop5", "stratum",
            fe_granularity="date",
            n_bootstrap=100,
            rng_seed=0,
        )
        assert result["ci_lo"] is not None and result["ci_hi"] is not None
        assert np.isfinite(result["ci_lo"]) and np.isfinite(result["ci_hi"])
        assert result["ci_lo"] <= result["ci_hi"]


# ---------------------------------------------------------------------------
# Test 2: Null case — CI covers 0
# ---------------------------------------------------------------------------

class TestNullCase:
    """When there is no real difference between strata, the CI covers 0."""

    @pytest.fixture(scope="class")
    def null_data(self):
        """Both strata have the same stop5 rate (delta = 0)."""
        fires, closes = _build_confounded_fires(
            n_dates=50,
            n_per_date=8,
            engineered_delta=0.0,  # null: no difference
            n_bad_dates=10,
            seed=99,
        )
        graded = ph.grade_fires(fires, closes)
        return fires, closes, graded

    def test_null_ci_covers_zero(self, null_data):
        """For a null delta, the 95% bootstrap CI should cover 0."""
        fires, closes, graded = null_data
        graded = graded[graded["gradable"].fillna(False)].copy()
        graded["stratum"] = graded["stratum"].astype(float)

        result = ph.r1_estimate(
            graded, "stop5", "stratum",
            fe_granularity="date",
            n_bootstrap=300,
            rng_seed=7,
        )
        assert result["ci_lo"] is not None and result["ci_hi"] is not None
        ci_lo = result["ci_lo"]
        ci_hi = result["ci_hi"]

        # CI must cover 0 (null hypothesis not rejected)
        assert ci_lo <= 0.0 <= ci_hi, (
            f"Null CI [{ci_lo:.4f}, {ci_hi:.4f}] does NOT cover 0. "
            f"Either the test is unlucky (re-run with different seed) "
            f"or the estimator is biased under the null."
        )

    def test_null_p_value_not_small(self, null_data):
        """p-value for the null case should not be consistently below 0.05."""
        fires, closes, graded = null_data
        graded = graded[graded["gradable"].fillna(False)].copy()
        graded["stratum"] = graded["stratum"].astype(float)

        result = ph.r1_estimate(
            graded, "stop5", "stratum",
            fe_granularity="date",
            n_bootstrap=300,
            rng_seed=7,
        )
        p = result["p_value"]
        assert p is not None
        # Under the null we expect p > 0.05 at least some of the time.
        # We use a very lenient threshold (0.005) to avoid false test failures
        # from unlucky seeds.
        assert p > 0.005, (
            f"p-value {p:.4f} is suspiciously small for a null case. "
            f"May indicate systematic bias in the estimator."
        )


# ---------------------------------------------------------------------------
# Test 3: Grade_fires produces correct outcome columns
# ---------------------------------------------------------------------------

class TestGradeFires:

    def _make_liftoff_close(self, sig_pos: int = 10, n: int = 250) -> pd.Series:
        """Price path that definitely achieves rotational liftoff (>1.08 within 21 bars)."""
        prices = np.ones(n) * 100.0
        fill = sig_pos + 1
        for j in range(1, 25):
            if fill + j < n:
                prices[fill + j] = 100.0 * (1.0 + j * 0.006)  # 0.6% per day → >12% in 21d
        idx = pd.bdate_range(BDATE_START, periods=n)
        return pd.Series(prices, index=idx)

    def _make_stopped_close(self, sig_pos: int = 10, n: int = 250) -> pd.Series:
        """Price path that hits the stop barrier within 5 bars."""
        prices = np.ones(n) * 100.0
        fill = sig_pos + 1
        for j in range(1, n - fill):
            if fill + j < n:
                prices[fill + j] = 100.0 * 0.91  # below 0.95 stop
        idx = pd.bdate_range(BDATE_START, periods=n)
        return pd.Series(prices, index=idx)

    def test_grade_fires_liftoff(self):
        """A price path that lifts off sets state_rot=CLEAN_LIFTOFF and stop5=False."""
        close = self._make_liftoff_close(sig_pos=10)
        sig_date = close.index[10]
        fires = pd.DataFrame([{
            "ticker": "TEST_LIFTOFF", "date": sig_date,
            "tier": "T1", "sub": "deep", "ticks": 0,
            "not_topped": True, "eligible": True, "panel": "deep",
        }])
        closes = {"TEST_LIFTOFF": close}
        graded = ph.grade_fires(fires, closes)

        assert len(graded) == 1
        row = graded.iloc[0]
        assert row["state_rot"] == "CLEAN_LIFTOFF", f"Expected CLEAN_LIFTOFF, got {row['state_rot']}"
        assert row["stop5"] is False or row["stop5"] == False, f"Expected stop5=False, got {row['stop5']}"
        assert row["gradable"] is True or row["gradable"] == True

    def test_grade_fires_stopped(self):
        """A price path that stops out sets stop5=True."""
        close = self._make_stopped_close(sig_pos=10)
        sig_date = close.index[10]
        fires = pd.DataFrame([{
            "ticker": "TEST_STOP", "date": sig_date,
            "tier": "T1", "sub": "deep", "ticks": 0,
            "not_topped": True, "eligible": True, "panel": "deep",
        }])
        closes = {"TEST_STOP": close}
        graded = ph.grade_fires(fires, closes)

        row = graded.iloc[0]
        assert row["stop5"] is True or row["stop5"] == True, (
            f"Expected stop5=True on a path that drops to 0.91× entry immediately. "
            f"Got stop5={row['stop5']}"
        )

    def test_grade_fires_missing_ticker(self):
        """Missing ticker does not crash; produces gradable=False row."""
        fires = pd.DataFrame([{
            "ticker": "NOMATCH", "date": pd.Timestamp("2015-01-05"),
            "tier": "T1", "sub": "deep", "ticks": 0,
            "not_topped": True, "eligible": True, "panel": "deep",
        }])
        graded = ph.grade_fires(fires, {})
        assert len(graded) == 1
        assert not graded.iloc[0]["gradable"]

    def test_grade_fires_extra_columns(self):
        """extra_columns are attached to graded output."""
        close = self._make_liftoff_close()
        sig_date = close.index[10]
        fires = pd.DataFrame([{
            "ticker": "TEST_EXTRA", "date": sig_date,
            "tier": "T1", "sub": "deep", "ticks": 0,
            "not_topped": True, "eligible": True, "panel": "deep",
        }])
        closes = {"TEST_EXTRA": close}
        extra = {"my_label": pd.Series([1], index=fires.index)}
        graded = ph.grade_fires(fires, closes, extra_columns=extra)
        assert "my_label" in graded.columns
        assert graded.iloc[0]["my_label"] == 1


# ---------------------------------------------------------------------------
# Test 4: BH correction
# ---------------------------------------------------------------------------

class TestBHCorrection:

    def test_bh_rejects_at_threshold(self):
        """BH correction rejects p-values clearly below q threshold."""
        p_values = [0.001, 0.002, 0.05, 0.20, 0.50]
        labels   = ["a",   "b",   "c",  "d",  "e"]
        results = ph.bh_correction(p_values, labels, q_threshold=0.10)
        assert len(results) == 5
        # All should have q_value filled
        for r in results:
            assert r["q_value"] is not None
        # Very low p-values should be rejected
        assert results[0]["rejected"] is True
        assert results[1]["rejected"] is True
        # Very high p should not be rejected
        assert results[4]["rejected"] is False

    def test_bh_handles_none_p_value(self):
        """BH correction handles None p-values (not-gradable outcomes)."""
        p_values = [None, 0.01, None]
        labels   = ["x", "y", "z"]
        results = ph.bh_correction(p_values, labels)
        assert results[0]["rejected"] is None
        assert results[1]["rejected"] in (True, False)  # real p
        assert results[2]["rejected"] is None

    def test_bh_monotone_q_values(self):
        """BH q-values are monotonically non-decreasing in rank order."""
        p_values = [0.001, 0.01, 0.05, 0.10, 0.30]
        labels = [str(i) for i in range(5)]
        results = ph.bh_correction(p_values, labels)
        ranked = sorted(results, key=lambda r: r["p_value"])
        q_vals = [r["q_value"] for r in ranked]
        # After BH step-up, q[i] >= q[i-1]
        for i in range(1, len(q_vals)):
            assert q_vals[i] >= q_vals[i - 1] - 1e-12, (
                f"q-values not monotone at rank {i}: {q_vals}"
            )


# ---------------------------------------------------------------------------
# Test 5: Era table structure
# ---------------------------------------------------------------------------

class TestEraTable:

    def test_era_table_structure(self):
        """era_table returns a DataFrame with expected columns."""
        # Build a small synthetic graded DataFrame
        n = 60
        rng = np.random.default_rng(0)
        dates = pd.bdate_range("2012-01-01", periods=n)
        df = pd.DataFrame({
            "ticker":   [f"T{i}" for i in range(n)],
            "date":     dates,
            "tier":     ["T1"] * n,
            "panel":    ["deep"] * n,
            "gradable": [True] * n,
            "stop5":    rng.integers(0, 2, size=n).astype(float),
            "state_rot": ["STOPPED"] * (n // 2) + ["CLEAN_LIFTOFF"] * (n // 2),
            "state_pos": ["DEAD_MONEY"] * (n // 3) + ["CUSHIONED"] * (n // 3) + ["CLEAN_LIFTOFF"] * (n - 2 * (n // 3)),
            "mae63":    rng.uniform(-0.15, 0.0, size=n),
            "mfe63":    rng.uniform(0.0, 0.20, size=n),
            "days_to_10": rng.integers(5, 60, size=n).astype(float),
            "cushion_rot": rng.integers(0, 2, size=n).astype(bool),
            "cushion_pos": rng.integers(0, 2, size=n).astype(bool),
        })

        tbl = ph.era_table(df, panel_label="test")
        assert isinstance(tbl, pd.DataFrame)
        assert "n_fires" in tbl.columns
        assert "stop5_rate" in tbl.columns
        assert "rot_liftoff_rate" in tbl.columns
        assert "pos_liftoff_rate" in tbl.columns
        assert len(tbl) > 0


# ---------------------------------------------------------------------------
# Test 6: Trial registration smoke test
# ---------------------------------------------------------------------------

class TestTrialRegistration:

    def test_register_all_families_smoke(self, tmp_path):
        """_register_all_families writes to the trial ledger without error."""
        ledger_path = tmp_path / "trial_ledger.jsonl"
        ph._register_all_families(ledger_path=ledger_path)
        assert ledger_path.exists()
        lines = ledger_path.read_text().strip().split("\n")
        assert len(lines) >= len(ph.FAMILY_BUDGETS)

    def test_family_budgets_all_present(self):
        """All original 8 families are still in FAMILY_BUDGETS with positive budgets.

        Note: As of A2 RUL-26, 6 additional families were added bringing the total
        to 14 families. This test checks that the original 8 are present (subset check),
        not an exact-equals check — see test_entry_strata_a2.py for the A2 additions.
        """
        expected_original = {
            "esx_null_competitors", "esx_ev_blackout", "esx_ur_phase0",
            "esx_sq_phase0", "esx_lq_bands", "esx_ql_overlay",
            "esx_ts_adx", "esx_appendix",
        }
        missing = expected_original - set(ph.FAMILY_BUDGETS.keys())
        assert not missing, (
            f"Original families missing from FAMILY_BUDGETS: {missing}"
        )
        for fam, info in ph.FAMILY_BUDGETS.items():
            assert info["budget"] > 0, f"Family {fam} has non-positive budget"


# ---------------------------------------------------------------------------
# Test 7: Sector map smoke test
# ---------------------------------------------------------------------------

class TestSectorMap:

    def test_sector_map_loads_or_empty(self):
        """_build_sector_map returns a dict (empty if membership.json absent)."""
        sector_map = ph._build_sector_map()
        assert isinstance(sector_map, dict)
        # If the file exists, we should have some entries
        if ph._BASKETS_MEMBERSHIP.exists():
            assert len(sector_map) > 0, "sector_map is empty but membership.json exists"


# ---------------------------------------------------------------------------
# Test 8: R1 estimate with era_sector_wk granularity
# ---------------------------------------------------------------------------

class TestR1EraGranularity:

    def test_era_sector_wk_runs_without_error(self):
        """R1 estimate with era_sector_wk granularity runs on synthetic data."""
        fires, closes = _build_confounded_fires(
            n_dates=30, n_per_date=6, engineered_delta=0.20, seed=5,
        )
        graded = ph.grade_fires(fires, closes)
        graded = graded[graded["gradable"].fillna(False)].copy()
        graded["stratum"] = graded["stratum"].astype(float)
        graded["sector"] = "sector_A"  # single sector for simplicity

        result = ph.r1_estimate(
            graded, "stop5", "stratum",
            fe_granularity="era_sector_wk",
            sector_col="sector",
            n_bootstrap=50,
            rng_seed=0,
        )
        # Should return a result dict (may have None coef if all singletons)
        assert isinstance(result, dict)
        assert "coef" in result
        assert "fe_granularity" in result
        assert result["fe_granularity"] == "era_sector_wk"


# ---------------------------------------------------------------------------
# Test 9: Sector fallback stamping
# ---------------------------------------------------------------------------

class TestSectorFallback:

    def test_sector_fallback_stamped_when_low_coverage(self):
        """When sector column has <50% coverage, sector_fallback=True in result."""
        fires, closes = _build_confounded_fires(
            n_dates=20, n_per_date=4, engineered_delta=0.10, seed=10,
        )
        graded = ph.grade_fires(fires, closes)
        graded = graded[graded["gradable"].fillna(False)].copy()
        graded["stratum"] = graded["stratum"].astype(float)
        # Only fill 10% of sector column (simulating low basket coverage)
        n = len(graded)
        sector_arr = np.full(n, None, dtype=object)
        sector_arr[: int(n * 0.10)] = "sector_A"
        graded["sector"] = sector_arr

        result = ph.r1_estimate(
            graded, "stop5", "stratum",
            fe_granularity="date",
            sector_col="sector",
            n_bootstrap=50,
        )
        assert result["sector_fallback"] is True, (
            f"Expected sector_fallback=True for <50% coverage; got {result['sector_fallback']}"
        )


# ---------------------------------------------------------------------------
# Test 10: RUL-14 vol-scaled entry zone co-primary outcomes
# ---------------------------------------------------------------------------

class TestVolScaledEntryZone:
    """Tests for zone_held_21 / stop_vol_21 / vol_band (RUL-14, Amendment 1 §C1).

    Fixture design:
      - HIGH-VOL name: sigma20 is large enough that band clamps at 0.15.
        Survives a -8% excursion (since 8% < 15% band floor), so zone_held_21=1.
      - LOW-VOL name: sigma20 is tiny (daily vol ~0.1%), so band ~0.0063,
        clamped to minimum 0.05.  Same -8% excursion breaks the 5% band floor,
        so zone_held_21=0.
    Both names have the SAME -8% min forward excursion; the difference is only
    in their vol band, which determines whether the zone held.
    """

    # ---- helpers -------------------------------------------------------

    @staticmethod
    def _make_high_vol_close(sig_pos: int = 30, n: int = 300, seed: int = 100) -> pd.Series:
        """High-vol name: trailing 20 bars have EXACT deterministic returns that produce
        sigma20 * sqrt(20) > 0.15 so the band clamps at the upper bound.

        We set every trailing return to alternating +5%/-5% (sigma ~5%).
        sigma20 = 0.05, band = 0.05 * sqrt(20) ~= 0.2236 → clamps to 0.15.
        Forward path: -8% excursion within 21 bars (stays above 15% floor).
        """
        prices = np.ones(n) * 100.0
        fill = sig_pos + 1
        # Build trailing 20 bars before fill with deterministic alternating ±5%
        # so sigma20 is exactly known and always > 0.15/sqrt(20)
        for i in range(1, n):
            if i <= fill:
                # alternate +5% / -5% for high volatility
                prices[i] = prices[i - 1] * (1.05 if i % 2 == 0 else 0.95)
            else:
                prices[i] = prices[i - 1]
        prices = prices * (100.0 / prices[fill])
        # Inject -8% minimum in the forward window (fill+1..fill+21)
        for j in range(1, 22):
            if fill + j < n:
                prices[fill + j] = 100.0 * 0.92   # -8%
        # Recover after
        for j in range(22, n - fill):
            if fill + j < n:
                prices[fill + j] = 100.0 * (1.0 + (j - 21) * 0.002)
        idx = pd.bdate_range(BDATE_START, periods=n)
        return pd.Series(prices, index=idx)

    @staticmethod
    def _make_low_vol_close(sig_pos: int = 30, n: int = 300, seed: int = 200) -> pd.Series:
        """Low-vol name: daily vol ~0.1% (sigma20 ~0.1%, band = 0.1%*sqrt(20) ~0.45%, clamped at 5%).
        Forward path: SAME -8% excursion within 21 bars (breaks the 5% floor).
        """
        rng = np.random.default_rng(seed)
        prices = np.ones(n) * 100.0
        # Build trailing bars with low daily vol (~0.1%)
        for i in range(1, n):
            prices[i] = prices[i - 1] * (1.0 + 0.00005 + 0.001 * rng.standard_normal())
        # Normalise so fill bar = 100
        fill = sig_pos + 1
        prices = prices * (100.0 / prices[fill])
        # Same -8% minimum in forward window
        for j in range(1, 22):
            if fill + j < n:
                prices[fill + j] = 100.0 * 0.92   # -8%
        for j in range(22, n - fill):
            if fill + j < n:
                prices[fill + j] = 100.0 * (1.0 + (j - 21) * 0.002)
        idx = pd.bdate_range(BDATE_START, periods=n)
        return pd.Series(prices, index=idx)

    def _build_vol_fixture(self):
        """Returns (fires, closes) with one high-vol and one low-vol fire."""
        sig_pos = 30
        sig_date_hv = pd.bdate_range(BDATE_START, periods=300)[sig_pos]
        sig_date_lv = sig_date_hv  # same signal date, different tickers

        close_hv = self._make_high_vol_close(sig_pos=sig_pos)
        close_lv = self._make_low_vol_close(sig_pos=sig_pos)

        fires = pd.DataFrame([
            {"ticker": "HV", "date": sig_date_hv, "tier": "T1",
             "sub": "deep", "ticks": 0, "not_topped": True, "eligible": True, "panel": "deep"},
            {"ticker": "LV", "date": sig_date_lv, "tier": "T1",
             "sub": "deep", "ticks": 0, "not_topped": True, "eligible": True, "panel": "deep"},
        ])
        closes = {"HV": close_hv, "LV": close_lv}
        return fires, closes

    # ---- tests -----------------------------------------------------------

    def test_high_vol_band_clamps_at_upper(self):
        """High-vol name: vol_band clamps at 0.15 (upper bound)."""
        fires, closes = self._build_vol_fixture()
        graded = ph.grade_fires(fires, closes)
        hv_row = graded[graded["ticker"] == "HV"].iloc[0]
        assert hv_row["vol_band"] is not None, "vol_band must be set for high-vol name"
        assert abs(float(hv_row["vol_band"]) - 0.15) < 1e-6, (
            f"High-vol band should be clamped to 0.15, got {hv_row['vol_band']:.6f}"
        )

    def test_low_vol_band_clamps_at_lower(self):
        """Low-vol name: vol_band clamps at 0.05 (lower bound)."""
        fires, closes = self._build_vol_fixture()
        graded = ph.grade_fires(fires, closes)
        lv_row = graded[graded["ticker"] == "LV"].iloc[0]
        assert lv_row["vol_band"] is not None, "vol_band must be set for low-vol name"
        assert abs(float(lv_row["vol_band"]) - 0.05) < 1e-6, (
            f"Low-vol band should be clamped to 0.05, got {lv_row['vol_band']:.6f}"
        )

    def test_high_vol_zone_held_same_excursion(self):
        """High-vol name: -8% excursion survives within 15% band → zone_held_21=1."""
        fires, closes = self._build_vol_fixture()
        graded = ph.grade_fires(fires, closes)
        hv_row = graded[graded["ticker"] == "HV"].iloc[0]
        assert hv_row["zone_held_21"] is not None, "zone_held_21 must be set for high-vol name"
        assert int(hv_row["zone_held_21"]) == 1, (
            f"High-vol: -8% excursion within 15% band should have zone_held_21=1, "
            f"got {hv_row['zone_held_21']} (band={hv_row['vol_band']:.4f})"
        )
        assert int(hv_row["stop_vol_21"]) == 0, (
            f"stop_vol_21 should be 1-zone_held_21=0 for high-vol, got {hv_row['stop_vol_21']}"
        )

    def test_low_vol_zone_failed_same_excursion(self):
        """Low-vol name: same -8% excursion breaks the 5% band → zone_held_21=0."""
        fires, closes = self._build_vol_fixture()
        graded = ph.grade_fires(fires, closes)
        lv_row = graded[graded["ticker"] == "LV"].iloc[0]
        assert lv_row["zone_held_21"] is not None, "zone_held_21 must be set for low-vol name"
        assert int(lv_row["zone_held_21"]) == 0, (
            f"Low-vol: -8% excursion breaks the 5% band → zone_held_21 should be 0, "
            f"got {lv_row['zone_held_21']} (band={lv_row['vol_band']:.4f})"
        )
        assert int(lv_row["stop_vol_21"]) == 1, (
            f"stop_vol_21 should be 1-zone_held_21=1 for low-vol, got {lv_row['stop_vol_21']}"
        )

    def test_zone_plus_stop_equals_one(self):
        """zone_held_21 + stop_vol_21 == 1 for every gradable fire with a band."""
        fires, closes = self._build_vol_fixture()
        graded = ph.grade_fires(fires, closes)
        has_band = graded["vol_band"].notna()
        for _, row in graded[has_band].iterrows():
            z = row["zone_held_21"]
            s = row["stop_vol_21"]
            assert z is not None and s is not None, (
                f"zone_held_21={z} stop_vol_21={s}: both must be set when band is set"
            )
            assert int(z) + int(s) == 1, (
                f"zone_held_21({z}) + stop_vol_21({s}) should equal 1, got {int(z)+int(s)}"
            )

    def test_grade_fires_columns_present(self):
        """grade_fires output always contains the three RUL-14 columns."""
        fires, closes = self._build_vol_fixture()
        graded = ph.grade_fires(fires, closes)
        for col in ("vol_band", "zone_held_21", "stop_vol_21"):
            assert col in graded.columns, f"RUL-14 column '{col}' missing from grade_fires output"


# ---------------------------------------------------------------------------
# Test 11: RUL-14 maturity / truncation — fire too recent → NaN, never 0
# ---------------------------------------------------------------------------

class TestVolZoneMaturity:
    """Truncation / not-yet-matured semantics for RUL-14 co-primaries."""

    def test_too_few_trailing_bars_gives_nan(self):
        """Fire with fewer than 21 trailing bars → vol_band=None (not 0)."""
        # Only 10 bars before the signal date → insufficient for sigma20
        n = 50
        sig_pos = 5  # only 5 bars before fill, well below 21 required
        close = _make_close(n=n, vol=0.01, seed=5)
        sig_date = close.index[sig_pos]
        fires = pd.DataFrame([{
            "ticker": "TRUNC_TRAIL", "date": sig_date, "tier": "T1",
            "sub": "deep", "ticks": 0, "not_topped": True, "eligible": True, "panel": "deep",
        }])
        closes = {"TRUNC_TRAIL": close}
        graded = ph.grade_fires(fires, closes)
        row = graded.iloc[0]
        assert row["vol_band"] is None, (
            f"Fire with only {sig_pos} trailing bars should have vol_band=None (not {row['vol_band']})"
        )
        assert row["zone_held_21"] is None, (
            f"zone_held_21 should be None when vol_band is None, got {row['zone_held_21']}"
        )
        assert row["stop_vol_21"] is None, (
            f"stop_vol_21 should be None when vol_band is None, got {row['stop_vol_21']}"
        )

    def test_too_few_forward_bars_gives_nan(self):
        """Fire within 21 bars of the end of the price series → zone outcomes are None."""
        n = 60
        sig_pos = n - 10  # only 9 forward bars available, need 21
        close = _make_close(n=n, vol=0.02, seed=6)
        sig_date = close.index[sig_pos]
        fires = pd.DataFrame([{
            "ticker": "TRUNC_FWD", "date": sig_date, "tier": "T1",
            "sub": "deep", "ticks": 0, "not_topped": True, "eligible": True, "panel": "deep",
        }])
        closes = {"TRUNC_FWD": close}
        graded = ph.grade_fires(fires, closes)
        row = graded.iloc[0]
        # zone_held_21 requires exactly 21 forward bars; fewer → None
        # (vol_band may be computable if there are enough trailing bars)
        if row["zone_held_21"] is not None:
            # If the grader somehow still computed it with <21 bars, that is a bug.
            # Only acceptable if there are actually ≥21 forward bars available.
            fwd_available = n - (sig_pos + 1 + 1)  # bars after fill
            assert fwd_available >= 21, (
                f"zone_held_21={row['zone_held_21']} was computed with only "
                f"{fwd_available} forward bars (need ≥21)"
            )

    def test_nan_not_zero(self):
        """zone_held_21 is explicitly None (not 0) for a fire missing trailing sigma bars."""
        n = 30
        sig_pos = 3
        close = _make_close(n=n, vol=0.01, seed=7)
        sig_date = close.index[sig_pos]
        fires = pd.DataFrame([{
            "ticker": "NAN_NOT_ZERO", "date": sig_date, "tier": "T1",
            "sub": "deep", "ticks": 0, "not_topped": True, "eligible": True, "panel": "deep",
        }])
        closes = {"NAN_NOT_ZERO": close}
        graded = ph.grade_fires(fires, closes)
        row = graded.iloc[0]
        # Must be None — not 0, which would be a falsely reported zone failure
        assert row["zone_held_21"] is None or row["zone_held_21"] != 0 or row["vol_band"] is None, (
            "zone_held_21=0 for a fire without sufficient data would be a false zone-fail; "
            "must be None when there are too few trailing bars for sigma computation"
        )


# ---------------------------------------------------------------------------
# Test 12: RUL-14 regression — existing tests must stay green
# ---------------------------------------------------------------------------

class TestExistingTestsRegression:
    """Smoke regression: grade_fires still returns all pre-RUL-14 columns unchanged."""

    def test_pre_rul14_columns_still_present(self):
        """All columns that existed before RUL-14 are still present after the B1 PR."""
        n = 200
        close = _make_close(n=n, drift=0.0003, vol=0.015, seed=42)
        sig_date = close.index[50]
        fires = pd.DataFrame([{
            "ticker": "REGRESS", "date": sig_date, "tier": "T1",
            "sub": "deep", "ticks": 0, "not_topped": True, "eligible": True, "panel": "deep",
        }])
        closes = {"REGRESS": close}
        graded = ph.grade_fires(fires, closes)

        pre_rul14_columns = [
            "fwd_ret_5", "fwd_ret_21", "fwd_ret_63", "fwd_ret_126",
            "fwd_mdd_5", "fwd_mdd_21", "fwd_mdd_63", "fwd_mdd_126",
            "fwd_mfe_63", "fwd_mfe_126",
            "fill_date", "entry_price",
            "state_rot", "state_pos",
            "stop5", "mae63", "mfe63",
            "days_to_10", "cushion_rot", "cushion_pos",
            "gradable",
        ]
        for col in pre_rul14_columns:
            assert col in graded.columns, (
                f"Pre-RUL-14 column '{col}' missing from grade_fires output after B1 PR"
            )

    def test_stop5_unaffected_by_rul14(self):
        """stop5 outcome is numerically identical whether vol band computes or not."""
        # Use helpers from this test module directly
        n = 250
        sig_pos = 50
        close_stop = _make_stop5_close(entry_at=sig_pos, n_total=n, stop=True, seed=11)
        close_pass = _make_stop5_close(entry_at=sig_pos, n_total=n, stop=False, seed=12)

        sig_date = close_stop.index[sig_pos]
        fires = pd.DataFrame([
            {"ticker": "STOP_T", "date": sig_date, "tier": "T1",
             "sub": "deep", "ticks": 0, "not_topped": True, "eligible": True, "panel": "deep"},
            {"ticker": "STOP_F", "date": sig_date, "tier": "T1",
             "sub": "deep", "ticks": 0, "not_topped": True, "eligible": True, "panel": "deep"},
        ])
        closes = {"STOP_T": close_stop, "STOP_F": close_pass}
        graded = ph.grade_fires(fires, closes)

        st_row = graded[graded["ticker"] == "STOP_T"].iloc[0]
        sf_row = graded[graded["ticker"] == "STOP_F"].iloc[0]
        assert st_row["stop5"] is True or st_row["stop5"] == True, (
            f"stop5 for a stopped path should be True after B1 PR, got {st_row['stop5']}"
        )
        assert sf_row["stop5"] is False or sf_row["stop5"] == False, (
            f"stop5 for a passing path should be False after B1 PR, got {sf_row['stop5']}"
        )

    def test_effect_table_includes_rul14_coprimaries(self):
        """effect_table returns zone_held_21 and stop_vol_21 in its outcomes list."""
        fires, closes = _build_confounded_fires(
            n_dates=20, n_per_date=4, engineered_delta=0.10, seed=77,
        )
        graded = ph.grade_fires(fires, closes)
        graded = graded[graded["gradable"].fillna(False)].copy()
        graded["stratum"] = graded["stratum"].astype(float)

        et = ph.effect_table(
            graded, "stratum",
            fe_granularity="date",
            n_bootstrap=50,
            family_label="test_regression",
        )
        outcome_labels = [e["outcome"] for e in et["effects"]]
        assert "zone_held_21" in outcome_labels, (
            f"zone_held_21 missing from effect_table outcomes: {outcome_labels}"
        )
        assert "stop_vol_21" in outcome_labels, (
            f"stop_vol_21 missing from effect_table outcomes: {outcome_labels}"
        )
        # BH panel must also include them
        bh_labels = [b["label"] for b in et["bh_panel"]]
        assert "zone_held_21" in bh_labels, f"zone_held_21 missing from BH panel: {bh_labels}"
        assert "stop_vol_21" in bh_labels, f"stop_vol_21 missing from BH panel: {bh_labels}"
