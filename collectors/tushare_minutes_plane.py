"""Bulk historical A-share minute-bar plane (TuShare ``stk_mins``, doc 370).

This is the "separately reviewed bulk plane" that
``research/TUSHARE_ADDONS_COLLECTOR_FOUNDATION_2026-08-09.md`` §"Deliberate
limitations" item 4 demands before minute history may be expanded past the
single-ticker pilot: an object-store layout, a request/rate budget, a resumable
manifest, a coverage ledger, a corporate-action basis statement, and a sampled
reconciliation gate.  Architecture authority is
``research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md`` (Lane B).

What this module is
-------------------

* **Planning is free and offline.**  ``plan_backfill`` performs no network call
  and no filesystem write.  It emits every vendor call the backfill would make,
  the projected row budget, and the wall-clock floor.
* **Execution is gated by TP-0.** ``execute_backfill`` fails closed unless a
  Lane-A ``stk_mins`` probe receipt already exists on disk. Sequencing law: no
  bulk backfill runs before that endpoint's live access/schema witness.
* **The store is keep-first immutable.**  A partition is one
  ``(frequency, ticker, year)`` bundle of ``part.parquet`` + ``receipt.json``.
  An identical rerun is a byte-preserving no-op.  Changed vendor rows for an
  already-witnessed partition are an integrity contradiction that is recorded
  in the coverage ledger and never overwritten.
* **Nothing is silently dropped or silently trusted.**  Zero-volume bars are
  RETAINED and classified (``bar_class``); a response that reaches the
  documented 8,000-row cap is treated as possibly truncated and refused; an
  off-tick price fails the partition rather than being rounded into the store.

Corporate-action basis (binding, and repeated in every receipt)
--------------------------------------------------------------

``stk_mins`` prices are vendor-served **NOMINAL intraday** prices: they are the
prices printed on that session, unadjusted for later splits, dividends, or
rights issues.  This plane performs no adjustment and publishes no adjustment
factor.

* The nominal DAILY authority remains the spine's ``daily`` / ``stk_limit``
  effective-date plane (``collectors/china_tushare_spine.py``).  Same-day
  nominal daily bars from that spine are the ONLY reconciliation anchor this
  plane accepts.
* ``china_stocks_raw`` (Yahoo-sourced, split-ADJUSTED) is **FORBIDDEN** as a
  minute-price crosscheck basis.  Comparing a nominal minute tape against an
  adjusted daily plane manufactures a fake mismatch on every name that ever
  split, and silently agrees on the ones that did not — the worst possible
  detector.  ``reconcile_partition`` accepts a daily frame only through
  ``DAILY_REFERENCE_BASIS`` and refuses any other declared basis.

Unit trap (measured against both vendor contracts)
--------------------------------------------------

``stk_mins`` ships ``vol`` in **shares** and ``amount`` in **CNY**.  The spine's
``daily`` plane ships ``volume_lots`` in **lots (手, 100 shares)** and
``amount_cny_thousands`` in **thousands of CNY**.  Reconciliation converts
explicitly through ``SHARES_PER_LOT`` / ``CNY_PER_AMOUNT_UNIT``; never compare
the two raw columns.

Authority
---------

Collection is operator-ordered under
``research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md``. This module deliberately
carries no self-attestation environment gate or legal conclusion. Product
surfaces built on this store still ship through normal design commissioning,
not merely because the private store exists.

The nonclaims this module still makes are EPISTEMIC, not legal: access is
observed at request time and nowhere else; an absent bar is never fabricated;
a zero-volume bar is classified, never attributed to a cause it did not
witness. Those claims remain bounded to what the collected evidence can prove.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time as _time
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from collectors import tushare_addons as addons
from collectors import tushare_client as tc
from lib import config

# --------------------------------------------------------------------------------------
# Identity, authority, and the pinned base contract
# --------------------------------------------------------------------------------------

DEFAULT_STORE_ROOT = config.data_dir() / "tushare_minutes"
DEFAULT_ADDONS_ROOT = addons.DEFAULT_OUTPUT_ROOT
DEFAULT_SPINE_STORE = config.data_dir() / "china_tushare_spine"
DEFAULT_EVENT_CATALOG = (
    config.data_dir() / "china_microstructure" / "limit_events.parquet"
)

AUTHORITY = "context_display_only"
PARTITION_SCHEMA_VERSION = "tushare_minutes_partition.v1"
RECEIPT_SCHEMA_VERSION = "tushare_minutes_partition_receipt.v1"
MANIFEST_SCHEMA_VERSION = "cn_tushare_minutes_manifest.v1"
COVERAGE_ROW_SCHEMA_VERSION = "cn_tushare_minutes_coverage_row.v1"
PLAN_SCHEMA_VERSION = "cn_tushare_minutes_backfill_plan.v1"

SHANGHAI = ZoneInfo("Asia/Shanghai")

#: The ``stk_mins`` endpoint contract is OWNED by ``collectors/tushare_addons.py``.
#: It is imported, never re-declared: forking the field list or the row cap here
#: would let the bulk plane drift away from the pilot that witnessed the schema.
BASE_ENDPOINT_CONTRACT = addons.ENDPOINTS["stk_mins"]
BASE_VENDOR_FIELDS = BASE_ENDPOINT_CONTRACT.vendor_fields
MAX_ROWS_PER_RESPONSE = BASE_ENDPOINT_CONTRACT.max_rows  # documented 8,000-row cap
ALLOWED_FREQUENCIES = addons.ALLOWED_FREQUENCIES

# --------------------------------------------------------------------------------------
# Rate budget (300/min is ONE shared premium pool; this plane margins itself to 240)
# --------------------------------------------------------------------------------------

SHARED_PREMIUM_POOL_CALLS_PER_MINUTE = 300
RATE_CEILING_CALLS_PER_MINUTE = 240
SEQUENTIAL_EXECUTION_ONLY = True

# --------------------------------------------------------------------------------------
# A-share clocks and price ticks
#
# These MIRROR ``collectors/china_tushare_spine.py`` (A_SHARE_PRICE_TICK /
# A_SHARE_PRICE_SCALE) and ``collectors/tushare_addons._minute_session_segment``.
# They are re-declared rather than imported so this plane does not pull a 4,900-line
# collector into every planning call and does not depend on a private helper; the
# drift is pinned by ``tests/test_tushare_minutes_plane.py``, which imports both
# originals and asserts equality.
# --------------------------------------------------------------------------------------

A_SHARE_PRICE_TICK = Decimal("0.01")
A_SHARE_PRICE_SCALE = 100

REGULAR_TRADING_WINDOWS: tuple[tuple[time, time], ...] = (
    (time(9, 30), time(11, 30)),
    (time(13, 0), time(15, 0)),
)
#: TuShare doc 370 does not define a hard minute cutoff.  Current SSE/SZSE rules admit
#: post-close fixed-price trading here, so rows are KEPT and labelled rather than
#: silently discarded — and never counted as regular-window tape.
POST_CLOSE_WINDOW: tuple[time, time] = (time(15, 5), time(15, 30))

SESSION_SEGMENT_REGULAR = "regular_trading_window"
SESSION_SEGMENT_POST_CLOSE = "unclassified_post_close"

#: ``stk_mins`` volume is SHARES and amount is CNY; the spine's ``daily`` plane is
#: lots (手) and thousands of CNY.  Every cross-plane comparison goes through these.
SHARES_PER_LOT = 100
CNY_PER_AMOUNT_UNIT = 1000

FREQUENCY_STEP_MINUTES: Mapping[str, int] = {
    "1min": 1,
    "5min": 5,
    "15min": 15,
    "30min": 30,
    "60min": 60,
}

BAR_CLASS_TRADED = "traded"
BAR_CLASS_ZERO_VOLUME_FLAT = "zero_volume_flat"
BAR_CLASS_ZERO_VOLUME_INCONSISTENT = "zero_volume_inconsistent"
BAR_CLASS_VOLUME_WITHOUT_AMOUNT = "volume_without_amount"
BAR_CLASSES = (
    BAR_CLASS_TRADED,
    BAR_CLASS_ZERO_VOLUME_FLAT,
    BAR_CLASS_ZERO_VOLUME_INCONSISTENT,
    BAR_CLASS_VOLUME_WITHOUT_AMOUNT,
)

CORPORATE_ACTION_BASIS: Mapping[str, object] = {
    "schema_version": "cn_tushare_minutes_corporate_action_basis.v1",
    "minute_price_basis": "tushare_stk_mins_vendor_served_nominal_intraday_unadjusted",
    "adjustment_performed": "none_this_plane_publishes_no_adjustment_factor",
    "nominal_daily_authority": (
        "tushare_daily_and_stk_limit_effective_date_plane_from_full_a_spine"
    ),
    "reconciliation_anchor": "same_day_nominal_daily_bars_from_the_spine",
    "forbidden_reconciliation_basis": "china_stocks_raw_yahoo_split_adjusted_plane",
    "forbidden_basis_reason": (
        "an adjusted daily plane manufactures a mismatch on every name that split "
        "and agrees silently on the ones that did not"
    ),
    "vendor_revision_policy": (
        "keep_first_immutable_partitions_revisions_recorded_as_contradictions"
    ),
}

DAILY_REFERENCE_BASIS = "tushare.daily_unadjusted_nominal"
FORBIDDEN_DAILY_REFERENCE_BASES = frozenset(
    {
        "china_stocks_raw",
        "china_stocks_raw_yahoo_split_adjusted_plane",
        "yahoo_adjusted",
        "yahoo_split_adjusted",
    }
)

#: EPISTEMIC nonclaims only.  The licensing question is settled by the operator's
#: pinned statement; what remains is what this store can and cannot EVIDENCE.
PLANE_NONCLAIMS: tuple[str, ...] = (
    "context_only_not_signal_authority",
    "product_surfaces_ship_through_normal_design_commissioning_not_from_this_store",
    "no_fillability_or_execution_claim",
    "no_level2_order_book_or_queue_position",
    "minute_prices_are_nominal_and_carry_no_corporate_action_adjustment",
    "zero_volume_bars_are_classified_not_attributed_to_suspension",
    "post_close_rows_are_unclassified_not_a_completeness_claim",
    "absent_bars_are_never_fabricated_a_short_session_is_recorded_short",
    "coverage_ledger_records_what_was_witnessed_not_that_history_is_complete",
)


class MinutesPlaneHeld(RuntimeError):
    """An expected gate/entitlement/sequencing hold; message is a fixed reason code."""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


class MinutesPlaneIntegrityError(RuntimeError):
    """A vendor response or an immutable on-disk partition contradicted its contract."""


QueryFunction = Callable[..., "pd.DataFrame | None"]
ClockFunction = Callable[[], datetime]


# --------------------------------------------------------------------------------------
# Canonical hashing (byte-identical convention to the addons pilot)
# --------------------------------------------------------------------------------------


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
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


# --------------------------------------------------------------------------------------
# Exact decimal prices (the spine's approach; never binary-float rounding)
# --------------------------------------------------------------------------------------


def exact_decimal(value: object, *, field_name: str) -> Decimal:
    """Parse a finite decimal through TEXT, never through binary-float state."""
    if isinstance(value, bool) or value is None:
        raise MinutesPlaneIntegrityError(f"{field_name} must be a finite decimal")
    try:
        if pd.isna(value):
            raise MinutesPlaneIntegrityError(f"{field_name} must be a finite decimal")
    except (TypeError, ValueError):
        pass
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise MinutesPlaneIntegrityError(
            f"{field_name} must be a finite decimal"
        ) from exc
    if not parsed.is_finite():
        raise MinutesPlaneIntegrityError(f"{field_name} must be a finite decimal")
    return parsed


def quote_price_cents(value: object, *, field_name: str) -> int:
    """Validate a positive on-tick A-share quote and return its lossless cent value."""
    price = exact_decimal(value, field_name=field_name)
    if price <= 0:
        raise MinutesPlaneIntegrityError(f"{field_name} must be positive")
    tick_price = price.quantize(A_SHARE_PRICE_TICK, rounding=ROUND_HALF_UP)
    if price != tick_price:
        raise MinutesPlaneIntegrityError(
            f"{field_name}={price} is off the A-share CNY {A_SHARE_PRICE_TICK} quote tick"
        )
    return int(tick_price * A_SHARE_PRICE_SCALE)


def _finite_number(value: object, *, field_name: str) -> float:
    if value is None:
        raise MinutesPlaneIntegrityError(f"{field_name} is required")
    try:
        if pd.isna(value):
            raise MinutesPlaneIntegrityError(f"{field_name} is required")
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        raise MinutesPlaneIntegrityError(f"boolean entered numeric field {field_name}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MinutesPlaneIntegrityError(f"{field_name} is not numeric") from exc
    if not math.isfinite(result):
        raise MinutesPlaneIntegrityError(f"{field_name} is not finite")
    return result


# --------------------------------------------------------------------------------------
# Session clocks and per-session row budgets
# --------------------------------------------------------------------------------------


def _minutes(clock: time) -> int:
    return clock.hour * 60 + clock.minute


def classify_session_segment(minute_clock: time) -> str:
    """``regular_trading_window`` / ``unclassified_post_close``; raises off-clock.

    Mirrors ``tushare_addons._minute_session_segment`` exactly (drift-pinned by test).
    """
    for start, end in REGULAR_TRADING_WINDOWS:
        if start <= minute_clock <= end:
            return SESSION_SEGMENT_REGULAR
    if POST_CLOSE_WINDOW[0] <= minute_clock <= POST_CLOSE_WINDOW[1]:
        return SESSION_SEGMENT_POST_CLOSE
    raise MinutesPlaneIntegrityError("minute bar is outside admitted A-share clocks")


def _window_stamp_count(start: time, end: time, step_minutes: int) -> int:
    return (_minutes(end) - _minutes(start)) // step_minutes + 1


def max_bars_per_session(frequency: str) -> int:
    """CONSERVATIVE upper bound on rows one ticker-session can return at ``frequency``.

    Counted from the admitted clocks themselves (both regular windows inclusive, plus
    the post-close window this plane keeps), NOT from doc 370's nominal 240-bar
    session.  The bound is deliberately loose: a chunk sized against a 240-bar session
    would allow 33 sessions/call at 1min, and any extra stamp the vendor returns —
    a post-close print, an inclusive boundary bar — would push the response into the
    8,000-row cap and produce a silently truncated tape.  Trading ~4 sessions of
    headroom per call for that guarantee is the right trade.
    """
    step = FREQUENCY_STEP_MINUTES.get(str(frequency))
    if step is None:
        raise MinutesPlaneHeld("unsupported_stk_mins_frequency")
    regular = sum(
        _window_stamp_count(start, end, step) for start, end in REGULAR_TRADING_WINDOWS
    )
    post_close = _window_stamp_count(POST_CLOSE_WINDOW[0], POST_CLOSE_WINDOW[1], step)
    return regular + post_close


def sessions_per_chunk(frequency: str) -> int:
    """Sessions one vendor call may request without risking the documented row cap."""
    per_session = max_bars_per_session(frequency)
    count = MAX_ROWS_PER_RESPONSE // per_session
    if count < 1:
        raise MinutesPlaneHeld("row_cap_cannot_hold_one_session_at_this_frequency")
    return count


# --------------------------------------------------------------------------------------
# Session calendar (planning input; declared provenance, never invented)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionCalendar:
    """An ordered list of A-share sessions with EXPLICIT provenance.

    The plane never synthesizes a calendar.  A calendar derived from observed event
    rows is an observed LOWER BOUND on real sessions and says so in its nonclaims;
    the spine's attested SSE=SZSE ``market_sessions.parquet`` is preferred whenever
    that store exists.
    """

    sessions: tuple[date, ...]
    source: str
    source_path: str | None
    source_sha256: str | None
    nonclaims: tuple[str, ...]

    def between(self, start: date, end: date) -> tuple[date, ...]:
        return tuple(day for day in self.sessions if start <= day <= end)

    def receipt(self) -> dict[str, object]:
        return {
            "source": self.source,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "session_count": len(self.sessions),
            "first_session": self.sessions[0].isoformat() if self.sessions else None,
            "last_session": self.sessions[-1].isoformat() if self.sessions else None,
            "nonclaims": list(self.nonclaims),
        }


def _ordered_unique_dates(values: Iterable[object]) -> tuple[date, ...]:
    seen: set[date] = set()
    for value in values:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            raise MinutesPlaneIntegrityError("session calendar contains a null date")
        seen.add(stamp.date())
    return tuple(sorted(seen))


def load_session_calendar_from_spine(
    store: Path = DEFAULT_SPINE_STORE,
) -> SessionCalendar:
    """Attested SSE=SZSE session clock from the full-A spine's ``market_sessions``."""
    path = Path(store) / "reference" / "market_sessions.parquet"
    if not path.is_file():
        raise MinutesPlaneHeld("spine_market_sessions_artifact_is_absent")
    frame = pd.read_parquet(path)
    if "trade_date" not in frame.columns:
        raise MinutesPlaneIntegrityError("spine market_sessions lacks trade_date")
    return SessionCalendar(
        sessions=_ordered_unique_dates(frame["trade_date"]),
        source="china_tushare_spine.reference.market_sessions",
        source_path=str(path),
        source_sha256=file_hash(path),
        nonclaims=("attested_sse_szse_consensus_clock_bse_not_covered",),
    )


def load_session_calendar_from_event_catalog(
    path: Path = DEFAULT_EVENT_CATALOG,
) -> SessionCalendar:
    """Observed sessions from the limit-event catalog — a LOWER BOUND, not a calendar.

    A date with no limit event anywhere in the catalog's universe is invisible here.
    That is safe for chunk planning (the chunk is a date RANGE; the vendor returns
    whatever sessions actually exist) precisely because ``max_bars_per_session`` is
    already margined; it would NOT be safe as a completeness claim, and is not made
    into one.
    """
    path = Path(path)
    if not path.is_file():
        raise MinutesPlaneHeld("limit_event_catalog_is_absent")
    frame = pd.read_parquet(path, columns=["date"])
    return SessionCalendar(
        sessions=_ordered_unique_dates(frame["date"]),
        source="china_microstructure.limit_events.observed_sessions",
        source_path=str(path),
        source_sha256=file_hash(path),
        nonclaims=(
            "observed_lower_bound_on_sessions_not_an_exchange_calendar",
            "a_session_with_no_limit_event_in_this_universe_is_not_represented",
            "prefer_spine_market_sessions_when_that_store_exists",
        ),
    )


# --------------------------------------------------------------------------------------
# Universe
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Universe:
    """Tickers to back-fill, with the years each ticker is actually WANTED for."""

    tickers: tuple[str, ...]
    source: str
    source_path: str | None
    source_sha256: str | None
    event_years: Mapping[str, frozenset[int]] = field(default_factory=dict)

    def receipt(self) -> dict[str, object]:
        return {
            "source": self.source,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "ticker_count": len(self.tickers),
            "has_event_years": bool(self.event_years),
        }


def _canonical_ticker(raw: object) -> str:
    value = str(raw or "").strip().upper()
    normalized = tc.norm_ticker(value) or ""
    if len(normalized) != 9 or normalized[6] != "." or not normalized[:6].isdigit():
        raise MinutesPlaneIntegrityError(f"not an A-share ticker: {value!r}")
    suffix = normalized[7:]
    if suffix == "BJ":
        raise MinutesPlaneHeld("BSE_tickers_blocked_pending_calendar_authority")
    if suffix not in {"SS", "SZ"}:
        raise MinutesPlaneIntegrityError(f"not an A-share ticker: {value!r}")
    return normalized


def load_universe_from_event_catalog(path: Path = DEFAULT_EVENT_CATALOG) -> Universe:
    """Distinct tickers in the limit-event catalog + the years each has events in."""
    path = Path(path)
    if not path.is_file():
        raise MinutesPlaneHeld("limit_event_catalog_is_absent")
    frame = pd.read_parquet(path, columns=["date", "ticker"])
    years: dict[str, set[int]] = {}
    for raw_ticker, raw_date in zip(frame["ticker"], frame["date"], strict=True):
        ticker = _canonical_ticker(raw_ticker)
        years.setdefault(ticker, set()).add(pd.Timestamp(raw_date).year)
    return Universe(
        tickers=tuple(sorted(years)),
        source="china_microstructure.limit_events.distinct_tickers",
        source_path=str(path),
        source_sha256=file_hash(path),
        event_years={ticker: frozenset(value) for ticker, value in years.items()},
    )


def load_universe_from_file(path: Path) -> Universe:
    """One ticker per line (``#`` comments and blanks ignored)."""
    path = Path(path)
    if not path.is_file():
        raise MinutesPlaneHeld("universe_file_is_absent")
    tickers: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped:
            tickers.append(_canonical_ticker(stripped))
    if not tickers:
        raise MinutesPlaneHeld("universe_file_is_empty")
    return Universe(
        tickers=tuple(sorted(set(tickers))),
        source="operator_supplied_ticker_file",
        source_path=str(path),
        source_sha256=file_hash(path),
    )


# --------------------------------------------------------------------------------------
# Request planning
# --------------------------------------------------------------------------------------


def _vendor_ticker(ticker: str) -> str:
    return ticker[:-3] + ".SH" if ticker.endswith(".SS") else ticker


def chunk_vendor_request(
    *, ticker: str, frequency: str, start: date, end: date
) -> dict[str, object]:
    """The exact ``stk_mins`` parameters for one chunk — token-free, hashable."""
    return {
        "api_name": BASE_ENDPOINT_CONTRACT.api_name,
        "fields": ",".join(BASE_VENDOR_FIELDS),
        "ts_code": _vendor_ticker(ticker),
        "freq": frequency,
        "start_date": f"{start.isoformat()} 00:00:00",
        "end_date": f"{end.isoformat()} 23:59:59",
    }


@dataclass(frozen=True)
class ChunkPlan:
    frequency: str
    ticker: str
    year: int
    chunk_index: int
    start_date: date
    end_date: date
    session_count: int
    projected_max_rows: int

    @property
    def vendor_request(self) -> dict[str, object]:
        return chunk_vendor_request(
            ticker=self.ticker,
            frequency=self.frequency,
            start=self.start_date,
            end=self.end_date,
        )

    @property
    def request_sha256(self) -> str:
        return canonical_hash(self.vendor_request)

    def as_dict(self) -> dict[str, object]:
        return {
            "frequency": self.frequency,
            "ticker": self.ticker,
            "year": self.year,
            "chunk_index": self.chunk_index,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "session_count": self.session_count,
            "projected_max_rows": self.projected_max_rows,
            "vendor_request": self.vendor_request,
            "request_sha256": self.request_sha256,
        }


@dataclass(frozen=True)
class PartitionPlan:
    frequency: str
    ticker: str
    year: int
    chunks: tuple[ChunkPlan, ...]
    status: str  # planned | skipped_fetched_clean | blocked_contradiction

    @property
    def session_count(self) -> int:
        return sum(chunk.session_count for chunk in self.chunks)

    @property
    def projected_max_rows(self) -> int:
        return sum(chunk.projected_max_rows for chunk in self.chunks)

    @property
    def request_sha256(self) -> str:
        return canonical_hash([chunk.vendor_request for chunk in self.chunks])

    @property
    def call_count(self) -> int:
        return 0 if self.status != "planned" else len(self.chunks)

    def as_dict(self) -> dict[str, object]:
        return {
            "frequency": self.frequency,
            "ticker": self.ticker,
            "year": self.year,
            "status": self.status,
            "chunk_count": len(self.chunks),
            "call_count": self.call_count,
            "session_count": self.session_count,
            "projected_max_rows": self.projected_max_rows,
            "request_sha256": self.request_sha256,
            "chunks": [chunk.as_dict() for chunk in self.chunks],
        }


def _client_throttle_seconds(api_name: str) -> float:
    """The SHARED client's own per-endpoint floor — read, never assumed.

    ``collectors/tushare_client`` sleeps at least this long between calls to one
    endpoint.  It stacks UNDER this plane's governor, so the honest pacing figure is
    ``min(governor ceiling, 60 / throttle)`` — quoting the 240/min ceiling alone would
    overstate throughput by ~40% at the client's current 0.35s default.
    """
    table = getattr(tc, "_THROTTLE", {})
    default = getattr(tc, "_DEFAULT_THROTTLE", 0.35)
    return float(table.get(api_name, default))


def rate_budget_receipt(calls_per_minute: int = RATE_CEILING_CALLS_PER_MINUTE) -> dict:
    throttle = _client_throttle_seconds(BASE_ENDPOINT_CONTRACT.api_name)
    client_floor = 60.0 / throttle if throttle > 0 else float("inf")
    return {
        "shared_premium_pool_calls_per_minute": SHARED_PREMIUM_POOL_CALLS_PER_MINUTE,
        "plane_governor_calls_per_minute": int(calls_per_minute),
        "client_throttle_seconds": throttle,
        "client_throttle_source": "collectors.tushare_client",
        "client_floor_calls_per_minute": round(client_floor, 4),
        "effective_calls_per_minute": round(
            min(float(calls_per_minute), client_floor), 4
        ),
        "concurrency": "sequential_only",
        "budget_note": (
            "the 300/min premium pool is shared with nightly incrementals and the "
            "running premium lanes; this plane never runs beside another bulk lane"
        ),
    }


def wall_clock_estimate(
    call_count: int, calls_per_minute: int = RATE_CEILING_CALLS_PER_MINUTE
) -> dict[str, object]:
    """Pacing FLOOR for a plan — explicitly not a latency-aware prediction."""
    budget = rate_budget_receipt(calls_per_minute)
    effective = float(budget["effective_calls_per_minute"])
    seconds = (call_count / effective * 60.0) if effective > 0 else float("inf")
    return {
        **budget,
        "call_count": int(call_count),
        "pacing_floor_seconds": round(seconds, 3),
        "pacing_floor_hours": round(seconds / 3600.0, 3),
        "nonclaim": (
            "pacing floor only; real wall clock is max(pacing floor, vendor latency x "
            "calls) and stk_mins latency is UNMEASURED until the TP-0 probe receipt"
        ),
    }


def _chunk_year(
    *, ticker: str, frequency: str, year: int, sessions: Sequence[date]
) -> tuple[ChunkPlan, ...]:
    per_chunk = sessions_per_chunk(frequency)
    per_session = max_bars_per_session(frequency)
    chunks: list[ChunkPlan] = []
    for index in range(0, len(sessions), per_chunk):
        window = sessions[index : index + per_chunk]
        chunks.append(
            ChunkPlan(
                frequency=frequency,
                ticker=ticker,
                year=year,
                chunk_index=len(chunks),
                start_date=window[0],
                end_date=window[-1],
                session_count=len(window),
                projected_max_rows=len(window) * per_session,
            )
        )
    return tuple(chunks)


@dataclass(frozen=True)
class BackfillPlan:
    frequency: str
    start_date: date
    end_date: date
    year_scope: str
    partitions: tuple[PartitionPlan, ...]
    universe_receipt: Mapping[str, object]
    calendar_receipt: Mapping[str, object]
    store_root: str
    all_years_call_count: int

    @property
    def call_count(self) -> int:
        return sum(partition.call_count for partition in self.partitions)

    @property
    def plan_sha256(self) -> str:
        return canonical_hash(
            [partition.request_sha256 for partition in self.partitions]
        )

    def summary(self) -> dict[str, object]:
        by_status: dict[str, int] = {}
        for partition in self.partitions:
            by_status[partition.status] = by_status.get(partition.status, 0) + 1
        planned = [p for p in self.partitions if p.status == "planned"]
        return {
            "schema_version": PLAN_SCHEMA_VERSION,
            "authority": AUTHORITY,
            "mode": "planned_no_network_no_write",
            "endpoint": BASE_ENDPOINT_CONTRACT.api_name,
            "endpoint_contract_sha256": BASE_ENDPOINT_CONTRACT.contract_hash,
            "frequency": self.frequency,
            "requested_range": {
                "start": self.start_date.isoformat(),
                "end": self.end_date.isoformat(),
            },
            "year_scope": self.year_scope,
            "store_root": self.store_root,
            "universe": dict(self.universe_receipt),
            "session_calendar": dict(self.calendar_receipt),
            "row_budget": {
                "documented_row_cap": MAX_ROWS_PER_RESPONSE,
                "max_bars_per_session": max_bars_per_session(self.frequency),
                "sessions_per_chunk": sessions_per_chunk(self.frequency),
                "projected_max_rows": sum(p.projected_max_rows for p in planned),
            },
            "partition_counts": {
                "total": len(self.partitions),
                **by_status,
            },
            "ticker_count": len({p.ticker for p in self.partitions}),
            "session_observations": sum(p.session_count for p in planned),
            "call_count": self.call_count,
            "call_count_if_all_years": self.all_years_call_count,
            "wall_clock": wall_clock_estimate(self.call_count),
            "corporate_action_basis": dict(CORPORATE_ACTION_BASIS),
            "plan_sha256": self.plan_sha256,
            "nonclaims": list(PLANE_NONCLAIMS),
        }

    def as_dict(self, *, include_chunks: bool = False) -> dict[str, object]:
        payload = self.summary()
        if include_chunks:
            payload["partitions"] = [p.as_dict() for p in self.partitions]
        return payload


def plan_backfill(
    *,
    universe: Universe,
    calendar: SessionCalendar,
    frequency: str,
    start: date,
    end: date,
    store_root: Path = DEFAULT_STORE_ROOT,
    year_scope: str = "event-years",
    manifest: pd.DataFrame | None = None,
) -> BackfillPlan:
    """Plan every vendor call the backfill would make.  No network, no write.

    ``year_scope``:

    * ``event-years`` (default) — a ticker-year is planned only when the universe
      reports a limit event for that ticker in that year.  This is the CN limit
      program's actual battery need and is ~an order of magnitude cheaper.
    * ``all-years`` — every ticker crossed with every year in the range.

    Resume: a partition already recorded ``fetched`` in ``manifest`` AND present on
    disk with a receipt that recomputes is ``skipped_fetched_clean`` and costs zero
    calls.  A partition recorded ``contradiction`` is ``blocked_contradiction``: it
    is never silently re-fetched over first evidence.
    """
    if frequency not in ALLOWED_FREQUENCIES:
        raise MinutesPlaneHeld("unsupported_stk_mins_frequency")
    if year_scope not in {"event-years", "all-years"}:
        raise MinutesPlaneHeld("unsupported_year_scope")
    if end < start:
        raise MinutesPlaneHeld("requested_range_is_inverted")
    if year_scope == "event-years" and not universe.event_years:
        raise MinutesPlaneHeld("universe_has_no_event_years_use_all_years")

    root = Path(store_root)
    status_by_key = _manifest_status_index(manifest)
    sessions_by_year: dict[int, list[date]] = {}
    for day in calendar.between(start, end):
        sessions_by_year.setdefault(day.year, []).append(day)

    partitions: list[PartitionPlan] = []
    all_years_calls = 0
    for ticker in universe.tickers:
        wanted = universe.event_years.get(ticker, frozenset())
        for year in sorted(sessions_by_year):
            sessions = sessions_by_year[year]
            chunks = _chunk_year(
                ticker=ticker, frequency=frequency, year=year, sessions=sessions
            )
            all_years_calls += len(chunks)
            if year_scope == "event-years" and year not in wanted:
                continue
            recorded = status_by_key.get((frequency, ticker, year))
            if recorded == "contradiction":
                status = "blocked_contradiction"
            elif recorded == "fetched" and _partition_is_on_disk(
                root, frequency=frequency, ticker=ticker, year=year
            ):
                status = "skipped_fetched_clean"
            else:
                status = "planned"
            partitions.append(
                PartitionPlan(
                    frequency=frequency,
                    ticker=ticker,
                    year=year,
                    chunks=chunks,
                    status=status,
                )
            )
    return BackfillPlan(
        frequency=frequency,
        start_date=start,
        end_date=end,
        year_scope=year_scope,
        partitions=tuple(partitions),
        universe_receipt=universe.receipt(),
        calendar_receipt=calendar.receipt(),
        store_root=str(root),
        all_years_call_count=all_years_calls,
    )


# --------------------------------------------------------------------------------------
# Rate governor
# --------------------------------------------------------------------------------------


class RateGovernor:
    """Sliding-window call governor, hard-capped at ``calls_per_minute``.

    Sequential execution only — this plane never runs two callers concurrently, so a
    plain deque of admitted call stamps is the whole mechanism.  ``clock``/``sleeper``
    are injectable so pacing is provable without wall-clock tests.
    """

    def __init__(
        self,
        calls_per_minute: int = RATE_CEILING_CALLS_PER_MINUTE,
        *,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = _time.monotonic,
        sleeper: Callable[[float], None] = _time.sleep,
    ) -> None:
        if calls_per_minute < 1:
            raise MinutesPlaneHeld("rate_governor_requires_a_positive_ceiling")
        if calls_per_minute > SHARED_PREMIUM_POOL_CALLS_PER_MINUTE:
            raise MinutesPlaneHeld("rate_governor_exceeds_the_shared_premium_pool")
        if calls_per_minute > RATE_CEILING_CALLS_PER_MINUTE:
            raise MinutesPlaneHeld("rate_governor_exceeds_the_plane_ceiling")
        self.calls_per_minute = int(calls_per_minute)
        self.window_seconds = float(window_seconds)
        self._clock = clock
        self._sleeper = sleeper
        self._stamps: deque[float] = deque()
        self.total_calls = 0
        self.total_sleep_seconds = 0.0

    def acquire(self) -> float:
        """Block until one more call fits the window; return seconds slept."""
        slept = 0.0
        now = self._clock()
        while self._stamps and now - self._stamps[0] >= self.window_seconds:
            self._stamps.popleft()
        if len(self._stamps) >= self.calls_per_minute:
            wait = self.window_seconds - (now - self._stamps[0])
            if wait > 0:
                self._sleeper(wait)
                slept = wait
                self.total_sleep_seconds += wait
            now = self._clock()
            while self._stamps and now - self._stamps[0] >= self.window_seconds:
                self._stamps.popleft()
        self._stamps.append(now)
        self.total_calls += 1
        return slept

    def receipt(self) -> dict[str, object]:
        return {
            "calls_per_minute": self.calls_per_minute,
            "window_seconds": self.window_seconds,
            "total_calls": self.total_calls,
            "total_sleep_seconds": round(self.total_sleep_seconds, 6),
            "concurrency": "sequential_only",
        }


# --------------------------------------------------------------------------------------
# Normalized partition schema (a DECLARED extension of the pilot contract)
# --------------------------------------------------------------------------------------

_EXTENSION_FIELDS: tuple[addons.SchemaField, ...] = (
    addons.SchemaField("trade_time_utc", "string", False, "ISO-8601 UTC"),
    addons.SchemaField("open_cents", "int64", False, "CNY cents (exact)"),
    addons.SchemaField("high_cents", "int64", False, "CNY cents (exact)"),
    addons.SchemaField("low_cents", "int64", False, "CNY cents (exact)"),
    addons.SchemaField("close_cents", "int64", False, "CNY cents (exact)"),
    addons.SchemaField("bar_class", "string", False, " | ".join(BAR_CLASSES)),
)

#: Base pilot fields verbatim + this plane's declared extensions.  The float64 price
#: columns are the base contract's; the ``*_cents`` columns are the EXACT authority —
#: never compare A-share prices as floats.
PARTITION_FIELDS: tuple[addons.SchemaField, ...] = (
    BASE_ENDPOINT_CONTRACT.output_schema + _EXTENSION_FIELDS
)

SCHEMA_DERIVATION: Mapping[str, object] = {
    "base_endpoint": BASE_ENDPOINT_CONTRACT.api_name,
    "base_contract_sha256": BASE_ENDPOINT_CONTRACT.contract_hash,
    "base_module": "collectors.tushare_addons",
    "relationship": "declared_superset_never_a_silent_fork",
    "extension_fields": [f.name for f in _EXTENSION_FIELDS],
    "extension_rationale": (
        "UTC companion stamp for cross-market joins; integer-cent prices so joins "
        "against the spine's cent plane are exact; bar_class so zero-volume rows are "
        "retained with their cause visible"
    ),
}


def _pa_type(name: str) -> pa.DataType:
    if name == "string":
        return pa.string()
    if name == "float64":
        return pa.float64()
    if name == "int64":
        return pa.int64()
    raise AssertionError(f"unsupported tracked Arrow type: {name}")


def schema_descriptor() -> dict[str, object]:
    return {
        "schema_version": PARTITION_SCHEMA_VERSION,
        "fields": [f.as_dict() for f in PARTITION_FIELDS],
        "derivation": dict(SCHEMA_DERIVATION),
    }


def arrow_schema() -> pa.Schema:
    descriptor = schema_descriptor()
    return pa.schema(
        [
            pa.field(f.name, _pa_type(f.arrow_type), nullable=f.nullable)
            for f in PARTITION_FIELDS
        ],
        metadata={
            b"partition_schema_version": PARTITION_SCHEMA_VERSION.encode(),
            b"endpoint": BASE_ENDPOINT_CONTRACT.api_name.encode(),
            b"base_contract_sha256": BASE_ENDPOINT_CONTRACT.contract_hash.encode(),
            b"schema_sha256": canonical_hash(descriptor).encode(),
        },
    )


def classify_bar(
    *,
    volume: float,
    amount: float,
    open_cents: int,
    high_cents: int,
    low_cents: int,
    close_cents: int,
) -> str:
    """Retain every bar; name WHY a bar carries no volume.  Never drop, never trust.

    A zero-volume bar in this tape is usually a suspended or untraded interval whose
    prices are stale carry-forwards.  Attributing it to a suspension requires the
    spine's ``suspend_d`` plane and is deliberately NOT done here — the class states
    what was observed, not what caused it.
    """
    if volume < 0 or amount < 0:
        raise MinutesPlaneIntegrityError("minute volume/amount is negative")
    if volume == 0:
        if amount != 0:
            return BAR_CLASS_ZERO_VOLUME_INCONSISTENT
        flat = open_cents == high_cents == low_cents == close_cents
        return (
            BAR_CLASS_ZERO_VOLUME_FLAT if flat else BAR_CLASS_ZERO_VOLUME_INCONSISTENT
        )
    if amount == 0:
        return BAR_CLASS_VOLUME_WITHOUT_AMOUNT
    return BAR_CLASS_TRADED


def normalize_minute_rows(
    frame: pd.DataFrame, *, ticker: str, frequency: str, year: int
) -> list[dict[str, object]]:
    """Vendor rows -> normalized partition records for ONE ticker-year.

    Every check is fail-closed: unexpected columns, a response that reached the row
    cap (presumed truncated), an off-session stamp, an out-of-year row, an off-tick
    price, incoherent OHLC, or a duplicate exact bar all raise.
    """
    missing = sorted(set(BASE_VENDOR_FIELDS) - set(frame.columns))
    extra = sorted(set(frame.columns) - set(BASE_VENDOR_FIELDS))
    if missing or extra or len(frame.columns) != len(set(frame.columns)):
        raise MinutesPlaneIntegrityError(
            "stk_mins response schema differs from the documented fields"
        )
    records: list[dict[str, object]] = []
    for raw in frame.to_dict(orient="records"):
        row_ticker = _canonical_ticker(raw["ts_code"])
        if row_ticker != ticker:
            raise MinutesPlaneIntegrityError("vendor row escaped the requested ticker")
        try:
            stamp = pd.Timestamp(raw["trade_time"])
        except Exception as exc:
            raise MinutesPlaneIntegrityError("minute trade_time is invalid") from exc
        if pd.isna(stamp):
            raise MinutesPlaneIntegrityError("minute trade_time is null")
        stamp = (
            stamp.tz_localize(SHANGHAI)
            if stamp.tzinfo is None
            else stamp.tz_convert(SHANGHAI)
        )
        if stamp.second or stamp.microsecond or stamp.nanosecond:
            raise MinutesPlaneIntegrityError("minute bar is not on an exact minute")
        if stamp.year != year:
            raise MinutesPlaneIntegrityError("minute bar escaped the partition year")
        segment = classify_session_segment(stamp.time().replace(tzinfo=None))
        open_cents = quote_price_cents(raw["open"], field_name="stk_mins.open")
        high_cents = quote_price_cents(raw["high"], field_name="stk_mins.high")
        low_cents = quote_price_cents(raw["low"], field_name="stk_mins.low")
        close_cents = quote_price_cents(raw["close"], field_name="stk_mins.close")
        if (
            high_cents < max(open_cents, close_cents)
            or low_cents > min(open_cents, close_cents)
            or low_cents > high_cents
        ):
            raise MinutesPlaneIntegrityError("minute OHLC values are incoherent")
        volume = _finite_number(raw["vol"], field_name="stk_mins.vol")
        amount = _finite_number(raw["amount"], field_name="stk_mins.amount")
        records.append(
            {
                "schema_version": PARTITION_SCHEMA_VERSION,
                "authority": AUTHORITY,
                "trade_date": stamp.date().isoformat(),
                "ticker": ticker,
                "frequency": frequency,
                "trade_time": stamp.isoformat(),
                "session_segment": segment,
                "open": float(Decimal(open_cents) / A_SHARE_PRICE_SCALE),
                "close": float(Decimal(close_cents) / A_SHARE_PRICE_SCALE),
                "high": float(Decimal(high_cents) / A_SHARE_PRICE_SCALE),
                "low": float(Decimal(low_cents) / A_SHARE_PRICE_SCALE),
                "volume": volume,
                "amount": amount,
                "trade_time_utc": stamp.tz_convert(timezone.utc).isoformat(),
                "open_cents": open_cents,
                "high_cents": high_cents,
                "low_cents": low_cents,
                "close_cents": close_cents,
                "bar_class": classify_bar(
                    volume=volume,
                    amount=amount,
                    open_cents=open_cents,
                    high_cents=high_cents,
                    low_cents=low_cents,
                    close_cents=close_cents,
                ),
            }
        )
    records.sort(key=lambda row: str(row["trade_time"]))
    stamps = [row["trade_time"] for row in records]
    if len(stamps) != len(set(stamps)):
        raise MinutesPlaneIntegrityError("minute response has duplicate exact bars")
    return records


# --------------------------------------------------------------------------------------
# Keep-first immutable store
# --------------------------------------------------------------------------------------


def partition_path(root: Path, *, frequency: str, ticker: str, year: int) -> Path:
    """``by_frequency=<freq>/by_ticker=<ticker>/year=YYYY``.

    ``frequency`` and ``ticker`` are also typed COLUMNS inside the Parquet file, so
    their directory keys carry the ``by_`` prefix that stops Hive partition discovery
    from colliding with them (the addons pilot's convention).  ``year`` is not a
    column, so it stays a plain, discoverable Hive key.
    """
    return (
        Path(root)
        / f"by_frequency={frequency}"
        / f"by_ticker={ticker}"
        / f"year={year:04d}"
    )


def _partition_is_on_disk(
    root: Path, *, frequency: str, ticker: str, year: int
) -> bool:
    destination = partition_path(root, frequency=frequency, ticker=ticker, year=year)
    return (destination / "part.parquet").is_file() and (
        destination / "receipt.json"
    ).is_file()


def partition_identity(*, frequency: str, ticker: str, year: int) -> dict[str, object]:
    return {"frequency": frequency, "ticker": ticker, "year": int(year)}


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def load_receipt(path: Path) -> dict[str, object]:
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MinutesPlaneIntegrityError("partition receipt is unreadable") from exc
    if not isinstance(receipt, dict):
        raise MinutesPlaneIntegrityError("partition receipt is not an object")
    declared = receipt.get("receipt_sha256")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if not _is_sha256(declared) or canonical_hash(body) != declared:
        raise MinutesPlaneIntegrityError("partition receipt hash does not recompute")
    return receipt


def _bar_class_counts(records: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts = {name: 0 for name in BAR_CLASSES}
    for row in records:
        counts[str(row["bar_class"])] += 1
    return counts


def _segment_counts(records: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts = {SESSION_SEGMENT_REGULAR: 0, SESSION_SEGMENT_POST_CLOSE: 0}
    for row in records:
        counts[str(row["session_segment"])] += 1
    return counts


def _partition_receipt_body(
    *,
    identity: Mapping[str, object],
    chunks: Sequence[Mapping[str, object]],
    calendar_receipt: Mapping[str, object],
    tp0_probe: Mapping[str, object],
    governor_receipt: Mapping[str, object],
    observed_at: datetime,
    records: Sequence[Mapping[str, object]],
    data_hash: str,
    parquet_hash: str,
    source_rows_hash: str,
) -> dict[str, object]:
    descriptor = schema_descriptor()
    trade_dates = sorted({str(row["trade_date"]) for row in records})
    return {
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "authority": AUTHORITY,
        "plane": "tushare_minutes_bulk_historical",
        "base_endpoint_contract": {
            **BASE_ENDPOINT_CONTRACT.contract_payload(),
            "contract_sha256": BASE_ENDPOINT_CONTRACT.contract_hash,
        },
        "schema_receipt": {**descriptor, "schema_sha256": canonical_hash(descriptor)},
        "corporate_action_basis": dict(CORPORATE_ACTION_BASIS),
        "partition_identity": dict(identity),
        "request_receipt": {
            "chunks": [dict(chunk) for chunk in chunks],
            "chunk_count": len(chunks),
            "request_sha256": canonical_hash([dict(chunk) for chunk in chunks]),
            "documented_row_cap": MAX_ROWS_PER_RESPONSE,
            "cap_policy": "a_response_at_the_cap_is_refused_as_possibly_truncated",
            "governor": dict(governor_receipt),
        },
        "session_calendar_receipt": dict(calendar_receipt),
        "tp0_probe_reference": dict(tp0_probe),
        "access_observation_receipt": {
            "observation": "access_observed_at_request_time",
            "observation_basis": "valid_rows_returned_for_these_exact_chunk_requests",
            "observed_at_asia_shanghai": observed_at.astimezone(SHANGHAI).isoformat(),
            "observed_at_utc": observed_at.astimezone(timezone.utc).isoformat(),
            "nonclaims": [
                "observation_is_scoped_to_this_request_time_not_future_access",
                "valid_rows_do_not_certify_vendor_side_completeness_for_this_range",
            ],
        },
        "data_receipt": {
            "row_count": len(records),
            "session_count_observed": len(trade_dates),
            "first_session": trade_dates[0] if trade_dates else None,
            "last_session": trade_dates[-1] if trade_dates else None,
            "first_bar": str(records[0]["trade_time"]) if records else None,
            "last_bar": str(records[-1]["trade_time"]) if records else None,
            "bar_class_counts": _bar_class_counts(records),
            "session_segment_counts": _segment_counts(records),
            "canonical_vendor_rows_sha256": source_rows_hash,
            "normalized_rows_sha256": data_hash,
            "parquet_sha256": parquet_hash,
        },
        "reconciliation": {
            "gate": "sampled_daily_ohlc_vs_minute_aggregate",
            "status": "declared_runs_in_verify_mode_over_the_store",
            "required_basis": DAILY_REFERENCE_BASIS,
            "forbidden_bases": sorted(FORBIDDEN_DAILY_REFERENCE_BASES),
        },
        "runtime_receipt": {
            "python": ".".join(str(value) for value in sys.version_info[:3]),
            "pandas": pd.__version__,
            "pyarrow": pa.__version__,
            "plane_source_sha256": file_hash(Path(__file__)),
            "addons_source_sha256": file_hash(Path(addons.__file__)),
            "tushare_client_source_sha256": file_hash(Path(tc.__file__)),
            "github_repository": os.environ.get("GITHUB_REPOSITORY"),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "nonclaim": "environment_fields_are_execution_context_not_signed_identity",
        },
        "nonclaims": list(PLANE_NONCLAIMS),
    }


@dataclass(frozen=True)
class PartitionResult:
    status: str  # written | unchanged
    frequency: str
    ticker: str
    year: int
    partition_path: str
    row_count: int
    data_hash: str
    receipt_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "frequency": self.frequency,
            "ticker": self.ticker,
            "year": self.year,
            "partition_path": self.partition_path,
            "row_count": self.row_count,
            "data_hash": self.data_hash,
            "receipt_hash": self.receipt_hash,
        }


def _partition_receipt_invariants(
    destination: Path, identity: Mapping[str, object]
) -> dict[str, object]:
    """Bundle shape + receipt invariants shared by the install and verify paths."""
    if destination.is_symlink() or not destination.is_dir():
        raise MinutesPlaneIntegrityError("partition path exists but is not a directory")
    children = list(destination.iterdir())
    if any(child.is_symlink() for child in children):
        raise MinutesPlaneIntegrityError("partition bundle contains a symlink")
    if {child.name for child in children} != {"part.parquet", "receipt.json"}:
        raise MinutesPlaneIntegrityError(
            "partition bundle is partial or has unknown files"
        )
    receipt = load_receipt(destination / "receipt.json")
    if (
        receipt.get("receipt_schema_version") != RECEIPT_SCHEMA_VERSION
        or receipt.get("authority") != AUTHORITY
    ):
        raise MinutesPlaneIntegrityError("partition receipt authority changed")
    if receipt.get("partition_identity") != dict(identity):
        raise MinutesPlaneIntegrityError("partition receipt identity changed")
    if receipt.get("corporate_action_basis") != dict(CORPORATE_ACTION_BASIS):
        raise MinutesPlaneIntegrityError("partition corporate-action basis changed")
    expected_contract = {
        **BASE_ENDPOINT_CONTRACT.contract_payload(),
        "contract_sha256": BASE_ENDPOINT_CONTRACT.contract_hash,
    }
    if receipt.get("base_endpoint_contract") != expected_contract:
        raise MinutesPlaneIntegrityError("partition base endpoint contract changed")
    if not isinstance(receipt.get("data_receipt"), dict):
        raise MinutesPlaneIntegrityError("partition data receipt is malformed")
    if file_hash(destination / "part.parquet") != receipt["data_receipt"].get(
        "parquet_sha256"
    ):
        raise MinutesPlaneIntegrityError("partition parquet bytes do not match receipt")
    return receipt


def _validate_existing_partition(
    destination: Path,
    *,
    identity: Mapping[str, object],
    incoming_data_hash: str,
    incoming_source_rows_hash: str,
) -> dict[str, object]:
    """Keep-first: an identical rerun is a no-op; a revision is a loud contradiction."""
    receipt = _partition_receipt_invariants(destination, identity)
    data_receipt = receipt["data_receipt"]
    if data_receipt.get("normalized_rows_sha256") != incoming_data_hash:
        raise MinutesPlaneIntegrityError(
            "vendor rows were REVISED for an already-witnessed partition; first "
            "evidence is kept and nothing was overwritten"
        )
    if data_receipt.get("canonical_vendor_rows_sha256") != incoming_source_rows_hash:
        raise MinutesPlaneIntegrityError(
            "pre-normalization vendor rows changed for an already-witnessed partition"
        )
    return receipt


def verify_partition_bundle(
    destination: Path, *, identity: Mapping[str, object]
) -> list[dict[str, object]]:
    """Re-derive an installed partition from its own bytes; return its records.

    Deliberately does NOT re-assert the pre-normalization vendor digest: that value
    cannot be recomputed without the original vendor response, and comparing the
    receipt's copy against itself would be a check that cannot fail.  What IS
    recomputed here — the Parquet bytes, the receipt digest, and the normalized-row
    digest rebuilt from the stored rows — can each fail on real corruption.
    """
    destination = Path(destination)
    receipt = _partition_receipt_invariants(destination, identity)
    records = read_partition_records(destination)
    if canonical_hash(records) != receipt["data_receipt"].get("normalized_rows_sha256"):
        raise MinutesPlaneIntegrityError(
            "stored rows do not rebuild the receipt's normalized-row digest"
        )
    if len(records) != receipt["data_receipt"].get("row_count"):
        raise MinutesPlaneIntegrityError("stored row count does not match the receipt")
    return records


def install_partition(
    *,
    root: Path,
    frequency: str,
    ticker: str,
    year: int,
    records: Sequence[Mapping[str, object]],
    chunks: Sequence[Mapping[str, object]],
    calendar_receipt: Mapping[str, object],
    tp0_probe: Mapping[str, object],
    governor_receipt: Mapping[str, object],
    source_rows_hash: str,
    observed_at: datetime,
) -> PartitionResult:
    """Install one immutable ticker-year bundle, or prove the existing one identical."""
    identity = partition_identity(frequency=frequency, ticker=ticker, year=year)
    destination = partition_path(root, frequency=frequency, ticker=ticker, year=year)
    data_hash = canonical_hash([dict(row) for row in records])
    if destination.exists():
        receipt = _validate_existing_partition(
            destination,
            identity=identity,
            incoming_data_hash=data_hash,
            incoming_source_rows_hash=source_rows_hash,
        )
        return PartitionResult(
            status="unchanged",
            frequency=frequency,
            ticker=ticker,
            year=year,
            partition_path=str(destination),
            row_count=len(records),
            data_hash=data_hash,
            receipt_hash=str(receipt["receipt_sha256"]),
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=".tushare-minutes-stage-", dir=destination.parent)
    )
    try:
        parquet_path = stage / "part.parquet"
        table = pa.Table.from_pylist(
            [dict(row) for row in records], schema=arrow_schema()
        )
        pq.write_table(
            table,
            parquet_path,
            compression="zstd",
            use_dictionary=False,
            write_statistics=True,
        )
        parquet_hash = file_hash(parquet_path)
        receipt = _partition_receipt_body(
            identity=identity,
            chunks=chunks,
            calendar_receipt=calendar_receipt,
            tp0_probe=tp0_probe,
            governor_receipt=governor_receipt,
            observed_at=observed_at,
            records=records,
            data_hash=data_hash,
            parquet_hash=parquet_hash,
            source_rows_hash=source_rows_hash,
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
                identity=identity,
                incoming_data_hash=data_hash,
                incoming_source_rows_hash=source_rows_hash,
            )
            return PartitionResult(
                status="unchanged",
                frequency=frequency,
                ticker=ticker,
                year=year,
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
        return PartitionResult(
            status="written",
            frequency=frequency,
            ticker=ticker,
            year=year,
            partition_path=str(destination),
            row_count=len(records),
            data_hash=data_hash,
            receipt_hash=str(receipt["receipt_sha256"]),
        )
    finally:
        if stage.exists():
            shutil.rmtree(stage)


# --------------------------------------------------------------------------------------
# Coverage ledger (manifest/coverage.parquet + manifest/coverage_receipt.json)
# --------------------------------------------------------------------------------------

COVERAGE_STATUSES = ("planned", "fetched", "contradiction")

COVERAGE_SCHEMA = pa.schema(
    [
        pa.field("schema_version", pa.string(), nullable=False),
        pa.field("frequency", pa.string(), nullable=False),
        pa.field("ticker", pa.string(), nullable=False),
        pa.field("year", pa.int32(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
        pa.field("request_sha256", pa.string(), nullable=False),
        pa.field("chunk_count", pa.int32(), nullable=False),
        pa.field("planned_session_count", pa.int32(), nullable=False),
        pa.field("row_count", pa.int64(), nullable=True),
        pa.field("observed_session_count", pa.int32(), nullable=True),
        pa.field("first_bar", pa.string(), nullable=True),
        pa.field("last_bar", pa.string(), nullable=True),
        pa.field("zero_volume_rows", pa.int64(), nullable=True),
        pa.field("inconsistent_rows", pa.int64(), nullable=True),
        pa.field("post_close_rows", pa.int64(), nullable=True),
        pa.field("receipt_sha256", pa.string(), nullable=True),
        pa.field("partition_path", pa.string(), nullable=False),
        pa.field("observed_at_utc", pa.string(), nullable=True),
        pa.field("contradiction_reason", pa.string(), nullable=True),
    ]
)
COVERAGE_COLUMNS: tuple[str, ...] = tuple(COVERAGE_SCHEMA.names)


def manifest_dir(root: Path) -> Path:
    return Path(root) / "manifest"


def coverage_path(root: Path) -> Path:
    return manifest_dir(root) / "coverage.parquet"


def coverage_receipt_path(root: Path) -> Path:
    return manifest_dir(root) / "coverage_receipt.json"


def read_manifest(root: Path) -> pd.DataFrame:
    """The coverage ledger, or an empty typed frame when the store is new."""
    path = coverage_path(root)
    if not path.is_file():
        return pd.DataFrame(
            {name: pd.Series(dtype="object") for name in COVERAGE_COLUMNS}
        )
    frame = pd.read_parquet(path)
    missing = sorted(set(COVERAGE_COLUMNS) - set(frame.columns))
    if missing:
        raise MinutesPlaneIntegrityError(f"coverage ledger lacks columns: {missing}")
    return frame


def _manifest_status_index(
    manifest: pd.DataFrame | None,
) -> dict[tuple[str, str, int], str]:
    if manifest is None or manifest.empty:
        return {}
    index: dict[tuple[str, str, int], str] = {}
    for row in manifest.to_dict(orient="records"):
        index[(str(row["frequency"]), str(row["ticker"]), int(row["year"]))] = str(
            row["status"]
        )
    return index


def coverage_row(
    *,
    frequency: str,
    ticker: str,
    year: int,
    status: str,
    request_sha256: str,
    chunk_count: int,
    planned_session_count: int,
    partition_path_value: str,
    row_count: int | None = None,
    observed_session_count: int | None = None,
    first_bar: str | None = None,
    last_bar: str | None = None,
    zero_volume_rows: int | None = None,
    inconsistent_rows: int | None = None,
    post_close_rows: int | None = None,
    receipt_sha256: str | None = None,
    observed_at_utc: str | None = None,
    contradiction_reason: str | None = None,
) -> dict[str, object]:
    if status not in COVERAGE_STATUSES:
        raise MinutesPlaneIntegrityError(f"unsupported coverage status: {status}")
    return {
        "schema_version": COVERAGE_ROW_SCHEMA_VERSION,
        "frequency": frequency,
        "ticker": ticker,
        "year": int(year),
        "status": status,
        "request_sha256": request_sha256,
        "chunk_count": int(chunk_count),
        "planned_session_count": int(planned_session_count),
        "row_count": row_count,
        "observed_session_count": observed_session_count,
        "first_bar": first_bar,
        "last_bar": last_bar,
        "zero_volume_rows": zero_volume_rows,
        "inconsistent_rows": inconsistent_rows,
        "post_close_rows": post_close_rows,
        "receipt_sha256": receipt_sha256,
        "partition_path": partition_path_value,
        "observed_at_utc": observed_at_utc,
        "contradiction_reason": contradiction_reason,
    }


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_manifest(
    root: Path,
    rows: Sequence[Mapping[str, object]],
    *,
    plan_summary: Mapping[str, object] | None = None,
    reconciliation: Mapping[str, object] | None = None,
    tp0_probe: Mapping[str, object] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Write ``coverage.parquet`` + its versioned JSON manifest; return the manifest."""
    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: (str(row["frequency"]), str(row["ticker"]), int(row["year"])),
    )
    keys = [(row["frequency"], row["ticker"], row["year"]) for row in ordered]
    if len(keys) != len(set(keys)):
        raise MinutesPlaneIntegrityError("coverage ledger has duplicate partition keys")
    table = pa.Table.from_pylist(ordered, schema=COVERAGE_SCHEMA)
    path = coverage_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".coverage.")
    os.close(handle)
    try:
        pq.write_table(
            table,
            temporary,
            compression="zstd",
            use_dictionary=False,
            write_statistics=True,
        )
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

    status_counts: dict[str, int] = {}
    for row in ordered:
        status_counts[str(row["status"])] = status_counts.get(str(row["status"]), 0) + 1
    stamp = generated_at or datetime.now(timezone.utc)
    manifest: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": stamp.astimezone(timezone.utc).isoformat(),
        "authority": AUTHORITY,
        "source": "tushare_pro",
        "endpoint": BASE_ENDPOINT_CONTRACT.api_name,
        "store_root": str(root),
        "provenance": {
            "plane_source_sha256": file_hash(Path(__file__)),
            "base_contract_sha256": BASE_ENDPOINT_CONTRACT.contract_hash,
            "partition_schema_sha256": canonical_hash(schema_descriptor()),
            "coverage_row_schema_version": COVERAGE_ROW_SCHEMA_VERSION,
        },
        "rate_budget": rate_budget_receipt(),
        "corporate_action_basis": dict(CORPORATE_ACTION_BASIS),
        "tp0_probe_reference": dict(tp0_probe) if tp0_probe else None,
        "plan_summary": dict(plan_summary) if plan_summary else None,
        "coverage": {
            "artifact": {
                "path": str(path),
                "sha256": file_hash(path),
                "bytes": path.stat().st_size,
                "rows": len(ordered),
            },
            "partition_count": len(ordered),
            "status_counts": status_counts,
            "row_count": sum(int(row["row_count"] or 0) for row in ordered),
            "semantic_sha256": canonical_hash(ordered),
        },
        "reconciliation": dict(reconciliation)
        if reconciliation
        else {
            "status": "not_run",
            "note": "run scripts/backfill_tushare_minutes.py --verify",
        },
        "nonclaims": list(PLANE_NONCLAIMS),
    }
    manifest["manifest_sha256"] = canonical_hash(manifest)
    _atomic_write_bytes(coverage_receipt_path(root), _json_bytes(manifest) + b"\n")
    return manifest


# --------------------------------------------------------------------------------------
# Sampled reconciliation gate: minute aggregate vs the spine's NOMINAL daily bar
# --------------------------------------------------------------------------------------

DAILY_REFERENCE_COLUMNS = (
    "trade_date",
    "ticker",
    "open_cents",
    "high_cents",
    "low_cents",
    "close_cents",
    "volume_lots",
    "amount_cny_thousands",
)


def aggregate_regular_window(
    records: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    """Aggregate ONE session's regular-window minute bars into a day bar.

    The post-close window is excluded: it is not continuous-auction tape, and folding
    it into a daily comparison would put prints the daily bar may or may not contain
    on the wrong side of the gate.
    """
    window = [
        row for row in records if row["session_segment"] == SESSION_SEGMENT_REGULAR
    ]
    if not window:
        return None
    ordered = sorted(window, key=lambda row: str(row["trade_time"]))
    traded = [row for row in ordered if row["bar_class"] != BAR_CLASS_ZERO_VOLUME_FLAT]
    price_rows = traded or ordered
    return {
        "open_cents": int(price_rows[0]["open_cents"]),
        "close_cents": int(ordered[-1]["close_cents"]),
        "high_cents": max(int(row["high_cents"]) for row in price_rows),
        "low_cents": min(int(row["low_cents"]) for row in price_rows),
        "volume_shares": sum(float(row["volume"]) for row in ordered),
        "amount_cny": sum(float(row["amount"]) for row in ordered),
        "bar_count": len(ordered),
    }


def reconcile_session(
    aggregate: Mapping[str, object], daily: Mapping[str, object]
) -> dict[str, object]:
    """Compare one minute aggregate against one NOMINAL daily bar.

    Required (a failure is a real defect):

    * ``close_exact`` — the last regular-window bar closes at the session close.
    * ``high_within`` / ``low_within`` — the minute tape cannot print outside the
      day's published range.
    * ``volume_within`` / ``amount_within`` — the regular window cannot exceed the
      whole day (which also carries the auctions and the post-close window).

    Reported, never required:

    * ``open_exact`` — vendors differ on whether the opening call auction is stamped
      into the first minute bar.  Failing a gate on an unpinned vendor convention
      would manufacture a defect rate that means nothing.
    """
    daily_open = int(daily["open_cents"])
    daily_high = int(daily["high_cents"])
    daily_low = int(daily["low_cents"])
    daily_close = int(daily["close_cents"])
    daily_volume_shares = float(daily["volume_lots"]) * SHARES_PER_LOT
    daily_amount_cny = float(daily["amount_cny_thousands"]) * CNY_PER_AMOUNT_UNIT
    minute_volume = float(aggregate["volume_shares"])
    minute_amount = float(aggregate["amount_cny"])
    checks = {
        "close_exact": int(aggregate["close_cents"]) == daily_close,
        "high_within": int(aggregate["high_cents"]) <= daily_high,
        "low_within": int(aggregate["low_cents"]) >= daily_low,
        "volume_within": minute_volume <= daily_volume_shares * (1.0 + 1e-9),
        "amount_within": minute_amount <= daily_amount_cny * (1.0 + 1e-9),
    }
    reported = {
        "open_exact": int(aggregate["open_cents"]) == daily_open,
        "minute_volume_share_of_daily": (
            round(minute_volume / daily_volume_shares, 6)
            if daily_volume_shares > 0
            else None
        ),
        "minute_amount_share_of_daily": (
            round(minute_amount / daily_amount_cny, 6) if daily_amount_cny > 0 else None
        ),
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    return {
        "required_checks": checks,
        "reported_checks": reported,
        "failed_checks": failed,
        "passed": not failed,
    }


def _sample_keys(
    keys: Sequence[tuple[str, str]], sample_size: int, *, seed: str
) -> list[tuple[str, str]]:
    """Deterministic, reproducible sample — the digest ordering IS the receipt."""
    scored = sorted(
        keys,
        key=lambda key: hashlib.sha256(
            f"{seed}|{key[0]}|{key[1]}".encode()
        ).hexdigest(),
    )
    return scored[: max(0, sample_size)]


def load_daily_reference(
    store: Path = DEFAULT_SPINE_STORE, *, years: Iterable[int] | None = None
) -> pd.DataFrame:
    """Nominal daily bars from the full-A spine.  The ONLY permitted anchor."""
    root = Path(store) / "daily"
    if not root.is_dir():
        raise MinutesPlaneHeld("spine_daily_plane_is_absent")
    wanted = set(years) if years is not None else None
    frames: list[pd.DataFrame] = []
    for path in sorted(root.glob("year=*/month=*/part.parquet")):
        year_key = path.parent.parent.name.split("=", 1)[-1]
        if wanted is not None and (
            not year_key.isdigit() or int(year_key) not in wanted
        ):
            continue
        frames.append(pd.read_parquet(path))
    if not frames:
        raise MinutesPlaneHeld("spine_daily_plane_has_no_partitions_for_these_years")
    daily = pd.concat(frames, ignore_index=True)
    missing = sorted(set(DAILY_REFERENCE_COLUMNS) - set(daily.columns))
    if missing:
        raise MinutesPlaneIntegrityError(f"spine daily plane lacks columns: {missing}")
    basis = daily.get("price_source_basis")
    if basis is not None:
        observed = {str(value) for value in basis.dropna().unique()}
        forbidden = observed & FORBIDDEN_DAILY_REFERENCE_BASES
        if forbidden:
            raise MinutesPlaneIntegrityError(
                f"daily reference declares a FORBIDDEN adjusted basis: {sorted(forbidden)}"
            )
        if observed and observed != {DAILY_REFERENCE_BASIS}:
            raise MinutesPlaneIntegrityError(
                "daily reference basis is not the nominal TuShare daily plane"
            )
    return daily[list(DAILY_REFERENCE_COLUMNS)]


_PLAIN_CASTS: Mapping[str, Callable[[object], object]] = {
    "string": lambda value: str(value),
    "float64": lambda value: float(value),
    "int64": lambda value: int(value),
}


def _plain_record(row: Mapping[str, object]) -> dict[str, object]:
    """Parquet read-back -> the exact plain-Python record shape that was hashed.

    ``read_parquet`` hands back NumPy scalars, which ``json.dumps`` refuses and which
    would otherwise make a recomputed digest silently un-comparable.
    """
    return {f.name: _PLAIN_CASTS[f.arrow_type](row[f.name]) for f in PARTITION_FIELDS}


def read_partition_records(path: Path) -> list[dict[str, object]]:
    """Normalized records read back from an installed partition, plain-Python typed."""
    frame = pd.read_parquet(Path(path) / "part.parquet")
    missing = sorted({f.name for f in PARTITION_FIELDS} - set(frame.columns))
    extra = sorted(set(frame.columns) - {f.name for f in PARTITION_FIELDS})
    if missing or extra:
        raise MinutesPlaneIntegrityError(
            f"partition parquet schema drifted (missing={missing} extra={extra})"
        )
    return [_plain_record(row) for row in frame.to_dict(orient="records")]


def iter_store_partitions(root: Path) -> list[tuple[str, str, int, Path]]:
    """Every installed ``(frequency, ticker, year, path)`` bundle, sorted."""
    found: list[tuple[str, str, int, Path]] = []
    for parquet in sorted(
        Path(root).glob("by_frequency=*/by_ticker=*/year=*/part.parquet")
    ):
        directory = parquet.parent
        year_key = directory.name.split("=", 1)[-1]
        ticker = directory.parent.name.split("=", 1)[-1]
        frequency = directory.parent.parent.name.split("=", 1)[-1]
        if not year_key.isdigit():
            raise MinutesPlaneIntegrityError(
                f"store has a non-numeric year key: {directory}"
            )
        found.append((frequency, ticker, int(year_key), directory))
    return found


def run_reconciliation_gate(
    root: Path,
    *,
    daily: pd.DataFrame | None = None,
    sample_size: int = 50,
    seed: str = "cn_tushare_minutes_reconciliation.v1",
) -> dict[str, object]:
    """Sampled OHLC-vs-minute-aggregate gate over whatever partitions exist.

    An absent daily plane is reported as ``unavailable_no_daily_reference_plane`` —
    never as a pass.  A gate that cannot see a failure has not proved anything.
    """
    partitions = iter_store_partitions(root)
    if not partitions:
        return {
            "status": "no_partitions_in_store",
            "passed": None,
            "required_basis": DAILY_REFERENCE_BASIS,
        }
    if daily is None:
        return {
            "status": "unavailable_no_daily_reference_plane",
            "passed": None,
            "required_basis": DAILY_REFERENCE_BASIS,
            "note": (
                "the spine's nominal daily plane is the only permitted anchor; "
                "china_stocks_raw (split-adjusted) is forbidden and is not a fallback"
            ),
            "partition_count": len(partitions),
        }
    daily_index: dict[tuple[str, str], dict[str, object]] = {}
    for row in daily.to_dict(orient="records"):
        daily_index[(str(row["ticker"]), str(row["trade_date"]))] = row

    sessions: dict[tuple[str, str], list[dict[str, object]]] = {}
    for _frequency, ticker, _year, directory in partitions:
        for record in read_partition_records(directory):
            sessions.setdefault((ticker, str(record["trade_date"])), []).append(record)

    comparable = sorted(key for key in sessions if key in daily_index)
    sample = _sample_keys(comparable, sample_size, seed=seed)
    results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for ticker, trade_date in sample:
        aggregate = aggregate_regular_window(sessions[(ticker, trade_date)])
        if aggregate is None:
            results.append(
                {
                    "ticker": ticker,
                    "trade_date": trade_date,
                    "status": "no_regular_window_bars",
                }
            )
            continue
        outcome = reconcile_session(aggregate, daily_index[(ticker, trade_date)])
        entry = {"ticker": ticker, "trade_date": trade_date, **outcome}
        results.append(entry)
        if not outcome["passed"]:
            failures.append(entry)
    checked = [entry for entry in results if "passed" in entry]
    return {
        "status": "executed",
        "required_basis": DAILY_REFERENCE_BASIS,
        "forbidden_bases": sorted(FORBIDDEN_DAILY_REFERENCE_BASES),
        "unit_conversions": {
            "daily_volume_lots_to_shares": SHARES_PER_LOT,
            "daily_amount_thousands_to_cny": CNY_PER_AMOUNT_UNIT,
        },
        "partition_count": len(partitions),
        "session_count_in_store": len(sessions),
        "comparable_session_count": len(comparable),
        "sample_size_requested": sample_size,
        "sample_size_checked": len(checked),
        "sample_seed": seed,
        "sample_sha256": canonical_hash(list(sample)),
        "failure_count": len(failures),
        "failures": failures[:20],
        "results_sha256": canonical_hash(results),
        "passed": bool(checked) and not failures,
        "aggregation_note": (
            "regular window only; the post-close window is excluded from the daily "
            "comparison and open_exact is reported, never required"
        ),
    }


# --------------------------------------------------------------------------------------
# Execution gate
# --------------------------------------------------------------------------------------


def find_tp0_probe_receipts(addons_root: Path = DEFAULT_ADDONS_ROOT) -> list[Path]:
    """Lane-A ``stk_mins`` probe receipts, newest path last."""
    root = Path(addons_root) / BASE_ENDPOINT_CONTRACT.api_name
    if not root.is_dir():
        return []
    return sorted(root.glob("by_frequency=*/by_trade_date=*/by_scope=*/receipt.json"))


def require_tp0_probe_receipt(
    addons_root: Path = DEFAULT_ADDONS_ROOT,
) -> dict[str, object]:
    """TP-0 sequencing law: no bulk backfill before a live probe receipt exists.

    The probe is what upgrades ``stk_mins`` from an operator-reported purchase to
    ``access_observed_at_request_time``.  Backfilling before it would spend the
    shared premium budget on an endpoint whose access and schema are still claims.
    """
    receipts = find_tp0_probe_receipts(addons_root)
    if not receipts:
        raise MinutesPlaneHeld(
            "tp0_stk_mins_probe_receipt_absent_backfill_is_sequenced"
        )
    latest = receipts[-1]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise MinutesPlaneIntegrityError("TP-0 probe receipt is not an object")
    access = payload.get("access_observation_receipt")
    if not isinstance(access, dict) or (
        access.get("observation") != "access_observed_at_request_time"
    ):
        raise MinutesPlaneHeld("tp0_probe_receipt_does_not_witness_access")
    contract = payload.get("endpoint_contract")
    contract_sha = (
        contract.get("contract_sha256") if isinstance(contract, dict) else None
    )
    return {
        "receipt_path": str(latest),
        "receipt_sha256": payload.get("receipt_sha256"),
        "probe_contract_sha256": contract_sha,
        "plane_base_contract_sha256": BASE_ENDPOINT_CONTRACT.contract_hash,
        "contract_agrees": contract_sha == BASE_ENDPOINT_CONTRACT.contract_hash,
        "observed_at_asia_shanghai": access.get("observed_at_asia_shanghai"),
        "receipt_count": len(receipts),
    }


# --------------------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------------------


def _source_scalar(value: object) -> object:
    """One canonical, JSON-safe pre-normalization vendor value (or None)."""
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
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MinutesPlaneIntegrityError(
                "vendor source contains a non-finite value"
            )
        return value
    raise MinutesPlaneIntegrityError(
        "vendor source contains an unsupported scalar type"
    )


def _source_rows_hash(frames: Sequence[pd.DataFrame]) -> str:
    """Digest of the canonical PRE-normalization vendor rows across a partition's chunks."""
    rows: list[dict[str, object]] = []
    for frame in frames:
        for raw in frame.to_dict(orient="records"):
            rows.append(
                {name: _source_scalar(raw[name]) for name in BASE_VENDOR_FIELDS}
            )
    rows.sort(key=_json_bytes)
    return canonical_hash(rows)


def _fetch_chunk(
    chunk: ChunkPlan, *, query: QueryFunction, governor: RateGovernor
) -> pd.DataFrame:
    governor.acquire()
    request = chunk.vendor_request
    params = {k: v for k, v in request.items() if k not in {"api_name", "fields"}}
    frame = query(request["api_name"], fields=str(request["fields"]), **params)
    if frame is None:
        return pd.DataFrame(columns=list(BASE_VENDOR_FIELDS))
    if len(frame) >= MAX_ROWS_PER_RESPONSE:
        raise MinutesPlaneIntegrityError(
            f"stk_mins chunk returned {len(frame)} rows at the documented "
            f"{MAX_ROWS_PER_RESPONSE}-row cap; the tape is presumed TRUNCATED"
        )
    return frame


def execute_backfill(
    plan: BackfillPlan,
    *,
    store_root: Path = DEFAULT_STORE_ROOT,
    addons_root: Path = DEFAULT_ADDONS_ROOT,
    query: QueryFunction | None = None,
    governor: RateGovernor | None = None,
    clock: ClockFunction | None = None,
    max_partitions: int | None = None,
) -> dict[str, object]:
    """Run the plan sequentially, partition by partition, and rewrite the ledger.

    TP-0 is enforced HERE, not only by the caller: a successful bounded Lane-A probe
    receipt must precede the bulk plane. A partition that raises is recorded ``contradiction`` in the
    coverage ledger and execution CONTINUES — a single bad ticker-year must not
    abort a multi-hour backfill, and it must not vanish either.
    """
    tp0 = require_tp0_probe_receipt(addons_root)
    root = Path(store_root)
    engine = query or tc.query
    pace = governor or RateGovernor()
    now = clock or (lambda: datetime.now(timezone.utc))

    existing = {
        (str(row["frequency"]), str(row["ticker"]), int(row["year"])): dict(row)
        for row in read_manifest(root).to_dict(orient="records")
    }
    executed = 0
    for partition in plan.partitions:
        key = (partition.frequency, partition.ticker, partition.year)
        target = partition_path(
            root,
            frequency=partition.frequency,
            ticker=partition.ticker,
            year=partition.year,
        )
        base = {
            "frequency": partition.frequency,
            "ticker": partition.ticker,
            "year": partition.year,
            "request_sha256": partition.request_sha256,
            "chunk_count": len(partition.chunks),
            "planned_session_count": partition.session_count,
            "partition_path_value": str(target),
        }
        if partition.status != "planned":
            existing.setdefault(key, coverage_row(status="planned", **base))
            continue
        if max_partitions is not None and executed >= max_partitions:
            existing[key] = coverage_row(status="planned", **base)
            continue
        executed += 1
        try:
            frames = [
                _fetch_chunk(chunk, query=engine, governor=pace)
                for chunk in partition.chunks
            ]
            combined = (
                pd.concat(frames, ignore_index=True)
                if frames
                else pd.DataFrame(columns=list(BASE_VENDOR_FIELDS))
            )
            records = normalize_minute_rows(
                combined,
                ticker=partition.ticker,
                frequency=partition.frequency,
                year=partition.year,
            )
            if not records:
                existing[key] = coverage_row(
                    status="contradiction",
                    contradiction_reason="vendor returned no rows for a planned ticker-year",
                    **base,
                )
                continue
            result = install_partition(
                root=root,
                frequency=partition.frequency,
                ticker=partition.ticker,
                year=partition.year,
                records=records,
                chunks=[chunk.vendor_request for chunk in partition.chunks],
                calendar_receipt=plan.calendar_receipt,
                tp0_probe=tp0,
                governor_receipt=pace.receipt(),
                source_rows_hash=_source_rows_hash(frames),
                observed_at=now(),
            )
            classes = _bar_class_counts(records)
            segments = _segment_counts(records)
            existing[key] = coverage_row(
                status="fetched",
                row_count=result.row_count,
                observed_session_count=len({str(r["trade_date"]) for r in records}),
                first_bar=str(records[0]["trade_time"]),
                last_bar=str(records[-1]["trade_time"]),
                zero_volume_rows=(
                    classes[BAR_CLASS_ZERO_VOLUME_FLAT]
                    + classes[BAR_CLASS_ZERO_VOLUME_INCONSISTENT]
                ),
                inconsistent_rows=(
                    classes[BAR_CLASS_ZERO_VOLUME_INCONSISTENT]
                    + classes[BAR_CLASS_VOLUME_WITHOUT_AMOUNT]
                ),
                post_close_rows=segments[SESSION_SEGMENT_POST_CLOSE],
                receipt_sha256=result.receipt_hash,
                observed_at_utc=now().astimezone(timezone.utc).isoformat(),
                **base,
            )
        except (MinutesPlaneIntegrityError, MinutesPlaneHeld) as exc:
            existing[key] = coverage_row(
                status="contradiction",
                contradiction_reason=f"{type(exc).__name__}: {exc}",
                **base,
            )
    manifest = write_manifest(
        root,
        list(existing.values()),
        plan_summary=plan.summary(),
        tp0_probe=tp0,
    )
    return {
        "status": "executed",
        "partitions_attempted": executed,
        "governor": pace.receipt(),
        "manifest": manifest,
    }


def verify_store(
    root: Path = DEFAULT_STORE_ROOT,
    *,
    daily: pd.DataFrame | None = None,
    sample_size: int = 50,
) -> dict[str, object]:
    """Recompute the ledger from the store and run the reconciliation gate.

    Ledger drift (a row the store does not back, or a partition the ledger does not
    know) is reported explicitly.  The recomputed ledger is NOT written back — a
    verify pass must not launder a contradiction into a clean row.
    """
    root = Path(root)
    recorded = {
        (str(row["frequency"]), str(row["ticker"]), int(row["year"])): dict(row)
        for row in read_manifest(root).to_dict(orient="records")
    }
    observed: dict[tuple[str, str, int], dict[str, object]] = {}
    receipt_failures: list[dict[str, object]] = []
    for frequency, ticker, year, directory in iter_store_partitions(root):
        key = (frequency, ticker, year)
        try:
            records = verify_partition_bundle(
                directory,
                identity=partition_identity(
                    frequency=frequency, ticker=ticker, year=year
                ),
            )
        except (MinutesPlaneIntegrityError, MinutesPlaneHeld) as exc:
            receipt_failures.append(
                {
                    "partition": f"{frequency}/{ticker}/{year}",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        observed[key] = {"row_count": len(records)}
    reconciliation = run_reconciliation_gate(root, daily=daily, sample_size=sample_size)
    ledger_only = sorted(f"{f}/{t}/{y}" for (f, t, y) in set(recorded) - set(observed))
    store_only = sorted(f"{f}/{t}/{y}" for (f, t, y) in set(observed) - set(recorded))
    row_mismatches = [
        f"{f}/{t}/{y}"
        for (f, t, y), value in observed.items()
        if (f, t, y) in recorded
        and recorded[(f, t, y)].get("row_count") is not None
        and int(recorded[(f, t, y)]["row_count"]) != int(value["row_count"])
    ]
    contradictions = sorted(
        f"{f}/{t}/{y}"
        for (f, t, y), row in recorded.items()
        if str(row.get("status")) == "contradiction"
    )
    return {
        "status": "verified",
        "store_root": str(root),
        "ledger_partition_count": len(recorded),
        "store_partition_count": len(observed),
        "ledger_rows_without_a_partition": ledger_only,
        "partitions_missing_from_ledger": store_only,
        "row_count_mismatches": sorted(row_mismatches),
        "receipt_failures": receipt_failures,
        "recorded_contradictions": contradictions,
        "reconciliation": reconciliation,
        "passed": (
            not ledger_only
            and not store_only
            and not row_mismatches
            and not receipt_failures
            and not contradictions
            and reconciliation.get("passed") is True
        ),
        "nonclaims": list(PLANE_NONCLAIMS),
    }


__all__ = [
    "AUTHORITY",
    "BASE_ENDPOINT_CONTRACT",
    "CORPORATE_ACTION_BASIS",
    "COVERAGE_COLUMNS",
    "DEFAULT_STORE_ROOT",
    "MANIFEST_SCHEMA_VERSION",
    "MAX_ROWS_PER_RESPONSE",
    "RATE_CEILING_CALLS_PER_MINUTE",
    "BackfillPlan",
    "ChunkPlan",
    "MinutesPlaneHeld",
    "MinutesPlaneIntegrityError",
    "PartitionPlan",
    "PartitionResult",
    "RateGovernor",
    "SessionCalendar",
    "Universe",
    "aggregate_regular_window",
    "arrow_schema",
    "classify_bar",
    "classify_session_segment",
    "coverage_row",
    "execute_backfill",
    "install_partition",
    "load_daily_reference",
    "load_session_calendar_from_event_catalog",
    "load_session_calendar_from_spine",
    "load_universe_from_event_catalog",
    "load_universe_from_file",
    "max_bars_per_session",
    "normalize_minute_rows",
    "partition_path",
    "plan_backfill",
    "quote_price_cents",
    "read_manifest",
    "reconcile_session",
    "require_tp0_probe_receipt",
    "run_reconciliation_gate",
    "sessions_per_chunk",
    "verify_partition_bundle",
    "verify_store",
    "wall_clock_estimate",
    "write_manifest",
]
