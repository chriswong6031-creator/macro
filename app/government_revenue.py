"""Read-only API for the Government Revenue vertical intelligence workbench.

The service never recalculates procurement metrics at request time.  It serves
the compact, deterministic artifact produced by
``scripts.build_government_revenue`` and fails closed when that artifact is
missing or malformed.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_REPO = Path(os.environ.get("MACRO_REPO", "/opt/macro"))
_PATHS = (
    _REPO / "data" / "government_revenue" / "latest.json",
    _REPO / "site" / "government-revenue-data" / "latest.json",
)
_TICKER = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_LOCK = threading.Lock()
_CACHE: dict = {"path": None, "mtime_ns": None, "payload": None}


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
        "awards", "recent_actions",
    }
    return {key: row[key] for key in allowed if key in row}


@router.get("/api/government-revenue/latest")
def latest(limit: int = Query(default=100, ge=1, le=250)) -> dict:
    payload = _load()
    return {
        key: value
        for key, value in payload.items()
        if key != "companies"
    } | {
        "companies": [_public_company(row) for row in (payload.get("companies") or [])[:limit]],
    }


@router.get("/api/government-revenue/company/{ticker}")
def company(ticker: str) -> dict:
    ticker = ticker.strip().upper()
    if not _TICKER.fullmatch(ticker):
        raise HTTPException(status_code=400, detail="invalid ticker")
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
