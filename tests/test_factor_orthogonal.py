"""Löwdin factor orthogonalization (Phase 3 additive): decorrelate the factor set so
the composite stops double-counting overlapping factors (value/quality, low-vol/low-beta).
Pure-math on synthetic correlated factors — no network."""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.factor_orthogonal import (orthogonal_composite, orthogonalize,
                                       overlap_diagnostics)


def _correlated_factors(n: int = 500, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    latent = rng.normal(size=n)                       # shared driver
    return pd.DataFrame({
        "a": latent + 0.5 * rng.normal(size=n),
        "b": latent + 0.6 * rng.normal(size=n),       # a,b,c all load on latent
        "c": latent + 0.8 * rng.normal(size=n),
        "d": rng.normal(size=n),                       # independent
    })


def _mean_abs_offdiag(df: pd.DataFrame) -> float:
    c = df.corr().values
    n = c.shape[0]
    return float(np.mean(np.abs(c[~np.eye(n, dtype=bool)])))


def test_orthogonalize_decorrelates():
    F = _correlated_factors()
    assert _mean_abs_offdiag(F) > 0.25                # genuinely correlated to start
    O = orthogonalize(F)
    assert _mean_abs_offdiag(O) < 0.02                # ~uncorrelated after
    assert list(O.columns) == list(F.columns) and O.shape == F.shape


def test_orthogonal_composite_is_standardized_and_gated():
    F = _correlated_factors()
    oc = orthogonal_composite(F, min_legs=3)
    assert abs(oc.mean()) < 1e-6 and abs(oc.std(ddof=0) - 1.0) < 1e-6
    # a row missing too many legs -> NaN
    F2 = F.copy()
    F2.loc[0, ["a", "b"]] = np.nan                     # only 2 legs left on row 0
    assert pd.isna(orthogonal_composite(F2, min_legs=3).iloc[0])


def test_overlap_diagnostics_shows_redundancy_removed():
    d = overlap_diagnostics(_correlated_factors())
    assert d["mean_abs_corr_orth"] < d["mean_abs_corr_raw"]
    assert any(p["a"] in ("a", "b", "c") and p["b"] in ("a", "b", "c") for p in d["top_pairs"])


def test_thin_input_returns_unchanged():
    F = _correlated_factors(n=10)                      # < 3*ncols rows -> too thin
    out = orthogonalize(F)
    pd.testing.assert_frame_equal(out, F)
    assert orthogonalize(pd.DataFrame({"only": [1.0, 2.0, 3.0]})).shape[1] == 1  # <2 cols
