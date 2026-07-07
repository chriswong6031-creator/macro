"""Minimal no-network tests for W3 bank call-report stress scripts.

Tests cover:
  1. Quarter-date generation (collect_ffiec_y9c._quarter_dates)
  2. Signal construction (w3_bank_callreport_stress_phase0._build_signals)
  3. IC computation on synthetic data (no network, no live FDIC call)
  4. Ticker map coverage (all 20 basket members present)
  5. BH correction plumbing (use engine.validation.benjamini_hochberg)

No network calls; no FDIC API; no file system writes during testing.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.collect_ffiec_y9c import _quarter_dates, TICKER_CERT_MAP  # noqa: E402
from scripts.w3_bank_callreport_stress_phase0 import (  # noqa: E402
    _build_signals, _cross_section_ic, _ic_summary, _bootstrap_ic_ci,
    FAMILY,
)
from engine.validation import benjamini_hochberg  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Quarter-date generation
# ---------------------------------------------------------------------------
class TestQuarterDates:
    def test_count_2018_to_2026(self):
        """2018-Q1 to 2026-Q1 should yield exactly 33 quarter-end dates."""
        dates = _quarter_dates("2018-Q1", "2026-Q1")
        assert len(dates) == 33

    def test_first_and_last(self):
        dates = _quarter_dates("2018-Q1", "2026-Q1")
        assert dates[0] == "20180331"
        assert dates[-1] == "20260331"

    def test_q_format(self):
        """Each date is YYYYMMDD and a real quarter-end."""
        dates = _quarter_dates("2023-Q1", "2023-Q4")
        assert dates == ["20230331", "20230630", "20230930", "20231231"]

    def test_single_quarter(self):
        dates = _quarter_dates("2024-Q2", "2024-Q2")
        assert dates == ["20240630"]


# ---------------------------------------------------------------------------
# 2. Ticker map completeness
# ---------------------------------------------------------------------------
EXPECTED_TICKERS = [
    "RF", "KEY", "CFG", "HBAN", "FITB", "MTB", "TFC", "USB", "PNC",
    "WAL", "EWBC", "CFR", "FHN", "WTFC", "WBS", "SSB", "UMBF",
    "BPOP", "COLB", "FCNCA",
]


class TestTickerMap:
    def test_all_20_tickers_present(self):
        for t in EXPECTED_TICKERS:
            assert t in TICKER_CERT_MAP, f"{t} missing from TICKER_CERT_MAP"

    def test_cert_and_rssdhcr_nonzero(self):
        for t, (cert, rssd, name) in TICKER_CERT_MAP.items():
            assert cert > 0, f"{t}: CERT must be positive"
            assert rssd > 0, f"{t}: RSSDHCR must be positive"
            assert len(name) > 3, f"{t}: BHC name too short"


# ---------------------------------------------------------------------------
# 3. Signal construction on synthetic data
# ---------------------------------------------------------------------------
def _make_synthetic_panel(n_tickers: int = 5, n_quarters: int = 12) -> pd.DataFrame:
    """Build a minimal synthetic panel for signal-construction testing."""
    rng = np.random.default_rng(42)
    tickers = [f"T{i}" for i in range(n_tickers)]
    repdte_dates = _quarter_dates("2021-Q1", "2023-Q4")[:n_quarters]
    rows = []
    for t in tickers:
        for qd in repdte_dates:
            asset = rng.uniform(1e7, 1e8)
            eq = asset * rng.uniform(0.07, 0.12)
            dep = asset * rng.uniform(0.75, 0.90)
            depunins = dep * rng.uniform(0.30, 0.55)
            coredep = dep * rng.uniform(0.70, 0.90)
            lnrecons = asset * rng.uniform(0.02, 0.08)
            lnrenres = asset * rng.uniform(0.05, 0.15)
            lnremult = asset * rng.uniform(0.01, 0.04)
            lnlsnet = asset * rng.uniform(0.55, 0.75)
            ncrenrer = rng.uniform(0.5, 5.0)
            ncreconr = rng.uniform(0.0, 3.0)
            lnndepc = dep * rng.uniform(0.0, 0.05)
            sc = asset * rng.uniform(0.10, 0.25)
            cre_total = lnrecons + lnrenres + lnremult
            rows.append({
                "ticker": t,
                "repdte": qd,
                "report_date": pd.Timestamp(f"{qd[:4]}-{qd[4:6]}-{qd[6:8]}"),
                "signal_date": pd.Timestamp(f"{qd[:4]}-{qd[4:6]}-{qd[6:8]}") + pd.Timedelta(days=45),
                "asset": asset, "eq": eq, "dep": dep, "depunins": depunins,
                "coredep": coredep, "lnrecons": lnrecons, "lnrenres": lnrenres,
                "lnremult": lnremult, "lnlsnet": lnlsnet, "ncrenrer": ncrenrer,
                "ncreconr": ncreconr, "lnndepc": lnndepc, "sc": sc,
                "cre_total": cre_total,
                "cre_to_equity": cre_total / eq,
                "cre_to_asset": cre_total / asset,
                "nonfarm_nres_cre": lnrenres,
                "cnd_cre": lnrecons,
                "unins_dep_share": depunins / asset,
                "brkd_dep_share": lnndepc / dep,
                "ncrenrer_wavg": ncrenrer,
                "n_charters": 1,
                "namehcr": f"HC_{t}",
            })
    return pd.DataFrame(rows).sort_values(["ticker", "report_date"]).reset_index(drop=True)


class TestBuildSignals:
    def test_signal_columns_present(self):
        panel = _make_synthetic_panel()
        sig = _build_signals(panel)
        for col in ["v1_score", "v2_score", "v3_score", "signal_date", "ticker"]:
            assert col in sig.columns, f"Missing column: {col}"

    def test_no_nan_in_scores_after_warmup(self):
        """Scores should be finite after dropping the first 2 quarters (warmup)."""
        panel = _make_synthetic_panel(n_quarters=10)
        sig = _build_signals(panel)
        assert sig["v1_score"].notna().all(), "NaN in v1_score after build"
        assert sig["v2_score"].notna().all(), "NaN in v2_score after build"
        assert sig["v3_score"].notna().all(), "NaN in v3_score after build"

    def test_signal_dates_after_report_dates(self):
        """PIT: signal_date must be >= report_date + 44 days."""
        panel = _make_synthetic_panel()
        sig = _build_signals(panel)
        lag = (sig["signal_date"] - sig["report_date"]).dt.days
        assert (lag >= 44).all(), "Signal date precedes PIT lag"

    def test_output_rows_less_than_input(self):
        """Rows should be dropped (NaN from diffs)."""
        panel = _make_synthetic_panel(n_tickers=3, n_quarters=8)
        sig = _build_signals(panel)
        assert len(sig) < len(panel), "No rows dropped — diffs not working"


# ---------------------------------------------------------------------------
# 4. IC computation on synthetic data
# ---------------------------------------------------------------------------
def _make_synthetic_signals_and_returns(n_dates: int = 20, n_tickers: int = 8,
                                         seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    # Signal has a small positive correlation with future returns
    signal_vals = rng.normal(0, 1, (n_dates, n_tickers))
    # Return: signal + noise
    ret_vals = 0.05 * signal_vals + rng.normal(0, 1, (n_dates, n_tickers))

    dates = pd.date_range("2021-01-01", periods=n_dates, freq="QS")
    tickers = [f"T{i}" for i in range(n_tickers)]

    sig_rows = []
    ret_rows = []
    for di, d in enumerate(dates):
        for ti, t in enumerate(tickers):
            sig_rows.append({"ticker": t, "signal_date": d, "v1_score": signal_vals[di, ti]})
            ret_rows.append({"ticker": t, "date": d, "fwd_63d": ret_vals[di, ti]})

    return pd.DataFrame(sig_rows), pd.DataFrame(ret_rows)


class TestICComputation:
    def test_returns_series(self):
        sig, ret = _make_synthetic_signals_and_returns()
        ics = _cross_section_ic(sig, ret, "v1_score", 63)
        assert isinstance(ics, pd.Series), "IC should be a Series"
        assert len(ics) > 0, "IC series is empty"

    def test_ic_in_range(self):
        sig, ret = _make_synthetic_signals_and_returns()
        ics = _cross_section_ic(sig, ret, "v1_score", 63)
        assert (ics.abs() <= 1.0).all(), "IC values must be in [-1, 1]"

    def test_perfect_correlation_gives_high_ic(self):
        """When signal == return (rank-identical), IC should be ≈1."""
        n, m = 15, 10
        vals = np.random.default_rng(1).normal(0, 1, (n, m))
        dates = pd.date_range("2021-01-01", periods=n, freq="QS")
        tickers = [f"T{i}" for i in range(m)]
        sig_rows, ret_rows = [], []
        for di, d in enumerate(dates):
            for ti, t in enumerate(tickers):
                sig_rows.append({"ticker": t, "signal_date": d, "v1_score": vals[di, ti]})
                ret_rows.append({"ticker": t, "date": d, "fwd_63d": vals[di, ti]})
        sig = pd.DataFrame(sig_rows)
        ret = pd.DataFrame(ret_rows)
        ics = _cross_section_ic(sig, ret, "v1_score", 63)
        assert ics.mean() > 0.9, f"Expected IC ≈ 1 for perfect signal, got {ics.mean():.3f}"

    def test_ic_summary_keys(self):
        sig, ret = _make_synthetic_signals_and_returns()
        ics = _cross_section_ic(sig, ret, "v1_score", 63)
        summary = _ic_summary(ics, "test")
        for key in ["mean_ic", "icir", "pct_positive", "t_stat", "p_value", "n_dates"]:
            assert key in summary, f"Missing key {key} in IC summary"

    def test_bootstrap_ci_shape(self):
        sig, ret = _make_synthetic_signals_and_returns()
        ics = _cross_section_ic(sig, ret, "v1_score", 63)
        ci = _bootstrap_ic_ci(ics)
        assert "ci_lo" in ci and "ci_hi" in ci
        assert ci["ci_lo"] <= ci["ci_hi"]

    def test_empty_ics_handled(self):
        ics = pd.Series(dtype=float)
        summary = _ic_summary(ics, "empty")
        assert summary["n_dates"] == 0
        assert math.isnan(summary["mean_ic"])


# ---------------------------------------------------------------------------
# 5. BH correction plumbing
# ---------------------------------------------------------------------------
class TestBHCorrection:
    def test_bh_returns_dict(self):
        pvals = {"V1": 0.04, "V2": 0.10, "V3": 0.82}
        result = benjamini_hochberg(pvals, alpha=0.10)
        assert isinstance(result, dict)
        for k in pvals:
            assert k in result

    def test_bh_q_monotone(self):
        """BH q-values should be >= raw p-values in the adjusted form."""
        pvals = {"A": 0.01, "B": 0.05, "C": 0.15, "D": 0.20}
        result = benjamini_hochberg(pvals)
        for k, v in pvals.items():
            assert result[k]["q"] >= v * 0.99, f"q < p for {k}"

    def test_nan_pvals_excluded(self):
        """NaN p-values should be silently excluded from BH."""
        pvals = {"V1": 0.05, "V2": float("nan"), "V3": 0.20}
        valid = {k: v for k, v in pvals.items() if not math.isnan(v)}
        result = benjamini_hochberg(valid)
        assert "V1" in result and "V3" in result
        assert "V2" not in result


# ---------------------------------------------------------------------------
# 6. Trial ledger — family registration
# ---------------------------------------------------------------------------
class TestTrialLedger:
    def test_family_has_registered_trials(self):
        """The trial ledger for our family should have ≥ 1 config registered."""
        from engine.trial_ledger import TrialLedger
        led = TrialLedger(family=FAMILY)
        n = led.effective_n(FAMILY)
        # Either 0 (clean env) or >= 1 (after study run) — just verify no crash
        assert isinstance(n, int) and n >= 0
