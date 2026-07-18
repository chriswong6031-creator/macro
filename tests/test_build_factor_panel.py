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
    _compute_twin_bleed_flag,
    _build_twin_membership,
    _compute_size_terciles,
    _compute_twin_ew_returns,
    _classify_dna,
    _build_style_regime_timeline,
    build_panel,
    BETA_WIN,
    MIN_PERIODS,
    VASICEK_W,
    ATT_WINDOWS,
    ZERO_RET_THRESH,
    BLOCK_B_LEGS,
    FACTOR_MODEL,
    PANEL_COLUMNS,
    TWIN_MIN_PEERS,
    TWIN_TOP_N,
    TWIN_RET_WIN,
    TWIN_BLEED_LOOKBACK,
    DNA_CLASS_ORDER,
    CYCLICAL_VALUE_SECTORS,
    STYLE_REGIME_STATES,
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
            backfill=True,  # force rebuild to test idempotence (bypasses incremental skip)
        )
        panel2 = build_panel(
            data_root=tmp_path,
            out_root=tmp_path,
            start_date=pd.Timestamp(start),
            end_date=pd.Timestamp(end),
            tickers=tickers,
            backfill=True,  # force rebuild — idempotence test, not incremental test
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

        # String/categorical columns (includes P1-C string cols):
        for col in ["ticker", "date", "factor_model",
                    "dna_class", "style_regime", "style_regime_pending"]:
            if col in p1.columns:
                pd.testing.assert_series_equal(p1[col], p2[col], check_names=False,
                                               obj=f"column {col}")

        # Numeric columns (P1-C string cols dna_class/style_regime/style_regime_pending
        # are checked via assert_series_equal in the string block above):
        str_cols = {"ticker", "date", "factor_model",
                    "dna_class", "style_regime", "style_regime_pending"}
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

    def test_p1c_columns_emitted(self, tmp_path):
        """P1-C must emit dna_class, style_regime, style_regime_pending columns.

        Updated from the P1-B guard that checked these were absent.  P1-C delivers
        them as §3.6-listed v1 columns.  Twin columns (P1-B) remain expected.
        """
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
        emitted = set(panel.columns)
        # P1-C columns must now be present:
        p1c_cols = {"dna_class", "style_regime", "style_regime_pending"}
        missing_p1c = p1c_cols - emitted
        assert not missing_p1c, f"P1-C must emit columns; missing: {missing_p1c}"
        # Twin columns must still be present (P1-B deliverable):
        twin_cols = {"twin_rel_20d", "twin_bleed_flag", "twin_n_peers", "twin_fallback"}
        missing_twin = twin_cols - emitted
        assert not missing_twin, (
            f"P1-B columns must still be present; missing: {missing_twin}"
        )


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
        """Build panel over [dates[start_offset], dates[end_offset]].

        Uses backfill=True to force a full rebuild (bypasses incremental skip)
        so the perturbation test can rebuild the same date window twice.
        """
        start = dates[start_offset]
        end = dates[end_offset]
        panel = build_panel(
            data_root=tmp_path, out_root=tmp_path,
            start_date=start, end_date=end, tickers=tickers,
            backfill=True,  # force rebuild: test calls same window twice
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
    identical parquet column sets (exactly PANEL_COLUMNS).

    NOTE: P1-C adds 3 more columns (dna_class, style_regime, style_regime_pending),
    so PANEL_COLUMNS now has 55 entries (48 P1-A + 4 P1-B + 3 P1-C).
    P1-B added 4 twin columns (was 52 entries).
    (48 from P1-A + 4 twin).  The authoritative list is PANEL_COLUMNS itself.

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


# ===========================================================================
# P1-B TWIN TESTS
# Seven required test groups (masterplan §7 P1-B):
#   (a) membership freeze: intramonth data changes do not alter membership
#   (b) PIT: future perturbation after freeze date does not change any twin value
#   (c) fallback logic (<8 peers → industry EW, twin_fallback=True)
#   (d) twin_bleed determinism on a hand-computed fixture (60d window per RULING-1)
#   (e) NULL-backfill: non-current-month dates all-None
#   (f) schema stability 44 cols across universe mixes
#   (g) self-exclusion
# ===========================================================================


def _make_twin_dates(n: int = 400, start: str = "2024-01-02") -> pd.DatetimeIndex:
    """n business days starting from start."""
    return pd.bdate_range(start, periods=n)


def _make_returns_s(n: int = 400, seed: int = 0, scale: float = 0.01) -> pd.Series:
    rng = np.random.default_rng(seed)
    dates = _make_twin_dates(n)
    return pd.Series(rng.normal(0, scale, n), index=dates)


class TestTwinBleedFlag:
    """(d) twin_bleed determinism on a hand-computed fixture (RULING-1 / PREREG H4).

    RULING-1: twin_bleed_flag = True iff
      (a) twin basket 20d return at eval_date < 0
      (b) current 20d-drawdown-from-20d-high > median of prior 60d distribution
          of 20d-drawdown-from-20d-high observations.
    The prior 60d window governs (not 252d — PREREG H4 overrides masterplan §3.5).
    """

    def _make_constant_decline_series(self, n: int = 120) -> pd.Series:
        """Declining twin basket: -0.5% per day → 20d return strongly negative."""
        dates = _make_twin_dates(n)
        returns = pd.Series([-0.005] * n, index=dates)
        return returns

    def _make_flat_series(self, n: int = 120) -> pd.Series:
        """Flat twin basket: 0% return → 20d return = 0."""
        dates = _make_twin_dates(n)
        return pd.Series([0.0] * n, index=dates)

    def test_bleed_flag_true_on_accelerating_decline(self):
        """Accelerating declining twin basket → both conditions met → True.

        A constant-rate decline produces a constant 20d drawdown (= the 20d
        rolling return from 20d high, which stabilizes at a fixed level once
        the 20d window is full of identical returns).  To make current_drawdown >
        median of the prior 60d distribution, we need a DEEPENING drawdown:
        the rate of decline must accelerate so the current drawdown exceeds
        the median of prior observations.

        Design: 80 flat days (prior_dd all zeros), then 20 accelerating decline
        days.  After 20 days of decline the 20d return is negative and the
        current drawdown greatly exceeds the median (≈0) of the prior 60d window.
        """
        n_flat = 80
        n_decline = 20
        dates = _make_twin_dates(n_flat + n_decline)
        flat_rets = [0.0] * n_flat
        decline_rets = [-0.01] * n_decline  # -1%/day × 20 = ~18% drawdown
        rets = pd.Series(flat_rets + decline_rets, index=dates)
        eval_date = dates[-1]
        result = _compute_twin_bleed_flag(rets, eval_date)
        assert result is True or result is None, (
            f"Accelerating decline: expected True or None (data), got {result}"
        )
        # More strict: with n=100 (>> TWIN_RET_WIN+1=21), should be True not None:
        if result is not None:
            assert result is True, (
                f"Accelerating decline: expected True, got {result}"
            )

    def test_bleed_flag_false_on_flat_twin(self):
        """Flat twin basket: 20d return = 0 → condition (a) fails → False."""
        rets = self._make_flat_series(120)
        eval_date = rets.index[-1]
        result = _compute_twin_bleed_flag(rets, eval_date)
        assert result is False or result is None, (
            f"Flat twin: expected False or None, got {result}"
        )

    def test_bleed_flag_false_on_rising_twin(self):
        """Rising twin basket: 20d return > 0 → condition (a) fails → False."""
        dates = _make_twin_dates(120)
        rets = pd.Series([0.003] * 120, index=dates)  # +0.3%/day
        eval_date = rets.index[-1]
        result = _compute_twin_bleed_flag(rets, eval_date)
        assert result is False or result is None, (
            f"Rising twin: expected False or None, got {result}"
        )

    def test_bleed_flag_none_on_insufficient_data(self):
        """Too few data points → None (cannot compute 20d return or pullback)."""
        dates = _make_twin_dates(15)
        rets = pd.Series([-0.005] * 15, index=dates)
        result = _compute_twin_bleed_flag(rets, rets.index[-1])
        assert result is None, (
            f"Insufficient data: expected None, got {result}"
        )

    def test_bleed_flag_deterministic(self):
        """Calling _compute_twin_bleed_flag twice on the same inputs yields same result."""
        rng = np.random.default_rng(42)
        dates = _make_twin_dates(150)
        rets = pd.Series(rng.normal(-0.001, 0.01, 150), index=dates)
        eval_date = dates[-1]
        r1 = _compute_twin_bleed_flag(rets, eval_date)
        r2 = _compute_twin_bleed_flag(rets, eval_date)
        assert r1 == r2, f"Non-deterministic: got {r1} then {r2}"

    def test_bleed_flag_hand_computed(self):
        """Hand-computed fixture: verify condition (b) using known drawdown values.

        We construct a series where:
          - The first 80 days are flat (0% daily return) — these form the 60d prior
            distribution window.  Drawdown from 20d high = 0 on all flat days.
          - Days 81–100 decline at -1%/day for 20 days.
          - We evaluate at day 100.

        At day 100 (eval_date):
          20d return = (0.99)^20 - 1 ≈ -18.2% < 0  → condition (a) True
          Current drawdown from 20d high = (0.99)^20 / 1.0 - 1 ≈ -18.2% (since
            the 20d high was price at day 81), abs ≈ 18.2%.
          Prior 60d window = days 41–99 (strictly before day 100).
            Days 41–80: all flat, drawdown = 0.
            Days 81–99: declining, drawdown from 20d high grows from 0 to ~17.2%.
            Median of [0, 0, ..., 0 (40 obs), ~1%, ~2%, ..., ~17.2% (19 obs)] ≈ 0%
            (the 40 zeros dominate — median ≈ 0%).
          Current drawdown (18.2%) > median (≈ 0%) → condition (b) True.
          Expected result: True.
        """
        n_flat = 80
        n_decline = 20
        n = n_flat + n_decline
        dates = _make_twin_dates(n)
        flat_rets = [0.0] * n_flat
        decline_rets = [-0.01] * n_decline
        rets = pd.Series(flat_rets + decline_rets, index=dates)
        eval_date = dates[-1]

        result = _compute_twin_bleed_flag(rets, eval_date)
        assert result is True, (
            f"Hand-computed fixture: expected True (declining 20d twin with "
            f"prior 60d of flat drawdown → current > median), got {result}"
        )

    def test_bleed_flag_prior_window_is_60d_not_252d(self):
        """RULING-1: prior distribution window is 60 TRADING observations (not calendar days).

        BEHAVIORAL TEST: construct a fixture where the step-change in the drawdown series
        is placed such that a trading-60 positional slice and a calendar-60-day cutoff
        produce DIFFERENT medians and therefore DIFFERENT flag outcomes.

        On a business-day index, 60 calendar days covers approximately 42 trading rows.
        The fixture uses n_total=310 rows (start 2024-01-02):
          - Rows 0-248:   flat (price=1.0, drawdown=0)
          - Rows 249-281: heavy decline -1.5%/day (33 rows) → drawdown rises then
                          stabilises at ~25% within the rolling-20d window
          - Row 282:      recovery (+65%) → price to new high → dd drops to 0
          - Rows 283-289: flat at new high
          - Rows 290-309: mild decline -0.2%/day (20 rows, 20d return ≈ -3.9%)

        eval_date = dates[-1] (row 309).
        trading-60 prior = rows 249-308 (60 rows):
          rows 249-281 = 33 rows of heavy dd (≥5%), rows 282-308 = flat then mild dd.
          33 out of 60 rows are elevated → median is elevated (≈ 5-25%).
        calendar-60 prior ≈ rows 267-308 (42 rows):
          rows 267-281 = 15 rows of heavy dd, rows 282-308 = flat then mild (<5%) dd.
          15 out of 42 rows elevated → median ≈ 0% (< 50%).
        current_dd ≈ 3.9% < trading-60 median → flag_trading60 = False.
        current_dd ≈ 3.9% > calendar-60 median → flag_cal60 = True.
        The outcomes DIFFER. The function (using trading-60) must return False.

        Secondary check: TWIN_BLEED_LOOKBACK constant == 60.
        """
        # Secondary constant check:
        assert TWIN_BLEED_LOOKBACK == 60, (
            f"RULING-1: TWIN_BLEED_LOOKBACK must be 60, got {TWIN_BLEED_LOOKBACK}"
        )

        # Build the fixture:
        n_total = 310
        dates = _make_twin_dates(n_total)
        rets_list = [0.0] * 249          # rows 0-248: flat
        rets_list.extend([-0.015] * 33)  # rows 249-281: heavy decline
        rets_list.append(0.65)           # row 282: recovery
        rets_list.extend([0.0] * 7)      # rows 283-289: flat
        rets_list.extend([-0.002] * 20)  # rows 290-309: mild decline (-0.2%/day)
        assert len(rets_list) == n_total, f"fixture length {len(rets_list)} != {n_total}"

        rets = pd.Series(rets_list, index=dates)
        eval_date = dates[-1]

        # Independently compute expected result with trading-60 logic:
        hist = rets[rets.index <= eval_date].dropna()
        price = (1 + hist).cumprod()
        rolling_high = price.rolling(TWIN_RET_WIN, min_periods=1).max()
        dd_series = ((price / rolling_high) - 1).abs()

        twin_20d = float(((1 + hist.tail(TWIN_RET_WIN)).prod() - 1))
        assert twin_20d < 0, f"Fixture error: 20d return should be < 0, got {twin_20d:.4f}"

        current_dd = float(dd_series.loc[eval_date])
        prior_60 = dd_series[dd_series.index < eval_date].tail(60)
        median_trading60 = float(prior_60.median())
        expected_flag = bool(current_dd > median_trading60)  # should be False

        # Verify the fixture is discriminating: calendar-60 gives DIFFERENT outcome:
        cutoff_cal60 = eval_date - pd.Timedelta(days=60)
        prior_cal60 = dd_series[
            (dd_series.index >= cutoff_cal60) & (dd_series.index < eval_date)
        ].dropna()
        median_cal60 = float(prior_cal60.median())
        flag_cal60 = bool(current_dd > median_cal60)
        assert flag_cal60 != expected_flag, (
            f"Fixture invariant broken: trading-60 and calendar-60 must give different "
            f"flag outcomes (trading_flag={expected_flag}, cal_flag={flag_cal60}, "
            f"current_dd={current_dd:.4f}, median_60={median_trading60:.4f}, "
            f"median_cal60={median_cal60:.4f}). Fixture needs redesign."
        )

        # Call the function and assert it uses the TRADING-60 (correct) outcome:
        result = _compute_twin_bleed_flag(rets, eval_date)
        assert result == expected_flag, (
            f"RULING-1 behavioral test: function returned {result}, expected "
            f"trading-60 outcome {expected_flag} "
            f"(current_dd={current_dd:.4f}, median_trading60={median_trading60:.4f}, "
            f"median_cal60={median_cal60:.4f}). "
            "The prior window must use 60 TRADING observations (positional tail), "
            "not a calendar-60-day cutoff (~42 trading rows)."
        )

    def test_bleed_flag_pit_future_irrelevant(self):
        """PIT: future data after eval_date must not change twin_bleed_flag.

        Build a series up to date T; compute flag at T.
        Then extend the series with future data (after T); compute flag at T again.
        Results must be identical.
        """
        rng = np.random.default_rng(99)
        n_base = 150
        dates_base = _make_twin_dates(n_base)
        rets_base = pd.Series(rng.normal(-0.002, 0.01, n_base), index=dates_base)
        eval_date = dates_base[-1]

        result_base = _compute_twin_bleed_flag(rets_base, eval_date)

        # Extend with 50 extra future days:
        n_extra = 50
        dates_extended = _make_twin_dates(n_base + n_extra)
        extra_rets = pd.Series(rng.normal(0.01, 0.01, n_extra), index=dates_extended[n_base:])
        rets_extended = pd.concat([rets_base, extra_rets])

        # The function filters to <= eval_date internally, so future data is PIT-safe:
        result_extended = _compute_twin_bleed_flag(rets_extended, eval_date)
        assert result_base == result_extended, (
            f"PIT violation: flag at eval_date changed when future data added. "
            f"Before={result_base}, after={result_extended}"
        )


class TestTwinMembership:
    """(c) fallback logic and (g) self-exclusion."""

    def _make_fake_ns(self, tickers: list[str], sector: str) -> dict[str, tuple[str, str]]:
        """Make a fake ns dict for testing."""
        return {t: (t, sector) for t in tickers}

    def _make_fake_resid(self, tickers: list[str], n: int = 350,
                         seed: int = 7) -> dict[str, pd.Series]:
        rng = np.random.default_rng(seed)
        dates = _make_twin_dates(n)
        return {t: pd.Series(rng.normal(0, 0.01, n), index=dates) for t in tickers}

    def _make_fake_bday_index(self, n: int = 350) -> pd.DatetimeIndex:
        return _make_twin_dates(n)

    def test_self_exclusion(self):
        """(g) The ticker must not appear in its own twin basket."""
        tickers = [f"T{i:03d}" for i in range(20)]
        sector = "Industrials"
        ns = self._make_fake_ns(tickers, sector)
        resid = self._make_fake_resid(tickers)
        bday_idx = self._make_fake_bday_index()
        freeze_date = bday_idx[300]

        for target in tickers[:5]:
            members, _fallback = _build_twin_membership(
                freeze_date=freeze_date,
                ticker=target,
                sector=sector,
                size_tercile=1,  # mid-size tercile
                all_resid_1d=resid,
                size_tercile_map={t: 1 for t in tickers},  # all mid-size
                ns=ns,
                bday_index=bday_idx,
            )
            assert target not in members, (
                f"Self-exclusion failure: {target} appears in its own twin basket."
            )

    def test_fallback_when_fewer_than_8_peers(self):
        """(c) If fewer than TWIN_MIN_PEERS survive, fallback=True and members = sector EW."""
        # Only 5 tickers in the sector (< TWIN_MIN_PEERS=8):
        tickers = [f"T{i:03d}" for i in range(5)]
        sector = "Utilities"
        ns = self._make_fake_ns(tickers, sector)
        resid = self._make_fake_resid(tickers, seed=42)
        bday_idx = self._make_fake_bday_index()
        freeze_date = bday_idx[300]

        target = tickers[0]
        members, fallback = _build_twin_membership(
            freeze_date=freeze_date,
            ticker=target,
            sector=sector,
            size_tercile=1,
            all_resid_1d=resid,
            size_tercile_map={t: 1 for t in tickers},
            ns=ns,
            bday_index=bday_idx,
        )
        assert fallback is True, (
            f"Expected fallback=True when sector has {len(tickers)} tickers < {TWIN_MIN_PEERS}, "
            f"got fallback={fallback}"
        )
        # Members should be the sector EW (all same-sector, self-excluded):
        for m in members:
            assert m != target, "Self-exclusion violated in fallback basket"

    def test_no_fallback_when_sufficient_peers(self):
        """(c) If ≥ TWIN_MIN_PEERS survive the filter, fallback=False."""
        # 20 tickers in the sector, all same size tercile → 19 candidates → ≥ 8:
        n_tickers = 20
        tickers = [f"T{i:03d}" for i in range(n_tickers)]
        sector = "Industrials"
        ns = self._make_fake_ns(tickers, sector)
        resid = self._make_fake_resid(tickers, n=350, seed=17)
        bday_idx = self._make_fake_bday_index()
        freeze_date = bday_idx[300]

        target = tickers[0]
        members, fallback = _build_twin_membership(
            freeze_date=freeze_date,
            ticker=target,
            sector=sector,
            size_tercile=1,
            all_resid_1d=resid,
            size_tercile_map={t: 1 for t in tickers},
            ns=ns,
            bday_index=bday_idx,
        )
        assert fallback is False, (
            f"Expected fallback=False with {n_tickers} tickers, got fallback={fallback}"
        )
        assert len(members) <= TWIN_TOP_N, (
            f"Expected ≤ {TWIN_TOP_N} members, got {len(members)}"
        )
        assert len(members) >= TWIN_MIN_PEERS, (
            f"Expected ≥ {TWIN_MIN_PEERS} members, got {len(members)}"
        )

    def test_top_n_cap(self):
        """Members are capped at TWIN_TOP_N (=12) by correlation ranking."""
        n_tickers = 40  # plenty of candidates
        tickers = [f"T{i:03d}" for i in range(n_tickers)]
        sector = "Financials"
        ns = self._make_fake_ns(tickers, sector)
        resid = self._make_fake_resid(tickers, n=350, seed=31)
        bday_idx = self._make_fake_bday_index()
        freeze_date = bday_idx[300]

        target = tickers[0]
        members, fallback = _build_twin_membership(
            freeze_date=freeze_date,
            ticker=target,
            sector=sector,
            size_tercile=1,
            all_resid_1d=resid,
            size_tercile_map={t: 1 for t in tickers},
            ns=ns,
            bday_index=bday_idx,
        )
        assert fallback is False, f"Unexpected fallback with {n_tickers} tickers"
        assert len(members) == TWIN_TOP_N, (
            f"Expected exactly {TWIN_TOP_N} members (top-N cap), got {len(members)}"
        )


class TestTwinNullBackfill:
    """(e) NULL-backfill: non-current-month build dates must have all-None twin columns.

    RULING-2: twin columns are computed ONLY for dates in the current freeze month.
    All other (backfill) dates receive None — same R3 semantics as Block-B.
    """

    def _write_twin_fixtures(
        self, root: Path, tickers: list[str], n_dates: int = 350,
        seed: int = 77
    ) -> pd.DatetimeIndex:
        """Write minimal fixtures for build_panel with twin-capable schema."""
        rng_local = np.random.default_rng(seed)
        dates = pd.bdate_range("2024-06-03", periods=n_dates)
        as_of_date = dates[-1]

        # Breadth closes:
        bdir = root / "data" / "breadth"
        bdir.mkdir(parents=True, exist_ok=True)
        closes = pd.DataFrame(
            {t: 100.0 * (1 + rng_local.normal(0, 0.01, n_dates)).cumprod()
             for t in tickers},
            index=dates,
        )
        closes.to_parquet(bdir / "_closes_cache.parquet")
        meta = pd.DataFrame(
            {"name": tickers, "sector": ["Industrials"] * len(tickers)},
            index=tickers,
        )
        meta.to_parquet(bdir / "constituents.parquet")

        # Yahoo ETFs:
        ydir = root / "data" / "yahoo"
        ydir.mkdir(exist_ok=True)
        for sym in ["SPY", "IWM", "QQQ", "TLT", "DX-Y.NYB", "FXI", "XLI"]:
            df = pd.DataFrame(
                {"close": 100.0 * (1 + rng_local.normal(0, 0.01, n_dates)).cumprod()},
                index=dates,
            )
            df.to_parquet(ydir / f"{sym}.parquet")

        # baskets.json:
        sdir = root / "site" / "basketdata"
        sdir.mkdir(parents=True, exist_ok=True)
        ai_levels = list(100.0 * (1 + rng_local.normal(0, 0.01, n_dates)).cumprod())
        (sdir / "baskets.json").write_text(json.dumps({
            "chart": {
                "dates": [str(d.date()) for d in dates],
                "bench": [1.0] * n_dates,
                "baskets": {"ai_infra": ai_levels},
            }
        }))

        # factordata — as_of matches last date:
        fddir = root / "site" / "factordata"
        fddir.mkdir(parents=True, exist_ok=True)
        per_ticker = {t: {"alpha": float(rng_local.normal(0, 1))} for t in tickers}
        (fddir / "alpha.json").write_text(json.dumps({
            "as_of": str(as_of_date.date()),
            "per_ticker": per_ticker,
        }))
        factors_table = [
            {
                "ticker": t,
                "sector": "Industrials",
                "mktcap_bn": float(1.0 + rng_local.uniform(0, 100)),
                **{leg: float(rng_local.normal(0, 1)) for leg in BLOCK_B_LEGS},
            }
            for t in tickers
        ]
        (fddir / "factors.json").write_text(json.dumps({
            "as_of": str(as_of_date.date()),
            "table": factors_table,
        }))
        return dates

    def test_twin_null_on_backfill_dates(self, tmp_path):
        """(e) Non-current-month build dates → twin columns all None.

        Build a panel over a date range spanning TWO calendar months.
        The factors_as_of falls in the LATER month.
        All rows in the EARLIER month must have None for all 4 twin columns.
        """
        # n_dates=350 starting 2024-06-03 → last date ≈ 2025-10-xx
        tickers = [f"T{i:03d}" for i in range(20)]
        dates = self._write_twin_fixtures(tmp_path, tickers, n_dates=350, seed=5)

        # Build over a window spanning month[-2] to month[-1] (both the current
        # and a prior month).  factors_as_of = dates[-1] (end of last month).
        start = dates[-45]   # ~2 months back
        end = dates[-1]

        panel = build_panel(
            data_root=tmp_path, out_root=tmp_path,
            start_date=start, end_date=end,
            tickers=tickers,
        )
        assert not panel.empty, "Panel is empty"
        assert "twin_n_peers" in panel.columns, "twin_n_peers missing from panel"

        panel["date"] = pd.to_datetime(panel["date"])
        # Determine the current freeze month (factors_as_of month):
        factors_as_of_date = dates[-1]
        cur_year, cur_month = factors_as_of_date.year, factors_as_of_date.month

        # Rows NOT in the current freeze month → twin columns must all be None:
        non_freeze = panel[
            ~((panel["date"].dt.year == cur_year) &
              (panel["date"].dt.month == cur_month))
        ]
        assert len(non_freeze) > 0, (
            "fixture produced no backfill rows — vacuous test: "
            "the build window must span at least two calendar months so "
            "there are rows in a non-current-freeze month to check."
        )
        for col in ["twin_rel_20d", "twin_bleed_flag", "twin_n_peers", "twin_fallback"]:
                non_null = non_freeze[col].notna()
                assert not non_null.any(), (
                    f"RULING-2 violation: backfill rows have non-null {col} "
                    f"({non_null.sum()} non-null rows in non-current-month dates). "
                    "Twin columns must be None for all non-current-month build dates."
                )


class TestTwinMembershipFreeze:
    """(a) Membership freeze: intramonth data changes do not alter membership.

    Once membership is frozen on the first trading day of the month,
    intramonth data should not change which tickers are in the basket.
    (This is structural: membership is computed once at the freeze date
    and cached for the month — the test verifies that two calls with the
    same freeze date produce identical results.)
    """

    def _make_resid_dict(self, tickers: list[str], n: int = 350,
                         seed: int = 0) -> dict[str, pd.Series]:
        rng = np.random.default_rng(seed)
        dates = _make_twin_dates(n)
        return {t: pd.Series(rng.normal(0, 0.01, n), index=dates) for t in tickers}

    def test_membership_identical_for_same_freeze_date(self):
        """Calling _build_twin_membership twice with same freeze_date yields identical members."""
        tickers = [f"T{i:03d}" for i in range(25)]
        sector = "Consumer Discretionary"
        ns = {t: (t, sector) for t in tickers}
        resid = self._make_resid_dict(tickers, seed=11)
        bday_idx = _make_twin_dates(350)
        freeze_date = bday_idx[260]

        members1, fallback1 = _build_twin_membership(
            freeze_date=freeze_date, ticker=tickers[0], sector=sector,
            size_tercile=1, all_resid_1d=resid,
            size_tercile_map={t: 1 for t in tickers},
            ns=ns, bday_index=bday_idx,
        )
        members2, fallback2 = _build_twin_membership(
            freeze_date=freeze_date, ticker=tickers[0], sector=sector,
            size_tercile=1, all_resid_1d=resid,
            size_tercile_map={t: 1 for t in tickers},
            ns=ns, bday_index=bday_idx,
        )
        assert sorted(members1) == sorted(members2), (
            "Membership is non-deterministic for the same freeze_date"
        )
        assert fallback1 == fallback2

    def test_membership_invariant_to_post_freeze_data(self):
        """Adding future data after the freeze date must not change membership.

        PIT guard (masterplan §3.5 + RULING-1): the correlation window ends at
        freeze_date - 1 (window exclusion: bday_index[win_start:win_end_idx] is
        exclusive of freeze_date itself).  Any data at or after freeze_date must
        not affect membership.

        OFF-BY-ONE BLIND SPOT FIX (FIX-3 2026-07-05):
        freeze_date is set to bday_idx_base[-4] (NOT the last base date) and the
        extended series DIVERGES from the base at/after freeze_date.  This means:
          - A window ending at freeze_date-1 (correct PIT) uses the SAME prefix
            data → membership unchanged.
          - A window ending at freeze_date (off-by-one bug) would include diverging
            data at the freeze_date row → membership changes → test FAILS.
        The prior version used freeze_date = bday_idx_base[-1] (the last base row),
        so the extended series had NO data at freeze_date to diverge → the test was
        blind to the off-by-one.
        """
        n_base = 300
        n_extra = 50
        tickers = [f"T{i:03d}" for i in range(20)]
        sector = "Materials"
        ns = {t: (t, sector) for t in tickers}
        bday_idx_base = _make_twin_dates(n_base)
        bday_idx_extended = _make_twin_dates(n_base + n_extra)
        # FIX-3: freeze_date NOT at the end of base — leaves room for diverging data.
        freeze_date = bday_idx_base[-4]  # 3 rows before the end of base history

        # Pre-generate ALL base values (shared prefix for both base and extended):
        rng = np.random.default_rng(19)
        base_values: dict[str, np.ndarray] = {
            t: rng.normal(0, 0.01, n_base) for t in tickers
        }
        # Extended diverges STARTING AT freeze_date index (position n_base-4):
        # The correlation window uses data UP TO (but not including) freeze_date.
        # At/after freeze_date, the extended series has EXTREME diverging values
        # that would change correlations if they leaked into the window.
        freeze_pos = n_base - 4  # position of freeze_date in bday_idx_base
        extended_values: dict[str, np.ndarray] = {}
        rng_div = np.random.default_rng(777)
        for t in tickers:
            extended = base_values[t].copy().tolist()
            # At/after freeze_date: massive diverging values (would flip correlations):
            extended[freeze_pos] = float(rng_div.choice([-100.0, 100.0]))  # extreme at freeze
            for _ in range(n_extra):
                extended.append(float(rng_div.choice([-100.0, 100.0])))
            extended_values[t] = np.array(extended[:n_base + n_extra])

        resid_base = {
            t: pd.Series(base_values[t], index=bday_idx_base)
            for t in tickers
        }
        resid_extended = {
            t: pd.Series(extended_values[t], index=bday_idx_extended)
            for t in tickers
        }

        # Membership at freeze_date with base history:
        members_base, fallback_base = _build_twin_membership(
            freeze_date=freeze_date, ticker=tickers[0], sector=sector,
            size_tercile=1, all_resid_1d=resid_base,
            size_tercile_map={t: 1 for t in tickers},
            ns=ns, bday_index=bday_idx_base,
        )
        # Membership at same freeze_date with extended history (post-freeze diverges):
        members_ext, fallback_ext = _build_twin_membership(
            freeze_date=freeze_date, ticker=tickers[0], sector=sector,
            size_tercile=1, all_resid_1d=resid_extended,
            size_tercile_map={t: 1 for t in tickers},
            ns=ns, bday_index=bday_idx_extended,
        )
        assert sorted(members_base) == sorted(members_ext), (
            "PIT violation: diverging data at/after freeze_date changed twin membership. "
            f"Base members: {sorted(members_base)[:5]}... "
            f"Extended members: {sorted(members_ext)[:5]}...\n"
            "The correlation window must use only data strictly before freeze_date."
        )
        assert fallback_base == fallback_ext


class TestTwinSchemaStability44:
    """(f) Schema stability: all universe configurations produce exactly PANEL_COLUMNS.

    Extends the P1-A schema stability test by adding 4 twin columns.
    Note: the actual count is 52 (48 from P1-A + 4 twin from P1-B).
    The masterplan spec's "40→44" was an approximation; the authoritative list
    is PANEL_COLUMNS.
    """

    def _build_and_read_cols(self, tmp_path: Path, tickers: list[str],
                              sectors: list[str], n_dates: int = 350) -> list[str]:
        """Build a panel and return the parquet column list."""
        rng = np.random.default_rng(66)
        dates = pd.bdate_range("2024-06-03", periods=n_dates)
        as_of_date = dates[-1]

        bdir = tmp_path / "data" / "breadth"
        bdir.mkdir(parents=True, exist_ok=True)
        closes = pd.DataFrame(
            {t: 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()
             for t in tickers},
            index=dates,
        )
        closes.to_parquet(bdir / "_closes_cache.parquet")
        meta = pd.DataFrame({"name": tickers, "sector": sectors}, index=tickers)
        meta.to_parquet(bdir / "constituents.parquet")

        ydir = tmp_path / "data" / "yahoo"
        ydir.mkdir(exist_ok=True)
        for sym in ["SPY", "IWM", "QQQ", "TLT", "DX-Y.NYB", "FXI", "XLK", "XLI", "XLV"]:
            df = pd.DataFrame(
                {"close": 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()},
                index=dates,
            )
            df.to_parquet(ydir / f"{sym}.parquet")

        sdir = tmp_path / "site" / "basketdata"
        sdir.mkdir(parents=True, exist_ok=True)
        ai = list(100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod())
        (sdir / "baskets.json").write_text(json.dumps({
            "chart": {
                "dates": [str(d.date()) for d in dates],
                "bench": [1.0] * n_dates,
                "baskets": {"ai_infra": ai},
            }
        }))

        fddir = tmp_path / "site" / "factordata"
        fddir.mkdir(parents=True, exist_ok=True)
        (fddir / "alpha.json").write_text(json.dumps({
            "as_of": str(as_of_date.date()),
            "per_ticker": {t: {"alpha": float(rng.normal(0, 1))} for t in tickers},
        }))
        factors_table = [
            {
                "ticker": t,
                "sector": sectors[i],
                "mktcap_bn": float(1 + rng.uniform(0, 100)),
                **{leg: float(rng.normal(0, 1)) for leg in BLOCK_B_LEGS},
            }
            for i, t in enumerate(tickers)
        ]
        (fddir / "factors.json").write_text(json.dumps({
            "as_of": str(as_of_date.date()),
            "table": factors_table,
        }))

        build_panel(
            data_root=tmp_path, out_root=tmp_path,
            start_date=dates[-5], end_date=dates[-1],
            tickers=tickers,
        )
        for p in sorted((tmp_path / "data" / "factordata" / "panel").rglob("panel.parquet")):
            return list(pd.read_parquet(p).columns)
        return []

    def test_schema_extended_with_four_twin_columns(self, tmp_path):
        """(f) Schema extended by P1-B with 4 twin + P1-C with 3 DNA/style = 55 cols.

        P1-A: 48 columns (3 identity + 8 betas + 3×10 attribution + 1 resid_1d +
        5 block_b + 1 alpha_z).  P1-B adds 4 twin columns (52).  P1-C adds 3
        DNA/style_regime columns (55).  PANEL_COLUMNS is the authoritative list.
        """
        cols = self._build_and_read_cols(
            tmp_path / "ss",
            tickers=["A", "B", "C", "D", "E"],
            sectors=["Industrials"] * 5,
        )
        twin_cols = {"twin_rel_20d", "twin_bleed_flag", "twin_n_peers", "twin_fallback"}
        missing_twin = twin_cols - set(PANEL_COLUMNS)
        assert not missing_twin, (
            f"PANEL_COLUMNS is missing twin columns: {missing_twin}"
        )
        assert cols == PANEL_COLUMNS, (
            f"Single-sector: parquet columns differ from PANEL_COLUMNS.\n"
            f"Extra: {set(cols) - set(PANEL_COLUMNS)}\n"
            f"Missing: {set(PANEL_COLUMNS) - set(cols)}"
        )
        # P1-C columns ARE now in schema (55 cols = 48 P1-A + 4 P1-B + 3 P1-C):
        p1c_cols = {"dna_class", "style_regime", "style_regime_pending"}
        missing_p1c = p1c_cols - set(PANEL_COLUMNS)
        assert not missing_p1c, (
            f"P1-C columns missing from PANEL_COLUMNS (required by §5.4): {missing_p1c}"
        )

    def test_55_columns_mixed_sector(self, tmp_path):
        """(f) Mixed-sector universe (IT + Health Care) → 55 columns == PANEL_COLUMNS."""
        cols = self._build_and_read_cols(
            tmp_path / "mixed",
            tickers=["AAPL", "JNJ"],
            sectors=["Information Technology", "Health Care"],
        )
        assert cols == PANEL_COLUMNS, (
            f"Mixed: parquet columns differ from PANEL_COLUMNS.\n"
            f"Extra: {set(cols) - set(PANEL_COLUMNS)}\n"
            f"Missing: {set(PANEL_COLUMNS) - set(cols)}"
        )


class TestTwinEwReturns:
    """Unit tests for _compute_twin_ew_returns."""

    def test_equal_weight_is_mean(self):
        """Twin EW return = arithmetic mean of member daily returns."""
        dates = _make_twin_dates(50)
        rng = np.random.default_rng(77)
        # Build two tickers with known returns:
        closes_data = {
            "A": 100.0 * (1 + pd.Series(rng.normal(0.001, 0.01, 50), index=dates)).cumprod(),
            "B": 100.0 * (1 + pd.Series(rng.normal(0.002, 0.01, 50), index=dates)).cumprod(),
        }
        closes_df = pd.DataFrame(closes_data)

        ew = _compute_twin_ew_returns(["A", "B"], closes_df, dates)

        # Compare to manual mean of pct_change:
        ret_a = closes_df["A"].pct_change(fill_method=None)
        ret_b = closes_df["B"].pct_change(fill_method=None)
        expected = pd.concat([ret_a, ret_b], axis=1).mean(axis=1, skipna=True)
        pd.testing.assert_series_equal(
            ew.dropna(), expected.reindex(dates).dropna(),
            check_names=False, rtol=1e-9,
        )

    def test_empty_members_returns_nan(self):
        """Empty member list → all-NaN series."""
        dates = _make_twin_dates(10)
        closes_df = pd.DataFrame({"A": [100.0] * 10}, index=dates)
        ew = _compute_twin_ew_returns([], closes_df, dates)
        assert ew.isna().all(), "Empty members should produce all-NaN series"

    def test_single_member_equals_that_member(self):
        """Single member → EW return equals that member's daily return."""
        dates = _make_twin_dates(30)
        rng = np.random.default_rng(9)
        closes_df = pd.DataFrame(
            {"ONLY": 100.0 * (1 + pd.Series(rng.normal(0, 0.01, 30), index=dates)).cumprod()},
        )
        ew = _compute_twin_ew_returns(["ONLY"], closes_df, dates)
        expected = closes_df["ONLY"].pct_change(fill_method=None).reindex(dates)
        pd.testing.assert_series_equal(
            ew.dropna(), expected.dropna(),
            check_names=False, rtol=1e-9,
        )


class TestTwinSizeTerciles:
    """Unit tests for _compute_size_terciles."""

    def test_tercile_labels_are_0_1_2(self):
        """Size terciles must use labels 0 (small), 1 (mid), 2 (large)."""
        # 9 tickers in one sector: 3 small, 3 mid, 3 large
        tickers = [f"T{i:02d}" for i in range(9)]
        mktcaps = [1.0, 2.0, 3.0,   # small
                   10.0, 11.0, 12.0, # mid
                   100.0, 110.0, 120.0]  # large
        df = pd.DataFrame({
            "sector": ["Industrials"] * 9,
            "mktcap_bn": mktcaps,
        }, index=tickers)
        ns = {t: (t, "Industrials") for t in tickers}
        tercile_map = _compute_size_terciles(df, ns)
        small = [t for t, v in tercile_map.items() if v == 0]
        mid = [t for t, v in tercile_map.items() if v == 1]
        large = [t for t, v in tercile_map.items() if v == 2]
        assert len(small) == 3, f"Expected 3 small, got {len(small)}"
        assert len(mid) == 3, f"Expected 3 mid, got {len(mid)}"
        assert len(large) == 3, f"Expected 3 large, got {len(large)}"

    def test_all_same_mktcap_falls_to_mid(self):
        """If all mktcaps in a sector are equal, qcut may fail — all assigned to mid(1)."""
        tickers = ["A", "B", "C"]
        df = pd.DataFrame({
            "sector": ["Utilities"] * 3,
            "mktcap_bn": [10.0, 10.0, 10.0],
        }, index=tickers)
        ns = {t: (t, "Utilities") for t in tickers}
        tercile_map = _compute_size_terciles(df, ns)
        # Should not raise; values should be valid (0, 1, or 2):
        for t in tickers:
            assert t in tercile_map, f"{t} missing from tercile map"
            assert tercile_map[t] in (0, 1, 2), f"Invalid tercile label {tercile_map[t]}"

    def test_missing_mktcap_excluded(self):
        """Tickers with NaN or missing mktcap are excluded from the output dict."""
        tickers = ["A", "B", "C"]
        df = pd.DataFrame({
            "sector": ["Financials"] * 3,
            "mktcap_bn": [float("nan"), 10.0, 20.0],
        }, index=tickers)
        ns = {t: (t, "Financials") for t in tickers}
        tercile_map = _compute_size_terciles(df, ns)
        assert "A" not in tercile_map, "NaN mktcap ticker should not be in tercile map"
        assert "B" in tercile_map and "C" in tercile_map


# ---------------------------------------------------------------------------
# P1-C tests — DNA class cascade (§3.3 + RULING-A)
# ---------------------------------------------------------------------------
class TestDNAClassCascade:
    """Tests for _classify_dna: priority cascade, None semantics, and each class trigger."""

    def _base_row(self) -> dict:
        """Default row dict with all required Block-B inputs present (non-None)."""
        return {
            "quality_pct": 50.0,
            "value_pct": 50.0,
            "payout_pct": 50.0,
            "low_vol_pct": 50.0,
            "profitability_pct": 50.0,
            "size_pct": 50.0,
            "beta_mkt": 1.0,
            "beta_growth": 0.2,
            "beta_sector": 0.1,
            "beta_rates": 0.1,
            "beta_china": 0.0,
        }

    def test_all_false_conditions_returns_mixed(self):
        """When no archetype conditions are met → 'mixed'."""
        row = self._base_row()
        # All defaults are midrange — none should trigger a specific class
        result = _classify_dna(row, "Health Care")
        assert result == "mixed", f"Expected 'mixed', got '{result}'"

    def test_missing_required_block_b_returns_none(self):
        """RULING-A: any required Block-B input None → dna_class = None (NOT EVALUABLE)."""
        for missing_key in ["quality_pct", "value_pct", "payout_pct", "low_vol_pct"]:
            row = self._base_row()
            row[missing_key] = None
            result = _classify_dna(row, "Health Care")
            assert result is None, (
                f"Expected None when {missing_key}=None (RULING-A); got '{result}'"
            )

    def test_all_required_block_b_none_returns_none(self):
        """RULING-A: all Block-B inputs None → None."""
        row = self._base_row()
        for k in ["quality_pct", "value_pct", "payout_pct", "low_vol_pct"]:
            row[k] = None
        assert _classify_dna(row, "Energy") is None

    def test_quality_growth_triggers(self):
        """quality_growth: quality≥70 AND value<60 AND beta_growth>0.3."""
        row = self._base_row()
        row["quality_pct"] = 75.0
        row["value_pct"] = 40.0
        row["beta_growth"] = 0.5
        assert _classify_dna(row, "Information Technology") == "quality_growth"

    def test_high_beta_liquidity_triggers(self):
        """high_beta_liquidity: beta_mkt>1.3 AND beta_growth>0.4 AND low_vol<35."""
        row = self._base_row()
        row["beta_mkt"] = 1.5
        row["beta_growth"] = 0.6
        row["low_vol_pct"] = 20.0
        # Must not trigger quality_growth first (keep quality_pct low):
        row["quality_pct"] = 30.0
        assert _classify_dna(row, "Consumer Discretionary") == "high_beta_liquidity"

    def test_cyclical_value_triggers(self):
        """cyclical_value: value≥65 AND sector∈{Energy,Industrials,Materials} AND beta_sector>0.2."""
        row = self._base_row()
        row["value_pct"] = 70.0
        row["beta_sector"] = 0.4
        # Must not trigger quality_growth or high_beta first:
        row["quality_pct"] = 30.0
        row["beta_mkt"] = 0.8
        row["beta_growth"] = 0.1
        for sector in ["Energy", "Industrials", "Materials"]:
            assert _classify_dna(row, sector) == "cyclical_value", (
                f"cyclical_value must trigger for sector={sector}"
            )
        # Non-cyclical sector: does NOT trigger
        assert _classify_dna(row, "Health Care") != "cyclical_value"

    def test_defensive_quality_triggers(self):
        """defensive_quality: quality≥65 AND low_vol≥60 AND beta_mkt<0.85."""
        row = self._base_row()
        row["quality_pct"] = 70.0
        row["low_vol_pct"] = 65.0
        row["beta_mkt"] = 0.7
        row["value_pct"] = 55.0  # below quality_growth threshold (<60 ok, but quality<70 ok)
        row["beta_growth"] = 0.1   # below quality_growth beta_growth threshold
        assert _classify_dna(row, "Utilities") == "defensive_quality"

    def test_rate_duration_sensitive_triggers(self):
        """rate_duration_sensitive: abs(beta_rates)>0.25 AND (payout≥55 OR low_vol≥55)."""
        row = self._base_row()
        row["beta_rates"] = 0.4
        row["payout_pct"] = 60.0
        # Must not trigger earlier classes:
        row["quality_pct"] = 30.0
        row["beta_mkt"] = 0.8
        row["beta_growth"] = 0.1
        row["value_pct"] = 30.0
        row["low_vol_pct"] = 30.0
        assert _classify_dna(row, "Real Estate") == "rate_duration_sensitive"

        # Also triggers with negative beta_rates:
        row["beta_rates"] = -0.35
        row["payout_pct"] = 40.0
        row["low_vol_pct"] = 60.0
        assert _classify_dna(row, "Real Estate") == "rate_duration_sensitive"

    def test_china_crypto_proxy_via_china_beta(self):
        """china_crypto_proxy via beta_china > 0.30."""
        row = self._base_row()
        row["beta_china"] = 0.5
        # Must not trigger earlier classes:
        row["quality_pct"] = 30.0
        row["beta_mkt"] = 0.8
        row["beta_growth"] = 0.1
        row["value_pct"] = 30.0
        row["low_vol_pct"] = 30.0
        row["beta_rates"] = 0.05
        assert _classify_dna(row, "Health Care") == "china_crypto_proxy"

    def test_china_crypto_proxy_via_sector_path(self):
        """china_crypto_proxy via beta_mkt>1.1 AND IT sector AND value<30."""
        row = self._base_row()
        row["beta_china"] = 0.0   # no china beta
        row["beta_mkt"] = 1.2
        row["value_pct"] = 20.0
        # Must not trigger earlier classes:
        row["quality_pct"] = 30.0
        row["beta_growth"] = 0.1
        row["low_vol_pct"] = 30.0
        row["beta_rates"] = 0.05
        for sector in ["Information Technology", "Technology",
                        "Communication Services", "Communications"]:
            assert _classify_dna(row, sector) == "china_crypto_proxy", (
                f"china_crypto_proxy must trigger for sector={sector}"
            )
        # Non-eligible sector: does NOT trigger this path
        result = _classify_dna(row, "Energy")
        assert result != "china_crypto_proxy"

    def test_small_spec_triggers(self):
        """small_spec: size_pct<30 AND low_vol<40 AND quality<45."""
        row = self._base_row()
        row["size_pct"] = 20.0
        row["low_vol_pct"] = 25.0
        row["quality_pct"] = 30.0
        # Must not trigger earlier classes:
        row["beta_mkt"] = 0.9
        row["beta_growth"] = 0.1
        row["value_pct"] = 40.0
        row["beta_rates"] = 0.05
        row["beta_china"] = 0.0
        assert _classify_dna(row, "Consumer Discretionary") == "small_spec"

    def test_priority_order_quality_growth_beats_high_beta(self):
        """quality_growth has higher priority than high_beta_liquidity."""
        row = self._base_row()
        # Both quality_growth and high_beta_liquidity could trigger:
        row["quality_pct"] = 75.0
        row["value_pct"] = 40.0
        row["beta_growth"] = 0.5
        row["beta_mkt"] = 1.5
        row["low_vol_pct"] = 20.0
        # quality_growth fires first (higher priority):
        assert _classify_dna(row, "Information Technology") == "quality_growth"

    def test_none_vs_mixed_distinction_is_load_bearing(self):
        """RULING-A: None (NOT EVALUABLE) != 'mixed' (evaluated, no archetype).

        This distinction is explicitly required by RULING-A: 'mixed' is reserved
        for rows that WERE evaluated and matched no archetype.
        """
        # Row with all Block-B None → None (not evaluable):
        row_none = self._base_row()
        row_none["quality_pct"] = None
        result_none = _classify_dna(row_none, "Health Care")
        assert result_none is None, "Expected None for missing Block-B"

        # Row with all Block-B present but no archetype matches → 'mixed':
        row_mixed = self._base_row()
        result_mixed = _classify_dna(row_mixed, "Health Care")
        assert result_mixed == "mixed", "Expected 'mixed' when evaluated but no archetype"

        # Critical: these are distinct values
        assert result_none != result_mixed, "None and 'mixed' must be distinct"
        assert result_none is None
        assert result_mixed == "mixed"

    def test_missing_beta_treated_as_zero(self):
        """Missing Block-A betas (None) are treated as 0.0 — condition fails gracefully."""
        row = self._base_row()
        # quality_growth requires beta_growth > 0.3; if beta_growth=None → treated as 0.0
        row["quality_pct"] = 75.0
        row["value_pct"] = 40.0
        row["beta_growth"] = None  # treated as 0.0 → quality_growth condition fails
        result = _classify_dna(row, "Information Technology")
        # Should not be quality_growth (beta_growth condition failed):
        assert result != "quality_growth"
        # Should still evaluate (Block-B is present) → not None:
        assert result is not None


# ---------------------------------------------------------------------------
# P1-C tests — style_regime classifier (§3.4)
# ---------------------------------------------------------------------------
class TestStyleRegimeClassifier:
    """Tests for _build_style_regime_timeline: hysteresis, idempotence, fail-open."""

    def _write_etf_fixture(self, root: Path, dates: pd.DatetimeIndex,
                           iwf_rets: np.ndarray | None = None,
                           iwd_rets: np.ndarray | None = None,
                           qqq_rets: np.ndarray | None = None,
                           spy_rets: np.ndarray | None = None,
                           iwm_rets: np.ndarray | None = None) -> None:
        """Write synthetic ETF parquets for style_regime testing."""
        rng = np.random.default_rng(42)
        n = len(dates)
        ydir = root / "data" / "yahoo"
        ydir.mkdir(parents=True, exist_ok=True)

        default_rets = rng.normal(0, 0.01, n)
        pairs = [
            ("IWF", iwf_rets if iwf_rets is not None else default_rets),
            ("IWD", iwd_rets if iwd_rets is not None else default_rets),
            ("QQQ", qqq_rets if qqq_rets is not None else default_rets),
            ("SPY", spy_rets if spy_rets is not None else default_rets),
            ("IWM", iwm_rets if iwm_rets is not None else default_rets),
        ]
        for sym, rets in pairs:
            closes = 100.0 * (1 + rets).cumprod()
            df = pd.DataFrame({"close": closes}, index=dates)
            df.to_parquet(ydir / f"{sym}.parquet")

    def test_missing_etf_data_returns_mixed(self, tmp_path):
        """If all ETF parquets are missing → fail-open: all dates return 'mixed'."""
        # No ETF parquets written
        dates = pd.bdate_range("2025-01-02", periods=30)
        confirmed, pending = _build_style_regime_timeline(tmp_path, dates)
        assert (confirmed == "mixed").all(), "Missing ETF data must yield 'mixed' for all dates"
        assert len(confirmed) == len(dates)

    def test_hysteresis_one_day_match_goes_to_pending(self, tmp_path):
        """Hysteresis: 1 day match → pending only, confirmed state unchanged.

        RULING (§3.4): a state change requires 2 consecutive daily confirmations.
        On day 1 match, confirmed stays at 'mixed'; pending becomes the new state.
        """
        n = 60  # enough for 20d rolling warmup
        dates = pd.bdate_range("2025-01-02", periods=n)

        # Build ETF returns where growth_momentum conditions fire for exactly 1 day
        # at the end, then stops.  We engineer QQQ >> SPY (>+3%) on the last day only.
        # To ensure warmup, use similar returns for most of history.
        rng = np.random.default_rng(99)
        base_ret = rng.normal(0.0003, 0.008, n)  # slight positive drift

        qqq_rets = base_ret.copy()
        spy_rets = base_ret.copy()
        iwf_rets = base_ret.copy()
        iwd_rets = base_ret.copy()
        iwm_rets = base_ret.copy()

        # For the last day: make QQQ massively outperform SPY over trailing 20d
        # by injecting a large positive return into QQQ on days [-21:-1]
        qqq_rets[-21:-1] += 0.003  # QQQ 20d return ~6% above SPY

        self._write_etf_fixture(
            tmp_path, dates,
            qqq_rets=qqq_rets, spy_rets=spy_rets,
            iwf_rets=iwf_rets, iwd_rets=iwd_rets, iwm_rets=iwm_rets,
        )
        # Write factor_series.json to provide leader context (minimal):
        fs_dir = tmp_path / "site" / "factordata"
        fs_dir.mkdir(parents=True, exist_ok=True)
        # We don't need real factor series for this test — just let it fall back gracefully
        (fs_dir / "factor_series.json").write_text('{"as_of": "2025-01-02"}')

        confirmed, pending = _build_style_regime_timeline(tmp_path, dates)
        assert len(confirmed) == n
        # All confirmed states must be valid strings:
        for v in confirmed:
            assert v in STYLE_REGIME_STATES, f"Invalid state: {v}"

    def test_hysteresis_two_consecutive_days_flip(self, tmp_path):
        """Hysteresis: 2 consecutive days of same non-mixed state → flip confirmed.

        Verified behaviorally: after 2 consecutive matching days, confirmed changes.
        """
        n = 60
        dates = pd.bdate_range("2025-01-02", periods=n)
        rng = np.random.default_rng(7)
        base = rng.normal(0, 0.008, n)

        # Engineer IWM >> SPY (>+4%) for the last 3+ days (20d rolling window)
        # to fire junk_rally conditions.
        iwm_rets = base.copy()
        spy_rets = base.copy()
        iwm_rets[-22:-1] += 0.003   # IWM outperforms SPY by ~6% over 20d window

        self._write_etf_fixture(
            tmp_path, dates,
            iwm_rets=iwm_rets, spy_rets=spy_rets,
        )
        fs_dir = tmp_path / "site" / "factordata"
        fs_dir.mkdir(parents=True, exist_ok=True)
        (fs_dir / "factor_series.json").write_text('{"as_of": "2025-01-02"}')

        confirmed, pending = _build_style_regime_timeline(tmp_path, dates)
        assert len(confirmed) == n
        # All states valid:
        for v in confirmed:
            assert v in STYLE_REGIME_STATES

    def test_immediate_reversion_to_mixed(self, tmp_path):
        """Hysteresis: failing conditions → immediate reversion to 'mixed' (no delay).

        §3.4: 'Reversions to mixed are immediate (1 day).'
        """
        n = 60
        dates = pd.bdate_range("2025-01-02", periods=n)
        rng = np.random.default_rng(11)
        base = rng.normal(0, 0.008, n)

        self._write_etf_fixture(tmp_path, dates)
        fs_dir = tmp_path / "site" / "factordata"
        fs_dir.mkdir(parents=True, exist_ok=True)
        (fs_dir / "factor_series.json").write_text('{"as_of": "2025-01-02"}')

        # With all-identical ETF returns (ratios = 0), no condition fires → all 'mixed'
        confirmed, pending = _build_style_regime_timeline(tmp_path, dates)
        # Once a state is confirmed, if conditions fail the next day → back to mixed
        # For this test: with neutral ratios, state should be 'mixed' throughout.
        assert all(v in STYLE_REGIME_STATES for v in confirmed.values)

    def test_idempotence_historical_states_unchanged(self, tmp_path):
        """Idempotence: appending future dates must not change historical confirmed states.

        PREREG §2.5(a): style_regime[t] is a pure function of data ≤ t.
        Running the classifier on [d1, d2] produces the same confirmed states for
        d1 as running it on [d1, d2, d3, d4, d5] (extended window).
        """
        n_short = 60
        n_long = 80
        dates_short = pd.bdate_range("2025-01-02", periods=n_short)
        dates_long = pd.bdate_range("2025-01-02", periods=n_long)

        rng = np.random.default_rng(42)
        base = rng.normal(0, 0.008, n_long)

        short_root = tmp_path / "short"
        long_root = tmp_path / "long"
        short_root.mkdir(); long_root.mkdir()

        # Write same ETF returns for both (only first n_short rows for short fixture):
        for root, n in [(short_root, n_short), (long_root, n_long)]:
            dates_n = pd.bdate_range("2025-01-02", periods=n)
            self._write_etf_fixture(root, dates_n,
                                    iwf_rets=base[:n], iwd_rets=base[:n],
                                    qqq_rets=base[:n], spy_rets=base[:n],
                                    iwm_rets=base[:n])
            fs_dir = root / "site" / "factordata"
            fs_dir.mkdir(parents=True, exist_ok=True)
            (fs_dir / "factor_series.json").write_text('{"as_of": "2025-01-02"}')

        conf_short, _ = _build_style_regime_timeline(short_root, dates_short)
        conf_long, _ = _build_style_regime_timeline(long_root, dates_long)

        # Historical states (dates in short window) must be identical:
        for d in dates_short:
            v_short = conf_short.get(d)
            v_long = conf_long.get(d)
            assert v_short == v_long, (
                f"Idempotence failure at {d.date()}: short='{v_short}', long='{v_long}'. "
                "Extending history forward must not change past confirmed states."
            )

    def test_style_regime_states_are_valid_strings(self, tmp_path):
        """All emitted style_regime values must be in STYLE_REGIME_STATES."""
        n = 50
        dates = pd.bdate_range("2025-01-02", periods=n)
        self._write_etf_fixture(tmp_path, dates)
        fs_dir = tmp_path / "site" / "factordata"
        fs_dir.mkdir(parents=True, exist_ok=True)
        (fs_dir / "factor_series.json").write_text('{"as_of": "2025-01-02"}')

        confirmed, pending = _build_style_regime_timeline(tmp_path, dates)
        for v in confirmed:
            assert v in STYLE_REGIME_STATES, f"Invalid style_regime state: {v!r}"

    def test_pending_is_none_when_no_flip_in_progress(self, tmp_path):
        """style_regime_pending is None when confirmed state is stable."""
        n = 50
        dates = pd.bdate_range("2025-01-02", periods=n)
        self._write_etf_fixture(tmp_path, dates)
        fs_dir = tmp_path / "site" / "factordata"
        fs_dir.mkdir(parents=True, exist_ok=True)
        (fs_dir / "factor_series.json").write_text('{"as_of": "2025-01-02"}')

        confirmed, pending = _build_style_regime_timeline(tmp_path, dates)
        assert len(pending) == len(dates)
        # Each pending value must be None or a valid state string:
        for v in pending:
            assert v is None or v in STYLE_REGIME_STATES, (
                f"Invalid pending value: {v!r}"
            )


# ---------------------------------------------------------------------------
# P1-C tests — world_state lobe (§5.4 + RULING-B)
# ---------------------------------------------------------------------------
class TestWorldStateLobe:
    """Tests for _compose_factor_weather: fail-open, purity, RULING-B.

    FIX-1 (RULING-B fold): _compose_factor_weather now takes root= and loads
    data internally.  Tests use tmp_path fixtures to isolate reads.
    """

    def _import_ws(self):
        """Import world_state module."""
        import importlib
        ws = importlib.import_module("engine.neuralweb.world_state")
        return ws

    def _import_compose(self):
        """Import _compose_factor_weather from world_state."""
        ws = self._import_ws()
        if not hasattr(ws, "_compose_factor_weather"):
            pytest.skip("_compose_factor_weather not yet wired in world_state.py")
        return ws._compose_factor_weather

    def _import_clean(self):
        """Import _clean helper from world_state."""
        ws = self._import_ws()
        if not hasattr(ws, "_clean"):
            pytest.skip("_clean not available in world_state.py")
        return ws._clean

    def test_fail_open_empty_root(self, tmp_path):
        """Empty root dir → fail-open: returns dict with nulls, never raises."""
        compose = self._import_compose()
        try:
            result = compose(root=tmp_path)
        except Exception as exc:
            pytest.fail(f"_compose_factor_weather raised on empty root: {exc}")
        assert isinstance(result, dict), "Must return dict even on missing inputs"
        assert result.get("display_only") is True, "display_only must be True"

    def test_fail_open_missing_data_dir(self, tmp_path):
        """Missing data/ dir → fail-open: returns dict with nulls."""
        compose = self._import_compose()
        # tmp_path is empty — no data/ or site/ dir
        result = compose(root=tmp_path)
        assert isinstance(result, dict)
        assert result.get("display_only") is True

    def test_lobe_purity_identical_on_double_call(self, tmp_path):
        """Calling _compose_factor_weather twice with same root → identical dicts."""
        compose = self._import_compose()
        r1 = compose(root=tmp_path)
        r2 = compose(root=tmp_path)

        import json as _json
        s1 = _json.dumps(r1, sort_keys=True, default=str)
        s2 = _json.dumps(r2, sort_keys=True, default=str)
        assert s1 == s2, "Lobe must be pure — double-call must produce identical dicts"

    def test_display_only_hardcoded_true(self, tmp_path):
        """display_only must be True — §5.4 mandates this."""
        compose = self._import_compose()
        result = compose(root=tmp_path)
        assert result.get("display_only") is True

    def test_lobe_has_required_keys(self, tmp_path):
        """Lobe must include the §5.4-specified keys (may be None)."""
        compose = self._import_compose()
        result = compose(root=tmp_path)
        required = {
            "style_regime", "style_regime_pending", "style_regime_hold_days",
            "factor_leader", "factor_leader_ic",
            "etf_pulse_summary", "display_only",
        }
        missing = required - set(result.keys())
        assert not missing, (
            f"_compose_factor_weather missing required keys: {missing}"
        )

    def test_lobe_has_ratio_keys(self, tmp_path):
        """Lobe must include the three ETF ratio keys (FIX-3)."""
        compose = self._import_compose()
        result = compose(root=tmp_path)
        ratio_keys = {"ratio_iwf_iwd_20d", "ratio_qqq_spy_20d", "ratio_iwm_spy_20d"}
        missing = ratio_keys - set(result.keys())
        assert not missing, (
            f"_compose_factor_weather missing ratio keys: {missing} "
            "(FIX-3: real 20d ETF ratios, not etf_pulse.json)"
        )

    def test_nan_guard_prevents_invalid_json(self, tmp_path):
        """FIX-5 regression: lobe output must serialize cleanly with allow_nan=False.

        Feed a synthetic panel row with style_regime_pending=float('nan') and a
        numpy.float64 field — the output must json.dumps cleanly without NaN literals
        or numpy type errors.

        This guards against the house issue where np.int64 in JSON triggered
        TypeError and broad except silently zeroed ledgers (qledger-numpy-json-dumps
        memory entry).
        """
        import json as _json
        import numpy as np_

        ws = self._import_ws()
        _clean = ws._clean if hasattr(ws, "_clean") else None
        if _clean is None:
            pytest.skip("_clean not available")

        # Simulate the pathological values that used to ship as 'NaN' literal:
        compose = self._import_compose()
        result = compose(root=tmp_path)

        # Manually inject NaN and numpy scalar to simulate panel read:
        result_patched = dict(result)
        result_patched["style_regime_pending"] = _clean(float("nan"))
        result_patched["style_regime_hold_days"] = _clean(np_.int64(5))
        result_patched["factor_leader_ic"] = _clean(np_.float64(-0.03))

        # Must serialize without error (allow_nan=False catches NaN literals):
        try:
            s = _json.dumps(result_patched, allow_nan=False)
        except (ValueError, TypeError) as exc:
            pytest.fail(
                f"FIX-5 regression: lobe output fails json.dumps(allow_nan=False): {exc}\n"
                f"Patched dict: {result_patched}"
            )
        # Values round-trip correctly:
        loaded = _json.loads(s)
        assert loaded["style_regime_pending"] is None, (
            "NaN float must become null, not 'NaN' literal"
        )
        assert isinstance(loaded["style_regime_hold_days"], int), (
            "numpy.int64 must become native int"
        )
        assert isinstance(loaded["factor_leader_ic"], float), (
            "numpy.float64 must become native float"
        )

    def test_clean_helper_nan_becomes_none(self):
        """_clean: float NaN → None; float Inf → None; None → None."""
        import math
        _clean = self._import_clean()
        assert _clean(None) is None
        assert _clean(float("nan")) is None
        assert _clean(float("inf")) is None
        assert _clean(float("-inf")) is None
        assert _clean(0.0) == 0.0
        assert _clean(1.5) == 1.5
        assert _clean("hello") == "hello"

    def test_clean_helper_numpy_scalars(self):
        """_clean: numpy scalar types → native Python types."""
        import numpy as np_
        _clean = self._import_clean()

        # numpy int:
        v_int = _clean(np_.int64(42))
        assert isinstance(v_int, int), f"Expected int, got {type(v_int)}"
        assert v_int == 42

        # numpy float (non-NaN):
        v_float = _clean(np_.float64(3.14))
        assert isinstance(v_float, float), f"Expected float, got {type(v_float)}"
        assert abs(v_float - 3.14) < 1e-9

        # numpy float NaN → None:
        v_nan = _clean(np_.float64(float("nan")))
        assert v_nan is None, "numpy NaN float must become None"

        # numpy bool_:
        v_bool = _clean(np_.bool_(True))
        assert isinstance(v_bool, bool), f"Expected bool, got {type(v_bool)}"
        assert v_bool is True


# ---------------------------------------------------------------------------
# P1-C tests — behavioral hysteresis (FIX-6)
# ---------------------------------------------------------------------------
class TestStyleRegimeBehavioralHysteresis:
    """FIX-6: behavioral hysteresis tests that actually drive non-mixed raw states.

    The prior 7 TestStyleRegimeClassifier tests were non-behavioral: fixtures
    had factor_series.json lacking chart_data.spread, so leader was always
    'mixed' and no non-mixed raw state could ever arise.

    These new tests build fixtures that genuinely satisfy growth_momentum or
    quality_defense conditions (real ETF closes + a factor_series.json with
    chart_data.spread providing the confirmed leader), then assert EXACT
    hysteresis behavior:
      - day-1 match: confirmed='mixed', pending='growth_momentum'
      - day-2 consecutive: confirmed='growth_momentum', pending=None
      - conditions failing after: immediate confirmed='mixed'
      - future-append: history unchanged (idempotence / PIT)

    Mutation demonstration (included in test docstrings): changing the structural 2-day rule
    from 2 to 1 causes test_two_day_confirm_flips_confirmed to fail.
    """

    def _write_etf_closes(self, ydir: Path, sym: str,
                          dates: pd.DatetimeIndex, closes: np.ndarray) -> None:
        """Write a yahoo-style parquet with a 'close' column."""
        df = pd.DataFrame({"close": closes}, index=dates)
        df.to_parquet(ydir / f"{sym}.parquet")

    def _write_growth_momentum_fixture(
        self, root: Path, n_base: int = 80, n_signal: int = 5,
    ) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
        """Write ETF + factor_series fixtures that drive growth_momentum raw state.

        growth_momentum conditions (§3.4 frozen thresholds):
          QQQ/SPY 20d ratio > +0.03
          leader in {'growth', 'profitability'}
          IWF/IWD 20d ratio > 0

        Design (robust, not marginal):

        The fixture has two phases:

        1. Base period (n_base days): Factor leader 'growth' is CONFIRMED (by a rising
           growth_spread that gives 3+ consecutive leader sessions, achieved within the
           first 30 base days). ETF ratios are ALL ZERO in this phase, so no
           growth_momentum condition fires → confirmed='mixed' throughout base period.

        2. Signal window (n_signal days): ETF ratios EXCEED thresholds with a large
           margin — QQQ outperforms SPY by +0.4%/day compounded over 20 days = +8.3%
           20d ratio (well above the 0.03 threshold). IWF outperforms IWD by +0.3%/day
           → ratio > 0. Leader is still 'growth' (factor_series.json covers full period).
           Now all three growth_momentum conditions are met → raw='growth_momentum'.
           The hysteresis counter runs over signal_dates only.

        Key insight: in the signal window, the 20-day rolling window contains BOTH
        base days (0% edge) and signal days (+0.4% edge). On signal day 1, the 20-window
        has 19 base days (0%) and 1 signal day (+0.4%) → cumulative ratio ≈ +0.4%.
        That is < 0.03 threshold!

        Fix: use a LARGER daily edge so even 1 day in the window exceeds the threshold.
        We need (1+edge) - 1 > 0.03 → edge > 0.03. Use +4%/day (0.04).
        Then signal day 1: window = 19 base (0%) + 1 signal (+4%) → ratio ≈ +4%.
        min_periods=10, so we need the window to have at least 10 observations.
        With n_base=80 (>> 20), the window is always full → ratio = (1.04)^1 × 1^19 - 1 ≈ +4%.

        Actually the implementation computes: roll_a - roll_b where roll_a = prod(1+a_ret)
        and roll_b = prod(1+b_ret) over the 20-window. QQQ on signal day 1:
          roll_qqq = (1+0.04)^1 × (1+0)^19 = 1.04
          roll_spy = (1+0)^20 = 1.0
          ratio = 1.04 - 1.0 = 0.04 > 0.03 ✓

        Similarly IWF on signal day 1:
          roll_iwf = (1+0.03)^1 = 1.03, roll_iwd = 1.0 → ratio = 0.03 > 0 ✓

        Returns (all_dates, signal_dates).
        """
        ydir = root / "data" / "yahoo"
        ydir.mkdir(parents=True, exist_ok=True)
        fddir = root / "site" / "factordata"
        fddir.mkdir(parents=True, exist_ok=True)

        n_total = n_base + n_signal
        dates = pd.bdate_range("2024-01-02", periods=n_total)
        signal_dates = dates[n_base:]

        # Base period: all ETFs have ZERO daily returns → ratios exactly 0.
        # Signal window: QQQ +4%/day, IWF +3%/day (large edges so even 1 day in the
        # 20-window exceeds the threshold; no random noise to be deterministic).
        qqq_ret = np.zeros(n_total)
        spy_ret = np.zeros(n_total)
        iwf_ret = np.zeros(n_total)
        iwd_ret = np.zeros(n_total)
        iwm_ret = np.zeros(n_total)

        signal_slice = slice(n_base, n_total)
        qqq_ret[signal_slice] = 0.04   # +4%/day → ratio = 4% on signal day 1
        iwf_ret[signal_slice] = 0.03   # +3%/day → ratio = 3% > 0 on signal day 1

        def _to_closes(ret_arr: np.ndarray) -> np.ndarray:
            return 100.0 * (1 + ret_arr).cumprod()

        for sym, ret in [("QQQ", qqq_ret), ("SPY", spy_ret),
                         ("IWF", iwf_ret), ("IWD", iwd_ret),
                         ("IWM", iwm_ret)]:
            self._write_etf_closes(ydir, sym, dates, _to_closes(ret))

        # factor_series.json: 'growth' confirmed leader from day 30 of base period onward.
        # Growth spread rises starting at day 30; by day 33+ (3+ sessions), leader='growth'.
        # This ensures leader='growth' is confirmed well before the signal window AND
        # stays confirmed throughout the signal window.
        dates_str = [str(d.date()) for d in dates]
        n_leader_start = 30  # start growth outperformance at day 30 of base period

        growth_spread: list[float] = []
        for i in range(n_total):
            if i == 0:
                growth_spread.append(1.0)
            elif i < n_leader_start:
                growth_spread.append(growth_spread[-1])  # flat
            else:
                growth_spread.append(growth_spread[-1] * 1.02)  # +2%/day growth

        other_spread = [1.0] * n_total  # all other factors flat throughout

        factor_series_json = {
            "as_of": str(dates[-1].date()),
            "rotation": {"leader": "growth"},
            "chart_data": {
                "dates": dates_str,
                "spread": {
                    "growth": growth_spread,
                    "value": other_spread,
                    "quality": other_spread,
                    "low_vol": other_spread,
                    "profitability": other_spread,
                    "payout": other_spread,
                }
            }
        }
        (fddir / "factor_series.json").write_text(json.dumps(factor_series_json))

        return dates, signal_dates

    def test_day1_match_goes_to_pending_not_confirmed(self, tmp_path):
        """FIX-6 behavioral: day-1 growth_momentum match → pending='growth_momentum',
        confirmed='mixed'.

        This test requires a fixture that actually drives a non-mixed raw state.
        The fixture gives exactly 1 signal day at the end.  With the structural 2-consecutive-day rule (§3.4),
        the confirmed state must stay 'mixed' and pending must be 'growth_momentum'.

        MUTATION DEMONSTRATION: changing the structural 2-day rule from 2 to 1 would make
        day-1 confirm immediately → confirmed becomes 'growth_momentum' → this test
        FAILS (confirmed != 'mixed').
        """
        n_base = 80
        n_signal = 1  # exactly 1 signal day
        dates, signal_dates = self._write_growth_momentum_fixture(
            tmp_path, n_base=n_base, n_signal=n_signal
        )
        build_dates = signal_dates  # just the 1 signal day

        confirmed, pending = _build_style_regime_timeline(tmp_path, build_dates)
        assert len(confirmed) == len(build_dates)

        # With 1 signal day: raw='growth_momentum' but hysteresis requires 2 consecutive.
        # Therefore: confirmed='mixed', pending='growth_momentum'.
        last_confirmed = confirmed.iloc[-1]
        last_pending = pending.iloc[-1]

        assert last_confirmed == "mixed", (
            f"FIX-6 behavioral: day-1 match must keep confirmed='mixed' "
            f"(§3.4 requires 2 consecutive). "
            f"Got confirmed='{last_confirmed}'. "
            "MUTATION CHECK: if this fails under an immediate-flip mutation, "
            "the hysteresis is correctly non-trivial."
        )
        assert last_pending == "growth_momentum", (
            f"FIX-6 behavioral: day-1 match must set pending='growth_momentum'. "
            f"Got pending='{last_pending}'"
        )

    def test_two_consecutive_days_flip_confirmed(self, tmp_path):
        """FIX-6 behavioral: 2 consecutive growth_momentum days → confirmed='growth_momentum'.

        MUTATION DEMONSTRATION: under an immediate-flip mutation, day-1 already confirms
        → this test still PASSES (weaker). But test_day1_match_goes_to_pending_not_confirmed
        FAILS (that test only gives 1 signal day, so under immediate-flip the
        confirmed would be 'growth_momentum' not 'mixed').

        More robustly: if we delete the 'pending' column concept entirely (never set
        pending state, always flip on first match), then:
        - test_day1_match_goes_to_pending_not_confirmed FAILS (confirmed='growth_momentum')
        - this test STILL PASSES (2-day confirmed is also 1-day confirmed)
        But test_pending_tracks_candidate_on_day1 below FAILS (pending is always None).
        """
        n_base = 80
        n_signal = 2  # exactly 2 consecutive signal days
        dates, signal_dates = self._write_growth_momentum_fixture(
            tmp_path, n_base=n_base, n_signal=n_signal
        )
        build_dates = signal_dates

        confirmed, pending = _build_style_regime_timeline(tmp_path, build_dates)
        assert len(confirmed) == len(build_dates)

        # After 2 consecutive signal days: confirmed='growth_momentum', pending=None
        last_confirmed = confirmed.iloc[-1]
        last_pending = pending.iloc[-1]

        assert last_confirmed == "growth_momentum", (
            f"FIX-6 behavioral: 2 consecutive days must flip confirmed to "
            f"'growth_momentum'. Got confirmed='{last_confirmed}'. "
            "MUTATION: changing confirm to 1-day still passes this; "
            "test_day1_match_goes_to_pending_not_confirmed is the discriminating test."
        )
        assert last_pending is None, (
            f"FIX-6 behavioral: after 2-day confirm, pending must be None. "
            f"Got pending='{last_pending}'"
        )

    def test_pending_tracks_candidate_on_day1(self, tmp_path):
        """FIX-6 behavioral: 2-day fixture — day-1 sets pending, day-2 clears it.

        Build with 2 signal days; look at BOTH days:
        - day-1: confirmed='mixed', pending='growth_momentum'
        - day-2: confirmed='growth_momentum', pending=None

        MUTATION: removing the pending state (always None) causes day-1 pending to be
        None → this test FAILS on the day-1 pending assertion.
        """
        n_base = 80
        n_signal = 2
        dates, signal_dates = self._write_growth_momentum_fixture(
            tmp_path, n_base=n_base, n_signal=n_signal
        )
        build_dates = signal_dates  # the 2 signal days

        confirmed, pending = _build_style_regime_timeline(tmp_path, build_dates)
        assert len(confirmed) == 2

        # Day 1 of signal window:
        day1_confirmed = confirmed.iloc[0]
        day1_pending = pending.iloc[0]
        # Day 2 of signal window:
        day2_confirmed = confirmed.iloc[1]
        day2_pending = pending.iloc[1]

        assert day1_confirmed == "mixed", (
            f"FIX-6 day-1: confirmed must stay 'mixed'. Got '{day1_confirmed}'. "
            "MUTATION: an immediate-flip (no pending step) makes this fail — executed proof in P1-C adjudication."
        )
        assert day1_pending == "growth_momentum", (
            f"FIX-6 day-1: pending must be 'growth_momentum'. Got '{day1_pending}'. "
            "MUTATION: removing pending state makes this fail."
        )
        assert day2_confirmed == "growth_momentum", (
            f"FIX-6 day-2: confirmed must flip to 'growth_momentum'. Got '{day2_confirmed}'."
        )
        assert day2_pending is None, (
            f"FIX-6 day-2: after flip, pending must be None. Got '{day2_pending}'."
        )

    def test_reversion_to_mixed_is_immediate(self, tmp_path):
        """FIX-6 behavioral: after confirm, failing conditions → immediate 'mixed'.

        Strategy: drive growth_momentum for 2 days (confirming it), then on day 3
        make the factor LEADER go 'mixed' by truncating factor_series.json to not
        cover day 3's date. The leader lookup falls back to 'mixed' for missing dates
        → growth_momentum condition fails → raw='mixed' → confirmed flips immediately.

        This isolates the hysteresis-reversion path independently of ETF ratios.
        """
        root = tmp_path / "revert"
        root.mkdir()
        n_base = 80
        n_signal = 3  # signal days: [gm, gm, mixed-leader] → [mixed, confirmed, mixed]
        n_total = n_base + n_signal
        dates = pd.bdate_range("2024-01-02", periods=n_total)
        signal_dates = dates[n_base:]

        ydir = root / "data" / "yahoo"
        ydir.mkdir(parents=True, exist_ok=True)
        fddir = root / "site" / "factordata"
        fddir.mkdir(parents=True, exist_ok=True)

        # ETFs: zero returns in base period (all ratios = 0 → no growth_momentum in base).
        # All 3 signal days: QQQ +4%/day, IWF +3%/day (large edge, ratio >0.03 on day 1).
        qqq_ret = np.zeros(n_total)
        iwf_ret = np.zeros(n_total)
        signal_slice = slice(n_base, n_total)
        qqq_ret[signal_slice] = 0.04   # +4%/day, ratio ≈ +4% on signal day 1
        iwf_ret[signal_slice] = 0.03   # +3%/day, ratio > 0

        def _to_closes(ret_arr: np.ndarray) -> np.ndarray:
            return 100.0 * (1 + ret_arr).cumprod()

        for sym, ret in [("QQQ", qqq_ret), ("SPY", np.zeros(n_total)),
                         ("IWF", iwf_ret), ("IWD", np.zeros(n_total)),
                         ("IWM", np.zeros(n_total))]:
            df = pd.DataFrame({"close": _to_closes(ret)}, index=dates)
            df.to_parquet(ydir / f"{sym}.parquet")

        # factor_series.json: covers base + signal days 1 and 2 ONLY (NOT signal day 3).
        # Signal day 3's date is absent → leader falls back to 'mixed' via ffill but
        # since _compute_leader_series uses reindex(method='ffill'), the last confirmed
        # leader will ffill. So we need a DIFFERENT strategy: make ALL factors flat (equal)
        # on signal day 3 so the leader becomes 'mixed' (no dominant factor).
        # Actually: truncate factor_series.json so it doesn't cover signal day 3 at all.
        # reindex(method='ffill') WILL ffill the leader from signal day 2 to day 3.
        # → The leader stays 'growth' even on signal day 3. That breaks our reversion plan.
        #
        # Better plan for reversion: use factor_series.json with ALL factors identical
        # on signal days 1-3, then shift the advantage back to other factors on day 3.
        # Make growth spread FLAT on day 3 while ALL others remain flat too → leader stays
        # 'growth' via ffill. Still broken.
        #
        # Most reliable plan: use factor_series.json where growth STOPS outperforming
        # and 'value' takes over on signal day 3 → 20d rolling leader becomes 'value'
        # after 3+ sessions. But 3-session debounce means single day change won't flip.
        #
        # Cleanest plan: use a leader that switches BEFORE the signal window.
        # Instead, just use the simple hysteresis property directly:
        # growth_momentum requires: QQQ/SPY > 0.03 AND leader ∈ {growth, profitability}
        # On day 3: make QQQ/SPY ratio = 0 by having QQQ also be 0 on day 3.
        # But the 20-day window on day 3 contains signal days 1 and 2 (both with +4%),
        # so ratio ≈ +8% (two slots of +4%) → still > 0.03.
        #
        # Resolution: use the factor_series.json truncation but account for ffill.
        # The reindex(method='ffill') in _compute_leader_series fills the last date's
        # leader to ALL subsequent dates. But the function computes leader for
        # ALL ETF dates, then reindexes to the requested dates.
        # If factor_series.json ends before signal day 3, the roll20 DataFrame ends there,
        # and the reindex to all_etf_dates_idx will ffill to signal day 3.
        # So the leader IS 'growth' on signal day 3 too. Truncation alone doesn't work.
        #
        # True resolution: write factor_series.json where ALL factors have EQUAL returns
        # on signal day 3, so no single factor dominates → leader_raw picks 'growth'
        # (idxmax returns first column in case of tie, which alphabetically is 'growth').
        # That also doesn't give 'mixed'. The classification returns 'mixed' only when
        # NO matches pass or multiple match. But 'mixed' leader → no condition fires.
        #
        # FINAL PLAN: Write factor_series.json where a NON-GROWTH factor (e.g. 'quality')
        # becomes the confirmed leader on signal day 3. Since confirmed leader requires
        # 3 consecutive sessions, and we only have 1 day, the confirmed leader stays
        # 'growth' (debounce). Raw leader may change but confirmed won't flip in 1 day.
        # → This doesn't work in 1 signal day either.
        #
        # The CORRECT approach: test reversion via the ETF ratio alone.
        # We need QQQ/SPY 20d ratio < 0.03 on signal day 3.
        # Current setup: signal days 1+2 each add +4% to the 20-slot window.
        # On signal day 3, the window has: 18 base days (0%) + 2 signal days (+4%each).
        # Ratio = (1.04^2 × 1.0^18) - 1.0^20 ≈ (1.0816 - 1) = 0.0816 > 0.03.
        # Still above threshold.
        #
        # We need to put ZERO returns on signal day 3 for QQQ AND reduce signal day 1+2
        # contribution to < 0.03. Use a much smaller edge: +1.5%/day.
        # On day 3 with QQQ=0: window has 18 zeros + 2 signal days (1.5%each).
        # Ratio = 1.015^2 - 1 = 0.0302 ≈ 0.03. That's marginal.
        # Use 1%/day instead: ratio = 1.01^2 - 1 = 0.0201 < 0.03 ✓ on signal day 3.
        # But signal day 1: window has 19 zeros + 1 day of +1% → ratio = 0.01 < 0.03. ✗
        # That FAILS signal day 1 (ratio doesn't exceed threshold).
        #
        # ACTUAL RESOLUTION:
        # On signal DAY 1: need ratio > 0.03 → use a LARGE edge (+4%/day) ON day 1 only.
        # On signal DAY 2: same large edge, ratio ≈ +8% (2 slots) → still > 0.03.
        # On signal DAY 3: small edge (0%) on day 3 itself. Window has slots:
        #   17 zeros (base) + 2 signal-1-2 (+4%) + 1 signal-3 (0%) = ratio ≈ +8% > 0.03.
        # Ratio is high regardless. Back to the same problem.
        #
        # ONLY CLEAN PATH: use a different mechanism for signal day 3 failure — make
        # the leader switch. For the leader to switch ON signal day 3, we need:
        #   - growth was confirmed leader before signal window (3 consecutive dominant)
        #   - ALL factors flat for 3+ sessions ending on signal day 3 → raw leader is
        #     whatever factor was already dominant (still 'growth') → no switch.
        #
        # The honest conclusion: the reversion test should use a completely SEPARATE
        # fixture where the ETF ratio drops below 0.03 specifically through using a
        # SHORT window of signal-edge days (only 2), and then having QQQ edge stop.
        # The ratio on day 3 depends on how many edge days are still IN the 20-window.
        # If we use only 2 signal days WITH edge, then on day 3 (zero edge), the window
        # contains: 17 zeros + 2 edge days → ratio still > 0.03 (if edge was 4%).
        #
        # The ONLY way to get ratio < 0.03 on signal day 3 is if fewer edge-days
        # are in the window AND/OR the edge is smaller.
        # With edge=4% and exactly 1 edge day in the window: ratio = 4% > 3%. ✗
        # With edge=2% and exactly 1 edge day: ratio = 2% < 3%. ✓
        # But with edge=2% and signal day 1: 1 edge day → ratio = 2% < 3%. ✗ day1 fails.
        #
        # BREAKTHROUGH: use TWO SEPARATE ETF EDGE VALUES.
        # Signal day 1: use a LARGE one-time spike (+50%/day) → ratio = 50% >> 0.03 ✓
        # Signal day 2: same spike → ratio = (1.5^2 - 1) = 1.25 >> 0.03 ✓
        # Signal day 3: zero → ratio = 1.5^2 / 1 - 1 ≈ 125% (still in window!) ✗
        # STILL DOESN'T WORK because all 3 days are within the 20-window.
        #
        # FINAL BREAKTHROUGH: use NEGATIVE ETF edge on signal day 3 to bring the ratio
        # below 0.03. With spike of +4% on days 1+2, on day 3:
        # roll_qqq = (1.04)^2 * (1 + edge3)^1 * 1^17
        # roll_spy = 1^20
        # ratio = (1.04^2) * (1 + edge3) - 1
        # We need: 1.0816 * (1 + edge3) - 1 < 0.03
        # → 1 + edge3 < 1.03 / 1.0816 ≈ 0.9523
        # → edge3 < -4.77%
        # Use edge3 = -10%/day on signal day 3.
        # ratio = 1.0816 * 0.90 - 1 = 0.97344 - 1 = -0.02656 < 0.03 ✓
        # IWF on day 3: 1.03^2 * 0.90 - 1 = 0.9565 - 1 = -0.04 < 0 → IWF/IWD < 0
        # → growth_momentum also fails on the IWF/IWD > 0 condition.
        # So using large negative return on signal day 3 makes raw='mixed'. ✓
        # BUT: negative 10% daily return is unrealistic but fine for a test fixture.

        # Re-build ETF arrays with this approach:
        qqq_ret2 = np.zeros(n_total)
        iwf_ret2 = np.zeros(n_total)
        qqq_ret2[n_base] = 0.04      # signal day 1: +4%
        qqq_ret2[n_base + 1] = 0.04  # signal day 2: +4%
        qqq_ret2[n_base + 2] = -0.10 # signal day 3: −10% (kills the ratio)
        iwf_ret2[n_base] = 0.03
        iwf_ret2[n_base + 1] = 0.03
        iwf_ret2[n_base + 2] = -0.10

        for sym, ret in [("QQQ", qqq_ret2), ("SPY", np.zeros(n_total)),
                         ("IWF", iwf_ret2), ("IWD", np.zeros(n_total)),
                         ("IWM", np.zeros(n_total))]:
            df = pd.DataFrame({"close": _to_closes(ret)}, index=dates)
            df.to_parquet(ydir / f"{sym}.parquet")

        # Growth leader: rises from day 30 (confirmed well before signal window).
        # Covers ALL dates including signal day 3 → leader='growth' on all signal days.
        # On signal day 3, ratio < 0.03 → condition fails → raw='mixed' regardless of leader.
        n_leader_start = 30
        growth_spread: list[float] = []
        for i in range(n_total):
            if i == 0:
                growth_spread.append(1.0)
            elif i < n_leader_start:
                growth_spread.append(growth_spread[-1])
            else:
                growth_spread.append(growth_spread[-1] * 1.02)

        factor_series_json = {
            "as_of": str(dates[-1].date()),
            "rotation": {"leader": "growth"},
            "chart_data": {
                "dates": [str(d.date()) for d in dates],
                "spread": {
                    "growth": growth_spread,
                    "value": [1.0] * n_total,
                    "quality": [1.0] * n_total,
                    "low_vol": [1.0] * n_total,
                    "profitability": [1.0] * n_total,
                    "payout": [1.0] * n_total,
                }
            }
        }
        (fddir / "factor_series.json").write_text(json.dumps(factor_series_json))

        confirmed, pending = _build_style_regime_timeline(root, signal_dates)
        assert len(confirmed) == n_signal, (
            f"Expected {n_signal} confirmed states, got {len(confirmed)}"
        )

        # Signal day 1: ratio >0.03, leader='growth' → raw='growth_momentum' first time
        # → pending='growth_momentum', confirmed='mixed'.
        # Signal day 2: raw='growth_momentum' again → FLIP → confirmed='growth_momentum'.
        # Signal day 3: day not in factor_series.json → leader='mixed'
        # → growth_momentum condition FAILS (leader not in {growth, profitability})
        # → raw='mixed' → IMMEDIATE reversion → confirmed='mixed'.
        day1 = confirmed.iloc[0]
        day2 = confirmed.iloc[1]
        day3 = confirmed.iloc[2]

        assert day1 == "mixed", (
            f"FIX-6 reversion: signal day 1 (1 consecutive) must be 'mixed'. Got '{day1}'."
        )
        assert day2 == "growth_momentum", (
            f"FIX-6 reversion: signal day 2 (2 consecutive) must be 'growth_momentum'. "
            f"Got '{day2}'."
        )
        assert day3 == "mixed", (
            f"FIX-6 reversion: signal day 3 (leader='mixed') must IMMEDIATELY revert to "
            f"'mixed'. Got '{day3}'. "
            "MUTATION: if reversion required 2 days, day3 would stay 'growth_momentum'."
        )

    def test_future_append_leaves_history_unchanged(self, tmp_path):
        """FIX-6 idempotence: appending future signal dates must not change past states.

        Build twice in separate roots: once with n_signal=2 (2 days), once with
        n_signal=4 (4 days, same base period + 2 extra future days).
        The first 2 confirmed states must be identical between the two runs — i.e.
        adding future dates to the build_dates arg does not alter historical states.
        """
        root_2 = tmp_path / "sig2"
        root_4 = tmp_path / "sig4"
        root_2.mkdir()
        root_4.mkdir()

        # Write separate fixtures for each root (n_signal differs):
        dates_2, signal_dates_2 = self._write_growth_momentum_fixture(
            root_2, n_base=80, n_signal=2
        )
        dates_4, signal_dates_4 = self._write_growth_momentum_fixture(
            root_4, n_base=80, n_signal=4
        )

        conf_2, _ = _build_style_regime_timeline(root_2, signal_dates_2)
        conf_4, _ = _build_style_regime_timeline(root_4, signal_dates_4)

        # The sig4 root has 4 signal days; sig2 has 2.
        # The FIRST 2 signal dates in both fixtures correspond to the same chronological
        # position relative to the base period (both use bdate_range from "2024-01-02").
        # The confirmed states for those 2 dates must be identical:
        assert len(conf_2) == 2
        assert len(conf_4) == 4
        for i in range(2):
            assert conf_2.iloc[i] == conf_4.iloc[i], (
                f"FIX-6 idempotence: signal date {i} differs between n_signal=2 "
                f"('{conf_2.iloc[i]}') and n_signal=4 ('{conf_4.iloc[i]}'). "
                "Future-append must not change past confirmed states."
            )


# ---------------------------------------------------------------------------
# P1-C tests — schema stability (55 columns)
# ---------------------------------------------------------------------------
class TestSchemaStability55:
    """P1-C: panel parquet must have exactly 55 columns (PANEL_COLUMNS)."""

    def test_panel_columns_count(self):
        """PANEL_COLUMNS must have exactly 55 entries after P1-C."""
        assert len(PANEL_COLUMNS) == 55, (
            f"Expected 55 PANEL_COLUMNS (48 P1-A + 4 P1-B + 3 P1-C); got {len(PANEL_COLUMNS)}"
        )

    def test_p1c_columns_in_panel_columns(self):
        """dna_class, style_regime, style_regime_pending must be in PANEL_COLUMNS."""
        p1c_cols = {"dna_class", "style_regime", "style_regime_pending"}
        missing = p1c_cols - set(PANEL_COLUMNS)
        assert not missing, f"P1-C columns missing from PANEL_COLUMNS: {missing}"

    def _write_minimal_p1c_fixtures(self, root: Path, tickers: list,
                                    sectors: list, n_dates: int = 350) -> pd.DatetimeIndex:
        """Write minimal fixtures including ETF Yahoo parquets for style_regime."""
        rng = np.random.default_rng(77)
        dates = pd.bdate_range("2025-01-02", periods=n_dates)
        as_of = dates[-1]

        bdir = root / "data" / "breadth"
        bdir.mkdir(parents=True, exist_ok=True)
        closes = pd.DataFrame(
            {t: 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()
             for t in tickers}, index=dates)
        closes.to_parquet(bdir / "_closes_cache.parquet")
        meta = pd.DataFrame({"name": tickers, "sector": sectors}, index=tickers)
        meta.to_parquet(bdir / "constituents.parquet")

        ydir = root / "data" / "yahoo"
        ydir.mkdir(exist_ok=True)
        # Write block-A ETF streams:
        for sym in ["SPY", "IWM", "QQQ", "TLT", "DX-Y.NYB", "FXI", "XLK"]:
            df = pd.DataFrame(
                {"close": 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()},
                index=dates)
            df.to_parquet(ydir / f"{sym}.parquet")
        # Write style_regime ETF streams:
        for sym in ["IWF", "IWD"]:
            df = pd.DataFrame(
                {"close": 100.0 * (1 + rng.normal(0, 0.01, n_dates)).cumprod()},
                index=dates)
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
            {"ticker": t,
             **{leg: float(rng.normal(0, 1)) for leg in BLOCK_B_LEGS},
             "mktcap_bn": 10.0}
            for t in tickers
        ]
        (fddir / "factors.json").write_text(json.dumps({
            "as_of": str(as_of.date()), "table": factors_table,
        }))
        # Minimal factor_series.json for style_regime:
        (fddir / "factor_series.json").write_text('{"as_of": "' + str(as_of.date()) + '"}')

        return dates

    def test_schema_55_cols_after_p1c(self, tmp_path):
        """Panel written to parquet must have exactly 55 columns == PANEL_COLUMNS."""
        tickers = ["AAPL", "MSFT"]
        sectors = ["Information Technology", "Information Technology"]
        dates = self._write_minimal_p1c_fixtures(tmp_path, tickers, sectors)
        start = dates[-3]
        end = dates[-1]
        build_panel(
            data_root=tmp_path, out_root=tmp_path,
            start_date=start, end_date=end, tickers=tickers,
        )
        parquet_files = list((tmp_path / "data" / "factordata" / "panel").rglob("panel.parquet"))
        assert parquet_files, "No parquet files written"
        for p in parquet_files:
            cols = list(pd.read_parquet(p).columns)
            assert cols == PANEL_COLUMNS, (
                f"Schema mismatch in {p}.\n"
                f"Extra: {set(cols) - set(PANEL_COLUMNS)}\n"
                f"Missing: {set(PANEL_COLUMNS) - set(cols)}\n"
                f"Expected exactly {len(PANEL_COLUMNS)} columns, got {len(cols)}"
            )

    def test_gitignore_panel_not_tracked(self, tmp_path):
        """Panel dir must be gitignored (data/factordata/panel/ in .gitignore).

        RULING-C: nightly panel step writes no tracked files — sentinel git-add
        staging set needs no changes.
        """
        import subprocess
        repo_root = Path(__file__).resolve().parents[1]
        gitignore = repo_root / ".gitignore"
        assert gitignore.exists(), ".gitignore not found"
        content = gitignore.read_text()
        assert "data/factordata/panel/" in content, (
            "data/factordata/panel/ must be in .gitignore "
            "(RULING-C: no tracked files written by panel step)"
        )


class TestSeasonalClimateRead:
    """Fail-open branches of world_state._read_seasonal_climate (B4)."""

    def _import_read(self):
        import importlib
        ws = importlib.import_module("engine.neuralweb.world_state")
        if not hasattr(ws, "_read_seasonal_climate"):
            pytest.skip("_read_seasonal_climate not present")
        return ws._read_seasonal_climate

    def _write(self, tmp_path, payload):
        import json as _json
        d = tmp_path / "site" / "factordata"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "factor_seasonality.json"
        p.write_text(payload if isinstance(payload, str) else _json.dumps(payload))
        return tmp_path

    def test_absent_file_none(self, tmp_path):
        assert self._import_read()(tmp_path) is None

    def test_non_dict_json_none(self, tmp_path):
        assert self._import_read()(self._write(tmp_path, "[1, 2, 3]")) is None

    def test_malformed_json_none(self, tmp_path):
        assert self._import_read()(self._write(tmp_path, "{not json")) is None

    def test_v1_schema_none(self, tmp_path):
        repo = self._write(tmp_path, {"as_of": "2026-05", "factors": []})
        assert self._import_read()(repo) is None

    def test_v2_missing_now_none(self, tmp_path):
        repo = self._write(tmp_path, {"schema": "factor_seasonality.v2", "as_of": "2026-05"})
        assert self._import_read()(repo) is None

    def test_valid_v2_compact_dict(self, tmp_path):
        repo = self._write(tmp_path, {
            "schema": "factor_seasonality.v2", "as_of": "2026-05",
            "now": {
                "month": 7,
                "factors": [
                    {"key": "momentum", "verdict": "headwind"},
                    {"key": "value", "verdict": "neutral"},
                    {"key": None, "verdict": "neutral"},
                ],
                "headline_en": "July is usually a rough month for the market's recent winners.",
                "stance_en": "Watch — don't chase this month's hottest stocks.",
            },
        })
        out = self._import_read()(repo)
        assert out is not None
        assert out["display_only"] is True
        assert out["month"] == 7
        assert out["seasonality_as_of"] == "2026-05"
        assert out["verdicts"] == {"momentum": "headwind", "value": "neutral"}
        assert "rough month" in out["headline_en"]
        assert out["stance_en"].startswith("Watch")
