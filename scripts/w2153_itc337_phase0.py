"""W2-153 USITC Section 337 Exclusion-Risk — Phase-0 Event Study.

LANE A6, wave-2 queue. No collector; no nightly edits. This script is the
entire harness: data acquisition, event parsing, return study, gate logic,
and report generation.

===========================================================================
PRE-REGISTERED DESIGN (frozen before first execution)
===========================================================================

FAMILY: w2153_itc337

HYPOTHESIS
Respondents named in ITC Section 337 investigations face exclusion-order risk
that should generate negative forward beta-adjusted abnormal returns around
two distinct event types:

  E1 — Institution notice: ITC formally institutes a 337 investigation.
       Published in the Federal Register. PIT fence: FR publication date +1
       business day (reflects actual investor awareness).

  E2 — Adverse final determination: Commission issues a final determination
       finding a Section 337 violation, published in the Federal Register.
       PIT fence: FR publication date (same day; these are unambiguous
       adverse findings that have been telegraphed by the ALJ initial
       determination weeks earlier).

DIRECTION: NEGATIVE for both event types (exclusion-order risk / actual order).

GATED CELLS (4 total):
  C1: E1_institution_5d    institution × 5d  forward beta-adj AR
  C2: E1_institution_21d   institution × 21d forward beta-adj AR
  C3: E2_adverse_5d        adverse-final × 5d  forward beta-adj AR
  C4: E2_adverse_21d       adverse-final × 21d forward beta-adj AR

GATES (all must pass):
  G1: ≥1 gated cell shows negative direction with |t| ≥ 2 (Newey-West HAC,
      date-clustered) AND survives BH-FDR correction q ≤ 0.10 across 4 cells.
  G2: Not-one-sector: the n ≥ 5 contributing calendar-date observations span
      at least 2 distinct 2-digit GICS sectors (guards against concentration
      in semis/tech being the sole driver).

UNDERPOWERED RULE (AMENDMENT A1, pre-registered before first run):
  If any gated cell has fewer than 25 calendar-date observations AFTER
  collapsing to one obs per event-date, that cell is flagged UNDERPOWERED.
  Underpowered cells contribute to descriptive statistics only; they cannot
  satisfy G1. The gate verdict for underpowered cells is UNDERPOWERED,
  not NULL.

BETA ADJUSTMENT:
  Trailing-252-day OLS beta vs SPY (PIT: using only data up to the event
  availability date). Minimum 60 trading days of overlap to compute beta;
  otherwise beta = 1.0.

CALENDAR-TIME COLLAPSE:
  Multiple events on the same availability date (same calendar date) are
  averaged to a single observation before Newey-West. This prevents pseudo-
  replication from dates where multiple respondents appear simultaneously
  (e.g. a complaint naming 10 companies).

NW LAGS:
  E1 (institution, 5d):  lags = 1
  E1 (institution, 21d): lags = 4
  E2 (adverse, 5d):      lags = 1
  E2 (adverse, 21d):     lags = 4

AMENDMENT A2: SECTOR MAPPING
  Sectors are sourced from the stocks/ store metadata if available; otherwise
  assigned by GICS manual lookup for the mapped tickers. If sector data is
  absent for a ticker, it is excluded from the G2 sector check but included
  in return statistics.

===========================================================================
DATA SOURCES
===========================================================================

  1. Federal Register API (api.federalregister.gov) — institution notices
     and final determination notices from ITC. Search terms and filters
     documented below in _search_fr_docs().

  2. Full text of each notice (raw_text_url): parses respondent company names
     from the structured notice text.

  3. Respondent ticker map: scripts/w2153_itc337_respondent_map.csv
     (manual, validity-windowed). Coverage printed at startup.

  4. Prices: data/massive_stock_day/<T>.parquet for tickers with 2021+
     data; data/stocks/<T>.parquet for tickers needing deeper history.
     Deep history from stocks/ is used for pre-2021 events.

===========================================================================

Run:
    python -m scripts.w2153_itc337_phase0

Writes:
    data/itc337/fr_docs_institution.parquet   — FR institution notices
    data/itc337/fr_docs_adverse.parquet       — FR adverse determination notices
    data/itc337/events_e1.parquet             — mapped institution events
    data/itc337/events_e2.parquet             — mapped adverse events
    reports/w2153-itc337-phase0.md            — gate report
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.trial_ledger import TrialLedger          # noqa: E402
from engine.validation import newey_west_tstat, benjamini_hochberg  # noqa: E402

# ---------------------------------------------------------------------------
# CONSTANTS (frozen before first run — part of pre-registration)
# ---------------------------------------------------------------------------
FAMILY     = "w2153_itc337"
REPORT_PATH = ROOT / "reports" / "w2153-itc337-phase0.md"
ITC337_DIR  = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/itc337")

# Price stores (real dirs, not git-tracked)
PRICE_DAY_DIR   = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day")
PRICE_DEEP_DIR  = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/stocks")

# Benchmark
SPY = "SPY"

# Study window (price store constraints)
PRICE_DAY_START = date(2021, 7, 6)
PRICE_DAY_END   = date(2026, 7, 2)
PRICE_DEEP_START = date(1980, 1, 1)

# Beta estimation window
BETA_WIN     = 252
BETA_MIN_OBS = 60

# Forward return windows (trading days)
FWD_5  = 5
FWD_21 = 21

# PIT fences (calendar days after FR publication date)
# E1: +1 business day — publication appears next morning
# E2: 0 — same-day; final determinations are market-moving headline news
E1_PIT_FENCE_BD = 1    # business days after FR pub date
E2_PIT_FENCE_BD = 0

# NW lags per cell
NW_LAGS = {
    "E1_institution_5d": 1,
    "E1_institution_21d": 4,
    "E2_adverse_5d": 1,
    "E2_adverse_21d": 4,
}

# Underpowered threshold (calendar-date observations, post-collapse)
UNDERPOWERED_N = 25

# FR API
FR_API_BASE = "https://www.federalregister.gov/api/v1"
FR_PER_PAGE = 100       # max per request
FR_THROTTLE_SEC = 0.35  # polite rate limit

# Pre-registered trial grid (logged BEFORE results)
TRIAL_GRID = [
    {"variant": "E1_institution_5d",  "event": "institution",         "fwd_days": 5,
     "direction": "negative", "pit_fence_bd": E1_PIT_FENCE_BD},
    {"variant": "E1_institution_21d", "event": "institution",         "fwd_days": 21,
     "direction": "negative", "pit_fence_bd": E1_PIT_FENCE_BD},
    {"variant": "E2_adverse_5d",      "event": "adverse_final_det",   "fwd_days": 5,
     "direction": "negative", "pit_fence_bd": E2_PIT_FENCE_BD},
    {"variant": "E2_adverse_21d",     "event": "adverse_final_det",   "fwd_days": 21,
     "direction": "negative", "pit_fence_bd": E2_PIT_FENCE_BD},
]


# ---------------------------------------------------------------------------
# RESPONDENT TICKER MAP
# ---------------------------------------------------------------------------

def load_respondent_map() -> dict[str, dict]:
    """Load the respondent-pattern → ticker map from CSV.

    Returns {PATTERN_UPPER -> {ticker, valid_from, valid_to, tier, notes}}.
    tier='X' means private/foreign-listed; we keep them for coverage
    accounting but they will not match any price store.
    """
    csv_path = ROOT / "scripts" / "w2153_itc337_respondent_map.csv"
    df = pd.read_csv(csv_path, keep_default_na=False, dtype=str)
    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        pat = row["respondent_pattern"].strip().upper()
        vf = pd.to_datetime(row["valid_from"]).date() if row["valid_from"] else None
        vt = pd.to_datetime(row["valid_to"]).date()   if row["valid_to"]   else None
        ticker = row["ticker"].strip() if row["ticker"].strip() else None
        out[pat] = {
            "ticker": ticker,
            "valid_from": vf,
            "valid_to":   vt,
            "tier":   row["tier"].strip(),
            "notes":  row["notes"].strip(),
        }
    return out


def match_respondent(name: str, event_date: date, rmap: dict) -> str | None:
    """Match a respondent name string to a ticker via substring lookup.

    Tries longest-pattern match first to avoid over-matching short patterns
    (e.g. 'FORD' matching 'STANFORD'). Returns None if no match, if tier='X',
    or if outside the validity window.
    """
    name_up = name.strip().upper()
    # Collect all matching patterns using word-boundary-aware matching.
    # Short patterns (≤5 chars) require a word boundary on both sides to
    # prevent 'SAP' matching 'disapprove', 'FORD' matching 'AFFORD', etc.
    matches = []
    for pat, info in rmap.items():
        if len(pat) <= 5:
            # Word-boundary check: pat must be surrounded by non-word chars or string edges
            import re as _re
            if _re.search(r'(?<![A-Z0-9])' + _re.escape(pat) + r'(?![A-Z0-9])', name_up):
                matches.append((len(pat), pat, info))
        else:
            if pat in name_up:
                matches.append((len(pat), pat, info))
    if not matches:
        return None
    # Pick longest matching pattern
    matches.sort(key=lambda x: x[0], reverse=True)
    _, _, info = matches[0]

    if info["tier"] in ("X", "B"):
        return None        # private or foreign-only listed (not US-tradable)
    ticker = info["ticker"]
    if not ticker:
        return None

    # Validity window check
    vf = info["valid_from"]
    vt = info["valid_to"]
    if vf and event_date < vf:
        return None
    if vt and event_date > vt:
        return None
    return ticker


# ---------------------------------------------------------------------------
# PRICE LOADING
# ---------------------------------------------------------------------------

def _load_single_price(ticker: str) -> pd.Series | None:
    """Load close series for a ticker, preferring massive_stock_day then stocks."""
    for d in (PRICE_DAY_DIR, PRICE_DEEP_DIR):
        p = d / f"{ticker}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index).normalize()
            col = next((c for c in ("close", "Close", "adj_close") if c in df.columns), None)
            if col:
                return df[col].astype(float).sort_index()
    return None


def load_prices(tickers: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load close and daily return matrices for the given tickers + SPY."""
    needed = sorted(set(tickers) | {SPY})
    closes: dict[str, pd.Series] = {}
    for t in needed:
        s = _load_single_price(t)
        if s is not None and len(s) > 60:
            closes[t] = s
        else:
            print(f"  WARNING: no price data for {t}", file=sys.stderr)
    close_df = pd.DataFrame(closes).sort_index()
    ret_df   = close_df.pct_change()
    return close_df, ret_df


def _next_business_day(d: date, n: int) -> date:
    """Advance d by n business days."""
    if n == 0:
        return d
    cur = d
    count = 0
    while count < n:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 5:   # Mon–Fri
            count += 1
    return cur


def compute_beta(ret_df: pd.DataFrame, ticker: str,
                 as_of: date, win: int = BETA_WIN) -> float:
    """Trailing-window PIT beta vs SPY."""
    if ticker not in ret_df.columns or SPY not in ret_df.columns:
        return 1.0
    sub = ret_df.loc[:pd.Timestamp(as_of)].tail(win)
    x   = sub[SPY].dropna()
    y   = sub[ticker].reindex(x.index).dropna()
    x   = x.reindex(y.index)
    if len(y) < BETA_MIN_OBS:
        return 1.0
    cov = float(np.cov(y.values, x.values)[0, 1])
    var = float(x.var())
    return cov / var if var > 1e-10 else 1.0


def abnormal_return(ret_df: pd.DataFrame, ticker: str,
                    avail_date: date, fwd_days: int,
                    beta: float) -> float | None:
    """Cumulative abnormal return = stock_cum - beta * SPY_cum over fwd_days.

    Entry on avail_date (the next-bar convention: we use returns AFTER avail_date).
    """
    ts = pd.Timestamp(avail_date)
    future = ret_df.loc[ts:].iloc[1: fwd_days + 1]
    if len(future) < fwd_days:
        return None
    def _cum(col):
        s = future[col] if col in future.columns else None
        if s is None or s.isna().all():
            return None
        return float((1 + s).prod() - 1)
    sr  = _cum(ticker)
    spr = _cum(SPY)
    if sr is None or spr is None:
        return None
    return sr - beta * spr


# ---------------------------------------------------------------------------
# FEDERAL REGISTER FETCH
# ---------------------------------------------------------------------------

def _fr_search(term: str, pub_date_gte: str, pub_date_lte: str,
               max_docs: int = 2000) -> list[dict]:
    """Paginate through Federal Register API search results.

    Returns list of dicts with keys: document_number, publication_date,
    title, docket_ids.
    """
    docs: list[dict] = []
    page = 1
    while len(docs) < max_docs:
        params = {
            "conditions[term]":                   term,
            "conditions[agencies][]":             "international-trade-commission",
            "conditions[publication_date][gte]":  pub_date_gte,
            "conditions[publication_date][lte]":  pub_date_lte,
            "per_page": FR_PER_PAGE,
            "order": "oldest",
            "page": page,
        }
        try:
            r = requests.get(f"{FR_API_BASE}/articles.json",
                             params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  FR API error (page {page}): {e}", file=sys.stderr)
            break

        results = data.get("results", [])
        if not results:
            break
        for item in results:
            docs.append({
                "document_number": item.get("document_number", ""),
                "publication_date": item.get("publication_date", ""),
                "title":           item.get("title", ""),
                "docket_ids":      item.get("docket_ids", ""),
            })
        total_pages = data.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1
        time.sleep(FR_THROTTLE_SEC)

    return docs


def _fetch_doc_text(doc_number: str, pub_date: str) -> str | None:
    """Fetch raw text of a Federal Register notice via the raw_text_url pattern."""
    # pub_date format: YYYY-MM-DD
    try:
        yr, mo, dy = pub_date.split("-")
        url = (f"https://www.federalregister.gov/documents/full_text/text"
               f"/{yr}/{mo}/{dy}/{doc_number}.txt")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  Text fetch failed for {doc_number}: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# TEXT PARSING — respondent extraction
# ---------------------------------------------------------------------------

_RESPONDENT_HEADER_PAT = re.compile(
    r"(?:Respondent[s]?\s*[:;]|Named\s+as\s+[Rr]espondent[s]?|"
    r"The\s+following\s+firms?\s+(?:is|are)\s+(?:named|listed)\s+as\s+[Rr]espondent[s]?)",
    re.IGNORECASE
)

_SECTION_END_PAT = re.compile(
    r"(?:Complainant[s]?\s*[:;]|Commission\s+Investigative|"
    r"Notice\s+of\s+Investigation|Pursuant\s+to|FOR\s+FURTHER\s+INFORMATION|"
    r"SUPPLEMENTARY\s+INFORMATION|DATES\s*:|ACTION\s*:|SUMMARY\s*:)",
    re.IGNORECASE
)

def _extract_respondents_from_text(text: str) -> list[str]:
    """Parse respondent company names from a Federal Register notice text.

    Strategy:
    1. Find the 'Respondents:' section header.
    2. Extract lines until the next section header or 200-char gap with no names.
    3. Each bullet line / named entity is a potential respondent.
    Returns a list of raw company name strings (before mapping).
    """
    if not text:
        return []

    lines = text.splitlines()
    in_respondents = False
    respondent_lines: list[str] = []
    consecutive_blank = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        if not in_respondents:
            if _RESPONDENT_HEADER_PAT.search(stripped):
                in_respondents = True
                # Sometimes the names are on the same line after the colon
                # E.g. "Respondents: Acme Corp, FooBar Ltd"
                after = _RESPONDENT_HEADER_PAT.split(stripped, maxsplit=1)
                remainder = after[-1].strip(" :;") if len(after) > 1 else ""
                if remainder and len(remainder) > 3:
                    respondent_lines.append(remainder)
            continue

        # We're in the respondents section
        if _SECTION_END_PAT.search(stripped):
            break   # Hit next section header

        if not stripped:
            consecutive_blank += 1
            if consecutive_blank > 3:
                break
            continue
        else:
            consecutive_blank = 0

        # Skip lines that are clearly not company names
        if len(stripped) < 4:
            continue
        if stripped.startswith(("AGENCY:", "ACTION:", "SUMMARY:", "DATES:")):
            break

        respondent_lines.append(stripped)

    # Also try to extract from "337-TA-XXX" context and surrounding text
    # by looking for all-caps entity names with "Inc", "Corp", "Ltd", "LLC"
    corp_pat = re.compile(
        r"([A-Z][A-Za-z0-9\s,\.\-\'&/]+?(?:Inc\.?|Corp\.?|Ltd\.?|LLC\.?|"
        r"L\.L\.C\.?|Co\.?|Limited|Corporation|Company|Technologies|Systems|"
        r"Electronics|Semiconductor|Networks|Industries|Group|Holdings))",
        re.MULTILINE
    )

    # If we found explicit respondent section, use those; otherwise try corp_pat
    if respondent_lines:
        names = []
        for rl in respondent_lines:
            # Split by commas and semicolons for multi-name lines
            parts = re.split(r'[;,]', rl)
            for p in parts:
                p = p.strip().strip(".-•–—*·")
                # Remove trailing country/state parentheticals like "(Japan)" or "(Delaware)"
                p = re.sub(r'\s*\([^)]*\)\s*$', '', p).strip()
                if len(p) > 4:
                    names.append(p)
        return names
    else:
        # Fallback: extract all company-name-pattern matches from full text
        matches = corp_pat.findall(text)
        return list(dict.fromkeys(m.strip() for m in matches if len(m.strip()) > 4))[:30]


def _extract_inv_number(text: str, title: str, docket_ids: str) -> str | None:
    """Extract investigation number (337-TA-NNN) from text, title, or docket_ids."""
    for source in (docket_ids, title, text or ""):
        m = re.search(r'337-TA-(\d+)', source)
        if m:
            return f"337-TA-{m.group(1)}"
    return None


# ---------------------------------------------------------------------------
# EVENT TABLE BUILDING
# ---------------------------------------------------------------------------

def build_institution_events(rmap: dict, cache_dir: Path) -> pd.DataFrame:
    """Fetch Federal Register institution notices and build E1 event table.

    Searches for 'Notice of Institution of Investigation' + '337-TA' from ITC.
    PIT fence: FR publication date + 1 business day.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    docs_cache = cache_dir / "fr_docs_institution.parquet"

    if docs_cache.exists():
        print(f"  Using cached E1 FR docs: {docs_cache}")
        docs_df = pd.read_parquet(docs_cache)
        docs = docs_df.to_dict("records")
    else:
        print("  Fetching E1 institution notices from Federal Register API...")
        docs = _fr_search(
            term='"Notice of Institution of Investigation" "337-TA"',
            pub_date_gte="2000-01-01",
            pub_date_lte=str(PRICE_DAY_END),
        )
        print(f"  Found {len(docs)} E1 candidate docs from FR API")
        docs_df = pd.DataFrame(docs)
        docs_df.to_parquet(docs_cache, index=False)

    # Parse each notice for investigation number and respondents
    events: list[dict] = []
    text_cache = cache_dir / "texts_institution"
    text_cache.mkdir(exist_ok=True)

    for _, row in docs_df.iterrows():
        doc_num  = row["document_number"]
        pub_date = row["publication_date"]
        title    = row["title"]
        dockets  = str(row.get("docket_ids", ""))

        # Filter by title keywords
        title_up = title.upper()
        if "INSTITUTION" not in title_up or "INVESTIGATION" not in title_up:
            continue

        # Try text cache first
        txt_path = text_cache / f"{doc_num}.txt"
        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8", errors="replace")
        else:
            text = _fetch_doc_text(doc_num, pub_date)
            if text:
                txt_path.write_text(text, encoding="utf-8")
            time.sleep(FR_THROTTLE_SEC)

        inv_num = _extract_inv_number(text, title, dockets)
        respondents = _extract_respondents_from_text(text)

        try:
            ev_date   = date.fromisoformat(pub_date)
        except (ValueError, TypeError):
            continue
        avail_date = _next_business_day(ev_date, E1_PIT_FENCE_BD)

        for resp in respondents:
            ticker = match_respondent(resp, ev_date, rmap)
            events.append({
                "inv_num":    inv_num or "",
                "doc_num":    doc_num,
                "event_date": ev_date,
                "avail_date": avail_date,
                "respondent": resp,
                "ticker":     ticker or "",
                "event_type": "institution",
            })

    ev_df = pd.DataFrame(events) if events else pd.DataFrame(
        columns=["inv_num", "doc_num", "event_date", "avail_date",
                 "respondent", "ticker", "event_type"])
    ev_df["event_date"] = pd.to_datetime(ev_df["event_date"])
    ev_df["avail_date"] = pd.to_datetime(ev_df["avail_date"])
    ev_df = ev_df.drop_duplicates(subset=["inv_num", "ticker"], keep="first")
    ev_df = ev_df.sort_values("event_date")

    save_path = cache_dir / "events_e1.parquet"
    ev_df.to_parquet(save_path, index=False)
    mapped = ev_df[ev_df["ticker"] != ""]
    print(f"  E1 total respondent-event rows: {len(ev_df)}")
    print(f"  E1 rows with mapped tickers: {len(mapped)}")
    print(f"  E1 unique mapped tickers: {sorted(mapped['ticker'].unique())}")
    return ev_df


def build_adverse_events(rmap: dict, cache_dir: Path) -> pd.DataFrame:
    """Fetch Federal Register adverse final determination notices (E2).

    Adverse = Commission finds a Section 337 violation; exclusion order issued.
    Search terms: 'violation' 'exclusion order' '337-TA' from ITC.
    PIT fence: FR publication date (same day — these are clear outcomes).
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    docs_cache = cache_dir / "fr_docs_adverse.parquet"

    if docs_cache.exists():
        print(f"  Using cached E2 FR docs: {docs_cache}")
        docs_df = pd.read_parquet(docs_cache)
        docs = docs_df.to_dict("records")
    else:
        print("  Fetching E2 adverse determination notices from Federal Register API...")
        docs = _fr_search(
            term='"violation" "exclusion order" "337-TA"',
            pub_date_gte="2000-01-01",
            pub_date_lte=str(PRICE_DAY_END),
        )
        print(f"  Found {len(docs)} E2 candidate docs from FR API")
        docs_df = pd.DataFrame(docs)
        docs_df.to_parquet(docs_cache, index=False)

    # Parse each notice
    events: list[dict] = []
    text_cache = cache_dir / "texts_adverse"
    text_cache.mkdir(exist_ok=True)

    for _, row in docs_df.iterrows():
        doc_num  = row["document_number"]
        pub_date = row["publication_date"]
        title    = row["title"]
        dockets  = str(row.get("docket_ids", ""))

        # Filter by title keywords — must indicate a violation finding
        title_up = title.upper()
        adverse_keywords = ("VIOLATION", "EXCLUSION ORDER", "CEASE AND DESIST",
                            "FINAL DETERMINATION")
        if not any(kw in title_up for kw in adverse_keywords):
            continue
        # Must be 337 related
        if "337" not in title_up and "337" not in dockets:
            continue

        txt_path = text_cache / f"{doc_num}.txt"
        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8", errors="replace")
        else:
            text = _fetch_doc_text(doc_num, pub_date)
            if text:
                txt_path.write_text(text, encoding="utf-8")
            time.sleep(FR_THROTTLE_SEC)

        inv_num = _extract_inv_number(text, title, dockets)
        respondents = _extract_respondents_from_text(text)

        try:
            ev_date   = date.fromisoformat(pub_date)
        except (ValueError, TypeError):
            continue
        avail_date = _next_business_day(ev_date, E2_PIT_FENCE_BD)

        for resp in respondents:
            ticker = match_respondent(resp, ev_date, rmap)
            events.append({
                "inv_num":    inv_num or "",
                "doc_num":    doc_num,
                "event_date": ev_date,
                "avail_date": avail_date,
                "respondent": resp,
                "ticker":     ticker or "",
                "event_type": "adverse_final_det",
            })

    ev_df = pd.DataFrame(events) if events else pd.DataFrame(
        columns=["inv_num", "doc_num", "event_date", "avail_date",
                 "respondent", "ticker", "event_type"])
    ev_df["event_date"] = pd.to_datetime(ev_df["event_date"])
    ev_df["avail_date"] = pd.to_datetime(ev_df["avail_date"])
    ev_df = ev_df.drop_duplicates(subset=["inv_num", "ticker"], keep="first")
    ev_df = ev_df.sort_values("event_date")

    save_path = cache_dir / "events_e2.parquet"
    ev_df.to_parquet(save_path, index=False)
    mapped = ev_df[ev_df["ticker"] != ""]
    print(f"  E2 total respondent-event rows: {len(ev_df)}")
    print(f"  E2 rows with mapped tickers: {len(mapped)}")
    print(f"  E2 unique mapped tickers: {sorted(mapped['ticker'].unique())}")
    return ev_df


# ---------------------------------------------------------------------------
# EVENT STUDY CORE
# ---------------------------------------------------------------------------

def run_event_study(ev_df: pd.DataFrame, ret_df: pd.DataFrame,
                    fwd_days: int, nw_lags: int) -> dict:
    """Calendar-time collapsed event study.

    Steps:
    1. Filter to events where ticker has price data and avail_date is within
       the price window with at least fwd_days forward bars.
    2. Compute PIT beta-adjusted abnormal return for each event.
    3. Collapse to one observation per avail_date (calendar-time average).
    4. Newey-West t-stat on the date-indexed series.

    Returns dict with n_events, n_dates, mean_ar, nw, by_ticker, cal_series.
    """
    if ev_df is None or ev_df.empty:
        return {"n_events": 0, "n_dates": 0, "mean_ar": None, "nw": {},
                "by_ticker": {}, "cal_series": None, "underpowered": True}

    # Filter to mapped tickers with price data
    mapped = ev_df[ev_df["ticker"].isin(ret_df.columns)].copy()
    if mapped.empty:
        return {"n_events": 0, "n_dates": 0, "mean_ar": None, "nw": {},
                "by_ticker": {}, "cal_series": None, "underpowered": True}

    # Filter to price window
    price_end_ts = pd.Timestamp(PRICE_DAY_END)
    margin_days  = timedelta(days=int(fwd_days * 1.5) + 5)
    mapped = mapped[
        (mapped["avail_date"] <= price_end_ts - margin_days)
    ]
    if mapped.empty:
        return {"n_events": 0, "n_dates": 0, "mean_ar": None, "nw": {},
                "by_ticker": {}, "cal_series": None, "underpowered": True}

    pars: list[dict] = []
    for _, row in mapped.iterrows():
        ticker     = row["ticker"]
        avail_date = row["avail_date"].date()
        beta = compute_beta(ret_df, ticker, avail_date)
        ar   = abnormal_return(ret_df, ticker, avail_date, fwd_days, beta)
        if ar is None:
            continue
        pars.append({"avail_date": avail_date, "ticker": ticker, "ar": ar})

    if not pars:
        return {"n_events": 0, "n_dates": 0, "mean_ar": None, "nw": {},
                "by_ticker": {}, "cal_series": None, "underpowered": True}

    par_df = pd.DataFrame(pars)

    agg_df = par_df.groupby("ticker")["ar"].agg(["count", "mean"])
    by_ticker = {
        t: {"n": int(row["count"]),
            "mean_ar_pct": round(float(row["mean"]) * 100, 3)}
        for t, row in agg_df.iterrows()
    }

    # Calendar-time collapse
    cal = par_df.groupby("avail_date")["ar"].mean()
    n_events = len(par_df)
    n_dates  = len(cal)

    underpowered = n_dates < UNDERPOWERED_N

    if n_dates < 8:
        nw = {"mean": None, "se": None, "t": None, "p": None, "n": n_dates}
    else:
        nw = newey_west_tstat(cal.values, lags=nw_lags)

    return {
        "n_events":    n_events,
        "n_dates":     n_dates,
        "mean_ar":     round(float(cal.mean()) * 100, 4) if n_dates > 0 else None,
        "nw":          nw,
        "by_ticker":   by_ticker,
        "cal_series":  cal,
        "underpowered": underpowered,
    }


# ---------------------------------------------------------------------------
# SECTOR DIVERSITY CHECK (G2)
# ---------------------------------------------------------------------------

# Manual GICS-2 sector map for tickers we expect to appear in ITC studies
# (abbreviated; sourced from public GICS classifications)
TICKER_SECTOR: dict[str, str] = {
    "AAPL": "45",  # IT
    "MSFT": "45",  # IT
    "GOOGL": "50", # Communication Services
    "META": "50",  # Communication Services
    "AMZN": "25",  # Consumer Discretionary
    "QCOM": "45",  # IT
    "INTC": "45",  # IT
    "NVDA": "45",  # IT
    "AMD":  "45",  # IT
    "AVGO": "45",  # IT
    "TXN":  "45",  # IT
    "MU":   "45",  # IT
    "MRVL": "45",  # IT
    "SWKS": "45",  # IT
    "QRVO": "45",  # IT
    "CRUS": "45",  # IT
    "SYNA": "45",  # IT
    "DIOD": "45",  # IT
    "SMTC": "45",  # IT
    "LSCC": "45",  # IT
    "MCHP": "45",  # IT
    "ON":   "45",  # IT
    "WOLF": "45",  # IT
    "COHR": "45",  # IT
    "NOK":  "45",  # IT
    "BB":   "45",  # IT
    "IBM":  "45",  # IT
    "ORCL": "45",  # IT
    "SAP":  "45",  # IT
    "CSCO": "45",  # IT
    "JNPR": "45",  # IT
    "NTGR": "45",  # IT
    "WDC":  "45",  # IT
    "STX":  "45",  # IT
    "XRX":  "45",  # IT
    "PHG":  "20",  # Industrials
    "ZBRA": "45",  # IT
    "DBD":  "45",  # IT
    "VYX":  "45",  # IT
    "SONY": "25",  # Consumer Discretionary
    "NTDOY": "25", # Consumer Discretionary
    "EA":   "25",  # Consumer Discretionary
    "TTWO": "25",  # Consumer Discretionary
    "ATVI": "25",  # Consumer Discretionary (pre-acquisition)
    "NFLX": "50",  # Communication Services
    "TSM":  "45",  # IT
    "ERIC": "45",  # IT
    "CAJ":  "45",  # IT
    "MSI":  "45",  # IT
    "IDCC": "45",  # IT
    "LUMENTUM": "45",
    "LITE": "45",  # IT
    "GLW":  "45",  # IT
    "HPQ":  "45",  # IT
    "HPE":  "45",  # IT
    "DELL": "45",  # IT
    "NLST": "45",  # IT
    # Industrials/auto/med
    "CAT":  "20",  # Industrials
    "DE":   "20",  # Industrials
    "GE":   "20",  # Industrials
    "HON":  "20",  # Industrials
    "ROK":  "20",  # Industrials
    "EMR":  "20",  # Industrials
    "ITW":  "20",  # Industrials
    "DHR":  "20",  # Industrials
    "MMM":  "20",  # Industrials
    "F":    "25",  # Consumer Discretionary (autos)
    "GM":   "25",  # Consumer Discretionary
    "TSLA": "25",  # Consumer Discretionary
    "TM":   "25",  # Consumer Discretionary
    "HMC":  "25",  # Consumer Discretionary
    "STLA": "25",  # Consumer Discretionary
    # Healthcare
    "ABT":  "35",  # Healthcare
    "BAX":  "35",  # Healthcare
    "BDX":  "35",  # Healthcare
    "BSX":  "35",  # Healthcare
    "EW":   "35",  # Healthcare
    "MDT":  "35",  # Healthcare
    "SYK":  "35",  # Healthcare
    "ZBH":  "35",  # Healthcare
    "JNJ":  "35",  # Healthcare
    "PFE":  "35",  # Healthcare
    "LLY":  "35",  # Healthcare
    "NVO":  "35",  # Healthcare
    "NVS":  "35",  # Healthcare
    "AZN":  "35",  # Healthcare
    "SNY":  "35",  # Healthcare
    # Materials / Chem
    "DD":   "15",  # Materials
    "DOW":  "15",  # Materials
}


def check_sector_diversity(par_df_or_cal: pd.DataFrame | None,
                           by_ticker: dict) -> dict:
    """G2: check that contributing tickers span >= 2 distinct GICS-2 sectors.

    Uses the by_ticker dict (which contains tickers with n >= 1 observations).
    Returns {sectors, n_sectors, pass, tickers_with_sector, tickers_missing_sector}.
    """
    tickers = list(by_ticker.keys())
    sectors: set[str] = set()
    with_sector: list[str] = []
    without_sector: list[str] = []
    for t in tickers:
        sec = TICKER_SECTOR.get(t)
        if sec:
            sectors.add(sec)
            with_sector.append(t)
        else:
            without_sector.append(t)

    return {
        "sectors":               sorted(sectors),
        "n_sectors":             len(sectors),
        "pass":                  len(sectors) >= 2,
        "tickers_with_sector":   with_sector,
        "tickers_missing_sector": without_sector,
    }


# ---------------------------------------------------------------------------
# GATE LOGIC
# ---------------------------------------------------------------------------

def apply_gates(results: dict) -> dict:
    """Apply G1 (|t|≥2, BH q≤0.10) and G2 (sector diversity) across 4 cells.

    Underpowered cells (n_dates < 25) cannot satisfy G1.
    """
    gated_cells = [c["variant"] for c in TRIAL_GRID]

    # Collect p-values for BH correction (exclude underpowered cells)
    pvals: dict[str, float] = {}
    for k in gated_cells:
        r = results.get(k, {})
        if r.get("underpowered"):
            continue
        nw = r.get("nw", {})
        p = nw.get("p")
        if p is not None and np.isfinite(p):
            pvals[k] = p

    bh = benjamini_hochberg(pvals, alpha=0.10) if pvals else {}

    # G1 evaluation
    g1_passing: list[str] = []
    g1_detail: dict[str, dict] = {}
    for k in gated_cells:
        r = results.get(k, {})
        if r.get("underpowered"):
            g1_detail[k] = {"status": "UNDERPOWERED",
                            "n_dates": r.get("n_dates", 0)}
            continue
        nw = r.get("nw", {})
        t = nw.get("t")
        mean_ar = r.get("mean_ar")
        if t is None or mean_ar is None:
            g1_detail[k] = {"status": "NO_DATA"}
            continue
        neg_dir    = mean_ar < 0
        abs_t_ge2  = abs(t) >= 2.0
        bh_pass    = bh.get(k, {}).get("reject", False)
        if neg_dir and abs_t_ge2 and bh_pass:
            g1_passing.append(k)
            g1_detail[k] = {"status": "PASS",
                            "mean_ar": mean_ar, "t": t,
                            "q": bh.get(k, {}).get("q")}
        else:
            g1_detail[k] = {
                "status": "FAIL",
                "mean_ar": mean_ar, "t": t,
                "neg_dir": neg_dir,
                "abs_t_ge2": abs_t_ge2,
                "bh_reject": bh_pass,
                "q": bh.get(k, {}).get("q"),
            }

    # G2 sector diversity (evaluated for any cell with data, not just G1 passing)
    # Per pre-registration: overall sector diversity using all contributing tickers
    # across all events in the study
    all_by_ticker: dict[str, dict] = {}
    for k in gated_cells:
        for tk, info in results.get(k, {}).get("by_ticker", {}).items():
            if tk not in all_by_ticker:
                all_by_ticker[tk] = info
    g2 = check_sector_diversity(None, all_by_ticker)

    # Verdict
    if not g1_passing:
        verdict = "NULL"
        all_underpowered = all(
            results.get(k, {}).get("underpowered", True) for k in gated_cells
        )
        if all_underpowered:
            verdict = "UNDERPOWERED_NULL"
    elif not g2["pass"]:
        verdict = "G1_PASS_G2_FAIL_SECTOR_CONCENTRATION"
    else:
        verdict = "CONFIRMER_CANDIDATE"

    return {
        "G1_passing":    g1_passing,
        "G1_pass":       len(g1_passing) > 0,
        "G1_detail":     g1_detail,
        "bh_results":    bh,
        "G2_sector":     g2,
        "G2_pass":       g2["pass"],
        "verdict":       verdict,
    }


# ---------------------------------------------------------------------------
# COVERAGE SUMMARY
# ---------------------------------------------------------------------------

def compute_coverage(rmap: dict, ev_e1: pd.DataFrame, ev_e2: pd.DataFrame,
                     all_tickers: list[str]) -> dict:
    """Summarize ticker map coverage and event counts."""
    mapped_tickers_a = {p: info for p, info in rmap.items()
                        if info["tier"] == "A" and info["ticker"]}
    mapped_tickers_x = {p: info for p, info in rmap.items()
                        if info["tier"] == "X"}

    e1_mapped = ev_e1[ev_e1["ticker"] != ""] if not ev_e1.empty else pd.DataFrame()
    e2_mapped = ev_e2[ev_e2["ticker"] != ""] if not ev_e2.empty else pd.DataFrame()

    return {
        "n_patterns_tier_a": len(mapped_tickers_a),
        "n_patterns_tier_x": len(mapped_tickers_x),
        "distinct_us_tickers_in_map": len({info["ticker"] for info in mapped_tickers_a.values()}),
        "e1_total_respondent_rows": len(ev_e1),
        "e1_mapped_ticker_rows":   len(e1_mapped),
        "e1_unique_tickers":       sorted(e1_mapped["ticker"].unique().tolist()) if not e1_mapped.empty else [],
        "e2_total_respondent_rows": len(ev_e2),
        "e2_mapped_ticker_rows":    len(e2_mapped),
        "e2_unique_tickers":        sorted(e2_mapped["ticker"].unique().tolist()) if not e2_mapped.empty else [],
        "tickers_with_prices":      sorted(t for t in all_tickers if
                                           (PRICE_DAY_DIR / f"{t}.parquet").exists() or
                                           (PRICE_DEEP_DIR / f"{t}.parquet").exists()),
    }


# ---------------------------------------------------------------------------
# REPORT WRITING
# ---------------------------------------------------------------------------

def _fmt_nw(nw: dict) -> str:
    if not nw or nw.get("t") is None:
        return "n/a (insufficient observations)"
    return (f"mean={nw.get('mean', 'n/a'):.5f}, "
            f"HAC-t={nw.get('t', 'n/a'):.3f}, "
            f"p={nw.get('p', 'n/a'):.4f}, n={nw.get('n', 'n/a')}")


def write_report(results: dict, gates: dict, coverage: dict,
                 ev_e1: pd.DataFrame, ev_e2: pd.DataFrame) -> None:
    verdict      = gates["verdict"]
    verdict_label = {
        "NULL":                                  "NULL — no pre-registered gate passed",
        "UNDERPOWERED_NULL":                     "NULL (UNDERPOWERED) — all cells below n=25 threshold; descriptive only",
        "CONFIRMER_CANDIDATE":                   "CONFIRMER CANDIDATE — G1 + G2 passed",
        "G1_PASS_G2_FAIL_SECTOR_CONCENTRATION":  "PARTIAL — G1 passed but G2 (sector diversity) failed",
    }.get(verdict, verdict)

    r_e1_5  = results.get("E1_institution_5d", {})
    r_e1_21 = results.get("E1_institution_21d", {})
    r_e2_5  = results.get("E2_adverse_5d", {})
    r_e2_21 = results.get("E2_adverse_21d", {})

    def _power_label(r: dict) -> str:
        if r.get("underpowered"):
            return f"UNDERPOWERED (n_dates={r.get('n_dates', 0)}, need≥{UNDERPOWERED_N})"
        return f"powered (n_dates={r.get('n_dates', 0)})"

    lines = [
        "# W2-153 USITC Section 337 Exclusion Risk — Phase-0 Event Study",
        "",
        f"**Date:** {date.today().isoformat()}  ",
        f"**Family:** `{FAMILY}`  ",
        f"**VERDICT: {verdict_label}**",
        "",
        "> **In plain English:** Section 337 of the Tariff Act allows the ITC to issue",
        "> exclusion orders (import bans) against foreign companies infringing US patents.",
        "> This study asks: when the ITC names a US-listed company's products or a",
        "> US-listed respondent in a 337 investigation, do that company's shares",
        "> systematically underperform the market over the following 5 and 21 trading days?",
        "> Two event types are tested: (1) the formal institution of an investigation,",
        "> and (2) an adverse final determination finding a violation. Both are predicted",
        "> to drive negative beta-adjusted abnormal returns. If a gate is marked",
        "> UNDERPOWERED (fewer than 25 calendar-date observations), the result is",
        "> descriptive only — no promotion claim is made.",
        "",
        "---",
        "",
        "## 1. Pre-Registered Design",
        "",
        f"**Family:** `{FAMILY}` (4 gated cells, logged before results)  ",
        "**Direction:** NEGATIVE (exclusion-order risk → stock underperformance)  ",
        "",
        "| Cell | Event | Forward window | PIT fence | Power gate |",
        "|------|-------|---------------|-----------|------------|",
        f"| E1_institution_5d  | Institution notice (FR pub) | 5 td  | pub+1 BD | n≥{UNDERPOWERED_N} calendar dates |",
        f"| E1_institution_21d | Institution notice (FR pub) | 21 td | pub+1 BD | n≥{UNDERPOWERED_N} calendar dates |",
        f"| E2_adverse_5d      | Adverse final determination | 5 td  | same day | n≥{UNDERPOWERED_N} calendar dates |",
        f"| E2_adverse_21d     | Adverse final determination | 21 td | same day | n≥{UNDERPOWERED_N} calendar dates |",
        "",
        "**Gate G1:** ≥1 cell negative, |HAC-t| ≥ 2, BH-FDR q ≤ 0.10 across 4 cells;",
        "  underpowered cells (n < 25) excluded from G1.  ",
        "**Gate G2:** contributing tickers span ≥ 2 distinct GICS-2 sectors (not-one-sector).",
        "",
        "**Amendment A1 (pre-registered before first run):** UNDERPOWERED flag",
        "  (n_dates < 25) — descriptive only, no gate claims.  ",
        "**Amendment A2 (pre-registered before first run):** Sector lookup uses",
        "  TICKER_SECTOR manual map; missing-sector tickers included in return stats",
        "  but excluded from sector count.",
        "",
        "---",
        "",
        "## 2. Data Coverage",
        "",
        f"**Price store:** massive_stock_day ({PRICE_DAY_START} → {PRICE_DAY_END}); ",
        "  stocks/ for tickers with deeper history.  ",
        "**Event source:** Federal Register API — ITC institution notices and adverse",
        "  determination notices with '337-TA' in title/docket.  ",
        "**PIT fence:** E1 = FR publication date + 1 BD; E2 = FR publication date.  ",
        "",
        f"**Respondent map:** {coverage['n_patterns_tier_a']} US-listed patterns (Tier-A), "
        f"{coverage['n_patterns_tier_x']} private/foreign-listed (Tier-X, excluded).  ",
        f"**Distinct US tickers in map:** {coverage['distinct_us_tickers_in_map']}",
        "",
        "**Mapping coverage statement:**",
        "Many ITC 337 respondents are foreign companies (Asian OEM manufacturers,",
        "Korean conglomerates, European industrials) or private US entities — these",
        "are marked Tier-X and excluded from the return study. Only US-listed",
        "companies with tradable tickers contribute to the event study. Coverage is",
        "biased toward large-cap technology respondents (Apple, Qualcomm, etc.) where",
        "ITC cases are most frequently filed against US-listed companies.",
        "",
        "| Metric | E1 (institution) | E2 (adverse final) |",
        "|--------|-----------------|-------------------|",
        f"| Total respondent-notice rows | {coverage['e1_total_respondent_rows']} | {coverage['e2_total_respondent_rows']} |",
        f"| Rows with mapped US ticker | {coverage['e1_mapped_ticker_rows']} | {coverage['e2_mapped_ticker_rows']} |",
        f"| Unique US tickers mapped | {len(coverage['e1_unique_tickers'])} | {len(coverage['e2_unique_tickers'])} |",
        "",
        f"**E1 mapped tickers:** {', '.join(coverage['e1_unique_tickers']) or 'none'}  ",
        f"**E2 mapped tickers:** {', '.join(coverage['e2_unique_tickers']) or 'none'}  ",
        f"**Tickers with price data:** {', '.join(coverage['tickers_with_prices']) or 'none'}",
        "",
        "---",
        "",
        "## 3. Results",
        "",
        "### E1 — Institution of Investigation",
        "",
        "**Hypothesis:** ITC institution notice → negative beta-adjusted AR over 5d, 21d.",
        "**PIT:** FR publication date + 1 business day.",
        "",
        f"**E1_institution_5d** ({_power_label(r_e1_5)}):",
        f"  - Events (respondent-ticker pairs in window): {r_e1_5.get('n_events', 0)}",
        f"  - Calendar dates (post-collapse): {r_e1_5.get('n_dates', 0)}",
        f"  - Mean beta-adj AR: {r_e1_5.get('mean_ar', 'n/a')}%",
        f"  - NW HAC: {_fmt_nw(r_e1_5.get('nw', {}))}",
        "",
        f"**E1_institution_21d** ({_power_label(r_e1_21)}):",
        f"  - Events: {r_e1_21.get('n_events', 0)}",
        f"  - Calendar dates: {r_e1_21.get('n_dates', 0)}",
        f"  - Mean beta-adj AR: {r_e1_21.get('mean_ar', 'n/a')}%",
        f"  - NW HAC: {_fmt_nw(r_e1_21.get('nw', {}))}",
        "",
        "**Per-ticker breakdown (E1, in study window):**",
        "",
        "| Ticker | n events | Mean AR % |",
        "|--------|----------|-----------|",
    ]

    for t, info in sorted(r_e1_21.get("by_ticker", {}).items()):
        lines.append(f"| {t} | {info.get('n', 0)} | {info.get('mean_ar_pct', 'n/a')} |")

    lines += [
        "",
        "**Honest prior on E1:** Institution notices are forward-looking; the market",
        "may price patent litigation risk gradually as complaints are filed (before",
        "the FR notice). Some respondents are named in cases where they are confident",
        "of success. The 5d window captures the immediate market reaction; 21d captures",
        "the medium-term settlement/order-risk repricing.",
        "",
        "### E2 — Adverse Final Determination",
        "",
        "**Hypothesis:** Commission finding of 337 violation → negative beta-adj AR",
        "over 5d, 21d. Final determinations are typically telegraphed by the ALJ's",
        "initial determination weeks earlier, so much of the news may be priced in.",
        "",
        f"**E2_adverse_5d** ({_power_label(r_e2_5)}):",
        f"  - Events: {r_e2_5.get('n_events', 0)}",
        f"  - Calendar dates: {r_e2_5.get('n_dates', 0)}",
        f"  - Mean beta-adj AR: {r_e2_5.get('mean_ar', 'n/a')}%",
        f"  - NW HAC: {_fmt_nw(r_e2_5.get('nw', {}))}",
        "",
        f"**E2_adverse_21d** ({_power_label(r_e2_21)}):",
        f"  - Events: {r_e2_21.get('n_events', 0)}",
        f"  - Calendar dates: {r_e2_21.get('n_dates', 0)}",
        f"  - Mean beta-adj AR: {r_e2_21.get('mean_ar', 'n/a')}%",
        f"  - NW HAC: {_fmt_nw(r_e2_21.get('nw', {}))}",
        "",
        "**Per-ticker breakdown (E2, in study window):**",
        "",
        "| Ticker | n events | Mean AR % |",
        "|--------|----------|-----------|",
    ]

    for t, info in sorted(r_e2_21.get("by_ticker", {}).items()):
        lines.append(f"| {t} | {info.get('n', 0)} | {info.get('mean_ar_pct', 'n/a')} |")

    lines += [
        "",
        "---",
        "",
        "## 4. Gate Verdicts",
        "",
        "### G1 — |HAC-t| ≥ 2, BH-FDR q ≤ 0.10, negative direction",
        "",
        "**BH correction (across powered cells only):**",
        "",
        "| Cell | n_dates | mean_AR% | HAC-t | p | q (BH) | H0 rejected |",
        "|------|---------|---------|-------|---|--------|-------------|",
    ]

    for k in [c["variant"] for c in TRIAL_GRID]:
        r = results.get(k, {})
        nw = r.get("nw", {})
        bh_entry = gates["bh_results"].get(k, {})
        up_note = " (UNDERPOWERED)" if r.get("underpowered") else ""
        t_str = f"{nw.get('t', 'n/a'):.3f}" if nw.get("t") is not None else "n/a"
        p_str = f"{nw.get('p', 'n/a'):.4f}" if nw.get("p") is not None else "n/a"
        q_str = f"{bh_entry.get('q', 'n/a'):.4f}" if bh_entry.get("q") is not None else "n/a"
        rej = "YES" if bh_entry.get("reject") else ("n/a" if r.get("underpowered") else "NO")
        lines.append(
            f"| {k}{up_note} | {r.get('n_dates', 0)} | {r.get('mean_ar', 'n/a')} "
            f"| {t_str} | {p_str} | {q_str} | {rej} |"
        )

    g1_pass = gates.get("G1_pass", False)
    g2_pass = gates.get("G2_pass", False)
    g2_info = gates.get("G2_sector", {})

    lines += [
        "",
        f"**G1 result: {'PASS' if g1_pass else 'FAIL'}**",
        f"  - Passing cells: {gates.get('G1_passing', []) or 'none'}",
    ]

    for k, d in gates.get("G1_detail", {}).items():
        status = d.get("status", "?")
        if status == "UNDERPOWERED":
            lines.append(f"  - {k}: UNDERPOWERED (n_dates={d.get('n_dates', 0)})")
        elif status == "PASS":
            lines.append(f"  - {k}: PASS (mean_ar={d.get('mean_ar', 'n/a')}%, t={d.get('t', 'n/a'):.3f}, q={d.get('q', 'n/a')})")
        elif status == "FAIL":
            lines.append(
                f"  - {k}: FAIL (mean_ar={d.get('mean_ar', 'n/a')}%, "
                f"t={d.get('t', 'n/a')}, neg_dir={d.get('neg_dir')}, "
                f"|t|≥2={d.get('abs_t_ge2')}, BH_reject={d.get('bh_reject')})"
            )

    lines += [
        "",
        "### G2 — Sector Diversity (≥2 GICS-2 sectors among contributing tickers)",
        "",
        f"**G2 result: {'PASS' if g2_pass else 'FAIL'}**  ",
        f"  - Sectors represented: {g2_info.get('sectors', [])}  ",
        f"  - Number of distinct GICS-2 sectors: {g2_info.get('n_sectors', 0)}  ",
        f"  - Tickers with sector code: {g2_info.get('tickers_with_sector', [])}  ",
        f"  - Tickers missing sector code (excluded from count): {g2_info.get('tickers_missing_sector', [])}",
        "",
        f"### FINAL VERDICT: **{verdict_label}**",
        "",
        "---",
        "",
        "## 5. PIT Assumptions and Caveats",
        "",
        "- **No look-ahead.** All thresholds and beta estimates use only data",
        "  available strictly before the event availability date.",
        "- **Price store covers 2021-07 → 2026-07.** ITC investigations go back to",
        "  the 1970s; events before 2021-07 are parsed but excluded from return study.",
        "  Any cell with n < 25 after the price window filter is flagged UNDERPOWERED.",
        "- **Respondent mapping is partial.** Most ITC 337 respondents are foreign",
        "  manufacturers or private US entities. The fraction of investigations with at",
        "  least one mappable US-listed respondent is estimated at 15–30% (varies by",
        "  technology sector). Mapping coverage is printed at runtime.",
        "- **Calendar-time collapse.** Same-day events are averaged to prevent",
        "  pseudo-replication from large complaints naming 10–30 respondents.",
        "- **Beta adjustment.** Trailing 252-day OLS beta vs SPY, PIT. Default = 1.0",
        "  if fewer than 60 trading days of overlap.",
        "- **Text parsing.** Respondent names are extracted by regex from raw FR",
        "  notice text. The parser may miss names with unusual formatting or",
        "  over-match on tangentially mentioned companies. Coverage counts are",
        "  conservative lower bounds.",
        "- **Investigation heterogeneity.** Not all 337 cases carry equal exclusion",
        "  risk. A complaint by a non-practicing entity (NPE/patent troll) against",
        "  Apple differs from a Qualcomm-Ericsson standards-essential patent dispute.",
        "  This study treats all institutions equally — a severity-stratified",
        "  follow-up would be the natural extension.",
        "",
        "---",
        "",
        "## 6. Nightly Wiring (for consolidation)",
        "",
        "This is a phase-0 standalone harness. No collector or nightly job is proposed",
        "unless the gates pass and this study advances to phase-1.",
        "",
        "If promoted, the wiring would be:",
        "  1. Weekly incremental fetch of new FR notices (institution + adverse).",
        "  2. Parse respondent names → map to tickers → append to events_e1/e2.",
        "  3. Nightly: compute beta-adjusted AR for events that have aged into their",
        "     forward window; update signal panel.",
        "  4. Signal consumed as a confirmer (display-only context overlay),",
        "     never as a direct scoring input.",
        "",
        "---",
        "",
        "## 7. Conclusion",
        "",
    ]

    if verdict == "UNDERPOWERED_NULL":
        lines += [
            "**All 4 gated cells are UNDERPOWERED (n < 25 calendar-date observations).**",
            "This reflects the fundamental challenge of this lane: most ITC 337 respondents",
            "are foreign companies or private entities. Among the mapped US-listed tickers,",
            "there are insufficient non-overlapping event dates in the 2021–2026 price window",
            "to power a formal gate test.",
            "",
            "**Descriptive observations (no gate claims):**",
        ]
        for k in [c["variant"] for c in TRIAL_GRID]:
            r = results.get(k, {})
            lines.append(
                f"  - {k}: n_dates={r.get('n_dates', 0)}, "
                f"mean_AR={r.get('mean_ar', 'n/a')}%, "
                f"{_fmt_nw(r.get('nw', {}))}"
            )
        lines += [
            "",
            "**Recommendation:** Do not promote. The signal cannot be powered without",
            "either (a) a deeper price history (stocks/ back to 2000) combined with a",
            "full historical FR document fetch, or (b) a broader ticker map capturing",
            "more US-listed respondents. File this as a null-but-worth-revisiting result.",
        ]
    elif verdict == "NULL":
        lines += [
            "No pre-registered gate passed. The ITC Section 337 institution and adverse",
            "determination events do not show statistically reliable negative beta-adjusted",
            "abnormal returns in the tested forward windows.",
            "",
            "Possible explanations:",
            "- **Already priced.** Patent litigation risk may be partially priced at",
            "  complaint filing (before FR institution notice), especially for tech majors.",
            "- **Sample composition.** The mapped US-listed respondents are predominantly",
            "  large-cap companies with strong balance sheets for whom a single ITC case",
            "  is a routine legal cost, not an existential threat.",
            "- **Heterogeneous cases.** Mixing NPE trolls, standards-essential disputes,",
            "  and genuine competitive IP battles dilutes any systematic effect.",
        ]
    elif verdict == "CONFIRMER_CANDIDATE":
        lines += [
            "G1 and G2 both passed. The flagged cells show negative beta-adjusted",
            "abnormal returns with |HAC-t| ≥ 2, survive BH-FDR q ≤ 0.10, and the",
            "contributing tickers span ≥ 2 GICS-2 sectors.",
            "",
            "**Next step:** Propose a phase-1 collector to extend the historical panel",
            "and confirm the signal on a pre-specified holdout period.",
        ]
    elif verdict == "G1_PASS_G2_FAIL_SECTOR_CONCENTRATION":
        lines += [
            "G1 passed but G2 (sector diversity) failed. The negative signal is",
            "driven by companies concentrated in a single sector. The effect may",
            "be sector-specific rather than a general ITC exclusion-risk premium.",
        ]

    lines += [
        "",
        "---",
        "",
        f"*Generated by scripts/w2153_itc337_phase0.py — lane A6, wave-2.*",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written: {REPORT_PATH}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> str:
    print("=" * 70)
    print("W2-153 USITC Section 337 Exclusion-Risk Phase-0")
    print("=" * 70)

    # Step 0: Log trial grid BEFORE computing results (house rule)
    print("\n[0] Logging trial grid to ledger (pre-results)...")
    led = TrialLedger(family=FAMILY)
    n_new = led.log_grid(TRIAL_GRID, family=FAMILY,
                         info_cutoff=str(PRICE_DAY_END),
                         note="pre-registered W2-153 phase-0 grid (A6 lane)")
    print(f"  Logged {n_new} new / {len(TRIAL_GRID)} total configs to family '{FAMILY}'")

    # Step 1: Load respondent map
    print("\n[1] Loading respondent map...")
    rmap = load_respondent_map()
    tier_a = {p: info for p, info in rmap.items() if info["tier"] == "A" and info["ticker"]}
    tier_x = {p: info for p, info in rmap.items() if info["tier"] == "X"}
    print(f"  Tier-A (US-listed): {len(tier_a)} patterns, "
          f"{len({info['ticker'] for info in tier_a.values()})} distinct tickers")
    print(f"  Tier-X (private/foreign): {len(tier_x)} patterns (excluded from returns)")

    # Step 2: Build event tables (fetch from Federal Register + parse texts)
    print("\n[2] Building E1 institution events...")
    ev_e1 = build_institution_events(rmap, ITC337_DIR)

    print("\n[3] Building E2 adverse final determination events...")
    ev_e2 = build_adverse_events(rmap, ITC337_DIR)

    # Step 3: Identify all tickers that appear in events
    all_mapped_tickers: list[str] = []
    for ev_df in (ev_e1, ev_e2):
        if not ev_df.empty:
            all_mapped_tickers.extend(ev_df["ticker"][ev_df["ticker"] != ""].unique().tolist())
    all_mapped_tickers = sorted(set(all_mapped_tickers))
    print(f"\n[4] All mapped tickers across both event types: {all_mapped_tickers}")

    # PRICE-STORE VERIFICATION (rule 3 in house rules)
    print("\n[4b] Verifying price store coverage per mapped ticker...")
    tickers_with_price: list[str] = []
    for t in all_mapped_tickers:
        found = False
        for d in (PRICE_DAY_DIR, PRICE_DEEP_DIR):
            p = d / f"{t}.parquet"
            if p.exists():
                df_check = pd.read_parquet(p)
                n = len(df_check)
                print(f"  {t}: {d.name} → {n} rows")
                found = True
                tickers_with_price.append(t)
                break
        if not found:
            print(f"  {t}: NO PRICE DATA FOUND", file=sys.stderr)

    # Step 4: Load prices
    print(f"\n[5] Loading prices for {len(tickers_with_price)} tickers + SPY...")
    close_df, ret_df = load_prices(tickers_with_price)
    print(f"  Price matrix: {close_df.shape[1]} tickers, {len(close_df)} days")
    if SPY in close_df.columns:
        print(f"  SPY positive control: {len(close_df[SPY].dropna())} rows, "
              f"last close={close_df[SPY].dropna().iloc[-1]:.2f}")
    else:
        print("  WARNING: SPY not in price matrix!", file=sys.stderr)

    # Step 5: Run event studies
    print("\n[6] Running event studies (calendar-time collapsed, per pre-registration)...")
    results: dict[str, dict] = {}
    for cell in TRIAL_GRID:
        k         = cell["variant"]
        ev_type   = cell["event"]
        fwd_days  = cell["fwd_days"]
        nw_lags   = NW_LAGS[k]
        ev_df     = ev_e1 if ev_type == "institution" else ev_e2

        # Filter to mapped tickers only
        if not ev_df.empty:
            ev_mapped = ev_df[ev_df["ticker"].isin(ret_df.columns)]
        else:
            ev_mapped = pd.DataFrame(columns=ev_df.columns if not ev_df.empty else
                                     ["inv_num", "doc_num", "event_date", "avail_date",
                                      "respondent", "ticker", "event_type"])

        print(f"  Running {k} (fwd={fwd_days}d, NW_lags={nw_lags}, "
              f"n_candidate_events={len(ev_mapped)})...")
        r = run_event_study(ev_mapped, ret_df, fwd_days, nw_lags)
        results[k] = r
        nw = r.get("nw", {})
        up_flag = " [UNDERPOWERED]" if r.get("underpowered") else ""
        print(f"    -> events={r['n_events']}, dates={r['n_dates']}{up_flag}, "
              f"mean_AR={r['mean_ar']}%, t={nw.get('t')}, p={nw.get('p')}")

    # Step 6: Apply gates
    print("\n[7] Applying pre-registered gates...")
    gates = apply_gates(results)
    print(f"  G1 pass: {gates['G1_pass']} | passing cells: {gates['G1_passing']}")
    print(f"  G2 sector: {gates['G2_sector'].get('n_sectors', 0)} sectors | "
          f"pass: {gates['G2_pass']}")
    print(f"  VERDICT: {gates['verdict']}")

    # Step 7: Coverage summary
    coverage = compute_coverage(rmap, ev_e1, ev_e2, all_mapped_tickers)

    # Step 8: Write report
    print("\n[8] Writing report...")
    write_report(results, gates, coverage, ev_e1, ev_e2)

    # Step 9: Print ledger delta
    print("\n[9] Ledger delta (last 6 lines of trial_ledger.jsonl):")
    ledger_path = ROOT / "data" / "trial_ledger.jsonl"
    if ledger_path.exists():
        with open(ledger_path) as f:
            all_lines = f.readlines()
        for ln in all_lines[-6:]:
            print(" ", ln.rstrip())

    print("\nDone. Verdict:", gates["verdict"])
    return gates["verdict"]


if __name__ == "__main__":
    main()
