"""Vendor-shaped scoring — 0-100 percentiles, and the rule that turns legs into a score.

Three rules, and it matters that two of them are the SAME ranking:

    rank_then_blend   score = sum_i w_i * pct(leg_i)            bounded by its inputs
    blend_then_rank   score = pct(sum_i w_i * pct(leg_i))       SAME ORDER, different values
    z_then_rank       score = pct(sum_i w_i * z(leg_i))         a genuinely different order

`blend_then_rank` is a monotone transform of `rank_then_blend`, so the two produce an
IDENTICAL leaderboard and differ only in the printed number. That is not a technicality —
it is the whole explanation of Fintel's strangest published numbers. On the 2023-08-21
board MCEM (86.15 / 89.66 / 75.60 -> 91.04) and WSM (85.06 / 89.83 / 74.55 -> 90.64) each
score ABOVE every one of their own sub-scores. No CONVEX weighted average can exceed its
inputs, so Fintel re-percentiles the blend: being good on three legs at once is rarer than
being good on any one, so the joint blend has a thin upper tail that re-ranking stretches.
`exceeds_all_subscores()` is the check that refutes the un-re-ranked reading; note it does
NOT refute an affine blend, and the fitted weights below do sum above 1 with a negative
intercept — which is what a locally-linearised rank map looks like.

`z_then_rank` is the one that reorders, because z-scores let a single extreme leg carry a
name that percentiles would cap at 100. On this panel the raw legs are ratio explosions off
tiny denominators (fcf_to_debt reaches 871x), so z-space blending is the more fragile
choice — but it is the one most vendors actually use, so it is offered and measured rather
than assumed away. `rule_divergence()` reports how far apart the two orderings land.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.quant_lab.specs import FINTEL_OBSERVED_SCORES

# Fintel prints scores on 0-100 where 50 is the universe average — i.e. a percentile rank.
SCORE_MIN, SCORE_MAX = 0.0, 100.0


def percentile_score(s: pd.Series, *, min_n: int = 20) -> pd.Series:
    """Cross-sectional percentile rank on 0-100 (higher = better), NaN-preserving.

    `min_n` is a floor on the number of ranked names: a percentile over a handful of names
    is a rank dressed up as a population statistic, and the vendor's own framing ("50 is
    the average") only means anything against a real cross-section. Below the floor we
    return all-NaN rather than a confident-looking number.
    """
    v = pd.to_numeric(pd.Series(s), errors="coerce")
    valid = v.notna()
    if int(valid.sum()) < min_n:
        return pd.Series(np.nan, index=v.index, dtype=float)
    # average ties, then scale to (0, 100]; pct=True gives (0, 1]
    return (v.rank(pct=True, na_option="keep") * SCORE_MAX).astype(float)


def _winsor_z(s: pd.Series, cap: float = 3.0) -> pd.Series:
    """Winsorised cross-sectional z-score. Mandatory here: the raw legs are ratios off
    small denominators (fcf_to_debt reaches 871x on this panel) and an un-winsorised z
    would let one accounting artifact dominate every blend it appears in."""
    v = pd.to_numeric(pd.Series(s), errors="coerce")
    mu, sd = v.mean(), v.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(np.nan, index=v.index, dtype=float)
    return ((v - mu) / sd).clip(-cap, cap)


def _weighted_blend(vals: pd.DataFrame, weights: dict[str, float],
                    min_legs: int) -> tuple[pd.Series, pd.Series]:
    """Weight-renormalised blend over the legs a name actually has, plus the leg COUNT.

    A name missing a leg is scored on its remaining legs with the weights renormalised,
    NOT imputed to the median — imputing would quietly reward missing data, which on this
    panel correlates with being small and thinly covered (exactly the names the model is
    supposed to discriminate between).

    But renormalising is not free either, and `min_legs` is where that bill is paid. A
    name scored on 2 of 6 legs is not comparable to one scored on 6: it only has to be
    good at two things, so it floats to the top of a board it was never really evaluated
    for. The first run of this scorer put YOU, PTON and DBX (3 legs each) above ADBE
    (6 legs) for exactly that reason. The leg count is returned so callers can show it and
    the default floor is a supermajority, not 2.
    """
    cols = [c for c in vals.columns if c in weights]
    if not cols:
        nan = pd.Series(np.nan, index=vals.index, dtype=float)
        return nan, pd.Series(0, index=vals.index, dtype=int)
    P = vals[cols].astype(float)
    W = pd.DataFrame({c: np.where(P[c].notna(), float(weights[c]), np.nan) for c in cols},
                     index=P.index)
    wsum = W.sum(axis=1, skipna=True)
    num = (P * W).sum(axis=1, skipna=True)
    n_used = P.notna().sum(axis=1).astype(int)
    out = (num / wsum.replace(0.0, np.nan)).where(n_used >= min_legs)
    return out, n_used


def default_min_legs(n_legs: int) -> int:
    """A supermajority of the model's legs — ceil(2/3), floor 2.

    Not a tuned parameter: the point is only that a name must be evaluated on most of the
    model before it can be ranked BY the model.
    """
    return max(2, int(np.ceil(2 * n_legs / 3)))


RULES = ("blend_then_rank", "rank_then_blend", "z_then_rank")


def composite(legs: pd.DataFrame, weights: dict[str, float] | None = None, *,
              rule: str = "blend_then_rank", min_legs: int | None = None,
              min_n: int = 20) -> dict:
    """Score a leg cross-section the way the vendor appears to.

    `legs` is a ticker-indexed frame of RAW leg values, already oriented so that higher is
    better. Returns the per-leg percentiles and the per-name leg count alongside the
    composite, so a surface can show both the decomposition Fintel prints (Quality /
    Value / Momentum / total) and how much of the model each name was actually judged on.
    """
    if rule not in RULES:
        raise ValueError(f"unknown combination rule: {rule!r} (expected one of {RULES})")
    legs = pd.DataFrame(legs)
    weights = weights or {c: 1.0 for c in legs.columns}
    if min_legs is None:
        min_legs = default_min_legs(len([c for c in legs.columns if c in weights]))

    pcts = pd.DataFrame({c: percentile_score(legs[c], min_n=min_n) for c in legs.columns})
    basis = pd.DataFrame({c: _winsor_z(legs[c]) for c in legs.columns}) \
        if rule == "z_then_rank" else pcts
    blend, n_used = _weighted_blend(basis, weights, min_legs)
    # rank_then_blend keeps the blend as the score; the other two re-percentile it.
    score = blend if rule == "rank_then_blend" else percentile_score(blend, min_n=min_n)

    return {
        "score": score,
        "leg_pct": pcts,
        "blend": blend,
        "n_legs_used": n_used,
        "rule": rule,
        "weights": {k: float(v) for k, v in weights.items() if k in legs.columns},
        "n_scored": int(score.notna().sum()),
        "n_universe": int(len(legs)),
        "min_legs": int(min_legs),
    }


# ---------------------------------------------------------------------------------------
# Recovering Fintel's rule from Fintel's own printed numbers.
# ---------------------------------------------------------------------------------------
def observed_frame() -> pd.DataFrame:
    return pd.DataFrame(FINTEL_OBSERVED_SCORES,
                        columns=["ticker", "quality", "value", "momentum", "qvm"]
                        ).set_index("ticker")


def exceeds_all_subscores(df: pd.DataFrame | None = None) -> list[str]:
    """Names whose published QVM beats every one of their own sub-scores.

    A non-empty result refutes any CONVEX weighted average (a convex mean is bounded by
    its inputs), which is the load-bearing check behind `combination.rule =
    "blend_then_rank"` in specs.py. On the published board this returns exactly MCEM and
    WSM — two counterexamples, which is enough. It does NOT refute an affine blend with
    weights summing above 1, and the fit below finds precisely that; both readings point
    at the same re-percentiling step.
    """
    d = observed_frame() if df is None else df
    hi = d[["quality", "value", "momentum"]].max(axis=1)
    return sorted(d.index[d["qvm"] > hi].tolist())


def fit_observed_weights(df: pd.DataFrame | None = None) -> dict:
    """OLS fit of published QVM on its published sub-scores.

    HONESTY: n = 10, from ONE date, and every row is a high scorer the vendor chose to
    print. The fit therefore describes the TOP-DECILE neighbourhood of the rank map, where
    a percentile transform is locally affine. It is not the global rule and must not be
    presented as one. The slope sum exceeding 1 with a negative intercept is itself the
    fingerprint of that re-ranking step.
    """
    d = observed_frame() if df is None else df
    X = np.column_stack([d[["quality", "value", "momentum"]].to_numpy(float),
                         np.ones(len(d))])
    y = d["qvm"].to_numpy(float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    resid = y - pred
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "weights": {"quality": float(beta[0]), "value": float(beta[1]),
                    "momentum": float(beta[2])},
        "intercept": float(beta[3]),
        "weight_sum": float(beta[:3].sum()),
        "r2": float(1 - (resid ** 2).sum() / ss_tot) if ss_tot > 0 else float("nan"),
        "max_abs_resid": float(np.abs(resid).max()),
        "rmse": float(np.sqrt((resid ** 2).mean())),
        "n": int(len(d)),
        "exceeds_all_subscores": exceeds_all_subscores(d),
        "caveat": ("n=10, single date, high-scorers only — a LOCAL top-decile fit, not the "
                   "global combination rule."),
    }


def rule_divergence(legs: pd.DataFrame, weights: dict[str, float] | None = None,
                    *, top_n: int = 20, min_legs: int | None = None) -> dict:
    """How much the blending BASIS changes the leaderboard on a real cross-section.

    Compares percentile-space blending against z-space blending. It deliberately does NOT
    compare blend_then_rank against rank_then_blend: those are monotone transforms of each
    other and always agree on order, so such a "divergence" measure would report 20/20
    overlap on every input and prove nothing — a vacuous check that looks like a passing
    one. The real fork is rank-space vs z-space, where a single extreme leg can carry a
    name in z-space that percentiles would cap.
    """
    a = composite(legs, weights, rule="blend_then_rank", min_legs=min_legs)["score"]
    b = composite(legs, weights, rule="z_then_rank", min_legs=min_legs)["score"]
    j = pd.concat([a.rename("pct_space"), b.rename("z_space")], axis=1).dropna()
    if len(j) < max(top_n, 10):
        return {"comparable": False, "n": int(len(j)),
                "note": f"only {len(j)} jointly-scored names — below the {top_n}-name floor"}
    ta = set(j["pct_space"].nlargest(top_n).index)
    tb = set(j["z_space"].nlargest(top_n).index)
    return {
        "comparable": True,
        "n": int(len(j)),
        "top_n": top_n,
        "overlap": len(ta & tb),
        "overlap_frac": round(len(ta & tb) / top_n, 3),
        "spearman": round(float(j["pct_space"].rank().corr(j["z_space"].rank())), 4),
        "only_pct_space": sorted(ta - tb),
        "only_z_space": sorted(tb - ta),
    }
