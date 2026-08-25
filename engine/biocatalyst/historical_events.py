"""Pointer-bound entitled projection for licensed BioCatalyst history.

The projection is deliberately separate from the CT.gov current-generation
pointer while sharing the existing BioCatalyst public root.  It is a read
materialization, not a source archive or event authority.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from .jv_snapshot import canonical_json_bytes


class HistoricalEventError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class HistoricalEventProjection:
    generation_id: str
    published_at: str
    capture_observed_at: str
    coverage: dict[str, Any]
    events: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class HistoricalEventPage:
    rows: tuple[dict[str, Any], ...]
    total: int
    next_cursor: str | None


_GEN_RE = re.compile(r"^bpcjv_gen_[0-9a-f]{24}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_EVENT_RE = re.compile(r"^bpcjv_event_[0-9a-f]{24}$")
_EVENT_KEYS = frozenset(
    {
        "contract_id",
        "schema_version",
        "event_id",
        "source",
        "company",
        "event",
        "asset",
        "historical_market",
        "normalization",
        "unsafe_fields",
        "authority",
    }
)
_PRIVATE_NORMALIZED_KEYS = frozenset(
    {
        "raw",
        "raw_row",
        "raw_bytes",
        "sha256",
        "hash",
        "manifest_sha256",
        "source_sha256",
        "object_key",
        "path",
        "locator",
        "company_url",
        "catalyst_url",
        "source_url",
        "receipt",
        "provenance",
    }
)
_SOURCE_KEYS = frozenset({"provider", "source_id", "license_class", "family", "source_ordinal", "capture_observed_at", "source_published_at", "source_published_at_state"})
_COMPANY_KEYS = frozenset({"ticker_evidence", "name_evidence", "resolution_state", "security_id", "issuer_id", "resolution_basis", "issuer_relationship_state"})
_CLOCK_KEYS = frozenset({"date", "date_precision", "family", "stage", "description", "source_available_at", "observed_at"})
_ASSET_KEYS = frozenset({"kind", "label", "indication"})
_MARKET_KEYS = frozenset({"price_at_event", "price_movement"})
_NORMALIZATION_KEYS = frozenset({"state", "repair"})
_AUTHORITY_KEYS = frozenset({"classification", "decision_authority", "allowed_uses", "forbidden_uses"})
_COVERAGE_KEYS = frozenset({"state", "source_rows", "normalized_rows", "identity_resolved", "identity_unresolved", "duplicates_collapsed", "families", "family_source_rows"})
_GENERATION_KEYS = frozenset({"contract_id", "schema_version", "generation_id", "published_at", "capture_observed_at", "coverage", "artifacts", "manifest_sha256"})
_KNOWN_FAMILIES = frozenset({"historical_fda", "device_history", "device_pipeline_history"})
_ALLOWED_USES = ["display", "context", "explain"]
_FORBIDDEN_USES = ["originate_signal", "rank_security", "select_security", "size_position", "gate_decision", "execute_trade", "raise_authority"]
_MAX_OBJECT_BYTES = 1_048_576
_MAX_EVENTS_BYTES = 67_108_864


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _refuse_private(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _normalized_key(str(key)) in _PRIVATE_NORMALIZED_KEYS:
                raise HistoricalEventError("HISTORICAL_EVENT_PRIVATE_FIELD")
            _refuse_private(child)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            _refuse_private(child)
    elif isinstance(value, str):
        folded = value.casefold()
        if re.search(r"(?:https?|s3|r2|file)://", folded) or "/raw/" in folded:
            raise HistoricalEventError("HISTORICAL_EVENT_PRIVATE_FIELD")


def _nullable_text(value: object, maximum: int) -> bool:
    return value is None or (isinstance(value, str) and len(value) <= maximum)


def _datetime_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _nonempty_text(value: object, maximum: int) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= maximum


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_coverage(value: object, *, event_count: int | None = None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _COVERAGE_KEYS:
        raise HistoricalEventError("HISTORICAL_EVENT_COVERAGE_INVALID")
    coverage = dict(value)
    numeric_keys = (
        "source_rows",
        "normalized_rows",
        "identity_resolved",
        "identity_unresolved",
        "duplicates_collapsed",
    )
    families = coverage.get("families")
    family_source_rows = coverage.get("family_source_rows")
    if (
        coverage.get("state") not in {"ready", "partial"}
        or any(not _count(coverage.get(key)) for key in numeric_keys)
        or not isinstance(families, Mapping)
        or not isinstance(family_source_rows, Mapping)
        or not set(families).issubset(_KNOWN_FAMILIES)
        or not set(family_source_rows).issubset(_KNOWN_FAMILIES)
        or any(not _count(item) for item in families.values())
        or any(not _count(item) for item in family_source_rows.values())
        or coverage["normalized_rows"] != sum(families.values())
        or coverage["source_rows"] != sum(family_source_rows.values())
        or coverage["normalized_rows"]
        != coverage["identity_resolved"] + coverage["identity_unresolved"]
        or any(families.get(family, 0) > family_source_rows.get(family, 0) for family in families)
        or (event_count is not None and coverage["normalized_rows"] != event_count)
    ):
        raise HistoricalEventError("HISTORICAL_EVENT_COVERAGE_INVALID")
    return coverage


def _validate_generation(value: object, *, generation_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _GENERATION_KEYS:
        raise HistoricalEventError("HISTORICAL_EVENT_GENERATION_INVALID")
    manifest = dict(value)
    digest = manifest.get("manifest_sha256")
    unhashed = dict(manifest)
    unhashed.pop("manifest_sha256", None)
    if (
        manifest.get("contract_id") != "biocatalyst_historical_event_generation.v1"
        or manifest.get("schema_version") != "1.0.0"
        or manifest.get("generation_id") != generation_id
        or not _datetime_text(manifest.get("published_at"))
        or not _datetime_text(manifest.get("capture_observed_at"))
        or not _DIGEST_RE.fullmatch(str(digest or ""))
        or digest != sha256(canonical_json_bytes(unhashed)).hexdigest()
    ):
        raise HistoricalEventError("HISTORICAL_EVENT_GENERATION_INVALID")
    published = datetime.fromisoformat(str(manifest["published_at"]).replace("Z", "+00:00"))
    captured = datetime.fromisoformat(str(manifest["capture_observed_at"]).replace("Z", "+00:00"))
    if published < captured:
        raise HistoricalEventError("HISTORICAL_EVENT_GENERATION_INVALID")
    _validate_coverage(manifest.get("coverage"))
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1 or not isinstance(artifacts[0], Mapping):
        raise HistoricalEventError("HISTORICAL_EVENT_GENERATION_INVALID")
    artifact = artifacts[0]
    if (
        set(artifact) != {"name", "sha256", "byte_count"}
        or artifact.get("name") != "events.jsonl"
        or not _DIGEST_RE.fullmatch(str(artifact.get("sha256", "")))
        or not _count(artifact.get("byte_count"))
        or artifact.get("byte_count") > _MAX_EVENTS_BYTES
    ):
        raise HistoricalEventError("HISTORICAL_EVENT_GENERATION_INVALID")
    return manifest


def validate_event(event: object) -> dict[str, Any]:
    if not isinstance(event, Mapping) or set(event) != _EVENT_KEYS:
        raise HistoricalEventError("HISTORICAL_EVENT_RECORD_INVALID")
    row = dict(event)
    if (
        row.get("contract_id") != "biocatalyst_historical_event_record.v1"
        or row.get("schema_version") != "1.0.0"
        or not _EVENT_RE.fullmatch(str(row.get("event_id", "")))
    ):
        raise HistoricalEventError("HISTORICAL_EVENT_RECORD_INVALID")
    source = row.get("source")
    company = row.get("company")
    clock = row.get("event")
    asset = row.get("asset")
    market = row.get("historical_market")
    normalization = row.get("normalization")
    authority = row.get("authority")
    if not all(isinstance(value, Mapping) for value in (source, company, clock, asset, market, normalization, authority)):
        raise HistoricalEventError("HISTORICAL_EVENT_RECORD_INVALID")
    if (
        set(source) != _SOURCE_KEYS
        or set(company) != _COMPANY_KEYS
        or set(clock) != _CLOCK_KEYS
        or set(asset) != _ASSET_KEYS
        or set(market) != _MARKET_KEYS
        or set(normalization) != _NORMALIZATION_KEYS
        or set(authority) != _AUTHORITY_KEYS
        or source.get("provider") != "BioPharmCatalyst"
        or source.get("source_id") != "biopharmcatalyst_jv_snapshot"
        or source.get("license_class") != "licensed_finite_snapshot"
        or source.get("family") not in {"historical_fda", "device_history", "device_pipeline_history"}
        or isinstance(source.get("source_ordinal"), bool)
        or not isinstance(source.get("source_ordinal"), int)
        or source.get("source_ordinal") < 1
        or not _datetime_text(source.get("capture_observed_at"))
        or source.get("source_published_at_state") not in {"observed", "unknown"}
        or (source.get("source_published_at_state") == "unknown" and source.get("source_published_at") is not None)
        or (source.get("source_published_at_state") == "observed" and not _datetime_text(source.get("source_published_at")))
        or company.get("resolution_state") not in {"resolved", "unresolved", "ambiguous", "stale_ticker"}
        or company.get("resolution_basis") not in {"time_scoped_alias", "current_catalog_only", "none", "ambiguous"}
        or company.get("issuer_relationship_state") not in {"current_only", "unavailable"}
        or not _nullable_text(company.get("ticker_evidence"), 32)
        or not _nullable_text(company.get("name_evidence"), 240)
        or not _nullable_text(company.get("security_id"), 240)
        or not _nullable_text(company.get("issuer_id"), 240)
        or clock.get("family") not in {"regulatory", "device"}
        or not _nullable_text(clock.get("stage"), 160)
        or not _nullable_text(clock.get("description"), 600)
        or not _datetime_text(clock.get("observed_at"))
        or asset.get("kind") not in {"drug", "device", "unknown"}
        or not _nullable_text(asset.get("label"), 240)
        or not _nullable_text(asset.get("indication"), 320)
        or not _nullable_text(market.get("price_at_event"), 64)
        or not _nullable_text(market.get("price_movement"), 64)
        or normalization.get("state") != "deterministic"
        or normalization.get("repair") not in {"none", "missing_row_index_unshifted"}
        or authority.get("decision_authority") is not False
        or authority.get("classification") != "licensed_historical_context"
        or authority.get("allowed_uses") != _ALLOWED_USES
        or authority.get("forbidden_uses") != _FORBIDDEN_USES
        or not isinstance(row.get("unsafe_fields"), list)
        or any(not isinstance(value, str) for value in row.get("unsafe_fields", ()))
        or len(row.get("unsafe_fields", ())) != len(set(row.get("unsafe_fields", ())))
    ):
        raise HistoricalEventError("HISTORICAL_EVENT_RIGHTS_INVALID")
    try:
        date.fromisoformat(str(clock.get("date")))
    except ValueError:
        raise HistoricalEventError("HISTORICAL_EVENT_DATE_INVALID") from None
    if clock.get("date_precision") != "day" or clock.get("source_available_at") is not None:
        raise HistoricalEventError("HISTORICAL_EVENT_CLOCK_INVALID")
    resolution_state = company.get("resolution_state")
    resolution_basis = company.get("resolution_basis")
    security_id = company.get("security_id")
    issuer_id = company.get("issuer_id")
    issuer_relationship = company.get("issuer_relationship_state")
    if resolution_state == "resolved":
        if (
            not _nonempty_text(security_id, 240)
            or resolution_basis not in {"time_scoped_alias", "current_catalog_only"}
            or (issuer_id is not None and not _nonempty_text(issuer_id, 240))
            or (issuer_id is not None and issuer_relationship != "current_only")
            or (issuer_id is None and issuer_relationship != "unavailable")
        ):
            raise HistoricalEventError("HISTORICAL_EVENT_IDENTITY_INVALID")
    elif (
        security_id is not None
        or issuer_id is not None
        or issuer_relationship != "unavailable"
        or (resolution_state == "ambiguous" and resolution_basis != "ambiguous")
        or (resolution_state in {"unresolved", "stale_ticker"} and resolution_basis != "none")
    ):
        raise HistoricalEventError("HISTORICAL_EVENT_IDENTITY_INVALID")
    if clock.get("observed_at") != source.get("capture_observed_at"):
        raise HistoricalEventError("HISTORICAL_EVENT_CLOCK_INVALID")
    if row["unsafe_fields"] != sorted(row["unsafe_fields"]):
        raise HistoricalEventError("HISTORICAL_EVENT_RIGHTS_INVALID")
    _refuse_private(row)
    return row


def _load_object(path: Path, code: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise HistoricalEventError(code)
    try:
        raw = path.read_bytes()
        if len(raw) > _MAX_OBJECT_BYTES:
            raise ValueError
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        raise HistoricalEventError(code) from None
    if not isinstance(value, dict):
        raise HistoricalEventError(code)
    return value


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


class HistoricalEventPublisher:
    """Validate, promote and read one content-addressed historical projection."""

    def __init__(self, root: Path) -> None:
        raw = Path(root)
        if raw.is_symlink():
            raise HistoricalEventError("HISTORICAL_EVENT_ROOT_INVALID")
        self.root = raw.resolve()

    @property
    def pointer_path(self) -> Path:
        return self.root / "current.json"

    @property
    def generations_root(self) -> Path:
        return self.root / "generations"

    def publish(
        self,
        events: Sequence[Mapping[str, Any]],
        *,
        coverage: Mapping[str, Any],
        capture_observed_at: str,
        published_at: str,
    ) -> HistoricalEventProjection:
        validated = tuple(validate_event(event) for event in events)
        validated_coverage = _validate_coverage(coverage, event_count=len(validated))
        if not _datetime_text(capture_observed_at) or not _datetime_text(published_at):
            raise HistoricalEventError("HISTORICAL_EVENT_GENERATION_INVALID")
        ids = [row["event_id"] for row in validated]
        if len(ids) != len(set(ids)):
            raise HistoricalEventError("HISTORICAL_EVENT_DUPLICATE")
        ordered = tuple(sorted(validated, key=lambda row: (row["event"]["date"], row["event_id"]), reverse=True))
        events_bytes = b"".join(canonical_json_bytes(row) + b"\n" for row in ordered)
        artifact_sha = sha256(events_bytes).hexdigest()
        generation_seed = {
            "events_sha256": artifact_sha,
            "coverage": validated_coverage,
            "capture_observed_at": capture_observed_at,
            "published_at": published_at,
        }
        generation_id = "bpcjv_gen_" + sha256(canonical_json_bytes(generation_seed)).hexdigest()[:24]
        manifest = {
            "contract_id": "biocatalyst_historical_event_generation.v1",
            "schema_version": "1.0.0",
            "generation_id": generation_id,
            "published_at": published_at,
            "capture_observed_at": capture_observed_at,
            "coverage": validated_coverage,
            "artifacts": [{"name": "events.jsonl", "sha256": artifact_sha, "byte_count": len(events_bytes)}],
        }
        manifest["manifest_sha256"] = sha256(canonical_json_bytes(manifest)).hexdigest()
        _validate_generation(manifest, generation_id=generation_id)
        manifest_bytes = canonical_json_bytes(manifest) + b"\n"
        self.generations_root.mkdir(parents=True, exist_ok=True)
        if self.generations_root.is_symlink():
            raise HistoricalEventError("HISTORICAL_EVENT_ROOT_INVALID")
        generation = self.generations_root / generation_id
        if generation.exists():
            existing_manifest = generation / "manifest.json"
            existing_events = generation / "events.jsonl"
            if (
                not generation.is_dir()
                or generation.is_symlink()
                or {path.name for path in generation.iterdir()} != {"manifest.json", "events.jsonl"}
                or not existing_manifest.is_file()
                or existing_manifest.is_symlink()
                or not existing_events.is_file()
                or existing_events.is_symlink()
                or existing_manifest.read_bytes() != manifest_bytes
                or existing_events.read_bytes() != events_bytes
            ):
                raise HistoricalEventError("HISTORICAL_EVENT_GENERATION_COLLISION")
        else:
            staging = Path(tempfile.mkdtemp(prefix=f".{generation_id}.", dir=self.generations_root))
            try:
                (staging / "events.jsonl").write_bytes(events_bytes)
                (staging / "manifest.json").write_bytes(manifest_bytes)
                os.replace(staging, generation)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        pointer = {
            "contract_id": "biocatalyst_historical_event_pointer.v1",
            "schema_version": "1.0.0",
            "generation_id": generation_id,
            "manifest_sha256": manifest["manifest_sha256"],
            "published_at": published_at,
        }
        _atomic_write(self.pointer_path, canonical_json_bytes(pointer) + b"\n")
        return self.read_current()

    def read_current(self) -> HistoricalEventProjection:
        if self.generations_root.is_symlink():
            raise HistoricalEventError("HISTORICAL_EVENT_ROOT_INVALID")
        pointer = _load_object(self.pointer_path, "HISTORICAL_EVENT_UNAVAILABLE")
        if set(pointer) != {
            "contract_id",
            "schema_version",
            "generation_id",
            "manifest_sha256",
            "published_at",
        }:
            raise HistoricalEventError("HISTORICAL_EVENT_POINTER_INVALID")
        generation_id = str(pointer.get("generation_id", ""))
        if (
            pointer.get("contract_id") != "biocatalyst_historical_event_pointer.v1"
            or pointer.get("schema_version") != "1.0.0"
            or not _GEN_RE.fullmatch(generation_id)
            or not _DIGEST_RE.fullmatch(str(pointer.get("manifest_sha256", "")))
            or not _datetime_text(pointer.get("published_at"))
        ):
            raise HistoricalEventError("HISTORICAL_EVENT_POINTER_INVALID")
        generation = self.generations_root / generation_id
        if not generation.is_dir() or generation.is_symlink():
            raise HistoricalEventError("HISTORICAL_EVENT_GENERATION_INVALID")
        children = {path.name for path in generation.iterdir()}
        if children != {"manifest.json", "events.jsonl"}:
            raise HistoricalEventError("HISTORICAL_EVENT_GENERATION_INVALID")
        manifest = _validate_generation(
            _load_object(generation / "manifest.json", "HISTORICAL_EVENT_GENERATION_INVALID"),
            generation_id=generation_id,
        )
        if (
            manifest["manifest_sha256"] != pointer.get("manifest_sha256")
            or manifest["published_at"] != pointer.get("published_at")
        ):
            raise HistoricalEventError("HISTORICAL_EVENT_GENERATION_INVALID")
        artifacts = manifest.get("artifacts")
        artifact = artifacts[0]
        events_path = generation / "events.jsonl"
        if not events_path.is_file() or events_path.is_symlink():
            raise HistoricalEventError("HISTORICAL_EVENT_ARTIFACT_INVALID")
        events_bytes = events_path.read_bytes()
        if (
            len(events_bytes) > _MAX_EVENTS_BYTES
            or artifact.get("byte_count") != len(events_bytes)
            or artifact.get("sha256") != sha256(events_bytes).hexdigest()
        ):
            raise HistoricalEventError("HISTORICAL_EVENT_ARTIFACT_INVALID")
        events: list[dict[str, Any]] = []
        try:
            for line in events_bytes.splitlines():
                if line:
                    events.append(validate_event(json.loads(line)))
        except (UnicodeError, json.JSONDecodeError):
            raise HistoricalEventError("HISTORICAL_EVENT_ARTIFACT_INVALID") from None
        ids = [row["event_id"] for row in events]
        if len(ids) != len(set(ids)):
            raise HistoricalEventError("HISTORICAL_EVENT_DUPLICATE")
        expected_order = sorted(events, key=lambda row: (row["event"]["date"], row["event_id"]), reverse=True)
        if events != expected_order:
            raise HistoricalEventError("HISTORICAL_EVENT_ORDER_INVALID")
        coverage = _validate_coverage(manifest.get("coverage"), event_count=len(events))
        return HistoricalEventProjection(
            generation_id=generation_id,
            published_at=str(manifest.get("published_at")),
            capture_observed_at=str(manifest.get("capture_observed_at")),
            coverage=dict(coverage),
            events=tuple(events),
        )


def _query_binding(
    *,
    q: str | None,
    family: str,
    stage: str | None,
    asset: str | None,
    from_date: str | None,
    to_date: str | None,
    limit: int,
) -> bytes:
    return canonical_json_bytes(
        {
            "q": q or "",
            "family": family,
            "stage": stage or "",
            "asset": asset or "",
            "from_date": from_date or "",
            "to_date": to_date or "",
            "limit": limit,
        }
    )


def _cursor(offset: int, binding: bytes, key: bytes) -> str:
    payload = {"offset": offset, "query": sha256(binding).hexdigest()}
    body = canonical_json_bytes(payload)
    signature = hmac.new(key, body, "sha256").hexdigest()
    return base64.urlsafe_b64encode(body + b"." + signature.encode()).decode().rstrip("=")


def _decode_cursor(value: str | None, binding: bytes, key: bytes) -> int:
    if value is None:
        return 0
    if len(value) > 512 or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise HistoricalEventError("HISTORICAL_EVENT_CURSOR_INVALID")
    try:
        padded = value + "=" * (-len(value) % 4)
        body, signature = base64.urlsafe_b64decode(padded.encode()).rsplit(b".", 1)
        expected = hmac.new(key, body, "sha256").hexdigest().encode()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(body)
        offset = payload["offset"]
        query_digest = payload["query"]
    except (ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        raise HistoricalEventError("HISTORICAL_EVENT_CURSOR_INVALID") from None
    if query_digest != sha256(binding).hexdigest():
        raise HistoricalEventError("HISTORICAL_EVENT_CURSOR_QUERY_MISMATCH")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise HistoricalEventError("HISTORICAL_EVENT_CURSOR_INVALID")
    return offset


def query_events(
    events: Sequence[Mapping[str, Any]],
    *,
    q: str | None,
    family: str,
    stage: str | None,
    asset: str | None,
    from_date: str | None,
    to_date: str | None,
    limit: int,
    cursor: str | None,
    cursor_key: bytes,
) -> HistoricalEventPage:
    if family not in {"all", "regulatory", "device"}:
        raise HistoricalEventError("HISTORICAL_EVENT_FILTER_INVALID")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise HistoricalEventError("HISTORICAL_EVENT_FILTER_INVALID")
    try:
        lower = date.fromisoformat(from_date) if from_date else None
        upper = date.fromisoformat(to_date) if to_date else None
    except ValueError:
        raise HistoricalEventError("HISTORICAL_EVENT_FILTER_INVALID") from None
    if lower and upper and lower > upper:
        raise HistoricalEventError("HISTORICAL_EVENT_FILTER_INVALID")
    normalized_q = " ".join((q or "").casefold().split()) or None
    normalized_stage = " ".join((stage or "").casefold().split()) or None
    normalized_asset = " ".join((asset or "").casefold().split()) or None
    binding = _query_binding(q=normalized_q, family=family, stage=normalized_stage, asset=normalized_asset, from_date=from_date, to_date=to_date, limit=limit)
    offset = _decode_cursor(cursor, binding, cursor_key)
    matched: list[dict[str, Any]] = []
    for raw in events:
        row = validate_event(raw)
        company = row["company"]
        event = row["event"]
        asset_block = row["asset"]
        event_day = date.fromisoformat(event["date"])
        haystack = " ".join(str(value or "") for value in (company.get("ticker_evidence"), company.get("name_evidence"))).casefold()
        asset_haystack = " ".join(str(value or "") for value in (asset_block.get("label"), asset_block.get("indication"))).casefold()
        if normalized_q and normalized_q not in haystack:
            continue
        if family != "all" and event.get("family") != family:
            continue
        if normalized_stage and normalized_stage not in str(event.get("stage") or "").casefold():
            continue
        if normalized_asset and normalized_asset not in asset_haystack:
            continue
        if lower and event_day < lower:
            continue
        if upper and event_day > upper:
            continue
        matched.append(row)
    matched.sort(key=lambda row: (row["event"]["date"], row["event_id"]), reverse=True)
    page = tuple(matched[offset : offset + limit])
    next_offset = offset + len(page)
    return HistoricalEventPage(page, len(matched), _cursor(next_offset, binding, cursor_key) if next_offset < len(matched) else None)
