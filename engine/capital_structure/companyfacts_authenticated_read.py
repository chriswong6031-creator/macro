"""Authenticated, metadata-only reads of the selected Company Facts generation.

This is intentionally a read facade, not a Company Facts interpretation or
source-object access API.  It authenticates the externally witnessed selected
receipt before exposing the immutable manifest and coverage metadata.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import math
from pathlib import Path
from types import MappingProxyType
import time
from typing import Any, Callable

import collectors.sec_capital_structure_companyfacts as _companyfacts


_ANCHOR_COLUMNS = [
    "schema", "manifest_id", "source_system", "source_id", "issuer", "filing", "document",
    "retrieval", "storage", "rights", "privacy", "parser", "spans",
]


@dataclass(frozen=True)
class CompanyFactsSelectedCoverageReceipt:
    """Identity and exact ordered-prefix commitments of the selected receipt."""

    receipt_id: str
    receipt_path: str
    receipt_sha256: str
    receipt_byte_length: int
    generation_id: str
    sequence: int
    published_at: str
    source_manifest_descriptor: Mapping[str, Any]
    coverage_descriptor: Mapping[str, Any]
    manifest_prefix: Mapping[str, Any]
    coverage_prefix: Mapping[str, Any]


@dataclass(frozen=True)
class CompanyFactsAuthenticatedSnapshot:
    """An immutable, authenticated selection with no Company Facts raw bytes."""

    manifests: tuple[Mapping[str, Any], ...]
    coverage_rows: tuple[Mapping[str, Any], ...]
    selected_coverage_receipt: CompanyFactsSelectedCoverageReceipt
    selected_coverage_receipt_record: Mapping[str, Any]
    selected_coverage_receipt_bytes: bytes
    observed_head: Mapping[str, Any]


def _freeze(value: Any) -> Any:
    """Deep-copy data-plane records into recursively immutable API values."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return deepcopy(value)


def _resolve_trust(
    *, signer: _companyfacts.CompanyFactsSigner | None,
    head_guard: _companyfacts.CompanyFactsHeadGuard | None,
) -> tuple[_companyfacts.CompanyFactsSigner, _companyfacts.CompanyFactsHeadGuard]:
    if (signer is None) != (head_guard is None):
        raise _companyfacts.CompanyFactsIntakeError(
            "Company Facts authenticated read requires signer and head_guard together"
        )
    if signer is not None and head_guard is not None:
        return signer, head_guard
    return _companyfacts._build_production_trust_context()


def _read_anchor_records(
    root: Path, *, lane: Any, deadline: float, monotonic: Callable[[], float],
) -> list[dict[str, Any]]:
    records = _companyfacts._read_source_manifest_ledger(
        root.parent / _companyfacts.SOURCE_LEDGER_FILENAME, _ANCHOR_COLUMNS,
        max_bytes=_companyfacts.MAX_ANCHOR_LEDGER_BYTES, parent_fd=lane.parent_fd,
        deadline=deadline, monotonic=monotonic,
    )
    _companyfacts._require_deadline(
        deadline, monotonic, label="filing anchor ledger decode",
    )
    return records


def _injected_anchor_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise _companyfacts.CompanyFactsIntakeError(
                "Company Facts authenticated read anchors must be mappings"
            )
        native = _companyfacts._native(record)
        if not isinstance(native, Mapping):
            raise _companyfacts.CompanyFactsIntakeError(
                "Company Facts authenticated read anchor is malformed"
            )
        normalized.append(dict(native))
    return normalized


def _read_deadline(
    *, max_read_seconds: float, monotonic: Callable[[], float],
) -> float:
    if (
        isinstance(max_read_seconds, bool)
        or not isinstance(max_read_seconds, (int, float))
        or not math.isfinite(max_read_seconds)
        or not 0 < float(max_read_seconds) <= _companyfacts.HARD_MAX_RUN_SECONDS
    ):
        raise ValueError(
            "max_read_seconds must be finite, greater than 0, and at most "
            f"{_companyfacts.HARD_MAX_RUN_SECONDS}"
        )
    return monotonic() + float(max_read_seconds)


def load_authenticated_companyfacts_snapshot(
    *,
    max_read_seconds: float = _companyfacts.MAX_RUN_SECONDS,
) -> CompanyFactsAuthenticatedSnapshot:
    """Load the production Company Facts selection using environment-backed trust."""
    return _load_authenticated_companyfacts_snapshot(
        max_read_seconds=max_read_seconds,
    )


def _load_authenticated_companyfacts_snapshot(
    *,
    root: Path | None = None,
    anchor_records: Sequence[Mapping[str, Any]] | None = None,
    signer: _companyfacts.CompanyFactsSigner | None = None,
    head_guard: _companyfacts.CompanyFactsHeadGuard | None = None,
    max_read_seconds: float = _companyfacts.MAX_RUN_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> CompanyFactsAuthenticatedSnapshot:
    """Injected test seam for the production authenticated-read implementation.

    This helper never resolves a Company Facts source store and never performs
    an SEC HTTP request. It remains private so callers cannot redirect the
    production trust or filesystem boundary.
    """
    deadline = _read_deadline(max_read_seconds=max_read_seconds, monotonic=monotonic)
    safe_root = Path(root) if root is not None else _companyfacts._data_root()
    signer, head_guard = _resolve_trust(signer=signer, head_guard=head_guard)
    _companyfacts._require_deadline(
        deadline, monotonic, label="authenticated read trust construction",
    )

    with _companyfacts.open_companyfacts_authenticated_read_lane(
        safe_root, deadline=deadline, monotonic=monotonic, sleeper=sleeper,
    ) as lane:
        observed_head, observed_token = _companyfacts._read_head_before_deadline(
            head_guard, deadline=deadline, monotonic=monotonic,
        )
        if observed_head is None:
            raise _companyfacts.CompanyFactsIntakeError(
                "Company Facts authenticated read requires an external authenticated head witness"
            )
        _companyfacts._validate_head_witness(observed_head, signer=signer)

        initial_pointer_snapshot = _companyfacts.read_companyfacts_authenticated_current_pointer_snapshot(
            safe_root, lane=lane, deadline=deadline, monotonic=monotonic,
        )
        if initial_pointer_snapshot is None:
            raise _companyfacts.CompanyFactsIntakeError(
                "Company Facts authenticated read requires a current pointer"
            )
        initial_pointer, initial_pointer_fingerprint = initial_pointer_snapshot
        anchors = (
            _injected_anchor_records(anchor_records)
            if anchor_records is not None
            else _read_anchor_records(
                safe_root, lane=lane, deadline=deadline, monotonic=monotonic,
            )
        )
        _companyfacts._require_deadline(
            deadline, monotonic, label="authenticated read anchor materialization",
        )
        manifests, coverage_rows, receipt = _companyfacts._load_committed_bundle(
            root=safe_root,
            receipt_path=safe_root / "coverage_receipt.json",
            anchor_records=anchors,
            signer=signer,
            head_witness=observed_head,
            lane=lane,
            deadline=deadline,
            monotonic=monotonic,
        )
        if receipt is None:
            raise _companyfacts.CompanyFactsIntakeError(
                "Company Facts authenticated read found no selected immutable receipt"
            )
        _companyfacts._require_deadline(
            deadline, monotonic, label="authenticated receipt-chain decode",
        )
        receipt_bytes = _companyfacts._canonical_bytes(receipt) + b"\n"
        if _companyfacts._bytes_receipt(receipt_bytes) != {
            "sha256": observed_head["receipt_sha256"],
            "byte_length": observed_head["receipt_byte_length"],
        }:
            raise _companyfacts.CompanyFactsIntakeError(
                "Company Facts selected receipt canonical bytes are detached from the witnessed head"
            )

        # The local lease serializes cooperative publishers.  These checks also
        # reject a remote head advance or an uncooperative pointer rewrite while
        # the immutable chain was being authenticated.
        final_pointer_snapshot = _companyfacts.read_companyfacts_authenticated_current_pointer_snapshot(
            safe_root, lane=lane, deadline=deadline, monotonic=monotonic,
        )
        final_head, final_token = _companyfacts._read_head_before_deadline(
            head_guard, deadline=deadline, monotonic=monotonic,
        )
        if final_head is None:
            raise _companyfacts.CompanyFactsIntakeError(
                "Company Facts external authenticated head disappeared during read"
            )
        _companyfacts._validate_head_witness(final_head, signer=signer)
        if (
            final_pointer_snapshot is None
            or final_pointer_snapshot[0] != initial_pointer
            or final_pointer_snapshot[1] != initial_pointer_fingerprint
        ):
            raise _companyfacts.CompanyFactsIntakeError(
                "Company Facts current pointer changed during authenticated read"
            )
        if final_head != observed_head or final_token != observed_token:
            raise _companyfacts.CompanyFactsIntakeError(
                "Company Facts external authenticated head changed during read"
            )
        _companyfacts._assert_lane_path_identity(lane)
        _companyfacts._require_deadline(
            deadline, monotonic, label="authenticated read final verification",
        )

    _companyfacts._require_deadline(
        deadline, monotonic, label="authenticated read lease release",
    )
    selected = CompanyFactsSelectedCoverageReceipt(
        receipt_id=str(receipt["receipt_id"]),
        receipt_path="receipts/" + str(receipt["receipt_id"]).rsplit(":", 1)[-1] + ".json",
        receipt_sha256=str(observed_head["receipt_sha256"]),
        receipt_byte_length=int(observed_head["receipt_byte_length"]),
        generation_id=str(receipt["generation"]["generation_id"]),
        sequence=int(receipt["sequence"]),
        published_at=str(receipt["published_at"]),
        source_manifest_descriptor=_freeze(receipt["generation"]["source_manifest"]),
        coverage_descriptor=_freeze(receipt["generation"]["coverage"]),
        manifest_prefix=_freeze(receipt["companyfacts_manifest_ledger"]),
        coverage_prefix=_freeze(receipt["coverage_ledger"]),
    )
    snapshot = CompanyFactsAuthenticatedSnapshot(
        manifests=tuple(_freeze(record) for record in manifests),
        coverage_rows=tuple(_freeze(record) for record in coverage_rows),
        selected_coverage_receipt=selected,
        selected_coverage_receipt_record=_freeze(receipt),
        selected_coverage_receipt_bytes=bytes(receipt_bytes),
        observed_head=_freeze(observed_head),
    )
    _companyfacts._require_deadline(
        deadline, monotonic, label="authenticated read result materialization",
    )
    return snapshot


__all__ = [
    "CompanyFactsAuthenticatedSnapshot",
    "CompanyFactsSelectedCoverageReceipt",
    "load_authenticated_companyfacts_snapshot",
]
