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
import re
from collections.abc import Iterable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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

_SOURCE_CONTRACTS: dict[str, dict[str, Any]] = {
    "CPI": {
        "host": "bls.gov",
        "publisher": "U.S. Bureau of Labor Statistics",
        "source_id": "bls_cpi",
        "parser": ("cpi", 1),
        "raw_unit": "percent",
    },
    "PPI": {
        "host": "bls.gov",
        "publisher": "U.S. Bureau of Labor Statistics",
        "source_id": "bls_ppi",
        "parser": ("ppi", 1),
        "raw_unit": "percent",
    },
    "NFP": {
        "host": "bls.gov",
        "publisher": "U.S. Bureau of Labor Statistics",
        "source_id": "bls_employment",
        "parser": ("nfp", 1),
        "raw_unit": "persons",
    },
    "PCE": {
        "host": "bea.gov",
        "publisher": "U.S. Bureau of Economic Analysis",
        "source_id": "bea_pce",
        "parser": ("pce", 1),
        "raw_unit": "percent",
    },
    "CLAIMS": {
        "host": "dol.gov",
        "publisher": "U.S. Department of Labor",
        "source_id": "dol_claims",
        "parser": ("claims", 1),
        "raw_unit": "persons",
    },
}

_EVENT_BY_RELEASE = {
    release: event_type
    for event_type, specs in _TARGETS.items()
    for release, _value_key, _metric_id, _unit, _scale in specs
}
_SPEC_BY_RELEASE = {
    release: (metric_id, unit, scale)
    for specs in _TARGETS.values()
    for release, _value_key, metric_id, unit, scale in specs
}

_MONTHS = {
    name: month
    for month, names in enumerate(
        (
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}

_ISO_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
_EXPLICIT_REFERENCE_FIELDS = (
    "scheduled_reference_period",
    "expected_reference_period",
    "forecast_period",
    "reference_period",
)
_DEFECT_SIDECAR_SCHEMA = "official_actual_defects.v1"
_SOURCE_BINDING_DEFECT = "known_source_binding_defect"
_DEFECT_SIDECAR_INVALID = "official_actual_defect_sidecar_invalid"
DEFAULT_DEFECTS_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "release_forecast"
    / "official_actual_defects.json"
)


def _monthly_period(release_day: date) -> str:
    year, month = release_day.year, release_day.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}-{month:02d}"


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_iso_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not _ISO_TIMESTAMP.fullmatch(value):
        return None
    token = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _official_url(value: Any, allowed_host: str) -> bool:
    try:
        parsed = urlparse(str(value))
        host = (parsed.hostname or "").lower().rstrip(".")
        return parsed.scheme == "https" and (
            host == allowed_host or host.endswith("." + allowed_host)
        )
    except ValueError:
        return False


def _parse_month_reference(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = " ".join(value.strip().split())
    if re.fullmatch(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])", token):
        return token
    match = re.fullmatch(
        r"([A-Za-z]+)\s*,?\s+((?:19|20)\d{2})",
        token,
    )
    if not match:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    return f"{int(match.group(2)):04d}-{month:02d}"


def _parse_week_reference(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    token = " ".join(value.strip().split())
    iso_day = _parse_iso_date(token)
    if iso_day is not None:
        return iso_day
    match = re.fullmatch(
        r"([A-Za-z]+)\s+(\d{1,2}),\s*((?:19|20)\d{2})",
        token,
    )
    if not match:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(2)))
    except ValueError:
        return None


def _source_compatible(event_type: str, value: dict[str, Any], source_url: Any) -> bool:
    contract = _SOURCE_CONTRACTS[event_type]
    parser = value.get("parser") if isinstance(value.get("parser"), dict) else {}
    expected_parser, expected_version = contract["parser"]
    return bool(
        _official_url(source_url, str(contract["host"]))
        and value.get("publisher") == contract["publisher"]
        and value.get("source_id") == contract["source_id"]
        and parser.get("name") == expected_parser
        and type(parser.get("version")) is int
        and parser.get("version") == expected_version
    )


def _resolve_reference_period(
    event_type: str,
    publication: dict[str, Any],
    actual: dict[str, Any],
    release_day: date,
) -> tuple[str, str] | None:
    """Return the scoring target period only after parser/source-period agreement."""
    raw_actual_period = actual.get("reference_period")
    explicit_periods = [
        publication.get(field)
        for field in _EXPLICIT_REFERENCE_FIELDS
        if publication.get(field) not in (None, "")
    ]

    if event_type == "CLAIMS":
        parsed = _parse_week_reference(raw_actual_period)
        if parsed is None:
            return None
        for raw_expected in explicit_periods:
            expected = _parse_week_reference(raw_expected)
            if expected is None or expected != parsed:
                return None
        lag_days = (release_day - parsed).days
        if lag_days < 0 or lag_days > 7:
            return None
        return release_day.isoformat(), "release_event_date_with_validated_reference_week"

    parsed = _parse_month_reference(raw_actual_period)
    if parsed is None:
        return None
    for raw_expected in explicit_periods:
        expected = _parse_month_reference(raw_expected)
        if expected is None or expected != parsed:
            return None

    release_month = f"{release_day.year:04d}-{release_day.month:02d}"
    if parsed >= release_month:
        return None
    if not explicit_periods:
        # Backward-compatible schedule fallback.  Explicit official/feed period
        # metadata wins when present, so delayed releases are never blindly
        # relabelled as release-month-minus-one.
        if parsed != _monthly_period(release_day):
            return None
        resolution = "validated_parser_period_against_regular_release_schedule"
    else:
        resolution = "validated_parser_and_source_reference_period"
    return parsed, resolution


def _publication_timestamps(
    publication: dict[str, Any],
) -> tuple[str, str | None, str | None] | None:
    observed_values = [
        publication.get(field)
        for field in ("first_seen_at", "detected_at", "observed_at")
        if publication.get(field) not in (None, "")
    ]
    observed_times = [_parse_iso_timestamp(value) for value in observed_values]
    if any(value is None for value in observed_times):
        return None

    verified_raw = publication.get("verified_at")
    verified = (
        _parse_iso_timestamp(verified_raw)
        if verified_raw not in (None, "")
        else None
    )
    if verified_raw not in (None, "") and verified is None:
        return None
    if not observed_times:
        if verified is None:
            return None
        observed = verified
    else:
        observed = min(value for value in observed_times if value is not None)

    source_raw = publication.get("source_released_at")
    source_released = (
        _parse_iso_timestamp(source_raw)
        if source_raw not in (None, "")
        else None
    )
    if source_raw not in (None, "") and source_released is None:
        return None
    if source_released is not None and observed < source_released:
        return None
    if verified is not None and verified < observed:
        return None
    return _iso_utc(observed), _iso_utc(source_released), _iso_utc(verified)


def _sha256(value: Any) -> str | None:
    text = str(value or "").lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        return None
    return text


def _receipt_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "official_actual:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _known_receipt_defect_errors(
    row: Any,
    *,
    defects_path: str | Path = DEFAULT_DEFECTS_PATH,
) -> list[str]:
    """Return immutable sidecar defects without silently dropping bad governance data.

    An absent sidecar means no local quarantine policy and therefore fails open.
    Once a sidecar exists, an unreadable/invalid root fails closed for every receipt.
    A receipt ID present in the keyed defect map remains quarantined even when its
    matching metadata is malformed; a damaged entry must never revive known-bad
    scoring truth.
    """
    try:
        payload = json.loads(Path(defects_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError, TypeError):
        return [_DEFECT_SIDECAR_INVALID]

    if (
        not isinstance(payload, dict)
        or payload.get("schema") != _DEFECT_SIDECAR_SCHEMA
        or not isinstance(payload.get("defects_by_receipt"), dict)
    ):
        return [_DEFECT_SIDECAR_INVALID]

    receipt_id = row.get("receipt_id") if isinstance(row, dict) else None
    defects = payload["defects_by_receipt"]
    if not isinstance(receipt_id, str) or receipt_id not in defects:
        return []

    defect = defects[receipt_id]
    if not isinstance(defect, dict):
        return [_SOURCE_BINDING_DEFECT]
    # Receipt-ID membership is the immutable quarantine decision.  The remaining
    # fields are audit metadata; malformed matching metadata fails closed under the
    # same explicit defect rather than accidentally unquarantining the receipt.
    if defect.get("defect_code") != _SOURCE_BINDING_DEFECT:
        return [_SOURCE_BINDING_DEFECT]
    return [_SOURCE_BINDING_DEFECT]


def normalize_publication(
    publication: dict[str, Any],
    *,
    defects_path: str | Path = DEFAULT_DEFECTS_PATH,
) -> list[dict[str, Any]]:
    """Normalize one verified live-publication row; fail closed to ``[]``.

    Parser prose is required to resolve to the source/feed reference period (or
    the regular schedule fallback when no explicit period is supplied).  A
    malformed reference such as ``"The"`` therefore cannot be attached to a
    plausible-looking month and enter scoring truth.
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
    if (
        source_sha is None
        or not _source_compatible(event_type, publication, source_url)
        or (
            actual.get("source_url") not in (None, "")
            and not _official_url(
                actual.get("source_url"), str(_SOURCE_CONTRACTS[event_type]["host"])
            )
        )
        or actual.get("unit") != _SOURCE_CONTRACTS[event_type]["raw_unit"]
    ):
        return []
    release_day = _parse_iso_date(publication.get("date"))
    if release_day is None:
        return []

    period_resolution = _resolve_reference_period(
        event_type, publication, actual, release_day
    )
    timestamps = _publication_timestamps(publication)
    if period_resolution is None or timestamps is None:
        return []
    period, resolution = period_resolution
    observed_at, source_released_at, verified_at = timestamps
    parser = publication.get("parser") if isinstance(publication.get("parser"), dict) else {}

    rows: list[dict[str, Any]] = []
    for release, value_key, metric_id, unit, scale in specs:
        raw_value = actual.get(value_key)
        try:
            raw_float = float(raw_value)
            value = round(raw_float * scale, 6)
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
                "actual": value,
                "actual_raw": raw_float,
                "unit": unit,
                "published_precision": 0 if event_type in ("NFP", "CLAIMS") else 1,
                "actual_basis": "official_published_metric",
                "actual_source": "official_release_document",
                "source_url": str(source_url),
                "source_sha256": source_sha,
                "publisher": publication.get("publisher"),
                "source_id": publication.get("source_id"),
                "source_released_at": source_released_at,
                "observed_at": observed_at,
                "verified_at": verified_at,
                "parser_name": parser.get("name"),
                "parser_version": parser.get("version"),
                "official_reference_period": actual.get("reference_period"),
                "period_resolution": resolution,
                "integrity_contract": "official_actual_integrity.v1",
                "automatic_scoring_eligible": True,
                "display_only": True,
                "authority": False,
            }
        )
    return [
        row
        for row in rows
        if not receipt_integrity_errors(row, defects_path=defects_path)
    ]


def receipt_integrity_errors(
    row: Any,
    *,
    defects_path: str | Path = DEFAULT_DEFECTS_PATH,
) -> list[str]:
    """Return scoring-integrity violations for one persisted actual receipt."""
    if not isinstance(row, dict):
        return ["not_object"]

    errors: list[str] = []
    release = str(row.get("release") or "")
    event_type = _EVENT_BY_RELEASE.get(release)
    spec = _SPEC_BY_RELEASE.get(release)
    if event_type is None or spec is None:
        return ["unsupported_release"]
    metric_id, unit, scale = spec
    contract = _SOURCE_CONTRACTS[event_type]

    if row.get("schema") != "release_actual.v1":
        errors.append("schema_mismatch")
    if row.get("row_type") != "actual":
        errors.append("not_actual_row")
    if row.get("sequence") != "first":
        errors.append("not_first_sequence")
    if row.get("actual_basis") != "official_published_metric":
        errors.append("actual_basis_mismatch")
    if row.get("actual_source") != "official_release_document":
        errors.append("actual_source_mismatch")
    if row.get("metric_id") != metric_id:
        errors.append("metric_id_mismatch")
    if row.get("exact_target_id") != metric_id + "_printed_first":
        errors.append("exact_target_id_mismatch")
    if row.get("unit") != unit:
        errors.append("unit_mismatch")

    parser_name, parser_version = contract["parser"]
    if row.get("publisher") != contract["publisher"]:
        errors.append("publisher_mismatch")
    if row.get("source_id") != contract["source_id"]:
        errors.append("source_id_mismatch")
    if row.get("parser_name") != parser_name:
        errors.append("parser_name_mismatch")
    if type(row.get("parser_version")) is not int or row.get("parser_version") != parser_version:
        errors.append("parser_version_mismatch")
    if not _official_url(row.get("source_url"), str(contract["host"])):
        errors.append("source_agency_mismatch")

    source_sha = _sha256(row.get("source_sha256"))
    if source_sha is None:
        errors.append("source_sha256_invalid")

    release_day = _parse_iso_date(row.get("release_date"))
    period = row.get("period")
    reference = row.get("official_reference_period")
    if release_day is None:
        errors.append("release_date_invalid")
    elif event_type == "CLAIMS":
        reference_day = _parse_week_reference(reference)
        if period != release_day.isoformat():
            errors.append("scheduled_period_mismatch")
        if reference_day is None:
            errors.append("reference_period_invalid")
        elif not 0 <= (release_day - reference_day).days <= 7:
            errors.append("reference_period_schedule_mismatch")
    else:
        reference_month = _parse_month_reference(reference)
        if reference_month is None:
            errors.append("reference_period_invalid")
        elif reference_month != period:
            errors.append("reference_period_target_mismatch")
        release_month = f"{release_day.year:04d}-{release_day.month:02d}"
        if not isinstance(period, str) or not re.fullmatch(
            r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])", period
        ):
            errors.append("target_period_invalid")
        elif period >= release_month:
            errors.append("target_period_not_pre_release")

    observed = _parse_iso_timestamp(row.get("observed_at"))
    if observed is None:
        errors.append("observed_at_invalid")
    source_raw = row.get("source_released_at")
    source_released = (
        _parse_iso_timestamp(source_raw) if source_raw not in (None, "") else None
    )
    if source_raw not in (None, "") and source_released is None:
        errors.append("source_released_at_invalid")
    if observed is not None and source_released is not None and observed < source_released:
        errors.append("observed_before_source_release")
    verified_raw = row.get("verified_at")
    verified = (
        _parse_iso_timestamp(verified_raw) if verified_raw not in (None, "") else None
    )
    if verified_raw not in (None, "") and verified is None:
        errors.append("verified_at_invalid")
    if observed is not None and verified is not None and verified < observed:
        errors.append("verified_before_observed")

    try:
        actual = float(row.get("actual"))
        actual_raw = float(row.get("actual_raw"))
    except (TypeError, ValueError):
        errors.append("actual_invalid")
        actual = actual_raw = math.nan
    if not math.isfinite(actual) or not math.isfinite(actual_raw):
        if "actual_invalid" not in errors:
            errors.append("actual_invalid")
    elif not math.isclose(actual, actual_raw * scale, rel_tol=0.0, abs_tol=1e-6):
        errors.append("actual_scale_mismatch")

    if source_sha is not None and math.isfinite(actual):
        identity = {
            "release": release,
            "period": period,
            "sequence": "first",
            "metric_id": metric_id,
            "value": actual,
            "source_sha256": source_sha,
        }
        if row.get("receipt_id") != _receipt_id(identity):
            errors.append("receipt_id_mismatch")
    errors.extend(_known_receipt_defect_errors(row, defects_path=defects_path))
    return errors


def is_scoring_truth_eligible(
    row: Any,
    *,
    defects_path: str | Path = DEFAULT_DEFECTS_PATH,
) -> bool:
    """Whether a receipt may serve as canonical scoring truth."""
    return not receipt_integrity_errors(row, defects_path=defects_path)


def receipts_from_payload(
    payload: dict[str, Any],
    *,
    defects_path: str | Path = DEFAULT_DEFECTS_PATH,
) -> list[dict[str, Any]]:
    """Extract de-duplicated official receipts from ``release_publications.v2``."""
    if not isinstance(payload, dict) or payload.get("schema") != "release_publications.v2":
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for publication in payload.get("publications") or []:
        for row in normalize_publication(publication, defects_path=defects_path):
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
    payload: dict[str, Any],
    existing: Iterable[dict[str, Any]],
    *,
    defects_path: str | Path = DEFAULT_DEFECTS_PATH,
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
        if is_scoring_truth_eligible(row, defects_path=defects_path):
            key = (str(row.get("release")), str(row.get("period")), str(row.get("sequence") or "first"))
            first_by_key.setdefault(key, row)

    novel: list[dict[str, Any]] = []
    for row in receipts_from_payload(payload, defects_path=defects_path):
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
    rows: Iterable[dict[str, Any]],
    release: str,
    period: str,
    *,
    defects_path: str | Path = DEFAULT_DEFECTS_PATH,
) -> dict[str, Any] | None:
    """Return the keep-first canonical official actual for a target."""
    candidates = [
        row for row in rows
        if is_scoring_truth_eligible(row, defects_path=defects_path)
        and row.get("release") == release
        and row.get("period") == period
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda row: _parse_iso_timestamp(row.get("observed_at"))
        or datetime.max.replace(tzinfo=timezone.utc),
    )
