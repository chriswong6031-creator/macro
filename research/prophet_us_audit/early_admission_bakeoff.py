#!/usr/bin/env python3
"""Early-admission construction bake-off — EXECUTES the frozen charter
``research/prophet_us_audit/EARLY_ADMISSION_BAKEOFF_2026-08-11.md`` §1-§7.

Measurement / display tier. No gate, rank, veto, or engine change ships from this file.
It asks the §6.9 question: for a FILTERING machine whose operator plants a stop under the
decline low, which candidate construction SURFACES a name closest to that low with
survivable stop geometry?

Everything indicator-side is REUSED, never re-derived:
  * 3D confluence + the ``early`` (grey-dot) leg : ``engine.signal_quality.signal_frame``
  * the absolute-session 3D grid + knowability   : ``engine.signal_quality._tf_grid``
  * 1D MACD-RSI / StochRSI                       : ``engine.signal_quality._rsi_macd/_stoch_rsi_kd``
  * Wilder ATR14                                 : ``engine.stock_technicals.atr``
  * structure-stop ARM->CONFIRM chain            : charting-app ``signal_layer.confluence_v2``

Every synthetic 3D-grid fire is stamped at its bucket's LAST session (G0.4 knowability),
never at the bucket OPEN label.

Run:  python3 research/prophet_us_audit/early_admission_bakeoff.py
      [--tickers STLD,NEM] [--out path.json]
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

from engine.signal_quality import (  # noqa: E402
    _rsi_macd, _stoch_rsi_kd, _tf_grid, _xup, signal_frame, ANCHOR_ERA, OS,
)
from engine.stock_technicals import atr as wilder_atr  # noqa: E402

# ---------------------------------------------------------------- frozen constants
BUCKET_N = 3               # the 3D grid every §7 marker is drawn on
DEDUP_SESSIONS = 10        # episode dedup: fires within 10 sessions collapse to the FIRST
C1_OS_BAND = 20            # C1/C3: both 3D %K and %D strictly under this at the cross bar
C1_ZERO_BOUND = 2.0        # C1z cohort: 3D %K printed <= this within the lookback
C1_ZERO_LOOKBACK = 10      # ... in the 10 completed 3D bars before the cross
C1_RECENT_1D = 5           # C1 immediate-confirm: last 1D cross-up within this many sessions
C1_WAIT_MAX = 10           # C1 waited-confirm: first fresh 1D cross-up within this window
PIVOT_R = 3                # C4 / structure-stop swing low radius
LOOKBACK_LOW = 45          # P_low window [T-45, T]
NEAR_LOW_PCT = 0.05        # near-low = entry within 5% of P_low
TROUGH_FWD = 15            # td_to_trough / false-bounce forward window
FALSE_BOUNCE_K = 0.98      # false bounce = forward low < P_low * 0.98
MAE_FWD = 21
FWD_MAX = 42               # survival / MFE / R2 horizon
MIN_FWD_SESSIONS = 30      # below this the survival/MFE/R2 row is TRUNCATED, not counted
STOP_A_K = 0.99            # stop A = P_low * 0.99
STOP_B_ATR = 0.25          # stop B = min(low(T), low(T-1)) - 0.25 * ATR14
R_MULTIPLE = 2.0
BREADTH_WASHOUT_BACK = 10  # washout breadth window [T-10, T]
BREADTH_TURN_BACK = 5      # turn breadth window [T-5, T]
BREADTH_SPREAD_READ = 0.10 # pre-stated read: >= 10pp top-vs-bottom false-bounce spread
STOP_NEAR_WIN = 10         # structure-stop near-low window [T-10, T+10]
STOP_NEAR_TOL = 2          # ... within +/- 2 sessions of its argmin low
SESSIONS_PER_YEAR = 252.0
# ---- §8 discriminator lane (frozen with the charter, before any §R number was viewed) ----
MA_TREND = 200             # trend class: above/below the 200-session mean
VOL_Z_WIN = 60             # down-day volume z-score baseline
VOL_CLIMAX_BACK = 15       # ... max over [T-15, T]
DECLINE_WIN = 126          # decline depth: close(T) / max close over [T-126, T] - 1
RS_WIN = 63                # 63-session relative strength vs SPY
X1D_BACK = 10              # "1D MACD-RSI crossed at/before T" lookback
REPEAT_BACK = 20           # repeat-fire flag: a prior C2r fire in [T-20, T-1]
WASH_SPELL_MAX = 40        # cap on the 3D washout-spell walk-back (buckets)
LIVE_PP = 0.10             # pre-stated: LIVE if |spread| >= 10pp, sign-stable across halves
SUGGESTIVE_PP = 0.05       # ... SUGGESTIVE if >= 5pp, sign-stable
MIN_CELL_N = 20            # an extreme cell thinner than this gets no verdict
MIN_CELL_NAMES = 20        # per-name-first spread needs this many names in each extreme cell
BOOT_B = 500               # month-cluster bootstrap draws
BOOT_SEED = 20260811
CURRENT_REGIME_FROM = "2026-01-01"
TRACE_FROM, TRACE_TO = "2026-05-01", "2026-08-10"
EXEMPLARS = ("STLD", "NEM", "HL", "UEC")
STORE_ONLY_EXEMPLARS = ("STLD", "NEM")
ADDON_EXEMPLARS = ("HL", "UEC")     # priced, no site/signals file -> never pooled in store lanes

CONSTRUCTIONS = ("C0", "C1", "C2s", "C2r", "C3", "C4")
STORE_LANES = ("C0", "C2s")          # lanes that read the published store
RECOMPUTED_LANES = ("C1", "C2r", "C3", "C4")

DEF_PRICE_ROOT = "/Users/chriswong/actions-runner-2/_work/macro/macro/data/baskets/ohlcv"
DEF_STOCKS_ROOT = "/Users/chriswong/actions-runner-2/_work/macro/macro/data/stocks"
DEF_MEMBERSHIP = "/Users/chriswong/actions-runner-2/_work/macro/macro/data/baskets/membership.json"
DEF_SPY = "/Users/chriswong/actions-runner-2/_work/macro/macro/data/yahoo/SPY.parquet"
DEF_CHARTING = "/Users/chriswong/Documents/Cluade/charting-app"

DEVIATIONS: list[str] = []
NOTES: list[str] = []
TABLES: dict[str, dict] = {}
#: store events dropped because they predate this price root's coverage (never relocated)
STORE_DROPPED: dict[str, int] = {"C0": 0, "C2s": 0}


def deviate(msg: str) -> None:
    if msg not in DEVIATIONS:
        DEVIATIONS.append(msg)


def note(msg: str) -> None:
    if msg not in NOTES:
        NOTES.append(msg)


# ---------------------------------------------------------------- plain-text tables
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
        w = [max(len(self.columns[i]), *(len(r[i]) for r in cells)) for i in range(len(self.columns))]
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
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, (np.bool_,)):
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


#: columnar layout for the frozen episode / stop dumps (fields once, not per row)
EPISODE_FIELDS = [
    "ticker", "date", "pos", "construction", "addon", "close", "p_low", "p_low_date",
    "entry_vs_low", "near_low", "entry_vs_low_open", "near_low_open", "open_slip",
    "td_to_trough", "false_bounce", "mae_21", "stop_a", "stop_b", "survive_a", "survive_b",
    "mfe_42", "reached_2r", "fwd21", "fwd42", "ex21", "ex42", "fwd_sessions",
    "window_sessions", "c1z", "meta",
]
STOP_FIELDS = ["ticker", "date", "close", "stop_level", "argmin_date", "gap",
               "near_low_stop", "full_window", "hist_rising", "m3_bull", "fwd10", "fwd21",
               "addon"]


META_FIELDS = ["basis", "type", "quality", "confirm", "cross_known", "wait_sessions",
               "zero_bound", "store_date", "mapped", "open_label", "k", "d", "pivot",
               "pivot_low", "d3_at_confirm"]
FEATURE_FIELDS = ["f_k_cross", "f_zero_bound", "f_wash_dur", "f_decline_depth",
                  "f_x1d_crossed", "f_hist_rising", "f_macd1_level", "f_higher_low",
                  "f_dist_swing", "f_vol_z_down", "f_vol_ratio", "f_above200", "f_rs63",
                  "f_spy_d3_lt20", "washout_breadth", "turn_breadth", "basket",
                  "members_with_data", "hindsight_roster"]


def episodes_frame(rows: list[dict]) -> pd.DataFrame:
    """Episode records -> a flat frame (meta dict exploded into columns) for parquet."""
    out = []
    for r in rows:
        d = {f: r.get(f) for f in EPISODE_FIELDS if f != "meta"}
        d.update({f: (r.get("meta") or {}).get(f) for f in META_FIELDS})
        d.update({f: r.get(f) for f in FEATURE_FIELDS})
        out.append(d)
    df = pd.DataFrame(out)
    for col in ("date", "p_low_date", "cross_known", "store_date", "open_label", "pivot"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def pct(x) -> float | None:
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(100.0 * x, 2)


def med(vals) -> float | None:
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return float(np.median(v)) if v else None


def mean(vals) -> float | None:
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return float(np.mean(v)) if v else None


def rate(flags) -> float | None:
    v = [bool(x) for x in flags if x is not None]
    return float(np.mean(v)) if v else None


# ---------------------------------------------------------------- loaders
def load_ohlc(ticker: str, price_root: Path, stocks_root: Path) -> tuple[pd.DataFrame | None, str]:
    """Adjusted daily OHLC(V). baskets/ohlcv primary; data/stocks fallback (no `open`)."""
    p = price_root / f"{ticker}.parquet"
    if p.exists():
        df = pd.read_parquet(p)
        if {"high", "low", "close"}.issubset(df.columns):
            return _norm_frame(df), "ohlcv"
    q = stocks_root / f"{ticker}.parquet"
    if q.exists():
        df = pd.read_parquet(q)
        if {"high", "low", "close"}.issubset(df.columns):
            out = _norm_frame(df)
            if "open" not in out.columns:
                # data/stocks carries no `open`: the next-session-open sensitivity column is
                # unavailable for these names (recorded, never silently substituted).
                out["open"] = np.nan
            return out, "stocks"
    return None, "missing"


def _norm_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = pd.DatetimeIndex(out.index).tz_localize(None).normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in out.columns]
    out = out[keep].dropna(subset=["close", "high", "low"])
    return out


def load_store(signals_dir: Path) -> dict[str, dict]:
    out = {}
    for path in sorted(signals_dir.glob("*.json")):
        try:
            out[path.stem] = json.loads(path.read_text())
        except Exception:
            continue
    return out


def git_sha(repo: Path, ref: str = "HEAD", *paths: str) -> str | None:
    cmd = (["git", "-C", str(repo), "log", "-1", "--format=%H", ref, "--", *paths]
           if paths else ["git", "-C", str(repo), "rev-parse", ref])
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=60).stdout.strip() or None
    except Exception:
        return None


# ---------------------------------------------------------------- per-name lanes
class NameData:
    """Everything one ticker contributes: price frame, both grids, and each lane's fires."""

    def __init__(self, ticker: str, df: pd.DataFrame, source: str):
        self.ticker, self.df, self.source = ticker, df, source
        self.idx = df.index
        self.pos = {d: i for i, d in enumerate(self.idx)}
        self.close = df["close"]
        self.high, self.low = df["high"], df["low"]
        self.open_ = df["open"] if "open" in df.columns else pd.Series(np.nan, index=self.idx)
        self.c = self.close.to_numpy(dtype="float64")
        self.h = self.high.to_numpy(dtype="float64")
        self.l = self.low.to_numpy(dtype="float64")
        self.o = self.open_.to_numpy(dtype="float64")
        self.atr14 = wilder_atr(self.high, self.low, self.close, 14).to_numpy(dtype="float64")

        # -- 1D legs (house parameterization, reused from the engine) --
        m1, s1 = _rsi_macd(self.close)
        self.macd1, self.sig1 = m1, s1
        self.hist1 = (m1 - s1).to_numpy(dtype="float64")
        self.macd1_ge = (m1 >= s1).fillna(False).to_numpy()
        self.xup1 = _xup(m1, s1).fillna(False).to_numpy()
        self.k1, self.d1 = _stoch_rsi_kd(self.close)

        # -- 3D grid + confluence frame (bucket-OPEN labelled; knowability = bucket LAST) --
        self.grid3 = _tf_grid(self.close, BUCKET_N, "US")
        self.sf = signal_frame(self.close, self.high, self.low, market="US")
        self.ok = not self.sf.empty
        self.last_session = self.grid3.last_session          # label -> bucket last session
        self.bucket_of_row = self.grid3.bucket               # daily date -> bucket id
        self.label_of_bucket = self.grid3.label              # bucket id -> OPEN label
        if self.ok:
            ls = pd.DatetimeIndex(self.last_session.reindex(self.sf.index).to_numpy())
            self.sf_known = ls                               # daily knowability date per 3D row
            self.d3_daily = self._to_daily(self.sf["d"], ls)
            self.k3_daily = self._to_daily(self.sf["k"], ls)
            self.m3_ge_daily = self._to_daily(
                (self.sf["macd"] >= self.sf["sig"]).astype(float), ls) >= 0.5
        else:
            self.sf_known = pd.DatetimeIndex([])
            self.d3_daily = pd.Series(np.nan, index=self.idx)
            self.k3_daily = pd.Series(np.nan, index=self.idx)
            self.m3_ge_daily = pd.Series(False, index=self.idx)
        # -- §8 feature substrate (all PIT at the fire session) --
        self.ma200 = self.close.rolling(MA_TREND).mean().to_numpy(dtype="float64")
        vol = (df["volume"] if "volume" in df.columns
               else pd.Series(np.nan, index=self.idx)).astype("float64")
        self.vol = vol.to_numpy(dtype="float64")
        self.vol20 = vol.rolling(20).mean().to_numpy(dtype="float64")
        vm, vs = vol.rolling(VOL_Z_WIN).mean(), vol.rolling(VOL_Z_WIN).std(ddof=0)
        vz = (vol - vm) / vs.replace(0, np.nan)
        down = self.close < self.close.shift(1)
        self.vol_z_down = vz.where(down).to_numpy(dtype="float64")   # NaN on up days
        self.pivot_mask = self._pivot_mask()
        self.fires: dict[str, list[dict]] = {}
        self.unconfirmed_c1 = 0
        self.eval_start_pos: int | None = None

    def _pivot_mask(self) -> np.ndarray:
        """Radius-3 swing lows on the daily LOW, strict on both sides (the C4 / structure
        primitive). A pivot at p is only KNOWABLE at p+3."""
        cond = pd.Series(True, index=self.idx)
        for j in range(1, PIVOT_R + 1):
            cond &= (self.low < self.low.shift(j)) & (self.low < self.low.shift(-j))
        return cond.fillna(False).to_numpy()

    def row3_as_of(self, T: int) -> int | None:
        """Index of the last COMPLETED 3D bucket row as of daily position T."""
        if not self.ok or len(self.sf_known) == 0:
            return None
        r = int(self.sf_known.searchsorted(self.idx[T], side="right")) - 1
        return r if r >= 0 else None

    def _to_daily(self, series: pd.Series, known: pd.DatetimeIndex) -> pd.Series:
        """3D state -> daily, forward-filled from each bucket's LAST session (knowability)."""
        kd = pd.Series(series.to_numpy(), index=known)
        kd = kd[~kd.index.isna()]
        kd = kd[~kd.index.duplicated(keep="last")].sort_index()
        return kd.reindex(self.idx, method="ffill")

    def bucket_last_for(self, day: pd.Timestamp) -> pd.Timestamp | None:
        """Map any date (a bucket OPEN label, or any session) to its bucket's LAST session."""
        if day in self.last_session.index:
            v = self.last_session.loc[day]
            return None if pd.isna(v) else pd.Timestamp(v)
        # Not a label of THIS series' grid (store built on a deeper price cache): resolve the
        # bucket id from the absolute session calendar and take that bucket's last session.
        try:
            from engine import session_anchor
            bid = int(session_anchor.session_positions(
                pd.DatetimeIndex([day]), "US")[0]) // BUCKET_N
        except Exception:
            return None
        if bid in self.label_of_bucket.index:
            lab = self.label_of_bucket.loc[bid]
            v = self.last_session.get(lab)
            return None if v is None or pd.isna(v) else pd.Timestamp(v)
        return None

    def snap(self, day) -> int | None:
        """Position of `day` in this name's session index; else the first session AFTER it.

        Returns None for a date BEFORE this series starts: the store is built on a deeper
        price cache (1996+) than the adjusted ohlcv root (2014+), and snapping a 1998 marker
        onto the first available bar would fabricate an episode. Those are dropped and
        counted, never relocated."""
        d = pd.Timestamp(day)
        i = self.pos.get(d)
        if i is not None:
            return i
        if d < self.idx[0]:
            return None
        j = int(self.idx.searchsorted(d, side="left"))
        return j if j < len(self.idx) else None


# ---------------------------------------------------------------- fire generators
def gen_c0(nd: NameData, doc: dict | None) -> list[dict]:
    """C0 — incumbent BUY/REBUY markers as published (signal_date is the knowable date)."""
    out = []
    for m in (doc or {}).get("markers", []):
        if m.get("type") not in ("buy", "rebuy"):
            continue
        sd = m.get("signal_date") or None
        if sd:
            day, basis = pd.Timestamp(sd), "signal_date"
        elif m.get("date"):
            bl = nd.bucket_last_for(pd.Timestamp(m["date"]))
            if bl is None:
                continue
            day, basis = bl, "bucket_last_from_open_label"
        else:
            continue
        i = nd.pos.get(day)
        if i is None:
            i = nd.snap(day)          # store date not a session of THIS price series
            if i is None:
                STORE_DROPPED["C0"] += 1
                continue
            day = nd.idx[i]
            basis += "+snapped"
        out.append({"date": day, "pos": i, "basis": basis, "type": m.get("type"),
                    "quality": m.get("quality")})
    return out


def gen_c2s(nd: NameData, doc: dict | None) -> list[dict]:
    """C2s — published grey dots. The store stamps them at the bucket OPEN label (measured,
    see the parity table), so each is mapped to its bucket's LAST session for knowability."""
    out = []
    for ds in (doc or {}).get("early_markers", []) or []:
        raw = pd.Timestamp(ds)
        bl = nd.bucket_last_for(raw)
        if bl is None:
            STORE_DROPPED["C2s"] += 1
            continue
        i = nd.pos.get(bl)
        if i is None:
            i = nd.snap(bl)
            if i is None:
                STORE_DROPPED["C2s"] += 1
                continue
            bl = nd.idx[i]
        out.append({"date": bl, "pos": i, "store_date": raw,
                    "mapped": bool(bl != raw)})
    return out


def gen_c1(nd: NameData) -> tuple[list[dict], list[dict], int]:
    """C1 — 3D StochRSI %K x %D bull cross with BOTH lines < 20, confirmed by the 1D
    MACD-RSI cross-up (immediate if one is already in force, else the first fresh one
    within 10 sessions). Returns (fires, c1z_subset, unconfirmed_count)."""
    if not nd.ok:
        return [], [], 0
    k, d = nd.sf["k"], nd.sf["d"]
    cross = _xup(k, d).fillna(False)
    deep = (k < C1_OS_BAND) & (d < C1_OS_BAND)
    zero = k.shift(1).rolling(C1_ZERO_LOOKBACK, min_periods=1).min() <= C1_ZERO_BOUND
    sel = (cross & deep).fillna(False).to_numpy()
    kn = nd.sf_known
    fires, unconfirmed = [], 0
    for r in np.flatnonzero(sel):
        kd = kn[r]
        if pd.isna(kd):
            continue
        i = nd.pos.get(pd.Timestamp(kd))
        if i is None:
            continue
        since = _bars_since_at(nd.xup1, i)
        if nd.macd1_ge[i] and since is not None and since <= C1_RECENT_1D:
            fires.append({"date": nd.idx[i], "pos": i, "confirm": "immediate",
                          "cross_known": nd.idx[i], "zero_bound": bool(zero.iloc[r]),
                          "row3": int(r)})
            continue
        j = None
        for t in range(i + 1, min(i + 1 + C1_WAIT_MAX, len(nd.idx))):
            if nd.xup1[t]:
                j = t
                break
        if j is None:
            unconfirmed += 1
            continue
        fires.append({"date": nd.idx[j], "pos": j, "confirm": "waited",
                      "cross_known": nd.idx[i], "wait_sessions": j - i,
                      "zero_bound": bool(zero.iloc[r]), "row3": int(r)})
    c1z = [f for f in fires if f.get("zero_bound")]
    return fires, c1z, unconfirmed


def _bars_since_at(flags: np.ndarray, i: int) -> int | None:
    """Sessions since the most recent True at or before i (0 = at i); None if never."""
    prior = np.flatnonzero(flags[: i + 1])
    return None if prior.size == 0 else int(i - prior[-1])


def gen_c2r(nd: NameData) -> list[dict]:
    """C2r — the engine's own `early` leg recomputed from prices, stamped at bucket-LAST."""
    if not nd.ok:
        return []
    sel = nd.sf["early"].fillna(False).to_numpy().astype(bool)
    out = []
    for r in np.flatnonzero(sel):
        kd = nd.sf_known[r]
        if pd.isna(kd):
            continue
        i = nd.pos.get(pd.Timestamp(kd))
        if i is None:
            continue
        out.append({"date": nd.idx[i], "pos": i, "open_label": nd.sf.index[r],
                    "k": float(nd.sf["k"].iloc[r]), "d": float(nd.sf["d"].iloc[r]),
                    "row3": int(r)})
    return out


def gen_c3(nd: NameData, c2r: list[dict]) -> list[dict]:
    """C3 — C2r fires whose 3D cross bar itself printed under the 20 line (both %K and %D)."""
    return [f for f in c2r if np.isfinite(f["k"]) and np.isfinite(f["d"])
            and f["k"] < C1_OS_BAND and f["d"] < C1_OS_BAND]


def gen_c4(nd: NameData) -> list[dict]:
    """C4 — confirmed radius-3 swing low (strict min of lows p-3..p+3), knowable at p+3,
    qualifying when the last COMPLETED 3D bucket's %D is under 20 as of p+3."""
    lo = nd.low
    cond = pd.Series(True, index=nd.idx)
    for j in range(1, PIVOT_R + 1):
        cond &= (lo < lo.shift(j)) & (lo < lo.shift(-j))
    cond = cond.fillna(False).to_numpy()
    d3 = nd.d3_daily.to_numpy(dtype="float64")
    out = []
    for p in np.flatnonzero(cond):
        t = int(p) + PIVOT_R
        if t >= len(nd.idx):
            continue
        if not np.isfinite(d3[t]) or d3[t] >= C1_OS_BAND:
            continue
        out.append({"date": nd.idx[t], "pos": t, "pivot": nd.idx[p],
                    "pivot_low": float(lo.iloc[p]), "d3_at_confirm": float(d3[t])})
    return out


def dedup(fires: list[dict]) -> list[dict]:
    """Episode dedup: fires within DEDUP_SESSIONS of a prior KEPT fire collapse to the first."""
    kept, last = [], None
    for f in sorted(fires, key=lambda x: x["pos"]):
        if last is not None and f["pos"] - last < DEDUP_SESSIONS:
            continue
        kept.append(f)
        last = f["pos"]
    return kept


# ---------------------------------------------------------------- the ruler (§2)
def rule_episode(nd: NameData, T: int, spy: pd.Series | None) -> dict | None:
    n = len(nd.idx)
    if T < LOOKBACK_LOW:
        return None                                   # no full [T-45, T] decline window
    c0 = nd.c[T]
    if not np.isfinite(c0) or c0 <= 0:
        return None
    p_low_slice = nd.l[T - LOOKBACK_LOW: T + 1]
    p_low = float(np.nanmin(p_low_slice))
    if not np.isfinite(p_low) or p_low <= 0:
        return None
    fwd_avail = n - 1 - T
    row: dict = {
        "ticker": nd.ticker, "date": nd.idx[T], "pos": T, "close": float(c0),
        "p_low": p_low, "p_low_date": nd.idx[T - LOOKBACK_LOW + int(np.nanargmin(p_low_slice))],
        "entry_vs_low": float(c0 / p_low - 1.0),
        "fwd_sessions": int(fwd_avail),
    }
    row["near_low"] = bool(row["entry_vs_low"] <= NEAR_LOW_PCT)

    nxt_open = nd.o[T + 1] if T + 1 < n else np.nan
    if np.isfinite(nxt_open) and nxt_open > 0:
        row["entry_vs_low_open"] = float(nxt_open / p_low - 1.0)
        row["near_low_open"] = bool(row["entry_vs_low_open"] <= NEAR_LOW_PCT)
        row["open_slip"] = float(nxt_open / c0 - 1.0)
    else:
        row["entry_vs_low_open"] = row["near_low_open"] = row["open_slip"] = None

    # td_to_trough + false bounce need the full [T, T+15] forward leg
    if fwd_avail >= TROUGH_FWD:
        w = nd.l[T - LOOKBACK_LOW: T + TROUGH_FWD + 1]
        row["td_to_trough"] = int(T - (T - LOOKBACK_LOW + int(np.nanargmin(w))))
        fb = nd.l[T + 1: T + TROUGH_FWD + 1]
        row["false_bounce"] = bool(np.nanmin(fb) < p_low * FALSE_BOUNCE_K)
    else:
        row["td_to_trough"] = row["false_bounce"] = None
        row["trunc_trough"] = True

    if fwd_avail >= MAE_FWD:
        row["mae_21"] = float(np.nanmin(nd.l[T + 1: T + MAE_FWD + 1]) / c0 - 1.0)
    else:
        row["mae_21"] = None

    stop_a = p_low * STOP_A_K
    atr = nd.atr14[T]
    lo2 = min(nd.l[T], nd.l[T - 1]) if T >= 1 else nd.l[T]
    stop_b = float(lo2 - STOP_B_ATR * atr) if np.isfinite(atr) else None
    row["stop_a"] = float(stop_a)
    row["stop_b"] = stop_b

    if fwd_avail >= MIN_FWD_SESSIONS:
        end = min(T + FWD_MAX, n - 1)
        lows, closes = nd.l[T + 1: end + 1], nd.c[T + 1: end + 1]
        row["survive_a"] = bool(not np.any(lows <= stop_a))
        row["survive_b"] = (None if stop_b is None else bool(not np.any(lows <= stop_b)))
        row["mfe_42"] = float(np.nanmax(closes) / c0 - 1.0)
        target = c0 + R_MULTIPLE * (c0 - stop_a)
        hit = None
        for x in range(len(lows)):
            if lows[x] <= stop_a:            # same-session tie -> STOPPED (conservative)
                hit = False
                break
            if closes[x] >= target:
                hit = True
                break
        row["reached_2r"] = bool(hit) if hit is not None else False
        row["window_sessions"] = int(end - T)
    else:
        row["survive_a"] = row["survive_b"] = row["mfe_42"] = row["reached_2r"] = None
        row["trunc_forward"] = True

    for hz in (21, 42):
        key = f"fwd{hz}"
        if fwd_avail >= hz:
            row[key] = float(nd.c[T + hz] / c0 - 1.0)
            row[f"ex{hz}"] = (None if spy is None else _excess(spy, nd.idx[T], nd.idx[T + hz],
                                                              row[key]))
        else:
            row[key] = row[f"ex{hz}"] = None
    return row


# ---------------------------------------------------------------- §8 feature battery
def wash_spell(nd: NameData, r3: int | None) -> int | None:
    """Completed 3D buckets with %D < 20 in the CURRENT washout spell at bucket row r3.

    If r3 itself is not oversold the spell is the most recent contiguous run ending at or
    before r3 (0 when there is none inside the walk-back cap)."""
    if r3 is None or not nd.ok:
        return None
    d = nd.sf["d"].to_numpy(dtype="float64")
    j = r3
    while j >= 0 and r3 - j <= WASH_SPELL_MAX and not (np.isfinite(d[j]) and d[j] < C1_OS_BAND):
        j -= 1
    if j < 0 or r3 - j > WASH_SPELL_MAX:
        return 0
    n = 0
    while j - n >= 0 and np.isfinite(d[j - n]) and d[j - n] < C1_OS_BAND:
        n += 1
    return int(n)


def features(nd: NameData, T: int, fire: dict, spy_ctx: dict) -> dict:
    """The §8 battery, every value knowable at the close of session T."""
    f: dict = {}
    c0 = nd.c[T]

    # 1. washout depth — 3D %K at the CROSS bar (the fire's own 3D row where the lane has
    #    one; else the last completed bucket as of T), plus the 0-bound flag.
    r3 = fire.get("row3")
    if r3 is None:
        r3 = nd.row3_as_of(T)
    if r3 is not None and nd.ok:
        k3 = nd.sf["k"].to_numpy(dtype="float64")
        f["f_k_cross"] = float(k3[r3]) if np.isfinite(k3[r3]) else None
        lo = max(0, r3 - C1_ZERO_LOOKBACK)
        prior = k3[lo:r3]
        f["f_zero_bound"] = (bool(np.nanmin(prior) <= C1_ZERO_BOUND)
                             if prior.size and np.isfinite(prior).any() else None)
    else:
        f["f_k_cross"] = f["f_zero_bound"] = None
    # 2. washout duration
    f["f_wash_dur"] = wash_spell(nd, r3)
    # 3. decline depth
    a = max(0, T - DECLINE_WIN)
    hi = np.nanmax(nd.c[a: T + 1])
    f["f_decline_depth"] = float(c0 / hi - 1.0) if np.isfinite(hi) and hi > 0 else None
    # 4. 1D confirm state
    b = max(0, T - X1D_BACK)
    f["f_x1d_crossed"] = bool(nd.xup1[b: T + 1].any())
    f["f_hist_rising"] = bool(T >= 2 and np.isfinite(nd.hist1[T - 2])
                              and nd.hist1[T] > nd.hist1[T - 1] > nd.hist1[T - 2])
    m1v = nd.macd1.to_numpy(dtype="float64")[T]
    f["f_macd1_level"] = float(m1v) if np.isfinite(m1v) else None
    # 5. structure — PIT confirmed r3 swing lows (a pivot at p is knowable at p+3)
    piv = np.flatnonzero(nd.pivot_mask[: max(0, T - PIVOT_R) + 1])
    if piv.size >= 1:
        last = float(nd.l[piv[-1]])
        f["f_dist_swing"] = float(c0 / last - 1.0) if last > 0 else None
        f["f_higher_low"] = (bool(last >= float(nd.l[piv[-2]])) if piv.size >= 2 else None)
    else:
        f["f_dist_swing"] = f["f_higher_low"] = None
    # 6. volume signature
    vb = max(0, T - VOL_CLIMAX_BACK)
    w = nd.vol_z_down[vb: T + 1]
    f["f_vol_z_down"] = (float(np.nanmax(w)) if w.size and np.isfinite(w).any() else None)
    f["f_vol_ratio"] = (float(nd.vol[T] / nd.vol20[T])
                        if np.isfinite(nd.vol[T]) and np.isfinite(nd.vol20[T])
                        and nd.vol20[T] > 0 else None)
    # 7. trend class
    f["f_above200"] = (bool(c0 > nd.ma200[T]) if np.isfinite(nd.ma200[T]) else None)
    spy = spy_ctx.get("close")
    f["f_rs63"] = None
    if spy is not None and T >= RS_WIN:
        own = c0 / nd.c[T - RS_WIN] - 1.0 if nd.c[T - RS_WIN] > 0 else None
        i1 = int(spy.index.searchsorted(nd.idx[T], side="right")) - 1
        i0 = int(spy.index.searchsorted(nd.idx[T - RS_WIN], side="right")) - 1
        if own is not None and i0 >= 0 and i1 > i0:
            f["f_rs63"] = float(own - (spy.iloc[i1] / spy.iloc[i0] - 1.0))
    # 8. market context — SPY's own 3D %D under 20 at T (systemic washout)
    sd3 = spy_ctx.get("d3_daily")
    if sd3 is not None:
        i = int(sd3.index.searchsorted(nd.idx[T], side="right")) - 1
        v = float(sd3.iloc[i]) if i >= 0 else np.nan
        f["f_spy_d3_lt20"] = bool(v < C1_OS_BAND) if np.isfinite(v) else None
    else:
        f["f_spy_d3_lt20"] = None
    # 9. theme breadth is attached by the §3 lane; 10. repeat-fire by the §8 stage
    return f


def _excess(spy: pd.Series, d0: pd.Timestamp, d1: pd.Timestamp, r: float) -> float | None:
    try:
        i0 = spy.index.searchsorted(d0, side="right") - 1
        i1 = spy.index.searchsorted(d1, side="right") - 1
        if i0 < 0 or i1 < 0 or i1 <= i0:
            return None
        b = float(spy.iloc[i1] / spy.iloc[i0] - 1.0)
        return float(r - b)
    except Exception:
        return None


# ---------------------------------------------------------------- structure stops (§4)
def confirm_events(cv2, close: pd.Series) -> list[dict]:
    """CONFIRM (structure-stop) events with the swing LEVEL the daily close broke.

    charting-app HEAD's ``warn_events`` returns only ``{ts, kind}``; the ``stop_level``
    enrichment lives on an unmerged branch. This mirrors HEAD's own ARM/pivot machinery
    (``_arm_event_daily``, ``_confirmed_swing_lows_r3``, ARMED_WINDOW) verbatim and adds the
    level; the emitted confirm timestamps are cross-checked against ``warn_events`` itself.
    """
    dclose = close.dropna()
    di = dclose.index
    dv = dclose.to_numpy(dtype="float64")
    if len(di) < cv2.PIVOT_RADIUS * 2 + 2:
        return []
    arm = cv2._arm_event_daily(dclose, di)
    piv = cv2._confirmed_swing_lows_r3(dclose, cv2.PIVOT_RADIUS)
    piv_pos = di.searchsorted(piv, side="left")
    know_pos = piv_pos + cv2.PIVOT_RADIUS
    order = np.argsort(know_pos)
    kp, pv = know_pos[order], piv_pos[order]
    confirmed_low = np.full(len(di), np.nan)
    j, cur = 0, np.nan
    for t in range(len(di)):
        while j < len(kp) and kp[j] <= t:
            cur = dv[pv[j]]
            j += 1
        confirmed_low[t] = cur
    out, armed_until = [], -1
    for t in range(len(di)):
        if arm[t]:
            armed_until = t + cv2.ARMED_WINDOW
        if t <= armed_until:
            lvl = confirmed_low[t]
            if not np.isnan(lvl) and dv[t] < lvl:
                out.append({"date": di[t], "stop_level": float(lvl)})
                armed_until = -1
    return out


def stop_row(nd: NameData, T: int) -> dict | None:
    n = len(nd.idx)
    a, b = max(0, T - STOP_NEAR_WIN), min(n - 1, T + STOP_NEAR_WIN)
    if b - a < 2:
        return None
    arg = a + int(np.nanargmin(nd.l[a: b + 1]))
    row = {"ticker": nd.ticker, "date": nd.idx[T], "pos": T, "close": float(nd.c[T]),
           "argmin_date": nd.idx[arg], "gap": int(T - arg),
           "near_low_stop": bool(abs(T - arg) <= STOP_NEAR_TOL),
           "full_window": bool(T - STOP_NEAR_WIN >= 0 and T + STOP_NEAR_WIN <= n - 1)}
    row["hist_rising"] = bool(
        T >= 2 and np.isfinite(nd.hist1[T]) and np.isfinite(nd.hist1[T - 1])
        and np.isfinite(nd.hist1[T - 2])
        and nd.hist1[T] > nd.hist1[T - 1] > nd.hist1[T - 2])
    m3 = nd.m3_ge_daily.to_numpy()
    row["m3_bull"] = bool(m3[T]) if T < len(m3) else False
    for hz in (10, 21):
        row[f"fwd{hz}"] = (float(nd.c[T + hz] / nd.c[T] - 1.0) if T + hz < n else None)
    return row


# ---------------------------------------------------------------- §8 discriminator lane
#: (key, label, kind) — kind "t" = tercile within-lane, "b" = binary, "m" = median split
FEATURE_SPEC = [
    ("f_k_cross", "1  washout depth: 3D %K at the cross bar", "t"),
    ("f_zero_bound", "1b washout depth: 3D %K <= 2 in the prior 10 buckets", "b"),
    ("f_wash_dur", "2  washout duration: consecutive 3D buckets with %D < 20", "t"),
    ("f_decline_depth", "3  decline depth: close(T)/max close[T-126,T] - 1", "t"),
    ("f_x1d_crossed", "4a 1D confirm state: MACD-RSI crossed up within [T-10, T]", "b"),
    ("f_macd1_level", "4b 1D washout depth: MACD-RSI line level at T", "t"),
    ("f_higher_low", "5a structure: latest confirmed r3 swing low >= the prior one", "b"),
    ("f_dist_swing", "5b structure: close(T) vs the latest confirmed swing low", "t"),
    ("f_vol_z_down", "6a volume: max down-day volume z (vs 60d) in [T-15, T]", "m"),
    ("f_vol_ratio", "6b volume: fire-day volume / its 20d average", "t"),
    ("f_above200", "7a trend class: close(T) above its 200-session mean", "b"),
    ("f_rs63", "7b trend class: 63-session relative strength vs SPY", "t"),
    ("f_spy_d3_lt20", "8  market context: SPY's own 3D %D < 20 at T", "b"),
    ("washout_breadth", "9a theme breadth: basket members washed out in [T-10, T]", "t"),
    ("turn_breadth", "9b theme breadth: basket members with a C2r fire in [T-5, T]", "t"),
    ("f_repeat_false", "10 repeat-fire: a prior C2r fire in [T-20, T-1] that false-started",
     "b"),
]

#: Features whose DEFINITION shares a term with the label, so a spread is partly mechanical
#: rather than evidence of foresight. `f_dist_swing` measures how far close(T) sits above the
#: latest confirmed swing low; stop A is planted at P_low x 0.99 and the confirmed swing low
#: is normally that same low — so a high cell has a distant stop BY CONSTRUCTION and is
#: harder to stop out. Reported in full, marked, and never chosen as the 2x2 axis.
LABEL_COUPLED = {"f_dist_swing"}


def label_episodes(df: pd.DataFrame) -> pd.DataFrame:
    """§8 labels. FALSE START = stop A hit within +42 OR the false-bounce condition fired;
    DURABLE = stop A survived with no false bounce. Any row missing either input (a
    truncated forward window) is EXCLUDED and counted — never defaulted to a verdict."""
    d = df.copy()
    sa, fb = d["survive_a"], d["false_bounce"]
    known = sa.notna() & fb.notna()
    false_start = known & ((~sa.fillna(False).astype(bool)) | fb.fillna(False).astype(bool))
    durable = known & sa.fillna(False).astype(bool) & (~fb.fillna(True).astype(bool))
    d["label"] = np.where(false_start, "false_start",
                          np.where(durable, "durable", "excluded"))
    return d


def add_repeat_flag(d: pd.DataFrame, c2r: pd.DataFrame) -> pd.DataFrame:
    """Feature 10 — a prior C2r fire within [T-20, T-1] whose own episode false-started.

    Distance is EXACT session distance: the frozen episode plane carries each fire's
    position in its own name's session index (`pos`), so no calendar-day approximation is
    needed."""
    prior = c2r[c2r["label"] == "false_start"][["ticker", "pos"]]
    by: dict[str, np.ndarray] = {t: np.sort(g["pos"].to_numpy())
                                 for t, g in prior.groupby("ticker")}
    out = []
    for t, p in zip(d["ticker"].to_numpy(), d["pos"].to_numpy()):
        arr = by.get(t)
        if arr is None or not len(arr):
            out.append(False)
            continue
        out.append(bool(((arr >= p - REPEAT_BACK) & (arr < p)).any()))
    d = d.copy()
    d["f_repeat_false"] = out
    return d


def cells_for(d: pd.DataFrame, key: str, kind: str) -> list[tuple[str, pd.Series]] | None:
    """Split one feature into ordered cells. Returns None when the feature is degenerate."""
    v = d[key]
    if v.notna().sum() < 3 * MIN_CELL_N:
        return None
    if kind == "b":
        b = v.dropna().astype(bool)
        if b.nunique() < 2:
            return None
        m = v.notna()
        return [("False", m & (v == False)), ("True", m & (v == True))]  # noqa: E712
    if kind == "m":
        cut = float(v.median())
        return [(f"<= {cut:.3g}", v <= cut), (f"> {cut:.3g}", v > cut)]
    try:
        q = v.quantile([1 / 3, 2 / 3]).to_numpy()
    except Exception:
        return None
    if not np.isfinite(q).all() or q[0] >= q[1]:
        return None
    return [(f"bottom (<= {q[0]:.3g})", v <= q[0]),
            (f"middle", (v > q[0]) & (v <= q[1])),
            (f"top (> {q[1]:.3g})", v > q[1])]


def fs_rate(d: pd.DataFrame, mask) -> tuple[float | None, int, int]:
    part = d[mask & d["label"].isin(["false_start", "durable"])]
    if part.empty:
        return None, 0, 0
    return (float((part["label"] == "false_start").mean()), len(part),
            int(part["ticker"].nunique()))


def pn_fs_rate(d: pd.DataFrame, mask) -> tuple[float | None, int]:
    part = d[mask & d["label"].isin(["false_start", "durable"])]
    if part.empty:
        return None, 0
    per = part.groupby("ticker")["label"].apply(lambda s: (s == "false_start").mean())
    return float(per.mean()), int(per.size)


def boot_spread_ci(d: pd.DataFrame, lo_mask, hi_mask) -> tuple[float | None, float | None]:
    """Month-cluster bootstrap CI on the top-vs-bottom false-start spread (seeded)."""
    part = d[(lo_mask | hi_mask) & d["label"].isin(["false_start", "durable"])].copy()
    if part.empty:
        return None, None
    part["_hi"] = hi_mask.reindex(part.index).fillna(False).to_numpy()
    part["_fs"] = (part["label"] == "false_start").to_numpy()
    part["_m"] = part["date"].dt.to_period("M").astype(str)
    groups = [g[["_hi", "_fs"]].to_numpy() for _, g in part.groupby("_m")]
    if len(groups) < 4:
        return None, None
    rng = np.random.default_rng(BOOT_SEED)
    draws = []
    for _ in range(BOOT_B):
        pick = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        hi, fs = pick[:, 0].astype(bool), pick[:, 1].astype(bool)
        if hi.sum() == 0 or (~hi).sum() == 0:
            continue
        draws.append(fs[hi].mean() - fs[~hi].mean())
    if len(draws) < BOOT_B // 4:
        return None, None
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def ore_ledger(lane: str, d: pd.DataFrame, key_prefix: str) -> list[dict]:
    """The §8 ore ledger for one lane: univariate splits only, pre-stated read criteria."""
    graded = d[d["label"].isin(["false_start", "durable"])]
    tb = Table(f"{key_prefix}.ledger",
               f"§8 ORE LEDGER — {lane} episodes: false-start rate by feature cell",
               ["feature", "cells (low -> high)", "n per cell", "names per cell",
                "false-start% per cell", "spread pp (hi-lo)", "95% CI pp (month-cluster)",
                "per-name-first spread pp", "early-half pp", "late-half pp",
                "median entry_vs_low lo -> hi", "label-coupled", "READ"],
               "LIVE = |spread| >= 10pp AND sign-stable across the halves; SUGGESTIVE = "
               ">= 5pp sign-stable; else null. Extreme cells thinner than 20 episodes get "
               "no verdict. No combinations searched. `label-coupled` marks a feature whose "
               "definition shares a term with the label. READ THE entry_vs_low COLUMN "
               "ALONGSIDE EVERY SPREAD: stop A sits at P_low x 0.99, so any feature whose "
               "cells differ in entry_vs_low is partly re-measuring stop DISTANCE rather "
               "than foresight — a cell entered further above its decline low is harder to "
               "stop out for arithmetic reasons alone.")
    ledger = []
    for key, label, kind in FEATURE_SPEC:
        coupled = key in LABEL_COUPLED
        if key not in d.columns:
            tb.add(label, "(feature absent)", "-", "-", "-", None, "-", None, None, None,
                   "-", coupled, "no data")
            continue
        cells = cells_for(graded, key, kind)
        if cells is None:
            why = ("degenerate: one cell only" if graded[key].notna().sum() >= 3 * MIN_CELL_N
                   else "too few graded rows with this feature")
            tb.add(label, f"({why})", "-", "-", "-", None, "-", None, None, None, "-",
                   coupled, "degenerate")
            ledger.append({"feature": key, "read": "degenerate", "why": why})
            continue
        rates, ns, nn = [], [], []
        for _, m in cells:
            r, n, k = fs_rate(graded, m)
            rates.append(r)
            ns.append(n)
            nn.append(k)
        lo_m, hi_m = cells[0][1], cells[-1][1]
        sp = (None if rates[0] is None or rates[-1] is None else rates[-1] - rates[0])
        # The halves are cut on the median date of the rows this feature can SEE, not of the
        # whole lane: the theme-breadth features only exist after each basket's own creation
        # date, so a lane-wide median would hand them one empty half and no sign test.
        seen = graded[key].notna()
        smid = graded.loc[seen, "date"].median()
        early, late = seen & (graded["date"] <= smid), seen & (graded["date"] > smid)
        e_lo, e_hi = fs_rate(graded[early], lo_m[early]), fs_rate(graded[early], hi_m[early])
        l_lo, l_hi = fs_rate(graded[late], lo_m[late]), fs_rate(graded[late], hi_m[late])
        e_sp = (None if e_lo[0] is None or e_hi[0] is None else e_hi[0] - e_lo[0])
        l_sp = (None if l_lo[0] is None or l_hi[0] is None else l_hi[0] - l_lo[0])
        pn_lo, npn_lo = pn_fs_rate(graded, lo_m)
        pn_hi, npn_hi = pn_fs_rate(graded, hi_m)
        pn_sp = (pn_hi - pn_lo if pn_lo is not None and pn_hi is not None
                 and min(npn_lo, npn_hi) >= MIN_CELL_NAMES else None)
        thin = min(ns[0], ns[-1]) < MIN_CELL_N
        stable = (e_sp is not None and l_sp is not None and e_sp != 0 and l_sp != 0
                  and np.sign(e_sp) == np.sign(l_sp) == np.sign(sp or 0))
        if thin or sp is None:
            read = "thin — no verdict"
        elif abs(sp) >= LIVE_PP and stable:
            read = "LIVE"
        elif abs(sp) >= SUGGESTIVE_PP and stable:
            read = "SUGGESTIVE"
        else:
            read = "null"
        ci = boot_spread_ci(graded, lo_m, hi_m) if not thin else (None, None)
        # stop A is anchored at P_low x 0.99, so cells that differ in entry_vs_low differ in
        # how far the stop sits — printed next to every spread so the reader can tell a
        # discriminator from a stop-distance proxy.
        ev_lo = med(graded.loc[lo_m, "entry_vs_low"].tolist())
        ev_hi = med(graded.loc[hi_m, "entry_vs_low"].tolist())
        ev = ("-" if ev_lo is None or ev_hi is None
              else f"{ev_lo:.3f} -> {ev_hi:.3f}")
        tb.add(label, " | ".join(c[0] for c in cells), " | ".join(str(x) for x in ns),
               " | ".join(str(x) for x in nn),
               " | ".join("-" if r is None else f"{100 * r:.1f}" for r in rates),
               pct(sp),
               "-" if ci[0] is None else f"{100 * ci[0]:.1f} .. {100 * ci[1]:.1f}",
               pct(pn_sp), pct(e_sp), pct(l_sp), ev, coupled, read)
        ledger.append({"feature": key, "label": label, "kind": kind,
                       "cells": [c[0] for c in cells], "n": ns, "names": nn,
                       "false_start_rate": rates, "spread": sp, "ci95": list(ci),
                       "per_name_spread": pn_sp, "early_spread": e_sp,
                       "late_spread": l_sp, "entry_vs_low_lo": ev_lo,
                       "entry_vs_low_hi": ev_hi, "label_coupled": coupled, "read": read})
    tb.emit()
    return ledger


def run_discriminators(ep_path: Path, key_prefix: str = "R8") -> dict:
    """§8: read the FROZEN episode parquet back and map the ore. No fitted models."""
    raw = pd.read_parquet(ep_path)
    raw = raw[~raw["addon"].astype(bool)]                 # panel only; add-ons never pooled
    lab = label_episodes(raw)
    c2r = lab[lab["construction"] == "C2r"]
    out: dict = {}

    tl = Table(f"{key_prefix}.labels", "§8 label accounting (FALSE START / DURABLE / "
                                       "excluded-truncated)",
               ["lane", "episodes", "names", "false_start", "durable", "excluded "
                "(truncated forward window)", "false-start% of graded"],
               "FALSE START = stop A hit within +42 OR false bounce; DURABLE = stop A "
               "survived AND no false bounce; anything with a missing input is excluded")
    for lane in ("C2r", "C1"):
        d = lab[lab["construction"] == lane]
        g = d[d["label"].isin(["false_start", "durable"])]
        tl.add(lane, len(d), int(d["ticker"].nunique()),
               int((d["label"] == "false_start").sum()),
               int((d["label"] == "durable").sum()),
               int((d["label"] == "excluded").sum()),
               pct(float((g["label"] == "false_start").mean()) if len(g) else None))
    tl.emit()
    out["labels"] = TABLES[f"{key_prefix}.labels"]

    for lane in ("C2r", "C1"):
        d = add_repeat_flag(lab[lab["construction"] == lane], c2r)
        out[f"ledger_{lane}"] = ore_ledger(lane, d, f"{key_prefix}.{lane}")

    # the ONE permitted cross-tab: strongest feature on C2r x theme turn breadth (2x2)
    led = [r for r in out["ledger_C2r"] if r.get("spread") is not None
           and r["read"] in ("LIVE", "SUGGESTIVE", "null")]
    excluded = [r["feature"] for r in led if r.get("label_coupled")]
    led = [r for r in led if not r.get("label_coupled")]
    best = max(led, key=lambda r: abs(r["spread"])) if led else None
    live = [r for r in led if r["read"] == "LIVE"]
    if live:
        best = max(live, key=lambda r: abs(r["spread"]))
    if excluded:
        deviate("§8 2x2 axis: the charter says 'the single strongest LIVE feature'. The "
                f"strongest by raw spread is label-COUPLED ({', '.join(excluded)}) — its "
                "cells differ by how far stop A sits from the entry BY CONSTRUCTION, so "
                "cross-tabbing it would measure the ruler, not foresight. The 2x2 uses the "
                "strongest NON-coupled feature instead; the coupled row is still printed in "
                "full in the ledger with its spread and CI.")
    t2 = Table(f"{key_prefix}.cross2x2",
               "§8 2x2 — strongest C2r discriminator x theme TURN breadth (median split)",
               ["strongest feature", "feature cell", "turn breadth", "episodes", "names",
                "false-start%"],
               "the single pre-permitted cross-tab; no other combination was searched")
    if best is None:
        t2.add("(no gradeable feature)", "-", "-", 0, 0, None)
    else:
        d = add_repeat_flag(lab[lab["construction"] == "C2r"], c2r)
        g = d[d["label"].isin(["false_start", "durable"]) & d["turn_breadth"].notna()]
        kind = dict((k, kd) for k, _, kd in FEATURE_SPEC)[best["feature"]]
        cells = cells_for(g, best["feature"], kind)
        tbm = float(g["turn_breadth"].median()) if len(g) else np.nan
        if cells:
            for cname, cmask in [cells[0], cells[-1]]:
                for blab, bmask in ((f"low (<= {tbm:.3g})", g["turn_breadth"] <= tbm),
                                    (f"high (> {tbm:.3g})", g["turn_breadth"] > tbm)):
                    r, n, k = fs_rate(g, cmask & bmask)
                    t2.add(best["label"], cname, blab, n, k, pct(r))
        else:
            t2.add(best["label"], "(degenerate on the breadth subset)", "-", 0, 0, None)
    t2.emit()
    out["cross2x2"] = TABLES[f"{key_prefix}.cross2x2"]
    out["strongest_feature"] = None if best is None else best["feature"]
    return out


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--price-root", default=DEF_PRICE_ROOT)
    ap.add_argument("--stocks-root", default=DEF_STOCKS_ROOT)
    ap.add_argument("--signals-dir", default=str(REPO / "site" / "signals"))
    ap.add_argument("--membership", default=DEF_MEMBERSHIP)
    ap.add_argument("--spy", default=DEF_SPY)
    ap.add_argument("--charting-app", default=DEF_CHARTING)
    ap.add_argument("--tickers", default="", help="comma list; debug subset run")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent
                                        / "early_admission_bakeoff_results.json"))
    ap.add_argument("--discriminators", dest="discriminators", action="store_true",
                    default=True, help="run the §8 durable-vs-false-start lane (default)")
    ap.add_argument("--no-discriminators", dest="discriminators", action="store_false")
    args = ap.parse_args()

    t_start = time.time()
    price_root, stocks_root = Path(args.price_root), Path(args.stocks_root)
    signals_dir = Path(args.signals_dir)

    print("=" * 100)
    print("EARLY-ADMISSION CONSTRUCTION BAKE-OFF — executing "
          "EARLY_ADMISSION_BAKEOFF_2026-08-11.md §1-§7")
    print("=" * 100)

    store = load_store(signals_dir)
    store_names = sorted(store)
    subset = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    panel, unpriced = [], []
    for t in store_names:
        if (price_root / f"{t}.parquet").exists() or (stocks_root / f"{t}.parquet").exists():
            panel.append(t)
        else:
            unpriced.append(t)
    addons = [t for t in ADDON_EXEMPLARS if (price_root / f"{t}.parquet").exists()]
    universe = panel + [t for t in addons if t not in panel]
    if subset:
        universe = [t for t in universe if t in subset] or subset
        panel = [t for t in panel if t in subset]
        addons = [t for t in addons if t in subset]

    if unpriced:
        note(f"store names with no price series (excluded from every lane): {unpriced}")
    asof = {}
    for t, doc in store.items():
        asof.setdefault(doc.get("asof"), []).append(t)
    if len(asof) > 1:
        stale = {k: v for k, v in sorted(asof.items()) if len(v) <= 3}
        note("signals store is NOT uniformly as-of one date: "
             + ", ".join(f"{k}={len(v)} file(s)" for k, v in sorted(asof.items()))
             + f"; the stale files are {stale} — their C0/C2s right edge is older than the "
               "price tape, so those names carry fewer recent store episodes than they "
               "would on a fresh bake.")

    # SPY benchmark
    spy = None
    spy_src = None
    for cand in (price_root / "SPY.parquet", Path(args.spy)):
        if not cand.exists():
            continue
        try:
            sdf = pd.read_parquet(cand)
            if "close" not in sdf.columns:
                continue
            s = sdf["close"].dropna()
            s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
            spy = s[~s.index.duplicated(keep="last")].sort_index()
            spy_src = str(cand)
            break
        except Exception:
            continue
    spy_ctx: dict = {"close": spy, "d3_daily": None}
    if spy is not None:
        # SPY's own 3D StochRSI %D on the engine grid — the §8 systemic-washout context flag
        sg = _tf_grid(spy, BUCKET_N, "US")
        _, sd = _stoch_rsi_kd(sg.close)
        sk = pd.Series(sd.to_numpy(), index=pd.DatetimeIndex(
            sg.last_session.reindex(sd.index).to_numpy()))
        sk = sk[~sk.index.isna()]
        spy_ctx["d3_daily"] = sk[~sk.index.duplicated(keep="last")].sort_index()
    if spy is None:
        deviate("SPY benchmark unavailable — fwd21/fwd42 excess columns and the §8 "
                "relative-strength / systemic-washout features are null.")
    elif "baskets/ohlcv" not in (spy_src or ""):
        deviate(f"SPY is NOT in the ohlcv price root; benchmark read from {spy_src} "
                "(charter §2 named the ohlcv root).")

    # charting-app stop lane
    cv2 = None
    charting_sha = git_sha(Path(args.charting_app))
    try:
        sys.path.insert(0, str(Path(args.charting_app)))
        from signal_layer import confluence_v2 as _cv2   # noqa: E402
        cv2 = _cv2
    except Exception as exc:                                     # pragma: no cover
        deviate(f"charting-app signal_layer.confluence_v2 import FAILED ({exc}); "
                "the §4 structure-stop lane is SKIPPED.")
    if cv2 is not None and not hasattr(cv2, "warn_events"):
        cv2 = None
        deviate("charting-app confluence_v2 has no warn_events; §4 stop lane SKIPPED.")

    print(f"\nuniverse: store={len(store_names)}  priced-panel={len(panel)}  "
          f"add-on exemplars={addons}  unpriced={unpriced}")

    # ------------------------------------------------ per-name computation
    nds: dict[str, NameData] = {}
    price_meta: dict[str, dict] = {}
    for t in universe:
        df, src = load_ohlc(t, price_root, stocks_root)
        if df is None or len(df) < 300:
            continue
        nd = NameData(t, df, src)
        if not nd.ok:
            continue
        nds[t] = nd
        price_meta[t] = {"source": src, "first": str(df.index[0].date()),
                         "last": str(df.index[-1].date()), "rows": int(len(df))}
    print(f"names with a usable 3D frame: {len(nds)}")

    # common evaluation window per name: the first session at which the recomputed 3D lane
    # can fire at all (so store lanes and recomputed lanes are scored on the SAME window)
    for t, nd in nds.items():
        finite = nd.sf[["k", "d", "macd", "sig"]].notna().all(axis=1).to_numpy()
        if not finite.any():
            nd.eval_start_pos = None
            continue
        r0 = int(np.flatnonzero(finite)[0])
        kd = nd.sf_known[r0]
        i = nd.pos.get(pd.Timestamp(kd)) if not pd.isna(kd) else None
        nd.eval_start_pos = max(int(i or 0), LOOKBACK_LOW)

    raw_counts = {c: 0 for c in CONSTRUCTIONS}
    win_counts = {c: 0 for c in CONSTRUCTIONS}
    episodes: dict[str, list[dict]] = {c: [] for c in CONSTRUCTIONS}
    addon_episodes: dict[str, list[dict]] = {c: [] for c in CONSTRUCTIONS}
    c1z_keys: set[tuple[str, str]] = set()
    c1_confirm_split = {"immediate": 0, "waited": 0}
    c1_unconfirmed = 0
    c1_wait_lens: list[int] = []
    c2s_mapped = c2s_total = 0
    all_fires: dict[str, dict[str, list[dict]]] = {}
    raw_fires: dict[str, dict[str, list[dict]]] = {}

    for t, nd in nds.items():
        doc = store.get(t)
        c1, c1z, unconf = gen_c1(nd)
        c1_unconfirmed += unconf
        c2r = gen_c2r(nd)
        fires = {
            "C0": gen_c0(nd, doc),
            "C1": c1,
            "C2s": gen_c2s(nd, doc),
            "C2r": c2r,
            "C3": gen_c3(nd, c2r),
            "C4": gen_c4(nd),
        }
        c2s_total += len(fires["C2s"])
        c2s_mapped += sum(1 for f in fires["C2s"] if f.get("mapped"))
        z_dates = {f["date"] for f in c1z}
        raw_fires[t] = {c: list(v) for c, v in fires.items()}
        for c in CONSTRUCTIONS:
            raw_counts[c] += len(fires[c])
            kept = dedup(fires[c])
            fires[c] = kept
            if c == "C1":
                for f in kept:
                    c1_confirm_split[f["confirm"]] += 1
                    if f["confirm"] == "waited":
                        c1_wait_lens.append(int(f["wait_sessions"]))
                    if f["date"] in z_dates:
                        c1z_keys.add((t, str(f["date"].date())))
        all_fires[t] = fires
        is_addon = t not in panel
        for c in CONSTRUCTIONS:
            if is_addon and c in STORE_LANES:
                continue
            for f in fires[c]:
                if nd.eval_start_pos is None or f["pos"] < nd.eval_start_pos:
                    continue
                r = rule_episode(nd, f["pos"], spy)
                if r is None:
                    continue
                r["construction"] = c
                r["addon"] = is_addon
                r.update(features(nd, f["pos"], f, spy_ctx))
                r["meta"] = {k: (str(v.date()) if isinstance(v, pd.Timestamp) else v)
                             for k, v in f.items() if k not in ("pos",)}
                r["c1z"] = (c == "C1" and (t, str(f["date"].date())) in c1z_keys)
                (addon_episodes if is_addon else episodes)[c].append(r)
                if not is_addon:
                    win_counts[c] += 1

    # ------------------------------------------------ §R0 substrate + gates
    stld = nds.get("STLD")
    gate = {}
    if stld is not None:
        c0_dates = {str(f["date"].date()) for f in all_fires["STLD"]["C0"]}
        c0_raw = {str(pd.Timestamp(m["signal_date"]).date())
                  for m in store["STLD"]["markers"]
                  if m.get("type") in ("buy", "rebuy") and m.get("signal_date")}
        gate["stld_c0_2026_08_07"] = "2026-08-07" in c0_raw
        gate["stld_c0_2026_08_07_after_dedup"] = "2026-08-07" in c0_dates
        gate["stld_c2s_store_has_2026_07_10"] = "2026-07-10" in (
            store["STLD"].get("early_markers") or [])
        bl = stld.bucket_last_for(pd.Timestamp("2026-07-10"))
        gate["stld_2026_07_10_bucket_last"] = str(pd.Timestamp(bl).date()) if bl is not None else None
        c2r_dates = [str(f["date"].date()) for f in gen_c2r(stld)]
        gate["stld_c2r_2026_dates"] = [d for d in c2r_dates if d >= "2026-01-01"]
        target = gate["stld_2026_07_10_bucket_last"]
        gate["stld_c2r_reproduces_the_dot"] = bool(target in c2r_dates)

    tb = Table("R0", "Substrate, universe and acceptance gates", ["item", "value"])
    tb.add("repo SHA", git_sha(REPO))
    tb.add("signals store", f"{signals_dir} ({len(store_names)} files)")
    tb.add("price root", str(price_root))
    tb.add("STLD last price date", price_meta.get("STLD", {}).get("last"))
    tb.add("charting-app SHA", charting_sha)
    tb.add("SPY benchmark", spy_src)
    tb.add("anchor era", ANCHOR_ERA)
    tb.add("primary panel names (store ∩ priced ∩ 3D-frame)",
           len([t for t in nds if t in panel]))
    tb.add("add-on exemplar names (traces only)", ", ".join(t for t in nds if t not in panel))
    tb.add("GATE 1a  STLD C0 carries signal_date 2026-08-07", gate.get("stld_c0_2026_08_07"))
    tb.add("GATE 1b  STLD C2s store carries 2026-07-10",
           gate.get("stld_c2s_store_has_2026_07_10"))
    tb.add("         ... its 3D bucket LAST session", gate.get("stld_2026_07_10_bucket_last"))
    tb.add("GATE 1c  STLD C2r reproduces that dot", gate.get("stld_c2r_reproduces_the_dot"))
    tb.add("         STLD C2r 2026 fire dates", ", ".join(gate.get("stld_c2r_2026_dates", [])))
    tb.emit()

    # ------------------------------------------------ §R0b C2s / C2r parity
    par = Table("R0b", "C2s (published grey dot) vs C2r (recomputed) parity on the overlap",
                ["metric", "value"],
                "match = same name, |date diff| <= 1 session, after mapping the store's "
                "bucket-OPEN label to its bucket LAST session")
    matched = unmatched = extra = 0
    unmatched_ex, extra_ex = [], []
    for t, nd in nds.items():
        if t not in panel:
            continue
        # RAW (pre-dedup) streams on BOTH sides — this is an identity check, not an outcome
        s = sorted({f["pos"] for f in raw_fires[t]["C2s"]})
        rr = sorted({f["pos"] for f in raw_fires[t]["C2r"]})
        for p in s:
            hit = [q for q in rr if abs(q - p) <= 1]
            if hit:
                matched += 1
                rr.remove(hit[0])
            else:
                unmatched += 1
                if len(unmatched_ex) < 8:
                    unmatched_ex.append(f"{t}@{nd.idx[p].date()}")
        extra += len(rr)
        if rr and len(extra_ex) < 8:
            extra_ex.append(f"{t}@{nd.idx[rr[0]].date()}")
    tot = matched + unmatched
    par.add("raw store dots on priced panel names (bucket-last mapped)", tot)
    par.add("matched by a raw C2r fire within 1 session", matched)
    par.add("match rate", pct(matched / tot) if tot else None)
    par.add("store dots with NO C2r counterpart", unmatched)
    par.add("C2r fires with NO store dot (store trims history / deeper cache)", extra)
    par.add("unmatched examples", ", ".join(unmatched_ex))
    par.add("C2r-only examples", ", ".join(extra_ex))
    par.add("raw store dots whose date was a bucket-OPEN label (remapped)",
            f"{c2s_mapped} of {c2s_total}")
    par.emit()
    if c2s_mapped:
        note("MEASURED: `early_markers` in site/signals are stamped at the 3D bucket OPEN "
             f"label, not the bucket last session ({c2s_mapped}/{c2s_total} moved on "
             "mapping). Every C2s episode here is stamped at its bucket LAST session per "
             "the G0.4 knowability law; the raw store date is kept in each episode's meta.")

    # ---------------------------------- §R0c the dot as PLOTTED vs as KNOWABLE
    # The operator reads the dot off the chart at the bucket-OPEN label; the G0.4 law says it
    # is only knowable at the bucket's LAST close. Both stamps are priced so the cost of the
    # correction is a number, not an assertion.
    plt = Table("R0c", "Grey dot as PLOTTED (store bucket-OPEN label) vs as KNOWABLE "
                       "(bucket LAST session) — the cost of the G0.4 correction",
                ["stamp", "episodes", "names", "median entry_vs_low", "near_low%",
                 "median close"],
                "same episode set, two entry stamps; gap between them printed below")
    gaps, plot_rows, know_rows = [], [], []
    for t, nd in nds.items():
        if t not in panel:
            continue
        for f in all_fires[t]["C2s"]:
            if nd.eval_start_pos is None or f["pos"] < nd.eval_start_pos:
                continue
            j = nd.pos.get(pd.Timestamp(f["store_date"]))
            if j is None:
                continue
            a, b = rule_episode(nd, j, spy), rule_episode(nd, f["pos"], spy)
            if a is None or b is None:
                continue
            plot_rows.append(a)
            know_rows.append(b)
            gaps.append(float(f["pos"] - j))
    for lab, rows in (("as PLOTTED (bucket-open label)", plot_rows),
                      ("as KNOWABLE (bucket-last)", know_rows)):
        plt.add(lab, len(rows), len({r["ticker"] for r in rows}),
                med([r["entry_vs_low"] for r in rows]),
                pct(rate([r["near_low"] for r in rows])),
                med([r["close"] for r in rows]))
    plt.add("median sessions between the two stamps", len(gaps),
            len({r["ticker"] for r in know_rows}), med(gaps), None, None)
    plt.emit()

    # ------------------------------------------------ §R1 exemplar traces
    print("\n" + "=" * 100)
    print(f"§R1 EXEMPLAR TRACES  {TRACE_FROM} → {TRACE_TO}  (printed before any pooled number)")
    print("=" * 100)
    stop_events: dict[str, list[dict]] = {}
    if cv2 is not None:
        for t, nd in nds.items():
            try:
                stop_events[t] = confirm_events(cv2, nd.close)
            except Exception as exc:
                stop_events[t] = []
                note(f"stop lane failed on {t}: {exc}")

    for t in EXEMPLARS:
        nd = nds.get(t)
        tt = Table(f"R1.{t}", f"{t} — every lane event, chronological",
                   ["date", "lane", "detail", "close", "P_low[T-45,T]", "P_low date",
                    "entry_vs_low", "td_to_trough", "false_bounce", "MFE_42"])
        if nd is None:
            tt.add("-", "(no price series / no 3D frame)", "", None, None, "", None, None, "", None)
            tt.emit()
            continue
        rows = []
        for c in CONSTRUCTIONS:
            if t not in panel and c in STORE_LANES:
                continue
            for f in all_fires[t][c]:
                d = f["date"]
                if not (pd.Timestamp(TRACE_FROM) <= d <= pd.Timestamp(TRACE_TO)):
                    continue
                r = rule_episode(nd, f["pos"], spy) or {}
                detail = {
                    "C0": lambda f: f"{f.get('type')}/{f.get('quality')}",
                    "C1": lambda f: f"{f.get('confirm')} cross@{f.get('cross_known').date()}"
                                    + (" zero-bound" if f.get("zero_bound") else ""),
                    "C2s": lambda f: f"store label {pd.Timestamp(f['store_date']).date()}",
                    "C2r": lambda f: f"k={f['k']:.1f} d={f['d']:.1f}",
                    "C3": lambda f: f"k={f['k']:.1f} d={f['d']:.1f}",
                    "C4": lambda f: f"pivot {pd.Timestamp(f['pivot']).date()} "
                                    f"low {f['pivot_low']:.2f} d3={f['d3_at_confirm']:.1f}",
                }[c](f)
                rows.append((d, c, detail, r.get("close"), r.get("p_low"),
                             str(pd.Timestamp(r["p_low_date"]).date()) if r.get("p_low_date") is not None else "",
                             r.get("entry_vs_low"), r.get("td_to_trough"),
                             r.get("false_bounce"), r.get("mfe_42")))
        for ev in stop_events.get(t, []):
            d = ev["date"]
            if pd.Timestamp(TRACE_FROM) <= d <= pd.Timestamp(TRACE_TO):
                i = nd.pos[d]
                sr = stop_row(nd, i) or {}
                rows.append((d, "STOP", f"stop_level {ev['stop_level']:.2f}; argmin low "
                                        f"{pd.Timestamp(sr['argmin_date']).date()} "
                                        f"gap {sr.get('gap')}; "
                                        f"hist_rising={sr.get('hist_rising')} "
                                        f"m3_bull={sr.get('m3_bull')}",
                             float(nd.c[i]), None, "", None, None, "", None))
        for m in (store.get(t) or {}).get("markers", []):
            if m.get("type") not in ("sell", "cut"):
                continue
            sd = m.get("signal_date") or m.get("date")
            d = pd.Timestamp(sd)
            if pd.Timestamp(TRACE_FROM) <= d <= pd.Timestamp(TRACE_TO):
                i = nd.snap(d)
                rows.append((d, f"store-{m['type']}", f"bucket label {m.get('date')}",
                             float(nd.c[i]) if i is not None else None, None, "", None, None,
                             "", None))
        for r in sorted(rows, key=lambda x: (x[0], x[1])):
            tt.add(str(pd.Timestamp(r[0]).date()), *r[1:])
        tt.emit()

    # ------------------------------------------------ §R2 headline ruler
    def agg_block(key: str, title: str, per_name: bool, subset_fn=None, notes: str = "") -> Table:
        cols = ["lane", "episodes", "names", "near_low%", "entry_vs_low", "td_to_trough",
                "false_bounce%", "MAE_21", "survA%", "survB%", "MFE_42", "R2%",
                "fwd21", "fwd42", "ex21", "ex42", "near_low_open%"]
        tb = Table(key, title, cols, notes)
        for c in CONSTRUCTIONS:
            eps = [e for e in episodes[c] if subset_fn is None or subset_fn(e)]
            if not eps:
                tb.add(c, 0, 0, *[None] * 14)
                continue
            names = sorted({e["ticker"] for e in eps})
            if per_name:
                byn: dict[str, list[dict]] = {}
                for e in eps:
                    byn.setdefault(e["ticker"], []).append(e)
                def pn(fn, field):
                    return med([fn([x[field] for x in v]) for v in byn.values()])
                vals = [pct(pn(rate, "near_low")), pn(med, "entry_vs_low"),
                        pn(med, "td_to_trough"), pct(pn(rate, "false_bounce")),
                        pn(med, "mae_21"), pct(pn(rate, "survive_a")),
                        pct(pn(rate, "survive_b")), pn(med, "mfe_42"),
                        pct(pn(rate, "reached_2r")), pn(med, "fwd21"), pn(med, "fwd42"),
                        pn(med, "ex21"), pn(med, "ex42"), pct(pn(rate, "near_low_open"))]
            else:
                g = lambda f: [e[f] for e in eps]
                vals = [pct(rate(g("near_low"))), med(g("entry_vs_low")),
                        med(g("td_to_trough")), pct(rate(g("false_bounce"))),
                        med(g("mae_21")), pct(rate(g("survive_a"))),
                        pct(rate(g("survive_b"))), med(g("mfe_42")),
                        pct(rate(g("reached_2r"))), med(g("fwd21")), med(g("fwd42")),
                        med(g("ex21")), med(g("ex42")), pct(rate(g("near_low_open")))]
            tb.add(c, len(eps), len(names), *vals)
        return tb

    print("\n" + "=" * 100)
    print("§R2 RULER — per-name-first, then pooled (honest-N on every row)")
    print("=" * 100)
    agg_block("R2a", "PER-NAME-FIRST (per-name median/rate, then median across names)",
              True, None, "rates are medians of per-name rates; see R2c for the mean").emit()
    agg_block("R2b", "POOLED-EPISODE", False, None,
              "every episode weighted equally; survivorship-tinted outcome columns").emit()

    tc = Table("R2c", "PER-NAME-FIRST rate metrics — MEAN across names",
               ["lane", "names", "near_low%", "false_bounce%", "survA%", "survB%", "R2%"])
    for c in CONSTRUCTIONS:
        eps = episodes[c]
        byn: dict[str, list[dict]] = {}
        for e in eps:
            byn.setdefault(e["ticker"], []).append(e)
        if not byn:
            tc.add(c, 0, None, None, None, None, None)
            continue
        f = lambda k: pct(mean([rate([x[k] for x in v]) for v in byn.values()]))
        tc.add(c, len(byn), f("near_low"), f("false_bounce"), f("survive_a"),
               f("survive_b"), f("reached_2r"))
    tc.emit()

    # C1 / C1z cohort split
    tz = Table("R2d", "C1 cohort splits (confirm timing, and the C1z zero-bound subset)",
               ["cohort", "episodes", "names", "near_low%", "entry_vs_low", "td_to_trough",
                "false_bounce%", "survA%", "MFE_42", "R2%"])

    def cohort_row(label, eps):
        if not eps:
            tz.add(label, 0, 0, *[None] * 7)
            return
        g = lambda f: [e[f] for e in eps]
        tz.add(label, len(eps), len({e["ticker"] for e in eps}),
               pct(rate(g("near_low"))), med(g("entry_vs_low")), med(g("td_to_trough")),
               pct(rate(g("false_bounce"))), pct(rate(g("survive_a"))), med(g("mfe_42")),
               pct(rate(g("reached_2r"))))

    cohort_row("C1 all", episodes["C1"])
    cohort_row("C1 immediate-confirm",
               [e for e in episodes["C1"] if e["meta"].get("confirm") == "immediate"])
    cohort_row("C1 waited-confirm",
               [e for e in episodes["C1"] if e["meta"].get("confirm") == "waited"])
    cohort_row("C1z (3D %K <= 2 in prior 10 bars)", [e for e in episodes["C1"] if e["c1z"]])
    cohort_row("C1 non-zero-bound", [e for e in episodes["C1"] if not e["c1z"]])
    tz.emit()

    tcx = Table("R2e", "C1 confirm accounting + fire economics",
                ["metric", "value"])
    tcx.add("C1 3D deep crosses that never found a 1D confirm within 10 sessions "
            "(unconfirmed, NO fire; all names, all dates)", c1_unconfirmed)
    imm = [e for e in episodes["C1"] if e["meta"].get("confirm") == "immediate"]
    wai = [e for e in episodes["C1"] if e["meta"].get("confirm") == "waited"]
    tcx.add("C1 panel episodes confirmed IMMEDIATELY", len(imm))
    tcx.add("C1 panel episodes confirmed after WAITING", len(wai))
    tcx.add("median wait when waiting (sessions, panel episodes)",
            med([float(e["meta"]["wait_sessions"]) for e in wai]))
    tcx.add("deduped C1 fires across ALL names incl. add-ons (immediate / waited)",
            f"{c1_confirm_split['immediate']} / {c1_confirm_split['waited']}")
    tcx.add("median wait, all names", med([float(x) for x in c1_wait_lens]))
    tcx.emit()

    # fire rate + truncation accounting
    name_years = 0.0
    for t, nd in nds.items():
        if t in panel and nd.eval_start_pos is not None:
            name_years += max(0, len(nd.idx) - 1 - nd.eval_start_pos) / SESSIONS_PER_YEAR
    tf = Table("R2f", "Honest-N: fires, episodes, truncation and fire rate",
               ["lane", "raw fires", "episodes (deduped, in-window, priced)", "names",
                "fires/name-year", "truncated: no T+15", "truncated: <30 fwd sessions"])
    for c in CONSTRUCTIONS:
        eps = episodes[c]
        tf.add(c, raw_counts[c], len(eps), len({e["ticker"] for e in eps}),
               round(len(eps) / name_years, 4) if name_years else None,
               sum(1 for e in eps if e.get("trunc_trough")),
               sum(1 for e in eps if e.get("trunc_forward")))
    tf.emit()
    note(f"store events dropped for predating the ohlcv price root's coverage "
         f"(never relocated onto the first available bar): C0={STORE_DROPPED['C0']}, "
         f"C2s={STORE_DROPPED['C2s']}. The store is built on a ~1996+ price cache; the "
         f"adjusted ohlcv root starts ~2014, so the deep-history half of the published "
         f"marker stream is unmeasurable here and is excluded from every table.")
    note(f"panel measurable exposure = {name_years:.1f} name-years "
         f"(common window: each name scored only from the first session its recomputed 3D "
         f"lane can fire, so store lanes and recomputed lanes see the SAME window)")

    # half-split
    th = Table("R2g", "Half-split by fire date (each lane split at ITS OWN median date)",
               ["lane", "half", "median date", "episodes", "near_low%", "entry_vs_low",
                "td_to_trough", "false_bounce%", "survA%", "MFE_42", "R2%"])
    half_state = {}
    for c in CONSTRUCTIONS:
        eps = sorted(episodes[c], key=lambda e: e["date"])
        if len(eps) < 4:
            th.add(c, "-", "-", len(eps), *[None] * 7)
            continue
        mid = eps[len(eps) // 2]["date"]
        lo = [e for e in eps if e["date"] <= mid]
        hi = [e for e in eps if e["date"] > mid]
        half_state[c] = (lo, hi)
        for lab, part in (("early", lo), ("late", hi)):
            g = lambda f: [e[f] for e in part]
            th.add(c, lab, str(pd.Timestamp(mid).date()), len(part),
                   pct(rate(g("near_low"))), med(g("entry_vs_low")), med(g("td_to_trough")),
                   pct(rate(g("false_bounce"))), pct(rate(g("survive_a"))),
                   med(g("mfe_42")), pct(rate(g("reached_2r"))))
    th.emit()

    # current regime
    agg_block("R2h", f"CURRENT-REGIME CELL — episodes with T >= {CURRENT_REGIME_FROM} (pooled)",
              False, lambda e: str(pd.Timestamp(e["date"]).date()) >= CURRENT_REGIME_FROM,
              "the adjudication-coverage answer for today's regime").emit()

    # C0 coverage
    tcov = Table("R2i", "C0 coverage — share of incumbent BUY episodes with an earlier "
                        "candidate fire in the prior 30 sessions",
                 ["lane", "C0 episodes", "covered", "coverage%", "median lead (sessions)"])
    for c in ("C1", "C2r", "C3", "C4"):
        by_name: dict[str, list[int]] = {}
        for e in episodes[c]:
            by_name.setdefault(e["ticker"], []).append(e["pos"])
        cov, leads = 0, []
        for e in episodes["C0"]:
            cands = [p for p in by_name.get(e["ticker"], []) if 0 <= e["pos"] - p <= 30]
            if cands:
                cov += 1
                leads.append(float(e["pos"] - max(cands)))
        tcov.add(c, len(episodes["C0"]), cov,
                 pct(cov / len(episodes["C0"])) if episodes["C0"] else None, med(leads))
    tcov.emit()

    # ------------------------------------------------ §R3 theme-breadth lane
    print("\n" + "=" * 100)
    print("§R3 THEME-BREADTH CONDITIONING LANE")
    print("=" * 100)
    memb = json.loads(Path(args.membership).read_text())
    baskets = memb.get("baskets", {})
    basket_of: dict[str, list[str]] = {}
    for bk in sorted(baskets):
        for m in baskets[bk].get("members", []):
            basket_of.setdefault(m["ticker"], []).append(bk)
    seed = memb.get("seed_date")
    added_hist: dict = {}
    for bk in baskets.values():
        for m in bk.get("members", []):
            added_hist[m.get("added")] = added_hist.get(m.get("added"), 0) + 1
    at_seed = added_hist.get(seed, 0)
    note(f"BREADTH LANE IS TIME-BOUNDED: membership `added` is the index-inclusion mask "
         f"back-projected to seed_date={seed}, and {at_seed} of "
         f"{sum(added_hist.values())} memberships carry exactly that date. Honouring it "
         f"point-in-time means NO episode before {seed} has a live roster, so §3 and the §8 "
         f"breadth features are measured only on the post-{seed} slice of each lane "
         f"(episode counts in R3/R8 show the shortfall). This is a substrate limit, not a "
         f"null result.")
    note(f"membership.json: {len(baskets)} baskets, note={memb.get('note')!r}; "
         "rosters are CURATED WITH HINDSIGHT and 35/49 basket levels are back-projected "
         "(file's own history_note) — the breadth lane carries that flag. A name in several "
         "baskets is assigned its first basket by sorted key (deterministic).")

    breadth_cache: dict[str, dict | None] = {}

    def breadth_rec(t: str) -> dict | None:
        if t in breadth_cache:
            return breadth_cache[t]
        nd = nds.get(t)
        if nd is None:
            df, src = load_ohlc(t, price_root, stocks_root)
            if df is None or len(df) < 300:
                breadth_cache[t] = None
                return None
            nd = NameData(t, df, src)
            if not nd.ok:
                breadth_cache[t] = None
                return None
        rec = {"idx": nd.idx,
               "os": (nd.d3_daily < C1_OS_BAND).fillna(False).to_numpy(),
               "fires": np.zeros(len(nd.idx), dtype=bool)}
        for f in dedup(gen_c2r(nd)):
            rec["fires"][f["pos"]] = True
        breadth_cache[t] = rec
        return rec

    breadth_rows: dict[str, list[dict]] = {c: [] for c in ("C1", "C2r", "C3")}
    for c in ("C1", "C2r", "C3"):
        for e in episodes[c]:
            bl = basket_of.get(e["ticker"])
            if not bl:
                continue
            bk = bl[0]
            members = baskets[bk]["members"]
            T = pd.Timestamp(e["date"])
            live, hindsight = [], False
            for m in members:
                add, rem = m.get("added"), m.get("removed")
                if add and pd.Timestamp(add) > T:
                    continue
                if rem and pd.Timestamp(rem) <= T:
                    continue
                if not add:
                    hindsight = True
                live.append(m["ticker"])
            wash, turn, have = 0, 0, 0
            for mt in live:
                rec = breadth_rec(mt)
                if rec is None:
                    continue
                j = int(rec["idx"].searchsorted(T, side="right")) - 1
                if j < 0:
                    continue
                have += 1
                a = max(0, j - BREADTH_WASHOUT_BACK)
                if rec["os"][a: j + 1].any():
                    wash += 1
                b = max(0, j - BREADTH_TURN_BACK)
                if rec["fires"][b: j + 1].any():
                    turn += 1
            if have < 5:
                continue
            # written onto the episode ITSELF so the frozen parquet (and the §8 lane that
            # reads it) carry the breadth measures without recomputing the basket pass
            e["basket"] = bk
            e["members_with_data"] = have
            e["washout_breadth"] = wash / have
            e["turn_breadth"] = turn / have
            e["hindsight_roster"] = hindsight
            breadth_rows[c].append(e)

    for measure in ("washout_breadth", "turn_breadth"):
        tbr = Table(f"R3.{measure}", f"Outcome by within-construction TERCILE of {measure}",
                    ["lane", "tercile", "episodes", "names", f"{measure} range",
                     "false_bounce%", "survA%", "MFE_42"],
                    "top-vs-bottom spread printed in R3.spread; pre-stated read = "
                    ">= 10pp false-bounce spread with consistent sign across the half-split")
        spreads = {}
        for c in ("C1", "C2r", "C3"):
            rows = sorted(breadth_rows[c], key=lambda r: r[measure])
            if len(rows) < 9:
                tbr.add(c, "-", len(rows), 0, "-", None, None, None)
                continue
            n3 = len(rows) // 3
            parts = [("bottom", rows[:n3]), ("middle", rows[n3: len(rows) - n3]),
                     ("top", rows[len(rows) - n3:])]
            vals = {}
            for lab, part in parts:
                g = lambda f: [r[f] for r in part]
                fb = rate(g("false_bounce"))
                vals[lab] = fb
                tbr.add(c, lab, len(part), len({r["ticker"] for r in part}),
                        f"{part[0][measure]:.2f}-{part[-1][measure]:.2f}",
                        pct(fb), pct(rate(g("survive_a"))), med(g("mfe_42")))
            if vals.get("top") is not None and vals.get("bottom") is not None:
                spreads[c] = vals["top"] - vals["bottom"]
        tbr.emit()
        ts = Table(f"R3.spread.{measure}",
                   f"Top-vs-bottom tercile FALSE-BOUNCE spread on {measure}, "
                   "with half-split sign stability",
                   ["lane", "episodes with a basket", "names", "spread pp (top-bottom)",
                    "early-half spread pp", "late-half spread pp", "|spread| >= 10pp",
                    "sign consistent", "READ"])
        for c in ("C1", "C2r", "C3"):
            sp = spreads.get(c)
            halves = []
            rows = sorted(breadth_rows[c], key=lambda r: r[measure])
            if len(rows) >= 18:
                by_date = sorted(rows, key=lambda r: r["date"])
                mid = by_date[len(by_date) // 2]["date"]
                for part in ([r for r in rows if r["date"] <= mid],
                             [r for r in rows if r["date"] > mid]):
                    part = sorted(part, key=lambda r: r[measure])
                    n3 = len(part) // 3
                    if n3 < 2:
                        halves.append(None)
                        continue
                    hb = rate([r["false_bounce"] for r in part[:n3]])
                    ht = rate([r["false_bounce"] for r in part[len(part) - n3:]])
                    halves.append(None if hb is None or ht is None else ht - hb)
            while len(halves) < 2:
                halves.append(None)
            consistent = (None if sp is None or any(h is None for h in halves)
                          else bool(np.sign(halves[0]) == np.sign(halves[1]) != 0))
            big = None if sp is None else bool(abs(sp) >= BREADTH_SPREAD_READ)
            read = "null" if not (big and consistent) else "supported"
            ts.add(c, len(breadth_rows[c]), len({r["ticker"] for r in breadth_rows[c]}),
                   pct(sp), pct(halves[0]), pct(halves[1]), big, consistent,
                   read if sp is not None else "no data")
        ts.emit()

    # ------------------------------------------------ §R4 structure-stop lane
    print("\n" + "=" * 100)
    print("§R4 STRUCTURE-STOP CONTEXT REPLAY")
    print("=" * 100)
    stop_rows: list[dict] = []
    if cv2 is not None:
        # parity: HEAD's own warn_events must emit exactly the confirm dates we levelled
        pt = Table("R4.parity", "confirm_events (with stop_level) vs charting-app "
                                "warn_events(kind='confirm')",
                   ["names checked", "confirm dates ours", "confirm dates warn_events",
                    "identical"])
        ours = wev = 0
        same = True
        for t, nd in nds.items():
            a = {str(e["date"].date()) for e in stop_events.get(t, [])}
            b = {e["ts"] for e in cv2.warn_events(nd.close) if e["kind"] == "confirm"}
            ours += len(a)
            wev += len(b)
            same = same and (a == b)
        pt.add(len(nds), ours, wev, same)
        pt.emit()

        for t, nd in nds.items():
            for ev in stop_events.get(t, []):
                i = nd.pos.get(ev["date"])
                if i is None:
                    continue
                r = stop_row(nd, i)
                if r is None:
                    continue
                r["stop_level"] = ev["stop_level"]
                r["addon"] = t not in panel
                stop_rows.append(r)

        def stop_block(key, title, rows, splitter, labels):
            tbl = Table(key, title, ["cohort", "n", "names", "near_low_stop%",
                                     "median fwd10", "median fwd21"])
            for lab, fn in zip(labels, splitter):
                part = [r for r in rows if fn(r)]
                if not part:
                    tbl.add(lab, 0, 0, None, None, None)
                    continue
                tbl.add(lab, len(part), len({r["ticker"] for r in part}),
                        pct(rate([r["near_low_stop"] for r in part])),
                        med([r["fwd10"] for r in part]), med([r["fwd21"] for r in part]))
            tbl.emit()

        full = [r for r in stop_rows if r["full_window"] and not r["addon"]]
        full_all = [r for r in stop_rows if r["full_window"]]
        stop_block("R4a", "Structure-stop CONFIRMs — near-low audit "
                          "(full +/-10 window only)",
                   full_all, [lambda r: not r["addon"], lambda r: True, lambda r: r["addon"]],
                   ["primary panel", "panel + HL/UEC add-ons", "HL/UEC add-ons only"])
        stop_block("R4b", "split (a): 1D MACD-RSI histogram RISING at the confirm "
                          "(hist(T)>hist(T-1)>hist(T-2))",
                   full, [lambda r: r["hist_rising"], lambda r: not r["hist_rising"]],
                   ["hist rising (contradicted stop)", "hist not rising"])
        stop_block("R4c", "split (b): 3D MACD-RSI at-or-above its signal line at the confirm",
                   full, [lambda r: r["m3_bull"], lambda r: not r["m3_bull"]],
                   ["3D macd >= sig", "3D macd < sig"])
        stop_block("R4d", "joint split (a)x(b)", full,
                   [lambda r: r["hist_rising"] and r["m3_bull"],
                    lambda r: r["hist_rising"] and not r["m3_bull"],
                    lambda r: (not r["hist_rising"]) and r["m3_bull"],
                    lambda r: (not r["hist_rising"]) and not r["m3_bull"]],
                   ["hist rising & 3D bull", "hist rising & 3D bear",
                    "hist flat/falling & 3D bull", "hist flat/falling & 3D bear"])

        # named receipts
        tr = Table("R4.receipts", "Named receipt rows — STLD 2026 stops and HL 2026-07-31",
                   ["ticker", "date", "close", "stop_level", "argmin low date", "gap",
                    "near_low_stop", "hist_rising", "3D macd>=sig", "fwd10", "fwd21"])
        for r in sorted(stop_rows, key=lambda x: (x["ticker"], x["date"])):
            if r["ticker"] == "STLD" and str(pd.Timestamp(r["date"]).date()) >= "2026-01-01":
                tr.add(r["ticker"], str(pd.Timestamp(r["date"]).date()), r["close"],
                       r["stop_level"], str(pd.Timestamp(r["argmin_date"]).date()), r["gap"],
                       r["near_low_stop"], r["hist_rising"], r["m3_bull"], r["fwd10"],
                       r["fwd21"])
        hl_rows = [r for r in stop_rows if r["ticker"] == "HL"
                   and str(pd.Timestamp(r["date"]).date()) >= "2026-01-01"]
        for r in hl_rows:
            tr.add(r["ticker"], str(pd.Timestamp(r["date"]).date()), r["close"],
                   r["stop_level"], str(pd.Timestamp(r["argmin_date"]).date()), r["gap"],
                   r["near_low_stop"], r["hist_rising"], r["m3_bull"], r["fwd10"], r["fwd21"])
        tr.emit()

        # the HL 2026-07-31 receipt disagreement -> phase sweep (print BOTH, flag)
        hl = nds.get("HL")
        if hl is not None:
            got = any(str(pd.Timestamp(r["date"]).date()) == "2026-07-31" for r in hl_rows)
            tp = Table("R4.hl_phase",
                       "HL 2026-07-31 served-slice stop vs full-history recompute — "
                       "leading-history PHASE sweep of confluence_v2's 2B/3B resample",
                       ["slice", "confirm dates >= 2026-06-01", "has 2026-07-31"])
            for k in range(6):
                ev = [e for e in cv2.warn_events(hl.close.iloc[k:])
                      if e["kind"] == "confirm" and e["ts"] >= "2026-06-01"]
                tp.add(f"drop {k} leading sessions", ", ".join(e["ts"] for e in ev) or "-",
                       any(e["ts"] == "2026-07-31" for e in ev))
            for start in ("2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01",
                          "2024-01-01", "2025-01-01"):
                s = hl.close[hl.close.index >= start]
                ev = [e for e in cv2.warn_events(s)
                      if e["kind"] == "confirm" and e["ts"] >= "2026-06-01"]
                tp.add(f"slice from {start}", ", ".join(e["ts"] for e in ev) or "-",
                       any(e["ts"] == "2026-07-31" for e in ev))
            tp.emit()
            if not got:
                deviate("HL 2026-07-31 structure stop does NOT reproduce on the FULL-history "
                        "recompute (charter §4 named it as a must-appear receipt). It DOES "
                        "reproduce at other leading-history phases (R4.hl_phase). Cause: "
                        "charting-app confluence_v2._arm_event_daily still cuts its 2B/3B "
                        "bars with pandas `resample`, whose bin edges are phased to the "
                        "SERIES' FIRST timestamp — the served slice and the full history "
                        "are different grids. Both readings printed; nothing tuned.")

        # secondary: macro-store sell markers
        sell_rows = []
        for t, nd in nds.items():
            if t not in panel:
                continue
            for m in (store.get(t) or {}).get("markers", []):
                if m.get("type") != "sell":
                    continue
                sd = m.get("signal_date") or m.get("date")
                i = nd.pos.get(pd.Timestamp(sd))
                if i is None:
                    i = nd.snap(pd.Timestamp(sd))
                if i is None:
                    continue
                r = stop_row(nd, i)
                if r:
                    sell_rows.append(r)
        full_sell = [r for r in sell_rows if r["full_window"]]
        stop_block("R4e", "SECONDARY — macro-store `sell` (3D CS) markers, same near-low audit",
                   full_sell, [lambda r: True, lambda r: r["hist_rising"],
                               lambda r: not r["hist_rising"], lambda r: r["m3_bull"],
                               lambda r: not r["m3_bull"]],
                   ["all sells", "hist rising", "hist not rising", "3D macd >= sig",
                    "3D macd < sig"])
    else:
        Table("R4a", "Structure-stop lane", ["status"]).emit()

    # ------------------------------------------------ add-on exemplar episodes
    ta = Table("R5", "Add-on exemplars (HL, UEC) — recomputed lanes only, NEVER pooled",
               ["ticker", "lane", "episodes", "near_low%", "median entry_vs_low",
                "median td_to_trough", "false_bounce%", "survA%", "median MFE_42"])
    for t in addons:
        for c in RECOMPUTED_LANES:
            eps = [e for e in addon_episodes[c] if e["ticker"] == t]
            if not eps:
                ta.add(t, c, 0, *[None] * 6)
                continue
            g = lambda f: [e[f] for e in eps]
            ta.add(t, c, len(eps), pct(rate(g("near_low"))), med(g("entry_vs_low")),
                   med(g("td_to_trough")), pct(rate(g("false_bounce"))),
                   pct(rate(g("survive_a"))), med(g("mfe_42")))
    ta.emit()

    # ------------------------------------------------ freeze the episode/stop planes
    # Episode + stop detail lives in zstd parquet, NOT in the JSON: the same 36k episodes as
    # JSON key/value rows was a ~40 MB artifact, most of it repeated key names.
    out_dir = Path(args.out).resolve().parent
    ep_path = out_dir / "early_admission_bakeoff_episodes.parquet"
    st_path = out_dir / "early_admission_bakeoff_stops.parquet"
    all_eps = [e for c in CONSTRUCTIONS for e in episodes[c]] + \
              [e for c in RECOMPUTED_LANES for e in addon_episodes[c]]
    ep_df = episodes_frame(all_eps)
    ep_df.to_parquet(ep_path, compression="zstd", index=False)
    st_df = pd.DataFrame([{f: r.get(f) for f in STOP_FIELDS} for r in stop_rows])
    if not st_df.empty:
        for col in ("date", "argmin_date"):
            st_df[col] = pd.to_datetime(st_df[col], errors="coerce")
    st_df.to_parquet(st_path, compression="zstd", index=False)
    print(f"\nfroze {len(ep_df)} episodes -> {ep_path.name} "
          f"({ep_path.stat().st_size / 1e6:.2f} MB, zstd)")
    print(f"froze {len(st_df)} structure stops -> {st_path.name} "
          f"({st_path.stat().st_size / 1e6:.2f} MB, zstd)")

    # ------------------------------------------------ §8 discriminator lane
    r8: dict = {}
    if args.discriminators:
        print("\n" + "=" * 100)
        print("§R8 DURABLE-BOTTOM vs FALSE-START DISCRIMINATOR LANE (charter §8)")
        print("=" * 100)
        r8 = run_discriminators(ep_path)

    # ------------------------------------------------ deviations + notes
    print("\n" + "=" * 100)
    print("DEVIATIONS (visible, never silent)")
    print("=" * 100)
    for i, d in enumerate(DEVIATIONS, 1):
        print(f"  D{i}. {d}")
    if not DEVIATIONS:
        print("  (none)")
    print("\nNOTES")
    for i, n_ in enumerate(NOTES, 1):
        print(f"  N{i}. {n_}")

    # ------------------------------------------------ freeze
    out = {
        "study": "early_admission_bakeoff",
        "charter": "research/prophet_us_audit/EARLY_ADMISSION_BAKEOFF_2026-08-11.md",
        "tier": "measurement/display — no gate, rank, veto or engine change ships from this",
        "run_metadata": {
            "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "runtime_seconds": round(time.time() - t_start, 1),
            "argv": sys.argv[1:],
        },
        "provenance": {
            "repo_sha": git_sha(REPO),
            "signals_store_dir": str(signals_dir),
            "signals_store_files": len(store_names),
            "signals_store_origin_main_sha": git_sha(REPO, "origin/main"),
            "signals_store_last_commit_touching_it":
                git_sha(REPO, "origin/main", "site/signals"),
            "signals_store_asof_dates": sorted({d.get("asof") for d in store.values()
                                                if d.get("asof")}),
            "price_root": str(price_root),
            "stocks_fallback_root": str(stocks_root),
            "stld_last_price_date": price_meta.get("STLD", {}).get("last"),
            "spy_source": spy_src,
            "charting_app_path": str(Path(args.charting_app)),
            "charting_app_sha": charting_sha,
            "membership_path": str(Path(args.membership)),
            "membership_note": memb.get("note"),
            "membership_history_note": memb.get("history_note"),
            "membership_added_semantics": memb.get("added_semantics"),
            "membership_baskets": len(baskets),
            "anchor_era": ANCHOR_ERA,
        },
        "constants": {
            "BUCKET_N": BUCKET_N, "DEDUP_SESSIONS": DEDUP_SESSIONS,
            "C1_OS_BAND": C1_OS_BAND, "C1_ZERO_BOUND": C1_ZERO_BOUND,
            "C1_ZERO_LOOKBACK": C1_ZERO_LOOKBACK, "C1_RECENT_1D": C1_RECENT_1D,
            "C1_WAIT_MAX": C1_WAIT_MAX, "PIVOT_R": PIVOT_R,
            "LOOKBACK_LOW": LOOKBACK_LOW, "NEAR_LOW_PCT": NEAR_LOW_PCT,
            "TROUGH_FWD": TROUGH_FWD, "FALSE_BOUNCE_K": FALSE_BOUNCE_K,
            "MAE_FWD": MAE_FWD, "FWD_MAX": FWD_MAX,
            "MIN_FWD_SESSIONS": MIN_FWD_SESSIONS, "STOP_A_K": STOP_A_K,
            "STOP_B_ATR": STOP_B_ATR, "R_MULTIPLE": R_MULTIPLE,
            "BREADTH_WASHOUT_BACK": BREADTH_WASHOUT_BACK,
            "BREADTH_TURN_BACK": BREADTH_TURN_BACK,
            "BREADTH_SPREAD_READ": BREADTH_SPREAD_READ,
            "STOP_NEAR_WIN": STOP_NEAR_WIN, "STOP_NEAR_TOL": STOP_NEAR_TOL,
            "SESSIONS_PER_YEAR": SESSIONS_PER_YEAR,
            "engine_OS_band": OS, "CURRENT_REGIME_FROM": CURRENT_REGIME_FROM,
        },
        "universe": {
            "store_names": len(store_names),
            "primary_panel": sorted(t for t in nds if t in panel),
            "addon_exemplars": sorted(t for t in nds if t not in panel),
            "store_names_unpriced": unpriced,
            "panel_name_years": round(name_years, 2),
        },
        "acceptance_gates": gate,
        "deviations": DEVIATIONS,
        "notes": NOTES,
        "tables": TABLES,
        "discriminator_lane": {k: v for k, v in r8.items() if k != "labels"},
        # Episode-level detail is SPLIT OUT to zstd parquet so this JSON stays small enough
        # to read and diff; the §8 lane reads the parquet back rather than any in-memory state.
        "split_out": {
            "episodes_parquet": ep_path.name,
            "episodes_rows": int(len(ep_df)),
            "episodes_columns": list(ep_df.columns),
            "episodes_by_construction": {c: len(episodes[c]) for c in CONSTRUCTIONS},
            "addon_episodes_by_construction": {c: len(addon_episodes[c])
                                               for c in RECOMPUTED_LANES},
            "stops_parquet": st_path.name,
            "stops_rows": int(len(st_df)),
            "stops_columns": STOP_FIELDS,
            "compression": "zstd",
        },
        "price_meta": price_meta,
    }
    Path(args.out).write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwrote {args.out}  ({Path(args.out).stat().st_size / 1e6:.2f} MB)  "
          f"in {time.time() - t_start:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
