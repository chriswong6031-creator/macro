"""Read-only API for the Government Revenue vertical intelligence workbench.

The service never recalculates procurement metrics at request time.  It serves
the compact, deterministic artifact produced by
``scripts.build_government_revenue`` and fails closed when that artifact is
missing or malformed.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_REPO = Path(os.environ.get("MACRO_REPO", "/opt/macro"))
_PATHS = (
    _REPO / "data" / "government_revenue" / "latest.json",
    _REPO / "site" / "government-revenue-data" / "latest.json",
)
_TICKER = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_NOTICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_LOCK = threading.Lock()
_CACHE: dict = {"path": None, "mtime_ns": None, "payload": None}
_SENSITIVE_KEY = re.compile(
    r"(?:^private|api[_-]?key|authorization|(?:^|_)(?:secret|token|password|credential)s?(?:$|_)|"
    r"raw_(?:body|payload|receipt|request|response)|(?:request|response)_headers)",
    re.IGNORECASE,
)
_SENSITIVE_QUERY_KEY = re.compile(
    r"(?:api[_-]?key|authorization|secret|token|password|credential)", re.IGNORECASE
)


def _public_url(value: object) -> str | None:
    try:
        parsed = urlsplit(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    query = urlencode([
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not _SENSITIVE_QUERY_KEY.search(key)
    ])
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    if port:
        host = f"{host}:{port}"
    return urlunsplit(("https", host, parsed.path, query, parsed.fragment))


def _scrub_public(value: object) -> object:
    """Recursively remove collector-private keys and credential-shaped URL params."""
    if isinstance(value, dict):
        return {
            str(key): _scrub_public(item)
            for key, item in value.items()
            if not _SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [_scrub_public(item) for item in value]
    if isinstance(value, str) and value.lower().startswith(("http://", "https://")):
        return _public_url(value)
    return value


def _artifact_path() -> Path | None:
    return next((path for path in _PATHS if path.exists()), None)


def _load() -> dict:
    path = _artifact_path()
    if path is None:
        raise HTTPException(status_code=503, detail="government revenue artifact unavailable")
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError as exc:
        raise HTTPException(status_code=503, detail="government revenue artifact unavailable") from exc
    with _LOCK:
        if (
            _CACHE["payload"] is not None
            and _CACHE["path"] == str(path)
            and _CACHE["mtime_ns"] == mtime_ns
        ):
            return _CACHE["payload"]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="government revenue artifact unreadable") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != "company_government_revenue.v1":
            raise HTTPException(status_code=503, detail="government revenue artifact schema mismatch")
        _CACHE.update(path=str(path), mtime_ns=mtime_ns, payload=payload)
        return payload


def _public_company(row: dict) -> dict:
    """Return the already-public compact row; never expose collector receipts."""
    allowed = {
        "ticker", "name", "entity_match", "metrics", "monthly_obligations",
        "recompete_candidates", "catalyst_facts", "confidence", "provenance",
        "awards", "recent_actions", "tags", "authority", "opportunity_candidates",
    }
    return _scrub_public({key: row[key] for key in allowed if key in row})


def _opportunity_intelligence(payload: dict) -> dict:
    value = payload.get("opportunity_intelligence")
    return value if isinstance(value, dict) else {}


def _procurement_workspace(payload: dict) -> dict:
    value = payload.get("procurement_workspace")
    if not isinstance(value, dict) or value.get("schema_version") != "government_procurement_workspace.v1":
        raise HTTPException(status_code=503, detail="government procurement workspace unavailable")
    return value


def _public_workspace_event(row: dict) -> dict:
    allowed = {
        "contract", "event_id", "record_id", "version", "kind", "state",
        "title_original", "title_zh", "translation_status", "agency", "change",
        "opportunity", "recompete", "dates", "amounts", "primary_date_id",
        "primary_amount_id", "listed_company_impacts", "primary_ticker",
        "display_priority", "evidence", "authority",
    }
    return _scrub_public({key: row[key] for key in allowed if key in row})


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"v1:{offset}".encode("ascii")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    if len(cursor) > 32 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
        version, offset = raw.split(":", 1)
        value = int(offset)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    if version != "v1" or value < 0 or value > 10_000:
        raise HTTPException(status_code=400, detail="invalid cursor")
    return value


def _public_opportunity(row: dict) -> dict:
    """Expose normalized official evidence and bounded derived context only."""
    allowed = {
        "contract", "notice_id", "solicitation_number", "revision_id", "title",
        "description", "notice_type", "base_type", "status", "agency", "office",
        "organization_code", "naics_code", "psc_code", "set_aside", "posted_at",
        "response_deadline", "archive_date", "place_of_performance", "resource_links",
        "known_at", "effective_at", "source_url", "tags", "documents",
        "days_to_response", "defense_relevant", "company_candidates", "authority",
        "current_state", "observation_horizon_at", "observation_age_minutes",
        "observation_basis", "current_state_reason",
    }
    return _scrub_public({key: row[key] for key in allowed if key in row})


def _public_opportunity_event(row: dict) -> dict:
    allowed = {
        "contract", "event_id", "event_type", "version", "notice_id", "revision_id",
        "title", "known_at", "effective_at", "first_seen_at", "changed_fields",
        "changed_values", "source_refs", "evidence_class", "confidence_state", "authority",
    }
    event = {key: row[key] for key in allowed if key in row}
    snapshot = row.get("record_snapshot")
    if isinstance(snapshot, dict):
        event["record_snapshot"] = _public_opportunity(snapshot)
    return _scrub_public(event)


def _validated_ticker(value: str | None) -> str | None:
    if value is None:
        return None
    ticker = value.strip().upper()
    if not _TICKER.fullmatch(ticker):
        raise HTTPException(status_code=400, detail="invalid ticker")
    return ticker


@router.get("/api/government-revenue/latest")
def latest(limit: int = Query(default=100, ge=1, le=250)) -> dict:
    payload = _load()
    opportunity = _opportunity_intelligence(payload)
    workspace = payload.get("procurement_workspace") or {}
    top_level = {
        key: payload.get(key)
        for key in (
            "schema_version", "workbench", "as_of", "known_at", "generated_at",
            "source", "authority", "freshness", "coverage", "market",
        )
        if key in payload
    }
    return _scrub_public(top_level | {
        "companies": [_public_company(row) for row in (payload.get("companies") or [])[:limit]],
        "opportunity_intelligence": {
            key: opportunity.get(key)
            for key in (
                "schema_version", "record_contract", "event_contract", "as_of",
                "known_at", "authority", "freshness", "coverage", "market", "provenance",
            )
            if key in opportunity
        },
        "procurement_workspace": {
            key: workspace.get(key)
            for key in (
                "schema_version", "event_contract", "as_of", "known_at", "authority",
                "freshness", "coverage", "facets", "total", "display_sort", "limitations",
            )
            if key in workspace
        },
    })


@router.get("/api/government-revenue/company/{ticker}")
def company(ticker: str) -> dict:
    ticker = _validated_ticker(ticker)
    payload = _load()
    row = next((item for item in payload.get("companies") or [] if item.get("ticker") == ticker), None)
    if row is None:
        raise HTTPException(status_code=404, detail="company not covered")
    return {
        "schema_version": payload["schema_version"],
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "authority": payload.get("authority"),
        "company": _public_company(row),
    }


@router.get("/api/government-revenue/search")
def search(q: str = Query(min_length=1, max_length=80), limit: int = Query(default=20, ge=1, le=50)) -> dict:
    needle = q.casefold().strip()
    payload = _load()
    matches = []
    for row in payload.get("companies") or []:
        haystack = f"{row.get('ticker', '')} {row.get('name', '')}".casefold()
        if needle in haystack:
            matches.append({
                "ticker": row.get("ticker"),
                "name": row.get("name"),
                "metrics": row.get("metrics") or {},
                "confidence": row.get("confidence"),
            })
        if len(matches) >= limit:
            break
    return {"as_of": payload.get("as_of"), "query": q, "results": matches}


@router.get("/api/government-revenue/opportunities")
def opportunities(
    q: str | None = Query(default=None, min_length=1, max_length=120),
    ticker: str | None = Query(default=None),
    agency: str | None = Query(default=None, min_length=1, max_length=100),
    status: str | None = Query(default=None, min_length=1, max_length=40),
    defense_only: bool = Query(default=False),
    deadline_within_days: int | None = Query(default=None, ge=0, le=730),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=50, ge=1, le=250),
) -> dict:
    """Search the prebuilt, point-in-time opportunity projection."""
    payload = _load()
    intelligence = _opportunity_intelligence(payload)
    ticker = _validated_ticker(ticker)
    needle = q.casefold().strip() if q else None
    agency_needle = agency.casefold().strip() if agency else None
    status_needle = status.casefold().strip() if status else None
    rows: list[dict] = []
    for raw in intelligence.get("opportunities") or []:
        if not isinstance(raw, dict):
            continue
        candidates = raw.get("company_candidates") or []
        if ticker and not any(item.get("ticker") == ticker for item in candidates if isinstance(item, dict)):
            continue
        if agency_needle and agency_needle not in str(raw.get("agency") or "").casefold():
            continue
        if status_needle and status_needle != str(raw.get("status") or "").casefold():
            continue
        if defense_only and not raw.get("defense_relevant"):
            continue
        days = raw.get("days_to_response")
        if deadline_within_days is not None and (
            not isinstance(days, int) or days < 0 or days > deadline_within_days
        ):
            continue
        if needle:
            haystack = " ".join(
                str(raw.get(key) or "")
                for key in (
                    "notice_id", "solicitation_number", "title", "description",
                    "agency", "office", "naics_code", "psc_code",
                )
            ).casefold()
            candidate_text = " ".join(
                f"{item.get('ticker', '')} {item.get('name', '')}"
                for item in candidates if isinstance(item, dict)
            ).casefold()
            if needle not in haystack and needle not in candidate_text:
                continue
        rows.append(_public_opportunity(raw))
    total = len(rows)
    page = rows[offset:offset + limit]
    return {
        "schema_version": intelligence.get("schema_version"),
        "as_of": intelligence.get("as_of") or payload.get("as_of"),
        "known_at": intelligence.get("known_at"),
        "authority": intelligence.get("authority") or payload.get("authority"),
        "freshness": intelligence.get("freshness") or {},
        "query": {
            "q": q, "ticker": ticker, "agency": agency, "status": status,
            "defense_only": defense_only, "deadline_within_days": deadline_within_days,
        },
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + len(page) < total,
        },
        "results": page,
    }


@router.get("/api/government-revenue/opportunity/{notice_id}")
def opportunity(notice_id: str) -> dict:
    if not _NOTICE_ID.fullmatch(notice_id):
        raise HTTPException(status_code=400, detail="invalid notice id")
    payload = _load()
    intelligence = _opportunity_intelligence(payload)
    row = next(
        (
            item for item in intelligence.get("opportunities") or []
            if isinstance(item, dict) and item.get("notice_id") == notice_id
        ),
        None,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="opportunity not covered")
    events = [
        event for event in intelligence.get("events") or []
        if isinstance(event, dict) and event.get("notice_id") == notice_id
    ]
    return {
        "schema_version": intelligence.get("schema_version"),
        "as_of": intelligence.get("as_of") or payload.get("as_of"),
        "known_at": intelligence.get("known_at"),
        "authority": intelligence.get("authority") or payload.get("authority"),
        "opportunity": _public_opportunity(row),
        "events": [_public_opportunity_event(event) for event in events],
    }


@router.get("/api/government-revenue/recompetes")
def recompetes(
    ticker: str | None = Query(default=None),
    within_days: int = Query(default=540, ge=30, le=1095),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=50, ge=1, le=250),
) -> dict:
    """Return deterministic POP-end watches, never implied solicitation forecasts."""
    payload = _load()
    ticker = _validated_ticker(ticker)
    rows: list[dict] = []
    for company_row in payload.get("companies") or []:
        if not isinstance(company_row, dict):
            continue
        if ticker and company_row.get("ticker") != ticker:
            continue
        for watch in company_row.get("recompete_candidates") or []:
            if not isinstance(watch, dict) or int(watch.get("days_to_end") or 10**9) > within_days:
                continue
            rows.append({
                "ticker": company_row.get("ticker"),
                "name": company_row.get("name"),
                "classification": "derived_deterministic",
                "label_limit": "period-of-performance expiry watch; not an official recompete date or solicitation forecast",
                "authority": payload.get("authority"),
                **watch,
            })
    rows.sort(key=lambda row: (int(row.get("days_to_end") or 10**9), str(row.get("ticker") or "")))
    total = len(rows)
    page = rows[offset:offset + limit]
    return {
        "schema_version": payload.get("schema_version"),
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "authority": payload.get("authority"),
        "pagination": {
            "offset": offset, "limit": limit, "total": total,
            "has_more": offset + len(page) < total,
        },
        "results": page,
    }


@router.get("/api/government-revenue/workspace")
def workspace(
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    """Return a stable cursor page in the backend-prioritized workspace order."""
    source = _procurement_workspace(_load())
    offset = _decode_cursor(cursor)
    events = [
        _public_workspace_event(row)
        for row in (source.get("events") or [])[offset:offset + limit]
        if isinstance(row, dict)
    ]
    total = int(source.get("total") or len(source.get("events") or []))
    next_offset = offset + len(events)
    metadata = {
        key: source.get(key)
        for key in (
            "schema_version", "event_contract", "as_of", "known_at", "generated_at",
            "authority", "freshness", "coverage", "facets", "total", "display_sort",
            "federation_contract", "limitations",
        )
        if key in source
    }
    return _scrub_public(metadata | {
        "events": events,
        "next_cursor": _encode_cursor(next_offset) if next_offset < total else None,
    })


def _event_critical_date(row: dict) -> str:
    primary = row.get("primary_date_id")
    dates = row.get("dates") or []
    value = next(
        (item.get("value") for item in dates if isinstance(item, dict) and item.get("id") == primary),
        None,
    )
    return str(value or "9999-12-31")


def _event_primary_amount(row: dict) -> float:
    primary = row.get("primary_amount_id")
    amounts = row.get("amounts") or []
    value = next(
        (item.get("value") for item in amounts if isinstance(item, dict) and item.get("id") == primary),
        None,
    )
    return float(value) if isinstance(value, (int, float)) else float("-inf")


@router.get("/api/government-revenue/events")
def events(
    mode: str = Query(default="changes", pattern=r"^(changes|opportunities|recompetes)$"),
    q: str | None = Query(default=None, min_length=1, max_length=120),
    ticker: str | None = Query(default=None),
    agency_id: str | None = Query(default=None, min_length=1, max_length=120),
    notice_type: str | None = Query(default=None, min_length=1, max_length=80),
    evidence_class: str | None = Query(default=None, min_length=1, max_length=60),
    impact: str | None = Query(default=None, pattern=r"^(high|medium|low|unknown)$"),
    deadline: str = Query(default="all", pattern=r"^(7d|30d|90d|540d|all)$"),
    scope: str = Query(default="mapped", pattern=r"^(mapped|all)$"),
    sort: str = Query(default="priority", pattern=r"^(priority|newest|critical_date|largest_official_amount)$"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    """Filter the prebuilt event ledger without recalculating intelligence."""
    source = _procurement_workspace(_load())
    ticker = _validated_ticker(ticker)
    needle = q.casefold().strip() if q else None
    agency_needle = agency_id.casefold().strip() if agency_id else None
    notice_needle = notice_type.casefold().strip() if notice_type else None
    evidence_needle = evidence_class.casefold().strip() if evidence_class else None
    deadline_days = None if deadline == "all" else int(deadline[:-1])
    source_rows = [row for row in source.get("events") or [] if isinstance(row, dict)]
    if mode == "opportunities":
        latest_by_record: dict[str, dict] = {}
        for row in source_rows:
            if row.get("kind") != "opportunity":
                continue
            record_id = str(row.get("record_id") or "")
            prior = latest_by_record.get(record_id)
            row_clock = str((row.get("change") or {}).get("known_at") or "")
            prior_clock = str((prior.get("change") or {}).get("known_at") or "") if prior else ""
            if prior is None or (row_clock, int(row.get("version") or 0)) > (
                prior_clock,
                int(prior.get("version") or 0),
            ):
                latest_by_record[record_id] = row
        source_rows = list(latest_by_record.values())

    rows: list[dict] = []
    for raw in source_rows:
        if not isinstance(raw, dict):
            continue
        if mode == "opportunities" and raw.get("kind") != "opportunity":
            continue
        if mode == "recompetes" and raw.get("kind") != "recompete":
            continue
        impacts = raw.get("listed_company_impacts") or []
        if scope == "mapped" and not impacts:
            continue
        if ticker and raw.get("primary_ticker") != ticker and not any(
            item.get("ticker") == ticker for item in impacts if isinstance(item, dict)
        ):
            continue
        agency_name = str((raw.get("agency") or {}).get("department_name") or "")
        if agency_needle and agency_needle not in agency_name.casefold():
            continue
        raw_notice_type = str((raw.get("opportunity") or {}).get("notice_type") or "")
        if notice_needle and notice_needle != raw_notice_type.casefold():
            continue
        mapping_class = str((raw.get("evidence") or {}).get("mapping_class") or "unmapped")
        if evidence_needle and evidence_needle != mapping_class.casefold():
            continue
        materiality = str(
            (((impacts or [{}])[0].get("materiality") or {}).get("band") or "unknown")
        )
        if impact and impact != materiality:
            continue
        if deadline_days is not None:
            days = (raw.get("recompete") or {}).get("days_to_current_end")
            if days is None:
                due = next(
                    (
                        item.get("value") for item in raw.get("dates") or []
                        if isinstance(item, dict) and item.get("id") == "response_deadline"
                    ),
                    None,
                )
                try:
                    due_day = datetime.fromisoformat(str(due).replace("Z", "+00:00")).date()
                    as_of_day = datetime.fromisoformat(str(source.get("as_of"))).date()
                    days = (due_day - as_of_day).days
                except (TypeError, ValueError):
                    days = None
            if not isinstance(days, int) or days < 0 or days > deadline_days:
                continue
        if needle:
            haystack = " ".join([
                str(raw.get("event_id") or ""),
                str(raw.get("record_id") or ""),
                str(raw.get("title_original") or ""),
                agency_name,
                str(raw.get("primary_ticker") or ""),
                str((raw.get("change") or {}).get("what_changed_en") or ""),
            ]).casefold()
            if needle not in haystack:
                continue
        rows.append(raw)

    if sort == "newest":
        rows.sort(key=lambda row: str((row.get("change") or {}).get("known_at") or ""), reverse=True)
    elif sort == "critical_date":
        rows.sort(key=_event_critical_date)
    elif sort == "largest_official_amount":
        rows.sort(key=_event_primary_amount, reverse=True)
    # priority retains the audited order already serialized by the engine.

    offset = _decode_cursor(cursor)
    total = len(rows)
    page = rows[offset:offset + limit]
    next_offset = offset + len(page)
    return {
        "schema_version": source.get("schema_version"),
        "event_contract": source.get("event_contract"),
        "as_of": source.get("as_of"),
        "known_at": source.get("known_at"),
        "authority": source.get("authority"),
        "freshness": source.get("freshness"),
        "query": {
            "mode": mode, "q": q, "ticker": ticker, "agency_id": agency_id,
            "notice_type": notice_type, "evidence_class": evidence_class,
            "impact": impact, "deadline": deadline, "scope": scope, "sort": sort,
        },
        "events": [_public_workspace_event(row) for row in page],
        "next_cursor": _encode_cursor(next_offset) if next_offset < total else None,
        "total": total,
    }


@router.get("/api/government-revenue/event/{event_id}")
def event(event_id: str) -> dict:
    if not _NOTICE_ID.fullmatch(event_id):
        raise HTTPException(status_code=400, detail="invalid event id")
    source = _procurement_workspace(_load())
    row = next(
        (
            item for item in source.get("events") or []
            if isinstance(item, dict) and item.get("event_id") == event_id
        ),
        None,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="procurement event not covered")
    return {
        "schema_version": source.get("schema_version"),
        "as_of": source.get("as_of"),
        "known_at": source.get("known_at"),
        "authority": source.get("authority"),
        "event": _public_workspace_event(row),
    }
