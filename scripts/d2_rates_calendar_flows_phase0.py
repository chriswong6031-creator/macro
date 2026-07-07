"""Phase-0: d2_rates_calendar_flows — Treasury calendar timing family.

FAMILY: d2_rates_calendar_flows  (one LG-US-RATES-CAL slot, one trial budget)
Pre-registered per: research/SIGNAL_LAB_FRONTIER_DAY2_FABLE_ADJUDICATION_2026-07-06.md
item 1 — authorised at adjudication 2026-07-06.

THREE VARIANTS (one family, one BH correction):
  V1  auction-cycle concession/rebound (Lou-Yan-Zhang)
      Data: data/treasury_auctions/auctions.parquet (10y + 30y coupon auctions, 2016+)
            data/yahoo/TLT.parquet
      Construct: TLT return in pre-auction concession window (t-3..t0) and
                 post-auction rebound window (t0..t+3); entry conditional on
                 measured concession (pre-window TLT return < 0).
      Direction per prereg: concession negative, rebound positive → long-TLT
                 post-auction conditional on observed concession.

  V2  quarter-end pension rebalance
      Data: data/yahoo/SPY.parquet, data/yahoo/TLT.parquet
      Construct: cumulative SPY-minus-TLT gap from quarter-start to t-7 business
                 days before quarter-end → sign predicts final-week TLT-vs-SPY
                 relative drift.
      Direction per prereg: large equity outperformance → bond-buying rebalance →
                 TLT relative strength in final week.

  V3  month-end extension day
      Data: data/yahoo/TLT.parquet, data/yahoo/IEF.parquet
      Construct: TLT/IEF return on last business day of month vs same-month
                 average day.
      Direction per prereg: positive (index extension buying on last day).

GATES (frozen before results, applied across the family):
  G1  BH FDR q <= 0.10 across all family cells (primary BH screen)
  G2  split-half same-sign per variant (each half independently signed correctly)
  G3  each variant vs its unconditional same-calendar baseline
  G4  |t_HAC| >= 2 with date-clustering (Newey-West, collapse one obs per event-date)

STATS LAW (CLAUDE.md §4): collapse to one obs per event-date, then Newey-West
on the date-indexed series. All thresholds trailing/expanding PIT — no full-sample
quantiles used here (calendar windows are fixed by the mechanism, not by data).

AMENDMENTS REGISTERED BEFORE COMPUTING (gaps in written prereg):
  AM-1: For V1, 10y and 30y auctions tested separately and pooled; all three
        cells enter BH. Pre-registered choice: pooled cell is the headline
        (most events; same mechanism); tenor-split cells are family members.
  AM-2: For V1, "measured concession" = pre-window TLT cum-return < 0 (i.e.
        the 3 trading days before auction show TLT selling). Threshold = 0
        (sign-based, not quantile) — pre-registered to avoid full-sample quantile
        look-ahead.
  AM-3: For V2, "final week" = last 5 business days of quarter; gap measured
        from quarter-start. Quarter boundaries = calendar-quarter-end per
        pd.offsets.BQuarterEnd(). t-7 = 7 business days before quarter-end.
  AM-4: For V3, last business day identified as the last trading day in each
        calendar month present in the TLT price series. Baseline = mean of all
        other trading days in the same month.
  AM-5: Newey-West lag = min(4, sqrt(n)) per Andrews rule of thumb applied to
        the collapsed date-level series length.

PIT ASSUMPTIONS:
  - Auction dates: known in advance (Treasury pre-announces); no look-ahead risk
    for the post-auction window (t0..t+3 = after the event date).
  - Pre-auction window (t-3..t0): returns before the auction are observable;
    using them to condition the post-auction trade is causal.
  - Yahoo prices: daily close; no intraday assumption needed.
  - Quarter/month-end identifiers: purely calendar-derived, no future data.

Run:
    python -m scripts.d2_rates_calendar_flows_phase0
Writes: reports/d2-rates-calendar-flows-phase0.md
        logs to engine/trial_ledger.py (family=d2_rates_calendar_flows)
"""
from __future__ import annotations

import sys
import math
import json
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.validation import newey_west_tstat, benjamini_hochberg  # noqa: E402
from engine.trial_ledger import TrialLedger                         # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAMILY = "d2_rates_calendar_flows"
ANN = 252

# ---------------------------------------------------------------------------
# Newey-West lag by Andrews rule of thumb on collapsed series
# ---------------------------------------------------------------------------

def _nw_lags(n: int) -> int:
    return max(2, min(4, int(math.sqrt(n))))


# ---------------------------------------------------------------------------
# Data loading + price-store verification
# ---------------------------------------------------------------------------

def load_prices() -> dict[str, pd.Series]:
    """Load TLT, IEF, SPY from yahoo store. Verify nested-parquet layout."""
    store = ROOT / "data" / "yahoo"
    out = {}
    for ticker in ("TLT", "IEF", "SPY"):
        path = store / f"{ticker}.parquet"
        df = pd.read_parquet(path)
        # price column: prefer 'close', fallback 'close_price'
        col = "close" if "close" in df.columns else "close_price"
        s = df[col].sort_index().dropna()
        s.index = pd.to_datetime(s.index)
        out[ticker] = s
        print(f"  [{ticker}] {len(s)} rows, {s.index.min().date()} .. {s.index.max().date()}")
    return out


def load_auctions() -> pd.DataFrame:
    path = ROOT / "data" / "treasury_auctions" / "auctions.parquet"
    df = pd.read_parquet(path)
    df["auction_date"] = pd.to_datetime(df["auction_date"])
    # Filter to 10y and 30y coupon auctions (tenor_years 9.5-10.5 and 29-30.5)
    is_10y = df["tenor_years"].between(9.5, 10.5)
    is_30y = df["tenor_years"].between(29.0, 30.5)
    df["tenor_bucket"] = np.where(is_10y, "10y", np.where(is_30y, "30y", "other"))
    df = df[df["tenor_bucket"].isin(["10y", "30y"])].copy()
    df = df.sort_values("auction_date").reset_index(drop=True)
    print(f"  [auctions] {len(df)} rows (10y: {(df['tenor_bucket']=='10y').sum()}, "
          f"30y: {(df['tenor_bucket']=='30y').sum()}), "
          f"{df['auction_date'].min().date()} .. {df['auction_date'].max().date()}")
    return df


# ---------------------------------------------------------------------------
# V1: Auction-cycle concession / rebound
# ---------------------------------------------------------------------------

def _trading_offset(close: pd.Series, ref_date: pd.Timestamp, n: int) -> pd.Timestamp | None:
    """Return the trading date that is n business-days offset from ref_date."""
    idx = close.index
    pos = idx.searchsorted(ref_date)
    target = pos + n
    if target < 0 or target >= len(idx):
        return None
    return idx[target]


def v1_auction_cycle(prices: dict[str, pd.Series], auctions: pd.DataFrame) -> dict:
    """
    For each 10y/30y coupon auction:
      - pre-window:  TLT cum-return from t-3 to t0 (day before auction close)
      - post-window: TLT cum-return from t0 to t+3
      - conditional: include post-window only if pre-window < 0 (concession observed)
    Returns stats dict per cell.
    """
    tlt = prices["TLT"]
    rows = []
    for _, row in auctions.iterrows():
        t0_date = row["auction_date"]
        tenor = row["tenor_bucket"]

        # Find t0: last trading day on or before auction_date
        pos0 = tlt.index.searchsorted(t0_date, side="right") - 1
        if pos0 < 4 or pos0 + 3 >= len(tlt):
            continue
        t0 = tlt.index[pos0]

        # pre-window: 3 days ending at t0 (close at t0 vs close at t-3)
        t_minus3 = tlt.index[pos0 - 3]
        pre_ret = float(tlt.iloc[pos0] / tlt.iloc[pos0 - 3] - 1)

        # post-window: 3 days from t0 (close at t+3 vs close at t0)
        t_plus3 = tlt.index[pos0 + 3]
        post_ret = float(tlt.iloc[pos0 + 3] / tlt.iloc[pos0] - 1)

        rows.append({
            "auction_date": t0_date,
            "event_date": t0,
            "tenor": tenor,
            "pre_ret": pre_ret,
            "post_ret": post_ret,
            "concession_observed": pre_ret < 0,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return {"error": "no auction events found"}

    # Collapse to one obs per event_date (drop duplicate dates if any)
    df = df.drop_duplicates("event_date").set_index("event_date").sort_index()

    results = {}
    # Cells: pooled (all), 10y only, 30y only — conditional on concession
    cells = {
        "v1_pooled_conditional": df[df["concession_observed"]]["post_ret"],
        "v1_10y_conditional":    df[(df["concession_observed"]) & (df["tenor"] == "10y")]["post_ret"],
        "v1_30y_conditional":    df[(df["concession_observed"]) & (df["tenor"] == "30y")]["post_ret"],
        "v1_pooled_unconditional": df["post_ret"],  # baseline for gate G3
    }
    # Also pre-window stats for sanity (should be negative per Lou-Yan-Zhang)
    pre_nw = newey_west_tstat(df["pre_ret"].values, lags=_nw_lags(len(df)))

    results["pre_window_mean"] = pre_nw["mean"]
    results["pre_window_t_hac"] = pre_nw["t"]
    results["pre_window_n"] = pre_nw["n"]
    results["pre_window_direction_correct"] = (
        pre_nw["mean"] is not None and pre_nw["mean"] < 0
    )

    for cell_name, series in cells.items():
        series = series.dropna()
        n = len(series)
        if n < 5:
            results[cell_name] = {"n": n, "mean": None, "t_hac": None, "p_hac": None}
            continue
        nw = newey_west_tstat(series.values, lags=_nw_lags(n))
        results[cell_name] = {
            "n": n,
            "mean_pct": round(100 * nw["mean"], 3) if nw["mean"] else None,
            "t_hac": nw["t"],
            "p_hac": nw["p"],
            "sign_correct": (nw["mean"] is not None and nw["mean"] > 0),
        }

    results["n_auctions_total"] = len(df)
    results["n_with_concession"] = int(df["concession_observed"].sum())
    return results


# ---------------------------------------------------------------------------
# V2: Quarter-end pension rebalance
# ---------------------------------------------------------------------------

def v2_quarter_end_rebalance(prices: dict[str, pd.Series]) -> dict:
    """
    For each quarter-end:
      - gap: cumulative SPY-minus-TLT return from quarter-start to t-7 bus days before QE
      - outcome: TLT-minus-SPY return in the final 5 bus days before quarter-end
      - direction: large positive gap (equity outperformed) -> positive TLT-vs-SPY outcome
    Returns NW stats for (a) conditional on gap>0, (b) unconditional, (c) gap-signed.
    """
    spy = prices["SPY"]
    tlt = prices["TLT"]

    # Common trading days
    common = spy.index.intersection(tlt.index)
    spy_c = spy.reindex(common)
    tlt_c = tlt.reindex(common)

    # Quarter-end dates on the common calendar
    qe_dates = pd.date_range(common.min(), common.max(), freq="BQE")

    rows = []
    for qe in qe_dates:
        # find actual trading day at or just before quarter-end
        pos_qe = common.searchsorted(qe, side="right") - 1
        if pos_qe < 60 or pos_qe < 7:
            continue
        # t-7 (7 bus days before quarter-end)
        pos_t7 = pos_qe - 7
        # quarter-start: first trading day of the quarter (pos_qe - ~63 days; use 60)
        pos_qs = max(0, pos_qe - 63)
        # find true quarter-start (first bus day of the quarter)
        qe_ts = common[pos_qe]
        quarter_start = qe_ts - pd.offsets.BQuarterBegin(startingMonth=1)
        # find first trading day >= quarter_start
        pos_qs_true = common.searchsorted(quarter_start, side="left")
        if pos_qs_true >= pos_t7:
            continue

        # Gap: spy cum - tlt cum from quarter-start to t-7
        spy_gap = float(spy_c.iloc[pos_t7] / spy_c.iloc[pos_qs_true] - 1)
        tlt_gap_for_calc = float(tlt_c.iloc[pos_t7] / tlt_c.iloc[pos_qs_true] - 1)
        gap = spy_gap - tlt_gap_for_calc  # equity outperformance vs bonds

        # Outcome: TLT vs SPY in final 5 bus days (pos_t7 -> pos_qe)
        pos_final_start = pos_qe - 5
        if pos_final_start < 0:
            continue
        tlt_final = float(tlt_c.iloc[pos_qe] / tlt_c.iloc[pos_final_start] - 1)
        spy_final = float(spy_c.iloc[pos_qe] / spy_c.iloc[pos_final_start] - 1)
        outcome = tlt_final - spy_final  # TLT relative strength in final week

        rows.append({
            "qe_date": common[pos_qe],
            "gap_equity_outperf": gap,
            "outcome_tlt_rel": outcome,
            "gap_positive": gap > 0,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return {"error": "no quarter-end events"}

    # One obs per event date (already unique by construction)
    df = df.set_index("qe_date").sort_index()

    results = {}
    cells = {
        "v2_conditional_gap_pos": df[df["gap_positive"]]["outcome_tlt_rel"],
        "v2_unconditional": df["outcome_tlt_rel"],  # baseline for G3
    }
    # Gap-signed: outcome * sign(gap)
    df["signed_outcome"] = df["outcome_tlt_rel"] * np.sign(df["gap_equity_outperf"])
    cells["v2_gap_signed"] = df["signed_outcome"]

    for cell_name, series in cells.items():
        series = series.dropna()
        n = len(series)
        if n < 5:
            results[cell_name] = {"n": n, "mean": None, "t_hac": None, "p_hac": None}
            continue
        nw = newey_west_tstat(series.values, lags=_nw_lags(n))
        results[cell_name] = {
            "n": n,
            "mean_pct": round(100 * nw["mean"], 3) if nw["mean"] else None,
            "t_hac": nw["t"],
            "p_hac": nw["p"],
            "sign_correct": (nw["mean"] is not None and nw["mean"] > 0),
        }

    results["n_quarters"] = len(df)
    results["pct_gap_positive"] = round(100 * df["gap_positive"].mean(), 1)
    return results


# ---------------------------------------------------------------------------
# V3: Month-end extension day
# ---------------------------------------------------------------------------

def v3_month_end_extension(prices: dict[str, pd.Series]) -> dict:
    """
    For each calendar month in TLT history:
      - last_day_ret: TLT (and IEF) return on the last trading day of month
      - avg_other_ret: mean return on all OTHER trading days of the same month
      - outcome: last_day_ret (direction: positive per prereg)
      - baseline: avg_other_ret (for G3)
    """
    tlt = prices["TLT"]
    ief = prices["IEF"]

    tlt_ret = tlt.pct_change().dropna()
    ief_ret = ief.pct_change().dropna()

    common = tlt_ret.index.intersection(ief_ret.index)
    tlt_r = tlt_ret.reindex(common)
    ief_r = ief_ret.reindex(common)

    # Identify last trading day per calendar month
    month_groups = pd.Series(common).groupby(pd.to_datetime(common).to_period("M"))

    rows_tlt = []
    rows_ief = []
    for period, group in month_groups:
        dates = sorted(group.values)
        if len(dates) < 5:  # skip partial months
            continue
        last_day = pd.Timestamp(dates[-1])
        other_days = [pd.Timestamp(d) for d in dates[:-1]]

        tlt_last = float(tlt_r.loc[last_day])
        ief_last = float(ief_r.loc[last_day])
        tlt_avg_other = float(tlt_r.loc[other_days].mean())
        ief_avg_other = float(ief_r.loc[other_days].mean())

        rows_tlt.append({
            "event_date": last_day,
            "last_day_ret": tlt_last,
            "avg_other_ret": tlt_avg_other,
            "excess_over_avg": tlt_last - tlt_avg_other,
        })
        rows_ief.append({
            "event_date": last_day,
            "last_day_ret": ief_last,
            "avg_other_ret": ief_avg_other,
            "excess_over_avg": ief_last - ief_avg_other,
        })

    results = {}
    for label, rows in [("tlt", rows_tlt), ("ief", rows_ief)]:
        df = pd.DataFrame(rows).set_index("event_date").sort_index()
        n = len(df)

        # Primary: last-day return absolute level
        nw_last = newey_west_tstat(df["last_day_ret"].values, lags=_nw_lags(n))
        # Baseline: avg other day return
        nw_base = newey_west_tstat(df["avg_other_ret"].values, lags=_nw_lags(n))
        # Excess over baseline
        nw_exc = newey_west_tstat(df["excess_over_avg"].values, lags=_nw_lags(n))

        results[f"v3_{label}_last_day"] = {
            "n": n,
            "mean_pct": round(100 * nw_last["mean"], 4) if nw_last["mean"] else None,
            "t_hac": nw_last["t"],
            "p_hac": nw_last["p"],
            "sign_correct": (nw_last["mean"] is not None and nw_last["mean"] > 0),
        }
        results[f"v3_{label}_avg_other"] = {
            "n": n,
            "mean_pct": round(100 * nw_base["mean"], 4) if nw_base["mean"] else None,
            "t_hac": nw_base["t"],
            "p_hac": nw_base["p"],
        }
        results[f"v3_{label}_excess"] = {
            "n": n,
            "mean_pct": round(100 * nw_exc["mean"], 4) if nw_exc["mean"] else None,
            "t_hac": nw_exc["t"],
            "p_hac": nw_exc["p"],
            "sign_correct": (nw_exc["mean"] is not None and nw_exc["mean"] > 0),
        }
    return results


# ---------------------------------------------------------------------------
# Split-half (GATE G2) — per-variant
# ---------------------------------------------------------------------------

def split_half_sign(series: pd.Series) -> dict:
    """Return sign in first and second half; pass if same-sign positive."""
    s = series.dropna().sort_index()
    n = len(s)
    if n < 10:
        return {"n": n, "pass": False, "reason": "too few obs"}
    h1 = s.iloc[:n // 2]
    h2 = s.iloc[n // 2:]
    m1 = float(h1.mean())
    m2 = float(h2.mean())
    same_sign = (np.sign(m1) == np.sign(m2))
    direction_correct = (m1 > 0 and m2 > 0)
    return {
        "n": n, "n_h1": len(h1), "n_h2": len(h2),
        "mean_h1_pct": round(100 * m1, 4),
        "mean_h2_pct": round(100 * m2, 4),
        "same_sign": same_sign,
        "direction_correct": direction_correct,
        "pass": direction_correct,
    }


# ---------------------------------------------------------------------------
# Trial ledger registration
# ---------------------------------------------------------------------------

def register_trials(ledger: TrialLedger) -> None:
    """Register every config in the family grid BEFORE computing results."""
    configs = [
        # V1 cells
        {"variant": "V1", "tenor": "pooled", "condition": "conditional_concession"},
        {"variant": "V1", "tenor": "10y",    "condition": "conditional_concession"},
        {"variant": "V1", "tenor": "30y",    "condition": "conditional_concession"},
        {"variant": "V1", "tenor": "pooled", "condition": "unconditional"},
        # V2 cells
        {"variant": "V2", "condition": "gap_positive"},
        {"variant": "V2", "condition": "unconditional"},
        {"variant": "V2", "condition": "gap_signed"},
        # V3 cells
        {"variant": "V3", "instrument": "TLT", "metric": "last_day_return"},
        {"variant": "V3", "instrument": "TLT", "metric": "excess_over_avg"},
        {"variant": "V3", "instrument": "IEF", "metric": "last_day_return"},
        {"variant": "V3", "instrument": "IEF", "metric": "excess_over_avg"},
    ]
    n = ledger.log_grid(configs, family=FAMILY)
    print(f"  [ledger] registered {n} configs for family={FAMILY}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    out = []

    header = f"""# d2_rates_calendar_flows — Phase-0 Validation Report

**Family:** {FAMILY}
**Pre-reg:** research/SIGNAL_LAB_FRONTIER_DAY2_FABLE_ADJUDICATION_2026-07-06.md item 1
**Date run:** 2026-07-06

## Pre-registered amendments (gaps in written prereg, filed BEFORE computing)

- AM-1: 10y and 30y auction cells tested separately and pooled; all enter BH.
  Headline = pooled (most events, same mechanism).
- AM-2: "Measured concession" = pre-window TLT cum-return < 0 (sign gate, no full-sample quantile).
- AM-3: "Final week" = last 5 bus days of quarter; gap from quarter-start; t-7 = 7 bus days pre-QE.
- AM-4: Last business day = last trading day in calendar month per TLT price series.
- AM-5: Newey-West lag = min(4, sqrt(n)) applied to collapsed date-level series.
"""
    out.append(header)

    # ------------------------------------------------------------------ #
    # Data loading + verification
    # ------------------------------------------------------------------ #
    print("\n=== DATA STORE VERIFICATION ===")
    out.append("## Data store verification\n```")
    prices = load_prices()
    auctions = load_auctions()
    for ticker, s in prices.items():
        out.append(f"{ticker}: {len(s)} rows, {s.index.min().date()} .. {s.index.max().date()}")
    out.append(f"Auctions: {len(auctions)} rows, "
               f"{auctions['auction_date'].min().date()} .. "
               f"{auctions['auction_date'].max().date()}, "
               f"10y={( auctions['tenor_bucket']=='10y').sum()} "
               f"30y={(auctions['tenor_bucket']=='30y').sum()}")
    out.append("```\n")

    # ------------------------------------------------------------------ #
    # Register trials BEFORE computing
    # ------------------------------------------------------------------ #
    print("\n=== TRIAL LEDGER REGISTRATION ===")
    led = TrialLedger(family=FAMILY)
    register_trials(led)
    n_trials = led.effective_n(FAMILY)
    out.append(f"**Trial budget:** {n_trials} configs registered pre-computation "
               f"(family={FAMILY})\n")

    # ------------------------------------------------------------------ #
    # Compute variants
    # ------------------------------------------------------------------ #
    print("\n=== COMPUTING V1: AUCTION CYCLE ===")
    r1 = v1_auction_cycle(prices, auctions)

    print("\n=== COMPUTING V2: QUARTER-END REBALANCE ===")
    r2 = v2_quarter_end_rebalance(prices)

    print("\n=== COMPUTING V3: MONTH-END EXTENSION ===")
    r3 = v3_month_end_extension(prices)

    # ------------------------------------------------------------------ #
    # Build p-value map for BH FDR (GATE G1)
    # Primary cells: one per variant (headline cell per variant)
    # ------------------------------------------------------------------ #
    # Primary cells entered into BH:
    pval_map = {}

    # V1: headline = pooled conditional
    v1h = r1.get("v1_pooled_conditional", {})
    if v1h.get("p_hac") is not None:
        pval_map["v1_pooled_conditional"] = v1h["p_hac"]
    # V1 10y and 30y also enter family BH (AM-1)
    for k in ("v1_10y_conditional", "v1_30y_conditional"):
        c = r1.get(k, {})
        if c.get("p_hac") is not None:
            pval_map[k] = c["p_hac"]

    # V2: headline = conditional on gap > 0
    v2h = r2.get("v2_conditional_gap_pos", {})
    if v2h.get("p_hac") is not None:
        pval_map["v2_conditional_gap_pos"] = v2h["p_hac"]
    v2s = r2.get("v2_gap_signed", {})
    if v2s.get("p_hac") is not None:
        pval_map["v2_gap_signed"] = v2s["p_hac"]

    # V3: TLT and IEF last-day and excess cells
    for k in ("v3_tlt_last_day", "v3_tlt_excess", "v3_ief_last_day", "v3_ief_excess"):
        c = r3.get(k, {})
        if c.get("p_hac") is not None:
            pval_map[k] = c["p_hac"]

    bh = benjamini_hochberg(pval_map, alpha=0.10)

    # ------------------------------------------------------------------ #
    # Split-half: rebuild series for each variant
    # ------------------------------------------------------------------ #
    # V1 pooled conditional
    tlt = prices["TLT"]
    v1_series_rows = []
    for _, row in auctions.iterrows():
        t0_date = row["auction_date"]
        pos0 = tlt.index.searchsorted(t0_date, side="right") - 1
        if pos0 < 4 or pos0 + 3 >= len(tlt):
            continue
        pre_ret = float(tlt.iloc[pos0] / tlt.iloc[pos0 - 3] - 1)
        post_ret = float(tlt.iloc[pos0 + 3] / tlt.iloc[pos0] - 1)
        v1_series_rows.append({
            "event_date": tlt.index[pos0],
            "post_ret": post_ret,
            "concession": pre_ret < 0,
        })
    v1_df = pd.DataFrame(v1_series_rows).drop_duplicates("event_date").set_index("event_date")
    v1_cond_series = v1_df[v1_df["concession"]]["post_ret"]

    # V2 conditional
    spy = prices["SPY"]
    tlt2 = prices["TLT"]
    common = spy.index.intersection(tlt2.index)
    spy_c = spy.reindex(common)
    tlt_c = tlt2.reindex(common)
    qe_dates = pd.date_range(common.min(), common.max(), freq="BQE")
    v2_rows = []
    for qe in qe_dates:
        pos_qe = common.searchsorted(qe, side="right") - 1
        if pos_qe < 60:
            continue
        pos_t7 = pos_qe - 7
        qe_ts = common[pos_qe]
        quarter_start = qe_ts - pd.offsets.BQuarterBegin(startingMonth=1)
        pos_qs_true = common.searchsorted(quarter_start, side="left")
        if pos_qs_true >= pos_t7:
            continue
        spy_gap = float(spy_c.iloc[pos_t7] / spy_c.iloc[pos_qs_true] - 1)
        tlt_gap_f = float(tlt_c.iloc[pos_t7] / tlt_c.iloc[pos_qs_true] - 1)
        gap = spy_gap - tlt_gap_f
        pos_final = pos_qe - 5
        if pos_final < 0:
            continue
        tlt_final = float(tlt_c.iloc[pos_qe] / tlt_c.iloc[pos_final] - 1)
        spy_final = float(spy_c.iloc[pos_qe] / spy_c.iloc[pos_final] - 1)
        outcome = tlt_final - spy_final
        v2_rows.append({"event_date": common[pos_qe], "gap": gap, "outcome": outcome})
    v2_df = pd.DataFrame(v2_rows).set_index("event_date").sort_index()
    v2_cond_series = v2_df[v2_df["gap"] > 0]["outcome"]

    # V3 TLT last-day series
    tlt_ret = tlt.pct_change().dropna()
    month_groups = pd.Series(tlt_ret.index).groupby(pd.to_datetime(tlt_ret.index).to_period("M"))
    v3_tlt_rows = []
    for period, group in month_groups:
        dates = sorted(group.values)
        if len(dates) < 5:
            continue
        last_day = pd.Timestamp(dates[-1])
        v3_tlt_rows.append({"event_date": last_day, "ret": float(tlt_ret.loc[last_day])})
    v3_tlt_series = pd.DataFrame(v3_tlt_rows).set_index("event_date")["ret"]

    sh_v1 = split_half_sign(v1_cond_series)
    sh_v2 = split_half_sign(v2_cond_series)
    sh_v3 = split_half_sign(v3_tlt_series)

    # ------------------------------------------------------------------ #
    # Report sections
    # ------------------------------------------------------------------ #

    # --- V1 ----
    out.append("## V1 — Auction-cycle concession/rebound (Lou-Yan-Zhang)\n")
    out.append(f"Universe: 10y + 30y coupon auctions 2016-2026. "
               f"Pre-auction concession window t-3..t0; post-auction rebound t0..t+3.\n")
    out.append(f"Pre-window TLT mean return: {r1.get('pre_window_mean', 'N/A'):.4%} "
               f"(t_HAC={r1.get('pre_window_t_hac', 'N/A')}, "
               f"n={r1.get('pre_window_n', 'N/A')})")
    out.append(f"Direction correct (pre-window < 0): {r1.get('pre_window_direction_correct', 'N/A')}\n")

    out.append("```")
    out.append(f"{'cell':<30} {'n':>5} {'mean%':>8} {'t_HAC':>7} {'p':>7} {'sign_ok':>8} {'BH_q':>7} {'BH_rej':>7}")
    for k in ("v1_pooled_conditional", "v1_10y_conditional", "v1_30y_conditional",
              "v1_pooled_unconditional"):
        c = r1.get(k, {})
        bh_r = bh.get(k, {})
        n_c = c.get("n", 0)
        m = f"{c.get('mean_pct', 'N/A')}" if c.get("mean_pct") is not None else "N/A"
        t = f"{c.get('t_hac', 'N/A')}"
        p = f"{c.get('p_hac', 'N/A')}"
        sign = str(c.get("sign_correct", "N/A"))
        bh_q = f"{bh_r.get('q', 'N/A')}"
        bh_rej = str(bh_r.get("reject", "N/A"))
        out.append(f"{k:<30} {n_c:>5} {m:>8} {t:>7} {p:>7} {sign:>8} {bh_q:>7} {bh_rej:>7}")
    out.append("```\n")

    out.append("**Split-half (G2) — V1 pooled conditional:**")
    out.append(f"```\n"
               f"H1: mean={sh_v1['mean_h1_pct']}% (n={sh_v1['n_h1']})\n"
               f"H2: mean={sh_v1['mean_h2_pct']}% (n={sh_v1['n_h2']})\n"
               f"Same-sign positive: {sh_v1['pass']}\n"
               f"GATE G2 V1: {'PASS' if sh_v1['pass'] else 'FAIL'}\n```\n")

    # G3 V1: conditional vs unconditional baseline
    v1_cond_g = r1.get("v1_pooled_conditional", {})
    v1_unc_g = r1.get("v1_pooled_unconditional", {})
    v1_g3_pass = (v1_cond_g.get("mean_pct") is not None and
                  v1_unc_g.get("mean_pct") is not None and
                  (v1_cond_g["mean_pct"] or 0) > (v1_unc_g["mean_pct"] or 0))
    out.append(f"**G3 V1 (conditional > unconditional baseline):**")
    out.append(f"  Conditional mean: {v1_cond_g.get('mean_pct')}%  "
               f"Unconditional mean: {v1_unc_g.get('mean_pct')}%  "
               f"{'PASS' if v1_g3_pass else 'FAIL'}\n")

    # --- V2 ----
    out.append("## V2 — Quarter-end pension rebalance\n")
    out.append(f"Universe: all quarter-ends 2002-2026. "
               f"Gap = SPY-TLT outperformance from quarter-start to t-7. "
               f"Outcome = TLT-vs-SPY final 5 bus days.\n")
    out.append(f"Quarters total: {r2.get('n_quarters', 'N/A')}  "
               f"Pct with equity outperf gap: {r2.get('pct_gap_positive', 'N/A')}%\n")

    out.append("```")
    out.append(f"{'cell':<30} {'n':>5} {'mean%':>8} {'t_HAC':>7} {'p':>7} {'sign_ok':>8} {'BH_q':>7} {'BH_rej':>7}")
    for k in ("v2_conditional_gap_pos", "v2_gap_signed", "v2_unconditional"):
        c = r2.get(k, {})
        bh_r = bh.get(k, {})
        n_c = c.get("n", 0)
        m = f"{c.get('mean_pct', 'N/A')}" if c.get("mean_pct") is not None else "N/A"
        t = f"{c.get('t_hac', 'N/A')}"
        p = f"{c.get('p_hac', 'N/A')}"
        sign = str(c.get("sign_correct", "N/A"))
        bh_q = f"{bh_r.get('q', 'N/A')}"
        bh_rej = str(bh_r.get("reject", "N/A"))
        out.append(f"{k:<30} {n_c:>5} {m:>8} {t:>7} {p:>7} {sign:>8} {bh_q:>7} {bh_rej:>7}")
    out.append("```\n")

    out.append("**Split-half (G2) — V2 conditional on gap>0:**")
    out.append(f"```\n"
               f"H1: mean={sh_v2['mean_h1_pct']}% (n={sh_v2['n_h1']})\n"
               f"H2: mean={sh_v2['mean_h2_pct']}% (n={sh_v2['n_h2']})\n"
               f"Same-sign positive: {sh_v2['pass']}\n"
               f"GATE G2 V2: {'PASS' if sh_v2['pass'] else 'FAIL'}\n```\n")

    # G3 V2
    v2_cond_g = r2.get("v2_conditional_gap_pos", {})
    v2_unc_g = r2.get("v2_unconditional", {})
    v2_g3_pass = (v2_cond_g.get("mean_pct") is not None and
                  v2_unc_g.get("mean_pct") is not None and
                  abs(v2_cond_g.get("mean_pct") or 0) > abs(v2_unc_g.get("mean_pct") or 0))
    out.append(f"**G3 V2 (conditional > unconditional baseline in absolute effect):**")
    out.append(f"  Conditional mean: {v2_cond_g.get('mean_pct')}%  "
               f"Unconditional mean: {v2_unc_g.get('mean_pct')}%  "
               f"{'PASS' if v2_g3_pass else 'FAIL'}\n")

    # --- V3 ----
    out.append("## V3 — Month-end index extension day\n")
    out.append("Universe: all calendar months in TLT history (2002-2026). "
               "Last trading day return vs avg of all other days in the month.\n")
    out.append("```")
    out.append(f"{'cell':<30} {'n':>5} {'mean%':>9} {'t_HAC':>7} {'p':>7} {'sign_ok':>8} {'BH_q':>7} {'BH_rej':>7}")
    for k in ("v3_tlt_last_day", "v3_tlt_excess", "v3_tlt_avg_other",
              "v3_ief_last_day", "v3_ief_excess", "v3_ief_avg_other"):
        c = r3.get(k, {})
        bh_r = bh.get(k, {})
        n_c = c.get("n", 0)
        m = f"{c.get('mean_pct', 'N/A')}" if c.get("mean_pct") is not None else "N/A"
        t = f"{c.get('t_hac', 'N/A')}"
        p = f"{c.get('p_hac', 'N/A')}"
        sign = str(c.get("sign_correct", "N/A"))
        bh_q = f"{bh_r.get('q', 'N/A')}"
        bh_rej = str(bh_r.get("reject", "N/A"))
        out.append(f"{k:<30} {n_c:>5} {m:>9} {t:>7} {p:>7} {sign:>8} {bh_q:>7} {bh_rej:>7}")
    out.append("```\n")

    out.append("**Split-half (G2) — V3 TLT last-day return:**")
    out.append(f"```\n"
               f"H1: mean={sh_v3['mean_h1_pct']}% (n={sh_v3['n_h1']})\n"
               f"H2: mean={sh_v3['mean_h2_pct']}% (n={sh_v3['n_h2']})\n"
               f"Same-sign positive: {sh_v3['pass']}\n"
               f"GATE G2 V3: {'PASS' if sh_v3['pass'] else 'FAIL'}\n```\n")

    # G3 V3: last-day vs avg-other
    v3_last = r3.get("v3_tlt_last_day", {})
    v3_other = r3.get("v3_tlt_avg_other", {})
    v3_g3_pass = (v3_last.get("mean_pct") is not None and
                  v3_other.get("mean_pct") is not None and
                  (v3_last.get("mean_pct") or 0) > (v3_other.get("mean_pct") or 0))
    out.append(f"**G3 V3 (last-day mean > avg-other-days baseline):**")
    out.append(f"  Last-day mean: {v3_last.get('mean_pct')}%  "
               f"Avg-other-days mean: {v3_other.get('mean_pct')}%  "
               f"{'PASS' if v3_g3_pass else 'FAIL'}\n")

    # ------------------------------------------------------------------ #
    # Gate summary table
    # ------------------------------------------------------------------ #
    # G1: BH FDR — any cell with q <= 0.10 and reject=True
    g1_rejections = {k: v for k, v in bh.items() if v.get("reject")}
    g1_pass = len(g1_rejections) > 0

    # G4: |t_HAC| >= 2 for headline cells
    def t_ok(c):
        t = c.get("t_hac")
        return t is not None and abs(t) >= 2.0

    g4_v1 = t_ok(v1_cond_g)
    g4_v2 = t_ok(v2_cond_g)
    g4_v3 = t_ok(v3_last)
    g4_pass = g4_v1 or g4_v2 or g4_v3  # at least one variant clears the t bar

    # Overall: SCORED = at least one variant passes all four gates
    # A null result is a valid outcome
    def variant_passes_all(bh_key, g2_sh, g3_pass_var, t_c):
        bh_ok = bh.get(bh_key, {}).get("reject", False)
        return bh_ok and g2_sh["pass"] and g3_pass_var and t_ok(t_c)

    v1_all = variant_passes_all("v1_pooled_conditional", sh_v1, v1_g3_pass, v1_cond_g)
    v2_all = variant_passes_all("v2_conditional_gap_pos", sh_v2, v2_g3_pass, v2_cond_g)
    v3_all = variant_passes_all("v3_tlt_last_day", sh_v3, v3_g3_pass, v3_last)

    any_pass = v1_all or v2_all or v3_all
    verdict = "SCORED" if any_pass else "NULL — all four gates required; not all cleared"

    out.append("## Gate summary (frozen gates, applied after computing)\n")
    out.append("```")
    out.append(f"{'Gate':<50} {'Result':>10}")
    out.append("-" * 62)
    out.append(f"G1 BH FDR q<=0.10 (any family cell rejects)          "
               f"{'PASS' if g1_pass else 'FAIL'}")
    if g1_rejections:
        for k, v in g1_rejections.items():
            out.append(f"   -> {k}: q={v['q']}")
    else:
        out.append(f"   -> no cell survives BH at q<=0.10")

    out.append(f"G2 split-half same-sign positive:")
    out.append(f"   V1 pooled conditional:   {'PASS' if sh_v1['pass'] else 'FAIL'} "
               f"(H1={sh_v1['mean_h1_pct']}% H2={sh_v1['mean_h2_pct']}%)")
    out.append(f"   V2 gap>0 conditional:    {'PASS' if sh_v2['pass'] else 'FAIL'} "
               f"(H1={sh_v2['mean_h1_pct']}% H2={sh_v2['mean_h2_pct']}%)")
    out.append(f"   V3 TLT last-day:         {'PASS' if sh_v3['pass'] else 'FAIL'} "
               f"(H1={sh_v3['mean_h1_pct']}% H2={sh_v3['mean_h2_pct']}%)")

    out.append(f"G3 conditional > unconditional baseline:")
    out.append(f"   V1: {'PASS' if v1_g3_pass else 'FAIL'}  "
               f"V2: {'PASS' if v2_g3_pass else 'FAIL'}  "
               f"V3: {'PASS' if v3_g3_pass else 'FAIL'}")

    out.append(f"G4 |t_HAC| >= 2 (headline cell per variant):")
    out.append(f"   V1 t={v1_cond_g.get('t_hac')}: {'PASS' if g4_v1 else 'FAIL'}  "
               f"V2 t={v2_cond_g.get('t_hac')}: {'PASS' if g4_v2 else 'FAIL'}  "
               f"V3 t={v3_last.get('t_hac')}: {'PASS' if g4_v3 else 'FAIL'}")

    out.append("-" * 62)
    out.append(f"{'Per-variant (all 4 gates):':<50}")
    out.append(f"   V1 auction-cycle:          {'PASS' if v1_all else 'FAIL'}")
    out.append(f"   V2 quarter-end rebalance:  {'PASS' if v2_all else 'FAIL'}")
    out.append(f"   V3 month-end extension:    {'PASS' if v3_all else 'FAIL'}")
    out.append("```\n")

    out.append(f"## VERDICT\n\n**{verdict}**\n")

    out.append("""## In plain English

This study tests three ideas about how the bond market (TLT = 20-year Treasury ETF)
behaves around predictable calendar events.

**V1 — Auction concession/rebound:** When the Treasury sells new bonds, dealers
must absorb supply in the days before the auction, pushing prices down (the
"concession"). The academic prediction (Lou, Yan, Zhang) is that this selling
reverses shortly after the auction date — a rebound. We look at 10-year and
30-year coupon auctions from 2016 onward, measure whether TLT actually fell in
the 3 days before each auction, and if it did, whether it bounced over the 3 days
after.

**V2 — Quarter-end pension rebalancing:** Large pension funds are required to
maintain fixed allocations between stocks and bonds. If stocks greatly outperformed
bonds over a quarter, pensions must sell stocks and buy bonds in the last few days
of the quarter to rebalance. The prediction: when stocks have beaten bonds by a lot
(the "gap"), TLT should outperform SPY in the final week of the quarter.

**V3 — Month-end extension:** Bond index managers buy longer-duration bonds on the
last day of the month to match their benchmark's new duration (bonds added to
indices have longer maturities than those removed). The prediction: TLT and IEF
should show a positive return on the last trading day of each month, above the
rest-of-month average.

All three are pre-registered bets — if the evidence doesn't support them, the null
result is reported honestly. A failed gate is a successful test.
""")

    # ------------------------------------------------------------------ #
    # Nightly wiring section
    # ------------------------------------------------------------------ #
    out.append("""## Nightly wiring (for consolidation)

If any variant clears all four gates, it should be integrated as follows:

**V1 auction-cycle** (if SCORED):
  - Standalone collector (standalone, do NOT edit scripts/collect.py):
    `scripts/collect_treasury_auctions.py` — already on disk at
    `data/treasury_auctions/`; verify it runs incrementally.
  - Signal generator: `engine/rates_calendar_signals.py` → function
    `auction_cycle_signal(tlt_prices, auctions_df)` returns a date-indexed
    Series of expected next-3d TLT excess return, NaN on non-auction weeks.
  - Wire into nightly via `scripts/build_rates_calendar.py` (new, standalone).

**V2 quarter-end rebalance** (if SCORED):
  - No new data collection needed (SPY + TLT already in yahoo store).
  - Signal: `engine/rates_calendar_signals.py` → `qe_rebalance_signal()`.
  - Fire 7 business days before each quarter-end; active for 5 bus days.

**V3 month-end extension** (if SCORED):
  - No new collection needed.
  - Signal: `engine/rates_calendar_signals.py` → `month_end_extension_signal()`.
  - Active only on last trading day of month; returns zero all other days.

All three can share a single `rates_calendar_signals.py` module and a single
`build_rates_calendar.py` nightly job under the existing pipeline.

**DO NOT wire into production until at least one variant clears all gates.**
""")

    report = "\n".join(out)
    print("\n" + "=" * 70)
    print(report)
    print("=" * 70)

    rp = ROOT / "reports" / "d2-rates-calendar-flows-phase0.md"
    rp.parent.mkdir(exist_ok=True)
    rp.write_text(report)
    print(f"\n[written] {rp}")

    # JSON summary for CI / calling scripts
    summary = {
        "family": FAMILY,
        "verdict": verdict,
        "n_trials_registered": n_trials,
        "g1_bh_pass": g1_pass,
        "g1_rejections": list(g1_rejections.keys()),
        "g2_v1_pass": sh_v1["pass"],
        "g2_v2_pass": sh_v2["pass"],
        "g2_v3_pass": sh_v3["pass"],
        "g3_v1_pass": v1_g3_pass,
        "g3_v2_pass": v2_g3_pass,
        "g3_v3_pass": v3_g3_pass,
        "g4_v1_t": v1_cond_g.get("t_hac"),
        "g4_v2_t": v2_cond_g.get("t_hac"),
        "g4_v3_t": v3_last.get("t_hac"),
        "v1_all_gates": v1_all,
        "v2_all_gates": v2_all,
        "v3_all_gates": v3_all,
        "bh_table": bh,
    }
    print("\n=== JSON SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
