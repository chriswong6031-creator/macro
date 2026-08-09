"""Resumable, provenance-first TuShare full-A-share daily/security spine.

This collector is the universe-completeness substrate for China microstructure
research.  It deliberately does *not* score signals or claim alpha.  It builds:

* a lifecycle-aware SH/SZ/BJ security master (listed, delisted, paused and
  approved-but-not-yet-trading names);
* a stable identity alias table, including Beijing Stock Exchange old-code ->
  920-code mappings;
* an exact market-session clock attested by equal SSE and SZSE calendars;
* effective-dated name/ST provenance; and
* partitioned daily, daily-basic, price-limit, suspension and exact-daily ST
  observations.

Authority: ``context_only``.  The collector reads ``TUSHARE_TOKEN`` only through
``collectors.tushare_client``.  It never accepts, writes, hashes, or logs a token.

Store layout (``data/china_tushare_spine`` by default)::

    reference/source_stock_basic/{exchange}_{status}.parquet
    reference/source_bse_mapping.parquet
    reference/security_master.parquet
    reference/identity_aliases.parquet
    reference/trade_calendar/year=YYYY.parquet
    reference/market_sessions.parquet
    name_history/year=YYYY.parquet
    {daily,daily_basic,stk_limit,suspend_d,stock_st}/
        year=YYYY/month=MM/part.parquet
    event_daily/year=YYYY/month=MM/part.parquet
    coverage/daily_security_coverage.parquet
    collection_state.json
    completeness_manifest.json

Daily partitions are monthly, atomically replaced, and keyed by source unit
(normally one market session).  ``collection_state.json`` records successful
empty event days as well as landed partitions, so a zero-suspension day is not
queried forever.  Failed/unlicensed calls are never marked complete.

Exact-session contract
----------------------
TuShare's published ``trade_cal`` contract advertises SSE and SZSE (not BSE).
The canonical A-share session clock therefore requires exact equality between
the SSE and SZSE calendars.  BSE dates are derived from that attested consensus
from 2021-11-15 onward; this provenance is explicit in every manifest.

Positive-volume contract
------------------------
TuShare ``daily.vol`` is measured in lots (手).  Raw daily rows are retained,
including anomalous zero-volume rows, and gain ``positive_volume = vol > 0``.
Any consumer claiming a traded/listing session MUST filter that boolean; a row's
mere presence is not a trade.  Other endpoints have no volume field and must
join ``daily`` on ``(trade_date, ticker)`` before making a traded-universe claim.

ST contract
-----------
``stock_st`` is exact daily ST/risk-warning membership but its official history
starts 2016-01-01.  ``namechange`` supplies older effective-dated names and an
``is_st_name`` inference, but that inference is not represented as complete
daily ST membership.  Manifests preserve this pre-2016 gap.

Usage (no implicit full-history run)::

    python -m collectors.china_tushare_spine --start 20110101 --end 20260807
    python -m collectors.china_tushare_spine --start 20110101 --end 20260807 \
        --max-requests 50
    python -m collectors.china_tushare_spine --start 20110101 --end 20260807 \
        --dry-run

The default request cap is intentionally small.  Re-running resumes incomplete
units.  ``--allow-bulk`` is required to raise the cap above the safety ceiling
or disable it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from collectors import tushare_client as tc
from lib import config

log = logging.getLogger(__name__)

MANIFEST_SCHEMA_VERSION = "cn_tushare_a_share_spine_manifest.v1"
STATE_SCHEMA_VERSION = "cn_tushare_a_share_spine_state.v1"
AUTHORITY = "context_only"
SOURCE_NAME = "tushare_pro"

DEFAULT_STORE = config.data_dir() / "china_tushare_spine"
DEFAULT_ENDPOINTS = ("daily", "daily_basic", "stk_limit", "suspend_d", "stock_st")
DAILY_ENDPOINTS = frozenset(DEFAULT_ENDPOINTS)
EMPTY_ALLOWED_ENDPOINTS = frozenset({"suspend_d", "stock_st"})
DENSE_ENDPOINTS = frozenset({"daily", "daily_basic", "stk_limit"})

DEFAULT_MAX_REQUESTS = 50
SAFE_MAX_REQUESTS = 100
ST_DAILY_START = date(2016, 1, 1)
BSE_LAUNCH = date(2021, 11, 15)
CALENDAR_HISTORY_START = date(1991, 1, 1)
NAME_HISTORY_START_YEAR = 1990
NAMECHANGE_MAX_PER_RUN = 5

# A-share orders are quoted in CNY 0.01 increments.  Do not replace Decimal
# arithmetic here with Python/NumPy round: both are ties-to-even and binary
# floats cannot represent many half-cent cases exactly.  The current SZSE rule
# (2026, 3.3.11 and 3.3.19) explicitly requires 四舍五入 to the quote tick,
# then a one-tick move when the rounded band is closer than one tick, and a
# one-tick absolute floor.  Exact TuShare ``stk_limit`` values remain the event
# authority; this primitive is a deterministic validator/reconstruction tool.
A_SHARE_PRICE_TICK = Decimal("0.01")
A_SHARE_PRICE_SCALE = 100
SZSE_2026_TRADING_RULE_URL = (
    "https://docs.static.szse.cn/www/lawrules/rule/trade/current/"
    "W020260424690713155663.pdf"
)
SSE_2026_TRADING_RULE_URL = (
    "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/"
    "c/c_20260424_10816482.shtml"
)
TUSHARE_DAILY_DOC_URL = "https://tushare.pro/document/2?doc_id=27"
TUSHARE_STK_LIMIT_DOC_URL = "https://tushare.pro/document/2?doc_id=183"

EXCHANGES = ("SSE", "SZSE", "BSE")
CALENDAR_EXCHANGES = ("SSE", "SZSE")
LIST_STATUSES = ("L", "D", "P", "G")

MIC_BY_SOURCE_EXCHANGE = {"SSE": "XSHG", "SZSE": "XSHE", "BSE": "XBSE"}
REPO_SUFFIX_BY_SOURCE_EXCHANGE = {"SSE": "SS", "SZSE": "SZ", "BSE": "BJ"}
SOURCE_EXCHANGE_BY_SUFFIX = {"SH": "SSE", "SS": "SSE", "SZ": "SZSE", "BJ": "BSE"}

ENDPOINT_FIELDS: dict[str, str] = {
    "stock_basic": (
        "ts_code,symbol,name,area,industry,market,exchange,curr_type,"
        "list_status,list_date,delist_date,is_hs"
    ),
    "bse_mapping": "name,o_code,n_code,list_date",
    "trade_cal": "exchange,cal_date,is_open,pretrade_date",
    "namechange": "ts_code,name,start_date,end_date,ann_date,change_reason",
    "daily": (
        "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
    ),
    "daily_basic": (
        "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,"
        "pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv,"
        "limit_status"
    ),
    "stk_limit": "trade_date,ts_code,pre_close,up_limit,down_limit",
    "suspend_d": "ts_code,trade_date,suspend_timing,suspend_type",
    "stock_st": "ts_code,name,trade_date,type,type_name",
}

# If a response lands at its documented maximum, completeness is not provable.
# Refuse to mark that unit complete rather than silently blessing truncation.
SOURCE_ROW_CAPS: dict[str, int] = {
    "stock_basic": 6000,
    "daily": 6000,
    "daily_basic": 6000,
    "stk_limit": 5800,
    "stock_st": 1000,
    "bse_mapping": 1000,
}

KEY_COLUMNS: dict[str, list[str]] = {
    "daily": ["trade_date", "ticker"],
    "daily_basic": ["trade_date", "ticker"],
    "stk_limit": ["trade_date", "ticker"],
    "suspend_d": ["trade_date", "ticker", "suspend_type", "suspend_timing"],
    "stock_st": ["trade_date", "ticker", "st_type"],
    "event_daily": ["trade_date", "ticker"],
    "name_history": ["ticker", "effective_from", "name", "announced_date"],
    "trade_calendar": ["exchange", "cal_date"],
}

_ST_PREFIX = re.compile(r"^(?:N?\*ST|N?ST|S\*ST|SST|PT)", re.IGNORECASE)
_COMPACT_DATE = re.compile(r"^\d{8}$")
_TUSHARE_CODE = re.compile(r"^(?P<code>\d{6})\.(?P<suffix>SH|SS|SZ|BJ)$", re.IGNORECASE)


class SpineError(RuntimeError):
    """Fail-closed contract or store-integrity error."""


class RequestBudgetExhausted(SpineError):
    """Internal control-flow signal for a clean resumable stop."""


@dataclass(frozen=True)
class Identity:
    """Canonical security identity while retaining the vendor-observed code."""

    source_ts_code: str
    ticker: str
    security_id: str
    source_exchange: str
    repo_exchange: str
    mic: str
    code: str
    board: str


@dataclass(frozen=True)
class LimitPriceBounds:
    """Exact CNY price-limit bounds in both Decimal yuan and integer cents."""

    upper: Decimal
    lower: Decimal
    upper_cents: int
    lower_cents: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(value: str | date | pd.Timestamp) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    text = str(value).strip()
    try:
        if _COMPACT_DATE.fullmatch(text):
            return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        return date.fromisoformat(text)
    except ValueError as exc:
        raise SpineError(f"invalid date {value!r}; expected YYYYMMDD or YYYY-MM-DD") from exc


def _compact(value: str | date | pd.Timestamp) -> str:
    return _parse_date(value).strftime("%Y%m%d")


def _exact_decimal(value: Any, *, field: str) -> Decimal:
    """Parse a finite decimal through text, never through binary-float state."""
    if isinstance(value, bool) or value is None:
        raise SpineError(f"{field} must be a finite decimal")
    try:
        if pd.isna(value):
            raise SpineError(f"{field} must be a finite decimal")
    except (TypeError, ValueError):
        pass
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise SpineError(f"{field} must be a finite decimal") from exc
    if not parsed.is_finite():
        raise SpineError(f"{field} must be a finite decimal")
    return parsed


def _quote_price_cents(
    value: Any,
    *,
    field: str,
    allow_missing: bool = False,
) -> int | None:
    """Validate a positive A-share quote and return its lossless cent value."""
    if value is None:
        if allow_missing:
            return None
        raise SpineError(f"{field} is required")
    try:
        if pd.isna(value):
            if allow_missing:
                return None
            raise SpineError(f"{field} is required")
    except (TypeError, ValueError):
        pass
    price = _exact_decimal(value, field=field)
    if price <= 0:
        raise SpineError(f"{field} must be positive")
    tick_price = price.quantize(A_SHARE_PRICE_TICK, rounding=ROUND_HALF_UP)
    if price != tick_price:
        raise SpineError(
            f"{field}={price} is off the A-share CNY {A_SHARE_PRICE_TICK} quote tick"
        )
    return int(tick_price * A_SHARE_PRICE_SCALE)


def a_share_limit_price_bounds(
    previous_close: str | float | Decimal,
    limit_ratio: str | float | Decimal,
) -> LimitPriceBounds:
    """Return legal half-up CNY bounds for a caller-supplied limit ratio.

    This implements the current SZSE 2026 rule 3.3.19 mechanics: calculate
    ``previous_close * (1 +/- ratio)``, round half-up to CNY 0.01, force at
    least one quote tick of separation from the previous close, and floor a
    bound at one tick.  The previous close must itself be an exact quote.

    The function does not decide whether a security/date has a limit or which
    effective-dated ratio applies.  In the full-A spine, vendor ``stk_limit``
    is authoritative and this function is used only for validation or an
    explicitly scoped reconstruction.
    """
    previous_cents = _quote_price_cents(previous_close, field="previous_close")
    assert previous_cents is not None
    previous = Decimal(previous_cents) / A_SHARE_PRICE_SCALE
    ratio = _exact_decimal(limit_ratio, field="limit_ratio")
    if ratio <= 0 or ratio >= 1:
        raise SpineError("limit_ratio must be greater than 0 and less than 1")

    upper = (previous * (Decimal(1) + ratio)).quantize(
        A_SHARE_PRICE_TICK, rounding=ROUND_HALF_UP,
    )
    lower = (previous * (Decimal(1) - ratio)).quantize(
        A_SHARE_PRICE_TICK, rounding=ROUND_HALF_UP,
    )
    if abs(upper - previous) < A_SHARE_PRICE_TICK:
        upper = previous + A_SHARE_PRICE_TICK
    if abs(previous - lower) < A_SHARE_PRICE_TICK:
        lower = previous - A_SHARE_PRICE_TICK
    upper = max(upper, A_SHARE_PRICE_TICK)
    lower = max(lower, A_SHARE_PRICE_TICK)
    return LimitPriceBounds(
        upper=upper,
        lower=lower,
        upper_cents=int(upper * A_SHARE_PRICE_SCALE),
        lower_cents=int(lower * A_SHARE_PRICE_SCALE),
    )


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "nat"}:
        return None
    return _parse_date(text).isoformat()


def _source_ts_code(value: Any) -> str:
    """Return TuShare's suffix convention, reversing the shared client's .SS map."""
    text = str(value or "").strip().upper()
    if text.endswith(".SS"):
        return text[:-3] + ".SH"
    return text


def _board_for(code: str, source_exchange: str) -> str:
    if source_exchange == "BSE":
        return "bse"
    if source_exchange == "SSE" and code.startswith(("688", "689")):
        return "star"
    if source_exchange == "SZSE" and code.startswith(("300", "301", "302")):
        return "chinext"
    return "main"


def canonical_identity(
    ts_code: Any,
    *,
    bse_aliases: Mapping[str, str] | None = None,
) -> Identity:
    """Canonicalise SH/SZ/BJ identity and apply BSE old -> 920 aliases.

    ``ticker`` follows the repository convention (Shanghai ``.SS``), while
    ``source_ts_code`` always follows TuShare (Shanghai ``.SH``).  ``security_id``
    is stable and venue-qualified; it must be used instead of a bare six-digit
    code in cross-exchange stores.
    """
    observed_source = _source_ts_code(ts_code)
    if not _TUSHARE_CODE.fullmatch(observed_source):
        raise SpineError(f"not a canonical SH/SZ/BJ TuShare code: {ts_code!r}")
    source = observed_source
    if bse_aliases:
        source = _source_ts_code(bse_aliases.get(source, source))
    match = _TUSHARE_CODE.fullmatch(source)
    if not match:
        raise SpineError(f"not a canonical SH/SZ/BJ TuShare code: {ts_code!r}")
    code = match.group("code")
    suffix = match.group("suffix").upper()
    source_exchange = SOURCE_EXCHANGE_BY_SUFFIX[suffix]
    repo_suffix = REPO_SUFFIX_BY_SOURCE_EXCHANGE[source_exchange]
    mic = MIC_BY_SOURCE_EXCHANGE[source_exchange]
    return Identity(
        source_ts_code=observed_source,
        ticker=f"{code}.{repo_suffix}",
        security_id=f"CN-{mic}-{code}",
        source_exchange=source_exchange,
        repo_exchange=repo_suffix,
        mic=mic,
        code=code,
        board=_board_for(code, source_exchange),
    )


def is_st_name(name: Any) -> bool:
    """Conservative name-based ST/risk-warning inference for name history."""
    text = re.sub(r"\s+", "", str(name or "")).upper()
    return bool(_ST_PREFIX.match(text))


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _assert_configured_token_absent(raw: bytes, *, artifact: str) -> None:
    """Fail before hashing/receipting if configured credential bytes escaped."""
    secret = tc.token()
    if secret and secret.encode("utf-8") in raw:
        raise SpineError(f"configured credential bytes found in artifact: {artifact}")


def _receipt_bytes(path: Path, store: Path) -> bytes:
    raw = path.read_bytes()
    _assert_configured_token_absent(raw, artifact=path.relative_to(store).as_posix())
    return raw


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return str(value)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".parquet")
    os.close(fd)
    try:
        frame.to_parquet(temporary, index=False, compression="zstd")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_parquet_strict(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        raise SpineError(f"unreadable existing spine partition: {path}: {exc}") from exc


def _duplicates(frame: pd.DataFrame, keys: Sequence[str]) -> int:
    if frame.empty:
        return 0
    missing = [key for key in keys if key not in frame.columns]
    if missing:
        raise SpineError(f"partition missing key columns {missing}")
    return int(frame.duplicated(list(keys), keep=False).sum())


def _upsert_partition(
    path: Path,
    new: pd.DataFrame,
    *,
    keys: Sequence[str],
) -> tuple[int, int]:
    """Atomically upsert a deterministic monthly/reference partition.

    Returns ``(rows_after, revised_key_count)``.  Existing unreadable content is
    fatal; it is never overwritten as though absent.
    """
    incoming = new.copy()
    if _duplicates(incoming, keys):
        raise SpineError(f"incoming rows duplicate keys {list(keys)} for {path}")
    revised = 0
    if path.exists():
        existing = _read_parquet_strict(path)
        if _duplicates(existing, keys):
            raise SpineError(f"existing rows duplicate keys {list(keys)} for {path}")
        if incoming.empty:
            return len(existing), 0
        old_keys = set(map(tuple, existing[list(keys)].itertuples(index=False, name=None)))
        new_keys = set(map(tuple, incoming[list(keys)].itertuples(index=False, name=None)))
        revised = len(old_keys & new_keys)
        combined = pd.concat([existing, incoming], ignore_index=True)
        combined = combined.drop_duplicates(list(keys), keep="last")
    else:
        combined = incoming
    if not combined.empty:
        combined = combined.sort_values(list(keys), kind="stable", na_position="last")
    combined = combined.reset_index(drop=True)
    _atomic_parquet(path, combined)
    return len(combined), revised


def _replace_partition_units(
    path: Path,
    new: pd.DataFrame,
    *,
    keys: Sequence[str],
    unit_column: str,
    units: Iterable[str],
) -> tuple[int, int]:
    """Replace complete exact-source units inside a shared partition.

    A successful exact-day re-fetch is a snapshot, not an append. Removing all
    old rows for the day before inserting the new response prevents vendor
    deletions (including a newly empty suspension/ST day) from leaving ghosts.
    """
    incoming = new.copy()
    unit_values = {str(value) for value in units}
    if not unit_values:
        raise SpineError("partition replacement requires at least one source unit")
    if _duplicates(incoming, keys):
        raise SpineError(f"incoming rows duplicate keys {list(keys)} for {path}")
    if not incoming.empty:
        if unit_column not in incoming.columns:
            raise SpineError(f"incoming partition lacks unit column {unit_column!r}")
        unexpected = set(incoming[unit_column].astype(str)) - unit_values
        if unexpected:
            raise SpineError(f"incoming partition crossed source units: {sorted(unexpected)[:10]}")

    revised = 0
    if path.exists():
        existing = _read_parquet_strict(path)
        if _duplicates(existing, keys):
            raise SpineError(f"existing rows duplicate keys {list(keys)} for {path}")
        if unit_column not in existing.columns and not existing.empty:
            raise SpineError(f"existing partition lacks unit column {unit_column!r}")
        old_unit = existing[
            existing[unit_column].astype(str).isin(unit_values)
        ] if not existing.empty else existing
        if not incoming.empty and not old_unit.empty:
            old_keys = set(map(tuple, old_unit[list(keys)].itertuples(index=False, name=None)))
            new_keys = set(map(tuple, incoming[list(keys)].itertuples(index=False, name=None)))
            revised = len(old_keys & new_keys)
        retained = existing[
            ~existing[unit_column].astype(str).isin(unit_values)
        ] if not existing.empty else existing
        combined = pd.concat([retained, incoming], ignore_index=True)
    else:
        if incoming.empty:
            return 0, 0
        combined = incoming
    if not combined.empty:
        combined = combined.sort_values(list(keys), kind="stable", na_position="last")
    combined = combined.reset_index(drop=True)
    _atomic_parquet(path, combined)
    return len(combined), revised


def _empty_state() -> dict[str, Any]:
    return {"schema_version": STATE_SCHEMA_VERSION, "units": {}}


def load_state(store: Path) -> dict[str, Any]:
    path = store / "collection_state.json"
    if not path.exists():
        return _empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SpineError(f"collection state is unreadable: {path}: {exc}") from exc
    if state.get("schema_version") != STATE_SCHEMA_VERSION or not isinstance(state.get("units"), dict):
        raise SpineError(f"collection state has an unsupported schema: {path}")
    return state


def _unit_record(state: Mapping[str, Any], endpoint: str, unit: str) -> Mapping[str, Any] | None:
    endpoint_units = state.get("units", {}).get(endpoint, {})
    record = endpoint_units.get(unit) if isinstance(endpoint_units, dict) else None
    return record if isinstance(record, dict) else None


def _unit_done(state: Mapping[str, Any], store: Path, endpoint: str, unit: str) -> bool:
    record = _unit_record(state, endpoint, unit)
    if not record or record.get("status") not in {"complete", "empty"}:
        return False
    partition = record.get("partition")
    return not partition or (store / str(partition)).exists()


def _set_unit(
    state: dict[str, Any],
    store: Path,
    endpoint: str,
    unit: str,
    *,
    status: str,
    observed_at: str,
    row_count: int = 0,
    source_row_count: int = 0,
    dropped_row_count: int = 0,
    unmatched_master_row_count: int = 0,
    revised_key_count: int = 0,
    partition: Path | None = None,
    reason: str | None = None,
) -> None:
    if status not in {"complete", "empty", "failed"}:
        raise SpineError(f"invalid state status: {status}")
    endpoint_units = state.setdefault("units", {}).setdefault(endpoint, {})
    previous = endpoint_units.get(unit, {})
    record: dict[str, Any] = {
        "status": status,
        "observed_at": observed_at,
        "row_count": int(row_count),
        "source_row_count": int(source_row_count),
        "dropped_row_count": int(dropped_row_count),
        "unmatched_master_row_count": int(unmatched_master_row_count),
        "revised_key_count": int(revised_key_count),
        "attempts": int(previous.get("attempts", 0)) + 1,
    }
    if partition is not None:
        record["partition"] = partition.relative_to(store).as_posix()
    if reason:
        # Never place a vendor response or credential-bearing exception in state.
        record["reason"] = reason
    endpoint_units[unit] = record
    _atomic_json(store / "collection_state.json", state)


def _bse_alias_map(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {}
    needed = {"o_code", "n_code"}
    if not needed.issubset(frame.columns):
        raise SpineError(f"bse_mapping missing columns: {sorted(needed - set(frame.columns))}")
    aliases: dict[str, str] = {}
    for row in frame.itertuples(index=False):
        old = _source_ts_code(row.o_code)
        new = _source_ts_code(row.n_code)
        old_identity = canonical_identity(old)
        new_identity = canonical_identity(new)
        if old_identity.source_exchange != "BSE" or new_identity.source_exchange != "BSE":
            raise SpineError(f"non-BSE row in bse_mapping: {old!r} -> {new!r}")
        if old in aliases and aliases[old] != new:
            raise SpineError(f"conflicting BSE alias: {old} -> {aliases[old]} / {new}")
        aliases[old] = new
    return aliases


def _load_bse_mapping(store: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    path = store / "reference" / "source_bse_mapping.parquet"
    if not path.exists():
        raise SpineError("BSE identity mapping is absent; reference bootstrap is incomplete")
    frame = _read_parquet_strict(path)
    return frame, _bse_alias_map(frame)


def _normalise_bse_mapping(frame: pd.DataFrame) -> pd.DataFrame:
    expected = ["name", "o_code", "n_code", "list_date"]
    missing = [column for column in expected if column not in frame.columns]
    if missing and not frame.empty:
        raise SpineError(f"bse_mapping missing columns {missing}")
    if frame.empty:
        return pd.DataFrame(columns=expected)
    out = frame[expected].copy()
    out["o_code"] = out["o_code"].map(_source_ts_code)
    out["n_code"] = out["n_code"].map(_source_ts_code)
    out["list_date"] = out["list_date"].map(_iso)
    _bse_alias_map(out)
    return out.sort_values(["n_code", "o_code"], kind="stable").reset_index(drop=True)


def compile_security_master(store: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compile security master + alias table from landed reference source units."""
    mapping, aliases = _load_bse_mapping(store)
    raw_frames: list[pd.DataFrame] = []
    for exchange in EXCHANGES:
        for status in LIST_STATUSES:
            path = store / "reference" / "source_stock_basic" / f"{exchange}_{status}.parquet"
            if not path.exists():
                raise SpineError(f"stock_basic reference unit absent: {exchange}/{status}")
            frame = _read_parquet_strict(path)
            if not frame.empty:
                raw_frames.append(frame)
    if not raw_frames:
        raise SpineError("stock_basic reference returned no securities")
    raw = pd.concat(raw_frames, ignore_index=True)
    required = {"ts_code", "name", "exchange", "list_status", "list_date"}
    missing = required - set(raw.columns)
    if missing:
        raise SpineError(f"stock_basic source missing columns {sorted(missing)}")

    rows: list[dict[str, Any]] = []
    for item in raw.to_dict(orient="records"):
        ident = canonical_identity(item.get("ts_code"), bse_aliases=aliases)
        declared_exchange = str(item.get("exchange") or "").upper()
        if declared_exchange and declared_exchange != ident.source_exchange:
            raise SpineError(
                f"stock_basic exchange disagrees with code: {item.get('ts_code')} "
                f"({declared_exchange} != {ident.source_exchange})"
            )
        list_date = _iso(item.get("list_date"))
        if list_date is None:
            # Approved/untraded G rows may lack a listing date.  They remain in
            # the master but cannot enter a historical eligible universe.
            effective_from = None
        else:
            effective_from_date = _parse_date(list_date)
            if ident.source_exchange == "BSE":
                effective_from_date = max(effective_from_date, BSE_LAUNCH)
            effective_from = effective_from_date.isoformat()
        delist_date = _iso(item.get("delist_date"))
        rows.append({
            "security_id": ident.security_id,
            "ticker": ident.ticker,
            "source_ts_code": ident.source_ts_code,
            "code": ident.code,
            "mic": ident.mic,
            "exchange": ident.source_exchange,
            "repo_exchange": ident.repo_exchange,
            "board": ident.board,
            "name": str(item.get("name") or ""),
            "market": str(item.get("market") or ""),
            "currency": str(item.get("curr_type") or ""),
            "list_status": str(item.get("list_status") or ""),
            "list_date": list_date,
            "delist_date": delist_date,
            "effective_from": effective_from,
            "effective_to": delist_date,
            "area": str(item.get("area") or ""),
            "industry": str(item.get("industry") or ""),
            "is_hs": str(item.get("is_hs") or ""),
            "source": "tushare.stock_basic",
        })
    master = pd.DataFrame(rows)
    if master.empty:
        raise SpineError("compiled security master is empty")
    duplicate_tickers = master[master.duplicated("ticker", keep=False)]
    if not duplicate_tickers.empty:
        # Identical duplicate status units are harmless only after exact dedup.
        comparison = [c for c in master.columns if c != "source"]
        master = master.drop_duplicates(comparison, keep="last")
        if master.duplicated("ticker", keep=False).any():
            tickers = sorted(master.loc[master.duplicated("ticker", keep=False), "ticker"].unique())
            raise SpineError(f"conflicting security-master identities: {tickers[:10]}")
    master = master.sort_values(["exchange", "ticker"], kind="stable").reset_index(drop=True)

    alias_rows: list[dict[str, Any]] = []
    for row in master.itertuples(index=False):
        alias_rows.append({
            "alias_ticker": row.ticker,
            "canonical_ticker": row.ticker,
            "security_id": row.security_id,
            "alias_kind": "canonical",
            "source": "tushare.stock_basic",
        })
    for item in mapping.to_dict(orient="records"):
        old_ident = canonical_identity(item["o_code"])
        new_ident = canonical_identity(item["n_code"])
        alias_rows.append({
            "alias_ticker": old_ident.ticker,
            "canonical_ticker": new_ident.ticker,
            "security_id": new_ident.security_id,
            "alias_kind": "bse_old_code",
            "source": "tushare.bse_mapping",
        })
    alias_frame = pd.DataFrame(alias_rows).drop_duplicates(
        ["alias_ticker", "canonical_ticker", "alias_kind"], keep="last"
    )
    conflicts = alias_frame.groupby("alias_ticker")["canonical_ticker"].nunique()
    if int((conflicts > 1).sum()):
        raise SpineError("identity alias maps one alias ticker to multiple canonical tickers")
    alias_frame = alias_frame.sort_values(["alias_ticker", "alias_kind"], kind="stable").reset_index(drop=True)
    _atomic_parquet(store / "reference" / "security_master.parquet", master)
    _atomic_parquet(store / "reference" / "identity_aliases.parquet", alias_frame)
    return master, alias_frame


def _normalise_calendar(frame: pd.DataFrame, exchange: str, start: date, end: date) -> pd.DataFrame:
    needed = {"cal_date", "is_open"}
    if not needed.issubset(frame.columns):
        raise SpineError(f"trade_cal missing columns {sorted(needed - set(frame.columns))}")
    out = frame.copy()
    out["exchange"] = exchange
    out["cal_date"] = out["cal_date"].map(_iso)
    out["pretrade_date"] = out.get("pretrade_date", pd.Series([None] * len(out))).map(_iso)
    out["is_open"] = pd.to_numeric(out["is_open"], errors="coerce").astype("Int64")
    if out["cal_date"].isna().any() or not set(out["is_open"].dropna().astype(int)).issubset({0, 1}):
        raise SpineError(f"trade_cal returned invalid dates/is_open values for {exchange}")
    if out["is_open"].isna().any():
        raise SpineError(f"trade_cal returned null is_open values for {exchange}")
    expected = {d.date().isoformat() for d in pd.date_range(start, end, freq="D")}
    actual = set(out["cal_date"].astype(str))
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SpineError(
            f"trade_cal calendar-day coverage mismatch for {exchange}: "
            f"missing={missing[:5]} extra={extra[:5]}"
        )
    out = out[["exchange", "cal_date", "is_open", "pretrade_date"]]
    if _duplicates(out, KEY_COLUMNS["trade_calendar"]):
        raise SpineError(f"trade_cal duplicated exchange/date rows for {exchange}")
    return out.sort_values(["exchange", "cal_date"], kind="stable").reset_index(drop=True)


def compile_market_sessions(store: Path, start: date, end: date) -> pd.DataFrame:
    """Build the canonical session clock, requiring exact SSE/SZSE agreement."""
    frames = [_read_parquet_strict(path) for path in sorted(
        (store / "reference" / "trade_calendar").glob("year=*.parquet")
    )]
    if not frames:
        raise SpineError("no trade-calendar partitions are available")
    calendar = pd.concat(frames, ignore_index=True)
    calendar = calendar.drop_duplicates(["exchange", "cal_date"], keep="last")
    calendar["cal_date"] = calendar["cal_date"].astype(str)
    requested_dates = {d.date().isoformat() for d in pd.date_range(start, end, freq="D")}
    calendar_dates: dict[str, set[str]] = {}
    opens: dict[str, set[str]] = {}
    for exchange in CALENDAR_EXCHANGES:
        all_subset = calendar[calendar["exchange"] == exchange]
        calendar_dates[exchange] = set(all_subset["cal_date"])
        subset = all_subset[all_subset["cal_date"].isin(requested_dates)]
        if set(subset["cal_date"]) != requested_dates:
            missing = sorted(requested_dates - set(subset["cal_date"]))
            raise SpineError(f"calendar is incomplete for {exchange}: {missing[:10]}")
        opens[exchange] = set(all_subset.loc[pd.to_numeric(all_subset["is_open"]) == 1, "cal_date"])
    if calendar_dates["SSE"] != calendar_dates["SZSE"]:
        raise SpineError("SSE/SZSE calendar-day coverage differs across landed partitions")
    if opens["SSE"] != opens["SZSE"]:
        only_sse = sorted(opens["SSE"] - opens["SZSE"])
        only_szse = sorted(opens["SZSE"] - opens["SSE"])
        raise SpineError(
            "SSE/SZSE open-session calendars disagree; refusing a synthetic clock: "
            f"only_sse={only_sse[:10]} only_szse={only_szse[:10]}"
        )
    for exchange in CALENDAR_EXCHANGES:
        ordered_open = calendar[
            (calendar["exchange"] == exchange) & (pd.to_numeric(calendar["is_open"]) == 1)
        ].sort_values("cal_date", kind="stable")
        previous: str | None = None
        for row in ordered_open.itertuples(index=False):
            current = str(row.cal_date)
            declared_previous = _iso(row.pretrade_date)
            if previous is not None and declared_previous != previous:
                raise SpineError(
                    f"{exchange} pretrade_date breaks exact-session adjacency at {current}: "
                    f"{declared_previous!r} != {previous!r}"
                )
            previous = current

    all_calendar_dates = sorted(opens["SSE"])
    position = {session: idx for idx, session in enumerate(all_calendar_dates)}
    sessions = pd.DataFrame({"trade_date": all_calendar_dates})
    sessions["market_session_position"] = sessions["trade_date"].map(position).astype("int64")
    sessions["calendar_provenance"] = "tushare.trade_cal:SSE=SZSE"
    sessions["bse_calendar_provenance"] = "derived_from_attested_SSE_SZSE_consensus"
    _atomic_parquet(store / "reference" / "market_sessions.parquet", sessions)
    return sessions


def _master_maps(store: Path) -> tuple[pd.DataFrame, dict[str, str], dict[str, dict[str, Any]]]:
    master_path = store / "reference" / "security_master.parquet"
    if not master_path.exists():
        raise SpineError("security master is absent; reference bootstrap is incomplete")
    master = _read_parquet_strict(master_path)
    _, aliases = _load_bse_mapping(store)
    lookup = {str(row["ticker"]): row for row in master.to_dict(orient="records")}
    return master, aliases, lookup


def _session_map(store: Path) -> dict[str, int]:
    path = store / "reference" / "market_sessions.parquet"
    if not path.exists():
        raise SpineError("market-session clock is absent")
    sessions = _read_parquet_strict(path)
    return dict(zip(sessions["trade_date"].astype(str), sessions["market_session_position"].astype(int)))


def _identity_columns(identity: Identity) -> dict[str, Any]:
    return {
        "security_id": identity.security_id,
        "ticker": identity.ticker,
        "source_ts_code": identity.source_ts_code,
        "exchange": identity.source_exchange,
        "board": identity.board,
    }


def normalise_name_history(frame: pd.DataFrame, store: Path) -> tuple[pd.DataFrame, int]:
    _, aliases, master_lookup = _master_maps(store)
    required = {"ts_code", "name", "start_date", "end_date", "ann_date", "change_reason"}
    if not required.issubset(frame.columns) and not frame.empty:
        raise SpineError(f"namechange missing columns {sorted(required - set(frame.columns))}")
    rows: list[dict[str, Any]] = []
    orphans = 0
    for item in frame.to_dict(orient="records"):
        ident = canonical_identity(item.get("ts_code"), bse_aliases=aliases)
        if ident.ticker not in master_lookup:
            orphans += 1
        name = str(item.get("name") or "")
        rows.append({
            **_identity_columns(ident),
            "name": name,
            "effective_from": _iso(item.get("start_date")),
            "effective_to": _iso(item.get("end_date")),
            "announced_date": _iso(item.get("ann_date")),
            "change_reason": str(item.get("change_reason") or ""),
            "is_st_name": is_st_name(name),
            "st_provenance": "namechange_name_inference_partial",
            "source": "tushare.namechange",
        })
    columns = [
        "security_id", "ticker", "source_ts_code", "exchange", "board", "name",
        "effective_from", "effective_to", "announced_date", "change_reason",
        "is_st_name", "st_provenance", "source",
    ]
    out = pd.DataFrame(rows, columns=columns)
    if not out.empty and _duplicates(out, KEY_COLUMNS["name_history"]):
        raise SpineError("namechange produced duplicate effective-name keys")
    return out, orphans


def normalise_daily_endpoint(
    endpoint: str,
    frame: pd.DataFrame,
    trade_date: str | date,
    store: Path,
) -> tuple[pd.DataFrame, int]:
    """Normalise one exact-session endpoint response and filter to the A-share master."""
    if endpoint not in DAILY_ENDPOINTS:
        raise SpineError(f"unsupported daily spine endpoint: {endpoint}")
    expected_date = _parse_date(trade_date).isoformat()
    sessions = _session_map(store)
    if expected_date not in sessions:
        raise SpineError(f"off-calendar endpoint unit: {endpoint}/{expected_date}")
    _, aliases, master_lookup = _master_maps(store)
    if "ts_code" not in frame.columns or "trade_date" not in frame.columns:
        raise SpineError(f"{endpoint} missing ts_code/trade_date")

    rows: list[dict[str, Any]] = []
    dropped = 0
    for item in frame.to_dict(orient="records"):
        source_date = _iso(item.get("trade_date"))
        if source_date != expected_date:
            raise SpineError(
                f"{endpoint} response crossed requested session {expected_date}: {source_date}"
            )
        ident = canonical_identity(item.get("ts_code"), bse_aliases=aliases)
        master_row = master_lookup.get(ident.ticker)
        if master_row is None:
            # stk_limit includes B-shares/funds by contract.  Anything not in
            # stock_basic's A-share lifecycle is excluded and counted.
            dropped += 1
            continue
        row: dict[str, Any] = {
            **_identity_columns(ident),
            "trade_date": expected_date,
            "market_session_position": sessions[expected_date],
            "source": f"tushare.{endpoint}",
        }
        if endpoint == "daily":
            volume = pd.to_numeric(item.get("vol"), errors="coerce")
            if pd.notna(volume) and (not math.isfinite(float(volume)) or float(volume) < 0):
                raise SpineError("daily.vol must be finite and non-negative")
            amount = pd.to_numeric(item.get("amount"), errors="coerce")
            if pd.notna(amount) and (not math.isfinite(float(amount)) or float(amount) < 0):
                raise SpineError("daily.amount must be finite and non-negative")
            row["volume_lots"] = volume
            row["amount_cny_thousands"] = amount
            row["positive_volume"] = bool(pd.notna(volume) and float(volume) > 0.0)
            for column in ("open", "high", "low", "close", "pre_close"):
                cents = _quote_price_cents(
                    item.get(column), field=f"daily.{column}",
                    allow_missing=not row["positive_volume"],
                )
                row[f"{column}_cents"] = cents
                row[column] = (
                    float(Decimal(cents) / A_SHARE_PRICE_SCALE)
                    if cents is not None else None
                )
            for column in ("change", "pct_chg"):
                row[column] = pd.to_numeric(item.get(column), errors="coerce")
            present_ohlc = [row[f"{column}_cents"] for column in ("open", "high", "low", "close")]
            if all(value is not None for value in present_ohlc):
                open_cents, high_cents, low_cents, close_cents = present_ohlc
                if high_cents < max(open_cents, close_cents) or low_cents > min(open_cents, close_cents):
                    raise SpineError("daily OHLC ordering is internally inconsistent")
                if low_cents > high_cents:
                    raise SpineError("daily.low exceeds daily.high")
            row["price_source_basis"] = "tushare.daily_unadjusted_nominal"
            row["quote_tick_cny"] = float(A_SHARE_PRICE_TICK)
        elif endpoint == "daily_basic":
            for column in [c for c in ENDPOINT_FIELDS[endpoint].split(",") if c not in {"ts_code", "trade_date"}]:
                row[column] = pd.to_numeric(item.get(column), errors="coerce")
        elif endpoint == "stk_limit":
            pre_close_cents = _quote_price_cents(
                item.get("pre_close"), field="stk_limit.pre_close",
            )
            up_missing = item.get("up_limit") is None or pd.isna(item.get("up_limit"))
            down_missing = item.get("down_limit") is None or pd.isna(item.get("down_limit"))
            if up_missing != down_missing:
                raise SpineError("stk_limit must publish both upper/lower prices or neither")
            up_limit_cents = _quote_price_cents(
                item.get("up_limit"), field="stk_limit.up_limit", allow_missing=True,
            )
            down_limit_cents = _quote_price_cents(
                item.get("down_limit"), field="stk_limit.down_limit", allow_missing=True,
            )
            if up_limit_cents is not None and not (
                up_limit_cents >= pre_close_cents >= down_limit_cents
            ):
                raise SpineError("stk_limit upper/pre-close/lower ordering is inconsistent")
            for column, cents in (
                ("pre_close", pre_close_cents),
                ("up_limit", up_limit_cents),
                ("down_limit", down_limit_cents),
            ):
                row[f"{column}_cents"] = cents
                row[column] = (
                    float(Decimal(cents) / A_SHARE_PRICE_SCALE)
                    if cents is not None else None
                )
            row["source_limits_present"] = bool(up_limit_cents is not None)
            row["limit_price_source"] = "tushare.stk_limit_exact_daily"
            row["quote_tick_cny"] = float(A_SHARE_PRICE_TICK)
        elif endpoint == "suspend_d":
            raw_timing = item.get("suspend_timing")
            row["suspend_timing"] = (
                "" if raw_timing is None or pd.isna(raw_timing) else str(raw_timing)
            )
            raw_suspend_type = item.get("suspend_type")
            row["suspend_type"] = (
                "" if raw_suspend_type is None or pd.isna(raw_suspend_type)
                else str(raw_suspend_type).upper()
            )
            if row["suspend_type"] not in {"S", "R"}:
                raise SpineError(f"suspend_d returned invalid suspend_type: {row['suspend_type']!r}")
        elif endpoint == "stock_st":
            row["name"] = str(item.get("name") or "")
            row["st_type"] = str(item.get("type") or "")
            row["st_type_name"] = str(item.get("type_name") or "")
            row["is_st"] = True
            row["st_provenance"] = "tushare.stock_st_exact_daily"
        rows.append(row)
    out = pd.DataFrame(rows)
    if not out.empty and _duplicates(out, KEY_COLUMNS[endpoint]):
        raise SpineError(f"{endpoint} response duplicated canonical A-share keys")
    if not out.empty:
        out = out.sort_values(KEY_COLUMNS[endpoint], kind="stable").reset_index(drop=True)
    return out, dropped


def _monthly_partition(store: Path, endpoint: str, trade_date: date) -> Path:
    return store / endpoint / f"year={trade_date.year:04d}" / f"month={trade_date.month:02d}" / "part.parquet"


def _name_partition(store: Path, year: int) -> Path:
    return store / "name_history" / f"year={year:04d}.parquet"


def _calendar_partition(store: Path, year: int) -> Path:
    return store / "reference" / "trade_calendar" / f"year={year:04d}.parquet"


def _year_segments(start: date, end: date) -> list[tuple[int, date, date]]:
    return [
        (year, max(start, date(year, 1, 1)), min(end, date(year, 12, 31)))
        for year in range(start.year, end.year + 1)
    ]


class TushareAShareSpineCollector:
    """Bounded request orchestrator.  Network behavior is injectable for tests."""

    def __init__(
        self,
        store: Path = DEFAULT_STORE,
        *,
        query: Callable[..., pd.DataFrame | None] | None = None,
        now: Callable[[], datetime] = _utc_now,
        max_requests: int = DEFAULT_MAX_REQUESTS,
    ) -> None:
        self.store = Path(store)
        self.query = query or tc.query
        self.now = now
        self.max_requests = int(max_requests)
        self.requests_made = 0
        self.failures: list[dict[str, str]] = []
        self.state = load_state(self.store)

    @property
    def observed_at(self) -> str:
        return self.now().astimezone(timezone.utc).isoformat()

    def _call(self, endpoint: str, **params: Any) -> pd.DataFrame | None:
        if self.max_requests and self.requests_made >= self.max_requests:
            raise RequestBudgetExhausted("request cap reached; state is resumable")
        self.requests_made += 1
        # _return_empty distinguishes an authenticated zero-row event day from
        # an unavailable/failed call while preserving query()'s legacy default.
        return self.query(endpoint, fields=ENDPOINT_FIELDS[endpoint], _return_empty=True, **params)

    def _mark_failed(self, endpoint: str, unit: str, reason: str) -> None:
        self.failures.append({"endpoint": endpoint, "unit": unit, "reason": reason})
        _set_unit(
            self.state, self.store, endpoint, unit, status="failed",
            observed_at=self.observed_at, reason=reason,
        )

    def collect_reference(self, *, refresh: bool = False) -> bool:
        mapping_path = self.store / "reference" / "source_bse_mapping.parquet"
        mapping_unit = "all"
        if refresh or not _unit_done(self.state, self.store, "bse_mapping", mapping_unit):
            frame = self._call("bse_mapping")
            if frame is None:
                self._mark_failed("bse_mapping", mapping_unit, "vendor_unavailable_or_unlicensed")
                return False
            if len(frame) >= SOURCE_ROW_CAPS["bse_mapping"]:
                self._mark_failed("bse_mapping", mapping_unit, "documented_source_row_cap_reached")
                return False
            normal = _normalise_bse_mapping(frame)
            if normal.empty:
                self._mark_failed("bse_mapping", mapping_unit, "unexpected_empty_bse_identity_mapping")
                return False
            _atomic_parquet(mapping_path, normal)
            _set_unit(
                self.state, self.store, "bse_mapping", mapping_unit,
                status="empty" if normal.empty else "complete", observed_at=self.observed_at,
                row_count=len(normal), source_row_count=len(frame), partition=mapping_path,
            )
        for exchange in EXCHANGES:
            for status in LIST_STATUSES:
                unit = f"{exchange}:{status}"
                path = self.store / "reference" / "source_stock_basic" / f"{exchange}_{status}.parquet"
                if not refresh and _unit_done(self.state, self.store, "stock_basic", unit):
                    continue
                frame = self._call("stock_basic", exchange=exchange, list_status=status)
                if frame is None:
                    self._mark_failed("stock_basic", unit, "vendor_unavailable_or_unlicensed")
                    continue
                if len(frame) >= SOURCE_ROW_CAPS["stock_basic"]:
                    self._mark_failed("stock_basic", unit, "documented_source_row_cap_reached")
                    continue
                normal = frame.copy()
                if status == "L" and normal.empty:
                    self._mark_failed("stock_basic", unit, "unexpected_empty_listed_exchange")
                    continue
                if "exchange" not in normal.columns:
                    normal["exchange"] = exchange
                if "list_status" not in normal.columns:
                    normal["list_status"] = status
                _atomic_parquet(path, normal)
                _set_unit(
                    self.state, self.store, "stock_basic", unit,
                    status="empty" if normal.empty else "complete", observed_at=self.observed_at,
                    row_count=len(normal), source_row_count=len(frame), partition=path,
                )
        ready = all(
            _unit_done(self.state, self.store, "stock_basic", f"{exchange}:{status}")
            for exchange in EXCHANGES for status in LIST_STATUSES
        ) and _unit_done(self.state, self.store, "bse_mapping", mapping_unit)
        if ready:
            compile_security_master(self.store)
        return ready

    def collect_calendars(self, start: date, end: date) -> bool:
        for year, segment_start, segment_end in _year_segments(start, end):
            for exchange in CALENDAR_EXCHANGES:
                unit = f"{exchange}:{_compact(segment_start)}:{_compact(segment_end)}"
                if _unit_done(self.state, self.store, "trade_cal", unit):
                    continue
                frame = self._call(
                    "trade_cal", exchange=exchange, start_date=_compact(segment_start),
                    end_date=_compact(segment_end),
                )
                if frame is None:
                    self._mark_failed("trade_cal", unit, "vendor_unavailable_or_unlicensed")
                    continue
                try:
                    normal = _normalise_calendar(frame, exchange, segment_start, segment_end)
                except SpineError:
                    self._mark_failed("trade_cal", unit, "calendar_contract_failed")
                    raise
                path = _calendar_partition(self.store, year)
                rows, revised = _upsert_partition(
                    path, normal, keys=KEY_COLUMNS["trade_calendar"],
                )
                _set_unit(
                    self.state, self.store, "trade_cal", unit, status="complete",
                    observed_at=self.observed_at, row_count=len(normal), source_row_count=len(frame),
                    revised_key_count=revised, partition=path,
                )
                log.debug("trade_cal %s landed (%d partition rows)", unit, rows)
        ready = all(
            _unit_done(
                self.state, self.store, "trade_cal",
                f"{exchange}:{_compact(segment_start)}:{_compact(segment_end)}",
            )
            for _, segment_start, segment_end in _year_segments(start, end)
            for exchange in CALENDAR_EXCHANGES
        )
        if ready:
            compile_market_sessions(self.store, start, end)
        return ready

    def collect_name_history(self, end: date) -> None:
        years = list(range(NAME_HISTORY_START_YEAR, end.year + 1))
        years.sort(key=lambda year: (
            1 if _unit_record(self.state, "namechange", str(year)) else 0,
            year,
        ))
        attempted = 0
        for year in years:
            unit = str(year)
            if _unit_done(self.state, self.store, "namechange", unit):
                continue
            if attempted >= NAMECHANGE_MAX_PER_RUN:
                break
            attempted += 1
            frame = self._call(
                "namechange", start_date=f"{year:04d}0101", end_date=f"{year:04d}1231",
            )
            if frame is None:
                self._mark_failed("namechange", unit, "vendor_unavailable_or_unlicensed")
                continue
            if len(frame) >= 6000:
                self._mark_failed("namechange", unit, "possible_undocumented_source_row_cap")
                continue
            normal, orphans = normalise_name_history(frame, self.store)
            path = _name_partition(self.store, year)
            if normal.empty:
                _set_unit(
                    self.state, self.store, "namechange", unit, status="empty",
                    observed_at=self.observed_at, source_row_count=len(frame),
                )
                continue
            rows, revised = _upsert_partition(path, normal, keys=KEY_COLUMNS["name_history"])
            _set_unit(
                self.state, self.store, "namechange", unit, status="complete",
                observed_at=self.observed_at, row_count=len(normal), source_row_count=len(frame),
                unmatched_master_row_count=orphans, revised_key_count=revised, partition=path,
            )
            log.debug("namechange %d landed (%d partition rows)", year, rows)

    def collect_daily(self, start: date, end: date, endpoints: Sequence[str]) -> None:
        session_path = self.store / "reference" / "market_sessions.parquet"
        sessions = _read_parquet_strict(session_path)
        sessions = sessions[
            (sessions["trade_date"].astype(str) >= start.isoformat())
            & (sessions["trade_date"].astype(str) <= end.isoformat())
        ]
        dates = [_parse_date(value) for value in sorted(sessions["trade_date"], reverse=True)]
        # Unattempted units first; prior failures are retried only after new work,
        # preventing a historical entitlement gap from starving the rest of the tape.
        work: list[tuple[int, date, str]] = []
        for trade_date in dates:
            for endpoint in endpoints:
                if endpoint == "stock_st" and trade_date < ST_DAILY_START:
                    continue
                unit = _compact(trade_date)
                if _unit_done(self.state, self.store, endpoint, unit):
                    continue
                priority = 1 if _unit_record(self.state, endpoint, unit) else 0
                work.append((priority, trade_date, endpoint))
        work.sort(key=lambda item: (item[0], -item[1].toordinal(), endpoints.index(item[2])))
        for _, trade_date, endpoint in work:
            unit = _compact(trade_date)
            frame = self._call(endpoint, trade_date=unit)
            if frame is None:
                self._mark_failed(endpoint, unit, "vendor_unavailable_or_unlicensed")
                continue
            cap = SOURCE_ROW_CAPS.get(endpoint)
            if cap is not None and len(frame) >= cap:
                self._mark_failed(endpoint, unit, "documented_source_row_cap_reached")
                continue
            if frame.empty:
                if endpoint not in EMPTY_ALLOWED_ENDPOINTS:
                    self._mark_failed(endpoint, unit, "unexpected_empty_open_session")
                    continue
                path = _monthly_partition(self.store, endpoint, trade_date)
                _replace_partition_units(
                    path,
                    pd.DataFrame(),
                    keys=KEY_COLUMNS[endpoint],
                    unit_column="trade_date",
                    units=[trade_date.isoformat()],
                )
                _set_unit(
                    self.state, self.store, endpoint, unit, status="empty",
                    observed_at=self.observed_at, source_row_count=0,
                )
                continue
            try:
                normal, dropped = normalise_daily_endpoint(endpoint, frame, trade_date, self.store)
            except SpineError:
                self._mark_failed(endpoint, unit, "daily_contract_failed")
                raise
            if normal.empty and endpoint in DENSE_ENDPOINTS:
                self._mark_failed(endpoint, unit, "no_A_share_rows_after_identity_filter")
                continue
            path = _monthly_partition(self.store, endpoint, trade_date)
            rows, revised = _replace_partition_units(
                path,
                normal,
                keys=KEY_COLUMNS[endpoint],
                unit_column="trade_date",
                units=[trade_date.isoformat()],
            )
            _set_unit(
                self.state, self.store, endpoint, unit,
                status="empty" if normal.empty else "complete", observed_at=self.observed_at,
                row_count=len(normal), source_row_count=len(frame), dropped_row_count=dropped,
                revised_key_count=revised, partition=path if not normal.empty else None,
            )
            log.debug("%s %s landed (%d partition rows)", endpoint, unit, rows)


def _expected_endpoint_units(
    store: Path, start: date, end: date, endpoint: str,
) -> list[str]:
    sessions_path = store / "reference" / "market_sessions.parquet"
    if not sessions_path.exists():
        return []
    sessions = _read_parquet_strict(sessions_path)
    dates = [
        _parse_date(value) for value in sessions["trade_date"].astype(str)
        if start <= _parse_date(value) <= end
    ]
    if endpoint == "stock_st":
        dates = [value for value in dates if value >= ST_DAILY_START]
    return [_compact(value) for value in sorted(dates)]


def _frame_semantic_sha256(frame: pd.DataFrame, keys: Sequence[str]) -> str:
    if frame.empty:
        return hashlib.sha256(b"").hexdigest()
    ordered = frame.sort_values(list(keys), kind="stable", na_position="last")
    hasher = hashlib.sha256()
    for row in ordered.to_dict(orient="records"):
        safe = {str(key): _json_safe(value) for key, value in sorted(row.items())}
        hasher.update(_canonical_json_bytes(safe))
        hasher.update(b"\n")
    return hasher.hexdigest()


def _partition_receipts(store: Path, endpoint: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    total_rows = 0
    duplicate_rows = 0
    min_date: str | None = None
    max_date: str | None = None
    positive_volume_rows = 0
    keys = KEY_COLUMNS[endpoint]
    hasher = hashlib.sha256()
    for path in sorted((store / endpoint).glob("year=*/month=*/part.parquet")):
        raw = _receipt_bytes(path, store)
        frame = _read_parquet_strict(path)
        duplicates = _duplicates(frame, keys)
        duplicate_rows += duplicates
        dates = frame["trade_date"].astype(str) if "trade_date" in frame.columns else pd.Series(dtype=str)
        part_min = dates.min() if not dates.empty else None
        part_max = dates.max() if not dates.empty else None
        min_date = min(filter(None, [min_date, part_min]), default=None)
        max_date = max(filter(None, [max_date, part_max]), default=None)
        semantic = _frame_semantic_sha256(frame, keys)
        hasher.update(path.relative_to(store).as_posix().encode("utf-8"))
        hasher.update(semantic.encode("ascii"))
        total_rows += len(frame)
        if endpoint == "daily" and "positive_volume" in frame.columns:
            positive_volume_rows += int(frame["positive_volume"].fillna(False).astype(bool).sum())
        receipts.append({
            "path": path.relative_to(store).as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "semantic_sha256": semantic,
            "bytes": path.stat().st_size,
            "rows": len(frame),
            "duplicate_key_rows": duplicates,
            "min_date": part_min,
            "max_date": part_max,
        })
    return receipts, {
        "row_count": total_rows,
        "duplicate_key_rows": duplicate_rows,
        "min_date": min_date,
        "max_date": max_date,
        "positive_volume_rows": positive_volume_rows if endpoint == "daily" else None,
        "semantic_sha256": hasher.hexdigest(),
    }


def _dense_key_coverage_vs_daily(
    store: Path, endpoint: str, start: date, end: date,
) -> dict[str, Any]:
    expected_count = 0
    covered_count = 0
    extra_count = 0
    missing_sample: list[str] = []
    for daily_path in sorted((store / "daily").glob("year=*/month=*/part.parquet")):
        daily = _read_parquet_strict(daily_path)
        if daily.empty:
            continue
        daily = daily[
            (daily["trade_date"].astype(str) >= start.isoformat())
            & (daily["trade_date"].astype(str) <= end.isoformat())
        ]
        if daily.empty:
            continue
        relative = daily_path.relative_to(store / "daily")
        endpoint_path = store / endpoint / relative
        observed = _read_parquet_strict(endpoint_path) if endpoint_path.exists() else pd.DataFrame()
        if not observed.empty:
            observed = observed[
                (observed["trade_date"].astype(str) >= start.isoformat())
                & (observed["trade_date"].astype(str) <= end.isoformat())
            ]
        expected_keys = set(zip(daily["trade_date"].astype(str), daily["ticker"].astype(str)))
        observed_keys = (
            set(zip(observed["trade_date"].astype(str), observed["ticker"].astype(str)))
            if not observed.empty else set()
        )
        missing = sorted(expected_keys - observed_keys)
        expected_count += len(expected_keys)
        covered_count += len(expected_keys & observed_keys)
        extra_count += len(observed_keys - expected_keys)
        for trade_date, ticker in missing:
            if len(missing_sample) >= 20:
                break
            missing_sample.append(f"{trade_date}:{ticker}")
    return {
        "daily_keys": expected_count,
        "covered_daily_keys": covered_count,
        "missing_daily_keys": expected_count - covered_count,
        "extra_non_daily_keys": extra_count,
        "coverage_pct": round(100.0 * covered_count / expected_count, 6)
        if expected_count else 0.0,
        "missing_sample": missing_sample,
        "complete": bool(expected_count and expected_count == covered_count),
    }


def build_canonical_event_substrate(
    store: Path,
    start: date,
    end: date,
) -> dict[str, Any]:
    """Materialise event-ready nominal quotes joined to exact vendor limits.

    ``daily`` is the unadjusted quote/volume plane and ``stk_limit`` is the
    authoritative daily upper/lower-limit plane.  Integer cents are canonical;
    calculated half-up bounds are intentionally *not* substituted for vendor
    limits.  A cross-source previous-close mismatch fails closed.
    """
    output_receipts: list[dict[str, Any]] = []
    event_rows = 0
    positive_volume_rows = 0
    bounded_rows = 0
    no_published_limit_rows = 0
    for daily_path in sorted((store / "daily").glob("year=*/month=*/part.parquet")):
        daily = _read_parquet_strict(daily_path)
        if daily.empty:
            continue
        in_range = (
            (daily["trade_date"].astype(str) >= start.isoformat())
            & (daily["trade_date"].astype(str) <= end.isoformat())
        )
        if not in_range.any():
            continue
        daily = daily[in_range].copy()
        relative = daily_path.relative_to(store / "daily")
        limit_path = store / "stk_limit" / relative
        if not limit_path.exists():
            raise SpineError(f"canonical event substrate lacks stk_limit partition: {relative}")
        limits = _read_parquet_strict(limit_path)
        if _duplicates(daily, KEY_COLUMNS["daily"]):
            raise SpineError(f"daily partition duplicates canonical event keys: {relative}")
        if _duplicates(limits, KEY_COLUMNS["stk_limit"]):
            raise SpineError(f"stk_limit partition duplicates canonical event keys: {relative}")
        limits = limits[
            (limits["trade_date"].astype(str) >= start.isoformat())
            & (limits["trade_date"].astype(str) <= end.isoformat())
        ].copy()

        daily_columns = [
            "security_id", "ticker", "source_ts_code", "exchange", "board",
            "trade_date", "market_session_position", "open", "high", "low",
            "close", "pre_close", "open_cents", "high_cents", "low_cents",
            "close_cents", "pre_close_cents", "volume_lots",
            "amount_cny_thousands", "positive_volume", "price_source_basis",
        ]
        limit_columns = [
            "trade_date", "ticker", "pre_close_cents", "up_limit", "down_limit",
            "up_limit_cents", "down_limit_cents", "source_limits_present",
            "limit_price_source",
        ]
        missing_daily = sorted(set(daily_columns) - set(daily.columns))
        missing_limits = sorted(set(limit_columns) - set(limits.columns))
        if missing_daily or missing_limits:
            raise SpineError(
                "canonical event source columns missing: "
                f"daily={missing_daily}, stk_limit={missing_limits}"
            )
        expected = daily[daily_columns].copy()
        source_limits = limits[limit_columns].copy().rename(
            columns={"pre_close_cents": "limit_pre_close_cents"},
        )
        merged = expected.merge(
            source_limits, on=["trade_date", "ticker"], how="left", validate="one_to_one",
            indicator=True,
        )
        absent = merged[merged["_merge"] != "both"]
        if not absent.empty:
            sample = absent[["trade_date", "ticker"]].head(20).to_dict(orient="records")
            raise SpineError(f"daily keys absent from exact stk_limit source: {sample}")
        merged = merged.drop(columns="_merge")

        compared = merged[
            merged["pre_close_cents"].notna() & merged["limit_pre_close_cents"].notna()
        ]
        mismatch = compared[
            compared["pre_close_cents"].astype("int64")
            != compared["limit_pre_close_cents"].astype("int64")
        ]
        if not mismatch.empty:
            sample = mismatch[[
                "trade_date", "ticker", "pre_close_cents", "limit_pre_close_cents",
            ]].head(20).to_dict(orient="records")
            raise SpineError(f"daily/stk_limit previous-close mismatch: {sample}")

        merged["event_eligible"] = (
            merged["positive_volume"].fillna(False).astype(bool)
            & merged["source_limits_present"].fillna(False).astype(bool)
        )
        bounded = merged["source_limits_present"].fillna(False).astype(bool)
        merged["touched_up"] = (
            merged["event_eligible"]
            & merged["high_cents"].ge(merged["up_limit_cents"])
        )
        merged["sealed_up"] = (
            merged["event_eligible"]
            & merged["close_cents"].ge(merged["up_limit_cents"])
        )
        merged["touched_down"] = (
            merged["event_eligible"]
            & merged["low_cents"].le(merged["down_limit_cents"])
        )
        merged["sealed_down"] = (
            merged["event_eligible"]
            & merged["close_cents"].le(merged["down_limit_cents"])
        )
        merged["event_price_authority"] = (
            "tushare.daily_unadjusted_plus_stk_limit_exact_daily"
        )
        merged["calculated_limit_role"] = "validator_only_never_event_authority"
        merged["quote_tick_cny"] = float(A_SHARE_PRICE_TICK)
        merged = merged.sort_values(KEY_COLUMNS["event_daily"], kind="stable").reset_index(drop=True)

        output_path = store / "event_daily" / relative
        _replace_partition_units(
            output_path,
            merged,
            keys=KEY_COLUMNS["event_daily"],
            unit_column="trade_date",
            units=set(merged["trade_date"].astype(str)),
        )
        receipt = _file_receipt(output_path, store, KEY_COLUMNS["event_daily"])
        assert receipt is not None
        output_receipts.append(receipt)
        event_rows += len(merged)
        positive_volume_rows += int(merged["positive_volume"].fillna(False).astype(bool).sum())
        bounded_rows += int(bounded.sum())
        no_published_limit_rows += int((~bounded).sum())

    return {
        "ready": bool(output_receipts and event_rows),
        "row_count": event_rows,
        "positive_volume_rows": positive_volume_rows,
        "source_limit_rows": bounded_rows,
        "no_published_limit_rows": no_published_limit_rows,
        "daily_source": "tushare.daily_unadjusted_nominal",
        "limit_source": "tushare.stk_limit_exact_daily",
        "integer_price_unit": "CNY_cents",
        "calculated_limit_role": "validator_only_never_event_authority",
        "partitions": output_receipts,
    }


def _eligible_tickers(master: pd.DataFrame, trade_date: str) -> set[str]:
    eligible = master[master["effective_from"].notna()].copy()
    eligible = eligible[eligible["effective_from"].astype(str) <= trade_date]
    eligible = eligible[
        eligible["effective_to"].isna() | (eligible["effective_to"].astype(str) >= trade_date)
    ]
    return set(eligible["ticker"].astype(str))


def build_daily_security_coverage(
    store: Path,
    start: date,
    end: date,
    state: Mapping[str, Any],
) -> pd.DataFrame:
    """Per-session lifecycle-vs-daily coverage, without loading the full tape at once."""
    master_path = store / "reference" / "security_master.parquet"
    session_path = store / "reference" / "market_sessions.parquet"
    columns = [
        "trade_date", "eligible_n", "daily_n", "positive_volume_n", "suspended_n",
        "unexplained_missing_n", "unexpected_daily_n", "suspension_state_known",
    ]
    if not master_path.exists() or not session_path.exists():
        return pd.DataFrame(columns=columns)
    master = _read_parquet_strict(master_path)
    sessions = _read_parquet_strict(session_path)
    requested = [
        value for value in sessions["trade_date"].astype(str)
        if start.isoformat() <= value <= end.isoformat()
    ]
    rows: list[dict[str, Any]] = []
    by_month: dict[str, list[str]] = {}
    for trade_date in requested:
        by_month.setdefault(trade_date[:7], []).append(trade_date)
    for month, trade_dates in sorted(by_month.items()):
        year, month_number = map(int, month.split("-"))
        daily_path = store / "daily" / f"year={year:04d}" / f"month={month_number:02d}" / "part.parquet"
        suspend_path = store / "suspend_d" / f"year={year:04d}" / f"month={month_number:02d}" / "part.parquet"
        daily = _read_parquet_strict(daily_path) if daily_path.exists() else pd.DataFrame()
        suspend = _read_parquet_strict(suspend_path) if suspend_path.exists() else pd.DataFrame()
        for trade_date in trade_dates:
            unit = trade_date.replace("-", "")
            if not _unit_done(state, store, "daily", unit):
                continue
            daily_day = daily[daily["trade_date"].astype(str) == trade_date] if not daily.empty else daily
            actual = set(daily_day.get("ticker", pd.Series(dtype=str)).astype(str))
            positive = set(daily_day.loc[
                daily_day.get("positive_volume", pd.Series(False, index=daily_day.index)).fillna(False).astype(bool),
                "ticker",
            ].astype(str)) if not daily_day.empty else set()
            suspension_known = _unit_done(state, store, "suspend_d", unit)
            if suspension_known and not suspend.empty:
                suspend_day = suspend[
                    (suspend["trade_date"].astype(str) == trade_date)
                    & (suspend["suspend_type"].astype(str) == "S")
                    & (suspend["suspend_timing"].fillna("").astype(str) == "")
                ]
                suspended = set(suspend_day["ticker"].astype(str))
            else:
                suspended = set()
            eligible = _eligible_tickers(master, trade_date)
            missing = eligible - actual
            unexplained = missing - suspended if suspension_known else missing
            rows.append({
                "trade_date": trade_date,
                "eligible_n": len(eligible),
                "daily_n": len(actual),
                "positive_volume_n": len(positive),
                "suspended_n": len(suspended),
                "unexplained_missing_n": len(unexplained),
                "unexpected_daily_n": len(actual - eligible),
                "suspension_state_known": bool(suspension_known),
            })
    coverage = pd.DataFrame(rows, columns=columns)
    if not coverage.empty:
        coverage = coverage.sort_values("trade_date", kind="stable").reset_index(drop=True)
        _atomic_parquet(store / "coverage" / "daily_security_coverage.parquet", coverage)
    return coverage


def _file_receipt(path: Path, store: Path, keys: Sequence[str]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    raw = _receipt_bytes(path, store)
    frame = _read_parquet_strict(path)
    return {
        "path": path.relative_to(store).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "semantic_sha256": _frame_semantic_sha256(frame, keys),
        "bytes": path.stat().st_size,
        "rows": len(frame),
        "duplicate_key_rows": _duplicates(frame, keys),
    }


def _json_file_receipt(path: Path, store: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    raw = _receipt_bytes(path, store)
    return {
        "path": path.relative_to(store).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _state_unit_summary(
    state: Mapping[str, Any], endpoint: str, expected: Sequence[str],
) -> dict[str, Any]:
    records = {unit: _unit_record(state, endpoint, unit) for unit in expected}
    complete = [unit for unit, record in records.items() if record and record.get("status") == "complete"]
    empty = [unit for unit, record in records.items() if record and record.get("status") == "empty"]
    failed = [unit for unit, record in records.items() if record and record.get("status") == "failed"]
    pending = sorted(set(expected) - set(complete) - set(empty))
    return {
        "expected_units": len(expected),
        "complete_units": len(complete),
        "empty_units": len(empty),
        "failed_units": len(failed),
        "pending_units": len(pending),
        "complete": len(complete) + len(empty) == len(expected),
        "failed_or_pending_sample": pending[:20],
        "unmatched_master_row_count": sum(
            int(record.get("unmatched_master_row_count", 0))
            for record in records.values() if record
        ),
    }


def _name_history_receipts(store: Path) -> tuple[list[dict[str, Any]], int, str]:
    receipts: list[dict[str, Any]] = []
    total_rows = 0
    hasher = hashlib.sha256()
    for path in sorted((store / "name_history").glob("year=*.parquet")):
        receipt = _file_receipt(path, store, KEY_COLUMNS["name_history"])
        assert receipt is not None
        receipts.append(receipt)
        total_rows += int(receipt["rows"])
        hasher.update(receipt["path"].encode("utf-8"))
        hasher.update(receipt["semantic_sha256"].encode("ascii"))
    return receipts, total_rows, hasher.hexdigest()


def _reference_source_receipts(store: Path) -> list[dict[str, Any]]:
    """Hash every landed raw reference artifact before derived compilation."""
    receipts: list[dict[str, Any]] = []
    bse = _file_receipt(
        store / "reference" / "source_bse_mapping.parquet",
        store,
        ["o_code", "n_code"],
    )
    if bse is not None:
        receipts.append(bse)
    for path in sorted((store / "reference" / "source_stock_basic").glob("*.parquet")):
        receipt = _file_receipt(path, store, ["ts_code"])
        assert receipt is not None
        receipts.append(receipt)
    for path in sorted((store / "reference" / "trade_calendar").glob("year=*.parquet")):
        receipt = _file_receipt(path, store, KEY_COLUMNS["trade_calendar"])
        assert receipt is not None
        receipts.append(receipt)
    return receipts


def build_completeness_manifest(
    store: Path,
    start: date,
    end: date,
    endpoints: Sequence[str],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build and atomically publish the completeness/ore receipt."""
    state = load_state(store)
    manifest_endpoints = tuple(dict.fromkeys((*DEFAULT_ENDPOINTS, *endpoints)))
    generated_at = generated_at or _utc_now().isoformat()
    master_path = store / "reference" / "security_master.parquet"
    aliases_path = store / "reference" / "identity_aliases.parquet"
    sessions_path = store / "reference" / "market_sessions.parquet"
    master = _read_parquet_strict(master_path) if master_path.exists() else pd.DataFrame()
    aliases = _read_parquet_strict(aliases_path) if aliases_path.exists() else pd.DataFrame()
    sessions = _read_parquet_strict(sessions_path) if sessions_path.exists() else pd.DataFrame()
    stock_basic_units = [f"{exchange}:{status}" for exchange in EXCHANGES for status in LIST_STATUSES]
    calendar_units = [
        f"{exchange}:{_compact(segment_start)}:{_compact(segment_end)}"
        for _, segment_start, segment_end in _year_segments(CALENDAR_HISTORY_START, end)
        for exchange in CALENDAR_EXCHANGES
    ]
    namechange_units = [str(year) for year in range(NAME_HISTORY_START_YEAR, end.year + 1)]
    reference_source_units = {
        "stock_basic": _state_unit_summary(state, "stock_basic", stock_basic_units),
        "bse_mapping": _state_unit_summary(state, "bse_mapping", ["all"]),
        "trade_cal": _state_unit_summary(state, "trade_cal", calendar_units),
        "namechange": _state_unit_summary(state, "namechange", namechange_units),
    }
    reference_source_artifacts = _reference_source_receipts(store)
    reference_ready = bool(
        not master.empty
        and not aliases.empty
        and sessions_path.exists()
        and all(summary["complete"] for summary in reference_source_units.values())
        and all(receipt["duplicate_key_rows"] == 0 for receipt in reference_source_artifacts)
    )

    endpoint_receipts: dict[str, Any] = {}
    endpoints_complete = True
    for endpoint in manifest_endpoints:
        expected = _expected_endpoint_units(store, start, end, endpoint)
        records = {unit: _unit_record(state, endpoint, unit) for unit in expected}
        complete = sorted(unit for unit, record in records.items() if record and record.get("status") == "complete")
        empty = sorted(unit for unit, record in records.items() if record and record.get("status") == "empty")
        failed = sorted(unit for unit, record in records.items() if record and record.get("status") == "failed")
        pending = sorted(set(expected) - set(complete) - set(empty))
        partitions, totals = _partition_receipts(store, endpoint)
        daily_key_coverage = (
            _dense_key_coverage_vs_daily(store, endpoint, start, end)
            if endpoint in {"daily_basic", "stk_limit"} else None
        )
        not_applicable = endpoint == "stock_st" and not expected and end < ST_DAILY_START
        endpoint_complete = (
            (not_applicable or (bool(expected) and not pending))
            and totals["duplicate_key_rows"] == 0
            and (daily_key_coverage is None or daily_key_coverage["complete"])
        )
        endpoints_complete = endpoints_complete and endpoint_complete
        endpoint_receipts[endpoint] = {
            "required": True,
            "not_applicable": not_applicable,
            "expected_session_units": len(expected),
            "complete_units": len(complete),
            "empty_units": len(empty),
            "failed_units": len(failed),
            "pending_units": len(pending),
            "coverage_pct": round(100.0 * (len(complete) + len(empty)) / len(expected), 6)
            if expected else (100.0 if not_applicable else 0.0),
            "complete": endpoint_complete,
            "failed_or_pending_sample": pending[:20],
            "daily_key_coverage": daily_key_coverage,
            "partitions": partitions,
            **totals,
        }

    event_sources_ready = all(
        endpoint in endpoint_receipts and endpoint_receipts[endpoint]["complete"]
        for endpoint in ("daily", "stk_limit")
    )
    canonical_event_substrate = (
        build_canonical_event_substrate(store, start, end)
        if event_sources_ready else {
            "ready": False,
            "row_count": 0,
            "positive_volume_rows": 0,
            "source_limit_rows": 0,
            "no_published_limit_rows": 0,
            "daily_source": "tushare.daily_unadjusted_nominal",
            "limit_source": "tushare.stk_limit_exact_daily",
            "integer_price_unit": "CNY_cents",
            "calculated_limit_role": "validator_only_never_event_authority",
            "partitions": [],
        }
    )

    coverage = build_daily_security_coverage(store, start, end, state)
    coverage_receipt: dict[str, Any] = {
        "completed_session_rows": len(coverage),
        "sessions_with_known_suspensions": int(coverage.get(
            "suspension_state_known", pd.Series(dtype=bool)
        ).fillna(False).astype(bool).sum()),
        "eligible_security_observations": int(coverage.get("eligible_n", pd.Series(dtype=int)).sum()),
        "daily_security_observations": int(coverage.get("daily_n", pd.Series(dtype=int)).sum()),
        "positive_volume_observations": int(coverage.get("positive_volume_n", pd.Series(dtype=int)).sum()),
        "unexplained_missing_observations": int(coverage.get(
            "unexplained_missing_n", pd.Series(dtype=int)
        ).sum()),
        "unexpected_daily_observations": int(coverage.get(
            "unexpected_daily_n", pd.Series(dtype=int)
        ).sum()),
    }
    coverage_receipt["complete"] = bool(
        len(coverage)
        and coverage_receipt["sessions_with_known_suspensions"] == len(coverage)
        and coverage_receipt["unexplained_missing_observations"] == 0
        and coverage_receipt["unexpected_daily_observations"] == 0
    )
    if not coverage.empty:
        worst = coverage.sort_values(
            ["unexplained_missing_n", "unexpected_daily_n", "trade_date"],
            ascending=[False, False, True], kind="stable",
        ).head(10)
        coverage_receipt["worst_session_sample"] = [
            {key: _json_safe(value) for key, value in row.items()}
            for row in worst.to_dict(orient="records")
        ]
    else:
        coverage_receipt["worst_session_sample"] = []

    security_receipt = _file_receipt(master_path, store, ["ticker"])
    alias_receipt = _file_receipt(aliases_path, store, ["alias_ticker", "alias_kind"])
    session_receipt = _file_receipt(sessions_path, store, ["trade_date"])
    name_history_partitions, name_history_rows, name_history_semantic = _name_history_receipts(store)
    state_receipt = _json_file_receipt(store / "collection_state.json", store)
    exchange_counts = (
        {str(k): int(v) for k, v in master["exchange"].value_counts().sort_index().items()}
        if not master.empty else {}
    )
    board_counts = (
        {str(k): int(v) for k, v in master["board"].value_counts().sort_index().items()}
        if not master.empty else {}
    )
    requested_sessions = 0
    if not sessions.empty:
        requested_sessions = int((
            (sessions["trade_date"].astype(str) >= start.isoformat())
            & (sessions["trade_date"].astype(str) <= end.isoformat())
        ).sum())

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": generated_at,
        "authority": AUTHORITY,
        "source": SOURCE_NAME,
        "collection_state": state_receipt,
        "requested_range": {"start": start.isoformat(), "end": end.isoformat()},
        "complete": bool(
            reference_ready
            and endpoints_complete
            and coverage_receipt["complete"]
            and canonical_event_substrate["ready"]
        ),
        "reference": {
            "ready": reference_ready,
            "security_master": security_receipt,
            "identity_aliases": alias_receipt,
            "market_sessions": session_receipt,
            "security_count": len(master),
            "identity_alias_count": len(aliases),
            "requested_market_sessions": requested_sessions,
            "exchange_counts": exchange_counts,
            "board_counts": board_counts,
            "missing_effective_from_count": int(master.get(
                "effective_from", pd.Series(dtype=object)
            ).isna().sum()) if not master.empty else 0,
            "source_units": reference_source_units,
            "source_artifacts": reference_source_artifacts,
            "name_history_partitions": name_history_partitions,
            "name_history_row_count": name_history_rows,
            "name_history_semantic_sha256": name_history_semantic,
        },
        "endpoints": endpoint_receipts,
        "canonical_event_substrate": canonical_event_substrate,
        "daily_security_coverage": coverage_receipt,
        "contracts": {
            "identity": {
                "repo_ticker_suffixes": {"SSE": ".SS", "SZSE": ".SZ", "BSE": ".BJ"},
                "security_id_format": "CN-{MIC}-{six_digit_code}",
                "bse_alias_policy": "old .BJ codes map to TuShare bse_mapping n_code (920xxx)",
            },
            "exact_session": {
                "rule": "SSE open-session set must equal SZSE open-session set",
                "bse_provenance": "derived_from_attested_SSE_SZSE_consensus_from_2021-11-15",
                "row_field": "market_session_position",
            },
            "positive_volume": {
                "source_field": "daily.vol",
                "stored_field": "volume_lots",
                "unit": "lots (手)",
                "rule": "positive_volume = volume_lots > 0",
                "consumer_law": (
                    "a traded/listing-session claim must filter daily.positive_volume; "
                    "other endpoints must join daily on (trade_date,ticker)"
                ),
            },
            "st": {
                "exact_daily_source": "tushare.stock_st",
                "exact_daily_start": ST_DAILY_START.isoformat(),
                "pre_2016_source": "tushare.namechange name inference",
                "pre_2016_completeness": "partial_not_exact_daily_membership",
            },
            "price_basis": {
                "daily": "unadjusted nominal OHLC; pre_close is ex-rights adjusted vendor field",
                "pro_bar": "not called by this direct-REST collector",
            },
            "price_limit": {
                "event_authority": "tushare.daily unadjusted quotes joined to tushare.stk_limit",
                "quote_tick_cny": str(A_SHARE_PRICE_TICK),
                "canonical_storage": "integer CNY cents",
                "calculated_rounding": "Decimal ROUND_HALF_UP (四舍五入), never round/np.round",
                "minimum_move_rule": "force one quote tick when rounded difference is below one tick",
                "minimum_bound_rule": "a calculated bound below one tick is floored at one tick",
                "calculated_limit_role": "validator_only_never_event_authority",
                "szse_2026_rule": SZSE_2026_TRADING_RULE_URL,
                "sse_2026_rule": SSE_2026_TRADING_RULE_URL,
                "tushare_daily_contract": TUSHARE_DAILY_DOC_URL,
                "tushare_stk_limit_contract": TUSHARE_STK_LIMIT_DOC_URL,
            },
        },
        "data_gaps": [
            "stock_st exact daily history begins 2016-01-01; earlier namechange inference is partial",
            "TuShare trade_cal documentation does not advertise BSE; BSE sessions are derived from SSE=SZSE",
            "a response at a documented row cap is rejected as truncated, not marked complete",
            "endpoint entitlement and sustained live throughput were not exercised in this code-only wave",
            "provider redistribution/retention rights for a bulk cache require operator confirmation",
            "no bitemporal vendor-revision ledger; a same-key re-fetch replaces the local materialization",
            "collection is single-writer; no cross-process or distributed collection lock is implemented",
            "the existing Yahoo raw plane is split-adjusted and is incompatible with exact legal limit history",
        ],
        "ore_ledger": {
            "constructed": [
                "listed+delisted+paused+approved security lifecycle by exchange/status",
                "BSE old-code to canonical 920-code identity aliases",
                "SSE/SZSE exact-calendar consensus with session positions",
                "nominal daily OHLCV plus explicit positive-volume state",
                "daily_basic, stk_limit, suspend_d and stock_st exact-date partitions",
                "effective-dated name/ST-name history",
                "per-session lifecycle/daily/suspension completeness reconciliation",
                "integer-cent nominal event substrate joined to vendor exact daily upper/lower limits",
                "Decimal half-up limit validator with one-tick separation and floor rules",
            ],
            "not_tested": [
                "pro_bar adjusted-price construction",
                "pre-2016 exact daily ST membership",
                "direct BSE trade-calendar endpoint",
                "minute, auction, order-book, seal-time or fillability history",
                "live bulk backfill, provider throughput and purchased-addon entitlement",
                "historical reconciliation of calculated bounds against vendor stk_limit across all rule eras",
            ],
        },
    }
    unsigned_bytes = _canonical_json_bytes(manifest)
    _assert_configured_token_absent(unsigned_bytes, artifact="completeness_manifest(unsigned)")
    manifest["manifest_identity_sha256"] = hashlib.sha256(unsigned_bytes).hexdigest()
    manifest_path = store / "completeness_manifest.json"
    _atomic_json(manifest_path, manifest)
    _receipt_bytes(manifest_path, store)
    return manifest


def collect(
    *,
    start: str | date,
    end: str | date,
    store: Path = DEFAULT_STORE,
    endpoints: Iterable[str] = DEFAULT_ENDPOINTS,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    allow_bulk: bool = False,
    refresh_reference: bool = False,
    dry_run: bool = False,
    query: Callable[..., pd.DataFrame | None] | None = None,
    require_token: bool = True,
    now: Callable[[], datetime] = _utc_now,
) -> dict[str, Any]:
    """Run one bounded/resumable collection wave and publish a manifest.

    A missing token is an honest no-op before any store write.  Tests can inject
    ``query`` and set ``require_token=False``; production callers cannot pass a
    token value through this API.
    """
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if start_date > end_date:
        raise SpineError("start date is after end date")
    selected = tuple(dict.fromkeys(str(value).strip() for value in endpoints if str(value).strip()))
    unknown = sorted(set(selected) - DAILY_ENDPOINTS)
    if unknown:
        raise SpineError(f"unsupported endpoints: {unknown}")
    if max_requests < 0:
        raise SpineError("max_requests must be non-negative")
    if (max_requests == 0 or max_requests > SAFE_MAX_REQUESTS) and not allow_bulk:
        raise SpineError(
            f"max_requests={max_requests} exceeds the {SAFE_MAX_REQUESTS}-call safety ceiling; "
            "pass allow_bulk=True explicitly"
        )
    if dry_run:
        state = load_state(Path(store))
        return {
            "dry_run": True,
            "network_calls": 0,
            "writes": 0,
            "requested_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "endpoints": list(selected),
            "completed_units": sum(
                1 for units in state.get("units", {}).values() for record in units.values()
                if record.get("status") in {"complete", "empty"}
            ),
            "note": "dry-run is network-free; exact pending sessions require a landed calendar",
        }
    if require_token and query is None and not tc.enabled():
        return {
            "dry_run": False,
            "no_op": True,
            "requests_made": 0,
            "error": "TUSHARE_TOKEN is not configured; spine collection made no writes",
        }

    collector = TushareAShareSpineCollector(
        Path(store), query=query, now=now, max_requests=max_requests,
    )
    capped = False
    stage = "reference"
    try:
        reference_ready = collector.collect_reference(refresh=refresh_reference)
        if not reference_ready:
            stage = "reference_incomplete"
        else:
            stage = "calendar"
            calendar_ready = collector.collect_calendars(CALENDAR_HISTORY_START, end_date)
            if not calendar_ready:
                stage = "calendar_incomplete"
            else:
                stage = "name_history"
                collector.collect_name_history(end_date)
                stage = "daily"
                collector.collect_daily(start_date, end_date, selected)
                stage = "complete"
    except RequestBudgetExhausted:
        capped = True
        stage = f"{stage}_request_cap"

    # A manifest can be built only after the reference/session spine exists.
    manifest: dict[str, Any] | None = None
    if (Path(store) / "reference" / "market_sessions.parquet").exists():
        manifest = build_completeness_manifest(
            Path(store), start_date, end_date, selected,
            generated_at=now().astimezone(timezone.utc).isoformat(),
        )
    return {
        "dry_run": False,
        "no_op": False,
        "requests_made": collector.requests_made,
        "capped": capped,
        "stage": stage,
        "failures": collector.failures,
        "manifest_complete": bool(manifest and manifest.get("complete")),
        "manifest_path": str(Path(store) / "completeness_manifest.json") if manifest else None,
    }


def _parse_endpoints(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="first calendar date (YYYYMMDD)")
    parser.add_argument("--end", default=_utc_now().strftime("%Y%m%d"),
                        help="last calendar date (YYYYMMDD; default UTC today)")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--endpoints", type=_parse_endpoints,
                        default=DEFAULT_ENDPOINTS,
                        help="comma list: daily,daily_basic,stk_limit,suspend_d,stock_st")
    parser.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS,
                        help=f"bounded calls this run (default {DEFAULT_MAX_REQUESTS}; 0 is unlimited)")
    parser.add_argument("--allow-bulk", action="store_true",
                        help="required for an unlimited or >100-call run")
    parser.add_argument("--refresh-reference", action="store_true",
                        help="refresh stock_basic and BSE aliases before resuming")
    parser.add_argument("--dry-run", action="store_true",
                        help="network-free/no-write plan summary")
    args = parser.parse_args()
    result = collect(
        start=args.start, end=args.end, store=args.store, endpoints=args.endpoints,
        max_requests=args.max_requests, allow_bulk=args.allow_bulk,
        refresh_reference=args.refresh_reference, dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    _main()
