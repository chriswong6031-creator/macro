"""Pure OFAC SDN parser and sanctions-geography projector.

All geography is address-evidence geography. Nothing in this module infers a
person's or entity's current location from nationality, citizenship, flag,
birthplace, program, identifiers, narrative, or model output.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping
from xml.etree import ElementTree as ET


CURRENT_NAMESPACE = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"
DELTA_NAMESPACE = "https://www.treasury.gov/ofac/DeltaFile/1.0"
SCHEMA_VERSION = "mastermind.sanctions_geography.v1"
PARSER_REVISION = "ofac-sanctions-v1.0.3"
DEFAULT_MAX_XML_BYTES = 50_000_000
DEFAULT_MAX_ENTRIES = 25_000
DEFAULT_MAX_ADDRESSES_PER_ENTRY = 200
DEFAULT_MAX_SUPERSEDED_OBSERVATIONS = 32

_CURRENT = f"{{{CURRENT_NAMESPACE}}}"
_DELTA = f"{{{DELTA_NAMESPACE}}}"
_UNSAFE_XML_RE = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9]+")

# Source-specific spelling bridge into the existing Natural Earth 1:110m
# geometry identities. This is not an ISO registry and intentionally does not
# roll territories or Region:* source values into sovereign geometries.
OFAC_TO_NATURAL_EARTH_NAME = {
    "bahamas the": "Bahamas",
    "bosnia and herzegovina": "Bosnia and Herz.",
    "burma": "Myanmar",
    "central african republic": "Central African Rep.",
    "congo democratic republic of the": "Dem. Rep. Congo",
    "congo republic of the": "Congo",
    "czech republic": "Czechia",
    "dominican republic": "Dominican Rep.",
    "equatorial guinea": "Eq. Guinea",
    "korea north": "North Korea",
    "korea south": "South Korea",
    "north macedonia the republic of": "Macedonia",
    "south sudan": "S. Sudan",
    "the gambia": "Gambia",
    "united states": "United States of America",
}


class SourceShapeError(RuntimeError):
    """The official payload no longer matches the frozen parser contract."""


class ProjectionBoundsError(RuntimeError):
    """A bounded consumer would otherwise be silently truncated."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    value = _SPACE_RE.sub(" ", element.text).strip()
    if len(value) > 20_000:
        raise SourceShapeError("source text exceeds reviewed bound")
    return value


def _child_text(parent: ET.Element, tag: str, ns: str) -> str:
    return _text(parent.find(ns + tag))


def _reject_hostile_xml(payload: bytes, *, max_bytes: int = DEFAULT_MAX_XML_BYTES) -> None:
    if not payload:
        raise SourceShapeError("empty XML payload")
    if len(payload) > max_bytes:
        raise SourceShapeError(f"XML payload exceeds {max_bytes} byte bound")
    if _UNSAFE_XML_RE.search(payload):
        raise SourceShapeError("DTD/entity declarations are forbidden")


def _parse_root(payload: bytes, *, namespace: str, root_name: str) -> ET.Element:
    _reject_hostile_xml(payload)
    try:
        root = ET.parse(io.BytesIO(payload)).getroot()
    except ET.ParseError as exc:
        raise SourceShapeError(f"invalid XML: {exc}") from exc
    expected = f"{{{namespace}}}{root_name}"
    if root.tag != expected:
        raise SourceShapeError(f"unexpected root namespace/tag: {root.tag!r}; expected {expected!r}")
    return root


def _normalized_text(value: str) -> str:
    return _SPACE_RE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def _name_key(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return _PUNCT_RE.sub(" ", ascii_value).strip()


def _address_fingerprint(address: Mapping[str, Any]) -> str:
    fields = {
        key: _normalized_text(str(address.get(key) or "")).casefold()
        for key in ("line1", "line2", "line3", "city", "state_province", "postal_code", "published_country")
    }
    return hashlib.sha256(canonical_json_bytes(fields)).hexdigest()


def _entry_fingerprint(entry: Mapping[str, Any]) -> str:
    value = {
        "uid": entry["uid"],
        "name": entry["name"],
        "entity_type": entry["entity_type"],
        "programs": entry["programs"],
        "addresses": [
            {key: address.get(key) for key in (
                "line1", "line2", "line3", "city", "state_province", "postal_code", "published_country"
            )}
            for address in entry["addresses"]
        ],
    }
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _basic_name(entry: ET.Element) -> str:
    parts = [
        _child_text(entry, "firstName", _CURRENT),
        _child_text(entry, "middleName", _CURRENT),
        _child_text(entry, "lastName", _CURRENT),
        _child_text(entry, "suffix", _CURRENT),
    ]
    return _normalized_text(" ".join(part for part in parts if part))


def _basic_address(element: ET.Element) -> dict[str, Any]:
    address = {
        "line1": _child_text(element, "address1", _CURRENT),
        "line2": _child_text(element, "address2", _CURRENT),
        "line3": _child_text(element, "address3", _CURRENT),
        "city": _child_text(element, "city", _CURRENT),
        "state_province": _child_text(element, "stateOrProvince", _CURRENT),
        "postal_code": _child_text(element, "postalCode", _CURRENT),
        "published_country": _child_text(element, "country", _CURRENT),
    }
    address["address_id"] = _address_fingerprint(address)[:24]
    source_uid = _child_text(element, "uid", _CURRENT)
    address["source_address_uids"] = [source_uid] if source_uid else []
    return address


def parse_current_sdn(
    payload: bytes,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_addresses_per_entry: int = DEFAULT_MAX_ADDRESSES_PER_ENTRY,
) -> dict[str, Any]:
    root = _parse_root(payload, namespace=CURRENT_NAMESPACE, root_name="sdnList")
    publication = root.find(_CURRENT + "publshInformation")
    if publication is None:
        raise SourceShapeError("missing publshInformation")
    raw_date = _child_text(publication, "Publish_Date", _CURRENT)
    try:
        published_at = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
    except ValueError as exc:
        raise SourceShapeError(f"unexpected Publish_Date: {raw_date!r}") from exc
    raw_count = _child_text(publication, "Record_Count", _CURRENT)
    if not raw_count.isdigit():
        raise SourceShapeError("Record_Count is not an integer")

    entries: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for index, element in enumerate(root.findall(_CURRENT + "sdnEntry")):
        if index >= max_entries:
            raise ProjectionBoundsError(f"entry bound exceeded: {max_entries}")
        uid = _child_text(element, "uid", _CURRENT)
        identity_resolved = bool(uid and uid.isdigit())
        if not identity_resolved:
            uid = "unresolved:" + hashlib.sha256(ET.tostring(element, encoding="utf-8")).hexdigest()[:24]
        programs = sorted({
            _text(program)
            for program in element.findall(f"{_CURRENT}programList/{_CURRENT}program")
            if _text(program)
        })
        addresses_by_id: dict[str, dict[str, Any]] = {}
        for address_element in element.findall(f"{_CURRENT}addressList/{_CURRENT}address"):
            address = _basic_address(address_element)
            key = address["address_id"]
            if key in addresses_by_id:
                known = addresses_by_id[key]["source_address_uids"]
                known.extend(item for item in address["source_address_uids"] if item not in known)
                known.sort(key=lambda item: int(item) if item.isdigit() else item)
            else:
                addresses_by_id[key] = address
        if len(addresses_by_id) > max_addresses_per_entry:
            raise ProjectionBoundsError(f"address bound exceeded for UID {uid}: {max_addresses_per_entry}")
        entry = {
            "uid": uid,
            "list_identity": "OFAC_SDN",
            "identity_resolved": identity_resolved,
            "name": _basic_name(element),
            "entity_type": _child_text(element, "sdnType", _CURRENT),
            "programs": programs,
            "addresses": sorted(addresses_by_id.values(), key=lambda row: row["address_id"]),
        }
        entry["source_fingerprint"] = _entry_fingerprint(entry)
        if uid in seen and seen[uid] != entry["source_fingerprint"]:
            raise SourceShapeError(f"duplicate UID {uid} has conflicting source fields")
        if uid not in seen:
            seen[uid] = entry["source_fingerprint"]
            entries.append(entry)

    expected_count = int(raw_count)
    if expected_count != len(entries):
        raise SourceShapeError(f"record count mismatch: source={expected_count} parsed={len(entries)}")
    entries.sort(key=lambda row: (0, int(row["uid"])) if row["uid"].isdigit() else (1, row["uid"]))
    return {"published_at": published_at, "record_count": expected_count, "entries": entries}


def _delta_name(entity: ET.Element) -> str:
    names = entity.findall(f"{_DELTA}names/{_DELTA}name")
    primary = next((name for name in names if _child_text(name, "isPrimary", _DELTA).casefold() == "true"), None)
    if primary is None:
        primary = names[0] if names else None
    if primary is None:
        return ""
    translations = primary.findall(f"{_DELTA}translations/{_DELTA}translation")
    translation = next(
        (row for row in translations if _child_text(row, "isPrimary", _DELTA).casefold() == "true"),
        translations[0] if translations else None,
    )
    if translation is None:
        return ""
    return (
        _child_text(translation, "formattedFullName", _DELTA)
        or _child_text(translation, "formattedLastName", _DELTA)
        or _normalized_text(" ".join(
            _child_text(part, "value", _DELTA)
            for part in translation.findall(f"{_DELTA}nameParts/{_DELTA}namePart")
        ))
    )


def _delta_address(element: ET.Element) -> dict[str, Any]:
    parts: defaultdict[str, list[str]] = defaultdict(list)
    for part in element.findall(f"{_DELTA}translations/{_DELTA}translation/{_DELTA}addressParts/{_DELTA}addressPart"):
        kind = _child_text(part, "type", _DELTA).upper()
        value = _child_text(part, "value", _DELTA)
        if value:
            parts[kind].append(value)
    address = {
        "line1": " · ".join(parts["ADDRESS1"]),
        "line2": " · ".join(parts["ADDRESS2"]),
        "line3": " · ".join(parts["ADDRESS3"]),
        "city": " · ".join(parts["CITY"]),
        "state_province": " · ".join(parts["STATE/PROVINCE"]),
        "postal_code": " · ".join(parts["POSTAL CODE"]),
        "published_country": _child_text(element, "country", _DELTA),
    }
    address["address_id"] = _address_fingerprint(address)[:24]
    source_uid = element.attrib.get("id", "")
    address["source_address_uids"] = [source_uid] if source_uid else []
    return address


def _delta_field_operations(entity: ET.Element, *, max_operations: int = 5_000) -> list[dict[str, str | None]]:
    operations: list[dict[str, str | None]] = []

    def visit(parent: ET.Element, path: tuple[str, ...]) -> None:
        for child in list(parent):
            local = child.tag.rsplit("}", 1)[-1]
            child_path = (*path, local)
            action = child.attrib.get("action")
            if action:
                if action not in {"add", "remove", "update"}:
                    raise SourceShapeError(f"unrecognized delta field action: {action!r}")
                operations.append({
                    "path": "/".join(child_path),
                    "action": action,
                    "old_value": child.attrib.get("oldValue"),
                    "value": _text(child),
                })
                if len(operations) > max_operations:
                    raise ProjectionBoundsError(f"delta field-operation bound exceeded: {max_operations}")
            visit(child, child_path)

    visit(entity, ())
    return operations


def parse_delta(payload: bytes, *, max_changes: int = DEFAULT_MAX_ENTRIES) -> dict[str, Any]:
    root = _parse_root(payload, namespace=DELTA_NAMESPACE, root_name="sanctionsData")
    publication = root.find(_DELTA + "publicationInfo")
    if publication is None:
        raise SourceShapeError("delta publicationInfo missing")
    published_at = _child_text(publication, "datePublished", _DELTA)
    if not published_at:
        raise SourceShapeError("delta datePublished missing")
    changes: list[dict[str, Any]] = []
    for index, entity in enumerate(root.findall(f"{_DELTA}entities/{_DELTA}entity")):
        if index >= max_changes:
            raise ProjectionBoundsError(f"delta change bound exceeded: {max_changes}")
        raw_action = entity.attrib.get("action")
        # DeltaFile.xsd makes entity@action optional. An absent entity action is
        # an in-place correction whose child fields carry add/remove/update
        # operations; it is not an unidentified add or remove.
        action = raw_action.strip().casefold() if raw_action is not None else "correct"
        if action not in {"add", "remove", "correct"}:
            raise SourceShapeError(f"unrecognized delta action: {action!r}")
        uid = entity.attrib.get("id", "").strip()
        identity_resolved = bool(uid and uid.isdigit())
        if not identity_resolved:
            uid = "unresolved:" + hashlib.sha256(ET.tostring(entity, encoding="utf-8")).hexdigest()[:24]
        programs = sorted({
            _text(program)
            for program in entity.findall(f"{_DELTA}sanctionsPrograms/{_DELTA}sanctionsProgram")
            if _text(program)
        })
        addresses_by_id: dict[str, dict[str, Any]] = {}
        for address_element in entity.findall(f"{_DELTA}addresses/{_DELTA}address"):
            address = _delta_address(address_element)
            addresses_by_id.setdefault(address["address_id"], address)
        general_info = entity.find(_DELTA + "generalInfo")
        change = {
            "uid": uid,
            "list_identity": "OFAC_SDN",
            "identity_resolved": identity_resolved,
            "action": action,
            "name": _delta_name(entity),
            "entity_type": _child_text(general_info if general_info is not None else ET.Element("x"), "entityType", _DELTA),
            "programs": programs,
            "addresses": sorted(addresses_by_id.values(), key=lambda row: row["address_id"]),
            "field_operations": _delta_field_operations(entity),
        }
        change["source_fingerprint"] = _entry_fingerprint(change)
        changes.append(change)
    return {
        "published_at": published_at,
        "publication_type": _child_text(publication, "publicationType", _DELTA),
        "changes": changes,
    }


def _boundary_index(topology: Mapping[str, Any]) -> tuple[dict[str, dict[str, str]], str]:
    try:
        geometries = topology["objects"]["countries"]["geometries"]
    except (KeyError, TypeError) as exc:
        raise SourceShapeError("Natural Earth topology lacks objects.countries.geometries") from exc
    if not isinstance(geometries, list):
        raise SourceShapeError("Natural Earth countries geometry collection is not a list")
    index: dict[str, dict[str, str]] = {}
    seen_ids: set[str] = set()
    for geometry in geometries:
        geo_id = str(geometry.get("id", ""))
        name = str((geometry.get("properties") or {}).get("name", "")).strip()
        if not name:
            raise SourceShapeError("Natural Earth geometry identity is missing or duplicated")
        # The existing 1:110m asset contains three disputed/de-facto shapes
        # (N. Cyprus, Somaliland, Kosovo) without numeric IDs. They remain visible
        # boundary context but cannot become canonical aggregate identities.
        if not geo_id:
            continue
        if geo_id in seen_ids:
            raise SourceShapeError("Natural Earth geometry identity is missing or duplicated")
        seen_ids.add(geo_id)
        index[_name_key(name)] = {"geo_id": geo_id, "geo_name": name}
    return index, hashlib.sha256(canonical_json_bytes(topology)).hexdigest()


def _resolve_country(published_country: str, boundary_index: Mapping[str, dict[str, str]]) -> dict[str, Any]:
    key = _name_key(published_country)
    target_name = OFAC_TO_NATURAL_EARTH_NAME.get(key, published_country)
    boundary = boundary_index.get(_name_key(target_name))
    if not published_country or key.startswith("region ") or boundary is None:
        return {"geo_id": None, "geo_name": None, "state": "GEO_UNRESOLVED"}
    return {"geo_id": boundary["geo_id"], "geo_name": boundary["geo_name"], "state": "RESOLVED"}


def _receipt_identities(receipts: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_key": receipt.get("source_key"),
            "raw_sha256": receipt.get("raw_sha256"),
            "schema_revision": receipt.get("schema_revision"),
            "parser_revision": receipt.get("parser_revision"),
        }
        for receipt in receipts
    ]


def _source_identity(
    current_receipt: Mapping[str, Any],
    delta_receipts: list[Mapping[str, Any]],
    schema_receipts: list[Mapping[str, Any]],
    catalog_receipts: list[Mapping[str, Any]],
    topology_hash: str,
) -> str:
    return hashlib.sha256(canonical_json_bytes({
        "current": _receipt_identities([current_receipt]),
        "deltas": _receipt_identities(delta_receipts),
        "schemas": _receipt_identities(schema_receipts),
        "catalogs": _receipt_identities(catalog_receipts),
        "topology_sha256": topology_hash,
        "parser_revision": PARSER_REVISION,
    })).hexdigest()


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _stale_after(published_at: str) -> str:
    day = _parse_day(published_at)
    if day is None:
        raise SourceShapeError("current publication date is not ISO-compatible")
    return (day + timedelta(days=8)).isoformat() + "T00:00:00Z"


def _address_label(address: Mapping[str, Any]) -> str:
    fields = [
        address.get("line1"), address.get("line2"), address.get("line3"), address.get("city"),
        address.get("state_province"), address.get("postal_code"), address.get("published_country"),
    ]
    return ", ".join(str(value) for value in fields if value)


def _observation_snapshot(
    entry: Mapping[str, Any],
    *,
    source_identity: str,
) -> dict[str, Any]:
    """Retain the exact prior accepted fact surface without nesting its history."""

    return {
        "uid": str(entry.get("uid") or ""),
        "list_identity": str(entry.get("list_identity") or "OFAC_SDN"),
        "identity_resolved": bool(entry.get("identity_resolved")),
        "name": str(entry.get("name") or ""),
        "entity_type": str(entry.get("entity_type") or ""),
        "programs": copy.deepcopy(list(entry.get("programs") or [])),
        "addresses": copy.deepcopy(list(entry.get("addresses") or [])),
        "states": copy.deepcopy(list(entry.get("states") or [])),
        "source_fingerprint": str(entry.get("source_fingerprint") or ""),
        "observed_in_source_identity": str(
            entry.get("observed_in_source_identity") or source_identity
        ),
    }


def build_projection(
    *,
    current_xml: bytes,
    current_receipt: Mapping[str, Any],
    delta_documents: list[tuple[bytes, Mapping[str, Any]]],
    topology: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    as_of: str,
    schema_receipts: list[Mapping[str, Any]] | None = None,
    catalog_receipts: list[Mapping[str, Any]] | None = None,
    boundary_receipt: Mapping[str, Any] | None = None,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_superseded_observations: int = DEFAULT_MAX_SUPERSEDED_OBSERVATIONS,
) -> dict[str, Any]:
    """Build the bounded canonical projection; no network or filesystem effects."""

    # Validate the caller clock without making it content identity. Freshness is
    # represented by the deterministic stale_after threshold.
    try:
        datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("as_of must be an ISO datetime") from exc
    if max_superseded_observations < 1:
        raise ValueError("max_superseded_observations must be positive")

    boundary_index, topology_hash = _boundary_index(topology)
    delta_receipts = [receipt for _, receipt in delta_documents]
    schema_receipts = list(schema_receipts or [])
    catalog_receipts = list(catalog_receipts or [])
    identity = _source_identity(current_receipt, delta_receipts, schema_receipts, catalog_receipts, topology_hash)
    if (
        previous
        and previous.get("schema_version") == SCHEMA_VERSION
        and previous.get("source_identity") == identity
        and previous.get("source_state") == "CURRENT"
        and "degraded" not in previous
    ):
        return copy.deepcopy(previous)

    current = parse_current_sdn(current_xml, max_entries=max_entries)
    if len(current["entries"]) > max_entries:
        raise ProjectionBoundsError(f"entry bound exceeded: {max_entries}")
    parsed_deltas: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
    for payload, receipt in delta_documents:
        parsed_deltas.append((parse_delta(payload), receipt))
    parsed_deltas.sort(key=lambda item: (item[0]["published_at"], str(item[1].get("source_key"))))

    latest_action: dict[str, str] = {}
    changes: list[dict[str, Any]] = []
    for parsed, receipt in parsed_deltas:
        for change in parsed["changes"]:
            latest_action[change["uid"]] = change["action"]
            projected_change = copy.deepcopy(change)
            projected_change["published_at"] = parsed["published_at"]
            projected_change["publication_type"] = parsed["publication_type"]
            projected_change["state"] = {
                "add": "ADDED",
                "remove": "REMOVED",
                "correct": "SOURCE_CORRECTED",
            }[change["action"]]
            projected_change["source_key"] = receipt.get("source_key")
            for address in projected_change["addresses"]:
                address.update(_resolve_country(address["published_country"], boundary_index))
                address["published_address"] = _address_label(address)
            changes.append(projected_change)
    changes.sort(key=lambda row: (row["published_at"], row["uid"], row["action"]), reverse=True)

    previous_by_uid = {
        str(row.get("uid")): row
        for row in (previous or {}).get("entries", [])
        if row.get("uid") is not None
    }
    entries: list[dict[str, Any]] = []
    country_entry_ids: defaultdict[str, set[str]] = defaultdict(set)
    country_address_counts: Counter[str] = Counter()
    country_program_entry_ids: defaultdict[str, defaultdict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    geo_names: dict[str, str] = {}
    unresolved: Counter[str] = Counter()

    for raw_entry in current["entries"]:
        entry = copy.deepcopy(raw_entry)
        states = ["CURRENT"] if entry["identity_resolved"] else ["CURRENT", "IDENTITY_UNRESOLVED"]
        if latest_action.get(entry["uid"]) == "add":
            states.append("ADDED")
        prior = previous_by_uid.get(entry["uid"])
        if latest_action.get(entry["uid"]) == "correct" or (
            prior and prior.get("source_fingerprint") != entry["source_fingerprint"]
        ):
            states.append("SOURCE_CORRECTED")
        entry["states"] = states
        entry["observed_in_source_identity"] = identity
        if prior:
            raw_history = prior.get("superseded_observations", [])
            if not isinstance(raw_history, list) or not all(
                isinstance(row, Mapping) for row in raw_history
            ):
                raise SourceShapeError(
                    f"prior superseded observation history is malformed for UID {entry['uid']}"
                )
            history = copy.deepcopy(raw_history)
            if prior.get("source_fingerprint") != entry["source_fingerprint"]:
                history.append(
                    _observation_snapshot(
                        prior,
                        source_identity=str((previous or {}).get("source_identity") or ""),
                    )
                )
            if len(history) > max_superseded_observations:
                raise ProjectionBoundsError(
                    "superseded observation bound exceeded for UID "
                    f"{entry['uid']}: {max_superseded_observations}"
                )
            if history:
                entry["superseded_observations"] = history
        for address in entry["addresses"]:
            address.update(_resolve_country(address["published_country"], boundary_index))
            address["published_address"] = _address_label(address)
            if address["geo_id"] is None:
                unresolved[address["published_country"] or "(blank)"] += 1
                continue
            geo_id = address["geo_id"]
            geo_names[geo_id] = address["geo_name"]
            country_entry_ids[geo_id].add(entry["uid"])
            country_address_counts[geo_id] += 1
            for program in entry["programs"]:
                country_program_entry_ids[geo_id][program].add(entry["uid"])
        entries.append(entry)

    country_change_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for change in changes:
        if change["state"] in {"ADDED", "REMOVED"}:
            for geo_id in {address["geo_id"] for address in change["addresses"] if address["geo_id"]}:
                country_change_counts[geo_id][change["state"]] += 1

    countries = []
    for geo_id in sorted(country_entry_ids, key=lambda value: (-len(country_entry_ids[value]), geo_names[value], value)):
        programs = [
            {"program": program, "entries": len(ids)}
            for program, ids in country_program_entry_ids[geo_id].items()
        ]
        programs.sort(key=lambda row: (-row["entries"], row["program"]))
        countries.append({
            "geo_id": geo_id,
            "country": geo_names[geo_id],
            "entries": len(country_entry_ids[geo_id]),
            "published_addresses": country_address_counts[geo_id],
            "added": country_change_counts[geo_id]["ADDED"],
            "removed": country_change_counts[geo_id]["REMOVED"],
            "programs": programs,
        })

    total_addresses = sum(len(entry["addresses"]) for entry in entries)
    resolved_addresses = total_addresses - sum(unresolved.values())
    entries_with_addresses = sum(bool(entry["addresses"]) for entry in entries)
    projection: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "parser_revision": PARSER_REVISION,
        "capability_state": "BUILT_NOT_PROVEN",
        "production_state": "PRODUCTION_INERT",
        "source_state": "CURRENT",
        "source_identity": identity,
        "projection_id": "sha256:" + identity,
        "source": {
            "current": dict(current_receipt),
            "schemas": [dict(receipt) for receipt in schema_receipts],
            "catalogs": [dict(receipt) for receipt in catalog_receipts],
            "deltas": [dict(receipt) for receipt in delta_receipts],
            "rights": {
                "ofac": "official_government_public_information",
                "ofac_url": "https://ofac.treasury.gov/sanctions-list-service",
                "boundaries": "Natural Earth public domain",
                "boundaries_url": "https://www.naturalearthdata.com/about/terms-of-use/",
            },
        },
        "boundary": dict(boundary_receipt or {
            "source_key": "natural_earth_world_110m_existing_asset",
            "asset": "site/world-110m.json",
            "canonical_sha256": topology_hash,
        }),
        "freshness": {
            "published_at": current["published_at"],
            "stale_after": _stale_after(current["published_at"]),
        },
        "summary": {
            "current_entries": len(entries),
            "entries_with_published_addresses": entries_with_addresses,
            "published_addresses": total_addresses,
            "geo_resolved_addresses": resolved_addresses,
            "geo_unresolved_addresses": sum(unresolved.values()),
            "resolved_countries": len(countries),
            "recent_official_changes": len(changes),
        },
        "countries": countries,
        "entries": entries,
        "changes": changes,
        "unresolved_geography": [
            {"published_country": name, "published_addresses": count, "state": "GEO_UNRESOLVED"}
            for name, count in sorted(unresolved.items(), key=lambda item: (-item[1], item[0]))
        ],
        "method": {
            "geography_basis": "published_address_country_only",
            "not_current_location": True,
            "nationality_citizenship_flag_birthplace_excluded": True,
            "model_output_authority": "NONE",
            "delta_membership_authority": "NONE_CURRENT_FULL_SNAPSHOT_WINS",
            "hard_entry_bound": max_entries,
            "hard_superseded_observation_bound_per_entry": max_superseded_observations,
        },
    }
    return projection
