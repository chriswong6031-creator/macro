"""Partial-pooling weight engine — the deterministic loop that #13/#19 said couldn't close.

The audit's deadlock (#19): every self-calibrating gate uses a ``min_n=20 else 1.0`` cliff,
and the data-collection design can never produce 20 graded same-channel samples, so the
"adaptive" weights stay hand-set forever and "building" is indistinguishable from "starved".
This module replaces that cliff with HIERARCHICAL EMPIRICAL-BAYES SHRINKAGE so a weight moves
*a little* immediately and nothing swings on n=5.

THREE HARD SAFETY PROPERTIES (from the masterplan + the China reassessment Q6)
-----------------------------------------------------------------------------
(a) SHRINK TOWARD ZERO, NOT OPTIMISM. Two of the China suite's proposed confirmer legs
    measured WRONG-SIGN; shrinking toward a "weakly positive" prior would institutionalize a
    drain. So the global prior is 0 (no edge) and a reliably-wrong leg's pooled weight can go
    NEGATIVE. ``pooled_weight`` is a shrunken *signed* mean — never floored at a positive prior.

(b) HIERARCHICAL — per-member weights shrink toward their FAMILY mean, and the family mean
    itself shrinks toward the global 0. So n=5 in a family of 6 borrows strength from its
    five siblings and moves a little, instead of being stuck at the equal-weight prior until
    it clears an unreachable min-n. This is what kills the min-n cliff.

(c) TRUST-REGION + CAPABILITY GATES (the risk_radar_intl bounded-tuner pattern). A weight
    moves at most ``MAX_STEP`` per update from its current value; the whole vector is
    L1-renormalised so it stays a convex-ish blend; and nothing arms until an ARMING
    PREDICATE holds (≥ MIN_FAMILY_N effective graded events per family AND the pooled vector
    beats equal-weight on held-out spine data). Never free-fits on tiny n.

THE MATH (deliberately simple, fully deterministic, no scipy)
-------------------------------------------------------------
For a member m with n_m effective graded events and signed-outcome mean x̄_m and variance s²_m:

    reliability_m = n_m / (n_m + K)                       # 0 at cold-start → 1 as n→∞
    shrunk_m      = reliability_m * x̄_m                   # toward ZERO (property a)
    family_mean   = Σ reliability_m·x̄_m / Σ reliability_m  # precision-weighted family center
    pooled_m      = λ·shrunk_m + (1-λ)·(reliability_fam·family_mean)   # borrow strength (b)

``K`` is the pooling strength (higher = more shrinkage; the "prior sample size"). The
measurement-error inflation from the leakage-tax flip rates (Q6) enters as an OPTIONAL
per-member ``noise`` that reduces reliability, so a replay-fragile leg is trusted less.

Weights = a monotone transform of pooled signed edge, renormalised, trust-region-capped
against the caller's current weights. Everything degrades gracefully: zero graded data →
equal weights (the honest cold-start), never a crash, never a fabricated tilt.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

log = logging.getLogger(__name__)

__all__ = [
    "MemberStat",
    "member_stats_from_outcomes",
    "pooled_edges",
    "pooled_weights",
    "trust_region_step",
    "arming",
    "ArmStatus",
]

# --- pooling / trust-region constants (mirrors risk_radar_intl_tune's bounded knobs) ----
K_POOL = 8.0            # prior sample size: reliability = n/(n+K). n=8 → half-trusted.
LAMBDA_SELF = 0.6       # weight on the member's own shrunk edge vs the family mean.
MAX_STEP = 0.10         # max L1 move of any single weight per update (trust region).
MIN_FAMILY_N = 12       # effective graded events a family needs before it can ARM.
MIN_MEMBER_N = 3        # a member with fewer than this borrows PURELY from the family mean.
HELDOUT_FRAC = 0.3      # fraction of events reserved to test pooled-beats-equal (arming).


@dataclass
class MemberStat:
    """Sufficient statistics for one poolable member (a lane / channel / desk)."""
    key: str
    n: float            # effective graded events (co-firing-collapsed)
    mean: float         # signed-outcome mean (positive = correct-direction edge)
    var: float = 1.0    # outcome variance (defaults to 1 → n-only reliability)
    noise: float = 0.0  # extra measurement-error variance (leakage-tax flip inflation)

    def reliability(self, k: float = K_POOL) -> float:
        """n/(n+K), further discounted by measurement noise. In [0, 1)."""
        if self.n <= 0:
            return 0.0
        rel = self.n / (self.n + k)
        if self.noise > 0:
            rel *= 1.0 / (1.0 + self.noise)     # a noisy leg is trusted less
        return max(0.0, min(0.999, rel))


def member_stats_from_outcomes(
    outcomes: Mapping[str, Sequence[float]],
    noise: Mapping[str, float] | None = None,
) -> list[MemberStat]:
    """Build MemberStat list from {member_key: [signed_outcome, ...]}. Empty lists → n=0
    cold-start members (reliability 0, so they shrink entirely to the family/global prior)."""
    noise = noise or {}
    out = []
    for key, xs in outcomes.items():
        xs = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
        n = float(len(xs))
        if n == 0:
            out.append(MemberStat(key=key, n=0.0, mean=0.0, var=1.0, noise=noise.get(key, 0.0)))
            continue
        mean = sum(xs) / n
        var = (sum((x - mean) ** 2 for x in xs) / n) if n > 1 else 1.0
        out.append(MemberStat(key=key, n=n, mean=mean, var=max(var, 1e-9),
                              noise=noise.get(key, 0.0)))
    return out


def pooled_edges(members: Sequence[MemberStat], *, k: float = K_POOL,
                 lam: float = LAMBDA_SELF) -> dict[str, float]:
    """Hierarchical empirical-Bayes SIGNED pooled edge per member. Shrinks toward ZERO
    (global prior, property a) and borrows strength from the precision-weighted family mean
    (property b). A reliably-wrong member keeps a NEGATIVE pooled edge."""
    if not members:
        return {}
    # precision-weighted family center (members with more reliability pull it more)
    num = sum(m.reliability(k) * m.mean for m in members)
    den = sum(m.reliability(k) for m in members)
    family_mean = (num / den) if den > 1e-9 else 0.0
    rel_fam = den / (den + 1.0)     # the family's own reliability (shrinks family→global 0)

    pooled: dict[str, float] = {}
    for m in members:
        rel = m.reliability(k)
        shrunk_self = rel * m.mean                     # toward zero
        borrowed = rel_fam * family_mean               # the family prior (already shrunk to 0)
        # a very-low-n member (< MIN_MEMBER_N) leans almost entirely on the family
        w_self = lam if m.n >= MIN_MEMBER_N else lam * (m.n / MIN_MEMBER_N)
        pooled[m.key] = w_self * shrunk_self + (1.0 - w_self) * borrowed
    return pooled


def pooled_weights(members: Sequence[MemberStat], *, k: float = K_POOL,
                   lam: float = LAMBDA_SELF, floor: float = 0.0) -> dict[str, float]:
    """Deterministic weight vector from pooled signed edges. A member with a NEGATIVE pooled
    edge gets a weight BELOW the equal-weight baseline (and can be clipped to ``floor``); a
    positive edge gets more. Renormalised to sum to 1 when any positive weight survives, else
    falls back to equal weights (honest cold-start). This is the deterministic path #13 says
    never existed."""
    keys = [m.key for m in members]
    if not keys:
        return {}
    eq = 1.0 / len(keys)
    edges = pooled_edges(members, k=k, lam=lam)
    if not any(abs(v) > 1e-9 for v in edges.values()):
        return {kk: eq for kk in keys}                 # nothing learned yet → equal weights

    # map signed edge → a multiplicative tilt around the equal weight, bounded so no single
    # member can dominate on thin evidence. tanh keeps it smooth and bounded in (-1, 1).
    raw = {}
    for kk in keys:
        tilt = math.tanh(edges[kk] * 4.0)              # scale: a +0.25 edge → ~+0.76 tilt
        raw[kk] = max(floor, eq * (1.0 + tilt))
    tot = sum(raw.values())
    if tot <= 1e-12:
        return {kk: eq for kk in keys}
    return {kk: raw[kk] / tot for kk in keys}


def trust_region_step(current: Mapping[str, float], target: Mapping[str, float],
                      *, max_step: float = MAX_STEP) -> dict[str, float]:
    """Move ``current`` toward ``target`` along the (current→target) direction by at most
    ``max_step`` on the largest-moving key, so NO weight moves more than ``max_step`` and the
    result still sums to 1 without a renorm blow-up. The bounded-step guard from
    risk_radar_intl_tune: a self-tuning weight can't jump off a cliff on one noisy update.

    Both current and target sum to ~1, so the full move vector already conserves mass; we only
    SCALE it down by a global factor α ≤ 1 chosen so the biggest single move is ``max_step``.
    That keeps the step within the trust region AND mass-conserving (no post-hoc renorm can
    inflate a key past the bound)."""
    keys = list(target.keys())
    if not keys:
        return dict(current)
    eq = 1.0 / len(keys)
    cur = {kk: float(current.get(kk, eq)) for kk in keys}
    deltas = {kk: float(target.get(kk, eq)) - cur[kk] for kk in keys}
    max_delta = max((abs(d) for d in deltas.values()), default=0.0)
    if max_delta <= 1e-12:
        return {kk: cur[kk] for kk in keys}
    alpha = min(1.0, max_step / max_delta)              # scale so the largest move == max_step
    stepped = {kk: max(0.0, cur[kk] + alpha * deltas[kk]) for kk in keys}
    tot = sum(stepped.values())
    if tot <= 1e-12:
        return {kk: eq for kk in keys}
    return {kk: stepped[kk] / tot for kk in keys}


@dataclass
class ArmStatus:
    """The arming decision + its distance-to-arming (the 'armory' report shape)."""
    armed: bool
    n_eff: float
    need_n: float
    pooled_beats_equal: bool | None
    heldout_edge_pooled: float | None
    heldout_edge_equal: float | None
    reason: str

    def to_dict(self) -> dict:
        return {
            "armed": self.armed, "n_eff": round(self.n_eff, 2), "need_n": self.need_n,
            "pooled_beats_equal": self.pooled_beats_equal,
            "heldout_edge_pooled": (round(self.heldout_edge_pooled, 5)
                                    if self.heldout_edge_pooled is not None else None),
            "heldout_edge_equal": (round(self.heldout_edge_equal, 5)
                                   if self.heldout_edge_equal is not None else None),
            "reason": self.reason,
        }


def arming(events: Sequence[dict], *, k: float = K_POOL, lam: float = LAMBDA_SELF,
           min_family_n: float = MIN_FAMILY_N, heldout_frac: float = HELDOUT_FRAC) -> ArmStatus:
    """The ARM-BY-EVIDENCE predicate (no env flags). Given a time-ordered list of graded
    events ``[{key, event_key, outcome, as_of}, ...]`` for ONE family, decide whether the
    pooled weights may go LIVE. Two conditions, both required:

      1. ≥ ``min_family_n`` effective (co-firing-collapsed) graded events in the family.
      2. On a chronological held-out tail, the pooled weights produce a HIGHER realized edge
         than equal weights (pooled must EARN the flip — never armed on in-sample fit).

    Returns an ArmStatus carrying distance-to-arming so an 'armory' report can show progress.
    Deterministic; degrades to not-armed (never crashes) on thin/degenerate data."""
    ev = [e for e in events if e.get("outcome") is not None]
    n_eff = float(len({e.get("event_key") or f"{e.get('key')}:{e.get('as_of')}" for e in ev}))
    if n_eff < min_family_n:
        return ArmStatus(False, n_eff, float(min_family_n), None, None, None,
                         f"accruing: {n_eff:.0f}/{min_family_n:.0f} effective events")

    # chronological split — fit pooling on the first (1-heldout), test on the tail.
    ev_sorted = sorted(ev, key=lambda e: str(e.get("as_of") or ""))
    cut = max(1, int(len(ev_sorted) * (1.0 - heldout_frac)))
    train, test = ev_sorted[:cut], ev_sorted[cut:]
    if not test:
        return ArmStatus(False, n_eff, float(min_family_n), None, None, None,
                         "no held-out tail to validate on yet")

    # per-key signed outcomes on train → pooled weights
    by_key: dict[str, list[float]] = {}
    for e in train:
        by_key.setdefault(str(e.get("key")), []).append(float(e["outcome"]))
    members = member_stats_from_outcomes(by_key)
    pooled = pooled_weights(members, k=k, lam=lam)
    keys = list(pooled.keys()) or list(by_key.keys())
    eqw = {kk: 1.0 / len(keys) for kk in keys} if keys else {}

    # realized edge on the held-out tail = weight(key) · outcome, averaged. A weighting that
    # up-weights the keys that keep predicting scores higher.
    def realized(weights):
        num = den = 0.0
        for e in test:
            w = weights.get(str(e.get("key")))
            if w is None:
                continue
            num += w * float(e["outcome"]); den += w
        return (num / den) if den > 1e-9 else 0.0

    ep, ee = realized(pooled), realized(eqw)
    beats = ep > ee
    return ArmStatus(
        armed=bool(beats), n_eff=n_eff, need_n=float(min_family_n),
        pooled_beats_equal=beats, heldout_edge_pooled=ep, heldout_edge_equal=ee,
        reason=("armed: pooled beats equal-weight on held-out tail"
                if beats else "held: pooled does not beat equal-weight out-of-sample"))
