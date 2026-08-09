"""API surface for the seasonality RESEARCH BROWSER — handlers only, unwired.

This module deliberately registers NOTHING.  There is no ``APIRouter``, no
dependency, no path decorator: router registration, auth, and entitlement wiring
are a separate late PR, and shipping the handler first means the schema can be
reviewed before anything can reach it.  Nothing here imports FastAPI, so the
thin seasonality CI runner can execute the whole surface.

What the handlers guarantee, because a research-tier browser that is sloppy about
these becomes indistinguishable from a screener:

* ``asof`` is EXPLICIT and required — a browser that silently means "now" has no
  reproducible answer;
* pagination is deterministic over a stable total order with a unique tiebreaker,
  so page 2 of an unchanged set never repeats or skips a row.  The exact-multiple
  page size (where trailing-page bugs live) is pinned in the test suite;
* payloads are bounded by an enforced maximum page size — a request for more is
  refused, never quietly clamped;
* model and data versions and the source entitlements ride on EVERY response —
  every reachable status, not the happy path plus one 400;
* private data is ``no-store``, a public body still carries ``Vary`` so a shared
  cache cannot serve one consumer's response to another, and NO refusal is ever
  shared-cacheable;
* stale and partial states are explicit response fields, and UNKNOWN freshness is
  printed as unknown rather than as fresh.  A partial answer with no stated
  reason is a server error here, not a short list;
* the rate limiter is a HOOK parameter, not a live limiter this module owns — and
  every way an injected hook or row provider can misbehave (raising, returning
  the wrong shape, handing back an illegal ``Retry-After``) becomes a stated
  response rather than a traceback;
* the API body and the server-rendered view share one builder AND one envelope,
  so the two surfaces cannot drift into different semantics on a refusal either.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from engine.seasonality import screener

API_SCHEMA = "seasonality.research_browser.api.v1"

#: Version of the calendar-clock model behind the rows. ``v0`` on purpose: there
#: is no graded out-of-sample epoch, so there is no model to version yet.
MODEL_VERSION = "seasonality-research-browser-v0-uncalibrated"
DATA_CONTRACT_VERSIONS = {
    "result_set": screener.RESEARCH_BROWSER_SCHEMA,
    "row": screener.RESEARCH_ROW_SCHEMA,
    "calendar_entity": "biopharma_seasonality.entity.v1",
}

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

#: An explicit asof is still a BOUNDED one. A far-future date is not a research
#: question anyone can answer, and `date(1, 1, 1)` is a parsing accident, not a
#: request. Both used to be served with a 200.
MIN_ASOF = date(1990, 1, 1)

#: RFC 9110 `delta-seconds`: a non-negative integer. A limiter handing back `-5`
#: or `1e30` produced a header proxies and clients reject or ignore.
MAX_RETRY_AFTER_S = 3600
DEFAULT_RETRY_AFTER_S = 60

PRIVATE_CACHE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Vary": "Authorization",
}
#: `Vary: Authorization` rides on the PUBLIC headers too. Without it a shared
#: cache keys a licensed, per-consumer body on the URL alone and serves one
#: caller's response — including its `consumer` identity and its entitlement
#: block — to every other caller for the whole max-age.
PUBLIC_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=60",
    "Vary": "Authorization",
}

#: What the rows rest on and what a reader is allowed to do with it. Rides on
#: every response so an entitlement question never needs a second call.
DEFAULT_SOURCE_ENTITLEMENTS = (
    {
        "source": "end_of_day_price_history",
        "entitlement": "licensed_internal_use",
        "redistribution": "aggregate_statistics_only",
    },
    {
        "source": "security_identity_snapshots",
        "entitlement": "licensed_internal_use",
        "redistribution": "not_redistributable",
    },
)

# Error codes are stable strings — the UI branches on them, not on prose.
ERR_ASOF_REQUIRED = "asof_required"
ERR_ASOF_INVALID = "asof_invalid"
ERR_PAGE_INVALID = "page_invalid"
ERR_PAGE_SIZE_INVALID = "page_size_invalid"
ERR_PAGE_SIZE_EXCEEDS_MAX = "page_size_exceeds_max"
ERR_SORT_BY_NOT_ALLOWED = "sort_by_not_allowed"
ERR_MIXED_ESTIMATE_AXIS = "mixed_estimate_axis"
ERR_CONSUMER_REFUSED = "consumer_refused"
ERR_RATE_LIMITED = "rate_limited"
ERR_PARTIAL_WITHOUT_REASON = "partial_without_reason"
ERR_ROWS_NOT_TOTALLY_ORDERED = "rows_not_totally_ordered"
ERR_ASOF_OUT_OF_RANGE = "asof_out_of_range"
ERR_UNKNOWN_PARAMETER = "unknown_parameter"
ERR_RATE_LIMIT_HOOK_FAILED = "rate_limit_hook_failed"
ERR_ROWS_PROVIDER_FAILED = "rows_provider_failed"
ERR_ROWS_PROVIDER_CONTRACT = "rows_provider_contract_violation"
ERR_RESULT_SET_REFUSED = "result_set_refused"


@dataclass(frozen=True)
class ApiResponse:
    """A transport-agnostic response. The caller adapts it to its framework."""

    status: int
    body: dict
    headers: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ViewModel:
    """The server-rendered view over the API body.

    ``result`` is the SAME payload the API returns — and so is everything else.
    The view used to hold ``result`` alone, so on any 4xx/5xx it handed the
    renderer ``None`` with no error code and, because the tier declaration lives
    in the envelope rather than inside ``result``, no ``tier`` or
    ``is_calibrated_screener`` either: 400, 403, 429 and 500 were
    indistinguishable to the UI, and a refusal page carried no tier disclosure at
    all.  ``error`` and ``envelope`` close that, so the two surfaces really are
    one schema rather than one field of it.
    """

    status: int
    result: dict | None
    error: dict | None = None
    envelope: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)


def _headers(*, private: bool, extra: Mapping[str, str] | None = None) -> dict:
    headers = dict(PRIVATE_CACHE_HEADERS) if private else dict(PUBLIC_CACHE_HEADERS)
    if extra:
        headers.update(extra)
    return headers


def _envelope(**extra) -> dict:
    """Fields that ride on EVERY response, success or failure."""
    # The tier declaration is read from the module at CALL time, so it is checked
    # at call time too: a reassigned `screener.TIER` must fail the request, never
    # upgrade the claim the envelope makes on every single response.
    screener.assert_research_tier_intact()
    payload = {
        "schema": API_SCHEMA,
        "tier": screener.TIER,
        "is_calibrated_screener": screener.IS_CALIBRATED_SCREENER,
        "not_calibrated_reason": screener.NOT_CALIBRATED_REASON,
        "model_version": MODEL_VERSION,
        "data_versions": dict(DATA_CONTRACT_VERSIONS),
        "source_entitlements": [dict(entry) for entry in DEFAULT_SOURCE_ENTITLEMENTS],
    }
    payload.update(extra)
    return payload


def _error(code: str, message: str, *, status: int, **extra) -> ApiResponse:
    # A refusal is NEVER shared-cacheable, whatever `private` the caller asked
    # for: a `public, max-age=60` on a 429 lets one consumer's rate-limit answer
    # be served to every other consumer for a minute.
    return ApiResponse(
        status=status,
        body=_envelope(error={"code": code, "message": message, **extra}, result=None),
        headers=_headers(private=True),
    )


def _coerce_asof(value: object) -> date:
    if isinstance(value, datetime):
        # `datetime` subclasses `date`, so an `isinstance(value, date)` check
        # passes it straight through and `isoformat()` then emits a time
        # component: two requests for the same trading day serialise differently
        # and take different rate-limit keys. An ISO STRING carrying a time is
        # already refused here, so a datetime object is refused the same way.
        raise ValueError(
            f"asof {value!r} is a datetime; a research browser is asof a calendar day, "
            "and a timestamp makes two reads of the same day disagree"
        )
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"asof {value!r} is neither a date nor an ISO date string")


def _paginate(total: int, *, page: int, page_size: int) -> dict:
    """Explicit pagination state — including the out-of-range page.

    A page past the end returns an EMPTY page that says so, rather than silently
    handing back the last page, which is how a reader ends up double-counting.
    """
    total_pages = (total + page_size - 1) // page_size if total else 0
    offset = (page - 1) * page_size
    return {
        "page": page,
        "page_size": page_size,
        "max_page_size": MAX_PAGE_SIZE,
        "offset": offset,
        "total_rows": total,
        "total_pages": total_pages,
        "has_more": offset + page_size < total,
        "next_page": page + 1 if offset + page_size < total else None,
        # `page > 1`, not `total > 0`: page 5 of an EMPTY set is as far past the
        # end as page 7 of a 12-row set, and reporting one True and the other
        # False gives a client two answers to one condition. Page 1 is never out
        # of range — an empty first page is an empty set, not an overshoot.
        "page_out_of_range": page > 1 and offset >= total,
    }


def _retry_after(verdict: Mapping | None) -> int:
    """A `Retry-After` that is always a legal RFC 9110 ``delta-seconds``."""
    raw = verdict.get("retry_after_s") if verdict else None
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_S
    if seconds < 1:
        return DEFAULT_RETRY_AFTER_S
    return min(seconds, MAX_RETRY_AFTER_S)


def _rows_provider_contract_error(provided: object) -> str | None:
    """Name the way the injected provider broke its contract, or ``None``.

    The provider is the one dependency this module does not own, so every shape
    it can return wrong — a bare list, a 3-tuple, a string where the provenance
    mapping goes, dicts where rows go — must become a stated 500 rather than an
    unpacking traceback.
    """
    if isinstance(provided, (str, bytes, Mapping)) or not isinstance(provided, Sequence):
        return (
            "rows_provider must return a (rows, provenance) pair; got "
            f"{type(provided).__name__}"
        )
    if len(provided) != 2:
        return f"rows_provider must return a (rows, provenance) pair; got {len(provided)} values"
    rows, provenance = provided
    if provenance is not None and not isinstance(provenance, Mapping):
        return f"rows_provider provenance must be a mapping; got {type(provenance).__name__}"
    if isinstance(rows, (str, bytes, Mapping)) or not isinstance(rows, Sequence):
        return f"rows_provider rows must be a sequence; got {type(rows).__name__}"
    for index, row in enumerate(rows):
        if not isinstance(row, screener.ResearchRow):
            return (
                f"rows_provider row {index} is a {type(row).__name__}, not a ResearchRow; "
                "the row invariants are what make a row servable"
            )
    return None


def build_research_browser_response(
    *,
    asof: object,
    consumer: str,
    rows_provider: Callable[[date], tuple[Sequence[screener.ResearchRow], Mapping]],
    universe: screener.UniverseDisclosure,
    multiplicity: Mapping,
    page: int = 1,
    page_size: int | None = None,
    sort_by: str | None = None,
    descending: bool = False,
    rate_limit_hook: Callable[[Mapping], Mapping] | None = None,
    private: bool = True,
) -> ApiResponse:
    """The single builder behind both the API handler and the server-rendered view."""
    if asof is None:
        return _error(
            ERR_ASOF_REQUIRED,
            "asof is required: a research browser with an implicit 'now' is not reproducible.",
            status=400,
        )
    try:
        asof_date = _coerce_asof(asof)
    except ValueError as exc:
        return _error(ERR_ASOF_INVALID, str(exc), status=400)

    today = date.today()
    if asof_date > today:
        return _error(
            ERR_ASOF_OUT_OF_RANGE,
            f"asof {asof_date.isoformat()} is in the future; there is no history to browse "
            "after today, and a research answer dated forward is not a research answer",
            status=400,
            min_asof=MIN_ASOF.isoformat(),
            max_asof=today.isoformat(),
        )
    if asof_date < MIN_ASOF:
        return _error(
            ERR_ASOF_OUT_OF_RANGE,
            f"asof {asof_date.isoformat()} is before {MIN_ASOF.isoformat()}, which is earlier "
            "than any panel behind this browser — that is a parsing accident, not a request",
            status=400,
            min_asof=MIN_ASOF.isoformat(),
            max_asof=today.isoformat(),
        )

    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        return _error(ERR_PAGE_INVALID, f"page must be an integer >= 1; got {page!r}", status=400)

    size = DEFAULT_PAGE_SIZE if page_size is None else page_size
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        return _error(
            ERR_PAGE_SIZE_INVALID, f"page_size must be an integer >= 1; got {page_size!r}", status=400
        )
    if size > MAX_PAGE_SIZE:
        return _error(
            ERR_PAGE_SIZE_EXCEEDS_MAX,
            f"page_size {size} exceeds the maximum {MAX_PAGE_SIZE}. The request is refused rather "
            "than clamped, so a caller never believes it received a full set.",
            status=400,
            max_page_size=MAX_PAGE_SIZE,
        )

    try:
        identity = screener.assert_consumer_permitted(consumer)
    except screener.MachineAuthorityRefused as exc:
        return _error(ERR_CONSUMER_REFUSED, str(exc), status=403, consumer=str(consumer))

    if rate_limit_hook is not None:
        try:
            verdict = rate_limit_hook(
                {"consumer": identity, "asof": asof_date.isoformat(), "page": page, "page_size": size}
            )
        except Exception as exc:  # noqa: BLE001 - a limiter is an injected dependency
            # Fail CLOSED and say so: a limiter that raises must not fall through
            # to an unlimited served page.
            return _error(
                ERR_RATE_LIMIT_HOOK_FAILED,
                f"the rate-limit hook raised {type(exc).__name__}: {exc}",
                status=500,
            )
        if not isinstance(verdict, Mapping) or not verdict.get("allowed"):
            # `verdict` is only read as a mapping AFTER it has been proved to be
            # one. The guard above used to detect a non-Mapping and the next line
            # then called `.get` on that same object, so the exact input the
            # check existed for was the one that crashed it.
            retry_after = _retry_after(verdict if isinstance(verdict, Mapping) else None)
            return ApiResponse(
                status=429,
                body=_envelope(
                    error={
                        "code": ERR_RATE_LIMITED,
                        "message": "rate limit reached for this consumer",
                        "retry_after_s": retry_after,
                    },
                    result=None,
                ),
                # Never `public`: a shared cache would hand one consumer's 429 to
                # everyone else for the whole max-age.
                headers=_headers(private=True, extra={"Retry-After": str(retry_after)}),
            )

    try:
        provided = rows_provider(asof_date)
    except Exception as exc:  # noqa: BLE001 - the provider is an injected dependency
        # A store outage is the single most likely production failure, and it used
        # to surface as a raw traceback with no envelope at all.
        return _error(
            ERR_ROWS_PROVIDER_FAILED,
            f"the row provider raised {type(exc).__name__}: {exc}",
            status=500,
        )
    contract_error = _rows_provider_contract_error(provided)
    if contract_error:
        return _error(ERR_ROWS_PROVIDER_CONTRACT, contract_error, status=500)
    rows, provenance = provided
    provenance = dict(provenance or {})
    partial = bool(provenance.get("partial"))
    partial_reason = provenance.get("partial_reason")
    if partial and not partial_reason:
        # A short list with no stated cause is silent truncation. Refuse it.
        return _error(
            ERR_PARTIAL_WITHOUT_REASON,
            "the row provider reported a partial answer without naming the cause; "
            "refusing to serve a silently truncated result set",
            status=500,
        )

    try:
        result = screener.build_result_set(
            asof=asof_date,
            rows=rows,
            consumer=identity,
            multiplicity=multiplicity,
            universe=universe,
            sort_by=sort_by,
            descending=descending,
        )
    except screener.SortKeyError as exc:
        return _error(
            ERR_SORT_BY_NOT_ALLOWED, str(exc), status=400, sortable_columns=list(screener.SORTABLE_COLUMNS)
        )
    except screener.MixedEstimateAxisError as exc:
        return _error(ERR_MIXED_ESTIMATE_AXIS, str(exc), status=400)
    except screener.DeterminismError as exc:
        return _error(ERR_ROWS_NOT_TOTALLY_ORDERED, str(exc), status=500)
    except screener.ScreenerError as exc:
        # The BASE class, last. `build_result_set` and every `ResearchRow`
        # invariant raise bare `ScreenerError` on ~a dozen paths (a bad universe
        # object, a forged multiplicity block, a calibrated row on this tier); an
        # uncaught one is a traceback with no envelope, which would defeat the
        # "every response declares the tier" property this module is built on.
        return _error(ERR_RESULT_SET_REFUSED, str(exc), status=500)

    ordered_rows = result["rows"]
    pagination = _paginate(len(ordered_rows), page=page, page_size=size)
    page_rows = ordered_rows[pagination["offset"] : pagination["offset"] + size]
    result = dict(result)
    result["rows"] = page_rows
    result["pagination"] = pagination
    result["counts"] = {**result["counts"], "rows_on_page": len(page_rows)}
    result["freshness"] = _freshness_state(provenance)
    result["completeness"] = {
        "partial": partial,
        "partial_reason": partial_reason,
        "omitted_row_count": provenance.get("omitted_row_count"),
        "omitted_symbols": list(provenance.get("omitted_symbols") or ()),
    }

    return ApiResponse(status=200, body=_envelope(result=result, error=None), headers=_headers(private=private))


#: What the freshness block says when the provider supplied no provenance at all.
UNKNOWN_FRESHNESS_REASON = "provider_supplied_no_freshness_provenance"


def _freshness_state(provenance: Mapping) -> dict:
    """Freshness, with UNKNOWN printed as unknown rather than as fresh.

    ``stale: False`` alongside ``artifact_asof: None`` was an affirmative
    freshness claim assembled out of an absence of information. A null is printed
    here instead, which is the compliant form.
    """
    known = "stale" in provenance or not _is_blank(provenance.get("artifact_asof"))
    if not known:
        return {
            "stale": None,
            "stale_reason": UNKNOWN_FRESHNESS_REASON,
            "artifact_asof": None,
            "known": False,
        }
    return {
        "stale": bool(provenance.get("stale")),
        "stale_reason": provenance.get("stale_reason"),
        "artifact_asof": provenance.get("artifact_asof"),
        "known": True,
    }


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


#: The parameters the handler accepts. An unrecognised one is a 400, not a crash.
_HANDLER_PARAMETERS = frozenset(
    inspect.signature(build_research_browser_response).parameters
)
_REQUIRED_HANDLER_PARAMETERS = ("consumer", "rows_provider", "universe", "multiplicity")


def _dispatch(kwargs: Mapping) -> ApiResponse:
    """Validate the caller's kwargs, then build.

    The handler is the documented entry point and used to splat ``**kwargs``
    straight into a signature with a required keyword-only ``asof`` and no
    catch-all — so the natural wiring (splat the query dict) produced a
    ``TypeError`` traceback for a MISSING ``asof``, and any unrecognised query
    parameter did the same. ``ERR_ASOF_REQUIRED`` was only reachable by passing
    the literal ``asof=None``.
    """
    unknown = sorted(set(kwargs) - _HANDLER_PARAMETERS)
    if unknown:
        return _error(
            ERR_UNKNOWN_PARAMETER,
            f"unrecognised parameter(s) {unknown}; this endpoint accepts "
            f"{sorted(_HANDLER_PARAMETERS)}",
            status=400,
            unknown_parameters=unknown,
            accepted_parameters=sorted(_HANDLER_PARAMETERS),
        )
    missing = [name for name in _REQUIRED_HANDLER_PARAMETERS if name not in kwargs]
    if missing:
        return _error(
            ERR_UNKNOWN_PARAMETER,
            f"missing required parameter(s) {missing}",
            status=400,
            missing_parameters=missing,
        )
    return build_research_browser_response(**{"asof": kwargs.get("asof"), **dict(kwargs)})


def research_browser_handler(**kwargs) -> ApiResponse:
    """JSON API handler. Unwired: no router, no auth dependency, no path."""
    return _dispatch(kwargs)


def research_browser_view(**kwargs) -> ViewModel:
    """Server-rendered view over the SAME payload the API returns.

    Identical semantics is the point: the view holds the API body's ``result``
    unchanged AND the same envelope and error object, so a field the UI reads and
    a field the API serves cannot drift — including on a refusal, where the view
    previously carried nothing but a status code.
    """
    response = _dispatch(kwargs)
    body = response.body
    envelope = {key: value for key, value in body.items() if key not in ("result", "error")}
    return ViewModel(
        status=response.status,
        result=body.get("result"),
        error=body.get("error"),
        envelope=envelope,
        headers=dict(response.headers),
    )


def result_schema() -> dict:
    """The schema both surfaces speak, for docs and contract tests."""
    screener.assert_research_tier_intact()
    return {
        "api_schema": API_SCHEMA,
        "result_set_schema": screener.RESEARCH_BROWSER_SCHEMA,
        "row_schema": screener.RESEARCH_ROW_SCHEMA,
        "tier": screener.TIER,
        "is_calibrated_screener": screener.IS_CALIBRATED_SCREENER,
        "model_version": MODEL_VERSION,
        "data_versions": dict(DATA_CONTRACT_VERSIONS),
        "sortable_columns": list(screener.SORTABLE_COLUMNS),
        "uncertainty_semantics": list(screener.UNCERTAINTY_SEMANTICS),
        "estimate_types": sorted(screener.ESTIMATE_TYPES),
        "max_page_size": MAX_PAGE_SIZE,
        "default_page_size": DEFAULT_PAGE_SIZE,
        "permitted_consumers": sorted(screener.PERMITTED_CONSUMERS),
    }
