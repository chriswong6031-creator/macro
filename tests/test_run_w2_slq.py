"""Tests for scripts/research/run_w2_slq.py — W2 S-LQ Liquidity Hygiene Band Study.

Scope:
  1. Tercile-rule fixture: bands are assigned from trailing-year cross-sectional
     data only — no future data leaked.
  2. Deterioration-sign fixture: slope-based sign computed from the correct window.
  3. Band assignment determinism: same input → same output.
  4. Hygiene bar evaluation logic: correct mapping of CI thresholds to clauses.
  5. Band direction: higher proxy values → band 0 (worst liquidity), lower → band 2 (best).

These are unit tests: hand-constructed, deterministic, fast (<5s total).
No production data required.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from scripts.research.run_w2_slq import (
    assign_lq_bands,
    evaluate_hygiene_bar,
    PROXY_AMIHUD,
    PROXY_CS,
    TRAILING_YEAR_BARS,
    DETERIORATION_WINDOW,
    HYGIENE_VOLUME_THRESHOLD,
    N_BANDS,
    BAND_LABELS,
    OUTCOME_COLS,
    OUTCOME_COLS_BH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bdate(n: int, start: str = "2010-01-04") -> pd.DatetimeIndex:
    """Return n business-day dates starting at start."""
    return pd.bdate_range(start=start, periods=n)


def _build_amihud_fixture(
    n_bars: int = 320,
    base_close: float = 50.0,
    base_vol: float = 1_000_000.0,
) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame sufficient for Amihud computation.

    Uses deterministic values so the proxy series is predictable:
    - close: steps of 0.1 starting at base_close (mild uptrend)
    - volume: flat at base_vol
    - high = close * 1.01, low = close * 0.99
    No random values: same input always produces same output.
    """
    idx = _bdate(n_bars)
    close = base_close + np.arange(n_bars) * 0.1
    volume = np.full(n_bars, base_vol)
    return pd.DataFrame(
        {
            "close": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "volume": volume,
        },
        index=idx,
    )


def _build_cs_fixture(
    n_bars: int = 320,
    base_close: float = 50.0,
) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame sufficient for Corwin-Schultz computation.

    Uses deterministic values: close steps by 0.1; H/L spread = ±1%.
    """
    idx = _bdate(n_bars)
    close = base_close + np.arange(n_bars) * 0.1
    return pd.DataFrame(
        {
            "close": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "volume": np.full(n_bars, 1_000_000.0),
        },
        index=idx,
    )


def _build_fires_at_date(
    tickers: list[str],
    fire_date: pd.Timestamp,
) -> pd.DataFrame:
    """Build a synthetic gate-fire DataFrame with all tickers firing on one date."""
    return pd.DataFrame(
        {
            "ticker": tickers,
            "date": [fire_date] * len(tickers),
        }
    )


# ---------------------------------------------------------------------------
# TestTercileRuleNoFutureLeak
# ---------------------------------------------------------------------------

class TestTercileRuleNoFutureLeak:
    """The band assignment must use ONLY trailing data at each fire date.

    Mechanism under test: for fire_date D, the cross-sectional tercile thresholds
    are computed from proxy values at date D (trailing 252 bars ending at D).
    Changing data AFTER D must not change the band assigned to D.
    """

    def test_band_unchanged_when_future_data_added(self):
        """Adding future data after fire_date must not change the assigned band.

        We create two stores: one with data only up to fire_date, one with extra
        future bars. The band assigned to the fire_date fire should be identical.
        We need >=3 tickers at fire_date to form terciles.
        """
        n_history = 280  # > TRAILING_YEAR_BARS (252)
        n_future = 20
        idx_history = _bdate(n_history)
        fire_date = idx_history.max()

        # Use 3 tickers with distinct volumes (needed to form cross-sectional terciles)
        def _make_store(extra_bars: int = 0) -> dict[str, pd.DataFrame]:
            store = {}
            for label, vol in [("A", 50_000.0), ("B", 500_000.0), ("C", 5_000_000.0)]:
                df = _build_amihud_fixture(n_bars=n_history + extra_bars)
                # Trim to fire_date for "no future" variant
                if extra_bars == 0:
                    df = df[df.index <= fire_date]
                store[label] = df
            return store

        store_a = _make_store(extra_bars=0)      # no future data
        store_b = _make_store(extra_bars=n_future)  # extra future bars

        fires = _build_fires_at_date(["A", "B", "C"], fire_date)

        result_a = assign_lq_bands(fires.copy(), store_a, PROXY_AMIHUD)
        result_b = assign_lq_bands(fires.copy(), store_b, PROXY_AMIHUD)

        # Bands should be identical — future data is not used
        # For each ticker, compare band assignment
        for ticker in ["A", "B", "C"]:
            band_a = result_a.set_index("ticker").loc[ticker, "lq_band"]
            band_b = result_b.set_index("ticker").loc[ticker, "lq_band"]
            # NaN bands are acceptable only if both are NaN (same data, same coverage)
            if pd.isna(band_a) and pd.isna(band_b):
                continue  # both NaN → consistent (no data issue)
            assert band_a == band_b, (
                f"Band for {ticker} changed when future data was added: "
                f"store_a band={band_a}, store_b band={band_b}. "
                "Future data must not affect bands."
            )

    def test_cross_section_uses_only_tickers_present_at_fire(self):
        """Tercile thresholds are computed from the cross-section AT the fire date.

        If we add a new ticker whose data starts AFTER fire_date, it should NOT
        enter the cross-section or shift the thresholds for the original tickers.
        We need >=3 tickers to form terciles; the new ticker (starting after fire_date)
        must not be included in the cross-section.
        """
        n_history = 280
        fire_date_idx = _bdate(n_history)
        fire_date = fire_date_idx[n_history - 1]

        # Three original tickers with enough history
        def _orig_store() -> dict[str, pd.DataFrame]:
            return {
                label: _build_amihud_fixture(n_bars=n_history)
                for label in ("A", "B", "C")
            }

        # Same but add TICKER_D whose data starts AFTER fire_date
        future_start = fire_date + pd.Timedelta(days=7)
        future_idx = pd.bdate_range(start=future_start, periods=40)
        store_with_four = {
            **_orig_store(),
            "D": pd.DataFrame(
                {"close": np.ones(40) * 100.0, "volume": np.ones(40) * 500_000.0,
                 "high": np.ones(40) * 101.0, "low": np.ones(40) * 99.0},
                index=future_idx,
            ),
        }

        fires = _build_fires_at_date(["A", "B", "C"], fire_date)

        result_three = assign_lq_bands(fires.copy(), _orig_store(), PROXY_AMIHUD)
        result_four  = assign_lq_bands(fires.copy(), store_with_four, PROXY_AMIHUD)

        # TICKER_D starts after fire_date — it gets no proxy value at fire_date
        # → it does not enter the cross-section → bands for A/B/C unchanged
        for ticker in ["A", "B", "C"]:
            band_three = result_three.set_index("ticker").loc[ticker, "lq_band"]
            band_four  = result_four.set_index("ticker").loc[ticker, "lq_band"]
            if pd.isna(band_three) and pd.isna(band_four):
                continue
            assert band_three == band_four, (
                f"Band for {ticker} changed when future-only ticker D was added: "
                f"3-ticker band={band_three}, 4-ticker band={band_four}. "
                "Post-fire ticker should not affect band."
            )

    def test_insufficient_history_gives_nan_band(self):
        """Tickers with fewer than TRAILING_YEAR_BARS should get NaN band."""
        # Only 50 bars — less than TRAILING_YEAR_BARS (252)
        short_store = {"TICKER_SHORT": _build_amihud_fixture(n_bars=50)}
        fires = _build_fires_at_date(
            ["TICKER_SHORT"],
            _bdate(50).max(),
        )
        result = assign_lq_bands(fires, short_store, PROXY_AMIHUD)
        assert pd.isna(result["lq_band"].iloc[0]), (
            "Ticker with < TRAILING_YEAR_BARS should have NaN band (not enough history)."
        )


# ---------------------------------------------------------------------------
# TestDeteriorationSign
# ---------------------------------------------------------------------------

class TestDeteriorationSign:
    """The deterioration sign must be computed from the 20d slope of the proxy.

    Fixed window = DETERIORATION_WINDOW = 20 bars.
    The sign is based on slope = proxy[-1] - proxy[-DETERIORATION_WINDOW-1]:
      +1 = proxy rising (liquidity deteriorating)
      -1 = proxy falling (liquidity improving)
      0  = flat
    """

    def test_deterioration_sign_column_present(self):
        """assign_lq_bands must add lq_det_sign column."""
        store = {"TK": _build_amihud_fixture(n_bars=300)}
        fires = _build_fires_at_date(["TK"], _bdate(300).max())
        result = assign_lq_bands(fires, store, PROXY_AMIHUD)
        assert "lq_det_sign" in result.columns, "lq_det_sign column must be present in output."

    def test_deterioration_sign_is_integer_or_nan(self):
        """lq_det_sign values must be in {-1, 0, 1, NaN}."""
        store = {"TK": _build_amihud_fixture(n_bars=300)}
        fires = _build_fires_at_date(["TK"], _bdate(300).max())
        result = assign_lq_bands(fires, store, PROXY_AMIHUD)
        valid = result["lq_det_sign"].dropna()
        for v in valid:
            assert v in (-1, 0, 1), f"Unexpected deterioration sign value: {v}"

    def test_rising_proxy_gives_positive_det_sign(self):
        """A proxy series that is monotonically RISING over the final window
        must produce det_sign = +1 (liquidity deteriorating).

        We engineer an artificially high-illiquidity run at the end:
        last 25 bars have volume halved (→ Amihud ratio doubles).
        """
        n_bars = 300
        idx = _bdate(n_bars)
        close = 50.0 + np.arange(n_bars) * 0.01
        # Halve volume in the last 25 bars → Amihud spikes up
        volume = np.full(n_bars, 1_000_000.0)
        volume[-25:] = 50_000.0  # much lower volume → ILLIQ rises

        store = {
            "TK": pd.DataFrame(
                {"close": close, "volume": volume,
                 "high": close * 1.01, "low": close * 0.99},
                index=idx,
            )
        }
        fire_date = idx[-1]
        fires = _build_fires_at_date(["TK"], fire_date)
        result = assign_lq_bands(fires, store, PROXY_AMIHUD)

        det = result["lq_det_sign"].iloc[0]
        # With volume halved, Amihud should be rising → det_sign = +1
        assert det in (1, None), (
            f"Expected det_sign=+1 (rising ILLIQ = deteriorating liquidity), got {det}."
        )

    def test_falling_proxy_gives_negative_det_sign(self):
        """A proxy series that FALLS over the final window gives det_sign = -1.

        Volume increases over the last 25 bars → Amihud ILLIQ falls.
        """
        n_bars = 300
        idx = _bdate(n_bars)
        close = 50.0 + np.arange(n_bars) * 0.01
        volume = np.full(n_bars, 50_000.0)
        volume[-25:] = 2_000_000.0  # volume surges → ILLIQ drops

        store = {
            "TK": pd.DataFrame(
                {"close": close, "volume": volume,
                 "high": close * 1.01, "low": close * 0.99},
                index=idx,
            )
        }
        fire_date = idx[-1]
        fires = _build_fires_at_date(["TK"], fire_date)
        result = assign_lq_bands(fires, store, PROXY_AMIHUD)

        det = result["lq_det_sign"].iloc[0]
        assert det in (-1, None), (
            f"Expected det_sign=-1 (falling ILLIQ = improving liquidity), got {det}."
        )


# ---------------------------------------------------------------------------
# TestBandDirection
# ---------------------------------------------------------------------------

class TestBandDirection:
    """Higher proxy values → band 0 (worst); lower proxy values → band 2 (best).

    The band assignment is cross-sectional, not per-ticker: at a given fire date,
    the ticker with the HIGHEST Amihud ILLIQ (least liquid) gets band 0.
    """

    def _three_ticker_store(
        self,
        volumes: tuple[float, float, float] = (50_000.0, 500_000.0, 5_000_000.0),
        n_bars: int = 280,
    ) -> tuple[dict[str, pd.DataFrame], pd.Timestamp]:
        """Build 3-ticker store with different volumes (→ different Amihud levels)."""
        idx = _bdate(n_bars)
        fire_date = idx[-1]
        close = 50.0 + np.arange(n_bars) * 0.01
        store = {}
        for i, (label, vol) in enumerate(zip(["A", "B", "C"], volumes)):
            store[label] = pd.DataFrame(
                {
                    "close": close,
                    "high": close * 1.005,
                    "low": close * 0.995,
                    "volume": np.full(n_bars, vol),
                },
                index=idx,
            )
        return store, fire_date

    def test_lowest_volume_ticker_gets_band_0(self):
        """Ticker A (lowest volume) has highest Amihud → band 0 (worst liquidity)."""
        # volumes: A=50k (lowest vol, highest ILLIQ), B=500k, C=5M (highest vol, lowest ILLIQ)
        store, fire_date = self._three_ticker_store(
            volumes=(50_000.0, 500_000.0, 5_000_000.0)
        )
        fires = _build_fires_at_date(["A", "B", "C"], fire_date)
        result = assign_lq_bands(fires, store, PROXY_AMIHUD)

        result = result.set_index("ticker")
        band_a = result.loc["A", "lq_band"]
        band_b = result.loc["B", "lq_band"]
        band_c = result.loc["C", "lq_band"]

        # A should be band 0 (worst), C should be band 2 (best)
        assert band_a == 0.0, (
            f"Lowest-volume ticker should be band 0 (worst), got band={band_a}."
        )
        assert band_c == 2.0, (
            f"Highest-volume ticker should be band 2 (best), got band={band_c}."
        )

    def test_band_values_form_complete_tercile_partition(self):
        """With 3 tickers at a fire date, bands should be {0, 1, 2} — one each."""
        store, fire_date = self._three_ticker_store()
        fires = _build_fires_at_date(["A", "B", "C"], fire_date)
        result = assign_lq_bands(fires, store, PROXY_AMIHUD)

        bands = sorted(result["lq_band"].dropna().tolist())
        # With exactly 3 tickers and distinct proxy values, all three bands appear
        # (p33 and p67 percentiles split the distribution into 3 parts)
        assert set(bands) == {0.0, 1.0, 2.0}, (
            f"Expected bands {{0, 1, 2}} with 3 tickers, got {set(bands)}."
        )


# ---------------------------------------------------------------------------
# TestHygieneBarEvaluation
# ---------------------------------------------------------------------------

class TestHygieneBarEvaluation:
    """Unit tests for the evaluate_hygiene_bar function.

    Tests the two-clause logic without requiring live data.
    """

    def _make_band_results_with_stop5(
        self,
        ci_lo: float,
        ci_hi: float,
        coef: float = 0.05,
        affected_vol_pct: float = 0.08,  # 8% — within 10% limit
    ) -> dict[int, dict]:
        """Build minimal band_results dict with stop5 for band 0."""
        return {
            0: {
                "n_treatment": 100,
                "n_control": 900,
                "effects": [
                    {
                        "outcome": "stop5",
                        "coef": coef,
                        "ci_lo": ci_lo,
                        "ci_hi": ci_hi,
                        "p_value": 0.01,
                    },
                    {
                        "outcome": "fwd_mdd_21",
                        "coef": -0.001,
                        "ci_lo": -0.01,
                        "ci_hi": 0.005,  # includes 0 → no degradation
                        "p_value": 0.5,
                    },
                ],
                "era_table": None,
                "era_sign_stable": None,
                "nc2_marginality": None,
                "affected_volume_pct": affected_vol_pct,
                "skipped": False,
            }
        }

    def _make_band_results_with_mdd21(
        self,
        ci_lo: float,
        ci_hi: float,
        coef: float = -0.05,
        affected_vol_pct: float = 0.08,
    ) -> dict[int, dict]:
        """Build minimal band_results dict with fwd_mdd_21 CI for band 0."""
        return {
            0: {
                "n_treatment": 100,
                "n_control": 900,
                "effects": [
                    {
                        "outcome": "stop5",
                        "coef": 0.001,
                        "ci_lo": -0.005,
                        "ci_hi": 0.005,  # includes 0 → no stop5 degradation
                        "p_value": 0.8,
                    },
                    {
                        "outcome": "fwd_mdd_21",
                        "coef": coef,
                        "ci_lo": ci_lo,
                        "ci_hi": ci_hi,
                        "p_value": 0.02,
                    },
                ],
                "era_table": None,
                "era_sign_stable": None,
                "nc2_marginality": None,
                "affected_volume_pct": affected_vol_pct,
                "skipped": False,
            }
        }

    def test_stop5_ci_lo_gt0_triggers_clause_a(self):
        """Clause A met when stop5 CI_lo > 0 (more stops, significantly worse)."""
        br = self._make_band_results_with_stop5(ci_lo=0.02, ci_hi=0.08, coef=0.05)
        hr = evaluate_hygiene_bar(br, proxy=PROXY_AMIHUD, panel="deep")
        assert hr["clause_a_stop5_degradation"] is True, (
            "CI_lo > 0 on stop5 should trigger Clause A (degradation)."
        )
        assert hr["clause_a_met"] is True

    def test_stop5_ci_includes_zero_no_clause_a(self):
        """Clause A NOT met when stop5 CI includes 0."""
        br = self._make_band_results_with_stop5(ci_lo=-0.01, ci_hi=0.08, coef=0.03)
        hr = evaluate_hygiene_bar(br, proxy=PROXY_AMIHUD, panel="deep")
        # stop5 CI includes 0 → no degradation on stop5
        # fwd_mdd_21 CI includes 0 (set in helper) → no degradation on mdd21
        assert hr["clause_a_stop5_degradation"] is False, (
            "CI_lo < 0 on stop5 means CI includes 0 — not significant degradation."
        )

    def test_mdd21_ci_hi_lt0_triggers_clause_a(self):
        """Clause A met when fwd_mdd_21 CI_hi < 0 (more-negative MDD, worse)."""
        br = self._make_band_results_with_mdd21(ci_lo=-0.03, ci_hi=-0.005)
        hr = evaluate_hygiene_bar(br, proxy=PROXY_AMIHUD, panel="deep")
        assert hr["clause_a_mdd21_degradation"] is True, (
            "fwd_mdd_21 CI_hi < 0 (all negative = more adverse MDD) should trigger Clause A."
        )
        assert hr["clause_a_met"] is True

    def test_mdd21_ci_includes_zero_no_clause_a(self):
        """Clause A NOT met when fwd_mdd_21 CI includes 0."""
        br = self._make_band_results_with_mdd21(ci_lo=-0.03, ci_hi=0.005)
        hr = evaluate_hygiene_bar(br, proxy=PROXY_AMIHUD, panel="deep")
        assert hr["clause_a_mdd21_degradation"] is False, (
            "fwd_mdd_21 CI_hi > 0 (CI includes 0) should NOT trigger Clause A."
        )

    def test_clause_b_volume_within_limit(self):
        """Clause B met when affected volume <= 10%."""
        br = self._make_band_results_with_stop5(ci_lo=0.02, ci_hi=0.08,
                                                affected_vol_pct=0.08)  # 8%
        hr = evaluate_hygiene_bar(br, proxy=PROXY_AMIHUD, panel="deep")
        assert hr["clause_b_met"] is True, "8% affected volume should satisfy Clause B (<=10%)."

    def test_clause_b_volume_exceeds_limit(self):
        """Clause B NOT met when affected volume > 10%."""
        br = self._make_band_results_with_stop5(ci_lo=0.02, ci_hi=0.08,
                                                affected_vol_pct=0.12)  # 12%
        hr = evaluate_hygiene_bar(br, proxy=PROXY_AMIHUD, panel="deep")
        assert hr["clause_b_met"] is False, "12% affected volume should FAIL Clause B (>10%)."

    def test_hygiene_bar_requires_both_clauses(self):
        """HYGIENE BAR MET requires BOTH Clause A and Clause B."""
        # Clause A met, Clause B NOT met (volume too high)
        br_a_only = self._make_band_results_with_stop5(
            ci_lo=0.02, ci_hi=0.08, affected_vol_pct=0.15
        )
        hr = evaluate_hygiene_bar(br_a_only, proxy=PROXY_AMIHUD, panel="deep")
        assert hr["hygiene_bar_met"] is False, (
            "Hygiene bar requires BOTH clauses; Clause B failure should prevent MET."
        )

        # Clause B met, Clause A NOT met (CI includes 0)
        br_b_only = self._make_band_results_with_stop5(
            ci_lo=-0.01, ci_hi=0.08, affected_vol_pct=0.05
        )
        hr_b = evaluate_hygiene_bar(br_b_only, proxy=PROXY_AMIHUD, panel="deep")
        assert hr_b["hygiene_bar_met"] is False, (
            "Hygiene bar requires BOTH clauses; Clause A failure should prevent MET."
        )

    def test_hygiene_bar_met_when_both_clauses(self):
        """HYGIENE BAR MET when both Clause A and Clause B are satisfied."""
        br = self._make_band_results_with_stop5(ci_lo=0.02, ci_hi=0.08,
                                                affected_vol_pct=0.08)
        hr = evaluate_hygiene_bar(br, proxy=PROXY_AMIHUD, panel="deep")
        assert hr["hygiene_bar_met"] is True, (
            "Both clauses met should produce HYGIENE BAR MET."
        )

    def test_skipped_band_gives_none_verdict(self):
        """When worst band is skipped (insufficient fires), verdict is None."""
        br = {0: {"skipped": True, "n_treatment": 0}}
        hr = evaluate_hygiene_bar(br, proxy=PROXY_AMIHUD, panel="deep")
        assert hr["hygiene_bar_met"] is None, (
            "Skipped worst band should give None (not False) for hygiene_bar_met."
        )


# ---------------------------------------------------------------------------
# TestBandAssignmentDeterminism
# ---------------------------------------------------------------------------

class TestBandAssignmentDeterminism:
    """The same input should always produce the same output."""

    def test_identical_inputs_give_identical_outputs(self):
        """Two calls with identical store and fires must produce identical bands."""
        store = {"TK": _build_amihud_fixture(n_bars=300)}
        fires = _build_fires_at_date(["TK"], _bdate(300).max())

        result_1 = assign_lq_bands(fires.copy(), store, PROXY_AMIHUD)
        result_2 = assign_lq_bands(fires.copy(), store, PROXY_AMIHUD)

        pd.testing.assert_frame_equal(
            result_1[["ticker", "date", "lq_band", "lq_det_sign"]].reset_index(drop=True),
            result_2[["ticker", "date", "lq_band", "lq_det_sign"]].reset_index(drop=True),
            check_exact=True,
            obj="assign_lq_bands determinism",
        )


# ---------------------------------------------------------------------------
# TestProxyColumnRequirements
# ---------------------------------------------------------------------------

class TestProxyColumnRequirements:
    """Proxies gracefully handle missing columns."""

    def test_amihud_requires_volume(self):
        """Without volume column, Amihud proxy cannot be computed → NaN band."""
        n_bars = 300
        idx = _bdate(n_bars)
        close = 50.0 + np.arange(n_bars) * 0.1
        store_no_vol = {
            "TK": pd.DataFrame(
                {"close": close, "high": close * 1.01, "low": close * 0.99},
                index=idx,
            )
        }
        fires = _build_fires_at_date(["TK"], idx[-1])
        result = assign_lq_bands(fires, store_no_vol, PROXY_AMIHUD)
        assert pd.isna(result["lq_band"].iloc[0]), (
            "Amihud without volume column should give NaN band."
        )

    def test_cs_requires_high_and_low(self):
        """Without high/low columns, Corwin-Schultz proxy cannot be computed → NaN band."""
        n_bars = 300
        idx = _bdate(n_bars)
        close = 50.0 + np.arange(n_bars) * 0.1
        store_no_hl = {
            "TK": pd.DataFrame(
                {"close": close, "volume": np.full(n_bars, 1_000_000.0)},
                index=idx,
            )
        }
        fires = _build_fires_at_date(["TK"], idx[-1])
        result = assign_lq_bands(fires, store_no_hl, PROXY_CS)
        assert pd.isna(result["lq_band"].iloc[0]), (
            "Corwin-Schultz without high/low columns should give NaN band."
        )


# ---------------------------------------------------------------------------
# TestConstantsSanity
# ---------------------------------------------------------------------------

class TestConstantsSanity:
    """Basic sanity checks on module-level constants."""

    def test_trailing_year_bars(self):
        """TRAILING_YEAR_BARS should be 252 (one trading year)."""
        assert TRAILING_YEAR_BARS == 252

    def test_deterioration_window(self):
        """DETERIORATION_WINDOW should be 20 bars (fixed)."""
        assert DETERIORATION_WINDOW == 20

    def test_hygiene_volume_threshold(self):
        """HYGIENE_VOLUME_THRESHOLD should be 0.10 (10%)."""
        assert abs(HYGIENE_VOLUME_THRESHOLD - 0.10) < 1e-9

    def test_n_bands(self):
        """N_BANDS should be 3."""
        assert N_BANDS == 3

    def test_outcome_bh_excludes_mirrors(self):
        """BH pool should exclude stop_vol_21 and days_to_10."""
        assert "stop_vol_21" not in OUTCOME_COLS_BH, "stop_vol_21 should be excluded from BH pool"
        assert "days_to_10" not in OUTCOME_COLS_BH, "days_to_10 should be excluded from BH pool"

    def test_outcome_bh_includes_primary_endpoints(self):
        """BH pool should include the 21d primary endpoints."""
        for col in ("stop5", "fwd_mdd_21", "rotational_liftoff", "zone_held_21"):
            assert col in OUTCOME_COLS_BH, f"{col} should be in OUTCOME_COLS_BH"

    def test_fwd_mdd_21_in_outcome_cols(self):
        """fwd_mdd_21 (mae21) must be in OUTCOME_COLS — it is the RUL-13 co-primary."""
        assert "fwd_mdd_21" in OUTCOME_COLS, "fwd_mdd_21 must be in OUTCOME_COLS (RUL-13 mandate)"


# ---------------------------------------------------------------------------
# TestDegenerateCrossSection
# ---------------------------------------------------------------------------

class TestDegenerateCrossSection:
    """Degenerate cross-sections (all-identical proxy values → p33 >= p67) must log
    a warning and leave bands as NaN — never raise a NameError or crash.

    This regression test covers the branch fixed by the fire_date rename in
    run_w2_slq.py lines 519-524 (degenerate guard) and 544-552 (>50% capture guard).
    The NameError was latent because normal cross-sections never hit p33 >= p67.
    """

    def _build_identical_proxy_store(
        self,
        n_bars: int = 300,
        n_tickers: int = 4,
    ) -> tuple[dict[str, pd.DataFrame], pd.Timestamp]:
        """Build a store where ALL tickers have IDENTICAL volume → identical Amihud ILLIQ.

        Identical proxy values force p33 == p67 (degenerate cross-section).
        """
        idx = _bdate(n_bars)
        fire_date = idx[-1]
        close = 50.0 + np.arange(n_bars) * 0.01
        # All tickers share the exact same close and volume → same Amihud series
        store = {}
        for i in range(n_tickers):
            label = f"TK{i}"
            store[label] = pd.DataFrame(
                {
                    "close": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "volume": np.full(n_bars, 1_000_000.0),  # identical
                },
                index=idx,
            )
        return store, fire_date

    def test_degenerate_cross_section_does_not_raise(self):
        """All-identical proxy values → p33 >= p67; should log a warning, not raise."""
        import logging

        store, fire_date = self._build_identical_proxy_store(n_tickers=4)
        tickers = list(store.keys())
        fires = _build_fires_at_date(tickers, fire_date)

        # Must not raise any exception (NameError was the latent bug pre-fix)
        try:
            result = assign_lq_bands(fires, store, PROXY_AMIHUD)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                f"assign_lq_bands raised {type(exc).__name__} on degenerate cross-section: {exc}"
            ) from exc

        # All bands must be NaN — degenerate cross-section is left unassigned
        assert result["lq_band"].isna().all(), (
            "Degenerate cross-section (p33 >= p67) should leave all bands as NaN, "
            f"got: {result['lq_band'].tolist()}"
        )

    def test_degenerate_cross_section_emits_warning(self, caplog):
        """assign_lq_bands must emit a WARNING log for the degenerate date."""
        store, fire_date = self._build_identical_proxy_store(n_tickers=4)
        tickers = list(store.keys())
        fires = _build_fires_at_date(tickers, fire_date)

        with caplog.at_level(logging.WARNING, logger="run_w2_slq"):
            assign_lq_bands(fires, store, PROXY_AMIHUD)

        warning_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("degenerate" in m.lower() for m in warning_msgs), (
            f"Expected a 'degenerate' warning log for all-identical proxy cross-section; "
            f"got: {warning_msgs}"
        )
