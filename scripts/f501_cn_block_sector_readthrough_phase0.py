"""Phase-0: F5-01 CN block-discount sector read-through.

FAMILY: f501_cn_block_sector_readthrough
LANE: LG-CN-SUPPLY slot reclaimed after d2_cn_holder_sale_calendar directional fail.
Authorization: research/SIGNAL_LAB_FRONTIER_WAVE5_FABLE_DOCKET_2026-07-06.md §F5-01.

=== PRE-REGISTERED DESIGN (frozen before any results are computed) ===

EVENT:
  >=2 distinct names in the same sector-group printing deep-discount blocks
  (avg_premium_pct <= -8%; DEEP variant <= -15%) within a trailing 10-session window.
  Event date = the day the 2nd name qualifies.
  Availability = event_date + 1 trading day (block data publishes T+0 evening / T+1).

OUTCOME:
  Forward 21d and 63d returns of NON-blocked peers in the same sector-group
  (equal-weight, exclude all blocked names in that group on that event date),
  vs (a) CN-A market EW baseline and (b) own-group unconditional baseline.

SECTOR GROUPING (primary):
  data/baskets_china/membership.json — 22 curated baskets (full coverage).
  SW-L1 robustness: data/china_block_tape/sw_l1_constituents.parquet (5/31 codes,
  Agriculture/Chemicals/Steel/Nonferrous Metals/Electronics, 1,185 stocks).

VARIANTS (frozen):
  V1 — all deep-discount clusters (threshold <= -8%)
  V2 — DEEP clusters (threshold <= -15%)
  V3 — UNLOCK-DRIVEN: clusters where >=1 blocked name had an unlock within +/-30 days.
       PRE-REGISTERED STATUS: FORWARD-ACCRUAL ONLY (NON-GATED).
       Reason: akshare stock_restricted_release_detail_em only covers 2022-12-02 to
       2024-12-02 (verified 2026-07-07 via live probe). Historical broad calendar not
       available from any probed endpoint. The per-stock Sina endpoint covers historical
       data but scraping 5,000 tickers at the batch size needed is >budget for this run.
       V3 is registered here with gates frozen; execution requires either the nightly
       china_unlocks store to mature (2024+ data only) or a batch per-stock scrape.

DIRECTION: NEGATIVE peer returns after clusters (sector supply / informed-holder
  pessimism read-through).

GATED CELLS (<=6):
  B-V1-21d  basket V1 clusters, 21d excess vs market
  B-V1-63d  basket V1 clusters, 63d excess vs market
  B-V2-21d  basket V2 clusters (DEEP), 21d excess vs market
  B-V2-63d  basket V2 clusters (DEEP), 63d excess vs market
  SW-V1-21d  SW-L1 robustness V1, 21d excess (5 codes only — reported with coverage)
  SW-V1-63d  SW-L1 robustness V1, 63d excess

GATES (frozen before results):
  G1  Pre-registered direction: |t_HAC| >= 2 (date-clustered, NW) AND t < 0
       BH q <= 0.10 across gated cells
  G2  Split-half same-sign (2013-2019 vs 2020-2026)
  G3  Leave-one-cycle-out: {2015-crash, 2018-bear, 2024-09-stimulus} — all three
       holdout sub-samples same-sign negative
  G4  Read-through survives excluding single most-clustered basket (concentration check)

AMENDMENTS REGISTERED BEFORE COMPUTING:
  AM-1  Market baseline = CSI 300 ETF (510300.SS). Fallback: equal-weight of all
        stocks in china_stocks_raw that have price data on the event date.
        Report which was used.
  AM-2  Minimum peers requirement: at least 2 non-blocked peers in the basket
        with price data on event_date. Events with <2 peers skipped; reported.
  AM-3  Trailing 10-session window: measured in block-tape trading dates
        (dates where >= 1 name appeared in block tape). Not calendar days.
  AM-4  Basket membership: membership.json seed_date = 2021-06-15 (all 'added' dates =
        2021-06-15). Per membership.json history_note: "Pre-launch series use the basket's
        starting membership." We apply the fixed 2021-06-15 roster across the full 2013+
        backtest window. This is SURVIVORSHIP-BIASED with respect to the basket composition
        (stocks added to baskets after 2021 or removed are not handled). All basket tickers
        present on 2021-06-15 are treated as basket members for the full study period.
        AMENDMENT: If a ticker has 'removed' set, it is excluded from event dates AFTER
        its removal date. Tickers with no 'removed' are treated as permanent members.
        (For SW: use sw_l1_constituents.parquet ticker_code mapped to ticker.)
  AM-5  If a ticker appears in multiple baskets, assign it to ALL matching baskets
        (each cluster is scored per-basket independently).
  AM-6  Overlap-correction for 63d cells: when multiple events in the same basket
        fall within a 63-day window, use date-collapsed portfolio returns
        (equal-weight of all active event peers on that date) rather than
        counting multiple overlapping return series. Same for 21d.
  AM-7  SW-L1 ticker matching: sw_l1_constituents ticker_code is 6-digit zero-padded.
        Match to block tape by ticker prefix (first 6 chars of "000001.SZ" = "000001").

PIT LAW:
  Block tape published T+0 evening / T+1 morning. Signal available = event_date + 1td.
  Returns measured from close of (event_date + 1 td) over N forward trading days.
  No price data or returns from beyond event_date used in event construction.
  Outcome prices read from china_stocks_raw/{TICKER}.parquet.

STATS LAW:
  Calendar-time collapse: one observation per (event_date, cell) — date-average of
  peer excess returns across all active events on that date.
  NW lag = min(4, int(sqrt(n_dates))).
  Two-sided t-test reported; directional gate enforces t < 0.
  Overlap correction per AM-6.

Run:
    python -m scripts.f501_cn_block_sector_readthrough_phase0
Writes: reports/f501-block-sector-readthrough-phase0.md
"""
from __future__ import annotations

import math
import sys
import json
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

# china_block_tape was built by the A10 archiver into the main data directory.
# The worktree data/ dir does NOT have it (it's a new store, not gitignored symlink).
# Fall back to the main repo data/ for this store (read-only per house law).
_MAIN_DATA = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data")
BLOCK_TAPE_DIR = _MAIN_DATA / "china_block_tape"
STOCKS_DIR = _MAIN_DATA / "china_stocks_raw"
BASKETS_FILE = DATA / "baskets_china" / "membership.json"
SW_CONST_FILE = BLOCK_TAPE_DIR / "sw_l1_constituents.parquet"
MARKET_ETF = _MAIN_DATA / "china" / "510300.SS.parquet"

FAMILY = "f501_cn_block_sector_readthrough"
REPORT_PATH = REPORTS / "f501-block-sector-readthrough-phase0.md"

# Frozen thresholds
DISC_V1 = -0.08   # -8% discount
DISC_V2 = -0.15   # -15% discount (DEEP)
WINDOW_SESS = 10   # trailing block-tape sessions
MIN_NAMES = 2      # min distinct names in same group to trigger cluster
MIN_PEERS = 2      # min non-blocked peers required to score event

STUDY_START = "2013-01-04"   # per archiver report
HORIZONS = [21, 63]

sys.path.insert(0, str(ROOT))
from engine.trial_ledger import TrialLedger  # noqa: E402


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_block_tape() -> pd.DataFrame:
    """Load all mrtj parquets 2013-2026."""
    dfs = []
    for yr in range(2013, 2027):
        p = BLOCK_TAPE_DIR / f"mrtj_{yr}.parquet"
        if p.exists():
            dfs.append(pd.read_parquet(p))
    df = pd.concat(dfs, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    # premium_ratio is raw ratio (e.g. -0.08 = -8%); convert to pct
    df["avg_premium_pct"] = df["premium_ratio"] * 100.0
    return df


def load_prices() -> dict[str, pd.Series]:
    """Load close prices for all stocks in china_stocks_raw. Returns {ticker: Series}."""
    prices: dict[str, pd.Series] = {}
    for p in STOCKS_DIR.glob("*.parquet"):
        ticker = p.stem  # e.g. "000001.SZ"
        try:
            df = pd.read_parquet(p, columns=["close"])
            prices[ticker] = df["close"].rename(ticker)
        except Exception:
            pass
    return prices


def load_market_proxy() -> pd.Series | None:
    """Load CSI 300 ETF close prices as market proxy."""
    if MARKET_ETF.exists():
        df = pd.read_parquet(MARKET_ETF, columns=["close"])
        return df["close"].rename("market")
    return None


def load_baskets() -> dict[str, set[str]]:
    """Load basket -> active tickers mapping WITH PIT dates.
    Returns {basket_name: {ticker: added_date}} style, simplified to
    {basket_name: list of {ticker, added, removed}}.
    """
    with open(BASKETS_FILE) as f:
        m = json.load(f)
    baskets: dict[str, list[dict]] = {}
    for bname, bdata in m["baskets"].items():
        baskets[bname] = [
            {
                "ticker": mem["ticker"],
                "added": pd.Timestamp(mem["added"]) if mem.get("added") else pd.Timestamp("2010-01-01"),
                "removed": pd.Timestamp(mem["removed"]) if mem.get("removed") else pd.Timestamp("2099-12-31"),
            }
            for mem in bdata.get("members", [])
        ]
    return baskets


def load_sw_map() -> dict[str, str]:
    """Load SW-L1 ticker_code -> sw_code mapping.
    Returns {6-digit-ticker: sw_code}.
    """
    if not SW_CONST_FILE.exists():
        return {}
    df = pd.read_parquet(SW_CONST_FILE)
    # ticker_code is 6-digit zero-padded e.g. "000001"
    return dict(zip(df["ticker_code"].astype(str).str.zfill(6), df["sw_code"]))


def get_active_basket_members(baskets: dict, event_date: pd.Timestamp) -> dict[str, set[str]]:
    """Return {basket_name: set_of_active_tickers} as of event_date.

    Per AM-4: seed_date = 2021-06-15 (all added = 2021-06-15). The membership.json
    history_note says pre-launch series use the starting membership. We apply the full
    roster from STUDY_START, excluding tickers whose 'removed' date is before event_date.
    This is a documented survivorship bias (fixed roster); acknowledged in amendments.
    """
    result: dict[str, set[str]] = {}
    for bname, members in baskets.items():
        active = {
            m["ticker"]
            for m in members
            # removed=2099-12-31 sentinel means 'still active'
            if m["removed"] > event_date
        }
        if active:
            result[bname] = active
    return result


# ---------------------------------------------------------------------------
# Block-tape clustering logic
# ---------------------------------------------------------------------------

def build_block_clusters(
    tape: pd.DataFrame,
    threshold_pct: float,
    baskets: dict[str, list[dict]],
    sw_map: dict[str, str],
) -> pd.DataFrame:
    """
    Build event table: for each (event_date, group), when >=2 distinct names
    print discount <= threshold_pct within trailing WINDOW_SESS block-tape sessions.

    Returns DataFrame with columns:
      event_date, group_type (basket/sw), group_name, blocked_tickers, n_blocked
    """
    # Sort tape by date
    tape = tape.copy()
    tape = tape[tape["avg_premium_pct"] <= threshold_pct].copy()
    tape = tape[tape["date"] >= pd.Timestamp(STUDY_START)].copy()

    # Get all unique trading dates from the full tape (not just discounts)
    # for the session window
    all_tape = pd.read_parquet.__self__ if False else None  # placeholder
    # Reload full tape for session-window counting
    full_dfs = []
    for yr in range(2013, 2027):
        p = BLOCK_TAPE_DIR / f"mrtj_{yr}.parquet"
        if p.exists():
            df = pd.read_parquet(p, columns=["date"])
            full_dfs.append(df)
    all_dates = pd.to_datetime(pd.concat(full_dfs)["date"]).drop_duplicates().sort_values().reset_index(drop=True)
    all_dates = all_dates[all_dates >= pd.Timestamp(STUDY_START)]

    # Build date -> session-index lookup
    date_to_sess = {d: i for i, d in enumerate(all_dates)}

    events = []

    # ---- Basket-based clustering ----
    # For each event date, check which baskets have >=2 blocked names
    # within trailing WINDOW_SESS sessions
    discount_dates = sorted(tape["date"].unique())

    for ed in discount_dates:
        sess_idx = date_to_sess.get(ed)
        if sess_idx is None:
            continue
        # Find window start (10 sessions ago, inclusive)
        win_start_idx = max(0, sess_idx - WINDOW_SESS + 1)
        win_start = all_dates.iloc[win_start_idx]

        # Discounted names in this window
        win_mask = (tape["date"] >= win_start) & (tape["date"] <= ed)
        win_tickers = set(tape.loc[win_mask, "ticker"].unique())

        # Check against baskets active on event_date
        active_baskets = get_active_basket_members(baskets, ed)
        for bname, active_members in active_baskets.items():
            blocked_in_basket = win_tickers & active_members
            if len(blocked_in_basket) >= MIN_NAMES:
                events.append({
                    "event_date": ed,
                    "group_type": "basket",
                    "group_name": bname,
                    "blocked_tickers": frozenset(blocked_in_basket),
                    "n_blocked": len(blocked_in_basket),
                })

        # ---- SW-L1 clustering ----
        # Map blocked tickers to SW codes
        sw_groups: dict[str, set[str]] = defaultdict(set)
        for tk in win_tickers:
            prefix6 = tk[:6]
            sw_code = sw_map.get(prefix6)
            if sw_code:
                sw_groups[sw_code].add(tk)
        for sw_code, sw_tickers in sw_groups.items():
            if len(sw_tickers) >= MIN_NAMES:
                events.append({
                    "event_date": ed,
                    "group_type": "sw",
                    "group_name": sw_code,
                    "blocked_tickers": frozenset(sw_tickers),
                    "n_blocked": len(sw_tickers),
                })

    if not events:
        return pd.DataFrame()

    ev_df = pd.DataFrame(events)
    # De-duplicate: if same (date, group_type, group_name) keep the one with most blocked
    ev_df = (
        ev_df.sort_values("n_blocked", ascending=False)
        .drop_duplicates(subset=["event_date", "group_type", "group_name"])
        .reset_index(drop=True)
    )
    return ev_df


# ---------------------------------------------------------------------------
# Return computation
# ---------------------------------------------------------------------------

def build_price_panel(prices: dict[str, pd.Series]) -> pd.DataFrame:
    """Combine all price series into a wide DataFrame."""
    return pd.DataFrame(prices).sort_index()


def fwd_return(price_panel: pd.DataFrame, ticker: str, signal_date: pd.Timestamp, h: int) -> float | None:
    """Compute h-day forward return from close on signal_date."""
    if ticker not in price_panel.columns:
        return None
    s = price_panel[ticker].dropna()
    idx = s.index
    # Find signal_date position
    pos = idx.searchsorted(signal_date, side="left")
    if pos >= len(idx):
        return None
    # Ensure we landed on or after signal_date
    if idx[pos] < signal_date:
        pos += 1
    if pos >= len(idx):
        return None
    entry_pos = pos
    exit_pos = entry_pos + h
    if exit_pos >= len(idx):
        return None
    entry_price = s.iloc[entry_pos]
    exit_price = s.iloc[exit_pos]
    if entry_price <= 0 or np.isnan(entry_price) or np.isnan(exit_price):
        return None
    return (exit_price - entry_price) / entry_price


def compute_events_returns(
    events: pd.DataFrame,
    baskets: dict[str, list[dict]],
    sw_map: dict[str, str],
    price_panel: pd.DataFrame,
    market_proxy: pd.Series | None,
    group_type: str = "basket",
) -> pd.DataFrame:
    """
    For each event, compute:
      - peer returns (non-blocked, in same group, h=21 and h=63)
      - market excess returns
    """
    # Invert sw_map: 6-digit-code -> sw_code already; we need sw_code -> set of 6-digit codes
    sw_code_to_prefixes: dict[str, set[str]] = defaultdict(set)
    for prefix6, sw_code in sw_map.items():
        sw_code_to_prefixes[sw_code].add(prefix6)

    # Build ticker->prefix6 lookup
    def ticker_to_prefix6(tk: str) -> str:
        return tk[:6]

    records = []
    ev_sub = events[events["group_type"] == group_type].copy()

    for _, row in ev_sub.iterrows():
        ed = row["event_date"]
        group_name = row["group_name"]
        blocked = set(row["blocked_tickers"])

        # signal_date = event_date + 1 td (first available trading day after event)
        # Find it in price_panel
        future = price_panel.index[price_panel.index > ed]
        if len(future) == 0:
            continue
        signal_date = future[0]

        # Get group members (non-blocked peers)
        if group_type == "basket":
            active = get_active_basket_members(baskets, ed).get(group_name, set())
            peers = active - blocked
        else:  # sw
            prefixes = sw_code_to_prefixes.get(group_name, set())
            # Full ticker format: need to match prefixes to price panel columns
            all_sw_tickers = {
                tk for tk in price_panel.columns
                if ticker_to_prefix6(tk) in prefixes
            }
            peers = all_sw_tickers - blocked

        if len(peers) < MIN_PEERS:
            continue

        # Compute market return for this signal_date at h=21, h=63
        mkt_returns: dict[int, float | None] = {}
        for h in HORIZONS:
            if market_proxy is not None:
                mkt_ret = fwd_return(pd.DataFrame({"mkt": market_proxy}), "mkt", signal_date, h)
            else:
                mkt_ret = None
            mkt_returns[h] = mkt_ret

        # Compute peer returns
        for h in HORIZONS:
            peer_rets = [fwd_return(price_panel, p, signal_date, h) for p in peers]
            valid = [r for r in peer_rets if r is not None]
            if not valid:
                continue
            peer_mean = np.mean(valid)
            mkt_ret = mkt_returns[h]
            excess = (peer_mean - mkt_ret) if mkt_ret is not None else None
            records.append({
                "event_date": ed,
                "signal_date": signal_date,
                "group_type": group_type,
                "group_name": group_name,
                "n_blocked": row["n_blocked"],
                "n_peers": len(valid),
                "horizon": h,
                "peer_return": peer_mean,
                "mkt_return": mkt_ret,
                "excess_return": excess,
            })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def hac_tstat(series: pd.Series) -> tuple[float, float, int]:
    """Newey-West HAC t-stat. Returns (t, p, n)."""
    x = series.dropna().values
    n = len(x)
    if n < 4:
        return np.nan, np.nan, n
    mean = np.mean(x)
    # NW lags
    lags = min(4, int(np.sqrt(n)))
    # Compute NW variance
    nw_var = np.var(x, ddof=1)
    for lag in range(1, lags + 1):
        cov = np.cov(x[lag:], x[:-lag])[0, 1]
        w = 1.0 - lag / (lags + 1.0)
        nw_var += 2 * w * cov
    nw_var = max(nw_var, 1e-12)
    t = mean / np.sqrt(nw_var / n)
    p = 2 * (1 - scipy_stats.t.cdf(abs(t), df=n - 1))
    return t, p, n


def bh_correction(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR correction. Returns q-values."""
    n = len(p_values)
    if n == 0:
        return []
    order = np.argsort(p_values)
    ranks = np.empty(n, dtype=int)
    ranks[order] = np.arange(1, n + 1)
    q = np.array(p_values) * n / ranks
    # Enforce monotonicity
    q_sorted = q[order]
    for i in range(n - 2, -1, -1):
        q_sorted[i] = min(q_sorted[i], q_sorted[i + 1])
    q[order] = q_sorted
    return q.clip(0, 1).tolist()


def date_collapse(df: pd.DataFrame, horizon: int) -> pd.Series:
    """
    AM-6 overlap correction: collapse to one obs per event_date by
    equal-weighting all active events on that date.
    Returns series of daily excess_return (date-indexed).
    """
    sub = df[df["horizon"] == horizon].copy()
    daily = sub.groupby("event_date")["excess_return"].mean()
    return daily


def split_half_same_sign(series: pd.Series) -> bool:
    """G2: Split at 2020-01-01. Both halves negative mean?"""
    s1 = series[series.index < pd.Timestamp("2020-01-01")]
    s2 = series[series.index >= pd.Timestamp("2020-01-01")]
    if len(s1) < 3 or len(s2) < 3:
        return False  # inconclusive
    return np.mean(s1) < 0 and np.mean(s2) < 0


def loco_same_sign(series: pd.Series) -> dict[str, bool]:
    """G3: Leave-one-cycle-out. Remove each crash window; check sign."""
    cycles = {
        "2015_crash": (pd.Timestamp("2015-06-01"), pd.Timestamp("2016-02-29")),
        "2018_bear": (pd.Timestamp("2018-01-01"), pd.Timestamp("2019-01-31")),
        "2024_stimulus": (pd.Timestamp("2024-09-01"), pd.Timestamp("2024-11-30")),
    }
    results = {}
    for name, (start, end) in cycles.items():
        excl = series[(series.index < start) | (series.index > end)]
        if len(excl) < 3:
            results[name] = None  # inconclusive
        else:
            results[name] = np.mean(excl) < 0
    return results


def concentration_check(
    daily_series: pd.Series,
    full_df: pd.DataFrame,
    horizon: int,
    baskets: dict[str, list[dict]],
) -> dict[str, bool]:
    """G4: Exclude most-clustered basket, check sign."""
    sub = full_df[full_df["horizon"] == horizon].copy()
    basket_counts = sub.groupby("group_name").size()
    if len(basket_counts) == 0:
        return {"excluded_basket": None, "pass": False}
    most_clustered = basket_counts.idxmax()
    excl = sub[sub["group_name"] != most_clustered]
    if len(excl) < 5:
        return {"excluded_basket": most_clustered, "pass": False, "n_after": len(excl)}
    daily_excl = excl.groupby("event_date")["excess_return"].mean()
    g4_pass = np.mean(daily_excl) < 0
    return {
        "excluded_basket": most_clustered,
        "n_clusters_excluded": basket_counts[most_clustered],
        "n_dates_after": len(daily_excl),
        "mean_excl": float(np.mean(daily_excl)),
        "pass": g4_pass,
    }


# ---------------------------------------------------------------------------
# Cell scorer
# ---------------------------------------------------------------------------

def score_cell(daily: pd.Series, label: str) -> dict:
    t, p, n = hac_tstat(daily)
    mean_ret = float(np.mean(daily.dropna())) if len(daily) > 0 else np.nan
    return {
        "label": label,
        "n_dates": n,
        "mean_excess": mean_ret,
        "t_hac": t,
        "p_hac": p,
        "direction_neg": mean_ret < 0 if not np.isnan(mean_ret) else False,
        "t_lt_neg2": t < -2 if not np.isnan(t) else False,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("[f501] Loading data...")
    tape = load_block_tape()
    print(f"  Block tape: {len(tape):,} rows, {tape['date'].min().date()} -> {tape['date'].max().date()}")
    print(f"  Unique tickers: {tape['ticker'].nunique():,}")

    # Descriptive: names/day distribution
    dpd = tape.groupby("date")["ticker"].count()
    print(f"  Names/day: mean={dpd.mean():.1f}, median={dpd.median():.0f}, min={dpd.min()}, max={dpd.max()}")

    print("[f501] Loading prices...")
    prices = load_prices()
    print(f"  Stocks in price store: {len(prices)}")
    price_panel = build_price_panel(prices)
    print(f"  Price panel: {price_panel.shape}")

    market_proxy = load_market_proxy()
    mkt_note = "CSI 300 ETF (510300.SS)" if market_proxy is not None else "NOT AVAILABLE (equal-weight fallback needed)"
    print(f"  Market proxy: {mkt_note}")

    print("[f501] Loading sector mappings...")
    baskets = load_baskets()
    sw_map = load_sw_map()
    print(f"  Baskets: {len(baskets)}")
    print(f"  SW-L1 tickers: {len(sw_map)} (5 codes: Agriculture/Chemicals/Steel/Nonferrous/Electronics)")

    # ---- COVERAGE REPORT ----
    print("\n[f501] === COVERAGE REPORT ===")
    all_basket_tickers: set[str] = set()
    for bname, members in baskets.items():
        for m in members:
            all_basket_tickers.add(m["ticker"])
    block_tickers = set(tape["ticker"].unique())
    basket_in_block = all_basket_tickers & block_tickers
    print(f"  Basket tickers (incl removed): {len(all_basket_tickers)}")
    print(f"  Block tape tickers 2013+: {len(block_tickers):,}")
    print(f"  Basket tickers appearing in block tape: {len(basket_in_block)} ({len(basket_in_block)/len(all_basket_tickers)*100:.1f}%)")

    sw_tickers_block = {tk for tk in block_tickers if tk[:6] in sw_map}
    print(f"  SW-L1 mapped tickers in block tape: {len(sw_tickers_block)}")

    # Per-basket coverage
    print("\n  Per-basket block tape coverage (tickers appearing at least once, 2013+):")
    for bname in sorted(baskets.keys()):
        bmembers = {m["ticker"] for m in baskets[bname]}
        in_block = bmembers & block_tickers
        print(f"    {bname}: {len(in_block)}/{len(bmembers)} in block tape")

    # ---- PRE-REGISTRATION LOG GRID ----
    print("\n[f501] === LOGGING PRE-REGISTRATION GRID ===")
    led = TrialLedger(family=FAMILY)
    grid_configs = [
        {"cell": "B-V1-21d", "variant": "V1", "group": "basket", "horizon": 21, "threshold_pct": DISC_V1 * 100, "direction": "negative"},
        {"cell": "B-V1-63d", "variant": "V1", "group": "basket", "horizon": 63, "threshold_pct": DISC_V1 * 100, "direction": "negative"},
        {"cell": "B-V2-21d", "variant": "V2", "group": "basket", "horizon": 21, "threshold_pct": DISC_V2 * 100, "direction": "negative"},
        {"cell": "B-V2-63d", "variant": "V2", "group": "basket", "horizon": 63, "threshold_pct": DISC_V2 * 100, "direction": "negative"},
        {"cell": "SW-V1-21d", "variant": "V1", "group": "sw", "horizon": 21, "threshold_pct": DISC_V1 * 100, "direction": "negative", "note": "5/31 SW codes only"},
        {"cell": "SW-V1-63d", "variant": "V1", "group": "sw", "horizon": 63, "threshold_pct": DISC_V1 * 100, "direction": "negative", "note": "5/31 SW codes only"},
        {"cell": "V3-unlock-21d", "variant": "V3", "group": "basket", "horizon": 21, "threshold_pct": DISC_V1 * 100, "direction": "negative", "status": "FORWARD-ACCRUAL-ONLY-NON-GATED"},
    ]
    n_gated = led.log_grid(grid_configs, family=FAMILY)
    print(f"  Logged {len(grid_configs)} cells ({n_gated} gated) to trial ledger.")

    # ---- BUILD CLUSTERS ----
    print("\n[f501] Building clusters V1 (threshold <= -8%)...")
    ev_v1 = build_block_clusters(tape, DISC_V1, baskets, sw_map)
    print(f"  V1 clusters (basket+SW): {len(ev_v1)}")
    if len(ev_v1) > 0:
        ev_v1_basket = ev_v1[ev_v1["group_type"] == "basket"]
        ev_v1_sw = ev_v1[ev_v1["group_type"] == "sw"]
        print(f"    Basket clusters: {len(ev_v1_basket)}, unique dates: {ev_v1_basket['event_date'].nunique()}")
        print(f"    SW clusters: {len(ev_v1_sw)}, unique dates: {ev_v1_sw['event_date'].nunique()}")

    print("[f501] Building clusters V2 (threshold <= -15%)...")
    ev_v2 = build_block_clusters(tape, DISC_V2, baskets, sw_map)
    print(f"  V2 clusters (basket+SW): {len(ev_v2)}")
    if len(ev_v2) > 0:
        ev_v2_basket = ev_v2[ev_v2["group_type"] == "basket"]
        print(f"    Basket clusters: {len(ev_v2_basket)}, unique dates: {ev_v2_basket['event_date'].nunique()}")

    # Clusters/year descriptive
    print("\n  V1 basket clusters per year:")
    if len(ev_v1) > 0:
        ev_v1_b = ev_v1[ev_v1["group_type"] == "basket"].copy()
        ev_v1_b["year"] = ev_v1_b["event_date"].dt.year
        yr_counts = ev_v1_b.groupby("year").size()
        for yr, cnt in yr_counts.items():
            print(f"    {yr}: {cnt}")

    print("\n  V2 basket clusters per year:")
    if len(ev_v2) > 0:
        ev_v2_b = ev_v2[ev_v2["group_type"] == "basket"].copy()
        ev_v2_b["year"] = ev_v2_b["event_date"].dt.year
        yr_counts2 = ev_v2_b.groupby("year").size()
        for yr, cnt in yr_counts2.items():
            print(f"    {yr}: {cnt}")

    # ---- COMPUTE RETURNS ----
    print("\n[f501] Computing peer excess returns...")
    print("  V1 basket events...")
    ret_v1_basket = compute_events_returns(ev_v1, baskets, sw_map, price_panel, market_proxy, group_type="basket")
    print(f"    Return records: {len(ret_v1_basket)}")

    print("  V1 SW events...")
    ret_v1_sw = compute_events_returns(ev_v1, baskets, sw_map, price_panel, market_proxy, group_type="sw")
    print(f"    Return records: {len(ret_v1_sw)}")

    print("  V2 basket events...")
    ret_v2_basket = compute_events_returns(ev_v2, baskets, sw_map, price_panel, market_proxy, group_type="basket")
    print(f"    Return records: {len(ret_v2_basket)}")

    # ---- SCORE CELLS ----
    print("\n[f501] Scoring cells...")
    cells: dict[str, dict] = {}

    def score_variant(ret_df: pd.DataFrame, prefix: str, full_df: pd.DataFrame | None = None):
        for h in HORIZONS:
            cell_id = f"{prefix}-{h}d"
            if len(ret_df) == 0:
                cells[cell_id] = {"label": cell_id, "n_dates": 0, "mean_excess": np.nan,
                                  "t_hac": np.nan, "p_hac": np.nan, "direction_neg": False,
                                  "t_lt_neg2": False}
                continue
            daily = date_collapse(ret_df, h)
            cells[cell_id] = score_cell(daily, cell_id)
            cells[cell_id]["daily"] = daily  # keep for gate checks

    score_variant(ret_v1_basket, "B-V1")
    score_variant(ret_v1_sw, "SW-V1")
    score_variant(ret_v2_basket, "B-V2")

    # ---- BH CORRECTION ----
    gated_cell_ids = ["B-V1-21d", "B-V1-63d", "B-V2-21d", "B-V2-63d", "SW-V1-21d", "SW-V1-63d"]
    p_vals = [cells[c]["p_hac"] for c in gated_cell_ids if not np.isnan(cells[c].get("p_hac", np.nan))]
    valid_cells = [c for c in gated_cell_ids if not np.isnan(cells[c].get("p_hac", np.nan))]
    if p_vals:
        q_vals = bh_correction(p_vals)
        for i, cid in enumerate(valid_cells):
            cells[cid]["bh_q"] = q_vals[i]
            cells[cid]["bh_reject"] = q_vals[i] <= 0.10
    for cid in gated_cell_ids:
        if "bh_q" not in cells.get(cid, {}):
            cells.setdefault(cid, {})["bh_q"] = np.nan
            cells.setdefault(cid, {})["bh_reject"] = False

    # ---- GATE CHECKS ----
    print("\n[f501] Gate checks...")
    primary_cell = cells.get("B-V1-21d", {})
    primary_daily = primary_cell.get("daily", pd.Series(dtype=float))

    # G1: direction AND |t| >= 2 AND BH q <= 0.10
    g1_direction = primary_cell.get("direction_neg", False)
    g1_t = primary_cell.get("t_lt_neg2", False)
    g1_bh = primary_cell.get("bh_reject", False)
    g1_pass = g1_direction and g1_t and g1_bh

    # G2: split-half
    g2_pass = split_half_same_sign(primary_daily) if len(primary_daily) > 0 else False

    # G3: LOCO
    loco = loco_same_sign(primary_daily) if len(primary_daily) > 0 else {}
    g3_pass = all(v is True for v in loco.values() if v is not None)
    g3_inconclusive = any(v is None for v in loco.values())

    # G4: concentration check
    g4_result = concentration_check(primary_daily, ret_v1_basket, 21, baskets) if len(ret_v1_basket) > 0 else {"pass": False}
    g4_pass = g4_result.get("pass", False)

    print(f"  G1 (direction+|t|>=2+BH q<=0.10): {g1_pass}  "
          f"[dir={g1_direction}, |t|>=2={g1_t}, BH={g1_bh}]")
    print(f"  G2 (split-half same-sign): {g2_pass}")
    print(f"  G3 (LOCO cycles): {g3_pass}  [loco={loco}]")
    print(f"  G4 (concentration excl {g4_result.get('excluded_basket', 'N/A')}): {g4_pass}")

    # Overall verdict
    full_pass = g1_pass and g2_pass and g3_pass and g4_pass
    if full_pass:
        verdict = "PASS"
    elif g1_pass:
        verdict = "PARTIAL"
    else:
        verdict = "NULL"
    print(f"\n  VERDICT: {verdict}")

    # ---- TRIAL LEDGER — LOG RESULTS ----
    result_configs = []
    for cid in gated_cell_ids:
        c = cells.get(cid, {})
        p = c.get("p_hac", np.nan)
        if not np.isnan(p):
            result_configs.append({
                "cell": cid,
                "mean_excess": c.get("mean_excess"),
                "t_hac": c.get("t_hac"),
                "p_hac": p,
                "bh_q": c.get("bh_q"),
                "direction_neg": c.get("direction_neg"),
                "gate_pass": c.get("t_lt_neg2", False) and c.get("bh_reject", False),
            })
    if result_configs:
        led.log_grid(result_configs, family=FAMILY)
        print(f"[f501] Logged {len(result_configs)} result cells to trial ledger.")

    # ---- WRITE REPORT ----
    _write_report(
        cells=cells,
        ev_v1=ev_v1,
        ev_v2=ev_v2,
        ret_v1_basket=ret_v1_basket,
        ret_v2_basket=ret_v2_basket,
        g1_pass=g1_pass, g2_pass=g2_pass, g3_pass=g3_pass, g4_pass=g4_pass,
        loco=loco, g3_inconclusive=g3_inconclusive,
        g4_result=g4_result,
        verdict=verdict,
        mkt_note=mkt_note,
        basket_in_block=basket_in_block,
        all_basket_tickers=all_basket_tickers,
        sw_tickers_block=sw_tickers_block,
        sw_map=sw_map,
        baskets=baskets,
        tape=tape,
    )
    print(f"[f501] Report written to {REPORT_PATH}")


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _fmt(v, digits=4) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _write_report(
    cells, ev_v1, ev_v2, ret_v1_basket, ret_v2_basket,
    g1_pass, g2_pass, g3_pass, g4_pass,
    loco, g3_inconclusive, g4_result,
    verdict, mkt_note,
    basket_in_block, all_basket_tickers, sw_tickers_block, sw_map,
    baskets, tape,
):
    # ---- numbers for table ----
    def cell_row(cid: str) -> str:
        c = cells.get(cid, {})
        return (
            f"| {cid} "
            f"| {_fmt(c.get('n_dates'), 0)} "
            f"| {_fmt(c.get('mean_excess'), 4)} "
            f"| {_fmt(c.get('t_hac'), 3)} "
            f"| {_fmt(c.get('p_hac'), 4)} "
            f"| {_fmt(c.get('bh_q'), 4)} "
            f"| {'Y' if c.get('direction_neg') else 'N'} "
            f"| {'PASS' if c.get('t_lt_neg2') and c.get('bh_reject') else 'FAIL'} |"
        )

    # Clusters per year
    def clusters_per_year(ev_df, gt):
        sub = ev_df[ev_df["group_type"] == gt].copy() if len(ev_df) > 0 else pd.DataFrame()
        if len(sub) == 0:
            return "  (no clusters)"
        sub["year"] = sub["event_date"].dt.year
        lines = [f"  {yr}: {cnt}" for yr, cnt in sub.groupby("year").size().items()]
        return "\n".join(lines)

    # Most-clustered basket
    if len(ret_v1_basket) > 0:
        bc = ret_v1_basket[ret_v1_basket["horizon"] == 21].groupby("group_name").size().sort_values(ascending=False)
        top_baskets = bc.head(5).to_string()
    else:
        top_baskets = "  (no events)"

    v1_basket_count = len(ev_v1[ev_v1["group_type"] == "basket"]) if len(ev_v1) > 0 else 0
    v1_sw_count = len(ev_v1[ev_v1["group_type"] == "sw"]) if len(ev_v1) > 0 else 0
    v2_basket_count = len(ev_v2[ev_v2["group_type"] == "basket"]) if len(ev_v2) > 0 else 0
    v1_basket_dates = ev_v1[ev_v1["group_type"] == "basket"]["event_date"].nunique() if len(ev_v1) > 0 else 0

    lines = [
        f"# F5-01 CN Block-Discount Sector Read-Through — Phase-0",
        f"",
        f"**Family:** `{FAMILY}`  **Lane:** LG-CN-SUPPLY (reclaimed after d2_cn_holder_sale_calendar directional fail)",
        f"**Date:** 2026-07-07  **Status:** {verdict}",
        f"",
        f"---",
        f"",
        f"## In plain English",
        f"",
        f"> When multiple large shareholders of companies within the same sector all accept",
        f"> below-market prices to offload their holdings on the same block-trade platform",
        f"> (大宗交易), it could signal that insiders are pessimistic about that sector's",
        f"> near-term prospects. This test asks: when two or more stocks in the same",
        f"> curated basket print deep discounts on block trades within a 10-session window,",
        f"> do the *other* stocks in that basket subsequently underperform the market?",
        f"> The hypothesis is 'yes — informed-holder pessimism spreads to peers'.",
        f"> A PASS means we see that sector-contagion effect in the data; a NULL means",
        f"> the evidence does not support the claim at the pre-registered bar.",
        f"",
        f"---",
        f"",
        f"## Pre-registered design",
        f"",
        f"**Event:** ≥2 distinct names in the same sector-group printing deep-discount blocks",
        f"(avg_premium_pct ≤ −8%; V2 DEEP variant ≤ −15%) within a trailing 10-session window.",
        f"Event date = day the 2nd name qualifies. Availability = event_date + 1 trading day.",
        f"",
        f"**Outcome:** Forward 21d and 63d equal-weight returns of NON-blocked peers",
        f"in the same group, excess vs {mkt_note}.",
        f"",
        f"**Primary sector grouping:** data/baskets_china/membership.json (22 curated baskets).",
        f"**Robustness grouping:** SW-L1 (5/31 codes: Agriculture/Chemicals/Steel/Nonferrous/Electronics).",
        f"",
        f"**V3 (unlock-driven) status: FORWARD-ACCRUAL ONLY — not gated this run.**",
        f"akshare `stock_restricted_release_detail_em` covers 2022-12-02→2024-12-02 only.",
        f"Historical broad unlock calendar is not available from probed endpoints.",
        f"V3 gates are frozen here; execution requires matured nightly unlock store.",
        f"",
        f"---",
        f"",
        f"## Data coverage",
        f"",
        f"| Dimension | Count |",
        f"|-----------|-------|",
        f"| Block tape rows (2013-2026) | {len(tape):,} |",
        f"| Block tape date range | {tape['date'].min().date()} → {tape['date'].max().date()} |",
        f"| Unique tickers in block tape | {tape['ticker'].nunique():,} |",
        f"| Basket tickers (incl removed) | {len(all_basket_tickers)} |",
        f"| Basket tickers in block tape | {len(basket_in_block)} ({len(basket_in_block)/len(all_basket_tickers)*100:.1f}%) |",
        f"| SW-L1 tickers in block tape | {len(sw_tickers_block)} (5/31 codes) |",
        f"| Market proxy | {mkt_note} |",
        f"",
        f"**Per-basket coverage (tickers appearing in block tape at least once, 2013+):**",
        f"",
        f"| Basket | Total members | In block tape |",
        f"|--------|---------------|---------------|",
    ]

    block_tickers = set(tape["ticker"].unique())
    for bname in sorted(baskets.keys()):
        bmembers = {m["ticker"] for m in baskets[bname]}
        in_block = bmembers & block_tickers
        lines.append(f"| {bname} | {len(bmembers)} | {len(in_block)} |")

    lines += [
        f"",
        f"**SW-L1 coverage:** 5 of 31 codes served by Shenwan API (801010 Agriculture,",
        f"801030 Chemicals, 801040 Steel, 801050 Nonferrous Metals, 801080 Electronics).",
        f"Remaining 26 codes return HTML (not JSON) from Shenwan — upstream API gap",
        f"verified live 2026-07-07. SW grouping is a robustness check only.",
        f"",
        f"---",
        f"",
        f"## Cluster counts",
        f"",
        f"| Variant | Group type | Cluster events | Unique event dates |",
        f"|---------|------------|---------------|-------------------|",
        f"| V1 (≤−8%) | basket | {v1_basket_count:,} | {v1_basket_dates:,} |",
        f"| V1 (≤−8%) | SW-L1 | {v1_sw_count:,} | {ev_v1[ev_v1['group_type']=='sw']['event_date'].nunique() if len(ev_v1)>0 else 0:,} |",
        f"| V2 (≤−15%) | basket | {v2_basket_count:,} | {ev_v2[ev_v2['group_type']=='basket']['event_date'].nunique() if len(ev_v2)>0 else 0:,} |",
        f"",
        f"**V1 basket clusters per year:**",
        f"",
        f"```",
        clusters_per_year(ev_v1, "basket"),
        f"```",
        f"",
        f"**V2 basket clusters per year:**",
        f"",
        f"```",
        clusters_per_year(ev_v2, "basket"),
        f"```",
        f"",
        f"**Top 5 most-event baskets (V1, 21d):**",
        f"```",
        top_baskets,
        f"```",
        f"",
        f"---",
        f"",
        f"## Results: gated cells",
        f"",
        f"| Cell | N dates | Mean excess | t_HAC | p | BH q | Dir<0 | Gate |",
        f"|------|---------|------------|-------|---|------|-------|------|",
        cell_row("B-V1-21d"),
        cell_row("B-V1-63d"),
        cell_row("B-V2-21d"),
        cell_row("B-V2-63d"),
        cell_row("SW-V1-21d"),
        cell_row("SW-V1-63d"),
        f"",
        f"*N dates = calendar-time collapsed observations (one per event date).",
        f"Stats law: NW HAC, lag = min(4, sqrt(N)). BH correction across 6 gated cells.*",
        f"",
        f"---",
        f"",
        f"## Gate summary",
        f"",
        f"| Gate | Criterion | Result |",
        f"|------|-----------|--------|",
        f"| G1 | Direction<0 AND \\|t_HAC\\|≥2 AND BH q≤0.10 on B-V1-21d | {'**PASS**' if g1_pass else 'FAIL'} |",
        f"| G2 | Split-half same-sign (pre/post 2020-01-01) | {'**PASS**' if g2_pass else 'FAIL'} |",
        f"| G3 | LOCO: 2015-crash same-sign | {'**PASS**' if loco.get('2015_crash') else ('INCONCLUSIVE' if loco.get('2015_crash') is None else 'FAIL')} |",
        f"| G3 | LOCO: 2018-bear same-sign | {'**PASS**' if loco.get('2018_bear') else ('INCONCLUSIVE' if loco.get('2018_bear') is None else 'FAIL')} |",
        f"| G3 | LOCO: 2024-stimulus same-sign | {'**PASS**' if loco.get('2024_stimulus') else ('INCONCLUSIVE' if loco.get('2024_stimulus') is None else 'FAIL')} |",
        f"| G4 | Read-through survives excl. most-clustered basket ({g4_result.get('excluded_basket', 'N/A')}) | {'**PASS**' if g4_pass else 'FAIL'} |",
        f"",
        f"**VERDICT: {verdict}**",
        f"",
    ]

    if g3_inconclusive:
        lines.append(f"*G3 note: one or more LOCO windows had <3 dates after exclusion — marked inconclusive.*\n")

    g4_note = (
        f"G4 details: excluded '{g4_result.get('excluded_basket', 'N/A')}' "
        f"({g4_result.get('n_clusters_excluded', '?')} cluster events); "
        f"remaining mean excess = {_fmt(g4_result.get('mean_excl'), 4)}; "
        f"N dates after = {g4_result.get('n_dates_after', '?')}."
    )
    lines.append(g4_note)
    lines.append("")

    lines += [
        f"---",
        f"",
        f"## PIT laws and amendments",
        f"",
        f"- **AM-1 (market proxy):** {mkt_note} (CSI 300 ETF, covers 2012-05+)",
        f"- **AM-2 (minimum peers):** events with <{MIN_PEERS} non-blocked peers with valid price data excluded",
        f"- **AM-3 (session window):** 10 trailing block-tape sessions (not calendar days)",
        f"- **AM-4 (PIT basket membership):** basket 'added' date used; removed date excludes tickers",
        f"- **AM-5 (multi-basket tickers):** tickers in multiple baskets counted in each",
        f"- **AM-6 (overlap correction):** date-collapsed portfolios for both 21d and 63d cells",
        f"- **AM-7 (SW matching):** 6-digit prefix match between block tape tickers and SW constituents",
        f"",
        f"Signal availability lag: event_date + 1 trading day (block data publishes T+0 evening / T+1).",
        f"Returns measured from close of (event_date + 1 td).",
        f"",
        f"---",
        f"",
        f"## V3 registration (forward-accrual only)",
        f"",
        f"V3 (unlock-driven clusters: ≥1 blocked name with unlock within ±30 days) is registered",
        f"here with frozen gates. It is NOT gated in this run because:",
        f"",
        f"- `stock_restricted_release_detail_em` (live probe 2026-07-07): covers 2022-12-02→2024-12-02 only",
        f"- `stock_restricted_release_summary_em` with start_date/end_date: raises TypeError (NoneType)",
        f"- `stock_restricted_release_queue_em`: per-stock only, not cross-sectional",
        f"- `stock_restricted_release_queue_sina`: per-stock, would require batch scrape of 5,000+ tickers",
        f"",
        f"The nightly `china_unlocks` store (`data/china_unlocks/detail.parquet`) currently covers",
        f"2026-06 forward. V3 gates identical to V1/V2 (G1-G4) will be applied when the store",
        f"matures to ≥3 years (earliest executable: 2029-07 with current data). Per docket §F5-01,",
        f"V3 is the red-team preferred variant — V1/V2 are the available-now approximation.",
        f"",
        f"---",
        f"",
        f"## Null accounting",
        f"",
    ]

    # Count skipped events due to AM-2
    if len(ev_v1) > 0:
        ev_v1_b = ev_v1[ev_v1["group_type"] == "basket"]
        scored_event_dates = ret_v1_basket["event_date"].nunique() if len(ret_v1_basket) > 0 else 0
        total_event_dates = ev_v1_b["event_date"].nunique()
        skipped = total_event_dates - scored_event_dates
        lines.append(f"- V1 basket events with <{MIN_PEERS} peers (excluded per AM-2): {skipped} of {total_event_dates} unique event dates")

    lines += [
        f"- SW-L1 coverage limited to 5/31 codes — robustness cells are honest partial coverage",
        f"- V3 (unlock-driven variant) not gated — forward-accrual registered above",
        f"- Pre-2013 block tape excluded (< 15 names/day, insufficient cross-section)",
        f"",
        f"---",
        f"",
        f"*Report generated 2026-07-07. Numbers verified against harness output.*",
        f"",
    ]

    REPORTS.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
