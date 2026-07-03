"""China turnover-surge early-rotation signal — Phase 0 falsification.

Hypothesis: in a retail-driven A-share market a sector's RELATIVE TURNOVER SURGE
(成交额 z-score, cross-sectionally demeaned) LEADS its forward relative strength —
i.e. volume arrives before price, flagging the NEXT running theme.

Panel: the 32 Shenwan L1 sector indices, data/china_sectors/*.parquet, 1999-2026,
survivorship-free (all 32 sectors existed from inception).

Signal construction (leak-free: uses data <= d only at every date d):
  surge_d  = z(log20d_amount_d vs own trailing 250d distribution)
           → then cross-sectionally DEMEANED across sectors (isolates WHICH sector
             surges above the broad market's volume level; strips the market-wide
             volume expansion common to all sectors on risk-on days).

Forward target: sector RELATIVE return vs EW-of-all-sectors over next 20d and 60d,
measured on a non-overlapping MONTHLY grid (end-of-month dates) to avoid look-ahead
in IC autocorrelation.

Stats:
  (a) Per-date cross-sectional Spearman rank-IC via engine.validation.rank_ic;
      summary stats via ic_summary HAC-t (Newey-West 4/2 lags for 20/60d);
      sub-eras: full (2000-2026) / 2015+ / 2021+.
  (b) Benjamini-Hochberg FDR (alpha=0.10) across all
      {signal-variant x horizon x era} cells.
  (c) EVENT STUDY: top-decile surge months (signal >= 80th pctile for that sector)
      → mean forward 20d / 60d relative return vs all months.
  (d) LAGGED variant: signal at d-21 → forward return from d (checks whether the
      surge is leading or merely coincident with the return move).

Writes reports/china-turnover-surge.md with real table + honest verdict.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as spstats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine.validation import rank_ic, ic_summary, benjamini_hochberg  # noqa: E402
from lib import config  # noqa: E402

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #
SECTORS_DIR = "data/china_sectors"
AMOUNT_WINDOW = 20       # mean turnover window
LOOKBACK = 250           # trailing distribution for z-score
MIN_LOOKBACK = 60        # minimum history required (~3 months), conservative
FWD_20D = 20             # short horizon
FWD_60D = 60             # medium horizon
DECILE_THRESH = 0.80     # top-20% for event study
MIN_SECTORS = 10         # minimum cross-section to compute IC (of 32 available)


# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #
def load_sector_panel(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load all 32 Shenwan sector parquets; return (close, amount) aligned."""
    close_d, amount_d = {}, {}
    for fp in sorted((root / SECTORS_DIR).glob("*.parquet")):
        if fp.stem == "valuation":
            continue
        df = pd.read_parquet(fp)
        if "close" not in df.columns or "amount" not in df.columns:
            continue
        close_d[fp.stem] = df["close"]
        amount_d[fp.stem] = df["amount"]
    close = pd.DataFrame(close_d).sort_index()
    amount = pd.DataFrame(amount_d).sort_index()
    # align on common dates
    idx = close.index.intersection(amount.index)
    return close.loc[idx], amount.loc[idx]


# --------------------------------------------------------------------------- #
# signal construction
# --------------------------------------------------------------------------- #
def build_signal(amount: pd.DataFrame) -> pd.DataFrame:
    """Compute the cross-sectionally-demeaned z-score of log(20d-mean amount).

    Leak-free: at each date d, the z-score uses only data in (d-LOOKBACK, d].
    Cross-sectional demeaning removes market-wide volume expansions so only the
    RELATIVE surge of a sector vs others survives.

    Returns a DataFrame of the same shape as `amount`.
    """
    log_amt = np.log(amount.clip(lower=1e-9))
    # rolling 20d mean of log amount (forward-looking blocker: min_periods guards early rows)
    roll20 = log_amt.rolling(AMOUNT_WINDOW, min_periods=AMOUNT_WINDOW // 2).mean()
    # per-sector z-score vs own trailing 250d distribution
    rol_mean = roll20.rolling(LOOKBACK, min_periods=MIN_LOOKBACK).mean()
    rol_std = roll20.rolling(LOOKBACK, min_periods=MIN_LOOKBACK).std()
    z = (roll20 - rol_mean) / rol_std.replace(0, np.nan)
    # cross-sectional demeaning: subtract mean across sectors each day
    # (keeps the signal about WHICH sector surges, not whether total market volume is high)
    z_dm = z.sub(z.mean(axis=1), axis=0)
    return z_dm


# --------------------------------------------------------------------------- #
# forward returns (relative to EW of all sectors)
# --------------------------------------------------------------------------- #
def build_fwd_relative(close: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Sector fwd `horizon`-day return MINUS the EW-of-all-sectors return.

    At date d, fwd_rel[d, s] = close[d+horizon]/close[d] - 1  - universe_mean
    (universe_mean computed the same way — no look-ahead).

    Shift by `horizon` so index d holds the forward return STARTING at d.
    """
    # raw fwd return for each sector (pct change horizon bars ahead)
    fwd_raw = close.pct_change(horizon, fill_method=None).shift(-horizon)
    # EW universe mean at each date
    ew = fwd_raw.mean(axis=1)
    # relative return
    return fwd_raw.sub(ew, axis=0)


# --------------------------------------------------------------------------- #
# monthly grid (non-overlapping)
# --------------------------------------------------------------------------- #
def monthly_grid(idx: pd.DatetimeIndex, burnin: int, lookforward: int) -> list:
    """End-of-month dates satisfying the burn-in and look-forward constraints."""
    grid = [idx[idx <= me][-1]
            for me in pd.date_range(idx.min(), idx.max(), freq="ME")
            if len(idx[idx <= me])]
    iloc_map = {d: idx.get_loc(d) for d in grid}
    return [d for d in grid if iloc_map[d] >= burnin and iloc_map[d] + lookforward < len(idx)]


# --------------------------------------------------------------------------- #
# IC series
# --------------------------------------------------------------------------- #
def compute_ic_series(signal: pd.DataFrame, fwd_rel: pd.DataFrame,
                      grid: list) -> list[float]:
    """Cross-sectional rank IC for each date in `grid`."""
    ics = []
    for d in grid:
        if d not in signal.index or d not in fwd_rel.index:
            continue
        s = signal.loc[d].dropna()
        f = fwd_rel.loc[d].dropna()
        ic = rank_ic(s, f)
        ics.append(ic)
    return ics


# --------------------------------------------------------------------------- #
# era slicing helpers
# --------------------------------------------------------------------------- #
def era_grid(grid: list, start_year: int | None) -> list:
    if start_year is None:
        return grid
    return [d for d in grid if d.year >= start_year]


# --------------------------------------------------------------------------- #
# event study: top-decile surge months
# --------------------------------------------------------------------------- #
def event_study(signal: pd.DataFrame, fwd_rel_20: pd.DataFrame,
                fwd_rel_60: pd.DataFrame, grid: list) -> dict:
    """For each sector separately, label top-decile surge months and compare
    their mean forward relative return vs all other months.

    Returns aggregated stats: mean and t-stat of the top-decile premium.
    """
    surplus_20, surplus_60 = [], []  # (top-decile avg) - (non-top avg) per sector per grid date
    top20_ret, all20_ret = [], []
    top60_ret, all60_ret = [], []

    for col in signal.columns:
        s_col = signal[col].dropna()
        for d in grid:
            if d not in s_col.index:
                continue
            sv = s_col.loc[d]
            # threshold is the 80th pctile of the signal ACROSS all grid dates up to d
            # for this sector — leak-free, but computed per-sector using the full grid
            # (for the event study the in-sample quantile is standard practice)
            past = s_col.loc[s_col.index <= d]
            thresh = float(past.quantile(DECILE_THRESH))
            is_top = sv >= thresh

            f20 = fwd_rel_20.loc[d, col] if (d in fwd_rel_20.index and col in fwd_rel_20.columns) else np.nan
            f60 = fwd_rel_60.loc[d, col] if (d in fwd_rel_60.index and col in fwd_rel_60.columns) else np.nan

            if is_top:
                if not np.isnan(f20):
                    top20_ret.append(f20)
                if not np.isnan(f60):
                    top60_ret.append(f60)
            else:
                if not np.isnan(f20):
                    all20_ret.append(f20)
                if not np.isnan(f60):
                    all60_ret.append(f60)

    def ev(top, non_top):
        if len(top) < 10 or len(non_top) < 10:
            return {"n_top": len(top), "n_other": len(non_top), "mean_top": None,
                    "mean_other": None, "excess": None, "t": None, "p": None}
        t_arr = np.array(top)
        n_arr = np.array(non_top)
        excess = float(t_arr.mean() - n_arr.mean())
        tstat, pval = spstats.ttest_ind(t_arr, n_arr, equal_var=False)
        return {"n_top": len(top), "n_other": len(non_top),
                "mean_top": round(float(t_arr.mean()) * 100, 3),
                "mean_other": round(float(n_arr.mean()) * 100, 3),
                "excess": round(excess * 100, 3),
                "t": round(float(tstat), 2),
                "p": round(float(pval), 4)}

    return {"fwd20": ev(top20_ret, all20_ret), "fwd60": ev(top60_ret, all60_ret)}


# --------------------------------------------------------------------------- #
# report rendering
# --------------------------------------------------------------------------- #
def fmt_ic_row(label: str, summary: dict) -> str:
    if "mean_ic" not in summary:
        return f"| {label} | — | — | — | — | — | {summary.get('n', '?')} |"
    return (f"| {label} | {summary['mean_ic']:.4f} | {summary['ic_vol']:.4f} "
            f"| {summary['t_hac']:.2f} | {summary['p_hac']:.4f} "
            f"| {summary['hit']:.3f} | {summary['n']} |")


def fmt_bh_row(key: str, bh: dict) -> str:
    r = bh.get(key, {})
    if not r:
        return f"| {key} | — | — | — |"
    return (f"| {key} | {r.get('p', '?'):.4f} | {r.get('q', '?'):.4f} "
            f"| {'YES' if r.get('reject') else 'no'} |")


def render(ic_rows: list[tuple], bh_results: dict, ev20: dict, ev60: dict,
           close: pd.DataFrame, grid_full: list) -> str:
    lines = [
        "# China turnover-surge early-rotation signal — Phase 0 (26y Shenwan)",
        "",
        (f"*Generated by `scripts/china_turnover_surge_phase0.py`.  "
         f"Panel: 32 Shenwan L1 sectors, "
         f"{close.index.min().date()} → {close.index.max().date()}, "
         f"{len(grid_full)} monthly rebalance dates.*"),
        "",
        "**Signal:** z-score of log(20d-mean turnover 成交额) vs trailing 250d distribution, "
        "then cross-sectionally demeaned across sectors each date.  "
        "**Target:** sector forward return MINUS EW-of-all-sectors over the same horizon "
        "(relative performance, not absolute).  "
        "**Lagged variant (d-21):** signal is shifted forward 21 calendar business days — "
        "if volume truly LEADS price, the lag should preserve the IC; "
        "if the signal is merely COINCIDENT, the lag should kill it.",
        "",
        "---",
        "",
        "## IC table  (cross-sectional rank-IC, Newey-West HAC t-stat)",
        "",
        "| variant · era · horizon | mean IC | IC vol | HAC-t | HAC-p | hit | n |",
        "|---|--:|--:|--:|--:|--:|--:|",
    ]
    for label, summary in ic_rows:
        lines.append(fmt_ic_row(label, summary))

    lines += [
        "",
        "---",
        "",
        "## Benjamini-Hochberg FDR (alpha = 10%)",
        "",
        "| cell | raw p | BH-q | reject? |",
        "|---|--:|--:|--:|",
    ]
    for k in sorted(bh_results.keys()):
        lines.append(fmt_bh_row(k, bh_results))

    lines += [
        "",
        "---",
        "",
        "## Event study  (top-decile surge months vs all other months)",
        "",
        "**20-day horizon:**",
        (f"  n_top={ev20['n_top']}  n_other={ev20['n_other']}  "
         f"mean_top={ev20['mean_top']}%  mean_other={ev20['mean_other']}%  "
         f"excess={ev20['excess']}%  t={ev20['t']}  p={ev20['p']}"),
        "",
        "**60-day horizon:**",
        (f"  n_top={ev60['n_top']}  n_other={ev60['n_other']}  "
         f"mean_top={ev60['mean_top']}%  mean_other={ev60['mean_other']}%  "
         f"excess={ev60['excess']}%  t={ev60['t']}  p={ev60['p']}"),
    ]

    return "\n".join(lines)


def verdict_str(ic_rows: list[tuple], bh_results: dict, ev20: dict, ev60: dict) -> str:
    """One honest paragraph verdict based on HAC-t, BH-q, and event study."""
    # collect key numbers
    full20 = next((s for l, s in ic_rows if "contemporaneous" in l and "20d" in l and "full" in l), {})
    full60 = next((s for l, s in ic_rows if "contemporaneous" in l and "60d" in l and "full" in l), {})
    lag20 = next((s for l, s in ic_rows if "lagged d-21" in l and "20d" in l and "full" in l), {})
    lag60 = next((s for l, s in ic_rows if "lagged d-21" in l and "60d" in l and "full" in l), {})

    any_bh_reject = any(v.get("reject") for v in bh_results.values())
    lead_survives = (lag20.get("p_hac", 1) < 0.15 or lag60.get("p_hac", 1) < 0.15)

    lines = [
        "",
        "---",
        "",
        "## Verdict",
        "",
    ]

    ic20_t = full20.get("t_hac")
    ic60_t = full60.get("t_hac")
    lag20_t = lag20.get("t_hac")
    lag60_t = lag60.get("t_hac")
    ev_p20 = ev20.get("p")
    ev_p60 = ev60.get("p")

    # Determine overall signal strength
    contemporaneous_sig = (
        (ic20_t is not None and abs(ic20_t) > 2.0) or
        (ic60_t is not None and abs(ic60_t) > 2.0)
    )
    lagged_sig = (
        (lag20_t is not None and abs(lag20_t) > 2.0) or
        (lag60_t is not None and abs(lag60_t) > 2.0)
    )
    event_sig = (
        (ev_p20 is not None and ev_p20 < 0.10) or
        (ev_p60 is not None and ev_p60 < 0.10)
    )

    if lagged_sig and contemporaneous_sig:
        verdict = "LEADS"
        summary = (
            f"The turnover-surge signal **LEADS** forward relative returns. "
            f"The contemporaneous IC HAC-t ({ic20_t:.2f} / {ic60_t:.2f} for 20d/60d) is "
            f"statistically meaningful, and — critically — the LAGGED variant (signal at d-21, "
            f"forward from d) also survives with HAC-t ({lag20_t:.2f} / {lag60_t:.2f}), "
            f"confirming the relationship is predictive, not merely coincident with the price move. "
            f"BH FDR rejection: {any_bh_reject}. "
            f"Event-study p-values: 20d p={ev_p20}, 60d p={ev_p60}. "
            f"Practical caution: sector-level turnover data may not be available intraday; the "
            f"20d-mean smoothing means the signal turns slowly; and the 32-sector universe is tiny "
            f"(cross-sectional ICs are noisy at N=32)."
        )
    elif contemporaneous_sig and not lagged_sig:
        verdict = "COINCIDENT"
        summary = (
            f"The turnover-surge signal is **COINCIDENT** with the return move, not a true leading "
            f"indicator. The contemporaneous IC HAC-t is notable ({ic20_t:.2f} / {ic60_t:.2f} for "
            f"20d/60d), but the LAGGED variant (signal at d-21) weakens substantially "
            f"(HAC-t {lag20_t:.2f} / {lag60_t:.2f}). This means volume and price are moving "
            f"together in the same period — likely capturing the same information — rather than "
            f"volume arriving first. The signal has no standalone predictive value for a "
            f"forward-looking rotation strategy."
        )
    else:
        verdict = "DEAD"
        summary = (
            f"The turnover-surge signal is **DEAD** as a forward sector-rotation indicator. "
            f"Neither the contemporaneous (HAC-t {ic20_t:.2f} / {ic60_t:.2f}) nor the lagged "
            f"(HAC-t {lag20_t:.2f} / {lag60_t:.2f}) variant clears statistical significance "
            f"after HAC correction. BH FDR rejects: {any_bh_reject}. "
            f"Event-study p-values: 20d p={ev_p20}, 60d p={ev_p60}. "
            f"Volume surges in Chinese sectors either reverse (hot money retreats) or are "
            f"contemporaneous noise. The hypothesis that retail volume LEADS sectoral price "
            f"leadership is not supported by 26 years of Shenwan data."
        )

    lines.append(f"**{verdict}** — {summary}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    root = config.ROOT
    print("[load] reading 32 Shenwan sector parquets …")
    close, amount = load_sector_panel(root)
    n_sectors = close.shape[1]
    print(f"  {n_sectors} sectors, {close.shape[0]} trading days, "
          f"{close.index.min().date()} → {close.index.max().date()}")

    # ------------------------------------------------------------------ #
    # signals
    # ------------------------------------------------------------------ #
    print("[signal] building contemporaneous surge signal …")
    signal = build_signal(amount)        # shape = (dates, 32 sectors)

    print("[signal] building lagged (d-21) surge signal …")
    # Signal at d-21: shift signal forward by 21 trading days so that on each
    # rebalance date d we use the signal value from 21 trading days earlier.
    # Leak-free: the shifted value was already computed with data <= (d-21).
    signal_lag = signal.shift(21)

    # ------------------------------------------------------------------ #
    # forward relative returns
    # ------------------------------------------------------------------ #
    print("[fwd] building forward relative returns (20d, 60d) …")
    fwd20 = build_fwd_relative(close, FWD_20D)
    fwd60 = build_fwd_relative(close, FWD_60D)

    # ------------------------------------------------------------------ #
    # monthly grids
    # ------------------------------------------------------------------ #
    idx = close.index
    # burn-in: need LOOKBACK + AMOUNT_WINDOW + 21 lag buffer = ~295 trading days
    burnin = LOOKBACK + AMOUNT_WINDOW + 25
    grid_full = monthly_grid(idx, burnin, FWD_60D + 5)
    grid_2015 = era_grid(grid_full, 2015)
    grid_2021 = era_grid(grid_full, 2021)

    print(f"  grid: {len(grid_full)} rebalances (full), "
          f"{len(grid_2015)} (2015+), {len(grid_2021)} (2021+)")

    # ------------------------------------------------------------------ #
    # IC series per variant x era x horizon
    # ------------------------------------------------------------------ #
    print("[ic] computing IC series …")

    def compute(sig, grid, label_prefix, lags_20=4, lags_60=2):
        """Compute ic_summary for 20d and 60d."""
        ics20 = compute_ic_series(sig, fwd20, grid)
        ics60 = compute_ic_series(sig, fwd60, grid)
        return [
            (f"{label_prefix} · 20d", ic_summary(ics20, periods_per_year=12)),
            (f"{label_prefix} · 60d", ic_summary(ics60, periods_per_year=4)),
        ]

    ic_rows: list[tuple] = []

    for era_name, grid_era in [("full", grid_full), ("2015+", grid_2015), ("2021+", grid_2021)]:
        print(f"  [ic] contemporaneous · {era_name} …")
        ic_rows += compute(signal, grid_era, f"contemporaneous · {era_name}")
        print(f"  [ic] lagged d-21 · {era_name} …")
        ic_rows += compute(signal_lag, grid_era, f"lagged d-21 · {era_name}")

    # ------------------------------------------------------------------ #
    # Benjamini-Hochberg FDR
    # ------------------------------------------------------------------ #
    print("[bh] running Benjamini-Hochberg FDR …")
    pvals = {label: s.get("p_hac") for label, s in ic_rows}
    bh_results = benjamini_hochberg(pvals, alpha=0.10)

    # ------------------------------------------------------------------ #
    # event study
    # ------------------------------------------------------------------ #
    print("[event] running event study (top-decile surge months) …")
    ev = event_study(signal, fwd20, fwd60, grid_full)
    ev20_stats = ev["fwd20"]
    ev60_stats = ev["fwd60"]

    # ------------------------------------------------------------------ #
    # print table to stdout
    # ------------------------------------------------------------------ #
    print("\n--- IC TABLE ---")
    header = f"{'variant':<45} {'mean IC':>8} {'IC vol':>8} {'HAC-t':>7} {'HAC-p':>7} {'hit':>6} {'n':>5}"
    print(header)
    print("-" * len(header))
    for label, s in ic_rows:
        if "mean_ic" not in s:
            print(f"{label:<45} {'n/a':>8}")
            continue
        print(f"{label:<45} {s['mean_ic']:>8.4f} {s['ic_vol']:>8.4f} "
              f"{s['t_hac']:>7.2f} {s['p_hac']:>7.4f} {s['hit']:>6.3f} {s['n']:>5}")

    print("\n--- BH FDR (alpha=10%) ---")
    for k in sorted(bh_results.keys()):
        r = bh_results[k]
        print(f"  {k:<45} p={r.get('p', '?'):.4f}  q={r.get('q', '?'):.4f}  "
              f"reject={'YES' if r.get('reject') else 'no'}")

    print("\n--- EVENT STUDY ---")
    print(f"  20d: n_top={ev20_stats['n_top']}  n_other={ev20_stats['n_other']}  "
          f"mean_top={ev20_stats['mean_top']}%  mean_other={ev20_stats['mean_other']}%  "
          f"excess={ev20_stats['excess']}%  t={ev20_stats['t']}  p={ev20_stats['p']}")
    print(f"  60d: n_top={ev60_stats['n_top']}  n_other={ev60_stats['n_other']}  "
          f"mean_top={ev60_stats['mean_top']}%  mean_other={ev60_stats['mean_other']}%  "
          f"excess={ev60_stats['excess']}%  t={ev60_stats['t']}  p={ev60_stats['p']}")

    # ------------------------------------------------------------------ #
    # write report
    # ------------------------------------------------------------------ #
    report_body = render(ic_rows, bh_results, ev20_stats, ev60_stats, close, grid_full)
    report_body += verdict_str(ic_rows, bh_results, ev20_stats, ev60_stats)

    out = root / config.load()["storage"]["reports_dir"] / "china-turnover-surge.md"
    out.write_text(report_body + "\n")
    print(f"\n[report] written → {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
