#!/usr/bin/env python3
"""Build a private, point-in-time forensic replay docket from authorized Oracle history.

This is a Wave-0 research harness, not a signal engine.  It deliberately separates:

* selection (ticker, direction, setup and observed entry),
* contract construction (option/underlying choice and observed option terms), and
* retrospective management/outcomes.

Historical issue times are absent from the authorized source.  The harness never invents
one: every case keeps ``exact_timestamp=null`` and emits open/midday/close-boundary cutoff
requirements for sensitivity analysis.  Every future feature join must carry event time,
availability time, vintage/revision identity, missingness and quality.

Privacy boundary
----------------
The authorized input, normalized replay cases, and per-case feature requirements are
private.  CLI execution refuses to put them anywhere inside the repository.  The only
repo-safe artifact is a strict-schema aggregate receipt containing counts and coverage,
never tickers, raw rows, authorization prose, or the authorization image.

Authority boundary
------------------
All output is research-only.  It creates no Prophet or Neural-Web authority, advances no
ledger, originates no signal, and performs no automatic training.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
import tempfile
import unicodedata
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
CONTRACT_DIR = REPO_ROOT / "contracts" / "research"

INPUT_SCHEMA = CONTRACT_DIR / "momoedge_oracle_history_authorized.v1.schema.json"
CASE_SCHEMA = CONTRACT_DIR / "momoedge_oracle_replay_case.v1.schema.json"
FEATURE_RECEIPT_SCHEMA = CONTRACT_DIR / "momoedge_oracle_asof_feature_receipt.v1.schema.json"
AGGREGATE_SCHEMA = CONTRACT_DIR / "momoedge_oracle_replay_receipt.v1.schema.json"
THETA_REMOTE_INVENTORY_SCHEMA = (
    CONTRACT_DIR / "momoedge_theta_remote_inventory_aggregate.v1.schema.json"
)

INPUT_SCHEMA_ID = "momoedge.oracle_history_authorized/v1"
CASE_SCHEMA_ID = "momoedge.oracle_forensic_replay_case/v1"
FEATURE_RECEIPT_SCHEMA_ID = "momoedge.oracle_asof_feature_receipt_requirement/v1"
AGGREGATE_SCHEMA_ID = "momoedge.oracle_history_replay_wave0_receipt/v1"
THETA_REMOTE_INVENTORY_SCHEMA_ID = "momoedge.theta_remote_inventory_aggregate/v1"

FEATURE_FAMILIES = (
    "price_technical",
    "macro_regime",
    "options_flow_campaign",
    "gex_vol_oi",
    "news_alt_data",
)

CUTOFF_SPECS = (
    ("market_open", time(9, 30)),
    ("mid_session", time(12, 0)),
    ("market_close_boundary", time(15, 59)),
)
MARKET_TIMEZONE = "America/New_York"
THETA_REMOTE_PREFIX = "thetadata_eod"
THETA_TIERS = ("eod", "oi", "greeks")

AUTHORITY = {
    "tier": "research_only",
    "prophet": "none",
    "neural_web": "none",
    "signal_origination": False,
    "automatic_training": False,
}

REQUIRED_EVIDENCE: dict[str, list[str]] = {
    "price_technical": [
        "intraday_price_snapshot",
        "daily_price_history_through_cutoff",
        "adjustment_vintage",
        "technical_feature_values",
        "event_time",
        "available_at",
    ],
    "macro_regime": [
        "macro_release_vintage",
        "regime_state_as_known",
        "breadth_state_as_known",
        "event_time",
        "available_at",
    ],
    "options_flow_campaign": [
        "trade_prints_or_honest_null",
        "nbbo_at_print_or_honest_null",
        "signing_method",
        "campaign_cluster_state",
        "contract_liquidity",
        "event_time",
        "available_at",
    ],
    "gex_vol_oi": [
        "chain_snapshot",
        "iv_surface",
        "greeks_snapshot",
        "open_interest_prior_session",
        "gex_levels",
        "event_time",
        "available_at",
    ],
    "news_alt_data": [
        "published_at",
        "first_seen_at",
        "source_identity",
        "entity_linkage",
        "alt_data_vintage_or_honest_null",
        "available_at",
    ],
}


class ReplayInputError(ValueError):
    """Safe validation error that never echoes private field values."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:24]}"


def _normalize_ticker(value: object) -> str:
    """Remove display-only Unicode controls without changing ticker punctuation."""
    normalized = "".join(
        char for char in str(value) if unicodedata.category(char) != "Cf"
    ).strip().upper()
    if not normalized:
        raise ReplayInputError("ticker is empty after display-control normalization")
    return normalized


def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_document(document: Any, schema_path: Path) -> None:
    """Validate against Draft 2020-12 without echoing a private invalid value."""
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:  # pragma: no cover - repo CI installs jsonschema
        raise RuntimeError("jsonschema is required for the replay harness") from exc

    validator = Draft202012Validator(
        _load_schema(schema_path),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(document), key=lambda err: list(err.absolute_path))
    if not errors:
        return
    err = errors[0]
    pointer = "/" + "/".join(str(item) for item in err.absolute_path)
    pointer = pointer if pointer != "/" else "<root>"
    raise ReplayInputError(
        f"{schema_path.name} rejected {pointer}: schema rule {err.validator!s} failed"
    )


def _parse_mdy(value: str, field: str) -> date:
    try:
        return datetime.strptime(value, "%m-%d-%Y").date()
    except (TypeError, ValueError) as exc:
        raise ReplayInputError(f"{field}: invalid calendar date") from exc


def _parse_expiration(value: str, field: str) -> date:
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m-%d-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except (TypeError, ValueError):
            continue
    raise ReplayInputError(f"{field}: unsupported expiration date format")


def _semantic_validate(history: dict[str, Any]) -> None:
    records = history["records"]
    summary = history["displayed_summary"]
    if summary["trades"] != len(records):
        raise ReplayInputError("displayed_summary.trades does not equal records length")
    if summary["wins_displayed"] > summary["trades"]:
        raise ReplayInputError("displayed_summary.wins_displayed exceeds trades")

    indexes = [record["source_index"] for record in records]
    if len(indexes) != len(set(indexes)):
        raise ReplayInputError("records.source_index values are not unique")

    for position, record in enumerate(records):
        issue = _parse_mdy(record["issued_date"], f"records/{position}/issued_date")
        if record["closed_date"] is not None:
            closed = _parse_mdy(record["closed_date"], f"records/{position}/closed_date")
            if closed < issue:
                raise ReplayInputError(f"records/{position}/closed_date predates issued_date")
        if record["option"] is not None:
            _parse_expiration(
                record["option"]["expiration"],
                f"records/{position}/option/expiration",
            )


def load_and_validate_history(
    input_path: Path,
    *,
    schema_path: Path = INPUT_SCHEMA,
) -> tuple[dict[str, Any], str]:
    """Read and validate the private input, returning document and content fingerprint."""
    payload = input_path.read_bytes()
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayInputError("authorized history input is not valid UTF-8 JSON") from exc
    validate_document(document, schema_path)
    _semantic_validate(document)
    return document, _sha256_bytes(payload)


def _market_session_state(issue_date: date) -> str:
    try:
        from lib.nyse_calendar import is_session

        return "session" if is_session(issue_date) else "non_session"
    except Exception:  # noqa: BLE001 - receipt must preserve calendar uncertainty
        return "calendar_unavailable"


def cutoff_sensitivity(issue_date: date) -> list[dict[str, Any]]:
    """Three scenario cutoffs; none is asserted to be the historical issue time."""
    tz = ZoneInfo(MARKET_TIMEZONE)
    return [
        {
            "cutoff_id": cutoff_id,
            "candidate_as_of": datetime.combine(issue_date, cutoff, tzinfo=tz).isoformat(),
            "timezone": MARKET_TIMEZONE,
            "sensitivity_only": True,
        }
        for cutoff_id, cutoff in CUTOFF_SPECS
    ]


def derive_cohort_policy(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Infer display-format cohorts without claiming true server-engine versions."""
    option_dates = [
        _parse_mdy(record["issued_date"], "issued_date")
        for record in records
        if record["instrument"] == "option"
    ]
    underlying_dates = [
        _parse_mdy(record["issued_date"], "issued_date")
        for record in records
        if record["instrument"] == "underlying"
    ]
    return {
        "basis": "observed_instrument_format_frontiers",
        "first_observed_option_issue": min(option_dates).isoformat() if option_dates else None,
        "last_observed_underlying_issue": (
            max(underlying_dates).isoformat() if underlying_dates else None
        ),
        "inferred": True,
        "true_engine_version_claimed": False,
    }


def cohort_id_for_date(issue_date: date, policy: dict[str, Any]) -> str:
    first_option = (
        date.fromisoformat(policy["first_observed_option_issue"])
        if policy["first_observed_option_issue"]
        else None
    )
    last_underlying = (
        date.fromisoformat(policy["last_observed_underlying_issue"])
        if policy["last_observed_underlying_issue"]
        else None
    )
    if first_option is None or issue_date < first_option:
        return "pre_option_format"
    if last_underlying is not None and issue_date <= last_underlying:
        return "mixed_format_transition"
    return "post_underlying_format"


def _temporal_quality(record: dict[str, Any]) -> dict[str, Any]:
    """Preserve raw dates and flag source inconsistencies without correcting them."""
    issue = _parse_mdy(record["issued_date"], "issued_date")
    closed = (
        _parse_mdy(record["closed_date"], "closed_date")
        if record["closed_date"] is not None
        else None
    )
    option = record["option"]
    expiration = (
        _parse_expiration(option["expiration"], "option.expiration")
        if option is not None
        else None
    )
    calendar_days = (closed - issue).days if closed is not None else None
    close_minus_expiration = (
        (closed - expiration).days
        if closed is not None and expiration is not None
        else None
    )
    reported_holding_end_minus_expiration = (
        (issue + timedelta(days=record["days_held"]) - expiration).days
        if record["days_held"] is not None and expiration is not None
        else None
    )

    flags: list[str] = []
    issue_year_shift_candidate: date | None = None
    if closed is None:
        flags.append("missing_close_date")
    elif (
        record["days_held"] is not None
        and calendar_days is not None
        and calendar_days >= 300
        and record["days_held"] <= 60
        and closed.year == issue.year + 1
    ):
        try:
            candidate = issue.replace(year=issue.year + 1)
        except ValueError:
            candidate = issue.replace(year=issue.year + 1, day=28)
        candidate_days = (closed - candidate).days
        # ``days_held`` may be trading rather than calendar days; the bounded window
        # identifies only the obvious one-year display conflict and does not rewrite it.
        if candidate_days >= 0 and abs(candidate_days - record["days_held"]) <= 14:
            flags.append("issue_close_days_held_year_conflict")
            issue_year_shift_candidate = candidate
    if (
        reported_holding_end_minus_expiration is not None
        and reported_holding_end_minus_expiration > 0
    ):
        flags.append("reported_holding_interval_after_option_expiration")
    if not flags:
        flags = ["clean"]

    has_anomaly = flags != ["clean"]
    if option is None:
        expiry_return = "not_applicable"
    elif has_anomaly:
        expiry_return = "excluded_temporal_quality"
    else:
        expiry_return = "eligible"
    return {
        "raw_source_values": {
            "issued_date": record["issued_date"],
            "closed_date": record["closed_date"],
            "days_held": record["days_held"],
            "option_expiration": option["expiration"] if option is not None else None,
        },
        "derived_diagnostics": {
            "calendar_days_issue_to_close": calendar_days,
            "issue_year_shift_candidate": (
                issue_year_shift_candidate.isoformat()
                if issue_year_shift_candidate is not None
                else None
            ),
            "close_minus_option_expiration_days": close_minus_expiration,
            "reported_holding_end_minus_option_expiration_days": (
                reported_holding_end_minus_expiration
            ),
        },
        "quality_flags": flags,
        "normalization_only": True,
        "correction_overlay": {
            "state": "required_unresolved" if has_anomaly else "not_required",
            "applied": False,
            "raw_source_values_retained": True,
        },
        "replay_eligibility": {
            "overlap_allocation": (
                "excluded_temporal_quality" if has_anomaly else "eligible"
            ),
            "expiry_return": expiry_return,
        },
    }


def build_replay_cases(
    history: dict[str, Any],
    input_sha256: str,
    *,
    validate_outputs: bool = True,
) -> list[dict[str, Any]]:
    policy = derive_cohort_policy(history["records"])
    cases: list[dict[str, Any]] = []
    for record in history["records"]:
        issue = _parse_mdy(record["issued_date"], "issued_date")
        option = record["option"]
        case_id = _stable_id("momo_case", input_sha256, record["source_index"])
        contract_state = "observed_retro_record" if option is not None else "not_applicable"
        contract_unknown = (
            [
                "quote_timestamp",
                "bid",
                "ask",
                "spread",
                "delta",
                "iv",
                "open_interest_available_at",
                "contract_candidate_set",
                "slippage",
            ]
            if option is not None
            else []
        )
        case = {
            "schema": CASE_SCHEMA_ID,
            "case_id": case_id,
            "source_record_index": record["source_index"],
            "issue_date": issue.isoformat(),
            "issue_time": {
                "state": "unknown_date_only",
                "exact_timestamp": None,
                "timezone": MARKET_TIMEZONE,
                "market_session_state": _market_session_state(issue),
                "cutoff_sensitivity": cutoff_sensitivity(issue),
            },
            "cohort": {
                "cohort_id": cohort_id_for_date(issue, policy),
                "basis": policy["basis"],
                "inferred": True,
                "true_engine_version_claimed": False,
            },
            "temporal_quality": _temporal_quality(record),
            "decision_layers": {
                "selection": {
                    "state": "observed_retro_record",
                    "ticker": _normalize_ticker(record["ticker"]),
                    "direction": record["direction"],
                    "setup_raw": record["setup"],
                    "underlying_entry": record["underlying"]["entry"],
                    "unknown_at_issue": [
                        "issue_timestamp",
                        "selection_rank",
                        "candidate_universe",
                        "suppressed_candidates",
                        "initial_stop",
                        "initial_targets",
                    ],
                },
                "contract_construction": {
                    "state": contract_state,
                    "instrument": record["instrument"],
                    "contract": option["contract"] if option is not None else None,
                    "expiration": (
                        _parse_expiration(option["expiration"], "option.expiration").isoformat()
                        if option is not None
                        else None
                    ),
                    "premium_paid": option["premium_paid"] if option is not None else None,
                    "unknown_at_issue": contract_unknown,
                },
                "management": {
                    "state": "retrospective_outcome",
                    "closed_date": (
                        _parse_mdy(record["closed_date"], "closed_date").isoformat()
                        if record["closed_date"] is not None
                        else None
                    ),
                    "days_held": record["days_held"],
                    "table_status": record["table_status"],
                    "detail_status": record["detail_status"],
                    "status_disagreement": record["table_status"] != record["detail_status"],
                    "confidence_pct_observed": record["confidence_pct"],
                    "confidence_temporal_semantics": "unknown_retro_display",
                    "underlying_exit": record["underlying"]["exit"],
                    "underlying_return_pct": record["underlying"]["return_pct"],
                    "option_premium_exit": option["premium_exit"] if option is not None else None,
                    "option_return_pct": option["return_pct"] if option is not None else None,
                    "option_leverage_x": option["leverage_x"] if option is not None else None,
                    "contracts_observed": option["contracts"] if option is not None else None,
                    "dollar_pnl_observed": option["dollar_pnl"] if option is not None else None,
                    "unobserved_lifecycle": [
                        "management_event_timestamps",
                        "partial_exit_sequence",
                        "target_or_stop_first_passage",
                        "alerts_delivered",
                        "realized_execution_costs",
                    ],
                },
            },
            "required_feature_families": list(FEATURE_FAMILIES),
            "authority": dict(AUTHORITY),
        }
        if validate_outputs:
            validate_document(case, CASE_SCHEMA)
        cases.append(case)
    return sorted(cases, key=lambda item: (item["issue_date"], item["source_record_index"]))


def _decision_layers_for_family(case: dict[str, Any], family: str) -> list[str]:
    option_case = case["decision_layers"]["contract_construction"]["instrument"] == "option"
    if family in {"price_technical", "options_flow_campaign", "gex_vol_oi"}:
        layers = ["selection"]
        if option_case:
            layers.append("contract_construction")
        layers.append("management")
        return layers
    return ["selection", "management"]


def build_feature_receipt_requirements(
    cases: Iterable[dict[str, Any]],
    *,
    validate_outputs: bool = True,
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for case in cases:
        for cutoff in case["issue_time"]["cutoff_sensitivity"]:
            for family in FEATURE_FAMILIES:
                candidate_as_of = cutoff["candidate_as_of"]
                receipt = {
                    "schema": FEATURE_RECEIPT_SCHEMA_ID,
                    "receipt_id": _stable_id(
                        "momo_feat",
                        case["case_id"],
                        cutoff["cutoff_id"],
                        family,
                    ),
                    "case_id": case["case_id"],
                    "family": family,
                    "decision_layers": _decision_layers_for_family(case, family),
                    "cutoff_id": cutoff["cutoff_id"],
                    "candidate_as_of": candidate_as_of,
                    "issue_time_state": "unknown_date_only",
                    "status": "required_unresolved",
                    "point_in_time_contract": {
                        "event_time_lte": candidate_as_of,
                        "available_at_lte": candidate_as_of,
                        "source_vintage_required": True,
                        "revision_identity_required": True,
                        "missingness_required": True,
                        "quality_required": True,
                        "same_day_eod_requires_observed_availability": True,
                        "unknown_issue_time_uses_prior_session_daily_state": True,
                        "issue_day_eod_not_assumed_available": True,
                    },
                    "required_evidence": REQUIRED_EVIDENCE[family],
                    "evidence": [],
                }
                if validate_outputs:
                    validate_document(receipt, FEATURE_RECEIPT_SCHEMA)
                receipts.append(receipt)
    return receipts


def _parquet_dates(frame: Any, *, candidates: tuple[str, ...] = ()) -> set[date]:
    import pandas as pd

    for column in candidates:
        if column in frame.columns:
            parsed = pd.to_datetime(frame[column], errors="coerce", utc=True)
            return set(parsed.dropna().dt.date)
    parsed_index = pd.to_datetime(frame.index, errors="coerce", utc=True)
    return set(parsed_index[~pd.isna(parsed_index)].date)


def _read_parquet(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        import pandas as pd

        return pd.read_parquet(path)
    except Exception:  # noqa: BLE001 - coverage audit is honest-null, never fatal
        return None


def _record_pairs(records: list[dict[str, Any]]) -> list[tuple[str, date]]:
    return [
        (_normalize_ticker(record["ticker"]), _parse_mdy(record["issued_date"], "issued_date"))
        for record in records
    ]


def _coverage_count(records: list[dict[str, Any]], pairs: set[tuple[str, date]]) -> int:
    return sum(pair in pairs for pair in _record_pairs(records))


def _ticker_date_parquet_pairs(
    repo_root: Path,
    records: list[dict[str, Any]],
    pattern: str,
    *,
    date_columns: tuple[str, ...] = (),
) -> tuple[set[tuple[str, date]], int]:
    pairs: set[tuple[str, date]] = set()
    files = 0
    for ticker in sorted({_normalize_ticker(record["ticker"]) for record in records}):
        path = repo_root / pattern.format(ticker=ticker)
        frame = _read_parquet(path)
        if frame is None:
            continue
        files += 1
        pairs.update((ticker, value) for value in _parquet_dates(frame, candidates=date_columns))
    return pairs, files


def _parse_ticker_collection(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            parsed = [part.strip() for part in value.split(",") if part.strip()]
        value = parsed
    if hasattr(value, "tolist") and not isinstance(value, (list, tuple, set)):
        value = value.tolist()
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).upper() for item in value if str(item).strip()]


def _theta_supporting_counts(
    repo_root: Path,
    records: list[dict[str, Any]],
) -> tuple[dict[str, int], bool]:
    store: Path | None = None
    if repo_root.resolve() == REPO_ROOT.resolve():
        try:
            from engine.thetadata_store import resolve_thetadata_store

            store = resolve_thetadata_store(
                required=False,
                purpose="momoedge-history-replay-wave0",
            )
        except Exception:  # noqa: BLE001 - audit reports unresolved store
            store = None
    else:
        candidate = repo_root / "data" / "thetadata_eod"
        if any((candidate / tier).is_dir() for tier in ("eod", "oi", "greeks")):
            store = candidate

    counts: dict[str, int] = {
        "theta_eod_yearfile_records": 0,
        "theta_oi_yearfile_records": 0,
        "theta_greeks_yearfile_records": 0,
    }
    if store is None:
        return counts, False
    for tier, key in (
        ("eod", "theta_eod_yearfile_records"),
        ("oi", "theta_oi_yearfile_records"),
        ("greeks", "theta_greeks_yearfile_records"),
    ):
        counts[key] = sum(
            (
                store
                / tier
                / _normalize_ticker(record["ticker"])
                / f"{_parse_mdy(record['issued_date'], 'issued_date').year}.parquet"
            ).is_file()
            for record in records
        )
    return counts, True


def build_theta_selective_restore_plan(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a private, current-prefix-only plan for the required root/year shards.

    The plan contains authorized roots and therefore belongs only in the guarded private
    output directory.  It deliberately omits the duplicated ``*.OLD`` families and does
    not download anything.
    """
    pairs = sorted(
        {
            (
                _normalize_ticker(record["ticker"]),
                _parse_mdy(record["issued_date"], "issued_date").year,
            )
            for record in records
        }
    )
    return [
        {
            "schema": "momoedge.theta_selective_restore_plan_row_private/v1",
            "tier": tier,
            "root": root,
            "year": year,
            "key": f"{THETA_REMOTE_PREFIX}/{tier}/{root}/{year}.parquet",
            "relative_restore_path": f"{tier}/{root}/{year}.parquet",
            "inventory_state": "not_probed",
            "content_length": None,
            "etag": None,
            "last_modified": None,
            "selective_restore_only": True,
        }
        for tier in THETA_TIERS
        for root, year in pairs
    ]


def _datetime_as_z(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayInputError("R2 inventory returned an invalid object timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _targeted_head(client: Any, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:  # noqa: BLE001 - botocore is an optional CLI dependency
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        # Never echo the private key, bucket, endpoint, or exception message.
        raise ReplayInputError("targeted R2 inventory HEAD failed") from exc


def probe_theta_remote_inventory(
    history: dict[str, Any],
    input_sha256: str,
    *,
    client: Any,
    bucket: str,
    generated_at: str | None = None,
    validate_output: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """HEAD only the authorized root/year objects; return aggregate + private plan.

    This function never lists a prefix and never GETs object content.  A future selective
    restore can consume the private plan, but Wave 0 performs inventory only.
    """
    records = history["records"]
    plan = build_theta_selective_restore_plan(records)
    manifest_head = _targeted_head(
        client,
        bucket,
        f"{THETA_REMOTE_PREFIX}/_manifest.json",
    )
    manifest_last_modified = (
        _datetime_as_z(manifest_head.get("LastModified")) if manifest_head else None
    )

    available_pairs: dict[str, set[tuple[str, int]]] = {
        tier: set() for tier in THETA_TIERS
    }
    tier_bytes: Counter[str] = Counter()
    for row in plan:
        head = _targeted_head(client, bucket, row["key"])
        if head is None:
            row["inventory_state"] = "missing"
            continue
        content_length = int(head.get("ContentLength", 0))
        row.update(
            {
                "inventory_state": "available",
                "content_length": content_length,
                "etag": str(head.get("ETag", "")).strip('"') or None,
                "last_modified": _datetime_as_z(head.get("LastModified")),
            }
        )
        pair = (row["root"], row["year"])
        available_pairs[row["tier"]].add(pair)
        tier_bytes[row["tier"]] += content_length

    record_pairs = [
        (
            _normalize_ticker(record["ticker"]),
            _parse_mdy(record["issued_date"], "issued_date").year,
        )
        for record in records
    ]
    required_pairs = set(record_pairs)
    all_tiers_pairs = set.intersection(
        *(available_pairs[tier] for tier in THETA_TIERS)
    )
    tiers = [
        {
            "tier": tier,
            "required_objects": len(required_pairs),
            "available_objects": len(available_pairs[tier]),
            "candidate_issue_records": sum(
                pair in available_pairs[tier] for pair in record_pairs
            ),
            "available_bytes": tier_bytes[tier],
        }
        for tier in THETA_TIERS
    ]
    inventory = {
        "schema": THETA_REMOTE_INVENTORY_SCHEMA_ID,
        "generated_at": (
            generated_at
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "input_schema": INPUT_SCHEMA_ID,
        "input_sha256": input_sha256,
        "inventory_method": "targeted_head_object_current_keys",
        "prefix": THETA_REMOTE_PREFIX,
        "manifest_last_modified": manifest_last_modified,
        "record_count": len(records),
        "required_root_count": len({pair[0] for pair in required_pairs}),
        "required_root_year_pairs": len(required_pairs),
        "tiers": tiers,
        "all_tiers_available_root_count": len(
            {pair[0] for pair in all_tiers_pairs}
        ),
        "all_tiers_available_root_year_pairs": len(all_tiers_pairs),
        "all_tiers_candidate_issue_records": sum(
            pair in all_tiers_pairs for pair in record_pairs
        ),
        "total_available_objects": sum(item["available_objects"] for item in tiers),
        "total_available_bytes": sum(item["available_bytes"] for item in tiers),
        "current_prefix_only": True,
        "legacy_old_prefix_probed": False,
        "objects_downloaded": False,
        "keys_or_tickers_included": False,
        "full_issue_date_rows_verified": False,
    }
    if validate_output:
        validate_document(inventory, THETA_REMOTE_INVENTORY_SCHEMA)
        _semantic_validate_theta_remote_inventory(inventory)
    return inventory, plan


def load_theta_remote_inventory(
    path: Path,
    *,
    expected_input_sha256: str,
) -> dict[str, Any]:
    """Load a prior aggregate-only inventory and bind it to this private input."""
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayInputError("Theta remote inventory is not valid UTF-8 JSON") from exc
    validate_document(inventory, THETA_REMOTE_INVENTORY_SCHEMA)
    _semantic_validate_theta_remote_inventory(inventory)
    if inventory["input_sha256"] != expected_input_sha256:
        raise ReplayInputError("Theta remote inventory does not match authorized input")
    return inventory


def _semantic_validate_theta_remote_inventory(inventory: dict[str, Any]) -> None:
    tiers = inventory["tiers"]
    if {item["tier"] for item in tiers} != set(THETA_TIERS):
        raise ReplayInputError("Theta remote inventory does not contain the three tiers")
    required = inventory["required_root_year_pairs"]
    if any(item["required_objects"] != required for item in tiers):
        raise ReplayInputError("Theta remote inventory requirement counts disagree")
    if any(item["available_objects"] > item["required_objects"] for item in tiers):
        raise ReplayInputError("Theta remote inventory available count exceeds required")
    if any(item["candidate_issue_records"] > inventory["record_count"] for item in tiers):
        raise ReplayInputError("Theta remote inventory candidate count exceeds records")
    if inventory["total_available_objects"] != sum(
        item["available_objects"] for item in tiers
    ):
        raise ReplayInputError("Theta remote inventory object totals disagree")
    if inventory["total_available_bytes"] != sum(item["available_bytes"] for item in tiers):
        raise ReplayInputError("Theta remote inventory byte totals disagree")
    if inventory["all_tiers_available_root_year_pairs"] > required:
        raise ReplayInputError("Theta remote inventory shared coverage exceeds requirements")
    if inventory["all_tiers_available_root_count"] > inventory["required_root_count"]:
        raise ReplayInputError("Theta remote inventory shared root count exceeds requirements")
    if inventory["all_tiers_candidate_issue_records"] > inventory["record_count"]:
        raise ReplayInputError("Theta remote inventory shared candidates exceed records")


def _r2_client_from_env() -> tuple[Any, str]:
    names = (
        "R2_ENDPOINT",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET",
    )
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ReplayInputError(
            "targeted R2 inventory requires configured R2 endpoint, credentials, and bucket"
        )
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - operator-only inventory mode
        raise RuntimeError("boto3 is required for targeted R2 inventory") from exc
    client = boto3.client(
        "s3",
        endpoint_url=values["R2_ENDPOINT"],
        aws_access_key_id=values["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=values["R2_SECRET_ACCESS_KEY"],
    )
    return client, values["R2_BUCKET"]


def build_theta_data_plane_summary(
    repo_root: Path,
    records: list[dict[str, Any]],
    remote_inventory: dict[str, Any] | None,
) -> dict[str, Any]:
    """Distinguish local resolution from targeted remote candidate availability."""
    _, local_resolved = _theta_supporting_counts(repo_root, records)
    required_pairs = {
        (
            _normalize_ticker(record["ticker"]),
            _parse_mdy(record["issued_date"], "issued_date").year,
        )
        for record in records
    }
    if remote_inventory is None:
        return {
            "local_state": "resolved" if local_resolved else "unresolved",
            "r2_state": "not_audited",
            "inventory_method": "not_run",
            "manifest_last_modified": None,
            "required_root_year_pairs": len(required_pairs),
            "candidate_issue_records": 0,
            "current_available_root_count": 0,
            "current_available_objects": 0,
            "current_available_bytes": 0,
            "current_prefix_only": False,
            "legacy_old_prefix_probed": False,
            "selective_restore_state": "planned_not_executed",
            "object_content_downloaded": False,
            "issue_day_eod_policy": "prior_session_only_when_issue_time_unknown",
        }
    return {
        "local_state": "resolved" if local_resolved else "unresolved",
        "r2_state": (
            "available_candidate"
            if remote_inventory["all_tiers_available_root_year_pairs"]
            else "unavailable"
        ),
        "inventory_method": remote_inventory["inventory_method"],
        "manifest_last_modified": remote_inventory["manifest_last_modified"],
        "required_root_year_pairs": remote_inventory["required_root_year_pairs"],
        "candidate_issue_records": remote_inventory[
            "all_tiers_candidate_issue_records"
        ],
        "current_available_root_count": remote_inventory[
            "all_tiers_available_root_count"
        ],
        "current_available_objects": remote_inventory["total_available_objects"],
        "current_available_bytes": remote_inventory["total_available_bytes"],
        "current_prefix_only": remote_inventory["current_prefix_only"],
        "legacy_old_prefix_probed": remote_inventory["legacy_old_prefix_probed"],
        "selective_restore_state": "planned_not_executed",
        "object_content_downloaded": remote_inventory["objects_downloaded"],
        "issue_day_eod_policy": "prior_session_only_when_issue_time_unknown",
    }


def audit_repo_data(
    repo_root: Path,
    records: list[dict[str, Any]],
    *,
    theta_remote_inventory: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Audit only adapter candidates; no feature is asserted PIT-ready from date presence."""
    total = len(records)

    # Price / technical: daily adjusted histories, current vintage and date-only.
    price_pairs, price_files = _ticker_date_parquet_pairs(
        repo_root,
        records,
        "data/yahoo/{ticker}.parquet",
        date_columns=("date", "Date"),
    )
    price_exact = _coverage_count(records, price_pairs)

    # Macro: one genuine PIT-oriented daily store plus a recent accrued market-state store.
    macro_dates: set[date] = set()
    macro_pit_dates: set[date] = set()
    macro_recent_dates: set[date] = set()
    macro_pit = _read_parquet(repo_root / "data" / "regime" / "regime_v2_pit.parquet")
    if macro_pit is not None:
        macro_pit_dates = _parquet_dates(macro_pit)
        macro_dates.update(macro_pit_dates)
    macro_recent = _read_parquet(
        repo_root / "data" / "regime" / "market_state_history.parquet"
    )
    if macro_recent is not None:
        macro_recent_dates = _parquet_dates(macro_recent, candidates=("date", "as_of"))
        macro_dates.update(macro_recent_dates)
    issue_dates = [_parse_mdy(record["issued_date"], "issued_date") for record in records]
    macro_exact = sum(value in macro_dates for value in issue_dates)

    # Options: daily magnitude aggregates are not campaign prints.  Campaign coverage is
    # counted only from the timestamped per-print ledger.
    daily_flow_pairs, daily_flow_files = _ticker_date_parquet_pairs(
        repo_root,
        records,
        "data/options_flow/summary_{ticker}.parquet",
        date_columns=("date", "session_date", "asof"),
    )
    daily_flow_exact = _coverage_count(records, daily_flow_pairs)
    print_pairs: set[tuple[str, date]] = set()
    print_ledger = _read_parquet(repo_root / "data" / "flow_signals" / "ledger.parquet")
    if print_ledger is not None and {"root", "session_date"}.issubset(print_ledger.columns):
        import pandas as pd

        parsed = pd.to_datetime(print_ledger["session_date"], errors="coerce", utc=True)
        for ticker, observed_date in zip(print_ledger["root"], parsed.dt.date, strict=False):
            if observed_date is not None:
                print_pairs.add((str(ticker).upper(), observed_date))
    print_exact = _coverage_count(records, print_pairs)

    # GEX / vol / OI: compact GEX and dislocation history plus canonical Theta tiers.
    gex_pairs, gex_files = _ticker_date_parquet_pairs(
        repo_root,
        records,
        "data/polygon_gex/summary_{ticker}.parquet",
        date_columns=("date", "session_date", "asof"),
    )
    gex_exact = _coverage_count(records, gex_pairs)
    dislocation_pairs: set[tuple[str, date]] = set()
    dislocation = _read_parquet(
        repo_root / "data" / "options_dislocation" / "snapshots.parquet"
    )
    if dislocation is not None and {"underlying", "date"}.issubset(dislocation.columns):
        import pandas as pd

        parsed = pd.to_datetime(dislocation["date"], errors="coerce", utc=True)
        for ticker, observed_date in zip(dislocation["underlying"], parsed.dt.date, strict=False):
            if observed_date is not None:
                dislocation_pairs.add((str(ticker).upper(), observed_date))
    dislocation_exact = _coverage_count(records, dislocation_pairs)
    theta_counts, theta_resolved = _theta_supporting_counts(repo_root, records)
    remote_tiers = {
        item["tier"]: item for item in (theta_remote_inventory or {}).get("tiers", [])
    }
    remote_counts = {
        "theta_r2_required_root_year_pairs": (
            theta_remote_inventory["required_root_year_pairs"]
            if theta_remote_inventory
            else 0
        ),
        "theta_r2_all_tiers_available_root_year_pairs": (
            theta_remote_inventory["all_tiers_available_root_year_pairs"]
            if theta_remote_inventory
            else 0
        ),
        "theta_r2_candidate_issue_records": (
            theta_remote_inventory["all_tiers_candidate_issue_records"]
            if theta_remote_inventory
            else 0
        ),
        "theta_r2_all_tiers_available_root_count": (
            theta_remote_inventory["all_tiers_available_root_count"]
            if theta_remote_inventory
            else 0
        ),
        "theta_r2_current_available_objects": (
            theta_remote_inventory["total_available_objects"]
            if theta_remote_inventory
            else 0
        ),
        "theta_r2_current_available_bytes": (
            theta_remote_inventory["total_available_bytes"]
            if theta_remote_inventory
            else 0
        ),
        **{
            f"theta_r2_{tier}_available_objects": remote_tiers.get(tier, {}).get(
                "available_objects", 0
            )
            for tier in THETA_TIERS
        },
    }

    # News / alt data: first-seen entity news and an accrued daily alt-data snapshot.
    news_pairs: set[tuple[str, date]] = set()
    news = _read_parquet(repo_root / "data" / "news" / "event_log.parquet")
    if news is not None and {"first_seen_utc", "tickers"}.issubset(news.columns):
        import pandas as pd

        parsed = pd.to_datetime(news["first_seen_utc"], errors="coerce", utc=True)
        for raw_tickers, observed_date in zip(news["tickers"], parsed.dt.date, strict=False):
            if observed_date is None:
                continue
            news_pairs.update(
                (ticker, observed_date) for ticker in _parse_ticker_collection(raw_tickers)
            )
    news_exact = _coverage_count(records, news_pairs)

    alt_pairs: set[tuple[str, date]] = set()
    alt_path = repo_root / "data" / "desk_grader" / "alt_data_snapshots.jsonl"
    if alt_path.is_file():
        try:
            for line in alt_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                alt_pairs.add((str(row["ticker"]).upper(), date.fromisoformat(row["date"])))
        except (KeyError, ValueError, json.JSONDecodeError):
            alt_pairs = set()
    alt_exact = _coverage_count(records, alt_pairs)
    news_alt_exact = _coverage_count(records, news_pairs | alt_pairs)

    return [
        {
            "family": "price_technical",
            "state": "partial_retro" if price_files else "unavailable",
            "record_count": total,
            "exact_issue_date_records": price_exact,
            "within_day_ready": False,
            "available_at_ready": False,
            "supporting_counts": {
                "ticker_files": price_files,
                "exact_issue_date_records": price_exact,
            },
            "blocker_codes": [
                "issue_timestamp_unknown",
                "intraday_price_archive_unmapped",
                "historical_adjustment_vintage_unavailable",
            ],
        },
        {
            "family": "macro_regime",
            "state": "partial_pit" if macro_pit is not None else "unavailable",
            "record_count": total,
            "exact_issue_date_records": macro_exact,
            "within_day_ready": False,
            "available_at_ready": False,
            "supporting_counts": {
                "pit_daily_exact_issue_records": sum(
                    value in macro_pit_dates for value in issue_dates
                ),
                "recent_accrual_exact_issue_records": sum(
                    value in macro_recent_dates for value in issue_dates
                ),
                "combined_exact_issue_records": macro_exact,
            },
            "blocker_codes": [
                "issue_timestamp_unknown",
                "within_day_regime_state_unavailable",
                "per_feature_release_availability_not_materialized",
            ],
        },
        {
            "family": "options_flow_campaign",
            "state": "partial_pit" if print_ledger is not None else "unavailable",
            "record_count": total,
            "exact_issue_date_records": print_exact,
            "within_day_ready": print_exact > 0,
            "available_at_ready": bool(
                print_ledger is not None and "ingested_at" in print_ledger.columns
            ),
            "supporting_counts": {
                "daily_aggregate_ticker_files": daily_flow_files,
                "daily_aggregate_exact_issue_records": daily_flow_exact,
                "per_print_exact_issue_records": print_exact,
            },
            "blocker_codes": [
                "historical_per_print_nbbo_sparse",
                "daily_backfill_is_magnitude_only",
                "campaign_history_not_available_for_full_record",
                "signed_direction_is_soft",
            ],
        },
        {
            "family": "gex_vol_oi",
            "state": (
                "candidate_only"
                if (
                    gex_files
                    or dislocation is not None
                    or theta_resolved
                    or theta_remote_inventory is not None
                )
                else "unavailable"
            ),
            "record_count": total,
            "exact_issue_date_records": _coverage_count(
                records,
                gex_pairs | dislocation_pairs,
            ),
            "within_day_ready": False,
            "available_at_ready": False,
            "supporting_counts": {
                "polygon_gex_ticker_files": gex_files,
                "polygon_gex_exact_issue_records": gex_exact,
                "dislocation_exact_issue_records": dislocation_exact,
                **theta_counts,
                **remote_counts,
            },
            "blocker_codes": [
                *([] if theta_resolved else ["thetadata_local_store_unresolved"]),
                *(
                    [
                        "theta_r2_selective_restore_pending",
                        "theta_remote_yearfile_rows_unverified",
                    ]
                    if theta_remote_inventory
                    else ["theta_r2_inventory_not_run"]
                ),
                "historical_chain_cutoff_snapshots_sparse",
                "open_interest_requires_prior_session",
                "issue_day_eod_not_known_before_close",
                "historical_intraday_theta_source_unavailable",
                "within_day_gex_vintage_unavailable",
            ],
        },
        {
            "family": "news_alt_data",
            "state": (
                "candidate_only" if (news is not None or alt_path.is_file()) else "unavailable"
            ),
            "record_count": total,
            "exact_issue_date_records": news_alt_exact,
            "within_day_ready": news_exact > 0,
            "available_at_ready": news is not None and "first_seen_utc" in news.columns,
            "supporting_counts": {
                "timestamped_news_exact_issue_records": news_exact,
                "daily_alt_exact_issue_records": alt_exact,
                "combined_exact_issue_records": news_alt_exact,
            },
            "blocker_codes": [
                "timestamped_entity_news_history_sparse",
                "alt_data_vintage_history_sparse",
                "issue_timestamp_unknown",
            ],
        },
    ]


def capital_constrained_proxy(
    cases: Iterable[dict[str, Any]],
    *,
    max_slots: int,
    return_basis: str,
    same_day_policy: str,
) -> dict[str, Any]:
    """Fixed-initial-capital slot proxy, explicitly not a reconstructed track record."""
    if max_slots < 1:
        raise ValueError("max_slots must be at least 1")
    if return_basis not in {"underlying", "reported_instrument"}:
        raise ValueError("return_basis must be underlying or reported_instrument")
    if same_day_policy not in {"close_before_issue", "issue_before_close"}:
        raise ValueError("same_day_policy must be close_before_issue or issue_before_close")

    rows: list[dict[str, Any]] = []
    excluded = 0
    excluded_temporal = 0
    for case in cases:
        management = case["decision_layers"]["management"]
        contract = case["decision_layers"]["contract_construction"]
        if (
            case["temporal_quality"]["replay_eligibility"]["overlap_allocation"]
            != "eligible"
        ):
            excluded_temporal += 1
            continue
        closed_date = management["closed_date"]
        if return_basis == "underlying":
            return_pct = management["underlying_return_pct"]
        elif contract["instrument"] == "option":
            return_pct = management["option_return_pct"]
        else:
            return_pct = management["underlying_return_pct"]
        if closed_date is None or return_pct is None:
            excluded += 1
            continue
        rows.append(
            {
                "case_id": case["case_id"],
                "source_record_index": case["source_record_index"],
                "issue_date": date.fromisoformat(case["issue_date"]),
                "closed_date": date.fromisoformat(closed_date),
                "return_pct": Decimal(str(return_pct)),
            }
        )

    issue_by_date: dict[date, list[dict[str, Any]]] = {}
    all_dates: set[date] = set()
    for row in rows:
        issue_by_date.setdefault(row["issue_date"], []).append(row)
        all_dates.update((row["issue_date"], row["closed_date"]))
    for day_rows in issue_by_date.values():
        day_rows.sort(key=lambda row: row["source_record_index"])

    active: dict[str, dict[str, Any]] = {}
    accepted: list[dict[str, Any]] = []
    skipped_no_slot = 0

    def close_due(day: date) -> None:
        for case_id in [
            case_id
            for case_id, row in active.items()
            if row["closed_date"] == day
        ]:
            active.pop(case_id)

    for day in sorted(all_dates):
        if same_day_policy == "close_before_issue":
            close_due(day)
        for row in issue_by_date.get(day, []):
            if len(active) >= max_slots:
                skipped_no_slot += 1
                continue
            active[row["case_id"]] = row
            accepted.append(row)
        # Always close same-day trades after their issue.  Under issue-before-close this also
        # closes prior positions; under close-before-issue the first pass already did so.
        close_due(day)

    contribution = sum((row["return_pct"] for row in accepted), Decimal("0")) / Decimal(
        max_slots
    )
    return {
        "state": "research_proxy_not_track_record",
        "return_basis": return_basis,
        "max_slots": max_slots,
        "same_day_policy": same_day_policy,
        "eligible_records": len(rows),
        "accepted_records": len(accepted),
        "skipped_no_slot": skipped_no_slot,
        "excluded_incomplete": excluded,
        "excluded_temporal_quality": excluded_temporal,
        "fixed_initial_capital_return_pct": float(contribution),
    }


def _cohort_aggregate(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = ("pre_option_format", "mixed_format_transition", "post_underlying_format")
    output: list[dict[str, Any]] = []
    for cohort_id in order:
        members = [case for case in cases if case["cohort"]["cohort_id"] == cohort_id]
        if not members:
            continue
        instruments = Counter(
            case["decision_layers"]["contract_construction"]["instrument"] for case in members
        )
        directions = Counter(case["decision_layers"]["selection"]["direction"] for case in members)
        output.append(
            {
                "cohort_id": cohort_id,
                "first_issue_date": min(case["issue_date"] for case in members),
                "last_issue_date": max(case["issue_date"] for case in members),
                "record_count": len(members),
                "instrument_counts": {
                    "underlying": instruments["underlying"],
                    "option": instruments["option"],
                },
                "direction_counts": {
                    "BULL": directions["BULL"],
                    "BEAR": directions["BEAR"],
                },
            }
        )
    return output


def _round_float(value: Decimal | float, digits: int = 6) -> float:
    return round(float(value), digits)


def build_aggregate_receipt(
    history: dict[str, Any],
    input_sha256: str,
    cases: list[dict[str, Any]],
    feature_receipts: list[dict[str, Any]],
    data_availability: list[dict[str, Any]],
    theta_data_plane: dict[str, Any],
    *,
    generated_at: str | None = None,
    proxy_metrics: list[dict[str, Any]] | None = None,
    validate_output: bool = True,
) -> dict[str, Any]:
    records = history["records"]
    summary = history["displayed_summary"]
    policy = derive_cohort_policy(records)

    underlying_returns = [Decimal(str(record["underlying"]["return_pct"])) for record in records]
    underlying_sum = sum(underlying_returns, Decimal("0"))
    headline_total = Decimal(str(summary["total_alpha_pct"]))
    option_returns = [
        Decimal(str(record["option"]["return_pct"]))
        for record in records
        if record["option"] is not None and record["option"]["return_pct"] is not None
    ]
    status_pairs = Counter(
        (record["table_status"], record["detail_status"])
        for record in records
        if record["table_status"] != record["detail_status"]
    )
    issued_dates = [_parse_mdy(record["issued_date"], "issued_date") for record in records]
    temporal_flags = [case["temporal_quality"]["quality_flags"] for case in cases]
    holding_after_expiration_days = [
        case["temporal_quality"]["derived_diagnostics"][
            "reported_holding_end_minus_option_expiration_days"
        ]
        for case in cases
        if "reported_holding_interval_after_option_expiration"
        in case["temporal_quality"]["quality_flags"]
    ]

    receipt = {
        "schema": AGGREGATE_SCHEMA_ID,
        "generated_at": (
            generated_at
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "input": {
            "schema": INPUT_SCHEMA_ID,
            "sha256": input_sha256,
            "captured_at": history["captured_at"],
            "authorization_validated": True,
            "record_count": len(records),
        },
        "record_range": {
            "first_issue_date": min(issued_dates).isoformat(),
            "last_issue_date": max(issued_dates).isoformat(),
            "unique_issue_dates": len(set(issued_dates)),
        },
        "issue_time": {
            "exact_timestamp_records": 0,
            "date_only_records": len(records),
            "timezone": MARKET_TIMEZONE,
            "cutoff_ids": [spec[0] for spec in CUTOFF_SPECS],
            "sensitivity_only": True,
        },
        "cohort_policy": policy,
        "cohorts": _cohort_aggregate(cases),
        "decision_layers": {
            "selection_records": len(cases),
            "contract_construction_records": sum(
                case["decision_layers"]["contract_construction"]["instrument"] == "option"
                for case in cases
            ),
            "management_records": len(cases),
            "management_with_close_date": sum(
                case["decision_layers"]["management"]["closed_date"] is not None
                for case in cases
            ),
            "management_without_close_date": sum(
                case["decision_layers"]["management"]["closed_date"] is None
                for case in cases
            ),
        },
        "displayed_additive_metrics": {
            "headline_definition": summary["total_alpha_definition"],
            "headline_total_alpha_pct": float(headline_total),
            "reconstructed_visible_underlying_sum_pct": _round_float(underlying_sum),
            "headline_minus_reconstructed_pct": _round_float(headline_total - underlying_sum),
            "reconstructed_visible_underlying_mean_pct": _round_float(
                underlying_sum / Decimal(len(underlying_returns))
            ),
            "headline_win_rate_pct": summary["win_rate_pct"],
            "headline_wins": summary["wins_displayed"],
            "visible_return_class_counts": {
                "positive": sum(value > 0 for value in underlying_returns),
                "zero": sum(value == 0 for value in underlying_returns),
                "negative": sum(value < 0 for value in underlying_returns),
            },
            "option_records": sum(record["option"] is not None for record in records),
            "option_return_observed_records": len(option_returns),
            "reconstructed_visible_option_sum_pct": _round_float(
                sum(option_returns, Decimal("0"))
            ),
            "reconstruction_is_track_record": False,
        },
        "capital_constrained_metrics": {
            "identification_state": "not_identifiable_from_source",
            "blocker_codes": [
                "position_sizes_unavailable",
                "portfolio_capital_unavailable",
                "issue_timestamps_unavailable",
                *(
                    ["close_dates_incomplete"]
                    if any(record["closed_date"] is None for record in records)
                    else []
                ),
                *(
                    ["temporal_correction_overlays_unresolved"]
                    if any(flags != ["clean"] for flags in temporal_flags)
                    else []
                ),
                "commissions_slippage_and_spreads_unavailable",
                "overlap_allocation_policy_unavailable",
            ],
            "proxy_metrics": proxy_metrics or [],
        },
        "status_disagreements": {
            "count": sum(status_pairs.values()),
            "pairs": [
                {
                    "table_status": table_status,
                    "detail_status": detail_status,
                    "count": count,
                }
                for (table_status, detail_status), count in sorted(status_pairs.items())
            ],
            "both_values_retained": True,
        },
        "temporal_source_quality": {
            "raw_values_retained": True,
            "corrections_applied": 0,
            "clean_records": sum(flags == ["clean"] for flags in temporal_flags),
            "missing_close_date_records": sum(
                "missing_close_date" in flags for flags in temporal_flags
            ),
            "issue_close_days_held_year_conflict_records": sum(
                "issue_close_days_held_year_conflict" in flags
                for flags in temporal_flags
            ),
            "holding_interval_after_option_expiration_records": len(
                holding_after_expiration_days
            ),
            "max_holding_interval_beyond_option_expiration_days": max(
                holding_after_expiration_days,
                default=0,
            ),
            "correction_overlay_required_records": sum(
                flags != ["clean"] for flags in temporal_flags
            ),
            "overlap_replay_excluded_records": sum(
                case["temporal_quality"]["replay_eligibility"]["overlap_allocation"]
                != "eligible"
                for case in cases
            ),
            "expiry_return_replay_excluded_option_records": sum(
                case["temporal_quality"]["replay_eligibility"]["expiry_return"]
                == "excluded_temporal_quality"
                for case in cases
            ),
        },
        "theta_data_plane": theta_data_plane,
        "data_availability": data_availability,
        "runtime_outputs": {
            "replay_case_count": len(cases),
            "feature_receipt_count": len(feature_receipts),
            "private_output_required": True,
            "private_output_in_repo_allowed": False,
        },
        "privacy": {
            "raw_records_included": False,
            "ticker_values_included": False,
            "authorization_payload_included": False,
            "authorization_image_included": False,
            "private_runtime_artifacts_committed": False,
        },
        "authority": dict(AUTHORITY),
    }
    if validate_output:
        validate_document(receipt, AGGREGATE_SCHEMA)
        families = [entry["family"] for entry in data_availability]
        if sorted(families) != sorted(FEATURE_FAMILIES):
            raise ReplayInputError("aggregate data_availability does not contain five families")
    return receipt


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def enforce_private_output_boundary(private_output_dir: Path, repo_root: Path) -> Path:
    resolved_output = private_output_dir.expanduser().resolve()
    resolved_repo = repo_root.expanduser().resolve()
    if resolved_output == resolved_repo or _is_within(resolved_output, resolved_repo):
        raise ReplayInputError("private replay output must be outside the repository")
    return resolved_output


def _atomic_write(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _json_bytes(document: Any) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _jsonl_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    return (
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
            for row in rows
        )
    ).encode("utf-8")


def write_outputs(
    *,
    private_output_dir: Path,
    aggregate_receipt_path: Path,
    repo_root: Path,
    cases: list[dict[str, Any]],
    feature_receipts: list[dict[str, Any]],
    aggregate_receipt: dict[str, Any],
    theta_restore_plan: list[dict[str, Any]],
    theta_remote_inventory: dict[str, Any] | None,
) -> dict[str, Path]:
    private_dir = enforce_private_output_boundary(private_output_dir, repo_root)
    private_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private_dir, 0o700)

    cases_path = private_dir / "replay_cases.jsonl"
    features_path = private_dir / "asof_feature_receipt_requirements.jsonl"
    theta_plan_path = private_dir / "theta_r2_selective_restore_plan.jsonl"
    theta_inventory_path = private_dir / "theta_r2_inventory_aggregate.json"
    manifest_path = private_dir / "manifest.json"
    private_manifest = {
        "schema": "momoedge.oracle_history_replay_private_manifest/v1",
        "input_sha256": aggregate_receipt["input"]["sha256"],
        "replay_case_count": len(cases),
        "feature_receipt_count": len(feature_receipts),
        "theta_restore_plan_count": len(theta_restore_plan),
        "theta_remote_inventory_attached": theta_remote_inventory is not None,
        "authority": dict(AUTHORITY),
        "privacy": {"repository_output": False, "file_mode": "0600"},
    }

    _atomic_write(cases_path, _jsonl_bytes(cases), mode=0o600)
    _atomic_write(features_path, _jsonl_bytes(feature_receipts), mode=0o600)
    _atomic_write(theta_plan_path, _jsonl_bytes(theta_restore_plan), mode=0o600)
    if theta_remote_inventory is not None:
        _atomic_write(theta_inventory_path, _json_bytes(theta_remote_inventory), mode=0o600)
    _atomic_write(manifest_path, _json_bytes(private_manifest), mode=0o600)
    _atomic_write(aggregate_receipt_path, _json_bytes(aggregate_receipt), mode=0o644)
    return {
        "cases": cases_path,
        "features": features_path,
        "theta_restore_plan": theta_plan_path,
        **(
            {"theta_remote_inventory": theta_inventory_path}
            if theta_remote_inventory is not None
            else {}
        ),
        "private_manifest": manifest_path,
        "aggregate_receipt": aggregate_receipt_path,
    }


def run(
    *,
    input_path: Path,
    private_output_dir: Path,
    aggregate_receipt_path: Path,
    repo_root: Path = REPO_ROOT,
    portfolio_slots: Iterable[int] = (),
    generated_at: str | None = None,
    theta_remote_inventory_path: Path | None = None,
    probe_theta_r2: bool = False,
) -> dict[str, Any]:
    history, input_sha256 = load_and_validate_history(input_path)
    cases = build_replay_cases(history, input_sha256)
    feature_receipts = build_feature_receipt_requirements(cases)
    theta_restore_plan = build_theta_selective_restore_plan(history["records"])
    theta_remote_inventory: dict[str, Any] | None = None
    if probe_theta_r2:
        client, bucket = _r2_client_from_env()
        theta_remote_inventory, theta_restore_plan = probe_theta_remote_inventory(
            history,
            input_sha256,
            client=client,
            bucket=bucket,
            generated_at=generated_at,
        )
    elif theta_remote_inventory_path is not None:
        theta_remote_inventory = load_theta_remote_inventory(
            theta_remote_inventory_path,
            expected_input_sha256=input_sha256,
        )
    data_availability = audit_repo_data(
        repo_root,
        history["records"],
        theta_remote_inventory=theta_remote_inventory,
    )
    theta_data_plane = build_theta_data_plane_summary(
        repo_root,
        history["records"],
        theta_remote_inventory,
    )

    proxy_metrics = [
        capital_constrained_proxy(
            cases,
            max_slots=slots,
            return_basis=basis,
            same_day_policy=policy,
        )
        for slots in portfolio_slots
        for basis in ("underlying", "reported_instrument")
        for policy in ("close_before_issue", "issue_before_close")
    ]
    receipt = build_aggregate_receipt(
        history,
        input_sha256,
        cases,
        feature_receipts,
        data_availability,
        theta_data_plane,
        generated_at=generated_at,
        proxy_metrics=proxy_metrics,
    )
    paths = write_outputs(
        private_output_dir=private_output_dir,
        aggregate_receipt_path=aggregate_receipt_path,
        repo_root=repo_root,
        cases=cases,
        feature_receipts=feature_receipts,
        aggregate_receipt=receipt,
        theta_restore_plan=theta_restore_plan,
        theta_remote_inventory=theta_remote_inventory,
    )
    return {"receipt": receipt, "paths": paths}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build private MomoEdge Oracle replay cases and an aggregate-only receipt."
    )
    parser.add_argument("--input", type=Path, required=True, help="Authorized private JSON input")
    parser.add_argument(
        "--private-output-dir",
        type=Path,
        required=True,
        help="Directory outside the repository for private cases and feature receipts",
    )
    parser.add_argument(
        "--aggregate-receipt",
        type=Path,
        required=True,
        help="Aggregate-only JSON receipt path",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--portfolio-slots",
        type=int,
        action="append",
        default=[],
        help="Optional research-only fixed-slot sensitivity (repeatable)",
    )
    parser.add_argument(
        "--generated-at",
        help="Optional deterministic RFC3339 timestamp for the aggregate receipt",
    )
    theta_group = parser.add_mutually_exclusive_group()
    theta_group.add_argument(
        "--theta-remote-inventory",
        type=Path,
        help="Prior aggregate-only targeted R2 inventory bound to this input",
    )
    theta_group.add_argument(
        "--probe-theta-r2",
        action="store_true",
        help="HEAD only required current-prefix Theta root/year objects; never download",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run(
        input_path=args.input,
        private_output_dir=args.private_output_dir,
        aggregate_receipt_path=args.aggregate_receipt,
        repo_root=args.repo_root,
        portfolio_slots=args.portfolio_slots,
        generated_at=args.generated_at,
        theta_remote_inventory_path=args.theta_remote_inventory,
        probe_theta_r2=args.probe_theta_r2,
    )
    receipt = result["receipt"]
    print(
        "momoedge-history-replay: "
        f"cases={receipt['runtime_outputs']['replay_case_count']} "
        f"feature_receipts={receipt['runtime_outputs']['feature_receipt_count']} "
        "authority=research_only"
    )
    print(f"aggregate_receipt={result['paths']['aggregate_receipt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
