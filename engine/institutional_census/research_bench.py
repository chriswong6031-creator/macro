"""Private, durable publication for the institutional 13F research bench.

The research bench contains manager identities and is deliberately excluded
from the public evidence bucket, site artifacts, and Git.  This module owns a
separate credential namespace and private-bucket keyspace.  Canonical bench
bytes are immutable and content addressed; one small compare-and-swap pointer
is the only mutable object.
"""

from __future__ import annotations

import calendar
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

from engine.research_vault.r2_store import (
    LocalStore,
    R2Store,
    StrictConditionalWriteStore,
    VersionedBytes,
)

from .models import (
    Institutional13FError,
    canonical_json_bytes,
    decode_canonical_json,
    normalize_report_period,
    normalize_utc,
    utc_datetime,
    validate_sha256,
    validate_version,
)

RESEARCH_BENCH_SCHEMA = "institutional_13f.research_bench/v1"
PRIVATE_RESEARCH_POINTER_SCHEMA = "institutional_13f.private_research_bench_pointer/v1"
PRIVATE_RESEARCH_PREFIX = "smart-money/13f/private-research/v1"
PRIVATE_RESEARCH_POINTER_KEY = f"{PRIVATE_RESEARCH_PREFIX}/current.json"
MAX_RESEARCH_BENCH_BYTES = 16 * 1024 * 1024
MAX_RESEARCH_POINTER_BYTES = 16 * 1024
MAX_RESEARCH_CANDIDATES = 500
RESEARCH_POINTER_CAS_ATTEMPTS = 3
RESEARCH_TEMPORAL_POLICY = "current_identifier_and_classification_maps"

_RESEARCH_ENVIRONMENT = (
    "INSTITUTIONAL_13F_RESEARCH_R2_ENDPOINT",
    "INSTITUTIONAL_13F_RESEARCH_R2_ACCESS_KEY_ID",
    "INSTITUTIONAL_13F_RESEARCH_R2_SECRET_ACCESS_KEY",
    "INSTITUTIONAL_13F_RESEARCH_R2_BUCKET",
)


class Institutional13FResearchBenchError(Institutional13FError):
    """Private research-bench publication failed closed."""


class Institutional13FResearchR2Store(R2Store):
    """R2 store bound only to the private research credential namespace."""

    credential_namespace = "INSTITUTIONAL_13F_RESEARCH_R2"

    def __init__(self, bucket: str, *, client: object) -> None:
        if not isinstance(bucket, str) or not bucket.strip():
            raise Institutional13FResearchBenchError(
                "dedicated institutional 13F research bucket is required"
            )
        if client is None:
            raise Institutional13FResearchBenchError(
                "dedicated institutional 13F research client is required"
            )
        super().__init__(bucket.strip(), client=client)


def _research_r2_client(*, endpoint: str, access_key: str, secret_key: str):
    """Construct a client without consulting public or generic R2 settings."""

    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover - production dependency is pinned.
        raise Institutional13FResearchBenchError(
            "boto3 is required for private institutional 13F research storage"
        ) from exc
    options = {
        "region_name": "auto",
        "signature_version": "s3v4",
        "max_pool_connections": 16,
        "retries": {"max_attempts": 5, "mode": "adaptive"},
        "connect_timeout": 15,
        "read_timeout": 60,
    }
    try:
        config = Config(
            **options,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    except TypeError:  # pragma: no cover - compatibility with older botocore.
        config = Config(**options)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=config,
    )


def build_institutional_13f_research_store(
    *,
    local_dir: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> StrictConditionalWriteStore:
    """Build an explicit local store or the dedicated private research store.

    No ``R2_*``, ``R2_RESEARCH_*``, public-evidence, or institutional evidence
    credential is ever used as a fallback.  A workflow may explicitly map its
    private secret names into this exact namespace before invoking the builder.
    """

    if local_dir is not None:
        if str(local_dir) == "":
            raise Institutional13FResearchBenchError(
                "private research local_dir cannot be empty"
            )
        return LocalStore(local_dir)

    source = os.environ if environment is None else environment
    configured = {name: source.get(name) for name in _RESEARCH_ENVIRONMENT}
    missing = [
        name
        for name, value in configured.items()
        if not isinstance(value, str) or not value
    ]
    if missing:
        raise Institutional13FResearchBenchError(
            "dedicated institutional 13F research R2 configuration is incomplete: "
            + ", ".join(missing)
        )
    client = _research_r2_client(
        endpoint=str(configured["INSTITUTIONAL_13F_RESEARCH_R2_ENDPOINT"]),
        access_key=str(configured["INSTITUTIONAL_13F_RESEARCH_R2_ACCESS_KEY_ID"]),
        secret_key=str(configured["INSTITUTIONAL_13F_RESEARCH_R2_SECRET_ACCESS_KEY"]),
    )
    return Institutional13FResearchR2Store(
        str(configured["INSTITUTIONAL_13F_RESEARCH_R2_BUCKET"]), client=client
    )


def _previous_quarter(period: str) -> str:
    current = date.fromisoformat(normalize_report_period(period))
    if (
        current.month not in {3, 6, 9, 12}
        or current.day != calendar.monthrange(current.year, current.month)[1]
    ):
        raise Institutional13FResearchBenchError(
            "private research current_period must be a calendar quarter end"
        )
    if current.month == 3:
        return date(current.year - 1, 12, 31).isoformat()
    previous_month = current.month - 3
    return date(
        current.year,
        previous_month,
        calendar.monthrange(current.year, previous_month)[1],
    ).isoformat()


def _bench_object_key(digest: str) -> str:
    normalized = validate_sha256(digest, field="research bench sha256")
    return (
        f"{PRIVATE_RESEARCH_PREFIX}/objects/sha256/{normalized[:2]}/{normalized}.json"
    )


@dataclass(frozen=True)
class PrivateResearchBenchPointer:
    current_period: str
    baseline_period: str
    source_cutoff_at: str
    published_at: str
    producer_version: str
    bench_sha256: str
    bench_byte_length: int
    bench_object_key: str
    schema: str = PRIVATE_RESEARCH_POINTER_SCHEMA

    def __post_init__(self) -> None:
        current = normalize_report_period(self.current_period)
        baseline = normalize_report_period(self.baseline_period)
        if baseline != _previous_quarter(current):
            raise Institutional13FResearchBenchError(
                "private research baseline_period must immediately precede current_period"
            )
        source_cutoff = normalize_utc(
            self.source_cutoff_at, field="research source_cutoff_at"
        )
        published = normalize_utc(self.published_at, field="research published_at")
        if utc_datetime(published, field="research published_at") < utc_datetime(
            source_cutoff, field="research source_cutoff_at"
        ):
            raise Institutional13FResearchBenchError(
                "private research published_at cannot predate source_cutoff_at"
            )
        digest = validate_sha256(self.bench_sha256, field="research bench sha256")
        if (
            isinstance(self.bench_byte_length, bool)
            or not isinstance(self.bench_byte_length, int)
            or not 1 <= self.bench_byte_length <= MAX_RESEARCH_BENCH_BYTES
        ):
            raise Institutional13FResearchBenchError(
                "private research bench byte length is invalid"
            )
        if self.bench_object_key != _bench_object_key(digest):
            raise Institutional13FResearchBenchError(
                "private research bench key does not bind its digest"
            )
        if self.schema != PRIVATE_RESEARCH_POINTER_SCHEMA:
            raise Institutional13FResearchBenchError(
                "private research pointer schema is unsupported"
            )
        object.__setattr__(self, "current_period", current)
        object.__setattr__(self, "baseline_period", baseline)
        object.__setattr__(self, "source_cutoff_at", source_cutoff)
        object.__setattr__(self, "published_at", published)
        object.__setattr__(
            self, "producer_version", validate_version(self.producer_version)
        )
        object.__setattr__(self, "bench_sha256", digest)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "current_period": self.current_period,
            "baseline_period": self.baseline_period,
            "source_cutoff_at": self.source_cutoff_at,
            "published_at": self.published_at,
            "producer_version": self.producer_version,
            "bench_sha256": self.bench_sha256,
            "bench_byte_length": self.bench_byte_length,
            "bench_object_key": self.bench_object_key,
        }

    def to_json_bytes(self) -> bytes:
        payload = canonical_json_bytes(self.to_dict())
        if len(payload) > MAX_RESEARCH_POINTER_BYTES:
            raise Institutional13FResearchBenchError(
                "private research pointer exceeds its byte ceiling"
            )
        return payload

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> PrivateResearchBenchPointer:
        if len(payload) > MAX_RESEARCH_POINTER_BYTES:
            raise Institutional13FResearchBenchError(
                "private research pointer exceeds its byte ceiling"
            )
        value = decode_canonical_json(payload, label="private research bench pointer")
        expected = {
            "schema",
            "current_period",
            "baseline_period",
            "source_cutoff_at",
            "published_at",
            "producer_version",
            "bench_sha256",
            "bench_byte_length",
            "bench_object_key",
        }
        if set(value) != expected:
            raise Institutional13FResearchBenchError(
                "private research pointer shape is invalid"
            )
        return cls(**value)


@dataclass(frozen=True)
class PublishedResearchBench:
    pointer: PrivateResearchBenchPointer
    bench: Mapping[str, Any]
    payload: bytes
    pointer_updated: bool

    def receipt(self) -> dict[str, Any]:
        """Return the private compiler receipt; never copy this into public JSON."""

        return {
            "schema": self.pointer.schema,
            "pointer_key": PRIVATE_RESEARCH_POINTER_KEY,
            "current_period": self.pointer.current_period,
            "baseline_period": self.pointer.baseline_period,
            "source_cutoff_at": self.pointer.source_cutoff_at,
            "sha256": self.pointer.bench_sha256,
            "byte_length": self.pointer.bench_byte_length,
            "pointer_updated": self.pointer_updated,
        }


def _require_store(store: object) -> StrictConditionalWriteStore:
    if not isinstance(store, StrictConditionalWriteStore):
        raise Institutional13FResearchBenchError(
            "private research publication requires a conditional-write store"
        )
    try:
        store.validate_strict_conditional_write_capability()
    except Exception as exc:
        raise Institutional13FResearchBenchError(
            "private research conditional-write capability validation failed"
        ) from exc
    return store


def _bounded_read(
    store: StrictConditionalWriteStore,
    key: str,
    maximum_bytes: int,
) -> bytes | None:
    try:
        payload = store.get_bytes_strict_bounded(key, maximum_bytes)
    except Exception as exc:
        raise Institutional13FResearchBenchError(
            f"private research bounded read failed for {key}"
        ) from exc
    if payload is not None and (
        type(payload) is not bytes or len(payload) > maximum_bytes
    ):
        raise Institutional13FResearchBenchError(
            f"private research bounded read is invalid for {key}"
        )
    return payload


def _create_immutable(
    store: StrictConditionalWriteStore,
    *,
    key: str,
    payload: bytes,
) -> bool:
    existing = _bounded_read(store, key, MAX_RESEARCH_BENCH_BYTES)
    if existing is not None:
        if existing == payload:
            return False
        raise Institutional13FResearchBenchError(
            "private research immutable object collision"
        )
    failure: BaseException | None = None
    try:
        written = store.put_bytes_strict_conditional(
            key,
            payload,
            expected_version=None,
            content_type="application/json",
        )
    except Exception as exc:  # noqa: BLE001 - acknowledgement can be lost.
        written = None
        failure = exc
    echoed = _bounded_read(store, key, MAX_RESEARCH_BENCH_BYTES)
    if echoed == payload:
        return written is True
    error = Institutional13FResearchBenchError(
        "private research immutable object write did not verify"
    )
    if failure is not None:
        raise error from failure
    raise error


def _validated_bench(
    bench: Mapping[str, Any],
    *,
    current_period: str,
    source_cutoff_at: str,
) -> tuple[Mapping[str, Any], bytes]:
    if not isinstance(bench, Mapping):
        raise Institutional13FResearchBenchError(
            "private research bench must be a mapping"
        )
    value = dict(bench)
    if value.get("schema") != RESEARCH_BENCH_SCHEMA:
        raise Institutional13FResearchBenchError(
            "private research bench schema is unsupported"
        )
    if value.get("authority") != "research_only":
        raise Institutional13FResearchBenchError(
            "private research bench authority must remain research_only"
        )
    if value.get("point_in_time") is not False:
        raise Institutional13FResearchBenchError(
            "private research bench must disclose point_in_time false"
        )
    if value.get("temporal_policy") != RESEARCH_TEMPORAL_POLICY:
        raise Institutional13FResearchBenchError(
            "private research bench temporal policy is unsupported"
        )
    if normalize_report_period(str(value.get("as_of_period") or "")) != current_period:
        raise Institutional13FResearchBenchError(
            "private research bench does not bind current_period"
        )
    generated_at = normalize_utc(
        value.get("generated_at"), field="research bench generated_at"
    )
    if generated_at != source_cutoff_at:
        raise Institutional13FResearchBenchError(
            "private research bench does not bind source_cutoff_at"
        )
    candidates = value.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > MAX_RESEARCH_CANDIDATES:
        raise Institutional13FResearchBenchError(
            "private research bench candidates are invalid"
        )
    if value.get("candidate_count") != len(candidates):
        raise Institutional13FResearchBenchError(
            "private research bench candidate count is inconsistent"
        )
    if not all(isinstance(candidate, Mapping) for candidate in candidates):
        raise Institutional13FResearchBenchError(
            "private research bench candidate rows are invalid"
        )
    payload = canonical_json_bytes(value)
    if not payload or len(payload) > MAX_RESEARCH_BENCH_BYTES:
        raise Institutional13FResearchBenchError(
            "private research bench exceeds its byte ceiling"
        )
    decoded = decode_canonical_json(payload, label="private research bench")
    return MappingProxyType(decoded), payload


def _load_pointer_versioned(
    store: StrictConditionalWriteStore,
) -> tuple[PrivateResearchBenchPointer | None, str | None]:
    try:
        observed = store.get_bytes_strict_bounded_versioned(
            PRIVATE_RESEARCH_POINTER_KEY, MAX_RESEARCH_POINTER_BYTES
        )
    except Exception as exc:
        raise Institutional13FResearchBenchError(
            "private research pointer versioned read failed"
        ) from exc
    if type(observed) is not VersionedBytes:
        raise Institutional13FResearchBenchError(
            "private research pointer versioned read returned an invalid value"
        )
    if observed.data is None:
        return None, None
    return PrivateResearchBenchPointer.from_json_bytes(observed.data), observed.version


def _load_payload(
    store: StrictConditionalWriteStore,
    pointer: PrivateResearchBenchPointer,
) -> tuple[Mapping[str, Any], bytes]:
    payload = _bounded_read(store, pointer.bench_object_key, MAX_RESEARCH_BENCH_BYTES)
    if payload is None:
        raise Institutional13FResearchBenchError(
            "private research bench object is missing"
        )
    if (
        len(payload) != pointer.bench_byte_length
        or sha256(payload).hexdigest() != pointer.bench_sha256
    ):
        raise Institutional13FResearchBenchError(
            "private research bench object receipt mismatch"
        )
    value = decode_canonical_json(payload, label="private research bench")
    validated, canonical = _validated_bench(
        value,
        current_period=pointer.current_period,
        source_cutoff_at=pointer.source_cutoff_at,
    )
    if canonical != payload:
        raise Institutional13FResearchBenchError(
            "private research bench object is not canonical"
        )
    return validated, payload


def _load_current_versioned(
    store: StrictConditionalWriteStore,
) -> tuple[PublishedResearchBench | None, str | None]:
    pointer, version = _load_pointer_versioned(store)
    if pointer is None:
        return None, None
    bench, payload = _load_payload(store, pointer)
    return PublishedResearchBench(pointer, bench, payload, False), version


def load_private_research_bench(
    store: StrictConditionalWriteStore,
) -> PublishedResearchBench:
    """Load and verify the complete bench through its private current pointer."""

    checked = _require_store(store)
    loaded, _version = _load_current_versioned(checked)
    if loaded is None:
        raise Institutional13FResearchBenchError(
            "private research bench pointer is missing"
        )
    return loaded


def _same_projection(
    first: PrivateResearchBenchPointer,
    second: PrivateResearchBenchPointer,
) -> bool:
    return bool(
        first.current_period == second.current_period
        and first.baseline_period == second.baseline_period
        and first.source_cutoff_at == second.source_cutoff_at
        and first.bench_sha256 == second.bench_sha256
        and first.bench_byte_length == second.bench_byte_length
        and first.bench_object_key == second.bench_object_key
    )


def _assert_successor(
    current: PrivateResearchBenchPointer,
    desired: PrivateResearchBenchPointer,
) -> bool:
    current_period = date.fromisoformat(current.current_period)
    desired_period = date.fromisoformat(desired.current_period)
    if desired_period < current_period:
        raise Institutional13FResearchBenchError(
            "private research current_period cannot rewind"
        )
    if (
        desired_period == current_period
        and desired.baseline_period != current.baseline_period
    ):
        raise Institutional13FResearchBenchError(
            "private research baseline_period cannot fork"
        )
    current_cutoff = utc_datetime(
        current.source_cutoff_at, field="research source_cutoff_at"
    )
    desired_cutoff = utc_datetime(
        desired.source_cutoff_at, field="research source_cutoff_at"
    )
    if desired_cutoff < current_cutoff:
        raise Institutional13FResearchBenchError(
            "private research source_cutoff_at cannot rewind"
        )
    if utc_datetime(desired.published_at, field="research published_at") < utc_datetime(
        current.published_at, field="research published_at"
    ):
        raise Institutional13FResearchBenchError(
            "private research published_at cannot rewind"
        )
    if desired_period == current_period and desired_cutoff == current_cutoff:
        if _same_projection(current, desired):
            return False
        raise Institutional13FResearchBenchError(
            "private research projection forks an existing source cutoff"
        )
    return True


def publish_private_research_bench(
    store: StrictConditionalWriteStore,
    *,
    bench: Mapping[str, Any],
    current_period: str,
    baseline_period: str,
    source_cutoff_at: str,
    published_at: str,
    producer_version: str,
) -> PublishedResearchBench:
    """Publish canonical bench bytes, then CAS-advance the private pointer."""

    checked = _require_store(store)
    current = normalize_report_period(current_period)
    baseline = normalize_report_period(baseline_period)
    cutoff = normalize_utc(source_cutoff_at, field="research source_cutoff_at")
    normalized_bench, payload = _validated_bench(
        bench, current_period=current, source_cutoff_at=cutoff
    )
    digest = sha256(payload).hexdigest()
    desired = PrivateResearchBenchPointer(
        current_period=current,
        baseline_period=baseline,
        source_cutoff_at=cutoff,
        published_at=published_at,
        producer_version=producer_version,
        bench_sha256=digest,
        bench_byte_length=len(payload),
        bench_object_key=_bench_object_key(digest),
    )
    desired_pointer_bytes = desired.to_json_bytes()
    immutable_ready = False

    for _attempt in range(RESEARCH_POINTER_CAS_ATTEMPTS):
        observed, version = _load_current_versioned(checked)
        if observed is not None:
            should_advance = _assert_successor(observed.pointer, desired)
            if not should_advance:
                # Retain the first verified publication metadata for exact
                # replay, just as immutable evidence receipts do.
                confirmed, _confirmed_version = _load_current_versioned(checked)
                if confirmed is not None and _same_projection(
                    confirmed.pointer, desired
                ):
                    return confirmed
                continue
        if not immutable_ready:
            _create_immutable(
                checked,
                key=desired.bench_object_key,
                payload=payload,
            )
            immutable_ready = True
        failure: BaseException | None = None
        try:
            written = checked.put_bytes_strict_conditional(
                PRIVATE_RESEARCH_POINTER_KEY,
                desired_pointer_bytes,
                expected_version=version,
                content_type="application/json",
            )
        except Exception as exc:  # noqa: BLE001 - acknowledgement can be lost.
            written = None
            failure = exc
        if written is True:
            loaded, _loaded_version = _load_current_versioned(checked)
            if (
                loaded is not None
                and loaded.pointer == desired
                and loaded.payload == payload
            ):
                return PublishedResearchBench(desired, normalized_bench, payload, True)
            raise Institutional13FResearchBenchError(
                "private research pointer write did not verify"
            )
        if written not in {False, None}:
            raise Institutional13FResearchBenchError(
                "private research pointer CAS returned a non-boolean result"
            )
        reconciled, _reconciled_version = _load_current_versioned(checked)
        if reconciled is not None and _same_projection(reconciled.pointer, desired):
            return PublishedResearchBench(
                reconciled.pointer, reconciled.bench, reconciled.payload, True
            )
        if failure is not None:
            raise Institutional13FResearchBenchError(
                "private research pointer CAS outcome is unknown"
            ) from failure

    raise Institutional13FResearchBenchError(
        "private research pointer CAS retry limit reached"
    )
