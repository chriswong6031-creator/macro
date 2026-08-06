"""W8 Ignition Layer — retro stand-in battery (S-COIL / S-RANKVEL / S-THRUST-LAG / S-INSIDER).

RESEARCH / SHADOW TIER. These are MEASUREMENTS, not signals. Nothing here touches
admission, ranking, sizing, or any site surface. Charter:
`research/PROPHET_US_IGNITION_LAYER_W8_BY_FABLE.md`.

Frame
-----
`data/baskets/ohlcv/*.parquet` — 2,768 US tickers, full OHLCV, 2014-01-02..2026-07-31.
This is the widest LOCAL panel: `data/massive_stock_day` is manifest-only in the checkout
(20,677 tickers described, zero data files — the store lives off the render path), so the
#4561 `close_panel()` route is unavailable here and the coverage delta is stated in the
charter §2 rather than assumed away. Benchmark: `data/yahoo/SPY.parquet`.
The store is SURVIVOR-LEAN (sampled 120 names: 119 carry bars to the final session) — a
named coverage debt, not a resolved one, exactly as W4 carried it.

Outcomes
--------
Forward H in (10, 21, 63) sessions, three readings per event:
  raw            — plain forward return
  excess_spy     — minus SPY over the same window
  excess_med     — minus the same-day cross-sectional median (date-demeaned by construction)

Ruler (W4 gate-matched, `research/winners/FINGERPRINT_CONTROLS_W4.md`)
---------------------------------------------------------------------
Every sensor's PRIMARY statistic is a matched-set delta:
    delta = excess(event) - median(excess(matched controls, SAME session))
aggregated as the median over events, with a month-block bootstrap whose resampling atom
is the matched set, plus a ticker-cluster bootstrap as the recurrence robustness check.
Controls are GATE-MATCHED per sensor (they pass the same trigger and differ only on the
axis under test) because full-population effect sizes are known-inflated and, per the W4
adjudication, may not be cited.

Method guards (standins idiom)
------------------------------
Pinned REPRO_ASOF; date-demeaned beside raw; per-name-first beside pooled;
loser := excess < -3pp at H (threshold stated, medians reported so no verdict hangs on
it); half-split robustness; thin cells print n and nothing else; per-leg fire counts so a
dead leg is visible rather than silently null; numpy booleans compared with bool().

NO COMPOSITE. Each sensor is reported alone. The INTERSECTION cohort is reported as its
own table — an intersection is a filter, never a weight, and no score is formed anywhere.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "ignition_standins_results.json")
os.chdir(REPO)
sys.path.insert(0, REPO)

REPRO_ASOF = "2026-07-31"       # panel's last complete session; every series truncated here
HORIZONS = (10, 21, 63)
LOSER_PP = -3.0
N_BOOT = 2000
SEED = 20260805

# --- S-COIL ---------------------------------------------------------------
ATR_WIN = 21          # trailing ATR window
PCT_WIN = 252         # own-history window for the ATR percentile
PCT_MAX = 0.25        # compression := ATR percentile < p25
MA_WIN = 50           # uptrend reference
MA_SLOPE = 10         # 50dMA "rising" lookback
BREAK_WIN = 21        # prior N-day high the release must clear
COMP_LOOKBACK = 21    # window in which compressed sessions are counted
COMP_MIN = 10         # >= 10 compressed sessions required

# --- S-RANKVEL ------------------------------------------------------------
RS_WIN = 63           # return window whose cross-sectional rank is the RS percentile
VEL_WIN = 5           # acceleration measured over 5 sessions
VEL_MIN = 0.20        # >= +20 percentile points
RS_LEVEL = 0.70       # crossing above p70
LEVEL_TOL = 0.05      # control must sit within +/- 5 percentile points of the event
FLAT_MAX = 0.05       # control must NOT have accelerated (delta < +5 points)

# --- S-THRUST-LAG ---------------------------------------------------------
HIGH20 = 20           # member "above its own 20d high"
THRUST_LO = 0.30      # thrust := member fraction crosses from < 0.30 ...
THRUST_HI = 0.50      # ... to > 0.50 ...
THRUST_WIN = 5        # ... within 5 sessions
MIN_MEMBERS = 6       # a basket needs this many covered+active members to be readable

# --- S-INSIDER ------------------------------------------------------------
CLUSTER_N = 2         # >= 2 DISTINCT insider buyers ...
CLUSTER_WIN = 60      # ... within a trailing 60 calendar days


# ==========================================================================
# panel
# ==========================================================================
def load_panel(asof: str = REPRO_ASOF, limit: int | None = None) -> dict[str, pd.DataFrame]:
    """Wide (date x ticker) frames for close/high/low/volume, truncated at `asof`."""
    files = sorted(glob.glob("data/baskets/ohlcv/*.parquet"))
    if limit:
        files = files[:limit]
    cols: dict[str, dict[str, pd.Series]] = {f: {} for f in ("close", "high", "low", "volume")}
    for f in files:
        t = os.path.basename(f)[:-8]
        try:
            d = pd.read_parquet(f, columns=["close", "high", "low", "volume"])
        except Exception:
            continue
        if d.empty:
            continue
        for f_ in cols:
            cols[f_][t] = d[f_]
    out = {}
    for f_, series in cols.items():
        w = pd.DataFrame(series).sort_index().astype("float32")
        out[f_] = w.loc[w.index <= pd.Timestamp(asof)]
    return out


def load_spy(asof: str = REPRO_ASOF) -> pd.Series:
    s = pd.read_parquet("data/yahoo/SPY.parquet")["close"]
    s = s.sort_index()
    return s.loc[s.index <= pd.Timestamp(asof)]


def forward_frames(close: pd.DataFrame, spy: pd.Series) -> dict[int, dict[str, pd.DataFrame]]:
    """For each horizon: raw forward return, excess vs SPY, excess vs same-day median."""
    out: dict[int, dict[str, pd.DataFrame]] = {}
    spy_al = spy.reindex(close.index).ffill()
    for h in HORIZONS:
        raw = close.shift(-h) / close - 1.0
        spy_fwd = spy_al.shift(-h) / spy_al - 1.0
        ex_spy = raw.sub(spy_fwd, axis=0)
        ex_med = raw.sub(raw.median(axis=1), axis=0)
        out[h] = {"raw": raw, "excess_spy": ex_spy, "excess_med": ex_med}
    return out


# ==========================================================================
# event detectors — pure, panel-in / panel-out (unit-tested on synthetic series)
# ==========================================================================
def true_range(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    pc = close.shift(1)
    a = (high - low).to_numpy()
    b = (high - pc).abs().to_numpy()
    c = (low - pc).abs().to_numpy()
    return pd.DataFrame(np.maximum(np.maximum(a, b), c), index=close.index, columns=close.columns)


def coil_compression(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame) -> pd.DataFrame:
    """UPTREND coil: low ATR percentile AND price above a RISING 50dMA.

    This is deliberately NOT a bottoming state. The bottom-radar PRIMED tier was killed as
    a directional durable-bottom gate (DO_NOT_REBUILD §2), and the DURABLE_BOTTOM H2 result
    falsified 'calm base' arming after a washout. Requiring price ABOVE a RISING 50dMA puts
    this state in the continuation regime those two verdicts did not test.
    """
    atr = true_range(high, low, close).rolling(ATR_WIN).mean()
    atr_pct = atr.rolling(PCT_WIN).rank(pct=True)
    ma = close.rolling(MA_WIN).mean()
    rising = ma > ma.shift(MA_SLOPE)
    return (atr_pct < PCT_MAX) & (close > ma) & rising


def coil_events(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame) -> dict:
    """Event = the RELEASE bar: first close above the prior 21d high after >=10 compressed
    sessions. The compression state is read at t-1, so the release bar's own range can never
    enter the ATR window that admits it (the W4 onset-bar lesson).

    LEGALITY: this instrument grades the release bar ONLY. It never surfaces, ranks, or
    reports the compressed/'armed' state as a standalone read — that is the arming variant
    BANNED by ESX section 9 / DT-R5. Volume carries no leg here at all (ESX RUL-1).
    """
    compressed = coil_compression(close, high, low)
    comp_run = compressed.rolling(COMP_LOOKBACK).sum() >= COMP_MIN
    prior_high = high.rolling(BREAK_WIN).max().shift(1)
    breakout = close > prior_high
    first = breakout & ~(breakout.shift(1).fillna(False).astype(bool))
    armed_prev = comp_run.shift(1).fillna(False).astype(bool)
    events = first & armed_prev
    controls = first & ~armed_prev          # GATE-MATCHED: same release, no compression
    diag = {
        "compressed_name_days": int(compressed.to_numpy().sum()),
        "comp_run_name_days": int(comp_run.to_numpy().sum()),
        "breakout_name_days": int(breakout.to_numpy().sum()),
        "first_breakout_name_days": int(first.to_numpy().sum()),
        "events": int(events.to_numpy().sum()),
        "gate_matched_controls": int(controls.to_numpy().sum()),
    }
    return {"events": events, "controls": controls, "diag": diag}


def rankvel_events(close: pd.DataFrame) -> dict:
    """Cross-sectional acceleration: RS percentile (63d return rank, PIT per session) gains
    >= +20 points over 5 sessions AND crosses above p70.

    Controls are LEVEL-MATCHED: same-day names sitting within +/-5 percentile points of the
    event's own level but WITHOUT the acceleration. The axis under test is the DERIVATIVE,
    so the level must be held fixed or the comparison just re-measures momentum.

    Nearest prior: W4 tested `rs_turn_21_63` pre-onset and it was NULL. This is a different
    construction (percentile-change magnitude + level crossing, level-matched controls), and
    a null here would be a second strike on the rs-derivative family, not a repeat of one.
    """
    r = close / close.shift(RS_WIN) - 1.0
    pct = r.rank(axis=1, pct=True)
    prev = pct.shift(VEL_WIN)
    delta = pct - prev
    events = (delta >= VEL_MIN) & (pct >= RS_LEVEL) & (prev < RS_LEVEL)
    slow = (delta < FLAT_MAX) & (pct >= RS_LEVEL)     # at level, arrived without acceleration
    diag = {
        "pct_covered_name_days": int(pct.notna().to_numpy().sum()),
        "accel_name_days": int((delta >= VEL_MIN).to_numpy().sum()),
        "at_level_name_days": int((pct >= RS_LEVEL).to_numpy().sum()),
        "crossed_level_name_days": int(((pct >= RS_LEVEL) & (prev < RS_LEVEL)).to_numpy().sum()),
        "events": int(events.to_numpy().sum()),
        "level_matched_pool": int(slow.to_numpy().sum()),
    }
    return {"events": events, "pct": pct, "slow": slow, "diag": diag}


def above_20d_high(close: pd.DataFrame, high: pd.DataFrame) -> pd.DataFrame:
    return close > high.rolling(HIGH20).max().shift(1)


def active_members(basket: dict, day: pd.Timestamp, covered: set[str]) -> list[str]:
    """PIT membership: honor added/removed dates."""
    out = []
    ds = str(day.date())
    for m in basket.get("members", []):
        t = m.get("ticker")
        if t not in covered:
            continue
        added, removed = m.get("added"), m.get("removed")
        if added and ds < added:
            continue
        if removed and ds >= removed:
            continue
        out.append(t)
    return out


def thrust_lag_events(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                      baskets: dict) -> dict:
    """Theme thrust -> coiled laggard.

    Thrust = the fraction of a theme's PIT-active members trading above their own 20d high
    crosses from < 0.30 to > 0.50 within 5 sessions. Candidate = a member that is BELOW its
    own 20d high at thrust time AND carries S-COIL compression.

    Two control arms, both same-session:
      (a) already_moved — members ABOVE their 20d high at thrust (the names the theme has
          already paid for);
      (b) coiled_nonthrust — compressed, below-20d-high names in themes NOT thrusting that
          day (isolates the theme context from the compression itself).

    This composes the measured laggard-cross positive (RESULTS_2026-08-03: the same 2D cross
    on RS63<=0.40 laggards printed +0.33% pooled / +1.44% per-name vs the leader-reset
    family's -1.50% / -2.12%) with theme context.

    Ignition Radar reconciliation (charter section 4): the radar's ignition definition and
    this thrust definition are the SAME FAMILY, different construction. This instrument is a
    measurement; it creates no rotation surface and no parallel authority.
    """
    a20 = above_20d_high(close, high)
    compressed = coil_compression(close, high, low)
    covered = set(close.columns)
    idx = close.index
    colpos = {t: i for i, t in enumerate(close.columns)}
    a20_np = a20.to_numpy()
    comp_np = compressed.to_numpy()
    day_str = np.array([str(d.date()) for d in idx])

    frac_by_basket: dict[str, pd.Series] = {}
    active_by_basket: dict[str, dict[pd.Timestamp, list[str]]] = {}
    for bid, b in baskets.items():
        if str(bid).startswith("us_sector_"):
            continue                     # GICS pseudo-baskets are not curation
        members = [m for m in b.get("members", []) if m.get("ticker") in covered]
        if len({m["ticker"] for m in members}) < MIN_MEMBERS:
            continue
        # PIT membership as a (days x members) mask, built vectorised over the date axis
        mcols, mask_cols = [], []
        for m in members:
            t = m["ticker"]
            live = np.ones(len(idx), dtype=bool)
            if m.get("added"):
                live &= day_str >= m["added"]
            if m.get("removed"):
                live &= day_str < m["removed"]
            mcols.append(colpos[t])
            mask_cols.append(live)
        if not mcols:
            continue
        mpos = np.asarray(mcols)
        live_mat = np.column_stack(mask_cols)                 # days x members
        sub = a20_np[:, mpos]                                 # days x members
        n_live = live_mat.sum(axis=1)
        n_above = (sub & live_mat).sum(axis=1)
        fr = np.where(n_live >= MIN_MEMBERS, n_above / np.maximum(n_live, 1), np.nan)
        frac_by_basket[bid] = pd.Series(fr, index=idx)
        tick_arr = np.array([m["ticker"] for m in members])
        active_by_basket[bid] = {
            idx[i]: list(tick_arr[live_mat[i]]) for i in range(len(idx))
            if n_live[i] >= MIN_MEMBERS}

    events, moved, thrust_days = [], [], 0
    thrust_flags = pd.DataFrame(False, index=idx, columns=list(frac_by_basket))
    for bid, fr in frac_by_basket.items():
        lo_recent = (fr < THRUST_LO).rolling(THRUST_WIN).max().shift(1)
        fired = (fr > THRUST_HI) & (lo_recent == 1.0)
        fired = fired & ~(fired.shift(1).fillna(False).astype(bool))
        thrust_flags[bid] = fired.reindex(idx).fillna(False)
        rp = {d: i for i, d in enumerate(idx)}
        for day in idx[fired.reindex(idx).fillna(False).to_numpy()]:
            thrust_days += 1
            i = rp[day]
            for t in active_by_basket[bid].get(day, []):
                j = colpos[t]
                if bool(a20_np[i, j]):
                    moved.append({"date": day, "ticker": t, "basket": bid})
                elif bool(comp_np[i, j]):
                    events.append({"date": day, "ticker": t, "basket": bid})

    # arm (b): compressed, below-20d-high names on days their own themes are NOT thrusting
    thrusting_names_by_day: dict[pd.Timestamp, set[str]] = {}
    for bid, fired in thrust_flags.items():
        for day in idx[fired.to_numpy()]:
            thrusting_names_by_day.setdefault(day, set()).update(
                active_by_basket[bid].get(day, []))
    ev_days = sorted({e["date"] for e in events})
    rowpos = {d: i for i, d in enumerate(idx)}
    cols = np.asarray(close.columns)
    nonthrust = []
    for day in ev_days:
        i = rowpos[day]
        hot = thrusting_names_by_day.get(day, set())
        sel = comp_np[i] & ~a20_np[i]
        for t in cols[sel]:
            if t not in hot:
                nonthrust.append({"date": day, "ticker": t})

    diag = {
        "baskets_read": len(frac_by_basket),
        "thrust_events": thrust_days,
        "candidates_coiled_laggard": len(events),
        "control_already_moved": len(moved),
        "control_coiled_nonthrust": len(nonthrust),
    }
    return {"events": pd.DataFrame(events), "moved": pd.DataFrame(moved),
            "nonthrust": pd.DataFrame(nonthrust), "diag": diag}


def insider_cluster_events(panel: pd.DataFrame, buy_col: str, date_col: str,
                           person_col: str, ticker_col: str) -> pd.DataFrame:
    """Cluster accumulation: >= CLUSTER_N DISTINCT insider buyers within a trailing
    CLUSTER_WIN calendar days. Event date = the SECOND buyer's FILING date (not the trade
    date) — the filing is when the market could know, so PIT correctness requires it.

    Returns one row per cluster onset (ticker, event_date, n_buyers).
    """
    df = panel[[ticker_col, date_col, person_col, buy_col]].copy()
    df = df[df[buy_col].astype(bool)]
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.dropna(subset=[ticker_col, date_col, person_col])
    df = df.sort_values(date_col)
    rows = []
    for t, g in df.groupby(ticker_col, sort=False):
        g = g.sort_values(date_col)
        dates = g[date_col].to_numpy()
        people = g[person_col].to_numpy()
        last_fire = None
        for i in range(len(g)):
            lo = dates[i] - np.timedelta64(CLUSTER_WIN, "D")
            win = (dates <= dates[i]) & (dates > lo)
            distinct = len(set(people[win]))
            if distinct >= CLUSTER_N:
                d = pd.Timestamp(dates[i])
                # one fire per cluster: suppress until the window clears
                if last_fire is not None and (d - last_fire).days <= CLUSTER_WIN:
                    continue
                rows.append({"ticker": t, "date": d, "n_buyers": int(distinct)})
                last_fire = d
    return pd.DataFrame(rows)


# ==========================================================================
# grading
# ==========================================================================
def _cell(vals: pd.Series, tickers: pd.Series) -> dict:
    """Standins-idiom cohort cell. Thin cells print n and nothing else."""
    if len(vals) < 20:
        return {"n": int(len(vals)), "thin": True}
    byname = pd.DataFrame({"v": vals.to_numpy(), "t": tickers.to_numpy()}).groupby("t")["v"].median()
    return {
        "n": int(len(vals)),
        "names": int(byname.shape[0]),
        "median_pp": round(float(vals.median()) * 100, 2),
        "mean_pp": round(float(vals.mean()) * 100, 2),
        "per_name_median_pp": round(float(byname.median()) * 100, 2),
        "win_pct": round(float((vals > 0).mean() * 100), 1),
        "loser_rate_pct": round(float((vals * 100 < LOSER_PP).mean() * 100), 1),
    }


def _block_ci(deltas: np.ndarray, blocks: np.ndarray, b: int = N_BOOT,
              seed: int = SEED) -> tuple[float, float]:
    """Block bootstrap on the median of per-event deltas; `blocks` is the resampling atom
    (calendar month for the primary, ticker for the recurrence check)."""
    uniq = np.unique(blocks)
    if len(uniq) < 3 or len(deltas) < 20:
        return (float("nan"), float("nan"))
    by = {u: deltas[blocks == u] for u in uniq}
    rng = np.random.default_rng(seed)
    meds = np.empty(b)
    for i in range(b):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        meds[i] = np.median(np.concatenate([by[u] for u in pick]))
    return (float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5)))


def attach_flat_controls(ev: pd.DataFrame, ctrl_flags: pd.DataFrame,
                         out_frame: pd.DataFrame) -> pd.DataFrame:
    """Control median per SESSION (the control set does not depend on the event's own
    value) — used by S-COIL, S-THRUST-LAG arm (b) and S-INSIDER's market arm."""
    vals = out_frame.where(ctrl_flags)
    med = vals.median(axis=1, skipna=True)
    cnt = vals.notna().sum(axis=1)
    ev = ev.copy()
    ev["ctrl_median"] = ev["date"].map(med)
    ev["ctrl_n"] = ev["date"].map(cnt)
    return ev


def _positions(ev: pd.DataFrame, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    di = frame.index.get_indexer(pd.to_datetime(ev["date"]))
    ti = frame.columns.get_indexer(ev["ticker"])
    return di, ti


def attach_level_controls(ev: pd.DataFrame, level: pd.DataFrame, pool: pd.DataFrame,
                          out_frame: pd.DataFrame, tol: float = LEVEL_TOL) -> pd.DataFrame:
    """Control median per EVENT, matched on the event's own level (+/- tol). One sorted
    array per session + searchsorted keeps this O(log n) per event instead of a rescan."""
    ev = ev.copy()
    if ev.empty:
        ev["ctrl_median"] = []
        ev["ctrl_n"] = []
        return ev
    di, ti = _positions(ev, level)
    lvl_all = level.to_numpy(dtype=float)
    pool_all = pool.to_numpy(dtype=bool)
    out_all = out_frame.to_numpy(dtype=float)
    lvl_ev = np.where((di >= 0) & (ti >= 0), lvl_all[di, ti], np.nan)
    meds = np.full(len(ev), np.nan)
    ns = np.zeros(len(ev), dtype=int)
    cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for k in range(len(ev)):
        lv, d = lvl_ev[k], di[k]
        if d < 0 or not np.isfinite(lv):
            continue
        if d not in cache:
            ok = pool_all[d] & np.isfinite(lvl_all[d]) & np.isfinite(out_all[d])
            l_ok, o_ok = lvl_all[d][ok], out_all[d][ok]
            order = np.argsort(l_ok, kind="stable")
            cache[d] = (l_ok[order], o_ok[order])
        ls, os_ = cache[d]
        i0, i1 = np.searchsorted(ls, [lv - tol, lv + tol])
        sel = os_[i0:i1]
        ns[k] = len(sel)
        if len(sel) >= 3:
            meds[k] = float(np.median(sel))
    ev["ctrl_median"] = meds
    ev["ctrl_n"] = ns
    return ev


def matched_delta(ev: pd.DataFrame, out_frame: pd.DataFrame, min_ctrl: int = 3) -> dict:
    """Primary statistic: median over events of
    [ excess(event) - median(excess(same-session matched controls)) ].

    `ev` must already carry `ctrl_median` / `ctrl_n` from one of the attach_* helpers.
    """
    if ev.empty or "ctrl_median" not in ev:
        return {"n_matched": 0, "thin": True}
    di, ti = _positions(ev, out_frame)
    out_all = out_frame.to_numpy(dtype=float)
    ev_val = np.where((di >= 0) & (ti >= 0), out_all[di, ti], np.nan)
    cm = ev["ctrl_median"].to_numpy(dtype=float)
    keep = np.isfinite(ev_val) & np.isfinite(cm) & (ev["ctrl_n"].to_numpy() >= min_ctrl)
    if int(keep.sum()) < 20:
        return {"n_matched": int(keep.sum()), "thin": True}
    dz = ev_val[keep] - cm[keep]
    dts = pd.to_datetime(pd.Series(ev["date"].to_numpy()[keep]))
    mo = np.array([f"{d.year}-{d.month:02d}" for d in dts])
    tk = np.asarray(ev["ticker"].to_numpy()[keep])
    ev_vals = ev_val[keep]
    lo, hi = _block_ci(dz, mo)
    clo, chi = _block_ci(dz, tk, seed=SEED + 1)
    byname = pd.DataFrame({"d": dz, "t": tk}).groupby("t")["d"].median()
    return {
        "n_matched": int(len(dz)),
        "names": int(len(np.unique(tk))),
        "months": int(len(np.unique(mo))),
        "delta_pp": round(float(np.median(dz)) * 100, 2),
        "per_name_delta_pp": round(float(byname.median()) * 100, 2),
        "month_block_ci_pp": [round(lo * 100, 2), round(hi * 100, 2)],
        "ticker_cluster_ci_pp": [round(clo * 100, 2), round(chi * 100, 2)],
        "excludes_zero": bool(np.isfinite(lo) and (lo > 0 or hi < 0)),
        "event_median_pp": round(float(np.median(ev_vals)) * 100, 2),
    }


def half_split(ev: pd.DataFrame, out_frame: pd.DataFrame) -> dict:
    """Same matched delta, computed independently in each time half."""
    if ev.empty or "ctrl_median" not in ev:
        return {"thin": True}
    mid = pd.to_datetime(ev["date"]).median()
    out = {}
    for label, m in (("first_half", ev[pd.to_datetime(ev["date"]) <= mid]),
                     ("second_half", ev[pd.to_datetime(ev["date"]) > mid])):
        r = matched_delta(m, out_frame)
        out[label] = {"n": r.get("n_matched", 0), "delta_pp": r.get("delta_pp", "thin"),
                      "ci_pp": r.get("month_block_ci_pp", "thin")}
    return out


def grade_sensor(ev: pd.DataFrame, fwd: dict, attach) -> dict:
    """Full per-sensor read: cohort cells (raw / vs SPY / vs day-median), the matched-set
    delta with both bootstraps, and the half-split — at every horizon. No composite is
    formed and no sensor is combined with another here."""
    res: dict = {}
    for h in HORIZONS:
        block: dict = {}
        for kind in ("raw", "excess_spy", "excess_med"):
            frame = fwd[h][kind]
            di, ti = _positions(ev, frame)
            arr = frame.to_numpy(dtype=float)
            vals = np.where((di >= 0) & (ti >= 0), arr[di, ti], np.nan)
            ok = np.isfinite(vals)
            block[kind] = _cell(pd.Series(vals[ok]),
                                pd.Series(np.asarray(ev["ticker"])[ok]))
        primary = fwd[h]["excess_spy"]
        ev_c = attach(ev, primary)
        md = matched_delta(ev_c, primary)
        block["matched_delta_vs_controls"] = md
        block["half_split"] = half_split(ev_c, primary)
        res[f"H{h}"] = block
    return res


def bool_frame_to_events(flags: pd.DataFrame) -> pd.DataFrame:
    arr = flags.to_numpy()
    di, ti = np.nonzero(arr)
    return pd.DataFrame({"date": flags.index[di], "ticker": flags.columns[ti]})


def events_to_bool_frame(ev: pd.DataFrame, like: pd.DataFrame) -> pd.DataFrame:
    """Inverse of bool_frame_to_events, on the grid of `like`."""
    arr = np.zeros(like.shape, dtype=bool)
    if ev is not None and not ev.empty:
        di, ti = _positions(ev, like)
        ok = (di >= 0) & (ti >= 0)
        arr[di[ok], ti[ok]] = True
    return pd.DataFrame(arr, index=like.index, columns=like.columns)


# ==========================================================================
# intersection — a FILTER, never a weight
# ==========================================================================
def intersection_cohort(sensors: dict[str, pd.DataFrame], close: pd.DataFrame,
                        window: int = 5, min_sensors: int = 2) -> pd.DataFrame:
    """Name-days where >= min_sensors distinct sensors are KNOWN to have fired within the
    trailing `window` sessions.

    The window is BACKWARD-ONLY and the observation is stamped on the session the SECOND
    distinct sensor fires. A symmetric +/- window would select the cohort using up to
    `window` sessions of future information — and because every sensor here is a breakout /
    acceleration event, "a sensor will fire in the next 5 sessions" is very nearly "the
    price rose in the next 5 sessions". That lookahead inflated this cohort to +6.6pp /
    87% win at H=10 in the first run of this battery; the backward-only form below is the
    corrected construction, and the inflated numbers are not reported anywhere.

    Reported as its own cohort with its own n. No score is formed, no sensor is weighted,
    and co-firing confers nothing — this table exists to show what the lens cohort looks
    like, and the charter's miss-audit grades that cohort, not a blend.
    """
    pos = {d: i for i, d in enumerate(close.index)}
    n = len(close.index)
    # per (ticker, sensor): the sessions on which that sensor is "known" (fire .. fire+window)
    known: dict[tuple[str, int], set[str]] = {}
    for name, ev in sensors.items():
        if ev is None or ev.empty:
            continue
        for d, t in zip(pd.to_datetime(ev["date"]), ev["ticker"]):
            i = pos.get(d)
            if i is None:
                continue
            for j in range(i, min(n, i + window + 1)):
                known.setdefault((t, j), set()).add(name)
    rows = [{"date": close.index[j], "ticker": t, "n_sensors": len(s),
             "sensors": "+".join(sorted(s))}
            for (t, j), s in known.items() if len(s) >= min_sensors]
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "n_sensors", "sensors"])
    out = pd.DataFrame(rows).sort_values(["ticker", "date"]).reset_index(drop=True)
    # collapse consecutive sessions of the same (ticker, sensor-set) to the FIRST one —
    # that first session is the day the second sensor fired, i.e. the first knowable day.
    gap = out.groupby(["ticker", "sensors"])["date"].diff().dt.days
    out["grp"] = gap.isna() | gap.gt(window * 2)
    out["grp"] = out["grp"].cumsum()
    return out.groupby(["ticker", "sensors", "grp"], as_index=False).first()[
        ["date", "ticker", "n_sensors", "sensors"]]


def insider_census(close: pd.DataFrame) -> dict:
    """S-INSIDER is DETECTED and CENSUSED here but deliberately NOT GRADED.

    Kills-check outcome (the fence: a construction that matches a kill becomes a named gap
    instead of a run). The briefed construction — cluster of >= 2 distinct open-market
    buyers, graded forward at H=10/21/63 against SECTOR-matched controls — collides with
    the `esx_insider_sponsor` family (DO_NOT_REBUILD section 2, 'Entry-time thesis at 21d
    (insider / macro / positioning) REFUTED 3-for-3', RUL-18..29):

      * That study tested the SAME core predicate (I1: cluster >= 2 distinct open-market
        buyers on filing_date windows; I1-sens >= 3; I2 cluster >= 2 around the fire) at the
        SAME primary horizon (21d).
      * Its finding was not a plain null. Unconditional insider strata were ADVERSE
        (I1 baskets stop5 +6.22pp, CI [+4.90, +7.37], BH-rejected), and the I1w reserve
        contrast attributed that adversity to the WASHOUT STATE, not to the cluster
        (within-washout marginal +0.5pp, CI [-0.8, +1.8], n_treat=3,815).
      * The decisive methodological lesson is exactly what sector-matching would miss:
        controls must hold the co-occurring STATE fixed, not merely the sector. Sector-
        matched controls would re-estimate the state, reproduce the adverse sign, and read
        as a discovery. Running it would also spend a contrast the family has already
        closed ('no re-run of these contrasts', A2_INSIDER_REPORT.md).

    What stays OPEN, per the same ruling, and is the lawful re-entry path:
      (a) the 63/126d HOLDABILITY lane, coordinated with esx_ql_overlay / S-QL (RUL-20);
      (b) the 252d long-hold ruler `long_hold.insider_sponsor_lh` (Ruler-H ~2027-H2);
      (c) display-only `sponsor_present`-style context, which carries no ranking authority.
    Any of those needs its own prereg and its own lane owner; none is claimed here.

    So this function measures COVERAGE only — how many cluster events the store actually
    supports, over what span, on how many names. That confers nothing, re-runs no killed
    contrast, and is precisely what a future prereg needs in order to be powered.
    """
    out: dict = {
        "status": "NAMED GAP — detector built and censused, outcomes deliberately NOT graded",
        "reason": "collides with esx_insider_sponsor / RUL-18..29 (21d entry-time insider "
                  "cluster, REFUTED 3-for-3; adversity attributed to the washout state by "
                  "the I1w within-washout contrast). Sector-matched controls do not hold "
                  "the co-occurring state fixed, which is the exact error that study "
                  "diagnosed.",
        "lawful_reentry": ["63/126d holdability lane coordinated with esx_ql_overlay/S-QL "
                           "(RUL-20)",
                           "252d long_hold.insider_sponsor_lh Ruler-H (~2027-H2)",
                           "display-only sponsor_present context (no ranking authority)"],
        "pit_basis": "filing_date, never trans_date (RUL-23 known-date law; the store's "
                     "median filing lag is 2 trading days)",
        "buy_definition": "code == 'P' (open-market purchase); the collector keeps only "
                          "P/S and drops grants/exercises/gifts (config.yml open_market_codes)",
        "distinct_buyer_key": "rptownercik — the same distinct-insider key engine/"
                              "insider_factor.py uses; context_api._insider_dim does NOT "
                              "dedupe by insider and is therefore not the right reader here",
    }
    try:
        files = sorted(glob.glob("data/sec_insider/panel/*.parquet"))
        if not files:
            out["coverage"] = {"error": "data/sec_insider/panel is empty"}
            return out
        panel = pd.concat(
            [pd.read_parquet(f, columns=["ticker", "filing_date", "code", "rptownercik"])
             for f in files], ignore_index=True)
        panel["is_buy"] = panel["code"].astype(str).str.upper() == "P"
        ev = insider_cluster_events(panel, "is_buy", "filing_date", "rptownercik", "ticker")
        in_panel = ev[ev["ticker"].isin(set(close.columns))]
        out["coverage"] = {
            "panel_rows": int(len(panel)),
            "panel_tickers": int(panel["ticker"].nunique()),
            "filing_date_range": [str(panel["filing_date"].min())[:10],
                                  str(panel["filing_date"].max())[:10]],
            "buy_rows": int(panel["is_buy"].sum()),
            "cluster_events": int(len(ev)),
            "cluster_event_names": int(ev["ticker"].nunique()) if len(ev) else 0,
            "cluster_events_on_price_panel": int(len(in_panel)),
            "cluster_event_names_on_price_panel": (int(in_panel["ticker"].nunique())
                                                   if len(in_panel) else 0),
            "event_date_range": ([str(ev["date"].min())[:10], str(ev["date"].max())[:10]]
                                 if len(ev) else None),
            "insider_panel_ends": "2026-03-31 — four months short of the price panel's "
                                  "2026-07-31, a coverage debt any future prereg inherits",
        }
    except Exception as exc:                      # census must never fail the battery
        out["coverage"] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def foresight_census(close: pd.DataFrame) -> dict:
    """Charter section 5: is the Thematic Foresight Desk's per-theme STAGE history deep
    enough to run a lead-time study TODAY? Census, not a run."""
    out: dict = {"question": "does theme-stage lead theme price, and by how much"}
    try:
        rows = [json.loads(x) for x in open("data/foresight/log.jsonl") if x.strip()]
        by: dict[str, list] = {}
        for r in sorted(rows, key=lambda r: r["asof"]):
            by.setdefault(r["theme"], []).append(r)
        trans = [{"theme": t, "date": pd.Timestamp(b["asof"]), "from": a["stage"],
                  "to": b["stage"], "members": b.get("members", [])}
                 for t, seq in by.items() for a, b in zip(seq, seq[1:])
                 if a["stage"] != b["stage"]]
        tr = pd.DataFrame(trans)
        sess = close.index
        matured = {}
        for h in HORIZONS:
            cutoff = sess[-(h + 1)] if len(sess) > h else None
            matured[f"H{h}"] = {
                "last_date_with_matured_window": str(cutoff.date()) if cutoff is not None else None,
                "matured_transitions": int((tr["date"] <= cutoff).sum()) if cutoff is not None else 0,
            }
        members = {m for r in trans for m in r["members"]}
        out.update({
            "history_exists": True,
            "store": "data/foresight/log.jsonl",
            "rows": len(rows),
            "distinct_asof": int(len({r["asof"] for r in rows})),
            "span": [min(r["asof"] for r in rows), max(r["asof"] for r in rows)],
            "themes": len(by),
            "stage_transitions": len(tr),
            "member_tickers": len(members),
            "member_tickers_on_price_panel": len(members & set(close.columns)),
            "matured_by_horizon": matured,
            "verdict": (
                "SPEC ONLY — DO NOT RUN YET. The history EXISTS (correcting the brief's "
                "assumption), but it is ~5 weeks deep: only H=10 has any matured "
                "transitions and H=21 / H=63 have ZERO. 33 transitions across 17 themes is "
                "below any inferential floor here — the month-block bootstrap this battery "
                "uses needs >= 3 distinct months and the log spans about one. The log is "
                "already accruing, so the clock is real rather than blocked."),
        })
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def main() -> None:
    limit = int(os.environ.get("IGNITION_LIMIT", "0")) or None
    P = load_panel(limit=limit)
    close, high, low = P["close"], P["high"], P["low"]
    spy = load_spy()
    fwd = forward_frames(close, spy)

    res: dict = {
        "meta": {
            "repro_asof": REPRO_ASOF,
            "status": "RESEARCH / SHADOW TIER — measurements only; no admission, rank, "
                      "size, gate, or site surface anywhere in this file",
            "frame": "data/baskets/ohlcv/*.parquet (split+dividend-adjusted close, "
                     "verified equal to data/yahoo adjusted close on AAPL/KO/XOM)",
            "benchmark": "data/yahoo/SPY.parquet close",
            "panel": {"names": int(close.shape[1]), "sessions": int(close.shape[0]),
                      "first": str(close.index.min().date()),
                      "last": str(close.index.max().date())},
            "coverage_delta": (
                "The #4561 close_panel() over data/massive_stock_day (~2,252 cols) is NOT "
                "merged (branch origin/claude/prophet-us-scan-tier, tip 5bb16b514f1) and "
                "the store's parquets are R2-only (.gitignore:246 — the checkout holds "
                "only _manifest.json + _backfill_state.json). This frame is therefore "
                "WIDER and far DEEPER than the merged alternatives: 2,768 names x 3,163 "
                "sessions from 2014-01-02, vs the 3-tier breadth union's 1,540 names from "
                "2023-06-27 (1,897 with the yahoo overlay)."),
            "survivorship": "SURVIVOR-LEAN and stated, not resolved: of 120 sampled names, "
                            "119 carry bars to the final session. Same debt W4 carried.",
            "horizons": list(HORIZONS),
            "loser_def": f"excess < {LOSER_PP}pp at H",
            "ruler": "W4 gate-matched matched-set delta; month-block bootstrap (atom = the "
                     "matched set) + ticker-cluster bootstrap; full-population effect sizes "
                     "are NOT cited (W4 adjudication).",
            "no_composite": "Each sensor is reported alone. The intersection is a cohort "
                            "filter with its own n, never a weight or a score.",
            "seed": SEED, "n_boot": N_BOOT,
        }
    }

    # ---------------- S-COIL ----------------
    coil = coil_events(close, high, low)
    ev_coil = bool_frame_to_events(coil["events"])
    res["S_COIL"] = {
        "construction": (
            f"compression = ATR{ATR_WIN} percentile vs own {PCT_WIN}d < p{int(PCT_MAX*100)} "
            f"AND close > {MA_WIN}dMA AND {MA_WIN}dMA rising over {MA_SLOPE}d; "
            f"event = first close above the prior {BREAK_WIN}d high after >= {COMP_MIN} "
            f"compressed sessions in the trailing {COMP_LOOKBACK}. Compression read at t-1 "
            "so the release bar cannot enter the ATR window that admits it."),
        "controls": "GATE-MATCHED: same-session names printing the same first-close-above-"
                    "prior-21d-high WITHOUT the compression run.",
        "kills_check": (
            "Release-bar-only by construction — the compressed/'armed' state is never "
            "surfaced or graded standalone (ESX section 9 / DT-R5 ban the arming variant). "
            "Volume carries no leg (ESX RUL-1, H4). UPTREND coil (above a RISING 50dMA), "
            "which is neither the bottom-radar PRIMED durable-bottom gate (DNR section 2) "
            "nor DURABLE_BOTTOM H2's post-washout calm base. Species S16 (S-SQ squeeze-"
            "release) OWNS this construction and is already accruing; this is a stand-in "
            "on a different frame, not a parallel authority."),
        "fire_counts": coil["diag"],
    }
    res["S_COIL"]["grades"] = grade_sensor(
        ev_coil, fwd, lambda e, f: attach_flat_controls(e, coil["controls"], f))

    # ---------------- S-RANKVEL ----------------
    rv = rankvel_events(close)
    ev_rv = bool_frame_to_events(rv["events"])
    res["S_RANKVEL"] = {
        "construction": (
            f"RS percentile = cross-sectional PIT rank of the {RS_WIN}d return; event = "
            f"percentile gains >= +{int(VEL_MIN*100)} points over {VEL_WIN} sessions AND "
            f"crosses above p{int(RS_LEVEL*100)}."),
        "controls": (
            f"LEVEL-MATCHED: same-session names within +/-{int(LEVEL_TOL*100)} percentile "
            f"points of the event's own level that did NOT accelerate (5d change < "
            f"+{int(FLAT_MAX*100)} points) — the axis under test is the DERIVATIVE."),
        "kills_check": (
            "R-4 (rs zero-sum tautology) is scoped to member-DISPERSION gates and "
            "donor/recipient rotation pairs, not to a per-name rank derivative graded "
            "against level-matched controls; nothing here gates. Nearest measured prior is "
            "W4's rs_turn_21_63 NULL (alpha/m [-0.175, +0.222]) — a different construction, "
            "and a null here would be a second strike on the rs-derivative family."),
        "fire_counts": rv["diag"],
    }
    res["S_RANKVEL"]["grades"] = grade_sensor(
        ev_rv, fwd, lambda e, f: attach_level_controls(e, rv["pct"], rv["slow"], f))

    # ---------------- S-THRUST-LAG ----------------
    baskets = json.load(open("data/baskets/membership.json"))["baskets"]
    tl = thrust_lag_events(close, high, low, baskets)
    ev_tl = tl["events"]
    res["S_THRUST_LAG"] = {
        "construction": (
            f"theme = curated basket (us_sector_ excluded, PIT added/removed honored, "
            f">= {MIN_MEMBERS} covered active members); thrust = member fraction above own "
            f"{HIGH20}d high crosses from < {THRUST_LO} to > {THRUST_HI} within "
            f"{THRUST_WIN} sessions; candidate = member BELOW its own {HIGH20}d high "
            "carrying S-COIL compression at thrust."),
        "controls": "(a) already-moved members of the SAME basket at thrust; "
                    "(b) compressed below-20d-high names in NON-thrusting themes, same day.",
        "kills_check": (
            "Composes the measured laggard-cross positive (RESULTS_2026-08-03: same cross "
            "on RS63<=0.40 laggards +0.33% pooled / +1.44% per-name vs leader-reset "
            "-1.50% / -2.12%) with theme context. Creates no rotation surface "
            "(DNR section 1 sector_rotation_schedule.v1 DO-NOT-BUILD) and no parallel "
            "authority beside the suspended Ignition Radar (DNR section 4) — charter "
            "section 4 reconciles the two ignition definitions."),
        "fire_counts": tl["diag"],
    }
    if not ev_tl.empty:
        moved_flags = events_to_bool_frame(tl["moved"], close)
        nt_flags = events_to_bool_frame(tl["nonthrust"], close)
        res["S_THRUST_LAG"]["grades_vs_already_moved"] = grade_sensor(
            ev_tl, fwd, lambda e, f: attach_flat_controls(e, moved_flags, f))
        res["S_THRUST_LAG"]["grades_vs_coiled_nonthrust"] = grade_sensor(
            ev_tl, fwd, lambda e, f: attach_flat_controls(e, nt_flags, f))
    else:
        res["S_THRUST_LAG"]["grades"] = {"thin": True, "n": 0}

    # ---------------- S-INSIDER — COVERAGE CENSUS ONLY (grading is a NAMED GAP) -------
    res["S_INSIDER"] = insider_census(close)

    # ---------------- section 5 foresight lead-time — MATURITY CENSUS ----------------
    res["FORESIGHT_LEADTIME_CENSUS"] = foresight_census(close)

    # ---------------- INTERSECTION (filter, not weight) ----------------
    inter = intersection_cohort(
        {"S_COIL": ev_coil, "S_RANKVEL": ev_rv,
         "S_THRUST_LAG": ev_tl if not ev_tl.empty else None}, close)
    res["INTERSECTION"] = {
        "definition": "name-days where >= 2 distinct sensors fired within +/- 5 sessions; "
                      "runs of the same (ticker, sensor-set) collapsed to the first session",
        "n": int(len(inter)),
        "by_set": (inter["sensors"].value_counts().to_dict() if len(inter) else {}),
        "law": "A filter, not a weight. No composite score is formed anywhere.",
    }
    if len(inter) >= 20:
        res["INTERSECTION"]["grades"] = {}
        for h in HORIZONS:
            blk = {}
            for kind in ("raw", "excess_spy", "excess_med"):
                frame = fwd[h][kind]
                di, ti = _positions(inter, frame)
                arr = frame.to_numpy(dtype=float)
                vals = np.where((di >= 0) & (ti >= 0), arr[di, ti], np.nan)
                ok = np.isfinite(vals)
                blk[kind] = _cell(pd.Series(vals[ok]),
                                  pd.Series(np.asarray(inter["ticker"])[ok]))
            res["INTERSECTION"]["grades"][f"H{h}"] = blk

    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
