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
COMPILER_VERSION = "capital-structure-share-count-truth/1.0.0"

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


def _receipt_material(receipt: Mapping[str, Any]) -> dict[str, str]:
    required = (
        "issuer_id", "source_url", "source_payload_sha256", "source_retrieved_at",
        "system_available_at",
    )
    missing = [key for key in required if not str(receipt.get(key) or "").strip()]
    if missing:
        raise ShareCountTruthError(f"source receipt missing required fields: {', '.join(missing)}")
    if str(receipt.get("source_system") or "sec_companyfacts") != "sec_companyfacts":
        raise ShareCountTruthError("source receipt source_system must be sec_companyfacts")
    if str(receipt.get("acquisition_state") or "provided_snapshot") != "provided_snapshot":
        raise ShareCountTruthError("source receipt acquisition_state must be provided_snapshot")
    issuer_id = str(receipt["issuer_id"])
    cik = _issuer_cik(issuer_id)
    source_url = str(receipt["source_url"])
    expected_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    if source_url != expected_url:
        raise ShareCountTruthError("source receipt source_url must exactly identify the issuer Company Facts endpoint")
    payload_hash = str(receipt["source_payload_sha256"]).lower()
    if not re.fullmatch(r"[a-f0-9]{64}", payload_hash):
        raise ShareCountTruthError("source receipt source_payload_sha256 must be lowercase SHA-256")
    retrieved = _parse_timestamp(receipt["source_retrieved_at"], "source_retrieved_at")
    available = _parse_timestamp(receipt["system_available_at"], "system_available_at")
    if _timestamp(available) < _timestamp(retrieved):
        raise ShareCountTruthError("system_available_at cannot precede source_retrieved_at")
    return {
        "issuer_id": issuer_id,
        "source_url": source_url,
        "source_payload_sha256": payload_hash,
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


def observation_id_for(record: Mapping[str, Any]) -> str:
    """Digest the full immutable version, excluding its self-referential ID."""
    material = deepcopy(dict(record))
    material.pop("observation_id", None)
    return _digest_id("share-count:cs:", material)


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
            "source_system": "sec_companyfacts",
            "source_url": receipt["source_url"],
            "source_payload_sha256": receipt["source_payload_sha256"],
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
    record["observation_id"] = observation_id_for(record)
    return record


def _revision_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    material = deepcopy(dict(record))
    material.pop("observation_id", None)
    material.pop("version", None)
    material.pop("relationships", None)
    return material


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
    if _canonical_json(_revision_payload(candidate)) == _canonical_json(_revision_payload(current)):
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


def source_acquisition_unavailable_result(*, reason: str = "no_retained_companyfacts_snapshot_supplied") -> dict[str, Any]:
    """Explicitly represent the deliberate absence of a collector in this wave."""
    return {
        "schema": "capital_structure.share_count_compile_result.v1",
        "status": "unavailable",
        "source_acquisition": {
            "state": "unavailable",
            "collector_state": "not_implemented_in_share_count_truth_wave",
            "reason": reason,
        },
        "observations": [],
        "counts": {"observations": 0, "new_observations": 0, "deferred": 0, "ambiguous": 0},
    }


def compile_share_count_observations(
    source_bytes: bytes,
    source_receipt: Mapping[str, Any],
    *,
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
    validate_share_count_history(existing_observations)

    grouped: dict[tuple[str | None, ...], list[dict[str, Any]]] = defaultdict(list)
    for candidate in _fact_candidates(
        payload, issuer_id=receipt["issuer_id"], system_available_at=receipt["system_available_at"],
    ):
        grouped[candidate["slot_key"]].append(candidate)
    new_rows: list[dict[str, Any]] = []
    for _slot, group in sorted(grouped.items(), key=lambda item: repr(item[0])):
        row = _record_from_group(group, receipt=receipt)
        applied, is_new = _apply_correction_history(row, existing_observations)
        if is_new:
            new_rows.append(applied)

    output = [dict(row) for row in existing_observations] + new_rows
    validate_share_count_history(output)
    output.sort(key=lambda row: (
        str(row.get("issuer_id") or ""), str(row.get("logical_observation_id") or ""),
        int((row.get("version") or {}).get("correction_version") or 0),
    ))
    current_rows = [row for row in output if row in new_rows]
    return {
        "schema": "capital_structure.share_count_compile_result.v1",
        "status": "ok",
        "compiler_version": COMPILER_VERSION,
        "source_acquisition": {
            "state": "provided_snapshot",
            "collector_state": "not_implemented_in_share_count_truth_wave",
            "source_receipt_id": source_receipt_id_for(source_receipt),
        },
        "observations": output,
        "counts": {
            "observations": len(output),
            "new_observations": len(new_rows),
            "deferred": sum(row["state"]["disposition"] == "deferred" for row in current_rows),
            "ambiguous": sum(row["state"]["disposition"] == "ambiguous" for row in current_rows),
        },
    }
