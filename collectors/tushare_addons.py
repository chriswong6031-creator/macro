"""Bounded, provenance-first collectors for purchased TuShare A-share add-ons.

This module intentionally exposes *pilot* collection only:

* ``stk_mins`` accepts exactly one ticker, one exchange session, and one frequency;
* ``stk_premarket`` accepts exactly one ticker and one exchange session;
* ``stk_auction`` accepts exactly one ticker in the current Shanghai session during
  TuShare's documented 09:26-09:29 capture window; and
* no range/backfill API exists here.

Every successful response is normalized and validated before the first filesystem
mutation.  It is then installed as an immutable directory containing ``part.parquet``
and ``receipt.json``.  The receipt binds the official TuShare documentation contract,
sanitized request, two-exchange ``trade_cal`` observations, normalized schema, exact
row payload, Parquet bytes, and the clock observed immediately before the add-on
request.  A rerun with identical data is a no-op; a revised response for an existing
partition is a loud keep-first contradiction.

``stk_auction_o`` and ``stk_auction_c`` are deliberately absent from the runnable
contract.  Their state is ``blocked_pending_written_entitlement_confirmation`` even
though TuShare documents them: documentation is not proof that this account bought
those separate permissions.

Execution is blocked unless a separately provisioned written-vendor-authorization or
institutional-contract gate is present.  Personal-plan pricing is not treated as a
commercial-use grant.  No token, token hash, request header, or raw vendor payload is
persisted or logged.  All outputs remain ``context_display_only`` and grant no
commercial, product, team-sharing, signal, or strategy authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

from collectors import tushare_client as tc
from lib import config

DEFAULT_OUTPUT_ROOT = config.data_dir() / "tushare_addons"

AUTHORITY = "context_display_only"
PARTITION_SCHEMA_VERSION = "tushare_addon_partition.v2"
RECEIPT_SCHEMA_VERSION = "tushare_addon_collection_receipt.v2"
CONTRACT_CAPTURE_DATE = "2026-08-09"
SHANGHAI = ZoneInfo("Asia/Shanghai")

LICENSE_AUTHORITY_ENV = "TUSHARE_VENDOR_LICENSE_AUTHORITY"
LICENSE_AUTHORITY_REFERENCE_ENV = "TUSHARE_VENDOR_LICENSE_AUTHORITY_SHA256"
LICENSE_AUTHORITY_GATE_VALUE = (
    "written_vendor_authorization_or_institutional_contract_verified"
)
# Deliberately empty until a vendor-signed authorization or institutional contract is
# reviewed out of band and its exact digest is added through a normal code-review PR.
# Environment variables alone are operator-controlled and may never self-attest rights.
TRUSTED_VENDOR_LICENSE_AUTHORITY_SHA256S: frozenset[str] = frozenset()

ALLOWED_FREQUENCIES = ("1min", "5min", "15min", "30min", "60min")
BLOCKED_UNCONFIRMED_ENDPOINTS: Mapping[str, str] = {
    "stk_auction_o": "blocked_pending_written_entitlement_confirmation",
    "stk_auction_c": "blocked_pending_written_entitlement_confirmation",
}
JOIN_BASIS_CONTRACT: Mapping[str, object] = {
    "schema_version": "tushare_addon_join_basis.v2",
    "ticker_identity": "repo_canonical_SS_SZ_with_BJ_pilots_blocked",
    "exchange_calendar_scope": (
        "SSE_and_SZSE_only_BSE_requires_documented_calendar_authority"
    ),
    "required_nominal_history": (
        "tushare_daily_and_stk_limit_effective_date_plane_from_full_a_spine"
    ),
    "forbidden_nominal_history": "china_stocks_raw_yahoo_split_adjusted_plane",
    "direct_limit_fields": "preserve_stk_premarket_up_limit_and_down_limit",
    "collector_join_status": "declared_not_executed",
}

_TICKER_RE = re.compile(r"^[0-9]{6}\.(?:SS|SZ|BJ)$")
_MINUTE_CURRENT_DAY_NOT_BEFORE = time(21, 0)
_PREMARKET_CURRENT_DAY_NOT_BEFORE = time(16, 30)
_AUCTION_WINDOW_START = time(9, 26)
_AUCTION_WINDOW_END = time(9, 30)
_HTTPS_API_URL = "https://api.tushare.pro"
_HTTP_TIMEOUT_SECONDS = 30


class CollectionHeld(RuntimeError):
    """An expected entitlement/clock/source hold; safe message is a fixed reason code."""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


class CollectorIntegrityError(RuntimeError):
    """A vendor response or immutable on-disk partition contradicted its contract."""


@dataclass(frozen=True)
class SchemaField:
    name: str
    arrow_type: str
    nullable: bool
    unit: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": self.arrow_type,
            "nullable": self.nullable,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class EndpointContract:
    api_name: str
    document_id: int
    title: str
    description: str
    vendor_fields: tuple[str, ...]
    output_schema: tuple[SchemaField, ...]
    max_rows: int = 8_000
    declared_access_context: str = (
        "operator_reported_purchase_not_vendor_attested_and_not_a_license_grant"
    )
    exchange_clock_context_urls: tuple[str, ...] = ()

    @property
    def document_url(self) -> str:
        return f"https://tushare.pro/document/2?doc_id={self.document_id}"

    def contract_payload(self) -> dict[str, object]:
        return {
            "api_name": self.api_name,
            "document_id": self.document_id,
            "document_url": self.document_url,
            "contract_capture_date": CONTRACT_CAPTURE_DATE,
            "title": self.title,
            "description": self.description,
            "vendor_fields": list(self.vendor_fields),
            "output_schema": [field.as_dict() for field in self.output_schema],
            "max_rows": self.max_rows,
            "declared_access_context": self.declared_access_context,
            "exchange_clock_context_urls": list(self.exchange_clock_context_urls),
        }

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.contract_payload())


_COMMON_FIELDS = (
    SchemaField("schema_version", "string", False),
    SchemaField("authority", "string", False),
    SchemaField("trade_date", "string", False, "Asia/Shanghai exchange date"),
    SchemaField("ticker", "string", False, "repo canonical .SS/.SZ; .BJ blocked"),
    SchemaField("frequency", "string", False),
)

ENDPOINTS: Mapping[str, EndpointContract] = {
    "stk_mins": EndpointContract(
        api_name="stk_mins",
        document_id=370,
        title="股票历史分钟行情",
        description="one A-share ticker/session/frequency historical minute pilot",
        vendor_fields=(
            "ts_code",
            "trade_time",
            "open",
            "close",
            "high",
            "low",
            "vol",
            "amount",
        ),
        output_schema=_COMMON_FIELDS
        + (
            SchemaField("trade_time", "string", False, "ISO-8601 Asia/Shanghai"),
            SchemaField(
                "session_segment",
                "string",
                False,
                "regular_trading_window or unclassified_post_close",
            ),
            SchemaField("open", "float64", False, "CNY/share"),
            SchemaField("close", "float64", False, "CNY/share"),
            SchemaField("high", "float64", False, "CNY/share"),
            SchemaField("low", "float64", False, "CNY/share"),
            SchemaField("volume", "float64", False, "shares"),
            SchemaField("amount", "float64", False, "CNY"),
        ),
        exchange_clock_context_urls=(
            (
                "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/"
                "exchange/c/c_20260424_10816482.shtml"
            ),
            (
                "https://docs.static.szse.cn/www/lawrules/rule/trade/current/"
                "W020260424690713155663.pdf"
            ),
        ),
    ),
    "stk_premarket": EndpointContract(
        api_name="stk_premarket",
        document_id=329,
        title="股本情况（盘前）",
        description=(
            "one-session total/float shares and TuShare-reported daily "
            "price-limit fields"
        ),
        vendor_fields=(
            "trade_date",
            "ts_code",
            "total_share",
            "float_share",
            "pre_close",
            "up_limit",
            "down_limit",
        ),
        output_schema=_COMMON_FIELDS
        + (
            SchemaField("total_share_10k", "float64", False, "10,000 shares"),
            SchemaField("float_share_10k", "float64", False, "10,000 shares"),
            SchemaField("pre_close", "float64", True, "CNY/share; ex-right reference"),
            SchemaField("up_limit", "float64", True, "CNY/share"),
            SchemaField("down_limit", "float64", True, "CNY/share"),
        ),
    ),
    "stk_auction": EndpointContract(
        api_name="stk_auction",
        document_id=369,
        title="当日集合竞价",
        description="same-day stock opening-auction transaction snapshot captured 09:26-09:29",
        vendor_fields=(
            "ts_code",
            "trade_date",
            "vol",
            "price",
            "amount",
            "pre_close",
            "turnover_rate",
            "volume_ratio",
            "float_share",
        ),
        output_schema=_COMMON_FIELDS
        + (
            SchemaField("volume", "float64", False, "shares"),
            SchemaField("price", "float64", False, "CNY/share"),
            SchemaField("amount", "float64", False, "CNY"),
            SchemaField("pre_close", "float64", True, "CNY/share"),
            SchemaField("turnover_rate_pct", "float64", True, "percent"),
            SchemaField("volume_ratio", "float64", True, "ratio"),
            SchemaField("float_share_10k", "float64", True, "10,000 shares"),
        ),
    ),
}


@dataclass(frozen=True)
class PilotRequest:
    endpoint: str
    trade_date: date | str
    ticker: str | None = None
    frequency: str | None = None


@dataclass(frozen=True)
class NormalizedRequest:
    endpoint: str
    trade_date: date
    ticker: str | None
    frequency: str

    @property
    def vendor_ticker(self) -> str | None:
        if self.ticker and self.ticker.endswith(".SS"):
            return self.ticker[:-3] + ".SH"
        return self.ticker

    @property
    def scope(self) -> str:
        if self.ticker is None:
            raise CollectorIntegrityError(
                "normalized pilot unexpectedly lacks a ticker"
            )
        return f"ticker-{self.ticker}"

    def identity(self) -> dict[str, object]:
        return {
            "endpoint": self.endpoint,
            "trade_date": self.trade_date.isoformat(),
            "ticker": self.ticker,
            "frequency": self.frequency,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class PilotResult:
    status: str
    endpoint: str
    partition_path: str
    row_count: int
    data_hash: str
    receipt_hash: str
    authority: str = AUTHORITY

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "endpoint": self.endpoint,
            "partition_path": self.partition_path,
            "row_count": self.row_count,
            "data_hash": self.data_hash,
            "receipt_hash": self.receipt_hash,
            "authority": self.authority,
        }


QueryFunction = Callable[..., pd.DataFrame | None]
ClockFunction = Callable[[], datetime]


def _license_authority_receipt() -> dict[str, object]:
    """Fail closed unless a separately reviewed vendor-license gate is provisioned."""
    authority = os.environ.get(LICENSE_AUTHORITY_ENV, "").strip()
    reference = os.environ.get(LICENSE_AUTHORITY_REFERENCE_ENV, "").strip().lower()
    if authority != LICENSE_AUTHORITY_GATE_VALUE or not _is_sha256(reference):
        raise CollectionHeld(
            "written_vendor_authorization_or_institutional_contract_required"
        )
    if reference not in TRUSTED_VENDOR_LICENSE_AUTHORITY_SHA256S:
        raise CollectionHeld("vendor_license_authority_not_out_of_band_allowlisted")
    return {
        "gate_state": "satisfied_for_bounded_metadata_only_pilot",
        "accepted_basis": LICENSE_AUTHORITY_GATE_VALUE,
        "authority_reference_sha256": reference,
        "trust_anchor": "code_reviewed_out_of_band_sha256_allowlist",
        "personal_pricing_nonclaim": "personal_pricing_is_not_a_commercial_use_grant",
        "scope_nonclaims": [
            "no_commercial_use_authority",
            "no_product_publication_authority",
            "no_team_sharing_or_redistribution_authority",
            "no_signal_or_strategy_authority",
        ],
    }


def _query_tushare_https(
    api_name: str, fields: str = "", **params: object
) -> pd.DataFrame | None:
    """Minimal HTTPS-only query path that never logs token, payload, or response text."""
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        return None
    payload = {
        "api_name": api_name,
        "token": token,
        "params": params,
        "fields": fields,
    }
    try:
        response = requests.post(
            _HTTPS_API_URL,
            json=payload,
            timeout=_HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": "MastermindX-TuShare-Addon-Pilot/1"},
            allow_redirects=False,
        )
        if (
            response.is_redirect
            or response.is_permanent_redirect
            or 300 <= response.status_code < 400
        ):
            return None
        response.raise_for_status()
        body = response.json()
    except Exception:  # noqa: BLE001 - credential-bearing request state stays private
        return None
    if not isinstance(body, dict) or body.get("code") not in {0, "0"}:
        return None
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    fields = data.get("fields")
    items = data.get("items")
    if (
        not isinstance(fields, list)
        or not all(isinstance(field, str) and field for field in fields)
        or len(fields) != len(set(fields))
        or not isinstance(items, list)
    ):
        return None
    try:
        return pd.DataFrame(items, columns=fields)
    except (TypeError, ValueError):
        return None


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _canonical_ticker(raw: object) -> str:
    value = str(raw or "").strip().upper()
    normalized = tc.norm_ticker(value) or ""
    if not _TICKER_RE.fullmatch(normalized):
        raise CollectorIntegrityError("vendor response contains a non-A-share ticker")
    return normalized


def _parse_date(raw: date | str) -> date:
    if isinstance(raw, datetime):
        raise CollectionHeld("trade_date_must_not_include_time")
    if isinstance(raw, date):
        return raw
    value = str(raw).strip()
    try:
        if re.fullmatch(r"[0-9]{8}", value):
            value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CollectionHeld("invalid_trade_date") from exc


def normalize_request(request: PilotRequest) -> NormalizedRequest:
    endpoint = str(request.endpoint).strip()
    if endpoint in BLOCKED_UNCONFIRMED_ENDPOINTS:
        raise CollectionHeld(BLOCKED_UNCONFIRMED_ENDPOINTS[endpoint])
    if endpoint not in ENDPOINTS:
        raise CollectionHeld("unsupported_tushare_addon_endpoint")
    trade_day = _parse_date(request.trade_date)
    ticker = _canonical_ticker(request.ticker) if request.ticker else None
    if ticker is None:
        raise CollectionHeld("all_tushare_addon_pilots_require_one_ticker")
    if ticker.endswith(".BJ"):
        raise CollectionHeld("BSE_pilots_blocked_pending_calendar_authority")
    frequency = str(request.frequency).strip() if request.frequency else ""

    if endpoint == "stk_mins":
        if ticker is None:
            raise CollectionHeld("stk_mins_requires_one_ticker")
        if frequency not in ALLOWED_FREQUENCIES:
            raise CollectionHeld("stk_mins_requires_one_supported_frequency")
    elif frequency:
        raise CollectionHeld("frequency_is_only_valid_for_stk_mins")
    elif endpoint == "stk_premarket":
        frequency = "daily_premarket"
    else:
        frequency = "opening_auction"
    return NormalizedRequest(endpoint, trade_day, ticker, frequency)


def _normalized_now(now: datetime | None) -> datetime:
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(SHANGHAI)


def _validate_collection_clock(request: NormalizedRequest, now_cst: datetime) -> str:
    today = now_cst.date()
    clock = now_cst.time().replace(tzinfo=None)
    if request.endpoint == "stk_auction":
        if request.trade_date != today:
            raise CollectionHeld("stk_auction_is_same_day_capture_only")
        if not _AUCTION_WINDOW_START <= clock < _AUCTION_WINDOW_END:
            raise CollectionHeld("outside_documented_stk_auction_capture_window")
        return "same_day_09:26-09:29_Asia/Shanghai"
    if request.trade_date > today:
        raise CollectionHeld("future_session_collection_refused")
    if (
        request.endpoint == "stk_mins"
        and request.trade_date == today
        and clock < _MINUTE_CURRENT_DAY_NOT_BEFORE
    ):
        raise CollectionHeld("current_minute_session_not_finalized")
    if (
        request.endpoint == "stk_premarket"
        and request.trade_date == today
        and clock < _PREMARKET_CURRENT_DAY_NOT_BEFORE
    ):
        raise CollectionHeld("current_premarket_snapshot_may_still_update")
    if request.endpoint == "stk_mins":
        return "historical_or_current_after_21:00_Asia/Shanghai"
    return "historical_or_current_after_16:30_Asia/Shanghai"


def _safe_query(
    query_fn: QueryFunction, api_name: str, **kwargs: object
) -> pd.DataFrame:
    try:
        frame = query_fn(api_name, **kwargs)
    except Exception:  # noqa: BLE001 - do not surface a vendor/client exception string
        raise CollectionHeld("tushare_query_failed_without_persisted_payload") from None
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        raise CollectionHeld(f"{api_name}_unavailable_empty_or_unentitled")
    return frame.copy()


def _official_session_receipt(
    request: NormalizedRequest, query_fn: QueryFunction
) -> tuple[list[dict[str, object]], str]:
    compact = request.trade_date.strftime("%Y%m%d")
    observations: list[dict[str, object]] = []
    states: list[bool] = []
    for exchange in ("SSE", "SZSE"):
        frame = _safe_query(
            query_fn,
            "trade_cal",
            fields="exchange,cal_date,is_open,pretrade_date",
            exchange=exchange,
            start_date=compact,
            end_date=compact,
        )
        expected_columns = {"exchange", "cal_date", "is_open", "pretrade_date"}
        if (
            len(frame.columns) != len(set(frame.columns))
            or set(frame.columns) != expected_columns
        ):
            raise CollectorIntegrityError(
                "trade_cal response lacks exact-session fields"
            )
        exact = frame.loc[frame["cal_date"].astype(str) == compact]
        if len(exact) != 1:
            raise CollectorIntegrityError(
                "trade_cal response is not unique for requested date"
            )
        row = exact.iloc[0]
        if str(row["exchange"]).strip() != exchange:
            raise CollectorIntegrityError(
                "trade_cal response escaped requested exchange"
            )
        raw_open = str(row["is_open"]).strip()
        if raw_open not in {"0", "1", "0.0", "1.0"}:
            raise CollectorIntegrityError("trade_cal is_open value is invalid")
        is_open = raw_open in {"1", "1.0"}
        states.append(is_open)
        raw_pretrade_date = str(row["pretrade_date"]).strip().replace("-", "")
        if not re.fullmatch(r"[0-9]{8}", raw_pretrade_date):
            raise CollectorIntegrityError("trade_cal pretrade_date is invalid")
        try:
            prior_day = _parse_date(raw_pretrade_date)
        except CollectionHeld as exc:
            raise CollectorIntegrityError("trade_cal pretrade_date is invalid") from exc
        if prior_day >= request.trade_date:
            raise CollectorIntegrityError("trade_cal pretrade_date is not prior")
        observations.append(
            {
                "endpoint": "trade_cal",
                "exchange": exchange,
                "cal_date": request.trade_date.isoformat(),
                "is_open": is_open,
                "pretrade_date": prior_day.isoformat(),
            }
        )
    if len(set(states)) != 1:
        raise CollectorIntegrityError(
            "SSE/SZSE trade calendars disagree for requested date"
        )
    if not states[0]:
        raise CollectionHeld("requested_date_is_not_an_open_SSE_SZSE_session")
    return observations, canonical_hash(observations)


def _require_columns(frame: pd.DataFrame, contract: EndpointContract) -> None:
    missing = sorted(set(contract.vendor_fields) - set(frame.columns))
    extra = sorted(set(frame.columns) - set(contract.vendor_fields))
    if missing or extra or len(frame.columns) != len(set(frame.columns)):
        raise CollectorIntegrityError(
            f"{contract.api_name} response schema differs from documented fields"
        )
    if len(frame) > contract.max_rows:
        raise CollectorIntegrityError(
            f"{contract.api_name} response exceeds documented {contract.max_rows}-row cap"
        )


def _source_scalar(value: object) -> object:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        return _source_scalar(item())
    if isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CollectorIntegrityError("vendor source contains a non-finite value")
        return value
    raise CollectorIntegrityError("vendor source contains an unsupported scalar type")


def _source_rows_hash(frame: pd.DataFrame, contract: EndpointContract) -> str:
    """Hash canonical vendor-field/value observations before normalization."""
    _require_columns(frame, contract)
    rows = [
        {field: _source_scalar(raw[field]) for field in contract.vendor_fields}
        for raw in frame.to_dict(orient="records")
    ]
    rows.sort(key=_json_bytes)
    return canonical_hash(rows)


def _number(value: object, *, nullable: bool, positive: bool = False) -> float | None:
    if value is None or pd.isna(value):
        if nullable:
            return None
        raise CollectorIntegrityError("required numeric vendor field is null")
    if isinstance(value, bool):
        raise CollectorIntegrityError("boolean entered a numeric vendor field")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CollectorIntegrityError("vendor numeric field is not numeric") from exc
    if not math.isfinite(result):
        raise CollectorIntegrityError("vendor numeric field is not finite")
    if positive and result <= 0:
        raise CollectorIntegrityError("vendor positive numeric field is not positive")
    return result


def _normalized_trade_date(raw: object, expected: date) -> str:
    value = str(raw or "").strip().replace("-", "")
    if value != expected.strftime("%Y%m%d"):
        raise CollectorIntegrityError("vendor row escaped the exact requested session")
    return expected.isoformat()


def _common_record(
    request: NormalizedRequest, raw_ticker: object, raw_trade_date: object
) -> dict[str, object]:
    ticker = _canonical_ticker(raw_ticker)
    if ticker.endswith(".BJ"):
        raise CollectionHeld("BSE_rows_blocked_pending_calendar_authority")
    if request.ticker is not None and ticker != request.ticker:
        raise CollectorIntegrityError("vendor row escaped the exact requested ticker")
    return {
        "schema_version": PARTITION_SCHEMA_VERSION,
        "authority": AUTHORITY,
        "trade_date": _normalized_trade_date(raw_trade_date, request.trade_date),
        "ticker": ticker,
        "frequency": request.frequency,
    }


def _minute_session_segment(minute_clock: time) -> str:
    if time(9, 30) <= minute_clock <= time(11, 30) or time(
        13, 0
    ) <= minute_clock <= time(15, 0):
        return "regular_trading_window"
    if time(15, 5) <= minute_clock <= time(15, 30):
        # TuShare doc 370 does not define which minute segments it returns.  Current
        # SSE/SZSE rules admit post-close fixed-price trading in this window, but a
        # ticker/date-specific effective-date classifier is deliberately not inferred.
        return "unclassified_post_close"
    raise CollectorIntegrityError("minute bar is outside admitted A-share clocks")


def _normalize_minute_rows(
    frame: pd.DataFrame, request: NormalizedRequest, contract: EndpointContract
) -> list[dict[str, object]]:
    _require_columns(frame, contract)
    records: list[dict[str, object]] = []
    for raw in frame.to_dict(orient="records"):
        try:
            stamp = pd.Timestamp(raw["trade_time"])
        except Exception as exc:
            raise CollectorIntegrityError("minute trade_time is invalid") from exc
        if pd.isna(stamp):
            raise CollectorIntegrityError("minute trade_time is null")
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize(SHANGHAI)
        else:
            stamp = stamp.tz_convert(SHANGHAI)
        if (
            stamp.date() != request.trade_date
            or stamp.second != 0
            or stamp.microsecond != 0
            or stamp.nanosecond != 0
        ):
            raise CollectorIntegrityError(
                "minute bar escaped exact session/minute clock"
            )
        minute_clock = stamp.time().replace(tzinfo=None)
        session_segment = _minute_session_segment(minute_clock)
        common = _common_record(
            request, raw["ts_code"], request.trade_date.strftime("%Y%m%d")
        )
        open_ = _number(raw["open"], nullable=False, positive=True)
        close = _number(raw["close"], nullable=False, positive=True)
        high = _number(raw["high"], nullable=False, positive=True)
        low = _number(raw["low"], nullable=False, positive=True)
        volume = _number(raw["vol"], nullable=False)
        amount = _number(raw["amount"], nullable=False)
        assert None not in (open_, close, high, low, volume, amount)
        if volume < 0 or amount < 0:
            raise CollectorIntegrityError("minute volume/amount is negative")
        if low > min(open_, close) or high < max(open_, close) or low > high:
            raise CollectorIntegrityError("minute OHLC values are incoherent")
        common.update(
            {
                "trade_time": stamp.isoformat(),
                "session_segment": session_segment,
                "open": open_,
                "close": close,
                "high": high,
                "low": low,
                "volume": volume,
                "amount": amount,
            }
        )
        records.append(common)
    records.sort(key=lambda row: (str(row["ticker"]), str(row["trade_time"])))
    keys = [(row["ticker"], row["trade_time"]) for row in records]
    if not records or len(keys) != len(set(keys)):
        raise CollectorIntegrityError(
            "minute response is empty or has duplicate exact bars"
        )
    return records


def _normalize_premarket_rows(
    frame: pd.DataFrame, request: NormalizedRequest, contract: EndpointContract
) -> list[dict[str, object]]:
    _require_columns(frame, contract)
    records: list[dict[str, object]] = []
    for raw in frame.to_dict(orient="records"):
        common = _common_record(request, raw["ts_code"], raw["trade_date"])
        total = _number(raw["total_share"], nullable=False, positive=True)
        floating = _number(raw["float_share"], nullable=False, positive=True)
        assert total is not None and floating is not None
        if floating > total * (1.0 + 1e-9):
            raise CollectorIntegrityError("premarket float shares exceed total shares")
        pre_close = _number(raw["pre_close"], nullable=True, positive=True)
        up_limit = _number(raw["up_limit"], nullable=True, positive=True)
        down_limit = _number(raw["down_limit"], nullable=True, positive=True)
        if up_limit is not None and down_limit is not None and up_limit <= down_limit:
            raise CollectorIntegrityError("premarket upper/lower limits are inverted")
        if pre_close is not None:
            if up_limit is not None and pre_close > up_limit:
                raise CollectorIntegrityError(
                    "premarket reference close exceeds upper limit"
                )
            if down_limit is not None and pre_close < down_limit:
                raise CollectorIntegrityError(
                    "premarket reference close is below lower limit"
                )
        common.update(
            {
                "total_share_10k": total,
                "float_share_10k": floating,
                "pre_close": pre_close,
                "up_limit": up_limit,
                "down_limit": down_limit,
            }
        )
        records.append(common)
    records.sort(key=lambda row: str(row["ticker"]))
    tickers = [str(row["ticker"]) for row in records]
    if not records or len(tickers) != len(set(tickers)):
        raise CollectorIntegrityError(
            "premarket response is empty or has duplicate tickers"
        )
    return records


def _normalize_auction_rows(
    frame: pd.DataFrame, request: NormalizedRequest, contract: EndpointContract
) -> list[dict[str, object]]:
    _require_columns(frame, contract)
    records: list[dict[str, object]] = []
    for raw in frame.to_dict(orient="records"):
        common = _common_record(request, raw["ts_code"], raw["trade_date"])
        volume = _number(raw["vol"], nullable=False)
        price = _number(raw["price"], nullable=False, positive=True)
        amount = _number(raw["amount"], nullable=False)
        assert volume is not None and price is not None and amount is not None
        if volume < 0 or amount < 0:
            raise CollectorIntegrityError("auction volume/amount is negative")
        turnover = _number(raw["turnover_rate"], nullable=True)
        ratio = _number(raw["volume_ratio"], nullable=True)
        floating = _number(raw["float_share"], nullable=True, positive=True)
        if (turnover is not None and turnover < 0) or (ratio is not None and ratio < 0):
            raise CollectorIntegrityError("auction rate/ratio is negative")
        common.update(
            {
                "volume": volume,
                "price": price,
                "amount": amount,
                "pre_close": _number(raw["pre_close"], nullable=True, positive=True),
                "turnover_rate_pct": turnover,
                "volume_ratio": ratio,
                "float_share_10k": floating,
            }
        )
        records.append(common)
    records.sort(key=lambda row: str(row["ticker"]))
    tickers = [str(row["ticker"]) for row in records]
    if not records or len(tickers) != len(set(tickers)):
        raise CollectorIntegrityError(
            "auction response is empty or has duplicate tickers"
        )
    return records


def _normalize_rows(
    frame: pd.DataFrame, request: NormalizedRequest, contract: EndpointContract
) -> list[dict[str, object]]:
    if request.endpoint == "stk_mins":
        return _normalize_minute_rows(frame, request, contract)
    if request.endpoint == "stk_premarket":
        return _normalize_premarket_rows(frame, request, contract)
    return _normalize_auction_rows(frame, request, contract)


def _pa_type(name: str) -> pa.DataType:
    if name == "string":
        return pa.string()
    if name == "float64":
        return pa.float64()
    raise AssertionError(f"unsupported tracked Arrow type: {name}")


def schema_descriptor(contract: EndpointContract) -> dict[str, object]:
    return {
        "schema_version": PARTITION_SCHEMA_VERSION,
        "fields": [field.as_dict() for field in contract.output_schema],
    }


def arrow_schema(contract: EndpointContract) -> pa.Schema:
    descriptor = schema_descriptor(contract)
    return pa.schema(
        [
            pa.field(field.name, _pa_type(field.arrow_type), nullable=field.nullable)
            for field in contract.output_schema
        ],
        metadata={
            b"partition_schema_version": PARTITION_SCHEMA_VERSION.encode(),
            b"endpoint": contract.api_name.encode(),
            b"contract_sha256": contract.contract_hash.encode(),
            b"schema_sha256": canonical_hash(descriptor).encode(),
        },
    )


def _vendor_request(
    request: NormalizedRequest, contract: EndpointContract
) -> dict[str, object]:
    compact = request.trade_date.strftime("%Y%m%d")
    params: dict[str, object] = {
        "fields": ",".join(contract.vendor_fields),
    }
    if request.endpoint == "stk_mins":
        params.update(
            {
                "ts_code": request.vendor_ticker,
                "freq": request.frequency,
                "start_date": f"{request.trade_date.isoformat()} 00:00:00",
                "end_date": f"{request.trade_date.isoformat()} 23:59:59",
            }
        )
    else:
        params["trade_date"] = compact
        if request.vendor_ticker:
            params["ts_code"] = request.vendor_ticker
        if request.endpoint == "stk_auction":
            params["ts_type"] = "STK"
    return params


def _sanitized_transport_request(
    endpoint: str, vendor_request: Mapping[str, object]
) -> dict[str, object]:
    return {
        "transport": "HTTPS",
        "api_name": endpoint,
        "fields": vendor_request.get("fields", ""),
        "params": {
            key: value for key, value in vendor_request.items() if key != "fields"
        },
    }


def partition_path(root: Path, request: NormalizedRequest) -> Path:
    return (
        root
        / request.endpoint
        / f"by_frequency={request.frequency}"
        / f"by_trade_date={request.trade_date.isoformat()}"
        / f"by_scope={request.scope}"
    )


def _receipt_without_hash(
    *,
    contract: EndpointContract,
    request: NormalizedRequest,
    vendor_request: Mapping[str, object],
    calendar_observations: Sequence[Mapping[str, object]],
    calendar_hash: str,
    license_authority: Mapping[str, object],
    clock_policy: str,
    now_cst: datetime,
    records: Sequence[Mapping[str, object]],
    source_rows_hash: str,
    data_hash: str,
    parquet_hash: str,
) -> dict[str, object]:
    descriptor = schema_descriptor(contract)
    request_identity = request.identity()
    return {
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "authority": AUTHORITY,
        "endpoint_contract": {
            **contract.contract_payload(),
            "contract_sha256": contract.contract_hash,
        },
        "access_observation_receipt": {
            "declaration": contract.declared_access_context,
            "observation": "access_observed_at_request_time",
            "observation_basis": "valid_nonempty_rows_returned_for_this_request",
            "observed_at_asia_shanghai": now_cst.isoformat(),
            "nonclaims": [
                "not_proof_of_purchase",
                "not_proof_of_payment",
                "not_proof_of_license_or_commercial_use_rights",
                "not_proof_of_future_access",
                "not_proof_of_trial_absence",
            ],
            "blocked_unconfirmed_endpoints": dict(BLOCKED_UNCONFIRMED_ENDPOINTS),
        },
        "license_authority_gate": dict(license_authority),
        "join_basis_contract": dict(JOIN_BASIS_CONTRACT),
        "request": {
            "identity": request_identity,
            "identity_sha256": canonical_hash(request_identity),
            "vendor_request_without_token": _sanitized_transport_request(
                request.endpoint, vendor_request
            ),
            "maximum_vendor_calls": 3,
            "range_or_bulk_mode": False,
        },
        "request_clock": {
            "observed_at_utc": now_cst.astimezone(timezone.utc).isoformat(),
            "observed_at_asia_shanghai": now_cst.isoformat(),
            "observation_point": (
                "after_trade_cal_immediately_before_addon_endpoint_request"
            ),
            "completeness_policy": clock_policy,
        },
        "runtime_receipt": {
            "python": ".".join(str(value) for value in sys.version_info[:3]),
            "pandas": pd.__version__,
            "pyarrow": pa.__version__,
            "collector_source_sha256": file_hash(Path(__file__)),
            "tushare_client_source_sha256": file_hash(Path(tc.__file__)),
            "github_repository": os.environ.get("GITHUB_REPOSITORY"),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "dependency_lock_sha256": os.environ.get(
                "TUSHARE_ADDON_DEPENDENCY_LOCK_SHA256"
            ),
            "nonclaim": "environment_fields_are_execution_context_not_signed_identity",
        },
        "exact_session_receipt": {
            "source_endpoint": "trade_cal",
            "required_exchanges": ["SSE", "SZSE"],
            "observations": [dict(item) for item in calendar_observations],
            "observations_sha256": calendar_hash,
        },
        "schema_receipt": {
            **descriptor,
            "schema_sha256": canonical_hash(descriptor),
        },
        "data_receipt": {
            "row_count": len(records),
            "canonical_vendor_rows_sha256": source_rows_hash,
            "normalized_rows_sha256": data_hash,
            "parquet_sha256": parquet_hash,
        },
        "partition_identity": request_identity,
        "nonclaims": [
            "context_only_not_signal_authority",
            "no_commercial_use_or_product_publication_authority",
            "no_team_sharing_or_redistribution_authority",
            "no_fillability_or_execution_claim",
            "no_complete_historical_backfill_claim",
            "post_close_rows_are_unclassified_not_a_completeness_claim",
            "no_level2_order_book_or_queue_position",
        ],
    }


def _load_receipt(path: Path) -> dict[str, object]:
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectorIntegrityError(
            "immutable partition receipt is unreadable"
        ) from exc
    if not isinstance(receipt, dict):
        raise CollectorIntegrityError("immutable partition receipt is not an object")
    declared = receipt.get("receipt_sha256")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if not _is_sha256(declared) or canonical_hash(body) != declared:
        raise CollectorIntegrityError(
            "immutable partition receipt hash does not recompute"
        )
    return receipt


def _validate_existing_partition(
    destination: Path,
    contract: EndpointContract,
    request: NormalizedRequest,
    incoming_data_hash: str,
    incoming_source_rows_hash: str,
    incoming_calendar_hash: str,
    incoming_license_authority: Mapping[str, object],
) -> dict[str, object]:
    if destination.is_symlink() or not destination.is_dir():
        raise CollectorIntegrityError(
            "immutable partition path exists but is not a directory"
        )
    if any(child.is_symlink() for child in destination.iterdir()):
        raise CollectorIntegrityError("immutable partition bundle contains a symlink")
    children = {child.name for child in destination.iterdir()}
    if children != {"part.parquet", "receipt.json"}:
        raise CollectorIntegrityError(
            "immutable partition bundle is partial or has unknown files"
        )
    receipt = _load_receipt(destination / "receipt.json")
    if (
        receipt.get("receipt_schema_version") != RECEIPT_SCHEMA_VERSION
        or receipt.get("authority") != AUTHORITY
    ):
        raise CollectorIntegrityError("immutable partition receipt authority changed")
    endpoint_contract = receipt.get("endpoint_contract")
    request_receipt = receipt.get("request")
    data_receipt = receipt.get("data_receipt")
    schema_receipt = receipt.get("schema_receipt")
    session_receipt = receipt.get("exact_session_receipt")
    runtime_receipt = receipt.get("runtime_receipt")
    access_receipt = receipt.get("access_observation_receipt")
    license_receipt = receipt.get("license_authority_gate")
    clock_receipt = receipt.get("request_clock")
    if not all(
        isinstance(value, dict)
        for value in (
            endpoint_contract,
            request_receipt,
            data_receipt,
            schema_receipt,
            session_receipt,
            runtime_receipt,
            access_receipt,
            license_receipt,
            clock_receipt,
        )
    ):
        raise CollectorIntegrityError(
            "immutable partition receipt sections are malformed"
        )
    expected_contract = {
        **contract.contract_payload(),
        "contract_sha256": contract.contract_hash,
    }
    if endpoint_contract != expected_contract:
        raise CollectorIntegrityError("immutable partition endpoint contract changed")
    if (
        set(access_receipt)
        != {
            "declaration",
            "observation",
            "observation_basis",
            "observed_at_asia_shanghai",
            "nonclaims",
            "blocked_unconfirmed_endpoints",
        }
        or access_receipt.get("declaration") != contract.declared_access_context
        or access_receipt.get("observation") != "access_observed_at_request_time"
        or access_receipt.get("observation_basis")
        != "valid_nonempty_rows_returned_for_this_request"
        or access_receipt.get("nonclaims")
        != [
            "not_proof_of_purchase",
            "not_proof_of_payment",
            "not_proof_of_license_or_commercial_use_rights",
            "not_proof_of_future_access",
            "not_proof_of_trial_absence",
        ]
        or access_receipt.get("blocked_unconfirmed_endpoints")
        != dict(BLOCKED_UNCONFIRMED_ENDPOINTS)
    ):
        raise CollectorIntegrityError("immutable access observation receipt changed")
    if license_receipt != dict(incoming_license_authority):
        raise CollectorIntegrityError("immutable license authority gate changed")
    if receipt.get("join_basis_contract") != dict(JOIN_BASIS_CONTRACT):
        raise CollectorIntegrityError("immutable join basis contract changed")
    if receipt.get("nonclaims") != [
        "context_only_not_signal_authority",
        "no_commercial_use_or_product_publication_authority",
        "no_team_sharing_or_redistribution_authority",
        "no_fillability_or_execution_claim",
        "no_complete_historical_backfill_claim",
        "post_close_rows_are_unclassified_not_a_completeness_claim",
        "no_level2_order_book_or_queue_position",
    ]:
        raise CollectorIntegrityError("immutable authority nonclaims changed")
    identity = request.identity()
    if (
        request_receipt.get("identity") != identity
        or receipt.get("partition_identity") != identity
        or request_receipt.get("identity_sha256") != canonical_hash(identity)
        or request_receipt.get("vendor_request_without_token")
        != _sanitized_transport_request(
            request.endpoint, _vendor_request(request, contract)
        )
        or request_receipt.get("maximum_vendor_calls") != 3
        or request_receipt.get("range_or_bulk_mode") is not False
    ):
        raise CollectorIntegrityError("immutable partition request identity changed")
    descriptor = schema_descriptor(contract)
    if schema_receipt != {
        **descriptor,
        "schema_sha256": canonical_hash(descriptor),
    }:
        raise CollectorIntegrityError("immutable partition schema receipt changed")
    try:
        observed_utc = datetime.fromisoformat(str(clock_receipt["observed_at_utc"]))
        observed_shanghai = datetime.fromisoformat(
            str(clock_receipt["observed_at_asia_shanghai"])
        )
    except (KeyError, ValueError) as exc:
        raise CollectorIntegrityError(
            "immutable collection clock is malformed"
        ) from exc
    if (
        set(clock_receipt)
        != {
            "observed_at_utc",
            "observed_at_asia_shanghai",
            "observation_point",
            "completeness_policy",
        }
        or observed_utc.tzinfo is None
        or observed_shanghai.tzinfo is None
        or observed_utc.utcoffset() != timedelta(0)
        or observed_shanghai.utcoffset() != timedelta(hours=8)
        or observed_utc != observed_shanghai
        or clock_receipt.get("observation_point")
        != "after_trade_cal_immediately_before_addon_endpoint_request"
        or access_receipt.get("observed_at_asia_shanghai")
        != clock_receipt.get("observed_at_asia_shanghai")
    ):
        raise CollectorIntegrityError("immutable collection clock is malformed")
    try:
        expected_clock_policy = _validate_collection_clock(request, observed_shanghai)
    except CollectionHeld as exc:
        raise CollectorIntegrityError("immutable collection clock is invalid") from exc
    if clock_receipt.get("completeness_policy") != expected_clock_policy:
        raise CollectorIntegrityError("immutable collection clock policy changed")
    observations = session_receipt.get("observations")
    stored_calendar_hash = session_receipt.get("observations_sha256")
    if (
        session_receipt.get("source_endpoint") != "trade_cal"
        or session_receipt.get("required_exchanges") != ["SSE", "SZSE"]
        or not isinstance(observations, list)
        or canonical_hash(observations) != stored_calendar_hash
        or stored_calendar_hash != incoming_calendar_hash
    ):
        raise CollectorIntegrityError("immutable exact-session receipt changed")
    if not all(
        _is_sha256(runtime_receipt.get(field))
        for field in ("collector_source_sha256", "tushare_client_source_sha256")
    ):
        raise CollectorIntegrityError("immutable runtime provenance is malformed")
    lock_hash = runtime_receipt.get("dependency_lock_sha256")
    if lock_hash is not None and not _is_sha256(lock_hash):
        raise CollectorIntegrityError("immutable dependency provenance is malformed")
    if set(data_receipt) != {
        "row_count",
        "canonical_vendor_rows_sha256",
        "normalized_rows_sha256",
        "parquet_sha256",
    }:
        raise CollectorIntegrityError("immutable data receipt schema changed")
    parquet_path = destination / "part.parquet"
    if data_receipt.get("parquet_sha256") != file_hash(parquet_path):
        raise CollectorIntegrityError("immutable Parquet bytes contradict the receipt")
    if (
        not _is_sha256(data_receipt.get("canonical_vendor_rows_sha256"))
        or data_receipt.get("canonical_vendor_rows_sha256") != incoming_source_rows_hash
    ):
        raise CollectorIntegrityError("keep-first vendor source contradiction")
    try:
        table = pq.ParquetFile(parquet_path).read()
    except Exception as exc:
        raise CollectorIntegrityError("immutable Parquet part is unreadable") from exc
    if table.schema != arrow_schema(contract):
        raise CollectorIntegrityError(
            "immutable Parquet schema contradicts the contract"
        )
    stored_rows = table.to_pylist()
    stored_hash = canonical_hash(stored_rows)
    if data_receipt.get("normalized_rows_sha256") != stored_hash:
        raise CollectorIntegrityError(
            "immutable normalized rows contradict the receipt"
        )
    if incoming_data_hash != stored_hash:
        raise CollectorIntegrityError("keep-first immutable partition contradiction")
    if int(data_receipt.get("row_count", -1)) != len(stored_rows):
        raise CollectorIntegrityError(
            "immutable partition row count contradicts the receipt"
        )
    return receipt


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _install_partition(
    *,
    root: Path,
    contract: EndpointContract,
    request: NormalizedRequest,
    vendor_request: Mapping[str, object],
    calendar_observations: Sequence[Mapping[str, object]],
    calendar_hash: str,
    license_authority: Mapping[str, object],
    clock_policy: str,
    now_cst: datetime,
    records: Sequence[Mapping[str, object]],
    source_rows_hash: str,
) -> PilotResult:
    destination = partition_path(root, request)
    data_hash = canonical_hash(list(records))
    if destination.exists():
        receipt = _validate_existing_partition(
            destination,
            contract,
            request,
            data_hash,
            source_rows_hash,
            calendar_hash,
            license_authority,
        )
        return PilotResult(
            status="unchanged",
            endpoint=request.endpoint,
            partition_path=str(destination),
            row_count=len(records),
            data_hash=data_hash,
            receipt_hash=str(receipt["receipt_sha256"]),
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=".tushare-addon-stage-", dir=destination.parent)
    )
    try:
        parquet_path = stage / "part.parquet"
        table = pa.Table.from_pylist(list(records), schema=arrow_schema(contract))
        pq.write_table(
            table,
            parquet_path,
            compression="zstd",
            use_dictionary=False,
            write_statistics=True,
        )
        parquet_hash = file_hash(parquet_path)
        receipt = _receipt_without_hash(
            contract=contract,
            request=request,
            vendor_request=vendor_request,
            calendar_observations=calendar_observations,
            calendar_hash=calendar_hash,
            license_authority=license_authority,
            clock_policy=clock_policy,
            now_cst=now_cst,
            records=records,
            source_rows_hash=source_rows_hash,
            data_hash=data_hash,
            parquet_hash=parquet_hash,
        )
        receipt["receipt_sha256"] = canonical_hash(receipt)
        receipt_path = stage / "receipt.json"
        receipt_path.write_bytes(_json_bytes(receipt) + b"\n")
        _fsync_file(parquet_path)
        _fsync_file(receipt_path)
        stage_descriptor = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(stage_descriptor)
        finally:
            os.close(stage_descriptor)
        try:
            os.rename(stage, destination)
        except OSError:
            if not destination.exists():
                raise
            existing = _validate_existing_partition(
                destination,
                contract,
                request,
                data_hash,
                source_rows_hash,
                calendar_hash,
                license_authority,
            )
            return PilotResult(
                status="unchanged",
                endpoint=request.endpoint,
                partition_path=str(destination),
                row_count=len(records),
                data_hash=data_hash,
                receipt_hash=str(existing["receipt_sha256"]),
            )
        parent_descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
        return PilotResult(
            status="written",
            endpoint=request.endpoint,
            partition_path=str(destination),
            row_count=len(records),
            data_hash=data_hash,
            receipt_hash=str(receipt["receipt_sha256"]),
        )
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def pilot_plan(
    request: PilotRequest, *, output_root: Path = DEFAULT_OUTPUT_ROOT
) -> dict[str, object]:
    """Return a no-network, no-write plan for one structurally bounded request."""
    normalized = normalize_request(request)
    contract = ENDPOINTS[normalized.endpoint]
    return {
        "status": "planned_no_network_no_write",
        "authority": AUTHORITY,
        "request": normalized.identity(),
        "partition_path": str(partition_path(output_root, normalized)),
        "endpoint_contract_sha256": contract.contract_hash,
        "endpoint_document_url": contract.document_url,
        "declared_access_context": contract.declared_access_context,
        "license_authority_gate": {
            "required_for_execute": True,
            "state": "not_evaluated_plan_only",
            "accepted_basis": LICENSE_AUTHORITY_GATE_VALUE,
            "trust_anchor": "code_reviewed_out_of_band_sha256_allowlist",
            "personal_pricing_nonclaim": (
                "personal_pricing_is_not_a_commercial_use_grant"
            ),
        },
        "blocked_unconfirmed_endpoints": dict(BLOCKED_UNCONFIRMED_ENDPOINTS),
        "join_basis_contract": dict(JOIN_BASIS_CONTRACT),
        "maximum_vendor_calls": 3,
        "range_or_bulk_mode": False,
    }


def collect_pilot(
    request: PilotRequest,
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    query_fn: QueryFunction = _query_tushare_https,
    now: datetime | None = None,
    clock_fn: ClockFunction | None = None,
) -> PilotResult:
    """Collect one bounded pilot partition or fail before installing any evidence."""
    normalized = normalize_request(request)
    license_authority = _license_authority_receipt()
    if now is not None and clock_fn is not None:
        raise CollectionHeld("ambiguous_collection_clock_source")
    if clock_fn is not None:
        observe_clock = clock_fn
    elif now is not None:
        observe_clock = lambda: now
    else:
        observe_clock = lambda: datetime.now(timezone.utc)

    initial_now_cst = _normalized_now(observe_clock())
    _validate_collection_clock(normalized, initial_now_cst)
    if query_fn is _query_tushare_https and not tc.enabled():
        raise CollectionHeld("TUSHARE_TOKEN_absent")
    calendar_observations, calendar_hash = _official_session_receipt(
        normalized, query_fn
    )
    contract = ENDPOINTS[normalized.endpoint]
    vendor_request = _vendor_request(normalized, contract)
    # The two calendar calls can consume most of the four-minute auction window.
    # Re-observe immediately before the paid add-on call; this final observation,
    # rather than the earlier admission check, is what the receipt binds.
    request_now_cst = _normalized_now(observe_clock())
    clock_policy = _validate_collection_clock(normalized, request_now_cst)
    frame = _safe_query(query_fn, normalized.endpoint, **vendor_request)
    source_rows_hash = _source_rows_hash(frame, contract)
    records = _normalize_rows(frame, normalized, contract)
    return _install_partition(
        root=output_root,
        contract=contract,
        request=normalized,
        vendor_request=vendor_request,
        calendar_observations=calendar_observations,
        calendar_hash=calendar_hash,
        license_authority=license_authority,
        clock_policy=clock_policy,
        now_cst=request_now_cst,
        records=records,
        source_rows_hash=source_rows_hash,
    )


__all__ = [
    "ALLOWED_FREQUENCIES",
    "AUTHORITY",
    "BLOCKED_UNCONFIRMED_ENDPOINTS",
    "DEFAULT_OUTPUT_ROOT",
    "ENDPOINTS",
    "JOIN_BASIS_CONTRACT",
    "CollectionHeld",
    "CollectorIntegrityError",
    "EndpointContract",
    "PilotRequest",
    "PilotResult",
    "arrow_schema",
    "collect_pilot",
    "normalize_request",
    "partition_path",
    "pilot_plan",
    "schema_descriptor",
]
