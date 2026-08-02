"""Immutable, point-in-time SEC Company Facts share-count observations.

This module is intentionally a *pure normalization kernel*.  It accepts exact
already-acquired Company Facts bytes plus a caller-supplied source receipt and
returns immutable observations.  It never calls EDGAR, reads the legacy
``edgar_facts`` cache, selects a current share count, estimates fully diluted
shares, or makes a financing/risk/trading/Prophet claim.

The narrow truth plane is useful precisely because it preserves the distinction
between a directly observed common-shares-outstanding/public-float fact and the
much broader claims that may eventually consume it.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SHARE_COUNT_OBSERVATION_SCHEMA = "capital_structure.share_count_observation.v1"
COMPANYFACTS_SOURCE_RECEIPT_SCHEMA = "capital_structure.companyfacts_source_receipt.v1"
COMPANYFACTS_SOURCE_SNAPSHOT_SCHEMA = "capital_structure.companyfacts_source_snapshot.v1"
SHARE_COUNT_SNAPSHOT_FACT_OBSERVATION_SCHEMA = "capital_structure.share_count_snapshot_fact_observation.v1"
SHARE_COUNT_LEDGER_SCHEMA = "capital_structure.share_count_ledger.v1"
COMPILER_VERSION = "capital-structure-share-count-truth/1.1.0"

_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_ISSUER_RE = re.compile(r"^issuer:([0-9]{10})$")


class ShareCountTruthError(ValueError):
    """The caller supplied source bytes or history that cannot be made immutable."""


class SourceAcquisitionUnavailable(ShareCountTruthError):
    """Kept for upstream callers that choose to express no retained source input."""


class _Definition:
    def __init__(
        self,
        *,
        metric_kind: str,
        expected_unit: str,
        security_state: str,
        security_classification: str,
        security_basis: str,
    ) -> None:
        self.metric_kind = metric_kind
        self.expected_unit = expected_unit
        self.security_state = security_state
        self.security_classification = security_classification
        self.security_basis = security_basis


# These are deliberately direct, named SEC XBRL concepts.  The two share
# concepts remain separate facts: a cover-page DEI count is not silently
# substituted for the us-gaap balance-sheet concept (and vice versa).
SUPPORTED_FACTS: dict[tuple[str, str], _Definition] = {
    ("us-gaap", "CommonStockSharesOutstanding"): _Definition(
        metric_kind="common_shares_outstanding",
        expected_unit="shares",
        security_state="concept_semantic",
        security_classification="common_stock",
        security_basis="xbrl_concept_semantics",
    ),
    ("dei", "EntityCommonStockSharesOutstanding"): _Definition(
        metric_kind="common_shares_outstanding",
        expected_unit="shares",
        security_state="concept_semantic",
        security_classification="common_stock",
        security_basis="xbrl_concept_semantics",
    ),
    ("dei", "EntityPublicFloat"): _Definition(
        metric_kind="public_float",
        expected_unit="USD",
        security_state="not_security_specific",
        security_classification="not_security_specific",
        security_basis="companyfacts_fact_has_no_security_class",
    ),
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _digest_id(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(_canonical_json(value)).hexdigest()[:24]


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_timestamp(value: Any, field: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ShareCountTruthError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ShareCountTruthError(f"{field} must be ISO-8601 with timezone: {raw!r}") from exc
    if parsed.tzinfo is None:
        raise ShareCountTruthError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _valid_date(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        date.fromisoformat(raw)
    except ValueError:
        return None
    return raw


def _decimal_text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    text = format(parsed, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _issuer_cik(issuer_id: str) -> str:
    match = _ISSUER_RE.fullmatch(issuer_id)
    if not match:
        raise ShareCountTruthError("source receipt issuer_id must be issuer:<10 digit CIK>")
    return match.group(1)


@lru_cache(maxsize=1)
def _source_receipt_schema() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "capital_structure_companyfacts_source_receipt.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _source_snapshot_schema() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "capital_structure_companyfacts_source_snapshot.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _snapshot_fact_observation_schema() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "capital_structure_share_count_snapshot_fact_observation.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _receipt_material(receipt: Mapping[str, Any]) -> dict[str, str | int]:
    """Normalize one closed, externally retained Company Facts receipt.

    A receipt identifies a *source snapshot*, not a fact correction.  The
    snapshot carries its own bytes/hash, retained-object locator and clocks;
    fact-slot revisions are deliberately compared through ``fact_revision_id``
    below instead.  That prevents a harmless Company Facts root-metadata or
    retrieval-clock refresh from being mislabeled as a corrected share fact.
    """
    from jsonschema import Draft202012Validator, FormatChecker

    if not isinstance(receipt, Mapping):
        raise ShareCountTruthError("source receipt must be an object")
    validator = Draft202012Validator(_source_receipt_schema(), format_checker=FormatChecker())
    errors = list(validator.iter_errors(dict(receipt)))
    if errors:
        joined = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:5]
        )
        raise ShareCountTruthError(f"source receipt contract violation: {joined}")
    issuer_id = str(receipt["issuer_id"])
    cik = _issuer_cik(issuer_id)
    source_url = str(receipt["source_url"])
    expected_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    if source_url != expected_url:
        raise ShareCountTruthError("source receipt source_url must exactly identify the issuer Company Facts endpoint")
    payload_hash = str(receipt["source_payload_sha256"]).lower()
    if not re.fullmatch(r"[a-f0-9]{64}", payload_hash):
        raise ShareCountTruthError("source receipt source_payload_sha256 must be lowercase SHA-256")
    raw_object_locator = str(receipt["raw_object_locator"])
    if not raw_object_locator.endswith(payload_hash):
        raise ShareCountTruthError("source receipt raw_object_locator must end with source_payload_sha256")
    manifest_locator = str(receipt["manifest_locator"])
    # This wave has no collector/readback path. The locator is therefore
    # explicitly only a raw-payload-hash-bound handle; a future collector must
    # verify actual manifest resolution before relying on it operationally.
    if not manifest_locator.endswith(payload_hash):
        raise ShareCountTruthError("source receipt manifest_locator must end with source_payload_sha256")
    retrieved = _parse_timestamp(receipt["source_retrieved_at"], "source_retrieved_at")
    available = _parse_timestamp(receipt["system_available_at"], "system_available_at")
    if _timestamp(available) < _timestamp(retrieved):
        raise ShareCountTruthError("system_available_at cannot precede source_retrieved_at")
    return {
        "schema": COMPANYFACTS_SOURCE_RECEIPT_SCHEMA,
        "version": 1,
        "source_system": "sec_companyfacts",
        "acquisition_state": "provided_snapshot",
        "issuer_id": issuer_id,
        "source_url": source_url,
        "source_payload_sha256": payload_hash,
        "raw_object_locator": raw_object_locator,
        "manifest_locator": manifest_locator,
        "source_retrieved_at": retrieved,
        "system_available_at": available,
    }


def source_receipt_id_for(receipt: Mapping[str, Any]) -> str:
    """Return the stable receipt identity after strict receipt normalization."""
    return _digest_id("companyfacts-receipt:cs:", _receipt_material(receipt))


def logical_observation_id_for(record: Mapping[str, Any]) -> str:
    """Stable slot identity, deliberately independent of value and source hash."""
    metric = record.get("metric") or {}
    fact = record.get("fact") or {}
    period = record.get("period") or {}
    filing = record.get("filing") or {}
    material = {
        "issuer_id": record.get("issuer_id"),
        "metric_kind": metric.get("kind"),
        "namespace": fact.get("namespace"),
        "name": fact.get("name"),
        "unit": fact.get("unit"),
        "period_end": period.get("period_end"),
        "accession": filing.get("accession"),
        "form": filing.get("form"),
        "filed": filing.get("filed"),
    }
    return _digest_id("share-count-slot:cs:", material)


def fact_revision_id_for(record: Mapping[str, Any]) -> str:
    """Digest only fact-slot semantics, never incidental snapshot provenance.

    Company Facts is a whole-issuer snapshot.  Its root metadata, unrelated
    concepts, response hash and receipt clocks can all change while an in-scope
    XBRL fact has not.  They remain linked through immutable source snapshots,
    but must not advance this fact's correction chain.
    """
    evidence = record.get("evidence") or {}
    entries = evidence.get("fact_entries") or []
    entry_hashes = sorted(
        str(entry.get("entry_sha256") or "")
        for entry in entries if isinstance(entry, Mapping)
    )
    material = {
        "logical_observation_id": record.get("logical_observation_id"),
        "metric": record.get("metric"),
        "fact": record.get("fact"),
        "security_class": record.get("security_class"),
        "period": record.get("period"),
        "filing": record.get("filing"),
        # State/eligibility can change solely because a later retained receipt
        # establishes a later system clock.  It is snapshot-local, never a
        # fact correction by itself.
        "entry_sha256s": entry_hashes,
    }
    return _digest_id("share-count-revision:cs:", material)


def observation_id_for(record: Mapping[str, Any]) -> str:
    """Digest the full immutable version, excluding its self-referential ID."""
    material = deepcopy(dict(record))
    material.pop("observation_id", None)
    return _digest_id("share-count:cs:", material)


def snapshot_fact_observation_id_for(record: Mapping[str, Any]) -> str:
    """Digest a receipt-bound snapshot-local fact observation body."""
    material = deepcopy(dict(record))
    material.pop("snapshot_fact_observation_id", None)
    return _digest_id("share-count-snapshot-fact:cs:", material)


def source_snapshot_id_for(snapshot: Mapping[str, Any]) -> str:
    """Digest the full normalized snapshot body, excluding its self ID only."""
    material = deepcopy(dict(snapshot))
    material.pop("source_snapshot_id", None)
    return _digest_id("companyfacts-snapshot:cs:", material)


@lru_cache(maxsize=1)
def _observation_schema() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "capital_structure_share_count_observation.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def validate_share_count_observation(record: Mapping[str, Any]) -> None:
    """Fail closed if a generated or supplied row escapes the closed contract."""
    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(_observation_schema(), format_checker=FormatChecker())
    errors = list(validator.iter_errors(record))
    if errors:
        joined = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:5]
        )
        raise ShareCountTruthError(f"share-count observation contract violation: {joined}")


def _schema_errors(schema: Mapping[str, Any], record: Mapping[str, Any]) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(dict(record))
    ]


def _canonical_entry_hashes(record: Mapping[str, Any]) -> list[str]:
    evidence = record.get("evidence") or {}
    entries = evidence.get("fact_entries") or []
    hashes = sorted({
        str(entry.get("entry_sha256") or "")
        for entry in entries if isinstance(entry, Mapping)
    })
    if not hashes or any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in hashes):
        raise ShareCountTruthError("canonical observation lacks nonempty valid fact-entry hashes")
    return hashes


def validate_snapshot_fact_observation(record: Mapping[str, Any]) -> None:
    """Validate one receipt-bound, snapshot-local fact observation."""
    if not isinstance(record, Mapping):
        raise ShareCountTruthError("snapshot-fact observation must be an object")
    errors = _schema_errors(_snapshot_fact_observation_schema(), record)
    if errors:
        raise ShareCountTruthError(f"snapshot-fact observation contract violation: {'; '.join(errors[:5])}")
    if record.get("snapshot_fact_observation_id") != snapshot_fact_observation_id_for(record):
        raise ShareCountTruthError("snapshot-fact observation ID digest mismatch")
    hashes = list(record.get("fact_entry_sha256s") or [])
    if hashes != sorted(hashes) or len(hashes) != len(set(hashes)):
        raise ShareCountTruthError("snapshot-fact observation hashes must be sorted and unique")
    point_in_time = record.get("point_in_time") or {}
    if point_in_time.get("available_at") != point_in_time.get("system_available_at"):
        raise ShareCountTruthError("snapshot-fact observation available_at must equal system_available_at")
    if _timestamp(str(point_in_time["system_available_at"])) < _timestamp(
        str(point_in_time["source_retrieved_at"]),
    ):
        raise ShareCountTruthError("snapshot-fact observation system_available_at cannot precede source_retrieved_at")


def _validate_snapshot_fact_semantics(
    snapshot_fact: Mapping[str, Any], canonical: Mapping[str, Any], receipt: Mapping[str, str | int],
) -> None:
    """Resolve every snapshot-fact reference against the canonical fact ledger."""
    if snapshot_fact.get("source_receipt_id") != _digest_id("companyfacts-receipt:cs:", receipt):
        raise ShareCountTruthError("snapshot-fact observation receipt does not match source snapshot")
    if snapshot_fact.get("logical_observation_id") != canonical.get("logical_observation_id"):
        raise ShareCountTruthError("snapshot-fact observation logical ID does not resolve canonical observation")
    if snapshot_fact.get("fact_revision_id") != canonical.get("fact_revision_id"):
        raise ShareCountTruthError("snapshot-fact observation revision ID does not resolve canonical observation")
    if snapshot_fact.get("observation_id") != canonical.get("observation_id"):
        raise ShareCountTruthError("snapshot-fact observation ID does not resolve canonical observation")
    if list(snapshot_fact.get("fact_entry_sha256s") or []) != _canonical_entry_hashes(canonical):
        raise ShareCountTruthError("snapshot-fact observation hashes do not match canonical fact evidence")

    point_in_time = snapshot_fact.get("point_in_time") or {}
    for field in ("source_retrieved_at", "system_available_at"):
        if point_in_time.get(field) != receipt.get(field):
            raise ShareCountTruthError(f"snapshot-fact observation {field} does not match source receipt")

    state = snapshot_fact.get("state") or {}
    reported = snapshot_fact.get("reported") or {}
    normalized = snapshot_fact.get("normalized") or {}
    disposition = state.get("disposition")
    if normalized.get("state") != disposition:
        raise ShareCountTruthError("snapshot-fact normalized state does not match snapshot-local disposition")
    if disposition == "observed":
        definition = SUPPORTED_FACTS.get((
            str((canonical.get("fact") or {}).get("namespace") or ""),
            str((canonical.get("fact") or {}).get("name") or ""),
        ))
        if definition is None:
            raise ShareCountTruthError("snapshot-fact canonical observation names an unsupported fact")
        if reported.get("unit") != (canonical.get("fact") or {}).get("unit") or reported.get("scale") != "1":
            raise ShareCountTruthError("snapshot-fact observed reported unit/scale does not match canonical fact")
        if reported.get("value") is None or normalized.get("value") != reported.get("value"):
            raise ShareCountTruthError("snapshot-fact observed values are detached from direct fact value")
        if normalized.get("unit") != definition.expected_unit or normalized.get("scale") != "1":
            raise ShareCountTruthError("snapshot-fact observed normalized unit/scale is invalid")
    elif disposition == "deferred":
        if any(normalized.get(field) is not None for field in ("value", "unit", "scale")):
            raise ShareCountTruthError("deferred snapshot-fact observation carries normalized value")
    elif disposition == "ambiguous":
        if reported.get("value") is not None or any(normalized.get(field) is not None for field in ("value", "unit", "scale")):
            raise ShareCountTruthError("ambiguous snapshot-fact observation carries a selected value")


def validate_source_snapshot(
    snapshot: Mapping[str, Any], observations: Sequence[Mapping[str, Any]],
) -> None:
    """Validate source snapshot body and every cross-ledger fact linkage."""
    if not isinstance(snapshot, Mapping):
        raise ShareCountTruthError("source snapshot must be an object")
    errors = _schema_errors(_source_snapshot_schema(), snapshot)
    if errors:
        raise ShareCountTruthError(f"source snapshot contract violation: {'; '.join(errors[:5])}")
    receipt = _receipt_material(snapshot.get("source_receipt") or {})
    receipt_id = _digest_id("companyfacts-receipt:cs:", receipt)
    if snapshot.get("source_receipt_id") != receipt_id:
        raise ShareCountTruthError("source snapshot receipt ID is detached from its receipt")
    if snapshot.get("source_snapshot_id") != source_snapshot_id_for(snapshot):
        raise ShareCountTruthError("source snapshot ID digest mismatch")

    canonical_by_id = {str(row.get("observation_id") or ""): row for row in observations}
    snapshot_facts = list(snapshot.get("snapshot_fact_observations") or [])
    links = list(snapshot.get("fact_links") or [])
    by_snapshot_fact_id: dict[str, Mapping[str, Any]] = {}
    logical_snapshot_facts: set[str] = set()
    for fact in snapshot_facts:
        validate_snapshot_fact_observation(fact)
        fact_id = str(fact.get("snapshot_fact_observation_id") or "")
        logical_id = str(fact.get("logical_observation_id") or "")
        if fact_id in by_snapshot_fact_id:
            raise ShareCountTruthError("source snapshot repeats snapshot-fact observation ID")
        if logical_id in logical_snapshot_facts:
            raise ShareCountTruthError("source snapshot has multiple snapshot-fact observations for one logical slot")
        canonical = canonical_by_id.get(str(fact.get("observation_id") or ""))
        if canonical is None:
            raise ShareCountTruthError("snapshot-fact observation references missing canonical observation")
        _validate_snapshot_fact_semantics(fact, canonical, receipt)
        by_snapshot_fact_id[fact_id] = fact
        logical_snapshot_facts.add(logical_id)

    linked_ids: set[str] = set()
    linked_logical_ids: set[str] = set()
    for link in links:
        logical_id = str(link.get("logical_observation_id") or "")
        fact_id = str(link.get("snapshot_fact_observation_id") or "")
        if logical_id in linked_logical_ids:
            raise ShareCountTruthError("source snapshot has multiple links for one logical slot")
        if fact_id in linked_ids:
            raise ShareCountTruthError("source snapshot has multiple links to one snapshot-fact observation")
        fact = by_snapshot_fact_id.get(fact_id)
        if fact is None or fact.get("logical_observation_id") != logical_id:
            raise ShareCountTruthError("source snapshot link does not resolve its snapshot-fact observation")
        linked_logical_ids.add(logical_id)
        linked_ids.add(fact_id)
    if linked_ids != set(by_snapshot_fact_id) or linked_logical_ids != logical_snapshot_facts:
        raise ShareCountTruthError("source snapshot links must cover exactly one snapshot-fact observation per logical slot")


def validate_share_count_ledger(ledger: Mapping[str, Any]) -> None:
    """Validate the self-contained immutable fact and append-only snapshot ledgers."""
    if not isinstance(ledger, Mapping):
        raise ShareCountTruthError("share-count ledger must be an object")
    required = {
        "schema", "status", "compiler_version", "source_acquisition", "observations",
        "source_snapshots", "counts",
    }
    if set(ledger) != required:
        raise ShareCountTruthError("share-count ledger has unexpected or missing top-level fields")
    if ledger.get("schema") != SHARE_COUNT_LEDGER_SCHEMA or ledger.get("status") != "ok":
        raise ShareCountTruthError("share-count ledger has wrong schema or status")
    observations = ledger.get("observations")
    snapshots = ledger.get("source_snapshots")
    if not isinstance(observations, list) or not isinstance(snapshots, list):
        raise ShareCountTruthError("share-count ledger observations and source_snapshots must be arrays")
    validate_share_count_history(observations)
    snapshot_ids: set[str] = set()
    for snapshot in snapshots:
        snapshot_id = str((snapshot or {}).get("source_snapshot_id") or "")
        if snapshot_id in snapshot_ids:
            raise ShareCountTruthError("duplicate source_snapshot_id in ledger")
        snapshot_ids.add(snapshot_id)
        validate_source_snapshot(snapshot, observations)
    counts = ledger.get("counts") or {}
    expected_count_fields = {"observations_total", "source_snapshots_total", "current_snapshot"}
    if set(counts) != expected_count_fields:
        raise ShareCountTruthError("share-count ledger counts must describe totals and the current snapshot only")
    if counts.get("observations_total") != len(observations):
        raise ShareCountTruthError("share-count ledger observations_total does not match observations")
    if counts.get("source_snapshots_total") != len(snapshots):
        raise ShareCountTruthError("share-count ledger source_snapshots_total does not match source_snapshots")
    source_acquisition = ledger.get("source_acquisition") or {}
    if set(source_acquisition) != {
        "state", "collector_state", "source_receipt_id", "source_receipt_schema", "source_snapshot_id",
    }:
        raise ShareCountTruthError("share-count ledger source_acquisition has unexpected or missing fields")
    if (
        source_acquisition.get("state") != "provided_snapshot"
        or source_acquisition.get("collector_state") != "not_implemented_in_share_count_truth_wave"
        or source_acquisition.get("source_receipt_schema") != COMPANYFACTS_SOURCE_RECEIPT_SCHEMA
    ):
        raise ShareCountTruthError("share-count ledger source_acquisition is not a provided Company Facts snapshot")
    current_snapshot_id = str(source_acquisition.get("source_snapshot_id") or "")
    current_snapshot = next(
        (snapshot for snapshot in snapshots if snapshot.get("source_snapshot_id") == current_snapshot_id),
        None,
    )
    if current_snapshot is None:
        raise ShareCountTruthError("share-count ledger current source snapshot does not resolve")
    if source_acquisition.get("source_receipt_id") != current_snapshot.get("source_receipt_id"):
        raise ShareCountTruthError("share-count ledger current receipt does not resolve current source snapshot")
    snapshot_facts = current_snapshot.get("snapshot_fact_observations") or []
    expected_current_counts = {
        "snapshot_fact_observations": len(snapshot_facts),
        **{
            disposition: sum(
                fact.get("state", {}).get("disposition") == disposition
                for fact in snapshot_facts
            )
            for disposition in ("observed", "deferred", "ambiguous")
        },
    }
    if counts.get("current_snapshot") != expected_current_counts:
        raise ShareCountTruthError("share-count ledger disposition counts do not describe current source snapshot")


def _source_entry(
    *, pointer: str, entry: Any, unit: str
) -> dict[str, Any]:
    raw = dict(entry) if isinstance(entry, Mapping) else entry
    mapping = entry if isinstance(entry, Mapping) else {}
    return {
        "json_pointer": pointer,
        "entry_sha256": hashlib.sha256(_canonical_json(raw)).hexdigest(),
        "value": _decimal_text(mapping.get("val")),
        "unit": unit,
        "period_end": _valid_date(mapping.get("end")),
        "fiscal_year": (
            mapping.get("fy")
            if isinstance(mapping.get("fy"), int) and 1900 <= mapping["fy"] <= 3000
            else None
        ),
        "fiscal_period": _string_or_none(mapping.get("fp"), max_length=32),
        "frame": _string_or_none(mapping.get("frame"), max_length=64),
        "filed": _valid_date(mapping.get("filed")),
        "accession": _accession_or_none(mapping.get("accn")),
        "form": _string_or_none(mapping.get("form"), max_length=32),
    }


def _accession_or_none(value: Any) -> str | None:
    raw = str(value or "").strip()
    return raw if _ACCESSION_RE.fullmatch(raw) else None


def _string_or_none(value: Any, *, max_length: int) -> str | None:
    raw = str(value or "").strip()
    return raw if raw and len(raw) <= max_length else None


def _candidate_issue(
    entry: Any, unit: str, definition: _Definition, *, system_available_at: str
) -> str | None:
    if not isinstance(entry, Mapping):
        return "malformed_fact_entry"
    raw_value = _decimal_text(entry.get("val"))
    if raw_value is None:
        return "missing_value"
    if Decimal(raw_value) < 0:
        return "negative_value"
    if unit != definition.expected_unit:
        return "unexpected_unit"
    if _valid_date(entry.get("end")) is None:
        return "missing_period_end"
    filed = _valid_date(entry.get("filed"))
    if (
        _accession_or_none(entry.get("accn")) is None
        or _string_or_none(entry.get("form"), max_length=32) is None
        or filed is None
    ):
        return "missing_filing_provenance"
    # Company Facts carries a filed *date*, not an accepted timestamp.  We do
    # not pretend otherwise, but an internal availability date before that
    # public filing date is still an impossible historical observation.
    if _timestamp(system_available_at).date() < date.fromisoformat(filed):
        return "system_availability_precedes_filed_date"
    return None


def _slot_key(
    *, issuer_id: str, namespace: str, name: str, unit: str, entry: Any,
    definition: _Definition,
) -> tuple[str | None, ...]:
    mapping = entry if isinstance(entry, Mapping) else {}
    return (
        issuer_id,
        definition.metric_kind,
        namespace,
        name,
        unit,
        _valid_date(mapping.get("end")),
        _accession_or_none(mapping.get("accn")),
        _string_or_none(mapping.get("form"), max_length=32),
        _valid_date(mapping.get("filed")),
    )


def _fact_candidates(
    payload: Mapping[str, Any], *, issuer_id: str, system_available_at: str
) -> list[dict[str, Any]]:
    facts = payload.get("facts")
    if not isinstance(facts, Mapping):
        raise ShareCountTruthError("Company Facts payload must contain facts object")
    candidates: list[dict[str, Any]] = []
    for (namespace, name), definition in SUPPORTED_FACTS.items():
        taxonomy = facts.get(namespace)
        if not isinstance(taxonomy, Mapping):
            continue
        concept = taxonomy.get(name)
        if not isinstance(concept, Mapping):
            continue
        units = concept.get("units")
        if not isinstance(units, Mapping):
            continue
        for raw_unit, raw_entries in sorted(units.items(), key=lambda item: str(item[0])):
            unit = str(raw_unit)
            entries: Sequence[Any] = raw_entries if isinstance(raw_entries, list) else [raw_entries]
            for index, entry in enumerate(entries):
                pointer = f"/facts/{namespace}/{name}/units/{unit}/{index}"
                candidates.append({
                    "definition": definition,
                    "namespace": namespace,
                    "name": name,
                    "unit": unit,
                    "entry": entry,
                    "entry_evidence": _source_entry(pointer=pointer, entry=entry, unit=unit),
                    "issue": _candidate_issue(
                        entry, unit, definition, system_available_at=system_available_at,
                    ),
                    "slot_key": _slot_key(
                        issuer_id=issuer_id, namespace=namespace, name=name, unit=unit,
                        entry=entry, definition=definition,
                    ),
                })
    return candidates


def _fact_period(entry: Any) -> dict[str, Any]:
    mapping = entry if isinstance(entry, Mapping) else {}
    fy = mapping.get("fy")
    fiscal_year = fy if isinstance(fy, int) and 1900 <= fy <= 3000 else None
    return {
        "period_end": _valid_date(mapping.get("end")),
        "fiscal_year": fiscal_year,
        "fiscal_period": _string_or_none(mapping.get("fp"), max_length=32),
        "frame": _string_or_none(mapping.get("frame"), max_length=64),
    }


def _fact_filing(entry: Any) -> dict[str, Any]:
    mapping = entry if isinstance(entry, Mapping) else {}
    return {
        "accession": _accession_or_none(mapping.get("accn")),
        "form": _string_or_none(mapping.get("form"), max_length=32),
        "filed": _valid_date(mapping.get("filed")),
        # Company Facts does not expose EDGAR accepted timestamp.  The null is
        # intentional: this source must not manufacture a filing-time clock.
        "accepted_at": None,
    }


def _state_for_group(group: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    values = {
        str(item["entry_evidence"]["value"])
        for item in group if item["entry_evidence"]["value"] is not None
    }
    if len(values) > 1:
        return "ambiguous", "multiple_distinct_values_for_fact_slot"
    contexts = {
        (
            item["entry_evidence"]["fiscal_year"], item["entry_evidence"]["fiscal_period"],
            item["entry_evidence"]["frame"],
        )
        for item in group
    }
    if len(contexts) > 1:
        return "ambiguous", "multiple_distinct_contexts_for_fact_slot"
    issues = sorted({str(item["issue"]) for item in group if item.get("issue")})
    if issues:
        return "deferred", issues[0]
    return "observed", "direct_sec_companyfacts_fact"


def _record_from_group(
    group: Sequence[Mapping[str, Any]], *, receipt: Mapping[str, str]
) -> dict[str, Any]:
    ordered = sorted(group, key=lambda item: item["entry_evidence"]["json_pointer"])
    first = ordered[0]
    definition: _Definition = first["definition"]
    disposition, reason = _state_for_group(ordered)
    entry = first["entry"]
    raw_value = first["entry_evidence"]["value"]
    unit = str(first["unit"])
    if disposition == "observed":
        reported = {"value": raw_value, "unit": unit, "scale": "1"}
        normalized = {"value": raw_value, "unit": definition.expected_unit, "scale": "1", "state": "observed"}
    elif disposition == "ambiguous":
        reported = {"value": None, "unit": unit, "scale": "1"}
        normalized = {"value": None, "unit": None, "scale": None, "state": "ambiguous"}
    else:
        reported = {"value": raw_value, "unit": unit, "scale": "1"}
        normalized = {"value": None, "unit": None, "scale": None, "state": "deferred"}
    record: dict[str, Any] = {
        "schema": SHARE_COUNT_OBSERVATION_SCHEMA,
        "observation_id": "",
        "logical_observation_id": "",
        "fact_revision_id": "",
        "issuer_id": receipt["issuer_id"],
        "metric": {"kind": definition.metric_kind, "scope": "direct_sec_companyfacts_fact"},
        "fact": {
            "namespace": first["namespace"], "name": first["name"], "unit": unit,
            "scale": "1", "source_value_encoding": "companyfacts_actual_units",
        },
        "security_class": {
            "state": definition.security_state,
            "classification": definition.security_classification,
            "raw_label": None,
            "basis": definition.security_basis,
        },
        "period": _fact_period(entry),
        "filing": _fact_filing(entry),
        "state": {"disposition": disposition, "reason": reason},
        "reported": reported,
        "normalized": normalized,
        "evidence": {
            "source_receipt_id": _digest_id("companyfacts-receipt:cs:", receipt),
            "source_receipt_schema": receipt["schema"],
            "source_system": "sec_companyfacts",
            "source_url": receipt["source_url"],
            "source_payload_sha256": receipt["source_payload_sha256"],
            "raw_object_locator": receipt["raw_object_locator"],
            "manifest_locator": receipt["manifest_locator"],
            "fact_entries": [item["entry_evidence"] for item in ordered],
        },
        "source_acquisition": {
            "state": "provided_snapshot",
            "collector_state": "not_implemented_in_share_count_truth_wave",
        },
        "point_in_time": {
            "system_available_at": receipt["system_available_at"],
            "source_retrieved_at": receipt["source_retrieved_at"],
            "available_at": receipt["system_available_at"],
        },
        "relationships": {"supersedes": [], "contradiction_ids": []},
        "version": {"immutable_record": True, "correction_version": 1, "correction_of": None},
        "authority": {
            "is_context_only": True, "rank_authority": False, "sizing_authority": False,
            "entry_authority": False, "trade_authority": False, "prophet_authority": False,
        },
    }
    record["logical_observation_id"] = logical_observation_id_for(record)
    record["fact_revision_id"] = fact_revision_id_for(record)
    record["observation_id"] = observation_id_for(record)
    return record


def validate_share_count_history(observations: Sequence[Mapping[str, Any]]) -> None:
    """Validate immutable IDs and an unbroken, non-branching correction chain."""
    by_slot: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    ids: set[str] = set()
    for index, raw in enumerate(observations):
        record = dict(raw)
        observation_id = str(record.get("observation_id") or "")
        if observation_id in ids:
            raise ShareCountTruthError(f"duplicate observation_id in history: {observation_id}")
        ids.add(observation_id)
        if record.get("schema") != SHARE_COUNT_OBSERVATION_SCHEMA:
            raise ShareCountTruthError(f"history row {index} has wrong schema")
        validate_share_count_observation(record)
        if record.get("logical_observation_id") != logical_observation_id_for(record):
            raise ShareCountTruthError(f"history row {index} logical_observation_id digest mismatch")
        if record.get("fact_revision_id") != fact_revision_id_for(record):
            raise ShareCountTruthError(f"history row {index} fact_revision_id digest mismatch")
        if observation_id != observation_id_for(record):
            raise ShareCountTruthError(f"history row {index} observation_id digest mismatch")
        by_slot[str(record["logical_observation_id"])].append(record)
    for logical_id, versions in by_slot.items():
        versions.sort(key=lambda row: int((row.get("version") or {}).get("correction_version") or 0))
        for expected, row in enumerate(versions, start=1):
            version = row.get("version") or {}
            relationships = row.get("relationships") or {}
            actual = int(version.get("correction_version") or 0)
            if actual != expected:
                raise ShareCountTruthError(f"{logical_id} correction versions must be contiguous from 1")
            if expected == 1:
                if version.get("correction_of") is not None or relationships.get("supersedes"):
                    raise ShareCountTruthError(f"{logical_id} v1 cannot name a predecessor")
            else:
                predecessor = versions[expected - 2]["observation_id"]
                if version.get("correction_of") != predecessor or relationships.get("supersedes") != [predecessor]:
                    raise ShareCountTruthError(f"{logical_id} v{expected} must supersede exactly v{expected - 1}")
                if row.get("fact_revision_id") == versions[expected - 2].get("fact_revision_id"):
                    raise ShareCountTruthError(f"{logical_id} cannot correct unchanged fact revision")


def _apply_correction_history(
    candidate: Mapping[str, Any], existing_observations: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], bool]:
    """Return latest existing version if byte-equivalent, else append one correction."""
    logical_id = str(candidate["logical_observation_id"])
    prior = [dict(row) for row in existing_observations if row.get("logical_observation_id") == logical_id]
    if not prior:
        return dict(candidate), True
    prior.sort(key=lambda row: int((row.get("version") or {}).get("correction_version") or 0))
    current = prior[-1]
    if candidate["fact_revision_id"] == current.get("fact_revision_id"):
        return current, False
    corrected = deepcopy(dict(candidate))
    next_version = int((current.get("version") or {}).get("correction_version") or 0) + 1
    corrected["version"] = {
        "immutable_record": True,
        "correction_version": next_version,
        "correction_of": current["observation_id"],
    }
    corrected["relationships"] = {"supersedes": [current["observation_id"]], "contradiction_ids": []}
    corrected["observation_id"] = observation_id_for(corrected)
    return corrected, True


def _snapshot_fact_observation(
    candidate: Mapping[str, Any], applied: Mapping[str, Any], *, receipt: Mapping[str, str | int],
) -> dict[str, Any]:
    """Materialize one receipt-local state/PIT observation for a fact revision.

    This row is intentionally distinct from the canonical fact observation.
    For example, an early retained receipt can defer a fact because the system
    clock predates its filing date, while a later receipt of unchanged bytes can
    truthfully observe it.  That is a new snapshot-local observation, never a
    fabricated fact correction.
    """
    record: dict[str, Any] = {
        "schema": SHARE_COUNT_SNAPSHOT_FACT_OBSERVATION_SCHEMA,
        "snapshot_fact_observation_id": "",
        "source_receipt_id": _digest_id("companyfacts-receipt:cs:", receipt),
        "logical_observation_id": str(candidate["logical_observation_id"]),
        "fact_revision_id": str(candidate["fact_revision_id"]),
        "observation_id": str(applied["observation_id"]),
        "state": deepcopy(dict(candidate["state"])),
        "reported": deepcopy(dict(candidate["reported"])),
        "normalized": deepcopy(dict(candidate["normalized"])),
        "point_in_time": {
            "source_retrieved_at": receipt["source_retrieved_at"],
            "system_available_at": receipt["system_available_at"],
            "available_at": receipt["system_available_at"],
        },
        "fact_entry_sha256s": _canonical_entry_hashes(candidate),
        "authority": {
            "is_context_only": True, "rank_authority": False, "sizing_authority": False,
            "entry_authority": False, "trade_authority": False, "prophet_authority": False,
        },
    }
    record["snapshot_fact_observation_id"] = snapshot_fact_observation_id_for(record)
    validate_snapshot_fact_observation(record)
    return record


def _source_snapshot(
    receipt: Mapping[str, str | int], snapshot_facts: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create the canonical receipt-bound snapshot body and its fact links."""
    ordered_facts = sorted(
        [deepcopy(dict(fact)) for fact in snapshot_facts],
        key=lambda fact: str(fact["logical_observation_id"]),
    )
    snapshot: dict[str, Any] = {
        "schema": COMPANYFACTS_SOURCE_SNAPSHOT_SCHEMA,
        "source_snapshot_id": "",
        "source_receipt_id": _digest_id("companyfacts-receipt:cs:", receipt),
        "source_receipt": dict(receipt),
        "snapshot_fact_observations": ordered_facts,
        "fact_links": [
            {
                "logical_observation_id": fact["logical_observation_id"],
                "snapshot_fact_observation_id": fact["snapshot_fact_observation_id"],
            }
            for fact in ordered_facts
        ],
    }
    snapshot["source_snapshot_id"] = source_snapshot_id_for(snapshot)
    validate_source_snapshot(snapshot, observations)
    return snapshot


def source_acquisition_unavailable_result(*, reason: str = "no_retained_companyfacts_snapshot_supplied") -> dict[str, Any]:
    """Explicitly represent the deliberate absence of a collector in this wave."""
    return {
        "schema": SHARE_COUNT_LEDGER_SCHEMA,
        "status": "unavailable",
        "compiler_version": COMPILER_VERSION,
        "source_acquisition": {
            "state": "unavailable",
            "collector_state": "not_implemented_in_share_count_truth_wave",
            "reason": reason,
        },
        "observations": [],
        "source_snapshots": [],
        "counts": {
            "observations_total": 0,
            "source_snapshots_total": 0,
            "current_snapshot": {
                "snapshot_fact_observations": 0,
                "observed": 0,
                "deferred": 0,
                "ambiguous": 0,
            },
        },
    }


def compile_share_count_observations(
    source_bytes: bytes,
    source_receipt: Mapping[str, Any],
    *,
    existing_ledger: Mapping[str, Any] | None = None,
    existing_observations: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Purely normalize one exact Company Facts source snapshot.

    ``source_bytes`` must be the retained bytes whose SHA-256 is named by
    ``source_receipt``.  There is intentionally no HTTP fallback and no read of
    ``collectors.edgar_facts``: that cache is a fetch-time materialization rather
    than an immutable historical source ledger.
    """
    if not isinstance(source_bytes, bytes):
        raise ShareCountTruthError("source_bytes must be bytes")
    receipt = _receipt_material(source_receipt)
    actual_hash = _sha256(source_bytes)
    if actual_hash != receipt["source_payload_sha256"]:
        raise ShareCountTruthError("source receipt payload hash does not bind supplied source_bytes")
    try:
        payload = json.loads(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShareCountTruthError("source_bytes must be UTF-8 JSON Company Facts payload") from exc
    if not isinstance(payload, Mapping):
        raise ShareCountTruthError("Company Facts source root must be an object")
    payload_cik = str(payload.get("cik") or "").zfill(10)
    if payload_cik != _issuer_cik(receipt["issuer_id"]):
        raise ShareCountTruthError("Company Facts payload CIK does not match receipt issuer_id")
    if existing_ledger is not None:
        if existing_observations:
            raise ShareCountTruthError("supply existing_ledger or existing_observations, not both")
        validate_share_count_ledger(existing_ledger)
        prior_observations = [deepcopy(dict(row)) for row in existing_ledger["observations"]]
        prior_snapshots = [deepcopy(dict(row)) for row in existing_ledger["source_snapshots"]]
    else:
        prior_observations = [deepcopy(dict(row)) for row in existing_observations]
        prior_snapshots: list[dict[str, Any]] = []
        validate_share_count_history(prior_observations)

    grouped: dict[tuple[str | None, ...], list[dict[str, Any]]] = defaultdict(list)
    for candidate in _fact_candidates(
        payload, issuer_id=receipt["issuer_id"], system_available_at=receipt["system_available_at"],
    ):
        grouped[candidate["slot_key"]].append(candidate)
    new_rows: list[dict[str, Any]] = []
    snapshot_facts: list[dict[str, Any]] = []
    for _slot, group in sorted(grouped.items(), key=lambda item: repr(item[0])):
        row = _record_from_group(group, receipt=receipt)
        applied, is_new = _apply_correction_history(row, prior_observations)
        if is_new:
            new_rows.append(applied)
        snapshot_facts.append(_snapshot_fact_observation(row, applied, receipt=receipt))

    output = [*prior_observations, *new_rows]
    validate_share_count_history(output)
    output.sort(key=lambda row: (
        str(row.get("issuer_id") or ""), str(row.get("logical_observation_id") or ""),
        int((row.get("version") or {}).get("correction_version") or 0),
    ))
    current_snapshot = _source_snapshot(receipt, snapshot_facts, output)
    existing_snapshot_ids = {
        str(snapshot.get("source_snapshot_id") or "") for snapshot in prior_snapshots
    }
    new_source_snapshots = [] if current_snapshot["source_snapshot_id"] in existing_snapshot_ids else [current_snapshot]
    source_snapshots = [*prior_snapshots, *new_source_snapshots]
    current_dispositions = {
        disposition: sum(
            fact["state"]["disposition"] == disposition
            for fact in current_snapshot["snapshot_fact_observations"]
        )
        for disposition in ("observed", "deferred", "ambiguous")
    }
    result = {
        "schema": SHARE_COUNT_LEDGER_SCHEMA,
        "status": "ok",
        "compiler_version": COMPILER_VERSION,
        "source_acquisition": {
            "state": "provided_snapshot",
            "collector_state": "not_implemented_in_share_count_truth_wave",
            "source_receipt_id": source_receipt_id_for(source_receipt),
            "source_receipt_schema": COMPANYFACTS_SOURCE_RECEIPT_SCHEMA,
            "source_snapshot_id": current_snapshot["source_snapshot_id"],
        },
        "observations": output,
        "source_snapshots": source_snapshots,
        "counts": {
            "observations_total": len(output),
            "source_snapshots_total": len(source_snapshots),
            "current_snapshot": {
                "snapshot_fact_observations": len(current_snapshot["snapshot_fact_observations"]),
                **current_dispositions,
            },
        },
    }
    validate_share_count_ledger(result)
    return result
