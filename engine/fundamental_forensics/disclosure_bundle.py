"""Immutable disclosure-projection bundle transport for the render path.

The nightly render needs exactly one thing from the Filing Forensics SEC lane:
the twelve bounded private disclosure projections the workbench attaches.  It
does not need the raw Submissions cache, the accession archive, or the growing
immutable source store those projections were built from — restoring that store
is linear in its size and had grown to ~24 minutes on the render path.

This module publishes the projections as ONE immutable, content-addressed
bundle plus a compare-and-swap ``latest`` pointer, so a consumer pays one
bounded GET for the pointer and one bounded GET for the bundle regardless of
how large the source store becomes.

The protocol deliberately mirrors :mod:`engine.fundamental_forensics.source_sync`
rather than importing its private helpers: create-only immutable writes with
exact-byte readback, a strictly decoded pointer that is never silently
overwritten, and a monotone pointer clock.  The owned versioned prefix is
``fundamental_forensics/disclosures/v1``; changing that layout is a storage
migration, not an implementation detail.

Every clock is supplied by the caller.  There is intentionally no ``now()``
fallback anywhere in this module.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence

from engine.research_vault.r2_store import (
    Store,
    StrictConditionalWriteStore,
    VersionedBytes,
)

from .disclosure_projection import (
    validate_disclosure_projection,
    write_disclosure_projection,
)
from .models import canonical_json, parse_utc, utc_text


DISCLOSURE_BUNDLE_SCHEMA = "fundamental_forensics.disclosure_projection_bundle/v1"
DISCLOSURE_BUNDLE_LATEST_SCHEMA = (
    "fundamental_forensics.disclosure_projection_bundle_latest/v1"
)
DISCLOSURE_BUNDLE_PUBLISH_SCHEMA = (
    "fundamental_forensics.disclosure_projection_bundle_publish/v1"
)
DISCLOSURE_BUNDLE_RESTORE_SCHEMA = (
    "fundamental_forensics.disclosure_projection_bundle_restore/v1"
)
DISCLOSURE_BUNDLE_PREFIX = "fundamental_forensics/disclosures/v1"
DISCLOSURE_BUNDLE_LATEST_KEY = f"{DISCLOSURE_BUNDLE_PREFIX}/latest.json"

# Hard ceilings, not suggestions: the bundle carries twelve bounded projections
# whose own per-track caps live in disclosure_projection.  A remote object that
# outgrows this ceiling is a schema failure, not a bigger download.
HARD_MAX_BUNDLE_BYTES = 64 * 1024 * 1024
HARD_MAX_POINTER_BYTES = 4096

# One hour of tolerated forward skew between the consumer's explicit clock and
# the publisher's: two hosts, two samplings, no shared clock authority.
MAX_FUTURE_SKEW_SECONDS = 3600.0

_BUNDLE_ID_RE = re.compile(r"^ffdiscbundle_[a-f0-9]{64}$")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")
_PATH_PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_BUNDLE_KEYS = frozenset({"schema", "bundle_id", "published_at", "tickers", "projections"})
_POINTER_KEYS = frozenset({"schema", "bundle_id", "bundle_key", "published_at"})


class DisclosureBundleError(RuntimeError):
    """A disclosure-projection bundle cannot be safely published or restored."""


def _normalized_clock(value: str | datetime, *, field: str) -> str:
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise DisclosureBundleError(str(exc)) from exc
    if parsed is None:
        raise DisclosureBundleError(f"{field} is required")
    return utc_text(parsed) or ""  # pragma: no cover - parsed is non-null


def _clock_datetime(value: str, *, field: str) -> datetime:
    parsed = parse_utc(value, field=field)
    if parsed is None:  # pragma: no cover - callers normalize first
        raise DisclosureBundleError(f"{field} is required")
    return parsed


def _normalized_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise DisclosureBundleError(f"invalid ticker: {value!r}")
    return ticker


def _validate_key(key: str) -> str:
    """Validate an R2 key before passing it to a fail-open generic store."""
    if not isinstance(key, str) or not key.startswith(DISCLOSURE_BUNDLE_PREFIX + "/"):
        raise DisclosureBundleError("object key is outside the owned bundle prefix")
    if len(key) > 1024 or "\\" in key or "\x00" in key or "?" in key or "#" in key:
        raise DisclosureBundleError("unsafe object key")
    path = PurePosixPath(key)
    if path.is_absolute() or not path.parts or any(
        part in {"", ".", ".."} or not _PATH_PART_RE.fullmatch(part)
        for part in path.parts
    ):
        raise DisclosureBundleError("unsafe object key")
    return key


def bundle_object_key(bundle_id: str) -> str:
    """Return the only valid immutable object key for one bundle identity."""
    if not isinstance(bundle_id, str) or not _BUNDLE_ID_RE.fullmatch(bundle_id):
        raise DisclosureBundleError("invalid disclosure bundle id")
    return f"{DISCLOSURE_BUNDLE_PREFIX}/bundles/{bundle_id}.json"


def _strict_json_object(content: bytes, *, label: str) -> dict[str, Any]:
    """Decode canonical bundle JSON without duplicate-key or nonfinite ambiguity."""
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError(f"duplicate JSON key: {key!r}")
            output[key] = value
        return output

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise DisclosureBundleError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise DisclosureBundleError(f"{label} must be an object")
    return value


def _bundle_body(
    *, published_at: str, projections: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Return the canonical identity-free bundle body for one projection set."""
    if not isinstance(projections, Mapping) or not projections:
        raise DisclosureBundleError("disclosure bundle requires at least one projection")
    body_projections: dict[str, Any] = {}
    for raw_ticker, projection in projections.items():
        if type(raw_ticker) is not str:
            raise DisclosureBundleError("disclosure bundle ticker key must be a string")
        ticker = _normalized_ticker(raw_ticker)
        if ticker != raw_ticker:
            raise DisclosureBundleError(
                f"disclosure bundle ticker key is not normalized: {raw_ticker!r}"
            )
        try:
            validate_disclosure_projection(projection)
        except ValueError as exc:
            raise DisclosureBundleError(
                f"disclosure bundle projection for {ticker} is invalid: {exc}"
            ) from exc
        issuer_ticker = str((projection.get("issuer") or {}).get("ticker") or "")
        if issuer_ticker != ticker:
            raise DisclosureBundleError(
                f"disclosure bundle key {ticker} does not match projection issuer {issuer_ticker}"
            )
        body_projections[ticker] = dict(projection)
    return {
        "schema": DISCLOSURE_BUNDLE_SCHEMA,
        "bundle_id": "",
        "published_at": published_at,
        "tickers": sorted(body_projections),
        "projections": body_projections,
    }


def _bundle_id_for(body: Mapping[str, Any]) -> str:
    """Hash the canonical identity-free body, mirroring the source-snapshot id."""
    identity = dict(body)
    identity["bundle_id"] = ""
    return "ffdiscbundle_" + sha256(canonical_json(identity).encode("utf-8")).hexdigest()


def build_disclosure_bundle(
    projections: Mapping[str, Mapping[str, Any]], *, published_at: str
) -> dict[str, Any]:
    """Build one canonical bundle from already-validated private projections.

    ``published_at`` is the publisher's explicit UTC clock; a naive or missing
    value is rejected rather than replaced by a machine clock.  Keys must be
    normalized tickers equal to their projection's ``issuer.ticker`` so a
    consumer's ticker-set check cannot be satisfied by a mislabeled payload.
    """
    body = _bundle_body(
        published_at=_normalized_clock(published_at, field="published_at"),
        projections=projections,
    )
    body["bundle_id"] = _bundle_id_for(body)
    validate_disclosure_bundle(body)
    return body


def validate_disclosure_bundle(value: Mapping[str, Any]) -> None:
    """Validate a bundle strictly enough to reject torn or substituted data."""
    if not isinstance(value, Mapping):
        raise DisclosureBundleError("disclosure bundle must be an object")
    if set(value) != set(_BUNDLE_KEYS):
        raise DisclosureBundleError("disclosure bundle shape is invalid")
    if value.get("schema") != DISCLOSURE_BUNDLE_SCHEMA:
        raise DisclosureBundleError("unsupported disclosure bundle schema")
    bundle_id = value.get("bundle_id")
    if not isinstance(bundle_id, str) or not _BUNDLE_ID_RE.fullmatch(bundle_id):
        raise DisclosureBundleError("disclosure bundle id is invalid")
    published_at = value.get("published_at")
    if published_at != _normalized_clock(str(published_at or ""), field="published_at"):
        raise DisclosureBundleError("disclosure bundle clock is not UTC-normalized")
    projections = value.get("projections")
    if not isinstance(projections, Mapping) or not projections:
        raise DisclosureBundleError("disclosure bundle requires at least one projection")
    tickers = value.get("tickers")
    if not isinstance(tickers, list) or tickers != sorted(projections):
        raise DisclosureBundleError("disclosure bundle ticker index does not match its projections")
    body = _bundle_body(published_at=str(published_at), projections=projections)
    if _bundle_id_for(body) != bundle_id or dict(value) != {**body, "bundle_id": bundle_id}:
        raise DisclosureBundleError("disclosure bundle identity or canonical body is invalid")


def _bundle_bytes(bundle: Mapping[str, Any]) -> bytes:
    validate_disclosure_bundle(bundle)
    payload = canonical_json(dict(bundle)).encode("utf-8")
    if len(payload) > HARD_MAX_BUNDLE_BYTES:
        raise DisclosureBundleError(
            f"disclosure bundle exceeds hard byte ceiling ({len(payload)} > {HARD_MAX_BUNDLE_BYTES})"
        )
    return payload


def _read_bounded_optional(store: Any, key: str, *, maximum_bytes: int) -> bytes | None:
    """Strictly read at most ``maximum_bytes`` while preserving absence.

    Absence is meaningful here only as the predecessor for a conditional create
    or pointer CAS; a network, auth, or body failure must never be downgraded
    into "the object is not there".
    """
    key = _validate_key(key)
    try:
        result = store.get_bytes_strict_bounded(key, maximum_bytes)
    except Exception as exc:  # noqa: BLE001 - never downgrade an outage to absence.
        raise DisclosureBundleError(f"private bundle-store bounded read failed for {key}") from exc
    if result is not None and not isinstance(result, bytes):
        raise DisclosureBundleError(f"private bundle-store returned non-bytes for {key}")
    if result is not None and len(result) > maximum_bytes:
        raise DisclosureBundleError(
            f"private bundle-store ignored bounded read limit for {key}"
        )
    return result


def _readback_immutable_create(
    store: StrictConditionalWriteStore,
    *,
    key: str,
    payload: bytes,
    maximum_bytes: int,
    cause: BaseException | None,
) -> None:
    """Reconcile a failed/ambiguous create without attempting an overwrite."""
    try:
        echoed = _read_bounded_optional(store, key, maximum_bytes=maximum_bytes)
    except DisclosureBundleError as exc:
        error = DisclosureBundleError(f"private bundle-store immutable write failed for {key}")
        raise error from (cause if cause is not None else exc)
    if echoed == payload:
        return
    error = DisclosureBundleError(
        f"disclosure bundle immutable object collision: {key}"
        if echoed is not None
        else f"private bundle-store immutable object read-back mismatch: {key}"
    )
    if cause is not None:
        raise error from cause
    raise error


def _create_immutable(
    store: StrictConditionalWriteStore, *, key: str, payload: bytes, maximum_bytes: int
) -> bool:
    """Create one immutable object with ``If-None-Match`` semantics.

    A false conditional response, timeout, or connection loss is resolved only
    by a bounded exact-byte readback: exact bytes prove idempotent completion;
    different bytes are a collision; no state is ever repaired by an overwrite.
    Returns True only when this call performed the accepted create.
    """
    key = _validate_key(key)
    if type(payload) is not bytes:
        raise DisclosureBundleError("immutable bundle payload must be exact bytes")
    if len(payload) > maximum_bytes:
        raise DisclosureBundleError("immutable bundle payload exceeds bounded read limit")
    try:
        written = store.put_bytes_strict_conditional(
            key, payload, expected_version=None, content_type="application/json"
        )
    except Exception as exc:  # noqa: BLE001 - remote commit may already have happened.
        _readback_immutable_create(
            store, key=key, payload=payload, maximum_bytes=maximum_bytes, cause=exc
        )
        return False
    if written is True:
        echoed = _read_bounded_optional(store, key, maximum_bytes=maximum_bytes)
        if echoed != payload:
            raise DisclosureBundleError(
                f"private bundle-store immutable object read-back mismatch: {key}"
            )
        return True
    if written is False:
        _readback_immutable_create(
            store, key=key, payload=payload, maximum_bytes=maximum_bytes, cause=None
        )
        return False
    raise DisclosureBundleError(f"private bundle-store immutable write failed for {key}")


def _pointer_body(bundle: Mapping[str, Any]) -> dict[str, Any]:
    bundle_id = str(bundle["bundle_id"])
    return {
        "schema": DISCLOSURE_BUNDLE_LATEST_SCHEMA,
        "bundle_id": bundle_id,
        "bundle_key": bundle_object_key(bundle_id),
        "published_at": str(bundle["published_at"]),
    }


def _decode_pointer(content: bytes) -> dict[str, Any]:
    """Decode the sole mutable key strictly; a corrupt pointer is never repaired."""
    value = _strict_json_object(content, label="disclosure bundle pointer")
    if set(value) != set(_POINTER_KEYS):
        raise DisclosureBundleError("disclosure bundle pointer shape is invalid")
    if value.get("schema") != DISCLOSURE_BUNDLE_LATEST_SCHEMA:
        raise DisclosureBundleError("unsupported disclosure bundle pointer")
    bundle_id = value.get("bundle_id")
    if not isinstance(bundle_id, str) or not _BUNDLE_ID_RE.fullmatch(bundle_id):
        raise DisclosureBundleError("disclosure bundle pointer id is invalid")
    if value.get("bundle_key") != bundle_object_key(bundle_id):
        raise DisclosureBundleError("disclosure bundle pointer key does not bind its id")
    normalized = _normalized_clock(str(value.get("published_at") or ""), field="published_at")
    if value.get("published_at") != normalized:
        raise DisclosureBundleError("disclosure bundle pointer clock is invalid")
    if canonical_json(value).encode("utf-8") != content:
        raise DisclosureBundleError("disclosure bundle pointer is not canonically encoded")
    return value


def _read_versioned_pointer(store: StrictConditionalWriteStore) -> VersionedBytes:
    """Read the exact predecessor token for the sole mutable bundle key."""
    try:
        observed = store.get_bytes_strict_bounded_versioned(
            DISCLOSURE_BUNDLE_LATEST_KEY, HARD_MAX_POINTER_BYTES
        )
    except Exception as exc:  # noqa: BLE001 - latest availability is publication authority.
        raise DisclosureBundleError(
            "disclosure bundle latest pointer versioned read failed"
        ) from exc
    if type(observed) is not VersionedBytes:
        raise DisclosureBundleError("disclosure bundle latest pointer versioned read is invalid")
    if observed.data is None:
        if observed.version is not None:
            raise DisclosureBundleError("missing disclosure bundle pointer has a version")
    elif (
        type(observed.data) is not bytes
        or not isinstance(observed.version, str)
        or not observed.version
    ):
        raise DisclosureBundleError("present disclosure bundle pointer lacks an opaque version")
    return observed


def publish_disclosure_bundle(
    store: StrictConditionalWriteStore, bundle: Mapping[str, Any]
) -> dict[str, Any]:
    """Publish one immutable bundle, then advance ``latest`` by exact-predecessor CAS.

    The pointer is monotone in the publisher's explicit clock: a bundle older
    than the currently published one is refused rather than rewinding what the
    render path reads.  Re-publishing the identical bundle is idempotent.
    """
    if not isinstance(store, StrictConditionalWriteStore):
        raise DisclosureBundleError(
            "disclosure bundle publication requires a StrictConditionalWriteStore adapter"
        )
    try:
        store.validate_strict_conditional_write_capability()
    except Exception as exc:  # noqa: BLE001 - capability must be proven pre-write.
        raise DisclosureBundleError(
            "disclosure bundle conditional-write capability validation failed"
        ) from exc
    payload = _bundle_bytes(bundle)
    bundle_id = str(bundle["bundle_id"])
    key = bundle_object_key(bundle_id)
    _create_immutable(store, key=key, payload=payload, maximum_bytes=HARD_MAX_BUNDLE_BYTES)

    pointer = _pointer_body(bundle)
    pointer_bytes = canonical_json(pointer).encode("utf-8")
    if len(pointer_bytes) > HARD_MAX_POINTER_BYTES:  # pragma: no cover - fixed small shape
        raise DisclosureBundleError("disclosure bundle pointer exceeds its byte ceiling")
    prior = _read_versioned_pointer(store)
    if prior.data is not None:
        current = _decode_pointer(prior.data)
        if current["bundle_id"] == bundle_id:
            if prior.data != pointer_bytes:
                raise DisclosureBundleError(
                    "disclosure bundle pointer disagrees with its immutable bundle"
                )
            return {
                "schema": DISCLOSURE_BUNDLE_PUBLISH_SCHEMA,
                "bundle_id": bundle_id,
                "bundle_key": key,
                "published_at": str(bundle["published_at"]),
                "tickers": list(bundle["tickers"]),
                "pointer_updated": False,
            }
        if str(current["published_at"]) > str(bundle["published_at"]):
            raise DisclosureBundleError(
                "stale disclosure bundle cannot rewind a newer published pointer"
            )
    try:
        written = store.put_bytes_strict_conditional(
            DISCLOSURE_BUNDLE_LATEST_KEY,
            pointer_bytes,
            expected_version=prior.version,
            content_type="application/json",
        )
    except Exception as exc:  # noqa: BLE001 - acknowledgement may have been lost.
        _pointer_after_failed_cas(store, payload=pointer_bytes, cause=exc)
    else:
        if written is not True:
            _pointer_after_failed_cas(store, payload=pointer_bytes, cause=None)
    return {
        "schema": DISCLOSURE_BUNDLE_PUBLISH_SCHEMA,
        "bundle_id": bundle_id,
        "bundle_key": key,
        "published_at": str(bundle["published_at"]),
        "tickers": list(bundle["tickers"]),
        "pointer_updated": True,
    }


def _pointer_after_failed_cas(
    store: StrictConditionalWriteStore, *, payload: bytes, cause: BaseException | None
) -> None:
    """Accept a lost CAS only when the pointer already carries our exact bytes."""
    observed = _read_versioned_pointer(store)
    if observed.data == payload:
        return
    if observed.data is not None:
        _decode_pointer(observed.data)
    error = DisclosureBundleError(
        "disclosure bundle latest pointer compare-and-swap conflict"
    )
    if cause is not None:
        raise error from cause
    raise error


def restore_disclosure_bundle(
    store: Store,
    *,
    output_root: Path,
    expected_tickers: Sequence[str],
    now: str,
    warn_age_days: float = 3.0,
    fail_age_days: float = 21.0,
) -> dict[str, Any]:
    """Restore every projection in the published bundle into ``output_root``.

    ``now`` is the consumer's explicit UTC clock — this module never samples
    one.  The bundle is validated wholly in memory (pointer binding, canonical
    encoding, identity, and exact ticker-set equality in both directions)
    before any local file is written.  A mid-loop filesystem failure can still
    leave a mixed generation on disk; the CLI exits nonzero and the engine's
    hard gate stops the job, so a torn set never reaches the broad build.
    """
    if not callable(getattr(store, "get_bytes_strict_bounded", None)):
        raise DisclosureBundleError(
            "disclosure bundle restore requires a StrictBoundedReadStore adapter"
        )
    for name, value in (("warn_age_days", warn_age_days), ("fail_age_days", fail_age_days)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise DisclosureBundleError(f"{name} must be a positive number")
    if warn_age_days > fail_age_days:
        raise DisclosureBundleError("warn_age_days cannot exceed fail_age_days")
    now_text = _normalized_clock(now, field="now")
    expected = sorted({_normalized_ticker(item) for item in expected_tickers})
    if not expected:
        raise DisclosureBundleError("at least one expected ticker is required")

    pointer_bytes = _read_bounded_optional(
        store, DISCLOSURE_BUNDLE_LATEST_KEY, maximum_bytes=HARD_MAX_POINTER_BYTES
    )
    if pointer_bytes is None:
        raise DisclosureBundleError("no published disclosure bundle")
    pointer = _decode_pointer(pointer_bytes)

    age_seconds = (
        _clock_datetime(now_text, field="now")
        - _clock_datetime(str(pointer["published_at"]), field="published_at")
    ).total_seconds()
    if age_seconds < -MAX_FUTURE_SKEW_SECONDS:
        raise DisclosureBundleError(
            "published disclosure bundle clock is in the future beyond tolerated skew"
        )
    age_days = age_seconds / 86400.0
    if age_days > fail_age_days:
        raise DisclosureBundleError(
            f"published disclosure bundle is {age_days:.1f} days old (limit {fail_age_days})"
        )

    content = _read_bounded_optional(
        store, str(pointer["bundle_key"]), maximum_bytes=HARD_MAX_BUNDLE_BYTES
    )
    if content is None:
        raise DisclosureBundleError(
            f"disclosure bundle pointer does not bind an object: {pointer['bundle_key']}"
        )
    bundle = _strict_json_object(content, label="disclosure bundle")
    validate_disclosure_bundle(bundle)
    if canonical_json(bundle).encode("utf-8") != content:
        raise DisclosureBundleError("disclosure bundle is not canonically encoded")
    if str(bundle["bundle_id"]) != str(pointer["bundle_id"]):
        raise DisclosureBundleError("disclosure bundle pointer does not bind this bundle")
    # The age gate above trusted the pointer's clock before the bundle was
    # readable; a rewritten pointer must not be able to freshen a stale bundle.
    if str(bundle["published_at"]) != str(pointer["published_at"]):
        raise DisclosureBundleError("disclosure bundle pointer clock does not match its bundle")

    present = sorted(str(item) for item in bundle["tickers"])
    if present != expected:
        missing = [item for item in expected if item not in present]
        extra = [item for item in present if item not in expected]
        raise DisclosureBundleError(
            "published disclosure bundle ticker set does not match the expected targets "
            f"(missing: {missing or 'none'}; unexpected: {extra or 'none'})"
        )

    root = Path(output_root)
    restored = 0
    for ticker in present:
        write_disclosure_projection(root, bundle["projections"][ticker])
        restored += 1
    return {
        "schema": DISCLOSURE_BUNDLE_RESTORE_SCHEMA,
        "bundle_id": str(bundle["bundle_id"]),
        "published_at": str(bundle["published_at"]),
        "tickers": present,
        "restored_files": restored,
        "stale_warning": age_days > warn_age_days,
    }


__all__ = [
    "DISCLOSURE_BUNDLE_LATEST_KEY",
    "DISCLOSURE_BUNDLE_LATEST_SCHEMA",
    "DISCLOSURE_BUNDLE_PREFIX",
    "DISCLOSURE_BUNDLE_PUBLISH_SCHEMA",
    "DISCLOSURE_BUNDLE_RESTORE_SCHEMA",
    "DISCLOSURE_BUNDLE_SCHEMA",
    "DisclosureBundleError",
    "HARD_MAX_BUNDLE_BYTES",
    "HARD_MAX_POINTER_BYTES",
    "MAX_FUTURE_SKEW_SECONDS",
    "build_disclosure_bundle",
    "bundle_object_key",
    "publish_disclosure_bundle",
    "restore_disclosure_bundle",
    "validate_disclosure_bundle",
]
