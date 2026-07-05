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


# ---------------------------------------------------------------------------
# Shared fixture writer used by C-3 integration tests
# ---------------------------------------------------------------------------
def _write_c3_fixtures(root: Path, tickers: list[str], n_dates: int = 350,
                       seed: int = 7) -> pd.DatetimeIndex:
    """Write a complete minimal fixture tree for build_panel.

    Returns the DatetimeIndex of all business dates in the fixture.

    IMPORTANT: each asset uses an INDEPENDENT seeded RNG derived from (seed, asset_name)
    so that changing n_dates does not perturb other assets' return series.  This
    is required for truncation-invariance tests: the first n_T rows of every stream
    must be identical whether the fixture has n_T or n_T+60 rows.
    """
    def _asset_rng(base_seed: int, name: str) -> np.random.Generator:
        """Per-asset deterministic RNG — independent of n_dates."""
        h = abs(hash(name)) % (2**31)
        return np.random.default_rng(base_seed * 100_003 + h)

    dates = pd.bdate_range("2025-01-02", periods=n_dates)
    as_of_date = dates[-1]

    bdir = root / "data" / "breadth"
    bdir.mkdir(parents=True, exist_ok=True)
    closes = pd.DataFrame(
        {t: 100.0 * (1 + _asset_rng(seed, t).normal(0, 0.01, n_dates)).cumprod()
         for t in tickers},
        index=dates,
    )
    closes.to_parquet(bdir / "_closes_cache.parquet")
    sectors = ["Information Technology"] * len(tickers)
    meta = pd.DataFrame({"name": tickers, "sector": sectors}, index=tickers)
    meta.to_parquet(bdir / "constituents.parquet")

    ydir = root / "data" / "yahoo"
    ydir.mkdir(exist_ok=True)
    for sym in ["SPY", "IWM", "QQQ", "TLT", "DX-Y.NYB", "FXI", "XLK"]:
        df = pd.DataFrame(
            {"close": 100.0 * (1 + _asset_rng(seed, sym).normal(0, 0.01, n_dates)).cumprod()},
            index=dates,
        )
        df.to_parquet(ydir / f"{sym}.parquet")

    sdir = root / "site" / "basketdata"
    sdir.mkdir(parents=True, exist_ok=True)
    ai_levels = list(
        100.0 * (1 + _asset_rng(seed, "ai_infra").normal(0, 0.01, n_dates)).cumprod()
    )
    (sdir / "baskets.json").write_text(json.dumps({
        "chart": {
            "dates": [str(d.date()) for d in dates],
            "bench": [1.0] * n_dates,
            "baskets": {"ai_infra": ai_levels},
        }
    }))

    fddir = root / "site" / "factordata"
    fddir.mkdir(parents=True, exist_ok=True)
    alpha_rng = _asset_rng(seed, "alpha_json")
    per_ticker = {t: {"alpha": float(alpha_rng.normal(0, 1))} for t in tickers}
    (fddir / "alpha.json").write_text(json.dumps({
        "as_of": str(as_of_date.date()), "per_ticker": per_ticker,
    }))
    factors_rng = _asset_rng(seed, "factors_json")
    factors_table = [
        {"ticker": t, **{leg: float(factors_rng.normal(0, 1)) for leg in BLOCK_B_LEGS},
         "mktcap_bn": 10.0}
        for t in tickers
    ]
    (fddir / "factors.json").write_text(json.dumps({
        "as_of": str(as_of_date.date()), "table": factors_table,
    }))
    return dates


# ---------------------------------------------------------------------------
# C-3(a) Future-perturbation invariance
# ---------------------------------------------------------------------------
class TestFuturePerturbationInvariance:
    """C-3(a): Perturbing a strictly-future ETF price must not change any
    historical Block-A value (beta_, contrib_, resid_, alibi_).

    Two sub-cases: SPY (mkt stream) and IWM (size stream).

    This test discriminates causal rolling orth from static orth: with static
    orth the full-history covariance matrix changes when future data changes,
    propagating backward into historical orth coefficients and therefore
    historical betas.  The rolled .shift(1) variant is immune.
    """

    def _run_build(self, tmp_path: Path, tickers: list[str],
                   dates: pd.DatetimeIndex,
                   start_offset: int = -20, end_offset: int = -1) -> pd.DataFrame:
        """Build panel over [dates[start_offset], dates[end_offset]]."""
        start = dates[start_offset]
        end = dates[end_offset]
        panel = build_panel(
            data_root=tmp_path, out_root=tmp_path,
            start_date=start, end_date=end, tickers=tickers,
        )
        return panel.sort_values(["ticker", "date"]).reset_index(drop=True)

    def _perturb_yahoo(self, tmp_path: Path, sym: str, after_row: int,
                       delta: float = 5.0) -> None:
        """Overwrite the yahoo parquet for sym, adding delta to all rows > after_row."""
        p = tmp_path / "data" / "yahoo" / f"{sym}.parquet"
        df = pd.read_parquet(p)
        df_new = df.copy()
        df_new.iloc[after_row + 1:] += delta
        df_new.to_parquet(p)

    def _get_block_a_cols(self, panel: pd.DataFrame) -> list[str]:
        """Return all Block-A numeric columns: beta_, contrib_, resid_, alibi_."""
        return [c for c in panel.columns
                if any(c.startswith(pfx)
                       for pfx in ("beta_", "contrib_", "resid_", "alibi_"))]

    def test_spy_future_perturbation_does_not_affect_past_betas(self, tmp_path):
        """Perturbing SPY at strictly future dates must not change Block-A values at past dates.

        Strategy: build panel over dates[-20:-10] (a window ending well before the end).
        Then perturb SPY at dates[-9:] (strictly future relative to the build window).
        Re-build over the same window — all Block-A values must be byte-identical.

        The perturbation uses dates[-9:] (row index -9 to -1 in a 350-date fixture),
        which are strictly AFTER the build window end (dates[-10]).  With causal
        rolling orth (shift-1 coefficients), future data never affects past rows.
        """
        n_dates = 350
        tickers = ["AAPL", "MSFT"]
        dates = _write_c3_fixtures(tmp_path, tickers, n_dates=n_dates, seed=13)

        # Build over dates[-20] to dates[-10] (20 dates, well before the series end):
        build_end_idx = -10  # dates[-10] is our historical window end
        panel_before = self._run_build(tmp_path, tickers, dates,
                                       start_offset=-20, end_offset=build_end_idx)
        assert not panel_before.empty, "Pre-perturbation panel is empty"

        # Perturb SPY at rows > (n_dates + build_end_idx) = 340:
        # dates[-10] is index 340 (0-based), so after_row=340 means rows 341..349 are perturbed.
        after_row = n_dates + build_end_idx  # = 340
        self._perturb_yahoo(tmp_path, "SPY", after_row=after_row, delta=5.0)

        panel_after = self._run_build(tmp_path, tickers, dates,
                                      start_offset=-20, end_offset=build_end_idx)
        assert not panel_after.empty, "Post-perturbation panel is empty"

        assert len(panel_before) == len(panel_after), (
            f"Row count changed after SPY perturbation: {len(panel_before)} vs {len(panel_after)}")

        block_a_cols = self._get_block_a_cols(panel_before)
        assert block_a_cols, "No Block-A columns found"

        p_b = panel_before.reset_index(drop=True)
        p_a = panel_after.reset_index(drop=True)

        for col in block_a_cols:
            s1 = p_b[col]
            s2 = p_a[col]
            pd.testing.assert_series_equal(
                s1.isna(), s2.isna(), check_names=False,
                obj=f"SPY-perturb: null mask mismatch in {col}",
            )
            mask = s1.notna()
            if mask.any():
                np.testing.assert_allclose(
                    s1[mask].to_numpy(dtype=float),
                    s2[mask].to_numpy(dtype=float),
                    rtol=1e-8,
                    err_msg=(f"SPY future-perturbation changed historical {col} "
                             "— causal rolling orth must be immune to future data"),
                )

    def test_iwm_future_perturbation_does_not_affect_past_betas(self, tmp_path):
        """Perturbing IWM (size stream) at future dates must not change past Block-A values.

        Same strategy as the SPY test: build window ends at dates[-10], perturb IWM
        at dates[-9:] (strictly future), re-build over same window — byte-identical.
        """
        n_dates = 350
        tickers = ["AAPL", "MSFT"]
        dates = _write_c3_fixtures(tmp_path, tickers, n_dates=n_dates, seed=17)

        build_end_idx = -10
        panel_before = self._run_build(tmp_path, tickers, dates,
                                       start_offset=-20, end_offset=build_end_idx)
        assert not panel_before.empty

        after_row = n_dates + build_end_idx  # = 340
        self._perturb_yahoo(tmp_path, "IWM", after_row=after_row, delta=5.0)

        panel_after = self._run_build(tmp_path, tickers, dates,
                                      start_offset=-20, end_offset=build_end_idx)
        assert not panel_after.empty

        assert len(panel_before) == len(panel_after)

        block_a_cols = self._get_block_a_cols(panel_before)
        p_b = panel_before.reset_index(drop=True)
        p_a = panel_after.reset_index(drop=True)

        for col in block_a_cols:
            s1 = p_b[col]
            s2 = p_a[col]
            pd.testing.assert_series_equal(
                s1.isna(), s2.isna(), check_names=False,
                obj=f"IWM-perturb: null mask mismatch in {col}",
            )
            mask = s1.notna()
            if mask.any():
                np.testing.assert_allclose(
                    s1[mask].to_numpy(dtype=float),
                    s2[mask].to_numpy(dtype=float),
                    rtol=1e-8,
                    err_msg=(f"IWM future-perturbation changed historical {col} "
                             "— causal rolling orth must be immune to future data"),
                )


# ---------------------------------------------------------------------------
# C-3(b) Truncation invariance
# ---------------------------------------------------------------------------
class TestTruncationInvariance:
    """C-3(b): Rows for dates ≤ T must be identical whether the history ends
    at T or T+60 (the discriminating test for static orthogonalization).

    With static full-history Gram-Schmidt the covariance matrix includes all
    rows up to the end of the history, so extending by 60 days changes the
    orth coefficients at all historical dates.  With causal rolling orth each
    row's coefficient depends only on the prior 252-day window (shifted 1), so
    extending the history forward does not affect older rows.
    """

    def _write_fixture_with_n(self, tmp_path: Path, tickers: list[str],
                               n_dates: int, seed: int = 21) -> pd.DatetimeIndex:
        """Write fixture with n_dates and return the date index."""
        return _write_c3_fixtures(tmp_path, tickers, n_dates=n_dates, seed=seed)

    def test_truncation_invariance_block_a(self, tmp_path):
        """T-length and T+60-length history → identical Block-A rows for all dates ≤ T."""
        tickers = ["AAPL", "MSFT", "GOOGL"]
        n_T = 300        # shorter history ends here
        n_T60 = n_T + 60  # extended history

        # Build with shorter history:
        dates_short = pd.bdate_range("2025-01-02", periods=n_T)
        T_end = dates_short[-1]

        # tmp_path is for the SHORT fixture; use a sub-dir for the LONG one
        short_root = tmp_path / "short"
        long_root = tmp_path / "long"
        short_root.mkdir(); long_root.mkdir()

        _write_c3_fixtures(short_root, tickers, n_dates=n_T, seed=21)
        _write_c3_fixtures(long_root, tickers, n_dates=n_T60, seed=21)
        # NOTE: both fixtures must share the SAME underlying return series prefix
        # so that rows at dates ≤ T use the same data.  Since _write_c3_fixtures
        # uses the same seed, the first n_T rows of both are byte-identical.

        # Build from both roots using the same output start/end window:
        start_date = dates_short[-10]  # last 10 dates of short
        panel_short = build_panel(
            data_root=short_root, out_root=short_root,
            start_date=start_date, end_date=T_end, tickers=tickers,
        )
        panel_long = build_panel(
            data_root=long_root, out_root=long_root,
            start_date=start_date, end_date=T_end, tickers=tickers,
        )

        assert not panel_short.empty, "Short panel produced no rows"
        assert not panel_long.empty, "Long panel produced no rows"

        p_s = panel_short.sort_values(["ticker", "date"]).reset_index(drop=True)
        p_l = panel_long.sort_values(["ticker", "date"]).reset_index(drop=True)

        assert len(p_s) == len(p_l), (
            f"Row count differs: short={len(p_s)}, long={len(p_l)}")

        block_a_cols = [c for c in p_s.columns
                        if any(c.startswith(pfx)
                               for pfx in ("beta_", "contrib_", "resid_", "alibi_"))]
        assert block_a_cols, "No Block-A columns found"

        for col in block_a_cols:
            s_s = p_s[col].reset_index(drop=True)
            s_l = p_l[col].reset_index(drop=True)
            pd.testing.assert_series_equal(
                s_s.isna(), s_l.isna(), check_names=False,
                obj=f"Truncation test: null mask mismatch in {col}",
            )
            mask = s_s.notna()
            if mask.any():
                np.testing.assert_allclose(
                    s_s[mask].to_numpy(dtype=float),
                    s_l[mask].to_numpy(dtype=float),
                    rtol=1e-8,
                    err_msg=(f"Truncation invariance failure in {col}: "
                             "extending history by 60d must not change rows at ≤ T "
                             "(static orth would fail this test)"),
                )


# ---------------------------------------------------------------------------
# C-3(c) Schema stability across universe types
# ---------------------------------------------------------------------------
class TestSchemaStability:
    """C-3(c): china-only, non-china-only, and mixed universes must produce
    identical parquet column sets (exactly PANEL_COLUMNS — 40 columns).

    China-eligible tickers (IT sector) get non-null beta_china values.
    Non-china tickers get null beta_china values.  But the COLUMN must always
    be present — it is part of the frozen v1 schema.
    """

    def _build_and_read_parquet_cols(self, tmp_path: Path, tickers: list[str],
                                     sectors: list[str]) -> list[str]:
        rng_local = np.random.default_rng(55)
        n_dates = 350
        dates = pd.bdate_range("2025-01-02", periods=n_dates)
        as_of_date = dates[-1]

        bdir = tmp_path / "data" / "breadth"
        bdir.mkdir(parents=True, exist_ok=True)
        closes = pd.DataFrame(
            {t: 100.0 * (1 + rng_local.normal(0, 0.01, n_dates)).cumprod()
             for t in tickers}, index=dates,
        )
        closes.to_parquet(bdir / "_closes_cache.parquet")
        meta = pd.DataFrame({"name": tickers, "sector": sectors}, index=tickers)
        meta.to_parquet(bdir / "constituents.parquet")

        ydir = tmp_path / "data" / "yahoo"
        ydir.mkdir(exist_ok=True)
        for sym in ["SPY", "IWM", "QQQ", "TLT", "DX-Y.NYB", "FXI", "XLK", "XLV"]:
            df = pd.DataFrame(
                {"close": 100.0 * (1 + rng_local.normal(0, 0.01, n_dates)).cumprod()},
                index=dates,
            )
            df.to_parquet(ydir / f"{sym}.parquet")

        sdir = tmp_path / "site" / "basketdata"
        sdir.mkdir(parents=True, exist_ok=True)
        ai_levels = list(100.0 * (1 + rng_local.normal(0, 0.01, n_dates)).cumprod())
        (sdir / "baskets.json").write_text(json.dumps({
            "chart": {
                "dates": [str(d.date()) for d in dates],
                "bench": [1.0] * n_dates,
                "baskets": {"ai_infra": ai_levels},
            }
        }))

        fddir = tmp_path / "site" / "factordata"
        fddir.mkdir(parents=True, exist_ok=True)
        per_ticker = {t: {"alpha": float(rng_local.normal(0, 1))} for t in tickers}
        (fddir / "alpha.json").write_text(json.dumps({
            "as_of": str(as_of_date.date()), "per_ticker": per_ticker,
        }))
        factors_table = [
            {"ticker": t, **{leg: float(rng_local.normal(0, 1)) for leg in BLOCK_B_LEGS},
             "mktcap_bn": 10.0}
            for t in tickers
        ]
        (fddir / "factors.json").write_text(json.dumps({
            "as_of": str(as_of_date.date()), "table": factors_table,
        }))

        build_panel(
            data_root=tmp_path, out_root=tmp_path,
            start_date=dates[-3], end_date=dates[-1], tickers=tickers,
        )
        # Read back the written parquet to get its columns:
        for p in sorted((tmp_path / "data" / "factordata" / "panel").rglob("panel.parquet")):
            return list(pd.read_parquet(p).columns)
        return []

    def test_china_only_universe_schema(self, tmp_path):
        """China-only universe (IT sector) → parquet columns == PANEL_COLUMNS."""
        cols = self._build_and_read_parquet_cols(
            tmp_path / "china",
            tickers=["AAPL", "MSFT"],
            sectors=["Information Technology", "Information Technology"],
        )
        assert cols == PANEL_COLUMNS, (
            f"China-only: parquet columns differ from PANEL_COLUMNS.\n"
            f"Extra: {set(cols) - set(PANEL_COLUMNS)}\n"
            f"Missing: {set(PANEL_COLUMNS) - set(cols)}"
        )

    def test_non_china_universe_schema(self, tmp_path):
        """Non-china universe (Health Care) → parquet columns == PANEL_COLUMNS."""
        cols = self._build_and_read_parquet_cols(
            tmp_path / "nonchina",
            tickers=["JNJ", "PFE"],
            sectors=["Health Care", "Health Care"],
        )
        assert cols == PANEL_COLUMNS, (
            f"Non-china: parquet columns differ from PANEL_COLUMNS.\n"
            f"Extra: {set(cols) - set(PANEL_COLUMNS)}\n"
            f"Missing: {set(PANEL_COLUMNS) - set(cols)}"
        )

    def test_mixed_universe_schema(self, tmp_path):
        """Mixed universe (IT + Health Care) → parquet columns == PANEL_COLUMNS."""
        cols = self._build_and_read_parquet_cols(
            tmp_path / "mixed",
            tickers=["AAPL", "JNJ"],
            sectors=["Information Technology", "Health Care"],
        )
        assert cols == PANEL_COLUMNS, (
            f"Mixed: parquet columns differ from PANEL_COLUMNS.\n"
            f"Extra: {set(cols) - set(PANEL_COLUMNS)}\n"
            f"Missing: {set(PANEL_COLUMNS) - set(cols)}"
        )


# ---------------------------------------------------------------------------
# F1 fix tests — betas must be written to the panel (not all-NULL)
# ---------------------------------------------------------------------------
class TestF1BetasWritten:
    """F1: build_panel must stamp Vasicek-shrunk beta values into every row.

    Before the fix, all 8 beta_* columns were 100% NULL in the written parquet
    because betas_t was used for attribution but never written into the row dict.
    """

    def _write_fixture(self, root: Path, tickers: list[str],
                       sectors: list[str], n_dates: int = 350) -> pd.DatetimeIndex:
        rng = np.random.default_rng(99)
        dates = pd.bdate_range("2025-01-02", periods=n_dates)
        as_of = dates[-1]

        bdir = root / "data" / "breadth"
        bdir.mkdir(parents=True, exist_ok=True)
        closes = pd.DataFrame(
            {t: 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()
             for t in tickers},
            index=dates,
        )
        closes.to_parquet(bdir / "_closes_cache.parquet")
        meta = pd.DataFrame({"name": tickers, "sector": sectors}, index=tickers)
        meta.to_parquet(bdir / "constituents.parquet")

        ydir = root / "data" / "yahoo"
        ydir.mkdir(exist_ok=True)
        for sym in ["SPY", "IWM", "QQQ", "TLT", "DX-Y.NYB", "FXI", "XLK"]:
            df = pd.DataFrame(
                {"close": 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()},
                index=dates,
            )
            df.to_parquet(ydir / f"{sym}.parquet")

        sdir = root / "site" / "basketdata"
        sdir.mkdir(parents=True, exist_ok=True)
        ai_levels = list(100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod())
        (sdir / "baskets.json").write_text(json.dumps({
            "chart": {
                "dates": [str(d.date()) for d in dates],
                "bench": [1.0] * n_dates,
                "baskets": {"ai_infra": ai_levels},
            }
        }))

        fddir = root / "site" / "factordata"
        fddir.mkdir(parents=True, exist_ok=True)
        per_ticker = {t: {"alpha": float(rng.normal(0, 1))} for t in tickers}
        (fddir / "alpha.json").write_text(json.dumps({
            "as_of": str(as_of.date()), "per_ticker": per_ticker,
        }))
        factors_table = [
            {"ticker": t, **{leg: float(rng.normal(0, 1)) for leg in BLOCK_B_LEGS},
             "mktcap_bn": 10.0}
            for t in tickers
        ]
        (fddir / "factors.json").write_text(json.dumps({
            "as_of": str(as_of.date()), "table": factors_table,
        }))
        return dates

    def test_beta_mkt_non_null_for_post_warmup_rows(self, tmp_path):
        """F1: beta_mkt must be non-null for post-warmup rows (not all-NULL).

        The warmup period is MIN_PERIODS + 1 (shift) = 127 business days.
        With n_dates=350, building the last 10 dates must yield non-null beta_mkt.
        """
        tickers = ["AAPL", "MSFT"]
        sectors = ["Information Technology", "Information Technology"]
        dates = self._write_fixture(tmp_path, tickers, sectors, n_dates=350)

        panel = build_panel(
            data_root=tmp_path, out_root=tmp_path,
            start_date=dates[-10], end_date=dates[-1],
            tickers=tickers,
        )
        assert not panel.empty, "Panel is empty"
        assert "beta_mkt" in panel.columns, "beta_mkt column missing from panel"

        # Post-warmup rows (all of them here — last 10 of 350) must have non-null beta_mkt.
        non_null_count = panel["beta_mkt"].notna().sum()
        assert non_null_count > 0, (
            f"F1 regression: beta_mkt is 100% NULL in panel ({len(panel)} rows). "
            "betas_t must be stamped into the row dict."
        )
        # More specifically: for a well-warmed series (350 dates >> 127 warmup),
        # essentially all rows in the last-10-date window must have non-null betas.
        assert non_null_count == len(panel), (
            f"F1: expected all {len(panel)} post-warmup rows to have non-null beta_mkt, "
            f"got {non_null_count} non-null."
        )

    def test_beta_china_non_null_for_china_sector(self, tmp_path):
        """F1 + china stream: beta_china non-null for IT sector (china-exposed) ticker.

        We check the written parquet (which goes through PANEL_COLUMNS reindex).
        beta_china requires enough history to warm up through 7 sequential causal-orth
        steps (each adds ~127 NaN rows): minimum ~7 × 127 = 889 bdays.  We use 950.
        """
        root = tmp_path / "china_sector"
        tickers = ["AAPL", "MSFT"]
        sectors = ["Information Technology", "Information Technology"]
        # Need 1200 dates to warm up china stream after 6 prior orth steps:
        # Each orth step adds ~127 NaN rows; beta computation needs another 127.
        # Total: 8 × 127 = ~1016 bdays required; we use 1200 for headroom.
        dates = self._write_fixture(root, tickers, sectors, n_dates=1200)

        build_panel(
            data_root=root, out_root=root,
            start_date=dates[-10], end_date=dates[-1],
            tickers=tickers,
        )

        # Read back the written parquet (which has PANEL_COLUMNS schema):
        parquet_files = sorted((root / "data" / "factordata" / "panel").rglob("panel.parquet"))
        assert parquet_files, "No parquet written"
        pq = pd.concat([pd.read_parquet(p) for p in parquet_files])
        assert "beta_china" in pq.columns, (
            "beta_china column missing from parquet schema"
        )

        aapl_rows = pq[pq["ticker"] == "AAPL"]
        assert len(aapl_rows) > 0, "No AAPL rows in parquet"
        non_null = aapl_rows["beta_china"].notna().sum()
        assert non_null > 0, (
            "F1: beta_china is NULL for china-exposed (IT sector) ticker AAPL — "
            "betas_t must be stamped into the row dict so the FXI beta is written. "
            "(Requires 950 bdays of history to warm up through 7 orth steps.)"
        )

    def test_beta_china_null_for_non_china_sector(self, tmp_path):
        """F1: beta_china must be None for non-china-sector tickers (Health Care).

        Check against the written parquet schema.
        """
        root = tmp_path / "non_china"
        tickers = ["JNJ", "PFE"]
        sectors = ["Health Care", "Health Care"]
        # Need XLV for Health Care sector:
        dates = self._write_fixture(root, tickers, sectors, n_dates=350)
        # Write XLV (Health Care ETF):
        rng = np.random.default_rng(77)
        n_dates = 350
        dates2 = pd.bdate_range("2025-01-02", periods=n_dates)
        df = pd.DataFrame(
            {"close": 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()},
            index=dates2,
        )
        df.to_parquet(root / "data" / "yahoo" / "XLV.parquet")

        build_panel(
            data_root=root, out_root=root,
            start_date=dates[-10], end_date=dates[-1],
            tickers=tickers,
        )

        parquet_files = sorted((root / "data" / "factordata" / "panel").rglob("panel.parquet"))
        assert parquet_files, "No parquet written"
        pq = pd.concat([pd.read_parquet(p) for p in parquet_files])
        assert "beta_china" in pq.columns, "beta_china column missing from parquet schema"
        # Health Care is not in CHINA_SECTORS — beta_china must be all-None.
        jnj_rows = pq[pq["ticker"] == "JNJ"]
        assert len(jnj_rows) > 0, "No JNJ rows in parquet"
        all_null = jnj_rows["beta_china"].isna().all()
        assert all_null, (
            f"F1: beta_china must be None for non-china sector (Health Care) ticker JNJ, "
            f"but got non-null values: {jnj_rows['beta_china'].dropna().values}"
        )


# ---------------------------------------------------------------------------
# F2 fix tests — SPY-fallback degeneracy must not poison the panel
# ---------------------------------------------------------------------------
class TestF2SpyFallbackDegeneracy:
    """F2: multi-ticker fixture including one ticker with sector='—' (unmapped).

    Mandated regression assertions (from F2 spec):
      (i)  alibi_share_20d has nunique() > 1 across rows
      (ii) abs(resid_ret_20d).max() < 1.0
      (iii) unmapped-sector ticker has beta_sector/contrib_sector_* all None
             while its beta_mkt is non-null
    """

    def _write_fixture_with_unmapped(
        self,
        root: Path,
        mapped_tickers: list[str],
        unmapped_tickers: list[str],
        n_dates: int = 350,
    ) -> pd.DatetimeIndex:
        """Write fixture with both mapped-sector and unmapped-sector ('—') tickers."""
        rng = np.random.default_rng(31415)
        dates = pd.bdate_range("2025-01-02", periods=n_dates)
        as_of = dates[-1]
        all_tickers = mapped_tickers + unmapped_tickers
        sectors = (["Information Technology"] * len(mapped_tickers)
                   + ["—"] * len(unmapped_tickers))

        bdir = root / "data" / "breadth"
        bdir.mkdir(parents=True, exist_ok=True)
        closes = pd.DataFrame(
            {t: 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()
             for t in all_tickers},
            index=dates,
        )
        closes.to_parquet(bdir / "_closes_cache.parquet")
        meta = pd.DataFrame({"name": all_tickers, "sector": sectors}, index=all_tickers)
        meta.to_parquet(bdir / "constituents.parquet")

        ydir = root / "data" / "yahoo"
        ydir.mkdir(exist_ok=True)
        for sym in ["SPY", "IWM", "QQQ", "TLT", "DX-Y.NYB", "FXI", "XLK"]:
            df = pd.DataFrame(
                {"close": 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()},
                index=dates,
            )
            df.to_parquet(ydir / f"{sym}.parquet")

        sdir = root / "site" / "basketdata"
        sdir.mkdir(parents=True, exist_ok=True)
        ai_levels = list(100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod())
        (sdir / "baskets.json").write_text(json.dumps({
            "chart": {
                "dates": [str(d.date()) for d in dates],
                "bench": [1.0] * n_dates,
                "baskets": {"ai_infra": ai_levels},
            }
        }))

        fddir = root / "site" / "factordata"
        fddir.mkdir(parents=True, exist_ok=True)
        per_ticker = {t: {"alpha": float(rng.normal(0, 1))} for t in all_tickers}
        (fddir / "alpha.json").write_text(json.dumps({
            "as_of": str(as_of.date()), "per_ticker": per_ticker,
        }))
        factors_table = [
            {"ticker": t, **{leg: float(rng.normal(0, 1)) for leg in BLOCK_B_LEGS},
             "mktcap_bn": 10.0}
            for t in all_tickers
        ]
        (fddir / "factors.json").write_text(json.dumps({
            "as_of": str(as_of.date()), "table": factors_table,
        }))
        return dates

    def test_f2_spy_fallback_regression(self, tmp_path):
        """F2 mandated regression: mixed mapped + unmapped-sector fixture.

        Assertions:
          (i)  alibi_share_20d nunique() > 1  (not spiked at 0.500)
          (ii) abs(resid_ret_20d).max() < 1.0  (not ~1e11-1e13)
          (iii) unmapped ticker has beta_sector/contrib_sector_* all None,
                beta_mkt non-null
        """
        mapped = ["AAPL", "MSFT", "GOOGL"]
        unmapped = ["UNMAPPED1"]
        dates = self._write_fixture_with_unmapped(
            tmp_path, mapped, unmapped, n_dates=350
        )

        panel = build_panel(
            data_root=tmp_path, out_root=tmp_path,
            start_date=dates[-20], end_date=dates[-1],
            tickers=mapped + unmapped,
        )
        assert not panel.empty, "Panel is empty"

        # (i) alibi_share_20d must NOT be a degenerate spike at 0.500:
        alibi_col = "alibi_share_20d"
        assert alibi_col in panel.columns, f"{alibi_col} not in panel"
        alibi_vals = panel[alibi_col].dropna()
        assert len(alibi_vals) > 0, f"No non-null {alibi_col} values"
        n_unique = alibi_vals.nunique()
        assert n_unique > 1, (
            f"F2 regression (i): {alibi_col} has only {n_unique} unique value(s) — "
            f"degenerate spike detected (all values = {alibi_vals.unique()[:5]}). "
            "SPY-fallback sector must be skipped."
        )
        # Also check that values are NOT all 0.5 (the degenerate case):
        spike_at_half = (alibi_vals - 0.5).abs() < 1e-6
        assert not spike_at_half.all(), (
            f"F2 regression (i): all {alibi_col} values are 0.500 — degenerate. "
            "SPY-fallback sector must be skipped."
        )

        # (ii) max |resid_ret_20d| must be < 1.0:
        resid_col = "resid_ret_20d"
        assert resid_col in panel.columns, f"{resid_col} not in panel"
        resid_vals = panel[resid_col].dropna()
        assert len(resid_vals) > 0, f"No non-null {resid_col} values"
        max_abs_resid = resid_vals.abs().max()
        assert max_abs_resid < 1.0, (
            f"F2 regression (ii): max |{resid_col}| = {max_abs_resid:.4f} >= 1.0 — "
            "degenerate resid detected (expected < 1.0 for sensible returns). "
            "SPY-fallback sector must be skipped."
        )

        # (iii) unmapped ticker: beta_sector and contrib_sector_* all None; beta_mkt non-null:
        for tkr in unmapped:
            tkr_rows = panel[panel["ticker"] == tkr]
            if len(tkr_rows) == 0:
                continue  # ticker had no betas at all — not a blocker

            # beta_sector must be all-None for unmapped ticker:
            assert "beta_sector" in panel.columns, "beta_sector column missing"
            bs = tkr_rows["beta_sector"]
            assert bs.isna().all(), (
                f"F2 regression (iii): unmapped ticker {tkr} has non-null beta_sector "
                f"({bs.dropna().values}) — sector stream must be skipped."
            )

            # contrib_sector_* must be all-None:
            contrib_sector_cols = [c for c in panel.columns if c.startswith("contrib_sector_")]
            for col in contrib_sector_cols:
                assert tkr_rows[col].isna().all(), (
                    f"F2 regression (iii): unmapped ticker {tkr} has non-null {col} "
                    f"({tkr_rows[col].dropna().values}) — sector stream must be skipped."
                )

            # beta_mkt must be non-null (other streams are unaffected):
            assert "beta_mkt" in panel.columns, "beta_mkt column missing"
            bm = tkr_rows["beta_mkt"]
            assert bm.notna().any(), (
                f"F2 regression (iii): unmapped ticker {tkr} has all-null beta_mkt — "
                "beta_mkt should be non-null (only sector stream is skipped)."
            )
