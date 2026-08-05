"""ROC-extremes measurement battery — blow-off tops, washout grain, burst rhythm (US book).

TIER: RESEARCH / SHADOW — ZERO AUTHORITY. Every number here is a MEASUREMENT. Nothing in
this file touches admission, ranking, sizing, gating, or any user-facing surface, and
nothing in it may be cited as an authority read. It is the US measurement precursor to the CN
extension legs (``engine/china_signals.py`` ret5/ret20), which have never been ported.

WHY IT EXISTS (operator directive 2026-08-05)
  (a) blow-off-top detection — "a run terminates when ROC(12) goes to an extreme";
  (b) washout-bottom zones at SECTOR/ASSET grain (deliberately not name grain);
  (c) the burst-rest-burst rhythm of high-beta names — "5-day 35% bursts; from an
      absolute bottom an initial burst, then a couple of days of rest, then more".

KILL FENCES THIS BATTERY MUST NOT CROSS (research/DO_NOT_REBUILD.md)
  * PSS-F1 / PSS-F3 / PSS-F4 (rows 70/72/73) — STANDALONE NAME-LEVEL BOTTOM-TIMERS are
    killed. S-ROCW-GRAIN is therefore run at sector/asset grain ONLY; no name-grain
    washout timer is constructed anywhere in this file.
  * Washout x turn (2W operator seed, row 78) — KILLED as an entry seed. Nothing here
    is an entry construction; the washout sensor measures stabilization geometry only.
  * Bottom-radar PRIMED as a DIRECTIONAL durable-bottom gate (row 120) — KILLED. No
    tier, gate, or directional stance is emitted from any read below.
  * Cross-sectional commodity momentum L/S (row 116) — KILLED. The futures series here
    are measured one at a time against their own history; there is no cross-sectional
    rank, no long/short, and no portfolio.
  * Absolute-threshold anchors as PRIMARY constructions (row 109, absolute-VIX
    spike-and-fade, REJECT-STAT: non-stationary absolute anchors) — every primary gate
    below is a PER-NAME OWN-HISTORY PERCENTILE. Absolute ROC bands are reported as
    DESCRIPTIVE STRATA ONLY and are labelled as such in the output.
  * PM4 (row 89) — extension-flavoured metrics with |rho| >= 0.85 against
    ext_z / ext_atr / dist_to_52wh are fenced REDUNDANT. S-ROCX-TOP therefore computes
    its own redundancy read against ext_z (px/SMA200-1, z-scored over 252d, the
    ``engine/extension.py`` construction) and PRINTS the verdict
    REDUNDANT-WITH-EXT_Z when the fence is crossed. No spin, no re-parameterisation.

METHOD (mirrors research/prophet_us_audit/superintelligence_standins.py)
  Panel      data/baskets/ohlcv/*.parquet (OHLCV, per-name), truncated at REPRO_ASOF.
  Benchmark  data/yahoo/SPY.parquet.
  Horizons   H in {10, 21, 63} sessions.
  Frames     raw fwd return; excess vs SPY; excess vs same-day cross-sectional median;
             dd_within_h (max drawdown from the event close inside H, from LOWS at name
             grain); mfe_within_h (max runup inside H, from HIGHS at name grain).
  Ruler      GATE-MATCHED matched-set delta: delta = event value - median of the
             same-session controls, controls sharing every gate leg except the one
             under test. Month-block bootstrap (atom = calendar month) is the primary
             CI; a ticker-cluster bootstrap is reported beside it as the recurrence
             check. Per-name-first medians sit beside pooled medians. Half-split at the
             panel midpoint date is the robustness read. Cells under MIN_CELL print n
             only. Per-leg fire counts are always emitted, so a DEAD LEG PRINTS ZERO
             rather than vanishing.
  Loser      excess_spy < -3pp at H (threshold stated; medians reported beside it so no
             verdict hangs on the threshold).
  Stamping   BACKWARD-ONLY everywhere. An event at bar e is selected using bars <= e and
             never a bar after e (the W8 intersection-lookahead lesson). The stamping of
             S-BURST-RHYTHM is pinned by a mutate-the-future invariance test in
             tests/test_roc_extremes_battery.py, together with a positive control that
             proves the test can see a lookahead when one is present.

Run:  python3 research/prophet_us_audit/roc_extremes_battery.py
Out:  research/prophet_us_audit/roc_extremes_battery_results.json
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "roc_extremes_battery_results.json")

REPRO_ASOF = "2026-07-31"
HORIZONS = (10, 21, 63)
LOSER_PP = -3.0
MIN_CELL = 30            # cells thinner than this print n only
BOOT_N = 2000            # month-block bootstrap draws (primary)
CLUSTER_BOOT_N = 1000    # ticker-cluster bootstrap draws (recurrence check)
MAX_BOOT_ROWS = 80_000   # month-stratified cap on a bootstrapped arm (disclosed)
RHO_FENCE = 0.85         # PM4 redundancy fence
SEED = 20260805
MIN_BARS = 300           # a name needs >= 300 bars to enter the panel (252 + 63 windows)

BOOT_FRAMES = ("excess_spy", "dd")   # frames that carry bootstrap CIs
FRAMES_NAME = ("raw", "excess_spy", "excess_xs", "dd", "mfe")
FRAMES_GRAIN = ("raw", "excess_spy", "excess_xs", "dd")

GRAIN_ETFS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV",
              "XLY", "SMH", "GDX", "XME", "GLD")
GRAIN_FUTURES = ("GC=F", "SI=F", "PL=F", "PA=F", "HG=F", "CL=F")


# ─────────────────────────────────────────────────────────────────────────────
# primitives
# ─────────────────────────────────────────────────────────────────────────────
def pct_rank(obj, window: int, min_periods: int):
    """Percentile of the latest value inside its OWN trailing window (no lookahead).

    Same construction as engine/indicators.pct_rank_window, with min_periods stated
    rather than implied so the warm-up is auditable.
    """
    return obj.rolling(window, min_periods=min_periods).rank(pct=True)


def roll_q(obj, window: int, q: float, min_periods: int):
    """Trailing quantile of the own history (no lookahead)."""
    return obj.rolling(window, min_periods=min_periods).quantile(q)


def roc(px, n: int):
    """n-session rate of change."""
    return px / px.shift(n) - 1.0


def ext_z(C: pd.DataFrame) -> pd.DataFrame:
    """engine/extension.py:92-93 construction: px/SMA200-1, z-scored over 252d."""
    sma200 = C.rolling(200, min_periods=100).mean()
    ext = C / sma200 - 1.0
    mu = ext.rolling(252, min_periods=120).mean()
    sd = ext.rolling(252, min_periods=120).std().replace(0, np.nan)
    return (ext - mu) / sd


def fwd_ret(C: pd.DataFrame, h: int) -> pd.DataFrame:
    return C.shift(-h) / C - 1.0


def fwd_min(X: pd.DataFrame, h: int) -> pd.DataFrame:
    """min over bars [t+1 .. t+h]."""
    return X.rolling(h, min_periods=h).min().shift(-h)


def fwd_max(X: pd.DataFrame, h: int) -> pd.DataFrame:
    """max over bars [t+1 .. t+h]."""
    return X.rolling(h, min_periods=h).max().shift(-h)


def leg_counts(masks: dict) -> dict:
    """Fire count per leg, EVERY key always present.

    A leg that never fires reports 0 — it is never dropped from the output, so a dead
    leg is visible in the results JSON instead of silently disappearing.
    """
    out = {}
    for k, v in masks.items():
        arr = v.to_numpy() if hasattr(v, "to_numpy") else np.asarray(v)
        out[k] = int(np.count_nonzero(arr))
    return out


def _idx(mask: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(row, col) positions of a boolean panel mask. NaN comparisons are already False."""
    ri, ci = np.where(mask.to_numpy())
    return ri.astype(np.int64), ci.astype(np.int64)


def disjoin(ev, ct, n_cols: int):
    """Drop control cells that are ALSO event cells; return the survivors + a keep mask.

    A bar cannot be its own control. Two arms can legitimately name the same
    (session, series) cell — at grain a deep step-1 and a mild step-1 can resolve to one
    stabilization bar, and a burst that rests all five sessions fires on the same bar the
    no-rest arm stamps. Left alone those cells enter the matched-set delta as an exact
    zero and drag the median toward 0 (the smoke run's grain delta was EXACTLY +0.000 for
    this reason). The removal count is reported, never silent.
    """
    eri, eci = ev
    cri, cci = ct
    if eri.size == 0 or cri.size == 0:
        return ct, np.ones(cri.size, dtype=bool), 0
    ekey = eri.astype(np.int64) * n_cols + eci
    ckey = cri.astype(np.int64) * n_cols + cci
    keep = ~np.isin(ckey, ekey)
    return (cri[keep], cci[keep]), keep, int((~keep).sum())


def thin_note(label: str, n: int, because: str) -> str | None:
    """A printed explanation for any arm under MIN_CELL — never a silent skip."""
    if n >= MIN_CELL:
        return None
    return (f"{label}: n={n} < MIN_CELL={MIN_CELL} — no delta/CI is reported for it. "
            f"Why: {because}")


# ─────────────────────────────────────────────────────────────────────────────
# ruler: matched-set delta + block bootstraps
# ─────────────────────────────────────────────────────────────────────────────
def _blocks(vals: np.ndarray, keys: np.ndarray) -> list[np.ndarray]:
    order = np.argsort(keys, kind="stable")
    v, k = vals[order], keys[order]
    cuts = np.flatnonzero(np.diff(k)) + 1
    return [a for a in np.split(v, cuts) if a.size]


def _cap(vals: np.ndarray, keys: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray, dict]:
    """Month-stratified deterministic cap so a very large arm cannot blow the runtime."""
    n = vals.size
    if n <= MAX_BOOT_ROWS:
        return vals, keys, {"used": int(n), "of": int(n), "capped": False}
    keep = rng.permutation(n)[:MAX_BOOT_ROWS]
    keep.sort()
    return vals[keep], keys[keep], {"used": int(MAX_BOOT_ROWS), "of": int(n), "capped": True}


def block_boot_ci(vals: np.ndarray, keys: np.ndarray, n_boot: int, seed: int,
                  stat=np.median) -> dict | None:
    """95% CI of `stat` under a block bootstrap whose resample atom is `keys`."""
    vals = np.asarray(vals, dtype=float)
    ok = np.isfinite(vals)
    vals, keys = vals[ok], np.asarray(keys)[ok]
    if vals.size < MIN_CELL:
        return None
    rng = np.random.default_rng(seed)
    vals, keys, cap = _cap(vals, keys, rng)
    arrs = _blocks(vals, keys)
    k = len(arrs)
    if k < 3:
        return {"ci95": None, "blocks": int(k), "note": "fewer than 3 blocks", **cap}
    draws = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        pick = rng.integers(0, k, k)
        draws[b] = stat(np.concatenate([arrs[i] for i in pick]))
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"ci95": [round(float(lo), 3), round(float(hi), 3)],
            "blocks": int(k), "draws": int(n_boot), **cap}


def block_boot_diff_ci(a_vals, a_keys, b_vals, b_keys, n_boot: int, seed: int,
                       stat=np.mean) -> dict | None:
    """95% CI of stat(A) - stat(B) under a shared-block bootstrap (atom = key).

    Used for the two RATE differences (P(second burst), top-proximity) where a matched
    median delta is meaningless because the outcome is binary.
    """
    a_vals, b_vals = np.asarray(a_vals, float), np.asarray(b_vals, float)
    a_keys, b_keys = np.asarray(a_keys), np.asarray(b_keys)
    oa, ob = np.isfinite(a_vals), np.isfinite(b_vals)
    a_vals, a_keys, b_vals, b_keys = a_vals[oa], a_keys[oa], b_vals[ob], b_keys[ob]
    if a_vals.size < MIN_CELL or b_vals.size < MIN_CELL:
        return None
    rng = np.random.default_rng(seed)
    keys = sorted(set(a_keys.tolist()) | set(b_keys.tolist()))
    amap = {k: a_vals[a_keys == k] for k in keys}
    bmap = {k: b_vals[b_keys == k] for k in keys}
    keys = [k for k in keys if amap[k].size or bmap[k].size]
    k = len(keys)
    if k < 3:
        return {"ci95": None, "blocks": int(k), "note": "fewer than 3 blocks"}
    draws = np.empty(n_boot, dtype=float)
    good = 0
    for b in range(n_boot):
        pick = [keys[i] for i in rng.integers(0, k, k)]
        aa = np.concatenate([amap[p] for p in pick]) if pick else np.array([])
        bb = np.concatenate([bmap[p] for p in pick]) if pick else np.array([])
        if aa.size == 0 or bb.size == 0:
            draws[b] = np.nan
            continue
        draws[b] = stat(aa) - stat(bb)
        good += 1
    d = draws[np.isfinite(draws)]
    if d.size < n_boot // 2:
        return {"ci95": None, "blocks": int(k), "note": "degenerate resamples"}
    lo, hi = np.percentile(d, [2.5, 97.5])
    return {"ci95": [round(float(lo), 3), round(float(hi), 3)],
            "blocks": int(k), "draws": int(good)}


def matched_delta(ev_vals, ev_ri, ct_vals, ct_ri, n_rows: int):
    """delta = event value - median of the SAME-SESSION gate-matched controls."""
    med = np.full(n_rows, np.nan)
    if ct_vals.size:
        s = pd.Series(ct_vals).groupby(ct_ri).median()
        med[np.asarray(s.index, dtype=np.int64)] = s.to_numpy()
    d = ev_vals - med[ev_ri]
    ok = np.isfinite(d)
    return d, ok


def _rate(x: np.ndarray, thr: float) -> float | None:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return None
    return round(float(np.mean(x < thr) * 100.0), 2)


def frame_table(ev_vals, ev_ri, ev_ci, ct_vals, ct_ri, n_rows: int, mid_row: int,
                months: np.ndarray, frame: str, seed: int) -> dict:
    """One frame x one horizon: pooled/per-name/half-split medians + CIs, in pp."""
    ev_ok = np.isfinite(ev_vals)
    ct_ok = np.isfinite(ct_vals)
    out = {"n_events_with_outcome": int(ev_ok.sum()),
           "n_controls_with_outcome": int(ct_ok.sum())}
    if int(ev_ok.sum()) < MIN_CELL:
        out["thin"] = True
        return out
    out["event_median_pp"] = round(float(np.nanmedian(ev_vals) * 100), 3)
    out["control_median_pp"] = (round(float(np.nanmedian(ct_vals) * 100), 3)
                                if int(ct_ok.sum()) else None)
    d, ok = matched_delta(ev_vals, ev_ri, ct_vals, ct_ri, n_rows)
    dv, dri, dci = d[ok], ev_ri[ok], ev_ci[ok]
    out["n_matched"] = int(dv.size)
    out["n_dates_matched"] = int(np.unique(dri).size)
    # how much of the arm survives the same-session matching requirement — a low number
    # here means the delta is computed on a session-clustered subset of the fires
    out["matched_coverage_pct"] = round(float(dv.size / max(int(ev_ok.sum()), 1) * 100), 1)
    if dv.size < MIN_CELL:
        out["thin_matched"] = True
        return out
    out["delta_median_pp"] = round(float(np.median(dv) * 100), 3)
    per_name = pd.Series(dv).groupby(dci).median()
    out["per_name_first_delta_pp"] = round(float(per_name.median() * 100), 3)
    out["n_names"] = int(per_name.size)
    for lbl, m in (("half1", dri < mid_row), ("half2", dri >= mid_row)):
        n = int(m.sum())
        out[lbl] = ({"n": n} if n < MIN_CELL else
                    {"n": n, "delta_median_pp": round(float(np.median(dv[m]) * 100), 3)})
    if frame in BOOT_FRAMES:
        mb = block_boot_ci(dv * 100, months[ok], BOOT_N, seed)
        if mb:
            out["delta_ci95_month_block_pp"] = mb.get("ci95")
            out["month_blocks"] = mb.get("blocks")
            if mb.get("capped"):
                out["boot_subsample"] = {"used": mb["used"], "of": mb["of"]}
        cb = block_boot_ci(dv * 100, dci, CLUSTER_BOOT_N, seed + 1)
        if cb:
            out["delta_ci95_ticker_cluster_pp"] = cb.get("ci95")
            out["ticker_clusters"] = cb.get("blocks")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# detectors — pure functions, no store access (the unit tests drive these directly)
# ─────────────────────────────────────────────────────────────────────────────
def rocx_top_legs(C: pd.DataFrame, *, hi_q: float = 0.95, severe_q: float = 0.98,
                  ctrl: tuple[float, float] = (0.50, 0.80)) -> dict:
    """S-ROCX-TOP legs. Every leg is returned, so a dead leg counts 0 rather than vanish.

    Fire: roc12 own-history percentile (252d, min 126) >= hi_q AND close > SMA50 AND
    SMA50 rising over 10 sessions. Controls share the uptrend legs with the percentile
    in [0.50, 0.80).
    """
    r12 = roc(C, 12)
    p12 = pct_rank(r12, 252, 126)
    sma50 = C.rolling(50, min_periods=50).mean()
    above = C > sma50
    rising = sma50 > sma50.shift(10)
    up = above & rising
    return {
        "roc12": r12, "roc12_pctile": p12, "sma50": sma50,
        "legs": {
            "close_above_sma50": above,
            "sma50_rising_10": rising,
            "uptrend_both_legs": up,
            f"roc12_pctile_ge_{hi_q}": p12 >= hi_q,
            f"roc12_pctile_ge_{severe_q}": p12 >= severe_q,
            "roc12_pctile_ctrl_band_50_80": (p12 >= ctrl[0]) & (p12 < ctrl[1]),
        },
        "fire": up & (p12 >= hi_q),
        "fire_severe": up & (p12 >= severe_q),
        "control": up & (p12 >= ctrl[0]) & (p12 < ctrl[1]),
    }


def roc12_term_legs(C: pd.DataFrame, *, mover_min: float = 0.15,
                    near_high: float = 0.05, fire_q: float = 0.99,
                    ctrl: tuple[float, float] = (0.80, 0.90)) -> dict:
    """S-ROC12-TERM legs: burst-movers, within `near_high` of their own 63d high."""
    r5 = roc(C, 5)
    p97_5 = roll_q(r5, 252, 0.97, 126)
    mover = p97_5 >= mover_min
    hi63 = C.rolling(63, min_periods=63).max()
    near = C >= (1.0 - near_high) * hi63
    r12 = roc(C, 12)
    q99 = roll_q(r12, 252, fire_q, 126)
    p12 = pct_rank(r12, 252, 126)
    base = mover & near
    return {
        "roc12": r12, "roc12_pctile": p12,
        "legs": {
            "burst_mover_p97_roc5_ge_15pct": mover,
            "within_5pct_of_63d_high": near,
            "mover_and_near_high": base,
            "roc12_ge_own_p99": r12 >= q99,
            "roc12_pctile_ctrl_band_80_90": (p12 >= ctrl[0]) & (p12 < ctrl[1]),
        },
        "fire": base & (r12 >= q99),
        "control": base & (p12 >= ctrl[0]) & (p12 < ctrl[1]),
    }


def washout_events(close, *, trough_q: float = 0.05, win: int = 504, min_p: int = 252,
                   stab_look: int = 5, stab_within: int = 21,
                   ctrl_band: tuple[float, float] = (0.10, 0.30)) -> dict:
    """S-ROCW-GRAIN two-step detector on ONE series. Returns integer bar positions.

    step 1  roc21 <= own-history p05 (rolling `win`, min_periods `min_p`)  [fire arm]
            roc21 own-history percentile in [0.10, 0.30)                   [control arm]
    step 2  the FIRST session within the next `stab_within` bars whose close exceeds the
            max close of the prior `stab_look` sessions. THAT bar is the event.

    Backward-only: step 1 sits at s < t and step 2 reads closes t-5..t, so an event at
    bar t uses no bar after t. Episodes are non-overlapping — after an event at t the
    scan resumes at t+1 — so one decline contributes one episode, not a cluster.
    """
    c = pd.Series(close).astype(float)
    n = len(c)
    r21 = roc(c, 21)
    thr = roll_q(r21, win, trough_q, min_p)
    pct = pct_rank(r21, win, min_p)
    prior_max = c.shift(1).rolling(stab_look, min_periods=stab_look).max()
    stab = (c > prior_max).to_numpy()
    deep = (r21 <= thr).to_numpy() & np.isfinite(thr.to_numpy())
    mild = ((pct >= ctrl_band[0]) & (pct < ctrl_band[1])).to_numpy()
    cv = c.to_numpy()

    def walk(step1: np.ndarray) -> list[tuple[int, int, float]]:
        out: list[tuple[int, int, float]] = []
        i = 0
        while i < n:
            if not bool(step1[i]):
                i += 1
                continue
            t = -1
            for j in range(i + 1, min(i + 1 + stab_within, n)):
                if bool(stab[j]):
                    t = j
                    break
            if t < 0:
                i += 1
                continue
            out.append((i, t, float(np.nanmin(cv[i:t + 1]))))
            i = t + 1
        return out

    return {"fire": walk(deep), "control": walk(mild),
            "n_step1_deep": int(np.count_nonzero(deep)),
            "n_step1_mild": int(np.count_nonzero(mild)),
            "n_stabilization_bars": int(np.count_nonzero(stab))}


def burst_events(close, low, *, q_hi: float = 0.97, win: int = 252, min_p: int = 126,
                 mover_min: float = 0.15, low_win: int = 63, low_recent: int = 10,
                 rest_min: int = 2, rest_max: int = 5, band_dn: float = 0.50,
                 band_up: float = 0.25, break_frac: float = 0.618) -> dict:
    """S-BURST-RHYTHM detector on ONE series. Returns integer bar positions.

    B1 (burst off a bottom), all three legs evaluated AT the bar (membership drifts):
      roc5 >= own trailing p97 AND that p97 >= `mover_min` (burst-mover) AND the
      trailing `low_win`-session low sits within the prior `low_recent` sessions.

    From a B1 at bar i with 5-day gain g, walk k = 1..5 over cum_k = close[i+k]/close[i]-1:
      * cum_k < -break_frac*g            -> CONTROL ARM (a) "broken rest", event = i+k.
      * -band_dn*g <= cum_k <= band_up*g -> still resting; m = k.
      * otherwise (left the band upward) -> the rest ended at i+k. m >= rest_min gives
        the FIRE at bar i+k ("the first session AFTER a completed 2-5 session rest that
        held"); m < rest_min is the early-runaway cohort, counted, not a fire.
      * all 5 in band -> FIRE at i+6.
    Every arm's event bar e is decided from bars <= e: the walk stops at the resolving
    bar and never reads past it. CONTROL ARM (b) "no rest" (roc5 makes a new high in
    each of sessions 1..5) is stamped at i+6, i.e. also from bars <= e; a close-based
    variant of the same cohort is returned beside it. Arms (a)/(b) can in principle both
    describe one B1 — the overlap is counted and printed, never assumed away.
    """
    c = pd.Series(close).astype(float)
    l = pd.Series(low).astype(float)
    n = len(c)
    r5 = roc(c, 5)
    p97 = roll_q(r5, win, q_hi, min_p)
    mover = (p97 >= mover_min).to_numpy() & np.isfinite(p97.to_numpy())
    min_long = l.rolling(low_win, min_periods=low_win).min()
    min_short = l.rolling(low_recent + 1, min_periods=low_recent + 1).min()
    recent = (min_short <= min_long * (1.0 + 1e-12)).to_numpy() & np.isfinite(min_long.to_numpy())
    b1 = (r5 >= p97).to_numpy() & mover & recent
    cv, gv, rv = c.to_numpy(), r5.to_numpy(), r5.to_numpy()

    fires: list[dict] = []
    breaks: list[dict] = []
    norest: list[dict] = []
    norest_close: list[dict] = []
    early = 0
    unresolved = 0
    overlap = 0
    i = 0
    while i < n:
        if not bool(b1[i]):
            i += 1
            continue
        g = float(gv[i])
        if not np.isfinite(g) or g <= 0:
            i += 1
            continue
        lo_b, hi_b, brk_b = -band_dn * g, band_up * g, -break_frac * g
        m, arm, e = 0, None, -1
        for k in range(1, rest_max + 1):
            j = i + k
            if j >= n:
                break
            cum = cv[j] / cv[i] - 1.0
            if cum < brk_b:
                arm, e = "break", j
                break
            if lo_b <= cum <= hi_b:
                m = k
                continue
            arm, e = ("fire" if m >= rest_min else "early"), j
            break
        if arm is None and m == rest_max and i + rest_max + 1 < n:
            arm, e = "fire", i + rest_max + 1
        row = {"b1": i, "event": e, "k": (e - i) if e > 0 else None, "gain": g}
        if arm == "fire":
            fires.append(row)
        elif arm == "break":
            breaks.append(row)
        elif arm == "early":
            early += 1
        else:
            unresolved += 1
        # control arm (b): roc5 makes a new high in each of sessions 1..5 -> event i+6
        j5 = i + rest_max
        if j5 + 1 < n:
            strict = True
            best = rv[i]
            for k in range(1, rest_max + 1):
                v = rv[i + k]
                if not (np.isfinite(v) and v > best):
                    strict = False
                    break
                best = v
            if strict:
                norest.append({"b1": i, "event": j5 + 1, "k": rest_max + 1, "gain": g})
                if arm == "fire":
                    overlap += 1
            cbest = cv[i]
            cstrict = True
            for k in range(1, rest_max + 1):
                if not (cv[i + k] > cbest):
                    cstrict = False
                    break
                cbest = cv[i + k]
            if cstrict:
                norest_close.append({"b1": i, "event": j5 + 1, "k": rest_max + 1, "gain": g})
        i = (max(e, j5 + 1) + 1) if e > 0 else (i + 1)
    return {"fire": fires, "control_break": breaks, "control_no_rest": norest,
            "control_no_rest_close_variant": norest_close,
            "n_b1_bars": int(np.count_nonzero(b1)),
            "n_mover_bars": int(np.count_nonzero(mover)),
            "n_recent_low_bars": int(np.count_nonzero(recent)),
            "n_early_runaway": int(early), "n_unresolved": int(unresolved),
            "n_no_rest_overlapping_a_fire": int(overlap)}


# ─────────────────────────────────────────────────────────────────────────────
# panel loading
# ─────────────────────────────────────────────────────────────────────────────
def build_panel() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    files = sorted(glob.glob("data/baskets/ohlcv/*.parquet"))
    cl, hi, lo, names, short = [], [], [], [], []
    for f in files:
        t = os.path.basename(f)[:-len(".parquet")]
        try:
            d = pd.read_parquet(f, columns=["high", "low", "close"])
        except Exception:      # a corrupt/odd parquet must not kill the whole panel
            short.append(t)
            continue
        d = d[d.index <= pd.Timestamp(REPRO_ASOF)]
        if len(d) < MIN_BARS:
            short.append(t)
            continue
        names.append(t)
        cl.append(d["close"])
        hi.append(d["high"])
        lo.append(d["low"])
    C = pd.concat(cl, axis=1, keys=names).sort_index().astype(float)
    Hi = pd.concat(hi, axis=1, keys=names).sort_index().astype(float)
    Lo = pd.concat(lo, axis=1, keys=names).sort_index().astype(float)
    meta = {"files": len(files), "names": len(names),
            "skipped_under_min_bars": len(short), "min_bars": MIN_BARS,
            "sessions": int(C.shape[0]),
            "dates": [str(C.index.min().date()), str(C.index.max().date())],
            "repro_asof": REPRO_ASOF,
            "names_with_a_bar_on_asof": int(C.notna().iloc[-1].sum())}
    return C, Hi, Lo, meta


def load_spy(index: pd.DatetimeIndex) -> pd.Series:
    s = pd.read_parquet("data/yahoo/SPY.parquet")["close"].astype(float)
    s = s[s.index <= pd.Timestamp(REPRO_ASOF)]
    return s.reindex(index).ffill(limit=1)


def build_grain_panel(C: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """47 curated basket EW indexes + sector/thematic ETFs + commodity futures.

    Basket indexes are equal-weight cumulative products of the same-day mean member
    return. Membership is read from TODAY's membership.json (added/removed dates exist
    but are not replayed) — a stated PIT/survivorship caveat, the same one the sibling
    battery carries for S-C, not a silent assumption.
    """
    with open("data/baskets/membership.json") as fh:
        memb = json.load(fh).get("baskets", {})
    cols: dict[str, pd.Series] = {}
    cover: list[dict] = []
    R = C.pct_change(fill_method=None)
    enough = C.notna().sum() >= 100
    for bid, b in memb.items():
        want = [m["ticker"] for m in b.get("members", []) if not m.get("removed")]
        have = [t for t in want if t in C.columns]
        usable = [t for t in have if bool(enough.get(t, False))]
        cover.append({"basket": bid, "members": len(want), "in_panel": len(have),
                      "usable_ge_100_bars": len(usable)})
        if len(usable) < 3:
            continue
        m = R[usable].mean(axis=1, skipna=True)
        first = m.first_valid_index()
        if first is None:
            continue
        m = m.loc[first:].fillna(0.0)
        cols[f"basket:{bid}"] = (1.0 + m).cumprod().reindex(C.index)
    absent, filled, last_bar = [], 0, {}
    for sym in GRAIN_ETFS + GRAIN_FUTURES:
        cands = [sym.replace("=", "_"), sym.replace("=F", "_F"), sym]
        path = next((p for p in (f"data/yahoo/{x}.parquet" for x in dict.fromkeys(cands))
                     if os.path.exists(p)), None)
        if path is None:
            absent.append(sym)
            print(f"WARN grain series ABSENT from data/yahoo (skipped, not silently): {sym}")
            continue
        s = pd.read_parquet(path)["close"].astype(float)
        s = s[s.index <= pd.Timestamp(REPRO_ASOF)]
        last_bar[sym] = str(s.index.max().date()) if len(s) else None
        r = s.reindex(C.index)
        pre = r.notna()
        r = r.ffill(limit=1)
        filled += int((r.notna() & ~pre).sum())
        kind = "futures" if sym in GRAIN_FUTURES else "etf"
        cols[f"{kind}:{sym}"] = r
    G = pd.DataFrame(cols).sort_index()
    meta = {
        "series": int(G.shape[1]),
        "baskets_built": int(sum(1 for k in G.columns if k.startswith("basket:"))),
        "baskets_in_file": len(memb),
        "etf_series": int(sum(1 for k in G.columns if k.startswith("etf:"))),
        "futures_series": int(sum(1 for k in G.columns if k.startswith("futures:"))),
        "absent_symbols": absent,
        "per_basket_member_coverage": cover,
        "yahoo_last_bar": last_bar,
        "alignment": ("NYSE session index from the equity panel; non-equity series "
                      f"forward-filled at most 1 session to bridge calendar gaps "
                      f"({filled} bars bridged)"),
        "pit_caveat": ("basket membership is TODAY's membership.json (removed members "
                       "excluded for the whole history) — composition look-ahead is "
                       "stated, not corrected"),
        "dd_basis": "close (grain series carry no intraday high/low)",
    }
    return G, meta


# ─────────────────────────────────────────────────────────────────────────────
# sensor drivers
# ─────────────────────────────────────────────────────────────────────────────
def _frames_name(C, Hi, Lo, spy, h) -> dict:
    f = fwd_ret(C, h)
    sp = spy.shift(-h) / spy - 1.0
    return {
        "raw": f.to_numpy(dtype="float32"),
        "excess_spy": f.sub(sp, axis=0).to_numpy(dtype="float32"),
        "excess_xs": f.sub(f.median(axis=1), axis=0).to_numpy(dtype="float32"),
        "dd": (fwd_min(Lo, h) / C - 1.0).to_numpy(dtype="float32"),
        "mfe": (fwd_max(Hi, h) / C - 1.0).to_numpy(dtype="float32"),
    }


def _frames_grain(G, spy, h) -> dict:
    f = fwd_ret(G, h)
    sp = spy.shift(-h) / spy - 1.0
    return {
        "raw": f.to_numpy(dtype="float32"),
        "excess_spy": f.sub(sp, axis=0).to_numpy(dtype="float32"),
        "excess_xs": f.sub(f.median(axis=1), axis=0).to_numpy(dtype="float32"),
        "dd": (fwd_min(G, h) / G - 1.0).to_numpy(dtype="float32"),
    }


def _pair_tables(pairs: list[dict], frames_fn, index: pd.DatetimeIndex,
                 frame_keys: tuple[str, ...]) -> dict:
    """One pass per horizon over the shared panel; every (event, control) pair filled."""
    n_rows = len(index)
    mid_row = n_rows // 2
    months = (index.year * 100 + index.month).to_numpy()
    out = {p["key"]: {} for p in pairs}
    for h in HORIZONS:
        F = frames_fn(h)
        for p in pairs:
            eri, eci = p["ev"]
            cri, cci = p["ct"]
            tbl = {"n_events": int(eri.size), "n_controls": int(cri.size)}
            if eri.size:
                exc = F["excess_spy"][eri, eci]
                tbl["event_loser_rate_pct"] = _rate(exc, LOSER_PP / 100.0)
            if cri.size:
                tbl["control_loser_rate_pct"] = _rate(F["excess_spy"][cri, cci],
                                                      LOSER_PP / 100.0)
            tbl["frames"] = {}
            for fk in frame_keys:
                tbl["frames"][fk] = frame_table(
                    F[fk][eri, eci], eri, eci, F[fk][cri, cci], cri,
                    n_rows, mid_row, months[eri], fk, SEED + h)
            out[p["key"]][str(h)] = tbl
        del F
    return out


def redundancy_vs_ext_z(C: pd.DataFrame, p12: pd.DataFrame, fire: pd.DataFrame) -> dict:
    """PM4 fence read: ROC(12) own-history percentile vs the ext_z construction."""
    Z = ext_z(C)
    a, b = p12.to_numpy(), Z.to_numpy()
    ok = np.isfinite(a) & np.isfinite(b)
    av, bv = a[ok], b[ok]
    pooled = float(np.corrcoef(av, bv)[0, 1]) if av.size > 2 else float("nan")
    n = av.size
    sub = av
    if n > 3_000_000:
        rng = np.random.default_rng(SEED)
        keep = rng.permutation(n)[:3_000_000]
        sub, bsub = av[keep], bv[keep]
    else:
        bsub = bv
    spear = float(np.corrcoef(pd.Series(sub).rank().to_numpy(),
                              pd.Series(bsub).rank().to_numpy())[0, 1]) if sub.size > 2 else float("nan")
    xs = []
    for i in range(a.shape[0]):
        m = np.isfinite(a[i]) & np.isfinite(b[i])
        if int(m.sum()) < 30:
            continue
        x, y = a[i][m], b[i][m]
        if x.std() == 0 or y.std() == 0:
            continue
        xs.append(float(np.corrcoef(x, y)[0, 1]))
    xs_mean = float(np.mean(xs)) if xs else float("nan")
    fm = fire.to_numpy() & ok
    fa, fb = a[fm], b[fm]
    on_fire = float(np.corrcoef(fa, fb)[0, 1]) if fa.size > 2 else float("nan")
    reads = {"pooled_pearson": round(pooled, 4), "pooled_spearman": round(spear, 4),
             "mean_cross_sectional_pearson": round(xs_mean, 4),
             "on_fire_cells_pearson": round(on_fire, 4)}
    mx = max(abs(v) for v in reads.values() if np.isfinite(v))
    return {**reads, "n_cells": int(n), "n_dates_in_xs_mean": len(xs),
            "decision_statistic": "mean_cross_sectional_pearson (fence applied to the "
                                  "LARGEST |rho| of the four reads — fail-closed)",
            "max_abs_rho": round(mx, 4), "fence": RHO_FENCE,
            "redundant": bool(mx >= RHO_FENCE)}


def run_name_grain(C, Hi, Lo, spy) -> dict:
    """S-ROCX-TOP, S-BURST-RHYTHM and S-ROC12-TERM share one panel pass."""
    index, cols = C.index, list(C.columns)
    top = rocx_top_legs(C)
    term = roc12_term_legs(C)

    # --- per-series walkers (S-BURST) ---
    b_fire_r, b_fire_c, b_brk_r, b_brk_c = [], [], [], []
    b_nr_r, b_nr_c, b_nrc_r, b_nrc_c = [], [], [], []
    legs_sum = {"n_b1_bars": 0, "n_mover_bars": 0, "n_recent_low_bars": 0,
                "n_early_runaway": 0, "n_unresolved": 0, "n_no_rest_overlapping_a_fire": 0}
    for j, t in enumerate(cols):
        c = C[t].dropna()
        if len(c) < MIN_BARS:
            continue
        l = Lo[t].reindex(c.index)
        ev = burst_events(c, l)
        pos = index.get_indexer(c.index)
        for k in legs_sum:
            legs_sum[k] += int(ev[k])
        for key, rr, cc in (("fire", b_fire_r, b_fire_c),
                            ("control_break", b_brk_r, b_brk_c),
                            ("control_no_rest", b_nr_r, b_nr_c),
                            ("control_no_rest_close_variant", b_nrc_r, b_nrc_c)):
            for row in ev[key]:
                rr.append(int(pos[row["event"]]))
                cc.append(j)

    def _arr(r, c):
        return (np.asarray(r, dtype=np.int64), np.asarray(c, dtype=np.int64))

    burst_arms = {"fire": _arr(b_fire_r, b_fire_c),
                  "control_break": _arr(b_brk_r, b_brk_c),
                  "control_no_rest": _arr(b_nr_r, b_nr_c),
                  "control_no_rest_close_variant": _arr(b_nrc_r, b_nrc_c)}

    pairs = [
        {"key": "top_p95", "ev": _idx(top["fire"]), "ct": _idx(top["control"])},
        {"key": "top_p98", "ev": _idx(top["fire_severe"]), "ct": _idx(top["control"])},
        {"key": "burst_vs_break", "ev": burst_arms["fire"], "ct": burst_arms["control_break"]},
        {"key": "burst_vs_norest", "ev": burst_arms["fire"], "ct": burst_arms["control_no_rest"]},
        {"key": "burst_vs_norest_close", "ev": burst_arms["fire"],
         "ct": burst_arms["control_no_rest_close_variant"]},
        {"key": "term", "ev": _idx(term["fire"]), "ct": _idx(term["control"])},
    ]
    n_cols = len(cols)
    overlap_removed = {}
    for p in pairs:
        p["ct"], _keep, removed = disjoin(p["ev"], p["ct"], n_cols)
        overlap_removed[p["key"]] = removed
        if p["key"].startswith("burst_vs"):
            arm = {"burst_vs_break": "control_break",
                   "burst_vs_norest": "control_no_rest",
                   "burst_vs_norest_close": "control_no_rest_close_variant"}[p["key"]]
            burst_arms[arm] = p["ct"]
    tables = _pair_tables(pairs, lambda h: _frames_name(C, Hi, Lo, spy, h),
                          index, FRAMES_NAME)

    months = (index.year * 100 + index.month).to_numpy()

    # ---- S-ROCX-TOP ----
    fri, fci = pairs[0]["ev"]
    r12v = top["roc12"].to_numpy()
    strata = []
    for lbl, lo_ in (("roc12_ge_40pct", 0.40), ("roc12_ge_60pct", 0.60), ("roc12_ge_80pct", 0.80)):
        m = r12v[fri, fci] >= lo_
        strata.append({"band": lbl, "n": int(m.sum())})
    dd21 = (fwd_min(Lo, 21) / C - 1.0).to_numpy(dtype="float32")
    for row, (_, lo_) in zip(strata, (("a", 0.40), ("b", 0.60), ("c", 0.80))):
        m = r12v[fri, fci] >= lo_
        if int(m.sum()) >= MIN_CELL:
            row["median_dd_within_21_pp"] = round(float(np.nanmedian(dd21[fri[m], fci[m]]) * 100), 2)
    red = redundancy_vs_ext_z(C, top["roc12_pctile"], top["fire"])

    S_TOP = {
        "construction": ("roc12 = close/close.shift(12)-1; own-history percentile "
                         "(rolling 252d, min_periods 126) >= 0.95 (severe 0.98) AND "
                         "close > SMA50 AND SMA50 rising over 10 sessions. Controls: "
                         "same uptrend legs, percentile in [0.50, 0.80)."),
        "tier": "research/shadow — measurement only, zero authority",
        "fire_counts": {"legs": leg_counts(top["legs"]),
                        "events_p95": int(pairs[0]["ev"][0].size),
                        "events_p98": int(pairs[1]["ev"][0].size),
                        "controls_p95": int(pairs[0]["ct"][0].size),
                        "controls_p98": int(pairs[1]["ct"][0].size),
                        "control_cells_dropped_as_also_events": {
                            "p95": overlap_removed["top_p95"],
                            "p98": overlap_removed["top_p98"]}},
        "thin_notes": [n for n in (
            thin_note("S-ROCX-TOP fires p95", int(pairs[0]["ev"][0].size),
                      "the uptrend legs and the >=p95 percentile leg print above; a zero "
                      "here would mean one of those legs never co-occurred"),
            thin_note("S-ROCX-TOP fires p98", int(pairs[1]["ev"][0].size),
                      "same legs at the severe percentile")) if n],
        "redundancy_vs_ext_z": red,
        "absolute_strata_DESCRIPTIVE_ONLY": {
            "note": ("absolute ROC bands are DESCRIPTIVE. The VIX absolute-threshold kill "
                     "(DO_NOT_REBUILD row 109) fences non-stationary absolute anchors out "
                     "of primary constructions; the per-name percentile above is primary."),
            "bands": strata},
        "primary_read": "dd_within_h delta at H=21 (deeper drawdown after the extreme?)",
        "hypothesis_sign": "NEGATIVE delta on dd and on excess would support blow-off termination",
        "variants": {"p95": tables["top_p95"], "p98": tables["top_p98"]},
    }

    # ---- S-BURST-RHYTHM ----
    r5 = roc(C, 5)
    p95_5 = roll_q(r5, 252, 0.95, 126)
    sec = (r5 >= p95_5).astype(float)
    # max over [e+1, e+15]; the final 15 sessions carry NO forward window and must stay
    # NaN — scoring them as "no second burst" would be a truncation bias, not a null.
    sec_fwd = sec.rolling(15, min_periods=1).max().shift(-15).to_numpy()
    sec15 = np.where(np.isfinite(sec_fwd), (sec_fwd > 0).astype(float), np.nan)
    second = {}
    for arm, (rr, cc) in burst_arms.items():
        second[arm] = sec15[rr, cc].astype(float) if rr.size else np.array([])
    # events inside the final 15 sessions carry NO forward window: they are NaN above and
    # are dropped here rather than counted as "no second burst" (truncation, not a null).
    sec_ok = {a: np.isfinite(v) for a, v in second.items()}
    sec_reads = {}
    for arm in ("fire", "control_break", "control_no_rest", "control_no_rest_close_variant"):
        v = second[arm][sec_ok[arm]]
        sec_reads[arm] = {"n_events": int(second[arm].size), "n_scorable": int(v.size),
                          "p_second_burst_within_15_pct": (round(float(v.mean() * 100), 2)
                                                           if v.size >= MIN_CELL else None)}
    diffs = {}
    fa = second["fire"][sec_ok["fire"]]
    for arm in ("control_break", "control_no_rest", "control_no_rest_close_variant"):
        a_r, _ = burst_arms["fire"]
        b_r, _ = burst_arms[arm]
        fb = second[arm][sec_ok[arm]]
        if fa.size >= MIN_CELL and fb.size >= MIN_CELL:
            d = block_boot_diff_ci(second["fire"] * 100, months[a_r],
                                   second[arm] * 100, months[b_r], BOOT_N, SEED + 7)
            diffs[arm] = {"diff_pp": round(float(fa.mean() - fb.mean()) * 100, 2),
                          "month_block": d}
        else:
            diffs[arm] = {"diff_pp": None, "month_block": None,
                          "note": f"arm too thin to compare (fire n={fa.size}, "
                                  f"{arm} n={fb.size}, MIN_CELL={MIN_CELL}) — "
                                  "printed, not skipped"}

    S_BURST = {
        "construction": ("burst-movers = own trailing p97 of roc5 >= +15%, evaluated AT "
                         "the bar. B1 = roc5 >= own p97 AND the trailing 63d low sits in "
                         "the prior 10 sessions. Rest = cumulative return from the B1 bar "
                         "inside [-50%, +25%] of the B1 5d gain for 2-5 sessions; the fire "
                         "is the first session AFTER the completed rest. Control (a) = the "
                         "rest gave back >61.8% of the burst; control (b) = no rest, roc5 "
                         "makes a new high in each of sessions 1..5."),
        "tier": "research/shadow — measurement only, zero authority",
        "fire_counts": {"legs": legs_sum,
                        "events_fire": int(burst_arms["fire"][0].size),
                        "control_break": int(burst_arms["control_break"][0].size),
                        "control_no_rest_strict_roc5": int(burst_arms["control_no_rest"][0].size),
                        "control_no_rest_close_variant": int(
                            burst_arms["control_no_rest_close_variant"][0].size),
                        "control_cells_dropped_as_also_events": {
                            k: overlap_removed[k] for k in
                            ("burst_vs_break", "burst_vs_norest", "burst_vs_norest_close")}},
        "thin_notes": [n for n in (
            thin_note("control arm (b) strict (roc5 makes a new high in each of sessions 1..5)",
                      int(burst_arms["control_no_rest"][0].size),
                      f"of {legs_sum['n_b1_bars']} B1 bars, five consecutive strictly-rising "
                      "roc5 readings is a rare shape — the close-based variant of the same "
                      "cohort is reported beside it for exactly this reason. Arm (a) "
                      "'broken rest' is the PRIMARY control and carries the verdict"),
            thin_note("control arm (b) close-based variant",
                      int(burst_arms["control_no_rest_close_variant"][0].size),
                      "same cohort, closes instead of roc5 making the new highs"),
            thin_note("S-BURST fires", int(burst_arms["fire"][0].size),
                      "B1 bars and the mover/recent-low legs print above")) if n],
        "second_burst": {"definition": "roc5 >= own trailing p95 at any bar in [e+1, e+15]",
                         "rates": sec_reads, "fire_minus_control": diffs},
        "primary_read": "P(second burst within 15 sessions) vs control arm (a) 'broken rest'",
        "hypothesis_sign": "POSITIVE difference would support the burst-rest-burst grammar",
        "variants": {"vs_control_break_arm_a": tables["burst_vs_break"],
                     "vs_control_no_rest_arm_b": tables["burst_vs_norest"],
                     "vs_control_no_rest_close_variant": tables["burst_vs_norest_close"]},
    }

    # ---- S-ROC12-TERM ----
    near5 = C.rolling(6, min_periods=6).max().shift(-5)
    fwd63 = C.rolling(63, min_periods=63).max().shift(-62)
    prox = ((near5 >= fwd63 * (1.0 - 1e-12)).astype(float)
            .where(fwd63.notna() & near5.notna()).to_numpy(dtype="float32"))
    tri, tci = pairs[5]["ev"]
    cri, cci = pairs[5]["ct"]
    pe, pc = prox[tri, tci], prox[cri, cci]
    pe_f, pc_f = pe[np.isfinite(pe)], pc[np.isfinite(pc)]
    tp_diff = block_boot_diff_ci(pe * 100, months[tri], pc * 100, months[cri],
                                 BOOT_N, SEED + 11)
    S_TERM = {
        "construction": ("burst-movers within 5% of their own 63d high. Fire: roc12 >= own "
                         "trailing p99 (252d). Control: same legs, roc12 own-history "
                         "percentile in [0.80, 0.90)."),
        "tier": "research/shadow — measurement only, zero authority",
        "fire_counts": {"legs": leg_counts(term["legs"]),
                        "events": int(tri.size), "controls": int(cri.size),
                        "control_cells_dropped_as_also_events": overlap_removed["term"]},
        "thin_notes": [n for n in (
            thin_note("S-ROC12-TERM fires", int(tri.size),
                      "the burst-mover leg, the within-5%-of-63d-high leg and the >=p99 "
                      "leg all print above"),) if n],
        "top_proximity": {
            "definition": ("fraction of events whose max close over [t, t+62] already "
                           "occurred within [t, t+5] — i.e. the extreme marked the local top"),
            "event_pct": (round(float(pe_f.mean() * 100), 2) if pe_f.size >= MIN_CELL else None),
            "control_pct": (round(float(pc_f.mean() * 100), 2) if pc_f.size >= MIN_CELL else None),
            "n_event": int(pe_f.size), "n_control": int(pc_f.size),
            "diff_pp": (round(float(pe_f.mean() - pc_f.mean()) * 100, 2)
                        if pe_f.size >= MIN_CELL and pc_f.size >= MIN_CELL else None),
            "month_block": tp_diff},
        "primary_read": "top_proximity difference (fires vs controls)",
        "hypothesis_sign": "POSITIVE difference would support ROC(12) extremes marking local tops",
        "variants": {"p99_vs_p80_90": tables["term"]},
    }
    return {"S_ROCX_TOP": S_TOP, "S_BURST_RHYTHM": S_BURST, "S_ROC12_TERM": S_TERM}


def run_grain(G, spy, gmeta) -> dict:
    index, cols = G.index, list(G.columns)
    fr_r, fr_c, ct_r, ct_c = [], [], [], []
    fr_trough, ct_trough = [], []
    legs = {"n_step1_deep": 0, "n_step1_mild": 0, "n_stabilization_bars": 0}
    per_series = []
    for j, t in enumerate(cols):
        s = G[t].dropna()
        if len(s) < 300:
            per_series.append({"series": t, "bars": len(s), "fires": 0,
                               "note": "under 300 bars — skipped, printed"})
            continue
        ev = washout_events(s)
        pos = index.get_indexer(s.index)
        for k in legs:
            legs[k] += int(ev[k])
        for key, rr, cc, tl in (("fire", fr_r, fr_c, fr_trough),
                                ("control", ct_r, ct_c, ct_trough)):
            for (s1, e, low) in ev[key]:
                rr.append(int(pos[e]))
                cc.append(j)
                tl.append(low)
        per_series.append({"series": t, "bars": len(s),
                           "fires": len(ev["fire"]), "controls": len(ev["control"])})
    eri = np.asarray(fr_r, dtype=np.int64)
    eci = np.asarray(fr_c, dtype=np.int64)
    cri = np.asarray(ct_r, dtype=np.int64)
    cci = np.asarray(ct_c, dtype=np.int64)
    fr_trough = np.asarray(fr_trough, dtype=float)
    ct_trough = np.asarray(ct_trough, dtype=float)
    (cri, cci), keep, dropped = disjoin((eri, eci), (cri, cci), len(cols))
    ct_trough = ct_trough[keep] if ct_trough.size else ct_trough

    # same-session vs same-month matching feasibility (printed either way)
    ev_dates = set(eri.tolist())
    ct_dates = set(cri.tolist())
    same_session = len(ev_dates & ct_dates)
    ev_m = (index.year * 100 + index.month).to_numpy()
    same_month = len(set(ev_m[eri].tolist()) & set(ev_m[cri].tolist())) if eri.size else 0
    n_ev_with_session_ctrl = int(np.isin(eri, list(ct_dates)).sum()) if eri.size else 0
    frac = (n_ev_with_session_ctrl / eri.size) if eri.size else 0.0
    use_month = frac < 0.50

    # month-matched control medians when session matching is too thin
    def month_pairs(F, key):
        """delta against same-MONTH controls (the declared fallback)."""
        ev = F[key][eri, eci]
        ct = F[key][cri, cci]
        med = pd.Series(ct).groupby(ev_m[cri]).median()
        lut = {int(k): float(v) for k, v in med.items()}
        base = np.array([lut.get(int(m), np.nan) for m in ev_m[eri]])
        return ev - base

    pairs = [{"key": "washout", "ev": (eri, eci), "ct": (cri, cci)}]
    tables = _pair_tables(pairs, lambda h: _frames_grain(G, spy, h), index, FRAMES_GRAIN)

    # month-matched deltas beside the session-matched ones
    month_tbl = {}
    for h in HORIZONS:
        F = _frames_grain(G, spy, h)
        row = {}
        for fk in ("excess_spy", "dd", "raw"):
            d = month_pairs(F, fk)
            ok = np.isfinite(d)
            if int(ok.sum()) < MIN_CELL:
                row[fk] = {"n": int(ok.sum()), "thin": True}
                continue
            cell = {"n": int(ok.sum()),
                    "delta_median_pp": round(float(np.median(d[ok]) * 100), 3)}
            if fk in BOOT_FRAMES:
                b = block_boot_ci(d[ok] * 100, ev_m[eri][ok], BOOT_N, SEED + h)
                if b:
                    cell["delta_ci95_month_block_pp"] = b.get("ci95")
                    cell["month_blocks"] = b.get("blocks")
            row[fk] = cell
        month_tbl[str(h)] = row
        del F

    # held_low_21 — does the next-21-session low stay above the step-1 trough low
    fmin21 = fwd_min(G, 21).to_numpy(dtype="float64")
    held_e = (fmin21[eri, eci] > fr_trough) if eri.size else np.array([])
    held_c = (fmin21[cri, cci] > ct_trough) if cri.size else np.array([])
    fin_e = np.isfinite(fmin21[eri, eci]) if eri.size else np.array([], dtype=bool)
    fin_c = np.isfinite(fmin21[cri, cci]) if cri.size else np.array([], dtype=bool)
    he = held_e[fin_e].astype(float) if fin_e.size else np.array([])
    hc = held_c[fin_c].astype(float) if fin_c.size else np.array([])
    held = {"definition": ("the min close over [t+1, t+21] stays above the step-1 washout "
                           "low (min close from the trough bar through the event bar)"),
            "event_pct": round(float(he.mean() * 100), 2) if he.size >= MIN_CELL else None,
            "control_pct": round(float(hc.mean() * 100), 2) if hc.size >= MIN_CELL else None,
            "n_event": int(he.size), "n_control": int(hc.size),
            "diff_pp": (round(float(he.mean() - hc.mean()) * 100, 2)
                        if he.size >= MIN_CELL and hc.size >= MIN_CELL else None),
            "month_block": (block_boot_diff_ci(he * 100, ev_m[eri][fin_e],
                                               hc * 100, ev_m[cri][fin_c], BOOT_N, SEED + 13)
                            if he.size and hc.size else None)}

    return {
        "construction": ("step 1: roc21 <= own-history p05 (rolling 504d, min 252). "
                         "step 2: the first session within the next 21 bars closing above "
                         "the max close of the prior 5 sessions — THAT bar is the event. "
                         "Controls: identical stabilization geometry after a MILDER decline "
                         "(roc21 own-history percentile in [0.10, 0.30))."),
        "tier": "research/shadow — measurement only, zero authority",
        "grain_note": ("SECTOR/ASSET grain deliberately — name-level standalone bottom "
                       "timers are a killed family (PSS-F1/F3/F4, DO_NOT_REBUILD rows "
                       "70/72/73); no name-grain washout construction exists in this file."),
        "universe": gmeta,
        "fire_counts": {"legs": legs, "events": int(eri.size), "controls": int(cri.size),
                        "series_with_at_least_one_fire": len(set(eci.tolist())),
                        "control_cells_dropped_as_also_events": int(dropped),
                        "per_series": per_series},
        "thin_notes": [n for n in (
            thin_note("S-ROCW-GRAIN fires", int(eri.size),
                      "step-1 deep bars and stabilization bars print above; a zero would "
                      "mean no deep decline ever produced a stabilization inside 21 sessions"),
            thin_note("S-ROCW-GRAIN controls", int(cri.size),
                      "milder-decline step-1 bars print above")) if n],
        "matching": {
            "same_session_dates_shared": int(same_session),
            "events_with_a_same_session_control": n_ev_with_session_ctrl,
            "events_total": int(eri.size),
            "same_session_coverage_pct": round(frac * 100, 1),
            "same_month_blocks_shared": int(same_month),
            "primary": ("same-MONTH matching (SAID SO: same-session coverage "
                        f"{round(frac * 100, 1)}% < 50% at this grain)") if use_month
                       else "same-session matching",
            "both_reported": True},
        "outcome_note": ("excess-vs-SPY on a futures series is a CROSS-ASSET read, not a "
                         "like-for-like benchmark — the raw frame is reported beside it "
                         "for exactly that reason. dd is close-based at this grain."),
        "held_low_21": held,
        "primary_read": "excess_spy delta at H=21 under the declared matching",
        "hypothesis_sign": "POSITIVE delta would support a tradable washout-stabilization zone",
        "session_matched": tables["washout"],
        "month_matched": month_tbl,
    }


# ─────────────────────────────────────────────────────────────────────────────
# verdicts
# ─────────────────────────────────────────────────────────────────────────────
def _verdict_from_ci(n: int, ci, point) -> tuple[str, str]:
    if n < MIN_CELL:
        return "THIN", f"n={n} < MIN_CELL={MIN_CELL}"
    if ci is None:
        return "THIN", f"n={n}, no CI (too few blocks)"
    lo, hi = ci
    if lo > 0:
        return "POSITIVE", f"delta {point:+.2f} CI [{lo:+.2f}, {hi:+.2f}] n={n}"
    if hi < 0:
        return "NEGATIVE", f"delta {point:+.2f} CI [{lo:+.2f}, {hi:+.2f}] n={n}"
    return "NULL", f"delta {point:+.2f} CI [{lo:+.2f}, {hi:+.2f}] straddles 0, n={n}"


def build_verdicts(res: dict) -> dict:
    v = {}
    top = res["S_ROCX_TOP"]
    t21 = top["variants"]["p95"].get("21", {}).get("frames", {}).get("dd", {})
    n = int(t21.get("n_matched", t21.get("n_events_with_outcome", 0)) or 0)
    verd, why = _verdict_from_ci(n, t21.get("delta_ci95_month_block_pp"),
                                 t21.get("delta_median_pp", float("nan")))
    if top["redundancy_vs_ext_z"]["redundant"]:
        verd = "REDUNDANT-WITH-EXT_Z"
        why = (f"max |rho| {top['redundancy_vs_ext_z']['max_abs_rho']} >= {RHO_FENCE} "
               f"(PM4 fence) — {why}")
    v["S_ROCX_TOP"] = {"verdict": verd, "driver": why,
                       "read": "dd_within_21 matched delta (pp), p95 variant",
                       "rho_max_abs": top["redundancy_vs_ext_z"]["max_abs_rho"]}

    g = res["S_ROCW_GRAIN"]
    use_month = g["matching"]["primary"].startswith("same-MONTH")
    cell = (g["month_matched"]["21"]["excess_spy"] if use_month
            else g["session_matched"]["21"]["frames"]["excess_spy"])
    n = int(cell.get("n", cell.get("n_matched", 0)) or 0)
    verd, why = _verdict_from_ci(n, cell.get("delta_ci95_month_block_pp"),
                                 cell.get("delta_median_pp", float("nan")))
    v["S_ROCW_GRAIN"] = {"verdict": verd, "driver": f"{why} [{g['matching']['primary']}]",
                         "read": "excess_spy matched delta (pp) at H=21"}

    b = res["S_BURST_RHYTHM"]
    d = b["second_burst"]["fire_minus_control"].get("control_break", {})
    mb = (d or {}).get("month_block") or {}
    nf = b["second_burst"]["rates"]["fire"]["n_scorable"]
    verd, why = _verdict_from_ci(nf, mb.get("ci95"),
                                 d.get("diff_pp") if d.get("diff_pp") is not None
                                 else float("nan"))
    v["S_BURST_RHYTHM"] = {"verdict": verd,
                           "driver": f"{why}; P(2nd burst) fire "
                                     f"{b['second_burst']['rates']['fire']['p_second_burst_within_15_pct']}% "
                                     f"vs broken-rest "
                                     f"{b['second_burst']['rates']['control_break']['p_second_burst_within_15_pct']}%",
                           "read": "P(second burst <=15 sessions) fire minus control arm (a)"}

    t = res["S_ROC12_TERM"]
    tp = t["top_proximity"]
    mb = tp.get("month_block") or {}
    verd, why = _verdict_from_ci(tp["n_event"], mb.get("ci95"),
                                 tp.get("diff_pp") or float("nan"))
    v["S_ROC12_TERM"] = {"verdict": verd,
                         "driver": f"{why}; top-proximity {tp['event_pct']}% vs "
                                   f"{tp['control_pct']}%",
                         "read": "top-proximity rate difference (pp)"}
    return v


def print_verdicts(res: dict) -> None:
    print()
    print("=" * 78)
    print("ROC EXTREMES BATTERY — VERDICTS (research/shadow tier; zero authority)")
    print("=" * 78)
    for k, v in res["verdicts"].items():
        print(f"{k:<18} {v['verdict']:<22} {v['read']}")
        print(f"{'':<18} {v['driver']}")
    print("-" * 78)
    print(f"runtime {res['meta']['runtime_sec']}s   panel {res['panel']['names']} names "
          f"x {res['panel']['sessions']} sessions   asof {REPRO_ASOF}")
    print("=" * 78)


# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    t0 = time.time()
    os.chdir(REPO)
    sys.path.insert(0, REPO)
    C, Hi, Lo, pmeta = build_panel()
    spy = load_spy(C.index)
    res: dict = {
        "meta": {
            "tier": "RESEARCH / SHADOW — measurements, not signals. Nothing here touches "
                    "admission, ranking, sizing or any surface.",
            "repro_asof": REPRO_ASOF, "horizons": list(HORIZONS),
            "loser_def": f"excess_spy < {LOSER_PP}pp at H",
            "min_cell": MIN_CELL, "boot": {"month_block": BOOT_N,
                                           "ticker_cluster": CLUSTER_BOOT_N,
                                           "arm_cap_rows": MAX_BOOT_ROWS,
                                           "frames_with_ci": list(BOOT_FRAMES)},
            "ruler": ("gate-matched matched-set delta = event value - median of the "
                      "same-session gate-matched controls; month-block bootstrap primary, "
                      "ticker-cluster bootstrap as the recurrence check; per-name-first "
                      "medians and a midpoint half-split beside the pooled read"),
            "stamping": "backward-only everywhere (pinned by tests/test_roc_extremes_battery.py)",
            "frame_identity_note": (
                "raw, excess_spy and excess_xs report the SAME delta_median_pp by "
                "construction, and that is not a copy-paste defect: the same-session "
                "control median already removes every additive session constant, and the "
                "SPY return and the cross-sectional median ARE session constants. The "
                "three frames therefore differ only in their unmatched pooled medians and "
                "loser rates. dd and mfe are per-name path statistics, not session "
                "constants, so their deltas are genuinely different reads."),
            "kill_fences": ["PSS-F1/F3/F4 standalone name-level bottom-timers (rows 70/72/73)",
                            "washout x turn entry seed (row 78)",
                            "bottom-radar PRIMED directional gate (row 120)",
                            "cross-sectional commodity momentum L/S (row 116)",
                            "absolute-threshold anchors as primary constructions (row 109)",
                            "PM4 redundancy fence |rho| >= 0.85 vs ext_z (row 89)"],
        },
        "panel": pmeta,
    }
    print(f"[panel] {pmeta['names']} names x {pmeta['sessions']} sessions "
          f"({pmeta['dates'][0]}..{pmeta['dates'][1]})  {round(time.time() - t0, 1)}s")
    res.update(run_name_grain(C, Hi, Lo, spy))
    print(f"[name-grain sensors done] {round(time.time() - t0, 1)}s")
    G, gmeta = build_grain_panel(C)
    res["S_ROCW_GRAIN"] = run_grain(G, spy.reindex(G.index), gmeta)
    print(f"[grain sensor done] {round(time.time() - t0, 1)}s")
    res["verdicts"] = build_verdicts(res)
    res["meta"]["runtime_sec"] = round(time.time() - t0, 1)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print_verdicts(res)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
