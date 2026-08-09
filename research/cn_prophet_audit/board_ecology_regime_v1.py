#!/usr/bin/env python3
"""board_ecology_regime_v1.py — CN board-ecology / regime instruments v1 (CN LIMIT-MOVE ALPHA, W1).

WHAT THIS IS
    A MEASUREMENT instrument, display/audit tier.  ``limit_move_footprint_v0`` established
    that the base rate of the 打板 game is an ERA ARTIFACT: main-board first-board ->
    second-board continuation swings 7.93% (2011) to 24.18% (2015), a 3x regime swing that
    dominates every per-name feature it measured (best stable holdout lift 3.93x).  This
    instrument builds the market-level dials the 打板 ecosystem actually watches, from our
    own tape, and measures how much continuation probability each one carries.

      STAGE A  PANEL — the v0 detector, re-used verbatim in convention, plus one addition:
               the daily bar's HIGH, which v0 deliberately did not read.  The high is the
               only daily-visible trace of a broken seal (炸板).
      STAGE B  INSTRUMENTS — six daily board-level series, 2011 -> latest, plus rolling and
               de-trended forms.  Committed as board_ecology_series_v1.parquet.  This is the
               deliverable even if every measurement below nulls.
      STAGE C  M1 REGIME CONDITIONALS — P(first board at T -> board at T+1) by quintile of
               each instrument measured at T.  Fit/holdout split, by-year stability, a
               WITHIN-YEAR re-quantile that removes the era clock entirely, and a double
               sort of the top two.
      STAGE D  M2 LADDER-LEADER CASCADE — the practitioner's 高标断板, 情绪退潮 claim,
               measured rather than assumed, with the circular version of the same
               statistic printed beside the non-circular one.
      STAGE E  M3 炸板率 AS A DIAL.
      STAGE F  M4 DAY-OF-WEEK, era-controlled (the weekend-fermentation hypothesis).
      STAGE G  M5 ZT_POOL CROSS-VALIDATION — how biased our curated-universe dials are
               against an independent market-wide vendor scrape.  Mandatory honesty probe.
      STAGE H  M6 2015 / 2024 SANITY — if these dials do not light up in the two known
               manias, they are broken.

WHAT IT IS NOT
    Not a promotion, not a gate, not a ranker.  Nothing here sizes, ranks or admits
    anything.  No number is pooled across board types.  ChiNext is never pooled across its
    2020-08-24 band change.  Every null is printed rather than hidden, and the ORE LEDGER in
    the receipt names what was NOT tested so a null here is never read as a closed door.

CONVENTIONS — REUSED FROM v0, NOT REINVENTED
    Board and limit width come from ``engine.china_microstructure`` (imported):
    ``_board_from_ticker`` and ``limit_width_for_date``.  PRIMARY limit-up close is v0's
    adjudicated primary, ``close >= round(prev_close*(1+w), 2) * (1 - 0.002)``; the strict
    column rides beside it.  Exclusions, the 10-calendar-day pair rule, Wilson 95% and the
    n<20 THIN label are v0's, unchanged.

Run from repo root:  TZ=UTC python3 research/cn_prophet_audit/board_ecology_regime_v1.py
Outputs (frozen, committed):
    research/cn_prophet_audit/BOARD_ECOLOGY_REGIME_V1_2026-08-08.json
    research/cn_prophet_audit/board_ecology_series_v1.parquet
    research/cn_prophet_audit/BOARD_ECOLOGY_REGIME_V1_2026-08-08.md  (hand-written from the JSON)
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import OrderedDict
from pathlib import Path

os.environ["TZ"] = "UTC"
try:
    time.tzset()
except AttributeError:  # pragma: no cover - non-POSIX
    pass

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from engine.china_microstructure import (  # noqa: E402
    CHINEXT_STAR_IPO_WINDOW,
    CHINEXT_WIDE_DATE,
    IPO_PRE2014_DATE,
    LIMIT_TAPE_START_DATE,
    PRE2014_IPO_WINDOW,
    ST_STORE_COVERAGE_DATE,
    _board_from_ticker,
    limit_width_for_date,
)

DATA = REPO / "data"
OUT_DIR = REPO / "research" / "cn_prophet_audit"
OUT_JSON = OUT_DIR / "BOARD_ECOLOGY_REGIME_V1_2026-08-08.json"
OUT_PARQUET = OUT_DIR / "board_ecology_series_v1.parquet"

# ── frozen parameters (v0's, unchanged, plus this lane's own) ─────────────────

WINDOW_START = LIMIT_TAPE_START_DATE          # 2011-01-01
WINDOW_END = pd.Timestamp("2026-08-07")       # last bar in the raw store at build time

LIMIT_CLOSE_TOL = 0.002       # v0's adjudicated PRIMARY cushion (feed precision, not a widening)
NEAR_LIMIT_FRAC = 0.95        # v0's near-limit definition
MAX_PAIR_GAP_DAYS = 10        # v0's suspension-aware pair rule
THIN_CELL_N = 20              # v0's THIN label
SPLIT_DATE = pd.Timestamp("2021-11-26")       # v0's global 70/30 date split, pinned

N_QUINTILES = 5
MA_WINDOW = 5                 # the practitioner's rolling window
MA_MIN_PERIODS = 3
DETREND_WINDOW = 250          # trailing-session median for the de-trended (rel250) forms
DETREND_MIN_PERIODS = 60

# M2 — DECLARED BEFORE THE MEASUREMENT RAN.  A "leader" at ladder 1 or 2 is not a 高标;
# the headline stratum is H >= 4 and H >= 3 / H >= 5 are printed as sensitivity.
LEADER_H_HEADLINE = 4
LEADER_H_STRATA = (3, 4, 5)

# The instrument set.  Every value is observable at that session's CLOSE — nothing here
# reads a bar after the conditioning date.
INSTRUMENTS = OrderedDict([
    ("i1_first_board_count", "names printing their FIRST board (连板 == 1) at d"),
    ("i1_first_board_count_ma5", "5-session mean of i1_first_board_count"),
    ("i1_first_board_count_rel250",
     "i1_first_board_count / its own trailing 250-session median (era-normalised)"),
    ("i2_limit_up_total", "all limit-up closes at d, any ladder"),
    ("i2_limit_down_total", "all limit-down closes at d"),
    ("i2_net_breadth", "i2_limit_up_total - i2_limit_down_total"),
    ("i2_limit_up_total_rel250",
     "i2_limit_up_total / its own trailing 250-session median (era-normalised)"),
    ("i3_max_active_ladder", "the 高标 height: max 连板 N across all names limit-up at d"),
    ("i4_zhaban_count", "炸板 proxy: names whose HIGH reached the band but did not close there"),
    ("i4_zhaban_rate", "i4_zhaban_count / (i4_zhaban_count + i2_limit_up_total)"),
    ("i4_zhaban_rate_ma5", "5-session mean of i4_zhaban_rate"),
    ("i5_realized_continuation",
     "of the names whose PRIOR usable bar was a limit-up close, the share closing limit-up at d"),
    ("i5_realized_continuation_ma5", "5-session mean of i5_realized_continuation"),
    ("i6_near_limit_count", "names with return >= 0.95*w at d that did not close at the limit"),
])

COUNT_INSTRUMENTS = (
    "i1_first_board_count", "i2_limit_up_total", "i2_limit_down_total",
    "i2_net_breadth", "i4_zhaban_count", "i6_near_limit_count",
)

CONVENTION_NOTE = (
    "Board + width resolved by engine.china_microstructure.limit_width_for_date / "
    "_board_from_ticker (imported, never reimplemented). The per-bar event test is "
    "vectorised, and is v0's — see limit_move_footprint_v0.detect_ticker, whose STAGE 0 "
    "parity gate pins it against the module's own row loop at 100% recall on a 25-ticker "
    "sample. This instrument adds exactly one column that v0 did not read: the bar's HIGH, "
    "used for the 炸板 touch-fail proxy."
)


# ── small helpers (v0's, unchanged) ──────────────────────────────────────────

def streak_lengths(flags: np.ndarray) -> np.ndarray:
    """Vectorised consecutive-True run length ending at each position."""
    f = np.asarray(flags, dtype=bool)
    n = f.size
    if n == 0:
        return np.zeros(0, dtype=np.int32)
    idx = np.arange(1, n + 1, dtype=np.int64)
    reset = np.where(~f, idx, 0)
    np.maximum.accumulate(reset, out=reset)
    out = idx - reset
    out[~f] = 0
    return out.astype(np.int32)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for a binomial rate. None when n == 0."""
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))


def jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, float):
        return None if (np.isnan(obj) or np.isinf(obj)) else obj
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    if obj is pd.NaT:
        return None
    return obj


def rate_block(k: int, n: int) -> dict:
    ci = wilson(int(k), int(n))
    return {
        "n": int(n), "k": int(k),
        "rate_pct": round(100.0 * k / n, 3) if n else None,
        "wilson95_pct": [round(100.0 * ci[0], 3), round(100.0 * ci[1], 3)] if ci else None,
        "thin": bool(n < THIN_CELL_N),
    }


def quantile_edges(values: np.ndarray, q: int) -> np.ndarray:
    """Interior cut points for q buckets, deduplicated.

    Bucketing is ON VALUES, not on row order (v0's correction).  Count instruments are
    heavily tied, so the realised bucket count is often < q and is always reported rather
    than assumed.
    """
    v = np.asarray(values, dtype="float64")
    v = v[np.isfinite(v)]
    if v.size == 0:
        return np.zeros(0)
    cuts = np.quantile(v, [i / q for i in range(1, q)])
    return np.unique(cuts)


def assign_bucket(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Bucket index by searchsorted; NaN -> -1."""
    v = np.asarray(values, dtype="float64")
    out = np.searchsorted(edges, v, side="right").astype(np.int32)
    out[~np.isfinite(v)] = -1
    return out


# ── STAGE A — universe, exclusions, per-ticker detection ─────────────────────

def load_st_cohort() -> tuple[frozenset[str], str]:
    """ST/*ST tickers, excluded wholesale (v0's rule, v0's reasoning)."""
    p = DATA / "china_st" / "st_snapshot.parquet"
    if not p.exists():
        return frozenset(), "st_snapshot.parquet MISSING — no ST exclusion applied"
    df = pd.read_parquet(p)
    tick = frozenset(df["ticker"].astype(str).tolist())
    asof = sorted(set(df["asof"].astype(str)))
    expected = ST_STORE_COVERAGE_DATE.strftime("%Y-%m-%d")
    matches = (len(asof) == 1 and asof[0] == expected)
    return tick, (
        f"n={len(tick)} tickers, asof {asof}; engine ST_STORE_COVERAGE_DATE={expected}; "
        f"still-single-date={matches}"
    )


def detect_ticker(ticker: str, df: pd.DataFrame, board: str) -> tuple[pd.DataFrame, dict]:
    """v0's vectorised detector plus the HIGH-based 炸板 touch flags.

    Runs over the FULL price history so nothing is seeded by a partial window, then returns
    only in-window rows.  Limit flags are forced False outside the window so no 连板 streak
    can be seeded by a pre-1996 bar, when the band did not exist.
    """
    stats = {"ipo_excluded": 0, "exdiv_excluded": 0, "zero_volume_excluded": 0,
             "bars_in_window": 0}
    if df is None or len(df) < 30:
        return pd.DataFrame(), stats

    df = df.sort_index()
    idx = pd.to_datetime(df.index)
    close = df["close"].to_numpy(dtype=np.float64)
    high = df["high"].to_numpy(dtype=np.float64)
    low = df["low"].to_numpy(dtype=np.float64)
    open_ = df["open"].to_numpy(dtype=np.float64)
    vol = df["volume"].to_numpy(dtype=np.float64)
    n = len(close)

    pc = np.roll(close, 1)
    pc[0] = np.nan

    if board == "chinext":
        width = np.where(
            idx.to_numpy() >= CHINEXT_WIDE_DATE.to_datetime64(),
            limit_width_for_date("chinext", CHINEXT_WIDE_DATE),
            limit_width_for_date("chinext", CHINEXT_WIDE_DATE - pd.Timedelta(days=1)))
    else:
        width = np.full(n, limit_width_for_date(board, WINDOW_END), dtype=np.float64)
    width = width.astype(np.float64)

    # --- exclusions, v0's set exactly ---
    excl = np.zeros(n, dtype=bool)

    ipo_window = 0
    if board in ("star", "chinext"):
        ipo_window = CHINEXT_STAR_IPO_WINDOW
    elif idx.min() < IPO_PRE2014_DATE:
        ipo_window = PRE2014_IPO_WINDOW
    ipo_mask = np.zeros(n, dtype=bool)
    if ipo_window:
        ipo_mask[:ipo_window] = True
        excl |= ipo_mask

    bad_pc = ~np.isfinite(pc) | (pc <= 0)
    excl |= bad_pc

    with np.errstate(invalid="ignore", divide="ignore"):
        open_move = np.abs(open_ - pc) / pc
    exdiv = np.isfinite(open_move) & (open_move > width * 1.5) & ~excl
    excl |= exdiv

    zero_vol = np.isfinite(vol) & (vol <= 0) & ~excl
    excl |= zero_vol

    with np.errstate(invalid="ignore"):
        lim_up = np.round(pc * (1.0 + width), 2)
        lim_down = np.round(pc * (1.0 - width), 2)
        ret = close / pc - 1.0

    in_win = np.asarray((idx >= WINDOW_START) & (idx <= WINDOW_END), dtype=bool)
    live = in_win & ~excl

    lu = live & np.isfinite(lim_up) & (close >= lim_up * (1.0 - LIMIT_CLOSE_TOL))
    ld = live & np.isfinite(lim_down) & (close <= lim_down * (1.0 + LIMIT_CLOSE_TOL))
    lu_strict = live & np.isfinite(lim_up) & (close >= lim_up)
    near_up = live & np.isfinite(ret) & (ret >= NEAR_LIMIT_FRAC * width) & ~lu

    # THE ONE ADDITION TO v0 — the intraday touch. The daily bar's only trace of a seal
    # that formed and broke. Both tolerances carried; the tolerant one is primary for the
    # same reason v0's tolerant CLOSE is primary (feed precision), and the strict column is
    # kept in full because the noise direction is not symmetric between a high and a close.
    touch = live & np.isfinite(lim_up) & (high >= lim_up * (1.0 - LIMIT_CLOSE_TOL))
    touch_strict = live & np.isfinite(lim_up) & (high >= lim_up)
    zhaban = touch & ~lu
    zhaban_strict = touch_strict & ~lu_strict

    lianban = streak_lengths(lu)

    # --- T -> T+1 pairing, suspension-aware (v0's rule) ---
    days = idx.to_numpy().astype("datetime64[D]").astype(np.int64)
    gap_next = np.r_[np.diff(days), np.iinfo(np.int64).max]
    pair_ok = gap_next <= MAX_PAIR_GAP_DAYS

    nxt_lu = np.r_[lu[1:], False]
    nxt_live = np.r_[live[1:], False]
    y_ok = pair_ok & nxt_live

    dates_np = idx.to_numpy()
    nxt_date = np.empty(n, dtype=dates_np.dtype)
    if n > 1:
        nxt_date[:-1] = dates_np[1:]
    nxt_date[-1] = np.datetime64("NaT")

    keep = in_win
    stats["ipo_excluded"] = int((ipo_mask & keep).sum())
    stats["exdiv_excluded"] = int((exdiv & keep).sum())
    stats["zero_volume_excluded"] = int((zero_vol & keep).sum())
    stats["bars_in_window"] = int(keep.sum())

    out = pd.DataFrame({
        "date": idx[keep],
        "ticker": ticker,
        "board": board,
        "live": live[keep],
        "limit_up": lu[keep],
        "limit_up_strict": lu_strict[keep],
        "limit_down": ld[keep],
        "near_limit_up": near_up[keep],
        "zhaban": zhaban[keep],
        "zhaban_strict": zhaban_strict[keep],
        "lianban": lianban[keep].astype(np.int16),
        "y_ok": y_ok[keep],
        "y_limit_up": nxt_lu[keep],
        "next_bar_date": nxt_date[keep],
    })
    return out, stats


def build_panel() -> tuple[pd.DataFrame, dict]:
    st_set, st_note = load_st_cohort()
    files = sorted((DATA / "china_stocks_raw").glob("*.parquet"))
    meta = {
        "raw_store": ("data/china_stocks_raw (nominal/unadjusted OHLCV — the correct basis; "
                      "data/china_stocks is split/dividend adjusted and would fabricate "
                      "limit misses)"),
        "files_found": len(files),
        "st_cohort": st_note,
        "st_excluded_tickers": len(st_set),
        "window": [WINDOW_START.strftime("%Y-%m-%d"), WINDOW_END.strftime("%Y-%m-%d")],
    }

    frames = []
    agg = {"ipo_excluded": 0, "exdiv_excluded": 0, "zero_volume_excluded": 0,
           "bars_in_window": 0}
    boards_seen, kept, skipped_st, skipped_thin = {}, 0, 0, 0
    for p in files:
        ticker = p.stem
        if ticker in st_set:
            skipped_st += 1
            continue
        board = _board_from_ticker(ticker)
        try:
            df = pd.read_parquet(p)
        except Exception:  # noqa: BLE001
            skipped_thin += 1
            continue
        out, stats = detect_ticker(ticker, df, board)
        if out.empty:
            skipped_thin += 1
            continue
        for k in agg:
            agg[k] += stats[k]
        boards_seen[board] = boards_seen.get(board, 0) + 1
        frames.append(out)
        kept += 1

    meta.update({
        "tickers_kept": kept,
        "tickers_skipped_st": skipped_st,
        "tickers_skipped_thin_or_unreadable": skipped_thin,
        "board_counts": boards_seen,
        "excluded_bars": agg,
    })

    panel = pd.concat(frames, ignore_index=True)
    panel["ticker"] = panel["ticker"].astype("category")
    panel["board"] = panel["board"].astype("category")
    panel["year"] = panel["date"].dt.year.astype(np.int16)
    meta["panel_rows"] = len(panel)
    meta["live_rows"] = int(panel["live"].sum())
    meta["limit_up_primary"] = int(panel["limit_up"].sum())
    meta["limit_up_strict"] = int(panel["limit_up_strict"].sum())
    meta["zhaban_primary"] = int(panel["zhaban"].sum())
    meta["zhaban_strict"] = int(panel["zhaban_strict"].sum())

    raw_names = {p.stem for p in files}
    gap = {"raw_store_names": len(raw_names), "st_snapshot_names": len(st_set),
           "st_names_present_in_raw": len(st_set & raw_names)}
    zp = DATA / "china_zt_pool" / "pool.parquet"
    if zp.exists():
        zt_names = set(pd.read_parquet(zp)["ticker"].astype(str))
        gap.update({
            "zt_pool_names": len(zt_names),
            "zt_pool_names_present_in_raw": len(zt_names & raw_names),
            "zt_pool_names_present_pct": round(
                100.0 * len(zt_names & raw_names) / max(1, len(zt_names)), 1),
        })
    gap["reading"] = (
        "The two store-measured probes of how far the raw universe falls short of the listed "
        "A-share market. M5 turns the second one into a MEASURED undercount factor on the "
        "regime dials themselves, which is the number this lane actually owes the program."
    )
    meta["universe_gap"] = gap
    return panel, meta


# ── STAGE B — the daily instrument series ────────────────────────────────────

def build_series(panel: pd.DataFrame) -> pd.DataFrame:
    """Six board-level daily instruments + rolling and de-trended forms.

    Every column is observable at that session's own close.  Counts are 0 on a session with
    no events (a real zero); RATES are null when their denominator is empty (not zero) —
    an empty denominator is an absence of information, not a rate of 0.
    """
    live = panel[panel["live"]]
    key = ["board", "date"]

    base = live.groupby(key, observed=True).agg(
        n_live_names=("ticker", "size"),
        i2_limit_up_total=("limit_up", "sum"),
        i2_limit_down_total=("limit_down", "sum"),
        i4_zhaban_count=("zhaban", "sum"),
        i4_zhaban_count_strict=("zhaban_strict", "sum"),
        i6_near_limit_count=("near_limit_up", "sum"),
        limit_up_strict_total=("limit_up_strict", "sum"),
    )

    lu = live[live["limit_up"]]
    i1 = lu[lu["lianban"] == 1].groupby(key, observed=True).size().rename("i1_first_board_count")
    i3 = lu.groupby(key, observed=True)["lianban"].max().rename("i3_max_active_ladder")

    # i5 — indexed by the TARGET date (the session the continuation printed on), which is
    # what a practitioner reads off the tape at that close.  A name whose next usable bar is
    # not the very next session lands on the session it actually traded, by construction.
    pr = live[live["limit_up"] & live["y_ok"]]
    i5 = pr.groupby(["board", "next_bar_date"], observed=True)["y_limit_up"].agg(
        i5_k="sum", i5_pairs_n="size")
    i5.index = i5.index.set_names(["board", "date"])

    ser = base.join([i1, i3], how="left").join(i5, how="left").reset_index()
    ser["i1_first_board_count"] = ser["i1_first_board_count"].fillna(0).astype(np.int32)
    ser["i3_max_active_ladder"] = ser["i3_max_active_ladder"].fillna(0).astype(np.int32)
    ser["i5_pairs_n"] = ser["i5_pairs_n"].fillna(0).astype(np.int32)
    ser["i5_k"] = ser["i5_k"].fillna(0).astype(np.int32)
    for c in ("i2_limit_up_total", "i2_limit_down_total", "i4_zhaban_count",
              "i4_zhaban_count_strict", "i6_near_limit_count", "limit_up_strict_total"):
        ser[c] = ser[c].astype(np.int32)

    ser["i2_net_breadth"] = (ser["i2_limit_up_total"] - ser["i2_limit_down_total"]).astype(np.int32)

    denom = ser["i4_zhaban_count"] + ser["i2_limit_up_total"]
    ser["i4_zhaban_rate"] = np.where(denom > 0, ser["i4_zhaban_count"] / denom, np.nan)
    denom_s = ser["i4_zhaban_count_strict"] + ser["limit_up_strict_total"]
    ser["i4_zhaban_rate_strict"] = np.where(
        denom_s > 0, ser["i4_zhaban_count_strict"] / denom_s, np.nan)
    ser["i5_realized_continuation"] = np.where(
        ser["i5_pairs_n"] > 0, ser["i5_k"] / ser["i5_pairs_n"], np.nan)

    ser = ser.sort_values(["board", "date"]).reset_index(drop=True)
    ser["board"] = ser["board"].astype(str)

    out = []
    for board, g in ser.groupby("board", sort=True):
        g = g.sort_values("date").copy()
        g["session_index"] = np.arange(len(g), dtype=np.int32)
        for col, tgt in (("i1_first_board_count", "i1_first_board_count_ma5"),
                         ("i4_zhaban_rate", "i4_zhaban_rate_ma5"),
                         ("i5_realized_continuation", "i5_realized_continuation_ma5")):
            g[tgt] = g[col].rolling(MA_WINDOW, min_periods=MA_MIN_PERIODS).mean()
        for col in ("i1_first_board_count", "i2_limit_up_total"):
            med = g[col].rolling(DETREND_WINDOW, min_periods=DETREND_MIN_PERIODS).median()
            g[f"{col}_rel250"] = np.where(med > 0, g[col] / med, np.nan)
        g["year"] = g["date"].dt.year.astype(np.int16)
        g["dow"] = g["date"].dt.dayofweek.astype(np.int8)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def series_receipt(ser: pd.DataFrame) -> dict:
    rows = []
    for board, g in ser.groupby("board", sort=True):
        rec = {
            "board": board,
            "sessions": len(g),
            "first_session": g["date"].min().strftime("%Y-%m-%d"),
            "last_session": g["date"].max().strftime("%Y-%m-%d"),
        }
        for c in ("i1_first_board_count", "i2_limit_up_total", "i2_limit_down_total",
                  "i3_max_active_ladder", "i4_zhaban_count", "i6_near_limit_count"):
            rec[f"{c}__mean"] = round(float(g[c].mean()), 3)
            rec[f"{c}__max"] = int(g[c].max())
        for c in ("i4_zhaban_rate", "i5_realized_continuation"):
            rec[f"{c}__mean"] = round(float(g[c].mean(skipna=True)), 5)
            rec[f"{c}__null_sessions"] = int(g[c].isna().sum())
        rows.append(rec)
    return {"by_board": rows}


# ── STAGE C — M1 regime conditionals ─────────────────────────────────────────

def _bucket_stats(rows: pd.DataFrame, ycol: str, dates_in_bucket: int,
                  lo: float, hi: float) -> dict:
    n, k = len(rows), int(rows[ycol].sum())
    rec = rate_block(k, n)
    rec["n_dates"] = int(dates_in_bucket)
    rec["value_lo"] = None if not np.isfinite(lo) else round(float(lo), 4)
    rec["value_hi"] = None if not np.isfinite(hi) else round(float(hi), 4)
    # PER-DATE-FIRST estimator — the analogue of v0's per-name-first column. Outcomes inside
    # a single session are massively correlated (that is the whole subject of this lane), so
    # the pooled cell is dominated by the largest sessions.  Each date contributes one rate.
    if n:
        per = rows.groupby("date", observed=True)[ycol].agg(["size", "sum"])
        r = per["sum"] / per["size"]
        rec["per_date_median_pct"] = round(100.0 * float(r.median()), 3)
        rec["per_date_mean_pct"] = round(100.0 * float(r.mean()), 3)
        rec["per_date_n"] = int(len(per))
    else:
        rec["per_date_median_pct"] = None
        rec["per_date_mean_pct"] = None
        rec["per_date_n"] = 0
    return rec


def _quintile_table(rows: pd.DataFrame, dser: pd.DataFrame, instr: str,
                    edges: np.ndarray, ycol: str) -> dict:
    """Bucket DATES by the instrument, then pool the rows inside each bucket."""
    d = dser[["date", instr]].dropna(subset=[instr]).copy()
    if d.empty or edges.size == 0:
        return {"status": "no usable dates", "buckets": []}
    d["bucket"] = assign_bucket(d[instr].to_numpy(), edges)
    r = rows.merge(d[["date", "bucket", instr]], on="date", how="inner")
    if r.empty:
        return {"status": "no rows on bucketed dates", "buckets": []}
    date_counts = d.groupby("bucket").agg(n=("date", "size"), lo=(instr, "min"),
                                          hi=(instr, "max"))
    buckets = []
    for b, gg in r.groupby("bucket", observed=True):
        info = date_counts.loc[b] if b in date_counts.index else None
        buckets.append({
            "bucket": int(b),
            **_bucket_stats(gg, ycol,
                            int(info["n"]) if info is not None else 0,
                            float(info["lo"]) if info is not None else np.nan,
                            float(info["hi"]) if info is not None else np.nan),
        })
    buckets.sort(key=lambda x: x["bucket"])
    if len(buckets) >= 2:
        top, bot = buckets[-1], buckets[0]
        spread = (round(top["rate_pct"] / bot["rate_pct"], 3)
                  if (top["rate_pct"] and bot["rate_pct"]) else None)
        pd_spread = (round(top["per_date_median_pct"] / bot["per_date_median_pct"], 3)
                     if (top["per_date_median_pct"] and bot["per_date_median_pct"]) else None)
    else:
        spread = pd_spread = None
    return {
        "realised_buckets": len(buckets),
        "buckets": buckets,
        "top_over_bottom_spread": spread,
        "top_over_bottom_spread_per_date": pd_spread,
        "monotonicity_rho": _bucket_monotonicity(buckets),
        "min_bucket_dates": min((b["n_dates"] for b in buckets), default=0),
        "rows": len(r),
    }


def _bucket_monotonicity(buckets: list[dict]) -> float | None:
    """Spearman rho between bucket index and bucket rate.

    A top-over-bottom ratio can be produced by one freak end bucket. Rho across every
    realised bucket says whether the instrument is a GRADIENT or a corner artefact, and the
    two disagree often enough here to be worth printing side by side.
    """
    r = [b["rate_pct"] for b in buckets if b["rate_pct"] is not None]
    if len(r) < 3:
        return None
    x = pd.Series(range(len(r)), dtype="float64")
    y = pd.Series(r, dtype="float64")
    v = x.corr(y, method="spearman")
    return None if pd.isna(v) else round(float(v), 3)


def _within_year_table(rows: pd.DataFrame, dser: pd.DataFrame, instr: str,
                       ycol: str) -> dict:
    """Re-quantile the instrument WITHIN each calendar year, then pool by bucket.

    THE ERA CONTROL THAT MATTERS.  v0 established that the base rate swings 3x by era, and
    every count instrument here also grows with the universe (811 names in 2011 -> 1,243 in
    2026).  A raw-value quintile is therefore partly an era clock.  Bucketing inside the
    year removes the clock entirely: if the spread survives here, the instrument carries
    something beyond 'which year is it'.
    """
    d = dser[["date", "year", instr]].dropna(subset=[instr]).copy()
    if d.empty:
        return {"status": "no usable dates"}
    parts, per_year = [], []
    for y, g in d.groupby("year", sort=True):
        e = quantile_edges(g[instr].to_numpy(), N_QUINTILES)
        if e.size == 0:
            continue
        gg = g.copy()
        gg["bucket"] = assign_bucket(gg[instr].to_numpy(), e)
        parts.append(gg)
        ry = rows.merge(gg[["date", "bucket"]], on="date", how="inner")
        if ry.empty:
            continue
        tb, bb = int(ry["bucket"].max()), int(ry["bucket"].min())
        if tb == bb:
            continue
        t, b = ry[ry["bucket"] == tb], ry[ry["bucket"] == bb]
        tr, br = float(t[ycol].mean()), float(b[ycol].mean())
        per_year.append({
            "year": int(y), "n_top": len(t), "n_bottom": len(b),
            "top_pct": round(100.0 * tr, 3), "bottom_pct": round(100.0 * br, 3),
            "ratio": round(tr / br, 3) if br > 0 else None,
            "diff_pp": round(100.0 * (tr - br), 3),
        })
    if not parts:
        return {"status": "no year had usable edges"}
    d2 = pd.concat(parts, ignore_index=True)
    r = rows.merge(d2[["date", "bucket"]], on="date", how="inner")
    if r.empty:
        return {"status": "no rows"}
    date_counts = d2.groupby("bucket").size()
    buckets = []
    for b, gg in r.groupby("bucket", observed=True):
        buckets.append({"bucket": int(b),
                        **_bucket_stats(gg, ycol, int(date_counts.get(b, 0)),
                                        np.nan, np.nan)})
    buckets.sort(key=lambda x: x["bucket"])
    spread = None
    if len(buckets) >= 2 and buckets[0]["rate_pct"] and buckets[-1]["rate_pct"]:
        spread = round(buckets[-1]["rate_pct"] / buckets[0]["rate_pct"], 3)
    # THE FULLY ERA-NEUTRAL COLUMN. The pooled within-year number above still weights years
    # by their row count, so a mania year with ten times the first boards dominates it. This
    # one gives every year one vote.
    yew = {"years_scored": len(per_year)}
    if per_year:
        ratios = [p["ratio"] for p in per_year if p["ratio"] is not None]
        diffs = [p["diff_pp"] for p in per_year]
        direction_up = (spread or 1.0) > 1.0
        yew.update({
            "median_ratio": round(float(np.median(ratios)), 3) if ratios else None,
            "mean_diff_pp": round(float(np.mean(diffs)), 3),
            "median_diff_pp": round(float(np.median(diffs)), 3),
            "years_in_pooled_direction": sum(
                1 for p in per_year if (p["diff_pp"] > 0) == direction_up),
            "per_year": per_year,
        })
    return {"buckets": buckets, "top_over_bottom_spread": spread,
            "monotonicity_rho": _bucket_monotonicity(buckets),
            "year_equal_weight": yew,
            "note": ("quintile edges recomputed inside each calendar year, so bucket "
                     "membership carries no era information. Read year_equal_weight beside "
                     "the pooled spread: the pooled one still weights years by row count.")}


def _by_year_stability(rows: pd.DataFrame, dser: pd.DataFrame, instr: str,
                       edges: np.ndarray, ycol: str, global_spread: float | None) -> dict:
    if global_spread is None:
        global_spread = 1.0
    d = dser[["date", instr]].dropna(subset=[instr]).copy()
    d["bucket"] = assign_bucket(d[instr].to_numpy(), edges)
    # BOTTOM is the lowest OCCUPIED bucket, not literal 0. When the 20th percentile equals the
    # instrument's floor (every count instrument whose p20 is 0, and i5 whose p20 is 0.0),
    # searchsorted(..., side="right") can never return 0, so a hardcoded 0 makes every bottom
    # cell empty and every yearly spread None.
    # rows already carries `year`; merging dser's copy would collide into year_x/year_y
    r = rows.merge(d[["date", "bucket"]], on="date", how="inner")
    # Ends are taken from the ROWS, not the dates. i3_max_active_ladder's bucket 0 is
    # "no name held a board that session", which by construction contains zero first-board
    # rows — reading the ends off the date distribution would score every year as empty.
    top_b = int(r["bucket"].max()) if len(r) else 0
    bot_b = int(r["bucket"].min()) if len(r) else 0
    out = []
    for y, g in r.groupby("year", sort=True):
        t = g[g["bucket"] == top_b]
        b = g[g["bucket"] == bot_b]
        rec = {"year": int(y),
               "top_bucket": rate_block(int(t[ycol].sum()), len(t)),
               "bottom_bucket": rate_block(int(b[ycol].sum()), len(b))}
        tr, br = rec["top_bucket"]["rate_pct"], rec["bottom_bucket"]["rate_pct"]
        rec["spread"] = round(tr / br, 3) if (tr and br) else None
        out.append(rec)
    agreeing = sum(1 for r_ in out if r_["spread"] is not None
                   and (r_["spread"] - 1.0) * (global_spread - 1.0) > 0)
    scored = sum(1 for r_ in out if r_["spread"] is not None)
    return {
        "bucket_indices": {"bottom": bot_b, "top": top_b},
        "years": out,
        "years_scored": scored,
        "years_agreeing_with_pooled_direction": agreeing,
        "note": ("The yearly cells use the GLOBAL fit-window edges, so in a year whose "
                 "instrument distribution sits entirely inside one bucket the opposite end is "
                 "empty and the year is unscored. That is why "
                 "within_year_quintiles_full_window — which re-cuts inside each year and "
                 "therefore always populates both ends — is the better era control of the "
                 "two, and this table is the coarser cross-check."),
    }


def _double_sort(rows: pd.DataFrame, dser: pd.DataFrame, a: str, b: str,
                 ea: np.ndarray, eb: np.ndarray, ycol: str, q: int) -> dict:
    d = dser[["date", a, b]].dropna(subset=[a, b]).copy()
    if d.empty:
        return {"status": "no usable dates"}
    d["ba"] = assign_bucket(d[a].to_numpy(), ea)
    d["bb"] = assign_bucket(d[b].to_numpy(), eb)
    r = rows.merge(d[["date", "ba", "bb"]], on="date", how="inner")
    cells = []
    for (i, j), gg in r.groupby(["ba", "bb"], observed=True):
        rec = {"bucket_a": int(i), "bucket_b": int(j)}
        rec.update(rate_block(int(gg[ycol].sum()), len(gg)))
        rec["n_dates"] = int(d[(d["ba"] == i) & (d["bb"] == j)].shape[0])
        cells.append(rec)
    cells.sort(key=lambda c: (c["bucket_a"], c["bucket_b"]))
    return {"grid": f"{q}x{q}", "instrument_a": a, "instrument_b": b, "cells": cells,
            "thin_cells": sum(1 for c in cells if c["thin"]), "total_cells": len(cells)}


def m1_regime_conditionals(panel: pd.DataFrame, ser: pd.DataFrame) -> dict:
    """P(first board at T -> board at T+1) by quintile of each instrument AT T."""
    live = panel[panel["live"] & panel["y_ok"]]
    fb_all = live[live["limit_up"] & (live["lianban"] == 1)][
        ["date", "board", "ticker", "y_limit_up", "year"]].copy()
    fb_all["board"] = fb_all["board"].astype(str)

    out = {
        "unit": "one row per (name, T) where the name printed its FIRST board at T and has a "
                "usable T+1 bar; outcome = the name closes limit-up again at T+1",
        "instrument_timing": "every instrument is measured at T's CLOSE — no value in this "
                             "stage reads a bar after T",
        "bucketing": f"DATES are quantiled into {N_QUINTILES} buckets on the instrument's "
                     f"VALUE (edges fitted on the pre-{SPLIT_DATE:%Y-%m-%d} window and applied "
                     f"unchanged to the holdout), then the rows on those dates are pooled. "
                     f"Count instruments are heavily tied, so the REALISED bucket count is "
                     f"printed and is often < {N_QUINTILES}.",
        "self_inclusion_note": (
            "A conditioned row is itself one of the day's first boards, so it adds exactly +1 "
            "to i1 and i2 on EVERY conditioned row. That is a constant shift, not a "
            "differential bias, and no leave-one-out is applied. i3 is the one exception: a "
            "first board can only BE the max ladder on a day whose max ladder is 1, which is "
            "a small and separately visible set of sessions."),
        "clustering_warning": (
            "THE WILSON INTERVALS BELOW ARE UNDERSTATED AND ARE PRINTED ONLY BY HOUSE "
            "CONVENTION. Outcomes inside one session are massively correlated — that "
            "correlation is the entire subject of this lane — so the effective sample size of "
            "a bucket is closer to its n_dates than to its n. Read n_dates and the "
            "per-date-first column, not the interval."),
        "boards": {},
    }

    for board, era_note, era_mask in (
        ("main", "full window 2011-01-01 -> 2026-08-07", None),
        ("chinext", f"±20% band era only, on/after CHINEXT_WIDE_DATE "
                    f"{CHINEXT_WIDE_DATE:%Y-%m-%d} — ChiNext is NEVER pooled across its band "
                    f"change", CHINEXT_WIDE_DATE),
    ):
        dser = ser[ser["board"] == board].copy()
        rows = fb_all[fb_all["board"] == board].copy()
        if era_mask is not None:
            dser = dser[dser["date"] >= era_mask]
            rows = rows[rows["date"] >= era_mask]
        if rows.empty:
            out["boards"][board] = {"status": "no rows"}
            continue

        split = SPLIT_DATE if era_mask is None else pd.Timestamp(
            np.sort(dser["date"].unique())[int(len(dser) * 0.70)])
        fit_d, hold_d = dser[dser["date"] < split], dser[dser["date"] >= split]
        fit_r, hold_r = rows[rows["date"] < split], rows[rows["date"] >= split]

        entry = {
            "era": era_note,
            "split_date": split.strftime("%Y-%m-%d"),
            "fit_sessions": len(fit_d), "holdout_sessions": len(hold_d),
            "fit_rows": len(fit_r), "holdout_rows": len(hold_r),
            "fit_base_rate": rate_block(int(fit_r["y_limit_up"].sum()), len(fit_r)),
            "holdout_base_rate": rate_block(int(hold_r["y_limit_up"].sum()), len(hold_r)),
            "instruments": {},
        }
        ranked = []
        for instr in INSTRUMENTS:
            if instr not in dser.columns:
                continue
            edges = quantile_edges(fit_d[instr].to_numpy(), N_QUINTILES)
            if edges.size == 0:
                entry["instruments"][instr] = {"status": "no fit-window variation"}
                continue
            fit_t = _quintile_table(fit_r, fit_d, instr, edges, "y_limit_up")
            hold_t = _quintile_table(hold_r, hold_d, instr, edges, "y_limit_up")
            f_sp, h_sp = fit_t.get("top_over_bottom_spread"), hold_t.get("top_over_bottom_spread")
            stable = None
            if f_sp is not None and h_sp is not None:
                stable = (f_sp - 1.0) * (h_sp - 1.0) > 0
            rec = {
                "definition": INSTRUMENTS[instr],
                "fit": fit_t, "holdout": hold_t,
                "fit_spread": f_sp, "holdout_spread": h_sp,
                "sign_stable_fit_to_holdout": stable,
                "verdict": ("UNSTABLE" if stable is False else
                            ("stable-sign" if stable else "undetermined")),
                "within_year_quintiles_full_window": _within_year_table(
                    rows, dser, instr, "y_limit_up"),
                "by_year": _by_year_stability(rows, dser, instr, edges, "y_limit_up", h_sp),
            }
            entry["instruments"][instr] = rec
            if h_sp is not None and stable and h_sp > 0:
                # An INVERSE dial (spread < 1) is exactly as strong as its reciprocal, so
                # magnitude is max(sp, 1/sp) and the direction is carried separately. Ranking
                # on |sp - 1| would silently rank every inverse instrument last.
                ranked.append((round(max(h_sp, 1.0 / h_sp), 3), instr, h_sp,
                               rec["within_year_quintiles_full_window"].get(
                                   "top_over_bottom_spread"),
                               hold_t.get("monotonicity_rho"),
                               hold_t.get("min_bucket_dates")))
        ranked.sort(reverse=True)
        entry["ranked_by_holdout_spread"] = [
            {"instrument": i, "holdout_spread": s, "magnitude": mag,
             "direction": "higher -> MORE continuation" if s > 1 else
                          "higher -> LESS continuation",
             "within_year_spread": wy, "holdout_monotonicity_rho": rho,
             "min_bucket_dates": mbd}
            for mag, i, s, wy, rho, mbd in ranked]
        entry["instruments_total"] = len(entry["instruments"])
        entry["instruments_with_a_holdout_spread"] = sum(
            1 for r in entry["instruments"].values() if r.get("holdout_spread") is not None)
        entry["instruments_collapsed_to_one_bucket"] = sorted(
            k for k, r in entry["instruments"].items()
            if isinstance(r.get("holdout"), dict) and r["holdout"].get("realised_buckets") == 1)
        entry["ranking_note"] = (
            "magnitude = max(spread, 1/spread) so an inverse dial is not ranked last by "
            "construction. READ within_year_spread BESIDE IT: an instrument whose spread "
            "collapses toward 1.0 once the quintiles are recomputed inside each calendar "
            "year was measuring the era, not the ecology.")

        if len(ranked) >= 2:
            a, b = ranked[0][1], ranked[1][1]
            ea = quantile_edges(fit_d[a].to_numpy(), N_QUINTILES)
            eb = quantile_edges(fit_d[b].to_numpy(), N_QUINTILES)
            ds5 = _double_sort(hold_r, hold_d, a, b, ea, eb, "y_limit_up", N_QUINTILES)
            ea3 = quantile_edges(fit_d[a].to_numpy(), 3)
            eb3 = quantile_edges(fit_d[b].to_numpy(), 3)
            ds3 = _double_sort(hold_r, hold_d, a, b, ea3, eb3, "y_limit_up", 3)
            entry["double_sort_holdout"] = {
                "5x5": ds5, "3x3_collapse": ds3,
                "collapse_rule": (f"the {N_QUINTILES}x{N_QUINTILES} grid is reported first; "
                                  f"the 3x3 is the collapse the brief asks for where the "
                                  f"5x5 is THIN (n < {THIN_CELL_N})"),
            }
        out["boards"][board] = entry
    return out


# ── STAGE D — M2 ladder-leader cascade ───────────────────────────────────────

def m2_leader_cascade(panel: pd.DataFrame, ser: pd.DataFrame) -> dict:
    """The practitioner's 高标断板 -> 情绪退潮 claim, measured.

    Leader-failure day d: EVERY name that stood at the board's max active ladder on the
    previous session d-1, and that has a usable bar at d, fails to close limit-up at d.
    Leader-extend day: at least one of them holds.  A session where no leader has a usable
    bar at d is UNDEFINED and is counted, not silently dropped.
    """
    live = panel[panel["live"]]
    out = {
        "definitions": {
            "leader": "a name closing limit-up at d-1 whose 连板 equals that board's "
                      "i3_max_active_ladder at d-1",
            "leader_failure_day_d": "every leader with a usable bar at d fails to close "
                                    "limit-up at d",
            "leader_extend_day_d": "at least one such leader closes limit-up at d",
            "undefined": "no leader has a usable bar at d (suspension) — counted, not dropped",
            "H_strata": f"declared BEFORE the measurement: headline H >= {LEADER_H_HEADLINE}; "
                        f"H >= {LEADER_H_STRATA[0]} and H >= {LEADER_H_STRATA[2]} printed as "
                        f"sensitivity",
        },
        "circularity_warning": (
            "The same-day statistic r(d) INCLUDES the leaders themselves, so on a "
            "leader-failure day the leaders mechanically drag it down. That version is "
            "CIRCULAR and is printed only so the size of the artefact is visible. The "
            "load-bearing column is r_ex_leaders(d), which removes every leader from both "
            "numerator and denominator."),
        "boards": {},
    }

    for board in ("main", "chinext"):
        dser = ser[ser["board"] == board].sort_values("date").reset_index(drop=True)
        if board == "chinext":
            dser = dser[dser["date"] >= CHINEXT_WIDE_DATE].reset_index(drop=True)
        if len(dser) < 50:
            out["boards"][board] = {"status": "too few sessions"}
            continue
        sessions = dser["date"].to_numpy()
        prev_of = dict(zip(sessions[1:], sessions[:-1]))
        maxlad = dict(zip(dser["date"], dser["i3_max_active_ladder"]))

        b_live = live[live["board"].astype(str) == board]
        lu_pairs = b_live[b_live["limit_up"] & b_live["y_ok"]][
            ["date", "ticker", "lianban", "y_limit_up", "next_bar_date"]].copy()

        # leader rows: limit-up at d-1 at the board's max ladder, next bar == d
        lu_pairs["maxlad_at_date"] = lu_pairs["date"].map(maxlad)
        lu_pairs["is_leader"] = (lu_pairs["lianban"] == lu_pairs["maxlad_at_date"])

        # every T -> T+1 pair, indexed by the TARGET session
        tgt = lu_pairs.rename(columns={"next_bar_date": "target"})
        tgt = tgt[tgt["target"].notna()]

        day_rows = []
        grp = dict(list(tgt.groupby("target", observed=True)))
        for d in sessions[1:]:
            dprev = prev_of[d]
            H = int(maxlad.get(dprev, 0))
            g = grp.get(d)
            if g is None or g.empty:
                day_rows.append({"date": d, "H": H, "status": "no_pairs"})
                continue
            g_prev = g[g["date"] == dprev]
            lead = g_prev[g_prev["is_leader"]]
            nonlead = g[~((g["date"] == dprev) & g["is_leader"])]
            if lead.empty:
                status = "undefined_no_usable_leader"
            elif int(lead["y_limit_up"].sum()) == 0:
                status = "leader_fail"
            else:
                status = "leader_extend"
            day_rows.append({
                "date": d, "H": H, "status": status,
                "n_leaders": len(lead),
                "r_all_n": len(g), "r_all_k": int(g["y_limit_up"].sum()),
                "r_ex_n": len(nonlead), "r_ex_k": int(nonlead["y_limit_up"].sum()),
            })
        dd = pd.DataFrame(day_rows)
        dd["year"] = pd.to_datetime(dd["date"]).dt.year

        # next-day first-board outcomes, keyed by the first-board session
        fb = b_live[b_live["limit_up"] & (b_live["lianban"] == 1) & b_live["y_ok"]][
            ["date", "y_limit_up"]]
        fb_day = fb.groupby("date", observed=True)["y_limit_up"].agg(
            fb_n="size", fb_k="sum").reset_index()
        dd = dd.merge(fb_day, on="date", how="left")
        dd[["fb_n", "fb_k"]] = dd[["fb_n", "fb_k"]].fillna(0).astype(int)

        entry = {"sessions_examined": len(dd),
                 "status_counts": {k: int(v) for k, v in
                                   dd["status"].value_counts().items()},
                 "strata": {}}
        for hmin in LEADER_H_STRATA:
            sub = dd[(dd["H"] >= hmin) & dd["status"].isin(["leader_fail", "leader_extend"])]
            fail = sub[sub["status"] == "leader_fail"]
            ext = sub[sub["status"] == "leader_extend"]
            rec = {
                "H_min": hmin,
                "n_days_fail": len(fail), "n_days_extend": len(ext),
                "same_day_r_ex_leaders": {
                    "leader_fail": rate_block(int(fail["r_ex_k"].sum()),
                                              int(fail["r_ex_n"].sum())),
                    "leader_extend": rate_block(int(ext["r_ex_k"].sum()),
                                                int(ext["r_ex_n"].sum())),
                },
                "same_day_r_all_CIRCULAR": {
                    "leader_fail": rate_block(int(fail["r_all_k"].sum()),
                                              int(fail["r_all_n"].sum())),
                    "leader_extend": rate_block(int(ext["r_all_k"].sum()),
                                                int(ext["r_all_n"].sum())),
                },
                "next_day_first_to_second": {
                    "leader_fail": rate_block(int(fail["fb_k"].sum()),
                                              int(fail["fb_n"].sum())),
                    "leader_extend": rate_block(int(ext["fb_k"].sum()),
                                                int(ext["fb_n"].sum())),
                },
            }
            for blk in ("same_day_r_ex_leaders", "same_day_r_all_CIRCULAR",
                        "next_day_first_to_second"):
                a = rec[blk]["leader_fail"]["rate_pct"]
                b = rec[blk]["leader_extend"]["rate_pct"]
                rec[blk]["fail_over_extend"] = round(a / b, 3) if (a and b) else None
            # ERA CONTROL — the fail/extend mix is not flat across years, so the pooled
            # comparison is re-done with every year weighted equally.
            yr = []
            for y, g in sub.groupby("year", sort=True):
                f, e = g[g["status"] == "leader_fail"], g[g["status"] == "leader_extend"]
                fr = (f["r_ex_k"].sum() / f["r_ex_n"].sum()) if f["r_ex_n"].sum() else None
                er = (e["r_ex_k"].sum() / e["r_ex_n"].sum()) if e["r_ex_n"].sum() else None
                ffr = (f["fb_k"].sum() / f["fb_n"].sum()) if f["fb_n"].sum() else None
                efr = (e["fb_k"].sum() / e["fb_n"].sum()) if e["fb_n"].sum() else None
                yr.append({
                    "year": int(y), "days_fail": len(f), "days_extend": len(e),
                    "r_ex_fail_pct": round(100.0 * fr, 3) if fr is not None else None,
                    "r_ex_extend_pct": round(100.0 * er, 3) if er is not None else None,
                    "fb_fail_pct": round(100.0 * ffr, 3) if ffr is not None else None,
                    "fb_extend_pct": round(100.0 * efr, 3) if efr is not None else None,
                })
            rec["by_year"] = yr
            diffs = [(y["r_ex_fail_pct"] - y["r_ex_extend_pct"]) for y in yr
                     if y["r_ex_fail_pct"] is not None and y["r_ex_extend_pct"] is not None]
            fdiffs = [(y["fb_fail_pct"] - y["fb_extend_pct"]) for y in yr
                      if y["fb_fail_pct"] is not None and y["fb_extend_pct"] is not None]
            rec["year_equal_weight"] = {
                "years": len(diffs),
                "same_day_r_ex_mean_diff_pp": round(float(np.mean(diffs)), 3) if diffs else None,
                "same_day_r_ex_years_negative": int(sum(1 for x in diffs if x < 0)),
                "next_day_fb_mean_diff_pp": round(float(np.mean(fdiffs)), 3) if fdiffs else None,
                "next_day_fb_years_negative": int(sum(1 for x in fdiffs if x < 0)),
                "reading": "diff = leader-FAIL minus leader-EXTEND, in percentage points; "
                           "negative means the practitioner claim's direction",
            }
            entry["strata"][f"H_ge_{hmin}"] = rec
        out["boards"][board] = entry
    return out


# ── STAGE E — M3 炸板率 as a dial ────────────────────────────────────────────

def m3_zhaban_dial(panel: pd.DataFrame, ser: pd.DataFrame) -> dict:
    """r(d+1) and P(first->second) conditioned on the 炸板 rate at d."""
    live = panel[panel["live"]]
    out = {
        "claim_under_test": "practitioner claim — a high 炸板率 means fragile sentiment, so "
                            "tomorrow's continuation should be worse",
        "definitions": {
            "i4_zhaban_rate": "zhaban_count / (zhaban_count + limit_up_total) at d, where "
                              "zhaban = high reached the band (within the same 0.2% cushion "
                              "as the close test) and the close did not hold it",
            "r(d+1)": "i5_realized_continuation on the NEXT session of that board",
            "P(first->second)": "over first-board rows AT d, the share boarding again at "
                                "their next usable bar",
        },
        "robustness": "the whole table is re-run on i4_zhaban_rate_strict (high >= the exact "
                      "band, close < the exact band) because the feed-noise argument that "
                      "makes a tolerant CLOSE test right does not point the same way for a HIGH",
        "boards": {},
    }
    for board in ("main", "chinext"):
        dser = ser[ser["board"] == board].sort_values("date").reset_index(drop=True)
        if board == "chinext":
            dser = dser[dser["date"] >= CHINEXT_WIDE_DATE].reset_index(drop=True)
        if len(dser) < 100:
            out["boards"][board] = {"status": "too few sessions"}
            continue
        d = dser.copy()
        d["r_next"] = d["i5_realized_continuation"].shift(-1)
        d["r_next_n"] = d["i5_pairs_n"].shift(-1)

        b_live = live[live["board"].astype(str) == board]
        fb = b_live[b_live["limit_up"] & (b_live["lianban"] == 1) & b_live["y_ok"]][
            ["date", "y_limit_up", "year"]].copy()
        if board == "chinext":
            fb = fb[fb["date"] >= CHINEXT_WIDE_DATE]

        entry = {}
        for label, col in (("primary_tolerant", "i4_zhaban_rate"),
                           ("strict", "i4_zhaban_rate_strict")):
            fit = d[d["date"] < SPLIT_DATE] if board == "main" else d.iloc[:int(len(d) * 0.7)]
            edges = quantile_edges(fit[col].to_numpy(), N_QUINTILES)
            if edges.size == 0:
                entry[label] = {"status": "no fit-window variation"}
                continue
            dd = d.dropna(subset=[col]).copy()
            dd["bucket"] = assign_bucket(dd[col].to_numpy(), edges)
            split = fit["date"].max() if len(fit) else SPLIT_DATE

            def _rnext(frame: pd.DataFrame) -> tuple[list[dict], float | None]:
                rn = frame.dropna(subset=["r_next"])
                blocks = []
                for b, g in rn.groupby("bucket", observed=True):
                    k = float((g["r_next"] * g["r_next_n"]).sum())
                    n = float(g["r_next_n"].sum())
                    rec = {"bucket": int(b), "n_dates": len(g),
                           "value_lo": round(float(g[col].min()), 5),
                           "value_hi": round(float(g[col].max()), 5),
                           "per_date_median_r_next_pct": round(
                               100.0 * float(g["r_next"].median()), 3)}
                    rec.update(rate_block(int(round(k)), int(round(n))))
                    blocks.append(rec)
                blocks.sort(key=lambda x: x["bucket"])
                s = None
                if len(blocks) >= 2 and blocks[0]["rate_pct"] and blocks[-1]["rate_pct"]:
                    s = round(blocks[-1]["rate_pct"] / blocks[0]["rate_pct"], 3)
                return blocks, s

            rblocks, sp = _rnext(dd)
            rb_fit, sp_fit = _rnext(dd[dd["date"] <= split])
            rb_hold, sp_hold = _rnext(dd[dd["date"] > split])

            # ERA CONTROL for the r(d+1) channel, matching what M1 applies to the
            # first->second channel: re-quantile inside each calendar year and give every
            # year one vote. Without this the table cannot tell a real dial from an era clock.
            per_year = []
            for y, gy in dd.groupby("year", sort=True):
                ey = quantile_edges(gy[col].to_numpy(), N_QUINTILES)
                if ey.size == 0:
                    continue
                gy = gy.dropna(subset=["r_next"]).copy()
                if gy.empty:
                    continue
                gy["yb"] = assign_bucket(gy[col].to_numpy(), ey)
                tb, bb = int(gy["yb"].max()), int(gy["yb"].min())
                if tb == bb:
                    continue
                t, b = gy[gy["yb"] == tb], gy[gy["yb"] == bb]
                tn, bn = float(t["r_next_n"].sum()), float(b["r_next_n"].sum())
                if tn <= 0 or bn <= 0:
                    continue
                tr = float((t["r_next"] * t["r_next_n"]).sum()) / tn
                br = float((b["r_next"] * b["r_next_n"]).sum()) / bn
                per_year.append({"year": int(y), "n_top_pairs": int(tn),
                                 "n_bottom_pairs": int(bn),
                                 "top_pct": round(100.0 * tr, 3),
                                 "bottom_pct": round(100.0 * br, 3),
                                 "ratio": round(tr / br, 3) if br > 0 else None,
                                 "diff_pp": round(100.0 * (tr - br), 3)})
            yew = {"years_scored": len(per_year)}
            if per_year:
                rr = [p["ratio"] for p in per_year if p["ratio"] is not None]
                yew.update({
                    "median_ratio": round(float(np.median(rr)), 3) if rr else None,
                    "mean_diff_pp": round(float(np.mean([p["diff_pp"] for p in per_year])), 3),
                    "years_negative_diff": sum(1 for p in per_year if p["diff_pp"] < 0),
                    "per_year": per_year,
                })
            fbt = _quintile_table(fb, dd, col, edges, "y_limit_up")
            fbt_hold = _quintile_table(fb[fb["date"] > split], dd[dd["date"] > split],
                                       col, edges, "y_limit_up")
            entry[label] = {
                "r_next_by_bucket": rblocks,
                "r_next_top_over_bottom": sp,
                "r_next_monotonicity_rho": _bucket_monotonicity(rblocks),
                "r_next_fit_top_over_bottom": sp_fit,
                "r_next_holdout_top_over_bottom": sp_hold,
                "r_next_holdout_buckets": rb_hold,
                "r_next_fit_buckets": rb_fit,
                "r_next_sign_stable": (None if (sp_fit is None or sp_hold is None)
                                       else bool((sp_fit - 1.0) * (sp_hold - 1.0) > 0)),
                "r_next_within_year_equal_weight": yew,
                "first_to_second_by_bucket": fbt,
                "first_to_second_top_over_bottom": fbt.get("top_over_bottom_spread"),
                "first_to_second_monotonicity_rho": fbt.get("monotonicity_rho"),
                "first_to_second_holdout": fbt_hold,
                "split_date": split.strftime("%Y-%m-%d"),
                "split_note": ("quintile edges are fitted on the pre-split window only; the "
                               "full-window table is printed first and the fit/holdout split "
                               "beside it, because a full-window conditional could be carried "
                               "entirely by one era"),
            }
        out["boards"][board] = entry
    return out


# ── STAGE F — M4 day of week ─────────────────────────────────────────────────

DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}


def m4_day_of_week(panel: pd.DataFrame, ser: pd.DataFrame) -> dict:
    """r(d) by weekday, and P(first->second) by the weekday of the FIRST-BOARD session.

    The operator's weekend-fermentation hypothesis, at the aggregate level.  The sharp form
    is the second table: a first board printed on a FRIDAY has a weekend of attention before
    its continuation is graded, so the Friday cell is the one the hypothesis predicts.
    """
    live = panel[panel["live"]]
    out = {
        "hypothesis": "weekend fermentation — a board printed before a weekend gets two "
                      "non-trading days of attention accrual, so its continuation should be "
                      "stronger",
        "era_control": "pooled cells are printed with a YEAR-EQUAL-WEIGHT column beside them, "
                       "because the weekday mix of a mania year is not the weekday mix of a "
                       "quiet one and the pooled number would otherwise be an era average",
        "boards": {},
    }
    for board in ("main", "chinext"):
        dser = ser[ser["board"] == board].copy()
        if board == "chinext":
            dser = dser[dser["date"] >= CHINEXT_WIDE_DATE]
        b_live = live[live["board"].astype(str) == board]
        fb = b_live[b_live["limit_up"] & (b_live["lianban"] == 1) & b_live["y_ok"]][
            ["date", "y_limit_up", "year", "next_bar_date"]].copy()
        if board == "chinext":
            fb = fb[fb["date"] >= CHINEXT_WIDE_DATE]
        fb["dow"] = fb["date"].dt.dayofweek
        fb["gap_days"] = (fb["next_bar_date"] - fb["date"]).dt.days

        r_rows, fb_rows = [], []
        for dow, g in dser.groupby("dow", sort=True):
            k = float((g["i5_realized_continuation"] * g["i5_pairs_n"]).sum(skipna=True))
            n = float(g["i5_pairs_n"].sum())
            rec = {"dow": DOW_NAMES[int(dow)], "n_sessions": len(g)}
            rec.update(rate_block(int(round(k)), int(round(n))))
            per_year = g.groupby("year").apply(
                lambda x: (x["i5_realized_continuation"] * x["i5_pairs_n"]).sum()
                / x["i5_pairs_n"].sum() if x["i5_pairs_n"].sum() else np.nan,
                include_groups=False)
            per_year = per_year.dropna()
            rec["year_equal_weight_pct"] = (round(100.0 * float(per_year.mean()), 3)
                                            if len(per_year) else None)
            rec["years"] = int(len(per_year))
            r_rows.append(rec)

        for dow, g in fb.groupby("dow", sort=True):
            rec = {"dow": DOW_NAMES[int(dow)]}
            rec.update(rate_block(int(g["y_limit_up"].sum()), len(g)))
            per_year = g.groupby("year")["y_limit_up"].mean()
            rec["year_equal_weight_pct"] = round(100.0 * float(per_year.mean()), 3)
            rec["years"] = int(len(per_year))
            rec["per_date_median_pct"] = round(
                100.0 * float(g.groupby("date", observed=True)["y_limit_up"].mean().median()), 3)
            fb_rows.append(rec)

        # THE CONTROL THE HYPOTHESIS ACTUALLY NEEDS. "Weekend fermentation" is a claim about
        # NON-TRADING DAYS, not about Fridays. The calendar gap between a first board and the
        # session that grades it separates the two: gap 1 = a normal overnight, gap 3 = a
        # weekend, gap >= 4 = a public holiday. If the mechanism is real it should track the
        # gap, not the weekday label.
        # A gap of 4+ days has TWO possible causes and they are different mechanisms: a
        # market-wide public holiday (the hypothesis's mechanism, on more days) or a
        # name-specific SUSPENSION (a 停牌 for a restructuring announcement, whose resumption
        # bar routinely gaps straight to the limit for reasons that have nothing to do with
        # attention accrual). Separating them turns the confound into a measurement.
        sess = np.sort(dser["date"].unique())
        next_sess = dict(zip(sess[:-1], sess[1:]))
        fb = fb.copy()
        fb["market_next"] = fb["date"].map(next_sess)
        fb["market_wide_gap"] = fb["next_bar_date"] == fb["market_next"]

        gap_rows = []
        for lo, hi, lbl in ((1, 1, "1 (overnight)"), (2, 2, "2"), (3, 3, "3 (weekend)"),
                            (4, 7, "4-7"), (8, 10, "8-10")):
            g = fb[(fb["gap_days"] >= lo) & (fb["gap_days"] <= hi)]
            rec = {"gap_days": lbl}
            rec.update(rate_block(int(g["y_limit_up"].sum()), len(g)))
            if len(g):
                py = g.groupby("year")["y_limit_up"].mean()
                rec["year_equal_weight_pct"] = round(100.0 * float(py.mean()), 3)
                rec["years"] = int(len(py))
                for sub_lbl, sub in (("market_wide_holiday", g[g["market_wide_gap"]]),
                                     ("name_suspension", g[~g["market_wide_gap"]])):
                    rec[sub_lbl] = rate_block(int(sub["y_limit_up"].sum()), len(sub))
            gap_rows.append(rec)
        gap_note = (
            "market_wide_holiday = the name's next bar IS the board's next session, so the "
            "whole market was shut; name_suspension = the board traded in between and this "
            "name did not. ONLY the market-wide rows test the hypothesis.")
        fri = fb[fb["dow"] == 4]
        fri_rows = []
        for lo, hi, lbl in ((3, 3, "3 (clean weekend)"), (4, 10, "4-10 (weekend + holiday)")):
            g = fri[(fri["gap_days"] >= lo) & (fri["gap_days"] <= hi)]
            rec = {"friday_gap": lbl}
            rec.update(rate_block(int(g["y_limit_up"].sum()), len(g)))
            fri_rows.append(rec)

        out["boards"][board] = {
            "r_by_dow_of_d": r_rows,
            "first_to_second_by_dow_of_T": fb_rows,
            "first_to_second_by_calendar_gap": gap_rows,
            "calendar_gap_note": gap_note,
            "friday_first_boards_by_gap": fri_rows,
        }
    return out


# ── STAGE G — M5 zt_pool cross-validation (the mandatory honesty probe) ──────

def m5_zt_pool(panel: pd.DataFrame, ser: pd.DataFrame) -> dict:
    """How biased are our curated-universe regime dials against a market-wide vendor scrape?

    THE DATE SEMANTICS ARE DIAGNOSED FIRST, because they are wrong in a way that would
    silently corrupt every number below if taken at face value.
    """
    p = DATA / "china_zt_pool" / "pool.parquet"
    if not p.exists():
        return {"status": "zt_pool MISSING"}
    z = pd.read_parquet(p)
    z["date_raw"] = z["date"].astype(str)
    z["d"] = pd.to_datetime(z["date_raw"])

    # --- 1. date semantics ---
    payload_cols = ["ticker", "name", "consec_boards", "seal_fund_yi", "failed_seals",
                    "turnover_pct", "sector"]
    sig = (z.sort_values(["date_raw", "ticker"])
             .groupby("date_raw")[payload_cols]
             .apply(lambda g: pd.util.hash_pandas_object(
                 g.reset_index(drop=True), index=False).sum(), include_groups=False))
    dates = sorted(z["date_raw"].unique())
    seen: dict[int, str] = {}
    diag = []
    for dt in dates:
        h = int(sig.loc[dt])
        dup_of = seen.get(h)
        if dup_of is None:
            seen[h] = dt
        ts = pd.Timestamp(dt)
        diag.append({
            "date": dt,
            "dow": DOW_NAMES[ts.dayofweek],
            "rows": int((z["date_raw"] == dt).sum()),
            "asof": sorted(set(z.loc[z["date_raw"] == dt, "asof"].astype(str)))[0],
            "is_weekend": bool(ts.dayofweek >= 5),
            "payload_duplicate_of": dup_of,
        })

    weekend_rows = [r for r in diag if r["is_weekend"]]
    weekend_dupes = [r for r in weekend_rows if r["payload_duplicate_of"]]
    semantics = {
        "verdict": (
            "`date` IS A SCRAPE-RUN STAMP, NOT A TRADE DATE, from 2026-07-02 onward. "
            f"{len(weekend_rows)} of {len(dates)} dates fall on a Saturday or Sunday, and "
            f"{len(weekend_dupes)} of those {len(weekend_rows)} carry a payload BYTE-IDENTICAL "
            "to the preceding Friday's (compared on every column except date/asof). The "
            "vendor endpoint returns the last trading day's pool; the writer stamps it with "
            "the run date. The 2026-06-15 -> 2026-06-26 block (asof 2026-07-06) is a backfill "
            "and IS trade-date stamped — it contains no weekend rows at all — and 2026-06-30 / "
            "2026-07-01 carry asof = date + 1, i.e. a trade date scraped the next morning. So "
            "the store changed semantics mid-life."),
        "consequence_if_ignored": (
            "Every Friday would be counted three times and every Monday's pool would be read "
            "as a Sunday's. Nothing downstream in this file uses a weekend or duplicate row."),
        "ownership": "the L0 lane owns the heal (a trade-date column, or de-duplication at "
                     "write time). This lane only refuses to be fooled by it.",
        "n_dates_raw": len(dates),
        "n_weekend_dates": len(weekend_rows),
        "n_payload_duplicate_dates": sum(1 for r in diag if r["payload_duplicate_of"]),
        "per_date": diag,
    }

    # --- 2. clean overlap dates ---
    ours_by_date = ser.groupby("date", as_index=False).agg(
        ours_limit_up=("i2_limit_up_total", "sum"),
        ours_first_board=("i1_first_board_count", "sum"),
        ours_zhaban=("i4_zhaban_count", "sum"),
        ours_max_ladder=("i3_max_active_ladder", "max"),
    )
    our_dates = set(ours_by_date["date"].dt.strftime("%Y-%m-%d"))
    clean = [r["date"] for r in diag
             if not r["is_weekend"] and not r["payload_duplicate_of"] and r["date"] in our_dates]
    dropped = [{"date": r["date"], "reason": ("weekend" if r["is_weekend"] else
                                              ("payload_duplicate" if r["payload_duplicate_of"]
                                               else "no session in our tape"))}
               for r in diag if r["date"] not in clean]

    # --- 3. which trade date does a vendor row describe? measured, not assumed ---
    raw_names = set(panel["ticker"].cat.categories.astype(str))
    live = panel[panel["live"]]
    lu_by_date = {d.strftime("%Y-%m-%d"): set(g["ticker"].astype(str))
                  for d, g in live[live["limit_up"]].groupby("date", observed=True)}
    sess = sorted(our_dates)
    prev_sess = {sess[i]: sess[i - 1] for i in range(1, len(sess))}
    align = {"same_day_hits": 0, "prev_day_hits": 0, "vendor_rows_in_universe": 0}
    for dt in clean:
        vend = set(z.loc[z["date_raw"] == dt, "ticker"].astype(str)) & raw_names
        align["vendor_rows_in_universe"] += len(vend)
        align["same_day_hits"] += len(vend & lu_by_date.get(dt, set()))
        pd_ = prev_sess.get(dt)
        if pd_:
            align["prev_day_hits"] += len(vend & lu_by_date.get(pd_, set()))
    align["same_day_recall_pct"] = round(
        100.0 * align["same_day_hits"] / max(1, align["vendor_rows_in_universe"]), 2)
    align["prev_day_recall_pct"] = round(
        100.0 * align["prev_day_hits"] / max(1, align["vendor_rows_in_universe"]), 2)
    align["verdict"] = ("date is the TRADE date on the clean weekday rows"
                        if align["same_day_hits"] >= align["prev_day_hits"]
                        else "date is the trade date + 1 on the clean weekday rows")

    # --- 3b. DETECTION AGREEMENT INSIDE THE SHARED UNIVERSE ---
    # The undercount factor answers "how much of the market do we not hold". This answers a
    # different and equally load-bearing question: OF THE NAMES WE DO HOLD, does our detector
    # agree with the vendor about who limit-upped? v0 could only check 连板 agreement WITHIN
    # rows both sources already agreed on, so this direction was never measured.
    lu_strict_by_date = {d.strftime("%Y-%m-%d"): set(g["ticker"].astype(str))
                         for d, g in live[live["limit_up_strict"]].groupby("date",
                                                                           observed=True)}
    agree = {"both": 0, "ours_only": 0, "vendor_only": 0,
             "ours_only_that_are_tolerant_only": 0, "ours_total": 0, "vendor_total": 0,
             "both_strict": 0, "ours_total_strict": 0}
    for dt in clean:
        vend = set(z.loc[z["date_raw"] == dt, "ticker"].astype(str)) & raw_names
        ours = lu_by_date.get(dt, set())
        ours_s = lu_strict_by_date.get(dt, set())
        only_ours = ours - vend
        agree["both"] += len(ours & vend)
        agree["ours_only"] += len(only_ours)
        agree["vendor_only"] += len(vend - ours)
        agree["ours_only_that_are_tolerant_only"] += len(only_ours - ours_s)
        agree["ours_total"] += len(ours)
        agree["vendor_total"] += len(vend)
        agree["both_strict"] += len(ours_s & vend)
        agree["ours_total_strict"] += len(ours_s)
    agree["recall_of_vendor_pct"] = round(
        100.0 * agree["both"] / max(1, agree["vendor_total"]), 2)
    agree["precision_vs_vendor_pct"] = round(
        100.0 * agree["both"] / max(1, agree["ours_total"]), 2)
    agree["precision_vs_vendor_strict_pct"] = round(
        100.0 * agree["both_strict"] / max(1, agree["ours_total_strict"]), 2)
    agree["recall_of_vendor_strict_pct"] = round(
        100.0 * agree["both_strict"] / max(1, agree["vendor_total"]), 2)
    agree["share_of_ours_only_explained_by_the_cushion_pct"] = round(
        100.0 * agree["ours_only_that_are_tolerant_only"] / max(1, agree["ours_only"]), 2)
    agree["reading"] = (
        "Recall is near-total in both definitions: essentially every name the vendor calls a "
        "limit-up, we also call one. PRECISION is where the two disagree — we flag names the "
        "vendor's pool does not list. The cushion share says how much of that gap is the 0.2% "
        "tolerance rather than a genuine difference of opinion about the event. Whatever the "
        "cause, the consequence for THIS lane is one-directional and must be carried into "
        "every level below: our i2 count is inflated relative to a vendor-consistent count, "
        "so the TRUE undercount against the market is LARGER than the raw ratio.")

    # --- 4. the undercount factor ---
    per = []
    for dt in clean:
        zz = z[z["date_raw"] == dt]
        ours = ours_by_date[ours_by_date["date"] == pd.Timestamp(dt)]
        if ours.empty:
            continue
        o = ours.iloc[0]
        vend_all = len(zz)
        vend_first = int((zz["consec_boards"] == 1).sum())
        per.append({
            "date": dt,
            "vendor_limit_up": vend_all,
            "ours_limit_up": int(o["ours_limit_up"]),
            "undercount_x": round(vend_all / max(1, int(o["ours_limit_up"])), 3),
            "vendor_first_board": vend_first,
            "ours_first_board": int(o["ours_first_board"]),
            "undercount_first_x": round(vend_first / max(1, int(o["ours_first_board"])), 3),
            "vendor_max_ladder": int(zz["consec_boards"].max()),
            "ours_max_ladder": int(o["ours_max_ladder"]),
            "vendor_failed_seals_sum": int(zz["failed_seals"].sum()),
            "ours_zhaban": int(o["ours_zhaban"]),
            "vendor_names_in_our_universe": len(
                set(zz["ticker"].astype(str)) & raw_names),
        })
    pdf = pd.DataFrame(per)
    stats: dict = {"clean_dates": len(pdf)}
    if not pdf.empty:
        for col, key in (("undercount_x", "undercount_all_boards"),
                         ("undercount_first_x", "undercount_first_board")):
            stats[key] = {
                "median": round(float(pdf[col].median()), 3),
                "mean": round(float(pdf[col].mean()), 3),
                "p25": round(float(pdf[col].quantile(0.25)), 3),
                "p75": round(float(pdf[col].quantile(0.75)), 3),
                "min": round(float(pdf[col].min()), 3),
                "max": round(float(pdf[col].max()), 3),
                "iqr_over_median": round(
                    float(pdf[col].quantile(0.75) - pdf[col].quantile(0.25))
                    / max(1e-9, float(pdf[col].median())), 3),
            }
        stats["pooled_undercount_x"] = round(
            float(pdf["vendor_limit_up"].sum()) / max(1, float(pdf["ours_limit_up"].sum())), 3)
        # The raw ratio flatters us: it divides the vendor's count by OUR count, and our count
        # includes rows the vendor does not call limit-ups at all (see
        # detection_agreement_shared_universe.precision_vs_vendor_pct). Re-stated against only
        # the events both sources agree on, the shortfall is larger.
        stats["pooled_undercount_x_vendor_consistent"] = round(
            float(pdf["vendor_limit_up"].sum()) / max(1, float(agree["both"])), 3)
        stats["names_in_our_universe_share_pct"] = round(
            100.0 * float(pdf["vendor_names_in_our_universe"].sum())
            / max(1, float(pdf["vendor_limit_up"].sum())), 2)
        stats["max_ladder_agreement"] = {
            "exact": int((pdf["vendor_max_ladder"] == pdf["ours_max_ladder"]).sum()),
            "ours_lower": int((pdf["ours_max_ladder"] < pdf["vendor_max_ladder"]).sum()),
            "ours_higher": int((pdf["ours_max_ladder"] > pdf["vendor_max_ladder"]).sum()),
            "mean_gap": round(float((pdf["vendor_max_ladder"]
                                     - pdf["ours_max_ladder"]).mean()), 3),
        }
        # 炸板 correlation — related object, NOT the same object. See the note.
        a = pdf["ours_zhaban"].astype(float)
        b = pdf["vendor_failed_seals_sum"].astype(float)
        stats["zhaban_vs_vendor_failed_seals"] = {
            "n_dates": len(pdf),
            "spearman": round(float(a.corr(b, method="spearman")), 3),
            "pearson": round(float(a.corr(b, method="pearson")), 3),
            "ours_mean": round(float(a.mean()), 2),
            "vendor_mean": round(float(b.mean()), 2),
            "NOT_THE_SAME_OBJECT": (
                "ours counts NAMES that reached the band and closed below it (a failed seal). "
                "The vendor's failed_seals is a per-name COUNT of intraday seal breaks among "
                "names that are IN the limit-up pool — i.e. mostly names that did hold by the "
                "close. Values run 0..47 per name. A high correlation would be evidence that "
                "both track the same underlying seal fragility; it is not a validation of "
                "either as a measurement of the other."),
        }
        # ladder distribution
        zc = z[z["date_raw"].isin(clean)]
        ours_lad = live[live["limit_up"] & live["date"].isin(
            [pd.Timestamp(d) for d in clean])]["lianban"].clip(upper=6)
        stats["ladder_distribution"] = {
            "vendor": {int(k): int(v) for k, v in
                       zc["consec_boards"].clip(upper=6).value_counts().sort_index().items()},
            "ours": {int(k): int(v) for k, v in
                     ours_lad.value_counts().sort_index().items()},
            "vendor_share_pct": {int(k): round(100.0 * v / len(zc), 2) for k, v in
                                 zc["consec_boards"].clip(upper=6)
                                 .value_counts().sort_index().items()},
            "ours_share_pct": {int(k): round(100.0 * v / max(1, len(ours_lad)), 2) for k, v in
                               ours_lad.value_counts().sort_index().items()},
        }
    return {
        "date_semantics": semantics,
        "clean_overlap_dates": clean,
        "dropped_dates": dropped,
        "trade_date_alignment": align,
        "detection_agreement_shared_universe": agree,
        "undercount": stats,
        "per_date": per,
        "reading": (
            "THE NUMBER THE PROGRAM NEEDS. Our regime dials are computed on a curated "
            "large/mid-cap slice; the vendor pool is market-wide. The undercount factor is "
            "how many real limit-ups exist for each one we see. It is measured on "
            f"{len(pdf)} clean weekday dates and its dispersion is printed beside it, because "
            "a STABLE undercount would mean our dials are the market's dials on a different "
            "scale (safe to quantile) while an UNSTABLE one would mean the bias itself moves "
            "with the regime (not safe). 47 dates is far too short a history to replicate any "
            "regime measurement on the vendor universe — that is in the ORE LEDGER, not here."),
    }


# ── STAGE H — M6 mania sanity ────────────────────────────────────────────────

def m6_mania_sanity(ser: pd.DataFrame) -> dict:
    out = {
        "why": "these dials must light up in the two known manias. If they do not, they are "
               "broken, and no conditional above is worth reading.",
        "windows": {},
    }
    cols = ["i1_first_board_count", "i2_limit_up_total", "i2_limit_down_total",
            "i3_max_active_ladder", "i4_zhaban_count", "i4_zhaban_rate",
            "i5_realized_continuation", "i6_near_limit_count"]
    main = ser[ser["board"] == "main"].copy()
    main["ym"] = main["date"].dt.strftime("%Y-%m")

    for label, lo, hi in (("mania_2015", "2015-05-01", "2015-09-30"),
                          ("mania_2024", "2024-09-01", "2024-10-31"),
                          ("baseline_2023", "2023-01-01", "2023-12-31")):
        w = main[(main["date"] >= lo) & (main["date"] <= hi)]
        by_month = []
        for ym, g in w.groupby("ym", sort=True):
            rec = {"month": ym, "sessions": len(g)}
            for c in cols:
                v = float(g[c].mean(skipna=True))
                rec[c] = round(v, 4) if np.isfinite(v) else None
            by_month.append(rec)
        rec_all = {"window": [lo, hi], "sessions": len(w), "by_month": by_month}
        for c in cols:
            v = float(w[c].mean(skipna=True))
            rec_all[f"{c}__mean"] = round(v, 4) if np.isfinite(v) else None
        out["windows"][label] = rec_all

    full = main
    out["full_window_mean_main"] = {
        c: round(float(full[c].mean(skipna=True)), 4) for c in cols}
    peaks = main.nlargest(10, "i2_limit_up_total")[
        ["date", "i1_first_board_count", "i2_limit_up_total", "i3_max_active_ladder",
         "i4_zhaban_rate", "i5_realized_continuation"]]
    out["top10_sessions_by_limit_up_total_main"] = [
        {"date": r["date"].strftime("%Y-%m-%d"),
         "i1": int(r["i1_first_board_count"]),
         "i2_lu": int(r["i2_limit_up_total"]),
         "i3_max_ladder": int(r["i3_max_active_ladder"]),
         "i4_rate": None if not np.isfinite(r["i4_zhaban_rate"]) else round(
             float(r["i4_zhaban_rate"]), 4),
         "i5": None if not np.isfinite(r["i5_realized_continuation"]) else round(
             float(r["i5_realized_continuation"]), 4)}
        for _i, r in peaks.iterrows()]
    return out


# ── main ─────────────────────────────────────────────────────────────────────

ORE_LEDGER = {
    "principle": (
        "THE ORE LAW binds this lane. A null here closes the SPECIFIC construction tested, "
        "never the search space, and every construction NOT tested is named below so a reader "
        "cannot mistake this file's coverage for the topic's coverage."),
    "untested_variants": [
        {"variant": "题材 / concept-level heat (板块 / 概念 limit-up counts)",
         "why_not": "needs a THS/同花顺 concept-membership mapping we do not hold. The sector "
                    "map we do hold (data/china_search/members.parquet) is a CURRENT GICS-ish "
                    "classification, not the 概念 taxonomy the 打板 crowd actually trades.",
         "status": "Wave 2"},
        {"variant": "volume-weighted ecology (turnover-weighted first-board count, "
                    "market-wide turnover as a heat dial)",
         "why_not": "not attempted here; the instrument set was frozen at six counts before "
                    "the run. Volume is present in the store, so this is buildable and is the "
                    "cheapest next variant.",
         "status": "buildable now, deliberately out of this lane's scope"},
        {"variant": "index-return interaction (regime dial conditional on CSI300/CSI1000 "
                    "same-day and trailing return)",
         "why_not": "an index series was not joined. A limit-up count on a +2% index day and "
                    "on a −2% index day are plausibly different objects and this lane cannot "
                    "tell them apart.",
         "status": "Wave 2"},
        {"variant": "northbound-flow interaction (陆股通 net flow as a regime co-dial)",
         "why_not": "not joined; northbound was also suspended as a daily disclosure in "
                    "2024, so any such instrument has a hard coverage break.",
         "status": "Wave 2, with a coverage caveat"},
        {"variant": "regime replication on the zt_pool (market-wide) universe",
         "why_not": "47 scrape dates, of which fewer still are clean. A regime measurement "
                    "needs regimes; this history cannot contain two. MEASURED-TOO-SHORT, not "
                    "a null.",
         "status": "blocked on history, not on method"},
        {"variant": "intraday heat propagation (does the first hour's seal count predict the "
                    "close's?)",
         "why_not": "daily bars only. Named in v0's Stage-4 collector proposals.",
         "status": "blocked on a collector"},
        {"variant": "炸板率 leading-vs-coincident decomposition",
         "why_not": "M3 measures 炸板率 at d against outcomes at d+1, which cannot separate "
                    "'炸板率 predicts tomorrow' from '炸板率 and tomorrow are both driven by a "
                    "slow-moving sentiment state'. A lead-lag / innovation decomposition "
                    "(residualising against the trailing state) was not run.",
         "status": "buildable now, out of scope"},
        {"variant": "regime x per-name feature crosses (does v0's f3 run-up lift depend on "
                    "the regime bucket?)",
         "why_not": "requires v0's per-name feature panel in the same process. That is the "
                    "explicit Wave-2 join with the L1/L3 lanes.",
         "status": "Wave 2, with L1/L3"},
        {"variant": "seal-quality dials (封单量 / 首封时间 aggregated to a market level)",
         "why_not": "we hold seal_fund_yi for 47 dates only and no first-touch time at all. "
                    "v0's Stage-4 #1 collector is the unblocker.",
         "status": "blocked on a collector"},
        {"variant": "limit-DOWN ecology as a regime dial (跌停 breadth, down-ladder depth)",
         "why_not": "i2_limit_down_total is BUILT and carried in the series, and net breadth "
                    "is conditioned in M1 — but the down-side ladder, its own continuation "
                    "rate and its own cascade were not measured. The survivorship hole (the "
                    "store holds the CURRENT listed universe) bites hardest exactly here.",
         "status": "partially built; the down-ladder is untested"},
        {"variant": "ST-cohort and small-cap ecology",
         "why_not": "the ST cohort is excluded wholesale (v0's rule — no membership history) "
                    "and the raw store carries 1 of 100 current ST names anyway. The 打板 game "
                    "lives disproportionately in exactly this cohort. M5 measures the size of "
                    "the resulting blindness; it does not fix it.",
         "status": "blocked on the universe"},
    ],
}


def main() -> int:
    t0 = time.time()
    print("[stage A] building panel from data/china_stocks_raw ...", flush=True)
    panel, meta = build_panel()
    print(f"          {len(panel):,} rows, {panel['ticker'].nunique()} names, "
          f"{time.time() - t0:.1f}s", flush=True)

    print("[stage B] daily instrument series ...", flush=True)
    ser = build_series(panel)
    keep_cols = ["date", "board", "session_index", "year", "dow", "n_live_names",
                 "i1_first_board_count", "i1_first_board_count_ma5",
                 "i1_first_board_count_rel250", "i2_limit_up_total", "i2_limit_down_total",
                 "i2_net_breadth", "i2_limit_up_total_rel250", "i3_max_active_ladder",
                 "i4_zhaban_count", "i4_zhaban_count_strict", "i4_zhaban_rate",
                 "i4_zhaban_rate_strict", "i4_zhaban_rate_ma5", "i5_realized_continuation",
                 "i5_realized_continuation_ma5", "i5_pairs_n", "i5_k",
                 "i6_near_limit_count", "limit_up_strict_total"]
    ser_out = ser[keep_cols].copy()
    ser_out.to_parquet(OUT_PARQUET, index=False)
    print(f"          {len(ser_out):,} board-sessions -> {OUT_PARQUET.name}", flush=True)

    print("[stage C] M1 regime conditionals ...", flush=True)
    m1 = m1_regime_conditionals(panel, ser)
    print("[stage D] M2 ladder-leader cascade ...", flush=True)
    m2 = m2_leader_cascade(panel, ser)
    print("[stage E] M3 炸板率 dial ...", flush=True)
    m3 = m3_zhaban_dial(panel, ser)
    print("[stage F] M4 day-of-week ...", flush=True)
    m4 = m4_day_of_week(panel, ser)
    print("[stage G] M5 zt_pool cross-validation ...", flush=True)
    m5 = m5_zt_pool(panel, ser)
    print("[stage H] M6 mania sanity ...", flush=True)
    m6 = m6_mania_sanity(ser)

    payload = {
        "instrument": "research/cn_prophet_audit/board_ecology_regime_v1.py",
        "lane": "CN LIMIT-MOVE ALPHA — Wave 1, L2 BOARD ECOLOGY / REGIME INSTRUMENTS",
        "builds_on": "research/cn_prophet_audit/limit_move_footprint_v0.py (PR #4999)",
        "tier": "display/audit — MEASUREMENT ONLY. Nothing here ranks, sizes, gates or admits.",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_sec": None,
        "series_artifact": "research/cn_prophet_audit/board_ecology_series_v1.parquet",
        "definitions": {
            "limit_up_close_PRIMARY": (
                f"close >= round(prev_close*(1+w), 2) * (1 - {LIMIT_CLOSE_TOL}) — v0's "
                "adjudicated primary. The 0.2% is a feed-precision cushion, not a widening: "
                "v0 measured 43.4% of the marginal events moving strictly MORE than the full "
                "band, which is impossible for a real limit-up."),
            "limit_up_close_strict": "close >= round(prev_close*(1+w), 2) — carried in parallel",
            "zhaban_proxy_PRIMARY": (
                f"high >= round(prev_close*(1+w), 2) * (1 - {LIMIT_CLOSE_TOL}) AND not a "
                "PRIMARY limit-up close. The daily-bar shadow of a seal that formed and broke. "
                "THIS IS A PROXY: a name that traded through the band at 09:31 and one that "
                "touched it at 14:58 are the same row, and a name that never sealed but merely "
                "printed a high inside the cushion is counted the same as one that did."),
            "zhaban_proxy_strict": "high >= round(prev_close*(1+w), 2) AND not a STRICT "
                                   "limit-up close — carried in parallel; M3 is re-run on it",
            "near_limit_up": f"return >= {NEAR_LIMIT_FRAC} * w and not a PRIMARY limit close",
            "lianban_N": "consecutive PRIMARY limit-up closes ending on the bar; any non-limit "
                         "bar, including an excluded one, resets it to 0",
            "T -> T+1": f"the name's next usable bar, at most {MAX_PAIR_GAP_DAYS} calendar days "
                        f"later (A-share suspensions otherwise masquerade as tomorrow)",
            "w": "engine.china_microstructure.limit_width_for_date — star 20%, chinext 20% "
                 "on/after 2020-08-24 else 10%, main 10%, bse 30%",
        },
        "convention_note": CONVENTION_NOTE,
        "exclusions": {
            "st_cohort": "ALL dates for every ticker in data/china_st/st_snapshot.parquet "
                         "(v0's rule: that store carries one asof and no membership history)",
            "ipo_windows": f"STAR/ChiNext first {CHINEXT_STAR_IPO_WINDOW} sessions; pre-2014 "
                           f"listings first {PRE2014_IPO_WINDOW} session",
            "exdiv_suspect": "|open - prev_close| / prev_close > 1.5*w",
            "zero_volume": "bars with volume <= 0 (suspension placeholders)",
            "never_pooled": "no statistic is pooled across board types; ChiNext is never "
                            "pooled across CHINEXT_WIDE_DATE 2020-08-24",
        },
        "binding_caveats": {
            "universe_is_curated_AND_THE_DIALS_INHERIT_IT": (
                "data/china_stocks_raw holds ~1,842 curated large/mid-cap names against a "
                "listed A-share market of roughly 5,400. A REGIME DIAL BUILT FROM A CURATED "
                "SLICE UNDERCOUNTS THE MARKET, and unlike a per-name feature this bias lands "
                "directly in the instrument's level. M5 measures the factor. Read every count "
                "in the series as a curated-slice count, never as 涨停家数."),
            "survivorship": "the store holds the CURRENT listed universe; delisted names are "
                            "absent, which biases the limit-DOWN series most",
            "clustered_outcomes": "outcomes inside one session are massively correlated. Every "
                                  "Wilson interval printed here is UNDERSTATED; the effective "
                                  "sample size of a date-conditioned bucket is nearer its "
                                  "n_dates than its n.",
            "no_significance_claim": "the test used throughout is spread magnitude plus sign "
                                     "stability across an independent time block, never a "
                                     "p-value",
        },
        "meta": meta,
        "series_receipt": series_receipt(ser),
        "m1_regime_conditionals": m1,
        "m2_leader_cascade": m2,
        "m3_zhaban_dial": m3,
        "m4_day_of_week": m4,
        "m5_zt_pool_crossvalidation": m5,
        "m6_mania_sanity": m6,
        "ore_ledger": ORE_LEDGER,
    }
    payload["runtime_sec"] = round(time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(jsonable(payload), indent=2, ensure_ascii=False) + "\n")
    print(f"[done] {payload['runtime_sec']:.1f}s -> {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
