"""BTC Re-entry Trigger Evaluation — Override-Registry Program W4

PRE-REGISTERED QUALIFYING BAR (stated before any results are computed):
  A trigger qualifies for W4 tranche duty if ALL of:
    1. hit_rate_180d >= 70%  (fraction of fires where fwd return at +180d is positive)
    2. MAE_worse_than_neg25_within_90d <= 30%  (fraction of fires with max drawdown < -25%
       within 90 calendar days after firing)
    3. n >= 4 fires (minimum signal authority)

CAVEATS (pre-stated):
  - bottom_pressure composite has ~16 hand-set DOF (~8 conditions × weight + threshold parameters)
    → risk of in-sample curve-fit; treat qualifying results as hypothesis-generating
  - Overlapping 180d forward windows inflate apparent sample size; independent-episode counts
    (fires > 180d apart from the prior fire) are the honest denominator
  - MVRV-Z fires: the "days above 0" cooldown prevents daily re-fires, but the underlying
    rolling-window z-score uses overlapping data → effective N is much smaller than bar count
  - n=3–6 for most triggers: any qualification is weak and should not override judgment

Usage:
    import sys
    sys.path.insert(0, '/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/zen-volhard-77003f')
    from research.entry_timing.btc_trigger_eval import run_all
    results = run_all()
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd
from datetime import timedelta

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _nearest_trading_day(close: pd.Series, target_date: pd.Timestamp) -> pd.Timestamp | None:
    """Return the closest available trading day >= target_date within 5 days."""
    idx = close.index
    candidates = idx[idx >= target_date]
    if len(candidates) == 0:
        return None
    # also try <=5d past
    candidates2 = idx[(idx >= target_date - timedelta(days=5)) & (idx <= target_date + timedelta(days=5))]
    if len(candidates2) == 0:
        return None
    diffs = np.abs((candidates2 - target_date).total_seconds().values)
    return candidates2[int(diffs.argmin())]


def _fwd_return(close: pd.Series, fire: pd.Timestamp, days: int):
    target = fire + timedelta(days=days)
    t = _nearest_trading_day(close, target)
    if t is None or t <= fire:
        return np.nan
    return close[t] / close[fire] - 1


def _mae_90d(close: pd.Series, fire: pd.Timestamp) -> float:
    """Max adverse excursion as a fraction (negative = loss) within 90 calendar days."""
    end = fire + timedelta(days=90)
    window = close[(close.index > fire) & (close.index <= end)]
    if len(window) == 0:
        return np.nan
    min_close = window.min()
    return min_close / close[fire] - 1


def _independent_episodes(fire_dates: list[pd.Timestamp], gap_days: int = 180) -> int:
    """Count fires that are >gap_days apart from the immediately preceding fire."""
    if not fire_dates:
        return 0
    count = 1
    prev = fire_dates[0]
    for d in fire_dates[1:]:
        if (d - prev).days > gap_days:
            count += 1
            prev = d
    return count


def _compute_metrics(close: pd.Series, fire_dates: list[pd.Timestamp],
                     momentum_state: pd.Series) -> dict:
    """Compute all W4 metrics for a list of fire dates."""
    if not fire_dates:
        return {"n": 0, "fire_dates": [], "independent_episodes": 0}

    fwd90, fwd180, fwd365 = [], [], []
    mae_list = []
    bear_days_to_bottom, bear_pct_below = [], []

    for f in fire_dates:
        r90 = _fwd_return(close, f, 90)
        r180 = _fwd_return(close, f, 180)
        r365 = _fwd_return(close, f, 365)
        fwd90.append(r90)
        fwd180.append(r180)
        fwd365.append(r365)

        mae = _mae_90d(close, f)
        mae_list.append(mae)

        # bear-phase fire analysis
        ms = momentum_state.get(f, "neutral") if isinstance(momentum_state, dict) else \
             (momentum_state[f] if f in momentum_state.index else "neutral")
        if ms == "bear":
            end_look = f + timedelta(days=365)
            window = close[(close.index > f) & (close.index <= end_look)]
            if len(window) > 0:
                min_close = window.min()
                min_date = window.idxmin()
                bear_days_to_bottom.append((min_date - f).days)
                bear_pct_below.append(min_close / close[f] - 1)

    fwd90 = np.array(fwd90, dtype=float)
    fwd180 = np.array(fwd180, dtype=float)
    fwd365 = np.array(fwd365, dtype=float)
    mae_arr = np.array(mae_list, dtype=float)

    valid90  = fwd90[~np.isnan(fwd90)]
    valid180 = fwd180[~np.isnan(fwd180)]
    valid365 = fwd365[~np.isnan(fwd365)]
    valid_mae = mae_arr[~np.isnan(mae_arr)]

    n = len(fire_dates)
    ind_ep = _independent_episodes(fire_dates)

    def _safe(arr, fn):
        return fn(arr) if len(arr) > 0 else np.nan

    return {
        "n": n,
        "independent_episodes": ind_ep,
        "fire_dates": [str(d.date()) for d in fire_dates],
        # forward returns
        "fwd_90d_median":  _safe(valid90,  np.median),
        "fwd_90d_mean":    _safe(valid90,  np.mean),
        "hit_rate_90d":    _safe(valid90,  lambda a: (a > 0).mean()),
        "fwd_180d_median": _safe(valid180, np.median),
        "fwd_180d_mean":   _safe(valid180, np.mean),
        "hit_rate_180d":   _safe(valid180, lambda a: (a > 0).mean()),
        "fwd_365d_median": _safe(valid365, np.median),
        "fwd_365d_mean":   _safe(valid365, np.mean),
        "hit_rate_365d":   _safe(valid365, lambda a: (a > 0).mean()),
        # MAE
        "mae_median_pct":       _safe(valid_mae, lambda a: np.median(a) * 100),
        "pct_mae_worse_neg15":  _safe(valid_mae, lambda a: (a < -0.15).mean()),
        "pct_mae_worse_neg25":  _safe(valid_mae, lambda a: (a < -0.25).mean()),
        # bear-phase bottom timing
        "bear_fires": len(bear_days_to_bottom),
        "bear_median_days_to_bottom": np.median(bear_days_to_bottom) if bear_days_to_bottom else np.nan,
        "bear_median_pct_below":      np.median(bear_pct_below) * 100 if bear_pct_below else np.nan,
    }


# ---------------------------------------------------------------------------
# trigger (a) — MVRV-Z first cross below 0 after >=90 days above
# ---------------------------------------------------------------------------

def trigger_a_mvrv_cross(sig: pd.DataFrame) -> list[pd.Timestamp]:
    """First day mvrv_z < 0 after >= 90 consecutive days where mvrv_z >= 0."""
    mz = sig["mvrv_z"].dropna()
    fires = []
    above_streak = 0
    min_streak = 90

    for date, val in mz.items():
        if val >= 0:
            above_streak += 1
        else:
            if above_streak >= min_streak:
                fires.append(date)
            above_streak = 0  # reset regardless (we're now below)

    return fires


# ---------------------------------------------------------------------------
# trigger (b) — weekly close reclaiming 20w MA after >=60 days below
# ---------------------------------------------------------------------------

def trigger_b_20w_reclaim(sig: pd.DataFrame) -> list[pd.Timestamp]:
    """Weekly close > 20w SMA, having been below for >= 60 calendar days.
    Non-repainting: uses completed weeks only (shift by 1 week on the weekly series).
    Maps back to daily using the daily close index.
    """
    close = sig["close"]

    # Weekly close: last price of the week ending on Friday (or nearest day)
    weekly = close.resample("W-FRI").last().dropna()

    # 20-week SMA
    w20 = weekly.rolling(20, min_periods=10).mean()

    # shift(1) on weekly = previous completed week (non-repainting)
    weekly_s = weekly.shift(1)
    w20_s = w20.shift(1)

    # Determine when weekly close is above/below w20
    above_w = (weekly_s > w20_s)

    # Track fires on weekly basis
    weekly_fires = []
    below_since = None  # first date below the 20w MA (calendar date)
    min_days_below = 60

    for date, is_above in above_w.items():
        if pd.isna(is_above):
            continue
        if not is_above:
            if below_since is None:
                below_since = date
        else:
            if below_since is not None:
                days_below = (date - below_since).days
                if days_below >= min_days_below:
                    weekly_fires.append(date)
            below_since = None

    # Map weekly fire dates to last available daily trading day on or before that week-end
    daily_fires = []
    daily_idx = close.index
    for wdate in weekly_fires:
        # Find last trading day <= wdate
        mask = daily_idx[daily_idx <= wdate]
        if len(mask) > 0:
            daily_fires.append(mask[-1])

    return daily_fires


# ---------------------------------------------------------------------------
# trigger (c) — bottom_pressure threshold cross after >=20d below
# ---------------------------------------------------------------------------

def trigger_c_bottom_pressure(sig: pd.DataFrame, threshold: float) -> list[pd.Timestamp]:
    """First day bottom_pressure >= threshold after >=20 consecutive days below it."""
    bp = sig["bottom_pressure"].dropna()
    fires = []
    below_streak = 0
    min_streak = 20

    for date, val in bp.items():
        if val < threshold:
            below_streak += 1
        else:
            if below_streak >= min_streak:
                fires.append(date)
            below_streak = 0  # reset — stays above now until drops again

    return fires


# ---------------------------------------------------------------------------
# trigger (d1) — (a) AND (c@0.45) within 60-day window
# ---------------------------------------------------------------------------

def trigger_d1_mvrv_and_bp45(fires_a: list[pd.Timestamp],
                              fires_c: list[pd.Timestamp],
                              window_days: int = 60) -> list[pd.Timestamp]:
    """Fire when BOTH triggers (a) and (c@0.45) are active within a 60-day window.
    Either can fire first; we record the date of the SECOND trigger in the pair.
    Each fire can only be used once (earliest-first matching).
    """
    used_a = set()
    used_c = set()
    combo_fires = []

    # Build all valid pairs (a_date, c_date) where abs(diff) <= 60d
    pairs = []
    for da in fires_a:
        for dc in fires_c:
            if abs((da - dc).days) <= window_days:
                pairs.append((da, dc, max(da, dc)))

    # Sort by the "second" date and greedy pick non-overlapping
    pairs.sort(key=lambda x: x[2])
    for da, dc, trigger_date in pairs:
        if da not in used_a and dc not in used_c:
            combo_fires.append(trigger_date)
            used_a.add(da)
            used_c.add(dc)

    return sorted(combo_fires)


# ---------------------------------------------------------------------------
# trigger (d2) — (b) AFTER (a) within 120d
# ---------------------------------------------------------------------------

def trigger_d2_mvrv_then_20w(fires_a: list[pd.Timestamp],
                              fires_b: list[pd.Timestamp],
                              window_days: int = 120) -> list[pd.Timestamp]:
    """MVRV-Z crosses below 0 (a) FIRST, then within 120 days the 20w-MA reclaim (b) fires.
    Record the date of the 20w-MA reclaim (b) fire.
    """
    used_a = set()
    used_b = set()
    combo_fires = []

    for db in fires_b:
        # find the most recent (a) fire that is BEFORE db and within 120 days
        eligible_a = [da for da in fires_a
                      if da < db and (db - da).days <= window_days and da not in used_a]
        if eligible_a and db not in used_b:
            # use the most recent qualifying (a) fire
            best_a = max(eligible_a)
            combo_fires.append(db)
            used_a.add(best_a)
            used_b.add(db)

    return sorted(combo_fires)


# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------

def _verdict(m: dict, name: str) -> str:
    n = m.get("n", 0)
    hit = m.get("hit_rate_180d", np.nan)
    mae25 = m.get("pct_mae_worse_neg25", np.nan)

    fails = []
    if n < 4:
        fails.append(f"n={n} < 4")
    if np.isnan(hit) or hit < 0.70:
        h_pct = f"{hit*100:.0f}%" if not np.isnan(hit) else "N/A"
        fails.append(f"hit_rate_180d={h_pct} < 70%")
    if np.isnan(mae25) or mae25 > 0.30:
        m_pct = f"{mae25*100:.0f}%" if not np.isnan(mae25) else "N/A"
        fails.append(f"MAE<-25% rate={m_pct} > 30%")

    if not fails:
        return f"QUALIFIES — {name}"
    else:
        return f"DOES NOT QUALIFY — {name}: " + "; ".join(fails)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run_all(verbose: bool = True) -> dict:
    # Load signal frame
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
    from engine import btc_signals
    if verbose:
        print("Loading BTC signal frame (this may take a moment)...")
    sig = btc_signals.compute_all()
    if verbose:
        print(f"  Frame shape: {sig.shape}, date range: {sig.index[0].date()} → {sig.index[-1].date()}")

    close = sig["close"]
    ms = sig["momentum_state"]

    # ---- fire dates ----
    if verbose:
        print("\nComputing trigger fire dates...")

    fa   = trigger_a_mvrv_cross(sig)
    fb   = trigger_b_20w_reclaim(sig)
    fc45 = trigger_c_bottom_pressure(sig, 0.45)
    fc60 = trigger_c_bottom_pressure(sig, 0.60)
    fd1  = trigger_d1_mvrv_and_bp45(fa, fc45, window_days=60)
    fd2  = trigger_d2_mvrv_then_20w(fa, fb, window_days=120)

    # ---- metrics ----
    if verbose:
        print("Computing metrics...")

    ma_res   = _compute_metrics(close, fa,   ms)
    mb_res   = _compute_metrics(close, fb,   ms)
    mc45_res = _compute_metrics(close, fc45, ms)
    mc60_res = _compute_metrics(close, fc60, ms)
    md1_res  = _compute_metrics(close, fd1,  ms)
    md2_res  = _compute_metrics(close, fd2,  ms)

    triggers = {
        "(a) MVRV-Z cross<0":       ma_res,
        "(b) 20w-MA reclaim":       mb_res,
        "(c) BP>=0.45":             mc45_res,
        "(c) BP>=0.60":             mc60_res,
        "(d1) (a) AND (c@0.45)":   md1_res,
        "(d2) (a) THEN (b) 120d":  md2_res,
    }

    verdicts = {
        "(a) MVRV-Z cross<0":      _verdict(ma_res,   "MVRV-Z first cross below 0"),
        "(b) 20w-MA reclaim":      _verdict(mb_res,   "Weekly 20w-MA reclaim"),
        "(c) BP>=0.45":            _verdict(mc45_res, "bottom_pressure >= 0.45"),
        "(c) BP>=0.60":            _verdict(mc60_res, "bottom_pressure >= 0.60"),
        "(d1) (a) AND (c@0.45)":  _verdict(md1_res,  "MVRV + BP combo"),
        "(d2) (a) THEN (b) 120d": _verdict(md2_res,  "MVRV then 20w-MA"),
    }

    return {
        "sig_shape": sig.shape,
        "date_range": (str(sig.index[0].date()), str(sig.index[-1].date())),
        "triggers": triggers,
        "verdicts": verdicts,
    }


def print_report(results: dict) -> None:
    print("\n" + "=" * 72)
    print("BTC RE-ENTRY TRIGGER EVALUATION — Override-Registry W4")
    print("=" * 72)
    print(f"Signal frame: {results['date_range'][0]} → {results['date_range'][1]}")
    print(f"Shape: {results['sig_shape']}")

    print("\n" + "─" * 72)
    print("PRE-REGISTERED QUALIFYING BAR (stated before results):")
    print("  1. hit_rate_180d >= 70%")
    print("  2. MAE worse than -25% within 90d <= 30% of fires")
    print("  3. n >= 4 fires")
    print("─" * 72)

    print("\nSUMMARY TABLE")
    print(f"{'Trigger':<26} {'n':>4} {'indep':>6} {'hit90':>6} {'hit180':>7} {'hit365':>7} "
          f"{'med180':>7} {'MAE<-15':>8} {'MAE<-25':>8}")
    print("-" * 90)
    for name, m in results["triggers"].items():
        n  = m["n"]
        ie = m["independent_episodes"]
        h90  = f"{m['hit_rate_90d']*100:.0f}%"  if not np.isnan(m.get("hit_rate_90d", np.nan)) else "N/A"
        h180 = f"{m['hit_rate_180d']*100:.0f}%" if not np.isnan(m.get("hit_rate_180d", np.nan)) else "N/A"
        h365 = f"{m['hit_rate_365d']*100:.0f}%" if not np.isnan(m.get("hit_rate_365d", np.nan)) else "N/A"
        m180 = f"{m['fwd_180d_median']*100:.0f}%" if not np.isnan(m.get("fwd_180d_median", np.nan)) else "N/A"
        mae15 = f"{m['pct_mae_worse_neg15']*100:.0f}%" if not np.isnan(m.get("pct_mae_worse_neg15", np.nan)) else "N/A"
        mae25 = f"{m['pct_mae_worse_neg25']*100:.0f}%" if not np.isnan(m.get("pct_mae_worse_neg25", np.nan)) else "N/A"
        print(f"{name:<26} {n:>4} {ie:>6} {h90:>6} {h180:>7} {h365:>7} {m180:>7} {mae15:>8} {mae25:>8}")

    print("\n" + "─" * 72)
    print("PER-TRIGGER DETAIL")
    print("─" * 72)
    for name, m in results["triggers"].items():
        print(f"\n{name}")
        print(f"  Fire dates ({m['n']} total, {m['independent_episodes']} independent >180d):")
        for d in m.get("fire_dates", []):
            print(f"    {d}")
        if m["n"] > 0:
            print(f"  Fwd 90d:  median={m.get('fwd_90d_median', np.nan)*100:.1f}%  "
                  f"mean={m.get('fwd_90d_mean', np.nan)*100:.1f}%  "
                  f"hit={m.get('hit_rate_90d', np.nan)*100:.0f}%")
            print(f"  Fwd 180d: median={m.get('fwd_180d_median', np.nan)*100:.1f}%  "
                  f"mean={m.get('fwd_180d_mean', np.nan)*100:.1f}%  "
                  f"hit={m.get('hit_rate_180d', np.nan)*100:.0f}%")
            print(f"  Fwd 365d: median={m.get('fwd_365d_median', np.nan)*100:.1f}%  "
                  f"mean={m.get('fwd_365d_mean', np.nan)*100:.1f}%  "
                  f"hit={m.get('hit_rate_365d', np.nan)*100:.0f}%")
            print(f"  MAE:      median={m.get('mae_median_pct', np.nan):.1f}%  "
                  f"<-15%: {m.get('pct_mae_worse_neg15', np.nan)*100:.0f}%  "
                  f"<-25%: {m.get('pct_mae_worse_neg25', np.nan)*100:.0f}%")
            if m["bear_fires"] > 0:
                print(f"  Bear-phase fires: {m['bear_fires']}")
                print(f"    Median days to cycle bottom: {m.get('bear_median_days_to_bottom', np.nan):.0f}d")
                print(f"    Median % below fire at bottom: {m.get('bear_median_pct_below', np.nan):.1f}%")

    print("\n" + "─" * 72)
    print("VERDICT")
    print("─" * 72)
    for name, v in results["verdicts"].items():
        print(f"  {v}")

    print("\n" + "─" * 72)
    print("CAVEATS")
    print("─" * 72)
    print("  1. bottom_pressure composite: ~16 hand-set DOF (~8 conditions × weight + threshold")
    print("     parameters). Calibrated to match known BTC cycle lows → in-sample fit risk.")
    print("     Any qualification of (c) or (d1) should be treated as hypothesis-generating only.")
    print("  2. Overlapping 180d windows: 'independent episodes' (fires > 180d apart) is the")
    print("     honest N for forward-return statistics, not the total fire count.")
    print("  3. MVRV-Z rolling-window z-score: uses overlapping data → even with the 90d cooldown,")
    print("     effective independent N is much less than the fire count implies.")
    print("  4. Small-sample warning: n=3–7 for most triggers. Any result is statistically fragile.")
    print("  5. Data coverage: MVRV-Z requires on-chain data which may be sparse pre-2017.")
    print("  6. The 20w-MA trigger uses shift(1) on the weekly series for non-repainting, but")
    print("     the mapping back to daily may be 1–5 days early vs real-time observation.")
    print("=" * 72)


if __name__ == "__main__":
    results = run_all(verbose=True)
    print_report(results)
