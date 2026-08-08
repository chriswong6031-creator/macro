"""Recorded-denominator coverage epochs for the dark BioCatalyst B1S4 lane.

The already-shipped ``engine.biocatalyst.discovery`` module proves that a set of
discovery runs reconciles into one atomic, gap-free selection-date envelope.  It
does not, on its own, say how much of the source that envelope actually covers.
This module adds exactly that missing half and nothing else:

* a **recorded coverage denominator** — the source's own ``totalCount`` per
  included scope, the observed unique record count, and the named exclusions the
  declared query family cannot reach;
* a **budget ledger** — byte, request, wall-clock and rate-limit budgets replayed
  from the run receipts, plus the stop condition actually hit;
* a **lifecycle block** — replay, correction, withdrawal and rollback behaviour
  bound to an exact digest of the included run payloads; and
* a **deterministic admission decision** that nominates already-reviewed fixed
  cohort members and can never enlarge one.

The central rule this module exists to enforce is that **a coverage claim is
earned only by the recorded denominator, never by the breadth of a query
string**.  An epoch that queried widely but recorded no denominator and no
exclusions claims nothing here: it fails validation.

No transport, scheduler, credential, storage, publication, route, model, or
alert path belongs in this module.  Nothing here enables a source, enlarges a
cohort, or converts a registry fact into a company, security, or sponsor identity.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import re
from typing import Any, Mapping, Sequence

from engine.biocatalyst.discovery import (
    DISCOVERY_COVERAGE_CONTRACT_ID,
    MAX_PAGES,
    MAX_RECORDS,
    build_discovery_coverage_epoch,
    validate_discovery_coverage_epoch,
    validate_discovery_run,
)
from engine.biocatalyst.fixed_cohort import (
    FIXED_COHORT_MAX_NCT_IDS,
    admit_fixed_cohort_candidates,
)
from engine.sector_intelligence import canonical_json_bytes, canonical_json_sha256
from engine.sector_intelligence.contracts import (
    ContractError,
    ContractValidationError,
    ValidationIssue,
    validate_contract,
)


COVERAGE_EPOCH_CONTRACT_ID = DISCOVERY_COVERAGE_CONTRACT_ID
ADMISSION_DECISION_CONTRACT_ID = "biocatalyst_cohort_admission_decision.v1"

DENOMINATOR_BASIS = "recorded_source_declared_total_count_per_included_scope"
DENOMINATOR_SEMANTICS = "denominator_is_recorded_evidence_not_inferred_from_query_breadth"

EXCLUSION_KINDS = (
    "records_outside_the_declared_selection_window",
    "records_never_returned_by_the_declared_query_family",
    "source_records_removed_or_withheld_by_the_registry",
    "resources_outside_the_declared_studies_endpoint",
    "records_beyond_the_recorded_budget_stop_condition",
)
MAX_KNOWN_EXCLUSIONS = 32
MAX_EXCLUSION_DESCRIPTION_BYTES = 512

COMPLETE_STOP_CONDITION = "declared_window_completed"
STOP_CONDITIONS = (
    COMPLETE_STOP_CONDITION,
    "byte_budget_reached",
    "request_budget_reached",
    "wall_clock_budget_reached",
    "rate_limit_interval_reached",
    "page_cap_reached",
    "record_cap_reached",
)

# One discovery run brackets its pages with a before/after ``/version`` probe.
VERSION_PROBES_PER_RUN = 2
MAX_BYTE_BUDGET = 137_438_953_472
MAX_REQUEST_BUDGET = 4_196_352
MAX_WALL_CLOCK_BUDGET_MS = 604_800_000
MAX_REQUEST_INTERVAL_MS = 86_400_000

LIFECYCLE_POLICY = {
    "replay_determinism": "epoch_is_a_pure_function_of_its_recorded_run_payload_digests",
    "correction_policy": "corrections_supersede_by_a_new_epoch_never_by_mutation",
    "withdrawal_policy": "withdrawal_closes_transaction_to_and_retains_the_withdrawn_epoch",
    "rollback_policy": "rollback_restores_the_prior_superseded_epoch_reference_only",
}
WITHDRAWAL_REASON_CODES = (
    "source_correction",
    "budget_or_rate_limit_breach",
    "denominator_unreconciled",
    "scope_review_revoked",
)
DISCOVERY_AUTHORITY = {
    "identity_inference": "source_native_record_identifiers_only_no_company_or_security_inference",
    "model_authority": "no_model_scoring_ordering_sizing_or_alerting_authority",
    "membership_authority": "reviewed_fixed_cohort_membership_only",
    "expansion_policy": "measured_separately_reviewed_epochs_never_an_unbounded_universe",
}

ADMISSION_AUTHORITY = "reviewed_fixed_cohort_membership_only"
ADMISSION_SEMANTICS = {
    "membership_change": "admission_never_enlarges_a_reviewed_cohort",
    "record_identity": "source_native_nct_id_only_no_company_or_security_inference",
    "authority": "facts_and_context_only_no_scoring_ordering_sizing_or_alerting",
    "discovery_binding": "candidates_must_be_recorded_in_the_bound_coverage_epoch",
}
ADMITTED_REASON = "nominated_reviewed_cohort_member"
NOT_A_MEMBER_REASON = "not_a_reviewed_cohort_member"
NOT_DISCOVERED_REASON = "not_recorded_in_the_bound_coverage_epoch"

# The sibling fixed-cohort control owns admission refusal.  This module never
# re-implements that decision: every candidate is offered to
# ``admit_fixed_cohort_candidates`` and classified by its own refusal.  The
# literal below only lets that refusal be told apart from a malformed input, and
# ``tests/test_biocatalyst_coverage_epoch.py`` pins it against the sibling.
COHORT_ENLARGEMENT_REFUSAL = "candidates may not enlarge fixed-cohort membership"

_SCOPE_REF_RE = re.compile(r"^ctgov_discovery_scope_[a-f0-9]{24}$")
_EPOCH_ID_RE = re.compile(r"^ctgov_discovery_coverage_[A-Za-z0-9_-]{1,96}$")
_MILLISECOND = timedelta(milliseconds=1)


class CoverageEpochError(ValueError):
    """A bounded, fail-closed coverage-epoch construction error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _detached(document: object, *, code: str) -> dict[str, Any]:
    """Return a plain JSON copy so reads cannot disagree with validation."""

    try:
        parsed = json.loads(canonical_json_bytes(document))
    except (ContractError, TypeError, ValueError, RecursionError, MemoryError) as exc:
        raise CoverageEpochError(code) from exc
    if type(parsed) is not dict:
        raise CoverageEpochError(code)
    return parsed


def _require_int(value: object, *, lower: int, upper: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise CoverageEpochError(code)
    return value


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _elapsed_ms(start: object, end: object, *, code: str) -> int:
    first, second = _parse_datetime(start), _parse_datetime(end)
    if first is None or second is None or second < first:
        raise CoverageEpochError(code)
    return (second - first) // _MILLISECOND


def _normalise_exclusions(known_exclusions: object) -> list[dict[str, str]]:
    if not isinstance(known_exclusions, (list, tuple)) or not known_exclusions:
        raise CoverageEpochError("COVERAGE_EXCLUSIONS_REQUIRED")
    if len(known_exclusions) > MAX_KNOWN_EXCLUSIONS:
        raise CoverageEpochError("COVERAGE_EXCLUSION_CAP_EXCEEDED")
    rows: list[dict[str, str]] = []
    for exclusion in known_exclusions:
        if not isinstance(exclusion, Mapping) or set(exclusion) != {"kind", "description"}:
            raise CoverageEpochError("COVERAGE_EXCLUSION_INVALID")
        kind, description = exclusion.get("kind"), exclusion.get("description")
        if kind not in EXCLUSION_KINDS:
            raise CoverageEpochError("COVERAGE_EXCLUSION_KIND_UNKNOWN")
        if (
            not isinstance(description, str)
            or not description
            or len(description.encode("utf-8")) > MAX_EXCLUSION_DESCRIPTION_BYTES
        ):
            raise CoverageEpochError("COVERAGE_EXCLUSION_INVALID")
        rows.append({"kind": kind, "description": description})
    if len({row["kind"] for row in rows}) != len(rows):
        raise CoverageEpochError("COVERAGE_EXCLUSION_DUPLICATE_KIND")
    rows.sort(key=lambda row: row["kind"])
    return rows


def derive_coverage_denominator(
    runs: Sequence[Mapping[str, Any]], *, known_exclusions: Sequence[Mapping[str, str]]
) -> dict[str, Any]:
    """Return the recorded denominator for already-validated discovery runs.

    The denominator is *recorded*, never inferred: every total comes from the
    source's own ``totalCount`` for one included scope, and the observed count is
    the union of the records those runs actually returned.
    """

    totals: dict[str, int] = {}
    observed: set[str] = set()
    for run in runs:
        scope_ref = run.get("scope_ref")
        counts = run.get("counts")
        if not isinstance(scope_ref, str) or not _SCOPE_REF_RE.fullmatch(scope_ref):
            raise CoverageEpochError("COVERAGE_DENOMINATOR_SCOPE_INVALID")
        if not isinstance(counts, Mapping):
            raise CoverageEpochError("COVERAGE_DENOMINATOR_COUNTS_INVALID")
        declared = _require_int(
            counts.get("declared_total_count"),
            lower=0,
            upper=MAX_RECORDS,
            code="COVERAGE_DENOMINATOR_COUNTS_INVALID",
        )
        if totals.setdefault(scope_ref, declared) != declared:
            raise CoverageEpochError("COVERAGE_DENOMINATOR_SCOPE_CONFLICT")
        records = run.get("deduplicated_records")
        if not isinstance(records, list):
            raise CoverageEpochError("COVERAGE_DENOMINATOR_COUNTS_INVALID")
        for record in records:
            if not isinstance(record, Mapping) or not isinstance(record.get("nct_id"), str):
                raise CoverageEpochError("COVERAGE_DENOMINATOR_COUNTS_INVALID")
            observed.add(record["nct_id"])
    if not totals:
        raise CoverageEpochError("COVERAGE_DENOMINATOR_SCOPE_INVALID")
    declared_total_sum = sum(totals.values())
    unreconciled = declared_total_sum - len(observed)
    if unreconciled < 0:
        # More distinct records than the source ever declared cannot be a
        # coverage claim; it is a contradiction in the recorded evidence.
        raise CoverageEpochError("COVERAGE_DENOMINATOR_UNRECONCILED")
    return {
        "basis": DENOMINATOR_BASIS,
        "semantics": DENOMINATOR_SEMANTICS,
        "declared_total_by_scope": [
            {"scope_ref": scope_ref, "declared_total_count": totals[scope_ref]}
            for scope_ref in sorted(totals)
        ],
        "declared_total_sum": declared_total_sum,
        "observed_unique_records": len(observed),
        "unreconciled_records": unreconciled,
        "known_exclusions": _normalise_exclusions(known_exclusions),
    }


def derive_budget_ledger(
    runs: Sequence[Mapping[str, Any]],
    *,
    byte_budget: int,
    request_budget: int,
    wall_clock_budget_ms: int,
    min_request_interval_ms: int,
    stop_condition: str,
) -> dict[str, Any]:
    """Replay the byte/request/time/rate-limit spend recorded by the runs."""

    if stop_condition not in STOP_CONDITIONS:
        raise CoverageEpochError("COVERAGE_STOP_CONDITION_UNKNOWN")
    byte_budget = _require_int(byte_budget, lower=0, upper=MAX_BYTE_BUDGET, code="COVERAGE_BUDGET_INVALID")
    request_budget = _require_int(request_budget, lower=0, upper=MAX_REQUEST_BUDGET, code="COVERAGE_BUDGET_INVALID")
    wall_clock_budget_ms = _require_int(
        wall_clock_budget_ms, lower=0, upper=MAX_WALL_CLOCK_BUDGET_MS, code="COVERAGE_BUDGET_INVALID"
    )
    min_request_interval_ms = _require_int(
        min_request_interval_ms, lower=0, upper=MAX_REQUEST_INTERVAL_MS, code="COVERAGE_BUDGET_INVALID"
    )

    bytes_spent = requests_spent = wall_clock_spent_ms = 0
    intervals: list[int] = []
    for run in runs:
        pages = run.get("pages")
        cut = run.get("source_cut")
        if not isinstance(pages, list) or not pages or not isinstance(cut, Mapping):
            raise CoverageEpochError("COVERAGE_BUDGET_RUN_INVALID")
        for page in pages:
            if not isinstance(page, Mapping):
                raise CoverageEpochError("COVERAGE_BUDGET_RUN_INVALID")
            bytes_spent += _require_int(
                page.get("byte_count"), lower=0, upper=MAX_BYTE_BUDGET, code="COVERAGE_BUDGET_RUN_INVALID"
            )
        requests_spent += len(pages) + VERSION_PROBES_PER_RUN
        wall_clock_spent_ms += _elapsed_ms(
            run.get("started_at"), run.get("finished_at"), code="COVERAGE_BUDGET_RUN_INVALID"
        )
        receipts = [
            cut.get("version_before_retrieved_at"),
            *(page.get("received_at") for page in pages),
            cut.get("version_after_retrieved_at"),
        ]
        for first, second in zip(receipts, receipts[1:]):
            intervals.append(_elapsed_ms(first, second, code="COVERAGE_BUDGET_RUN_INVALID"))
    if not intervals:
        raise CoverageEpochError("COVERAGE_BUDGET_RUN_INVALID")
    observed_min_request_interval_ms = min(intervals)
    if (
        bytes_spent > byte_budget
        or requests_spent > request_budget
        or wall_clock_spent_ms > wall_clock_budget_ms
    ):
        raise CoverageEpochError("COVERAGE_BUDGET_EXCEEDED")
    if observed_min_request_interval_ms < min_request_interval_ms:
        raise CoverageEpochError("COVERAGE_RATE_LIMIT_VIOLATION")
    if observed_min_request_interval_ms > MAX_REQUEST_INTERVAL_MS:
        raise CoverageEpochError("COVERAGE_BUDGET_RUN_INVALID")
    return {
        "byte_budget": byte_budget,
        "bytes_spent": bytes_spent,
        "request_budget": request_budget,
        "requests_spent": requests_spent,
        "wall_clock_budget_ms": wall_clock_budget_ms,
        "wall_clock_spent_ms": wall_clock_spent_ms,
        "min_request_interval_ms": min_request_interval_ms,
        "observed_min_request_interval_ms": observed_min_request_interval_ms,
        "stop_condition": stop_condition,
    }


def included_run_payload_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    """Digest the included run payload hashes so replay is exactly checkable."""

    digests = []
    for row in rows:
        digest = row.get("run_payload_sha256") if isinstance(row, Mapping) else None
        if not isinstance(digest, str):
            raise CoverageEpochError("COVERAGE_REPLAY_DIGEST_INVALID")
        digests.append(digest)
    return canonical_json_sha256(sorted(digests))


def build_attested_coverage_epoch(
    *,
    coverage_epoch_id: str,
    runs: Sequence[Mapping[str, Any]],
    declared_start_date: str,
    declared_end_date: str,
    transaction_from: str,
    known_exclusions: Sequence[Mapping[str, str]],
    byte_budget: int,
    request_budget: int,
    wall_clock_budget_ms: int,
    min_request_interval_ms: int = 0,
    stop_condition: str = COMPLETE_STOP_CONDITION,
    supersedes_coverage_epoch_id: str | None = None,
) -> dict[str, Any]:
    """Build one coverage epoch whose claim is backed by a recorded denominator.

    The atomic window reconciliation is delegated to the already-shipped
    ``build_discovery_coverage_epoch``; this function only adds the denominator,
    budget, lifecycle, and authority attestations and rebinds the payload digest.
    """

    if not isinstance(runs, (list, tuple)) or not runs or len(runs) > MAX_PAGES:
        raise CoverageEpochError("COVERAGE_RUN_CAP_INVALID")
    if stop_condition not in STOP_CONDITIONS:
        raise CoverageEpochError("COVERAGE_STOP_CONDITION_UNKNOWN")
    base = build_discovery_coverage_epoch(
        coverage_epoch_id=coverage_epoch_id,
        runs=runs,
        declared_start_date=declared_start_date,
        declared_end_date=declared_end_date,
        transaction_from=transaction_from,
    )
    normalized_runs = [validate_discovery_run(run) for run in runs]
    if (
        supersedes_coverage_epoch_id is not None
        and (
            not isinstance(supersedes_coverage_epoch_id, str)
            or _EPOCH_ID_RE.fullmatch(supersedes_coverage_epoch_id) is None
            or supersedes_coverage_epoch_id == base["coverage_epoch_id"]
        )
    ):
        raise CoverageEpochError("COVERAGE_LIFECYCLE_SUPERSEDES_INVALID")
    if base["coverage_state"] == "complete" and stop_condition != COMPLETE_STOP_CONDITION:
        raise CoverageEpochError("COVERAGE_STOP_CONDITION_CONTRADICTS_CLAIM")

    payload = {key: value for key, value in base.items() if key != "coverage_payload_sha256"}
    payload["coverage_denominator"] = derive_coverage_denominator(
        normalized_runs, known_exclusions=known_exclusions
    )
    payload["budget_ledger"] = derive_budget_ledger(
        normalized_runs,
        byte_budget=byte_budget,
        request_budget=request_budget,
        wall_clock_budget_ms=wall_clock_budget_ms,
        min_request_interval_ms=min_request_interval_ms,
        stop_condition=stop_condition,
    )
    payload["lifecycle"] = {
        **LIFECYCLE_POLICY,
        "included_run_payload_digest_sha256": included_run_payload_digest(base["included_runs"]),
        "supersedes_coverage_epoch_id": supersedes_coverage_epoch_id,
        "superseded_by_coverage_epoch_id": None,
        "withdrawn_at": None,
        "withdrawal_reason_code": None,
    }
    payload["discovery_authority"] = dict(DISCOVERY_AUTHORITY)
    payload["coverage_payload_sha256"] = canonical_json_sha256(payload)
    return validate_attested_coverage_epoch(payload, runs=normalized_runs)


def _denominator_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    denominator = document.get("coverage_denominator")
    exclusions = denominator.get("known_exclusions") if isinstance(denominator, Mapping) else None
    if not isinstance(denominator, Mapping) or not isinstance(exclusions, list) or not exclusions:
        # THE honesty rule.  Query breadth is not evidence: an epoch that records
        # no denominator and no exclusions is not permitted to claim coverage.
        return [
            _issue(
                "$.coverage_denominator",
                "coverage_epoch.unrecorded_denominator",
                "a coverage claim requires a recorded denominator and its known exclusions",
            )
        ]
    issues: list[ValidationIssue] = []
    if denominator.get("basis") != DENOMINATOR_BASIS or denominator.get("semantics") != DENOMINATOR_SEMANTICS:
        issues.append(
            _issue(
                "$.coverage_denominator",
                "coverage_epoch.unrecorded_denominator",
                "the denominator must declare its recorded, non-inferred basis",
            )
        )
    kinds = [row.get("kind") for row in exclusions if isinstance(row, Mapping)]
    if len(kinds) != len(exclusions) or any(kind not in EXCLUSION_KINDS for kind in kinds):
        issues.append(
            _issue(
                "$.coverage_denominator.known_exclusions",
                "coverage_epoch.exclusion_kind",
                "every known exclusion must use a reviewed exclusion kind",
            )
        )
    elif kinds != sorted(kinds) or len(set(kinds)) != len(kinds):
        issues.append(
            _issue(
                "$.coverage_denominator.known_exclusions",
                "coverage_epoch.exclusion_kind",
                "known exclusions must be unique and ordered by kind",
            )
        )
    rows = denominator.get("declared_total_by_scope")
    if not isinstance(rows, list) or not rows:
        return issues + [
            _issue(
                "$.coverage_denominator.declared_total_by_scope",
                "coverage_epoch.unrecorded_denominator",
                "the denominator must record one source-declared total per included scope",
            )
        ]
    refs = [row.get("scope_ref") for row in rows if isinstance(row, Mapping)]
    totals = [row.get("declared_total_count") for row in rows if isinstance(row, Mapping)]
    if len(refs) != len(rows) or any(
        isinstance(total, bool) or not isinstance(total, int) for total in totals
    ):
        return issues + [
            _issue(
                "$.coverage_denominator.declared_total_by_scope",
                "coverage_epoch.unrecorded_denominator",
                "the denominator must record one source-declared total per included scope",
            )
        ]
    if refs != sorted(refs) or len(set(refs)) != len(refs):
        issues.append(
            _issue(
                "$.coverage_denominator.declared_total_by_scope",
                "coverage_epoch.denominator_order",
                "declared totals must be unique and ordered by scope reference",
            )
        )
    included = document.get("included_runs")
    if isinstance(included, list):
        evidenced = {
            row.get("scope_ref")
            for row in included
            if isinstance(row, Mapping) and isinstance(row.get("scope_ref"), str)
        }
        if set(refs) != evidenced:
            # A denominator may only be recorded for scopes the epoch evidences,
            # so a wide query cannot borrow a denominator it never ran.
            issues.append(
                _issue(
                    "$.coverage_denominator.declared_total_by_scope",
                    "coverage_epoch.denominator_scope_binding",
                    "declared totals must cover exactly the scopes evidenced by included runs",
                )
            )
    declared_sum = denominator.get("declared_total_sum")
    observed = denominator.get("observed_unique_records")
    unreconciled = denominator.get("unreconciled_records")
    numeric = (declared_sum, observed, unreconciled)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in numeric):
        return issues + [
            _issue(
                "$.coverage_denominator",
                "coverage_epoch.denominator_arithmetic",
                "denominator totals must be exact integers",
            )
        ]
    if declared_sum != sum(totals) or unreconciled != declared_sum - observed or unreconciled < 0:
        issues.append(
            _issue(
                "$.coverage_denominator",
                "coverage_epoch.denominator_arithmetic",
                "denominator totals must reconcile exactly with the recorded per-scope totals",
            )
        )
    return issues


def _budget_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    ledger = document.get("budget_ledger")
    if not isinstance(ledger, Mapping):
        return [
            _issue(
                "$.budget_ledger",
                "coverage_epoch.unrecorded_budget",
                "a coverage epoch must record its byte, request, time and rate-limit budgets",
            )
        ]
    issues: list[ValidationIssue] = []
    stop_condition = ledger.get("stop_condition")
    if stop_condition not in STOP_CONDITIONS:
        issues.append(
            _issue(
                "$.budget_ledger.stop_condition",
                "coverage_epoch.stop_condition",
                "the stop condition actually hit must be one of the reviewed conditions",
            )
        )
    elif document.get("coverage_state") == "complete" and stop_condition != COMPLETE_STOP_CONDITION:
        # Stopping on a budget is a partial walk; it may never read as complete.
        issues.append(
            _issue(
                "$.budget_ledger.stop_condition",
                "coverage_epoch.stop_condition",
                "only a completed declared window may claim complete coverage",
            )
        )
    for budget_key, spent_key in (
        ("byte_budget", "bytes_spent"),
        ("request_budget", "requests_spent"),
        ("wall_clock_budget_ms", "wall_clock_spent_ms"),
    ):
        budget, spent = ledger.get(budget_key), ledger.get(spent_key)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (budget, spent)):
            issues.append(
                _issue(
                    f"$.budget_ledger.{spent_key}",
                    "coverage_epoch.budget_exceeded",
                    "recorded budgets and spends must be exact integers",
                )
            )
        elif spent > budget:
            issues.append(
                _issue(
                    f"$.budget_ledger.{spent_key}",
                    "coverage_epoch.budget_exceeded",
                    "recorded spend may never exceed its recorded budget",
                )
            )
    declared_interval = ledger.get("min_request_interval_ms")
    observed_interval = ledger.get("observed_min_request_interval_ms")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (declared_interval, observed_interval)
    ) or observed_interval < declared_interval:
        issues.append(
            _issue(
                "$.budget_ledger.observed_min_request_interval_ms",
                "coverage_epoch.rate_limit",
                "the observed request interval may never undercut the recorded rate limit",
            )
        )
    return issues


def _lifecycle_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    lifecycle = document.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        return [
            _issue(
                "$.lifecycle",
                "coverage_epoch.lifecycle",
                "a coverage epoch must record replay, correction, withdrawal and rollback behaviour",
            )
        ]
    issues: list[ValidationIssue] = []
    for key, expected in LIFECYCLE_POLICY.items():
        if lifecycle.get(key) != expected:
            issues.append(
                _issue(
                    f"$.lifecycle.{key}",
                    "coverage_epoch.lifecycle",
                    "lifecycle policy must bind the reviewed replay and correction semantics",
                )
            )
    epoch_id = document.get("coverage_epoch_id")
    superseded_by = lifecycle.get("superseded_by_coverage_epoch_id")
    supersedes = lifecycle.get("supersedes_coverage_epoch_id")
    withdrawn_at = lifecycle.get("withdrawn_at")
    reason = lifecycle.get("withdrawal_reason_code")
    if isinstance(epoch_id, str) and epoch_id in {superseded_by, supersedes}:
        issues.append(
            _issue(
                "$.lifecycle",
                "coverage_epoch.lifecycle",
                "an epoch may not supersede or be superseded by itself",
            )
        )
    transaction_to = document.get("transaction_to")
    if transaction_to is None:
        if superseded_by is not None or withdrawn_at is not None or reason is not None:
            issues.append(
                _issue(
                    "$.lifecycle",
                    "coverage_epoch.lifecycle",
                    "an open epoch may not record a withdrawal or a successor",
                )
            )
    else:
        if (superseded_by is None) == (withdrawn_at is None):
            issues.append(
                _issue(
                    "$.lifecycle",
                    "coverage_epoch.lifecycle",
                    "a closed epoch must record exactly one of supersession or withdrawal",
                )
            )
        if withdrawn_at is not None and (withdrawn_at != transaction_to or reason not in WITHDRAWAL_REASON_CODES):
            issues.append(
                _issue(
                    "$.lifecycle.withdrawn_at",
                    "coverage_epoch.lifecycle",
                    "a withdrawal must close the transaction interval and record its reason",
                )
            )
        if withdrawn_at is None and reason is not None:
            issues.append(
                _issue(
                    "$.lifecycle.withdrawal_reason_code",
                    "coverage_epoch.lifecycle",
                    "a withdrawal reason requires a withdrawal",
                )
            )
    rows = document.get("included_runs")
    if isinstance(rows, list):
        try:
            expected_digest = included_run_payload_digest(rows)
        except (CoverageEpochError, ContractError):
            expected_digest = None
        if expected_digest is not None and lifecycle.get("included_run_payload_digest_sha256") != expected_digest:
            issues.append(
                _issue(
                    "$.lifecycle.included_run_payload_digest_sha256",
                    "coverage_epoch.replay_digest",
                    "the replay digest must bind exactly the included run payload digests",
                )
            )
    return issues


def attested_coverage_epoch_semantic_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    """Return the B1S4 attestation failures for one coverage-epoch document."""

    if not isinstance(document, Mapping):
        return [_issue("$", "coverage_epoch.document", "a coverage epoch must be a JSON object")]
    issues = _denominator_issues(document)
    issues.extend(_budget_issues(document))
    issues.extend(_lifecycle_issues(document))
    if document.get("discovery_authority") != DISCOVERY_AUTHORITY:
        issues.append(
            _issue(
                "$.discovery_authority",
                "coverage_epoch.authority",
                "discovery may never infer identity or carry model, ordering, or alerting authority",
            )
        )
    return sorted(set(issues))


def validate_attested_coverage_epoch(
    epoch: Mapping[str, Any], *, runs: Sequence[Mapping[str, Any]] | None = None
) -> dict[str, Any]:
    """Validate the base epoch contract and then its recorded attestations."""

    normalized = validate_discovery_coverage_epoch(epoch, runs=runs)
    issues = attested_coverage_epoch_semantic_issues(normalized)
    if runs is not None:
        issues.extend(_replay_issues(normalized, runs))
    if issues:
        raise ContractValidationError(COVERAGE_EPOCH_CONTRACT_ID, tuple(sorted(set(issues))))
    return normalized


def _replay_issues(
    document: Mapping[str, Any], runs: Sequence[Mapping[str, Any]]
) -> list[ValidationIssue]:
    normalized_runs = [validate_discovery_run(run) for run in runs]
    issues: list[ValidationIssue] = []
    denominator = document.get("coverage_denominator")
    if isinstance(denominator, Mapping) and isinstance(denominator.get("known_exclusions"), list):
        try:
            expected = derive_coverage_denominator(
                normalized_runs, known_exclusions=denominator["known_exclusions"]
            )
        except CoverageEpochError:
            expected = None
        if expected is None or dict(denominator) != expected:
            issues.append(
                _issue(
                    "$.coverage_denominator",
                    "coverage_epoch.denominator_replay",
                    "the recorded denominator must replay exactly from the supplied runs",
                )
            )
    ledger = document.get("budget_ledger")
    if isinstance(ledger, Mapping):
        try:
            expected_ledger = derive_budget_ledger(
                normalized_runs,
                byte_budget=ledger.get("byte_budget"),
                request_budget=ledger.get("request_budget"),
                wall_clock_budget_ms=ledger.get("wall_clock_budget_ms"),
                min_request_interval_ms=ledger.get("min_request_interval_ms"),
                stop_condition=ledger.get("stop_condition"),
            )
        except CoverageEpochError:
            expected_ledger = None
        if expected_ledger is None or dict(ledger) != expected_ledger:
            issues.append(
                _issue(
                    "$.budget_ledger",
                    "coverage_epoch.budget_replay",
                    "the recorded budget spend must replay exactly from the supplied runs",
                )
            )
    return issues


def _classify_candidate(
    cohort: Mapping[str, Any], candidate: str, *, repo_root: object | None
) -> bool:
    """Offer one candidate to the sibling control and read back its own verdict."""

    try:
        admit_fixed_cohort_candidates(cohort, [candidate], repo_root=repo_root)
    except ContractError:
        # A cohort that does not validate is not a refusal; it is a broken input.
        raise
    except ValueError as exc:
        if str(exc) == COHORT_ENLARGEMENT_REFUSAL:
            return False
        raise CoverageEpochError("COVERAGE_ADMISSION_CANDIDATES_INVALID") from exc
    return True


def build_cohort_admission_decision(
    *,
    epoch: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
    cohort: Mapping[str, Any],
    candidates: Sequence[str],
    decided_at: str,
    repo_root: object | None = None,
) -> dict[str, Any]:
    """Decide, deterministically, which discovered candidates a cohort admits.

    Admission is never originated here.  Every candidate is offered to the
    sibling ``admit_fixed_cohort_candidates`` control, so a candidate outside the
    reviewed membership is refused by that control's own refusal, and the
    reviewed bound can never grow.
    """

    normalized_epoch = validate_attested_coverage_epoch(epoch, runs=runs)
    if normalized_epoch["coverage_state"] != "complete":
        raise CoverageEpochError("COVERAGE_ADMISSION_REQUIRES_A_COMPLETE_EPOCH")
    normalized_runs = [validate_discovery_run(run) for run in runs]
    discovered = {
        record["nct_id"]
        for run in normalized_runs
        for record in run["deduplicated_records"]
    }
    if type(candidates) not in (list, tuple):
        raise CoverageEpochError("COVERAGE_ADMISSION_CANDIDATES_INVALID")
    if not 1 <= len(candidates) <= FIXED_COHORT_MAX_NCT_IDS:
        raise CoverageEpochError("COVERAGE_ADMISSION_CANDIDATE_CAP_INVALID")
    if len(set(candidates)) != len(candidates):
        raise CoverageEpochError("COVERAGE_ADMISSION_CANDIDATES_INVALID")

    decisions: list[dict[str, str]] = []
    nominated: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            raise CoverageEpochError("COVERAGE_ADMISSION_CANDIDATES_INVALID")
        if candidate not in discovered:
            decisions.append(
                {"nct_id": candidate, "decision": "refused", "reason": NOT_DISCOVERED_REASON}
            )
            continue
        if _classify_candidate(cohort, candidate, repo_root=repo_root):
            decisions.append(
                {"nct_id": candidate, "decision": "admitted", "reason": ADMITTED_REASON}
            )
            nominated.append(candidate)
        else:
            decisions.append(
                {"nct_id": candidate, "decision": "refused", "reason": NOT_A_MEMBER_REASON}
            )
    # The canonical admitted order is the cohort's own order, produced by the
    # sibling control rather than reconstructed here.
    admitted = (
        list(admit_fixed_cohort_candidates(cohort, nominated, repo_root=repo_root))
        if nominated
        else []
    )
    decisions.sort(key=lambda row: row["nct_id"])
    snapshot = _detached(cohort, code="COVERAGE_ADMISSION_COHORT_INVALID")
    membership = snapshot.get("nct_ids")
    if not isinstance(membership, list) or not membership:
        raise CoverageEpochError("COVERAGE_ADMISSION_COHORT_INVALID")

    payload: dict[str, Any] = {
        "contract_id": ADMISSION_DECISION_CONTRACT_ID,
        "schema_version": "1.0.0",
        "source_id": "clinicaltrials_gov_v2",
        "source_native_identifier_kind": "nct_id",
        "coverage_epoch_ref": normalized_epoch["coverage_epoch_id"],
        "coverage_payload_sha256": normalized_epoch["coverage_payload_sha256"],
        "coverage_transaction_from": normalized_epoch["transaction_from"],
        "discovered_record_count": len(discovered),
        "cohort_id": snapshot.get("cohort_id"),
        "cohort_payload_sha256": snapshot.get("cohort_payload_sha256"),
        "reviewed_membership_bound": len(membership),
        "decisions": decisions,
        "admitted_nct_ids": admitted,
        "refused_nct_ids": sorted(
            row["nct_id"] for row in decisions if row["decision"] == "refused"
        ),
        "admission_authority": ADMISSION_AUTHORITY,
        "admission_semantics": dict(ADMISSION_SEMANTICS),
        "decided_at": decided_at,
        "transaction_from": decided_at,
        "transaction_to": None,
        "hash_scope": "canonical_payload_excluding_decision_payload_sha256",
    }
    identity = canonical_json_sha256(payload)
    payload["decision_id"] = f"biocatalyst_cohort_admission_{identity[:24]}"
    payload["decision_payload_sha256"] = canonical_json_sha256(payload)
    return validate_cohort_admission_decision(payload, cohort=cohort, repo_root=repo_root)


def cohort_admission_decision_semantic_issues(
    document: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Return the deterministic admission failures for one decision document."""

    if not isinstance(document, Mapping):
        return [_issue("$", "cohort_admission.document", "an admission decision must be a JSON object")]
    issues: list[ValidationIssue] = []
    decisions = document.get("decisions")
    admitted = document.get("admitted_nct_ids")
    refused = document.get("refused_nct_ids")
    if not isinstance(decisions, list) or not isinstance(admitted, list) or not isinstance(refused, list):
        return [_issue("$.decisions", "cohort_admission.decisions", "admission decisions must be recorded as lists")]
    rows = [row for row in decisions if isinstance(row, Mapping)]
    if len(rows) != len(decisions):
        return [_issue("$.decisions", "cohort_admission.decisions", "every admission decision must be an object")]
    ids = [row.get("nct_id") for row in rows]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        issues.append(
            _issue("$.decisions", "cohort_admission.order", "decisions must be unique and ordered by NCT identifier")
        )
    for index, row in enumerate(rows):
        admitted_row = row.get("decision") == "admitted"
        if admitted_row != (row.get("reason") == ADMITTED_REASON):
            issues.append(
                _issue(
                    f"$.decisions[{index}].reason",
                    "cohort_admission.reason",
                    "an admitted decision requires the reviewed-membership reason and no other",
                )
            )
    expected_admitted = {row["nct_id"] for row in rows if row.get("decision") == "admitted"}
    expected_refused = {row["nct_id"] for row in rows if row.get("decision") == "refused"}
    if set(admitted) != expected_admitted or len(set(admitted)) != len(admitted):
        issues.append(
            _issue("$.admitted_nct_ids", "cohort_admission.decisions", "admitted identifiers must equal the admitted decisions")
        )
    if sorted(refused) != sorted(expected_refused) or refused != sorted(refused):
        issues.append(
            _issue("$.refused_nct_ids", "cohort_admission.decisions", "refused identifiers must equal the refused decisions in order")
        )
    bound = document.get("reviewed_membership_bound")
    if isinstance(bound, bool) or not isinstance(bound, int) or len(expected_admitted) > bound:
        issues.append(
            _issue(
                "$.admitted_nct_ids",
                "cohort_admission.enlargement",
                "an admission may never exceed the reviewed cohort membership bound",
            )
        )
    discovered_count = document.get("discovered_record_count")
    if isinstance(discovered_count, int) and not isinstance(discovered_count, bool):
        discovered_decisions = [row for row in rows if row.get("reason") != NOT_DISCOVERED_REASON]
        if len(discovered_decisions) > discovered_count:
            issues.append(
                _issue(
                    "$.decisions",
                    "cohort_admission.discovery_binding",
                    "more candidates were treated as discovered than the epoch recorded",
                )
            )
    if document.get("admission_authority") != ADMISSION_AUTHORITY or document.get("admission_semantics") != ADMISSION_SEMANTICS:
        issues.append(
            _issue(
                "$.admission_semantics",
                "cohort_admission.authority",
                "admission carries reviewed-membership authority only, never identity or ordering authority",
            )
        )
    decided = _parse_datetime(document.get("decided_at"))
    coverage_from = _parse_datetime(document.get("coverage_transaction_from"))
    transaction_from = _parse_datetime(document.get("transaction_from"))
    if decided is None or coverage_from is None or transaction_from is None:
        issues.append(
            _issue("$.decided_at", "cohort_admission.knowledge_time", "admission times must be exact instants")
        )
    elif decided < coverage_from or transaction_from < decided:
        issues.append(
            _issue(
                "$.decided_at",
                "cohort_admission.knowledge_time",
                "an admission may not predate the coverage epoch it is bound to",
            )
        )
    expected_digest = None
    try:
        expected_digest = canonical_json_sha256(
            {key: value for key, value in document.items() if key != "decision_payload_sha256"}
        )
        expected_identity = canonical_json_sha256(
            {
                key: value
                for key, value in document.items()
                if key not in {"decision_id", "decision_payload_sha256"}
            }
        )
    except ContractError:
        return issues + [
            _issue("$", "cohort_admission.hash", "an admission decision must be finite canonical JSON")
        ]
    if document.get("decision_payload_sha256") != expected_digest:
        issues.append(
            _issue("$.decision_payload_sha256", "cohort_admission.hash", "declared digest does not match the canonical payload")
        )
    if document.get("decision_id") != f"biocatalyst_cohort_admission_{expected_identity[:24]}":
        issues.append(
            _issue(
                "$.decision_id",
                "cohort_admission.identity",
                "decision_id must be derived from the payload excluding identity and digest",
            )
        )
    return sorted(set(issues))


def validate_cohort_admission_decision(
    document: Mapping[str, Any],
    *,
    cohort: Mapping[str, Any] | None = None,
    epoch: Mapping[str, Any] | None = None,
    repo_root: object | None = None,
) -> dict[str, Any]:
    """Validate one admission decision and, when supplied, its exact bindings."""

    normalized = _detached(document, code="COVERAGE_ADMISSION_CONTRACT_INVALID")
    try:
        validate_contract(ADMISSION_DECISION_CONTRACT_ID, normalized, repo_root=repo_root)
    except ContractValidationError:
        raise
    except ContractError as exc:
        raise CoverageEpochError("COVERAGE_ADMISSION_CONTRACT_INVALID") from exc
    issues = cohort_admission_decision_semantic_issues(normalized)
    if cohort is not None:
        snapshot = _detached(cohort, code="COVERAGE_ADMISSION_COHORT_INVALID")
        membership = snapshot.get("nct_ids")
        admitted = normalized.get("admitted_nct_ids")
        if not isinstance(membership, list):
            issues.append(
                _issue("$.cohort_id", "cohort_admission.cohort_binding", "the bound cohort must declare its membership")
            )
        else:
            if normalized.get("cohort_id") != snapshot.get("cohort_id") or normalized.get(
                "cohort_payload_sha256"
            ) != snapshot.get("cohort_payload_sha256"):
                issues.append(
                    _issue("$.cohort_id", "cohort_admission.cohort_binding", "the decision must bind the exact reviewed cohort")
                )
            if normalized.get("reviewed_membership_bound") != len(membership):
                issues.append(
                    _issue(
                        "$.reviewed_membership_bound",
                        "cohort_admission.cohort_binding",
                        "the reviewed bound must equal the reviewed cohort membership size",
                    )
                )
            if isinstance(admitted, list) and not set(admitted) <= set(membership):
                issues.append(
                    _issue(
                        "$.admitted_nct_ids",
                        "cohort_admission.enlargement",
                        "an admission may never introduce a non-member into a reviewed cohort",
                    )
                )
            if isinstance(admitted, list) and admitted != [
                nct_id for nct_id in membership if nct_id in set(admitted)
            ]:
                issues.append(
                    _issue(
                        "$.admitted_nct_ids",
                        "cohort_admission.order",
                        "admitted identifiers must keep the reviewed cohort order",
                    )
                )
    if epoch is not None:
        bound_epoch = validate_attested_coverage_epoch(epoch)
        if (
            normalized.get("coverage_epoch_ref") != bound_epoch["coverage_epoch_id"]
            or normalized.get("coverage_payload_sha256") != bound_epoch["coverage_payload_sha256"]
            or normalized.get("coverage_transaction_from") != bound_epoch["transaction_from"]
        ):
            issues.append(
                _issue(
                    "$.coverage_epoch_ref",
                    "cohort_admission.coverage_binding",
                    "the decision must bind the exact attested coverage epoch",
                )
            )
    if issues:
        raise ContractValidationError(ADMISSION_DECISION_CONTRACT_ID, tuple(sorted(set(issues))))
    return normalized


__all__ = [
    "ADMISSION_DECISION_CONTRACT_ID",
    "COMPLETE_STOP_CONDITION",
    "COVERAGE_EPOCH_CONTRACT_ID",
    "COHORT_ENLARGEMENT_REFUSAL",
    "CoverageEpochError",
    "DENOMINATOR_BASIS",
    "DENOMINATOR_SEMANTICS",
    "DISCOVERY_AUTHORITY",
    "EXCLUSION_KINDS",
    "LIFECYCLE_POLICY",
    "STOP_CONDITIONS",
    "VERSION_PROBES_PER_RUN",
    "WITHDRAWAL_REASON_CODES",
    "attested_coverage_epoch_semantic_issues",
    "build_attested_coverage_epoch",
    "build_cohort_admission_decision",
    "cohort_admission_decision_semantic_issues",
    "derive_budget_ledger",
    "derive_coverage_denominator",
    "included_run_payload_digest",
    "validate_attested_coverage_epoch",
    "validate_cohort_admission_decision",
]
