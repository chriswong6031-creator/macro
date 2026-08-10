#!/usr/bin/env python3
"""continuation_rider_v1.py — CN LIMIT-MOVE ALPHA, Wave 1 L1: THE CONTINUATION RIDER.

WHAT THIS IS
    A MEASUREMENT instrument, display/audit tier.  It asks one question the v0 footprint
    instrument (research/cn_prophet_audit/limit_move_footprint_v0.py, PR #4999) could not:

        given a name closed at the limit on day T with 连板 N, and given what its T+1
        OPENING AUCTION printed, what happens next — and could you actually have bought it?

    v0 established the ladder: P(next-bar limit-up close | 连板 N) is monotone and large
    (main 16.5% at N=1 → 72.8% at N=6) against a ~1.27% unconditional rate.  The ladder is
    a fact about the tape.  It is NOT an entry.  Two things stand between it and a trade,
    and this instrument measures both:

      (1) THE OPEN GAP.  The 09:15-09:25 call auction at T+1 is the first moment overnight
          demand becomes visible after a locked board hid it.  The gap it prints is
          decidable BEFORE the entry and tradable AT the entry, which makes it the only
          conditioner in the daily basis that is honestly entry-timed.
      (2) FILLABILITY.  A large share of realised continuation opens AT the limit (一字板).
          Those boards are counted by every base-rate table ever published and are not
          buyable at the open.  Every entry book here refuses them.  The share they carry
          is reported as THE FILLABILITY TAX — the continuation you cannot buy.

    FIVE constructions, all measured, all printed whether they work or not:

      C1  OPEN-GAP CONDITIONING (primary).  P(next board | board, N, gap band), plus the
          intraday-touch rate, the limit-DOWN tail, and the open→close return an entrant
          at the open actually receives.  Fit/holdout split; by-year for main N=1.
      C2  FILLABILITY-HONEST ENTRY BOOK.  Enter at the T+1 open only where the open is
          below the limit.  Three exit state machines on daily bars (E1 board-fail, E2
          first down-close, E3 T+4 time stop), each with LOCKED-EXIT HONESTY: a scheduled
          exit bar that opens at/below the limit-down price cannot be sold and is rolled.
      C3  CONFIRMED-LADDER VARIANT.  The same book restricted to N ≥ 2 at T, against N = 1.
      C4  DAY-OF-WEEK / FERMENTATION.  Continuation and expectancy by weekday of T, and by
          the calendar gap T→T+1 (1 day vs weekend vs holiday), era-controlled.
      C5  GAP-CONTINUOUS SHAPE.  Main N=1, 20 quantile bins of the gap — monotone, or a
          hump that rolls over into unfillability?

WHAT IT IS NOT
    Not a promotion, not a gate, not a ranker, not a signal, not a claim that any cell is
    tradeable.  Nothing here sizes, ranks, admits or scores anything.  No LLM is involved.
    THE ORE LAW binds: a null on one construction closes that construction and nothing
    else — see the ORE LEDGER in the receipt for what was NOT tested.

    Costs and slippage are NOT the headline.  Fills are assumed at the printed open, which
    is optimistic for exactly the names this study is about; a round-trip cost sensitivity
    is carried beside every return cell rather than in place of it.

CONVENTIONS — REUSED FROM v0 VERBATIM, NOT REINVENTED
    Board + limit width: engine.china_microstructure._board_from_ticker /
    limit_width_for_date (imported).  PRIMARY limit-up close: the tolerant test
    ``close >= round(prev_close*(1+w), 2) * (1 - 0.002)``, which v0 adjudicated against an
    independent vendor scrape (99.79% 连板 agreement vs 91.13% for strict) and adopted as
    primary; strict is carried as a parallel column where it is cheap.  Exclusions, the
    ≤10-calendar-day pair rule, the 2021-11-26 fit/holdout split, Wilson intervals, THIN
    labelling at n<20 and the never-pool-boards rule are all v0's and are unchanged.

    The v0 STAGE-2 ladder is RE-DERIVED here and pinned against v0's published numbers
    (see v0_ladder_parity) so this instrument's panel is shown to be the same panel before
    any of its own findings are read.

Run from repo root:  TZ=UTC python3 research/cn_prophet_audit/continuation_rider_v1.py
Outputs (frozen, committed):
    research/cn_prophet_audit/CONTINUATION_RIDER_V1_2026-08-08.json
    research/cn_prophet_audit/CONTINUATION_RIDER_V1_2026-08-08.md  (hand-written from the JSON)
"""
from __future__ import annotations

import json
import os
import sys
import time
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

# Import deliberately follows the TZ pin and the sys.path bootstrap above.
from engine.china_microstructure import (
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
OUT_JSON = (REPO / "research" / "cn_prophet_audit"
            / "CONTINUATION_RIDER_V1_2026-08-08.json")

# ── frozen parameters (all of them v0's unless marked NEW) ────────────────────

WINDOW_START = LIMIT_TAPE_START_DATE            # 2011-01-01
WINDOW_END = pd.Timestamp("2026-08-07")         # last bar in the raw store at build time

LIMIT_CLOSE_TOL = 0.002                         # v0's adjudicated tolerance (PRIMARY)
MAX_PAIR_GAP_DAYS = 10                          # T → T+1 must be within 10 calendar days
THIN_CELL_N = 20                                # cells below this n are labelled THIN

# v0's Stage-3 split date, REUSED as a frozen constant rather than re-derived.  Re-deriving
# a 70/30 split from this instrument's own row set would land on a different date and make
# the two studies non-comparable for no gain.
SPLIT_DATE = pd.Timestamp("2021-11-26")

# NEW — entry book parameters.
TIME_STOP_SESSIONS = 3          # E3: exit at the open of T+4  (T+1 entry + 3 sessions)
MAX_HOLD_SESSIONS = 30          # hard cap on the E1/E2 signal walk; hitting it is flagged
ROLL_CAP_SESSIONS = 10          # locked-exit roll cap, then forced close at the last close
# A-share round trip: 0.10% stamp duty (sell side) + ~0.025% commission each way.  Applied
# ONLY as a sensitivity column; every headline return in this file is gross.
ROUND_TRIP_COST = 0.0015

N_QUANTILE_BINS = 20            # C5 gap curve
N_COHORT_CAP = 3                # N cohorts are {1, 2, 3+}

GAP_BAND_LABELS = [
    "g0_below_-3pct",
    "g1_-3_to_0pct",
    "g2_0_to_+2pct",
    "g3_+2_to_+5pct",
    "g4_+5pct_to_0.95w",
    "g5_0.95w_to_limit",
    "g6_at_or_above_limit_UNFILLABLE",
]
# DEVIATION, disclosed: the brief's band list runs "[+5%, 0.95w)" straight into "opens at or
# above the limit".  Those two do not meet — on a 10% board 0.95w is +9.50% and the
# unfillable threshold is +9.78% — so a real slice of opens would have fallen through the
# partition and been silently dropped.  g5 is that slice, added so the bands are exhaustive.
GAP_BAND_NOTE = (
    "The brief's bands leave a hole between 0.95w and the unfillable threshold "
    "(+9.50%..+9.78% on a 10% board, +19.00%..+19.76% on a 20% board). g5 is that hole, "
    "added so every usable T+1 open lands in exactly one band. Bands are defined on the "
    "gap g = open[T+1]/close[T] - 1, except g6, which is defined on the PRICE test "
    "open[T+1] >= limit_price[T+1] * (1 - 0.002) — the same tolerant rule the limit-close "
    "definition uses. g6 rows are UNFILLABLE at the open by construction and are excluded "
    "from every entry book."
)

# v0's published STAGE-2 ladder (LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.md, Stage 2 table).
# Re-derived here and compared cell by cell. A mismatch means this instrument's panel is
# not v0's panel and every number below would be reading a different universe.
V0_PUBLISHED_LADDER = {
    "main":    {1: (38290, 16.50), 2: (6257, 36.61), 3: (2254, 45.52),
                4: (1019, 54.37), 5: (547, 66.91), 6: (360, 72.78)},
    "chinext": {1: (6587, 16.76), 2: (1094, 39.12), 3: (423, 52.48),
                4: (219, 63.47), 5: (137, 78.83), 6: (105, 76.19)},
    "star":    {1: (773, 10.09), 2: (77, 12.99), 3: (10, 50.00)},
}
V0_PUBLISHED_UNCONDITIONAL = {"main": 1.27, "chinext": 1.14, "star": 0.32}
V0_PARITY_RATE_TOL_PP = 0.02    # published to 2dp, so 0.02pp is the rounding floor

EXIT_RULES = {
    "E1_board_fail": "sell at the next open after the first session that FAILS to close "
                     "limit-up (the classic 打板 ride-the-ladder exit)",
    "E2_first_down_close": "sell at the next open after the first session that closes "
                           "below its own open",
    "E3_time_stop_T4": "sell at the open of T+4 (three sessions after the T+1 entry), "
                       "unconditionally",
}

LOCKED_EXIT_NOTE = (
    "LOCKED-EXIT HONESTY. A scheduled exit bar whose OPEN is at or below that bar's "
    "limit-down price (open <= limit_dn * (1 + 0.002)) cannot be sold at the open — the "
    "book is one-sided. The exit rolls to the next usable bar's open, up to "
    f"{ROLL_CAP_SESSIONS} sessions; if the chain breaks or the cap is exhausted the "
    "position is closed at the last available CLOSE and flagged forced_close. The roll rate "
    "and the mean extra loss the roll cost are reported per cell. Without this the book "
    "would sell the un-sellable at a price that never traded, which is the single largest "
    "way a 打板 backtest lies."
)


# ── small helpers ─────────────────────────────────────────────────────────────

def streak_lengths(flags: np.ndarray) -> np.ndarray:
    """Vectorised consecutive-True run length ending at each position (v0's helper)."""
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
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        return None if (np.isnan(obj) or np.isinf(obj)) else obj
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    return obj


def _r(x, nd=2):
    """Round or None. Never lets a NaN reach the JSON as a bare float."""
    if x is None:
        return None
    v = float(x)
    return None if (np.isnan(v) or np.isinf(v)) else round(v, nd)


def rate_block(k: int, n: int) -> dict:
    ci = wilson(k, n)
    return {
        "n": int(n), "k": int(k),
        "rate_pct": _r(100.0 * k / n) if n else None,
        "wilson95_pct": [_r(100.0 * ci[0]), _r(100.0 * ci[1])] if ci else None,
        "thin": bool(n < THIN_CELL_N),
    }


def ret_block(rets: np.ndarray, names: np.ndarray | None = None,
              dates: np.ndarray | None = None) -> dict:
    """Return-distribution block. Reports the clustering receipt beside the moments.

    n alone overstates independence badly here: limit-move runs cluster in theme waves, so
    a 900-trade cell can be a few dozen episodes. n_dates and the top-5-name share are
    printed so that is visible rather than inferred.
    """
    x = np.asarray(rets, dtype="float64")
    x = x[np.isfinite(x)]
    n = int(x.size)
    if n == 0:
        return {"n": 0, "thin": True}
    wins = int((x > 0).sum())
    ci = wilson(wins, n)
    out = {
        "n": n,
        "win_rate_pct": _r(100.0 * wins / n),
        "win_wilson95_pct": [_r(100.0 * ci[0]), _r(100.0 * ci[1])] if ci else None,
        "mean_pct": _r(100.0 * float(x.mean()), 3),
        "median_pct": _r(100.0 * float(np.median(x)), 3),
        "p10_pct": _r(100.0 * float(np.percentile(x, 10)), 3),
        "p90_pct": _r(100.0 * float(np.percentile(x, 90)), 3),
        "worst_pct": _r(100.0 * float(x.min()), 3),
        "best_pct": _r(100.0 * float(x.max()), 3),
        "std_pct": _r(100.0 * float(x.std(ddof=1)), 3) if n > 1 else None,
        "mean_after_costs_pct": _r(100.0 * float(((1.0 + x) * (1.0 - ROUND_TRIP_COST)
                                                  - 1.0).mean()), 3),
        "thin": bool(n < THIN_CELL_N),
    }
    if names is not None and len(names) == len(rets):
        nm = pd.Series(np.asarray(names)[np.isfinite(np.asarray(rets, dtype="float64"))])
        vc = nm.value_counts()
        out["n_names"] = int(vc.size)
        out["top5_name_share_pct"] = _r(100.0 * float(vc.head(5).sum()) / n)
    if dates is not None and len(dates) == len(rets):
        dt = pd.Series(np.asarray(dates)[np.isfinite(np.asarray(rets, dtype="float64"))])
        out["n_dates"] = int(dt.nunique())
    return out


def value_quantile_bins(v: pd.Series, nbins: int) -> pd.Series | None:
    """Quantile bins on VALUES, so ties share a bucket (v0's correction, kept).

    Binning ranks instead would guarantee `nbins` equal buckets even for a heavily tied
    variable, splitting one value across several 'quantiles' whose spread is cross-name
    base-rate variation wearing a feature's name.  Realised bucket counts are reported.
    """
    v = v.dropna()
    if v.empty:
        return None
    try:
        b = pd.qcut(v, nbins, labels=False, duplicates="drop")
    except ValueError:
        return None
    if b.isna().all():
        return None
    return b.astype("Int64")


# ── STAGE 0 — universe + exclusions (v0's, unchanged) ─────────────────────────

def load_st_cohort() -> tuple[frozenset[str], str]:
    """ST/*ST tickers, excluded wholesale on every date.

    data/china_st carries ONE asof and no membership history, so a per-date 5% band is not
    reconstructible; dropping the cohort is the conservative choice v0 made and this
    instrument does not relitigate it.
    """
    p = DATA / "china_st" / "st_snapshot.parquet"
    if not p.exists():
        return frozenset(), "st_snapshot.parquet MISSING — no ST exclusion applied"
    df = pd.read_parquet(p)
    tick = frozenset(df["ticker"].astype(str).tolist())
    asof = sorted(set(df["asof"].astype(str)))
    expected = ST_STORE_COVERAGE_DATE.strftime("%Y-%m-%d")
    return tick, (f"n={len(tick)} tickers, asof {asof}; engine ST_STORE_COVERAGE_DATE="
                  f"{expected}; still-single-date={len(asof) == 1 and asof[0] == expected}")


# ── per-ticker: panel arrays, event rows, entry book ──────────────────────────

def _ticker_arrays(df: pd.DataFrame, board: str) -> dict | None:
    """Full-history arrays for one ticker: prices, limits, exclusions, 连板."""
    if df is None or len(df) < 30:
        return None
    df = df.sort_index()
    idx = pd.to_datetime(df.index)
    o = df["open"].to_numpy(dtype=np.float64)
    h = df["high"].to_numpy(dtype=np.float64)
    lo = df["low"].to_numpy(dtype=np.float64)
    c = df["close"].to_numpy(dtype=np.float64)
    vol = df["volume"].to_numpy(dtype=np.float64)
    n = len(c)

    pc = np.roll(c, 1)
    pc[0] = np.nan

    if board == "chinext":
        wide = limit_width_for_date("chinext", CHINEXT_WIDE_DATE)
        narrow = limit_width_for_date("chinext", CHINEXT_WIDE_DATE - pd.Timedelta(days=1))
        width = np.where(idx.to_numpy() >= CHINEXT_WIDE_DATE.to_datetime64(), wide, narrow)
    else:
        width = np.full(n, limit_width_for_date(board, WINDOW_END), dtype=np.float64)
    width = width.astype(np.float64)

    # exclusions — identical to v0 / engine.china_microstructure._detect_limit_events
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
        open_move = np.abs(o - pc) / pc
    exdiv = np.isfinite(open_move) & (open_move > width * 1.5) & ~excl
    excl |= exdiv
    zero_vol = np.isfinite(vol) & (vol <= 0) & ~excl
    excl |= zero_vol

    with np.errstate(invalid="ignore"):
        lim_up = np.round(pc * (1.0 + width), 2)
        lim_dn = np.round(pc * (1.0 - width), 2)

    in_win = np.asarray((idx >= WINDOW_START) & (idx <= WINDOW_END), dtype=bool)
    live = in_win & ~excl

    lu = live & np.isfinite(lim_up) & (c >= lim_up * (1.0 - LIMIT_CLOSE_TOL))
    ld = live & np.isfinite(lim_dn) & (c <= lim_dn * (1.0 + LIMIT_CLOSE_TOL))
    lu_strict = live & np.isfinite(lim_up) & (c >= lim_up)
    lianban = streak_lengths(lu)

    days = idx.to_numpy().astype("datetime64[D]").astype(np.int64)

    return {
        "idx": idx, "o": o, "h": h, "lo": lo, "c": c, "pc": pc, "width": width,
        "lim_up": lim_up, "lim_dn": lim_dn, "live": live, "in_win": in_win,
        "lu": lu, "ld": ld, "lu_strict": lu_strict, "lianban": lianban,
        "days": days, "n": n,
        "excl_stats": {
            "ipo_excluded": int((ipo_mask & in_win).sum()),
            "exdiv_excluded": int((exdiv & in_win).sum()),
            "zero_volume_excluded": int((zero_vol & in_win).sum()),
            "bars_in_window": int(in_win.sum()),
            "live_bars_in_window": int(live.sum()),
        },
    }


def _gap_bands(gap: np.ndarray, width: np.ndarray, unfillable: np.ndarray,
               ok: np.ndarray) -> np.ndarray:
    """Band index per row; -1 where the T+1 bar is unusable."""
    b = np.select(
        [gap < -0.03, gap < 0.0, gap < 0.02, gap < 0.05, gap < 0.95 * width],
        [0, 1, 2, 3, 4], default=5).astype(np.int8)
    b = np.where(unfillable, np.int8(6), b)
    return np.where(ok & np.isfinite(gap), b, np.int8(-1)).astype(np.int8)


def process_ticker(ticker: str, A: dict, board: str):
    """Return (event rows for limit-up days, trade tuples). A from _ticker_arrays."""
    n = A["n"]
    live, lu, ld, c, o, h = A["live"], A["lu"], A["ld"], A["c"], A["o"], A["h"]
    lim_up, lim_dn, days = A["lim_up"], A["lim_dn"], A["days"]

    # ── T → T+1 pairing, v0's rule: the IMMEDIATELY following bar, live, ≤10 cal days.
    # Because the successor is always i+1, a usable chain is contiguous in array indices,
    # which is what makes the multi-session exit walk below exact rather than approximate.
    gap_next = np.r_[np.diff(days), np.iinfo(np.int64).max]
    pair_ok = gap_next <= MAX_PAIR_GAP_DAYS
    nxt_live = np.r_[live[1:], False]
    y_ok = pair_ok & nxt_live

    def shift_next(a, fill):
        return np.r_[a[1:], fill]

    nxt_o = shift_next(o, np.nan)
    nxt_h = shift_next(h, np.nan)
    nxt_c = shift_next(c, np.nan)
    nxt_lu = shift_next(lu, False)
    nxt_lu_strict = shift_next(A["lu_strict"], False)
    nxt_ld = shift_next(ld, False)
    nxt_lim_up = shift_next(lim_up, np.nan)
    # NOTE: the T+1 limit-DOWN price is deliberately NOT shifted here. The entry book reads
    # lim_dn[b] directly off the full array at whatever bar an exit lands on, which may be
    # many sessions past T+1; a shifted copy would only be usable for the T+1 bar and would
    # invite exactly the off-by-one this comment exists to prevent.
    nxt_width = shift_next(A["width"], np.nan)
    nxt_lo = shift_next(A["lo"], np.nan)

    with np.errstate(invalid="ignore", divide="ignore"):
        gap = nxt_o / c - 1.0
        r_oc = nxt_c / nxt_o - 1.0
    unfill = np.isfinite(nxt_o) & np.isfinite(nxt_lim_up) & (
        nxt_o >= nxt_lim_up * (1.0 - LIMIT_CLOSE_TOL))
    touch = np.isfinite(nxt_h) & np.isfinite(nxt_lim_up) & (
        nxt_h >= nxt_lim_up * (1.0 - LIMIT_CLOSE_TOL))
    # strict 一字: the whole T+1 bar printed at the limit (open == high == low == close).
    yizi = unfill & nxt_lu & np.isfinite(nxt_lo) & (nxt_o == nxt_h) & (nxt_o == nxt_lo) \
        & (nxt_o == nxt_c)
    band = _gap_bands(gap, nxt_width, unfill, y_ok)

    sel = np.where(live & lu)[0]           # every limit-up board-day in window
    if sel.size == 0:
        return None, []

    idx = A["idx"]
    ev = pd.DataFrame({
        "date": idx[sel],
        "ticker": ticker,
        "board": board,
        "N": A["lianban"][sel].astype(np.int16),
        "y_ok": y_ok[sel],
        "pair_gap_days": np.where(pair_ok[sel], gap_next[sel], -1).astype(np.int16),
        "gap": gap[sel].astype(np.float32),
        "band": band[sel],
        "unfillable_open": unfill[sel] & y_ok[sel],
        "yizi_strict": yizi[sel] & y_ok[sel],
        "y_limit_up": nxt_lu[sel] & y_ok[sel],
        "y_limit_up_strict": nxt_lu_strict[sel] & y_ok[sel],
        "y_limit_down": nxt_ld[sel] & y_ok[sel],
        "y_touch": touch[sel] & y_ok[sel],
        "r_open_close": np.where(y_ok[sel], r_oc[sel], np.nan).astype(np.float32),
    })

    # ── the entry book ────────────────────────────────────────────────────────
    def usable_next(i: int) -> int:
        j = i + 1
        if j >= n:
            return -1
        if not bool(live[j]):
            return -1
        if days[j] - days[i] > MAX_PAIR_GAP_DAYS:
            return -1
        return j

    def resolve_exit(b_sched: int, fallback_bar: int):
        """Turn a scheduled exit bar into a realised (price, bar, rolls, forced) tuple."""
        if b_sched < 0:
            return float(c[fallback_bar]), fallback_bar, 0, True, np.nan
        sched_open = float(o[b_sched])
        rolls = 0
        b = b_sched
        while bool(np.isfinite(lim_dn[b])) and o[b] <= lim_dn[b] * (1.0 + LIMIT_CLOSE_TOL):
            if rolls >= ROLL_CAP_SESSIONS:
                return float(c[b]), b, rolls, True, sched_open
            nb = usable_next(b)
            rolls += 1
            if nb < 0:
                return float(c[b]), b, rolls, True, sched_open
            b = nb
        return float(o[b]), b, rolls, False, sched_open

    trades = []
    entry_ok = ev["y_ok"].to_numpy() & ~ev["unfillable_open"].to_numpy()
    for pos, t in enumerate(sel):
        if not bool(entry_ok[pos]):
            continue
        e = t + 1                      # y_ok guarantees this is the usable successor
        entry_px = float(o[e])
        if not np.isfinite(entry_px) or entry_px <= 0:
            continue
        N = int(A["lianban"][t])
        bnd = int(band[t])
        dt = idx[t]

        for rule in ("E1_board_fail", "E2_first_down_close", "E3_time_stop_T4"):
            forced_walk = False
            if rule == "E3_time_stop_T4":
                cur = e
                ok_walk = True
                for _ in range(TIME_STOP_SESSIONS):
                    nb = usable_next(cur)
                    if nb < 0:
                        ok_walk = False
                        break
                    cur = nb
                b_sched = cur if ok_walk else -1
                fallback = cur
            else:
                cur = e
                steps = 0
                while True:
                    if rule == "E1_board_fail":
                        cont = bool(lu[cur])
                    else:
                        cont = bool(c[cur] >= o[cur])
                    if not cont:
                        break
                    nb = usable_next(cur)
                    if nb < 0 or steps >= MAX_HOLD_SESSIONS:
                        forced_walk = True
                        break
                    cur = nb
                    steps += 1
                b_sched = -1 if forced_walk else usable_next(cur)
                fallback = cur
            px, b_exit, rolls, forced, sched_open = resolve_exit(b_sched, fallback)
            ret = px / entry_px - 1.0
            extra = (px / sched_open - 1.0) if (rolls > 0 and np.isfinite(sched_open)
                                                and sched_open > 0) else np.nan
            trades.append((
                dt, ticker, board, N, bnd, rule, entry_px, px, ret,
                int(b_exit - e), rolls, bool(forced or forced_walk), extra,
            ))

    return ev, trades


# ── price-basis audit ─────────────────────────────────────────────────────────
#
# NOT decoration. Every limit price in this file is round(prev_close*(1+w), 2), and that
# expression only means what it says if prev_close is a real 0.01-tick A-share price. An
# A-share close CANNOT be a non-2-decimal number, so the share of non-2dp closes is a direct,
# decisive measurement of whether the store is a nominal tape. Prices are stored float32, so
# the test is tolerant to ~1e-4 of a cent, not exact.
TWO_DP_TOL_CENTS = 0.02


def _accumulate_price_basis(A: dict, acc: dict) -> None:
    live = A["live"]
    if not bool(live.any()):
        return
    c = A["c"][live]
    yrs = A["idx"][live].year.to_numpy()
    is2 = np.abs(c * 100.0 - np.round(c * 100.0)) < TWO_DP_TOL_CENTS
    for y in np.unique(yrs):
        m = yrs == y
        slot = acc["by_year"].setdefault(int(y), [0, 0])
        slot[0] += int(m.sum())
        slot[1] += int(is2[m].sum())
    acc["names"] += 1
    if bool(is2.all()):
        acc["names_all_2dp"] += 1
    else:
        acc["last_non_2dp"].append(A["idx"][live][~is2].max())

    # How far the tick-rounding of the limit price moves it, relative to the true band.
    # This is the exact quantity v0's 0.002 tolerance has to absorb; if its tail exceeded
    # the tolerance the primary limit rule would be losing real events.
    pc = A["pc"][live]
    w = A["width"][live]
    exact = pc * (1.0 + w)
    ok = np.isfinite(exact) & (exact > 0)
    err = np.abs(np.round(exact, 2) - exact)[ok] / exact[ok]
    acc["live_bars"] += int(ok.sum())
    acc["err_over_tol"] += int((err > LIMIT_CLOSE_TOL).sum())
    acc["err_over_half_tol"] += int((err > LIMIT_CLOSE_TOL / 2).sum())
    if err.size:
        acc["max_err"] = max(acc["max_err"], float(err.max()))
        acc["tick_err_samples"].extend(err[::500].tolist())


def price_basis_audit(acc: dict) -> dict:
    by_year = [{"year": y, "live_bars": v[0], "closes_on_the_0.01_tick": v[1],
                "share_on_tick_pct": _r(100.0 * v[1] / v[0]) if v[0] else None}
               for y, v in sorted(acc["by_year"].items())]
    s = np.asarray(acc["tick_err_samples"], dtype="float64")
    pct = ({f"p{q}": _r(100.0 * float(np.percentile(s, q)), 4)
            for q in (50, 90, 99, 99.9, 100)} if s.size else {})
    lastn = pd.Series(acc["last_non_2dp"])
    return {
        "question": ("Is data/china_stocks_raw a NOMINAL A-share tape? An exchange close is "
                     "always a whole number of 0.01 ticks, so any non-2-decimal close is "
                     "proof of an applied adjustment factor."),
        "by_year": by_year,
        "names_measured": acc["names"],
        "names_on_tick_for_their_whole_history": acc["names_all_2dp"],
        "last_off_tick_bar_percentiles": ({
            "p10": lastn.quantile(0.10).strftime("%Y-%m-%d"),
            "p50": lastn.quantile(0.50).strftime("%Y-%m-%d"),
            "p90": lastn.quantile(0.90).strftime("%Y-%m-%d"),
            "max": lastn.max().strftime("%Y-%m-%d"),
        } if len(lastn) else None),
        "tick_rounding_error_on_the_limit_price_pct": pct,
        "tick_rounding_error_sample_n": int(s.size),
        "live_bars_measured": acc["live_bars"],
        "bars_where_rounding_error_exceeds_the_0.002_tolerance": acc["err_over_tol"],
        "bars_where_rounding_error_exceeds_half_the_tolerance": acc["err_over_half_tol"],
        "max_rounding_error_pct": _r(100.0 * acc["max_err"], 4),
        "reading": (
            "MEASURED, not asserted. The store is BACK-ADJUSTED, not nominal: closes sit "
            "exactly on the 0.01 tick from each name's most recent corporate action forward "
            "and are scaled (off-tick) before it, which is the back-adjustment signature and "
            "is why the off-tick share falls monotonically toward the present. v0's header "
            "calls this store 'nominal/unadjusted'; that description is wrong, and the "
            "correction should land in the CN data-plane docs. It does NOT overturn v0's "
            "definition adjudication — it EXPLAINS it. Rounding a scaled price to a 0.01 tick "
            "is exactly why the strict test close >= round(prev_close*(1+w), 2) is brittle "
            "against its own inputs, and why a cushion was needed. What matters for THIS "
            "instrument is whether 0.002 is a big enough cushion, which is the measured tail "
            "above. Note also that adjustment PRESERVES returns, so every gap, every "
            "open-to-close and every trade return in this file is unaffected; only the "
            "round-to-tick step is."),
    }


# ── panel build ───────────────────────────────────────────────────────────────

_T0 = [time.time()]

TRADE_COLS =["date", "ticker", "board", "N", "band", "rule", "entry_px", "exit_px",
              "ret", "hold_sessions", "rolls", "forced_close", "roll_extra_loss"]


def build(verbose: bool = True):
    st_set, st_note = load_st_cohort()
    files = sorted((DATA / "china_stocks_raw").glob("*.parquet"))

    agg = {"ipo_excluded": 0, "exdiv_excluded": 0, "zero_volume_excluded": 0,
           "bars_in_window": 0, "live_bars_in_window": 0}
    uncond = {}     # board -> [usable rows, next-bar limit-up count]
    boards_seen, kept, skipped_st, skipped_thin = {}, 0, 0, 0
    ev_frames, trade_rows = [], []
    basis = {"by_year": {}, "tick_err_samples": [], "live_bars": 0, "err_over_tol": 0,
             "err_over_half_tol": 0, "max_err": 0.0, "names_all_2dp": 0, "names": 0,
             "last_non_2dp": []}

    for i, p in enumerate(files):
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
        A = _ticker_arrays(df, board)
        if A is None:
            skipped_thin += 1
            continue
        _accumulate_price_basis(A, basis)
        # unconditional next-bar limit-up rate, accumulated as scalars (the full 4.98M-row
        # panel is never materialised — this instrument only needs the limit-up days).
        live = A["live"]
        days = A["days"]
        gap_next = np.r_[np.diff(days), np.iinfo(np.int64).max]
        y_ok = (gap_next <= MAX_PAIR_GAP_DAYS) & np.r_[live[1:], False]
        usable = live & y_ok
        slot = uncond.setdefault(board, [0, 0])
        slot[0] += int(usable.sum())
        slot[1] += int((usable & np.r_[A["lu"][1:], False]).sum())

        for k in agg:
            agg[k] += A["excl_stats"][k]
        boards_seen[board] = boards_seen.get(board, 0) + 1
        kept += 1

        ev, trades = process_ticker(ticker, A, board)
        if ev is not None and len(ev):
            ev_frames.append(ev)
        if trades:
            trade_rows.extend(trades)
        if verbose and (i + 1) % 400 == 0:
            print(f"          ... {i + 1}/{len(files)} files "
                  f"({time.time() - _T0[0]:.0f}s)", flush=True)

    events = pd.concat(ev_frames, ignore_index=True)
    events["year"] = events["date"].dt.year.astype(np.int16)
    events["dow"] = events["date"].dt.dayofweek.astype(np.int8)
    events["era"] = np.where(events["date"] < SPLIT_DATE, "fit", "holdout")
    events["Ncoh"] = np.minimum(events["N"].to_numpy(), N_COHORT_CAP).astype(np.int8)

    trades = pd.DataFrame(trade_rows, columns=TRADE_COLS)
    trades["year"] = trades["date"].dt.year.astype(np.int16)
    trades["dow"] = trades["date"].dt.dayofweek.astype(np.int8)
    trades["era"] = np.where(trades["date"] < SPLIT_DATE, "fit", "holdout")
    trades["Ncoh"] = np.minimum(trades["N"].to_numpy(), N_COHORT_CAP).astype(np.int8)

    raw_names = {p.stem for p in files}
    gapmeta = {"raw_store_names": len(raw_names), "st_snapshot_names": len(st_set),
               "st_names_present_in_raw": len(st_set & raw_names)}
    zp = DATA / "china_zt_pool" / "pool.parquet"
    if zp.exists():
        zt_names = set(pd.read_parquet(zp)["ticker"].astype(str))
        gapmeta.update({
            "zt_pool_names": len(zt_names),
            "zt_pool_names_present_in_raw": len(zt_names & raw_names),
            "zt_pool_names_present_pct": _r(
                100.0 * len(zt_names & raw_names) / max(1, len(zt_names)), 1),
        })

    meta = {
        "raw_store": ("data/china_stocks_raw — the correct basis of the two, and the one v0 "
                      "used. NOT the adjusted twin data/china_stocks, which carries a second, "
                      "larger adjustment factor and would fabricate limit misses. See "
                      "price_basis_audit: this store is itself BACK-ADJUSTED rather than "
                      "nominal, which is a measured correction to v0's description of it."),
        "files_found": len(files),
        "tickers_kept": kept,
        "tickers_skipped_st": skipped_st,
        "tickers_skipped_thin_or_unreadable": skipped_thin,
        "board_counts": boards_seen,
        "st_cohort": st_note,
        "window": [WINDOW_START.strftime("%Y-%m-%d"), WINDOW_END.strftime("%Y-%m-%d")],
        "excluded_bars": agg,
        "universe_gap": gapmeta,
        "limit_up_days": len(events),
        "limit_up_days_with_usable_next_bar": int(events["y_ok"].sum()),
        "entries_fillable": int(len(trades) // max(1, len(EXIT_RULES))),
        "unconditional_next_bar_limit_up": {
            b: {"usable_ticker_days": v[0], "next_bar_limit_up": v[1],
                "rate_pct": _r(100.0 * v[1] / v[0]) if v[0] else None}
            for b, v in sorted(uncond.items())},
    }
    return events, trades, meta, price_basis_audit(basis)


# ── v0 parity gate ────────────────────────────────────────────────────────────

def v0_ladder_parity(events: pd.DataFrame, meta: dict) -> dict:
    """Re-derive v0's Stage-2 ladder and pin it against v0's PUBLISHED numbers.

    This is the only check that this instrument is standing on the same panel the
    adjudicated v0 study stood on.  It is deliberately a comparison against published
    OUTPUT rather than a re-import of v0's code: v0 lives on an unmerged branch, and a
    number that has been through adversarial review is the stronger reference anyway.
    """
    u = events[events["y_ok"]]
    rows, worst_rate, worst_n = [], 0.0, 0
    for board, cells in V0_PUBLISHED_LADDER.items():
        g = u[u["board"] == board]
        for N, (pub_n, pub_rate) in sorted(cells.items()):
            cell = g[g["N"] == N]
            n = len(cell)
            k = int(cell["y_limit_up"].sum())
            rate = 100.0 * k / n if n else float("nan")
            d_rate = abs(rate - pub_rate) if n else float("nan")
            rows.append({
                "board": board, "N": N,
                "published_n": pub_n, "measured_n": n, "delta_n": n - pub_n,
                "published_rate_pct": pub_rate, "measured_rate_pct": _r(rate),
                "delta_rate_pp": _r(d_rate, 4),
                "match": bool(n == pub_n and np.isfinite(d_rate)
                              and d_rate <= V0_PARITY_RATE_TOL_PP),
            })
            if np.isfinite(d_rate):
                worst_rate = max(worst_rate, d_rate)
            worst_n = max(worst_n, abs(n - pub_n))
    unc = []
    for board, pub in V0_PUBLISHED_UNCONDITIONAL.items():
        m = meta["unconditional_next_bar_limit_up"].get(board, {})
        unc.append({"board": board, "published_rate_pct": pub,
                    "measured_rate_pct": m.get("rate_pct"),
                    "usable_ticker_days": m.get("usable_ticker_days")})
    return {
        "reference": ("research/cn_prophet_audit/LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.md "
                      "STAGE 2 (PR #4999, branch claude/cn-limit-footprint-v0)"),
        "cells": rows,
        "cells_matched": int(sum(1 for r in rows if r["match"])),
        "cells_total": len(rows),
        "max_abs_delta_n": int(worst_n),
        "max_abs_delta_rate_pp": _r(worst_rate, 4),
        "unconditional": unc,
        "verdict": ("PASS — every published ladder cell reproduced exactly (n) and to "
                    "published precision (rate)."
                    if all(r["match"] for r in rows) else
                    "MISMATCH — see cells; do not read anything below until resolved."),
    }


# ── C1 — open-gap conditioning ────────────────────────────────────────────────

def _c1_cell(g: pd.DataFrame) -> dict:
    n = len(g)
    out = {"n": n, "thin": bool(n < THIN_CELL_N)}
    out["p_next_board"] = rate_block(int(g["y_limit_up"].sum()), n)
    out["p_intraday_touch"] = rate_block(int(g["y_touch"].sum()), n)
    out["p_limit_down_close"] = rate_block(int(g["y_limit_down"].sum()), n)
    out["p_unfillable_open"] = rate_block(int(g["unfillable_open"].sum()), n)
    r = g["r_open_close"].to_numpy(dtype="float64")
    r = r[np.isfinite(r)]
    if r.size:
        out["open_to_close"] = {
            "n": int(r.size),
            "mean_pct": _r(100.0 * float(r.mean()), 3),
            "median_pct": _r(100.0 * float(np.median(r)), 3),
            "p10_pct": _r(100.0 * float(np.percentile(r, 10)), 3),
            "p90_pct": _r(100.0 * float(np.percentile(r, 90)), 3),
            "share_positive_pct": _r(100.0 * float((r > 0).mean())),
        }
    out["n_names"] = int(g["ticker"].nunique())
    out["n_dates"] = int(g["date"].nunique())
    return out


def c1_open_gap(events: pd.DataFrame) -> dict:
    u = events[events["y_ok"]].copy()
    res = {
        "definition": {
            "gap": "g = open[T+1] / close[T] - 1, decidable at the 09:25 call auction",
            "bands": GAP_BAND_LABELS,
            "band_note": GAP_BAND_NOTE,
            "N_cohorts": "1, 2, 3+ (3+ pools every 连板 >= 3)",
            "p_next_board": "the name closes at the limit again on T+1 (tolerant rule)",
            "p_intraday_touch": "high[T+1] >= limit_price[T+1] * (1 - 0.002) — the board was "
                                "touched at some point, whether or not it held",
            "p_limit_down_close": "close[T+1] at the DOWN limit — the tail an open-entrant eats",
            "open_to_close": "close[T+1]/open[T+1] - 1 — the day-1 return of an entrant who "
                             "bought the open and sold the close",
        },
        "by_era": {},
    }
    for era in ("all", "fit", "holdout"):
        e = u if era == "all" else u[u["era"] == era]
        rows = []
        for board in sorted(e["board"].unique()):
            gb = e[e["board"] == board]
            for Nc in sorted(gb["Ncoh"].unique()):
                gn = gb[gb["Ncoh"] == Nc]
                rec = {"board": board, "N_cohort": f"{Nc}+" if Nc == N_COHORT_CAP else str(Nc),
                       "band": "ALL"}
                rec.update(_c1_cell(gn))
                rows.append(rec)
                for bi in range(len(GAP_BAND_LABELS)):
                    cell = gn[gn["band"] == bi]
                    if not len(cell):
                        continue
                    rec = {"board": board,
                           "N_cohort": f"{Nc}+" if Nc == N_COHORT_CAP else str(Nc),
                           "band": GAP_BAND_LABELS[bi],
                           "band_share_of_cohort_pct": _r(100.0 * len(cell) / len(gn))}
                    rec.update(_c1_cell(cell))
                    rows.append(rec)
        res["by_era"][era] = rows

    # by-year, main N=1 — the era story the pooled table hides
    m1 = u[(u["board"] == "main") & (u["Ncoh"] == 1)]
    yr = []
    for year, g in m1.groupby("year", observed=True):
        rec = {"year": int(year), "band": "ALL"}
        rec.update(_c1_cell(g))
        rec["share_unfillable_pct"] = _r(100.0 * float(g["unfillable_open"].mean()))
        fill = g[~g["unfillable_open"]]
        rec["p_next_board_fillable_only"] = rate_block(
            int(fill["y_limit_up"].sum()), len(fill))
        yr.append(rec)
        for bi in range(len(GAP_BAND_LABELS)):
            cell = g[g["band"] == bi]
            if not len(cell):
                continue
            rec = {"year": int(year), "band": GAP_BAND_LABELS[bi], "n": len(cell)}
            rec.update(rate_block(int(cell["y_limit_up"].sum()), len(cell)))
            yr.append(rec)
    yr.sort(key=lambda r: (r["year"], r["band"]))
    res["main_N1_by_year"] = yr
    return res


# ── THE FILLABILITY TAX ───────────────────────────────────────────────────────

def fillability_tax(events: pd.DataFrame) -> dict:
    u = events[events["y_ok"]]
    rows = []
    for board in sorted(u["board"].unique()):
        gb = u[u["board"] == board]
        for Nc in ["ALL"] + sorted(gb["Ncoh"].unique().tolist()):
            g = gb if Nc == "ALL" else gb[gb["Ncoh"] == Nc]
            boards_realised = g[g["y_limit_up"]]
            nb = len(boards_realised)
            rows.append({
                "board": board,
                "N_cohort": Nc if Nc == "ALL" else (
                    f"{Nc}+" if Nc == N_COHORT_CAP else str(Nc)),
                "board_days": len(g),
                "p_next_board_pct": _r(100.0 * float(g["y_limit_up"].mean())),
                "realised_next_boards": nb,
                "of_which_unfillable_open": int(boards_realised["unfillable_open"].sum()),
                "FILLABILITY_TAX_pct": _r(
                    100.0 * float(boards_realised["unfillable_open"].mean())) if nb else None,
                "of_which_strict_yizi": int(boards_realised["yizi_strict"].sum()),
                "strict_yizi_share_pct": _r(
                    100.0 * float(boards_realised["yizi_strict"].mean())) if nb else None,
                "p_next_board_BUYABLE_pct": _r(
                    100.0 * float((g["y_limit_up"] & ~g["unfillable_open"]).mean())),
                "entry_availability_pct": _r(100.0 * float((~g["unfillable_open"]).mean())),
                "p_next_board_GIVEN_fillable_entry_pct": _r(
                    100.0 * float(g.loc[~g["unfillable_open"], "y_limit_up"].mean())
                ) if int((~g["unfillable_open"]).sum()) else None,
                "thin": bool(nb < THIN_CELL_N),
            })
    return {
        "definition": {
            "unfillable_open": "open[T+1] >= limit_price[T+1] * (1 - 0.002) — the 一字/秒板 "
                               "open. The name is already sealed when the continuous session "
                               "starts; there is no price at which a new entrant is filled.",
            "strict_yizi": "the whole T+1 bar printed at the limit (open == high == low == "
                           "close) — the narrowest reading of 一字板, carried beside the "
                           "actionable one.",
            "FILLABILITY_TAX": "share of REALISED next-day boards whose T+1 open was "
                               "unfillable — the continuation you cannot buy.",
            "entry_availability": "share of board-days that offered a fillable T+1 open at "
                                  "all — the denominator side of the same fact.",
            "p_next_board_GIVEN_fillable_entry": (
                "P(next board | the T+1 open was fillable) — the only version of the ladder a "
                "trader can act on. Everything else in this table exists to show how far it "
                "sits below the published ladder."),
        },
        "by_board_N": rows,
    }


# ── C2 / C3 — the entry book ──────────────────────────────────────────────────

def _book_cell(g: pd.DataFrame) -> dict:
    out = ret_block(g["ret"].to_numpy(), g["ticker"].to_numpy(), g["date"].to_numpy())
    if out["n"] == 0:
        return out
    out["mean_hold_sessions"] = _r(float(g["hold_sessions"].mean()), 2)
    out["median_hold_sessions"] = _r(float(g["hold_sessions"].median()), 1)
    rolled = g["rolls"].to_numpy() > 0
    out["rolled_exit_pct"] = _r(100.0 * float(rolled.mean()))
    out["n_rolled"] = int(rolled.sum())
    ex = g["roll_extra_loss"].to_numpy(dtype="float64")
    ex = ex[np.isfinite(ex)]
    out["rolled_mean_extra_loss_pct"] = _r(100.0 * float(ex.mean()), 3) if ex.size else None
    out["rolled_worst_extra_loss_pct"] = _r(100.0 * float(ex.min()), 3) if ex.size else None
    out["forced_close_pct"] = _r(100.0 * float(g["forced_close"].mean()))
    return out


def c2_entry_book(trades: pd.DataFrame) -> dict:
    res = {
        "entry": ("BUY at the open of T+1, and ONLY where open[T+1] < limit_price[T+1] * "
                  "(1 - 0.002). Unfillable (一字) opens are refused, not modelled as fills."),
        "exit_rules": EXIT_RULES,
        "locked_exit_note": LOCKED_EXIT_NOTE,
        "cost_note": (f"Every return is GROSS. mean_after_costs_pct applies a flat "
                      f"{ROUND_TRIP_COST * 100:.2f}% round trip (0.10% stamp duty on the sell "
                      f"+ ~0.025% commission each way). SLIPPAGE IS NOT MODELLED: fills are "
                      f"assumed at the printed open, which is optimistic for exactly these "
                      f"names."),
        "clustering_note": ("n counts trades, not independent episodes — limit-move runs "
                            "arrive in theme waves. n_dates and top5_name_share_pct are "
                            "printed on every cell so the effective sample is visible."),
        "by_era": {},
    }
    for era in ("all", "fit", "holdout"):
        t = trades if era == "all" else trades[trades["era"] == era]
        rows = []
        for board in sorted(t["board"].unique()):
            tb = t[t["board"] == board]
            for rule in EXIT_RULES:
                tr = tb[tb["rule"] == rule]
                for Nc in ["ALL"] + sorted(tr["Ncoh"].unique().tolist()):
                    tn = tr if Nc == "ALL" else tr[tr["Ncoh"] == Nc]
                    label = Nc if Nc == "ALL" else (
                        f"{Nc}+" if Nc == N_COHORT_CAP else str(Nc))
                    rec = {"board": board, "rule": rule, "N_cohort": label, "band": "ALL"}
                    rec.update(_book_cell(tn))
                    rows.append(rec)
                    for bi in range(len(GAP_BAND_LABELS)):
                        cell = tn[tn["band"] == bi]
                        if not len(cell):
                            continue
                        rec = {"board": board, "rule": rule, "N_cohort": label,
                               "band": GAP_BAND_LABELS[bi]}
                        rec.update(_book_cell(cell))
                        rows.append(rec)
        res["by_era"][era] = rows
    return res


def c3_confirmed_ladder(trades: pd.DataFrame) -> dict:
    """N >= 2 at T versus N == 1, same book, same exits, same fillability rule."""
    rows = []
    for era in ("fit", "holdout"):
        t = trades[trades["era"] == era]
        for board in sorted(t["board"].unique()):
            tb = t[t["board"] == board]
            for rule in EXIT_RULES:
                tr = tb[tb["rule"] == rule]
                a = tr[tr["Ncoh"] == 1]
                b = tr[tr["Ncoh"] >= 2]
                ra, rb = _book_cell(a), _book_cell(b)
                rows.append({
                    "era": era, "board": board, "rule": rule,
                    "N1": ra, "N2plus": rb,
                    "delta_mean_pp": (_r(rb.get("mean_pct", 0) - ra.get("mean_pct", 0), 3)
                                      if ra.get("n") and rb.get("n") else None),
                    "delta_win_rate_pp": (
                        _r(rb.get("win_rate_pct", 0) - ra.get("win_rate_pct", 0))
                        if ra.get("n") and rb.get("n") else None),
                })
    return {
        "question": ("The ladder says a confirmed 连板 continues far more often. The entry "
                     "book asks whether that survives the two things the ladder ignores — "
                     "you must be able to BUY it, and you must be able to SELL it."),
        "comparisons": rows,
    }


# ── C4 — day of week / fermentation ───────────────────────────────────────────

DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}


def _gapclass(d: int) -> str:
    if d == 1:
        return "1d_intraweek"
    if 2 <= d <= 3:
        return "2-3d_weekend"
    return "4d+_holiday"


def c4_fermentation(events: pd.DataFrame, trades: pd.DataFrame) -> dict:
    u = events[events["y_ok"]].copy()
    u["dow_name"] = u["dow"].map(DOW_NAMES)
    u["gapclass"] = [_gapclass(int(d)) for d in u["pair_gap_days"].to_numpy()]
    t = trades.copy()
    t["dow_name"] = t["dow"].map(DOW_NAMES)

    by_dow = []
    for era in ("all", "fit", "holdout"):
        e = u if era == "all" else u[u["era"] == era]
        for board in sorted(e["board"].unique()):
            gb = e[e["board"] == board]
            for Nc in ["ALL"] + sorted(gb["Ncoh"].unique().tolist()):
                gn = gb if Nc == "ALL" else gb[gb["Ncoh"] == Nc]
                label = Nc if Nc == "ALL" else (
                    f"{Nc}+" if Nc == N_COHORT_CAP else str(Nc))
                for dow in sorted(gn["dow"].unique()):
                    cell = gn[gn["dow"] == dow]
                    rec = {"era": era, "board": board, "N_cohort": label,
                           "dow": DOW_NAMES[int(dow)]}
                    rec.update(rate_block(int(cell["y_limit_up"].sum()), len(cell)))
                    rec["share_unfillable_pct"] = _r(
                        100.0 * float(cell["unfillable_open"].mean()))
                    rec["mean_gap_pct"] = _r(100.0 * float(
                        np.nanmean(cell["gap"].to_numpy(dtype="float64"))), 3)
                    by_dow.append(rec)

    by_gapclass = []
    for era in ("all", "fit", "holdout"):
        e = u if era == "all" else u[u["era"] == era]
        for board in sorted(e["board"].unique()):
            gb = e[e["board"] == board]
            for Nc in ["ALL"] + sorted(gb["Ncoh"].unique().tolist()):
                gn = gb if Nc == "ALL" else gb[gb["Ncoh"] == Nc]
                label = Nc if Nc == "ALL" else (
                    f"{Nc}+" if Nc == N_COHORT_CAP else str(Nc))
                for gc in sorted(gn["gapclass"].unique()):
                    cell = gn[gn["gapclass"] == gc]
                    rec = {"era": era, "board": board, "N_cohort": label, "gap_class": gc}
                    rec.update(rate_block(int(cell["y_limit_up"].sum()), len(cell)))
                    rec["share_unfillable_pct"] = _r(
                        100.0 * float(cell["unfillable_open"].mean()))
                    by_gapclass.append(rec)

    # THE OPERATOR'S SPECIFIC HYPOTHESIS: Friday boards ferment over the weekend.
    friday_test = []
    for era in ("fit", "holdout"):
        e = u[u["era"] == era]
        for board in sorted(e["board"].unique()):
            gb = e[e["board"] == board]
            for Nc in sorted(gb["Ncoh"].unique().tolist()):
                gn = gb[gb["Ncoh"] == Nc]
                fri = gn[gn["dow"] == 4]
                mid = gn[gn["dow"].isin([1, 2, 3])]
                fb = rate_block(int(fri["y_limit_up"].sum()), len(fri))
                mb = rate_block(int(mid["y_limit_up"].sum()), len(mid))
                overlap = None
                if fb["wilson95_pct"] and mb["wilson95_pct"]:
                    overlap = not (fb["wilson95_pct"][0] > mb["wilson95_pct"][1]
                                   or mb["wilson95_pct"][0] > fb["wilson95_pct"][1])
                friday_test.append({
                    "era": era, "board": board,
                    "N_cohort": f"{Nc}+" if Nc == N_COHORT_CAP else str(Nc),
                    "friday": fb, "tue_wed_thu": mb,
                    "delta_pp": (_r(fb["rate_pct"] - mb["rate_pct"])
                                 if fb["rate_pct"] is not None
                                 and mb["rate_pct"] is not None else None),
                    "wilson_intervals_overlap": overlap,
                    "friday_share_unfillable_pct": _r(
                        100.0 * float(fri["unfillable_open"].mean())) if len(fri) else None,
                    "midweek_share_unfillable_pct": _r(
                        100.0 * float(mid["unfillable_open"].mean())) if len(mid) else None,
                })

    # THE CONTROL THE HYPOTHESIS NEEDS. Friday boards gap up MORE than midweek boards, and
    # the gap is already this study's strongest conditioner — so a raw Friday-vs-midweek
    # difference could be the gap wearing a weekday hat. Re-run the comparison INSIDE each
    # gap band: if the Friday edge survives, fermentation adds something the gap does not
    # already carry; if it vanishes, the weekday variable is redundant.
    within_band = []
    for era in ("fit", "holdout"):
        e = u[u["era"] == era]
        for board in ("main", "chinext"):
            gb = e[e["board"] == board]
            for Nc in (1, 2):
                gn = gb[gb["Ncoh"] == Nc]
                for bi in range(len(GAP_BAND_LABELS)):
                    cell = gn[gn["band"] == bi]
                    fri = cell[cell["dow"] == 4]
                    mid = cell[cell["dow"].isin([1, 2, 3])]
                    if not len(fri) or not len(mid):
                        continue
                    fb = rate_block(int(fri["y_limit_up"].sum()), len(fri))
                    mb = rate_block(int(mid["y_limit_up"].sum()), len(mid))
                    overlap = None
                    if fb["wilson95_pct"] and mb["wilson95_pct"]:
                        overlap = not (fb["wilson95_pct"][0] > mb["wilson95_pct"][1]
                                       or mb["wilson95_pct"][0] > fb["wilson95_pct"][1])
                    within_band.append({
                        "era": era, "board": board, "N_cohort": str(Nc),
                        "band": GAP_BAND_LABELS[bi],
                        "friday_n": fb["n"], "friday_rate_pct": fb["rate_pct"],
                        "midweek_n": mb["n"], "midweek_rate_pct": mb["rate_pct"],
                        "delta_pp": (_r(fb["rate_pct"] - mb["rate_pct"])
                                     if fb["rate_pct"] is not None
                                     and mb["rate_pct"] is not None else None),
                        "wilson_intervals_overlap": overlap,
                        "thin": bool(fb["thin"] or mb["thin"]),
                    })

    # expectancy by weekday, holdout, E1 — the entry-book version of the same question
    expectancy = []
    for board in sorted(t["board"].unique()):
        for rule in EXIT_RULES:
            for era in ("fit", "holdout"):
                tt = t[(t["board"] == board) & (t["rule"] == rule) & (t["era"] == era)]
                for dow in sorted(tt["dow"].unique()):
                    cell = tt[tt["dow"] == dow]
                    rec = {"era": era, "board": board, "rule": rule,
                           "dow": DOW_NAMES[int(dow)]}
                    rec.update(_book_cell(cell))
                    expectancy.append(rec)

    xtab = (u.groupby(["dow", "gapclass"], observed=True).size()
            .reset_index(name="n"))
    xtab["dow"] = xtab["dow"].map(DOW_NAMES)
    return {
        "hypothesis": ("Operator: a board printed on Friday ferments over the weekend — "
                       "after-hours discussion recruits Monday demand the midweek board "
                       "never gets. Tested as (a) continuation rate by weekday of T, "
                       "(b) continuation rate by the calendar gap T->T+1, and (c) entry-book "
                       "expectancy by weekday. Era-controlled throughout."),
        "collinearity_warning": (
            "Weekday of T and the T->T+1 calendar gap are ~the same variable: a Friday board "
            "almost always has a 3-day gap and a Mon-Thu board a 1-day gap. The two tables "
            "below are therefore ONE test presented two ways, not two independent tests. The "
            "cross-tab is printed so that is checkable rather than asserted."),
        "dow_x_gapclass_crosstab": xtab.to_dict("records"),
        "continuation_by_dow": by_dow,
        "continuation_by_gap_class": by_gapclass,
        "friday_vs_midweek": friday_test,
        "friday_vs_midweek_WITHIN_gap_band": within_band,
        "entry_book_expectancy_by_dow": expectancy,
    }


# ── C5 — the gap-continuous shape ─────────────────────────────────────────────

def c5_gap_curve(events: pd.DataFrame) -> dict:
    u = events[(events["board"] == "main") & (events["Ncoh"] == 1) & events["y_ok"]].copy()
    out = {
        "cohort": "main board, 连板 N = 1, usable T+1",
        "method": (f"{N_QUANTILE_BINS} quantile bins on the VALUES of g (ties share a bin, "
                   f"so realised bin counts and sizes are printed, not assumed equal)"),
        "curves": {},
    }
    for era in ("all", "fit", "holdout"):
        e = u if era == "all" else u[u["era"] == era]
        for scope, sub in (("all_opens", e), ("fillable_only", e[~e["unfillable_open"]])):
            b = value_quantile_bins(sub["gap"], N_QUANTILE_BINS)
            if b is None:
                out["curves"][f"{era}__{scope}"] = {"status": "insufficient rows"}
                continue
            sub = sub.loc[b.index]
            rows = []
            for bi, g in sub.groupby(b, observed=True):
                rec = {"bin": int(bi),
                       "gap_lo_pct": _r(100.0 * float(g["gap"].min()), 3),
                       "gap_hi_pct": _r(100.0 * float(g["gap"].max()), 3),
                       "share_of_rows_pct": _r(100.0 * len(g) / len(sub), 3),
                       "share_unfillable_pct": _r(
                           100.0 * float(g["unfillable_open"].mean()))}
                rec.update(rate_block(int(g["y_limit_up"].sum()), len(g)))
                rec["p_limit_down_pct"] = _r(100.0 * float(g["y_limit_down"].mean()))
                rec["open_to_close_mean_pct"] = _r(100.0 * float(
                    np.nanmean(g["r_open_close"].to_numpy(dtype="float64"))), 3)
                rows.append(rec)
            rows.sort(key=lambda r: (r["gap_lo_pct"], r["bin"]))
            rates = [r["rate_pct"] for r in rows if r["rate_pct"] is not None]
            peak = int(np.argmax(rates)) if rates else None
            # A bare all(rates[i] <= rates[i+1]) reads False on one 0.3pp wobble in a flat
            # floor, which would let a real monotone curve be reported as "not monotone".
            # So the decreases are COUNTED, and separately counted when they are large enough
            # that the two bins' Wilson intervals do not even overlap.
            dec, sig_dec = 0, 0
            for i in range(len(rows) - 1):
                a, b = rows[i], rows[i + 1]
                if a["rate_pct"] is None or b["rate_pct"] is None:
                    continue
                if b["rate_pct"] < a["rate_pct"]:
                    dec += 1
                    wa, wb = a["wilson95_pct"], b["wilson95_pct"]
                    if wa and wb and wb[1] < wa[0]:
                        sig_dec += 1
            # elbow: the lowest bin from which every later bin's rate exceeds the floor
            # (the median rate of the bins whose gap range sits entirely at or below zero).
            floor_rates = [r["rate_pct"] for r in rows
                           if r["gap_hi_pct"] is not None and r["gap_hi_pct"] <= 0
                           and r["rate_pct"] is not None]
            floor = float(np.median(floor_rates)) if floor_rates else None
            elbow = None
            if floor is not None:
                for i, r in enumerate(rows):
                    if r["rate_pct"] is not None and r["rate_pct"] > 2.0 * floor and all(
                            (x["rate_pct"] or 0) > floor for x in rows[i:]):
                        elbow = {"bin_index_from_low": i,
                                 "gap_lo_pct": r["gap_lo_pct"],
                                 "rate_pct": r["rate_pct"]}
                        break
            out["curves"][f"{era}__{scope}"] = {
                "realised_bins": len(rows),
                "rows": rows,
                "strictly_monotone_increasing": bool(dec == 0),
                "adjacent_decreases": dec,
                "adjacent_decreases_with_disjoint_wilson": sig_dec,
                "down_gap_floor_rate_pct": _r(floor),
                "elbow_first_bin_at_2x_the_floor": elbow,
                "peak_bin_index_from_low": peak,
                "peak_bin_gap_range_pct": (
                    [rows[peak]["gap_lo_pct"], rows[peak]["gap_hi_pct"]]
                    if peak is not None else None),
                "peak_rate_pct": rates[peak] if peak is not None else None,
                "last_bin_rate_pct": rates[-1] if rates else None,
                "rolls_over_after_peak": bool(
                    peak is not None and peak < len(rates) - 1
                    and rates[-1] < rates[peak]),
            }
    out["reading"] = (
        "The shape question the brief asks — monotone, or a hump that rolls over into "
        "unfillability — is answered by rolls_over_after_peak together with "
        "adjacent_decreases_with_disjoint_wilson. A handful of adjacent_decreases inside the "
        "flat down-gap floor is sampling noise; a decrease whose Wilson intervals are "
        "DISJOINT is a shape claim."
    )
    return out


# ── ORE LEDGER (structured; the receipt carries the prose version) ────────────

ORE_LEDGER = {
    "law": ("THE ORE LAW: a null closes the CONSTRUCTION TESTED, never the hypothesis. "
            "Everything below is untested by this instrument — none of it is refuted by "
            "anything above, and several items are the obvious next constructions."),
    "untested_variants": [
        {"variant": "intraday pullback entries (buy the first dip after a strong open, or "
                    "the 09:35/10:00 print instead of the open)",
         "blocked_by": "needs minute bars; the daily basis has one price per session",
         "why_it_matters": "the gap bands here are entry-timed but entry-PRICED only at the "
                           "open; a weak-open band that nulls at the open may still pay on a "
                           "pullback, and a strong-open band that pays at the open may be "
                           "unreachable in practice"},
        {"variant": "seal-break (开板) re-entry — buy when a sealed board breaks and re-seals",
         "blocked_by": "needs intraday first-touch times and seal-break counts (collector #3 "
                       "in the v0 data-gap receipt)",
         "why_it_matters": "the single most-used discretionary 打板 entry; entirely invisible "
                           "in a daily bar, where a 09:31 seal and a 14:55 seal are one row"},
        {"variant": "closing-auction imbalance conditioning at T (14:57-15:00 集合竞价)",
         "blocked_by": "collector #2 in the v0 data-gap receipt — not collected",
         "why_it_matters": "the mechanism the gap is a downstream proxy for; if the imbalance "
                           "is the real conditioner, the gap bands are a lossy shadow of it"},
        {"variant": "封单量 (resting order-wall volume at the limit) conditioning",
         "blocked_by": "held for 2026-06-15 forward only (data/china_zt_pool.seal_fund_yi), "
                       "no history",
         "why_it_matters": "the practitioner's primary conviction measure; without it "
                           "'limit-up' pools a ~100x range of demand into one flag"},
        {"variant": "regime-gate interaction (does the rider only work in hot tape?)",
         "blocked_by": "deliberately out of scope — this is the Wave-2 cross with the L2 "
                       "market-state lane",
         "why_it_matters": "the by-year table already shows a 3x era swing in the base rate; "
                           "a market-state gate is the obvious conditioner and is NOT tested "
                           "here"},
        {"variant": "stop-loss exit family (fixed %, ATR, trailing, intraday stop)",
         "blocked_by": "an intraday stop is unmeasurable on daily bars without assuming a "
                       "path; a close-based stop was not in the pre-registered exit set",
         "why_it_matters": "the p10 and worst-trade columns show where a stop would bind; "
                           "three exit rules is not the exit space"},
        {"variant": "per-N and per-band exit tuning (different exit rule per cohort)",
         "blocked_by": "not run — the same three rules are applied to every cohort by design, "
                       "so the cohort comparison is like-for-like",
         "why_it_matters": "an E3 time stop tuned per N is an obvious improvement and an "
                           "obvious overfit; it needs its own holdout discipline"},
        {"variant": "ST universe (5% band) and BSE (30% band)",
         "blocked_by": "ST dropped wholesale (no membership history); the raw store carries "
                       "ZERO bse names",
         "why_it_matters": "the 打板 game lives disproportionately in small-cap and ST names; "
                           "this study cannot see them at all"},
        {"variant": "replication on the zt_pool universe (the vendor's whole-market limit-up "
                    "pool) rather than the curated raw store",
         "blocked_by": "zt_pool covers 2026-06-15 forward only — no history to replicate on",
         "why_it_matters": "only 29% of the names that hit the vendor's limit-up pool exist "
                           "in our universe; the coverage gap is the largest single "
                           "limitation of every number here"},
        {"variant": "short side — riding limit-DOWN continuation",
         "blocked_by": "A-share retail short-selling is largely unavailable, and the store is "
                       "survivors-only so the terminal down-runs of delisted names are absent",
         "why_it_matters": "the limit-down cells printed here are survivor-biased UPWARD "
                           "(they under-count catastrophe) and must not be read as a short "
                           "opportunity"},
        {"variant": "sector/theme cohort conditioning (is the rider a theme-wave artifact?)",
         "blocked_by": "not run in this lane; v0's f4 sector-heat feature is the nearest probe",
         "why_it_matters": "the clustering receipt (n_dates vs n) shows trades arrive in "
                           "waves; whether the gap edge survives within-wave is untested"},
    ],
}


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    t0 = time.time()
    _T0[0] = t0
    print("[build] panel + entry book over data/china_stocks_raw ...", flush=True)
    events, trades, meta, basis = build()
    print(f"        {len(events)} limit-up board-days, {len(trades)} trade legs, "
          f"{time.time() - t0:.1f}s", flush=True)

    print("[gate ] v0 ladder parity ...", flush=True)
    parity = v0_ladder_parity(events, meta)
    print(f"        {parity['cells_matched']}/{parity['cells_total']} cells matched; "
          f"max |Δn|={parity['max_abs_delta_n']}, "
          f"max |Δrate|={parity['max_abs_delta_rate_pp']}pp", flush=True)

    print("[C1   ] open-gap conditioning ...", flush=True)
    c1 = c1_open_gap(events)
    print("[tax  ] fillability tax ...", flush=True)
    tax = fillability_tax(events)
    print("[C2/C3] entry book + confirmed-ladder variant ...", flush=True)
    c2 = c2_entry_book(trades)
    c3 = c3_confirmed_ladder(trades)
    print("[C4   ] day-of-week / fermentation ...", flush=True)
    c4 = c4_fermentation(events, trades)
    print("[C5   ] gap-continuous shape ...", flush=True)
    c5 = c5_gap_curve(events)

    payload = {
        "instrument": "research/cn_prophet_audit/continuation_rider_v1.py",
        "program": "CN LIMIT-MOVE ALPHA, Wave 1, lane L1 — THE CONTINUATION RIDER",
        "builds_on": ("research/cn_prophet_audit/limit_move_footprint_v0.py (PR #4999) — "
                      "conventions reused verbatim, ladder re-derived and pinned"),
        "tier": "display/audit — MEASUREMENT ONLY. Nothing here ranks, sizes, gates or admits.",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_sec": None,
        "definitions": {
            "limit_up_close_PRIMARY": (
                f"close >= round(prev_close*(1+w), 2) * (1 - {LIMIT_CLOSE_TOL}). v0's "
                "adjudicated primary: the tolerance is a feed-precision cushion (the median "
                "marginal event moved exactly 100.000% of the band and 43.4% moved strictly "
                "MORE, which is impossible for a real limit-up), corroborated by the vendor "
                "scrape agreeing with it on 99.79% of matched 连板 rows vs 91.13% for strict."),
            "limit_up_close_strict": "close >= round(prev_close*(1+w), 2) — carried as a "
                                     "parallel column on the T+1 outcome.",
            "limit_down_close": f"close <= round(prev_close*(1-w), 2) * (1 + {LIMIT_CLOSE_TOL})",
            "lianban_N": "consecutive limit-up closes ending on the bar; any non-limit bar, "
                         "including an excluded one, resets it to 0",
            "T_to_T1": (f"the IMMEDIATELY following bar, which must be live and at most "
                        f"{MAX_PAIR_GAP_DAYS} calendar days later. Because the successor is "
                        f"always i+1, a usable chain is contiguous, which makes the "
                        f"multi-session exit walk exact."),
            "w": "engine.china_microstructure.limit_width_for_date — star 20%, chinext 20% "
                 "on/after 2020-08-24 else 10%, main 10%, bse 30%",
            "fit_holdout_split": (f"{SPLIT_DATE:%Y-%m-%d} — v0's computed 70/30 date, REUSED "
                                  f"as a frozen constant so the two studies are comparable. "
                                  f"Holdout is the headline."),
        },
        "exclusions": {
            "st_cohort": "ALL dates for every ticker in data/china_st/st_snapshot.parquet "
                         "(one asof, no membership history, so a per-date 5% band is not "
                         "reconstructible).",
            "ipo_windows": f"STAR/ChiNext first {CHINEXT_STAR_IPO_WINDOW} sessions; pre-2014 "
                           f"listings' first {PRE2014_IPO_WINDOW} session. Every ticker's "
                           f"first bar is independently unusable (no prev_close).",
            "exdiv_suspect": (
                "|open - prev_close| / prev_close > 1.5*w. NOTE the residual this leaves for a "
                "GAP study specifically: the store is back-adjusted for splits but a cash "
                "dividend still prints a mechanical gap-down of roughly the yield on its "
                "ex-date, far below the 1.5*w trigger. Those land in band g1 [-3%, 0) and are "
                "not overnight demand — they are arithmetic. A-share names go ex once a year, "
                "so this dilutes g1 by order 0.4% of its rows for a limit-up cohort; it is "
                "noise, not a direction, because a name's ex-date is uncorrelated with its "
                "having boarded the day before. Disclosed rather than patched, because "
                "patching it needs a dividend calendar this repo does not hold per date."),
            "zero_volume": "bars with volume <= 0 (suspension placeholders)",
            "universe_is_curated": (
                "THE BINDING COVERAGE FACT. data/china_stocks_raw holds a curated subset of "
                "the listed A-share market (roughly 5,400 names — an external reference "
                "figure, not one these stores measure). See meta.universe_gap for the two "
                "store-measured probes. The 打板 game lives disproportionately in exactly the "
                "small-cap and ST names this universe omits. No number here is market-wide."),
            "survivorship": (
                "The store holds the CURRENT listed universe. Delisted names are absent, "
                "which biases the limit-DOWN cells most: the terminal down-limit runs of "
                "delisted names are simply not here, so every limit-down rate below is a "
                "SURVIVORS-ONLY figure and reads better than the truth."),
            "usability_asymmetry": (
                "A bar's usability at T+1 is a property of T+1, so conditioning on it is a "
                "filter a trader at T could not apply. It is applied uniformly to numerator "
                "and denominator (v0's handling, unchanged), so ratios are essentially "
                "unaffected; absolute rates are rates among USABLE next bars, not among all "
                "next bars. This instrument adds a second, sharper instance of the same "
                "asymmetry and does NOT hide it: the entry book refuses unfillable opens, "
                "which is a T+1 property — but that one is legitimate, because the 09:25 "
                "auction prints BEFORE the 09:30 entry. Fillability is knowable at entry; "
                "next-bar usability is not."),
        },
        "meta": meta,
        "price_basis_audit": basis,
        "v0_ladder_parity": parity,
        "c1_open_gap_conditioning": c1,
        "fillability_tax": tax,
        "c2_entry_book": c2,
        "c3_confirmed_ladder": c3,
        "c4_dow_fermentation": c4,
        "c5_gap_curve": c5,
        "ore_ledger": ORE_LEDGER,
    }
    payload["runtime_sec"] = round(time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(jsonable(payload), indent=2, ensure_ascii=False) + "\n")
    print(f"[done ] {payload['runtime_sec']:.1f}s -> {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
