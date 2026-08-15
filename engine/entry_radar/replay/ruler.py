"""W5 inference ruler — per-name-first aggregation + month-cluster bootstrap.

PSS §7 discipline, restated per house pattern (there is no shared helper to
import — `scripts/research/pss_f1_downvol.py` is the copy-per-script precedent):

* the unit of the primary statistic is episode → per-name mean → cross-name mean
  (never pooled-fire-first; E1 errata law);
* uncertainty = month-cluster bootstrap, cluster = calendar month of the
  decision session, NB = 1000, seed pinned per family via ``prereg.seed_for``;
  ticker-only clustering is forbidden (DT-R14) and no API here accepts it;
* two-sided bootstrap p with the (1+count)/(NB+1) correction; a cluster-robust
  t over monthly means is PRINTED ALONGSIDE every bootstrap p (the
  normal-approx-at-few-blocks disclosure) — BH is keyed on the bootstrap p.

Pure numpy/pandas; no I/O; deterministic under the injected seed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
import pandas as pd

from engine.entry_radar.replay import prereg


@dataclass(frozen=True)
class RulerResult:
    """One inferential read: estimate, CI, p, and its disclosure companions."""

    stat: float                 # per-name-first point estimate
    ci_low: float               # 2.5th percentile (bootstrap)
    ci_high: float              # 97.5th percentile (bootstrap)
    p_boot: float               # two-sided bootstrap p ((1+c)/(NB+1) corrected)
    t_cluster: float | None     # t over monthly means (printed, never keyed)
    n_episodes: int
    n_names: int
    n_months: int               # honest-N clusters (distinct decision months)
    eff_names: float            # 1/HHI over per-name episode shares (§12 floor)
    nb: int
    seed: int

    def floors_met(self) -> bool:
        """§12 grading floors for ONE arm's inputs (arms are checked separately
        by the caller; this covers the pooled-difference table's own sample)."""
        return (self.n_episodes >= prereg.FLOOR_EPISODES_PER_ARM
                and self.n_months >= prereg.FLOOR_DISTINCT_MONTHS
                and self.eff_names >= prereg.FLOOR_EFF_NAMES)


def per_name_first(frame: pd.DataFrame, value_col: str) -> float:
    """Episode rows -> per-name means -> cross-name mean.  NaN rows dropped."""
    sub = frame[["name", value_col]].dropna()
    if sub.empty:
        return float("nan")
    return float(sub.groupby("name")[value_col].mean().mean())


def _month_key(sessions: pd.Series) -> pd.Series:
    d = pd.to_datetime(sessions)
    return d.dt.strftime("%Y-%m")


def month_cluster_bootstrap(
    frame: pd.DataFrame,
    *,
    stat_fn: Callable[[pd.DataFrame], float],
    seed: int,
    nb: int = prereg.NB_BOOTSTRAP,
) -> RulerResult:
    """Bootstrap ``stat_fn`` over month clusters of ``frame``.

    ``frame`` must carry columns ``name`` (ticker), ``session`` (decision
    session), plus whatever ``stat_fn`` reads.  Each replicate draws calendar
    months with replacement (same count as observed), concatenates the drawn
    months' episode rows (duplicates allowed — a month drawn twice contributes
    twice), and recomputes the FULL statistic (per-name-first inside the
    replicate).  A name absent from the drawn months simply drops for that
    replicate.
    """
    if frame.empty:
        return RulerResult(float("nan"), float("nan"), float("nan"), float("nan"),
                           None, 0, 0, 0, 0.0, nb, seed)
    f = frame.copy()
    f["_month"] = _month_key(f["session"])
    months = sorted(f["_month"].unique())
    by_month = {m: g for m, g in f.groupby("_month")}

    point = float(stat_fn(f))
    rng = np.random.default_rng(seed)
    stats = np.empty(nb, dtype=float)
    for i in range(nb):
        draw = rng.choice(months, size=len(months), replace=True)
        rep = pd.concat([by_month[m] for m in draw], ignore_index=True)
        stats[i] = stat_fn(rep)
    stats = stats[np.isfinite(stats)]
    if stats.size == 0:
        ci_lo = ci_hi = p = float("nan")
    else:
        ci_lo, ci_hi = (float(np.percentile(stats, 2.5)),
                        float(np.percentile(stats, 97.5)))
        n_le = int(np.sum(stats <= 0.0))
        n_ge = int(np.sum(stats >= 0.0))
        p = 2.0 * min((1 + n_le) / (stats.size + 1), (1 + n_ge) / (stats.size + 1))
        p = min(1.0, p)

    # cluster-robust t over monthly means of the same statistic's ingredient:
    # the per-month per-name-first value (printed beside p, never keyed).
    monthly = [stat_fn(g) for _, g in f.groupby("_month")]
    monthly_arr = np.asarray([m for m in monthly if np.isfinite(m)], dtype=float)
    if monthly_arr.size >= 2 and float(monthly_arr.std(ddof=1)) > 0.0:
        t = float(monthly_arr.mean()
                  / (monthly_arr.std(ddof=1) / math.sqrt(monthly_arr.size)))
    else:
        t = None

    shares = f["name"].value_counts(normalize=True).to_numpy(dtype=float)
    hhi = float(np.sum(shares ** 2))
    eff_names = (1.0 / hhi) if hhi > 0 else 0.0

    return RulerResult(
        stat=point, ci_low=ci_lo, ci_high=ci_hi, p_boot=float(p), t_cluster=t,
        n_episodes=int(len(f)), n_names=int(f["name"].nunique()),
        n_months=int(len(months)), eff_names=eff_names, nb=nb, seed=seed,
    )


def difference_stat(value_col: str, arm_col: str,
                    arm_a: str, arm_b: str) -> Callable[[pd.DataFrame], float]:
    """stat_fn factory: per-name-first mean of arm A minus arm B, computed
    INSIDE each replicate (both arms resampled on the same drawn months)."""
    def _stat(frame: pd.DataFrame) -> float:
        a = per_name_first(frame[frame[arm_col] == arm_a], value_col)
        b = per_name_first(frame[frame[arm_col] == arm_b], value_col)
        return a - b
    return _stat


def bh_fdr(pvals: dict[str, float], q: float = prereg.BH_Q,
           m_total: int = prereg.BH_M_TOTAL) -> dict[str, bool]:
    """Benjamini–Hochberg at q with the denominator FIXED at ``m_total`` (§10,
    M2 fix): an ungraded question contributes no rejection and never shrinks
    the denominator, so a partially-graded family is judged conservatively
    against the full declared family size.

    Returns {question: survives} over the graded (finite-p) questions only;
    the caller discloses whenever the graded set is smaller than ``m_total``.
    """
    items = [(k, v) for k, v in pvals.items() if v is not None and np.isfinite(v)]
    if not items:
        return {}
    m = max(int(m_total), len(items))
    items.sort(key=lambda kv: kv[1])
    survives_rank = 0
    for i, (_, p) in enumerate(items, start=1):
        if p <= q * i / m:
            survives_rank = i
    out = {k: (i <= survives_rank) for i, (k, _) in enumerate(items, start=1)}
    return out


def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson CI for a rate (false-start tables); (nan, nan) when n == 0."""
    if n <= 0:
        return float("nan"), float("nan")
    phat = hits / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return center - half, center + half


__all__ = ["RulerResult", "per_name_first", "month_cluster_bootstrap",
           "difference_stat", "bh_fdr", "wilson_interval"]
