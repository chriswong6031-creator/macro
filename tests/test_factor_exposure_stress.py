"""Stress-conditioned factor covariance (WRI W1).

The math that must hold: (1) the orthogonalization transform can be FIT on one window
and APPLIED to another, reproducing the in-window orthogonalization exactly and keeping
extended data in the SAME orthogonal basis (so the client's b'·F_stress·b never mixes
bases); (2) a stress covariance estimated on worst-quartile market days captures
tail-only co-movement that calm-day covariance misses; (3) the emit is strictly additive
— every pre-existing key survives, the new keys are well-formed and symmetric, n_stress
is consistent with the quantile; (4) a scrap sample emits stress_meta.available=False and
no covariance rather than shipping noise. Pure-math on synthetic data; the real export is
smoke-checked opportunistically. (engine/factor_exposure.py::factor_cov_stress.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import factor_exposure as fe


def _idx(n: int):
    return pd.date_range("2016-01-01", periods=n, freq="B")


# --------------------------------------------------------------------------- #
# 1. synthetic positive control — down-day-only co-movement
# --------------------------------------------------------------------------- #
def test_stress_offdiag_exceeds_calm_when_comovement_is_tail_only():
    """Two factors uncorrelated on normal days but strongly co-moving on down-market
    days: the stress-window covariance off-diagonal must dwarf the calm off-diagonal.

    Construction: `mkt` is the market. On down-market days (mkt<0) `oil` and `btc` both
    pick up a large SHARED shock of FIXED variance (gated on down days, uncorrelated with
    the size of the market move so it does not leak into the mkt column); on up days they
    are independent noise. The transform is fit on the calm-ish trailing 252 window where
    oil/btc barely co-move, so oil's peel of btc is ~0 and the tail co-movement survives
    into the orthogonal residuals — visible only when the covariance is conditioned on the
    worst quartile of market days. (btc follows oil in FACTOR_ORDER, so this is also the
    honest test that a tail-only shared component is NOT removed by the calm-fit peel.)"""
    rng = np.random.default_rng(11)
    n = 900
    m = rng.normal(0, 0.011, n)
    down = m < 0
    shock = rng.normal(0, 0.02, n)                        # fixed-variance shared tail shock
    common = np.where(down, shock, 0.0)                   # present ONLY on down days
    oil = common + rng.normal(0, 0.004, n)
    btc = common + rng.normal(0, 0.004, n)
    F = pd.DataFrame({"mkt": m, "oil": oil, "btc": btc}, index=_idx(n))

    calm = fe.factor_cov(F, window=n)                     # covariance on ALL days (annualized)
    stress = fe.factor_cov_stress(F, fit_window=252, stress_window=756,
                                  quantile=0.25, min_stress_rows=400, min_stress_days=60)
    assert stress["available"] is True
    assert stress["n_stress"] == 189                      # 25% of 756 (masterplan anchor)
    scov = stress["cov"]

    calm_ob = abs(float(calm.loc["oil", "btc"]))
    stress_ob = float(scov.loc["oil", "btc"])
    # tail-only co-movement, the core product claim:
    #  (a) a materially POSITIVE stress off-diagonal...
    assert stress_ob > 0.002
    #  (b) ...an order of magnitude above the near-zero calm off-diagonal (the whole
    #      point: co-movement measured on all days evaporates vs the worst days)...
    assert stress_ob > 10.0 * calm_ob
    #  (c) ...landing on the oil/btc pair, not smeared into the (peeled-out) market column.
    assert stress_ob > 3.0 * abs(float(scov.loc["mkt", "oil"]))


def test_stress_and_calm_agree_when_no_tail_comovement():
    """Negative control: with NO regime-dependent co-movement (oil/btc independent on all
    days), BOTH the calm and stress oil/btc off-diagonals sit near zero — the stress lens
    invents nothing when there is no tail structure to find."""
    rng = np.random.default_rng(12)
    n = 900
    m = rng.normal(0, 0.011, n)
    F = pd.DataFrame({"mkt": m,
                      "oil": rng.normal(0, 0.012, n),      # independent of btc, all regimes
                      "btc": rng.normal(0, 0.02, n)}, index=_idx(n))
    calm = fe.factor_cov(F, window=n)
    stress = fe.factor_cov_stress(F, fit_window=252, stress_window=756, quantile=0.25)
    scov = stress["cov"]
    calm_corr = abs(float(calm.loc["oil", "btc"])) / np.sqrt(
        float(calm.loc["oil", "oil"]) * float(calm.loc["btc", "btc"]))
    stress_corr = abs(float(scov.loc["oil", "btc"])) / np.sqrt(
        float(scov.loc["oil", "oil"]) * float(scov.loc["btc", "btc"]))
    assert calm_corr < 0.15 and stress_corr < 0.25        # both ~uncorrelated, no blow-up


# --------------------------------------------------------------------------- #
# 2. basis consistency — fit on a window, apply to extended data
# --------------------------------------------------------------------------- #
def test_fit_apply_reproduces_in_window_orthogonalization_exactly():
    """orthogonalize_apply(F, fit(F)) == orthogonalize_factors(F) to machine precision,
    and applying a window-fit transform to an EXTENDED frame reproduces the in-window
    orthogonalization on the overlap — the invariant that keeps the stress cov in the
    shipped-betas basis."""
    rng = np.random.default_rng(13)
    n = 800
    m = rng.normal(0, 0.01, n)
    F = pd.DataFrame({
        "mkt": m,
        "growth": 0.9 * m + rng.normal(0, 0.003, n),
        "size": 0.7 * m + rng.normal(0, 0.004, n),
        "oil": rng.normal(0, 0.012, n),
    }, index=_idx(n))

    # (a) fit+apply on the SAME frame is byte-identical to the convenience wrapper
    direct = fe.orthogonalize_factors(F)
    applied = fe.orthogonalize_apply(F, fe.orthogonalize_fit(F))
    assert float((direct - applied).abs().to_numpy().max()) < 1e-12

    # (b) fit on trailing 252, apply to trailing 756: the last-252 overlap reproduces the
    #     in-window orthogonalization EXACTLY (same fixed transform, not a re-fit)
    win, sw = 252, 756
    transform = fe.orthogonalize_fit(F.tail(win))
    g_ext = fe.orthogonalize_apply(F.tail(sw), transform)
    g_in = fe.orthogonalize_factors(F.tail(win))
    assert float((g_ext.tail(win) - g_in).abs().to_numpy().max()) < 1e-12

    # (c) in-window columns are pairwise orthogonal
    c = g_in.corr().abs().to_numpy().copy()
    np.fill_diagonal(c, 0.0)
    assert float(c.max()) < 1e-9

    # (d) re-fitting on the 756 window gives a DIFFERENT basis (the trap the design avoids)
    refit = fe.orthogonalize_apply(F.tail(sw), fe.orthogonalize_fit(F.tail(sw)))
    assert float((refit.tail(win) - g_in).abs().to_numpy().max()) > 1e-6


def test_fit_returns_sequential_coefficients_in_factor_order():
    """The fitted transform exposes coeffs per FACTOR_ORDER: mkt (first) has no priors;
    each later factor carries a slope against every already-orthogonalized prior."""
    rng = np.random.default_rng(14)
    n = 400
    m = rng.normal(0, 0.01, n)
    F = pd.DataFrame({"mkt": m, "growth": 0.8 * m + rng.normal(0, 0.003, n),
                      "size": 0.5 * m + rng.normal(0, 0.004, n)}, index=_idx(n))
    tr = fe.orthogonalize_fit(F)
    assert tr["order"] == ["mkt", "growth", "size"]
    assert tr["coeffs"]["mkt"] == {}                      # market stays raw
    assert set(tr["coeffs"]["growth"]) == {"mkt"}
    assert set(tr["coeffs"]["size"]) == {"mkt", "growth"}
    # growth's fitted slope on mkt recovers the ~0.8 loading
    assert abs(tr["coeffs"]["growth"]["mkt"] - 0.8) < 0.1


# --------------------------------------------------------------------------- #
# 3. stress-day selection consistency
# --------------------------------------------------------------------------- #
def test_stress_days_match_raw_mkt_quantile():
    """n_stress and mkt_cut_daily are consistent with the raw-mkt quantile over the
    stress window: the cut equals the empirical quantile and n_stress equals the count
    at-or-below it (≈ quantile × window)."""
    rng = np.random.default_rng(15)
    n = 900
    F = pd.DataFrame({"mkt": rng.normal(0, 0.011, n),
                      "oil": rng.normal(0, 0.012, n),
                      "btc": rng.normal(0, 0.02, n)}, index=_idx(n))
    sw, q = 756, 0.25
    stress = fe.factor_cov_stress(F, fit_window=252, stress_window=sw, quantile=q)
    mkt_win = F["mkt"].tail(sw)
    assert stress["window_d"] == sw
    assert abs(stress["mkt_cut_daily"] - round(float(mkt_win.quantile(q)), 5)) < 1e-9
    assert stress["n_stress"] == int((mkt_win <= float(mkt_win.quantile(q))).sum())
    # roughly a quarter of the window
    assert 0.20 * sw <= stress["n_stress"] <= 0.30 * sw


# --------------------------------------------------------------------------- #
# 4. schema / backward-compat on the real export
# --------------------------------------------------------------------------- #
def test_compute_exposure_schema_strictly_additive():
    """The stress emit is strictly additive: every pre-existing key is still present and
    unchanged in shape, the new keys are well-formed, the stress matrix is symmetric and
    shares the factor_cov key order, and stress_meta is consistent with the quantile."""
    out = fe.compute_exposure()
    if out is None:                                       # no store in this env — skip
        return
    # (a) every pre-existing top-level key survives
    for k in ("as_of", "window_d", "n", "note", "factors", "factor_vol_ann",
              "factor_cov", "betas", "most_idiosyncratic"):
        assert k in out, f"pre-existing key {k!r} dropped"
    # (b) stress_meta ALWAYS present (available true/false)
    assert "stress_meta" in out and "available" in out["stress_meta"]

    if not out["stress_meta"]["available"]:               # guard path in this env
        assert "factor_cov_stress" not in out and "factor_vol_stress_ann" not in out
        assert "reason" in out["stress_meta"]
        return

    keys = list(out["factor_cov"].keys())
    scov = out["factor_cov_stress"]
    svol = out["factor_vol_stress_ann"]
    meta = out["stress_meta"]

    # (c) stress cov shares the factor_cov key set / order and is square + symmetric
    assert list(scov.keys()) == keys
    for a in keys:
        assert list(scov[a].keys()) == keys
        for b in keys:
            assert abs(scov[a][b] - scov[b][a]) < 1e-9
    # (d) stress vols are the sqrt of the stress-cov diagonal (rounding-tolerant)
    for k in keys:
        assert abs(svol[k] - round(float(np.sqrt(max(scov[k][k], 0.0))), 4)) < 5e-4
    # (e) meta is self-consistent
    assert meta["quantile"] == 0.25
    assert isinstance(meta["n_stress"], int) and meta["n_stress"] >= 60
    assert meta["n_stress"] <= meta["window_d"]
    assert "worst-quartile" in meta["note"] and "idiosyncratic" in meta["note"]
    # n_stress must be ~a quarter of the actual window (quantile selection)
    assert 0.15 * meta["window_d"] <= meta["n_stress"] <= 0.35 * meta["window_d"]


# --------------------------------------------------------------------------- #
# 5. small-sample guard
# --------------------------------------------------------------------------- #
def test_guard_abstains_on_tiny_history():
    """A stress window with too few rows / stress days emits stress_meta.available=False
    and NO covariance — never a matrix fit on a scrap sample."""
    rng = np.random.default_rng(16)
    n = 120                                               # far below any usable window
    F = pd.DataFrame({"mkt": rng.normal(0, 0.011, n),
                      "oil": rng.normal(0, 0.012, n)}, index=_idx(n))
    stress = fe.factor_cov_stress(F, fit_window=252, stress_window=756,
                                  quantile=0.25, min_stress_rows=400, min_stress_days=60)
    assert stress["available"] is False
    assert "cov" not in stress
    assert stress["window_d"] == n                        # window shrunk to what exists
    assert "reason" in stress


def test_guard_fires_when_stress_days_below_floor():
    """Enough rows but the stress-day floor is not met → abstain (no cov)."""
    rng = np.random.default_rng(17)
    n = 500
    F = pd.DataFrame({"mkt": rng.normal(0, 0.011, n),
                      "oil": rng.normal(0, 0.012, n)}, index=_idx(n))
    # quantile 0.25 of 500 rows ≈ 125 stress days, so force the floor high to trip it
    stress = fe.factor_cov_stress(F, fit_window=252, stress_window=500,
                                  quantile=0.25, min_stress_rows=400, min_stress_days=200)
    assert stress["available"] is False and "cov" not in stress


def test_guard_path_through_compute_exposure_synthetic(monkeypatch):
    """End-to-end guard: a tiny synthetic factor frame drives compute_exposure() to emit
    stress_meta.available=False with no stress-cov key, while the pre-existing keys still
    ship. Patches factor_frame + the close matrix so the whole export runs on ~130 rows."""
    rng = np.random.default_rng(18)
    n = 130
    idx = _idx(n)
    F = pd.DataFrame({"mkt": rng.normal(0, 0.011, n),
                      "growth": rng.normal(0, 0.01, n),
                      "oil": rng.normal(0, 0.012, n)}, index=idx)
    # a small close matrix aligned to F so stock_betas has enough obs at min_obs floor
    px = pd.DataFrame({f"S{i}": (1 + rng.normal(0, 0.02, n)).cumprod() for i in range(6)},
                      index=idx)

    monkeypatch.setattr(fe, "factor_frame", lambda asof=None: F)
    monkeypatch.setattr(fe, "_closes", lambda: px)
    monkeypatch.setattr(fe, "_etf_closes", lambda: pd.DataFrame())
    monkeypatch.setattr(fe, "_names_sectors", lambda: {})
    # loosen the min-obs floors so betas estimate on the short synthetic window
    monkeypatch.setattr(fe, "_cfg", lambda: {
        "window_d": 120, "min_obs": 100, "min_factor_obs": 120, "max_abs_beta": 5.0,
        "top_n_idio": 3, "stress_window_d": 756, "stress_quantile": 0.25})

    out = fe.compute_exposure()
    assert out is not None
    assert out["stress_meta"]["available"] is False
    assert "factor_cov_stress" not in out and "factor_vol_stress_ann" not in out
    # pre-existing contract intact even on the guard path
    for k in ("factor_cov", "factor_vol_ann", "betas", "factors"):
        assert k in out
