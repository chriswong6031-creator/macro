"""Canonical official-release actual receipts for Release Radar.

The live publication watcher already extracts deterministic facts from BLS,
BEA, and DOL documents.  This module normalizes those facts into the exact
forecast target units and an immutable, keep-first receipt contract.  It never
derives a CPI, PPI, PCE, or payroll print by differencing unrelated vintages.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_OFFICIAL_HOSTS = ("bls.gov", "bea.gov", "dol.gov")

# event type -> [(release id, metric key, metric id, forecast unit, scale)]
_TARGETS: dict[str, tuple[tuple[str, str, str, str, float], ...]] = {
    "CPI": (
        ("cpi_headline", "headline_mom", "cpi_headline_mom", "percent", 1.0),
        ("cpi_core", "core_mom", "cpi_core_mom", "percent", 1.0),
    ),
    "PPI": (
        ("ppi_finaldemand", "headline_mom", "ppi_headline_mom", "percent", 1.0),
    ),
    "PCE": (
        ("pce_headline", "headline_mom", "pce_headline_mom", "percent", 1.0),
        ("pce_core", "core_mom", "pce_core_mom", "percent", 1.0),
    ),
    "NFP": (
        ("nfp", "payroll_change", "nfp_payroll_change", "thousands", 1.0 / 1000.0),
    ),
    "CLAIMS": (
        ("claims", "initial_claims", "claims_initial", "thousands", 1.0 / 1000.0),
    ),
}


def _monthly_period(release_day: date) -> str:
    year, month = release_day.year, release_day.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}-{month:02d}"


def _official_url(value: Any) -> bool:
    try:
        parsed = urlparse(str(value))
        host = (parsed.hostname or "").lower().rstrip(".")
        return parsed.scheme == "https" and any(
            host == allowed or host.endswith("." + allowed)
            for allowed in _OFFICIAL_HOSTS
        )
    except Exception:
        return False


def _sha256(value: Any) -> str | None:
    text = str(value or "").lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        return None
    return text


def _receipt_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "official_actual:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def normalize_publication(publication: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize one verified live-publication row; fail closed to ``[]``.

    The target period is resolved from the scheduled official event date rather
    than free-form parser prose.  This prevents a malformed reference string
    (for example, ``"The"``) from being attached to a payroll score.
    """
    if not isinstance(publication, dict):
        return []
    event_type = str(publication.get("type") or "").upper()
    specs = _TARGETS.get(event_type)
    actual = publication.get("actual")
    if not specs or not isinstance(actual, dict):
        return []
    if publication.get("data_ready") is not True:
        return []

    source_url = publication.get("source_url") or actual.get("source_url")
    source_sha = _sha256(
        publication.get("source_sha256") or publication.get("content_sha256")
    )
    if not _official_url(source_url) or source_sha is None:
        return []
    try:
        release_day = date.fromisoformat(str(publication.get("date"))[:10])
    except (TypeError, ValueError):
        return []

    period = release_day.isoformat() if event_type == "CLAIMS" else _monthly_period(release_day)
    observed_at = (
        publication.get("first_seen_at")
        or publication.get("detected_at")
        or publication.get("observed_at")
        or publication.get("verified_at")
    )
    if not observed_at:
        return []
    parser = publication.get("parser") if isinstance(publication.get("parser"), dict) else {}

    rows: list[dict[str, Any]] = []
    for release, value_key, metric_id, unit, scale in specs:
        raw_value = actual.get(value_key)
        try:
            raw_float = float(raw_value)
            value = raw_float * scale
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue

        identity = {
            "release": release,
            "period": period,
            "sequence": "first",
            "metric_id": metric_id,
            "value": value,
            "source_sha256": source_sha,
        }
        rows.append(
            {
                "schema": "release_actual.v1",
                "row_type": "actual",
                "receipt_id": _receipt_id(identity),
                "release": release,
                "period": period,
                "release_date": release_day.isoformat(),
                "sequence": "first",
                "exact_target_id": metric_id + "_printed_first",
                "metric_id": metric_id,
                "actual": round(value, 6),
                "actual_raw": raw_float,
                "unit": unit,
                "published_precision": 0 if event_type in ("NFP", "CLAIMS") else 1,
                "actual_basis": "official_published_metric",
                "actual_source": "official_release_document",
                "source_url": str(source_url),
                "source_sha256": source_sha,
                "publisher": publication.get("publisher"),
                "source_id": publication.get("source_id"),
                "source_released_at": publication.get("source_released_at"),
                "observed_at": observed_at,
                "verified_at": publication.get("verified_at"),
                "parser_name": parser.get("name"),
                "parser_version": parser.get("version"),
                "official_reference_period": actual.get("reference_period"),
                "period_resolution": (
                    "release_event_date" if event_type == "CLAIMS"
                    else "release_event_month_minus_one"
                ),
                "display_only": True,
                "authority": False,
            }
        )
    return rows


def receipts_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract de-duplicated official receipts from ``release_publications.v2``."""
    if not isinstance(payload, dict) or payload.get("schema") != "release_publications.v2":
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for publication in payload.get("publications") or []:
        for row in normalize_publication(publication):
            receipt_id = row["receipt_id"]
            if receipt_id not in seen:
                rows.append(row)
                seen.add(receipt_id)
    return rows


def load_actual_ledger(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append(row)
                except (ValueError, TypeError):
                    continue
    except OSError:
        pass
    return rows


def reconcile_receipts(
    payload: dict[str, Any], existing: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return only novel keep-first receipts.

    A later document hash for the same target is retained as an explicit
    ``correction_candidate`` rather than replacing the first receipt.  It is not
    eligible for automatic scoring until a human or a deterministic correction
    policy adjudicates it.
    """
    existing_rows = [row for row in existing if isinstance(row, dict)]
    existing_ids = {str(row.get("receipt_id")) for row in existing_rows}
    first_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in existing_rows:
        if row.get("row_type") == "actual":
            key = (str(row.get("release")), str(row.get("period")), str(row.get("sequence") or "first"))
            first_by_key.setdefault(key, row)

    novel: list[dict[str, Any]] = []
    for row in receipts_from_payload(payload):
        if row["receipt_id"] in existing_ids:
            continue
        key = (row["release"], row["period"], row["sequence"])
        prior = first_by_key.get(key)
        if prior is not None:
            row = {
                **row,
                "row_type": "correction_candidate",
                "supersedes_receipt_id": prior.get("receipt_id"),
                "automatic_scoring_eligible": False,
            }
        else:
            first_by_key[key] = row
        novel.append(row)
        existing_ids.add(row["receipt_id"])
    return novel


def canonical_actual(
    rows: Iterable[dict[str, Any]], release: str, period: str
) -> dict[str, Any] | None:
    """Return the keep-first canonical official actual for a target."""
    candidates = [
        row for row in rows
        if isinstance(row, dict)
        and row.get("row_type") == "actual"
        and row.get("release") == release
        and row.get("period") == period
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: str(row.get("observed_at") or "9999"))
