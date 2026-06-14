"""Honest-validation primitives shared by every calibrator (vector / commodity /
forex). Two jobs, both pure-numpy (no scipy/sklearn) so the data-bot env stays thin:

  1. backtest_core() — the allocation→returns engine with a turnover-scaled one-way
     transaction cost. A position acts NEXT bar (shift(1), no look-ahead); cost is
     charged on each unit of |Δpos|, so a full 0→1→0 round trip pays 2×cost_bps.
     It returns the raw gross/net/hold return series each per-asset backtest then
     summarizes in its own units (TRADING_YEAR differs; key naming differs —
     vector ships `hodl_*`, commodity ships `hold_*`). Keeping ONE cost engine
     means the three calibrators can't drift apart on how cost is applied.

  2. deflated_sharpe() — the multiple-testing haircut (Bailey & López de Prado
     2014). A raw Sharpe picked as the BEST of N tried configs is upward-biased;
     the DSR deflates it for (i) the number of independent trials N, (ii) sample
     length T, and (iii) the return distribution's skew and (fat) kurtosis,
     returning P(true Sharpe > 0). This is the one de-Prado tool that genuinely
     applies to a solo free-data signal hunt: the real risk is silently trying
     many variants and reporting the winner.

These lived inline in scripts/calibrate_vector.py first; factored here so the
commodity and forex calibrators import them rather than keeping divergent copies.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

EULER_GAMMA = 0.5772156649015329


# --------------------------------------------------------------------------- #
# allocation backtest core (turnover-scaled transaction cost)
# --------------------------------------------------------------------------- #
def backtest_core(close: pd.Series, alloc: pd.Series, cost_bps: float = 0.0) -> dict:
    """Next-bar allocation engine with a one-way transaction cost.

    `cost_bps` is the ONE-WAY cost (spread + fee/slippage) in basis points,
    charged on each unit of position turnover |Δpos|. Returns the building-block
    series the per-asset backtests summarize — the headline strat is NET of cost,
    `gross` exposes the costless path, `turnover` drives the drag. Works for
    long/flat (alloc ∈ [0,1]) and long/short (alloc ∈ [-1,1]) the same way.
    cost_bps default 0.0 keeps legacy callers gross-of-cost.
    """
    ret = close.pct_change().fillna(0)
    pos = alloc.shift(1).reindex(ret.index).ffill().fillna(0)   # act next bar
    turnover = pos.diff().abs().fillna(0.0)                      # |Δpos|, day-1 ramp from 0
    cost = (cost_bps / 1e4) * turnover
    gross = pos * ret
    net = gross - cost
    hold = ret
    years = (close.index[-1] - close.index[0]).days / 365.25
    return {"ret": ret, "pos": pos, "turnover": turnover,
            "gross": gross, "net": net, "hold": hold, "years": years}


# --------------------------------------------------------------------------- #
# normal CDF / inverse-CDF (Acklam) — no scipy
# --------------------------------------------------------------------------- #
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF — Acklam's rational approximation (abs err
    < 1.2e-9 over the whole range), so we need no scipy."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= phigh:
        q = p - 0.5
        r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


# --------------------------------------------------------------------------- #
# return moments + Deflated Sharpe Ratio
# --------------------------------------------------------------------------- #
def ret_moments(r: pd.Series):
    """(per-period Sharpe, skew, Pearson-kurtosis, n) of a return series — the
    inputs the DSR consumes. Pearson kurtosis (normal = 3), ddof=1 like sharpe()."""
    r = r.dropna()
    if len(r) < 3:
        return None
    mu, sd = r.mean(), r.std(ddof=1)
    if not sd:
        return None
    z = (r - mu) / sd
    return mu / sd, float((z**3).mean()), float((z**4).mean()), int(len(r))


# legacy alias — scripts.calibrate_vector re-exported `_ret_moments`
_ret_moments = ret_moments


def deflated_sharpe(sr_daily, skew, kurt, T, n_trials, sr_variance=None,
                    trading_year: float = 252) -> dict | None:
    """DSR for a strategy selected as the best of `n_trials` configs.
    `sr_daily` = its per-period Sharpe; `sr_variance` = cross-trial variance of the
    per-period Sharpes (if None, fall back to the SR-estimator's own variance as a
    conservative proxy). `trading_year` only scales the *_annual report fields — the
    DSR probability itself is annualization-invariant."""
    if sr_daily is None or T is None or T < 3 or skew is None or kurt is None:
        return None
    var_scaler = 1.0 - skew * sr_daily + ((kurt - 1.0) / 4.0) * sr_daily * sr_daily
    var_scaler = max(var_scaler, 1e-9)
    # Floor the cross-trial SR variance at the null SR-sampling variance (~1/T):
    # a handful of near-duplicate allocation variants understates true trial
    # dispersion, which would make the SR0 haircut too lenient. max() keeps it honest.
    proxy = var_scaler / (T - 1)
    sr_variance = proxy if (sr_variance is None or sr_variance <= 0) else max(sr_variance, proxy)
    N = max(int(n_trials), 1)
    if N == 1:
        sr0 = 0.0
    else:
        z1, z2 = _norm_ppf(1 - 1.0 / N), _norm_ppf(1 - 1.0 / (N * np.e))
        sr0 = np.sqrt(sr_variance) * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)
    dsr = _norm_cdf((sr_daily - sr0) * np.sqrt(T - 1) / np.sqrt(var_scaler))
    ann = float(np.sqrt(trading_year))
    return {"dsr": round(float(dsr), 4),
            "sr_daily": round(float(sr_daily), 6), "sr_annual": round(float(sr_daily) * ann, 2),
            "sr0_daily": round(float(sr0), 6), "sr0_annual": round(float(sr0) * ann, 2),
            "n_trials": N, "T": int(T), "skew": round(float(skew), 3), "kurt": round(float(kurt), 3)}


def dsr_verdict(dsr: float) -> str:
    """Shared wording for the DSR pass/marginal/fail bands (≥0.95 / ≥0.90 / else)."""
    return ("SURVIVES multiple-testing (DSR≥0.95)" if dsr >= 0.95
            else "MARGINAL (0.90≤DSR<0.95)" if dsr >= 0.90
            else "FAILS multiple-testing haircut (DSR<0.90)")


# --------------------------------------------------------------------------- #
# STABILITY GATES (shared) — purged CV, block-bootstrap CI, probability
# calibration, collinearity. Pure numpy/pandas. (Vector D-vec-GATES; see DECISIONS.)
# --------------------------------------------------------------------------- #
def purged_folds(index, k: int, embargo: int) -> dict:
    """K contiguous time folds with a label-leak guard: within each fold drop the
    trailing `embargo` rows, because a forward label (up to `embargo` days) computed
    near a fold's right edge peeks into the NEXT fold. This is the purge/embargo that
    a single split_date lacks (its boundary row's 90d label leaks across the split).
    Returns {fold1: DatetimeIndex, ...}; degrades to one embargoed block if too short."""
    n = len(index)
    if k < 2 or n < k * (embargo + 5):
        return {"fold1": index[: max(0, n - embargo)]}
    bounds = np.linspace(0, n, k + 1).astype(int)
    out = {}
    for i in range(k):
        lo, hi = int(bounds[i]), int(bounds[i + 1])
        out[f"fold{i + 1}"] = index[lo: max(lo, hi - embargo)]
    return out


def _sharpe(r, ann: int) -> float:
    sd = float(np.std(r))
    return float(np.mean(r) / sd * math.sqrt(ann)) if sd else float("nan")


def _maxdd(r) -> float:
    eq = np.cumprod(1.0 + np.asarray(r, float))
    peak = np.maximum.accumulate(eq)
    return float(np.min(eq / peak - 1.0))


def block_bootstrap_ci(returns, block: int = 21, B: int = 5000, seed: int = 7,
                       ann: int = 365) -> dict:
    """Circular block bootstrap of a daily strategy-return series → 95% CI on the
    annualized Sharpe and the max-drawdown. Blocks preserve autocorrelation; the
    point estimates ship with a CI instead of a bare number (the allocation variants
    were point estimates with no interval). Returns {} if the series is too short."""
    r = np.asarray(returns.dropna() if hasattr(returns, "dropna") else returns, float)
    n = len(r)
    if n < max(block * 3, 60):
        return {}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    sh = np.empty(B)
    dd = np.empty(B)
    starts_grid = np.arange(block)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + starts_grid[None, :]).ravel()[:n] % n
        s = r[idx]
        sh[k] = _sharpe(s, ann)
        dd[k] = _maxdd(s)
    def q(a, mul=1.0, nd=2):
        return [round(float(np.percentile(a, p)) * mul, nd) for p in (2.5, 50, 97.5)]
    return {"sharpe_ci": q(sh), "maxdd_ci_pct": q(dd, 100.0, 1),
            "sharpe_gt0_prob": round(float(np.mean(sh > 0)), 3),
            "block": block, "B": B, "n": n}


def brier_reliability(p, y, n_bins: int = 10) -> dict:
    """Brier score + skill (vs the base-rate climatology) + a reliability curve
    (mean predicted vs observed frequency per probability bin) for forecasts p∈[0,1]
    against binary outcomes y. This is the missing LEVEL check — every shipped
    discipline checked rank/sign, none checked whether stated odds match reality."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    m = np.isfinite(p) & np.isfinite(y)
    p, y = p[m], y[m]
    if len(p) < 30:
        return {}
    brier = float(np.mean((p - y) ** 2))
    base = float(np.mean((y.mean() - y) ** 2))
    edges = np.linspace(0, 1, n_bins + 1)
    rel = []
    for i in range(n_bins):
        hi_incl = i == n_bins - 1
        b = (p >= edges[i]) & ((p <= edges[i + 1]) if hi_incl else (p < edges[i + 1]))
        if int(b.sum()) >= 10:
            rel.append({"bin": f"{edges[i]:.1f}-{edges[i + 1]:.1f}", "n": int(b.sum()),
                        "pred": round(float(p[b].mean()), 3), "obs": round(float(y[b].mean()), 3)})
    return {"brier": round(brier, 4), "base_brier": round(base, 4),
            "skill_score": round(1 - brier / base, 3) if base else None,
            "reliability": rel, "n": int(len(p)), "base_rate": round(float(y.mean()), 3)}


def platt_fit(p, y, iters: int = 400, lr: float = 0.2, l2: float = 1.0) -> dict:
    """Platt logistic recalibration y ~ sigmoid(a·logit(p)+b), fit by GD with mild L2
    shrinkage toward identity (a=1,b=0) — robust on small N where plain isotonic
    overfits. Returns (a,b) + the recalibrated Brier. a≈1,b≈0 ⇒ already calibrated."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    m = np.isfinite(p) & np.isfinite(y)
    p, y = np.clip(p[m], 1e-4, 1 - 1e-4), y[m]
    if len(p) < 40:
        return {}
    z = np.log(p / (1 - p))
    a, b, n = 1.0, 0.0, len(z)
    for _ in range(iters):
        f = 1.0 / (1.0 + np.exp(-(a * z + b)))
        a -= lr * (float(np.mean((f - y) * z)) + l2 * (a - 1.0) / n)
        b -= lr * float(np.mean(f - y))
    f = 1.0 / (1.0 + np.exp(-(a * z + b)))
    return {"a": round(a, 3), "b": round(b, 3), "brier_recal": round(float(np.mean((f - y) ** 2)), 4)}


def vif(df) -> dict:
    """Variance inflation factor per column from the correlation matrix inverse
    (VIF≈1 independent, >5 redundant, >10 severe collinearity). Surfaces the
    cost-basis cluster triple-counting that a heuristic vote can't see."""
    d = df.dropna()
    if len(d) < 30 or d.shape[1] < 2:
        return {}
    sd = d.std(ddof=0).replace(0, np.nan)
    X = ((d - d.mean()) / sd).dropna(axis=1, how="any")
    if X.shape[1] < 2:
        return {}
    C = np.corrcoef(X.values, rowvar=False)
    Ci = np.linalg.pinv(C)
    return {col: round(float(Ci[i, i]), 2) for i, col in enumerate(X.columns)}


def top_correlated_pairs(df, k: int = 8, thresh: float = 0.6) -> list:
    """The |corr|≥thresh pairs (top k), to name the redundant clusters explicitly."""
    d = df.dropna()
    if len(d) < 30 or d.shape[1] < 2:
        return []
    c = d.corr().abs()
    cols = list(c.columns)
    pairs = [{"a": cols[i], "b": cols[j], "corr": round(float(c.iloc[i, j]), 2)}
             for i in range(len(cols)) for j in range(i + 1, len(cols))
             if c.iloc[i, j] >= thresh]
    return sorted(pairs, key=lambda x: -x["corr"])[:k]


# --------------------------------------------------------------------------- #
# Signal-quality scorecard primitives (Phase A). The Information Coefficient is
# the institutional lingua franca for ranking signals on ONE comparable scale;
# Newey-West makes its t-stat honest under the serial correlation that overlapping
# forward-return windows inject; Benjamini-Hochberg deflates the panel of signals
# you screened (the DSR deflates one strategy — FDR deflates the family). All pure
# numpy/pandas, no scipy/sklearn.
# --------------------------------------------------------------------------- #
def rank_ic(signal, fwd) -> float:
    """Cross-sectional rank IC on ONE date: Spearman correlation between a signal
    cross-section and the forward return across the universe. Higher = the signal
    ranks winners above losers that period. NaN if fewer than 10 joint names."""
    j = pd.concat([pd.Series(signal).rename("s"), pd.Series(fwd).rename("f")], axis=1).dropna()
    if len(j) < 10:
        return float("nan")
    return float(j["s"].rank().corr(j["f"].rank()))


def newey_west_tstat(x, lags: int = 4) -> dict:
    """HAC (Newey-West) t-stat for the MEAN of `x`. Overlapping forward-return
    windows serially-correlate a signal's per-date stats, so a plain t-stat
    overstates significance; the Bartlett-weighted long-run variance corrects it.
    Returns mean, HAC se, t, and a two-sided p (normal approx — large-sample)."""
    import math
    a = np.asarray(pd.Series(x).dropna(), float)
    n = len(a)
    if n < 8:
        return {"mean": None, "se": None, "t": None, "p": None, "n": n}
    mean = float(a.mean())
    d = a - mean
    var = float(np.dot(d, d) / n)                       # gamma_0
    L = min(int(lags), n - 1)
    for j in range(1, L + 1):
        gj = float(np.dot(d[j:], d[:-j]) / n)           # gamma_j (autocovariance)
        var += 2.0 * (1.0 - j / (L + 1)) * gj           # Bartlett kernel weight
    se = math.sqrt(max(var, 1e-18) / n)
    t = mean / se if se else float("nan")
    return {"mean": round(mean, 5), "se": round(se, 5), "t": round(t, 3),
            "p": round(2.0 * (1.0 - _norm_cdf(abs(t))), 4), "n": n}


def ic_summary(ics, periods_per_year: int = 4) -> dict:
    """Summarize a time series of per-date ICs: mean IC, IC vol, IC-IR (mean/vol),
    annualized IC-IR, a Newey-West t-stat (the IC series autocorrelates when the
    forward window overlaps the sampling step), hit rate and n."""
    import math
    s = pd.Series(ics).dropna()
    n = len(s)
    if n < 6:
        return {"n": n}
    mean, sd = float(s.mean()), float(s.std(ddof=1))
    icir = mean / sd if sd else float("nan")
    nw = newey_west_tstat(s, lags=max(1, periods_per_year // 2))
    return {"mean_ic": round(mean, 4), "ic_vol": round(sd, 4), "ic_ir": round(icir, 3),
            "ic_ir_ann": round(icir * math.sqrt(periods_per_year), 3),
            "t_hac": nw["t"], "p_hac": nw["p"], "hit": round(float((s > 0).mean()), 3), "n": n}


def benjamini_hochberg(pvals: dict, alpha: float = 0.10) -> dict:
    """Benjamini-Hochberg FDR across a PANEL of p-values (one per screened signal):
    controls the expected false-discovery rate at `alpha` — the right correction
    when you test many signals and keep the significant ones. Returns per-name
    {p, q (BH-adjusted), reject}."""
    items = [(k, float(v)) for k, v in pvals.items() if v is not None and np.isfinite(v)]
    m = len(items)
    if m == 0:
        return {}
    items.sort(key=lambda kv: kv[1])
    out, qprev = {}, 1.0
    for i in range(m - 1, -1, -1):                       # walk up, enforce monotone q
        k, p = items[i]
        qprev = min(qprev, p * m / (i + 1))
        out[k] = {"p": round(p, 4), "q": round(float(qprev), 4), "reject": bool(qprev <= alpha)}
    return out
