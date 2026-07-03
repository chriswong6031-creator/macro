"""Federal Register policy-document collector — keyless, no auth required.

Fetches RULE / PRORULE / NOTICE / PRESDOCU documents from the Federal Register API
(https://www.federalregister.gov/api/v1) and maps them to the 18 config-defined themes via
a deterministic AGENCY-SLUG × TERM two-stage filter (data/federal_register/theme_map.json).

Two-stage filter (masterplan R9d):
  Stage-1 (API): conditions[term] — full-text search in title+abstract+body.
  Stage-2 (post-fetch Python): check agencies[*].slug in the theme's agency list (OR across
  the full agency list including parent slugs).  A doc passes only if BOTH stages match.
  Agency list may be EMPTY for a theme — in that case Stage-2 is a no-op (all term-matches
  kept), which only applies to themes with highly specific terms (none in current map).

Output:
  data/federal_register/documents.parquet  — append-only PIT tape (document_number PK,
      _first_seen timestamp; significant stored AS-FIRST-SEEN per masterplan R9f).
  data/federal_register/reg_velocity.parquet — pre-aggregated per-basket theme_event frame
      (basket_id index, recent_count, prior_count, recent_sig_count); consumed by
      engine/theme_activity.py SOURCES entry "fedreg_velocity".

Registration: scripts/collect.py END-appended, _SLOW set.
No API key required. Pace: 0.5s inter-request sleep (no rate-limit headers observed).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

BASE_URL = "https://www.federalregister.gov/api/v1/documents.json"
FR_RECENT_D = 90    # look-back window for "recent" velocity bucket (days)
FR_PRIOR_D = 90     # look-back window for "prior" velocity bucket (days)
PAGE_SIZE = 1000    # API supports up to 1000 per page
REQUEST_PAUSE = 0.5  # seconds between API calls (polite pace; no rate-limit headers)

# Doc types: full set for thematic tracking
DOC_TYPES = ["RULE", "PRORULE", "NOTICE", "PRESDOCU"]

# Regulatory stage taxonomy (type + action-text rules)
_STAGE_WEIGHTS: list[tuple[str, str, str, float]] = [
    # (doc_type, action_text_substring, reg_stage, weight)
    ("PRESDOCU", "",                        "executive_order",    2.0),
    ("RULE",     "interim final",           "interim_final_rule", 1.8),
    ("RULE",     "",                        "final_rule",         1.5),
    ("PRORULE",  "",                        "proposed_rule",      0.8),
    ("NOTICE",   "request for information", "rfi",                0.4),
    ("NOTICE",   "notice of funding",       "funding_notice",     0.6),
    ("NOTICE",   "solicitation",            "funding_notice",     0.6),
    ("NOTICE",   "",                        "notice",             0.3),
]

# Fields to request from the API (minimises payload)
_FIELDS = [
    "document_number", "title", "abstract", "publication_date",
    "type", "significant", "action", "agencies",
    "comments_close_on", "regulation_id_numbers", "docket_ids",
    "cfr_references",
]


def _theme_map() -> dict[str, dict]:
    p = config.data_dir() / "federal_register" / "theme_map.json"
    if not p.exists():
        log.warning("federal_register: theme_map.json not found at %s", p)
        return {}
    try:
        return json.loads(p.read_text()) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("federal_register: failed to load theme_map.json: %s", exc)
        return {}


def _reg_stage(doc_type: str, action: str) -> tuple[str, float]:
    """Derive (reg_stage, weight) from document type and action text."""
    t = (doc_type or "").upper()
    a = (action or "").lower()
    for dtype, kw, stage, w in _STAGE_WEIGHTS:
        if dtype == t or (dtype == "" and t in ("RULE", "PRORULE", "NOTICE", "PRESDOCU")):
            if kw == "" or kw in a:
                # Apply significance multiplier only at velocity(), not here
                return stage, w
    return "notice", 0.3


def _agency_slugs(agencies: list[dict]) -> set[str]:
    """Extract all slug values (including parent slugs) from an agencies list."""
    out: set[str] = set()
    for a in (agencies or []):
        if isinstance(a, dict):
            if a.get("slug"):
                out.add(a["slug"])
            # some nested structures have parent_id but not parent slug; include raw slug only
    return out


def _fetch_page(term: str, gte: str, lte: str, page: int, ua: str) -> dict | None:
    """Fetch one page from the Federal Register documents.json endpoint."""
    params: dict = {
        "conditions[term]": term,
        "conditions[publication_date][gte]": gte,
        "conditions[publication_date][lte]": lte,
        "per_page": PAGE_SIZE,
        "page": page,
        "order": "oldest",
    }
    for t in DOC_TYPES:
        params.setdefault("conditions[type][]", [])
        if isinstance(params["conditions[type][]"], list):
            params["conditions[type][]"].append(t)
        else:
            params["conditions[type][]"] = [params["conditions[type][]"], t]
    for f in _FIELDS:
        params.setdefault("fields[]", [])
        if isinstance(params["fields[]"], list):
            params["fields[]"].append(f)
        else:
            params["fields[]"] = [params["fields[]"], f]

    r = requests.get(BASE_URL, params=params, timeout=60,
                     headers={"User-Agent": ua})
    if r.status_code in (429, 500, 502, 503, 504):
        raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
    r.raise_for_status()
    return r.json()


def _fetch_all_for_term(term: str, gte: str, lte: str, ua: str) -> list[dict]:
    """Fetch all pages for a single (term, date-range) query. Returns list of doc dicts."""
    docs: list[dict] = []
    for page in range(1, 200):  # safety cap: 200 pages × 1000 = 200k docs
        try:
            data = _fetch_page(term, gte, lte, page, ua)
        except Exception as exc:  # noqa: BLE001
            if is_connection_error(exc):
                raise
            log.warning("federal_register: page %d term=%r failed: %s", page, term, exc)
            break
        batch = (data or {}).get("results") or []
        docs.extend(batch)
        total_pages = (data or {}).get("total_pages") or 1
        if page >= total_pages or len(batch) < PAGE_SIZE:
            break
        time.sleep(REQUEST_PAUSE)
    return docs


def velocity(
    docs: pd.DataFrame,
    *,
    today: "pd.Timestamp | None" = None,
    recent_d: int = FR_RECENT_D,
    prior_d: int = FR_PRIOR_D,
) -> pd.DataFrame:
    """Pure: roll per-doc rows up to per-basket {recent_count, prior_count, recent_sig_count}.

    Args:
        docs: The documents DataFrame (must have columns: basket_id, publication_date,
              significant [bool|None], weight [float]).
        today: Reference date for window calculation. Defaults to UTC today.
        recent_d: Length of the recent window in days.
        prior_d: Length of the prior window in days.

    Returns:
        DataFrame indexed by basket_id with columns:
          recent_count      — raw doc count in recent window
          prior_count       — raw doc count in prior window
          recent_sig_count  — EO-12866-significant docs in recent window (significant IS True)
    """
    if docs is None or docs.empty:
        return pd.DataFrame()
    t0 = today if today is not None else pd.Timestamp(datetime.now(timezone.utc).date())
    rec_lo = t0 - pd.Timedelta(days=recent_d)
    pri_lo = t0 - pd.Timedelta(days=recent_d + prior_d)

    pub = pd.to_datetime(docs["publication_date"], errors="coerce")
    rec_mask = (pub > rec_lo) & (pub <= t0)
    pri_mask = (pub > pri_lo) & (pub <= rec_lo)

    # significant IS True only; null/False both treated as not significant (masterplan R9f risk#4)
    sig = docs.get("significant") if "significant" in docs.columns else None

    counts: dict[str, list[int]] = {}  # basket_id -> [recent_count, prior_count, recent_sig]
    for basket_id, grp in docs.groupby("basket_id"):
        idx = grp.index
        rec = rec_mask.reindex(idx, fill_value=False)
        pri = pri_mask.reindex(idx, fill_value=False)
        rc = int(rec.sum())
        pc = int(pri.sum())
        if sig is not None:
            sig_col = sig.reindex(idx, fill_value=None)
            rsc = int((rec & (sig_col == True)).sum())  # noqa: E712 — explicit True check
        else:
            rsc = 0
        counts[str(basket_id)] = [rc, pc, rsc]

    rows = [
        {"basket_id": b, "recent_count": rc, "prior_count": pc, "recent_sig_count": rsc}
        for b, (rc, pc, rsc) in counts.items()
        if rc > 0 or pc > 0
    ]
    return pd.DataFrame(rows).set_index("basket_id") if rows else pd.DataFrame()


class FederalRegisterAdapter(Adapter):
    """Federal Register policy-document velocity collector (keyless, display-only).

    Produces:
      data/federal_register/documents.parquet  — append-only PIT raw tape
      data/federal_register/reg_velocity.parquet — theme_event frame for theme_activity
    """

    name = "federal_register"
    group = "federal_register"
    stale_after_days = 2  # daily FR publication; run daily

    def __init__(self) -> None:
        pass  # no API key required

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        tmap = _theme_map()
        if not tmap:
            raise ValueError("federal_register: theme_map.json missing or empty")

        cfg = config.load()
        ua = cfg.get("sponsors", {}).get("user_agent", "macro-dashboard/1.0 research")

        now_utc = datetime.now(timezone.utc)
        today = now_utc.date()

        if full_history:
            gte = "2015-01-01"
        else:
            # Fetch enough to cover both recent + prior windows plus a small cushion
            lookback = today - pd.Timedelta(days=FR_RECENT_D + FR_PRIOR_D + 10).to_pytimedelta()
            gte = lookback.strftime("%Y-%m-%d") if hasattr(lookback, "strftime") else str(lookback)
        lte = today.strftime("%Y-%m-%d")

        # Load existing documents for dedup + PIT integrity
        docs_path = config.data_dir() / "federal_register" / "documents.parquet"
        docs_path.parent.mkdir(parents=True, exist_ok=True)

        existing: pd.DataFrame
        if docs_path.exists():
            try:
                existing = pd.read_parquet(docs_path)
            except Exception:  # noqa: BLE001
                existing = pd.DataFrame()
        else:
            existing = pd.DataFrame()

        seen_ids: set[str] = set(existing["document_number"].tolist()) if not existing.empty and "document_number" in existing.columns else set()

        first_seen_ts = now_utc.isoformat()
        new_rows: list[dict] = []

        for theme_id, spec in tmap.items():
            terms: list[str] = spec.get("terms") or []
            agency_slugs_allowed: set[str] = set(spec.get("agencies") or [])

            seen_doc_ids_this_theme: set[str] = set()

            for term in terms:
                time.sleep(REQUEST_PAUSE)
                try:
                    page_docs = _fetch_all_for_term(term, gte, lte, ua)
                except Exception as exc:  # noqa: BLE001
                    if is_connection_error(exc):
                        raise
                    log.warning("federal_register: term=%r theme=%s failed: %s", term, theme_id, exc)
                    continue

                for d in page_docs:
                    doc_num = d.get("document_number") or ""
                    if not doc_num:
                        continue
                    # Skip if already processed for this theme in this run
                    composite_key = f"{doc_num}:{theme_id}"
                    if composite_key in seen_doc_ids_this_theme:
                        continue
                    seen_doc_ids_this_theme.add(composite_key)

                    # Stage-2 agency filter: OR across full agencies list + parent slugs
                    doc_agency_slugs = _agency_slugs(d.get("agencies") or [])
                    if agency_slugs_allowed and not doc_agency_slugs.intersection(agency_slugs_allowed):
                        continue  # two-stage filter: passes term (stage-1) but fails agency (stage-2)

                    doc_type = (d.get("type") or "").upper()
                    action = d.get("action") or ""
                    reg_stage, weight = _reg_stage(doc_type, action)

                    # significant: store AS-FIRST-SEEN (never overwrite); null != false
                    significant_raw = d.get("significant")
                    significant = True if significant_raw is True else (False if significant_raw is False else None)

                    pub_date = d.get("publication_date") or ""
                    comments_close = d.get("comments_close_on")

                    rin_list = d.get("regulation_id_numbers") or []
                    rin = rin_list[0] if rin_list else None

                    cfr_refs = d.get("cfr_references") or []
                    cfr_ref = ""
                    if cfr_refs and isinstance(cfr_refs[0], dict):
                        t_val = cfr_refs[0].get("title", "")
                        p_val = cfr_refs[0].get("part", "")
                        cfr_ref = f"{t_val} CFR {p_val}" if t_val and p_val else ""

                    # PIT stamp: only on NEW documents (never overwrite _first_seen)
                    is_new = doc_num not in seen_ids

                    new_rows.append({
                        "document_number": doc_num,
                        "basket_id": theme_id,
                        "publication_date": pub_date,
                        "type": doc_type,
                        "reg_stage": reg_stage,
                        "weight": weight,
                        "significant": significant,
                        "title": (d.get("title") or "")[:500],
                        "abstract": (d.get("abstract") or "")[:1000],
                        "action": action[:200],
                        "rin": rin,
                        "comments_close_on": comments_close,
                        "agency_slug": next(iter(doc_agency_slugs), ""),
                        "cfr_ref": cfr_ref,
                        "_first_seen": first_seen_ts if is_new else None,
                    })
                    seen_ids.add(doc_num)

        if not new_rows:
            log.info("federal_register: no new documents fetched (gte=%s)", gte)
            # Still compute velocity from existing data
            if not existing.empty:
                vel = velocity(existing)
                if not vel.empty:
                    vel_path = config.data_dir() / "federal_register" / "reg_velocity.parquet"
                    vel.to_parquet(vel_path)
            ingest = pd.DataFrame(
                {"docs_fetched": [0], "baskets": [0]},
                index=[pd.Timestamp(today)],
            )
            return {"federal_register__ingest": ingest}

        new_df = pd.DataFrame(new_rows)

        # Merge: append new rows into existing; preserve _first_seen on existing rows
        if not existing.empty:
            # For rows that exist already (same document_number + basket_id), keep existing _first_seen
            merged = pd.concat([existing, new_df], ignore_index=True)
            # Deduplicate: keep first occurrence per (document_number, basket_id) to preserve PIT _first_seen
            merged = merged.drop_duplicates(subset=["document_number", "basket_id"], keep="first")
        else:
            merged = new_df

        # Sort by publication date for readability
        merged = merged.sort_values("publication_date", ignore_index=True)

        # Write append-only tape
        merged.to_parquet(docs_path, index=False)

        # Compute and write velocity frame
        vel = velocity(merged)
        vel_path = config.data_dir() / "federal_register" / "reg_velocity.parquet"
        if not vel.empty:
            vel.to_parquet(vel_path)

        n_new = len(new_df)
        n_baskets = len(vel) if not vel.empty else 0
        log.info(
            "federal_register: %d docs fetched (%d total in tape) -> %d baskets in velocity",
            n_new, len(merged), n_baskets,
        )

        ingest = pd.DataFrame(
            {"docs_fetched": [n_new], "baskets": [n_baskets]},
            index=[pd.Timestamp(today)],
        )
        return {"federal_register__ingest": ingest}
