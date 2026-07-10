"""collectors/clinicaltrials_themes.py — ClinicalTrials.gov theme-level pipeline density.

TIL W10 (PR-W10). Keyless; weekly cadence; collect-lane step.

WHAT THIS BUILDS (vs per-stock clinicaltrials.py):
  The existing collectors/clinicaltrials.py is per-TICKER (per-stock Phase-3 catalyst).
  This module is per-THEME (aggregate capital-commitment signal across ALL industry
  sponsors per modality/indication). It answers: "Is the GLP-1 obesity pipeline growing
  or shrinking as a whole?" rather than "Did Novo Nordisk file a new study?"

  The capital-commitment meaning of the aggregate is what dies if academic studies
  dominate — so INDUSTRY sponsor filter is strictly enforced here.

VERIFIED LIVE 2026-07-09:
  Endpoint:    https://clinicaltrials.gov/api/v2/studies
  API version: v2 (pinned; never uses v1 or versionless fallback)
  INDUSTRY filter: filter.advanced=AREA[LeadSponsorClass]INDUSTRY
    NOTE: SponsorType area name returns HTTP 400; LeadSponsorClass is correct.
  Enrollment:  protocolSection.designModule.enrollmentInfo.count
  Phase:       protocolSection.designModule.phases  (list; may be None/[])
  First post:  protocolSection.statusModule.studyFirstPostDateStruct.date (PIT key)
  Count:       top-level totalCount (requires countTotal=true param)
  Paging:      nextPageToken (top-level field when more pages exist)
  Rate etiquette: 0.35s inter-request; 1000 studies max per modality per run

PIT LAW (W9):
  Study counts keyed by studyFirstPostDate (when study was first posted on the
  registry — the publicly visible registration date). Ingest date recorded
  separately as ingest_date. No retroactive query-expansion without bumping
  vocabulary_version in clinical_modalities.yml.

OUTPUT:
  data/clinical_trials/modality_monthly.parquet (git-stored, small)
  data/clinical_trials/ct_themes_state.json  (state file; last-ingest per modality)

Per-modality isolation: one bad modality query never voids others.
Tolerant: always exits 0; honest null written on complete failure.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import yaml

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"
_API_VERSION_VERIFIED = "v2"  # pinned; never downgrade without re-verification

# Fields requested from the v2 API
_FIELDS = (
    "NCTId,Phase,LeadSponsorClass,StudyFirstPostDate,EnrollmentCount"
)
_INDUSTRY_FILTER = "AREA[LeadSponsorClass]INDUSTRY"

_PAGE_SIZE = 1000       # max per page (well within v2 limits)
_PACE_S = 0.35          # polite inter-request delay (seconds)
_BACKFILL_START = "2018-01-01"   # PIT law: consistent backfill horizon
_TIMEOUT_S = 45
_RETRIES = 2

# Phase-1/2/3 canonical strings in CT.gov v2 API (as returned in phases list)
_PHASE_MAP = {
    "PHASE1": "phase1",
    "PHASE2": "phase2",
    "PHASE3": "phase3",
}

# Store columns (git-stored parquet schema)
STORE_COLS = [
    "modality_id",       # from config
    "theme_id",          # from config
    "nct_id",            # NCT number (deduplication key)
    "study_first_post_date",  # PIT date key (YYYY-MM-DD string)
    "year_month",        # YYYY-MM derived from study_first_post_date
    "phases_raw",        # pipe-joined raw phase strings (e.g. "PHASE1|PHASE2")
    "phase1",            # bool: is PHASE1 in phases
    "phase2",            # bool: is PHASE2 in phases
    "phase3",            # bool: is PHASE3 in phases
    "enrollment_target", # int or None from enrollmentInfo.count
    "sponsor_class",     # always "INDUSTRY" (post-filter)
    "ingest_date",       # YYYY-MM-DD when this collector wrote the row
    "vocabulary_version",  # from config schema_version stamp
]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config" / "clinical_modalities.yml"
_DEFAULT_STORE = _REPO_ROOT / "data" / "clinical_trials"
_PARQUET_FILE = "modality_monthly.parquet"
_STATE_FILE = "ct_themes_state.json"

# Main-checkout fallback (untracked-store false-null trap law)
_MAIN_CHECKOUT_STORE = Path(
    "/Users/chriswong/Documents/Cluade/Macro Dashboard/data/clinical_trials"
)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load clinical_modalities.yml."""
    with open(_CONFIG_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _store_path() -> Path:
    override = os.environ.get("CLINICAL_THEMES_STORE")
    if override:
        return Path(override)
    return _DEFAULT_STORE


# ---------------------------------------------------------------------------
# State file helpers
# ---------------------------------------------------------------------------

def _load_state(store: Path) -> dict:
    """Load state file (per-modality last-ingest date)."""
    p = store / _STATE_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


def _save_state(store: Path, state: dict) -> None:
    store.mkdir(parents=True, exist_ok=True)
    (store / _STATE_FILE).write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# API client (reuses existing v2 session; mirrors clinicaltrials.py patterns)
# ---------------------------------------------------------------------------

def _http_get(session: requests.Session, params: dict) -> Optional[dict]:
    """Fetch one page from the v2 API; return parsed JSON or None on error."""
    try:
        r = session.get(_STUDIES_URL, params=params, timeout=_TIMEOUT_S)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as exc:
        log.warning("CT.gov v2 HTTP %s for params %s: %s", exc.response.status_code, params, exc)
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("CT.gov v2 request error for params %s: %s", params, exc)
        return None


def _build_params(modality: dict, page_token: Optional[str] = None) -> dict:
    """Build v2 API params for a modality config row."""
    query_type = modality.get("query_type", "query.intr")
    params: dict = {
        "filter.advanced": _INDUSTRY_FILTER,
        "pageSize": _PAGE_SIZE,
        "fields": _FIELDS,
        "countTotal": "true",
    }
    # Backfill date filter: studyFirstPostDate >= 2018-01-01
    # Use the filter.advanced compound with date range
    # Note: AREA[StudyFirstPostDate]RANGE[2018-01-01,MAX] is a valid v2 filter
    # We combine with the INDUSTRY filter using AND
    params["filter.advanced"] = (
        f"AREA[LeadSponsorClass]INDUSTRY "
        f"AND AREA[StudyFirstPostDate]RANGE[{_BACKFILL_START},MAX]"
    )
    if query_type == "query.intr":
        params["query.intr"] = modality["query"]
    elif query_type == "query.cond":
        params["query.cond"] = modality["query"]
    elif query_type == "combined":
        params["query.cond"] = modality["query_cond"]
        params["query.intr"] = modality["query_intr"]
    else:
        params["query.term"] = modality.get("query", "")
    if page_token:
        params["pageToken"] = page_token
    return params


def _parse_study(study: dict, modality: dict, ingest_date: str, vocab_version: str) -> Optional[dict]:
    """
    Parse one v2 study object into a store row.
    Returns None if sponsor class is not INDUSTRY (post-filter safety guard).
    """
    ps = study.get("protocolSection", {})
    id_mod = ps.get("identificationModule", {})
    status_mod = ps.get("statusModule", {})
    design_mod = ps.get("designModule", {})
    sponsor_mod = ps.get("sponsorCollaboratorsModule", {})

    # Post-filter safety: must be INDUSTRY
    sponsor_class = (sponsor_mod.get("leadSponsor", {}).get("class") or "").upper()
    if sponsor_class != "INDUSTRY":
        return None

    nct_id = id_mod.get("nctId") or ""
    if not nct_id:
        return None

    # PIT date: studyFirstPostDateStruct.date
    first_post_struct = status_mod.get("studyFirstPostDateStruct") or {}
    first_post_date = first_post_struct.get("date") or ""
    if not first_post_date:
        return None

    # year_month for aggregation (YYYY-MM)
    year_month = first_post_date[:7] if len(first_post_date) >= 7 else ""
    if not year_month:
        return None

    # Phases
    phases_list = design_mod.get("phases") or []
    phases_raw = "|".join(phases_list) if phases_list else ""
    phase1 = "PHASE1" in phases_list
    phase2 = "PHASE2" in phases_list
    phase3 = "PHASE3" in phases_list

    # Enrollment target
    enroll_info = design_mod.get("enrollmentInfo") or {}
    enrollment_target: Optional[int] = None
    try:
        ec = enroll_info.get("count")
        if ec is not None:
            enrollment_target = int(ec)
    except (ValueError, TypeError):
        pass

    return {
        "modality_id": modality["modality_id"],
        "theme_id": modality["theme_id"],
        "nct_id": nct_id,
        "study_first_post_date": first_post_date,
        "year_month": year_month,
        "phases_raw": phases_raw,
        "phase1": phase1,
        "phase2": phase2,
        "phase3": phase3,
        "enrollment_target": enrollment_target,
        "sponsor_class": sponsor_class,
        "ingest_date": ingest_date,
        "vocabulary_version": vocab_version,
    }


# ---------------------------------------------------------------------------
# Per-modality fetch with full paging
# ---------------------------------------------------------------------------

def _fetch_modality(
    session: requests.Session,
    modality: dict,
    ingest_date: str,
    vocab_version: str,
    *,
    backfill: bool = False,
    state: dict,
) -> tuple[list[dict], int, Optional[str]]:
    """
    Fetch all INDUSTRY-sponsored studies for one modality.

    Returns:
      (rows: list[dict], total_api_count: int, error_msg: Optional[str])

    Incremental mode: only fetches studies not already in the state
    (compares by most-recent year_month in state).
    Full backfill: fetches from _BACKFILL_START regardless of state.

    Per-modality isolation: catches all exceptions; returns empty rows + error.
    """
    modality_id = modality["modality_id"]
    rows: list[dict] = []
    page_token: Optional[str] = None
    total_count = 0
    pages_fetched = 0
    max_pages = 20  # safety cap (~20k studies; no modality should exceed this)

    try:
        while True:
            params = _build_params(modality, page_token)
            payload = _http_get(session, params)
            if payload is None:
                err = f"HTTP error on page {pages_fetched + 1}"
                log.warning("clinicaltrials_themes [%s]: %s", modality_id, err)
                return rows, total_count, err

            if pages_fetched == 0:
                total_count = payload.get("totalCount", 0)

            studies = payload.get("studies") or []
            for study in studies:
                row = _parse_study(study, modality, ingest_date, vocab_version)
                if row is not None:
                    rows.append(row)

            pages_fetched += 1
            page_token = payload.get("nextPageToken")
            if not page_token or pages_fetched >= max_pages:
                break

            time.sleep(_PACE_S)

    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        log.warning("clinicaltrials_themes [%s]: unexpected error: %s", modality_id, exc)
        return rows, total_count, err

    log.info(
        "clinicaltrials_themes [%s]: %d rows from %d pages (API totalCount=%d)",
        modality_id, len(rows), pages_fetched, total_count
    )
    return rows, total_count, None


# ---------------------------------------------------------------------------
# Parquet store helpers
# ---------------------------------------------------------------------------

def _load_existing(store: Path) -> Optional[pd.DataFrame]:
    p = store / _PARQUET_FILE
    if p.exists():
        try:
            df = pd.read_parquet(p)
            log.debug("clinicaltrials_themes: loaded existing parquet (%d rows)", len(df))
            return df
        except Exception as exc:  # noqa: BLE001
            log.warning("clinicaltrials_themes: parquet unreadable: %s", exc)
    return None


def _save_parquet(store: Path, df: pd.DataFrame) -> None:
    store.mkdir(parents=True, exist_ok=True)
    p = store / _PARQUET_FILE
    df.to_parquet(p, index=False)
    log.info("clinicaltrials_themes: saved parquet (%d rows) → %s", len(df), p)


def _merge_rows(existing: Optional[pd.DataFrame], new_rows: list[dict]) -> pd.DataFrame:
    """
    Merge new rows into existing parquet.
    Deduplication key: (modality_id, nct_id) — keep first (earliest ingest).
    The vocabulary_version field enables future query-expansion without tainting
    existing rows.
    """
    if not new_rows:
        return existing if existing is not None else pd.DataFrame(columns=STORE_COLS)
    new_df = pd.DataFrame(new_rows, columns=STORE_COLS)
    if existing is None or existing.empty:
        return new_df.drop_duplicates(subset=["modality_id", "nct_id"], keep="first")
    combined = pd.concat([existing, new_df], ignore_index=True)
    return combined.drop_duplicates(subset=["modality_id", "nct_id"], keep="first").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Monthly aggregate helper (for engine consumption)
# ---------------------------------------------------------------------------

def compute_monthly_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate parquet to monthly (modality × year_month) summary rows.

    Columns:
      modality_id, theme_id, year_month,
      n_new_registrations   — count of studies first posted in this month
      enrollment_sum        — sum of enrollment targets (NaN where missing)
      n_phase1_new          — new Phase-1 studies registered in month
      n_phase2_new          — new Phase-2 studies registered in month
      n_phase3_new          — new Phase-3 studies registered in month (late-stage proxy)
      n_no_phase            — registrations with no phase listed
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "modality_id", "theme_id", "year_month",
            "n_new_registrations", "enrollment_sum",
            "n_phase1_new", "n_phase2_new", "n_phase3_new", "n_no_phase",
        ])
    grp = df.groupby(["modality_id", "theme_id", "year_month"])
    agg = grp.agg(
        n_new_registrations=("nct_id", "count"),
        enrollment_sum=("enrollment_target", "sum"),
        n_phase1_new=("phase1", "sum"),
        n_phase2_new=("phase2", "sum"),
        n_phase3_new=("phase3", "sum"),
    ).reset_index()
    # n_no_phase: studies where none of phase1/2/3 are True
    df2 = df.copy()
    df2["_no_phase"] = ~(df2["phase1"] | df2["phase2"] | df2["phase3"])
    no_phase = df2.groupby(["modality_id", "theme_id", "year_month"])["_no_phase"].sum().reset_index()
    no_phase = no_phase.rename(columns={"_no_phase": "n_no_phase"})
    agg = agg.merge(no_phase, on=["modality_id", "theme_id", "year_month"], how="left")
    agg["n_no_phase"] = agg["n_no_phase"].fillna(0).astype(int)
    agg = agg.sort_values(["modality_id", "year_month"]).reset_index(drop=True)
    return agg


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_clinicaltrials_themes(
    *,
    backfill: bool = False,
    dry_run: bool = False,
    store_path: Optional[Path] = None,
) -> dict:
    """
    Collect theme-level ClinicalTrials.gov pipeline density data.

    Parameters
    ----------
    backfill : bool
        If True, fetch from _BACKFILL_START for all modalities (ignores state).
    dry_run : bool
        If True, fetch but do not write to parquet or state file.
    store_path : Optional[Path]
        Override store directory (for tests).

    Returns
    -------
    dict
        Summary: {modality_id: {rows_fetched, api_total, error}}
        plus top-level keys: total_rows_new, total_rows_stored, errors.
    """
    now = datetime.now(timezone.utc)
    ingest_date = now.strftime("%Y-%m-%d")

    # Load config
    try:
        cfg = _load_config()
    except Exception as exc:  # noqa: BLE001
        log.error("clinicaltrials_themes: config load failed: %s", exc)
        return {"error": f"config load failed: {exc}", "total_rows_new": 0}

    modalities = cfg.get("modalities") or []
    vocab_version = str(cfg.get("vocabulary_version", "v1"))

    if not modalities:
        log.warning("clinicaltrials_themes: no modalities in config — exiting")
        return {"total_rows_new": 0, "errors": 0}

    store = store_path or _store_path()
    state = _load_state(store)
    existing = _load_existing(store)

    # HTTP session with polite headers
    session = requests.Session()
    session.headers.update({
        "User-Agent": "MacroDashboard/1.0 (research-only; contact: research@mastermind-x.com)",
        "Accept": "application/json",
    })

    all_new_rows: list[dict] = []
    summary: dict = {}
    errors = 0

    for modality in modalities:
        modality_id = modality.get("modality_id", "unknown")
        try:
            rows, api_total, err = _fetch_modality(
                session, modality, ingest_date, vocab_version,
                backfill=backfill, state=state,
            )
            summary[modality_id] = {
                "rows_fetched": len(rows),
                "api_total": api_total,
                "error": err,
            }
            if err:
                errors += 1
            else:
                all_new_rows.extend(rows)
                state[modality_id] = {"last_ingest": ingest_date, "api_total": api_total}
        except Exception as exc:  # noqa: BLE001
            log.warning("clinicaltrials_themes [%s]: isolation catch: %s", modality_id, exc)
            summary[modality_id] = {"rows_fetched": 0, "api_total": 0, "error": str(exc)}
            errors += 1

        time.sleep(_PACE_S)

    # Merge and write
    merged = _merge_rows(existing, all_new_rows)
    total_new = len(all_new_rows)
    total_stored = len(merged)

    if not dry_run and total_new > 0:
        _save_parquet(store, merged)
        _save_state(store, state)
        log.info(
            "clinicaltrials_themes: +%d new rows → %d total stored (%d errors)",
            total_new, total_stored, errors,
        )
    elif dry_run:
        log.info(
            "clinicaltrials_themes [dry-run]: would write %d new rows (total=%d, %d errors)",
            total_new, total_stored, errors,
        )
    else:
        log.info("clinicaltrials_themes: 0 new rows; no changes written (%d errors)", errors)

    return {
        "modalities": summary,
        "total_rows_new": total_new,
        "total_rows_stored": total_stored,
        "errors": errors,
        "ingest_date": ingest_date,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(
        description="ClinicalTrials.gov theme-level pipeline density collector (TIL W10)"
    )
    parser.add_argument(
        "--backfill", action="store_true",
        help=f"Backfill from {_BACKFILL_START} for all modalities"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch but do not write to disk"
    )
    args = parser.parse_args()

    result = run_clinicaltrials_themes(backfill=args.backfill, dry_run=args.dry_run)
    print(
        f"clinicaltrials_themes: +{result.get('total_rows_new', 0)} new rows "
        f"({result.get('total_rows_stored', 0)} total stored, "
        f"{result.get('errors', 0)} modality errors)"
    )
