"""Coherent CPI target history and archived-release parity gates.

This module is deliberately upstream of every Release Radar model.  It turns
the ALFRED ``output_type=2`` stores into a small, deterministic history where
the target-month and prior-month index levels are selected from the *same*
release vintage.  It does not fit a model and it does not promote an epoch.

The ALFRED-derived one-decimal value remains a proxy.  The governed comparison
corpus contains official BLS archived release-edition observations, whose
retrospective files are not proof of the bytes or values first published on a
release day.  A preregistered parity sample can make
``alfred_same_release_vintage_proxy_v1`` a usable candidate target epoch, but
``official_first_print_v1`` remains withheld until actual first-publication
evidence, a complete history, and a separate promotion decision exist.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from engine.release_cpi_official_truth import (
    ARCHIVE_NONPUBLICATION_ACTUAL_BASIS,
    ARCHIVE_SEQUENCE,
    ARCHIVED_TABLE1_ACTUAL_BASIS,
    FIRST_PRINT_STATUS,
    CpiOfficialTruthError,
    CpiSourceSpec,
    build_cpi_not_published_truth,
    canonical_json_bytes,
    rebuild_cpi_official_truth_receipt,
)
from engine.release_target_truth import (
    SOURCE_OUTPUT_TYPE,
    load_full_vintage_parquets,
    reconstruct_release_target,
    round_published_1dp,
)

HISTORY_SCHEMA = "release_cpi_target_history.v1"
TARGET_ROW_SCHEMA = "release_cpi_target.v1"
PARITY_SCHEMA = "release_cpi_truth_parity.v1"
PREREGISTERED_SAMPLE_SCHEMA = "release_cpi_truth_preregistered_sample.v1"
OFFICIAL_COLLECTION_MANIFEST_SCHEMA = "release_cpi_official_collection_manifest.v1"
COLLECTOR_MANIFEST_SCHEMA = "release_target_vintage_collection.v1"
COLLECTOR_INTEGRITY_PROFILE = "release_target_artifact_sha256_bytes.v1"
OFFICIAL_TRUTH_SCHEMA = "release_cpi_official_truth.v1"
OFFICIAL_TRUTH_INTEGRITY_PROFILE = "bls_table1_exact_bytes_sha256.v1"
OFFICIAL_NONPUBLICATION_INTEGRITY_PROFILE = (
    "bls_nonpublication_page_exact_bytes_sha256.v1"
)
OFFICIAL_NONPUBLICATION_DECLARATION_SCHEMA = (
    "release_cpi_archive_nonpublication_declaration.v1"
)
OFFICIAL_NONPUBLICATION_URL = "https://www.bls.gov/bls/news-release/cpi.htm"

CANDIDATE_TARGET_EPOCH = "alfred_same_release_vintage_proxy_v1"
OFFICIAL_ARCHIVE_OBSERVATION_EPOCH = "official_bls_archived_release_table1_v1"
WITHHELD_OFFICIAL_TARGET_EPOCH = "official_first_print_v1"

MIN_RELEASE_LAG_DAYS = 7
MAX_RELEASE_LAG_DAYS = 45

CPI_SERIES_BY_RELEASE: dict[str, str] = {
    "cpi_headline": "CPIAUCSL",
    "cpi_core": "CPILFESL",
}
DEFAULT_PREREGISTERED_SAMPLE_RELPATH = (
    Path("data") / "release_forecast" / "cpi_truth" / "preregistered_sample.json"
)

_HEADLINE_ALIASES = (
    "headline_mom",
    "cpi_headline_mom",
    "headline_cpi_mom",
    "cpi_mom",
)
_CORE_ALIASES = (
    "core_mom",
    "cpi_core_mom",
    "core_cpi_mom",
)
_ALLOWED_CLASSIFICATIONS = {"annual_revision", "ordinary", "explicit_gap"}
_MONTH_PREFIX = re.compile(r"^(\d{4})-(\d{2})(?:-\d{2})?$")


class CpiTargetHistoryError(ValueError):
    """A source cannot safely produce a coherent CPI target history."""


class CpiTruthParityError(CpiTargetHistoryError):
    """The preregistered official/ALFRED comparison cannot pass safely."""


def default_cpi_vintage_paths(repo_root: str | Path) -> dict[str, Path]:
    """Return the canonical full-vintage paths keyed by release type."""

    root = Path(repo_root)
    base = root / "data" / "fred_vintage" / "release_targets"
    return {
        release: base / f"{series_id}_all_vintages.parquet"
        for release, series_id in CPI_SERIES_BY_RELEASE.items()
    }


def default_collector_manifest_path(repo_root: str | Path) -> Path:
    return (
        Path(repo_root) / "data" / "fred_vintage" / "release_targets" / "manifest.json"
    )


def default_preregistered_sample_path(repo_root: str | Path) -> Path:
    return Path(repo_root) / DEFAULT_PREREGISTERED_SAMPLE_RELPATH


def build_cpi_target_history(
    repo_root: str | Path | None = None,
    *,
    vintage_paths: Mapping[str, str | Path] | None = None,
    manifest_path: str | Path | None = None,
    preregistered_sample_path: str | Path | None = None,
    min_release_lag_days: int = MIN_RELEASE_LAG_DAYS,
    max_release_lag_days: int = MAX_RELEASE_LAG_DAYS,
) -> dict[str, Any]:
    """Build sorted headline/core CPI targets from bound full-vintage stores.

    ``vintage_paths`` may be keyed by release type (``cpi_headline`` /
    ``cpi_core``) or by FRED series id (``CPIAUCSL`` / ``CPILFESL``).
    Every source parquet must be byte-bound by the collector manifest.  The
    absolute path recorded by a runner is not portable, so binding is by
    series id, basename, exact byte count, and exact SHA-256.

    ALFRED bulk-inception rows are not historical releases.  A period is
    eligible only when its earliest realtime start is in the immediately next
    calendar month and 7--45 days after the reference month ended.  Once a row
    is eligible, failure to find exactly one same-vintage prior level aborts
    the entire build rather than silently dropping a target.
    """

    if min_release_lag_days < 0 or max_release_lag_days < min_release_lag_days:
        raise CpiTargetHistoryError("invalid release-lag bounds")

    logical_root = _logical_root(repo_root)
    resolved_paths = _resolve_vintage_paths(repo_root, vintage_paths)
    resolved_manifest = _resolve_manifest_path(repo_root, manifest_path)
    manifest, manifest_receipt = _load_and_bind_manifest(
        resolved_manifest,
        resolved_paths,
        logical_root=logical_root,
    )
    gap_evidence, gap_receipt = _load_preregistered_nonpublications(
        repo_root,
        preregistered_sample_path,
        logical_root=logical_root,
    )
    gap_periods = set(gap_evidence)

    targets: list[dict[str, Any]] = []
    source_artifacts: dict[str, dict[str, Any]] = {}
    rejected_counts: Counter[str] = Counter()
    rejected_periods: list[dict[str, Any]] = []

    for release, series_id in CPI_SERIES_BY_RELEASE.items():
        path = resolved_paths[release]
        entry = _manifest_series_entry(manifest, series_id)
        artifact = _artifact_receipt(
            path,
            entry,
            manifest_receipt,
            logical_root=logical_root,
        )
        source_artifacts[series_id] = artifact

        frame = load_full_vintage_parquets(path, series_id=series_id)
        _validate_loaded_frame_against_manifest(frame, entry, series_id)
        release_targets, series_rejections, series_rejected_periods = (
            _build_series_history(
                frame,
                release=release,
                series_id=series_id,
                artifact=artifact,
                min_release_lag_days=min_release_lag_days,
                max_release_lag_days=max_release_lag_days,
                known_nonpublication_periods=gap_periods,
            )
        )
        if not release_targets:
            raise CpiTargetHistoryError(
                f"{series_id} produced no plausible next-month release targets"
            )
        targets.extend(release_targets)
        rejected_counts.update(series_rejections)
        rejected_periods.extend(series_rejected_periods)

    release_order = {
        release: position for position, release in enumerate(CPI_SERIES_BY_RELEASE)
    }
    targets.sort(
        key=lambda row: (
            str(row["period"]),
            release_order.get(str(row["release"]), len(release_order)),
        )
    )
    _require_headline_core_alignment(targets)
    history_hash = _payload_sha256(targets)
    first_target = targets[0]
    last_target = targets[-1]
    rejected_periods.sort(key=lambda row: (str(row["period"]), str(row["release"])))
    rejected_after_nonpublication = sorted(
        {
            str(row["period"])
            for row in rejected_periods
            if row["reason"] == "prior_period_officially_not_published"
        }
    )
    coverage = {
        "candidate_period_start": str(first_target["period"]),
        "candidate_period_end": str(last_target["period"]),
        "target_rows": len(targets),
        "targets_per_release": {
            release: sum(1 for row in targets if row["release"] == release)
            for release in CPI_SERIES_BY_RELEASE
        },
        "start_boundary": {
            "period": first_target["period"],
            "release_date": first_target["release_date"],
            "release_lag_days": first_target["release_lag_days"],
            "admitted_because": (
                "earliest realtime_start is in the immediately next calendar "
                "month and the release lag is within the inclusive 7-45 day gate"
            ),
        },
        "explicit_nonpublication_periods": sorted(gap_periods),
        "coherent_targets_rejected_after_nonpublication": (
            rejected_after_nonpublication
        ),
    }

    return {
        "schema": HISTORY_SCHEMA,
        "status": "candidate",
        "asof": manifest_receipt["completed_at"],
        "candidate_data_asof": manifest_receipt["completed_at"],
        "target_epoch": CANDIDATE_TARGET_EPOCH,
        "candidate_target_epoch": {
            "name": CANDIDATE_TARGET_EPOCH,
            "status": "candidate_requires_preregistered_parity",
        },
        "official_archive_observation_epoch": {
            "name": OFFICIAL_ARCHIVE_OBSERVATION_EPOCH,
            "status": "preregistered_parity_required",
            "observation_kind": "official_archived_release_edition",
            "first_print_status": FIRST_PRINT_STATUS,
            "first_publication_evidence_verified": False,
        },
        "official_target_epoch": {
            "name": WITHHELD_OFFICIAL_TARGET_EPOCH,
            "status": "withheld",
            "promotion_authorized": False,
            "reason": (
                "ALFRED same-vintage values are release proxies, not a complete "
                "official first-print history; retrospective BLS archive editions "
                "do not establish first-published bytes or values"
            ),
        },
        "target_definition": {
            "basis": "alfred_same_release_vintage",
            "value": "published_proxy_1dp",
            "rounding": "decimal_half_up_0.1_percentage_point",
            "published_proxy_is_official_release": False,
            "source_output_type": SOURCE_OUTPUT_TYPE,
        },
        "release_lag_gate": {
            "calendar_month": "immediately_after_reference_month",
            "days_after_reference_month_end_min": min_release_lag_days,
            "days_after_reference_month_end_max": max_release_lag_days,
        },
        "source_manifest": manifest_receipt,
        "source_artifacts": source_artifacts,
        "known_nonpublications": {
            "periods": sorted(gap_periods),
            "cases": [gap_evidence[period] for period in sorted(gap_evidence)],
            "preregistered_sample": gap_receipt,
        },
        "history_hash": f"sha256:{history_hash}",
        "coverage": coverage,
        "n_targets": len(targets),
        "n_by_release": {
            release: sum(1 for row in targets if row["release"] == release)
            for release in CPI_SERIES_BY_RELEASE
        },
        "period_min": min(str(row["period"]) for row in targets),
        "period_max": max(str(row["period"]) for row in targets),
        "rejected_candidate_rows": {
            "n": sum(rejected_counts.values()),
            "by_reason": dict(sorted(rejected_counts.items())),
            "note": (
                "Rejected rows include ALFRED bulk-inception state and any earliest "
                "realtime start that is not a plausible next-month CPI release"
            ),
        },
        "rejected_candidate_periods": rejected_periods,
        "targets": targets,
        "display_only": True,
        "authority": False,
    }


def load_official_table1_receipts(path: str | Path) -> list[dict[str, Any]]:
    """Load official CPI receipts into a schema-tolerant comparison shape.

    Supported inputs include JSONL publication receipts with a ``metrics``
    mapping, nested ``actual``/``table1`` metric mappings, and normalized
    one-metric rows such as ``release='cpi_headline', actual=0.2``.  Values may
    be scalars or mappings containing ``value``/``actual``.  The loader is
    flexible about container shape but strict about period identity, numeric
    finiteness, and conflicting duplicate metric values.
    """

    receipt_path = Path(path)
    objects = _read_json_records(receipt_path, kind="official Table 1 receipts")
    normalized: list[dict[str, Any]] = []
    for obj in objects:
        period = _extract_period(obj)
        release_date = _optional_iso_date(
            obj.get("release_date")
            or obj.get("date")
            or _nested_get(obj, "publication", "release_date")
        )
        metrics = _extract_metrics(obj)
        status = str(obj.get("status") or "ok")
        if not metrics and status not in {"unavailable", "not_published", "gap"}:
            raise CpiTruthParityError(
                f"official receipt for {period} contains no headline/core MoM metric"
            )
        source = obj.get("source") if isinstance(obj.get("source"), Mapping) else {}
        normalized.append(
            {
                "period": period,
                "release_date": release_date,
                "status": status,
                "metrics": metrics,
                "receipt_id": obj.get("receipt_id") or obj.get("id"),
                "schema": obj.get("schema"),
                "integrity_profile": obj.get("integrity_profile"),
                "sequence": obj.get("sequence"),
                "source": dict(source),
                "source_sha256": obj.get("source_sha256")
                or source.get("document_sha256")
                or source.get("sha256"),
                "receipt_payload_sha256": _payload_sha256(obj),
                "raw": dict(obj),
            }
        )
    return normalized


def evaluate_preregistered_parity(
    history: Mapping[str, Any],
    *,
    official_receipts_path: str | Path,
    preregistered_sample_path: str | Path,
    official_collection_manifest_path: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Compare archived BLS release-edition observations with the ALFRED proxy.

    The preregistration and collection manifests must bind the exact receipt
    corpus and retained official BLS archive documents.  Every receipt is
    deterministically rebuilt from those documents before comparison.  These
    are retrospective archived release editions, not proven first-published
    observations.  January reference months are classified as
    ``annual_revision``; other observed periods are ``ordinary``.  Missing
    evidence is admissible only when preregistered as ``explicit_gap`` with a
    source-bound nonpublication receipt.  Any missing target, unexpected
    receipt, ambiguous receipt, binding failure, precision error, or metric
    mismatch raises :class:`CpiTruthParityError`.
    """

    candidate_data_asof = _validate_history_payload(history)
    receipts_path = Path(official_receipts_path)
    prereg_path = Path(preregistered_sample_path)
    logical_root = _logical_root(repo_root)
    prereg, prereg_receipt = _load_preregistered_manifest(
        prereg_path,
        logical_root=logical_root,
    )
    receipts_binding = _verify_receipts_binding(
        prereg,
        receipts_path,
        logical_root=logical_root,
    )
    receipts = load_official_table1_receipts(receipts_path)
    samples = _normalize_preregistered_samples(prereg)
    _validate_preregistered_gate(prereg, samples)
    collection_path = (
        Path(official_collection_manifest_path)
        if official_collection_manifest_path is not None
        else receipts_path.with_name("official_table1_collection.json")
    )
    collection_binding = _load_and_validate_official_collection(
        collection_path,
        prereg=prereg,
        prereg_path=prereg_path,
        receipts_path=receipts_path,
        samples=samples,
        receipts=receipts,
        logical_root=logical_root,
    )
    evidence_available_at = _latest_governed_timestamp(
        candidate_data_asof,
        prereg_receipt["frozen_at"],
        collection_binding["completed_at"],
    )
    preregistered_aggregate_verified = bool(
        receipts_binding["aggregate_binding_verified"]
    )
    receipts_binding.update(
        {
            "aggregate_binding_verified": True,
            "binding_mode": "collection_manifest_exact_ordered_corpus",
            "preregistered_aggregate_binding_verified": (
                preregistered_aggregate_verified
            ),
            "collection_manifest_artifact_sha256": collection_binding[
                "artifact_sha256"
            ],
            "ordered_receipt_count": collection_binding["receipts"]["count"],
            "per_case_receipt_identity_verified": True,
            "deterministic_receipt_rebuild_verified": collection_binding[
                "deterministic_receipt_rebuild_verified"
            ],
            "deterministic_receipt_rebuild_verified_count": collection_binding[
                "deterministic_receipt_rebuild_verified_count"
            ],
        }
    )

    target_index = {
        (str(row["release"]), str(row["period"])): row
        for row in history.get("targets", [])
        if isinstance(row, Mapping)
    }
    if len(target_index) != len(history.get("targets", [])):
        raise CpiTruthParityError(
            "history contains duplicate or malformed target identities"
        )

    cases: list[dict[str, Any]] = []
    source_evidence_results: list[bool] = []
    classification_counts: Counter[str] = Counter()
    comparison_count = 0
    for sample in samples:
        period = sample["period"]
        classification = sample["classification"]
        classification_counts[classification] += 1
        period_receipts = [
            receipt for receipt in receipts if receipt.get("period") == period
        ]
        matching_receipts = _matching_receipts(receipts, sample)
        source_evidence_results.append(
            _validate_case_receipt_bindings(
                prereg,
                sample,
                matching_receipts,
                period_receipts=period_receipts,
                aggregate_binding_verified=bool(
                    receipts_binding["aggregate_binding_verified"]
                ),
            )
        )

        if classification == "explicit_gap":
            unexpected = sorted(
                {
                    metric
                    for receipt in matching_receipts
                    for metric in receipt["metrics"]
                }
            )
            if unexpected:
                raise CpiTruthParityError(
                    f"preregistered explicit gap {period} unexpectedly has metrics: "
                    f"{unexpected}; re-preregister before using the new evidence"
                )
            if any(str(receipt.get("status")) == "ok" for receipt in matching_receipts):
                raise CpiTruthParityError(
                    f"preregistered explicit gap {period} has an unexpected ok receipt"
                )
            cases.append(
                {
                    "period": period,
                    "release_date": sample.get("release_date"),
                    "classification": classification,
                    "status": "explicit_gap",
                    "reason": sample["reason"],
                    "comparisons": [],
                }
            )
            continue

        if not matching_receipts:
            raise CpiTruthParityError(
                f"preregistered {classification} sample has no official receipt: "
                f"{period}"
            )
        if any(str(receipt.get("status")) != "ok" for receipt in matching_receipts):
            raise CpiTruthParityError(
                f"preregistered published sample has a non-ok official receipt: {period}"
            )

        comparisons: list[dict[str, Any]] = []
        for release in CPI_SERIES_BY_RELEASE:
            target = target_index.get((release, period))
            if target is None:
                raise CpiTruthParityError(
                    f"preregistered {classification} sample is missing ALFRED target "
                    f"{release}/{period}"
                )
            expected_release_date = sample.get("release_date")
            if (
                expected_release_date
                and target.get("release_date") != expected_release_date
            ):
                raise CpiTruthParityError(
                    f"release-date mismatch for {release}/{period}: "
                    f"history={target.get('release_date')} prereg={expected_release_date}"
                )

            official, evidence = _resolve_official_metric(
                matching_receipts,
                release,
                sample,
            )
            official_1dp = round_published_1dp(official)
            if not math.isclose(official, official_1dp, abs_tol=1e-12):
                raise CpiTruthParityError(
                    f"official Table 1 metric is not expressed at 0.1pp precision: "
                    f"{release}/{period}={official!r}"
                )
            proxy = float(target["published_proxy_1dp"])
            if not math.isclose(proxy, official_1dp, abs_tol=1e-12):
                raise CpiTruthParityError(
                    f"official/ALFRED parity mismatch for {release}/{period}: "
                    f"official={official_1dp} proxy={proxy}"
                )
            comparisons.append(
                {
                    "release": release,
                    "official_archived_release_edition_observation": official_1dp,
                    "alfred_published_proxy_1dp": proxy,
                    "difference_pp": 0.0,
                    "receipt_ids": evidence["receipt_ids"],
                    "source_sha256": evidence["source_sha256"],
                    "status": "match",
                }
            )
            comparison_count += 1

        cases.append(
            {
                "period": period,
                "release_date": sample.get("release_date"),
                "classification": classification,
                "status": "passed",
                "comparisons": comparisons,
            }
        )

    if comparison_count == 0:
        raise CpiTruthParityError(
            "preregistered sample contains no comparable official metrics"
        )
    receipts_binding["per_case_source_evidence_verified"] = all(source_evidence_results)
    receipts_binding["per_case_source_evidence_verified_count"] = sum(
        source_evidence_results
    )

    return {
        "schema": PARITY_SCHEMA,
        "status": "passed",
        "asof": evidence_available_at,
        "candidate_data_asof": candidate_data_asof,
        "evidence_available_at": evidence_available_at,
        "candidate_target_epoch": {
            "name": CANDIDATE_TARGET_EPOCH,
            "status": "candidate_archive_release_edition_parity_passed",
            "promotion_authorized": False,
        },
        "parity_basis": {
            "name": OFFICIAL_ARCHIVE_OBSERVATION_EPOCH,
            "observation_kind": "official_archived_release_edition",
            "description": "official archived release-edition observations",
            "first_print_status": FIRST_PRINT_STATUS,
            "first_publication_evidence_verified": False,
            "deterministic_receipt_rebuild_required": True,
            "deterministic_receipt_rebuild_verified": True,
        },
        "official_archive_observation_epoch": {
            "name": OFFICIAL_ARCHIVE_OBSERVATION_EPOCH,
            "status": "bounded_preregistered_parity_passed",
            "promotion_authorized": False,
            "first_print_status": FIRST_PRINT_STATUS,
            "first_publication_evidence_verified": False,
        },
        "official_target_epoch": {
            "name": WITHHELD_OFFICIAL_TARGET_EPOCH,
            "status": "withheld",
            "promotion_authorized": False,
            "reason": (
                "Parity against retrospective official BLS archive editions does "
                "not establish first-published bytes or values, create a complete "
                "official first-print history, or authorize a model/champion change"
            ),
        },
        "history_schema": history.get("schema"),
        "history_hash": history.get("history_hash"),
        "candidate_coverage": history.get("coverage"),
        "official_receipts": receipts_binding,
        "official_collection_manifest": collection_binding,
        "preregistered_sample": prereg_receipt,
        "n_cases": len(cases),
        "n_metric_comparisons": comparison_count,
        "classifications": dict(sorted(classification_counts.items())),
        "cases": cases,
        "display_only": True,
        "authority": False,
    }


def _resolve_vintage_paths(
    repo_root: str | Path | None,
    vintage_paths: Mapping[str, str | Path] | None,
) -> dict[str, Path]:
    supplied = vintage_paths or (
        default_cpi_vintage_paths(repo_root) if repo_root is not None else None
    )
    if supplied is None:
        raise CpiTargetHistoryError("repo_root or vintage_paths is required")
    resolved: dict[str, Path] = {}
    for release, series_id in CPI_SERIES_BY_RELEASE.items():
        raw = supplied.get(release) or supplied.get(series_id)
        if raw is None:
            raise CpiTargetHistoryError(
                f"missing full-vintage path for {release}/{series_id}"
            )
        path = Path(raw)
        if not path.is_file():
            raise CpiTargetHistoryError(f"full-vintage source is missing: {path}")
        resolved[release] = path
    return resolved


def _resolve_manifest_path(
    repo_root: str | Path | None,
    manifest_path: str | Path | None,
) -> Path:
    path = (
        Path(manifest_path)
        if manifest_path is not None
        else (
            default_collector_manifest_path(repo_root)
            if repo_root is not None
            else None
        )
    )
    if path is None or not path.is_file():
        raise CpiTargetHistoryError(f"collector manifest is missing: {path}")
    return path


def _load_preregistered_nonpublications(
    repo_root: str | Path | None,
    preregistered_sample_path: str | Path | None,
    *,
    logical_root: Path | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None]:
    if preregistered_sample_path is not None:
        path = Path(preregistered_sample_path)
        if not path.is_file():
            raise CpiTargetHistoryError(f"preregistered CPI sample is missing: {path}")
    elif repo_root is not None:
        path = default_preregistered_sample_path(repo_root)
        if not path.is_file():
            return {}, None
    else:
        return {}, None

    payload, receipt = _load_preregistered_manifest(
        path,
        logical_root=logical_root,
    )
    samples = _normalize_preregistered_samples(payload)
    evidence: dict[str, dict[str, Any]] = {}
    sources = payload.get("sources")
    if not isinstance(sources, Mapping):
        raise CpiTruthParityError(
            "preregistered nonpublication evidence has no source registry"
        )
    for sample in samples:
        if sample["classification"] != "explicit_gap":
            continue
        source_spec = sources.get(sample.get("source_id"))
        if not isinstance(source_spec, Mapping):
            raise CpiTruthParityError(
                f"nonpublication source is missing for {sample['period']}"
            )
        bound = _validate_preregistered_nonpublication_evidence(
            sample,
            source_spec,
        )
        evidence[str(sample["period"])] = bound
    return evidence, receipt


def _logical_root(repo_root: str | Path | None) -> Path | None:
    return Path(repo_root).resolve() if repo_root is not None else None


def _logical_path(path: Path, logical_root: Path | None) -> str:
    resolved = path.resolve()
    if logical_root is not None:
        try:
            return resolved.relative_to(logical_root).as_posix()
        except ValueError:
            pass
    return path.name


def _validate_preregistered_nonpublication_evidence(
    sample: Mapping[str, Any],
    source_spec: Mapping[str, Any],
) -> dict[str, Any]:
    period = str(sample["period"])
    case_id = sample.get("case_id")
    source_id = sample.get("source_id")
    reason = sample.get("reason")
    source_url = sample.get("release_page_url")
    statement = sample.get("evidence_statement")
    receipt_id = sample.get("receipt_id")
    source_sha = sample.get("source_sha256")
    evidence_sha = sample.get("evidence_sha256")
    evidence_bytes = sample.get("evidence_bytes")
    declaration_sha = sample.get("declaration_sha256")
    declaration_bytes = sample.get("declaration_bytes")

    if not isinstance(case_id, str) or not case_id.strip():
        raise CpiTruthParityError(f"nonpublication case_id is missing for {period}")
    if not isinstance(source_id, str) or not source_id.strip():
        raise CpiTruthParityError(f"nonpublication source_id is missing for {period}")
    if not isinstance(reason, str) or not reason.strip():
        raise CpiTruthParityError(f"nonpublication reason is missing for {period}")
    if source_url != OFFICIAL_NONPUBLICATION_URL:
        raise CpiTruthParityError(
            f"nonpublication source URL is not the pinned BLS page for {period}"
        )
    if (
        source_spec.get("url") != source_url
        or source_spec.get("publisher") != "U.S. Bureau of Labor Statistics"
        or source_spec.get("host") != "www.bls.gov"
        or source_spec.get("content_type") != "text/html"
    ):
        raise CpiTruthParityError(
            f"nonpublication source registry mismatch for {period}"
        )
    if not isinstance(statement, str) or not statement.strip():
        raise CpiTruthParityError(
            f"nonpublication evidence statement is missing for {period}"
        )
    normalized_statement = " ".join(statement.lower().split())
    month_label = pd.Timestamp(f"{period}-01").strftime("%B %Y").lower()
    if (
        f"{month_label} consumer price index" not in normalized_statement
        or "not published" not in normalized_statement
    ):
        raise CpiTruthParityError(
            f"nonpublication evidence statement does not identify {period}"
        )
    if not isinstance(receipt_id, str) or not re.fullmatch(
        r"cpi_official_truth:[0-9a-f]{32}", receipt_id
    ):
        raise CpiTruthParityError(
            f"nonpublication receipt_id is not pinned for {period}"
        )
    _require_sha256(source_sha, f"gap {period} source_sha256")
    _require_sha256(evidence_sha, f"gap {period} evidence_sha256")
    _require_positive_bytes(evidence_bytes, f"gap {period} evidence_bytes")
    if source_sha != evidence_sha:
        raise CpiTruthParityError(
            f"nonpublication source/evidence hash mismatch for {period}"
        )
    if (
        source_spec.get("container_sha256") != source_sha
        or source_spec.get("container_bytes") != evidence_bytes
    ):
        raise CpiTruthParityError(
            f"nonpublication source registry byte binding mismatch for {period}"
        )

    declaration = {
        "schema": OFFICIAL_NONPUBLICATION_DECLARATION_SCHEMA,
        "case_id": case_id,
        "source_id": source_id,
        "period": period,
        "reason": reason,
        "source_url": source_url,
        "evidence_statement": statement,
        "source_sha256": source_sha,
        "source_bytes": evidence_bytes,
    }
    body = canonical_json_bytes(declaration)
    calculated_declaration_sha = hashlib.sha256(body).hexdigest()
    _require_sha256(declaration_sha, f"gap {period} declaration_sha256")
    _require_positive_bytes(declaration_bytes, f"gap {period} declaration_bytes")
    if calculated_declaration_sha != declaration_sha or len(body) != declaration_bytes:
        raise CpiTruthParityError(
            f"nonpublication preregistered declaration mismatch for {period}"
        )
    if source_sha == declaration_sha:
        raise CpiTruthParityError(
            f"nonpublication evidence for {period} is only a self-hashed declaration"
        )
    return {
        "period": period,
        "case_id": case_id,
        "source_id": source_id,
        "receipt_id": receipt_id,
        "reason": reason,
        "source_url": source_url,
        "evidence_statement": statement,
        "source_sha256": source_sha,
        "source_bytes": evidence_bytes,
        "declaration_sha256": declaration_sha,
        "declaration_bytes": declaration_bytes,
        "evidence_basis": "retained_official_bls_html_bytes",
    }


def _load_and_bind_manifest(
    path: Path,
    vintage_paths: Mapping[str, Path],
    *,
    logical_root: Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = _read_json_mapping(path, kind="collector manifest")
    if payload.get("schema") != COLLECTOR_MANIFEST_SCHEMA:
        raise CpiTargetHistoryError(
            f"collector manifest schema must be {COLLECTOR_MANIFEST_SCHEMA!r}"
        )
    if payload.get("integrity_profile") != COLLECTOR_INTEGRITY_PROFILE:
        raise CpiTargetHistoryError(
            "collector manifest lacks the required exact-byte integrity profile"
        )
    if payload.get("source_output_type") != SOURCE_OUTPUT_TYPE:
        raise CpiTargetHistoryError("collector manifest source_output_type must be 2")
    if payload.get("status") != "ok":
        raise CpiTargetHistoryError(
            f"collector manifest status must be 'ok', got {payload.get('status')!r}"
        )
    completed_at = _normalize_governed_timestamp(
        payload.get("completed_at"),
        field="collector manifest completed_at",
        error_type=CpiTargetHistoryError,
    )

    # Force every required entry through exact byte/hash verification now.
    manifest_receipt = {
        "schema": payload["schema"],
        "integrity_profile": payload["integrity_profile"],
        "source_output_type": payload["source_output_type"],
        "collected_at": payload.get("collected_at"),
        "completed_at": completed_at,
        "path": _logical_path(path, logical_root),
        "artifact_bytes": path.stat().st_size,
        "artifact_sha256": _sha256_file(path),
    }
    for release, series_id in CPI_SERIES_BY_RELEASE.items():
        entry = _manifest_series_entry(payload, series_id)
        _artifact_receipt(
            vintage_paths[release],
            entry,
            manifest_receipt,
            logical_root=logical_root,
        )
    return payload, manifest_receipt


def _manifest_series_entry(
    manifest: Mapping[str, Any], series_id: str
) -> Mapping[str, Any]:
    series = manifest.get("series")
    if not isinstance(series, Mapping) or not isinstance(
        series.get(series_id), Mapping
    ):
        raise CpiTargetHistoryError(
            f"collector manifest has no bound entry for {series_id}"
        )
    entry = series[series_id]
    if entry.get("status") not in {"written", "sealed"}:
        raise CpiTargetHistoryError(
            f"collector manifest entry {series_id} is not durably written or sealed"
        )
    return entry


def _artifact_receipt(
    path: Path,
    entry: Mapping[str, Any],
    manifest_receipt: Mapping[str, Any],
    *,
    logical_root: Path | None = None,
) -> dict[str, Any]:
    expected_sha = entry.get("artifact_sha256")
    expected_bytes = entry.get("artifact_bytes")
    if not isinstance(expected_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_sha
    ):
        raise CpiTargetHistoryError(
            f"manifest entry for {path.name} has no valid artifact_sha256"
        )
    if not isinstance(expected_bytes, int) or expected_bytes <= 0:
        raise CpiTargetHistoryError(
            f"manifest entry for {path.name} has no valid artifact_bytes"
        )
    recorded_path = entry.get("path")
    if recorded_path and Path(str(recorded_path)).name != path.name:
        raise CpiTargetHistoryError(
            f"manifest basename mismatch for {path}: recorded={recorded_path!r}"
        )
    actual_bytes = path.stat().st_size
    actual_sha = _sha256_file(path)
    if actual_bytes != expected_bytes:
        raise CpiTargetHistoryError(
            f"source parquet byte-count mismatch for {path.name}: "
            f"manifest={expected_bytes} actual={actual_bytes}"
        )
    if actual_sha != expected_sha:
        raise CpiTargetHistoryError(
            f"source parquet SHA-256 mismatch for {path.name}: "
            f"manifest={expected_sha} actual={actual_sha}"
        )
    return {
        "path": _logical_path(path, logical_root),
        "artifact_bytes": actual_bytes,
        "artifact_sha256": actual_sha,
        "manifest_artifact_sha256": manifest_receipt["artifact_sha256"],
        "manifest_bound": True,
        "manifest_entry_status": entry.get("status"),
        "rows": entry.get("rows"),
        "periods": entry.get("periods"),
        "release_dates": entry.get("release_dates"),
        "period_min": entry.get("period_min"),
        "period_max": entry.get("period_max"),
    }


def _validate_loaded_frame_against_manifest(
    frame: pd.DataFrame,
    entry: Mapping[str, Any],
    series_id: str,
) -> None:
    if frame.empty:
        raise CpiTargetHistoryError(f"{series_id} full-vintage frame is empty")
    expected_rows = entry.get("rows")
    if isinstance(expected_rows, int) and len(frame) != expected_rows:
        raise CpiTargetHistoryError(
            f"{series_id} row-count mismatch: manifest={expected_rows} loaded={len(frame)}"
        )
    expected_periods = entry.get("periods")
    actual_periods = int(frame["period"].nunique())
    if isinstance(expected_periods, int) and actual_periods != expected_periods:
        raise CpiTargetHistoryError(
            f"{series_id} period-count mismatch: "
            f"manifest={expected_periods} loaded={actual_periods}"
        )
    if set(frame["series"]) != {series_id}:
        raise CpiTargetHistoryError(f"{series_id} source contains another series")


def _build_series_history(
    frame: pd.DataFrame,
    *,
    release: str,
    series_id: str,
    artifact: Mapping[str, Any],
    min_release_lag_days: int,
    max_release_lag_days: int,
    known_nonpublication_periods: set[str],
) -> tuple[list[dict[str, Any]], Counter[str], list[dict[str, Any]]]:
    groups = {
        pd.Timestamp(period): group.copy()
        for period, group in frame.groupby("period", sort=True)
    }
    earliest = (
        frame.groupby("period", as_index=False)["realtime_start"]
        .min()
        .sort_values("period")
    )
    rows: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    rejected_periods: list[dict[str, Any]] = []
    for candidate in earliest.itertuples(index=False):
        period = pd.Timestamp(candidate.period).to_period("M").to_timestamp()
        release_date = pd.Timestamp(candidate.realtime_start).normalize()
        next_month = period + pd.offsets.MonthBegin(1)
        period_end = period + pd.offsets.MonthEnd(1)
        lag_days = int((release_date - period_end).days)
        period_text = period.strftime("%Y-%m")
        prior_period = period - pd.offsets.MonthBegin(1)
        prior_period_text = prior_period.strftime("%Y-%m")

        # Governed official nonpublication evidence takes precedence over every
        # ALFRED row, including a later backfill that otherwise looks like a
        # plausible release.  The immediately following month is also unusable
        # because a coherent MoM target requires the unpublished prior period.
        if period_text in known_nonpublication_periods:
            rejected["period_officially_not_published"] += 1
            rejected_periods.append(
                {
                    "release": release,
                    "series_id": series_id,
                    "period": period_text,
                    "release_date": release_date.date().isoformat(),
                    "reason": "period_officially_not_published",
                }
            )
            continue
        if prior_period_text in known_nonpublication_periods:
            rejected["prior_period_officially_not_published"] += 1
            rejected_periods.append(
                {
                    "release": release,
                    "series_id": series_id,
                    "period": period_text,
                    "release_date": release_date.date().isoformat(),
                    "prior_period": prior_period_text,
                    "reason": "prior_period_officially_not_published",
                }
            )
            continue

        if release_date.to_period("M") != next_month.to_period("M"):
            rejected["not_immediately_next_calendar_month"] += 1
            continue
        if not min_release_lag_days <= lag_days <= max_release_lag_days:
            rejected["outside_release_lag_gate"] += 1
            continue

        prior_group = groups.get(prior_period)
        current_group = groups.get(period)
        if current_group is None or prior_group is None:
            raise CpiTargetHistoryError(
                f"plausible release {series_id}/{period:%Y-%m} lacks current/prior rows"
            )
        request_frame = pd.concat([prior_group, current_group], ignore_index=True)
        truth = reconstruct_release_target(
            request_frame,
            series_id=series_id,
            period=period,
            release_date=release_date,
            as_of=release_date,
        )
        if truth.get("status") != "ok":
            raise CpiTargetHistoryError(
                f"same-vintage reconstruction failed for {series_id}/{period:%Y-%m}: "
                f"{truth.get('reason')}"
            )
        provenance = truth.get("provenance")
        if not isinstance(provenance, Mapping):
            raise CpiTargetHistoryError(
                f"same-vintage provenance missing for {series_id}/{period:%Y-%m}"
            )
        if provenance.get("same_release_vintage") is not True:
            raise CpiTargetHistoryError(
                f"same-vintage assertion absent for {series_id}/{period:%Y-%m}"
            )

        rows.append(
            {
                "schema": TARGET_ROW_SCHEMA,
                "target_epoch": CANDIDATE_TARGET_EPOCH,
                "release": release,
                "series_id": series_id,
                "target_id": truth["target_id"],
                "period": truth["period"],
                "prior_period": truth["prior_period"],
                "release_date": truth["release_date"],
                "release_lag_days": lag_days,
                "target_kind": truth["target_kind"],
                "unit": truth["unit"],
                "latent_change": truth["latent_change"],
                "published_proxy_1dp": truth["published_proxy_1dp"],
                "published_precision": truth["published_precision"],
                "current_level": truth["current_level"],
                "prior_level_same_vintage": truth["prior_level_same_vintage"],
                "basis": "alfred_same_release_vintage",
                "same_release_vintage": True,
                "cross_vintage_fallback_used": False,
                "published_proxy_is_official_release": False,
                "source_artifact": {
                    "artifact_sha256": artifact["artifact_sha256"],
                    "artifact_bytes": artifact["artifact_bytes"],
                    "manifest_artifact_sha256": artifact["manifest_artifact_sha256"],
                },
                "provenance": dict(provenance),
                "display_only": True,
                "authority": False,
            }
        )
    return rows, rejected, rejected_periods


def _require_headline_core_alignment(targets: Sequence[Mapping[str, Any]]) -> None:
    identities: dict[str, set[tuple[str, str]]] = {
        release: set() for release in CPI_SERIES_BY_RELEASE
    }
    for row in targets:
        release = str(row.get("release"))
        if release in identities:
            identities[release].add(
                (str(row.get("period")), str(row.get("release_date")))
            )
    if identities["cpi_headline"] != identities["cpi_core"]:
        only_headline = sorted(identities["cpi_headline"] - identities["cpi_core"])[:5]
        only_core = sorted(identities["cpi_core"] - identities["cpi_headline"])[:5]
        raise CpiTargetHistoryError(
            "headline/core target histories are not period/release-date aligned: "
            f"headline_only={only_headline} core_only={only_core}"
        )


def _validate_history_payload(history: Mapping[str, Any]) -> str:
    if history.get("schema") != HISTORY_SCHEMA:
        raise CpiTruthParityError(f"history schema must be {HISTORY_SCHEMA!r}")
    if history.get("target_epoch") != CANDIDATE_TARGET_EPOCH:
        raise CpiTruthParityError("history target epoch is not the candidate epoch")
    if history.get("status") != "candidate":
        raise CpiTruthParityError("history is not in candidate status")
    targets = history.get("targets")
    if not isinstance(targets, list) or not targets:
        raise CpiTruthParityError("history has no targets")
    if history.get("history_hash") != f"sha256:{_payload_sha256(targets)}":
        raise CpiTruthParityError("history target payload hash mismatch")
    history_asof = _normalize_governed_timestamp(
        history.get("asof"),
        field="history asof",
        error_type=CpiTruthParityError,
    )
    candidate_data_asof = _normalize_governed_timestamp(
        history.get("candidate_data_asof"),
        field="history candidate_data_asof",
        error_type=CpiTruthParityError,
    )
    if history_asof != candidate_data_asof:
        raise CpiTruthParityError(
            "history asof must equal its ALFRED candidate_data_asof"
        )
    source_manifest = history.get("source_manifest")
    if not isinstance(source_manifest, Mapping):
        raise CpiTruthParityError("history source manifest binding is missing")
    bound_completed_at = _normalize_governed_timestamp(
        source_manifest.get("completed_at"),
        field="history source manifest completed_at",
        error_type=CpiTruthParityError,
    )
    if candidate_data_asof != bound_completed_at:
        raise CpiTruthParityError(
            "history candidate_data_asof does not match its bound ALFRED manifest"
        )
    return candidate_data_asof


def _load_preregistered_manifest(
    path: Path,
    *,
    logical_root: Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        payload = _read_json_mapping(path, kind="preregistered sample")
    except CpiTargetHistoryError as exc:
        raise CpiTruthParityError(str(exc)) from exc
    if payload.get("schema") != PREREGISTERED_SAMPLE_SCHEMA:
        raise CpiTruthParityError(
            f"preregistered sample schema must be {PREREGISTERED_SAMPLE_SCHEMA!r}"
        )
    declared_epoch = payload.get("candidate_target_epoch") or payload.get(
        "target_epoch"
    )
    if isinstance(declared_epoch, Mapping):
        declared_epoch = declared_epoch.get("name")
    if declared_epoch != CANDIDATE_TARGET_EPOCH:
        raise CpiTruthParityError(
            f"preregistered target epoch must be {CANDIDATE_TARGET_EPOCH!r}"
        )
    official_archive_epoch = payload.get("official_target_epoch")
    if not isinstance(official_archive_epoch, Mapping):
        raise CpiTruthParityError(
            "preregistered sample lacks its official archive observation epoch"
        )
    if (
        official_archive_epoch.get("target_epoch") != OFFICIAL_ARCHIVE_OBSERVATION_EPOCH
        or official_archive_epoch.get("status") != "withheld"
        or official_archive_epoch.get("first_print_status") != FIRST_PRINT_STATUS
    ):
        raise CpiTruthParityError(
            "preregistered official archive observation epoch is invalid"
        )
    frozen_at = _normalize_governed_timestamp(
        payload.get("frozen_at"),
        field="preregistered sample frozen_at",
        error_type=CpiTruthParityError,
    )
    receipt = {
        "path": _logical_path(path, logical_root),
        "schema": payload.get("schema"),
        "artifact_bytes": path.stat().st_size,
        "artifact_sha256": _sha256_file(path),
        "frozen_at": frozen_at,
    }
    return payload, receipt


def _verify_receipts_binding(
    prereg: Mapping[str, Any],
    receipt_path: Path,
    *,
    logical_root: Path | None,
) -> dict[str, Any]:
    if not receipt_path.is_file():
        raise CpiTruthParityError(f"official receipt file is missing: {receipt_path}")
    binding = prereg.get("official_receipts_binding") or prereg.get("official_receipts")
    if not isinstance(binding, Mapping):
        binding = {}
    expected_sha = (
        binding.get("sha256")
        or binding.get("artifact_sha256")
        or prereg.get("official_receipts_sha256")
    )
    expected_bytes = (
        binding.get("bytes")
        or binding.get("artifact_bytes")
        or prereg.get("official_receipts_bytes")
    )
    binding_declared = expected_sha is not None or expected_bytes is not None
    if binding_declared and (
        not isinstance(expected_sha, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha)
    ):
        raise CpiTruthParityError(
            "preregistered official-receipt aggregate has an invalid SHA-256 binding"
        )
    if binding_declared and (
        not isinstance(expected_bytes, int) or expected_bytes <= 0
    ):
        raise CpiTruthParityError(
            "preregistered official-receipt aggregate has an invalid byte binding"
        )
    recorded_path = binding.get("path")
    if recorded_path and Path(str(recorded_path)).name != receipt_path.name:
        raise CpiTruthParityError(
            "preregistered official-receipt basename does not match supplied file"
        )
    actual_sha = _sha256_file(receipt_path)
    actual_bytes = receipt_path.stat().st_size
    if binding_declared and (
        expected_sha != actual_sha or expected_bytes != actual_bytes
    ):
        raise CpiTruthParityError(
            "official receipt file no longer matches the preregistered byte binding"
        )
    return {
        "path": _logical_path(receipt_path, logical_root),
        "artifact_sha256": actual_sha,
        "artifact_bytes": actual_bytes,
        "aggregate_binding_verified": binding_declared,
        "binding_mode": (
            "aggregate_sha256_bytes_and_per_case_source"
            if binding_declared
            else "per_case_exact_source_receipts"
        ),
    }


def _load_and_validate_official_collection(
    path: Path,
    *,
    prereg: Mapping[str, Any],
    prereg_path: Path,
    receipts_path: Path,
    samples: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]],
    logical_root: Path | None,
) -> dict[str, Any]:
    try:
        payload = _read_json_mapping(
            path,
            kind="official CPI collection manifest",
        )
    except CpiTargetHistoryError as exc:
        raise CpiTruthParityError(str(exc)) from exc
    if payload.get("schema") != OFFICIAL_COLLECTION_MANIFEST_SCHEMA:
        raise CpiTruthParityError(
            "official collection manifest schema must be "
            f"{OFFICIAL_COLLECTION_MANIFEST_SCHEMA!r}"
        )
    if payload.get("status") != "complete":
        raise CpiTruthParityError("official collection manifest is not complete")
    completed_at = _normalize_governed_timestamp(
        payload.get("completed_at"),
        field="official collection manifest completed_at",
        error_type=CpiTruthParityError,
    )

    prereg_binding = payload.get("preregistered_sample")
    receipt_binding = payload.get("receipts")
    if not isinstance(prereg_binding, Mapping) or not isinstance(
        receipt_binding, Mapping
    ):
        raise CpiTruthParityError(
            "official collection manifest lacks prereg/receipt bindings"
        )
    _verify_declared_file_binding(
        prereg_binding,
        prereg_path,
        kind="preregistered sample",
    )
    _verify_declared_file_binding(
        receipt_binding,
        receipts_path,
        kind="official receipt aggregate",
    )
    declared_count = receipt_binding.get("count")
    if not isinstance(declared_count, int) or declared_count != len(receipts):
        raise CpiTruthParityError(
            "official collection receipt count does not match the aggregate"
        )

    collection_cases = payload.get("cases")
    if not isinstance(collection_cases, list) or len(collection_cases) != len(samples):
        raise CpiTruthParityError(
            "official collection cases do not exactly cover the preregistration"
        )
    sample_pairs: list[tuple[str, str]] = []
    for sample in samples:
        case_id = sample.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise CpiTruthParityError(
                f"preregistered case lacks case_id: {sample.get('period')}"
            )
        sample_pairs.append((case_id, str(sample["period"])))
    if len(set(sample_pairs)) != len(sample_pairs):
        raise CpiTruthParityError("preregistered case identities are duplicated")

    declared_pairs: list[tuple[str, str]] = []
    declared_receipt_ids: list[str] = []
    for case in collection_cases:
        if not isinstance(case, Mapping):
            raise CpiTruthParityError("official collection case is malformed")
        pair = (str(case.get("case_id") or ""), str(case.get("period") or ""))
        receipt_id = case.get("receipt_id")
        if not all(pair) or not isinstance(receipt_id, str) or not receipt_id:
            raise CpiTruthParityError(
                "official collection case lacks exact identity/receipt binding"
            )
        declared_pairs.append(pair)
        declared_receipt_ids.append(receipt_id)
    if len(set(declared_pairs)) != len(declared_pairs):
        raise CpiTruthParityError("official collection cases are duplicated")
    if declared_pairs != sample_pairs:
        raise CpiTruthParityError(
            "official collection cases are missing, extra, or reordered"
        )

    counts = payload.get("counts")
    published_count = sum(
        sample["classification"] != "explicit_gap" for sample in samples
    )
    gap_count = len(samples) - published_count
    if (
        not isinstance(counts, Mapping)
        or counts.get("published") != published_count
        or counts.get("not_published") != gap_count
        or not isinstance(counts.get("distinct_source_urls"), int)
        or counts.get("distinct_source_urls") <= 0
    ):
        raise CpiTruthParityError(
            "official collection manifest count census is inconsistent"
        )

    actual_receipt_ids = [str(receipt.get("receipt_id") or "") for receipt in receipts]
    actual_periods = [str(receipt.get("period") or "") for receipt in receipts]
    if (
        not all(actual_receipt_ids)
        or len(set(actual_receipt_ids)) != len(actual_receipt_ids)
        or declared_receipt_ids != actual_receipt_ids
        or [period for _, period in declared_pairs] != actual_periods
    ):
        raise CpiTruthParityError(
            "official receipt aggregate is not an exact one-per-case ordered corpus"
        )

    archive = payload.get("archive")
    if not isinstance(archive, Mapping) or not archive.get("path"):
        raise CpiTruthParityError(
            "official collection manifest lacks its retained archive path"
        )
    archive_root = _resolve_declared_path(
        str(archive["path"]),
        manifest_path=path,
        logical_root=logical_root,
    )
    if not archive_root.is_dir():
        raise CpiTruthParityError(
            f"official retained archive is missing: {archive_root}"
        )

    verified_documents: list[dict[str, Any]] = []
    for collection_case, receipt, sample in zip(
        collection_cases,
        receipts,
        samples,
        strict=True,
    ):
        raw = receipt.get("raw")
        if not isinstance(raw, Mapping) or raw.get("schema") != OFFICIAL_TRUTH_SCHEMA:
            raise CpiTruthParityError(
                f"official collection receipt payload is invalid: {receipt.get('period')}"
            )
        period = str(receipt.get("period") or "")
        _verify_official_receipt_identity(raw, period)
        if collection_case.get("truth_status") != raw.get(
            "status"
        ) or collection_case.get("publication_status") != (
            "not_published" if raw.get("status") == "not_published" else "published"
        ):
            raise CpiTruthParityError(
                f"official collection case status mismatch: {receipt.get('period')}"
            )
        source = raw.get("source")
        if not isinstance(source, Mapping):
            raise CpiTruthParityError(
                f"official receipt source is missing: {receipt.get('period')}"
            )
        document_sha = source.get("document_sha256")
        document_bytes = source.get("document_bytes")
        extension = source.get("document_extension")
        _require_sha256(
            document_sha,
            f"official document {receipt.get('period')} SHA-256",
        )
        _require_positive_bytes(
            document_bytes,
            f"official document {receipt.get('period')} bytes",
        )
        if not isinstance(extension, str) or not re.fullmatch(
            r"\.(?:html|xls|xlsx)", extension
        ):
            raise CpiTruthParityError(
                f"official document extension is unsafe: {receipt.get('period')}"
            )
        declared_source = collection_case.get("source")
        if not isinstance(declared_source, Mapping):
            raise CpiTruthParityError(
                f"official collection source binding is missing: {receipt.get('period')}"
            )
        expected_object = (
            Path("documents") / "sha256" / f"{document_sha}{extension}"
        ).as_posix()
        source_fields = {
            "url": source.get("url"),
            "member": source.get("member"),
            "transport_sha256": source.get("transport_sha256"),
            "transport_bytes": source.get("transport_bytes"),
            "document_sha256": document_sha,
            "document_bytes": document_bytes,
            "document_object": expected_object,
        }
        if any(
            declared_source.get(key) != value for key, value in source_fields.items()
        ):
            raise CpiTruthParityError(
                f"official collection source binding mismatch: {receipt.get('period')}"
            )
        object_path = archive_root / expected_object
        if not object_path.is_file():
            raise CpiTruthParityError(
                f"retained official document is missing: {object_path.name}"
            )
        if (
            object_path.stat().st_size != document_bytes
            or _sha256_file(object_path) != document_sha
        ):
            raise CpiTruthParityError(
                f"retained official document binding mismatch: {object_path.name}"
            )
        document_body = object_path.read_bytes()
        try:
            if raw.get("status") == "not_published":
                rebuilt = build_cpi_not_published_truth(
                    document_body,
                    case_id=str(sample.get("case_id") or ""),
                    source_id=str(sample.get("source_id") or ""),
                    period=period,
                    reason=str(sample.get("reason") or ""),
                    source_url=str(sample.get("release_page_url") or ""),
                    evidence_statement=str(sample.get("evidence_statement") or ""),
                ).receipt
            else:
                sources = prereg.get("sources")
                source_spec = (
                    sources.get(sample.get("source_id"))
                    if isinstance(sources, Mapping)
                    else None
                )
                if not isinstance(source_spec, Mapping):
                    raise CpiTruthParityError(
                        f"published case lacks a preregistered source: {period}"
                    )
                rebuilt = rebuild_cpi_official_truth_receipt(
                    document_body,
                    spec=CpiSourceSpec(
                        period=period,
                        release_date=str(sample.get("release_date") or ""),
                        url=str(source_spec.get("url") or ""),
                        member=(
                            str(sample["member"])
                            if sample.get("member") is not None
                            else None
                        ),
                    ),
                    transport_sha256=str(source_spec.get("container_sha256") or ""),
                    transport_bytes=source_spec.get("container_bytes"),
                )
        except CpiOfficialTruthError as exc:
            raise CpiTruthParityError(
                "retained official document cannot deterministically rebuild "
                f"the receipt for {period}: {exc}"
            ) from exc
        if dict(raw) != rebuilt:
            raise CpiTruthParityError(
                f"retained-document deterministic receipt rebuild mismatch for {period}"
            )
        verified_documents.append(
            {
                "period": receipt.get("period"),
                "path": _logical_path(object_path, logical_root),
                "artifact_sha256": document_sha,
                "artifact_bytes": document_bytes,
            }
        )

    return {
        "schema": payload["schema"],
        "status": payload["status"],
        "completed_at": completed_at,
        "path": _logical_path(path, logical_root),
        "artifact_sha256": _sha256_file(path),
        "artifact_bytes": path.stat().st_size,
        "preregistered_sample": {
            "path": _logical_path(prereg_path, logical_root),
            "sha256": prereg_binding.get("sha256"),
            "bytes": prereg_binding.get("bytes"),
        },
        "receipts": {
            "path": _logical_path(receipts_path, logical_root),
            "sha256": receipt_binding.get("sha256"),
            "bytes": receipt_binding.get("bytes"),
            "count": receipt_binding.get("count"),
        },
        "archive": {
            "path": _logical_path(archive_root, logical_root),
            "transport_retention": archive.get("transport_retention"),
            "document_retention": archive.get("document_retention"),
        },
        "case_receipt_ids": declared_receipt_ids,
        "counts": dict(counts),
        "cases": [dict(case) for case in collection_cases],
        "retained_documents_verified": len(verified_documents),
        "retained_documents": verified_documents,
        "deterministic_receipt_rebuild_verified": True,
        "deterministic_receipt_rebuild_verified_count": len(verified_documents),
        "receipts_binding_verified": True,
    }


def _verify_declared_file_binding(
    binding: Mapping[str, Any], path: Path, *, kind: str
) -> None:
    expected_sha = binding.get("sha256") or binding.get("artifact_sha256")
    expected_bytes = binding.get("bytes") or binding.get("artifact_bytes")
    _require_sha256(expected_sha, f"{kind} SHA-256")
    _require_positive_bytes(expected_bytes, f"{kind} bytes")
    recorded_path = binding.get("path")
    if recorded_path and Path(str(recorded_path)).name != path.name:
        raise CpiTruthParityError(f"{kind} path binding mismatch")
    if path.stat().st_size != expected_bytes or _sha256_file(path) != expected_sha:
        raise CpiTruthParityError(f"{kind} no longer matches collection manifest")


def _resolve_declared_path(
    declared: str,
    *,
    manifest_path: Path,
    logical_root: Path | None,
) -> Path:
    raw = Path(declared)
    if raw.is_absolute():
        return raw
    candidates = []
    if logical_root is not None:
        candidates.append(logical_root / raw)
    candidates.extend((manifest_path.parent / raw, manifest_path.parent / raw.name))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _normalize_preregistered_samples(
    prereg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    raw_samples = prereg.get("samples") or prereg.get("cases") or prereg.get("sample")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise CpiTruthParityError("preregistered sample manifest has no sample cases")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_samples:
        if not isinstance(raw, Mapping):
            raise CpiTruthParityError("every preregistered sample must be an object")
        period = _coerce_month_text(
            raw.get("period") or raw.get("reference_period"),
            "preregistered period",
        )
        if period in seen:
            raise CpiTruthParityError(f"duplicate preregistered period: {period}")
        seen.add(period)

        publication_status = raw.get("publication_status")
        classification = raw.get("classification") or raw.get("stratum")
        if raw.get("explicit_gap") is True or publication_status == "not_published":
            classification = "explicit_gap"
        if classification is None:
            classification = "annual_revision" if period.endswith("-01") else "ordinary"
        classification = str(classification)
        if classification not in _ALLOWED_CLASSIFICATIONS:
            raise CpiTruthParityError(
                f"invalid preregistered classification {classification!r}"
            )
        if classification == "annual_revision" and not period.endswith("-01"):
            raise CpiTruthParityError(
                f"annual_revision sample must be a January reference month: {period}"
            )
        if classification == "ordinary" and period.endswith("-01"):
            raise CpiTruthParityError(
                f"January reference month must be classified annual_revision: {period}"
            )
        reason = raw.get("reason") or raw.get("gap_reason")
        if classification == "explicit_gap" and not str(reason or "").strip():
            raise CpiTruthParityError(
                f"explicit_gap sample requires a reason: {period}"
            )
        release_date = _optional_iso_date(raw.get("release_date"))
        if publication_status not in (None, "published", "not_published"):
            raise CpiTruthParityError(
                f"invalid publication_status for {period}: {publication_status!r}"
            )
        if publication_status == "published" and classification == "explicit_gap":
            raise CpiTruthParityError(
                f"published case cannot be classified explicit_gap: {period}"
            )
        if publication_status == "published" and release_date is None:
            raise CpiTruthParityError(
                f"published preregistered case lacks release_date: {period}"
            )
        if publication_status == "not_published" and release_date is not None:
            raise CpiTruthParityError(
                f"not_published preregistered case must not have release_date: {period}"
            )
        normalized.append(
            {
                "period": period,
                "release_date": release_date,
                "classification": classification,
                "reason": str(reason).strip() if reason else None,
                "case_id": raw.get("case_id") or raw.get("id"),
                "publication_status": publication_status,
                "source_id": raw.get("source_id"),
                "member": raw.get("member"),
                "member_sha256": raw.get("member_sha256"),
                "member_bytes": raw.get("member_bytes"),
                "release_page_url": raw.get("release_page_url"),
                "evidence_statement": raw.get("evidence_statement"),
                "evidence_sha256": raw.get("evidence_sha256"),
                "evidence_bytes": raw.get("evidence_bytes"),
                "declaration_sha256": raw.get("declaration_sha256"),
                "declaration_bytes": raw.get("declaration_bytes"),
                "receipt_id": raw.get("receipt_id"),
                "source_sha256": raw.get("source_sha256"),
            }
        )
    return sorted(normalized, key=lambda item: item["period"])


def _validate_preregistered_gate(
    prereg: Mapping[str, Any], samples: Sequence[Mapping[str, Any]]
) -> None:
    gate = prereg.get("gate")
    if not isinstance(gate, Mapping):
        raise CpiTruthParityError("preregistered sample has no declared parity gate")

    counts = Counter(str(sample["classification"]) for sample in samples)
    published = len(samples) - counts["explicit_gap"]
    expected_counts = {
        "published_cases_required": published,
        "explicit_gap_cases_required": counts["explicit_gap"],
        "annual_revision_cases_required": counts["annual_revision"],
        "ordinary_cases_required": counts["ordinary"],
    }
    for field, actual in expected_counts.items():
        expected = gate.get(field)
        if not isinstance(expected, int) or expected != actual:
            raise CpiTruthParityError(
                f"preregistered gate count mismatch for {field}: "
                f"declared={expected!r} actual={actual}"
            )
    for field in (
        "headline_mom_exact_tolerance_pp",
        "core_mom_exact_tolerance_pp",
    ):
        value = gate.get(field)
        if not isinstance(value, (int, float)) or float(value) != 0.0:
            raise CpiTruthParityError(
                f"preregistered exact parity gate must set {field}=0.0"
            )
    if gate.get("source_hash_and_length_required") is not True:
        raise CpiTruthParityError(
            "preregistered parity gate must require source hashes and lengths"
        )
    if gate.get("manifest_bound_alfred_inputs_required") is not True:
        raise CpiTruthParityError(
            "preregistered parity gate must require manifest-bound ALFRED inputs"
        )
    if gate.get("missing_or_unadjudicated_mismatch_policy") != "fail_closed":
        raise CpiTruthParityError(
            "preregistered parity gate must fail closed on missing/mismatch evidence"
        )


def _validate_case_receipt_bindings(
    prereg: Mapping[str, Any],
    sample: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    *,
    period_receipts: Sequence[Mapping[str, Any]],
    aggregate_binding_verified: bool,
) -> bool:
    """Bind one sample to either exact source receipts or a frozen aggregate."""

    period = str(sample["period"])
    if sample["classification"] == "explicit_gap":
        sources = prereg.get("sources")
        source_spec = (
            sources.get(sample.get("source_id"))
            if isinstance(sources, Mapping)
            else None
        )
        if not isinstance(source_spec, Mapping):
            raise CpiTruthParityError(
                f"explicit gap lacks a bound source object: {period}"
            )
        if len(period_receipts) != 1 or len(receipts) != 1:
            raise CpiTruthParityError(
                f"explicit gap {period} must resolve to exactly one pinned receipt; "
                f"period_receipts={len(period_receipts)} pinned_matches={len(receipts)}"
            )
        _verify_nonpublication_receipt(sample, receipts[0], source_spec)
        return True

    source_id = sample.get("source_id")
    sources = prereg.get("sources")
    source_spec = (
        sources.get(source_id)
        if isinstance(sources, Mapping) and source_id is not None
        else None
    )
    if source_spec is None:
        if aggregate_binding_verified:
            return False
        raise CpiTruthParityError(
            f"published case {period} lacks a preregistered exact source binding"
        )
    if not isinstance(source_spec, Mapping):
        raise CpiTruthParityError(f"preregistered source {source_id!r} is malformed")
    if len(receipts) != 1:
        raise CpiTruthParityError(
            f"published case {period} must resolve to exactly one official receipt; "
            f"found={len(receipts)}"
        )

    receipt = receipts[0]
    raw = receipt.get("raw")
    if not isinstance(raw, Mapping):
        raise CpiTruthParityError(f"official receipt payload is missing for {period}")
    _verify_official_receipt_identity(raw, period)
    source = receipt.get("source")
    if not isinstance(source, Mapping):
        raise CpiTruthParityError(f"official receipt source is missing for {period}")

    expected_transport_sha = source_spec.get("container_sha256")
    expected_transport_bytes = source_spec.get("container_bytes")
    _require_sha256(expected_transport_sha, f"source {source_id} container_sha256")
    _require_positive_bytes(
        expected_transport_bytes,
        f"source {source_id} container_bytes",
    )
    if source.get("url") != source_spec.get("url"):
        raise CpiTruthParityError(f"official source URL mismatch for {period}")
    if source.get("transport_sha256") != expected_transport_sha:
        raise CpiTruthParityError(f"official transport SHA-256 mismatch for {period}")
    if source.get("transport_bytes") != expected_transport_bytes:
        raise CpiTruthParityError(f"official transport byte mismatch for {period}")

    expected_document_sha = sample.get("member_sha256")
    expected_document_bytes = sample.get("member_bytes")
    _require_sha256(expected_document_sha, f"case {period} member_sha256")
    _require_positive_bytes(expected_document_bytes, f"case {period} member_bytes")
    if source.get("member") != sample.get("member"):
        raise CpiTruthParityError(f"official archive member mismatch for {period}")
    if source.get("document_sha256") != expected_document_sha:
        raise CpiTruthParityError(f"official document SHA-256 mismatch for {period}")
    if source.get("document_bytes") != expected_document_bytes:
        raise CpiTruthParityError(f"official document byte mismatch for {period}")
    return True


def _verify_official_receipt_identity(receipt: Mapping[str, Any], period: str) -> None:
    if receipt.get("schema") != OFFICIAL_TRUTH_SCHEMA:
        raise CpiTruthParityError(
            f"official receipt schema mismatch for {period}: {receipt.get('schema')!r}"
        )
    expected_profile = (
        OFFICIAL_NONPUBLICATION_INTEGRITY_PROFILE
        if receipt.get("status") == "not_published"
        else OFFICIAL_TRUTH_INTEGRITY_PROFILE
    )
    if receipt.get("integrity_profile") != expected_profile:
        raise CpiTruthParityError(
            f"official receipt integrity profile mismatch for {period}"
        )
    if receipt.get("sequence") != ARCHIVE_SEQUENCE:
        raise CpiTruthParityError(
            f"official receipt is not an archived release edition for {period}"
        )
    if receipt.get("first_print_status") != FIRST_PRINT_STATUS:
        raise CpiTruthParityError(
            f"official archive receipt overstates first-print status for {period}"
        )
    if receipt.get("authority") is not False:
        raise CpiTruthParityError(
            f"official archive receipt authority must be false for {period}"
        )
    if receipt.get("display_only") is not True:
        raise CpiTruthParityError(
            f"official archive receipt display_only must be true for {period}"
        )
    expected_basis = (
        ARCHIVE_NONPUBLICATION_ACTUAL_BASIS
        if receipt.get("status") == "not_published"
        else ARCHIVED_TABLE1_ACTUAL_BASIS
    )
    if receipt.get("actual_basis") != expected_basis:
        raise CpiTruthParityError(
            f"official archive receipt actual basis mismatch for {period}"
        )
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id.startswith(
        "cpi_official_truth:"
    ):
        raise CpiTruthParityError(f"official receipt id is invalid for {period}")
    unsigned = dict(receipt)
    unsigned.pop("receipt_id", None)
    expected_id = (
        "cpi_official_truth:"
        + hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()[:32]
    )
    if receipt_id != expected_id:
        raise CpiTruthParityError(
            f"official receipt payload/identity mismatch for {period}"
        )


def _verify_nonpublication_receipt(
    sample: Mapping[str, Any],
    receipt: Mapping[str, Any],
    source_spec: Mapping[str, Any],
) -> None:
    period = str(sample["period"])
    raw = receipt.get("raw")
    if not isinstance(raw, Mapping):
        raise CpiTruthParityError(
            f"nonpublication receipt payload is missing for {period}"
        )
    _verify_official_receipt_identity(raw, period)
    if raw.get("status") != "not_published" or raw.get("release_date") is not None:
        raise CpiTruthParityError(
            f"explicit-gap receipt is not a nonpublication receipt for {period}"
        )
    exact_fields = {
        "case_id": sample.get("case_id"),
        "source_id": sample.get("source_id"),
        "period": period,
        "reason": sample.get("reason"),
        "receipt_id": sample.get("receipt_id"),
        "source_sha256": sample.get("source_sha256"),
    }
    for field, expected in exact_fields.items():
        if expected in (None, "") or raw.get(field) != expected:
            raise CpiTruthParityError(
                f"nonpublication receipt {field} mismatch for {period}"
            )
    if raw.get("targets") != [] or raw.get("metrics") != {}:
        raise CpiTruthParityError(
            f"nonpublication receipt unexpectedly contains metrics for {period}"
        )

    source = raw.get("source")
    if not isinstance(source, Mapping):
        raise CpiTruthParityError(
            f"nonpublication receipt source is missing for {period}"
        )
    source_url = sample.get("release_page_url")
    if (
        not isinstance(source_url, str)
        or source.get("url") != source_url
        or source_spec.get("url") != source_url
        or source.get("source_id") != sample.get("source_id")
        or source.get("publisher") != source_spec.get("publisher")
        or source.get("host") != source_spec.get("host")
    ):
        raise CpiTruthParityError(
            f"nonpublication receipt source URL mismatch for {period}"
        )
    declaration = {
        "schema": OFFICIAL_NONPUBLICATION_DECLARATION_SCHEMA,
        "case_id": sample.get("case_id"),
        "source_id": sample.get("source_id"),
        "period": period,
        "reason": sample.get("reason"),
        "source_url": source_url,
        "evidence_statement": sample.get("evidence_statement"),
        "source_sha256": sample.get("source_sha256"),
        "source_bytes": sample.get("evidence_bytes"),
    }
    declaration_body = canonical_json_bytes(declaration)
    declaration_sha = hashlib.sha256(declaration_body).hexdigest()
    expected_declaration_sha = sample.get("declaration_sha256")
    expected_declaration_bytes = sample.get("declaration_bytes")
    expected_evidence_sha = sample.get("evidence_sha256")
    expected_evidence_bytes = sample.get("evidence_bytes")
    _require_sha256(expected_declaration_sha, f"gap {period} declaration_sha256")
    _require_positive_bytes(
        expected_declaration_bytes,
        f"gap {period} declaration_bytes",
    )
    _require_sha256(expected_evidence_sha, f"gap {period} evidence_sha256")
    _require_positive_bytes(expected_evidence_bytes, f"gap {period} evidence_bytes")
    if (
        declaration_sha != expected_declaration_sha
        or len(declaration_body) != expected_declaration_bytes
        or sample.get("source_sha256") != expected_evidence_sha
        or raw.get("source_sha256") != expected_evidence_sha
        or source.get("transport_sha256") != expected_evidence_sha
        or source.get("transport_bytes") != expected_evidence_bytes
        or source.get("document_sha256") != expected_evidence_sha
        or source.get("document_bytes") != expected_evidence_bytes
        or source.get("evidence_statement") != sample.get("evidence_statement")
        or source_spec.get("container_sha256") != expected_evidence_sha
        or source_spec.get("container_bytes") != expected_evidence_bytes
        or source_spec.get("content_type") != "text/html"
        or source.get("declaration_schema")
        != OFFICIAL_NONPUBLICATION_DECLARATION_SCHEMA
        or source.get("declaration_sha256") != declaration_sha
        or source.get("declaration_bytes") != len(declaration_body)
    ):
        raise CpiTruthParityError(
            f"nonpublication declaration binding mismatch for {period}"
        )


def _require_sha256(value: Any, name: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise CpiTruthParityError(f"{name} is not an exact SHA-256")


def _require_positive_bytes(value: Any, name: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise CpiTruthParityError(f"{name} is not a positive byte count")


def _matching_receipts(
    receipts: Sequence[Mapping[str, Any]], sample: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    matches = [row for row in receipts if row.get("period") == sample["period"]]
    release_date = sample.get("release_date")
    if release_date:
        matches = [row for row in matches if row.get("release_date") == release_date]
    receipt_id = sample.get("receipt_id")
    if receipt_id:
        matches = [row for row in matches if row.get("receipt_id") == receipt_id]
    source_sha = sample.get("source_sha256")
    if source_sha:
        matches = [row for row in matches if row.get("source_sha256") == source_sha]
    return matches


def _resolve_official_metric(
    receipts: Sequence[Mapping[str, Any]],
    release: str,
    sample: Mapping[str, Any],
) -> tuple[float, dict[str, Any]]:
    values: list[float] = []
    receipt_ids: set[str] = set()
    source_shas: set[str] = set()
    for receipt in receipts:
        metrics = receipt.get("metrics")
        if not isinstance(metrics, Mapping) or release not in metrics:
            continue
        values.append(float(metrics[release]))
        if receipt.get("receipt_id"):
            receipt_ids.add(str(receipt["receipt_id"]))
        if receipt.get("source_sha256"):
            source_shas.add(str(receipt["source_sha256"]))
    if not values:
        raise CpiTruthParityError(
            f"no bound official metric for {release}/{sample['period']}"
        )
    unique = {float(value) for value in values}
    if len(unique) != 1:
        raise CpiTruthParityError(
            f"conflicting official metrics for {release}/{sample['period']}: "
            f"{sorted(unique)}"
        )
    return next(iter(unique)), {
        "receipt_ids": sorted(receipt_ids),
        "source_sha256": sorted(source_shas),
    }


def _extract_period(obj: Mapping[str, Any]) -> str:
    value = (
        obj.get("period")
        or obj.get("reference_period")
        or obj.get("official_reference_period")
        or _nested_get(obj, "actual", "reference_period")
        or _nested_get(obj, "metrics", "reference_period")
        or _nested_get(obj, "table1", "reference_period")
    )
    return _coerce_month_text(value, "official reference period")


def _extract_metrics(obj: Mapping[str, Any]) -> dict[str, float]:
    containers: list[Mapping[str, Any]] = []
    for candidate in (
        obj.get("metrics"),
        obj.get("actual"),
        obj.get("table1"),
        _nested_get(obj, "table1", "metrics"),
        _nested_get(obj, "actual", "metrics"),
        obj,
    ):
        if isinstance(candidate, Mapping):
            containers.append(candidate)

    metrics: dict[str, float] = {}
    raw_targets = obj.get("targets")
    if isinstance(raw_targets, list):
        for target in raw_targets:
            if not isinstance(target, Mapping):
                raise CpiTruthParityError("official receipt target is not an object")
            release = target.get("release") or target.get("release_type")
            if release not in CPI_SERIES_BY_RELEASE:
                continue
            raw_value = target.get("mom")
            if raw_value is None:
                raw_value = target.get("actual")
            if raw_value is None:
                raw_value = target.get("value")
            if raw_value is None:
                raise CpiTruthParityError(
                    f"official receipt target {release} has no MoM value"
                )
            value = _coerce_metric_value(raw_value, f"targets.{release}.mom")
            if release in metrics and metrics[release] != value:
                raise CpiTruthParityError(
                    f"receipt contains conflicting targets for {release}"
                )
            metrics[str(release)] = value

    for release, aliases in (
        ("cpi_headline", _HEADLINE_ALIASES),
        ("cpi_core", _CORE_ALIASES),
    ):
        found: list[float] = []
        for container in containers:
            for alias in aliases:
                if alias in container:
                    found.append(_coerce_metric_value(container[alias], alias))
        direct_release = obj.get("release") or obj.get("release_type")
        if (
            direct_release == release
            and "actual" in obj
            and not isinstance(obj.get("actual"), Mapping)
        ):
            found.append(_coerce_metric_value(obj["actual"], "actual"))
        if found:
            unique = {float(value) for value in found}
            if len(unique) != 1:
                raise CpiTruthParityError(
                    f"receipt contains conflicting aliases for {release}: {sorted(unique)}"
                )
            value = next(iter(unique))
            if release in metrics and metrics[release] != value:
                raise CpiTruthParityError(
                    f"receipt target/metric values conflict for {release}"
                )
            metrics[release] = value
    return metrics


def _coerce_metric_value(value: Any, name: str) -> float:
    if isinstance(value, Mapping):
        for key in ("value", "actual", "percent", "mom"):
            if key in value:
                value = value[key]
                break
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise CpiTruthParityError(f"official metric {name!r} is not numeric") from exc
    if not math.isfinite(numeric):
        raise CpiTruthParityError(f"official metric {name!r} is not finite")
    return numeric


def _read_json_records(path: Path, *, kind: str) -> list[Mapping[str, Any]]:
    if not path.is_file():
        raise CpiTruthParityError(f"{kind} file is missing: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise CpiTruthParityError(f"{kind} file is empty: {path}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        records: list[Mapping[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CpiTruthParityError(
                    f"invalid JSONL in {kind} at line {line_number}"
                ) from exc
            if not isinstance(item, Mapping):
                raise CpiTruthParityError(f"{kind} line {line_number} is not an object")
            records.append(item)
        if not records:
            raise CpiTruthParityError(f"{kind} contains no records")
        return records

    if isinstance(parsed, list):
        records = parsed
    elif isinstance(parsed, Mapping):
        nested = parsed.get("receipts") or parsed.get("rows") or parsed.get("records")
        records = nested if isinstance(nested, list) else [parsed]
    else:
        raise CpiTruthParityError(f"{kind} must contain objects")
    if not records or not all(isinstance(item, Mapping) for item in records):
        raise CpiTruthParityError(f"{kind} contains malformed records")
    return list(records)


def _read_json_mapping(path: Path, *, kind: str) -> dict[str, Any]:
    if not path.is_file():
        raise CpiTargetHistoryError(f"{kind} is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CpiTargetHistoryError(f"{kind} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CpiTargetHistoryError(f"{kind} must be a JSON object")
    return payload


def _coerce_month_text(value: Any, name: str) -> str:
    if value is None:
        raise CpiTruthParityError(f"{name} is missing")
    text = str(value).strip()
    match = _MONTH_PREFIX.match(text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        raise CpiTruthParityError(f"{name} is not a valid month: {value!r}")
    stamp = pd.Timestamp(parsed)
    return f"{stamp.year:04d}-{stamp.month:02d}"


def _optional_iso_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise CpiTruthParityError(f"invalid release date: {value!r}")
    return pd.Timestamp(parsed).date().isoformat()


def _nested_get(obj: Mapping[str, Any], *keys: str) -> Any:
    value: Any = obj
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _normalize_governed_timestamp(
    value: Any,
    *,
    field: str,
    error_type: type[CpiTargetHistoryError],
) -> str:
    """Validate one source clock and return a canonical UTC timestamp."""

    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field} must be a timezone-aware ISO-8601 timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise error_type(
            f"{field} must be a timezone-aware ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise error_type(f"{field} must include an explicit timezone offset")
    return parsed.astimezone(timezone.utc).isoformat()


def _latest_governed_timestamp(*values: str) -> str:
    """Return the latest already-validated source clock without a wall clock."""

    if not values:
        raise CpiTruthParityError("evidence availability requires source clocks")
    parsed = [datetime.fromisoformat(value) for value in values]
    return max(parsed).astimezone(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _payload_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "CANDIDATE_TARGET_EPOCH",
    "CPI_SERIES_BY_RELEASE",
    "HISTORY_SCHEMA",
    "PARITY_SCHEMA",
    "WITHHELD_OFFICIAL_TARGET_EPOCH",
    "CpiTargetHistoryError",
    "CpiTruthParityError",
    "build_cpi_target_history",
    "default_collector_manifest_path",
    "default_cpi_vintage_paths",
    "evaluate_preregistered_parity",
    "load_official_table1_receipts",
]
