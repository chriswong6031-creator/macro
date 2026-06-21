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
def backtest_core(close: pd.Series, alloc: pd.Series, cost_bps: float = 0.0,
                  cash_yield: pd.Series | None = None, *,
                  dollar_adv: pd.Series | None = None, aum_usd: float | None = None,
                  impact_eta: float = 0.1, vol_window: int = 21) -> dict:
    """Next-bar allocation engine with a one-way transaction cost.

    `cost_bps` is the ONE-WAY cost (spread + fee/slippage) in basis points,
    charged on each unit of position turnover |Δpos|. Returns the building-block
    series the per-asset backtests summarize — the headline strat is NET of cost,
    `gross` exposes the costless path, `turnover` drives the drag. Works for
    long/flat (alloc ∈ [0,1]) and long/short (alloc ∈ [-1,1]) the same way.
    cost_bps default 0.0 keeps legacy callers gross-of-cost.

    `cash_yield` (annualized %, e.g. 3.63 = 3.63%/yr) credits the FLAT sleeve:
    the (1-pos) capital not in the asset earns the prevailing short rate. REQUIRED
    for an equity-vs-treasuries strategy — the de-risked sleeve sits in T-bills,
    not under the mattress, so without it CAGR is understated by the carry on
    ~25-50% of capital and the comparison vs an all-equity buy&hold is unfair.
    Interest accrues on CALENDAR days between bars (a Fri→Mon bar earns 3 days),
    matching the close-to-close return that also spans the weekend; a >100%
    position pays no phantom rebate (clip lower=0). Default None keeps the
    BTC/commodity/forex callers (where flat = uninvested cash) byte-identical.

    SQUARE-ROOT MARKET IMPACT (optional, capacity realism — roadmap Phase 3). A flat
    bps can't tell a $5M microcap trade from a $9k mega-cap one. Pass `dollar_adv`
    (the asset's dollar ADV series, e.g. (close*volume).rolling(21).median()) and a
    portfolio `aum_usd` to ADD an Almgren-style impact term on top of the linear
    `cost_bps`: impact_rate = impact_eta · σ · √(participation), with
    participation = traded$/ADV$ = (aum_usd·|Δpos|)/ADV$ and σ the trailing per-bar
    return vol. Cost grows with √AUM, so net Sharpe degrades as size rises — the
    basis of `capacity_curve`. Both None (default) → the legacy flat-cost path,
    byte-identical for every existing caller.
    """
    ret = close.pct_change().fillna(0)
    pos = alloc.shift(1).reindex(ret.index).ffill().fillna(0)   # act next bar
    turnover = pos.diff().abs().fillna(0.0)                      # |Δpos|, day-1 ramp from 0
    if dollar_adv is not None and aum_usd:
        # per-bar impact rate (fraction of traded notional), added to the linear cost
        sigma = ret.rolling(vol_window).std()
        sigma = sigma.fillna(sigma.median()).fillna(0.0)
        adv = dollar_adv.reindex(ret.index).ffill()
        traded_usd = float(aum_usd) * turnover
        participation = (traded_usd / adv.where(adv > 0)).clip(lower=0.0).fillna(0.0)
        impact_rate = impact_eta * sigma * np.sqrt(participation)
        cost = (cost_bps / 1e4 + impact_rate) * turnover
    else:
        cost = (cost_bps / 1e4) * turnover
    if cash_yield is not None:
        days = pd.Series(ret.index, index=ret.index).diff().dt.days.fillna(0).clip(lower=0)
        rf = (cash_yield.reindex(ret.index).ffill().fillna(0.0) / 100.0) * (days / 365.0)
        cash_leg = (1.0 - pos).clip(lower=0) * rf               # bill carry on the flat sleeve
    else:
        cash_leg = 0.0
    gross = pos * ret + cash_leg
    net = gross - cost
    hold = ret
    years = (close.index[-1] - close.index[0]).days / 365.25
    return {"ret": ret, "pos": pos, "turnover": turnover,
            "gross": gross, "net": net, "hold": hold, "years": years}


def dollar_adv(close: pd.Series, volume: pd.Series, window: int = 21) -> pd.Series:
    """Rolling-median dollar average daily volume — the ADV$ denominator of the
    participation rate. Median (not mean) so a single block print doesn't inflate
    capacity. `volume` is share volume; close*volume is dollar volume."""
    return (close * volume).rolling(window, min_periods=max(2, window // 2)).median()


def _ann_sharpe(r: pd.Series, ppy: int = 252) -> float:
    r = r.dropna()
    if len(r) < 3:
        return float("nan")
    sd = r.std(ddof=1)
    return float(r.mean() / sd * np.sqrt(ppy)) if sd else float("nan")


def capacity_curve(close: pd.Series, alloc: pd.Series, adv_usd: pd.Series,
                   aum_grid: list[float], *, cost_bps: float = 0.0,
                   impact_eta: float = 0.1, cash_yield: pd.Series | None = None,
                   ppy: int = 252) -> dict:
    """Net annualized Sharpe of an allocation as a function of deployed AUM, under
    the square-root impact model — the honest answer to "how much money can this
    signal hold?".

    Returns the per-AUM curve plus an UNAMBIGUOUS capacity verdict:
      * `economic`    — gross Sharpe ≥ buy & hold (is there any edge to deploy at all?).
        When False, capacity is meaningless: the signal does not beat buy & hold even
        costless, so `capacity_usd` is None and `verdict="no_edge"`.
      * `capacity_usd`— the largest grid AUM whose NET Sharpe still beats buy & hold.
      * `grid_capped` — net Sharpe still beats buy & hold at the LARGEST grid AUM, i.e.
        true capacity exceeds the grid (`verdict="exceeds_grid"`), distinct from no_edge.
    Gross Sharpe (AUM-independent) and the buy&hold Sharpe anchor the read."""
    bh = _ann_sharpe(close.pct_change(), ppy)
    gross = _ann_sharpe(backtest_core(close, alloc, cost_bps=cost_bps,
                                      cash_yield=cash_yield)["gross"], ppy)
    grid = sorted(aum_grid)
    curve, capacity = [], None
    for aum in grid:
        bt = backtest_core(close, alloc, cost_bps=cost_bps, cash_yield=cash_yield,
                           dollar_adv=adv_usd, aum_usd=aum, impact_eta=impact_eta)
        ns = _ann_sharpe(bt["net"], ppy)
        # mean participation on rebalancing bars (where turnover>0)
        part = bt["turnover"]
        traded = aum * part
        adv = adv_usd.reindex(bt["turnover"].index).ffill()
        pr = (traded / adv.where(adv > 0)).replace([np.inf, -np.inf], np.nan)
        mean_part = float(pr[part > 0].mean()) if (part > 0).any() else 0.0
        row = {"aum_usd": float(aum), "net_sharpe": ns,
               "mean_participation": round(mean_part, 4) if mean_part == mean_part else None,
               "ann_cost_drag": round(float((bt["gross"] - bt["net"]).mean() * ppy), 4)}
        curve.append(row)
        if ns == ns and bh == bh and ns >= bh:
            capacity = float(aum)
    economic = bool(gross == gross and bh == bh and gross >= bh)
    grid_capped = bool(capacity is not None and capacity >= grid[-1])
    verdict = ("no_edge" if not economic else
               "exceeds_grid" if grid_capped else
               "capped" if capacity is not None else "no_edge")
    return {"buyhold_sharpe": round(bh, 3) if bh == bh else None,
            "gross_sharpe": round(gross, 3) if gross == gross else None,
            "impact_eta": impact_eta, "cost_bps": cost_bps,
            "economic": economic, "grid_capped": grid_capped, "verdict": verdict,
            "capacity_usd": capacity, "curve": curve}


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


def deflated_sharpe(sr_daily, skew, kurt, T, n_trials=None, sr_variance=None,
                    trading_year: float = 252, *, ledger=None,
                    family: str | None = None) -> dict | None:
    """DSR for a strategy selected as the best of N tried configs.
    `sr_daily` = its per-period Sharpe; `sr_variance` = cross-trial variance of the
    per-period Sharpes (if None, fall back to the SR-estimator's own variance as a
    conservative proxy). `trading_year` only scales the *_annual report fields — the
    DSR probability itself is annualization-invariant.

    N (the multiple-testing count) comes from ONE of two sources:

    * `n_trials` (int) — the legacy path: the caller asserts the count. This is the
      p-hacking surface (a caller can lowball it), so new code should NOT use it; the
      `tests/test_no_literal_ntrials.py` ratchet blocks new literal callers.
    * `ledger=` + `family=` — the honest path: N is the count of DISTINCT configs the
      Trial Ledger recorded for `family` AT GENERATION, which the caller cannot
      understate. Pass a `engine.trial_ledger.TrialLedger` (duck-typed: anything with
      an `effective_n(family)` method works).

    Exactly one of {`n_trials`, `ledger`} must be given; passing both is a ValueError."""
    if (ledger is not None) and (n_trials is not None):
        raise ValueError(
            "deflated_sharpe: pass EITHER a literal n_trials OR a ledger= handle, "
            "not both — they are two ways to set the same N")
    if ledger is not None:
        n_trials = ledger.effective_n(family)
    elif n_trials is None:
        raise ValueError(
            "deflated_sharpe requires the multiple-testing N: pass ledger= (honest, "
            "counted at generation) or n_trials= (legacy literal)")
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


def fold_robust(full_sign: int, fold_signs: list, want: int) -> bool:
    """Purged-CV robustness: the full-sample sign matches `want`, NO non-empty fold
    flips to the opposite sign, and all-but-one of the non-empty folds agree. Stricter
    than the pre/post split it complements. (Lifted from calibrate_vector so engine
    leaves — anticipation — can import it directly rather than from a CLI script.)"""
    nz = [s for s in fold_signs if s != 0]
    if not nz:
        return False
    flip = sum(1 for s in nz if s == -want)
    agree = sum(1 for s in nz if s == want)
    return full_sign == want and flip == 0 and agree >= max(1, len(nz) - 1)


# --------------------------------------------------------------------------- #
# Combinatorial Purged CV + Probability of Backtest Overfitting (López de Prado,
# AFML ch.11-12; Bailey-Borwein-LdP-Zhu 2014). The P3/P4 anti-overfit core: judge a
# strategy on a DISTRIBUTION of backtest paths (not one number) and on how likely the
# in-sample-best config is overfit. Pure numpy; the symmetric purge mirrors the geometry
# already proven in engine.meta_label._train_events (purge BOTH sides of each test block).
# --------------------------------------------------------------------------- #
def cpcv_paths(n_obs: int, n_groups: int = 6, k_test: int = 2, embargo: int = 0) -> list:
    """Combinatorial Purged Cross-Validation splits. Partition `n_obs` ordered observations
    into `n_groups` contiguous groups; for EVERY C(n_groups, k_test) choice of test groups,
    train = all other observations with a SYMMETRIC purge — drop training rows within
    `embargo` of each test block on BOTH sides (a forward label of length `embargo` near a
    boundary would otherwise leak across it). Returns a list of (train_idx, test_idx) int
    arrays — C(n_groups, k_test) backtest PATHS, so a strategy yields a performance
    distribution, not a single (cherry-pickable) number. Empty list on degenerate inputs."""
    from itertools import combinations
    n_obs = int(n_obs)
    if n_groups < 2 or k_test < 1 or k_test >= n_groups or n_obs < n_groups:
        return []
    bounds = np.linspace(0, n_obs, n_groups + 1).astype(int)
    out = []
    for combo in combinations(range(n_groups), k_test):
        test_idx = np.concatenate([np.arange(bounds[g], bounds[g + 1]) for g in combo])
        test_set = set(int(i) for i in test_idx)
        purged = set()
        for g in combo:                                       # symmetric purge + embargo
            lo, hi = int(bounds[g]), int(bounds[g + 1])
            purged.update(range(max(0, lo - embargo), lo))
            purged.update(range(hi, min(n_obs, hi + embargo)))
        train_idx = np.array([i for i in range(n_obs)
                              if i not in test_set and i not in purged], dtype=int)
        out.append((train_idx, test_idx))
    return out


def prob_backtest_overfitting(perf, n_splits: int = 16) -> dict | None:
    """Probability of Backtest Overfitting via Combinatorial Symmetric Cross-Validation.
    `perf` is a (T_obs x N_configs) matrix of per-observation performance (e.g. daily returns)
    for the N candidate configs you searched. Split T into `n_splits` (even) contiguous
    sub-periods; for every way to pick n_splits/2 as in-sample (IS) and the complement as
    out-of-sample (OOS): take the IS-best config and find its OOS RANK among all configs;
    PBO = the fraction of combinations where the IS-best lands BELOW the OOS median (logit<0).
    High PBO (→1) means picking the in-sample winner is selection over noise — the strategy
    family is overfit. Returns {pbo, n_combos, median_logit} or None on degenerate input."""
    from itertools import combinations
    M = np.asarray(perf, dtype=float)
    if M.ndim != 2 or M.shape[1] < 2:
        return None
    T, N = M.shape
    S = int(n_splits) - (int(n_splits) % 2)                   # force even
    if S < 2 or T < S:
        return None
    bounds = np.linspace(0, T, S + 1).astype(int)
    blocks = [np.arange(bounds[i], bounds[i + 1]) for i in range(S)]

    def _ir(rows):                                            # information ratio per config
        sub = M[rows]
        mu = sub.mean(axis=0)
        sd = sub.std(axis=0, ddof=1)
        return np.where(sd > 0, mu / sd, 0.0)

    logits = []
    half = S // 2
    for combo in combinations(range(S), half):
        comp = [i for i in range(S) if i not in combo]
        is_perf = _ir(np.concatenate([blocks[i] for i in combo]))
        oos_perf = _ir(np.concatenate([blocks[i] for i in comp]))
        n_star = int(np.argmax(is_perf))                      # IS-best config
        rank = int(oos_perf.argsort().argsort()[n_star])      # 0=worst .. N-1=best OOS
        omega = (rank + 1) / (N + 1)
        omega = min(max(omega, 1e-6), 1 - 1e-6)
        logits.append(math.log(omega / (1 - omega)))
    if not logits:
        return None
    arr = np.array(logits)
    return {"pbo": round(float((arr < 0).mean()), 4), "n_combos": int(arr.size),
            "median_logit": round(float(np.median(arr)), 4)}


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


def expected_calibration_error(p, y, n_bins: int = 10) -> dict:
    """Expected Calibration Error — the binned gap between stated confidence and observed
    frequency for forecasts p∈[0,1] vs binary y. ECE = Σ_b (n_b/N)·|conf_b − acc_b|; MCE =
    max_b |conf_b − acc_b|. ECE→0 means '70% really means ~70%'. Rising ECE is the earliest
    decay alarm for a probabilistic signal (recession probit, bottom_radar ladder). {} on thin N."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    m = np.isfinite(p) & np.isfinite(y)
    p, y = p[m], y[m]
    if len(p) < 30:
        return {}
    edges = np.linspace(0, 1, n_bins + 1)
    N = len(p)
    ece, mce = 0.0, 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        sel = (p >= lo) & (p <= hi) if i == n_bins - 1 else (p >= lo) & (p < hi)
        nb = int(sel.sum())
        if nb == 0:
            continue
        gap = abs(float(p[sel].mean()) - float(y[sel].mean()))
        ece += (nb / N) * gap
        mce = max(mce, gap)
    return {"ece": round(ece, 4), "mce": round(mce, 4), "n": int(N)}


def isotonic_calibration(p, y) -> dict:
    """Isotonic (monotone) recalibration via Pool-Adjacent-Violators — fits a non-decreasing
    score→probability map with NO functional form (unlike Platt's sigmoid), so it corrects an
    arbitrarily-shaped miscalibration when N is ample. Returns {x, y_cal, n, ece_before,
    ece_after}; feed `model` + new scores to `apply_calibration`. {} on thin N (use platt_fit)."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    m = np.isfinite(p) & np.isfinite(y)
    p, y = p[m], y[m]
    if len(p) < 30:
        return {}
    order = np.argsort(p, kind="mergesort")
    xs, ys = p[order], y[order].astype(float)
    blocks: list = []                                # [mean, weight, count]
    for v in ys:
        blocks.append([float(v), 1.0, 1])
        while len(blocks) >= 2 and blocks[-2][0] > blocks[-1][0]:
            m2, w2, c2 = blocks.pop()
            m1, w1, c1 = blocks.pop()
            nw = w1 + w2
            blocks.append([(m1 * w1 + m2 * w2) / nw, nw, c1 + c2])
    fitted = np.array([blk[0] for blk in blocks for _ in range(blk[2])], dtype=float)
    model = {"x": xs.tolist(), "y_cal": fitted.tolist(), "n": int(len(p))}
    model["ece_before"] = expected_calibration_error(p, y).get("ece")
    model["ece_after"] = expected_calibration_error(apply_calibration(model, p), y).get("ece")
    return model


def apply_calibration(model: dict, p_new) -> "np.ndarray":
    """Map new scores through a fitted isotonic `model` (step function = last x ≤ p_new)."""
    x = np.asarray(model.get("x", []), float)
    yc = np.asarray(model.get("y_cal", []), float)
    pn = np.asarray(p_new, float)
    if x.size == 0:
        return pn
    idx = np.clip(np.searchsorted(x, pn, side="right") - 1, 0, len(yc) - 1)
    return yc[idx]


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


def resid_z(z: pd.Series, basis: list, win: int, min_p: int) -> pd.Series:
    """Sequential CAUSAL residual of a standardized signal `z` on each series in
    `basis` (already-orthogonalized earlier axes). Peels one basis at a time using a
    rolling-beta regression evaluated with PRIOR-window betas (shift(1), no
    look-ahead); the residual stays raw until a beta is estimable. This is the
    z-series analogue of forex_signals.orthogonalize (which returns a price index —
    wrong shape here). Fixed-form: the only parameter is the rolling window, declared
    in config, not tuned. (Vector D-vec-ENSEMBLE.)"""
    e = z.copy()
    for b in basis:
        b = b.reindex(e.index)
        cov = e.rolling(win, min_periods=min_p).cov(b)
        var = b.rolling(win, min_periods=min_p).var()
        beta = (cov / var.replace(0, np.nan)).shift(1)            # causal
        e = (e - beta * b).where(beta.notna(), e)                 # raw until estimable
    return e


# --------------------------------------------------------------------------- #
# CRPS — the one net-new primitive (Anticipation Engine). brier_reliability only
# scores a BINARY forecast; the multi-horizon cone is a DISTRIBUTION (return
# quantiles + drawdown), so we need a proper scoring rule for the whole forecast.
# Continuous Ranked Probability Score is the distributional analogue of MAE:
# CRPS(F, y) = E|X - y| - ½E|X - X'|, X,X' ~ F. Lower is better; it rewards a
# forecast that is BOTH sharp and calibrated, and collapses to |x-y| for a point
# forecast. Pure numpy (no scipy), via the sorted-ensemble identity.
# --------------------------------------------------------------------------- #
def crps_ensemble(samples, y) -> float:
    """CRPS of an ENSEMBLE forecast (a set of Monte-Carlo / empirical-analog sample
    outcomes) against a scalar realization `y`. O(m log m) via the closed form
    E|X-X'| = (2/m²)·Σ_i (2i-m-1)·x_(i) on the sorted ensemble. NaN if empty."""
    s = np.sort(np.asarray(samples, float))
    s = s[np.isfinite(s)]
    m = len(s)
    if m == 0 or y is None or not np.isfinite(y):
        return float("nan")
    mae = float(np.mean(np.abs(s - y)))
    i = np.arange(1, m + 1)
    ediff = float((2.0 / (m * m)) * np.sum((2 * i - m - 1) * s))
    return mae - 0.5 * ediff


def crps_score(sample_sets, ys, clim=None) -> dict:
    """Mean CRPS over many (forecast-ensemble, realization) pairs, plus a SKILL
    score vs an unconditional climatology forecast `clim` (a single fixed ensemble —
    e.g. the pooled outcome distribution — used for every obs). skill = 1 - crps/crps_clim;
    >0 means the conditional cone beats 'always predict the base distribution'. Pass a
    SUBSAMPLED clim (a few hundred points) — the climatology leg is O(len(ys)·|clim|)."""
    ys = np.asarray(ys, float)
    vals = [crps_ensemble(s, y) for s, y in zip(sample_sets, ys) if s is not None]
    pairs = [(v, y) for v, y in zip(vals, ys) if np.isfinite(v)]
    if len(pairs) < 10:
        return {}
    mc = float(np.mean([v for v, _ in pairs]))
    out = {"crps": round(mc, 4), "n": len(pairs)}
    if clim is not None and len(clim):
        cv = float(np.mean([crps_ensemble(clim, y) for _, y in pairs]))
        out["crps_clim"] = round(cv, 4)
        out["skill"] = round(1 - mc / cv, 3) if cv else None
    return out


# --------------------------------------------------------------------------- #
# OUT-OF-SAMPLE return-prediction tests (Index Direction model). The single
# honest bar for any directional/return forecast: does it beat the EXPANDING
# HISTORICAL MEAN (the Goyal-Welch random-walk benchmark) out-of-sample? Two
# net-new primitives — both pure-numpy, layered on newey_west_tstat.
# --------------------------------------------------------------------------- #
def oos_r2(realized, forecast, bench=None, min_n: int = 60) -> dict:
    """Campbell-Thompson out-of-sample R²: 1 - Σ(r-f)² / Σ(r-bench)², where bench is
    the recursive/EXPANDING historical mean (passed in, or computed causally here as
    the shifted expanding mean of `realized` when None). OOS_R² > 0 ⇒ the forecast
    beats 'always predict the mean' out-of-sample. `realized`/`forecast` must be
    TIME-ORDERED. Returns {} if fewer than min_n aligned points."""
    r = np.asarray(realized, float)
    f = np.asarray(forecast, float)
    if bench is None:
        b = pd.Series(r).expanding(min_periods=1).mean().shift(1).to_numpy()
    else:
        b = np.asarray(bench, float)
    m = np.isfinite(r) & np.isfinite(f) & np.isfinite(b)
    r, f, b = r[m], f[m], b[m]
    if len(r) < min_n:
        return {}
    sse_f = float(np.sum((r - f) ** 2))
    sse_b = float(np.sum((r - b) ** 2))
    return {"oos_r2": round(1.0 - sse_f / sse_b, 5) if sse_b else None,
            "mspe_fcst": round(sse_f / len(r), 6), "mspe_bench": round(sse_b / len(r), 6),
            "n": int(len(r))}


def clark_west(realized, forecast, bench=None, hac_lags: int = 4) -> dict:
    """Clark-West (2007) adjusted test of OOS_R² > 0 for NESTED models (forecast nests
    the historical-mean benchmark). The naive MSPE comparison is biased against the
    larger model because estimating the extra parameter adds noise under the null; CW
    adds back (bench-f)². f_adj = (r-bench)² - (r-f)² + (bench-f)²; a positive mean
    (HAC t-stat via newey_west_tstat) ⇒ the predictor has genuine OOS content. Returns
    {cw_t, cw_p (ONE-sided), mean_adj, n}."""
    r = np.asarray(realized, float)
    f = np.asarray(forecast, float)
    if bench is None:
        b = pd.Series(r).expanding(min_periods=1).mean().shift(1).to_numpy()
    else:
        b = np.asarray(bench, float)
    m = np.isfinite(r) & np.isfinite(f) & np.isfinite(b)
    r, f, b = r[m], f[m], b[m]
    if len(r) < 8:
        return {}
    f_adj = (r - b) ** 2 - (r - f) ** 2 + (b - f) ** 2
    nw = newey_west_tstat(f_adj, lags=hac_lags)
    t = nw.get("t")
    one_sided = (nw["p"] / 2.0 if (t is not None and t > 0) else
                 (1.0 - nw["p"] / 2.0 if t is not None else None))
    return {"cw_t": t, "cw_p": round(one_sided, 4) if one_sided is not None else None,
            "mean_adj": nw.get("mean"), "n": int(len(r))}


# --------------------------------------------------------------------------- #
# INCREMENTAL IC — the institutional honesty test. rank_ic measures a signal's RAW
# correlation with forward returns, which conflates genuine information with repackaged
# common-factor exposure (a momentum signal "predicts" partly because it IS momentum). The
# institutional question is the INCREMENTAL IC: after neutralizing the signal cross-section
# against the factors you already own (market beta, size, sector, momentum, low-vol), does
# any independent forecasting power survive? cross_sectional_resid does the one-date
# neutralization (OLS residual); the per-date residual ICs then feed ic_summary exactly like
# raw ICs, so the whole HAC-t / BH-FDR gauntlet applies to the HARDER, honest number.
# --------------------------------------------------------------------------- #
def cross_sectional_resid(signal, loadings):
    """Residualize one cross-section of `signal` (ticker->value) against `loadings`
    (DataFrame ticker x factor) by OLS with an intercept — the part of the signal
    ORTHOGONAL to the factors you already own. Standardizes the loadings so scale is
    irrelevant; returns NaN-free residuals on the jointly-present names (>= 5, else empty)."""
    s = pd.Series(signal).dropna()
    X = pd.DataFrame(loadings).reindex(s.index)
    j = pd.concat([s.rename("_y"), X], axis=1).dropna()
    if len(j) < 5 or j.shape[1] < 2:
        return pd.Series(dtype=float)
    y = j["_y"].to_numpy(float)
    cols = [c for c in j.columns if c != "_y"]
    Z = j[cols].to_numpy(float)
    sd = Z.std(axis=0, ddof=0)
    sd[sd == 0] = 1.0
    Z = (Z - Z.mean(axis=0)) / sd                       # standardize loadings
    A = np.column_stack([np.ones(len(y)), Z])           # + intercept
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ beta
    return pd.Series(resid, index=j.index)


def incremental_ic(signal_by_date: dict, fwd_by_date: dict, loadings_by_date: dict,
                   periods_per_year: int = 12) -> dict:
    """Raw vs factor-NEUTRALIZED rank-IC across a rebalance grid. `*_by_date` map a date
    to a cross-section (signal Series / forward-return Series / loadings DataFrame). Returns
    raw and incremental ic_summary blocks + the mean-IC delta — the share of a signal's edge
    that is NOT just repackaged factor exposure. A signal whose IC collapses to ~0 after
    neutralization carries no independent information, however good its raw IC looked."""
    raw_ics, inc_ics = [], []
    for d, sig in signal_by_date.items():
        fwd = fwd_by_date.get(d)
        if fwd is None or sig is None or len(sig) == 0:
            continue
        raw_ics.append(rank_ic(sig, fwd))
        load = loadings_by_date.get(d)
        if load is not None and len(load):
            resid = cross_sectional_resid(sig, load)
            if len(resid):
                inc_ics.append(rank_ic(resid, fwd))
    raw = ic_summary(raw_ics, periods_per_year=periods_per_year)
    inc = ic_summary(inc_ics, periods_per_year=periods_per_year)
    rm, im = raw.get("mean_ic"), inc.get("mean_ic")
    return {"raw": raw, "incremental": inc,
            "ic_delta": round(im - rm, 4) if (rm is not None and im is not None) else None,
            "surviving_frac": round(im / rm, 3) if (rm not in (None, 0) and im is not None) else None}
