"""Resumable, provenance-first TuShare full-A daily/security spine.

This ``context_only`` foundation builds a lifecycle-aware SH/SZ/BJ master,
canonical/old-BSE aliases, an SSE=SZSE market-session clock, post-2016 exact-day
``bak_basic`` universe witnesses, effective-dated names, and daily quote/limit/
suspension/ST partitions.  It does not score signals or claim alpha.

TuShare licensing/compliance is ``CHAIRMAN_VERIFIED_PRIVATE / SATISFIED``
(``DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE``).  The controlling
agreement and its supporting evidence are confidential and outside coding/agent
scope under NDA/privacy constraints: no runtime path, CLI flag, manifest field,
or test in this repository may request, inspect, persist, hash, quote, or gate on
them.  What this module does enforce is technical -- the token is read only
through ``collectors.tushare_client`` and is never accepted, persisted, hashed, or
logged here, and every response must bind to its exact request.

The default store is private and outside the repository:
``~/.local/share/macro-dashboard/china_tushare_spine`` (override only with
``CN_TUSHARE_SPINE_STORE`` or ``--store``).  Its principal layout is::

    reference/current_generation.json
    reference/generations/<generation>/
        source_{bse_mapping,stock_basic,fund_basic}/...
        {security_master,identity_aliases,instrument_classification}.parquet
    reference/{trade_calendar/year=YYYY,market_sessions}.parquet
    bak_basic/year=YYYY/month=MM/part.parquet
    name_history/year=YYYY.parquet
    {daily,daily_basic,stk_limit,suspend_d,stock_st}/year=YYYY/month=MM/part.parquet
    source_row_classification/{known_excluded,quarantined_unknown}/...
    range_campaigns/<campaign-id>/{plan,terminal_index,campaign_receipt}...
    source_range_shards/{daily,daily_basic,stk_limit}/<campaign-id>/...
    receipts/requests/<endpoint>/range:<leaf-id>/<attempt-id>.json
    event_daily/year=YYYY/month=MM/part.parquet
    coverage/daily_security_coverage.parquet
    collection_state.json
    completeness_manifest.json

Every response must have the exact requested schema and belong to the exact
exchange/status/date/ticker request.  Each source unit satisfies
``source = landed_A + independently_known_out_of_scope + quarantined_unknown``;
unknown rows, name orphans, absent/tampered request or classification receipts, or
an uncovered ticker-range campaign block completeness.  Capped whole-market
responses are discarded as non-authoritative probes before deterministic
ticker-by-date-range recovery.  Range leaves split below the endpoint cap,
transpose back to exact-day partitions, and keep each attempt immutable.  The
operational gate nevertheless remains false pending live canary, throughput, and
correctness evidence.

``daily`` is unadjusted nominal price authority and retains zero-volume rows with
``positive_volume = volume_lots > 0``.  A traded/listing-session claim must filter
that flag.  ``stk_limit`` is exact legal-band authority.  Canonical event prices
are integer CNY cents; OHLC must remain inside published bounds and touch/seal
flags use integer equality.  The Decimal half-up calculator is validator-only.

Usage (no implicit full-history collection)::

    python -m collectors.china_tushare_spine --start 20110101 --end 20260807 \
        --max-requests 50
    python -m collectors.china_tushare_spine --start 20110101 --end 20260807 \
        --dry-run

The default request cap is intentionally small.  Re-running resumes incomplete
units.  ``--allow-bulk`` is required above the safety ceiling or for unlimited
collection.  ``BULK_HISTORICAL_BACKFILL_READY`` is deliberately false until a
separately reviewed wave proves the range implementation against live data with
canary, throughput, and correctness evidence.  It is a technical readiness gate
and must never be read, restored, or re-titled as a licensing gate.

Because that gate waits on canary evidence, the canary itself must be runnable
first: ``--canary`` performs real bounded collection while the gate is still
false, capped at ``CANARY_MAX_REQUESTS`` requests over ``CANARY_MAX_RANGE_DAYS``
calendar days, never with ``--allow-bulk``, and refusing rather than starting the
unproven ticker-range campaign if a documented row cap fires.  The three modes
are therefore ``--dry-run`` (network-free plan), ``--canary`` (real, hard-bounded)
and the default bulk/backfill path (still gated).
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import logging
import math
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from collectors import china_tushare_range_shards as crs
from collectors import tushare_client as tc

log = logging.getLogger(__name__)

MANIFEST_SCHEMA_VERSION = "cn_tushare_a_share_spine_manifest.v1"
STATE_SCHEMA_VERSION = "cn_tushare_a_share_spine_state.v2"
# TECHNICAL READINESS GATE -- NOT a licensing gate.  Scalable range shards are
# implemented and synthetic-tested, but no live parity/throughput canary has run,
# so bulk historical collection stays fail-closed on engineering evidence alone:
# canary parity, sustained throughput, and range/completeness correctness.  Flip
# it only in a separate reviewed change that cites those measurements.  Licensing
# and compliance are settled outside this repository and are never re-litigated
# here (see the module docstring).
BULK_HISTORICAL_BACKFILL_READY = False
# The canary is the evidence that gate wants, so it must be runnable BEFORE the
# gate opens -- otherwise the sequence is circular and the gate can never be
# retired on measurement.  ``collect(..., canary=True)`` therefore performs real
# bounded collection while ``BULK_HISTORICAL_BACKFILL_READY`` is still False,
# under hard ceilings enforced below and with every technical control unchanged
# (exact request/schema binding, PIT, source-row accounting, receipts, locking).
# What the canary may NOT do is exercise the unproven scalable path: a documented
# row cap refuses instead of starting a ticker-range campaign, and bulk/unlimited
# budgets stay forbidden.  Opening the bulk gate remains a separate reviewed
# change that cites canary receipts.
CANARY_MAX_REQUESTS = 12
CANARY_MAX_RANGE_DAYS = 5
AUTHORITY = "context_only"
SOURCE_NAME = "tushare_pro"

DEFAULT_STORE = Path(os.environ.get(
    "CN_TUSHARE_SPINE_STORE",
    Path.home() / ".local" / "share" / "macro-dashboard" / "china_tushare_spine",
))
DEFAULT_ENDPOINTS = ("daily", "daily_basic", "stk_limit", "suspend_d", "stock_st")
DAILY_ENDPOINTS = frozenset(DEFAULT_ENDPOINTS)
EMPTY_ALLOWED_ENDPOINTS = frozenset({"suspend_d", "stock_st"})
DENSE_ENDPOINTS = frozenset({"daily", "daily_basic", "stk_limit"})
PIT_UNIVERSE_ENDPOINT = "bak_basic"
FUND_REFERENCE_ENDPOINT = "fund_basic"

DEFAULT_MAX_REQUESTS = 50
SAFE_MAX_REQUESTS = 100
ST_DAILY_START = date(2016, 1, 1)
PIT_UNIVERSE_START = date(2016, 1, 1)
BSE_LAUNCH = date(2021, 11, 15)
# --- Mainland session-clock epoch (frozen, definition-versioned) -------------
# The canonical mainland session axis begins at a FROZEN epoch, not at the first
# date any venue happens to publish.  The epoch is the earliest calendar year for
# which TuShare `trade_cal` supplies a JOINTLY complete SSE+SZSE calendar; it is
# frozen in source and is never selected at runtime, so two runs over the same
# store can never disagree about which date owns which ordinal.
#
# 1992-01-01 was established by an outcome-blind source census over the landed
# calendar partitions (`scripts/research/cn_limit_calendar_epoch_census.py`):
# SSE and SZSE each return 366 of 366 unique civil dates for 1992, every year
# 1992..2023 is jointly complete with zero open/closed parity mismatches, and
# both exchanges show zero `pretrade_date` chain violations and zero missing
# civil dates.  1991 fails only because TuShare returns 182 of 365 days for SZSE.
#
# That 182-day shortfall is SOURCE-HISTORY TRUNCATION, not evidence that the
# missing civil dates fell outside the trading system.  Pre-epoch history is
# therefore typed `PRE_EPOCH_SOURCE_UNSUPPORTED`: it is never imputed as closed,
# never assigned an ordinal, and SSE history is never borrowed as exact SZSE
# history.  Bump the definition string, never mutate the date in place, if a
# future authority moves the epoch — artifacts stamped under different
# definitions must stay distinguishable.
MAINLAND_CALENDAR_EPOCH_DEFINITION = "mainland-joint-complete-v1"
MAINLAND_CALENDAR_EPOCH = date(1992, 1, 1)
PRE_EPOCH_SOURCE_STATE = "PRE_EPOCH_SOURCE_UNSUPPORTED"
CALENDAR_HISTORY_START = MAINLAND_CALENDAR_EPOCH
NAME_HISTORY_START_YEAR = 1990
NAMECHANGE_MAX_PER_RUN = 5
FUND_STATUSES = ("L", "D", "I")

TUSHARE_BAK_BASIC_DOC_URL = "https://tushare.pro/document/2?doc_id=262"
TUSHARE_FUND_BASIC_DOC_URL = "https://tushare.pro/document/2?doc_id=19"
SSE_SECURITY_CODE_GUIDE_URL = (
    "https://www.sse.com.cn/lawandrules/guide/stock/jyglywznylc/zn/"
    "c/c_20260713_10825354.shtml"
)
SZSE_SECURITY_CODE_RANGE_URL = (
    "https://www.szse.cn/marketServices/technicalservice/doc/"
    "P020241212550140892927.pdf"
)

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
    "fund_basic": (
        "ts_code,name,management,custodian,fund_type,found_date,due_date,list_date,"
        "issue_date,delist_date,issue_amount,m_fee,c_fee,duration_year,p_value,min_amount,"
        "exp_return,benchmark,status,invest_type,type,trustee,purc_startdate,redm_startdate,market"
    ),
    "trade_cal": "exchange,cal_date,is_open,pretrade_date",
    "namechange": "ts_code,name,start_date,end_date,ann_date,change_reason",
    "bak_basic": (
        "trade_date,ts_code,name,industry,area,pe,float_share,total_share,total_assets,"
        "liquid_assets,fixed_assets,reserved,reserved_pershare,eps,bvps,pb,list_date,undp,"
        "per_undp,rev_yoy,profit_yoy,gpr,npr,holder_num"
    ),
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
    "fund_basic": 15000,
    "bak_basic": 7000,
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
    "bak_basic": ["trade_date", "ticker"],
    "source_classification": ["trade_date", "source_row_ordinal"],
}

_ST_PREFIX = re.compile(r"^(?:N?\*ST|N?ST|S\*ST|SST|PT)", re.IGNORECASE)
_COMPACT_DATE = re.compile(r"^\d{8}$")
_TUSHARE_CODE = re.compile(r"^(?P<code>\d{6})\.(?P<suffix>SH|SS|SZ|BJ)$", re.IGNORECASE)
_T_PREFIXED_LEGACY_VENDOR_CODE = re.compile(r"^T\d{6}\.[A-Z]{2}$")


class SpineError(RuntimeError):
    """Fail-closed contract or store-integrity error."""


class RequestBudgetExhausted(SpineError):
    """Internal control-flow signal for a clean resumable stop."""


@dataclass(frozen=True)
class VendorResponse:
    """A schema- and request-bound response plus its persisted request receipt."""

    frame: pd.DataFrame | None
    receipt: Mapping[str, Any]


@dataclass(frozen=True)
class NormalisedSourceUnit:
    """Lossless classification of every source row in an exact request unit."""

    landed_a: pd.DataFrame
    known_excluded: pd.DataFrame
    quarantined_unknown: pd.DataFrame

    @property
    def source_row_count(self) -> int:
        return len(self.landed_a) + len(self.known_excluded) + len(self.quarantined_unknown)


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
    # TuShare's ZERO SENTINEL for an unpublished date.  `stock_basic` returns an
    # empty string, already covered above, but `bak_basic` returns "0" -- which
    # reached this function as a hard SpineError the first time pit_universe ever
    # ran against the real vendor, killing the whole unit over one descriptive
    # field on an otherwise valid A-share row.
    #
    # This is fail-CLOSED, not an imputation.  A null date is an EXPECTED state
    # the callers already model: a row whose list_date is null "remains in the
    # master but cannot enter a historical eligible universe" (see the
    # effective_from branch in the stock_basic normaliser).  Nulling the sentinel
    # therefore narrows eligibility; inventing a date would have widened it.
    #
    # An all-zero run is the only safe spelling of this test: every real date has
    # a non-zero digit in its year, so this can never swallow one.  A malformed
    # date that is merely wrong ("202401", "0000-00-00") still raises below.
    if set(text) == {"0"}:
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
    if source_exchange == "SZSE":
        try:
            numeric_code = int(code)
        except ValueError:
            numeric_code = -1
        # SZSE's official allocation covers 300000-309799 ChiNext shares and
        # 309800-309999 ChiNext depositary receipts.  Do not misclassify future
        # 303-309 families as main-board securities.
        if 300000 <= numeric_code <= 309999:
            return "chinext"
    return "main"


_TUSHARE_MARKET_BY_BOARD = {
    "main": "主板",
    "chinext": "创业板",
    "star": "科创板",
    "bse": "北交所",
}


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


def _is_canonical_ts_code(ts_code: Any) -> bool:
    """True unless ``ts_code`` fails ``canonical_identity`` (legacy/delisted vendor codes)."""
    try:
        canonical_identity(ts_code)
    except SpineError:
        return False
    return True


def _known_excluded_noncanonical_code_family(raw_ts_code: Any) -> str | None:
    """Provenance for a non-canonical ``ts_code`` that is independently classifiable.

    Matches exactly one tight, observed pattern (exemplar ``'T600018.SS'``): a
    T-prefixed legacy vendor code.  The claim is narrow -- only that the raw
    string sits outside the official 6-digit A-share coding scheme
    (``_TUSHARE_CODE``), never an assertion about what the security is or
    was.  Any other non-canonical shape returns ``None`` and stays
    quarantined as genuinely unknown.
    """
    text = str(raw_ts_code or "")
    if _T_PREFIXED_LEGACY_VENDOR_CODE.fullmatch(text):
        return "official_A_code_scheme_excludes_T_prefixed_legacy_vendor_code"
    return None


def _stock_basic_ts_code_classification(ts_code: Any) -> str:
    """Classify one raw stock_basic ``ts_code`` into its accounting role.

    One of ``'landed_A'`` (canonical), ``'known_excluded'`` (non-canonical
    but independently classifiable, e.g. a T-prefixed legacy vendor code), or
    ``'quarantined_unknown'`` (non-canonical and genuinely unknown).  Shared
    by every stock_basic accounting/verification path -- collect_reference's
    unit accounting, the artifact-receipt role recomputation, and
    compile_security_master -- so the three-way split is drawn identically
    everywhere.
    """
    if _is_canonical_ts_code(ts_code):
        return "landed_A"
    if _known_excluded_noncanonical_code_family(ts_code) is not None:
        return "known_excluded"
    return "quarantined_unknown"


def is_st_name(name: Any) -> bool:
    """Conservative name-based ST/risk-warning inference for name history."""
    text = re.sub(r"\s+", "", str(name or "")).upper()
    return bool(_ST_PREFIX.match(text))


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _iter_logical_strings(value: Any) -> Iterable[str]:
    """Yield decoded scalar text so compressed columnar files cannot hide credentials."""
    if isinstance(value, pd.DataFrame):
        yield from _iter_logical_strings(value.attrs)
        yield from _iter_logical_strings(value.columns)
        yield from _iter_logical_strings(value.index)
        for position in range(len(value.columns)):
            series = value.iloc[:, position]
            if isinstance(series.dtype, pd.CategoricalDtype):
                # Unused dictionary values are serialized into Parquet too; a
                # row-value-only scan would miss a credential hidden there.
                yield from _iter_logical_strings(series.cat.categories)
            yield from _iter_logical_strings(series.tolist())
        return
    if isinstance(value, pd.Series):
        yield from _iter_logical_strings(value.name)
        yield from _iter_logical_strings(value.index)
        if isinstance(value.dtype, pd.CategoricalDtype):
            yield from _iter_logical_strings(value.cat.categories)
        yield from _iter_logical_strings(value.tolist())
        return
    if isinstance(value, pd.MultiIndex):
        yield from _iter_logical_strings(value.names)
        for level in value.levels:
            yield from _iter_logical_strings(level)
        yield from _iter_logical_strings(value.tolist())
        return
    if isinstance(value, pd.Index):
        yield from _iter_logical_strings(value.name)
        categories = getattr(value, "categories", None)
        if categories is not None:
            yield from _iter_logical_strings(categories)
        yield from _iter_logical_strings(value.tolist())
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _iter_logical_strings(item)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _iter_logical_strings(item)
        return
    if isinstance(value, (str, bytes)):
        yield value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def _assert_configured_token_absent_logical(value: Any, *, artifact: str) -> None:
    """Fail on decoded values before a write and again after a Parquet read."""
    secret = tc.token()
    if not secret:
        return
    if any(secret in text for text in _iter_logical_strings(value)):
        raise SpineError(f"configured credential found in decoded artifact values: {artifact}")


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
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
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
    _assert_configured_token_absent_logical(payload, artifact=path.name)
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


def _atomic_bytes(path: Path, raw: bytes) -> None:
    _assert_configured_token_absent(raw, artifact=path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    _assert_configured_token_absent_logical(frame, artifact=path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".parquet")
    os.close(fd)
    try:
        frame.to_parquet(temporary, index=False, compression="zstd")
        serialized = Path(temporary).read_bytes()
        _assert_configured_token_absent(serialized, artifact=path.name)
        try:
            roundtrip = pd.read_parquet(temporary)
        except Exception as exc:
            raise SpineError(f"serialized spine partition failed roundtrip: {path.name}") from exc
        _assert_configured_token_absent_logical(roundtrip, artifact=path.name)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_parquet_strict(path: Path) -> pd.DataFrame:
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        raise SpineError(f"unreadable existing spine partition: {path}: {exc}") from exc
    _assert_configured_token_absent_logical(frame, artifact=path.name)
    return frame


@contextlib.contextmanager
def spine_store_lock(store: Path) -> Iterable[None]:
    """Acquire a non-blocking process lock before any mutable store operation."""
    target = Path(store)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.parent / f".{target.name}.writer.lock"
    with lock_path.open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SpineError(f"another process holds the spine writer lock: {lock_path}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
    _assert_configured_token_absent_logical(state, artifact=path.name)
    if state.get("schema_version") != STATE_SCHEMA_VERSION or not isinstance(state.get("units"), dict):
        raise SpineError(f"collection state has an unsupported schema: {path}")
    return state


def _unit_record(state: Mapping[str, Any], endpoint: str, unit: str) -> Mapping[str, Any] | None:
    endpoint_units = state.get("units", {}).get(endpoint, {})
    record = endpoint_units.get(unit) if isinstance(endpoint_units, dict) else None
    return record if isinstance(record, dict) else None


def _shard_coverage(
    state: Mapping[str, Any], store: Path, endpoint: str, unit: str,
    record: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Recompute a parent unit's ticker-shard coverage from terminal child receipts."""
    if record.get("collection_method") != "per_ticker_shards":
        return None
    expected_count = record.get("expected_ticker_count")
    expected_hash = record.get("expected_ticker_sha256")
    if not isinstance(expected_count, int) or expected_count <= 0:
        return {
            "expected_ticker_count": expected_count,
            "completed_ticker_count": 0,
            "authoritative_source_row_count": 0,
            "expected_ticker_sha256": expected_hash,
            "observed_ticker_sha256": None,
            "complete": False,
        }
    shard_endpoint = f"{endpoint}_shard"
    prefix = f"{unit}:"
    tickers = sorted(
        shard_unit[len(prefix):]
        for shard_unit in state.get("units", {}).get(shard_endpoint, {})
        if str(shard_unit).startswith(prefix)
        and _unit_done(state, store, shard_endpoint, str(shard_unit))
    )
    authoritative_source_rows = sum(
        int((_unit_record(state, shard_endpoint, f"{unit}:{ticker}") or {}).get(
            "source_row_count", 0,
        ))
        for ticker in tickers
    )
    observed_hash = hashlib.sha256("\n".join(tickers).encode("utf-8")).hexdigest()
    return {
        "expected_ticker_count": expected_count,
        "completed_ticker_count": len(tickers),
        "authoritative_source_row_count": authoritative_source_rows,
        "expected_ticker_sha256": expected_hash,
        "observed_ticker_sha256": observed_hash,
        "complete": bool(
            len(tickers) == expected_count
            and isinstance(expected_hash, str)
            and observed_hash == expected_hash
            and authoritative_source_rows == int(record.get("source_row_count", 0))
        ),
    }


def _contained_store_path(store: Path, relative: Any) -> Path:
    raw = Path(str(relative))
    if raw.is_absolute() or ".." in raw.parts:
        raise SpineError("state artifact path is not store-relative")
    root = store.resolve()
    candidate = (root / raw).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SpineError("state artifact path escapes the spine store") from exc
    return candidate


def _validate_private_store_path(store: Path) -> Path:
    """Reject stageable paid-data stores anywhere inside the repository."""
    resolved = Path(store).expanduser().resolve(strict=False)
    repo_root = Path(__file__).resolve().parents[1]
    legacy_ignored = (repo_root / "data" / "china_tushare_spine").resolve(strict=False)
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        return resolved
    try:
        resolved.relative_to(legacy_ignored)
    except ValueError as exc:
        raise SpineError(
            "TuShare spine store must remain outside the repository; only the exact "
            "ignored data/china_tushare_spine containment root is permitted"
        ) from exc
    return resolved


def _expected_unit_partition_path(
    store: Path, endpoint: str, unit: str, record: Mapping[str, Any],
) -> Path | None:
    base = endpoint.removesuffix("_shard")
    if endpoint.endswith("_shard"):
        compact, ticker = unit.split(":", 1)
        return _shard_partition(store, base, _parse_date(compact), ticker)
    if base in DAILY_ENDPOINTS:
        return _monthly_partition(store, base, _parse_date(unit))
    if base == PIT_UNIVERSE_ENDPOINT:
        return _pit_partition(store, _parse_date(unit))
    if base == "namechange":
        return _name_partition(store, int(unit.split(":", 1)[0]))
    if base == "trade_cal":
        _, compact_start, _ = unit.split(":", 2)
        return _calendar_partition(store, _parse_date(compact_start).year)
    relative = record.get("partition")
    return _contained_store_path(store, relative) if relative else None


def _unit_artifact_receipt(
    store: Path, endpoint: str, unit: str, record: Mapping[str, Any],
    *, role: str = "landed_A",
) -> dict[str, Any]:
    """Recompute the exact landed subset represented by one terminal state unit.

    ``role`` only matters for ``stock_basic`` (one of ``'landed_A'``,
    ``'known_excluded'``, or ``'quarantined_unknown'``): unlike the
    daily-cadence endpoints, a non-canonical (legacy/delisted vendor code)
    row is never split into a separate ``source_row_classification``
    partition -- the raw response parquet is stored verbatim (raw parquet is
    raw truth) and every role is recomputed from that one file via
    ``_stock_basic_ts_code_classification``.
    """
    base = endpoint.removesuffix("_shard")
    expected_path = _expected_unit_partition_path(store, endpoint, unit, record)
    recorded_relative = record.get("partition")
    if recorded_relative:
        recorded_path = _contained_store_path(store, recorded_relative)
        if expected_path is not None and recorded_path != expected_path.resolve(strict=False):
            raise SpineError(f"{endpoint}/{unit} partition path disagrees with its unit")
        expected_path = recorded_path
    if expected_path is None:
        frame = pd.DataFrame()
        relative_path = None
    else:
        relative_path = expected_path.resolve(strict=False).relative_to(store.resolve()).as_posix()
        frame = _read_parquet_strict(expected_path) if expected_path.is_file() else pd.DataFrame()
    if not frame.empty and endpoint.endswith("_shard"):
        # Shard files are one exact raw request unit and are never shared.
        subset = frame.copy()
        keys = [column for column in ("trade_date", "ts_code") if column in subset.columns]
    elif base in DAILY_ENDPOINTS | {PIT_UNIVERSE_ENDPOINT}:
        expected_date = _parse_date(unit.split(":", 1)[0]).isoformat()
        if not frame.empty and "trade_date" not in frame.columns:
            raise SpineError(f"{endpoint}/{unit} artifact lacks trade_date")
        subset = frame[
            frame["trade_date"].map(_iso) == expected_date
        ].copy() if not frame.empty else frame.copy()
        keys = KEY_COLUMNS[base]
    elif base == "trade_cal":
        exchange, compact_start, compact_end = unit.split(":", 2)
        start = _parse_date(compact_start).isoformat()
        end = _parse_date(compact_end).isoformat()
        if not frame.empty and not {"exchange", "cal_date"}.issubset(frame.columns):
            raise SpineError(f"trade_cal/{unit} artifact lacks its selector columns")
        subset = frame[
            (frame["exchange"].astype(str) == exchange)
            & (frame["cal_date"].map(_iso).between(start, end))
        ].copy() if not frame.empty else frame.copy()
        keys = KEY_COLUMNS["trade_calendar"]
    elif base == "namechange":
        subset = frame.copy()
        keys = KEY_COLUMNS["name_history"]
    else:
        subset = frame.copy()
        keys = {
            "bse_mapping": ["o_code", "n_code"],
            "stock_basic": ["ts_code"],
            "fund_basic": ["ts_code"],
        }.get(base, list(subset.columns))
        if base == "stock_basic" and not subset.empty:
            row_roles = subset["ts_code"].map(_stock_basic_ts_code_classification)
            subset = subset[row_roles == role].reset_index(drop=True)
    if subset.empty:
        duplicate_rows = 0
    elif not keys:
        raise SpineError(f"{endpoint}/{unit} artifact has no semantic key")
    else:
        duplicate_rows = _duplicates(subset, keys)
    return {
        "path": relative_path,
        "unit_row_count": len(subset),
        "unit_semantic_sha256": _frame_semantic_sha256(subset, keys),
        "key_columns": list(keys),
        "duplicate_key_rows": duplicate_rows,
    }


def _empty_unit_artifact_receipt() -> dict[str, Any]:
    return {
        "path": None,
        "unit_row_count": 0,
        "unit_semantic_sha256": hashlib.sha256(b"").hexdigest(),
        "key_columns": [],
        "duplicate_key_rows": 0,
    }


def _classification_unit_artifact_receipt(
    store: Path,
    endpoint: str,
    unit: str,
    classification: str,
) -> dict[str, Any]:
    base = endpoint.removesuffix("_shard")
    if endpoint.endswith("_shard"):
        return _empty_unit_artifact_receipt()
    if base not in DAILY_ENDPOINTS | {PIT_UNIVERSE_ENDPOINT, "namechange"}:
        return _empty_unit_artifact_receipt()
    compact = unit.split(":", 1)[-1] if base == "namechange" else unit.split(":", 1)[0]
    day = _parse_date(compact)
    path = _classification_partition(store, classification, base, day)
    frame = _read_parquet_strict(path) if path.is_file() else pd.DataFrame()
    if not frame.empty and "trade_date" not in frame.columns:
        raise SpineError(f"{classification}/{base}/{unit} artifact lacks trade_date")
    subset = frame[
        frame["trade_date"].map(_iso) == day.isoformat()
    ].copy() if not frame.empty else frame.copy()
    keys = KEY_COLUMNS["source_classification"]
    duplicates = _duplicates(subset, keys) if not subset.empty else 0
    return {
        "path": path.resolve(strict=False).relative_to(store.resolve()).as_posix(),
        "unit_row_count": len(subset),
        "unit_semantic_sha256": _frame_semantic_sha256(subset, keys),
        "key_columns": keys,
        "duplicate_key_rows": duplicates,
    }


def _unit_artifact_receipts(
    store: Path, endpoint: str, unit: str, record: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    primary = _unit_artifact_receipt(store, endpoint, unit, record)
    if endpoint == FUND_REFERENCE_ENDPOINT:
        landed = _empty_unit_artifact_receipt()
        known_excluded = primary
        quarantined = _classification_unit_artifact_receipt(
            store, endpoint, unit, "quarantined_unknown",
        )
    elif endpoint == "stock_basic":
        # stock_basic has no source_row_classification partition of its own
        # (raw parquet is raw truth); every role is recomputed from the same
        # raw file the landed role above already read.
        landed = primary
        known_excluded = _unit_artifact_receipt(
            store, endpoint, unit, record, role="known_excluded",
        )
        quarantined = _unit_artifact_receipt(
            store, endpoint, unit, record, role="quarantined_unknown",
        )
    else:
        landed = primary
        known_excluded = _classification_unit_artifact_receipt(
            store, endpoint, unit, "known_excluded",
        )
        quarantined = _classification_unit_artifact_receipt(
            store, endpoint, unit, "quarantined_unknown",
        )
    return {
        "landed_A": landed,
        "known_excluded": known_excluded,
        "quarantined_unknown": quarantined,
    }


def _unit_artifact_counts_match(
    receipts: Mapping[str, Mapping[str, Any]], record: Mapping[str, Any],
) -> bool:
    expected = {
        "landed_A": int(record.get("row_count", 0)),
        "known_excluded": int(record.get("known_excluded_row_count", 0)),
        "quarantined_unknown": int(record.get("quarantined_unknown_row_count", 0)),
    }
    return all(
        role in receipts
        and int(receipts[role].get("unit_row_count", -1)) == count
        and int(receipts[role].get("duplicate_key_rows", -1)) == 0
        for role, count in expected.items()
    )


_REQUEST_RECEIPT_BINDING_FIELDS = (
    "request_id", "endpoint", "unit", "fields", "params", "request_contract_sha256",
    "observed_at", "response_status", "response_row_count", "response_columns",
    "response_semantic_sha256",
    "receipt_role", "discarded_probe_row_count",
)


def _expected_request_params(state_endpoint: str, state_unit: str) -> dict[str, Any]:
    endpoint = state_endpoint.removesuffix("_shard")
    if state_endpoint.endswith("_shard"):
        compact, ticker = state_unit.split(":", 1)
        return {"trade_date": compact, "ts_code": _source_ts_code(ticker)}
    if endpoint in DAILY_ENDPOINTS | {PIT_UNIVERSE_ENDPOINT}:
        return {"trade_date": state_unit}
    if endpoint == "stock_basic":
        _, exchange, status = state_unit.rsplit(":", 2)
        return {"exchange": exchange, "list_status": status}
    if endpoint == "fund_basic":
        _, status = state_unit.rsplit(":", 1)
        return {"market": "E", "status": status}
    if endpoint == "trade_cal":
        exchange, start, end = state_unit.split(":", 2)
        return {"exchange": exchange, "start_date": start, "end_date": end}
    if endpoint == "namechange":
        year, end = state_unit.split(":", 1)
        return {"start_date": f"{year}0101", "end_date": end}
    if endpoint == "bse_mapping":
        return {}
    raise SpineError(f"cannot derive request parameters for {state_endpoint}/{state_unit}")


def _unit_request_receipts_valid(
    state_endpoint: str,
    state_unit: str,
    record: Mapping[str, Any],
    store: Path,
    campaign_cache: dict[str, crs.CampaignVerification] | None = None,
) -> bool:
    if record.get("collection_method") == "per_ticker_range_shards":
        reference = record.get("range_campaign_receipt")
        if not isinstance(reference, Mapping):
            return False
        campaign_id = str(reference.get("campaign_id") or "")
        try:
            if campaign_cache is not None and campaign_id in campaign_cache:
                verification = campaign_cache[campaign_id]
            else:
                verification = crs.verify_campaign(store, campaign_id)
                if campaign_cache is not None:
                    campaign_cache[campaign_id] = verification
            if not verification.complete:
                return False
            campaign_reference = crs.campaign_receipt_reference(store, verification)
        except crs.RangeShardError:
            return False
        try:
            expected_date = _parse_date(state_unit).isoformat()
        except (ValueError, SpineError):
            return False
        day = verification.day_receipts.get(expected_date)
        if not isinstance(day, Mapping):
            return False
        expected_reference = {
            **campaign_reference,
            "trade_date": expected_date,
            "authoritative_row_count": int(day["authoritative_row_count"]),
            "authoritative_semantic_sha256": day["authoritative_semantic_sha256"],
        }
        return bool(
            dict(reference) == expected_reference
            and int(record.get("source_row_count", -1))
            == int(day["authoritative_row_count"])
        )
    receipts = record.get("request_receipts")
    if not isinstance(receipts, list) or not receipts:
        return False
    expected_endpoint = state_endpoint.removesuffix("_shard")
    try:
        expected_params = _expected_request_params(state_endpoint, state_unit)
    except (SpineError, ValueError):
        return False
    persisted_count = 0
    authoritative_response_rows = 0
    for embedded in receipts:
        if not isinstance(embedded, Mapping):
            return False
        relative = embedded.get("path")
        if not relative:
            if not (
                record.get("collection_method") == "per_ticker_shards"
                and embedded.get("endpoint") == expected_endpoint
                and embedded.get("unit") == state_unit
                and embedded.get("response_status") in {"shards_complete", "shards_incomplete"}
            ):
                return False
            continue
        try:
            path = _contained_store_path(store, relative)
        except SpineError:
            return False
        if not path.is_file():
            return False
        try:
            decoded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        try:
            _assert_configured_token_absent_logical(decoded, artifact=path.name)
        except SpineError:
            return False
        if not isinstance(decoded, dict):
            return False
        if any(decoded.get(name) != embedded.get(name) for name in _REQUEST_RECEIPT_BINDING_FIELDS):
            return False
        if decoded.get("endpoint") != expected_endpoint or decoded.get("unit") != state_unit:
            return False
        fields = decoded.get("fields")
        params = decoded.get("params")
        if (
            fields != ENDPOINT_FIELDS.get(expected_endpoint, "").split(",")
            or not isinstance(params, dict)
            or params != expected_params
        ):
            return False
        contract = {
            "endpoint": expected_endpoint,
            "fields": fields,
            "params": {str(key): _json_safe(value) for key, value in sorted(params.items())},
            "unit": state_unit,
        }
        contract_hash = hashlib.sha256(_canonical_json_bytes(contract)).hexdigest()
        canonical_path = _request_receipt_path(
            store, expected_endpoint, state_unit, contract_hash,
        ).resolve(strict=False)
        response_count = decoded.get("response_row_count")
        response_status = decoded.get("response_status")
        response_semantic = decoded.get("response_semantic_sha256")
        cap_probe = response_status == "non_authoritative_cap_probe"
        if (
            decoded.get("request_id") != contract_hash
            or decoded.get("request_contract_sha256") != contract_hash
            or path.stem != contract_hash
            or path.resolve() != canonical_path
            or response_status not in {
                "accepted", "accepted_empty", "non_authoritative_cap_probe",
            }
            or not isinstance(response_count, int)
            or response_count < 0
            or (
                not cap_probe
                and (response_status == "accepted_empty") != (response_count == 0)
            )
            or decoded.get("response_columns") != fields
            or not re.fullmatch(r"[0-9a-f]{64}", str(response_semantic or ""))
            or (response_count == 0 and response_semantic != hashlib.sha256(b"").hexdigest())
        ):
            return False
        if cap_probe:
            if not (
                record.get("collection_method") == "per_ticker_shards"
                and decoded.get("receipt_role") == "discarded_non_authoritative_cap_probe"
                and decoded.get("discarded_probe_row_count") == response_count
                and response_count >= SOURCE_ROW_CAPS.get(expected_endpoint, 10**12)
            ):
                return False
        else:
            if decoded.get("receipt_role") is not None or decoded.get(
                "discarded_probe_row_count"
            ) is not None:
                return False
            authoritative_response_rows += response_count
        persisted_count += 1
    if persisted_count == 0:
        return False
    if record.get("collection_method") != "per_ticker_shards":
        return authoritative_response_rows == int(record.get("source_row_count", 0))
    return True


def _unit_done(
    state: Mapping[str, Any],
    store: Path,
    endpoint: str,
    unit: str,
    campaign_cache: dict[str, crs.CampaignVerification] | None = None,
) -> bool:
    record = _unit_record(state, endpoint, unit)
    if not record or record.get("status") not in {"complete", "empty"}:
        return False
    request_bound = _unit_request_receipts_valid(
        endpoint, unit, record, store, campaign_cache,
    )
    equation_holds = int(record.get("source_row_count", 0)) == sum((
        int(record.get("landed_a_row_count", record.get("row_count", 0))),
        int(record.get("known_excluded_row_count", 0)),
        int(record.get("quarantined_unknown_row_count", 0)),
    ))
    if (
        not record.get("source_accounting_complete")
        or not equation_holds
        or int(record.get("quarantined_unknown_row_count", 0)) != 0
        or not request_bound
    ):
        return False
    shard_coverage = _shard_coverage(state, store, endpoint, unit, record)
    if shard_coverage is not None and (
        not shard_coverage["complete"]
        or int(shard_coverage["authoritative_source_row_count"])
        != int(record.get("source_row_count", 0))
    ):
        return False
    expected_artifacts = record.get("unit_artifact_receipts")
    if not isinstance(expected_artifacts, Mapping):
        return False
    try:
        observed_artifacts = _unit_artifact_receipts(store, endpoint, unit, record)
    except SpineError:
        return False
    return bool(
        dict(expected_artifacts) == observed_artifacts
        and _unit_artifact_counts_match(observed_artifacts, record)
    )


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
    known_excluded_row_count: int = 0,
    quarantined_unknown_row_count: int = 0,
    witness_missing_row_count: int = 0,
    unmatched_master_row_count: int = 0,
    revised_key_count: int = 0,
    partition: Path | None = None,
    reason: str | None = None,
    request_receipts: Sequence[Mapping[str, Any]] = (),
    collection_method: str = "whole_market",
    generation_id: str | None = None,
    expected_ticker_count: int | None = None,
    expected_ticker_sha256: str | None = None,
    range_campaign_receipt: Mapping[str, Any] | None = None,
    persist_state: bool = True,
) -> None:
    if status not in {"complete", "empty", "failed", "collecting"}:
        raise SpineError(f"invalid state status: {status}")
    source_accounting_complete = (
        int(source_row_count)
        == int(row_count) + int(known_excluded_row_count) + int(quarantined_unknown_row_count)
    )
    endpoint_units = state.setdefault("units", {}).setdefault(endpoint, {})
    previous = endpoint_units.get(unit, {})
    record: dict[str, Any] = {
        "status": status,
        "observed_at": observed_at,
        "row_count": int(row_count),
        "source_row_count": int(source_row_count),
        "landed_a_row_count": int(row_count),
        "known_excluded_row_count": int(known_excluded_row_count),
        "quarantined_unknown_row_count": int(quarantined_unknown_row_count),
        # DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION -- telemetry only, a SUBSET of
        # landed_a_row_count above, never a fourth term in the source-row
        # equation and never a completion gate (C3).
        "witness_missing_row_count": int(witness_missing_row_count),
        "source_accounting_complete": source_accounting_complete,
        "unmatched_master_row_count": int(unmatched_master_row_count),
        "revised_key_count": int(revised_key_count),
        "attempts": int(previous.get("attempts", 0)) + 1,
        "collection_method": collection_method,
        "request_receipts": [_json_safe(dict(receipt)) for receipt in request_receipts],
    }
    if partition is not None:
        record["partition"] = partition.relative_to(store).as_posix()
    if reason:
        # Never place a vendor response or credential-bearing exception in state.
        record["reason"] = reason
    if generation_id:
        record["generation_id"] = generation_id
    if expected_ticker_count is not None:
        record["expected_ticker_count"] = int(expected_ticker_count)
    if expected_ticker_sha256 is not None:
        record["expected_ticker_sha256"] = expected_ticker_sha256
    if range_campaign_receipt is not None:
        record["range_campaign_receipt"] = _json_safe(dict(range_campaign_receipt))
    if status in {"complete", "empty"}:
        artifacts = _unit_artifact_receipts(store, endpoint, unit, record)
        if not _unit_artifact_counts_match(artifacts, record):
            raise SpineError(f"{endpoint}/{unit} terminal state disagrees with landed artifact")
        record["unit_artifact_receipts"] = artifacts
    endpoint_units[unit] = record
    if persist_state:
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
        try:
            old_identity = canonical_identity(old)
            new_identity = canonical_identity(new)
        except SpineError:
            # A non-canonical bse_mapping vendor code (same defect class as
            # the stock_basic/fund_basic legacy-code shapes) simply cannot
            # alias; excluding it from the alias map is correct on its own
            # terms, not a tolerated error -- it never participates in BSE
            # old-code resolution either way.  This is a whole-table fetch
            # with no per-row request literal to bind against, so there is
            # no fatal check being weakened here.
            continue
        if old_identity.source_exchange != "BSE" or new_identity.source_exchange != "BSE":
            raise SpineError(f"non-BSE row in bse_mapping: {old!r} -> {new!r}")
        if not new_identity.code.startswith("920"):
            raise SpineError(f"BSE canonical n_code is not in the 920 family: {new!r}")
        if old_identity.code.startswith("920"):
            raise SpineError(f"BSE old-code alias is already a 920 code: {old!r}")
        if old in aliases and aliases[old] != new:
            raise SpineError(f"conflicting BSE alias: {old} -> {aliases[old]} / {new}")
        aliases[old] = new
    return aliases


def _reference_generation_dir(store: Path, generation_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{8,96}", generation_id):
        raise SpineError("invalid reference-generation identifier")
    return store / "reference" / "generations" / generation_id


def _reference_generation_semantic_sha256(store: Path, generation_id: str) -> str:
    generation_dir = _reference_generation_dir(store, generation_id)
    paths = sorted(generation_dir.rglob("*.parquet"))
    if not paths:
        raise SpineError("reference generation contains no Parquet artifacts")
    hasher = hashlib.sha256()
    for path in paths:
        frame = _read_parquet_strict(path)
        semantic = _raw_response_semantic_sha256(frame)
        hasher.update(path.relative_to(generation_dir).as_posix().encode("utf-8"))
        hasher.update(semantic.encode("ascii"))
    return hasher.hexdigest()


def _current_reference_generation(store: Path, *, required: bool = True) -> str | None:
    pointer = store / "reference" / "current_generation.json"
    if not pointer.exists():
        if required:
            raise SpineError("reference generation pointer is absent")
        return None
    try:
        payload = json.loads(pointer.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SpineError("reference generation pointer is unreadable") from exc
    _assert_configured_token_absent_logical(payload, artifact=pointer.name)
    if set(payload) != {"generation_id", "generation_semantic_sha256"}:
        raise SpineError("reference generation pointer is malformed")
    generation_id = str(payload["generation_id"])
    generation_dir = _reference_generation_dir(store, generation_id)
    if not generation_dir.is_dir():
        raise SpineError("reference generation pointer targets an absent generation")
    expected_hash = str(payload["generation_semantic_sha256"])
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise SpineError("reference generation pointer contains an invalid semantic hash")
    if _reference_generation_semantic_sha256(store, generation_id) != expected_hash:
        raise SpineError("reference generation semantic hash does not match its pointer")
    return generation_id


def _reference_source_path(
    store: Path,
    generation_id: str,
    endpoint: str,
    unit: str | None = None,
) -> Path:
    root = _reference_generation_dir(store, generation_id)
    if endpoint == "bse_mapping":
        return root / "source_bse_mapping.parquet"
    if endpoint == "stock_basic" and unit:
        exchange, status = unit.split(":", 1)
        return root / "source_stock_basic" / f"{exchange}_{status}.parquet"
    if endpoint == "fund_basic" and unit:
        return root / "source_fund_basic" / f"E_{unit}.parquet"
    raise SpineError(f"unsupported reference source path: {endpoint}/{unit}")


def _reference_derived_path(store: Path, name: str, generation_id: str | None = None) -> Path:
    generation = generation_id or _current_reference_generation(store)
    assert generation is not None
    return _reference_generation_dir(store, generation) / name


def _load_bse_mapping(
    store: Path, generation_id: str | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    generation = generation_id or _current_reference_generation(store)
    assert generation is not None
    path = _reference_source_path(store, generation, "bse_mapping")
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


def compile_security_master(
    store: Path, generation_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compile one immutable security/reference generation before pointer promotion."""
    generation = generation_id or _current_reference_generation(store)
    assert generation is not None
    mapping, aliases = _load_bse_mapping(store, generation)
    raw_frames: list[pd.DataFrame] = []
    for exchange in EXCHANGES:
        for status in LIST_STATUSES:
            path = _reference_source_path(store, generation, "stock_basic", f"{exchange}:{status}")
            if not path.exists():
                raise SpineError(f"stock_basic reference unit absent: {exchange}/{status}")
            frame = _read_parquet_strict(path)
            if not frame.empty:
                raw_frames.append(frame)
    if not raw_frames:
        raise SpineError("stock_basic reference returned no securities")
    raw = pd.concat(raw_frames, ignore_index=True)
    required = {
        "ts_code", "symbol", "name", "market", "exchange", "curr_type",
        "list_status", "list_date", "delist_date",
    }
    missing = required - set(raw.columns)
    if missing:
        raise SpineError(f"stock_basic source missing columns {sorted(missing)}")

    rows: list[dict[str, Any]] = []
    non_canonical_classification_rows: list[dict[str, Any]] = []
    for item in raw.to_dict(orient="records"):
        try:
            ident = canonical_identity(item.get("ts_code"), bse_aliases=aliases)
        except SpineError:
            # Same try/except pattern as normalise_bak_basic: a legacy/
            # delisted-era vendor code (T-prefix, old .SS suffix) is a real
            # payload in TuShare's delisted universe.  The reference call
            # already accounted for this row's presence in the raw source
            # unit (collect_reference/_set_unit); the master itself must not
            # contain a row for an unparseable code.  A tight, independently
            # classifiable non-canonical pattern lands known_out_of_scope
            # with its narrow provenance claim; anything else stays
            # quarantined_unknown -- the same three-way split as everywhere
            # else in this file (_stock_basic_ts_code_classification).
            raw_code = str(item.get("ts_code") or "")
            provenance = _known_excluded_noncanonical_code_family(raw_code)
            non_canonical_classification_rows.append({
                "source_ts_code": raw_code,
                "ticker": raw_code,
                "security_class": "unclassified",
                "scope_classification": (
                    "known_out_of_scope" if provenance is not None else "quarantined_unknown"
                ),
                "classification_source": provenance or "tushare.stock_basic_non_canonical_ts_code",
                "effective_from": _iso(item.get("list_date")),
                "effective_to": _iso(item.get("delist_date")),
            })
            continue
        declared_exchange = str(item.get("exchange") or "").upper()
        if declared_exchange and declared_exchange != ident.source_exchange:
            raise SpineError(
                f"stock_basic exchange disagrees with code: {item.get('ts_code')} "
                f"({declared_exchange} != {ident.source_exchange})"
            )
        if str(item.get("symbol") or "").zfill(6) != ident.code:
            raise SpineError(f"stock_basic symbol/code mismatch: {item.get('ts_code')!r}")
        if str(item.get("curr_type") or "").upper() != "CNY":
            raise SpineError(f"stock_basic returned a non-CNY instrument: {item.get('ts_code')!r}")
        declared_market = str(item.get("market") or "")
        if declared_market not in set(_TUSHARE_MARKET_BY_BOARD.values()):
            raise SpineError(f"stock_basic returned a non-A instrument market: {item.get('market')!r}")
        if declared_market != _TUSHARE_MARKET_BY_BOARD[ident.board]:
            raise SpineError(
                f"stock_basic market disagrees with official code-range board: "
                f"{item.get('ts_code')!r} ({declared_market} != {ident.board})"
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
        try:
            old_ident = canonical_identity(item["o_code"])
            new_ident = canonical_identity(item["n_code"])
        except SpineError:
            # Mirrors _bse_alias_map: a non-canonical bse_mapping code cannot
            # alias, so it contributes no alias_frame row instead of crashing
            # the compile on the same raw source _bse_alias_map already
            # tolerated.
            continue
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

    classification_rows: list[dict[str, Any]] = [
        {
            "source_ts_code": row.source_ts_code,
            "ticker": row.ticker,
            "security_class": "A_share",
            "scope_classification": "known_A",
            "classification_source": "tushare.stock_basic",
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
        }
        for row in master.itertuples(index=False)
    ]
    for status in FUND_STATUSES:
        fund_path = _reference_source_path(store, generation, "fund_basic", status)
        if not fund_path.exists():
            raise SpineError(f"fund_basic reference unit absent: E/{status}")
        funds = _read_parquet_strict(fund_path)
        for item in funds.to_dict(orient="records"):
            try:
                ident = canonical_identity(item.get("ts_code"))
            except SpineError:
                # Same non-canonical-vendor-code shape as stock_basic
                # (exemplar '1610221.SZ'): every fund_basic row is already
                # known_out_of_scope regardless of ts_code parseability
                # (collect_reference's fund loop already accounts for its
                # presence wholesale as known_excluded), so the raw code
                # stands in for the identity columns instead of dropping the
                # row or crashing the compile.
                raw_code = str(item.get("ts_code") or "")
                classification_rows.append({
                    "source_ts_code": raw_code,
                    "ticker": raw_code,
                    "security_class": "exchange_fund",
                    "scope_classification": "known_out_of_scope",
                    "classification_source": "tushare.fund_basic_non_canonical_ts_code",
                    "effective_from": _iso(item.get("list_date")),
                    "effective_to": _iso(item.get("delist_date")),
                })
                continue
            classification_rows.append({
                "source_ts_code": ident.source_ts_code,
                "ticker": ident.ticker,
                "security_class": "exchange_fund",
                "scope_classification": "known_out_of_scope",
                "classification_source": "tushare.fund_basic",
                "effective_from": _iso(item.get("list_date")),
                "effective_to": _iso(item.get("delist_date")),
            })
    # Quarantined non-canonical stock_basic rows are excluded from the master
    # itself (above) but still accounted for in the classification artifact
    # this function emits, so their presence in the raw source is never a
    # silent drop.
    classification_rows.extend(non_canonical_classification_rows)
    classifications = pd.DataFrame(classification_rows).drop_duplicates(
        ["ticker", "scope_classification"], keep="last",
    )
    conflicts = classifications.groupby("ticker")["scope_classification"].nunique()
    if int((conflicts > 1).sum()):
        sample = sorted(conflicts[conflicts > 1].index)[:10]
        raise SpineError(f"instrument scope classification conflicts: {sample}")
    classifications = classifications.sort_values(
        ["scope_classification", "ticker"], kind="stable",
    ).reset_index(drop=True)
    _atomic_parquet(_reference_derived_path(store, "security_master.parquet", generation), master)
    _atomic_parquet(_reference_derived_path(store, "identity_aliases.parquet", generation), alias_frame)
    _atomic_parquet(
        _reference_derived_path(store, "instrument_classification.parquet", generation),
        classifications,
    )
    return master, alias_frame


def _promote_reference_generation(store: Path, generation_id: str) -> None:
    generation_dir = _reference_generation_dir(store, generation_id)
    required = (
        "security_master.parquet", "identity_aliases.parquet", "instrument_classification.parquet",
    )
    if any(not (generation_dir / name).exists() for name in required):
        raise SpineError("reference generation cannot be promoted before derived artifacts close")
    _atomic_json(store / "reference" / "current_generation.json", {
        "generation_id": generation_id,
        "generation_semantic_sha256": _reference_generation_semantic_sha256(
            store, generation_id,
        ),
    })


def _normalise_calendar(frame: pd.DataFrame, exchange: str, start: date, end: date) -> pd.DataFrame:
    needed = {"exchange", "cal_date", "is_open", "pretrade_date"}
    if not needed.issubset(frame.columns):
        raise SpineError(f"trade_cal missing columns {sorted(needed - set(frame.columns))}")
    out = frame.copy()
    declared = set(out["exchange"].dropna().astype(str).str.upper())
    if declared != {exchange}:
        raise SpineError(
            f"trade_cal response exchange does not bind to request {exchange}: {sorted(declared)}"
        )
    out["exchange"] = out["exchange"].astype(str).str.upper()
    out["cal_date"] = out["cal_date"].map(_iso)
    out["pretrade_date"] = out["pretrade_date"].map(_iso)
    raw_open = out["is_open"].copy()
    out["is_open"] = pd.to_numeric(raw_open, errors="coerce").astype("Int64")
    if raw_open.notna().sum() != out["is_open"].notna().sum():
        raise SpineError(f"trade_cal returned non-numeric is_open values for {exchange}")
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

    # The epoch bounds the AXIS, not merely the request.  Every set below was
    # previously derived from all landed partitions regardless of the requested
    # range, so a pre-epoch partition sitting on disk would silently occupy the
    # low ordinals and shift every position -- moving the collection constant
    # alone would not re-anchor anything.  Pre-epoch rows are therefore removed
    # here, by definition, and reported rather than silently dropped.
    epoch_iso = MAINLAND_CALENDAR_EPOCH.isoformat()
    if start < MAINLAND_CALENDAR_EPOCH:
        raise SpineError(
            f"{PRE_EPOCH_SOURCE_STATE}: the mainland session axis is frozen at "
            f"{epoch_iso} under definition {MAINLAND_CALENDAR_EPOCH_DEFINITION}; "
            f"refusing to compile from {start.isoformat()}. Pre-epoch history is "
            "unsupported source, not closed sessions -- it is never imputed and "
            "never assigned a session position."
        )
    pre_epoch = calendar[calendar["cal_date"] < epoch_iso]
    if not pre_epoch.empty:
        excluded = {
            exchange: int((pre_epoch["exchange"] == exchange).sum())
            for exchange in CALENDAR_EXCHANGES
        }
        log.info(
            "%s: excluded %d landed calendar row(s) before epoch %s from the "
            "session axis (%s)",
            PRE_EPOCH_SOURCE_STATE, len(pre_epoch), epoch_iso, excluded,
        )
        calendar = calendar[calendar["cal_date"] >= epoch_iso]
        if calendar.empty:
            raise SpineError(
                f"every landed calendar row precedes the {epoch_iso} epoch; "
                "no session axis can be compiled"
            )

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

    # Safe to read one venue: the equality checks above already proved
    # opens["SSE"] == opens["SZSE"], so this is a proven-identical set rather
    # than SSE history standing in for SZSE history.
    all_calendar_dates = sorted(opens["SSE"])
    position = {session: idx for idx, session in enumerate(all_calendar_dates)}
    sessions = pd.DataFrame({"trade_date": all_calendar_dates})
    sessions["market_session_position"] = sessions["trade_date"].map(position).astype("int64")
    sessions["calendar_provenance"] = "tushare.trade_cal:SSE=SZSE"
    sessions["bse_calendar_provenance"] = "derived_from_attested_SSE_SZSE_consensus"
    # Stamp the axis definition so an artifact can never be silently compared
    # against one minted under a different epoch.
    sessions["calendar_epoch"] = epoch_iso
    sessions["calendar_epoch_definition"] = MAINLAND_CALENDAR_EPOCH_DEFINITION
    _atomic_parquet(store / "reference" / "market_sessions.parquet", sessions)
    return sessions


def _master_maps(
    store: Path,
    generation_id: str | None = None,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, dict[str, Any]]]:
    generation = generation_id or _current_reference_generation(store)
    assert generation is not None
    master_path = _reference_derived_path(store, "security_master.parquet", generation)
    if not master_path.exists():
        raise SpineError("security master is absent; reference bootstrap is incomplete")
    master = _read_parquet_strict(master_path)
    _, aliases = _load_bse_mapping(store, generation)
    lookup = {str(row["ticker"]): row for row in master.to_dict(orient="records")}
    return master, aliases, lookup


def _pit_partition(store: Path, trade_date: date) -> Path:
    return (
        store / PIT_UNIVERSE_ENDPOINT / f"year={trade_date.year:04d}"
        / f"month={trade_date.month:02d}" / "part.parquet"
    )


def _instrument_scope_maps(
    store: Path, trade_date: str | date, generation_id: str | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return independently witnessed A and out-of-scope ticker provenance."""
    generation = generation_id or _current_reference_generation(store)
    assert generation is not None
    classifications = _read_parquet_strict(_reference_derived_path(
        store, "instrument_classification.parquet", generation,
    ))
    known_a = {
        str(row.ticker): str(row.classification_source)
        for row in classifications[
            classifications["scope_classification"] == "known_A"
        ].itertuples(index=False)
    }
    known_out = {
        str(row.ticker): str(row.classification_source)
        for row in classifications[
            classifications["scope_classification"] == "known_out_of_scope"
        ].itertuples(index=False)
    }
    day = _parse_date(trade_date)
    if day >= PIT_UNIVERSE_START:
        path = _pit_partition(store, day)
        if path.exists():
            pit = _read_parquet_strict(path)
            subset = pit[pit["trade_date"].astype(str) == day.isoformat()]
            for ticker in subset.get("ticker", pd.Series(dtype=str)).astype(str):
                known_a[ticker] = "tushare.bak_basic_exact_daily"
    conflict = sorted(set(known_a) & set(known_out))
    if conflict:
        raise SpineError(f"instrument scope maps conflict: {conflict[:10]}")
    return known_a, known_out


def _all_known_a_tickers(store: Path, generation_id: str | None = None) -> set[str]:
    generation = generation_id or _current_reference_generation(store)
    assert generation is not None
    classifications = _read_parquet_strict(_reference_derived_path(
        store, "instrument_classification.parquet", generation,
    ))
    known = set(classifications.loc[
        classifications["scope_classification"] == "known_A", "ticker",
    ].astype(str))
    for path in sorted((store / PIT_UNIVERSE_ENDPOINT).glob("year=*/month=*/part.parquet")):
        frame = _read_parquet_strict(path)
        known.update(frame.get("ticker", pd.Series(dtype=str)).astype(str))
    return known


def _range_query_identities(
    store: Path,
    start: date,
    end: date,
    generation_id: str,
) -> tuple[list[dict[str, str]], str]:
    """Freeze every historical A query identity, including both BSE code eras.

    ``stock_basic`` supplies lifecycle overlap while in-range ``bak_basic`` rows
    can only expand the union.  Every official BSE old-code mapping is queried
    alongside its canonical 920 code; equal overlap is de-duplicated by the
    range campaign and disagreement blocks transposition.
    """
    master, bse_aliases, lookup = _master_maps(store, generation_id)
    tickers: set[str] = set()
    for row in master.to_dict(orient="records"):
        effective_from = _iso(row.get("effective_from"))
        effective_to = _iso(row.get("effective_to"))
        if effective_from is None:
            continue
        if _parse_date(effective_from) <= end and (
            effective_to is None or _parse_date(effective_to) >= start
        ):
            tickers.add(str(row["ticker"]))
    pit_receipts: list[dict[str, Any]] = []
    for path in sorted((store / PIT_UNIVERSE_ENDPOINT).glob("year=*/month=*/part.parquet")):
        frame = _read_parquet_strict(path)
        if frame.empty or "trade_date" not in frame.columns:
            continue
        subset = frame[
            (frame["trade_date"].astype(str) >= start.isoformat())
            & (frame["trade_date"].astype(str) <= end.isoformat())
        ].copy()
        if subset.empty:
            continue
        tickers.update(subset.get("ticker", pd.Series(dtype=str)).astype(str))
        pit_receipts.append({
            "path": path.relative_to(store).as_posix(),
            "row_count": len(subset),
            "semantic_sha256": _raw_response_semantic_sha256(subset),
        })
    absent = sorted(tickers - set(lookup))
    if absent:
        raise SpineError(f"range universe contains tickers absent from pinned master: {absent[:10]}")

    identities: list[dict[str, str]] = []
    for ticker in sorted(tickers):
        row = lookup[ticker]
        canonical_source = _source_ts_code(ticker)
        identities.append({
            "canonical_ticker": ticker,
            "source_ts_code": canonical_source,
            "alias_kind": "canonical",
        })
        observed_source = _source_ts_code(row.get("source_ts_code"))
        if observed_source != canonical_source:
            identities.append({
                "canonical_ticker": ticker,
                "source_ts_code": observed_source,
                "alias_kind": "stock_basic_observed_alias",
            })
    for old_source, new_source in sorted(bse_aliases.items()):
        new_identity = canonical_identity(new_source, bse_aliases=bse_aliases)
        if new_identity.ticker not in tickers:
            continue
        identities.append({
            "canonical_ticker": new_identity.ticker,
            "source_ts_code": _source_ts_code(old_source),
            "alias_kind": "bse_old_code",
        })
    deduplicated = {
        (item["canonical_ticker"], item["source_ts_code"]): item
        for item in identities
    }
    identities = sorted(
        deduplicated.values(),
        key=lambda item: (
            item["canonical_ticker"], item["alias_kind"] != "canonical",
            item["source_ts_code"],
        ),
    )
    witness = {
        "reference_generation_id": generation_id,
        "reference_generation_semantic_sha256": _reference_generation_semantic_sha256(
            store, generation_id,
        ),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "canonical_tickers": sorted(tickers),
        "pit_partition_receipts": pit_receipts,
        "query_identities": identities,
    }
    return identities, hashlib.sha256(_canonical_json_bytes(witness)).hexdigest()


def _range_sessions(store: Path, start: date, end: date) -> list[str]:
    sessions = _read_parquet_strict(store / "reference" / "market_sessions.parquet")
    return sorted(
        value for value in sessions["trade_date"].astype(str)
        if start.isoformat() <= value <= end.isoformat()
    )


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


def _is_a_share_identity(identity: Identity) -> bool:
    if identity.source_exchange == "SSE":
        return identity.code.startswith("6")
    if identity.source_exchange == "SZSE":
        return identity.code.startswith(("0", "3"))
    return identity.code.startswith(("43", "83", "87", "88", "920"))


def _known_out_of_scope_code_family(identity: Identity) -> str | None:
    """Return independent official-code provenance for exchange B shares."""
    if identity.source_exchange == "SSE" and identity.code.startswith("900"):
        return "SSE_security_code_900xxx_B_share"
    if identity.source_exchange == "SZSE" and identity.code.startswith("200"):
        return "SZSE_security_code_200xxx_B_share"
    return None


def _validate_response_binding(
    endpoint: str,
    frame: pd.DataFrame,
    params: Mapping[str, Any],
) -> tuple[list[int], list[int]]:
    """Require exact returned fields and prove every row belongs to the request.

    Returns ``(known_excluded_ordinals, quarantined_unknown_ordinals)`` for
    ``stock_basic``/``fund_basic`` rows whose ``ts_code`` is not a canonical
    SH/SZ/BJ identity -- legacy/delisted-era vendor codes (a T-prefix, an old
    ``.SS`` suffix, a non-6-digit fund code such as ``'1610221.SZ'``) are
    real payloads in TuShare's reference universe.  Those rows still must
    bind to the requested literal params (exchange/list_status for
    stock_basic, market/status for fund_basic) exactly as before; every
    other, identity-dependent check (the venue/board/currency checks that
    require a parsed ``Identity``) is skipped for them.  A non-canonical row
    matching a tight, independently classifiable pattern (see
    ``_known_excluded_noncanonical_code_family``, e.g. a T-prefixed legacy
    vendor code) is reported as known-excluded; every other non-canonical
    row is reported as quarantined-unknown.  Both lists are empty for every
    other endpoint.
    """
    expected_columns = ENDPOINT_FIELDS[endpoint].split(",")
    if list(frame.columns) != expected_columns:
        raise SpineError(
            f"{endpoint} returned schema does not exactly match requested fields: "
            f"expected={expected_columns} actual={list(frame.columns)}"
        )
    known_excluded_rows: list[int] = []
    quarantined_rows: list[int] = []
    if endpoint == "stock_basic":
        exchange = str(params.get("exchange") or "").upper()
        status = str(params.get("list_status") or "").upper()
        for ordinal, item in enumerate(frame.to_dict(orient="records")):
            if str(item["exchange"] or "").upper() != exchange:
                raise SpineError("stock_basic response does not bind to requested exchange")
            if str(item["list_status"] or "").upper() != status:
                raise SpineError("stock_basic response does not bind to requested list_status")
            try:
                ident = canonical_identity(item["ts_code"])
            except SpineError:
                if _known_excluded_noncanonical_code_family(item["ts_code"]) is not None:
                    known_excluded_rows.append(ordinal)
                else:
                    quarantined_rows.append(ordinal)
                continue
            if ident.source_exchange != exchange:
                raise SpineError("stock_basic response does not bind to requested exchange")
            if str(item["curr_type"] or "").upper() != "CNY":
                raise SpineError("stock_basic response contains a non-CNY instrument")
            if str(item["symbol"] or "").zfill(6) != ident.code:
                raise SpineError("stock_basic symbol does not match ts_code")
            declared_market = str(item["market"] or "")
            if declared_market not in set(_TUSHARE_MARKET_BY_BOARD.values()):
                raise SpineError("stock_basic response contains a non-A instrument market")
            if declared_market != _TUSHARE_MARKET_BY_BOARD[ident.board]:
                raise SpineError("stock_basic market does not match its official board code range")
            if not _is_a_share_identity(ident):
                raise SpineError("stock_basic response contains a non-A code family")
    elif endpoint == "fund_basic":
        market = str(params.get("market") or "")
        status = str(params.get("status") or "")
        for ordinal, item in enumerate(frame.to_dict(orient="records")):
            if str(item["market"] or "") != market or str(item["status"] or "") != status:
                raise SpineError("fund_basic response does not bind to requested market/status")
            try:
                ident = canonical_identity(item["ts_code"])
            except SpineError:
                # A legacy/non-6-digit vendor fund code (exemplar
                # '1610221.SZ') is a real fund_basic payload row.  The
                # literal market/status binding above is still proved for
                # it; the venue check is identity-dependent and is skipped,
                # matching the stock_basic treatment above.  fund_basic rows
                # are already wholesale known_excluded in
                # collect_reference's fund loop (row_count=0,
                # known_excluded_row_count=len(frame)), so this only feeds
                # the per-call receipt counts, not the unit accounting.
                if _known_excluded_noncanonical_code_family(item["ts_code"]) is not None:
                    known_excluded_rows.append(ordinal)
                else:
                    quarantined_rows.append(ordinal)
                continue
            if ident.source_exchange not in {"SSE", "SZSE"}:
                raise SpineError("fund_basic response contains a non-SH/SZ venue")
    elif endpoint == "trade_cal":
        exchange = str(params.get("exchange") or "").upper()
        declared = set(frame["exchange"].dropna().astype(str).str.upper())
        if frame.empty or declared != {exchange}:
            raise SpineError("trade_cal response does not bind to requested exchange")
        start = _parse_date(params["start_date"])
        end = _parse_date(params["end_date"])
        dates = {_parse_date(value) for value in frame["cal_date"]}
        expected = {value.date() for value in pd.date_range(start, end, freq="D")}
        if dates != expected:
            raise SpineError("trade_cal response does not bind to the exact requested date range")
    elif endpoint == "namechange":
        start = _parse_date(params["start_date"])
        end = _parse_date(params["end_date"])
        for value in frame["ann_date"]:
            if value is None or pd.isna(value) or not start <= _parse_date(value) <= end:
                raise SpineError("namechange response announcement anchor is outside request range")
    elif endpoint in DAILY_ENDPOINTS | {PIT_UNIVERSE_ENDPOINT}:
        expected_date = _parse_date(params["trade_date"])
        if any(_parse_date(value) != expected_date for value in frame["trade_date"]):
            raise SpineError(f"{endpoint} response crossed the requested trade_date")
        requested_code = params.get("ts_code")
        if requested_code:
            expected_code = _source_ts_code(requested_code)
            if any(_source_ts_code(value) != expected_code for value in frame["ts_code"]):
                raise SpineError(f"{endpoint} ticker shard crossed the requested ts_code")
    return known_excluded_rows, quarantined_rows


def _strict_numeric(
    value: Any,
    *,
    field: str,
    allow_missing: bool = True,
    minimum: float | None = None,
    integral: bool = False,
    allowed: set[int] | None = None,
) -> float | int | None:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        if allow_missing:
            return None
        raise SpineError(f"{field} is required")
    if isinstance(value, bool):
        raise SpineError(f"{field} must be numeric")
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed) or not math.isfinite(float(parsed)):
        raise SpineError(f"{field} must be a finite numeric value")
    number = float(parsed)
    if minimum is not None and number < minimum:
        raise SpineError(f"{field} must be >= {minimum}")
    if integral:
        if not number.is_integer():
            raise SpineError(f"{field} must be an integer")
        integer = int(number)
        if allowed is not None and integer not in allowed:
            raise SpineError(f"{field} is outside its documented domain")
        return integer
    return number


def _classified_source_row(
    item: Mapping[str, Any],
    *,
    ordinal: int,
    classification: str,
    classification_source: str,
    expected_date: str,
) -> dict[str, Any]:
    return {
        "source_row_ordinal": int(ordinal),
        "trade_date": expected_date,
        "raw_ts_code": str(item.get("ts_code") or ""),
        "scope_classification": classification,
        "classification_source": classification_source,
        "raw_payload_json": json.dumps(
            {str(key): _json_safe(value) for key, value in sorted(item.items())},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ),
    }


def normalise_bak_basic(
    frame: pd.DataFrame,
    trade_date: str | date,
    store: Path,
    generation_id: str | None = None,
) -> NormalisedSourceUnit:
    """Land the official post-2016 point-in-time A-share universe witness."""
    expected_date = _parse_date(trade_date).isoformat()
    sessions = _session_map(store)
    if expected_date not in sessions:
        raise SpineError(f"off-calendar endpoint unit: bak_basic/{expected_date}")
    generation = generation_id or _current_reference_generation(store)
    assert generation is not None
    master, aliases, _ = _master_maps(store, generation)
    known_a = set(master["ticker"].astype(str))
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    numeric_fields = [
        field for field in ENDPOINT_FIELDS[PIT_UNIVERSE_ENDPOINT].split(",")
        if field not in {"trade_date", "ts_code", "name", "industry", "area", "list_date"}
    ]
    for ordinal, item in enumerate(frame.to_dict(orient="records")):
        try:
            ident = canonical_identity(item.get("ts_code"), bse_aliases=aliases)
        except SpineError:
            ident = None
        code_exclusion = _known_out_of_scope_code_family(ident) if ident else None
        if code_exclusion:
            excluded.append(_classified_source_row(
                item, ordinal=ordinal, classification="known_out_of_scope",
                classification_source=code_exclusion, expected_date=expected_date,
            ))
            continue
        if ident is None:
            unknown.append(_classified_source_row(
                item, ordinal=ordinal, classification="quarantined_unknown",
                classification_source="bak_basic_unparseable_ts_code",
                expected_date=expected_date,
            ))
            continue
        if not _is_a_share_identity(ident):
            unknown.append(_classified_source_row(
                item, ordinal=ordinal, classification="quarantined_unknown",
                classification_source="bak_basic_non_a_share_identity",
                expected_date=expected_date,
            ))
            continue
        # DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION -- the current stock_basic
        # snapshot is a lifecycle/reference WITNESS, not exhaustive historical
        # membership authority.  A parseable A-share identity this PIT row
        # observes but the current snapshot no longer publishes still LANDS as
        # a legal union member; the current-snapshot miss is recorded as
        # telemetry on the row, never as a reason to quarantine it.
        row = {
            **_identity_columns(ident),
            "trade_date": expected_date,
            "market_session_position": sessions[expected_date],
            "name": str(item.get("name") or ""),
            "industry": str(item.get("industry") or ""),
            "area": str(item.get("area") or ""),
            "list_date": _iso(item.get("list_date")),
            "source": "tushare.bak_basic_exact_daily",
            "current_stock_basic_witness_missing": bool(ident.ticker not in known_a),
        }
        for field in numeric_fields:
            minimum = 0.0 if field in {
                "float_share", "total_share", "total_assets", "liquid_assets", "fixed_assets",
                "holder_num",
            } else None
            row[field] = _strict_numeric(
                item.get(field), field=f"bak_basic.{field}", allow_missing=True,
                minimum=minimum, integral=field == "holder_num",
            )
        rows.append(row)
    landed = pd.DataFrame(rows)
    if not landed.empty and _duplicates(landed, KEY_COLUMNS["bak_basic"]):
        raise SpineError("bak_basic response duplicated exact-date A-share keys")
    return NormalisedSourceUnit(
        landed_a=landed.sort_values(KEY_COLUMNS["bak_basic"], kind="stable").reset_index(drop=True)
        if not landed.empty else landed,
        known_excluded=pd.DataFrame(excluded, columns=[
            "source_row_ordinal", "trade_date", "raw_ts_code", "scope_classification",
            "classification_source", "raw_payload_json",
        ]),
        quarantined_unknown=pd.DataFrame(unknown),
    )


def normalise_name_history(
    frame: pd.DataFrame,
    store: Path,
    unit_date: str | date,
    generation_id: str | None = None,
) -> NormalisedSourceUnit:
    """Classify every namechange row; only independently known A names land."""
    generation = generation_id or _current_reference_generation(store)
    assert generation is not None
    _, aliases, _ = _master_maps(store, generation)
    known_a, known_out = _instrument_scope_maps(store, unit_date, generation)
    known_a.update({
        ticker: "tushare.bak_basic_exact_daily"
        for ticker in _all_known_a_tickers(store, generation)
    })
    expected_date = _parse_date(unit_date).isoformat()
    required = {"ts_code", "name", "start_date", "end_date", "ann_date", "change_reason"}
    if not required.issubset(frame.columns) and not frame.empty:
        raise SpineError(f"namechange missing columns {sorted(required - set(frame.columns))}")
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for ordinal, item in enumerate(frame.to_dict(orient="records")):
        try:
            ident = canonical_identity(item.get("ts_code"), bse_aliases=aliases)
        except SpineError:
            ident = None
        code_exclusion = _known_out_of_scope_code_family(ident) if ident else None
        if ident and (code_exclusion or ident.ticker in known_out):
            excluded.append(_classified_source_row(
                item, ordinal=ordinal, classification="known_out_of_scope",
                classification_source=code_exclusion or known_out[ident.ticker],
                expected_date=expected_date,
            ))
            continue
        if ident is None or ident.ticker not in known_a:
            unknown.append(_classified_source_row(
                item, ordinal=ordinal, classification="quarantined_unknown",
                classification_source="namechange_absent_from_A_universe_witness",
                expected_date=expected_date,
            ))
            continue
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
    classification_columns = [
        "source_row_ordinal", "trade_date", "raw_ts_code", "scope_classification",
        "classification_source", "raw_payload_json",
    ]
    return NormalisedSourceUnit(
        landed_a=out,
        known_excluded=pd.DataFrame(excluded, columns=classification_columns),
        quarantined_unknown=pd.DataFrame(unknown, columns=classification_columns),
    )


def normalise_daily_endpoint(
    endpoint: str,
    frame: pd.DataFrame,
    trade_date: str | date,
    store: Path,
    generation_id: str | None = None,
) -> NormalisedSourceUnit:
    """Classify every source row, landing only independently witnessed A shares."""
    if endpoint not in DAILY_ENDPOINTS:
        raise SpineError(f"unsupported daily spine endpoint: {endpoint}")
    expected_date = _parse_date(trade_date).isoformat()
    sessions = _session_map(store)
    if expected_date not in sessions:
        raise SpineError(f"off-calendar endpoint unit: {endpoint}/{expected_date}")
    generation = generation_id or _current_reference_generation(store)
    assert generation is not None
    _, aliases, _ = _master_maps(store, generation)
    known_a, known_out = _instrument_scope_maps(store, expected_date, generation)

    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for ordinal, item in enumerate(frame.to_dict(orient="records")):
        source_date = _iso(item.get("trade_date"))
        if source_date != expected_date:
            raise SpineError(
                f"{endpoint} response crossed requested session {expected_date}: {source_date}"
            )
        try:
            ident = canonical_identity(item.get("ts_code"), bse_aliases=aliases)
        except SpineError:
            ident = None
        code_exclusion = _known_out_of_scope_code_family(ident) if ident else None
        if code_exclusion:
            excluded.append(_classified_source_row(
                item, ordinal=ordinal, classification="known_out_of_scope",
                classification_source=code_exclusion, expected_date=expected_date,
            ))
            continue
        if ident is None or ident.ticker not in known_a | known_out:
            unknown.append(_classified_source_row(
                item, ordinal=ordinal, classification="quarantined_unknown",
                classification_source="absent_from_stock_basic_fund_basic_and_bak_basic",
                expected_date=expected_date,
            ))
            continue
        if ident.ticker in known_out:
            excluded.append(_classified_source_row(
                item, ordinal=ordinal, classification="known_out_of_scope",
                classification_source=known_out[ident.ticker], expected_date=expected_date,
            ))
            continue
        row: dict[str, Any] = {
            **_identity_columns(ident),
            "trade_date": expected_date,
            "market_session_position": sessions[expected_date],
            "source": f"tushare.{endpoint}",
        }
        if endpoint == "daily":
            volume = _strict_numeric(
                item.get("vol"), field="daily.vol", allow_missing=False, minimum=0.0,
            )
            amount = _strict_numeric(
                item.get("amount"), field="daily.amount", allow_missing=False, minimum=0.0,
            )
            row["volume_lots"] = volume
            row["amount_cny_thousands"] = amount
            row["positive_volume"] = bool(float(volume) > 0.0)
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
                row[column] = _strict_numeric(
                    item.get(column), field=f"daily.{column}", allow_missing=True,
                )
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
            for column in [
                c for c in ENDPOINT_FIELDS[endpoint].split(",")
                if c not in {"ts_code", "trade_date", "close", "limit_status"}
            ]:
                minimum = 0.0 if column in {
                    "close", "turnover_rate", "turnover_rate_f", "volume_ratio", "pb", "ps",
                    "ps_ttm", "dv_ratio", "dv_ttm", "total_share", "float_share", "free_share",
                    "total_mv", "circ_mv",
                } else None
                row[column] = _strict_numeric(
                    item.get(column), field=f"daily_basic.{column}", allow_missing=True,
                    minimum=minimum,
                )
            close_cents = _quote_price_cents(
                item.get("close"), field="daily_basic.close", allow_missing=False,
            )
            assert close_cents is not None
            row["close_cents"] = close_cents
            row["close"] = float(Decimal(close_cents) / A_SHARE_PRICE_SCALE)
            row["limit_status"] = _strict_numeric(
                item.get("limit_status"), field="daily_basic.limit_status", allow_missing=True,
                integral=True, allowed=set(range(7)),
            )
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
                up_limit_cents > pre_close_cents >= down_limit_cents
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
            if not row["name"] or not row["st_type"] or not row["st_type_name"]:
                raise SpineError("stock_st exact membership requires name/type/type_name")
            row["is_st"] = True
            row["st_provenance"] = "tushare.stock_st_exact_daily"
        rows.append(row)
    landed = pd.DataFrame(rows)
    if not landed.empty and _duplicates(landed, KEY_COLUMNS[endpoint]):
        raise SpineError(f"{endpoint} response duplicated canonical A-share keys")
    if not landed.empty:
        landed = landed.sort_values(KEY_COLUMNS[endpoint], kind="stable").reset_index(drop=True)
    columns = [
        "source_row_ordinal", "trade_date", "raw_ts_code", "scope_classification",
        "classification_source", "raw_payload_json",
    ]
    return NormalisedSourceUnit(
        landed_a=landed,
        known_excluded=pd.DataFrame(excluded, columns=columns),
        quarantined_unknown=pd.DataFrame(unknown, columns=columns),
    )


def _monthly_partition(store: Path, endpoint: str, trade_date: date) -> Path:
    return store / endpoint / f"year={trade_date.year:04d}" / f"month={trade_date.month:02d}" / "part.parquet"


def _classification_partition(
    store: Path, classification: str, endpoint: str, trade_date: date,
) -> Path:
    if classification not in {"known_excluded", "quarantined_unknown"}:
        raise SpineError("invalid source-row classification partition")
    return (
        store / "source_row_classification" / classification / endpoint
        / f"year={trade_date.year:04d}" / f"month={trade_date.month:02d}" / "part.parquet"
    )


def _request_receipt_path(store: Path, endpoint: str, unit: str, request_id: str) -> Path:
    safe_unit = re.sub(r"[^A-Za-z0-9_.-]", "_", unit)
    return store / "receipts" / "requests" / endpoint / safe_unit / f"{request_id}.json"


def _mark_non_authoritative_cap_probe(
    store: Path, receipt: Mapping[str, Any], *, source_cap: int,
) -> dict[str, Any]:
    """Atomically relabel a capped whole-market response as discarded evidence.

    The response proves that the source cap was reached, but its truncated rows
    are not part of the authoritative unit equation.  Persist the role on the
    canonical request receipt before any ticker shard is attempted so a crash
    cannot leave the probe masquerading as an accepted authoritative response.
    """
    relative = receipt.get("path")
    if not relative:
        raise SpineError("capped response is missing its persisted request receipt")
    path = _contained_store_path(store, relative)
    if not path.is_file():
        raise SpineError("capped response request receipt is absent")
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SpineError("capped response request receipt is unreadable") from exc
    if not isinstance(decoded, dict) or any(
        decoded.get(field) != receipt.get(field)
        for field in _REQUEST_RECEIPT_BINDING_FIELDS
        if field not in {"receipt_role", "discarded_probe_row_count"}
    ):
        raise SpineError("capped response receipt disagrees with its embedded evidence")
    response_count = decoded.get("response_row_count")
    if (
        decoded.get("response_status") != "accepted"
        or not isinstance(response_count, int)
        or response_count < source_cap
    ):
        raise SpineError("only an accepted at-cap response can become a cap probe")
    decoded.update({
        "response_status": "non_authoritative_cap_probe",
        "receipt_role": "discarded_non_authoritative_cap_probe",
        "discarded_probe_row_count": response_count,
    })
    _atomic_json(path, decoded)
    decoded["path"] = path.relative_to(store).as_posix()
    return decoded


def _shard_partition(store: Path, endpoint: str, trade_date: date, ticker: str) -> Path:
    safe_ticker = re.sub(r"[^A-Za-z0-9_.-]", "_", ticker)
    return (
        store / "source_shards" / endpoint / f"year={trade_date.year:04d}"
        / f"month={trade_date.month:02d}" / trade_date.isoformat() / f"{safe_ticker}.parquet"
    )


def _name_partition(store: Path, year: int) -> Path:
    return store / "name_history" / f"year={year:04d}.parquet"


def _calendar_partition(store: Path, year: int) -> Path:
    return store / "reference" / "trade_calendar" / f"year={year:04d}.parquet"


def _year_segments(start: date, end: date) -> list[tuple[int, date, date]]:
    return [
        (year, max(start, date(year, 1, 1)), min(end, date(year, 12, 31)))
        for year in range(start.year, end.year + 1)
    ]


def _raw_response_semantic_sha256(frame: pd.DataFrame) -> str:
    rows = [
        _canonical_json_bytes({str(key): _json_safe(value) for key, value in sorted(item.items())})
        for item in frame.to_dict(orient="records")
    ]
    return hashlib.sha256(b"\n".join(sorted(rows))).hexdigest()


class TushareAShareSpineCollector:
    """Bounded request orchestrator.  Network behavior is injectable for tests."""

    def __init__(
        self,
        store: Path = DEFAULT_STORE,
        *,
        query: Callable[..., pd.DataFrame | None] | None = None,
        now: Callable[[], datetime] = _utc_now,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        canary: bool = False,
    ) -> None:
        if not BULK_HISTORICAL_BACKFILL_READY and not canary:
            raise SpineError(
                "full-A collector is foundation-only: scalable ticker-range cap fallback "
                "has not been code-reviewed, so live/injected collection is disabled "
                "outside a bounded canary window (canary=True)"
            )
        if canary and int(max_requests) > CANARY_MAX_REQUESTS:
            raise SpineError(
                f"canary window is capped at {CANARY_MAX_REQUESTS} requests; "
                f"got max_requests={max_requests}"
            )
        self.canary = bool(canary)
        self.store = _validate_private_store_path(Path(store))
        self.query = query or tc.query
        self.now = now
        self.max_requests = int(max_requests)
        self.requests_made = 0
        self.failures: list[dict[str, str]] = []
        self.state = load_state(self.store)
        # Generations are immutable after atomic promotion.  Verify the pointer
        # and every generation artifact once for this collector operation, then
        # pass the pinned id through hot-path lookups instead of reopening the
        # complete reference set for every endpoint/day.
        self.reference_generation = _current_reference_generation(
            self.store, required=False,
        )

    @property
    def observed_at(self) -> str:
        return self.now().astimezone(timezone.utc).isoformat()

    def _call(self, endpoint: str, unit: str, **params: Any) -> VendorResponse:
        if self.max_requests and self.requests_made >= self.max_requests:
            raise RequestBudgetExhausted("request cap reached; state is resumable")
        self.requests_made += 1
        requested_fields = ENDPOINT_FIELDS[endpoint]
        request_contract = {
            "endpoint": endpoint,
            "fields": requested_fields.split(","),
            "params": {str(key): _json_safe(value) for key, value in sorted(params.items())},
            "unit": unit,
        }
        request_id = hashlib.sha256(_canonical_json_bytes(request_contract)).hexdigest()
        # _return_empty distinguishes an authenticated zero-row event day from
        # an unavailable/failed call while preserving query()'s legacy default.
        frame = self.query(endpoint, fields=requested_fields, _return_empty=True, **params)
        receipt: dict[str, Any] = {
            "request_id": request_id,
            "endpoint": endpoint,
            "unit": unit,
            "fields": requested_fields.split(","),
            "params": request_contract["params"],
            "request_contract_sha256": hashlib.sha256(
                _canonical_json_bytes(request_contract)
            ).hexdigest(),
            "observed_at": self.observed_at,
            "response_status": "unavailable",
            "response_row_count": 0,
            "response_columns": [],
            "response_semantic_sha256": None,
            "non_canonical_identity_row_count": 0,
            "known_excluded_noncanonical_row_count": 0,
        }
        if frame is not None:
            try:
                if not isinstance(frame, pd.DataFrame):
                    raise SpineError(f"{endpoint} returned a non-DataFrame response")
                _assert_configured_token_absent_logical(frame, artifact=f"response:{endpoint}/{unit}")
                # Preserve what was actually returned before judging it.  A
                # rejected schema is evidence, not a fictitious zero-row miss.
                receipt.update({
                    "response_status": "observed_pending_validation",
                    "response_row_count": len(frame),
                    "response_columns": list(frame.columns),
                    "response_semantic_sha256": _raw_response_semantic_sha256(frame),
                })
                known_excluded_noncanonical_rows, quarantined_noncanonical_rows = (
                    _validate_response_binding(endpoint, frame, params)
                )
                receipt["known_excluded_noncanonical_row_count"] = len(
                    known_excluded_noncanonical_rows
                )
                receipt["non_canonical_identity_row_count"] = (
                    len(known_excluded_noncanonical_rows) + len(quarantined_noncanonical_rows)
                )
            except SpineError:
                receipt["response_status"] = "rejected_contract"
                _atomic_json(_request_receipt_path(self.store, endpoint, unit, request_id), receipt)
                raise
            receipt.update({
                "response_status": "accepted_empty" if frame.empty else "accepted",
            })
        path = _request_receipt_path(self.store, endpoint, unit, request_id)
        _atomic_json(path, receipt)
        receipt["path"] = path.relative_to(self.store).as_posix()
        return VendorResponse(frame=frame, receipt=receipt)

    def _mark_failed(
        self,
        endpoint: str,
        unit: str,
        reason: str,
        *,
        request_receipts: Sequence[Mapping[str, Any]] = (),
        source_row_count: int = 0,
        row_count: int = 0,
        known_excluded_row_count: int = 0,
        quarantined_unknown_row_count: int = 0,
        witness_missing_row_count: int = 0,
        unmatched_master_row_count: int = 0,
        collection_method: str = "whole_market",
        generation_id: str | None = None,
    ) -> None:
        self.failures.append({"endpoint": endpoint, "unit": unit, "reason": reason})
        _set_unit(
            self.state, self.store, endpoint, unit, status="failed",
            observed_at=self.observed_at, reason=reason,
            request_receipts=request_receipts, source_row_count=source_row_count,
            row_count=row_count, known_excluded_row_count=known_excluded_row_count,
            quarantined_unknown_row_count=quarantined_unknown_row_count,
            witness_missing_row_count=witness_missing_row_count,
            unmatched_master_row_count=unmatched_master_row_count,
            collection_method=collection_method, generation_id=generation_id,
        )

    def collect_reference(self, *, refresh: bool = False) -> bool:
        current = self.reference_generation
        self.reference_generation = current
        generation_state = self.state.setdefault("reference_generation", {})
        staging = generation_state.get("staging_id")
        if staging and current == staging:
            generation_state.update({"current_id": staging, "staging_id": None})
            _atomic_json(self.store / "collection_state.json", self.state)
            staging = None
        if current and not refresh and not staging:
            for name in (
                "security_master.parquet", "identity_aliases.parquet",
                "instrument_classification.parquet",
            ):
                if not _reference_derived_path(self.store, name, current).exists():
                    raise SpineError("current reference generation is missing a derived artifact")
            return True
        if not staging:
            contract_hash = hashlib.sha256(_canonical_json_bytes({
                endpoint: ENDPOINT_FIELDS[endpoint]
                for endpoint in ("bse_mapping", "stock_basic", "fund_basic")
            })).hexdigest()[:12]
            timestamp = self.now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            staging = f"ref-{timestamp}-{contract_hash}"
            generation_state.update({
                "staging_id": staging,
                "current_id": current,
                "started_at": self.observed_at,
                "status": "collecting",
            })
            _atomic_json(self.store / "collection_state.json", self.state)

        mapping_unit = f"{staging}:all"
        mapping_path = _reference_source_path(self.store, staging, "bse_mapping")
        if not _unit_done(self.state, self.store, "bse_mapping", mapping_unit):
            response = self._call("bse_mapping", mapping_unit)
            frame = response.frame
            if frame is None:
                self._mark_failed(
                    "bse_mapping", mapping_unit, "vendor_unavailable_or_unlicensed",
                    request_receipts=[response.receipt], generation_id=staging,
                )
                return False
            if len(frame) >= SOURCE_ROW_CAPS["bse_mapping"]:
                self._mark_failed(
                    "bse_mapping", mapping_unit, "documented_source_row_cap_reached",
                    request_receipts=[response.receipt], source_row_count=len(frame),
                    quarantined_unknown_row_count=len(frame), generation_id=staging,
                )
                return False
            normal = _normalise_bse_mapping(frame)
            if normal.empty:
                self._mark_failed(
                    "bse_mapping", mapping_unit, "unexpected_empty_bse_identity_mapping",
                    request_receipts=[response.receipt], generation_id=staging,
                )
                return False
            _atomic_parquet(mapping_path, normal)
            _set_unit(
                self.state, self.store, "bse_mapping", mapping_unit,
                status="complete", observed_at=self.observed_at,
                row_count=len(normal), source_row_count=len(frame), partition=mapping_path,
                request_receipts=[response.receipt], generation_id=staging,
            )

        for exchange in EXCHANGES:
            for status in LIST_STATUSES:
                source_unit = f"{exchange}:{status}"
                unit = f"{staging}:{source_unit}"
                path = _reference_source_path(self.store, staging, "stock_basic", source_unit)
                if _unit_done(self.state, self.store, "stock_basic", unit):
                    continue
                response = self._call(
                    "stock_basic", unit, exchange=exchange, list_status=status,
                )
                frame = response.frame
                if frame is None:
                    self._mark_failed(
                        "stock_basic", unit, "vendor_unavailable_or_unlicensed",
                        request_receipts=[response.receipt], generation_id=staging,
                    )
                    continue
                if len(frame) >= SOURCE_ROW_CAPS["stock_basic"]:
                    self._mark_failed(
                        "stock_basic", unit, "documented_source_row_cap_reached",
                        request_receipts=[response.receipt], source_row_count=len(frame),
                        quarantined_unknown_row_count=len(frame), generation_id=staging,
                    )
                    continue
                if status == "L" and frame.empty:
                    self._mark_failed(
                        "stock_basic", unit, "unexpected_empty_listed_exchange",
                        request_receipts=[response.receipt], generation_id=staging,
                    )
                    continue
                # Raw parquet is raw truth: store the frame verbatim even
                # though some rows may carry a non-canonical (legacy/delisted
                # vendor) ts_code.  Classify it the same three-way split
                # _validate_response_binding already applied (canonical /
                # independently classifiable known-excluded / genuinely
                # unknown quarantined), so the unit's row_count/
                # known_excluded_row_count/quarantined_unknown_row_count
                # equation balances against exactly what was stored.
                _atomic_parquet(path, frame)
                row_roles = [
                    _stock_basic_ts_code_classification(item.get("ts_code"))
                    for item in frame.to_dict(orient="records")
                ]
                known_excluded_count = row_roles.count("known_excluded")
                quarantined_count = row_roles.count("quarantined_unknown")
                _set_unit(
                    self.state, self.store, "stock_basic", unit,
                    status="empty" if frame.empty else "complete", observed_at=self.observed_at,
                    row_count=len(frame) - known_excluded_count - quarantined_count,
                    source_row_count=len(frame),
                    known_excluded_row_count=known_excluded_count,
                    quarantined_unknown_row_count=quarantined_count,
                    partition=path,
                    request_receipts=[response.receipt], generation_id=staging,
                )

        for status in FUND_STATUSES:
            unit = f"{staging}:{status}"
            path = _reference_source_path(self.store, staging, "fund_basic", status)
            if _unit_done(self.state, self.store, "fund_basic", unit):
                continue
            response = self._call("fund_basic", unit, market="E", status=status)
            frame = response.frame
            if frame is None:
                self._mark_failed(
                    "fund_basic", unit, "vendor_unavailable_or_unlicensed",
                    request_receipts=[response.receipt], generation_id=staging,
                )
                continue
            if len(frame) >= SOURCE_ROW_CAPS["fund_basic"]:
                self._mark_failed(
                    "fund_basic", unit, "documented_source_row_cap_reached",
                    request_receipts=[response.receipt], source_row_count=len(frame),
                    quarantined_unknown_row_count=len(frame), generation_id=staging,
                )
                continue
            if status == "L" and frame.empty:
                self._mark_failed(
                    "fund_basic", unit, "unexpected_empty_listed_exchange_funds",
                    request_receipts=[response.receipt], generation_id=staging,
                )
                continue
            _atomic_parquet(path, frame)
            _set_unit(
                self.state, self.store, "fund_basic", unit,
                status="empty" if frame.empty else "complete", observed_at=self.observed_at,
                row_count=0, source_row_count=len(frame),
                known_excluded_row_count=len(frame), partition=path,
                request_receipts=[response.receipt], generation_id=staging,
            )

        ready = (
            _unit_done(self.state, self.store, "bse_mapping", mapping_unit)
            and all(
                _unit_done(
                    self.state, self.store, "stock_basic",
                    f"{staging}:{exchange}:{status}",
                )
                for exchange in EXCHANGES for status in LIST_STATUSES
            )
            and all(
                _unit_done(self.state, self.store, "fund_basic", f"{staging}:{status}")
                for status in FUND_STATUSES
            )
        )
        if ready:
            compile_security_master(self.store, staging)
            _promote_reference_generation(self.store, staging)
            generation_state.update({
                "current_id": staging, "staging_id": None, "status": "complete",
                "promoted_at": self.observed_at,
            })
            _atomic_json(self.store / "collection_state.json", self.state)
            self.reference_generation = staging
        return ready

    def collect_calendars(self, start: date, end: date) -> bool:
        work: list[tuple[int, int, str, date, date]] = []
        for year, segment_start, segment_end in _year_segments(start, end):
            for exchange in CALENDAR_EXCHANGES:
                unit = f"{exchange}:{_compact(segment_start)}:{_compact(segment_end)}"
                if not _unit_done(self.state, self.store, "trade_cal", unit):
                    retry = 1 if _unit_record(self.state, "trade_cal", unit) else 0
                    work.append((retry, -year, exchange, segment_start, segment_end))
        for _, neg_sort_year, exchange, segment_start, segment_end in sorted(work):
            unit = f"{exchange}:{_compact(segment_start)}:{_compact(segment_end)}"
            response = self._call(
                "trade_cal", unit, exchange=exchange,
                start_date=_compact(segment_start), end_date=_compact(segment_end),
            )
            frame = response.frame
            if frame is None:
                self._mark_failed(
                    "trade_cal", unit, "vendor_unavailable_or_unlicensed",
                    request_receipts=[response.receipt],
                )
                continue
            try:
                normal = _normalise_calendar(frame, exchange, segment_start, segment_end)
            except SpineError:
                self._mark_failed("trade_cal", unit, "calendar_contract_failed")
                raise
            path = _calendar_partition(self.store, segment_start.year)
            rows, revised = _upsert_partition(
                path, normal, keys=KEY_COLUMNS["trade_calendar"],
            )
            _set_unit(
                self.state, self.store, "trade_cal", unit, status="complete",
                observed_at=self.observed_at, row_count=len(normal), source_row_count=len(frame),
                revised_key_count=revised, partition=path,
                request_receipts=[response.receipt],
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

    def _replace_source_classifications(
        self,
        endpoint: str,
        trade_date: date,
        normal: NormalisedSourceUnit,
    ) -> None:
        for classification, frame in (
            ("known_excluded", normal.known_excluded),
            ("quarantined_unknown", normal.quarantined_unknown),
        ):
            path = _classification_partition(self.store, classification, endpoint, trade_date)
            _replace_partition_units(
                path, frame, keys=KEY_COLUMNS["source_classification"],
                unit_column="trade_date", units=[trade_date.isoformat()],
            )

    def collect_pit_universe(self, start: date, end: date) -> bool:
        """Collect the official exact-day A-share list witness from 2016 onward."""
        sessions = _read_parquet_strict(self.store / "reference" / "market_sessions.parquet")
        lower = max(start, PIT_UNIVERSE_START)
        dates = [
            _parse_date(value) for value in sessions["trade_date"].astype(str)
            if lower <= _parse_date(value) <= end
        ]
        work = sorted(
            (
                1 if _unit_record(self.state, PIT_UNIVERSE_ENDPOINT, _compact(day)) else 0,
                -day.toordinal(), day,
            )
            for day in dates
            if not _unit_done(self.state, self.store, PIT_UNIVERSE_ENDPOINT, _compact(day))
        )
        for _, _, trade_date in work:
            unit = _compact(trade_date)
            response = self._call(PIT_UNIVERSE_ENDPOINT, unit, trade_date=unit)
            frame = response.frame
            if frame is None:
                self._mark_failed(
                    PIT_UNIVERSE_ENDPOINT, unit, "vendor_unavailable_or_unlicensed",
                    request_receipts=[response.receipt],
                )
                continue
            if len(frame) >= SOURCE_ROW_CAPS[PIT_UNIVERSE_ENDPOINT]:
                self._mark_failed(
                    PIT_UNIVERSE_ENDPOINT, unit, "documented_source_row_cap_reached",
                    request_receipts=[response.receipt], source_row_count=len(frame),
                    quarantined_unknown_row_count=len(frame),
                )
                continue
            if frame.empty:
                self._mark_failed(
                    PIT_UNIVERSE_ENDPOINT, unit, "unexpected_empty_open_session",
                    request_receipts=[response.receipt],
                )
                continue
            normal = normalise_bak_basic(
                frame, trade_date, self.store, self.reference_generation,
            )
            self._replace_source_classifications(PIT_UNIVERSE_ENDPOINT, trade_date, normal)
            path = _pit_partition(self.store, trade_date)
            _replace_partition_units(
                path, normal.landed_a, keys=KEY_COLUMNS["bak_basic"],
                unit_column="trade_date", units=[trade_date.isoformat()],
            )
            witness_missing_row_count = int(normal.landed_a.get(
                "current_stock_basic_witness_missing", pd.Series(dtype=bool),
            ).sum())
            if not normal.quarantined_unknown.empty:
                self._mark_failed(
                    PIT_UNIVERSE_ENDPOINT, unit, "quarantined_unknown_source_rows",
                    request_receipts=[response.receipt], source_row_count=len(frame),
                    row_count=len(normal.landed_a),
                    known_excluded_row_count=len(normal.known_excluded),
                    quarantined_unknown_row_count=len(normal.quarantined_unknown),
                    witness_missing_row_count=witness_missing_row_count,
                    collection_method="whole_market",
                )
                continue
            _set_unit(
                self.state, self.store, PIT_UNIVERSE_ENDPOINT, unit, status="complete",
                observed_at=self.observed_at, row_count=len(normal.landed_a),
                source_row_count=len(frame), partition=path,
                known_excluded_row_count=len(normal.known_excluded),
                witness_missing_row_count=witness_missing_row_count,
                request_receipts=[response.receipt],
            )
        expected = [_compact(day) for day in sorted(dates)]
        return all(
            _unit_done(self.state, self.store, PIT_UNIVERSE_ENDPOINT, unit)
            for unit in expected
        )

    def collect_name_history(self, end: date) -> None:
        years = list(range(NAME_HISTORY_START_YEAR, end.year + 1))
        years.sort(key=lambda year: (
            1 if any(
                str(unit).startswith(f"{year}:")
                for unit in self.state.get("units", {}).get("namechange", {})
            ) else 0,
            year,
        ))
        attempted = 0
        for year in years:
            segment_end = min(end, date(year, 12, 31))
            unit = f"{year}:{_compact(segment_end)}"
            if _unit_done(self.state, self.store, "namechange", unit):
                continue
            if attempted >= NAMECHANGE_MAX_PER_RUN:
                break
            attempted += 1
            response = self._call(
                "namechange", unit, start_date=f"{year:04d}0101",
                end_date=_compact(segment_end),
            )
            frame = response.frame
            if frame is None:
                self._mark_failed(
                    "namechange", unit, "vendor_unavailable_or_unlicensed",
                    request_receipts=[response.receipt],
                )
                continue
            if len(frame) >= 6000:
                self._mark_failed(
                    "namechange", unit, "possible_undocumented_source_row_cap",
                    request_receipts=[response.receipt], source_row_count=len(frame),
                    quarantined_unknown_row_count=len(frame),
                )
                continue
            normal = normalise_name_history(
                frame, self.store, segment_end, self.reference_generation,
            )
            self._replace_source_classifications("namechange", segment_end, normal)
            path = _name_partition(self.store, year)
            _atomic_parquet(path, normal.landed_a)
            if not normal.quarantined_unknown.empty:
                self._mark_failed(
                    "namechange", unit, "namechange_orphans_absent_from_A_universe_witness",
                    request_receipts=[response.receipt], source_row_count=len(frame),
                    row_count=len(normal.landed_a),
                    known_excluded_row_count=len(normal.known_excluded),
                    quarantined_unknown_row_count=len(normal.quarantined_unknown),
                    unmatched_master_row_count=len(normal.quarantined_unknown),
                )
                continue
            if normal.landed_a.empty:
                _set_unit(
                    self.state, self.store, "namechange", unit, status="empty",
                    observed_at=self.observed_at, source_row_count=len(frame),
                    known_excluded_row_count=len(normal.known_excluded),
                    partition=path, request_receipts=[response.receipt],
                )
                continue
            _set_unit(
                self.state, self.store, "namechange", unit, status="complete",
                observed_at=self.observed_at, row_count=len(normal.landed_a),
                source_row_count=len(frame),
                known_excluded_row_count=len(normal.known_excluded),
                unmatched_master_row_count=0, revised_key_count=0, partition=path,
                request_receipts=[response.receipt],
            )
            log.debug("namechange %d landed (%d partition rows)", year, len(normal.landed_a))

    def _expected_shard_tickers(self, trade_date: date) -> list[str]:
        master, _, _ = _master_maps(self.store, self.reference_generation)
        # bak_basic corroborates the lifecycle universe; it can never shrink it.
        # The exact frozen union is hashed into the parent shard plan below.
        return sorted(_eligible_tickers_with_pit(self.store, master, trade_date.isoformat()))

    def _active_range_campaign(
        self, endpoint: str, start: date, end: date,
    ) -> dict[str, Any] | None:
        record = self.state.get("range_campaigns", {}).get(endpoint)
        if not isinstance(record, dict):
            return None
        if record.get("start_date") != start.isoformat() or record.get("end_date") != end.isoformat():
            raise SpineError(
                f"{endpoint} already has a range campaign for a different requested interval"
            )
        plan = crs.load_plan(self.store, str(record.get("campaign_id") or ""))
        if plan.get("endpoint") != endpoint:
            raise SpineError("range campaign endpoint does not bind central progress state")
        return record

    def _activate_range_campaign(
        self,
        endpoint: str,
        start: date,
        end: date,
        *,
        trigger_unit: str,
        cap_probe_receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        if endpoint not in DENSE_ENDPOINTS:
            raise SpineError(f"range campaigns are unavailable for {endpoint}")
        if self.canary and not BULK_HISTORICAL_BACKFILL_READY:
            # The scalable ticker-range path is exactly what the bulk gate is
            # still withholding, so a canary must never be the thing that first
            # exercises it live.  Refuse and let the operator shrink the window.
            raise SpineError(
                f"canary window hit the documented {endpoint} row cap; the ticker-range "
                "campaign stays refused until BULK_HISTORICAL_BACKFILL_READY is promoted "
                "in a separate reviewed change. Narrow the canary range and re-run."
            )
        existing = self._active_range_campaign(endpoint, start, end)
        if existing is not None:
            return existing
        generation = self.reference_generation or _current_reference_generation(self.store)
        assert generation is not None
        identities, universe_witness = _range_query_identities(
            self.store, start, end, generation,
        )
        sessions = _range_sessions(self.store, start, end)
        plan = crs.ensure_campaign(
            self.store,
            endpoint=endpoint,
            fields=ENDPOINT_FIELDS[endpoint].split(","),
            source_row_cap=SOURCE_ROW_CAPS[endpoint],
            sessions=sessions,
            query_identities=identities,
            reference_generation_id=generation,
            reference_generation_semantic_sha256=_reference_generation_semantic_sha256(
                self.store, generation,
            ),
            universe_witness_sha256=universe_witness,
        )
        record = {
            "campaign_id": plan["campaign_id"],
            "endpoint": endpoint,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "status": "collecting",
            "trigger_unit": trigger_unit,
            "cap_probe_receipt": _json_safe(dict(cap_probe_receipt)),
            "planned_leaf_count": len(crs.planned_leaves(plan)),
            "query_identity_count": int(plan["query_identity_count"]),
            "created_at": self.observed_at,
        }
        self.state.setdefault("range_campaigns", {})[endpoint] = record
        _set_unit(
            self.state, self.store, endpoint, trigger_unit, status="collecting",
            observed_at=self.observed_at, request_receipts=[cap_probe_receipt],
            collection_method="per_ticker_range_shards",
        )
        return record

    def _collect_range_leaf(
        self, plan: Mapping[str, Any], leaf: crs.RangeLeaf,
    ) -> None:
        if self.max_requests and self.requests_made >= self.max_requests:
            raise RequestBudgetExhausted("request cap reached; range campaign is resumable")
        self.requests_made += 1
        query_kwargs: dict[str, Any] = {
            "fields": ENDPOINT_FIELDS[leaf.endpoint],
            "_return_empty": True,
            **leaf.params,
        }
        # Hidden transport retries would consume vendor quota without producing
        # one immutable attempt receipt per HTTP request.  The range scheduler
        # owns retries explicitly instead.
        if self.query is tc.query:
            query_kwargs["_retries"] = 0
        frame = self.query(leaf.endpoint, **query_kwargs)
        if frame is not None and not isinstance(frame, pd.DataFrame):
            raise SpineError(f"{leaf.endpoint} range query returned a non-DataFrame response")
        if frame is not None:
            _assert_configured_token_absent_logical(
                frame, artifact=f"range-response:{leaf.endpoint}/{leaf.leaf_id}",
            )
        try:
            state = crs.record_attempt(
                self.store, plan, leaf, frame=frame, observed_at=self.observed_at,
            )
        except crs.RangeShardError as exc:
            self.failures.append({
                "endpoint": leaf.endpoint,
                "unit": leaf.unit,
                "reason": "range_leaf_contract_failed",
            })
            raise SpineError("range leaf response failed its exact contract") from exc
        if state.get("status") == "retryable":
            self.failures.append({
                "endpoint": leaf.endpoint,
                "unit": leaf.unit,
                "reason": "vendor_unavailable_or_unlicensed",
            })

    def _materialize_range_campaign(
        self,
        endpoint: str,
        plan: Mapping[str, Any],
        verification: crs.CampaignVerification,
    ) -> None:
        if not verification.complete or verification.receipt is None:
            raise SpineError("range campaign cannot transpose before exact completion")
        campaign_reference = crs.campaign_receipt_reference(self.store, verification)
        resolved = verification.resolved_frame.copy()
        if not resolved.empty:
            resolved["trade_date"] = resolved["trade_date"].map(_iso)
            resolved = resolved.sort_values(["trade_date", "ts_code"], kind="stable")
        for trade_date_text in plan["sessions"]:
            trade_date = _parse_date(trade_date_text)
            unit = _compact(trade_date)
            raw_day = resolved[
                resolved["trade_date"].astype(str) == trade_date_text
            ].copy() if not resolved.empty else pd.DataFrame(columns=ENDPOINT_FIELDS[endpoint].split(","))
            if raw_day.empty:
                raise SpineError(
                    f"{endpoint}/{unit} range campaign returned an unexpected empty open session"
                )
            normal = normalise_daily_endpoint(
                endpoint, raw_day, trade_date, self.store, self.reference_generation,
            )
            if normal.landed_a.empty:
                raise SpineError(f"{endpoint}/{unit} range campaign landed no A-share rows")
            if not normal.quarantined_unknown.empty:
                raise SpineError(f"{endpoint}/{unit} range campaign produced quarantined rows")
            path = _monthly_partition(self.store, endpoint, trade_date)
            prior = _unit_record(self.state, endpoint, unit)
            if prior and prior.get("status") in {"complete", "empty"}:
                prior_receipt = _unit_artifact_receipt(
                    self.store, endpoint, unit, prior,
                )
                new_semantic = _frame_semantic_sha256(normal.landed_a, KEY_COLUMNS[endpoint])
                if (
                    int(prior_receipt["unit_row_count"]) != len(normal.landed_a)
                    or prior_receipt["unit_semantic_sha256"] != new_semantic
                ):
                    raise SpineError(
                        f"{endpoint}/{unit} range/whole-market revision conflict"
                    )
            self._replace_source_classifications(endpoint, trade_date, normal)
            _, revised = _replace_partition_units(
                path, normal.landed_a, keys=KEY_COLUMNS[endpoint],
                unit_column="trade_date", units=[trade_date_text],
            )
            expected_tickers = self._expected_shard_tickers(trade_date)
            ticker_hash = hashlib.sha256(
                "\n".join(expected_tickers).encode("utf-8")
            ).hexdigest()
            day_receipt = verification.day_receipts[trade_date_text]
            range_reference = {
                **campaign_reference,
                "trade_date": trade_date_text,
                "authoritative_row_count": int(day_receipt["authoritative_row_count"]),
                "authoritative_semantic_sha256": day_receipt[
                    "authoritative_semantic_sha256"
                ],
            }
            _set_unit(
                self.state, self.store, endpoint, unit, status="complete",
                observed_at=self.observed_at, row_count=len(normal.landed_a),
                source_row_count=len(raw_day),
                known_excluded_row_count=len(normal.known_excluded),
                quarantined_unknown_row_count=0, revised_key_count=revised,
                partition=path,
                request_receipts=(prior or {}).get("request_receipts", []),
                collection_method="per_ticker_range_shards",
                expected_ticker_count=len(expected_tickers),
                expected_ticker_sha256=ticker_hash,
                range_campaign_receipt=range_reference,
                persist_state=False,
            )
        campaign_state = self.state.setdefault("range_campaigns", {})[endpoint]
        campaign_state.update({
            "status": "complete",
            "completed_at": self.observed_at,
            "campaign_receipt": campaign_reference,
            "authoritative_row_count": int(
                verification.receipt["authoritative_row_count"]
            ),
            "duplicate_alias_observation_row_count": int(
                verification.receipt["duplicate_alias_observation_row_count"]
            ),
        })
        _atomic_json(self.store / "collection_state.json", self.state)

    def _advance_range_campaign(
        self, endpoint: str, start: date, end: date, *, request_allowance: int,
    ) -> bool:
        record = self._active_range_campaign(endpoint, start, end)
        if record is None:
            return False
        plan = crs.load_plan(self.store, record["campaign_id"])
        if record.get("status") == "complete":
            crs.verify_campaign(self.store, plan["campaign_id"])
            return True
        if record.get("status") == "failed":
            raise SpineError(
                f"{endpoint} range campaign is terminally failed: {record.get('reason')}"
            )
        pending = crs.pending_leaves(self.store, plan)
        for leaf in pending[:max(0, request_allowance)]:
            try:
                self._collect_range_leaf(plan, leaf)
            except SpineError:
                record["status"] = "failed"
                record["reason"] = "range_leaf_contract_failed"
                record["last_advanced_at"] = self.observed_at
                _atomic_json(self.store / "collection_state.json", self.state)
                raise
        pending_after = crs.pending_leaves(self.store, plan)
        progress = crs.campaign_progress(self.store, plan)
        record.update(progress)
        record["last_advanced_at"] = self.observed_at
        _atomic_json(self.store / "collection_state.json", self.state)
        if progress["failed_leaf_count"]:
            record["status"] = "failed"
            record["reason"] = "range_leaf_contract_failed"
            _atomic_json(self.store / "collection_state.json", self.state)
            raise SpineError("range campaign contains a terminally failed leaf")
        if pending_after:
            return False
        try:
            verification = crs.finalize_campaign(self.store, plan)
        except crs.RangeShardError as exc:
            record["status"] = "failed"
            record["reason"] = "range_campaign_artifact_verification_failed"
            _atomic_json(self.store / "collection_state.json", self.state)
            raise SpineError("range campaign failed terminal verification") from exc
        if not verification.complete:
            record["status"] = "failed"
            record["reason"] = "bse_alias_conflict"
            _atomic_json(self.store / "collection_state.json", self.state)
            raise SpineError("range campaign retained conflicting BSE alias observations")
        self._materialize_range_campaign(endpoint, plan, verification)
        return True

    def collect_daily(self, start: date, end: date, endpoints: Sequence[str]) -> None:
        session_path = self.store / "reference" / "market_sessions.parquet"
        sessions = _read_parquet_strict(session_path)
        sessions = sessions[
            (sessions["trade_date"].astype(str) >= start.isoformat())
            & (sessions["trade_date"].astype(str) <= end.isoformat())
        ]
        dates = [_parse_date(value) for value in sorted(sessions["trade_date"], reverse=True)]
        active_range_endpoints = {
            endpoint for endpoint in endpoints
            if endpoint in DENSE_ENDPOINTS
            and self._active_range_campaign(endpoint, start, end) is not None
        }
        # Unattempted units first; prior failures are retried only after new work,
        # preventing a historical entitlement gap from starving the rest of the tape.
        work: list[tuple[int, date, str]] = []
        for trade_date in dates:
            for endpoint in endpoints:
                if endpoint == "stock_st" and trade_date < ST_DAILY_START:
                    continue
                if endpoint in active_range_endpoints:
                    # Once a dense endpoint hits its whole-market cap, its one
                    # immutable range campaign owns the complete requested span.
                    continue
                unit = _compact(trade_date)
                if _unit_done(self.state, self.store, endpoint, unit):
                    continue
                priority = 1 if _unit_record(self.state, endpoint, unit) else 0
                work.append((priority, trade_date, endpoint))
        work.sort(key=lambda item: (item[0], -item[1].toordinal(), endpoints.index(item[2])))
        for _, trade_date, endpoint in work:
            if endpoint in self.state.get("range_campaigns", {}):
                continue
            unit = _compact(trade_date)
            request_receipts: list[Mapping[str, Any]] = []
            response = self._call(endpoint, unit, trade_date=unit)
            frame = response.frame
            request_receipts = [response.receipt]
            collection_method = "whole_market"
            if frame is None:
                self._mark_failed(
                    endpoint, unit, "vendor_unavailable_or_unlicensed",
                    request_receipts=request_receipts,
                )
                continue
            cap = SOURCE_ROW_CAPS.get(endpoint)
            if cap is not None and len(frame) >= cap:
                if endpoint not in DENSE_ENDPOINTS:
                    self._mark_failed(
                        endpoint, unit, "documented_source_row_cap_reached",
                        request_receipts=request_receipts, source_row_count=len(frame),
                        quarantined_unknown_row_count=len(frame),
                    )
                    continue
                if len(request_receipts) != 1:
                    raise SpineError(
                        f"{endpoint}/{unit} capped whole-market probe has ambiguous receipts"
                    )
                cap_probe = _mark_non_authoritative_cap_probe(
                    self.store, request_receipts[0], source_cap=cap,
                )
                self._activate_range_campaign(
                    endpoint, start, end, trigger_unit=unit,
                    cap_probe_receipt=cap_probe,
                )
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
                    request_receipts=request_receipts, collection_method=collection_method,
                )
                continue
            try:
                normal = normalise_daily_endpoint(
                    endpoint, frame, trade_date, self.store, self.reference_generation,
                )
            except SpineError:
                self._mark_failed(
                    endpoint, unit, "daily_contract_failed",
                    request_receipts=request_receipts, source_row_count=len(frame),
                    quarantined_unknown_row_count=len(frame),
                    collection_method=collection_method,
                )
                raise
            self._replace_source_classifications(endpoint, trade_date, normal)
            if normal.landed_a.empty and endpoint in DENSE_ENDPOINTS:
                self._mark_failed(
                    endpoint, unit, "no_A_share_rows_after_identity_filter",
                    request_receipts=request_receipts, source_row_count=len(frame),
                    known_excluded_row_count=len(normal.known_excluded),
                    quarantined_unknown_row_count=len(normal.quarantined_unknown),
                    collection_method=collection_method,
                )
                continue
            path = _monthly_partition(self.store, endpoint, trade_date)
            rows, revised = _replace_partition_units(
                path,
                normal.landed_a,
                keys=KEY_COLUMNS[endpoint],
                unit_column="trade_date",
                units=[trade_date.isoformat()],
            )
            if not normal.quarantined_unknown.empty:
                self._mark_failed(
                    endpoint, unit, "quarantined_unknown_source_rows",
                    request_receipts=request_receipts, source_row_count=len(frame),
                    row_count=len(normal.landed_a),
                    known_excluded_row_count=len(normal.known_excluded),
                    quarantined_unknown_row_count=len(normal.quarantined_unknown),
                    collection_method=collection_method,
                )
                continue
            shard_record = _unit_record(self.state, endpoint, unit) or {}
            _set_unit(
                self.state, self.store, endpoint, unit,
                status="empty" if normal.landed_a.empty else "complete", observed_at=self.observed_at,
                row_count=len(normal.landed_a), source_row_count=len(frame),
                known_excluded_row_count=len(normal.known_excluded),
                quarantined_unknown_row_count=0, revised_key_count=revised,
                partition=path if not normal.landed_a.empty else None,
                request_receipts=request_receipts, collection_method=collection_method,
                expected_ticker_count=shard_record.get("expected_ticker_count"),
                expected_ticker_sha256=shard_record.get("expected_ticker_sha256"),
            )
            log.debug("%s %s landed (%d partition rows)", endpoint, unit, rows)

        active = [
            endpoint for endpoint in endpoints
            if endpoint in DENSE_ENDPOINTS
            and self._active_range_campaign(endpoint, start, end) is not None
            and self.state["range_campaigns"][endpoint].get("status") != "complete"
        ]
        for index, endpoint in enumerate(active):
            if self.max_requests:
                remaining = self.max_requests - self.requests_made
                if remaining <= 0:
                    raise RequestBudgetExhausted(
                        "request cap reached; range campaigns are resumable"
                    )
                allowance = max(1, remaining // (len(active) - index))
            else:
                allowance = 10**9
            self._advance_range_campaign(
                endpoint, start, end, request_allowance=allowance,
            )


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
    if endpoint == PIT_UNIVERSE_ENDPOINT:
        dates = [value for value in dates if value >= PIT_UNIVERSE_START]
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
    limit_status_audited_rows = 0
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
        daily_basic_path = store / "daily_basic" / relative
        if not limit_path.exists():
            raise SpineError(f"canonical event substrate lacks stk_limit partition: {relative}")
        if not daily_basic_path.exists():
            raise SpineError(f"canonical event substrate lacks daily_basic audit partition: {relative}")
        limits = _read_parquet_strict(limit_path)
        daily_basic = _read_parquet_strict(daily_basic_path)
        if _duplicates(daily, KEY_COLUMNS["daily"]):
            raise SpineError(f"daily partition duplicates canonical event keys: {relative}")
        if _duplicates(limits, KEY_COLUMNS["stk_limit"]):
            raise SpineError(f"stk_limit partition duplicates canonical event keys: {relative}")
        limits = limits[
            (limits["trade_date"].astype(str) >= start.isoformat())
            & (limits["trade_date"].astype(str) <= end.isoformat())
        ].copy()
        daily_basic = daily_basic[
            (daily_basic["trade_date"].astype(str) >= start.isoformat())
            & (daily_basic["trade_date"].astype(str) <= end.isoformat())
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
        if "limit_status" not in daily_basic.columns:
            raise SpineError("daily_basic limit_status audit field is absent")
        if "close_cents" not in daily_basic.columns:
            raise SpineError("daily_basic exact close audit field is absent")
        status = daily_basic[["trade_date", "ticker", "close_cents", "limit_status"]].copy()
        status = status.rename(columns={"close_cents": "daily_basic_close_cents"})
        merged = merged.merge(
            status, on=["trade_date", "ticker"], how="left", validate="one_to_one",
        )

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
        outside = merged[
            bounded & (
                merged["open_cents"].lt(merged["down_limit_cents"])
                | merged["open_cents"].gt(merged["up_limit_cents"])
                | merged["high_cents"].lt(merged["down_limit_cents"])
                | merged["high_cents"].gt(merged["up_limit_cents"])
                | merged["low_cents"].lt(merged["down_limit_cents"])
                | merged["low_cents"].gt(merged["up_limit_cents"])
                | merged["close_cents"].lt(merged["down_limit_cents"])
                | merged["close_cents"].gt(merged["up_limit_cents"])
            )
        ]
        if not outside.empty:
            sample = outside[[
                "trade_date", "ticker", "open_cents", "high_cents", "low_cents",
                "close_cents", "up_limit_cents", "down_limit_cents",
            ]].head(20).to_dict(orient="records")
            raise SpineError(f"daily OHLC breached vendor-published legal bounds: {sample}")
        merged["touched_up"] = (
            merged["event_eligible"]
            & merged["high_cents"].eq(merged["up_limit_cents"])
        )
        merged["sealed_up"] = (
            merged["event_eligible"]
            & merged["close_cents"].eq(merged["up_limit_cents"])
        )
        merged["touched_down"] = (
            merged["event_eligible"]
            & merged["low_cents"].eq(merged["down_limit_cents"])
        )
        merged["sealed_down"] = (
            merged["event_eligible"]
            & merged["close_cents"].eq(merged["down_limit_cents"])
        )
        status_present = merged["limit_status"].notna()
        close_audit_mismatch = merged[
            merged["daily_basic_close_cents"].isna()
            | merged["close_cents"].ne(merged["daily_basic_close_cents"])
        ]
        if not close_audit_mismatch.empty:
            sample = close_audit_mismatch[[
                "trade_date", "ticker", "close_cents", "daily_basic_close_cents",
            ]].head(20).to_dict(orient="records")
            raise SpineError(f"daily/daily_basic exact-close mismatch: {sample}")
        observed_status = merged.loc[status_present, "limit_status"].astype(int)
        status_mismatch = (
            (observed_status.isin({2, 3})
             != merged.loc[status_present, "sealed_up"].astype(bool))
            | (observed_status.isin({5, 6})
               != merged.loc[status_present, "sealed_down"].astype(bool))
        )
        if status_mismatch.any():
            sample = merged.loc[status_present].loc[status_mismatch, [
                "trade_date", "ticker", "limit_status", "sealed_up", "sealed_down",
            ]].head(20).to_dict(orient="records")
            raise SpineError(f"daily_basic.limit_status disagrees with exact close/limits: {sample}")
        direction_mismatch = (
            (observed_status.eq(0)
             & merged.loc[status_present, "close_cents"].ne(
                 merged.loc[status_present, "pre_close_cents"]
             ))
            | (observed_status.eq(1)
               & merged.loc[status_present, "close_cents"].le(
                   merged.loc[status_present, "pre_close_cents"]
               ))
            | (observed_status.eq(4)
               & merged.loc[status_present, "close_cents"].ge(
                   merged.loc[status_present, "pre_close_cents"]
               ))
        )
        if direction_mismatch.any():
            sample = merged.loc[status_present].loc[direction_mismatch, [
                "trade_date", "ticker", "limit_status", "pre_close_cents", "close_cents",
            ]].head(20).to_dict(orient="records")
            raise SpineError(f"daily_basic.limit_status direction disagrees with exact close: {sample}")
        one_price_up = merged[
            status_present & merged["limit_status"].eq(3)
            & ~(
                merged["open_cents"].eq(merged["up_limit_cents"])
                & merged["high_cents"].eq(merged["up_limit_cents"])
                & merged["low_cents"].eq(merged["up_limit_cents"])
                & merged["close_cents"].eq(merged["up_limit_cents"])
            )
        ]
        one_price_down = merged[
            status_present & merged["limit_status"].eq(6)
            & ~(
                merged["open_cents"].eq(merged["down_limit_cents"])
                & merged["high_cents"].eq(merged["down_limit_cents"])
                & merged["low_cents"].eq(merged["down_limit_cents"])
                & merged["close_cents"].eq(merged["down_limit_cents"])
            )
        ]
        if not one_price_up.empty or not one_price_down.empty:
            raise SpineError("daily_basic one-price limit_status disagrees with OHLC")
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
        limit_status_audited_rows += int(status_present.sum())

    return {
        "ready": bool(output_receipts and event_rows),
        "row_count": event_rows,
        "positive_volume_rows": positive_volume_rows,
        "source_limit_rows": bounded_rows,
        "no_published_limit_rows": no_published_limit_rows,
        "daily_basic_limit_status_audited_rows": limit_status_audited_rows,
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


def _eligible_tickers_with_pit(store: Path, master: pd.DataFrame, trade_date: str) -> set[str]:
    lifecycle = _eligible_tickers(master, trade_date)
    day = _parse_date(trade_date)
    if day >= PIT_UNIVERSE_START:
        path = _pit_partition(store, day)
        if path.exists():
            frame = _read_parquet_strict(path)
            subset = frame[frame["trade_date"].astype(str) == day.isoformat()]
            pit = set(subset.get("ticker", pd.Series(dtype=str)).astype(str))
            return lifecycle | pit
    return lifecycle


def _pit_lifecycle_reconciliation(
    store: Path,
    master: pd.DataFrame,
    sessions: pd.DataFrame,
    start: date,
    end: date,
) -> dict[str, Any]:
    """Prove PIT rows are a legal union member, not a lifecycle intersection.

    DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION -- a PIT ticker absent from the
    current stock_basic-derived security master ("witness-missing") is a
    legal union member and never blocks; a PIT ticker that IS in the master
    but whose lifecycle window does not cover the observed trade_date is an
    unresolved source contradiction and keeps blocking.  A lifecycle-eligible
    ticker missing from the PIT witness (``missing_in_pit``) is unchanged --
    not ruled on by this decision -- and keeps blocking exactly as before.
    """
    requested = [
        value for value in sessions.get("trade_date", pd.Series(dtype=str)).astype(str)
        if max(start, PIT_UNIVERSE_START).isoformat() <= value <= end.isoformat()
    ]
    master_tickers = set(master["ticker"].astype(str)) if not master.empty else set()
    missing_sessions: list[str] = []
    missing_in_pit: list[tuple[str, str]] = []
    extra_in_pit: list[tuple[str, str]] = []
    absent_from_master: list[tuple[str, str]] = []
    window_conflict: list[tuple[str, str]] = []
    lifecycle_observations = 0
    pit_observations = 0
    union_observations = 0
    union_hasher = hashlib.sha256()
    for trade_date in requested:
        day = _parse_date(trade_date)
        path = _pit_partition(store, day)
        if not path.exists():
            missing_sessions.append(trade_date)
            continue
        frame = _read_parquet_strict(path)
        subset = frame[frame["trade_date"].astype(str) == trade_date]
        pit = set(subset.get("ticker", pd.Series(dtype=str)).astype(str))
        if not pit:
            missing_sessions.append(trade_date)
            continue
        lifecycle = _eligible_tickers(master, trade_date)
        union = lifecycle | pit
        lifecycle_observations += len(lifecycle)
        pit_observations += len(pit)
        union_observations += len(union)
        missing_in_pit.extend((trade_date, ticker) for ticker in sorted(lifecycle - pit))
        pit_not_in_lifecycle_window = sorted(pit - lifecycle)
        extra_in_pit.extend((trade_date, ticker) for ticker in pit_not_in_lifecycle_window)
        for ticker in pit_not_in_lifecycle_window:
            if ticker not in master_tickers:
                absent_from_master.append((trade_date, ticker))
            else:
                window_conflict.append((trade_date, ticker))
        union_hasher.update(trade_date.encode("ascii"))
        union_hasher.update(b"\0")
        union_hasher.update("\n".join(sorted(union)).encode("utf-8"))
        union_hasher.update(b"\n")
    omission_denominator = union_observations
    current_snapshot_omission_rate = (
        len(absent_from_master) / omission_denominator if omission_denominator else 0.0
    )
    return {
        "not_applicable": not requested,
        "required_session_count": len(requested),
        "reconciled_session_count": len(requested) - len(missing_sessions),
        "missing_pit_session_count": len(missing_sessions),
        "lifecycle_eligible_observation_count": lifecycle_observations,
        "pit_observation_count": pit_observations,
        "union_observation_count": union_observations,
        "lifecycle_missing_from_pit_count": len(missing_in_pit),
        "pit_missing_from_lifecycle_count": len(extra_in_pit),
        "pit_absent_from_master_count": len(absent_from_master),
        "pit_lifecycle_window_conflict_count": len(window_conflict),
        "missing_pit_session_sample": missing_sessions[:20],
        "lifecycle_missing_from_pit_sample": [
            {"trade_date": trade_date, "ticker": ticker}
            for trade_date, ticker in missing_in_pit[:20]
        ],
        "pit_missing_from_lifecycle_sample": [
            {"trade_date": trade_date, "ticker": ticker}
            for trade_date, ticker in extra_in_pit[:20]
        ],
        "pit_absent_from_master_sample": [
            {"trade_date": trade_date, "ticker": ticker}
            for trade_date, ticker in absent_from_master[:20]
        ],
        "pit_lifecycle_window_conflict_sample": [
            {"trade_date": trade_date, "ticker": ticker}
            for trade_date, ticker in window_conflict[:20]
        ],
        "current_snapshot_omission_rate": current_snapshot_omission_rate,
        "frozen_union_semantic_sha256": union_hasher.hexdigest(),
        "complete": bool(
            len(missing_sessions) == 0
            and len(missing_in_pit) == 0
            and len(window_conflict) == 0
        ),
    }


def build_daily_security_coverage(
    store: Path,
    start: date,
    end: date,
    state: Mapping[str, Any],
    generation_id: str | None = None,
) -> pd.DataFrame:
    """Per-session lifecycle-vs-daily coverage, without loading the full tape at once."""
    try:
        master_path = _reference_derived_path(
            store, "security_master.parquet", generation_id,
        )
    except SpineError:
        master_path = store / "reference" / "__absent_security_master.parquet"
    session_path = store / "reference" / "market_sessions.parquet"
    columns = [
        "trade_date", "eligible_n", "daily_n", "positive_volume_n", "suspended_n",
        "unexplained_missing_n", "unexpected_daily_n", "suspension_state_known",
        "pit_only_without_daily_n",
    ]
    if not master_path.exists() or not session_path.exists():
        return pd.DataFrame(columns=columns)
    master = _read_parquet_strict(master_path)
    master_tickers = set(master["ticker"].astype(str)) if not master.empty else set()
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
            eligible = _eligible_tickers_with_pit(store, master, trade_date)
            missing = eligible - actual
            # DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION -- a witness-missing PIT
            # ticker (absent from the current stock_basic-derived security
            # master) with no daily observation is not an unexplained coverage
            # gap: "the vendor's daily tape omitted it" and "it did not trade"
            # are not separable from these sources, so it is recorded as its
            # own telemetry bucket rather than promoted to event-eligible or
            # silently dropped.  A ticker that IS in the master with a
            # lifecycle window covering this date, and is missing from daily,
            # is unaffected and keeps blocking exactly as before.
            pit_only_without_daily = {ticker for ticker in missing if ticker not in master_tickers}
            explainable_missing = missing - pit_only_without_daily
            unexplained = (
                explainable_missing - suspended if suspension_known else explainable_missing
            )
            rows.append({
                "trade_date": trade_date,
                "eligible_n": len(eligible),
                "daily_n": len(actual),
                "positive_volume_n": len(positive),
                "suspended_n": len(suspended),
                "unexplained_missing_n": len(unexplained),
                "unexpected_daily_n": len(actual - eligible),
                "suspension_state_known": bool(suspension_known),
                "pit_only_without_daily_n": len(pit_only_without_daily),
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
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise SpineError(f"JSON receipt source is unreadable: {path}") from exc
    _assert_configured_token_absent_logical(decoded, artifact=path.name)
    return {
        "path": path.relative_to(store).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _request_receipts_summary(store: Path) -> dict[str, Any]:
    count_by_endpoint: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    hasher = hashlib.sha256()
    receipt_count = 0
    discarded_probe_rows = 0
    for path in sorted((store / "receipts" / "requests").glob("*/*/*.json")):
        raw = _receipt_bytes(path, store)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise SpineError(f"request receipt is unreadable: {path}") from exc
        _assert_configured_token_absent_logical(payload, artifact=path.name)
        endpoint = str(payload.get("endpoint") or "")
        status = str(payload.get("response_status") or "")
        if not endpoint or not status or not payload.get("request_contract_sha256"):
            raise SpineError(f"request receipt is malformed: {path}")
        count_by_endpoint[endpoint] = count_by_endpoint.get(endpoint, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "non_authoritative_cap_probe":
            discarded = payload.get("discarded_probe_row_count")
            if (
                payload.get("receipt_role") != "discarded_non_authoritative_cap_probe"
                or not isinstance(discarded, int)
                or discarded != payload.get("response_row_count")
            ):
                raise SpineError(f"cap-probe receipt is malformed: {path}")
            discarded_probe_rows += discarded
        hasher.update(path.relative_to(store).as_posix().encode("utf-8"))
        hasher.update(hashlib.sha256(raw).digest())
        receipt_count += 1
    return {
        "request_count": receipt_count,
        "count_by_endpoint": dict(sorted(count_by_endpoint.items())),
        "response_status_counts": dict(sorted(status_counts.items())),
        "discarded_non_authoritative_probe_rows": discarded_probe_rows,
        "semantic_sha256": hasher.hexdigest(),
    }


def _collector_provenance() -> dict[str, Any]:
    module_path = Path(__file__).resolve()
    repo_root = module_path.parents[1]
    schema_path = repo_root / "contracts" / "cn_tushare_a_share_spine_manifest.v1.schema.json"
    try:
        git_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        git_sha = "unavailable"
    query_contract = {
        "endpoint_fields": ENDPOINT_FIELDS,
        "row_caps": SOURCE_ROW_CAPS,
        "normalization_contract": "exact_schema_request_binding_lossless_scope_accounting_v2",
    }
    return {
        "collector_git_sha": git_sha,
        "collector_source_sha256": hashlib.sha256(module_path.read_bytes()).hexdigest(),
        "manifest_schema_sha256": (
            hashlib.sha256(schema_path.read_bytes()).hexdigest() if schema_path.exists() else None
        ),
        "endpoint_query_contract_sha256": hashlib.sha256(
            _canonical_json_bytes(query_contract)
        ).hexdigest(),
    }


def _lifecycle_edge_reconciliation(
    store: Path, master: pd.DataFrame, start: date, end: date,
) -> dict[str, Any]:
    lifecycle = master.set_index("ticker") if not master.empty else pd.DataFrame()
    before_list = 0
    after_delist = 0
    bse_before_launch = 0
    pit_list_date_mismatch = 0
    last_daily: dict[str, str] = {}
    for path in sorted((store / "daily").glob("year=*/month=*/part.parquet")):
        frame = _read_parquet_strict(path)
        frame = frame[
            (frame["trade_date"].astype(str) >= start.isoformat())
            & (frame["trade_date"].astype(str) <= end.isoformat())
        ]
        for row in frame.itertuples(index=False):
            ticker = str(row.ticker)
            day = str(row.trade_date)
            last_daily[ticker] = max(last_daily.get(ticker, day), day)
            if ticker in lifecycle.index:
                source = lifecycle.loc[ticker]
                effective_from = source.get("effective_from")
                effective_to = source.get("effective_to")
                if pd.notna(effective_from) and day < str(effective_from):
                    before_list += 1
                if pd.notna(effective_to) and day > str(effective_to):
                    after_delist += 1
            if ticker.endswith(".BJ") and day < BSE_LAUNCH.isoformat():
                bse_before_launch += 1
    for path in sorted((store / PIT_UNIVERSE_ENDPOINT).glob("year=*/month=*/part.parquet")):
        pit = _read_parquet_strict(path)
        if pit.empty:
            continue
        for row in pit.itertuples(index=False):
            if pd.notna(row.list_date) and str(row.list_date) and str(row.trade_date) < str(row.list_date):
                pit_list_date_mismatch += 1
    return {
        "delist_date_inclusive_contract": True,
        "daily_before_list_rows": before_list,
        "daily_after_delist_rows": after_delist,
        "BSE_rows_before_2021_11_15": bse_before_launch,
        "bak_basic_rows_before_reported_list_date": pit_list_date_mismatch,
        "last_daily_ticker_count": len(last_daily),
        "complete": not any((before_list, after_delist, bse_before_launch, pit_list_date_mismatch)),
    }


def _state_unit_summary(
    state: Mapping[str, Any], endpoint: str, expected: Sequence[str], store: Path | None = None,
) -> dict[str, Any]:
    records = {unit: _unit_record(state, endpoint, unit) for unit in expected}
    campaign_cache: dict[str, crs.CampaignVerification] = {}
    failed = [unit for unit, record in records.items() if record and record.get("status") == "failed"]
    accounting = []
    for unit in expected:
        record = records.get(unit) or {}
        source_rows = int(record.get("source_row_count", 0))
        landed = int(record.get("landed_a_row_count", record.get("row_count", 0)))
        excluded = int(record.get("known_excluded_row_count", 0))
        unknown = int(record.get("quarantined_unknown_row_count", 0))
        equation = source_rows == landed + excluded + unknown
        request_bound = bool(
            store is not None
            and _unit_request_receipts_valid(
                endpoint, unit, record, store, campaign_cache,
            )
        )
        artifact_bound = False
        if store is not None and isinstance(record.get("unit_artifact_receipts"), Mapping):
            try:
                observed_artifacts = _unit_artifact_receipts(store, endpoint, unit, record)
                artifact_bound = bool(
                    dict(record["unit_artifact_receipts"]) == observed_artifacts
                    and _unit_artifact_counts_match(observed_artifacts, record)
                )
            except SpineError:
                artifact_bound = False
        shard_coverage = (
            _shard_coverage(state, store, endpoint, unit, record)
            if store is not None else None
        )
        accounting.append({
            "unit": unit,
            "status": record.get("status", "pending"),
            "source_rows": source_rows,
            "landed_A_rows": landed,
            "known_excluded_rows": excluded,
            "quarantined_unknown_rows": unknown,
            "equation_holds": equation,
            "request_bound": request_bound,
            "artifact_bound": artifact_bound,
            "collection_method": record.get("collection_method", "pending"),
            "expected_ticker_count": (
                shard_coverage.get("expected_ticker_count") if shard_coverage else None
            ),
            "completed_ticker_count": (
                shard_coverage.get("completed_ticker_count") if shard_coverage else None
            ),
            "expected_ticker_sha256": (
                shard_coverage.get("expected_ticker_sha256") if shard_coverage else None
            ),
            "observed_ticker_sha256": (
                shard_coverage.get("observed_ticker_sha256") if shard_coverage else None
            ),
            "shard_coverage_complete": (
                shard_coverage.get("complete") if shard_coverage else None
            ),
            "complete": bool(
                store is not None
                and _unit_done(state, store, endpoint, unit, campaign_cache)
            ),
        })
    equations_hold = all(row["equation_holds"] for row in accounting)
    requests_bound = all(row["request_bound"] for row in accounting)
    artifacts_bound = all(row["artifact_bound"] for row in accounting)
    unknown_rows = sum(row["quarantined_unknown_rows"] for row in accounting)
    complete = [
        row["unit"] for row in accounting
        if row["status"] == "complete" and row["complete"]
    ]
    empty = [
        row["unit"] for row in accounting
        if row["status"] == "empty" and row["complete"]
    ]
    incomplete = [row["unit"] for row in accounting if not row["complete"]]
    pending = [unit for unit in incomplete if unit not in failed]
    unmatched = sum(
        int(record.get("unmatched_master_row_count", 0))
        for record in records.values() if record
    )
    return {
        "expected_units": len(expected),
        "complete_units": len(complete),
        "empty_units": len(empty),
        "failed_units": len(failed),
        "pending_units": len(pending),
        "complete": bool(
            len(complete) + len(empty) == len(expected)
            and equations_hold and requests_bound and artifacts_bound
            and unknown_rows == 0 and unmatched == 0
        ),
        "failed_or_pending_sample": incomplete[:20],
        "source_row_count": sum(row["source_rows"] for row in accounting),
        "landed_A_row_count": sum(row["landed_A_rows"] for row in accounting),
        "known_excluded_row_count": sum(row["known_excluded_rows"] for row in accounting),
        "quarantined_unknown_row_count": unknown_rows,
        "source_accounting_equations_hold": equations_hold,
        "all_units_request_bound": requests_bound,
        "all_units_artifact_bound": artifacts_bound,
        "unmatched_master_row_count": unmatched,
        "request_receipt_count": sum(
            sum(
                1 for receipt in record.get("request_receipts", [])
                if isinstance(receipt, Mapping)
                and receipt.get("path")
                and (store is None or (store / str(receipt["path"])).is_file())
            )
            for record in records.values() if record
        ),
        "unit_accounting": accounting,
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


def _reference_source_receipts(
    store: Path, generation_id: str | None = None,
) -> list[dict[str, Any]]:
    """Hash every landed raw reference artifact before derived compilation."""
    receipts: list[dict[str, Any]] = []
    generation = generation_id or _current_reference_generation(store, required=False)
    if generation is None:
        return receipts
    bse = _file_receipt(
        _reference_source_path(store, generation, "bse_mapping"),
        store,
        ["o_code", "n_code"],
    )
    if bse is not None:
        receipts.append(bse)
    generation_dir = _reference_generation_dir(store, generation)
    for path in sorted((generation_dir / "source_stock_basic").glob("*.parquet")):
        receipt = _file_receipt(path, store, ["ts_code"])
        assert receipt is not None
        receipts.append(receipt)
    for path in sorted((generation_dir / "source_fund_basic").glob("*.parquet")):
        receipt = _file_receipt(path, store, ["ts_code"])
        assert receipt is not None
        receipts.append(receipt)
    for path in sorted((store / "reference" / "trade_calendar").glob("year=*.parquet")):
        receipt = _file_receipt(path, store, KEY_COLUMNS["trade_calendar"])
        assert receipt is not None
        receipts.append(receipt)
    return receipts


def _range_campaign_manifest_summaries(
    store: Path, state: Mapping[str, Any], start: date, end: date,
) -> dict[str, dict[str, Any] | None]:
    """Expose exact campaign evidence without copying paid raw payloads."""
    summaries: dict[str, dict[str, Any] | None] = {}
    campaigns = state.get("range_campaigns", {})
    if not isinstance(campaigns, Mapping):
        raise SpineError("range campaign state is malformed")
    for endpoint in sorted(DENSE_ENDPOINTS):
        record = campaigns.get(endpoint)
        if record is None:
            summaries[endpoint] = None
            continue
        if not isinstance(record, Mapping):
            raise SpineError(f"{endpoint} range campaign state is malformed")
        campaign_id = str(record.get("campaign_id") or "")
        try:
            plan = crs.load_plan(store, campaign_id)
            progress = crs.campaign_progress(store, plan)
        except crs.RangeShardError as exc:
            raise SpineError(f"{endpoint} range campaign evidence is invalid") from exc
        if (
            plan.get("endpoint") != endpoint
            or record.get("start_date") != plan.get("start_date")
            or record.get("end_date") != plan.get("end_date")
        ):
            raise SpineError(f"{endpoint} central range state does not bind its plan")
        plan_path = store / "range_campaigns" / campaign_id / "plan.json"
        plan_receipt = _json_file_receipt(plan_path, store)
        if plan_receipt is None:
            raise SpineError(f"{endpoint} range campaign plan is absent")
        probe = record.get("cap_probe_receipt")
        if not isinstance(probe, Mapping) or not probe.get("path"):
            raise SpineError(f"{endpoint} range campaign lacks its cap trigger receipt")
        trigger_unit = str(record.get("trigger_unit") or "")
        if not _unit_request_receipts_valid(
            endpoint,
            trigger_unit,
            {
                "collection_method": "per_ticker_shards",
                "request_receipts": [probe],
            },
            store,
        ):
            raise SpineError(f"{endpoint} range campaign cap trigger is not request-bound")
        probe_path = _contained_store_path(store, probe["path"])
        probe_file = _json_file_receipt(probe_path, store)
        if probe_file is None:
            raise SpineError(f"{endpoint} range campaign cap trigger is absent")
        cap_probe_receipt = {
            **probe_file,
            "request_id": probe.get("request_id"),
            "response_row_count": int(probe.get("response_row_count", -1)),
            "response_status": probe.get("response_status"),
        }
        receipt_path = store / "range_campaigns" / campaign_id / "campaign_receipt.json"
        verification: crs.CampaignVerification | None = None
        terminal_reference: dict[str, Any] | None = None
        terminal_receipt: Mapping[str, Any] | None = None
        if receipt_path.exists():
            try:
                verification = crs.verify_campaign(store, campaign_id)
                terminal_reference = crs.campaign_receipt_reference(store, verification)
            except crs.RangeShardError as exc:
                raise SpineError(f"{endpoint} terminal range receipt is invalid") from exc
            terminal_receipt = verification.receipt
        campaign_cache = (
            {campaign_id: verification} if verification is not None else {}
        )
        bound_days = 0
        for trade_date_text in plan["sessions"]:
            unit = _compact(_parse_date(trade_date_text))
            unit_record = _unit_record(state, endpoint, unit) or {}
            if _unit_request_receipts_valid(
                endpoint, unit, unit_record, store, campaign_cache,
            ):
                bound_days += 1
        status = str(record.get("status") or "")
        if status not in {"collecting", "complete", "failed"}:
            raise SpineError(f"{endpoint} range campaign status is invalid")
        summaries[endpoint] = {
            "endpoint": endpoint,
            "campaign_id": campaign_id,
            "status": status,
            "requested_range_matches_manifest": bool(
                plan["start_date"] == start.isoformat()
                and plan["end_date"] == end.isoformat()
            ),
            "start_date": plan["start_date"],
            "end_date": plan["end_date"],
            "trigger_unit": trigger_unit,
            "source_row_cap": int(plan["source_row_cap"]),
            "split_width_sessions": int(plan["source_row_cap"]) - 1,
            "split_rule": plan["split_rule"],
            "session_count": int(plan["session_count"]),
            "session_sha256": plan["session_sha256"],
            "query_identity_count": int(plan["query_identity_count"]),
            "query_identity_sha256": plan["query_identity_sha256"],
            "reference_generation_id": plan["reference_generation_id"],
            "reference_generation_semantic_sha256": plan[
                "reference_generation_semantic_sha256"
            ],
            "universe_witness_sha256": plan["universe_witness_sha256"],
            **progress,
            "plan_receipt": plan_receipt,
            "cap_probe_count": 1,
            "cap_probe_receipt": cap_probe_receipt,
            "terminal_campaign_receipt": terminal_reference,
            "observed_response_row_count": (
                int(terminal_receipt["observed_response_row_count"])
                if terminal_receipt is not None else None
            ),
            "authoritative_row_count": (
                int(terminal_receipt["authoritative_row_count"])
                if terminal_receipt is not None else None
            ),
            "duplicate_alias_observation_row_count": (
                int(terminal_receipt["duplicate_alias_observation_row_count"])
                if terminal_receipt is not None else None
            ),
            "conflicting_alias_row_count": (
                int(terminal_receipt["conflicting_alias_row_count"])
                if terminal_receipt is not None else None
            ),
            "source_accounting_complete": (
                bool(terminal_receipt["source_accounting_complete"])
                if terminal_receipt is not None else False
            ),
            "transposed_session_count": bound_days,
            "all_day_receipts_bound": bool(
                verification is not None
                and verification.complete
                and bound_days == int(plan["session_count"])
            ),
        }
    return summaries


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
    manifest_endpoints = tuple(dict.fromkeys((PIT_UNIVERSE_ENDPOINT, *DEFAULT_ENDPOINTS, *endpoints)))
    generated_at = generated_at or _utc_now().isoformat()
    generation = _current_reference_generation(store, required=False)
    master_path = (
        _reference_derived_path(store, "security_master.parquet", generation)
        if generation else store / "reference" / "__absent_security_master.parquet"
    )
    aliases_path = (
        _reference_derived_path(store, "identity_aliases.parquet", generation)
        if generation else store / "reference" / "__absent_identity_aliases.parquet"
    )
    classification_path = (
        _reference_derived_path(store, "instrument_classification.parquet", generation)
        if generation else store / "reference" / "__absent_instrument_classification.parquet"
    )
    sessions_path = store / "reference" / "market_sessions.parquet"
    master = _read_parquet_strict(master_path) if master_path.exists() else pd.DataFrame()
    aliases = _read_parquet_strict(aliases_path) if aliases_path.exists() else pd.DataFrame()
    sessions = _read_parquet_strict(sessions_path) if sessions_path.exists() else pd.DataFrame()
    stock_basic_units = [
        f"{generation}:{exchange}:{status}" for exchange in EXCHANGES for status in LIST_STATUSES
    ] if generation else []
    fund_basic_units = [f"{generation}:{status}" for status in FUND_STATUSES] if generation else []
    calendar_units = [
        f"{exchange}:{_compact(segment_start)}:{_compact(segment_end)}"
        for _, segment_start, segment_end in _year_segments(CALENDAR_HISTORY_START, end)
        for exchange in CALENDAR_EXCHANGES
    ]
    namechange_units = [
        f"{year}:{_compact(min(end, date(year, 12, 31)))}"
        for year in range(NAME_HISTORY_START_YEAR, end.year + 1)
    ]
    reference_source_units = {
        "stock_basic": _state_unit_summary(state, "stock_basic", stock_basic_units, store),
        "bse_mapping": _state_unit_summary(
            state, "bse_mapping", [f"{generation}:all"] if generation else [], store,
        ),
        "fund_basic": _state_unit_summary(state, "fund_basic", fund_basic_units, store),
        "trade_cal": _state_unit_summary(state, "trade_cal", calendar_units, store),
        "namechange": _state_unit_summary(state, "namechange", namechange_units, store),
    }
    reference_source_artifacts = _reference_source_receipts(store, generation)
    reference_ready = bool(
        not master.empty
        and not aliases.empty
        and classification_path.exists()
        and sessions_path.exists()
        and generation is not None
        and all(summary["complete"] for summary in reference_source_units.values())
        and all(receipt["duplicate_key_rows"] == 0 for receipt in reference_source_artifacts)
    )

    endpoint_receipts: dict[str, Any] = {}
    endpoints_complete = True
    for endpoint in manifest_endpoints:
        expected = _expected_endpoint_units(store, start, end, endpoint)
        unit_summary = _state_unit_summary(state, endpoint, expected, store)
        partitions, totals = _partition_receipts(store, endpoint)
        daily_key_coverage = (
            _dense_key_coverage_vs_daily(store, endpoint, start, end)
            if endpoint in {"daily_basic", "stk_limit"} else None
        )
        not_applicable = bool(
            not expected and (
                (endpoint == "stock_st" and end < ST_DAILY_START)
                or (endpoint == PIT_UNIVERSE_ENDPOINT and end < PIT_UNIVERSE_START)
            )
        )
        endpoint_complete = (
            (not_applicable or (bool(expected) and unit_summary["complete"]))
            and totals["duplicate_key_rows"] == 0
            and (daily_key_coverage is None or daily_key_coverage["complete"])
        )
        endpoints_complete = endpoints_complete and endpoint_complete
        endpoint_receipts[endpoint] = {
            "required": True,
            "not_applicable": not_applicable,
            "expected_session_units": len(expected),
            "complete_units": unit_summary["complete_units"],
            "empty_units": unit_summary["empty_units"],
            "failed_units": unit_summary["failed_units"],
            "pending_units": unit_summary["pending_units"],
            "coverage_pct": round(
                100.0 * (unit_summary["complete_units"] + unit_summary["empty_units"])
                / len(expected), 6,
            )
            if expected else (100.0 if not_applicable else 0.0),
            "complete": endpoint_complete,
            "failed_or_pending_sample": unit_summary["failed_or_pending_sample"],
            "source_row_count": unit_summary["source_row_count"],
            "landed_A_row_count": unit_summary["landed_A_row_count"],
            "known_excluded_row_count": unit_summary["known_excluded_row_count"],
            "quarantined_unknown_row_count": unit_summary["quarantined_unknown_row_count"],
            "source_accounting_equations_hold": unit_summary["source_accounting_equations_hold"],
            "all_units_request_bound": unit_summary["all_units_request_bound"],
            "all_units_artifact_bound": unit_summary["all_units_artifact_bound"],
            "request_receipt_count": unit_summary["request_receipt_count"],
            "unit_accounting": unit_summary["unit_accounting"],
            "daily_key_coverage": daily_key_coverage,
            "partitions": partitions,
            **totals,
        }

    event_sources_ready = all(
        endpoint in endpoint_receipts and endpoint_receipts[endpoint]["complete"]
        for endpoint in ("daily", "daily_basic", "stk_limit")
    )
    canonical_event_substrate = (
        build_canonical_event_substrate(store, start, end)
        if event_sources_ready else {
            "ready": False,
            "row_count": 0,
            "positive_volume_rows": 0,
            "source_limit_rows": 0,
            "no_published_limit_rows": 0,
            "daily_basic_limit_status_audited_rows": 0,
            "daily_source": "tushare.daily_unadjusted_nominal",
            "limit_source": "tushare.stk_limit_exact_daily",
            "integer_price_unit": "CNY_cents",
            "calculated_limit_role": "validator_only_never_event_authority",
            "partitions": [],
        }
    )

    coverage = build_daily_security_coverage(store, start, end, state, generation)
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
        # Telemetry only (DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION C6) -- never
        # part of the `complete` conjunction below.
        "pit_only_without_daily_observations": int(coverage.get(
            "pit_only_without_daily_n", pd.Series(dtype=int)
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
    coverage_receipt["artifact"] = _file_receipt(
        store / "coverage" / "daily_security_coverage.parquet",
        store, ["trade_date"],
    )

    security_receipt = _file_receipt(master_path, store, ["ticker"])
    alias_receipt = _file_receipt(aliases_path, store, ["alias_ticker", "alias_kind"])
    classification_receipt = _file_receipt(
        classification_path, store, ["scope_classification", "ticker"],
    )
    session_receipt = _file_receipt(sessions_path, store, ["trade_date"])
    name_history_partitions, name_history_rows, name_history_semantic = _name_history_receipts(store)
    state_receipt = _json_file_receipt(store / "collection_state.json", store)
    request_receipts = _request_receipts_summary(store)
    provenance = _collector_provenance()
    lifecycle = _lifecycle_edge_reconciliation(store, master, start, end)
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
    pit_lifecycle = _pit_lifecycle_reconciliation(store, master, sessions, start, end)
    range_campaigns = _range_campaign_manifest_summaries(store, state, start, end)

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": generated_at,
        "authority": AUTHORITY,
        "source": SOURCE_NAME,
        "deployment_status": (
            "operational_backfill_gate_code_reviewed"
            if BULK_HISTORICAL_BACKFILL_READY
            else "foundation_only_range_shards_synthetic_no_live_canary"
        ),
        "bulk_historical_backfill_ready": BULK_HISTORICAL_BACKFILL_READY,
        "provenance": provenance,
        "request_receipts": request_receipts,
        "collection_state": state_receipt,
        "requested_range": {"start": start.isoformat(), "end": end.isoformat()},
        "complete": bool(
            BULK_HISTORICAL_BACKFILL_READY
            and reference_ready
            and endpoints_complete
            and pit_lifecycle["complete"]
            and coverage_receipt["complete"]
            and canonical_event_substrate["ready"]
            and lifecycle["complete"]
        ),
        "reference": {
            "ready": reference_ready,
            "generation_id": generation,
            "generation_pointer": _json_file_receipt(
                store / "reference" / "current_generation.json", store,
            ),
            "security_master": security_receipt,
            "identity_aliases": alias_receipt,
            "instrument_classification": classification_receipt,
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
        "range_campaigns": range_campaigns,
        "pit_lifecycle_reconciliation": pit_lifecycle,
        "canonical_event_substrate": canonical_event_substrate,
        "daily_security_coverage": coverage_receipt,
        "lifecycle_edge_reconciliation": lifecycle,
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
            "point_in_time_universe": {
                "source": "tushare.bak_basic exact trade_date",
                "exact_daily_start": PIT_UNIVERSE_START.isoformat(),
                "pre_2016_completeness": "no_independent_daily_universe_witness",
                "reconciliation_law": (
                    "universe is lifecycle union PIT; a PIT row the current stock_basic "
                    "snapshot omits is a legal union member recorded as telemetry; "
                    "lifecycle-eligible securities missing from PIT and PIT rows "
                    "contradicting their own master lifecycle window block completeness. "
                    "A PIT observation alone grants no trading/event or canonical-identity "
                    "authority; positive-volume plus exact legal-band evidence is what "
                    "proves historical trading."
                ),
                "contract": TUSHARE_BAK_BASIC_DOC_URL,
            },
            "source_row_accounting": {
                "equation": "source_rows = landed_A_rows + known_excluded_rows + quarantined_unknown_rows",
                "completion_law": "every unit equation holds and quarantined_unknown_rows == 0",
                "known_exclusion_source": (
                    "independent tushare.fund_basic identities plus official SSE/SZSE "
                    "B-share code families"
                ),
                "fund_contract": TUSHARE_FUND_BASIC_DOC_URL,
                "sse_code_contract": SSE_SECURITY_CODE_GUIDE_URL,
                "szse_code_contract": SZSE_SECURITY_CODE_RANGE_URL,
            },
            "compliance": {
                "status": "CHAIRMAN_VERIFIED_PRIVATE / SATISFIED",
                "evidence_scope": "confidential_outside_coding_scope_nda_privacy",
                "runtime_gate": False,
            },
            "cap_fallback": {
                "endpoints": ["daily", "daily_basic", "stk_limit"],
                "whole_market_fast_path": "exact_trade_date_until_first_documented_cap",
                "cap_trigger_policy": (
                    "discard_probe_and_switch_entire_endpoint_requested_interval"
                ),
                "method": "immutable_per_ticker_date_range_campaign",
                "split_rule": (
                    "deterministic_contiguous_market_session_chunks_cap_minus_one_v1"
                ),
                "leaf_state_model": "separate_atomic_json_per_leaf",
                "attempt_receipt_model": "immutable_numbered_receipt_per_physical_request",
                "retry_priority": "unattempted_then_fewest_attempts",
                "bse_alias_resolution": (
                    "canonical_preferred_when_equal_conflicting_rows_retained_and_block"
                ),
                "transposition_rule": (
                    "terminal_campaign_then_exact_day_normalize_replace_and_receipt_bind"
                ),
                "request_estimate_formula": "H_e + I_e * ceil(S/(C_e-1)) + R_e",
                "range_shard_implemented": True,
                "synthetic_verification_complete": True,
                "live_canary_complete": False,
                "live_canary_required_for_promotion": True,
            },
            "price_basis": {
                "daily": "unadjusted nominal OHLC; pre_close is ex-rights adjusted vendor field",
                "pro_bar": "not called by this direct-REST collector",
            },
            "price_limit": {
                "event_authority": (
                    "tushare.daily unadjusted quotes joined to tushare.stk_limit; "
                    "touches/seals require integer-cent equality"
                ),
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
            "bak_basic exact PIT A-share universe witness begins 2016-01-01; pre-2016 remains a named gap",
            "TuShare trade_cal documentation does not advertise BSE; BSE sessions are derived from SSE=SZSE",
            "endpoint entitlement and sustained live throughput were not exercised in this code-only wave",
            "ticker-range cap recovery has synthetic proof only; licensed live cap-trigger parity and throughput are untested",
            "no bitemporal vendor-revision ledger; a same-key re-fetch replaces the local materialization",
            "single-host advisory writer lock is implemented; no distributed multi-host lease exists",
            "the existing Yahoo raw plane is split-adjusted and is incompatible with exact legal limit history",
        ],
        "ore_ledger": {
            "constructed": [
                "listed+delisted+paused+approved security lifecycle by exchange/status",
                "atomic immutable reference generations plus fund-based out-of-scope identities",
                "post-2016 exact-day bak_basic PIT A-share universe witness",
                "lossless source row accounting with unknown quarantine",
                "request-bound exact schemas and persisted request/response receipts",
                "immutable endpoint-wide ticker-date-range campaigns with cap-minus-one session leaves",
                "separate atomic leaf state, immutable physical-attempt receipts, and raw artifact hashes",
                "BSE canonical/historical alias de-duplication with retained conflict blocking",
                "discarded cap probes, terminal/day receipts, and exact-day transposition binding",
                "terminal landed/classification/request artifacts bound by recomputed semantic receipts",
                "BSE old-code to canonical 920-code identity aliases",
                "SSE/SZSE exact-calendar consensus with session positions",
                "nominal daily OHLCV plus explicit positive-volume state",
                "daily_basic, stk_limit, suspend_d and stock_st exact-date partitions",
                "effective-dated name/ST-name history",
                "per-session lifecycle/daily/suspension completeness reconciliation",
                "integer-cent nominal event substrate joined to vendor exact daily upper/lower limits",
                "Decimal half-up limit validator with one-tick separation and floor rules",
                "strict vendor-bound OHLC and integer-equality touch/seal classification",
            ],
            "not_tested": [
                "pro_bar adjusted-price construction",
                "pre-2016 exact daily ST membership",
                "direct BSE trade-calendar endpoint",
                "minute, auction, order-book, seal-time or fillability history",
                "licensed live cap-trigger parity and purchased-addon entitlement",
                "sustained throughput, transient retry distribution, wall-clock, and paid request cost",
                "historical reconciliation of calculated bounds against vendor stk_limit across all rule eras",
            ],
        },
    }
    stable_identity_payload = dict(manifest)
    stable_identity_payload.pop("generated_at", None)
    unsigned_bytes = _canonical_json_bytes(stable_identity_payload)
    _assert_configured_token_absent(unsigned_bytes, artifact="completeness_manifest(stable_identity)")
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
    canary: bool = False,
    query: Callable[..., pd.DataFrame | None] | None = None,
    require_token: bool = True,
    now: Callable[[], datetime] = _utc_now,
) -> dict[str, Any]:
    """Run one bounded/resumable collection wave and publish a manifest.

    A missing token is an honest no-op before any store write.  Every real or
    injected request path stays bounded by the technical gates: request budget,
    the safety ceiling, exact request/schema binding, and
    ``BULK_HISTORICAL_BACKFILL_READY``.  ``require_token=False`` is a test seam
    for injected responses, not a bypass of those gates.

    ``canary=True`` is the one execution path permitted while the bulk gate is
    still False, because the canary is the evidence that gate is waiting for.  It
    is hard-bounded before any store or network use -- at most
    ``CANARY_MAX_REQUESTS`` requests over at most ``CANARY_MAX_RANGE_DAYS``
    calendar days, never with ``allow_bulk``, and a documented row cap refuses
    rather than starting the unproven ticker-range campaign.  It is not a bulk
    backfill and does not promote anything.
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
    if canary:
        # Hard canary ceilings, checked before any store or network use.  These
        # are what make a real run safe while the bulk gate is still shut.
        if allow_bulk:
            raise SpineError("canary windows are never bulk runs; drop allow_bulk")
        if max_requests <= 0 or max_requests > CANARY_MAX_REQUESTS:
            raise SpineError(
                f"canary max_requests must be 1..{CANARY_MAX_REQUESTS}; got {max_requests}"
            )
        span_days = (end_date - start_date).days + 1
        if span_days > CANARY_MAX_RANGE_DAYS:
            raise SpineError(
                f"canary range is capped at {CANARY_MAX_RANGE_DAYS} calendar days; "
                f"requested {span_days}"
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
    if not BULK_HISTORICAL_BACKFILL_READY and not canary:
        raise SpineError(
            "full-A collector is foundation-only: scalable ticker-range cap fallback "
            "has not been code-reviewed, so collection is disabled before store/network "
            "use outside a bounded canary window (--canary / canary=True)"
        )

    store_path = _validate_private_store_path(Path(store))
    with spine_store_lock(store_path):
        collector = TushareAShareSpineCollector(
            store_path, query=query, now=now, max_requests=max_requests,
            canary=canary,
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
                    stage = "pit_universe"
                    pit_ready = collector.collect_pit_universe(start_date, end_date)
                    if not pit_ready:
                        stage = "pit_universe_incomplete"
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
        if (store_path / "reference" / "market_sessions.parquet").exists():
            manifest = build_completeness_manifest(
                store_path, start_date, end_date, selected,
                generated_at=now().astimezone(timezone.utc).isoformat(),
            )
    return {
        "dry_run": False,
        "no_op": False,
        "canary": bool(canary),
        "bulk_historical_backfill_ready": BULK_HISTORICAL_BACKFILL_READY,
        "requests_made": collector.requests_made,
        "capped": capped,
        "stage": stage,
        "failures": collector.failures,
        "manifest_complete": bool(manifest and manifest.get("complete")),
        "manifest_path": str(store_path / "completeness_manifest.json") if manifest else None,
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
    parser.add_argument(
        "--canary", action="store_true",
        help=(
            f"bounded real canary window permitted while the bulk readiness gate is "
            f"still closed: at most {CANARY_MAX_REQUESTS} requests over "
            f"{CANARY_MAX_RANGE_DAYS} calendar days, never with --allow-bulk, and a "
            "documented row cap refuses instead of starting a range campaign"
        ),
    )
    args = parser.parse_args()
    result = collect(
        start=args.start, end=args.end, store=args.store, endpoints=args.endpoints,
        max_requests=args.max_requests, allow_bulk=args.allow_bulk,
        refresh_reference=args.refresh_reference, dry_run=args.dry_run,
        canary=args.canary,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    _main()
