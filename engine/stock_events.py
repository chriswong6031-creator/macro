"""engine/stock_events.py — Signal Episode Atlas W1: per-name event extraction (sea.v1).

MEASUREMENT artifact — a deterministic derivation from price history.  Not a
call record; no historical row claims foresight.  Claims class-conditional base
rates only — never pre-onset winner identification (DNR §2 fingerprint Layer-3).

Program: `research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md` (§3 frozen
taxonomy, §5 statistical honesty).  Precedent: `engine/index_momentum.py` is the
same event model at INDEX grain (grids × direction × depth-pctile-at-cross ×
velocity); SEA generalises it to NAME grain and adds outcomes + conditioning.

LEGAL FENCE (the rulings this construction must not re-litigate)
---------------------------------------------------------------
Per-name OUTCOME-AUDITION tool selection is KILLED (PTT-W1a, DNR §2 row 69,
two-ruler zero-OOS) — this library never selects an indicator per name; one
frozen construction, per-name evidence enters only as n-weighted shrinkage
posteriors with all component n printed.  Era-pooled inference across the 2010
break is forbidden (DT-R16 #1751) — era column recorded, atlas cells era-split.
Sector-grain scored washout→turn is NULL (Oracle P8 P-W1/S-W3); the 2W-washout×
turn entry interaction is KILLED (#1747 Amendment-3); this artifact is
display/measurement tier with zero authority.

WHAT IT PRODUCES
----------------
  data/stock_events/events_backfill.parquet  — written ONCE by
      `scripts/backfill_stock_events.py`; FROZEN thereafter.  Holds only events
      old enough that every forward window has matured, so its outcome cells are
      complete at birth and never need rewriting (#4540: never rewrite a big
      file nightly).
  data/stock_events/live/YYYY-MM.parquet     — monthly parts holding the young
      events (those inside the maturation window at backfill time) plus every
      event since.  Appended nightly, keep-FIRST idempotent on
      (ticker, grid, date, direction); outcome cells filled in place by
      `mature_outcomes()` as their windows complete.  ONLY these small parts are
      ever rewritten.
  data/stock_events/README.md                — metadata sidecar (universe basis,
      taxonomy version, canon params snapshot).

MATH — REUSED, NEVER REIMPLEMENTED
----------------------------------
`engine.canon` only (`rsi_macd`, `stoch_rsi_kd`, `crossover`, `crossunder`,
`resample_sessions`).  `engine.technicals.rsi` is a DIFFERENT rsi (bare `ewm`
warm-up) that flips near-threshold crosses in the early history — exactly the
depth region this library reads — and must NEVER appear here.

PIT LAW
-------
Completed bars only.  Session grids (2B/3B) drop the trailing bucket when
`len(daily) % n != 0` (`index_momentum._resample_to_grid` idiom); the calendar
weekly grid drops a label that lands after the last daily bar
(`washout_turn._completed_weekly` idiom).  `depth_pctile` reads a TRAILING
window only.  Forward outcomes are filled ONLY for matured events — a partial
window is NaN with `matured=False`, never a truncated return.  Archetype labels
are PIT (last `asof_date` at-or-before the event date), falling back to
`archetype_unknown` — its own cohort, never today's label projected backward.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.canon import (  # REUSE VERBATIM — never reimplement these
    BASE_LEN,
    CONF_W,
    FAST_LEN,
    OB,
    OS,
    RSI_LEN,
    SIG_LEN,
    crossover,
    crossunder,
    resample_sessions,
    rsi_macd,
    stoch_rsi_kd,
)
from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled
# Universe + price loading are the mtf_upturn definitions (precedent:
# washout_turn / build_congress import them the same way) — one universe, one
# fallback chain, no second source of truth.
from engine.mtf_upturn import _build_universe, _load_close
# #4663 deep-history reader: prepend-only ratio-aligned splice (stocks→yahoo) so the
# depth percentile and era coverage read the name's FULL record, not the 2014-start
# preferred store. Prepend-only = recent bars (and therefore recent cross detection)
# are byte-identical to the preferred store; only pre-boundary history is added.
from engine.washout_turn import _deepen_close

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (invariant — measurement/display tier, zero authority)
# ---------------------------------------------------------------------------

AUTHORITY = {
    "tier": "display",
    "horizon_role": "context",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

TAXONOMY_VERSION = "sea.v1"

UNIVERSE_BASIS = "2026-08 basket membership — survivor-biased backfill"

# ---------------------------------------------------------------------------
# Frozen taxonomy (masterplan §3 — every axis divides n, so the axes are few)
# ---------------------------------------------------------------------------

#: (label, n_sessions | None) — "W" is the calendar W-FRI grid.  1D is excluded
#: on purpose (noise at name grain, masterplan §3).
GRIDS: tuple[str, ...] = ("2B", "3B", "W")
GRID_SESSIONS = {"2B": 2, "3B": 3}
_WEEKLY_RULE = "W-FRI"

#: Trailing depth-percentile window per grid (≈ 10 years of that grid's bars).
DEPTH_WINDOW_BARS = {"2B": 1260, "3B": 840, "W": 520}

#: Minimum finite observations before a depth percentile is meaningful.  Below
#: this the event is STILL recorded, with depth_class "unknown" — an event that
#: cannot be classified is a cohort, not a deletion.
MIN_DEPTH_OBS = 100

#: depth_class cut points (percentile of the LINE within the trailing window).
DEPTH_WASHOUT_MAX = 15.0
DEPTH_DEEP_MAX = 30.0
DEPTH_MID_MAX = 70.0

#: washout_len_class cut points, in completed bars since the line was last ≥ 0.
WASHOUT_SHORT_MAX = 8      # short = < 8
WASHOUT_MEDIUM_MAX = 26    # medium = 8..26 ; long = > 26

#: Histogram velocity lag (IHM `hist_vel3`).
HIST_VEL_LAG = 3

#: Drawdown receipt lookback, in DAILY sessions.
DD_LOOKBACK_SESSIONS = 252

#: Forward horizons.  W grid → completed WEEKLY bars; 2B/3B → DAILY sessions
#: after the event date (the session grids' own bars are not a natural horizon).
FWD_W_SHORT, FWD_W_LONG = 13, 26
FWD_S_SHORT, FWD_S_LONG = 21, 63

#: The era break DT-R16 (#1751) forbids pooling across.
ERA_BREAK = pd.Timestamp("2010-01-01")

#: Regime stamps mirror `engine/oracle/memory.py` (`_regime_bucket`, cfg
#: `regime_vix_threshold`) so the vocabulary is shared across programs.
REGIME_VIX_THRESHOLD = 0.6
REGIME_VIX_WINDOW = 252 * 10
REGIME_VIX_MIN_OBS = 250
REGIME_SPY_MA = 200

#: Maturation window: an event older than this has every forward window closed,
#: so it can be frozen into the backfill file.  26 weeks is the longest horizon.
MATURITY_DAYS = 26 * 7

#: Minimum daily bars before a name is read at all (mtf_upturn's floor is the
#: loader's; this is the extractor's own).
MIN_DAILY_BARS = 260

#: Canon params actually consumed — snapshotted into the metadata sidecar so a
#: param drift in canon is visible in the shipped artifact.
CANON_PARAMS = {
    "rsi_len": RSI_LEN,
    "macd_fast": FAST_LEN,
    "macd_slow": BASE_LEN,
    "macd_signal": SIG_LEN,
    "ob": OB,
    "os": OS,
    "conf_w": CONF_W,
    "grids": list(GRIDS),
    "weekly_rule": _WEEKLY_RULE,
    "depth_window_bars": dict(DEPTH_WINDOW_BARS),
}

#: Parquet schema — declared explicitly so an EMPTY frame still round-trips with
#: the right columns (a schema that only exists when rows exist is a schema that
#: drifts).
EVENT_COLUMNS: tuple[str, ...] = (
    "ticker", "grid", "date", "direction", "era",
    "depth_pctile", "depth_window_n", "depth_class", "level",
    "washout_len", "washout_len_class", "align_class",
    "hist_vel3", "stoch_k", "stoch_d", "drawdown_pct", "close", "line", "sig",
    "archetype_at_event", "sector",
    "regime_vix_pctile", "regime_spy_above_200d", "regime_bucket",
    "fwd_13w", "fwd_26w", "fwd_21s", "fwd_63s",
    "exc_13w", "exc_26w", "exc_21s", "exc_63s",
    "matured_short", "matured",
)

KEY_COLS: tuple[str, ...] = ("ticker", "grid", "date", "direction")

#: Outcome cells maturation may fill in place (nothing else is ever rewritten).
OUTCOME_COLS: tuple[str, ...] = (
    "fwd_13w", "fwd_26w", "fwd_21s", "fwd_63s",
    "exc_13w", "exc_26w", "exc_21s", "exc_63s",
    "matured_short", "matured",
)

_DIR = "stock_events"
_BACKFILL_FILE = "events_backfill.parquet"
_LIVE_DIR = "live"


# ---------------------------------------------------------------------------
# Grid construction (PIT: completed bars only)
# ---------------------------------------------------------------------------

def grid_series(close: pd.Series, grid: str) -> pd.Series | None:
    """Resample ``close`` to ``grid``, keeping COMPLETED bars only.

    2B/3B use the session-GROUPED resampler (canon) and drop the trailing bucket
    when the session count is not an exact multiple of n — that bucket is still
    accumulating (`index_momentum._resample_to_grid`).  W uses the calendar
    W-FRI resample and drops a label dated after the last daily bar — that week
    is still open (`washout_turn._completed_weekly`).
    """
    s = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    if s.empty:
        return None
    if grid == "W":
        wk = s.resample(_WEEKLY_RULE).last().dropna()
        if len(wk) and wk.index[-1].date() > s.index[-1].date():
            wk = wk.iloc[:-1]
        return wk if len(wk) else None
    n = GRID_SESSIONS.get(grid)
    if n is None:
        return None
    bucketed, _known = resample_sessions(s, n)
    if len(bucketed) and int(s.count()) % n != 0:
        bucketed = bucketed.iloc[:-1]
    return bucketed if len(bucketed) else None


def _line_sig(bars: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Canon RSI-MACD line/signal on a grid series, warm-up NaNs dropped."""
    line_raw, sig_raw = rsi_macd(bars)
    ok = line_raw.notna() & sig_raw.notna()
    return line_raw[ok], sig_raw[ok]


# ---------------------------------------------------------------------------
# Class axes
# ---------------------------------------------------------------------------

def depth_pctile(line_vals: np.ndarray, i: int, window: int) -> tuple[float | None, int]:
    """Strictly-less-than rank of ``line_vals[i]`` within the TRAILING window.

    Returns ``(pctile | None, n_obs)``.  The window ENDS at i (inclusive) — a
    percentile that could see bars after the event would be look-ahead, which is
    the one thing an episode library may never do (masterplan §5).  Fewer than
    ``MIN_DEPTH_OBS`` finite observations → ``None`` (class "unknown").
    """
    lo = max(0, i - window + 1)
    w = line_vals[lo:i + 1]
    w = w[np.isfinite(w)]
    cur = line_vals[i]
    if len(w) < MIN_DEPTH_OBS or not np.isfinite(cur):
        return None, int(len(w))
    return 100.0 * float((w < cur).sum()) / len(w), int(len(w))


def depth_class(pctile: float | None) -> str:
    """washout ≤15 · deep (15,30] · mid (30,70] · high >70 · unknown."""
    if pctile is None or not np.isfinite(pctile):
        return "unknown"
    if pctile <= DEPTH_WASHOUT_MAX:
        return "washout"
    if pctile <= DEPTH_DEEP_MAX:
        return "deep"
    if pctile <= DEPTH_MID_MAX:
        return "mid"
    return "high"


def washout_len(line_vals: np.ndarray, i: int) -> int:
    """Completed bars since the line was last ≥ 0 (0 when the line is ≥ 0 now).

    A line that has never been ≥ 0 inside the available history returns i+1 —
    the whole readable span — rather than a null: "at least this long" is the
    honest read, and the class buckets saturate at "long" anyway.
    """
    cur = line_vals[i]
    if not np.isfinite(cur) or cur >= 0.0:
        return 0
    for k in range(i - 1, -1, -1):
        v = line_vals[k]
        if np.isfinite(v) and v >= 0.0:
            return i - k
    return i + 1


def washout_len_class(n_bars: int, level: str) -> str:
    """short <8 · medium 8–26 · long >26 · na (above_zero has no washout run)."""
    if level == "above_zero":
        return "na"
    if n_bars < WASHOUT_SHORT_MAX:
        return "short"
    if n_bars <= WASHOUT_MEDIUM_MAX:
        return "medium"
    return "long"


def _era(ts: pd.Timestamp) -> str:
    """DT-R16 (#1751): the 2010 regime break is never pooled across silently."""
    return "pre2010" if pd.Timestamp(ts) < ERA_BREAK else "post2010"


def regime_bucket(vix_pctile: float | None, spy_above_200d: float | bool | None) -> str:
    """Four-bucket regime label — SAME semantics as `oracle.memory._regime_bucket`.

    hi/lo vix × above/below 200d, with an ``any_*`` half when one side is null.
    Both null → "regime_unknown" (the oracle's "unknown", named for this library
    so a regime column is never confused with a missing archetype).
    """
    vix_hi: bool | None = None
    if vix_pctile is not None and np.isfinite(float(vix_pctile)):
        vix_hi = float(vix_pctile) >= REGIME_VIX_THRESHOLD
    spy_hi: bool | None = None
    if spy_above_200d is not None and np.isfinite(float(spy_above_200d)):
        spy_hi = bool(float(spy_above_200d) >= 0.5)
    if vix_hi is None and spy_hi is None:
        return "regime_unknown"
    vix_label = ("hi_vix" if vix_hi else "lo_vix") if vix_hi is not None else "any_vix"
    spy_label = ("above200" if spy_hi else "below200") if spy_hi is not None else "any_spy"
    return f"{vix_label}_{spy_label}"


# ---------------------------------------------------------------------------
# Extraction context — market-wide series loaded ONCE per pass
# ---------------------------------------------------------------------------

@dataclass
class ExtractContext:
    """Market-wide inputs shared by every name in a pass.

    All fields are optional: an empty context yields events with null excess
    returns, null regime stamps and ``archetype_unknown`` — a degraded but
    HONEST row, never a crash.  Tests build one from synthetic series.
    """

    spy_daily: pd.Series | None = None
    spy_weekly: pd.Series | None = None
    vix_pctile: pd.Series | None = None          # fraction 0..1, oracle semantics
    spy_above_200d: pd.Series | None = None      # 1.0/0.0 on SPY's daily index
    archetypes: dict[str, tuple[np.ndarray, list[str]]] = field(default_factory=dict)

    @classmethod
    def build(cls, data_root: Path | None = None) -> "ExtractContext":
        spy = _load_close("SPY", data_root)
        if spy is not None:
            spy = _deepen_close("SPY", spy, data_root)
        spy_wk = grid_series(spy, "W") if spy is not None else None
        above = None
        if spy is not None and len(spy) >= REGIME_SPY_MA:
            ma = spy.rolling(REGIME_SPY_MA, min_periods=REGIME_SPY_MA).mean()
            above = (spy > ma).astype(float).where(ma.notna())
        return cls(
            spy_daily=spy,
            spy_weekly=spy_wk,
            vix_pctile=_load_vix_pctile(data_root),
            spy_above_200d=above,
            archetypes=_load_archetype_index(data_root),
        )


def _load_vix_pctile(data_root: Path | None = None) -> pd.Series | None:
    """VIX close percentile vs its trailing 252×10 sessions, as a FRACTION 0..1.

    Fraction (not 0-100) on purpose: `oracle.memory._regime_bucket` compares
    against ``regime_vix_threshold = 0.6``, and one vocabulary written twice
    cures in one place only if the UNITS match too.  Null before ~1990 (the VIX
    store starts 1990-01-02) and until MIN_OBS observations exist.
    """
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    p = root / "yahoo" / "_VIX.parquet"
    if not p.exists():
        p = config.ROOT / "data" / "yahoo" / "_VIX.parquet"
    if not p.exists():
        log.debug("stock_events: _VIX.parquet absent — regime_vix_pctile null")
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        col = "close" if "close" in df.columns else "close_price"
        s = pd.to_numeric(df[col], errors="coerce").dropna().sort_index()
    except Exception as e:  # noqa: BLE001 — a missing regime stamp is a null, not a crash
        log.warning("stock_events: VIX load failed (%s) — regime stamps null", e)
        return None
    v = s.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        lo = max(0, i - REGIME_VIX_WINDOW + 1)
        w = v[lo:i + 1]
        if len(w) >= REGIME_VIX_MIN_OBS:
            out[i] = float((w < v[i]).sum()) / len(w)
    return pd.Series(out, index=s.index)


def _load_archetype_index(
    data_root: Path | None = None,
) -> dict[str, tuple[np.ndarray, list[str]]]:
    """PIT archetype lookup: {ticker: (asof_dates ascending, archetype labels)}.

    Reads the FROZEN `data/archetypes/history.parquet` artifact rather than
    calling `stock_fundamentals.archetypes_history()`, which REBUILDS the panel
    and writes to `data/` — a rebuild has no place on a nightly extraction path
    and would make an off-lane run write data.  Absent file / absent ticker →
    the caller stamps "archetype_unknown", a real cohort (masterplan §5).
    """
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    p = root / "archetypes" / "history.parquet"
    if not p.exists():
        log.info("stock_events: archetypes/history.parquet absent — all rows archetype_unknown")
        return {}
    try:
        df = pd.read_parquet(p, columns=["ticker", "asof_date", "archetype"])
    except Exception as e:  # noqa: BLE001
        log.warning("stock_events: archetype history load failed (%s)", e)
        return {}
    df = df.dropna(subset=["ticker", "asof_date"]).sort_values("asof_date")
    out: dict[str, tuple[np.ndarray, list[str]]] = {}
    for tk, g in df.groupby("ticker", sort=False):
        labels = [
            str(a) if isinstance(a, str) and a else "archetype_unknown"
            for a in g["archetype"].tolist()
        ]
        out[str(tk)] = (pd.to_datetime(g["asof_date"]).to_numpy(), labels)
    return out


def _archetype_at(
    ctx: ExtractContext | None, ticker: str, when: pd.Timestamp
) -> str:
    """Last archetype label whose asof_date is at-or-before ``when`` (PIT)."""
    if ctx is None:
        return "archetype_unknown"
    entry = ctx.archetypes.get(ticker)
    if not entry:
        return "archetype_unknown"
    dates, labels = entry
    pos = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(when)), side="right")) - 1
    if pos < 0:
        return "archetype_unknown"
    return labels[pos]


def _at_or_before(series: pd.Series | None, when: pd.Timestamp) -> float | None:
    """Value of ``series`` on the last index at-or-before ``when`` (no look-ahead)."""
    if series is None or len(series) == 0:
        return None
    pos = int(series.index.searchsorted(pd.Timestamp(when), side="right")) - 1
    if pos < 0:
        return None
    v = series.iloc[pos]
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


# ---------------------------------------------------------------------------
# Forward outcomes — matured only, NEVER a partial window
# ---------------------------------------------------------------------------

def _fwd_return(vals: np.ndarray, i: int, h: int) -> float | None:
    """``vals[i+h]/vals[i] - 1`` or None when the window has not closed."""
    if i < 0 or i + h >= len(vals):
        return None
    a, b = vals[i], vals[i + h]
    if not (np.isfinite(a) and np.isfinite(b)) or a <= 0:
        return None
    return float(b / a - 1.0)


def _bench_fwd(bench: pd.Series | None, when: pd.Timestamp, h: int) -> float | None:
    """Same-window benchmark return anchored at the last bench bar ≤ ``when``."""
    if bench is None or len(bench) == 0:
        return None
    pos = int(bench.index.searchsorted(pd.Timestamp(when), side="right")) - 1
    if pos < 0:
        return None
    return _fwd_return(bench.to_numpy(dtype=float), pos, h)


def _excess(own: float | None, bench: float | None) -> float | None:
    """Excess vs benchmark — null unless BOTH legs matured (no half-filled cell)."""
    if own is None or bench is None:
        return None
    return float(own - bench)


# ---------------------------------------------------------------------------
# Per-symbol extraction
# ---------------------------------------------------------------------------

def extract_symbol_events(
    ticker: str,
    close: pd.Series,
    *,
    basket_ids: list[str] | None = None,
    ctx: ExtractContext | None = None,
) -> list[dict]:
    """Every canon RSI-MACD cross event (bull + bear) on the three frozen grids.

    Pure: reads only its arguments.  Never raises on a well-formed close series.
    """
    daily = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    if len(daily) < MIN_DAILY_BARS:
        return []
    sector = (basket_ids or ["sector_unknown"])[0] if basket_ids else "sector_unknown"

    # --- per-grid frames (needed by every grid's align_class) ---------------
    frames: dict[str, dict[str, Any]] = {}
    for g in GRIDS:
        bars = grid_series(daily, g)
        if bars is None or len(bars) < MIN_DEPTH_OBS:
            continue
        line, sig = _line_sig(bars)
        if len(line) < HIST_VEL_LAG + 2:
            continue
        hist = line - sig
        k_raw, d_raw = stoch_rsi_kd(bars)
        frames[g] = {
            "bars": bars.reindex(line.index),
            "line": line,
            "sig": sig,
            "hist": hist,
            "vel": hist - hist.shift(HIST_VEL_LAG),
            "k": k_raw.reindex(line.index),
            "d": d_raw.reindex(line.index),
            # definite-True alignment mask: NaN legs stay NaN, never a silent False
            "bull_state": (line > sig).where(line.notna() & sig.notna()),
        }
    if not frames:
        return []

    daily_vals = daily.to_numpy(dtype=float)
    dd_roll = daily.rolling(DD_LOOKBACK_SESSIONS, min_periods=20).max()
    events: list[dict] = []

    for g, fr in frames.items():
        line, sig = fr["line"], fr["sig"]
        line_vals = line.to_numpy(dtype=float)
        bar_vals = fr["bars"].to_numpy(dtype=float)
        window = DEPTH_WINDOW_BARS[g]
        bull = crossover(line, sig)
        bear = crossunder(line, sig)
        weekly = g == "W"
        h_short, h_long = (FWD_W_SHORT, FWD_W_LONG) if weekly else (FWD_S_SHORT, FWD_S_LONG)

        for direction, mask in (("bull", bull), ("bear", bear)):
            for i in np.flatnonzero(mask.to_numpy()):
                i = int(i)
                when = pd.Timestamp(line.index[i])
                pct, n_obs = depth_pctile(line_vals, i, window)
                lv = line_vals[i]
                level = "above_zero" if (np.isfinite(lv) and lv >= 0.0) else "below_zero"
                wl = washout_len(line_vals, i)

                # align_class — the OTHER grids' bull state on their own last
                # completed bar at-or-before this event date; only definite
                # Trues count (a NaN leg is not an aligned leg).
                align = 0
                for og, ofr in frames.items():
                    if og == g:
                        continue
                    v = _at_or_before(ofr["bull_state"], when)
                    if v is not None and v >= 0.5:
                        align += 1

                # --- outcomes: matured only ---------------------------------
                if weekly:
                    own_s = _fwd_return(bar_vals, i, h_short)
                    own_l = _fwd_return(bar_vals, i, h_long)
                    bench_s = _bench_fwd(ctx.spy_weekly if ctx else None, when, h_short)
                    bench_l = _bench_fwd(ctx.spy_weekly if ctx else None, when, h_long)
                else:
                    dpos = int(daily.index.searchsorted(when, side="right")) - 1
                    own_s = _fwd_return(daily_vals, dpos, h_short)
                    own_l = _fwd_return(daily_vals, dpos, h_long)
                    bench_s = _bench_fwd(ctx.spy_daily if ctx else None, when, h_short)
                    bench_l = _bench_fwd(ctx.spy_daily if ctx else None, when, h_long)

                vix_p = _at_or_before(ctx.vix_pctile if ctx else None, when)
                spy_ab = _at_or_before(ctx.spy_above_200d if ctx else None, when)
                dd = _at_or_before(dd_roll, when)
                close_at = float(bar_vals[i]) if np.isfinite(bar_vals[i]) else None

                row = {
                    "ticker": ticker,
                    "grid": g,
                    "date": when,
                    "direction": direction,
                    "era": _era(when),
                    "depth_pctile": _r(pct, 2),
                    "depth_window_n": n_obs,
                    "depth_class": depth_class(pct),
                    "level": level,
                    "washout_len": int(wl),
                    "washout_len_class": washout_len_class(int(wl), level),
                    "align_class": int(align),
                    "hist_vel3": _r(_iloc(fr["vel"], i), 4),
                    "stoch_k": _r(_iloc(fr["k"], i), 2),
                    "stoch_d": _r(_iloc(fr["d"], i), 2),
                    "drawdown_pct": (
                        _r((close_at / dd - 1.0) * 100.0, 2)
                        if (close_at and dd and dd > 0) else None
                    ),
                    "close": _r(close_at, 4),
                    "line": _r(lv, 4),
                    "sig": _r(_iloc(sig, i), 4),
                    "archetype_at_event": _archetype_at(ctx, ticker, when),
                    "sector": sector,
                    "regime_vix_pctile": _r(vix_p, 4),
                    "regime_spy_above_200d": (None if spy_ab is None else bool(spy_ab >= 0.5)),
                    "regime_bucket": regime_bucket(vix_p, spy_ab),
                    "fwd_13w": None, "fwd_26w": None, "fwd_21s": None, "fwd_63s": None,
                    "exc_13w": None, "exc_26w": None, "exc_21s": None, "exc_63s": None,
                    "matured_short": own_s is not None,
                    "matured": own_l is not None,
                }
                if weekly:
                    row["fwd_13w"], row["fwd_26w"] = _r(own_s, 6), _r(own_l, 6)
                    row["exc_13w"] = _r(_excess(own_s, bench_s), 6)
                    row["exc_26w"] = _r(_excess(own_l, bench_l), 6)
                else:
                    row["fwd_21s"], row["fwd_63s"] = _r(own_s, 6), _r(own_l, 6)
                    row["exc_21s"] = _r(_excess(own_s, bench_s), 6)
                    row["exc_63s"] = _r(_excess(own_l, bench_l), 6)
                events.append(row)
    return events


def _iloc(s: pd.Series, i: int) -> float | None:
    try:
        f = float(s.iloc[i])
    except (TypeError, ValueError, IndexError):
        return None
    return f if np.isfinite(f) else None


def _r(v: Any, nd: int) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if np.isfinite(f) else None


def events_frame(rows: list[dict]) -> pd.DataFrame:
    """Rows → a DataFrame with the FROZEN column set (stable even when empty)."""
    df = pd.DataFrame(rows, columns=list(EVENT_COLUMNS))
    if df.empty:
        df = df.astype({"date": "datetime64[ns]"})
        # A nullable bool even when empty: an object-dtype column of None/True
        # round-trips through parquet differently on an empty vs a populated
        # write, and a schema that only exists when rows exist is one that drifts.
        df["regime_spy_above_200d"] = df["regime_spy_above_200d"].astype("boolean")
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    for c in ("matured", "matured_short"):
        df[c] = df[c].fillna(False).astype(bool)
    df["regime_spy_above_200d"] = df["regime_spy_above_200d"].astype("boolean")
    return df.sort_values(list(KEY_COLS)).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Full-universe extraction
# ---------------------------------------------------------------------------

def extract_universe(
    data_root: Path | None = None,
    *,
    ctx: ExtractContext | None = None,
    universe: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """Extract every event for the whole US organ universe.  Never raises."""
    t0 = time.time()
    uni = universe if universe is not None else _build_universe(data_root)
    context = ctx if ctx is not None else ExtractContext.build(data_root)
    rows: list[dict] = []
    n_names = n_skipped = 0
    for sym, basket_ids in sorted(uni.items()):
        close = _load_close(sym, data_root)
        if close is None:
            n_skipped += 1
            continue
        close = _deepen_close(sym, close, data_root)
        try:
            got = extract_symbol_events(sym, close, basket_ids=basket_ids, ctx=context)
        except Exception as e:  # noqa: BLE001 — one bad name never kills the pass
            log.debug("stock_events: %s extraction failed: %s", sym, e)
            n_skipped += 1
            continue
        if got:
            n_names += 1
            rows.extend(got)
        else:
            n_skipped += 1
    df = events_frame(rows)
    log.info(
        "stock_events: extracted %d events over %d names (%d skipped) in %.1fs",
        len(df), n_names, n_skipped, time.time() - t0,
    )
    return df


# ---------------------------------------------------------------------------
# Storage — a frozen backfill + small monthly live parts (#4540)
# ---------------------------------------------------------------------------

def events_dir(data_root: Path | None = None) -> Path:
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    return root / _DIR


def backfill_path(data_root: Path | None = None) -> Path:
    return events_dir(data_root) / _BACKFILL_FILE


def live_dir(data_root: Path | None = None) -> Path:
    return events_dir(data_root) / _LIVE_DIR


def split_cutoff(asof: pd.Timestamp | date | str) -> pd.Timestamp:
    """Backfill/live boundary: events strictly OLDER than this are frozen.

    An event this old has every forward window closed, so its outcome cells are
    complete at write time — which is what lets the backfill file be written
    once and never rewritten.  Younger events are seeded into the live parts,
    where maturation fills them as their windows complete.  ONE maturation path,
    only small files ever rewritten.
    """
    return pd.Timestamp(asof).normalize() - pd.Timedelta(days=MATURITY_DAYS)


def write_backfill(
    df: pd.DataFrame, data_root: Path | None = None, *, overwrite: bool = False
) -> Path:
    """Write the FROZEN backfill parquet (refuses to clobber unless overwrite)."""
    p = backfill_path(data_root)
    if p.exists() and not overwrite:
        raise FileExistsError(
            f"{p} already exists — the backfill file is frozen after its one write; "
            "pass overwrite=True only for a deliberate re-derivation"
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    _to_parquet_with_metadata(df, p)
    return p


def _to_parquet_with_metadata(df: pd.DataFrame, path: Path) -> None:
    """Parquet write carrying the honesty metadata in the schema itself."""
    meta = {
        b"universe_basis": UNIVERSE_BASIS.encode(),
        b"taxonomy_version": TAXONOMY_VERSION.encode(),
        b"canon_params": json.dumps(CANON_PARAMS, sort_keys=True).encode(),
        b"tier": b"display",
        b"masterplan": b"research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md",
    }
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.Table.from_pandas(df, preserve_index=False)
        existing = table.schema.metadata or {}
        table = table.replace_schema_metadata({**existing, **meta})
        pq.write_table(table, path)
    except Exception as e:  # noqa: BLE001 — metadata is a bonus, the data is not
        log.debug("stock_events: pyarrow metadata write failed (%s) — plain parquet", e)
        df.to_parquet(path, index=False)


def _part_path(data_root: Path | None, month: str) -> Path:
    return live_dir(data_root) / f"{month}.parquet"


def append_live_events(
    df: pd.DataFrame,
    data_root: Path | None = None,
    *,
    require_nightly_lane: bool = True,
) -> int:
    """Append events into monthly live parts.  Keep-FIRST idempotent on KEY_COLS.

    Gated by `engine.ledger_lane.nightly_advance_enabled()` exactly like
    `washout_turn._stamp_ledger`: an intraday/off-lane run computes and
    DISCARDS.  ``require_nightly_lane=False`` is the one-shot backfill seeding
    path (`scripts/backfill_stock_events.py`), which is operator-invoked off the
    render path — the only sanctioned bypass.
    """
    if require_nightly_lane and not _ledger_advance_enabled():
        log.debug("stock_events.append_live_events: skipped (COLLECT_LANE != nightly)")
        return 0
    if df is None or df.empty:
        return 0
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    appended = 0
    for month, part in out.groupby(out["date"].dt.strftime("%Y-%m"), sort=True):
        p = _part_path(data_root, str(month))
        p.parent.mkdir(parents=True, exist_ok=True)
        new = part.reindex(columns=list(EVENT_COLUMNS))
        if p.exists():
            try:
                old = pd.read_parquet(p)
                old["date"] = pd.to_datetime(old["date"]).dt.normalize()
            except Exception as e:  # noqa: BLE001
                log.warning("stock_events: live part %s unreadable (%s) — rewritten", p, e)
                old = pd.DataFrame(columns=list(EVENT_COLUMNS))
            before = len(old)
            combined = pd.concat([old, new], ignore_index=True)
            combined = combined.drop_duplicates(subset=list(KEY_COLS), keep="first")
            gained = len(combined) - before
            if gained <= 0:
                continue  # nothing new — do not rewrite the part at all
            appended += gained
        else:
            combined = new.drop_duplicates(subset=list(KEY_COLS), keep="first")
            appended += len(combined)
        combined = combined.sort_values(list(KEY_COLS)).reset_index(drop=True)
        _to_parquet_with_metadata(combined, p)
    return appended


def mature_outcomes(
    fresh: pd.DataFrame | None = None,
    data_root: Path | None = None,
    *,
    require_nightly_lane: bool = True,
) -> int:
    """Fill newly-matured NaN outcome cells IN THE LIVE PARTS ONLY.

    The backfill file is frozen with complete outcomes by construction (every
    row in it is older than the maturation window), so it is never opened here.
    Only outcome columns are touched; class axes and receipts are immutable once
    written.  Returns the number of CELLS filled.
    """
    if require_nightly_lane and not _ledger_advance_enabled():
        log.debug("stock_events.mature_outcomes: skipped (COLLECT_LANE != nightly)")
        return 0
    d = live_dir(data_root)
    if not d.exists():
        return 0
    if fresh is None:
        fresh = extract_universe(data_root)
    if fresh is None or fresh.empty:
        return 0
    src = fresh.copy()
    src["date"] = pd.to_datetime(src["date"]).dt.normalize()
    # A duplicate key would make the reindex below RAISE and take the whole
    # nightly maturation with it; the extractor cannot produce one (crossover
    # and crossunder are mutually exclusive on a bar), so this is a cheap fence
    # around a caller-supplied frame, not a known defect.
    src = src.drop_duplicates(subset=list(KEY_COLS), keep="last").set_index(list(KEY_COLS))
    filled = 0
    for p in sorted(d.glob("*.parquet")):
        try:
            part = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            log.warning("stock_events: live part %s unreadable (%s) — skipped", p, e)
            continue
        part["date"] = pd.to_datetime(part["date"]).dt.normalize()
        idx = pd.MultiIndex.from_frame(part[list(KEY_COLS)])
        part_filled = 0
        for col in OUTCOME_COLS:
            if col not in src.columns or col not in part.columns:
                continue
            new_vals = src[col].reindex(idx).to_numpy()
            cur = part[col].to_numpy()
            if col in ("matured", "matured_short"):
                # A maturity FLAG only ever turns on (an outcome never un-matures).
                turn_on = np.array([bool(v) is True for v in new_vals]) & ~np.array(
                    [bool(v) is True for v in cur]
                )
                if turn_on.any():
                    part.loc[turn_on, col] = True
                    part_filled += int(turn_on.sum())
                continue
            missing = pd.isna(cur) & ~pd.isna(new_vals)
            if missing.any():
                part.loc[missing, col] = new_vals[missing]
                part_filled += int(missing.sum())
        if part_filled:
            part[["matured", "matured_short"]] = part[["matured", "matured_short"]].fillna(False)
            _to_parquet_with_metadata(
                part.sort_values(list(KEY_COLS)).reset_index(drop=True), p
            )
            filled += part_filled
    return filled


def load_events(data_root: Path | None = None) -> pd.DataFrame:
    """Concat the frozen backfill + every live part.  Empty frame when absent."""
    parts: list[pd.DataFrame] = []
    bp = backfill_path(data_root)
    if bp.exists():
        try:
            parts.append(pd.read_parquet(bp))
        except Exception as e:  # noqa: BLE001
            log.warning("stock_events: backfill unreadable (%s)", e)
    d = live_dir(data_root)
    if d.exists():
        for p in sorted(d.glob("*.parquet")):
            try:
                parts.append(pd.read_parquet(p))
            except Exception as e:  # noqa: BLE001
                log.warning("stock_events: live part %s unreadable (%s)", p, e)
    if not parts:
        return events_frame([])
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.drop_duplicates(subset=list(KEY_COLS), keep="last")
    return df.sort_values(list(KEY_COLS)).reset_index(drop=True)


def write_metadata_sidecar(
    data_root: Path | None = None, *, extra: dict | None = None
) -> Path:
    """`data/stock_events/README.md` — the honesty metadata in human form."""
    d = events_dir(data_root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "README.md"
    body = [
        "# data/stock_events — Signal Episode Atlas event library",
        "",
        f"- taxonomy_version: `{TAXONOMY_VERSION}`",
        f"- universe_basis: `{UNIVERSE_BASIS}`",
        "- tier: display / MEASUREMENT. Authority block all-false — this library",
        "  ranks nothing, gates nothing, sizes nothing, escalates nothing.",
        "- program: `research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md`",
        "",
        "## Files",
        "",
        "- `events_backfill.parquet` — written ONCE by",
        "  `python -m scripts.backfill_stock_events --run`; FROZEN thereafter.",
        "  Contains only events older than the 26-week maturation window, so every",
        "  outcome cell is complete at write time.",
        "- `live/YYYY-MM.parquet` — monthly parts. Appended nightly (keep-first on",
        "  `(ticker, grid, date, direction)`); outcome cells filled in place by",
        "  `mature_outcomes()`. Only these small parts are ever rewritten.",
        "",
        "## Honesty",
        "",
        "- Survivorship: the universe is TODAY's basket membership, so the",
        "  backfilled history inherits survivorship. Widening to the full panel is",
        "  a later, separately-adjudicated step.",
        "- Clustering: events overlap in time within and across names. Cells print",
        "  `n_distinct_years` beside `n`; promotion-grade inference is",
        "  pre-specified as date-blocked bootstrap, never pooled t on raw events.",
        "- Era: DT-R16 (#1751) forbids pooling across the 2010 regime break — every",
        "  row carries `era`, and atlas cells report pooled AND post2010.",
        "- No look-ahead: `depth_pctile` reads a trailing window only; forward",
        "  outcomes exist only for matured events; archetype labels are PIT.",
        "",
        "## Canon parameter snapshot",
        "",
        "```json",
        json.dumps(CANON_PARAMS, indent=2, sort_keys=True),
        "```",
    ]
    if extra:
        body += ["", "## Build stamp", "", "```json",
                 json.dumps(extra, indent=2, sort_keys=True, default=str), "```"]
    p.write_text("\n".join(body) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Nightly path
# ---------------------------------------------------------------------------

def nightly_update(data_root: Path | None = None) -> dict:
    """Nightly: extract → append new live rows → fill newly-matured outcomes.

    Off the nightly lane this computes and DISCARDS (no `data/` write), exactly
    like every other forward-ledger organ.  Never raises.
    """
    t0 = time.time()
    out: dict[str, Any] = {
        "extracted": 0, "appended": 0, "matured_filled": 0,
        "written": _ledger_advance_enabled(), "elapsed_s": 0.0,
    }
    try:
        fresh = extract_universe(data_root)
        out["extracted"] = int(len(fresh))
        if not fresh.empty:
            cutoff = _live_boundary(data_root, fresh)
            young = fresh[fresh["date"] > cutoff]
            out["live_boundary"] = str(pd.Timestamp(cutoff).date())
            out["appended"] = append_live_events(young, data_root)
            out["matured_filled"] = mature_outcomes(fresh, data_root)
    except Exception as e:  # noqa: BLE001 — additive organ, never fatal
        log.warning("stock_events.nightly_update failed: %s", e)
        out["error"] = str(e)
    out["elapsed_s"] = round(time.time() - t0, 2)
    return out


def _live_boundary(data_root: Path | None, fresh: pd.DataFrame) -> pd.Timestamp:
    """The date above which events belong to the LIVE parts.

    Derived from the frozen backfill's own max date, so there is no second piece
    of state to drift out of sync.  With no backfill present the boundary falls
    back to the same maturation cutoff the backfill would have used, so a
    hook that runs before the one-shot backfill seeds the same live window
    instead of silently writing 150 monthly parts.
    """
    bp = backfill_path(data_root)
    if bp.exists():
        try:
            got = pd.read_parquet(bp, columns=["date"])
            if len(got):
                return pd.Timestamp(pd.to_datetime(got["date"]).max()).normalize()
        except Exception as e:  # noqa: BLE001
            log.warning("stock_events: backfill max-date read failed (%s)", e)
    asof = pd.Timestamp(fresh["date"].max()).normalize()
    return split_cutoff(asof) - pd.Timedelta(days=1)
