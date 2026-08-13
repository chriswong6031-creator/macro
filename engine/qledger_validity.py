"""engine/qledger_validity.py — metric-validity invariants for the Universal Scoreboard.

WHY THIS EXISTS
---------------
:mod:`engine.qledger` stores a claim corpus and a grade corpus. Both are honest.
The hazard is entirely in the READING: three ways to compute a number from those
two files that looks like a performance metric and is not one. Each was found
live in the tree on 2026-08-12 and each is silent — nothing raises, nothing goes
red, and the resulting figure renders perfectly.

  V1  SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS
      ``grades.jsonl.excess`` is RAW subject-minus-control return. It is NOT
      signed by the claim's direction. The stored ``hit`` field is what carries
      direction: hit == (sign(excess) == direction). Proof, from the 2026-08-12
      corpus cross-tab of (direction, hit, sign(excess)):
            (-1, True,  excess<=0)  4594      (1, True,  excess>0)  4046
            (-1, False, excess>0)   4140      (1, False, excess<=0) 4432
      A correct bearish call therefore CONTRIBUTES A NEGATIVE excess. Averaging
      signed excess over a family holding both directions measures the drift of
      the subject universe, not the skill of the calls. On the 2026-08-12 corpus
      that pooled figure is -0.0065 (t=-17.9) — an impressive-looking, and
      entirely meaningless, number. Legal readings for a mixed family: the hit
      rate, mean |excess| (a "did it move at all" duel, as the placebo lane
      already uses), or signed excess split per direction.

  V2  HIT_RATE_ON_A_SALIENCE_FAMILY
      A claim with ``direction == 0`` asserts importance, not direction, so
      ``hit`` is undefined for it and is stored null. 71% of the 2026-08-12
      corpus (32,123 of 45,203 claims) is direction==0. A hit rate computed over
      a salience family is a ratio over an empty verdict set; a headline claim
      count that does not separate the two overstates the directional evidence
      by ~3.5x.

  V3  OFF_HORIZON_VERDICT
      Grading emits every in-scope horizon as it matures, so a family declaring
      ``horizon_d=63`` accrues 5d and 21d rows LONG before its own ruler matures.
      Measured 2026-08-12: the ``radar`` family declares horizon_d=63 on all
      9,482 of its claims, the grade corpus holds ZERO rows at horizon 63, and
      all 13,651 of its verdicts sit at 5d/21d. Reading those as radar's record
      is precisely what ``DNR:KILL-OFFHORIZON-VERDICTS`` forbids ("verdicts only
      at registered horizon_role ruler"). They are ACCRUING, not a verdict.

WHAT THIS MODULE IS
-------------------
Pure functions over already-loaded lists of dicts. It reads no files, writes no
files, and imports nothing from :mod:`engine.qledger` — so it is cheap to test
with synthetic rows and cannot be broken by a store-layout change. The file shell
and the CI gate live in ``scripts/check_qledger_metric_validity.py``.

This module NEVER blocks accrual and NEVER de-rates a desk. Per house epistemics
(CLAUDE.md §Epistemics) a null is not a blocker: these findings constrain how a
number may be REPORTED, not whether a claim may be registered.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

# Severity vocabulary. Deliberately mirrors engine.neuralweb.contradictions:
# 'critical' is reserved for the Article-2 alert vocabulary and is forbidden here.
SEVERITY_NOTE = "note"
SEVERITY_INVALID = "invalid"
VALID_SEVERITIES = frozenset({SEVERITY_NOTE, SEVERITY_INVALID})

FINDING_CODES = (
    "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS",
    "HIT_RATE_ON_A_SALIENCE_FAMILY",
    "OFF_HORIZON_VERDICT",
)


@dataclass(frozen=True)
class Finding:
    """One metric-validity violation against one claim family."""

    code: str
    family: str
    severity: str
    detail: str

    def __post_init__(self) -> None:
        if self.code not in FINDING_CODES:
            raise ValueError(f"unknown finding code {self.code!r}")
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(f"unknown severity {self.severity!r}")


@dataclass
class FamilyProfile:
    """What a claim family is, derived from its own claims — never assumed."""

    family: str
    n_claims: int = 0
    directions: set[int] = field(default_factory=set)
    declared_horizons: set[int] = field(default_factory=set)

    @property
    def salience_only(self) -> bool:
        """True when every claim is direction==0, so ``hit`` is undefined."""
        return self.directions == {0}

    @property
    def directional(self) -> bool:
        return bool(self.directions - {0})

    @property
    def direction_homogeneous(self) -> bool:
        """True when signed excess may be pooled: at most one non-zero sign."""
        return len(self.directions - {0}) <= 1

    @property
    def ruler_horizon(self) -> int | None:
        """The family's own declared horizon — the only legal verdict horizon.

        A family declaring several horizons is ruled by its LONGEST: grading
        emits shorter in-scope horizons on the way there, and the claim is not
        resolved until its own declared horizon matures.
        """
        return max(self.declared_horizons) if self.declared_horizons else None


def _as_int(value: Any) -> int | None:
    """Coerce a stored direction/horizon to int. Stores hold both 1 and '1'."""
    if isinstance(value, bool):  # bool is an int subclass; never a direction
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


GROUP_FAMILY = "family"
GROUP_DESK = "desk"
GROUP_KEYS = (GROUP_FAMILY, GROUP_DESK)


def group_key(claim: dict, group_by: str = GROUP_FAMILY) -> str | None:
    """The grouping key for one claim. Mirrors ``engine.qledger._family_key``.

    ``family`` falls back to ``desk`` because the store's early rows predate the
    ``claim_family`` field; ``desk`` never falls back, so a claim with no desk is
    simply not desk-grouped.
    """
    if group_by == GROUP_DESK:
        return claim.get("desk")
    if group_by == GROUP_FAMILY:
        return claim.get("claim_family") or claim.get("desk")
    raise ValueError(f"unknown group_by {group_by!r}; expected one of {GROUP_KEYS}")


def profile_families(
    claims: Iterable[dict],
    *,
    include_placebo: bool = False,
    group_by: str = GROUP_FAMILY,
) -> dict[str, FamilyProfile]:
    """Derive a :class:`FamilyProfile` per group from the claim rows.

    ``group_by='family'`` (default) keys on ``claim_family`` (falling back to
    ``desk``); ``group_by='desk'`` keys on ``desk``. Both groupings are PUBLISHED
    — ``track_record.json`` carries ``by_family`` AND ``by_desk`` — and a desk
    holding two families of opposite direction is exactly as unpoolable as a
    mixed family, so the invariants must be answerable at either altitude.

    Placebo claims are excluded by default: the placebo tape is a control arm,
    and folding it into a family's direction profile would let a synthetic row
    decide whether a real family may pool its excess.
    """
    out: dict[str, FamilyProfile] = {}
    for claim in claims:
        if not include_placebo and claim.get("is_placebo"):
            continue
        family = group_key(claim, group_by)
        if family is None:
            continue
        prof = out.get(family)
        if prof is None:
            prof = out[family] = FamilyProfile(family=family)
        prof.n_claims += 1
        direction = _as_int(claim.get("direction"))
        if direction is not None:
            prof.directions.add(direction)
        horizon = _as_int(claim.get("horizon_d"))
        if horizon is not None:
            prof.declared_horizons.add(horizon)
    return out


def may_pool_signed_excess(profile: FamilyProfile) -> bool:
    """V1 gate. False when a signed ``excess_mean`` would be uninterpretable.

    A salience-only family is allowed: with no directional claims there is no
    sign convention to violate, and mean excess is a legitimate drift statistic.
    """
    return profile.direction_homogeneous


def may_report_hit_rate(profile: FamilyProfile) -> bool:
    """V2 gate. False for a salience-only family, where ``hit`` is undefined."""
    return profile.directional


def matured_horizons(grades: Iterable[dict], family_claim_ids: set[str]) -> set[int]:
    """The set of horizons actually present in the grade corpus for a family."""
    out: set[int] = set()
    for grade in grades:
        if grade.get("claim_id") in family_claim_ids:
            horizon = _as_int(grade.get("horizon_d"))
            if horizon is not None:
                out.add(horizon)
    return out


def audit(
    claims: Sequence[dict],
    grades: Sequence[dict],
    *,
    reported_metrics: dict[str, set[str]] | None = None,
    group_by: str = GROUP_FAMILY,
) -> list[Finding]:
    """Return every metric-validity finding for this corpus.

    ``reported_metrics`` maps group -> the metric names a caller intends to
    publish (e.g. ``{"radar": {"excess_mean", "hit_rate"}}``). Two modes, and the
    difference between them is the difference between an advisory and a gate:

    * ``reported_metrics=None`` (permissive / ADVISORY) — assume a reader may
      reach for any metric, which is what a dashboard or an LLM summarising the
      raw store would do. Correct as a standing advisory over the store; it
      reports a HAZARD, not a defect, so its findings are not attributable to a
      PR author and it must never be a merge gate.
    * ``reported_metrics={...}`` (GATE) — audit only what is actually published.
      A finding then means someone really publishes an illegal reading. The
      caller must derive the map from a PUBLISHED ARTIFACT, never by re-running
      the same legality predicates the emitter uses — a map derived from the code
      under audit cannot fail (memory: receipt-written-from-the-same-variable).

    A group with no entry in ``reported_metrics`` publishes nothing and is
    therefore silent; an explicit empty set means the same thing.
    """
    profiles = profile_families(claims, group_by=group_by)
    ids_by_family: dict[str, set[str]] = {}
    for claim in claims:
        if claim.get("is_placebo"):
            continue
        family = group_key(claim, group_by)
        cid = claim.get("claim_id")
        if family is not None and cid is not None:
            ids_by_family.setdefault(family, set()).add(cid)

    findings: list[Finding] = []
    for family, prof in sorted(profiles.items()):
        # `reported_metrics is None` is ADVISORY; an EMPTY dict is a GATE over a
        # publication surface that names nothing, which is not the same thing —
        # `(reported_metrics or {})` would have collapsed the two and quietly run
        # every gate caller in advisory mode the moment its map came back empty.
        wanted = None if reported_metrics is None else (reported_metrics.get(family) or set())

        if (wanted is None or "excess_mean" in wanted) and not may_pool_signed_excess(prof):
            signs = sorted(prof.directions - {0})
            findings.append(
                Finding(
                    code="SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS",
                    family=family,
                    severity=SEVERITY_INVALID,
                    detail=(
                        f"family holds directions {signs}; grades.excess is raw "
                        f"(not direction-signed), so a pooled signed excess_mean "
                        f"measures universe drift, not skill. Report hit_rate, "
                        f"mean |excess|, or split the mean per direction."
                    ),
                )
            )

        # wilson_ci_low is a CI *on the hit rate*, so publishing it is publishing
        # a hit rate by another name; it fails V2 for exactly the same reason.
        if (
            wanted is None or wanted & {"hit_rate", "wilson_ci_low"}
        ) and not may_report_hit_rate(prof):
            findings.append(
                Finding(
                    code="HIT_RATE_ON_A_SALIENCE_FAMILY",
                    family=family,
                    severity=SEVERITY_INVALID,
                    detail=(
                        f"all {prof.n_claims} claims carry direction==0 (salience, "
                        f"not direction), so hit is undefined and stored null; a "
                        f"hit rate here is a ratio over an empty verdict set."
                    ),
                )
            )

        # V3 asks "may this family's graded rows be read as a verdict". In GATE
        # mode a group that publishes nothing is not being read at all, so the
        # question does not arise; in ADVISORY mode (wanted is None) it always does.
        ruler = prof.ruler_horizon
        if ruler is not None and (wanted is None or wanted):
            matured = matured_horizons(grades, ids_by_family.get(family, set()))
            if matured and ruler not in matured:
                findings.append(
                    Finding(
                        code="OFF_HORIZON_VERDICT",
                        family=family,
                        severity=SEVERITY_NOTE,
                        detail=(
                            f"declares horizon_d={ruler} but the grade corpus holds "
                            f"only {sorted(matured)}; those rows are ACCRUING, not a "
                            f"verdict (DNR:KILL-OFFHORIZON-VERDICTS). Verdict n at "
                            f"the declared ruler is 0."
                        ),
                    )
                )
    return findings
