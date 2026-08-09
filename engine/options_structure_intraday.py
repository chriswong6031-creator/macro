"""Light, descriptive U-CHAIN eligibility packets for MSC R2.2-A.

This module turns one root/bucket from the private ``chain_snapshots`` Parquet
plane into a compact public receipt.  It does not select an underlying, issue a
signal, size a trade, or grant Prophet authority.  Profiles remain separate and
only describe which *contracts* satisfy their own disclosed laws.

The existing Prophet option resolver is deliberately reused for its target
delta and monthly-expiry law.  Primary delta ties preserve its first-source-row
``idxmin`` behavior.  Its EOD fallback depends on input row order; this packet
does not import that defect.  The fallback profile is explicitly labelled and
uses a deterministic closest-OTM order instead.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
from numbers import Integral, Real
import re
from typing import Any, Mapping, Sequence

import pandas as pd

from engine.prophet_bridge import TARGET_DELTA, _next_monthly_expiry
from engine.session_digest import ET, is_early_close, session_window_et
from lib import nyse_calendar


SCHEMA = "options.contract_eligibility/v1"
CURRENT_SCHEMA = "options.contract_eligibility.current/v1"
INDEX_SCHEMA = "options.contract_eligibility.index/v1"

PROPHET_PROFILE = "prophet_delta60_monthly_v1"
CONVEX_PROFILE = "convex_otm_30_180_v1"
PROFILE_ORDER = (PROPHET_PROFILE, CONVEX_PROFILE)

QUOTE_FRESHNESS_MINUTES = 20
DEFAULT_CADENCE_MINUTES = 15
MAX_PROJECTED_CONTRACTS = 20_000

_ROOT_RE = re.compile(r"^[A-Z0-9](?:[A-Z0-9.-]{0,13}[A-Z0-9])?$")
_OCC_ROOT_RE = re.compile(r"^[A-Z0-9]{1,6}$")
_BUCKET_RE = re.compile(r"^(?:0\d|1\d|2[0-3]):(?:00|15|30|45)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DECIMAL_RE = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d+)?$")
_INTEGER_RE = re.compile(r"^(?:0|[1-9]\d*)$")
_ISO_CLOCK_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})?$"
)
# A float at 2^53 is itself exact, but it is also the rounded representation
# produced by nullable-float coercion of 2^53 + 1. Without lexical provenance
# those cases are indistinguishable, so floats at/above this boundary fail
# closed. Exact integer/string inputs remain unbounded Python integers.
_FLOAT_INTEGER_ALIAS_BOUNDARY = 2**53

CHAIN_REQUIRED_COLUMNS = frozenset({
    "root", "expiration", "strike", "right", "snapshot_ts", "snapshot_bucket",
    "source", "bid", "ask", "delta", "theta", "vega", "rho", "epsilon",
    "lambda", "implied_vol", "iv_error", "underlying_price", "gamma", "vanna",
    "charm", "vomma", "veta",
})
OI_REQUIRED_COLUMNS = frozenset({
    "root", "expiration", "strike", "right", "snapshot_ts", "open_interest", "source",
})
CONTRACT_KEY = ("root", "expiration", "strike", "right")
GREEK_FIELDS = (
    "delta", "theta", "vega", "rho", "epsilon", "lambda", "gamma", "vanna",
    "charm", "vomma", "veta",
)


class OptionsStructureIntradayError(ValueError):
    """The private source or requested publication violates the W0a contract."""


def authority_block() -> dict[str, bool]:
    """Every W0a authority is false by construction."""
    return {
        "rank_authority": False,
        "gate_authority": False,
        "sizing_authority": False,
        "issue_authority": False,
        "trade_authority": False,
        "prophet_authority": False,
    }


def canonical_json_bytes(payload: object) -> bytes:
    """Return deterministic strict JSON bytes (including a final newline)."""
    try:
        return (
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise OptionsStructureIntradayError(f"payload is not strict canonical JSON: {exc}") from exc


def strict_json_object(body: bytes) -> dict[str, Any]:
    """Parse one strict JSON object, rejecting duplicate keys and NaN/Infinity."""
    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise OptionsStructureIntradayError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def reject_constant(value: str) -> None:
        raise OptionsStructureIntradayError(f"non-finite JSON number: {value}")

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OptionsStructureIntradayError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise OptionsStructureIntradayError("JSON root must be an object")
    return value


def _safe_root(value: object) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or value != value.upper()
    ):
        raise OptionsStructureIntradayError(f"unsafe root: {value!r}")
    root = value
    if not root or not _ROOT_RE.fullmatch(root) or ".." in root:
        raise OptionsStructureIntradayError(f"unsafe root: {value!r}")
    return root


def _as_date(value: object, *, field: str) -> date:
    if isinstance(value, bool) or value is None:
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}")
    if isinstance(value, pd.Timestamp):
        if pd.isna(value) or value.tzinfo is not None:
            raise OptionsStructureIntradayError(f"invalid {field}: {value!r}")
        if any((value.hour, value.minute, value.second, value.microsecond, value.nanosecond)):
            raise OptionsStructureIntradayError(f"non-midnight {field}: {value!r}")
        return value.date()
    if isinstance(value, datetime):
        if value.tzinfo is not None or any((value.hour, value.minute, value.second, value.microsecond)):
            raise OptionsStructureIntradayError(f"non-canonical {field}: {value!r}")
        return value.date()
    if isinstance(value, date):
        return value
    text = value if isinstance(value, str) else ""
    if not _DATE_RE.fullmatch(text):
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}")
    try:
        parsed = date.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}") from exc
    if parsed.isoformat() != text:
        raise OptionsStructureIntradayError(f"non-canonical {field}: {value!r}")
    return parsed


def _as_utc(
    value: object,
    *,
    field: str,
    naive_tz=ET,
    require_timezone: bool = False,
) -> datetime:
    """Parse a timestamp; collector-naive vendor clocks are ET by contract."""
    if isinstance(value, bool) or value is None or isinstance(value, date) and not isinstance(value, datetime):
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}")
    if isinstance(value, str) and not _ISO_CLOCK_RE.fullmatch(value):
        raise OptionsStructureIntradayError(f"non-canonical {field}: {value!r}")
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}") from exc
    if pd.isna(ts):
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}")
    if ts.nanosecond:
        raise OptionsStructureIntradayError(
            f"sub-microsecond {field} precision is not supported: {value!r}"
        )
    if require_timezone and ts.tzinfo is None:
        raise OptionsStructureIntradayError(f"{field} must be timezone-aware: {value!r}")
    if ts.tzinfo is None:
        ts = ts.tz_localize(naive_tz)
    return ts.tz_convert("UTC").to_pydatetime()


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool) or pd.isna(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return 0.0 if number == 0 else number


def _canonical_positive_decimal(value: object, *, field: str) -> tuple[Decimal, str]:
    """Parse one positive decimal identity without rounding its representation."""
    if value is None or isinstance(value, bool):
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}")
    if isinstance(value, str):
        if not _DECIMAL_RE.fullmatch(value):
            raise OptionsStructureIntradayError(f"non-canonical {field}: {value!r}")
        lexical = value
    elif isinstance(value, Decimal):
        lexical = str(value)
    elif isinstance(value, Integral):
        lexical = str(int(value))
    elif isinstance(value, Real):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise OptionsStructureIntradayError(f"non-finite {field}: {value!r}")
        lexical = str(value)
    else:
        item = getattr(value, "item", None)
        if callable(item):
            return _canonical_positive_decimal(item(), field=field)
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}")
    try:
        decimal_value = Decimal(lexical)
    except InvalidOperation as exc:
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}") from exc
    if not decimal_value.is_finite() or decimal_value <= 0:
        raise OptionsStructureIntradayError(f"{field} must be finite and positive: {value!r}")
    canonical = format(decimal_value, "f")
    if "." in canonical:
        canonical = canonical.rstrip("0").rstrip(".")
    if not _DECIMAL_RE.fullmatch(canonical):
        raise OptionsStructureIntradayError(f"non-canonical {field}: {value!r}")
    return decimal_value, canonical


def _exact_nonnegative_integer(value: object, *, field: str) -> int | None:
    """Parse an optional exact integer and never round through binary float."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, bool):
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}")
    if isinstance(value, str):
        if not _INTEGER_RE.fullmatch(value):
            raise OptionsStructureIntradayError(f"non-canonical {field}: {value!r}")
        return int(value)
    if isinstance(value, Integral):
        parsed = int(value)
    elif isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise OptionsStructureIntradayError(f"{field} must be an exact integer: {value!r}")
        parsed = int(value)
    elif isinstance(value, Real):
        numeric = float(value)
        if math.isnan(numeric):
            return None
        if not math.isfinite(numeric):
            raise OptionsStructureIntradayError(f"non-finite {field}: {value!r}")
        if numeric < 0:
            raise OptionsStructureIntradayError(f"{field} must be non-negative: {value!r}")
        if not numeric.is_integer():
            raise OptionsStructureIntradayError(f"{field} must be an exact integer: {value!r}")
        if numeric >= _FLOAT_INTEGER_ALIAS_BOUNDARY:
            raise OptionsStructureIntradayError(
                f"{field} float is at or above the ambiguous 2^53 boundary: {value!r}"
            )
        parsed = int(numeric)
    else:
        item = getattr(value, "item", None)
        if callable(item):
            return _exact_nonnegative_integer(item(), field=field)
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}")
    if parsed < 0:
        raise OptionsStructureIntradayError(f"{field} must be non-negative: {value!r}")
    return parsed


def _required_control_integer(value: object, *, field: str) -> int:
    """Require a genuinely integral control value; never coerce strings/floats."""
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise OptionsStructureIntradayError(f"{field} must be an integer")
    return int(value)


def _source_root(value: object, *, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or value != value.upper():
        raise OptionsStructureIntradayError(f"non-canonical {field}: {value!r}")
    return _safe_root(value)


def _source_right(value: object, *, field: str) -> str:
    if not isinstance(value, str) or value not in {"C", "P"}:
        raise OptionsStructureIntradayError(f"invalid {field}: {value!r}")
    return value


def _finite_required(value: object, *, field: str) -> float:
    number = _finite_float(value)
    if number is None:
        raise OptionsStructureIntradayError(f"non-finite {field}: {value!r}")
    return number


def _json_scalar(value: object) -> object:
    """Normalize a DataFrame scalar for stable source-receipt hashing."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return _iso_utc(_as_utc(value, field="receipt timestamp"))
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return 0.0 if value == 0 else float(value)
    # numpy scalar types expose item(); avoid importing numpy solely for this.
    item = getattr(value, "item", None)
    if callable(item):
        return _json_scalar(item())
    return str(value)


def _frame_digest(frame: pd.DataFrame, columns: Sequence[str]) -> str:
    rows: list[dict[str, object]] = []
    for _, row in frame.loc[:, list(columns)].iterrows():
        rows.append({column: _json_scalar(row[column]) for column in columns})
    return sha256(canonical_json_bytes(rows)).hexdigest()


def _contract_id(root: str, expiry: date, right: str, strike_canonical: str) -> str:
    raw = f"{root}|{expiry.isoformat()}|{right}|{strike_canonical}".encode("ascii")
    return f"contract:uchain:{sha256(raw).hexdigest()}"


def construct_occ_symbol(root: str, expiry: date, right: str, strike: object) -> str | None:
    """Construct standard 21-character OCC symbology only when exact and safe."""
    if not _OCC_ROOT_RE.fullmatch(root) or right not in {"C", "P"}:
        return None
    try:
        strike_decimal, _canonical = _canonical_positive_decimal(strike, field="OCC strike")
    except OptionsStructureIntradayError:
        return None
    strike_millis_decimal = strike_decimal * Decimal(1000)
    if strike_millis_decimal != strike_millis_decimal.to_integral_value():
        return None
    strike_millis = int(strike_millis_decimal)
    if strike_millis > 99_999_999:
        return None
    return f"{root:<6}{expiry:%y%m%d}{right}{strike_millis:08d}"


def _previous_session(session: date) -> date:
    previous = nyse_calendar.last_session_on_or_before(session - timedelta(days=1))
    if previous >= session or not nyse_calendar.is_session(previous):
        raise OptionsStructureIntradayError(
            f"could not derive a real prior NYSE session for {session.isoformat()}"
        )
    intervening = nyse_calendar.sessions_between(previous + timedelta(days=1), session - timedelta(days=1))
    if intervening:
        raise OptionsStructureIntradayError(
            f"derived OI vintage is not the immediately prior NYSE session: {previous.isoformat()}"
        )
    return previous


def _validate_session(session: date, bucket: str) -> tuple[datetime, datetime, datetime]:
    if not nyse_calendar.is_session(session):
        raise OptionsStructureIntradayError(f"not an NYSE session: {session.isoformat()}")
    if not _BUCKET_RE.fullmatch(bucket):
        raise OptionsStructureIntradayError(f"invalid snapshot bucket: {bucket!r}")
    open_at, close_at = session_window_et(session)
    hour, minute = (int(part) for part in bucket.split(":"))
    bucket_at = datetime.combine(session, datetime.min.time(), tzinfo=ET).replace(hour=hour, minute=minute)
    if bucket_at < open_at or bucket_at > close_at:
        raise OptionsStructureIntradayError(
            f"bucket {bucket} outside NYSE window {open_at:%H:%M}-{close_at:%H:%M} ET"
        )
    return open_at, close_at, bucket_at


def _validate_columns(frame: pd.DataFrame, required: frozenset[str], *, label: str) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise OptionsStructureIntradayError(f"{label} source is not a DataFrame")
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise OptionsStructureIntradayError(f"{label} source missing columns: {', '.join(missing)}")


def _normalize_chain(
    frame: pd.DataFrame,
    *,
    root: str,
    session: date,
    bucket: str,
) -> pd.DataFrame:
    _validate_columns(frame, CHAIN_REQUIRED_COLUMNS, label="chain")
    if frame.empty:
        raise OptionsStructureIntradayError(f"empty chain source for {root}")
    working = frame.copy()
    working["source_row_ordinal"] = range(len(working))
    working["root_value"] = working["root"].map(
        lambda value: _source_root(value, field="chain root")
    )
    source_roots = set(working["root_value"])
    if source_roots != {root}:
        raise OptionsStructureIntradayError(
            f"chain root mismatch: expected {root}, saw {sorted(source_roots)}"
        )
    if not frame["source"].eq("chain_snapshot").all():
        raise OptionsStructureIntradayError("chain source tag must be chain_snapshot")
    if working["snapshot_bucket"].map(lambda value: isinstance(value, str)).eq(False).any():
        raise OptionsStructureIntradayError("chain snapshot_bucket must be a string")
    selected = working[working["snapshot_bucket"] == bucket].copy()
    if selected.empty:
        raise OptionsStructureIntradayError(f"chain source has no rows for bucket {bucket}")

    selected["expiration_date"] = selected["expiration"].map(lambda v: _as_date(v, field="expiration"))
    strike_parts = selected["strike"].map(
        lambda value: _canonical_positive_decimal(value, field="chain strike")
    )
    selected["strike_decimal"] = strike_parts.map(lambda part: part[0])
    selected["strike_canonical"] = strike_parts.map(lambda part: part[1])
    selected["strike_value"] = selected["strike_decimal"].map(float)
    selected["right_value"] = selected["right"].map(
        lambda value: _source_right(value, field="chain right")
    )
    selected["snapshot_utc"] = selected["snapshot_ts"].map(
        lambda v: _as_utc(v, field="snapshot_ts")
    )
    selected["contract_key"] = list(zip(
        selected["root_value"],
        selected["expiration_date"],
        selected["strike_canonical"],
        selected["right_value"],
    ))
    if selected["contract_key"].duplicated().any():
        raise OptionsStructureIntradayError("duplicate chain contract tuple in requested bucket")
    return selected.sort_values(
        ["expiration_date", "right_value", "strike_decimal", "source_row_ordinal"],
        kind="stable",
    ).reset_index(drop=True)


def _normalize_oi(
    frame: pd.DataFrame,
    *,
    root: str,
    session: date,
    observed_at: datetime,
    session_open_at: datetime,
) -> tuple[pd.DataFrame, dict[tuple, Mapping[str, Any]], int, int]:
    _validate_columns(frame, OI_REQUIRED_COLUMNS, label="open-interest")
    if frame.empty:
        return frame.copy(), {}, 0, 0
    normalized = frame.copy()
    normalized["root_value"] = normalized["root"].map(
        lambda value: _source_root(value, field="OI root")
    )
    source_roots = set(normalized["root_value"])
    if source_roots != {root}:
        raise OptionsStructureIntradayError(f"OI root mismatch: expected {root}, saw {sorted(source_roots)}")
    if not frame["source"].eq("chain_snapshot").all():
        raise OptionsStructureIntradayError("OI source tag must be chain_snapshot")
    normalized["expiration_date"] = normalized["expiration"].map(lambda v: _as_date(v, field="OI expiration"))
    strike_parts = normalized["strike"].map(
        lambda value: _canonical_positive_decimal(value, field="OI strike")
    )
    normalized["strike_decimal"] = strike_parts.map(lambda part: part[0])
    normalized["strike_canonical"] = strike_parts.map(lambda part: part[1])
    normalized["strike_value"] = normalized["strike_decimal"].map(float)
    normalized["right_value"] = normalized["right"].map(
        lambda value: _source_right(value, field="OI right")
    )
    normalized["snapshot_utc"] = normalized["snapshot_ts"].map(
        lambda v: _as_utc(v, field="OI snapshot_ts")
    )
    normalized["open_interest_value"] = normalized["open_interest"].map(
        lambda value: _exact_nonnegative_integer(value, field="open_interest")
    )
    all_keys = list(zip(
        normalized["root_value"],
        normalized["expiration_date"],
        normalized["strike_canonical"],
        normalized["right_value"],
    ))
    if len(all_keys) != len(set(all_keys)):
        raise OptionsStructureIntradayError("duplicate OI contract tuple")
    for stamp in normalized["snapshot_utc"]:
        if stamp > observed_at:
            raise OptionsStructureIntradayError("OI snapshot timestamp is after builder observation")
        if stamp.astimezone(ET) > session_open_at:
            raise OptionsStructureIntradayError("OI snapshot timestamp is after the NYSE session open")
    usable_mask = normalized["expiration_date"].map(lambda expiry: expiry >= session)
    for stamp in normalized.loc[usable_mask, "snapshot_utc"]:
        stamp_et = stamp.astimezone(ET)
        if stamp_et.date() != session:
            raise OptionsStructureIntradayError(
                f"OI snapshot date {stamp_et.date()} does not match availability session {session}"
            )
    expected_vintage = _previous_session(session)
    if "vintage_session" in normalized.columns:
        normalized["vintage_session_value"] = normalized["vintage_session"].map(
            lambda value: _as_date(value, field="OI vintage_session")
        )
        if not normalized["vintage_session_value"].eq(expected_vintage).all():
            raise OptionsStructureIntradayError(
                f"OI vintage_session must be the prior NYSE session {expected_vintage.isoformat()}"
            )
    else:
        normalized["vintage_session_value"] = expected_vintage
    usable = normalized[usable_mask].copy()
    expired_excluded_count = int((~usable_mask).sum())
    keys = list(zip(
        usable["root_value"],
        usable["expiration_date"],
        usable["strike_canonical"],
        usable["right_value"],
    ))
    lookup: dict[tuple, Mapping[str, Any]] = {}
    for idx, key in enumerate(keys):
        lookup[key] = usable.iloc[idx]
    return normalized.sort_values(
        ["expiration_date", "right_value", "strike_decimal"], kind="stable"
    ).reset_index(drop=True), lookup, len(usable), expired_excluded_count


def _quote_state(
    row: Mapping[str, Any],
    *,
    observed_at: datetime,
    available_at: datetime,
    open_at: datetime,
    close_at: datetime,
) -> tuple[dict[str, Any], list[str]]:
    bid = _finite_float(row.get("bid"))
    ask = _finite_float(row.get("ask"))
    snapshot_at = row["snapshot_utc"]
    observed_age_minutes = (observed_at - snapshot_at).total_seconds() / 60.0
    age_minutes = (available_at - snapshot_at).total_seconds() / 60.0
    reasons: list[str] = []
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        reasons.append("ZERO_OR_MISSING_QUOTE")
    elif ask < bid:
        reasons.append("CROSSED_QUOTE")
    if observed_age_minutes < 0:
        reasons.append("QUOTE_CLOCK_IN_FUTURE")
    elif age_minutes > QUOTE_FRESHNESS_MINUTES:
        reasons.append("QUOTE_STALE")
    snapshot_et = snapshot_at.astimezone(ET)
    # Vendor stamps immediately after the closing bucket can still describe the
    # just-completed chain.  Bound that grace by the same 20-minute quote clock.
    if snapshot_et < open_at or snapshot_et > close_at + timedelta(minutes=QUOTE_FRESHNESS_MINUTES):
        reasons.append("QUOTE_OUTSIDE_SESSION_WINDOW")
    if reasons or bid is None or ask is None:
        mid = None
        spread_abs = None
        spread_pct = None
    else:
        mid = (bid + ask) / 2.0
        spread_abs = ask - bid
        spread_pct = (spread_abs / mid) * 100.0 if mid > 0 else None
    return {
        "snapshot_ts": _iso_utc(snapshot_at),
        "age_minutes": round(age_minutes, 6),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_abs": spread_abs,
        "spread_pct": spread_pct,
        "browser_eligible": not reasons,
        "ineligible_reasons": sorted(set(reasons)),
        "bid_size": None,
        "ask_size": None,
        "depth_available": False,
        "capacity_assessed": False,
    }, reasons


def _contract_receipt(
    row: Mapping[str, Any],
    *,
    root: str,
    session: date,
    observed_at: datetime,
    available_at: datetime,
    open_at: datetime,
    close_at: datetime,
    oi_lookup: Mapping[tuple, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    expiry = row["expiration_date"]
    strike_decimal = row["strike_decimal"]
    strike_canonical = row["strike_canonical"]
    strike = row["strike_value"]
    right = row["right_value"]
    key = (root, expiry, strike_canonical, right)
    quote, reasons = _quote_state(
        row,
        observed_at=observed_at,
        available_at=available_at,
        open_at=open_at,
        close_at=close_at,
    )
    spot = _finite_float(row.get("underlying_price"))
    if spot is None or spot <= 0:
        reasons.append("MISSING_UNDERLYING_PRICE")
    dte = (expiry - session).days
    if dte < 0:
        reasons.append("EXPIRED_CONTRACT")
    if spot is None or spot <= 0:
        otm_pct = None
    elif right == "C":
        otm_pct = ((strike / spot) - 1.0) * 100.0
    else:
        otm_pct = (1.0 - (strike / spot)) * 100.0
    oi_row = oi_lookup.get(key)
    oi_value = (
        None
        if oi_row is None
        else _exact_nonnegative_integer(
            oi_row.get("open_interest_value"), field="open_interest"
        )
    )
    oi_ts = None if oi_row is None else _iso_utc(oi_row["snapshot_utc"])
    volume_value = _exact_nonnegative_integer(row.get("volume"), field="option volume")
    vintage_session = (
        _previous_session(session)
        if oi_row is None
        else oi_row["vintage_session_value"]
    )
    receipt = {
        "contract_id": _contract_id(root, expiry, right, strike_canonical),
        "contract": {
            "root": root,
            "expiration": expiry.isoformat(),
            "right": right,
            "strike": strike,
            "strike_canonical": strike_canonical,
            "occ_symbol": construct_occ_symbol(root, expiry, right, strike_decimal),
        },
        "dte_calendar_days": dte,
        "moneyness": {
            "underlying_price": spot,
            "otm_pct": otm_pct,
            "state": None if otm_pct is None else ("otm" if otm_pct > 0 else "atm_or_itm"),
        },
        "quote": quote,
        "greeks": {field: _finite_float(row.get(field)) for field in GREEK_FIELDS},
        "implied_vol": _finite_float(row.get("implied_vol")),
        "iv_error": _finite_float(row.get("iv_error")),
        "volume": {
            "value": None if volume_value is None else int(volume_value),
            "available": volume_value is not None,
            "source_note": (
                "chain_snapshot"
                if volume_value is not None
                else "volume_not_captured_by_chain_snapshot"
            ),
        },
        "open_interest": {
            "value": oi_value,
            "snapshot_ts": oi_ts,
            "vintage_session": vintage_session.isoformat(),
            "timing": "prior_session_eod_positions",
            "vintage_derivation": "previous_real_nyse_session",
        },
        "profile_matches": [],
        "profile_evaluations": {},
        "authority": authority_block(),
        "_source_row_ordinal": int(row["source_row_ordinal"]),
    }
    return receipt, sorted(set(reasons))


def _convex_profile(
    contracts: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    eligible: list[dict[str, Any]] = []
    filter_ids = (
        "browser_quote_fresh_valid",
        "dte_30_180",
        "otm_5_20_pct",
        "absolute_delta_0_10_0_45",
        "spread_pct_lte_15",
        "prior_session_oi_gte_100",
    )
    pass_counts = {filter_id: 0 for filter_id in filter_ids}
    evaluations: dict[str, dict[str, Any]] = {}
    for contract in contracts:
        delta = contract["greeks"]["delta"]
        otm_pct = contract["moneyness"]["otm_pct"]
        spread_pct = contract["quote"]["spread_pct"]
        oi = contract["open_interest"]["value"]
        checks = {
            "browser_quote_fresh_valid": bool(contract["quote"]["browser_eligible"]),
            "dte_30_180": 30 <= contract["dte_calendar_days"] <= 180,
            "otm_5_20_pct": otm_pct is not None and 5.0 <= otm_pct <= 20.0,
            "absolute_delta_0_10_0_45": delta is not None and 0.10 <= abs(delta) <= 0.45,
            "spread_pct_lte_15": spread_pct is not None and spread_pct <= 15.0,
            "prior_session_oi_gte_100": oi is not None and oi >= 100,
        }
        passed = [filter_id for filter_id in filter_ids if checks[filter_id]]
        failed = [filter_id for filter_id in filter_ids if not checks[filter_id]]
        for filter_id in passed:
            pass_counts[filter_id] += 1
        evaluations[contract["contract_id"]] = {
            "matched": not failed,
            "passed_filters": passed,
            "failed_filters": failed,
        }
        if not failed:
            eligible.append(contract)
            if len(eligible) > MAX_PROJECTED_CONTRACTS:
                raise OptionsStructureIntradayError(
                    f"projected contract count exceeds {MAX_PROJECTED_CONTRACTS}"
                )
    eligible.sort(key=lambda item: (
        item["quote"]["spread_pct"],
        -item["open_interest"]["value"],
        item["contract_id"],
    ))
    ids = [item["contract_id"] for item in eligible]
    return {
        "profile_id": CONVEX_PROFILE,
        "profile_kind": "research_filter",
        "status": "eligible" if ids else "abstain",
        "abstention_reason": None if ids else "NO_CONTRACT_PASSED_PROFILE",
        "definition": {
            "dte_calendar_days": {"minimum": 30, "maximum": 180},
            "otm_pct": {"minimum": 5.0, "maximum": 20.0},
            "absolute_delta": {"minimum": 0.10, "maximum": 0.45},
            "spread_pct_maximum": 15.0,
            "prior_session_open_interest_minimum": 100,
            "quote_browser_eligible_required": True,
            "research_only_not_reconstructed_competitor_rule": True,
            "ranking_inputs": [],
        },
        "within_profile_order": [
            "quote.spread_pct ASC",
            "open_interest.value DESC",
            "contract_id ASC",
        ],
        "evaluated_contract_count": len(contracts),
        "filter_pass_counts": pass_counts,
        "eligible_contract_ids": ids,
        "authority": authority_block(),
    }, evaluations


def _prophet_profile(
    contracts: Sequence[dict[str, Any]],
    request: Mapping[str, Any] | None,
    *,
    packet_session: date,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "profile_id": PROPHET_PROFILE,
        "profile_kind": "legacy_display_resolver",
        "definition": {
            "law_source": "engine.prophet_bridge.resolve_option",
            "right": "C for BULL; P for BEAR",
            "target_expiry": "nearest monthly >= clock_date + horizon_days + 15 calendar days",
            "primary": f"nearest delta to +{TARGET_DELTA:.2f} for calls / -{TARGET_DELTA:.2f} for puts",
            "fallback": "closest OTM strike when target-expiry delta is unavailable",
            "legacy_fallback_disclosure": (
                "resolve_option uses source row order for its EOD first-OTM fallback; "
                "this packet uses deterministic closest-OTM strike order"
            ),
            "primary_tie_semantics": "first source row, matching pandas Series.idxmin",
            "browser_gate_semantics": (
                "resolve the legacy candidate first; abstain rather than substitute when its quote or spot is ineligible"
            ),
            "quote_browser_eligible_required": True,
        },
        "within_profile_order": [],
        "eligible_contract_ids": [],
        "selection": None,
        "authority": authority_block(),
    }
    if request is None:
        return {
            **base,
            "status": "context_required",
            "abstention_reason": "MISSING_PROPHET_PLAN_CONTEXT",
            "request": None,
        }
    direction = request.get("direction")
    if not isinstance(direction, str) or direction not in {"BULL", "BEAR"}:
        raise OptionsStructureIntradayError("Prophet profile direction must be BULL or BEAR")
    anchor = _as_date(request.get("clock_date"), field="Prophet clock_date")
    if not nyse_calendar.is_session(anchor):
        raise OptionsStructureIntradayError("Prophet clock_date must be a real NYSE session")
    if anchor > packet_session:
        raise OptionsStructureIntradayError(
            "Prophet clock_date cannot be later than the packet session"
        )
    horizon = _required_control_integer(
        request.get("horizon_days"), field="Prophet horizon_days"
    )
    if horizon < 0 or horizon > 730:
        raise OptionsStructureIntradayError("Prophet horizon_days outside 0..730")
    entry_raw = request.get("entry")
    if (
        isinstance(entry_raw, bool)
        or not isinstance(entry_raw, (Real, Decimal))
    ):
        raise OptionsStructureIntradayError("Prophet entry must be a number")
    entry = _finite_required(entry_raw, field="Prophet entry")
    if entry <= 0:
        raise OptionsStructureIntradayError("Prophet entry must be positive")
    target_expiry = _next_monthly_expiry(anchor + timedelta(days=horizon + 15))
    right = "C" if direction == "BULL" else "P"
    request_block = {
        "direction": direction,
        "clock_date": anchor.isoformat(),
        "horizon_days": horizon,
        "entry": entry,
        "target_expiry": target_expiry.isoformat(),
        "right": right,
    }
    target = [
        item for item in contracts
        if item["contract"]["right"] == right
        and item["contract"]["expiration"] == target_expiry.isoformat()
    ]
    delta_target = TARGET_DELTA if right == "C" else -TARGET_DELTA
    primary = [item for item in target if item["greeks"]["delta"] is not None]
    if primary:
        primary.sort(key=lambda item: (
            abs(item["greeks"]["delta"] - delta_target),
            item["_source_row_ordinal"],
        ))
        chosen = primary[0]
        mode = "primary_delta60"
        ordering = [
            f"abs(greeks.delta - {delta_target:+.2f}) ASC",
            "source_row_ordinal ASC (legacy pandas idxmin first-row tie)",
        ]
    else:
        if right == "C":
            fallback = [item for item in target if item["contract"]["strike"] >= entry]
            fallback.sort(key=lambda item: (
                item["contract"]["strike"] - entry,
                item["_source_row_ordinal"],
            ))
        else:
            fallback = [item for item in target if item["contract"]["strike"] <= entry]
            fallback.sort(key=lambda item: (
                entry - item["contract"]["strike"],
                item["_source_row_ordinal"],
            ))
        if not fallback:
            return {
                **base,
                "status": "abstain",
                "abstention_reason": "NO_BROWSER_ELIGIBLE_TARGET_EXPIRY_CONTRACT",
                "request": request_block,
            }
        chosen = fallback[0]
        mode = "fallback_closest_otm_deterministic"
        ordering = [
            "absolute OTM distance from entry ASC",
            "source_row_ordinal ASC",
        ]
    if (
        not chosen["quote"]["browser_eligible"]
        or chosen["moneyness"]["underlying_price"] is None
        or chosen["moneyness"]["underlying_price"] <= 0
        or chosen["dte_calendar_days"] < 0
    ):
        return {
            **base,
            "status": "abstain",
            "abstention_reason": "LEGACY_CANDIDATE_NOT_BROWSER_ELIGIBLE",
            "request": request_block,
        }
    return {
        **base,
        "status": "selected",
        "abstention_reason": None,
        "request": request_block,
        "within_profile_order": ordering,
        "eligible_contract_ids": [chosen["contract_id"]],
        "selection": {
            "contract_id": chosen["contract_id"],
            "mode": mode,
            "target_delta": delta_target if mode == "primary_delta60" else None,
        },
    }


def build_packet(
    chain_frame: pd.DataFrame,
    oi_frame: pd.DataFrame,
    *,
    root: str,
    session_date: str | date,
    snapshot_bucket: str,
    observed_at: str | datetime,
    available_at: str | datetime | None = None,
    cadence_minutes: int = DEFAULT_CADENCE_MINUTES,
    prophet_request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one strict per-root/per-bucket descriptive packet."""
    safe_root = _safe_root(root)
    session = _as_date(session_date, field="session_date")
    open_at, close_at, bucket_at = _validate_session(session, snapshot_bucket)
    observed = _as_utc(
        observed_at,
        field="observed_at",
        naive_tz=timezone.utc,
        require_timezone=True,
    )
    available = _as_utc(
        observed_at if available_at is None else available_at,
        field="available_at",
        naive_tz=timezone.utc,
        require_timezone=True,
    )
    if available < observed:
        raise OptionsStructureIntradayError("available_at precedes observed_at")
    bucket_utc = bucket_at.astimezone(timezone.utc)
    if observed < bucket_utc:
        raise OptionsStructureIntradayError("builder observed_at precedes the requested bucket")
    latest_session_clock = close_at.astimezone(timezone.utc) + timedelta(
        minutes=QUOTE_FRESHNESS_MINUTES
    )
    if observed.astimezone(ET).date() != session or observed > latest_session_clock:
        raise OptionsStructureIntradayError("builder observed_at is outside the causal session window")
    if available.astimezone(ET).date() != session or available > latest_session_clock:
        raise OptionsStructureIntradayError("available_at is outside the causal session window")
    cadence = _required_control_integer(cadence_minutes, field="cadence_minutes")
    if cadence != DEFAULT_CADENCE_MINUTES:
        raise OptionsStructureIntradayError(
            f"cadence_minutes must be {DEFAULT_CADENCE_MINUTES} for MSC R2.2-A"
        )

    chain = _normalize_chain(
        chain_frame,
        root=safe_root,
        session=session,
        bucket=snapshot_bucket,
    )
    oi, oi_lookup, oi_usable_count, oi_expired_excluded_count = _normalize_oi(
        oi_frame,
        root=safe_root,
        session=session,
        observed_at=observed,
        session_open_at=open_at,
    )
    all_contracts: list[dict[str, Any]] = []
    quote_rejections: dict[str, int] = {}
    for _, row in chain.iterrows():
        receipt, reasons = _contract_receipt(
            row,
            root=safe_root,
            session=session,
            observed_at=observed,
            available_at=available,
            open_at=open_at,
            close_at=close_at,
            oi_lookup=oi_lookup,
        )
        for reason in reasons:
            quote_rejections[reason] = quote_rejections.get(reason, 0) + 1
        all_contracts.append(receipt)
    contract_ids = [item["contract_id"] for item in all_contracts]
    if len(contract_ids) != len(set(contract_ids)):
        raise OptionsStructureIntradayError("duplicate contract IDs after canonical identity binding")

    # Profiles are built independently; neither profile can influence the
    # other profile's membership or order.
    convex_profile, convex_evaluations = _convex_profile(all_contracts)
    profiles = {
        PROPHET_PROFILE: _prophet_profile(
            all_contracts, prophet_request, packet_session=session
        ),
        CONVEX_PROFILE: convex_profile,
    }
    match_map: dict[str, set[str]] = {}
    for profile_id in PROFILE_ORDER:
        for contract_id in profiles[profile_id]["eligible_contract_ids"]:
            match_map.setdefault(contract_id, set()).add(profile_id)
            if len(match_map) > MAX_PROJECTED_CONTRACTS:
                raise OptionsStructureIntradayError(
                    f"projected contract count exceeds {MAX_PROJECTED_CONTRACTS}"
                )
    projected: list[dict[str, Any]] = []
    for contract in all_contracts:
        matches = match_map.get(contract["contract_id"])
        if not matches:
            continue
        contract["profile_matches"] = sorted(matches)
        contract["profile_evaluations"] = {
            CONVEX_PROFILE: convex_evaluations[contract["contract_id"]],
        }
        contract.pop("_source_row_ordinal", None)
        projected.append(contract)
    # Contract order is identity-only, never a cross-profile recommendation.
    projected.sort(key=lambda item: item["contract_id"])

    chain_digest_columns = sorted(
        CHAIN_REQUIRED_COLUMNS.union(
            {"volume"} if "volume" in chain.columns else set()
        ).union({"source_row_ordinal"})
    )
    oi_digest_columns = sorted(
        OI_REQUIRED_COLUMNS.union(
            {"vintage_session"} if "vintage_session" in oi.columns else set()
        )
    )
    source_snapshot_times = list(chain["snapshot_utc"])
    packet: dict[str, Any] = {
        "schema": SCHEMA,
        "packet_id": None,
        "root": safe_root,
        "session": {
            "date": session.isoformat(),
            "open_at": _iso_utc(open_at.astimezone(timezone.utc)),
            "close_at": _iso_utc(close_at.astimezone(timezone.utc)),
            "early_close": is_early_close(session),
            "snapshot_bucket": snapshot_bucket,
            "bucket_at": _iso_utc(bucket_at.astimezone(timezone.utc)),
            "cadence_minutes": cadence,
        },
        "clocks": {
            "vendor_snapshot_ts_min": _iso_utc(min(source_snapshot_times)),
            "vendor_snapshot_ts_max": _iso_utc(max(source_snapshot_times)),
            "vendor_naive_clock_interpretation": "America/New_York",
            "builder_observed_at": _iso_utc(observed),
            "available_at": _iso_utc(available),
            "browser_freshness_limit_minutes": QUOTE_FRESHNESS_MINUTES,
        },
        "source_receipt": {
            "source_family": "chain_snapshot",
            "private_raw_parquet_published": False,
            "chain": {
                "logical_key": f"chain_snapshots/{safe_root}/{session.isoformat()}.parquet",
                "bucket_sha256": _frame_digest(chain, chain_digest_columns),
                "bucket_row_count": len(chain),
            },
            "prior_session_open_interest": {
                "logical_key": f"chain_snapshots/{safe_root}/{session.isoformat()}_oi.parquet",
                "projection_sha256": (
                    _frame_digest(oi, oi_digest_columns)
                    if len(oi)
                    else sha256(canonical_json_bytes([])).hexdigest()
                ),
                "row_count": len(oi),
                "usable_row_count": oi_usable_count,
                "expired_excluded_row_count": oi_expired_excluded_count,
                "vintage_session": _previous_session(session).isoformat(),
                "vintage_derivation": "previous_real_nyse_session",
            },
        },
        "coverage": {
            "complete_root_bucket": True,
            "source_contract_count": len(all_contracts),
            "browser_eligible_contract_count": sum(
                1 for item in all_contracts if item["quote"]["browser_eligible"]
            ),
            "projected_contract_count": len(projected),
            "quote_rejection_counts": dict(sorted(quote_rejections.items())),
        },
        "profiles": profiles,
        "contracts": projected,
        "limitations": {
            "bid_ask_depth": "unavailable",
            "capacity_assessed": False,
            "underlying_selection": "not_in_scope",
            "execution_quote_polling": "not_in_scope",
            "issuance": "not_authorized",
        },
        "authority": authority_block(),
    }
    identity_payload = dict(packet)
    identity_payload.pop("packet_id")
    packet["packet_id"] = f"packet:uchain:{sha256(canonical_json_bytes(identity_payload)).hexdigest()}"
    # Final encoding is a load-bearing strictness check, not merely serialization.
    strict_json_object(canonical_json_bytes(packet))
    return packet


def packet_key(root: str, session_date: str | date, snapshot_bucket: str) -> str:
    safe_root = _safe_root(root)
    session = _as_date(session_date, field="session_date")
    if not _BUCKET_RE.fullmatch(snapshot_bucket):
        raise OptionsStructureIntradayError(f"invalid snapshot bucket: {snapshot_bucket!r}")
    return f"options_structure/msc_intraday/{safe_root}/{session.isoformat()}/{snapshot_bucket.replace(':', '')}.json"


def current_key(root: str) -> str:
    return f"options_structure/msc_intraday/{_safe_root(root)}/current.json"


def index_key() -> str:
    return "options_structure/msc_intraday/index.json"


def object_receipt(key: str, body: bytes, packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "sha256": sha256(body).hexdigest(),
        "bytes": len(body),
        "packet_id": packet["packet_id"],
    }


def discovery_epoch(session_date: str, snapshot_bucket: str) -> str:
    session = _as_date(session_date, field="discovery session_date")
    if not _BUCKET_RE.fullmatch(snapshot_bucket):
        raise OptionsStructureIntradayError(
            f"invalid discovery snapshot bucket: {snapshot_bucket!r}"
        )
    return f"{session.isoformat()}/{snapshot_bucket}"


def build_current_pointer(
    packet: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    index_id: str,
) -> dict[str, Any]:
    epoch = discovery_epoch(
        packet["session"]["date"], packet["session"]["snapshot_bucket"]
    )
    payload: dict[str, Any] = {
        "schema": CURRENT_SCHEMA,
        "pointer_id": None,
        "root": packet["root"],
        "session_date": packet["session"]["date"],
        "snapshot_bucket": packet["session"]["snapshot_bucket"],
        "epoch": epoch,
        "available_at": packet["clocks"]["available_at"],
        "complete_root_bucket": True,
        "authoritative_discovery": False,
        "derived_from_index": {
            "key": index_key(),
            "index_id": index_id,
            "epoch": epoch,
        },
        "object": dict(receipt),
        "authority": authority_block(),
    }
    identity = dict(payload)
    identity.pop("pointer_id")
    payload["pointer_id"] = f"pointer:uchain:{sha256(canonical_json_bytes(identity)).hexdigest()}"
    return payload


def build_index(packets: Sequence[Mapping[str, Any]], receipts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if not packets:
        raise OptionsStructureIntradayError("cannot build an empty global index")
    ordered = sorted(packets, key=lambda item: item["root"])
    sessions = {(item["session"]["date"], item["session"]["snapshot_bucket"]) for item in ordered}
    if len(sessions) != 1:
        raise OptionsStructureIntradayError("global index packets do not share one session bucket")
    if len({item["root"] for item in ordered}) != len(ordered):
        raise OptionsStructureIntradayError("global index contains duplicate roots")
    session_date, bucket = next(iter(sessions))
    epoch = discovery_epoch(session_date, bucket)
    roots: list[dict[str, Any]] = []
    for packet in ordered:
        root = packet["root"]
        receipt = receipts.get(root)
        if receipt is None:
            raise OptionsStructureIntradayError(f"missing object receipt for {root}")
        roots.append({
            "root": root,
            "derivative_current_key": current_key(root),
            "object": dict(receipt),
        })
    available_values = {item["clocks"]["available_at"] for item in ordered}
    if len(available_values) != 1:
        raise OptionsStructureIntradayError("global index packets do not share available_at")
    payload: dict[str, Any] = {
        "schema": INDEX_SCHEMA,
        "index_id": None,
        "session_date": session_date,
        "snapshot_bucket": bucket,
        "epoch": epoch,
        "available_at": next(iter(available_values)),
        "complete_bucket": True,
        "authoritative_discovery": True,
        "commit_role": "sole_authoritative_global_index",
        "root_count": len(roots),
        "roots": roots,
        "profile_ordering": "none_across_profiles",
        "authority": authority_block(),
    }
    identity = dict(payload)
    identity.pop("index_id")
    payload["index_id"] = f"index:uchain:{sha256(canonical_json_bytes(identity)).hexdigest()}"
    return payload
