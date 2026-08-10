"""Clock-free W1B.3B projection of the current SPY raw-close ratio.

The source is the credential-free public ``massive_stock_day`` R2 plane.  That
plane is mutable, so a usable read is deliberately a small transaction rather
than a single GET: manifest GET, SPY HEAD/GET/HEAD, then an identical manifest
GET.  Strong single-part ETags, byte lengths, last-modified values, bodies, and
the publish-last manifest anchor must all agree before any source object exists.

Only the last 21 consecutive frozen-v1 XNYS session dates support the feature.
Older rows remain source-support evidence; they are not reconstructed
point-in-time observations.  The value is a provider-documented unadjusted
daily-aggregate close ratio, not an economic return.  XNYS binds dates only;
the provider bar may include eligible full-market-day trades and does not
authenticate a regular-session close.  Corporate actions are explicitly
unevaluated.  The projector samples no clock and carries display/context-only,
zero-weight authority.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import os
import re
import stat
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

SOURCE_OBSERVATION_SCHEMA = "market_memory.spy_daily_price_source_observation.v1"
SNAPSHOT_SCHEMA = "market_memory.spy_raw_close_ratio_snapshot.v1"
PROFILE = "public_r2_massive_stock_day_spy_raw.v1"
TRANSFORM_VERSION = "market_memory.spy_raw_close_ratio_20_sessions.v1"
FEATURE = "price.raw_close_ratio_20_sessions"

PUBLIC_R2_HOST = "pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"
PUBLIC_R2_BASE = f"https://{PUBLIC_R2_HOST}"
MANIFEST_URL = f"{PUBLIC_R2_BASE}/massive_stock_day/_manifest.json"
SPY_PARQUET_URL = f"{PUBLIC_R2_BASE}/massive_stock_day/SPY.parquet"

_GIT_SOURCE_PATHS = {
    "canary_identity_config": "config/market_memory_canary.v1.json",
    "xnys_calendar_module": "lib/nyse_calendar.py",
    "massive_entitlement_record": "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md",
    "technical_price_basis_contract": (
        "config/market_memory_technical_price_basis.v1.json"
    ),
}
_GIT_SOURCE_ROLES = tuple(_GIT_SOURCE_PATHS)
_GIT_SOURCE_LIMITS = {
    "canary_identity_config": 32 * 1024,
    "xnys_calendar_module": 256 * 1024,
    "massive_entitlement_record": 64 * 1024,
    "technical_price_basis_contract": 32 * 1024,
}
_CANARY_CONFIG_SHA256_V1 = (
    "5e7823e48866b2c0828122b65f684ed5872c6816a6224f61e44db4c03d129b33"
)
_CALENDAR_SHA256_V1 = "7c9167fd416babb64c3067ae7e6237615011ad79e26d826e57005486496410ce"
_MASSIVE_ENTITLEMENT_SHA256_V1 = (
    "82ad971b46d4159739117d3defe19a25a2a24ede45e5e8d28494c5849e757891"
)
_MASSIVE_ENTITLEMENT_ASSERTIONS_V1 = (
    "aggregates",
    "second/minute/hourly/daily",
    "External redistribution",
    "Derived Materials",
    "Retention",
    "The executed document is held privately by the operator",
)
_TECHNICAL_PRICE_BASIS_SHA256_V1 = (
    "ce0244d9c18e3fdcb621c7ced6e3700cb8cb43ff0952b355b82d0542ed6b1be9"
)

_MAX_MANIFEST_BYTES = 512 * 1024
_MAX_SPY_PARQUET_BYTES = 8 * 1024 * 1024
_MIN_SPY_ROWS = 21
_MAX_SPY_ROWS = 4_096
_MAX_PARQUET_ROW_GROUPS = 32
_MAX_PARQUET_UNCOMPRESSED_BYTES = 16 * 1024 * 1024
_MAX_MANIFEST_FILES = 30_000
_MAX_FILENAME_BYTES = 160
_PARQUET_PHYSICAL_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "transactions",
    "date",
)
_PRICE_COLUMNS = ("open", "high", "low", "close")
_INTEGER_COLUMNS = ("volume", "transactions")

_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")
_GIT_OID = _COMMIT
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_MD5_ETAG_HEADER = re.compile(r'"([a-f0-9]{32})"\Z')
_CONTENT_LENGTH = re.compile(r"0|[1-9][0-9]*\Z")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_SOURCE_ID = re.compile(r"mmtechsrc_[a-f0-9]{64}\Z")
_SNAPSHOT_ID = re.compile(r"mmtechsnap_[a-f0-9]{64}\Z")

_CALENDAR_MIN_YEAR = 1962
_CALENDAR_MAX_YEAR = 2100
_ONE_OFF_CLOSURES_V1 = frozenset(
    {
        date(2012, 10, 29),
        date(2012, 10, 30),
        date(2018, 12, 5),
        date(2025, 1, 9),
    }
)


def _authority_v1() -> dict[str, Any]:
    """Return the frozen v1 authority without a mutable registry dependency."""

    return {
        "tier": "display",
        "horizon_role": "context",
        "context_only": True,
        "proposal_weight": 0,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "may_escalate": False,
        "may_trade": False,
        "may_originate": False,
        "may_select_options_candidate": False,
        "may_execute": False,
        "may_write_options_episode": False,
        "may_append_outcome": False,
        "may_train_prophet": False,
    }


def _canary_config_v1() -> dict[str, Any]:
    """Return the exact reviewed identity/config literal for this profile."""

    return {
        "schema": "market_memory.canary_identity_config.v1",
        "symbol": "SPY",
        "subject": {
            "canonical_key": "US:ETF:SPDR_SP_500_ETF_TRUST",
            "subject_id": (
                "mmsecurity_5fc37e8db34f74314b654c910ea8bacfa7de8b5d2d067f2e5421c9d5745ceb4c"
            ),
            "instrument_key": "US:ARCX:SPY:USD",
            "instrument_id": (
                "mmsecurity_6f361f5bad9f06a3b2ff157585d5728f55f77198420959aadd8922d1045c3fea"
            ),
            "identity_version": (
                "mmidentityv_65ec5e55473e953b55fa2d146f40e8b56dfae2e68a3df7423405db1034d16903"
            ),
            "mic": "ARCX",
            "currency": "USD",
        },
        "universe": {
            "canonical_key": "US_MARKET_CONTEXT_CANARY",
            "universe_id": (
                "mmuniverse_5f6904b77722f506a8d1d6f283ef69678a1ec7df3b2c1fc25cc1a15a3a4e8e6a"
            ),
            "membership_status": "market_scope",
        },
        "calendar": {
            "canonical_key": "US_CASH_EQUITIES",
            "calendar_id": (
                "mmcalendar_a102c5367c17f9c0b4df3af5c2826824fc112935ec76e6d18d55833f53644e0c"
            ),
            "market_session": "XNYS_REGULAR",
            "rules_version": "lib.nyse_calendar.full_day_closures.v1",
            "coverage": "full_day_closures_only",
            "quality": {
                "status": "degraded",
                "flags": ["partial_coverage"],
                "staleness_seconds": 0,
                "imputed": False,
            },
        },
        "authority": _authority_v1(),
    }


def _technical_price_basis_contract_v1() -> dict[str, Any]:
    """Return the reviewed provider-semantics assertion bound by v1."""

    return {
        "schema": "market_memory.technical_price_basis_contract.v1",
        "source_product": "us_stocks_sip/day_aggs_v1",
        "provider": "Massive",
        "documentation": {
            "url": (
                "https://massive.com/docs/flat-files/stocks/overview?"
                "assetClass=stocks&license=personal&name=stocks_basic"
            ),
            "reviewed_on": "2026-08-10",
            "assertion": "provider_documents_stock_flat_files_as_unadjusted",
        },
        "price_basis": {
            "basis": "provider_documented_unadjusted_flat_file",
            "source_session_scope": (
                "provider_daily_aggregate_eligible_trades_full_market_day"
            ),
            "regular_session_close_authenticated": False,
            "xnys_calendar_dates_only": True,
            "raw_unadjusted": True,
            "split_adjusted": False,
            "dividend_adjusted": False,
            "other_corporate_action_adjusted": False,
            "economic_return": False,
            "basis_authenticated_by_shape": False,
        },
        "limitations": {
            "provider_contract_not_inferred_from_bytes": True,
            "regular_session_close_not_authenticated": True,
            "point_in_time_corporate_actions": False,
            "split_detection": False,
        },
        "authority": _authority_v1(),
    }


_TRANSPORT_POLICY = {
    "transaction": "get_manifest_head_if_match_get_head_manifest_recheck",
    "https_only": True,
    "canonical_host_and_paths": True,
    "redirects_allowed": False,
    "query_allowed": False,
    "compression_allowed": False,
    "strong_single_part_md5_etag_required": True,
    "conditional_get_if_match_required": True,
}
_TEMPORAL_POLICY = {
    "current_endpoint_only": True,
    "historical_rows_operational": False,
    "historical_rows_support_only": True,
    "availability_clock_owner": "private_technical_store_first_durable_write",
    "projector_samples_clock": False,
}
_LIMITATIONS = {
    "current_endpoint_only": True,
    "historical_rows_support_only": True,
    "historical_rows_operational": False,
    "session_calendar_use": "dates_only",
    "provider_daily_aggregate_scope": (
        "provider_daily_aggregate_eligible_trades_full_market_day"
    ),
    "regular_session_close_authenticated": False,
    "point_in_time_corporate_actions": False,
    "total_return": False,
    "calendar_coverage": "full_day_closures_only",
    "calendar_partial_coverage": True,
}
_PRICE_BASIS = {
    "basis": "provider_documented_unadjusted_flat_file",
    "source_product": "us_stocks_sip/day_aggs_v1",
    "source_contract_role": "technical_price_basis_contract",
    "source_contract_sha256": _TECHNICAL_PRICE_BASIS_SHA256_V1,
    "basis_authenticated_by_shape": False,
    "source_session_scope": (
        "provider_daily_aggregate_eligible_trades_full_market_day"
    ),
    "regular_session_close_authenticated": False,
    "xnys_calendar_dates_only": True,
    "raw_unadjusted": True,
    "split_adjusted": False,
    "dividend_adjusted": False,
    "other_corporate_action_adjusted": False,
    "economic_return": False,
    "corporate_action_status": "not_evaluated",
    "split_detection": False,
}
_QUALITY = {
    "status": "degraded",
    "flags": [
        "corporate_actions_not_evaluated",
        "raw_unadjusted_not_economic_return",
        "regular_session_close_not_authenticated",
        "partial_calendar_coverage",
    ],
    "actual_output_source": True,
    "current_endpoint_only": True,
    "imputed": False,
    "training_eligible": False,
    "promotion_eligible": False,
}


class MarketMemoryTechnicalObservationError(ValueError):
    """The public source transaction or clock-free projection is inadmissible."""


@dataclass(frozen=True)
class HttpResponse:
    """Exact response boundary used by the credential-free transport adapter."""

    status: int
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes = b""


@dataclass(frozen=True)
class FetchedSpyDailyInputs:
    """Detached remote bytes and their stable content validators."""

    manifest_body: bytes
    manifest_headers: tuple[tuple[str, str], ...]
    spy_body: bytes
    spy_headers: tuple[tuple[str, str], ...]

    def detached(self) -> FetchedSpyDailyInputs:
        return copy.deepcopy(self)


@dataclass(frozen=True)
class PinnedTechnicalSources:
    """Exact identity/calendar bodies read from one pinned repository tip."""

    pinned_commit: str
    canary_config_body: bytes
    calendar_module_body: bytes
    license_record_body: bytes
    price_basis_contract_body: bytes
    git_blob_oids: tuple[tuple[str, str], ...]

    def detached(self) -> PinnedTechnicalSources:
        return copy.deepcopy(self)


@dataclass(frozen=True)
class PinnedTechnicalInputs:
    """Remote transaction plus reviewed Git sources needed by the projector."""

    fetched: FetchedSpyDailyInputs
    pinned_sources: PinnedTechnicalSources

    def detached(self) -> PinnedTechnicalInputs:
        return copy.deepcopy(self)


@dataclass(frozen=True)
class TechnicalSnapshotBundle:
    """Exact raw evidence plus canonical source and feature object bytes."""

    pinned_inputs: PinnedTechnicalInputs
    source_observation: dict[str, Any]
    source_observation_bytes: bytes
    feature_object: dict[str, Any]
    feature_object_bytes: bytes

    def detached(self) -> TechnicalSnapshotBundle:
        return copy.deepcopy(self)


@dataclass(frozen=True)
class _RemoteValidator:
    content_type: str
    content_length: int
    etag_md5: str
    last_modified: str
    last_modified_at: datetime

    def headers(self) -> tuple[tuple[str, str], ...]:
        return (
            ("content-type", self.content_type),
            ("content-length", str(self.content_length)),
            ("etag", f'"{self.etag_md5}"'),
            ("last-modified", self.last_modified),
        )


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise MarketMemoryTechnicalObservationError(
            "technical projection must be finite canonical JSON"
        ) from exc


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _md5(body: bytes) -> str:
    # R2's strong single-part ETag is an MD5 content validator.  It is used only
    # as transport evidence; SHA-256 remains the cryptographic content digest.
    return hashlib.md5(body).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON token {value}")


def _strict_json_object(body: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise MarketMemoryTechnicalObservationError(
            f"{label} must be strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise MarketMemoryTechnicalObservationError(f"{label} must be a JSON object")
    return value


def _exact_fields(
    value: Mapping[str, Any], *, expected: frozenset[str], label: str
) -> None:
    if type(value) is not dict or frozenset(value) != expected:
        raise MarketMemoryTechnicalObservationError(
            f"{label} fields are not the frozen v1 contract"
        )


def _canonical_url(url: object, *, expected: str, label: str) -> str:
    if type(url) is not str or url != expected:
        raise MarketMemoryTechnicalObservationError(
            f"{label} response did not remain on its canonical URL"
        )
    parsed = urlsplit(url)
    expected_parts = urlsplit(expected)
    if (
        parsed.scheme != "https"
        or parsed.hostname != PUBLIC_R2_HOST
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != expected_parts.path
        or parsed.query
        or parsed.fragment
    ):
        raise MarketMemoryTechnicalObservationError(
            f"{label} URL violates the frozen HTTPS host/path contract"
        )
    return url


def _header_map(response: HttpResponse, *, label: str) -> dict[str, str]:
    if type(response.headers) is not tuple:
        raise MarketMemoryTechnicalObservationError(
            f"{label} headers must be exact name/value pairs"
        )
    result: dict[str, str] = {}
    for item in response.headers:
        if type(item) is not tuple or len(item) != 2:
            raise MarketMemoryTechnicalObservationError(
                f"{label} headers must be exact name/value pairs"
            )
        name, value = item
        if (
            type(name) is not str
            or type(value) is not str
            or not name
            or any(character in name for character in "\r\n:")
            or any(character in value for character in "\r\n")
            or value != value.strip()
        ):
            raise MarketMemoryTechnicalObservationError(
                f"{label} contains a malformed HTTP header"
            )
        normalized = name.lower()
        if normalized in result:
            raise MarketMemoryTechnicalObservationError(
                f"{label} contains duplicate HTTP headers"
            )
        result[normalized] = value
    for forbidden in (
        "content-encoding",
        "transfer-encoding",
        "content-range",
        "location",
    ):
        if forbidden in result:
            raise MarketMemoryTechnicalObservationError(
                f"{label} uses forbidden compression, range, or redirect metadata"
            )
    return result


def _response_validator(
    response: HttpResponse,
    *,
    expected_url: str,
    expected_content_type: str,
    method: str,
    byte_limit: int,
    label: str,
) -> _RemoteValidator:
    if type(response) is not HttpResponse:
        raise MarketMemoryTechnicalObservationError(
            f"{label} fetcher must return HttpResponse"
        )
    if type(response.status) is not int or response.status != 200:
        raise MarketMemoryTechnicalObservationError(f"{label} did not return HTTP 200")
    _canonical_url(response.url, expected=expected_url, label=label)
    headers = _header_map(response, label=label)
    required = {"content-type", "content-length", "etag", "last-modified"}
    if not required.issubset(headers):
        raise MarketMemoryTechnicalObservationError(
            f"{label} is missing a required content validator"
        )
    if headers["content-type"] != expected_content_type:
        raise MarketMemoryTechnicalObservationError(
            f"{label} content type is not canonical"
        )
    raw_length = headers["content-length"]
    if not _CONTENT_LENGTH.fullmatch(raw_length):
        raise MarketMemoryTechnicalObservationError(
            f"{label} content length is not canonical"
        )
    content_length = int(raw_length)
    if not 1 <= content_length <= byte_limit:
        raise MarketMemoryTechnicalObservationError(
            f"{label} content length is outside its frozen bound"
        )
    etag_match = _MD5_ETAG_HEADER.fullmatch(headers["etag"])
    if etag_match is None:
        raise MarketMemoryTechnicalObservationError(
            f"{label} requires one strong lowercase single-part MD5 ETag"
        )
    last_modified = headers["last-modified"]
    try:
        parsed_last_modified = parsedate_to_datetime(last_modified)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MarketMemoryTechnicalObservationError(
            f"{label} Last-Modified is not canonical IMF-fixdate"
        ) from exc
    if (
        parsed_last_modified.tzinfo is None
        or parsed_last_modified.utcoffset() != timedelta(0)
        or format_datetime(parsed_last_modified.astimezone(timezone.utc), usegmt=True)
        != last_modified
    ):
        raise MarketMemoryTechnicalObservationError(
            f"{label} Last-Modified is not canonical IMF-fixdate"
        )
    if type(response.body) is not bytes:
        raise MarketMemoryTechnicalObservationError(
            f"{label} body must be exact immutable bytes"
        )
    if method == "HEAD":
        if response.body:
            raise MarketMemoryTechnicalObservationError(
                f"{label} HEAD response unexpectedly contains a body"
            )
    elif method == "GET":
        if len(response.body) != content_length:
            raise MarketMemoryTechnicalObservationError(
                f"{label} body length differs from Content-Length"
            )
        if _md5(response.body) != etag_match.group(1):
            raise MarketMemoryTechnicalObservationError(
                f"{label} body differs from its strong ETag"
            )
    else:
        raise MarketMemoryTechnicalObservationError("unsupported source HTTP method")
    return _RemoteValidator(
        content_type=headers["content-type"],
        content_length=content_length,
        etag_md5=etag_match.group(1),
        last_modified=last_modified,
        last_modified_at=parsed_last_modified.astimezone(timezone.utc),
    )


def _default_fetcher(method: str, url: str, headers: Mapping[str, str]) -> HttpResponse:
    """Credential-free bounded HTTPS transport with redirects disabled."""

    limit = _MAX_MANIFEST_BYTES if url == MANIFEST_URL else _MAX_SPY_PARQUET_BYTES
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.request(
                method,
                url,
                headers=dict(headers),
                allow_redirects=False,
                stream=True,
                timeout=(10, 30),
            )
            response.raw.decode_content = False
            body = (
                b""
                if method == "HEAD" or response.status_code != 200
                else response.raw.read(limit + 1)
            )
            if len(body) > limit:
                raise MarketMemoryTechnicalObservationError(
                    "public source response exceeded its frozen byte bound"
                )
            return HttpResponse(
                status=response.status_code,
                url=response.url,
                headers=tuple(response.raw.headers.items()),
                body=body,
            )
    except MarketMemoryTechnicalObservationError:
        raise
    except (OSError, requests.RequestException) as exc:
        raise MarketMemoryTechnicalObservationError(
            "credential-free public source request failed"
        ) from exc


Fetcher = Callable[[str, str, Mapping[str, str]], HttpResponse]


def _fetch(
    fetcher: Fetcher,
    *,
    method: str,
    url: str,
    accept: str,
    if_match: str | None = None,
) -> HttpResponse:
    headers = {
        "Accept": accept,
        "Accept-Encoding": "identity",
        "User-Agent": "MastermindX-MarketMemory/1.0",
    }
    if if_match is not None:
        if _MD5_ETAG_HEADER.fullmatch(if_match) is None:
            raise MarketMemoryTechnicalObservationError(
                "conditional source ETag is not canonical"
            )
        headers["If-Match"] = if_match
    try:
        response = fetcher(method, url, headers)
    except MarketMemoryTechnicalObservationError:
        raise
    except Exception as exc:
        raise MarketMemoryTechnicalObservationError(
            "credential-free public source request failed"
        ) from exc
    if type(response) is not HttpResponse:
        raise MarketMemoryTechnicalObservationError(
            "source fetcher must return the frozen HttpResponse boundary"
        )
    return response


def fetch_current_spy_daily_inputs(
    *, fetcher: Fetcher | None = None
) -> FetchedSpyDailyInputs:
    """Perform and validate one stable public-R2 source transaction."""

    transport = _default_fetcher if fetcher is None else fetcher
    manifest_first = _fetch(
        transport,
        method="GET",
        url=MANIFEST_URL,
        accept="application/json",
    )
    spy_head_before = _fetch(
        transport,
        method="HEAD",
        url=SPY_PARQUET_URL,
        accept="application/octet-stream",
    )
    head_before_validator = _response_validator(
        spy_head_before,
        expected_url=SPY_PARQUET_URL,
        expected_content_type="application/octet-stream",
        method="HEAD",
        byte_limit=_MAX_SPY_PARQUET_BYTES,
        label="initial SPY HEAD",
    )
    spy_get = _fetch(
        transport,
        method="GET",
        url=SPY_PARQUET_URL,
        accept="application/octet-stream",
        if_match=f'"{head_before_validator.etag_md5}"',
    )
    spy_head_after = _fetch(
        transport,
        method="HEAD",
        url=SPY_PARQUET_URL,
        accept="application/octet-stream",
    )
    manifest_final = _fetch(
        transport,
        method="GET",
        url=MANIFEST_URL,
        accept="application/json",
    )

    manifest_first_validator = _response_validator(
        manifest_first,
        expected_url=MANIFEST_URL,
        expected_content_type="application/json",
        method="GET",
        byte_limit=_MAX_MANIFEST_BYTES,
        label="initial manifest GET",
    )
    manifest_final_validator = _response_validator(
        manifest_final,
        expected_url=MANIFEST_URL,
        expected_content_type="application/json",
        method="GET",
        byte_limit=_MAX_MANIFEST_BYTES,
        label="final manifest GET",
    )
    get_validator = _response_validator(
        spy_get,
        expected_url=SPY_PARQUET_URL,
        expected_content_type="application/octet-stream",
        method="GET",
        byte_limit=_MAX_SPY_PARQUET_BYTES,
        label="SPY GET",
    )
    head_after_validator = _response_validator(
        spy_head_after,
        expected_url=SPY_PARQUET_URL,
        expected_content_type="application/octet-stream",
        method="HEAD",
        byte_limit=_MAX_SPY_PARQUET_BYTES,
        label="final SPY HEAD",
    )
    if (
        manifest_first_validator != manifest_final_validator
        or manifest_first.body != manifest_final.body
    ):
        raise MarketMemoryTechnicalObservationError(
            "public manifest changed during the SPY source transaction"
        )
    if not (head_before_validator == get_validator == head_after_validator):
        raise MarketMemoryTechnicalObservationError(
            "SPY object changed during its HEAD/GET/HEAD transaction"
        )
    if manifest_first_validator.last_modified_at < get_validator.last_modified_at:
        raise MarketMemoryTechnicalObservationError(
            "publish-last manifest predates the SPY parquet"
        )

    # Parse the manifest before returning any source bytes.  Parquet/anchor parity
    # is completed by the pure projector after the pinned Git sources are attached.
    _validate_manifest(manifest_first.body)
    return FetchedSpyDailyInputs(
        manifest_body=bytes(manifest_first.body),
        manifest_headers=manifest_first_validator.headers(),
        spy_body=bytes(spy_get.body),
        spy_headers=get_validator.headers(),
    )


def _git(root: Path, *args: str, text: bool = False) -> bytes | str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=text,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MarketMemoryTechnicalObservationError(
            "cannot bind technical intake to Git"
        ) from exc
    return result.stdout


def _safe_stable_read(path: Path, *, role: str) -> bytes:
    try:
        path_before = path.lstat()
    except OSError as exc:
        raise MarketMemoryTechnicalObservationError(f"{role} is unavailable") from exc
    if stat.S_ISLNK(path_before.st_mode) or not stat.S_ISREG(path_before.st_mode):
        raise MarketMemoryTechnicalObservationError(
            f"{role} must be a regular non-symlink"
        )
    limit = _GIT_SOURCE_LIMITS[role]
    if not 1 <= path_before.st_size <= limit:
        raise MarketMemoryTechnicalObservationError(
            f"{role} is empty or exceeds its byte bound"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MarketMemoryTechnicalObservationError(
            f"{role} could not be opened safely"
        ) from exc
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        path_after = path.lstat()
    except OSError as exc:
        raise MarketMemoryTechnicalObservationError(
            f"{role} changed during its stable read"
        ) from exc
    finally:
        os.close(descriptor)
    body = b"".join(chunks)
    identities = {
        (
            item.st_dev,
            item.st_ino,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
            stat.S_IFMT(item.st_mode),
        )
        for item in (path_before, before, after, path_after)
    }
    if (
        len(identities) != 1
        or not stat.S_ISREG(after.st_mode)
        or len(body) != after.st_size
        or len(body) > limit
    ):
        raise MarketMemoryTechnicalObservationError(
            f"{role} changed during its stable read"
        )
    return body


def _full_head_commit(root: Path) -> str:
    value = str(_git(root, "rev-parse", "--verify", "HEAD^{commit}", text=True)).strip()
    if not _COMMIT.fullmatch(value):
        raise MarketMemoryTechnicalObservationError("repository HEAD is malformed")
    return value


def read_pinned_technical_sources(
    repository_root: str | Path,
    *,
    pinned_commit: str,
) -> PinnedTechnicalSources:
    """Read config/calendar bodies and prove exact ownership by current HEAD."""

    if type(pinned_commit) is not str or not _COMMIT.fullmatch(pinned_commit):
        raise MarketMemoryTechnicalObservationError(
            "pinned_commit must be one full lowercase Git object ID"
        )
    root = Path(repository_root).expanduser().resolve()
    if not root.is_dir():
        raise MarketMemoryTechnicalObservationError("repository root is unavailable")
    top = str(_git(root, "rev-parse", "--show-toplevel", text=True)).strip()
    if Path(top).resolve() != root:
        raise MarketMemoryTechnicalObservationError(
            "repository root must be the exact worktree top level"
        )
    if _full_head_commit(root) != pinned_commit:
        raise MarketMemoryTechnicalObservationError(
            "pinned_commit is not the current repository tip"
        )

    bodies: dict[str, bytes] = {}
    blob_oids: list[tuple[str, str]] = []
    for role in _GIT_SOURCE_ROLES:
        repo_path = _GIT_SOURCE_PATHS[role]
        body = _safe_stable_read(root / repo_path, role=role)
        tracked = _git(root, "show", f"{pinned_commit}:{repo_path}")
        if type(tracked) is not bytes or body != tracked:
            raise MarketMemoryTechnicalObservationError(
                f"{role} bytes differ from the pinned Git object"
            )
        object_type = str(
            _git(root, "cat-file", "-t", f"{pinned_commit}:{repo_path}", text=True)
        ).strip()
        blob_oid = str(
            _git(root, "rev-parse", f"{pinned_commit}:{repo_path}", text=True)
        ).strip()
        if object_type != "blob" or not _GIT_OID.fullmatch(blob_oid):
            raise MarketMemoryTechnicalObservationError(
                f"{role} is not one canonical Git blob"
            )
        bodies[role] = body
        blob_oids.append((role, blob_oid))

    if _full_head_commit(root) != pinned_commit:
        raise MarketMemoryTechnicalObservationError(
            "repository HEAD changed during technical intake"
        )
    return PinnedTechnicalSources(
        pinned_commit=pinned_commit,
        canary_config_body=bodies["canary_identity_config"],
        calendar_module_body=bodies["xnys_calendar_module"],
        license_record_body=bodies["massive_entitlement_record"],
        price_basis_contract_body=bodies["technical_price_basis_contract"],
        git_blob_oids=tuple(blob_oids),
    )


def _git_blob_oid(body: bytes, *, hexadecimal_length: int) -> str:
    framed = f"blob {len(body)}\0".encode("ascii") + body
    if hexadecimal_length == 40:
        return hashlib.sha1(framed).hexdigest()
    if hexadecimal_length == 64:
        return hashlib.sha256(framed).hexdigest()
    raise MarketMemoryTechnicalObservationError("unsupported Git object format")


def _validated_pinned_sources(
    value: PinnedTechnicalSources,
) -> PinnedTechnicalSources:
    if type(value) is not PinnedTechnicalSources:
        raise MarketMemoryTechnicalObservationError(
            "technical Git sources must use PinnedTechnicalSources"
        )
    if type(value.pinned_commit) is not str or not _COMMIT.fullmatch(
        value.pinned_commit
    ):
        raise MarketMemoryTechnicalObservationError("pinned Git commit is malformed")
    bodies = {
        "canary_identity_config": value.canary_config_body,
        "xnys_calendar_module": value.calendar_module_body,
        "massive_entitlement_record": value.license_record_body,
        "technical_price_basis_contract": value.price_basis_contract_body,
    }
    for role, body in bodies.items():
        if type(body) is not bytes or not body or len(body) > _GIT_SOURCE_LIMITS[role]:
            raise MarketMemoryTechnicalObservationError(
                f"{role} must be exact bounded immutable bytes"
            )
    if (
        type(value.git_blob_oids) is not tuple
        or any(
            type(item) is not tuple or len(item) != 2 for item in value.git_blob_oids
        )
        or tuple(item[0] for item in value.git_blob_oids) != _GIT_SOURCE_ROLES
    ):
        raise MarketMemoryTechnicalObservationError(
            "Git blob references are incomplete or out of order"
        )
    for role, oid in value.git_blob_oids:
        if type(oid) is not str or not _GIT_OID.fullmatch(oid):
            raise MarketMemoryTechnicalObservationError(
                "Git blob reference is malformed"
            )
        if oid != _git_blob_oid(bodies[role], hexadecimal_length=len(oid)):
            raise MarketMemoryTechnicalObservationError(
                f"{role} Git blob ID does not bind its exact bytes"
            )
    if _sha256(value.canary_config_body) != _CANARY_CONFIG_SHA256_V1:
        raise MarketMemoryTechnicalObservationError(
            "canary identity config does not match the frozen v1 SHA-256"
        )
    if (
        _strict_json_object(value.canary_config_body, label="canary identity config")
        != _canary_config_v1()
    ):
        raise MarketMemoryTechnicalObservationError(
            "canary identity config does not match the frozen v1 literal"
        )
    if _sha256(value.calendar_module_body) != _CALENDAR_SHA256_V1:
        raise MarketMemoryTechnicalObservationError(
            "XNYS calendar module does not match the frozen v1 SHA-256"
        )
    if _sha256(value.license_record_body) != _MASSIVE_ENTITLEMENT_SHA256_V1:
        raise MarketMemoryTechnicalObservationError(
            "Massive entitlement record does not match the reviewed v1 SHA-256"
        )
    try:
        license_text = value.license_record_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MarketMemoryTechnicalObservationError(
            "Massive entitlement record is not UTF-8"
        ) from exc
    if any(
        assertion not in license_text
        for assertion in _MASSIVE_ENTITLEMENT_ASSERTIONS_V1
    ):
        raise MarketMemoryTechnicalObservationError(
            "Massive entitlement record lacks a reviewed v1 rights assertion"
        )
    if _sha256(value.price_basis_contract_body) != _TECHNICAL_PRICE_BASIS_SHA256_V1:
        raise MarketMemoryTechnicalObservationError(
            "technical price-basis contract does not match the reviewed v1 SHA-256"
        )
    if (
        _strict_json_object(
            value.price_basis_contract_body,
            label="technical price-basis contract",
        )
        != _technical_price_basis_contract_v1()
    ):
        raise MarketMemoryTechnicalObservationError(
            "technical price-basis contract does not match the reviewed v1 literal"
        )
    return value.detached()


def _headers_validator(
    headers: object,
    *,
    expected_content_type: str,
    byte_limit: int,
    label: str,
) -> _RemoteValidator:
    if type(headers) is not tuple:
        raise MarketMemoryTechnicalObservationError(
            f"{label} validators must be exact header pairs"
        )
    response = HttpResponse(status=200, url=MANIFEST_URL, headers=headers, body=b"")
    # Reuse the strict header parser, then construct the validator directly.  The
    # stored body is validated separately because this is not a HEAD response.
    parsed_headers = _header_map(response, label=label)
    required = {"content-type", "content-length", "etag", "last-modified"}
    if set(parsed_headers) != required:
        raise MarketMemoryTechnicalObservationError(
            f"{label} validators contain noncanonical fields"
        )
    raw_length = parsed_headers["content-length"]
    etag_match = _MD5_ETAG_HEADER.fullmatch(parsed_headers["etag"])
    if (
        parsed_headers["content-type"] != expected_content_type
        or not _CONTENT_LENGTH.fullmatch(raw_length)
        or etag_match is None
    ):
        raise MarketMemoryTechnicalObservationError(f"{label} validators are malformed")
    length = int(raw_length)
    if not 1 <= length <= byte_limit:
        raise MarketMemoryTechnicalObservationError(
            f"{label} content length is outside its frozen bound"
        )
    raw_last_modified = parsed_headers["last-modified"]
    try:
        parsed_last_modified = parsedate_to_datetime(raw_last_modified)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MarketMemoryTechnicalObservationError(
            f"{label} Last-Modified is malformed"
        ) from exc
    if (
        parsed_last_modified.tzinfo is None
        or format_datetime(parsed_last_modified.astimezone(timezone.utc), usegmt=True)
        != raw_last_modified
    ):
        raise MarketMemoryTechnicalObservationError(
            f"{label} Last-Modified is malformed"
        )
    return _RemoteValidator(
        content_type=parsed_headers["content-type"],
        content_length=length,
        etag_md5=etag_match.group(1),
        last_modified=raw_last_modified,
        last_modified_at=parsed_last_modified.astimezone(timezone.utc),
    )


def _validated_fetched(value: FetchedSpyDailyInputs) -> FetchedSpyDailyInputs:
    if type(value) is not FetchedSpyDailyInputs:
        raise MarketMemoryTechnicalObservationError(
            "remote source must use FetchedSpyDailyInputs"
        )
    for body, limit, label in (
        (value.manifest_body, _MAX_MANIFEST_BYTES, "manifest body"),
        (value.spy_body, _MAX_SPY_PARQUET_BYTES, "SPY parquet body"),
    ):
        if type(body) is not bytes or not body or len(body) > limit:
            raise MarketMemoryTechnicalObservationError(
                f"{label} must be exact bounded immutable bytes"
            )
    manifest_validator = _headers_validator(
        value.manifest_headers,
        expected_content_type="application/json",
        byte_limit=_MAX_MANIFEST_BYTES,
        label="manifest",
    )
    spy_validator = _headers_validator(
        value.spy_headers,
        expected_content_type="application/octet-stream",
        byte_limit=_MAX_SPY_PARQUET_BYTES,
        label="SPY parquet",
    )
    for body, validator, label in (
        (value.manifest_body, manifest_validator, "manifest"),
        (value.spy_body, spy_validator, "SPY parquet"),
    ):
        if len(body) != validator.content_length or _md5(body) != validator.etag_md5:
            raise MarketMemoryTechnicalObservationError(
                f"{label} bytes do not match their stored transport validators"
            )
    if manifest_validator.last_modified_at < spy_validator.last_modified_at:
        raise MarketMemoryTechnicalObservationError(
            "publish-last manifest predates the SPY parquet"
        )
    _validate_manifest(value.manifest_body)
    return value.detached()


def _parse_date(value: object, *, field: str) -> date:
    if type(value) is not str or not _DATE.fullmatch(value):
        raise MarketMemoryTechnicalObservationError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise MarketMemoryTechnicalObservationError(
            f"{field} must be a valid ISO date"
        ) from exc
    if parsed.isoformat() != value:
        raise MarketMemoryTechnicalObservationError(f"{field} must be canonical")
    return parsed


def _exact_int(value: object, *, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MarketMemoryTechnicalObservationError(
            f"{field} is outside its frozen integer bound"
        )
    return value


def _validate_manifest(body: bytes) -> dict[str, Any]:
    manifest = _strict_json_object(body, label="public R2 manifest")
    _exact_fields(
        manifest,
        expected=frozenset({"dir", "count", "files", "store"}),
        label="public R2 manifest",
    )
    if manifest["dir"] != "massive_stock_day":
        raise MarketMemoryTechnicalObservationError(
            "public R2 manifest has the wrong directory"
        )
    count = _exact_int(
        manifest["count"],
        field="manifest count",
        minimum=100,
        maximum=_MAX_MANIFEST_FILES,
    )
    files = manifest["files"]
    if type(files) is not list or len(files) != count:
        raise MarketMemoryTechnicalObservationError(
            "public R2 manifest file list does not match its count"
        )
    for filename in files:
        if (
            type(filename) is not str
            or not filename
            or filename != Path(filename).name
            or filename in {".", ".."}
            or "\\" in filename
            or len(filename.encode("utf-8")) > _MAX_FILENAME_BYTES
            or not (filename.endswith(".parquet") or filename == "_backfill_state.json")
        ):
            raise MarketMemoryTechnicalObservationError(
                "public R2 manifest contains an unsafe or noncanonical filename"
            )
    if len(set(files)) != len(files) or files != sorted(files):
        raise MarketMemoryTechnicalObservationError(
            "public R2 manifest files must be unique and sorted"
        )
    if files.count("SPY.parquet") != 1 or files.count("_backfill_state.json") != 1:
        raise MarketMemoryTechnicalObservationError(
            "public R2 manifest must name exactly one SPY object and state sidecar"
        )

    store = manifest["store"]
    _exact_fields(
        store,
        expected=frozenset(
            {"store", "n_tickers", "latest_date", "updated_at", "coverage", "anchor"}
        ),
        label="public R2 store manifest",
    )
    if store["store"] != "massive_stock_day":
        raise MarketMemoryTechnicalObservationError("store manifest profile is wrong")
    n_tickers = _exact_int(
        store["n_tickers"],
        field="store ticker count",
        minimum=100,
        maximum=_MAX_MANIFEST_FILES - 1,
    )
    if n_tickers + 1 != count:
        raise MarketMemoryTechnicalObservationError(
            "store ticker count does not match the publish manifest"
        )
    latest = _parse_date(store["latest_date"], field="store latest_date")
    updated_at = store["updated_at"]
    if type(updated_at) is not str:
        raise MarketMemoryTechnicalObservationError("store updated_at is malformed")
    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketMemoryTechnicalObservationError(
            "store updated_at is malformed"
        ) from exc
    if updated.tzinfo is None or updated.utcoffset() != timedelta(0):
        raise MarketMemoryTechnicalObservationError("store updated_at must be UTC")
    if updated.astimezone(timezone.utc).date() < latest:
        raise MarketMemoryTechnicalObservationError(
            "store updated_at predates its latest source session"
        )

    coverage = store["coverage"]
    _exact_fields(
        coverage,
        expected=frozenset(
            {
                "first_day",
                "last_day",
                "n_processed_days",
                "max_missing_run_weekdays",
                "max_missing_run_weekdays_recent",
                "recent_window_bdays",
                "missing_sample",
            }
        ),
        label="store coverage",
    )
    first_day = _parse_date(coverage["first_day"], field="coverage first_day")
    last_day = _parse_date(coverage["last_day"], field="coverage last_day")
    if first_day > last_day or last_day != latest:
        raise MarketMemoryTechnicalObservationError(
            "store coverage bounds do not match its latest session"
        )
    _exact_int(
        coverage["n_processed_days"],
        field="coverage n_processed_days",
        minimum=1,
        maximum=10_000,
    )
    _exact_int(
        coverage["max_missing_run_weekdays"],
        field="coverage max_missing_run_weekdays",
        minimum=0,
        maximum=10_000,
    )
    _exact_int(
        coverage["max_missing_run_weekdays_recent"],
        field="coverage max_missing_run_weekdays_recent",
        minimum=0,
        maximum=10_000,
    )
    _exact_int(
        coverage["recent_window_bdays"],
        field="coverage recent_window_bdays",
        minimum=1,
        maximum=2_000,
    )
    missing_sample = coverage["missing_sample"]
    if type(missing_sample) is not list or len(missing_sample) > 10:
        raise MarketMemoryTechnicalObservationError(
            "coverage missing_sample is malformed"
        )
    missing_dates = [
        _parse_date(item, field="coverage missing_sample item")
        for item in missing_sample
    ]
    if missing_dates != sorted(set(missing_dates)) or any(
        item < first_day or item > last_day for item in missing_dates
    ):
        raise MarketMemoryTechnicalObservationError(
            "coverage missing_sample is unordered or outside coverage"
        )

    anchor = store["anchor"]
    _exact_fields(
        anchor,
        expected=frozenset(
            {"ticker", "first", "last", "n_rows", "max_gap_calendar_days"}
        ),
        label="SPY manifest anchor",
    )
    if anchor["ticker"] != "SPY":
        raise MarketMemoryTechnicalObservationError("manifest anchor is not SPY")
    anchor_first = _parse_date(anchor["first"], field="SPY anchor first")
    anchor_last = _parse_date(anchor["last"], field="SPY anchor last")
    if anchor_first > anchor_last or anchor_last != latest:
        raise MarketMemoryTechnicalObservationError(
            "SPY manifest anchor does not bind the store tip"
        )
    _exact_int(
        anchor["n_rows"],
        field="SPY anchor row count",
        minimum=_MIN_SPY_ROWS,
        maximum=_MAX_SPY_ROWS,
    )
    _exact_int(
        anchor["max_gap_calendar_days"],
        field="SPY anchor max calendar gap",
        minimum=1,
        maximum=31,
    )
    return manifest


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = following - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed_fixed_holiday(value: date) -> date:
    if value.weekday() == 5:
        return value - timedelta(days=1)
    if value.weekday() == 6:
        return value + timedelta(days=1)
    return value


def _frozen_v1_holidays(year: int) -> frozenset[date]:
    if type(year) is not int or not _CALENDAR_MIN_YEAR <= year <= _CALENDAR_MAX_YEAR:
        raise MarketMemoryTechnicalObservationError(
            "frozen XNYS calendar supports only years 1962 through 2100"
        )
    holidays: set[date] = set()
    new_year = date(year, 1, 1)
    if new_year.weekday() == 6:
        holidays.add(new_year + timedelta(days=1))
    elif new_year.weekday() != 5:
        holidays.add(new_year)
    if year >= 1998:
        holidays.add(_nth_weekday(year, 1, 0, 3))
    holidays.add(_nth_weekday(year, 2, 0, 3))
    holidays.add(_easter(year) - timedelta(days=2))
    holidays.add(_last_weekday(year, 5, 0))
    if year >= 2022:
        holidays.add(_observed_fixed_holiday(date(year, 6, 19)))
    holidays.add(_observed_fixed_holiday(date(year, 7, 4)))
    holidays.add(_nth_weekday(year, 9, 0, 1))
    holidays.add(_nth_weekday(year, 11, 3, 4))
    holidays.add(_observed_fixed_holiday(date(year, 12, 25)))
    return frozenset(item for item in holidays if item.year == year)


def is_frozen_v1_xnys_session(value: date) -> bool:
    """Return whether a date is a session under the frozen reviewed v1 rules."""

    if type(value) is not date:
        raise MarketMemoryTechnicalObservationError(
            "frozen XNYS session evaluator requires an exact date"
        )
    if not _CALENDAR_MIN_YEAR <= value.year <= _CALENDAR_MAX_YEAR:
        raise MarketMemoryTechnicalObservationError(
            "frozen XNYS calendar supports only years 1962 through 2100"
        )
    return (
        value.weekday() < 5
        and value not in _frozen_v1_holidays(value.year)
        and value not in _ONE_OFF_CLOSURES_V1
    )


def _previous_frozen_v1_session(value: date) -> date:
    candidate = value - timedelta(days=1)
    for _ in range(31):
        if candidate.year < _CALENDAR_MIN_YEAR:
            break
        if is_frozen_v1_xnys_session(candidate):
            return candidate
        candidate -= timedelta(days=1)
    raise MarketMemoryTechnicalObservationError(
        "no prior frozen XNYS session exists in the supported 31 days"
    )


def _read_spy_parquet(body: bytes) -> pd.DataFrame:
    try:
        parquet_file = pq.ParquetFile(io.BytesIO(body))
        metadata = parquet_file.metadata
    except Exception as exc:
        raise MarketMemoryTechnicalObservationError(
            "SPY source has unreadable parquet metadata"
        ) from exc
    if metadata is None:
        raise MarketMemoryTechnicalObservationError(
            "SPY source has no parquet metadata"
        )
    if not _MIN_SPY_ROWS <= metadata.num_rows <= _MAX_SPY_ROWS:
        raise MarketMemoryTechnicalObservationError(
            "SPY parquet row count is outside its frozen bound"
        )
    if metadata.num_columns != len(_PARQUET_PHYSICAL_COLUMNS):
        raise MarketMemoryTechnicalObservationError(
            "SPY parquet column count is not canonical"
        )
    if not 1 <= metadata.num_row_groups <= _MAX_PARQUET_ROW_GROUPS:
        raise MarketMemoryTechnicalObservationError(
            "SPY parquet row-group count is outside its frozen bound"
        )
    if tuple(parquet_file.schema_arrow.names) != _PARQUET_PHYSICAL_COLUMNS:
        raise MarketMemoryTechnicalObservationError(
            "SPY parquet columns or order are not canonical"
        )
    expected_types = (
        pa.float64(),
        pa.float64(),
        pa.float64(),
        pa.float64(),
        pa.int64(),
        pa.int64(),
        pa.timestamp("ms"),
    )
    if tuple(field.type for field in parquet_file.schema_arrow) != expected_types:
        raise MarketMemoryTechnicalObservationError(
            "SPY parquet physical types are not canonical"
        )
    total_uncompressed = 0
    for row_group_index in range(metadata.num_row_groups):
        row_group = metadata.row_group(row_group_index)
        if row_group.num_rows < 0 or row_group.num_columns != metadata.num_columns:
            raise MarketMemoryTechnicalObservationError(
                "SPY parquet row-group metadata is malformed"
            )
        for column_index in range(row_group.num_columns):
            size = row_group.column(column_index).total_uncompressed_size
            if type(size) is not int or size < 0:
                raise MarketMemoryTechnicalObservationError(
                    "SPY parquet uncompressed column size is malformed"
                )
            total_uncompressed += size
            if total_uncompressed > _MAX_PARQUET_UNCOMPRESSED_BYTES:
                raise MarketMemoryTechnicalObservationError(
                    "SPY parquet exceeds its uncompressed byte bound"
                )
    try:
        table = parquet_file.read(use_threads=False)
        if (
            table.num_rows != metadata.num_rows
            or table.num_columns != metadata.num_columns
        ):
            raise MarketMemoryTechnicalObservationError(
                "SPY materialized shape differs from its metadata"
            )
        frame = table.to_pandas()
    except MarketMemoryTechnicalObservationError:
        raise
    except Exception as exc:
        raise MarketMemoryTechnicalObservationError(
            "SPY parquet could not be safely materialized"
        ) from exc
    if not isinstance(frame, pd.DataFrame):
        raise MarketMemoryTechnicalObservationError("SPY source is not tabular")
    return frame


def _validated_spy_rows(
    body: bytes, *, anchor: Mapping[str, Any]
) -> tuple[list[date], list[float]]:
    frame = _read_spy_parquet(body)
    if tuple(frame.columns) != (*_PRICE_COLUMNS, *_INTEGER_COLUMNS):
        raise MarketMemoryTechnicalObservationError(
            "SPY parquet value columns or order are not canonical"
        )
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.name != "date":
        raise MarketMemoryTechnicalObservationError(
            "SPY parquet requires the canonical date index"
        )
    if (
        frame.index.tz is not None
        or frame.index.has_duplicates
        or not frame.index.is_monotonic_increasing
        or (frame.index != frame.index.normalize()).any()
    ):
        raise MarketMemoryTechnicalObservationError(
            "SPY date index is duplicated, unordered, zoned, or non-midnight"
        )
    for column in _PRICE_COLUMNS:
        if frame[column].dtype != "float64":
            raise MarketMemoryTechnicalObservationError(
                f"SPY {column} column must remain floating point"
            )
    for column in _INTEGER_COLUMNS:
        if frame[column].dtype != "int64":
            raise MarketMemoryTechnicalObservationError(
                f"SPY {column} column must remain integer"
            )
        if (frame[column] < 0).any():
            raise MarketMemoryTechnicalObservationError(
                f"SPY {column} is negative or noncanonical"
            )

    dates = [timestamp.date() for timestamp in frame.index]
    closes: list[float] = []
    for _, row in frame.iterrows():
        prices: dict[str, float] = {}
        for column in _PRICE_COLUMNS:
            raw = row[column]
            try:
                parsed = float(raw)
            except (TypeError, ValueError, OverflowError) as exc:
                raise MarketMemoryTechnicalObservationError(
                    f"SPY {column} is not numeric"
                ) from exc
            if not math.isfinite(parsed) or parsed <= 0:
                raise MarketMemoryTechnicalObservationError(
                    f"SPY {column} is non-finite or non-positive"
                )
            prices[column] = parsed
        if prices["high"] < max(prices["open"], prices["low"], prices["close"]):
            raise MarketMemoryTechnicalObservationError("SPY high is below its bar")
        if prices["low"] > min(prices["open"], prices["high"], prices["close"]):
            raise MarketMemoryTechnicalObservationError("SPY low is above its bar")
        closes.append(prices["close"])

    if len(dates) != anchor["n_rows"]:
        raise MarketMemoryTechnicalObservationError(
            "SPY parquet row count differs from the manifest anchor"
        )
    if (
        dates[0].isoformat() != anchor["first"]
        or dates[-1].isoformat() != anchor["last"]
    ):
        raise MarketMemoryTechnicalObservationError(
            "SPY parquet date bounds differ from the manifest anchor"
        )
    maximum_gap = max(
        (current - previous).days for previous, current in pairwise(dates)
    )
    if maximum_gap != anchor["max_gap_calendar_days"]:
        raise MarketMemoryTechnicalObservationError(
            "SPY parquet maximum gap differs from the manifest anchor"
        )
    support_dates = dates[-21:]
    expected = [support_dates[-1]]
    for _ in range(20):
        expected.append(_previous_frozen_v1_session(expected[-1]))
    expected.reverse()
    if support_dates != expected:
        raise MarketMemoryTechnicalObservationError(
            "SPY source lacks the exact last 21 consecutive frozen XNYS sessions"
        )
    return dates, closes


def _artifact_ref(
    *, url: str, body: bytes, validator: _RemoteValidator
) -> dict[str, Any]:
    return {
        "url": url,
        "sha256": _sha256(body),
        "bytes": len(body),
        "etag_md5": validator.etag_md5,
        "last_modified": validator.last_modified,
        "content_type": validator.content_type,
    }


def _git_artifact_refs(
    sources: PinnedTechnicalSources,
) -> dict[str, dict[str, Any]]:
    bodies = {
        "canary_identity_config": sources.canary_config_body,
        "xnys_calendar_module": sources.calendar_module_body,
        "massive_entitlement_record": sources.license_record_body,
        "technical_price_basis_contract": sources.price_basis_contract_body,
    }
    oids = dict(sources.git_blob_oids)
    return {
        role: {
            "repo_path": _GIT_SOURCE_PATHS[role],
            "sha256": _sha256(bodies[role]),
            "bytes": len(bodies[role]),
            "git_blob_oid": oids[role],
        }
        for role in _GIT_SOURCE_ROLES
    }


def _source_observation_id(
    *, session: str, remote_sources: Mapping[str, Any], git_sources: Mapping[str, Any]
) -> str:
    core = {
        "profile": PROFILE,
        "session": session,
        "remote_sources": dict(remote_sources),
        "git_source_sha256": {
            role: git_sources[role]["sha256"] for role in _GIT_SOURCE_ROLES
        },
    }
    return "mmtechsrc_" + _sha256(_canonical_bytes(core))


def _snapshot_id(*, source_observation_id: str, state: Mapping[str, Any]) -> str:
    core = {
        "source_observation_id": source_observation_id,
        "transform_version": TRANSFORM_VERSION,
        "semantic_value": dict(state),
    }
    return "mmtechsnap_" + _sha256(_canonical_bytes(core))


def project_current_spy_raw_close_ratio(
    inputs: PinnedTechnicalInputs,
) -> TechnicalSnapshotBundle:
    """Purely project the current endpoint from exact remote and Git inputs."""

    if type(inputs) is not PinnedTechnicalInputs:
        raise MarketMemoryTechnicalObservationError(
            "technical inputs must use the frozen PinnedTechnicalInputs boundary"
        )
    checked_fetched = _validated_fetched(inputs.fetched)
    checked_sources = _validated_pinned_sources(inputs.pinned_sources)
    manifest = _validate_manifest(checked_fetched.manifest_body)
    anchor = manifest["store"]["anchor"]
    dates, closes = _validated_spy_rows(checked_fetched.spy_body, anchor=anchor)

    manifest_validator = _headers_validator(
        checked_fetched.manifest_headers,
        expected_content_type="application/json",
        byte_limit=_MAX_MANIFEST_BYTES,
        label="manifest",
    )
    spy_validator = _headers_validator(
        checked_fetched.spy_headers,
        expected_content_type="application/octet-stream",
        byte_limit=_MAX_SPY_PARQUET_BYTES,
        label="SPY parquet",
    )
    remote_sources = {
        "publish_manifest": _artifact_ref(
            url=MANIFEST_URL,
            body=checked_fetched.manifest_body,
            validator=manifest_validator,
        ),
        "spy_daily_parquet": _artifact_ref(
            url=SPY_PARQUET_URL,
            body=checked_fetched.spy_body,
            validator=spy_validator,
        ),
    }
    git_sources = _git_artifact_refs(checked_sources)
    session = dates[-1].isoformat()
    source_observation_id = _source_observation_id(
        session=session,
        remote_sources=remote_sources,
        git_sources=git_sources,
    )
    source_observation = {
        "schema": SOURCE_OBSERVATION_SCHEMA,
        "source_observation_id": source_observation_id,
        "profile": PROFILE,
        "session": session,
        "remote_sources": remote_sources,
        "git_sources": git_sources,
        "manifest_anchor": copy.deepcopy(anchor),
        "transport_policy": copy.deepcopy(_TRANSPORT_POLICY),
        "temporal_policy": copy.deepcopy(_TEMPORAL_POLICY),
        "limitations": copy.deepcopy(_LIMITATIONS),
        "authority": _authority_v1(),
    }
    source_observation_bytes = _canonical_bytes(source_observation)

    start_close = closes[-21]
    end_close = closes[-1]
    ratio = end_close / start_close
    if not math.isfinite(ratio) or ratio <= 0:
        raise MarketMemoryTechnicalObservationError(
            "raw close ratio is non-finite or non-positive"
        )
    state = {
        "feature": FEATURE,
        "lookback_sessions": 20,
        "support_observations": 21,
        "start_session": dates[-21].isoformat(),
        "end_session": session,
        "start_close": start_close,
        "end_close": end_close,
        "value": ratio,
    }
    config = _canary_config_v1()
    subject = config["subject"]
    feature_object = {
        "schema": SNAPSHOT_SCHEMA,
        "snapshot_id": _snapshot_id(
            source_observation_id=source_observation_id,
            state=state,
        ),
        "source_observation_id": source_observation_id,
        "session": session,
        "transform_version": TRANSFORM_VERSION,
        "subject": {
            "symbol": config["symbol"],
            "subject_id": subject["subject_id"],
            "instrument_id": subject["instrument_id"],
            "identity_version": subject["identity_version"],
            "mic": subject["mic"],
            "currency": subject["currency"],
            "universe_id": config["universe"]["universe_id"],
            "calendar_id": config["calendar"]["calendar_id"],
            "market_session": config["calendar"]["market_session"],
        },
        "state": state,
        "price_basis": copy.deepcopy(_PRICE_BASIS),
        "quality": copy.deepcopy(_QUALITY),
        "limitations": copy.deepcopy(_LIMITATIONS),
        "authority": _authority_v1(),
    }
    feature_object_bytes = _canonical_bytes(feature_object)
    return TechnicalSnapshotBundle(
        pinned_inputs=PinnedTechnicalInputs(
            fetched=checked_fetched,
            pinned_sources=checked_sources,
        ),
        source_observation=source_observation,
        source_observation_bytes=source_observation_bytes,
        feature_object=feature_object,
        feature_object_bytes=feature_object_bytes,
    )


def build_current_spy_raw_close_ratio(
    repository_root: str | Path,
    *,
    pinned_commit: str,
    fetcher: Fetcher | None = None,
) -> TechnicalSnapshotBundle:
    """Fetch the current public object and bind it to one exact repository tip."""

    fetched = fetch_current_spy_daily_inputs(fetcher=fetcher)
    sources = read_pinned_technical_sources(
        repository_root,
        pinned_commit=pinned_commit,
    )
    return project_current_spy_raw_close_ratio(
        PinnedTechnicalInputs(fetched=fetched, pinned_sources=sources)
    )


def validate_technical_snapshot_bundle(
    value: TechnicalSnapshotBundle,
) -> TechnicalSnapshotBundle:
    """Reproject exact detached raw bytes and reject any bundle tampering."""

    if type(value) is not TechnicalSnapshotBundle:
        raise MarketMemoryTechnicalObservationError(
            "technical snapshot must use the frozen bundle boundary"
        )
    if (
        type(value.source_observation) is not dict
        or type(value.feature_object) is not dict
    ):
        raise MarketMemoryTechnicalObservationError(
            "technical source and feature objects must be dictionaries"
        )
    if (
        type(value.source_observation_bytes) is not bytes
        or type(value.feature_object_bytes) is not bytes
    ):
        raise MarketMemoryTechnicalObservationError(
            "technical source and feature bodies must be exact immutable bytes"
        )
    if value.source_observation_bytes != _canonical_bytes(value.source_observation):
        raise MarketMemoryTechnicalObservationError(
            "technical source observation bytes are noncanonical or tampered"
        )
    if value.feature_object_bytes != _canonical_bytes(value.feature_object):
        raise MarketMemoryTechnicalObservationError(
            "technical feature object bytes are noncanonical or tampered"
        )
    rebuilt = project_current_spy_raw_close_ratio(value.pinned_inputs)
    if (
        value.source_observation != rebuilt.source_observation
        or value.source_observation_bytes != rebuilt.source_observation_bytes
        or value.feature_object != rebuilt.feature_object
        or value.feature_object_bytes != rebuilt.feature_object_bytes
    ):
        raise MarketMemoryTechnicalObservationError(
            "technical bundle does not reproduce from its exact raw evidence"
        )
    if not _SOURCE_ID.fullmatch(rebuilt.source_observation["source_observation_id"]):
        raise MarketMemoryTechnicalObservationError("technical source ID is malformed")
    if not _SNAPSHOT_ID.fullmatch(rebuilt.feature_object["snapshot_id"]):
        raise MarketMemoryTechnicalObservationError(
            "technical snapshot ID is malformed"
        )
    return rebuilt.detached()


__all__ = [
    "FEATURE",
    "MANIFEST_URL",
    "PROFILE",
    "PUBLIC_R2_BASE",
    "SNAPSHOT_SCHEMA",
    "SOURCE_OBSERVATION_SCHEMA",
    "SPY_PARQUET_URL",
    "TRANSFORM_VERSION",
    "FetchedSpyDailyInputs",
    "HttpResponse",
    "MarketMemoryTechnicalObservationError",
    "PinnedTechnicalInputs",
    "PinnedTechnicalSources",
    "TechnicalSnapshotBundle",
    "build_current_spy_raw_close_ratio",
    "fetch_current_spy_daily_inputs",
    "is_frozen_v1_xnys_session",
    "project_current_spy_raw_close_ratio",
    "read_pinned_technical_sources",
    "validate_technical_snapshot_bundle",
]
