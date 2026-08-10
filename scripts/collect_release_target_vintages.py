"""Collect canonical ALFRED full-vintage stores for release-target truth.

Each output is an independent, atomically replaced parquet carrying explicit
``series`` and ``source_output_type=2`` columns.  Missing credentials and
per-series fetch failures are fail-open: no existing artifact is overwritten.

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
) -> dict[str, Any]:
    """Fetch and persist bounded full-vintage matrices.

    The returned receipt is suitable for logs/monitoring.  It is always
    explicit about skipped and failed series.  With no ``FRED_API_KEY`` the
    function returns ``status='skipped'`` without creating directories or
    touching any existing parquet.

    ``fetcher`` is injectable for deterministic tests; production defaults to
    :func:`collectors.fred.fetch_all_vintages` and always requests
    ``output_type=2``.
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
    successful = 0
    failed = 0
    for series_id in requested:
        output_path = default_vintage_path(root, series_id)
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
                    "path": str(output_path),
                }
                log.warning(
                    "[release_target_vintages] %s returned no rows; existing store untouched",
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
                    "path": str(output_path),
                }
                continue

            rows = len(normalized)
            periods = int(normalized["period"].nunique())
            release_dates = int(normalized["realtime_start"].nunique())
            artifact: dict[str, Any] = {}
            if not dry_run:
                artifact = _atomic_write_parquet(normalized, output_path)
            successful += 1
            receipt["series"][series_id] = {
                "status": "dry_run" if dry_run else "written",
                "path": str(output_path),
                "rows": rows,
                "periods": periods,
                "release_dates": release_dates,
                "period_min": normalized["period"].min().date().isoformat(),
                "period_max": normalized["period"].max().date().isoformat(),
                **artifact,
            }
            log.info(
                "[release_target_vintages] %s: %d rows, %d periods -> %s%s",
                series_id,
                rows,
                periods,
                output_path,
                " (dry run)" if dry_run else "",
            )
        except Exception as exc:
            failed += 1
            receipt["series"][series_id] = {
                "status": "failed",
                "reason": f"{type(exc).__name__}: {exc}",
                "path": str(output_path),
            }
            log.exception(
                "[release_target_vintages] %s failed; existing store untouched",
                series_id,
            )

    if successful and not failed:
        receipt["status"] = "dry_run" if dry_run else "ok"
    elif successful:
        receipt["status"] = "partial"
    else:
        receipt["status"] = "failed"

    # This clock is stamped only after every requested series has either been
    # durably replaced or recorded as failed/skipped.  The manifest is written
    # last, so its presence remains the collection-completion boundary.
    receipt["completed_at"] = _utc_now()
    if successful and not dry_run:
        manifest = root / "data" / "fred_vintage" / "release_targets" / "manifest.json"
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
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    result = collect_release_target_vintages(
        series_ids=args.series,
        realtime_start=args.realtime_start,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
