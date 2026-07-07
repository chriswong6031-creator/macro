"""Block-trade (大宗交易) daily per-name tape archiver — F5-01 accrual infrastructure.

LANE: A10 (wave-5 data-build). No signal logic here; this module archives the raw
akshare block-trade feeds and builds a point-in-time (PIT) append-only store that
will feed F5-01 premium/discount backtesting.

=== TWO AKSHARE FEEDS — PROBE RESULTS (sampled 2013-2026, 24 date pairs) ===

  stock_dzjy_mrtj(start_date, end_date)  — PER-NAME DAILY AGGREGATE
    Columns: 交易日期, 证券代码, 证券简称, 涨跌幅, 收盘价, 成交价, 折溢率, 成交笔数,
             成交总量, 成交总额, 成交总额/流通市值
    History: serves from ~2005-01-04 (confirmed back to 2004-11-01; 2004-10 fails).
             Treats each (name, date) as a single aggregate row; 折溢率 = price ratio
             (cross_price÷close - 1, signed; positive = block crossed ABOVE close).
             Returns data consistently across all periods.
    Coverage: 50-400 rows/3-day window, declining in 2020 vs 2022+ uptick.

  stock_dzjy_mrmx(start_date, end_date)  — PER-TRADE DETAIL
    Columns: 交易日期, 证券代码, 证券简称, 成交价, 成交量, 成交额, 买方营业部, 卖方营业部
    History: serves from ~2012-09 (confirmed 2012-09; 2012-08 fails; 2013-04 ok).
             Includes buyer/seller brokerage (营业部) — critical for institutional
             vs retail attribution when both sides are "机构专用" (institutional).
    Coverage: 1-80 rows/3-day window; sparser for pre-2019 dates.

=== STORE LAYOUT ===

  data/china_block_tape/
    mrtj_YYYY.parquet   — yearly partitions for per-name aggregate (mrtj feed)
    mrmx_YYYY.parquet   — yearly partitions for per-trade detail (mrmx feed)
    sw_l1_map.parquet   — Shenwan L1 industry-level list (snapshot_date column).
                        NOTE: this is a HARDCODED 31-industry list with NO
                        per-stock → industry mapping (no ticker column). It
                        cannot link block-trade names to SW-L1 industries.
                        Akshare's constituent APIs (index_component_sw,
                        stock_industry_clf_hist_sw) were unavailable at build
                        time (schema mismatch / SSL errors). A future re-snapshot
                        is needed once per-stock constituent data becomes
                        accessible; SW classifications drift over time.

  Each yearly parquet is APPEND-ONLY by date: a re-run skips dates already stored.
  The PIT write-path: collect date D on day D+1 (or later); never overwrite an
  already-stored session so historical integrity is preserved.

=== COLUMNS STORED ===

  mrtj schema:
    date (str YYYY-MM-DD), ticker (str e.g. "000001.SZ"), name (str),
    chg_pct (float, 涨跌幅), close (float, 收盘价), cross_price (float, 成交价),
    premium_ratio (float, 折溢率 — cross_price/close - 1, raw ratio NOT percent;
                   positive means block crossed ABOVE the day's close),
    n_trades (int, 成交笔数), vol_lots (float, 成交总量), amt_wan (float, 成交总额 万元),
    amt_pct_mktcap (float, 成交总额/流通市值), asof (str YYYY-MM-DD, collection date)

  mrmx schema:
    date (str YYYY-MM-DD), ticker, name, cross_price (float), vol_lots (float),
    amt_wan (float, 成交额), buyer_branch (str, 买方营业部), seller_branch (str, 卖方营业部),
    asof (str YYYY-MM-DD)

=== EARLIEST BACKTEST DATE FOR F5-01 ===

  mrtj (premium/discount signal): 2005-01-04 — ~21 years of history.
    Practical signal start (enough daily breadth): 2010 (~15-50 names/day).
    Recommended F5-01 backtest start: 2010-01-04.

  mrmx (buyer/seller identity): 2012-09-01 — ~14 years.
    Recommended F5-01 buyer-attribution start: 2013-01-01.

=== NIGHTLY WIRING (for consolidation) ===

  In scripts/collect.py, add to the SERIAL collectors block (after china_zt_pool):

    # F5-01 block-tape archive
    from collectors.china_block_tape import refresh as refresh_block_tape
    _run("china_block_tape", refresh_block_tape)

  Or via the adapter pattern:
    Adapter("china_block_tape", refresh, hosts=["akshare"], serial=True)

  The refresh() function is resumable and idempotent: it skips dates already on disk
  and throttles at <= 2 req/s. Typical nightly delta: 1 date × 2 calls ≈ 2 seconds.

UNIT NOTES:
  - 折溢率 is stored as the RAW RATIO (e.g. -0.0699 for a 7% discount), NOT as percent.
    Engine consumers: multiply by 100 for display or pct-based thresholds.
  - 成交总额 is in 万元 (10,000 RMB). amt_wan column stores this directly.
    Downstream: amt_wan / 10000 gives 亿元; / 100 gives 百万元.
  - 成交总量 is in lots (手, 100 shares each). vol_lots stores this directly.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import logging
import time
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger("china_block_tape")

# ── Store location ─────────────────────────────────────────────────────────────
STORE = config.data_dir() / "china_block_tape"

# ── Throttle ───────────────────────────────────────────────────────────────────
THROTTLE_S: float = 0.55          # ≤ 2 req/s (generous margin for retries)

# ── Backfill parameters ────────────────────────────────────────────────────────
# mrtj history confirmed from 2005-01-04; mrmx from 2012-09-01.
# We archive mrmx from 2012-09-01, mrtj from 2005-01-04.
MRTJ_BACKFILL_START = "20050104"
MRMX_BACKFILL_START = "20120901"

# Chunk size for backfill requests (calendar days per API call).
# Keeping small avoids HTTP timeouts and makes progress resumable.
CHUNK_DAYS = 30


# ── Column normalisation ────────────────────────────────────────────────────────

def _col(cols: list[str], *needles: str) -> str | None:
    """First column whose name contains any needle (handles akshare column drift)."""
    for c in cols:
        s = str(c)
        if any(nd in s for nd in needles):
            return c
    return None


def _to_ticker(code: str | None) -> str | None:
    """Normalise 6-digit A-share code to 'NNNNNN.SH' / 'NNNNNN.SZ' / 'NNNNNN.BJ'."""
    if not code:
        return None
    s = str(code).strip()
    if not s or not s.isdigit():
        return None
    s = s.zfill(6)
    if s.startswith(("60", "68", "90", "51", "50")):
        return f"{s}.SH"
    elif s.startswith(("83", "87", "43")):
        return f"{s}.BJ"
    else:
        return f"{s}.SZ"


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> int | None:
    try:
        f = float(v)
        return None if pd.isna(f) else int(f)
    except (TypeError, ValueError):
        return None


# ── Parse feeds ────────────────────────────────────────────────────────────────

def _parse_mrtj(df: pd.DataFrame, asof: str) -> list[dict]:
    """Normalise a stock_dzjy_mrtj response into canonical rows."""
    if df is None or df.empty:
        return []
    cols = list(df.columns)
    date_c = _col(cols, "交易日期")
    code_c = _col(cols, "证券代码", "代码")
    name_c = _col(cols, "证券简称", "简称", "名称")
    chg_c  = _col(cols, "涨跌幅")
    close_c = _col(cols, "收盘价", "收盘")
    cross_c = _col(cols, "成交价")
    prem_c  = _col(cols, "折溢率")
    ntrd_c  = _col(cols, "成交笔数")
    vol_c   = _col(cols, "成交总量")
    amt_c   = _col(cols, "成交总额")
    pct_mc_c = _col(cols, "流通市值", "成交总额/流通市值")

    rows: list[dict] = []
    for _, r in df.iterrows():
        raw_code = str(r.get(code_c, "") or "").strip() if code_c else ""
        ticker = _to_ticker(raw_code)
        if not ticker:
            continue
        raw_date = str(r.get(date_c, "") or "").strip() if date_c else ""
        try:
            date_iso = pd.to_datetime(raw_date).strftime("%Y-%m-%d")
        except Exception:
            continue
        rows.append({
            "date": date_iso,
            "ticker": ticker,
            "name": str(r.get(name_c, "") or "").strip() if name_c else "",
            "chg_pct": _safe_float(r.get(chg_c)) if chg_c else None,
            "close": _safe_float(r.get(close_c)) if close_c else None,
            "cross_price": _safe_float(r.get(cross_c)) if cross_c else None,
            "premium_ratio": _safe_float(r.get(prem_c)) if prem_c else None,
            "n_trades": _safe_int(r.get(ntrd_c)) if ntrd_c else None,
            "vol_lots": _safe_float(r.get(vol_c)) if vol_c else None,
            "amt_wan": _safe_float(r.get(amt_c)) if amt_c else None,
            "amt_pct_mktcap": _safe_float(r.get(pct_mc_c)) if pct_mc_c else None,
            "asof": asof,
        })
    return rows


def _parse_mrmx(df: pd.DataFrame, asof: str) -> list[dict]:
    """Normalise a stock_dzjy_mrmx response into canonical rows."""
    if df is None or df.empty:
        return []
    cols = list(df.columns)
    date_c   = _col(cols, "交易日期")
    code_c   = _col(cols, "证券代码", "代码")
    name_c   = _col(cols, "证券简称", "简称", "名称")
    cross_c  = _col(cols, "成交价")
    vol_c    = _col(cols, "成交量")
    amt_c    = _col(cols, "成交额")
    buyer_c  = _col(cols, "买方营业部", "买方")
    seller_c = _col(cols, "卖方营业部", "卖方")

    rows: list[dict] = []
    for _, r in df.iterrows():
        raw_code = str(r.get(code_c, "") or "").strip() if code_c else ""
        ticker = _to_ticker(raw_code)
        if not ticker:
            continue
        raw_date = str(r.get(date_c, "") or "").strip() if date_c else ""
        try:
            date_iso = pd.to_datetime(raw_date).strftime("%Y-%m-%d")
        except Exception:
            continue
        rows.append({
            "date": date_iso,
            "ticker": ticker,
            "name": str(r.get(name_c, "") or "").strip() if name_c else "",
            "cross_price": _safe_float(r.get(cross_c)) if cross_c else None,
            "vol_lots": _safe_float(r.get(vol_c)) if vol_c else None,
            "amt_wan": _safe_float(r.get(amt_c)) if amt_c else None,
            "buyer_branch": str(r.get(buyer_c, "") or "").strip() if buyer_c else "",
            "seller_branch": str(r.get(seller_c, "") or "").strip() if seller_c else "",
            "asof": asof,
        })
    return rows


# ── Stored-dates helpers ────────────────────────────────────────────────────────

def _stored_dates_mrtj() -> set[str]:
    """All 'date' values already on disk across all yearly mrtj partitions."""
    dates: set[str] = set()
    for p in sorted(STORE.glob("mrtj_*.parquet")):
        try:
            dates |= set(pd.read_parquet(p, columns=["date"])["date"].astype(str).unique())
        except Exception:
            pass
    return dates


def _stored_dates_mrmx() -> set[str]:
    """All 'date' values already on disk across all yearly mrmx partitions."""
    dates: set[str] = set()
    for p in sorted(STORE.glob("mrmx_*.parquet")):
        try:
            dates |= set(pd.read_parquet(p, columns=["date"])["date"].astype(str).unique())
        except Exception:
            pass
    return dates


def _year_path(feed: str, year: int) -> Path:
    return STORE / f"{feed}_{year}.parquet"


def _append_rows(rows: list[dict], feed: str) -> int:
    """Append rows to the appropriate yearly partition; returns count written."""
    if not rows:
        return 0
    df_new = pd.DataFrame(rows)
    # Partition by year derived from date column
    df_new["_year"] = pd.to_datetime(df_new["date"]).dt.year
    written = 0
    for year, grp in df_new.groupby("_year"):
        grp = grp.drop(columns=["_year"])
        p = _year_path(feed, int(year))
        if p.exists():
            try:
                existing = pd.read_parquet(p)
                # Drop any rows whose date is already present (idempotent)
                existing_dates = set(existing["date"].astype(str).unique())
                grp = grp[~grp["date"].astype(str).isin(existing_dates)]
                if grp.empty:
                    continue
                combined = pd.concat([existing, grp], ignore_index=True)
            except Exception:
                combined = grp
        else:
            combined = grp
        combined.to_parquet(p, index=False)
        written += len(grp)
    return written


# ── Fetch helpers ───────────────────────────────────────────────────────────────

def _fetch_mrtj(start: str, end: str) -> pd.DataFrame | None:
    """One akshare call for the per-name aggregate table over [start, end]."""
    import akshare as ak
    try:
        df = ak.stock_dzjy_mrtj(start_date=start, end_date=end)
    except Exception as e:
        log.debug("mrtj %s–%s failed: %s", start, end, e)
        return None
    return df if df is not None and not df.empty else None


def _fetch_mrmx(start: str, end: str) -> pd.DataFrame | None:
    """One akshare call for the per-trade detail table over [start, end]."""
    import akshare as ak
    try:
        df = ak.stock_dzjy_mrmx(start_date=start, end_date=end)
    except Exception as e:
        log.debug("mrmx %s–%s failed: %s", start, end, e)
        return None
    return df if df is not None and not df.empty else None


# ── Date-chunk generator ────────────────────────────────────────────────────────

def _date_chunks(start_yyyymmdd: str, end_yyyymmdd: str, chunk_days: int = CHUNK_DAYS):
    """Yield (start, end) YYYYMMDD pairs in calendar-day chunks."""
    start = _dt.datetime.strptime(start_yyyymmdd, "%Y%m%d").date()
    end   = _dt.datetime.strptime(end_yyyymmdd,   "%Y%m%d").date()
    cur = start
    while cur <= end:
        chunk_end = min(cur + _dt.timedelta(days=chunk_days - 1), end)
        yield cur.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")
        cur = chunk_end + _dt.timedelta(days=1)


# ── SW L1 mapping snapshot ──────────────────────────────────────────────────────

def refresh_sw_l1_map() -> int:
    """Build / refresh the Shenwan L1 industry-level reference list.

    IMPORTANT LIMITATIONS:
      - This writes an INDUSTRY-LEVEL list only, NOT a per-stock constituent map.
      - There is NO ticker column: block-trade names cannot be mapped to SW-L1
        industries using this file alone.
      - The 31-industry list is derived from the hardcoded china_sectors.SW_L1 dict,
        not from a live akshare constituent query. Akshare's per-stock constituent
        APIs (index_component_sw, stock_industry_clf_hist_sw) were unavailable at
        build time due to schema mismatch / SSL certificate errors on swsresearch.com.
      - SW classifications DRIFT over time. This snapshot reflects the SW 2021
        L1 industry taxonomy as of the snapshot_date. A fresh re-snapshot is needed
        after any SW reclassification cycle (typically annual).

    Writes data/china_block_tape/sw_l1_map.parquet with columns:
      sw_code (str, e.g. '801010'), sw_code_si (str, e.g. '801010.SI'),
      cn_name (str), en_name (str), snapshot_date (str YYYY-MM-DD),
      pe_ttm (float, optional), pb (float, optional), div_pct (float, optional).

    Also enriches with live valuation data (PE/PB/div) from sw_index_first_info()
    if available. Returns number of industries written.
    """
    import akshare as ak

    # Import SW_L1 canonical dict from the existing sectors collector
    from collectors.china_sectors import SW_L1

    snapshot_date = _dt.date.today().isoformat()

    rows = []
    for code, (cn, en) in SW_L1.items():
        rows.append({
            "sw_code": code,
            "sw_code_si": f"{code}.SI",
            "cn_name": cn,
            "en_name": en,
            "snapshot_date": snapshot_date,
        })

    df = pd.DataFrame(rows)

    # Enrich with live valuation if available
    try:
        info = ak.sw_index_first_info()
        # Map code.SI -> pe_ttm, pb, div
        info_cols = list(info.columns)
        code_c = _col(info_cols, "行业代码", "代码")
        pe_c   = _col(info_cols, "TTM", "ttm")
        pb_c   = _col(info_cols, "市净率")
        div_c  = _col(info_cols, "股息率")
        if code_c:
            val_map = {}
            for _, r in info.iterrows():
                c = str(r.get(code_c, "")).strip()
                val_map[c] = {
                    "pe_ttm":  _safe_float(r.get(pe_c))  if pe_c  else None,
                    "pb":      _safe_float(r.get(pb_c))  if pb_c  else None,
                    "div_pct": _safe_float(r.get(div_c)) if div_c else None,
                }
            df["pe_ttm"]  = df["sw_code_si"].map(lambda x: val_map.get(x, {}).get("pe_ttm"))
            df["pb"]      = df["sw_code_si"].map(lambda x: val_map.get(x, {}).get("pb"))
            df["div_pct"] = df["sw_code_si"].map(lambda x: val_map.get(x, {}).get("div_pct"))
    except Exception as e:
        log.warning("sw_l1_map: valuation enrich skipped (%s)", e)
        df["pe_ttm"] = None
        df["pb"]     = None
        df["div_pct"] = None

    STORE.mkdir(parents=True, exist_ok=True)
    out = STORE / "sw_l1_map.parquet"
    df.to_parquet(out, index=False)
    log.info("sw_l1_map: wrote %d industries to %s", len(df), out)
    return len(df)


# ── Backfill ────────────────────────────────────────────────────────────────────

def backfill(
    *,
    feed: str = "both",       # "mrtj" | "mrmx" | "both"
    start: str | None = None, # override YYYYMMDD
    end:   str | None = None, # override YYYYMMDD (default: today)
    max_chunks: int | None = None,   # safety cap for tests
    verbose: bool = False,
) -> dict[str, int]:
    """Resumable backfill of one or both feeds from their earliest known date.

    Args:
        feed: which feed to backfill ("mrtj", "mrmx", or "both").
        start: override the default start date (YYYYMMDD). Defaults to MRTJ_BACKFILL_START
               or MRMX_BACKFILL_START depending on the feed.
        end:   override the end date (YYYYMMDD). Defaults to today.
        max_chunks: cap the number of chunks processed (for tests/preview).
        verbose: print progress.

    Returns:
        dict with keys 'mrtj_written', 'mrmx_written' (row counts).
    """
    STORE.mkdir(parents=True, exist_ok=True)
    asof = _dt.date.today().isoformat()
    today_str = _dt.date.today().strftime("%Y%m%d")
    end_str = end or today_str

    results = {"mrtj_written": 0, "mrmx_written": 0}
    feeds_to_run = ["mrtj", "mrmx"] if feed == "both" else [feed]

    for fd in feeds_to_run:
        default_start = MRTJ_BACKFILL_START if fd == "mrtj" else MRMX_BACKFILL_START
        start_str = start or default_start

        stored = _stored_dates_mrtj() if fd == "mrtj" else _stored_dates_mrmx()
        log.info("%s: %d dates already stored, backfilling %s → %s",
                 fd, len(stored), start_str, end_str)
        if verbose:
            print(f"[{fd}] {len(stored)} dates stored, backfilling {start_str} → {end_str}")

        chunks_done = 0
        total_written = 0

        for chunk_start, chunk_end in _date_chunks(start_str, end_str):
            if max_chunks is not None and chunks_done >= max_chunks:
                log.info("%s: hit max_chunks=%d, stopping", fd, max_chunks)
                break

            # Quick skip: if all calendar dates in this chunk already appear in stored,
            # we can skip. (Approximate check — good enough for resumability.)
            chunk_start_d = _dt.datetime.strptime(chunk_start, "%Y%m%d").date()
            chunk_end_d   = _dt.datetime.strptime(chunk_end,   "%Y%m%d").date()
            # Convert stored dates to a set of date objects for comparison
            stored_d = {_dt.date.fromisoformat(d) for d in stored if len(d) == 10}
            # Business days in chunk (approximate: check Mon-Fri count)
            bdays_in_chunk = sum(
                1 for i in range((chunk_end_d - chunk_start_d).days + 1)
                if (chunk_start_d + _dt.timedelta(days=i)).weekday() < 5
            )
            already_stored = sum(
                1 for i in range((chunk_end_d - chunk_start_d).days + 1)
                if (chunk_start_d + _dt.timedelta(days=i)) in stored_d
            )
            # If most business days are already stored, skip this chunk
            if bdays_in_chunk > 0 and already_stored >= bdays_in_chunk:
                chunks_done += 1
                continue

            # Fetch
            if fd == "mrtj":
                raw = _fetch_mrtj(chunk_start, chunk_end)
                rows = _parse_mrtj(raw, asof)
            else:
                raw = _fetch_mrmx(chunk_start, chunk_end)
                rows = _parse_mrmx(raw, asof)

            # Filter to only new dates
            if rows:
                rows_new = [r for r in rows if r["date"] not in stored]
                n_written = _append_rows(rows_new, fd)
                # Update stored set for subsequent chunks
                stored |= {r["date"] for r in rows_new}
                total_written += n_written
                if verbose and n_written > 0:
                    dates_hit = sorted({r["date"] for r in rows_new})
                    print(f"  [{fd}] chunk {chunk_start}-{chunk_end}: "
                          f"{n_written} rows, dates={dates_hit[0]}..{dates_hit[-1]}")
            else:
                if verbose:
                    print(f"  [{fd}] chunk {chunk_start}-{chunk_end}: empty/error (expected for holidays)")

            chunks_done += 1
            time.sleep(THROTTLE_S)

        results[f"{fd}_written"] = total_written
        log.info("%s: backfill complete, %d rows written total", fd, total_written)

    return results


# ── Nightly refresh (incremental) ───────────────────────────────────────────────

def refresh() -> dict[str, int]:
    """Nightly incremental refresh: collect the last 5 trading-day window for both feeds.

    Designed to be called from scripts/collect.py. Throttles at ≤ 2 req/s.
    Returns {'mrtj_written': n, 'mrmx_written': n}.
    """
    STORE.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today()
    # Look back 10 calendar days to catch delayed publications and recent holidays
    window_start = (today - _dt.timedelta(days=10)).strftime("%Y%m%d")
    window_end   = today.strftime("%Y%m%d")
    return backfill(feed="both", start=window_start, end=window_end)


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="China block-trade tape archiver (F5-01 accrual infra)."
    )
    sub = ap.add_subparsers(dest="cmd")

    # backfill sub-command
    bf = sub.add_parser("backfill", help="Full historical backfill (resumable)")
    bf.add_argument("--feed",   default="both", choices=["mrtj", "mrmx", "both"])
    bf.add_argument("--start",  default=None, help="Override start YYYYMMDD")
    bf.add_argument("--end",    default=None, help="Override end YYYYMMDD")
    bf.add_argument("--max-chunks", type=int, default=None,
                    help="Cap chunks (for preview/testing)")
    bf.add_argument("--verbose", "-v", action="store_true")

    # sw-map sub-command
    sub.add_parser("sw-map", help="Build/refresh the SW L1 snapshot")

    # refresh sub-command
    sub.add_parser("refresh", help="Nightly incremental refresh (last 10 days)")

    # probe sub-command
    sub.add_parser("probe", help="Print store coverage summary")

    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    if args.cmd == "backfill":
        r = backfill(
            feed=args.feed,
            start=args.start,
            end=args.end,
            max_chunks=args.max_chunks,
            verbose=args.verbose,
        )
        print(f"Done: {r}")

    elif args.cmd == "sw-map":
        n = refresh_sw_l1_map()
        print(f"SW L1 map: {n} industries written.")

    elif args.cmd == "refresh":
        r = refresh()
        print(f"Refresh: {r}")

    elif args.cmd == "probe":
        _probe_coverage()

    else:
        ap.print_help()


def _probe_coverage() -> None:
    """Print a summary of what's currently on disk."""
    print("\n=== china_block_tape store coverage ===")
    print(f"Location: {STORE}")
    for fd in ("mrtj", "mrmx"):
        files = sorted(STORE.glob(f"{fd}_*.parquet"))
        if not files:
            print(f"  {fd}: no data yet")
            continue
        all_dates = set()
        total_rows = 0
        for f in files:
            try:
                df = pd.read_parquet(f, columns=["date"])
                all_dates |= set(df["date"].astype(str).unique())
                total_rows += len(df)
            except Exception:
                pass
        if all_dates:
            sorted_dates = sorted(all_dates)
            print(f"  {fd}: {total_rows} rows, {len(all_dates)} dates, "
                  f"{sorted_dates[0]} → {sorted_dates[-1]}, "
                  f"{len(files)} yearly file(s)")
    sw_map = STORE / "sw_l1_map.parquet"
    if sw_map.exists():
        df_sw = pd.read_parquet(sw_map)
        snap = df_sw["snapshot_date"].iloc[0] if "snapshot_date" in df_sw.columns else "?"
        print(f"  sw_l1_map: {len(df_sw)} industries, snapshot_date={snap}")
    else:
        print("  sw_l1_map: not yet built")
    print()


if __name__ == "__main__":
    main()
