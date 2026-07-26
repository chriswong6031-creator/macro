"""engine.marketing.ad_stats — honest measurement for a split test.

Ad Central spine, module 3 of 5 (`research/AD_CENTRAL_MASTERPLAN.md` §3).

Beta-Binomial posterior per arm on a binary primary metric.  Reports posterior
mean, credible interval, P(best), and the difference vs control with an interval.

**Pure Python — deliberately no scipy/numpy.**  CI packs install minimal deps, and
an `importorskip` "fix" would disarm the gate rather than repair it.  The
regularized incomplete beta is a continued fraction (Lentz); quantiles are
bisected on it; P(best) and the difference distribution are computed by
deterministic quadrature.  No RNG anywhere (masterplan §0 G-G): Thompson
allocation downstream reads these probabilities *in expectation* rather than
sampling them, so a re-run reproduces byte-identically.

The laws this module enforces, not merely implements:

* **G-B, assignment-time denominators.** An arm carries `assigned` and
  `converted`.  There is no field for "units that survived to the outcome" —
  outcome-conditioned denominators delete losers and manufacture lift, so the
  shape refuses to represent one.
* **G-C, the null is the control.** Nothing is compared against 0.5 or against a
  bare prior.  Every verdict names the control and prints its posterior.
* **G-D, n-floor.** Below the floor the verdict is `seeding` and no arm is
  declared, promoted, killed, or scaled.
* **G-E, frozen primary metric.** `decide()` refuses a metric that is not the
  arena's pre-registered primary.

The prior is stated in every verdict.  Default Beta(1,1) is uniform — at the
sample sizes a small-budget test reaches it is a *conservative* choice (wide
intervals, slow to declare), which is the safe direction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_PRIOR_ALPHA: float = 1.0
DEFAULT_PRIOR_BETA: float = 1.0
DEFAULT_N_FLOOR: int = 100
DEFAULT_CREDIBLE_LEVEL: float = 0.90
# P(best) at or above this, with a difference interval excluding zero, separates.
DEFAULT_DECISIVE: float = 0.95
# A difference interval entirely inside ±this is a real finding: "the same".
DEFAULT_PRACTICAL_PP: float = 0.5

_GRID_N: int = 513          # odd → Simpson's rule pairs up exactly
_DIFF_GRID_N: int = 513     # convolution is O(n²); 513 keeps a pair under ~0.1s
_BISECT_ITERS: int = 80

VERDICTS: tuple[str, ...] = ("seeding", "separated", "equivalent", "null")


class FrozenMetricViolation(ValueError):
    """Raised when a stop decision is attempted on a non-primary metric (G-E)."""


# ─────────────────────────────────────────────────────────────────────────────
# Regularized incomplete beta — I_x(a, b)
# ─────────────────────────────────────────────────────────────────────────────

def _log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (modified Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def beta_cdf(x: float, a: float, b: float) -> float:
    """P(X ≤ x) for X ~ Beta(a, b).  Clamped to [0, 1]."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    if a <= 0.0 or b <= 0.0:
        return 0.0
    lbt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
           + a * math.log(x) + b * math.log1p(-x))
    bt = math.exp(lbt)
    if x < (a + 1.0) / (a + b + 2.0):
        val = bt * _betacf(a, b, x) / a
    else:
        val = 1.0 - bt * _betacf(b, a, 1.0 - x) / b
    return min(1.0, max(0.0, val))


def beta_ppf(q: float, a: float, b: float) -> float:
    """Inverse CDF by bisection.  Monotone and deterministic."""
    if q <= 0.0:
        return 0.0
    if q >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(_BISECT_ITERS):
        mid = 0.5 * (lo + hi)
        if beta_cdf(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _beta_log_pdf(x: float, a: float, b: float) -> float:
    if x <= 0.0 or x >= 1.0:
        return -math.inf
    return (a - 1.0) * math.log(x) + (b - 1.0) * math.log1p(-x) - _log_beta(a, b)


# ─────────────────────────────────────────────────────────────────────────────
# Arm
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Arm:
    """One creative under test.

    `assigned` is the intention-to-treat denominator — every unit the arena
    handed to this arm, whether or not it stuck around.  There is deliberately no
    "eligible" or "engaged" denominator field (G-B).
    """
    arm_id: str
    creative_id: str = ""
    assigned: int = 0
    converted: int = 0
    spend_usd: float = 0.0
    is_control: bool = False
    status: str = "live"        # live | retired | promoted
    # Human name for the plain-word sentences. Falls back to the id, but a
    # console line reading "adc-d50a1a888439 is ahead by 3pp" tells the reader
    # nothing — pass the creative's headline here.
    label: str = ""

    @property
    def name(self) -> str:
        return self.label or self.arm_id

    def posterior(self, prior_alpha: float, prior_beta: float) -> tuple[float, float]:
        conv = max(0, int(self.converted))
        assigned = max(0, int(self.assigned))
        conv = min(conv, assigned)          # conversions cannot exceed assignments
        return prior_alpha + conv, prior_beta + (assigned - conv)

    def as_dict(self) -> dict:
        return {
            "arm_id": self.arm_id,
            "creative_id": self.creative_id,
            "label": self.label,
            "assigned": self.assigned,
            "converted": self.converted,
            "spend_usd": round(float(self.spend_usd), 4),
            "is_control": self.is_control,
            "status": self.status,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Quadrature helpers
# ─────────────────────────────────────────────────────────────────────────────

def _support(posteriors: list[tuple[float, float]], widen: float = 10.0) -> tuple[float, float]:
    """Grid bounds covering every posterior's bulk, clipped to [0, 1]."""
    lo, hi = 1.0, 0.0
    for a, b in posteriors:
        n = a + b
        mean = a / n if n > 0 else 0.5
        sd = math.sqrt(max(mean * (1.0 - mean) / (n + 1.0), 1e-12))
        lo = min(lo, mean - widen * sd)
        hi = max(hi, mean + widen * sd)
    lo = max(0.0, lo)
    hi = min(1.0, hi)
    if hi - lo < 1e-9:
        lo, hi = max(0.0, lo - 1e-3), min(1.0, hi + 1e-3)
    return lo, hi


def prob_best(posteriors: list[tuple[float, float]]) -> list[float]:
    """P(arm k has the highest rate), by quadrature.

    ``P_k = ∫ f_k(x) ∏_{j≠k} F_j(x) dx`` on a shared grid.  Normalized at the end
    so the vector sums to 1 — quadrature error shows up as a renormalization, not
    as a probability that silently fails to be one.
    """
    k = len(posteriors)
    if k == 0:
        return []
    if k == 1:
        return [1.0]

    lo, hi = _support(posteriors)
    n = _GRID_N
    h = (hi - lo) / (n - 1)
    xs = [lo + i * h for i in range(n)]

    # Precompute each arm's pdf and cdf on the grid — O(k·n) betacf evaluations.
    pdfs: list[list[float]] = []
    cdfs: list[list[float]] = []
    for a, b in posteriors:
        pdfs.append([math.exp(_beta_log_pdf(x, a, b)) if 0.0 < x < 1.0 else 0.0 for x in xs])
        cdfs.append([beta_cdf(x, a, b) for x in xs])

    out: list[float] = []
    for idx in range(k):
        vals = []
        for i in range(n):
            prod = pdfs[idx][i]
            if prod > 0.0:
                for j in range(k):
                    if j != idx:
                        prod *= cdfs[j][i]
            vals.append(prod)
        out.append(_simpson(vals, h))

    total = sum(out)
    if total <= 0.0:
        return [1.0 / k] * k
    return [v / total for v in out]


def _simpson(vals: list[float], h: float) -> float:
    """Composite Simpson's rule; falls back to the trapezoid on an even count."""
    n = len(vals)
    if n < 2:
        return 0.0
    if n % 2 == 0:
        return h * (sum(vals) - 0.5 * (vals[0] + vals[-1]))
    total = vals[0] + vals[-1]
    for i in range(1, n - 1):
        total += vals[i] * (4.0 if i % 2 == 1 else 2.0)
    return total * h / 3.0


def prob_greater(a1: float, b1: float, a2: float, b2: float) -> float:
    """P(X₁ > X₂) for independent Betas, by quadrature."""
    lo, hi = _support([(a1, b1), (a2, b2)])
    n = _GRID_N
    h = (hi - lo) / (n - 1)
    vals = []
    for i in range(n):
        x = lo + i * h
        if 0.0 < x < 1.0:
            vals.append(math.exp(_beta_log_pdf(x, a1, b1)) * beta_cdf(x, a2, b2))
        else:
            vals.append(0.0)
    return min(1.0, max(0.0, _simpson(vals, h)))


def difference_interval(
    a1: float, b1: float, a2: float, b2: float,
    level: float = DEFAULT_CREDIBLE_LEVEL,
) -> tuple[float, float]:
    """Credible interval for (X₁ − X₂), independent Betas, by discrete convolution.

    Both posteriors are discretized onto one shared grid so the difference lands
    on integer index offsets; the convolution is then exact on that lattice.
    Returns bounds on the *absolute* difference (a rate difference, not a ratio).
    """
    lo, hi = _support([(a1, b1), (a2, b2)], widen=12.0)
    n = _DIFF_GRID_N
    h = (hi - lo) / (n - 1)
    xs = [lo + i * h for i in range(n)]

    def _weights(a: float, b: float) -> list[float]:
        raw = [math.exp(_beta_log_pdf(x, a, b)) if 0.0 < x < 1.0 else 0.0 for x in xs]
        s = sum(raw)
        return [v / s for v in raw] if s > 0 else [1.0 / n] * n

    w1 = _weights(a1, b1)
    w2 = _weights(a2, b2)

    # buckets[d + (n-1)] = P(index difference == d)
    buckets = [0.0] * (2 * n - 1)
    for i, p1 in enumerate(w1):
        if p1 <= 0.0:
            continue
        base = i + n - 1
        for j, p2 in enumerate(w2):
            if p2 > 0.0:
                buckets[base - j] += p1 * p2

    tail = (1.0 - level) / 2.0
    cum = 0.0
    lo_d: float | None = None
    hi_d: float | None = None
    for idx, p in enumerate(buckets):
        cum += p
        if lo_d is None and cum >= tail:
            lo_d = (idx - (n - 1)) * h
        if cum >= 1.0 - tail:
            hi_d = (idx - (n - 1)) * h
            break
    if lo_d is None:
        lo_d = -(n - 1) * h
    if hi_d is None:
        hi_d = (n - 1) * h
    return lo_d, hi_d


# ─────────────────────────────────────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ArmReadout:
    arm_id: str
    creative_id: str
    label: str
    assigned: int
    converted: int
    rate: float                 # posterior mean — NOT converted/assigned
    observed_rate: float        # the raw ratio, printed alongside for audit
    ci_low: float
    ci_high: float
    prob_best: float
    is_control: bool
    status: str
    # vs control (None on the control arm itself)
    diff_pp: float | None = None
    diff_pp_low: float | None = None
    diff_pp_high: float | None = None
    prob_beats_control: float | None = None
    rel_lift_pct: float | None = None

    def as_dict(self) -> dict:
        return {
            "arm_id": self.arm_id,
            "creative_id": self.creative_id,
            "label": self.label,
            "assigned": self.assigned,
            "converted": self.converted,
            "rate": round(self.rate, 6),
            "observed_rate": round(self.observed_rate, 6),
            "ci_low": round(self.ci_low, 6),
            "ci_high": round(self.ci_high, 6),
            "prob_best": round(self.prob_best, 6),
            "is_control": self.is_control,
            "status": self.status,
            "diff_pp": None if self.diff_pp is None else round(self.diff_pp, 4),
            "diff_pp_low": None if self.diff_pp_low is None else round(self.diff_pp_low, 4),
            "diff_pp_high": None if self.diff_pp_high is None else round(self.diff_pp_high, 4),
            "prob_beats_control": (None if self.prob_beats_control is None
                                   else round(self.prob_beats_control, 6)),
            "rel_lift_pct": None if self.rel_lift_pct is None else round(self.rel_lift_pct, 3),
        }


@dataclass
class Readout:
    verdict: str                # seeding | separated | equivalent | null
    primary_metric: str
    control_arm_id: str | None
    winner_arm_id: str | None
    arms: list[ArmReadout] = field(default_factory=list)
    n_floor: int = DEFAULT_N_FLOOR
    credible_level: float = DEFAULT_CREDIBLE_LEVEL
    prior: dict = field(default_factory=dict)
    plain: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "primary_metric": self.primary_metric,
            "control_arm_id": self.control_arm_id,
            "winner_arm_id": self.winner_arm_id,
            "arms": [a.as_dict() for a in self.arms],
            "n_floor": self.n_floor,
            "credible_level": self.credible_level,
            "prior": dict(self.prior),
            "plain": self.plain,
            "notes": list(self.notes),
        }


def analyze(
    arms: list[Arm],
    *,
    primary_metric: str,
    n_floor: int = DEFAULT_N_FLOOR,
    prior_alpha: float = DEFAULT_PRIOR_ALPHA,
    prior_beta: float = DEFAULT_PRIOR_BETA,
    credible_level: float = DEFAULT_CREDIBLE_LEVEL,
    decisive: float = DEFAULT_DECISIVE,
    practical_pp: float = DEFAULT_PRACTICAL_PP,
) -> Readout:
    """Score every arm and return a verdict that may well be "nothing separated".

    Verdicts
    --------
    ``seeding``     any live arm below the n-floor — no arm declared (G-D)
    ``separated``   a leader with P(best) ≥ `decisive` AND a difference interval
                    vs control excluding 0
    ``equivalent``  every arm's difference interval sits inside ±`practical_pp` —
                    a real finding: these creatives are the same, stop testing
    ``null``        enough data, no separation.  Printed, not hidden (G-C).
    """
    live = [a for a in arms if a.status == "live"]
    if not live:
        return Readout(
            verdict="null", primary_metric=primary_metric, control_arm_id=None,
            winner_arm_id=None, arms=[], n_floor=n_floor,
            credible_level=credible_level,
            prior={"alpha": prior_alpha, "beta": prior_beta},
            plain="No ads are live in this test.", notes=["no_live_arms"],
        )

    control = next((a for a in live if a.is_control), live[0])
    posteriors = [a.posterior(prior_alpha, prior_beta) for a in live]
    pbest = prob_best(posteriors)
    ca, cb = control.posterior(prior_alpha, prior_beta)

    tail = (1.0 - credible_level) / 2.0
    readouts: list[ArmReadout] = []
    for arm, (a, b), pb in zip(live, posteriors, pbest):
        mean = a / (a + b)
        observed = (arm.converted / arm.assigned) if arm.assigned > 0 else 0.0
        r = ArmReadout(
            arm_id=arm.arm_id, creative_id=arm.creative_id, label=arm.label,
            assigned=arm.assigned, converted=arm.converted,
            rate=mean, observed_rate=observed,
            ci_low=beta_ppf(tail, a, b), ci_high=beta_ppf(1.0 - tail, a, b),
            prob_best=pb, is_control=arm.is_control, status=arm.status,
        )
        if arm.arm_id != control.arm_id:
            d_lo, d_hi = difference_interval(a, b, ca, cb, level=credible_level)
            control_mean = ca / (ca + cb)
            r.diff_pp = (mean - control_mean) * 100.0
            r.diff_pp_low = d_lo * 100.0
            r.diff_pp_high = d_hi * 100.0
            r.prob_beats_control = prob_greater(a, b, ca, cb)
            # Point estimate from posterior means.  Deliberately NOT given an
            # interval: a ratio of two posteriors is not what the convolution
            # above computed, and inventing one would be the dishonest step.
            r.rel_lift_pct = ((mean - control_mean) / control_mean * 100.0
                              if control_mean > 0 else None)
        readouts.append(r)

    notes: list[str] = []

    # ── G-D: n-floor ─────────────────────────────────────────────────────────
    under = [a.arm_id for a in live if a.assigned < n_floor]
    if under:
        smallest = min(a.assigned for a in live)
        return Readout(
            verdict="seeding", primary_metric=primary_metric,
            control_arm_id=control.arm_id, winner_arm_id=None,
            arms=readouts, n_floor=n_floor, credible_level=credible_level,
            prior={"alpha": prior_alpha, "beta": prior_beta},
            plain=(f"Still gathering data — {len(under)} of {len(live)} ads have been "
                   f"seen by fewer than {n_floor} people (lowest so far: {smallest}). "
                   f"No ad is ahead yet, and none will be called until every one of "
                   f"them clears that mark."),
            notes=[f"under_floor:{aid}" for aid in under],
        )

    # ── leader ───────────────────────────────────────────────────────────────
    leader = max(readouts, key=lambda r: r.rate)
    non_control = [r for r in readouts if not r.is_control]

    def _name(r: ArmReadout) -> str:
        """Plain name for a sentence — never a bare `adc-…` id when copy exists."""
        return f"“{r.label}”" if r.label else r.arm_id

    # ── equivalence: every contrast inside the practical band ────────────────
    # Checked BEFORE separation on purpose. A difference can be real (interval
    # excludes zero) and still too small to be worth acting on; when both hold,
    # "too small to chase" is the more useful verdict than "winner". The wording
    # below claims only what is measured — inside the band — never that the
    # difference is exactly zero.
    if non_control and all(
        r.diff_pp_low is not None and r.diff_pp_high is not None
        and r.diff_pp_low > -practical_pp and r.diff_pp_high < practical_pp
        for r in non_control
    ):
        return Readout(
            verdict="equivalent", primary_metric=primary_metric,
            control_arm_id=control.arm_id, winner_arm_id=None,
            arms=readouts, n_floor=n_floor, credible_level=credible_level,
            prior={"alpha": prior_alpha, "beta": prior_beta},
            plain=(f"Nothing here is worth chasing. Every ad lands within "
                   f"±{practical_pp} points of the copy we already run, at "
                   f"{int(credible_level * 100)}% confidence — too small to matter even "
                   f"where it is real. That is a result, not a shortfall: stop testing "
                   f"this wording and change something bigger."),
            notes=["equivalent_within_practical_band"],
        )

    # ── separation ───────────────────────────────────────────────────────────
    separated = (
        not leader.is_control
        and leader.prob_best >= decisive
        and leader.diff_pp_low is not None
        and leader.diff_pp_low > 0.0
    )
    if separated:
        return Readout(
            verdict="separated", primary_metric=primary_metric,
            control_arm_id=control.arm_id, winner_arm_id=leader.arm_id,
            arms=readouts, n_floor=n_floor, credible_level=credible_level,
            prior={"alpha": prior_alpha, "beta": prior_beta},
            plain=(f"{_name(leader)} beats the current copy by "
                   f"{leader.diff_pp:.2f} points "
                   f"({leader.diff_pp_low:.2f} to {leader.diff_pp_high:.2f}, "
                   f"{int(credible_level * 100)}% confident), and is the best of the "
                   f"{len(readouts)} with probability {leader.prob_best:.2f}."),
            notes=notes,
        )

    # ── G-C: the null, printed ───────────────────────────────────────────────
    if leader.is_control:
        headline = "The copy we already run is still the best of them."
    else:
        headline = (f"{_name(leader)} is nominally ahead but not far enough to call "
                    f"— it is best with probability {leader.prob_best:.2f}, and we "
                    f"need {decisive:.2f}.")
    return Readout(
        verdict="null", primary_metric=primary_metric,
        control_arm_id=control.arm_id, winner_arm_id=None,
        arms=readouts, n_floor=n_floor, credible_level=credible_level,
        prior={"alpha": prior_alpha, "beta": prior_beta},
        plain=(f"No ad pulled ahead. {headline} Every ad has been seen by at least "
               f"{n_floor} people, so this is a real null — not missing data."),
        notes=notes + ["no_separation"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Decision (G-E)
# ─────────────────────────────────────────────────────────────────────────────

def decide(readout: Readout, *, frozen_primary_metric: str) -> dict[str, Any]:
    """Turn a readout into a stop/continue decision.

    Raises `FrozenMetricViolation` when the readout was computed on anything other
    than the arena's pre-registered primary metric (G-E).  Secondary metrics are
    exploratory: they may be *looked at* and may never stop, kill, or fund an arm.
    """
    if readout.primary_metric != frozen_primary_metric:
        raise FrozenMetricViolation(
            f"stop decision attempted on {readout.primary_metric!r}; this arena's "
            f"pre-registered primary metric is {frozen_primary_metric!r}. Secondary "
            f"metrics are exploratory and can never trigger a stop."
        )
    stop = readout.verdict in ("separated", "equivalent")
    return {
        "stop": stop,
        "verdict": readout.verdict,
        "winner_arm_id": readout.winner_arm_id,
        "reason": readout.plain,
        "metric": readout.primary_metric,
    }
