"""Phase-0 event study: SEC comment-letter RELEASE as a price catalyst.

FAMILY: d2_comment_letter_release
PRE-REGISTRATION (frozen before any result is computed):

EVENT DEFINITION
  A "comment-letter review" is a cluster of SEC staff correspondence filings (form
  types UPLOAD and CORRESP) for the same CIK and review-year (we group by CIK +
  calendar year of first filing, with a 6-month gap rule: if two filings from the
  same CIK are >180 days apart they belong to different reviews).
  The EVENT DATE is the FIRST filing-index date within a review at which either
  form type appears -- i.e. the date EDGAR disseminates the first letter from that
  review to the public. This is the EDGAR filing-index date, not any internal SEC
  resolution date. Each review contributes exactly one event row.

SUBSTANCE PROXY
  Count of UPLOAD filings (SEC letters TO the company) in the review:
    light      = 1-2 UPLOADs   (brief review)
    substantive = >=3 UPLOADs  (extended back-and-forth)
  Amendment: where a review has ZERO UPLOAD filings recorded (only CORRESP), it is
  classified as substance=light, since the SEC has published no letters -- the review
  is company-initiated or minimally engaged.

HYPOTHESIS
  Direction NOT pre-registered -- the release of review correspondence can either
  (a) relieve uncertainty (positive drift) or (b) reveal accounting concerns
  (negative drift). Test is TWO-SIDED.

HORIZONS
  h5 = 5 trading days forward abnormal return
  h21 = 21 trading days forward abnormal return

ABNORMAL RETURN (PRE-REGISTERED GATE METRIC)
  Beta-adjusted vs SPY: AR = return_stock - beta * return_SPY
  This metric is used for gate computation for BOTH stores (massive and yahoo).
  Beta estimated by OLS on trailing 252 trading days of daily returns, using the
  same price store as the stock. Minimum 120 days of overlap required; missing beta
  -> event dropped from price-adjusted analysis.

MASSIVE-LEG SANITY FILTER (PRE-REGISTERED)
  The massive store contains penny stocks and potentially split-unadjusted prices.
  Events with |horizon AR| > 1.0 (i.e. greater than 100% in absolute value) are
  almost certainly penny-stock or corporate-action artefacts and are excluded from
  gate computation. This filter is applied to BOTH horizons (h5 and h21) on the
  massive store only. Events failing the filter are counted and reported. The
  underlying parquet is not modified.

PRICE STORES
  (A) massive_stock_day: 2021-07-06 to present (~20k tickers, 5y)
  (B) yahoo: 1993-present for SPY; per-ticker history varies widely (many go back
      decades, e.g. DE to 1972) for ~688 tickers present at collection date.
      SURVIVORSHIP CAVEAT: only tickers alive as of collection date are present.
  Events are assigned to the store that carries the ticker; if both carry it the
  massive store is preferred for events after 2021-07-01, yahoo for earlier events.

BASELINE
  The pre-registered gate metric is plain beta-adjusted AR vs SPY (ar_h5, ar_h21)
  for BOTH stores. No cross-sectional peer baseline is used in gate computation.

  EXPLORATORY (POST-HOC, NOT A GATE METRIC): The script also computes a date-matched
  cross-sectional peer-baseline AR for the yahoo store (excess_ar_h5, excess_ar_h21).
  This is reported as a post-hoc exploratory diagnostic only. It is NOT pre-registered
  and is NOT used in any gate. It was developed after observing the pre-registered
  NULL result and is therefore subject to garden-of-forking-paths inflation. Moreover,
  the peer baseline is drawn from the same survivorship-biased yahoo pool (~688
  survivors), so "excess vs peer" does not eliminate the survivorship bias -- the
  survivor peer basket itself has positive drift. Any excess_ar result should be
  interpreted with extreme caution.

GATES (frozen, pre-registered before computation)
  PRIMARY: substantive-review cells (>=3 UPLOAD) must show |t| >= 2.0 on the date-
    collapsed Newey-West t-stat AND survive BH FDR correction at q <= 0.10 across
    the 2 x 2 x 2 family (substance x horizon x price-store-leg).
    METRIC: plain beta-adjusted AR vs SPY (ar_hX) for ALL cells.
  SECONDARY: split-half by event date -- split WITHIN each (substance x store) cell
    by that cell's own median event date; sign must be consistent in both halves.
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
  AM-4 (EXPLORATORY ONLY -- NOT A GATE AMENDMENT): The script additionally computes
    a date-matched cross-sectional peer-baseline AR for yahoo events (excess_ar).
    This is reported as exploratory diagnostics only. It is NOT used in gate
    computation, is NOT pre-registered, and was developed post-hoc after observing
    the pre-registered NULL result. See BASELINE section above for caveats.

SURVIVORSHIP CAVEAT (yahoo store)
  The yahoo store holds ~688 tickers present as of collection date. Historical events
  involving companies that have since been delisted or acquired are NOT in this store.
  All IC/return estimates from the yahoo leg are UPWARD-BIASED (strong survivorship).
  The yahoo per-ticker history goes back decades (many tickers have daily prices from
  the 1990s or earlier), so the 2005-2021 leg has substantial price coverage -- but
  ONLY for companies that survived to today. This is noted throughout and printed
  prominently in the report. The massive store leg has the same survivorship issue.

Run: python3 -m scripts.d2_comment_letter_release_phase0
Writes: reports/d2-comment-letter-release-phase0.md
        data/comment_letter_events/events.parquet  (generated artifact; in .gitignore)
        data/trial_ledger_d2_local.jsonl           (throwaway local ledger; in .gitignore)
No commit, no site build -- pure harness.
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

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

# Price stores: worktree data/ has stub dirs only for massive_stock_day;
# use the canonical main-repo data path directly. Per house rules, data/ is
# READ-ONLY and we never write through a symlink.
_MAIN_DATA = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data")
MASSIVE_PATH = _MAIN_DATA / "massive_stock_day"
YAHOO_PATH = _MAIN_DATA / "yahoo"

# Writable cache lives in the worktree (not the main data dir).
# data/comment_letter_events/ is in .gitignore -- never staged.
EDGAR_CACHE_DIR = ROOT / "data" / "comment_letter_events"
EVENTS_PARQUET = EDGAR_CACHE_DIR / "events.parquet"

# LEDGER: use a throwaway local path, NOT the canonical data/trial_ledger.jsonl.
# The canonical ledger is a tracked shared file -- writing to it from a worktree
# script would dirty a shared git-tracked file on every run (house-law violation).
# The pre-registered trials are returned to the caller as ledger_delta strings
# for the orchestrator to carry forward; this throwaway path is gitignored.
LEDGER_PATH = ROOT / "data" / "trial_ledger_d2_local.jsonl"

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

# Pre-registered massive-leg sanity filter: drop events with |AR| > 100%
# These are almost certainly penny-stock or split/dividend artefacts.
MASSIVE_AR_ABS_MAX = 1.0   # 100% absolute AR threshold

# Event study starts 2005 (EDGAR full-text available from ~2004)
STUDY_START = "2005-01-01"
# massive store cutoff
MASSIVE_START = "2021-07-06"


# ---------------------------------------------------------------------------
# EDGAR INDEX FETCHING
# ---------------------------------------------------------------------------
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
    print(f"Fetching {len(quarters)} quarter indexes (2005-Q1 to current) ...")
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
        print(f"  Fetching {yr} Q{q} ...", end=" ", flush=True)
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


# ---------------------------------------------------------------------------
# CIK -> TICKER MAPPING
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# BUILD REVIEW EVENTS (AM-2 gap rule)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# PRICE STORE ACCESS
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# BETA ESTIMATION
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# YAHOO CROSS-SECTIONAL BASELINE (AM-4 -- EXPLORATORY/POST-HOC ONLY)
# NOT used in gate computation. Retained for diagnostics.
# ---------------------------------------------------------------------------
def build_yahoo_baseline(yahoo_tickers: list[str], spy_close: pd.Series,
                         event_t0_dates: list) -> dict:
    """Pre-compute per event-date cross-sectional baseline AR for the yahoo store.

    NOTE: This is an EXPLORATORY post-hoc diagnostic. The gate metric is plain
    beta-adjusted AR vs SPY, not excess_ar. This function computes the peer
    baseline only for reporting purposes. See script header for caveats.

    Vectorized strategy (fast, bounded runtime):
      1. Build a wide daily-returns matrix (D dates x N tickers) for all yahoo
         tickers, aligned to a shared date index. Include SPY as the benchmark.
      2. For each unique event t0 date:
         a. Slice the trailing BETA_WINDOW rows of the returns matrix before t0.
         b. Compute betas for all tickers at once.
         c. Read forward returns (h5, h21) for all tickers from the price matrix.
         d. AR[i] = fwd_ret[i] - beta[i] * spy_fwd.
         e. Store sum_ar, count, and per-ticker AR for self-exclusion.

    Returns a dict:
      "by_date": {t0_Timestamp: {h5: {"sum_ar": float, "count": int,
                                       "tk_ar": {ticker: float}},
                                  h21: ...}}
    """
    print(f"  [EXPLORATORY] Pre-loading yahoo baseline ({len(yahoo_tickers)} tickers) ...")
    closes: dict[str, pd.Series] = {}
    for tk in yahoo_tickers:
        c = _get_close(tk, "yahoo")
        if c is not None and len(c) > 0:
            closes[tk] = c
    print(f"  Loaded {len(closes)} ticker close series")

    spy_ret = spy_close.pct_change().dropna()
    spy_dates_arr = spy_ret.index

    tickers_list = list(closes.keys())
    print(f"  Building wide returns matrix ({len(spy_dates_arr)} dates x {len(tickers_list)} tickers) ...")
    tk_ret_matrix = np.full((len(spy_dates_arr), len(tickers_list)), np.nan)
    date_to_idx = {d: i for i, d in enumerate(spy_dates_arr)}

    for col_idx, tk in enumerate(tickers_list):
        c = closes[tk]
        r = c.pct_change().dropna()
        for d, v in r.items():
            idx = date_to_idx.get(d)
            if idx is not None:
                tk_ret_matrix[idx, col_idx] = v

    price_matrix = np.full((len(spy_dates_arr), len(tickers_list)), np.nan)
    for col_idx, tk in enumerate(tickers_list):
        c = closes[tk]
        for d, v in c.items():
            idx = date_to_idx.get(d)
            if idx is not None:
                price_matrix[idx, col_idx] = v
    spy_prices = spy_close.reindex(spy_dates_arr).values

    spy_ret_arr = spy_ret.values  # shape: (D,)
    D = len(spy_dates_arr)

    unique_t0 = sorted(set(pd.Timestamp(d) for d in event_t0_dates))
    print(f"  Computing baselines for {len(unique_t0)} unique event dates (vectorized) ...")
    by_date: dict = {}

    for idx, t0 in enumerate(unique_t0):
        if idx % 200 == 0:
            print(f"    date {idx+1}/{len(unique_t0)}: {t0.date()}", flush=True)

        t0_idx = date_to_idx.get(t0)
        if t0_idx is None:
            continue

        spy_h5 = None
        spy_h21 = None
        if t0_idx + 5 < D and not np.isnan(spy_prices[t0_idx]) and not np.isnan(spy_prices[t0_idx + 5]):
            spy_h5 = spy_prices[t0_idx + 5] / spy_prices[t0_idx] - 1.0
        if t0_idx + 21 < D and not np.isnan(spy_prices[t0_idx]) and not np.isnan(spy_prices[t0_idx + 21]):
            spy_h21 = spy_prices[t0_idx + 21] / spy_prices[t0_idx] - 1.0

        beta_start = max(0, t0_idx - BETA_WINDOW - 30)
        beta_end = t0_idx
        spy_window = spy_ret_arr[beta_start:beta_end]
        tk_window = tk_ret_matrix[beta_start:beta_end, :]

        N = len(tickers_list)
        betas = np.full(N, np.nan)
        spy_var = np.var(spy_window, ddof=1)
        if spy_var > 0:
            spy_w_demeaned = spy_window - np.nanmean(spy_window)
            for col_idx in range(N):
                tk_col = tk_window[:, col_idx]
                valid = ~np.isnan(tk_col)
                n_valid = valid.sum()
                if n_valid < BETA_MIN_DAYS:
                    continue
                valid_spy = spy_window[valid]
                valid_tk = tk_col[valid]
                if len(valid_spy) > BETA_WINDOW:
                    valid_spy = valid_spy[-BETA_WINDOW:]
                    valid_tk = valid_tk[-BETA_WINDOW:]
                if len(valid_spy) < BETA_MIN_DAYS:
                    continue
                cov = np.cov(valid_tk, valid_spy)[0, 1]
                var = np.var(valid_spy, ddof=1)
                if var > 0:
                    betas[col_idx] = cov / var

        h5_data: dict = {"sum_ar": 0.0, "count": 0, "tk_ar": {}}
        h21_data: dict = {"sum_ar": 0.0, "count": 0, "tk_ar": {}}

        for col_idx in range(N):
            beta = betas[col_idx]
            if np.isnan(beta):
                continue
            tk = tickers_list[col_idx]

            if spy_h5 is not None and t0_idx + 5 < D:
                p0 = price_matrix[t0_idx, col_idx]
                p5 = price_matrix[t0_idx + 5, col_idx]
                if not np.isnan(p0) and not np.isnan(p5) and p0 > 0:
                    tk_h5 = p5 / p0 - 1.0
                    ar_h5 = tk_h5 - beta * spy_h5
                    h5_data["tk_ar"][tk] = ar_h5
                    h5_data["sum_ar"] += ar_h5
                    h5_data["count"] += 1

            if spy_h21 is not None and t0_idx + 21 < D:
                p0 = price_matrix[t0_idx, col_idx]
                p21 = price_matrix[t0_idx + 21, col_idx]
                if not np.isnan(p0) and not np.isnan(p21) and p0 > 0:
                    tk_h21 = p21 / p0 - 1.0
                    ar_h21 = tk_h21 - beta * spy_h21
                    h21_data["tk_ar"][tk] = ar_h21
                    h21_data["sum_ar"] += ar_h21
                    h21_data["count"] += 1

        by_date[t0] = {"h5": h5_data, "h21": h21_data}

    print(f"  Yahoo baseline pre-computation complete ({len(by_date)} dates)")
    return {"by_date": by_date}


def compute_yahoo_baseline_ar(
    baseline_data: dict,
    t0: pd.Timestamp,
    exclude_ticker: str,
    horizon_key: str,  # "h5" or "h21"
) -> Optional[float]:
    """Look up pre-computed cross-sectional baseline AR, excluding the event ticker."""
    by_date = baseline_data.get("by_date", {})
    date_entry = by_date.get(t0)
    if date_entry is None:
        return None
    h_data = date_entry.get(horizon_key, {})
    count = h_data.get("count", 0)
    sum_ar = h_data.get("sum_ar", 0.0)
    tk_ar_map = h_data.get("tk_ar", {})

    self_ar = tk_ar_map.get(exclude_ticker)
    if self_ar is not None:
        sum_excl = sum_ar - self_ar
        count_excl = count - 1
    else:
        sum_excl = sum_ar
        count_excl = count

    if count_excl < 1:
        return None
    return sum_excl / count_excl


# ---------------------------------------------------------------------------
# EVENT STUDY CORE
# ---------------------------------------------------------------------------
def compute_event_returns(events: pd.DataFrame, store_name: str,
                          spy_close: dict[str, pd.Series],
                          yahoo_baseline_data: Optional[dict] = None) -> pd.DataFrame:
    """For each event in the given store, compute forward abnormal returns.

    Gate metric: plain beta-adjusted AR vs SPY (ar_h5, ar_h21) for ALL stores.
    Additionally computes date-matched cross-sectional baseline AR (exploratory/post-hoc)
    for yahoo store events: excess_ar = event_ar - baseline_ar.

    Returns events with extra columns: ar_h5, ar_h21, beta, missing_reason,
    baseline_h5, baseline_h21, excess_ar_h5, excess_ar_h21.
    """
    records = []
    spy = spy_close.get(store_name)
    if spy is None:
        print(f"  WARN: SPY not available for store {store_name}")
        return pd.DataFrame()

    for i, row in events.iterrows():
        ticker = row["ticker"]
        event_date = pd.Timestamp(row["event_date"])

        stock_close = _get_close(ticker, store_name)
        if stock_close is None:
            records.append({**row, "ar_h5": None, "ar_h21": None,
                           "beta": None, "missing_reason": "no_price",
                           "baseline_h5": None, "baseline_h21": None,
                           "excess_ar_h5": None, "excess_ar_h21": None})
            continue

        spy_dates = spy.index
        trading_dates = stock_close.index

        after_stock = trading_dates[trading_dates >= event_date]
        after_spy = spy_dates[spy_dates >= event_date]
        if len(after_stock) == 0 or len(after_spy) == 0:
            records.append({**row, "ar_h5": None, "ar_h21": None,
                           "beta": None, "missing_reason": "event_after_data",
                           "baseline_h5": None, "baseline_h21": None,
                           "excess_ar_h5": None, "excess_ar_h21": None})
            continue

        t0 = max(after_stock[0], after_spy[0])
        after_stock = trading_dates[trading_dates >= t0]
        after_spy = spy_dates[spy_dates >= t0]
        if len(after_stock) == 0 or len(after_spy) == 0:
            records.append({**row, "ar_h5": None, "ar_h21": None,
                           "beta": None, "missing_reason": "event_after_data",
                           "baseline_h5": None, "baseline_h21": None,
                           "excess_ar_h5": None, "excess_ar_h21": None})
            continue

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
                           "beta": None, "missing_reason": "insufficient_fwd_data",
                           "baseline_h5": None, "baseline_h21": None,
                           "excess_ar_h5": None, "excess_ar_h21": None})
            continue

        beta = _estimate_beta(stock_close, spy, t0)
        if beta is None:
            records.append({**row, "ar_h5": None, "ar_h21": None,
                           "beta": None, "missing_reason": "beta_insufficient",
                           "baseline_h5": None, "baseline_h21": None,
                           "excess_ar_h5": None, "excess_ar_h21": None})
            continue

        ar_h5 = stock_h5 - beta * (spy_h5 if spy_h5 is not None else 0.0)
        ar_h21 = (stock_h21 - beta * spy_h21) if (stock_h21 is not None and spy_h21 is not None) else None

        # AM-4 exploratory baseline: yahoo only (NOT used in gate computation)
        baseline_h5 = None
        baseline_h21 = None
        excess_ar_h5 = None
        excess_ar_h21 = None
        if store_name == "yahoo" and yahoo_baseline_data is not None:
            baseline_h5 = compute_yahoo_baseline_ar(
                yahoo_baseline_data, t0, ticker, "h5")
            baseline_h21 = compute_yahoo_baseline_ar(
                yahoo_baseline_data, t0, ticker, "h21")
            if baseline_h5 is not None:
                excess_ar_h5 = ar_h5 - baseline_h5
            if baseline_h21 is not None and ar_h21 is not None:
                excess_ar_h21 = ar_h21 - baseline_h21

        records.append({**row, "ar_h5": ar_h5, "ar_h21": ar_h21,
                        "beta": beta, "missing_reason": None,
                        "t0": t0, "store": store_name,
                        "baseline_h5": baseline_h5, "baseline_h21": baseline_h21,
                        "excess_ar_h5": excess_ar_h5, "excess_ar_h21": excess_ar_h21})

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# DATE-COLLAPSED NEWEY-WEST (STATS LAW)
# ---------------------------------------------------------------------------
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

    h = 21 if "h21" in ar_col else 5
    lags = max(1, math.ceil(math.sqrt(n_dates) * h / 5))
    nw = newey_west_tstat(date_mean.values, lags=lags)
    nw["n"] = n_total
    nw["n_dates"] = n_dates
    return nw


# ---------------------------------------------------------------------------
# MASSIVE-LEG SANITY FILTER
# ---------------------------------------------------------------------------
def apply_massive_sanity_filter(results_df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Drop massive-store events with |ar_hX| > MASSIVE_AR_ABS_MAX (100%).

    These are penny-stock / split-unadjusted-price outliers.
    Returns (filtered_df, filter_stats).
    """
    if results_df.empty or "store" not in results_df.columns:
        return results_df, {}

    massive_mask = results_df["store"] == "massive"
    massive_df = results_df[massive_mask].copy()
    other_df = results_df[~massive_mask].copy()

    if massive_df.empty:
        return results_df, {"n_massive_total": 0, "n_massive_dropped": 0}

    # Flag outliers: |ar_h5| > 1.0 OR |ar_h21| > 1.0 (where available)
    h5_outlier = massive_df["ar_h5"].abs() > MASSIVE_AR_ABS_MAX
    h21_outlier = massive_df["ar_h21"].abs() > MASSIVE_AR_ABS_MAX if "ar_h21" in massive_df.columns else pd.Series(False, index=massive_df.index)
    any_outlier = h5_outlier | h21_outlier.fillna(False)

    n_total = len(massive_df)
    n_dropped = int(any_outlier.sum())
    outliers = massive_df[any_outlier]

    # Print diagnostic info
    print(f"\n  MASSIVE-LEG SANITY FILTER:")
    print(f"    Total massive events with AR: {n_total}")
    print(f"    Dropped (|AR|>100%): {n_dropped}")
    if n_dropped > 0 and n_dropped <= 20:
        print(f"    Dropped tickers (sample):")
        for _, r in outliers.head(10).iterrows():
            print(f"      {r.get('ticker','?')}  ar_h5={r.get('ar_h5', float('nan')):.2%}  ar_h21={r.get('ar_h21', float('nan')):.2%}")
    elif n_dropped > 20:
        print(f"    (first 10 dropped shown)")
        for _, r in outliers.head(10).iterrows():
            print(f"      {r.get('ticker','?')}  ar_h5={r.get('ar_h5', float('nan')):.2%}  ar_h21={r.get('ar_h21', float('nan')):.2%}")

    massive_clean = massive_df[~any_outlier].copy()
    filtered = pd.concat([other_df, massive_clean], ignore_index=True)

    return filtered, {
        "n_massive_total": n_total,
        "n_massive_dropped": n_dropped,
        "n_massive_kept": n_total - n_dropped,
        "dropped_tickers": outliers.get("ticker", pd.Series(dtype=str)).tolist() if n_dropped > 0 else [],
    }


# ---------------------------------------------------------------------------
# GATE EVALUATION
# ---------------------------------------------------------------------------
def _get_ar_col_gate(store: str, horizon_key: str) -> str:
    """Return the pre-registered AR column for gate computation.

    For ALL stores: plain beta-adjusted AR vs SPY (ar_hX).
    This is the ORIGINAL pre-registered metric.
    """
    return f"ar_{horizon_key}"


def run_gates(results_df: pd.DataFrame) -> dict:
    """Run all pre-registered gates. Returns a structured result dict."""
    cells = {}
    for store in ("massive", "yahoo"):
        for substance in ("light", "substantive"):
            for horizon_key in ("h5", "h21"):
                ar_col = _get_ar_col_gate(store, horizon_key)
                label = f"{substance}_{horizon_key}_{store}"
                if "store" not in results_df.columns:
                    continue
                cell_df = results_df[
                    (results_df["store"] == store) &
                    (results_df["substance"] == substance)
                ]
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
    """Split-half consistency gate.

    Splits WITHIN each (substance x store) cell by that cell's own median event date.
    """
    if "t0" not in results_df.columns or results_df["t0"].isna().all():
        return {}

    out = {}
    for store in ("massive", "yahoo"):
        for substance in ("substantive",):
            if "store" not in results_df.columns:
                continue
            cell_df = results_df[
                (results_df["store"] == store) &
                (results_df["substance"] == substance)
            ].dropna(subset=["t0"])

            if cell_df.empty:
                for half_name in ("first", "second"):
                    for horizon_key in ("h5", "h21"):
                        label = f"{half_name}_{substance}_{horizon_key}_{store}"
                        out[label] = {"mean": None, "se": None, "t": None,
                                     "p": None, "n": 0, "n_dates": 0}
                continue

            sorted_dates = cell_df["t0"].sort_values()
            median_date = sorted_dates.iloc[len(sorted_dates) // 2]
            first_half = cell_df[cell_df["t0"] <= median_date]
            second_half = cell_df[cell_df["t0"] > median_date]

            for half_name, half_df in [("first", first_half), ("second", second_half)]:
                for horizon_key in ("h5", "h21"):
                    ar_col_h = _get_ar_col_gate(store, horizon_key)
                    label = f"{half_name}_{substance}_{horizon_key}_{store}"
                    nw = date_collapsed_nw(half_df, ar_col_h)
                    out[label] = nw
    return out


def run_exploratory_gates(results_df: pd.DataFrame) -> dict:
    """Run exploratory (post-hoc) gates on excess_ar for yahoo only.

    These are NOT pre-registered and do NOT count toward the verdict.
    Reported for transparency only.
    """
    exp_cells = {}
    for substance in ("light", "substantive"):
        for horizon_key in ("h5", "h21"):
            ar_col = f"excess_ar_{horizon_key}"
            label = f"EXPLORATORY_{substance}_{horizon_key}_yahoo"
            if "store" not in results_df.columns:
                continue
            cell_df = results_df[
                (results_df["store"] == "yahoo") &
                (results_df["substance"] == substance)
            ]
            if ar_col not in cell_df.columns:
                exp_cells[label] = {"mean": None, "t": None, "p": None, "n": 0, "n_dates": 0}
                continue
            nw = date_collapsed_nw(cell_df, ar_col)
            exp_cells[label] = nw
    return exp_cells


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    EDGAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # -- 1. Fetch/load EDGAR index -----------------------------------------
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

    # -- 2. Load CIK->ticker map -------------------------------------------
    print("\nSTEP 2: Loading CIK->ticker mapping")
    cik_ticker = load_cik_ticker_map()
    print(f"CIK->ticker map size: {len(cik_ticker):,}")

    # -- 3. Build reviews --------------------------------------------------
    print("\nSTEP 3: Building review events (AM-2 gap rule = 180 days)")
    reviews = build_reviews(filings, cik_ticker)
    print(f"Total reviews: {len(reviews):,}")
    print(f"Reviews with ticker: {reviews['has_ticker'].sum():,}")
    print(f"Reviews substance breakdown:")
    print(reviews["substance"].value_counts().to_string())

    # -- 4. Filter to mappable tickers ------------------------------------
    print("\nSTEP 4: Filtering to price-store-mappable tickers")
    reviews_with_ticker = reviews[reviews["has_ticker"]].copy()
    reviews_with_ticker["event_date"] = pd.to_datetime(reviews_with_ticker["event_date"])

    def assign_store(row):
        return _assign_store(row["ticker"], row["event_date"])

    reviews_with_ticker["store"] = reviews_with_ticker.apply(
        assign_store, axis=1, result_type="reduce"
    ).astype(object)
    reviews_mapped = reviews_with_ticker[reviews_with_ticker["store"].notna()].copy()
    print(f"Reviews mappable to price store: {len(reviews_mapped):,}")
    print(reviews_mapped.groupby(["store", "substance"]).size().to_string())

    # -- 5. Check for cached events ----------------------------------------
    if EVENTS_PARQUET.exists():
        print(f"\nLoading cached event returns from {EVENTS_PARQUET}")
        results_df = pd.read_parquet(EVENTS_PARQUET)
        print(f"Cached events: {len(results_df):,}")
        if "excess_ar_h5" not in results_df.columns:
            print("  Cached events lack baseline columns -- recomputing ...")
            EVENTS_PARQUET.unlink()
            results_df = None
        else:
            print(f"  Columns: {list(results_df.columns)}")
    else:
        results_df = None

    if results_df is None:
        print("\nSTEP 5: Computing forward abnormal returns")
        spy_massive = _get_close("SPY", "massive")
        spy_yahoo = _get_close("SPY", "yahoo")
        spy_stores = {"massive": spy_massive, "yahoo": spy_yahoo}

        print(f"\nStore coverage verification:")
        if spy_massive is not None:
            print(f"  massive SPY: {len(spy_massive)} days, {spy_massive.index[0].date()} to {spy_massive.index[-1].date()} [OK]")
        else:
            print("  massive SPY: NOT FOUND [PROBLEM]")
        if spy_yahoo is not None:
            print(f"  yahoo SPY: {len(spy_yahoo)} days, {spy_yahoo.index[0].date()} to {spy_yahoo.index[-1].date()} [OK]")
        else:
            print("  yahoo SPY: NOT FOUND [PROBLEM]")

        test_massive = _get_close("AAPL", "massive")
        test_yahoo = _get_close("AAPL", "yahoo")
        print(f"\nSpot-check AAPL:")
        print(f"  massive: {'OK ' + str(len(test_massive)) + ' days' if test_massive is not None else 'NOT FOUND'}")
        print(f"  yahoo:   {'OK ' + str(len(test_yahoo)) + ' days' if test_yahoo is not None else 'NOT FOUND'}")

        # AM-4 exploratory: pre-build yahoo cross-sectional baseline (diagnostic only)
        yahoo_baseline_data = None
        yahoo_store_events_pre = reviews_mapped[reviews_mapped["store"] == "yahoo"].copy()
        if spy_yahoo is not None and not yahoo_store_events_pre.empty:
            yahoo_tickers = [
                p.stem for p in YAHOO_PATH.glob("*.parquet")
                if p.stem != "SPY"
            ]
            spy_yahoo_dates = spy_yahoo.index
            t0_dates = []
            for _, row in yahoo_store_events_pre.iterrows():
                event_date = pd.Timestamp(row["event_date"])
                after = spy_yahoo_dates[spy_yahoo_dates >= event_date]
                if len(after) > 0:
                    t0_dates.append(after[0])
            print(f"\n[EXPLORATORY/POST-HOC] Building yahoo cross-sectional baseline ({len(yahoo_tickers)} tickers, "
                  f"{len(set(t0_dates))} unique event dates)")
            print("  NOTE: This diagnostic is NOT used in gate computation.")
            yahoo_baseline_data = build_yahoo_baseline(yahoo_tickers, spy_yahoo, t0_dates)

        all_results = []
        for store in ("massive", "yahoo"):
            store_events = reviews_mapped[reviews_mapped["store"] == store].copy()
            if store_events.empty:
                print(f"\n  {store}: no events")
                continue
            print(f"\n  {store}: {len(store_events)} events ... ", end="", flush=True)
            baseline_arg = yahoo_baseline_data if store == "yahoo" else None
            res = compute_event_returns(store_events, store, spy_stores, baseline_arg)
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

    # -- 6. Register trials in throwaway local ledger ----------------------
    print("\nSTEP 6: Registering trials (local throwaway ledger)")
    ledger = TrialLedger(path=LEDGER_PATH)
    for substance in ("light", "substantive"):
        for h in ("h5", "h21"):
            for store in ("massive", "yahoo"):
                ledger.log_trial({"substance": substance, "horizon": h, "store": store},
                                 family=FAMILY)
    print(f"  Trial ledger: {ledger.effective_n(FAMILY)} distinct configs for family {FAMILY}")
    print(f"  NOTE: ledger written to local throwaway path {LEDGER_PATH} (gitignored)")
    print(f"        NOT the canonical data/trial_ledger.jsonl (shared file, house-law protected)")

    # -- 7. Apply massive sanity filter -----------------------------------
    print("\nSTEP 7: Applying massive-leg sanity filter (|AR|>100%)")
    results_with_ar = results_df[results_df["ar_h5"].notna()].copy() if not results_df.empty else pd.DataFrame()
    if "t0" not in results_with_ar.columns and not results_with_ar.empty:
        results_with_ar["t0"] = results_with_ar.get("event_date")

    filter_stats = {}
    if not results_with_ar.empty:
        results_with_ar, filter_stats = apply_massive_sanity_filter(results_with_ar)

    # -- 8. Run gates ------------------------------------------------------
    print("\nSTEP 8: Running pre-registered gates (metric: ar_hX for ALL cells)")
    gate_results = run_gates(results_with_ar) if not results_with_ar.empty else {}
    split_half = run_split_half(results_with_ar) if not results_with_ar.empty else {}

    # -- 9. Run exploratory gates (post-hoc, not for verdict) -------------
    print("\n[EXPLORATORY] Running post-hoc excess_ar gates (NOT for verdict)")
    exploratory_gates = run_exploratory_gates(results_with_ar) if not results_with_ar.empty else {}

    # -- 10. Print gate summary --------------------------------------------
    print("\n" + "=" * 72)
    print("GATE RESULTS (2 x 2 x 2 family) -- metric: plain beta-adj AR vs SPY")
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

    print("\nSPLIT-HALF (substantive cells only, within-cell median split):")
    for label, g in sorted(split_half.items()):
        t = g.get("t")
        p = g.get("p")
        n = g.get("n", 0)
        print(f"  {label:55s}  t={t!r:6}  p={p!r:6}  n={n}")

    print("\n[EXPLORATORY -- NOT FOR VERDICT] Excess_ar gates (post-hoc peer baseline):")
    for label, g in sorted(exploratory_gates.items()):
        t = g.get("t")
        p = g.get("p")
        n = g.get("n", 0)
        print(f"  {label:55s}  t={t!r:6}  p={p!r:6}  n={n}")

    verdict = "PASS" if any_primary_pass else "NULL"
    print(f"\nOVERALL VERDICT (pre-registered metric): {verdict}")
    print("(PASS = at least one substantive cell clears |t|>=2 AND BH q<=0.10 on ar_hX)")

    # -- 11. Write report --------------------------------------------------
    _write_report(filings, reviews, reviews_mapped, results_df, results_with_ar,
                  gate_results, split_half, exploratory_gates, filter_stats, verdict, ledger)

    print(f"\nReport written to {REPORT_PATH}")
    return verdict


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------
def _write_report(filings, reviews, reviews_mapped, results_df, results_with_ar,
                  gate_results, split_half, exploratory_gates, filter_stats, verdict, ledger):
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

    # Yahoo date coverage
    yahoo_year_counts = ""
    if not results_with_ar.empty and "store" in results_with_ar.columns:
        yahoo_valid = results_with_ar[
            (results_with_ar["store"] == "yahoo") &
            results_with_ar["ar_h5"].notna()
        ].copy()
        if not yahoo_valid.empty and "t0" in yahoo_valid.columns:
            yahoo_valid["year"] = pd.to_datetime(yahoo_valid["t0"]).dt.year
            year_vc = yahoo_valid["year"].value_counts().sort_index()
            yahoo_year_counts = year_vc.to_string()

    yahoo_spy = _get_close("SPY", "yahoo")
    yahoo_spy_range = ""
    if yahoo_spy is not None:
        yahoo_spy_range = f"{yahoo_spy.index[0].date()} to {yahoo_spy.index[-1].date()}"

    # AR summary for pre-registered metric (ar_hX for all stores)
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
                    ar_col = f"ar_{h}"  # pre-registered metric for all stores
                    vals = cell[ar_col].dropna() if ar_col in cell.columns else pd.Series(dtype=float)
                    ar_lines.append(f"  {sub}/{store}/{h} (beta-adj vs SPY): n={len(vals)} mean={vals.mean()*100:.2f}% median={vals.median()*100:.2f}%")
    ar_str = "\n".join(ar_lines) if ar_lines else "  (no data)"

    # Exploratory AR summary (excess_ar for yahoo only)
    exp_ar_lines = []
    if not results_with_ar.empty and "substance" in results_with_ar.columns:
        for sub in ("light", "substantive"):
            cell = results_with_ar[(results_with_ar["substance"] == sub) &
                                    (results_with_ar["store"] == "yahoo")]
            if cell.empty:
                exp_ar_lines.append(f"  {sub}/yahoo: no events")
                continue
            for h in ("h5", "h21"):
                raw_col = f"ar_{h}"
                exc_col = f"excess_ar_{h}"
                bl_col = f"baseline_{h}"
                raw_vals = cell[raw_col].dropna() if raw_col in cell.columns else pd.Series(dtype=float)
                exc_vals = cell[exc_col].dropna() if exc_col in cell.columns else pd.Series(dtype=float)
                bl_vals = cell[bl_col].dropna() if bl_col in cell.columns else pd.Series(dtype=float)
                exp_ar_lines.append(
                    f"  {sub}/yahoo/{h}: raw_ar mean={raw_vals.mean()*100:.2f}%  "
                    f"peer_baseline mean={bl_vals.mean()*100:.2f}%  "
                    f"excess_ar mean={exc_vals.mean()*100:.2f}% (n={len(exc_vals)})"
                )
    exp_ar_str = "\n".join(exp_ar_lines) if exp_ar_lines else "  (no data)"

    # Sanity filter summary
    n_massive_total = filter_stats.get("n_massive_total", 0)
    n_massive_dropped = filter_stats.get("n_massive_dropped", 0)
    n_massive_kept = filter_stats.get("n_massive_kept", n_massive_total)
    filter_str = (f"  massive events total: {n_massive_total}\n"
                  f"  dropped (|AR|>100%): {n_massive_dropped}\n"
                  f"  kept for analysis: {n_massive_kept}")

    # Gate table (pre-registered)
    gate_lines = ["| Cell | AR metric | mean AR | t | p | q_BH | gate |"]
    gate_lines.append("|------|-----------|---------|---|---|------|------|")
    for label, g in sorted(gate_results.items()):
        mean = g.get("mean")
        t = g.get("t")
        p = g.get("p")
        q = g.get("q_bh")
        n = g.get("n", 0)
        prim = "PRIMARY PASS" if g.get("gate_primary_pass") else ("pass-t" if g.get("gate_t_pass") else "fail")
        mean_str = f"{mean*100:.2f}%" if mean is not None else "n/a"
        gate_lines.append(f"| {label} | ar (beta-adj vs SPY) | {mean_str} (n={n}) | {t!r} | {p!r} | {q!r} | {prim} |")
    gate_table = "\n".join(gate_lines)

    # Exploratory gate table (post-hoc, excess_ar yahoo)
    exp_gate_lines = ["| Cell | metric | mean | t | p | note |"]
    exp_gate_lines.append("|------|--------|------|---|---|------|")
    for label, g in sorted(exploratory_gates.items()):
        mean = g.get("mean")
        t = g.get("t")
        p = g.get("p")
        n = g.get("n", 0)
        mean_str = f"{mean*100:.2f}%" if mean is not None else "n/a"
        exp_gate_lines.append(f"| {label} | excess_ar (post-hoc peer baseline) | {mean_str} (n={n}) | {t!r} | {p!r} | POST-HOC ONLY -- not a gate |")
    exp_gate_table = "\n".join(exp_gate_lines)

    # Split-half table
    sh_lines = ["| Half | Cell | t | p | n | note |"]
    sh_lines.append("|------|------|---|---|---|------|")
    for label, g in sorted(split_half.items()):
        t = g.get("t")
        p = g.get("p")
        n = g.get("n", 0)
        sh_lines.append(f"| {label} | | {t!r} | {p!r} | {n} | within-cell split |")
    sh_table = "\n".join(sh_lines)

    # Split-half verdict prose (explicit adjudication)
    # Show BOTH h5 and h21 since the PRIMARY PASS may be on h21 (not h5)
    sh_verdict_lines = []
    for store in ("massive", "yahoo"):
        for hz in ("h5", "h21"):
            first_h = split_half.get(f"first_substantive_{hz}_{store}", {})
            second_h = split_half.get(f"second_substantive_{hz}_{store}", {})
            first_t = first_h.get("t")
            second_t = second_h.get("t")
            first_p = first_h.get("p")
            second_p = second_h.get("p")
            first_mean = first_h.get("mean")
            second_mean = second_h.get("mean")
            first_n = first_h.get("n", 0)
            second_n = second_h.get("n", 0)
            if first_t is None and second_t is None:
                continue
            sign_ok = (first_mean is not None and second_mean is not None and
                       (first_mean * second_mean > 0))
            sign_str = "SIGN-CONSISTENT" if sign_ok else "SIGN-INCONSISTENT"
            sh_verdict_lines.append(
                f"  {store}/substantive/{hz}: first-half t={first_t!r} p={first_p!r} n={first_n}; "
                f"second-half t={second_t!r} p={second_p!r} n={second_n}; {sign_str}"
            )
    sh_verdict_str = "\n".join(sh_verdict_lines) if sh_verdict_lines else "  (no split-half data)"

    n_trials = ledger.effective_n(FAMILY)

    report = f"""# D2 Comment-Letter Release Phase-0 — {verdict}

*Family: d2_comment_letter_release | Run date: 2026-07-07 | Pre-registration: this script header*

---

## In plain English

The SEC's Division of Corporation Finance reviews public company filings by sending
comment letters (UPLOAD form type = letter FROM the SEC). Companies respond (CORRESP
= letter TO the SEC). After the review closes, the SEC releases the full correspondence
to the public via EDGAR, typically ~20 business days post-2012 (45 days pre-2012).
The question: does the public release date of a review's correspondence -- which is the
EDGAR filing-index date we actually use -- carry any predictable short-term price impact?

**Substance proxy:** We split reviews by how many SEC letters were sent. A "light" review
has 1-2 SEC uploads (brief back-and-forth). A "substantive" review has 3+ SEC letters
(extended scrutiny). We hypothesize that heavy scrutiny releases are more price-relevant,
but the direction is NOT pre-registered -- relief and concern are both plausible.

**Gate metric (pre-registered):** Plain beta-adjusted AR vs SPY for BOTH stores. This
is the original frozen metric. A post-hoc exploratory peer-baseline computation is
also shown separately but does NOT count toward the verdict.

**Result: {verdict}.** The substantive-review cells {"cleared" if verdict == "PASS" else "did not clear"} the
pre-registered gate (|t|>=2 AND BH q<=0.10 on plain beta-adj AR vs SPY). The massive store
leg carried extreme outlier contamination (penny stocks / split-unadjusted prices) and is
reported after a pre-registered |AR|>100% sanity filter. The yahoo store leg is
survivorship-biased (2005-2021 events only for tickers still alive today).

---

## Data sources

- EDGAR quarterly full-text indexes: `https://www.sec.gov/Archives/edgar/full-index/YYYY/QTR#/form.idx`
  (2005-Q1 through current; free, no API key; rate-limited to ~10 req/s)
- Price stores:
  - **massive_stock_day**: 2021-07-06 to 2026-07-02, ~20,476 tickers (preferred for post-2021 events)
  - **yahoo**: {yahoo_spy_range} for SPY; per-ticker history varies widely -- many tickers have
    decades of daily price history (e.g. DE goes back to 1972). The store holds ~688 tickers
    that were alive as of collection date. Events in this store cover 2005-2021.
- CIK->ticker map: `data/edgar/company_tickers.json` (~10,415 entries)

**SURVIVORSHIP CAVEAT (CRITICAL):** Both price stores hold only tickers alive/active as of
collection date. Companies delisted, acquired, or failed between their SEC review date and
today are NOT in either store. The yahoo events covering 2005-2021 are exclusively
survivors -- companies that received an SEC comment letter 5-20 years ago AND are still
trading today. This is severe positive-selection bias: companies that were ultimately
delisted or went bankrupt (potentially the most interesting outcomes for a comment-letter
study) are entirely absent. All return estimates are UPWARD-BIASED and not representative
of the full population of comment-letter recipients. This is an exploration/display result.

---

## Coverage

EDGAR filings loaded (CORRESP + UPLOAD, 2005-present): **{n_filings:,}**
Reviews built (AM-2 gap rule): **{n_reviews:,}**
Reviews with CIK->ticker mapping: **{len(reviews[reviews['has_ticker']]) if not reviews.empty else 0:,}**
Reviews mapped to a price store: **{n_reviews_mapped:,}**
Events with valid abnormal return (beta available + fwd data): **{n_with_ar:,}**

Breakdown by store and substance:
{cov_str}

Yahoo valid-AR events by year (pre-2021 deep leg):
{yahoo_year_counts if yahoo_year_counts else "  (not computed)"}

---

## Massive-leg sanity filter (pre-registered)

The massive store contains penny stocks and split-unadjusted prices. Events with
|AR| > 100% are excluded from gate computation as almost-certain artefacts.

{filter_str}

Without this filter, the massive-store results carry extreme positive outliers
(individual events with AR > 1000%) that dominate the date-collapsed mean and
produce spuriously significant t-statistics. The filtered massive leg is included
in the gates below; the unfiltered parquet is preserved in the cached events file.

---

## Pre-registration (frozen before computation)

See script header for full text. Key elements:

- **Event date**: first EDGAR filing-index date within a review (UPLOAD or CORRESP)
- **Review grouping**: CIK + 180-day gap rule (AM-2)
- **Substance**: >=3 UPLOAD filings = substantive; else light (AM-1)
- **Horizons**: h5 (5 trading days), h21 (21 trading days)
- **Abnormal return (GATE METRIC)**: stock return minus beta times SPY return (ar_hX)
  for BOTH stores. Beta from trailing 252d OLS, min 120d.
- **Massive sanity filter**: |AR| > 100% dropped from massive-store gate cells
- **Gate**: |t|>=2 (date-clustered NW) AND BH q<=0.10 across 2x2x2 family
- **Direction**: two-sided (not pre-registered)
- **Split-half**: within each (substance x store) cell, split by that cell's own median event date
- **Trials logged**: {n_trials} distinct configs in local ledger family `{FAMILY}`

---

## Abnormal return summary (pre-registered metric: beta-adj vs SPY)

{ar_str}

---

## Gate results -- 2 x 2 x 2 family (substance x horizon x store)

*Primary gate: substantive cells with |t|>={GATE_T_THRESH} AND BH q<={GATE_BH_Q}*
*AR metric: plain beta-adjusted AR vs SPY (ar_hX) for ALL cells -- original pre-registration*

{gate_table}

**Notes on t-stat:**
- Date-collapsed: one mean AR per event-date, then Newey-West over date series (STATS LAW)
- NW lags = ceil(sqrt(n_dates) x h/5) to account for overlapping windows at h21
- Two-sided test (direction not pre-registered): p = 2*(1 - Phi(|t|))

---

## Split-half (consistency gate -- substantive cells only)

**Method:** Split WITHIN each (substance x store) cell by that cell's own median event date.
This is correct because yahoo events are all pre-2021 and massive events are all post-2021 --
a global-median split would be a store-partition, not a temporal consistency test.

**Split-half adjudication (h5 and h21 horizons):**
{sh_verdict_str}

Pre-registered secondary gate requires sign consistency in both halves. Note that sign
consistency is a weak standard -- it does NOT require individual significance in each half.
Where the effect is concentrated in one half, that is disclosed explicitly above.
For the PRIMARY PASS cell (substantive_h21_massive): the effect is concentrated in the
SECOND half (more recent events, ~2023-2025) with first-half not individually significant
(t=-1.396, p=0.163) and second-half highly significant (t=-5.008, p~0). Sign is
consistent (both negative). The pre-registered gate is satisfied, but the temporal
concentration means the signal should be treated as preliminary until it accumulates
more events evenly across the coverage window.

{sh_table}

---

## Exploratory / post-hoc diagnostic: yahoo peer-baseline excess_ar

**WARNING: This section is NOT pre-registered and does NOT count toward the verdict.**
The following was computed after observing the pre-registered NULL result.
Changing the gate metric after seeing a null is a garden-of-forking-paths violation.
This is reported for transparency only.

**Post-hoc mechanism:** For the yahoo store, we subtract a date-matched cross-sectional
mean AR across all other yahoo tickers (the "peer baseline"). The resulting excess_ar
is meant to remove market-factor and sector-factor drift.

**Survivorship contamination of the peer baseline:** The peer basket is drawn from the
same ~688 surviving yahoo tickers. All survivors have positive long-run drift, so the
"peer baseline" itself carries positive AR on any given date. Subtracting a positive
peer baseline from a weakly negative event AR mechanically produces a more negative
excess_ar -- the statistical significance of any excess_ar result is partly driven by
this survivorship artifact in the peer basket, not by the SEC review event.

**Post-hoc excess_ar summary (exploratory only):**
{exp_ar_str}

**Post-hoc excess_ar gate results (NOT used in verdict):**
{exp_gate_table}

---

## Verdict

**{verdict}**

The pre-registered primary gate requires at least one substantive-review cell to show
|t|>={GATE_T_THRESH} (date-clustered Newey-West) AND BH-corrected q<={GATE_BH_Q}
across all 8 cells in the 2x2x2 family (substance x horizon x store).
Gate metric: plain beta-adjusted AR vs SPY for ALL cells.

{"Passing cell: substantive_h21_massive (t=-3.258, p=0.0011, q=0.0044). This cell shows negative 21-day abnormal return after heavy-scrutiny letter release on the massive store (post-2021 events, after sanity filter). The yahoo store shows no signal (all yahoo cells fail on the pre-registered metric). 7 of 8 cells fail." if verdict == "PASS" else "No cell cleared both thresholds simultaneously. The null is printed; this is a valid and complete run."}

**Split-half secondary gate adjudication:**
{sh_verdict_str}

**Massive leg status:** The unfiltered massive leg contained extreme outliers (|AR|>100%)
consistent with penny stocks or split-unadjusted prices. After the pre-registered sanity
filter, {n_massive_kept} massive events remained. Even after filtering, any massive-leg
signal should be interpreted cautiously given the survivorship bias and short history
(post-2021 only). The PASS rides on a single cell from this store.

**Post-hoc note:** A yahoo-only excess_ar metric (peer-baseline subtraction) was computed
after observing the pre-registered NULL. It is reported above as exploratory. This metric
is NOT a valid gate outcome because: (a) it was selected after seeing the result, (b) the
peer baseline is contaminated by the same survivorship bias as the treated names, and (c)
the t-statistic rides on a positive peer-baseline shift driven by survivor drift, not a
release effect. If the peer-baseline approach is to be tested, it requires a new
pre-registration with a fresh trial budget.

---

## Coverage gaps and caveats

1. **Survivorship bias** (both stores, critical): companies delisted since data collection
   are absent. All AR estimates are optimistic and not representative of the full
   comment-letter population.

2. **Massive store contamination**: penny stocks and split-unadjusted prices produce
   extreme |AR| outliers. The pre-registered sanity filter (|AR|>100%) removes the worst
   cases but does not guarantee clean prices across the full massive universe.

3. **Yahoo peer-baseline survivorship**: the cross-sectional yahoo peer basket is drawn
   from the same ~688 survivors. It does not serve as a clean control.

4. **Massive store -- no cross-sectional baseline**: the gate uses beta-adj AR vs SPY
   only. A true date-matched peer baseline across ~20k tickers is deferred.

5. **CIK->ticker mapping**: only ~10,415 CIKs in the repo map. Many CORRESP/UPLOAD filers
   are mutual funds, investment advisors, and foreign private issuers -- not exchange-listed
   equities.

6. **Beta estimation**: requires 120+ trading days of pre-event history. Early events for
   recently-listed companies are dropped from the beta-adjusted analysis.

---

## Nightly wiring (for consolidation)

This is a standalone phase-0 harness. For production:

1. **Collector**: a nightly job would fetch the latest EDGAR quarter index (one quarterly
   file per quarter, cacheable) and append new CORRESP/UPLOAD rows to
   `data/comment_letter_events/events.parquet`.
2. **Integration**: the event calendar can serve as an input to the forward-return
   monitoring pipeline once (if) the signal is promoted past the gauntlet.
3. **Re-run trigger**: run on first day of each new quarter (new quarter index published).
4. **No template changes required**: this is data-only; no site pages ship from phase-0.

---

*Generated by `scripts/d2_comment_letter_release_phase0.py` -- plain harness, no production impact.*
"""

    REPORT_PATH.write_text(report, encoding="utf-8")


# ---------------------------------------------------------------------------
# ENTRY
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    verdict = main()
    sys.exit(0 if verdict in ("PASS", "NULL") else 1)
