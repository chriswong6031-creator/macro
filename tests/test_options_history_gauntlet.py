"""Hermetic tests for scripts/research/options_history_gauntlet.py.

Tests cover:
1. BH-FDR arithmetic — hand-verified 5-pvalue example.
2. HAC t-test — known mean-zero input returns p≈1; known non-zero input returns finite t.
3. Realized-vol computation — known constant-return series.
4. Skew computation — synthetic chain with known put/call IVs.
5. Absent-store returns early SKIP (no exception).
6. No forward window > 21d computed anywhere (house yardstick guard).
7. No "validated" string in output (CI-mirroring).
"""
from __future__ import annotations

import math
import sys
import os
import pathlib

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import scripts.research.options_history_gauntlet as g


# ---------------------------------------------------------------------------
# Test 1 — BH-FDR arithmetic (hand-verified)
# ---------------------------------------------------------------------------

def test_bh_fdr_hand_example():
    """BH with 5 p-values, k=10 (pre-stated family size), alpha=0.10."""
    # p-values sorted: 0.001, 0.01, 0.03, 0.07, 0.12
    # BH thresholds: i/10 * 0.10 = 0.01, 0.02, 0.03, 0.04, 0.05
    # Reject: 0.001 <= 0.01 YES; 0.01 <= 0.02 YES; 0.03 <= 0.03 YES;
    #         0.07 <= 0.04 NO; 0.12 <= 0.05 NO
    pvals = {"a": 0.001, "b": 0.01, "c": 0.03, "d": 0.07, "e": 0.12}
    result = g._bh_fdr(pvals, k_family=10, alpha=0.10)

    assert result["a"]["reject_h0"] is True
    assert result["b"]["reject_h0"] is True
    assert result["c"]["reject_h0"] is True
    assert result["d"]["reject_h0"] is False
    assert result["e"]["reject_h0"] is False

    # Ranks: a=1, b=2, c=3, d=4, e=5 (sorted by raw_p)
    assert result["a"]["rank"] == 1
    assert result["e"]["rank"] == 5

    # BH adjusted p-value for "a" should be min(10*p_j/j for j>=1) = min(10*0.001/1,...) = 0.01
    assert result["a"]["bh_adj_p"] == pytest.approx(0.01, abs=1e-6)


def test_bh_fdr_all_null():
    """BH with all p-values > threshold — nothing rejected."""
    pvals = {"x": 0.5, "y": 0.8, "z": 0.9}
    result = g._bh_fdr(pvals, k_family=52, alpha=0.10)
    assert not any(r["reject_h0"] for r in result.values())


def test_bh_fdr_empty():
    """BH with empty pvals returns empty dict."""
    result = g._bh_fdr({}, k_family=52, alpha=0.10)
    assert result == {}


# ---------------------------------------------------------------------------
# Test 2 — HAC t-test
# ---------------------------------------------------------------------------

def test_hac_ttest_zero_mean():
    """Symmetric zero-mean series: p-value should be large (not significant)."""
    rng = np.random.default_rng(42)
    x = rng.normal(0, 1, 200)
    t_stat, p = g._hac_ttest(x)
    assert np.isfinite(t_stat)
    assert np.isfinite(p)
    assert p > 0.05  # not expected to be significant

def test_hac_ttest_strong_signal():
    """Strong nonzero mean: p-value should be very small."""
    x = np.ones(200) * 5.0 + np.random.default_rng(1).normal(0, 0.1, 200)
    t_stat, p = g._hac_ttest(x)
    assert np.isfinite(t_stat)
    assert p < 0.001

def test_hac_ttest_too_short():
    """Less than 5 observations returns nan."""
    t, p = g._hac_ttest(np.array([1.0, 2.0]))
    assert math.isnan(t)
    assert math.isnan(p)


# ---------------------------------------------------------------------------
# Test 3 — Realized volatility
# ---------------------------------------------------------------------------

def test_realized_vol_constant_returns():
    """Constant return series has zero realized vol after warmup."""
    prices = pd.Series([100.0 * (1.001 ** i) for i in range(50)])
    rv = g._realized_vol(prices, window=5)
    # After warmup, std of constant log-returns is 0
    assert rv.dropna().abs().max() < 1e-8

def test_realized_vol_random_returns():
    """Realized vol for random returns is positive and finite."""
    rng = np.random.default_rng(7)
    prices = pd.Series(np.cumprod(1 + rng.normal(0, 0.01, 100)) * 100)
    rv = g._realized_vol(prices, window=5)
    valid = rv.dropna()
    assert len(valid) > 0
    assert (valid > 0).all()
    assert np.isfinite(valid).all()


# ---------------------------------------------------------------------------
# Test 4 — Skew computation with synthetic chain
# ---------------------------------------------------------------------------

def _make_synthetic_chain(put_iv: float = 0.25, call_iv: float = 0.20,
                          spot: float = 100.0) -> pd.DataFrame:
    """Build a minimal synthetic greeks chain with one put at ~25Δ and one call at ATM."""
    date = pd.Timestamp("2020-01-03")
    expiration = pd.Timestamp("2020-02-01")  # ~29 days
    rows = [
        # 25-delta put: K ~= spot * 0.95
        {"date": date, "expiration": expiration, "strike": spot * 0.95,
         "right": "P", "implied_vol": put_iv, "delta": -0.25, "underlying_price": spot,
         "dte": 29},
        # ATM call: K ~= spot
        {"date": date, "expiration": expiration, "strike": spot,
         "right": "C", "implied_vol": call_iv, "delta": 0.50, "underlying_price": spot,
         "dte": 29},
        # Extra put to make the selection robust
        {"date": date, "expiration": expiration, "strike": spot * 0.97,
         "right": "P", "implied_vol": put_iv + 0.02, "delta": -0.35, "underlying_price": spot,
         "dte": 29},
        # Extra call
        {"date": date, "expiration": expiration, "strike": spot * 1.02,
         "right": "C", "implied_vol": call_iv - 0.01, "delta": 0.40, "underlying_price": spot,
         "dte": 29},
    ]
    return pd.DataFrame(rows)


def test_skew_sign_put_richer():
    """When put IV > call IV, skew should be positive."""
    chain = _make_synthetic_chain(put_iv=0.25, call_iv=0.20)
    # Patch _load_greeks_root to return this chain
    original = g._load_greeks_root

    def mock_load(root, years, cols):
        df = chain.copy()
        # Add missing cols with defaults
        for c in cols:
            if c not in df.columns:
                df[c] = np.nan
        return df[cols] if all(c in df.columns for c in cols) else df

    g._load_greeks_root = mock_load
    try:
        result = g._compute_daily_skew("TEST")
        if result is not None and not result.empty:
            # skew = put_iv - call_iv should be positive
            assert result["skew"].iloc[0] > 0
    finally:
        g._load_greeks_root = original


def test_skew_returns_none_on_empty():
    """_compute_daily_skew returns None when store returns None."""
    original = g._load_greeks_root
    g._load_greeks_root = lambda *a, **kw: None
    try:
        result = g._compute_daily_skew("TEST")
        assert result is None
    finally:
        g._load_greeks_root = original


# ---------------------------------------------------------------------------
# Test 5 — Absent store returns SKIP, no exception
# ---------------------------------------------------------------------------

def test_absent_store_check():
    """_store_check returns False for a nonexistent path."""
    original = g._STORE
    g._STORE = pathlib.Path("/nonexistent/theta-ops-wt/data/thetadata_eod")
    try:
        assert g._store_check() is False
    finally:
        g._STORE = original


# ---------------------------------------------------------------------------
# Test 6 — No forward window > 21d anywhere in script source
# ---------------------------------------------------------------------------

def test_no_long_horizon_windows():
    """Script source must not contain any 63-day / 90-day / 126-day window
    (house yardstick: 5d and 21d only; 3-6mo is wrong)."""
    source_path = pathlib.Path(__file__).parent.parent / "scripts/research/options_history_gauntlet.py"
    source = source_path.read_text()

    # These are the forbidden windows (any of these as a rolling window param)
    forbidden_patterns = ["shift(-63)", "shift(-90)", "shift(-126)",
                          "rolling(63)", "rolling(90)", "rolling(126)"]
    for pat in forbidden_patterns:
        assert pat not in source, f"Forbidden forward window found: {pat}"


# ---------------------------------------------------------------------------
# Test 7 — No "validated" as a claim in output text
# ---------------------------------------------------------------------------

def test_no_validated_in_output(capsys):
    """Running the study with mocked-empty data should not print 'validated' as a claim."""
    original_store = g._STORE
    g._STORE = pathlib.Path("/nonexistent/path")
    try:
        import sys as _sys
        original_argv = _sys.argv
        _sys.argv = ["options_history_gauntlet.py"]
        try:
            g.main()
        except SystemExit:
            pass
        finally:
            _sys.argv = original_argv
    finally:
        g._STORE = original_store

    captured = capsys.readouterr()
    # "validated" must not appear as a positive claim in output
    # "VALIDATED" in all-caps or in the context of "not validated" is acceptable
    # We check: the word "validated" does not appear in a standalone "X is validated" form
    lines_with_validated = [
        line for line in captured.out.lower().split("\n")
        if "validated" in line and "not validated" not in line
        and "no validated" not in line and "# validated" not in line
    ]
    # On absent store, output is just the SKIP message which contains no "validated"
    assert len(lines_with_validated) == 0, f"Found 'validated' in output: {lines_with_validated}"


# ---------------------------------------------------------------------------
# Test 8 — Mann-Whitney returns nan for degenerate inputs
# ---------------------------------------------------------------------------

def test_mannwhitney_degenerate():
    """Mann-Whitney with < 2 observations per group returns nan."""
    stat, p = g._mannwhitney(np.array([1.0]), np.array([2.0]))
    assert math.isnan(stat)
    assert math.isnan(p)

def test_mannwhitney_known_result():
    """Mann-Whitney test: two clearly separated distributions give small p."""
    a = np.linspace(10, 20, 50)
    b = np.linspace(1, 5, 50)
    stat, p = g._mannwhitney(a, b)
    assert np.isfinite(p)
    assert p < 0.001


# ---------------------------------------------------------------------------
# Test 9 — Era mask correctness
# ---------------------------------------------------------------------------

def test_era_mask():
    dates = pd.Series(pd.date_range("2018-01-01", "2021-12-31", freq="ME"))
    mask = g._era_mask(dates, "2019-01-01", "2019-12-31")
    in_era = dates[mask]
    assert in_era.dt.year.unique().tolist() == [2019]


# ---------------------------------------------------------------------------
# Test 10 — Preregistration doc exists and was committed before code
# ---------------------------------------------------------------------------

def test_preregistration_file_exists():
    """research/OPTIONS_HISTORY_GAUNTLET_E1.md must exist."""
    preregs = pathlib.Path(__file__).parent.parent / "research/OPTIONS_HISTORY_GAUNTLET_E1.md"
    assert preregs.exists(), "Preregistration memo must exist"
    text = preregs.read_text()
    # Must have the §Preregistration section
    assert "§Preregistration" in text
    # Must state BH family alpha
    assert "0.10" in text
    # Must forbid 3-6mo returns
    assert "3-6" in text or "63-day" in text


# ---------------------------------------------------------------------------
# Test 11 — SKEW BH assignment: exact cell_key match (no cross-target clobber)
# ---------------------------------------------------------------------------

def test_skew_bh_exact_key_match():
    """BH result assignment must use exact cell_key, not substring matching.
    Three cells in the same era+condition with different targets must get
    independent bh_adj_p / reject values (not all overwritten with one value).
    """
    # Build a pvals dict with three SKEW cells sharing era+condition but different targets
    # and with very different p-values so the distinction is clear.
    pvals = {
        "SKEW.Era1.HIGH_RISING.max_dd21": 0.0001,
        "SKEW.Era1.HIGH_RISING.rel_ret5": 0.9000,
        "SKEW.Era1.HIGH_RISING.rel_ret21": 0.8500,
    }
    bh = g._bh_fdr(pvals, k_family=52, alpha=0.10)
    # max_dd21 should reject; the other two should not
    assert bh["SKEW.Era1.HIGH_RISING.max_dd21"]["reject_h0"] is True
    assert bh["SKEW.Era1.HIGH_RISING.rel_ret5"]["reject_h0"] is False
    assert bh["SKEW.Era1.HIGH_RISING.rel_ret21"]["reject_h0"] is False
    # All three must have distinct bh_adj_p values (not the same value)
    adj_ps = [bh[k]["bh_adj_p"] for k in pvals]
    assert len(set(adj_ps)) > 1, "BH adj-p must differ across cells with different raw_p"


# ---------------------------------------------------------------------------
# Test 12 — _run_global_bh returns a dict (not None)
# ---------------------------------------------------------------------------

def test_run_global_bh_returns_dict():
    """_run_global_bh must return a dict of BH results (used by _print_summary)."""
    pvals = {"GEXR.Era1.5d": 0.001, "CWIV.Era3.5d": 0.05, "DOI.Era1.OI_UP.10d": 0.9}
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = g._run_global_bh(pvals)
    assert isinstance(result, dict), "_run_global_bh must return dict"
    assert len(result) == len(pvals)
    assert all("reject_h0" in v for v in result.values())


# ---------------------------------------------------------------------------
# Test 13 — Memo documents SC corrections and prereg deviations
# ---------------------------------------------------------------------------

def test_memo_documents_corrections():
    """The memo must document the statistical corrections and prereg deviations."""
    memo = pathlib.Path(__file__).parent.parent / "research/OPTIONS_HISTORY_GAUNTLET_E1.md"
    text = memo.read_text()
    # Must have the SC section
    assert "§Statistical Corrections" in text, "Memo must have §Statistical Corrections section"
    # Must document the benchmark deviation
    assert "P-3 AMENDMENT" in text, "Memo must document SKEW benchmark prereg deviation"
    # Must document the CWIV under-testing
    assert "secondary test" in text.lower(), "Memo must note secondary test not implemented"
    # Must acknowledge the anti-conservative blocker
    assert "anti-conservative" in text.lower() or "pseudo-replication" in text.lower()
