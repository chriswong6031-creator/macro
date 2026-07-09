"""
collectors/dol_labor_certs.py — DOL Foreign Labor Certification (LCA + PERM) collector.

Acquisition source:
  DOL Foreign Labor Application Gateway (FLAG) public performance-data disclosure files.
  Quarterly xlsx bulk files, keyless/free, published at:
    LCA: https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY{YYYY}_Q{N}.xlsx
    PERM: https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/PERM_Disclosure_Data_FY{YYYY}_Q{N}.xlsx
  URL patterns VERIFIED live 2026-07-09 via HEAD/range-request.

Column layout verified live 2026-07-09 by range-requesting and decompressing
xl/sharedStrings.xml from the actual quarterly xlsx files:

  LCA columns (verified from LCA_Disclosure_Data_FY2024_Q1.xlsx):
    CASE_NUMBER, CASE_STATUS, RECEIVED_DATE, DECISION_DATE, ORIGINAL_CERT_DATE,
    VISA_CLASS, JOB_TITLE, SOC_CODE, SOC_TITLE, FULL_TIME_POSITION, BEGIN_DATE,
    END_DATE, TOTAL_WORKER_POSITIONS, NEW_EMPLOYMENT, CONTINUED_EMPLOYMENT,
    CHANGE_PREVIOUS_EMPLOYMENT, NEW_CONCURRENT_EMPLOYMENT, CHANGE_EMPLOYER,
    AMENDED_PETITION, EMPLOYER_NAME, TRADE_NAME_DBA, EMPLOYER_ADDRESS1,
    EMPLOYER_ADDRESS2, EMPLOYER_CITY, EMPLOYER_STATE, EMPLOYER_POSTAL_CODE,
    EMPLOYER_COUNTRY, EMPLOYER_PROVINCE, EMPLOYER_PHONE, EMPLOYER_PHONE_EXT,
    NAICS_CODE, EMPLOYER_POC_*, AGENT_ATTORNEY_*, WORKSITE_WORKERS,
    SECONDARY_ENTITY, SECONDARY_ENTITY_BUSINESS_NAME,
    WORKSITE_ADDRESS1, WORKSITE_ADDRESS2, WORKSITE_CITY, WORKSITE_COUNTY,
    WORKSITE_STATE, WORKSITE_POSTAL_CODE,
    WAGE_RATE_OF_PAY_FROM, WAGE_RATE_OF_PAY_TO, WAGE_UNIT_OF_PAY,
    PREVAILING_WAGE, PW_UNIT_OF_PAY, PW_TRACKING_NUMBER, PW_WAGE_LEVEL, ...

  PERM columns (verified from PERM_Disclosure_Data_FY2025_Q1.xlsx):
    CASE_NUMBER, CASE_STATUS, RECEIVED_DATE, DECISION_DATE, REFILE,
    ORIG_FILE_DATE, ..., EMPLOYER_NAME, EMPLOYER_STATE_PROVINCE, ...,
    WORKSITE_STATE, JOB_TITLE, ..., WAGE_OFFER_FROM, WAGE_OFFER_TO,
    WAGE_OFFER_UNIT_OF_PAY, PW_WAGE, PW_UNIT_OF_PAY, PW_SKILL_LEVEL, ...

File sizes (observed 2026-07-09):
  LCA  FY2026 Q1: ~75MB  LCA  FY2025 Q4: ~79MB  LCA  FY2024 Q1: ~53MB
  PERM FY2025 Q1: ~844KB  PERM FY2025 Q4: downloaded confirmed.

RENDER BUDGET LAW: this collector NEVER runs on the nightly render path.
It is wired as a standalone CLI (scripts/collect_dol_certs.py) in the
collect lane only. On subsequent nightly runs it no-ops in seconds when
no new quarterly file exists.

PIT LAW: rows keyed by DECISION_DATE (point-in-time knowable).
File-level publication date is stored as file_published in the state file.
DOL release lag is typically 4-8 weeks after quarter-end.

Output:
  data/dol_certs/certs.parquet  (runner-local, gitignored)
    columns: [program, decision_date, case_status, employer_name,
              job_title, worksite_state, wage_annualized, file_published]

Store path env override: DOL_CERTS_STORE (mirrors WARN_STORE / THETADATA_STORE pattern).

Wiring: do NOT add to scripts/collect.py until Phase-1 gates pass.
Invoke standalone: python -m collectors.dol_labor_certs [--programs lca,perm]
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL patterns (verified live 2026-07-09)
# ---------------------------------------------------------------------------
_BASE_URL = "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs"
_LCA_URL_TMPL = _BASE_URL + "/LCA_Disclosure_Data_FY{fy}_Q{q}.xlsx"
_PERM_URL_TMPL = _BASE_URL + "/PERM_Disclosure_Data_FY{fy}_Q{q}.xlsx"

# DOL fiscal year: Oct 1 – Sep 30.  Q1=Oct-Dec, Q2=Jan-Mar, Q3=Apr-Jun, Q4=Jul-Sep.
_PROGRAM_URLS = {
    "lca": _LCA_URL_TMPL,
    "perm": _PERM_URL_TMPL,
}

# ---------------------------------------------------------------------------
# Compact column maps (raw → normalized)
# ---------------------------------------------------------------------------
_LCA_COLS = {
    "EMPLOYER_NAME": "employer_name",
    "JOB_TITLE": "job_title",
    "WORKSITE_STATE": "worksite_state",
    "DECISION_DATE": "decision_date",
    "CASE_STATUS": "case_status",
    # Annualized from WAGE_RATE_OF_PAY_FROM (LCA pays per unit — see _annualize)
    "WAGE_RATE_OF_PAY_FROM": "_wage_raw",
    "WAGE_UNIT_OF_PAY": "_wage_unit",
}
_PERM_COLS = {
    # DOL changed the PERM disclosure layout at FY2026: EMP_BUSINESS_NAME /
    # PRIMARY_WORKSITE_STATE / JOB_OPP_WAGE_* replaced the FY<=2025 names
    # (verified live against PERM FY2026_Q2 and FY2025_Q1, 2026-07-09).
    # Generations are disjoint; when multiple candidates map to one canonical
    # name, _normalize_df keeps the first present (dict order = newest first).
    "EMP_BUSINESS_NAME": "employer_name",
    "EMPLOYER_NAME": "employer_name",
    "JOB_TITLE": "job_title",
    "PRIMARY_WORKSITE_STATE": "worksite_state",
    "WORKSITE_STATE": "worksite_state",
    "DECISION_DATE": "decision_date",
    "CASE_STATUS": "case_status",
    "JOB_OPP_WAGE_FROM": "_wage_raw",
    "WAGE_OFFER_FROM": "_wage_raw",
    "JOB_OPP_WAGE_PER": "_wage_unit",
    "WAGE_OFFER_UNIT_OF_PAY": "_wage_unit",
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Only keep certified cases (deny/withdraw/withdrawn add noise, no hiring signal)
_KEEP_STATUSES = frozenset({"CERTIFIED", "Certified"})

# Wage unit → annual multiplier
_WAGE_MULTIPLIERS = {
    "Year": 1,
    "yr": 1,
    "Annual": 1,
    "Hour": 2080,
    "hr": 2080,
    "Week": 52,
    "wk": 52,
    "Month": 12,
    "mth": 12,
    "Bi-Weekly": 26,
}

# Default store (relative to repo root)
_DEFAULT_STORE_REL = Path("data/dol_certs/certs.parquet")
_STATE_FILE_REL = Path("data/dol_certs/_state.json")

# Known hardcoded fallback to main checkout
_MAIN_CHECKOUT_STORE = Path(
    "/Users/chriswong/Documents/Cluade/Macro Dashboard/data/dol_certs/certs.parquet"
)
_MAIN_CHECKOUT_STATE = Path(
    "/Users/chriswong/Documents/Cluade/Macro Dashboard/data/dol_certs/_state.json"
)

# Output columns (canonical store schema)
STORE_COLS = [
    "program",
    "decision_date",
    "case_status",
    "employer_name",
    "job_title",
    "worksite_state",
    "wage_annualized",
    "file_published",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _env_store_file(root: Path) -> Optional[Path]:
    """Resolve DOL_CERTS_STORE to the store FILE path.

    The env var names the store DIRECTORY (THETADATA_STORE convention).
    Back-compat: a value ending in .parquet is accepted as the file itself.
    (2026-07-09 incident: the old file-path-only semantics + a directory value
    wrote the store one level up, into git-swept data/.)
    """
    env_val = os.environ.get("DOL_CERTS_STORE", "").strip()
    if not env_val:
        return None
    p = Path(env_val) if Path(env_val).is_absolute() else root / env_val
    return p if p.suffix == ".parquet" else p / _DEFAULT_STORE_REL.name


def _find_store(root: Path) -> Optional[Path]:
    """Resolve store path via env override, local, then main-checkout fallback."""
    p = _env_store_file(root)
    if p is not None:
        if p.exists():
            return p
        log.warning("DOL_CERTS_STORE store file does not exist yet: %s", p)

    local = root / _DEFAULT_STORE_REL
    if local.exists():
        return local

    if _MAIN_CHECKOUT_STORE.exists():
        return _MAIN_CHECKOUT_STORE

    return None


def _store_dir(root: Path) -> Path:
    """Return store directory, preferring env override (directory semantics)."""
    p = _env_store_file(root)
    if p is not None:
        return p.parent
    return root / _DEFAULT_STORE_REL.parent


def _load_state(state_path: Path) -> dict:
    """Load the ingested-quarters state file."""
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("State file parse error: %s", exc)
    return {"ingested": []}


def _save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.rename(state_path)


def _dol_fiscal_quarters() -> list[tuple[str, str, str]]:
    """
    Return ordered list of (fiscal_year, quarter, release_slug) tuples,
    most-recent first, covering the past 6 quarters.

    DOL fiscal year runs Oct–Sep:
      Q1 = Oct, Nov, Dec  (FY starts Oct 1)
      Q2 = Jan, Feb, Mar
      Q3 = Apr, May, Jun
      Q4 = Jul, Aug, Sep
    """
    today = date.today()
    # Determine the most recent completed quarter
    cal_month = today.month
    cal_year = today.year

    # Calendar month → (fiscal_year, quarter)
    def _cal_to_fy_q(y: int, m: int) -> tuple[int, int]:
        if m >= 10:
            return y + 1, 1
        elif m >= 7:
            return y, 4
        elif m >= 4:
            return y, 3
        else:
            return y, 2

    fy, q = _cal_to_fy_q(cal_year, cal_month)

    quarters = []
    for _ in range(8):  # last 8 quarters to be safe
        quarters.append((str(fy), str(q)))
        q -= 1
        if q < 1:
            q = 4
            fy -= 1

    return quarters


def _annualize(wage_raw, unit: str) -> Optional[float]:
    """Convert a raw wage and unit to an annualized float."""
    if wage_raw is None:
        return None
    try:
        w = float(str(wage_raw).replace(",", "").strip())
    except (ValueError, TypeError):
        return None
    if w <= 0:
        return None
    mult = _WAGE_MULTIPLIERS.get(str(unit).strip(), None)
    if mult is None:
        # Unknown unit — try to annualize by assuming hourly if small (< 200)
        mult = 2080 if w < 200 else 1
    return round(w * mult, 2)


def _normalize_df(raw_df: pd.DataFrame, program: str, col_map: dict,
                  file_published: str) -> pd.DataFrame:
    """
    Normalize a raw DOL xlsx DataFrame into the compact STORE_COLS schema.

    Steps:
    1. Select only the columns we need (tolerant — ignore missing cols).
    2. Filter to CERTIFIED only.
    3. Annualize wage.
    4. Rename to canonical names.
    5. Add program + file_published.
    """
    # 1. Column selection — tolerant
    available: dict = {}
    seen_canonical: set = set()
    for col, mapped in col_map.items():
        if col in raw_df.columns and mapped not in seen_canonical:
            available[col] = mapped
            seen_canonical.add(mapped)
    if "DECISION_DATE" not in available and "decision_date" not in raw_df.columns:
        log.warning("No DECISION_DATE column found in %s file — skipping", program.upper())
        return pd.DataFrame(columns=STORE_COLS)

    df = raw_df[list(available.keys())].copy()
    df = df.rename(columns=available)

    # 2. Filter to certified only
    if "case_status" in df.columns:
        # startswith captures "Certified", "Certified - Expired", "Certified -
        # Withdrawn" — all were certified at decision time (hiring-intent basis).
        df = df[df["case_status"].str.strip().str.upper().str.startswith("CERTIFIED")].copy()

    # 3. Annualize wage
    wage_col = "_wage_raw"
    unit_col = "_wage_unit"
    if wage_col in df.columns:
        units = df[unit_col].fillna("Year") if unit_col in df.columns else pd.Series(
            ["Year"] * len(df)
        )
        df["wage_annualized"] = [
            _annualize(w, u)
            for w, u in zip(df[wage_col], units)
        ]
        df = df.drop(columns=[wage_col] + ([unit_col] if unit_col in df.columns else []))
    else:
        df["wage_annualized"] = None

    # 4. Normalize decision_date
    if "decision_date" in df.columns:
        df["decision_date"] = pd.to_datetime(df["decision_date"], errors="coerce")
        df = df[df["decision_date"].notna()]

    # 5. Add metadata columns
    df["program"] = program
    df["file_published"] = file_published

    # Clip employer and job_title
    for col in ("employer_name", "job_title", "worksite_state", "case_status"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    # Drop rows missing core fields
    df = df[
        df.get("employer_name", pd.Series([""] * len(df), index=df.index)).str.len() > 0
    ]

    # Select and reorder output columns
    out_cols = [c for c in STORE_COLS if c in df.columns]
    missing_cols = [c for c in STORE_COLS if c not in df.columns]
    for mc in missing_cols:
        df[mc] = None

    return df[STORE_COLS].reset_index(drop=True)


def download_and_normalize(
    program: str,
    fy: str,
    q: str,
    tmp_dir: Path,
    file_published: str,
) -> Optional[pd.DataFrame]:
    """
    Download a quarterly DOL disclosure xlsx and normalize to compact schema.

    Returns a DataFrame on success, None on download/parse failure.
    This function streams the download to a temp file to handle large xlsx files
    (LCA files are ~50-80MB; PERM files ~1-30MB).
    """
    url_tmpl = _PROGRAM_URLS.get(program)
    if url_tmpl is None:
        log.error("Unknown program: %s", program)
        return None

    url = url_tmpl.format(fy=fy, q=q)
    log.info("Downloading %s FY%s Q%s from %s", program.upper(), fy, q, url)

    fname = tmp_dir / f"{program}_fy{fy}_q{q}.xlsx"

    try:
        resp = requests.get(url, stream=True, timeout=(30, 300))
        if resp.status_code == 404:
            log.info("%s FY%s Q%s: 404 — file not yet published, skipping", program.upper(), fy, q)
            return None
        if resp.status_code != 200:
            log.warning("%s FY%s Q%s: HTTP %d — skipping", program.upper(), fy, q, resp.status_code)
            return None

        with open(fname, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):  # 1MB chunks
                fh.write(chunk)

        log.info("Downloaded %s (%.1f MB)", fname.name, fname.stat().st_size / 1e6)

    except Exception as exc:  # noqa: BLE001
        log.warning("Download error for %s FY%s Q%s: %s", program.upper(), fy, q, exc)
        return None

    # Parse xlsx
    col_map = _LCA_COLS if program == "lca" else _PERM_COLS
    try:
        # openpyxl engine required for xlsx; read_only=True reduces memory
        raw_df = pd.read_excel(
            fname,
            engine="openpyxl",
            dtype=str,      # read everything as str to avoid type coercion
        )
        log.info("Parsed %d rows from %s FY%s Q%s", len(raw_df), program.upper(), fy, q)
    except Exception as exc:  # noqa: BLE001
        log.warning("Parse error for %s FY%s Q%s: %s", program.upper(), fy, q, exc)
        return None

    return _normalize_df(raw_df, program, col_map, file_published)


def collect(
    programs: Optional[list[str]] = None,
    store_path: Optional[Path] = None,
    dry_run: bool = False,
    root: Optional[Path] = None,
) -> dict:
    """
    Main collect entry point.

    Detects the newest quarterly file not yet ingested, downloads, normalizes,
    and appends to the compact store.  No-ops immediately when the store is
    fresh (all recent quarters already ingested).

    Parameters
    ----------
    programs : list of 'lca' and/or 'perm'. Default: both.
    store_path : Override store path (for tests).
    dry_run : If True, detect new quarters but skip download/write.
    root : Repo root override (for tests).

    Returns
    -------
    dict with keys: programs_checked, new_quarters_ingested, rows_added, store_path
    """
    if root is None:
        root = _find_root()
    if programs is None:
        programs = ["lca", "perm"]

    # Resolve store paths
    if store_path is not None:
        actual_store = store_path
        state_path = store_path.parent / "_state.json"
    else:
        store_dir = _store_dir(root)
        actual_store = store_dir / "certs.parquet"
        # Also check main checkout state file
        state_path = store_dir / "_state.json"
        if not state_path.parent.exists() and _MAIN_CHECKOUT_STATE.parent.exists():
            state_path = _MAIN_CHECKOUT_STATE

    actual_store.parent.mkdir(parents=True, exist_ok=True)
    state = _load_state(state_path)
    ingested = set(state.get("ingested", []))

    quarters_to_check = _dol_fiscal_quarters()
    new_quarters: list[str] = []
    new_dfs: list[pd.DataFrame] = []

    with tempfile.TemporaryDirectory(prefix="dol_certs_") as tmp_str:
        tmp_dir = Path(tmp_str)

        for program in programs:
            for fy, q in quarters_to_check:
                key = f"{program}:FY{fy}_Q{q}"
                if key in ingested:
                    log.debug("Already ingested: %s — skipping", key)
                    continue

                if dry_run:
                    log.info("dry_run: would check %s", key)
                    continue

                # file_published = today (we record when we ingested it)
                file_published = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                try:
                    df = download_and_normalize(program, fy, q, tmp_dir, file_published)
                except Exception as exc:  # noqa: BLE001
                    # Layout drift or parse bug in ONE file must not void the
                    # whole run (2026-07-09 incident: FY2026 PERM layout change
                    # crashed normalize and lost the successful LCA ingest).
                    log.error("%s: normalize failed (%s) — skipping program", key, exc)
                    break
                if df is None:
                    # Not yet available (404) — skip to older quarters (they are MORE
                    # likely to be published, not less).  DOL publishes 4-8 weeks after
                    # quarter-end, so the newest detected quarter is almost always
                    # unpublished when this collector runs.
                    continue
                if df.empty:
                    log.info("%s: empty after normalization — still marking ingested", key)
                else:
                    new_dfs.append(df)
                    log.info("%s: %d certified rows", key, len(df))

                new_quarters.append(key)
                ingested.add(key)
                # Only ingest the most recent new quarter per run to stay fast
                break

    if new_dfs:
        # Append to existing store
        combined = pd.concat(new_dfs, ignore_index=True)

        if actual_store.exists():
            existing = pd.read_parquet(actual_store)
            combined = pd.concat([existing, combined], ignore_index=True)
            # De-duplicate by (program, decision_date, employer_name, job_title)
            dedup_cols = ["program", "decision_date", "employer_name", "job_title"]
            combined = combined.drop_duplicates(subset=dedup_cols, keep="last")
            combined = combined.sort_values(["program", "decision_date"]).reset_index(drop=True)

        tmp_out = actual_store.with_suffix(".tmp.parquet")
        combined.to_parquet(tmp_out, index=False)
        tmp_out.rename(actual_store)
        log.info("Store updated: %s (%d total rows)", actual_store, len(combined))

    if new_quarters:
        state["ingested"] = sorted(ingested)
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        _save_state(state_path, state)

    rows_added = sum(len(d) for d in new_dfs)
    result = {
        "programs_checked": programs,
        "new_quarters_ingested": new_quarters,
        "rows_added": rows_added,
        "store_path": str(actual_store),
    }
    if not new_quarters and not dry_run:
        log.info("collect_dol_certs: all recent quarters already ingested — no-op")

    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="DOL Foreign Labor Certification collector")
    parser.add_argument(
        "--programs",
        default="lca,perm",
        help="Comma-separated programs to collect: lca,perm (default: both)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect new quarters but skip download/write",
    )
    parser.add_argument(
        "--store",
        default=None,
        help="Override store path (default: data/dol_certs/certs.parquet or DOL_CERTS_STORE env)",
    )
    args = parser.parse_args()

    programs = [p.strip().lower() for p in args.programs.split(",") if p.strip()]
    store_path = Path(args.store) if args.store else None

    try:
        result = collect(programs=programs, store_path=store_path, dry_run=args.dry_run)
        log.info("Result: %s", result)
    except Exception as exc:  # noqa: BLE001
        log.error("collect_dol_certs failed: %s", exc)
    return 0  # always exit 0


if __name__ == "__main__":
    raise SystemExit(main())
