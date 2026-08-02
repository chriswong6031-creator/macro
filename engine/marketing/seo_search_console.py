"""engine.marketing.seo_search_console — Google Search Console ingestion adapter.

MKT-SEO-07 W0  (Beacon dept).  Wraps the Search Analytics REST API (v3), the
Sitemaps API (v3) and the URL Inspection API (v1) using raw HTTP + google-auth
bearer tokens.  Fully offline when credentials absent — writes explicit
unavailable state artifacts, never a healthy zero.

Public API (all fail-soft — no public function raises out of ``run``):
  load_sa_info(*, creds_path=None) -> tuple[dict | None, str | None]
  fetch_search_analytics(creds, prop, start_date, end_date, ...) -> list[dict]
  fetch_sitemaps(info, prop, *, token=None) -> dict
  inspect_urls(info, prop, urls, *, token=None, pace_s=...) -> list[dict]
  run(root, *, creds_path=None, days=28, as_of=None, write=True) -> dict

Artifacts written under data/marketing/seo/:
  search_console_state.json         — always (available bool + metadata)
  search_console_index_status.json  — always (sitemap + URL-inspection diagnostics)
  search_console_daily.parquet      — only when available; append-dedupe + 16-month cap
  page_family_scorecard.json        — only when available
  query_gaps.json                   — only when available

Credential resolution (checked in order):
  1. explicit creds_path param            (a FILE PATH — read it)
  2. env GOOGLE_APPLICATION_CREDENTIALS   (a FILE PATH — read it)
  3. env GSC_SA_JSON                      (raw JSON string from the CI secret)

The JSON is parsed ONCE, in-process, and handed to
``service_account.Credentials.from_service_account_info`` — no key material ever
touches disk on our side.  Parsing is deliberately forgiving of the one failure
mode the operator actually hit: a DOUBLE-ENCODED secret (the JSON pasted
quote-wrapped, i.e. ``json.dumps`` applied twice).  google-auth's
``from_service_account_file`` does ``json.load(f)`` then ``.keys()`` on the
result, so a double-encoded blob crashes with the opaque
``'str' object has no attribute 'keys'``.  ``load_sa_info`` unwraps up to two
layers of string encoding and, past that, says exactly what is wrong — including
a content-free SHAPE fingerprint of the rejected payload (``_describe_shape``:
category label + character count, never the payload) so the operator does not
spend a 30-60 min CI cycle per guess about what they actually pasted.

CLI:
  python -m engine.marketing.seo_search_console --root . [--days 28] [--dry-run]
  Prints compact summary.  exit 0 even when unavailable; exit 1 only on crash.

Dependency: google-auth (in requirements.txt) for service-account bearer tokens.
Soft-import: if not installed, writes unavailable state with reason.

SECURITY: ``private_key`` (and any other key material) is NEVER logged, never
printed, never returned in an error string, never written to any artifact — not
even truncated.  ``client_email`` and ``project_id`` ARE surfaced on purpose:
the operator needs them to know which service account to grant GSC access to.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote as _url_quote

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GSC_API_BASE = "https://www.googleapis.com/webmasters/v3/sites"
_URL_INSPECT_ENDPOINT = (
    "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
)
_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
_DEFAULT_PROPERTY = "sc-domain:mastermind-x.com"
_ROW_LIMIT = 25_000
_PAGE_CAP_MONTHS = 16   # cap parquet to last 16 months of dates

_ARTIFACTS_REL = Path("data") / "marketing" / "seo"
_STATE_FILE = "search_console_state.json"
_DAILY_FILE = "search_console_daily.parquet"
_SCORECARD_FILE = "page_family_scorecard.json"
_GAPS_FILE = "query_gaps.json"
_INDEX_STATUS_FILE = "search_console_index_status.json"

# Service-account fields google-auth requires before it will even try a token
# exchange.  Naming the missing ones beats "'str' object has no attribute 'keys'".
_SA_REQUIRED_KEYS = ("type", "client_email", "private_key", "token_uri")
_SA_TYPE = "service_account"
_MAX_JSON_UNWRAPS = 2   # tolerate a double-encoded secret, not an infinite onion

# --- URL Inspection budget -------------------------------------------------
# Quota is 2000 inspections/day and 600/min per property.  We inspect a fixed,
# deterministic core set most-important-first and pace the requests so a burst
# can never trip the per-minute ceiling.
_MAX_INSPECT_URLS = 12
_INSPECT_PACE_S = 0.25          # 12 URLs ≈ 3 s; 240/min worst case, well under 600
_RECENT_BLOG_COUNT = 2

#: Core set, most-important-first.  Site-root first ("" -> the origin itself).
_CORE_INSPECT_PATHS = (
    "",
    "products/index.html",
    "macro.html",
    "us_stocks.html",
    "plans.html",
    "start.html",
    "blog/index.html",
    "research/index.html",
    "learn/index.html",
    "tools/index.html",
)

# Brand detection: matches "mastermind" or "mastermind-x" etc. (case-insensitive).
_BRAND_RE = re.compile(r"master\s*mind", re.IGNORECASE)

# Query-gap heuristics (non-brand, in window).
_GAP_MIN_IMPRESSIONS = 20
_GAP_MAX_CTR = 0.01            # < 1 %
_GAP_POS_LOW = 11              # inclusive
_GAP_POS_HIGH = 30             # inclusive
_GAP_LIMIT = 30                # max gaps in output

# ---------------------------------------------------------------------------
# Atomic write helpers (mirrors seo_director pattern)
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path: Path, obj: Any) -> None:
    """Atomic write via temp file in same dir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def _write_parquet_atomic(path: Path, df: "pd.DataFrame") -> None:
    """Atomic write parquet via temp file."""
    import pandas as pd  # noqa: F401 — guarded by caller
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".parquet")
    os.close(tmp_fd)
    try:
        df.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


# ---------------------------------------------------------------------------
# Typed failures — the caller needs to tell an auth problem from an API problem,
# and a 403 (grant the SA access in the GSC UI) from a 404 (wrong property).
# ---------------------------------------------------------------------------


class GscAuthError(RuntimeError):
    """The service-account credentials were rejected while minting a token."""


class GscApiError(RuntimeError):
    """A Search Console REST call returned a non-2xx status.

    ``status`` is the HTTP status code so the caller can map 403/404 to the
    concrete operator action instead of a generic 'api error'.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = int(status)
        self.message = message


# ---------------------------------------------------------------------------
# Credential resolution — parse once, validate loudly, never spill key material
# ---------------------------------------------------------------------------


def _scrub_secret(text: str, info: dict | None = None) -> str:
    """Return ``text`` with any key material removed.

    Two layers, because an exception string can carry key bytes from anywhere:
      1. the literal ``private_key`` value of ``info`` (exact-substring removal),
      2. anything that looks like a PEM block or a ``key=`` / ``token=`` pair.
    """
    out = str(text)
    if info:
        for field in ("private_key", "private_key_id"):
            val = info.get(field)
            if isinstance(val, str) and len(val) >= 8 and val in out:
                out = out.replace(val, "<redacted>")
    out = re.sub(
        r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*PRIVATE KEY-----",
        "<redacted-pem>", out, flags=re.DOTALL,
    )
    out = re.sub(
        r"(token|key|secret|password|credential)[=:]\s*\S+",
        r"\1=<redacted>", out, flags=re.IGNORECASE,
    )
    return out


def _one_line(text: str, limit: int = 300) -> str:
    """Collapse an exception string to a single readable line."""
    flat = " ".join(str(text).split())
    return flat[:limit]


#: A whole payload that matches this (after strip) is an ADDRESS, not a key file.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
#: A single-line ``*.json`` value carrying no brace is a PATH, not file contents.
_JSON_PATH_RE = re.compile(r"^[^\n\r{}]{1,255}\.json$", re.IGNORECASE)


def _describe_shape(text: str) -> str:
    """Classify a REJECTED credential payload without ever echoing it.

    Every failed operator guess costs a full CI cycle (run 30742044120 burned one
    on ``the inner layer is not valid JSON: Expecting value: line 1 column 1``,
    which says the paste was *a quoted string* but not WHAT string), so a parse
    error has to name the SHAPE of what was actually pasted.

    Returns a fixed category label plus the payload LENGTH in characters (a
    40-char value is obviously not a key file; a real one is ~2300+).  First
    match wins.

    SECURITY: the return value is built from literals and ``len()`` only — it can
    never contain the payload, a substring of it, or one byte of ``private_key``.
    The payload is inspected, never logged.  Length is measured after stripping
    surrounding whitespace, i.e. on the same text the parser saw.
    """
    s = str(text).strip()
    n = len(s)
    if not s:
        return "empty / whitespace-only (0 chars)"
    if _EMAIL_RE.match(s):
        label = (
            "looks like an email address — paste the CONTENTS of the downloaded "
            ".json key file, not the service-account email"
        )
    elif s.startswith("-----BEGIN"):
        label = (
            "looks like a bare PEM private key — the secret must be the whole "
            ".json key file, not just the private_key field"
        )
    elif s.startswith("/") or s.startswith("~/") or _JSON_PATH_RE.match(s):
        label = (
            "looks like a FILE PATH — GSC_SA_JSON must contain the file's "
            "CONTENTS; use GOOGLE_APPLICATION_CREDENTIALS for a path"
        )
    elif s.startswith("{") and not s.endswith("}"):
        label = (
            "looks like TRUNCATED JSON (starts with '{' but does not end with "
            "'}') — the paste was cut off"
        )
    elif s.startswith("{"):
        label = "looks like a complete JSON object"
    else:
        label = "unrecognized text"
    return f"{label} ({n} chars)"


def _parse_sa_json(raw: str, source: str) -> tuple[dict | None, str | None]:
    """Parse a service-account JSON blob, tolerating a double-encoded secret.

    ``json.loads`` on a JSON *string literal* returns a ``str``, not a dict — that
    is exactly what google-auth chokes on with ``'str' object has no attribute
    'keys'``.  So: strip whitespace and a UTF-8 BOM, then ``json.loads`` up to
    ``_MAX_JSON_UNWRAPS`` times, stopping as soon as the result is not a string.
    A double-encoded secret (the operator's actual failure) therefore just works;
    anything deeper is named rather than crashed on.

    Every error string carries a ``_describe_shape`` fingerprint of the layer that
    actually failed — the INNER layer past depth 0, because that is where a pasted
    email address or file path lands once the outer quotes come off.
    """
    text = raw.strip().lstrip("﻿").strip()
    if not text:
        return None, f"{source} is empty"

    obj: Any = text
    for depth in range(_MAX_JSON_UNWRAPS):
        try:
            obj = json.loads(obj)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            # Never echo the payload — JSONDecodeError only carries a position,
            # and _describe_shape returns a category label + length, no content.
            # `obj` still holds the layer that failed (the assignment never ran),
            # so past depth 0 this fingerprints the INNER layer — where a pasted
            # email or file path actually shows up.
            layer = obj if isinstance(obj, str) else text
            if depth == 0:
                return None, (
                    f"{source} is not valid JSON: {_one_line(exc, 120)} "
                    f"[payload: {_describe_shape(layer)}]"
                )
            return None, (
                f"{source} is multiply-encoded and the inner layer is not valid "
                f"JSON: {_one_line(exc, 120)} "
                f"[inner payload: {_describe_shape(layer)}]"
            )
        if not isinstance(obj, str):
            break
    else:
        return None, (
            f"{source} parsed to str after {_MAX_JSON_UNWRAPS} unwraps — "
            f"the secret is multiply-encoded "
            f"[inner payload: {_describe_shape(obj)}]"
        )

    if not isinstance(obj, dict):
        return None, (
            f"{source} parsed to {type(obj).__name__} — expected a JSON object"
        )
    return obj, None


def _validate_sa_info(
    info: dict, source: str, raw: str | None = None
) -> str | None:
    """Return a precise error string, or None when ``info`` is usable.

    ``raw`` is the payload AS PASTED; when given, a content-free shape
    fingerprint of it is appended so the operator sees the size and kind of what
    landed in the secret alongside the field-level complaint.

    SECURITY: names the missing KEYS, never their values; the fingerprint is a
    category label plus a length (see ``_describe_shape``).
    """
    hint = "" if raw is None else f" [payload: {_describe_shape(raw)}]"
    missing = [k for k in _SA_REQUIRED_KEYS if not str(info.get(k) or "").strip()]
    if missing:
        return (
            f"{source}: service-account JSON missing keys: "
            f"{', '.join(missing)}{hint}"
        )
    actual_type = str(info.get("type"))
    if actual_type != _SA_TYPE:
        return (
            f"{source}: service-account JSON has type={actual_type!r} — "
            f"expected {_SA_TYPE!r}{hint}"
        )
    return None


def load_sa_info(
    *, creds_path: str | Path | None = None
) -> tuple[dict | None, str | None]:
    """Resolve, parse and validate the service-account JSON.

    Source order (unchanged from the original ``_resolve_creds``):
      1. explicit ``creds_path`` param            — a FILE PATH, read it
      2. env ``GOOGLE_APPLICATION_CREDENTIALS``   — a FILE PATH, read it
      3. env ``GSC_SA_JSON``                      — raw JSON from the CI secret

    Returns:
        ``(info, None)`` on success, ``(None, error)`` otherwise.  ``error`` names
        precisely what is wrong so the operator can fix the secret without
        guessing — the whole point of this helper.

    SECURITY: no branch of this function can emit ``private_key`` or any other
    key material.  ``client_email`` / ``project_id`` are deliberately NOT secret
    and are surfaced by callers so the operator knows which SA to grant access to.
    """
    raw: str | None = None
    source = ""

    if creds_path is not None:
        source = f"credentials file {creds_path}"
        p = str(creds_path)
        if not os.path.isfile(p):
            return None, f"credentials file not found: {p}"
        try:
            raw = Path(p).read_text(encoding="utf-8")
        except OSError as exc:
            return None, f"credentials file unreadable: {_one_line(exc, 160)}"
    else:
        env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if env_path:
            source = f"GOOGLE_APPLICATION_CREDENTIALS ({env_path})"
            if not os.path.isfile(env_path):
                return None, (
                    f"GOOGLE_APPLICATION_CREDENTIALS points at a missing file: "
                    f"{env_path}"
                )
            try:
                raw = Path(env_path).read_text(encoding="utf-8")
            except OSError as exc:
                return None, (
                    f"GOOGLE_APPLICATION_CREDENTIALS unreadable: {_one_line(exc, 160)}"
                )
        else:
            env_json = os.environ.get("GSC_SA_JSON", "")
            if env_json.strip():
                source = "GSC_SA_JSON"
                raw = env_json

    if raw is None:
        return None, "credentials not configured"

    info, err = _parse_sa_json(raw, source)
    if err is not None:
        return None, err
    assert info is not None  # narrowed by err is None

    err = _validate_sa_info(info, source, raw=raw)
    if err is not None:
        return None, err
    return info, None


def sa_identity(info: dict | None) -> dict:
    """The non-secret identity fields, safe to print and to write to artifacts."""
    if not info:
        return {}
    out = {}
    for field in ("client_email", "project_id"):
        val = info.get(field)
        if isinstance(val, str) and val:
            out[field] = val
    return out


# ---------------------------------------------------------------------------
# Bearer-token helper using google-auth
# ---------------------------------------------------------------------------


def _get_bearer_token(info: dict) -> str:
    """Return a valid OAuth2 bearer token for the GSC read-only scope.

    Takes the already-validated service-account dict — nothing is written to
    disk, so no key material can be left behind by a crashed process.

    Raises:
        ImportError:   google-auth not installed.
        GscAuthError:  credentials rejected (bad key, clock skew, revoked SA).

    SECURITY: the token is returned as a string, never logged; any google.auth
    error string is scrubbed before it becomes a reason.
    """
    from google.oauth2 import service_account  # type: ignore
    from google.auth.transport.requests import Request  # type: ignore

    try:
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=_SCOPES
        )
        credentials.refresh(Request())
    except Exception as exc:  # noqa: BLE001 — one clean line, never a traceback
        who = info.get("client_email") or "service account"
        raise GscAuthError(
            f"service account {who} could not obtain a token: "
            f"{_scrub_secret(_one_line(exc, 200), info)}"
        ) from None
    return credentials.token  # type: ignore[return-value]


def _token_for(info: dict, token: str | None = None) -> str:
    """Reuse a caller-supplied token, else mint one."""
    return token if token else _get_bearer_token(info)


# ---------------------------------------------------------------------------
# REST call helpers
# ---------------------------------------------------------------------------


def _api_error_message(resp: Any) -> str:
    """Best-effort one-line message from a Google API error body."""
    try:
        payload = resp.json()
    except Exception:  # noqa: BLE001
        payload = None
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict) and err.get("message"):
            return _one_line(err["message"], 200)
        if isinstance(err, str):
            return _one_line(err, 200)
    return _one_line(getattr(resp, "reason", "") or "HTTP error", 200)


def _raise_for_status(resp: Any) -> None:
    """Turn a non-2xx response into a GscApiError that CARRIES the status.

    ``requests.raise_for_status`` gives an HTTPError whose status is only
    recoverable via ``exc.response``; a 403 here means 'grant the service account
    access in the GSC UI' and a 404 means 'wrong property string', and those are
    different operator actions, so the status is part of the type.
    """
    status = int(getattr(resp, "status_code", 0) or 0)
    if status and status >= 400:
        raise GscApiError(status, _api_error_message(resp))


def _gsc_query(
    token: str,
    prop: str,
    start_date: str,
    end_date: str,
    dimensions: tuple[str, ...],
    search_type: str,
    start_row: int,
    row_limit: int,
) -> dict:
    """POST one page to the Search Analytics query endpoint.

    Returns the JSON-parsed response dict (may have 'rows' key, may not).
    Raises GscApiError on HTTP errors.
    """
    import requests  # type: ignore

    prop_encoded = _url_quote(prop, safe="")
    url = f"{_GSC_API_BASE}/{prop_encoded}/searchAnalytics/query"
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": list(dimensions),
        "searchType": search_type,
        "startRow": start_row,
        "rowLimit": row_limit,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=body, headers=headers, timeout=60)
    _raise_for_status(resp)
    return resp.json()


# ---------------------------------------------------------------------------
# Public: fetch_search_analytics
# ---------------------------------------------------------------------------


def fetch_search_analytics(
    creds: dict | str | Path,
    prop: str,
    start_date: str,
    end_date: str,
    *,
    dimensions: tuple[str, ...] = ("date", "page", "query", "country", "device"),
    search_type: str = "web",
    row_limit: int = _ROW_LIMIT,
    token: str | None = None,
) -> list[dict]:
    """Fetch search analytics rows for a property and date range via REST pagination.

    Args:
        creds:       Validated service-account dict (preferred — no disk round
                     trip), or a path to a service-account JSON key file.
        prop:        GSC property string (e.g. 'sc-domain:mastermind-x.com').
        start_date:  ISO date string 'YYYY-MM-DD'.
        end_date:    ISO date string 'YYYY-MM-DD'.
        dimensions:  Ordered tuple of dimension names.
        search_type: 'web' | 'image' | 'video' | 'news'.
        row_limit:   Max rows per page request (API max 25000).
        token:       Reuse an already-minted bearer token (optional).

    Returns:
        List of row dicts with keys = dimensions + ['clicks','impressions','ctr','position'].
        May be incomplete (API returns top rows by impressions, not all rows).

    Raises:
        ImportError:   if google-auth is not installed.
        GscAuthError:  credentials rejected while minting a token.
        GscApiError:   non-2xx from the API (carries .status).
        ValueError:    ``creds`` is a path that will not parse/validate.
    """
    if isinstance(creds, dict):
        info = creds
    else:
        info, err = load_sa_info(creds_path=creds)
        if info is None:
            raise ValueError(err or "credentials not configured")

    token = _token_for(info, token)

    all_rows: list[dict] = []
    start_row = 0

    while True:
        data = _gsc_query(
            token, prop, start_date, end_date,
            dimensions, search_type, start_row, row_limit,
        )
        page_rows = data.get("rows", [])
        if not page_rows:
            break

        for row in page_rows:
            keys = row.get("keys", [])
            rec: dict[str, Any] = {}
            for i, dim in enumerate(dimensions):
                rec[dim] = keys[i] if i < len(keys) else None
            rec["clicks"] = row.get("clicks", 0)
            rec["impressions"] = row.get("impressions", 0)
            rec["ctr"] = row.get("ctr", 0.0)
            rec["position"] = row.get("position", 0.0)
            all_rows.append(rec)

        start_row += len(page_rows)
        if len(page_rows) < row_limit:
            # Last page.
            break

    return all_rows


# ---------------------------------------------------------------------------
# Index-status diagnostics: Sitemaps API + URL Inspection API
#
# Search Analytics answers "how is it performing".  When a property is
# DEINDEXED, analytics is a flat zero and says nothing about why.  These two
# read-only endpoints (same webmasters.readonly scope) answer the actual
# question: has Google fetched the sitemap at all, and what does it say about
# each core URL.
# ---------------------------------------------------------------------------


def _sitemaps_get(token: str, prop: str) -> dict:
    """GET the Sitemaps list endpoint.  Own function so tests have one seam."""
    import requests  # type: ignore

    prop_encoded = _url_quote(prop, safe="")
    url = f"{_GSC_API_BASE}/{prop_encoded}/sitemaps"
    resp = requests.get(
        url, headers={"Authorization": f"Bearer {token}"}, timeout=60
    )
    _raise_for_status(resp)
    return resp.json() or {}


def _inspect_post(token: str, prop: str, url: str) -> dict:
    """POST one URL Inspection request.  Own function so tests have one seam."""
    import requests  # type: ignore

    resp = requests.post(
        _URL_INSPECT_ENDPOINT,
        json={"inspectionUrl": url, "siteUrl": prop, "languageCode": "en-US"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=60,
    )
    _raise_for_status(resp)
    return resp.json() or {}


def fetch_sitemaps(info: dict, prop: str, *, token: str | None = None) -> dict:
    """List the sitemaps Google knows about for ``prop``.

    Returns a dict::

        {"sitemaps": [ {path, lastSubmitted, lastDownloaded, isPending,
                        warnings, errors, submitted, indexed, contents}, ... ],
         "never_downloaded": [path, ...],
         "count": int}

    ``never_downloaded`` is the headline finding: a sitemap Google has never
    fetched cannot have contributed a single indexed URL.

    Raises GscAuthError / GscApiError — the caller decides how to fail soft.
    """
    token = _token_for(info, token)
    payload = _sitemaps_get(token, prop)

    out: list[dict] = []
    never: list[str] = []
    for entry in payload.get("sitemap", []) or []:
        if not isinstance(entry, dict):
            continue
        contents = []
        submitted = 0
        indexed = 0
        for c in entry.get("contents", []) or []:
            if not isinstance(c, dict):
                continue
            c_sub = _as_int(c.get("submitted"))
            c_idx = _as_int(c.get("indexed"))
            submitted += c_sub
            indexed += c_idx
            contents.append({
                "type": c.get("type"),
                "submitted": c_sub,
                "indexed": c_idx,
            })
        last_downloaded = entry.get("lastDownloaded")
        path = str(entry.get("path") or "")
        if not last_downloaded:
            never.append(path)
        out.append({
            "path": path,
            "lastSubmitted": entry.get("lastSubmitted"),
            "lastDownloaded": last_downloaded,
            "isPending": bool(entry.get("isPending", False)),
            "isSitemapsIndex": bool(entry.get("isSitemapsIndex", False)),
            "type": entry.get("type"),
            "warnings": _as_int(entry.get("warnings")),
            "errors": _as_int(entry.get("errors")),
            "submitted": submitted,
            "indexed": indexed,
            "contents": contents,
        })

    return {"sitemaps": out, "never_downloaded": never, "count": len(out)}


def _as_int(val: Any) -> int:
    """The Sitemaps API returns counts as STRINGS (int64 over JSON)."""
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return 0


def _index_status_fields(result: dict) -> dict:
    """Project the fields we care about out of one inspectionResult."""
    idx = result.get("indexStatusResult") or {}
    return {
        "verdict": idx.get("verdict"),
        "coverageState": idx.get("coverageState"),
        "robotsTxtState": idx.get("robotsTxtState"),
        "indexingState": idx.get("indexingState"),
        "lastCrawlTime": idx.get("lastCrawlTime"),
        "pageFetchState": idx.get("pageFetchState"),
        "googleCanonical": idx.get("googleCanonical"),
        "userCanonical": idx.get("userCanonical"),
        "inspectionResultLink": result.get("inspectionResultLink"),
    }


def inspect_urls(
    info: dict,
    prop: str,
    urls: list[str],
    *,
    token: str | None = None,
    pace_s: float = _INSPECT_PACE_S,
) -> list[dict]:
    """Run the URL Inspection API over ``urls`` (already capped by the caller).

    One record per input URL, in input order.  A per-URL failure is RECORDED and
    the sweep continues — a single 500 or a single unindexable URL must not cost
    us the other eleven answers.

    Quota: 2000/day, 600/min per property.  ``pace_s`` sleeps between calls so a
    burst can never trip the per-minute ceiling.
    """
    token = _token_for(info, token)

    out: list[dict] = []
    for i, url in enumerate(urls):
        if i and pace_s:
            time.sleep(pace_s)
        rec: dict[str, Any] = {"url": url, "error": None}
        try:
            payload = _inspect_post(token, prop, url)
            result = payload.get("inspectionResult") or {}
            rec.update(_index_status_fields(result))
        except Exception as exc:  # noqa: BLE001 — record and keep sweeping
            rec["error"] = _scrub_secret(_one_line(exc, 200), info)
            log.warning("gsc: url inspection failed for %s: %s", url, rec["error"])
        rec["indexed"] = _url_is_indexed(rec)
        out.append(rec)
    return out


def _url_is_indexed(rec: dict) -> bool:
    """PASS is Google's own word for 'this URL is indexed and can appear'.

    Deliberately NOT a substring sniff on coverageState: 'Crawled - currently not
    indexed' and 'Submitted and indexed' both contain 'indexed'.
    """
    return str(rec.get("verdict") or "").upper() == "PASS"


# --- core URL set ----------------------------------------------------------

_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)
_URL_BLOCK_RE = re.compile(r"<url>(.*?)</url>", re.IGNORECASE | re.DOTALL)
_LASTMOD_RE = re.compile(r"<lastmod>\s*(.*?)\s*</lastmod>", re.IGNORECASE | re.DOTALL)


def _origin_from_property(prop: str) -> str:
    """Fallback origin when site/sitemap.xml is unreadable."""
    if prop.startswith("sc-domain:"):
        return f"https://www.{prop.split(':', 1)[1].strip('/')}/"
    return prop if prop.endswith("/") else prop + "/"


def _core_inspect_urls(root: Path, prop: str) -> list[str]:
    """The fixed, deterministic core set — most-important-first, capped at 12.

    Origin and the two most recent blog posts come from ``site/sitemap.xml`` when
    it is readable; otherwise the origin is derived from the property string and
    the blog posts are simply omitted (never guessed).

    'Most recent' = <lastmod> descending, with the URL as a deterministic
    tie-break — this repo's sitemap emits blog entries WITHOUT a lastmod, so the
    tie-break is the operative ordering, and it must not depend on file mtimes
    (a fresh CI checkout rewrites those).
    """
    sitemap = root / "site" / "sitemap.xml"
    origin = _origin_from_property(prop)
    blog: list[tuple[str, str]] = []

    try:
        text = sitemap.read_text(encoding="utf-8")
    except OSError:
        text = ""

    if text:
        first = _LOC_RE.search(text)
        if first:
            loc = first.group(1)
            m = re.match(r"(https?://[^/]+)/?", loc)
            if m:
                origin = m.group(1) + "/"
        for block in _URL_BLOCK_RE.findall(text):
            loc_m = _LOC_RE.search(block)
            if not loc_m:
                continue
            loc = loc_m.group(1)
            if "/blog/" not in loc or loc.endswith("/blog/index.html"):
                continue
            lm_m = _LASTMOD_RE.search(block)
            blog.append((lm_m.group(1) if lm_m else "", loc))

    urls = [origin + path for path in _CORE_INSPECT_PATHS]
    for _, loc in sorted(blog, reverse=True)[:_RECENT_BLOG_COUNT]:
        if loc not in urls:
            urls.append(loc)
    return urls[:_MAX_INSPECT_URLS]


# --- artifact + annotations ------------------------------------------------


def _index_status_doc(
    *,
    as_of_iso: str,
    prop: str,
    available: bool,
    reason: str | None,
    sitemaps: dict | None = None,
    urls: list[dict] | None = None,
    identity: dict | None = None,
) -> dict:
    return {
        "schema": "gsc_index_status.v1",
        "as_of": as_of_iso,
        "available": available,
        "reason": reason,
        "property": prop,
        "service_account": identity or {},
        "sitemaps": sitemaps or {"sitemaps": [], "never_downloaded": [], "count": 0},
        "urls": urls or [],
    }


def collect_index_status(
    root: Path,
    *,
    info: dict,
    prop: str,
    as_of_iso: str,
    token: str | None = None,
    pace_s: float = _INSPECT_PACE_S,
) -> dict:
    """Build the gsc_index_status.v1 document.  Fail-soft: never raises.

    The sitemap leg and the URL leg fail independently — a sitemaps 500 must not
    cost us the inspection answers, and vice versa.
    """
    identity = sa_identity(info)
    sitemaps: dict = {"sitemaps": [], "never_downloaded": [], "count": 0}
    reasons: list[str] = []

    try:
        token = _token_for(info, token)
    except Exception as exc:  # noqa: BLE001
        return _index_status_doc(
            as_of_iso=as_of_iso, prop=prop, available=False,
            reason=_scrub_secret(_one_line(exc, 300), info), identity=identity,
        )

    try:
        sitemaps = fetch_sitemaps(info, prop, token=token)
    except Exception as exc:  # noqa: BLE001
        msg = _scrub_secret(_one_line(exc, 200), info)
        sitemaps["error"] = msg
        reasons.append(f"sitemaps: {msg}")
        log.warning("gsc: sitemaps fetch failed: %s", msg)

    try:
        urls = inspect_urls(
            info, prop, _core_inspect_urls(root, prop), token=token, pace_s=pace_s
        )
    except Exception as exc:  # noqa: BLE001
        msg = _scrub_secret(_one_line(exc, 200), info)
        reasons.append(f"url inspection: {msg}")
        log.warning("gsc: url inspection sweep failed: %s", msg)
        urls = []

    # Available when at least one leg produced something to read.
    available = bool(urls) or bool(sitemaps.get("sitemaps"))
    return _index_status_doc(
        as_of_iso=as_of_iso, prop=prop, available=available,
        reason="; ".join(reasons) if reasons else None,
        sitemaps=sitemaps, urls=urls, identity=identity,
    )


def _sitemap_last_downloaded(doc: dict) -> str:
    """Most recent lastDownloaded across sitemaps, or 'never'."""
    stamps = [
        s.get("lastDownloaded") for s in doc.get("sitemaps", {}).get("sitemaps", [])
        if s.get("lastDownloaded")
    ]
    return max(stamps) if stamps else "never"


def _emit_index_annotations(doc: dict) -> None:
    """GitHub annotation for the index-status sweep.

    Annotations MUST start their line — a logger prefixes the line with its level
    and GitHub silently drops the command (see tests/test_gh_annotation_line_start.py).
    Bare print, flush=True because stdout is block-buffered when piped in CI.
    """
    urls = doc.get("urls") or []
    inspected = [u for u in urls if not u.get("error")]
    indexed = [u for u in inspected if u.get("indexed")]
    last_dl = _sitemap_last_downloaded(doc)

    if not doc.get("available"):
        print(
            f"::warning title=gsc-index-status::index diagnostics unavailable: "
            f"{doc.get('reason') or 'unknown'}",
            flush=True,
        )
        return

    if inspected and not indexed:
        print(
            f"::warning title=gsc-index-status::0 of {len(inspected)} inspected "
            f"URLs are indexed on {doc.get('property')} — sitemap last downloaded: "
            f"{last_dl}",
            flush=True,
        )
        return

    print(
        f"::notice title=gsc-index-status::{len(indexed)} of {len(inspected)} "
        f"inspected URLs indexed on {doc.get('property')} — sitemap last "
        f"downloaded: {last_dl}",
        flush=True,
    )


def _print_index_summary(doc: dict) -> None:
    """Readable operator summary of the index-status sweep."""
    print("\n=== GSC Index Status ===")
    print(f"available : {doc.get('available')}")
    if doc.get("reason"):
        print(f"reason    : {doc.get('reason')}")
    identity = doc.get("service_account") or {}
    if identity.get("client_email"):
        print(f"service_ac: {identity['client_email']}")

    sm = doc.get("sitemaps") or {}
    entries = sm.get("sitemaps") or []
    print(f"sitemaps  : {len(entries)}")
    for s in entries:
        print(
            f"  {s.get('path')}\n"
            f"    submitted={s.get('lastSubmitted')} "
            f"downloaded={s.get('lastDownloaded') or 'NEVER'} "
            f"pending={s.get('isPending')} "
            f"warnings={s.get('warnings')} errors={s.get('errors')} "
            f"urls_submitted={s.get('submitted')} urls_indexed={s.get('indexed')}"
        )
    for path in sm.get("never_downloaded") or []:
        print(f"  !! never downloaded by Google: {path}")
    if sm.get("error"):
        print(f"  !! sitemaps leg failed: {sm['error']}")

    urls = doc.get("urls") or []
    inspected = [u for u in urls if not u.get("error")]
    indexed = [u for u in inspected if u.get("indexed")]
    print(f"\nindexed   : {len(indexed)} of {len(inspected)} inspected "
          f"({len(urls) - len(inspected)} errored)")
    for u in urls:
        if u.get("error"):
            print(f"  ERR  {u.get('url')} — {u['error']}")
            continue
        mark = "IDX " if u.get("indexed") else "NOT "
        print(
            f"  {mark} {u.get('url')}\n"
            f"       coverage={u.get('coverageState')} "
            f"last_crawl={u.get('lastCrawlTime') or 'never'} "
            f"fetch={u.get('pageFetchState')} robots={u.get('robotsTxtState')}"
        )


# ---------------------------------------------------------------------------
# Parquet append-dedupe + cap
# ---------------------------------------------------------------------------


def _load_existing_parquet(path: Path) -> "pd.DataFrame | None":
    """Load existing parquet if present; return None on any error."""
    if not path.exists():
        return None
    try:
        import pandas as pd
        return pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return None


def _build_parquet(
    new_rows: list[dict],
    existing: "pd.DataFrame | None",
    search_type: str,
    cutoff_date: "date",
) -> "pd.DataFrame":
    """Merge new_rows with existing, deduplicate, sort, cap at _PAGE_CAP_MONTHS.

    Dedup key: (date, page, query, country, device).
    Cap: drop rows older than cutoff_date (16 months prior to as_of).
    """
    import pandas as pd

    df_new = pd.DataFrame(new_rows)
    if df_new.empty:
        df_new = pd.DataFrame(columns=[
            "date", "page", "query", "country", "device",
            "clicks", "impressions", "ctr", "position", "is_brand", "search_type",
        ])
    else:
        df_new["is_brand"] = df_new.get("query", pd.Series(dtype=str)).fillna("").apply(
            lambda q: bool(_BRAND_RE.search(q))
        )
        df_new["search_type"] = search_type

    frames = [existing, df_new] if existing is not None else [df_new]
    df = pd.concat(frames, ignore_index=True)

    if df.empty:
        return df

    # Coerce date to string (YYYY-MM-DD) for consistent dedup.
    df["date"] = df["date"].astype(str)

    dedup_keys = ["date", "page", "query", "country", "device"]
    present_keys = [k for k in dedup_keys if k in df.columns]
    if present_keys:
        df = df.drop_duplicates(subset=present_keys, keep="last")

    # 16-month cap.
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")
    df = df[df["date"] >= cutoff_str]

    # Sort for stable output.
    sort_cols = [c for c in ["date", "page", "query", "country", "device"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------


def _build_scorecard(
    df: "pd.DataFrame",
    as_of: str,
    window: dict,
) -> dict:
    """Build page_family_scorecard.json from the full parquet dataframe."""
    from engine.marketing.seo_director import classify_page
    from urllib.parse import urlparse

    def _family(page: str) -> str:
        try:
            path = urlparse(page).path.lstrip("/")
            stem = Path(path).stem if path else "index"
            # Handle stocks sub-path
            if path.startswith("stocks/"):
                return "stocks"
            if path.startswith("products/"):
                return "products"
            return classify_page(stem)
        except Exception:  # noqa: BLE001
            return "core"

    families: dict[str, dict] = {}
    brand_clicks = 0
    brand_impr = 0
    nonbrand_clicks = 0
    nonbrand_impr = 0

    if df.empty:
        return {
            "schema": "gsc_scorecard.v1",
            "as_of": as_of,
            "window": window,
            "families": {},
            "brand_split": {
                "brand": {"clicks": 0, "impressions": 0},
                "non_brand": {"clicks": 0, "impressions": 0},
            },
        }

    import pandas as pd

    for page, page_df in df.groupby("page", sort=False):
        fam = _family(str(page))
        clicks = int(page_df["clicks"].sum())
        impr = int(page_df["impressions"].sum())
        total_clicks = clicks  # per-page totals already summed; ctr is weighted below
        n = len(page_df)
        ctr = float(page_df["ctr"].mean()) if n > 0 else 0.0
        avg_pos = float(page_df["position"].mean()) if n > 0 else 0.0

        if fam not in families:
            families[fam] = {
                "clicks": 0, "impressions": 0, "ctr": 0.0,
                "avg_position": 0.0, "_impr_sum": 0.0,
                "_pos_weighted": 0.0, "top_pages": [],
            }
        families[fam]["clicks"] += clicks
        families[fam]["impressions"] += impr
        # Impression-weighted avg ctr and position accumulators
        families[fam]["_impr_sum"] += impr
        families[fam]["_pos_weighted"] += avg_pos * impr

        # Track top_pages (up to 5 by clicks)
        families[fam]["top_pages"].append({
            "page": str(page), "clicks": clicks, "impressions": impr
        })

    # Finalize averages, sort top_pages, strip internal keys.
    for fam, data in families.items():
        impr_sum = data.pop("_impr_sum", 0.0) or 1.0
        pos_weighted = data.pop("_pos_weighted", 0.0)
        data["avg_position"] = round(pos_weighted / impr_sum, 2)
        if data["impressions"] > 0:
            data["ctr"] = round(data["clicks"] / data["impressions"], 4)
        data["top_pages"] = sorted(
            data["top_pages"], key=lambda x: x["clicks"], reverse=True
        )[:5]

    # Brand split.
    if "is_brand" in df.columns:
        brand_df = df[df["is_brand"] == True]  # noqa: E712
        nonbrand_df = df[df["is_brand"] == False]  # noqa: E712
        brand_clicks = int(brand_df["clicks"].sum())
        brand_impr = int(brand_df["impressions"].sum())
        nonbrand_clicks = int(nonbrand_df["clicks"].sum())
        nonbrand_impr = int(nonbrand_df["impressions"].sum())

    return {
        "schema": "gsc_scorecard.v1",
        "as_of": as_of,
        "window": window,
        "families": {
            fam: {
                "clicks": d["clicks"],
                "impressions": d["impressions"],
                "ctr": d["ctr"],
                "avg_position": d["avg_position"],
                "top_pages": d["top_pages"],
            }
            for fam, d in families.items()
        },
        "brand_split": {
            "brand": {"clicks": brand_clicks, "impressions": brand_impr},
            "non_brand": {"clicks": nonbrand_clicks, "impressions": nonbrand_impr},
        },
    }


# ---------------------------------------------------------------------------
# Query gaps
# ---------------------------------------------------------------------------


def _build_query_gaps(df: "pd.DataFrame", as_of: str, window: dict) -> dict:
    """Build query_gaps.json from the full parquet dataframe.

    Gaps = non-brand queries with impressions >= _GAP_MIN_IMPRESSIONS in window AND
    (ctr < _GAP_MAX_CTR OR position in [_GAP_POS_LOW, _GAP_POS_HIGH]).
    Sorted by impressions descending, capped at _GAP_LIMIT.
    """
    if df.empty or "query" not in df.columns:
        return {
            "schema": "gsc_gaps.v1",
            "as_of": as_of,
            "window": window,
            "gaps": [],
        }

    import pandas as pd

    # Filter non-brand.
    if "is_brand" in df.columns:
        df_nb = df[df["is_brand"] == False].copy()  # noqa: E712
    else:
        df_nb = df.copy()

    if df_nb.empty:
        return {"schema": "gsc_gaps.v1", "as_of": as_of, "window": window, "gaps": []}

    # Aggregate by query (impression-weighted position; sum clicks/impressions).
    agg = df_nb.groupby("query", sort=False).agg(
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        _pos_w=("position", lambda s: (s * df_nb.loc[s.index, "impressions"]).sum()),
        _impr_sum=("impressions", "sum"),
    ).reset_index()

    agg["ctr"] = agg["clicks"] / agg["impressions"].replace(0, float("nan"))
    agg["avg_position"] = agg["_pos_w"] / agg["_impr_sum"].replace(0, float("nan"))

    # Apply gap heuristics.
    mask = (
        (agg["impressions"] >= _GAP_MIN_IMPRESSIONS) &
        (
            (agg["ctr"] < _GAP_MAX_CTR) |
            (
                (agg["avg_position"] >= _GAP_POS_LOW) &
                (agg["avg_position"] <= _GAP_POS_HIGH)
            )
        )
    )
    gaps_df = agg[mask].sort_values("impressions", ascending=False).head(_GAP_LIMIT)

    # Best page per query (by clicks in this window).
    best_page_map: dict[str, str] = {}
    if "page" in df_nb.columns:
        page_agg = df_nb.groupby(["query", "page"], sort=False)["clicks"].sum().reset_index()
        for q, grp in page_agg.groupby("query", sort=False):
            best = grp.sort_values("clicks", ascending=False).iloc[0]["page"]
            best_page_map[str(q)] = str(best)

    gaps: list[dict] = []
    for _, row in gaps_df.iterrows():
        q = str(row["query"])
        ctr_val = float(row["ctr"]) if pd.notna(row["ctr"]) else 0.0
        pos_val = float(row["avg_position"]) if pd.notna(row["avg_position"]) else 0.0

        # Classify reason (both conditions may apply; pick primary).
        if ctr_val < _GAP_MAX_CTR:
            reason = "high_impressions_low_ctr"
        else:
            reason = "position_11_30"

        gaps.append({
            "query": q,
            "impressions": int(row["impressions"]),
            "clicks": int(row["clicks"]),
            "ctr": round(ctr_val, 4),
            "avg_position": round(pos_val, 2),
            "best_page": best_page_map.get(q, ""),
            "reason": reason,
        })

    return {
        "schema": "gsc_gaps.v1",
        "as_of": as_of,
        "window": window,
        "gaps": gaps,
    }


# ---------------------------------------------------------------------------
# Public: run()
# ---------------------------------------------------------------------------


def _state_for_disk(state: dict) -> dict:
    """The state dict minus the nested index-status doc (own artifact)."""
    return {k: v for k, v in state.items() if k != "index_status"}


def run(
    root: Path,
    *,
    creds_path: str | Path | None = None,
    days: int = 28,
    as_of: date | None = None,
    write: bool = True,
    index_status: bool = True,
    pace_s: float = _INSPECT_PACE_S,
) -> dict:
    """Disk-level wrapper: resolve credentials, fetch, aggregate, write artifacts.

    Args:
        root:         Repo root path.
        creds_path:   Explicit path to service-account JSON key (optional).
        days:         Number of days back from as_of to fetch.
        as_of:        Reference date (default: today UTC).
        write:        If False, skip all disk writes (dry-run).
        index_status: Run the sitemap + URL-inspection diagnostics sweep.
        pace_s:       Sleep between URL-inspection calls (quota pacing).

    Returns:
        State dict matching gsc_state.v1 schema, with the index-status document
        attached under ``index_status`` (also written as its own artifact).
    """
    import pandas as pd

    if as_of is None:
        as_of = datetime.now(timezone.utc).date()

    as_of_iso = as_of.strftime("%Y-%m-%d")
    start_date = (as_of - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    end_date = as_of_iso
    window = {"start": start_date, "end": end_date}

    prop = os.environ.get("GSC_PROPERTY", _DEFAULT_PROPERTY)

    seo_dir = root / _ARTIFACTS_REL

    def _state(
        available: bool,
        reason: str | None,
        rows_fetched: int = 0,
        identity: dict | None = None,
    ) -> dict:
        return {
            "schema": "gsc_state.v1",
            "as_of": as_of_iso,
            "available": available,
            "reason": reason,
            "property": prop,
            "service_account": identity or {},
            "window": window,
            "rows_fetched": rows_fetched,
            "rows_may_be_incomplete": True,
        }

    def _finish(state: dict, idx_doc: dict) -> dict:
        """Attach + persist the index-status doc, then return the state.

        ``index_status`` rides on the RETURNED dict for callers/tests but is not
        duplicated into search_console_state.json — it has its own artifact, and
        one fact wants one writer.
        """
        state["index_status"] = idx_doc
        if write:
            for path, obj in (
                (seo_dir / _STATE_FILE, _state_for_disk(state)),
                (seo_dir / _INDEX_STATUS_FILE, idx_doc),
            ):
                try:
                    _write_json_atomic(path, obj)
                except Exception as exc:  # noqa: BLE001
                    log.error("gsc: %s write failed: %s", path.name, exc)
        return state

    # --- credential resolution: parse + validate in one shot ---
    info, cred_error = load_sa_info(creds_path=creds_path)

    if info is None:
        reason = cred_error or "credentials not configured"
        if reason != "credentials not configured":
            # Malformed beats absent: the operator must FIX the secret, and the
            # precise cause is the whole value of this branch.
            print(
                f"::warning title=gsc-credentials-malformed::{reason}",
                flush=True,
            )
        state = _state(False, reason)
        return _finish(state, _index_status_doc(
            as_of_iso=as_of_iso, prop=prop, available=False, reason=reason,
        ))

    identity = sa_identity(info)

    # --- check google-auth import ---
    try:
        import google.oauth2.service_account  # noqa: F401
        import google.auth.transport.requests  # noqa: F401
    except ImportError:
        reason = "google-auth not installed (pip install google-auth)"
        state = _state(False, reason, identity=identity)
        return _finish(state, _index_status_doc(
            as_of_iso=as_of_iso, prop=prop, available=False, reason=reason,
            identity=identity,
        ))

    # --- fetch ---
    rows: list[dict] = []
    fetch_error: str | None = None
    fetch_status: int | None = None
    try:
        rows = fetch_search_analytics(info, prop, start_date, end_date)
    except GscApiError as exc:
        fetch_status = exc.status
        fetch_error = _scrub_secret(_one_line(exc, 300), info)
        log.warning("gsc: fetch failed (HTTP %s): %s", exc.status, fetch_error)
    except Exception as exc:  # noqa: BLE001
        fetch_error = _scrub_secret(_one_line(exc, 300), info)
        log.warning("gsc: fetch failed: %s", fetch_error)

    if fetch_error is not None:
        who = identity.get("client_email", "the service account")
        if fetch_status == 403:
            # By far the most likely first failure once the secret is right, and
            # its fix is a Search Console UI action — so name it, don't hide it
            # behind a generic "api error".
            reason = (
                f"service account {who} lacks access to {prop} — "
                f"add it as a user in Search Console"
            )
            print(f"::warning title=gsc-no-access::{reason}", flush=True)
        elif fetch_status == 404:
            reason = (
                f"property {prop} not found — check it is the DOMAIN property "
                f"{_DEFAULT_PROPERTY}"
            )
            print(f"::warning title=gsc-property-not-found::{reason}", flush=True)
        else:
            reason = f"api error: {fetch_error[:400]}"

        state = _state(False, reason, identity=identity)
        # An auth/property failure hits every endpoint identically — re-running
        # 12 inspections to collect 12 copies of the same 403 buys nothing.
        if index_status and fetch_status not in (401, 403, 404):
            idx_doc = collect_index_status(
                root, info=info, prop=prop, as_of_iso=as_of_iso, pace_s=pace_s
            )
            _emit_index_annotations(idx_doc)
        else:
            idx_doc = _index_status_doc(
                as_of_iso=as_of_iso, prop=prop, available=False, reason=reason,
                identity=identity,
            )
        return _finish(state, idx_doc)

    # --- success path ---
    state = _state(True, None, rows_fetched=len(rows), identity=identity)

    if index_status:
        idx_doc = collect_index_status(
            root, info=info, prop=prop, as_of_iso=as_of_iso, pace_s=pace_s
        )
        _emit_index_annotations(idx_doc)
    else:
        idx_doc = _index_status_doc(
            as_of_iso=as_of_iso, prop=prop, available=False,
            reason="index diagnostics disabled", identity=identity,
        )
    state["index_status"] = idx_doc

    if write:
        try:
            # 1. State file (always first).
            _write_json_atomic(seo_dir / _STATE_FILE, _state_for_disk(state))

            # 2. Index-status diagnostics.
            _write_json_atomic(seo_dir / _INDEX_STATUS_FILE, idx_doc)

            # 3. Parquet: append-dedupe.
            cutoff = as_of - timedelta(days=_PAGE_CAP_MONTHS * 30)
            existing_df = _load_existing_parquet(seo_dir / _DAILY_FILE)
            df = _build_parquet(rows, existing_df, "web", cutoff)
            if not df.empty:
                _write_parquet_atomic(seo_dir / _DAILY_FILE, df)

            # 4. Scorecard.
            scorecard = _build_scorecard(df, as_of_iso, window)
            _write_json_atomic(seo_dir / _SCORECARD_FILE, scorecard)

            # 5. Query gaps.
            gaps = _build_query_gaps(df, as_of_iso, window)
            _write_json_atomic(seo_dir / _GAPS_FILE, gaps)

        except Exception as exc:  # noqa: BLE001
            log.error("gsc: artifact write failed: %s", exc)
    else:
        # dry-run: still build the in-memory aggregates so the caller sees them.
        cutoff = as_of - timedelta(days=_PAGE_CAP_MONTHS * 30)
        existing_df = _load_existing_parquet(seo_dir / _DAILY_FILE)
        df = _build_parquet(rows, existing_df, "web", cutoff)

    return state


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_summary(state: dict, seo_dir: Path | None = None) -> None:
    print("\n=== GSC Search Console Ingest ===")
    print(f"as_of     : {state.get('as_of')}")
    print(f"available : {state.get('available')}")
    if not state.get("available"):
        print(f"reason    : {state.get('reason')}")
    print(f"property  : {state.get('property')}")
    identity = state.get("service_account") or {}
    if identity.get("client_email"):
        # Non-secret on purpose: the operator needs to know WHICH service
        # account to grant Search Console access to.
        print(f"service_ac: {identity['client_email']}")
    window = state.get("window", {})
    print(f"window    : {window.get('start')} -> {window.get('end')}")
    print(f"rows      : {state.get('rows_fetched', 0)}")
    print(f"incomplete: {state.get('rows_may_be_incomplete', True)} (API returns top rows only)")

    idx_doc = state.get("index_status")
    if isinstance(idx_doc, dict):
        _print_index_summary(idx_doc)

    if seo_dir and (seo_dir / _SCORECARD_FILE).exists():
        try:
            sc = json.loads((seo_dir / _SCORECARD_FILE).read_text(encoding="utf-8"))
            families = sc.get("families", {})
            if families:
                print("\nPage families:")
                for fam, data in sorted(families.items()):
                    print(f"  {fam:<12} clicks={data.get('clicks',0):>6} "
                          f"impr={data.get('impressions',0):>8} "
                          f"pos={data.get('avg_position',0):.1f}")
            brand_split = sc.get("brand_split", {})
            if brand_split:
                b = brand_split.get("brand", {})
                nb = brand_split.get("non_brand", {})
                print(f"\nBrand split: brand={b.get('clicks',0)} clicks / "
                      f"non-brand={nb.get('clicks',0)} clicks")
        except Exception:  # noqa: BLE001
            pass

    if seo_dir and (seo_dir / _GAPS_FILE).exists():
        try:
            gaps_doc = json.loads((seo_dir / _GAPS_FILE).read_text(encoding="utf-8"))
            n_gaps = len(gaps_doc.get("gaps", []))
            print(f"\nQuery gaps: {n_gaps}")
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="GSC Search Console ingestion adapter"
    )
    parser.add_argument("--root", default=".", help="Repo root (default: .)")
    parser.add_argument("--days", type=int, default=28, help="Days back to fetch (default: 28)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch without writing artifacts")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    seo_dir = root / _ARTIFACTS_REL

    try:
        state = run(root, days=args.days, write=not args.dry_run)
        _print_summary(state, seo_dir if not args.dry_run else None)
    except Exception as exc:  # noqa: BLE001
        print(f"::error:: gsc_search_console crashed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    # exit 0 even when unavailable


if __name__ == "__main__":
    main()
