"""engine.marketing.seo_search_console — Google Search Console ingestion adapter.

MKT-SEO-07 W0  (Beacon dept).  Wraps the Search Analytics REST API (v3) using
raw HTTP + google-auth bearer tokens.  Fully offline when credentials absent —
writes an explicit unavailable state artifact, never a healthy zero.

Public API (all fail-soft — no public function raises):
  fetch_search_analytics(creds_path, prop, start_date, end_date, ...) -> list[dict]
  run(root, *, creds_path=None, days=28, as_of=None, write=True) -> dict

Artifacts written under data/marketing/seo/:
  search_console_state.json     — always (available bool + metadata)
  search_console_daily.parquet  — only when available; append-dedupe + 16-month cap
  page_family_scorecard.json    — only when available
  query_gaps.json               — only when available

Credential resolution (checked in order):
  1. explicit creds_path param
  2. env GOOGLE_APPLICATION_CREDENTIALS (path to JSON key)
  3. env GSC_SA_JSON (raw JSON string — written to tmp file chmod 600, deleted after)

CLI:
  python -m engine.marketing.seo_search_console --root . [--days 28] [--dry-run]
  Prints compact summary.  exit 0 even when unavailable; exit 1 only on crash.

Dependency: google-auth (in requirements.txt) for service-account bearer tokens.
Soft-import: if not installed, writes unavailable state with reason.

SECURITY: Token/key material is NEVER logged, never written to any artifact, never
echoed to stdout.  The tmp file for GSC_SA_JSON is chmod 600 and deleted in finally.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import stat
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote as _url_quote

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GSC_API_BASE = "https://www.googleapis.com/webmasters/v3/sites"
_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
_DEFAULT_PROPERTY = "sc-domain:mastermind-x.com"
_ROW_LIMIT = 25_000
_PAGE_CAP_MONTHS = 16   # cap parquet to last 16 months of dates

_ARTIFACTS_REL = Path("data") / "marketing" / "seo"
_STATE_FILE = "search_console_state.json"
_DAILY_FILE = "search_console_daily.parquet"
_SCORECARD_FILE = "page_family_scorecard.json"
_GAPS_FILE = "query_gaps.json"

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
# Credential resolution
# ---------------------------------------------------------------------------


def _resolve_creds(creds_path: str | Path | None) -> tuple[str | None, str | None]:
    """Return (path_to_json_key, tmp_path_to_delete_after) or (None, None).

    Checks in order:
      1. explicit creds_path param
      2. env GOOGLE_APPLICATION_CREDENTIALS (path)
      3. env GSC_SA_JSON (raw JSON → tmp file chmod 600)

    SECURITY: Never logs key material.  Caller is responsible for deleting tmp_path.
    """
    if creds_path is not None:
        p = str(creds_path)
        if os.path.isfile(p):
            return p, None
        return None, None

    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if env_path and os.path.isfile(env_path):
        return env_path, None

    raw_json = os.environ.get("GSC_SA_JSON", "").strip()
    if raw_json:
        # Write to tmp file with 0600 perms so google-auth can read it safely.
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix=".gsc_sa_")
        try:
            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(raw_json)
            return tmp_path, tmp_path
        except Exception:  # noqa: BLE001
            try:
                os.unlink(tmp_path)
            except Exception:  # noqa: BLE001
                pass
            return None, None

    return None, None


# ---------------------------------------------------------------------------
# Bearer-token helper using google-auth
# ---------------------------------------------------------------------------


def _get_bearer_token(key_file: str) -> str:
    """Return a valid OAuth2 bearer token for the GSC read-only scope.

    Raises ImportError if google-auth is not installed, or google.auth errors.
    SECURITY: token is returned as a string, never logged.
    """
    from google.oauth2 import service_account  # type: ignore
    from google.auth.transport.requests import Request  # type: ignore

    credentials = service_account.Credentials.from_service_account_file(
        key_file, scopes=_SCOPES
    )
    credentials.refresh(Request())
    return credentials.token  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# REST call helpers
# ---------------------------------------------------------------------------


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
    Raises on HTTP errors.
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
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public: fetch_search_analytics
# ---------------------------------------------------------------------------


def fetch_search_analytics(
    creds_path: str | Path,
    prop: str,
    start_date: str,
    end_date: str,
    *,
    dimensions: tuple[str, ...] = ("date", "page", "query", "country", "device"),
    search_type: str = "web",
    row_limit: int = _ROW_LIMIT,
) -> list[dict]:
    """Fetch search analytics rows for a property and date range via REST pagination.

    Args:
        creds_path:  Path to service-account JSON key file.
        prop:        GSC property string (e.g. 'sc-domain:mastermind-x.com').
        start_date:  ISO date string 'YYYY-MM-DD'.
        end_date:    ISO date string 'YYYY-MM-DD'.
        dimensions:  Ordered tuple of dimension names.
        search_type: 'web' | 'image' | 'video' | 'news'.
        row_limit:   Max rows per page request (API max 25000).

    Returns:
        List of row dicts with keys = dimensions + ['clicks','impressions','ctr','position'].
        May be incomplete (API returns top rows by impressions, not all rows).

    Raises:
        ImportError: if google-auth is not installed.
        requests.HTTPError: on API error.
        Exception: on auth error.
    """
    token = _get_bearer_token(str(creds_path))

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


def run(
    root: Path,
    *,
    creds_path: str | Path | None = None,
    days: int = 28,
    as_of: date | None = None,
    write: bool = True,
) -> dict:
    """Disk-level wrapper: resolve credentials, fetch, aggregate, write artifacts.

    Args:
        root:       Repo root path.
        creds_path: Explicit path to service-account JSON key (optional).
        days:       Number of days back from as_of to fetch.
        as_of:      Reference date (default: today UTC).
        write:      If False, skip all disk writes (dry-run).

    Returns:
        State dict matching gsc_state.v1 schema.
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

    tmp_to_delete: str | None = None

    def _state(available: bool, reason: str | None, rows_fetched: int = 0) -> dict:
        return {
            "schema": "gsc_state.v1",
            "as_of": as_of_iso,
            "available": available,
            "reason": reason,
            "property": prop,
            "window": window,
            "rows_fetched": rows_fetched,
            "rows_may_be_incomplete": True,
        }

    # --- credential resolution ---
    resolved_path, tmp_to_delete = _resolve_creds(creds_path)

    if resolved_path is None:
        state = _state(False, "credentials not configured")
        if write:
            try:
                _write_json_atomic(seo_dir / _STATE_FILE, state)
            except Exception as exc:  # noqa: BLE001
                log.error("gsc: state write failed: %s", exc)
        return state

    # --- check google-auth import ---
    try:
        import google.oauth2.service_account  # noqa: F401
        import google.auth.transport.requests  # noqa: F401
    except ImportError:
        state = _state(False, "google-auth not installed (pip install google-auth)")
        if write:
            try:
                _write_json_atomic(seo_dir / _STATE_FILE, state)
            except Exception as exc:  # noqa: BLE001
                log.error("gsc: state write failed: %s", exc)
        if tmp_to_delete:
            try:
                os.unlink(tmp_to_delete)
            except Exception:  # noqa: BLE001
                pass
        return state

    # --- fetch ---
    rows: list[dict] = []
    fetch_error: str | None = None
    try:
        rows = fetch_search_analytics(
            resolved_path, prop, start_date, end_date,
        )
    except Exception as exc:  # noqa: BLE001
        fetch_error = str(exc)
        log.warning("gsc: fetch failed: %s", exc)
    finally:
        # Always delete the tmp credentials file.
        if tmp_to_delete:
            try:
                os.unlink(tmp_to_delete)
            except Exception:  # noqa: BLE001
                pass

    if fetch_error is not None:
        # Sanitize: strip any token/key material from the error string (paranoid).
        safe_error = re.sub(r"(token|key|secret|password|credential)[=:]\S+",
                            r"\1=<redacted>", fetch_error, flags=re.IGNORECASE)
        state = _state(False, f"api error: {safe_error[:400]}")
        if write:
            try:
                _write_json_atomic(seo_dir / _STATE_FILE, state)
            except Exception as exc:  # noqa: BLE001
                log.error("gsc: state write failed: %s", exc)
        return state

    # --- success path ---
    state = _state(True, None, rows_fetched=len(rows))

    if write:
        try:
            # 1. State file (always first).
            _write_json_atomic(seo_dir / _STATE_FILE, state)

            # 2. Parquet: append-dedupe.
            cutoff = as_of - timedelta(days=_PAGE_CAP_MONTHS * 30)
            existing_df = _load_existing_parquet(seo_dir / _DAILY_FILE)
            df = _build_parquet(rows, existing_df, "web", cutoff)
            if not df.empty:
                _write_parquet_atomic(seo_dir / _DAILY_FILE, df)

            # 3. Scorecard.
            scorecard = _build_scorecard(df, as_of_iso, window)
            _write_json_atomic(seo_dir / _SCORECARD_FILE, scorecard)

            # 4. Query gaps.
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
    window = state.get("window", {})
    print(f"window    : {window.get('start')} -> {window.get('end')}")
    print(f"rows      : {state.get('rows_fetched', 0)}")
    print(f"incomplete: {state.get('rows_may_be_incomplete', True)} (API returns top rows only)")

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
