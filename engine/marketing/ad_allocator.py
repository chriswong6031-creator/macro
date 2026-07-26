"""engine.marketing.ad_allocator — many arms, small budgets, no RNG.

Ad Central spine, module 5 of 5 (`research/AD_CENTRAL_MASTERPLAN.md` §3).

Allocates a daily envelope across live arms by **deterministic probability
matching**: each arm receives the posterior probability that it is the best arm,
computed by quadrature in `ad_stats.prob_best`.

That is Thompson sampling *in expectation*.  Sampled Thompson draws one value per
arm per round and funds the argmax; over many rounds each arm's spend share
converges to exactly P(best).  Computing P(best) directly and funding that share
reaches the same allocation without a seed, which is what lets a nightly re-run
reproduce yesterday's plan byte-for-byte (masterplan §0 G-G) — and lets an
operator audit a spend decision instead of re-rolling it.

Layered on top, in this order:

1. **Kill** — an arm at n ≥ floor whose credible upper bound sits below the
   control's posterior mean is retired.  The control is never retired.
2. **Exploration floor** — every arm still under the n-floor holds a minimum
   share, so probability matching cannot starve an arm before it has enough data
   to defend itself.  Winner-take-all on n=30 is how a bandit locks onto noise.
3. **Platform minimum** — an arm funded below the platform's minimum daily budget
   is paused for the day rather than funded at a level that buys nothing.
4. **Per-arm cap** — nothing exceeds it; excess redistributes to arms with
   headroom; a residue that fits nowhere goes **unspent**, because money forced
   past a cap is a cap that does not exist.

**Nothing here spends anything.**  Actuation requires the G-A triple gate —
`paid_enabled`, a non-zero envelope, and an operator arm — and every plan carries
`dry_run: True` until all three are on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import ad_stats

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MIN_DAILY_USD: float = 5.0      # typical platform floor for a daily budget
DEFAULT_PER_ARM_CAP_USD: float = 20.0
DEFAULT_EXPLORATION_FLOOR_SHARE: float = 0.10


@dataclass
class AllocatorConfig:
    daily_envelope_usd: float = 0.0
    per_arm_daily_cap_usd: float = DEFAULT_PER_ARM_CAP_USD
    min_daily_usd: float = DEFAULT_MIN_DAILY_USD
    exploration_floor_share: float = DEFAULT_EXPLORATION_FLOOR_SHARE
    n_floor: int = ad_stats.DEFAULT_N_FLOOR
    prior_alpha: float = ad_stats.DEFAULT_PRIOR_ALPHA
    prior_beta: float = ad_stats.DEFAULT_PRIOR_BETA
    credible_level: float = ad_stats.DEFAULT_CREDIBLE_LEVEL
    # G-A triple gate — all three must be true before a plan is anything but a rehearsal.
    paid_enabled: bool = False
    operator_armed: bool = False

    def as_dict(self) -> dict:
        return {
            "daily_envelope_usd": self.daily_envelope_usd,
            "per_arm_daily_cap_usd": self.per_arm_daily_cap_usd,
            "min_daily_usd": self.min_daily_usd,
            "exploration_floor_share": self.exploration_floor_share,
            "n_floor": self.n_floor,
            "prior_alpha": self.prior_alpha,
            "prior_beta": self.prior_beta,
            "credible_level": self.credible_level,
            "paid_enabled": self.paid_enabled,
            "operator_armed": self.operator_armed,
        }


def spend_permitted(cfg: AllocatorConfig) -> tuple[bool, list[str]]:
    """The G-A triple gate.  Returns (permitted, reasons_blocked).

    All three arms independent, all three required.  Any one off ⇒ dry run.
    """
    blocked: list[str] = []
    if not cfg.paid_enabled:
        blocked.append("paid_enabled_false")
    if float(cfg.daily_envelope_usd) <= 0.0:
        blocked.append("envelope_zero")
    if not cfg.operator_armed:
        blocked.append("operator_not_armed")
    return (not blocked), blocked


# ─────────────────────────────────────────────────────────────────────────────
# Plan
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Allocation:
    arm_id: str
    creative_id: str
    amount_usd: float
    share: float
    prob_best: float
    assigned: int
    status: str                 # funded | paused_below_minimum | retired | capped
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "arm_id": self.arm_id,
            "creative_id": self.creative_id,
            "amount_usd": round(self.amount_usd, 2),
            "share": round(self.share, 6),
            "prob_best": round(self.prob_best, 6),
            "assigned": self.assigned,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class Plan:
    allocations: list[Allocation] = field(default_factory=list)
    envelope_usd: float = 0.0
    allocated_usd: float = 0.0
    unallocated_usd: float = 0.0
    dry_run: bool = True
    blocked_by: list[str] = field(default_factory=list)
    retired: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "allocations": [a.as_dict() for a in self.allocations],
            "envelope_usd": round(self.envelope_usd, 2),
            "allocated_usd": round(self.allocated_usd, 2),
            "unallocated_usd": round(self.unallocated_usd, 2),
            "dry_run": self.dry_run,
            "blocked_by": list(self.blocked_by),
            "retired": list(self.retired),
            "notes": list(self.notes),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Kill rule
# ─────────────────────────────────────────────────────────────────────────────

def kill_candidates(arms: list[ad_stats.Arm], cfg: AllocatorConfig) -> dict[str, str]:
    """Arms whose credible upper bound is below the control's posterior mean.

    Requires n ≥ floor: an arm cannot be killed for a bad start.  The control is
    never a candidate — killing the baseline leaves nothing to measure against.
    """
    live = [a for a in arms if a.status == "live"]
    if len(live) < 2:
        return {}
    control = next((a for a in live if a.is_control), live[0])
    ca, cb = control.posterior(cfg.prior_alpha, cfg.prior_beta)
    control_mean = ca / (ca + cb)
    tail = (1.0 - cfg.credible_level) / 2.0

    out: dict[str, str] = {}
    for arm in live:
        if arm.arm_id == control.arm_id or arm.assigned < cfg.n_floor:
            continue
        a, b = arm.posterior(cfg.prior_alpha, cfg.prior_beta)
        upper = ad_stats.beta_ppf(1.0 - tail, a, b)
        if upper < control_mean:
            out[arm.arm_id] = (
                f"upper bound {upper:.4f} below control mean {control_mean:.4f} "
                f"at n={arm.assigned}"
            )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Allocate
# ─────────────────────────────────────────────────────────────────────────────

def allocate(arms: list[ad_stats.Arm], cfg: AllocatorConfig) -> Plan:
    """Build today's spend plan.  Never raises.

    Budget conservation is an invariant (masterplan §0 G-H):
        Σ amount ≤ envelope,  every amount ≤ per-arm cap,
        every funded amount ≥ platform minimum.
    """
    permitted, blocked = spend_permitted(cfg)
    envelope = max(0.0, float(cfg.daily_envelope_usd))
    plan = Plan(envelope_usd=envelope, dry_run=not permitted, blocked_by=blocked)

    live = [a for a in arms if a.status == "live"]
    if not live:
        plan.notes.append("No ads are live in this arena.")
        plan.unallocated_usd = envelope
        return plan

    # Zero envelope is the DEFAULT state, not an error — the whole paid plane ships
    # armed off. Report the standings the allocator would act on rather than a page
    # of "below the platform minimum" noise about money that does not exist.
    if envelope <= 0.0:
        posteriors = [a.posterior(cfg.prior_alpha, cfg.prior_beta) for a in live]
        pbest = ad_stats.prob_best(posteriors)
        plan.allocations = sorted(
            (
                Allocation(
                    arm_id=a.arm_id, creative_id=a.creative_id, amount_usd=0.0,
                    share=0.0, prob_best=p, assigned=a.assigned,
                    status="unfunded", reason="no daily budget is set",
                )
                for a, p in zip(live, pbest)
            ),
            key=lambda a: (-a.prob_best, a.arm_id),
        )
        plan.notes.append(
            "No daily budget is set, so nothing is allocated. The standings below are "
            "what the budget would follow if one were."
        )
        return plan

    # 1 ── kill ──────────────────────────────────────────────────────────────
    killed = kill_candidates(live, cfg)
    plan.retired = sorted(killed)
    running = [a for a in live if a.arm_id not in killed]
    if not running:
        plan.notes.append("all_arms_retired")
        plan.unallocated_usd = envelope
        return plan

    posteriors = [a.posterior(cfg.prior_alpha, cfg.prior_beta) for a in running]
    pbest = ad_stats.prob_best(posteriors)
    pbest_by_id = {a.arm_id: p for a, p in zip(running, pbest)}

    # 2 ── exploration floor for arms still under the n-floor ────────────────
    needs_floor = [a for a in running if a.assigned < cfg.n_floor]
    floor_share = max(0.0, float(cfg.exploration_floor_share))
    reserved = min(0.95, floor_share * len(needs_floor))
    per_floor = (reserved / len(needs_floor)) if needs_floor else 0.0
    if needs_floor and per_floor < floor_share:
        plan.notes.append(
            f"{len(needs_floor)} ads are still gathering data and share "
            f"{reserved * 100:.0f}% of the budget between them — less each than the "
            f"{floor_share * 100:.0f}% a single new ad normally holds."
        )

    raw_total = sum(pbest) or 1.0
    shares: dict[str, float] = {}
    for arm, p in zip(running, pbest):
        base = (1.0 - reserved) * (p / raw_total)
        shares[arm.arm_id] = base + (per_floor if arm.assigned < cfg.n_floor else 0.0)

    # 3 ── capacity diagnostic: can this envelope even run this many arms? ───
    min_daily = max(0.0, float(cfg.min_daily_usd))
    if min_daily > 0 and envelope > 0:
        testable = int(envelope // min_daily)
        if testable < len(running):
            plan.notes.append(
                f"${envelope:.2f} a day can fund at most {testable} ads at the "
                f"${min_daily:.2f} platform minimum, and {len(running)} are running. "
                f"The rest sit out today."
            )

    # 4 ── dollars, then cap + platform minimum, iterating on the residue ────
    cap = max(0.0, float(cfg.per_arm_daily_cap_usd))
    amounts: dict[str, float] = {}
    statuses: dict[str, str] = {}
    reasons: dict[str, str] = {}
    eligible = {a.arm_id for a in running}
    pool = envelope

    for _ in range(len(running) + 2):
        if not eligible or pool <= 1e-9:
            break
        share_total = sum(shares[aid] for aid in eligible) or 1.0
        settled: set[str] = set()
        for aid in sorted(eligible):
            want = pool * (shares[aid] / share_total)
            if cap > 0 and want >= cap:
                amounts[aid] = cap
                statuses[aid] = "capped"
                reasons[aid] = f"per-arm daily cap ${cap:.2f}"
                settled.add(aid)
        if settled:
            pool -= sum(amounts[aid] for aid in settled)
            eligible -= settled
            continue

        # Nothing capped this pass — check the platform minimum on the smallest arm.
        provisional = {
            aid: pool * (shares[aid] / share_total) for aid in eligible
        }
        starved = [aid for aid, v in provisional.items() if v < min_daily]
        if starved and len(eligible) > 1:
            # Drop the single worst-funded arm and re-spread; dropping them all at
            # once can starve a set that would have been fundable once one left.
            victim = min(starved, key=lambda aid: (provisional[aid], aid))
            amounts[victim] = 0.0
            statuses[victim] = "paused_below_minimum"
            reasons[victim] = (
                f"${provisional[victim]:.2f} is below the ${min_daily:.2f} platform "
                f"minimum — funded at that level it buys nothing"
            )
            eligible.discard(victim)
            continue

        for aid, value in provisional.items():
            if value < min_daily:
                amounts[aid] = 0.0
                statuses[aid] = "paused_below_minimum"
                reasons[aid] = (
                    f"${value:.2f} is below the ${min_daily:.2f} platform minimum"
                )
            else:
                amounts[aid] = value
                statuses.setdefault(aid, "funded")
        pool = 0.0
        eligible.clear()
        break

    for aid in eligible:                      # exhausted the loop with headroom left
        amounts.setdefault(aid, 0.0)
        statuses.setdefault(aid, "paused_below_minimum")
        reasons.setdefault(aid, "no allocation converged")

    # 5 ── round to cents; conservation must survive rounding ────────────────
    for aid in list(amounts):
        amounts[aid] = round(amounts[aid], 2)
    total = round(sum(amounts.values()), 2)
    if total > envelope:
        # Rounding can only push over by cents; shave the largest funded arm.
        overflow = round(total - envelope, 2)
        funded = sorted((aid for aid, v in amounts.items() if v > 0),
                        key=lambda aid: (-amounts[aid], aid))
        if funded:
            amounts[funded[0]] = round(amounts[funded[0]] - overflow, 2)
        total = round(sum(amounts.values()), 2)

    by_id = {a.arm_id: a for a in running}
    allocations = [
        Allocation(
            arm_id=aid,
            creative_id=by_id[aid].creative_id,
            amount_usd=amounts.get(aid, 0.0),
            share=(amounts.get(aid, 0.0) / envelope) if envelope > 0 else 0.0,
            prob_best=pbest_by_id.get(aid, 0.0),
            assigned=by_id[aid].assigned,
            status=statuses.get(aid, "funded"),
            reason=reasons.get(aid, ""),
        )
        for aid in sorted(by_id)
    ]
    allocations += [
        Allocation(
            arm_id=arm.arm_id, creative_id=arm.creative_id, amount_usd=0.0,
            share=0.0, prob_best=0.0, assigned=arm.assigned,
            status="retired", reason=killed[arm.arm_id],
        )
        for arm in live if arm.arm_id in killed
    ]

    plan.allocations = sorted(allocations, key=lambda a: (-a.amount_usd, a.arm_id))
    plan.allocated_usd = total
    plan.unallocated_usd = round(envelope - total, 2)
    if plan.dry_run:
        plan.notes.append("dry_run: no spend is authorised — " + ", ".join(blocked))
    return plan


def plan_summary(plan: Plan) -> str:
    """One plain sentence for the console — no jargon, no raw slugs."""
    funded = [a for a in plan.allocations if a.amount_usd > 0]
    if plan.dry_run:
        lead = "Rehearsal only — nothing will be spent"
        if plan.blocked_by:
            human = {
                "paid_enabled_false": "paid ads are switched off",
                "envelope_zero": "the daily budget is zero",
                "operator_not_armed": "no one has armed it",
            }
            lead += " (" + "; ".join(human.get(b, b) for b in plan.blocked_by) + ")"
        lead += ". "
    else:
        lead = ""
    if not funded:
        return lead + "No ad is funded today."
    return (
        f"{lead}{len(funded)} of {len(plan.allocations)} ads funded, "
        f"${plan.allocated_usd:.2f} of ${plan.envelope_usd:.2f}"
        + (f", ${plan.unallocated_usd:.2f} held back" if plan.unallocated_usd > 0.005 else "")
        + "."
    )
