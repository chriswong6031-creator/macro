#!/usr/bin/env python3
"""Footprint picker — EXECUTES the frozen prereg
``research/prophet_us_audit/FOOTPRINT_PICKER_PREREG_2026-08-11.md`` §1-§5.

The second layer on early admission: on the union admission set (C1-relaxed union the
dot-only episodes of the bake-off plane), do accumulation-footprint features at the fire
instant, and post-trough evidence POLICIES, separate durable entries from false starts —
under labels that cannot be gamed by stop-width arithmetic?

Both §RT defects of the bake-off are designed out by the charter and honoured here:
  * labels carry NO false-bounce leg (the P_low anchor is gone from the label), and
  * the primary basis X is fully entry-anchored (entry - 2 x ATR14), so a feature cannot
    win by placing the stop further away.

Volume-profile features reuse the product's own engine AS-IS — ``indicators_m2``'s
``anchored_vwap`` / ``rolling_poc`` / ``poc_retest_hold`` — so a footprint measured here is
the footprint the Terminal draws. Dark-pool participation reuses ``darkpool_signals``'s
``trailing_z`` / ``usable_history`` / ``streak_above_norm`` conventions.

Measurement / display tier throughout: no gate, rank, veto or engine change ships from this
file. Promotion of anything found here goes through the program's own sequencing.

Run:  python3 research/prophet_us_audit/footprint_picker.py [--tickers STLD,NEM] [--out p.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from engine.indicators_m2 import (  # noqa: E402  the product's own footprint engine
    anchored_vwap, poc_retest_hold, rolling_poc, volume_profile,
)
from engine.darkpool_signals import (  # noqa: E402  the desk's own participation conventions
    Z_WINDOW, Z_MIN_OBS, STREAK_WINDOW, streak_above_norm, trailing_z, usable_history,
)
from engine.stock_technicals import atr as wilder_atr  # noqa: E402

# ------------------------------------------------------------------ frozen constants (§1-§5)
EPISODES_SHA = "305990306ef"          # bake-off plane vintage, recorded as provenance
UNION_GAP = 3                         # C2r kept only with NO C1 fire within +/-3 sessions
FWD_MAX = 42                          # label horizon
MIN_FWD = 30                          # below this a label row is TRUNCATED, counted not graded
STOP_F_PCT = 0.08                     # basis F = entry - 8%
STOP_X_ATR = 2.0                      # basis X = entry - 2 x ATR14  (PRIMARY)
STOP_A_K = 0.99                       # basis A = P_low x 0.99 (bake-off continuity)
AVWAP_LOOKBACK = 126                  # D1 anchor: the decline's 126d closing-high date
POC_WINDOW, POC_BINS = 126, 24        # D2/D3 volume profile geometry
POC_TOL = 0.01                        # poc_retest_hold default tolerance (engine default)
ABSORB_BACK = 20                      # D4 window [T-20, T]
ABSORB_BAND = 1.02                    # D4: sessions whose low <= P_low x 1.02
QUIET_BACK = 15                       # D5 window [T-15, T]
P1_WAIT = 5                           # P1: first session >= T+5
P1_CHASE_CAP = 1.05                   # P1: ... and close <= fire-close x 1.05
P1_SEARCH_MAX = FWD_MAX               # P1 search bound (the label horizon; documented)
P2_WINDOW = 15                        # P2: confirmed r3 swing low within [T, T+15]
P2_HOLD = 0.98                        # P2: ... holding above P_low x 0.98
PIVOT_R = 3                           # r3 swing low radius
LOOKBACK_LOW = 45                     # P_low window, inherited from the plane
LIVE_PP, SUGGESTIVE_PP = 0.10, 0.05   # §5 read criteria
MIN_CELL_N = 20                       # an extreme cell thinner than this gets no verdict
MIN_CELL_NAMES = 20                   # per-name-first spread floor
QUINTILES = 5                         # the mandatory entry_vs_low conditioning
BOOT_B, BOOT_SEED = 500, 20260811     # month-cluster bootstrap
SESSIONS_PER_YEAR = 252.0
EXEMPLARS = ("STLD", "NEM")
EXEMPLAR_FROM = "2026-01-01"

DEF_EPISODES = ("/private/tmp/claude-501/-Users-chriswong-Documents-Cluade-Macro-Dashboard-"
                "-claude-worktrees-stoch-rsi-macd-confluence-2959db/"
                "de6f64ca-9a78-4c79-aa23-591e0d75d36c/scratchpad/"
                "episodes_305990306ef.parquet")
DEF_PRICES = "/Users/chriswong/actions-runner-2/_work/macro/macro/data/baskets/ohlcv"
DEF_DARK_DEEP = ("/Users/chriswong/actions-runner-2/_work/macro/macro/data/"
                 "finra_short_volume/panel_deep.parquet")
DEF_DARK_WIDE = ("/Users/chriswong/actions-runner-2/_work/macro/macro/data/"
                 "finra_short_volume/panel.parquet")
DEF_OPTIONS = "/Users/chriswong/actions-runner-2/_work/macro/macro/data/options_flow"

DEVIATIONS: list[str] = []
NOTES: list[str] = []
TABLES: dict[str, dict] = {}


def deviate(m: str) -> None:
    if m not in DEVIATIONS:
        DEVIATIONS.append(m)


def note(m: str) -> None:
    if m not in NOTES:
        NOTES.append(m)


# ------------------------------------------------------------------ plain-text tables
class Table:
    def __init__(self, key: str, title: str, columns: list[str], notes: str = ""):
        self.key, self.title, self.columns, self.notes = key, title, columns, notes
        self.rows: list[list] = []

    def add(self, *vals) -> None:
        self.rows.append(list(vals))

    def emit(self) -> None:
        TABLES[self.key] = {"title": self.title, "columns": self.columns,
                            "rows": [[_j(v) for v in r] for r in self.rows],
                            "notes": self.notes}
        print()
        print(f"### {self.key} — {self.title}")
        if self.notes:
            print(f"    ({self.notes})")
        if not self.rows:
            print("    (no rows)")
            return
        cells = [[_s(v) for v in r] for r in self.rows]
        w = [max(len(self.columns[i]), *(len(r[i]) for r in cells))
             for i in range(len(self.columns))]
        print("  " + "  ".join(c.ljust(w[i]) for i, c in enumerate(self.columns)))
        print("  " + "  ".join("-" * w[i] for i in range(len(self.columns))))
        for r in cells:
            print("  " + "  ".join(r[i].ljust(w[i]) for i in range(len(self.columns))))


def _s(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        if not np.isfinite(v):
            return "-"
        return f"{v:.4g}" if abs(v) >= 1000 else f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def _j(v):
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, float) and not np.isfinite(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return str(pd.Timestamp(v).date())
    if isinstance(v, dict):
        return {k: _j(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_j(x) for x in v]
    return v


def pct(x) -> float | None:
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(100 * x, 2)


def med(vals) -> float | None:
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return float(np.median(v)) if v else None


def mean_(vals) -> float | None:
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return float(np.mean(v)) if v else None


def rate(flags) -> float | None:
    v = [bool(x) for x in flags if x is not None and not (isinstance(x, float) and np.isnan(x))]
    return float(np.mean(v)) if v else None


def git_sha(repo: Path, ref: str = "HEAD") -> str | None:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", ref],
                              capture_output=True, text=True, timeout=60).stdout.strip() or None
    except Exception:
        return None


# ------------------------------------------------------------------ price + panel loaders
def load_ohlc(ticker: str, root: Path) -> pd.DataFrame | None:
    p = root / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:
        return None
    if not {"high", "low", "close", "volume"}.issubset(df.columns):
        return None
    df = df.copy()
    df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df.dropna(subset=["close", "high", "low"])


def load_darkpool(deep: Path, wide: Path) -> tuple[dict[str, pd.DataFrame], dict]:
    """FINRA off-exchange daily volume, deep panel UNION wide panel (deep wins on overlap)."""
    frames, meta = [], {}
    for tag, path in (("panel_deep", deep), ("panel", wide)):
        if not path.exists():
            meta[tag] = None
            continue
        d = pd.read_parquet(path)
        d["date"] = pd.DatetimeIndex(d["date"]).tz_localize(None).normalize()
        d["_src"] = tag
        meta[tag] = {"rows": int(len(d)), "tickers": int(d["ticker"].nunique()),
                     "first": str(d["date"].min().date()), "last": str(d["date"].max().date())}
        frames.append(d[["date", "ticker", "total_vol", "_src"]])
    if not frames:
        return {}, meta
    allp = pd.concat(frames, ignore_index=True)
    # deep panel wins where both cover the same (ticker, date): it is the longer-baseline feed
    allp["_rank"] = (allp["_src"] == "panel_deep").astype(int)
    allp = (allp.sort_values(["ticker", "date", "_rank"])
                .drop_duplicates(["ticker", "date"], keep="last"))
    out = {t: g.set_index("date")[["total_vol"]].sort_index()
           for t, g in allp.groupby("ticker")}
    return out, meta


def load_options(root: Path, ticker: str) -> pd.Series | None:
    p = root / f"summary_{ticker}.parquet"
    if not p.exists():
        return None
    try:
        d = pd.read_parquet(p)
    except Exception:
        return None
    if "net_premium_mn" not in d.columns:
        return None
    s = d["net_premium_mn"].astype("float64")
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


# ------------------------------------------------------------------ §1 labels
def label_row(nd: dict, T: int, stop: float | None) -> dict:
    """STOPPED (low <= stop before T+42) vs SURVIVED; r_mult recomputed for THIS basis."""
    n, lo, cl = nd["n"], nd["low"], nd["close"]
    c0 = cl[T]
    out = {"stop": stop}
    fwd = n - 1 - T
    if stop is None or stop <= 0 or stop >= c0 or fwd < MIN_FWD:
        out.update(stopped=None, r_mult=None, truncated=bool(fwd < MIN_FWD))
        return out
    end = min(T + FWD_MAX, n - 1)
    stopped = bool(np.any(lo[T + 1: end + 1] <= stop))
    risk = (c0 - stop) / c0
    fwd_ret = cl[end] / c0 - 1.0
    out.update(stopped=stopped, truncated=False,
               r_mult=(-1.0 if stopped else float(fwd_ret / risk)),
               risk_pct=float(risk), window=int(end - T))
    return out


# ------------------------------------------------------------------ §2 deep battery
def deep_features(nd: dict, T: int, p_low: float, avwap_cache: dict) -> dict:
    df, cl, lo, hi, vol = nd["df"], nd["close"], nd["low"], nd["high"], nd["vol"]
    f: dict = {}

    # D1 — AVWAP anchored at the decline's 126d closing-high date, read at T
    a = max(0, T - AVWAP_LOOKBACK)
    anchor = a + int(np.nanargmax(cl[a: T + 1]))
    key = anchor
    if key not in avwap_cache:
        avwap_cache[key] = anchored_vwap(df, int(anchor)).to_numpy(dtype="float64")
    av = avwap_cache[key][T]
    f["d1_avwap_above"] = bool(cl[T] > av) if np.isfinite(av) else None
    f["d1_avwap_dist"] = float(cl[T] / av - 1.0) if np.isfinite(av) and av > 0 else None
    f["d1_anchor_date"] = nd["idx"][anchor]

    # D2 — did the washout low land on the volume point-of-control (the CN "chip peak")
    poc = nd["poc"][T]
    f["d2_poc_dist"] = (float(abs(p_low / poc - 1.0))
                        if np.isfinite(poc) and poc > 0 and np.isfinite(p_low) else None)
    f["d2_poc"] = float(poc) if np.isfinite(poc) else None

    # D3 — POC retest-hold bullish event, as of T (engine flag, bar-specific by construction)
    f["d3_poc_hold"] = bool(nd["poc_hold"][T])

    # D4 — absorption share: [T-20, T] volume transacted on sessions at/near the low
    b = max(0, T - ABSORB_BACK)
    v = vol[b: T + 1]
    tot = float(np.nansum(v))
    if tot > 0 and np.isfinite(p_low):
        at_low = lo[b: T + 1] <= p_low * ABSORB_BAND
        f["d4_absorption"] = float(np.nansum(np.where(at_low, v, 0.0)) / tot)
    else:
        f["d4_absorption"] = None

    # D5 — quiet accumulation: rank-corr(volume, |daily return|) over [T-15, T]
    q = max(1, T - QUIET_BACK)
    rv = vol[q: T + 1]
    rr = np.abs(cl[q: T + 1] / cl[q - 1: T] - 1.0)
    ok = np.isfinite(rv) & np.isfinite(rr)
    if ok.sum() >= 8:
        f["d5_quiet"] = _spearman(rv[ok], rr[ok])
    else:
        f["d5_quiet"] = None
    return f


def _spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    sa, sb = ra.std(), rb.std()
    if sa == 0 or sb == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


# ------------------------------------------------------------------ §4 policies
def policies(nd: dict, T: int, p_low: float) -> dict:
    """P0 / P1 / P2 as DECISION POLICIES over the same fire set, graded on basis X."""
    n, cl, lo, atr = nd["n"], nd["close"], nd["low"], nd["atr"]
    c0 = cl[T]
    out: dict = {}

    def grade(s: int | None) -> dict:
        if s is None or s >= n:
            return {"entered": False, "entry_pos": None, "entry_close": None,
                    "stopped": None, "r_mult": None, "truncated": False,
                    "entry_vs_low": None}
        st = cl[s] - STOP_X_ATR * atr[s] if np.isfinite(atr[s]) else None
        r = label_row(nd, s, st)
        pl = float(np.nanmin(lo[max(0, s - LOOKBACK_LOW): s + 1]))
        return {"entered": True, "entry_pos": int(s), "entry_close": float(cl[s]),
                "stopped": r["stopped"], "r_mult": r["r_mult"],
                "truncated": bool(r.get("truncated")),
                "entry_vs_low": (float(cl[s] / pl - 1.0) if np.isfinite(pl) and pl > 0
                                 else None)}

    out["P0"] = grade(T)

    # P1 wait-k: first session >= T+5 with no stop touch printed and no chase past +5%
    stop_x = c0 - STOP_X_ATR * atr[T] if np.isfinite(atr[T]) else None
    s1 = None
    if stop_x is not None:
        for s in range(T + P1_WAIT, min(T + P1_SEARCH_MAX, n - 1) + 1):
            if np.any(lo[T + 1: s + 1] <= stop_x):
                break                                  # the stop already printed -> never enter
            if cl[s] <= c0 * P1_CHASE_CAP:
                s1 = s
                break
    out["P1"] = grade(s1)

    # P2 evidence-confirm: knowability close of the first confirmed r3 swing low in
    # [T, T+15] whose pivot low holds above P_low x 0.98
    s2 = None
    for p in range(T, min(T + P2_WINDOW, n - 1 - PIVOT_R) + 1):
        if p - PIVOT_R < 0:
            continue
        w = lo[p - PIVOT_R: p + PIVOT_R + 1]
        if not np.isfinite(w).all():
            continue
        if lo[p] < np.min(np.delete(w, PIVOT_R)) and lo[p] > p_low * P2_HOLD:
            s2 = p + PIVOT_R
            break
    out["P2"] = grade(s2)

    # P1v (§R8b) — the SAME entry as P1 but the fire's own risk contract retained: stop stays
    # at the fire-date entry - 2xATR14(T) and the horizon stays the FIRE's T+42, so P1 is
    # compared with P0 on one aligned clock instead of a later, longer one.
    end = min(T + FWD_MAX, n - 1)
    if s1 is None or stop_x is None or n - 1 - T < MIN_FWD or s1 >= end:
        out["P1v"] = {"entered": False, "entry_pos": None, "entry_close": None,
                      "stopped": None, "r_mult": None, "risk_pct": None}
    else:
        risk = (cl[s1] - stop_x) / cl[s1]
        if risk <= 0:
            out["P1v"] = {"entered": True, "entry_pos": int(s1),
                          "entry_close": float(cl[s1]), "stopped": None, "r_mult": None,
                          "risk_pct": None}
        else:
            hit = bool(np.any(lo[s1 + 1: end + 1] <= stop_x))
            out["P1v"] = {"entered": True, "entry_pos": int(s1),
                          "entry_close": float(cl[s1]), "stopped": hit,
                          "r_mult": (-1.0 if hit else float((cl[end] / cl[s1] - 1.0) / risk)),
                          "risk_pct": float(risk)}
    return out


# ------------------------------------------------------------------ §3 thin battery
def thin_features(part: pd.Series | None, opts: pd.Series | None,
                  known_date: pd.Timestamp) -> dict:
    """T1/T2/T3 stamped at the LAST session <= T-1 (published same evening -> knowable at
    T+1 open per charter §3, so a decision at close T may not read session T)."""
    f = {"t1_part_z": None, "t2_streak": None, "t3_prem_z": None, "t1_obs": 0}
    if part is not None and len(part):
        h = part[part.index <= known_date]
        if len(h) >= Z_MIN_OBS + 1:
            u = usable_history(h)
            f["t1_obs"] = int(len(u))
            f["t1_part_z"] = trailing_z(u, window=Z_WINDOW, min_obs=Z_MIN_OBS)
            if len(u) >= 5:
                f["t2_streak"] = int(streak_above_norm(u, window=STREAK_WINDOW))
    if opts is not None and len(opts):
        h = opts[opts.index <= known_date]
        if len(h) >= Z_MIN_OBS + 6:
            roll = h.rolling(6).sum().dropna()      # charter window [T-5, T], knowable tail
            if len(roll) >= Z_MIN_OBS + 1:
                f["t3_prem_z"] = trailing_z(roll, window=Z_WINDOW, min_obs=Z_MIN_OBS)
    return f


# ------------------------------------------------------------------ §5 ledger machinery
def cells_for(d: pd.DataFrame, key: str, kind: str):
    v = d[key]
    if v.notna().sum() < 3 * MIN_CELL_N:
        return None
    if kind == "b":
        b = v.dropna().astype(bool)
        if b.nunique() < 2:
            return None
        m = v.notna()
        return [("False", m & (v == False)), ("True", m & (v == True))]  # noqa: E712
    try:
        q = v.quantile([1 / 3, 2 / 3]).to_numpy()
    except Exception:
        return None
    if not np.isfinite(q).all() or q[0] >= q[1]:
        return None
    return [(f"bottom (<= {q[0]:.4g})", v <= q[0]),
            ("middle", (v > q[0]) & (v <= q[1])),
            (f"top (> {q[1]:.4g})", v > q[1])]


def fs_rate(d: pd.DataFrame, mask, col: str) -> tuple:
    part = d[mask & d[col].notna()]
    if part.empty:
        return None, 0, 0
    return float(part[col].astype(bool).mean()), len(part), int(part["ticker"].nunique())


def pn_rate(d: pd.DataFrame, mask, col: str) -> tuple:
    part = d[mask & d[col].notna()]
    if part.empty:
        return None, 0
    per = part.groupby("ticker")[col].apply(lambda s: s.astype(bool).mean())
    return float(per.mean()), int(per.size)


def boot_ci(d: pd.DataFrame, lo_m, hi_m, col: str) -> tuple:
    part = d[(lo_m | hi_m) & d[col].notna()].copy()
    if part.empty:
        return None, None
    part["_hi"] = hi_m.reindex(part.index).fillna(False).to_numpy()
    part["_fs"] = part[col].astype(bool).to_numpy()
    part["_m"] = part["date"].dt.to_period("M").astype(str)
    groups = [g[["_hi", "_fs"]].to_numpy() for _, g in part.groupby("_m")]
    if len(groups) < 4:
        return None, None
    rng = np.random.default_rng(BOOT_SEED)
    draws = []
    for _ in range(BOOT_B):
        pick = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        h, fsv = pick[:, 0].astype(bool), pick[:, 1].astype(bool)
        if h.sum() == 0 or (~h).sum() == 0:
            continue
        draws.append(fsv[h].mean() - fsv[~h].mean())
    if len(draws) < BOOT_B // 4:
        return None, None
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def quintile_spread(d: pd.DataFrame, key: str, kind: str, col: str) -> tuple:
    g = d[d[col].notna() & d["entry_vs_low"].notna() & d[key].notna()]
    if len(g) < QUINTILES * 3 * MIN_CELL_N:
        return None, 0
    try:
        q = pd.qcut(g["entry_vs_low"], QUINTILES, labels=False, duplicates="drop")
    except Exception:
        return None, 0
    sps = []
    for qi in sorted(set(q.dropna().astype(int))):
        sub = g[q == qi]
        cells = cells_for(sub, key, kind)
        if cells is None:
            continue
        a, b = fs_rate(sub, cells[0][1], col), fs_rate(sub, cells[-1][1], col)
        if a[0] is None or b[0] is None or min(a[1], b[1]) < MIN_CELL_N // 2:
            continue
        sps.append(b[0] - a[0])
    return (mean_(sps), len(sps)) if sps else (None, 0)


def spread_on(d: pd.DataFrame, key: str, kind: str, col: str) -> float | None:
    cells = cells_for(d, key, kind)
    if cells is None:
        return None
    a, b = fs_rate(d, cells[0][1], col), fs_rate(d, cells[-1][1], col)
    if a[0] is None or b[0] is None or min(a[1], b[1]) < MIN_CELL_N:
        return None
    return b[0] - a[0]


FEATURE_SPEC = [
    ("d1_avwap_above", "D1a AVWAP reclaim — close(T) above the 126d-high-anchored VWAP", "b",
     "deep"),
    ("d1_avwap_dist", "D1b AVWAP distance — close(T)/AVWAP - 1", "t", "deep"),
    ("d2_poc_dist", "D2  flush-on-shelf — |P_low / rolling_poc(126,24) - 1|", "t", "deep"),
    ("d3_poc_hold", "D3  POC retest-hold bullish flag at T", "b", "deep"),
    ("d4_absorption", "D4  absorption share — [T-20,T] volume on sessions at/near P_low", "t",
     "deep"),
    ("d5_quiet", "D5  quiet accumulation — rank-corr(volume, |ret|) over [T-15,T]", "t",
     "deep"),
    ("t1_part_z", "T1  dark pool — off-exchange participation_z (<= T-1)", "t", "thin"),
    ("t2_streak", "T2  dark pool — sessions above own norm, streak (<= T-1)", "t", "thin"),
    ("t3_prem_z", "T3  options — signed net-premium z over the charter window (<= T-1)", "t",
     "thin"),
    ("entry_vs_low", "REF entry_vs_low (the stop-width tell; NOT a footprint feature)", "t",
     "ref"),
]


def ledger(d: pd.DataFrame, tier: str, key_prefix: str) -> list[dict]:
    tb = Table(f"{key_prefix}",
               f"§5 FEATURE LEDGER — {tier} battery, stop-out rate by cell "
               f"(primary basis X = entry - 2xATR14)",
               ["feature", "cells (low -> high)", "n per cell", "names per cell",
                "stop-out% per cell", "spread pp (X)", "95% CI pp", "per-name-first pp",
                "early-half pp", "late-half pp", "median entry_vs_low lo -> hi",
                "within-quintile pp", "spread pp (A)", "spread pp (F)", "READ"],
               "LIVE = |spread| >= 10pp on X, same sign in BOTH halves AND on bases A and F; "
               "SUGGESTIVE = >= 5pp with the same stability; else null. The thin battery is "
               "capped at PROBE by charter §3 — a window this short can never mint LIVE. "
               "The entry_vs_low columns are the stop-width tell: basis X is entry-anchored, "
               "so a feature that moves only with entry_vs_low is not being paid for by the "
               "stop here, but the reader should still see it.")
    rows = []
    for key, label, kind, group in FEATURE_SPEC:
        if group != tier:
            continue
        cells = cells_for(d, key, kind)
        if cells is None:
            n_ok = int(d[key].notna().sum()) if key in d.columns else 0
            tb.add(label, f"(degenerate / too few rows: n={n_ok})", "-", "-", "-", None, "-",
                   None, None, None, "-", None, None, None, "no data")
            rows.append({"feature": key, "read": "degenerate", "n": n_ok})
            continue
        cr, cn, ck = [], [], []
        for _, m in cells:
            r, n, k = fs_rate(d, m, "stopped_X")
            cr.append(r)
            cn.append(n)
            ck.append(k)
        lo_m, hi_m = cells[0][1], cells[-1][1]
        sp = None if cr[0] is None or cr[-1] is None else cr[-1] - cr[0]
        seen = d[key].notna()
        smid = d.loc[seen, "date"].median()
        early, late = seen & (d["date"] <= smid), seen & (d["date"] > smid)
        e = (fs_rate(d[early], lo_m[early], "stopped_X"),
             fs_rate(d[early], hi_m[early], "stopped_X"))
        l = (fs_rate(d[late], lo_m[late], "stopped_X"),
             fs_rate(d[late], hi_m[late], "stopped_X"))
        e_sp = None if e[0][0] is None or e[1][0] is None else e[1][0] - e[0][0]
        l_sp = None if l[0][0] is None or l[1][0] is None else l[1][0] - l[0][0]
        pl, npl = pn_rate(d, lo_m, "stopped_X")
        ph, nph = pn_rate(d, hi_m, "stopped_X")
        pn_sp = (ph - pl if pl is not None and ph is not None
                 and min(npl, nph) >= MIN_CELL_NAMES else None)
        ci = boot_ci(d, lo_m, hi_m, "stopped_X")
        wq, nq = quintile_spread(d, key, kind, "stopped_X")
        sp_a = spread_on(d, key, kind, "stopped_A")
        sp_f = spread_on(d, key, kind, "stopped_F")
        ev_lo, ev_hi = (med(d.loc[lo_m, "entry_vs_low"].tolist()),
                        med(d.loc[hi_m, "entry_vs_low"].tolist()))
        thin = min(cn[0], cn[-1]) < MIN_CELL_N
        halves_ok = (e_sp is not None and l_sp is not None and sp is not None
                     and e_sp != 0 and l_sp != 0
                     and np.sign(e_sp) == np.sign(l_sp) == np.sign(sp))
        bases_ok = (sp_a is not None and sp_f is not None and sp is not None
                    and np.sign(sp_a) == np.sign(sp_f) == np.sign(sp))
        if tier == "thin":
            read = "PROBE (charter cap)"
        elif thin or sp is None:
            read = "thin — no verdict"
        elif abs(sp) >= LIVE_PP and halves_ok and bases_ok:
            read = "LIVE"
        elif abs(sp) >= SUGGESTIVE_PP and halves_ok and bases_ok:
            read = "SUGGESTIVE"
        else:
            read = "null"
        tb.add(label, " | ".join(c[0] for c in cells), " | ".join(str(x) for x in cn),
               " | ".join(str(x) for x in ck),
               " | ".join("-" if r is None else f"{100 * r:.1f}" for r in cr),
               pct(sp), "-" if ci[0] is None else f"{100 * ci[0]:.1f} .. {100 * ci[1]:.1f}",
               pct(pn_sp), pct(e_sp), pct(l_sp),
               "-" if ev_lo is None or ev_hi is None else f"{ev_lo:.3f} -> {ev_hi:.3f}",
               pct(wq), pct(sp_a), pct(sp_f), read)
        rows.append({"feature": key, "label": label, "kind": kind, "tier": tier,
                     "cells": [c[0] for c in cells], "n": cn, "names": ck,
                     "stop_out_rate": cr, "spread_X": sp, "ci95": list(ci),
                     "per_name_spread": pn_sp, "early": e_sp, "late": l_sp,
                     "spread_A": sp_a, "spread_F": sp_f, "within_quintile": wq,
                     "entry_vs_low_lo": ev_lo, "entry_vs_low_hi": ev_hi, "read": read})
    tb.emit()
    return rows


# ------------------------------------------------------------------ §R8 review appendix
def _sumr(x: pd.Series) -> float | None:
    v = x.dropna().to_numpy(dtype="float64")
    return float(np.sum(v)) if v.size else None


def run_review_appendix(d: pd.DataFrame, name_years: float) -> dict:
    """§R8 — the phase-2 review's three explanation-level receipts, frozen as tables.

    R3 shows P1/P2 losing per-name-year R against P0 but cannot say WHERE the loss comes
    from: the fires a policy skipped, the fires it entered later, or the horizon it was
    graded on. These tables decompose exactly that, and price the D2 result in ATR units."""
    out: dict = {}
    g0 = d["P0_stopped"].notna()

    # ---- R8a: where does the policy's R go? ------------------------------------------
    ta = Table("R8a", "§R8 POLICY DECOMPOSITION — skipped fires vs common fires vs the "
                      "chase cap",
               ["policy", "block", "n", "names", "P0 stop-out%", "P0 mean R", "P0 sum R",
                "policy sum R", "delta R (policy - P0)", "R per name-year"],
               "P0 enters every fire, so a policy's per-name-year R gap is exactly the R it "
               "declined on SKIPPED fires plus the R it gained or lost by entering the "
               "COMMON fires later. Blocks (a) and (b) partition the gap; block (c) prices "
               "the chase cap specifically.")
    r8a: dict = {}
    for pk in ("P1", "P2"):
        ent = d[f"{pk}_entered"].astype(bool)
        gp = d[f"{pk}_stopped"].notna()
        skipped = (~ent) & g0
        common = ent & g0 & gp
        s = d[skipped]
        ta.add(pk, "(a) skipped by the policy, graded by P0", len(s),
               int(s["ticker"].nunique()), pct(rate(s["P0_stopped"].tolist())),
               mean_(s["P0_r_mult"].tolist()), _sumr(s["P0_r_mult"]), None, None,
               round((_sumr(s["P0_r_mult"]) or 0.0) / name_years, 4) if name_years else None)
        c = d[common]
        p0s, pks = _sumr(c["P0_r_mult"]), _sumr(c[f"{pk}_r_mult"])
        ta.add(pk, "(b) entered by BOTH, graded by both", len(c),
               int(c["ticker"].nunique()), pct(rate(c["P0_stopped"].tolist())),
               mean_(c["P0_r_mult"].tolist()), p0s, pks,
               None if p0s is None or pks is None else pks - p0s,
               round(((pks or 0.0) - (p0s or 0.0)) / name_years, 4) if name_years else None)
        r8a[pk] = {"skipped_n": len(s), "skipped_sum_R": _sumr(s["P0_r_mult"]),
                   "common_n": len(c), "common_P0_sum_R": p0s, "common_policy_sum_R": pks}
    # (c) the chase cap, priced: what P1 declined, split by what P0 then did with it
    ent1 = d["P1_entered"].astype(bool)
    sk = d[(~ent1) & g0]
    for lab, part in (("(c) skipped & P0 STOPPED (avoided losses)",
                       sk[sk["P0_stopped"].astype(bool)]),
                      ("(c) skipped & P0 SURVIVED (forgone runaways)",
                       sk[~sk["P0_stopped"].astype(bool)])):
        ta.add("P1", lab, len(part), int(part["ticker"].nunique()),
               pct(rate(part["P0_stopped"].tolist())), mean_(part["P0_r_mult"].tolist()),
               _sumr(part["P0_r_mult"]), None, None,
               round((_sumr(part["P0_r_mult"]) or 0.0) / name_years, 4)
               if name_years else None)
    ta.emit()
    out["R8a"] = TABLES["R8a"]

    # ---- R8b: P1 on the FIRE's own risk contract + the fair same-set comparison --------
    tb = Table("R8b", "§R8 P1 VARIANT — same entry, the FIRE's stop and the FIRE's horizon "
                      "(plus the fair common-set P0 vs P1)",
               ["variant", "n entered", "names", "graded", "stop-out%", "mean R",
                "median R", "sum R", "R per name-year", "vs P0 on the common set"],
               "the shipped P1 re-anchors BOTH the stop and the clock to its later entry, so "
               "R3's comparison mixes a policy effect with a horizon effect. P1v holds the "
               "fire's stop (entry-2xATR14 at T) and the fire's T+42 fixed, changing only "
               "WHEN the position is taken.")
    gv = d["P1v_stopped"].notna()
    ent1g = ent1 & g0
    v = d[gv]
    rv = v["P1v_r_mult"].dropna().to_numpy(dtype="float64")
    tb.add("P1v (fire stop, fire horizon)", int(d["P1v_entered"].astype(bool).sum()),
           int(v["ticker"].nunique()), len(v), pct(rate(v["P1v_stopped"].tolist())),
           float(np.mean(rv)) if rv.size else None,
           float(np.median(rv)) if rv.size else None, _sumr(v["P1v_r_mult"]),
           round((_sumr(v["P1v_r_mult"]) or 0.0) / name_years, 4) if name_years else None,
           None)
    both = d[gv & g0]
    p0s, pvs = _sumr(both["P0_r_mult"]), _sumr(both["P1v_r_mult"])
    tb.add("... P0 on that SAME set", len(both), int(both["ticker"].nunique()), len(both),
           pct(rate(both["P0_stopped"].tolist())), mean_(both["P0_r_mult"].tolist()),
           med(both["P0_r_mult"].tolist()), p0s,
           round((p0s or 0.0) / name_years, 4) if name_years else None,
           None if p0s is None or pvs is None else round(pvs - p0s, 4))
    # the fair same-set comparison under the SHIPPED spec
    cs = d[ent1g & d["P1_stopped"].notna()]
    tb.add("SHIPPED P1 on the common set", len(cs), int(cs["ticker"].nunique()), len(cs),
           pct(rate(cs["P1_stopped"].tolist())), mean_(cs["P1_r_mult"].tolist()),
           med(cs["P1_r_mult"].tolist()), _sumr(cs["P1_r_mult"]),
           round((_sumr(cs["P1_r_mult"]) or 0.0) / name_years, 4) if name_years else None,
           None)
    p0c = _sumr(cs["P0_r_mult"])
    tb.add("... P0 on that SAME common set", len(cs), int(cs["ticker"].nunique()), len(cs),
           pct(rate(cs["P0_stopped"].tolist())), mean_(cs["P0_r_mult"].tolist()),
           med(cs["P0_r_mult"].tolist()), p0c,
           round((p0c or 0.0) / name_years, 4) if name_years else None,
           None if p0c is None else round((_sumr(cs["P1_r_mult"]) or 0.0) - p0c, 4))
    tb.emit()
    out["R8b"] = TABLES["R8b"]

    # ---- R8c: the D2 / D1a result priced in ATR units ---------------------------------
    tc = Table("R8c", "§R8 MECHANISM — stop WIDTH by cell for the two features that moved",
               ["feature", "cell", "n", "names", "median ATR14 (% of entry)",
                "median 2xATR stop width (% of entry)", "median entry_vs_low",
                "stop-out% (X)"],
               "basis X is entry-anchored but not width-constant: a cell whose names carry a "
               "wider ATR gets a wider stop and is mechanically harder to touch. This is the "
               "stop-width tell in the units the stop is actually set in.")
    dd = d.copy()
    dd["_atr_pct"] = dd["atr14"] / dd["close"]
    dd["_width"] = STOP_X_ATR * dd["_atr_pct"]
    for key, kind in (("d2_poc_dist", "t"), ("d1_avwap_above", "b")):
        cells = cells_for(dd, key, kind)
        if cells is None:
            tc.add(key, "(degenerate)", 0, 0, None, None, None, None)
            continue
        label = dict((k, lb) for k, lb, _, _ in FEATURE_SPEC)[key]
        for cname, cmask in cells:
            part = dd[cmask]
            tc.add(label, cname, len(part), int(part["ticker"].nunique()),
                   med(part["_atr_pct"].tolist()), med(part["_width"].tolist()),
                   med(part["entry_vs_low"].tolist()),
                   pct(rate(part["stopped_X"].tolist())))
    tc.emit()
    out["R8c"] = TABLES["R8c"]
    out["r8a"] = r8a
    return out


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--episodes", default=DEF_EPISODES)
    ap.add_argument("--prices", default=DEF_PRICES)
    ap.add_argument("--darkpool-deep", default=DEF_DARK_DEEP)
    ap.add_argument("--darkpool-wide", default=DEF_DARK_WIDE)
    ap.add_argument("--options", default=DEF_OPTIONS)
    ap.add_argument("--tickers", default="", help="comma list; debug subset run")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent
                                         / "footprint_picker_results.json"))
    ap.add_argument("--review-appendix", dest="review", action="store_true", default=True,
                    help="run the §R8 review appendix (default)")
    ap.add_argument("--no-review-appendix", dest="review", action="store_false")
    args = ap.parse_args()
    t_start = time.time()

    print("=" * 100)
    print("FOOTPRINT PICKER — executing FOOTPRINT_PICKER_PREREG_2026-08-11.md §1-§5")
    print("=" * 100)

    # ---------------------------------------------- union admission set (frozen in-script)
    ep = pd.read_parquet(args.episodes)
    ep["date"] = pd.DatetimeIndex(ep["date"])
    addon_n = int(ep["addon"].astype(bool).sum())
    pan = ep[~ep["addon"].astype(bool)]
    c1 = pan[pan["construction"] == "C1"]
    c2 = pan[pan["construction"] == "C2r"]
    c1pos = {t: np.sort(g["pos"].to_numpy()) for t, g in c1.groupby("ticker")}
    keep = []
    for t, p in zip(c2["ticker"], c2["pos"]):
        a = c1pos.get(t)
        keep.append(True if a is None or not len(a) else bool(np.min(np.abs(a - p)) > UNION_GAP))
    dot_only = c2[np.array(keep, dtype=bool)]
    union = pd.concat([c1.assign(lane="C1"), dot_only.assign(lane="C2r_dot_only")],
                      ignore_index=True)
    deviate("Pooled tables use the PANEL only (addon=False). The prereg does not mention the "
            f"bake-off's add-on exemplars (HL, UEC; {addon_n} episode rows across all lanes), "
            "but the bake-off substrate law makes them traces that are never pooled, and "
            "they carry no store lane. Both exemplar names (STLD, NEM) are panel names, so "
            "the §5 exemplar gate is unaffected.")
    subset = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]
    if subset:
        union = union[union["ticker"].isin(subset)]
    print(f"\nunion admission set: C1={len(c1)} + C2r dot-only={len(dot_only)} "
          f"(of {len(c2)} C2r) = {len(union)} episodes, "
          f"{union['ticker'].nunique()} names")

    # ---------------------------------------------- substrate
    prices = Path(args.prices)
    dark, dark_meta = load_darkpool(Path(args.darkpool_deep), Path(args.darkpool_wide))
    opt_root = Path(args.options)
    opt_files = sorted(opt_root.glob("summary_*.parquet"))
    print(f"substrate: darkpool {dark_meta} | options_flow files={len(opt_files)}")

    rows: list[dict] = []
    name_years = 0.0
    price_meta: dict[str, dict] = {}
    skipped: list[str] = []

    for ticker, g in union.groupby("ticker"):
        df = load_ohlc(ticker, prices)
        if df is None or len(df) < 300:
            skipped.append(ticker)
            continue
        idx = df.index
        nd = {
            "df": df, "idx": idx, "n": len(idx),
            "close": df["close"].to_numpy(dtype="float64"),
            "low": df["low"].to_numpy(dtype="float64"),
            "high": df["high"].to_numpy(dtype="float64"),
            "vol": df["volume"].to_numpy(dtype="float64") if "volume" in df else
                   np.full(len(idx), np.nan),
            "atr": wilder_atr(df["high"], df["low"], df["close"], 14).to_numpy(dtype="float64"),
            "poc": rolling_poc(df, window=POC_WINDOW, bins=POC_BINS).to_numpy(dtype="float64"),
            "poc_hold": poc_retest_hold(df, window=POC_WINDOW, bins=POC_BINS,
                                        tol=POC_TOL).to_numpy(),
        }
        price_meta[ticker] = {"first": str(idx[0].date()), "last": str(idx[-1].date()),
                              "rows": int(len(idx))}
        pos_of = {d: i for i, d in enumerate(idx)}
        part = None
        if ticker in dark:
            j = dark[ticker].join(df["volume"].rename("cons"), how="inner")
            j = j[j["cons"] > 0]
            if not j.empty:
                part = (j["total_vol"] / j["cons"]).dropna()
        opts = load_options(opt_root, ticker)
        avwap_cache: dict = {}
        name_years += max(0, len(idx) - 1) / SESSIONS_PER_YEAR

        for _, e in g.iterrows():
            T = pos_of.get(pd.Timestamp(e["date"]))
            if T is None or T < LOOKBACK_LOW:
                continue
            c0 = nd["close"][T]
            p_low = float(np.nanmin(nd["low"][T - LOOKBACK_LOW: T + 1]))
            atrT = nd["atr"][T]
            r: dict = {"ticker": ticker, "date": pd.Timestamp(e["date"]), "pos": int(T),
                       "lane": e["lane"], "close": float(c0), "p_low": p_low,
                       "entry_vs_low": float(c0 / p_low - 1.0) if p_low > 0 else None,
                       "atr14": float(atrT) if np.isfinite(atrT) else None}
            bases = {"A": p_low * STOP_A_K,
                     "F": c0 * (1.0 - STOP_F_PCT),
                     "X": (c0 - STOP_X_ATR * atrT) if np.isfinite(atrT) else None}
            for b, lvl in bases.items():
                lab = label_row(nd, T, lvl)
                r[f"stop_{b}"] = lab["stop"]
                r[f"stopped_{b}"] = lab["stopped"]
                r[f"r_mult_{b}"] = lab["r_mult"]
                r[f"trunc_{b}"] = lab.get("truncated")
                if b == "X":
                    r["risk_pct_X"] = lab.get("risk_pct")
            r.update(deep_features(nd, T, p_low, avwap_cache))
            known = idx[T - 1]
            r.update(thin_features(part, opts, known))
            pol = policies(nd, T, p_low)
            for pk, pv in pol.items():
                for f, v in pv.items():
                    r[f"{pk}_{f}"] = v
            rows.append(r)

    d = pd.DataFrame(rows)
    if skipped:
        note(f"union names with no usable price series (dropped): {sorted(skipped)}")
    print(f"scored {len(d)} union episodes across {d['ticker'].nunique()} names "
          f"in {time.time() - t_start:.0f}s")

    # ---------------------------------------------- R0 provenance + gates
    t0 = Table("R0", "Substrate, provenance and acceptance gates", ["item", "value"])
    t0.add("repo SHA", git_sha(REPO))
    t0.add("branch", subprocess.run(["git", "-C", str(REPO), "rev-parse", "--abbrev-ref",
                                     "HEAD"], capture_output=True, text=True).stdout.strip())
    t0.add("episode plane SHA (provenance)", EPISODES_SHA)
    t0.add("episode plane path", args.episodes)
    t0.add("episode plane rows", len(ep))
    t0.add("union rule", f"C1 UNION C2r with no C1 fire within +/-{UNION_GAP} sessions")
    t0.add("union episodes / names", f"{len(d)} / {d['ticker'].nunique()}")
    t0.add("price root", str(prices))
    t0.add("price last date (STLD)", price_meta.get("STLD", {}).get("last"))
    t0.add("darkpool deep panel", f"{args.darkpool_deep} :: {dark_meta.get('panel_deep')}")
    t0.add("darkpool wide panel", f"{args.darkpool_wide} :: {dark_meta.get('panel')}")
    t0.add("options_flow root", f"{opt_root} :: {len(opt_files)} summary files")
    t0.add("engine functions used (as-is)",
           "indicators_m2.anchored_vwap / rolling_poc / poc_retest_hold; "
           "darkpool_signals.trailing_z / usable_history / streak_above_norm; "
           "stock_technicals.atr")
    t0.add("primary label basis", f"X = entry - {STOP_X_ATR} x ATR14 (fully entry-anchored)")
    t0.add("robustness bases", f"A = P_low x {STOP_A_K}, F = entry - {STOP_F_PCT:.0%}")
    t0.add("false-bounce leg in labels", "NONE (charter §1)")
    t0.emit()

    # ---------------------------------------------- R1 EXEMPLARS (gate 1 — printed FIRST)
    print("\n" + "=" * 100)
    print("§R1 EXEMPLAR GATE — named union fires with every feature value, before any pool")
    print("=" * 100)
    exm_all = d[d["ticker"].isin(EXEMPLARS) & (d["date"] >= EXEMPLAR_FROM)]
    exm_ung = exm_all[exm_all["stopped_X"].isna()]
    ex_note = (f"{len(exm_ung)} of {len(exm_all)} exemplar rows are UNGRADED "
               f"({', '.join(f'{r.ticker} {r.date.date()}' for r in exm_ung.itertuples())}): "
               f"fewer than {MIN_FWD} forward sessions exist past them on a tape ending "
               f"{str(d['date'].max().date()) if len(d) else 'n/a'}, so their label columns "
               "are blank by the truncation rule and they contribute to NO pooled cell.")
    t1 = Table("R1", "STLD and NEM 2026 union fires — every feature at the fire instant",
               ["ticker", "date", "lane", "close", "P_low", "entry_vs_low", "ATR14",
                "stop X", "stopped X", "r_mult X", "stopped A", "stopped F",
                "D1a avwap_above", "D1b avwap_dist", "D1 anchor", "D2 poc_dist", "D2 poc",
                "D3 poc_hold", "D4 absorption", "D5 quiet", "T1 part_z", "T2 streak",
                "T3 prem_z", "P1 entered", "P2 entered"],
               "the charter's coverage gate: a construction that cannot show its work on the "
               "motivating exemplars does not get presented on pooled means. " + ex_note)
    exm = d[d["ticker"].isin(EXEMPLARS) & (d["date"] >= EXEMPLAR_FROM)].sort_values(
        ["ticker", "date"])
    for _, r in exm.iterrows():
        t1.add(r["ticker"], str(r["date"].date()), r["lane"], r["close"], r["p_low"],
               r["entry_vs_low"], r["atr14"], r["stop_X"], r["stopped_X"], r["r_mult_X"],
               r["stopped_A"], r["stopped_F"], r["d1_avwap_above"], r["d1_avwap_dist"],
               str(pd.Timestamp(r["d1_anchor_date"]).date()), r["d2_poc_dist"], r["d2_poc"],
               r["d3_poc_hold"], r["d4_absorption"], r["d5_quiet"], r["t1_part_z"],
               r["t2_streak"], r["t3_prem_z"], r["P1_entered"], r["P2_entered"])
    t1.emit()

    # ---------------------------------------------- R2 labels
    t2 = Table("R2", "§1 label accounting — three stop bases, no false-bounce leg",
               ["basis", "definition", "episodes", "names", "graded", "truncated (<30 fwd)",
                "stop-out%", "mean R", "median R", "p25 R", "p75 R", "median risk (% entry)"],
               "STOPPED = a low touches the stop before T+42; SURVIVED otherwise. r_mult is "
               "recomputed per basis: -1R on a stop, else the horizon close-to-close move in "
               "units of that basis' own initial risk.")
    for b, defn in (("X", f"entry - {STOP_X_ATR}xATR14  (PRIMARY)"),
                    ("A", f"P_low x {STOP_A_K}  (bake-off continuity)"),
                    ("F", f"entry - {STOP_F_PCT:.0%}")):
        gr = d[d[f"stopped_{b}"].notna()]
        rm = gr[f"r_mult_{b}"].dropna().to_numpy(dtype="float64")
        t2.add(b, defn, len(d), int(d["ticker"].nunique()), len(gr),
               int(d[f"trunc_{b}"].fillna(False).astype(bool).sum()),
               pct(rate(gr[f"stopped_{b}"].tolist())),
               float(np.mean(rm)) if rm.size else None,
               float(np.median(rm)) if rm.size else None,
               float(np.percentile(rm, 25)) if rm.size else None,
               float(np.percentile(rm, 75)) if rm.size else None,
               med((gr["risk_pct_X"] if b == "X" else
                    (gr["close"] - gr[f"stop_{b}"]) / gr["close"]).tolist()))
    t2.emit()

    # ---------------------------------------------- R3 policies
    # HORIZON MISALIGNMENT, measured: each policy re-anchors its +42 window to its OWN entry
    hz = {}
    for pk in ("P1", "P2"):
        off = (d.loc[d[f"{pk}_entered"].astype(bool), f"{pk}_entry_pos"]
               - d.loc[d[f"{pk}_entered"].astype(bool), "pos"]).dropna().astype(float)
        hz[pk] = (float(off.median()) if len(off) else None,
                  float(np.percentile(off, 95)) if len(off) else None)
    hz_note = (
        "HORIZON MISALIGNMENT (measured, not asserted): P0 is graded over exactly [T, T+"
        f"{FWD_MAX}], but each policy re-anchors its own +{FWD_MAX} window to its LATER "
        f"entry — P1 enters a median {hz['P1'][0]:.0f} / p95 {hz['P1'][1]:.0f} sessions "
        f"after T (grading to ~T+{FWD_MAX + (hz['P1'][0] or 0):.0f} / T+"
        f"{FWD_MAX + (hz['P1'][1] or 0):.0f}) and P2 a median {hz['P2'][0]:.0f} / p95 "
        f"{hz['P2'][1]:.0f} (grading to ~T+{FWD_MAX + (hz['P2'][0] or 0):.0f} / T+"
        f"{FWD_MAX + (hz['P2'][1] or 0):.0f}). A longer window gives a position more time "
        "BOTH to be stopped and to run, so this row-set comparison confounds the policy with "
        "its clock; R8b re-runs P1 on the fire's own stop and horizon to separate them.")
    t3 = Table("R3", "§4 POST-TROUGH EVIDENCE AS POLICIES (basis X, entries at real closes)",
               ["policy", "definition", "fires", "names", "entered", "entry rate%",
                "never entered", "graded", "stop-out%", "mean R", "median R", "p25 R",
                "p75 R", "total R per name-year", "median entry give-up vs P0"],
               "conditioning on 'the low held k sessions' deletes early stop-outs and "
               "manufactures edge (bake-off §RT), so the structural tier is measured as "
               "decision policies over the SAME fire set — fires never entered are counted, "
               "never dropped. No scalar winner is pre-declared. " + hz_note)
    p0_entry = d.set_index(["ticker", "pos"])["P0_entry_close"]
    for pk, defn in (("P0", "enter at the fire close"),
                     ("P1", f"first session >= T+{P1_WAIT} with no stop touch printed "
                            f"and close <= fire close x {P1_CHASE_CAP}"),
                     ("P2", f"knowability close of the first confirmed r3 swing low in "
                            f"[T, T+{P2_WINDOW}] holding above P_low x {P2_HOLD}")):
        ent = d[d[f"{pk}_entered"].astype(bool)]
        gr = ent[ent[f"{pk}_stopped"].notna()]
        rm = gr[f"{pk}_r_mult"].dropna().to_numpy(dtype="float64")
        give = None
        if pk != "P0" and not ent.empty:
            j = ent.set_index(["ticker", "pos"])
            give = med((j[f"{pk}_entry_close"] / p0_entry.reindex(j.index) - 1.0).tolist())
        t3.add(pk, defn, len(d), int(d["ticker"].nunique()), len(ent),
               pct(len(ent) / len(d)) if len(d) else None,
               len(d) - len(ent), len(gr), pct(rate(gr[f"{pk}_stopped"].tolist())),
               float(np.mean(rm)) if rm.size else None,
               float(np.median(rm)) if rm.size else None,
               float(np.percentile(rm, 25)) if rm.size else None,
               float(np.percentile(rm, 75)) if rm.size else None,
               round(float(np.sum(rm)) / name_years, 4) if rm.size and name_years else None,
               give)
    t3.emit()
    note(f"policy per-name-year R is normalised by {name_years:.1f} name-years of measurable "
         "panel exposure (the union names' full priced history).")

    # ---------------------------------------------- R4/R5 ledgers
    print("\n" + "=" * 100)
    print("§R4 DEEP BATTERY LEDGER (full plane)   §R5 THIN BATTERY (PROBE tier by charter)")
    print("=" * 100)
    deep_rows = ledger(d, "deep", "R4")
    thin_rows = ledger(d, "thin", "R5")
    ref_rows = ledger(d, "ref", "R5ref")

    # ---------------------------------------------- R6 coverage (gate 6)
    # DIFFERENTIAL TRUNCATION: the thin feeds are RECENT, and so are the ungraded rows
    tr = d[d["stopped_X"].isna()]
    gd = d[d["stopped_X"].notna()]
    tr_share = rate(tr["t1_part_z"].notna().tolist())
    gd_share = rate(gd["t1_part_z"].notna().tolist())
    trunc_note = (
        f"DIFFERENTIAL TRUNCATION (measured): the {len(tr)} truncated rows carry a T1 value "
        f"{pct(tr_share)}% of the time against {pct(gd_share)}% of the {len(gd)} graded rows "
        f"— a {pct(None if tr_share is None or gd_share is None else tr_share - gd_share)}pp "
        "gap, because both the thin feeds and the ungraded right edge live in the same recent "
        "window. The thin lane's gradeable sample is therefore biased away from the newest "
        "fires it is otherwise best placed to see.")
    t6 = Table("R6", "Thin-battery COVERAGE — how many union episodes can the thin feeds "
                     "actually see?",
               ["feature", "episodes with a value", "share of union%", "names", "first date",
                "last date"],
               "load-bearing honesty: the dark-pool deep panel starts 2023-08 and the "
               "options-flow store 2026-01, and both need >= 40 trailing observations before "
               "a z exists at all, so the thin battery speaks for a small and RECENT slice "
               "of a 12-year plane. Every thin verdict is capped at PROBE for this reason. "
               + trunc_note)
    for key, label, _, grp in FEATURE_SPEC:
        if grp != "thin":
            continue
        s = d[d[key].notna()]
        t6.add(label, len(s), pct(len(s) / len(d)) if len(d) else None,
               int(s["ticker"].nunique()) if len(s) else 0,
               str(s["date"].min().date()) if len(s) else None,
               str(s["date"].max().date()) if len(s) else None)
    t6.add("union episodes with ANY dark-pool participation row",
           int((d["t1_obs"] > 0).sum()), pct(float((d["t1_obs"] > 0).mean())),
           int(d.loc[d["t1_obs"] > 0, "ticker"].nunique()), None, None)
    t6.emit()

    # A zero-coverage feed must say WHY, or the null reads as a bug in this script
    t6b = Table("R6b", "Thin-feed substrate diagnosis — what the feeds actually contain",
                ["feed", "files/rows", "column read", "non-null rows per name (median)",
                 "first usable date", "observations needed for a z", "verdict"],
                "the charter dated options_flow at 2026-01+, which is true of the FILE but "
                "not of the SIGNED column this feature needs")
    if opt_files:
        stats = []
        for f in opt_files:
            try:
                s = pd.read_parquet(f)["net_premium_mn"]
            except Exception:
                continue
            nn = int(s.notna().sum())
            fd = s.dropna().index.min() if nn else None
            stats.append((len(s), nn, fd))
        rows_med = int(np.median([x[0] for x in stats])) if stats else 0
        nn_med = int(np.median([x[1] for x in stats])) if stats else 0
        firsts = [x[2] for x in stats if x[2] is not None]
        t6b.add("options_flow (T3)", f"{len(opt_files)} files / {rows_med} rows (median)",
                "net_premium_mn", nn_med,
                str(pd.Timestamp(min(firsts)).date()) if firsts else None,
                f">= {Z_MIN_OBS + 1} rolling-window observations",
                "UNCOMPUTABLE — the signed column is far shorter than the file")
        deviate("T3 (options signed net-premium z) is UNCOMPUTABLE on this substrate and "
                f"reports n=0. The charter dates options_flow at 2026-01+, which holds for "
                f"the summary files ({rows_med} rows each) but NOT for `net_premium_mn`: the "
                f"signed column carries only ~{nn_med} non-null rows per name beginning "
                f"{str(pd.Timestamp(min(firsts)).date()) if firsts else 'n/a'}, so no "
                f"{Z_WINDOW}-session z with a {Z_MIN_OBS}-observation floor can exist for "
                "any episode. Reported as an empty lane rather than silently re-specified "
                "with a different (shorter, non-charter) z convention.")
    for tag, meta in (("finra panel_deep (T1/T2)", dark_meta.get("panel_deep")),
                      ("finra panel wide (T1/T2)", dark_meta.get("panel"))):
        if meta:
            t6b.add(tag, f"{meta['rows']} rows / {meta['tickers']} tickers", "total_vol",
                    None, meta["first"], f">= {Z_MIN_OBS + 1} participation observations",
                    "usable on the recent slice only")
    t6b.emit()

    # ---------------------------------------------- R7 the one permitted cross-tab
    gradeable = [r for r in deep_rows if r.get("spread_X") is not None
                 and r["feature"] != "d4_absorption"]
    live = [r for r in gradeable if r["read"] == "LIVE"]
    best = (max(live, key=lambda r: abs(r["spread_X"])) if live else
            (max(gradeable, key=lambda r: abs(r["spread_X"])) if gradeable else None))
    t7 = Table("R7", "The ONE pre-permitted cross-tab — strongest non-coupled deep feature "
                     "x D4 absorption share",
               ["strongest feature", "feature cell", "D4 absorption", "episodes", "names",
                "stop-out% (X)"],
               "no other combination was searched (charter §5)")
    if best is None:
        t7.add("(no gradeable deep feature)", "-", "-", 0, 0, None)
    else:
        kind = dict((k, kd) for k, _, kd, _ in FEATURE_SPEC)[best["feature"]]
        g = d[d["stopped_X"].notna() & d["d4_absorption"].notna()]
        cells = cells_for(g, best["feature"], kind)
        d4m = float(g["d4_absorption"].median())
        if cells:
            for cname, cmask in [cells[0], cells[-1]]:
                for blab, bmask in ((f"low (<= {d4m:.3g})", g["d4_absorption"] <= d4m),
                                    (f"high (> {d4m:.3g})", g["d4_absorption"] > d4m)):
                    r, n, k = fs_rate(g, cmask & bmask, "stopped_X")
                    t7.add(best["label"], cname, blab, n, k, pct(r))
        else:
            t7.add(best["label"], "(degenerate on the D4 subset)", "-", 0, 0, None)
    t7.emit()

    # ---------------------------------------------- §R8 review appendix
    r8: dict = {}
    if args.review:
        print("\n" + "=" * 100)
        print("§R8 REVIEW APPENDIX (phase-2 explanation-level receipts, frozen as tables)")
        print("=" * 100)
        r8 = run_review_appendix(d, name_years)

    # ---------------------------------------------- deviations + notes
    print("\n" + "=" * 100)
    print("DEVIATIONS (visible, never silent)")
    print("=" * 100)
    for i, x in enumerate(DEVIATIONS, 1):
        print(f"  D{i}. {x}")
    print("\nNOTES")
    for i, x in enumerate(NOTES, 1):
        print(f"  N{i}. {x}")

    # ---------------------------------------------- freeze
    out_dir = Path(args.out).resolve().parent
    feat_path = out_dir / "footprint_picker_features.parquet"
    dd = d.copy()
    # object columns here are bool-or-None / float-or-None mixtures (a null is an honest
    # "not computable", never a 0), so they need nullable dtypes, not a coerce-to-object dump
    for c in dd.columns:
        if dd[c].dtype != object or c in ("ticker", "lane"):
            continue
        vals = dd[c].dropna()
        if len(vals) and all(isinstance(v, (bool, np.bool_)) for v in vals):
            dd[c] = dd[c].astype("boolean")
        else:
            dd[c] = pd.to_numeric(dd[c], errors="coerce").astype("Float64")
    dd.to_parquet(feat_path, compression="zstd", index=False)
    result = {
        "study": "footprint_picker",
        "charter": "research/prophet_us_audit/FOOTPRINT_PICKER_PREREG_2026-08-11.md",
        "tier": "measurement/display — no gate, rank, veto or engine change ships from this",
        "run_metadata": {"run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "runtime_seconds": round(time.time() - t_start, 1),
                         "argv": sys.argv[1:]},
        "provenance": {
            "repo_sha": git_sha(REPO),
            "episodes_sha": EPISODES_SHA,
            "episodes_path": args.episodes,
            "episodes_rows": int(len(ep)),
            "price_root": str(prices),
            "price_last_date_max": max((v["last"] for v in price_meta.values()), default=None),
            "price_last_date_exemplars": {k: price_meta.get(k, {}).get("last")
                                          for k in EXEMPLARS},
            "price_names_probed": len(price_meta),
            "darkpool": dark_meta,
            "darkpool_paths": [args.darkpool_deep, args.darkpool_wide],
            "options_root": str(opt_root),
            "options_files": len(opt_files),
            "engine_functions": ["indicators_m2.anchored_vwap", "indicators_m2.rolling_poc",
                                 "indicators_m2.poc_retest_hold",
                                 "indicators_m2.volume_profile (imported, geometry ref)",
                                 "darkpool_signals.trailing_z",
                                 "darkpool_signals.usable_history",
                                 "darkpool_signals.streak_above_norm",
                                 "stock_technicals.atr"],
        },
        "constants": {k: v for k, v in sorted(globals().items())
                      if k.isupper() and isinstance(v, (int, float, str, tuple))
                      and not k.startswith("DEF_")},
        "union": {"c1": int(len(c1)), "c2r_total": int(len(c2)),
                  "c2r_dot_only": int(len(dot_only)), "union_episodes": int(len(d)),
                  "union_names": int(d["ticker"].nunique()),
                  "panel_name_years": round(name_years, 2),
                  "addon_rows_excluded": addon_n},
        "deviations": DEVIATIONS,
        "notes": NOTES,
        "tables": TABLES,
        "ledger": {"deep": deep_rows, "thin": thin_rows, "reference": ref_rows},
        "review_appendix": {k: v for k, v in r8.items() if not k.startswith("R8")},
        "features_parquet": feat_path.name,
        "features_rows": int(len(dd)),
        "features_columns": list(dd.columns),
    }
    Path(args.out).write_text(json.dumps(result, indent=1, default=str))
    print(f"\nfroze {len(dd)} union episodes -> {feat_path.name} "
          f"({feat_path.stat().st_size / 1e6:.2f} MB, zstd)")
    print(f"wrote {args.out}  ({Path(args.out).stat().st_size / 1e6:.2f} MB)  "
          f"in {time.time() - t_start:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
