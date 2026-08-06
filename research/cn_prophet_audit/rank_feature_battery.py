"""CN Prophet ORDERING battery — what ranks the FUTURE best performers inside the
pool the board already admits — plus a direct port test of the US "coiled thrust"
(S-COIL) construction onto the A-share tape.

MEASUREMENT INSTRUMENT, not a signal.  Nothing here promotes, ranks, gates, or
sizes anything.  Every number is in-sample on one era and motivates preregs only.

Two parts
---------
PART A — within-admitted-pool ordering battery on the V1 episode frame.
    Frame = the 407 matured `cn_standout_v1` (board_definition='legacy') episodes,
    rebuilt through the SAME production code paths and the SAME GRADE_ASOF frozen
    replay pin as `v1_loser_audit.py` (imported, not re-implemented, so the two
    instruments cannot drift).  Every feature is read AT ADMISSION, trailing-only.
    For every feature x every outcome metric we report a Spearman rank-IC
    (continuous) or per-bucket medians + n (categorical), both POOLED and
    DATE-DEMEANED (mean of per-admission-date ICs).  The date-demeaned number is
    the honest within-pool basis and is the one every verdict quotes.

PART B — S-COIL CN retro (12 months, 2025-08-01 -> 2026-07-31).
    The US W8 ignition stand-in S-COIL construction (uptrend qualifier +
    compression run + directional release bar, release-bar-only entries) run over
    `data/china_stocks` against two controls: gate-matched non-compressed
    breakouts (same uptrend, same breakout, no compression) and an all-days
    baseline.  Plus the washout-context variant (CN's actual habitat): does a
    squeeze release INSIDE a washout beat a plain washout reclaim?

FENCES THIS INSTRUMENT RUNS UNDER (all cited in RANK_FEATURE_BATTERY.md)
-----------------------------------------------------------------------
1. DNR row "Washout x turn (2W operator seed) | KILLED" (Entry-stack Amendment-3,
   #1747): multi-timeframe stoch washout DEPTH behind a fire is an H1 FAIL
   (+3.5pp stop tax; `w2_deep ~ 0 alone`).  Depth features (`dd_from_high`,
   `washout_2w`) are TESTED here for completeness; a positive read on any of them
   is NOT a revival — it is a differently-constructed, different-market
   observation that can only re-enter through a composite + fresh prereg.
2. DNR rows 114-115 (W3 fingerprint census, W4 matched controls): "nothing
   measurable today identifies the future winner pre-onset".  This battery is
   WITHIN-ADMITTED-POOL ordering ONLY.  It never claims universe-level pre-onset
   winner detection and its results may not be cited as such.
3. ESX section 9 / DT-R5: the "arming" variant is BANNED from the squeeze family
   ("Release-bar-only definition frozen pre-run; an 'arming' variant is BANNED
   from the family").  Part B grades the RELEASE BAR ONLY.  Part A's compression
   columns are INTERNAL ORDERING FEATURES on an already-admitted pool, never a
   surfaced/ranked "armed" read — see RANK_FEATURE_BATTERY.md section "Fence
   compliance" for why that is a different construction.

Run from repo root:  python3 research/cn_prophet_audit/rank_feature_battery.py
Outputs: research/cn_prophet_audit/rank_feature_battery_results.json (frozen)
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

# Imported, never re-implemented: the frame these features hang on must be the
# SAME frame the shipped P0 gate reproduces.
from v1_loser_audit import (
    GRADE_ASOF,
    admission_character,
    forward_path,
    load_board,
    pct,
    sector_lookup,
)

from engine import china_standout_track as cst
from engine import track_scoring as ts
from engine.compression_signals import (
    chop_range_regime,
    chop_trend_regime,
    squeeze_on,
)
from engine.stock_technicals import is_nr7, true_range, ttm_squeeze

OUT = HERE / "rank_feature_battery_results.json"

H = 10                          # the shipped CN horizon (forced verdict)
CATASTROPHIC_PNL = -15.0        # absolute pnl (percent units) defining a catastrophe

# ── PART B pins ──────────────────────────────────────────────────────────────
# Same frozen-replay date as PART A: one truncation for the whole instrument, so
# a re-run tomorrow (the stores accrue a bar nightly) reproduces byte-for-byte.
# Warm-up floor. The ATR-percentile leg needs ATR_WIN + PCT_WIN = 273 trailing
# bars before it produces ANY value. At a 2024-06-01 floor that first value lands
# 2025-07-15 — two weeks before the event window opens — and the arm's fires then
# pile up in 2025-07/08 (82% of all events in one month) purely because every name
# entered the window with a barely-warm percentile. A floor a full extra year back
# makes the percentile warm for ~12 months before the first event, so event timing
# reflects the tape and not the boundary.
PANEL_LO = pd.Timestamp("2023-06-01")
EV_LO = pd.Timestamp("2025-08-01")
EV_HI = pd.Timestamp("2026-07-31")
MIN_BARS = 200                          # ">=200-bar names"
HORIZONS = (10, 21, 63)
BENCH_TICKER = "510300.SS"              # CSI300 ETF (engine.china_standout_track._BENCH)

# S-COIL constants — mirrored VERBATIM from research/prophet_us_audit/
# ignition_standins.py on PR #4564's branch (claude/w8-ignition-layer-charter).
ATR_WIN = 21          # trailing ATR window
PCT_WIN = 252         # own-history window for the ATR percentile
PCT_MAX = 0.25        # compression := ATR percentile < p25
MA_WIN = 50           # uptrend reference
MA_SLOPE = 10         # 50dMA "rising" lookback
BREAK_WIN = 21        # prior N-day high the release must clear
COMP_LOOKBACK = 21    # window in which compressed sessions are counted
COMP_MIN = 10         # >= 10 compressed sessions required
WASHOUT_DD = -0.20    # washout context: close <= -20% from own trailing 252d high


# ═════════════════════════════════════════════════════════════════════════════
# statistics helpers (dependency-light; scipy only for the t-distribution tail)
# ═════════════════════════════════════════════════════════════════════════════
def _t_sf(t: float, dof: int) -> float:
    """Two-sided p for a t statistic. Normal fallback if scipy is unavailable."""
    if dof <= 0 or not np.isfinite(t):
        return float("nan")
    try:
        from scipy import stats

        return float(2.0 * stats.t.sf(abs(t), dof))
    except Exception:  # noqa: BLE001  — normal approximation
        return float(math.erfc(abs(t) / math.sqrt(2.0)))


def spearman(x, y) -> tuple[float | None, int]:
    """Spearman rank correlation over the pairwise-complete rows. (rho, n)."""
    s = pd.DataFrame({"x": pd.to_numeric(pd.Series(x), errors="coerce"),
                      "y": pd.to_numeric(pd.Series(y), errors="coerce")}).dropna()
    if len(s) < 5 or s["x"].nunique() < 2 or s["y"].nunique() < 2:
        return None, len(s)
    r = float(s["x"].rank().corr(s["y"].rank()))
    return (r if np.isfinite(r) else None), len(s)


def pooled_ic(df: pd.DataFrame, feat: str, out: str) -> dict:
    r, n = spearman(df[feat], df[out])
    d = {"ic": pct(r) if r is not None else None, "n": n, "p": None}
    if r is not None and n > 3 and abs(r) < 1.0:
        t = r * math.sqrt((n - 2) / max(1e-12, 1.0 - r * r))
        d["p"] = pct(_t_sf(t, n - 2), 4)
    return d


def demeaned_ic(df: pd.DataFrame, feat: str, out: str, min_per_date: int = 8) -> dict:
    """Mean of per-admission-date Spearman ICs — the WITHIN-POOL ordering basis.

    Same idiom as v1_loser_audit's board_rank_ic (per-date rank correlation, then
    averaged), widened to any feature/outcome pair.  A date contributes only when
    it carries >= min_per_date complete pairs and the feature actually varies
    there (a constant feature inside a date carries no ordering information).
    """
    ics, ns = [], []
    for _d, g in df.groupby("date"):
        r, n = spearman(g[feat], g[out])
        if r is None or n < min_per_date:
            continue
        ics.append(r)
        ns.append(n)
    if not ics:
        return {"ic": None, "n_dates": 0, "n_pairs": 0, "t": None, "p": None}
    arr = np.asarray(ics, dtype=float)
    mean = float(arr.mean())
    out_d = {"ic": pct(mean), "n_dates": len(ics), "n_pairs": int(sum(ns)),
             "t": None, "p": None}
    if len(arr) >= 3 and arr.std(ddof=1) > 0:
        t = mean / (float(arr.std(ddof=1)) / math.sqrt(len(arr)))
        out_d["t"] = pct(t, 2)
        out_d["p"] = pct(_t_sf(t, len(arr) - 1), 4)
    return out_d


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n <= 0:
        return None
    p = k / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [pct(max(0.0, centre - half)), pct(min(1.0, centre + half))]


def cohort_stats(vals: np.ndarray) -> dict:
    """win% / median / mean / Wilson CI for one cohort of excess returns."""
    v = np.asarray([x for x in vals if x is not None and np.isfinite(x)], dtype=float)
    if v.size == 0:
        return {"n": 0, "win_rate": None, "wilson95": None, "median": None, "mean": None}
    k = int((v > 0).sum())
    return {"n": int(v.size), "win_rate": pct(k / v.size), "wilson95": wilson(k, v.size),
            "median": pct(float(np.median(v)), 3), "mean": pct(float(v.mean()), 3)}


# ═════════════════════════════════════════════════════════════════════════════
# PART A — frame construction
# ═════════════════════════════════════════════════════════════════════════════
# the v3 entry ladder (engine/china_board_rank.py::_ENTRY_VALUE) — used as the
# ORDINAL encoding of entry_status so it can carry a rank-IC, not just buckets.
ENTRY_ORD = {
    "buy_now": 1.0, "partial": 0.9, "buy_soon": 0.8, "hold": 0.65,
    "wait_pullback": 0.55, "later": 0.55, "await": 0.45, "await_confluence": 0.45,
    "watch": 0.4, "bounce_wait": 0.35, "extended": 0.0, "topping": 0.0,
    "blocked": 0.0, "exit": 0.0, "avoid": 0.0,
}

_ROW_COLS = (
    "board_rank", "tier", "setup", "ticks", "entry_status", "extended", "washout",
    "washout_2w", "coiled", "coiled_star", "coiled_fire", "ext_score", "ab_tier",
    "narr_level", "stage", "species_id",
    # spine outcomes carried on the row itself
    "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63",
    "terminal_state_clean8_21", "terminal_state_clean15_126", "post_cushion_breach",
)


def _tri_bool(v) -> bool | None:
    """None-preserving bool cast.

    NEVER use ``is True`` on these: the stores hand back numpy.bool_ and object
    columns, and ``np.True_ is True`` is False — the classic dead-leg trap that
    silently zeroes a detector.  Compare by value.
    """
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        if bool(pd.isna(v)):
            return None
    except (TypeError, ValueError):
        pass
    return bool(v)


def _pctile_of_own(series: pd.Series, d0: pd.Timestamp, win: int) -> float | None:
    """Value at d0 as a percentile of its OWN trailing `win` values ending at d0.

    Mirrors flow_exante_battery's turnover_pctile_60d idiom exactly:
    ``(trailing_window_excluding_today < today).mean()``.  Trailing only.
    """
    s = pd.to_numeric(series, errors="coerce").dropna()
    s = s[s.index <= d0]
    if len(s) < win + 1 or d0 not in s.index:
        return None
    today = float(s.iloc[-1])
    trail = s.iloc[-(win + 1):-1].astype(float)
    if not np.isfinite(today) or trail.isna().all():
        return None
    return float((trail < today).mean())


def compression_features(pdf: pd.DataFrame, d0: pd.Timestamp, diag: dict) -> dict:
    """The COMPRESSION family at admission — all trailing-only, all PIT.

    Every leg increments a per-leg fire counter in `diag` so a detector that
    silently never fires is visible in the output rather than reading as a null.
    """
    out: dict = {}
    need = {"high", "low", "close"}
    if not need.issubset(set(pdf.columns)):
        return out
    df = pdf[pdf.index <= d0]
    if len(df) < 60 or d0 not in df.index:
        return out
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")

    # 1. BB/KC squeeze state at admission (engine.compression_signals.squeeze_on)
    sq = squeeze_on(pd.DataFrame({"high": high, "low": low, "close": close}))
    sq_now = int(sq.loc[d0])
    out["sq_on"] = sq_now
    diag["sq_on"]["n"] += 1
    diag["sq_on"]["fired"] += int(sq_now == 1)

    # 2. squeeze DURATION — consecutive squeeze-on bars ending at admission
    arr = sq.to_numpy(dtype=int)
    dur = 0
    for i in range(len(arr) - 1, -1, -1):
        if arr[i] == 1:
            dur += 1
        else:
            break
    out["sq_duration"] = dur
    diag["sq_duration"]["n"] += 1
    diag["sq_duration"]["fired"] += int(dur > 0)

    # 3. Bollinger width (20d) as a percentile of its own trailing 252
    mid = close.rolling(20, min_periods=20).mean()
    sd = close.rolling(20, min_periods=20).std(ddof=0)
    bbw = ((mid + 2.0 * sd) - (mid - 2.0 * sd)) / mid.replace(0, np.nan)
    p = _pctile_of_own(bbw, d0, 252)
    if p is not None:
        out["bbw20_pctile_252"] = pct(p)
        diag["bbw20_pctile_252"]["n"] += 1
        diag["bbw20_pctile_252"]["fired"] += int(p < 0.25)

    # 4. NR7 within the last 3 sessions (inclusive of admission)
    nr = is_nr7(high, low).fillna(False).astype(int)
    tail = nr[nr.index <= d0].iloc[-3:]
    nr3 = int((tail.to_numpy() == 1).any()) if len(tail) else 0
    out["nr7_last3"] = nr3
    diag["nr7_last3"]["n"] += 1
    diag["nr7_last3"]["fired"] += int(nr3 == 1)

    # 5. 20d realized vol as a percentile of its own trailing 252
    rvol = close.pct_change().rolling(20, min_periods=20).std(ddof=0)
    p = _pctile_of_own(rvol, d0, 252)
    if p is not None:
        out["rvol20_pctile_252"] = pct(p)
        diag["rvol20_pctile_252"]["n"] += 1
        diag["rvol20_pctile_252"]["fired"] += int(p < 0.25)

    # 6. choppiness regime state (engine.compression_signals)
    cdf = pd.DataFrame({"high": high, "low": low, "close": close})
    trend = int(chop_trend_regime(cdf).loc[d0])
    rng = int(chop_range_regime(cdf).loc[d0])
    out["chop_regime"] = "trend" if trend == 1 else "range" if rng == 1 else "mid"
    out["chop_trend_state"] = trend
    diag["chop_trend_state"]["n"] += 1
    diag["chop_trend_state"]["fired"] += int(trend == 1)
    diag["chop_range_state"]["n"] += 1
    diag["chop_range_state"]["fired"] += int(rng == 1)

    # 7. Donchian width (20d) as a percentile of its own trailing 252
    dw = (high.rolling(20, min_periods=20).max()
          - low.rolling(20, min_periods=20).min()) / close.replace(0, np.nan)
    p = _pctile_of_own(dw, d0, 252)
    if p is not None:
        out["donch_width_pctile_252"] = pct(p)
        diag["donch_width_pctile_252"]["n"] += 1
        diag["donch_width_pctile_252"]["fired"] += int(p < 0.25)

    # 8. the S-COIL compression state itself (ATR-pctile leg + uptrend qualifier),
    #    so PART A and PART B read the SAME construction on the same names.
    #    PER-LEG DECOMPOSITION is mandatory here: a conjunction that never fires
    #    must be provably a REAL zero (the pool has no such names) and not a dead
    #    leg (a detector wired wrong).  The three legs are counted separately.
    tr = true_range(high, low, close)
    atr21 = tr.rolling(ATR_WIN, min_periods=ATR_WIN).mean()
    atr_pct = atr21.rolling(PCT_WIN, min_periods=PCT_WIN).rank(pct=True)
    ma = close.rolling(MA_WIN, min_periods=MA_WIN).mean()
    leg_above = bool(close.loc[d0] > ma.loc[d0]) if pd.notna(ma.loc[d0]) else False
    leg_rising = (bool(ma.loc[d0] > ma.shift(MA_SLOPE).loc[d0])
                  if pd.notna(ma.shift(MA_SLOPE).loc[d0]) else False)
    leg_calm = (bool(atr_pct.loc[d0] < PCT_MAX)
                if pd.notna(atr_pct.loc[d0]) else False)
    for k, hit in (("scoil_leg_close_gt_ma50", leg_above),
                   ("scoil_leg_ma50_rising", leg_rising),
                   ("scoil_leg_atr_pct_lt_p25", leg_calm)):
        diag[k]["n"] += 1
        diag[k]["fired"] += int(hit)
    coil = ((atr_pct < PCT_MAX) & (close > ma) & (ma > ma.shift(MA_SLOPE))).fillna(False)
    coil_now = int(coil.loc[d0])
    out["scoil_state"] = coil_now
    diag["scoil_state"]["n"] += 1
    diag["scoil_state"]["fired"] += int(coil_now == 1)
    run = int(coil[coil.index <= d0].iloc[-COMP_LOOKBACK:].sum())
    out["scoil_run_21"] = run
    diag["scoil_run_21"]["n"] += 1
    diag["scoil_run_21"]["fired"] += int(run >= COMP_MIN)
    return out


def turnover_feature(pdf: pd.DataFrame, d0: pd.Timestamp) -> dict:
    """turnover_pctile_60d — mirrored from flow_exante_battery.py (the separator)."""
    if "volume" not in pdf.columns:
        return {}
    p = _pctile_of_own(pdf["volume"], d0, 60)
    return {} if p is None else {"turnover_pctile_60d": pct(p)}


def build_frame() -> tuple[pd.DataFrame, dict]:
    """Rebuild the V1 matured-episode frame + every admission-time feature.

    Structurally identical to v1_loser_audit.main()'s frame construction (same
    production code paths, same GRADE_ASOF truncation, same T+1 fill, same
    forced-verdict scoring) and gated on the same P0 reproduction assert.
    """
    board = load_board()
    look = sector_lookup()
    bench = cst._bench_close()
    if bench is not None:
        bench = bench[bench.index <= GRADE_ASOF]

    board_days: dict[str, set[str]] = defaultdict(set)
    admit: dict[tuple[str, str], dict] = {}
    for _, r in board.iterrows():
        d, tk = str(r["date"]), str(r["ticker"])
        board_days[d].add(tk)
        admit[(d, tk)] = r.to_dict()

    # Per-leg fire counters. "n" = episodes the leg was COMPUTABLE on; "fired" =
    # episodes where the leg's own condition was TRUE (for the percentile columns
    # that is the compressed tail, value < p25 — a tail count, not coverage).
    diag_keys = ("sq_on", "sq_duration", "bbw20_pctile_252", "nr7_last3",
                 "rvol20_pctile_252", "chop_trend_state", "chop_range_state",
                 "donch_width_pctile_252", "scoil_leg_close_gt_ma50",
                 "scoil_leg_ma50_rising", "scoil_leg_atr_pct_lt_p25",
                 "scoil_state", "scoil_run_21")
    diag = {k: {"n": 0, "fired": 0} for k in diag_keys}

    rows, n_episodes, n_locked, n_skipped = [], 0, 0, 0
    for ep in ts.build_episodes(board_days):
        tk, d0s = ep["ticker"], ep["entry_date"]
        d0 = pd.Timestamp(d0s)
        pdf = cst._price_frame(tk)
        if pdf is not None:
            pdf = pdf[pdf.index <= GRADE_ASOF]
        if pdf is None or "close" not in pdf:
            n_skipped += 1
            continue
        fill, locked, pinned = cst._t1_fill(pdf, d0)
        if locked:
            n_locked += 1
        closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
        after = closes.index[closes.index > d0]
        sc = None
        if fill is not None and len(after):
            sc = ts.score_from_fill(closes, after[0], float(fill), H,
                                    bench_close=bench, include_fill_bar=True)
        if sc is None:
            n_skipped += 1
            continue
        n_episodes += 1
        if not (bool(sc["matured"]) and not locked) or sc.get("excess") is None:
            continue

        a = admit.get((d0s, tk)) or {}
        rec = {
            "ticker": tk, "date": d0s,
            "sector": (look.get(tk) or {}).get("sec"),
            "excess_h10": pct(sc.get("excess")),
            "pnl": pct(sc.get("pnl")),
            "pinned_ref": int(bool(pinned)),
            "initial_stock": int(d0s == "2026-06-30"),
        }
        # ── row fields ───────────────────────────────────────────────────────
        for c in _ROW_COLS:
            rec[c] = a.get(c)
        for c in ("extended", "washout", "coiled", "coiled_star", "coiled_fire",
                  "post_cushion_breach"):
            rec[c] = _tri_bool(rec.get(c))
        for c in ("tier", "entry_status", "ab_tier", "narr_level", "stage",
                  "species_id", "terminal_state_clean8_21",
                  "terminal_state_clean15_126"):
            rec[c] = rec[c] if isinstance(rec.get(c), str) else None
        for c in ("board_rank", "setup", "ticks", "ext_score", "washout_2w",
                  "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63"):
            v = rec.get(c)
            rec[c] = None if v is None or pd.isna(v) else float(v)
        rec["entry_ord"] = ENTRY_ORD.get(rec.get("entry_status")) \
            if rec.get("entry_status") else None
        # ── admission character (audit idiom, imported) ──────────────────────
        rec.update(admission_character(pdf, d0))
        rec.update(turnover_feature(pdf, d0))
        rec.update(compression_features(pdf, d0, diag))
        # ── forward path (audit idiom, imported): MAE_10 + day_of_max ────────
        if fill is not None:
            fp = forward_path(pdf, d0, float(fill), tk)
            rec["mae_10"] = fp.get("mae")
            rec["mfe_10_local"] = fp.get("mfe")
            rec["day_of_max"] = fp.get("day_of_max")
            rec["day_of_min"] = fp.get("day_of_min")
            rec["shape"] = fp.get("shape")
        rows.append(rec)

    df = pd.DataFrame(rows)
    win_rate = float((df["excess_h10"] > 0).mean())
    losers = int((df["excess_h10"] <= 0).sum())
    print(f"[PART A] episodes={n_episodes} matured={len(df)} "
          f"win={100 * win_rate:.2f}% losers={losers} locked={n_locked} "
          f"skipped={n_skipped}")
    # ── P0 reproduction gate — the shipped cn_track_ledger prior_record ───────
    assert n_episodes == 584, f"episodes {n_episodes} != shipped 584"
    assert len(df) == 407, f"matured {len(df)} != shipped 407"
    assert abs(win_rate - 0.6855) < 0.0015, f"win {win_rate:.4f} != shipped 0.6855"
    assert losers == 128, f"losers {losers} != shipped 128"

    repro = {"episodes": n_episodes, "matured": len(df), "win_rate": pct(win_rate),
             "losers": losers, "n_locked": n_locked, "n_skipped": n_skipped,
             "grade_asof": str(GRADE_ASOF.date()),
             "shipped": {"episodes": 584, "matured": 407, "win_rate": 0.6855,
                         "losers": 128}}
    return df, {"reproduction": repro, "compression_fire_counts": diag}


# ═════════════════════════════════════════════════════════════════════════════
# PART A — theme / cycle joins (mirrors sector_intel_exante_test.py)
# ═════════════════════════════════════════════════════════════════════════════
def attach_theme_state(df: pd.DataFrame) -> dict:
    flog = pd.read_parquet(ROOT / "data/china_sector_cycles/forward_log.parquet")
    flog = flog[flog["kind"] == "basket"].copy()
    flog["date"] = flog["date"].astype(str)
    mem = json.loads((ROOT / "data/baskets_china/membership.json").read_text())["baskets"]
    by_ticker: dict[str, list[tuple[str, str, str | None]]] = defaultdict(list)
    for bid, blk in mem.items():
        for m in blk.get("members") or []:
            by_ticker[str(m["ticker"])].append(
                (bid, str(m.get("added") or "1900-01-01"), m.get("removed")))
    flog_by = {(r["date"], str(r["id"])): r for _, r in flog.iterrows()}
    flog_dates = sorted(flog["date"].unique())

    in_basket, phase_slope, rs_rank, above200 = [], [], [], []
    for tkr, d in zip(df["ticker"], df["date"]):
        eff = max((x for x in flog_dates if x <= d), default=None)
        cands = []
        if eff is not None:
            for bid, added, removed in by_ticker.get(str(tkr), []):
                if added <= d and (removed is None or removed > d):
                    row = flog_by.get((eff, f"b-{bid}"))
                    if row is not None:
                        cands.append(row)
        if not cands:
            in_basket.append(0)
            phase_slope.append(None)
            rs_rank.append(None)
            above200.append(None)
            continue
        best = min(cands, key=lambda r: r.get("rs_rank") or 99)
        in_basket.append(1)
        phase_slope.append(f"{best.get('phase')}{'+' if (best.get('osc_slope') or 0) > 0 else '-'}")
        rs_rank.append(int(best["rs_rank"]) if pd.notna(best.get("rs_rank")) else None)
        above200.append(_tri_bool(best.get("above200d")))
    df["in_basket"] = in_basket
    df["phase_slope"] = phase_slope
    df["basket_rs_rank"] = rs_rank
    df["basket_above200d"] = above200
    return {"covered": int(sum(in_basket)), "episodes": len(df)}


# ═════════════════════════════════════════════════════════════════════════════
# PART A — the battery
# ═════════════════════════════════════════════════════════════════════════════
CONTINUOUS = [
    # existing row fields
    ("setup", "row"), ("ticks", "row"), ("entry_ord", "row"), ("ext_score", "row"),
    ("washout_2w", "row"), ("board_rank", "row"),
    # admission character
    ("trail_5", "char"), ("trail_21", "char"), ("trail_63", "char"),
    ("dd_from_high", "char"), ("vs_ma20", "char"), ("vs_ma50", "char"),
    ("vs_ma200", "char"), ("day0_ret", "char"), ("consec_up", "char"),
    ("vol_surge", "char"), ("turnover_pctile_60d", "char"),
    # compression family
    ("sq_on", "compression"), ("sq_duration", "compression"),
    ("bbw20_pctile_252", "compression"), ("nr7_last3", "compression"),
    ("rvol20_pctile_252", "compression"), ("chop_trend_state", "compression"),
    ("donch_width_pctile_252", "compression"), ("scoil_state", "compression"),
    ("scoil_run_21", "compression"),
    # theme / cycle
    ("in_basket", "theme"), ("basket_rs_rank", "theme"),
    # existing coiled flags (bool -> 0/1 for the IC)
    ("coiled_i", "row"), ("coiled_star_i", "row"), ("coiled_fire_i", "row"),
    ("extended_i", "row"), ("washout_i", "row"),
]

CATEGORICAL = [
    ("tier", "row"), ("entry_status", "row"), ("ab_tier", "row"),
    ("narr_level", "row"), ("stage", "row"), ("species_id", "row"),
    ("chop_regime", "compression"), ("phase_slope", "theme"),
]

# (key, label, coverage note) — every outcome the battery grades
OUTCOMES = [
    ("excess_h10", "CSI300-relative excess at the H=10 forced verdict (percent)"),
    ("mfe_10", "board-row fwd_mfe_10 (spine, T+1 HL2/open fill)"),
    ("mfe_21", "board-row fwd_mfe_21 (spine)"),
    ("mfe_63", "board-row fwd_mfe_63 (spine)"),
    ("mae_10", "MAE over the 10-session forward path (decimal, negative)"),
    ("catastrophic", "1 if absolute pnl <= -15% (percent units)"),
    ("clean_liftoff", "1 if terminal_state_clean8_21 == CLEAN_LIFTOFF"),
]


def prepare_outcomes(df: pd.DataFrame) -> dict:
    df["mfe_10"] = df["fwd_mfe_10"]
    df["mfe_21"] = df["fwd_mfe_21"]
    df["mfe_63"] = df["fwd_mfe_63"]
    df["catastrophic"] = (df["pnl"] <= CATASTROPHIC_PNL).astype(float)
    ts8 = df["terminal_state_clean8_21"]
    df["clean_liftoff"] = np.where(ts8.isna(), np.nan,
                                   (ts8 == "CLEAN_LIFTOFF").astype(float))
    # bool -> int mirrors for the continuous battery
    for src, dst in (("coiled", "coiled_i"), ("coiled_star", "coiled_star_i"),
                     ("coiled_fire", "coiled_fire_i"), ("extended", "extended_i"),
                     ("washout", "washout_i")):
        df[dst] = df[src].map(lambda v: None if v is None else int(bool(v)))
        df[dst] = pd.to_numeric(df[dst], errors="coerce")
    cov = {}
    for k, note in OUTCOMES:
        n = int(pd.to_numeric(df[k], errors="coerce").notna().sum())
        cov[k] = {"n_nonnull": n, "note": note,
                  "usable": n >= 40}
    return cov


def era_halves(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    dates = sorted(df["date"].unique())
    mid = len(dates) // 2
    return dates[:mid], dates[mid:]


def continuous_battery(df: pd.DataFrame, usable: list[str]) -> dict:
    h1_dates, h2_dates = era_halves(df)
    winners = df[df["excess_h10"] > 0]
    res: dict = {}
    for feat, fam in CONTINUOUS:
        if feat not in df.columns:
            continue
        col = pd.to_numeric(df[feat], errors="coerce")
        cov = int(col.notna().sum())
        n_distinct = int(col.nunique(dropna=True))
        modal_share = (float(col.value_counts(dropna=True).iloc[0] / cov)
                       if cov else None)
        blk: dict = {"family": fam, "coverage": cov, "n_distinct": n_distinct,
                     "modal_value_share": pct(modal_share) if modal_share is not None
                     else None, "metrics": {}}
        if cov < 40:
            blk["status"] = "UNUSABLE(coverage<40)"
            res[feat] = blk
            continue
        # A feature that is effectively constant on this pool carries NO ordering
        # information. Grading it produces an IC computed off a handful of rows on
        # a single date, which then sorts high by |IC| and reads as a finding.
        if n_distinct < 2 or (modal_share is not None and modal_share > 0.99):
            blk["status"] = "UNUSABLE(no variation on this pool)"
            res[feat] = blk
            continue
        blk["status"] = "graded"
        for out in usable:
            blk["metrics"][out] = {"pooled": pooled_ic(df, feat, out),
                                   "demeaned": demeaned_ic(df, feat, out)}
        # winners-only magnitude ordering (what ranks the +50s above the +5s)
        blk["winners_only_excess_h10"] = {
            "pooled": pooled_ic(winners, feat, "excess_h10"),
            "demeaned": demeaned_ic(winners, feat, "excess_h10", min_per_date=8),
            "n_winners": int(pd.to_numeric(winners[feat], errors="coerce").notna().sum()),
        }
        # stability: sign agreement of the demeaned excess IC across era halves
        a = demeaned_ic(df[df["date"].isin(h1_dates)], feat, "excess_h10")
        b = demeaned_ic(df[df["date"].isin(h2_dates)], feat, "excess_h10")
        agree = None
        if a["ic"] is not None and b["ic"] is not None:
            agree = bool((a["ic"] > 0) == (b["ic"] > 0))
        blk["halves_excess_h10"] = {"h1": a, "h2": b, "sign_agree": agree}
        res[feat] = blk
    return res


def categorical_battery(df: pd.DataFrame, usable: list[str]) -> dict:
    """Per-bucket medians + n, POOLED and DATE-DEMEANED.

    The demeaned column is the median of the bucket's WITHIN-DATE percentile rank
    of the outcome: 0.50 = the bucket performed exactly like its own admission
    day's pool; >0.50 = it beat the pool it was admitted alongside.
    """
    res: dict = {}
    for feat, fam in CATEGORICAL:
        if feat not in df.columns:
            continue
        sub = df[df[feat].notna()]
        blk: dict = {"family": fam, "coverage": len(sub), "buckets": {}}
        if len(sub) < 40:
            blk["status"] = "UNUSABLE(coverage<40)"
            res[feat] = blk
            continue
        blk["status"] = "graded"
        for out in usable:
            pct_rank = sub.groupby("date")[out].rank(pct=True)
            tbl = {}
            for k, g in sub.groupby(feat):
                vals = pd.to_numeric(g[out], errors="coerce").dropna()
                if vals.empty:
                    continue
                pr = pct_rank.loc[g.index].dropna()
                tbl[str(k)] = {
                    "n": len(vals),
                    "median": pct(float(vals.median()), 3),
                    "median_within_date_pctile": pct(float(pr.median())) if len(pr) else None,
                    "thin": bool(len(vals) < 15),
                }
            blk["buckets"][out] = tbl
        res[feat] = blk
    return res


def compression_vs_coiled(df: pd.DataFrame) -> dict:
    """Does the compression family carry ordering information the board's own
    `coiled` flags do not already carry?  Reported as a plain correlation matrix
    (Spearman) — a redundancy check, never a blend."""
    comp = ["sq_on", "sq_duration", "bbw20_pctile_252", "rvol20_pctile_252",
            "donch_width_pctile_252", "nr7_last3", "scoil_state", "scoil_run_21",
            "chop_trend_state"]
    flags = ["coiled_i", "coiled_star_i", "coiled_fire_i", "ticks", "setup"]
    mat: dict = {}
    for c in comp:
        if c not in df.columns:
            continue
        mat[c] = {}
        for f in flags:
            if f not in df.columns:
                continue
            r, n = spearman(df[c], df[f])
            mat[c][f] = {"rho": pct(r) if r is not None else None, "n": n}
    return mat


COLLIN_COLS = [
    "trail_5", "trail_21", "trail_63", "vs_ma20", "vs_ma50", "vs_ma200",
    "dd_from_high", "setup", "consec_up", "day0_ret", "turnover_pctile_60d",
    "vol_surge", "donch_width_pctile_252", "bbw20_pctile_252",
    "rvol20_pctile_252", "sq_on", "sq_duration", "nr7_last3", "in_basket",
    "coiled_i", "board_rank",
]


def collinearity(df: pd.DataFrame) -> dict:
    """Spearman correlation between the graded features themselves.

    Load-bearing, not decoration. 186 IC tests over 31 features is NOT 31
    independent axes: this matrix is how a reader sees that trail_5/trail_21/
    vs_ma20/vs_ma50/setup are one thrust axis, that vs_ma200 is largely
    drawdown-depth in another coordinate system (which is what makes the DNR
    #1747 depth fence bind on it), and that the three compression encodings are
    one width axis.
    """
    cols = [c for c in COLLIN_COLS if c in df.columns]
    m = df[cols].apply(pd.to_numeric, errors="coerce").corr(method="spearman")
    return {a: {b: pct(float(m.loc[a, b])) if np.isfinite(m.loc[a, b]) else None
                for b in cols} for a in cols}


def multiplicity_block(cont: dict, cat: dict, usable: list[str]) -> dict:
    n_cont = sum(1 for v in cont.values() if v.get("status") == "graded")
    n_cat = sum(1 for v in cat.values() if v.get("status") == "graded")
    n_tests = (n_cont) * len(usable)
    nominal = 0
    for v in cont.values():
        if v.get("status") != "graded":
            continue
        for m in v["metrics"].values():
            p = (m["demeaned"] or {}).get("p")
            if p is not None and p < 0.05:
                nominal += 1
    return {
        "n_continuous_features_graded": n_cont,
        "n_categorical_features_graded": n_cat,
        "n_usable_outcome_metrics": len(usable),
        "n_continuous_ic_tests": n_tests,
        "expected_nominal_hits_at_alpha_0.05": pct(0.05 * n_tests, 1),
        "observed_nominal_hits_demeaned": nominal,
        "honesty": (
            "No multiplicity correction is applied and none is claimed. With "
            f"{n_tests} continuous feature x metric IC tests, ~{0.05 * n_tests:.0f} "
            "nominally significant results are EXPECTED under the global null. A "
            "nominal hit here is not a finding. Only axes that are (a) stable in "
            "SIGN across both era halves, (b) mechanism-backed, and (c) survive a "
            "fresh pre-registration on out-of-era data may graduate to the score "
            "ladder. This is one era, 12 admission dates, 407 episodes, in-sample. "
            "The tests are also NOT independent of each other: see "
            "feature_collinearity_spearman -- the graded features collapse to about "
            "five distinct axes (short-horizon thrust, long-horizon position/depth, "
            "crowding, range width, theme membership), so both the expected-hits "
            "figure and the observed count are counts of correlated tests."
        ),
    }


MIN_LADDER_DATES = 6   # half the 12 graded admission dates


def rank_features(cont: dict) -> dict:
    """Rank by |date-demeaned IC| on excess_h10 with the stability check attached.

    RANKABILITY GATE: a feature must have contributed a per-date IC on at least
    MIN_LADDER_DATES of the 12 graded admission dates.  Without this gate a
    feature that varies on ONE date sorts by an IC estimated from that one date
    and lands near the top of the ladder — the sparsest possible number reading
    as the strongest possible finding.  Gated-out features are returned in
    `not_rankable` WITH their numbers, never silently dropped.
    """
    ranked, sparse = [], []
    for feat, blk in cont.items():
        if blk.get("status") != "graded":
            sparse.append({"feature": feat, "family": blk.get("family"),
                           "reason": blk.get("status"),
                           "coverage": blk.get("coverage"),
                           "n_distinct": blk.get("n_distinct"),
                           "modal_value_share": blk.get("modal_value_share")})
            continue
        m = blk["metrics"].get("excess_h10")
        if not m or m["demeaned"]["ic"] is None:
            sparse.append({"feature": feat, "family": blk["family"],
                           "reason": "no per-date IC computable"})
            continue
        d = m["demeaned"]
        halves = blk.get("halves_excess_h10") or {}
        row = {
            "feature": feat, "family": blk["family"],
            "demeaned_ic": d["ic"], "t": d["t"], "p": d["p"],
            "n_dates": d["n_dates"], "coverage": blk["coverage"],
            "modal_value_share": blk.get("modal_value_share"),
            "pooled_ic": m["pooled"]["ic"],
            "h1_ic": (halves.get("h1") or {}).get("ic"),
            "h2_ic": (halves.get("h2") or {}).get("ic"),
            "sign_agree": halves.get("sign_agree"),
            "winners_only_ic": (blk["winners_only_excess_h10"]["demeaned"] or {}).get("ic"),
        }
        if d["n_dates"] < MIN_LADDER_DATES:
            row["reason"] = f"n_dates {d['n_dates']} < {MIN_LADDER_DATES} (too sparse to rank)"
            sparse.append(row)
            continue
        ranked.append(row)
    ranked.sort(key=lambda r: -abs(r["demeaned_ic"]))
    return {"min_dates_gate": MIN_LADDER_DATES, "ranked": ranked,
            "not_rankable": sparse}


# ═════════════════════════════════════════════════════════════════════════════
# PART B — S-COIL CN retro
# ═════════════════════════════════════════════════════════════════════════════
def load_cn_panel() -> tuple[dict[str, pd.DataFrame], pd.Series]:
    frames: dict[str, pd.DataFrame] = {}
    for f in sorted(glob.glob(str(ROOT / "data/china_stocks/*.parquet"))):
        tkr = os.path.basename(f)[: -len(".parquet")]
        d = pd.read_parquet(f)
        d = d[(d.index >= PANEL_LO) & (d.index <= GRADE_ASOF)]
        if len(d) < MIN_BARS:
            continue
        frames[tkr] = d
    bench = cst._bench_close()
    if bench is None:
        raise RuntimeError(f"benchmark {BENCH_TICKER} unavailable")
    bench = bench[bench.index <= GRADE_ASOF]
    return frames, bench


def scoil_arms(d: pd.DataFrame) -> dict:
    """The two compression legs + the shared uptrend / release machinery.

    ARM 1 (primary, the brief's construction): BB/KC squeeze via the
      market-agnostic engine.stock_technicals.ttm_squeeze.
    ARM 2 (literal US mirror): ATR-percentile compression, verbatim
      research/prophet_us_audit/ignition_standins.py::coil_compression.

    Both arms are reported. Neither is selected on its result.
    """
    high = pd.to_numeric(d["high"], errors="coerce")
    low = pd.to_numeric(d["low"], errors="coerce")
    close = pd.to_numeric(d["close"], errors="coerce")
    ma = close.rolling(MA_WIN, min_periods=MA_WIN).mean()
    uptrend = ((close > ma) & (ma > ma.shift(MA_SLOPE))).fillna(False)

    prior_high = high.rolling(BREAK_WIN, min_periods=BREAK_WIN).max().shift(1)
    breakout = (close > prior_high).fillna(False)
    first = breakout & ~breakout.shift(1).fillna(False).astype(bool)

    hi252 = close.rolling(252, min_periods=60).max()
    dd = close / hi252 - 1.0

    tr = true_range(high, low, close)
    atr21 = tr.rolling(ATR_WIN, min_periods=ATR_WIN).mean()
    atr_pct = atr21.rolling(PCT_WIN, min_periods=PCT_WIN).rank(pct=True)

    arms = {
        # ARM 1: BB/KC squeeze; the uptrend qualifier is applied at the release bar
        # (below) exactly as it is for ARM 2's control, so both arms share one gate.
        "bbkc": ttm_squeeze(high, low, close, n=20).fillna(False),
        # ARM 2: US-verbatim — compression itself embeds the uptrend qualifier
        "atr_pctile": ((atr_pct < PCT_MAX) & (close > ma)
                       & (ma > ma.shift(MA_SLOPE))).fillna(False),
    }
    out = {"uptrend": uptrend, "first_break": first, "dd": dd, "arms": {}}
    for name, compressed in arms.items():
        run = compressed.rolling(COMP_LOOKBACK, min_periods=COMP_LOOKBACK).sum() >= COMP_MIN
        armed_prev = run.shift(1).fillna(False).astype(bool)
        out["arms"][name] = {
            "compressed": compressed, "run": run, "armed_prev": armed_prev,
            "events": (first & armed_prev & uptrend).fillna(False),
            # GATE-MATCHED control: same uptrend, same first breakout, NO compression
            "controls": (first & ~armed_prev & uptrend).fillna(False),
        }
    return out


def forward_excess(d: pd.DataFrame, bench_aligned: pd.Series) -> dict[int, pd.Series]:
    """Vectorised mirror of track_scoring.score_from_fill(include_fill_bar=True).

    fill  = T+1 (H+L)/2 (uniform basis — see the fill-basis note in the MD).
    exit  = close at index i+H (fill bar is i+1 and counts as bar 1 of H).
    excess= pnl% - benchmark% measured over the SAME fill-bar -> exit-bar window.
    """
    high = pd.to_numeric(d["high"], errors="coerce")
    low = pd.to_numeric(d["low"], errors="coerce")
    close = pd.to_numeric(d["close"], errors="coerce")
    fill = ((high.shift(-1) + low.shift(-1)) / 2.0)
    locked = ((high.shift(-1) == low.shift(-1))
              & (low.shift(-1) == close.shift(-1))).fillna(False)
    fill = fill.where(~locked)                     # locked-limit T+1 is unfillable
    fill = fill.where(fill > 0)
    b_fill = bench_aligned.shift(-1)
    out: dict[int, pd.Series] = {}
    for h in HORIZONS:
        exit_px = close.shift(-h)
        b_exit = bench_aligned.shift(-h)
        pnl = (exit_px / fill - 1.0) * 100.0
        bmk = (b_exit / b_fill - 1.0) * 100.0
        out[h] = pnl - bmk
    out["locked"] = locked
    return out


def part_b() -> dict:
    t0 = time.time()
    frames, bench = load_cn_panel()
    print(f"[PART B] universe: {len(frames)} names with >= {MIN_BARS} bars in "
          f"[{PANEL_LO.date()}, {GRADE_ASOF.date()}]")

    diag = {a: {k: 0 for k in ("compressed_name_days", "run_name_days",
                               "uptrend_name_days", "breakout_name_days",
                               "first_breakout_name_days", "events",
                               "gate_matched_controls", "events_in_window",
                               "controls_in_window", "events_locked_excluded")}
            for a in ("bbkc", "atr_pctile")}

    buckets: dict = {}

    def key(arm, cohort, h, half=None, wash=False):
        return (arm, cohort, h, half, wash)

    for arm in ("bbkc", "atr_pctile"):
        for cohort in ("event", "control", "alldays"):
            for h in HORIZONS:
                for half in (None, "h1", "h2"):
                    for wash in (False, True):
                        buckets[key(arm, cohort, h, half, wash)] = []

    # Per-calendar-month event/control tallies. Wilson on pooled name-days treats
    # every name-day as an independent bet; A-share name-days are heavily
    # cross-correlated and the H21/H63 windows overlap, so the pooled intervals
    # are several times too narrow. A month-by-month sign count is the cheap
    # dependence-aware check: it asks whether the sign holds across time blocks
    # rather than how tight an over-counted interval is.
    monthly: dict = defaultdict(lambda: {"ev_n": 0, "ev_w": 0, "ct_n": 0, "ct_w": 0})

    mid = EV_LO + (EV_HI - EV_LO) / 2
    n_alldays_cells = 0
    for d in frames.values():
        months = d.index.to_period("M").astype(str).to_numpy()
        ba = bench.reindex(d.index, method="bfill")
        fx = forward_excess(d, ba)
        sig = scoil_arms(d)
        win = (d.index >= EV_LO) & (d.index <= EV_HI)
        half_lbl = np.where(d.index < mid, "h1", "h2")
        wash_flag = (sig["dd"] <= WASHOUT_DD).fillna(False).to_numpy()
        locked = fx["locked"].to_numpy()
        up = sig["uptrend"].to_numpy()
        n_alldays_cells += int(win.sum())

        for arm in ("bbkc", "atr_pctile"):
            A = sig["arms"][arm]
            diag[arm]["compressed_name_days"] += int(A["compressed"].to_numpy().sum())
            diag[arm]["run_name_days"] += int(A["run"].fillna(False).to_numpy().sum())
            diag[arm]["uptrend_name_days"] += int(up.sum())
            diag[arm]["breakout_name_days"] += int(sig["first_break"].to_numpy().sum())
            diag[arm]["first_breakout_name_days"] += int(sig["first_break"].to_numpy().sum())
            ev = A["events"].to_numpy() & win
            ct = A["controls"].to_numpy() & win
            diag[arm]["events"] += int(A["events"].to_numpy().sum())
            diag[arm]["gate_matched_controls"] += int(A["controls"].to_numpy().sum())
            diag[arm]["events_in_window"] += int(ev.sum())
            diag[arm]["controls_in_window"] += int(ct.sum())
            diag[arm]["events_locked_excluded"] += int((ev & locked).sum())
            for cohort, mask in (("event", ev), ("control", ct),
                                 ("alldays", win & ~locked)):
                if not mask.any():
                    continue
                for h in HORIZONS:
                    vals = fx[h].to_numpy()
                    sel = mask & np.isfinite(vals)
                    if not sel.any():
                        continue
                    v = vals[sel]
                    hl = half_lbl[sel]
                    wf = wash_flag[sel]
                    buckets[key(arm, cohort, h, None, False)].extend(v.tolist())
                    buckets[key(arm, cohort, h, "h1", False)].extend(v[hl == "h1"].tolist())
                    buckets[key(arm, cohort, h, "h2", False)].extend(v[hl == "h2"].tolist())
                    buckets[key(arm, cohort, h, None, True)].extend(v[wf].tolist())
                    buckets[key(arm, cohort, h, "h1", True)].extend(v[wf & (hl == "h1")].tolist())
                    buckets[key(arm, cohort, h, "h2", True)].extend(v[wf & (hl == "h2")].tolist())
                    # month-block tally at the headline horizon only
                    if h == 10 and cohort in ("event", "control"):
                        mo = months[sel]
                        pre = "ev" if cohort == "event" else "ct"
                        for m_, val in zip(mo, v):
                            cell = monthly[(arm, m_)]
                            cell[f"{pre}_n"] += 1
                            cell[f"{pre}_w"] += int(val > 0)

    res: dict = {"universe": {"n_names": len(frames), "min_bars": MIN_BARS,
                              "panel_lo": str(PANEL_LO.date()),
                              "event_window": [str(EV_LO.date()), str(EV_HI.date())],
                              "grade_asof": str(GRADE_ASOF.date()),
                              "alldays_name_day_cells": n_alldays_cells,
                              "benchmark": BENCH_TICKER,
                              "fill": "T+1 (H+L)/2, locked-limit excluded"},
                 "fire_counts": diag, "arms": {},
                 "dependence_caveat": (
                     "Wilson intervals here treat every name-day as an independent "
                     "bet. A-share name-days are strongly cross-correlated and the "
                     "H21/H63 windows overlap, so the true intervals are several "
                     "times wider than printed -- most severely for the all-days "
                     "baseline (n~381k name-days is nothing like 381k independent "
                     "observations). The event-vs-control contrast is the defensible "
                     "comparison (both cohorts sit in the same tape on the same "
                     "gate); the month-block sign count below is the dependence-aware "
                     "check on it."
                 )}
    # month-block sign check on the H10 event-minus-control win-rate delta
    for arm in ("bbkc", "atr_pctile"):
        rows = []
        for (a_, m_), c in sorted(monthly.items()):
            if a_ != arm or c["ev_n"] < 10 or c["ct_n"] < 10:
                continue
            dlt = 100.0 * (c["ev_w"] / c["ev_n"] - c["ct_w"] / c["ct_n"])
            rows.append({"month": m_, "n_event": c["ev_n"], "n_control": c["ct_n"],
                         "event_win": pct(c["ev_w"] / c["ev_n"]),
                         "control_win": pct(c["ct_w"] / c["ct_n"]),
                         "delta_pp": pct(dlt, 2)})
        pos = sum(1 for r in rows if r["delta_pp"] > 0)
        tot = sum(r["n_event"] for r in rows)
        top = max((r["n_event"] for r in rows), default=0)
        res.setdefault("month_block_H10", {})[arm] = {
            "n_months": len(rows), "months_event_beats_control": pos,
            "months_event_loses": len(rows) - pos,
            # time-concentration: if one month owns most of the events, the arm is
            # one time block wearing an n of several hundred.
            "largest_month_share_of_events": pct(top / tot) if tot else None,
            "rows": rows}
    for arm in ("bbkc", "atr_pctile"):
        blk: dict = {}
        for wash in (False, True):
            tag = "washout_ctx" if wash else "all_context"
            blk[tag] = {}
            for h in HORIZONS:
                blk[tag][f"H{h}"] = {
                    coh: {
                        "full": cohort_stats(np.asarray(buckets[key(arm, coh, h, None, wash)])),
                        "h1": cohort_stats(np.asarray(buckets[key(arm, coh, h, "h1", wash)])),
                        "h2": cohort_stats(np.asarray(buckets[key(arm, coh, h, "h2", wash)])),
                    } for coh in ("event", "control", "alldays")
                }
                e = blk[tag][f"H{h}"]["event"]["full"]
                c = blk[tag][f"H{h}"]["control"]["full"]
                a = blk[tag][f"H{h}"]["alldays"]["full"]
                blk[tag][f"H{h}"]["deltas"] = {
                    "event_minus_control_win_pp": (
                        pct(100 * (e["win_rate"] - c["win_rate"]), 2)
                        if e["win_rate"] is not None and c["win_rate"] is not None else None),
                    "event_minus_control_median": (
                        pct(e["median"] - c["median"], 3)
                        if e["median"] is not None and c["median"] is not None else None),
                    "event_minus_alldays_win_pp": (
                        pct(100 * (e["win_rate"] - a["win_rate"]), 2)
                        if e["win_rate"] is not None and a["win_rate"] is not None else None),
                    "event_minus_alldays_median": (
                        pct(e["median"] - a["median"], 3)
                        if e["median"] is not None and a["median"] is not None else None),
                    "wilson_overlap_event_vs_control": (
                        None if e["wilson95"] is None or c["wilson95"] is None
                        else bool(e["wilson95"][0] <= c["wilson95"][1]
                                  and c["wilson95"][0] <= e["wilson95"][1])),
                }
        res["arms"][arm] = blk
    print(f"[PART B] done in {time.time() - t0:.1f}s")
    return res


# ═════════════════════════════════════════════════════════════════════════════
def main() -> None:
    t_start = time.time()
    df, meta = build_frame()
    theme_cov = attach_theme_state(df)
    cov = prepare_outcomes(df)
    usable = [k for k, _ in OUTCOMES if cov[k]["usable"]]
    unusable = [k for k, _ in OUTCOMES if not cov[k]["usable"]]
    print(f"[PART A] usable outcome metrics: {usable}")
    print(f"[PART A] UNUSABLE (coverage): {unusable}")

    cont = continuous_battery(df, usable)
    cat = categorical_battery(df, usable)
    ladder = rank_features(cont)
    h1, h2 = era_halves(df)

    out = {
        "as_of": str(GRADE_ASOF.date()),
        "instrument": "rank_feature_battery",
        "what_this_is": (
            "WITHIN-ADMITTED-POOL ordering measurement on one era (cn_standout_v1 "
            "legacy board, 12 graded admission dates, 407 matured episodes) plus a "
            "12-month S-COIL port retro. In-sample, no multiplicity correction, no "
            "promotion authority. Motivates pre-registrations only."
        ),
        "fences": {
            "dnr_1747_amendment3": (
                "Washout DEPTH ranking is KILLED (Entry-stack Amendment-3, #1747: "
                "multi-TF stoch washout depth behind a fire = H1 FAIL, +3.5pp stop "
                "tax, w2_deep ~ 0 alone). dd_from_high and washout_2w are graded here "
                "for completeness ONLY; any positive read is not a revival and can "
                "re-enter only via a composite + fresh prereg."
            ),
            "dnr_114_115": (
                "DO_NOT_REBUILD rows 114-115 (W3 fingerprint census / W4 matched "
                "controls) established that nothing measurable today identifies the "
                "future winner PRE-ONSET. This battery orders a pool the board has "
                "ALREADY admitted. It makes no universe-level pre-onset claim and "
                "may not be cited as one."
            ),
            "esx_s9_dt_r5": (
                "ESX section 9: 'Release-bar-only definition frozen pre-run; an "
                "\"arming\" variant is BANNED from the family.' DT-R5 kills the "
                "5-definition void-box family because 'the \"inside/armed\" state is "
                "the BANNED arming variant (ESX section 9)'. PART B grades the "
                "RELEASE BAR ONLY. PART A's compression columns are internal ordering "
                "features over an already-admitted pool -- never surfaced, ranked, or "
                "reported as an 'armed' read. See RANK_FEATURE_BATTERY.md."
            ),
        },
        "reproduction": meta["reproduction"],
        "era_halves": {"h1_dates": h1, "h2_dates": h2},
        "outcome_coverage": cov,
        "theme_coverage": theme_cov,
        "compression_fire_counts": meta["compression_fire_counts"],
        "compression_vs_existing_coiled_flags": compression_vs_coiled(df),
        "feature_collinearity_spearman": collinearity(df),
        "continuous_battery": cont,
        "categorical_battery": cat,
        "ordering_ladder_by_abs_demeaned_ic_on_excess_h10": ladder["ranked"],
        "ordering_ladder_not_rankable": ladder["not_rankable"],
        "ordering_ladder_min_dates_gate": ladder["min_dates_gate"],
        "multiplicity": multiplicity_block(cont, cat, usable),
        "part_b_scoil_cn_retro": part_b(),
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    print(f"wrote {OUT}")
    print(f"\n[PART A] not rankable ({len(ladder['not_rankable'])}): "
          + ", ".join(f"{r['feature']}({r.get('reason')})"
                      for r in ladder["not_rankable"]))
    print("\nTop 12 by |date-demeaned IC| on excess_h10:")
    for r in ladder["ranked"][:12]:
        print(f"  {r['feature']:24s} {r['demeaned_ic']!s:>8s}  "
              f"pooled {r['pooled_ic']!s:>8s}  halves "
              f"{r['h1_ic']!s:>8s}/{r['h2_ic']!s:>8s}  "
              f"agree={r['sign_agree']}  n_dates={r['n_dates']}")
    print(f"\ntotal runtime {time.time() - t_start:.1f}s")


if __name__ == "__main__":
    main()
