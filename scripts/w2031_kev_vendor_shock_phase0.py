"""W2-031 (+W2-033) CISA KEV Vendor-Exposure Shock — Phase-0 event study.

Wave-2 spike S1 (off-render, no collector, no wiring).

PRE-REGISTERED DESIGN — DO NOT MODIFY BEFORE RESULTS:
======================================================
Family: w2031_kev_vendor_shock
Variant grid (logged at generation, before any computation):
  V1  — every new KEV entry for a mapped public vendor; forward 5d + 21d abnormal return
  V2  — entries with knownRansomwareCampaignUse == 'Known' only; 5d + 21d
  V3  — cluster events: >=2 KEV entries for the same vendor within 5 trading days
         (event at the 2nd entry); 5d + 21d
  V4  — per vendor, count of open KEV entries with dueDate within next 14 calendar days,
         top-decile weeks → forward 21d abnormal return (W2-033 fold-in)

Abnormal return = vendor return minus beta*benchmark return.
  Beta: trailing 252-day OLS, min 120 days.
  Benchmark: IGV (iShares Expanded Tech-Software ETF) — all mapped vendors are software/security.

PRE-REGISTERED DIRECTION: negative abnormal returns after KEV exposure.

HONEST PRIOR (printed at runtime):
  Breach-event academic literature finds small and transient negative abnormal returns
  (typically -0.5% to -2% in 5-20d windows, often not significant after multiple-testing
  correction). Expected home for this signal is event-context DISPLAY for the special-situations
  desk, NOT a scored allocation signal. The probability of passing all three gates is low.

GATES (all must pass for confirmer candidacy):
  G1: V1 21d mean abnormal return is NEGATIVE with |t_HAC| >= 2.0 AND BH-FDR q <= 0.10
      across the 7-cell family (V1×2 + V2×2 + V3×2 + V4×1 — V4 is 21d-only).
  G2: Split-half same-sign — 2021-11..2024-02 vs 2024-03..2026-07 — for V1 21d mean.
  G3: Survives excluding Microsoft entries (largest vendor concentration).

PIT law: dateAdded IS the availability date (CISA publishes same-day). Event signal
triggered at CLOSE of dateAdded + 1 trading day (conservative — ensures public access
before entry price).

Run: python -m scripts.w2031_kev_vendor_shock_phase0
     python scripts/w2031_kev_vendor_shock_phase0.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.trial_ledger import TrialLedger  # noqa: E402
from engine.validation import newey_west_tstat, benjamini_hochberg  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
KEV_CACHE = ROOT / "data" / "cisa_kev" / "kev.json"
VENDOR_MAP_PATH = ROOT / "scripts" / "w2031_kev_vendor_map.csv"
BENCHMARK_TICKER = "IGV"  # iShares Expanded Tech-Software ETF
# The worktree's data/massive_stock_day/ top level contains only
# _manifest.json/_backfill_state.json plus a nested symlink named
# 'massive_stock_day' that points to the real parquet store.
# Resolve one level deeper so _load_prices() finds TICKER.parquet files.
MASSIVE_DIR = ROOT / "data" / "massive_stock_day" / "massive_stock_day"
YAHOO_DIR = ROOT / "data" / "yahoo"
BETA_WINDOW = 252
BETA_MIN = 120
FWD_SHORT = 5
FWD_LONG = 21
CLUSTER_WINDOW = 5   # trading days for V3 clustering
DUE_HORIZON = 14     # calendar days for V4 due-date pressure
FAMILY = "w2031_kev_vendor_shock"

# Pre-registered variant grid — logged BEFORE any computation
VARIANT_GRID = [
    {"variant": "V1", "horizon": 5,  "filter": "all",       "description": "all KEV entries, 5d abnormal return"},
    {"variant": "V1", "horizon": 21, "filter": "all",       "description": "all KEV entries, 21d abnormal return"},
    {"variant": "V2", "horizon": 5,  "filter": "ransomware","description": "ransomware KEV entries only, 5d"},
    {"variant": "V2", "horizon": 21, "filter": "ransomware","description": "ransomware KEV entries only, 21d"},
    {"variant": "V3", "horizon": 5,  "filter": "cluster",   "description": "cluster events (>=2 in 5d), 5d"},
    {"variant": "V3", "horizon": 21, "filter": "cluster",   "description": "cluster events (>=2 in 5d), 21d"},
    {"variant": "V4", "horizon": 21, "filter": "due_pressure","description": "top-decile due-date pressure weeks, 21d"},
]

# ---------------------------------------------------------------------------
# 1. KEV data
# ---------------------------------------------------------------------------

def _fetch_kev() -> list[dict]:
    """Fetch or return cached KEV catalog. Cache to data/cisa_kev/kev.json."""
    KEV_CACHE.parent.mkdir(parents=True, exist_ok=True)
    # Refresh if cache older than 1 day or missing
    if KEV_CACHE.exists():
        age_h = (datetime.now().timestamp() - KEV_CACHE.stat().st_mtime) / 3600
        if age_h < 24:
            with KEV_CACHE.open(encoding="utf-8") as fh:
                return json.load(fh)["vulnerabilities"]
    print(f"  Fetching KEV catalog from CISA...", flush=True)
    with urllib.request.urlopen(KEV_URL, timeout=60) as resp:
        raw = json.load(resp)
    with KEV_CACHE.open("w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    return raw["vulnerabilities"]


# ---------------------------------------------------------------------------
# 2. Vendor map
# ---------------------------------------------------------------------------

def _load_vendor_map() -> dict[str, dict]:
    """Load vendor map CSV -> {vendorProject: {ticker, valid_from, valid_to}} for PUBLIC only."""
    df = pd.read_csv(VENDOR_MAP_PATH)
    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        if str(row.get("status", "")).strip().lower() != "public":
            continue
        ticker = str(row.get("ticker", "")).strip()
        if not ticker:
            continue
        out[str(row["vendor"]).strip()] = {
            "ticker": ticker,
            "valid_from": str(row.get("valid_from", "2000-01-01")).strip(),
            "valid_to": str(row.get("valid_to", "2099-12-31")).strip() or "2099-12-31",
        }
    return out


# ---------------------------------------------------------------------------
# 3. Price loading
# ---------------------------------------------------------------------------

def _load_prices(ticker: str, directory: Path) -> pd.Series | None:
    """Load close prices from parquet file. Returns daily pd.Series with DatetimeIndex."""
    path = directory / f"{ticker}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        # Normalize index to date-only
        df.index = pd.to_datetime(df.index).normalize()
        if "close" in df.columns:
            return df["close"].rename(ticker)
        return None
    except Exception:
        return None


def _get_price_series(ticker: str) -> pd.Series | None:
    """Try massive_stock_day first (better coverage), then yahoo."""
    s = _load_prices(ticker, MASSIVE_DIR)
    if s is not None and len(s) > 100:
        return s
    s = _load_prices(ticker, YAHOO_DIR)
    return s


# ---------------------------------------------------------------------------
# 4. Trading days calendar
# ---------------------------------------------------------------------------

def _trading_days() -> pd.DatetimeIndex:
    """Build a market calendar from benchmark closes."""
    benchmark = _get_price_series(BENCHMARK_TICKER)
    if benchmark is None:
        raise RuntimeError(f"Cannot load benchmark {BENCHMARK_TICKER}")
    return pd.DatetimeIndex(sorted(benchmark.index))


def _next_trading_day(dt: pd.Timestamp, cal: pd.DatetimeIndex) -> pd.Timestamp | None:
    """Return the first trading day AFTER dt (entry on T+1 close)."""
    future = cal[cal > dt]
    return future[0] if len(future) > 0 else None


def _nth_trading_day(dt: pd.Timestamp, n: int, cal: pd.DatetimeIndex) -> pd.Timestamp | None:
    """Return the trading day n steps after dt (inclusive starting from next pos)."""
    pos = cal.searchsorted(dt, side="right")
    target = pos + n - 1
    if target >= len(cal):
        return None
    return cal[target]


def _count_trading_days_between(d1: pd.Timestamp, d2: pd.Timestamp, cal: pd.DatetimeIndex) -> int:
    """Number of trading days between d1 and d2 (exclusive of d1, inclusive of d2)."""
    return int(((cal > d1) & (cal <= d2)).sum())


# ---------------------------------------------------------------------------
# 5. Beta computation and abnormal return
# ---------------------------------------------------------------------------

def _compute_beta(vendor_prices: pd.Series, bench_prices: pd.Series,
                  event_date: pd.Timestamp) -> float | None:
    """OLS beta of vendor on benchmark using the 252 trading days BEFORE event_date."""
    # Use prices strictly before event_date
    v = vendor_prices[vendor_prices.index < event_date].tail(BETA_WINDOW)
    b = bench_prices[bench_prices.index < event_date].tail(BETA_WINDOW)
    common = v.index.intersection(b.index)
    if len(common) < BETA_MIN:
        return None
    vr = v.reindex(common).pct_change().dropna()
    br = b.reindex(common).pct_change().dropna()
    common2 = vr.index.intersection(br.index)
    if len(common2) < BETA_MIN:
        return None
    vr, br = vr.reindex(common2).values, br.reindex(common2).values
    cov = np.cov(vr, br)
    if cov[1, 1] < 1e-12:
        return None
    return float(cov[0, 1] / cov[1, 1])


def _abnormal_return(vendor_prices: pd.Series, bench_prices: pd.Series,
                     entry_date: pd.Timestamp, horizon: int,
                     cal: pd.DatetimeIndex, beta: float) -> float | None:
    """Forward horizon-day cumulative abnormal return from entry_date close."""
    exit_date = _nth_trading_day(entry_date, horizon, cal)
    if exit_date is None:
        return None
    if entry_date not in vendor_prices.index or exit_date not in vendor_prices.index:
        return None
    if entry_date not in bench_prices.index or exit_date not in bench_prices.index:
        return None
    vendor_ret = vendor_prices[exit_date] / vendor_prices[entry_date] - 1.0
    bench_ret = bench_prices[exit_date] / bench_prices[entry_date] - 1.0
    return float(vendor_ret - beta * bench_ret)


# ---------------------------------------------------------------------------
# 6. Build event set
# ---------------------------------------------------------------------------

def _build_events(vulns: list[dict], vendor_map: dict[str, dict],
                  cal: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Build the base event table.
    Returns DataFrame with columns:
      vendor, ticker, date_added, entry_date (T+1 trading day), is_ransomware,
      due_date, cve_id
    Only includes events where the vendor was publicly listed on date_added.
    """
    rows = []
    for v in vulns:
        vendor = str(v.get("vendorProject", "")).strip()
        if vendor not in vendor_map:
            continue
        vm = vendor_map[vendor]
        ticker = vm["ticker"]
        da = pd.Timestamp(v["dateAdded"])
        valid_from = pd.Timestamp(vm["valid_from"])
        valid_to = pd.Timestamp(vm["valid_to"])
        # Check corporate action window — vendor must be public on dateAdded
        if da < valid_from or da > valid_to:
            continue
        entry_date = _next_trading_day(da, cal)
        if entry_date is None:
            continue
        is_ransomware = str(v.get("knownRansomwareCampaignUse", "")).strip() == "Known"
        due_date = v.get("dueDate", "")
        rows.append({
            "vendor": vendor,
            "ticker": ticker,
            "cve_id": v.get("cveID", ""),
            "date_added": da,
            "entry_date": entry_date,
            "is_ransomware": is_ransomware,
            "due_date": pd.Timestamp(due_date) if due_date else pd.NaT,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("entry_date").reset_index(drop=True)
    return df


def _add_cluster_flag(events: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.DataFrame:
    """
    V3: Mark events where >=2 KEV entries for the SAME vendor occur within 5 trading days.
    The 'cluster_event' flag marks the 2nd (or later) entry in a run.
    """
    events = events.copy()
    events["cluster_event"] = False
    for ticker, grp in events.groupby("ticker"):
        dates = grp["entry_date"].sort_values().values
        if len(dates) < 2:
            continue
        for i in range(1, len(dates)):
            d_prev = pd.Timestamp(dates[i - 1])
            d_curr = pd.Timestamp(dates[i])
            td = _count_trading_days_between(d_prev, d_curr, cal)
            if 1 <= td <= CLUSTER_WINDOW:
                idx = grp.index[grp["entry_date"] == d_curr]
                events.loc[idx, "cluster_event"] = True
    return events


def _add_due_pressure(events: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.DataFrame:
    """
    V4 (W2-033): For each week (Monday of calendar week), count the number of open KEV entries
    where dueDate falls within the next 14 calendar days. Top-decile weeks become event signals.
    Assign a 'due_pressure_week' flag to events whose entry_date falls in a top-decile week.
    Returns events df with 'due_pressure_week' bool column.
    """
    events = events.copy()
    events["due_pressure_week"] = False

    # Only keep events with valid due dates
    has_due = events.dropna(subset=["due_date"])
    if has_due.empty:
        return events

    # Build weekly due-pressure series over the calendar
    # For each entry_date in trading calendar, count how many entries have due_date
    # in [entry_date, entry_date + 14 calendar days]
    all_entry_dates = pd.DatetimeIndex(sorted(events["entry_date"].unique()))

    # Group by week
    weekly_dates = pd.date_range(
        start=all_entry_dates.min() - pd.Timedelta(days=7),
        end=all_entry_dates.max() + pd.Timedelta(days=7),
        freq="W-MON"
    )

    pressure = []
    for week_start in weekly_dates:
        week_end = week_start + pd.Timedelta(days=14)
        # Count entries whose dueDate is in [week_start, week_end]
        cnt = int(((has_due["due_date"] >= week_start) & (has_due["due_date"] <= week_end)).sum())
        pressure.append({"week_start": week_start, "count": cnt})

    press_df = pd.DataFrame(pressure)
    if press_df.empty or press_df["count"].max() == 0:
        return events

    # NOTE: quantile computed over FULL 2021-2026 sample — this is NOT point-in-time.
    # A top-decile week label uses full-sample knowledge. V4 is flagged as NOT deployable
    # as-is; an expanding-window or trailing quantile would be the PIT form.
    threshold = press_df["count"].quantile(0.90)
    top_weeks = set(press_df.loc[press_df["count"] >= threshold, "week_start"].tolist())

    # Assign flag: entry_date's week (Monday) is in top_weeks
    def week_monday(dt: pd.Timestamp) -> pd.Timestamp:
        return dt - pd.Timedelta(days=dt.weekday())

    for idx, row in events.iterrows():
        mon = week_monday(row["entry_date"])
        if mon in top_weeks:
            events.at[idx, "due_pressure_week"] = True

    return events


# ---------------------------------------------------------------------------
# 7. Event study: compute abnormal returns per event
# ---------------------------------------------------------------------------

def _run_event_study(events: pd.DataFrame, bench_prices: pd.Series,
                     cal: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Compute beta and abnormal returns for each event row.
    Returns events df with added columns: beta, ar_5d, ar_21d.
    """
    events = events.copy()
    events["beta"] = np.nan
    events["ar_5d"] = np.nan
    events["ar_21d"] = np.nan

    # Cache price series per ticker
    price_cache: dict[str, pd.Series | None] = {}

    for idx, row in events.iterrows():
        ticker = row["ticker"]
        if ticker not in price_cache:
            price_cache[ticker] = _get_price_series(ticker)
        prices = price_cache[ticker]
        if prices is None:
            continue

        entry_date = row["entry_date"]
        beta = _compute_beta(prices, bench_prices, entry_date)
        if beta is None:
            continue
        events.at[idx, "beta"] = beta

        ar5 = _abnormal_return(prices, bench_prices, entry_date, FWD_SHORT, cal, beta)
        ar21 = _abnormal_return(prices, bench_prices, entry_date, FWD_LONG, cal, beta)
        events.at[idx, "ar_5d"] = ar5
        events.at[idx, "ar_21d"] = ar21

    return events


# ---------------------------------------------------------------------------
# 8. Summarize and gate evaluation
# ---------------------------------------------------------------------------

def _summarize_variant(ars: pd.Series, label: str) -> dict[str, Any]:
    """Compute mean, t_HAC, n for a set of abnormal returns.

    STATS NOTE — calendar-time collapse:
    Naive NW on the event-indexed array treats it as a time series and
    Bartlett-weights over event-index lags, but many events share the same
    calendar entry_date (especially Microsoft CVEs) and 21d forward windows
    overlap pervasively — so cross-event correlation is NOT corrected by
    event-index lags. We collapse to one observation per calendar entry_date
    (mean AR across all events on that date), then run NW on the resulting
    date-indexed series. This is the calendar-time portfolio method and
    correctly treats each trading day as one observation regardless of how
    many events share it. n_events = raw count; n_dates = dates used in NW.
    """
    clean = ars.dropna()
    n_events = len(clean)
    if n_events < 8:
        return {"label": label, "mean": None, "t_hac": None, "p_hac": None,
                "n": n_events, "n_events": n_events, "n_dates": 0}
    # Collapse to one observation per calendar date (simple mean across events on same date)
    if isinstance(clean.index, pd.DatetimeIndex):
        daily = clean.groupby(clean.index.date).mean()
    else:
        # ars was passed without a date index — fall back to raw (shouldn't happen)
        daily = clean
    n_dates = len(daily)
    if n_dates < 8:
        return {"label": label, "mean": None, "t_hac": None, "p_hac": None,
                "n": n_events, "n_events": n_events, "n_dates": n_dates}
    # NW lags = min(4, n_dates-1); for 21d windows ~sqrt(n_dates) would be
    # the Newey-West (1994) plug-in, but 4 is conservative and matches family
    nw_lags = min(4, n_dates - 1)
    nw = newey_west_tstat(daily.values, lags=nw_lags)
    return {
        "label": label,
        "mean": round(nw["mean"] * 100, 4) if nw["mean"] is not None else None,  # as %
        "t_hac": nw["t"],
        "p_hac": nw["p"],
        "n": n_events,
        "n_events": n_events,
        "n_dates": n_dates,
    }


# ---------------------------------------------------------------------------
# 9. Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("W2-031 CISA KEV Vendor-Exposure Shock — Phase-0")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # HONEST PRIOR (pre-registered, print before results)
    # -----------------------------------------------------------------------
    print()
    print("HONEST PRIOR (pre-registered):")
    print("  Breach-event academic literature finds small, transient negative")
    print("  abnormal returns (typically -0.5% to -2% over 5-20d), often not")
    print("  significant after multiple-testing correction. This signal's")
    print("  expected home is event-context DISPLAY for the special-situations")
    print("  desk, NOT a scored allocation signal. Prior probability of passing")
    print("  all three gates is LOW.")
    print()

    # -----------------------------------------------------------------------
    # Log variant grid at generation — BEFORE any computation
    # -----------------------------------------------------------------------
    ledger = TrialLedger(family=FAMILY)
    n_logged = ledger.log_grid(VARIANT_GRID, family=FAMILY, info_cutoff="2026-07-06")
    print(f"Trial ledger: logged {n_logged} new variants (family={FAMILY})")
    print()

    # -----------------------------------------------------------------------
    # Load KEV catalog
    # -----------------------------------------------------------------------
    print("Loading CISA KEV catalog...", flush=True)
    vulns = _fetch_kev()
    total_entries = len(vulns)
    print(f"  Total KEV entries: {total_entries}")
    print()

    # -----------------------------------------------------------------------
    # Load vendor map
    # -----------------------------------------------------------------------
    print("Loading vendor map...", flush=True)
    vendor_map = _load_vendor_map()
    mapped_vendors = set(vendor_map.keys())
    print(f"  Mapped public vendors: {len(mapped_vendors)}")
    mappable_entries = sum(1 for v in vulns if v["vendorProject"] in mapped_vendors)
    print(f"  KEV entries for mapped vendors: {mappable_entries} / {total_entries} "
          f"({mappable_entries/total_entries*100:.1f}%)")
    print()

    # -----------------------------------------------------------------------
    # Load benchmark and build calendar
    # -----------------------------------------------------------------------
    print("Loading benchmark (IGV)...", flush=True)
    bench_prices = _get_price_series(BENCHMARK_TICKER)
    if bench_prices is None:
        raise RuntimeError("IGV benchmark prices not found — cannot proceed")
    bench_prices.index = pd.to_datetime(bench_prices.index).normalize()
    print(f"  IGV: {len(bench_prices)} days, "
          f"{bench_prices.index[0].date()} to {bench_prices.index[-1].date()}")
    cal = pd.DatetimeIndex(sorted(bench_prices.index))
    print()

    # -----------------------------------------------------------------------
    # Build event table
    # -----------------------------------------------------------------------
    print("Building event table...", flush=True)
    events = _build_events(vulns, vendor_map, cal)
    mapped_public_events = len(events)
    print(f"  Events after corporate-action filter: {mapped_public_events}")
    if events.empty:
        print("  ERROR: No events found — check vendor map and price data")
        return

    events = _add_cluster_flag(events, cal)
    events = _add_due_pressure(events, cal)

    # Vendor breakdown
    vendor_counts = events.groupby("vendor").size().sort_values(ascending=False)
    print("  Events by vendor (top 15):")
    for v, c in vendor_counts.head(15).items():
        print(f"    {v:30s}  {c:4d}")
    print()

    # Ransomware subset
    n_ransomware = int(events["is_ransomware"].sum())
    n_cluster = int(events["cluster_event"].sum())
    n_due_pressure = int(events["due_pressure_week"].sum())
    print(f"  V1 (all):            {mapped_public_events} events")
    print(f"  V2 (ransomware):     {n_ransomware} events")
    print(f"  V3 (cluster):        {n_cluster} events")
    print(f"  V4 (due pressure):   {n_due_pressure} events")
    print()

    # -----------------------------------------------------------------------
    # Compute abnormal returns
    # -----------------------------------------------------------------------
    print("Computing abnormal returns (beta OLS + forward returns)...", flush=True)
    events = _run_event_study(events, bench_prices, cal)

    n_with_beta = int(events["beta"].notna().sum())
    n_ar5 = int(events["ar_5d"].notna().sum())
    n_ar21 = int(events["ar_21d"].notna().sum())
    print(f"  Events with valid beta:   {n_with_beta}")
    print(f"  Events with 5d AR:        {n_ar5}")
    print(f"  Events with 21d AR:       {n_ar21}")
    print()

    # -----------------------------------------------------------------------
    # Variant summaries — compute all 7 cells
    # -----------------------------------------------------------------------
    print("=" * 70)
    print("RESULTS BY VARIANT")
    print("=" * 70)
    print()

    def get_ars(mask: pd.Series, horizon_col: str) -> pd.Series:
        """Return AR series indexed by entry_date for calendar-time NW collapse."""
        sub = events.loc[mask, ["entry_date", horizon_col]].dropna(subset=[horizon_col])
        s = pd.Series(sub[horizon_col].values,
                      index=pd.DatetimeIndex(sub["entry_date"].values),
                      name=horizon_col)
        return s

    mask_all = pd.Series([True] * len(events), index=events.index)
    mask_ransomware = events["is_ransomware"]
    mask_cluster = events["cluster_event"]
    mask_due = events["due_pressure_week"]
    mask_no_msft = events["vendor"] != "Microsoft"

    summaries = {}

    for variant, mask, h_col, label in [
        ("V1_5d",  mask_all,       "ar_5d",  "V1  5d  all events"),
        ("V1_21d", mask_all,       "ar_21d", "V1 21d  all events"),
        ("V2_5d",  mask_ransomware,"ar_5d",  "V2  5d  ransomware only"),
        ("V2_21d", mask_ransomware,"ar_21d", "V2 21d  ransomware only"),
        ("V3_5d",  mask_cluster,   "ar_5d",  "V3  5d  cluster events"),
        ("V3_21d", mask_cluster,   "ar_21d", "V3 21d  cluster events"),
        ("V4_21d", mask_due,       "ar_21d", "V4 21d  due-pressure top-decile"),
    ]:
        s = _summarize_variant(get_ars(mask, h_col), label)
        summaries[variant] = s
        mean_str = f"{s['mean']:+.3f}%" if s["mean"] is not None else "n/a"
        t_str = f"{s['t_hac']:+.2f}" if s["t_hac"] is not None else "n/a"
        p_str = f"{s['p_hac']:.4f}" if s["p_hac"] is not None else "n/a"
        print(f"  {label:40s}  n={s['n']:4d}  mean={mean_str:>10s}  t_HAC={t_str:>7s}  p={p_str}")

    print()

    # -----------------------------------------------------------------------
    # Gate G1: BH-FDR across 4x2 family
    # -----------------------------------------------------------------------
    print("=" * 70)
    print("GATE G1: V1 21d negative + |t_HAC| >= 2 + BH-FDR q <= 0.10 over 7-cell family")
    print("=" * 70)

    # Collect p-values for the 7 cells (V1×2 + V2×2 + V3×2 + V4×1; V4 is 21d-only)
    pvals_for_bh = {k: v["p_hac"] for k, v in summaries.items() if v.get("p_hac") is not None}
    bh_results = benjamini_hochberg(pvals_for_bh, alpha=0.10)

    v1_21 = summaries.get("V1_21d", {})
    g1_negative = (v1_21.get("mean") is not None and v1_21["mean"] < 0)
    g1_t_ok = (v1_21.get("t_hac") is not None and abs(v1_21["t_hac"]) >= 2.0)
    bh_v1_21 = bh_results.get("V1_21d", {})
    g1_fdr_ok = bool(bh_v1_21.get("reject", False))

    print(f"  V1 21d mean AR: {v1_21.get('mean', 'n/a')}")
    print(f"  V1 21d t_HAC:   {v1_21.get('t_hac', 'n/a')}")
    print(f"  BH results (7-cell family):")
    for k, bh in sorted(bh_results.items()):
        rej_str = "REJECT" if bh.get("reject") else "retain"
        print(f"    {k:12s}  p={bh['p']:.4f}  q={bh['q']:.4f}  [{rej_str}]")
    print()
    g1_pass = g1_negative and g1_t_ok and g1_fdr_ok
    print(f"  G1 NEGATIVE:  {'PASS' if g1_negative else 'FAIL'}")
    print(f"  G1 |t|>=2:    {'PASS' if g1_t_ok else 'FAIL'}")
    print(f"  G1 BH-FDR:    {'PASS' if g1_fdr_ok else 'FAIL'}")
    print(f"  >>> G1: {'PASS' if g1_pass else 'FAIL'}")
    print()

    # -----------------------------------------------------------------------
    # Gate G2: Split-half same-sign for V1 21d
    # -----------------------------------------------------------------------
    print("=" * 70)
    print("GATE G2: Split-half same-sign (2021-11..2024-02 vs 2024-03..2026-07)")
    print("=" * 70)

    split_date = pd.Timestamp("2024-03-01")
    early_mask = mask_all & (events["entry_date"] < split_date)
    late_mask  = mask_all & (events["entry_date"] >= split_date)

    early_sum = _summarize_variant(get_ars(early_mask, "ar_21d"), "V1 21d early half")
    late_sum  = _summarize_variant(get_ars(late_mask,  "ar_21d"), "V1 21d late half")

    early_mean = early_sum.get("mean")
    late_mean  = late_sum.get("mean")
    early_mean_str = f"{early_mean:+.3f}%" if early_mean is not None else "n/a"
    late_mean_str  = f"{late_mean:+.3f}%" if late_mean  is not None else "n/a"

    print(f"  Early (2021-11..2024-02): n={early_sum['n']:3d}  mean={early_mean_str}  "
          f"t_HAC={early_sum.get('t_hac', 'n/a')}")
    print(f"  Late  (2024-03..2026-07): n={late_sum['n']:3d}  mean={late_mean_str}  "
          f"t_HAC={late_sum.get('t_hac', 'n/a')}")

    g2_pass = False
    if early_mean is not None and late_mean is not None:
        g2_pass = bool((early_mean < 0) == (late_mean < 0))  # same-sign
    print(f"  >>> G2: {'PASS' if g2_pass else 'FAIL'} (same-sign = {g2_pass})")
    print()

    # -----------------------------------------------------------------------
    # Gate G3: Survives excluding Microsoft
    # -----------------------------------------------------------------------
    print("=" * 70)
    print("GATE G3: Survives excluding Microsoft (largest vendor concentration)")
    print("=" * 70)

    n_msft = int((events["vendor"] == "Microsoft").sum())
    n_msft_ar21 = int(((events["vendor"] == "Microsoft") & events["ar_21d"].notna()).sum())
    no_msft_sum = _summarize_variant(get_ars(mask_no_msft, "ar_21d"), "V1 21d ex-MSFT")
    no_msft_mean = no_msft_sum.get("mean")
    no_msft_mean_str = f"{no_msft_mean:+.3f}%" if no_msft_mean is not None else "n/a"

    print(f"  Microsoft events in sample: {n_msft} total "
          f"({n_msft_ar21} with 21d AR = {n_msft_ar21/max(n_ar21,1)*100:.1f}% of 21d obs)")
    print(f"  Ex-MSFT: n={no_msft_sum['n']:3d}  mean={no_msft_mean_str}  "
          f"t_HAC={no_msft_sum.get('t_hac', 'n/a')}")

    g3_pass = False
    if no_msft_mean is not None and v1_21.get("mean") is not None:
        g3_pass = bool(no_msft_mean < 0 and (v1_21["mean"] < 0) == (no_msft_mean < 0))
    print(f"  >>> G3: {'PASS' if g3_pass else 'FAIL'}")
    print()

    # -----------------------------------------------------------------------
    # Composite verdict
    # -----------------------------------------------------------------------
    print("=" * 70)
    all_pass = g1_pass and g2_pass and g3_pass
    if all_pass:
        verdict = "PASS — all 3 gates cleared — propose confirmer candidacy"
        verdict_short = "PASS"
    else:
        fails = [g for g, ok in [("G1", g1_pass), ("G2", g2_pass), ("G3", g3_pass)] if not ok]
        verdict = f"NULL — gate(s) failed: {', '.join(fails)} — no confirmer proposed; display only"
        verdict_short = "NULL"

    print(f"VERDICT: {verdict}")
    print("=" * 70)
    print()

    # -----------------------------------------------------------------------
    # Write report
    # -----------------------------------------------------------------------
    _write_report(
        verdict=verdict, verdict_short=verdict_short,
        total_entries=total_entries, mapped_public_events=mapped_public_events,
        n_ransomware=n_ransomware, n_cluster=n_cluster, n_due_pressure=n_due_pressure,
        n_with_beta=n_with_beta, n_ar5=n_ar5, n_ar21=n_ar21,
        n_msft=n_msft, n_msft_ar21=n_msft_ar21, vendor_counts=vendor_counts,
        summaries=summaries, bh_results=bh_results,
        early_sum=early_sum, late_sum=late_sum,
        no_msft_sum=no_msft_sum,
        g1_pass=g1_pass, g2_pass=g2_pass, g3_pass=g3_pass,
        bench_start=str(bench_prices.index[0].date()),
        bench_end=str(bench_prices.index[-1].date()),
    )
    print("Report written to reports/w2031-kev-vendor-shock-phase0.md")


# ---------------------------------------------------------------------------
# 10. Report writer
# ---------------------------------------------------------------------------

def _write_report(*, verdict, verdict_short, total_entries, mapped_public_events,
                  n_ransomware, n_cluster, n_due_pressure,
                  n_with_beta, n_ar5, n_ar21, n_msft, n_msft_ar21, vendor_counts,
                  summaries, bh_results, early_sum, late_sum, no_msft_sum,
                  g1_pass, g2_pass, g3_pass,
                  bench_start, bench_end) -> None:
    report_path = ROOT / "reports" / "w2031-kev-vendor-shock-phase0.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    def fmt_mean(s):
        m = s.get("mean")
        return f"{m:+.3f}%" if m is not None else "n/a"
    def fmt_t(s):
        t = s.get("t_hac")
        return f"{t:+.2f}" if t is not None else "n/a"
    def fmt_p(s):
        p = s.get("p_hac")
        return f"{p:.4f}" if p is not None else "n/a"

    bh_rows = "\n".join(
        f"| {k:12s} | {bh['p']:.4f} | {bh['q']:.4f} | {'REJECT' if bh.get('reject') else 'retain'} |"
        for k, bh in sorted(bh_results.items())
    )

    vendor_top = "\n".join(
        f"| {v:30s} | {c:4d} |"
        for v, c in vendor_counts.head(15).items()
    )

    lines = f"""# W2-031 CISA KEV Vendor-Exposure Shock — Phase-0

**Family:** `w2031_kev_vendor_shock`
**Date:** 2026-07-06
**Status:** Wave-2 spike S1 — off-render, no collector, no wiring
**Verdict:** {verdict}

---

> **In plain English:** When a cybersecurity agency publishes a known-exploited
> vulnerability against a publicly-traded software vendor, does that vendor's
> stock underperform over the next 5 or 21 trading days? This script fetches
> every such entry from CISA's catalog (2021-present), maps them to tickers,
> and runs an event study with beta-adjusted returns. The pre-registered honest
> prior is that the effect is likely small or undetectable — academic research
> on breach disclosures finds modest, transient dips that often disappear after
> multiple-testing corrections. The goal is to determine whether this belongs
> as a display signal for the special-situations desk.

---

## 1. Pre-registered design

**Pre-registered direction:** NEGATIVE abnormal returns after KEV exposure.

**Honest prior (printed before results):** Breach-event literature finds small
and transient effects (typically −0.5% to −2% over 5–20d windows), often not
significant after multiple-testing correction. Expected home: event-context
DISPLAY for the special-situations desk, not a scored allocation signal.
Prior probability of clearing all three gates: LOW.

### Variants (logged to trial ledger at generation, before computation)

| Variant | Filter | Horizon | Description |
|---------|--------|---------|-------------|
| V1 | all entries | 5d | All KEV entries for mapped public vendors |
| V1 | all entries | 21d | All KEV entries for mapped public vendors |
| V2 | ransomware only | 5d | Entries with knownRansomwareCampaignUse = 'Known' |
| V2 | ransomware only | 21d | Same, 21d |
| V3 | cluster events | 5d | >=2 entries same vendor within 5 trading days |
| V3 | cluster events | 21d | Same, 21d |
| V4 | due pressure | 21d | Top-decile weeks by open due-dates within 14 cal days |

### Gates (all must pass for confirmer candidacy)

- **G1:** V1 21d mean abnormal return NEGATIVE with |t_HAC| >= 2.0 AND BH-FDR q <= 0.10
  across the 7-cell family (V1×2 + V2×2 + V3×2 + V4×1 — V4 is 21d-only).
- **G2:** Split-half same-sign: 2021-11..2024-02 vs 2024-03..2026-07 for V1 21d mean.
- **G3:** Survives excluding Microsoft entries (largest vendor concentration).

### PIT assumptions

- `dateAdded` in the CISA KEV catalog is the date CISA published the entry — same-day public.
- Entry triggered at CLOSE of `dateAdded + 1 trading day` (conservative; ensures public
  access before entry price is used).
- Beta estimated from trailing 252 trading days OLS (min 120), using IGV (iShares Expanded
  Tech-Software ETF) as benchmark — all mapped vendors are software/security sector.
- Vendor corporate actions: VMware mapped to VMW valid through 2023-10-30 (Broadcom
  acquisition close); Citrix/CTXS valid through 2022-09-08 (privatization); SolarWinds/SWI
  valid through early 2024 (Silver Lake take-private); ARM valid from 2023-09-14 (IPO).
- Only vendors publicly listed on `dateAdded` contribute events.

---

## 2. Data and coverage

| Metric | Value |
|--------|-------|
| KEV catalog total entries | {total_entries} |
| Events for mapped public vendors (post corporate-action filter) | {mapped_public_events} |
| Mapping coverage | {mapped_public_events/total_entries*100:.1f}% of total entries |
| Events with valid beta (≥120d history) | {n_with_beta} |
| Events with valid 5d abnormal return | {n_ar5} |
| Events with valid 21d abnormal return | {n_ar21} |
| Benchmark | IGV (yahoo), {bench_start} to {bench_end} |

**Variant event counts:**

| Variant | N |
|---------|---|
| V1 all | {mapped_public_events} (base set) |
| V2 ransomware | {n_ransomware} |
| V3 cluster | {n_cluster} |
| V4 due pressure | {n_due_pressure} |

**Top vendors by event count:**

| Vendor | Events |
|--------|--------|
{vendor_top}

---

## 3. Results

All means expressed as percentage abnormal return (vendor cumulative − beta × benchmark cumulative).

| Variant | N | Mean AR | t_HAC | p_HAC |
|---------|---|---------|-------|-------|
| V1  5d  all | {summaries['V1_5d']['n']} | {fmt_mean(summaries['V1_5d'])} | {fmt_t(summaries['V1_5d'])} | {fmt_p(summaries['V1_5d'])} |
| V1 21d  all | {summaries['V1_21d']['n']} | {fmt_mean(summaries['V1_21d'])} | {fmt_t(summaries['V1_21d'])} | {fmt_p(summaries['V1_21d'])} |
| V2  5d  ransomware | {summaries['V2_5d']['n']} | {fmt_mean(summaries['V2_5d'])} | {fmt_t(summaries['V2_5d'])} | {fmt_p(summaries['V2_5d'])} |
| V2 21d  ransomware | {summaries['V2_21d']['n']} | {fmt_mean(summaries['V2_21d'])} | {fmt_t(summaries['V2_21d'])} | {fmt_p(summaries['V2_21d'])} |
| V3  5d  cluster | {summaries['V3_5d']['n']} | {fmt_mean(summaries['V3_5d'])} | {fmt_t(summaries['V3_5d'])} | {fmt_p(summaries['V3_5d'])} |
| V3 21d  cluster | {summaries['V3_21d']['n']} | {fmt_mean(summaries['V3_21d'])} | {fmt_t(summaries['V3_21d'])} | {fmt_p(summaries['V3_21d'])} |
| V4 21d  due pressure | {summaries['V4_21d']['n']} | {fmt_mean(summaries['V4_21d'])} | {fmt_t(summaries['V4_21d'])} | {fmt_p(summaries['V4_21d'])} |

---

## 4. Gate evaluation

### G1 — Direction + significance + FDR

V1 21d: mean = {fmt_mean(summaries['V1_21d'])}, t_HAC = {fmt_t(summaries['V1_21d'])}

BH-FDR across 7-cell family (α = 0.10):

| Cell | p | q (BH) | Decision |
|------|---|--------|----------|
{bh_rows}

**G1: {'PASS' if g1_pass else 'FAIL'}**

### G2 — Split-half same-sign

| Period | N | Mean AR | t_HAC |
|--------|---|---------|-------|
| Early 2021-11..2024-02 | {early_sum['n']} | {fmt_mean(early_sum)} | {fmt_t(early_sum)} |
| Late  2024-03..2026-07 | {late_sum['n']} | {fmt_mean(late_sum)} | {fmt_t(late_sum)} |

**G2: {'PASS' if g2_pass else 'FAIL'}**

### G3 — Survives ex-Microsoft

Microsoft contributes {n_msft} events in catalog ({n_msft_ar21} with valid 21d AR = {n_msft_ar21/max(n_ar21,1)*100:.1f}% of 21d observations).

Ex-MSFT: n = {no_msft_sum['n']}, mean = {fmt_mean(no_msft_sum)}, t_HAC = {fmt_t(no_msft_sum)}

**G3: {'PASS' if g3_pass else 'FAIL'}**

---

## 5. Verdict

**{verdict}**

| Gate | Result |
|------|--------|
| G1 direction + |t_HAC|>=2 + BH-FDR q<=0.10 | {'PASS' if g1_pass else 'FAIL'} |
| G2 split-half same-sign | {'PASS' if g2_pass else 'FAIL'} |
| G3 survives ex-MSFT | {'PASS' if g3_pass else 'FAIL'} |

{'All three gates cleared. Propose confirmer candidacy: a collector build tracking daily KEV additions with T+1 entry prices would allow live scoring for the special-situations desk.' if verdict_short == 'PASS' else 'One or more gates failed. NULL printed. No collector build proposed. The signal may be deployed as event-context DISPLAY (informational flagging) for the special-situations desk without allocation or ranking influence. The null is consistent with the pre-registered honest prior.'}

---

## 6. Limitations and honest caveats

- **Microsoft concentration:** Microsoft contributes {n_msft} of the mapped-public events.
  Results with and without Microsoft are both reported in Gate G3.
- **Sector beta only:** We use a single software-sector benchmark (IGV). Individual vendor
  betas vary; a stock-specific factor model would produce cleaner abnormal returns.
- **No intraday resolution:** Entry at next-day close may miss same-day price moves if
  KEV additions become known before market close.
- **Price availability:** Vendors without price data in massive_stock_day or yahoo are
  excluded. All public vendors in the map (Cisco/SAP/Juniper/F5/NETGEAR/Ubiquiti/SolarWinds/
  Progress) are present in the massive store; small-cap or truly delisted tickers account for
  the beta-coverage drop (722/931 = 78% beta coverage).
- **Calendar-time NW:** t-stats are computed on date-collapsed means (calendar-time portfolio
  method) to handle overlapping 21d windows and same-date events. n_events counts raw events;
  the NW degrees of freedom are the number of distinct entry_dates.
- **V4 not point-in-time:** The top-decile threshold for V4 (due-pressure weeks) uses the
  full-sample quantile over 2021-2026. A live version would require an expanding-window or
  trailing quantile. V4 results are descriptive only.
- **Ransomware sub-sample is small:** V2 events ({n_ransomware}) may have insufficient
  power for reliable inference.
- **Cluster definition is heuristic:** The 5-trading-day cluster window is pre-registered
  but not empirically optimized.
- **This is a spike:** No collector wired, no nightly pipeline, no production scoring.

---

*Generated by `scripts/w2031_kev_vendor_shock_phase0.py` — wave-2 spike S1.*
*Not a validated signal. Nulls printed honestly.*
"""

    report_path.write_text(lines, encoding="utf-8")


if __name__ == "__main__":
    main()
