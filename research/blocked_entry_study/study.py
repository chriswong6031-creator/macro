"""BLOCKED-ENTRY STUDY — stop-based execution grading of bear_block-vetoed BUY fires.

Cohort: every raw CB/revBuy 3D-grid fire that the Golden Oracle refuses because of the
regime veto  bear_block = (~mo_bull) & (~above200) & (~w2_bull)   [confluence.py:316]
i.e. exactly the markers contracts.py stamps quality="regime_blocked". The keeper's own
"block" verdict (failed reclaim-and-hold / bearish divergence) is DISJOINT by construction
— confluence_v2.keeper_quality_map only grades (CB|revBuy) & ~bear_block — so the cohort is
already isolated to "would-enter with the veto off" without a second on/off pass.

Comparison arms: the contemporaneous TAKEN entries (CB|revBuy) & ~bear_block, and
random-date placebo entries on the same names matched count-per-name-year.

Execution (the operator's construction, frozen before any outcome was inspected):
  stop  = min(daily low of the fire 3D bar and the 2 prior 3D bars) - M*ATR14(daily)
  fill  = next session AFTER the fire bar's known_ts (its close session); price = that
          session's OPEN, falling back to its CLOSE where the store carries no open.
  exits (a) stop-only + 252-session time exit
        (b) stop + trail to breakeven once +1R
        (c) fixed 63-session time exit, no stop (packet-comparable ruler)
  stop triggers on a DAILY CLOSE below the stop; the intrabar-low rule is a sensitivity.

Design/test discipline: parameters frozen on data through DESIGN_END; only M (the ATR
buffer multiple) and the systemic-bear definition may be selected there. VERDICT era runs
with those frozen. Never tuned on the test era.

Run:  python3 study.py --mode pilot      (60 names, end-to-end)
      python3 study.py --mode full       (whole panel)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------- wiring ----
HERE = Path(__file__).resolve().parent
MACRO = HERE.parents[1]
CHART = Path(os.environ.get(
    "CHART_REPO",
    "/Users/chriswong/Documents/Cluade/charting-app/.claude/worktrees/mobile-search-live-quotes",
))
SIGNAL_SOURCE = CHART / "signal_layer" / "confluence.py"
SIGNAL_SOURCE_SHA256 = "30c12a90448579d689e2a9ed405055f6c44462cf0f69347940e619d020c7384d"

# This study is a frozen receipt, so silently importing whichever signal-layer
# bytes happen to occupy a personal worktree would make every downstream number
# unrepeatable.  The dependency is external because that is where the production
# implementation lives; pin its exact bytes and fail closed when they move.
try:
    _signal_sha = hashlib.sha256(SIGNAL_SOURCE.read_bytes()).hexdigest()
except OSError as exc:
    raise RuntimeError(
        f"blocked-entry study requires pinned signal source {SIGNAL_SOURCE}"
    ) from exc
if _signal_sha != SIGNAL_SOURCE_SHA256:
    raise RuntimeError(
        "blocked-entry signal source drifted: "
        f"expected {SIGNAL_SOURCE_SHA256}, got {_signal_sha}"
    )

# The imported signal layer also consults MACRO_REPO.  A caller's ambient value
# must not redirect half the study to a different checkout while the OHLC paths
# above read this one.
os.environ["MACRO_REPO"] = str(MACRO)
sys.path.insert(0, str(CHART))

from signal_layer import confluence as oracle  # noqa: E402

US_OHLCV = MACRO / "data" / "baskets" / "ohlcv"     # 2014+, has open
US_DEEP = MACRO / "data" / "stocks"                 # deep history, NO open
HK_DIR = MACRO / "data" / "hk_stocks"               # has open
CN_DIR = MACRO / "data" / "china_stocks"            # adjusted, has open
SPY_PATH = MACRO / "data" / "yahoo" / "SPY.parquet"  # closes-only back to 1993

# ------------------------------------------------------- FROZEN PARAMETERS ---
ANCHOR = 0                  # full-history oracle contract (_resample_3d docstring)
PHASE_SENSITIVITY = (1, 2)  # reported separately, never pooled
STOP_LOOKBACK_BARS = 3      # fire 3D bar + 2 prior
ATR_LEN = 14
ATR_MULT = 0.5              # TUNABLE on the design era only
ATR_SWEEP = (0.0, 0.25, 0.5, 0.75, 1.0)
HORIZON = 252
FIXED_HORIZON = 63
BOUGHT_LOW_SKIP = 5         # "never trades below entry after +5 sessions"
DESIGN_END = "2018-12-31"
DD_BANDS = ((0.00, 0.20), (0.20, 0.35), (0.35, 0.50), (0.50, 9.99))
DD_BAND_NAMES = ("dd_0_20", "dd_20_35", "dd_35_50", "dd_50_plus")
W2K_WASHOUT_MAX = 15        # "turned up from <15"
W2K_TURN_WINDOW = 2         # within last 2 two-week bars
SPY_DD_SYSTEMIC = 0.15      # def A: SPY >15% off its 252d high
SPY_BELOW200_DAYS = 40      # def B: below its 200dma for >40 sessions
MIN_FWD_SESSIONS = 21       # an event needs this much forward tape to be graded at all
MIN_R_FRAC = 0.005          # R below 0.5% of entry px is not R-graded (divide-by-~0 guard)
PLACEBO_SEED = 20260809

SIX_NAMES = ("UEC", "HL", "NEM", "9988.HK", "600547.SS", "002716.SZ")


def placebo_seed(sym: str) -> int:
    """Stable per-symbol seed; Python's salted ``hash`` is not a receipt."""
    digest = hashlib.md5(sym.encode("utf-8"), usedforsecurity=False).digest()
    return PLACEBO_SEED + (int.from_bytes(digest[:8], "big") % 100000)


# ------------------------------------------------------------------ data -----
def load_ohlc(sym: str) -> pd.DataFrame | None:
    """Merged daily OHLC. US names union the deep close/high/low store (pre-2014 history,
    no open) with the 2014+ OHLCV store (opens). The two stores were verified to share an
    adjustment basis (max |rel diff| 8.2e-7 on NEM's 3,140 overlapping sessions)."""
    frames: list[pd.DataFrame] = []
    if sym.endswith(".HK"):
        cands = [HK_DIR / f"{sym}.parquet"]
    elif sym.endswith((".SS", ".SZ")):
        cands = [CN_DIR / f"{sym}.parquet"]
    else:
        cands = [US_DEEP / f"{sym}.parquet", US_OHLCV / f"{sym}.parquet"]
    for p in cands:
        if not p.exists():
            continue
        try:
            frames.append(pd.read_parquet(p))
        except Exception:
            continue
    if not frames:
        return None
    hlc_parts, open_parts = [], []
    for f in frames:
        f = f.copy()
        f.index = pd.DatetimeIndex(f.index).tz_localize(None)
        f = f[~f.index.duplicated(keep="last")].sort_index()
        if {"high", "low", "close"}.issubset(f.columns):
            hlc_parts.append(f[["high", "low", "close"]])
        if "open" in f.columns:
            open_parts.append(f["open"])
    if not hlc_parts:
        return None
    hlc = hlc_parts[0]
    for nxt in hlc_parts[1:]:
        hlc = hlc.combine_first(nxt)
    opn = open_parts[0] if open_parts else pd.Series(np.nan, index=hlc.index, dtype="float64")
    for nxt in open_parts[1:]:
        opn = opn.combine_first(nxt)
    df = hlc.dropna(subset=["close"]).copy()
    df["open"] = opn.reindex(df.index)
    df["high"] = df["high"].fillna(df["close"])
    df["low"] = df["low"].fillna(df["close"])
    return df if len(df) >= 320 else None


def wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = ATR_LEN) -> np.ndarray:
    """ATR on the DAILY bars using the house SMA-seeded Wilder RMA (confluence._rma)."""
    prev = np.empty_like(close)
    prev[0] = close[0]
    prev[1:] = close[:-1]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    tr[0] = high[0] - low[0]
    return oracle._rma(pd.Series(tr), n).to_numpy()


def _first(mask: np.ndarray) -> int:
    """Index of the first True, or -1."""
    if mask.size == 0:
        return -1
    i = int(np.argmax(mask))
    return i if bool(mask[i]) else -1


# ------------------------------------------------------------- execution -----
def sim_exits(entry_i: int, entry_px: float, stop_px: float,
              close: np.ndarray, high: np.ndarray, low: np.ndarray,
              opn: np.ndarray | None = None) -> dict:
    """The three graded exits + the stop diagnostics, all off the daily tape.

    The entry bar itself can stop the position (we are filled at its open)."""
    n = close.size
    end = min(n, entry_i + HORIZON + 1)
    c, h, l = close[entry_i:end], high[entry_i:end], low[entry_i:end]
    censored = (entry_i + HORIZON) >= n
    R = entry_px - stop_px
    out: dict = {"R_px": float(R), "n_fwd": int(end - entry_i - 1), "censored": bool(censored)}

    below = c < stop_px
    si = _first(below)
    out["stop_hit_close"] = si >= 0
    out["stop_hit_intrabar"] = _first(l <= stop_px) >= 0

    # (a) stop-only + 252d time exit
    if si >= 0:
        out["a_px"], out["a_reason"], out["a_bars"] = float(c[si]), "stop", si
    else:
        out["a_px"] = float(c[-1])
        out["a_reason"] = "censored" if censored else "time252"
        out["a_bars"] = int(c.size - 1)

    # (b) stop + trail to breakeven once +1R (close-based arm, close-based stop)
    if R > 0:
        arm = _first(c >= entry_px + R)
        if arm < 0:
            out["b_px"], out["b_reason"], out["b_bars"] = out["a_px"], out["a_reason"], out["a_bars"]
        else:
            s1 = _first(below[:arm + 1])
            if s1 >= 0:
                out["b_px"], out["b_reason"], out["b_bars"] = float(c[s1]), "stop", s1
            else:
                post = c[arm + 1:] < entry_px
                s2 = _first(post)
                if s2 >= 0:
                    j = arm + 1 + s2
                    out["b_px"], out["b_reason"], out["b_bars"] = float(c[j]), "be_stop", j
                else:
                    out["b_px"] = float(c[-1])
                    out["b_reason"] = "censored" if censored else "time252"
                    out["b_bars"] = int(c.size - 1)
    else:
        out["b_px"], out["b_reason"], out["b_bars"] = out["a_px"], out["a_reason"], out["a_bars"]

    # (d) SENSITIVITY: the same stop read intrabar — triggered by the session LOW touching
    # the stop, filled at the stop level, or at the open when the session gapped through it.
    di = _first(l <= stop_px)
    if di >= 0:
        fill = stop_px
        if opn is not None:
            o = opn[entry_i + di]
            if np.isfinite(o) and o < stop_px:
                fill = float(o)
        out["d_px"], out["d_reason"], out["d_bars"] = float(fill), "stop_intrabar", di
    else:
        out["d_px"] = float(c[-1])
        out["d_reason"] = "censored" if censored else "time252"
        out["d_bars"] = int(c.size - 1)

    # (c) fixed 63-session time exit, NO stop (packet-comparable)
    if entry_i + FIXED_HORIZON < n:
        out["c_px"], out["c_reason"] = float(close[entry_i + FIXED_HORIZON]), "time63"
        out["c_bars"] = FIXED_HORIZON
    else:
        out["c_px"], out["c_reason"] = float(c[-1]), "censored"
        out["c_bars"] = int(c.size - 1)

    # R is only meaningful when the stop sits a real distance below the fill; a stop that
    # lands within MIN_R_FRAC of the entry makes the R multiple a divide-by-~0 artefact.
    r_ok = R > 0 and (R / entry_px) >= MIN_R_FRAC
    out["r_frac"] = float(R / entry_px)
    out["r_graded"] = bool(r_ok)
    for k in "abcd":
        px = out[f"{k}_px"]
        out[f"{k}_ret"] = float(px / entry_px - 1)
        out[f"{k}_R"] = float((px - entry_px) / R) if r_ok else None

    # descriptive: runups + "bought the low"
    for horiz, tag in ((126, "126"), (252, "252")):
        e2 = min(n, entry_i + horiz + 1)
        seg = high[entry_i:e2]
        out[f"runup_{tag}"] = float(seg.max() / entry_px - 1) if seg.size >= 21 else None
    seg = low[entry_i + BOUGHT_LOW_SKIP: min(n, entry_i + HORIZON + 1)]
    out["bought_low"] = bool(seg.min() >= entry_px) if seg.size >= 20 else None
    return out


# ------------------------------------------------------------ per symbol -----
def events_for_symbol(sym: str, anchor: int = ANCHOR) -> list[dict]:
    """Every blocked / taken fire on this name, plus its matched placebo draws."""
    df = load_ohlc(sym)
    if df is None:
        return []
    dc = df["close"]
    try:
        sig = oracle.compute_signals(dc, bar_anchor=anchor)
    except Exception:
        return []
    if sig.empty:
        return []
    rows = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    if len(rows) < 40:
        return []

    didx = df.index
    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    opn = df["open"].to_numpy(float)
    atr = wilder_atr(high, low, close)

    # 3D bar -> daily session boundaries (compute_signals uses the identical grouping)
    od, cd, _px = oracle._3d_groups(dc, anchor)
    bar_open_pos = didx.searchsorted(od)
    bar_close_pos = didx.searchsorted(cd)
    pos_of_bar = {ts: j for j, ts in enumerate(od)}

    # --- conditioning series -------------------------------------------------
    roll252 = pd.Series(close, index=didx).rolling(252, min_periods=60).max().to_numpy()
    # 2W StochRSI %K, leak-free: the PRIOR CLOSED 2W bar, mirroring w2_bull's shift(1)+ffill
    w2 = oracle._resample_2w(dc, 0)
    k2, _d2 = oracle.stoch_rsi_kd(w2)
    turn_up = (k2 > k2.shift(1)) & (k2.shift(1) < W2K_WASHOUT_MAX)
    turn_recent = turn_up.rolling(W2K_TURN_WINDOW, min_periods=1).max().astype(bool)
    k2_on3 = k2.shift(1).reindex(rows.index, method="ffill")
    turn_on3 = turn_recent.shift(1).reindex(rows.index, method="ffill").fillna(False).astype(bool)

    raw = (rows["CB"] | rows["revBuy"]).to_numpy(bool)
    bblk = rows["bear_block"].to_numpy(bool)
    cb = rows["CB"].to_numpy(bool)
    rb = rows["revBuy"].to_numpy(bool)
    known = pd.DatetimeIndex(rows["known_ts"])
    k2v = k2_on3.to_numpy(float)
    tuv = turn_on3.to_numpy(bool)

    market = "HK" if sym.endswith(".HK") else ("CN" if sym.endswith((".SS", ".SZ")) else "US")
    out: list[dict] = []

    def build(i: int, arm: str) -> dict | None:
        """Assemble one event at positional row i of the non-NaN signal rows."""
        j = pos_of_bar.get(rows.index[i])
        if j is None or j < STOP_LOOKBACK_BARS - 1:
            return None
        kpos = int(didx.searchsorted(known[i]))
        entry_i = kpos + 1
        if entry_i >= len(didx) - MIN_FWD_SESSIONS:
            return None
        lo_from = bar_open_pos[j - (STOP_LOOKBACK_BARS - 1)]
        lo_to = bar_close_pos[j]
        base_low = float(np.nanmin(low[lo_from:lo_to + 1]))
        a = float(atr[kpos])
        if not np.isfinite(a) or not np.isfinite(base_low) or a <= 0:
            return None
        px_open, px_close = opn[entry_i], close[entry_i]
        if np.isfinite(px_open) and px_open > 0:
            entry_px, basis = float(px_open), "open"
        else:
            entry_px, basis = float(px_close), "close"
        h252 = roll252[kpos]
        dd = float(close[kpos] / h252 - 1) if np.isfinite(h252) and h252 > 0 else None
        ev = {
            "sym": sym, "market": market, "arm": arm,
            "bar_open": str(rows.index[i].date()), "known_ts": str(known[i].date()),
            "entry_date": str(didx[entry_i].date()), "entry_px": entry_px, "entry_basis": basis,
            "kind": ("CB" if cb[i] and not rb[i] else "revBuy" if rb[i] and not cb[i] else "both")
            if arm != "placebo" else "placebo",
            "base_low3": base_low, "atr14": a,
            "dd252": dd, "k2w": float(k2v[i]) if np.isfinite(k2v[i]) else None,
            "total_washout": bool(tuv[i]),
        }
        # the always-close entry basis, as an entry-price sensitivity
        ev["entry_px_closebasis"] = float(px_close)
        for m in ATR_SWEEP:
            stop = base_low - m * a
            r = sim_exits(entry_i, entry_px, stop, close, high, low, opn)
            r["stop_px"] = float(stop)
            ev[f"m{m}"] = r
        rc = sim_exits(entry_i, float(px_close), base_low - ATR_MULT * a, close, high, low, opn)
        ev["closebasis"] = {k: rc[k] for k in ("a_ret", "a_R", "c_ret", "stop_hit_close")}
        return ev

    for i in np.flatnonzero(raw & bblk):
        ev = build(int(i), "blocked")
        if ev:
            out.append(ev)
    for i in np.flatnonzero(raw & ~bblk):
        ev = build(int(i), "taken")
        if ev:
            out.append(ev)

    # --- placebo: random dates on this name, matched count per name-year ------
    blocked_years: dict[int, int] = {}
    for ev in out:
        if ev["arm"] == "blocked":
            y = int(ev["entry_date"][:4])
            blocked_years[y] = blocked_years.get(y, 0) + 1
    if blocked_years:
        rng = np.random.default_rng(placebo_seed(sym))
        yrs = np.array([d.year for d in rows.index])
        for y, k in blocked_years.items():
            pool = np.flatnonzero((yrs == y) & ~raw)
            if pool.size == 0:
                continue
            for i in rng.choice(pool, size=min(k, pool.size), replace=False):
                ev = build(int(i), "placebo")
                if ev:
                    out.append(ev)
    return out


def _worker(args):
    sym, anchor = args
    try:
        return events_for_symbol(sym, anchor)
    except Exception as e:  # a panel must survive one bad name
        print(f"  !! {sym}: {type(e).__name__}: {e}", flush=True)
        return []


# ------------------------------------------------------------ market state ---
def spy_state() -> pd.DataFrame:
    spy = pd.read_parquet(SPY_PATH)
    s = spy["close"].dropna()
    s.index = pd.DatetimeIndex(s.index).tz_localize(None)
    dd = s / s.rolling(252, min_periods=60).max() - 1
    ma200 = s.rolling(200).mean()
    below = (s < ma200)
    # consecutive sessions below the 200dma
    grp = (~below).cumsum()
    run = below.groupby(grp).cumsum()
    out = pd.DataFrame({"spy_dd": dd, "spy_below200": below, "spy_below200_run": run})
    out["sysA"] = out["spy_dd"] <= -SPY_DD_SYSTEMIC
    out["sysB"] = out["spy_below200_run"] > SPY_BELOW200_DAYS
    out["sysAB"] = out["sysA"] | out["sysB"]
    return out


# --------------------------------------------------------------- metrics -----
def _pct(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), 4)


def cohort_metrics(evs: list[dict], m: float = ATR_MULT, variant: str = "a") -> dict:
    """Every headline number for one cohort under one ATR multiple and one exit variant."""
    n = len(evs)
    if n == 0:
        return {"n": 0}
    key = f"m{m}"
    rets = np.array([e[key][f"{variant}_ret"] for e in evs], float)
    Rs = np.array([e[key][f"{variant}_R"] for e in evs
                   if e[key][f"{variant}_R"] is not None], float)
    stop_c = np.array([e[key]["stop_hit_close"] for e in evs], bool)
    stop_i = np.array([e[key]["stop_hit_intrabar"] for e in evs], bool)
    bl = [e[key]["bought_low"] for e in evs if e[key]["bought_low"] is not None]
    ru126 = [e[key]["runup_126"] for e in evs if e[key]["runup_126"] is not None]
    ru252 = [e[key]["runup_252"] for e in evs if e[key]["runup_252"] is not None]
    cens = np.array([e[key]["censored"] for e in evs], bool)
    # date-clustered: one vote per (entry) date
    bydate: dict[str, list[float]] = {}
    for e in evs:
        bydate.setdefault(e["entry_date"], []).append(e[key][f"{variant}_ret"])
    dmed = [float(np.median(v)) for v in bydate.values()]
    capt = [e[key][f"{variant}_ret"] / e[key]["runup_252"]
            for e in evs if e[key]["runup_252"] not in (None, 0) and e[key]["runup_252"] > 0.01]
    rfrac = np.array([e[key]["r_frac"] for e in evs], float)
    wR = np.clip(Rs, np.percentile(Rs, 1), np.percentile(Rs, 99)) if Rs.size >= 20 else Rs
    return {
        "n": n,
        "n_names": len({e["sym"] for e in evs}),
        "n_dates": len(bydate),
        "expectancy_R": _pct(Rs.mean()) if Rs.size else None,
        "expectancy_R_winsor99": _pct(wR.mean()) if wR.size else None,
        "median_R": _pct(np.median(Rs)) if Rs.size else None,
        "n_R_graded": int(Rs.size),
        "median_risk_frac": _pct(np.median(rfrac)) if rfrac.size else None,
        "win_rate": _pct((rets > 0).mean()),
        "stop_hit_rate": _pct(stop_c.mean()),
        "stop_hit_rate_intrabar": _pct(stop_i.mean()),
        "mean_ret": _pct(rets.mean()),
        "median_ret": _pct(np.median(rets)),
        "p90_ret": _pct(np.percentile(rets, 90)),
        "p95_ret": _pct(np.percentile(rets, 95)),
        "bought_low_rate": _pct(np.mean(bl)) if bl else None,
        "median_runup_126": _pct(np.median(ru126)) if ru126 else None,
        "median_runup_252": _pct(np.median(ru252)) if ru252 else None,
        "median_capture_252": _pct(np.median(capt)) if capt else None,
        "median_of_per_date_medians": _pct(np.median(dmed)) if dmed else None,
        "censored_share": _pct(cens.mean()),
    }


def era_of(e: dict) -> str:
    return "design" if e["entry_date"] <= DESIGN_END else "verdict"


def dd_band(e: dict) -> str | None:
    if e["dd252"] is None:
        return None
    d = -e["dd252"]
    for (lo, hi), nm in zip(DD_BANDS, DD_BAND_NAMES):
        if lo <= d < hi:
            return nm
    return DD_BAND_NAMES[0] if d < 0 else DD_BAND_NAMES[-1]


def build_tables(events: list[dict], sysdef: str, m: float, markets: tuple[str, ...] | None = None) -> dict:
    """All reported tables, for one systemic-bear definition, ATR multiple and market set.

    The market filter matters: the systemic axis is measured on SPY, which is a meaningful
    regime ruler only for the US panel. CN/HK names are reported on their own tables."""
    if markets is not None:
        events = [e for e in events if e["market"] in markets]
    T: dict = {"markets": list(markets) if markets else "all"}
    arms = ("blocked", "taken", "placebo")
    for variant in ("a", "b", "c", "d"):
        T[f"by_arm_exit_{variant}"] = {
            a: {era: cohort_metrics([e for e in events
                                     if e["arm"] == a and era_of(e) == era], m, variant)
                for era in ("design", "verdict", "pooled")}
            for a in arms}
    # pooled fill-in (era_of never returns "pooled")
    for variant in ("a", "b", "c", "d"):
        for a in arms:
            T[f"by_arm_exit_{variant}"][a]["pooled"] = cohort_metrics(
                [e for e in events if e["arm"] == a], m, variant)

    blocked = [e for e in events if e["arm"] == "blocked"]
    # the 2x2: systemic x total-washout
    T["two_by_two"] = {}
    for era in ("design", "verdict", "pooled"):
        sel = blocked if era == "pooled" else [e for e in blocked if era_of(e) == era]
        cell = {}
        for sysv in (False, True):
            for tw in (False, True):
                sub = [e for e in sel if bool(e[sysdef]) == sysv and bool(e["total_washout"]) == tw]
                cell[f"systemic={sysv}|washout={tw}"] = cohort_metrics(sub, m, "a")
        T["two_by_two"][era] = cell
    # depth bands
    T["depth_bands"] = {}
    for era in ("design", "verdict", "pooled"):
        sel = blocked if era == "pooled" else [e for e in blocked if era_of(e) == era]
        T["depth_bands"][era] = {
            nm: cohort_metrics([e for e in sel if dd_band(e) == nm], m, "a")
            for nm in DD_BAND_NAMES}
    # systemic split alone, all three definitions
    T["systemic_split"] = {
        d: {str(v): cohort_metrics([e for e in blocked if bool(e[d]) == v], m, "a")
            for v in (False, True)}
        for d in ("sysA", "sysB", "sysAB")}
    T["washout_flag_split"] = {
        str(v): cohort_metrics([e for e in blocked if bool(e["total_washout"]) == v], m, "a")
        for v in (False, True)}
    # fire density quartiles
    dens = np.array([e["fire_density"] for e in blocked], float)
    if dens.size:
        qs = np.percentile(dens, [25, 50, 75])
        def qlab(d):
            return "q1" if d <= qs[0] else "q2" if d <= qs[1] else "q3" if d <= qs[2] else "q4"
        T["fire_density_quartiles"] = {
            "cuts": [float(x) for x in qs],
            **{q: cohort_metrics([e for e in blocked if qlab(e["fire_density"]) == q], m, "a")
               for q in ("q1", "q2", "q3", "q4")}}
    return T


# ------------------------------------------------------------------ main -----
def resolve_universe(mode: str) -> list[str]:
    us = {p.stem for p in US_OHLCV.glob("*.parquet")} | {p.stem for p in US_DEEP.glob("*.parquet")}
    hk = {p.stem for p in HK_DIR.glob("*.parquet")}
    cn = {p.stem for p in CN_DIR.glob("*.parquet")}
    allsyms = sorted(us) + sorted(hk) + sorted(cn)
    if mode == "full":
        return allsyms
    have = [s for s in SIX_NAMES if s in set(allsyms)]
    rest = [s for s in sorted(us) if s not in have]
    rng = np.random.default_rng(7)
    pick = list(rng.choice(rest, size=min(60 - len(have), len(rest)), replace=False))
    return have + pick


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="pilot", choices=("pilot", "full"))
    ap.add_argument("--anchor", type=int, default=ANCHOR)
    ap.add_argument("--procs", type=int, default=20)
    ap.add_argument("--out", default=str(HERE / "results.json"))
    args = ap.parse_args()

    syms = resolve_universe(args.mode)
    print(f"[universe] mode={args.mode} n={len(syms)} anchor={args.anchor}", flush=True)

    import multiprocessing as mp
    with mp.Pool(args.procs) as pool:
        chunks = pool.map(_worker, [(s, args.anchor) for s in syms], chunksize=8)
    events = [e for c in chunks for e in c]
    print(f"[events] {len(events)} raw", flush=True)
    if not events:
        print("no events"); return 1

    # --- market state + fire density (central) -------------------------------
    st = spy_state()
    sidx = st.index
    for e in events:
        d = pd.Timestamp(e["known_ts"])
        p = int(sidx.searchsorted(d, side="right")) - 1
        if p < 0:
            e["spy_dd"], e["sysA"], e["sysB"], e["sysAB"] = None, False, False, False
            e["spy_below200"] = None
        else:
            e["spy_dd"] = _pct(st["spy_dd"].iloc[p])
            e["spy_below200"] = bool(st["spy_below200"].iloc[p])
            for k in ("sysA", "sysB", "sysAB"):
                e[k] = bool(st[k].iloc[p])
    dens: dict[str, int] = {}
    for e in events:
        if e["arm"] == "blocked":
            dens[e["known_ts"]] = dens.get(e["known_ts"], 0) + 1
    for e in events:
        e["fire_density"] = dens.get(e["known_ts"], 0)

    # --- design-era tuning (the ONLY tuning permitted) -----------------------
    # Scoped to the US panel, which is the panel the systemic (SPY) axis rules.
    design_blocked = [e for e in events if e["arm"] == "blocked" and era_of(e) == "design"
                      and e["market"] == "US"]
    sweep = {f"m={m}": cohort_metrics(design_blocked, m, "a") for m in ATR_SWEEP}
    sysdef_sel = {d: {str(v): cohort_metrics(
        [e for e in design_blocked if bool(e[d]) == v], ATR_MULT, "a") for v in (False, True)}
        for d in ("sysA", "sysB", "sysAB")}
    # Selection criterion is the design-era MEAN RAW RETURN, not expectancy in R: R is the
    # entry-to-stop distance, so shrinking the buffer shrinks the denominator and inflates
    # R-expectancy monotonically — tuning on R would always pick the tightest stop for a
    # purely arithmetic reason. Raw return prices the real trade-off (a tighter stop takes
    # more stop-outs; a looser one takes bigger losses).
    valid = [(m, sweep[f"m={m}"].get("mean_ret")) for m in ATR_SWEEP
             if sweep[f"m={m}"].get("mean_ret") is not None]
    m_sel = max(valid, key=lambda kv: kv[1])[0] if valid else ATR_MULT
    # Systemic definition: selected on the design era by ABSOLUTE separation of the two
    # regimes' raw returns — which definition splits the axis most cleanly, irrespective of
    # which side comes out ahead. A signed criterion would bake the operator's hypothesised
    # direction into the selection. All three definitions are reported in both eras anyway.
    seps = {}
    for d in ("sysA", "sysB", "sysAB"):
        a = sysdef_sel[d]["False"].get("mean_ret")
        b = sysdef_sel[d]["True"].get("mean_ret")
        seps[d] = abs(a - b) if (a is not None and b is not None) else None
    ok = {k: v for k, v in seps.items() if v is not None}
    sys_sel = max(ok, key=lambda k: ok[k]) if ok else "sysAB"
    print(f"[design-era tuning] n={len(design_blocked)} ATR mult -> {m_sel}; systemic def -> {sys_sel}",
          flush=True)

    # --- coverage ------------------------------------------------------------
    blocked = [e for e in events if e["arm"] == "blocked"]
    cov = {
        "universe_requested": len(syms),
        "names_with_events": len({e["sym"] for e in events}),
        "n_events": len(events),
        "by_arm": {a: sum(1 for e in events if e["arm"] == a) for a in ("blocked", "taken", "placebo")},
        "blocked_by_market": {mk: sum(1 for e in blocked if e["market"] == mk)
                              for mk in ("US", "HK", "CN")},
        "by_market_arm": {mk: {a: sum(1 for e in events if e["market"] == mk and e["arm"] == a)
                               for a in ("blocked", "taken", "placebo")}
                          for mk in ("US", "HK", "CN")},
        "us_blocked_by_era": {era: sum(1 for e in blocked if e["market"] == "US" and era_of(e) == era)
                              for era in ("design", "verdict")},
        "us_names_with_blocked": len({e["sym"] for e in blocked if e["market"] == "US"}),
        "entry_basis_blocked": {b: sum(1 for e in blocked if e["entry_basis"] == b)
                                for b in ("open", "close")},
        "entry_basis_blocked_by_era": {
            era: {b: sum(1 for e in blocked if era_of(e) == era and e["entry_basis"] == b)
                  for b in ("open", "close")} for era in ("design", "verdict")},
        "blocked_by_era": {era: sum(1 for e in blocked if era_of(e) == era)
                           for era in ("design", "verdict")},
        "date_range_blocked": [min(e["entry_date"] for e in blocked),
                               max(e["entry_date"] for e in blocked)] if blocked else None,
        "median_entry_date_blocked": (sorted(e["entry_date"] for e in blocked)[len(blocked) // 2]
                                      if blocked else None),
        "six_names_present": {s: (s in {e["sym"] for e in events}) for s in SIX_NAMES},
    }

    payload = {
        "meta": {
            "generated": pd.Timestamp.now(tz="UTC").isoformat(),
            "mode": args.mode, "anchor": args.anchor,
            "veto": "bear_block = (~mo_bull) & (~above200) & (~w2_bull)  [confluence.py:316]",
            "cohort": "raw (CB|revBuy) & bear_block — keeper verdicts never reach these bars",
            "frozen": {"stop_lookback_3d_bars": STOP_LOOKBACK_BARS, "atr_len": ATR_LEN,
                       "atr_mult_spec": ATR_MULT, "horizon": HORIZON,
                       "fixed_horizon": FIXED_HORIZON, "design_end": DESIGN_END,
                       "dd_bands": DD_BAND_NAMES, "w2k_washout_max": W2K_WASHOUT_MAX,
                       "spy_dd_systemic": SPY_DD_SYSTEMIC,
                       "spy_below200_days": SPY_BELOW200_DAYS},
            "stop_rule": "daily CLOSE < stop (intrabar low reported as sensitivity)",
            "entry_rule": "next session after known_ts; OPEN, else CLOSE where no open exists",
            "signal_source": {
                "path": str(SIGNAL_SOURCE),
                "sha256": SIGNAL_SOURCE_SHA256,
                "chart_repo_commit": "f80116fad640c97e5a245ea9ab260e12d9e2cf25",
            },
            "placebo_seed_rule": "20260809 + md5(symbol)[:8] mod 100000",
        },
        "coverage": cov,
        "design_era_tuning": {
            "atr_mult_sweep_design_only": sweep,
            "systemic_def_sweep_design_only": sysdef_sel,
            "selected_atr_mult": m_sel,
            "selected_systemic_def": sys_sel,
            "systemic_def_abs_separation_design": {k: _pct(v) for k, v in seps.items()},
            "spec_default_atr_mult": ATR_MULT,
            "tuning_panel": "US only (the panel the SPY systemic axis rules)",
        },
        # PRIMARY: the US panel at the spec-frozen 0.5 ATR buffer and the spec's own
        # composite systemic definition (SPY >15% off high OR >40 sessions below its 200dma).
        "tables_us": build_tables(events, "sysAB", ATR_MULT, ("US",)),
        "tables_us_design_selected": build_tables(events, sys_sel, m_sel, ("US",)),
        "tables_cn": build_tables(events, "sysAB", ATR_MULT, ("CN",)),
        "tables_hk": build_tables(events, "sysAB", ATR_MULT, ("HK",)),
        "tables_all_markets": build_tables(events, "sysAB", ATR_MULT),
    }

    # six known names, per-event rows
    six = {}
    for s in SIX_NAMES:
        rowsx = [e for e in events if e["sym"] == s and e["arm"] == "blocked"]
        key = f"m{ATR_MULT}"
        six[s] = {
            "present": bool([e for e in events if e["sym"] == s]),
            "n_blocked": len(rowsx),
            "n_taken": len([e for e in events if e["sym"] == s and e["arm"] == "taken"]),
            "metrics": cohort_metrics(rowsx, ATR_MULT, "a") if rowsx else {"n": 0},
            "last_events": [
                {"bar_open": e["bar_open"], "known_ts": e["known_ts"], "entry_date": e["entry_date"],
                 "entry_px": round(e["entry_px"], 4), "basis": e["entry_basis"],
                 "stop": round(e[key]["stop_px"], 4), "dd252": e["dd252"], "k2w": e["k2w"],
                 "washout": e["total_washout"], "sysAB": e["sysAB"],
                 "a_ret": _pct(e[key]["a_ret"]), "a_R": _pct(e[key]["a_R"]),
                 "a_reason": e[key]["a_reason"], "c_ret": _pct(e[key]["c_ret"]),
                 "runup_252": _pct(e[key]["runup_252"])}
                for e in sorted(rowsx, key=lambda x: x["entry_date"])[-8:]],
        }
    payload["six_names"] = six

    # entry-basis sensitivity (all-close basis) on the US blocked cohort, split by era so
    # the era confound is visible: pre-2014 tape carries no opens, so the design era is
    # mostly close-filled while the verdict era is mostly open-filled.
    payload["sensitivity_entry_basis"] = {}
    for era in ("design", "verdict", "pooled"):
        sel = [e for e in blocked if e["market"] == "US" and (era == "pooled" or era_of(e) == era)]
        if not sel:
            continue
        cb_ret = np.array([e["closebasis"]["a_ret"] for e in sel], float)
        cb_R = np.array([e["closebasis"]["a_R"] for e in sel
                         if e["closebasis"]["a_R"] is not None], float)
        payload["sensitivity_entry_basis"][era] = {
            "primary_open_with_close_fallback": cohort_metrics(sel, ATR_MULT, "a"),
            "all_next_close_basis": {
                "n": int(cb_ret.size),
                "expectancy_R": _pct(cb_R.mean()) if cb_R.size else None,
                "win_rate": _pct((cb_ret > 0).mean()) if cb_ret.size else None,
                "median_ret": _pct(np.median(cb_ret)) if cb_ret.size else None,
            },
        }

    Path(args.out).write_text(json.dumps(payload, indent=1, default=str))
    pd.DataFrame([{k: v for k, v in e.items() if not isinstance(v, dict)} for e in events]).to_parquet(
        HERE / f"events_anchor{args.anchor}.parquet")
    print(f"[done] -> {args.out}", flush=True)
    hb = payload["tables_us"]["by_arm_exit_a"]
    print("  [US panel, exit (a), m=0.5]")
    for a in ("blocked", "taken", "placebo"):
        p = hb[a]["pooled"]
        print(f"  {a:8s} n={p.get('n')} expR={p.get('expectancy_R')} wr={p.get('win_rate')} "
              f"stop={p.get('stop_hit_rate')} medret={p.get('median_ret')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
