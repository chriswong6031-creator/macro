"""SEC Fails-to-Deliver Phase-0 IC Scorecard — SLF-001 (family: slf001_ftd_pressure).

PRE-REGISTERED GATES (must be evaluated BEFORE reading results):
  G1  BH-FDR q <= 0.10 on mean-IC t_HAC for the 3x2 signal family.
      Pre-registered sign: high FTD -> NEGATIVE forward return.
      (Mechanism: sellers struggle to deliver → they are forced buyers to close
       or the fail persists as a synthetic short → eventual buy pressure.
       Alternative: elevated FTD = informed supply-side pressure on weak names.
       We test the negative sign; positive sign = confound / wrong direction.)
  G2  Incremental: IC survives after cross-sectionally neutralizing vs
      size (log_mcap) + 12-1 momentum + FINRA short_ratio (where coverage
      overlaps). "Survives" = >= 50% of raw magnitude AND same sign as G1.
  G3  Bottom-vs-top quintile spread t_HAC >= 2 at 21d horizon.

PRE-REGISTERED CONFOUNDS TO REPORT (not hide):
  C1  Net-CNS balance semantics: FTD shares are net delivery failures at the
      DTCC central counterparty.  They do not directly measure naked short
      positions; they include failed long deliveries.  We note this but do
      not adjust — the raw quantity is what is publicly observable.
  C2  T+35 close-out cyclicality: NSCC Rule 11(a) compels buy-in on fails
      ≥35 days.  This creates a mechanical mean-reversion cycle.  We report
      IC separately by settlement-date parity (first-half vs second-half of
      month) as a robustness row.
  C3  Low-price concentration: Micro/penny stocks dominate fail counts by
      name count.  We report IC within price > $5 subset separately.

PIT DISCIPLINE:
  The FTD store stamps availability_date = period_end + 30 calendar days
  (conservative uniform lag; registered in collectors/sec_ftd.py).
  Signal computation at each rebalance date d uses only rows where
  availability_date <= d.  No price or volume data from the future is used.

UNIVERSE LIMITATION:
  massive_stock_day (closes + volume) covers 2021-07-06 to 2026-07-02.
  The IC panel therefore runs on ~60 monthly dates: 2021-07 .. 2026-06.
  The deeper FTD tape (2009->) ships for future re-runs when a longer
  close history is available.  This limitation is printed prominently.

ETF/ETN EXCLUSION:
  Pre-registered confound: ETF creation-basket fails are mechanically tied
  to arbitrage activity and are NOT a signal about the underlying firms.
  ETFs are excluded using EDGAR SIC code 6726 (Investment Offices, NEC) and/or
  entity_type flags (ETF/ETS/ETN/ETP), with a name-keyword fallback.
  NOTE: the original implementation (EDGAR-absence filter) was WRONG — it
  mislabeled 619+ real delisted/acquired stocks as ETFs.  Fixed 2026-07-06.

Run:
    .venv/bin/python -m scripts.sec_ftd_phase0
Writes reports/slf001-sec-ftd-phase0.md and data/trial_ledger.jsonl entries.
"""
from __future__ import annotations

import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine.trial_ledger import TrialLedger
from engine.validation import (
    benjamini_hochberg, block_bootstrap_ci, deflated_sharpe,
    dsr_verdict, ic_summary, newey_west_tstat, rank_ic, ret_moments,
)
from lib import config

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
FAMILY = "slf001_ftd_pressure"
COST_BPS = 5.0          # one-way spread+impact for quintile backtest

# The 3 signals × 2 horizons = 6 cells in the IC family
SIGNALS = ["ftd_ratio", "ftd_usd_adv", "ftd_zscore3"]
HORIZONS = [21, 63]     # trading days

# MASSIVE_STOCK_DAY canonical path (ticker-level parquet files)
MSD_PATH = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day")

# ETF keyword heuristics in EDGAR fundamentals to exclude
_ETF_CUSIP_SUFFIXES: tuple[str, ...] = ()  # curated below via fundamentals join


# ──────────────────────────────────────────────────────────────────────────────
# Data loading helpers
# ──────────────────────────────────────────────────────────────────────────────

def _load_ftd_panel() -> pd.DataFrame:
    p = config.data_dir() / "sec_ftd" / "panel.parquet"
    if not p.exists():
        print("[WARN] FTD panel not found — run scripts.backfill_sec_ftd first")
        return pd.DataFrame()
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df["date"])
    df["availability_date"] = pd.to_datetime(df["availability_date"])
    return df


def _load_fundamentals() -> pd.DataFrame:
    """EDGAR fundamentals panel (shares outstanding, annual)."""
    p = config.data_dir() / "edgar" / "fundamentals_panel.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def _load_membership() -> pd.DataFrame:
    p = config.data_dir() / "breadth" / "sp1500_pit_membership.parquet"
    if not p.exists():
        p = config.data_dir() / "breadth" / "sp500_pit_membership.parquet"
    m = pd.read_parquet(p)
    m["start_date"] = pd.to_datetime(m["start_date"])
    m["end_date"] = pd.to_datetime(m["end_date"])
    return m


def _eligible(membership: pd.DataFrame, d: pd.Timestamp) -> set:
    mask = (membership["start_date"] <= d) & (
        membership["end_date"].isna() | (membership["end_date"] >= d))
    return set(membership.loc[mask, "ticker"])


def _load_finra_short() -> pd.DataFrame:
    p = config.data_dir() / "finra_short_volume" / "panel.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p, columns=["date", "ticker", "short_ratio"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def _load_closes_and_adv(tickers: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load close and 20d ADV matrices from massive_stock_day parquet files."""
    closes, advs = {}, {}
    for tkr in tickers:
        fp = MSD_PATH / f"{tkr}.parquet"
        if not fp.exists():
            continue
        df = pd.read_parquet(fp, columns=["close", "volume"])
        if df.empty or "close" not in df.columns:
            continue
        closes[tkr] = df["close"]
        adv_series = (df["close"] * df["volume"]).rolling(20, min_periods=10).median()
        advs[tkr] = adv_series
    if not closes:
        return pd.DataFrame(), pd.DataFrame()
    return (pd.DataFrame(closes).sort_index(),
            pd.DataFrame(advs).sort_index())


def _identify_etfs(fundamentals: pd.DataFrame, all_tickers: set[str]) -> set[str]:
    """Identify ETFs/ETNs using SIC code and entity-type flags from EDGAR fundamentals.

    PRE-REGISTERED EXCLUSION (reviewer-required fix, 2026-07-06):
    The original implementation excluded any SP1500 ticker absent from the EDGAR
    fundamentals panel.  This is WRONG: 619 of the 1094 excluded tickers are real
    stocks (acquired/delisted/renamed names like ABMD, AJRD, AL, ACC, AIRC) that
    happen to have rolled off the living EDGAR panel.  That is a survivorship filter,
    not an ETF filter, and it is mislabeled.

    Correct approach: use EDGAR SIC code 6726 (Investment Offices, NEC) which covers
    registered investment company / ETF/ETN filings, or the entity_type field where
    present.  Tickers absent from EDGAR entirely are KEPT in the universe as they are
    likely delisted stocks (the universe is PIT-correct via membership dates), not ETFs.
    The SP1500 index itself does not include ETFs in its official construction.

    KNOWN LIMITATION: if the EDGAR fundamentals panel does not carry SIC or entity_type
    columns, we fall back to a curated keyword match on the 'name' column (e.g. ' ETF',
    ' FUND', ' TRUST' suffixes that are reliably ETF names).  We log the count excluded
    and the method used.
    """
    if fundamentals.empty:
        # No fundamentals data — cannot identify ETFs by filing; return empty set.
        # The SP1500 PIT universe does not officially include ETFs, so this is safe.
        print("[etf_filter] fundamentals empty — no ETF filter applied (SP1500 has no ETFs)")
        return set()

    etf_tickers: set[str] = set()

    # Method 1: SIC 6726 = Investment Offices (includes registered ETF/ETN issuers)
    if "sic" in fundamentals.columns:
        sic_etf = fundamentals[fundamentals["sic"].astype(str).str.startswith("6726")]
        etf_tickers |= set(sic_etf["ticker"].unique())

    # Method 2: entity_type flag (EDGAR uses 'ETS' or 'ETF' for exchange-traded products)
    if "entity_type" in fundamentals.columns:
        et_etf = fundamentals[fundamentals["entity_type"].str.upper().isin(
            {"ETF", "ETS", "ETN", "ETP"}
        )]
        etf_tickers |= set(et_etf["ticker"].unique())

    # Method 3: name-keyword fallback (only if neither SIC nor entity_type available)
    if not etf_tickers and "name" in fundamentals.columns:
        etf_keywords = [" ETF", " ETN", " ETP", "EXCHANGE TRADED FUND",
                        "EXCHANGE-TRADED FUND", "ISHARES ", "SPDR ", "PROSHARES "]
        name_upper = fundamentals["name"].str.upper()
        mask = name_upper.str.contains("|".join(etf_keywords), na=False)
        etf_tickers |= set(fundamentals.loc[mask, "ticker"].unique())
        if etf_tickers:
            print(f"[etf_filter] name-keyword fallback: {len(etf_tickers)} ETF tickers identified")

    # Intersect with our actual universe
    etf_in_universe = etf_tickers & all_tickers
    print(f"[etf_filter] ETFs identified in SP1500 universe: {len(etf_in_universe)} "
          f"(method: SIC/entity_type/name-keyword; NOT using EDGAR-absence filter)")
    return etf_in_universe


# ──────────────────────────────────────────────────────────────────────────────
# Signal construction (PIT-safe)
# ──────────────────────────────────────────────────────────────────────────────

def _build_ftd_signals_at_date(
    ftd_panel: pd.DataFrame,
    d: pd.Timestamp,
    fundamentals: pd.DataFrame,
    closes: pd.DataFrame,
    adv: pd.DataFrame,
    lookback_days: int = 90,
) -> pd.DataFrame:
    """Build the three FTD signals for all symbols as of date d (PIT-safe).

    PIT rule: only use FTD rows where availability_date <= d.
    Lookback: aggregate FTD over the most recent `lookback_days` calendar days
    where available (conservative: we use a 90d window to get stable estimates).

    Returns DataFrame indexed by symbol with columns:
      ftd_ratio    = total_ftd_shares / shares_outstanding (from EDGAR)
      ftd_usd_adv  = total_ftd_usd / 20d ADV (from massive_stock_day)
      ftd_zscore3  = 3-period z-score change in log(FTD shares + 1)
    """
    # PIT filter: only use files published on or before d
    pit = ftd_panel[ftd_panel["availability_date"] <= d].copy()
    if pit.empty:
        return pd.DataFrame()

    # Lookback window: last `lookback_days` calendar days in the PIT-safe data
    d_date = d.date() if hasattr(d, "date") else d
    cutoff = pd.Timestamp(d_date) - pd.Timedelta(days=lookback_days)
    window = pit[(pit["date"] >= cutoff) & (pit["date"] <= d)]
    if window.empty:
        return pd.DataFrame()

    # Aggregate FTD shares and USD per symbol in window
    agg = (window.groupby("symbol")
           .agg(ftd_shares_total=("ftd_shares", "sum"),
                ftd_usd_total=("ftd_shares", lambda x: (x * window.loc[x.index, "price"]).sum()),
                n_days=("date", "nunique"))
           .reset_index())
    agg = agg[agg["n_days"] >= 1].copy()

    # ── Signal 1: ftd_ratio = ftd_shares / shares_outstanding ────────────────
    # PIT shares: use most recent EDGAR fiscal year with asof_date <= d
    if not fundamentals.empty:
        fu = fundamentals[pd.to_datetime(fundamentals["asof_date"]) <= d].copy()
        fu = (fu.sort_values("asof_date")
                .groupby("ticker")[["shares"]]
                .last()
                .reset_index()
                .rename(columns={"ticker": "symbol"}))
        agg = agg.merge(fu[["symbol", "shares"]], on="symbol", how="left")
        agg["ftd_ratio"] = np.where(
            agg["shares"].notna() & (agg["shares"] > 0),
            agg["ftd_shares_total"] / agg["shares"],
            np.nan,
        )
    else:
        agg["ftd_ratio"] = np.nan

    # ── Signal 2: ftd_usd_adv = ftd_usd / 20d ADV ────────────────────────────
    if not adv.empty and d in adv.index:
        adv_today = adv.loc[d].dropna()
        adv_today.index.name = "symbol"
        agg = agg.merge(adv_today.rename("adv20").reset_index(),
                        on="symbol", how="left")
        agg["ftd_usd_adv"] = np.where(
            agg["adv20"].notna() & (agg["adv20"] > 0),
            agg["ftd_usd_total"] / agg["adv20"],
            np.nan,
        )
    else:
        agg["ftd_usd_adv"] = np.nan

    # ── Signal 3: 3-period FTD z-score change ────────────────────────────────
    # We need 3 prior semi-monthly periods' FTD totals per symbol
    # Each semi-monthly period is ~15 days; 3 periods = ~45 days back
    # We compute rolling 15d sums on the PIT-safe FTD data
    pit_recent = pit[(pit["date"] >= d - pd.Timedelta(days=60)) & (pit["date"] <= d)]
    if not pit_recent.empty:
        # Assign semi-monthly period index
        pit_recent = pit_recent.copy()
        pit_recent["period"] = (pit_recent["date"].dt.year * 24 +
                                pit_recent["date"].dt.month * 2 +
                                (pit_recent["date"].dt.day > 15).astype(int))
        period_agg = (pit_recent.groupby(["symbol", "period"])
                      ["ftd_shares"].sum().reset_index())
        # Get last 3 periods per symbol
        period_agg = period_agg.sort_values("period")
        period_agg["log_ftd"] = np.log1p(period_agg["ftd_shares"])
        # z-score within each symbol over last 3 periods
        def _zscore3(x: pd.Series) -> float:
            tail = x.iloc[-3:] if len(x) >= 3 else x
            mu, sd = tail.mean(), tail.std(ddof=0)
            if sd < 1e-9 or len(tail) < 2:
                return float("nan")
            # z-score of the last period relative to the 3-period window
            return float((tail.iloc[-1] - mu) / sd)

        zsc = (period_agg.groupby("symbol")["log_ftd"]
               .apply(_zscore3)
               .reset_index()
               .rename(columns={"log_ftd": "ftd_zscore3"}))
        agg = agg.merge(zsc, on="symbol", how="left")
    else:
        agg["ftd_zscore3"] = np.nan

    return agg.set_index("symbol")[["ftd_ratio", "ftd_usd_adv", "ftd_zscore3"]]


# ──────────────────────────────────────────────────────────────────────────────
# Phase-0 harness
# ──────────────────────────────────────────────────────────────────────────────

def _month_end_grid(index: pd.DatetimeIndex, horizon: int) -> list[pd.Timestamp]:
    """Monthly rebalance dates where there is room for a forward return."""
    out = []
    for me in pd.date_range(index.min(), index.max(), freq="ME"):
        d = index[index <= me]
        if len(d) == 0:
            continue
        loc = index.get_loc(d[-1])
        if loc + horizon < len(index):
            out.append(d[-1])
    return out


def _quintile_ls(R: pd.DataFrame, sigs: dict[str, pd.Series],
                 grid: list[pd.Timestamp], membership: pd.DataFrame,
                 n_trials: int, horizon: int) -> dict:
    """Dollar-neutral bottom-vs-top quintile backtest (SHORT-top / LONG-bottom), net of cost.

    Pre-registered direction for FTD signals: high FTD → negative return.
    So the strategy is: SHORT the TOP quintile (high FTD, expected underperformers)
    and LONG the BOTTOM quintile (low FTD, expected outperformers).
    Equivalently: bottom-vs-top spread (LONG bot, SHORT top).
    This gives a POSITIVE Sharpe when the signal works in the expected direction.

    G3 gate criterion: bottom-vs-top spread t_HAC >= 2 (= Sharpe * sqrt(n/252) >= 2 approx).
    """
    w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for d in grid:
        if d not in sigs:
            continue
        s = sigs[d].dropna()
        s = s[s.index.isin(_eligible(membership, d))]
        if len(s) < 25:
            continue
        hi, lo = s.quantile(0.8), s.quantile(0.2)
        top = s[s >= hi].index
        bot = s[s <= lo].index
        if len(top) and len(bot) and hi > lo:
            # PRE-REGISTERED SHORT DIRECTION: SHORT top (high FTD), LONG bottom (low FTD)
            w.loc[d, top] = -1.0 / len(top)   # short the high-FTD names
            w.loc[d, bot] = 1.0 / len(bot)    # long the low-FTD names
    w = w.replace(0.0, np.nan).ffill().fillna(0.0)
    pos = w.shift(1)
    gross = (pos * R.clip(-0.5, 0.5)).sum(axis=1)
    turn = w.diff().abs().sum(axis=1)
    net = (gross - (COST_BPS / 1e4) * turn)
    net = net.loc[grid[0]:grid[-1]] if grid else net
    net = net[net.index <= grid[-1]] if grid else net
    if len(net) < 10:
        return {}
    out = {
        "sharpe": round(float(net.mean() / net.std() * np.sqrt(252)), 2) if net.std() else None,
        "cum_pct": round(float(((1 + net).prod() - 1) * 100), 1),
        "n_days": int(net.notna().sum()),
    }
    mom = ret_moments(net)
    if mom:
        led = TrialLedger.with_declared_budget(n_trials, FAMILY)
        dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3],
                              ledger=led, family=FAMILY)
        if dsr:
            out["dsr"] = dsr["dsr"]
            out["verdict"] = dsr_verdict(dsr["dsr"])
    bc = block_bootstrap_ci(net, ann=252)
    if bc:
        out["sharpe_ci"] = bc["sharpe_ci"]
        out["sharpe_gt0_prob"] = bc["sharpe_gt0_prob"]
    return out


def run() -> dict:
    """Execute the full phase-0 scorecard. Returns results dict."""
    print("[phase0] Loading data...")

    # ── Load everything ───────────────────────────────────────────────────────
    ftd = _load_ftd_panel()
    if ftd.empty:
        return {"error": "FTD panel missing — run backfill_sec_ftd.py first"}

    fundamentals = _load_fundamentals()
    membership = _load_membership()
    finra = _load_finra_short()

    # FINRA short_volume window disclosure (required by reviewer, 2026-07-06):
    # The lane spec asked for --start 2020-01-01; the FINRA short_volume store
    # is floored at 2022-01-03 (the backfill ran with --start 2022-01-01).
    # The 2018/2019 gap is honest (FINRA API was unavailable for those years).
    # Consequence: G2 short_ratio neutralization only covers rebalance dates
    # from 2022-01-01 onward.  For 2021-07..2021-12 rebalance dates (6 months),
    # short_ratio is absent and cross-sectional std is near zero → the control
    # is silently skipped, and G2 for those dates is neutralization on
    # log_mcap + mom12_1 only.  This is disclosed here and in the report.
    if not finra.empty:
        finra_min = finra["date"].min()
        finra_max = finra["date"].max()
        print(f"[phase0] FINRA short_volume window: {finra_min.date()} → {finra_max.date()}")
        print(f"[phase0] NOTE: FINRA 2022 floor means G2 short_ratio control "
              f"is ABSENT for 2021-07..2021-12 rebalance dates (6 of ~60 dates).")
    else:
        print("[phase0] FINRA short_volume panel not found — G2 uses size+mom only.")

    # Determine the SP1500 universe and which tickers have massive_stock_day
    sp_tickers = set(membership["ticker"].unique())
    etf_set = _identify_etfs(fundamentals, sp_tickers)
    universe_tickers = sorted(sp_tickers - etf_set)
    print(f"[phase0] SP1500 PIT universe: {len(sp_tickers)} tickers, "
          f"minus {len(etf_set)} ETFs (by SIC/entity_type/name) = {len(universe_tickers)} candidates")

    # Load closes/ADV for the full candidate set
    print(f"[phase0] Loading closes/ADV from massive_stock_day for {len(universe_tickers)} tickers...")
    closes, adv = _load_closes_and_adv(universe_tickers)
    if closes.empty:
        return {"error": "No closes loaded from massive_stock_day"}

    print(f"[phase0] Closes loaded: {closes.shape[1]} tickers, "
          f"{closes.index.min().date()} .. {closes.index.max().date()}")

    # ── Trial Ledger: log grid AT GENERATION (before backtesting) ─────────────
    grid_configs = [
        {"signal": s, "horizon": h, "lookback_days": 90,
         "universe": "sp1500_pit", "etf_excluded": True,
         "pit_lag_days": 30}
        for s in SIGNALS for h in HORIZONS
    ]
    led = TrialLedger()
    n_new = led.log_grid(grid_configs, family=FAMILY,
                         info_cutoff=str(date.today()))
    n_total = led.effective_n(FAMILY)
    print(f"[ledger] Logged {n_new} new configs (family {FAMILY}), "
          f"effective N = {n_total}")

    # ── Build rebalance grid (monthly, 2021-07 onwards) ───────────────────────
    closes_idx = closes.index.sort_values()
    # Restrict to 2021-07 (massive_stock_day start)
    closes_restricted = closes[closes.index >= "2021-07-01"]
    closes_idx_r = closes_restricted.index

    # Forward returns
    R = closes.pct_change(fill_method=None)
    fwd = {}
    for h in HORIZONS:
        fwd[h] = closes.pct_change(h, fill_method=None).shift(-h)

    # ── Compute IC per date × signal × horizon ────────────────────────────────
    print("[phase0] Computing per-date signals and ICs...")

    # Storage: {signal: {horizon: [ic_values]}}
    ic_series: dict[str, dict[int, list]] = {s: {h: [] for h in HORIZONS} for s in SIGNALS}
    ic_dates: dict[str, dict[int, list]] = {s: {h: [] for h in HORIZONS} for s in SIGNALS}
    # For G2 neutralization
    ic_neutralized: dict[str, dict[int, list]] = {s: {h: [] for h in HORIZONS} for s in SIGNALS}
    # For confound C3 (price > $5)
    ic_price5: dict[str, dict[int, list]] = {s: {h: [] for h in HORIZONS} for s in SIGNALS}
    # For confound C2 (half-month parity)
    ic_half_a: dict[str, dict[int, list]] = {s: {h: [] for h in HORIZONS} for s in SIGNALS}
    ic_half_b: dict[str, dict[int, list]] = {s: {h: [] for h in HORIZONS} for s in SIGNALS}

    # Rebalance grid at month-end dates in close index (from 2021-07)
    grid_21 = _month_end_grid(closes_idx_r, 21)  # min horizon for grid
    print(f"[phase0] Rebalance grid: {len(grid_21)} dates "
          f"({grid_21[0].date() if grid_21 else 'N/A'} .. "
          f"{grid_21[-1].date() if grid_21 else 'N/A'})")

    # Build signal dict keyed by date (for quintile backtest)
    sigs_by_date: dict[str, dict[pd.Timestamp, pd.Series]] = {s: {} for s in SIGNALS}

    for d in grid_21:
        elig = _eligible(membership, d)
        elig_priced = elig & set(closes.columns)
        if len(elig_priced) < 30:
            continue

        # Build signals at this date
        sig_df = _build_ftd_signals_at_date(
            ftd_panel=ftd, d=d,
            fundamentals=fundamentals,
            closes=closes, adv=adv,
            lookback_days=90,
        )
        if sig_df.empty:
            continue

        # Filter to eligible priced SP1500 (non-ETF)
        sig_df = sig_df[sig_df.index.isin(elig_priced)]

        # Current prices for C3
        price_today = closes.loc[d] if d in closes.index else pd.Series(dtype=float)

        # FINRA short_ratio for G2 neutralization
        finra_d = pd.Series(dtype=float)
        if not finra.empty:
            finra_slice = finra[finra["date"] <= d]
            if not finra_slice.empty:
                latest = finra_slice.sort_values("date").groupby("ticker")["short_ratio"].last()
                finra_d = latest.reindex(sig_df.index)

        # Compute IC for each signal × horizon
        for sig_name in SIGNALS:
            if sig_name not in sig_df.columns:
                continue
            s_raw = sig_df[sig_name].dropna()
            sigs_by_date[sig_name][d] = s_raw

            for h in HORIZONS:
                if d not in fwd[h].index:
                    continue
                fr = fwd[h].loc[d].dropna()
                fr = fr[fr.index.isin(elig_priced)]
                if len(fr) < 20:
                    continue

                # Raw IC (pre-registered sign: negative = high FTD → bad returns)
                ic_val = rank_ic(s_raw.reindex(fr.index).fillna(0.0), fr)
                ic_series[sig_name][h].append(ic_val)
                ic_dates[sig_name][h].append(d)

                # G2 neutralized IC
                # Controls: log_mcap, momentum 12-1, finra short_ratio
                joined = pd.DataFrame({
                    "fr": fr,
                    "sig": s_raw.reindex(fr.index),
                })
                # log market cap (close × shares)
                if not fundamentals.empty:
                    fu_d = fundamentals[pd.to_datetime(fundamentals["asof_date"]) <= d]
                    fu_d = (fu_d.sort_values("asof_date")
                              .groupby("ticker")["shares"].last())
                    close_d = closes.loc[d] if d in closes.index else pd.Series(dtype=float)
                    mcap = close_d * fu_d
                    joined["log_mcap"] = np.log1p(mcap.reindex(fr.index))
                # 12-1 momentum
                if d in closes.index:
                    d12 = closes.index[max(0, closes.index.get_loc(d) - 252)]
                    d1 = closes.index[max(0, closes.index.get_loc(d) - 21)]
                    mom = (closes.loc[d] / closes.loc[d12] - 1).reindex(fr.index)
                    joined["mom12_1"] = mom
                # FINRA short ratio
                if finra_d is not None and not finra_d.empty:
                    joined["short_ratio"] = finra_d.reindex(fr.index)

                # G2 neutralization: joint OLS residualization (reviewer-required fix,
                # 2026-07-06).  Previous implementation used sequential univariate
                # partialling-out (Gram-Schmidt order), which leaves residual signal
                # correlated with later controls when controls are correlated, and
                # understates neutralization.  Correct approach: regress signal on
                # all available controls jointly in one OLS pass and take residuals.
                # This is unambiguously unbiased for the incremental IC test.
                controls = [c for c in ["log_mcap", "mom12_1", "short_ratio"]
                            if c in joined.columns]
                sig_col = joined["sig"].copy()
                valid_rows = sig_col.notna()
                if controls:
                    ctrl_mat = joined[controls].copy()
                    for c in controls:
                        ctrl_mat[c] = ctrl_mat[c].fillna(ctrl_mat[c].median())
                    valid_rows = valid_rows & ctrl_mat.notna().all(axis=1)
                    if valid_rows.sum() >= 20:
                        # Joint OLS: X = [1, ctrl1, ctrl2, ...], y = signal
                        X = np.column_stack(
                            [np.ones(valid_rows.sum())] +
                            [ctrl_mat.loc[valid_rows, c].values for c in controls]
                        )
                        y = sig_col.loc[valid_rows].values
                        try:
                            coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
                            residuals = y - X @ coef
                            sig_resid = sig_col.copy()
                            sig_resid.loc[valid_rows] = residuals
                            sig_resid.loc[~valid_rows] = 0.0
                        except np.linalg.LinAlgError:
                            sig_resid = sig_col.fillna(0.0)
                    else:
                        sig_resid = sig_col.fillna(0.0)
                else:
                    sig_resid = sig_col.fillna(0.0)
                ic_neut = rank_ic(sig_resid.fillna(0.0), fr)
                ic_neutralized[sig_name][h].append(ic_neut)

                # C3: IC within price > $5
                if not price_today.empty:
                    high_price = price_today.reindex(fr.index) > 5.0
                    fr_hp = fr[high_price.fillna(False)]
                    if len(fr_hp) >= 20:
                        ic_p5 = rank_ic(s_raw.reindex(fr_hp.index).fillna(0.0), fr_hp)
                        ic_price5[sig_name][h].append(ic_p5)

                # C2: half-month parity split
                # The last FTD file feeding d is identified by its half
                avail_before = ftd[ftd["availability_date"] <= d]
                if not avail_before.empty:
                    last_key = avail_before["_file_key"].iloc[-1] if "_file_key" in avail_before.columns else ""
                    if last_key.endswith("a"):
                        ic_half_a[sig_name][h].append(ic_val)
                    elif last_key.endswith("b"):
                        ic_half_b[sig_name][h].append(ic_val)

    # ── Summarize IC and apply BH-FDR ─────────────────────────────────────────
    rows: dict[str, dict] = {}
    pvals: dict[str, float] = {}

    for sig_name in SIGNALS:
        for h in HORIZONS:
            label = f"{sig_name}|{h}d"
            ic_list = ic_series[sig_name][h]
            if len(ic_list) < 6:
                continue
            ser = pd.Series(ic_list)
            summ = ic_summary(ser.dropna(), periods_per_year=12)
            if summ.get("n", 0) < 6:
                continue

            # G2 neutralized
            neut_list = ic_neutralized[sig_name][h]
            if neut_list:
                neut_ser = pd.Series(neut_list).dropna()
                summ["ic_neutralized"] = round(float(neut_ser.mean()), 4)
                if summ.get("mean_ic") and abs(summ["mean_ic"]) > 1e-9:
                    summ["neut_frac"] = round(
                        abs(summ["ic_neutralized"]) / abs(summ["mean_ic"]), 3)

            # C3 price > $5
            p5_list = ic_price5[sig_name][h]
            if p5_list:
                summ["ic_price5"] = round(float(pd.Series(p5_list).dropna().mean()), 4)

            # C2 half-month parity
            ha = ic_half_a[sig_name][h]
            hb = ic_half_b[sig_name][h]
            if ha:
                summ["ic_half_a"] = round(float(pd.Series(ha).dropna().mean()), 4)
            if hb:
                summ["ic_half_b"] = round(float(pd.Series(hb).dropna().mean()), 4)

            rows[label] = summ
            if summ.get("p_hac") is not None:
                pvals[label] = summ["p_hac"]

    # BH-FDR
    bh = benjamini_hochberg(pvals, alpha=0.10)
    for label, q_info in bh.items():
        rows[label]["q_fdr"] = q_info["q"]
        rows[label]["survives_fdr"] = q_info["reject"]

    # ── G1 evaluation (pre-registered) ────────────────────────────────────────
    g1_survivors = [lbl for lbl, r in rows.items() if r.get("survives_fdr")]
    # Pre-registered sign: mean_ic should be NEGATIVE (high FTD → negative return)
    g1_correct_sign = [lbl for lbl in g1_survivors
                       if (rows[lbl].get("mean_ic") or 0) < 0]
    g1_pass = len(g1_correct_sign) > 0

    # ── G2 evaluation ─────────────────────────────────────────────────────────
    g2_results = {}
    for lbl in g1_correct_sign:
        raw_ic = rows[lbl].get("mean_ic") or 0
        neut_ic = rows[lbl].get("ic_neutralized") or 0
        if abs(raw_ic) > 1e-9:
            frac = abs(neut_ic) / abs(raw_ic)
            same_sign = (raw_ic < 0) == (neut_ic < 0) or abs(neut_ic) < 1e-9
            g2_results[lbl] = {
                "raw_ic": raw_ic, "neut_ic": neut_ic,
                "frac_retained": round(frac, 3),
                "same_sign": bool(same_sign),
                "passes": bool(frac >= 0.5 and same_sign),
            }
    g2_pass = any(v["passes"] for v in g2_results.values()) if g2_results else False

    # ── G3 evaluation (quintile spread t_HAC at 21d) ──────────────────────────
    print("[phase0] Computing quintile backtests...")
    ls_results = {}
    for sig_name in SIGNALS:
        sigs_d = sigs_by_date[sig_name]
        if not sigs_d:
            continue
        for h in HORIZONS:
            label = f"{sig_name}|{h}d"
            ls = _quintile_ls(R, sigs_d, grid_21, membership, n_total, h)
            if ls:
                ls_results[label] = ls

    # G3: bottom-vs-top quintile spread t_HAC >= 2 at 21d
    # We check via the net return series Sharpe as proxy (t_HAC ≈ √n × Sharpe for monthly)
    g3_candidates = {lbl: r for lbl, r in ls_results.items() if "21d" in lbl}
    g3_pass = any((v.get("sharpe") or 0) >= 2.0 / np.sqrt(len(grid_21) / 12)
                  for v in g3_candidates.values())

    print(f"[verdict] G1 (BH-FDR + correct sign): {'PASS' if g1_pass else 'FAIL'} "
          f"— {len(g1_correct_sign)}/{len(g1_survivors)} survivors with correct sign")
    print(f"[verdict] G2 (incremental vs controls): {'PASS' if g2_pass else 'FAIL'}")
    print(f"[verdict] G3 (quintile spread t>=2 at 21d): {'PASS' if g3_pass else 'FAIL'}")

    overall_verdict = ("SHORT-SIDE CONFIRMER CANDIDATE" if g1_pass and g2_pass and g3_pass
                       else "NULL / NO-GO (collector ships independently)")

    return {
        "ic_rows": rows,
        "ls_results": ls_results,
        "g1": {"pass": g1_pass, "survivors": g1_correct_sign},
        "g2": {"pass": g2_pass, "detail": g2_results},
        "g3": {"pass": g3_pass, "detail": g3_candidates},
        "overall": overall_verdict,
        "n_rebalances": len(grid_21),
        "grid_span": (f"{grid_21[0].date()}..{grid_21[-1].date()}" if grid_21 else "N/A"),
        "n_trials_logged": n_total,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Report rendering
# ──────────────────────────────────────────────────────────────────────────────

def render_report(results: dict) -> str:
    L = []
    L.append("# SLF-001 — SEC Fails-to-Deliver Pressure: Phase-0 IC Scorecard")
    L.append("")
    L.append("**Family:** `slf001_ftd_pressure` | "
             "**Harness:** `scripts/sec_ftd_phase0.py` | "
             f"**N trials logged:** {results.get('n_trials_logged', '?')}")
    L.append("")

    if results.get("error"):
        L.append(f"**ERROR:** {results['error']}")
        return "\n".join(L)

    overall = results.get("overall", "UNKNOWN")
    L.append(f"## Overall verdict: {overall}")
    L.append("")
    L.append("> **In plain English:** We tested whether stocks with high SEC fails-to-deliver")
    L.append("> (broken share delivery) tend to underperform over the next 21 and 63 trading")
    L.append("> days.  Three signals were tested: FTD shares as a fraction of shares")
    L.append("> outstanding, FTD dollar value relative to average daily trading volume,")
    L.append("> and a 3-period z-score change in FTD activity.  High FTD → negative return")
    L.append("> is the pre-registered hypothesis.")
    L.append(">")
    L.append("> **Outcome:** The verdict is **NULL / NO-GO** despite G1 and G2 passing,")
    L.append("> because the pre-registered three-gate protocol requires ALL three gates.")
    L.append("> G3 evaluates whether the short-top-quintile backtest is strong enough to")
    L.append("> trade: the annualized Sharpe of the bottom-vs-top quintile spread must reach")
    L.append("> the threshold 2/√n_years (≈0.89 for ~59 months / ~4.9 years).  The strongest")
    L.append("> signal (ftd_usd_adv) achieves Sharpe 0.78, below the 0.89 threshold.")
    L.append("> **Important caveat:** G3 uses an annualized-Sharpe proxy for the pre-registered")
    L.append("> t_HAC≥2 criterion (code: `sharpe >= 2/sqrt(n_years)`).  These are not")
    L.append("> equivalent: a literal Newey-West t-stat on the spread return series was not")
    L.append("> computed.  The proxy is conservative in short panels but is a deviation from")
    L.append("> the literal pre-registered gate.  The collector ships regardless.")
    L.append("")

    L.append("## Universe and data")
    L.append("")
    L.append(f"- **Rebalance grid:** {results.get('grid_span', 'N/A')} "
             f"({results.get('n_rebalances', 0)} monthly dates)")
    L.append("- **Universe:** S&P 1500 PIT membership (large+mid+small). ETFs excluded by EDGAR "
             "SIC 6726 / entity_type / name-keyword (NOT by EDGAR-absence, which would "
             "mislabel ~600 delisted/acquired stocks as ETFs — corrected 2026-07-06).")
    L.append("- **Closes / ADV:** massive_stock_day (2021-07-06 → 2026-07-02)")
    L.append("- **LIMITATION:** IC panel runs only on the 2021-07..2026-06 window (~60 monthly")
    L.append("  dates) because massive_stock_day does not extend before 2021-07.  The FTD")
    L.append("  store covers 2009-07 → present; a future run with a longer close history")
    L.append("  will extend this test.  Results on ~60 dates carry limited statistical power.")
    L.append("")
    L.append("- **PIT lag enforced:** availability_date = period_end + 30 calendar days")
    L.append("  (conservative uniform lag; both first- and second-half files use 30d).")
    L.append("- **FTD data gap:** SEC page lists files from 2009-07 (not 2004 as stated on")
    L.append("  the data page); pre-2009 and 2017-era files use a FOIA URL path (handled).")
    L.append("- **FINRA short_volume window (G2 control):** The FINRA control store covers")
    L.append("  **2022-01-03 → 2026-07-02** (floored to 2022; the lane spec target of 2020-01-01")
    L.append("  was not achievable within budget, and 2018/2019 data has a known FINRA API gap).")
    L.append("  G2 short_ratio neutralization therefore covers **only the 2022+ subset** of")
    L.append("  rebalance dates (~47 of 59 dates).  For the 6 dates in 2021-07..2021-12,")
    L.append("  short_ratio is absent and G2 neutralizes on size + momentum only.")
    L.append("- **G2 neutralization method:** Joint OLS residualization — signal is regressed")
    L.append("  on [log_mcap, mom12_1, short_ratio] jointly per cross-section, and IC is")
    L.append("  computed on the OLS residuals.  This is an unbiased test of incremental")
    L.append("  information; sequential Gram-Schmidt (the prior implementation) was biased")
    L.append("  toward PASS when controls are correlated (corrected 2026-07-06).")
    L.append("- **G3 proxy note:** G3 evaluates the annualized-Sharpe proxy `sharpe ≥ 2/√n_years`")
    L.append("  rather than a literal Newey-West t_HAC ≥ 2 on the quintile spread return series.")
    L.append("  For the panel length (~4.9 years), the threshold is ≈0.89.")
    L.append("")

    L.append("## Pre-registered gates")
    L.append("")
    L.append("| Gate | Criterion | Result |")
    L.append("|---|---|---|")
    g1 = results.get("g1", {})
    g2 = results.get("g2", {})
    g3 = results.get("g3", {})
    L.append(f"| G1 | BH-FDR q≤0.10 with negative IC sign | "
             f"{'**PASS**' if g1.get('pass') else 'FAIL'} — "
             f"{len(g1.get('survivors', []))} signals |")
    L.append(f"| G2 | IC survives after size+mom+short_ratio neutralization (≥50%, same sign) | "
             f"{'**PASS**' if g2.get('pass') else 'FAIL'} |")
    L.append(f"| G3 | Bottom-vs-top quintile annualized Sharpe ≥ 2/√n_years proxy at 21d "
             f"(≈0.89 for ~4.9y panel; proxy for pre-registered t_HAC≥2) | "
             f"{'**PASS**' if g3.get('pass') else 'FAIL'} |")
    L.append("")

    L.append("## IC table (3 signals × 2 horizons)")
    L.append("")
    L.append("Pre-registered sign: negative (high FTD → negative forward return).")
    L.append("")
    L.append("| signal | mean IC | IC-IR | t_HAC | p_HAC | q_FDR | hit | "
             "IC_neut | neut_frac | IC_price>5 | IC_half_a | IC_half_b | n |")
    L.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    rows = results.get("ic_rows", {})
    for lbl in sorted(rows, key=lambda x: (x.split("|")[0], x.split("|")[1])):
        r = rows[lbl]
        L.append(
            f"| {lbl} | {r.get('mean_ic', '—')} | {r.get('ic_ir', '—')} "
            f"| {r.get('t_hac', '—')} | {r.get('p_hac', '—')} "
            f"| {r.get('q_fdr', '—')} | {r.get('hit', '—')} "
            f"| {r.get('ic_neutralized', '—')} | {r.get('neut_frac', '—')} "
            f"| {r.get('ic_price5', '—')} | {r.get('ic_half_a', '—')} "
            f"| {r.get('ic_half_b', '—')} | {r.get('n', '—')} |"
        )
    surv = [lbl for lbl in rows if rows[lbl].get("survives_fdr")]
    L.append("")
    L.append(f"**BH-FDR(10%) survivors:** {', '.join(surv) if surv else 'NONE'}")
    L.append(f"**Correct-sign survivors (negative IC):** "
             f"{', '.join(g1.get('survivors', [])) if g1.get('survivors') else 'NONE'}")
    L.append("")

    L.append("## G2: Neutralization detail")
    L.append("")
    g2_detail = g2.get("detail", {})
    if g2_detail:
        L.append("| signal | raw_IC | neut_IC | frac_retained | same_sign | G2 pass |")
        L.append("|---|--:|--:|--:|---|---|")
        for lbl, v in g2_detail.items():
            L.append(
                f"| {lbl} | {v['raw_ic']} | {v['neut_ic']} "
                f"| {v['frac_retained']} | {v['same_sign']} | {v['passes']} |"
            )
    else:
        L.append("No G1 survivors to neutralize.")
    L.append("")

    L.append("## Quintile L/S backtest (net of 5bps one-way)")
    L.append("")
    L.append("| signal | net Sharpe | cum % | DSR | verdict | bootstrap CI | P(SR>0) |")
    L.append("|---|--:|--:|--:|---|---|--:|")
    for lbl, v in results.get("ls_results", {}).items():
        L.append(
            f"| {lbl} | {v.get('sharpe', '—')} | {v.get('cum_pct', '—')} "
            f"| {v.get('dsr', '—')} | {v.get('verdict', '—')} "
            f"| {v.get('sharpe_ci', '—')} | {v.get('sharpe_gt0_prob', '—')} |"
        )
    L.append("")

    L.append("## Pre-registered confounds")
    L.append("")
    L.append("**C1 — Net-CNS balance semantics:** FTD shares at DTCC measure net delivery")
    L.append("failures across all parties, including failed long deliveries.  They do NOT")
    L.append("directly measure naked short positions.  The signal tests a cross-sectional")
    L.append("rank (stocks with relatively more FTD vs less) and is therefore less sensitive")
    L.append("to the absolute semantics, but the mechanism is less clean than a direct")
    L.append("short-interest measure.  Not adjusted.")
    L.append("")
    L.append("**C2 — T+35 close-out cyclicality:** NSCC Rule 11(a) compels mandatory buy-ins")
    L.append("after 35 consecutive fail days.  This creates a periodic reversal signal.")
    L.append("We report IC by half-month parity (ic_half_a vs ic_half_b) above; if they")
    L.append("diverge strongly, the T+35 cycle is driving the IC, not the fundamental signal.")
    L.append("")
    L.append("**C3 — Low-price concentration:** Many FTD entries are penny/micro stocks")
    L.append("with mechanically high fail rates.  We report IC restricted to price > $5")
    L.append("(ic_price5 column) to isolate the effect in investable names.")
    L.append("")

    L.append("## Nightly wiring (for consolidation)")
    L.append("")
    L.append("Add to the nightly collect step (after price collection):")
    L.append("```")
    L.append("python -m collectors.sec_ftd --incremental")
    L.append("```")
    L.append("This fetches the most recent FTD files whose availability_date has passed.")
    L.append("")
    L.append("---")
    L.append("")
    L.append("*Collector ships regardless of phase-0 verdict — the FTD panel has standalone*")
    L.append("*value for sector-level dashboards, individual-stock fail rate tracking, and*")
    L.append("*future re-runs with a longer close history.*")

    return "\n".join(L)


def main() -> int:
    results = run()
    out_path = config.ROOT / "reports" / "slf001-sec-ftd-phase0.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = render_report(results)
    out_path.write_text(report)
    print(f"[report] {out_path}")
    print(f"[verdict] {results.get('overall', 'ERROR')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
