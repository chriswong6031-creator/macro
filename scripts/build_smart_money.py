"""Build the 13F Smart-Money TRADE TRACKER desk + Ownership Intelligence Desk.

STAGE FLOW
----------
1. compute_tracker()     — per-trade scorecard / leaderboard / best-worst / rotation
2. compute_smart_money() — by-ticker consensus / most-held / trend (SM2-R10: called
                           HERE and smartmoney.json written here; standalone
                           build_site.py resolves this same canonical cohort)
3. Desk assembly         — build smartmoney_desk.json (frozen interface, masterplan §4)
4. Ledger advance        — nightly-only (COLLECT_LANE guard inside ownership_ledger.py)
5. Template render       — current smart_money.html.j2; desk payload passed as `desk`
                           so stage E3 can consume it when the template is rebuilt

NEVER-BREAK CONTRACT: returns 0 on ANY error (mirrors build_alt_data.py). Each new
block is wrapped in try/except with an honest 'unavailable' degradation.

SM2-R10: smartmoney.json produced here; build_site.py independently resolves the
  same canonical period and slugs before any standalone rewrite.
SM2-R11: per-axis freshness stamps in the desk payload; the filing-season clock and
  filed-vs-pending grid are REQUIRED — built here and embedded in `freshness`.
SM2-R3: no blending across axes; crowding keeps short_volume and short_interest as
  SEPARATE sub-dict keys. A unit test asserts no numeric field mixes axes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from lib import config  # noqa: E402
from lib.pages import (  # noqa: E402
    dbase_prefix,
    externalize_css_text,
    inject_text,
    write_page,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("build_smart_money")

_STALE = "unavailable"
_CENSUS_SCHEMA = "institutional_13f.census_public/v1"
_CENSUS_MAX_RAW_BYTES = 16 * 1024
_CENSUS_MAX_ROWS = 6
_CENSUS_RENDER_ARTIFACT_MAX_BYTES = 8 * 1024 * 1024
# Quarters `periods.current` may legitimately trail latest_completed_period():
# that reference advances on the 45-day filing deadline, but the SEC bulk set
# for the quarter publishes only ~2 weeks after it.  See _warn_if_census_frozen.
_CENSUS_PUBLICATION_LAG_QUARTERS = 1
_CENSUS_TOP_LEVEL_KEYS = frozenset({
    "schema", "state", "reason", "generated_at", "identity_grain", "periods",
    "coverage", "leaders", "sector_breadth", "freshness", "scope",
})
_CENSUS_COVERAGE_KEYS = frozenset({
    "current_original_filings",
    "baseline_original_filings",
    "paired_filings",
    "progress_pct",
    "current_notice_filers",
    "current_amendments",
    "current_holding_filers",
    "current_long_positions",
    "mapped_long_positions",
    "mapping_coverage_pct",
    "value_unit_status",
    "current_quality_excluded_reports",
    "baseline_quality_excluded_reports",
    "current_quality_excluded_lineages",
    "baseline_quality_excluded_lineages",
    "current_overlapping_amendment_lineages",
    "baseline_overlapping_amendment_lineages",
    "share_factor_security_exclusions",
    "structural_event_security_exclusions",
})
_CENSUS_COUNT_COVERAGE_KEYS = _CENSUS_COVERAGE_KEYS - frozenset({
    "progress_pct", "mapping_coverage_pct", "value_unit_status",
})
_CENSUS_LEADER_KEYS = frozenset({
    "ticker", "name", "issuer", "sector", "net_increasers", "net_filer_delta",
    "holder_delta", "paired_observations", "new_filers", "adding_filers",
    "trimming_filers", "exiting_filers",
})
_CENSUS_SECTOR_KEYS = frozenset({
    "sector", "name", "net_filer_delta", "net_increasers",
    "paired_observations", "security_count",
})
_CENSUS_SOURCE_KEYS = frozenset({
    "byte_length",
    "kind",
    "quality_findings",
    "sha256",
    "url",
    "rolling_overlay",
    "official_reference_url",
    "filing_window_cutoff_at",
    "acquisition_mode",
    "official_source_status",
    "expected_sha256_attested",
})
_CENSUS_SOURCE_PROVENANCE_KEYS = frozenset({
    "official_reference_url",
    "filing_window_cutoff_at",
    "acquisition_mode",
    "official_source_status",
    "expected_sha256_attested",
})
_CENSUS_QUALITY_FINDING_KEYS = frozenset({
    "confidential_omitted",
    "duplicate_included_manager_sequence",
    "included_manager_count_mismatch",
    "rolling_overlay_catalog_only",
    "rolling_overlay_excluded",
    "table_entry_total_mismatch",
    "table_value_total_mismatch",
})
_CENSUS_OVERLAY_KEYS = frozenset({
    "state",
    "generation_id",
    "manifest_sha256",
    "catalog_source_cutoff_at",
    "requested_source_cutoff_at",
    "catalog_filings_through_cutoff",
    "catalog_only_filings",
    "bulk_duplicate_filings_verified",
    "latest_known",
})
_CENSUS_IDENTIFIER_KEYS = frozenset({
    "resolved_cusips", "sha256", "source", "temporal_policy", "venue_policy",
})
_CENSUS_CLASSIFICATION_KEYS = frozenset({"source", "sha256", "temporal_policy"})
_CENSUS_FRESHNESS_KEYS = frozenset({
    "status",
    "as_of",
    "current_source",
    "baseline_source",
    "identifier_resolution",
    "sector_classification",
    "duplicate_original_lineages",
    "orphan_amendment_lineages",
    "relationship_deduplication",
    "source_cutoff_at",
    "latest_known",
})
_CENSUS_SCOPE_KEYS = frozenset({
    "population",
    "includes_passive_quant_custody",
    "skill_weighted",
    "comparison_basis",
    "action_basis",
    "reported_value_use",
    "corporate_action_filter",
    "materiality_threshold_pct",
    "notices_are_zero_portfolios",
    "authority",
})


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _jdump(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str)


def _site_dir() -> Path:
    d = config.ROOT / "site" / "factordata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _funddata_dir() -> Path:
    d = config.ROOT / "site" / "funddata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _degraded_census(reason: str) -> dict:
    """Small, honest public state used whenever the census boundary rejects input."""
    return {
        "schema": _CENSUS_SCHEMA,
        "state": "degraded",
        "reason": reason,
        "generated_at": None,
        "identity_grain": "filer",
        "periods": {"current": None, "baseline": None},
        "coverage": {
            "current_original_filings": 0,
            "baseline_original_filings": 0,
            "paired_filings": 0,
            "progress_pct": 0.0,
        },
        "leaders": {"broadening": [], "narrowing": []},
        "sector_breadth": [],
        "freshness": {"status": "unavailable", "as_of": None},
    }


def _census_object(
    value,
    *,
    path: str,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
) -> dict:
    if type(value) is not dict:
        raise ValueError(f"{path} must be an object")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise ValueError(f"{path} has unknown keys: {sorted(unknown)}")
    if missing:
        raise ValueError(f"{path} is missing keys: {sorted(missing)}")
    return value


def _census_string(
    value,
    *,
    path: str,
    nullable: bool = False,
    allow_empty: bool = False,
    maximum_chars: int = 4096,
) -> str | None:
    if value is None and nullable:
        return None
    if (
        type(value) is not str
        or (not value and not allow_empty)
        or len(value) > maximum_chars
    ):
        qualifier = " or null" if nullable else ""
        raise ValueError(f"{path} must be a bounded string{qualifier}")
    return value


def _census_integer(value, *, path: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{path} must be an integer >= {minimum}")
    return value


def _census_number(
    value,
    *,
    path: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ValueError(f"{path} must be a finite number")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{path} is below {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{path} exceeds {maximum}")
    return number


def _census_bool(value, *, path: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{path} must be a boolean")
    return value


def _census_date(value, *, path: str, nullable: bool = False) -> str | None:
    text = _census_string(value, path=path, nullable=nullable, maximum_chars=10)
    if text is None:
        return None
    try:
        if date.fromisoformat(text).isoformat() != text:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"{path} must be an ISO date") from exc
    return text


def _census_timestamp(
    value,
    *,
    path: str,
    nullable: bool = False,
) -> str | None:
    text = _census_string(value, path=path, nullable=nullable, maximum_chars=32)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00") if text.endswith("Z") else None
    except ValueError as exc:
        raise ValueError(f"{path} must be an ISO UTC timestamp") from exc
    if parsed is None or parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{path} must be an ISO UTC timestamp")
    return text


def _census_sha256(value, *, path: str, nullable: bool = False) -> str | None:
    text = _census_string(value, path=path, nullable=nullable, maximum_chars=64)
    if text is not None and re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise ValueError(f"{path} must be a lowercase SHA-256")
    return text


def _validate_census_coverage(value) -> None:
    coverage = _census_object(
        value,
        path="coverage",
        allowed=_CENSUS_COVERAGE_KEYS,
        required=frozenset({
            "current_original_filings",
            "baseline_original_filings",
            "paired_filings",
            "progress_pct",
        }),
    )
    for key in _CENSUS_COUNT_COVERAGE_KEYS & set(coverage):
        _census_integer(coverage[key], path=f"coverage.{key}")
    _census_number(
        coverage["progress_pct"], path="coverage.progress_pct", minimum=0, maximum=100
    )
    if "mapping_coverage_pct" in coverage:
        _census_number(
            coverage["mapping_coverage_pct"],
            path="coverage.mapping_coverage_pct",
            minimum=0,
            maximum=100,
        )
    if "value_unit_status" in coverage:
        _census_string(coverage["value_unit_status"], path="coverage.value_unit_status")


def _validate_census_leader(row, *, path: str) -> None:
    leader = _census_object(
        row,
        path=path,
        allowed=_CENSUS_LEADER_KEYS,
        required=_CENSUS_LEADER_KEYS,
    )
    _census_string(leader["ticker"], path=f"{path}.ticker", maximum_chars=32)
    for key in ("name", "issuer", "sector"):
        _census_string(
            leader[key], path=f"{path}.{key}", allow_empty=True, maximum_chars=512
        )
    for key in ("net_increasers", "net_filer_delta", "holder_delta"):
        _census_integer(leader[key], path=f"{path}.{key}", minimum=-(2**63))
    for key in (
        "paired_observations",
        "new_filers",
        "adding_filers",
        "trimming_filers",
        "exiting_filers",
    ):
        _census_integer(leader[key], path=f"{path}.{key}")


def _validate_census_sector(row, *, path: str) -> None:
    sector = _census_object(
        row,
        path=path,
        allowed=_CENSUS_SECTOR_KEYS,
        required=_CENSUS_SECTOR_KEYS,
    )
    for key in ("sector", "name"):
        _census_string(sector[key], path=f"{path}.{key}", maximum_chars=512)
    for key in ("net_filer_delta", "net_increasers"):
        _census_integer(sector[key], path=f"{path}.{key}", minimum=-(2**63))
    for key in ("paired_observations", "security_count"):
        _census_integer(sector[key], path=f"{path}.{key}")


def _validate_census_overlay(value, *, path: str) -> None:
    overlay = _census_object(
        value,
        path=path,
        allowed=_CENSUS_OVERLAY_KEYS,
        required=_CENSUS_OVERLAY_KEYS,
    )
    state = _census_string(overlay["state"], path=f"{path}.state", maximum_chars=16)
    if state not in {"applied", "unavailable", "disabled"}:
        raise ValueError(f"{path}.state is invalid")
    generation_id = _census_string(
        overlay["generation_id"],
        path=f"{path}.generation_id",
        nullable=True,
        maximum_chars=73,
    )
    if generation_id is not None and re.fullmatch(r"i13fgen_[0-9a-f]{64}", generation_id) is None:
        raise ValueError(f"{path}.generation_id is invalid")
    _census_sha256(
        overlay["manifest_sha256"], path=f"{path}.manifest_sha256", nullable=True
    )
    _census_timestamp(
        overlay["catalog_source_cutoff_at"],
        path=f"{path}.catalog_source_cutoff_at",
        nullable=True,
    )
    _census_timestamp(
        overlay["requested_source_cutoff_at"],
        path=f"{path}.requested_source_cutoff_at",
    )
    for key in (
        "catalog_filings_through_cutoff",
        "catalog_only_filings",
        "bulk_duplicate_filings_verified",
    ):
        _census_integer(overlay[key], path=f"{path}.{key}")
    _census_bool(overlay["latest_known"], path=f"{path}.latest_known")


def _validate_census_source(value, *, path: str) -> None:
    source = _census_object(
        value,
        path=path,
        allowed=_CENSUS_SOURCE_KEYS,
        required=frozenset({"byte_length", "kind", "quality_findings", "sha256", "url"}),
    )
    _census_integer(source["byte_length"], path=f"{path}.byte_length")
    for key in ("kind", "url"):
        _census_string(source[key], path=f"{path}.{key}", maximum_chars=4096)
    _census_sha256(source["sha256"], path=f"{path}.sha256")
    findings = _census_object(
        source["quality_findings"],
        path=f"{path}.quality_findings",
        allowed=_CENSUS_QUALITY_FINDING_KEYS,
    )
    for key in set(findings):
        _census_integer(findings[key], path=f"{path}.quality_findings.{key}")
    provenance_keys = set(source) & _CENSUS_SOURCE_PROVENANCE_KEYS
    if provenance_keys and provenance_keys != _CENSUS_SOURCE_PROVENANCE_KEYS:
        missing = sorted(_CENSUS_SOURCE_PROVENANCE_KEYS - provenance_keys)
        raise ValueError(f"{path} has incomplete source provenance: {missing}")
    if provenance_keys:
        _census_string(
            source["official_reference_url"],
            path=f"{path}.official_reference_url",
            maximum_chars=4096,
        )
        _census_timestamp(
            source["filing_window_cutoff_at"],
            path=f"{path}.filing_window_cutoff_at",
        )
        acquisition_mode = _census_string(
            source["acquisition_mode"],
            path=f"{path}.acquisition_mode",
            maximum_chars=32,
        )
        if acquisition_mode not in {
            "sec_https",
            "operator_https",
            "operator_http",
            "operator_file",
        }:
            raise ValueError(f"{path}.acquisition_mode is invalid")
        official_status = _census_string(
            source["official_source_status"],
            path=f"{path}.official_source_status",
            maximum_chars=64,
        )
        if official_status not in {
            "sec_https",
            "expected_sha256_attested",
            "operator_supplied_unattested",
        }:
            raise ValueError(f"{path}.official_source_status is invalid")
        _census_bool(
            source["expected_sha256_attested"],
            path=f"{path}.expected_sha256_attested",
        )
    if "rolling_overlay" in source:
        _validate_census_overlay(source["rolling_overlay"], path=f"{path}.rolling_overlay")


def _validate_census_freshness(value, *, degraded: bool) -> None:
    required = {"as_of"}
    if not degraded:
        required.update({
            "current_source",
            "baseline_source",
            "identifier_resolution",
            "sector_classification",
            "duplicate_original_lineages",
            "orphan_amendment_lineages",
            "relationship_deduplication",
        })
    freshness = _census_object(
        value,
        path="freshness",
        allowed=_CENSUS_FRESHNESS_KEYS,
        required=frozenset(required),
    )
    _census_timestamp(freshness["as_of"], path="freshness.as_of", nullable=degraded)
    if "status" in freshness:
        _census_string(freshness["status"], path="freshness.status", maximum_chars=64)
    for key in ("current_source", "baseline_source"):
        if key in freshness:
            _validate_census_source(freshness[key], path=f"freshness.{key}")
    if "identifier_resolution" in freshness:
        resolution = _census_object(
            freshness["identifier_resolution"],
            path="freshness.identifier_resolution",
            allowed=_CENSUS_IDENTIFIER_KEYS,
            required=_CENSUS_IDENTIFIER_KEYS,
        )
        _census_integer(
            resolution["resolved_cusips"],
            path="freshness.identifier_resolution.resolved_cusips",
        )
        _census_sha256(
            resolution["sha256"], path="freshness.identifier_resolution.sha256"
        )
        for key in ("source", "temporal_policy", "venue_policy"):
            _census_string(
                resolution[key], path=f"freshness.identifier_resolution.{key}"
            )
    if "sector_classification" in freshness:
        classification = freshness["sector_classification"]
        if type(classification) is str:
            _census_string(
                classification, path="freshness.sector_classification"
            )
        else:
            classification = _census_object(
                classification,
                path="freshness.sector_classification",
                allowed=_CENSUS_CLASSIFICATION_KEYS,
                required=_CENSUS_CLASSIFICATION_KEYS,
            )
            _census_sha256(
                classification["sha256"],
                path="freshness.sector_classification.sha256",
            )
            for key in ("source", "temporal_policy"):
                _census_string(
                    classification[key],
                    path=f"freshness.sector_classification.{key}",
                )
    if "relationship_deduplication" in freshness:
        _census_string(
            freshness["relationship_deduplication"],
            path="freshness.relationship_deduplication",
        )
    for key in ("duplicate_original_lineages", "orphan_amendment_lineages"):
        if key in freshness:
            _census_integer(freshness[key], path=f"freshness.{key}")
    if "source_cutoff_at" in freshness:
        _census_timestamp(freshness["source_cutoff_at"], path="freshness.source_cutoff_at")
    if "latest_known" in freshness:
        _census_bool(freshness["latest_known"], path="freshness.latest_known")


def _validate_census_scope(value) -> None:
    scope = _census_object(
        value,
        path="scope",
        allowed=_CENSUS_SCOPE_KEYS,
        required=_CENSUS_SCOPE_KEYS,
    )
    for key in (
        "population",
        "comparison_basis",
        "action_basis",
        "reported_value_use",
        "corporate_action_filter",
        "authority",
    ):
        _census_string(scope[key], path=f"scope.{key}")
    for key in (
        "includes_passive_quant_custody",
        "skill_weighted",
        "notices_are_zero_portfolios",
    ):
        _census_bool(scope[key], path=f"scope.{key}")
    _census_number(
        scope["materiality_threshold_pct"],
        path="scope.materiality_threshold_pct",
        minimum=0,
        maximum=100,
    )


def _reject_duplicate_json_keys(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = child
    return value


def _reject_non_json_constant(value: str):
    raise ValueError(f"invalid JSON numeric constant: {value}")


def _validate_census_document(value) -> dict:
    doc = _census_object(
        value,
        path="census",
        allowed=_CENSUS_TOP_LEVEL_KEYS,
        required=frozenset({
            "schema",
            "state",
            "generated_at",
            "identity_grain",
            "periods",
            "coverage",
            "leaders",
            "sector_breadth",
            "freshness",
        }),
    )
    if doc["schema"] != _CENSUS_SCHEMA:
        raise ValueError("schema mismatch")
    if doc["state"] not in {"rolling", "complete", "degraded"}:
        raise ValueError("invalid census state")
    degraded = doc["state"] == "degraded"
    if doc["identity_grain"] != "filer":
        raise ValueError("identity_grain must be filer")
    _census_timestamp(
        doc["generated_at"], path="generated_at", nullable=degraded
    )
    if "reason" in doc:
        if not degraded:
            raise ValueError("reason is only valid for degraded census state")
        _census_string(doc["reason"], path="reason", maximum_chars=256)
    elif degraded:
        raise ValueError("degraded census state requires reason")

    periods = _census_object(
        doc["periods"],
        path="periods",
        allowed=frozenset({"current", "baseline"}),
        required=frozenset({"current", "baseline"}),
    )
    for key in ("current", "baseline"):
        _census_date(periods[key], path=f"periods.{key}", nullable=degraded)
    _validate_census_coverage(doc["coverage"])

    leaders = _census_object(
        doc["leaders"],
        path="leaders",
        allowed=frozenset({"broadening", "narrowing"}),
        required=frozenset({"broadening", "narrowing"}),
    )
    bounded_leaders: dict[str, list[dict]] = {}
    for key in ("broadening", "narrowing"):
        rows = leaders[key]
        if type(rows) is not list:
            raise ValueError(f"leaders.{key} must be an array")
        for index, row in enumerate(rows):
            _validate_census_leader(row, path=f"leaders.{key}[{index}]")
        bounded_leaders[key] = rows[:_CENSUS_MAX_ROWS]

    sectors = doc["sector_breadth"]
    if type(sectors) is not list:
        raise ValueError("sector_breadth must be an array")
    for index, row in enumerate(sectors):
        _validate_census_sector(row, path=f"sector_breadth[{index}]")
    _validate_census_freshness(doc["freshness"], degraded=degraded)
    if "scope" in doc:
        _validate_census_scope(doc["scope"])
    elif not degraded:
        raise ValueError("census is missing keys: ['scope']")

    bounded = dict(doc)
    bounded["leaders"] = bounded_leaders
    bounded["sector_breadth"] = sectors[:_CENSUS_MAX_ROWS]
    return bounded


def _census_quarter_index(value: date) -> int:
    """Absolute quarter ordinal, so quarter subtraction never mis-crosses a year."""
    return value.year * 4 + (value.month - 1) // 3


def _warn_if_census_frozen(census: dict, *, today: date | None = None) -> None:
    """Annotate when a VALID census has quietly stopped advancing its period.

    The boundary below fails soft when the source is MISSING or MALFORMED — but
    a *frozen* census (a well-formed file whose ``periods.current`` stopped
    advancing) validates perfectly and republishes the same stale quarter
    forever, leaving no trace anywhere.  That is the same failure class as the
    sec_insider 2026q2 five-week freeze (#5601): the only signal was a nightly
    log line nobody reads.

    One quarter of lag is the DESIGN's steady state, not a fault.
    ``latest_completed_period`` advances the moment a quarter's 45-day filing
    deadline passes, while the SEC bulk set for that quarter publishes only
    ~2 weeks later — so the compiler legitimately trails by a quarter inside
    that publication window.  Two or more means accrual has stopped.

    Watchdog only: never raises, never changes what is published.
    """
    try:
        current = (census.get("periods") or {}).get("current")
        if not current:
            return  # degraded/absent — the load path has already said so
        from scripts.build_institutional_13f_census import latest_completed_period

        reference = today if today is not None else datetime.now(timezone.utc).date()
        expected = latest_completed_period(reference)
        lag = _census_quarter_index(expected) - _census_quarter_index(
            date.fromisoformat(current)
        )
        if lag <= _CENSUS_PUBLICATION_LAG_QUARTERS:
            return
        print(
            f"::warning title=institutional-13f-census-stale::"
            f"data/institutional_13f/public/census_latest.json periods.current "
            f"{current} trails the latest completed period {expected.isoformat()} "
            f"by {lag} quarters — the 13F census has stopped advancing (moved SEC "
            f"bulk URL? compiler lane not firing?) and the Smart-Money desk is "
            f"publishing a frozen quarter",
            flush=True,
        )
        log.warning(
            "institutional census stale: periods.current %s vs latest completed "
            "%s (lag %d quarters)",
            current,
            expected.isoformat(),
            lag,
        )
    except Exception as e:  # noqa: BLE001 — a watchdog must never break the build
        log.debug("institutional census staleness check skipped: %s", e)


def _load_institutional_census() -> dict:
    """Load the bounded census, then watch it for a silent freeze.

    The staleness check sits OUTSIDE the fail-closed boundary in
    ``_read_institutional_census`` on purpose: a watchdog that could raise
    inside that ``try`` would turn a perfectly good census into a degraded
    summary — the watchdog must observe the publish, never alter it.
    """
    census = _read_institutional_census()
    _warn_if_census_frozen(census)
    return census


def _read_institutional_census() -> dict:
    """Load and bound the public census projection; reject everything else.

    The private universal holdings plane never crosses this boundary.  Only the
    producer's compact public projection may be embedded in the page.
    """
    source = config.ROOT / "data" / "institutional_13f" / "public" / "census_latest.json"
    try:
        with source.open("rb") as fh:
            raw = fh.read(_CENSUS_MAX_RAW_BYTES + 1)
        if len(raw) > _CENSUS_MAX_RAW_BYTES:
            raise ValueError("source exceeds 16KB")
        doc = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_non_json_constant,
        )
        bounded = _validate_census_document(doc)
        if len(_jdump(bounded).encode("utf-8")) > _CENSUS_MAX_RAW_BYTES:
            raise ValueError("bounded projection exceeds 16KB")
        return bounded
    except FileNotFoundError:
        log.info("institutional census source absent — publishing degraded summary")
        return _degraded_census("source_missing")
    except Exception as e:  # noqa: BLE001 — public boundary must fail closed
        log.warning("institutional census source rejected — publishing degraded summary: %s", e)
        return _degraded_census("source_rejected")


def _publish_institutional_census() -> dict:
    """Publish and return the one bounded census object consumed by the desk."""
    census = _load_institutional_census()
    try:
        (_site_dir() / "institutional_census_summary.json").write_text(_jdump(census))
    except Exception as e:  # noqa: BLE001
        log.warning("write institutional census summary failed: %s", e)
    return census


def _load_bounded_json_object(
    path: Path,
    *,
    maximum_bytes: int,
    label: str,
    allow_non_finite: bool = False,
) -> dict:
    """Read one existing public artifact without admitting unbounded or loose JSON."""
    with path.open("rb") as fh:
        raw = fh.read(maximum_bytes + 1)
    if len(raw) > maximum_bytes:
        raise ValueError(f"{label} exceeds {maximum_bytes} bytes")
    load_kwargs = {"object_pairs_hook": _reject_duplicate_json_keys}
    if not allow_non_finite:
        load_kwargs["parse_constant"] = _reject_non_json_constant
    value = json.loads(raw.decode("utf-8"), **load_kwargs)
    if type(value) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    return value


def _postprocess_census_page(html: str, page_path: Path) -> str:
    """Apply the canonical page-specific asset pipeline without a site sweep."""

    from scripts.externalize_css import MIN_BYTES
    from scripts.optimize_assets import make_optimizer

    site_root = config.ROOT / "site"
    css_root = site_root / "assets" / "css"
    html = inject_text(html, dbase_prefix(page_path))

    def make_href(
        css: str,
        _index: int,
        _media: str | None,
    ) -> str | None:
        payload = css.encode("utf-8")
        if len(payload) < MIN_BYTES:
            return None
        digest = hashlib.sha256(payload).hexdigest()[:8]
        destination = css_root / f"{digest}.css"
        if destination.exists():
            if destination.read_bytes() != payload:
                raise ValueError("content-addressed census CSS collision")
        else:
            css_root.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        return f"assets/css/{digest}.css?v={digest}"

    externalized = externalize_css_text(html, make_href)
    optimized = make_optimizer(site_root)(externalized, page_path.parent)
    marker = '<section class="institutional-census" id="sec-census"'
    start = optimized.index(marker)
    end = optimized.index("</section>", start) + len("</section>")
    census = "\n".join(line.rstrip() for line in optimized[start:end].splitlines())
    return optimized[:start] + census + optimized[end:]


def render_institutional_census_only() -> int:
    """Refresh only the bounded Census block in the existing Smart-Money desk.

    This lane deliberately does not call collectors, cohort resolution, scoring,
    ledgers, or dossier builders.  Both existing public inputs are loaded and the
    three authorized payloads are fully rendered in memory before any is replaced.
    """
    factordata = config.ROOT / "site" / "factordata"
    desk_path = factordata / "smartmoney_desk.json"
    tracker_path = factordata / "smartmoney_tracker.json"
    summary_path = factordata / "institutional_census_summary.json"
    page_path = config.ROOT / "site" / "smart_money.html"
    try:
        desk = _load_bounded_json_object(
            desk_path,
            maximum_bytes=_CENSUS_RENDER_ARTIFACT_MAX_BYTES,
            label="smartmoney_desk.json",
            # The legacy desk intentionally contains Python JSON NaN sentinels.
            # Preserve those already-public values; the new census document is
            # loaded independently through the strict finite-number boundary.
            allow_non_finite=True,
        )
        tracker = _load_bounded_json_object(
            tracker_path,
            maximum_bytes=_CENSUS_RENDER_ARTIFACT_MAX_BYTES,
            label="smartmoney_tracker.json",
        )
        census = _load_institutional_census()
        census_payload = _jdump(census)
        if len(census_payload.encode("utf-8")) > _CENSUS_MAX_RAW_BYTES:
            raise ValueError("institutional census summary exceeds its byte ceiling")
        updated_desk = dict(desk)
        updated_desk["institutional_census"] = census
        desk_payload = _jdump(updated_desk)
        if len(desk_payload.encode("utf-8")) > _CENSUS_RENDER_ARTIFACT_MAX_BYTES:
            raise ValueError("updated smartmoney_desk.json exceeds its byte ceiling")

        env = Environment(
            loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True
        )
        html = env.get_template("smart_money.html.j2").render(
            trk=tracker,
            generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            active_section="us",
            active_page="smart_money",
            desk=updated_desk,
        )
        html = _postprocess_census_page(html, page_path)
        if len(html.encode("utf-8")) > _CENSUS_RENDER_ARTIFACT_MAX_BYTES:
            raise ValueError("rendered smart_money.html exceeds its byte ceiling")

        summary_path.write_text(census_payload)
        desk_path.write_text(desk_payload)
        write_page(page_path, html)
        log.info(
            "census render-only: wrote census summary + smartmoney_desk.json + "
            "smart_money.html without recomputation"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 -- render-only lane must fail closed.
        log.error("census render-only failed; no recomputation attempted: %s", exc)
        return 1


# --------------------------------------------------------------------------- #
# Board assembly helpers (pure given resolved data)                             #
# --------------------------------------------------------------------------- #

def _build_initiations(sm: dict, tracker: dict,
                       target_period: str | None = None,
                       included_slugs: list[str] | set[str] | None = None
                       ) -> list[dict]:
    """SM2-R2 neutral initiations board: new/material-add ≥ 1% book, filing_date DESC.

    Issuer-collapsed (if multiple funds initiate the same ticker, they appear as one
    row with a funds list). n_funds_initiating = fund count. Default sort = filing_date
    DESC (neutral chronology). The word 'validated' is banned from all strings.
    """
    MIN_PCT = 1.0
    by_ticker: dict[str, dict] = {}

    # Build leaderboard turnover index for cross-referencing
    lb = tracker.get("leaderboard", []) if tracker else []
    tt_index = {r["slug"]: r.get("turnover_tier") for r in lb}

    funds_cfg = (config.load().get("smart_money", {}) or {}).get("funds", {}) or {}

    try:
        from engine.smart_money import _read_period_pair, diff_snapshots, resolve_tickers
        from engine.smart_money import name_ticker_map, full_cusip_map, _snapshot_filing_date
        from engine.smart_money import position_rank_and_tilt, window_dressing_flag
        name_map = name_ticker_map()
        cusip_map, _ = full_cusip_map()
    except Exception:  # noqa: BLE001
        return []

    selected = set(included_slugs) if included_slugs is not None else set(funds_cfg)
    for slug, spec in funds_cfg.items():
        if slug not in selected:
            continue
        prev, latest = _read_period_pair(slug, target_period)
        if latest is None or latest.empty:
            continue
        fd = _snapshot_filing_date(latest)
        if not fd:
            continue
        diff = diff_snapshots(prev, latest)
        if diff.empty:
            continue
        diff = resolve_tickers(diff, name_map, cusip_map)
        diff = diff[diff["ticker"].notna()]
        if diff.empty:
            continue
        diff = position_rank_and_tilt(diff)

        for r in diff.itertuples(index=False):
            if r.action not in ("new", "add"):
                continue
            pct = float(r.pct_portfolio) if r.pct_portfolio is not None else 0.0
            if pct < MIN_PCT:
                continue
            ticker = str(r.ticker)
            # shares_change_pct: the actual share-count change from the diff output
            # (used by _incr_pct in board scoring — NOT tilt_pp which is overweight-vs-fund-mean)
            _scp = None
            if hasattr(r, "shares_change_pct") and r.shares_change_pct is not None:
                try:
                    _scp = float(r.shares_change_pct)
                except (TypeError, ValueError):
                    _scp = None
            fund_entry = {
                "slug": slug,
                "name": spec.get("name", slug),
                "action": r.action,
                "rank": int(r.rank) if hasattr(r, "rank") and r.rank is not None else None,
                "tilt": round(float(r.tilt_pp), 3) if hasattr(r, "tilt_pp") and r.tilt_pp is not None else None,
                "shares_change_pct": _scp,
                "pct_book": round(pct, 2),
                "turnover_tier": tt_index.get(slug),
            }
            if ticker not in by_ticker:
                by_ticker[ticker] = {
                    "ticker": ticker,
                    "issuer": str(getattr(r, "issuer", "") or ""),
                    "funds": [],
                    "filing_date": fd,
                    "since_excess": None,
                    "persistence": None,
                }
            by_ticker[ticker]["funds"].append(fund_entry)
            # Take the latest filing_date across funds initiating this ticker
            if fd > by_ticker[ticker]["filing_date"]:
                by_ticker[ticker]["filing_date"] = fd

    # Enrich with since_filing from the sm payload
    sm_bt = (sm or {}).get("by_ticker", {})
    for ticker, rec in by_ticker.items():
        sf = sm_bt.get(ticker, {}).get("since_filing")
        if sf:
            rec["since_excess"] = sf.get("ex_spy_pct")

    # n_funds_initiating per issuer
    result = []
    for ticker, rec in by_ticker.items():
        rec["n_funds_initiating"] = len(rec["funds"])
        result.append(rec)

    # SM2-R2: default sort = filing_date DESC (neutral chronology)
    result.sort(key=lambda r: r.get("filing_date", ""), reverse=True)
    return result


# Index / sector / commodity ETFs are excluded from the CROSS-STOCK consensus and
# crowding boards (GS-style single-stock convention): an SPY line is cash parking,
# not a stock pick, and it distorts holder counts. Fund-book views (accordion,
# rotation) still show them — this filter applies only to the cross-sectional boards.
_INDEX_ETFS = frozenset({
    "SPY", "IVV", "VOO", "QQQ", "IWM", "DIA", "VTI", "RSP", "MDY", "IJR", "IJH",
    "EEM", "EFA", "VEA", "VWO", "FXI", "KWEB", "EWJ", "EWZ", "INDA",
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    "SMH", "SOXX", "XBI", "IBB", "KRE", "XOP", "XME", "GDX", "GDXJ", "ARKK",
    "GLD", "SLV", "USO", "UNG", "TLT", "IEF", "SHY", "HYG", "LQD", "AGG", "BND",
})


def _build_grand_portfolio(sm: dict) -> list[dict]:
    """Issuer-collapsed consensus board sorted by aggregate $."""
    if not sm:
        return []
    by_ticker = sm.get("by_ticker", {})
    most_held = sm.get("most_held", [])
    out = []
    n_etf_skipped = 0
    for m in most_held:
        ticker = m.get("ticker", "")
        if ticker in _INDEX_ETFS:
            n_etf_skipped += 1
            continue
        bt = by_ticker.get(ticker, {})
        trend = bt.get("trend", {})
        holders_series = trend.get("holders_series", []) if trend else []
        # QoQ holder delta
        d_funds_qoq = (
            int(holders_series[-1]) - int(holders_series[-2])
            if len(holders_series) >= 2 else None
        )
        # n_top10: how many current holders have this in their top-10 (approx from rank)
        holders = bt.get("holders", [])
        n_top10 = sum(1 for h in holders if (h.get("position_rank") or 99) <= 10)
        # since_excess from since_filing
        since_excess = bt.get("since_filing", {}).get("ex_spy_pct") if bt.get("since_filing") else None
        # HHI from overlap_stats already in bt
        hhi = bt.get("ownership_hhi")
        max_book_pct = bt.get("max_book_pct")
        agg_value_usd = float(m.get("total_value", 0))
        # Issuer: take from first holder that carries it (propagated by compute_smart_money fix)
        issuer_gp = next((h.get("issuer", "") for h in holders if h.get("issuer")), "")
        out.append({
            "ticker": ticker,
            "issuer": issuer_gp,
            "n_funds": int(m.get("n_funds", 0)),
            "d_funds_qoq": d_funds_qoq,
            "holders_series": holders_series,
            "agg_value_usd": round(agg_value_usd, 0),
            "max_book_pct": max_book_pct,
            "hhi": hhi,
            "n_top10": n_top10,
            "since_excess": since_excess,
            "asof": bt.get("as_of", ""),
        })
    out.sort(key=lambda r: -(r.get("agg_value_usd") or 0))
    if n_etf_skipped:
        log.info("grand_portfolio: %d index-ETF lines excluded from cross-stock board",
                 n_etf_skipped)
    return out


def _build_crowding(sm: dict) -> list[dict]:
    """Crowding/unwind radar rows.

    SM2-R3: short_volume and short_interest are SEPARATE sub-dict keys — they must
    never share a column or an as-of. The `short_volume` sub-dict carries its own
    `asof` key; `short_interest` carries `settlement_date` as its stamp. No numeric
    field crosses the two axes.
    """
    if not sm:
        return []

    try:
        from engine.ownership_crowding import (adv_shares, days_to_exit as _dte,
                                               crowding_tier as _ct, implied_entry_band)
        from engine.short_volume import signal_map as sv_map
    except Exception:  # noqa: BLE001
        return []

    try:
        sv = sv_map()
    except Exception:  # noqa: BLE001
        sv = {}

    # Load short interest
    si_data: dict = {}
    try:
        import pandas as pd
        p = config.data_dir() / "finra" / "short_interest.parquet"
        if p.exists():
            si_df = pd.read_parquet(p)
            for idx, row in si_df.iterrows():
                si_data[str(idx)] = {
                    "days_to_cover": row.get("days_to_cover"),
                    "si_change_pct": row.get("si_change_pct"),
                    "settlement_date": str(row.get("settlement_date", "")) if row.get("settlement_date") else None,
                }
    except Exception:  # noqa: BLE001
        pass

    # ClosePanel for entry_band latest_close (reuse same price plumbing as enrich_since_filing)
    close_panel = None
    try:
        from engine.manager_trades import ClosePanel
        close_panel = ClosePanel()
    except Exception:  # noqa: BLE001
        log.debug("_build_crowding: ClosePanel unavailable — entry_band n_underwater will be None")

    by_ticker = sm.get("by_ticker", {})
    most_held = sm.get("most_held", [])

    # Build universe DTE distribution for quintile calibration
    # Uses aggregate shares directly from holder records (propagated in E2.5 fix).
    dte_universe: list[float] = []
    ticker_dte_map: dict[str, float | None] = {}
    for m in most_held:
        ticker = m.get("ticker", "")
        if ticker in _INDEX_ETFS:
            continue
        bt = by_ticker.get(ticker, {})
        holders = [h for h in bt.get("holders", []) if h.get("action") != "exit"]
        as_of = bt.get("as_of", "")
        adv_meta = adv_shares(ticker, as_of=as_of)
        adv = adv_meta["adv"] if adv_meta else None
        # Aggregate shares: sum from holder records (shares propagated by compute_smart_money)
        agg_shares = sum(float(h.get("shares") or 0) for h in holders)
        dte_val = _dte(agg_shares if agg_shares > 0 else None, adv)
        ticker_dte_map[ticker] = dte_val
        if dte_val is not None:
            dte_universe.append(dte_val)

    out = []
    for m in most_held:
        ticker = m.get("ticker", "")
        bt = by_ticker.get(ticker, {})
        holders = [h for h in bt.get("holders", []) if h.get("action") != "exit"]
        as_of = bt.get("as_of", "")
        dte_val = ticker_dte_map.get(ticker)
        ct = _ct(dte_val, dte_universe if len(dte_universe) >= 5 else None)

        # Issuer: take from first non-exit holder (populated by compute_smart_money fix)
        issuer = next((h.get("issuer", "") for h in holders if h.get("issuer")), "")

        # Implied entry band: pass latest close from ClosePanel (reuse existing price plumbing)
        ieb = None
        try:
            latest_close = None
            if close_panel is not None:
                cs = close_panel.get(ticker)
                if cs is not None and len(cs) > 0:
                    latest_close = float(cs.iloc[-1])
            ieb = implied_entry_band(holders, latest_close=latest_close)
        except Exception:  # noqa: BLE001
            pass

        # short_volume sub-dict — its own asof, strictly separate (SM2-R3)
        sv_rec = sv.get(ticker)
        sv_sub = None
        if sv_rec:
            sv_sub = {
                "ratio": sv_rec.get("short_ratio"),
                "trend_pp": sv_rec.get("trend_pp"),
                "ratio_z": sv_rec.get("ratio_z"),
                "asof": sv_rec.get("asof"),    # daily as-of, independent stamp
            }

        # short_interest sub-dict — settlement_date stamp, strictly separate (SM2-R3)
        si_rec = si_data.get(ticker)
        si_sub = None
        if si_rec:
            si_sub = {
                "days_to_cover": si_rec.get("days_to_cover"),
                "si_change_pct": si_rec.get("si_change_pct"),
                "settlement_date": si_rec.get("settlement_date"),  # bi-monthly as-of
            }

        out.append({
            "ticker": ticker,
            "issuer": issuer,
            "n_funds": int(m.get("n_funds", 0)),
            "agg_value_usd": round(float(m.get("total_value", 0)), 0),
            "hhi": bt.get("ownership_hhi"),
            "max_book_pct": bt.get("max_book_pct"),
            "days_to_exit": dte_val,
            "crowding_tier": ct,
            "entry_band": ieb,
            "short_volume": sv_sub,    # separate sub-dict, own asof (SM2-R3)
            "short_interest": si_sub,  # separate sub-dict, settlement_date (SM2-R3)
        })

    return out


def _build_activists(wire_rows: list[dict], sm: dict) -> list[dict]:
    """Activist situation monitor from the 13D/G wire axis.

    State comes from engine.beneficial_ownership.load_regime() — the per-ticker
    regime machine (activist / flip / passive / custodial), which is the classifier
    that carries the 13G→13D flip detection. The wire row's own form-derived label
    is only the fallback when a ticker has no regime entry.
    """
    bt = (sm or {}).get("by_ticker", {})
    slug_to_funds: dict[str, list[str]] = {}
    for tk, rec in bt.items():
        for h in rec.get("holders", []):
            slug_to_funds.setdefault(tk, []).append(h.get("fund", ""))

    regime: dict[str, dict] = {}
    try:
        from engine.beneficial_ownership import load_regime
        regime = load_regime() or {}
    except Exception as e:  # noqa: BLE001 — board degrades to form-derived labels
        log.warning("load_regime unavailable for activist board: %s", e)

    out = []
    for row in wire_rows:
        if row.get("axis") != "13dg":
            continue
        if row.get("signal") not in ("high", "low"):
            continue
        ticker = row.get("ticker") or ""
        reg = regime.get(ticker) or {}
        state = reg.get("regime") or reg.get("state") or ""
        if not state:
            # form-derived fallback: 13D from a non-custodian reads activist-form,
            # everything else passive-form (custodial rows never reach here — their
            # signal is 'noise').
            state = "activist" if row.get("action") == "13d" else "passive"
        sf = bt.get(ticker, {}).get("since_filing", {})
        n_tracked = len(slug_to_funds.get(ticker, []))
        out.append({
            "date_filed": row.get("date", ""),
            "filer": row.get("fund", ""),
            "ticker": ticker,
            "issuer": row.get("issuer", ""),
            "form": row.get("type", ""),
            "state": state,
            "signal": reg.get("signal") or row.get("signal", ""),
            "n_tracked_holders": n_tracked,
            "since_excess": sf.get("ex_spy_pct") if sf else None,
        })
    return out


def _build_managers(tracker: dict) -> dict:
    """Per-slug manager dict from the leaderboard."""
    out: dict[str, dict] = {}
    if not tracker:
        return out
    for r in tracker.get("leaderboard", []):
        slug = r.get("slug", "")
        if not slug:
            continue
        out[slug] = {
            "turnover_pct": r.get("turnover_pct"),
            "turnover_tier": r.get("turnover_tier"),
            "holding_period_q": r.get("holding_period_q"),
            "concentration_pct": r.get("concentration_pct"),
            "n_holdings": r.get("n_holdings"),
            "style": r.get("style"),
            "status": r.get("status"),
            "coverage_pct": r.get("coverage_pct"),
            "sell_skill": r.get("sell_skill"),
            "n_buys_h": r.get("n_buys_h"),
            "decay": r.get("decay"),
        }
    return out


# --------------------------------------------------------------------------- #
# Main                                                                          #
# --------------------------------------------------------------------------- #

def main() -> int:
    t0 = time.monotonic()
    phase_times: dict[str, float] = {}

    cfg = config.load()
    sm_cfg = cfg.get("smart_money", {}) or {}
    funds = sm_cfg.get("funds", {}) or {}

    # ---- Phase 1: compute_tracker ----
    t1 = time.monotonic()
    tracker = None
    try:
        from engine.manager_trades import compute_tracker
        tracker = compute_tracker()
        if not tracker:
            log.info("smart-money tracker: nothing to score — skipping tracker JSON")
    except Exception as e:  # noqa: BLE001
        log.warning("compute_tracker failed — continuing: %s", e)
    phase_times["tracker"] = round(time.monotonic() - t1, 2)

    if tracker:
        try:
            (_site_dir() / "smartmoney_tracker.json").write_text(_jdump(tracker))
        except Exception as e:  # noqa: BLE001
            log.warning("write smartmoney_tracker.json failed: %s", e)

    # Filing-season transition is resolved before any aggregate board is built.
    # This gives every downstream surface one homogeneous cohort contract:
    # complete prior-quarter baseline before strict majority, then the paired
    # incoming-quarter reporters as the rolling main cohort.
    clock: dict = {}
    filing_transition: dict = {}
    try:
        from engine.ownership_event_wire import (filing_season_clock,
                                                 latest_fund_filings)
        from engine.filing_transition import build_filing_transition
        clock = filing_season_clock(
            funds, fund_filings=latest_fund_filings(funds))
        filing_transition = build_filing_transition(funds, clock, tracker or {})
    except Exception as e:  # noqa: BLE001
        # Mixing each manager's latest quarter is a silent data-integrity failure.
        # Keep the prior published artifact and fail this build instead of
        # falling back to the legacy mixed-quarter behaviour.
        log.error("filing transition preflight failed — refusing mixed books: %s", e)
        return 1

    # ---- Phase 2: compute_smart_money (SM2-R10: called here) ----
    t2 = time.monotonic()
    sm = None
    try:
        from engine.smart_money import compute_smart_money
        sm = compute_smart_money(
            sm_cfg,
            target_period=filing_transition.get("canonical_period"),
            included_slugs=filing_transition.get("canonical_slugs"),
        )
        if not sm:
            log.info("compute_smart_money: no data — degraded desk")
    except Exception as e:  # noqa: BLE001
        log.warning("compute_smart_money failed — continuing: %s", e)
    phase_times["smart_money"] = round(time.monotonic() - t2, 2)

    if sm:
        try:
            (_site_dir() / "smartmoney.json").write_text(_jdump(sm))
        except Exception as e:  # noqa: BLE001
            log.warning("write smartmoney.json failed: %s", e)

    # ---- Phase 3: event wire + filing-season clock ----
    t3 = time.monotonic()
    wire: list[dict] = []
    wire_13dg_activists: list[dict] = []
    try:
        from engine.ownership_event_wire import (build_wire, freshness_axes,
                                                 _13dg_rows, _13DG_LOOKBACK_ACTIVISTS)
        wire, clock = build_wire(funds)
        # Rebuild the small transition payload from the exact clock returned with
        # the wire, but preserve the preflight cohort atomically if files changed
        # underneath this build. The next run will promote the newer receipt.
        from engine.filing_transition import build_filing_transition
        refreshed_transition = build_filing_transition(funds, clock, tracker or {})
        preflight_contract = (
            filing_transition.get("canonical_period"),
            tuple(filing_transition.get("canonical_slugs") or []),
        )
        refreshed_contract = (
            refreshed_transition.get("canonical_period"),
            tuple(refreshed_transition.get("canonical_slugs") or []),
        )
        if refreshed_contract == preflight_contract:
            filing_transition = refreshed_transition
        else:
            log.warning(
                "filing transition changed during build; preserving atomic preflight cohort")
        freshness = freshness_axes(wire, clock)
        # Activists board keeps its own 45-day 13D/G feed (independent of main wire cap)
        try:
            wire_13dg_activists = _13dg_rows(lookback_days=_13DG_LOOKBACK_ACTIVISTS)
        except Exception as e_act:  # noqa: BLE001
            log.warning("activists 45d 13D/G feed failed — falling back to main wire: %s", e_act)
            wire_13dg_activists = [r for r in wire if r.get("axis") == "13dg"]
    except Exception as e:  # noqa: BLE001
        log.warning("ownership_event_wire failed — continuing: %s", e)
        freshness = []
    phase_times["wire"] = round(time.monotonic() - t3, 2)

    # Public all-filer census projection.  This is a strict, bounded boundary:
    # private filings/holdings stay in the institutional evidence plane and only
    # the <=16KB public summary is written to site/ and embedded in the desk.
    institutional_census = _publish_institutional_census()

    # ---- Phase 4: assemble desk payload ----
    t4 = time.monotonic()
    try:
        initiations = _build_initiations(
            sm or {}, tracker or {},
            target_period=filing_transition.get("canonical_period"),
            included_slugs=filing_transition.get("canonical_slugs"),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("initiations build failed: %s", e)
        initiations = []

    try:
        grand_portfolio = _build_grand_portfolio(sm or {})
    except Exception as e:  # noqa: BLE001
        log.warning("grand_portfolio build failed: %s", e)
        grand_portfolio = []

    try:
        crowding = _build_crowding(sm or {})
    except Exception as e:  # noqa: BLE001
        log.warning("crowding build failed: %s", e)
        crowding = []

    try:
        # Activists board uses the 45-day 13D/G feed (independent of the capped 14d main wire)
        activists = _build_activists(wire_13dg_activists, sm or {})
    except Exception as e:  # noqa: BLE001
        log.warning("activists build failed: %s", e)
        activists = []

    try:
        managers = _build_managers(tracker or {})
    except Exception as e:  # noqa: BLE001
        log.warning("managers build failed: %s", e)
        managers = {}

    # ---- Phase 4.2: insider intelligence (two lanes, two clocks — SM2-R3) ----
    t42 = time.monotonic()
    insider_intel: dict = {}
    try:
        from engine.insider_intel import build_insider_intel
        # Roster = tickers currently held (non-exit holder) by any tracked fund.
        # Lets the market-wide quiver lane carry an honest "held by tracked funds"
        # flag (roster_hit) without blending lanes numerically. Empty → None so
        # "unknown" is never displayed as "not held".
        roster: set[str] = set()
        try:
            roster = {
                tk for tk, rec in ((sm or {}).get("by_ticker", {}) or {}).items()
                if any(h.get("action") != "exit" for h in rec.get("holders", []))
            }
        except Exception as e:  # noqa: BLE001
            log.warning("insider roster derivation failed — roster_hit degrades: %s", e)
        try:
            insider_intel = build_insider_intel(sm_cfg, roster=roster or None) or {}
        except TypeError:
            # Older engine signature without the roster kwarg — degrade politely.
            insider_intel = build_insider_intel(sm_cfg) or {}
        if not insider_intel:
            log.info("insider_intel: no data — desk section degrades to hidden")
    except Exception as e:  # noqa: BLE001
        log.warning("insider_intel build failed — continuing: %s", e)
        insider_intel = {}
    phase_times["insider_intel"] = round(time.monotonic() - t42, 2)

    # ---- Phase 4.3: per-fund intelligence (full books / conviction / theme reads) ----
    t43 = time.monotonic()
    fund_intel: dict = {}
    fund_intel_latest: dict = {}
    fund_intel_index: dict = {}
    try:
        from engine.fund_intelligence import build_fund_intel
        active_slugs = filing_transition.get("active_slugs") or list(funds)
        # Individual dossiers roll as soon as that manager files. Aggregate
        # flow/consensus boards receive a separate homogeneous cohort payload.
        fund_intel_latest = build_fund_intel(
            sm_cfg, tracker, included_slugs=active_slugs) or {}
        latest_periods = {
            str((fi.get("book_meta") or {}).get("period_end") or "")
            for fi in (fund_intel_latest.get("funds") or {}).values()
        }
        canonical_slugs = filing_transition.get("canonical_slugs") or active_slugs
        can_reuse_latest = (
            set(canonical_slugs) == set(active_slugs)
            and latest_periods == {str(filing_transition.get("canonical_period") or "")}
        )
        fund_intel = (
            fund_intel_latest if can_reuse_latest else
            (build_fund_intel(
                sm_cfg, tracker,
                target_period=filing_transition.get("canonical_period"),
                included_slugs=canonical_slugs,
            ) or {})
        )
    except Exception as e:  # noqa: BLE001
        log.warning("fund_intel build failed — continuing: %s", e)
        fund_intel = {}
        fund_intel_latest = {}
    if fund_intel_latest.get("funds"):
        _lb_grades = {r.get("slug"): r.get("grade")
                      for r in (tracker or {}).get("leaderboard", [])}
        for slug, fi in (fund_intel_latest.get("funds") or {}).items():
            # Per-fund JSON page payload — the 50 full books never ride in the
            # desk JSON (small pages; the dossier/template hydrates from here).
            try:
                (_funddata_dir() / f"{slug}.json").write_text(_jdump(fi))
            except Exception as e:  # noqa: BLE001
                log.warning("write funddata/%s.json failed: %s", slug, e)
            # Compact index row for the desk payload (directory grid + links).
            try:
                meta = fi.get("book_meta") or {}
                core = (fi.get("theme_read") or {}).get("core") or {}
                series = fi.get("sector_series") or []
                weights = ((series[-1] or {}).get("weights") or {}) if series else {}
                top_sector = max(weights, key=weights.get) if weights else None
                fund_intel_index[slug] = {
                    "core_lean_label": core.get("label"),
                    "core_lean_label_zh": core.get("label_zh"),
                    "book_value_usd": meta.get("book_value_usd"),
                    "n_positions": meta.get("n_positions"),
                    "top_sector": top_sector,
                    "grade": _lb_grades.get(slug),
                }
            except Exception as e:  # noqa: BLE001
                log.warning("fund_intel_index row failed for %s: %s", slug, e)
    phase_times["fund_intel"] = round(time.monotonic() - t43, 2)

    # ---- Phase 4.4: consolidated cross-fund flow + descriptive models ----
    t44 = time.monotonic()
    flow: dict = {}
    try:
        from engine.ownership_flow import (group_flow, models, rotation_history,
                                           stock_flow)
        flow_cfg = sm_cfg.get("flow", {}) or {}
        top_grades = flow_cfg.get("top_grades", ["A", "B"]) or ["A", "B"]
        top_slugs = [r.get("slug") for r in (tracker or {}).get("leaderboard", [])
                     if r.get("grade") in set(top_grades)]

        cls = None
        try:
            from engine.fund_intelligence import load_classifications
            cls = load_classifications()
        except Exception as e:  # noqa: BLE001
            log.warning("load_classifications failed — models degrade: %s", e)

        def _flow_part(name: str, default, fn, *args, **kwargs):
            """One flow sub-board; degrades honestly on failure (NEVER-BREAK)."""
            try:
                out = fn(*args, **kwargs)
                return out if out is not None else default
            except Exception as e_part:  # noqa: BLE001
                log.warning("flow.%s failed — continuing: %s", name, e_part)
                return default

        stock_flow_d = _flow_part("stock", {}, stock_flow, sm or {}, tracker or {})
        flow = {
            "stock": stock_flow_d,
            "sector": _flow_part("sector", {}, group_flow, fund_intel,
                                 tracker or {}, level="sector"),
            "theme": _flow_part("theme", {}, group_flow, fund_intel,
                                tracker or {}, level="theme"),
            "sector_top": _flow_part("sector_top", {}, group_flow, fund_intel,
                                     tracker or {}, level="sector",
                                     top_grades=top_grades),
            "theme_top": _flow_part("theme_top", {}, group_flow, fund_intel,
                                    tracker or {}, level="theme",
                                    top_grades=top_grades),
            "history": _flow_part("history", [], rotation_history, fund_intel),
            "history_top": _flow_part("history_top", [], rotation_history,
                                      fund_intel, top_slugs=top_slugs),
            "models": _flow_part("models", {}, models, sm or {}, tracker or {},
                                 stock_flow_d, crowding, fund_intel, cls),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("flow build failed — continuing: %s", e)
        flow = {}
    phase_times["flow"] = round(time.monotonic() - t44, 2)

    # ---- Phase 4.5: Follow Desk (followability + boards) ----
    t45 = time.monotonic()
    follow_desk: dict = {}
    try:
        from engine.fund_followability import compute_followability, load_books
        from engine.fund_boards import (build_best_buys, build_small_mid_board,
                                        build_sector_consensus, load_grade_a_card,
                                        load_cap_sources)

        # Reuse the classifications already loaded in Phase 4.4 if available
        _fol_cls = cls  # may be None — followability handles it
        if _fol_cls is None:
            try:
                from engine.fund_intelligence import load_classifications as _lc
                _fol_cls = _lc()
            except Exception as _e_cls:
                log.warning("follow-desk: load_classifications failed: %s", _e_cls)
                _fol_cls = {}

        _slugs = list(funds.keys())
        _books_by_fund = load_books(_slugs)

        # Build a single run-level price-series cache to avoid re-reading
        # the same parquet file thousands of times across 51 funds × many periods.
        # SM2-R12: each read is ~1-2ms but N_funds × N_periods × N_tickers
        # accumulates to minutes without this. Cache stays in-scope for the
        # duration of Phase 4.5 only (not leaked to other phases).
        from engine.fund_followability import _default_price_loader as _raw_pl
        _price_cache: dict = {}
        def _cached_price_loader(ticker: str, _cache=_price_cache) -> object:
            if ticker not in _cache:
                _cache[ticker] = _raw_pl(ticker)
            return _cache[ticker]

        # ---- followability cache gate (render-budget law) ----
        # The heavy compute (sleeve/rotation-IQ/front-run pricing across 51 funds x
        # 13 quarters) only meaningfully changes when a NEW FILING lands or the
        # scoring version bumps; filing-anchored windows drift slowly between
        # filings. Fingerprint = latest (period, filing_date, n_rows) per fund +
        # FOLLOW_VERSION; reuse the committed artifact when it matches and is
        # under _FOLLOW_CACHE_MAX_AGE_D old (bounds fixed-horizon drift to a week).
        # NOTE (SM4-R2): the memory block's "last 4 settled quarters" also advances
        # with price_thru (calendar time), which the fingerprint does NOT track — a
        # quarter that settles mid-week appears only when a filing lands or the 7-day
        # age cap forces a recompute. Staleness is bounded to <= 7 days; accepted.
        # The boards below are ALWAYS rebuilt fresh — they use daily inputs.
        import hashlib as _hl
        from engine.fund_followability import FOLLOW_VERSION as _FV
        _FOLLOW_CACHE_MAX_AGE_D = 7
        _fp_src: list = [_FV]
        for _s in sorted(_books_by_fund):
            _pers = _books_by_fund[_s]
            if not _pers:
                continue
            _mx = max(_pers)
            _df_mx = _pers[_mx]
            _fd_mx = ""
            try:
                if "filing_date" in _df_mx.columns and len(_df_mx):
                    _fd_mx = str(_df_mx["filing_date"].iloc[0])
            except Exception:  # noqa: BLE001
                pass
            _fp_src.append(f"{_s}|{_mx}|{_fd_mx}|{len(_df_mx)}")
        _fingerprint = _hl.sha1("\n".join(_fp_src).encode()).hexdigest()[:16]

        _followability = None
        _follow_computed_at = None
        _memory: dict = {}
        _cache_hit = False
        try:
            _prev = json.loads((_site_dir() / "smartmoney_follow.json").read_text())
            _pm = _prev.get("meta") or {}
            _age_ok = False
            if _pm.get("computed_at"):
                _age_d = (datetime.now(timezone.utc)
                          - datetime.fromisoformat(_pm["computed_at"])).days
                _age_ok = 0 <= _age_d <= _FOLLOW_CACHE_MAX_AGE_D
            if _pm.get("fingerprint") == _fingerprint and _age_ok and _prev.get("followability"):
                _followability = _prev["followability"]
                _follow_computed_at = _pm.get("computed_at")
                # SM4-R2: reuse memory block from prior artifact on cache hit
                if _prev.get("memory"):
                    _memory = _prev["memory"]
                    _cache_hit = True
                log.info("follow-desk: followability cache HIT (fp=%s, computed %s) — boards fresh",
                         _fingerprint, _follow_computed_at)
        except Exception:  # noqa: BLE001
            _followability = None

        if _followability is None:
            _followability = compute_followability(
                tracker or {}, _books_by_fund, _fol_cls or {},
                price_loader=_cached_price_loader,
            )
            _follow_computed_at = datetime.now(timezone.utc).isoformat()

        # SM4-R2: 4-quarter fund memory (compute when cache miss or memory absent)
        if not _cache_hit:
            try:
                from engine.fund_memory import compute_memory as _compute_memory
                _lb_rows = {r.get("slug"): r for r in (tracker or {}).get("leaderboard", [])}
                _fund_names_mem = {
                    slug: (spec.get("name") or slug)
                    for slug, spec in ((config.load().get("smart_money", {}) or {}).get("funds", {}) or {}).items()
                }
                _fund_grades_mem = {
                    slug: _lb_rows.get(slug, {}).get("grade")
                    for slug in _slugs
                }
                _memory = _compute_memory(
                    slugs=_slugs,
                    fund_names=_fund_names_mem,
                    fund_grades=_fund_grades_mem,
                    books_by_fund=_books_by_fund,
                    price_loader=_cached_price_loader,
                )
                log.info(
                    "follow-desk: fund memory computed — %d quarters, %d ranked funds",
                    len((_memory or {}).get("quarters", [])),
                    len((_memory or {}).get("board", [])),
                )
            except Exception as _e_mem:  # noqa: BLE001 — NEVER-BREAK
                log.warning("follow-desk: fund_memory compute failed — degrading: %s", _e_mem)
                _memory = {}

        # Derive sector_flows from the already-computed flow["sector"] output
        # shape: {key: {net_pp: float, ...}} — net_pp > 0 means net inflow
        _sector_flows: dict | None = None
        _raw_sector = (flow.get("sector") or {}).get("groups")
        if _raw_sector:
            _sector_flows = {
                row["key"]: {"net_inflow": float(row.get("net_pp") or 0) > 0}
                for row in _raw_sector if row.get("key")
            }

        _cap_sources = load_cap_sources()

        # Flat initiations list enriched with slug for board scoring
        _flat_initiations: list[dict] = []
        for init_row in initiations:
            ticker = init_row.get("ticker", "")
            # Sector lookup from classifications (FIX 2: was hard-coded None)
            _ticker_upper = (ticker or "").upper()
            _sector = ((_fol_cls or {}).get(_ticker_upper) or {}).get("sector")
            # since_excess is ticker-level (median across funds = same value — display only)
            for fe in init_row.get("funds", []):
                _flat_initiations.append({
                    "ticker": ticker,
                    "issuer": init_row.get("issuer", ""),
                    "action": fe.get("action", ""),
                    "pct_book": fe.get("pct_book") or 0.0,
                    "shares_change_pct": fe.get("shares_change_pct"),  # real share-count delta (not tilt)
                    "filing_date": init_row.get("filing_date", ""),
                    "since_excess": init_row.get("since_excess"),
                    "sector": _sector,
                    "slug": fe.get("slug", ""),
                    "name": fe.get("name", ""),
                })

        _best_buys = build_best_buys(
            _flat_initiations, _followability, _sector_flows, _cap_sources, top_n=40
        )
        _small_mid = build_small_mid_board(
            _best_buys or _flat_initiations, _followability, _cap_sources
        )

        # Sector consensus: build books_latest_pair from fund_intel sector_series
        _books_latest_pair: dict = {}
        for slug, fi_entry in (fund_intel.get("funds") or {}).items():
            _series = fi_entry.get("sector_series") or []
            if len(_series) < 2:
                continue
            _prev_w = (_series[-2] or {}).get("weights") or {}
            _curr_w = (_series[-1] or {}).get("weights") or {}
            _riq = (_followability.get(slug) or {}).get("rotation_iq") or {}
            _books_latest_pair[slug] = {
                "prev": _prev_w,
                "curr": _curr_w,
                "rotation_iq": _riq,
                "tickers_curr": {},  # ticker-level detail not needed for consensus bars
            }
        _consensus = build_sector_consensus(_books_latest_pair, _followability, _fol_cls or {})
        _grade_a = load_grade_a_card()

        # Tier counts for the meta block
        _tier_counts: dict[str, int] = {"follow": 0, "watch": 0, "fade": 0, "insufficient": 0}
        for fol_entry in _followability.values():
            t_key = fol_entry.get("follow_tier") or "insufficient"
            _tier_counts[t_key] = _tier_counts.get(t_key, 0) + 1

        # Proven-rotator count: funds with rotation_iq.n_calls>=6 AND hit_rate>=0.5
        # AND tier != "fade" (FIX 6: replaces first-row namespace hack in template)
        _n_proven_rotators = sum(
            1 for slug, fol_entry in _followability.items()
            if fol_entry.get("follow_tier") != "fade"
            and (fol_entry.get("rotation_iq") or {}).get("n_calls", 0) >= 6
            and ((fol_entry.get("rotation_iq") or {}).get("hit_rate") or 0.0) >= 0.5
        )

        follow_desk = {
            "followability": _followability,
            "best_buys": _best_buys,
            "small_mid": _small_mid,
            "sector_consensus": _consensus,
            "grade_a": _grade_a,
            "memory": _memory,  # SM4-R2: 4-quarter fund memory block
            "meta": {
                "n_follow": _tier_counts["follow"],
                "n_watch": _tier_counts["watch"],
                "n_fade": _tier_counts["fade"],
                "n_insufficient": _tier_counts["insufficient"],
                "n_proven_rotators": _n_proven_rotators,
                "phase_s": round(time.monotonic() - t45, 2),
                "fingerprint": _fingerprint,
                "computed_at": _follow_computed_at,
            },
        }

        # Write follow-desk artifact
        try:
            (_site_dir() / "smartmoney_follow.json").write_text(_jdump(follow_desk))
        except Exception as _e_fw:
            log.warning("write smartmoney_follow.json failed: %s", _e_fw)

        log.info(
            "follow-desk: follow=%d watch=%d fade=%d insufficient=%d | "
            "best_buys=%d small_mid=%d consensus_sectors=%d grade_a=%s",
            _tier_counts["follow"], _tier_counts["watch"],
            _tier_counts["fade"], _tier_counts["insufficient"],
            len(_best_buys), len(_small_mid), len(_consensus),
            "yes" if _grade_a else "no",
        )
    except Exception as e:  # noqa: BLE001 — NEVER-BREAK: follow desk must not break the build
        log.warning("follow-desk phase failed — desk degrades gracefully: %s", e)
        follow_desk = {}
    phase_times["follow"] = round(time.monotonic() - t45, 2)

    # ---- Phase 5: ledger advance (nightly-only) ----
    t5 = time.monotonic()
    ledger_added: dict = {}
    manager_history: dict = {}
    try:
        from engine.ownership_ledger import advance_ledgers, ledger_summary
        # L5 cohort: the conviction-buys composite earns a forward record
        # (additive kwarg — advance_ledgers(funds, sm) still works without it).
        ledger_added = advance_ledgers(funds, sm, models=flow.get("models"))
        ledger = ledger_summary()
    except Exception as e:  # noqa: BLE001
        log.warning("ledger advance/summary failed: %s", e)
        ledger = {}
    try:
        from engine.manager_history import (advance_manager_history,
                                            manager_history_summary)
        _manager_history_added = advance_manager_history(
            (follow_desk.get("memory") or {}) if follow_desk else {})
        manager_history = manager_history_summary()
        manager_history["added_this_run"] = _manager_history_added
    except Exception as e:  # noqa: BLE001
        log.warning("manager grade/excess history advance failed: %s", e)
        manager_history = {}
    phase_times["ledger"] = round(time.monotonic() - t5, 2)
    # "boards" keeps meaning the Phase-4 board assembly only — the new v3
    # phases are timed separately and subtracted so the benchmark stays honest.
    phase_times["boards"] = round(
        time.monotonic() - t4 - phase_times["ledger"]
        - phase_times.get("insider_intel", 0)
        - phase_times.get("fund_intel", 0)
        - phase_times.get("flow", 0)
        - phase_times.get("follow", 0), 2)

    built = datetime.now(timezone.utc).isoformat()

    # Typed operational receipt: distinguishes a healthy no-new-filing poll from
    # a stale collector or an unresolved post-deadline roster.  GitHub's narrow
    # filing-season workflow fails loudly on collection/publish errors; this
    # artifact lets the page and production probes inspect the same state.
    transition_health: dict = {}
    try:
        import pandas as pd
        run_path = config.data_dir() / "smart_money" / "smart_money_runs.parquet"
        collector_checked = None
        if run_path.exists():
            runs = pd.read_parquet(run_path)
            if len(runs.index):
                collector_checked = str(pd.to_datetime(runs.index).max().date())
        receipt_path = config.data_dir() / "smart_money" / "filing_receipts.parquet"
        receipt_count = (len(pd.read_parquet(receipt_path))
                         if receipt_path.exists() else 0)
        violations: list[str] = []
        if not collector_checked:
            violations.append("collector heartbeat unavailable")
        else:
            age_d = (datetime.now(timezone.utc).date()
                     - pd.Timestamp(collector_checked).date()).days
            if age_d > 3:
                violations.append(f"collector heartbeat is {age_d}d old")
        if (clock.get("quarter_state") == "window_closed"
                and filing_transition.get("pending_count", 0) > 0):
            violations.append(
                f"deadline passed with {filing_transition.get('pending_count')} unresolved funds")
        transition_health = {
            "status": "warning" if violations else "ok",
            "violations": violations,
            "collector_checked": collector_checked,
            "latest_filing_date": max(
                (str(row.get("filing_date") or "")
                 for row in clock.get("filed_pending", [])), default="") or None,
            "expected_period": filing_transition.get("expected_period"),
            "canonical_period": filing_transition.get("canonical_period"),
            "filed_count": filing_transition.get("filed_count", 0),
            "active_count": filing_transition.get("active_count", 0),
            "receipt_count": receipt_count,
            "generated_at": built,
        }
        quality_path = config.ROOT / "data" / "quality" / "smart_money_freshness.json"
        quality_path.parent.mkdir(parents=True, exist_ok=True)
        quality_path.write_text(_jdump(transition_health))
        (_site_dir() / "smartmoney_health.json").write_text(_jdump(transition_health))
    except Exception as e:  # noqa: BLE001
        log.warning("smart-money transition health receipt failed: %s", e)

    # Freshness block (SM2-R11 required)
    freshness_block = {
        "axes": freshness,
        "quarter_end": clock.get("quarter_end", _STALE),
        "next_deadline": clock.get("next_deadline", _STALE),
        "days_to_deadline": clock.get("days_to_deadline"),
        "quarter_state": clock.get("quarter_state", _STALE),
        "filed_pending": clock.get("filed_pending", []),
    }

    # Balanced display slice: the wire itself is newest-first across ALL axes, so a
    # naive top-60 render would show only the fast axes (daily insider/13dg) between
    # 13F filing windows. wire_display keeps the newest 20 rows PER normalized axis
    # (13f incl. amendments / 13dg / insider), merged newest-first — additive key,
    # display concern only.
    def _axis_norm(r: dict) -> str:
        ax = r.get("axis") or ""
        if ax.startswith("form4"):
            return "insider"
        if ax == "13f" and r.get("type") == "13f_amendment":
            return "13fa"     # amendments are dated later than the originals and
                              # would otherwise crowd out every rotation delta
        return ax
    _DISPLAY_CAPS = {"13f": 20, "13fa": 8, "13dg": 20, "insider": 20}
    wire_display: list[dict] = []
    for ax_key, cap in _DISPLAY_CAPS.items():
        ax_rows = [r for r in wire if _axis_norm(r) == ax_key]
        wire_display.extend(ax_rows[:cap])
    wire_display.sort(key=lambda r: r.get("date", ""), reverse=True)
    # F4: fold marking — these rows are the SAME dict objects as in `wire`, so
    # the flag lands in both lists. The template renders the FULL wire and folds
    # to data-fold="1" rows by default; "See more" reveals the rest client-side.
    for _r in wire_display:
        _r["_fold"] = 1

    desk: dict = {
        "built": built,
        "freshness": freshness_block,
        "filing_transition": filing_transition,
        "institutional_census": institutional_census,
        "transition_health": transition_health,
        "wire": wire,
        "wire_display": wire_display,
        "initiations": initiations,
        "grand_portfolio": grand_portfolio,
        "crowding": crowding,
        "activists": activists,
        "managers": managers,
        "insider_intel": insider_intel,
        "flow": flow,
        "fund_intel_index": fund_intel_index,
        "ledger": ledger,
        "manager_history": manager_history,
        "follow": follow_desk,
    }

    try:
        (_site_dir() / "smartmoney_desk.json").write_text(_jdump(desk))
        desk_kb = len(_jdump(desk)) // 1024
    except Exception as e:  # noqa: BLE001
        log.warning("write smartmoney_desk.json failed: %s", e)
        desk_kb = 0

    phase_times["total"] = round(time.monotonic() - t0, 2)

    # ---- Phase 6: template render ----
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        html = env.get_template("smart_money.html.j2").render(
            trk=tracker or {},
            generated_utc=generated_utc,
            active_section="us",
            active_page="smart_money",
            desk=desk,  # E3 template will consume this; current template ignores unknown vars
        )
        write_page(config.ROOT / "site" / "smart_money.html", html)
        log.info("wrote smart_money.html (%d KB)", len(html) // 1024)
    except Exception as e:  # noqa: BLE001
        log.warning("smart-money render failed — JSONs written, page skipped: %s", e)

    # ---- Phase 6.5: fund dossier pages AT SITE ROOT (F6: report_base.html.j2
    # hardcodes root-relative theme.css/theme.js, so site/fund_<slug>.html needs
    # no nav_prefix). Per-fund try/except — one bad book never kills the rest. ----
    t65 = time.monotonic()
    n_dossiers = 0
    if ((sm_cfg.get("dossier", {}) or {}).get("enabled", True)) and fund_intel_latest.get("funds"):
        _lb_rows = {r.get("slug"): r for r in (tracker or {}).get("leaderboard", [])}
        _by_fund = (tracker or {}).get("by_fund", {}) or {}
        dossier_tpl = None
        try:
            dossier_tpl = env.get_template("fund_dossier.html.j2")
        except Exception as e:  # noqa: BLE001
            log.warning("fund_dossier template unavailable — dossiers skipped: %s", e)
        if dossier_tpl is not None:
            for slug, fi in (fund_intel_latest.get("funds") or {}).items():
                try:
                    html_fund = dossier_tpl.render(
                        slug=slug,
                        fi=fi,
                        lb_row=_lb_rows.get(slug) or {},
                        bf=_by_fund.get(slug) or {},
                        desk=desk,
                        generated_utc=generated_utc,
                        active_section="us",
                        active_page="smart_money",
                    )
                    write_page(config.ROOT / "site" / f"fund_{slug}.html", html_fund)
                    n_dossiers += 1
                except Exception as e:  # noqa: BLE001
                    log.warning("fund dossier render failed for %s: %s", slug, e)
        # Fund directory page — own try/except, degrades to no page.
        try:
            index_rows = []
            for slug, fi in (fund_intel_latest.get("funds") or {}).items():
                lb = _lb_rows.get(slug) or {}
                sc = (_by_fund.get(slug) or {}).get("scorecard") or {}
                meta = fi.get("book_meta") or {}
                core = (fi.get("theme_read") or {}).get("core") or {}
                index_rows.append({
                    "slug": slug,
                    "name": (funds.get(slug) or {}).get("name", slug),
                    "style": (funds.get(slug) or {}).get("style"),
                    "status": (funds.get(slug) or {}).get("status"),
                    "grade": lb.get("grade"),
                    "reliability": lb.get("reliability") or sc.get("reliability"),
                    "core_lean_label": core.get("label"),
                    "core_lean_label_zh": core.get("label_zh"),
                    "book_value_usd": meta.get("book_value_usd"),
                    "n_positions": meta.get("n_positions"),
                    "href": f"fund_{slug}.html",
                })
            index_rows.sort(key=lambda r: -(r.get("book_value_usd") or 0))
            html_idx = env.get_template("fund_index.html.j2").render(
                rows=index_rows,
                desk=desk,
                generated_utc=generated_utc,
                active_section="us",
                active_page="smart_money",
            )
            write_page(config.ROOT / "site" / "fund_index.html", html_idx)
            log.info("wrote fund_index.html (%d funds) + %d dossier pages",
                     len(index_rows), n_dossiers)
        except Exception as e:  # noqa: BLE001
            log.warning("fund_index render failed — directory page skipped: %s", e)
    phase_times["dossiers"] = round(time.monotonic() - t65, 2)

    # Benchmark log (SM2-R12)
    _fol_meta = (follow_desk.get("meta") or {})
    log.info(
        "build_smart_money BENCHMARK: total=%.1fs | tracker=%.1fs smart_money=%.1fs "
        "wire=%.1fs boards=%.1fs insider_intel=%.1fs fund_intel=%.1fs flow=%.1fs "
        "follow=%.1fs ledger=%.1fs dossiers=%.1fs | "
        "desk=%dKB wire_rows=%d initiations=%d crowding=%d activists=%d "
        "dossier_pages=%d ledger_added=%s | "
        "follow: follow=%d watch=%d fade=%d insufficient=%d best_buys=%d",
        phase_times["total"],
        phase_times.get("tracker", 0),
        phase_times.get("smart_money", 0),
        phase_times.get("wire", 0),
        phase_times.get("boards", 0),
        phase_times.get("insider_intel", 0),
        phase_times.get("fund_intel", 0),
        phase_times.get("flow", 0),
        phase_times.get("follow", 0),
        phase_times.get("ledger", 0),
        phase_times.get("dossiers", 0),
        desk_kb,
        len(wire),
        len(initiations),
        len(crowding),
        len(activists),
        n_dossiers,
        ledger_added,
        _fol_meta.get("n_follow", 0),
        _fol_meta.get("n_watch", 0),
        _fol_meta.get("n_fade", 0),
        _fol_meta.get("n_insufficient", 0),
        len((follow_desk.get("best_buys") or [])),
    )

    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--census-render-only"]:
        sys.exit(render_institutional_census_only())
    sys.exit(main())
