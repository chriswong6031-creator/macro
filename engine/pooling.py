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
    beats equal-weight on held-out spine data BY A PRE-REGISTERED MARGIN — see below).
    Never free-fits on tiny n.

THE ARMING MARGIN (pre-registered 2026-07-25 — why "beats equal-weight" was not enough)
---------------------------------------------------------------------------------------
``arming`` originally required only ``heldout_edge_pooled > heldout_edge_equal`` — a strict
float comparison with NO floor. Measured on the live spine, that predicate armed on margins
as small as **3e-18** (machine epsilon), and at every armed point BOTH held-out edges were
NEGATIVE: the family lost out-of-sample under either weighting, pooled just lost ~3bp less.
Worse, while the family had a single contributing member the test was VACUOUS — one member
means the pooled and equal-weight vectors are the SAME allocation, so the margin is
identically zero and "pooled did not beat equal" was arithmetic, not evidence.

Arming the live desk-weight vector is a PROMOTION to authority, the same class of decision as
``engine.calibration_hub._PROMOTE_MARGIN = 0.05`` ("observed must clear its own null by ≥ 5pp,
not just significantly"). It gets the same kind of bar. Four pre-registered conditions now
stand between the shadow vector and the live one:

  1. ``MIN_FAMILY_N`` effective graded events (unchanged — this gates ACCRUAL).
  2. ``ARM_MIN_HELDOUT_N`` distinct events in the held-out tail. A weighted-mean comparison
     over four observations is not a measurement; at eight, no single held-out event can be
     more than ~1/8 of the verdict. Because ``HELDOUT_FRAC`` is 0.3, this raises the family's
     effective bar to ~27 graded events in practice — deliberately. MIN_FAMILY_N gates when
     the family has enough history to LOOK; this gates whether the TEST can decide anything.
  3. The held-out tail must carry ≥ 2 distinct members. With one member the comparison is
     undefined, not passed — a null result from a vacuous test is not evidence of anything.
  4. ``heldout_edge_pooled`` must be POSITIVE, and must clear ``heldout_edge_equal`` by
     ``max(ARM_MIN_MARGIN, ARM_MIN_MARGIN_REL × held-out outcome scale)``.

Condition 4 is two ideas. The SIGN gate (``ARM_REQUIRE_POSITIVE_EDGE``): a live weight vector
asserts "these weights capture edge", and ``pooled_weights`` can only produce a convex
allocation — it cannot go short. So a negative realized held-out edge means every allocation
over this family loses, and "loses slightly less than equal-weight" is not an edge to arm on.

The MARGIN floor is scale-aware because this module is generic and the caller sets the units,
so the RELATIVE bar (3% of the mean |outcome| on the tail) is the one that normally binds; the
ABSOLUTE bar is a backstop so a family whose outcome scale collapses toward zero cannot arm on
a proportionally large but materially meaningless difference.

WHERE 3% COMES FROM (measured, not assumed — the tilt this module produces is deliberately
bounded by ``tanh``, so the bar has to clear the noise band while staying REACHABLE):

    margin / held-out outcome scale        p50      p99      max
    pure noise, no real separation      0.0010   0.0154   0.0244   (2500 simulated draws,
                                                                    every permitted tail size)
    genuine separation (±3%, sd 4%)     0.0414     —      0.0589   (8 draws, range 0.023-0.059)
    perfect separation at desk scale    0.0521                     (a always right, b always wrong)

3% sits above the 99th percentile of what pure noise produces at the smallest permitted tail —
and above the largest pure-noise excursion observed — while staying under the median of a
genuinely separated family and under the mechanism's own ceiling, so a family that really has
edge can still arm. The margins that provoked this change measured **0.012 of scale**: inside
the pure-noise band, which is the quantitative form of "that is noise, not evidence". Every
bar is an overridable keyword so a caller with a genuinely different endpoint pre-registers its
own in its own module rather than quietly relaxing this one.

Erring strict is the correct asymmetry here, and it costs nothing: display-tier accrual is
untouched by any of these bars (a null NEVER blocks building), the shadow vector keeps being
computed and reported every night, and ``armed: true`` stays what it claims to be — a
statement that the loop is closed on evidence.

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

# --- PRE-REGISTERED ARMING BARS (2026-07-25) ------------------------------------------- #
# The sibling of engine.calibration_hub._PROMOTE_MARGIN. Arming the live weight vector is a
# promotion to authority; a hair's-breadth held-out lift must not buy one. Rationale in the
# module docstring (§THE ARMING MARGIN). Overridable per-caller via arming() keywords.
ARM_MIN_HELDOUT_N = 8      # distinct held-out events required before the test can decide
ARM_MIN_MARGIN = 0.0005    # absolute floor on (pooled − equal) held-out edge
ARM_MIN_MARGIN_REL = 0.03  # ...or 3% of the held-out outcome scale, whichever is LARGER
ARM_REQUIRE_POSITIVE_EDGE = True   # pooled must WIN out-of-sample, not merely lose less
ARM_MIN_MEMBERS = 2        # a one-member family makes the pooled-vs-equal test vacuous


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
    # Pre-registered-margin fields (2026-07-25). ``pooled_beats_equal`` remains the RAW
    # directional comparison so the report can still say "ahead, but not by enough";
    # ``armed`` reflects the full gate.
    margin: float | None = None           # heldout_edge_pooled − heldout_edge_equal
    margin_required: float | None = None  # max(ARM_MIN_MARGIN, rel × held-out outcome scale)
    heldout_n: float | None = None        # distinct events in the held-out tail
    need_heldout_n: float | None = None

    def to_dict(self) -> dict:
        return {
            "armed": self.armed, "n_eff": round(self.n_eff, 2), "need_n": self.need_n,
            "pooled_beats_equal": self.pooled_beats_equal,
            "heldout_edge_pooled": (round(self.heldout_edge_pooled, 5)
                                    if self.heldout_edge_pooled is not None else None),
            "heldout_edge_equal": (round(self.heldout_edge_equal, 5)
                                   if self.heldout_edge_equal is not None else None),
            "margin": round(self.margin, 6) if self.margin is not None else None,
            "margin_required": (round(self.margin_required, 6)
                                if self.margin_required is not None else None),
            "heldout_n": self.heldout_n,
            "need_heldout_n": self.need_heldout_n,
            "reason": self.reason,
        }


def arming(events: Sequence[dict], *, k: float = K_POOL, lam: float = LAMBDA_SELF,
           min_family_n: float = MIN_FAMILY_N, heldout_frac: float = HELDOUT_FRAC,
           min_heldout_n: float = ARM_MIN_HELDOUT_N,
           min_margin: float = ARM_MIN_MARGIN,
           min_margin_rel: float = ARM_MIN_MARGIN_REL,
           require_positive_edge: bool = ARM_REQUIRE_POSITIVE_EDGE,
           min_members: int = ARM_MIN_MEMBERS) -> ArmStatus:
    """The ARM-BY-EVIDENCE predicate (no env flags). Given a time-ordered list of graded
    events ``[{key, event_key, outcome, as_of}, ...]`` for ONE family, decide whether the
    pooled weights may go LIVE. Four conditions, ALL required (see the module docstring
    §THE ARMING MARGIN for why the last three exist):

      1. ≥ ``min_family_n`` effective (co-firing-collapsed) graded events in the family.
      2. ≥ ``min_heldout_n`` distinct events in the chronological held-out tail, carrying
         ≥ ``min_members`` distinct members — below that the pooled-vs-equal comparison
         cannot decide anything, and with one member it is arithmetically vacuous.
      3. The pooled weights produce a POSITIVE realized edge on that tail. Losing less than
         equal-weight is not an edge: ``pooled_weights`` yields a convex allocation, so a
         negative held-out edge means every allocation over this family loses out-of-sample.
      4. That edge clears equal-weight by ``max(min_margin, min_margin_rel × the tail's mean
         |outcome|)`` — a PRE-REGISTERED floor, the sibling of calibration_hub's
         ``_PROMOTE_MARGIN``. Pooled must EARN the flip; it is never armed on in-sample fit,
         on a hair's-breadth lift, or on float dust.

    Returns an ArmStatus carrying distance-to-arming so an 'armory' report can show progress.
    Deterministic; degrades to not-armed (never crashes) on thin/degenerate data."""
    ev = [e for e in events if e.get("outcome") is not None]
    n_eff = float(len({e.get("event_key") or f"{e.get('key')}:{e.get('as_of')}" for e in ev}))
    need_h = float(min_heldout_n)
    if n_eff < min_family_n:
        return ArmStatus(False, n_eff, float(min_family_n), None, None, None,
                         f"accruing: {n_eff:.0f}/{min_family_n:.0f} effective events",
                         need_heldout_n=need_h)

    # chronological split — fit pooling on the first (1-heldout), test on the tail.
    ev_sorted = sorted(ev, key=lambda e: str(e.get("as_of") or ""))
    cut = max(1, int(len(ev_sorted) * (1.0 - heldout_frac)))
    train, test = ev_sorted[:cut], ev_sorted[cut:]
    if not test:
        return ArmStatus(False, n_eff, float(min_family_n), None, None, None,
                         "no held-out tail to validate on yet", heldout_n=0.0,
                         need_heldout_n=need_h)

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
    margin = ep - ee

    # the tail's own outcome scale — the relative bar rides on this so the floor stays
    # meaningful whatever units the caller's endpoint uses (module docstring §THE ARMING MARGIN)
    tail_out = [abs(float(e["outcome"])) for e in test]
    scale = (sum(tail_out) / len(tail_out)) if tail_out else 0.0
    required = max(float(min_margin), float(min_margin_rel) * scale)

    # held-out size + membership: below these the comparison cannot decide anything.
    heldout_n = float(len({e.get("event_key") or f"{e.get('key')}:{e.get('as_of')}"
                           for e in test}))
    test_members = len({str(e.get("key")) for e in test})

    def _held(reason: str) -> ArmStatus:
        return ArmStatus(
            armed=False, n_eff=n_eff, need_n=float(min_family_n), pooled_beats_equal=beats,
            heldout_edge_pooled=ep, heldout_edge_equal=ee, reason=reason,
            margin=margin, margin_required=required, heldout_n=heldout_n,
            need_heldout_n=need_h)

    if heldout_n < min_heldout_n:
        return _held(f"held-out tail too thin to decide: {heldout_n:.0f}/{need_h:.0f} "
                     f"effective events")
    if test_members < min_members:
        return _held("vacuous: the held-out tail carries one contributing member, so pooled "
                     "and equal weighting are the SAME allocation — no test was run")
    if require_positive_edge and ep <= 0:
        return _held(f"held: pooled loses out-of-sample ({ep:+.5f}) — losing less than "
                     f"equal-weight ({ee:+.5f}) is not an edge")
    if margin < required:
        return _held(f"held: pooled clears equal-weight by {margin:+.6f}, under the "
                     f"pre-registered {required:.6f} bar")

    return ArmStatus(
        armed=True, n_eff=n_eff, need_n=float(min_family_n), pooled_beats_equal=beats,
        heldout_edge_pooled=ep, heldout_edge_equal=ee,
        reason=(f"armed: pooled earns {ep:+.5f} out-of-sample and clears equal-weight by "
                f"{margin:+.6f} (bar {required:.6f})"),
        margin=margin, margin_required=required, heldout_n=heldout_n, need_heldout_n=need_h)
