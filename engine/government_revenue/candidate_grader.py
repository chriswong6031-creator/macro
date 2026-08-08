"""Prospective grader for Government Revenue research candidates — Wave 9G.

WHAT THIS IS FOR
----------------
The Government Revenue lobe can produce evidence-bound, receipt-backed,
well-argued candidates and still have **no predictive value**.  This module is
the instrument that is allowed to say so.  Every construction below is chosen so
that a null cannot be dressed up as a result, and so that the honest answer
"this family does not predict anything" is reachable from the data.

It grades ONE preregistered family at a time (``research/
GOVERNMENT_REVENUE_CANDIDATE_GRADER_PREREG.md``).  The family's horizons,
benchmarks, entry rule, hit definition, maturity gate, and kill condition are
frozen in that document BEFORE any observation exists, and a copy of the
horizons travels on every issuance row so a later edit to the document cannot
retro-change what a live cohort was promised.

AUTHORITY (unchanged, non-negotiable)
-------------------------------------
Output is ``display``/``context``.  This module cannot create, rank, size, or
gate anything, and an attractive interim number is not a promotion.  Promotion
requires the existing gauntlet and an operator ruling.  ``_authority()`` mirrors
``engine/government_revenue/candidates.py`` exactly.

THE STATISTICAL TRAPS THIS FILE IS BUILT AROUND
-----------------------------------------------
Each of these has actually shipped in this repository.  The structure that
prevents each one is named so a future edit cannot quietly remove it:

1. **Resolution-conditioned denominators delete losers.**  The cohort is
   enumerated from the issuance log at ISSUANCE (``cohort_rows``), never from
   the graded subset.  ``CohortOutcome.issued_n`` is fixed there.  The
   graded-conditioned ``hit_rate`` is emitted ONLY beside its ``coverage`` and
   beside ``hit_rate_bounds``, whose width IS the coverage penalty: the lower
   bound counts every ungraded row as a miss, the upper bound as a hit.  A
   retraction never removes a row from the denominator — you cannot retract your
   way out of a loss, only into a wider bound.
2. **An unresolved endpoint is not 0.5.**  There is no imputation path.  A row
   the grader cannot resolve is ``ungraded`` with a named reason and is excluded
   from BOTH the numerator and the denominator of the conditional rate.
3. **Median of a binary rate can flip sign versus the pooled rate.**
   ``monthly_and_pooled`` returns both or raises; the payload cannot carry a
   median of monthly rates without the pooled figure beside it.
4. **A cadence change makes an N-gate vacuous.**  Re-observing one event nightly
   must not manufacture cohort members: ``cohort_rows`` keeps the FIRST issuance
   per ``candidate_id``, and the maturity gate counts distinct source events,
   distinct issuers, and distinct event months — never row count alone.
5. **``resample("nB")`` start-anchors every bin.**  There is no pandas here and
   no business-day arithmetic.  Horizons are counted as INDEX STEPS along an
   explicit :class:`SessionCalendar` supplied by the caller, and a horizon whose
   exit index runs off the end of that calendar is ``ungraded``, never clamped.
6. **Price vintages move.**  The collection lane re-adjusts historical closes in
   place, so a grade computed today may not reproduce tomorrow.  Every grade row
   records the :class:`PriceBasis` it was computed against (field, adjustment,
   vintage id, vintage clock), a panel whose ADJUSTMENT differs from the
   registered family is refused outright, and :func:`regrade_diff` surfaces rows
   whose value moved under a new vintage instead of silently overwriting them.
7. **A track record built on incomplete history is an artifact.**  No rate can
   be emitted without its coverage: :class:`Rate` refuses construction without a
   :class:`Coverage`, and :func:`assert_rates_carry_coverage` walks the finished
   payload and fails closed on any bare ``*_rate`` value — and on every
   coverage-bearing SUMMARY (``*_summary``, ``*_mean``, ``*_bound``), because the
   kill-bearing statistic is a mean, not a rate, and a walker that only knows
   about rates is blind to the number the verdict actually reads.
8. **A point comparison at the gate floor is a coin flip.**  Every verdict input
   carries an SD, a standard error, and a bootstrap interval, and each verdict
   region requires the INTERVAL to clear its registered threshold.  The
   registered N is the N that threshold needs (§7 of the registration states the
   power calculation); an N chosen for convenience makes a preregistered kill
   fire on noise.
9. **You cannot ungrade your way out of a loss.**  A correction may not rewrite
   the fields that DEFINE the measurement (``known_at``, ``ticker``,
   ``horizons``, ``entry_rule``, the source event, the issuer), the reason must
   come from a closed vocabulary, and — the supersession ratchet — a grade a
   superseded row already earned is RETAINED for the verdict statistic when its
   superseding row cannot be graded.  Supersession may lower coverage; it may
   never delete a number.  Below the registered verdict coverage floor no
   verdict fires at all.
10. **Absence of data reads as absence of event.**  The disclosure labels
   (earnings windows and subsequent filings) would, in the natural
   implementation, return an empty list for an issuer no calendar covers — so
   every issuer with the WORST data would score as the cleanest window.
   :class:`DisclosureCalendar` therefore declares the tickers it covers, and
   ``none_in_window`` (looked, found nothing) is a different state from
   ``unavailable`` (could not look) that no code path merges.  The labels are
   computed AFTER :func:`evaluate_verdict` returns, so they cannot be a verdict
   input: §7.2's registered N is derived for the paired market-relative mean,
   and a decision rule that grew a term would leave that N wrong in the
   document.

THREE COVERAGES, NEVER ONE
--------------------------
The handoff is explicit that a lobe can have excellent identity coverage and no
predictive value.  ``identity`` (issuers with a reviewed exact mapping),
``event`` (eligible events the spine actually observed), and ``outcome``
(issuance rows the grader could resolve) are three separate
:class:`Coverage` objects with three separate keys, and an outcome rate may only
cite an ``outcome`` coverage.  There is deliberately no code path that fuses
them into one number.

REUSED IDIOMS (not a second scheme)
-----------------------------------
The canonical-JSON + ``sha256`` content-address shape is
``engine/government_revenue/candidates.py``'s (``_canonical_json`` / ``_digest``,
delivery clocks excluded from identity).  The append-only JSONL discipline —
LF-only, one canonical object per line, trailing newline, prior-prefix hash
binding — is ``scripts/build_government_revenue_candidates.py``'s candidate
ledger, and the receipt shape is its projection-state ledger receipt.  The entry
convention (fill strictly after the signal bar, forward-only windows) is
``engine/grading.py``'s.  Those modules are NOT imported: this one stays free of
``jsonschema``/``pandas`` so it can be graded in a minimal environment, and the
duplication is three helper functions, deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import random
from statistics import median as _median, stdev as _stdev
from typing import Any, Iterable, Mapping, Sequence

ISSUANCE_CONTRACT = "government_revenue.candidate_issuance.v1"
REPORT_CONTRACT = "government_revenue.candidate_grade_report.v1"
SCHEMA_VERSION = "1.0.0"
ISSUANCE_LOG_FILENAME = "candidate_issuance_log.jsonl"
PREREG_DOCUMENT = "research/GOVERNMENT_REVENUE_CANDIDATE_GRADER_PREREG.md"

ROW_KINDS = ("issuance", "abstention", "correction", "retraction")

#: Every reason the grader may decline to grade a row it DID issue.  There is no
#: "assume neutral" member and there never will be one.
UNGRADED_REASONS = (
    "horizon_not_matured",
    "entry_session_unavailable",
    "price_missing",
    "benchmark_missing",
    "mapping_missing",
    "source_outage",
    "retracted",
    "calendar_gap",
)

#: Every reason the family may decline to ISSUE a candidate at all.  These are
#: abstentions, not outcomes: they are recorded in the same append-only log and
#: reported as an abstention rate, and they never enter the cohort denominator.
ABSTENTION_REASONS = (
    "family_mismatch",
    "ceiling_change_out_of_family",
    "direction_not_positive",
    "deobligation",
    "late_discovery",
    "not_exact_linked",
    "authority_not_display",
    "missing_known_at",
    "missing_source_event",
)

COVERAGE_KINDS = ("identity", "event", "outcome")

#: Every reason a superseding row may state.  §8 of the registration restricts a
#: supersession to a SOURCE-EVIDENCE correction; free text let "we disagree with
#: the outcome" wear the same clothes as "the official record changed", so the
#: vocabulary is closed and checked on the row.
CORRECTION_REASONS = (
    "source_record_corrected",
    "source_receipt_binding_failed",
    "evidence_artifact_regenerated",
)

#: A retraction is the strictest form and takes the narrower list: the upstream
#: official record changed, or the receipt binding failed.  Disagreement with an
#: outcome is not expressible.
RETRACTION_REASONS = (
    "source_record_corrected",
    "source_receipt_binding_failed",
)

#: The ONLY fields a superseding row may change.  This is an ALLOWLIST, not a
#: blocklist, and that is the whole point: a blocklist admits every field added
#: later, and the fields that define the MEASUREMENT (``known_at``, ``ticker``,
#: ``horizons``, ``entry_rule``, ``source_event``, ``issuer_company_id``,
#: ``effective_at``, ``prereg_document_sha256``) are exactly the ones a
#: post-outcome edit would reach for.  Rewriting ``known_at`` after the outcome
#: is observable RE-CUTS the entry session — post-issuance information reaching
#: the grade, which is the single leak this module exists to prevent.
CORRECTABLE_ROW_FIELDS = frozenset(
    {
        "candidate_payload_sha256",
        "evidence_generation",
        "observation_id",
    }
)


class GraderError(ValueError):
    """The grader refuses to produce a number it cannot stand behind."""


# ---------------------------------------------------------------------------
# canonical bytes + content addressing (idiom mirrored from candidates.py)
# ---------------------------------------------------------------------------


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def canonical_bytes(value: Any) -> bytes:
    return _canonical_json(value).encode("utf-8")


def _digest(prefix: str, value: Any) -> str:
    return f"{prefix}-{sha256(canonical_bytes(value)).hexdigest()[:24]}"


def _authority() -> dict[str, Any]:
    """Byte-identical to ``candidates.py:_authority`` — display/context only."""
    return {
        "tier": "display",
        "context_only": True,
        "can_rank": False,
        "can_size": False,
        "can_gate": False,
        "can_originate_signal": False,
        "can_add_candidates": False,
        "can_escalate": False,
    }


def _instant(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith(("Z", "z")):
            text = f"{text[:-1]}+00:00"
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


# ---------------------------------------------------------------------------
# session calendar — the explicit anti-``resample("nB")`` device
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionCalendar:
    """An explicit, ordered list of trading sessions.

    Horizons are counted as steps along THIS list.  Nothing in this module ever
    performs date arithmetic, business-day offsets, or ``resample`` binning:
    ``pandas.resample("nB")`` start-anchors every bin and has silently
    misaligned four separate lanes in this repository.  A horizon that runs past
    the end of the calendar returns ``None`` and grades ``ungraded``; it is never
    clamped to the last available session, which would quietly shorten the
    window and flatter a live cohort.
    """

    calendar_id: str
    sessions: tuple[date, ...]

    @classmethod
    def from_dates(cls, values: Iterable[date], *, calendar_id: str) -> "SessionCalendar":
        identifier = _text(calendar_id)
        if identifier is None:
            raise GraderError("session calendar needs a calendar_id")
        days: list[date] = []
        for value in values:
            if isinstance(value, datetime):
                raise GraderError("session calendar takes dates, not datetimes")
            if not isinstance(value, date):
                raise GraderError("session calendar takes date objects")
            days.append(value)
        ordered = tuple(sorted(set(days)))
        if not ordered:
            raise GraderError("session calendar is empty")
        if len(ordered) != len(days):
            raise GraderError("session calendar has duplicate sessions")
        return cls(calendar_id=identifier, sessions=ordered)

    def index_of(self, day: date) -> int | None:
        try:
            return self.sessions.index(day)
        except ValueError:
            return None

    def first_index_after(self, day: date) -> int | None:
        """First session strictly LATER than ``day`` — never the same session."""
        for index, session in enumerate(self.sessions):
            if session > day:
                return index
        return None

    def session(self, index: int) -> date | None:
        if index < 0 or index >= len(self.sessions):
            return None
        return self.sessions[index]

    def to_payload(self) -> dict[str, Any]:
        return {
            "calendar_id": self.calendar_id,
            "session_count": len(self.sessions),
            "first_session": self.sessions[0].isoformat(),
            "last_session": self.sessions[-1].isoformat(),
        }


def _horizon_exit_index(entry_index: int, horizon_sessions: int) -> int:
    """The ONLY place a horizon's exit index is computed.

    Kept as a module-level seam on purpose: the no-leakage suite monkeypatches
    it to ``+ horizon + 1`` and asserts the grade CHANGES, which is what proves
    the leakage assertion elsewhere is not vacuous.
    """
    return entry_index + horizon_sessions


# ---------------------------------------------------------------------------
# price basis + panel — the pinned vintage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceBasis:
    """What was graded against, recorded on the row.

    ``vintage_id``/``vintage_observed_at`` exist because the collection lane
    re-adjusts historical closes IN PLACE.  A grade is only reproducible against
    the vintage that produced it, so the vintage travels with the number.
    """

    field: str
    adjustment: str
    vintage_id: str
    vintage_observed_at: str

    def __post_init__(self) -> None:
        for name in ("field", "adjustment", "vintage_id", "vintage_observed_at"):
            if _text(getattr(self, name)) is None:
                raise GraderError(f"price basis {name} is required")
        if _instant(self.vintage_observed_at) is None:
            raise GraderError("price basis vintage_observed_at must be an instant")

    def to_payload(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "adjustment": self.adjustment,
            "vintage_id": self.vintage_id,
            "vintage_observed_at": self.vintage_observed_at,
        }


@dataclass(frozen=True)
class PricePanel:
    """Closes by symbol and session, plus the basis they were taken under."""

    basis: PriceBasis
    series: Mapping[str, Mapping[date, float]]

    def close(self, symbol: str, day: date) -> float | None:
        rows = self.series.get(symbol)
        if not isinstance(rows, Mapping):
            return None
        value = rows.get(day)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if value <= 0:
            return None
        return float(value)


# ---------------------------------------------------------------------------
# the preregistered family
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Horizon:
    name: str
    sessions: int
    role: str  # "primary" | "supporting" | "disclosure"

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "sessions": self.sessions, "role": self.role}


@dataclass(frozen=True)
class PreregisteredFamily:
    family_id: str
    title: str
    document: str
    version: str
    horizons: tuple[Horizon, ...]
    primary_horizon: str
    market_benchmark: str
    sector_benchmark: str
    price_field: str
    price_adjustment: str
    entry_session_rule: str
    hit_definition: str
    drawdown_definition: str
    placebo_offset_sessions: int
    calendar_id: str
    min_distinct_source_events: int
    min_distinct_issuers: int
    min_distinct_event_months: int
    # The event clock and the ENTRY clock are separate requirements.  A backfill
    # night can hand 40 events spanning 12 historical months ONE `known_at`, and
    # then every row shares one entry session and one market window: 40 rows, one
    # independent draw.  `effective_at` months alone cannot see that.
    min_distinct_known_at_months: int
    min_distinct_entry_sessions: int
    min_outcome_coverage: float
    # --- decision rule (registered here so the document/code drift guard sees
    # every threshold; a constant living only in the module is a threshold §9
    # cannot police) ---
    minimum_interesting_effect: float
    hit_rate_floor: float
    confidence_level: float
    bootstrap_resamples: int
    bootstrap_seed: int
    min_verdict_outcome_coverage: float
    # --- power (the arithmetic behind the registered N) ---
    planning_sd_paired: float
    planning_alpha: float
    planning_power: float
    planning_n_required: int
    accrual_expiry_date: str
    kill_condition_id: str

    def horizon(self, name: str) -> Horizon | None:
        for candidate in self.horizons:
            if candidate.name == name:
                return candidate
        return None

    def to_payload(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "title": self.title,
            "document": self.document,
            "version": self.version,
            "horizons": [horizon.to_payload() for horizon in self.horizons],
            "primary_horizon": self.primary_horizon,
            "market_benchmark": self.market_benchmark,
            "sector_benchmark": self.sector_benchmark,
            "price_field": self.price_field,
            "price_adjustment": self.price_adjustment,
            "entry_session_rule": self.entry_session_rule,
            "hit_definition": self.hit_definition,
            "drawdown_definition": self.drawdown_definition,
            "placebo_offset_sessions": self.placebo_offset_sessions,
            "calendar_id": self.calendar_id,
            "maturity_gate": {
                "min_distinct_source_events": self.min_distinct_source_events,
                "min_distinct_issuers": self.min_distinct_issuers,
                "min_distinct_event_months": self.min_distinct_event_months,
                "min_distinct_known_at_months": self.min_distinct_known_at_months,
                "min_distinct_entry_sessions": self.min_distinct_entry_sessions,
                "min_outcome_coverage": self.min_outcome_coverage,
            },
            "decision_rule": {
                "minimum_interesting_effect": self.minimum_interesting_effect,
                "hit_rate_floor": self.hit_rate_floor,
                "confidence_level": self.confidence_level,
                "bootstrap_resamples": self.bootstrap_resamples,
                "bootstrap_seed": self.bootstrap_seed,
                "min_verdict_outcome_coverage": self.min_verdict_outcome_coverage,
            },
            "power": {
                "planning_sd_paired": self.planning_sd_paired,
                "planning_alpha": self.planning_alpha,
                "planning_power": self.planning_power,
                "planning_n_required": self.planning_n_required,
            },
            "accrual_expiry_date": self.accrual_expiry_date,
            "kill_condition_id": self.kill_condition_id,
        }


#: The first — and for Wave 9G the only — preregistered family.  Narrow on
#: purpose: exact reviewed issuer, receipt-bound, a POSITIVE funded obligation
#: change on an existing award.  Ceiling-only changes (`award_ceiling_change`)
#: move no money and are a different economic claim, so they abstain here rather
#: than being folded in; option exercises and new awards likewise wait for their
#: own registration.  Values are mirrored in the preregistration document and
#: :func:`load_family_declaration` refuses to let the two drift.
GRV_FA1 = PreregisteredFamily(
    family_id="grv-fa1",
    title="exact-issuer receipt-bound positive funded-action acceleration",
    document=PREREG_DOCUMENT,
    version="3.0.0",
    horizons=(
        Horizon(name="h5", sessions=5, role="disclosure"),
        Horizon(name="h21", sessions=21, role="supporting"),
        Horizon(name="h63", sessions=63, role="primary"),
        Horizon(name="h126", sessions=126, role="supporting"),
    ),
    primary_horizon="h63",
    market_benchmark="SPY",
    sector_benchmark="ITA",
    price_field="close",
    price_adjustment="split_and_dividend_adjusted",
    entry_session_rule="first_session_strictly_after_known_at_utc_date",
    hit_definition="market_relative_return > 0",
    drawdown_definition="min over [entry_session, exit_session] of close/entry_close - 1",
    placebo_offset_sessions=-252,
    calendar_id="us_equity_sessions",
    # 545 is not a round number and is not a comfort number: it is what §7's
    # power calculation requires to separate the registered minimum interesting
    # effect (+3.0pp paired, h63) from a paired SD of 25pp at 80% power and
    # alpha 0.05.  The prior 40 made every verdict a coin flip in a lab coat.
    min_distinct_source_events=545,
    min_distinct_issuers=12,
    min_distinct_event_months=12,
    min_distinct_known_at_months=12,
    min_distinct_entry_sessions=120,
    min_outcome_coverage=0.70,
    minimum_interesting_effect=0.03,
    hit_rate_floor=0.50,
    confidence_level=0.95,
    bootstrap_resamples=2000,
    bootstrap_seed=20260806,
    min_verdict_outcome_coverage=0.70,
    planning_sd_paired=0.25,
    planning_alpha=0.05,
    planning_power=0.80,
    planning_n_required=545,
    accrual_expiry_date="2029-08-06",
    kill_condition_id="GRV-FA1-KILL-V2",
)

_FAMILY_REGISTRY = {GRV_FA1.family_id: GRV_FA1}

_DECLARATION_FENCE = "```json"


def family_by_id(family_id: str) -> PreregisteredFamily:
    family = _FAMILY_REGISTRY.get(family_id)
    if family is None:
        raise GraderError(f"unregistered candidate family: {family_id!r}")
    return family


def load_family_declaration(path: Path) -> tuple[PreregisteredFamily, str]:
    """Read the preregistration document and refuse code/document drift.

    Returns the registered family and the document's ``sha256``.  The digest is
    stamped on every issuance row, so an edit to the document after a cohort
    starts accruing is detectable from the log alone.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:  # pragma: no cover - filesystem failure
        raise GraderError(f"preregistration document is unavailable: {path}") from exc
    text = raw.decode("utf-8")
    start = text.find(_DECLARATION_FENCE)
    if start < 0:
        raise GraderError("preregistration document has no machine-readable declaration")
    body_start = start + len(_DECLARATION_FENCE)
    end = text.find("```", body_start)
    if end < 0:
        raise GraderError("preregistration declaration block is unterminated")
    try:
        declared = json.loads(text[body_start:end])
    except json.JSONDecodeError as exc:
        raise GraderError("preregistration declaration block is not JSON") from exc
    if not isinstance(declared, Mapping):
        raise GraderError("preregistration declaration block is not an object")
    family_id = _text(declared.get("family_id"))
    if family_id is None:
        raise GraderError("preregistration declaration has no family_id")
    family = family_by_id(family_id)
    if declared != family.to_payload():
        raise GraderError(
            "preregistration document and registered family disagree; "
            "a live cohort's terms may not be edited on either side"
        )
    # The kill condition must be WRITTEN OUT, not merely named by an id inside
    # the declaration block: an id with no prose behind it is not a decision rule
    # anyone can be held to.  The block is excluded from this search on purpose.
    prose = text[:start] + text[end:]
    if family.kill_condition_id not in prose:
        raise GraderError("preregistration document does not state its kill condition")
    return family, sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# admission — what the family will and will not issue
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdmissionDecision:
    admitted: bool
    reason: str | None


def admit(candidate: Mapping[str, Any], *, family: PreregisteredFamily) -> AdmissionDecision:
    """Decide, from ISSUANCE-TIME fields only, whether the family issues this.

    Every rejection is a named abstention reason, recorded in the log.  Nothing
    here reads a price, an outcome, or a clock later than the candidate's own
    ``known_at``.
    """
    if not isinstance(candidate, Mapping):
        return AdmissionDecision(False, "family_mismatch")
    if family.family_id != GRV_FA1.family_id:  # pragma: no cover - one family in W9G
        raise GraderError(f"no admission policy registered for {family.family_id!r}")
    authority = candidate.get("authority")
    if not isinstance(authority, Mapping) or dict(authority) != _authority():
        return AdmissionDecision(False, "authority_not_display")
    if _instant(candidate.get("known_at")) is None:
        return AdmissionDecision(False, "missing_known_at")
    source_event = candidate.get("source_event")
    if not isinstance(source_event, Mapping):
        return AdmissionDecision(False, "missing_source_event")
    candidate_family = candidate.get("candidate_family")
    if candidate_family == "award_ceiling_change":
        return AdmissionDecision(False, "ceiling_change_out_of_family")
    if candidate_family != "award_obligation_change":
        return AdmissionDecision(False, "family_mismatch")
    if source_event.get("event_type") == "deobligation":
        return AdmissionDecision(False, "deobligation")
    if candidate.get("transmission_direction") != "possible_positive":
        return AdmissionDecision(False, "direction_not_positive")
    coverage = candidate.get("coverage")
    if not isinstance(coverage, Mapping) or coverage.get("exact_link_status") != "exact_linked":
        return AdmissionDecision(False, "not_exact_linked")
    if source_event.get("is_late_discovery") is not False:
        # A late-discovered action was public before our pipeline could see it.
        # Grading it as if `known_at` were the market's first knowledge would
        # measure stale news, so the family abstains and reports the count.
        #
        # FAIL-CLOSED, and this is the whole point of the phrasing.  `bool(...)`
        # admitted a candidate whose payload simply OMITTED the key — the one
        # admission test in this function that failed OPEN, guarding the one
        # thing §1 says it guards.  A missing, null, or non-boolean flag is not
        # evidence of a fresh discovery; it is an absence of evidence, and the
        # family abstains on it.
        return AdmissionDecision(False, "late_discovery")
    return AdmissionDecision(True, None)


# ---------------------------------------------------------------------------
# the immutable issuance log
# ---------------------------------------------------------------------------

_ROW_FIELDS = (
    "contract",
    "schema_version",
    "row_kind",
    "row_id",
    "supersedes_row_id",
    "correction_reason",
    "abstention_reason",
    "family_id",
    "prereg_document",
    "prereg_version",
    "prereg_document_sha256",
    "horizons",
    "candidate_id",
    "observation_id",
    "ticker",
    "issuer_company_id",
    "candidate_payload_sha256",
    "known_at",
    "effective_at",
    "source_event",
    "evidence_generation",
    "entry_rule",
    "authority",
    "appended_at",
)

#: ``appended_at`` is a delivery clock and ``row_id`` is the address itself, so
#: neither participates in the address — same exclusion rule as the candidate
#: queue's ``candidate_queue_content_id``.
_ROW_ID_EXCLUDED = frozenset({"row_id", "appended_at"})


def row_content_id(row: Mapping[str, Any]) -> str:
    return _digest(
        "gri1",
        {key: value for key, value in row.items() if key not in _ROW_ID_EXCLUDED},
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GraderError(message)


def validate_issuance_row(row: Mapping[str, Any], *, label: str = "issuance row") -> None:
    _require(isinstance(row, Mapping), f"{label} is not an object")
    _require(set(row) == set(_ROW_FIELDS), f"{label} has an invalid field set")
    _require(row.get("contract") == ISSUANCE_CONTRACT, f"{label} has an invalid contract")
    _require(row.get("schema_version") == SCHEMA_VERSION, f"{label} has an invalid schema version")
    kind = row.get("row_kind")
    _require(kind in ROW_KINDS, f"{label} has an invalid row_kind")
    for name in ("family_id", "prereg_document", "prereg_version", "candidate_id", "ticker"):
        _require(_text(row.get(name)) is not None, f"{label} {name} is required")
    digest = row.get("prereg_document_sha256")
    _require(
        isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
        f"{label} prereg_document_sha256 is invalid",
    )
    _require(_instant(row.get("known_at")) is not None, f"{label} known_at is invalid")
    _require(_instant(row.get("appended_at")) is not None, f"{label} appended_at is invalid")
    _require(dict(row.get("authority") or {}) == _authority(), f"{label} authority is not display-tier")
    _require(row_content_id(row) == row.get("row_id"), f"{label} row_id does not address its own content")

    if kind == "abstention":
        _require(
            row.get("abstention_reason") in ABSTENTION_REASONS,
            f"{label} abstention_reason is invalid",
        )
        _require(row.get("horizons") == [], f"{label} abstention must carry no horizons")
        _require(row.get("entry_rule") is None, f"{label} abstention must carry no entry rule")
        _require(row.get("supersedes_row_id") is None, f"{label} abstention cannot supersede")
        return

    _require(row.get("abstention_reason") is None, f"{label} must not carry an abstention reason")
    horizons = row.get("horizons")
    _require(
        isinstance(horizons, list) and bool(horizons),
        f"{label} must freeze at least one horizon at issuance",
    )
    seen: set[str] = set()
    for horizon in horizons:
        _require(isinstance(horizon, Mapping), f"{label} horizon is not an object")
        _require(set(horizon) == {"name", "sessions", "role"}, f"{label} horizon has an invalid field set")
        name = _text(horizon.get("name"))
        _require(name is not None and name not in seen, f"{label} has a duplicate or unnamed horizon")
        seen.add(str(name))
        sessions = horizon.get("sessions")
        _require(
            isinstance(sessions, int) and not isinstance(sessions, bool) and sessions > 0,
            f"{label} horizon sessions must be a positive integer",
        )
    entry_rule = row.get("entry_rule")
    _require(isinstance(entry_rule, Mapping), f"{label} entry_rule is required")
    _require(
        set(entry_rule) == {"rule", "calendar_id", "price_basis", "market_benchmark", "sector_benchmark"},
        f"{label} entry_rule has an invalid field set",
    )
    basis = entry_rule.get("price_basis")
    _require(isinstance(basis, Mapping), f"{label} entry_rule price_basis is required")
    _require(
        set(basis) == {"field", "adjustment", "vintage_id", "vintage_observed_at"},
        f"{label} entry_rule price_basis has an invalid field set",
    )
    source_event = row.get("source_event")
    _require(isinstance(source_event, Mapping), f"{label} source_event is required")
    _require(
        set(source_event) == {"event_id", "event_type", "source_rail", "source_content_id", "is_late_discovery"},
        f"{label} source_event has an invalid field set",
    )
    _require(_text(source_event.get("event_id")) is not None, f"{label} source_event event_id is required")
    evidence = row.get("evidence_generation")
    _require(isinstance(evidence, Mapping), f"{label} evidence_generation is required")
    _require(
        set(evidence) == {"artifact_content_ids", "graph_id", "graph_digest", "receipt_ref_ids", "event_refs"},
        f"{label} evidence_generation has an invalid field set",
    )
    _require(
        isinstance(evidence.get("artifact_content_ids"), list) and bool(evidence["artifact_content_ids"]),
        f"{label} evidence_generation must name the artifact generation it depended on",
    )

    if kind == "issuance":
        _require(row.get("supersedes_row_id") is None, f"{label} issuance cannot supersede")
        _require(row.get("correction_reason") is None, f"{label} issuance carries no correction reason")
    else:
        _require(_text(row.get("supersedes_row_id")) is not None, f"{label} {kind} must name the row it supersedes")
        _require(_text(row.get("correction_reason")) is not None, f"{label} {kind} must state its reason")
        # §8 restricts a supersession to a source-evidence correction.  Free text
        # let "we dislike the outcome" wear the same clothes as "the official
        # record changed", so the reason comes from a closed vocabulary.
        _require(
            row.get("correction_reason") in CORRECTION_REASONS,
            f"{label} correction_reason is not a registered correction reason",
        )
        if kind == "retraction":
            _require(
                row.get("correction_reason") in RETRACTION_REASONS,
                f"{label} correction_reason is not a registered retraction reason",
            )


def build_issuance_row(
    candidate: Mapping[str, Any],
    *,
    family: PreregisteredFamily,
    prereg_document_sha256: str,
    price_basis: PriceBasis,
    appended_at: str,
    decision: AdmissionDecision | None = None,
) -> dict[str, Any]:
    """Build the append-only row for one considered candidate.

    An abstained candidate produces an ``abstention`` row: the family's refusals
    are part of the record, not a silent filter, so the abstention rate is
    computable from the log alone.
    """
    verdict = decision if decision is not None else admit(candidate, family=family)
    source_event = candidate.get("source_event")
    source_event = source_event if isinstance(source_event, Mapping) else {}
    known_at = _instant(candidate.get("known_at"))
    effective_at = _instant(candidate.get("effective_at"))
    resolution = candidate.get("issuer_resolution_ref")
    resolution = resolution if isinstance(resolution, Mapping) else {}
    receipts = candidate.get("source_receipt_refs")
    receipt_ids = sorted(
        {
            str(ref.get("ref_id"))
            for ref in (receipts if isinstance(receipts, list) else [])
            if isinstance(ref, Mapping) and _text(ref.get("ref_id")) is not None
        }
    )
    artifact_ids = candidate.get("artifact_content_ids")
    artifact_ids = sorted({str(value) for value in artifact_ids}) if isinstance(artifact_ids, list) else []
    event_refs = candidate.get("event_refs")
    event_refs = sorted({str(value) for value in event_refs}) if isinstance(event_refs, list) else []

    row: dict[str, Any] = {
        "contract": ISSUANCE_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "row_kind": "issuance" if verdict.admitted else "abstention",
        "row_id": "",
        "supersedes_row_id": None,
        "correction_reason": None,
        "abstention_reason": None if verdict.admitted else verdict.reason,
        "family_id": family.family_id,
        "prereg_document": family.document,
        "prereg_version": family.version,
        "prereg_document_sha256": prereg_document_sha256,
        # Horizons are COPIED here, frozen, at issuance.  Grading reads them off
        # the row, never off the live family object, so a later edit to the
        # registration cannot re-cut a window on an already-accruing cohort.
        "horizons": [horizon.to_payload() for horizon in family.horizons] if verdict.admitted else [],
        "candidate_id": _text(candidate.get("candidate_id")) or "",
        "observation_id": _text(candidate.get("observation_id")),
        "ticker": _text(candidate.get("ticker")) or "",
        "issuer_company_id": _text(candidate.get("issuer_company_id")),
        "candidate_payload_sha256": sha256(canonical_bytes(candidate)).hexdigest(),
        "known_at": known_at.isoformat() if known_at else _text(candidate.get("known_at")),
        "effective_at": effective_at.isoformat() if effective_at else None,
        "source_event": {
            "event_id": _text(source_event.get("event_id")),
            "event_type": _text(source_event.get("event_type")),
            "source_rail": _text(source_event.get("source_rail")),
            "source_content_id": _text(source_event.get("source_content_id")),
            "is_late_discovery": bool(source_event.get("is_late_discovery")),
        }
        if verdict.admitted
        else None,
        "evidence_generation": {
            "artifact_content_ids": artifact_ids,
            "graph_id": _text(resolution.get("graph_id")),
            "graph_digest": _text(resolution.get("graph_digest")),
            "receipt_ref_ids": receipt_ids,
            "event_refs": event_refs,
        }
        if verdict.admitted
        else None,
        "entry_rule": {
            "rule": family.entry_session_rule,
            "calendar_id": family.calendar_id,
            "price_basis": price_basis.to_payload(),
            "market_benchmark": family.market_benchmark,
            "sector_benchmark": family.sector_benchmark,
        }
        if verdict.admitted
        else None,
        "authority": _authority(),
        "appended_at": appended_at,
    }
    if not verdict.admitted:
        row["source_event"] = None
        row["evidence_generation"] = None
    row["row_id"] = row_content_id(row)
    validate_issuance_row(row)
    return row


def build_correction_row(
    prior: Mapping[str, Any],
    *,
    reason: str,
    appended_at: str,
    changes: Mapping[str, Any] | None = None,
    retract: bool = False,
) -> dict[str, Any]:
    """Append a superseding row.  The prior row is never touched.

    A retraction does NOT remove its target from the issuance cohort.  It moves
    the row to ``ungraded(retracted)``, which lowers coverage and widens the
    hit-rate bounds — you cannot retract your way out of a loss.

    Nor can you CORRECT your way out of one.  A superseding row may change only
    :data:`CORRECTABLE_ROW_FIELDS`; everything that defines the measurement is
    refused.  Rewriting ``known_at`` after the outcome is observable re-cuts the
    entry session and lets post-issuance information reach the grade; rewriting
    ``ticker`` moves the row onto a symbol the panel does not carry and quietly
    ungrades it; rewriting ``horizons`` or ``entry_rule`` re-cuts the window that
    §3 froze at issuance.  The allowlist is deliberate — a blocklist would admit
    every field a later schema adds.
    """
    validate_issuance_row(prior, label="superseded row")
    if prior.get("row_kind") == "abstention":
        raise GraderError("an abstention row has nothing to correct")
    if _text(reason) is None:
        raise GraderError("a correction must state its reason")
    allowed = RETRACTION_REASONS if retract else CORRECTION_REASONS
    if reason not in allowed:
        raise GraderError(
            f"correction_reason {reason!r} is not a registered "
            f"{'retraction' if retract else 'correction'} reason; §8 admits only "
            f"source-evidence corrections: {list(allowed)}"
        )
    row = dict(prior)
    for key, value in (changes or {}).items():
        if key not in _ROW_FIELDS:
            raise GraderError(f"correction cannot introduce field {key!r}")
        if key not in CORRECTABLE_ROW_FIELDS:
            raise GraderError(
                f"correction cannot rewrite {key!r}: it defines the measurement, "
                "and a measurement rewritten after the outcome is observable is "
                "post-issuance information reaching the grade"
            )
        row[key] = value
    row["row_kind"] = "retraction" if retract else "correction"
    row["supersedes_row_id"] = prior["row_id"]
    row["correction_reason"] = reason
    row["appended_at"] = appended_at
    row["row_id"] = row_content_id(row)
    validate_issuance_row(row, label="correction row")
    if row["row_id"] == prior["row_id"]:
        raise GraderError("a correction must differ from the row it supersedes")
    return row


@dataclass(frozen=True)
class IssuanceLog:
    raw: bytes
    rows: tuple[dict[str, Any], ...]

    @property
    def sha256(self) -> str:
        return sha256(self.raw).hexdigest()

    @property
    def byte_count(self) -> int:
        return len(self.raw)

    @property
    def line_count(self) -> int:
        return len(self.rows)


def parse_issuance_log(raw: bytes, *, label: str = "candidate issuance log") -> IssuanceLog:
    """Canonical JSONL only — LF endings, one canonical object per line.

    Same discipline as the candidate ledger in
    ``scripts/build_government_revenue_candidates.py``: a row that is not
    byte-canonical is a rewritten row, and a rewritten row is a mutated row.
    """
    if not raw:
        return IssuanceLog(raw=b"", rows=())
    if not raw.endswith(b"\n"):
        raise GraderError(f"{label} must end with one canonical JSONL newline")
    if b"\r" in raw:
        raise GraderError(f"{label} must use LF-only canonical JSONL")
    lines = raw[:-1].split(b"\n")
    if any(not line for line in lines):
        raise GraderError(f"{label} contains an empty JSONL row")
    rows: list[dict[str, Any]] = []
    row_ids: set[str] = set()
    for index, line in enumerate(lines, start=1):
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GraderError(f"{label} row {index} is malformed JSON") from exc
        if not isinstance(value, dict):
            raise GraderError(f"{label} row {index} is not an object")
        validate_issuance_row(value, label=f"{label} row {index}")
        if line != canonical_bytes(value):
            raise GraderError(f"{label} row {index} is not canonical JSON")
        row_id = str(value["row_id"])
        if row_id in row_ids:
            raise GraderError(f"{label} has a duplicate row_id")
        row_ids.add(row_id)
        rows.append(value)
    return IssuanceLog(raw=raw, rows=tuple(rows))


def load_issuance_log(path: Path) -> IssuanceLog:
    target = Path(path)
    try:
        raw = target.read_bytes() if target.exists() else b""
    except OSError as exc:  # pragma: no cover - filesystem failure
        raise GraderError(f"candidate issuance log is unavailable: {target}") from exc
    return parse_issuance_log(raw)


def verify_append_only(prior_raw: bytes, current_raw: bytes) -> bool:
    """True iff ``current_raw`` extends ``prior_raw`` without rewriting a byte."""
    return current_raw[: len(prior_raw)] == prior_raw


def append_issuance_rows(path: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Append rows and return the prefix-bound receipt.

    The write is ``"ab"`` — append-only at the syscall — and the receipt binds
    the prior prefix by hash so a later rewrite is detectable from the receipt
    alone.  A ``row_id`` already present is refused: a re-observation of an
    unchanged candidate is not a new record, and letting it through is exactly
    how issuance cadence inflates an N-gate.

    Honest limit, measured: the guarantee the tests can enforce is that the
    prior BYTES are unchanged, not that the syscall was an append.  A rewrite
    that reproduces the prefix exactly is indistinguishable from an append and
    leaves the record identical, so it is not a defect; a rewrite that changes
    or drops a superseded row fails both the prefix check here and the
    byte-identity assertion in the suite.
    """
    target = Path(path)
    prior = load_issuance_log(target)
    prior_ids = {row["row_id"] for row in prior.rows}
    payload = bytearray()
    batch_ids: set[str] = set()
    for index, row in enumerate(rows, start=1):
        validate_issuance_row(row, label=f"appended row {index}")
        row_id = str(row["row_id"])
        if row_id in prior_ids or row_id in batch_ids:
            raise GraderError(f"appended row {index} duplicates an existing row_id")
        batch_ids.add(row_id)
        supersedes = row.get("supersedes_row_id")
        if supersedes is not None and supersedes not in prior_ids and supersedes not in batch_ids:
            raise GraderError(f"appended row {index} supersedes a row that is not in the log")
        payload += canonical_bytes(dict(row)) + b"\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "ab") as handle:
        handle.write(bytes(payload))
    current = load_issuance_log(target)
    if not verify_append_only(prior.raw, current.raw):
        raise GraderError("candidate issuance log was rewritten, not appended")
    return {
        "contract": ISSUANCE_CONTRACT,
        "prior_sha256": sha256(prior.raw).hexdigest(),
        "prior_byte_count": prior.byte_count,
        "prior_line_count": prior.line_count,
        "sha256": current.sha256,
        "byte_count": current.byte_count,
        "line_count": current.line_count,
        "append_count": current.line_count - prior.line_count,
    }


def cohort_rows(log: IssuanceLog, *, family_id: str) -> tuple[dict[str, Any], ...]:
    """The issuance-time cohort: one row per candidate, first issuance wins.

    This is THE denominator.  It is enumerated here, from issuance, and never
    from the graded subset — a rate computed over "rows that resolved" deletes
    losers whenever resolution correlates with outcome.

    Re-observing the same candidate (a later ``observation_id`` for the same
    ``candidate_id``) does not add a cohort member, so raising issuance cadence
    cannot manufacture N.  Only an explicit correction/retraction replaces a row.
    """
    effective: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    by_row_id: dict[str, dict[str, Any]] = {}
    for row in log.rows:
        if row.get("family_id") != family_id or row.get("row_kind") == "abstention":
            continue
        by_row_id[str(row["row_id"])] = row
        candidate_id = str(row["candidate_id"])
        if row["row_kind"] == "issuance":
            if candidate_id in effective:
                continue
            effective[candidate_id] = row
            order.append(candidate_id)
            continue
        target = by_row_id.get(str(row.get("supersedes_row_id")))
        if target is None or str(target.get("candidate_id")) != candidate_id:
            raise GraderError("a correction supersedes a row from a different candidate")
        if candidate_id not in effective:
            raise GraderError("a correction supersedes a candidate that was never issued")
        effective[candidate_id] = row
    return tuple(effective[candidate_id] for candidate_id in order)


def superseded_ancestors(log: IssuanceLog, *, family_id: str) -> dict[str, tuple[dict[str, Any], ...]]:
    """Every row a later row superseded, per ``candidate_id``, oldest first.

    The append-only log keeps a superseded row byte-identical forever, so a grade
    that row already earned is still computable.  :func:`build_cohort_report`
    uses that for the SUPERSESSION RATCHET: a correction or retraction may lower
    coverage, but it may never delete a number the prior row had already earned.
    Without this, ``ungraded`` is a discretionary escape hatch from the
    kill-bearing mean, and §8's promise ("you cannot retract your way out of a
    loss") holds for the hit-rate bounds and is false for the verdict.
    """
    ancestors: dict[str, list[dict[str, Any]]] = {}
    by_row_id = {
        str(row["row_id"]): row
        for row in log.rows
        if row.get("family_id") == family_id and row.get("row_kind") != "abstention"
    }
    for row in log.rows:
        if row.get("family_id") != family_id or row.get("row_kind") == "abstention":
            continue
        target_id = row.get("supersedes_row_id")
        if target_id is None:
            continue
        target = by_row_id.get(str(target_id))
        if target is None:
            continue
        ancestors.setdefault(str(row["candidate_id"]), []).append(target)
    return {candidate_id: tuple(rows) for candidate_id, rows in ancestors.items()}


def abstention_rows(log: IssuanceLog, *, family_id: str) -> tuple[dict[str, Any], ...]:
    return tuple(
        row
        for row in log.rows
        if row.get("family_id") == family_id and row.get("row_kind") == "abstention"
    )


# ---------------------------------------------------------------------------
# coverage + rates — a rate may not be emitted without its coverage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Coverage:
    """One of exactly three kinds, never fused into a single number."""

    kind: str
    scope: str
    observed: int
    universe: int
    status: str

    def __post_init__(self) -> None:
        if self.kind not in COVERAGE_KINDS:
            raise GraderError(f"coverage kind must be one of {COVERAGE_KINDS}")
        if _text(self.scope) is None:
            raise GraderError("coverage needs a scope")
        if _text(self.status) is None:
            raise GraderError("coverage needs a status")
        for name in ("observed", "universe"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GraderError(f"coverage {name} must be a non-negative integer")
        if self.observed > self.universe:
            raise GraderError("coverage cannot observe more than its universe")

    @property
    def fraction(self) -> float | None:
        if self.universe == 0:
            return None
        return self.observed / self.universe

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "scope": self.scope,
            "observed": self.observed,
            "universe": self.universe,
            "fraction": self.fraction,
            "status": self.status,
        }


@dataclass(frozen=True)
class Rate:
    """A rate that structurally cannot travel without its coverage."""

    name: str
    numerator: int
    denominator: int
    coverage: Coverage

    def __post_init__(self) -> None:
        if _text(self.name) is None:
            raise GraderError("a rate needs a name")
        if not isinstance(self.coverage, Coverage):
            raise GraderError(f"rate {self.name!r} cannot be emitted without its coverage")
        for field_name in ("numerator", "denominator"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GraderError(f"rate {self.name!r} {field_name} must be a non-negative integer")
        if self.numerator > self.denominator:
            raise GraderError(f"rate {self.name!r} numerator exceeds its denominator")

    @property
    def value(self) -> float | None:
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "value": self.value,
            "coverage": self.coverage.to_payload(),
        }


#: Key suffixes that make a value coverage-bearing.  ``_rate``/``_ratio`` were
#: the original pair and they left the walker structurally blind to the numbers
#: the VERDICT reads: the kill-bearing statistic is a pooled MEAN, and
#: ``market_relative_return``, ``absolute_return``, ``max_drawdown`` and the
#: placebo delta all sailed past a rate-only walker.  Aggregate blocks therefore
#: carry a ``_summary`` suffix, means carry ``_mean``, and bounds carry
#: ``_bound``, so the walker can see every one of them.  Per-row payloads
#: deliberately use bare names (``market_relative_return``) because a single row
#: is an observation, not a statistic over a cohort.
COVERAGE_BEARING_SUFFIXES = ("_rate", "_ratio", "_mean", "_summary", "_bound")


def assert_rates_carry_coverage(payload: Any, *, path: str = "$") -> None:
    """Fail closed on any cohort statistic emitted without a coverage beside it.

    Belt-and-braces over :class:`Rate`: a hand-built dict added to the report by
    a later edit is caught here rather than shipping a bare percentage.  A rate
    must cite an ``outcome`` coverage — citing identity or event coverage would
    let "we mapped 90% of the issuers" stand in for "we resolved 90% of the
    cohort", which is precisely the conflation the handoff forbids.
    """
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            here = f"{path}.{key}"
            if key.endswith(COVERAGE_BEARING_SUFFIXES):
                if isinstance(value, Mapping):
                    holder: Mapping[str, Any] = value
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    holder = payload
                elif value is None:
                    holder = payload
                else:
                    holder = {}
                coverage = holder.get("coverage") if isinstance(holder, Mapping) else None
                if not isinstance(coverage, Mapping):
                    raise GraderError(f"{here} is a cohort statistic with no coverage beside it")
                if coverage.get("kind") != "outcome":
                    raise GraderError(
                        f"{here} cites {coverage.get('kind')!r} coverage; a cohort statistic must cite "
                        "its own outcome coverage, never identity or event coverage"
                    )
            assert_rates_carry_coverage(value, path=here)
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            assert_rates_carry_coverage(value, path=f"{path}[{index}]")


def monthly_and_pooled(
    per_row: Sequence[tuple[str, bool]],
    *,
    coverage: Coverage,
    name: str,
) -> dict[str, Any]:
    """Return the monthly rates, their median, AND the pooled rate — or nothing.

    The median of a set of binary rates can flip sign against the pooled rate
    (small months carry the same weight as large ones).  There is no code path
    here that returns one without the other.
    """
    buckets: dict[str, list[bool]] = {}
    for month, hit in per_row:
        buckets.setdefault(month, []).append(hit)
    monthly = [
        {
            "month": month,
            "hits": sum(1 for hit in values if hit),
            "graded": len(values),
            "hit_rate": (sum(1 for hit in values if hit) / len(values)) if values else None,
            "coverage": coverage.to_payload(),
        }
        for month, values in sorted(buckets.items())
    ]
    rates = [entry["hit_rate"] for entry in monthly if entry["hit_rate"] is not None]
    pooled = Rate(
        name=name,
        numerator=sum(1 for _month, hit in per_row if hit),
        denominator=len(per_row),
        coverage=coverage,
    )
    return {
        "monthly": monthly,
        "median_of_monthly_hit_rate": _median(rates) if rates else None,
        "pooled_hit_rate": pooled.to_payload(),
        "months": len(monthly),
        "coverage": coverage.to_payload(),
        "note": (
            "the median of monthly binary rates can flip sign against the pooled rate; "
            "both are emitted together or neither is"
        ),
    }


# ---------------------------------------------------------------------------
# grading one row
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RowGrade:
    row_id: str
    candidate_id: str
    ticker: str
    horizon: str
    state: str  # "graded" | "ungraded"
    ungraded_reason: str | None
    entry_session: date | None
    exit_session: date | None
    entry_month: str | None
    absolute_return: float | None
    market_relative_return: float | None
    sector_relative_return: float | None
    hit: bool | None
    max_drawdown: float | None
    read_window_sessions: int
    read_window_sha256: str | None
    price_basis: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "candidate_id": self.candidate_id,
            "ticker": self.ticker,
            "horizon": self.horizon,
            "state": self.state,
            "ungraded_reason": self.ungraded_reason,
            "entry_session": self.entry_session.isoformat() if self.entry_session else None,
            "exit_session": self.exit_session.isoformat() if self.exit_session else None,
            "entry_month": self.entry_month,
            "absolute_return": self.absolute_return,
            "market_relative_return": self.market_relative_return,
            "sector_relative_return": self.sector_relative_return,
            "hit": self.hit,
            "max_drawdown": self.max_drawdown,
            "read_window_sessions": self.read_window_sessions,
            "read_window_sha256": self.read_window_sha256,
            "price_basis": self.price_basis,
        }


def _ungraded(row: Mapping[str, Any], horizon_name: str, reason: str, basis: Mapping[str, Any]) -> RowGrade:
    if reason not in UNGRADED_REASONS:
        raise GraderError(f"unnamed ungraded reason: {reason!r}")
    return RowGrade(
        row_id=str(row["row_id"]),
        candidate_id=str(row["candidate_id"]),
        ticker=str(row["ticker"]),
        horizon=horizon_name,
        state="ungraded",
        ungraded_reason=reason,
        entry_session=None,
        exit_session=None,
        entry_month=None,
        absolute_return=None,
        market_relative_return=None,
        sector_relative_return=None,
        hit=None,
        max_drawdown=None,
        read_window_sessions=0,
        read_window_sha256=None,
        price_basis=dict(basis),
    )


def _read_window(
    panel: PricePanel,
    symbol: str,
    sessions: Sequence[date],
) -> tuple[list[float], list[tuple[str, str, float]]] | None:
    """The ONLY price accessor grading uses.

    It reads exactly the sessions handed to it and returns the consumed
    (symbol, session, close) triples so the caller can hash the window.  A grade
    whose ``read_window_sha256`` is unchanged provably consumed no other bar.

    ORDER IS PART OF THE EVIDENCE.  The triples are returned in read order and
    hashed in read order: hashing ``sorted(consumed)`` made the digest
    permutation-invariant, so swapping the entry and exit bars — which inverts
    the sign of every return — left the hash byte-identical and the audit
    question "did this grade read the window the right way round?" unanswerable.
    """
    closes: list[float] = []
    consumed: list[tuple[str, str, float]] = []
    for session in sessions:
        value = panel.close(symbol, session)
        if value is None:
            return None
        closes.append(value)
        consumed.append((symbol, session.isoformat(), value))
    return closes, consumed


def grade_row(
    row: Mapping[str, Any],
    horizon_name: str,
    *,
    panel: PricePanel,
    calendar: SessionCalendar,
    as_of: datetime,
) -> RowGrade:
    """Grade ONE issuance row at ONE horizon, reading only its own window.

    Leakage control.  Entry is the first session STRICTLY AFTER the UTC date of
    ``known_at`` — the row is never filled on the session during which it became
    knowable.  Exit is ``entry_index + horizon_sessions`` steps along the
    explicit calendar.  Every price read goes through :func:`_read_window` over
    ``[entry_session, exit_session]``; nothing outside that closed window is ever
    consulted, and ``read_window_sha256`` proves it.
    """
    validate_issuance_row(row, label="graded row")
    entry_rule = row.get("entry_rule") or {}
    basis = dict(entry_rule.get("price_basis") or {})
    if row["row_kind"] == "retraction":
        return _ungraded(row, horizon_name, "retracted", basis)

    frozen = {entry["name"]: entry for entry in row["horizons"]}
    horizon = frozen.get(horizon_name)
    if horizon is None:
        raise GraderError(f"row {row['row_id']} did not freeze horizon {horizon_name!r} at issuance")
    if entry_rule.get("calendar_id") != calendar.calendar_id:
        raise GraderError("grading calendar does not match the calendar frozen at issuance")
    if basis.get("adjustment") != panel.basis.adjustment or basis.get("field") != panel.basis.field:
        raise GraderError(
            "price panel basis differs from the basis pinned at issuance; "
            "regrade against the registered basis or file the drift"
        )
    graded_basis = panel.basis.to_payload()

    known_at = _instant(row["known_at"])
    if known_at is None:  # pragma: no cover - validation already refuses this
        return _ungraded(row, horizon_name, "entry_session_unavailable", graded_basis)
    entry_index = calendar.first_index_after(known_at.date())
    if entry_index is None:
        return _ungraded(row, horizon_name, "entry_session_unavailable", graded_basis)
    entry_session = calendar.sessions[entry_index]
    as_of_day = as_of.astimezone(timezone.utc).date()
    if entry_session > as_of_day:
        return _ungraded(row, horizon_name, "entry_session_unavailable", graded_basis)

    exit_index = _horizon_exit_index(entry_index, int(horizon["sessions"]))
    exit_session = calendar.session(exit_index)
    if exit_session is None or exit_session > as_of_day:
        return _ungraded(row, horizon_name, "horizon_not_matured", graded_basis)

    window = calendar.sessions[entry_index : exit_index + 1]
    if len(window) != int(horizon["sessions"]) + 1:
        # Belt-and-braces on the horizon arithmetic: a window that is not exactly
        # the frozen length is not the registered horizon, so it does not get a
        # number.  The no-leakage suite reaches this branch by mutation.
        return _ungraded(row, horizon_name, "calendar_gap", graded_basis)

    name_read = _read_window(panel, str(row["ticker"]), window)
    if name_read is None:
        return _ungraded(row, horizon_name, "price_missing", graded_basis)
    market_read = _read_window(panel, str(entry_rule["market_benchmark"]), (window[0], window[-1]))
    sector_read = _read_window(panel, str(entry_rule["sector_benchmark"]), (window[0], window[-1]))
    if market_read is None or sector_read is None:
        return _ungraded(row, horizon_name, "benchmark_missing", graded_basis)

    closes, consumed = name_read
    consumed = consumed + market_read[1] + sector_read[1]
    entry_close, exit_close = closes[0], closes[-1]
    absolute = exit_close / entry_close - 1.0
    market = market_read[0][-1] / market_read[0][0] - 1.0
    sector = sector_read[0][-1] / sector_read[0][0] - 1.0
    drawdown = min(close / entry_close - 1.0 for close in closes)

    return RowGrade(
        row_id=str(row["row_id"]),
        candidate_id=str(row["candidate_id"]),
        ticker=str(row["ticker"]),
        horizon=horizon_name,
        state="graded",
        ungraded_reason=None,
        entry_session=entry_session,
        exit_session=exit_session,
        entry_month=_month_key(entry_session),
        absolute_return=absolute,
        market_relative_return=absolute - market,
        sector_relative_return=absolute - sector,
        hit=(absolute - market) > 0,
        max_drawdown=drawdown,
        read_window_sessions=len(window),
        read_window_sha256=sha256(canonical_bytes(consumed)).hexdigest(),
        price_basis=graded_basis,
    )


def grade_placebo_row(
    row: Mapping[str, Any],
    horizon_name: str,
    *,
    panel: PricePanel,
    calendar: SessionCalendar,
    family: PreregisteredFamily,
) -> RowGrade:
    """The naive baseline: the same name, same horizon, shifted BACKWARD.

    ``placebo_offset_sessions`` is negative and registered, so the placebo window
    lies entirely BEFORE issuance and cannot borrow the future.  It answers the
    only question a bare hit rate cannot: does this name drift up anyway?

    It carries the SAME two refusals as :func:`grade_row` — foreign calendar and
    mismatched price basis.  A baseline computed on a different calendar or a
    different price adjustment than the cohort it is subtracted from is not a
    baseline, and the placebo delta is a verdict input, so a refusal on one side
    and silence on the other is a hole in the kill condition itself.
    """
    validate_issuance_row(row, label="placebo row")
    entry_rule = row.get("entry_rule") or {}
    basis = dict(entry_rule.get("price_basis") or {})
    if entry_rule.get("calendar_id") != calendar.calendar_id:
        raise GraderError("placebo calendar does not match the calendar frozen at issuance")
    if basis.get("adjustment") != panel.basis.adjustment or basis.get("field") != panel.basis.field:
        raise GraderError(
            "placebo price panel basis differs from the basis pinned at issuance; "
            "regrade against the registered basis or file the drift"
        )
    if row["row_kind"] == "retraction":
        return _ungraded(row, horizon_name, "retracted", basis)
    frozen = {entry["name"]: entry for entry in row["horizons"]}
    horizon = frozen.get(horizon_name)
    if horizon is None:
        raise GraderError(f"row {row['row_id']} did not freeze horizon {horizon_name!r} at issuance")
    known_at = _instant(row["known_at"])
    entry_index = calendar.first_index_after(known_at.date()) if known_at else None
    if entry_index is None:
        return _ungraded(row, horizon_name, "entry_session_unavailable", panel.basis.to_payload())
    placebo_entry = entry_index + family.placebo_offset_sessions
    placebo_exit = _horizon_exit_index(placebo_entry, int(horizon["sessions"]))
    if placebo_entry < 0 or placebo_exit >= entry_index:
        return _ungraded(row, horizon_name, "horizon_not_matured", panel.basis.to_payload())
    window = calendar.sessions[placebo_entry : placebo_exit + 1]
    name_read = _read_window(panel, str(row["ticker"]), window)
    if name_read is None:
        return _ungraded(row, horizon_name, "price_missing", panel.basis.to_payload())
    market_read = _read_window(panel, str(entry_rule["market_benchmark"]), (window[0], window[-1]))
    sector_read = _read_window(panel, str(entry_rule["sector_benchmark"]), (window[0], window[-1]))
    if market_read is None or sector_read is None:
        return _ungraded(row, horizon_name, "benchmark_missing", panel.basis.to_payload())
    closes, consumed = name_read
    consumed = consumed + market_read[1] + sector_read[1]
    absolute = closes[-1] / closes[0] - 1.0
    market = market_read[0][-1] / market_read[0][0] - 1.0
    sector = sector_read[0][-1] / sector_read[0][0] - 1.0
    return RowGrade(
        row_id=str(row["row_id"]),
        candidate_id=str(row["candidate_id"]),
        ticker=str(row["ticker"]),
        horizon=horizon_name,
        state="graded",
        ungraded_reason=None,
        entry_session=window[0],
        exit_session=window[-1],
        entry_month=_month_key(window[0]),
        absolute_return=absolute,
        market_relative_return=absolute - market,
        sector_relative_return=absolute - sector,
        hit=(absolute - market) > 0,
        max_drawdown=min(close / closes[0] - 1.0 for close in closes),
        read_window_sessions=len(window),
        read_window_sha256=sha256(canonical_bytes(consumed)).hexdigest(),
        price_basis=panel.basis.to_payload(),
    )


# ---------------------------------------------------------------------------
# disclosure labels — earnings windows and subsequent filings
# ---------------------------------------------------------------------------
#
# The handoff asks for "earnings-window and subsequent-filings outcome labels
# where available".  Those three words carry the whole design.
#
# WHAT THE LABEL IS FOR.  A graded horizon may span an earnings print or a
# subsequent periodic filing, and if it does, the return it produced is not
# cleanly attributable to the award action the family issued on.  The label
# records that fact so a reader can partition the cohort after the fact.  It is
# a CONTAMINATION marker, not an outcome and not a signal.
#
# WHY IT IS STRUCTURALLY OUTSIDE THE VERDICT.  §7.2 of the registration derives
# N = 545 from a power calculation over the paired market-relative mean.  Adding
# a term to the decision rule would invalidate that N while leaving the
# registered number in the document — the "registered N is the N the threshold
# needs" trap, inverted.  So the labels are computed AFTER ``evaluate_verdict``
# has already returned and are attached to the report beside the verdict, never
# inside its inputs.  ``build_cohort_report`` enforces the ordering and
# ``test_disclosure_labels_cannot_reach_the_verdict`` pins it by comparing the
# verdict block of a report built with a calendar against one built without.
#
# WHY "unavailable" AND "none_in_window" ARE DIFFERENT STATES.  This is the
# whole reason the class exists rather than a bare integer.  "We looked and no
# earnings fell in this window" is evidence.  "We have no earnings calendar for
# this issuer" is the absence of evidence.  Collapsing them — the natural
# implementation, a ``defaultdict(list)`` returning ``[]`` for an unknown ticker
# — silently converts every uncovered issuer into a clean, contamination-free
# row and flatters the cohort exactly where coverage is worst.  A calendar
# therefore declares the tickers it COVERS, and a ticker outside that set is
# ``unavailable`` with a named reason, never ``none_in_window``.

#: Kinds of disclosure a window may span.  ``filing`` is the "subsequent
#: filings" half of the handoff line: a periodic or current report published
#: after issuance and inside the frozen window.
DISCLOSURE_KINDS = ("earnings", "filing")

#: A label is either computed (and then says what it found) or it is not
#: computed (and then says why).  There is no fourth state and no default.
DISCLOSURE_LABEL_STATES = ("observed", "none_in_window", "unavailable")

#: Every reason a disclosure label may be absent.  Mirrors ``UNGRADED_REASONS``
#: in spirit: a row is never silently dropped from the label census, so the
#: three counts always sum to the cohort.
DISCLOSURE_UNAVAILABLE_REASONS = (
    "no_disclosure_calendar",
    "issuer_not_in_calendar",
    "row_ungraded",
    "source_outage",
)


@dataclass(frozen=True)
class DisclosureEvent:
    """One earnings print or filing, with its OWN availability clock.

    ``known_at`` is when this pipeline could first know the disclosure happened,
    and it is a separate clock from ``event_date``.  Filing indexes are
    published on a lag, so a label computed from an event whose ``known_at`` is
    in the future would be reading tomorrow's index to describe today's window —
    the same leak ``grade_row`` prevents on the price side.
    """

    kind: str
    ticker: str
    event_date: date
    known_at: str
    reference: str

    def __post_init__(self) -> None:
        if self.kind not in DISCLOSURE_KINDS:
            raise GraderError(f"disclosure kind must be one of {DISCLOSURE_KINDS}")
        if _text(self.ticker) is None:
            raise GraderError("disclosure event needs a ticker")
        if _text(self.reference) is None:
            raise GraderError("disclosure event needs a source reference")
        if isinstance(self.event_date, datetime) or not isinstance(self.event_date, date):
            raise GraderError("disclosure event_date must be a date, not a datetime")
        if _instant(self.known_at) is None:
            raise GraderError("disclosure event known_at must be an instant")

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "ticker": self.ticker,
            "event_date": self.event_date.isoformat(),
            "known_at": self.known_at,
            "reference": self.reference,
        }


@dataclass(frozen=True)
class DisclosureCalendar:
    """Earnings and filing dates, plus the tickers it CLAIMS to cover.

    ``covered_tickers`` is the load-bearing field.  Without it an empty event
    list is ambiguous between "no disclosures" and "no data", and the ambiguity
    resolves in the flattering direction by default.
    """

    calendar_id: str
    events: tuple[DisclosureEvent, ...]
    covered_tickers: frozenset[str]
    outage_tickers: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if _text(self.calendar_id) is None:
            raise GraderError("disclosure calendar needs a calendar_id")
        for event in self.events:
            if not isinstance(event, DisclosureEvent):
                raise GraderError("disclosure calendar takes DisclosureEvent objects")
            if event.ticker not in self.covered_tickers:
                raise GraderError(
                    f"disclosure calendar carries an event for {event.ticker!r} but does not "
                    "declare it covered; a calendar cannot know an event for an issuer it "
                    "does not cover"
                )
        overlap = self.covered_tickers & self.outage_tickers
        if overlap:
            raise GraderError(
                f"tickers {sorted(overlap)!r} are both covered and in outage; a ticker is one "
                "or the other, and the difference is exactly what the label reports"
            )

    @classmethod
    def build(
        cls,
        events: Iterable[DisclosureEvent],
        *,
        calendar_id: str,
        covered_tickers: Iterable[str],
        outage_tickers: Iterable[str] = (),
    ) -> "DisclosureCalendar":
        return cls(
            calendar_id=str(calendar_id),
            events=tuple(events),
            covered_tickers=frozenset(str(value) for value in covered_tickers),
            outage_tickers=frozenset(str(value) for value in outage_tickers),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "calendar_id": self.calendar_id,
            "event_count": len(self.events),
            "covered_ticker_count": len(self.covered_tickers),
            "outage_ticker_count": len(self.outage_tickers),
        }


@dataclass(frozen=True)
class DisclosureLabel:
    row_id: str
    candidate_id: str
    ticker: str
    horizon: str
    state: str
    unavailable_reason: str | None
    earnings_in_window: int | None
    filings_in_window: int | None
    events: tuple[dict[str, Any], ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "candidate_id": self.candidate_id,
            "ticker": self.ticker,
            "horizon": self.horizon,
            "state": self.state,
            "unavailable_reason": self.unavailable_reason,
            "earnings_in_window": self.earnings_in_window,
            "filings_in_window": self.filings_in_window,
            "events": [dict(event) for event in self.events],
        }


def _disclosure_window(grade: RowGrade) -> tuple[date, date] | None:
    """The ONLY place the label's window is computed.

    Deliberately a module-level seam, exactly like ``_horizon_exit_index``: the
    no-leakage suite monkeypatches it to run one session past the graded exit
    and asserts a label CHANGES, which is what proves the window assertion is
    not vacuous.  The window is the graded window and nothing else — a label is
    a statement about the return that was actually measured.
    """
    if grade.entry_session is None or grade.exit_session is None:
        return None
    return grade.entry_session, grade.exit_session


def label_disclosures(
    grade: RowGrade,
    *,
    disclosure: DisclosureCalendar | None,
    as_of: datetime,
) -> DisclosureLabel:
    """Label ONE graded row with the disclosures its own window spanned.

    Two clamps, both mutation-proved in the suite:

    1. **Window clamp** — only events inside ``[entry_session, exit_session]``
       count.  A disclosure after the exit did not touch the measured return.
    2. **Availability clamp** — only events whose ``known_at`` is at or before
       ``as_of`` count.  An index that has not published yet cannot describe a
       window that has already been graded.

    A row the grader could not grade has no window, so it has no label: it is
    ``unavailable`` with reason ``row_ungraded`` rather than being dropped.
    """
    base = dict(
        row_id=grade.row_id,
        candidate_id=grade.candidate_id,
        ticker=grade.ticker,
        horizon=grade.horizon,
    )

    def _unavailable(reason: str) -> DisclosureLabel:
        if reason not in DISCLOSURE_UNAVAILABLE_REASONS:
            raise GraderError(f"unnamed disclosure-unavailable reason: {reason!r}")
        return DisclosureLabel(
            state="unavailable",
            unavailable_reason=reason,
            earnings_in_window=None,
            filings_in_window=None,
            events=(),
            **base,
        )

    if disclosure is None:
        return _unavailable("no_disclosure_calendar")
    if grade.state != "graded":
        return _unavailable("row_ungraded")
    window = _disclosure_window(grade)
    if window is None:  # pragma: no cover - a graded row always carries both sessions
        return _unavailable("row_ungraded")
    if grade.ticker in disclosure.outage_tickers:
        return _unavailable("source_outage")
    if grade.ticker not in disclosure.covered_tickers:
        return _unavailable("issuer_not_in_calendar")

    start, end = window
    horizon_as_of = as_of.astimezone(timezone.utc)
    matched: list[dict[str, Any]] = []
    for event in disclosure.events:
        if event.ticker != grade.ticker:
            continue
        if event.event_date < start or event.event_date > end:
            continue
        available = _instant(event.known_at)
        if available is None or available > horizon_as_of:
            continue
        matched.append(event.to_payload())

    matched.sort(key=lambda item: (item["event_date"], item["kind"], item["reference"]))
    earnings = sum(1 for item in matched if item["kind"] == "earnings")
    filings = sum(1 for item in matched if item["kind"] == "filing")
    return DisclosureLabel(
        state="observed" if matched else "none_in_window",
        unavailable_reason=None,
        earnings_in_window=earnings,
        filings_in_window=filings,
        events=tuple(matched),
        **base,
    )


def disclosure_label_block(
    labels: Sequence[DisclosureLabel],
    *,
    family: PreregisteredFamily,
    horizon_name: str,
    issued_n: int,
    disclosure: DisclosureCalendar | None,
) -> dict[str, Any]:
    """The report block for one horizon's labels.

    The denominator of both rates is the number of rows whose label could be
    COMPUTED, and the coverage beside them carries the fixed issuance cohort as
    its universe — so a family with poor filing coverage reads as poor coverage,
    never as a clean cohort.
    """
    counts = {state: 0 for state in DISCLOSURE_LABEL_STATES}
    reasons: dict[str, int] = {}
    for label in labels:
        counts[label.state] = counts.get(label.state, 0) + 1
        if label.state == "unavailable":
            key = str(label.unavailable_reason)
            reasons[key] = reasons.get(key, 0) + 1

    computable = counts["observed"] + counts["none_in_window"]
    coverage = Coverage(
        kind="outcome",
        scope=(
            f"rows whose disclosure label was computable for {family.family_id} at "
            f"{horizon_name}; universe is the fixed issuance cohort, uncovered issuers "
            "are unavailable and never counted as clean"
        ),
        observed=computable,
        universe=issued_n,
        status="complete" if computable == issued_n else "partial",
    )
    return {
        "calendar": disclosure.to_payload() if disclosure is not None else None,
        "counts": counts,
        "unavailable_reasons": reasons,
        "earnings_window_rate": Rate(
            name=f"{family.family_id}.{horizon_name}.earnings_window_rate",
            numerator=sum(1 for label in labels if (label.earnings_in_window or 0) > 0),
            denominator=computable,
            coverage=coverage,
        ).to_payload(),
        "filing_window_rate": Rate(
            name=f"{family.family_id}.{horizon_name}.filing_window_rate",
            numerator=sum(1 for label in labels if (label.filings_in_window or 0) > 0),
            denominator=computable,
            coverage=coverage,
        ).to_payload(),
        "labels": [label.to_payload() for label in labels],
        "note": (
            "Descriptive contamination markers, computed AFTER the verdict and never an input "
            "to it: the registered power calculation is over the paired market-relative mean, "
            "and adding a term to the decision rule would invalidate the registered N. "
            "'none_in_window' means the calendar covered this issuer and found nothing; "
            "'unavailable' means it could not look. They are never merged."
        ),
    }


def regrade_diff(
    previous: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Rows whose graded value moved between two price vintages.

    Historical closes are re-adjusted in place upstream, so a stored grade can
    stop reproducing without anybody editing the grader.  This surfaces those
    rows instead of letting a silent overwrite rewrite a track record.
    """
    index = {(row.get("row_id"), row.get("horizon")): row for row in previous}
    drifted: list[dict[str, Any]] = []
    for row in current:
        key = (row.get("row_id"), row.get("horizon"))
        prior = index.get(key)
        if prior is None:
            continue
        if prior.get("read_window_sha256") == row.get("read_window_sha256"):
            continue
        drifted.append(
            {
                "row_id": row.get("row_id"),
                "horizon": row.get("horizon"),
                "prior_price_basis": prior.get("price_basis"),
                "current_price_basis": row.get("price_basis"),
                "prior_market_relative_return": prior.get("market_relative_return"),
                "current_market_relative_return": row.get("market_relative_return"),
                "prior_read_window_sha256": prior.get("read_window_sha256"),
                "current_read_window_sha256": row.get("read_window_sha256"),
            }
        )
    return drifted


# ---------------------------------------------------------------------------
# cohort report
# ---------------------------------------------------------------------------


def _bootstrap_seed(family: PreregisteredFamily, label: str) -> int:
    """A deterministic per-statistic seed, so a report reproduces exactly.

    The seed is registered (``bootstrap_seed``) and mixed with the statistic's
    label, so two different statistics do not share a resample stream and the
    same statistic reproduces bit-for-bit on a re-run.  A bootstrap whose
    interval moves between two runs of the same data is not evidence.
    """
    material = f"{family.family_id}:{family.bootstrap_seed}:{label}".encode("utf-8")
    return int(sha256(material).hexdigest()[:12], 16)


def _bootstrap_mean_ci(
    values: Sequence[float],
    *,
    family: PreregisteredFamily,
    label: str,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap interval for a mean — the only interval emitted.

    Nonparametric on purpose: single-name horizon returns are fat-tailed and
    skewed, so a normal-theory interval understates the tail exactly where a
    verdict would be decided.  ``n == 1`` returns a degenerate interval equal to
    the point value rather than ``None``; that is honest (one observation has no
    sampling spread to report) and it keeps the reachability fixtures from
    silently skipping the interval requirement.
    """
    if not values:
        return None, None
    if len(values) == 1:
        return float(values[0]), float(values[0])
    resamples = int(family.bootstrap_resamples)
    rng = random.Random(_bootstrap_seed(family, label))
    n = len(values)
    pool = list(values)
    means = [sum(rng.choices(pool, k=n)) / n for _ in range(resamples)]
    means.sort()
    alpha = (1.0 - float(family.confidence_level)) / 2.0
    low_index = min(resamples - 1, max(0, int(math.floor(alpha * resamples))))
    high_index = min(resamples - 1, max(0, int(math.ceil((1.0 - alpha) * resamples)) - 1))
    return means[low_index], means[high_index]


def _summary(
    values: Sequence[float],
    *,
    coverage: Coverage,
    family: PreregisteredFamily,
    label: str,
) -> dict[str, Any]:
    """n / mean / median / min / max — AND the spread the verdict needs.

    The prior version emitted five numbers with no dispersion at all, and §7's
    thresholds were compared against the bare mean.  At the old gate floor that
    made a preregistered KILL fire on noise roughly a quarter to two-fifths of
    the time under a true null, and roughly a sixth to a quarter of the time
    against a genuine +3pp edge.  An interval is not decoration here; it is the
    difference between a measurement and a coin flip.
    """
    payload: dict[str, Any] = {
        "n": len(values),
        "mean": None,
        "median": None,
        "min": None,
        "max": None,
        "sd": None,
        "standard_error": None,
        "ci_lower": None,
        "ci_upper": None,
        "ci_level": float(family.confidence_level),
        "ci_method": "percentile_bootstrap",
        "ci_resamples": int(family.bootstrap_resamples),
        "coverage": coverage.to_payload(),
    }
    if not values:
        return payload
    ordered = [float(value) for value in values]
    sd = _stdev(ordered) if len(ordered) > 1 else 0.0
    lower, upper = _bootstrap_mean_ci(ordered, family=family, label=label)
    payload.update(
        {
            "mean": sum(ordered) / len(ordered),
            "median": _median(ordered),
            "min": min(ordered),
            "max": max(ordered),
            "sd": sd,
            "standard_error": sd / math.sqrt(len(ordered)),
            "ci_lower": lower,
            "ci_upper": upper,
        }
    )
    return payload


def _rate_ci(
    hits: int,
    graded: int,
    *,
    family: PreregisteredFamily,
    label: str,
) -> tuple[float | None, float | None]:
    """Bootstrap interval for a conditional hit rate, same machinery as a mean."""
    if graded <= 0:
        return None, None
    return _bootstrap_mean_ci(
        [1.0] * hits + [0.0] * (graded - hits), family=family, label=label
    )


def maturity_gate(
    rows: Sequence[Mapping[str, Any]],
    *,
    family: PreregisteredFamily,
    outcome_coverage: Coverage,
    calendar: SessionCalendar,
) -> dict[str, Any]:
    """The N-gate, counted on things a cadence change cannot manufacture.

    Row count alone is not a gate: re-observing one event nightly would satisfy
    it without a single new event.  Distinct source events, distinct issuers, and
    distinct event months are the counters that require the world to supply
    something new.

    THE EVENT CLOCK IS NOT THE ENTRY CLOCK, and conflating them reopened the
    exact trap this gate closes.  Counting months off ``effective_at`` (falling
    back to ``known_at``) let ONE backfill night satisfy the gate: 40 rows, 40
    distinct ``event_id``, 12 issuers, ``effective_at`` spanning 12 historical
    months — and a single shared ``known_at``.  Every one of those rows then has
    the same entry session and the same market window: 40 rows, ONE independent
    draw.  The gate therefore counts BOTH clocks, plus the number of distinct
    entry sessions, which is the count of genuinely independent market windows
    the cohort actually contains.
    """
    events = {
        str((row.get("source_event") or {}).get("event_id"))
        for row in rows
        if isinstance(row.get("source_event"), Mapping)
    }
    issuers = {str(row.get("issuer_company_id") or row.get("ticker")) for row in rows}
    event_months: set[str] = set()
    known_at_months: set[str] = set()
    entry_sessions: set[date] = set()
    for row in rows:
        effective = _instant(row.get("effective_at")) or _instant(row.get("known_at"))
        if effective is not None:
            event_months.add(_month_key(effective.date()))
        known_at = _instant(row.get("known_at"))
        if known_at is None:
            continue
        known_at_months.add(_month_key(known_at.date()))
        entry_index = calendar.first_index_after(known_at.date())
        if entry_index is not None:
            entry_sessions.add(calendar.sessions[entry_index])
    coverage_fraction = outcome_coverage.fraction
    observed = {
        "issued": len(rows),
        "distinct_source_events": len(events),
        "distinct_issuers": len(issuers),
        "distinct_event_months": len(event_months),
        "distinct_known_at_months": len(known_at_months),
        "distinct_entry_sessions": len(entry_sessions),
        "outcome_coverage_fraction": coverage_fraction,
    }
    satisfied = (
        len(events) >= family.min_distinct_source_events
        and len(issuers) >= family.min_distinct_issuers
        and len(event_months) >= family.min_distinct_event_months
        and len(known_at_months) >= family.min_distinct_known_at_months
        and len(entry_sessions) >= family.min_distinct_entry_sessions
        and coverage_fraction is not None
        and coverage_fraction >= family.min_outcome_coverage
    )
    return {
        "satisfied": bool(satisfied),
        "required": {
            "min_distinct_source_events": family.min_distinct_source_events,
            "min_distinct_issuers": family.min_distinct_issuers,
            "min_distinct_event_months": family.min_distinct_event_months,
            "min_distinct_known_at_months": family.min_distinct_known_at_months,
            "min_distinct_entry_sessions": family.min_distinct_entry_sessions,
            "min_outcome_coverage": family.min_outcome_coverage,
        },
        "observed": observed,
        "note": (
            "issued counts DISTINCT source events, not issuance rows: a change in "
            "issuance cadence must not be able to satisfy this gate. The event clock "
            "(effective_at) and the entry clock (known_at) are counted separately, and "
            "distinct entry sessions is the count of independent market windows: one "
            "backfill night can spread effective_at over a year while every row shares "
            "one known_at, one entry session, and one draw"
        ),
    }


VERDICT_STATES = ("accruing", "expired_unmeasurable", "kill", "tested_null", "supported")

#: Named reasons a satisfied gate still produces no verdict.  A blocked verdict
#: is ``accruing`` with the reason printed — never a softer decided state, which
#: would be the escape hatch B1 describes.
VERDICT_BLOCKED_REASONS = (
    "verdict_basis_coverage_below_registered_floor",
    "verdict_inputs_unavailable",
)


def evaluate_verdict(
    per_horizon: Mapping[str, Any],
    *,
    family: PreregisteredFamily,
    as_of: datetime,
    latched_verdict: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply the registered kill condition — the reason this instrument exists.

    A kill condition no code path can emit is a detector with an unsatisfiable
    precondition: it returns a clean null forever and reads as working.  So is a
    SUPPORTED condition no plausible signal can reach — the prior rule required
    ``hits/issued > 0.50`` over the FIXED cohort, which at the registered 0.70
    coverage floor demanded a conditional h63 hit rate above 71.4%.  Both
    branches must be reachable or the instrument only has one answer.

    Three exhaustive regions, each testing an INTERVAL against a registered
    threshold rather than comparing a point estimate to zero:

    * **KILL** — the interval rules the minimum interesting effect OUT, both
      absolutely and against the family's own placebo.
    * **SUPPORTED** — the interval rules it IN, and the hit rate clears its
      floor with its own interval.
    * **TESTED-NULL** — everything else: measured, and neither ruled out nor
      supported at the registered power.  There is no fall-through region with a
      label that contradicts its own numbers.

    Two protections against optional stopping and post-hoc ungrading:
    ``latched_verdict`` implements §7's "evaluate H1 ONCE" (a decided verdict is
    reported forever, with any later recomputation printed beside it, never in
    place of it), and the verdict refuses to fire at all when the verdict-basis
    coverage is below the registered floor.

    It decides nothing.  The state is display context for an operator ruling and
    confers no authority in any branch, including ``supported``.
    """
    block = per_horizon.get(family.primary_horizon)
    if not isinstance(block, Mapping):
        raise GraderError(f"the primary horizon {family.primary_horizon!r} was not graded")
    gate = block["gate"]
    basis = block["verdict_basis"]
    mean_block = basis["market_relative_return_summary"]
    delta_block = basis["paired_placebo_delta_summary"]
    hit_block = basis["conditional_hit_rate"]
    inputs = {
        "pooled_market_relative_mean": mean_block["mean"],
        "pooled_market_relative_mean_ci_lower": mean_block["ci_lower"],
        "pooled_market_relative_mean_ci_upper": mean_block["ci_upper"],
        "placebo_delta_market_relative_mean": delta_block["mean"],
        "placebo_delta_market_relative_mean_ci_lower": delta_block["ci_lower"],
        "placebo_delta_market_relative_mean_ci_upper": delta_block["ci_upper"],
        "conditional_hit_rate": hit_block["value"],
        "conditional_hit_rate_ci_lower": hit_block["ci_lower"],
        "hit_rate_lower_bound": block["hit_rate_bounds"]["lower_bound_hit_rate"]["value"],
        "hit_rate_upper_bound": block["hit_rate_bounds"]["upper_bound_hit_rate"]["value"],
        "verdict_basis_coverage_fraction": basis["coverage"]["fraction"],
        "coverage": block["coverage"],
    }
    thresholds = {
        "minimum_interesting_effect": family.minimum_interesting_effect,
        "hit_rate_floor": family.hit_rate_floor,
        "confidence_level": family.confidence_level,
        "min_verdict_outcome_coverage": family.min_verdict_outcome_coverage,
    }
    expiry = date.fromisoformat(family.accrual_expiry_date)

    def finish(state: str, blocked: str | None = None) -> dict[str, Any]:
        return _verdict(
            state,
            family,
            gate,
            inputs,
            thresholds,
            blocked_reason=blocked,
            latched_verdict=latched_verdict,
        )

    if not gate["satisfied"]:
        # The gate is not an alibi: past the registered expiry, an unmet gate is
        # itself the finding — the family cannot be measured at this issuance rate.
        state = "expired_unmeasurable" if as_of.astimezone(timezone.utc).date() > expiry else "accruing"
        return finish(state)

    basis_coverage = inputs["verdict_basis_coverage_fraction"]
    if basis_coverage is None or basis_coverage < family.min_verdict_outcome_coverage:
        # B1's second protection.  Below the registered floor the kill-bearing
        # mean is a resolution-conditioned statistic, and a resolution-conditioned
        # statistic deletes whichever rows failed to resolve.  No verdict fires —
        # not a softer one, none.
        return finish("accruing", "verdict_basis_coverage_below_registered_floor")

    mean_low = inputs["pooled_market_relative_mean_ci_lower"]
    mean_high = inputs["pooled_market_relative_mean_ci_upper"]
    delta_low = inputs["placebo_delta_market_relative_mean_ci_lower"]
    delta_high = inputs["placebo_delta_market_relative_mean_ci_upper"]
    hit_low = inputs["conditional_hit_rate_ci_lower"]
    if None in (mean_low, mean_high, delta_low, delta_high):
        return finish("accruing", "verdict_inputs_unavailable")

    effect = family.minimum_interesting_effect
    if mean_high < effect and delta_high < effect:
        return finish("kill")
    if (
        mean_low > 0.0
        and delta_low > effect
        and hit_low is not None
        and hit_low > family.hit_rate_floor
    ):
        return finish("supported")
    return finish("tested_null")


_VERDICT_MEANING = {
    "accruing": (
        "no verdict is available and none is implied: either the maturity gate is not met, or "
        "the verdict-basis coverage is below the registered floor"
    ),
    "expired_unmeasurable": (
        "the registered accrual expiry passed with the gate unmet: the family is closed as "
        "unmeasurable at this issuance rate"
    ),
    "kill": (
        "the interval rules the registered minimum interesting effect OUT, both absolutely and "
        "against the family's own placebo; file a construction-scoped kill. The evidence rails, "
        "contract, and display surfaces are not deleted — a null never deletes the layer"
    ),
    "tested_null": (
        "measured, and neither ruled out nor supported at the registered power: the interval "
        "spans the registered minimum interesting effect. Filed as a null, authority unchanged. "
        "This label makes no claim about the sign of the cohort mean — read the printed inputs"
    ),
    "supported": (
        "eligibility to REQUEST the existing gauntlet, and nothing else. This is not a "
        "promotion, not a rank, not a size, and not a recommendation"
    ),
}

_DECIDED_STATES = ("kill", "tested_null", "supported", "expired_unmeasurable")


def _verdict(
    state: str,
    family: PreregisteredFamily,
    gate: Mapping[str, Any],
    inputs: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    *,
    blocked_reason: str | None = None,
    latched_verdict: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if state not in VERDICT_STATES:  # pragma: no cover - closed list
        raise GraderError(f"unknown verdict state {state!r}")
    if blocked_reason is not None and blocked_reason not in VERDICT_BLOCKED_REASONS:
        raise GraderError(f"unnamed verdict blocked reason: {blocked_reason!r}")
    payload = {
        "state": state,
        "recomputed_state": state,
        "latched": False,
        "latched_at": None,
        "verdict_blocked_reason": blocked_reason,
        "kill_condition_id": family.kill_condition_id,
        "primary_horizon": family.primary_horizon,
        "gate_satisfied": bool(gate["satisfied"]),
        "inputs": dict(inputs),
        "thresholds": dict(thresholds),
        "meaning": _VERDICT_MEANING[state],
        "authority_effect": "none in every branch; a ruling is an operator act",
    }
    if latched_verdict is None:
        return payload
    # §7 promises H1 is evaluated ONCE, at the first report where the gate is
    # satisfied. Recomputing every night and reporting the newest answer is
    # optional stopping against a rule that promised one look — and it is the
    # other way a losing cohort walks back a kill. The latched state is the
    # verdict; the live recomputation is printed beside it, never in place of it.
    latched_state = latched_verdict.get("state")
    if latched_state not in _DECIDED_STATES:
        return payload
    payload["state"] = str(latched_state)
    payload["latched"] = True
    payload["latched_at"] = latched_verdict.get("latched_at") or latched_verdict.get("evaluated_at")
    payload["meaning"] = _VERDICT_MEANING[str(latched_state)]
    payload["latch_note"] = (
        "§7 evaluates H1 once, at the first report where the gate is satisfied. This is that "
        "verdict; recomputed_state is tonight's recomputation, reported for drift, not for revision"
    )
    return payload


def _window_independence(
    grades: Sequence[RowGrade],
    *,
    calendar: SessionCalendar,
    horizon_sessions: int,
    coverage: Coverage,
) -> dict[str, Any]:
    """How many INDEPENDENT draws the cohort actually contains.

    ``issued_n`` counts rows.  Two candidates on the same ticker five sessions
    apart produce two h63 windows that overlap on 58 of 63 sessions and are
    counted twice by every rate in this report; the second window carries almost
    no new information about the family.  Nothing here de-duplicates them — the
    denominator is the issuance cohort by §5 and that stays — but the overlap is
    printed beside ``issued_n`` so a reader can see what N really is.
    """
    graded = [grade for grade in grades if grade.state == "graded" and grade.entry_session]
    entries: dict[str, list[int]] = {}
    for grade in graded:
        index = calendar.index_of(grade.entry_session)  # type: ignore[arg-type]
        if index is not None:
            entries.setdefault(grade.ticker, []).append(index)
    overlapping_pairs = 0
    max_overlap = 0
    for indices in entries.values():
        ordered = sorted(indices)
        for position, first in enumerate(ordered):
            for second in ordered[position + 1 :]:
                shared = horizon_sessions + 1 - (second - first)
                if shared > 0:
                    overlapping_pairs += 1
                    max_overlap = max(max_overlap, shared)
    # A conservative independent-draw estimate: greedily keep windows that do not
    # overlap a window already kept, per ticker.
    independent = 0
    for indices in entries.values():
        last_kept: int | None = None
        for index in sorted(indices):
            if last_kept is None or index - last_kept > horizon_sessions:
                independent += 1
                last_kept = index
    return {
        "graded_n": len(graded),
        "distinct_tickers": len(entries),
        "distinct_entry_sessions": len({index for indices in entries.values() for index in indices}),
        "overlapping_window_pairs": overlapping_pairs,
        "max_window_overlap_sessions": max_overlap,
        "non_overlapping_window_estimate": independent,
        "coverage": coverage.to_payload(),
        "note": (
            "issued_n counts rows, not independent draws; two windows on one ticker inside "
            "one horizon share most of their sessions and are counted twice by every rate here"
        ),
    }


def build_cohort_report(
    log: IssuanceLog,
    *,
    family: PreregisteredFamily,
    panel: PricePanel,
    calendar: SessionCalendar,
    as_of: datetime,
    identity_coverage: Coverage,
    event_coverage: Coverage,
    generated_at: str,
    latched_verdict: Mapping[str, Any] | None = None,
    disclosure: "DisclosureCalendar | None" = None,
) -> dict[str, Any]:
    """Grade a cohort and emit the display-tier report.

    ``identity_coverage`` and ``event_coverage`` are REQUIRED arguments and must
    carry their own kinds.  A lobe can have excellent identity coverage and no
    predictive value; publishing an outcome number without the other two beside
    it is the exact conflation the Wave 9G acceptance gates forbid, so it is not
    expressible here.
    """
    if identity_coverage.kind != "identity":
        raise GraderError("identity_coverage must be an identity coverage")
    if event_coverage.kind != "event":
        raise GraderError("event_coverage must be an event coverage")
    if panel.basis.adjustment != family.price_adjustment or panel.basis.field != family.price_field:
        raise GraderError("price panel does not match the registered price basis for this family")

    rows = cohort_rows(log, family_id=family.family_id)
    ancestors = superseded_ancestors(log, family_id=family.family_id)
    abstained = abstention_rows(log, family_id=family.family_id)
    considered = len(rows) + len(abstained)
    admission_coverage = Coverage(
        kind="outcome",
        scope="candidates the family considered, from the append-only issuance log",
        observed=considered,
        universe=considered,
        status="complete" if considered else "empty",
    )
    reasons: dict[str, int] = {}
    for row in abstained:
        reason = str(row.get("abstention_reason"))
        reasons[reason] = reasons.get(reason, 0) + 1

    per_horizon: dict[str, Any] = {}
    # Held aside deliberately.  These are NOT merged into ``per_horizon`` until
    # after ``evaluate_verdict`` has returned, so the verdict provably cannot
    # have read a disclosure label — see the disclosure section's header.
    disclosure_blocks: dict[str, Any] = {}
    for horizon in family.horizons:
        grades = [
            grade_row(row, horizon.name, panel=panel, calendar=calendar, as_of=as_of)
            for row in rows
        ]
        disclosure_blocks[horizon.name] = disclosure_label_block(
            [label_disclosures(grade, disclosure=disclosure, as_of=as_of) for grade in grades],
            family=family,
            horizon_name=horizon.name,
            issued_n=len(rows),
            disclosure=disclosure,
        )
        graded = [grade for grade in grades if grade.state == "graded"]
        ungraded = [grade for grade in grades if grade.state == "ungraded"]
        ungraded_reasons: dict[str, int] = {}
        for grade in ungraded:
            key = str(grade.ungraded_reason)
            ungraded_reasons[key] = ungraded_reasons.get(key, 0) + 1

        outcome_coverage = Coverage(
            kind="outcome",
            scope=(
                f"issuance-time cohort for {family.family_id} at {horizon.name}; "
                "denominator fixed at issuance, ungraded rows retained"
            ),
            observed=len(graded),
            universe=len(rows),
            status="complete" if len(graded) == len(rows) else "partial",
        )
        hits = sum(1 for grade in graded if grade.hit)
        hit_rate = Rate(
            name=f"{family.family_id}.{horizon.name}.hit_rate",
            numerator=hits,
            denominator=len(graded),
            coverage=outcome_coverage,
        )
        # Bounds over the FIXED issuance cohort.  The gap between them is the
        # cost of incomplete resolution, made visible instead of assumed away.
        lower = Rate(
            name=f"{family.family_id}.{horizon.name}.hit_rate_lower_bound",
            numerator=hits,
            denominator=len(rows),
            coverage=outcome_coverage,
        )
        upper = Rate(
            name=f"{family.family_id}.{horizon.name}.hit_rate_upper_bound",
            numerator=hits + len(ungraded),
            denominator=len(rows),
            coverage=outcome_coverage,
        )
        monthly = monthly_and_pooled(
            [(str(grade.entry_month), bool(grade.hit)) for grade in graded],
            coverage=outcome_coverage,
            name=f"{family.family_id}.{horizon.name}.pooled_hit_rate",
        )
        placebo = [
            grade_placebo_row(row, horizon.name, panel=panel, calendar=calendar, family=family)
            for row in rows
        ]
        placebo_graded = [grade for grade in placebo if grade.state == "graded"]
        placebo_coverage = Coverage(
            kind="outcome",
            scope=(
                f"placebo cohort: same names and horizon shifted "
                f"{family.placebo_offset_sessions} sessions, entirely pre-issuance"
            ),
            observed=len(placebo_graded),
            universe=len(rows),
            status="complete" if len(placebo_graded) == len(rows) else "partial",
        )
        market_relative = [float(grade.market_relative_return) for grade in graded]
        placebo_relative = [float(grade.market_relative_return) for grade in placebo_graded]

        # --- the supersession ratchet -------------------------------------
        # A superseding row that cannot be graded does not delete the grade its
        # predecessor already earned. The log keeps every superseded row
        # byte-identical, so the earlier grade is still computable, and §8's
        # promise — "you cannot retract your way out of a loss" — becomes true
        # for the kill-bearing MEAN and not only for the hit-rate bounds.
        # Coverage is deliberately NOT repaired by the ratchet: a retraction
        # still lowers outcome coverage and still widens the bounds. What it
        # cannot do is make a losing number disappear from the verdict.
        retained: list[dict[str, Any]] = []
        basis_real: dict[str, RowGrade] = {}
        basis_placebo: dict[str, RowGrade] = {}
        for row, grade, placebo_grade in zip(rows, grades, placebo):
            candidate_id = str(row["candidate_id"])
            if grade.state == "graded":
                basis_real[candidate_id] = grade
                if placebo_grade.state == "graded":
                    basis_placebo[candidate_id] = placebo_grade
                continue
            for ancestor in reversed(ancestors.get(candidate_id, ())):
                ancestor_grade = grade_row(
                    ancestor, horizon.name, panel=panel, calendar=calendar, as_of=as_of
                )
                if ancestor_grade.state != "graded":
                    continue
                basis_real[candidate_id] = ancestor_grade
                ancestor_placebo = grade_placebo_row(
                    ancestor, horizon.name, panel=panel, calendar=calendar, family=family
                )
                if ancestor_placebo.state == "graded":
                    basis_placebo[candidate_id] = ancestor_placebo
                retained.append(
                    {
                        "candidate_id": candidate_id,
                        "effective_row_id": grade.row_id,
                        "effective_row_kind": str(row["row_kind"]),
                        "effective_ungraded_reason": grade.ungraded_reason,
                        "retained_row_id": ancestor_grade.row_id,
                        "retained_ticker": ancestor_grade.ticker,
                        "retained_market_relative_return": ancestor_grade.market_relative_return,
                    }
                )
                break

        verdict_basis_coverage = Coverage(
            kind="outcome",
            scope=(
                f"verdict basis for {family.family_id} at {horizon.name}: graded rows plus "
                "grades retained from superseded rows (the supersession ratchet)"
            ),
            observed=len(basis_real),
            universe=len(rows),
            status="complete" if len(basis_real) == len(rows) else "partial",
        )
        basis_values = [float(basis_real[key].market_relative_return) for key in sorted(basis_real)]
        basis_hits = sum(1 for key in sorted(basis_real) if basis_real[key].hit)

        # --- M1: the placebo delta is PAIRED ------------------------------
        # The prior delta subtracted a mean over one row set from a mean over a
        # different row set: rows that were `horizon_not_matured` on the real
        # side were graded on the placebo side, so the difference was not a
        # difference of anything. It fed the kill condition. The delta is now a
        # mean of per-candidate differences over the INTERSECTION.
        paired_ids = sorted(set(basis_real) & set(basis_placebo))
        paired_differences = [
            float(basis_real[key].market_relative_return)
            - float(basis_placebo[key].market_relative_return)
            for key in paired_ids
        ]
        paired_coverage = Coverage(
            kind="outcome",
            scope=(
                "candidates graded on BOTH the event window and its registered placebo window; "
                "an unpaired difference of means is a difference of different cohorts"
            ),
            observed=len(paired_ids),
            universe=len(rows),
            status="complete" if len(paired_ids) == len(rows) else "partial",
        )

        # --- B1: the kill-bearing mean carries its own coverage penalty ----
        # The hit rate has had Manski bounds since day one; the mean the verdict
        # actually reads had none, so a row that stopped resolving simply left
        # the statistic. These bounds impute every unresolved row at the
        # registered support and are printed as sensitivity, not as the verdict
        # input: at the registered coverage floor an assumption-free support is
        # wide enough to make every verdict indeterminate, which is its own
        # broken instrument. §7 records that choice.
        support_low, support_high = -1.0, 1.0
        imputed_n = len(rows) - len(graded)
        bounds_payload: dict[str, Any] = {
            "issued_n": len(rows),
            "graded_n": len(graded),
            "imputed_n": imputed_n,
            "imputation_support": [support_low, support_high],
            "lower_bound_mean": None,
            "upper_bound_mean": None,
            "coverage": outcome_coverage.to_payload(),
            "note": (
                "sensitivity, not the verdict input: every unresolved row imputed at the "
                "registered support. The width IS the cost of incomplete resolution. No row "
                "is imputed to a neutral outcome anywhere in this instrument"
            ),
        }
        if len(rows):
            total = sum(market_relative)
            bounds_payload["lower_bound_mean"] = (total + imputed_n * support_low) / len(rows)
            bounds_payload["upper_bound_mean"] = (total + imputed_n * support_high) / len(rows)

        basis_hit_low, _basis_hit_high = _rate_ci(
            basis_hits,
            len(basis_real),
            family=family,
            label=f"{horizon.name}.verdict_basis.hit_rate",
        )

        per_horizon[horizon.name] = {
            "horizon": horizon.to_payload(),
            "cohort": {
                "issued_n": len(rows),
                "graded_n": len(graded),
                "ungraded_n": len(ungraded),
                "ungraded_reasons": ungraded_reasons,
                "denominator_source": "issuance_log_cohort",
            },
            "coverage": outcome_coverage.to_payload(),
            "hit_rate": hit_rate.to_payload(),
            "hit_rate_bounds": {
                "lower_bound_hit_rate": lower.to_payload(),
                "upper_bound_hit_rate": upper.to_payload(),
                "note": (
                    "lower counts every ungraded row as a miss, upper as a hit; "
                    "no ungraded row is imputed to a neutral outcome"
                ),
            },
            "hit_rate_by_month": monthly,
            "market_relative_return_summary": _summary(
                market_relative,
                coverage=outcome_coverage,
                family=family,
                label=f"{horizon.name}.market_relative",
            ),
            "market_relative_return_bounds": bounds_payload,
            "sector_relative_return_summary": _summary(
                [float(grade.sector_relative_return) for grade in graded],
                coverage=outcome_coverage,
                family=family,
                label=f"{horizon.name}.sector_relative",
            ),
            "absolute_return_summary": _summary(
                [float(grade.absolute_return) for grade in graded],
                coverage=outcome_coverage,
                family=family,
                label=f"{horizon.name}.absolute",
            ),
            "max_drawdown_summary": _summary(
                [float(grade.max_drawdown) for grade in graded],
                coverage=outcome_coverage,
                family=family,
                label=f"{horizon.name}.max_drawdown",
            ),
            "window_independence": _window_independence(
                grades,
                calendar=calendar,
                horizon_sessions=horizon.sessions,
                coverage=outcome_coverage,
            ),
            # The block the verdict reads, and the only one it reads.
            "verdict_basis": {
                "n": len(basis_real),
                "coverage": verdict_basis_coverage.to_payload(),
                "market_relative_return_summary": _summary(
                    basis_values,
                    coverage=verdict_basis_coverage,
                    family=family,
                    label=f"{horizon.name}.verdict_basis.market_relative",
                ),
                "paired_placebo_delta_summary": _summary(
                    paired_differences,
                    coverage=paired_coverage,
                    family=family,
                    label=f"{horizon.name}.verdict_basis.paired_delta",
                ),
                "conditional_hit_rate": {
                    "name": f"{family.family_id}.{horizon.name}.verdict_basis_hit_rate",
                    "numerator": basis_hits,
                    "denominator": len(basis_real),
                    "value": (basis_hits / len(basis_real)) if basis_real else None,
                    "ci_lower": basis_hit_low,
                    "coverage": verdict_basis_coverage.to_payload(),
                },
                "retained_from_superseded": retained,
                "note": (
                    "supersession may lower coverage; it may never delete a grade a superseded "
                    "row already earned. Retained grades are listed row by row above"
                ),
            },
            # Calibration, in the only form this contract supports.  A candidate
            # asserts a DIRECTION ("possible_positive"), never a probability, so
            # there is no reliability curve to draw and none is faked here.  What
            # can be calibrated is the asserted direction against the same names'
            # own base rate over the matched pre-issuance windows.
            "calibration": {
                "asserted_direction": "possible_positive",
                "asserted_probability": None,
                "realized_direction_rate": hit_rate.to_payload(),
                "placebo_base_rate": Rate(
                    name=f"{family.family_id}.{horizon.name}.placebo_direction_rate",
                    numerator=sum(1 for grade in placebo_graded if grade.hit),
                    denominator=len(placebo_graded),
                    coverage=placebo_coverage,
                ).to_payload(),
                "coverage": outcome_coverage.to_payload(),
                "limitation": (
                    "the candidate contract asserts a direction, not a probability; "
                    "no reliability curve is available and none is inferred"
                ),
            },
            "placebo": {
                "coverage": paired_coverage.to_payload(),
                "placebo_coverage": placebo_coverage.to_payload(),
                "market_relative_return_summary": _summary(
                    placebo_relative,
                    coverage=placebo_coverage,
                    family=family,
                    label=f"{horizon.name}.placebo_market_relative",
                ),
                "paired_n": len(paired_ids),
                "paired_delta_market_relative_mean": (
                    sum(paired_differences) / len(paired_differences)
                )
                if paired_differences
                else None,
                "unpaired_delta_market_relative_mean": (
                    (sum(market_relative) / len(market_relative))
                    - (sum(placebo_relative) / len(placebo_relative))
                )
                if market_relative and placebo_relative
                else None,
                "note": (
                    "the delta is PAIRED on candidate_id over rows graded on both windows; the "
                    "unpaired figure is printed for comparison only and carries no verdict power, "
                    "because a difference of means over two different row sets is not a difference"
                ),
            },
            "gate": maturity_gate(
                rows, family=family, outcome_coverage=outcome_coverage, calendar=calendar
            ),
            "rows": [grade.to_payload() for grade in grades],
        }

    verdict = evaluate_verdict(
        per_horizon, family=family, as_of=as_of, latched_verdict=latched_verdict
    )
    # ONLY NOW.  Attaching before the call above would put the labels inside the
    # verdict's argument, and "it happens not to read that key" is a property of
    # today's implementation, not a guarantee.  Ordering is the guarantee.
    for horizon_name, block in disclosure_blocks.items():
        per_horizon[horizon_name]["disclosure_labels"] = block
    report = {
        "contract": REPORT_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "as_of": as_of.astimezone(timezone.utc).isoformat(),
        "family": family.to_payload(),
        # Every digest the cohort was issued under.  More than one means the
        # registration document changed while the cohort was accruing — which
        # §9 of the registration forbids — so it is reported, not collapsed.
        "prereg_document_sha256": sorted({str(row["prereg_document_sha256"]) for row in rows}),
        "price_basis": panel.basis.to_payload(),
        "calendar": calendar.to_payload(),
        "issuance_log": {
            "sha256": log.sha256,
            "byte_count": log.byte_count,
            "line_count": log.line_count,
        },
        "admission": {
            "considered": considered,
            "issued": len(rows),
            "abstained": len(abstained),
            "abstention_rate": Rate(
                name=f"{family.family_id}.abstention_rate",
                numerator=len(abstained),
                denominator=considered,
                coverage=admission_coverage,
            ).to_payload(),
            "abstention_reasons": reasons,
        },
        # Three coverages, three keys, never fused.
        "identity_coverage": identity_coverage.to_payload(),
        "event_coverage": event_coverage.to_payload(),
        "outcome_by_horizon": per_horizon,
        "authority": _authority(),
        "verdict": verdict,
        "verdict_state": verdict["state"],
        "limitations": [
            "Display/context only: this report cannot rank, size, gate, or originate a signal.",
            "An interim number here is not a promotion; promotion requires the existing gauntlet and an operator ruling.",
            "Every rate is reported beside its coverage; a rate over part of a cohort is not the cohort's rate.",
            "Ungraded rows are never imputed to a neutral outcome and never leave the denominator.",
            "Every verdict input carries an SD, a standard error, and a bootstrap interval, and "
            "each verdict region requires the interval to clear its registered threshold; a point "
            "comparison at the gate floor is a coin flip.",
            "A superseding row may lower coverage but may not delete a grade its predecessor "
            "earned; retained grades are listed in verdict_basis.retained_from_superseded. The "
            "residual risk is disclosed: a genuine source correction still has its old grade read.",
            "issued_n counts rows, not independent draws; window_independence prints the overlap.",
            "Disclosure labels are descriptive contamination markers computed after the verdict, "
            "never an input to it. 'none_in_window' (the calendar covered this issuer and found "
            "nothing) and 'unavailable' (it could not look) are separate states and are never "
            "merged; an uncovered issuer is never counted as a clean window.",
            "known_at is when this pipeline could first know the action, not when the market first could; "
            "the source publishes on a lag and carries no public-first-disclosure clock.",
            "Grades are reproducible only against the recorded price vintage; upstream re-adjustment moves them.",
        ],
    }
    assert_rates_carry_coverage(report)
    return report
