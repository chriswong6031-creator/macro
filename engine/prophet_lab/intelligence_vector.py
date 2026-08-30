"""Pure D5 projection of Earnings workspaces into an Intelligence Vector.

This module is deliberately an adapter, not a store and not an Earnings
reader.  It resolves the candidate episode's canonical issuer identity, uses
the shared current-manifest discovery/revision-chain seams, selects only facts
whose three clocks were admissible at the B1 episode cut, and emits one
closed, non-authoritative ``earnings.event`` family.

The current manifest can discover the currently published event only.  It is
not a historical event-set reconstruction; that limitation is explicit in
every assembly receipt.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any, Callable, Mapping, Sequence

from engine.company_intelligence.event_workspace import WORKSPACE_WARNINGS
from engine.company_intelligence.identity import IdentityError as EarningsIdentityError
from engine.company_intelligence.identity import company_id_for_cik
from engine.neuralweb.company_intelligence_reader import (
    CompanyIntelligenceReadError,
    WorkspaceChainIntegrityError,
    WorkspaceChainNotPublished,
    find_current_event_id_for_company,
    read_event_source_revisions,
)
from engine.us_candidate_episode import (
    EpisodeContractError,
    episode_id as b1_episode_id,
)
from lib.dataos.identity import (
    IdentityError as IssuerIdentityError,
    parse_id as parse_dataos_id,
    security_id as dataos_security_id,
)


SCHEMA_INTELLIGENCE_VECTOR = "prophet.intelligence_vector/v1"
EARNINGS_FAMILY_ID = "earnings.event"
ADAPTER_SET_VERSION = "earnings-d5-adapter/1.0.0"
FAMILY_CONTRACT_VERSION = "earnings.event/v1"

ALL_FALSE_AUTHORITY: dict[str, bool] = {
    "can_rank": False,
    "can_gate": False,
    "can_size": False,
    "can_originate_signal": False,
    "can_change_entry_open": False,
    "can_change_execution": False,
}

_TOP_KEYS = frozenset({
    "schema", "projection_id", "episode_ref", "decision_cut",
    "adapter_set_version", "evidence_families", "economic_dependence_groups",
    "semantic_heads", "fusion_bindings", "authority", "assembly_receipt",
})
_FAMILY_KEYS = frozenset({
    "family_projection_id", "evidence_family_id", "family_contract_version",
    "owner_ref", "subject_binding", "semantic_head_ids", "method_version",
    "point_in_time", "applicability", "coverage", "freshness", "rights",
    "identity_state", "quality", "source_refs", "evidence_roots", "observations",
    "explanation_facts", "trajectory", "correction", "calibration", "fusion_bindings",
    "authority", "owner_warnings",
})
_FORBIDDEN_KEYS = frozenset({
    "score", "rank", "weight", "confidence", "conviction", "evidence_count",
    "entry_open", "ENTRY_OPEN", "body", "claims", "transcript",
    "private_path", "path", "url", "workspace", "source_span",
})
_PEG_RE = re.compile(r"^peg:[0-9a-f]{64}$")
_B1_EPISODE_ID_RE = re.compile(
    r"^pe:(?P<security>SEC:[^:]+):(?P<epoch>[^:]+):sa:"
    r"[0-9a-f]{24}:(?P<generation>[1-9][0-9]*)$"
)
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_WORKSPACE_GENERATION_RE = re.compile(r"^[0-9a-f]{24,64}$")
_EVENT_ID_RE = re.compile(r"^evt_[A-Za-z0-9_.:-]{1,127}$")
_EVENT_CIK_RE = re.compile(r"^evt_cik(?P<cik>[0-9]{10})_")
_EARNINGS_COMPANY_ID_RE = re.compile(r"^cik:(?P<cik>[0-9]{10})$")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_PATH_RE = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s]+)")
_NON_HTTP_URI_RE = re.compile(r"\b(?:s3|gs|file|ftp|ssh)://\S+", re.IGNORECASE)
_ARN_RE = re.compile(r"\barn:[a-z0-9_-]+:[^\s]+", re.IGNORECASE)
_UNC_PATH_RE = re.compile(r"\\\\[^\s\\]+\\[^\s]+")
_WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\[^\s]+")
_CREDENTIAL_RE = re.compile(
    r"(?:\bbearer(?:\s+|\s*:\s*)|(?<![A-Za-z0-9])[\"']?"
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|token|"
    r"authorization|client[_-]?secret|password|passwd|secret|private[_-]?key)"
    r"[\"']?\s*[:=]\s*)[\"']?[^\s,;}\]]+",
    re.IGNORECASE,
)
_STORAGE_LOCATOR_RE = re.compile(
    r"\b(?:bucket|object[_-]?key|storage[_-]?key)\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)
_OBJECT_ID_RE = re.compile(
    r"^(?:(?:doc|revision):[A-Za-z0-9][A-Za-z0-9_.:|-]{0,123}|"
    r"tx:[A-Z0-9](?:[A-Z0-9.-]{0,14}[A-Z0-9])?/\d{4}Q[1-4]|"
    r"disclosure_document_[0-9a-f]{64})$"
)
_FIELD_PATH_RE = re.compile(
    r"^(?:facts\[[0-9]+\]\.(?:metric|value|unit|basis)|"
    r"guidance\[[0-9]+\]\.(?:metric|low|high|unit|status)|"
    r"deltas\[[0-9]+\]\.(?:metric|basis_match|current\.(?:value|unit|basis)|"
    r"(?:prior|consensus)\.(?:schema|state|reason)))$"
)
_CLOCK_BASES = {
    "source_effective_at": frozenset({
        "earnings_owner_asserts_no_effective_clock_for_results",
    }),
    "source_published_at": frozenset({
        "event_workspace.lifecycle.source_available_at",
    }),
    "known_at": frozenset({"event_workspace.lifecycle.observed_at"}),
    "captured_at": frozenset({
        "per_source_system_recorded_at_not_exposed_by_revision_receipt",
    }),
    "computed_at": frozenset({"event_workspace.generated_at"}),
    "corrected_at": frozenset({
        "later_event_workspace.generated_at",
        "no_later_visible_source_revision",
    }),
    "decision_at": frozenset({"prophet.candidate_episode.opened_at"}),
}
_GUIDANCE_STATES = frozenset({"introduced", "reiterated", "raised", "cut", "withdrawn", "absent"})
_DELTA_ABSENCE_REASONS = frozenset({
    "not_available", "consensus_unlicensed", "no_span_addressable_evidence",
    "missing_source", "no_transcript", "not_applicable", "unknown",
})
_COVERAGE_QUALITY_VOCABULARY: dict[tuple[str, str], tuple[str, ...]] = {
    ("UNKNOWN", "canonical_identity_ambiguous"): ("identity_ambiguous",),
    ("UNKNOWN", "canonical_identity_unresolved"): ("identity_unresolved",),
    ("UNKNOWN", "current_manifest_integrity_failure"): ("correction_chain_integrity",),
    ("UNKNOWN", "source_fetch_failed"): ("source_unavailable",),
    ("NOT_COVERED", "no_current_generation_event"): ("current_event_not_published",),
    ("UNKNOWN", "correction_chain_integrity"): ("correction_chain_integrity",),
    ("NOT_COVERED", "no_verified_revisions"): ("revision_history_empty",),
    ("UNKNOWN", "missing_decision_clock"): ("missing_decision_clock",),
    ("COVERED", "verified_revision_chain"): (),
    ("UNKNOWN", "unresolved_clock_tie"): ("unresolved_clock_tie",),
    ("COVERED", "complete_allowlisted_owner_packet"): (),
    ("PARTIAL", "partial_allowlisted_owner_packet"): (),
    ("UNKNOWN", "exact_source_lineage_unavailable"): (),
}
_MAX_REVENUE = 1_000_000_000_000_000
_MIN_GUIDANCE_PCT = -100.0
_MAX_GUIDANCE_PCT = 1_000.0
_REVENUE_UNITS = frozenset({"USD", "usd_millions"})
_REVISION_CHAIN_BOUND_DISCLOSURE = (
    "CALLER_INJECTED_READER_BOUND; OWNER_DEFAULT_MAX_HOPS=500"
)


class IntelligenceVectorContractError(ValueError):
    """The D5 projection is not the closed, all-false v1 contract."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _content_id(prefix: str, value: Any) -> str:
    return f"{prefix}:{sha256(_canonical_bytes(value)).hexdigest()}"


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, bool)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if len(text) <= 128 and not _URL_RE.search(text) and not _PATH_RE.search(text):
            return text
        return None
    if isinstance(value, float) and value == value and value not in (float("inf"), float("-inf")):
        return value
    return None


def _sanitize_error_message(message: str) -> str:
    sanitized = _CREDENTIAL_RE.sub("[redacted-credential]", str(message))
    sanitized = _STORAGE_LOCATOR_RE.sub("[redacted-locator]", sanitized)
    sanitized = _URL_RE.sub("[redacted-url]", sanitized)
    sanitized = _NON_HTTP_URI_RE.sub("[redacted-locator]", sanitized)
    sanitized = _ARN_RE.sub("[redacted-locator]", sanitized)
    sanitized = _UNC_PATH_RE.sub("[redacted-path]", sanitized)
    sanitized = _WINDOWS_PATH_RE.sub("[redacted-path]", sanitized)
    sanitized = _PATH_RE.sub("[redacted-path]", sanitized)
    sanitized = "".join(character if character.isprintable() else " " for character in sanitized)
    return " ".join(sanitized.split())[:500]


def _safe_object_id(value: Any) -> str | None:
    text = str(value or "").strip()
    lowered = text.lower()
    if (
        not _OBJECT_ID_RE.fullmatch(text)
        or ":::" in text
        or any(marker in lowered for marker in ("arn:", "s3:", "gs:", "file:", "http:"))
    ):
        return None
    return text


def _bounded_number(
    value: Any, *, minimum: float, maximum: float,
) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and (
        value != value or value in (float("inf"), float("-inf"))
    ):
        return None
    if value < minimum or value > maximum:
        return None
    return value


def _episode_known_at(episode: Mapping[str, Any]) -> str | None:
    value = episode.get("_d5_episode_known_at")
    return str(value) if _parse_time(value) is not None else None


def _validate_b1_episode_identity(episode: Mapping[str, Any]) -> None:
    raw_episode_id = str(episode.get("episode_id") or "")
    match = _B1_EPISODE_ID_RE.fullmatch(raw_episode_id)
    if match is None:
        raise IntelligenceVectorContractError(
            "episode_id must have canonical B1 candidate-episode shape"
        )
    try:
        expected = b1_episode_id(
            str(episode.get("security_id") or ""),
            str(episode.get("identity_epoch") or ""),
            _as_mapping(episode.get("structural_anchor")),
            int(match.group("generation")),
        )
    except EpisodeContractError as exc:
        raise IntelligenceVectorContractError(
            "episode_id must bind canonical B1 security, epoch, and structural anchor"
        ) from exc
    if raw_episode_id != expected:
        raise IntelligenceVectorContractError(
            "episode_id does not match canonical B1 episode identity"
        )


def _is_canonical_b1_episode_ref_id(value: Any) -> bool:
    match = _B1_EPISODE_ID_RE.fullmatch(str(value or ""))
    if match is None:
        return False
    try:
        kind, listing = parse_dataos_id(match.group("security"))
    except IssuerIdentityError:
        return False
    return (
        kind == "security"
        and dataos_security_id(listing) == match.group("security")
    )


def _validate_owner_workspace_binding(
    revision: Mapping[str, Any], *, event_id: str, earnings_company_id: str,
) -> Mapping[str, Any]:
    workspace = revision.get("workspace")
    if not isinstance(workspace, Mapping):
        raise IntelligenceVectorContractError(
            "owner workspace binding requires a workspace body"
        )
    if workspace.get("schema") != "event_workspace.v1":
        raise IntelligenceVectorContractError(
            "owner workspace schema must be event_workspace.v1"
        )
    expected_cik = _EARNINGS_COMPANY_ID_RE.fullmatch(earnings_company_id)
    requested_event = _EVENT_CIK_RE.match(event_id)
    workspace_event_id = str(workspace.get("event_id") or "")
    workspace_event = _EVENT_CIK_RE.match(workspace_event_id)
    if (
        expected_cik is None
        or requested_event is None
        or workspace_event is None
        or requested_event.group("cik") != expected_cik.group("cik")
        or workspace_event.group("cik") != expected_cik.group("cik")
        or workspace_event_id != event_id
    ):
        raise IntelligenceVectorContractError(
            "owner workspace event binding disagrees with requested event or resolved CIK"
        )
    if _as_mapping(workspace.get("issuer")).get("company_id") != earnings_company_id:
        raise IntelligenceVectorContractError(
            "owner workspace issuer binding disagrees with resolved CIK"
        )
    if (
        not isinstance(revision.get("generation_id"), str)
        or _WORKSPACE_GENERATION_RE.fullmatch(revision["generation_id"]) is None
        or workspace.get("generation_id") != revision.get("generation_id")
    ):
        raise IntelligenceVectorContractError(
            "owner workspace generation binding disagrees with revision receipt"
        )
    lifecycle = workspace.get("lifecycle")
    if not isinstance(lifecycle, Mapping) or any(
        revision.get(clock_name) != lifecycle.get(clock_name)
        for clock_name in ("source_available_at", "observed_at")
    ):
        raise IntelligenceVectorContractError(
            "owner revision receipt clock disagrees with workspace lifecycle clock"
        )
    return workspace


def _clock(
    *, state: str, value: str | None, basis: str, source_ref_ids: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "state": state,
        "value": value,
        "interval": None,
        "precision": "INSTANT" if state == "ASSERTED" and value is not None else "UNKNOWN",
        "basis": basis,
        "source_ref_ids": list(source_ref_ids),
    }


def _point_in_time(
    episode: Mapping[str, Any], *, clocks: Mapping[str, Any] | None = None,
    decision_admissibility: str = "UNKNOWN", missing_clocks: Sequence[str] = (),
    corrected_at: str | None = None, corrected_ref_ids: Sequence[str] = (),
) -> dict[str, Any]:
    native = clocks or {}
    source_published = native.get("source_available_at")
    known = native.get("observed_at")
    computed = native.get("generated_at")
    asserted_source_clock = any(
        _parse_time(value) is not None
        for value in (source_published, known, computed)
    )
    return {
        "basis": "SOURCE_VINTAGE" if asserted_source_clock else "UNKNOWN",
        "decision_admissibility": decision_admissibility,
        "missing_clocks": list(missing_clocks),
        "source_effective_at": _clock(
            state="NOT_ASSERTED", value=None,
            basis="earnings_owner_asserts_no_effective_clock_for_results",
        ),
        "source_published_at": _clock(
            state="ASSERTED" if _parse_time(source_published) is not None else "UNKNOWN",
            value=source_published if _parse_time(source_published) is not None else None,
            basis="event_workspace.lifecycle.source_available_at",
        ),
        "known_at": _clock(
            state="ASSERTED" if _parse_time(known) is not None else "UNKNOWN",
            value=known if _parse_time(known) is not None else None,
            basis="event_workspace.lifecycle.observed_at",
        ),
        "captured_at": _clock(
            state="NOT_ASSERTED", value=None,
            basis="per_source_system_recorded_at_not_exposed_by_revision_receipt",
        ),
        "computed_at": _clock(
            state="ASSERTED" if _parse_time(computed) is not None else "UNKNOWN",
            value=computed if _parse_time(computed) is not None else None,
            basis="event_workspace.generated_at",
        ),
        "corrected_at": _clock(
            state="ASSERTED" if _parse_time(corrected_at) is not None else "NOT_ASSERTED",
            value=corrected_at if _parse_time(corrected_at) is not None else None,
            basis="later_event_workspace.generated_at" if corrected_at else "no_later_visible_source_revision",
            source_ref_ids=corrected_ref_ids,
        ),
        "decision_at": _clock(
            state="ASSERTED", value=str(episode.get("opened_at") or ""),
            basis="prophet.candidate_episode.opened_at",
        ),
    }


def _base_family(*, episode: Mapping[str, Any], identity_state: str, earnings_company_id: str | None) -> dict[str, Any]:
    subject_binding = {
        "state": identity_state,
        "episode_company_id": str(episode.get("company_id") or ""),
        "earnings_company_id": earnings_company_id,
        "owner_subject_id": None,
    }
    return {
        "family_projection_id": "",
        "evidence_family_id": EARNINGS_FAMILY_ID,
        "family_contract_version": FAMILY_CONTRACT_VERSION,
        "owner_ref": "company_intelligence.event_workspace/v1",
        "subject_binding": subject_binding,
        "semantic_head_ids": ["event_expectation"],
        "method_version": ADAPTER_SET_VERSION,
        "point_in_time": _point_in_time(episode),
        "applicability": {"state": "APPLICABLE", "basis": "earnings_results_event"},
        "coverage": {"state": "UNKNOWN", "basis": "not_evaluated"},
        "freshness": {"state": "UNKNOWN", "basis": "owner_has_no_staleness_clock"},
        "rights": {"state": "ALLOWED", "profile_ref": "event_workspace.v1:derived_only"},
        "identity_state": identity_state,
        "quality": {"flags": []},
        "source_refs": [],
        "evidence_roots": [],
        "observations": [],
        "explanation_facts": [],
        "trajectory": {"state": "NOT_APPLICABLE", "dimensions": []},
        "correction": {
            "state_at_decision": "NONE",
            "decision_version_ref_ids": [],
            "later_correction_ref_ids": [],
            "current_state": "UNKNOWN",
        },
        "calibration": {"state": "NOT_APPLICABLE", "registration_ref": None},
        "fusion_bindings": [],
        "authority": dict(ALL_FALSE_AUTHORITY),
        "owner_warnings": [],
    }


def _source_document_id(item: Mapping[str, Any]) -> str | None:
    return _safe_object_id(_as_mapping(item.get("source_span")).get("document_id"))


def _candidate_fact(workspace: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]] | None:
    accepted: list[tuple[int, Mapping[str, Any]]] = []
    for index, fact in enumerate(_as_list(workspace.get("facts"))):
        if not isinstance(fact, Mapping) or fact.get("metric") != "revenue":
            continue
        if (
            fact.get("unit") in _REVENUE_UNITS
            and _bounded_number(
                fact.get("value"), minimum=0, maximum=_MAX_REVENUE,
            ) is not None
            and fact.get("basis") in {"reported", "gaap"}
        ):
            accepted.append((index, fact))
    return accepted[0] if len(accepted) == 1 else None


def _accepted_fact(workspace: Mapping[str, Any]) -> tuple[int, Mapping[str, Any], str] | None:
    candidate = _candidate_fact(workspace)
    if candidate is None:
        return None
    index, fact = candidate
    document_id = _source_document_id(fact)
    return (index, fact, document_id) if document_id is not None else None


def _candidate_guidance(
    workspace: Mapping[str, Any],
) -> tuple[int, Mapping[str, Any]] | None:
    accepted: list[tuple[int, Mapping[str, Any]]] = []
    for index, guidance in enumerate(_as_list(workspace.get("guidance"))):
        if not isinstance(guidance, Mapping) or guidance.get("metric") != "revenue_yoy_pct":
            continue
        low = _bounded_number(
            guidance.get("low"), minimum=_MIN_GUIDANCE_PCT, maximum=_MAX_GUIDANCE_PCT,
        )
        high = _bounded_number(
            guidance.get("high"), minimum=_MIN_GUIDANCE_PCT, maximum=_MAX_GUIDANCE_PCT,
        )
        if (
            guidance.get("unit") == "percent"
            and guidance.get("status") in _GUIDANCE_STATES
            and low is not None and high is not None and low <= high
        ):
            accepted.append((index, guidance))
    return accepted[0] if len(accepted) == 1 else None


def _accepted_guidance(
    workspace: Mapping[str, Any],
) -> tuple[int, Mapping[str, Any], str] | None:
    candidate = _candidate_guidance(workspace)
    if candidate is None:
        return None
    index, guidance = candidate
    document_id = _source_document_id(guidance)
    return (index, guidance, document_id) if document_id is not None else None


def _delta_absence(value: Any) -> dict[str, str] | None:
    item = _as_mapping(value)
    reason = str(item.get("reason") or "")
    state = str(item.get("state") or (
        "absent" if item.get("schema") == "typed_absence.v1" else ""
    )).lower()
    if state != "absent" or reason not in _DELTA_ABSENCE_REASONS:
        return None
    return {"state": "ABSENT", "reason": reason}


def _candidate_delta(workspace: Mapping[str, Any]) -> tuple[int, dict[str, Any]] | None:
    fact_row = _candidate_fact(workspace)
    if fact_row is None:
        return None
    _fact_index, fact = fact_row
    accepted: list[tuple[int, dict[str, Any]]] = []
    for index, delta in enumerate(_as_list(workspace.get("deltas"))):
        if (
            not isinstance(delta, Mapping)
            or delta.get("schema") != "metric_delta.v1"
            or delta.get("metric") != "revenue"
            or delta.get("basis_match") is not False
        ):
            continue
        current = _as_mapping(delta.get("current"))
        current_value = _bounded_number(
            current.get("value"), minimum=0, maximum=_MAX_REVENUE,
        )
        prior = _delta_absence(delta.get("prior"))
        consensus = _delta_absence(delta.get("consensus"))
        if (
            current_value is None
            or current.get("unit") not in _REVENUE_UNITS
            or current.get("basis") not in {"reported", "gaap"}
            or current_value != fact.get("value")
            or current.get("unit") != fact.get("unit")
            or current.get("basis") != fact.get("basis")
            or prior is None
            or consensus is None
        ):
            continue
        accepted.append((index, {
            "schema": "metric_delta.v1",
            "metric": "revenue",
            "current": {
                "value": current_value,
                "unit": current["unit"],
                "basis": current["basis"],
            },
            "prior": prior,
            "consensus": consensus,
            "basis_match": False,
        }))
    return accepted[0] if len(accepted) == 1 else None


def _accepted_delta(workspace: Mapping[str, Any]) -> tuple[int, dict[str, Any], str] | None:
    candidate = _candidate_delta(workspace)
    fact_row = _accepted_fact(workspace)
    if candidate is None or fact_row is None:
        return None
    index, delta = candidate
    _fact_index, _fact, document_id = fact_row
    return index, delta, document_id


def _owner_allowlisted_lane_count(workspace: Mapping[str, Any]) -> int:
    return sum(
        candidate is not None
        for candidate in (
            _candidate_fact(workspace),
            _candidate_guidance(workspace),
            _candidate_delta(workspace),
        )
    )


def _adapted_field_paths(workspace: Mapping[str, Any]) -> dict[str, list[str]]:
    paths: dict[str, set[str]] = {}
    fact = _accepted_fact(workspace)
    if fact is not None:
        index, _item, document_id = fact
        paths.setdefault(document_id, set()).update({
            f"facts[{index}].metric", f"facts[{index}].unit",
            f"facts[{index}].value", f"facts[{index}].basis",
        })
    guidance = _accepted_guidance(workspace)
    if guidance is not None:
        index, _item, document_id = guidance
        paths.setdefault(document_id, set()).update({
            f"guidance[{index}].metric", f"guidance[{index}].low",
            f"guidance[{index}].high", f"guidance[{index}].unit",
            f"guidance[{index}].status",
        })
    delta = _accepted_delta(workspace)
    if delta is not None:
        index, _item, document_id = delta
        raw = _as_mapping(_as_list(workspace.get("deltas"))[index])
        fields = {
            f"deltas[{index}].metric", f"deltas[{index}].basis_match",
            f"deltas[{index}].current.value", f"deltas[{index}].current.unit",
            f"deltas[{index}].current.basis",
        }
        for side in ("prior", "consensus"):
            side_item = _as_mapping(raw.get(side))
            for key in ("schema", "state", "reason"):
                if key in side_item:
                    fields.add(f"deltas[{index}].{side}.{key}")
        paths.setdefault(document_id, set()).update(fields)
    return {document_id: sorted(field_paths) for document_id, field_paths in paths.items()}


def _source_refs(
    workspace: Mapping[str, Any], generation_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    refs: list[dict[str, Any]] = []
    roots: list[dict[str, Any]] = []
    field_paths_by_document = _adapted_field_paths(workspace)
    source_schemas = {
        "issuer_release": "event_workspace.source/issuer_release",
        "transcript": "event_workspace.source/transcript",
    }
    for raw_source in _as_list(workspace.get("sources")):
        if not isinstance(raw_source, Mapping):
            continue
        object_id = _safe_object_id(raw_source.get("document_id"))
        object_schema = source_schemas.get(str(raw_source.get("kind") or ""))
        field_paths = field_paths_by_document.get(str(object_id or ""))
        if object_id is None or object_schema is None or not field_paths:
            continue
        source_hash = raw_source.get("source_sha256")
        semantic = {
            "owner_namespace": "company_intelligence",
            "object_schema": object_schema,
            "object_id": object_id,
            "version_or_generation": generation_id,
            "content_hash": source_hash if isinstance(source_hash, str) and _HASH_RE.fullmatch(source_hash) else None,
            "field_paths": field_paths,
            "render_policy": "DERIVED_ONLY",
        }
        source_ref_id = _content_id("src", semantic)
        source_ref = {"source_ref_id": source_ref_id, **semantic}
        root_semantic = {"source_ref_id": source_ref_id, "root_type": "DOCUMENT_VERSION"}
        root_id = _content_id("er", root_semantic)
        refs.append(source_ref)
        roots.append({
            "evidence_root_id": root_id,
            "source_ref_id": source_ref_id,
            "root_type": root_semantic["root_type"],
        })
    refs_by_id = {item["source_ref_id"]: item for item in refs}
    roots_by_id = {item["evidence_root_id"]: item for item in roots}
    return (
        [refs_by_id[key] for key in sorted(refs_by_id)],
        [roots_by_id[key] for key in sorted(roots_by_id)],
    )


def _dependence_group_id(root_ids: Sequence[str]) -> str:
    return _content_id("edg", {
        "relation": "COMMON_INFORMATION_ORIGIN",
        "basis": "CONTRACT_RULE",
        "basis_refs": sorted(root_ids),
    })


def _observation(
    *, native_metric_id: str, value: Any, units: Any,
    source_ref_ids: list[str], root_ids: list[str], dependence_group_ids: list[str],
    correction_lineage_state: str, quality_flags: list[str] | None = None,
    value_state: str = "PRESENT", absence_reasons: list[str] | None = None,
) -> dict[str, Any] | None:
    if value_state == "ABSENT":
        clean_value = None
    elif isinstance(value, Mapping):
        clean_value = {"low": _scalar(value.get("low")), "high": _scalar(value.get("high"))}
        if clean_value["low"] is None and clean_value["high"] is None:
            return None
    else:
        clean_value = _scalar(value)
        if clean_value is None:
            return None
    semantic = {
        "native_metric_id": native_metric_id,
        "value_state": value_state,
        "value": clean_value,
        "units": _scalar(units),
        "method_class": "ADAPTER_MECHANICAL_PROJECTION",
        "method_version": ADAPTER_SET_VERSION,
        "source_ref_ids": sorted(set(source_ref_ids)),
        "evidence_root_ids": sorted(set(root_ids)),
        "economic_dependence_group_ids": sorted(set(dependence_group_ids)),
        "quality_flags": sorted(set(quality_flags or [])),
        "absence_reasons": sorted(set(absence_reasons or [])),
        "neutral_definition_ref": None,
        "correction_lineage_state": correction_lineage_state,
    }
    return {"observation_id": _content_id("obs", semantic), **semantic}


def _lineage_for_document(
    document_id: str, *, source_refs: Sequence[Mapping[str, Any]],
    evidence_roots: Sequence[Mapping[str, Any]],
) -> tuple[list[str], list[str]]:
    source_ids = sorted(
        str(item["source_ref_id"])
        for item in source_refs
        if item.get("object_id") == document_id
    )
    root_ids = sorted(
        str(item["evidence_root_id"])
        for item in evidence_roots
        if item.get("source_ref_id") in source_ids
    )
    return source_ids, root_ids


def _observations(
    workspace: Mapping[str, Any], *, source_refs: list[dict[str, Any]],
    evidence_roots: list[dict[str, Any]], dependence_group_ids: list[str],
    correction_lineage_state: str,
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    fact_row = _accepted_fact(workspace)
    if fact_row is not None:
        _index, fact, document_id = fact_row
        source_ref_ids, root_ids = _lineage_for_document(
            document_id, source_refs=source_refs, evidence_roots=evidence_roots,
        )
        item = _observation(
            native_metric_id="fact:revenue", value=fact.get("value"),
            units=fact.get("unit"), source_ref_ids=source_ref_ids, root_ids=root_ids,
            dependence_group_ids=dependence_group_ids,
            correction_lineage_state=correction_lineage_state,
        )
        if item is not None and source_ref_ids and root_ids:
            observations.append(item)
    guidance_row = _accepted_guidance(workspace)
    if guidance_row is not None:
        _index, guidance, document_id = guidance_row
        source_ref_ids, root_ids = _lineage_for_document(
            document_id, source_refs=source_refs, evidence_roots=evidence_roots,
        )
        guidance_status = str(guidance.get("status") or "")
        item = _observation(
            native_metric_id="guidance:revenue_yoy_pct",
            value={"low": guidance.get("low"), "high": guidance.get("high")},
            units=guidance.get("unit"), source_ref_ids=source_ref_ids, root_ids=root_ids,
            dependence_group_ids=dependence_group_ids,
            correction_lineage_state=correction_lineage_state,
            quality_flags=[f"status:{guidance_status}"],
        )
        if item is not None and source_ref_ids and root_ids:
            observations.append(item)
    return sorted(observations, key=lambda item: (item["native_metric_id"], item["observation_id"]))


def _trajectory(
    workspace: Mapping[str, Any], *, source_refs: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    delta_row = _accepted_delta(workspace)
    if delta_row is None:
        return {"state": "NOT_APPLICABLE", "dimensions": []}
    _index, delta, document_id = delta_row
    source_ref_ids, _root_ids = _lineage_for_document(
        document_id, source_refs=source_refs, evidence_roots=[],
    )
    revenue_observation_ids = sorted(
        str(item["observation_id"])
        for item in observations
        if item.get("native_metric_id") == "fact:revenue"
    )
    if not source_ref_ids or not revenue_observation_ids:
        return {"state": "NOT_APPLICABLE", "dimensions": []}
    return {
        "state": "PARTIAL",
        "dimensions": [{
            "dimension": "REVISION_CHANGE",
            "state": "PARTIAL",
            "native_metric_id": "metric_delta:revenue",
            "value": delta,
            "units": delta["current"]["unit"],
            "window": None,
            "cadence": "EVENT_NATIVE",
            "method_version": "metric_delta.v1",
            "reference_observation_ids": revenue_observation_ids,
            "source_ref_ids": source_ref_ids,
        }],
    }


def _absence_observation(
    *, reason_ids: Sequence[str], correction_lineage_state: str = "NOT_OBSERVABLE",
    source_ref_ids: Sequence[str] = (), root_ids: Sequence[str] = (),
) -> dict[str, Any]:
    result = _observation(
        native_metric_id="earnings:event_workspace",
        value=None,
        units=None,
        source_ref_ids=list(source_ref_ids),
        root_ids=list(root_ids),
        dependence_group_ids=[],
        correction_lineage_state=correction_lineage_state,
        value_state="ABSENT",
        absence_reasons=list(reason_ids),
    )
    assert result is not None
    return result


def _finish_family(family: dict[str, Any]) -> dict[str, Any]:
    semantic = {key: deepcopy(value) for key, value in family.items() if key != "family_projection_id"}
    family["family_projection_id"] = _content_id("pif", semantic)
    return family


def _build_envelope(
    *, episode: Mapping[str, Any], episode_generation_id: str, family: dict[str, Any],
    dependence_groups: list[dict[str, Any]], event_id: str | None,
    errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    opened_at = str(episode.get("opened_at") or "")
    anchor = _as_mapping(episode.get("structural_anchor"))
    envelope: dict[str, Any] = {
        "schema": SCHEMA_INTELLIGENCE_VECTOR,
        "projection_id": "",
        "episode_ref": {
            "schema": str(episode.get("schema") or ""),
            "episode_id": str(episode.get("episode_id") or ""),
            "generation_id": episode_generation_id,
            "identity_ref": str(episode.get("company_id") or ""),
        },
        "decision_cut": {
            "opened_at": opened_at,
            "opened_session": str(episode.get("opened_session") or ""),
            "anchor_time": anchor.get("time"),
            "known_at": _episode_known_at(episode),
            "tradable_at": {
                "state": "NOT_ASSERTED",
                "value": None,
                "basis": "no_us_availability_owner_and_b4_not_built",
            },
        },
        "adapter_set_version": ADAPTER_SET_VERSION,
        "evidence_families": [_finish_family(family)],
        "economic_dependence_groups": dependence_groups,
        "semantic_heads": [{
            "semantic_head_id": "event_expectation",
            "family_projection_ids": [family["family_projection_id"]],
        }],
        "fusion_bindings": [],
        "authority": dict(ALL_FALSE_AUTHORITY),
        "assembly_receipt": {
            "adapter": ADAPTER_SET_VERSION,
            "assembled_at": None,
            "source_reader": "read_event_source_revisions",
            "event_discovery_scope": "CURRENT_GENERATION_ONLY",
            "historical_event_set_reconstruction": False,
            "identity_resolution_scope": "CURRENT_REGISTRANT_ONLY",
            "revision_visibility_scope": "ISSUER_RELEASE_SOURCE_HASH_ONLY",
            "revision_chain_bound_disclosure": _REVISION_CHAIN_BOUND_DISCLOSURE,
            "event_id": event_id,
            "errors": errors or [],
        },
    }
    semantic = {key: deepcopy(value) for key, value in envelope.items() if key not in {"projection_id", "assembly_receipt"}}
    envelope["projection_id"] = _content_id("piv", semantic)
    validate_intelligence_vector(envelope)
    return envelope


def build_earnings_intelligence_vector(
    *,
    episode: Mapping[str, Any],
    episode_generation_id: str,
    episode_known_at: str,
    issuer_master: Any,
    find_event_id: Callable[[str], str | None] = find_current_event_id_for_company,
    read_revisions: Callable[[str], Sequence[Mapping[str, Any]]] = read_event_source_revisions,
) -> dict[str, Any]:
    """Build one closed Earnings family for an exact B1 episode generation.

    Both external reads are injectable for deterministic tests. Identity is
    always resolved first. Only after a CIK-backed Earnings company id exists
    does current-generation event discovery run.
    """
    if not isinstance(episode, Mapping):
        raise IntelligenceVectorContractError("episode must be an object")
    if not _PEG_RE.fullmatch(str(episode_generation_id or "")):
        raise IntelligenceVectorContractError("episode generation must be peg:<64 lowercase hex>")
    if str(episode.get("schema") or "") != "prophet.candidate_episode/v1":
        raise IntelligenceVectorContractError("episode schema mismatch")
    _validate_b1_episode_identity(episode)
    if _parse_time(episode_known_at) is None:
        raise IntelligenceVectorContractError("episode_known_at must come from the B1 event stream")
    episode = {**episode, "_d5_episode_known_at": episode_known_at}
    cut = _parse_time(episode.get("opened_at"))
    if cut is None:
        raise IntelligenceVectorContractError("episode opened_at decision cut is missing or invalid")
    known_at = _parse_time(episode_known_at)
    if known_at is None:
        raise IntelligenceVectorContractError("episode known_at is invalid")
    anchor_time = _parse_time(_as_mapping(episode.get("structural_anchor")).get("time"))
    if anchor_time is None:
        raise IntelligenceVectorContractError("episode anchor_time is invalid")
    if cut != max(anchor_time, known_at):
        raise IntelligenceVectorContractError(
            "episode opened_at must equal the exact B1 decision cut max(anchor.time, known_at)"
        )

    episode_company_id = str(episode.get("company_id") or "")
    earnings_company_id: str | None = None
    identity_ambiguous = False
    try:
        cik = issuer_master.cik_of_issuer(episode_company_id)
        if cik is not None:
            earnings_company_id = company_id_for_cik(cik)
    except IssuerIdentityError:
        identity_ambiguous = True
    except EarningsIdentityError:
        earnings_company_id = None

    if earnings_company_id is None:
        state = "AMBIGUOUS" if identity_ambiguous else "UNRESOLVED"
        family = _base_family(episode=episode, identity_state=state, earnings_company_id=None)
        reason = "CONFLICTED" if identity_ambiguous else "IDENTITY_UNRESOLVED"
        family["coverage"] = {"state": "UNKNOWN", "basis": f"canonical_identity_{state.lower()}"}
        family["quality"] = {"flags": [f"identity_{state.lower()}"]}
        family["observations"] = [_absence_observation(reason_ids=[reason])]
        if identity_ambiguous:
            family["correction"]["state_at_decision"] = "CONFLICTED"
            family["correction"]["current_state"] = "CONFLICTED"
        return _build_envelope(
            episode=episode, episode_generation_id=episode_generation_id, family=family,
            dependence_groups=[], event_id=None,
        )

    family = _base_family(
        episode=episode, identity_state="RESOLVED", earnings_company_id=earnings_company_id,
    )
    try:
        event_id = find_event_id(earnings_company_id)
    except WorkspaceChainIntegrityError as exc:
        family["coverage"] = {"state": "UNKNOWN", "basis": "current_manifest_integrity_failure"}
        family["point_in_time"] = _point_in_time(
            episode, decision_admissibility="UNVERIFIABLE",
        )
        family["quality"] = {"flags": ["correction_chain_integrity"]}
        family["correction"] = {
            "state_at_decision": "PENDING",
            "decision_version_ref_ids": [],
            "later_correction_ref_ids": [],
            "current_state": "UNKNOWN",
        }
        family["observations"] = [_absence_observation(
            reason_ids=["UNESTIMABLE", "CORRECTION_PENDING"],
        )]
        error = {"type": "WorkspaceChainIntegrityError", "message": _sanitize_error_message(str(exc))}
        return _build_envelope(
            episode=episode, episode_generation_id=episode_generation_id, family=family,
            dependence_groups=[], event_id=None, errors=[error],
        )
    except WorkspaceChainNotPublished:
        event_id = None
    except CompanyIntelligenceReadError as exc:
        family["coverage"] = {"state": "UNKNOWN", "basis": "source_fetch_failed"}
        family["quality"] = {"flags": ["source_unavailable"]}
        family["observations"] = [_absence_observation(reason_ids=["SOURCE_UNAVAILABLE"])]
        error = {"type": "CompanyIntelligenceReadError", "message": _sanitize_error_message(str(exc))}
        return _build_envelope(
            episode=episode, episode_generation_id=episode_generation_id, family=family,
            dependence_groups=[], event_id=None, errors=[error],
        )
    if event_id is None:
        family["coverage"] = {"state": "NOT_COVERED", "basis": "no_current_generation_event"}
        family["quality"] = {"flags": ["current_event_not_published"]}
        family["observations"] = [_absence_observation(reason_ids=["NOT_COVERED"])]
        return _build_envelope(
            episode=episode, episode_generation_id=episode_generation_id, family=family,
            dependence_groups=[], event_id=None,
        )

    family["subject_binding"]["owner_subject_id"] = event_id

    try:
        revisions = list(read_revisions(event_id))
    except WorkspaceChainIntegrityError as exc:
        family["coverage"] = {"state": "UNKNOWN", "basis": "correction_chain_integrity"}
        family["point_in_time"] = _point_in_time(
            episode, decision_admissibility="UNVERIFIABLE",
        )
        family["quality"] = {"flags": ["correction_chain_integrity"]}
        family["correction"] = {
            "state_at_decision": "PENDING",
            "decision_version_ref_ids": [],
            "later_correction_ref_ids": [],
            "current_state": "UNKNOWN",
        }
        family["observations"] = [_absence_observation(
            reason_ids=["UNESTIMABLE", "CORRECTION_PENDING"],
        )]
        error = {
            "type": "WorkspaceChainIntegrityError",
            "message": _sanitize_error_message(str(exc)),
        }
        return _build_envelope(
            episode=episode, episode_generation_id=episode_generation_id, family=family,
            dependence_groups=[], event_id=event_id, errors=[error],
        )
    except WorkspaceChainNotPublished:
        revisions = []
    except CompanyIntelligenceReadError as exc:
        family["coverage"] = {"state": "UNKNOWN", "basis": "source_fetch_failed"}
        family["quality"] = {"flags": ["source_unavailable"]}
        family["observations"] = [_absence_observation(reason_ids=["SOURCE_UNAVAILABLE"])]
        error = {"type": "CompanyIntelligenceReadError", "message": _sanitize_error_message(str(exc))}
        return _build_envelope(
            episode=episode, episode_generation_id=episode_generation_id, family=family,
            dependence_groups=[], event_id=event_id, errors=[error],
        )

    if not revisions:
        family["coverage"] = {"state": "NOT_COVERED", "basis": "no_verified_revisions"}
        family["quality"] = {"flags": ["revision_history_empty"]}
        family["observations"] = [_absence_observation(reason_ids=["NOT_COVERED"])]
        return _build_envelope(
            episode=episode, episode_generation_id=episode_generation_id, family=family,
            dependence_groups=[], event_id=event_id,
        )

    missing: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for revision in revisions:
        if not isinstance(revision, Mapping):
            raise IntelligenceVectorContractError(
                "owner revision receipt must be an object"
            )
        workspace = _validate_owner_workspace_binding(
            revision, event_id=event_id, earnings_company_id=earnings_company_id,
        )
        clocks = {
            "source_available_at": revision.get("source_available_at"),
            "observed_at": revision.get("observed_at"),
            "generated_at": workspace.get("generated_at"),
        }
        parsed = {}
        for name, value in clocks.items():
            parsed[name] = _parse_time(value)
            if parsed[name] is None:
                missing.add(name)
        normalized.append({"revision": revision, "workspace": workspace, "clocks": clocks, "parsed": parsed})

    if missing:
        family["coverage"] = {"state": "UNKNOWN", "basis": "missing_decision_clock"}
        family["point_in_time"] = _point_in_time(
            episode, clocks=normalized[0]["clocks"], decision_admissibility="UNKNOWN",
            missing_clocks=sorted(missing),
        )
        family["quality"] = {"flags": ["missing_decision_clock"]}
        family["observations"] = [_absence_observation(reason_ids=["UNKNOWN"])]
        return _build_envelope(
            episode=episode, episode_generation_id=episode_generation_id, family=family,
            dependence_groups=[], event_id=event_id,
        )

    admissible = [
        item for item in normalized
        if item["parsed"]["source_available_at"] <= cut
        and item["parsed"]["observed_at"] <= cut
        and item["parsed"]["generated_at"] <= cut
    ]
    if not admissible:
        after_cut = any(any(clock > cut for clock in item["parsed"].values()) for item in normalized)
        family["coverage"] = {"state": "COVERED", "basis": "verified_revision_chain"}
        family["point_in_time"] = _point_in_time(
            episode, clocks=normalized[-1]["clocks"],
            decision_admissibility="AFTER_DECISION_CUT" if after_cut else "UNVERIFIABLE",
        )
        family["freshness"] = {"state": "UNKNOWN", "basis": "owner_has_no_staleness_clock"}
        family["quality"] = {"flags": []}
        family["observations"] = [_absence_observation(
            reason_ids=["NOT_CAPTURED_AT_DECISION" if after_cut else "UNKNOWN"],
            correction_lineage_state="NOT_OBSERVABLE",
        )]
        return _build_envelope(
            episode=episode, episode_generation_id=episode_generation_id, family=family,
            dependence_groups=[], event_id=event_id,
        )

    newest_source = max(item["parsed"]["source_available_at"] for item in admissible)
    source_tied = [item for item in admissible if item["parsed"]["source_available_at"] == newest_source]
    newest_observed = max(item["parsed"]["observed_at"] for item in source_tied)
    finalists = [item for item in source_tied if item["parsed"]["observed_at"] == newest_observed]
    if len(finalists) != 1:
        family["coverage"] = {"state": "UNKNOWN", "basis": "unresolved_clock_tie"}
        family["point_in_time"] = _point_in_time(
            episode, clocks=finalists[0]["clocks"], decision_admissibility="UNVERIFIABLE",
        )
        family["quality"] = {"flags": ["unresolved_clock_tie"]}
        family["correction"] = {
            "state_at_decision": "CONFLICTED",
            "decision_version_ref_ids": [],
            "later_correction_ref_ids": [],
            "current_state": "CONFLICTED",
        }
        family["observations"] = [_absence_observation(
            reason_ids=["CONFLICTED"], correction_lineage_state="OBSERVED",
        )]
        return _build_envelope(
            episode=episode, episode_generation_id=episode_generation_id, family=family,
            dependence_groups=[], event_id=event_id,
        )

    chosen = finalists[0]
    revision = chosen["revision"]
    workspace = chosen["workspace"]
    generation_id = str(revision.get("generation_id") or "")
    decision_refs, decision_roots = _source_refs(workspace, generation_id)
    source_ref_ids = sorted(ref["source_ref_id"] for ref in decision_refs)
    root_ids = sorted(root["evidence_root_id"] for root in decision_roots)

    decision_hashes = {
        item["revision"].get("source_sha256") for item in admissible
    }
    if None in decision_hashes:
        lineage_state = "NOT_OBSERVABLE"
    elif len(decision_hashes) > 1:
        lineage_state = "OBSERVED"
    else:
        lineage_state = "NONE_IN_CHAIN"
    later = sorted(
        [
            item for item in normalized
            if item is not chosen and any(item["parsed"][name] > cut for name in item["parsed"])
        ],
        key=lambda item: (
            item["parsed"]["source_available_at"],
            item["parsed"]["observed_at"],
            item["parsed"]["generated_at"],
            str(item["revision"].get("generation_id") or ""),
        ),
    )
    later_refs: list[dict[str, Any]] = []
    later_roots: list[dict[str, Any]] = []
    for item in later:
        revision_refs, revision_roots = _source_refs(
            item["workspace"], str(item["revision"].get("generation_id") or ""),
        )
        later_refs.extend(revision_refs)
        later_roots.extend(revision_roots)
    if later and not later_refs:
        # A later owner revision exists, but the adapter cannot project any
        # allowlisted source lineage from it.  Preserve that uncertainty in
        # the observation semantics so a readdressed packet cannot relabel
        # this builder-owned UNKNOWN outcome as CURRENT.
        lineage_state = "NOT_OBSERVABLE"

    all_refs_by_id = {
        ref["source_ref_id"]: ref for ref in decision_refs + later_refs
    }
    all_roots_by_id = {
        root["evidence_root_id"]: root for root in decision_roots + later_roots
    }
    all_refs = [all_refs_by_id[key] for key in sorted(all_refs_by_id)]
    all_roots = [all_roots_by_id[key] for key in sorted(all_roots_by_id)]
    dependence_group_id = _dependence_group_id(root_ids) if root_ids else ""
    dependence_ids = [dependence_group_id] if dependence_group_id else []
    family["source_refs"] = all_refs
    family["evidence_roots"] = all_roots
    family["observations"] = _observations(
        workspace,
        source_refs=decision_refs,
        evidence_roots=decision_roots,
        dependence_group_ids=dependence_ids,
        correction_lineage_state=lineage_state,
    )
    if not family["observations"]:
        family["observations"] = [_absence_observation(
            reason_ids=["UNKNOWN"],
            correction_lineage_state=lineage_state,
        )]
    family["trajectory"] = _trajectory(
        workspace, source_refs=decision_refs, observations=family["observations"],
    )
    groups = ([{
        "dependence_group_id": dependence_group_id,
        "relation": "COMMON_INFORMATION_ORIGIN",
        "member_observation_refs": sorted(
            item["observation_id"] for item in family["observations"]
            if item["value_state"] != "ABSENT"
        ),
        "basis": "CONTRACT_RULE",
        "basis_refs": sorted(root_ids),
    }] if dependence_group_id and any(
        item["value_state"] != "ABSENT" for item in family["observations"]
    ) else [])
    later_ref_ids = sorted({ref["source_ref_id"] for ref in later_refs})
    later_generation_ids = {
        ref["version_or_generation"] for ref in later_refs
    }
    referenced_later = [
        item for item in later
        if item["revision"].get("generation_id") in later_generation_ids
    ]
    corrected_at = (
        max(
            referenced_later,
            key=lambda item: item["parsed"]["generated_at"],
        )["clocks"]["generated_at"]
        if referenced_later else None
    )
    expected_lane_count = _owner_allowlisted_lane_count(workspace)
    projected_lane_count = len([
        item for item in family["observations"] if item["value_state"] == "PRESENT"
    ]) + (1 if family["trajectory"]["state"] == "PARTIAL" else 0)
    if expected_lane_count > 0 and projected_lane_count == expected_lane_count:
        family["coverage"] = {
            "state": "COVERED",
            "basis": "complete_allowlisted_owner_packet",
        }
    elif projected_lane_count > 0:
        family["coverage"] = {
            "state": "PARTIAL",
            "basis": "partial_allowlisted_owner_packet",
        }
    else:
        family["coverage"] = {
            "state": "UNKNOWN",
            "basis": "exact_source_lineage_unavailable",
        }
    family["point_in_time"] = _point_in_time(
        episode, clocks=chosen["clocks"], decision_admissibility="ADMISSIBLE",
        corrected_at=corrected_at, corrected_ref_ids=later_ref_ids,
    )
    family["freshness"] = {"state": "UNKNOWN", "basis": "owner_has_no_staleness_clock"}
    family["quality"] = {"flags": []}
    family["owner_warnings"] = sorted({
        str(warning) for warning in _as_list(workspace.get("warnings")) if warning in WORKSPACE_WARNINGS
    })

    family["correction"] = {
        "state_at_decision": "NONE",
        "decision_version_ref_ids": sorted(source_ref_ids),
        "later_correction_ref_ids": later_ref_ids,
        "current_state": (
            "UNKNOWN" if lineage_state == "NOT_OBSERVABLE" or not source_ref_ids
            else (
                "CORRECTED" if later_ref_ids
                else ("UNKNOWN" if later else "CURRENT")
            )
        ),
    }
    return _build_envelope(
        episode=episode, episode_generation_id=episode_generation_id, family=family,
        dependence_groups=groups, event_id=event_id,
    )


def _require_keys(value: Any, expected: frozenset[str], *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IntelligenceVectorContractError(f"{name} must be an object")
    keys = set(value)
    if keys != set(expected):
        raise IntelligenceVectorContractError(
            f"{name} closed keys mismatch: missing={sorted(set(expected) - keys)!r}, extra={sorted(keys - set(expected))!r}"
        )
    return value


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in _FORBIDDEN_KEYS:
                raise IntelligenceVectorContractError(f"forbidden closed-contract field: {key}")
            _reject_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden_keys(child)


def _validate_source_ref(value: Any) -> None:
    item = _require_keys(value, frozenset({
        "source_ref_id", "owner_namespace", "object_schema", "object_id",
        "version_or_generation", "content_hash", "field_paths", "render_policy",
    }), name="source_ref")
    if not str(item["source_ref_id"]).startswith("src:"):
        raise IntelligenceVectorContractError("source_ref_id invalid")
    if item["owner_namespace"] != "company_intelligence":
        raise IntelligenceVectorContractError("source_ref owner namespace invalid")
    if item["object_schema"] not in {
        "event_workspace.source/issuer_release", "event_workspace.source/transcript",
    }:
        raise IntelligenceVectorContractError("source_ref object schema invalid")
    if _safe_object_id(item["object_id"]) != item["object_id"]:
        raise IntelligenceVectorContractError("source_ref object_id leaks a private locator")
    if not re.fullmatch(r"[0-9a-f]{24,64}", str(item["version_or_generation"] or "")):
        raise IntelligenceVectorContractError("source_ref generation invalid")
    if item["content_hash"] is not None and not _HASH_RE.fullmatch(str(item["content_hash"])):
        raise IntelligenceVectorContractError("source_ref content_hash invalid")
    if (
        not isinstance(item["field_paths"], list)
        or not item["field_paths"]
        or item["field_paths"] != sorted(set(item["field_paths"]))
        or any(not isinstance(path, str) or not _FIELD_PATH_RE.fullmatch(path) for path in item["field_paths"])
    ):
        raise IntelligenceVectorContractError("source_ref field_paths outside Earnings allowlist")
    if item["object_schema"].endswith("issuer_release") and any(
        path.startswith("guidance[") for path in item["field_paths"]
    ):
        raise IntelligenceVectorContractError("issuer release cannot claim transcript guidance fields")
    if item["object_schema"].endswith("transcript") and any(
        not path.startswith("guidance[") for path in item["field_paths"]
    ):
        raise IntelligenceVectorContractError("transcript source claims non-guidance fields")
    if item["render_policy"] != "DERIVED_ONLY":
        raise IntelligenceVectorContractError("source_ref render policy invalid")
    semantic = {key: deepcopy(child) for key, child in item.items() if key != "source_ref_id"}
    if item["source_ref_id"] != _content_id("src", semantic):
        raise IntelligenceVectorContractError("source_ref_id content address mismatch")


def _validate_observation(value: Any) -> None:
    item = _require_keys(value, frozenset({
        "observation_id", "native_metric_id", "value_state", "value", "units",
        "method_class", "method_version", "source_ref_ids", "evidence_root_ids",
        "economic_dependence_group_ids", "quality_flags", "absence_reasons",
        "neutral_definition_ref", "correction_lineage_state",
    }), name="observation")
    if not str(item["observation_id"]).startswith("obs:"):
        raise IntelligenceVectorContractError("observation_id invalid")
    if item["method_class"] != "ADAPTER_MECHANICAL_PROJECTION":
        raise IntelligenceVectorContractError("D5 may originate only mechanical projections")
    if item["method_version"] != ADAPTER_SET_VERSION:
        raise IntelligenceVectorContractError("observation method_version invalid")
    if item["value_state"] not in {"PRESENT", "MEASURED_NEUTRAL", "ABSENT"}:
        raise IntelligenceVectorContractError("observation value_state invalid")
    allowed_absence = {
        "NOT_APPLICABLE", "NOT_COVERED", "SOURCE_UNAVAILABLE", "STALE",
        "UNESTIMABLE", "CORRECTION_PENDING", "NOT_CAPTURED_AT_DECISION",
        "UNKNOWN", "IDENTITY_UNRESOLVED", "CONFLICTED",
    }
    if any(reason not in allowed_absence for reason in item["absence_reasons"]):
        raise IntelligenceVectorContractError("Earnings absence reason is not mintable")
    if item["value_state"] == "ABSENT":
        if item["value"] is not None or not item["absence_reasons"]:
            raise IntelligenceVectorContractError("absent observation requires null value and a reason")
        if (
            item["native_metric_id"] != "earnings:event_workspace"
            or item["units"] is not None
            or item["source_ref_ids"]
            or item["evidence_root_ids"]
            or item["economic_dependence_group_ids"]
            or item["quality_flags"]
        ):
            raise IntelligenceVectorContractError("absent Earnings observation shape invalid")
    elif item["absence_reasons"]:
        raise IntelligenceVectorContractError("present observation cannot carry absence reasons")
    elif not item["source_ref_ids"] or not item["evidence_root_ids"]:
        raise IntelligenceVectorContractError("present observation requires source and root lineage")
    if item["absence_reasons"] != sorted(set(item["absence_reasons"])):
        raise IntelligenceVectorContractError("absence reasons must be sorted and unique")
    for list_name in (
        "source_ref_ids", "evidence_root_ids", "economic_dependence_group_ids",
        "quality_flags",
    ):
        if not isinstance(item[list_name], list) or item[list_name] != sorted(set(item[list_name])):
            raise IntelligenceVectorContractError(f"observation {list_name} must be sorted and unique")
    if item["correction_lineage_state"] not in {"OBSERVED", "NONE_IN_CHAIN", "NOT_OBSERVABLE"}:
        raise IntelligenceVectorContractError("correction_lineage_state invalid")
    if item["neutral_definition_ref"] is not None or item["value_state"] == "MEASURED_NEUTRAL":
        raise IntelligenceVectorContractError("Earnings adapter does not mint measured-neutral values")
    if item["value_state"] == "PRESENT" and item["native_metric_id"] == "fact:revenue":
        if (
            _bounded_number(item["value"], minimum=0, maximum=_MAX_REVENUE) is None
            or item["units"] not in _REVENUE_UNITS
            or item["quality_flags"] != []
        ):
            raise IntelligenceVectorContractError("fact:revenue metric value or bound invalid")
    elif item["value_state"] == "PRESENT" and item["native_metric_id"] == "guidance:revenue_yoy_pct":
        range_item = _require_keys(
            item["value"], frozenset({"low", "high"}), name="observation range",
        )
        low = _bounded_number(
            range_item["low"], minimum=_MIN_GUIDANCE_PCT, maximum=_MAX_GUIDANCE_PCT,
        )
        high = _bounded_number(
            range_item["high"], minimum=_MIN_GUIDANCE_PCT, maximum=_MAX_GUIDANCE_PCT,
        )
        allowed_flags = {f"status:{state}" for state in _GUIDANCE_STATES}
        if (
            low is None or high is None or low > high
            or item["units"] != "percent"
            or len(item["quality_flags"]) != 1
            or item["quality_flags"][0] not in allowed_flags
        ):
            raise IntelligenceVectorContractError("guidance metric value or bound invalid")
    elif item["value_state"] != "ABSENT":
        raise IntelligenceVectorContractError("native Earnings metric is outside the closed allowlist")
    semantic = {key: deepcopy(child) for key, child in item.items() if key != "observation_id"}
    if item["observation_id"] != _content_id("obs", semantic):
        raise IntelligenceVectorContractError("observation_id content address mismatch")


def _validate_clock(
    value: Any, *, name: str, expected_bases: frozenset[str],
) -> None:
    item = _require_keys(
        value,
        frozenset({"state", "value", "interval", "precision", "basis", "source_ref_ids"}),
        name=name,
    )
    if item["state"] not in {"ASSERTED", "NOT_ASSERTED", "NOT_APPLICABLE", "UNKNOWN"}:
        raise IntelligenceVectorContractError(f"{name} state invalid")
    if item["basis"] not in expected_bases:
        raise IntelligenceVectorContractError(f"{name} clock basis invalid")
    if item["state"] == "ASSERTED" and _parse_time(item["value"]) is None:
        raise IntelligenceVectorContractError(f"{name} asserted without a valid instant")
    if item["state"] != "ASSERTED" and item["value"] is not None:
        raise IntelligenceVectorContractError(f"{name} named-null state carries a value")
    expected_precision = "INSTANT" if item["state"] == "ASSERTED" else "UNKNOWN"
    if item["precision"] != expected_precision or item["interval"] is not None:
        raise IntelligenceVectorContractError(f"{name} precision or interval invalid")
    if (
        not isinstance(item["source_ref_ids"], list)
        or item["source_ref_ids"] != sorted(set(item["source_ref_ids"]))
    ):
        raise IntelligenceVectorContractError(f"{name} source refs must be sorted and unique")


def _validate_metric_delta(value: Any) -> None:
    item = _require_keys(value, frozenset({
        "schema", "metric", "current", "prior", "consensus", "basis_match",
    }), name="metric_delta trajectory value")
    if item["schema"] != "metric_delta.v1" or item["metric"] != "revenue":
        raise IntelligenceVectorContractError("trajectory metric_delta outside allowlist")
    if item["basis_match"] is not False:
        raise IntelligenceVectorContractError("trajectory basis_match must remain false")
    current = _require_keys(
        item["current"], frozenset({"value", "unit", "basis"}),
        name="metric_delta current",
    )
    if (
        _bounded_number(current["value"], minimum=0, maximum=_MAX_REVENUE) is None
        or current["unit"] not in _REVENUE_UNITS
        or current["basis"] not in {"reported", "gaap"}
    ):
        raise IntelligenceVectorContractError("trajectory current value invalid")
    for side_name in ("prior", "consensus"):
        side = _require_keys(
            item[side_name], frozenset({"state", "reason"}),
            name=f"metric_delta {side_name}",
        )
        if side["state"] != "ABSENT" or side["reason"] not in _DELTA_ABSENCE_REASONS:
            raise IntelligenceVectorContractError("trajectory typed absence invalid")


def validate_intelligence_vector(payload: Mapping[str, Any]) -> None:
    """Fail closed on unknown keys, authority, leakage, or content-id drift."""
    _reject_forbidden_keys(payload)
    item = _require_keys(payload, _TOP_KEYS, name="intelligence_vector")
    if item["schema"] != SCHEMA_INTELLIGENCE_VECTOR:
        raise IntelligenceVectorContractError("intelligence_vector schema mismatch")
    episode_ref = _require_keys(
        item["episode_ref"],
        frozenset({"schema", "episode_id", "generation_id", "identity_ref"}),
        name="episode_ref",
    )
    if episode_ref["schema"] != "prophet.candidate_episode/v1":
        raise IntelligenceVectorContractError("episode_ref schema mismatch")
    if (
        not _is_canonical_b1_episode_ref_id(episode_ref["episode_id"])
        or not str(episode_ref["identity_ref"] or "").startswith("ISS:")
    ):
        raise IntelligenceVectorContractError(
            "episode_ref requires canonical B1 episode_id and issuer identity"
        )
    if not _PEG_RE.fullmatch(str(episode_ref["generation_id"] or "")):
        raise IntelligenceVectorContractError("episode_ref generation invalid")
    if item["adapter_set_version"] != ADAPTER_SET_VERSION:
        raise IntelligenceVectorContractError("adapter_set_version invalid")
    decision_cut = _require_keys(
        item["decision_cut"],
        frozenset({"opened_at", "opened_session", "anchor_time", "known_at", "tradable_at"}),
        name="decision_cut",
    )
    tradable = _require_keys(
        decision_cut["tradable_at"], frozenset({"state", "value", "basis"}),
        name="decision_cut.tradable_at",
    )
    if tradable != {
        "state": "NOT_ASSERTED", "value": None,
        "basis": "no_us_availability_owner_and_b4_not_built",
    }:
        raise IntelligenceVectorContractError("tradable_at must remain NOT_ASSERTED")
    opened_at = _parse_time(decision_cut["opened_at"])
    known_at = _parse_time(decision_cut["known_at"])
    anchor_time = _parse_time(decision_cut["anchor_time"])
    if opened_at is None or known_at is None or anchor_time is None:
        raise IntelligenceVectorContractError("decision cut timestamps are invalid")
    if opened_at != max(anchor_time, known_at):
        raise IntelligenceVectorContractError(
            "opened_at must equal the exact B1 decision cut max(anchor.time, known_at)"
        )
    if decision_cut["opened_session"] != str(decision_cut["opened_at"])[:10]:
        raise IntelligenceVectorContractError("opened_session does not match opened_at")
    if item["authority"] != ALL_FALSE_AUTHORITY:
        raise IntelligenceVectorContractError("intelligence_vector authority must be all false")
    if item["fusion_bindings"] != []:
        raise IntelligenceVectorContractError("D5 fusion_bindings must be empty")
    families = item["evidence_families"]
    if not isinstance(families, list) or len(families) != 1:
        raise IntelligenceVectorContractError("D5 must emit exactly one evidence family")
    family = _require_keys(families[0], _FAMILY_KEYS, name="evidence_family")
    if family["evidence_family_id"] != EARNINGS_FAMILY_ID:
        raise IntelligenceVectorContractError("only earnings.event is allowed")
    if (
        family["family_contract_version"] != FAMILY_CONTRACT_VERSION
        or family["method_version"] != ADAPTER_SET_VERSION
        or family["owner_ref"] != "company_intelligence.event_workspace/v1"
    ):
        raise IntelligenceVectorContractError("Earnings family contract version invalid")
    if family["semantic_head_ids"] != ["event_expectation"]:
        raise IntelligenceVectorContractError("semantic head must be event_expectation")
    if family["authority"] != ALL_FALSE_AUTHORITY or family["fusion_bindings"] != []:
        raise IntelligenceVectorContractError("family authority must be all false and fusion empty")
    subject_binding = _require_keys(
        family["subject_binding"],
        frozenset({"state", "episode_company_id", "earnings_company_id", "owner_subject_id"}),
        name="subject_binding",
    )
    if family["identity_state"] not in {"RESOLVED", "AMBIGUOUS", "UNRESOLVED", "NOT_APPLICABLE"}:
        raise IntelligenceVectorContractError("identity_state invalid")
    if subject_binding["state"] != family["identity_state"]:
        raise IntelligenceVectorContractError("subject binding and identity_state disagree")
    if subject_binding["episode_company_id"] != episode_ref["identity_ref"]:
        raise IntelligenceVectorContractError("subject binding episode identity mismatch")
    owner_subject_id = subject_binding["owner_subject_id"]
    if owner_subject_id is not None and not _EVENT_ID_RE.fullmatch(str(owner_subject_id)):
        raise IntelligenceVectorContractError("owner subject event id invalid")
    if family["identity_state"] == "RESOLVED":
        earnings_match = _EARNINGS_COMPANY_ID_RE.fullmatch(
            str(subject_binding["earnings_company_id"] or "")
        )
        if earnings_match is None:
            raise IntelligenceVectorContractError(
                "resolved subject binding requires canonical ten-digit CIK"
            )
        event_match = (
            _EVENT_CIK_RE.match(str(owner_subject_id))
            if owner_subject_id is not None else None
        )
        if owner_subject_id is not None and (
            event_match is None
            or event_match.group("cik") != earnings_match.group("cik")
        ):
            raise IntelligenceVectorContractError(
                "resolved binding requires an owner event with the same CIK"
            )
    elif (
        subject_binding["earnings_company_id"] is not None
        or owner_subject_id is not None
    ):
        raise IntelligenceVectorContractError(
            "unresolved identity binding must retain null owner identifiers"
        )
    point_in_time = _require_keys(
        family["point_in_time"],
        frozenset({
            "basis", "decision_admissibility", "missing_clocks", "source_effective_at",
            "source_published_at", "known_at", "captured_at", "computed_at",
            "corrected_at", "decision_at",
        }),
        name="family.point_in_time",
    )
    if point_in_time["basis"] not in {"SOURCE_VINTAGE", "UNKNOWN", "LIVE_CAPTURED"}:
        raise IntelligenceVectorContractError("point_in_time basis invalid")
    if point_in_time["decision_admissibility"] not in {
        "ADMISSIBLE", "RESEARCH_ONLY_RECONSTRUCTION", "AFTER_DECISION_CUT",
        "UNVERIFIABLE", "UNKNOWN",
    }:
        raise IntelligenceVectorContractError("decision_admissibility invalid")
    for clock_name in (
        "source_effective_at", "source_published_at", "known_at", "captured_at",
        "computed_at", "corrected_at", "decision_at",
    ):
        _validate_clock(
            point_in_time[clock_name],
            name=f"family.point_in_time.{clock_name}",
            expected_bases=_CLOCK_BASES[clock_name],
        )
    if (
        not isinstance(point_in_time["missing_clocks"], list)
        or point_in_time["missing_clocks"] != sorted(set(point_in_time["missing_clocks"]))
        or any(
            name not in {"source_available_at", "observed_at", "generated_at"}
            for name in point_in_time["missing_clocks"]
        )
    ):
        raise IntelligenceVectorContractError("point_in_time missing_clocks invalid")
    if point_in_time["basis"] == "LIVE_CAPTURED" and point_in_time["captured_at"]["state"] != "ASSERTED":
        raise IntelligenceVectorContractError("LIVE_CAPTURED requires asserted captured_at")
    if point_in_time["basis"] == "SOURCE_VINTAGE" and not any(
        point_in_time[name]["state"] == "ASSERTED"
        for name in ("source_published_at", "known_at", "computed_at")
    ):
        raise IntelligenceVectorContractError("SOURCE_VINTAGE requires an asserted source clock")
    if point_in_time["captured_at"] != _clock(
        state="NOT_ASSERTED", value=None,
        basis="per_source_system_recorded_at_not_exposed_by_revision_receipt",
    ):
        raise IntelligenceVectorContractError("captured_at cannot be invented without owner clock")
    if point_in_time["source_effective_at"] != _clock(
        state="NOT_ASSERTED", value=None,
        basis="earnings_owner_asserts_no_effective_clock_for_results",
    ):
        raise IntelligenceVectorContractError(
            "Earnings source_effective_at is a named-null and cannot be invented"
        )
    if point_in_time["decision_at"]["value"] != decision_cut["opened_at"]:
        raise IntelligenceVectorContractError("family decision_at disagrees with decision cut")
    if point_in_time["decision_admissibility"] == "ADMISSIBLE":
        for clock_name in ("source_published_at", "known_at", "computed_at"):
            clock_value = _parse_time(point_in_time[clock_name]["value"])
            if point_in_time[clock_name]["state"] != "ASSERTED" or clock_value is None or clock_value > opened_at:
                raise IntelligenceVectorContractError("admissible family has a clock after decision cut")
    applicability = _require_keys(
        family["applicability"], frozenset({"state", "basis"}), name="applicability",
    )
    if applicability != {"state": "APPLICABLE", "basis": "earnings_results_event"}:
        raise IntelligenceVectorContractError(
            "applicability is outside the closed Earnings vocabulary"
        )
    coverage = _require_keys(family["coverage"], frozenset({"state", "basis"}), name="coverage")
    coverage_key = (coverage["state"], coverage["basis"])
    if coverage_key not in _COVERAGE_QUALITY_VOCABULARY:
        raise IntelligenceVectorContractError(
            "coverage is outside the closed Earnings vocabulary"
        )
    if family["identity_state"] == "RESOLVED" and owner_subject_id is None:
        if coverage not in (
            {"state": "NOT_COVERED", "basis": "no_current_generation_event"},
            {"state": "UNKNOWN", "basis": "current_manifest_integrity_failure"},
            {"state": "UNKNOWN", "basis": "source_fetch_failed"},
        ):
            raise IntelligenceVectorContractError(
                "resolved binding without an owner event requires a coherent not-covered or read-failure outcome"
            )
    freshness = _require_keys(family["freshness"], frozenset({"state", "basis"}), name="freshness")
    if freshness != {"state": "UNKNOWN", "basis": "owner_has_no_staleness_clock"}:
        raise IntelligenceVectorContractError("freshness requires owner-native clock evidence")
    rights = _require_keys(family["rights"], frozenset({"state", "profile_ref"}), name="rights")
    if rights != {
        "state": "ALLOWED",
        "profile_ref": "event_workspace.v1:derived_only",
    }:
        raise IntelligenceVectorContractError(
            "Earnings rights must be ALLOWED; BLOCKED cannot carry PRESENT values"
        )
    quality = _require_keys(family["quality"], frozenset({"flags"}), name="quality")
    if (
        not isinstance(quality["flags"], list)
        or quality["flags"] != sorted(set(quality["flags"]))
        or tuple(quality["flags"]) != _COVERAGE_QUALITY_VOCABULARY[coverage_key]
    ):
        raise IntelligenceVectorContractError(
            "quality flags are outside the closed coverage vocabulary"
        )
    if family["explanation_facts"] != []:
        raise IntelligenceVectorContractError("Earnings v1 emits no explanation_facts")
    trajectory = _require_keys(family["trajectory"], frozenset({"state", "dimensions"}), name="trajectory")
    if trajectory["state"] not in {"PARTIAL", "NOT_APPLICABLE"}:
        raise IntelligenceVectorContractError("trajectory state invalid")
    if not isinstance(trajectory["dimensions"], list):
        raise IntelligenceVectorContractError("trajectory dimensions must be a list")
    if trajectory["state"] == "NOT_APPLICABLE" and trajectory["dimensions"] != []:
        raise IntelligenceVectorContractError("not-applicable trajectory must be empty")
    if trajectory["state"] == "PARTIAL" and len(trajectory["dimensions"]) != 1:
        raise IntelligenceVectorContractError("partial Earnings trajectory requires one owner delta")
    for dimension in trajectory["dimensions"]:
        dimension_item = _require_keys(dimension, frozenset({
            "dimension", "state", "native_metric_id", "value", "units", "window",
            "cadence", "method_version", "reference_observation_ids", "source_ref_ids",
        }), name="trajectory dimension")
        if {
            "dimension": dimension_item["dimension"],
            "state": dimension_item["state"],
            "native_metric_id": dimension_item["native_metric_id"],
            "window": dimension_item["window"],
            "cadence": dimension_item["cadence"],
            "method_version": dimension_item["method_version"],
        } != {
            "dimension": "REVISION_CHANGE", "state": "PARTIAL",
            "native_metric_id": "metric_delta:revenue",
            "window": None, "cadence": "EVENT_NATIVE", "method_version": "metric_delta.v1",
        }:
            raise IntelligenceVectorContractError("trajectory dimension outside Earnings allowlist")
        _validate_metric_delta(dimension_item["value"])
        if dimension_item["units"] != dimension_item["value"]["current"]["unit"]:
            raise IntelligenceVectorContractError("trajectory units disagree with owner delta")
        for list_name in ("reference_observation_ids", "source_ref_ids"):
            if (
                not isinstance(dimension_item[list_name], list)
                or not dimension_item[list_name]
                or dimension_item[list_name] != sorted(set(dimension_item[list_name]))
            ):
                raise IntelligenceVectorContractError("trajectory references must be non-empty canonical lists")
    correction = _require_keys(
        family["correction"],
        frozenset({
            "state_at_decision", "decision_version_ref_ids",
            "later_correction_ref_ids", "current_state",
        }),
        name="correction",
    )
    if correction["state_at_decision"] not in {"NONE", "PENDING", "CONFLICTED"}:
        raise IntelligenceVectorContractError("correction state_at_decision invalid")
    if correction["current_state"] not in {"CURRENT", "CORRECTED", "CONFLICTED", "UNKNOWN"}:
        raise IntelligenceVectorContractError("correction current_state invalid")
    for list_name in ("decision_version_ref_ids", "later_correction_ref_ids"):
        if (
            not isinstance(correction[list_name], list)
            or correction[list_name] != sorted(set(correction[list_name]))
        ):
            raise IntelligenceVectorContractError("correction references must be sorted and unique")
    if set(correction["decision_version_ref_ids"]) & set(correction["later_correction_ref_ids"]):
        raise IntelligenceVectorContractError("decision and later correction refs must be disjoint")
    if correction["current_state"] == "CORRECTED" and not correction["later_correction_ref_ids"]:
        raise IntelligenceVectorContractError("CORRECTED requires later correction refs")
    if correction["current_state"] == "CURRENT" and correction["later_correction_ref_ids"]:
        raise IntelligenceVectorContractError("CURRENT cannot carry later correction refs")
    if correction["later_correction_ref_ids"] and correction["current_state"] != "CORRECTED":
        raise IntelligenceVectorContractError("later correction refs require CORRECTED state")
    calibration = _require_keys(
        family["calibration"], frozenset({"state", "registration_ref"}), name="calibration",
    )
    if calibration != {"state": "NOT_APPLICABLE", "registration_ref": None}:
        raise IntelligenceVectorContractError("Earnings calibration is not applicable")
    if not isinstance(family["owner_warnings"], list) or any(
        warning not in WORKSPACE_WARNINGS for warning in family["owner_warnings"]
    ):
        raise IntelligenceVectorContractError("owner_warnings outside owner vocabulary")
    if family["owner_warnings"] != sorted(set(family["owner_warnings"])):
        raise IntelligenceVectorContractError("owner_warnings must be sorted and unique")
    if (
        not isinstance(family["source_refs"], list)
        or [ref.get("source_ref_id") for ref in family["source_refs"]]
        != sorted({ref.get("source_ref_id") for ref in family["source_refs"]})
    ):
        raise IntelligenceVectorContractError("source_refs must be sorted and unique")
    for source_ref in family["source_refs"]:
        _validate_source_ref(source_ref)
    if (
        not isinstance(family["evidence_roots"], list)
        or [root.get("evidence_root_id") for root in family["evidence_roots"]]
        != sorted({root.get("evidence_root_id") for root in family["evidence_roots"]})
    ):
        raise IntelligenceVectorContractError("evidence_roots must be sorted and unique")
    for root in family["evidence_roots"]:
        root_item = _require_keys(root, frozenset({
            "evidence_root_id", "source_ref_id", "root_type",
        }), name="evidence_root")
        if root_item["root_type"] != "DOCUMENT_VERSION":
            raise IntelligenceVectorContractError("evidence root type invalid")
        root_semantic = {key: deepcopy(child) for key, child in root_item.items() if key != "evidence_root_id"}
        if root_item["evidence_root_id"] != _content_id("er", root_semantic):
            raise IntelligenceVectorContractError("evidence_root_id content address mismatch")
    if (
        not isinstance(family["observations"], list)
        or not family["observations"]
        or family["observations"] != sorted(
            family["observations"],
            key=lambda observation: (
                observation.get("native_metric_id"), observation.get("observation_id"),
            ),
        )
    ):
        raise IntelligenceVectorContractError("observations must be a non-empty canonical list")
    for observation in family["observations"]:
        _validate_observation(observation)
    if (
        not isinstance(item["economic_dependence_groups"], list)
        or len(item["economic_dependence_groups"]) > 1
    ):
        raise IntelligenceVectorContractError("D5 permits at most one dependence group")
    for group in item["economic_dependence_groups"]:
        group_item = _require_keys(group, frozenset({
            "dependence_group_id", "relation", "member_observation_refs", "basis", "basis_refs",
        }), name="economic_dependence_group")
        group_semantic = {
            "relation": group_item["relation"],
            "basis": group_item["basis"],
            "basis_refs": sorted(group_item["basis_refs"]),
        }
        if group_item["dependence_group_id"] != _content_id("edg", group_semantic):
            raise IntelligenceVectorContractError("dependence_group_id content address mismatch")
        if (
            group_item["relation"] != "COMMON_INFORMATION_ORIGIN"
            or group_item["basis"] != "CONTRACT_RULE"
            or not group_item["member_observation_refs"]
            or group_item["member_observation_refs"]
            != sorted(set(group_item["member_observation_refs"]))
            or not group_item["basis_refs"]
            or group_item["basis_refs"] != sorted(set(group_item["basis_refs"]))
        ):
            raise IntelligenceVectorContractError("economic dependence vocabulary invalid")
    if not isinstance(item["semantic_heads"], list) or len(item["semantic_heads"]) != 1:
        raise IntelligenceVectorContractError("D5 requires one controlled semantic head")
    head = _require_keys(
        item["semantic_heads"][0],
        frozenset({"semantic_head_id", "family_projection_ids"}),
        name="semantic_head",
    )
    if (
        head["semantic_head_id"] != "event_expectation"
        or head["family_projection_ids"] != [family["family_projection_id"]]
    ):
        raise IntelligenceVectorContractError("semantic head must bind event_expectation exactly")
    receipt = _require_keys(
        item["assembly_receipt"],
        frozenset({
            "adapter", "assembled_at", "source_reader", "event_discovery_scope",
            "historical_event_set_reconstruction", "identity_resolution_scope",
            "revision_visibility_scope", "revision_chain_bound_disclosure",
            "event_id", "errors",
        }),
        name="assembly_receipt",
    )
    if receipt["event_discovery_scope"] != "CURRENT_GENERATION_ONLY" or receipt["historical_event_set_reconstruction"] is not False:
        raise IntelligenceVectorContractError("current-generation discovery limitation must be disclosed")
    if receipt["identity_resolution_scope"] != "CURRENT_REGISTRANT_ONLY":
        raise IntelligenceVectorContractError("current-registrant identity limitation must be disclosed")
    if receipt["revision_visibility_scope"] != "ISSUER_RELEASE_SOURCE_HASH_ONLY":
        raise IntelligenceVectorContractError("source-revision visibility limitation must be disclosed")
    if receipt["revision_chain_bound_disclosure"] != _REVISION_CHAIN_BOUND_DISCLOSURE:
        raise IntelligenceVectorContractError("revision-chain default bound must be disclosed")
    assembled_at = receipt["assembled_at"]
    if assembled_at is not None and (
        not isinstance(assembled_at, str) or _parse_time(assembled_at) is None
    ):
        raise IntelligenceVectorContractError(
            "assembly receipt assembled_at must be null or a valid timestamp"
        )
    if (
        receipt["adapter"] != ADAPTER_SET_VERSION
        or receipt["source_reader"] != "read_event_source_revisions"
        or not isinstance(receipt["errors"], list)
    ):
        raise IntelligenceVectorContractError("assembly receipt identity invalid")
    if receipt["event_id"] != owner_subject_id:
        raise IntelligenceVectorContractError("assembly receipt event id mismatch")
    for error in receipt["errors"]:
        error_item = _require_keys(error, frozenset({"type", "message"}), name="assembly error")
        message = error_item["message"]
        if (
            error_item["type"] not in {
                "WorkspaceChainIntegrityError", "CompanyIntelligenceReadError",
            }
            or not isinstance(message, str)
            or not message
            or len(message) > 500
            or _sanitize_error_message(message) != message
        ):
            raise IntelligenceVectorContractError("assembly error receipt is not sanitized")
    if receipt["errors"] != sorted(
        receipt["errors"], key=lambda error: (error["type"], error["message"]),
    ) or len({(error["type"], error["message"]) for error in receipt["errors"]}) != len(
        receipt["errors"]
    ):
        raise IntelligenceVectorContractError(
            "assembly receipt errors must be canonical and unique"
        )
    absence_reasons = {
        reason
        for observation in family["observations"]
        for reason in observation["absence_reasons"]
    }
    expected_error_types: set[str] = set()
    if absence_reasons & {"UNESTIMABLE", "CORRECTION_PENDING"}:
        expected_error_types.add("WorkspaceChainIntegrityError")
    if "SOURCE_UNAVAILABLE" in absence_reasons:
        expected_error_types.add("CompanyIntelligenceReadError")
    actual_error_types = {error["type"] for error in receipt["errors"]}
    if (
        actual_error_types != expected_error_types
        or len(receipt["errors"]) != len(expected_error_types)
    ):
        raise IntelligenceVectorContractError(
            "assembly error receipt does not match the serialized absence outcome"
        )
    if "CompanyIntelligenceReadError" in expected_error_types and coverage != {
        "state": "UNKNOWN", "basis": "source_fetch_failed",
    }:
        raise IntelligenceVectorContractError(
            "source error receipt requires the source-fetch-failed coverage outcome"
        )
    if "WorkspaceChainIntegrityError" in expected_error_types and coverage not in (
        {"state": "UNKNOWN", "basis": "current_manifest_integrity_failure"},
        {"state": "UNKNOWN", "basis": "correction_chain_integrity"},
    ):
        raise IntelligenceVectorContractError(
            "integrity error receipt requires an integrity-failure coverage outcome"
        )
    pending = correction["state_at_decision"] == "PENDING"
    pending_receipt = (
        actual_error_types == {"WorkspaceChainIntegrityError"}
        and absence_reasons == {"UNESTIMABLE", "CORRECTION_PENDING"}
        and coverage in (
            {"state": "UNKNOWN", "basis": "current_manifest_integrity_failure"},
            {"state": "UNKNOWN", "basis": "correction_chain_integrity"},
        )
    )
    if pending != pending_receipt or pending and (
        correction["current_state"] != "UNKNOWN"
        or correction["decision_version_ref_ids"]
        or correction["later_correction_ref_ids"]
        or any(observation["value_state"] != "ABSENT" for observation in family["observations"])
    ):
        raise IntelligenceVectorContractError(
            "PENDING correction requires the receipted integrity absence outcome"
        )
    claims_conflict = (
        correction["state_at_decision"] == "CONFLICTED"
        or correction["current_state"] == "CONFLICTED"
    )
    conflict_outcome = (
        absence_reasons == {"CONFLICTED"}
        and not actual_error_types
        and not correction["decision_version_ref_ids"]
        and not correction["later_correction_ref_ids"]
        and all(
            observation["value_state"] == "ABSENT"
            for observation in family["observations"]
        )
        and (
            (
                family["identity_state"] == "AMBIGUOUS"
                and coverage == {
                    "state": "UNKNOWN",
                    "basis": "canonical_identity_ambiguous",
                }
                and point_in_time["decision_admissibility"] == "UNKNOWN"
            )
            or (
                family["identity_state"] == "RESOLVED"
                and coverage == {
                    "state": "UNKNOWN",
                    "basis": "unresolved_clock_tie",
                }
                and point_in_time["decision_admissibility"] == "UNVERIFIABLE"
            )
        )
    )
    if claims_conflict != conflict_outcome or claims_conflict and (
        correction["state_at_decision"] != "CONFLICTED"
        or correction["current_state"] != "CONFLICTED"
    ):
        raise IntelligenceVectorContractError(
            "CONFLICTED correction requires the exact typed ambiguity or clock-tie outcome"
        )

    source_ref_ids = {ref["source_ref_id"] for ref in family["source_refs"]}
    root_ids = {root["evidence_root_id"] for root in family["evidence_roots"]}
    source_refs_by_id = {ref["source_ref_id"]: ref for ref in family["source_refs"]}
    roots_by_id = {root["evidence_root_id"]: root for root in family["evidence_roots"]}
    observation_ids = {observation["observation_id"] for observation in family["observations"]}
    group_ids = {group["dependence_group_id"] for group in item["economic_dependence_groups"]}
    if not set(correction["decision_version_ref_ids"]).issubset(source_ref_ids) or not set(
        correction["later_correction_ref_ids"]
    ).issubset(source_ref_ids):
        raise IntelligenceVectorContractError("correction references unknown source refs")
    decision_ref_ids = set(correction["decision_version_ref_ids"])
    later_ref_ids = set(correction["later_correction_ref_ids"])
    corrected_clock = point_in_time["corrected_at"]
    if later_ref_ids:
        if (
            corrected_clock["state"] != "ASSERTED"
            or corrected_clock["basis"] != "later_event_workspace.generated_at"
            or set(corrected_clock["source_ref_ids"]) != later_ref_ids
            or _parse_time(corrected_clock["value"]) is None
        ):
            raise IntelligenceVectorContractError(
                "corrected_at must bind the later correction generation refs"
            )
        decision_generations = {
            source_refs_by_id[ref_id]["version_or_generation"]
            for ref_id in decision_ref_ids
        }
        later_generations = {
            source_refs_by_id[ref_id]["version_or_generation"]
            for ref_id in later_ref_ids
        }
        if not later_generations or decision_generations & later_generations:
            raise IntelligenceVectorContractError(
                "decision and correction generations must be distinct"
            )
    elif corrected_clock != _clock(
        state="NOT_ASSERTED",
        value=None,
        basis="no_later_visible_source_revision",
    ):
        raise IntelligenceVectorContractError(
            "corrected_at cannot be asserted without later correction refs"
        )
    for root in family["evidence_roots"]:
        if root["source_ref_id"] not in source_ref_ids:
            raise IntelligenceVectorContractError("evidence root references unknown source")
    for clock_name in (
        "source_effective_at", "source_published_at", "known_at", "captured_at",
        "computed_at", "corrected_at", "decision_at",
    ):
        if not set(point_in_time[clock_name]["source_ref_ids"]).issubset(source_ref_ids):
            raise IntelligenceVectorContractError("clock references unknown sources")
    for observation in family["observations"]:
        if not set(observation["source_ref_ids"]).issubset(source_ref_ids):
            raise IntelligenceVectorContractError("observation references unknown sources")
        if not set(observation["evidence_root_ids"]).issubset(root_ids):
            raise IntelligenceVectorContractError("observation references unknown evidence roots")
        if not set(observation["economic_dependence_group_ids"]).issubset(group_ids):
            raise IntelligenceVectorContractError("observation references unknown dependence groups")
        if observation["value_state"] == "PRESENT":
            expected_root_ids = {
                root_id for root_id, root in roots_by_id.items()
                if root["source_ref_id"] in observation["source_ref_ids"]
            }
            if set(observation["evidence_root_ids"]) != expected_root_ids:
                raise IntelligenceVectorContractError("observation root lineage is not exact")
            prefix = (
                "facts[" if observation["native_metric_id"] == "fact:revenue"
                else "guidance["
            )
            expected_schema = (
                "event_workspace.source/issuer_release"
                if prefix == "facts[" else "event_workspace.source/transcript"
            )
            for source_ref_id in observation["source_ref_ids"]:
                source_ref = source_refs_by_id[source_ref_id]
                if (
                    source_ref["object_schema"] != expected_schema
                    or not any(path.startswith(prefix) for path in source_ref["field_paths"])
                ):
                    raise IntelligenceVectorContractError("observation source lineage is not exact")
                if prefix == "facts[":
                    fact_paths = {
                        path for path in source_ref["field_paths"]
                        if path.startswith("facts[")
                    }
                    fact_indices = {
                        path.split("[", 1)[1].split("]", 1)[0]
                        for path in fact_paths
                    }
                    if len(fact_indices) != 1:
                        raise IntelligenceVectorContractError(
                            "fact observation source lineage is not exact"
                        )
                    fact_index = next(iter(fact_indices))
                    if fact_paths != {
                        f"facts[{fact_index}].basis",
                        f"facts[{fact_index}].metric",
                        f"facts[{fact_index}].unit",
                        f"facts[{fact_index}].value",
                    }:
                        raise IntelligenceVectorContractError(
                            "fact basis must participate in exact source lineage"
                        )
                else:
                    guidance_paths = {
                        path for path in source_ref["field_paths"]
                        if path.startswith("guidance[")
                    }
                    guidance_indices = {
                        path.split("[", 1)[1].split("]", 1)[0]
                        for path in guidance_paths
                    }
                    if len(guidance_indices) != 1:
                        raise IntelligenceVectorContractError(
                            "guidance observation source lineage is not exact"
                        )
                    guidance_index = next(iter(guidance_indices))
                    if guidance_paths != {
                        f"guidance[{guidance_index}].high",
                        f"guidance[{guidance_index}].low",
                        f"guidance[{guidance_index}].metric",
                        f"guidance[{guidance_index}].status",
                        f"guidance[{guidance_index}].unit",
                    }:
                        raise IntelligenceVectorContractError(
                            "guidance observation source lineage is not exact"
                        )
    present_observations = [
        observation for observation in family["observations"]
        if observation["value_state"] == "PRESENT"
    ]
    evidence_admitted = (
        applicability == {"state": "APPLICABLE", "basis": "earnings_results_event"}
        and coverage["state"] in {"COVERED", "PARTIAL"}
        and point_in_time["decision_admissibility"] == "ADMISSIBLE"
        and not actual_error_types
    )
    if not evidence_admitted and (
        family["source_refs"]
        or family["evidence_roots"]
        or present_observations
        or trajectory["dimensions"]
        or correction["decision_version_ref_ids"]
        or correction["later_correction_ref_ids"]
        or item["economic_dependence_groups"]
    ):
        raise IntelligenceVectorContractError(
            "PRESENT evidence graph requires applicable, covered, admissible, error-free state"
        )
    if family["identity_state"] != "RESOLVED" and (
        family["source_refs"]
        or family["evidence_roots"]
        or present_observations
        or trajectory["dimensions"]
        or correction["decision_version_ref_ids"]
        or correction["later_correction_ref_ids"]
        or item["economic_dependence_groups"]
    ):
        raise IntelligenceVectorContractError(
            "unresolved identity cannot carry owner evidence"
        )
    if owner_subject_id is None and (
        family["source_refs"]
        or family["evidence_roots"]
        or present_observations
        or trajectory["dimensions"]
        or correction["decision_version_ref_ids"]
        or correction["later_correction_ref_ids"]
        or item["economic_dependence_groups"]
    ):
        raise IntelligenceVectorContractError(
            "binding without an owner event cannot carry owner evidence"
        )
    for dimension in trajectory["dimensions"]:
        if not set(dimension["reference_observation_ids"]).issubset(observation_ids):
            raise IntelligenceVectorContractError("trajectory references unknown observations")
        if not set(dimension["source_ref_ids"]).issubset(source_ref_ids):
            raise IntelligenceVectorContractError("trajectory references unknown sources")
        for source_ref_id in dimension["source_ref_ids"]:
            source_ref = source_refs_by_id[source_ref_id]
            delta_paths = {
                path for path in source_ref["field_paths"]
                if path.startswith("deltas[")
            }
            delta_indices = {
                path.split("[", 1)[1].split("]", 1)[0]
                for path in delta_paths
            }
            if (
                source_ref["object_schema"]
                != "event_workspace.source/issuer_release"
                or len(delta_indices) != 1
            ):
                raise IntelligenceVectorContractError(
                    "trajectory delta source lineage is not exact"
                )
            delta_index = next(iter(delta_indices))
            required = {
                f"deltas[{delta_index}].basis_match",
                f"deltas[{delta_index}].current.basis",
                f"deltas[{delta_index}].current.unit",
                f"deltas[{delta_index}].current.value",
                f"deltas[{delta_index}].metric",
            }
            for side in ("prior", "consensus"):
                side_paths = {
                    path for path in delta_paths
                    if path.startswith(f"deltas[{delta_index}].{side}.")
                }
                allowed_side_paths = (
                    {
                        f"deltas[{delta_index}].{side}.reason",
                        f"deltas[{delta_index}].{side}.state",
                    },
                    {
                        f"deltas[{delta_index}].{side}.reason",
                        f"deltas[{delta_index}].{side}.schema",
                    },
                    {
                        f"deltas[{delta_index}].{side}.reason",
                        f"deltas[{delta_index}].{side}.schema",
                        f"deltas[{delta_index}].{side}.state",
                    },
                )
                if side_paths not in allowed_side_paths:
                    raise IntelligenceVectorContractError(
                        "trajectory delta source lineage is not exact"
                    )
                required.update(side_paths)
            if delta_paths != required:
                raise IntelligenceVectorContractError(
                    "trajectory delta source lineage is not exact"
                )
    decision_evidence_ref_ids = {
        source_ref_id
        for observation in present_observations
        for source_ref_id in observation["source_ref_ids"]
    } | {
        source_ref_id
        for dimension in trajectory["dimensions"]
        for source_ref_id in dimension["source_ref_ids"]
    }
    if later_ref_ids & decision_evidence_ref_ids:
        raise IntelligenceVectorContractError(
            "later correction refs are audit-only and cannot support decision evidence"
        )
    if evidence_admitted and decision_ref_ids != decision_evidence_ref_ids:
        raise IntelligenceVectorContractError(
            "decision version refs must exactly equal PRESENT decision evidence refs"
        )
    if correction["current_state"] == "CURRENT" and not (
        correction["state_at_decision"] == "NONE"
        and family["identity_state"] == "RESOLVED"
        and owner_subject_id is not None
        and evidence_admitted
        and bool(present_observations)
        and bool(decision_ref_ids)
        and decision_ref_ids == decision_evidence_ref_ids
        and not later_ref_ids
        and not receipt["errors"]
        and all(
            observation["correction_lineage_state"]
            in {"OBSERVED", "NONE_IN_CHAIN"}
            for observation in present_observations
        )
    ):
        raise IntelligenceVectorContractError(
            "CURRENT requires resolved admitted owner evidence with exact decision refs and compatible lineage"
        )
    for group in item["economic_dependence_groups"]:
        if not set(group["member_observation_refs"]).issubset(observation_ids):
            raise IntelligenceVectorContractError("dependence group references unknown observations")
        if not set(group["basis_refs"]).issubset(root_ids):
            raise IntelligenceVectorContractError("dependence group references unknown roots")
        symmetric_members = {
            observation["observation_id"]
            for observation in family["observations"]
            if group["dependence_group_id"]
            in observation["economic_dependence_group_ids"]
        }
        if set(group["member_observation_refs"]) != symmetric_members:
            raise IntelligenceVectorContractError(
                "economic dependence membership must be symmetric"
            )

    family_semantic = {key: deepcopy(value) for key, value in family.items() if key != "family_projection_id"}
    if family["family_projection_id"] != _content_id("pif", family_semantic):
        raise IntelligenceVectorContractError("family projection_id content address mismatch")
    semantic = {key: deepcopy(value) for key, value in item.items() if key not in {"projection_id", "assembly_receipt"}}
    if item["projection_id"] != _content_id("piv", semantic):
        raise IntelligenceVectorContractError("projection_id content address mismatch")


__all__ = [
    "ADAPTER_SET_VERSION",
    "ALL_FALSE_AUTHORITY",
    "EARNINGS_FAMILY_ID",
    "IntelligenceVectorContractError",
    "SCHEMA_INTELLIGENCE_VECTOR",
    "build_earnings_intelligence_vector",
    "validate_intelligence_vector",
]
