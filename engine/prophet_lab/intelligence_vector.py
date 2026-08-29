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
from lib.dataos.identity import IdentityError as IssuerIdentityError


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
    "trajectory", "correction", "calibration", "fusion_bindings",
    "authority", "owner_warnings",
})
_FORBIDDEN_KEYS = frozenset({
    "score", "rank", "weight", "confidence", "conviction", "evidence_count",
    "entry_open", "ENTRY_OPEN", "body", "claims", "transcript",
    "private_path", "path", "url", "workspace", "source_span",
})
_PEG_RE = re.compile(r"^peg:[0-9a-f]{64}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_PATH_RE = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s]+)")
_METRIC_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,95}$")
_GUIDANCE_STATES = frozenset({"introduced", "reiterated", "raised", "cut", "withdrawn", "absent"})


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
    sanitized = _URL_RE.sub("[redacted-url]", str(message))
    sanitized = _PATH_RE.sub("[redacted-path]", sanitized)
    return sanitized[:500]


def _safe_object_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or _URL_RE.search(text) or text.startswith(("/", "\\")) or "../" in text:
        return None
    return text


def _episode_known_at(episode: Mapping[str, Any]) -> str | None:
    value = episode.get("_d5_episode_known_at")
    return str(value) if _parse_time(value) is not None else None


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
    return {
        "basis": "LIVE_CAPTURED",
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


def _source_refs(
    workspace: Mapping[str, Any], generation_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    refs: list[dict[str, Any]] = []
    roots: list[dict[str, Any]] = []
    for index, raw_source in enumerate(_as_list(workspace.get("sources"))):
        if not isinstance(raw_source, Mapping):
            continue
        object_id = _safe_object_id(raw_source.get("document_id"))
        if object_id is None:
            continue
        source_hash = raw_source.get("source_sha256")
        semantic = {
            "owner_namespace": "company_intelligence",
            "object_schema": "event_workspace.source_ref/v1",
            "object_id": object_id,
            "version_or_generation": generation_id,
            "content_hash": source_hash if isinstance(source_hash, str) and _HASH_RE.fullmatch(source_hash) else None,
            "field_paths": ["facts", "deltas", "guidance"],
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
    return refs, roots


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
        "source_ref_ids": source_ref_ids,
        "evidence_root_ids": root_ids,
        "economic_dependence_group_ids": dependence_group_ids,
        "quality_flags": sorted(set(quality_flags or [])),
        "absence_reasons": sorted(set(absence_reasons or [])),
        "neutral_definition_ref": None,
        "correction_lineage_state": correction_lineage_state,
    }
    return {"observation_id": _content_id("obs", semantic), **semantic}


def _observations(
    workspace: Mapping[str, Any], *, source_ref_ids: list[str], root_ids: list[str],
    dependence_group_ids: list[str], correction_lineage_state: str,
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for fact in _as_list(workspace.get("facts")):
        metric = str(fact.get("metric") or "") if isinstance(fact, Mapping) else ""
        if not _METRIC_RE.fullmatch(metric):
            continue
        item = _observation(
            native_metric_id=f"fact:{metric}", value=fact.get("value"),
            units=fact.get("unit"), source_ref_ids=source_ref_ids, root_ids=root_ids,
            dependence_group_ids=dependence_group_ids,
            correction_lineage_state=correction_lineage_state,
        )
        if item is not None:
            observations.append(item)
    for delta in _as_list(workspace.get("deltas")):
        metric = str(delta.get("metric") or "") if isinstance(delta, Mapping) else ""
        if not _METRIC_RE.fullmatch(metric):
            continue
        current = _as_mapping(delta.get("current"))
        flags = ["basis_match_false"] if delta.get("basis_match") is False else []
        item = _observation(
            native_metric_id=f"delta:{metric}", value=current.get("value"),
            units=current.get("unit"), source_ref_ids=source_ref_ids, root_ids=root_ids,
            dependence_group_ids=dependence_group_ids,
            correction_lineage_state=correction_lineage_state, quality_flags=flags,
        )
        if item is not None:
            observations.append(item)
    for guidance in _as_list(workspace.get("guidance")):
        metric = str(guidance.get("metric") or "") if isinstance(guidance, Mapping) else ""
        if not _METRIC_RE.fullmatch(metric):
            continue
        guidance_status = str(guidance.get("status") or "")
        item = _observation(
            native_metric_id=f"guidance:{metric}",
            value={"low": guidance.get("low"), "high": guidance.get("high")},
            units=guidance.get("unit"), source_ref_ids=source_ref_ids, root_ids=root_ids,
            dependence_group_ids=dependence_group_ids,
            correction_lineage_state=correction_lineage_state,
            quality_flags=[f"status:{guidance_status}"] if guidance_status in _GUIDANCE_STATES else [],
        )
        if item is not None:
            observations.append(item)
    return sorted(observations, key=lambda item: (item["native_metric_id"], item["observation_id"]))


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
            "revision_chain_bound_disclosure": "CALLER_INJECTED_READER_BOUND; OWNER_DEFAULT_MAX_HOPS=500",
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
    if _parse_time(episode_known_at) is None:
        raise IntelligenceVectorContractError("episode_known_at must come from the B1 event stream")
    episode = {**episode, "_d5_episode_known_at": episode_known_at}
    cut = _parse_time(episode.get("opened_at"))
    if cut is None:
        raise IntelligenceVectorContractError("episode opened_at decision cut is missing or invalid")

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
        workspace = _as_mapping(revision.get("workspace"))
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
        lineage_state = (
            "NOT_OBSERVABLE" if any(item["revision"].get("source_sha256") is None for item in normalized)
            else ("OBSERVED" if len({item["revision"].get("source_sha256") for item in normalized}) > 1 else "NONE_IN_CHAIN")
        )
        family["observations"] = [_absence_observation(
            reason_ids=["NOT_CAPTURED_AT_DECISION" if after_cut else "UNKNOWN"],
            correction_lineage_state=lineage_state,
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
    source_ref_ids = [ref["source_ref_id"] for ref in decision_refs]
    root_ids = [root["evidence_root_id"] for root in decision_roots]

    hashes = [item["revision"].get("source_sha256") for item in normalized]
    if any(value is None for value in hashes):
        lineage_state = "NOT_OBSERVABLE"
    elif len(set(hashes)) > 1:
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

    # Source aliases are content addressed, so preserving order and removing
    # duplicates is deterministic even if two workspace rows cite one source.
    all_refs = list({ref["source_ref_id"]: ref for ref in decision_refs + later_refs}.values())
    all_roots = list({root["evidence_root_id"]: root for root in decision_roots + later_roots}.values())
    dependence_group_id = _dependence_group_id(root_ids) if root_ids else ""
    dependence_ids = [dependence_group_id] if dependence_group_id else []
    family["source_refs"] = all_refs
    family["evidence_roots"] = all_roots
    family["observations"] = _observations(
        workspace,
        source_ref_ids=source_ref_ids,
        root_ids=root_ids,
        dependence_group_ids=dependence_ids,
        correction_lineage_state=lineage_state,
    )
    groups = ([{
        "dependence_group_id": dependence_group_id,
        "relation": "COMMON_INFORMATION_ORIGIN",
        "member_observation_refs": [item["observation_id"] for item in family["observations"]],
        "basis": "CONTRACT_RULE",
        "basis_refs": root_ids,
    }] if dependence_group_id and family["observations"] else [])
    corrected_at = (
        max(later, key=lambda item: item["parsed"]["generated_at"])["clocks"]["generated_at"]
        if later else None
    )
    later_ref_ids = [ref["source_ref_id"] for ref in later_refs]
    family["coverage"] = {"state": "COVERED", "basis": "decision_admissible_revision"}
    family["point_in_time"] = _point_in_time(
        episode, clocks=chosen["clocks"], decision_admissibility="ADMISSIBLE",
        corrected_at=corrected_at, corrected_ref_ids=later_ref_ids,
    )
    family["freshness"] = {"state": "CURRENT", "basis": "current_at_decision_cut"}
    family["quality"] = {"flags": []}
    family["owner_warnings"] = sorted({
        str(warning) for warning in _as_list(workspace.get("warnings")) if warning in WORKSPACE_WARNINGS
    })

    family["correction"] = {
        "state_at_decision": "NONE",
        "decision_version_ref_ids": source_ref_ids,
        "later_correction_ref_ids": later_ref_ids,
        "current_state": (
            "UNKNOWN" if lineage_state == "NOT_OBSERVABLE"
            else ("CORRECTED" if later_ref_ids else "CURRENT")
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
    if _safe_object_id(item["object_id"]) != item["object_id"]:
        raise IntelligenceVectorContractError("source_ref object_id leaks a private locator")
    if item["content_hash"] is not None and not _HASH_RE.fullmatch(str(item["content_hash"])):
        raise IntelligenceVectorContractError("source_ref content_hash invalid")
    if not isinstance(item["field_paths"], list) or any(
        path not in {"facts", "deltas", "guidance"} for path in item["field_paths"]
    ):
        raise IntelligenceVectorContractError("source_ref field_paths outside Earnings allowlist")
    if item["render_policy"] not in {"INTERNAL_ONLY", "DERIVED_ONLY", "DISPLAY_SAFE"}:
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
    elif item["absence_reasons"]:
        raise IntelligenceVectorContractError("present observation cannot carry absence reasons")
    if item["absence_reasons"] != sorted(set(item["absence_reasons"])):
        raise IntelligenceVectorContractError("absence reasons must be sorted and unique")
    if item["correction_lineage_state"] not in {"OBSERVED", "NONE_IN_CHAIN", "NOT_OBSERVABLE"}:
        raise IntelligenceVectorContractError("correction_lineage_state invalid")
    if isinstance(item["value"], Mapping):
        _require_keys(item["value"], frozenset({"low", "high"}), name="observation range")
    semantic = {key: deepcopy(child) for key, child in item.items() if key != "observation_id"}
    if item["observation_id"] != _content_id("obs", semantic):
        raise IntelligenceVectorContractError("observation_id content address mismatch")


def _validate_clock(value: Any, *, name: str) -> None:
    item = _require_keys(
        value,
        frozenset({"state", "value", "interval", "precision", "basis", "source_ref_ids"}),
        name=name,
    )
    if item["state"] not in {"ASSERTED", "NOT_ASSERTED", "NOT_APPLICABLE", "UNKNOWN"}:
        raise IntelligenceVectorContractError(f"{name} state invalid")
    if item["state"] == "ASSERTED" and _parse_time(item["value"]) is None:
        raise IntelligenceVectorContractError(f"{name} asserted without a valid instant")
    if item["state"] != "ASSERTED" and item["value"] is not None:
        raise IntelligenceVectorContractError(f"{name} named-null state carries a value")


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
    if not str(episode_ref["episode_id"] or "") or not str(episode_ref["identity_ref"] or "").startswith("ISS:"):
        raise IntelligenceVectorContractError("episode_ref identity is incomplete")
    if not _PEG_RE.fullmatch(str(episode_ref["generation_id"] or "")):
        raise IntelligenceVectorContractError("episode_ref generation invalid")
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
    point_in_time = _require_keys(
        family["point_in_time"],
        frozenset({
            "basis", "decision_admissibility", "missing_clocks", "source_effective_at",
            "source_published_at", "known_at", "captured_at", "computed_at",
            "corrected_at", "decision_at",
        }),
        name="family.point_in_time",
    )
    if point_in_time["basis"] not in {
        "LIVE_CAPTURED", "SOURCE_VINTAGE", "PUBLIC_RECONSTRUCTED",
        "RECOMPUTED_HISTORY", "CURRENT_SNAPSHOT_BACKFILL", "UNKNOWN",
    }:
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
        _validate_clock(point_in_time[clock_name], name=f"family.point_in_time.{clock_name}")
    applicability = _require_keys(
        family["applicability"], frozenset({"state", "basis"}), name="applicability",
    )
    if applicability["state"] not in {"APPLICABLE", "NOT_APPLICABLE", "UNKNOWN"}:
        raise IntelligenceVectorContractError("applicability state invalid")
    coverage = _require_keys(family["coverage"], frozenset({"state", "basis"}), name="coverage")
    if coverage["state"] not in {"COVERED", "PARTIAL", "NOT_COVERED", "UNKNOWN"}:
        raise IntelligenceVectorContractError("coverage state invalid")
    freshness = _require_keys(family["freshness"], frozenset({"state", "basis"}), name="freshness")
    if freshness["state"] not in {"CURRENT", "STALE", "EXPIRED", "UNKNOWN"}:
        raise IntelligenceVectorContractError("freshness state invalid")
    rights = _require_keys(family["rights"], frozenset({"state", "profile_ref"}), name="rights")
    if rights["state"] not in {"ALLOWED", "DERIVED_ONLY", "BLOCKED", "UNKNOWN"}:
        raise IntelligenceVectorContractError("rights state invalid")
    _require_keys(family["quality"], frozenset({"flags"}), name="quality")
    trajectory = _require_keys(family["trajectory"], frozenset({"state", "dimensions"}), name="trajectory")
    if trajectory["state"] not in {
        "AVAILABLE", "PARTIAL", "NOT_APPLICABLE", "INSUFFICIENT_HISTORY",
        "UNESTIMABLE", "ACCRUING",
    }:
        raise IntelligenceVectorContractError("trajectory state invalid")
    if not isinstance(trajectory["dimensions"], list):
        raise IntelligenceVectorContractError("trajectory dimensions must be a list")
    for dimension in trajectory["dimensions"]:
        _require_keys(dimension, frozenset({
            "dimension", "state", "native_metric_id", "value", "units", "window",
            "cadence", "method_version", "reference_observation_ids", "source_ref_ids",
        }), name="trajectory dimension")
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
    if correction["current_state"] not in {"CURRENT", "CORRECTED", "RETRACTED", "CONFLICTED", "UNKNOWN"}:
        raise IntelligenceVectorContractError("correction current_state invalid")
    _require_keys(family["calibration"], frozenset({"state", "registration_ref"}), name="calibration")
    if not isinstance(family["owner_warnings"], list) or any(
        warning not in WORKSPACE_WARNINGS for warning in family["owner_warnings"]
    ):
        raise IntelligenceVectorContractError("owner_warnings outside owner vocabulary")
    if family["owner_warnings"] != sorted(set(family["owner_warnings"])):
        raise IntelligenceVectorContractError("owner_warnings must be sorted and unique")
    for source_ref in family["source_refs"]:
        _validate_source_ref(source_ref)
    for root in family["evidence_roots"]:
        root_item = _require_keys(root, frozenset({
            "evidence_root_id", "source_ref_id", "root_type",
        }), name="evidence_root")
        if root_item["root_type"] not in {
            "DOCUMENT_VERSION", "EVENT_VERSION", "OWNER_PACKET", "SOURCE_SNAPSHOT",
            "MARKET_SESSION", "REGISTRY_RECORD", "OTHER",
        }:
            raise IntelligenceVectorContractError("evidence root type invalid")
        root_semantic = {key: deepcopy(child) for key, child in root_item.items() if key != "evidence_root_id"}
        if root_item["evidence_root_id"] != _content_id("er", root_semantic):
            raise IntelligenceVectorContractError("evidence_root_id content address mismatch")
    for observation in family["observations"]:
        _validate_observation(observation)
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
        if group_item["relation"] not in {
            "SAME_ECONOMIC_DRIVER", "COMMON_INFORMATION_ORIGIN",
            "MECHANICALLY_DERIVED", "UNKNOWN_OVERLAP",
        } or group_item["basis"] not in {"OWNER_ASSERTED", "CONTRACT_RULE", "EVAL_ASSERTED", "UNKNOWN"}:
            raise IntelligenceVectorContractError("economic dependence vocabulary invalid")
    for head in item["semantic_heads"]:
        _require_keys(head, frozenset({"semantic_head_id", "family_projection_ids"}), name="semantic_head")
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
    if "500" not in str(receipt["revision_chain_bound_disclosure"]):
        raise IntelligenceVectorContractError("revision-chain default bound must be disclosed")
    for error in receipt["errors"]:
        error_item = _require_keys(error, frozenset({"type", "message"}), name="assembly error")
        if _URL_RE.search(str(error_item["message"])) or _PATH_RE.search(str(error_item["message"])):
            raise IntelligenceVectorContractError("assembly error receipt is not sanitized")

    source_ref_ids = {ref["source_ref_id"] for ref in family["source_refs"]}
    root_ids = {root["evidence_root_id"] for root in family["evidence_roots"]}
    observation_ids = {observation["observation_id"] for observation in family["observations"]}
    group_ids = {group["dependence_group_id"] for group in item["economic_dependence_groups"]}
    if not set(correction["decision_version_ref_ids"]).issubset(source_ref_ids) or not set(
        correction["later_correction_ref_ids"]
    ).issubset(source_ref_ids):
        raise IntelligenceVectorContractError("correction references unknown source refs")
    for observation in family["observations"]:
        if not set(observation["source_ref_ids"]).issubset(source_ref_ids):
            raise IntelligenceVectorContractError("observation references unknown sources")
        if not set(observation["evidence_root_ids"]).issubset(root_ids):
            raise IntelligenceVectorContractError("observation references unknown evidence roots")
        if not set(observation["economic_dependence_group_ids"]).issubset(group_ids):
            raise IntelligenceVectorContractError("observation references unknown dependence groups")
    for group in item["economic_dependence_groups"]:
        if not set(group["member_observation_refs"]).issubset(observation_ids):
            raise IntelligenceVectorContractError("dependence group references unknown observations")

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
