"""Pure, receipt-bound Government Revenue research-candidate construction.

This module is intentionally an admission gate, not a signal generator.  It
only turns a reviewed, exact listed-company impact on a receipt-bound official
award-change event into research context.  Discovery-name matches, legacy
award tables, incomplete ownership paths, or non-current receipts return no
candidate.  The queue keeps those discovery names visible as mapping backlog
without asserting issuer attribution.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timezone
from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from engine.government_revenue import entity_resolution
from engine.government_revenue.entity_resolution import load_recipient_entity_graph


CONTRACT = "government_revenue_candidate.v1"
QUEUE_CONTRACT = "government_revenue_candidate_queue.v1"
SCHEMA_VERSION = "1.0.0"
HISTORICAL_SUPPRESSION_CONTRACT = (
    "government_revenue.candidate_historical_suppressions.v1"
)
HISTORICAL_SUPPRESSION_APPLICATION_CONTRACT = (
    "government_revenue.candidate_historical_suppression_application.v1"
)
HISTORICAL_SUPPRESSION_ACTIVATION_CONTRACT = (
    "government_revenue.candidate_historical_suppression_activation.v1"
)
HISTORICAL_SUPPRESSION_CONFIG_PATH = Path(
    "config/government_revenue/candidate_historical_suppressions.v1.json"
)
HISTORICAL_SUPPRESSION_SCHEMA_PATH = Path(
    "contracts/government_revenue/government_revenue_candidate_historical_suppressions.v1.schema.json"
)
HISTORICAL_SUPPRESSION_SOURCE_PREFIX = (
    "candidate-suppression-manifest-sha256:"
)
ISSUANCE_CORRECTION_CONTRACT = (
    "government_revenue.candidate_issuance_corrections.v1"
)
ISSUANCE_CORRECTION_APPLICATION_CONTRACT = (
    "government_revenue.candidate_issuance_correction_application.v1"
)
ISSUANCE_CORRECTION_ACTIVATION_CONTRACT = (
    "government_revenue.candidate_issuance_correction_activation.v1"
)
ISSUANCE_CORRECTION_CONFIG_PATH = Path(
    "config/government_revenue/candidate_issuance_corrections.v1.json"
)
ISSUANCE_CORRECTION_SCHEMA_PATH = Path(
    "contracts/government_revenue/government_revenue_candidate_issuance_corrections.v1.schema.json"
)
ISSUANCE_CORRECTION_SOURCE_PREFIX = (
    "candidate-issuance-correction-manifest-sha256:"
)
_HEX_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_TICKER = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
#: Award-change event types this gate turns into a candidate family.
#:
#: The first five are the action rail's.  The last two are their SNAPSHOT-rail
#: analogues, admitted because excluding them was an accident of which rail was
#: built first, not a protective decision:
#:
#: * ``reported_obligation_balance_changed`` is a move in the snapshot's
#:   ``total_obligated_amount`` -- the same economic fact the action rail
#:   publishes as ``obligation``/``deobligation``, read off the award's reported
#:   balance instead of off one transaction.  Its direction therefore comes from
#:   the SIGN of the move (see :data:`_SIGN_DIRECTED`), not from the event name,
#:   because one snapshot type carries both directions.
#: * ``award_value_changed`` is a compound snapshot move in which BOTH
#:   ``current_award_amount`` and ``potential_award_amount`` changed.  It
#:   strictly contains the admitted ``ceiling_changed``, so admitting the narrow
#:   event while dropping the compound one deleted a ceiling change purely
#:   because a second field moved with it.  The candidate carries ONLY the
#:   ceiling component (see :data:`_FAMILY_AMOUNT_ID`).
#:
#: ``award_discovered_late`` is deliberately NOT here.  Late discovery is a
#: disclosure state about when this pipeline first saw an award -- not a
#: catalyst family -- and it already has its own fail-closed treatment on
#: ``new_award`` below.
_SUPPORTED_FAMILIES = {
    "obligation": "award_obligation_change",
    "deobligation": "award_obligation_change",
    "ceiling_changed": "award_ceiling_change",
    "option_exercised": "option_exercise",
    "new_award": "new_award",
    "reported_obligation_balance_changed": "award_obligation_change",
    "award_value_changed": "award_ceiling_change",
}
IDENTITY_BASIS_SOURCE_RECORD = entity_resolution.IDENTITY_BASIS_SOURCE_RECORD
IDENTITY_BASIS_AWARD_LEVEL = entity_resolution.IDENTITY_BASIS_AWARD_LEVEL
IDENTITY_BASES = (IDENTITY_BASIS_SOURCE_RECORD, IDENTITY_BASIS_AWARD_LEVEL)
#: Printed on any candidate whose exact link rests on the award's recipient of
#: record rather than on an identity the observation itself asserted.  The
#: limitation is the user-facing half of the ruling: the link is exact, and it
#: is a claim about the award as collected, not about what the transaction said.
AWARD_LEVEL_IDENTITY_LIMITATION = (
    "Issuer identity comes from the award's recipient of record as collected, not from the "
    "transaction record itself; a recipient change recorded after collection would not be "
    "reflected in this link."
)

#: Event types whose candidate amount is NOT the event's own primary amount.
#:
#: A compound ``award_value_changed`` event leads with the current-value delta,
#: which is a different economic claim from the ceiling change this gate admits
#: it for.  The candidate therefore names the ceiling component explicitly; the
#: current-value component stays visible on the event, under its own semantic
#: label, and never enters the candidate's amount or materiality.  A compound
#: event that does not carry the ceiling delta produces no candidate at all.
_FAMILY_AMOUNT_ID = {"award_value_changed": "delta_potential_award_amount"}

#: Event types whose transmission direction is read from the sign of the
#: admitted amount rather than from the event type alone.  The action rail
#: splits direction into two type names (``obligation``/``deobligation``); the
#: snapshot rail publishes one type for both, so the sign is the only honest
#: source of direction for it.
_SIGN_DIRECTED = {"reported_obligation_balance_changed"}


def _authority() -> dict[str, Any]:
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


def _historical_suppression_authority() -> dict[str, Any]:
    """Authority of the reviewed infrastructure control, never of a candidate."""
    return {**_authority(), "tier": "infrastructure"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def historical_suppression_entry_key(entry: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the graph/clock-independent identity of one reviewed tombstone.

    ``observation_id`` and candidate ``known_at`` both move when the reviewed
    graph is re-published.  A suppression is therefore pinned to the stable
    candidate hypothesis plus the immutable official event/source identity.
    """
    if not isinstance(entry, Mapping):
        raise ValueError("historical suppression entry must be an object")
    fields = (
        "candidate_id",
        "source_event_id",
        "source_record_id",
        "source_rail",
        "source_content_sha256",
    )
    values: list[str] = []
    for field in fields:
        value = entry.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"historical suppression {field} is invalid")
        values.append(value)
    return tuple(values)


def candidate_historical_suppression_entry(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    """Project only the immutable source identity needed for a reviewed refusal."""
    if not isinstance(row, Mapping):
        raise ValueError("candidate row must be an object")
    source_event = row.get("source_event")
    if not isinstance(source_event, Mapping):
        raise ValueError("candidate source event is invalid")
    entry = {
        "candidate_id": row.get("candidate_id"),
        "candidate_family": row.get("candidate_family"),
        "source_event_id": source_event.get("event_id"),
        "source_record_id": source_event.get("record_id"),
        "source_rail": source_event.get("source_rail"),
        "source_content_sha256": source_event.get("source_content_id"),
        "observed_known_at": row.get("known_at"),
        "decision": "do_not_backfill",
        "reason_code": "pre_fix_candidate_became_visible_after_frozen_empty_projection",
    }
    historical_suppression_entry_key(entry)
    if not isinstance(entry["candidate_family"], str) or not entry["candidate_family"]:
        raise ValueError("historical suppression candidate_family is invalid")
    if not isinstance(entry["observed_known_at"], str) or not entry["observed_known_at"]:
        raise ValueError("historical suppression observed_known_at is invalid")
    if _HEX_SHA256.fullmatch(entry["source_content_sha256"]) is None:
        raise ValueError("historical suppression source_content_sha256 is invalid")
    return entry


def candidate_historical_suppression_activation(
    manifest: Mapping[str, Any],
    manifest_sha256: str,
    *,
    activated_at: str,
) -> dict[str, Any]:
    """Build the durable proof that every reviewed row matched at activation.

    Current matches may later rotate out of the bounded source window.  The
    activation proof therefore carries the original full entry set and its
    digest forever; later receipts may report entries inactive but may never
    mint, replace, or weaken this attestation.
    """
    if not isinstance(manifest, Mapping) or _HEX_SHA256.fullmatch(manifest_sha256) is None:
        raise ValueError("historical suppression activation manifest is invalid")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("historical suppression activation entries are invalid")
    normalized_entries = [dict(entry) for entry in entries]
    entry_keys = [historical_suppression_entry_key(entry) for entry in normalized_entries]
    if entry_keys != sorted(entry_keys) or len(entry_keys) != len(set(entry_keys)):
        raise ValueError("historical suppression activation entries are not canonical")
    reviewed_at = _instant(manifest.get("reviewed_at"))
    activation_clock = _instant(activated_at)
    if reviewed_at is None or activation_clock is None or activation_clock < reviewed_at:
        raise ValueError("historical suppression activation clock is invalid")
    predecessor = manifest.get("predecessor")
    if not isinstance(predecessor, Mapping):
        raise ValueError("historical suppression activation predecessor is invalid")
    source_entry_set_sha256 = sha256(
        _canonical_json(normalized_entries).encode("utf-8")
    ).hexdigest()
    payload = {
        "contract": HISTORICAL_SUPPRESSION_ACTIVATION_CONTRACT,
        "manifest_sha256": manifest_sha256,
        "predecessor_queue_content_id": predecessor.get("queue_content_id"),
        "prior_frozen_at": predecessor.get("projection_generated_at"),
        "activated_at": activated_at,
        "matched_entry_count": len(normalized_entries),
        "inactive_entry_count": 0,
        "source_entry_set_sha256": source_entry_set_sha256,
        "entries": normalized_entries,
    }
    activation_id = "grcsa1-" + sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()[:24]
    return {**payload, "activation_id": activation_id}


def load_candidate_historical_suppression_manifest(
    root: Path,
) -> tuple[dict[str, Any], str] | None:
    """Load the optional reviewed manifest and bind its exact checked-in bytes."""
    root = Path(root).resolve()
    manifest_path = root / HISTORICAL_SUPPRESSION_CONFIG_PATH
    if not manifest_path.exists():
        return None
    schema_path = root / HISTORICAL_SUPPRESSION_SCHEMA_PATH
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_no_duplicate_object
        )
        schema = json.loads(
            schema_path.read_text(encoding="utf-8"),
            object_pairs_hook=_no_duplicate_object,
        )
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(manifest),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("historical suppression manifest or schema is unreadable") from exc
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "root"
        raise ValueError(
            f"historical suppression manifest violates its schema at {location}: {first.message}"
        )
    if not isinstance(manifest, dict):
        raise ValueError("historical suppression manifest must be an object")
    if manifest.get("contract") != HISTORICAL_SUPPRESSION_CONTRACT:
        raise ValueError("historical suppression manifest contract is invalid")
    if manifest.get("authority") != _historical_suppression_authority():
        raise ValueError("historical suppression manifest authority is invalid")
    entries = manifest.get("entries")
    predecessor = manifest.get("predecessor")
    if not isinstance(entries, list) or not isinstance(predecessor, Mapping):
        raise ValueError("historical suppression manifest shape is invalid")
    keys = [historical_suppression_entry_key(entry) for entry in entries]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise ValueError("historical suppression entries must be unique and sorted")
    predecessor_at = _instant(predecessor.get("projection_generated_at"))
    reviewed_at = _instant(manifest.get("reviewed_at"))
    if predecessor_at is None or reviewed_at is None or reviewed_at < predecessor_at:
        raise ValueError("historical suppression manifest clocks are invalid")
    for entry in entries:
        observed_at = _instant(entry.get("observed_known_at"))
        if observed_at is None or observed_at > predecessor_at:
            raise ValueError(
                "historical suppression entry is not behind the declared predecessor"
            )
    return manifest, sha256(raw).hexdigest()


def issuance_correction_entry_key(entry: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the immutable official-source identity of one corrected issuance."""
    return historical_suppression_entry_key(entry)


def _canonical_value_sha256(value: Any) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate correction row is not canonical JSON") from exc
    return sha256(raw).hexdigest()


def candidate_issuance_correction_entry(row: Mapping[str, Any]) -> dict[str, Any]:
    """Bind one immutable ledger row to its exact official-source identity."""
    if not isinstance(row, Mapping):
        raise ValueError("candidate correction row must be an object")
    source_event = row.get("source_event")
    if not isinstance(source_event, Mapping):
        raise ValueError("candidate correction source event is invalid")
    entry = {
        "candidate_id": row.get("candidate_id"),
        "observation_id": row.get("observation_id"),
        "candidate_family": row.get("candidate_family"),
        "source_event_id": source_event.get("event_id"),
        "source_record_id": source_event.get("record_id"),
        "source_rail": source_event.get("source_rail"),
        "source_content_sha256": source_event.get("source_content_id"),
        "observed_known_at": row.get("known_at"),
        "issued_generated_at": row.get("generated_at"),
        "issued_row_sha256": _canonical_value_sha256(row),
    }
    issuance_correction_entry_key(entry)
    for field in (
        "observation_id",
        "candidate_family",
        "observed_known_at",
        "issued_generated_at",
    ):
        if not isinstance(entry[field], str) or not entry[field]:
            raise ValueError(f"candidate correction {field} is invalid")
    if _HEX_SHA256.fullmatch(entry["source_content_sha256"]) is None:
        raise ValueError("candidate correction source_content_sha256 is invalid")
    return entry


def candidate_issuance_correction_activation(
    manifest: Mapping[str, Any],
    manifest_sha256: str,
    *,
    activated_at: str,
) -> dict[str, Any]:
    """Build the durable proof that all incident rows were exactly quarantined."""
    if not isinstance(manifest, Mapping) or _HEX_SHA256.fullmatch(manifest_sha256) is None:
        raise ValueError("candidate correction activation manifest is invalid")
    entries = manifest.get("entries")
    incident = manifest.get("incident")
    if not isinstance(entries, list) or not entries or not isinstance(incident, Mapping):
        raise ValueError("candidate correction activation shape is invalid")
    normalized_entries = [dict(entry) for entry in entries]
    entry_keys = [issuance_correction_entry_key(entry) for entry in normalized_entries]
    if entry_keys != sorted(entry_keys) or len(entry_keys) != len(set(entry_keys)):
        raise ValueError("candidate correction activation entries are not canonical")
    reviewed_at = _instant(manifest.get("reviewed_at"))
    activation_clock = _instant(activated_at)
    if reviewed_at is None or activation_clock is None or activation_clock < reviewed_at:
        raise ValueError("candidate correction activation clock is invalid")
    issued_entry_set_sha256 = sha256(
        _canonical_json(normalized_entries).encode("utf-8")
    ).hexdigest()
    payload = {
        "contract": ISSUANCE_CORRECTION_ACTIVATION_CONTRACT,
        "manifest_sha256": manifest_sha256,
        "incident_id": incident.get("incident_id"),
        "publication_commit_sha": incident.get("publication_commit_sha"),
        "issued_queue_content_id": incident.get("issued_queue_content_id"),
        "issued_projection_generated_at": incident.get(
            "issued_projection_generated_at"
        ),
        "issued_queue_sha256": incident.get("issued_queue_sha256"),
        "issued_projection_state_sha256": incident.get(
            "issued_projection_state_sha256"
        ),
        "issued_ledger_sha256": incident.get("issued_ledger_sha256"),
        "issued_ledger_byte_count": incident.get("issued_ledger_byte_count"),
        "issued_ledger_line_count": incident.get("issued_ledger_line_count"),
        "activated_at": activated_at,
        "matched_issued_count": len(normalized_entries),
        "issued_entry_set_sha256": issued_entry_set_sha256,
        "entries": normalized_entries,
    }
    activation_id = "grcica1-" + sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()[:24]
    return {**payload, "activation_id": activation_id}


def load_candidate_issuance_correction_manifest(
    root: Path,
) -> tuple[dict[str, Any], str] | None:
    """Load and semantically bind the separate append-only incident correction."""
    root = Path(root).resolve()
    manifest_path = root / ISSUANCE_CORRECTION_CONFIG_PATH
    if not manifest_path.exists():
        return None
    schema_path = root / ISSUANCE_CORRECTION_SCHEMA_PATH
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_no_duplicate_object
        )
        schema = json.loads(
            schema_path.read_text(encoding="utf-8"),
            object_pairs_hook=_no_duplicate_object,
        )
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(manifest),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("candidate correction manifest or schema is unreadable") from exc
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "root"
        raise ValueError(
            f"candidate correction manifest violates its schema at {location}: {first.message}"
        )
    if not isinstance(manifest, dict) or manifest.get("contract") != ISSUANCE_CORRECTION_CONTRACT:
        raise ValueError("candidate correction manifest contract is invalid")
    if manifest.get("authority") != _historical_suppression_authority():
        raise ValueError("candidate correction manifest authority is invalid")
    incident = manifest.get("incident")
    original_review = manifest.get("original_review")
    entries = manifest.get("entries")
    if (
        not isinstance(incident, Mapping)
        or not isinstance(original_review, Mapping)
        or not isinstance(entries, list)
    ):
        raise ValueError("candidate correction manifest shape is invalid")
    publication_commit = incident.get("publication_commit_sha")
    if (
        not isinstance(publication_commit, str)
        or incident.get("incident_id") != "grcii1-" + publication_commit[:24]
        or incident.get("issued_ledger_line_count") != len(entries)
    ):
        raise ValueError("candidate correction incident identity is invalid")
    keys = [issuance_correction_entry_key(entry) for entry in entries]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise ValueError("candidate correction entries must be unique and sorted")
    suppression = load_candidate_historical_suppression_manifest(root)
    if suppression is None:
        raise ValueError("candidate correction lacks its original reviewed manifest")
    suppression_manifest, suppression_sha256 = suppression
    suppression_predecessor = suppression_manifest.get("predecessor")
    if (
        original_review.get("manifest_sha256") != suppression_sha256
        or original_review.get("reviewed_at") != suppression_manifest.get("reviewed_at")
        or not isinstance(suppression_predecessor, Mapping)
        or original_review.get("predecessor_queue_content_id")
        != suppression_predecessor.get("queue_content_id")
        or original_review.get("predecessor_projection_generated_at")
        != suppression_predecessor.get("projection_generated_at")
    ):
        raise ValueError("candidate correction original review binding is invalid")
    reviewed_at = _instant(manifest.get("reviewed_at"))
    issued_at = _instant(incident.get("issued_projection_generated_at"))
    first_notice_at = _instant(incident.get("first_issuance_notice_at"))
    if (
        reviewed_at is None
        or issued_at is None
        or first_notice_at is None
        or reviewed_at < issued_at
        or issued_at < first_notice_at
    ):
        raise ValueError("candidate correction incident clocks are invalid")
    suppression_by_key = {
        historical_suppression_entry_key(entry): entry
        for entry in suppression_manifest["entries"]
    }
    if set(keys) != set(suppression_by_key):
        raise ValueError("candidate correction does not exactly cover the original review")
    for entry in entries:
        suppression_entry = suppression_by_key[issuance_correction_entry_key(entry)]
        if (
            entry.get("candidate_family") != suppression_entry.get("candidate_family")
            or entry.get("observed_known_at") != suppression_entry.get("observed_known_at")
        ):
            raise ValueError("candidate correction entry differs from the original review")
    return manifest, sha256(raw).hexdigest()


def _current_historical_suppression_entries(
    *,
    manifest_by_key: Mapping[tuple[str, ...], Mapping[str, Any]],
    current_observations: Sequence[Mapping[str, Any]] | None,
    issued_observations: Sequence[Mapping[str, Any]],
    require_observed_known_at: bool,
) -> tuple[list[dict[str, Any]] | None, set[tuple[str, ...]]]:
    """Re-derive the exact currently visible unissued manifest entries."""
    if isinstance(issued_observations, (str, bytes)):
        raise ValueError("candidate suppression issued observations are invalid")
    issued_keys: set[tuple[str, ...]] = set()
    for index, row in enumerate(issued_observations, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(
                f"candidate suppression issued observation {index} is invalid"
            )
        issued_keys.add(
            historical_suppression_entry_key(
                candidate_historical_suppression_entry(row)
            )
        )
    manifest_keys = set(manifest_by_key)
    if manifest_keys.intersection(issued_keys):
        raise ValueError("a reviewed historical source identity was issued as a candidate")
    if current_observations is None:
        return None, issued_keys
    if isinstance(current_observations, (str, bytes)):
        raise ValueError("candidate suppression current source rows are invalid")
    current_by_key: dict[tuple[str, ...], dict[str, Any]] = {}
    for index, row in enumerate(current_observations, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(
                f"candidate suppression current source row {index} is invalid"
            )
        current_entry = candidate_historical_suppression_entry(row)
        key = historical_suppression_entry_key(current_entry)
        if key in issued_keys:
            continue
        if key in current_by_key:
            raise ValueError(
                "candidate suppression current source rows duplicate a stable identity"
            )
        reviewed_entry = manifest_by_key.get(key)
        if reviewed_entry is None:
            raise ValueError(
                "an unissued current source row has no reviewed historical suppression"
            )
        comparable = dict(current_entry)
        if not require_observed_known_at:
            comparable["observed_known_at"] = reviewed_entry["observed_known_at"]
        if comparable != reviewed_entry:
            raise ValueError(
                "candidate suppression current source identity differs from review"
            )
        current_by_key[key] = dict(reviewed_entry)
    return [current_by_key[key] for key in sorted(current_by_key)], issued_keys


def validate_candidate_historical_suppression_binding(
    queue: Mapping[str, Any],
    projection_state: Mapping[str, Any],
    *,
    root: Path,
    allow_exact_legacy_predecessor: bool = True,
    current_observations: Sequence[Mapping[str, Any]] | None = None,
    issued_observations: Sequence[Mapping[str, Any]] = (),
    require_exact_activation: bool = False,
    require_manifest: bool = False,
) -> dict[str, Any]:
    """Validate manifest, current source rows, and queue disclosure as one claim."""
    loaded = load_candidate_historical_suppression_manifest(root)
    coverage = queue.get("coverage")
    receipt = coverage.get("historical_candidate_suppression") if isinstance(coverage, Mapping) else None
    source_content_ids = queue.get("source_content_ids")
    suppression_source_ids = {
        value
        for value in source_content_ids
        if isinstance(value, str)
        and value.startswith(HISTORICAL_SUPPRESSION_SOURCE_PREFIX)
    } if isinstance(source_content_ids, list) else set()
    if loaded is None:
        if require_manifest:
            raise ValueError("candidate suppression manifest is required")
        if receipt is not None or suppression_source_ids:
            raise ValueError("candidate suppression lineage has no reviewed manifest")
        return {"status": "absent"}

    manifest, manifest_sha256 = loaded
    predecessor = manifest["predecessor"]
    manifest_entries = manifest["entries"]
    manifest_by_key = {
        historical_suppression_entry_key(entry): entry for entry in manifest_entries
    }
    expected_current_entries, _issued_keys = _current_historical_suppression_entries(
        manifest_by_key=manifest_by_key,
        current_observations=current_observations,
        issued_observations=issued_observations,
        require_observed_known_at=(require_exact_activation or receipt is None),
    )
    if receipt is None:
        if (
            allow_exact_legacy_predecessor
            and queue.get("content_id") == predecessor["queue_content_id"]
            and projection_state.get("generated_at")
            == predecessor["projection_generated_at"]
            and not suppression_source_ids
        ):
            return {
                "status": "legacy_predecessor",
                "manifest_sha256": manifest_sha256,
                "visible_reviewed_count": len(expected_current_entries or ()),
            }
        raise ValueError("candidate queue omits the current suppression receipt")
    if not isinstance(receipt, Mapping):
        raise ValueError("candidate suppression receipt is malformed")
    reviewed_at = _instant(manifest.get("reviewed_at"))
    generated_at = _instant(projection_state.get("generated_at"))
    if reviewed_at is None or generated_at is None or generated_at < reviewed_at:
        raise ValueError("candidate suppression receipt predates its reviewed manifest")
    matched_entries = receipt.get("entries")
    activation = receipt.get("activation")
    expected_source_id = HISTORICAL_SUPPRESSION_SOURCE_PREFIX + manifest_sha256
    if (
        receipt.get("contract") != HISTORICAL_SUPPRESSION_APPLICATION_CONTRACT
        or receipt.get("manifest_sha256") != manifest_sha256
        or receipt.get("policy") != "exact_source_identity_only"
        or receipt.get("decision") != "do_not_backfill"
        or receipt.get("predecessor_queue_content_id") != predecessor["queue_content_id"]
        or receipt.get("prior_frozen_at") != predecessor["projection_generated_at"]
        or receipt.get("manifest_entry_count") != len(manifest_entries)
        or not isinstance(matched_entries, list)
        or receipt.get("matched_count") != len(matched_entries)
        or receipt.get("inactive_count") != len(manifest_entries) - len(matched_entries)
        or suppression_source_ids != {expected_source_id}
        or not isinstance(activation, Mapping)
    ):
        raise ValueError("candidate suppression receipt binding is invalid")
    try:
        expected_activation = candidate_historical_suppression_activation(
            manifest,
            manifest_sha256,
            activated_at=activation.get("activated_at"),
        )
    except ValueError as exc:
        raise ValueError("candidate suppression activation is invalid") from exc
    activation_clock = _instant(activation.get("activated_at"))
    if (
        dict(activation) != expected_activation
        or activation_clock is None
        or generated_at < activation_clock
    ):
        raise ValueError("candidate suppression activation binding is invalid")
    matched_keys = [historical_suppression_entry_key(entry) for entry in matched_entries]
    if matched_keys != sorted(matched_keys) or len(matched_keys) != len(set(matched_keys)):
        raise ValueError("candidate suppression receipt entries are not unique and sorted")
    if any(
        key not in manifest_by_key
        or dict(matched_entries[index]) != dict(manifest_by_key[key])
        for index, key in enumerate(matched_keys)
    ):
        raise ValueError("candidate suppression receipt is detached from its manifest")
    if require_exact_activation and expected_current_entries is None:
        raise ValueError("candidate suppression activation lacks current source rows")
    if expected_current_entries is not None:
        if [dict(entry) for entry in matched_entries] != expected_current_entries:
            raise ValueError("candidate suppression receipt does not match current source rows")
        if require_exact_activation and len(expected_current_entries) != len(manifest_entries):
            raise ValueError(
                "candidate suppression activation is not an exact manifest/source bijection"
            )
    if generated_at == activation_clock and (
        [dict(entry) for entry in matched_entries]
        != [dict(entry) for entry in manifest_entries]
        or receipt.get("inactive_count") != 0
    ):
        raise ValueError(
            "candidate suppression first activation did not bind the full source bijection"
        )

    candidates = queue.get("candidates")
    recently_matured = queue.get("recently_matured", [])
    freshness = queue.get("freshness")
    if not isinstance(candidates, list) or not isinstance(recently_matured, list) or not isinstance(freshness, Mapping):
        raise ValueError("candidate suppression queue context is invalid")
    published_keys: set[tuple[str, ...]] = set()
    for row in (*candidates, *recently_matured):
        if not isinstance(row, Mapping):
            raise ValueError("candidate suppression queue row is invalid")
        published_keys.add(
            historical_suppression_entry_key(
                candidate_historical_suppression_entry(row)
            )
        )
    if set(manifest_by_key).intersection(published_keys):
        raise ValueError("a reviewed historical source identity is present in the queue")
    availability = freshness.get("exact_candidate_availability")
    if candidates and availability != "available":
        raise ValueError("candidate suppression cannot hide available forward candidates")
    if not candidates and matched_entries and availability != "withheld_historical":
        raise ValueError("candidate suppression zero queue lacks withheld disclosure")
    if not matched_entries and availability == "withheld_historical":
        raise ValueError("candidate queue claims a suppression that matched no row")
    return {
        "status": "bound",
        "manifest_sha256": manifest_sha256,
        "matched_count": len(matched_entries),
    }


def validate_candidate_issuance_correction_binding(
    queue: Mapping[str, Any],
    projection_state: Mapping[str, Any],
    *,
    root: Path,
    current_observations: Sequence[Mapping[str, Any]] | None = None,
    issued_observations: Sequence[Mapping[str, Any]] = (),
    allow_exact_incident_predecessor: bool = False,
    queue_raw_sha256: str | None = None,
    projection_state_raw_sha256: str | None = None,
    require_correction: bool = False,
) -> dict[str, Any]:
    """Validate one exact append-only correction without weakening suppression."""
    loaded = load_candidate_issuance_correction_manifest(root)
    if loaded is None:
        if require_correction:
            raise ValueError("candidate issuance correction manifest is required")
        return {"status": "absent"}
    manifest, manifest_sha256 = loaded
    incident = manifest["incident"]
    manifest_entries = [dict(entry) for entry in manifest["entries"]]
    entry_count = len(manifest_entries)
    if isinstance(issued_observations, (str, bytes)):
        raise ValueError("candidate correction issued observations are invalid")
    issued_rows = list(issued_observations)
    if len(issued_rows) < entry_count:
        raise ValueError("candidate correction ledger prefix is incomplete")
    prefix_rows = issued_rows[:entry_count]
    if any(not isinstance(row, Mapping) for row in prefix_rows):
        raise ValueError("candidate correction ledger prefix row is invalid")
    prefix_entries = [candidate_issuance_correction_entry(row) for row in prefix_rows]
    prefix_raw = b"".join(
        json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
        for row in prefix_rows
    )
    if (
        prefix_entries != manifest_entries
        or sha256(prefix_raw).hexdigest() != incident["issued_ledger_sha256"]
        or len(prefix_raw) != incident["issued_ledger_byte_count"]
    ):
        raise ValueError("candidate correction ledger prefix differs from the incident")

    coverage = queue.get("coverage")
    receipt = (
        coverage.get("historical_candidate_issuance_correction")
        if isinstance(coverage, Mapping)
        else None
    )
    suppression_receipt = (
        coverage.get("historical_candidate_suppression")
        if isinstance(coverage, Mapping)
        else None
    )
    source_content_ids = queue.get("source_content_ids")
    if not isinstance(source_content_ids, list):
        raise ValueError("candidate correction queue source ids are invalid")
    correction_source_ids = {
        value
        for value in source_content_ids
        if isinstance(value, str)
        and value.startswith(ISSUANCE_CORRECTION_SOURCE_PREFIX)
    }
    suppression_source_ids = {
        value
        for value in source_content_ids
        if isinstance(value, str)
        and value.startswith(HISTORICAL_SUPPRESSION_SOURCE_PREFIX)
    }
    if suppression_receipt is not None or suppression_source_ids:
        raise ValueError("candidate correction cannot claim historical non-issuance")

    ledger_binding = projection_state.get("ledger")
    if not isinstance(ledger_binding, Mapping):
        raise ValueError("candidate correction projection ledger binding is invalid")
    if receipt is None:
        if not allow_exact_incident_predecessor:
            raise ValueError("uncorrected candidate issuance incident cannot be served")
        queue_rows = queue.get("candidates")
        if (
            queue.get("content_id") != incident["issued_queue_content_id"]
            or projection_state.get("generated_at")
            != incident["issued_projection_generated_at"]
            or ledger_binding.get("sha256") != incident["issued_ledger_sha256"]
            or ledger_binding.get("byte_count") != incident["issued_ledger_byte_count"]
            or ledger_binding.get("line_count") != incident["issued_ledger_line_count"]
            or len(issued_rows) != entry_count
            or correction_source_ids
            or queue_raw_sha256 != incident["issued_queue_sha256"]
            or projection_state_raw_sha256
            != incident["issued_projection_state_sha256"]
            or not isinstance(queue_rows, list)
            or [candidate_issuance_correction_entry(row) for row in queue_rows]
            != manifest_entries
        ):
            raise ValueError("candidate issuance incident predecessor is not exact")
        return {
            "status": "uncorrected_incident",
            "manifest_sha256": manifest_sha256,
            "issued_count": entry_count,
        }

    expected_source_id = ISSUANCE_CORRECTION_SOURCE_PREFIX + manifest_sha256
    entries = receipt.get("entries") if isinstance(receipt, Mapping) else None
    activation = receipt.get("activation") if isinstance(receipt, Mapping) else None
    original_review = manifest["original_review"]
    if (
        not isinstance(receipt, Mapping)
        or receipt.get("contract") != ISSUANCE_CORRECTION_APPLICATION_CONTRACT
        or receipt.get("manifest_sha256") != manifest_sha256
        or receipt.get("incident_id") != incident["incident_id"]
        or receipt.get("original_review_manifest_sha256")
        != original_review["manifest_sha256"]
        or receipt.get("policy") != "exact_issued_source_identity_only"
        or receipt.get("decision") != "quarantine_erroneous_historical_issuance"
        or receipt.get("issued_queue_content_id")
        != incident["issued_queue_content_id"]
        or receipt.get("issued_projection_generated_at")
        != incident["issued_projection_generated_at"]
        or receipt.get("issued_ledger_sha256") != incident["issued_ledger_sha256"]
        or receipt.get("issued_ledger_byte_count")
        != incident["issued_ledger_byte_count"]
        or receipt.get("issued_ledger_line_count")
        != incident["issued_ledger_line_count"]
        or receipt.get("entry_count") != entry_count
        or receipt.get("matched_issued_count") != entry_count
        or receipt.get("quarantined_count") != entry_count
        or entries != manifest_entries
        or correction_source_ids != {expected_source_id}
        or not isinstance(activation, Mapping)
    ):
        raise ValueError("candidate issuance correction receipt binding is invalid")
    try:
        expected_activation = candidate_issuance_correction_activation(
            manifest,
            manifest_sha256,
            activated_at=activation.get("activated_at"),
        )
    except ValueError as exc:
        raise ValueError("candidate issuance correction activation is invalid") from exc
    generated_at = _instant(projection_state.get("generated_at"))
    activated_at = _instant(activation.get("activated_at"))
    if (
        dict(activation) != expected_activation
        or generated_at is None
        or activated_at is None
        or generated_at < activated_at
    ):
        raise ValueError("candidate issuance correction activation binding is invalid")
    if generated_at == activated_at and (
        len(issued_rows) != entry_count
        or ledger_binding.get("sha256") != incident["issued_ledger_sha256"]
        or ledger_binding.get("byte_count") != incident["issued_ledger_byte_count"]
        or ledger_binding.get("line_count") != incident["issued_ledger_line_count"]
        or ledger_binding.get("append_count") != 0
    ):
        raise ValueError("candidate correction activation changed the incident ledger")
    if current_observations is not None and generated_at == activated_at:
        if isinstance(current_observations, (str, bytes)):
            raise ValueError("candidate correction current observations are invalid")
        reviewed = load_candidate_historical_suppression_manifest(root)
        if reviewed is None:
            raise ValueError("candidate correction original review is unavailable")
        suppression_by_key = {
            historical_suppression_entry_key(entry): entry
            for entry in reviewed[0]["entries"]
        }
        current_by_key: dict[tuple[str, ...], dict[str, Any]] = {}
        for row in current_observations:
            current_entry = candidate_historical_suppression_entry(row)
            key = historical_suppression_entry_key(current_entry)
            if key not in suppression_by_key:
                continue
            comparable = dict(current_entry)
            comparable["observed_known_at"] = suppression_by_key[key][
                "observed_known_at"
            ]
            if comparable != suppression_by_key[key] or key in current_by_key:
                raise ValueError("candidate correction current source identity is invalid")
            current_by_key[key] = comparable
        if set(current_by_key) != set(suppression_by_key):
            raise ValueError("candidate correction activation lacks the exact source bijection")

    candidates = queue.get("candidates")
    recently_matured = queue.get("recently_matured", [])
    freshness = queue.get("freshness")
    if (
        not isinstance(candidates, list)
        or not isinstance(recently_matured, list)
        or not isinstance(freshness, Mapping)
    ):
        raise ValueError("candidate correction queue context is invalid")
    corrected_keys = {
        issuance_correction_entry_key(entry) for entry in manifest_entries
    }
    for row in (*candidates, *recently_matured):
        if not isinstance(row, Mapping):
            raise ValueError("candidate correction queue row is invalid")
        if historical_suppression_entry_key(
            candidate_historical_suppression_entry(row)
        ) in corrected_keys:
            raise ValueError("a quarantined issuance remains on an active surface")
    availability = freshness.get("exact_candidate_availability")
    active_rows = [*candidates, *recently_matured]
    if active_rows and availability != "available":
        raise ValueError("candidate correction cannot hide forward candidates")
    if not active_rows and availability != "quarantined_historical_issuance":
        raise ValueError("candidate correction zero queue lacks quarantine disclosure")
    return {
        "status": "corrected",
        "manifest_sha256": manifest_sha256,
        "quarantined_count": entry_count,
    }


def validate_candidate_reviewed_history_binding(
    queue: Mapping[str, Any],
    projection_state: Mapping[str, Any],
    *,
    root: Path,
    allow_exact_legacy_predecessor: bool = True,
    allow_exact_incident_predecessor: bool = False,
    current_observations: Sequence[Mapping[str, Any]] | None = None,
    issued_observations: Sequence[Mapping[str, Any]] = (),
    require_exact_activation: bool = False,
    require_manifest: bool = False,
    queue_raw_sha256: str | None = None,
    projection_state_raw_sha256: str | None = None,
) -> dict[str, Any]:
    """Route to non-issuance or correction without conflating their claims."""
    if load_candidate_issuance_correction_manifest(root) is not None:
        return validate_candidate_issuance_correction_binding(
            queue,
            projection_state,
            root=root,
            current_observations=current_observations,
            issued_observations=issued_observations,
            allow_exact_incident_predecessor=allow_exact_incident_predecessor,
            queue_raw_sha256=queue_raw_sha256,
            projection_state_raw_sha256=projection_state_raw_sha256,
            require_correction=require_manifest,
        )
    return validate_candidate_historical_suppression_binding(
        queue,
        projection_state,
        root=root,
        allow_exact_legacy_predecessor=allow_exact_legacy_predecessor,
        current_observations=current_observations,
        issued_observations=issued_observations,
        require_exact_activation=require_exact_activation,
        require_manifest=require_manifest,
    )


def _digest(prefix: str, value: Any) -> str:
    return f"{prefix}-{sha256(_canonical_json(value).encode('utf-8')).hexdigest()[:24]}"


def _without_queue_volatile_fields(value: Any) -> Any:
    """Drop generated-at envelope values before calculating a queue content ID."""
    if isinstance(value, Mapping):
        return {
            key: _without_queue_volatile_fields(child)
            for key, child in value.items()
            if key not in {"content_id", "generated_at"}
        }
    if isinstance(value, list):
        return [_without_queue_volatile_fields(child) for child in value]
    return value


def candidate_queue_content_id(payload: Mapping[str, Any]) -> str:
    """Return the deterministic queue ID, excluding envelope/content generation time.

    Writers and serving code must recompute this value instead of trusting an
    artifact-provided ID.  ``generated_at`` is excluded at every nesting level:
    it is delivery metadata and is not source evidence or candidate identity.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("candidate queue must be a mapping")
    return _digest("grcq1", _without_queue_volatile_fields(payload))


def candidate_latest_semantic_sha256(payload: Mapping[str, Any]) -> str:
    """Fingerprint every candidate-relevant latest field without delivery clocks.

    The mapping backlog consumes top-level company coverage while exact
    candidates consume the embedded procurement workspace.  Binding only the
    workspace would therefore allow a stale company backlog to survive a
    changed latest generation.  ``generated_at`` is assembly metadata at every
    nesting level and is the sole excluded field.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("candidate latest payload must be a mapping")
    def without_delivery_clock(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: without_delivery_clock(child)
                for key, child in value.items()
                if key != "generated_at"
            }
        if isinstance(value, list):
            return [without_delivery_clock(child) for child in value]
        return value

    return sha256(
        _canonical_json(without_delivery_clock(payload)).encode("utf-8")
    ).hexdigest()


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _iso(value: Any, *, end_of_day: bool = False) -> str | None:
    """Return a normalized UTC instant, accepting the contracts' date values."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max if end_of_day else time.min)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            try:
                parsed = datetime.combine(date.fromisoformat(raw), time.max if end_of_day else time.min)
            except ValueError:
                return None
        else:
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _instant(value: Any, *, end_of_day: bool = False) -> datetime | None:
    normalized = _iso(value, end_of_day=end_of_day)
    return datetime.fromisoformat(normalized) if normalized is not None else None


def _source_graph(loaded: Mapping[str, Any]) -> Mapping[str, Any]:
    strict_source = loaded.get("_strict_source_graph")
    if isinstance(strict_source, Mapping):
        return strict_source
    graph = loaded.get("graph")
    return graph if isinstance(graph, Mapping) else {}


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _as_rows(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _reviewed_exact_graph_tickers(
    loaded: Mapping[str, Any], *, analysis_as_of: datetime
) -> set[str]:
    """Return tickers reached by at least one active exact identifier path."""
    if loaded.get("status") != "ready":
        return set()
    record_fields = {
        "sam_uei": "recipient_uei",
        "cage": "recipient_cage",
        "usaspending_recipient_id": "usaspending_recipient_id",
    }
    tickers: set[str] = set()
    for ordinal, identifier in enumerate(_as_rows(_source_graph(loaded).get("identifiers"))):
        namespace = _text(identifier.get("namespace"))
        value = _text(identifier.get("value"))
        field = record_fields.get(namespace or "")
        if field is None or value is None:
            continue
        resolution = entity_resolution.resolve_recipient(
            {
                "source_record_key": f"graph-coverage:{ordinal}",
                "source_record_identity_stable": True,
                field: value,
                "effective_at": analysis_as_of.isoformat(),
                "known_at": analysis_as_of.isoformat(),
            },
            loaded,
            as_of=analysis_as_of,
        )
        issuer = _as_mapping(resolution.get("issuer")) or {}
        ticker = _text(issuer.get("ticker"))
        if resolution.get("resolution_state") in {"confirmed", "reviewed"} and ticker:
            tickers.add(ticker)
    return tickers


def _graph_evidence_content_ids(
    loaded: Mapping[str, Any], evidence_refs: Sequence[str]
) -> set[str]:
    wanted = set(evidence_refs)
    return {
        digest
        for row in _as_rows(_source_graph(loaded).get("evidence"))
        if _text(row.get("evidence_id")) in wanted
        and (digest := _text(row.get("content_sha256"))) is not None
    }


def _row_active(row: Mapping[str, Any], *, effective_at: datetime, analysis_as_of: datetime) -> bool:
    """The graph contract requires evidence refs, which are strings rather than rows."""
    known_at = _instant(row.get("known_at"))
    valid_from = _instant(row.get("valid_from"))
    valid_to = _instant(row.get("valid_to")) if row.get("valid_to") is not None else None
    evidence_refs = [ref for ref in row.get("evidence_refs", []) if _text(ref)] if isinstance(row.get("evidence_refs"), list) else []
    return bool(
        known_at is not None
        and valid_from is not None
        and known_at <= analysis_as_of
        and valid_from <= effective_at
        and (valid_to is None or effective_at <= valid_to)
        and evidence_refs
    )


def _event_freshness(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    workspace = _as_mapping(payload.get("procurement_workspace")) or {}
    freshness = _as_mapping(workspace.get("freshness")) or {}
    return _as_mapping(freshness.get("award_events")) or {}


def _workspace(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return _as_mapping(payload.get("procurement_workspace")) or {}


def _workspace_content_id(payload: Mapping[str, Any]) -> str:
    workspace = _workspace(payload)
    bundle_id = _text(workspace.get("bundle_id"))
    if bundle_id:
        return bundle_id
    return f"workspace-sha256:{sha256(_canonical_json(workspace).encode('utf-8')).hexdigest()}"


def _graph_content_id(loaded: Mapping[str, Any]) -> str:
    digest = _text(loaded.get("graph_digest"))
    return f"graph-sha256:{digest}" if digest else "graph-sha256:unavailable"


def _official_receipt(receipt: Mapping[str, Any], *, analysis_as_of: datetime) -> dict[str, Any] | None:
    ref_id = _text(receipt.get("ref_id"))
    record_id = _text(receipt.get("record_id"))
    content_sha256 = _text(receipt.get("content_sha256"))
    effective_at = _instant(receipt.get("effective_at"))
    known_at = _instant(receipt.get("known_at"))
    publisher = (_text(receipt.get("publisher")) or "").lower()
    url = _text(receipt.get("url")) or ""
    url_lower = url.lower()
    if not (
        ref_id
        and record_id
        and content_sha256
        and _HEX_SHA256.fullmatch(content_sha256)
        and effective_at is not None
        and known_at is not None
        and known_at <= analysis_as_of
        and "usaspending" in publisher
        and (url_lower.startswith("https://api.usaspending.gov/") or url_lower.startswith("https://www.usaspending.gov/"))
    ):
        return None
    return {
        "ref_id": ref_id,
        "record_id": record_id,
        "content_sha256": content_sha256,
        "effective_at": effective_at.isoformat(),
        "known_at": known_at.isoformat(),
        # Internal admission-only value.  It is stripped before the bounded
        # candidate contract is published.
        "_source_url": url,
    }


def _receipt_bound_event(event: Mapping[str, Any], *, analysis_as_of: datetime) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    if event.get("kind") != "award_change":
        return None
    award_change = _as_mapping(event.get("award_change"))
    evidence = _as_mapping(event.get("evidence"))
    change = _as_mapping(event.get("change"))
    if award_change is None or evidence is None or change is None:
        return None
    event_type = _text(award_change.get("event_type")) or _text(change.get("type"))
    source_rail = _text(award_change.get("source_rail"))
    source_identity = _as_mapping(award_change.get("source_identity"))
    source_content_id = _text(source_identity.get("content_sha256")) if source_identity else None
    effective_at = _instant(change.get("effective_at"))
    known_at = _instant(change.get("known_at"))
    if not (
        event_type in _SUPPORTED_FAMILIES
        and source_rail in {"usaspending_award_snapshot", "usaspending_award_action"}
        and source_content_id
        and _HEX_SHA256.fullmatch(source_content_id)
        and evidence.get("source_class") in {"official_fact", "observed_source_revision"}
        and evidence.get("mapping_class") == "reviewed"
        and not _as_rows(evidence.get("conflicts"))
        and effective_at is not None
        and known_at is not None
        and known_at <= analysis_as_of
    ):
        return None
    if event_type == "new_award" and award_change.get("is_late_discovery") is not False:
        return None
    receipts = [_official_receipt(row, analysis_as_of=analysis_as_of) for row in _as_rows(evidence.get("receipts"))]
    usable = [row for row in receipts if row is not None]
    if not usable:
        return None
    event_record_ids = {
        value
        for value in (
            _text(event.get("record_id")),
            _text(award_change.get("award_key")),
            _text(award_change.get("generated_award_id")),
            _text(award_change.get("piid")),
        )
        if value
    }
    event_record_ids.update(
        value.removeprefix("award:")
        for value in list(event_record_ids)
        if value.startswith("award:")
    )
    if not event_record_ids or any(receipt["record_id"] not in event_record_ids for receipt in usable):
        return None
    if source_content_id not in {receipt["content_sha256"] for receipt in usable}:
        return None
    return (
        {
            "event_id": _text(event.get("event_id")),
            "record_id": _text(event.get("record_id")),
            "event_type": event_type,
            "source_rail": source_rail,
            "source_content_id": source_content_id,
            "is_late_discovery": bool(award_change.get("is_late_discovery")),
            "effective_at": effective_at,
            "known_at": known_at,
            "change_summary": _text(change.get("what_changed_en")) or event_type.replace("_", " "),
        },
        usable,
    ) if _text(event.get("event_id")) and _text(event.get("record_id")) else None


def _event_amount(
    event: Mapping[str, Any], *, effective_at: datetime, amount_id: str | None = None
) -> dict[str, Any] | None:
    """Return the one amount fact this candidate is allowed to carry.

    ``amount_id`` names a fact other than the event's own primary amount, for a
    compound event whose lead amount is not the semantic being admitted.  A
    named fact that the event does not carry is a refusal, never a fallback to
    the primary: silently substituting a different economic quantity is exactly
    the failure the override exists to prevent.
    """
    primary_amount_id = amount_id or _text(event.get("primary_amount_id"))
    if not primary_amount_id:
        return None
    amount = next((row for row in _as_rows(event.get("amounts")) if _text(row.get("id")) == primary_amount_id), None)
    if amount is None:
        return None
    value = amount.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        return None
    if amount.get("currency") != "USD" or not _text(amount.get("semantic")) or not _text(amount.get("source_ref")):
        return None
    return {
        "amount_id": primary_amount_id,
        "value": float(value),
        "currency": "USD",
        "semantic": _text(amount.get("semantic")),
        "as_of": _iso(amount.get("as_of")) or effective_at.isoformat(),
        "source_ref": _text(amount.get("source_ref")),
    }


def _transmission_direction(event_type: str, *, amount_value: float) -> str:
    """Return the candidate's direction from the event type and, where the type
    carries both directions, the sign of the admitted amount.

    ``deobligation`` is negative by name.  A snapshot-rail obligation-balance
    move is ONE type covering both directions, so its sign is read instead; a
    move of exactly zero is reported as ``unknown`` rather than being rounded
    into a positive read.  Every other admitted type keeps the family's existing
    reading, so this changes no already-published direction.
    """
    if event_type == "deobligation":
        return "possible_negative"
    if event_type in _SIGN_DIRECTED:
        if amount_value < 0:
            return "possible_negative"
        return "possible_positive" if amount_value > 0 else "unknown"
    return "possible_positive"


def _graph_evidence_clocks(
    loaded: Mapping[str, Any],
    refs: Sequence[str],
    *,
    effective_at: datetime,
    analysis_as_of: datetime,
) -> list[datetime] | None:
    """Resolve every required graph evidence reference and its availability."""
    evidence_index = {
        _text(row.get("evidence_id")): row
        for row in _as_rows(_source_graph(loaded).get("evidence"))
        if _text(row.get("evidence_id"))
    }
    clocks: list[datetime] = []
    for ref in sorted(set(refs)):
        evidence = evidence_index.get(ref)
        if evidence is None:
            return None
        known_at = _instant(evidence.get("known_at"))
        valid_from = _instant(evidence.get("valid_from"))
        valid_to = _instant(evidence.get("valid_to"), end_of_day=True) if evidence.get("valid_to") is not None else None
        if not (
            known_at is not None
            and valid_from is not None
            and known_at <= analysis_as_of
            and valid_from <= effective_at
            and (valid_to is None or effective_at <= valid_to)
            and _text(evidence.get("source_ref"))
        ):
            return None
        clocks.append(known_at)
    return clocks


def _reviewed_ownership_path(
    impact_path: Sequence[Mapping[str, Any]],
    *,
    loaded: Mapping[str, Any],
    issuer_company_id: str,
    effective_at: datetime,
    analysis_as_of: datetime,
) -> tuple[list[dict[str, Any]], float, list[str], list[datetime]] | None:
    """Bind the event path to the strict graph view active at both clocks.

    Award events already construct their path through the recipient resolver,
    but this second admission boundary deliberately replays the graph edge
    decision.  A stale, blocked, substituted, or economically changed path
    therefore cannot become a candidate merely because its event JSON still
    says ``reviewed``.
    """
    graph = _source_graph(loaded)
    active_overrides = entity_resolution._active_overrides(  # noqa: SLF001
        graph,
        effective_at=effective_at,
        knowledge_cutoff=analysis_as_of,
    )
    normalized: list[dict[str, Any]] = []
    evidence_refs: list[str] = []
    clocks: list[datetime] = []
    economic_share = 1.0
    expected_child: str | None = None
    seen_edges: set[str] = set()
    for raw in impact_path:
        edge_id = _text(raw.get("edge_id"))
        child_entity_id = _text(raw.get("child_entity_id") or raw.get("from_id"))
        if not edge_id or not child_entity_id or edge_id in seen_edges:
            return None
        if expected_child is not None and child_entity_id != expected_child:
            return None
        active = entity_resolution._ownership_edges(  # noqa: SLF001
            graph,
            child_entity_id=child_entity_id,
            effective_at=effective_at,
            knowledge_cutoff=analysis_as_of,
            overrides=active_overrides,
        )
        matches = [
            edge
            for edge in active
            if _text(edge.get("edge_id") or edge.get("override_id")) == edge_id
        ]
        if len(matches) != 1:
            return None
        edge = matches[0]
        share, share_error = entity_resolution._edge_share(edge)  # noqa: SLF001
        if share_error or share is None:
            return None
        raw_share = raw.get("economic_share")
        if (
            not isinstance(raw_share, (int, float))
            or isinstance(raw_share, bool)
            or not math.isclose(float(raw_share), share, rel_tol=0.0, abs_tol=1e-12)
        ):
            return None
        relationship = _text(edge.get("relationship")) or "unknown"
        parent_entity_id = _text(edge.get("parent_entity_id") or edge.get("target_entity_id"))
        parent_company_id = _text(edge.get("parent_company_id") or edge.get("target_company_id"))
        raw_parent_entity = _text(raw.get("parent_entity_id") or raw.get("to_id"))
        raw_parent_company = _text(raw.get("parent_company_id"))
        raw_refs = sorted(
            ref for ref in raw.get("evidence_refs", []) if _text(ref)
        ) if isinstance(raw.get("evidence_refs"), list) else []
        edge_refs = sorted(
            ref for ref in edge.get("evidence_refs", []) if _text(ref)
        ) if isinstance(edge.get("evidence_refs"), list) else []
        if (
            _text(raw.get("relationship")) != relationship
            or raw_parent_entity != parent_entity_id
            or raw_parent_company != parent_company_id
            or not edge_refs
            or raw_refs != edge_refs
            or bool(parent_entity_id) == bool(parent_company_id)
        ):
            return None
        edge_known_at = _instant(edge.get("known_at"))
        if edge_known_at is None:
            return None
        clocks.append(edge_known_at)
        evidence_refs.extend(edge_refs)
        economic_share *= share
        normalized.append({
            "edge_id": edge_id,
            "from_entity_id": child_entity_id,
            "to_entity_id": parent_entity_id or parent_company_id,
            "relationship": relationship,
            "economic_share": share,
            "evidence_refs": edge_refs,
        })
        seen_edges.add(edge_id)
        expected_child = parent_entity_id
        if parent_company_id:
            if parent_company_id != issuer_company_id:
                return None
            expected_child = None
            if len(normalized) != len(impact_path):
                return None
    if not normalized or expected_child is not None:
        return None
    return normalized, economic_share, evidence_refs, clocks


def _active_graph_company(
    loaded: Mapping[str, Any],
    *,
    issuer_company_id: str,
    ticker: str,
    effective_at: datetime,
    analysis_as_of: datetime,
) -> Mapping[str, Any] | None:
    for company in _as_rows(_source_graph(loaded).get("companies")):
        if (
            _text(company.get("company_id")) == issuer_company_id
            and _text(company.get("ticker")) == ticker
            and (_text(company.get("verification_state")) or "").lower() in {"confirmed", "reviewed", "analyst_approved"}
            and _row_active(company, effective_at=effective_at, analysis_as_of=analysis_as_of)
        ):
            return company
    return None


def _active_conflict(
    loaded: Mapping[str, Any], *, issuer_company_id: str, effective_at: datetime, analysis_as_of: datetime
) -> bool:
    for conflict in _as_rows(_source_graph(loaded).get("conflicts")):
        company_ids = {_text(value) for value in conflict.get("candidate_company_ids", []) if _text(value)}
        if issuer_company_id in company_ids and _row_active(conflict, effective_at=effective_at, analysis_as_of=analysis_as_of):
            return True
    return False


def _reviewed_impact(
    impact: Mapping[str, Any],
    *,
    loaded: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    effective_at: datetime,
    analysis_as_of: datetime,
) -> tuple[dict[str, Any], Mapping[str, Any]] | None:
    ticker = _text(impact.get("ticker"))
    issuer_company_id = _text(impact.get("issuer_company_id"))
    company_name = _text(impact.get("company_name"))
    resolution_state = _text(impact.get("resolution_state"))
    identity_basis = _text(impact.get("identity_basis"))
    if identity_basis is not None and identity_basis not in IDENTITY_BASES:
        # An unrecognized basis is an unreadable provenance claim, not a
        # permission to publish the link without one.
        return None
    if not (
        ticker and _TICKER.fullmatch(ticker)
        and issuer_company_id and company_name
        and impact.get("relation_semantic") == "reviewed"
        and resolution_state in {"confirmed", "reviewed"}
    ):
        return None
    company = _active_graph_company(
        loaded, issuer_company_id=issuer_company_id, ticker=ticker,
        effective_at=effective_at, analysis_as_of=analysis_as_of,
    )
    if company is None or _active_conflict(
        loaded, issuer_company_id=issuer_company_id, effective_at=effective_at, analysis_as_of=analysis_as_of
    ):
        return None
    path = _reviewed_ownership_path(
        _as_rows(impact.get("ownership_path")),
        loaded=loaded,
        issuer_company_id=issuer_company_id,
        effective_at=effective_at,
        analysis_as_of=analysis_as_of,
    )
    if path is None:
        return None
    edges, economic_share, edge_evidence, path_clocks = path
    impact_evidence = [ref for ref in impact.get("evidence_refs", []) if _text(ref)] if isinstance(impact.get("evidence_refs"), list) else []
    company_evidence = [ref for ref in company.get("evidence_refs", []) if _text(ref)] if isinstance(company.get("evidence_refs"), list) else []
    if not impact_evidence or not company_evidence:
        return None
    graph_evidence_ids = {
        _text(row.get("evidence_id"))
        for row in _as_rows(_source_graph(loaded).get("evidence"))
        if _text(row.get("evidence_id"))
    }
    receipt_clocks_by_ref: dict[str, list[datetime]] = {}
    for receipt in receipts:
        receipt_known_at = _instant(receipt.get("known_at"))
        if receipt_known_at is None:
            return None
        for ref in (_text(receipt.get("ref_id")), _text(receipt.get("_source_url"))):
            if ref:
                receipt_clocks_by_ref.setdefault(ref, []).append(receipt_known_at)
    impact_evidence_clocks: list[datetime] = []
    for ref in sorted(set(impact_evidence)):
        matched = False
        if ref in graph_evidence_ids:
            graph_clocks = _graph_evidence_clocks(
                loaded,
                [ref],
                effective_at=effective_at,
                analysis_as_of=analysis_as_of,
            )
            if graph_clocks is not None:
                impact_evidence_clocks.extend(graph_clocks)
                matched = True
        if ref in receipt_clocks_by_ref:
            impact_evidence_clocks.extend(receipt_clocks_by_ref[ref])
            matched = True
        if not matched:
            return None
    graph_evidence = sorted(set(company_evidence + edge_evidence))
    evidence_clocks = _graph_evidence_clocks(
        loaded,
        graph_evidence,
        effective_at=effective_at,
        analysis_as_of=analysis_as_of,
    )
    company_known_at = _instant(company.get("known_at"))
    graph_known_at = _instant(loaded.get("graph_known_at"))
    if evidence_clocks is None or company_known_at is None or graph_known_at is None:
        return None
    resolution_known_at = max(
        company_known_at,
        graph_known_at,
        *path_clocks,
        *evidence_clocks,
        *impact_evidence_clocks,
    )
    return ({
        "ticker": ticker,
        "issuer_company_id": issuer_company_id,
        "company_name": company_name,
        "ownership_path": edges,
        "economic_share": economic_share,
        "resolution_state": resolution_state,
        "identity_basis": identity_basis,
        "evidence_refs": sorted(set(impact_evidence + company_evidence + [ref for edge in edges for ref in edge["evidence_refs"]])),
        "resolution_known_at": resolution_known_at,
    }, company)


def _candidate_from_event(
    event: Mapping[str, Any],
    *,
    loaded: Mapping[str, Any],
    analysis_as_of: datetime,
    generated_at: str,
) -> list[dict[str, Any]]:
    eligible_event = _receipt_bound_event(event, analysis_as_of=analysis_as_of)
    if eligible_event is None or loaded.get("status") != "ready":
        return []
    source_event, receipts = eligible_event
    amount = _event_amount(
        event,
        effective_at=source_event["effective_at"],
        amount_id=_FAMILY_AMOUNT_ID.get(source_event["event_type"]),
    )
    if amount is None:
        return []
    receipt_urls = {receipt["_source_url"] for receipt in receipts}
    receipt_refs = {receipt["ref_id"] for receipt in receipts}
    if amount["source_ref"] not in receipt_urls | receipt_refs:
        return []
    public_receipts = [
        {key: value for key, value in receipt.items() if not key.startswith("_")}
        for receipt in receipts
    ]
    result: list[dict[str, Any]] = []
    for raw_impact in _as_rows(event.get("listed_company_impacts")):
        reviewed = _reviewed_impact(
            raw_impact,
            loaded=loaded,
            receipts=receipts,
            effective_at=source_event["effective_at"],
            analysis_as_of=analysis_as_of,
        )
        if reviewed is None:
            continue
        impact, _company = reviewed
        family = _SUPPORTED_FAMILIES[source_event["event_type"]]
        candidate_id = _digest("grc1", {
            "candidate_family": family,
            "issuer_company_id": impact["issuer_company_id"],
            "event_id": source_event["event_id"],
        })
        graph_evidence_ids = _graph_evidence_content_ids(
            loaded, impact["evidence_refs"]
        )
        artifact_content_ids = sorted({
            source_event["source_content_id"],
            *(receipt["content_sha256"] for receipt in receipts),
            *graph_evidence_ids,
            _graph_content_id(loaded),
        })
        availability_known_at = max(
            source_event["known_at"],
            impact["resolution_known_at"],
            *(_instant(receipt["known_at"]) for receipt in receipts),
        )
        resolution_fingerprint = sha256(_canonical_json({
            "graph_id": loaded["graph_id"],
            "graph_digest": loaded["graph_digest"],
            "issuer_company_id": impact["issuer_company_id"],
            "ownership_path": impact["ownership_path"],
            "economic_share": impact["economic_share"],
            "evidence_refs": impact["evidence_refs"],
        }).encode("utf-8")).hexdigest()
        observation_id = _digest("gro1", {
            "candidate_id": candidate_id,
            "known_at": availability_known_at.isoformat(),
            "candidate_state": "awaiting_crosscheck",
            "artifact_content_ids": artifact_content_ids,
            "issuer_resolution_fingerprint": resolution_fingerprint,
        })
        direction = _transmission_direction(
            source_event["event_type"], amount_value=amount["value"]
        )
        evidence_refs = sorted(set(impact["evidence_refs"] + [receipt["ref_id"] for receipt in receipts]))
        result.append({
            "contract": CONTRACT,
            "schema_version": SCHEMA_VERSION,
            "candidate_id": candidate_id,
            "observation_id": observation_id,
            "candidate_scope": "government_revenue_research",
            "is_neuralweb_trade_candidate": False,
            "candidate_family": family,
            "candidate_state": "awaiting_crosscheck",
            "ticker": impact["ticker"],
            "issuer_company_id": impact["issuer_company_id"],
            "issuer": {
                "company_name": impact["company_name"],
                "ticker": impact["ticker"],
            },
            "issuer_resolution_ref": {
                "contract": "government_recipient_resolution.v1",
                "resolution_state": impact["resolution_state"],
                "relation_semantic": "reviewed",
                "identity_basis": impact["identity_basis"],
                "graph_id": loaded["graph_id"],
                "graph_digest": loaded["graph_digest"],
                "evidence_refs": evidence_refs,
            },
            "ownership_path_refs": [edge["edge_id"] for edge in impact["ownership_path"]],
            "event_refs": [source_event["event_id"], source_event["record_id"]],
            "source_event": {
                "event_id": source_event["event_id"],
                "record_id": source_event["record_id"],
                "event_type": source_event["event_type"],
                "source_rail": source_event["source_rail"],
                "source_content_id": source_event["source_content_id"],
                "is_late_discovery": source_event["is_late_discovery"],
                "effective_at": source_event["effective_at"].isoformat(),
                "known_at": source_event["known_at"].isoformat(),
                "amount": amount,
            },
            "source_receipt_refs": public_receipts,
            "artifact_content_ids": artifact_content_ids,
            "effective_at": source_event["effective_at"].isoformat(),
            "known_at": availability_known_at.isoformat(),
            "analysis_as_of": analysis_as_of.isoformat(),
            "generated_at": generated_at,
            "freshness": {
                "status": "ok",
                "award_events_status": "ok",
                "recipient_graph_status": "ready",
                "event_known_at": source_event["known_at"].isoformat(),
                "graph_known_at": loaded["graph_known_at"],
            },
            "coverage": {
                "scope": "receipt-bound forward-only USAspending award-event ledger; exact reviewed issuer linkage only",
                "exact_link_status": "exact_linked",
                "is_complete": False,
            },
            "materiality": {
                "observed_event_amount": amount["value"],
                "attributable_amount": amount["value"] * impact["economic_share"],
                "economic_share": impact["economic_share"],
                "issuer_attributed_denominator": None,
                "materiality_ratio": None,
                "comparison_state": "not_comparable",
                "reason_code": "exact_issuer_attributed_denominator_not_available",
            },
            "transmission_direction": direction,
            "mechanism": {
                "observed_change": source_event["change_summary"],
                "issuer_role": "reviewed_recipient",
                "possible_channels": ["backlog", "revenue", "margin", "cash", "guidance", "narrative"],
                "mechanism_steps": [
                    "Official receipt-bound award event was observed.",
                    "Reviewed ownership evidence links the recipient path to the listed issuer.",
                    "Financial transmission requires future performance, funding, and accounting recognition evidence.",
                ],
                "timing_window": "Future reported periods; timing depends on scope, funding, performance, and accounting recognition.",
                "dependencies": ["contract scope", "appropriation or obligation availability", "performance timing", "issuer accounting recognition"],
                "evidence_refs": evidence_refs,
            },
            "earnings_transmission": {
                "direction": direction,
                "statement_status": "research_context_not_trade_signal",
                "possible_earnings_channels": ["backlog", "revenue", "margin", "cash", "guidance", "narrative"],
            },
            "crosscheck_state": "not_evaluated",
            "counterevidence": [],
            "internal_watch_conditions": [
                "Confirm contract scope, funding, and performance milestones.",
                "Confirm issuer disclosure or other independently sourced financial transmission evidence.",
                "Require cross-layer confirmation before any downstream signal process considers the observation.",
            ],
            "authority": _authority(),
            "limitations": [
                "This is Government Revenue research context, not a trade or sizing signal.",
                "Materiality ratio remains unavailable until an exact issuer-attributed denominator has its own receipt and clock.",
                "Observed award amounts do not establish revenue timing, margin impact, or earnings impact.",
                *(
                    [AWARD_LEVEL_IDENTITY_LIMITATION]
                    if impact["identity_basis"] == IDENTITY_BASIS_AWARD_LEVEL
                    else []
                ),
            ],
        })
    return result


def build_candidate_observations(
    latest_payload: Mapping[str, Any],
    recipient_graph: Mapping[str, Any] | None,
    *,
    generated_at: str,
) -> list[dict[str, Any]]:
    """Return only exact, receipt-bound research candidates visible at ``as_of``.

    The function is pure: it writes nothing, does not use wall-clock time, and
    fails closed by returning an empty list for malformed or unavailable input.
    """
    if not isinstance(latest_payload, Mapping):
        return []
    generated = _iso(generated_at)
    analysis_as_of = _instant(latest_payload.get("as_of"), end_of_day=True)
    if generated is None or analysis_as_of is None:
        return []
    loaded = load_recipient_entity_graph(recipient_graph, as_of=analysis_as_of)
    if loaded.get("status") != "ready":
        return []
    award_freshness = _event_freshness(latest_payload)
    if award_freshness.get("status") != "ok":
        return []
    events = _as_rows(_workspace(latest_payload).get("events"))
    candidates = {
        candidate["candidate_id"]: candidate
        for event in events
        for candidate in _candidate_from_event(
            event, loaded=loaded, analysis_as_of=analysis_as_of, generated_at=generated,
        )
    }
    return [candidates[candidate_id] for candidate_id in sorted(candidates)]


def build_mapping_backlog(
    latest_payload: Mapping[str, Any],
    recipient_graph: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Expose discovery coverage that is not an exact reviewed issuer mapping."""
    if not isinstance(latest_payload, Mapping):
        return []
    analysis_as_of = _instant(latest_payload.get("as_of"), end_of_day=True)
    known_at = _iso(latest_payload.get("known_at"))
    if analysis_as_of is None or known_at is None:
        return []
    loaded = load_recipient_entity_graph(recipient_graph, as_of=analysis_as_of)
    graph_tickers = _reviewed_exact_graph_tickers(
        loaded, analysis_as_of=analysis_as_of
    )
    source_content_ids = sorted({
        _workspace_content_id(latest_payload),
        _graph_content_id(loaded),
        f"latest-sha256:{candidate_latest_semantic_sha256(latest_payload)}",
    })
    rows: list[dict[str, Any]] = []
    for company in _as_rows(latest_payload.get("companies")):
        ticker = _text(company.get("ticker"))
        company_name = _text(company.get("name"))
        if not ticker or _TICKER.fullmatch(ticker) is None or not company_name:
            continue
        entity_match = _as_mapping(company.get("entity_match")) or {}
        mapping_state = (
            "partial_identifier_coverage" if ticker in graph_tickers else "mapping_needed"
        )
        reason_codes = (
            ["partial_identifier_coverage"]
            if ticker in graph_tickers
            else ["exact_identifier_mapping_required"]
        )
        if not graph_tickers:
            reason_codes.append("recipient_graph_no_reviewed_issuer")
        rows.append({
            "backlog_id": _digest("grmb1", {"ticker": ticker, "company_name": company_name, "graph_digest": loaded.get("graph_digest")}),
            "ticker": ticker,
            "company_name": company_name,
            "mapping_state": mapping_state,
            "reason_codes": reason_codes,
            "source_association_method": _text(entity_match.get("method")),
            "issuer_attribution": "not_asserted",
            "known_at": known_at,
            "source_artifact_content_ids": source_content_ids,
            "limitations": [
                "Discovery-name association is retained only as mapping backlog and is not issuer attribution.",
                (
                    "At least one exact recipient path is reviewed, but the discovery scope is not complete."
                    if mapping_state == "partial_identifier_coverage"
                    else "An exact identifier and time-valid reviewed ownership path are required before a listed-company candidate can be emitted."
                ),
            ],
        })
    return sorted(rows, key=lambda row: (row["ticker"], row["backlog_id"]))


def _queue_counts(candidates: Sequence[Mapping[str, Any]], backlog: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(candidates),
        "exact_linked": len(candidates),
        "mapping_needed": len(backlog),
        "by_family": dict(sorted(Counter(row["candidate_family"] for row in candidates).items())),
        "by_state": dict(sorted(Counter(row["candidate_state"] for row in candidates).items())),
        "by_freshness": dict(sorted(Counter(row["freshness"]["status"] for row in candidates).items())),
        "by_exact_link_status": {"exact_linked": len(candidates), "mapping_needed": len(backlog)},
    }


def build_candidate_queue(
    latest_payload: Mapping[str, Any],
    recipient_graph: Mapping[str, Any] | None,
    *,
    generated_at: str,
) -> dict[str, Any]:
    """Build a deterministic display-only queue and explicit mapping backlog."""
    if not isinstance(latest_payload, Mapping):
        raise ValueError("latest_payload must be a mapping")
    generated = _iso(generated_at)
    analysis_as_of = _instant(latest_payload.get("as_of"), end_of_day=True)
    known_at = _iso(latest_payload.get("known_at"))
    if generated is None or analysis_as_of is None or known_at is None:
        raise ValueError("latest_payload.as_of, latest_payload.known_at, and generated_at must be parseable")
    loaded = load_recipient_entity_graph(recipient_graph, as_of=analysis_as_of)
    candidates = build_candidate_observations(latest_payload, recipient_graph, generated_at=generated)
    backlog = build_mapping_backlog(latest_payload, recipient_graph)
    award_freshness = _event_freshness(latest_payload)
    award_status = _text(award_freshness.get("status")) or "unavailable"
    exact_availability = "available" if candidates else ("not_observed" if award_status == "ok" else "unavailable")
    if candidates:
        reason = "Exact, receipt-bound award-change candidates are available for crosscheck."
    elif award_status == "ok":
        reason = "No reviewed, receipt-bound award-change event met exact candidate eligibility at the analysis clock."
    else:
        reason = "No receipt-bound award-change event generation is currently available; mapping backlog remains visible."
    workspace = _workspace(latest_payload)
    reviewed_tickers = sorted(
        _reviewed_exact_graph_tickers(loaded, analysis_as_of=analysis_as_of)
    )
    candidates = sorted(candidates, key=lambda row: row["candidate_id"])
    candidates.sort(key=lambda row: row["known_at"], reverse=True)
    queue = {
        "contract": QUEUE_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "as_of": analysis_as_of.isoformat(),
        "known_at": known_at,
        "generated_at": generated,
        "content_id": "grcq1-000000000000000000000000",
        "candidates": candidates,
        "mapping_backlog": backlog,
        "recently_matured": [],
        "counts": _queue_counts(candidates, backlog),
        "source_generation_ids": [_workspace_content_id(latest_payload), _text(loaded.get("graph_id")) or "recipient_graph:unavailable"],
        "source_content_ids": sorted({
            _workspace_content_id(latest_payload),
            _graph_content_id(loaded),
            f"latest-sha256:{candidate_latest_semantic_sha256(latest_payload)}",
        }),
        "freshness": {
            "status": "ok" if award_status == "ok" and loaded.get("status") == "ready" else "degraded",
            "award_events_status": award_status,
            "recipient_graph_status": _text(loaded.get("status")) or "unavailable",
            "exact_candidate_availability": exact_availability,
            "reason": reason,
        },
        "coverage": {
            "company_coverage_count": len(_as_rows(latest_payload.get("companies"))),
            "reviewed_issuer_company_count": len(reviewed_tickers),
            "reviewed_issuer_tickers": reviewed_tickers,
            "mapping_backlog_count": len(backlog),
            "award_change_events_visible": sum(1 for event in _as_rows(workspace.get("events")) if event.get("kind") == "award_change"),
            "is_complete": False,
        },
        "display_sort": {"primary": "known_at_desc", "tie_breaker": "candidate_id_asc", "is_investment_rank": False},
        "authority": _authority(),
        "limitations": [
            "Government Revenue candidates are research context only and cannot originate, rank, size, gate, or escalate a trade signal.",
            "Discovery-name coverage is visible as mapping backlog; it is never issuer attribution or a candidate source.",
            "No materiality ratio is emitted without an exact issuer-attributed denominator and its own receipt-bound clock.",
        ],
    }
    queue["content_id"] = candidate_queue_content_id(queue)
    if not is_valid_candidate_queue(queue):
        raise ValueError("candidate queue failed its contract validation")
    return queue


@lru_cache(maxsize=1)
def _validators() -> tuple[Draft202012Validator, Draft202012Validator]:
    root = Path(__file__).resolve().parents[2]
    candidate_schema = json.loads((root / "contracts/government_revenue/government_revenue_candidate.v1.schema.json").read_text(encoding="utf-8"))
    queue_schema = json.loads((root / "contracts/government_revenue/government_revenue_candidate_queue.v1.schema.json").read_text(encoding="utf-8"))
    suppression_schema = json.loads(
        (
            root
            / "contracts/government_revenue/government_revenue_candidate_historical_suppressions.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    correction_schema = json.loads(
        (
            root
            / "contracts/government_revenue/government_revenue_candidate_issuance_corrections.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    registry = Registry().with_resource(candidate_schema["$id"], Resource.from_contents(candidate_schema))
    registry = registry.with_resource(queue_schema["$id"], Resource.from_contents(queue_schema))
    registry = registry.with_resource(
        suppression_schema["$id"], Resource.from_contents(suppression_schema)
    )
    registry = registry.with_resource(
        correction_schema["$id"], Resource.from_contents(correction_schema)
    )
    checker = FormatChecker()
    return (
        Draft202012Validator(candidate_schema, registry=registry, format_checker=checker),
        Draft202012Validator(queue_schema, registry=registry, format_checker=checker),
    )


def is_valid_candidate_payload(payload: Mapping[str, Any]) -> bool:
    """Return ``True`` only for a schema-valid, fail-closed research candidate."""
    if not isinstance(payload, Mapping):
        return False
    validator, _queue_validator = _validators()
    return not list(validator.iter_errors(dict(payload)))


def is_valid_candidate_queue(payload: Mapping[str, Any]) -> bool:
    """Return ``True`` only for a schema-valid candidate queue."""
    if not isinstance(payload, Mapping):
        return False
    _candidate_validator, validator = _validators()
    if list(validator.iter_errors(dict(payload))):
        return False
    try:
        return payload.get("content_id") == candidate_queue_content_id(payload)
    except ValueError:
        return False


__all__ = [
    "HISTORICAL_SUPPRESSION_ACTIVATION_CONTRACT",
    "HISTORICAL_SUPPRESSION_APPLICATION_CONTRACT",
    "HISTORICAL_SUPPRESSION_CONFIG_PATH",
    "HISTORICAL_SUPPRESSION_CONTRACT",
    "HISTORICAL_SUPPRESSION_SCHEMA_PATH",
    "HISTORICAL_SUPPRESSION_SOURCE_PREFIX",
    "ISSUANCE_CORRECTION_ACTIVATION_CONTRACT",
    "ISSUANCE_CORRECTION_APPLICATION_CONTRACT",
    "ISSUANCE_CORRECTION_CONFIG_PATH",
    "ISSUANCE_CORRECTION_CONTRACT",
    "ISSUANCE_CORRECTION_SCHEMA_PATH",
    "ISSUANCE_CORRECTION_SOURCE_PREFIX",
    "build_candidate_observations",
    "build_candidate_queue",
    "build_mapping_backlog",
    "candidate_historical_suppression_activation",
    "candidate_historical_suppression_entry",
    "candidate_issuance_correction_activation",
    "candidate_issuance_correction_entry",
    "candidate_queue_content_id",
    "candidate_latest_semantic_sha256",
    "historical_suppression_entry_key",
    "issuance_correction_entry_key",
    "is_valid_candidate_payload",
    "is_valid_candidate_queue",
    "load_candidate_historical_suppression_manifest",
    "load_candidate_issuance_correction_manifest",
    "validate_candidate_historical_suppression_binding",
    "validate_candidate_issuance_correction_binding",
    "validate_candidate_reviewed_history_binding",
]
