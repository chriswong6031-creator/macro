"""Materialize authenticated SEC Company Facts into observed share-count facts.

This production command is a bridge between two separately witnessed lanes. It
first recovers the last externally selected share-count generation, then reads
the authenticated Company Facts generation, strict-reads only the next bounded
raw-object batch, runs the pure v2 normalizer, and publishes one all-or-nothing
share-count generation.

It never calls SEC, reads the legacy EDGAR facts cache, chooses a current share
basis, estimates fully diluted shares, calculates financing capacity/risk, or
invokes Prophet.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
import json
import math
import time
from typing import Any

from collectors.sec_capital_structure_companyfacts import (
    CompanyFactsIntakeError,
    _build_production_trust_context,
)
from engine.capital_structure.companyfacts_authenticated_read import (
    CompanyFactsAuthenticatedSnapshot,
    load_authenticated_companyfacts_snapshot,
)
from engine.capital_structure.share_count_materializer import (
    MAX_SOURCE_BATCH,
    ShareCountMaterializerError,
    compile_authenticated_companyfacts_share_count_prefix,
    validate_share_count_ledger,
)
from engine.capital_structure.share_count_publication import (
    ShareCountPublicationError,
    ShareCountPublicationResult,
    _publish_share_count_materialization_with_production_trust,
    recover_share_count_materialization,
)
from engine.capital_structure.source_store import (
    ContentAddressedSourceStore,
    SourceStoreVerificationError,
    build_source_stores,
)


MAX_SOURCE_OBJECT_BYTES = 32 * 1024 * 1024
MAX_SOURCE_BATCH_BYTES = 256 * 1024 * 1024
INPUT_BINDING_SCHEMA = "capital_structure.share_count_materialization_input_binding/v1"
# Keep one bounded wall-clock envelope around the whole bridge.  The
# authenticated reader and publication lane each use the same 15-minute
# production-scale budget internally; this outer deadline prevents a sequence
# of individually-bounded phases from consuming that budget repeatedly.
MATERIALIZATION_TIMEOUT_SECONDS = 15.0 * 60.0


class ShareCountMaterializationRunError(RuntimeError):
    """The production bridge could not prove one complete materialization."""


def _new_run_deadline(
    *, max_run_seconds: float, monotonic: Callable[[], float],
) -> float:
    if (
        isinstance(max_run_seconds, bool)
        or not isinstance(max_run_seconds, (int, float))
        or not math.isfinite(max_run_seconds)
        or max_run_seconds <= 0
    ):
        raise ShareCountMaterializationRunError(
            "materialization run deadline must be a finite positive number",
        )
    return monotonic() + float(max_run_seconds)


def _require_run_deadline(
    deadline: float | None,
    monotonic: Callable[[], float],
    *,
    label: str,
) -> None:
    if deadline is not None and monotonic() >= deadline:
        raise ShareCountMaterializationRunError(
            f"share-count materialization deadline exceeded during {label}",
        )


def _remaining_run_seconds(
    deadline: float,
    monotonic: Callable[[], float],
    *,
    label: str,
) -> float:
    now = monotonic()
    if now >= deadline:
        raise ShareCountMaterializationRunError(
            f"share-count materialization deadline exceeded during {label}",
        )
    return deadline - now


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ShareCountMaterializationRunError("materialization clock must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _native(value: Any) -> Any:
    """Thaw recursively immutable reader values into canonical JSON data."""
    if isinstance(value, Mapping):
        return {str(key): _native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(item) for item in value]
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as exc:
        raise ShareCountMaterializationRunError(
            "share-count ledger is not canonical JSON data",
        ) from exc


def _decode_existing(result: ShareCountPublicationResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    raw = result.ledger_bytes
    if not isinstance(raw, bytes):
        raise ShareCountMaterializationRunError(
            "share-count recovery did not return exact ledger bytes",
        )
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShareCountMaterializationRunError(
            "recovered share-count ledger is not UTF-8 JSON",
        ) from exc
    if not isinstance(decoded, dict):
        raise ShareCountMaterializationRunError(
            "recovered share-count ledger root must be an object",
        )
    validate_share_count_ledger(decoded)
    receipt_binding = result.receipt.get("input_binding")
    if (
        not isinstance(receipt_binding, Mapping)
        or receipt_binding.get("ledger_head_receipt_id") != decoded["ledger_head_receipt_id"]
    ):
        raise ShareCountMaterializationRunError(
            "recovered publication receipt is detached from the inner ledger head",
        )
    return decoded


def _strict_raw_batch(
    manifests: Sequence[Mapping[str, Any]],
    stores: Mapping[str, ContentAddressedSourceStore],
    *,
    deadline: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> list[bytes]:
    _require_run_deadline(deadline, monotonic, label="strict raw Company Facts reads")
    if len(manifests) > MAX_SOURCE_BATCH:
        raise ShareCountMaterializationRunError("raw Company Facts batch exceeds hard count cap")
    total = 0
    raw_batch: list[bytes] = []
    for manifest in manifests:
        _require_run_deadline(deadline, monotonic, label="strict raw Company Facts reads")
        storage = manifest.get("storage")
        content = manifest.get("content")
        if not isinstance(storage, Mapping) or not isinstance(content, Mapping):
            raise ShareCountMaterializationRunError(
                "Company Facts manifest has no closed storage/content binding",
            )
        store_id = str(storage.get("store_id") or "")
        store = stores.get(store_id)
        if store is None:
            raise ShareCountMaterializationRunError(
                f"Company Facts source store is unavailable for {store_id!r}",
            )
        if store.backend != storage.get("backend") or store.store_id != store_id:
            raise ShareCountMaterializationRunError(
                "Company Facts source store backend/namespace is rebound",
            )
        expected_length = content.get("byte_length")
        if (
            isinstance(expected_length, bool)
            or not isinstance(expected_length, int)
            or not 1 <= expected_length <= MAX_SOURCE_OBJECT_BYTES
        ):
            raise ShareCountMaterializationRunError(
                "Company Facts source object exceeds the strict per-object bound",
            )
        total += expected_length
        if total > MAX_SOURCE_BATCH_BYTES:
            raise ShareCountMaterializationRunError(
                "Company Facts source batch exceeds the aggregate byte bound",
            )
        _require_run_deadline(deadline, monotonic, label="strict raw Company Facts reads")
        raw = store.get_verified_strict_bounded(
            str(storage.get("object_key") or ""),
            str(content.get("content_sha256") or ""),
            expected_byte_length=expected_length,
            max_byte_length=MAX_SOURCE_OBJECT_BYTES,
        )
        # Source-store APIs retain their own bounded transport behavior but do
        # not accept this run deadline.  A post-call check is therefore the
        # strongest fail-closed boundary Python can enforce without pretending
        # to cancel an in-flight backend read.
        _require_run_deadline(deadline, monotonic, label="strict raw Company Facts reads")
        if raw is None:
            raise ShareCountMaterializationRunError(
                "Company Facts retained source object is missing",
            )
        raw_batch.append(raw)
    return raw_batch


def _input_binding(ledger: Mapping[str, Any]) -> dict[str, Any]:
    receipts = ledger.get("ledger_receipts")
    if not isinstance(receipts, list) or not receipts or not isinstance(receipts[-1], Mapping):
        raise ShareCountMaterializationRunError("share-count ledger has no tail receipt")
    tail = receipts[-1]
    binding = {
        "schema": INPUT_BINDING_SCHEMA,
        "ledger_head_receipt_id": ledger.get("ledger_head_receipt_id"),
        "ledger_sequence": tail.get("sequence"),
        "compiler_version": ledger.get("compiler_version"),
        "materialized_at": ledger.get("materialized_at"),
        "prefixes": _native(tail.get("prefixes")),
    }
    return binding


def _materialize_authenticated_snapshot(
    *,
    snapshot: CompanyFactsAuthenticatedSnapshot,
    current: ShareCountPublicationResult | None,
    stores: Mapping[str, ContentAddressedSourceStore],
    coverage_receipt_verifier: Any,
    now_fn: Callable[[], datetime],
    publisher: Callable[..., ShareCountPublicationResult],
    deadline: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> ShareCountPublicationResult | None:
    _require_run_deadline(deadline, monotonic, label="authenticated snapshot materialization")
    manifests = [_native(record) for record in snapshot.manifests]
    _require_run_deadline(deadline, monotonic, label="authenticated snapshot materialization")
    _require_run_deadline(deadline, monotonic, label="recovered ledger validation")
    existing = _decode_existing(current)
    _require_run_deadline(deadline, monotonic, label="recovered ledger validation")
    _require_run_deadline(deadline, monotonic, label="authenticated snapshot prefix validation")
    consumed = len(existing["source_snapshots"]) if existing is not None else 0
    if consumed > len(manifests):
        raise ShareCountMaterializationRunError(
            "share-count history is longer than the authenticated Company Facts prefix",
        )
    if existing is not None:
        prior_ids = [row["source_manifest_id"] for row in existing["source_snapshots"]]
        current_prefix = [row.get("manifest_id") for row in manifests[:consumed]]
        if prior_ids != current_prefix:
            raise ShareCountMaterializationRunError(
                "authenticated Company Facts prefix no longer extends share-count history",
            )
    _require_run_deadline(deadline, monotonic, label="authenticated snapshot prefix validation")

    batch_manifests = manifests[consumed:consumed + MAX_SOURCE_BATCH]
    if not batch_manifests and existing is None:
        # The authenticated intake can legitimately have a signed coverage receipt
        # before it has retained one source snapshot. Absence is not an empty green
        # share ledger and does not warrant a new share-count head.
        _require_run_deadline(deadline, monotonic, label="authenticated snapshot prefix validation")
        return None

    if batch_manifests:
        raw_batch = _strict_raw_batch(
            batch_manifests,
            stores,
            deadline=deadline,
            monotonic=monotonic,
        )
        _require_run_deadline(deadline, monotonic, label="strict raw Company Facts reads")
        materialized_at = _iso(now_fn())
        _require_run_deadline(deadline, monotonic, label="share-count model compilation")
        ledger = compile_authenticated_companyfacts_share_count_prefix(
            manifests,
            raw_batch,
            _native(snapshot.selected_coverage_receipt_record),
            coverage_receipt_bytes=snapshot.selected_coverage_receipt_bytes,
            coverage_receipt_verifier=coverage_receipt_verifier,
            materialized_at=materialized_at,
            existing_ledger=existing,
            expected_existing_ledger_head_receipt_id=(
                existing["ledger_head_receipt_id"] if existing is not None else None
            ),
        )
        _require_run_deadline(deadline, monotonic, label="share-count model compilation")
    else:
        assert existing is not None
        ledger = existing

    _require_run_deadline(deadline, monotonic, label="share-count ledger validation")
    validate_share_count_ledger(ledger)
    _require_run_deadline(deadline, monotonic, label="share-count ledger validation")
    _require_run_deadline(deadline, monotonic, label="publication payload construction")
    canonical_ledger_bytes = _canonical_bytes(ledger)
    input_binding = _input_binding(ledger)
    _require_run_deadline(deadline, monotonic, label="publication payload construction")
    _require_run_deadline(deadline, monotonic, label="share-count publication")
    result = publisher(
        canonical_ledger_bytes=canonical_ledger_bytes,
        input_binding=input_binding,
    )
    # Test seams may not support a deadline argument.  Production receives the
    # remaining budget through the wrapper in _run; if any publisher returns
    # after this run budget, do not report success. Recovery on the next run
    # remains the authority for any publication that completed before Python
    # regained control.
    _require_run_deadline(deadline, monotonic, label="share-count publication")
    return result


def _run(
    *,
    max_run_seconds: float = MATERIALIZATION_TIMEOUT_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
) -> ShareCountPublicationResult | None:
    """Run the closed production lane under one monotonic deadline.

    Recovery, the authenticated snapshot reader, and the closed publisher
    receive the exact remaining time from this single deadline. Trust and
    source-store construction expose only their own bounded behavior, so this
    orchestrator checks immediately before and after those phases rather than
    claiming it can interrupt them.
    """
    deadline = _new_run_deadline(max_run_seconds=max_run_seconds, monotonic=monotonic)
    # Recover and authenticate the independent share-count head before opening
    # upstream evidence or any retained source object.
    _require_run_deadline(deadline, monotonic, label="share-count recovery")
    current = recover_share_count_materialization(
        max_operation_seconds=_remaining_run_seconds(
            deadline,
            monotonic,
            label="share-count recovery",
        ),
    )
    _require_run_deadline(deadline, monotonic, label="share-count recovery")
    _require_run_deadline(deadline, monotonic, label="authenticated snapshot load")
    snapshot = load_authenticated_companyfacts_snapshot(
        max_read_seconds=_remaining_run_seconds(
            deadline,
            monotonic,
            label="authenticated snapshot load",
        ),
    )
    _require_run_deadline(deadline, monotonic, label="authenticated snapshot load")
    _require_run_deadline(deadline, monotonic, label="production trust construction")
    signer, _head_guard = _build_production_trust_context()
    _require_run_deadline(deadline, monotonic, label="production trust construction")
    _require_run_deadline(deadline, monotonic, label="source-store construction")
    stores = build_source_stores()
    _require_run_deadline(deadline, monotonic, label="source-store construction")

    def publisher_with_remaining_budget(
        *, canonical_ledger_bytes: bytes, input_binding: Mapping[str, Any],
    ) -> ShareCountPublicationResult:
        return _publish_share_count_materialization_with_production_trust(
            canonical_ledger_bytes=canonical_ledger_bytes,
            input_binding=input_binding,
            max_operation_seconds=_remaining_run_seconds(
                deadline,
                monotonic,
                label="share-count publication",
            ),
        )

    return _materialize_authenticated_snapshot(
        snapshot=snapshot,
        current=current,
        stores=stores,
        coverage_receipt_verifier=signer,
        now_fn=_utc_now,
        publisher=publisher_with_remaining_budget,
        deadline=deadline,
        monotonic=monotonic,
    )


def run() -> ShareCountPublicationResult | None:
    """Run the production lane with environment-backed trust only."""
    return _run()


def main() -> int:
    try:
        result = run()
    except (
        CompanyFactsIntakeError,
        ShareCountMaterializerError,
        ShareCountPublicationError,
        ShareCountMaterializationRunError,
        SourceStoreVerificationError,
        OSError,
        ValueError,
    ) as exc:
        print(f"::error title=capital-structure-share-count-materializer::{type(exc).__name__}: {exc}")
        return 2
    if result is None:
        print(
            "::notice title=capital-structure-share-count-materializer::"
            "authenticated Company Facts has no retained source snapshots; "
            "share-count state remains unavailable",
        )
        return 0
    action = "recovered" if result.recovered else "published" if result.published else "verified-noop"
    print(
        "capital-structure share-count materialization "
        f"{action}: receipt={result.receipt_id} generation={result.generation_id} "
        f"sequence={result.sequence}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
