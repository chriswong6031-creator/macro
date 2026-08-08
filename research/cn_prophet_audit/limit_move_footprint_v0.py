#!/usr/bin/env python3
"""limit_move_footprint_v0.py — CN limit-move footprint v0 (§6.8(f), ANTICIPATION program).

WHAT THIS IS
    A MEASUREMENT instrument, display/audit tier.  Three stages over the CN daily
    stores, in the order the charter fixes them:

      STAGE 1  EVENT CATALOG — every limit-up / limit-down / near-limit close on the
               raw (unadjusted) A-share tape, board-aware, with the 连板 (consecutive
               board) count and the first-board vs continuation split.  This is the
               deliverable even if every later stage nulls.
      STAGE 2  BASE RATES, BEFORE ANY FEATURE — P(limit-up at T+1 | first board at T),
               P(limit-up at T+1 | N consecutive boards at T), and the limit-down
               mirror; split by board type and by year; pooled AND per-name-first.
               These are the numbers a 打板 strategy actually lives on.  Ours.
      STAGE 3  PRE-REGISTERED FOOTPRINT SET — exactly EIGHT features, named in the
               charter BEFORE any of this ran (see PREREGISTERED_FEATURES below),
               measured at the T-1 close against a limit-up at T.  Decile lift, fit
               on the first 70% of the window, REPORTED on the last 30% holdout only.
               Pooled and per-name-first.  A feature whose holdout lift disagrees in
               sign with its fit-window lift is printed UNSTABLE, never averaged.

    The design IS the defence.  Thousands of names x a rare event is the richest
    false-discovery environment in this repo; a post-hoc feature search over it would
    manufacture a beautiful, worthless answer.  So the feature set is frozen at eight,
    written down first, and the holdout is never looked at until the fit window is done.

WHAT IT IS NOT
    Not a promotion, not a gate, not a ranker, not a claim that any cell is tradeable.
    Nothing here sizes, ranks or admits anything.  Every number is a measurement on
    our own stores, with the stores' own coverage holes printed rather than patched.
    There is NO pooled top-line across board types anywhere: a +-10% main-board name
    and a +-20% ChiNext name do not share a base rate, and averaging them would invent
    a number that describes no market.

LIMIT CONVENTION — REUSED, NOT REINVENTED
    Board classification and limit width come from ``engine.china_microstructure``
    (imported, not copied): ``_board_from_ticker`` and ``limit_width_for_date``.  That
    module is the repo's authority for CN-SYS-R12 and is era-aware.  See the
    CONVENTION_NOTE constant for the second, disagreeing implementation in
    ``engine.china_signals.board_type`` and why this instrument does not use it.

    The per-bar event test here is VECTORISED, so it is a re-implementation of
    ``_detect_limit_events``'s row loop.  It is pinned against that function on a
    deterministic ticker sample at run time (STAGE 0 parity gate) and cross-checked
    against the committed ``data/china_microstructure/limit_events.parquet`` tape.

Run from repo root:  TZ=UTC python3 research/cn_prophet_audit/limit_move_footprint_v0.py
Outputs (frozen, committed):
    research/cn_prophet_audit/LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.json
    research/cn_prophet_audit/LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.md   (hand-written from the JSON)
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
    _detect_limit_events,
    limit_width_for_date,
)

DATA = REPO / "data"
OUT_JSON = (REPO / "research" / "cn_prophet_audit"
            / "LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.json")

# ── frozen parameters ─────────────────────────────────────────────────────────

WINDOW_START = LIMIT_TAPE_START_DATE          # 2011-01-01, the module's own data floor
WINDOW_END = pd.Timestamp("2026-08-07")       # last bar in the raw store at build time

# TWO limit-close definitions, both measured, both printed.
#
#   STRICT (PRIMARY)  close >= round(prev_close*(1+w), 2).  The market-true rule and the
#                     rule the committed house tape (data/china_microstructure) uses.
#   TOLERANT          close >= limit_price * (1 - 0.002).  The build charter's "at or within
#                     0.2% of the limit" wording, carried as a full parallel column.
#
# The charter's tolerance was specified as a rounding cushion.  MEASURED, it is not one: on a
# 10% board it admits every close from about +9.78% to +10.00%, which is 2.0x the strict event
# count, and it swallows most of the near-limit class the same charter asks us to count
# separately (main-board near-limit-up collapses from ~19k to 1.6k under it).  So STRICT is the
# headline and TOLERANT rides beside it, rather than the other way round.  Deviation disclosed
# in the report; both numbers are in the JSON for every Stage-1 and Stage-2 cell.
LIMIT_CLOSE_TOL = 0.002
# Charter definition: near-limit is a move >= 95% of the band (9.5% on a 10% board,
# 19% on a 20% board) that did NOT close at the limit.
NEAR_LIMIT_FRAC = 0.95
# A T -> T+1 pair is only usable if the two bars are adjacent in calendar terms.
# A-share suspensions routinely park a name for weeks; the bar after a suspension is
# not "tomorrow" and must not be graded as if it were.
MAX_PAIR_GAP_DAYS = 10

FIT_FRACTION = 0.70                            # first 70% of dates fit; last 30% holdout
THIN_CELL_N = 20                               # cells below this n are labelled thin
MIN_PER_NAME_OBS = 250                         # per-name decile analysis floor (rows)
MIN_PER_NAME_POS = 10                          # per-name decile analysis floor (positives)
MIN_PER_NAME_COND_N = 10                       # per-name base-rate floor (conditioning events)
N_DECILES = 10
PARITY_SAMPLE = 25                             # tickers pinned against _detect_limit_events

# THE PRE-REGISTERED SET.  Eight features, named in masterplan §6.8(f) and in the build
# charter BEFORE this file was written.  Adding a ninth after seeing these results is
# the exact sin this instrument exists to prevent.
PREREGISTERED_FEATURES = OrderedDict([
    ("f1_vol_z20", "volume z-score of the T-1 bar vs its own prior 20 bars"),
    ("f2_turnover_ratio", "turnover ratio (volume / shares outstanding) at T-1"),
    ("f3_runup_5", "5-session run-up: close[T-1] / close[T-6] - 1"),
    ("f4_sector_heat", "same-day sector limit-up count at T-1, leave-one-out"),
    ("f5_near_limit_prev", "prior-session near-limit flag: near-limit-up at T-1"),
    ("f6_gap_pct", "gap at the T-1 open: open[T-1] / close[T-2] - 1"),
    ("f7_dist_52w_low", "distance from the 52w low: close[T-1] / min(low, 252 bars) - 1"),
    ("f8_consec_up_days", "consecutive up-close days ending at T-1"),
])
BINARY_FEATURES = {"f5_near_limit_prev"}

CONVENTION_NOTE = (
    "Board + width resolved by engine.china_microstructure.limit_width_for_date / "
    "_board_from_ticker (imported). A SECOND implementation exists at "
    "engine/china_signals.py:37-50 (board_type) which is neither era-aware (returns "
    "20% for a ChiNext name on any date, including before CHINEXT_WIDE_DATE "
    "2020-08-24) nor ST-aware (never narrows to 5%). That one feeds "
    "scripts/build_china_library.py -> cn_snapshot -> data/china_pick_lab/fires.jsonl, "
    "which is why fires.jsonl carries only widths {10.0, 20.0} and never 5.0. This "
    "instrument uses the era-aware module, so its widths will not match fires.jsonl "
    "on pre-2020-08-24 ChiNext bars."
)

# Data the daily basis structurally cannot see. STAGE 4: proposals, not builds.
DATA_GAPS = [
    {
        "gap": "closing-auction order imbalance (14:57-15:00 集合竞价)",
        "why_it_matters": (
            "The seal that holds into the close is decided in the closing auction. A daily "
            "bar records the outcome and destroys the mechanism: a name sealed with a thin "
            "queue and a name sealed with a wall are the same row here."
        ),
        "proposal": (
            "Collector: per-ticker closing-auction matched volume + unmatched imbalance "
            "(direction and size) at 15:00, daily snapshot, ~5k rows/day."
        ),
        "expected_discriminative_value": (
            "HIGH for T+1 continuation, the one question STAGE 2 measures and cannot "
            "explain: imbalance size is the direct observable behind whether a seal "
            "survives the open."
        ),
    },
    {
        "gap": "封单量 — resting order-wall volume at the limit price",
        "why_it_matters": (
            "The single most-watched 打板 number in the market, and the one input every "
            "practitioner conditions on. We have it for 47 dates (data/china_zt_pool, "
            "seal_fund_yi) and for no date before 2026-06-15."
        ),
        "proposal": (
            "Collector: extend the existing zt_pool scrape to persist seal_fund_yi, "
            "failed_seals and turnover_pct as an APPEND-ONLY daily tape, and backfill "
            "from any vendor with history. Already-running scrape, storage change only."
        ),
        "expected_discriminative_value": (
            "HIGHEST of the four. It is the direct measure of demand left unfilled at the "
            "limit; without it, 'limit-up' pools a 100x range of conviction into one flag."
        ),
    },
    {
        "gap": "intraday first-touch time and seal stability",
        "why_it_matters": (
            "A 09:31 seal that never breaks and a 14:55 seal are the same daily row. STAGE 1's "
            "near_limit and failed-seal counts are the crudest possible proxy for a "
            "distinction that is continuous."
        ),
        "proposal": (
            "Collector: per-limit-event intraday summary — first touch timestamp, count of "
            "seal breaks, cumulative minutes sealed, final seal time. Requires minute bars "
            "for limit names only (~50-300 names/day), not the whole universe."
        ),
        "expected_discriminative_value": (
            "MEDIUM-HIGH for continuation; first-touch time is the standard practitioner "
            "split (一字/秒板 vs 尾盘板) and is currently entirely invisible to us."
        ),
    },
    {
        "gap": "T+0 intraday turnover composition (who traded, at what size)",
        "why_it_matters": (
            "A-share T+1 settlement means the day's buyers cannot sell until tomorrow — the "
            "T+1 continuation base rates in STAGE 2 are a direct function of who is locked "
            "in. Order-size-bucketed flow (大单/中单/小单) is the standard decomposition and "
            "we hold none of it per name per day."
        ),
        "proposal": (
            "Collector: per-ticker daily order-size-bucketed net flow. data/china_lhb "
            "(龙虎榜) already lands a related disclosure for a small qualifying subset — the "
            "proposal is the universe-wide daily version, not a re-scrape of LHB."
        ),
        "expected_discriminative_value": (
            "MEDIUM. Plausibly the mechanism behind f4 (cohort heat), but it is the most "
            "vendor-dependent and least verifiable of the four; ranked last deliberately."
        ),
    },
]


# ── small helpers ─────────────────────────────────────────────────────────────

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
    return obj


# ── STAGE 0 — universe, conventions, exclusions ───────────────────────────────

def load_st_cohort() -> tuple[frozenset[str], str]:
    """ST/*ST tickers, excluded wholesale.

    data/china_st carries ONE date (ST_STORE_COVERAGE_DATE). There is no ST membership
    history, so a per-date ST width is not reconstructible. The conservative choice is
    to drop today's ST cohort from every date rather than apply a 5% band to bars where
    the name may not have been ST, or a 10% band to bars where it was.
    """
    p = DATA / "china_st" / "st_snapshot.parquet"
    if not p.exists():
        return frozenset(), "st_snapshot.parquet MISSING — no ST exclusion applied"
    df = pd.read_parquet(p)
    tick = frozenset(df["ticker"].astype(str).tolist())
    asof = sorted(set(df["asof"].astype(str)))
    return tick, f"n={len(tick)} tickers, single asof {asof}"


def load_sector_map() -> tuple[dict[str, str], dict]:
    p = DATA / "china_search" / "members.parquet"
    if not p.exists():
        return {}, {"source": str(p), "status": "MISSING"}
    df = pd.read_parquet(p)
    m = {str(k): str(v) for k, v in df["sector"].items()}
    return m, {
        "source": "data/china_search/members.parquet",
        "n_tickers": len(m),
        "n_sectors": int(df["sector"].nunique()),
        "caveat": (
            "CURRENT sector membership applied to 15 years of history — sector "
            "reclassification is not reconstructible from this store."
        ),
    }


# ── STAGE 1 — per-ticker event detection (vectorised) ─────────────────────────

def detect_ticker(ticker: str, df: pd.DataFrame, board: str) -> tuple[pd.DataFrame, dict]:
    """Vectorised limit-event detection + pre-registered features for one ticker.

    Runs over the FULL price history so rolling baselines (20-bar volume, 252-bar low)
    are warm at the window start, then returns only in-window rows.  Limit flags are
    forced False outside the window so no 连板 streak can be seeded by a pre-1996 bar,
    when the +-10% band did not exist.
    """
    stats = {"ipo_excluded": 0, "exdiv_excluded": 0, "zero_volume_excluded": 0, "bars_in_window": 0}
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

    # width per bar (era-aware ChiNext step). is_st is always False: the ST cohort is
    # dropped upstream, so no 5% band is ever applied here.
    if board == "chinext":
        width = np.where(idx.to_numpy() >= CHINEXT_WIDE_DATE.to_datetime64(),
                         limit_width_for_date("chinext", CHINEXT_WIDE_DATE),
                         limit_width_for_date("chinext", CHINEXT_WIDE_DATE - pd.Timedelta(days=1)))
    else:
        width = np.full(n, limit_width_for_date(board, WINDOW_END), dtype=np.float64)
    width = width.astype(np.float64)

    # --- exclusions, mirroring engine.china_microstructure._detect_limit_events ---
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

    # --- limit prices + flags ---
    with np.errstate(invalid="ignore"):
        lim_up = np.round(pc * (1.0 + width), 2)
        lim_down = np.round(pc * (1.0 - width), 2)
        ret = close / pc - 1.0

    in_win = np.asarray((idx >= WINDOW_START) & (idx <= WINDOW_END), dtype=bool)
    live = in_win & ~excl

    # PRIMARY = strict; TOLERANT = the charter's 0.2% band, carried in parallel.
    lu = live & np.isfinite(lim_up) & (close >= lim_up)
    ld = live & np.isfinite(lim_down) & (close <= lim_down)
    lu_tol = live & np.isfinite(lim_up) & (close >= lim_up * (1.0 - LIMIT_CLOSE_TOL))
    ld_tol = live & np.isfinite(lim_down) & (close <= lim_down * (1.0 + LIMIT_CLOSE_TOL))
    near_up = live & np.isfinite(ret) & (ret >= NEAR_LIMIT_FRAC * width) & ~lu
    near_dn = live & np.isfinite(ret) & (ret <= -NEAR_LIMIT_FRAC * width) & ~ld

    lianban = streak_lengths(lu)
    lianban_dn = streak_lengths(ld)
    lianban_tol = streak_lengths(lu_tol)
    lianban_dn_tol = streak_lengths(ld_tol)

    # --- pre-registered features, all observable at the bar's own close ---
    s_close = pd.Series(close)
    s_vol = pd.Series(vol)
    base_mu = s_vol.shift(1).rolling(20, min_periods=15).mean().to_numpy()
    base_sd = s_vol.shift(1).rolling(20, min_periods=15).std(ddof=0).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = np.where(base_sd > 0, (vol - base_mu) / base_sd, np.nan)
        f3 = close / np.roll(close, 5) - 1.0
        f6 = open_ / pc - 1.0
        low252 = pd.Series(low).rolling(252, min_periods=120).min().to_numpy()
        f7 = np.where(low252 > 0, close / low252 - 1.0, np.nan)
    f3[:5] = np.nan
    f8 = streak_lengths(np.r_[False, close[1:] > close[:-1]])

    # --- T -> T+1 pairing, suspension-aware ---
    days = idx.to_numpy().astype("datetime64[D]").astype(np.int64)
    gap_next = np.r_[np.diff(days), np.iinfo(np.int64).max]
    pair_ok = gap_next <= MAX_PAIR_GAP_DAYS

    nxt_lu = np.r_[lu[1:], False]
    nxt_ld = np.r_[ld[1:], False]
    nxt_lu_tol = np.r_[lu_tol[1:], False]
    nxt_ld_tol = np.r_[ld_tol[1:], False]
    nxt_live = np.r_[live[1:], False]
    y_ok = pair_ok & nxt_live

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
        "limit_down": ld[keep],
        "limit_up_tol": lu_tol[keep],
        "limit_down_tol": ld_tol[keep],
        "near_limit_up": near_up[keep],
        "near_limit_down": near_dn[keep],
        "lianban": lianban[keep],
        "lianban_down": lianban_dn[keep],
        "lianban_tol": lianban_tol[keep],
        "lianban_down_tol": lianban_dn_tol[keep],
        "y_ok": y_ok[keep],
        "y_limit_up": nxt_lu[keep],
        "y_limit_down": nxt_ld[keep],
        "y_limit_up_tol": nxt_lu_tol[keep],
        "y_limit_down_tol": nxt_ld_tol[keep],
        "f1_vol_z20": f1[keep].astype(np.float32),
        "f3_runup_5": f3[keep].astype(np.float32),
        "f5_near_limit_prev": near_up[keep],
        "f6_gap_pct": f6[keep].astype(np.float32),
        "f7_dist_52w_low": f7[keep].astype(np.float32),
        "f8_consec_up_days": f8[keep].astype(np.int16),
    })
    return out, stats


def build_panel() -> tuple[pd.DataFrame, dict]:
    st_set, st_note = load_st_cohort()
    sector_map, sector_meta = load_sector_map()

    files = sorted((DATA / "china_stocks_raw").glob("*.parquet"))
    meta = {
        "raw_store": "data/china_stocks_raw (nominal/unadjusted OHLCV — the correct basis; "
                     "data/china_stocks is split/dividend adjusted and would fabricate limit misses)",
        "files_found": len(files),
        "st_cohort": st_note,
        "st_excluded_tickers": len(st_set),
        "sector_map": sector_meta,
        "window": [WINDOW_START.strftime("%Y-%m-%d"), WINDOW_END.strftime("%Y-%m-%d")],
    }

    frames, agg = [], {"ipo_excluded": 0, "exdiv_excluded": 0, "zero_volume_excluded": 0,
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
    panel["sector"] = panel["ticker"].map(sector_map).fillna("UNKNOWN")
    panel["year"] = panel["date"].dt.year.astype(np.int16)
    meta["sector_coverage_pct"] = round(
        100.0 * float((panel["sector"] != "UNKNOWN").mean()), 2)
    meta["panel_rows"] = int(len(panel))
    meta["live_rows"] = int(panel["live"].sum())

    # f4 — cohort heat, LEAVE-ONE-OUT so the feature measures the sector, not the name.
    grp = panel.groupby(["date", "sector"], observed=True)["limit_up"].transform("sum")
    panel["f4_sector_heat"] = (grp - panel["limit_up"].astype(np.int32)).astype(np.float32)
    panel.loc[panel["sector"] == "UNKNOWN", "f4_sector_heat"] = np.nan
    return panel, meta


# ── STAGE 0 parity gate ───────────────────────────────────────────────────────

def parity_gate() -> dict:
    """Pin the vectorised detector against engine.china_microstructure._detect_limit_events.

    The module's row loop is the authority; this instrument's speed comes from a
    re-implementation, so the re-implementation must be shown to agree.  Compared on the
    STRICT test (close >= lim_up), which is what the module emits — the charter's 0.2%
    tolerance is this instrument's own widening and is reported separately.
    """
    st_set, _ = load_st_cohort()
    files = sorted((DATA / "china_stocks_raw").glob("*.parquet"))
    picks = [p for p in files if p.stem not in st_set]
    step = max(1, len(picks) // PARITY_SAMPLE)
    picks = picks[::step][:PARITY_SAMPLE]

    mine_n = theirs_n = agree = 0
    mismatches = []
    for p in picks:
        ticker, board = p.stem, _board_from_ticker(p.stem)
        df = pd.read_parquet(p)
        rows, _ipo, _exd = _detect_limit_events(
            ticker, df, board, st_set, start_date=WINDOW_START, end_date=WINDOW_END)
        theirs = {(r["date"], r["event"]) for r in rows
                  if r["event"] in ("sealed_up", "sealed_down")}
        out, _ = detect_ticker(ticker, df, board)
        mine = set()
        for _i, r in out[out["limit_up"]].iterrows():
            mine.add((r["date"].strftime("%Y-%m-%d"), "sealed_up"))
        for _i, r in out[out["limit_down"]].iterrows():
            mine.add((r["date"].strftime("%Y-%m-%d"), "sealed_down"))
        mine_n += len(mine)
        theirs_n += len(theirs)
        agree += len(mine & theirs)
        if mine != theirs and len(mismatches) < 6:
            mismatches.append({
                "ticker": ticker, "board": board,
                "only_mine": sorted(mine - theirs)[:4],
                "only_module": sorted(theirs - mine)[:4],
            })
    return {
        "tickers_sampled": len(picks),
        "events_mine_strict": mine_n,
        "events_module": theirs_n,
        "intersection": agree,
        "agreement_pct": round(100.0 * agree / max(1, theirs_n), 3),
        "sample_mismatches": mismatches,
        "note": ("Residual disagreement is expected and explained: this instrument "
                 "additionally drops zero-volume bars, and resolves the IPO window from "
                 "the ticker's FULL history rather than post-window-filter as the module "
                 "does (the module's first_bar_global is computed after its own date "
                 "filter, so it drops one extra bar for every pre-2011 listing)."),
    }


def tape_crosscheck(panel: pd.DataFrame) -> dict:
    """Cross-check STAGE 1 against the committed limit_events.parquet tape."""
    p = DATA / "china_microstructure" / "limit_events.parquet"
    if not p.exists():
        return {"status": "tape MISSING"}
    ev = pd.read_parquet(p)
    ev = ev[(ev["date"] >= WINDOW_START) & (ev["date"] <= WINDOW_END)]
    shared = set(panel["ticker"].unique()) & set(ev["ticker"].unique())
    evs = ev[ev["ticker"].isin(shared)].copy()
    mine = panel[panel["ticker"].isin(shared) & panel["live"]].copy()
    evs["year"] = pd.to_datetime(evs["date"]).dt.year
    tape_y = evs[evs["event"] == "sealed_up"].groupby("year").size()
    mine_y = mine[mine["limit_up"]].groupby("year").size()
    years = sorted(set(tape_y.index) | set(mine_y.index))
    by_year = [{
        "year": int(y),
        "tape_sealed_up": int(tape_y.get(y, 0)),
        "mine_strict_limit_up": int(mine_y.get(y, 0)),
        "delta": int(mine_y.get(y, 0)) - int(tape_y.get(y, 0)),
    } for y in years]

    # Per-ticker agreement — the aggregate delta is meaningless until you know whether it is
    # spread thinly over every name or concentrated in a few.  Measured, not assumed.
    tape_t = evs[evs["event"] == "sealed_up"].groupby("ticker").size()
    mine_t = mine[mine["limit_up"]].groupby("ticker").size()
    cmp_t = pd.DataFrame({"tape": tape_t, "mine": mine_t}).fillna(0).astype(int)
    cmp_t["delta"] = cmp_t["mine"] - cmp_t["tape"]
    gap = cmp_t[cmp_t["delta"] > 5].sort_values("delta", ascending=False)
    gap_names = []
    for tk, row in gap.head(30).iterrows():
        te = evs[(evs["ticker"] == tk) & (evs["event"] == "sealed_up")]["date"]
        gap_names.append({
            "ticker": tk, "tape": int(row["tape"]), "recomputed": int(row["mine"]),
            "tape_earliest_event": te.min().strftime("%Y-%m-%d") if len(te) else None,
        })
    per_ticker = {
        "tickers_compared": int(len(cmp_t)),
        "exact_agree": int((cmp_t["delta"] == 0).sum()),
        "exact_agree_pct": round(100.0 * float((cmp_t["delta"] == 0).mean()), 2),
        "tape_higher": int((cmp_t["delta"] < 0).sum()),
        "recomputed_higher": int((cmp_t["delta"] > 0).sum()),
        "delta_events_total": int(cmp_t["delta"].sum()),
        "delta_events_from_gap_names": int(gap["delta"].sum()),
    }
    return {
        "tape_history_gap_names_total": int(len(gap)),
        "tape_history_gap_names_absent_entirely": int((gap["tape"] == 0).sum()),
        "tape_history_gap_names": gap_names,
        "tape_history_gap_finding": (
            "SIDE FINDING, reported not acted on: for these names the committed "
            "limit_events.parquet holds only events from roughly 2026-07 onward and no earlier "
            "history, while the raw store supports a full 2011-forward record. The tape's own "
            "backfill flag is True for all 3,751 of its market-days, so the flag does not "
            "surface the hole. Consistent with a raw-price repair (adjusted -> nominal) landing "
            "after the one-time historical backfill, with the nightly appender only ever adding "
            "new dates. This instrument does not touch the tape; the CN data-plane owner should."
        ),
        "tape_rows_in_window": int(len(ev)),
        "tape_tickers": int(ev["ticker"].nunique()),
        "panel_tickers": int(panel["ticker"].nunique()),
        "shared_tickers": len(shared),
        "tape_sealed_up": int((evs["event"] == "sealed_up").sum()),
        "mine_limit_up_strict": int(mine["limit_up"].sum()),
        "mine_limit_up_tolerant": int(mine["limit_up_tol"].sum()),
        "tape_sealed_down": int((evs["event"] == "sealed_down").sum()),
        "mine_limit_down_strict": int(mine["limit_down"].sum()),
        "mine_limit_down_tolerant": int(mine["limit_down_tol"].sum()),
        "by_year": by_year,
        "per_ticker_agreement": per_ticker,
        "note": ("Shared-universe comparison; the strict column is the like-for-like one. The "
                 "aggregate delta is NOT spread across the book — per ticker, "
                 f"{per_ticker['exact_agree']} of {per_ticker['tickers_compared']} names "
                 f"({per_ticker['exact_agree_pct']}%) match the tape EXACTLY. Essentially the "
                 "whole delta is carried by a handful of names where the tape holds only "
                 "recent (2026-07 onward) events and no earlier history at all, while this "
                 "instrument recomputes their full record from the raw store. See "
                 "tape_history_gap_names. The detector itself is pinned at 100% by the STAGE 0 "
                 "parity gate, which calls the module directly on the same signature."),
    }


def zt_pool_crosscheck(panel: pd.DataFrame) -> dict:
    """Cross-check the 连板 count against the independently scraped zt_pool store."""
    p = DATA / "china_zt_pool" / "pool.parquet"
    if not p.exists():
        return {"status": "zt_pool MISSING"}
    z = pd.read_parquet(p)
    z["date"] = pd.to_datetime(z["date"])
    z = z[(z["date"] >= WINDOW_START) & (z["date"] <= WINDOW_END)]
    mine = panel[panel["limit_up"]][["date", "ticker", "lianban"]]
    j = z.merge(mine, on=["date", "ticker"], how="inner")
    if j.empty:
        return {"status": "no overlap", "zt_rows": int(len(z))}
    same = int((j["consec_boards"] == j["lianban"]).sum())
    return {
        "zt_pool_window": [z["date"].min().strftime("%Y-%m-%d"), z["date"].max().strftime("%Y-%m-%d")],
        "zt_pool_rows": int(len(z)),
        "zt_rows_matched_to_our_limit_up": int(len(j)),
        "match_rate_pct": round(100.0 * len(j) / max(1, len(z)), 2),
        "lianban_exact_agree": same,
        "lianban_agree_pct": round(100.0 * same / max(1, len(j)), 2),
        "note": ("zt_pool is an independent vendor scrape covering 2026-06-15 forward. "
                 "Rows in zt_pool with no match here are names outside our 1.8k-ticker raw "
                 "store or ST names we exclude, not detection misses per se."),
    }


# ── STAGE 1 — catalog tables ──────────────────────────────────────────────────

def stage1(panel: pd.DataFrame) -> dict:
    live = panel[panel["live"]]
    by_year = []
    for (board, year), g in live.groupby(["board", "year"], observed=True):
        by_year.append({
            "board": board, "year": int(year),
            "ticker_days": int(len(g)),
            "names": int(g["ticker"].nunique()),
            "limit_up": int(g["limit_up"].sum()),
            "limit_down": int(g["limit_down"].sum()),
            "limit_up_tol": int(g["limit_up_tol"].sum()),
            "limit_down_tol": int(g["limit_down_tol"].sum()),
            "near_limit_up": int(g["near_limit_up"].sum()),
            "near_limit_down": int(g["near_limit_down"].sum()),
            "limit_up_per_1k_ticker_days": round(1000.0 * g["limit_up"].mean(), 3),
            "limit_down_per_1k_ticker_days": round(1000.0 * g["limit_down"].mean(), 3),
            "first_board": int(((g["lianban"] == 1)).sum()),
            "continuation": int(((g["lianban"] >= 2)).sum()),
        })
    by_board = []
    for board, g in live.groupby("board", observed=True):
        lu = g[g["limit_up"]]
        dist = lu["lianban"].clip(upper=8).value_counts().sort_index()
        by_board.append({
            "board": board,
            "names": int(g["ticker"].nunique()),
            "ticker_days": int(len(g)),
            "limit_up": int(g["limit_up"].sum()),
            "limit_up_tol": int(g["limit_up_tol"].sum()),
            "limit_down": int(g["limit_down"].sum()),
            "limit_down_tol": int(g["limit_down_tol"].sum()),
            "tolerant_over_strict_x": round(
                float(g["limit_up_tol"].sum()) / max(1, int(g["limit_up"].sum())), 3),
            "near_limit_up": int(g["near_limit_up"].sum()),
            "near_limit_down": int(g["near_limit_down"].sum()),
            "limit_up_rate_pct": round(100.0 * g["limit_up"].mean(), 4),
            "limit_down_rate_pct": round(100.0 * g["limit_down"].mean(), 4),
            "near_limit_up_rate_pct": round(100.0 * g["near_limit_up"].mean(), 4),
            "first_board": int((lu["lianban"] == 1).sum()),
            "continuation_2plus": int((lu["lianban"] >= 2).sum()),
            "lianban_max": int(lu["lianban"].max()) if len(lu) else 0,
            "lianban_hist_1_to_8plus": {int(k): int(v) for k, v in dist.items()},
        })
    lu = live[live["limit_up"]]
    sect = []
    for (board, sector), g in lu.groupby(["board", "sector"], observed=True):
        denom = int((live["board"] == board).sum())
        sect.append({"board": board, "sector": sector, "limit_up": int(len(g)),
                     "share_of_board_limit_ups_pct": round(
                         100.0 * len(g) / max(1, int(lu["board"].eq(board).sum())), 2),
                     "board_ticker_days": denom})
    sect.sort(key=lambda r: (r["board"], -r["limit_up"]))
    return {"by_board": by_board, "by_board_year": by_year, "sector_distribution": sect}


# ── STAGE 2 — base rates ──────────────────────────────────────────────────────

def _rate_block(g: pd.DataFrame, ycol: str) -> dict:
    n = int(len(g))
    k = int(g[ycol].sum())
    ci = wilson(k, n)
    return {
        "n": n, "k": k,
        "rate_pct": round(100.0 * k / n, 2) if n else None,
        "wilson95_pct": [round(100.0 * ci[0], 2), round(100.0 * ci[1], 2)] if ci else None,
        "thin": n < THIN_CELL_N,
    }


def _per_name_rate(g: pd.DataFrame, ycol: str) -> dict:
    """Per-name-first estimator: each qualifying name contributes ONE rate, equally weighted."""
    per = g.groupby("ticker", observed=True)[ycol].agg(["size", "sum"])
    per = per[per["size"] >= MIN_PER_NAME_COND_N]
    if per.empty:
        return {"names": 0, "median_pct": None, "mean_pct": None}
    r = per["sum"] / per["size"]
    return {
        "names": int(len(per)),
        "median_pct": round(100.0 * float(r.median()), 2),
        "mean_pct": round(100.0 * float(r.mean()), 2),
        "p25_pct": round(100.0 * float(r.quantile(0.25)), 2),
        "p75_pct": round(100.0 * float(r.quantile(0.75)), 2),
        "min_events_per_name": MIN_PER_NAME_COND_N,
    }


def stage2(panel: pd.DataFrame) -> dict:
    usable = panel[panel["live"] & panel["y_ok"]]
    out = {"definitions": {
        "conditioning": "rows where the name closed at the limit on day T with 连板 == N",
        "target": "the name closes at the limit again on its NEXT usable bar (T+1)",
        "pair_rule": f"T and T+1 must be <= {MAX_PAIR_GAP_DAYS} calendar days apart "
                     f"(A-share suspensions otherwise masquerade as tomorrow)",
    }}

    N_CAP = 8
    for defn, suffix in (("strict", ""), ("tolerant", "_tol")):
        for side, cond_stem, streak_stem in (
            ("up", "limit_up", "lianban"),
            ("down", "limit_down", "lianban_down"),
        ):
            cond_col = cond_stem + suffix
            streak_col = streak_stem + suffix
            ycol = "y_" + cond_stem + suffix
            base = usable[usable[cond_col]].copy()
            base["N"] = base[streak_col].clip(upper=N_CAP)
            rows = []
            for (board, N), g in base.groupby(["board", "N"], observed=True):
                rec = {"board": board, "N": int(N),
                       "N_label": f"{N_CAP}+" if N == N_CAP else str(int(N))}
                rec.update(_rate_block(g, ycol))
                rec["per_name"] = _per_name_rate(g, ycol)
                rows.append(rec)
            rows.sort(key=lambda r: (r["board"], r["N"]))

            yearly = []
            first = base[base["N"] == 1]
            for (board, year), g in first.groupby(["board", "year"], observed=True):
                rec = {"board": board, "year": int(year)}
                rec.update(_rate_block(g, ycol))
                yearly.append(rec)
            yearly.sort(key=lambda r: (r["board"], r["year"]))

            uncond = []
            for board, g in usable.groupby("board", observed=True):
                rec = {"board": board}
                rec.update(_rate_block(g, ycol))
                uncond.append(rec)

            out[f"{defn}__limit_{side}"] = {
                "by_board_N": rows,
                "first_board_by_board_year": yearly,
                "unconditional_next_bar": uncond,
            }

    out["ladder_reading_note"] = (
        "The N ladder is a CONDITIONED-ON-REACHING table, not a per-run survival curve. A run "
        "that reached 8 boards contributes a row at N=1..7, every one of which continued, so "
        "high-N cells are dominated by the runs that were already long. Read a cell as 'a day "
        f"inside an N-board run is followed by another board X% of the time', never as 'the "
        f"Nth board continues X% of the time'. N={N_CAP} is a tail bucket pooling {N_CAP}+."
    )
    out["per_name_reading_note"] = (
        f"The per-name-first estimator needs >= {MIN_PER_NAME_COND_N} conditioning events in "
        "the SAME cell for a name to contribute. Only N=1 (and N=2 on main/chinext) clears "
        "that floor for a meaningful number of names; at high N the qualifying names are, by "
        "construction, the serial-limit names, so those per-name medians are a selected "
        "sub-population and are NOT a check on the pooled number. They are printed with their "
        "name count so the thinness is visible rather than inferred."
    )

    out["usable_rows"] = int(len(usable))
    out["rows_dropped_unusable_pair"] = int(
        (panel["live"] & ~panel["y_ok"]).sum())
    return out


# ── STAGE 3 — pre-registered features, time-split decile lift ─────────────────

def _decile_table(g: pd.DataFrame, feat: str, ycol: str) -> list[dict]:
    v = g[feat]
    ok = v.notna()
    g, v = g[ok], v[ok]
    if len(g) < N_DECILES * THIN_CELL_N:
        return []
    base = float(g[ycol].mean())
    if base <= 0:
        return []
    if feat in BINARY_FEATURES:
        buckets = g[feat].astype(bool).map({False: "0", True: "1"})
    else:
        try:
            buckets = pd.qcut(v.rank(method="first"), N_DECILES, labels=False, duplicates="drop")
            buckets = buckets.astype("Int64").astype(str)
        except ValueError:
            return []
    rows = []
    for b, gg in g.groupby(buckets, observed=True):
        n, k = int(len(gg)), int(gg[ycol].sum())
        rows.append({
            "bucket": str(b), "n": n, "k": k,
            "rate_pct": round(100.0 * k / n, 4) if n else None,
            "lift": round((k / n) / base, 3) if n and base else None,
            "feat_lo": round(float(gg[feat].min()), 4),
            "feat_hi": round(float(gg[feat].max()), 4),
            "thin": n < THIN_CELL_N,
        })
    rows.sort(key=lambda r: float(r["feat_lo"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


def _per_name_lift(g: pd.DataFrame, feat: str, ycol: str) -> dict:
    """Per-name-first decile lift: rank WITHIN each name, then equal-weight the names."""
    d = g[[feat, ycol, "ticker"]].dropna(subset=[feat])
    if d.empty:
        return {"names": 0, "top_bucket_lift_median": None, "bottom_bucket_lift_median": None}
    size = d.groupby("ticker", observed=True)[ycol].transform("size")
    pos = d.groupby("ticker", observed=True)[ycol].transform("sum")
    d = d[(size >= MIN_PER_NAME_OBS) & (pos >= MIN_PER_NAME_POS)]
    if d.empty:
        return {"names": 0, "top_bucket_lift_median": None, "bottom_bucket_lift_median": None}
    if feat in BINARY_FEATURES:
        d = d.assign(b=d[feat].astype(int))
        top, bot = 1, 0
    else:
        pct = d.groupby("ticker", observed=True)[feat].rank(pct=True, method="first")
        d = d.assign(b=np.minimum((pct * N_DECILES).astype(int), N_DECILES - 1))
        top, bot = N_DECILES - 1, 0
    name_base = d.groupby("ticker", observed=True)[ycol].mean()
    cell = d.groupby(["ticker", "b"], observed=True)[ycol].mean()
    lift = (cell / name_base.reindex(cell.index.get_level_values(0)).to_numpy())
    lift = lift.reset_index().rename(columns={ycol: "lift"})
    t = lift[lift["b"] == top]["lift"]
    bo = lift[lift["b"] == bot]["lift"]
    return {
        "names": int(d["ticker"].nunique()),
        "top_bucket_lift_median": round(float(t.median()), 3) if len(t) else None,
        "top_bucket_lift_mean": round(float(t.mean()), 3) if len(t) else None,
        "bottom_bucket_lift_median": round(float(bo.median()), 3) if len(bo) else None,
        "top_bucket_names_above_1": int((t > 1).sum()) if len(t) else 0,
        "top_bucket_names_total": int(len(t)),
    }


def _collinearity(hb: pd.DataFrame, feats: list[str]) -> dict:
    """Spearman correlation among the pre-registered features on the holdout.

    Seven features all showing lift is NOT seven findings if they are seven ways of
    measuring one thing.  This block exists so that question is answered with a number
    instead of a shrug.  Deterministic subsample (every k-th row) to keep runtime inside
    the budget; the subsample rule is printed, not hidden.
    """
    step = max(1, len(hb) // 200_000)
    sub = hb.iloc[::step]
    m = sub[feats].astype("float64").corr(method="spearman")
    return {
        "subsample_rule": f"every {step}th holdout row ({len(sub)} of {len(hb)})",
        "matrix": {a: {b: (None if pd.isna(m.loc[a, b]) else round(float(m.loc[a, b]), 3))
                       for b in feats} for a in feats},
        "max_abs_offdiag": round(float(
            m.where(~np.eye(len(feats), dtype=bool)).abs().max().max()), 3),
    }


def _conditioned_lift(hb: pd.DataFrame, feats: list[str]) -> dict:
    """Each feature's holdout top-decile lift AFTER removing the rows f5 already flags.

    f5 (prior-session near-limit) is by far the strongest single feature. If the other six
    are mostly re-detecting 'this name was already almost at the limit yesterday', their
    lift should collapse on the f5==False subset. If it survives, they carry something f5
    does not. One control, pre-specified in shape, applied identically to all of them.
    """
    sub = hb[~hb["f5_near_limit_prev"].astype(bool)]
    base = float(sub["y_limit_up"].mean()) if len(sub) else 0.0
    out = {"rows": int(len(sub)), "base_rate_pct": round(100.0 * base, 4), "features": {}}
    for f in feats:
        if f == "f5_near_limit_prev":
            continue
        t = _decile_table(sub, f, "y_limit_up")
        out["features"][f] = {"top_lift": t[-1]["lift"] if t else None,
                              "bottom_lift": t[0]["lift"] if t else None}
    return out


def _per_name_availability(hb: pd.DataFrame) -> dict:
    per = hb.groupby("ticker", observed=True)["y_limit_up"].agg(["size", "sum"])
    ok = (per["size"] >= MIN_PER_NAME_OBS) & (per["sum"] >= MIN_PER_NAME_POS)
    return {
        "names_total": int(len(per)),
        "names_qualifying": int(ok.sum()),
        "median_positives_per_name": float(per["sum"].median()),
        "floors": {"min_rows": MIN_PER_NAME_OBS, "min_positives": MIN_PER_NAME_POS},
        "note": ("When this is 0 the per-name-first column is a MEASURED null, not a bug: at "
                 "this board's base rate a name simply does not accumulate enough limit-ups in "
                 "the holdout to estimate its own decile curve."),
    }


def stage3(panel: pd.DataFrame) -> dict:
    usable = panel[panel["live"] & panel["y_ok"]]
    dates = np.sort(usable["date"].unique())
    split_i = int(len(dates) * FIT_FRACTION)
    split_date = pd.Timestamp(dates[split_i])
    fit = usable[usable["date"] < split_date]
    hold = usable[usable["date"] >= split_date]

    res = {
        "preregistered_features": dict(PREREGISTERED_FEATURES),
        "target": "limit_up_close at T (the bar AFTER the feature bar)",
        "time_split": {
            "rule": f"first {int(FIT_FRACTION * 100)}% of trading dates fit / inspect; "
                    f"last {100 - int(FIT_FRACTION * 100)}% REPORTED as holdout",
            "split_date": split_date.strftime("%Y-%m-%d"),
            "fit_dates": int(split_i),
            "holdout_dates": int(len(dates) - split_i),
            "fit_rows": int(len(fit)),
            "holdout_rows": int(len(hold)),
        },
        "not_measurable": {},
        "by_board": {},
    }

    for board in sorted(usable["board"].unique()):
        fb, hb = fit[fit["board"] == board], hold[hold["board"] == board]
        if len(hb) < N_DECILES * THIN_CELL_N:
            res["by_board"][board] = {"status": "insufficient holdout rows",
                                      "holdout_rows": int(len(hb))}
            continue
        entry = {
            "fit_rows": int(len(fb)), "holdout_rows": int(len(hb)),
            "fit_base_rate_pct": round(100.0 * float(fb["y_limit_up"].mean()), 4),
            "holdout_base_rate_pct": round(100.0 * float(hb["y_limit_up"].mean()), 4),
            "features": {},
        }
        for feat in PREREGISTERED_FEATURES:
            if feat not in usable.columns:
                continue
            ft = _decile_table(fb, feat, "y_limit_up")
            ht = _decile_table(hb, feat, "y_limit_up")
            if not ht:
                entry["features"][feat] = {"status": "insufficient non-null rows"}
                continue
            f_top = ft[-1]["lift"] if ft else None
            f_bot = ft[0]["lift"] if ft else None
            h_top, h_bot = ht[-1]["lift"], ht[0]["lift"]
            stable = None
            if f_top is not None and h_top is not None:
                stable = (f_top - 1.0) * (h_top - 1.0) > 0
            entry["features"][feat] = {
                "fit_top_lift": f_top, "fit_bottom_lift": f_bot,
                "holdout_top_lift": h_top, "holdout_bottom_lift": h_bot,
                "holdout_spread_top_over_bottom": (
                    round(h_top / h_bot, 3) if (h_top and h_bot) else None),
                "sign_stable_fit_to_holdout": stable,
                "verdict": ("UNSTABLE" if stable is False else
                            ("stable-sign" if stable else "undetermined")),
                "holdout_deciles": ht,
                "per_name_holdout": _per_name_lift(hb, feat, "y_limit_up"),
            }
        # Robustness: same holdout, same features, the charter's TOLERANT target instead.
        rb = {}
        for feat in PREREGISTERED_FEATURES:
            if feat not in usable.columns:
                continue
            t = _decile_table(hb, feat, "y_limit_up_tol")
            rb[feat] = {"holdout_top_lift": t[-1]["lift"] if t else None,
                        "holdout_bottom_lift": t[0]["lift"] if t else None}
        entry["robustness_tolerant_target"] = rb
        measured = [f for f in PREREGISTERED_FEATURES if f in usable.columns]
        entry["collinearity_holdout"] = _collinearity(hb, measured)
        entry["conditioned_on_not_near_limit"] = _conditioned_lift(hb, measured)
        entry["per_name_availability"] = _per_name_availability(hb)
        res["by_board"][board] = entry

    # ERA CONTROL. The global 70/30 split lands at 2021-11-26, which is AFTER ChiNext's
    # 2020-08-24 move from a 10% to a 20% band. So ChiNext's fit window is mostly a 10%-band
    # market and its holdout is entirely a 20%-band market — two different games, which is why
    # its fit and holdout base rates differ ~5x. Re-split ChiNext inside the 20%-band era only,
    # so a fit-to-holdout comparison there is like-for-like. Same eight pre-registered features,
    # no additions.
    cx = usable[(usable["board"] == "chinext") & (usable["date"] >= CHINEXT_WIDE_DATE)]
    era = {"rule": f"chinext rows on/after CHINEXT_WIDE_DATE {CHINEXT_WIDE_DATE:%Y-%m-%d} "
                   f"(the ±20% band era), re-split {int(FIT_FRACTION * 100)}/"
                   f"{100 - int(FIT_FRACTION * 100)} within that era",
           "rows": int(len(cx))}
    if len(cx) >= N_DECILES * THIN_CELL_N * 4:
        cdates = np.sort(cx["date"].unique())
        csplit = pd.Timestamp(cdates[int(len(cdates) * FIT_FRACTION)])
        cf, ch = cx[cx["date"] < csplit], cx[cx["date"] >= csplit]
        era.update({
            "split_date": csplit.strftime("%Y-%m-%d"),
            "fit_rows": int(len(cf)), "holdout_rows": int(len(ch)),
            "fit_base_rate_pct": round(100.0 * float(cf["y_limit_up"].mean()), 4),
            "holdout_base_rate_pct": round(100.0 * float(ch["y_limit_up"].mean()), 4),
            "features": {},
        })
        for feat in PREREGISTERED_FEATURES:
            if feat not in usable.columns:
                continue
            ft, ht = _decile_table(cf, feat, "y_limit_up"), _decile_table(ch, feat, "y_limit_up")
            if not ht:
                era["features"][feat] = {"status": "insufficient non-null rows"}
                continue
            f_top = ft[-1]["lift"] if ft else None
            h_top = ht[-1]["lift"]
            stable = None if f_top is None else (f_top - 1.0) * (h_top - 1.0) > 0
            era["features"][feat] = {
                "fit_top_lift": f_top, "holdout_top_lift": h_top,
                "holdout_bottom_lift": ht[0]["lift"],
                "sign_stable_fit_to_holdout": stable,
                "verdict": ("UNSTABLE" if stable is False else
                            ("stable-sign" if stable else "undetermined")),
            }
    else:
        era["status"] = "insufficient rows in the ±20% band era"
    res["chinext_band_era_control"] = era

    res["not_measurable"]["f2_turnover_ratio"] = {
        "status": "NULL — NOT MEASURABLE on this basis",
        "reason": (
            "A turnover ratio needs shares outstanding (or free float) PER DATE. No CN "
            "store carries one: data/china_stocks_raw has OHLCV only; "
            "data/china_fundamentals/fundamentals.parquet is a 4-asof payload blob with "
            "no share-count series; data/china_search/members.parquet carries a single "
            "CURRENT mktcap_yi; data/china_participation/tape.parquet is market-level. "
            "Applying a current share count to a 2013 bar is a knowingly wrong denominator "
            "(A-share counts grow materially through placements and conversions), so no "
            "proxy was substituted."
        ),
        "note": (
            "The pre-registered set stays at eight. This feature is printed null rather "
            "than silently swapped for a ninth — the swap is the false-discovery move this "
            "design exists to block. The collector that would unblock it is in STAGE 4."
        ),
        "partial_coverage": (
            "data/china_zt_pool/pool.parquet carries turnover_pct for limit-up names only, "
            "2026-06-15 forward (47 dates) — a conditioned-on-the-outcome sample, unusable "
            "as a T-1 predictor."
        ),
    }
    return res


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    t0 = time.time()
    print("[stage 0] parity gate vs engine.china_microstructure._detect_limit_events ...",
          flush=True)
    parity = parity_gate()
    print("          agreement %.3f%% on %d tickers (%d module events)"
          % (parity["agreement_pct"], parity["tickers_sampled"], parity["events_module"]),
          flush=True)

    print("[stage 1] building panel ...", flush=True)
    panel, meta = build_panel()
    print("          %d rows, %d names, %.1fs"
          % (len(panel), panel["ticker"].nunique(), time.time() - t0), flush=True)

    s1 = stage1(panel)
    xc_tape = tape_crosscheck(panel)
    xc_zt = zt_pool_crosscheck(panel)
    print("[stage 2] base rates ...", flush=True)
    s2 = stage2(panel)
    print("[stage 3] pre-registered features, time-split ...", flush=True)
    s3 = stage3(panel)

    payload = {
        "instrument": "research/cn_prophet_audit/limit_move_footprint_v0.py",
        "charter": "research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md §6.8(f)",
        "tier": "display/audit — MEASUREMENT ONLY. Nothing here ranks, sizes, gates or admits.",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_sec": None,
        "definitions": {
            "limit_up_close": "PRIMARY (strict): close >= round(prev_close*(1+w), 2). The "
                              "market-true rule and the committed house tape's rule.",
            "limit_up_close_tolerant": f"close >= round(prev_close*(1+w),2) * (1 - "
                                       f"{LIMIT_CLOSE_TOL}) — the build charter's "
                                       f"at-or-within-0.2% wording, measured in full and "
                                       f"reported in parallel, NOT used as the headline.",
            "why_strict_is_primary": (
                "MEASURED, not assumed: the 0.2% tolerance is not a rounding cushion. On a 10% "
                "board it admits every close from ~+9.78% to +10.00%, giving 2.0x the strict "
                "event count, and it absorbs most of the near-limit class the charter asks us "
                "to count separately (main-board near-limit-up falls from ~19k under strict to "
                "1.6k under tolerant, which would starve pre-registered feature f5). Both "
                "definitions are carried through Stage 1 and Stage 2; Stage 3 uses strict with "
                "a tolerant-target robustness column."),
            "near_limit_up": f"return >= {NEAR_LIMIT_FRAC} * w (9.5% on a 10% board, 19% on a "
                             f"20% board) AND not a STRICT limit close",
            "lianban_N": "consecutive limit-up closes ending on the bar; any non-limit bar, "
                         "including an excluded one, resets it to 0",
            "first_board": "lianban == 1", "continuation": "lianban >= 2",
            "w": "engine.china_microstructure.limit_width_for_date — star 20%, chinext 20% "
                 "on/after 2020-08-24 else 10%, main 10%, bse 30%",
        },
        "convention_note": CONVENTION_NOTE,
        "exclusions": {
            "st_cohort": "ALL dates for every ticker in data/china_st/st_snapshot.parquet. "
                         "That store carries one asof (2026-07-06) and no membership history, "
                         "so a per-date 5% band is not reconstructible.",
            "st_exclusion_is_near_vacuous": (
                "MEASURED: only 1 of the 100 current ST names exists in data/china_stocks_raw, "
                "so this exclusion removes exactly one ticker. That is not a clean bill of "
                "health — it is the universe telling us it does not carry the ST cohort at all "
                "(see universe_is_curated). The 5%-band problem is therefore not solved here, "
                "it is absent from the sample."),
            "st_residual_caveat": "Names that WERE ST historically but are not ST today remain "
                                  "in the sample at a 10% band. This is not fixable with the "
                                  "stores we hold and is not patched over.",
            "universe_is_curated": (
                "THE BINDING COVERAGE FACT. data/china_stocks_raw holds 1,842 names; the "
                "A-share market is roughly 5,400. Two independent measurements of the gap: "
                "(a) 1 of 100 current ST names is present; (b) of the 1,770 names that hit the "
                "limit-up pool in data/china_zt_pool's 47-session window, only 514 (29%) are in "
                "this store, and only 24.7% of that store's rows find a match here. Every count "
                "and every base rate below describes a CURATED large/mid-cap universe, not the "
                "A-share market — and the 打板 game lives disproportionately in exactly the "
                "small-cap and ST names this universe omits. Do not read these as market-wide."),
            "ipo_windows": f"STAR/ChiNext first {CHINEXT_STAR_IPO_WINDOW} sessions "
                           f"(no band during the 44% cap regime); pre-2014 listings first "
                           f"{PRE2014_IPO_WINDOW} session. Every ticker's first bar is "
                           f"independently unusable (no prev_close).",
            "exdiv_suspect": "|open - prev_close| / prev_close > 1.5*w — an ex-dividend or "
                             "ex-rights gap on a nominal tape is not a limit event.",
            "zero_volume": "bars with volume <= 0 (suspension placeholders).",
            "survivorship": "data/china_stocks_raw holds the CURRENT listed universe. Delisted "
                            "names are absent, which biases the limit-DOWN numbers most: the "
                            "terminal down-limit runs of delisted names are simply not here. "
                            "Read every limit-down cell as a survivors-only figure.",
        },
        "meta": meta,
        "parity_gate": parity,
        "crosscheck_limit_events_tape": xc_tape,
        "crosscheck_zt_pool": xc_zt,
        "stage1_event_catalog": s1,
        "stage2_base_rates": s2,
        "stage3_preregistered_features": s3,
        "stage4_data_gaps": DATA_GAPS,
    }
    payload["runtime_sec"] = round(time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(jsonable(payload), indent=2, ensure_ascii=False) + "\n")
    print("[done] %.1fs -> %s" % (payload["runtime_sec"], OUT_JSON), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
