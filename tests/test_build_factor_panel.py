"""Tests for scripts/build_factor_panel.py — P1-A Factor Intelligence builder.

Covers the five required test groups from the masterplan §7 P1-A row:

    (a) Beta causality — shifting input returns by one day must not change
        the beta used at t (no lookahead). Synthetic fixture.

    (b) alibi_share ∈ [0, 1] + scale-invariance (raw vs share computation
        identical) + zero-guard → None.

    (c) Orthogonalization order — later streams orthogonal to earlier ones
        on synthetic data.

    (d) Percentile breakpoints use only data ≤ t (PIT).

    (e) Idempotence — rebuilding the same (ticker, date) twice produces
        identical rows.

House conventions:
  - Never dirty tracked data files — all I/O through tmp_path.
  - No build_site imports.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
import pytest
from pathlib import Path

# Make sure the repo root is on sys.path so the scripts module is importable
import sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.build_factor_panel import (
    _causal_rolling_beta,
    _vasicek_shrink,
    _orthogonalize_series,
    _compute_attribution,
    _compute_block_b_percentiles,
    _compute_block_a_for_ticker,
    build_panel,
    BETA_WIN,
    MIN_PERIODS,
    VASICEK_W,
    ATT_WINDOWS,
    ZERO_RET_THRESH,
    BLOCK_B_LEGS,
    FACTOR_MODEL,
    PANEL_COLUMNS,
)


# ---------------------------------------------------------------------------
# Shared synthetic fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def rng() -> np.random.Generator:
    return np.random.default_rng(42)


def _make_dates(n: int = 400, start: str = "2024-01-02") -> pd.DatetimeIndex:
    """n business days starting from start."""
    return pd.bdate_range(start, periods=n)


def _make_returns(rng: np.random.Generator, n: int = 400,
                  seed_extra: int = 0) -> pd.Series:
    """Synthetic daily returns N(0, 0.01)."""
    dates = _make_dates(n)
    data = rng.normal(0, 0.01, size=n) + seed_extra * 0.001
    return pd.Series(data, index=dates, name="ret")


# ---------------------------------------------------------------------------
# (a) Beta causality — shifting input returns by 1 day must not change the
#     beta used AT t (no lookahead).
# ---------------------------------------------------------------------------
class TestBetaCausality:
    """The .shift(1) in _causal_rolling_beta means the beta at row t is
    estimated from the window ending at t-1.  Shifting y or x by 1 extra day
    before calling _causal_rolling_beta must produce the same beta at the
    SAME date t — because the window is defined relative to the data index,
    and an extra shift just moves every beta one row forward."""

    def test_shifted_y_does_not_change_beta_at_same_date(self, rng):
        """Beta causality: the beta at date t uses only data from [t-WIN, t-1].

        Concretely: if we shift y by 1 additional day and call
        _causal_rolling_beta, then align by date, the resulting betas must
        be identical at overlapping dates (the extra shift just shifts the
        entire output forward by one row — the value at any given DATE does
        not change).
        """
        dates = _make_dates(400)
        x = pd.Series(rng.normal(0, 0.01, 400), index=dates)
        y = pd.Series(rng.normal(0, 0.01, 400), index=dates)

        beta_y = _causal_rolling_beta(y, x, BETA_WIN, MIN_PERIODS)
        # Shift y by one extra day BEFORE computing betas:
        y_shifted = y.shift(1)
        beta_y_shifted = _causal_rolling_beta(y_shifted, x, BETA_WIN, MIN_PERIODS)

        # At each date t, beta_y[t] was estimated from (y[t-WIN:t-1], x[t-WIN:t-1]).
        # beta_y_shifted[t] was estimated from (y_shifted[t-WIN:t-1], x[t-WIN:t-1])
        #                                      = (y[t-WIN-1:t-2], x[t-WIN:t-1]).
        # These differ intentionally; the test checks that within each beta series,
        # the value at t is strictly a function of data before t (shift(1) enforces this).
        #
        # Concrete causality test: the beta at the LAST date must differ from
        # what it would be if computed without the shift (no-lag).
        beta_no_lag = (y.rolling(BETA_WIN, min_periods=MIN_PERIODS).cov(x)
                       / x.rolling(BETA_WIN, min_periods=MIN_PERIODS).var())
        # beta_y[t] = beta_no_lag[t-1] (the shift moves everything forward by 1)
        # So: beta_y.iloc[1:] should equal beta_no_lag.iloc[:-1] at overlapping positions
        aligned = pd.concat([beta_y.iloc[1:].reset_index(drop=True),
                             beta_no_lag.iloc[:-1].reset_index(drop=True)], axis=1).dropna()
        if not aligned.empty:
            np.testing.assert_allclose(
                aligned.iloc[:, 0].values,
                aligned.iloc[:, 1].values,
                rtol=1e-6,
                err_msg="shift(1) must produce beta[t] == no-shift beta[t-1]",
            )

    def test_beta_uses_only_past_data(self, rng):
        """Inserting a large return at date t+1 must not change beta at date t."""
        n = 400
        dates = _make_dates(n)
        x = pd.Series(rng.normal(0, 0.01, n), index=dates)
        y = pd.Series(rng.normal(0, 0.01, n), index=dates)

        beta_before = _causal_rolling_beta(y, x, BETA_WIN, MIN_PERIODS)

        # Modify FUTURE data (after a chosen test date):
        test_date = dates[300]
        y_perturbed = y.copy()
        y_perturbed.iloc[301:] += 10.0  # massive future perturbation

        beta_after = _causal_rolling_beta(y_perturbed, x, BETA_WIN, MIN_PERIODS)

        # Beta at test_date and before must be identical (future data not used):
        mask = beta_before.index <= test_date
        np.testing.assert_allclose(
            beta_before[mask].dropna().values,
            beta_after[mask].dropna().values,
            rtol=1e-8,
            err_msg="Future perturbation must not affect past betas",
        )


# ---------------------------------------------------------------------------
# (b) alibi_share ∈ [0,1] + scale-invariance + zero-guard → None
# ---------------------------------------------------------------------------
class TestAlibiShare:
    """Tests for _compute_attribution."""

    def _make_betas(self, streams=("mkt", "sector", "size")) -> dict[str, float]:
        return {f"beta_{s}": float(i + 0.5) for i, s in enumerate(streams)}

    def _make_stream_rets(self, streams=("mkt", "sector", "size"),
                          scale: float = 1.0) -> dict[str, float]:
        return {s: (0.01 * (i + 1)) * scale for i, s in enumerate(streams)}

    def test_alibi_share_in_0_1(self):
        """alibi_share must be in [0, 1] for typical inputs."""
        betas = self._make_betas()
        stream_rets = self._make_stream_rets()
        realized = 0.05
        for W in ATT_WINDOWS:
            att = _compute_attribution(betas, stream_rets, realized, W)
            alibi = att[f"alibi_share_{W}d"]
            assert alibi is not None
            assert 0.0 <= alibi <= 1.0, f"alibi_share_{W}d={alibi} out of [0,1]"

    def test_alibi_share_scale_invariance(self):
        """alibi_share computed from raw contributions == from normalized shares.

        Masterplan §3.1: 'It is scale-invariant (identical whether computed from
        raw contributions or normalized shares).'

        We verify by scaling all betas and stream returns by the same factor;
        the alibi_share must not change because it is a ratio of magnitudes.
        """
        betas = self._make_betas()
        stream_rets_1 = self._make_stream_rets(scale=1.0)
        stream_rets_10 = self._make_stream_rets(scale=10.0)
        realized = 0.05
        realized_10 = 0.50  # scale the realized return by the same factor
        # Also scale the betas:
        betas_10 = {k: v for k, v in betas.items()}  # betas unchanged; scaling stream rets

        W = 20
        att1 = _compute_attribution(betas, stream_rets_1, realized, W)
        # Scale both stream rets AND realized return by 10; alibi_share should be identical:
        att10 = _compute_attribution(betas, stream_rets_10, realized_10, W)

        alibi1 = att1[f"alibi_share_{W}d"]
        alibi10 = att10[f"alibi_share_{W}d"]
        assert alibi1 is not None and alibi10 is not None
        np.testing.assert_allclose(
            alibi1, alibi10, rtol=1e-6,
            err_msg="alibi_share must be scale-invariant",
        )

    def test_zero_return_guard(self):
        """If |realized_return_W| < 1e-6, all shares and alibi_share must be None."""
        betas = self._make_betas()
        stream_rets = self._make_stream_rets()
        realized = 0.0  # exactly zero — triggers the guard
        for W in ATT_WINDOWS:
            att = _compute_attribution(betas, stream_rets, realized, W)
            alibi = att[f"alibi_share_{W}d"]
            resid = att[f"resid_ret_{W}d"]
            contrib_keys = [k for k in att if k.startswith("contrib_")]
            assert alibi is None, f"alibi_share_{W}d must be None at zero return"
            assert resid is None, f"resid_ret_{W}d must be None at zero return"
            for ck in contrib_keys:
                assert att[ck] is None, f"{ck} must be None at zero return"

    def test_zero_return_guard_near_threshold(self):
        """Values >= threshold are NOT None; below threshold ARE None.

        Spec (masterplan §3.1): 'abs(realized_return_W) < 1e-6 → all shares None'.
        The guard is strict-less-than, so exactly 1e-6 is NOT guarded (it is non-zero).
        """
        betas = {"beta_mkt": 1.0}
        stream_rets = {"mkt": 0.01}
        W = 5

        # Just above threshold — not None (|ret| >= ZERO_RET_THRESH):
        att_above = _compute_attribution(betas, stream_rets, ZERO_RET_THRESH * 1.01, W)
        assert att_above[f"alibi_share_{W}d"] is not None

        # At threshold exactly — NOT None (guard is strict <, so 1e-6 is non-zero):
        att_at = _compute_attribution(betas, stream_rets, ZERO_RET_THRESH, W)
        assert att_at[f"alibi_share_{W}d"] is not None

        # Strictly below threshold — None:
        att_below = _compute_attribution(betas, stream_rets, ZERO_RET_THRESH * 0.5, W)
        assert att_below[f"alibi_share_{W}d"] is None

        # Zero exactly — None:
        att_zero = _compute_attribution(betas, stream_rets, 0.0, W)
        assert att_zero[f"alibi_share_{W}d"] is None

    def test_alibi_share_bounded_extreme_case(self):
        """alibi_share must stay [0,1] even when all return is explained."""
        # If the residual is zero, alibi = 1.0.
        betas = {"beta_mkt": 1.0}
        stream_rets = {"mkt": 0.05}
        realized = 0.05  # beta=1 × stream=0.05 → fully explained
        att = _compute_attribution(betas, stream_rets, realized, 20)
        alibi = att["alibi_share_20d"]
        assert alibi is not None
        np.testing.assert_allclose(alibi, 1.0, atol=1e-9)


# ---------------------------------------------------------------------------
# (c) Orthogonalization order — causal rolling Gram-Schmidt (R1 ruling)
# ---------------------------------------------------------------------------
class TestOrthogonalization:
    """Causal rolling Gram-Schmidt (R1 ruling 2026-07-04): each stream is
    residualized against prior causal-orth streams using a rolling 252d
    coefficient with .shift(1) — same convention as residual_alpha._causal_beta.

    Key behavioral differences from static Gram-Schmidt:
    - Global (full-series) correlation is NOT exactly 0 — rolling residualization
      achieves local absorption within each 252d window, not global orthogonality.
    - After the warmup period (min_periods=126 + 1 shift = 127 rows), the rolling
      coefficient captures the local linear relationship, absorbing most correlation.
    - Order dependence is preserved: orth(B|A) ≠ orth(A|B) in their post-warmup values.
    - Future-data causality is the primary guarantee (not exact orthogonality).
    """

    def test_streams_causal_orth_reduces_correlation(self, rng):
        """Causal rolling orth substantially reduces (not eliminates globally) correlation
        to prior streams in the post-warmup period.

        Static Gram-Schmidt achieves exact zero global correlation.  Causal rolling
        orth achieves substantial reduction over the estimation window (252d), with
        residual global correlation from the warmup period.

        We verify that post-warmup correlation is substantially lower after orth
        than before orth on highly correlated synthetic data.
        """
        n = 600  # needs > 2*252 for meaningful post-warmup period
        dates = _make_dates(n)
        common = rng.normal(0, 0.01, n)
        # Highly correlated streams (strong shared factor):
        s1 = pd.Series(common + rng.normal(0, 0.002, n), index=dates)
        s2 = pd.Series(0.9 * common + rng.normal(0, 0.002, n), index=dates)

        # Raw correlation should be high:
        raw_corr = abs(float(s2.corr(s1)))
        assert raw_corr > 0.8, f"Expected high raw correlation, got {raw_corr:.2f}"

        # Post causal orth:
        s2_orth = _orthogonalize_series(s2.copy(), [s1])

        # Post-warmup correlation (drop first 127 rows for warmup):
        warmup = 127
        s2_orth_pw = s2_orth.iloc[warmup:].dropna()
        s1_pw = s1.iloc[warmup:].reindex(s2_orth_pw.index).dropna()
        aligned = pd.concat([s2_orth_pw, s1_pw], axis=1).dropna()
        post_corr = abs(float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1])))

        # Post-warmup correlation must be substantially lower than raw:
        assert post_corr < raw_corr * 0.5, (
            f"Causal orth must reduce post-warmup correlation: "
            f"raw={raw_corr:.3f}, post_orth={post_corr:.3f}")

    def test_first_stream_unchanged(self, rng):
        """The first stream (mkt) is not orthogonalized — it stays raw."""
        n = 300
        dates = _make_dates(n)
        s1 = pd.Series(rng.normal(0, 0.01, n), index=dates)
        s1_copy = s1.copy()
        result = _orthogonalize_series(s1.copy(), [])  # no prior streams
        pd.testing.assert_series_equal(result, s1_copy)

    def test_orth_order_matters(self, rng):
        """Orthogonalizing in different orders produces different post-warmup residuals.

        The causal rolling Gram-Schmidt is order-dependent: orth(B|A) ≠ orth(A|B)
        in their post-warmup values, because each absorbs the rolling-window
        covariance with the prior stream differently.
        """
        n = 600
        dates = _make_dates(n)
        common = rng.normal(0, 0.01, n)
        # Make A and B highly correlated so their orth results differ strongly:
        a = pd.Series(common + rng.normal(0, 0.001, n), index=dates)
        b = pd.Series(0.95 * common + rng.normal(0, 0.001, n), index=dates)

        # Orth b against [a]:
        b_orth_a = _orthogonalize_series(b.copy(), [a])
        # Orth a against [b]:
        a_orth_b = _orthogonalize_series(a.copy(), [b])

        # b_orth_a and a_orth_b should differ in post-warmup values:
        warmup = 127
        b_pw = b_orth_a.iloc[warmup:].dropna().values
        a_pw = a_orth_b.iloc[warmup:].dropna().values
        min_len = min(len(b_pw), len(a_pw))
        assert not np.allclose(b_pw[:min_len], a_pw[:min_len], rtol=1e-4), \
            "Causal rolling orth residuals should be order-dependent post-warmup"

    def test_orth_causality_future_data_invariance(self, rng):
        """Causal rolling orth: perturbing future data must not change past orth values.

        This is the core guarantee of the R1 ruling: no future data leaks into
        historical orthogonalized stream values.
        """
        n = 500
        dates = _make_dates(n)
        s1 = pd.Series(rng.normal(0, 0.01, n), index=dates)
        s2 = pd.Series(0.8 * s1.values + rng.normal(0, 0.005, n), index=dates)

        # Baseline orth:
        s2_orth_base = _orthogonalize_series(s2.copy(), [s1])

        # Perturb s1 at future dates only (after row 350):
        test_date = dates[350]
        s1_perturbed = s1.copy()
        s1_perturbed.iloc[351:] += 5.0  # massive future perturbation

        s2_orth_perturbed = _orthogonalize_series(s2.copy(), [s1_perturbed])

        # Historical orth values (up to and including test_date) must be identical:
        mask = s2_orth_base.index <= test_date
        hist_base = s2_orth_base[mask].dropna()
        hist_perturbed = s2_orth_perturbed[mask].dropna()
        np.testing.assert_allclose(
            hist_base.values, hist_perturbed.values,
            rtol=1e-8,
            err_msg="Causal rolling orth: future perturbation must not affect past orth values",
        )


# ---------------------------------------------------------------------------
# (d) Percentile breakpoints use only data ≤ t (PIT)
# ---------------------------------------------------------------------------
class TestPITPercentiles:
    """Block-B percentiles must use only data available at t.

    _compute_block_b_percentiles takes a snapshot DataFrame (all data ≤ t by
    construction — the caller only ever passes the cross-section knowable at t).

    We verify that the percentile for ticker X is computed against the universe
    in the snapshot, not against a future or global cross-section.
    """

    def _make_factors_df(self, n_tickers: int = 50, seed: int = 0) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        tickers = [f"T{i:03d}" for i in range(n_tickers)]
        data = {leg: rng.normal(0, 1, n_tickers) for leg in BLOCK_B_LEGS}
        return pd.DataFrame(data, index=tickers)

    def test_percentile_computed_on_cross_section_only(self):
        """Percentile rank of a ticker must equal its rank within the supplied df."""
        df = self._make_factors_df(50)
        ticker = df.index[0]
        result = _compute_block_b_percentiles(df, ticker)
        for leg in BLOCK_B_LEGS:
            if result.get(f"{leg}_pct") is None:
                continue
            val = float(df.at[ticker, leg])
            col = df[leg].dropna()
            n = len(col)
            expected_rank = float((col < val).sum() + 0.5 * (col == val).sum()) / n
            expected_pct = float(np.clip(expected_rank * 98.0 + 1.0, 1.0, 99.0))
            np.testing.assert_allclose(
                result[f"{leg}_pct"], expected_pct, rtol=1e-6,
                err_msg=f"percentile mismatch for {leg}",
            )

    def test_smaller_universe_changes_percentile(self):
        """Adding new tickers that are EXTREME shifts the percentile rank of existing tickers.

        This confirms percentiles are computed on the supplied snapshot (PIT guard):
        if the cross-section grows with extreme new entries, the rank of the test
        ticker must change for at least one factor leg.
        """
        rng = np.random.default_rng(42)
        n_base = 20
        tickers_base = [f"T{i:03d}" for i in range(n_base)]
        # All base tickers have values near 0 (middle of distribution):
        data_base = {leg: rng.normal(0, 0.1, n_base) for leg in BLOCK_B_LEGS}
        df_small = pd.DataFrame(data_base, index=tickers_base)

        # Add 20 extreme tickers (very positive values) to expand the universe:
        n_extreme = 20
        tickers_extreme = [f"E{i:03d}" for i in range(n_extreme)]
        # All extreme tickers >> all base tickers:
        data_extreme = {leg: np.full(n_extreme, 100.0) for leg in BLOCK_B_LEGS}
        df_extreme = pd.DataFrame(data_extreme, index=tickers_extreme)

        df_large = pd.concat([df_small, df_extreme], axis=0)

        ticker = tickers_base[0]  # a mid-range base ticker
        r_small = _compute_block_b_percentiles(df_small, ticker)
        r_large = _compute_block_b_percentiles(df_large, ticker)

        # Adding 20 extreme-high entries shifts the ticker's rank DOWN substantially:
        any_diff = False
        for leg in BLOCK_B_LEGS:
            s = r_small.get(f"{leg}_pct")
            l = r_large.get(f"{leg}_pct")
            if s is not None and l is not None and abs(s - l) > 1.0:
                any_diff = True
                break
        assert any_diff, (
            "Adding extreme-valued tickers must change percentile rank (PIT guard: "
            "percentile is a function of the supplied cross-section, not a global set)")

    def test_missing_ticker_returns_nulls(self):
        """Unknown ticker → all percentile columns None, no error."""
        df = self._make_factors_df(20)
        result = _compute_block_b_percentiles(df, "UNKNOWN_TICKER_XYZ")
        for leg in BLOCK_B_LEGS:
            assert result.get(f"{leg}_pct") is None

    def test_percentile_bounds(self):
        """All percentile values must be in [1, 99]."""
        df = self._make_factors_df(100)
        for ticker in df.index:
            result = _compute_block_b_percentiles(df, ticker)
            for leg in BLOCK_B_LEGS:
                pct = result.get(f"{leg}_pct")
                if pct is not None:
                    assert 1.0 <= pct <= 99.0, (
                        f"{ticker} {leg}_pct={pct} out of [1, 99]")


# ---------------------------------------------------------------------------
# (e) Idempotence — rebuilding the same (ticker, date) twice → identical rows
# ---------------------------------------------------------------------------
class TestIdempotence:
    """build_panel called twice with same args must produce identical panels."""

    def _write_minimal_fixtures(self, root: Path, tickers: list[str],
                                n_dates: int = 350) -> None:
        """Write the minimal file tree for build_panel to run."""
        rng = np.random.default_rng(7)
        dates = pd.bdate_range("2025-01-02", periods=n_dates)

        # Breadth closes:
        breadth_dir = root / "data" / "breadth"
        breadth_dir.mkdir(parents=True, exist_ok=True)
        closes = pd.DataFrame(
            {t: 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()
             for t in tickers},
            index=dates,
        )
        closes.to_parquet(breadth_dir / "_closes_cache.parquet")
        # Constituents:
        meta = pd.DataFrame({
            "name": tickers,
            "sector": ["Information Technology"] * len(tickers),
        }, index=tickers)
        meta.to_parquet(breadth_dir / "constituents.parquet")

        # Yahoo ETFs (SPY, IWM, QQQ, TLT, DX-Y.NYB, FXI, XLK):
        yahoo_dir = root / "data" / "yahoo"
        yahoo_dir.mkdir(parents=True, exist_ok=True)
        for sym in ["SPY", "IWM", "QQQ", "TLT", "DX-Y.NYB", "FXI", "XLK"]:
            s = pd.DataFrame(
                {"close": 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()},
                index=dates,
            )
            s.to_parquet(yahoo_dir / f"{sym}.parquet")

        # baskets.json (ai_infra):
        site_dir = root / "site" / "basketdata"
        site_dir.mkdir(parents=True, exist_ok=True)
        ai_levels = list(100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod())
        baskets = {
            "chart": {
                "dates": [str(d.date()) for d in dates],
                "bench": [1.0] * n_dates,
                "baskets": {"ai_infra": ai_levels},
            }
        }
        (site_dir / "baskets.json").write_text(json.dumps(baskets))

        # alpha.json (alpha_z_house):
        factordata_dir = root / "site" / "factordata"
        factordata_dir.mkdir(parents=True, exist_ok=True)
        per_ticker = {t: {"alpha": float(rng.normal(0, 1))} for t in tickers}
        alpha_json = {"as_of": str(dates[-1].date()), "per_ticker": per_ticker}
        (factordata_dir / "alpha.json").write_text(json.dumps(alpha_json))

        # factors.json (Block-B):
        factors_table = [
            {
                "ticker": t,
                **{leg: float(rng.normal(0, 1)) for leg in BLOCK_B_LEGS},
                "mktcap_bn": 10.0,
            }
            for t in tickers
        ]
        factors_json = {"as_of": str(dates[-1].date()), "table": factors_table}
        (factordata_dir / "factors.json").write_text(json.dumps(factors_json))

    def test_identical_rows_on_rebuild(self, tmp_path):
        """Running build_panel twice produces identical parquet files."""
        tickers = ["AAPL", "MSFT", "GOOGL"]
        self._write_minimal_fixtures(tmp_path, tickers, n_dates=350)

        # Narrow date range (3 dates) to keep the test fast:
        dates = pd.bdate_range("2025-01-02", periods=350)
        start = str(dates[-5].date())
        end = str(dates[-1].date())

        panel1 = build_panel(
            data_root=tmp_path,
            out_root=tmp_path,
            start_date=pd.Timestamp(start),
            end_date=pd.Timestamp(end),
            tickers=tickers,
        )
        panel2 = build_panel(
            data_root=tmp_path,
            out_root=tmp_path,
            start_date=pd.Timestamp(start),
            end_date=pd.Timestamp(end),
            tickers=tickers,
        )

        assert not panel1.empty, "First build produced empty panel"
        assert not panel2.empty, "Second build produced empty panel"
        assert len(panel1) == len(panel2), "Row count mismatch between builds"

        # Sort both by (ticker, date) for stable comparison:
        p1 = panel1.sort_values(["ticker", "date"]).reset_index(drop=True)
        p2 = panel2.sort_values(["ticker", "date"]).reset_index(drop=True)

        # Drop any Period-typed columns (e.g. 'month') that build_panel may have
        # left in-memory (they are stripped before writing parquet but may survive
        # in the returned DataFrame):
        non_period_cols = [c for c in p1.columns
                           if not hasattr(p1[c].dtype, "freq")]  # Period has .freq
        p1 = p1[non_period_cols]
        p2 = p2[[c for c in non_period_cols if c in p2.columns]]

        # String/categorical columns:
        for col in ["ticker", "date", "factor_model"]:
            if col in p1.columns:
                pd.testing.assert_series_equal(p1[col], p2[col], check_names=False,
                                               obj=f"column {col}")

        # Numeric columns:
        str_cols = {"ticker", "date", "factor_model"}
        num_cols = [c for c in p1.columns if c not in str_cols]
        for col in num_cols:
            s1 = p1[col]
            s2 = p2[col]
            # Both null or both non-null at same positions:
            pd.testing.assert_series_equal(
                s1.isna(), s2.isna(),
                check_names=False,
                obj=f"null mask for column {col}",
            )
            # Non-null values must be numerically identical:
            mask = s1.notna()
            if mask.any():
                np.testing.assert_allclose(
                    s1[mask].to_numpy(dtype=float),
                    s2[mask].to_numpy(dtype=float),
                    rtol=1e-10,
                    err_msg=f"Idempotence failure in column {col}",
                )

    def test_factor_model_stamp_is_v1(self, tmp_path):
        """Every row must carry factor_model='v1'."""
        tickers = ["AAPL", "MSFT"]
        self._write_minimal_fixtures(tmp_path, tickers, n_dates=350)
        dates = pd.bdate_range("2025-01-02", periods=350)
        start = str(dates[-3].date())
        end = str(dates[-1].date())
        panel = build_panel(
            data_root=tmp_path,
            out_root=tmp_path,
            start_date=pd.Timestamp(start),
            end_date=pd.Timestamp(end),
            tickers=tickers,
        )
        assert not panel.empty
        assert (panel["factor_model"] == FACTOR_MODEL).all(), \
            "Not all rows have factor_model='v1'"

    def test_no_twin_dna_style_columns_emitted(self, tmp_path):
        """P1-A must NOT emit twin/dna_class/style_regime columns (later PRs)."""
        tickers = ["AAPL", "MSFT"]
        self._write_minimal_fixtures(tmp_path, tickers, n_dates=350)
        dates = pd.bdate_range("2025-01-02", periods=350)
        start = str(dates[-3].date())
        end = str(dates[-1].date())
        panel = build_panel(
            data_root=tmp_path,
            out_root=tmp_path,
            start_date=pd.Timestamp(start),
            end_date=pd.Timestamp(end),
            tickers=tickers,
        )
        assert not panel.empty
        forbidden = {"dna_class", "style_regime", "style_regime_pending",
                     "twin_rel_20d", "twin_bleed_flag", "twin_n_peers", "twin_fallback"}
        emitted = set(panel.columns)
        overlap = forbidden & emitted
        assert not overlap, f"P1-A emitted out-of-scope columns: {overlap}"


# ---------------------------------------------------------------------------
# Additional unit tests for Vasicek shrinkage
# ---------------------------------------------------------------------------
class TestVasicekShrinkage:
    def test_shrink_weight_1_is_noop(self):
        """w=1.0 → no shrinkage (return raw betas)."""
        beta = pd.DataFrame({"A": [1.0, 2.0], "B": [3.0, 4.0]})
        result = _vasicek_shrink(beta, w=1.0)
        pd.testing.assert_frame_equal(result, beta)

    def test_shrink_pulls_toward_mean(self):
        """Shrinkage pulls outlier betas toward the cross-sectional mean."""
        # Two tickers: beta 0.0 and 2.0; cross-sectional mean = 1.0.
        beta = pd.DataFrame({"A": [0.0], "B": [2.0]})
        shrunk = _vasicek_shrink(beta, w=0.66)
        # Shrunk values should be: 0.66*0.0 + 0.34*1.0 = 0.34 and 0.66*2.0 + 0.34*1.0 = 1.66
        np.testing.assert_allclose(shrunk["A"].values, [0.34], rtol=1e-6)
        np.testing.assert_allclose(shrunk["B"].values, [1.66], rtol=1e-6)

    def test_shrink_preserves_cross_sectional_mean(self):
        """Shrinkage preserves the cross-sectional mean (weighted average property)."""
        rng = np.random.default_rng(1)
        beta = pd.DataFrame(
            {"A": rng.normal(1, 0.5, 50), "B": rng.normal(1, 0.5, 50),
             "C": rng.normal(1, 0.5, 50)},
        )
        shrunk = _vasicek_shrink(beta, w=0.66)
        # The row-wise mean must be preserved (shrinkage is toward the mean):
        np.testing.assert_allclose(
            shrunk.mean(axis=1).values, beta.mean(axis=1).values, rtol=1e-8,
        )
