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


def bootstrap_effective_t(returns, block: int = 21, B: int = 2000,
                          seed: int = 7) -> dict:
    """Block-bootstrap effective sample size for a daily strategy-return series.

    Positively autocorrelated returns make the sqrt(T-1) SR error bar overconfident;
    this replaces raw T with the autocorrelation-honest count (masterplan N7:
    "block-bootstrap effective-N replacing raw sqrt(T-1)").

    For each of B circular block-bootstrap resamples, compute the resample mean;
    let v_boot = variance across those B means (ddof=1). Under iid sampling,
    v_boot == var(r)/n, so t_eff = var(r, ddof=1) / v_boot recovers n exactly.
    Under positive autocorrelation v_boot > var(r)/n, so t_eff < n — fewer effective
    observations. Returns {"t_eff": int, "t_raw": n, "ratio": float, "block": int,
    "B": int}, clamped to [30, n]. Returns {} when n < max(3*block, 60) or v_boot<=0.
    """
    r = np.asarray(returns.dropna() if hasattr(returns, "dropna") else returns, float)
    n = len(r)
    if n < max(3 * block, 60):
        return {}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts_grid = np.arange(block)
    means = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + starts_grid[None, :]).ravel()[:n] % n
        means[k] = r[idx].mean()
    v_boot = float(np.var(means, ddof=1))
    if v_boot <= 0:
        return {}
    v_iid = float(np.var(r, ddof=1))
    t_eff = int(np.clip(v_iid / v_boot, 30, n))
    return {"t_eff": t_eff, "t_raw": n, "ratio": round(t_eff / n, 3),
            "block": block, "B": B}


def deflated_sharpe(sr_daily, skew, kurt, T, n_trials=None, sr_variance=None,
                    trading_year: float = 252, *, ledger=None,
                    family: str | None = None, t_eff: int | None = None) -> dict | None:
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

    Exactly one of {`n_trials`, `ledger`} must be given; passing both is a ValueError.

    `t_eff` (optional, keyword-only) — a block-bootstrap effective sample size from
    `bootstrap_effective_t`. When provided and >= 3, the sqrt(T-1) confidence term and
    the proxy floor both use Te = min(t_eff, T) instead of raw T. Autocorrelated daily
    returns make the raw sqrt(T-1) overconfident; Te is the autocorrelation-honest count
    (masterplan N7). When None/invalid: bit-for-bit identical to the original behavior."""
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
    # Select the effective sample size: use t_eff if it is a valid int >= 3;
    # otherwise fall back to raw T (bit-for-bit identical for commodity/forex callers).
    if isinstance(t_eff, int) and t_eff >= 3:
        Te = min(int(t_eff), int(T))
    else:
        Te = int(T)
    var_scaler = 1.0 - skew * sr_daily + ((kurt - 1.0) / 4.0) * sr_daily * sr_daily
    var_scaler = max(var_scaler, 1e-9)
    # Floor the cross-trial SR variance at the null SR-sampling variance (~1/Te):
    # a handful of near-duplicate allocation variants understates true trial
    # dispersion, which would make the SR0 haircut too lenient. max() keeps it honest.
    proxy = var_scaler / (Te - 1)
    sr_variance = proxy if (sr_variance is None or sr_variance <= 0) else max(sr_variance, proxy)
    N = max(int(n_trials), 1)
    if N == 1:
        sr0 = 0.0
    else:
        z1, z2 = _norm_ppf(1 - 1.0 / N), _norm_ppf(1 - 1.0 / (N * np.e))
        sr0 = np.sqrt(sr_variance) * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)
    dsr = _norm_cdf((sr_daily - sr0) * np.sqrt(Te - 1) / np.sqrt(var_scaler))
    ann = float(np.sqrt(trading_year))
    result = {"dsr": round(float(dsr), 4),
              "sr_daily": round(float(sr_daily), 6), "sr_annual": round(float(sr_daily) * ann, 2),
              "sr0_daily": round(float(sr0), 6), "sr0_annual": round(float(sr0) * ann, 2),
              "n_trials": N, "T": int(T), "skew": round(float(skew), 3), "kurt": round(float(kurt), 3)}
    if isinstance(t_eff, int) and t_eff >= 3:
        result["t_eff"] = Te
    return result


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


def _calmar(r, ann: int) -> float:
    """CAGR / |maxDD| from a daily return array. Tail/capital-efficiency metric — the
    honest yardstick for a subtract-only sizing overlay (Sharpe alone is gamed by the
    leverage effect of vol-targeting)."""
    r = np.asarray(r, float)
    n = len(r)
    if n < 2:
        return float("nan")
    cagr = float(np.prod(1.0 + r) ** (ann / n) - 1.0)
    dd = abs(_maxdd(r))
    return cagr / dd if dd > 1e-9 else float("nan")


def paired_delta_ci(a, b, block: int = 21, B: int = 5000, seed: int = 13, ann: int = 252) -> dict:
    """Paired circular-block bootstrap of strategy A's outperformance over B. Resamples the
    TWO net-return series on the SAME block indices each draw — preserving their (usually
    high) correlation — then returns the 2.5/50/97.5 CI of Δsharpe and Δcalmar (A − B). "A
    adds value over B" ONLY when the CI excludes 0; bootstrapping each leg separately and
    eyeballing whether the intervals overlap is the wrong (far too lenient) test. The right
    comparison for two strategies on the same book (Ledoit-Wolf / DeMiguel paired test)."""
    a = (a.dropna() if hasattr(a, "dropna") else pd.Series(a).dropna())
    b = pd.Series(b).reindex(a.index).fillna(0.0)
    ra, rb = a.to_numpy(float), b.to_numpy(float)
    n = len(ra)
    if n < max(block * 3, 60):
        return {}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    grid = np.arange(block)
    ds = np.empty(B); dc = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        sa, sb = ra[idx], rb[idx]
        ds[k] = _sharpe(sa, ann) - _sharpe(sb, ann)
        dc[k] = _calmar(sa, ann) - _calmar(sb, ann)
    def q(arr):
        return [round(float(np.percentile(arr, p)), 3) for p in (2.5, 50, 97.5)]
    dsq, dcq = q(ds), q(dc)
    return {"delta_sharpe_ci": dsq, "delta_calmar_ci": dcq,
            "sharpe_better": bool(dsq[0] > 0), "calmar_better": bool(dcq[0] > 0),
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
    Returns mean, HAC se, t, and a two-sided p (normal approx — large-sample).

    `lags` is the REQUESTED truncation lag; the lag actually applied is clamped to
    ``min(lags, n - 1)`` because a Bartlett kernel cannot weight an autocovariance the
    sample does not contain. Both are reported — ``lags`` is the EFFECTIVE lag, echoed so
    a caller (and any artifact it publishes) can never advertise a correction the series
    was too short to receive; ``lags_requested`` keeps the ask visible beside it. A
    requested 21 on n=10 corrects only 9 lags, and printing the 21 is how an
    under-corrected t reads as a fully-corrected one (2026-08-03 experiments audit)."""
    import math
    a = np.asarray(pd.Series(x).dropna(), float)
    n = len(a)
    if n < 8:
        return {"mean": None, "se": None, "t": None, "p": None, "n": n,
                "lags": None, "lags_requested": int(lags)}
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
            "p": round(2.0 * (1.0 - _norm_cdf(abs(t))), 4), "n": n,
            "lags": L, "lags_requested": int(lags)}


def ic_summary(ics, periods_per_year: int = 4, hac_lags: int | None = None) -> dict:
    """Summarize a time series of per-date ICs: mean IC, IC vol, IC-IR (mean/vol),
    annualized IC-IR, a Newey-West t-stat (the IC series autocorrelates when the
    forward window overlaps the sampling step), hit rate and n.

    `hac_lags` OVERRIDES the Newey-West truncation lag. The default
    (``periods_per_year // 2``) is a REBALANCE-cadence heuristic: it assumes the grid is
    sampled at roughly the horizon, so a handful of lags spans the overlap. It silently
    under-corrects whenever the grid is sampled FINER than the forward window — daily
    cross-sections against a 21-day forward return overlap 21 deep, and Bartlett-weighting
    only 6 of those lags understates the long-run variance and inflates t. Pass the measured
    overlap (forward horizon ÷ sampling step, in the same units) whenever the caller knows
    its own cadence.

    ``hac_lags`` in the RESULT is the EFFECTIVE lag — newey_west_tstat clamps to
    ``min(lags, n - 1)``, so a requested 21 on a 10-point IC series applies 9. Echoing the
    request there published a correction the series never received (subsector rotation shipped
    ``hac_lags: 21`` on ``n: 10``; 2026-08-03 experiments audit). The ask is still visible as
    ``hac_lags_requested``: when the two differ, the series was too short to carry the
    correction its own cadence demands and the t is under-corrected, not honest.
    """
    import math
    s = pd.Series(ics).dropna()
    n = len(s)
    if n < 6:
        return {"n": n}
    mean, sd = float(s.mean()), float(s.std(ddof=1))
    icir = mean / sd if sd else float("nan")
    # coerce rather than isinstance-check: a numpy int or a 21.0 float must NOT silently fall
    # back to the (shorter, anticonservative) default — that is the very bug this override fixes
    try:
        lags = int(hac_lags) if hac_lags is not None else 0
    except (TypeError, ValueError):
        lags = 0
    if lags < 1:
        lags = max(1, periods_per_year // 2)
    nw = newey_west_tstat(s, lags=lags)
    return {"mean_ic": round(mean, 4), "ic_vol": round(sd, 4), "ic_ir": round(icir, 3),
            "ic_ir_ann": round(icir * math.sqrt(periods_per_year), 3),
            "t_hac": nw["t"], "p_hac": nw["p"], "hit": round(float((s > 0).mean()), 3), "n": n,
            # EFFECTIVE lag (clamped to n-1), not the ask — see the docstring note. The
            # fallback covers 6 <= n < 8, where newey_west_tstat short-circuits without
            # computing: the honest effective lag is still the clamp, never the request.
            "hac_lags": nw["lags"] if nw.get("lags") is not None else min(lags, max(n - 1, 1)),
            "hac_lags_requested": lags}


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
                   periods_per_year: int = 12, hac_lags: int | None = None) -> dict:
    """Raw vs factor-NEUTRALIZED rank-IC across a rebalance grid. `*_by_date` map a date
    to a cross-section (signal Series / forward-return Series / loadings DataFrame). Returns
    raw and incremental ic_summary blocks + the mean-IC delta — the share of a signal's edge
    that is NOT just repackaged factor exposure. A signal whose IC collapses to ~0 after
    neutralization carries no independent information, however good its raw IC looked.

    `hac_lags` is forwarded to both ic_summary calls — see its note there on why the
    periods_per_year default under-corrects an overlapping grid."""
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
    raw = ic_summary(raw_ics, periods_per_year=periods_per_year, hac_lags=hac_lags)
    inc = ic_summary(inc_ics, periods_per_year=periods_per_year, hac_lags=hac_lags)
    rm, im = raw.get("mean_ic"), inc.get("mean_ic")
    return {"raw": raw, "incremental": inc,
            "ic_delta": round(im - rm, 4) if (rm is not None and im is not None) else None,
            "surviving_frac": round(im / rm, 3) if (rm not in (None, 0) and im is not None) else None}


# --------------------------------------------------------------------------- #
# White's Reality Check + Hansen's SPA — testing a FAMILY, not a winner
# --------------------------------------------------------------------------- #
# Every other significance tool in this module prices ONE series (deflated_sharpe
# haircuts a hand-picked Sharpe by a trial count; benjamini_hochberg controls FDR
# across a list of p-values). Neither answers the question a search actually poses:
# "is the BEST of my K models genuinely better than the benchmark, once I account
# for having taken a maximum over K correlated candidates?" A per-model t-test
# answers a question nobody asked, and the max of K such t-stats is not a t-stat.
#
# White (2000) Reality Check and Hansen (2005) SPA answer exactly that, on the loss
# differentials d_k = L_benchmark - L_k. Both bootstrap the JOINT distribution of the
# K sample means (so the correlation between near-duplicate models is priced, not
# assumed away) and compare the observed maximum against the maximum of the
# bootstrapped null. SPA additionally studentizes each model by its own long-run
# standard error and drops hopeless models from the null via Hansen's recentering,
# which is what recovers the power White's RC loses to a single terrible candidate.
#
# The block bootstrap is CIRCULAR with a fixed block length, matching
# block_bootstrap_ci / paired_delta_ci above so the whole module shares one
# resampling idiom; the loss differentials of an overlapping forecast grid are
# serially correlated and an iid bootstrap would understate every standard error.
#
# MEASURED EMPIRICAL SIZE, printed rather than assumed (least-favourable null — every
# model's true expected loss EQUALS the benchmark's, which is where these tests are
# most distorted; K=5, B=500, 1,200-1,500 replications, nominal 5%):
#
#     data                block         RC       SPA_c
#     iid,      T=120     1 (matched)   5.5%      5.6%
#     iid,      T=120     5 (auto)      5.9%      7.9%
#     iid,      T=500     8 (auto)      5.3%      5.9%
#     AR(1).5,  T=120     5 (auto)     12.6%     14.6%
#     AR(1).5,  T=500     8 (auto)      7.7%      8.4%
#
# Read that honestly. With a block matched to the dependence the machinery is exact
# (5.5 / 5.6). Everything above that is the BLOCK BOOTSTRAP's finite-sample cost, not
# the statistic's: a T=120 series resampled in blocks of 5 contains ~24 effective
# blocks, and no choice of block length rescues it — sweeping the block from 5 to 24
# on that AR(1) panel moved RC only between 10.2% and 12.6% and made SPA strictly
# worse past block 8 (13.0% -> 19.3%), because a longer block buys dependence
# coverage with fewer independent blocks. The distortion shrinks with T, as a
# consistent test's must.
#
# Consequences a caller must live with, not route around:
#   * On a SHORT, serially-correlated panel (T ~ 100) both tests reject roughly twice
#     as often as advertised. A p just under 0.05 there is not evidence; treat ~0.02
#     as the working threshold, or lengthen the sample.
#   * SPA_c is the more liberal of the two at every T. It ships with Hansen's own
#     bracketing p-values (``p_value_upper`` = SPA_u, ``p_value_lower`` = SPA_l) so
#     the finite-sample slack is auditable from the return value itself.
#   * Report BOTH tests. RC is conservative against a family containing junk; SPA is
#     liberal in small samples. They fail in opposite directions, and agreement
#     between them is worth more than either number alone.
def _rc_abstain(reason: str, *, n_models: int, n_obs: int, block, B: int) -> dict:
    """The explicit non-answer. A degenerate family returns THIS, never a number:
    a p-value computed on 8 observations or an all-NaN column is not a weak result,
    it is an absent one, and the two must not be readable as the same thing."""
    return {"statistic": None, "p_value": None, "n_models": int(n_models),
            "n_obs": int(n_obs), "block": block, "B": int(B),
            "best_model": None, "recentred_models": 0,
            "abstained": True, "reason": reason}


def _rc_prepare(losses_benchmark, losses_models):
    """Align the benchmark loss series with the model loss panel and return
    ``(d, keys)`` where ``d`` is the T x K array of ``d_k = L_benchmark - L_k``
    (positive = model k beats the benchmark) on COMPLETE cases only.

    Accepts the model panel as a DataFrame, a dict of series, a 2-D array, or a
    single 1-D series. Alignment is by index when both sides are pandas objects
    with the same index, positional when the lengths match, and by reindex
    otherwise — a mismatch shows up as NaN rows and is dropped, never silently
    zero-filled."""
    if isinstance(losses_benchmark, pd.Series):
        b = losses_benchmark.astype(float)
    else:
        b = pd.Series(np.asarray(losses_benchmark, dtype=float).ravel())
    if isinstance(losses_models, pd.DataFrame):
        M = losses_models.astype(float)
    elif isinstance(losses_models, pd.Series):
        M = losses_models.astype(float).to_frame()
    elif isinstance(losses_models, dict):
        M = pd.DataFrame({k: pd.Series(v) for k, v in losses_models.items()}).astype(float)
    else:
        arr = np.asarray(losses_models, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        M = pd.DataFrame(arr, columns=[f"model_{i}" for i in range(arr.shape[1])])
    if not M.index.equals(b.index):
        # Positional alignment is only safe when at least one side's index carries no
        # meaning (a plain RangeIndex, which is what the array/dict paths above build).
        # Two MEANINGFUL indices of equal length that merely disagree — a one-row
        # offset between two date-indexed series — used to be joined positionally and
        # silently answered the wrong question; those reindex and drop instead.
        trivial = (isinstance(M.index, pd.RangeIndex) or isinstance(b.index, pd.RangeIndex))
        M = (M.set_axis(b.index) if (len(M) == len(b) and trivial)
             else M.reindex(b.index))
    keys = list(M.columns)
    bench_all_nan = not np.isfinite(b.to_numpy(float)).any()
    if not keys:
        return np.empty((0, 0)), keys, [], bench_all_nan
    all_nan = [k for k in keys if not np.isfinite(M[k].to_numpy(float)).any()]
    frame = pd.concat([b.rename("__bench__"), M], axis=1)
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    if frame.empty:
        return np.empty((0, len(keys))), keys, all_nan, bench_all_nan
    bench = frame["__bench__"].to_numpy(float)
    d = np.column_stack([bench - frame[k].to_numpy(float) for k in keys])
    return d, keys, all_nan, bench_all_nan


def _rc_auto_block(T: int) -> int:
    """Block length when the caller declares none: ``max(1, round(T ** (1/3)))``.

    The cube root is the textbook rate for a block bootstrap's optimal block under
    weak dependence (it balances the bias from breaking dependence at block joins
    against the variance from having few blocks). It is a DEFAULT, not a claim about
    this particular series: a caller who knows the autocorrelation horizon should
    pass ``block`` explicitly, and the value actually used is echoed in the result so
    a published number can never hide which one was applied."""
    return max(1, int(round(T ** (1.0 / 3.0))))


def _rc_boot_means(d: "np.ndarray", block: int, B: int, seed: int,
                   chunk: int = 256) -> "np.ndarray":
    """B x K matrix of circular-block-bootstrap means of the loss differentials.

    The SAME resampled row indices are applied to every model column in a draw, so
    the cross-model correlation structure survives the bootstrap — that is the whole
    point of testing a family jointly rather than K times separately. Chunked so a
    large (B, T, K) gather never materializes at once."""
    T, K = d.shape
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(T / block))
    grid = np.arange(block)
    out = np.empty((B, K), dtype=float)
    for start in range(0, B, chunk):
        stop = min(start + chunk, B)
        starts = rng.integers(0, T, size=(stop - start, nb))
        idx = (starts[:, :, None] + grid[None, None, :]).reshape(stop - start, nb * block)
        idx = idx[:, :T] % T
        out[start:stop] = d[idx].mean(axis=1)
    return out


def _rc_mc_pvalue(null_stats: "np.ndarray", observed: float) -> float:
    """Exact Monte-Carlo p-value: ``(1 + #{null >= observed}) / (B + 1)``.

    Two deliberate departures from the naive ``#{null > observed} / B``, and both
    are correctness, not taste.

    ``1 +`` / ``B + 1`` (Davison-Hinkley). The plain share treats the B bootstrap
    draws as if they were the whole null distribution; for finite B the resulting
    test is anti-conservative. The observed statistic is itself one draw from the
    null under H0, so it belongs in both numerator and denominator, which makes the
    test exact for ANY B rather than asymptotically valid for a large one. It also
    makes the floor honest — a p-value can never be reported as 0.0, only as
    ``<= 1/(B+1)``, which is the most a bootstrap of that size can resolve.

    ``>=`` rather than ``>``. For a continuous statistic ties have probability zero
    and the choice is cosmetic; for SPA it is NOT, because ``max(0, ...)`` puts an
    ATOM at zero. When no model clears its recentring threshold, every bootstrap
    draw and the observed statistic all collapse to exactly 0 — the honest reading
    is "not one candidate even beat the benchmark in sample", i.e. p = 1. Under
    ``>`` that case counts zero exceedances and reports ``p = 1/(B+1)``, turning the
    weakest possible evidence into the strongest possible rejection. Measured before
    the fix: SPA's empirical size at T=120, K=1 was 10.9% against a nominal 5%,
    because the single-model family lands in that atom often. With ``>=`` it is
    ~5%."""
    count = int(np.sum(np.asarray(null_stats, float) >= float(observed)))
    return float((1 + count) / (len(null_stats) + 1))


def _rc_core(losses_benchmark, losses_models, *, block, B, seed):
    """Shared setup for RC and SPA: differentials, degeneracy screen, bootstrap
    means. Returns ``(payload_or_None, ctx)`` — a non-None payload is an abstention
    the caller must return verbatim."""
    d, keys, all_nan, bench_all_nan = _rc_prepare(losses_benchmark, losses_models)
    K = len(keys)
    T = int(d.shape[0])
    # The block a caller would actually get is resolved BEFORE any abstention, so a
    # refusal reports the block that would have been used rather than echoing the
    # caller's un-resolved ``None`` — an abstention that reports ``block: None`` names
    # nothing an auditor can reproduce.
    blk = _rc_auto_block(max(T, 1)) if block is None else int(block)
    if block is not None and int(block) < 1:
        # NOT coerced.  ``max(1, ...)`` used to turn block=0 or block=-5 into an iid
        # bootstrap of a serially-correlated differential and report ``block: 1`` as
        # if the caller had asked for it.  A non-positive block is a caller error.
        return _rc_abstain(f"non_positive_block:{int(block)}", n_models=K, n_obs=T,
                           block=int(block), B=B), None
    if int(B) < 2:
        # np.percentile / a max over an empty null is not a p-value; ``(1+0)/(0+1)``
        # returned a confident 1.0 out of zero draws.
        return _rc_abstain(f"insufficient_bootstrap_draws_lt_2:{int(B)}", n_models=K,
                           n_obs=T, block=blk, B=B), None
    if K < 1:
        return _rc_abstain("no_models", n_models=K, n_obs=T, block=blk, B=B), None
    if bench_all_nan:
        # Named BEFORE the row-count screen: an all-NaN benchmark leaves zero complete
        # cases, and reporting that as "insufficient_obs_lt_20" names something other
        # than the actual defect.
        return _rc_abstain("all_nan_benchmark", n_models=K, n_obs=T, block=blk, B=B), None
    if all_nan:
        return _rc_abstain(f"all_nan_model_columns:{sorted(map(str, all_nan))}",
                           n_models=K, n_obs=T, block=blk, B=B), None
    if T < 20:
        return _rc_abstain("insufficient_obs_lt_20", n_models=K, n_obs=T, block=blk, B=B), None
    sd = d.std(axis=0, ddof=1)
    dead = [str(keys[i]) for i in range(K) if not np.isfinite(sd[i]) or sd[i] <= 0.0]
    if dead:
        return _rc_abstain(f"zero_variance_loss_differential:{sorted(dead)}",
                           n_models=K, n_obs=T, block=blk, B=B), None
    blk = min(blk, T)
    boot = _rc_boot_means(d, blk, int(B), int(seed))
    return None, {"d": d, "keys": keys, "T": T, "K": K, "block": blk,
                  "dbar": d.mean(axis=0), "boot": boot}


def reality_check(losses_benchmark, losses_models, *, block=None, B: int = 2000,
                  seed: int = 7) -> dict:
    """White's (2000) Reality Check for data snooping over a family of K models.

    Inputs are PER-PERIOD LOSSES (or negative performance): ``losses_benchmark`` is
    the benchmark's loss series, ``losses_models`` the K competing models as columns
    (DataFrame / dict of series / 2-D array). The test works on
    ``d_k = L_benchmark - L_k``, so a POSITIVE ``d_k`` means model k beats the
    benchmark.

    Null: ``max_k E[d_k] <= 0`` — no model in the family beats the benchmark. The
    statistic is ``max_k sqrt(T) * mean(d_k)``; its null distribution comes from a
    circular block bootstrap of the differentials recentred at their sample means
    (White's least-favourable configuration, all K means at zero), and the p-value is
    the share of bootstrap maxima exceeding the observed one. Because the maximum is
    taken over the SAME bootstrap draw for every model, the correlation between
    near-duplicate candidates is priced rather than assumed away.

    ``block`` defaults to ``max(1, round(T ** (1/3)))`` (see ``_rc_auto_block``);
    ``seed`` makes every call reproducible — there is no unseeded path.

    RC is known to be conservative when the family contains poor models: a single
    hopeless candidate inflates the bootstrap maximum and buries a genuinely good
    one. ``spa_test`` is the studentized, recentred fix; report both.

    Degenerate families return an abstention dict with ``abstained=True`` and a named
    ``reason`` instead of a number, and the reason names the ACTUAL defect:
    ``no_models``, ``all_nan_benchmark`` (screened before the row count, which would
    otherwise report a missing benchmark as ``insufficient_obs_lt_20``),
    ``all_nan_model_columns``, ``insufficient_obs_lt_20``,
    ``zero_variance_loss_differential``, ``non_positive_block`` (a caller error, not
    silently coerced to an iid bootstrap) and ``insufficient_bootstrap_draws_lt_2``
    (``B <= 1`` has no null distribution to compare against, and the
    ``(1 + 0) / (0 + 1)`` arithmetic would report a confident ``p = 1.0`` from zero
    draws).  The ``block`` field of an abstention is the block that WOULD have been
    used, resolved, never the caller's un-resolved ``None``."""
    early, ctx = _rc_core(losses_benchmark, losses_models, block=block, B=B, seed=seed)
    if early is not None:
        return early
    T, K, dbar, boot = ctx["T"], ctx["K"], ctx["dbar"], ctx["boot"]
    root = math.sqrt(T)
    stat = float(np.max(root * dbar))
    null_max = np.max(root * (boot - dbar), axis=1)
    p = _rc_mc_pvalue(null_max, stat)
    best = int(np.argmax(dbar))
    return {"statistic": round(stat, 6), "p_value": round(p, 6), "n_models": K,
            "n_obs": T, "block": ctx["block"], "B": int(B),
            "best_model": ctx["keys"][best], "recentred_models": K,
            "abstained": False, "reason": None}


def spa_test(losses_benchmark, losses_models, *, block=None, B: int = 2000,
             seed: int = 7) -> dict:
    """Hansen's (2005) Superior Predictive Ability test — the CONSISTENT variant (SPA_c).

    Same inputs and same ``d_k = L_benchmark - L_k`` convention as ``reality_check``,
    and the same null (``max_k E[d_k] <= 0``). Two differences, both of which matter:

    1. STUDENTIZATION. The statistic is
       ``max(0, max_k sqrt(T) * mean(d_k) / omega_k)`` where ``omega_k`` is the
       bootstrap standard error of ``sqrt(T) * mean(d_k)`` (the block bootstrap's own
       long-run standard deviation, Hansen's recommended estimator). Without it the
       maximum is dominated by whichever model happens to be noisiest.

    2. RECENTERING (this is the ``_c`` in SPA_c). Only models satisfying
       ``mean(d_k) >= -sqrt((omega_k ** 2 / T) * 2 * log(log(T)))`` are recentred at
       their sample mean and so CONTRIBUTE to the bootstrap null; every model below
       that threshold is recentred at zero instead, which pushes its bootstrap draws
       deep into the negative and removes it from the maximum. That is what stops one
       hopeless candidate from burying a good one, as it does under RC. The
       ``recentred_models`` field reports how many models CONTRIBUTE (pass the
       threshold); ``n_models - recentred_models`` were dropped to zero.
       The threshold is the consistent (SPA_c) rate. ``p_value`` IS SPA_c — one
       variant, named, is the reported number. Hansen's two bracketing variants ride
       along as diagnostics rather than as a menu: ``p_value_upper`` is SPA_u (every
       model kept, conservative, = studentized RC) and ``p_value_lower`` is SPA_l
       (every model dropped, liberal). They exist so the finite-sample slack in SPA_c
       is auditable from the return value; picking whichever of the three is smallest
       is p-hacking with three names, and no code here does it.

    ``block`` defaults to ``max(1, round(T ** (1/3)))``; ``seed`` is explicit and the
    result is bit-identical across calls. Degenerate families abstain exactly as in
    ``reality_check``.

    SIZE: SPA_c is the more liberal of the two tests at every sample length measured
    (7.9% at T=120 against a nominal 5%, 5.9% at T=500, and ~12% on a short
    serially-correlated panel). See the measured grid in the section comment above
    ``reality_check`` before reading a marginal p-value as a result."""
    early, ctx = _rc_core(losses_benchmark, losses_models, block=block, B=B, seed=seed)
    if early is not None:
        return early
    T, K, dbar, boot = ctx["T"], ctx["K"], ctx["dbar"], ctx["boot"]
    root = math.sqrt(T)
    Z = root * (boot - dbar)                       # (B, K) mean-zero bootstrap draws
    omega = Z.std(axis=0, ddof=1)
    if not np.all(np.isfinite(omega)) or np.any(omega <= 0.0):
        return _rc_abstain("zero_bootstrap_standard_error", n_models=K, n_obs=T,
                           block=ctx["block"], B=B)
    t_k = root * dbar / omega
    stat = float(max(0.0, float(np.max(t_k))))
    thresh = np.sqrt((omega ** 2 / T) * 2.0 * math.log(math.log(T)))
    keep = dbar >= -thresh                         # Hansen's consistent recentering

    def _p(centre):
        null_t = (root * (boot - centre)) / omega
        return _rc_mc_pvalue(np.maximum(0.0, np.max(null_t, axis=1)), stat)

    # Hansen's three recentring thresholds, from most to least permissive:
    # SPA_u keeps every model (threshold -inf), SPA_c keeps those above -A_k, SPA_l
    # keeps only models that beat the benchmark in sample (threshold 0). Dropping a
    # model shrinks the bootstrap null, so p_lower <= p_value <= p_upper by
    # construction.
    p = _p(np.where(keep, dbar, 0.0))              # SPA_c — the reported p-value
    p_upper = _p(dbar)                             # SPA_u — every model kept
    p_lower = _p(np.where(dbar >= 0.0, dbar, 0.0))  # SPA_l — only in-sample winners
    best = int(np.argmax(t_k))
    return {"statistic": round(stat, 6), "p_value": round(p, 6), "n_models": K,
            "n_obs": T, "block": ctx["block"], "B": int(B),
            "best_model": ctx["keys"][best], "recentred_models": int(keep.sum()),
            "p_value_upper": round(p_upper, 6), "p_value_lower": round(p_lower, 6),
            "abstained": False, "reason": None}
