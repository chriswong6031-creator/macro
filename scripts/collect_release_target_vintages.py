"""Collect canonical ALFRED full-vintage stores for release-target truth.

Every requested cohort is fetched and staged before any canonical parquet is
replaced.  The old manifest and downstream CPI completion marker are then
invalidated before the first source mutation, and the new exact-byte manifest
is published last.  Missing credentials and per-series fetch failures leave the
prior cohort untouched.

Usage::

    python3 scripts/collect_release_target_vintages.py
    python3 scripts/collect_release_target_vintages.py --series CPIAUCSL PAYEMS
    python3 scripts/collect_release_target_vintages.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from collectors.fred import fetch_all_vintages
from engine.release_target_truth import (
    SOURCE_OUTPUT_TYPE,
    SUPPORTED_SERIES,
    default_vintage_path,
    load_full_vintage_parquets,
    normalize_full_vintage_frame,
)
from lib import config

log = logging.getLogger(__name__)
_REALTIME_START = "1997-01-01"
_INTEGRITY_PROFILE = "release_target_artifact_sha256_bytes.v1"


def collect_release_target_vintages(
    *,
    repo_root: str | Path = _REPO,
    series_ids: Sequence[str] = SUPPORTED_SERIES,
    realtime_start: str = _REALTIME_START,
    api_key: str | None = None,
    dry_run: bool = False,
    fetcher: Callable[..., pd.DataFrame] | None = None,
    publisher: Callable[[Path, Path], None] | None = None,
) -> dict[str, Any]:
    """Fetch and persist bounded full-vintage matrices.

    The returned receipt is suitable for logs/monitoring.  It is always
    explicit about skipped and failed series.  With no ``FRED_API_KEY`` the
    function returns ``status='skipped'`` without creating directories or
    touching any existing parquet.

    ``fetcher`` and ``publisher`` are injectable for deterministic tests.
    Production defaults to :func:`collectors.fred.fetch_all_vintages`, always
    requests ``output_type=2``, and publishes only a fully validated cohort.
    """
    root = Path(repo_root)
    requested = _normalize_series_ids(series_ids)
    key = api_key if api_key is not None else config.secret("FRED_API_KEY")
    collected_at = _utc_now()
    receipt: dict[str, Any] = {
        "schema": "release_target_vintage_collection.v1",
        "integrity_profile": _INTEGRITY_PROFILE,
        "status": "pending",
        "source": "FRED/ALFRED",
        "source_output_type": SOURCE_OUTPUT_TYPE,
        "realtime_start": realtime_start,
        "collected_at": collected_at,
        "dry_run": dry_run,
        "series": {},
    }

    if not key:
        receipt["status"] = "skipped"
        receipt["reason"] = "missing_fred_api_key"
        receipt["completed_at"] = _utc_now()
        log.warning(
            "[release_target_vintages] FRED_API_KEY absent; leaving stores untouched"
        )
        return receipt

    run_fetcher = fetcher or fetch_all_vintages
    publish_staged = publisher or _publish_staged_parquet
    target_dir = root / "data" / "fred_vintage" / "release_targets"
    manifest = target_dir / "manifest.json"
    downstream_completion = (
        root / "data" / "release_forecast" / "cpi_truth" / "build_completion.json"
    )
    successful = 0
    failed = 0
    staged: dict[str, tuple[Path, Path, dict[str, Any]]] = {}
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)
    stage_context = (
        tempfile.TemporaryDirectory(prefix=".release-target-cohort.", dir=target_dir)
        if not dry_run
        else None
    )
    stage_root = Path(stage_context.name) if stage_context is not None else None
    try:
        for series_id in requested:
            output_path = default_vintage_path(root, series_id)
            receipt_path = output_path.relative_to(root).as_posix()
            try:
                raw = run_fetcher(
                    series_id=series_id,
                    output_type=SOURCE_OUTPUT_TYPE,
                    realtime_start=realtime_start,
                    api_key=key,
                )
                if raw is None or raw.empty:
                    failed += 1
                    receipt["series"][series_id] = {
                        "status": "skipped",
                        "reason": "empty_fetch",
                        "path": receipt_path,
                    }
                    log.warning(
                        "[release_target_vintages] %s returned no rows; prior cohort untouched",
                        series_id,
                    )
                    continue

                tagged = raw.copy()
                tagged["series"] = series_id
                tagged["source_output_type"] = SOURCE_OUTPUT_TYPE
                normalized = normalize_full_vintage_frame(tagged, series_id=series_id)
                if normalized.empty:
                    failed += 1
                    receipt["series"][series_id] = {
                        "status": "skipped",
                        "reason": "no_valid_rows_after_normalization",
                        "path": receipt_path,
                    }
                    continue

                metadata = {
                    "path": receipt_path,
                    "rows": len(normalized),
                    "periods": int(normalized["period"].nunique()),
                    "release_dates": int(normalized["realtime_start"].nunique()),
                    "period_min": normalized["period"].min().date().isoformat(),
                    "period_max": normalized["period"].max().date().isoformat(),
                }
                artifact: dict[str, Any] = {}
                if not dry_run:
                    if stage_root is None:  # pragma: no cover - construction invariant
                        raise RuntimeError("cohort staging directory was not created")
                    staged_path = stage_root / output_path.name
                    artifact = _atomic_write_parquet(normalized, staged_path)
                    staged[series_id] = (staged_path, output_path, artifact)
                successful += 1
                receipt["series"][series_id] = {
                    "status": "dry_run" if dry_run else "staged",
                    **metadata,
                }
                log.info(
                    "[release_target_vintages] %s: %d rows, %d periods validated%s",
                    series_id,
                    metadata["rows"],
                    metadata["periods"],
                    " (dry run)" if dry_run else "",
                )
            except Exception as exc:
                failed += 1
                receipt["series"][series_id] = {
                    "status": "failed",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "path": receipt_path,
                }
                log.exception(
                    "[release_target_vintages] %s failed; prior cohort untouched",
                    series_id,
                )

        if failed:
            receipt["status"] = "partial" if successful else "failed"
            receipt["publication_status"] = "aborted_before_source_mutation"
            for series_id in staged:
                receipt["series"][series_id]["status"] = "validated_not_published"
                receipt["series"][series_id]["reason"] = "cohort_validation_failed"
            receipt["completed_at"] = _utc_now()
            return receipt

        if dry_run:
            receipt["status"] = "dry_run"
            receipt["publication_status"] = "not_requested"
            receipt["completed_at"] = _utc_now()
            return receipt

        # From this boundary onward, marker absence explicitly means the cohort
        # is incomplete.  A crash or disk error can leave source files changed,
        # but never under an old manifest or downstream CPI completion receipt.
        # The CPI completion receipt binds the exact shared manifest bytes, so
        # even a PAYEMS/PCE/PPI-only subset publication invalidates it.
        _invalidate_file(downstream_completion)
        _invalidate_file(manifest)

        published: set[str] = set()
        try:
            for series_id in requested:
                staged_path, output_path, artifact = staged[series_id]
                publish_staged(staged_path, output_path)
                _fsync_file(output_path)
                _fsync_directory(output_path.parent)
                if (
                    output_path.stat().st_size != artifact["artifact_bytes"]
                    or _sha256_file(output_path) != artifact["artifact_sha256"]
                ):
                    raise OSError(
                        f"published artifact binding mismatch for {series_id}"
                    )
                receipt["series"][series_id].update({"status": "written", **artifact})
                published.add(series_id)
        except Exception as exc:
            receipt["status"] = "failed"
            receipt["publication_status"] = "incomplete_markers_invalidated"
            receipt["reason"] = (
                f"cohort_publication_failed: {type(exc).__name__}: {exc}"
            )
            for series_id in requested:
                if series_id not in published:
                    receipt["series"][series_id]["status"] = "not_published"
            receipt["completed_at"] = _utc_now()
            raise RuntimeError(receipt["reason"]) from exc

        receipt["status"] = "ok"
        receipt["publication_status"] = "complete"
        receipt["completed_at"] = _utc_now()
        _atomic_write_json(receipt, manifest)
        return receipt
    finally:
        if stage_context is not None:
            stage_context.cleanup()


def seal_existing_release_target_vintages(
    *,
    repo_root: str | Path = _REPO,
    series_ids: Sequence[str] = SUPPORTED_SERIES,
) -> dict[str, Any]:
    """Hash-bind already persisted full-vintage stores without refetching them.

    This migration is deliberately separate from collection: it preserves the
    prior collection clock and never presents a local integrity pass as fresh
    upstream data.  Every requested store must validate before the manifest is
    replaced, so a partial cohort can never be blessed as complete.
    """

    root = Path(repo_root)
    requested = _normalize_series_ids(series_ids)
    manifest = root / "data" / "fred_vintage" / "release_targets" / "manifest.json"
    prior: dict[str, Any] = {}
    if manifest.exists():
        try:
            decoded = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(decoded, dict):
                prior = decoded
        except (OSError, json.JSONDecodeError):
            prior = {}

    collected_at = str(prior.get("collected_at") or "").strip() or None
    sealed_at = _utc_now()
    receipt: dict[str, Any] = {
        "schema": "release_target_vintage_collection.v1",
        "integrity_profile": _INTEGRITY_PROFILE,
        "status": "pending",
        "mode": "seal_existing",
        "source": "FRED/ALFRED",
        "source_output_type": SOURCE_OUTPUT_TYPE,
        "realtime_start": prior.get("realtime_start", _REALTIME_START),
        "collected_at": collected_at,
        "completed_at": prior.get("completed_at") or collected_at,
        "sealed_at": sealed_at,
        "dry_run": False,
        "series": {},
    }

    for series_id in requested:
        output_path = default_vintage_path(root, series_id)
        if not output_path.is_file():
            raise FileNotFoundError(f"missing release-target store: {output_path}")
        normalized = load_full_vintage_parquets(output_path, series_id=series_id)
        if normalized.empty:
            raise ValueError(f"release-target store is empty: {output_path}")
        receipt["series"][series_id] = {
            "status": "sealed",
            "path": output_path.relative_to(root).as_posix(),
            "rows": len(normalized),
            "periods": int(normalized["period"].nunique()),
            "release_dates": int(normalized["realtime_start"].nunique()),
            "period_min": normalized["period"].min().date().isoformat(),
            "period_max": normalized["period"].max().date().isoformat(),
            "artifact_sha256": _sha256_file(output_path),
            "artifact_bytes": output_path.stat().st_size,
        }

    receipt["status"] = "ok"
    if _sealed_manifest_equivalent(prior, receipt):
        return prior
    _invalidate_file(
        root / "data" / "release_forecast" / "cpi_truth" / "build_completion.json"
    )
    _atomic_write_json(receipt, manifest)
    return receipt


def _normalize_series_ids(series_ids: Sequence[str]) -> tuple[str, ...]:
    requested: list[str] = []
    for raw in series_ids:
        for part in str(raw).split(","):
            series = part.upper().strip()
            if not series:
                continue
            if series not in SUPPORTED_SERIES:
                raise ValueError(
                    f"unsupported release-target series {series!r}; "
                    f"supported={list(SUPPORTED_SERIES)}"
                )
            if series not in requested:
                requested.append(series)
    if not requested:
        raise ValueError("at least one supported series is required")
    return tuple(requested)


def _sealed_manifest_equivalent(
    prior: dict[str, Any], candidate: dict[str, Any]
) -> bool:
    """Whether a prior sealed manifest already binds the exact candidate cohort."""

    if not prior or prior.get("mode") != "seal_existing":
        return False
    ignored = {"sealed_at"}
    return {key: value for key, value in prior.items() if key not in ignored} == {
        key: value for key, value in candidate.items() if key not in ignored
    }


def _atomic_write_parquet(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    """Atomically replace ``path`` and bind the exact persisted parquet bytes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.stem}.", suffix=".parquet", dir=path.parent, delete=False
    ) as handle:
        temp_path = Path(handle.name)
    try:
        frame.to_parquet(temp_path, index=False)
        artifact = {
            "artifact_sha256": _sha256_file(temp_path),
            "artifact_bytes": temp_path.stat().st_size,
        }
        _fsync_file(temp_path)
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
        return artifact
    finally:
        temp_path.unlink(missing_ok=True)


def _publish_staged_parquet(staged_path: Path, output_path: Path) -> None:
    """Atomically move one validated staged parquet into its canonical slot."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged_path, output_path)


def _invalidate_file(path: Path) -> None:
    """Durably remove a completion marker before mutating its bound sources."""

    if not path.exists():
        return
    path.unlink()
    _fsync_directory(path.parent)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.stem}.", suffix=".json", dir=path.parent, delete=False
    ) as handle:
        temp_path = Path(handle.name)
    try:
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _fsync_file(temp_path)
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect ALFRED output_type=2 stores for canonical release targets"
    )
    parser.add_argument(
        "--series",
        nargs="+",
        default=list(SUPPORTED_SERIES),
        help="Supported FRED series IDs (space- or comma-separated)",
    )
    parser.add_argument(
        "--realtime-start",
        default=_REALTIME_START,
        help="Earliest ALFRED real-time date (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Fetch/validate, do not write"
    )
    parser.add_argument(
        "--seal-existing",
        action="store_true",
        help="Hash-bind existing stores without fetching or changing data clocks",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    if args.seal_existing:
        if args.dry_run:
            raise SystemExit("--seal-existing and --dry-run are mutually exclusive")
        result = seal_existing_release_target_vintages(series_ids=args.series)
    else:
        result = collect_release_target_vintages(
            series_ids=args.series,
            realtime_start=args.realtime_start,
            dry_run=args.dry_run,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result.get("status") not in {"ok", "dry_run", "skipped"}:
        raise SystemExit(1)
