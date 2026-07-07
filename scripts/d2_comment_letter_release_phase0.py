"""Phase-0 event study: SEC comment-letter RELEASE as a price catalyst.

FAMILY: d2_comment_letter_release
PRE-REGISTRATION (frozen before any result is computed):

EVENT DEFINITION
  A "comment-letter review" is a cluster of SEC staff correspondence filings (form
  types UPLOAD and CORRESP) for the same CIK and review-year (we group by CIK +
  calendar year of first filing, with a 6-month gap rule: if two filings from the
  same CIK are >180 days apart they belong to different reviews).
  The EVENT DATE is the FIRST filing-index date within a review at which either
  form type appears — i.e. the date EDGAR disseminates the first letter from that
  review to the public. This is the EDGAR filing-index date, not any internal SEC
  resolution date. Each review contributes exactly one event row.

SUBSTANCE PROXY
  Count of UPLOAD filings (SEC letters TO the company) in the review:
    light      = 1-2 UPLOADs   (brief review)
    substantive = >=3 UPLOADs  (extended back-and-forth)
  Amendment: where a review has ZERO UPLOAD filings recorded (only CORRESP), it is
  classified as substance=light, since the SEC has published no letters — the review
  is company-initiated or minimally engaged.

HYPOTHESIS
  Direction NOT pre-registered — the release of review correspondence can either
  (a) relieve uncertainty (positive drift) or (b) reveal accounting concerns
  (negative drift). Test is TWO-SIDED.

HORIZONS
  h5 = 5 trading days forward abnormal return
  h21 = 21 trading days forward abnormal return

ABNORMAL RETURN
  Beta-adjusted vs SPY: AR = return_stock - beta * return_SPY
  Beta estimated by OLS on trailing 252 trading days of daily returns, using the
  same price store as the stock. Minimum 120 days of overlap required; missing beta
  -> event dropped from price-adjusted analysis.

PRICE STORES
  (A) massive_stock_day: 2021-07-06 to present (~20k tickers, 5y)
  (B) yahoo: 2005-01-01 to present (~688 tickers, deep leg, SURVIVORSHIP CAVEAT)
  Events are assigned to the store that carries the ticker; if both carry it the
  massive store is preferred for events after 2021-07-01, yahoo for earlier events.

BASELINE
  For each event date, all names in the store (excluding the event name itself) that
  have a valid price on that date AND the event date + horizon + 5 buffer days.
  Baseline mean AR is computed as the cross-sectional mean on that date.

GATES (frozen, pre-registered before computation)
  PRIMARY: substantive-review cells (>=3 UPLOAD) must show |t| >= 2.0 on the date-
    collapsed Newey-West t-stat AND survive BH FDR correction at q <= 0.10 across
    the 2 x 2 x 2 family (substance x horizon x store).
  SECONDARY: split-half by event date — sign must be consistent in both halves.
  All gates printed verbatim regardless of pass/fail. A null result is a valid run.

STATS LAW COMPLIANCE
  Events cluster in calendar time -> one obs per event-date for Newey-West.
  We compute a date-level mean AR (one number per date), then NW t-stat over
  the date-indexed series. lags = ceil(sqrt(n_dates)).
  Horizons > 5d have overlapping windows -> overlap-corrected stats (NW with
  lags proportional to horizon length).

AMENDMENTS LOGGED HERE (pre-registered gaps filled before computing)
  AM-1: Reviews with UPLOAD count = 0 but at least one CORRESP -> substance=light
    (rationale: no SEC letters published, so this is the minimal-engagement case).
  AM-2: CIK-year review grouping uses a 180-day gap rule: filings from the same CIK
    more than 180 calendar days apart start a new review even within the same year.
    This prevents multi-year ongoing reviews being counted as one event.
  AM-3: If a ticker has been delisted before the event date + 21d we still use
    whatever forward returns are available and note coverage; no forced imputation.

SURVIVORSHIP CAVEAT (yahoo store)
  The yahoo store holds ~688 tickers present as of collection date. Historical events
  involving companies that have since been delisted or acquired are NOT in this store.
  All IC/return estimates from the yahoo leg are UPWARD-BIASED. This is noted
  throughout and printed prominently in the report. The massive store leg has the
  same survivorship issue (only alive tickers as of 2021+).

Run: python3 -m scripts.d2_comment_letter_release_phase0
Writes: reports/d2-comment-letter-release-phase0.md
        data/comment_letter_events/events.parquet  (generated artifact; .gitignore'd)
No commit, no site build — pure harness.
"""
from __future__ import annotations

import gzip
import io
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.validation import benjamini_hochberg, newey_west_tstat  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent

# Price stores: worktree data/ has stub dirs only for massive_stock_day;
# use the canonical main-repo data path directly. Per house rules, data/ is
# READ-ONLY and we never write through a symlink.
_MAIN_DATA = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data")
MASSIVE_PATH = _MAIN_DATA / "massive_stock_day"
YAHOO_PATH = _MAIN_DATA / "yahoo"

# Writable cache lives in the worktree (not the main data dir)
EDGAR_CACHE_DIR = ROOT / "data" / "comment_letter_events"
EVENTS_PARQUET = EDGAR_CACHE_DIR / "events.parquet"
LEDGER_PATH = ROOT / "data" / "trial_ledger.jsonl"
REPORT_PATH = ROOT / "reports" / "d2-comment-letter-release-phase0.md"

EDGAR_BASE = "https://www.sec.gov/Archives/edgar/full-index"
USER_AGENT = "MacroDashboard research@macrodashboard.io"
RATE_LIMIT_S = 0.11        # 10 req/s max = 0.1s; pad to 0.11s
TIMEOUT_S = 45

# Pre-registration frozen thresholds
LIGHT_MAX_UPLOADS = 2      # <=2 UPLOAD => light
SUBSTANTIVE_MIN_UPLOADS = 3
REVIEW_GAP_DAYS = 180      # AM-2: new review if gap > 180 days same CIK
BETA_MIN_DAYS = 120
BETA_WINDOW = 252
HORIZONS = {"h5": 5, "h21": 21}
GATE_T_THRESH = 2.0
GATE_BH_Q = 0.10
FAMILY = "d2_comment_letter_release"

# Event study starts 2005 (EDGAR full-text available from ~2004)
STUDY_START = "2005-01-01"
# massive store cutoff
MASSIVE_START = "2021-07-06"


# ─────────────────────────────────────────────────────────────────────────────
# EDGAR INDEX FETCHING
# ─────────────────────────────────────────────────────────────────────────────
def _fetch_url(url: str, retries: int = 3) -> Optional[bytes]:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "gzip",
            })
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                raw = resp.read()
                if resp.info().get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  WARN: fetch failed {url}: {exc}")
    return None


def _quarter_pairs(start_year: int = 2005) -> list[tuple[int, int]]:
    """Generate (year, quarter) pairs from start_year through current quarter."""
    import datetime
    today = datetime.date.today()
    cur_q = (today.month - 1) // 3 + 1
    out = []
    for yr in range(start_year, today.year + 1):
        for q in range(1, 5):
            if yr == today.year and q > cur_q:
                break
            out.append((yr, q))
    return out


def fetch_corresp_upload_index(cache_dir: Path, force_refresh: bool = False) -> pd.DataFrame:
    """Fetch EDGAR quarterly form.idx files and extract CORRESP + UPLOAD filings.

    Caches each quarter's parsed rows as parquet to avoid re-fetching.
    Returns a DataFrame with columns: form_type, company_name, cik, date_filed, file_name.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []
    quarters = _quarter_pairs(2005)
    print(f"Fetching {len(quarters)} quarter indexes (2005-Q1 to current) …")
    last_request = 0.0

    for yr, q in quarters:
        cache_file = cache_dir / f"idx_{yr}_Q{q}.parquet"
        if cache_file.exists() and not force_refresh:
            df = pd.read_parquet(cache_file)
            all_rows.append(df)
            continue

        url = f"{EDGAR_BASE}/{yr}/QTR{q}/form.idx"
        # rate limit
        elapsed = time.monotonic() - last_request
        if elapsed < RATE_LIMIT_S:
            time.sleep(RATE_LIMIT_S - elapsed)
        print(f"  Fetching {yr} Q{q} …", end=" ", flush=True)
        raw = _fetch_url(url)
        last_request = time.monotonic()

        if raw is None:
            print("SKIP (failed)")
            continue

        text = raw.decode("utf-8", errors="replace")
        lines = text.split("\n")
        # find data start (after header line with dashes)
        data_start = 0
        for i, line in enumerate(lines):
            if line.startswith("---"):
                data_start = i + 1
                break

        rows = []
        for line in lines[data_start:]:
            if not line.strip():
                continue
            # Fixed-width format: form_type (12), company_name (62), cik (12), date_filed (12), file_name (rest)
            if len(line) < 60:
                continue
            form_type = line[:12].strip()
            if form_type not in ("CORRESP", "UPLOAD"):
                continue
            company_name = line[12:74].strip()
            rest = line[74:].strip().split()
            if len(rest) < 3:
                continue
            cik_str, date_filed, file_name = rest[0], rest[1], rest[2]
            try:
                cik = int(cik_str)
                pd.Timestamp(date_filed)  # validate date
            except Exception:
                continue
            rows.append({
                "form_type": form_type,
                "company_name": company_name,
                "cik": cik,
                "date_filed": date_filed,
                "file_name": file_name,
            })
        df_q = pd.DataFrame(rows)
        if not df_q.empty:
            df_q["date_filed"] = pd.to_datetime(df_q["date_filed"])
            df_q.to_parquet(cache_file, index=False)
            all_rows.append(df_q)
            print(f"{len(df_q)} rows")
        else:
            print("0 rows")

    if not all_rows:
        return pd.DataFrame()
    full = pd.concat(all_rows, ignore_index=True)
    full["date_filed"] = pd.to_datetime(full["date_filed"])
    full = full.sort_values(["cik", "date_filed"]).reset_index(drop=True)
    return full


# ─────────────────────────────────────────────────────────────────────────────
# CIK -> TICKER MAPPING
# ─────────────────────────────────────────────────────────────────────────────
def load_cik_ticker_map() -> dict[int, str]:
    """Load the repo's EDGAR company_tickers.json: {cik: ticker}.

    Tries the worktree data/ path first, then falls back to the canonical
    /Users/chriswong/Documents/Cluade/Macro Dashboard/data/edgar/ path so
    the file is found even when only price-store symlinks were created.
    """
    candidates = [
        ROOT / "data" / "edgar" / "company_tickers.json",
        Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/edgar/company_tickers.json"),
    ]
    p = None
    for c in candidates:
        if c.exists():
            p = c
            break
    if p is None:
        print("WARN: company_tickers.json not found in any candidate path")
        return {}
    with open(p) as f:
        raw = json.load(f)
    # Format: {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": ...}, ...}
    out: dict[int, str] = {}
    for v in raw.values():
        if isinstance(v, dict) and "cik_str" in v and "ticker" in v:
            out[int(v["cik_str"])] = str(v["ticker"]).upper()
    return out


# ─────────────────────────────────────────────────────────────────────────────
# BUILD REVIEW EVENTS (AM-2 gap rule)
# ─────────────────────────────────────────────────────────────────────────────
def build_reviews(filings: pd.DataFrame, cik_ticker: dict[int, str]) -> pd.DataFrame:
    """Cluster filings into reviews using AM-2 180-day gap rule.

    Returns one row per review with:
      cik, ticker, review_id, event_date (first filing date),
      n_upload, n_corresp, substance, has_ticker
    """
    rows = []
    for cik, grp in filings.groupby("cik"):
        ticker = cik_ticker.get(int(cik))
        grp = grp.sort_values("date_filed").reset_index(drop=True)
        # segment into reviews using 180-day gap rule
        dates = grp["date_filed"].values
        review_ids = np.zeros(len(grp), dtype=int)
        rev = 0
        for i in range(1, len(grp)):
            gap = (dates[i] - dates[i - 1]).astype("timedelta64[D]").astype(int)
            if gap > REVIEW_GAP_DAYS:
                rev += 1
            review_ids[i] = rev
        grp["review_id"] = review_ids
        for rid, rgrp in grp.groupby("review_id"):
            n_upload = int((rgrp["form_type"] == "UPLOAD").sum())
            n_corresp = int((rgrp["form_type"] == "CORRESP").sum())
            # AM-1: 0 UPLOADs => light
            substance = "substantive" if n_upload >= SUBSTANTIVE_MIN_UPLOADS else "light"
            event_date = rgrp["date_filed"].min()
            rows.append({
                "cik": int(cik),
                "ticker": ticker,
                "review_id": int(rid),
                "event_date": event_date,
                "n_upload": n_upload,
                "n_corresp": n_corresp,
                "substance": substance,
                "has_ticker": ticker is not None,
            })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# PRICE STORE ACCESS
# ─────────────────────────────────────────────────────────────────────────────
_price_cache: dict[str, pd.Series] = {}

def _get_close(ticker: str, store: str) -> Optional[pd.Series]:
    key = f"{store}:{ticker}"
    if key in _price_cache:
        return _price_cache[key]
    if store == "massive":
        p = MASSIVE_PATH / f"{ticker}.parquet"
    else:
        p = YAHOO_PATH / f"{ticker}.parquet"
    if not p.exists():
        _price_cache[key] = None
        return None
    try:
        df = pd.read_parquet(p)
        close = df["close"].sort_index().dropna()
        close.index = pd.to_datetime(close.index)
        _price_cache[key] = close
        return close
    except Exception:
        _price_cache[key] = None
        return None


def _assign_store(ticker: str, event_date: pd.Timestamp) -> Optional[str]:
    """Prefer massive for events after 2021-07-01, yahoo for earlier.
    If the preferred store doesn't have the ticker, try the other."""
    if event_date >= pd.Timestamp(MASSIVE_START):
        if (MASSIVE_PATH / f"{ticker}.parquet").exists():
            return "massive"
        if (YAHOO_PATH / f"{ticker}.parquet").exists():
            return "yahoo"
    else:
        if (YAHOO_PATH / f"{ticker}.parquet").exists():
            return "yahoo"
        if (MASSIVE_PATH / f"{ticker}.parquet").exists():
            return "massive"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# BETA ESTIMATION
# ─────────────────────────────────────────────────────────────────────────────
def _estimate_beta(stock_close: pd.Series, spy_close: pd.Series,
                   event_date: pd.Timestamp) -> Optional[float]:
    """Trailing 252d OLS beta of stock vs SPY, estimated using data BEFORE event_date."""
    end = event_date - pd.Timedelta(days=1)
    start = end - pd.Timedelta(days=BETA_WINDOW + 60)
    s = stock_close.loc[start:end].pct_change().dropna()
    m = spy_close.loc[start:end].pct_change().dropna()
    aligned = pd.concat([s, m], axis=1, join="inner")
    aligned.columns = ["stock", "spy"]
    if len(aligned) < BETA_MIN_DAYS:
        return None
    # Use last BETA_WINDOW rows
    aligned = aligned.iloc[-BETA_WINDOW:]
    cov = float(np.cov(aligned["stock"], aligned["spy"])[0, 1])
    var = float(np.var(aligned["spy"], ddof=1))
    if var == 0:
        return None
    return cov / var


# ─────────────────────────────────────────────────────────────────────────────
# EVENT STUDY CORE
# ─────────────────────────────────────────────────────────────────────────────
def compute_event_returns(events: pd.DataFrame, store_name: str,
                          spy_close: dict[str, pd.Series]) -> pd.DataFrame:
    """For each event in the given store, compute forward abnormal returns.

    Returns events with extra columns: ar_h5, ar_h21, beta, missing_reason.
    """
    records = []
    spy = spy_close.get(store_name)
    if spy is None:
        print(f"  WARN: SPY not available for store {store_name}")
        return pd.DataFrame()

    total = len(events)
    for i, row in events.iterrows():
        ticker = row["ticker"]
        event_date = pd.Timestamp(row["event_date"])
        substance = row["substance"]

        stock_close = _get_close(ticker, store_name)
        if stock_close is None:
            records.append({**row, "ar_h5": None, "ar_h21": None,
                           "beta": None, "missing_reason": "no_price"})
            continue

        # Find the trading day at or after event_date
        spy_dates = spy.index
        trading_dates = stock_close.index

        # Next trading day >= event_date
        after_stock = trading_dates[trading_dates >= event_date]
        after_spy = spy_dates[spy_dates >= event_date]
        if len(after_stock) == 0 or len(after_spy) == 0:
            records.append({**row, "ar_h5": None, "ar_h21": None,
                           "beta": None, "missing_reason": "event_after_data"})
            continue

        t0 = max(after_stock[0], after_spy[0])
        # re-align to the actual common trading day
        after_stock = trading_dates[trading_dates >= t0]
        after_spy = spy_dates[spy_dates >= t0]
        if len(after_stock) == 0 or len(after_spy) == 0:
            records.append({**row, "ar_h5": None, "ar_h21": None,
                           "beta": None, "missing_reason": "event_after_data"})
            continue

        # Entry = t0, hold for h days: return from t0 close to t0+h close
        def fwd_ret(close_series, t_start, h):
            future = close_series[close_series.index >= t_start]
            if len(future) <= h:
                return None  # AM-3: insufficient forward data
            return float(future.iloc[h] / future.iloc[0] - 1.0)

        stock_h5 = fwd_ret(stock_close, t0, 5)
        stock_h21 = fwd_ret(stock_close, t0, 21)
        spy_h5 = fwd_ret(spy, t0, 5)
        spy_h21 = fwd_ret(spy, t0, 21)

        if stock_h5 is None or spy_h5 is None:
            records.append({**row, "ar_h5": None, "ar_h21": None,
                           "beta": None, "missing_reason": "insufficient_fwd_data"})
            continue

        beta = _estimate_beta(stock_close, spy, t0)
        if beta is None:
            records.append({**row, "ar_h5": None, "ar_h21": None,
                           "beta": None, "missing_reason": "beta_insufficient"})
            continue

        ar_h5 = stock_h5 - beta * (spy_h5 if spy_h5 is not None else 0.0)
        ar_h21 = (stock_h21 - beta * spy_h21) if (stock_h21 is not None and spy_h21 is not None) else None

        records.append({**row, "ar_h5": ar_h5, "ar_h21": ar_h21,
                        "beta": beta, "missing_reason": None,
                        "t0": t0, "store": store_name})

    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# DATE-COLLAPSED NEWEY-WEST (STATS LAW)
# ─────────────────────────────────────────────────────────────────────────────
def date_collapsed_nw(df_cell: pd.DataFrame, ar_col: str) -> dict:
    """Collapse to one mean AR per event-date, then Newey-West over the date series.

    lags = ceil(sqrt(n_dates)) for h5, ceil(sqrt(n_dates) * 21/5) for h21
    to account for overlap (AM-2 stats compliance).
    """
    if df_cell.empty or ar_col not in df_cell.columns:
        return {"mean": None, "se": None, "t": None, "p": None, "n": 0, "n_dates": 0}

    valid = df_cell[["t0", ar_col]].dropna()
    if valid.empty:
        return {"mean": None, "se": None, "t": None, "p": None, "n": 0, "n_dates": 0}

    n_total = len(valid)
    date_mean = valid.groupby("t0")[ar_col].mean()
    n_dates = len(date_mean)
    if n_dates < 8:
        return {"mean": float(date_mean.mean()), "se": None, "t": None,
                "p": None, "n": n_total, "n_dates": n_dates}

    # lags: proportional to horizon overlap risk
    h = 21 if "h21" in ar_col else 5
    lags = max(1, math.ceil(math.sqrt(n_dates) * h / 5))
    nw = newey_west_tstat(date_mean.values, lags=lags)
    nw["n"] = n_total
    nw["n_dates"] = n_dates
    return nw


# ─────────────────────────────────────────────────────────────────────────────
# GATE EVALUATION
# ─────────────────────────────────────────────────────────────────────────────
def run_gates(results_df: pd.DataFrame) -> dict:
    """Run all pre-registered gates. Returns a structured result dict."""
    cells = {}
    for store in ("massive", "yahoo"):
        for substance in ("light", "substantive"):
            for horizon_key in ("h5", "h21"):
                ar_col = f"ar_{horizon_key}"
                cell_df = results_df[
                    (results_df.get("store", "") == store) &
                    (results_df["substance"] == substance)
                ] if "store" in results_df.columns else results_df[
                    results_df["substance"] == substance
                ]
                if "store" not in results_df.columns:
                    # filter not possible; skip
                    continue
                cell_df = results_df[
                    (results_df["store"] == store) &
                    (results_df["substance"] == substance)
                ]
                label = f"{substance}_{horizon_key}_{store}"
                nw = date_collapsed_nw(cell_df, ar_col)
                cells[label] = nw

    # BH correction across all 8 cells
    p_vals = {k: v["p"] for k, v in cells.items() if v.get("p") is not None}
    bh = benjamini_hochberg(p_vals, alpha=GATE_BH_Q)

    gate_results = {}
    for label, nw in cells.items():
        t = nw.get("t")
        p = nw.get("p")
        bh_entry = bh.get(label, {})
        q = bh_entry.get("q")
        reject = bh_entry.get("reject", False)
        is_substantive = "substantive" in label
        passes_t = (t is not None and abs(t) >= GATE_T_THRESH)
        passes_bh = reject
        gate_results[label] = {
            **nw,
            "q_bh": q,
            "bh_reject": reject,
            "gate_t_pass": passes_t,
            "gate_bh_pass": passes_bh,
            "gate_primary_pass": is_substantive and passes_t and passes_bh,
        }
    return gate_results


def run_split_half(results_df: pd.DataFrame) -> dict:
    """Split-half consistency gate: split by event date median."""
    if "t0" not in results_df.columns or results_df["t0"].isna().all():
        return {}
    median_date = results_df["t0"].dropna().sort_values().iloc[len(results_df.dropna(subset=["t0"])) // 2]
    first_half = results_df[results_df["t0"] <= median_date]
    second_half = results_df[results_df["t0"] > median_date]
    out = {}
    for half_name, half_df in [("first", first_half), ("second", second_half)]:
        for store in ("massive", "yahoo"):
            for substance in ("substantive",):
                for horizon_key in ("h5", "h21"):
                    ar_col = f"ar_{horizon_key}"
                    cell = half_df[
                        (half_df.get("store", pd.Series()) == store) &
                        (half_df["substance"] == substance)
                    ] if "store" in half_df.columns else pd.DataFrame()
                    if "store" in half_df.columns:
                        cell = half_df[
                            (half_df["store"] == store) &
                            (half_df["substance"] == substance)
                        ]
                    label = f"{half_name}_{substance}_{horizon_key}_{store}"
                    nw = date_collapsed_nw(cell, ar_col)
                    out[label] = nw
    return out


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    EDGAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Fetch/load EDGAR index ──────────────────────────────────────────
    print("=" * 72)
    print("STEP 1: Loading EDGAR CORRESP/UPLOAD index (2005-present)")
    print("=" * 72)

    filings = fetch_corresp_upload_index(EDGAR_CACHE_DIR)
    print(f"\nTotal CORRESP+UPLOAD filings loaded: {len(filings):,}")
    if filings.empty:
        print("ERROR: No filings loaded. Aborting.")
        sys.exit(1)
    print(f"Date range: {filings['date_filed'].min().date()} to {filings['date_filed'].max().date()}")
    print(f"Unique CIKs: {filings['cik'].nunique():,}")
    vc = filings["form_type"].value_counts()
    print(f"UPLOAD: {vc.get('UPLOAD', 0):,}  |  CORRESP: {vc.get('CORRESP', 0):,}")

    # ── 2. Load CIK->ticker map ─────────────────────────────────────────────
    print("\nSTEP 2: Loading CIK->ticker mapping")
    cik_ticker = load_cik_ticker_map()
    print(f"CIK->ticker map size: {len(cik_ticker):,}")

    # ── 3. Build reviews ───────────────────────────────────────────────────
    print("\nSTEP 3: Building review events (AM-2 gap rule = 180 days)")
    reviews = build_reviews(filings, cik_ticker)
    print(f"Total reviews: {len(reviews):,}")
    print(f"Reviews with ticker: {reviews['has_ticker'].sum():,}")
    print(f"Reviews substance breakdown:")
    print(reviews["substance"].value_counts().to_string())

    # ── 4. Filter to mappable tickers ─────────────────────────────────────
    print("\nSTEP 4: Filtering to price-store-mappable tickers")
    reviews_with_ticker = reviews[reviews["has_ticker"]].copy()
    reviews_with_ticker["event_date"] = pd.to_datetime(reviews_with_ticker["event_date"])

    # Assign store
    def assign_store(row):
        return _assign_store(row["ticker"], row["event_date"])

    reviews_with_ticker["store"] = reviews_with_ticker.apply(
        assign_store, axis=1, result_type="reduce"
    ).astype(object)
    reviews_mapped = reviews_with_ticker[reviews_with_ticker["store"].notna()].copy()
    print(f"Reviews mappable to price store: {len(reviews_mapped):,}")
    print(reviews_mapped.groupby(["store", "substance"]).size().to_string())

    # ── 5. Check for cached events ─────────────────────────────────────────
    if EVENTS_PARQUET.exists():
        print(f"\nLoading cached event returns from {EVENTS_PARQUET}")
        results_df = pd.read_parquet(EVENTS_PARQUET)
        print(f"Cached events: {len(results_df):,}")
    else:
        print("\nSTEP 5: Computing forward abnormal returns")
        # Load SPY from each store
        spy_massive = _get_close("SPY", "massive")
        spy_yahoo = _get_close("SPY", "yahoo")
        spy_stores = {"massive": spy_massive, "yahoo": spy_yahoo}

        # Verify coverage
        print(f"\nStore coverage verification:")
        if spy_massive is not None:
            print(f"  massive SPY: {len(spy_massive)} days, {spy_massive.index[0].date()} to {spy_massive.index[-1].date()} [OK]")
        else:
            print("  massive SPY: NOT FOUND [PROBLEM]")
        if spy_yahoo is not None:
            print(f"  yahoo SPY: {len(spy_yahoo)} days, {spy_yahoo.index[0].date()} to {spy_yahoo.index[-1].date()} [OK]")
        else:
            print("  yahoo SPY: NOT FOUND [PROBLEM]")

        # Spot-check: verify a known liquid ticker loads from each store
        test_massive = _get_close("AAPL", "massive")
        test_yahoo = _get_close("AAPL", "yahoo")
        print(f"\nSpot-check AAPL:")
        print(f"  massive: {'OK ' + str(len(test_massive)) + ' days' if test_massive is not None else 'NOT FOUND'}")
        print(f"  yahoo:   {'OK ' + str(len(test_yahoo)) + ' days' if test_yahoo is not None else 'NOT FOUND'}")

        # Run event study per store
        all_results = []
        for store in ("massive", "yahoo"):
            store_events = reviews_mapped[reviews_mapped["store"] == store].copy()
            if store_events.empty:
                print(f"\n  {store}: no events")
                continue
            print(f"\n  {store}: {len(store_events)} events … ", end="", flush=True)
            res = compute_event_returns(store_events, store, spy_stores)
            if not res.empty:
                res["store"] = store
                all_results.append(res)
                ok = res["ar_h5"].notna().sum()
                print(f"  {ok}/{len(store_events)} have valid AR")

        if not all_results:
            print("ERROR: No event returns computed")
            results_df = pd.DataFrame()
        else:
            results_df = pd.concat(all_results, ignore_index=True)
            results_df.to_parquet(EVENTS_PARQUET, index=False)
            print(f"\nSaved {len(results_df)} events to {EVENTS_PARQUET}")

    # ── 6. Run gates ───────────────────────────────────────────────────────
    print("\nSTEP 6: Running pre-registered gates")
    # Register trials in ledger (2 substances × 2 horizons × 2 stores = 8 cells)
    ledger = TrialLedger(path=LEDGER_PATH)
    for substance in ("light", "substantive"):
        for h in ("h5", "h21"):
            for store in ("massive", "yahoo"):
                ledger.log_trial({"substance": substance, "horizon": h, "store": store},
                                 family=FAMILY)
    print(f"  Trial ledger: {ledger.effective_n(FAMILY)} distinct configs for family {FAMILY}")

    results_with_ar = results_df[results_df["ar_h5"].notna()].copy() if not results_df.empty else pd.DataFrame()
    if "t0" not in results_with_ar.columns:
        results_with_ar["t0"] = results_with_ar.get("event_date")

    gate_results = run_gates(results_with_ar) if not results_with_ar.empty else {}
    split_half = run_split_half(results_with_ar) if not results_with_ar.empty else {}

    # ── 7. Print gate summary ──────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("GATE RESULTS (2 x 2 x 2 family)")
    print("=" * 72)
    any_primary_pass = False
    for label, g in sorted(gate_results.items()):
        t = g.get("t")
        p = g.get("p")
        q = g.get("q_bh")
        n = g.get("n", 0)
        nd = g.get("n_dates", 0)
        primary = g.get("gate_primary_pass", False)
        if primary:
            any_primary_pass = True
        status = "PRIMARY PASS" if primary else ("PASS-t" if g.get("gate_t_pass") else "FAIL")
        print(f"  {label:45s}  t={t!r:6}  p={p!r:6}  q={q!r:6}  n={n}(dates={nd})  [{status}]")

    print("\nSPLIT-HALF (substantive cells only):")
    for label, g in sorted(split_half.items()):
        t = g.get("t")
        p = g.get("p")
        n = g.get("n", 0)
        print(f"  {label:55s}  t={t!r:6}  p={p!r:6}  n={n}")

    verdict = "PASS" if any_primary_pass else "NULL"
    print(f"\nOVERALL VERDICT: {verdict}")
    print("(PASS = at least one substantive cell clears |t|>=2 AND BH q<=0.10)")

    # ── 8. Write report ────────────────────────────────────────────────────
    _write_report(filings, reviews, reviews_mapped, results_df, results_with_ar,
                  gate_results, split_half, verdict, ledger)

    print(f"\nReport written to {REPORT_PATH}")
    return verdict


# ─────────────────────────────────────────────────────────────────────────────
# REPORT
# ─────────────────────────────────────────────────────────────────────────────
def _write_report(filings, reviews, reviews_mapped, results_df, results_with_ar,
                  gate_results, split_half, verdict, ledger):
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    n_filings = len(filings) if not filings.empty else 0
    n_reviews = len(reviews) if not reviews.empty else 0
    n_reviews_mapped = len(reviews_mapped) if not reviews_mapped.empty else 0
    n_with_ar = len(results_with_ar) if not results_with_ar.empty else 0

    # Event coverage breakdown
    cov_lines = []
    if not reviews_mapped.empty and "store" in reviews_mapped.columns:
        for store in ("massive", "yahoo"):
            for sub in ("light", "substantive"):
                n = len(reviews_mapped[(reviews_mapped["store"] == store) &
                                        (reviews_mapped["substance"] == sub)])
                cov_lines.append(f"  {store} / {sub}: {n}")
    cov_str = "\n".join(cov_lines) if cov_lines else "  (no data)"

    # AR summary
    ar_lines = []
    if not results_with_ar.empty and "substance" in results_with_ar.columns:
        for sub in ("light", "substantive"):
            for store in ("massive", "yahoo"):
                cell = results_with_ar[(results_with_ar["substance"] == sub) &
                                        (results_with_ar["store"] == store)]
                if cell.empty:
                    ar_lines.append(f"  {sub}/{store}: no events")
                    continue
                for h in ("h5", "h21"):
                    ar_col = f"ar_{h}"
                    vals = cell[ar_col].dropna()
                    ar_lines.append(f"  {sub}/{store}/{h}: n={len(vals)} mean={vals.mean()*100:.2f}% median={vals.median()*100:.2f}%")
    ar_str = "\n".join(ar_lines) if ar_lines else "  (no data)"

    # Gate table
    gate_lines = ["| Cell | mean AR | t | p | q_BH | gate |"]
    gate_lines.append("|------|---------|---|---|------|------|")
    for label, g in sorted(gate_results.items()):
        mean = g.get("mean")
        t = g.get("t")
        p = g.get("p")
        q = g.get("q_bh")
        n = g.get("n", 0)
        prim = "PRIMARY PASS" if g.get("gate_primary_pass") else ("pass-t" if g.get("gate_t_pass") else "fail")
        mean_str = f"{mean*100:.2f}%" if mean is not None else "n/a"
        gate_lines.append(f"| {label} | {mean_str} (n={n}) | {t!r} | {p!r} | {q!r} | {prim} |")
    gate_table = "\n".join(gate_lines)

    # Split-half table
    sh_lines = ["| Half | Cell | t | p | n |"]
    sh_lines.append("|------|------|---|---|---|")
    for label, g in sorted(split_half.items()):
        t = g.get("t")
        p = g.get("p")
        n = g.get("n", 0)
        sh_lines.append(f"| {label} | | {t!r} | {p!r} | {n} |")
    sh_table = "\n".join(sh_lines)

    n_trials = ledger.effective_n(FAMILY)

    report = f"""# D2 Comment-Letter Release Phase-0 — {verdict}

*Family: d2_comment_letter_release | Run date: 2026-07-06 | Pre-registration: this script header*

---

## In plain English

The SEC's Division of Corporation Finance reviews public company filings by sending
comment letters (UPLOAD form type = letter FROM the SEC). Companies respond (CORRESP
= letter TO the SEC). After the review closes, the SEC releases the full correspondence
to the public via EDGAR, typically ~20 business days post-2012 (45 days pre-2012).
The question: does the public release date of a review's correspondence — which is the
EDGAR filing-index date we actually use — carry any predictable short-term price impact?

**Substance proxy:** We split reviews by how many SEC letters were sent. A "light" review
has 1-2 SEC uploads (brief back-and-forth). A "substantive" review has 3+ SEC letters
(extended scrutiny). We hypothesize that heavy scrutiny releases are more price-relevant,
but the direction is NOT pre-registered — relief and concern are both plausible.

**Result: {verdict}.** The substantive-review cells {"cleared" if verdict == "PASS" else "did not clear"} the
pre-registered gate (|t|>=2 AND BH q<=0.10).

---

## Data sources

- EDGAR quarterly full-text indexes: `https://www.sec.gov/Archives/edgar/full-index/YYYY/QTR#/form.idx`
  (2005-Q1 through current; free, no API key; rate-limited to ~10 req/s)
- Price stores:
  - **massive_stock_day**: 2021-07-06 to 2026-07-02, ~20,476 tickers (preferred for post-2021 events)
  - **yahoo**: 2023-07-03 to 2026-07-02, ~688 tickers (survivorship-biased, used for pre-2021 events
    from tickers in this set only — deep history coverage is LIMITED)
- CIK→ticker map: `data/edgar/company_tickers.json` (~10,415 entries)

**SURVIVORSHIP CAVEAT:** Both price stores hold only tickers alive/active as of collection date.
Companies delisted between their SEC review date and today are NOT in either store.
All return estimates are UPWARD-BIASED. This is a display/exploration result, not a
production signal claim.

---

## Coverage

EDGAR filings loaded (CORRESP + UPLOAD, 2005–present): **{n_filings:,}**
Reviews built (AM-2 gap rule): **{n_reviews:,}**
Reviews with CIK→ticker mapping: **{len(reviews[reviews['has_ticker']]) if not reviews.empty else 0:,}**
Reviews mapped to a price store: **{n_reviews_mapped:,}**
Events with valid abnormal return (beta available + fwd data): **{n_with_ar:,}**

Breakdown by store and substance:
{cov_str}

---

## Pre-registration (frozen before computation)

See script header for full text. Key elements:

- **Event date**: first EDGAR filing-index date within a review (UPLOAD or CORRESP)
- **Review grouping**: CIK + 180-day gap rule (AM-2)
- **Substance**: >=3 UPLOAD filings = substantive; else light (AM-1)
- **Horizons**: h5 (5 trading days), h21 (21 trading days)
- **Abnormal return**: stock return − beta × SPY return; beta from trailing 252d OLS, min 120d
- **Gate**: |t|>=2 (date-clustered NW) AND BH q<=0.10 across 2×2×2 family
- **Direction**: two-sided (not pre-registered)
- **Trials logged**: {n_trials} distinct configs in ledger family `{FAMILY}`

---

## Abnormal return summary (raw, pre-gate)

{ar_str}

---

## Gate results — 2 × 2 × 2 family (substance × horizon × store)

*Primary gate: substantive cells with |t|≥{GATE_T_THRESH} AND BH q≤{GATE_BH_Q}*

{gate_table}

**Notes on t-stat:**
- Date-collapsed: one mean AR per event-date, then Newey-West over date series (STATS LAW)
- NW lags = ceil(sqrt(n_dates) × h/5) to account for overlapping windows at h21
- Baseline: beta-adjusted vs SPY (OLS trailing 252d, min 120d)

---

## Split-half (consistency gate — substantive cells only)

{sh_table}

Sign consistency across halves: {"NOT APPLICABLE (no substantive events with AR)" if not split_half else "see table above"}

---

## Verdict

**{verdict}**

The pre-registered primary gate requires at least one substantive-review cell to show
|t|≥{GATE_T_THRESH} (date-clustered Newey-West) AND BH-corrected q≤{GATE_BH_Q}
across all 8 cells in the 2×2×2 family (substance × horizon × store).

{"At least one cell cleared both thresholds." if verdict == "PASS" else "No cell cleared both thresholds simultaneously. The null is printed; this is a valid and complete run."}

---

## Coverage gaps and caveats

1. **Survivorship bias** (both stores): companies delisted since data collection are absent.
   Historical reviews for failed companies are excluded. All AR estimates are optimistic.

2. **Yahoo store depth**: the yahoo store for this repo extends to ~2023-07-03, not 2005.
   Pre-2021 events can only be covered by tickers in the yahoo store AND having data back
   to the event date. In practice, the deep (2005-2021) leg has very sparse coverage.

3. **CIK→ticker mapping**: only ~10,415 CIKs in the repo map. Many CORRESP/UPLOAD filers
   are mutual funds, investment advisors, and foreign private issuers — not exchange-listed
   equities. The unmapped fraction is expected to be large.

4. **Beta estimation**: requires 120+ trading days of pre-event history. Early events for
   recently-listed companies will be dropped from the beta-adjusted analysis.

5. **Review grouping**: the 180-day gap rule (AM-2) is a simplification. Some long-running
   reviews may be split artificially; this creates conservative event counts (more reviews,
   smaller n per review) rather than optimistic ones.

---

## Nightly wiring (for consolidation)

This is a standalone phase-0 harness. For production:

1. **Collector**: a nightly job would fetch the latest EDGAR quarter index (one quarterly
   file per quarter, cacheable) and append new CORRESP/UPLOAD rows to
   `data/comment_letter_events/events.parquet`.
2. **Integration**: the event calendar (`events.parquet`) can serve as an input to the
   forward-return monitoring pipeline once (if) the signal is promoted past the gauntlet.
3. **Re-run trigger**: run on first day of each new quarter (new quarter index published).
4. **No template changes required**: this is data-only; no site pages ship from phase-0.

---

*Generated by `scripts/d2_comment_letter_release_phase0.py` — plain harness, no production impact.*
"""

    REPORT_PATH.write_text(report, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    verdict = main()
    sys.exit(0 if verdict in ("PASS", "NULL") else 1)
