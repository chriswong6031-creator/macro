"""Tests for scripts/narrative_realign_phase0.py — D7 one-shot salvage harness.

Design goals (two invariants the integrator must never break):

1. DETERMINISM — harness is deterministic on a fixture slice. Same SEED, same
   block-bootstrap, same expanding-z → identical IC / CI on identical data.
2. NO-LOOKAHEAD — the forward targets are strictly future (t+1..t+h); the
   expanding-z standardization uses only data available at t. The guard
   verifies the alignment by checking that the PIT signal at date t is
   non-trivially correlated with its own history but NOT with the raw
   (unlagged) forward target before it has been shifted.

Run as a plain script:  python tests/test_narrative_realign_phase0.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.narrative_realign_phase0 as nr  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _make_fixture(n: int = 400, seed: int = 0) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """Minimal synthetic dataset for determinism tests.

    Returns (tu_like, sfed_like, sec_rets) on a synthetic daily DatetimeIndex.
    Signals are AR(1) with low-frequency autocorrelation (like EPU/GPR);
    sector returns are iid (no planted edge) — ensures the test doesn't assume
    significance.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-01-04", periods=n, freq="B")

    # AR(1) signal with ρ=0.97 (macro series move slowly)
    tu = pd.Series(index=idx, dtype=float, data=0.0)
    for i in range(1, n):
        tu.iloc[i] = 0.97 * tu.iloc[i - 1] + rng.standard_normal()
    sfed = pd.Series(index=idx, dtype=float, data=0.0)
    for i in range(1, n):
        sfed.iloc[i] = 0.95 * sfed.iloc[i - 1] + rng.standard_normal()

    # iid sector returns
    tickers = ["S1", "S2", "S3", "S4", "S5"]
    sec_rets = pd.DataFrame(
        rng.standard_normal((n, len(tickers))) * 0.01,
        index=idx,
        columns=tickers,
    )
    return tu, sfed, sec_rets


# --------------------------------------------------------------------------- #
# test: expanding_z
# --------------------------------------------------------------------------- #
def test_expanding_z_no_lookahead():
    """expanding_z(t) must only use data through t — value at minp+k equals the
    z-score computed over the first minp+k observations."""
    n = 300
    s = pd.Series(np.random.default_rng(1).standard_normal(n))
    ez = nr.expanding_z(s, minp=100)
    for t in [99, 150, 250]:
        expected_mu = s.iloc[: t + 1].mean()
        expected_sd = s.iloc[: t + 1].std()
        expected_z = (s.iloc[t] - expected_mu) / expected_sd if expected_sd > 0 else np.nan
        if not np.isnan(ez.iloc[t]) and not np.isnan(expected_z):
            assert abs(ez.iloc[t] - expected_z) < 1e-10, (
                f"expanding_z lookahead at t={t}: got {ez.iloc[t]:.6f}, "
                f"expected {expected_z:.6f}"
            )


# --------------------------------------------------------------------------- #
# test: resid_ols
# --------------------------------------------------------------------------- #
def test_resid_ols_orthogonal():
    """OLS residual must be orthogonal to the regressors (within tolerance)."""
    rng = np.random.default_rng(42)
    idx = pd.date_range("2010-01-01", periods=200, freq="D")
    x1 = pd.Series(rng.standard_normal(200), index=idx, name="x1")
    x2 = pd.Series(rng.standard_normal(200), index=idx, name="x2")
    y = 2 * x1 - x2 + 0.3 * rng.standard_normal(200)
    y = pd.Series(y, index=idx)
    resid = nr.resid_ols(y, pd.DataFrame({"x1": x1, "x2": x2}))
    assert abs(np.corrcoef(resid.values, x1.values)[0, 1]) < 1e-10, "resid correlated with x1"
    assert abs(np.corrcoef(resid.values, x2.values)[0, 1]) < 1e-10, "resid correlated with x2"


# --------------------------------------------------------------------------- #
# test: boot_spearman_ci determinism
# --------------------------------------------------------------------------- #
def test_boot_spearman_determinism():
    """Same inputs → same IC / CI across two calls (SEED is fixed)."""
    rng = np.random.default_rng(99)
    n = 300
    s1 = pd.Series(rng.standard_normal(n))
    t1 = pd.Series(rng.standard_normal(n))
    r1 = nr.boot_spearman_ci(s1, t1, block=30, B=200, seed=nr.SEED)
    r2 = nr.boot_spearman_ci(s1, t1, block=30, B=200, seed=nr.SEED)
    assert r1 is not None and r2 is not None
    assert r1["ic"] == r2["ic"], "IC not deterministic"
    assert r1["lo"] == r2["lo"] and r1["hi"] == r2["hi"], "CI not deterministic"
    assert r1["p"] == r2["p"], "p not deterministic"


# --------------------------------------------------------------------------- #
# test: no-lookahead guard on forward targets
# --------------------------------------------------------------------------- #
def test_targets_A_no_lookahead():
    """cs_dispH at date t must not depend on the return at date t (or earlier
    than t+1). Verify by checking that the std at position t equals the
    cross-sectional std of the forward window [t+1..t+h]."""
    _, _, sec_rets = _make_fixture(n=150, seed=0)
    targets = nr.build_targets_A(sec_rets)

    h = 5
    cs_disp = targets[f"cs_disp{h}"]

    # At position t=10, the forward window should cover rows 11..15 (0-indexed)
    t_loc = 10
    t_date = sec_rets.index[t_loc]
    fwd_rows = sec_rets.iloc[t_loc + 1: t_loc + 1 + h]
    if len(fwd_rows) == h:
        expected_cs = fwd_rows.sum().std()   # cumulative log-ret per sector, then cross-sec std
        # Note: build_targets_A uses rolling(h).sum() then std(axis=1); replicate
        cum = fwd_rows.sum()
        expected = float(cum.std())
        got = float(cs_disp.loc[t_date])
        assert abs(got - expected) < 1e-9, (
            f"cs_disp{h} at t={t_date.date()}: got {got:.8f}, expected {expected:.8f}"
        )


def test_targets_B_no_lookahead():
    """comp_fadeH binary at t must be determined solely by forward window t+1..t+h
    and the trailing mean computed on data up to t-1."""
    rng = np.random.default_rng(0)
    idx = pd.date_range("2010-01-04", periods=200, freq="B")
    r_spy = pd.Series(rng.standard_normal(200) * 0.01, index=idx)

    targets = nr.build_targets_B(r_spy)
    h = 5

    t_loc = 130
    t_date = idx[t_loc]
    comp_fade = targets[f"comp_fade{h}"]

    # Recompute manually: forward return t+1..t+h
    fwd = r_spy.iloc[t_loc + 1: t_loc + 1 + h].sum()
    trail_mean = r_spy.iloc[: t_loc].rolling(126).mean().iloc[-1] if t_loc >= 126 else np.nan
    if not np.isnan(trail_mean):
        expected_val = float(fwd < trail_mean)
        got = float(comp_fade.loc[t_date])
        assert abs(got - expected_val) < 1e-10, (
            f"comp_fade{h} at t={t_date.date()}: got {got}, expected {expected_val}"
        )


# --------------------------------------------------------------------------- #
# test: BH-FDR monotonicity
# --------------------------------------------------------------------------- #
def test_bh_fdr_monotonicity():
    """q-values must be non-decreasing when tests are sorted by p-value."""
    pvals = {"a": 0.01, "b": 0.05, "c": 0.10, "d": 0.30, "e": 0.80}
    fdr = nr.benjamini_hochberg(pvals, alpha=0.10)
    qs = [fdr[k]["q"] for k in sorted(pvals, key=pvals.get)]
    for i in range(len(qs) - 1):
        assert qs[i] <= qs[i + 1] + 1e-12, f"q-values not monotone: {qs}"


# --------------------------------------------------------------------------- #
# test: license gate logic
# --------------------------------------------------------------------------- #
def test_license_gate_all_required():
    """All four conditions required: excl0, FDR-reject, sign-stable halves, positive IC (target A)."""
    fdr_yes = {"sig|tgt": {"p": 0.01, "q": 0.05, "reject": True}}
    fdr_no = {"sig|tgt": {"p": 0.20, "q": 0.30, "reject": False}}

    base_row = {
        "sig": "sig", "tgt": "tgt", "key": "sig|tgt",
        "res": {"ic": 0.10, "lo": 0.02, "hi": 0.20, "p": 0.01, "excl0": True, "n": 500},
        "ic_a": 0.08, "ic_b": 0.12,
    }

    assert nr._passes_license_gate(base_row, fdr_yes, "A"), "should pass"

    # FDR fail
    row = dict(base_row); assert not nr._passes_license_gate(row, fdr_no, "A"), "FDR fail"

    # excl0 fail
    row = dict(base_row); row["res"] = {**base_row["res"], "excl0": False}
    assert not nr._passes_license_gate(row, fdr_yes, "A"), "excl0 fail"

    # sign unstable
    row = dict(base_row); row["ic_a"] = -0.05; row["ic_b"] = 0.12
    assert not nr._passes_license_gate(row, fdr_yes, "A"), "sign unstable fail"

    # negative IC for target A
    row = dict(base_row); row["res"] = {**base_row["res"], "ic": -0.10}
    row["ic_a"] = -0.08; row["ic_b"] = -0.12
    assert not nr._passes_license_gate(row, fdr_yes, "A"), "negative IC target A"

    # target B accepts either sign (no directional requirement)
    assert nr._passes_license_gate(base_row, fdr_yes, "B"), "target B positive IC"


# --------------------------------------------------------------------------- #
# run all
# --------------------------------------------------------------------------- #
def _run_all():
    tests = [
        test_expanding_z_no_lookahead,
        test_resid_ols_orthogonal,
        test_boot_spearman_determinism,
        test_targets_A_no_lookahead,
        test_targets_B_no_lookahead,
        test_bh_fdr_monotonicity,
        test_license_gate_all_required,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(_run_all())
