"""Phase-0: pick_forward_dist — state-conditioned forward distributions for the equity
cross-section.

FROZEN PRE-REGISTRATION (written BEFORE any result was computed; any gap is an
amendment recorded in AMENDMENTS below and repeated in the results file)
================================================================================
Family:  pick_forward_dist_phase0
Program: advanced-quant-methods-w1 (wave 1)
Tier:    DIAGNOSTIC. This harness measures; it does not promote. No ship language,
         no authority claim, no gate on any user-facing surface follows from it.

QUESTION
--------
engine/forward_dist.py conditions ONE asset's history on ONE state series and reads
the empirical forward cone; engine/anticipation.py drives it live for 48 configured
cross-asset names. The ~2,900-name Prophet equity board has NO distributional read at
all. Before building one, measure the premise:

  On the real US wide panel, does a POOLED CROSS-SECTIONAL empirical forward
  distribution, conditioned on a name's causal state cell, beat the unconditional
  nulls out-of-sample — and is it calibrated?

"Beat" is scored by mean pinball loss across a fixed quantile grid (a CRPS proxy).
"Calibrated" is scored by realized coverage of the nominal 80% band. Both are
required: a sharper-but-wrong cone is worse than an honest wide one.

The construction is deliberately EMPIRICAL (an analog cohort of comparable name-days),
NOT a fitted quantile regression. Zero fitted weights, so there is nothing to overfit
and empirical quantiles cannot cross. Whether a FITTED quantile model adds anything on
top is a separate, later question and is explicitly out of scope here.

DATA
----
data/massive_stock_day/ — Polygon whole-market daily store, one parquet per instrument,
columns open/high/low/close/volume/transactions. Resolved by ladder:
  --data-root arg  ->  $MACRO_PRIMARY_DATA  ->  <repo>/data/massive_stock_day
  ->  /Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day
Read-only; this harness NEVER writes to the store.

PRICES ARE UNADJUSTED. Splits are repaired with the canonical, yahoo-verified
scripts.replay_standout_pipeline.split_adjust (the only sanctioned splitter here). It
adjusts CLOSE only, so the recovered factor is carried onto open/high/low (divide) and
volume (multiply) by engine.pick_forward_dist.carry_split_factor, and the two bars
straddling each applied factor change are stamped ineligible — a split print is not a
clean observation. Known residual: ~8-10 large SPINOFFS (GE, DD, T, EXC, MMM, DHR, WDC,
BKNG) are NOT splits, are not repaired by this splitter, and remain in the panel as
one-bar discontinuities. Dividends are not adjusted either (price return, not total
return). Both are disclosed in the results, not silently carried.

Back-adjustment is applied once over each full series, which is the standard convention
and is RATIO-NEUTRAL: every bar in a trailing window that contains no split is scaled by
the same constant, so every feature and every forward return here — all of them ratios —
is unchanged. It is not level-neutral. Two level-scale quantities therefore carry a
whisker of hindsight: the $5 price floor is applied to the back-adjusted price rather
than the price as printed, and the split-print stamp removes bars identified using the
whole series. Dollar volume is unaffected (the price divides and the share count
multiplies by the same factor). Neither touches an outcome, and both only ever REMOVE
observations from the universe; they are stated here rather than left to be discovered.

UNIVERSE (daily, causal — applies to TRAINING observations as well as evaluated ones)
  close > $5
  20-day MEDIAN dollar volume >= $2,000,000
  >= 300 bars of the name's own history (bar_index >= 300)
  every state feature and the vol scale finite on the bar
No instrument-type filter: the store is instrument-level and this repo holds no
whole-market classifier, so ETFs, ADRs, preferreds and warrants that clear the
liquidity filter are IN the universe. That is a named limitation on read-across to the
common-stock Prophet board, disclosed in the results — not an unregistered filter
invented after seeing a number.

STATE FEATURES (causal; full lag convention in engine/pick_forward_dist.py docstring)
  above_200dma : close > 200d SMA                                          (trend side)
  slope50_up   : 50d SMA > its own value 10 bars ago                      (trend slope)
  ext_pct      : 100 * (close / trailing-252d high - 1)   <= 0             (extension)
  rvol_z       : 20d realized daily vol, z-scored against its own trailing
                 252d mean/std LAGGED ONE BAR                             (vol state)
  coil         : 20d (high-low)/close range over its own trailing 252d
                 median LAGGED ONE BAR; < 1 = compression                 (coil)
A rolling statistic ending at bar t includes bar t (known at that close). Any reference
distribution a bar is scored against is lagged one bar, so no observation sits inside
its own reference. Forward outcomes are LABELS and are never fed back as state.

SCHEMES (exactly these five; no scheme is added, dropped or redefined after results)
  S1_trend      above_200dma x slope50_up                          -> 4 cells
  S2_extension  ext_pct, 4 equal-frequency bands                   -> 4 cells
  S3_vol        rvol_z,  4 equal-frequency bands                   -> 4 cells
  S4_coil       coil,    4 equal-frequency bands                   -> 4 cells
  S5_trend_vol  above_200dma x rvol_z (3 bands)                    -> 6 cells
Band edges are equal-frequency quantiles OF THE TRAINING COHORT ONLY (never the full
sample), refit on the quarterly schedule below. A bar missing any axis is uncodable
(-1) and is never silently pooled into a cell.

OUTCOMES / FRAMES
  Horizons H in {10, 21, 63} trading days, from engine.forward_dist.forward_paths:
    ret = close[t+h]/close[t] - 1, mae = worst dip, mfe = best pop, all in percent.
  PRIMARY FRAME is VOL-STANDARDIZED: (pct/100) / (vol_scale * sqrt(h)), where
    vol_scale = 20d realized daily vol LAGGED ONE BAR, floored at 0.005/day. A cone is
    therefore in "h-day sigmas" and is comparable across a multi-thousand-name
    cross-section; it re-scales to percent per name-date at emit.
  SECONDARY FRAME is the raw percent return, run at H=21 only, reported descriptively.
  Emitted per cell: return quantiles at tau in {0.05, 0.10, 0.25, 0.50, 0.75, 0.90,
    0.95}, MAE quantiles at {0.05, 0.25, 0.50}, MFE median, P(up), n.

COHORT + EMBARGO
  For as-of session t and horizon h, the training cohort is every panel observation
  (name, d) with
        d <= t - h - 1          (embargo: the outcome resolved STRICTLY before t)
    and d >  t - h - 1 - 504    (trailing window, 504 sessions)
  pooled ACROSS NAMES, restricted to the same state cell. Sessions are integer indices
  into the shared trading calendar, so the embargo is exact across holidays and gaps.

MIN-N FLOOR + DEGRADE
  A cell holding fewer than 400 pooled observations does NOT get its own thin
  quantiles: it inherits the pooled marginal and is stamped degraded=True with its own
  honest n preserved. A degraded cell is a null, printed, never a silent conditional.

WALK-FORWARD
  Refit boundaries are QUARTERLY. At the first evaluation session of each calendar
  quarter, band edges and every per-cell cone (and both baselines) are estimated on the
  embargoed cohort as of that session, then HELD FIXED for every evaluation date in the
  quarter. Because the fit is embargoed by h+1 sessions at the quarter start, every
  later evaluation date in that quarter is embargoed by at least that much.
  Evaluation dates: EVERY session from the first session on/after 2023-01-01 (the first
  ~18 months of the store are warm-up for the 252d references and the 504d cohort)
  through the last session with a fully realized H-horizon outcome. A date is skipped
  if its cross-section has fewer than 50 evaluable names.

BASELINES (the nulls that must be beaten; same cohort, same window, same frame)
  B0  pooled unconditional trailing distribution — no cells at all.
  B1  own-name trailing marginal — that name's own observations in the embargoed
      window, minimum 252; a name below that falls back to B0 and is stamped degraded.

METRICS
  pinball loss L_tau(y,q) = tau*(y-q) if y>=q else (tau-1)*(y-q); the score is the mean
    across the seven-tau grid, per observation, then averaged cross-sectionally per
    date (a CRPS proxy).
  coverage    = share of evaluated name-days with q10 <= y <= q90 (nominal 0.80).
  breach-run  = lag-1 autocorrelation of the per-date breach rate + longest run of
    dates above nominal. REPORT-ONLY: it carries no pre-registered null and gates
    nothing.
  MAE-p05 tail hit rate = share of name-days whose realized worst dip was at or beyond
    the predicted p05 dip (nominal 0.05).

STATS
  Skill deltas are formed PER DATE as (baseline mean pinball - scheme mean pinball), so
  a positive delta is skill, on the identical cross-section for both arms. The delta
  series is date-indexed and overlapping (h-day forward windows), so the CI is a
  circular BLOCK bootstrap with block = h (21 at the primary horizon), B = 5000,
  seed = 7, via engine.validation.block_bootstrap_ci; the interval in pinball units
  comes from engine.pick_forward_dist.block_bootstrap_mean_ci with the same settings.
  "Excludes 0" means the 2.5th and 97.5th percentiles of the bootstrap distribution
  fall on the same side of zero.

PRE-REGISTERED GATES (printed PASS/FAIL per scheme, at H=21, vol-standardized frame)
  G1 CALIBRATION   OOS 80%-band coverage in [0.72, 0.88].
  G2 SKILL vs B0   mean-pinball delta vs the pooled unconditional, date-blocked 95% CI
                   excluding 0 on the positive side.
  G3 SKILL vs B1   same, versus the own-name marginal.
  G4 CELL HONESTY  >= 80% of evaluated name-days sit in an above-floor (non-degraded)
                   cell. Below that the scheme is mostly marginal fallback wearing a
                   conditional label.
  Also reported, gating nothing: era-split (2023-24 vs 2025-26) sign stability of the
  G2 delta; n names / name-days / cells; coverage at H=10 and H=63; the raw-return
  frame at H=21; the breach-run statistic; the MAE-p05 tail hit rate.

VERDICT VOCABULARY (one per scheme; precedence top-down, first match wins)
  DEGENERATE       G4 fails — mostly marginal fallback, the cells are not real.
  MISCALIBRATED    G4 passes, G1 fails — the band is the wrong width.
  GO               G1-G4 all pass.
  CALIBRATED_ONLY  G1 and G4 pass, G2 and/or G3 fails — honest width, no measured edge.
These are DIAGNOSTIC verdicts. "GO" here means "this scheme survived phase-0 as
measured"; it authorizes nothing. Promotion to any ranked, sized or gated surface is a
separate adjudication the commissioning session owns.

FALSIFICATION POSTURE
  A failed gate is a RESULT and ships as one. Schemes are not redefined, thresholds are
  not moved, and horizons are not swapped after seeing a number: verdicts are issued
  ONLY at H=21, and H=10/H=63 are descriptive ladder rows that cannot become the
  headline. Nulls are printed.

AMENDMENTS (gaps closed BEFORE any compute; none after)
  AM-1  The commissioning brief states the panel ends 2026-07-28. It does not. The
        worktree's committed manifest claims latest_date 2026-07-28 / 20,677 tickers,
        but the parquets themselves (primary checkout) carry their own manifest reading
        latest_date 2026-07-02 / 19,133 tickers, and 20,476 parquet files. The READABLE
        data ends 2026-07-02; the committed manifest is ahead of the store it
        describes. This harness reports the calendar it actually read. A separate lane
        owns the publish outage; nothing here attempts to refresh or repair it.
  AM-2  Evaluation is at EVERY session, not a weekly subsample. A throughput probe
        (800 random names) measured before this header was frozen put the full panel
        build at ~2 minutes and the walk-forward at a few more, so the runtime budget
        does not force a subsample. Daily evaluation is also what makes block = h the
        correct block length: the dependence horizon is h SESSIONS, which is h
        OBSERVATIONS of the delta series only when the series is daily.
  AM-3  Band edges and cones are refit quarterly, while the module's cohort rule is
        stated "as of t". Quarter-start fitting is the conservative direction: a fit
        frozen at the quarter start is embargoed from every later evaluation date in
        that quarter by MORE than h+1 sessions, never less.
  AM-4  The min-cell floor of 400 pooled observations is unlikely to bind on a
        cross-section this wide (a 504-session cohort across thousands of names is
        millions of observations spread over 4-6 cells), which makes G4 a weak gate in
        THIS configuration. It is kept as pre-registered, and its weakness is stated in
        the results rather than fixed by moving the number after the fact.
  AM-5  B1 is fitted on the same quarterly schedule as everything else, so it is the
        name's own marginal as of the quarter start, not as of each evaluation date.
        That is the like-for-like comparison; giving one arm a fresher fit than another
        would be the confounded one.

Run:    python3 -m scripts.pick_forward_dist_phase0
        python3 -m scripts.pick_forward_dist_phase0 --max-names 400   # smoke
Writes: research/pick_forward_dist_phase0_results.json
        research/PICK_FORWARD_DIST_PHASE0.md
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

WT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WT_ROOT))
if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

from engine import pick_forward_dist as pfd                      # noqa: E402
from engine.trial_ledger import TrialLedger                       # noqa: E402
from engine.validation import block_bootstrap_ci                  # noqa: E402
from scripts.replay_standout_pipeline import split_adjust         # noqa: E402

# ------------------------------------------------------------------ frozen constants
FAMILY = "pick_forward_dist_phase0"
PROGRAM = "advanced-quant-methods-w1"

HORIZONS = (10, 21, 63)
PRIMARY_H = 21
WINDOW = pfd.DEFAULT_WINDOW          # 504
MIN_CELL_N = pfd.MIN_CELL_N          # 400
MIN_OWN_N = pfd.MIN_OWN_N            # 252
TAUS = pfd.TAUS
OOS_START = "2023-01-01"
MIN_XSEC = 50
ERA_SPLIT = "2025-01-01"

COV_LO, COV_HI = 0.72, 0.88          # G1
G4_MIN_HONEST = 0.80                 # G4
BOOT_B, BOOT_SEED = 5000, 7

SCHEMES = tuple(pfd.SCHEMES)
BASELINES = ("B0_pooled", "B1_ownname")

RESULTS_JSON = WT_ROOT / "research" / "pick_forward_dist_phase0_results.json"
RESULTS_MD = WT_ROOT / "research" / "PICK_FORWARD_DIST_PHASE0.md"
LEDGER_PATH = WT_ROOT / "data" / "trial_ledger.jsonl"

SPINOFF_UNREPAIRED = ["GE", "DD", "T", "EXC", "MMM", "DHR", "WDC", "BKNG"]


# ------------------------------------------------------------------ data root ladder
def resolve_data_root(arg: str | None) -> Path | None:
    """--data-root -> $MACRO_PRIMARY_DATA -> <repo>/data/massive_stock_day -> primary
    checkout. A root counts only if it actually holds parquets (the worktree carries the
    manifest but not the store)."""
    cands = []
    if arg:
        cands.append(Path(arg).expanduser())
    env = os.environ.get("MACRO_PRIMARY_DATA")
    if env:
        p = Path(env).expanduser()
        cands += [p, p / "massive_stock_day"]
    cands.append(WT_ROOT / "data" / "massive_stock_day")
    cands.append(Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day"))
    for c in cands:
        try:
            if c.is_dir() and any(c.glob("*.parquet")):
                return c
        except OSError:
            continue
    return None


# ------------------------------------------------------------------ load + repair
def load_frames(store: Path, max_names: int | None = None) -> tuple[dict, dict]:
    """Read every instrument, split-repair it, and keep the ones that could possibly
    clear the universe filter. The dollar-volume half of the prefilter is strictly
    WEAKER than build_panel's daily filter (a 20d median can never exceed the max, and
    close*volume is invariant under carry_split_factor). The PRICE half is not exact
    (REVIEW-8): it tests the RAW close against PRICE_MIN before back-adjustment, while
    build_panel tests the back-adjusted close — a name that never printed above $5 raw
    but clears $5 back-adjusted (reverse splits) is dropped here though build_panel
    would admit it. Removal-only (never adds a name, never touches an outcome); one
    more universe-definition whisker, stated rather than hidden."""
    paths = sorted(store.glob("*.parquet"))
    if max_names:
        paths = paths[:max_names]
    frames, stats = {}, {"files": len(paths), "read_ok": 0, "prefilter_pass": 0,
                         "split_repaired": 0, "bars_stamped": 0}
    for i, p in enumerate(paths):
        if i and i % 4000 == 0:
            print(f"    {i:,}/{len(paths):,} read, {len(frames):,} kept", flush=True)
        try:
            df = pd.read_parquet(p, columns=["open", "high", "low", "close", "volume"])
        except Exception:
            continue
        stats["read_ok"] += 1
        if len(df) <= pfd.MIN_BARS:
            continue
        close = df["close"]
        if not (close > pfd.PRICE_MIN).any():
            continue
        if float((close * df["volume"]).max()) < pfd.DVOL_MIN:
            continue
        stats["prefilter_pass"] += 1
        adj, touched = pfd.carry_split_factor(df, split_adjust(close))
        n_touched = int(touched.sum())
        if n_touched:
            stats["split_repaired"] += 1
            stats["bars_stamped"] += n_touched
        adj["split_touched"] = touched
        frames[p.stem] = adj
    return frames, stats


# ------------------------------------------------------------------ walk-forward
def _quarter(ts: pd.Timestamp) -> tuple[int, int]:
    return (int(ts.year), int((ts.month - 1) // 3 + 1))


def _fit_all(panel, asof_sess, h, ret_col, mae_col, mfe_col):
    fits = {s: pfd.fit_at(panel, asof_sess, s, h, window=WINDOW, min_n=MIN_CELL_N,
                          taus=TAUS, ret_col=ret_col, mae_col=mae_col, mfe_col=mfe_col)
            for s in SCHEMES}
    b0, b1 = pfd.fit_baselines_at(panel, asof_sess, h, window=WINDOW,
                                  min_own_n=MIN_OWN_N, taus=TAUS, ret_col=ret_col)
    fits["B0_pooled"], fits["B1_ownname"] = b0, b1
    return fits


def walk_forward(panel: pd.DataFrame, cal: pd.DatetimeIndex, h: int, *,
                 frame: str = "std") -> dict:
    """Quarterly-refit walk-forward at one horizon. `frame` selects the vol-standardized
    (primary) or raw-percent (secondary) outcome columns. Returns per-date series plus
    the pooled calibration reads."""
    ret_col = f"z_ret_{h}" if frame == "std" else f"ret_{h}"
    mae_col, mfe_col = f"z_mae_{h}", f"z_mfe_{h}"
    sess = panel["sess"].to_numpy()
    y_all = panel[ret_col].to_numpy(dtype=float)
    mae_all = panel[mae_col].to_numpy(dtype=float)
    name_codes = panel["name"].cat.codes.to_numpy().astype(np.int64)
    n_cats = int(panel["name"].cat.categories.size)
    # zero-copy column views — the per-date slice must never copy a DataFrame
    feat_arr = {c: panel[c].to_numpy() for c in pfd.FEATURE_COLS}

    first_oos = int(np.searchsorted(cal.to_numpy(), np.datetime64(OOS_START), side="left"))
    last_eval = len(cal) - 1 - h
    arms = list(SCHEMES) + list(BASELINES)

    dates, pin = [], {a: [] for a in arms}
    cov_hit = {a: [0, 0] for a in arms}            # [inside, total]
    breach_by_date = {a: [] for a in arms}
    honest = {a: [0, 0] for a in arms}             # [non-degraded, total]
    tail = {a: [0, 0] for a in arms}
    cur_q, fits = None, None
    names_seen = np.zeros(n_cats, dtype=bool)
    n_cells = {a: set() for a in arms}
    n_refits = 0
    i10, i90 = list(TAUS).index(0.10), list(TAUS).index(0.90)

    for t in range(first_oos, last_eval + 1):
        q = _quarter(cal[t])
        if q != cur_q:
            fits = _fit_all(panel, t, h, ret_col, mae_col, mfe_col)
            cur_q = q
            n_refits += 1
        a, b = (int(np.searchsorted(sess, t, "left")), int(np.searchsorted(sess, t, "right")))
        if b - a < MIN_XSEC:
            continue
        y = y_all[a:b]
        ok = np.isfinite(y)
        if int(ok.sum()) < MIN_XSEC:
            continue
        yo, mo = y[ok], mae_all[a:b][ok]
        row = {}
        for arm in arms:
            fit = fits[arm]
            if arm == "B0_pooled":
                codes = np.zeros(b - a, dtype=np.int64)
            elif arm == "B1_ownname":
                codes = name_codes[a:b]
            else:
                codes = pfd.assign_cells({c: v[a:b] for c, v in feat_arr.items()},
                                         arm, fit["edges_arr"]).astype(np.int64)
                n_cells[arm].update(int(c) for c in np.unique(codes))
            qmat, deg = pfd.cone_matrix(fit, codes, taus=TAUS)
            qo = qmat[ok]
            row[arm] = float(np.mean(pfd.mean_pinball(yo, qo, TAUS)))
            inside = (yo >= qo[:, i10]) & (yo <= qo[:, i90])
            cov_hit[arm][0] += int(inside.sum())
            cov_hit[arm][1] += int(inside.size)
            breach_by_date[arm].append(float(1.0 - inside.mean()))
            honest[arm][0] += int((~deg[ok]).sum())
            honest[arm][1] += int(ok.sum())
            if arm not in BASELINES:
                pred = pfd.cone_scalar(fit, codes[ok], field="mae_q", key="q05")
                good = np.isfinite(pred) & np.isfinite(mo)
                tail[arm][0] += int((mo[good] <= pred[good]).sum())
                tail[arm][1] += int(good.sum())
        dates.append(cal[t])
        for arm in arms:
            pin[arm].append(row[arm])
        names_seen[name_codes[a:b][ok]] = True

    idx = pd.DatetimeIndex(dates)
    return {
        "horizon": h, "frame": frame,
        "dates": idx,
        "pinball": {a: pd.Series(v, index=idx) for a, v in pin.items()},
        "coverage": {a: (c[0] / c[1] if c[1] else float("nan")) for a, c in cov_hit.items()},
        "breach": {a: pd.Series(v, index=idx) for a, v in breach_by_date.items()},
        "honest_frac": {a: (hh[0] / hh[1] if hh[1] else float("nan")) for a, hh in honest.items()},
        "tail_hit": {a: (tt[0] / tt[1] if tt[1] else float("nan")) for a, tt in tail.items()},
        "n_dates": len(idx), "n_names": int(names_seen.sum()), "n_refits": n_refits,
        "n_obs_total": cov_hit[arms[0]][1] if arms else 0,
        "n_cells_seen": {a: len(v) for a, v in n_cells.items()},
    }


def delta_stats(wf: dict, scheme: str, baseline: str, block: int) -> dict:
    """Per-date paired delta (baseline - scheme): positive = the scheme scored a lower
    pinball loss than the null on the same cross-section."""
    d = (wf["pinball"][baseline] - wf["pinball"][scheme]).dropna()
    if len(d) < max(block * 3, 60):
        return {"n_dates": int(len(d)), "mean_delta": None, "ci": None,
                "excludes_zero": False, "reason": "insufficient_dates"}
    mean_ci = pfd.block_bootstrap_mean_ci(d, block=block, B=BOOT_B, seed=BOOT_SEED)
    # ann=252: trading-day series (REVIEW-7 — the default 365 inflated the published
    # sharpe_ci ~1.20x; only the sign is ever consumed, but ship the honest number).
    sh = block_bootstrap_ci(d, block=block, B=BOOT_B, seed=BOOT_SEED, ann=252)
    sci = sh.get("sharpe_ci")
    return {
        "n_dates": int(len(d)),
        "mean_delta": round(float(d.mean()), 6),
        "pct_of_baseline": round(float(d.mean() / wf["pinball"][baseline].mean() * 100.0), 3)
        if float(wf["pinball"][baseline].mean()) else None,
        "ci": [round(v, 6) for v in mean_ci["ci"]],
        "excludes_zero": bool(mean_ci["excludes_zero"]),
        "gt0_prob": round(mean_ci["gt0_prob"], 4),
        "sharpe_ci": sci,
        "sharpe_ci_excludes_zero": bool(sci and (sci[0] > 0 or sci[2] < 0)),
        "frac_dates_positive": round(float((d > 0).mean()), 4),
        "block": block,
    }


def era_split(wf: dict, scheme: str, baseline: str) -> dict:
    d = (wf["pinball"][baseline] - wf["pinball"][scheme]).dropna()
    cut = pd.Timestamp(ERA_SPLIT)
    e1, e2 = d[d.index < cut], d[d.index >= cut]
    m1 = float(e1.mean()) if len(e1) else float("nan")
    m2 = float(e2.mean()) if len(e2) else float("nan")
    return {"era_2023_24": {"n_dates": int(len(e1)), "mean_delta": round(m1, 6)},
            "era_2025_26": {"n_dates": int(len(e2)), "mean_delta": round(m2, 6)},
            "sign_stable": bool(np.isfinite(m1) and np.isfinite(m2) and np.sign(m1) == np.sign(m2))}


def verdict_for(g1: bool, g2: bool, g3: bool, g4: bool) -> str:
    if not g4:
        return "DEGENERATE"
    if not g1:
        return "MISCALIBRATED"
    if g2 and g3:
        return "GO"
    return "CALIBRATED_ONLY"


# ------------------------------------------------------------------ study
def run_study(store: Path, max_names: int | None = None) -> dict:
    t_start = time.time()
    print(f"[startup] store       : {store}", flush=True)
    print(f"[startup] family      : {FAMILY} / program {PROGRAM}", flush=True)

    # Pre-register the multiple-testing budget BEFORE any compute (ledger law).
    led = TrialLedger(path=LEDGER_PATH, family=FAMILY)
    configs = [{
        "scheme": s, "cells": pfd.SCHEME_CELLS[s], "horizon": PRIMARY_H,
        "frame": "vol_standardized",
        "test": "mean_pinball_delta_vs_B0_and_B1",
        "gates": "G1 coverage[0.72,0.88]; G2 CI>0 vs B0; G3 CI>0 vs B1; G4 honest>=0.80",
    } for s in SCHEMES] + [{
        "baseline": b, "horizon": PRIMARY_H, "frame": "vol_standardized",
        "role": "pre-registered null",
    } for b in BASELINES]
    n_new = led.log_grid(configs, info_cutoff="2026-07-02",
                         note="pick_forward_dist phase-0; frozen prereg in the script "
                              "docstring, written before compute")
    print(f"[ledger]  {n_new} new trial configs (family={FAMILY}, total "
          f"{led.literal_n(FAMILY)})", flush=True)

    print("[load]    reading + split-repairing the store ...", flush=True)
    t0 = time.time()
    frames, lstats = load_frames(store, max_names=max_names)
    print(f"[load]    {lstats['read_ok']:,} read, {lstats['prefilter_pass']:,} prefiltered, "
          f"{lstats['split_repaired']:,} split-repaired ({lstats['bars_stamped']:,} bars "
          f"stamped) in {time.time()-t0:.0f}s", flush=True)

    print("[panel]   assembling the observation panel ...", flush=True)
    t0 = time.time()
    panel, cal = pfd.build_panel(frames, horizons=HORIZONS)
    del frames
    if panel.empty:
        raise SystemExit("no eligible observations — refusing to report an empty study")
    names = panel["name"].astype(str).unique()
    lower = sorted(n for n in names if any(c.islower() for c in n))
    print(f"[panel]   {len(panel):,} rows, {len(names):,} names, calendar "
          f"{cal[0].date()} -> {cal[-1].date()} ({len(cal)} sessions) in "
          f"{time.time()-t0:.0f}s", flush=True)

    results = {}
    for h in HORIZONS:
        print(f"[wf]      H={h} vol-standardized ...", flush=True)
        t0 = time.time()
        results[("std", h)] = walk_forward(panel, cal, h, frame="std")
        print(f"[wf]      H={h} done: {results[('std', h)]['n_dates']} dates, "
              f"{results[('std', h)]['n_obs_total']:,} name-days in {time.time()-t0:.0f}s",
              flush=True)
    print(f"[wf]      H={PRIMARY_H} raw-percent (secondary) ...", flush=True)
    results[("raw", PRIMARY_H)] = walk_forward(panel, cal, PRIMARY_H, frame="raw")

    # ---------------- gates (H=21, vol-standardized frame only)
    wf = results[("std", PRIMARY_H)]
    gates, schemes_out = {}, {}
    for s in SCHEMES:
        cov = wf["coverage"][s]
        d_b0 = delta_stats(wf, s, "B0_pooled", PRIMARY_H)
        d_b1 = delta_stats(wf, s, "B1_ownname", PRIMARY_H)
        g1 = bool(np.isfinite(cov) and COV_LO <= cov <= COV_HI)
        g2 = bool(d_b0["excludes_zero"] and (d_b0["mean_delta"] or 0) > 0)
        g3 = bool(d_b1["excludes_zero"] and (d_b1["mean_delta"] or 0) > 0)
        g4 = bool(np.isfinite(wf["honest_frac"][s]) and wf["honest_frac"][s] >= G4_MIN_HONEST)
        gates[s] = {
            "G1_calibration": {"pass": g1, "coverage_80": round(float(cov), 4),
                               "band": [COV_LO, COV_HI]},
            "G2_skill_vs_B0": {"pass": g2, **d_b0},
            "G3_skill_vs_B1": {"pass": g3, **d_b1},
            "G4_cell_honesty": {"pass": g4,
                                "honest_frac": round(float(wf["honest_frac"][s]), 4),
                                "min": G4_MIN_HONEST},
            "verdict": verdict_for(g1, g2, g3, g4),
        }
        schemes_out[s] = {
            "cells_declared": pfd.SCHEME_CELLS[s],
            "cells_seen_h21": wf["n_cells_seen"].get(s),
            "era_split_vs_B0": era_split(wf, s, "B0_pooled"),
            "mean_pinball_h21": round(float(wf["pinball"][s].mean()), 6),
            "breach_run_h21": pfd.breach_run_stat(wf["breach"][s]),
            "mae_p05_tail_hit_h21": None if not np.isfinite(wf["tail_hit"][s])
            else round(float(wf["tail_hit"][s]), 4),
            "horizons": {
                f"H{h}": {
                    "coverage_80": round(float(results[("std", h)]["coverage"][s]), 4),
                    "mean_pinball": round(float(results[("std", h)]["pinball"][s].mean()), 6),
                    "delta_vs_B0": delta_stats(results[("std", h)], s, "B0_pooled", h),
                    "delta_vs_B1": delta_stats(results[("std", h)], s, "B1_ownname", h),
                    "honest_frac": round(float(results[("std", h)]["honest_frac"][s]), 4),
                } for h in HORIZONS
            },
            "raw_frame_H21": {
                "coverage_80": round(float(results[("raw", PRIMARY_H)]["coverage"][s]), 4),
                "mean_pinball": round(float(results[("raw", PRIMARY_H)]["pinball"][s].mean()), 6),
                "delta_vs_B0": delta_stats(results[("raw", PRIMARY_H)], s, "B0_pooled", PRIMARY_H),
            },
        }

    baselines_out = {b: {
        "coverage_80_h21": round(float(wf["coverage"][b]), 4),
        "mean_pinball_h21": round(float(wf["pinball"][b].mean()), 6),
        "honest_frac_h21": round(float(wf["honest_frac"][b]), 4),
        "breach_run_h21": pfd.breach_run_stat(wf["breach"][b]),
        "horizons": {f"H{h}": {
            "coverage_80": round(float(results[("std", h)]["coverage"][b]), 4),
            "mean_pinball": round(float(results[("std", h)]["pinball"][b].mean()), 6),
        } for h in HORIZONS},
    } for b in BASELINES}

    runtime = time.time() - t_start
    out = {
        "family": FAMILY,
        "program": PROGRAM,
        "tier": "diagnostic — phase-0 measurement; promotes nothing",
        "prereg": "frozen in the module docstring of scripts/pick_forward_dist_phase0.py",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_sec": round(runtime, 1),
        "data": {
            "store": str(store),
            "files_seen": lstats["files"],
            "files_read": lstats["read_ok"],
            "prefilter_pass": lstats["prefilter_pass"],
            "split_repaired_names": lstats["split_repaired"],
            "split_bars_stamped": lstats["bars_stamped"],
            "calendar_first": str(cal[0].date()),
            "calendar_last": str(cal[-1].date()),
            "calendar_sessions": int(len(cal)),
            "panel_rows": int(len(panel)),
            "panel_names": int(len(names)),
            "names_with_lowercase_symbol": len(lower),
            "prices": "unadjusted; splits repaired via replay_standout_pipeline.split_adjust; "
                      "dividends NOT adjusted (price return)",
        },
        "config": {
            "horizons": list(HORIZONS), "primary_horizon": PRIMARY_H,
            "taus": list(TAUS), "window_sessions": WINDOW,
            "min_cell_n": MIN_CELL_N, "min_own_n": MIN_OWN_N,
            "vol_floor_daily": pfd.VOL_FLOOR,
            "universe": {"price_min": pfd.PRICE_MIN, "dvol20_median_min": pfd.DVOL_MIN,
                         "min_bars": pfd.MIN_BARS},
            "oos_start": OOS_START, "min_cross_section": MIN_XSEC,
            "refit": "quarterly", "eval_cadence": "every session",
            "bootstrap": {"B": BOOT_B, "seed": BOOT_SEED, "block": "= horizon"},
            "gates": {"G1_coverage_band": [COV_LO, COV_HI], "G4_min_honest_frac": G4_MIN_HONEST},
        },
        "eval_span": {
            "n_dates_h21": wf["n_dates"], "n_name_days_h21": wf["n_obs_total"],
            "n_names_h21": wf["n_names"], "n_quarterly_refits_h21": wf["n_refits"],
            "first_eval": str(wf["dates"][0].date()) if wf["n_dates"] else None,
            "last_eval": str(wf["dates"][-1].date()) if wf["n_dates"] else None,
        },
        "gates": gates,
        "schemes": schemes_out,
        "baselines": baselines_out,
        "verdicts": {s: gates[s]["verdict"] for s in SCHEMES},
        "caveats": [
            "SURVIVORSHIP: data/massive_stock_day is the Polygon whole-market store and "
            f"DOES carry delisted instruments ({lstats['files']:,} parquet files vs "
            "~4-6k currently-listed liquid names), so survivorship bias is bounded — but "
            "it is not zero: the store begins 2021-07-06, so anything delisted before "
            "that date is invisible, and the store is not a point-in-time listing "
            "snapshot.",
            "SINGLE ERA: the whole panel is 2021-07-06 to "
            f"{cal[-1].date()} — one macro regime block (post-COVID melt-up, the 2022 "
            "rate shock, the 2023-2026 AI-led advance). There is no independent second "
            "era, so the 2023-24 vs 2025-26 split reported here is a within-sample "
            "stability read, not an out-of-era replication.",
            "DIVIDENDS: prices are price-return, not total-return. Forward returns are "
            "understated for high-yield names by roughly the dividend paid in the window.",
            "SPINOFFS: ~8-10 large spinoffs (" + ", ".join(SPINOFF_UNREPAIRED) + ") are "
            "NOT splits; split_adjust does not repair them and they remain in the panel "
            "as one-bar discontinuities.",
            "INSTRUMENT MIX: the store is instrument-level and this repo holds no "
            "whole-market classifier, so ETFs, ADRs and preferred/class shares that "
            f"clear the liquidity filter are in the universe ({len(lower)} surviving "
            "symbols carry a lowercase character, the Polygon preferred/class-share "
            "convention). Read-across to the common-stock Prophet board is therefore "
            "approximate.",
            "G4 WEAKNESS (AM-4): with a cross-section this wide the 400-observation cell "
            "floor rarely binds, so G4 as configured is a weak gate. It was kept as "
            "pre-registered rather than retuned after the fact.",
            "OVERLAP: forward windows overlap across adjacent evaluation dates; the "
            "block bootstrap (block = horizon) is the correction, not an i.i.d. "
            "assumption.",
            "BACK-ADJUSTMENT IS RATIO-NEUTRAL, NOT LEVEL-NEUTRAL: splits are repaired "
            "once over each full series (the standard convention), so every feature and "
            "forward return used here is unchanged, but the $5 price floor is applied "
            "to the back-adjusted price rather than the price as printed, and the "
            "split-print stamp is identified using the whole series. Both only remove "
            "observations from the universe and neither touches an outcome — a small "
            "hindsight whisker in the universe definition, stated rather than hidden.",
            "B0's above-floor share is 0 by construction: the pooled unconditional "
            "baseline IS the marginal, so that field is meaningful only for a "
            "conditioning scheme.",
            "BREACH CLUSTERING IS MOSTLY MECHANICAL: adjacent evaluation dates share "
            f"{PRIMARY_H - 1} of their {PRIMARY_H} forward days, so the per-date breach "
            "rate is autocorrelated by construction at daily cadence. A high lag-1 "
            "autocorrelation here is therefore NOT by itself evidence of a modelling "
            "failure. The statistic is report-only for exactly this reason; comparing "
            "it ACROSS arms on the same dates is the only reading it supports.",
            "THE STANDARDIZER IS PART OF THE HYPOTHESIS, NOT NEUTRAL GROUND: outcomes "
            "are scaled by TRAILING realized 20d vol, which is a naive forecast of "
            "forward vol — realized vol mean-reverts, so a name whose 20d vol just "
            "spiked will realize LESS than one trailing sigma, and one in a vol trough "
            "will realize more. Any cell that sorts on vol state (S3_vol, and the vol "
            "axis of S5_trend_vol) can therefore earn a pinball gain purely by "
            "correcting that known bias in the scale. That is a real and useful "
            "correction, but it is a different claim from 'state carries forward-return "
            "information'. The decisive follow-up, OUT OF SCOPE for this phase-0: re-run "
            "with a HAR forward-vol forecast as the standardizer (engine/vol_forecast.py "
            "already ships one, exercised by tests/test_anticipation.py). If a vol-state "
            "scheme still beats B0 under that scale, the conditioning carries "
            "information; if the edge collapses, the finding is 'use a better vol "
            "forecast', not 'condition on vol state'. No verdict below distinguishes "
            "these two cases.",
            "THE RAW-PERCENT FRAME DOUBLE-COUNTS SCALE: in raw percent, a cell that "
            "sorts on extension or vol also sorts on return DISPERSION, so a scheme can "
            "score a large raw-frame gain purely by predicting width that the "
            "vol-standardizer already supplies in the primary frame. Where the raw "
            "delta is large and the standardized delta is not, the honest reading is "
            "that the scheme is re-deriving the vol scale, not adding information to "
            "it. The primary frame is the one the gates read.",
            "DATA END (AM-1): the readable store ends "
            f"{cal[-1].date()}, not 2026-07-28 as the worktree's committed manifest "
            "claims. A separate lane owns that publish outage.",
        ],
        # Findings from the commissioned adversarial review (2026-08-06), recorded in
        # the artifact so the design weaknesses travel with the numbers. These are
        # post-registration DISCLOSURES — no gate, scheme, or number was retuned.
        "post_run_review": [
            "REVIEW-1 (G1 IS NON-DISCRIMINATING AT THIS DESIGN): the unconditional "
            "null itself sits mid-band — B0 covers ~0.794 and B1 ~0.786 against the "
            "[0.72, 0.88] gate — so an empirical marginal fitted on a large cohort "
            "passes G1 by construction. G1+G4 being structurally weak means 'passes "
            "all four gates' really rests on G2/G3, the two gates capable of failing. "
            "The pooled coverage number also carries no overlap-corrected test "
            "statistic (the HEDGEYE C.4 spec's Kupiec/Christoffersen point about "
            "overlapping origins applies); a coverage TEST at non-overlapping origins "
            "belongs in the phase-1 harness.",
            "REVIEW-2 (COHORT RAMP / B1 NON-INDEPENDENCE): the store starts 2021-07-06, "
            "so the 504-session window is first full at 2024-10-16 — 52% of evaluation "
            "dates ran on a partial cohort — and B1's 252-observation floor is "
            "unsatisfiable before 2023-10-16, so early B1 cones degrade to B0 "
            "(honest_frac 0.60 overall: ~40% of name-days scored the 'own-name' "
            "baseline AS the pooled baseline). G3 is therefore a ~60/40 blend of the "
            "own-name test and G2, not a fully independent second gate.",
            "REVIEW-3 (S5 IS FRAGILE, S3 IS NOT): under a 10-test Bonferroni floor "
            "(5 schemes x 2 baselines, 0.005), S5-vs-B0's one-sided p=0.0074 fails "
            "while S3 survives at p<0.0002 on both baselines; clustering deltas at the "
            "14 quarterly refits gives S3 t=3.23 (12/14 quarters positive) but S5 "
            "t=2.04, under the df=13 critical value. Read S3 as the finding and S5 as "
            "suggestive. The CI is stable across block lengths 21-126, so the block "
            "choice itself is sound.",
            "REVIEW-5 (NEGATIVE CONTROL, MEASURED): a state-independent noise "
            "partition over an above-floor fixture cohort scores mean delta "
            "-0.00054 across 40 seeds (never exactly zero — random cells are noisy "
            "subsamples of the marginal, so they price slightly WORSE than it). The "
            "harness manufactures no positive edge from partitioning alone, and the "
            "two CALIBRATED_ONLY schemes (S1 -0.00052, S2 -0.00028) sit at "
            "noise-partition level, which sharpens the S3/S5 contrast. Pinned by "
            "test_noise_partition_manufactures_no_edge.",
            "REVIEW-ORDERING (CONSISTENT WITH THE STANDARDIZER CAVEAT): ranked by "
            "delta vs B0 at H=21, every positive scheme is a trailing-vol transform "
            "(S3 rvol_z +0.00280, S5 trend x vol +0.00219, S4 range-coil +0.00091) "
            "and both non-vol schemes are negative (S2 -0.00028, S1 -0.00052) — "
            "exactly the ordering the standardizer-artifact mechanism predicts. This "
            "raises the prior on the 'vol-forecast correction' reading; the HAR "
            "discriminator decides it.",
            "REVIEW-7 (sharpe_ci): earlier artifacts annualized the delta-series "
            "Sharpe at 365; regenerated at 252. The quantity is a sign-check only.",
            "REVIEW-9 (SPLIT-STAMP MECHANISM): the ineligibility stamp marks bar i-1 "
            "via one-bar-ahead factor information (touched = step | roll(step, -1)). "
            "Feature-side removal only (7,554 of 3.69M rows); outcomes are computed "
            "on the already-repaired series and never read the stamp.",
        ],
    }
    return out, results, panel, cal


# ------------------------------------------------------------------ report
def _fmt_ci(d: dict) -> str:
    if not d or d.get("ci") is None:
        return "n/a"
    lo, _, hi = d["ci"]
    return f"{d['mean_delta']:+.5f} [{lo:+.5f}, {hi:+.5f}]"


def write_markdown(out: dict, path: Path) -> None:
    prereg = (Path(__file__).read_text(encoding="utf-8").split('"""', 2)[1]).strip()
    L = []
    L.append("# Pick-class conditional forward distributions — Phase-0 (diagnostic)")
    L.append("")
    L.append(f"**Family** `{out['family']}` · **Program** `{out['program']}` · "
             f"**Tier** {out['tier']}")
    L.append(f"**Generated** {out['generated_utc']} · **Runtime** {out['runtime_sec']:.0f}s")
    L.append("")
    L.append("Phase-0 measures. It promotes nothing and authorizes nothing: the verdicts "
             "below are diagnostic labels for a later adjudication, not a ship decision.")
    L.append("")
    L.append("## 0. Headline")
    L.append("")
    L.append("| Scheme | Cells | Verdict | G1 coverage | G2 vs B0 | G3 vs B1 | G4 honest |")
    L.append("|---|---|---|---|---|---|---|")
    for s in SCHEMES:
        g = out["gates"][s]
        L.append("| `{s}` | {c} | **{v}** | {c1} {p1} | {c2} {p2} | {c3} {p3} | {c4} {p4} |".format(
            s=s, c=out["schemes"][s]["cells_declared"], v=g["verdict"],
            c1=f"{g['G1_calibration']['coverage_80']:.3f}",
            p1="PASS" if g["G1_calibration"]["pass"] else "FAIL",
            c2=_fmt_ci(g["G2_skill_vs_B0"]), p2="PASS" if g["G2_skill_vs_B0"]["pass"] else "FAIL",
            c3=_fmt_ci(g["G3_skill_vs_B1"]), p3="PASS" if g["G3_skill_vs_B1"]["pass"] else "FAIL",
            c4=f"{g['G4_cell_honesty']['honest_frac']:.3f}",
            p4="PASS" if g["G4_cell_honesty"]["pass"] else "FAIL"))
    L.append("")
    L.append("Deltas are per-date **baseline minus scheme** mean pinball on the identical "
             "cross-section, so a positive number is skill. CI = circular block bootstrap, "
             f"block = {PRIMARY_H} (the outcome overlap), B = {BOOT_B}, seed = {BOOT_SEED}.")
    L.append("")
    e = out["eval_span"]
    L.append(f"**Evaluated** {e['n_dates_h21']:,} sessions ({e['first_eval']} to "
             f"{e['last_eval']}), {e['n_name_days_h21']:,} name-days, {e['n_names_h21']:,} "
             f"distinct names at H={PRIMARY_H}.")
    L.append("")
    L.append("## 1. Baselines (the nulls)")
    L.append("")
    L.append("| Arm | Mean pinball H21 | Coverage H21 | H10 cov | H63 cov |")
    L.append("|---|---|---|---|---|")
    for b in BASELINES:
        bb = out["baselines"][b]
        L.append(f"| `{b}` | {bb['mean_pinball_h21']:.5f} | {bb['coverage_80_h21']:.3f} | "
                 f"{bb['horizons']['H10']['coverage_80']:.3f} | "
                 f"{bb['horizons']['H63']['coverage_80']:.3f} |")
    L.append("")
    b0m = out["baselines"]["B0_pooled"]["mean_pinball_h21"]
    b1m = out["baselines"]["B1_ownname"]["mean_pinball_h21"]
    harder = "B0" if b0m <= b1m else "B1"
    L.append(f"**Read G2 and G3 as an unequal pair.** B1 estimates its quantiles from at "
             f"most {WINDOW} own-name observations; B0 estimates them from the whole pooled "
             f"cohort, which is millions. The smaller sample is the noisier estimator, so "
             f"the two gates are not equally hard — here **{harder} is the harder baseline** "
             f"({b0m:.5f} vs {b1m:.5f} mean pinball). A scheme that clears the easier gate "
             f"and fails the harder one has NOT shown skill; the binding evidence is the "
             f"harder one. This asymmetry is a property of the pre-registered design, "
             f"reported rather than repaired.")
    L.append("")
    L.append("## 2. Per-scheme detail")
    L.append("")
    for s in SCHEMES:
        g, sc = out["gates"][s], out["schemes"][s]
        L.append(f"### `{s}` — {g['verdict']}")
        L.append("")
        L.append(f"- Cells declared {sc['cells_declared']}, seen at H21 {sc['cells_seen_h21']}; "
                 f"above-floor share {g['G4_cell_honesty']['honest_frac']:.3f}")
        L.append(f"- Mean pinball H21 {sc['mean_pinball_h21']:.5f} · "
                 f"MAE-p05 tail hit {sc['mae_p05_tail_hit_h21']} (nominal 0.05)")
        er = sc["era_split_vs_B0"]
        L.append(f"- Era split vs B0: 2023-24 {er['era_2023_24']['mean_delta']:+.5f} "
                 f"({er['era_2023_24']['n_dates']}d) · 2025-26 "
                 f"{er['era_2025_26']['mean_delta']:+.5f} ({er['era_2025_26']['n_dates']}d) · "
                 f"sign stable: {er['sign_stable']}")
        br = sc["breach_run_h21"]
        b0br = out["baselines"]["B0_pooled"]["breach_run_h21"]
        L.append(f"- Breach clustering (report-only, mostly mechanical — see caveats): "
                 f"lag-1 autocorr {br['lag1_autocorr']} vs B0's {b0br['lag1_autocorr']}, "
                 f"longest run above nominal {br['max_run_above_nominal']} dates, "
                 f"{br['frac_dates_above_nominal']} of dates above nominal")
        L.append(f"- Raw-percent frame H21 (secondary; double-counts scale — see caveats): "
                 f"coverage {sc['raw_frame_H21']['coverage_80']:.3f}, delta vs B0 "
                 f"{_fmt_ci(sc['raw_frame_H21']['delta_vs_B0'])}")
        L.append("")
        L.append("| H | Coverage | Mean pinball | Δ vs B0 [95% CI] | Δ vs B1 [95% CI] |")
        L.append("|---|---|---|---|---|")
        for h in HORIZONS:
            hh = sc["horizons"][f"H{h}"]
            star = " (primary)" if h == PRIMARY_H else ""
            L.append(f"| {h}{star} | {hh['coverage_80']:.3f} | {hh['mean_pinball']:.5f} | "
                     f"{_fmt_ci(hh['delta_vs_B0'])} | {_fmt_ci(hh['delta_vs_B1'])} |")
        L.append("")
        L.append("Verdicts are issued at H=21 only; H=10 and H=63 are descriptive rows.")
        L.append("")
    L.append("## 3. Honest caveats")
    L.append("")
    for c in out["caveats"]:
        L.append(f"- {c}")
    L.append("")
    L.append("## 3b. Post-run review addenda (2026-08-06 adversarial review — "
             "disclosures only, nothing retuned)")
    L.append("")
    for c in out.get("post_run_review", []):
        L.append(f"- {c}")
    L.append("")
    d = out["data"]
    L.append("## 4. Data + universe as actually read")
    L.append("")
    L.append(f"- Store `{d['store']}` — {d['files_seen']:,} parquet files, "
             f"{d['files_read']:,} read, {d['prefilter_pass']:,} past the cheap prefilter")
    L.append(f"- Calendar {d['calendar_first']} to {d['calendar_last']} "
             f"({d['calendar_sessions']} sessions)")
    L.append(f"- Panel {d['panel_rows']:,} eligible observations across {d['panel_names']:,} names")
    L.append(f"- Splits repaired on {d['split_repaired_names']:,} names; "
             f"{d['split_bars_stamped']:,} split-print bars stamped ineligible")
    L.append(f"- {d['prices']}")
    L.append("")
    L.append("## 5. Frozen pre-registration (verbatim)")
    L.append("")
    L.append("```text")
    L.append(prereg)
    L.append("```")
    L.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-root", default=None, help="massive_stock_day directory")
    ap.add_argument("--max-names", type=int, default=None, help="smoke-run cap on files read")
    ap.add_argument("--out-json", default=str(RESULTS_JSON))
    ap.add_argument("--out-md", default=str(RESULTS_MD))
    args = ap.parse_args()

    store = resolve_data_root(args.data_root)
    if store is None:
        print("HALT: no massive_stock_day parquets found on the resolution ladder "
              "(--data-root / $MACRO_PRIMARY_DATA / <repo>/data/massive_stock_day / "
              "primary checkout). Refusing to emit a study with no data.", flush=True)
        return 2

    out, _wf, _panel, _cal = run_study(store, max_names=args.max_names)

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(out, indent=1, default=str) + "\n",
                                   encoding="utf-8")
    write_markdown(out, Path(args.out_md))

    print("\n=================== VERDICTS (H=21, vol-standardized) ===================")
    for s in SCHEMES:
        g = out["gates"][s]
        print(f"  {s:<14} {g['verdict']:<16} "
              f"G1 {'PASS' if g['G1_calibration']['pass'] else 'FAIL'} (cov "
              f"{g['G1_calibration']['coverage_80']:.3f})  "
              f"G2 {'PASS' if g['G2_skill_vs_B0']['pass'] else 'FAIL'}  "
              f"G3 {'PASS' if g['G3_skill_vs_B1']['pass'] else 'FAIL'}  "
              f"G4 {'PASS' if g['G4_cell_honesty']['pass'] else 'FAIL'}", flush=True)
    print(f"\nwrote {args.out_json}\nwrote {args.out_md}\n"
          f"runtime {out['runtime_sec']:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
