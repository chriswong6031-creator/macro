"""
collectors/warn_notices.py — WARN Act notice collector (nightly incremental).

Acquisition path:
  Rung 1: biglocalnews/warn-scraper (pip-installable, Apache-2.0, open-source)
  Rung 2: Grey direct scraping for states the warn-scraper fails on

Output: data/warn/notices.parquet
  Normalized columns: notice_date, state, employer_raw, workers, effective_date,
                      source_state_page, scraped_at

Schedule:
  Top-15 WARN-volume states: weekly (see WIRING notes below)
  All other supported states: monthly (manual trigger or separate cron)

WIRING NOTE (for consolidation into collect.py):
  Do NOT edit scripts/collect.py to include this collector — the family is still
  in ACCRUAL phase. The nightly job caller should invoke this module standalone:
      python -m collectors.warn_notices [--states ca,ny,tx,...] [--out data/warn/notices.parquet]
  Once Phase-1 gates pass, wire into the main collect pipeline.

BLOCKED STATES (as of 2026-07-08):
  TX: TWC site returns HTTP 202 (CloudFlare bot-challenge) — scraper yields no links.
  PA: pa.gov returns HTTP 403 — IP-level block.
  NC: des.nc.gov returns HTTP 404 (moved URL) and CloudFlare challenge.
  MN: mn.gov/deed returns hCaptcha challenge.
  OH: scraper parse error (JSON div not found — state changed page structure).
  FL: scraper parse error (mainContentArea div gone).
  MI: scraper KeyError 'Site address' (state changed HTML structure).
  CO: scraper KeyError 'CO Notifications' (state changed page structure).
  ID: PDF scraper gets non-PDF response.
  KY: scraper TypeError on None URL (state changed page structure).
  LA: scraper None response (state returns None HTML).
  VA: requires Xvfb (X11 virtual display, not available on headless Mac).
  NE: DNS resolution failure (dol.nebraska.gov unreachable from this IP).
  NM: DNS resolution failure (www.dws.state.nm.us unreachable from this IP).

VPS FALLBACK (design — not yet deployed, deploy only if >=3 major states blocked):
  TX and PA (two major states) are blocked at the Mac IP level.
  Design: cron on 146.190.142.17 that:
    1. Runs warn-scraper for [tx, pa, mn, nc, oh, fl, mi] weekly
    2. Writes CSVs to /home/deploy/warn-raw/
    3. rsyncs to Mac: rsync -avz deploy@146.190.142.17:/home/deploy/warn-raw/ data/warn/raw-vps/
  Deploy trigger: if >=3 major-volume states (CA/TX/NY/IL/OH/PA/FL/MI/NJ/WA/GA/IN) are
  blocked simultaneously, implement this cron and rsync.
  Current status: 2 major states blocked (TX, PA) — VPS not yet deployed.
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── canonical column order ───────────────────────────────────────────────────
COLS = [
    "notice_date",
    "state",
    "employer_raw",
    "workers",
    "effective_date",
    "source_state_page",
    "scraped_at",
]

# Top-15 WARN-volume states (by historical notice frequency)
TOP15 = ["ca", "ny", "tx", "il", "oh", "pa", "fl", "mi", "nj", "wa", "ga", "nc", "in", "mn", "tn"]

# States supported by warn-scraper that actually work (as of 2026-07-08)
WORKING_STATES = [
    "ak", "al", "az", "ca", "ct", "dc", "de", "hi", "ia", "il",
    "in", "ks", "md", "me", "mt", "nj", "ny", "ok", "or", "ri",
    "sc", "sd", "tn", "ut", "vt", "wa", "wi",
]

# States where warn-scraper is broken (source site changed) — document only
BROKEN_SCRAPER = {
    "oh": "scraper KeyError: Could not find JSON data div (state changed page structure)",
    "fl": "scraper IndexError: mainContentArea div not found (state changed layout)",
    "mi": "scraper KeyError: 'Site address' (Michigan changed HTML structure 2025-11-25)",
    "co": "scraper KeyError: 'CO Notifications' (state changed page structure)",
    "id": "PDF scraper gets non-PDF response (state changed format)",
    "ky": "scraper TypeError on None URL (state moved link)",
    "la": "scraper TypeError: write() on None (state returns None body)",
    "va": "requires Xvfb X11 display (unavailable on headless Mac)",
    "ne": "DNS resolution failure for dol.nebraska.gov",
    "nm": "DNS resolution failure for www.dws.state.nm.us",
}

# States where this Mac's IP is blocked (CloudFlare / WAF)
BLOCKED_STATES = {
    "tx": "HTTP 202 CloudFlare bot-challenge loop",
    "pa": "HTTP 403 IP-level block",
    "mn": "hCaptcha CloudFlare challenge",
    "nc": "HTTP 404 + CloudFlare challenge (URL moved)",
    "ga": "TCP connect timeout to www.tcsg.edu",
}

# States not in warn-scraper at all
NOT_SUPPORTED = ["mn", "nc"]  # Also in BLOCKED_STATES

# ── per-state normalizers ────────────────────────────────────────────────────
def _parse_date(s: str) -> Optional[str]:
    """Return ISO date string or None."""
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in (
        "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d %H:%M:%S",
        "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%Y%m%d",
    ):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    # Try partial: "Feb 2026" → None (can't pin to day)
    return None


def _to_int(s: str) -> Optional[int]:
    if not s or not s.strip():
        return None
    cleaned = s.strip().replace(",", "").replace(" ", "").split(".")[0]
    try:
        v = int(cleaned)
        return v if v > 0 else None
    except ValueError:
        return None


def _normalize_ca(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("notice_date", "")),
            "state": "CA",
            "employer_raw": r.get("company", "").strip(),
            "workers": _to_int(r.get("num_employees", "")),
            "effective_date": _parse_date(r.get("effective_date", "")),
            "source_state_page": "https://edd.ca.gov/en/jobs_and_training/Layoff_Services_WARN",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_il(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Notice Date", r.get("Received Date", ""))),
            "state": "IL",
            "employer_raw": (r.get("Location Name", "") or r.get("Doing Business As Name", "")).strip(),
            "workers": _to_int(r.get("Total Affected Workers", r.get("Affected Workers", ""))),
            "effective_date": _parse_date(r.get("Layoff Date", r.get("Closure Date", ""))),
            "source_state_page": "https://www.illinoisworknet.com/WARN",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_nj(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Month Posted", "")),
            "state": "NJ",
            "employer_raw": r.get("Company", "").strip(),
            "workers": _to_int(r.get("Workforce Affected", "")),
            "effective_date": _parse_date(r.get("Effective Date", "")),
            "source_state_page": "https://www.nj.gov/labor/lwdhome/warn/",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_wa(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Received Date", "")),
            "state": "WA",
            "employer_raw": r.get("Company", "").strip(),
            "workers": _to_int(r.get("# of Workers", "")),
            "effective_date": _parse_date(r.get("Layoff Start Date", "")),
            "source_state_page": "https://www.esd.wa.gov/about-employees/WARN",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_in(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Notice Date", "")),
            "state": "IN",
            "employer_raw": r.get("Company", "").strip(),
            "workers": _to_int(r.get("Affected Workers", "")),
            "effective_date": _parse_date(r.get("LO/CL Date", "")),
            "source_state_page": "https://www.in.gov/dwd/warn-notices/",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_tn(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Notice Date", r.get("Received Date", ""))),
            "state": "TN",
            "employer_raw": r.get("Company", "").strip(),
            "workers": _to_int(r.get("No. Of Employees", "")),
            "effective_date": _parse_date(r.get("Effective Date", r.get("Layoff Date", ""))),
            "source_state_page": "https://www.tn.gov/workforce/general-resources/warn-notices.html",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_al(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Initial Report Date", "")),
            "state": "AL",
            "employer_raw": r.get("Company", "").strip(),
            "workers": _to_int(r.get("Planned # of Affected Employees", "")),
            "effective_date": _parse_date(r.get("Planned Starting Date", "")),
            "source_state_page": "https://www.madeinalabama.com/warn-act-notices/",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_or(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Received Date", "")),
            "state": "OR",
            "employer_raw": r.get("Company Name", "").strip(),
            "workers": _to_int(r.get("Laid Off", "")),
            "effective_date": _parse_date(r.get("Layoff Date", "")),
            "source_state_page": "https://www.oregon.gov/employ/Businesses/Pages/WARN-Notices.aspx",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_wi(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Notice Received", "")),
            "state": "WI",
            "employer_raw": r.get("Company", "").strip(),
            "workers": _to_int(r.get("Affected Workers", "")),
            "effective_date": _parse_date(r.get("Layoff Begin Date", "")),
            "source_state_page": "https://dwd.wisconsin.gov/dislocated_workers/warn.htm",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_ks(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("notice_date", "")),
            "state": "KS",
            "employer_raw": r.get("employer", "").strip(),
            "workers": _to_int(r.get("number_of_employees_affected", "")),
            "effective_date": None,
            "source_state_page": "https://www.kansasworks.com/search/warn_lookups",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_md(rows: list[dict], scraped_at: str) -> list[dict]:
    """MD has no header row; cols: notice_date, naics, company, address, county, workers, effective_date, type"""
    out = []
    for r in rows:
        # r is a dict with integer-ish keys from csv.DictReader or a raw list
        vals = list(r.values()) if isinstance(r, dict) else r
        if len(vals) < 7:
            continue
        out.append({
            "notice_date": _parse_date(vals[0]),
            "state": "MD",
            "employer_raw": str(vals[2]).strip(),
            "workers": _to_int(str(vals[5])),
            "effective_date": _parse_date(vals[6]) if len(vals) > 6 else None,
            "source_state_page": "https://www.dllr.state.md.us/employment/warn.shtml",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_sc(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("date", "")),
            "state": "SC",
            "employer_raw": r.get("company", "").strip(),
            "workers": _to_int(r.get("jobs", "")),
            "effective_date": None,
            "source_state_page": "https://jobs.scworks.org/warn",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_ny(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Date of WARN Notice ", r.get("Date of WARN Notice", ""))),
            "state": "NY",
            "employer_raw": r.get("Business Legal Name", "").strip(),
            "workers": _to_int(r.get("Number of Affected Workers ", r.get("Number of Affected Workers", ""))),
            "effective_date": _parse_date(r.get("Date Layoff/Closure Starts", "")),
            "source_state_page": "https://dol.ny.gov/warn-notices",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_ak(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Notice Date", "")),
            "state": "AK",
            "employer_raw": r.get("Company", "").strip(),
            "workers": _to_int(r.get("Employees Affected", "")),
            "effective_date": _parse_date(r.get("Layoff Date", "")),
            "source_state_page": "https://jobs.alaska.gov/rr/WARN_notices.htm",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_dc(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Notice Date", "")),
            "state": "DC",
            "employer_raw": r.get("Organization Name", "").strip(),
            "workers": _to_int(r.get("Number toEmployees Affected", r.get("Number of Employees Affected", ""))),
            "effective_date": _parse_date(r.get("Effective Layoff Date", "")),
            "source_state_page": "https://does.dc.gov/service/industry-labor-market-information",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_de(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("notice_date", "")),
            "state": "DE",
            "employer_raw": r.get("employer", "").strip(),
            "workers": _to_int(r.get("number_of_employees_affected", "")),
            "effective_date": None,
            "source_state_page": "https://joblink.delaware.gov/warn",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_hi(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Date", "")),
            "state": "HI",
            "employer_raw": r.get("Company", "").strip(),
            "workers": _to_int(r.get("jobs", "")),
            "effective_date": None,
            "source_state_page": "https://labor.hawaii.gov/wdc/warn-notices/",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_ia(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Notice Date", "")),
            "state": "IA",
            "employer_raw": r.get("Company", "").strip(),
            "workers": _to_int(r.get("Emp #", r.get("Emp#", ""))),
            "effective_date": _parse_date(r.get("Layoff Date", "")),
            "source_state_page": "https://www.iowaworkforcedevelopment.gov/warn-notices",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_me(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("notice_date", "")),
            "state": "ME",
            "employer_raw": r.get("employer", "").strip(),
            "workers": _to_int(r.get("number_of_employees_affected", "")),
            "effective_date": None,
            "source_state_page": "https://www.maine.gov/labor/labor_stats/warn.html",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_mt(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Date of Notice", "")),
            "state": "MT",
            "employer_raw": r.get("Name of Company", "").strip(),
            "workers": None,
            "effective_date": _parse_date(r.get("Date of Impact", "")),
            "source_state_page": "https://uid.dli.mt.gov/warn-notices",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_ok(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("notice_date", "")),
            "state": "OK",
            "employer_raw": r.get("company_name", "").strip(),
            "workers": None,
            "effective_date": None,
            "source_state_page": "https://oklahoma.gov/oesc/businesses/rapid-response/warn-notices.html",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_ri(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("WARN Date", r.get("Date Received", ""))),
            "state": "RI",
            "employer_raw": r.get("Company Name", "").strip(),
            "workers": _to_int(r.get("Number Affected", "")),
            "effective_date": _parse_date(r.get("Effective Date", "")),
            "source_state_page": "https://dlt.ri.gov/employers/workforce-regulation-safety/warn-act",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_sd(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Date Received", "")),
            "state": "SD",
            "employer_raw": r.get("Company", "").strip(),
            "workers": _to_int(r.get("Employees Affected", "")),
            "effective_date": None,
            "source_state_page": "https://dlr.sd.gov/workforce_services/businesses/warn_notices.aspx",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_ut(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("Date of Notice", "")),
            "state": "UT",
            "employer_raw": r.get("Company Name", "").strip(),
            "workers": _to_int(r.get("Affected Workers", "")),
            "effective_date": None,
            "source_state_page": "https://jobs.utah.gov/employer/business/warn.html",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_vt(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("notice_date", "")),
            "state": "VT",
            "employer_raw": r.get("employer", "").strip(),
            "workers": _to_int(r.get("number_of_employees_affected", "")),
            "effective_date": None,
            "source_state_page": "https://www.vermontjoblink.com/warn",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_az(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("notice_date", "")),
            "state": "AZ",
            "employer_raw": r.get("employer", "").strip(),
            "workers": _to_int(r.get("number_of_employees_affected", "")),
            "effective_date": None,
            "source_state_page": "https://www.azjobconnection.gov/ada/warn_lookups/search",
            "scraped_at": scraped_at,
        })
    return out


def _normalize_ct(rows: list[dict], scraped_at: str) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "notice_date": _parse_date(r.get("modifiedDate", "")),
            "state": "CT",
            "employer_raw": r.get("affected_company", "").strip(),
            "workers": None,
            "effective_date": _parse_date(r.get("layoff_dates", r.get("closing_dates", ""))),
            "source_state_page": "https://www.ctdol.state.ct.us/progsupt/bussrvce/warnreports/warnreports.htm",
            "scraped_at": scraped_at,
        })
    return out


# ── dispatcher ───────────────────────────────────────────────────────────────
_NORMALIZERS = {
    "ca": _normalize_ca,
    "il": _normalize_il,
    "nj": _normalize_nj,
    "wa": _normalize_wa,
    "in": _normalize_in,
    "tn": _normalize_tn,
    "al": _normalize_al,
    "or": _normalize_or,
    "wi": _normalize_wi,
    "ks": _normalize_ks,
    "sc": _normalize_sc,
    "ny": _normalize_ny,
    "ak": _normalize_ak,
    "dc": _normalize_dc,
    "de": _normalize_de,
    "hi": _normalize_hi,
    "ia": _normalize_ia,
    "me": _normalize_me,
    "mt": _normalize_mt,
    "ok": _normalize_ok,
    "ri": _normalize_ri,
    "sd": _normalize_sd,
    "ut": _normalize_ut,
    "vt": _normalize_vt,
    "az": _normalize_az,
    "ct": _normalize_ct,
}

# MD is special (no header row)
def _normalize_md_file(fpath: Path, scraped_at: str) -> list[dict]:
    rows = []
    with open(fpath, encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        for r in reader:
            if not any(r):
                continue
            if len(r) < 7:
                continue
            rows.append({
                "notice_date": _parse_date(r[0]),
                "state": "MD",
                "employer_raw": r[2].strip(),
                "workers": _to_int(r[5]),
                "effective_date": _parse_date(r[6]) if len(r) > 6 else None,
                "source_state_page": "https://www.dllr.state.md.us/employment/warn.shtml",
                "scraped_at": scraped_at,
            })
    return rows


def _read_csv_dict(fpath: Path) -> list[dict]:
    """Read CSV with DictReader; skip malformed lines."""
    rows = []
    with open(fpath, encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(dict(r))
    return rows


def normalize_state(state: str, fpath: Path, scraped_at: str) -> list[dict]:
    """Normalize a raw state CSV into the canonical schema."""
    state = state.lower()
    if state == "md":
        return _normalize_md_file(fpath, scraped_at)
    fn = _NORMALIZERS.get(state)
    if fn is None:
        logger.warning(f"No normalizer for state={state.upper()}, skipping")
        return []
    rows = _read_csv_dict(fpath)
    return fn(rows, scraped_at)


def scrape_states(
    states: list[str],
    raw_dir: Path,
    cache_dir: Path,
    venv_warn_scraper: Optional[Path] = None,
) -> dict[str, str]:
    """
    Run warn-scraper for each state. Returns dict of state -> status.
    Writes raw CSVs to raw_dir.
    """
    if venv_warn_scraper is None:
        # Try to find warn-scraper in PATH or a venv sibling
        venv_warn_scraper = Path(sys.executable).parent / "warn-scraper"
        if not venv_warn_scraper.exists():
            venv_warn_scraper = Path("warn-scraper")  # hope it's in PATH

    status = {}
    for state in states:
        if state.lower() in BLOCKED_STATES:
            status[state] = f"SKIP_BLOCKED: {BLOCKED_STATES[state.lower()]}"
            continue
        if state.lower() in BROKEN_SCRAPER:
            status[state] = f"SKIP_BROKEN: {BROKEN_SCRAPER[state.lower()]}"
            continue
        try:
            result = subprocess.run(
                [str(venv_warn_scraper), "--data-dir", str(raw_dir),
                 "--cache-dir", str(cache_dir), "--log-level", "warning", state.lower()],
                capture_output=True, text=True, timeout=300,
            )
            out_file = raw_dir / f"{state.lower()}.csv"
            if result.returncode == 0 and out_file.exists():
                status[state] = "OK"
            else:
                status[state] = f"FAILED: {result.stderr[-200:]}"
        except subprocess.TimeoutExpired:
            status[state] = "TIMEOUT"
        except Exception as exc:
            status[state] = f"ERROR: {exc}"
    return status


def build_panel(raw_dir: Path, states: Optional[list[str]] = None) -> pd.DataFrame:
    """
    Read all raw CSVs from raw_dir, normalize, and return a consolidated DataFrame.
    """
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_rows: list[dict] = []

    csv_files = sorted(raw_dir.glob("*.csv"))
    if states:
        states_lower = {s.lower() for s in states}
        csv_files = [f for f in csv_files if f.stem.lower() in states_lower]

    for fpath in csv_files:
        state = fpath.stem.lower()
        try:
            rows = normalize_state(state, fpath, scraped_at)
            all_rows.extend(rows)
            logger.info(f"{state.upper()}: normalized {len(rows)} rows")
        except Exception as exc:
            logger.error(f"{state.upper()}: normalize error: {exc}")

    if not all_rows:
        return pd.DataFrame(columns=COLS)

    df = pd.DataFrame(all_rows, columns=COLS)

    # Parse dates
    for col in ("notice_date", "effective_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce")

    # Clip to reasonable window (WARN Act enacted 1988)
    df = df[df["notice_date"].isna() | (df["notice_date"] >= "1988-01-01")]

    # Drop rows with no company and no date
    df = df[~(df["employer_raw"].isna() | (df["employer_raw"] == ""))]

    # Sort
    df = df.sort_values(["state", "notice_date"], na_position="last").reset_index(drop=True)

    return df


def run(
    states: Optional[list[str]] = None,
    raw_dir: Path = Path("data/warn/raw"),
    out_path: Path = Path("data/warn/notices.parquet"),
    venv_warn_scraper: Optional[Path] = None,
    scrape: bool = True,
):
    """
    Full pipeline: scrape -> normalize -> write parquet.
    Set scrape=False to use existing raw CSVs.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = raw_dir.parent / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if states is None:
        states = WORKING_STATES

    if scrape:
        logger.info(f"Scraping {len(states)} states...")
        status = scrape_states(states, raw_dir, cache_dir, venv_warn_scraper)
        for s, st in sorted(status.items()):
            logger.info(f"  {s.upper()}: {st}")

    logger.info("Building normalized panel...")
    df = build_panel(raw_dir, states)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info(f"Wrote {len(df):,} rows to {out_path}")
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="WARN notice collector")
    parser.add_argument("--states", help="Comma-separated state codes (default: all working)")
    parser.add_argument("--out", default="data/warn/notices.parquet")
    parser.add_argument("--raw-dir", default="data/warn/raw")
    parser.add_argument("--no-scrape", action="store_true", help="Skip scraping, use existing CSVs")
    args = parser.parse_args()

    states = args.states.split(",") if args.states else None
    run(
        states=states,
        raw_dir=Path(args.raw_dir),
        out_path=Path(args.out),
        scrape=not args.no_scrape,
    )
