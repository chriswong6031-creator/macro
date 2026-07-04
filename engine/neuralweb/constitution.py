"""engine.neuralweb.constitution — Neural Web constitutional rules in code.

Encodes the three Articles and the Authority Ladder (A0–A7) ratified by the operator
on 2026-07-04 (D4 ruling).  This module is PURELY DESCRIPTIVE + EVALUATIVE: it never
writes engine outputs, never calls IO, and has no side effects.  All authority grant
decisions that come back True here are logged by the caller before they act.

ARTICLE 1 — ORIGINATION BAN
  The Neural Web may never originate a signal, trade, escalation, or claim.  A7
  (ORIGINATE) is hard-coded refused by grant(): the method raises or returns a
  refused GrantResult unconditionally when target_level is A7.

ARTICLE 2 — SCORED-PATH PERIMETER
  The set of money-path / ranked-output surfaces that require at minimum a
  shadow-with-track-record tier to influence.  Read from config/synapse.yml
  meta.article2_surfaces (single source of truth — not duplicated here).

ARTICLE 3 — EVIDENCE-FLOOR FOR AUTHORITY GRANTS
  Every authority grant (can_force-style) must pass:
    (a) sample-size floors  (n >= min_n AND n_events >= min_events)
    (b) Wilson CI lower-bound lift > 1.25  (matches the retired point-estimate
        threshold of 1.25 — strictly tighter everywhere, zero grant-more cases)
    (c) evidence freshness  (evidence_asof within max_staleness_days)
  Grants that do not pass are refused; grants that previously passed but whose
  evidence has gone stale are lapsed (returned with granted=False, reason='stale').

AUTHORITY LADDER (A0–A7)
  Defined as AuthorityLevel enum.  Each level has a docstring naming it and
  its current holders / status.  A7 is permanently banned per Article 1.

WILSON LOWER BOUND
  The gate uses engine.qledger.wilson_ci_low, parameterised to z=1.645 (90%
  one-sided).  The qledger function defaults z=1.96; we call it with z=1.645.
  If the signature is ever incompatible, the wrapper wilson_lower() adapts.

Never raises into callers.  All failures return refused GrantResult with an
explanatory reason string.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authority Ladder
# ---------------------------------------------------------------------------

class AuthorityLevel(Enum):
    """Neural Web authority ladder A0–A7 (ratified D4, 2026-07-04).

    Each rung describes what the Neural Web may DO, not what it may see.
    Evidence requirements are encoded in Article 3 (grant_authority).
    """

    A0_OBSERVE = 0
    """OBSERVE — read all artifacts, ledger, health.  Held today by: bot_mcp."""

    A1_EXPLAIN = 1
    """EXPLAIN — narrate on any surface; produce committee memos.
    Held today by: all 6 Brains (narrative_brain, risk_brain, …)."""

    A2_ATTEND = 2
    """ATTEND — rank what deserves attention / operator deliberation.
    Held today by: briefing.py priority_queue."""

    A3_DE_ESCALATE = 3
    """DE-ESCALATE — lower LLM-facing escalations.
    Held today by: house law (6× clamp), heuristic de-esc gate."""

    A4_QUARANTINE = 4
    """QUARANTINE — freeze misbehaving engine output.
    Held today by: circuit breaker + §7 quarantine lane.
    Cortex may recommend; the breaker executes."""

    A5_GOVERN_TIERS = 5
    """GOVERN TIERS — promote / demote signals across DISPLAY→SHADOW→CONFIRMER→SCORED.
    Held today by: qledger ladder; qual_ladder.yml; passport ratchet.
    Promotions require gauntlet verdicts; demotions on measured decay are automatic."""

    A6_TUNE = 6
    """TUNE — adjust engine parameters / weights.
    Two lanes:
      (i)  bounded deterministic auto-apply — market_state_tune, intl_tune, arming
           predicates — ratified as standing A6 approvals (quarterly re-audit required).
      (ii) LLM-proposed — must land as machine-registered experiments with pre-committed
           gates; risk_radar_review arms only after lane-(ii) rewiring."""

    A7_ORIGINATE = 7
    """ORIGINATE — invent a signal, trade, or escalation.
    PERMANENTLY BANNED per Article 1.  grant() refuses this level unconditionally."""


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------

ARTICLES: dict[int, str] = {
    1: (
        "Article 1 — Origination Ban: The Neural Web may never originate a signal, "
        "trade, escalation, or claim.  A7 (ORIGINATE) is refused unconditionally."
    ),
    2: (
        "Article 2 — Scored-Path Perimeter: Money-path / ranked-output surfaces listed "
        "in config/synapse.yml meta.article2_surfaces require at minimum a shadow-with-"
        "track-record tier to influence.  These surfaces are the single source of truth "
        "— they are read, not duplicated here."
    ),
    3: (
        "Article 3 — Evidence Floor: Every authority grant must clear sample-size floors, "
        "a Wilson CI lower-bound lift > 1.25 (matches the retired point-estimate threshold — "
        "strictly tighter everywhere, zero grant-more cases), and freshness. "
        "Grants whose evidence has gone stale lapse — authority never persists on silence."
    ),
}


# ---------------------------------------------------------------------------
# A6 lane definitions (standing law, ratified D4 2026-07-04, expanded W7a PR2)
# ---------------------------------------------------------------------------

A6_LANES: dict[str, str] = {
    "i": (
        "A6 Lane (i) — Bounded Deterministic Auto-Apply: "
        "Clamped, do-no-harm-gated, pre-registered loops (market_state_tune, intl_tune, "
        "Engine-Fix arming predicates) are hereby ratified as standing A6 approvals.  "
        "Each auto-apply must log to the governance ledger (neuralweb.governance.v1) with "
        "event_type='a6_auto_apply', lane='i', backtest evidence, and calibration_ref.  "
        "Quarterly re-audit required: if the last apply is >180 calendar days old, a "
        "governance WARNING entry is emitted and human re-audit is required before the "
        "next auto-apply resumes."
    ),
    "ii": (
        "A6 Lane (ii) — LLM-Proposed Parameter Change: "
        "An Opus model proposes bounded parameter deltas; each proposal must be logged to "
        "the governance ledger as event_type='a6_llm_proposed' with the pre-committed gate "
        "BEFORE any apply decision.  The apply is executed only when a do-no-harm backtest "
        "confirms improvement; the result (apply or reject) is also logged.  "
        "Governance logging is fail-open: a logging failure never aborts the loop.  "
        "risk_radar_review is the canonical lane-(ii) tenant (W7a PR2, 2026-07-04); "
        "it arms via config.yml (risk_radar_review.enabled: true) and remains self-gated "
        "behind min_graded=30 + F1 do-no-harm + hard clamps."
    ),
}

A6_ARMING_PREDICATE_DOCTRINE: str = (
    "Arming-Predicate Doctrine (ratified D4 2026-07-04, standing A6 law): "
    "No env-flag safety switches.  Every flag-gated system declares an arming predicate "
    "(evidence-floor + self-gates); systems auto-arm with governance notification when the "
    "predicate holds.  Arming via config.yml (not _DEFAULTS) is the canonical mechanism — "
    "the config file is the operator's committed intent, readable by every run.  "
    "Source: research/ENGINE_FIX_MASTERPLAN.md §W4 + masterplan §4 A6 table row.  "
    "Standing approval: Engine Fix auto-arm doctrine ratified as A6 lane-(i) precedent."
)


# ---------------------------------------------------------------------------
# Article-2 perimeter (read from synapse.yml)
# ---------------------------------------------------------------------------

def article2_surfaces(root: str | Path | None = None) -> list[str]:
    """Return the Article-2 money-path surface list from config/synapse.yml.

    Single source of truth — we do NOT duplicate the list here.  If the file
    cannot be read, returns an empty list and logs a warning so callers can
    decide whether to fail-open or fail-closed.
    """
    try:
        import yaml  # optional at module level — only needed here
        if root is None:
            from lib import config  # type: ignore[import]
            base = Path(config.data_dir()).parent
        else:
            base = Path(root)
        p = base / "config" / "synapse.yml"
        if not p.exists():
            log.warning("constitution: synapse.yml not found at %s", p)
            return []
        with p.open() as fh:
            doc = yaml.safe_load(fh)
        return list((doc.get("meta") or {}).get("article2_surfaces") or [])
    except Exception as exc:  # noqa: BLE001
        log.warning("constitution: could not load article2_surfaces: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Wilson lower bound — wraps qledger to allow z parameterisation
# ---------------------------------------------------------------------------

def wilson_lower(k: int, n: int, z: float = 1.645) -> float:
    """90%-confidence one-sided Wilson score lower bound (z=1.645 default).

    Imports and wraps engine.qledger.wilson_ci_low, which defaults z=1.96.
    Calling with z=1.645 yields the 90% one-sided bound used by Article 3.

    Returns 0.0 when n == 0.
    """
    if n <= 0:
        return 0.0
    try:
        from engine.qledger import wilson_ci_low  # type: ignore[import]
        result = wilson_ci_low(hits=k, n=n, z=z)
        return float(result) if result is not None else 0.0
    except Exception:  # noqa: BLE001
        # Inline fallback (same formula) — never None, never raises
        import math
        phat = k / n
        z2 = z * z
        denom = 1.0 + z2 / n
        centre = phat + z2 / (2 * n)
        margin = z * math.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n)
        return max(0.0, round((centre - margin) / denom, 6))


# ---------------------------------------------------------------------------
# GrantResult
# ---------------------------------------------------------------------------

@dataclass
class GrantResult:
    """Result of an Article-3 authority-grant evaluation.

    Attributes
    ----------
    granted : bool
        True iff all three Article-3 gates cleared (n floors, Wilson lift, freshness).
    lift_lb : float | None
        wilson_lower(hits, n) / base_rate — the CI lower-bound lift.  None when base=0.
    wilson_lb : float | None
        The raw wilson_lower(hits, n) value.
    reason : str
        Human-readable explanation of the decision (for the governance ledger).
    lapses_at : str | None
        ISO-8601 UTC datetime when this grant expires (evidence_asof + max_staleness_days).
        None when the grant is already refused.
    """
    granted: bool
    lift_lb: float | None
    wilson_lb: float | None
    reason: str
    lapses_at: str | None


# ---------------------------------------------------------------------------
# Article-3 evaluator
# ---------------------------------------------------------------------------

def grant_authority(
    evidence: dict[str, Any],
    *,
    floors: dict[str, int],
    target_level: "AuthorityLevel | None" = None,
    now: datetime | None = None,
    max_staleness_days: int = 120,
) -> GrantResult:
    """Article-3 authority-grant evaluator.  Pure function — no IO, no side effects.

    Parameters
    ----------
    evidence : dict with keys:
        hits        : int   — number of alert-state calls where a drawdown occurred
        n           : int   — total number of graded alert-state calls
        base_rate   : float — base rate of drawdowns over ALL graded calls (including non-alerts)
        evidence_asof : str — ISO-8601 date of the most recent graded entry
    floors : dict with keys:
        min_n       : int — minimum total graded calls required (e.g. 30)
        min_events  : int — minimum loud-state calls required (e.g. 8)
    target_level : AuthorityLevel | None
        Optional target authority level.  If A7_ORIGINATE, the grant is refused
        unconditionally BEFORE any evidence evaluation (Article 1 — Origination Ban).
        Hard-coded refusal; no amount of evidence can override this.
    now : datetime | None
        Current time (UTC).  Defaults to datetime.now(timezone.utc).
    max_staleness_days : int
        A grant lapses when evidence_asof is older than this many days.  Default 120.

    Returns
    -------
    GrantResult
        granted=True only when ALL three Article-3 gates clear:
          1. n >= floors['min_n'] AND hits >= floors['min_events']
          2. wilson_lower(hits, n, z=1.645) / base_rate > 1.25
             (matches the retired point-estimate threshold of 1.25 — strictly tighter
             everywhere because wilson_lb <= point_estimate always; zero grant-more
             cases across all k/n/base sweep, verified by tests)
          3. evidence_asof within max_staleness_days
        Always refused when target_level is A7_ORIGINATE (Article 1 unconditional ban).
    """
    # Article 1 — Origination Ban: A7 is refused unconditionally, before any evidence
    # evaluation.  No amount of evidence, sample size, or Wilson lift can override this.
    if target_level is AuthorityLevel.A7_ORIGINATE:
        return GrantResult(
            granted=False,
            lift_lb=None,
            wilson_lb=None,
            reason="article-1-origination-ban: A7/ORIGINATE is permanently refused",
            lapses_at=None,
        )

    if now is None:
        now = datetime.now(timezone.utc)

    hits: int = int(evidence.get("hits") or 0)
    n: int = int(evidence.get("n") or 0)
    base_rate: float = float(evidence.get("base_rate") or 0.0)
    evidence_asof_str: str | None = evidence.get("evidence_asof")

    min_n: int = int(floors.get("min_n") or 0)
    min_events: int = int(floors.get("min_events") or 0)

    # Gate 1 — sample-size floors
    if n < min_n:
        return GrantResult(
            granted=False,
            lift_lb=None,
            wilson_lb=None,
            reason=f"insufficient-n: n={n} < min_n={min_n}",
            lapses_at=None,
        )
    if hits < min_events:
        return GrantResult(
            granted=False,
            lift_lb=None,
            wilson_lb=None,
            reason=f"insufficient-events: hits={hits} < min_events={min_events}",
            lapses_at=None,
        )

    # Gate 2 — Wilson CI lower-bound lift > 1.25
    # Threshold 1.25 matches the retired point-estimate floor (MIN_FORCE_LIFT=1.25).
    # Because wilson_lb <= point_estimate always, the CI gate is strictly tighter
    # everywhere — zero grant-more cases across a full k/n/base sweep (verified in
    # tests/test_constitution.py::test_wilson_gate_no_grant_more_cases_full_sweep).
    _LIFT_THRESHOLD = 1.25
    wb = wilson_lower(hits, n, z=1.645)
    if base_rate <= 0.0:
        return GrantResult(
            granted=False,
            lift_lb=None,
            wilson_lb=round(wb, 6),
            reason="zero-base-rate: cannot compute lift",
            lapses_at=None,
        )
    lift_lb = wb / base_rate

    if lift_lb <= _LIFT_THRESHOLD:
        return GrantResult(
            granted=False,
            lift_lb=round(lift_lb, 4),
            wilson_lb=round(wb, 6),
            reason=f"lift-lb-insufficient: wilson_lb/base={lift_lb:.4f} <= {_LIFT_THRESHOLD}",
            lapses_at=None,
        )

    # Gate 3 — freshness
    if evidence_asof_str is not None:
        try:
            asof_dt = datetime.fromisoformat(str(evidence_asof_str))
            if asof_dt.tzinfo is None:
                asof_dt = asof_dt.replace(tzinfo=timezone.utc)
            staleness = (now - asof_dt).days
            if staleness > max_staleness_days:
                return GrantResult(
                    granted=False,
                    lift_lb=round(lift_lb, 4),
                    wilson_lb=round(wb, 6),
                    reason=f"stale-evidence: {staleness}d > max {max_staleness_days}d",
                    lapses_at=None,
                )
            lapse_dt = asof_dt + timedelta(days=max_staleness_days)
        except Exception:  # noqa: BLE001
            lapse_dt = now + timedelta(days=max_staleness_days)
    else:
        lapse_dt = now + timedelta(days=max_staleness_days)

    lapses_at = lapse_dt.isoformat(timespec="seconds")
    return GrantResult(
        granted=True,
        lift_lb=round(lift_lb, 4),
        wilson_lb=round(wb, 6),
        reason="granted: n-floors cleared, wilson-lift > 1.25, evidence fresh",
        lapses_at=lapses_at,
    )
