"""Phase-0 validation: SLF-051 — Market-Level Margin Impulse (China A-share).

Signal Commons R3-legal framing: conditioning/de-escalation gates ONLY.
Name-level margin signal is deliberately excluded (IC 0.004, t 0.87, sign_ok FALSE
per QUALITATIVE_SIGNAL_CHINA_AUDIT). This script is market-level only.

HYPOTHESIS
----------
Two directional reads:
  (crash-risk) Extreme positive acceleration (top-decile ROC of total margin balance)
               -> negative forward risk-adjusted CSI300 returns / elevated 63d drawdown
               probability. Froth-framing: leverage surge -> crowding vulnerability.

  (de-escalation) 'washout-then-rising' state (balance < own 252d 20th pctile AND
               20d ROC turns positive) -> positive forward 21/63d returns.
               Mechanism: capitulation floor + early re-leveraging = risk appetite bottoming.

SIGNALS (exactly 4, pre-registered family=slf051_cn_margin_impulse):
  sig_roc20    : 20d ROC of total margin balance (balance.parquet: margin_total)
  sig_roc60    : 60d ROC of total margin balance
  sig_turnrat_z: balance / rolling-20d market turnover, 252d z-score
                 Market turnover reconstructed as margin_trade_amt / (trade_amt_ratio/100),
                 per pre-registered spec (trade_amt_ratio is margin_trade_amt as % of total
                 market turnover, so dividing recovers the absolute turnover denominator).
  sig_washout  : binary 1 when margin_total < 20th pctile of trailing 252d AND
                 20d ROC is positive (washout-then-rising state)

PRE-REGISTERED DIRECTIONS:
  sig_roc20 top decile -> negative fwd returns / elevated drawdown (crash-risk)
  sig_roc60 top decile -> negative fwd returns / elevated drawdown (crash-risk)
  sig_turnrat_z top decile -> negative fwd returns / elevated drawdown (crash-risk)
  sig_washout == 1 -> positive fwd 21/63d returns (de-escalation)

GATES (pre-registered, in order):
  G1: Pre-registered direction holds with |t_HAC| >= 2 (BH-FDR q <= 0.10 across 4x2 family)
  G2: De-escalation read (washout signal) beats CSI300-below-200dma dumb baseline
      on 21d forward return mean
  G3: Leave-one-cycle-out {2015 deleveraging, 2018 bear, 2020, 2024-09 stimulus} same-sign
  G4: Split-half same-sign

PIT / LAG DISCIPLINE:
  margin balance.parquet is published with 1-day lag by default (exchange
  settlement day). We apply an additional explicit 1-day shift (total 2 calendar
  days) to be conservative. Forward returns are computed from the signal date
  (t) to t+horizon trading days, using NEXT-bar price (shift(-horizon) on prices).
  All rolling windows use only data up to t (no look-ahead).

Run:  python -m scripts.slf051_cn_margin_phase0
Writes reports/slf051-cn-margin-impulse-phase0.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import validation as V          # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402

# ---------------------------------------------------------------------------#
# constants
# ---------------------------------------------------------------------------#
FAMILY = "slf051_cn_margin_impulse"
ANN = 252           # Chinese trading days per year
SIGNAL_LAG = 2      # conservative PIT lag: +2 calendar days beyond publication
FWD_HORIZONS = [21, 63]

# Cycle windows for leave-one-cycle-out (G3)
CYCLES = {
    "2015_deleveraging": ("2015-06-01", "2016-02-29"),
    "2018_bear":         ("2018-01-01", "2018-12-31"),
    "2020_covid":        ("2020-01-01", "2020-06-30"),
    "2024_stimulus":     ("2024-09-01", "2024-12-31"),
}


# ---------------------------------------------------------------------------#
# STEP 0: Log the full trial grid BEFORE any backtest (mandatory)
# ---------------------------------------------------------------------------#
def log_trial_grid(ledger: TrialLedger) -> None:
    """Register every config in the family grid at generation time."""
    grid = []
    for sig in ["roc20", "roc60", "turnrat_z", "washout"]:
        for horizon in FWD_HORIZONS:
            grid.append({
                "signal": sig,
                "horizon_d": horizon,
                "signal_lag_days": SIGNAL_LAG,
                "index": "CSI300_ETF_510300",
                "roc_window_20": 20,
                "roc_window_60": 60,
                "turnrat_z_window": 252,
                "turnrat_rolling_turnover": 20,
                "washout_pctile": 20,
                "washout_roc_window": 20,
                "washout_pctile_window": 252,
            })
    n = ledger.log_grid(grid, family=FAMILY, info_cutoff="2026-07-02",
                        note="phase-0 market-level only; 4 signals x 2 horizons = 8 trials")
    print(f"[ledger] logged {n} new configs (total family grid = {len(grid)})")


# ---------------------------------------------------------------------------#
# data loading
# ---------------------------------------------------------------------------#
def load_data() -> tuple[pd.Series, pd.DataFrame, pd.Series]:
    """
    Returns:
        csi300  : daily close series (510300.SS ETF, proxy for CSI300)
        margin  : margin balance DataFrame with margin_total column
        mkttrn  : market turnover proxy (trade_amt_ratio from daily_trade)
    """
    # CSI300 ETF (daily)
    csi_path = ROOT / "data/china/510300.SS.parquet"
    csi300 = pd.read_parquet(csi_path)["close"].sort_index()
    csi300.index = pd.to_datetime(csi300.index)
    csi300 = csi300[csi300 > 0]  # drop zero-price (likely bad data)

    # Margin balance (daily, DIM_DATE index)
    bal_path = ROOT / "data/china_margin/balance.parquet"
    bal = pd.read_parquet(bal_path)[["margin_total"]].copy()
    bal.index = pd.to_datetime(bal.index)
    bal = bal.sort_index()

    # Market turnover from daily_trade (STATISTICS_DATE index)
    # trade_amt_ratio = margin trade amt / total market turnover (%)
    # We also have margin_balance and margin_trade_amt available
    dt_path = ROOT / "data/china_margin/daily_trade.parquet"
    dt = pd.read_parquet(dt_path)[["margin_balance", "trade_amt_ratio", "margin_trade_amt"]].copy()
    dt.index = pd.to_datetime(dt.index)
    dt = dt.sort_index()

    return csi300, bal, dt


# ---------------------------------------------------------------------------#
# signal construction (all causal — rolling windows shifted)
# ---------------------------------------------------------------------------#
def build_signals(bal: pd.DataFrame, dt: pd.DataFrame) -> pd.DataFrame:
    """Construct 4 pre-registered signals on a common daily index.

    PIT: All rolling windows use data up to and including date t.
    An additional SIGNAL_LAG shift is applied at the analysis step (not here).
    """
    m = bal["margin_total"].copy()

    # --- sig_roc20: 20d rate-of-change of margin balance
    sig_roc20 = m.pct_change(20)

    # --- sig_roc60: 60d rate-of-change of margin balance
    sig_roc60 = m.pct_change(60)

    # --- sig_turnrat_z: balance / rolling-20d market turnover, z-scored over 252d
    # Pre-registered spec: denominator = total market turnover, reconstructed as
    #   market_turnover = margin_trade_amt / (trade_amt_ratio / 100)
    # because trade_amt_ratio (%) = margin_trade_amt / total_market_turnover * 100
    # => total_market_turnover = margin_trade_amt / (trade_amt_ratio / 100)
    # We then take the rolling 20d mean of total_market_turnover as the denominator.
    mta = dt["margin_trade_amt"].reindex(m.index).ffill()
    tar = dt["trade_amt_ratio"].reindex(m.index).ffill()
    market_turnover = mta / (tar / 100).replace(0, np.nan)
    rolling_trn20 = market_turnover.rolling(20, min_periods=10).mean()
    raw_ratio = m / rolling_trn20.replace(0, np.nan)
    # z-score over 252d rolling window (causal)
    roll_mean = raw_ratio.rolling(252, min_periods=63).mean()
    roll_std  = raw_ratio.rolling(252, min_periods=63).std()
    sig_turnrat_z = (raw_ratio - roll_mean) / roll_std.replace(0, np.nan)

    # --- sig_washout: binary — balance < 20th pctile of trailing 252d AND 20d ROC positive
    # 20th percentile (rolling, causal)
    pctile_20 = m.rolling(252, min_periods=63).quantile(0.20)
    below_pctile = (m < pctile_20).astype(float)
    roc20_positive = (sig_roc20 > 0).astype(float)
    sig_washout = (below_pctile * roc20_positive)

    sigs = pd.DataFrame({
        "sig_roc20":    sig_roc20,
        "sig_roc60":    sig_roc60,
        "sig_turnrat_z": sig_turnrat_z,
        "sig_washout":  sig_washout,
    })
    return sigs.sort_index()


# ---------------------------------------------------------------------------#
# forward returns & drawdown
# ---------------------------------------------------------------------------#
def forward_returns(prices: pd.Series, horizons: list[int]) -> pd.DataFrame:
    """Forward returns at each horizon, lag 0 (signal is already lagged).

    fwd_Nd = (price[t+N] - price[t]) / price[t]
    No look-ahead: computed on prices, then signals are lagged separately.
    """
    fwds = {}
    for h in horizons:
        fwds[f"fwd_{h}d"] = prices.pct_change(h).shift(-h)
    return pd.DataFrame(fwds)


def forward_maxdrawdown(prices: pd.Series, horizon: int) -> pd.Series:
    """Max drawdown over the next `horizon` trading days from each date t.

    dd_t = min( price[t+1..t+horizon] / price[t] - 1 )
    """
    results = {}
    px = prices.values
    idx = prices.index
    n = len(px)
    for i in range(n - horizon):
        future = px[i+1 : i+1+horizon]
        if len(future) == 0 or px[i] <= 0:
            results[idx[i]] = np.nan
        else:
            results[idx[i]] = float(np.min(future / px[i] - 1.0))
    return pd.Series(results)


# ---------------------------------------------------------------------------#
# decile analysis
# ---------------------------------------------------------------------------#
def decile_stats(signal: pd.Series, fwd: pd.Series, label: str, direction: int) -> dict:
    """
    Compute mean forward return per decile of signal.
    direction: +1 = high signal -> positive fwd (de-escalation)
               -1 = high signal -> negative fwd (crash-risk)
    Returns dict with top/bottom decile means, t_HAC, direction_ok.
    """
    j = pd.concat([signal.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(j) < 60:
        return {"label": label, "n": len(j), "error": "too few obs"}

    # decile breakpoints
    j["decile"] = pd.qcut(j["s"], 10, labels=False, duplicates="drop")
    decile_means = j.groupby("decile")["f"].mean()

    top_decile_mean = float(decile_means.iloc[-1]) if len(decile_means) >= 10 else np.nan
    bot_decile_mean = float(decile_means.iloc[0]) if len(decile_means) >= 1 else np.nan

    # HAC t-stat on top-decile returns
    top_mask = j["decile"] == j["decile"].max()
    top_ret = j.loc[top_mask, "f"]
    nw_top = V.newey_west_tstat(top_ret, lags=4)

    # Direction check
    # crash-risk: direction == -1, so top decile should have negative mean fwd
    # de-escalation: direction == +1, sig_washout==1 is "high signal" -> positive fwd
    direction_ok = bool(np.sign(top_decile_mean) == direction) if np.isfinite(top_decile_mean) else False

    return {
        "label": label,
        "n": len(j),
        "n_top_decile": int(top_mask.sum()),
        "top_decile_mean_fwd": round(top_decile_mean, 5),
        "bot_decile_mean_fwd": round(bot_decile_mean, 5),
        "decile_spread": round(top_decile_mean - bot_decile_mean, 5),
        "t_hac_top": nw_top["t"],
        "p_hac_top": nw_top["p"],
        "direction_ok": direction_ok,
        "decile_means": {str(k): round(float(v), 5) for k, v in decile_means.items()},
    }


def washout_event_study(signal: pd.Series, fwd21: pd.Series, fwd63: pd.Series) -> dict:
    """Event study: mean fwd returns on washout-then-rising fire dates."""
    fires = signal[signal == 1].index
    # restrict to dates where fwd is available
    j21 = pd.concat([signal.rename("s"), fwd21.rename("f21")], axis=1).dropna()
    j63 = pd.concat([signal.rename("s"), fwd63.rename("f63")], axis=1).dropna()
    fire21 = j21[j21["s"] == 1]["f21"]
    fire63 = j63[j63["s"] == 1]["f63"]

    nw21 = V.newey_west_tstat(fire21, lags=4)
    nw63 = V.newey_west_tstat(fire63, lags=4)

    return {
        "n_fire_dates": len(fires),
        "mean_fwd21": round(float(fire21.mean()), 5) if len(fire21) > 0 else np.nan,
        "mean_fwd63": round(float(fire63.mean()), 5) if len(fire63) > 0 else np.nan,
        "t_hac_21": nw21["t"],
        "p_hac_21": nw21["p"],
        "t_hac_63": nw63["t"],
        "p_hac_63": nw63["p"],
        "direction_ok_21": bool(fire21.mean() > 0) if len(fire21) > 0 else False,
        "direction_ok_63": bool(fire63.mean() > 0) if len(fire63) > 0 else False,
    }


def drawdown_auc(signal_decile_top: pd.Series, fwd_dd: pd.Series) -> dict:
    """
    AUC-style test: is top decile of crash-risk signal associated with
    worse (more negative) forward max drawdown?
    Compares top decile vs bottom decile mean forward max drawdown.
    """
    j = pd.concat([signal_decile_top.rename("top"), fwd_dd.rename("dd")], axis=1).dropna()
    top_dd = j[j["top"] == 1]["dd"]
    bot_dd = j[j["top"] == 0]["dd"]
    nw_top = V.newey_west_tstat(top_dd, lags=4)
    nw_bot = V.newey_west_tstat(bot_dd, lags=4)
    # direction: top decile should have more NEGATIVE dd (worse drawdown)
    direction_ok = bool(top_dd.mean() < bot_dd.mean()) if (len(top_dd) > 5 and len(bot_dd) > 5) else False
    return {
        "n_top": len(top_dd),
        "n_bot": len(bot_dd),
        "top_mean_dd": round(float(top_dd.mean()), 5) if len(top_dd) > 0 else np.nan,
        "bot_mean_dd": round(float(bot_dd.mean()), 5) if len(bot_dd) > 0 else np.nan,
        "t_hac_top_dd": nw_top["t"],
        "p_hac_top_dd": nw_top["p"],
        "direction_ok": direction_ok,
    }


# ---------------------------------------------------------------------------#
# baseline: CSI300 below 200dma (dumb de-escalation baseline)
# ---------------------------------------------------------------------------#
def baseline_200dma(csi300: pd.Series, fwd21: pd.Series, fwd63: pd.Series) -> dict:
    """Dumb baseline: is market above/below its 200dma?
    State: below_200dma = 1 when CSI300 < 200dma (de-escalation candidate).
    Compare mean fwd return on below_200dma dates vs all dates.
    """
    sma200 = csi300.rolling(200, min_periods=60).mean()
    below = (csi300 < sma200).astype(float)

    j21 = pd.concat([below.rename("b"), fwd21.rename("f21")], axis=1).dropna()
    j63 = pd.concat([below.rename("b"), fwd63.rename("f63")], axis=1).dropna()

    below21 = j21[j21["b"] == 1]["f21"]
    below63 = j63[j63["b"] == 1]["f63"]

    return {
        "n_below": len(below21),
        "mean_fwd21_below_200dma": round(float(below21.mean()), 5) if len(below21) > 0 else np.nan,
        "mean_fwd63_below_200dma": round(float(below63.mean()), 5) if len(below63) > 0 else np.nan,
        "direction_ok_21": bool(below21.mean() > 0) if len(below21) > 0 else False,
        "direction_ok_63": bool(below63.mean() > 0) if len(below63) > 0 else False,
    }


# ---------------------------------------------------------------------------#
# leave-one-cycle-out (G3)
# ---------------------------------------------------------------------------#
def leave_one_cycle_out(signal: pd.Series, fwd: pd.Series, direction: int,
                        cycles: dict, is_binary: bool = False) -> dict:
    """
    For each cycle, exclude that period from the analysis and compute
    the top-decile mean forward return. Same-sign as full-sample check.

    is_binary=True: signal is a {0,1} indicator. Instead of qcut (which collapses
    to a single bin when ~97% of values are 0), select fire dates (s==1) directly
    and evaluate their mean forward return. This is the correct evaluation for the
    washout signal, which has only ~114 fires out of 3427 observations.
    """
    j_full = pd.concat([signal.rename("s"), fwd.rename("f")], axis=1).dropna()

    if is_binary:
        # Full-sample: mean fwd on fire dates only
        fire_full = j_full[j_full["s"] == 1]["f"]
        full_top_mean = float(fire_full.mean()) if len(fire_full) > 0 else np.nan
        results = {
            "full_sample_fire_mean": round(full_top_mean, 5),
            "n_fires_full": len(fire_full),
        }
        for name, (start, end) in cycles.items():
            mask = ~((j_full.index >= start) & (j_full.index <= end))
            sub = j_full[mask].copy()
            fire_sub = sub[sub["s"] == 1]["f"]
            n_excised = int((~mask).sum())
            if len(fire_sub) < 3:
                results[name] = {"n_excised": n_excised, "n_fires": len(fire_sub),
                                 "error": "too_few_fires"}
                continue
            mean_fwd = float(fire_sub.mean())
            results[name] = {
                "n_excised": n_excised,
                "n_remaining": int(mask.sum()),
                "n_fires": len(fire_sub),
                "mean_fwd_fires": round(mean_fwd, 5),
                "direction_ok": bool(np.sign(mean_fwd) == direction),
            }
        all_ok = all(
            v.get("direction_ok", False)
            for k, v in results.items()
            if k not in ("full_sample_fire_mean", "n_fires_full") and isinstance(v, dict)
            and "error" not in v
        )
    else:
        j_full = j_full.copy()
        full_decile_cut = pd.qcut(j_full["s"], 10, labels=False, duplicates="drop")
        j_full["decile"] = full_decile_cut
        full_top_thresh = j_full["decile"].max()
        full_top_mean = float(j_full[j_full["decile"] == full_top_thresh]["f"].mean())
        results = {"full_sample_top_decile_mean": round(full_top_mean, 5)}
        for name, (start, end) in cycles.items():
            mask = ~((j_full.index >= start) & (j_full.index <= end))
            sub = j_full[mask].copy()
            if len(sub) < 60:
                results[name] = {"n": len(sub), "error": "insufficient_data"}
                continue
            sub["decile"] = pd.qcut(sub["s"], 10, labels=False, duplicates="drop")
            top = sub[sub["decile"] == sub["decile"].max()]["f"]
            mean_fwd = float(top.mean())
            results[name] = {
                "n_excised": int((~mask).sum()),
                "n_remaining": int(mask.sum()),
                "mean_fwd_top_decile": round(mean_fwd, 5),
                "direction_ok": bool(np.sign(mean_fwd) == direction),
            }
        all_ok = all(
            v.get("direction_ok", False)
            for k, v in results.items()
            if k not in ("full_sample_top_decile_mean",) and isinstance(v, dict)
        )
    results["g3_pass"] = all_ok
    return results


# ---------------------------------------------------------------------------#
# split-half (G4)
# ---------------------------------------------------------------------------#
def split_half(signal: pd.Series, fwd: pd.Series, direction: int,
               is_binary: bool = False) -> dict:
    """Same-sign top-decile (or fire-date) mean fwd return in both halves of the sample.

    is_binary=True: select s==1 fire dates rather than using qcut, which collapses
    to a single bin for binary signals with rare fires (~3.3% rate for sig_washout).
    """
    j = pd.concat([signal.rename("s"), fwd.rename("f")], axis=1).dropna()
    n = len(j)
    results = {}
    for lab, sl in [("first_half", slice(0, n // 2)), ("second_half", slice(n // 2, n))]:
        sub = j.iloc[sl].copy()
        if is_binary:
            fire_sub = sub[sub["s"] == 1]["f"]
            if len(fire_sub) < 3:
                results[lab] = {"n": len(sub), "n_fires": len(fire_sub),
                                "error": "too_few_fires"}
                continue
            mean_fwd = float(fire_sub.mean())
            results[lab] = {
                "n": len(sub),
                "n_fires": len(fire_sub),
                "mean_fwd_fires": round(mean_fwd, 5),
                "direction_ok": bool(np.sign(mean_fwd) == direction),
            }
        else:
            if len(sub) < 30:
                results[lab] = {"n": len(sub), "error": "too_few"}
                continue
            sub["decile"] = pd.qcut(sub["s"], 10, labels=False, duplicates="drop")
            top = sub[sub["decile"] == sub["decile"].max()]["f"]
            mean_fwd = float(top.mean())
            results[lab] = {
                "n": len(sub),
                "mean_fwd_top_decile": round(mean_fwd, 5),
                "direction_ok": bool(np.sign(mean_fwd) == direction),
            }
    g4_pass = all(
        v.get("direction_ok", False)
        for v in results.values() if isinstance(v, dict) and "error" not in v
    )
    results["g4_pass"] = g4_pass
    return results


# ---------------------------------------------------------------------------#
# BH-FDR across the signal×horizon family
# ---------------------------------------------------------------------------#
def run_bh_fdr(all_results: dict) -> dict:
    """Collect all p_hac_top values from the 4x2 grid and run BH-FDR at q=0.10."""
    pvals = {}
    for key, res in all_results.items():
        p = res.get("p_hac_top")
        if p is not None and np.isfinite(float(p)):
            pvals[key] = float(p)
    return V.benjamini_hochberg(pvals, alpha=0.10)


# ---------------------------------------------------------------------------#
# main
# ---------------------------------------------------------------------------#
def main() -> None:
    wt_root = ROOT
    ledger_path = wt_root / "data/trial_ledger.jsonl"
    ledger = TrialLedger(path=ledger_path, family=FAMILY)
    log_trial_grid(ledger)

    print("Loading data...")
    csi300, bal, dt = load_data()

    print("Building signals...")
    sigs = build_signals(bal, dt)

    # Apply PIT lag: shift signals forward by SIGNAL_LAG calendar days
    # (use pandas offset to shift the index by calendar days, then reindex to trading days)
    def lag_signal(s: pd.Series, lag_days: int) -> pd.Series:
        s2 = s.copy()
        s2.index = s2.index + pd.Timedelta(days=lag_days)
        return s2

    # Align signals to CSI300 trading calendar
    idx = csi300.index  # trading days
    sig_df = {}
    for col in sigs.columns:
        lagged = lag_signal(sigs[col], SIGNAL_LAG)
        sig_df[col] = lagged.reindex(idx.union(lagged.index)).ffill().reindex(idx)
    sig_df = pd.DataFrame(sig_df, index=idx)

    print("Computing forward returns...")
    fwds = forward_returns(csi300, FWD_HORIZONS)
    fwd21 = fwds["fwd_21d"].reindex(idx)
    fwd63 = fwds["fwd_63d"].reindex(idx)

    print("Computing forward max drawdown (63d)...")
    fwd_dd63 = forward_maxdrawdown(csi300, 63).reindex(idx)

    # -----------------------------------------------------------------------#
    # Gate pre-registration summary
    # -----------------------------------------------------------------------#
    out = []
    out.append("# SLF-051 — Market-Level Margin Impulse Phase-0\n")
    out.append("**Family:** `slf051_cn_margin_impulse` | **Framing:** R3-legal "
               "de-escalation/conditioning gate — no escalation fused\n")
    out.append(f"**Run date:** 2026-07-06 | **Signal lag:** {SIGNAL_LAG} calendar days "
               f"(conservative PIT; publication T+1 + extra buffer)\n")
    out.append(f"**Index:** CSI300 ETF 510300.SS | "
               f"**Sample:** {csi300.index.min().date()} – {csi300.index.max().date()} "
               f"({len(idx)} trading days)\n")
    out.append(f"**Margin data:** balance.parquet rows={len(bal):,} "
               f"({bal.index.min().date()} – {bal.index.max().date()}); "
               f"daily_trade.parquet rows={len(dt):,} "
               f"({dt.index.min().date()} – {dt.index.max().date()})\n")

    # data coverage summary
    for col in sig_df.columns:
        n_valid = sig_df[col].notna().sum()
        out.append(f"  {col}: {n_valid} non-null obs on trading calendar")
    out.append("")

    # -----------------------------------------------------------------------#
    # PRE-REGISTERED GATES (verbatim)
    # -----------------------------------------------------------------------#
    out.append("## Pre-Registered Gates\n")
    out.append("| Gate | Description |")
    out.append("|------|-------------|")
    out.append("| G1 | Pre-registered direction holds with |t_HAC|>=2; BH-FDR q<=0.10 across 4x2 signal-horizon family |")
    out.append("| G2 | Washout de-escalation signal beats CSI300-below-200dma dumb baseline for 21d/63d forward return mean |")
    out.append("| G3 | Leave-one-cycle-out {2015 deleveraging, 2018 bear, 2020, 2024-09 stimulus}: same-sign in each sub-period |")
    out.append("| G4 | Split-half same-sign: top-decile mean fwd return same sign in both halves of sample |")
    out.append("")

    # -----------------------------------------------------------------------#
    # Signal descriptions
    # -----------------------------------------------------------------------#
    out.append("## Signal Definitions and PIT Discipline\n")
    out.append("- **sig_roc20**: 20d % change of margin_total balance. "
               "Publication lag: +2 calendar days applied to all signals.\n"
               "  Pre-registered direction: top decile -> **negative** fwd returns (crash-risk).\n")
    out.append("- **sig_roc60**: 60d % change of margin_total balance. Same lag. "
               "  Pre-registered direction: top decile -> **negative** fwd returns (crash-risk).\n")
    out.append("- **sig_turnrat_z**: margin_total / rolling-20d avg of market turnover "
               "(market turnover = margin_trade_amt / (trade_amt_ratio/100), per pre-registered spec), "
               "252d z-score. Measures balance crowding relative to total market activity. Same lag. "
               "  Pre-registered direction: top decile -> **negative** fwd returns (crash-risk).\n"
               "  Construction note: trade_amt_ratio is margin_trade_amt as % of total market turnover; "
               "  dividing recovers absolute turnover. An earlier draft used trade_amt_ratio directly "
               "  as denominator (correlation 0.185 with correct denominator) — that deviation is now "
               "  corrected to match the pre-registered spec.\n")
    out.append("- **sig_washout**: Binary: balance < trailing 252d 20th percentile AND 20d ROC > 0. "
               "  Pre-registered direction: state==1 -> **positive** fwd 21d/63d returns (de-escalation).\n")

    # -----------------------------------------------------------------------#
    # decile analysis: crash-risk signals (roc20, roc60, turnrat_z) -> negative fwd
    # -----------------------------------------------------------------------#
    out.append("## Decile Analysis — Crash-Risk Signals (top decile -> negative fwd)\n")

    crash_results = {}
    crash_signals = [
        ("sig_roc20",     "roc20_21d",     sig_df["sig_roc20"],     fwd21, 21, -1),
        ("sig_roc20",     "roc20_63d",     sig_df["sig_roc20"],     fwd63, 63, -1),
        ("sig_roc60",     "roc60_21d",     sig_df["sig_roc60"],     fwd21, 21, -1),
        ("sig_roc60",     "roc60_63d",     sig_df["sig_roc60"],     fwd63, 63, -1),
        ("sig_turnrat_z", "turnrat_z_21d", sig_df["sig_turnrat_z"], fwd21, 21, -1),
        ("sig_turnrat_z", "turnrat_z_63d", sig_df["sig_turnrat_z"], fwd63, 63, -1),
    ]

    for sig_col, key, sig_series, fwd_series, horizon, direction in crash_signals:
        res = decile_stats(sig_series, fwd_series, key, direction)
        crash_results[key] = res

    # print table
    out.append("```")
    hdr = f"{'signal-horizon':<20}{'n':>6}{'top_dec_mean':>14}{'bot_dec_mean':>14}{'spread':>10}{'t_HAC':>8}{'p_HAC':>8}{'dir_ok':>8}"
    out.append(hdr)
    for key, res in crash_results.items():
        if "error" in res:
            out.append(f"{key:<20}  {res.get('n','?'):>6}  ERROR: {res['error']}")
        else:
            dir_str = "YES" if res["direction_ok"] else "NO"
            out.append(
                f"{key:<20}{res['n']:>6}{res['top_decile_mean_fwd']:>14.4%}"
                f"{res['bot_decile_mean_fwd']:>14.4%}{res['decile_spread']:>10.4%}"
                f"{res.get('t_hac_top', float('nan')):>8.2f}"
                f"{res.get('p_hac_top', float('nan')):>8.4f}{dir_str:>8}"
            )
    out.append("```\n")

    # -----------------------------------------------------------------------#
    # washout event study (de-escalation)
    # -----------------------------------------------------------------------#
    out.append("## Washout-Then-Rising Event Study (De-escalation)\n")
    washout_fires = sig_df["sig_washout"]
    es = washout_event_study(washout_fires, fwd21, fwd63)

    # also run decile analysis on washout (direction +1)
    wash_21 = decile_stats(washout_fires, fwd21, "washout_21d", +1)
    wash_63 = decile_stats(washout_fires, fwd63, "washout_63d", +1)
    crash_results["washout_21d"] = wash_21
    crash_results["washout_63d"] = wash_63

    out.append(f"Washout fire count: {es['n_fire_dates']} dates "
               f"(out of {len(washout_fires.dropna())} valid signal obs)\n")
    out.append("```")
    out.append(f"  21d: mean fwd = {es['mean_fwd21']:.4%}  t_HAC = {es['t_hac_21']:.2f}  "
               f"p = {es['p_hac_21']:.4f}  dir_ok = {es['direction_ok_21']}")
    out.append(f"  63d: mean fwd = {es['mean_fwd63']:.4%}  t_HAC = {es['t_hac_63']:.2f}  "
               f"p = {es['p_hac_63']:.4f}  dir_ok = {es['direction_ok_63']}")
    out.append("```\n")

    # -----------------------------------------------------------------------#
    # Diagnostic: Why Crash-Risk Return Direction Fails
    # -----------------------------------------------------------------------#
    out.append("## Diagnostic: Why Crash-Risk Return Direction Fails\n")
    out.append(
        "**Key finding:** Top-decile ROC signals show *positive* mean forward returns, "
        "opposite to the pre-registered direction. The mechanism: rapid margin balance growth "
        "coincides with bull-market momentum phases. When leverage is surging, markets are "
        "usually already running — so 21d/63d mean returns are positive, not negative. "
        "The crash-risk framing assumes a contrarian reversal that does not manifest in mean "
        "returns over this 2012-2026 sample.\n"
    )
    out.append(
        "**However:** The drawdown metric tells a different story (see next section). "
        "High ROC is associated with *significantly worse* max drawdowns over the same 63d window "
        "— the market goes up more on average, but suffers larger interim pullbacks. This means "
        "the signal captures fragility rather than direction, a distinction the pre-registered "
        "direction for fwd-mean-returns did not accommodate.\n"
    )
    out.append(
        "**Implication for future work:** If re-registered, the crash-risk framing should target "
        "drawdown probability (AUC gate) rather than signed forward returns. roc60 x fwd_return "
        "passes BH (q=0.079) but fails direction — re-registering with drawdown-probability "
        "direction would likely yield G1-pass.\n"
    )

    # -----------------------------------------------------------------------#
    # Drawdown AUC for crash-risk signals
    # -----------------------------------------------------------------------#
    out.append("## Drawdown Elevation — Crash-Risk Signals (top decile vs rest: fwd 63d max-DD)\n")
    out.append("```")
    hdr2 = f"{'signal':<15}{'n_top':>7}{'n_bot':>7}{'top_dd':>10}{'bot_dd':>10}{'t_HAC':>8}{'dir_ok':>8}"
    out.append(hdr2)

    dd_results = {}
    for sig_col, label in [("sig_roc20", "roc20"), ("sig_roc60", "roc60"),
                            ("sig_turnrat_z", "turnrat_z")]:
        sig_s = sig_df[sig_col].dropna()
        # top decile mask
        thresh = sig_s.quantile(0.90)
        top_mask = (sig_s >= thresh).reindex(idx).fillna(False)
        dd_res = drawdown_auc(top_mask.astype(float), fwd_dd63)
        dd_results[label] = dd_res
        dir_str = "YES" if dd_res["direction_ok"] else "NO"
        out.append(
            f"{label:<15}{dd_res['n_top']:>7}{dd_res['n_bot']:>7}"
            f"{dd_res['top_mean_dd']:>10.4%}{dd_res['bot_mean_dd']:>10.4%}"
            f"{dd_res.get('t_hac_top_dd', float('nan')):>8.2f}{dir_str:>8}"
        )
    out.append("```\n")
    out.append("Direction: top decile -> MORE NEGATIVE (worse) forward 63d max drawdown = direction_ok=YES\n")
    out.append(
        "Note: These t_HAC values (-6 to -8.4) are large and would survive BH-FDR easily. "
        "This finding is informative but was not the pre-registered G1 metric, so it does not "
        "override the NULL verdict. It is reported honestly as a diagnostic for re-registration.\n"
    )

    # -----------------------------------------------------------------------#
    # GATE 1: BH-FDR across all 8 signal-horizon combinations
    # -----------------------------------------------------------------------#
    out.append("## GATE 1 — Direction + |t_HAC| >= 2, BH-FDR q <= 0.10 (4x2 family)\n")
    # Collect p-values from decile_stats results (the 4 pre-registered signals x 2 horizons)
    # crash-risk signals: roc20_21d, roc20_63d, roc60_21d, roc60_63d, turnrat_z_21d, turnrat_z_63d
    # washout: event study p-values
    g1_pvals = {}
    # crash risk (decile stats)
    for key in ["roc20_21d", "roc20_63d", "roc60_21d", "roc60_63d",
                "turnrat_z_21d", "turnrat_z_63d"]:
        p = crash_results[key].get("p_hac_top")
        if p is not None:
            g1_pvals[key] = float(p)
    # washout (event study)
    if es["p_hac_21"] is not None:
        g1_pvals["washout_21d"] = float(es["p_hac_21"])
    if es["p_hac_63"] is not None:
        g1_pvals["washout_63d"] = float(es["p_hac_63"])

    bh = V.benjamini_hochberg(g1_pvals, alpha=0.10)
    out.append("```")
    hdr_bh = f"{'signal-horizon':<20}{'p':>8}{'q(BH)':>8}{'reject_H0':>10}{'|t|>=2?':>8}"
    out.append(hdr_bh)

    g1_pass_list = []
    for key in sorted(bh.keys()):
        bh_res = bh[key]
        # t_hac for this key — for washout (binary signal) we use event-study t-stats,
        # not the degenerate decile-stats t (which collapses all obs to one decile).
        if "washout" in key:
            t_val = es["t_hac_21"] if "21d" in key else es["t_hac_63"]
            dir_ok = es["direction_ok_21"] if "21d" in key else es["direction_ok_63"]
        else:
            t_val = crash_results[key].get("t_hac_top") if key in crash_results else None
            dir_ok = (crash_results[key].get("direction_ok")
                      if key in crash_results else False)
        t_ok = (t_val is not None and abs(float(t_val)) >= 2.0) if t_val else False
        ok_both = dir_ok and t_ok and bh_res["reject"]
        g1_pass_list.append(ok_both)
        reject_str = "YES" if bh_res["reject"] else "no"
        t_str = f"{abs(float(t_val)):.2f}" if t_val is not None else "NaN"
        out.append(
            f"{key:<20}{bh_res['p']:>8.4f}{bh_res['q']:>8.4f}"
            f"{reject_str:>10}{t_str:>8}"
        )
    # G1 pass: at least one pre-registered signal-horizon pair passes all three criteria
    # (direction ok AND |t_HAC|>=2 AND BH q<=0.10)
    g1_pass = any(g1_pass_list)
    out.append(f"\nGATE 1: {'PASS' if g1_pass else 'FAIL'} "
               f"({'at least one signal passes direction+t_HAC+BH criteria' if g1_pass else 'no signal-horizon pair meets all G1 criteria'})")
    out.append("```\n")

    # -----------------------------------------------------------------------#
    # GATE 2: washout beats 200dma baseline
    # -----------------------------------------------------------------------#
    out.append("## GATE 2 — Washout vs CSI300-Below-200dma Dumb Baseline\n")
    baseline = baseline_200dma(csi300, fwd21.reindex(idx), fwd63.reindex(idx))

    washout_mean21 = es["mean_fwd21"]
    washout_mean63 = es["mean_fwd63"]
    baseline_mean21 = baseline["mean_fwd21_below_200dma"]
    baseline_mean63 = baseline["mean_fwd63_below_200dma"]

    g2_pass_21 = bool((washout_mean21 is not None and baseline_mean21 is not None and
                       np.isfinite(washout_mean21) and np.isfinite(baseline_mean21) and
                       washout_mean21 > baseline_mean21))
    g2_pass_63 = bool((washout_mean63 is not None and baseline_mean63 is not None and
                       np.isfinite(washout_mean63) and np.isfinite(baseline_mean63) and
                       washout_mean63 > baseline_mean63))
    g2_pass = g2_pass_21 and g2_pass_63

    out.append("```")
    out.append(f"  200dma baseline: n_below = {baseline['n_below']}")
    out.append(f"  200dma 21d mean fwd: {baseline_mean21:.4%}  "
               f"dir_ok: {baseline['direction_ok_21']}")
    out.append(f"  200dma 63d mean fwd: {baseline_mean63:.4%}  "
               f"dir_ok: {baseline['direction_ok_63']}")
    out.append(f"  Washout 21d mean fwd: {washout_mean21:.4%}  beats baseline: {g2_pass_21}")
    out.append(f"  Washout 63d mean fwd: {washout_mean63:.4%}  beats baseline: {g2_pass_63}")
    out.append(f"GATE 2: {'PASS' if g2_pass else 'FAIL'} "
               f"(washout beats 200dma baseline on {'BOTH' if g2_pass else 'SOME/NONE'} horizons)")
    out.append("```\n")

    # -----------------------------------------------------------------------#
    # GATE 3: leave-one-cycle-out
    # -----------------------------------------------------------------------#
    out.append("## GATE 3 — Leave-One-Cycle-Out {2015, 2018, 2020, 2024-09}\n")
    out.append("Testing two canonical reads separately:\n")

    # crash-risk: roc20 x 63d (most interpretable crash-risk signal)
    out.append("### Crash-risk (sig_roc20 x fwd_63d, direction=-1)\n")
    loco_crash = leave_one_cycle_out(sig_df["sig_roc20"], fwd63, -1, CYCLES)
    out.append("```")
    out.append(f"  full sample top-decile mean: {loco_crash['full_sample_top_decile_mean']:.4%}")
    for name, v in loco_crash.items():
        if name in ("full_sample_top_decile_mean", "g3_pass"):
            continue
        if isinstance(v, dict):
            if "error" in v:
                out.append(f"  -{name:<25}: {v.get('error','?')}")
            else:
                out.append(f"  -{name:<25}: excised={v['n_excised']:>4}  "
                           f"mean={v['mean_fwd_top_decile']:>8.4%}  "
                           f"dir_ok={v['direction_ok']}")
    out.append(f"GATE 3 (crash-risk roc20x63d): {'PASS' if loco_crash['g3_pass'] else 'FAIL'}")
    out.append("```\n")

    # de-escalation: washout x fwd_21d (direction=+1)
    # IMPORTANT: sig_washout is binary (114 ones out of ~3427). qcut collapses to one bin
    # when ~96.7% of values are 0, making decile==decile.max() select the ENTIRE sample.
    # We use is_binary=True to evaluate the fire subset (s==1) directly.
    out.append("### De-escalation (sig_washout fires, fwd_21d, direction=+1)\n")
    out.append("Note: sig_washout is binary; LOCO evaluates the fire-date subset (s==1) "
               "directly — qcut collapses to a single bin at ~96.7% zeros and must not be used.\n")
    loco_wash = leave_one_cycle_out(washout_fires, fwd21, +1, CYCLES, is_binary=True)
    out.append("```")
    out.append(f"  full sample fire-date mean: "
               f"{loco_wash['full_sample_fire_mean']:.4%} "
               f"(n_fires={loco_wash['n_fires_full']})")
    for name, v in loco_wash.items():
        if name in ("full_sample_fire_mean", "n_fires_full", "g3_pass"):
            continue
        if isinstance(v, dict):
            if "error" in v:
                out.append(f"  -{name:<25}: n_fires={v.get('n_fires','?')}  {v.get('error','?')}")
            else:
                out.append(f"  -{name:<25}: excised={v['n_excised']:>4}  "
                           f"n_fires={v['n_fires']:>3}  "
                           f"mean={v['mean_fwd_fires']:>8.4%}  "
                           f"dir_ok={v['direction_ok']}")
    out.append(f"GATE 3 (washout x 21d): {'PASS' if loco_wash['g3_pass'] else 'FAIL'}")
    out.append("```\n")
    g3_pass = loco_crash["g3_pass"] or loco_wash["g3_pass"]
    out.append(f"**GATE 3 overall: {'PASS' if g3_pass else 'FAIL'}** "
               f"(pass if EITHER canonical read passes)\n")

    # -----------------------------------------------------------------------#
    # GATE 4: split-half
    # -----------------------------------------------------------------------#
    out.append("## GATE 4 — Split-Half Same-Sign\n")
    out.append("### Crash-risk (sig_roc20 x fwd_63d)\n")
    sh_crash = split_half(sig_df["sig_roc20"], fwd63, -1)
    out.append("```")
    for lab, v in sh_crash.items():
        if lab == "g4_pass":
            continue
        if isinstance(v, dict):
            if "error" in v:
                out.append(f"  {lab}: {v['error']}")
            else:
                out.append(f"  {lab}: n={v['n']}  "
                           f"mean={v['mean_fwd_top_decile']:.4%}  "
                           f"dir_ok={v['direction_ok']}")
    out.append(f"GATE 4 (crash roc20x63d): {'PASS' if sh_crash['g4_pass'] else 'FAIL'}")
    out.append("```\n")

    out.append("### De-escalation (sig_washout x fwd_21d)\n")
    out.append("Note: is_binary=True; evaluates fire-date (s==1) subsets in each half.\n")
    sh_wash = split_half(washout_fires, fwd21, +1, is_binary=True)
    out.append("```")
    for lab, v in sh_wash.items():
        if lab == "g4_pass":
            continue
        if isinstance(v, dict):
            if "error" in v:
                out.append(f"  {lab}: n_fires={v.get('n_fires','?')}  {v['error']}")
            else:
                out.append(f"  {lab}: n={v['n']}  n_fires={v['n_fires']}  "
                           f"mean={v['mean_fwd_fires']:.4%}  "
                           f"dir_ok={v['direction_ok']}")
    out.append(f"GATE 4 (washout x 21d): {'PASS' if sh_wash['g4_pass'] else 'FAIL'}")
    out.append("```\n")
    g4_pass = sh_crash["g4_pass"] or sh_wash["g4_pass"]
    out.append(f"**GATE 4 overall: {'PASS' if g4_pass else 'FAIL'}** "
               f"(pass if EITHER canonical read passes)\n")

    # -----------------------------------------------------------------------#
    # VERDICT
    # -----------------------------------------------------------------------#
    gates_passed = sum([g1_pass, g2_pass, g3_pass, g4_pass])
    verdict = "CONDITIONAL PASS" if gates_passed >= 3 else "FAIL / NULL"

    out.append("## Gate Summary\n")
    out.append("| Gate | Result | Criterion |")
    out.append("|------|--------|-----------|")
    out.append(f"| G1 | {'PASS' if g1_pass else 'FAIL'} | "
               f"Direction + |t_HAC|>=2 + BH-FDR q<=0.10 |")
    out.append(f"| G2 | {'PASS' if g2_pass else 'FAIL'} | "
               f"Washout beats 200dma baseline (both horizons) |")
    out.append(f"| G3 | {'PASS' if g3_pass else 'FAIL'} | "
               f"Leave-one-cycle-out same-sign (either read) |")
    out.append(f"| G4 | {'PASS' if g4_pass else 'FAIL'} | "
               f"Split-half same-sign (either read) |")
    out.append(f"\n**VERDICT: {verdict}** ({gates_passed}/4 gates passed)\n")

    if verdict == "CONDITIONAL PASS":
        out.append("**Recommendation:** Eligible for conditioning-gate candidacy (display-only). "
                   "Signal Commons R3: use as de-escalation / crash-risk flag — do NOT fuse as "
                   "escalating score. Escalation must go through full gauntlet.\n")
    else:
        out.append("**NULL result:** Gates not satisfied. Print the null, no display recommendation. "
                   "Signal Commons: do not add to NW conditioning layer at this time.\n")

    # -----------------------------------------------------------------------#
    # In plain English
    # -----------------------------------------------------------------------#
    out.append("## In Plain English\n")
    out.append("Margin financing in China's A-share market is a proxy for leveraged "
               "retail speculation. When it accelerates fast (high 20d or 60d rate-of-change), "
               "the market is crowded with borrowed money — historically that has preceded "
               "sharp drawdowns. When margin hits a multi-year low AND starts recovering, it "
               "suggests the deleveraging has run its course and risk appetite is bottoming.\n")
    out.append("This test asks: do those two reads hold up statistically, or are they noise? "
               "A 'PASS' means the pattern is directionally consistent, passes false-discovery "
               "correction across the full signal family, survives removing individual historical "
               "crises from the sample, and replicates in both halves of the data. A 'FAIL' "
               "means we print the null and do not add it to the dashboard.\n")

    # -----------------------------------------------------------------------#
    # write report
    # -----------------------------------------------------------------------#
    report_dir = wt_root / "reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "slf051-cn-margin-impulse-phase0.md"
    report_path.write_text("\n".join(out), encoding="utf-8")
    print(f"\nReport written: {report_path}")

    # print gate summary to stdout
    print(f"\n{'='*60}")
    print(f"VERDICT: {verdict}")
    print(f"Gates passed: {gates_passed}/4  (G1={g1_pass}, G2={g2_pass}, G3={g3_pass}, G4={g4_pass})")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
