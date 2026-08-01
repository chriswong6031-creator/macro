"""Build the public-safe Capital Structure observed-filing-state projection.

This writer is offline and fail-closed.  It first repairs an interrupted prior
twin publication when at least one valid copy survives, then verifies the event
compiler's telemetry-last generation receipt and publishes one canonical JSON
artifact plus one byte-identical static-site twin.  Each target replacement is
atomic; a later invocation heals a process-stop gap between the two replaces.
It never reads raw SEC objects and never performs network I/O.

Usage:
    python -m scripts.build_capital_structure_projection
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import pandas as pd

from engine.capital_structure.projection import (
    build_projection_bundle,
    validate_projection_bundle,
)
from scripts.compile_capital_structure_events import (
    EDGE_COLUMNS,
    REVIEW_COLUMNS,
    _load_contract,
    _load_existing_edges,
    _load_existing_events,
    _validate_committed_generation,
    dataframe_records,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _data_root() -> Path:
    from lib import config

    return config.data_dir() / "capital_structure"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable JSON object: {path}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON root must be an object: {path}")
    return dict(value)


def _validate_review_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.columns.tolist() != REVIEW_COLUMNS:
        raise ValueError(
            "review queue columns must exactly equal "
            f"{REVIEW_COLUMNS}; got {frame.columns.tolist()}"
        )
    rows = dataframe_records(frame)
    schema = _load_contract("review")
    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for index, row in enumerate(rows):
        errors = list(validator.iter_errors(row))
        if errors:
            raise ValueError(
                f"review queue row {index} violates its contract: {errors[0].message}"
            )
    return rows


def _validated_projection_bytes(path: Path) -> bytes | None:
    """Return a valid existing projection payload, or None when absent.

    Invalid existing output is intentionally an error rather than an empty
    state. Recovery may use the other valid twin, but cannot silently bless
    malformed bytes as the last-good publication.
    """
    if not path.exists():
        return None
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid existing projection JSON: {path}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"existing projection root must be an object: {path}")
    validate_projection_bundle(dict(value))
    return payload


def _atomic_write_one(payload: bytes, target: Path) -> None:
    """Replace one target atomically using a same-directory staged file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    staged = Path(staged_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, target)
    finally:
        if staged.exists():
            staged.unlink()


def _recover_projection_pair(canonical_path: Path, public_path: Path) -> bool:
    """Heal an interrupted pair publish from whichever valid copy survives.

    The canonical copy wins when two individually valid payloads differ because
    normal promotion always replaces it first. Thus a hard stop between target
    replaces is repaired deterministically on the next invocation. Returns
    True when a repair was made.
    """
    if canonical_path.resolve() == public_path.resolve():
        raise ValueError("canonical and public projection paths must be distinct")

    canonical_error: ValueError | None = None
    public_error: ValueError | None = None
    try:
        canonical = _validated_projection_bytes(canonical_path)
    except ValueError as exc:
        canonical = None
        canonical_error = exc
    try:
        public = _validated_projection_bytes(public_path)
    except ValueError as exc:
        public = None
        public_error = exc

    if canonical is None and public is None:
        if canonical_error is not None or public_error is not None:
            errors = "; ".join(
                str(error)
                for error in (canonical_error, public_error)
                if error is not None
            )
            raise ValueError(
                "capital-structure projection pair has no valid recovery copy: "
                + errors
            )
        return False
    if canonical is not None:
        if public != canonical:
            _atomic_write_one(canonical, public_path)
            return True
        return False

    assert public is not None
    _atomic_write_one(public, canonical_path)
    return True


def _promote_pair(payload: bytes, canonical_path: Path, public_path: Path) -> None:
    """Promote independently atomic files with ordinary-exception rollback.

    A process stop cannot be caught between replaces; startup recovery closes
    that gap on the next invocation. Do not describe the pair itself as one
    atomic filesystem transaction.
    """
    targets = [canonical_path, public_path]
    if canonical_path.resolve() == public_path.resolve():
        raise ValueError("canonical and public projection paths must be distinct")
    staged: list[Path] = []
    backups: list[Path] = []
    promoted: list[tuple[Path, Path | None]] = []
    try:
        for index, target in enumerate(targets):
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, staged_name = tempfile.mkstemp(
                prefix=f".{target.name}.publish-{index}.",
                suffix=".tmp",
                dir=target.parent,
            )
            source = Path(staged_name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            staged.append(source)

        for index, (source, target) in enumerate(zip(staged, targets, strict=True)):
            backup: Path | None = None
            if target.exists():
                descriptor, backup_name = tempfile.mkstemp(
                    prefix=f".{target.name}.backup-{index}.",
                    suffix=".tmp",
                    dir=target.parent,
                )
                os.close(descriptor)
                backup = Path(backup_name)
                backups.append(backup)
                # Copy the rollback bytes without moving the published path.
                # Readers therefore see either the old complete file or the
                # new complete file, never an ENOENT window before replace.
                shutil.copyfile(target, backup)
                with backup.open("rb") as handle:
                    os.fsync(handle.fileno())
            # Record before the staged replace so failure still restores the
            # just-created backup.
            promoted.append((target, backup))
            os.replace(source, target)
    except Exception:
        for target, backup in reversed(promoted):
            if backup is not None and backup.exists():
                os.replace(backup, target)
            elif target.exists():
                target.unlink()
        raise
    finally:
        for path in [*staged, *backups]:
            if path.exists():
                path.unlink()


def build_from_disk(
    *,
    root: Path | None = None,
    canonical_path: Path | None = None,
    public_path: Path | None = None,
    as_of: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Verify the W1 generation and publish the Wave 2A projection."""
    root = root or _data_root()
    canonical_path = canonical_path or (root / "projection.json")
    public_path = public_path or (
        _repo_root() / "site" / "capital-structure-data" / "latest.json"
    )
    produced_at = generated_at or _now_iso()

    # Repair a hard-stop gap from the previous invocation before inspecting the
    # current source generation. Even if that source now fails verification,
    # the last-good public/canonical pair returns to a byte-identical state.
    _recover_projection_pair(canonical_path, public_path)

    manifest_path = root / "source_manifest.parquet"
    manifests = (
        dataframe_records(pd.read_parquet(manifest_path))
        if manifest_path.exists()
        else []
    )
    telemetry_path = root / "telemetry.json"
    telemetry = (
        _read_json_object(telemetry_path)
        if telemetry_path.exists()
        else {
            "status": "missing",
            "as_of": None,
            "generation_id": None,
            "artifact_hashes": {},
            "source_ledger_receipt": None,
            "coverage_claim": None,
            "known_exclusions": [],
        }
    )
    has_generation = _validate_committed_generation(
        root, _load_contract("telemetry"), manifests
    )

    if has_generation:
        events = _load_existing_events(
            pd.read_parquet(root / "event_versions.parquet"),
            _load_contract("event"),
        )
        edge_frame = pd.read_parquet(root / "event_edges.parquet")
        if edge_frame.columns.tolist() != EDGE_COLUMNS:
            raise ValueError("event edge ledger columns changed before projection")
        edges = _load_existing_edges(edge_frame, _load_contract("edge"))
        reviews = _validate_review_rows(pd.read_parquet(root / "review_queue.parquet"))
    else:
        events, edges, reviews = [], [], []

    projection_as_of = as_of or telemetry.get("as_of") or produced_at
    bundle = build_projection_bundle(
        events,
        edges,
        reviews,
        telemetry,
        as_of=str(projection_as_of),
        generated_at=produced_at,
    )
    validate_projection_bundle(bundle)
    payload = (
        json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    _promote_pair(payload, canonical_path, public_path)
    if canonical_path.read_bytes() != public_path.read_bytes():
        raise ValueError("canonical/public capital-structure projections diverged")
    return {
        "status": bundle["coverage"]["state"],
        "generation_id": bundle["generation_id"],
        "as_of": bundle["as_of"],
        "issuers": bundle["coverage"]["issuer_count"],
        "events": bundle["coverage"]["event_count"],
        "canonical_path": str(canonical_path),
        "public_path": str(public_path),
        "byte_length": len(payload),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--canonical-path", type=Path, default=None)
    parser.add_argument("--public-path", type=Path, default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args(argv)
    summary = build_from_disk(
        root=args.root,
        canonical_path=args.canonical_path,
        public_path=args.public_path,
        as_of=args.as_of,
        generated_at=args.generated_at,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
