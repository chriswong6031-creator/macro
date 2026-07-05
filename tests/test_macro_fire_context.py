"""Tests for scripts/research/build_macro_fire_context.py.

Four fixture groups per spec:
  (a) Expanding-pctile has no look-ahead: pctile at t is unchanged when future
      rows are appended (prefix property).
  (b) M1/M2 flags on hand-built series with a known stress peak-and-turn.
  (c) P1/P2 publish-lag discipline: value NOT visible before publish date.
  (d) Weekly forward-fill correctness: flag is forward-filled from publish date
      through to the next publish date.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import scripts.research.build_macro_fire_context as mfc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _bdays(start: str, n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


# ---------------------------------------------------------------------------
# Group (a): Expanding-percentile no-look-ahead (prefix property)
# ---------------------------------------------------------------------------
class TestExpandingPctileNoLookahead:
    """expanding_pctile at t uses only data up to t; adding future rows does not
    change historical pctile values."""

    def test_prefix_property_trivial(self):
        """pctile computed on n rows equals the first n rows of pctile on n+k rows."""
        rng = np.random.default_rng(42)
        vals = pd.Series(rng.standard_normal(200),
                         index=_bdays("2010-01-04", 200))

        pctile_full = mfc._expanding_pctile(vals)
        for split in (50, 100, 150):
            pctile_prefix = mfc._expanding_pctile(vals.iloc[:split])
            diff = (pctile_full.iloc[:split] - pctile_prefix).abs().max()
            assert diff < 1e-10, (
                f"Expanding-pctile look-ahead detected at split={split}: "
                f"max abs diff = {diff}"
            )

    def test_prefix_property_monotone_series(self):
        """On a strictly increasing series, pctile should always be 1.0 (rank=max)."""
        n = 100
        vals = pd.Series(np.arange(n, dtype=float),
                         index=_bdays("2015-01-05", n))
        pctile = mfc._expanding_pctile(vals)
        # First row: rank(x0) vs [x0] = 1.0 (expanding rank pct of single element)
        # All other rows: always last element is max → pct=1.0
        assert (pctile == 1.0).all(), f"Expected all 1.0, got min={pctile.min()}"

    def test_prefix_property_stress(self):
        """Stress: 1000-row series; first 300 pctiles unchanged by rows 301-1000."""
        rng = np.random.default_rng(7)
        vals = pd.Series(rng.standard_normal(1000),
                         index=_bdays("2005-01-03", 1000))
        p300 = mfc._expanding_pctile(vals.iloc[:300])
        pfull = mfc._expanding_pctile(vals)
        diff = (pfull.iloc[:300] - p300).abs().max()
        assert diff < 1e-10, f"Look-ahead in 1000-row stress test: diff={diff}"


# ---------------------------------------------------------------------------
# Group (b): M1/M2 flags on hand-built stress peak-and-turn
# ---------------------------------------------------------------------------
class TestM1M2FlagsStress:
    """Build synthetic FSI and OAS series with a known stress peak-then-turn.
    Verify M1/M2 fires at the turn and not before the peak."""

    def _build_fsi_series(self, n: int = 300, peak_at: int = 200,
                          stress_level: float = 5.0) -> pd.Series:
        """Normal regime (mean 0, low vol) → sharp spike → slow decline."""
        rng = np.random.default_rng(3)
        vals = rng.standard_normal(n) * 0.3
        # Spike into high stress from peak_at-20 to peak_at
        for i in range(peak_at - 20, peak_at):
            vals[i] = stress_level * ((i - (peak_at - 20)) / 20.0)
        vals[peak_at] = stress_level
        # Slow decline after peak (still high but falling)
        for i in range(peak_at + 1, min(peak_at + 60, n)):
            vals[i] = stress_level * (1.0 - 0.02 * (i - peak_at))
        # Back to normal after
        for i in range(peak_at + 60, n):
            vals[i] = rng.standard_normal() * 0.3
        idx = _bdays("2010-01-04", n)
        return pd.Series(vals, index=idx)

    def test_m1_fires_after_peak_not_before(self):
        """M1: ofr_fsi_pctile_exp >= 0.80 AND mom15 < 0.
        Should NOT fire before the peak, SHOULD fire in the declining phase."""
        n, peak_at = 300, 200
        fsi = self._build_fsi_series(n=n, peak_at=peak_at, stress_level=5.0)

        pctile_exp = mfc._expanding_pctile(fsi)
        mom15 = fsi.diff(mfc._FSI_MOM15_WIN)
        m1 = (pctile_exp >= mfc._FSI_HIGH_PCTILE) & (mom15 < 0)

        # Before the peak (index 0..peak_at-1): pctile may be high but mom15 ≥ 0
        pre_peak = m1.iloc[:peak_at]
        # At least a few post-peak days should fire
        post_peak = m1.iloc[peak_at + mfc._FSI_MOM15_WIN: peak_at + 60]

        assert post_peak.any(), "M1 should fire at least once in declining-from-stress phase"
        # In the pure-rising phase, mom15 ≥ 0, so M1 must be False
        rising_phase = m1.iloc[peak_at - 20: peak_at]
        assert not rising_phase.any(), (
            f"M1 should not fire while FSI is still rising; fired={rising_phase.sum()}"
        )

    def test_m2_fires_after_oas_peak_not_before(self):
        """M2: hy_oas_pctile_exp >= 0.80 AND roc21 < 0."""
        n, peak_at = 300, 200
        # Use same stress shape for OAS (same semantics)
        oas = self._build_fsi_series(n=n, peak_at=peak_at, stress_level=10.0)

        pctile_exp = mfc._expanding_pctile(oas)
        roc21 = oas.diff(mfc._OAS_ROC21_WIN)
        m2 = (pctile_exp >= mfc._OAS_HIGH_PCTILE) & (roc21 < 0)

        post_peak = m2.iloc[peak_at + mfc._OAS_ROC21_WIN: peak_at + 60]
        assert post_peak.any(), "M2 should fire at least once in declining-from-stress phase"

        rising_phase = m2.iloc[peak_at - 21: peak_at]
        assert not rising_phase.any(), (
            f"M2 should not fire while OAS is still rising; fired={rising_phase.sum()}"
        )

    def test_m1_m2_never_fire_in_calm_regime(self):
        """In a pure-noise near-zero series, pctile never reaches 0.80 early
        (by definition of expanding) so M1/M2 should not fire in first 50 rows."""
        rng = np.random.default_rng(99)
        n = 200
        fsi = pd.Series(rng.standard_normal(n) * 0.1, index=_bdays("2018-01-02", n))
        oas = pd.Series(rng.standard_normal(n) * 0.1 + 3.0, index=_bdays("2018-01-02", n))

        pctile_fsi = mfc._expanding_pctile(fsi)
        pctile_oas = mfc._expanding_pctile(oas)
        mom15 = fsi.diff(15)
        roc21 = oas.diff(21)

        m1 = (pctile_fsi >= 0.80) & (mom15 < 0)
        m2 = (pctile_oas >= 0.80) & (roc21 < 0)

        # In the first 50 rows expanding-pctile cannot be 0.80 unless value is in top 20%
        # of a sample of ≤50 (possible but not in calm regime where distribution is symmetric).
        # Rather than asserting zero, assert the fraction is < 20%.
        assert m1.iloc[:50].mean() < 0.20, "M1 fires too often in calm early-sample regime"
        assert m2.iloc[:50].mean() < 0.20, "M2 fires too often in calm early-sample regime"


# ---------------------------------------------------------------------------
# Group (c): P1/P2 publish-lag discipline
# ---------------------------------------------------------------------------
class TestPublishLagDiscipline:
    """Values must NOT be visible before their publish date."""

    def test_p1_naaim_not_visible_before_publish_plus_7d(self):
        """NAAIM with 7-day lag: a survey at t should not appear before t+7 calendar days."""
        # Build a single NAAIM publish event at a known date
        publish_date = pd.Timestamp("2015-03-05")   # Thursday
        known_date = publish_date + pd.Timedelta(days=7)  # 2015-03-12

        # Simulate the builder's lag logic on a 2-row weekly series
        naaim = pd.Series(
            [50.0, 75.0],
            index=pd.DatetimeIndex([publish_date, publish_date + pd.Timedelta(weeks=1)])
        )
        lagged_index = naaim.index + pd.Timedelta(days=7)
        naaim_lagged = pd.Series(naaim.values, index=lagged_index)

        bdays = pd.bdate_range("2015-03-02", "2015-03-20")
        naaim_daily = (naaim_lagged
                       .reindex(bdays.union(naaim_lagged.index))
                       .ffill()
                       .reindex(bdays))

        # Before known_date (2015-03-12): value should be NaN (no prior context here)
        before = naaim_daily[naaim_daily.index < known_date]
        assert before.isna().all(), (
            f"NAAIM value visible before publish+7d: first non-null at "
            f"{naaim_daily.first_valid_index()}, expected >= {known_date.date()}"
        )

        # On or after known_date: value should be 50.0
        on_and_after = naaim_daily[naaim_daily.index >= known_date]
        assert on_and_after.notna().any(), "NAAIM should be visible after publish+7d"
        first_visible = naaim_daily[naaim_daily.index >= known_date].iloc[0]
        assert abs(first_visible - 50.0) < 1e-9, (
            f"Expected 50.0 at known_date, got {first_visible}"
        )

    def test_p2_cot_not_visible_before_friday_publish(self):
        """COT forward-filled from Friday publish: not visible before that Friday."""
        friday = pd.Timestamp("2015-04-10")  # a Friday
        cot = pd.Series([100.0], index=pd.DatetimeIndex([friday]))

        bdays = pd.bdate_range("2015-04-06", "2015-04-17")
        cot_daily = (cot.reindex(bdays.union(cot.index)).ffill().reindex(bdays))

        before_friday = cot_daily[cot_daily.index < friday]
        assert before_friday.isna().all(), (
            f"COT visible before Friday publish date; "
            f"first non-null: {cot_daily.first_valid_index()}"
        )

        on_and_after = cot_daily[cot_daily.index >= friday]
        assert (on_and_after == 100.0).all()

    def test_hy_oas_shift_one_business_day(self):
        """HY OAS +1bd shift: value on date d must not appear on bday grid until d+1bd."""
        obs_date = pd.Timestamp("2015-06-01")  # Monday
        known_date = obs_date + pd.offsets.BDay(1)  # Tuesday

        raw = pd.Series([3.5], index=pd.DatetimeIndex([obs_date]))
        shifted_index = raw.index + pd.offsets.BDay(1)
        shifted = pd.Series(raw.values, index=shifted_index)
        shifted = shifted[~shifted.index.duplicated(keep="last")].sort_index()

        bdays = pd.bdate_range("2015-05-29", "2015-06-05")
        hy = shifted.reindex(bdays.union(shifted.index)).ffill().reindex(bdays)

        before_known = hy[hy.index < known_date]
        assert before_known.isna().all(), (
            f"HY OAS visible before T+1bd; first value at {hy.first_valid_index()}"
        )
        on_known = hy.loc[known_date]
        assert abs(on_known - 3.5) < 1e-9


# ---------------------------------------------------------------------------
# Group (d): Weekly forward-fill correctness
# ---------------------------------------------------------------------------
class TestWeeklyForwardFill:
    """The weekly signal (NAAIM / COT) must be forward-filled correctly:
    - The flag fires from the known_date (publish+7d for NAAIM, publish for COT).
    - The flag holds until the next publish+lag event updates it.
    - A non-fire event clears the flag."""

    def test_naaim_forward_fill_until_next_publish(self):
        """NAAIM P1 True at week 1 (known_date), False at week 2 (next publish clears it),
        forward-fill correctly carries only the week-1 True window."""
        # Week 1: low NAAIM (below threshold conceptually)
        # Week 2: higher NAAIM (above threshold — flag should clear)
        pub1 = pd.Timestamp("2015-01-08")   # Thursday
        pub2 = pub1 + pd.Timedelta(weeks=1)

        known1 = pub1 + pd.Timedelta(days=7)  # 2015-01-15 (Thu)
        known2 = pub2 + pd.Timedelta(days=7)  # 2015-01-22 (Thu)

        # Directly test the forward-fill of the binary flag from known_date
        # (P1 flag computation logic depends on rolling pctile which needs many obs;
        # here we test the forward-fill mechanism directly)
        flag_wk = pd.Series(
            [True, False],
            index=pd.DatetimeIndex([known1, known2])
        )
        bdays = pd.bdate_range("2015-01-12", "2015-01-26")
        flag_daily = flag_wk.reindex(bdays.union(flag_wk.index)).ffill().reindex(bdays).fillna(False)

        # Before known1 (2015-01-15): False (no prior flag)
        before_k1 = flag_daily[flag_daily.index < known1]
        assert (before_k1 == False).all()

        # From known1 to the day before known2: True
        window_true = flag_daily[(flag_daily.index >= known1) & (flag_daily.index < known2)]
        assert window_true.all(), f"Expected True between known1 and known2, got {window_true.to_dict()}"

        # From known2 onward: False (updated by week2 = False)
        after_k2 = flag_daily[flag_daily.index >= known2]
        assert (after_k2 == False).all()

    def test_cot_forward_fill_between_fridays(self):
        """COT flag forward-filled from Friday; intermediate business days carry the
        same value until the next Friday updates it."""
        fri1 = pd.Timestamp("2015-02-06")   # Friday
        fri2 = fri1 + pd.Timedelta(weeks=1)

        flag_wk = pd.Series(
            [True, False],
            index=pd.DatetimeIndex([fri1, fri2])
        )
        bdays = pd.bdate_range("2015-02-02", "2015-02-13")
        flag_daily = flag_wk.reindex(bdays.union(flag_wk.index)).ffill().reindex(bdays).fillna(False)

        # Friday (fri1) and following week Mon-Thu: True
        true_window = flag_daily[(flag_daily.index >= fri1) & (flag_daily.index < fri2)]
        assert true_window.all(), f"Expected all True from fri1 to fri2-1d: {true_window.to_dict()}"

        # Friday 2 and after: False
        false_window = flag_daily[flag_daily.index >= fri2]
        assert (false_window == False).all()

    def test_m1_m2_are_boolean_compatible(self):
        """M1 and M2 output must be boolean (True/False/NaN → castable to bool)."""
        rng = np.random.default_rng(5)
        n = 100
        fsi = pd.Series(rng.standard_normal(n), index=_bdays("2012-01-02", n))
        oas = pd.Series(np.abs(rng.standard_normal(n)) * 3.0, index=_bdays("2012-01-02", n))

        p_fsi = mfc._expanding_pctile(fsi)
        p_oas = mfc._expanding_pctile(oas)
        mom15 = fsi.diff(15)
        roc21 = oas.diff(21)

        m1 = (p_fsi >= 0.80) & (mom15 < 0)
        m2 = (p_oas >= 0.80) & (roc21 < 0)

        assert m1.dtype in (bool, np.bool_) or m1.dtype == object, f"M1 dtype: {m1.dtype}"
        assert m2.dtype in (bool, np.bool_) or m2.dtype == object
        # Values should only be True or False (not NaN on non-null inputs)
        assert m1.dropna().isin([True, False]).all()
        assert m2.dropna().isin([True, False]).all()

    def test_expanding_pctile_single_element_is_one(self):
        """Single-element expanding rank must be 1.0 (rank=1/1 = 100th pctile)."""
        s = pd.Series([3.14], index=pd.DatetimeIndex(["2020-01-02"]))
        p = mfc._expanding_pctile(s)
        assert abs(p.iloc[0] - 1.0) < 1e-9, f"Single-element pctile: expected 1.0, got {p.iloc[0]}"


# ---------------------------------------------------------------------------
# Integration smoke: actual parquet (if present)
# ---------------------------------------------------------------------------
class TestParquetSmoke:
    """Basic sanity checks on the generated parquet — skipped if not built yet."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self._path = (
            Path(__file__).resolve().parents[1]
            / "data" / "research" / "macro_fire_context.parquet"
        )
        if not self._path.exists():
            pytest.skip("macro_fire_context.parquet not built — run build_macro_fire_context.py first")
        self._df = pd.read_parquet(self._path)

    def test_required_columns_present(self):
        required = [
            "vix", "spy_dd126", "hy_oas", "hy_oas_roc21", "hy_oas_pctile_exp",
            "ofr_fsi", "ofr_fsi_pctile_exp", "ofr_fsi_mom15",
            "stlfsi4_vintage",
            "macro_m1_fsi_turn", "macro_m2_oas_turn",
            "pos_p1_naaim_reset", "pos_p2_cot_reset",
        ]
        missing = [c for c in required if c not in self._df.columns]
        assert not missing, f"Missing columns: {missing}"

    def test_date_span_gte_2003(self):
        """Panel should start at or before 2003-01-01."""
        assert self._df.index.min() <= pd.Timestamp("2003-12-31"), (
            f"Panel starts too late: {self._df.index.min().date()}"
        )

    def test_core_series_full_coverage(self):
        """vix, spy_dd126, hy_oas, ofr_fsi must be 100% non-null in the panel."""
        for col in ("vix", "spy_dd126", "hy_oas", "ofr_fsi"):
            assert self._df[col].isna().sum() == 0, f"{col} has NaN values"

    def test_spy_dd126_is_non_positive(self):
        """spy_dd126 = price / rolling_max - 1 must be ≤ 0."""
        assert (self._df["spy_dd126"] <= 0.001).all(), (
            f"spy_dd126 has positive values: max={self._df['spy_dd126'].max()}"
        )

    def test_expanding_pctile_in_0_1(self):
        """Expanding percentile columns must be in [0, 1]."""
        for col in ("hy_oas_pctile_exp", "ofr_fsi_pctile_exp"):
            s = self._df[col].dropna()
            assert (s >= 0).all() and (s <= 1.001).all(), (
                f"{col} out of [0,1]: min={s.min()}, max={s.max()}"
            )

    def test_m1_m2_base_rates_single_digit(self):
        """M1 and M2 expected to have single-digit (< 15%) base rates."""
        m1_rate = self._df["macro_m1_fsi_turn"].mean()
        m2_rate = self._df["macro_m2_oas_turn"].mean()
        assert m1_rate < 0.15, f"M1 base rate too high: {100*m1_rate:.1f}%"
        assert m2_rate < 0.15, f"M2 base rate too high: {100*m2_rate:.1f}%"

    def test_flags_are_boolean(self):
        """Flag columns must contain only True/False (no NaN)."""
        for col in ("macro_m1_fsi_turn", "macro_m2_oas_turn",
                    "pos_p1_naaim_reset", "pos_p2_cot_reset"):
            assert self._df[col].isna().sum() == 0, f"{col} has NaN"
            assert set(self._df[col].unique()).issubset({True, False}), (
                f"{col} has unexpected values: {set(self._df[col].unique())}"
            )

    def test_stlfsi4_partial_coverage(self):
        """stlfsi4_vintage should be non-null only from ~2022 onward."""
        nn = self._df["stlfsi4_vintage"].notna()
        if nn.any():
            first_valid = self._df.index[nn][0]
            assert first_valid >= pd.Timestamp("2022-01-01"), (
                f"stlfsi4_vintage non-null before 2022: {first_valid.date()}"
            )

    def test_expanding_pctile_is_monotone_within_ties(self):
        """ofr_fsi_pctile_exp must be in [0, 1] and the builder must use the
        full OFR FSI history (pre-2002). We verify this by confirming that
        pctile values at early panel dates are < 1.0 (meaning the pre-panel
        history contributed — if only the panel start was used, row 0 would
        always be 1.0 by definition of single-element rank)."""
        p = self._df["ofr_fsi_pctile_exp"]
        # The first panel row should reflect pre-2002 OFR history.
        # With OFR data starting 2000-01-04, by 2002-01-02 there are ~500 prior
        # data points. Row 0 pctile < 1.0 iff the expanding window uses them.
        first_pctile = p.iloc[0]
        assert first_pctile < 1.0, (
            f"ofr_fsi_pctile_exp at row 0 = {first_pctile:.4f}; expected < 1.0 "
            f"because pre-2002 OFR history should be in the expanding window. "
            f"If this is 1.0 the builder dropped pre-panel history."
        )
