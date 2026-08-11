"""Build the coherent CPI proxy history and its preregistered parity cohort.

This is a fail-closed research builder.  It writes nothing unless both the
manifest-bound ALFRED history and parity against official BLS archived
release-edition observations pass.  The retrospective archive corpus is not
proof of first-published bytes or values.  The result remains display-only
candidate evidence; it never changes a Release Radar producer, model epoch,
champion, or combination layer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine.release_cpi_target_history import (
    CANDIDATE_TARGET_EPOCH,
    FIRST_PRINT_STATUS,
    OFFICIAL_ARCHIVE_OBSERVATION_EPOCH,
    WITHHELD_OFFICIAL_TARGET_EPOCH,
    CpiTargetHistoryError,
    build_cpi_target_history,
    default_collector_manifest_path,
    default_cpi_vintage_paths,
    evaluate_preregistered_parity,
)

DEFAULT_OFFICIAL_RECEIPTS = (
    Path("data") / "release_forecast" / "cpi_truth" / "official_table1_receipts.jsonl"
)
DEFAULT_PREREGISTERED_SAMPLE = (
    Path("data") / "release_forecast" / "cpi_truth" / "preregistered_sample.json"
)
DEFAULT_OFFICIAL_COLLECTION_MANIFEST = (
    Path("data") / "release_forecast" / "cpi_truth" / "official_table1_collection.json"
)
DEFAULT_HISTORY_OUTPUT = (
    Path("data")
    / "release_forecast"
    / "cpi_truth"
    / "alfred_same_release_vintage_proxy_v1.json"
)
DEFAULT_PARITY_OUTPUT = (
    Path("data") / "release_forecast" / "cpi_truth" / "parity_report.json"
)
DEFAULT_COMPLETION_OUTPUT = (
    Path("data") / "release_forecast" / "cpi_truth" / "build_completion.json"
)


def build_release_cpi_truth_parity(
    *,
    repo_root: str | Path = _REPO,
    vintage_paths: Mapping[str, str | Path] | None = None,
    collector_manifest_path: str | Path | None = None,
    official_receipts_path: str | Path | None = None,
    official_collection_manifest_path: str | Path | None = None,
    preregistered_sample_path: str | Path | None = None,
    history_output_path: str | Path | None = None,
    parity_output_path: str | Path | None = None,
    completion_output_path: str | Path | None = None,
    dry_run: bool = False,
    artifact_writer: Callable[[Path, bytes], None] | None = None,
) -> dict[str, Any]:
    """Build, gate, and optionally publish a deterministic artifact cohort.

    All source and destination paths are injectable for tests and controlled
    research runs.  Both payloads are computed before either destination is
    touched.  A failed history or parity check therefore preserves existing
    artifacts byte-for-byte.  Once both checks pass, any prior completion
    marker is invalidated before cohort replacement begins and is published
    again only after both new artifacts are durable.
    """

    root = Path(repo_root)
    resolved_vintages = (
        dict(vintage_paths)
        if vintage_paths is not None
        else default_cpi_vintage_paths(root)
    )
    manifest = (
        Path(collector_manifest_path)
        if collector_manifest_path
        else (default_collector_manifest_path(root))
    )
    official = _under_root(root, official_receipts_path, DEFAULT_OFFICIAL_RECEIPTS)
    official_collection = (
        Path(official_collection_manifest_path)
        if official_collection_manifest_path is not None
        else (
            official.with_name("official_table1_collection.json")
            if official_receipts_path is not None
            else root / DEFAULT_OFFICIAL_COLLECTION_MANIFEST
        )
    )
    preregistered = _under_root(
        root,
        preregistered_sample_path,
        DEFAULT_PREREGISTERED_SAMPLE,
    )
    history_output = _under_root(root, history_output_path, DEFAULT_HISTORY_OUTPUT)
    parity_output = _under_root(root, parity_output_path, DEFAULT_PARITY_OUTPUT)
    completion_output = _under_root(
        root,
        completion_output_path,
        DEFAULT_COMPLETION_OUTPUT,
    )
    if len({history_output, parity_output, completion_output}) != 3:
        raise CpiTargetHistoryError(
            "history, parity, and completion outputs must be different files"
        )

    history = build_cpi_target_history(
        repo_root=root,
        vintage_paths=resolved_vintages,
        manifest_path=manifest,
        preregistered_sample_path=preregistered,
    )
    parity = evaluate_preregistered_parity(
        history,
        official_receipts_path=official,
        preregistered_sample_path=preregistered,
        official_collection_manifest_path=official_collection,
        repo_root=root,
    )

    history_body = _canonical_artifact_bytes(history)
    parity_body = _canonical_artifact_bytes(parity)
    completion = {
        "schema": "release_cpi_truth_build_completion.v1",
        "status": "complete",
        "asof": parity["evidence_available_at"],
        "candidate_data_asof": history["candidate_data_asof"],
        "evidence_available_at": parity["evidence_available_at"],
        "candidate_target_epoch": CANDIDATE_TARGET_EPOCH,
        "official_archive_observation_epoch": {
            "name": OFFICIAL_ARCHIVE_OBSERVATION_EPOCH,
            "status": "bounded_preregistered_parity_passed",
            "first_print_status": FIRST_PRINT_STATUS,
            "first_publication_evidence_verified": False,
        },
        "official_target_epoch": {
            "name": WITHHELD_OFFICIAL_TARGET_EPOCH,
            "status": "withheld",
            "promotion_authorized": False,
            "reason": (
                "Retrospective official BLS archive editions do not establish "
                "first-published bytes or values"
            ),
        },
        "history_hash": history["history_hash"],
        "candidate_coverage": history["coverage"],
        "artifacts": {
            "history": {
                **_artifact_binding(root, history_output, history_body),
                "history_hash": history["history_hash"],
            },
            "parity": {
                **_artifact_binding(root, parity_output, parity_body),
                "history_hash": parity["history_hash"],
            },
        },
        "source_bindings": {
            "alfred_manifest": history["source_manifest"],
            "preregistered_sample": parity["preregistered_sample"],
            "official_receipts": parity["official_receipts"],
            "official_collection_manifest": parity["official_collection_manifest"],
        },
        "completion_boundary": True,
        "display_only": True,
        "authority": False,
    }
    completion_body = _canonical_artifact_bytes(completion)
    if not dry_run:
        writer = artifact_writer or _atomic_write
        _invalidate_completion(completion_output)
        writer(history_output, history_body)
        writer(parity_output, parity_body)
        # This is the cohort publication boundary.  Consumers must validate
        # both exact bindings above and ignore an incomplete pair.
        writer(completion_output, completion_body)

    return {
        "schema": "release_cpi_truth_parity_build.v1",
        "status": "dry_run_passed" if dry_run else "written",
        "asof": parity["evidence_available_at"],
        "candidate_data_asof": history["candidate_data_asof"],
        "evidence_available_at": parity["evidence_available_at"],
        "candidate_target_epoch": CANDIDATE_TARGET_EPOCH,
        "official_archive_observation_epoch": {
            "name": OFFICIAL_ARCHIVE_OBSERVATION_EPOCH,
            "status": "bounded_preregistered_parity_passed",
            "first_print_status": FIRST_PRINT_STATUS,
            "first_publication_evidence_verified": False,
        },
        "official_target_epoch": {
            "name": WITHHELD_OFFICIAL_TARGET_EPOCH,
            "status": "withheld",
            "promotion_authorized": False,
            "reason": (
                "Retrospective official BLS archive editions do not establish "
                "first-published bytes or values"
            ),
        },
        "n_targets": history["n_targets"],
        "n_cases": parity["n_cases"],
        "n_metric_comparisons": parity["n_metric_comparisons"],
        "outputs": {
            "history": {
                "path": _logical_output_path(root, history_output),
                "bytes": len(history_body),
                "written": not dry_run,
            },
            "parity": {
                "path": _logical_output_path(root, parity_output),
                "bytes": len(parity_body),
                "written": not dry_run,
            },
            "completion": {
                "path": _logical_output_path(root, completion_output),
                "bytes": len(completion_body),
                "written": not dry_run,
                "publication_boundary": True,
            },
        },
        "history": history,
        "parity": parity,
        "completion": completion,
        "display_only": True,
        "authority": False,
    }


def _under_root(
    root: Path,
    supplied: str | Path | None,
    default_relative: Path,
) -> Path:
    if supplied is None:
        return root / default_relative
    return Path(supplied)


def _canonical_artifact_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _artifact_binding(root: Path, path: Path, body: bytes) -> dict[str, Any]:
    return {
        "path": _logical_output_path(root, path),
        "artifact_sha256": hashlib.sha256(body).hexdigest(),
        "artifact_bytes": len(body),
    }


def _logical_output_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.",
        dir=path.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _invalidate_completion(path: Path) -> None:
    if not path.exists():
        return
    path.unlink()
    _fsync_directory(path.parent)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_REPO)
    parser.add_argument("--headline-vintages", type=Path)
    parser.add_argument("--core-vintages", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--official-receipts", type=Path)
    parser.add_argument("--official-collection-manifest", type=Path)
    parser.add_argument("--preregistered-sample", type=Path)
    parser.add_argument("--history-output", type=Path)
    parser.add_argument("--parity-output", type=Path)
    parser.add_argument("--completion-output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    vintage_paths = None
    if args.headline_vintages or args.core_vintages:
        if not args.headline_vintages or not args.core_vintages:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": (
                            "--headline-vintages and --core-vintages must be "
                            "supplied together"
                        ),
                    },
                    sort_keys=True,
                )
            )
            return 2
        vintage_paths = {
            "cpi_headline": args.headline_vintages,
            "cpi_core": args.core_vintages,
        }
    try:
        result = build_release_cpi_truth_parity(
            repo_root=args.root,
            vintage_paths=vintage_paths,
            collector_manifest_path=args.manifest,
            official_receipts_path=args.official_receipts,
            official_collection_manifest_path=args.official_collection_manifest,
            preregistered_sample_path=args.preregistered_sample,
            history_output_path=args.history_output,
            parity_output_path=args.parity_output,
            completion_output_path=args.completion_output,
            dry_run=args.dry_run,
        )
    except (CpiTargetHistoryError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error": f"{type(exc).__name__}: {exc}"},
                sort_keys=True,
            )
        )
        return 1

    summary = {
        key: value
        for key, value in result.items()
        if key not in {"history", "parity", "completion"}
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_COMPLETION_OUTPUT",
    "DEFAULT_HISTORY_OUTPUT",
    "DEFAULT_OFFICIAL_COLLECTION_MANIFEST",
    "DEFAULT_OFFICIAL_RECEIPTS",
    "DEFAULT_PARITY_OUTPUT",
    "DEFAULT_PREREGISTERED_SAMPLE",
    "build_release_cpi_truth_parity",
    "main",
]
