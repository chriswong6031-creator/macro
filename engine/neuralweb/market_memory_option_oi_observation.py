"""Future-only W1B.5 availability probe for the first Massive SPY option page.

This lane proves only that one bounded current API page contains at least one
syntactically valid open-interest observation.  It does not infer the option
measurement session from a calendar or from the capture clock.  It retains the
exact raw entity body as private evidence, but it does not project vendor
tickers, resolve permanent option identities, parse contract multipliers,
calculate GEX, sum open interest, or project any individual open-interest
value.

The transport performs exactly one request.  The bearer credential is supplied
by the caller, is never sourced from process state, and is not retained.  The
pure projector receives a detached exact entity body, selected safe response
headers, the response-body completion clock, and two exact Git-owned source
bodies.  ``observed_at`` belongs to a later private store boundary.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import os
import re
import stat
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from os import environ as _process_environment
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import parse_qsl, quote, quote_plus, unquote, unquote_plus, urlsplit

import requests

PROBE_RECEIPT_SCHEMA = "market_memory.option_oi_probe_receipt.v1"
SOURCE_OBSERVATION_SCHEMA = "market_memory.spy_option_oi_source_observation.v1"
PROFILE = "massive_spy_option_oi_first_page_availability.v1"

SOURCE_HOST = "api.massive.com"
SOURCE_PATH = "/v3/snapshot/options/SPY"
SOURCE_QUERY = "limit=250"
SOURCE_URL = f"https://{SOURCE_HOST}{SOURCE_PATH}?{SOURCE_QUERY}"

MAX_ENTITY_BYTES = 4 * 1024 * 1024
MAX_RESULTS = 250
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 200_000
MAX_JSON_INTEGER_DIGITS = 128
MAX_VENDOR_TICKER_BYTES = 160
MAX_NEXT_URL_BYTES = 16 * 1024

_GIT_SOURCE_PATHS = {
    "option_oi_source_config": "config/market_memory_option_oi_source.v1.json",
    "massive_entitlement_record": "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md",
}
_GIT_SOURCE_ROLES = tuple(_GIT_SOURCE_PATHS)
_GIT_SOURCE_LIMITS = {
    "option_oi_source_config": 32 * 1024,
    "massive_entitlement_record": 64 * 1024,
}
_OPTION_OI_SOURCE_CONFIG_SHA256_V1 = (
    "f7ae3d0f7c4a3fd41db48a8c7d6263a0e88a52af36943d3f1de40df0c0689898"
)
_MASSIVE_ENTITLEMENT_SHA256_V1 = (
    "82ad971b46d4159739117d3defe19a25a2a24ede45e5e8d28494c5849e757891"
)

_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")
_GIT_OID = _COMMIT
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_PROBE_ID = re.compile(r"mmoptionoiprobe_[a-f0-9]{64}\Z")
_SOURCE_ID = re.compile(r"mmoptionoisrc_[a-f0-9]{64}\Z")
_CONTENT_LENGTH = re.compile(r"0|[1-9][0-9]*\Z")
_UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:"
    r"[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_VENDOR_TICKER = re.compile(r"O:[A-Z0-9][A-Z0-9._-]*\Z")
_CREDENTIAL_JSON_KEY = re.compile(
    rb'"(?:authorization|proxy_authorization|api[_-]?key|x[_-]?api[_-]?key|'
    rb'access[_-]?token|client[_-]?secret|private[_-]?key|credential|secret)"\s*:',
    re.IGNORECASE,
)
_CREDENTIAL_JSON_KEY_NAME = re.compile(
    r"(?:authorization|proxy[_-]?authorization|api[_-]?key|x[_-]?api[_-]?key|"
    r"access[_-]?token|client[_-]?secret|private[_-]?key|credential|secret)\Z",
    re.IGNORECASE,
)
_FORBIDDEN_RESPONSE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
    }
)
_SELECTED_RESPONSE_HEADERS = ("content-type", "content-length")


def _authority_v1() -> dict[str, Any]:
    """Return the frozen zero-authority fence without a registry dependency."""

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


def _source_config_v1() -> dict[str, Any]:
    """Return the exact reviewed source-semantics literal for frozen v1."""

    return {
        "schema": "market_memory.option_oi_source_config.v1",
        "profile": PROFILE,
        "provider": "Massive",
        "source_product": "v3_snapshot_options_chain",
        "request": {
            "method": "GET",
            "scheme": "https",
            "host": SOURCE_HOST,
            "path": SOURCE_PATH,
            "query": {"limit": "250"},
            "accept": "application/json",
            "accept_encoding": "identity",
            "authorization_source": "explicit_bearer_argument_only",
        },
        "provider_claim": {
            "documentation_url": (
                "https://massive.com/docs/rest/options/snapshots/option-chain-snapshot"
            ),
            "reviewed_at": "2026-08-10",
            "open_interest_basis": "end_of_last_trading_day",
            "classification": "qualitative_only",
            "claim_authenticated_by_response": False,
            "measurement_date_available": False,
            "publication_date_available": False,
            "publication_timestamp_available": False,
            "publication_sla_available": False,
        },
        "scope": {
            "source_availability_only": True,
            "future_only": True,
            "first_page_only": True,
            "calendar_inference_allowed": False,
            "expected_measurement_session_inference_allowed": False,
            "expected_measurement_date_inference_allowed": False,
            "permanent_contract_identity_resolution": False,
            "contract_multiplier_parsing": False,
            "gex_projection": False,
            "open_interest_value_projection": False,
            "open_interest_total_projection": False,
        },
    }


_SAFE_REQUEST_RECEIPT = {
    "method": "GET",
    "scheme": "https",
    "host": SOURCE_HOST,
    "path": SOURCE_PATH,
    "query": {"limit": "250"},
}
_TRANSPORT_POLICY = {
    "authorization": "explicit_bearer_transport_only_not_retained",
    "accept": "application/json",
    "accept_encoding": "identity",
    "trust_env": False,
    "redirects_allowed": False,
    "streaming": True,
    "max_entity_bytes": MAX_ENTITY_BYTES,
    "request_count": 1,
    "continuation_requests": 0,
}
_COMPLETENESS = {
    "page_complete": True,
    "continuation_followed": False,
    "intentionally_bounded": True,
    "chain_complete": False,
    "contract_universe_complete": False,
    "atomic_chain_snapshot_verified": False,
}
_TEMPORAL = {
    "source_availability_only": True,
    "available_at_basis": "response_body_completed_at",
    "event_time": None,
    "measurement_time": None,
    "provider_measurement_date_available": False,
    "provider_publication_date_available": False,
    "provider_publication_timestamp_available": False,
    "provider_publication_sla_available": False,
    "freshness": "unverifiable",
    "expected_measurement_session_inferred": False,
    "expected_measurement_date_inferred": False,
    "calendar_used": False,
}
_IDENTITY = {
    "status": "unresolved",
    "vendor_tickers_projected": False,
    "permanent_occ_identity_parsed": False,
    "permanent_contract_identity_assigned": False,
    "adjustment_status": "unresolved",
    "multiplier_parsed": False,
    "gex_computed": False,
}
_ROUTING = {
    "replay_eligible": False,
    "trusted_input_eligible": False,
    "public_api_eligible": False,
    "options_episode_eligible": False,
    "prophet_eligible": False,
}
_LIMITATIONS = {
    "future_only": True,
    "first_page_only": True,
    "source_availability_only": True,
    "open_interest_values_projected": False,
    "open_interest_total_computed": False,
    "vendor_tickers_projected": False,
    "raw_entity_body_present_in_bundle": True,
    "raw_entity_body_publicly_exposed": False,
    "contract_identity_unresolved": True,
    "freshness_unverifiable": True,
    "historical_backfill": False,
}
_QUALITY = {
    "status": "degraded",
    "flags": [
        "first_page_intentionally_bounded",
        "chain_incomplete",
        "contract_identity_unresolved",
        "freshness_unverifiable",
    ],
    "imputed": False,
    "training_eligible": False,
    "promotion_eligible": False,
}


class MarketMemoryOptionOiObservationError(ValueError):
    """The option-OI probe or its source-only projection is inadmissible."""


@dataclass(frozen=True)
class HttpResponse:
    """Exact raw HTTP boundary returned by an injected transport."""

    status: int
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes
    response_body_completed_at: str


@dataclass(frozen=True)
class FetchedOptionOiResponse:
    """Detached exact entity body plus only the selected safe HTTP metadata."""

    status: int
    url: str
    selected_headers: tuple[tuple[str, str], ...]
    body: bytes
    response_body_completed_at: str

    def detached(self) -> FetchedOptionOiResponse:
        return copy.deepcopy(self)


@dataclass(frozen=True)
class PinnedOptionOiSources:
    """Exact source-config and entitlement bodies from one repository tip."""

    pinned_commit: str
    source_config_body: bytes
    license_record_body: bytes
    git_blob_oids: tuple[tuple[str, str], ...]

    def detached(self) -> PinnedOptionOiSources:
        return copy.deepcopy(self)


@dataclass(frozen=True)
class PinnedOptionOiInputs:
    """One exact fetched page and its reviewed Git-owned source references."""

    fetched_response: FetchedOptionOiResponse
    pinned_sources: PinnedOptionOiSources

    def detached(self) -> PinnedOptionOiInputs:
        return copy.deepcopy(self)


@dataclass(frozen=True)
class OptionOiObservationBundle:
    """Raw detached evidence plus canonical probe and source-object bytes."""

    pinned_inputs: PinnedOptionOiInputs
    probe_receipt: dict[str, Any]
    probe_receipt_bytes: bytes
    source_observation: dict[str, Any]
    source_observation_bytes: bytes

    def detached(self) -> OptionOiObservationBundle:
        return copy.deepcopy(self)


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
        raise MarketMemoryOptionOiObservationError(
            "option-OI projection must be finite canonical JSON"
        ) from exc


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            # Never echo a decoded key. A hostile response can spell the bearer
            # token with JSON escapes and otherwise smuggle it into a traceback.
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON token {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number {value}")
    return parsed


def _parse_bounded_int(value: str) -> int:
    digits = value.removeprefix("-")
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise ValueError("JSON integer exceeds the frozen digit bound")
    return int(value)


def _validate_json_shape(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise MarketMemoryOptionOiObservationError(
                "option-OI JSON exceeds the frozen node bound"
            )
        if depth > MAX_JSON_DEPTH:
            raise MarketMemoryOptionOiObservationError(
                "option-OI JSON exceeds the frozen depth bound"
            )
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)


def _strict_json_object(body: bytes, *, label: str) -> dict[str, Any]:
    if type(body) is not bytes or not 1 <= len(body) <= MAX_ENTITY_BYTES:
        raise MarketMemoryOptionOiObservationError(
            f"{label} must be exact bounded immutable bytes"
        )
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
            parse_float=_parse_finite_float,
            parse_int=_parse_bounded_int,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        OverflowError,
        RecursionError,
    ):
        raise MarketMemoryOptionOiObservationError(
            f"{label} must be strict finite UTF-8 JSON"
        ) from None
    _validate_json_shape(value)
    if type(value) is not dict:
        raise MarketMemoryOptionOiObservationError(f"{label} must be a JSON object")
    return value


def _validated_timestamp(value: object) -> str:
    if type(value) is not str or _UTC_TIMESTAMP.fullmatch(value) is None:
        raise MarketMemoryOptionOiObservationError(
            "response_body_completed_at must be canonical UTC microseconds"
        )
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise MarketMemoryOptionOiObservationError(
            "response_body_completed_at is not a real UTC timestamp"
        ) from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise MarketMemoryOptionOiObservationError(
            "response_body_completed_at is not canonical"
        )
    return value


def _credential_needles(bearer_token: str | None) -> tuple[bytes, ...]:
    if bearer_token is None:
        return ()
    raw = bearer_token.encode("ascii")
    values = {
        raw,
        b"Bearer " + raw,
        quote(bearer_token, safe="").encode("ascii"),
        quote_plus(bearer_token, safe="").encode("ascii"),
        base64.b64encode(raw),
        base64.urlsafe_b64encode(raw),
        base64.b64encode(raw).rstrip(b"="),
        base64.urlsafe_b64encode(raw).rstrip(b"="),
    }
    return tuple(sorted(values, key=lambda item: (len(item), item), reverse=True))


def _validate_bearer_token(value: object) -> str:
    if type(value) is not str or not 8 <= len(value) <= 4096:
        raise MarketMemoryOptionOiObservationError(
            "bearer token must be an explicit bounded ASCII string"
        )
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise MarketMemoryOptionOiObservationError(
            "bearer token must be an explicit bounded ASCII string"
        ) from exc
    if any(byte < 0x21 or byte > 0x7E for byte in encoded):
        raise MarketMemoryOptionOiObservationError(
            "bearer token contains whitespace or control bytes"
        )
    return value


def _reject_credential_material(
    value: bytes | str,
    *,
    label: str,
    bearer_token: str | None = None,
    inspect_json_keys: bool = False,
) -> None:
    body = value.encode("utf-8") if type(value) is str else value
    if type(body) is not bytes:
        raise MarketMemoryOptionOiObservationError(f"{label} is not byte-safe")
    lowered = body.lower()
    if b"bearer " in lowered:
        raise MarketMemoryOptionOiObservationError(
            f"{label} contains bearer credential material"
        )
    if inspect_json_keys and _CREDENTIAL_JSON_KEY.search(body) is not None:
        raise MarketMemoryOptionOiObservationError(
            f"{label} contains credential-bearing JSON"
        )
    for needle in _credential_needles(bearer_token):
        if needle and needle in body:
            raise MarketMemoryOptionOiObservationError(
                f"{label} contains supplied credential bytes"
            )


def _reject_decoded_json_credentials(
    value: object,
    *,
    bearer_token: str | None,
) -> None:
    """Reject secrets after JSON and percent decoding, not only raw-byte scans."""

    stack = [value]
    while stack:
        item = stack.pop()
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise MarketMemoryOptionOiObservationError(
                        "response body contains a non-string JSON key"
                    )
                if _CREDENTIAL_JSON_KEY_NAME.fullmatch(key) is not None:
                    raise MarketMemoryOptionOiObservationError(
                        "response body contains credential-bearing JSON"
                    )
                stack.append(key)
                stack.append(child)
        elif type(item) is list:
            stack.extend(item)
        elif type(item) is str:
            decoded_values = {item}
            frontier = {item}
            for _ in range(4):
                expanded = {
                    decoded
                    for candidate in frontier
                    for decoded in (unquote(candidate), unquote_plus(candidate))
                }
                expanded -= decoded_values
                if not expanded:
                    break
                decoded_values.update(expanded)
                frontier = expanded
            for decoded in decoded_values:
                _reject_credential_material(
                    decoded,
                    label="decoded response JSON",
                    bearer_token=bearer_token,
                )


def _canonical_source_url(value: object) -> str:
    if type(value) is not str or value != SOURCE_URL:
        raise MarketMemoryOptionOiObservationError(
            "option-OI response did not remain on the exact request URL"
        )
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != SOURCE_HOST
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != SOURCE_PATH
        or parsed.query != SOURCE_QUERY
        or parsed.fragment
    ):
        raise MarketMemoryOptionOiObservationError(
            "option-OI request violates the frozen host/path/query contract"
        )
    return value


def _raw_header_map(
    headers: object,
    *,
    bearer_token: str | None,
) -> dict[str, str]:
    if type(headers) is not tuple:
        raise MarketMemoryOptionOiObservationError(
            "response headers must be exact name/value pairs"
        )
    result: dict[str, str] = {}
    for item in headers:
        if type(item) is not tuple or len(item) != 2:
            raise MarketMemoryOptionOiObservationError(
                "response headers must be exact name/value pairs"
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
            raise MarketMemoryOptionOiObservationError(
                "response contains a malformed HTTP header"
            )
        normalized = name.lower()
        if normalized in result:
            raise MarketMemoryOptionOiObservationError(
                "response contains duplicate HTTP headers"
            )
        _reject_credential_material(
            name,
            label="response header name",
            bearer_token=bearer_token,
        )
        _reject_credential_material(
            value,
            label="response header value",
            bearer_token=bearer_token,
        )
        if normalized in _FORBIDDEN_RESPONSE_HEADERS:
            raise MarketMemoryOptionOiObservationError(
                "response contains credential-bearing HTTP metadata"
            )
        result[normalized] = value
    if "content-encoding" in result:
        raise MarketMemoryOptionOiObservationError(
            "compressed option-OI responses are forbidden"
        )
    if "location" in result or "content-range" in result:
        raise MarketMemoryOptionOiObservationError(
            "redirect and partial option-OI responses are forbidden"
        )
    return result


def _selected_safe_headers(
    headers: object,
    *,
    body_length: int,
    bearer_token: str | None,
) -> tuple[tuple[str, str], ...]:
    parsed = _raw_header_map(headers, bearer_token=bearer_token)
    if parsed.get("content-type") != "application/json":
        raise MarketMemoryOptionOiObservationError(
            "option-OI response Content-Type is not application/json"
        )
    if "content-length" in parsed:
        raw_length = parsed["content-length"]
        if _CONTENT_LENGTH.fullmatch(raw_length) is None:
            raise MarketMemoryOptionOiObservationError(
                "option-OI Content-Length is not canonical"
            )
        if int(raw_length) != body_length:
            raise MarketMemoryOptionOiObservationError(
                "option-OI body differs from Content-Length"
            )
    return tuple(
        (name, parsed[name]) for name in _SELECTED_RESPONSE_HEADERS if name in parsed
    )


def _bounded_raw_read(raw: object, *, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        try:
            chunk = raw.read(min(65_536, limit + 1 - total))
        except (OSError, ValueError) as exc:
            raise MarketMemoryOptionOiObservationError(
                "option-OI response body could not be read exactly"
            ) from exc
        if type(chunk) is not bytes:
            raise MarketMemoryOptionOiObservationError(
                "option-OI transport returned non-byte body data"
            )
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise MarketMemoryOptionOiObservationError(
                "option-OI response exceeded the 4 MiB entity bound"
            )
    return b"".join(chunks)


def _default_fetcher(
    method: str,
    url: str,
    headers: Mapping[str, str],
) -> HttpResponse:
    """Perform one environment-independent streamed request.

    The caller-supplied bearer value is already in ``headers``.  This adapter
    reads no environment variable, credential file, netrc entry, cookie jar, or
    ambient proxy configuration; ``Session.trust_env`` is disabled before the
    request is prepared.
    """

    response: Any | None = None
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
            body = _bounded_raw_read(response.raw, limit=MAX_ENTITY_BYTES)
            completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            return HttpResponse(
                status=response.status_code,
                url=response.url,
                headers=tuple(response.raw.headers.items()),
                body=body,
                response_body_completed_at=completed_at,
            )
    except MarketMemoryOptionOiObservationError:
        raise
    except (OSError, requests.RequestException):
        raise MarketMemoryOptionOiObservationError(
            "explicit-credential option-OI request failed"
        ) from None


Fetcher = Callable[[str, str, Mapping[str, str]], HttpResponse]


def fetch_current_spy_option_oi_response(
    *,
    bearer_token: str,
    fetcher: Fetcher | None = None,
) -> FetchedOptionOiResponse:
    """Fetch exactly the first bounded SPY chain page and discard the token."""

    token = _validate_bearer_token(bearer_token)
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Authorization": f"Bearer {token}",
        "User-Agent": "MastermindX-MarketMemory-OptionOI/1.0",
    }
    transport = _default_fetcher if fetcher is None else fetcher
    try:
        response = transport("GET", SOURCE_URL, headers)
    except MarketMemoryOptionOiObservationError:
        raise
    except Exception:  # noqa: BLE001 - sanitize arbitrary injected transports
        raise MarketMemoryOptionOiObservationError(
            "explicit-credential option-OI request failed"
        ) from None
    if type(response) is not HttpResponse:
        raise MarketMemoryOptionOiObservationError(
            "option-OI fetcher must return the exact HttpResponse boundary"
        )
    if type(response.status) is not int or response.status != 200:
        raise MarketMemoryOptionOiObservationError(
            "option-OI source did not return HTTP 200"
        )
    _canonical_source_url(response.url)
    if (
        type(response.body) is not bytes
        or not 1 <= len(response.body) <= MAX_ENTITY_BYTES
    ):
        raise MarketMemoryOptionOiObservationError(
            "option-OI body must be exact nonempty bytes within 4 MiB"
        )
    _reject_credential_material(
        response.url,
        label="response URL",
        bearer_token=token,
    )
    _reject_credential_material(
        response.body,
        label="response body",
        bearer_token=token,
        inspect_json_keys=True,
    )
    parsed_body = _strict_json_object(response.body, label="option-OI response body")
    _reject_decoded_json_credentials(parsed_body, bearer_token=token)
    selected_headers = _selected_safe_headers(
        response.headers,
        body_length=len(response.body),
        bearer_token=token,
    )
    completed_at = _validated_timestamp(response.response_body_completed_at)
    return FetchedOptionOiResponse(
        status=200,
        url=SOURCE_URL,
        selected_headers=selected_headers,
        body=bytes(response.body),
        response_body_completed_at=completed_at,
    )


def _git(root: Path, *args: str, text: bool = False) -> bytes | str:
    git_env = {
        key: value
        for key, value in _process_environment.items()
        if not key.startswith("GIT_")
    }
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={root}",
                "-C",
                str(root),
                *args,
            ],
            check=True,
            capture_output=True,
            text=text,
            timeout=30,
            env=git_env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MarketMemoryOptionOiObservationError(
            "cannot bind option-OI intake to Git"
        ) from exc
    return result.stdout


def _safe_stable_read(path: Path, *, role: str) -> bytes:
    try:
        path_before = path.lstat()
    except OSError as exc:
        raise MarketMemoryOptionOiObservationError(f"{role} is unavailable") from exc
    if stat.S_ISLNK(path_before.st_mode) or not stat.S_ISREG(path_before.st_mode):
        raise MarketMemoryOptionOiObservationError(
            f"{role} must be a regular non-symlink"
        )
    limit = _GIT_SOURCE_LIMITS[role]
    if not 1 <= path_before.st_size <= limit:
        raise MarketMemoryOptionOiObservationError(
            f"{role} is empty or exceeds its byte bound"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MarketMemoryOptionOiObservationError(
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
        raise MarketMemoryOptionOiObservationError(
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
        raise MarketMemoryOptionOiObservationError(
            f"{role} changed during its stable read"
        )
    return body


def _full_head_commit(root: Path) -> str:
    value = str(_git(root, "rev-parse", "--verify", "HEAD^{commit}", text=True)).strip()
    if _COMMIT.fullmatch(value) is None:
        raise MarketMemoryOptionOiObservationError("repository HEAD is malformed")
    return value


def read_pinned_option_oi_sources(
    repository_root: str | Path,
    *,
    pinned_commit: str,
) -> PinnedOptionOiSources:
    """Read both reviewed source bodies and prove exact current-HEAD ownership."""

    if type(pinned_commit) is not str or _COMMIT.fullmatch(pinned_commit) is None:
        raise MarketMemoryOptionOiObservationError("pinned_commit is malformed")
    try:
        root = Path(repository_root).resolve(strict=True)
    except OSError as exc:
        raise MarketMemoryOptionOiObservationError(
            "repository root is unavailable"
        ) from exc
    if not root.is_dir() or _full_head_commit(root) != pinned_commit:
        raise MarketMemoryOptionOiObservationError(
            "pinned_commit is not the current repository tip"
        )

    bodies: dict[str, bytes] = {}
    blob_oids: list[tuple[str, str]] = []
    for role in _GIT_SOURCE_ROLES:
        repo_path = _GIT_SOURCE_PATHS[role]
        body = _safe_stable_read(root / repo_path, role=role)
        tracked = _git(root, "show", f"{pinned_commit}:{repo_path}")
        if type(tracked) is not bytes or body != tracked:
            raise MarketMemoryOptionOiObservationError(
                f"{role} bytes differ from the pinned Git object"
            )
        object_type = str(
            _git(root, "cat-file", "-t", f"{pinned_commit}:{repo_path}", text=True)
        ).strip()
        blob_oid = str(
            _git(root, "rev-parse", f"{pinned_commit}:{repo_path}", text=True)
        ).strip()
        if object_type != "blob" or _GIT_OID.fullmatch(blob_oid) is None:
            raise MarketMemoryOptionOiObservationError(
                f"{role} is not one canonical Git blob"
            )
        bodies[role] = body
        blob_oids.append((role, blob_oid))

    if _full_head_commit(root) != pinned_commit:
        raise MarketMemoryOptionOiObservationError(
            "repository HEAD changed during option-OI intake"
        )
    return PinnedOptionOiSources(
        pinned_commit=pinned_commit,
        source_config_body=bodies["option_oi_source_config"],
        license_record_body=bodies["massive_entitlement_record"],
        git_blob_oids=tuple(blob_oids),
    )


def _git_blob_oid(body: bytes, *, hexadecimal_length: int) -> str:
    framed = f"blob {len(body)}\0".encode("ascii") + body
    if hexadecimal_length == 40:
        return hashlib.sha1(framed).hexdigest()
    if hexadecimal_length == 64:
        return hashlib.sha256(framed).hexdigest()
    raise MarketMemoryOptionOiObservationError("unsupported Git object format")


def _validated_pinned_sources(
    value: PinnedOptionOiSources,
) -> PinnedOptionOiSources:
    if type(value) is not PinnedOptionOiSources:
        raise MarketMemoryOptionOiObservationError(
            "option-OI Git sources must use PinnedOptionOiSources"
        )
    if (
        type(value.pinned_commit) is not str
        or _COMMIT.fullmatch(value.pinned_commit) is None
    ):
        raise MarketMemoryOptionOiObservationError("pinned Git commit is malformed")
    bodies = {
        "option_oi_source_config": value.source_config_body,
        "massive_entitlement_record": value.license_record_body,
    }
    for role, body in bodies.items():
        if type(body) is not bytes or not body or len(body) > _GIT_SOURCE_LIMITS[role]:
            raise MarketMemoryOptionOiObservationError(
                f"{role} must be exact bounded immutable bytes"
            )
    if (
        type(value.git_blob_oids) is not tuple
        or any(
            type(item) is not tuple or len(item) != 2 for item in value.git_blob_oids
        )
        or tuple(item[0] for item in value.git_blob_oids) != _GIT_SOURCE_ROLES
    ):
        raise MarketMemoryOptionOiObservationError(
            "Git blob references are incomplete or out of order"
        )
    for role, oid in value.git_blob_oids:
        if type(oid) is not str or _GIT_OID.fullmatch(oid) is None:
            raise MarketMemoryOptionOiObservationError(
                "Git blob reference is malformed"
            )
        if oid != _git_blob_oid(bodies[role], hexadecimal_length=len(oid)):
            raise MarketMemoryOptionOiObservationError(
                f"{role} Git blob ID does not bind its exact bytes"
            )
    if _sha256(value.source_config_body) != _OPTION_OI_SOURCE_CONFIG_SHA256_V1:
        raise MarketMemoryOptionOiObservationError(
            "option-OI source config does not match the frozen v1 SHA-256"
        )
    if (
        _strict_json_object(value.source_config_body, label="option-OI source config")
        != _source_config_v1()
    ):
        raise MarketMemoryOptionOiObservationError(
            "option-OI source config does not match the frozen v1 literal"
        )
    if _sha256(value.license_record_body) != _MASSIVE_ENTITLEMENT_SHA256_V1:
        raise MarketMemoryOptionOiObservationError(
            "Massive entitlement record does not match the reviewed v1 SHA-256"
        )
    try:
        value.license_record_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MarketMemoryOptionOiObservationError(
            "Massive entitlement record is not UTF-8"
        ) from exc
    return value.detached()


def _validated_fetched_response(
    value: FetchedOptionOiResponse,
) -> FetchedOptionOiResponse:
    if type(value) is not FetchedOptionOiResponse:
        raise MarketMemoryOptionOiObservationError(
            "remote source must use FetchedOptionOiResponse"
        )
    if type(value.status) is not int or value.status != 200:
        raise MarketMemoryOptionOiObservationError(
            "stored option-OI response status is not HTTP 200"
        )
    _canonical_source_url(value.url)
    if type(value.body) is not bytes or not 1 <= len(value.body) <= MAX_ENTITY_BYTES:
        raise MarketMemoryOptionOiObservationError(
            "stored option-OI body must be exact bounded immutable bytes"
        )
    _reject_credential_material(
        value.body,
        label="stored option-OI body",
        inspect_json_keys=True,
    )
    selected = _selected_safe_headers(
        value.selected_headers,
        body_length=len(value.body),
        bearer_token=None,
    )
    if selected != value.selected_headers:
        raise MarketMemoryOptionOiObservationError(
            "stored option-OI headers are not the selected canonical safe subset"
        )
    _validated_timestamp(value.response_body_completed_at)
    return value.detached()


def _validated_next_url(payload: Mapping[str, Any]) -> bool:
    if "next_url" not in payload or payload["next_url"] is None:
        return False
    value = payload["next_url"]
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > MAX_NEXT_URL_BYTES
    ):
        raise MarketMemoryOptionOiObservationError(
            "next_url must be a bounded canonical URL when present"
        )
    _reject_credential_material(value, label="next_url")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != SOURCE_HOST
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != SOURCE_PATH
        or not parsed.query
        or parsed.fragment
    ):
        raise MarketMemoryOptionOiObservationError(
            "next_url violates the provider continuation origin/path boundary"
        )
    try:
        pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=3,
        )
    except ValueError as exc:
        raise MarketMemoryOptionOiObservationError(
            "next_url query is malformed"
        ) from exc
    if not pairs or len({key for key, _ in pairs}) != len(pairs):
        raise MarketMemoryOptionOiObservationError(
            "next_url query fields are empty or duplicated"
        )
    for key, item in pairs:
        normalized = key.lower().replace("-", "_")
        if normalized not in {"cursor", "limit"} or not item:
            raise MarketMemoryOptionOiObservationError(
                "next_url contains a non-continuation query field"
            )
        _reject_credential_material(item, label="next_url query value")
        if normalized == "limit" and item != "250":
            raise MarketMemoryOptionOiObservationError(
                "next_url changes the frozen first-page limit"
            )
    if not any(key.lower() == "cursor" for key, _ in pairs):
        raise MarketMemoryOptionOiObservationError("next_url does not contain a cursor")
    return True


def _validated_page(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") != "OK" or type(payload.get("status")) is not str:
        raise MarketMemoryOptionOiObservationError(
            "option-OI provider payload status is not OK"
        )
    results = payload.get("results")
    if type(results) is not list or not 1 <= len(results) <= MAX_RESULTS:
        raise MarketMemoryOptionOiObservationError(
            "option-OI results must contain between 1 and 250 records"
        )

    tickers: set[str] = set()
    valid = 0
    null = 0
    absent = 0
    for index, result in enumerate(results):
        if type(result) is not dict:
            raise MarketMemoryOptionOiObservationError(
                f"option-OI result {index} must be an object"
            )
        details = result.get("details")
        if type(details) is not dict:
            raise MarketMemoryOptionOiObservationError(
                f"option-OI result {index} lacks vendor details"
            )
        ticker = details.get("ticker")
        if (
            type(ticker) is not str
            or not 1 <= len(ticker.encode("utf-8")) <= MAX_VENDOR_TICKER_BYTES
            or _VENDOR_TICKER.fullmatch(ticker) is None
            or not ticker.startswith("O:SPY")
        ):
            raise MarketMemoryOptionOiObservationError(
                f"option-OI result {index} is not a SPY vendor ticker"
            )
        if ticker in tickers:
            raise MarketMemoryOptionOiObservationError(
                "option-OI results contain duplicate vendor tickers"
            )
        tickers.add(ticker)

        if "open_interest" not in result:
            absent += 1
        elif result["open_interest"] is None:
            null += 1
        elif type(result["open_interest"]) is int and result["open_interest"] >= 0:
            valid += 1
        else:
            raise MarketMemoryOptionOiObservationError(
                f"option-OI result {index} has invalid open_interest"
            )
    if valid < 1:
        raise MarketMemoryOptionOiObservationError(
            "option-OI page contains no valid nonnegative integer OI"
        )
    next_url_present = _validated_next_url(payload)
    return {
        "results_count": len(results),
        "unique_vendor_ticker_count": len(tickers),
        "oi_presence_counts": {
            "valid_nonnegative_integer": valid,
            "null": null,
            "absent": absent,
        },
        "next_url_present": next_url_present,
    }


def _git_artifact_refs(
    sources: PinnedOptionOiSources,
) -> dict[str, dict[str, Any]]:
    bodies = {
        "option_oi_source_config": sources.source_config_body,
        "massive_entitlement_record": sources.license_record_body,
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


def _probe_receipt_id(core: Mapping[str, Any]) -> str:
    return "mmoptionoiprobe_" + _sha256(_canonical_bytes(dict(core)))


def _source_observation_id(core: Mapping[str, Any]) -> str:
    return "mmoptionoisrc_" + _sha256(_canonical_bytes(dict(core)))


def project_current_spy_option_oi_observation(
    inputs: PinnedOptionOiInputs,
) -> OptionOiObservationBundle:
    """Purely project source availability from exact remote and Git evidence."""

    if type(inputs) is not PinnedOptionOiInputs:
        raise MarketMemoryOptionOiObservationError(
            "option-OI inputs must use PinnedOptionOiInputs"
        )
    fetched = _validated_fetched_response(inputs.fetched_response)
    sources = _validated_pinned_sources(inputs.pinned_sources)
    payload = _strict_json_object(fetched.body, label="option-OI response body")
    _reject_decoded_json_credentials(payload, bearer_token=None)
    page_observation = _validated_page(payload)

    selected_headers = {name: value for name, value in fetched.selected_headers}
    response_receipt = {
        "status_code": 200,
        "final_url_matches_request": True,
        "selected_headers": selected_headers,
        "entity_body": {
            "sha256": _sha256(fetched.body),
            "bytes": len(fetched.body),
        },
        "response_body_completed_at": fetched.response_body_completed_at,
    }
    pagination_receipt = {
        "next_url_present": page_observation["next_url_present"],
        "next_url_projected": False,
        **copy.deepcopy(_COMPLETENESS),
    }
    probe_core = {
        "profile": PROFILE,
        "request": copy.deepcopy(_SAFE_REQUEST_RECEIPT),
        "transport_policy": copy.deepcopy(_TRANSPORT_POLICY),
        "response": response_receipt,
        "pagination": pagination_receipt,
    }
    probe_receipt = {
        "schema": PROBE_RECEIPT_SCHEMA,
        "probe_receipt_id": _probe_receipt_id(probe_core),
        **probe_core,
    }
    probe_receipt_bytes = _canonical_bytes(probe_receipt)

    git_sources = _git_artifact_refs(sources)
    source_core = {
        "profile": PROFILE,
        "probe_receipt_id": probe_receipt["probe_receipt_id"],
        "available_at": fetched.response_body_completed_at,
        "git_source_sha256": {
            role: git_sources[role]["sha256"] for role in _GIT_SOURCE_ROLES
        },
        "page_observation": page_observation,
        "temporal": copy.deepcopy(_TEMPORAL),
        "identity": copy.deepcopy(_IDENTITY),
        "completeness": copy.deepcopy(_COMPLETENESS),
    }
    config = _source_config_v1()
    source_observation = {
        "schema": SOURCE_OBSERVATION_SCHEMA,
        "source_observation_id": _source_observation_id(source_core),
        "profile": PROFILE,
        "probe_receipt_id": probe_receipt["probe_receipt_id"],
        "available_at": fetched.response_body_completed_at,
        "provider_claim": copy.deepcopy(config["provider_claim"]),
        "page_observation": page_observation,
        "temporal": copy.deepcopy(_TEMPORAL),
        "identity": copy.deepcopy(_IDENTITY),
        "completeness": copy.deepcopy(_COMPLETENESS),
        "git_sources": git_sources,
        "quality": copy.deepcopy(_QUALITY),
        "limitations": copy.deepcopy(_LIMITATIONS),
        "routing": copy.deepcopy(_ROUTING),
        "authority": _authority_v1(),
    }
    source_observation_bytes = _canonical_bytes(source_observation)
    for label, body in (
        ("probe receipt", probe_receipt_bytes),
        ("source observation", source_observation_bytes),
    ):
        _reject_credential_material(body, label=label)

    return OptionOiObservationBundle(
        pinned_inputs=PinnedOptionOiInputs(
            fetched_response=fetched,
            pinned_sources=sources,
        ),
        probe_receipt=probe_receipt,
        probe_receipt_bytes=probe_receipt_bytes,
        source_observation=source_observation,
        source_observation_bytes=source_observation_bytes,
    )


def build_current_spy_option_oi_observation(
    repository_root: str | Path,
    *,
    pinned_commit: str,
    bearer_token: str,
    fetcher: Fetcher | None = None,
) -> OptionOiObservationBundle:
    """Fetch one page, pin reviewed Git inputs, and build the detached bundle."""

    sources = read_pinned_option_oi_sources(
        repository_root,
        pinned_commit=pinned_commit,
    )
    fetched = fetch_current_spy_option_oi_response(
        bearer_token=bearer_token,
        fetcher=fetcher,
    )
    bundle = project_current_spy_option_oi_observation(
        PinnedOptionOiInputs(
            fetched_response=fetched,
            pinned_sources=sources,
        )
    )
    for label, body in (
        ("probe receipt", bundle.probe_receipt_bytes),
        ("source observation", bundle.source_observation_bytes),
    ):
        _reject_credential_material(
            body,
            label=label,
            bearer_token=bearer_token,
        )
    return bundle


def validate_option_oi_observation_bundle(
    value: OptionOiObservationBundle,
) -> OptionOiObservationBundle:
    """Reproject exact detached evidence and reject any bundle tampering."""

    if type(value) is not OptionOiObservationBundle:
        raise MarketMemoryOptionOiObservationError(
            "option-OI observation must use the frozen bundle boundary"
        )
    if (
        type(value.probe_receipt) is not dict
        or type(value.source_observation) is not dict
    ):
        raise MarketMemoryOptionOiObservationError(
            "option-OI receipt and source observation must be dictionaries"
        )
    if (
        type(value.probe_receipt_bytes) is not bytes
        or type(value.source_observation_bytes) is not bytes
    ):
        raise MarketMemoryOptionOiObservationError(
            "option-OI canonical objects must use exact immutable bytes"
        )
    if value.probe_receipt_bytes != _canonical_bytes(value.probe_receipt):
        raise MarketMemoryOptionOiObservationError(
            "option-OI probe receipt bytes are noncanonical or tampered"
        )
    if value.source_observation_bytes != _canonical_bytes(value.source_observation):
        raise MarketMemoryOptionOiObservationError(
            "option-OI source observation bytes are noncanonical or tampered"
        )
    rebuilt = project_current_spy_option_oi_observation(value.pinned_inputs)
    if (
        value.probe_receipt != rebuilt.probe_receipt
        or value.probe_receipt_bytes != rebuilt.probe_receipt_bytes
        or value.source_observation != rebuilt.source_observation
        or value.source_observation_bytes != rebuilt.source_observation_bytes
    ):
        raise MarketMemoryOptionOiObservationError(
            "option-OI bundle does not reproduce from its exact raw evidence"
        )
    if _PROBE_ID.fullmatch(rebuilt.probe_receipt["probe_receipt_id"]) is None:
        raise MarketMemoryOptionOiObservationError("option-OI probe ID is malformed")
    if (
        _SOURCE_ID.fullmatch(rebuilt.source_observation["source_observation_id"])
        is None
    ):
        raise MarketMemoryOptionOiObservationError("option-OI source ID is malformed")
    return rebuilt.detached()


__all__ = [
    "MAX_ENTITY_BYTES",
    "MAX_RESULTS",
    "PROBE_RECEIPT_SCHEMA",
    "PROFILE",
    "SOURCE_HOST",
    "SOURCE_OBSERVATION_SCHEMA",
    "SOURCE_PATH",
    "SOURCE_QUERY",
    "SOURCE_URL",
    "FetchedOptionOiResponse",
    "Fetcher",
    "HttpResponse",
    "MarketMemoryOptionOiObservationError",
    "OptionOiObservationBundle",
    "PinnedOptionOiInputs",
    "PinnedOptionOiSources",
    "build_current_spy_option_oi_observation",
    "fetch_current_spy_option_oi_response",
    "project_current_spy_option_oi_observation",
    "read_pinned_option_oi_sources",
    "validate_option_oi_observation_bundle",
]
