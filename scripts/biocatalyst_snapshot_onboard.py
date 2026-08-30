"""Onboard the authorized finite BioPharmCatalyst JV snapshot.

The default command is a read-only deterministic check.  ``--publish-private``
uses only the existing dedicated BioCatalyst R2 credentials; it never enables a
live BPC producer or changes the CT.gov source registry.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.biocatalyst.historical_events import HistoricalEventError, HistoricalEventPublisher
from engine.biocatalyst.jv_snapshot import (
    AUTHORIZED_INPUTS,
    AdmittedInput,
    SnapshotError,
    admit_files,
    build_snapshot_manifest,
    canonical_json_bytes,
    identity_resolver_from_parquet_bytes,
    normalize_corpus,
)

from engine.biocatalyst.storage import (
    BinaryObjectStore,
    DedicatedR2Config,
    DedicatedR2Store,
    MirrorReceipt,
    StorageError,
    mirror_bytes_verified,
)


_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True, slots=True)
class OnboardArtifacts:
    admitted: tuple[AdmittedInput, ...]
    manifest: dict[str, object]
    manifest_bytes: bytes
    normalized_bytes: bytes
    events: tuple[dict[str, object], ...]
    coverage: dict[str, object]


def _iso_datetime(value: str, *, code: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SnapshotError(code) from None
    if parsed.tzinfo is None:
        raise SnapshotError(code)
    return parsed.isoformat().replace("+00:00", "Z")


def _csv_rows(payload: bytes) -> int:
    # Admission pins the exact bytes. Counting non-empty physical records is
    # sufficient for inventory-only coverage and never exposes their content.
    import csv  # noqa: PLC0415
    from io import StringIO  # noqa: PLC0415

    try:
        rows = list(csv.reader(StringIO(payload.decode("utf-8-sig", errors="strict"))))
    except Exception:
        raise SnapshotError("AUTHORIZED_CSV_INVALID") from None
    return max(0, sum(1 for row in rows if any(cell.strip() for cell in row)) - 1)


def _family_manifest(artifacts: Mapping[str, bytes], corpus: object) -> list[dict[str, object]]:
    coverage = corpus.coverage
    family_source_rows = coverage["family_source_rows"]
    family_counts = coverage["families"]
    repair = corpus.historical_fda_repair
    return [
        {
            "family": "historical_fda",
            "source_rows": family_source_rows["historical_fda"],
            "normalized_rows": family_counts.get("historical_fda", 0),
            "repaired_rows": repair.repaired_count,
            "publication_state": "projected",
        },
        {
            "family": "device_history",
            "source_rows": family_source_rows["device_history"],
            "normalized_rows": family_counts.get("device_history", 0),
            "repaired_rows": 0,
            "publication_state": "projected",
        },
        {
            "family": "device_pipeline_history",
            "source_rows": family_source_rows["device_pipeline_history"],
            "normalized_rows": family_counts.get("device_pipeline_history", 0),
            "repaired_rows": 0,
            "publication_state": "projected",
        },
        {
            "family": "all_companies",
            "source_rows": _csv_rows(artifacts["all_companies"]),
            "normalized_rows": 0,
            "repaired_rows": 0,
            "publication_state": "reconciliation_only",
        },
        {
            "family": "mergers_acquisitions",
            "source_rows": _csv_rows(artifacts["mergers_acquisitions"]),
            "normalized_rows": 0,
            "repaired_rows": 0,
            "publication_state": "inventory_only",
        },
        {
            "family": "hedge_funds",
            "source_rows": _csv_rows(artifacts["hedge_funds"]),
            "normalized_rows": 0,
            "repaired_rows": 0,
            "publication_state": "inventory_only",
        },
    ]


def build_onboard_artifacts(
    admitted: Sequence[AdmittedInput],
    *,
    security_master: bytes,
    vendor_aliases: bytes,
    observed_at: str,
    source_published_at: str | None = None,
    expected_fda_rows: int | None = 15_700,
    expected_fda_shifted: int | None = 4_404,
) -> OnboardArtifacts:
    """Build the closed private/public artifacts without writing anywhere."""

    observed_at = _iso_datetime(observed_at, code="CAPTURE_CLOCK_INVALID")
    if source_published_at is not None:
        source_published_at = _iso_datetime(source_published_at, code="SOURCE_PUBLICATION_CLOCK_INVALID")
    by_id = {item.spec.input_id: item.data for item in admitted}
    if set(by_id) != set(AUTHORIZED_INPUTS):
        raise SnapshotError("AUTHORIZED_INPUT_SET_INVALID")
    resolver = identity_resolver_from_parquet_bytes(security_master, vendor_aliases)
    corpus = normalize_corpus(
        by_id["workbook_w4"],
        by_id["historical_fda"],
        observed_at=observed_at,
        source_published_at=source_published_at,
        expected_fda_rows=expected_fda_rows,
        expected_fda_shifted=expected_fda_shifted,
        identity_resolver=resolver,
    )
    manifest = build_snapshot_manifest(
        admitted,
        families=_family_manifest(by_id, corpus),
        observed_at=observed_at,
        source_published_at=source_published_at,
    )
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"
    return OnboardArtifacts(
        admitted=tuple(admitted),
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        normalized_bytes=corpus.jsonl,
        events=corpus.events,
        coverage=corpus.coverage,
    )


def safe_summary(
    artifacts: OnboardArtifacts,
    *,
    mode: str,
    projection_generation: str | None = None,
    private_receipts: int = 0,
) -> dict[str, object]:
    return {
        "status": "ok",
        "mode": mode,
        "source_id": "biopharmcatalyst_jv_snapshot",
        "license_class": "licensed_finite_snapshot",
        "manifest_sha256": artifacts.manifest["manifest_sha256"],
        "normalized_sha256": sha256(artifacts.normalized_bytes).hexdigest(),
        "normalized_byte_count": len(artifacts.normalized_bytes),
        "coverage": artifacts.coverage,
        "projection_generation": projection_generation,
        "private_artifacts_verified": private_receipts,
        "raw_payload_emitted": False,
    }


def private_object_keys(
    *,
    raw_inputs: Mapping[str, tuple[str, bytes]],
    manifest: bytes,
    normalized: bytes,
) -> dict[str, str]:
    keys: dict[str, str] = {}
    for input_id, (safe_name, payload) in sorted(raw_inputs.items()):
        if not _SAFE_NAME.fullmatch(safe_name):
            raise ValueError("UNSAFE_INPUT_NAME")
        digest = sha256(payload).hexdigest()
        keys[input_id] = f"biopharmcatalyst_jv_snapshot/raw/{digest}/{safe_name}"
    manifest_digest = sha256(manifest).hexdigest()
    normalized_digest = sha256(normalized).hexdigest()
    keys["manifest"] = f"biopharmcatalyst_jv_snapshot/manifests/{manifest_digest}.json"
    keys["normalized"] = f"biopharmcatalyst_jv_snapshot/normalized/{normalized_digest}/events.jsonl"
    return keys


def publish_private_artifacts(
    store: BinaryObjectStore,
    *,
    raw_inputs: Mapping[str, tuple[str, bytes]],
    manifest: bytes,
    normalized: bytes,
) -> tuple[MirrorReceipt, ...]:
    keys = private_object_keys(raw_inputs=raw_inputs, manifest=manifest, normalized=normalized)
    receipts: list[MirrorReceipt] = []
    for input_id, (_safe_name, payload) in sorted(raw_inputs.items()):
        receipts.append(
            mirror_bytes_verified(store, object_key=keys[input_id], payload=payload)
        )
    receipts.append(
        mirror_bytes_verified(
            store,
            object_key=keys["manifest"],
            payload=manifest,
            content_type="application/json",
        )
    )
    receipts.append(
        mirror_bytes_verified(
            store,
            object_key=keys["normalized"],
            payload=normalized,
            content_type="application/x-ndjson",
        )
    )
    return tuple(receipts)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--all-companies", type=Path, required=True)
    parser.add_argument("--historical-fda", type=Path, required=True)
    parser.add_argument("--mergers-acquisitions", type=Path, required=True)
    parser.add_argument("--hedge-funds", type=Path, required=True)
    parser.add_argument("--security-master", type=Path, required=True)
    parser.add_argument("--vendor-aliases", type=Path, required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--source-published-at")
    parser.add_argument("--publish-private", action="store_true")
    parser.add_argument("--publish-public", action="store_true")
    parser.add_argument("--public-root", type=Path)
    parser.add_argument("--projection-published-at")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.publish_public and (args.public_root is None or args.projection_published_at is None):
            raise SnapshotError("PUBLIC_PROJECTION_ARGUMENTS_REQUIRED")
        if not args.publish_public and (args.public_root is not None or args.projection_published_at is not None):
            raise SnapshotError("PUBLIC_PROJECTION_NOT_ARMED")
        paths = {
            "workbook_w4": args.workbook,
            "all_companies": args.all_companies,
            "historical_fda": args.historical_fda,
            "mergers_acquisitions": args.mergers_acquisitions,
            "hedge_funds": args.hedge_funds,
        }
        admitted = admit_files(paths)
        artifacts = build_onboard_artifacts(
            admitted,
            security_master=args.security_master.read_bytes(),
            vendor_aliases=args.vendor_aliases.read_bytes(),
            observed_at=args.observed_at,
            source_published_at=args.source_published_at,
        )
        receipts: tuple[MirrorReceipt, ...] = ()
        if args.publish_private:
            store = DedicatedR2Store(DedicatedR2Config.from_environment(os.environ))
            receipts = publish_private_artifacts(
                store,
                raw_inputs={item.spec.input_id: (item.spec.safe_name, item.data) for item in artifacts.admitted},
                manifest=artifacts.manifest_bytes,
                normalized=artifacts.normalized_bytes,
            )
        generation = None
        if args.publish_public:
            published_at = _iso_datetime(args.projection_published_at, code="PROJECTION_PUBLICATION_CLOCK_INVALID")
            projection = HistoricalEventPublisher(args.public_root).publish(
                artifacts.events,
                coverage=artifacts.coverage,
                capture_observed_at=str(artifacts.manifest["capture"]["observed_at"]),
                published_at=published_at,
            )
            generation = projection.generation_id
        mode = "check"
        if args.publish_private and args.publish_public:
            mode = "publish_private_and_public"
        elif args.publish_private:
            mode = "publish_private"
        elif args.publish_public:
            mode = "publish_public"
        print(json.dumps(safe_summary(artifacts, mode=mode, projection_generation=generation, private_receipts=len(receipts)), sort_keys=True))
        return 0
    except (OSError, SnapshotError, HistoricalEventError, StorageError) as exc:
        code = exc.code if isinstance(exc, (SnapshotError, HistoricalEventError, StorageError)) else "INPUT_READ_FAILED"
        print(json.dumps({"status": "error", "code": code}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
