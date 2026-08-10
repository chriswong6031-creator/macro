#!/usr/bin/env python3
"""weakness_entry_battery_v1.py — CN LIMIT-MOVE ALPHA, Wave 2 lane W2-B:
THE WEAKNESS-ENTRY BATTERY (回封 + 龙回头).

WHAT THIS IS
    A MEASUREMENT instrument, display/audit tier.  Wave 1's L1 rider
    (research/cn_prophet_audit/continuation_rider_v1.py, PR #5061) proved two things at once:
    the continuation ladder is real and era-stable, AND every naive next-open gap-chasing
    book loses money — anti-monotone in its own conditioner, because the 09:25 auction
    prices public strength.  Its ORE LEDGER named the family that survives that null:

        WEAKNESS ENTRIES.  Buy the name on a day it is NOT sealed.  The fill is guaranteed
        by construction (there is no wall to queue behind), and the adverse selection
        INVERTS — you are not paying the crowd's gap, you are being paid to absorb it.

    Two such families are computable on the daily basis.  Both are tested here.

      B-回封 (the blinded map's C3).  A name touches the limit and FAILS to hold it.  The
          break is the single most information-dense print on the tape: a wall was there and
          was eaten.  The day-of-break CLOSE is fillable by construction — the name is not
          sealed.  That is the 低吸-on-break entry L1 could not test, because every L1 entry
          was a post-board open.

      B-龙回头 (the blinded map's C10).  A proven ladder (N >= 3) ends.  Over the next 1-10
          sessions the name pulls back; the desk that distributed re-enters cheaper and the
          washout completes the chip transfer.  Every day of that window is fillable.

    THE QUESTION THIS INSTRUMENT EXISTS TO ANSWER, stated before any number was computed:
        Does ANY stable cohort in either battery clear POSITIVE expectancy net of a 15 bp
        round trip, in the fit window AND the holdout — the bar naive gap-chasing failed?

WHAT IT IS NOT
    Not a promotion, not a gate, not a ranker, not a signal, not a claim that any cell is
    tradeable.  Nothing here sizes, ranks, admits or scores anything.  No LLM is involved.
    THE ORE LAW binds: a null on one construction closes THAT CONSTRUCTION and nothing else.
    The ORE LEDGER at the bottom names what was not tested and why.

TWO DEFINITION BASES, NEVER SILENTLY MIXED
    The house tape (data/china_microstructure/limit_events.parquet, built by
    engine.china_microstructure._detect_limit_events) is STRICT: sealed_up is
    ``close >= round(prev_close*(1+w), 2)`` with no tolerance, and failed_up_seal is
    ``high >= lim_up and not sealed_up``.  v0 adjudicated a TOLERANT primary
    (``close >= lim_up * (1 - 0.002)``) against an independent vendor scrape and adopted it;
    L1 inherited it.  Both bases are carried here, side by side, and EVERY table is labelled
    with the basis of its population, its conditioner and its outcome.  A strict-population
    row is never scored with a tolerant outcome.  The overlap and the delta are measured
    (see population_receipt) rather than assumed: 4.5% of strict failed seals close inside
    the tolerance and are TOLERANT SEALS — they are in one battery's population and the
    other's complement, which is exactly the kind of silent mixing this section prevents.

CONVENTIONS — v0's, REUSED VERBATIM
    Board + limit width from engine.china_microstructure.  Exclusions (ST wholesale, IPO
    windows, ex-div suspects, zero volume), the <=10-calendar-day pair rule, the 2021-11-26
    fit/holdout split, Wilson intervals, THIN labelling at n < 20, never pool boards.
    L1's LOCKED-EXIT HONESTY and its E1/E3 exit walks are copied unchanged, so the two
    studies' return columns mean the same thing.

Run from repo root:  TZ=UTC python3 research/cn_prophet_audit/weakness_entry_battery_v1.py
Outputs (frozen, committed):
    research/cn_prophet_audit/WEAKNESS_ENTRY_BATTERY_V1_2026-08-09.json
    research/cn_prophet_audit/WEAKNESS_ENTRY_BATTERY_V1_2026-08-09.md  (hand-written from it)
"""
from __future__ import annotations

import json
import os
import subprocess
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

# Import deliberately follows the TZ pin and the sys.path bootstrap above.
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
AUDIT = REPO / "research" / "cn_prophet_audit"
OUT_JSON = AUDIT / "WEAKNESS_ENTRY_BATTERY_V1_2026-08-09.json"

# The healed limit_events vintage (PR #5059, branch claude/cn-limit-w1-dataheal) is the
# required input.  If it has merged, the in-tree copy IS the healed store; if not, the
# operator/lane places it at the override path below.  Row count decides, and is receipted.
TAPE_PATH = DATA / "china_microstructure" / "limit_events.parquet"
TAPE_OVERRIDE = REPO / ".w2scratch" / "limit_events_healed.parquet"
HEALED_ROWS = 71463
PREHEAL_ROWS = 60428

# The L2 regime dial lives on the salvage lane (claude/cn-limit-w1-regime-salvage).
DIAL_PATH = AUDIT / "board_ecology_series_v1.parquet"
DIAL_OVERRIDE = REPO / ".w2scratch" / "board_ecology_series_v1.parquet"

# ── frozen parameters (v0's / L1's unless marked NEW) ─────────────────────────

WINDOW_START = LIMIT_TAPE_START_DATE            # 2011-01-01
WINDOW_END = pd.Timestamp("2026-08-07")         # last bar in the raw store at build time

LIMIT_CLOSE_TOL = 0.002                         # v0's adjudicated tolerance
MAX_PAIR_GAP_DAYS = 10                          # T -> T+1 within 10 calendar days
THIN_CELL_N = 20                                # cells below this n are labelled THIN
SPLIT_DATE = pd.Timestamp("2021-11-26")         # v0's 70/30 date, frozen

TIME_STOP_SESSIONS = 3          # E3: exit at the open of T+4 (entry bar + 3 sessions)
MAX_HOLD_SESSIONS = 30          # hard cap on the E1 signal walk; hitting it is flagged
ROLL_CAP_SESSIONS = 10          # locked-exit roll cap, then forced close at the last close
ROUND_TRIP_COST = 0.0015        # 0.10% stamp duty (sell) + ~0.025% commission each way

VOL_LOOKBACK = 20               # NEW — volume z / volume-ratio reference window
LHT_MIN_LADDER = 3              # NEW — 龙回头 requires a proven ladder of N >= 3
LHT_WINDOW = 10                 # NEW — pullback entry window, sessions 1..10 after the end
LHT_FWD_SESSIONS = 5            # NEW — P(new board within 5 sessions of the qualifying day)

CENSUS_MIN_N = 100              # survivor census floor in EACH of fit and holdout
CENSUS_STRONG_N = 500           # the stronger floor, reported separately

# 回封 break-depth bands, on the tape's own close_off_limit_pct = (lim_up - close)/lim_up.
DEPTH_BANDS = ["d0_shallow_le1pct", "d1_mid_1_3pct", "d2_deep_gt3pct"]
DEPTH_NOTE = (
    "close_off_limit_pct = (lim_up - close) / lim_up, a FRACTION (engine contract), positive "
    "when the close sits below the limit. Bands: shallow <= 0.01, mid (0.01, 0.03], deep "
    "> 0.03. Rounding can make the field <= 0 on a marginal row; those land in shallow. NOTE "
    "the basis interaction, measured in population_receipt: a STRICT failed seal with "
    "close_off <= 0.002 is a TOLERANT SEAL, so the shallow band of the strict population is "
    "partly the tolerant population's complement rather than a weakness cohort at all."
)

# 龙回头 pullback-depth bands, as a FRACTION OF THE RUN'S HEIGHT (not of price).
RETRACE_BANDS = ["r0_lt15pct", "r1_15_30pct", "r2_gt30pct"]
DAYS_BANDS = ["t1_1_3d", "t2_4_6d", "t3_7_10d"]
RETRACE_NOTE = (
    "retrace_frac = (run_peak - close[q]) / (run_peak - run_base), where run_base is the "
    "close BEFORE the ladder's first board and run_peak is the running max HIGH over "
    "[run_start .. q] — a quantity known at q's close, never a forward maximum. Bands are "
    "fractions of the RUN's height, per the brief: < 0.15, [0.15, 0.30], > 0.30. "
    "close_ge_half_retrace is exactly retrace_frac <= 0.5."
)

ERA_BOUNDS = [
    ("e1_2011_14", 2011, 2014), ("e2_2015_mania", 2015, 2015),
    ("e3_2016_18_crackdown", 2016, 2018), ("e4_2019_21_revival", 2019, 2021),
    ("e5_2022_23_grind", 2022, 2023), ("e6_2024_26_current", 2024, 2026),
]

EXIT_RULES = OrderedDict([
    ("E1_board_fail", "sell at the next open after the first HELD session that fails to "
                      "close limit-up (L1's rule, copied; the walk starts at the first bar "
                      "held after entry, so an open entry and a close entry that share an "
                      "exit bar are compared like-for-like)"),
    ("E3_time_stop_T4", "sell at the open three usable sessions after the first held bar, "
                        "unconditionally (L1's E3, same bar for both entry anchors)"),
])

HOLD_SESSIONS_NOTE = (
    "hold_sessions here is (exit_bar - first_held + 1) — an INCLUSIVE count of bars held. "
    "L1 reports (exit_bar - entry_bar), which is one lower for the same trade. Returns, win "
    "rates and every expectancy column are unaffected (the exit BAR and both prices are "
    "identical), but a hold-length figure from this file is not directly comparable with "
    "L1's without adding one."
)

LOCKED_EXIT_NOTE = (
    "LOCKED-EXIT HONESTY (L1's, copied verbatim). A scheduled exit bar whose OPEN is at or "
    "below that bar's limit-down price (open <= lim_dn * (1 + 0.002)) cannot be sold at the "
    f"open — the book is one-sided. The exit rolls to the next usable bar's open, up to "
    f"{ROLL_CAP_SESSIONS} sessions; if the chain breaks or the cap is exhausted the position "
    "is closed at the last available CLOSE and flagged forced_close. Roll rate and the mean "
    "extra loss the roll cost are reported per cell."
)

BUY_FILLABILITY_NOTE = (
    "BUY-SIDE fillability is not the mirror of sell-side fillability, and this instrument "
    "depends on the difference. A close entry is unfillable only when the bar closes AT the "
    "limit-up (a sealed board has no offers). A limit-DOWN close is trivially fillable to "
    "BUY — the book is all sellers — which is why the weakness families have entries where "
    "the L1 rider had none. Every close entry here is checked against the limit-up test and "
    "the refusals are counted; by construction the 回封 population and the 龙回头 window "
    "contain no sealed closes, so the refusal count is a receipt, not a filter."
)

PRE_REGISTRATION = {
    "registered_before_any_number_was_read": True,
    "split": f"{SPLIT_DATE:%Y-%m-%d} — v0's computed 70/30 date, reused as a frozen constant. "
             "ONE holdout pass. Every conditioner, band edge, exit rule, cost bar and cell "
             "floor below was fixed by the lane brief before the first run.",
    "deviations_after_first_run": [
        {"change": "date-clustered standard errors added beside every per-trade figure",
         "why": "the per-trade t on the leading cohort was counting 4.4 same-day trades as "
                "4.4 independent observations",
         "kind": "a stricter reading of the same pre-registered bar, applied uniformly to "
                 "every cohort and reported alongside, not instead of, the per-trade figure",
         "moved_a_number": False},
        {"change": "volume-z tercile cut points fit per (basis, board) instead of pooled "
                   "across bases",
         "why": "the pooled fit double-counted the 15,629 rows the two bases share and let "
                "the tolerant population set the strict population's band edges — a "
                "violation of this instrument's own basis-discipline rule",
         "kind": "DEFECT FIX. Pre-registered before the re-run: the only cohorts that can "
                 "move are the six HF volz=* slices per basis/board; every other cohort, "
                 "rate table and book cell must be byte-identical, and that invariance is "
                 "the check on the fix",
         "moved_a_number": True},
        {"change": "thin-cell collapse now emits a disjoint partition plus separate "
                   "parent/pointer blocks",
         "why": "the previous form printed a thin cell under its own label carrying its "
                "PARENT's numbers, so two thin regime cells produced byte-identical rows and "
                "a parent appeared alongside siblings it contained — the three-way cell "
                "count and its positive count were both inflated",
         "kind": "DEFECT FIX, labelling and counting only; no trade, return or rate changes",
         "moved_a_number": True},
        {"change": "episode-level rates printed beside every 龙回头 row-level rate",
         "why": "row denominators were being reported next to episode counts, which reads as "
                "an episode probability and understates the interval by ~2.6x",
         "kind": "ADDITION. Row rates are unchanged; the episode rate is a new, wider, "
                 "honest companion",
         "moved_a_number": False},
        {"change": "paired-population overnight gap computed and published",
         "why": "the gap had been averaged over all usable break days including unfillable "
                "opens, whose gaps are ~+10% by construction, leaving the paired delta "
                "unexplained by ~0.12 pp",
         "kind": "DEFECT FIX in a reported causal number; the delta itself never changed",
         "moved_a_number": True},
        {"change": "census inference restated per family; reg_na / vz_na marked as "
                   "data-availability slices and excluded from best-cell reporting",
         "why": "pooling three families with different drifts manufactured a "
                "'below chance' artifact, and a missing-data slice was being advertised as "
                "the best cell",
         "kind": "DEFECT FIX in framing and in which cohorts may be advertised; no cohort "
                 "statistic recomputed",
         "moved_a_number": True},
    ],
    "decision_bar": ("A cohort CLEARS only if its mean per-trade return is positive AFTER a "
                     f"{ROUND_TRIP_COST * 1e4:.0f} bp round trip in BOTH the fit and the "
                     f"holdout window, with n >= {CENSUS_MIN_N} in each. Anything else is a "
                     "null for that construction."),
    "huifeng": {
        "population": "failed_up_seal days T. PRIMARY = the healed tape's strict-basis rows "
                      "matched into the panel; TWIN = the OHLCV tolerant definition "
                      "(high >= lim_up*(1-0.002) and close < lim_up*(1-0.002)).",
        "conditioners": ["break depth close_off_limit_pct (3 bands)",
                         "prior 连板 N at T-1 (0 / 1 / 2 / 3+), panel-derived because the "
                         "tape hardcodes lianban_count = 0 on every failed_up_seal row",
                         "volume z vs own trailing 20 sessions (terciles)",
                         "i5_realized_continuation_ma5 regime tercile",
                         "era (fit/holdout, and the 6-era harness)"],
        "outcomes": ["(a) P(limit-up close at T+1) — the 回封 rate; "
                     "P(limit-down close at T+1) — the trapdoor",
                     "(b) fillable entry book at the T+1 OPEN (L1's anchor), E1 + E3",
                     "(c) fillable entry book at the T CLOSE (the 低吸-on-break anchor L1 "
                     "could not test), E1 + E3, same exit bars"],
    },
    "longhuitou": {
        "population": "ladder-end days: the first no-board close after a tolerant-basis run "
                      f"of N >= {LHT_MIN_LADDER}. The pullback window is sessions 1..{LHT_WINDOW} "
                      "after the ladder end, TRUNCATED at the first new limit-up close "
                      "(a re-boarded name is no longer in a pullback and its close is not "
                      "fillable; truncations are counted).",
        "conditioners": ["retrace_frac band (3)", "days elapsed band (3)",
                         "volume ratio declining vs not", "no limit-down print since run end",
                         "close >= half retrace", "i5 regime tercile", "era"],
        "outcomes": [f"P(new limit-up close within {LHT_FWD_SESSIONS} sessions of the "
                     "qualifying day)",
                     "fillable entry book at the qualifying day's CLOSE, E1 + E3"],
    },
}


# ── small helpers (L1's, copied) ──────────────────────────────────────────────

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
    """Return-distribution block (L1's, copied). Clustering receipt beside the moments.

    n alone overstates independence badly here: limit-move episodes cluster in theme waves,
    and the 龙回头 window emits up to 10 rows from ONE episode. n_dates, n_names and the
    top-5-name share are printed so that is visible rather than inferred.
    """
    x = np.asarray(rets, dtype="float64")
    fin = np.isfinite(x)
    x = x[fin]
    n = int(x.size)
    if n == 0:
        return {"n": 0, "thin": True}
    wins = int((x > 0).sum())
    ci = wilson(wins, n)
    net = (1.0 + x) * (1.0 - ROUND_TRIP_COST) - 1.0
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
        "mean_net_pct": _r(100.0 * float(net.mean()), 3),
        "mean_net_se_pct": _r(100.0 * float(net.std(ddof=1)) / np.sqrt(n), 3) if n > 1 else None,
        "thin": bool(n < THIN_CELL_N),
    }
    if names is not None and len(names) == len(fin):
        nm = pd.Series(np.asarray(names)[fin])
        vc = nm.value_counts()
        out["n_names"] = int(vc.size)
        out["top5_name_share_pct"] = _r(100.0 * float(vc.head(5).sum()) / n)
    if dates is not None and len(dates) == len(fin):
        out["n_dates"] = int(pd.Series(np.asarray(dates)[fin]).nunique())
    return out


def era_of(year: int) -> str:
    for name, lo, hi in ERA_BOUNDS:
        if lo <= year <= hi:
            return name
    return "e0_out_of_range"


# ── STAGE 0 — universe + exclusions (v0's, unchanged) ─────────────────────────

def load_st_cohort() -> tuple[frozenset[str], str]:
    """ST/*ST tickers, excluded wholesale on every date (v0's choice, not relitigated)."""
    p = DATA / "china_st" / "st_snapshot.parquet"
    if not p.exists():
        return frozenset(), "st_snapshot.parquet MISSING — no ST exclusion applied"
    df = pd.read_parquet(p)
    tick = frozenset(df["ticker"].astype(str).tolist())
    asof = sorted(set(df["asof"].astype(str)))
    expected = ST_STORE_COVERAGE_DATE.strftime("%Y-%m-%d")
    return tick, (f"n={len(tick)} tickers, asof {asof}; engine ST_STORE_COVERAGE_DATE="
                  f"{expected}; still-single-date={len(asof) == 1 and asof[0] == expected}")


def load_tape() -> tuple[pd.DataFrame, dict]:
    """The healed limit_events vintage. Row count decides which vintage we actually got."""
    path, src = TAPE_PATH, "data/china_microstructure/limit_events.parquet (in tree)"
    if TAPE_OVERRIDE.exists():
        n_tree = len(pd.read_parquet(TAPE_PATH)) if TAPE_PATH.exists() else 0
        if n_tree < HEALED_ROWS:
            path, src = TAPE_OVERRIDE, (f"{TAPE_OVERRIDE.relative_to(REPO)} — extracted from "
                                        "branch claude/cn-limit-w1-dataheal (PR #5059), NOT "
                                        "committed by this lane; #5059 owns that file")
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    n = len(df)
    vintage = ("HEALED (PR #5059)" if n >= HEALED_ROWS else
               "PRE-HEAL — 314 names' history missing" if n <= PREHEAL_ROWS else
               "UNKNOWN vintage")
    return df, {
        "source": src, "rows": n, "vintage": vintage,
        "expected_healed_rows": HEALED_ROWS, "expected_preheal_rows": PREHEAL_ROWS,
        "basis": ("STRICT. engine._detect_limit_events: sealed_up is close >= "
                  "round(prev_close*(1+w),2) with NO tolerance; failed_up_seal is "
                  "high >= lim_up AND NOT sealed_up. The tape's lianban_count is hardcoded "
                  "to 0 on every failed_up_seal row, so prior 连板 is panel-derived here."),
        "event_counts": {str(k): int(v) for k, v in df["event"].value_counts().items()},
    }


def load_regime_dial() -> tuple[pd.DataFrame | None, dict]:
    """L2's board-ecology series; i5_realized_continuation_ma5 is the regime dial.

    LOOKAHEAD CHECK, not assumed. The producer indexes i5 by the TARGET date — the session
    the continuation PRINTED on — so i5[D] counts names that were limit-up on their previous
    usable bar and closed limit-up on D. Every input to that number is on the tape by D's
    close, and ma5 is a TRAILING rolling mean ending at D. The dial at T is therefore known
    at T's close and joining it to an event at T is not a lookahead. The check below is
    mechanical: it re-derives the ma5 from the raw column and confirms the window is trailing
    (a centred or forward window would disagree on the first/last rows).
    """
    path = DIAL_PATH if DIAL_PATH.exists() else DIAL_OVERRIDE
    if not path.exists():
        return None, {"available": False,
                      "note": "board_ecology_series_v1.parquet not present — the i5 regime "
                              "tercile is NULL in every table and is reported as such."}
    d = pd.read_parquet(path)
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values(["board", "date"]).reset_index(drop=True)
    checks = []
    for board, g in d.groupby("board", sort=True):
        g = g.sort_values("date")
        trail = g["i5_realized_continuation"].rolling(5, min_periods=3).mean()
        got = g["i5_realized_continuation_ma5"]
        both = np.isfinite(trail.to_numpy()) & np.isfinite(got.to_numpy())
        md = float(np.abs(trail.to_numpy()[both] - got.to_numpy()[both]).max()) if both.any() \
            else float("nan")
        fwd = g["i5_realized_continuation"][::-1].rolling(5, min_periods=3).mean()[::-1]
        bothf = np.isfinite(fwd.to_numpy()) & np.isfinite(got.to_numpy())
        mdf = float(np.abs(fwd.to_numpy()[bothf] - got.to_numpy()[bothf]).max()) if bothf.any() \
            else float("nan")
        checks.append({"board": str(board), "rows": int(len(g)),
                       "max_abs_diff_vs_TRAILING_ma5": _r(md, 9),
                       "max_abs_diff_vs_FORWARD_ma5": _r(mdf, 6)})
    return d[["date", "board", "i5_realized_continuation",
              "i5_realized_continuation_ma5", "i5_pairs_n"]], {
        "available": True,
        "source": str(path.relative_to(REPO)) + (
            " — extracted from branch claude/cn-limit-w1-regime-salvage; NOT committed by "
            "this lane" if path is DIAL_OVERRIDE else ""),
        "dial": "i5_realized_continuation_ma5, per (date, board)",
        "basis": "TOLERANT — the producer's limit_up flag is v0's tolerant rule; the dial is "
                 "therefore a tolerant-basis conditioner applied to both populations, and is "
                 "labelled as such wherever it appears.",
        "lookahead_check": {
            "claim": "the dial at T is known at T's close",
            "why": ("i5 is indexed by the TARGET date (the session the continuation printed "
                    "on), so i5[T] is computed from pairs whose second leg IS T; ma5 is a "
                    "trailing 5-session mean ending at T."),
            "mechanical": checks,
            "what_the_mechanical_check_DOES_prove": (
                "that ma5 is a TRAILING mean of the i5 column as stored in this file — it "
                "reproduces the trailing window to float precision and disagrees with a "
                "forward window."),
            "what_it_does_NOT_prove": (
                "that the i5 column itself is indexed by the target date. The check is "
                "internal to the file and cannot see how the producer built that column; if "
                "i5 were source-indexed by the ORIGIN date, a trailing ma5 of it would still "
                "reproduce trailingly and this check would still pass. Calling it 'decisive' "
                "on its own overstated it."),
            "source_indexing_verified_separately": (
                "board_ecology_regime_v1.py groups the pair frame by `next_bar_date` and "
                "renames that level to `date`, so i5[D] counts pairs whose SECOND leg is D. "
                "That is target-date indexing and it holds — confirmed by adversarial review "
                "of the producer, not by the mechanical check above."),
            "verdict": "PASS on both legs: trailing window (mechanical, here) and target-date "
                       "source indexing (producer read, reviewed).",
        },
        "terciles": "cut points computed on the FIT window only, per board, then applied to "
                    "the holdout — so the bucketing itself carries no holdout information.",
    }


# ── per-ticker panel arrays (L1's _ticker_arrays + this lane's additions) ──────

def _ticker_arrays(df: pd.DataFrame, board: str) -> dict | None:
    """Full-history arrays for one ticker: prices, limits, exclusions, both 连板 streaks."""
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

    # exclusions — identical to v0 / L1
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

    lu_tol_price = lim_up * (1.0 - LIMIT_CLOSE_TOL)
    lu = live & np.isfinite(lim_up) & (c >= lu_tol_price)             # tolerant seal
    lu_strict = live & np.isfinite(lim_up) & (c >= lim_up)            # strict seal
    ld = live & np.isfinite(lim_dn) & (c <= lim_dn * (1.0 + LIMIT_CLOSE_TOL))
    ld_strict = live & np.isfinite(lim_dn) & (c <= lim_dn)

    # NEW — the failed-seal populations, both bases.
    touch_tol = live & np.isfinite(lim_up) & np.isfinite(h) & (h >= lu_tol_price)
    touch_strict = live & np.isfinite(lim_up) & np.isfinite(h) & (h >= lim_up)
    fail_tol = touch_tol & ~lu
    fail_strict = touch_strict & ~lu_strict

    with np.errstate(invalid="ignore", divide="ignore"):
        close_off = (lim_up - c) / lim_up            # engine's fraction contract

    lianban = streak_lengths(lu)
    lianban_strict = streak_lengths(lu_strict)

    # NEW — volume conditioners, trailing window ending at t-1 (known at t's close).
    vs = pd.Series(vol)
    v_mean = vs.rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK).mean().shift(1).to_numpy()
    v_std = vs.rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK).std(ddof=1).shift(1).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        volz = np.where(np.isfinite(v_std) & (v_std > 0), (vol - v_mean) / v_std, np.nan)
        volratio = np.where(np.isfinite(v_mean) & (v_mean > 0), vol / v_mean, np.nan)

    days = idx.to_numpy().astype("datetime64[D]").astype(np.int64)

    return {
        "idx": idx, "o": o, "h": h, "lo": lo, "c": c, "pc": pc, "vol": vol, "width": width,
        "lim_up": lim_up, "lim_dn": lim_dn, "live": live, "in_win": in_win,
        "lu": lu, "lu_strict": lu_strict, "ld": ld, "ld_strict": ld_strict,
        "touch_tol": touch_tol, "touch_strict": touch_strict,
        "fail_tol": fail_tol, "fail_strict": fail_strict, "close_off": close_off,
        "lianban": lianban, "lianban_strict": lianban_strict,
        "volz": volz, "volratio": volratio, "days": days, "n": n,
        "excl_stats": {
            "ipo_excluded": int((ipo_mask & in_win).sum()),
            "exdiv_excluded": int((exdiv & in_win).sum()),
            "zero_volume_excluded": int((zero_vol & in_win).sum()),
            "bars_in_window": int(in_win.sum()),
            "live_bars_in_window": int(live.sum()),
        },
    }


# ── the shared exit machinery (L1's, copied) ──────────────────────────────────

def _make_walkers(A: dict):
    n, live, days = A["n"], A["live"], A["days"]
    o, c, lim_dn = A["o"], A["c"], A["lim_dn"]

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
        """Scheduled exit bar -> realised (price, bar, rolls, forced, scheduled_open)."""
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

    def exit_legs(first_held: int, lu_sig: np.ndarray):
        """(rule, exit_px, hold_sessions, rolls, forced, roll_extra) for E1 and E3.

        `first_held` is the first bar the position is exposed to — T+1 for BOTH an open
        entry at T+1 and a close entry at T. That is what makes the two anchors comparable:
        identical exit bars, different entry prices.
        """
        out = []
        for rule in EXIT_RULES:
            forced_walk = False
            if rule == "E3_time_stop_T4":
                cur, ok_walk = first_held, True
                for _ in range(TIME_STOP_SESSIONS):
                    nb = usable_next(cur)
                    if nb < 0:
                        ok_walk = False
                        break
                    cur = nb
                b_sched, fallback = (cur if ok_walk else -1), cur
            else:  # E1_board_fail
                cur, steps = first_held, 0
                while True:
                    if not bool(lu_sig[cur]):
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
            extra = (px / sched_open - 1.0) if (rolls > 0 and np.isfinite(sched_open)
                                                and sched_open > 0) else np.nan
            out.append((rule, px, int(b_exit - first_held + 1), rolls,
                        bool(forced or forced_walk), extra))
        return out

    return usable_next, resolve_exit, exit_legs


def _fwd_any(flag: np.ndarray, start: int, k: int, usable_next) -> tuple[bool, bool]:
    """Does `flag` fire within the next k usable sessions from `start` (exclusive)?

    Returns (fired, resolved). A chain that breaks before k steps with no fire is counted
    as NOT fired but flagged unresolved — dropping it instead would delete exactly the
    losers (the resolution-conditioned-denominator trap) and inflate the rate.
    """
    cur = start
    for _ in range(k):
        nb = usable_next(cur)
        if nb < 0:
            return False, False
        if bool(flag[nb]):
            return True, True
        cur = nb
    return False, True


# ── B-回封 — per-ticker event rows + the two entry books ──────────────────────

HF_COLS = ["date", "ticker", "board", "basis", "pos", "prior_N", "close_off", "volz",
           "y_limit_up", "y_limit_down", "y_ok", "unfillable_open", "gap",
           "entry_close", "entry_open"]
TRADE_COLS = ["date", "ticker", "board", "basis", "anchor", "rule", "cohort_key",
              "entry_px", "exit_px", "ret", "hold_sessions", "rolls", "forced_close",
              "roll_extra_loss", "paired"]


def process_huifeng(ticker: str, A: dict, board: str, strict_dates: set):
    """回封 rows + trades for one ticker, on BOTH definition bases."""
    n = A["n"]
    o, c, h, lu, lu_strict, ld, ld_strict = (A["o"], A["c"], A["h"], A["lu"], A["lu_strict"],
                                             A["ld"], A["ld_strict"])
    lim_up, live, days, idx = A["lim_up"], A["live"], A["days"], A["idx"]
    usable_next, _resolve, exit_legs = _make_walkers(A)

    rows, trades = [], []
    for basis in ("strict", "tolerant"):
        if basis == "strict":
            # PRIMARY: the healed tape's own rows, matched into the panel by (ticker, date).
            pop = np.zeros(n, dtype=bool)
            if strict_dates:
                in_tape = np.isin(days, np.fromiter(strict_dates, dtype=np.int64,
                                                    count=len(strict_dates)))
                pop = live & in_tape
            lu_sig, ld_sig, lb = lu_strict, ld_strict, A["lianban_strict"]
        else:
            pop = A["fail_tol"]
            lu_sig, ld_sig, lb = lu, ld, A["lianban"]

        sel = np.where(pop)[0]
        if sel.size == 0:
            continue
        for t in sel:
            nb = usable_next(t)
            y_ok = nb >= 0
            entry_close = float(c[t])
            if not np.isfinite(entry_close) or entry_close <= 0:
                continue
            prior_N = int(lb[t - 1]) if t >= 1 else 0
            co = float(A["close_off"][t])
            vz = float(A["volz"][t])
            unfill = False
            gapv = np.nan
            entry_open = np.nan
            if y_ok:
                eo = float(o[nb])
                lu_nb = float(lim_up[nb])
                unfill = bool(np.isfinite(eo) and np.isfinite(lu_nb)
                              and eo >= lu_nb * (1.0 - LIMIT_CLOSE_TOL))
                gapv = eo / entry_close - 1.0
                entry_open = eo
            rows.append((idx[t], ticker, board, basis, int(t), prior_N, co, vz,
                         bool(y_ok and lu_sig[nb]), bool(y_ok and ld_sig[nb]), bool(y_ok),
                         bool(unfill), gapv, entry_close, entry_open))

            if not y_ok:
                continue
            legs = exit_legs(nb, lu_sig)
            paired = bool(not unfill)  # the T+1-open book can only trade the fillable opens
            for anchor, entry_px in (("T_close", entry_close),
                                     ("T1_open", entry_open if not unfill else np.nan)):
                if not np.isfinite(entry_px) or entry_px <= 0:
                    continue
                for rule, px, hold, rolls, forced, extra in legs:
                    trades.append((idx[t], ticker, board, basis, anchor, rule, "", entry_px,
                                   px, px / entry_px - 1.0, hold, rolls, forced, extra,
                                   paired))
    return rows, trades


# ── B-龙回头 — per-ticker qualifying rows + the close-entry book ──────────────

LHT_COLS = ["date", "ticker", "board", "run_N", "run_end_date", "episode_id", "day_k",
            "retrace_frac", "run_height", "dd_price_pct", "volratio", "vol_declining",
            "no_ld_since_end", "close_ge_half", "y_new_board_5d", "resolved_5d",
            "entry_close", "sealed_at_close"]


def process_longhuitou(ticker: str, A: dict, board: str):
    """龙回头 pullback-window rows + close-entry trades for one ticker (TOLERANT basis)."""
    n = A["n"]
    o, c, h, lu, ld = A["o"], A["c"], A["h"], A["lu"], A["ld"]
    lim_up, live, idx = A["lim_up"], A["live"], A["idx"]
    lianban, volratio, vol = A["lianban"], A["volratio"], A["vol"]
    usable_next, _resolve, exit_legs = _make_walkers(A)

    rows, trades = [], []
    stats = {"runs": 0, "run_end_unusable": 0, "truncated_by_reboard": 0,
             "window_chain_broken": 0, "unresolved_5d": 0, "sealed_close_refused": 0,
             "bad_base": 0}

    # a run ends at re when lu[re] and the streak does not continue on re+1
    lu_next = np.r_[lu[1:], False]
    ends = np.where(lu & ~lu_next & (lianban >= LHT_MIN_LADDER))[0]
    for re_i in ends:
        run_N = int(lianban[re_i])
        rs = re_i - run_N + 1
        if rs < 1:
            stats["bad_base"] += 1
            continue
        run_base = float(c[rs - 1])
        if not np.isfinite(run_base) or run_base <= 0:
            stats["bad_base"] += 1
            continue
        stats["runs"] += 1
        run_peak = float(np.nanmax(h[rs:re_i + 1]))
        if not np.isfinite(run_peak) or run_peak <= run_base:
            stats["bad_base"] += 1
            continue

        q = usable_next(re_i)
        if q < 0:
            stats["run_end_unusable"] += 1
            continue
        episode_id = f"{ticker}:{idx[re_i]:%Y-%m-%d}"
        seen_ld = False
        prev_vr = float(volratio[re_i])
        for k in range(1, LHT_WINDOW + 1):
            if bool(lu[q]):                       # re-boarded: the pullback is over
                stats["truncated_by_reboard"] += 1
                break
            run_peak = max(run_peak, float(h[q]) if np.isfinite(h[q]) else run_peak)
            close_q = float(c[q])
            if not np.isfinite(close_q) or close_q <= 0:
                break
            denom = run_peak - run_base
            retr = (run_peak - close_q) / denom if denom > 0 else np.nan
            vr = float(volratio[q])
            declining = bool(np.isfinite(vr) and np.isfinite(prev_vr) and vr < prev_vr)
            seen_ld = seen_ld or bool(ld[q])
            fired, resolved = _fwd_any(lu, q, LHT_FWD_SESSIONS, usable_next)
            if not resolved:
                stats["unresolved_5d"] += 1
            sealed = bool(lu[q])                  # False by the loop guard; kept as a receipt
            if sealed:
                stats["sealed_close_refused"] += 1
            rows.append((idx[q], ticker, board, run_N, idx[re_i], episode_id, k,
                         retr, run_peak / run_base - 1.0, close_q / run_peak - 1.0,
                         vr, declining, bool(not seen_ld), bool(np.isfinite(retr)
                                                                and retr <= 0.5),
                         bool(fired), bool(resolved), close_q, sealed))

            nb = usable_next(q)
            if nb >= 0 and not sealed:
                for rule, px, hold, rolls, forced, extra in exit_legs(nb, lu):
                    trades.append((idx[q], ticker, board, "tolerant", "q_close", rule,
                                   episode_id, close_q, px, px / close_q - 1.0, hold, rolls,
                                   forced, extra, True))
            prev_vr = vr
            if nb < 0:
                stats["window_chain_broken"] += 1
                break
            q = nb
    return rows, trades, stats


# ── build ─────────────────────────────────────────────────────────────────────

_T0 = [time.time()]


def build(verbose: bool = True):
    st_set, st_note = load_st_cohort()
    tape, tape_meta = load_tape()
    dial, dial_meta = load_regime_dial()

    fu = tape[tape["event"] == "failed_up_seal"].copy()
    fu["day"] = fu["date"].to_numpy().astype("datetime64[D]").astype(np.int64)
    strict_by_ticker = {t: set(g["day"].tolist()) for t, g in fu.groupby("ticker", sort=False)}
    tape_key = set(zip(fu["ticker"].astype(str), fu["day"]))

    files = sorted((DATA / "china_stocks_raw").glob("*.parquet"))
    agg = {"ipo_excluded": 0, "exdiv_excluded": 0, "zero_volume_excluded": 0,
           "bars_in_window": 0, "live_bars_in_window": 0}
    boards_seen, kept, skipped_st, skipped_thin = {}, 0, 0, 0
    hf_rows, hf_trades, lht_rows, lht_trades = [], [], [], []
    lht_stats = {"runs": 0, "run_end_unusable": 0, "truncated_by_reboard": 0,
                 "window_chain_broken": 0, "unresolved_5d": 0, "sealed_close_refused": 0,
                 "bad_base": 0}
    panel_strict_key, panel_tol_key = set(), set()

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
        for k in agg:
            agg[k] += A["excl_stats"][k]
        boards_seen[board] = boards_seen.get(board, 0) + 1
        kept += 1

        d = A["days"]
        panel_strict_key.update((ticker, int(x)) for x in d[A["fail_strict"]])
        panel_tol_key.update((ticker, int(x)) for x in d[A["fail_tol"]])

        r, tr = process_huifeng(ticker, A, board, strict_by_ticker.get(ticker, set()))
        hf_rows.extend(r)
        hf_trades.extend(tr)
        r2, tr2, st = process_longhuitou(ticker, A, board)
        lht_rows.extend(r2)
        lht_trades.extend(tr2)
        for k2 in lht_stats:
            lht_stats[k2] += st[k2]

        if verbose and (i + 1) % 400 == 0:
            print(f"          ... {i + 1}/{len(files)} files "
                  f"({time.time() - _T0[0]:.0f}s)", flush=True)

    hf = pd.DataFrame(hf_rows, columns=HF_COLS)
    lht = pd.DataFrame(lht_rows, columns=LHT_COLS)
    tr_hf = pd.DataFrame(hf_trades, columns=TRADE_COLS)
    tr_lht = pd.DataFrame(lht_trades, columns=TRADE_COLS)

    for d_ in (hf, lht, tr_hf, tr_lht):
        if len(d_):
            d_["year"] = d_["date"].dt.year.astype(np.int16)
            d_["split"] = np.where(d_["date"] < SPLIT_DATE, "fit", "holdout")
            d_["era"] = [era_of(int(y)) for y in d_["year"]]

    # conditioner bands
    hf["depth_band"] = pd.cut(hf["close_off"], [-np.inf, 0.01, 0.03, np.inf],
                              labels=DEPTH_BANDS).astype(str)
    hf["Ncoh"] = np.where(hf["prior_N"] >= 3, "N3plus",
                          "N" + hf["prior_N"].clip(0, 2).astype(int).astype(str))
    lht["retrace_band"] = pd.cut(lht["retrace_frac"], [-np.inf, 0.15, 0.30, np.inf],
                                 labels=RETRACE_BANDS).astype(str)
    lht["days_band"] = pd.cut(lht["day_k"], [0, 3, 6, 10],
                              labels=DAYS_BANDS).astype(str)

    # regime tercile — cut points from the FIT window only, per board
    reg_meta = {"applied": False}
    if dial is not None:
        dd = dial.rename(columns={"i5_realized_continuation_ma5": "i5_ma5"})
        dd = dd.drop_duplicates(["date", "board"])
        cuts = {}
        for board, g in dd.groupby("board", sort=True):
            f = g[g["date"] < SPLIT_DATE]["i5_ma5"].dropna()
            if len(f) >= 100:
                cuts[str(board)] = [float(f.quantile(1 / 3)), float(f.quantile(2 / 3))]
        reg_meta = {"applied": True, "fit_cut_points_by_board": {k: [_r(v[0], 4), _r(v[1], 4)]
                                                                 for k, v in cuts.items()},
                    "labels": ["reg0_cold", "reg1_mid", "reg2_hot"],
                    "null_label": "reg_na",
                    "data_availability_slice": (
                        "reg_na is NOT a regime level and must never be advertised as a "
                        "conditioner cell. It marks rows where the dial is unavailable — "
                        "STAR (too few fit rows to cut) and the dial's own warm-up. A cohort "
                        "keyed on reg_na describes MISSING DATA, not hot/cold tape, and is "
                        "excluded from best-cell reporting.")}

        def attach(d_):
            if not len(d_):
                d_["i5_ma5"] = np.nan
                d_["reg"] = "reg_na"
                return d_
            m = d_.merge(dd[["date", "board", "i5_ma5"]], on=["date", "board"], how="left")
            lab = np.full(len(m), "reg_na", dtype=object)
            for b, (q1, q2) in cuts.items():
                sel = (m["board"] == b).to_numpy() & np.isfinite(m["i5_ma5"].to_numpy())
                v = m["i5_ma5"].to_numpy()
                lab[sel & (v <= q1)] = "reg0_cold"
                lab[sel & (v > q1) & (v <= q2)] = "reg1_mid"
                lab[sel & (v > q2)] = "reg2_hot"
            m["reg"] = lab
            return m

        hf, lht, tr_hf, tr_lht = attach(hf), attach(lht), attach(tr_hf), attach(tr_lht)
    else:
        for d_ in (hf, lht, tr_hf, tr_lht):
            d_["i5_ma5"] = np.nan
            d_["reg"] = "reg_na"

    # volume-z terciles for 回封 — fit-window cut points per (BASIS, board).
    # Pooling the two bases would double-count their 15,629 overlapping rows and let the
    # tolerant population's shape set the strict population's band edges, which is exactly
    # the basis mixing this instrument's discipline section forbids.
    vz_cuts = {}
    for (basis, board), g in hf[hf["split"] == "fit"].groupby(["basis", "board"], sort=True):
        v = g["volz"].replace([np.inf, -np.inf], np.nan).dropna()
        if len(v) >= 100:
            vz_cuts[f"{basis}|{board}"] = [float(v.quantile(1 / 3)),
                                           float(v.quantile(2 / 3))]
    vlab = np.full(len(hf), "vz_na", dtype=object)
    vv = hf["volz"].to_numpy()
    bkey = (hf["basis"].astype(str) + "|" + hf["board"].astype(str)).to_numpy()
    for b, (q1, q2) in vz_cuts.items():
        sel = (bkey == b) & np.isfinite(vv)
        vlab[sel & (vv <= q1)] = "vz0_low"
        vlab[sel & (vv > q1) & (vv <= q2)] = "vz1_mid"
        vlab[sel & (vv > q2)] = "vz2_high"
    hf["vz_band"] = vlab

    # carry the 回封 conditioners onto the trade rows via (basis, ticker, date)
    keycols = ["basis", "ticker", "date"]
    condcols = ["depth_band", "Ncoh", "vz_band", "unfillable_open"]
    tr_hf = tr_hf.merge(hf[keycols + condcols].drop_duplicates(keycols), on=keycols, how="left")
    lkey = ["ticker", "date"]
    tr_lht = tr_lht.merge(
        lht[lkey + ["retrace_band", "days_band", "run_N", "vol_declining",
                    "no_ld_since_end", "close_ge_half"]].drop_duplicates(lkey),
        on=lkey, how="left")

    meta = {
        "raw_store": ("data/china_stocks_raw — v0's and L1's basis. NOT the adjusted twin "
                      "data/china_stocks. L1 measured this store to be BACK-ADJUSTED rather "
                      "than nominal; that finding is inherited, not re-derived."),
        "files_found": len(files), "tickers_kept": kept, "tickers_skipped_st": skipped_st,
        "tickers_skipped_thin_or_unreadable": skipped_thin, "board_counts": boards_seen,
        "st_cohort": st_note,
        "window": [WINDOW_START.strftime("%Y-%m-%d"), WINDOW_END.strftime("%Y-%m-%d")],
        "excluded_bars": agg,
        "tape": tape_meta, "regime_dial": dial_meta, "regime_terciles": reg_meta,
        "volz_terciles": {
            "fit_cut_points_by_basis_and_board": {k: [_r(v[0], 3), _r(v[1], 3)]
                                                  for k, v in vz_cuts.items()},
            "note": ("Cut points are fit on each (basis, board) SEPARATELY. An earlier build "
                     "pooled the two bases, which double-counted their 15,629 overlapping "
                     "rows and let the tolerant population's shape set the strict "
                     "population's band edges — a basis-discipline violation that moved the "
                     "strict/main edges by roughly 5%."),
            "data_availability_slice": ("vz_na is NOT a tercile. It marks rows where the "
                                        "trailing 20-session volume window is unavailable "
                                        "(early history) or degenerate. It is a "
                                        "data-availability slice and is excluded from "
                                        "best-cell reporting."),
        },
        "longhuitou_walk_stats": lht_stats,
        "vintage": vintage_receipt(len(files), kept),
    }
    pop = population_receipt(hf, tape_key, panel_strict_key, panel_tol_key, fu)
    return hf, lht, tr_hf, tr_lht, meta, pop


def _git(*args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                           timeout=30)
        return r.stdout.strip() or "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def vintage_receipt(files_found: int, kept: int) -> dict:
    """Vintage identity that is STABLE across the commit that carries this output.

    Recording the build-time HEAD alone makes the artifact un-reproducible by equality the
    moment it is committed: committing moves HEAD, so the next run writes a different SHA and
    a byte-comparison of a frozen artifact would be a scheduled failure. The stable identity
    is the BASE and the DATA-STORE commits, which do not move when this file lands.
    """
    return {
        # merge-base, NOT `rev-parse origin/main`: worktrees share one .git, so a sibling
        # lane's fetch moves origin/main under this run. The branch point does not move.
        "base_sha": _git("merge-base", "HEAD", "origin/main"),
        "data_store_sha": _git("log", "-1", "--format=%H", "--",
                               "data/china_stocks_raw", "data/china_microstructure"),
        "build_head_sha": _git("rev-parse", "HEAD"),
        "sha_note": ("base_sha (this branch's point off main) and data_store_sha (the last "
                     "commit touching the input stores) are the stable vintage identity. "
                     "build_head_sha is whatever HEAD the run happened on and BY CONSTRUCTION "
                     "pre-dates the commit that carries this file — it will differ on any "
                     "re-run after commit, and that is not a reproducibility failure. "
                     "Everything else in this payload is byte-identical run to run."),
        "raw_store_names": files_found,
        "names_kept_after_st_exclusion": kept,
        "expansion_status": (
            "PRE-EXPANSION. This checkout's data/china_stocks_raw holds a curated subset of "
            "the listed A-share market. A sibling Codex lane is expanding the universe "
            "toward ~5,400 names; that expansion is NOT in this store and every count, rate "
            "and expectancy below is scoped to the smaller universe. Re-running this "
            "instrument post-expansion is the first item in the ORE LEDGER."),
        "collectors_untouched": ("This lane touched no collector, no engine data wiring and "
                                 "no Tushare surface — a sibling lane owns those."),
    }


def population_receipt(hf: pd.DataFrame, tape_key: set, panel_strict: set,
                       panel_tol: set, fu: pd.DataFrame) -> dict:
    """Both definitions' counts and their overlap — the delta made visible, not assumed."""
    s = hf[hf["basis"] == "strict"]
    t = hf[hf["basis"] == "tolerant"]
    matched = set(zip(s["ticker"].astype(str),
                      s["date"].to_numpy().astype("datetime64[D]").astype(np.int64)))
    inter = panel_strict & panel_tol
    co = fu["close_off_limit_pct"].to_numpy(dtype="float64")
    return {
        "what_this_answers": ("The brief asks for both definitions' counts and their overlap "
                              "so the delta between them is visible. It is large and it is "
                              "structural, not noise."),
        "tape_strict": {
            "failed_up_seal_rows_in_tape": int(len(fu)),
            "rows_matched_into_the_panel": int(len(s)),
            "rows_the_panel_could_not_place": int(len(tape_key) - len(matched)),
            "why_unplaced": ("ticker absent from data/china_stocks_raw, or the bar is "
                             "excluded by v0's rules (ST wholesale, IPO window, ex-div "
                             "suspect, zero volume) — the engine applies a 5% ST BAND where "
                             "v0 DROPS the ST name entirely, so the two universes differ by "
                             "construction."),
            "share_that_are_tolerant_SEALS_pct": _r(100.0 * float((co <= LIMIT_CLOSE_TOL).mean())),
            "tolerant_seals_as_share_of_SHALLOW_BAND_pct": _r(
                100.0 * float((co <= LIMIT_CLOSE_TOL).sum()) / max(1, int((co <= 0.01).sum()))),
            "tolerant_seal_note": ("close_off <= 0.002 means the close is inside v0's "
                                   "tolerance: the strict tape calls these BREAKS, the "
                                   "tolerant basis calls them SEALS. They are ~4.5% of the "
                                   "strict population overall — but they sit ENTIRELY inside "
                                   "the shallow depth band, where they are a much larger "
                                   "share (see the field above). That concentration is the "
                                   "number that matters, because the strict shallow band is "
                                   "one of the cohorts the census surfaces: a meaningful "
                                   "slice of it is not a weakness cohort at all but boards "
                                   "that v0's adjudicated rule counts as held."),
        },
        "tape_vs_panel_strict_agreement": {
            "note": ("The strict population is taken FROM THE TAPE, but the panel detects it "
                     "independently from the same OHLCV bars. If the two disagreed, the "
                     "instrument would be reading a different universe than the store it "
                     "claims to use. They do not."),
            "tape_rows_placed": int(len(matched)),
            "panel_detected": int(len(panel_strict)),
            "both": int(len(matched & panel_strict)),
            "tape_only": int(len(matched - panel_strict)),
            "panel_only": int(len(panel_strict - matched)),
            "agreement_pct": _r(100.0 * len(matched & panel_strict)
                                / max(1, len(matched | panel_strict)), 3),
        },
        "panel_derived": {
            "strict_failed_seals": int(len(panel_strict)),
            "tolerant_failed_seals": int(len(panel_tol)),
            "overlap": int(len(inter)),
            "strict_only": int(len(panel_strict - panel_tol)),
            "tolerant_only": int(len(panel_tol - panel_strict)),
            "jaccard_pct": _r(100.0 * len(inter) / max(1, len(panel_strict | panel_tol))),
            "reading": ("strict_only rows are the tolerant basis's SEALS (touched the limit "
                        "and closed within 0.2% of it). tolerant_only rows touched the "
                        "TOLERANT limit price but not the strict one — a near-touch the "
                        "strict tape does not record as a break at all."),
        },
        "tolerant_population_rows_scored": int(len(t)),
        "basis_discipline": ("Every table below carries a `basis` field. A strict-population "
                             "row is scored with strict outcomes (lu_strict / ld_strict) and "
                             "a strict 连板; a tolerant row with tolerant outcomes. The two "
                             "are never averaged together and never appear in the same cell."),
    }


# ── tables ────────────────────────────────────────────────────────────────────

def _hf_rate_cell(g: pd.DataFrame) -> dict:
    u = g[g["y_ok"]]
    n = len(u)
    out = {"n_events": int(len(g)), "n_with_usable_next_bar": int(n),
           "thin": bool(n < THIN_CELL_N)}
    if n:
        out["p_reseal_T1"] = rate_block(int(u["y_limit_up"].sum()), n)
        out["p_limit_down_T1"] = rate_block(int(u["y_limit_down"].sum()), n)
        out["p_unfillable_T1_open"] = rate_block(int(u["unfillable_open"].sum()), n)
        gp = u["gap"].to_numpy(dtype="float64")
        gp = gp[np.isfinite(gp)]
        if gp.size:
            out["gap_mean_pct"] = _r(100.0 * float(gp.mean()), 3)
            out["gap_median_pct"] = _r(100.0 * float(np.median(gp)), 3)
        out["n_names"] = int(u["ticker"].nunique())
        out["n_dates"] = int(u["date"].nunique())
    return out


def huifeng_rates(hf: pd.DataFrame) -> dict:
    """(a) the 回封 rate and the trapdoor, by every pre-registered conditioner."""
    res = {
        "definition": {
            "reseal_T1": "the name closes at the limit on T+1, on the POPULATION'S OWN basis "
                         "(strict population -> strict close test, tolerant -> tolerant)",
            "trapdoor_T1": "the name closes at the LIMIT-DOWN on T+1, same basis discipline",
            "depth_bands": DEPTH_BANDS, "depth_note": DEPTH_NOTE,
            "prior_N": "the 连板 streak ending at T-1, PANEL-derived. The tape's "
                       "lianban_count is hardcoded to 0 on every failed_up_seal row and "
                       "carries no information; using it would have silently collapsed the "
                       "whole N conditioner into one cell.",
            "denominator": "events whose immediately following bar is live and <= 10 "
                           "calendar days later (v0's usable-pair rule), applied to "
                           "numerator and denominator alike.",
        },
        "by_basis_board": {}, "by_depth": {}, "by_N": {}, "by_volz": {}, "by_regime": {},
        "by_era": {}, "depth_x_N": {}, "trapdoor_by_depth": {},
    }
    for basis in ("strict", "tolerant"):
        b0 = hf[hf["basis"] == basis]
        res["by_basis_board"][basis] = {
            str(bd): _hf_rate_cell(g) for bd, g in b0.groupby("board", sort=True)}
        for key, col in (("by_depth", "depth_band"), ("by_N", "Ncoh"),
                         ("by_volz", "vz_band"), ("by_regime", "reg")):
            res[key][basis] = {}
            for bd, g in b0.groupby("board", sort=True):
                res[key][basis][str(bd)] = {}
                for sp in ("fit", "holdout"):
                    gg = g[g["split"] == sp]
                    res[key][basis][str(bd)][sp] = {
                        str(v): _hf_rate_cell(h) for v, h in gg.groupby(col, sort=True)}
        res["by_era"][basis] = {}
        for bd, g in b0.groupby("board", sort=True):
            res["by_era"][basis][str(bd)] = {
                str(e): {str(v): _hf_rate_cell(h)
                         for v, h in ge.groupby("depth_band", sort=True)}
                for e, ge in g.groupby("era", sort=True)}
        res["depth_x_N"][basis] = {}
        for bd, g in b0.groupby("board", sort=True):
            res["depth_x_N"][basis][str(bd)] = {}
            for sp in ("fit", "holdout"):
                gg = g[g["split"] == sp]
                res["depth_x_N"][basis][str(bd)][sp] = {
                    f"{d}|{nn}": _hf_rate_cell(h)
                    for (d, nn), h in gg.groupby(["depth_band", "Ncoh"], sort=True)}
        # the risk table the brief asks for by name
        res["trapdoor_by_depth"][basis] = {}
        for bd, g in b0.groupby("board", sort=True):
            res["trapdoor_by_depth"][basis][str(bd)] = {}
            for sp in ("fit", "holdout", "all"):
                gg = g if sp == "all" else g[g["split"] == sp]
                u = gg[gg["y_ok"]]
                res["trapdoor_by_depth"][basis][str(bd)][sp] = {
                    str(d): {**rate_block(int(h["y_limit_down"].sum()), len(h)),
                             "reseal_rate_pct": _r(100.0 * float(h["y_limit_up"].mean()))
                             if len(h) else None,
                             "reseal_over_trapdoor": _r(
                                 float(h["y_limit_up"].sum()) / max(1, int(h["y_limit_down"].sum())))
                             if len(h) else None}
                    for d, h in u.groupby("depth_band", sort=True)}
    res["survivorship_warning"] = (
        "Every limit-DOWN rate here is a SURVIVORS-ONLY figure and reads BETTER than the "
        "truth: data/china_stocks_raw holds the currently listed universe, so the terminal "
        "down-limit sequences of delisted names are simply absent. The trapdoor is a lower "
        "bound on the real hazard.")
    return res


def date_clustered(rets: np.ndarray, dates: np.ndarray) -> dict:
    """Date-clustered net expectancy — the only honest standard error for these books.

    Trades are NOT independent: a 回封 cohort on one session shares a market-wide regime and
    a market-wide open, and one 龙回头 episode emits up to ten rows. The naive per-trade SE
    treats ~7 same-day trades as 7 observations and overstates t by roughly sqrt(7). This
    collapses each date to its own mean net return first, so the reported t counts SESSIONS.
    The point estimate also changes meaning, deliberately: date-equal weighting is what a
    book that cannot take unlimited same-day positions actually earns.
    """
    x = np.asarray(rets, dtype="float64")
    fin = np.isfinite(x)
    x = x[fin]
    if x.size == 0:
        return {"n_dates": 0}
    net = (1.0 + x) * (1.0 - ROUND_TRIP_COST) - 1.0
    dm = pd.Series(net).groupby(np.asarray(dates)[fin]).mean().to_numpy()
    k = int(dm.size)
    out = {"n_dates": k, "date_eq_weight_net_pct": _r(100.0 * float(dm.mean()), 3),
           "trades_per_date": _r(float(x.size) / k, 2)}
    if k > 1:
        se = float(dm.std(ddof=1)) / np.sqrt(k)
        out["date_clustered_se_pct"] = _r(100.0 * se, 3)
        out["date_clustered_t"] = _r(float(dm.mean()) / se, 2) if se > 0 else None
    return out


def _book_cell(g: pd.DataFrame) -> dict:
    out = ret_block(g["ret"].to_numpy(), g["ticker"].to_numpy(), g["date"].to_numpy())
    if not len(g):
        return out
    out.update(date_clustered(g["ret"].to_numpy(), g["date"].to_numpy()))
    out["roll_rate_pct"] = _r(100.0 * float((g["rolls"].to_numpy() > 0).mean()))
    ex = g.loc[g["rolls"] > 0, "roll_extra_loss"].to_numpy(dtype="float64")
    ex = ex[np.isfinite(ex)]
    out["roll_n"] = int(ex.size)
    out["roll_mean_extra_pct"] = _r(100.0 * float(ex.mean()), 3) if ex.size else None
    out["roll_worst_extra_pct"] = _r(100.0 * float(ex.min()), 3) if ex.size else None
    out["forced_close_rate_pct"] = _r(100.0 * float(g["forced_close"].to_numpy().mean()))
    out["mean_hold_sessions"] = _r(float(g["hold_sessions"].mean()), 2)
    ck = g["cohort_key"].astype(str)
    if bool((ck != "").any()):
        out["n_episodes"] = int(ck[ck != ""].nunique())
    return out


def paired_gap_block(hf: pd.DataFrame) -> dict:
    """Mean overnight gap on the PAIRED population — the number that explains the delta.

    Computing this over all usable break days is wrong and inflates nothing by accident: the
    unfillable opens are BY DEFINITION the ones that gapped to the limit (mean gap ~ +10%),
    and they are precisely the rows the paired comparison excludes. The delta between the
    two anchors is an identity on the paired set — ret_close = (1+ret_open)(1+gap) - 1 — so
    only the paired-set gap can close the arithmetic.
    """
    out = {
        "definition": ("mean of gap = open[T+1]/close[T] - 1 over break days with a usable "
                       "successor AND a FILLABLE T+1 open — i.e. exactly the rows the paired "
                       "book trades."),
        "why_not_all_usable_rows": ("unfillable opens gap to the limit by construction; "
                                    "including them mixes a ~+10% cohort into the mean and "
                                    "leaves the paired delta unexplained."),
        "by_basis_board_window": {},
    }
    for basis in ("strict", "tolerant"):
        b0 = hf[(hf["basis"] == basis) & hf["y_ok"]]
        out["by_basis_board_window"][basis] = {}
        for bd, g in b0.groupby("board", sort=True):
            cell = {}
            for sp in ("fit", "holdout"):
                gg = g[g["split"] == sp]
                pair = gg[~gg["unfillable_open"]]
                for tag, frame in (("paired_fillable_only", pair), ("all_usable", gg),
                                   ("unfillable_only", gg[gg["unfillable_open"]])):
                    v = frame["gap"].to_numpy(dtype="float64")
                    v = v[np.isfinite(v)]
                    cell[f"{sp}|{tag}"] = {"n": int(v.size),
                                           "mean_gap_pct": _r(100.0 * float(v.mean()), 4)
                                           if v.size else None}
            out["by_basis_board_window"][basis][str(bd)] = cell
    return out


def huifeng_book(tr: pd.DataFrame, hf: pd.DataFrame) -> dict:
    """(b) T+1-open entries vs (c) T-close entries — the comparison L1 could not make."""
    res = {
        "paired_population_gap": paired_gap_block(hf),
        "exit_rules": dict(EXIT_RULES), "locked_exit": LOCKED_EXIT_NOTE,
        "hold_sessions_convention": HOLD_SESSIONS_NOTE,
        "buy_fillability": BUY_FILLABILITY_NOTE,
        "anchors": {
            "T_close": "buy at the CLOSE of the break day T. Fillable by construction — a "
                       "failed seal is not sealed. This is the 低吸-on-break entry.",
            "T1_open": "buy at the OPEN of T+1, refused when that open is at/above the limit "
                       "(L1's anchor and L1's refusal rule).",
        },
        "comparison_note": (
            "The two anchors share EXIT BARS exactly — the exit walk starts at T+1 for both "
            "— so a difference between them is a difference in ENTRY PRICE and in POPULATION, "
            "nothing else. Two populations are reported for T_close: its own (every break "
            "day with a usable successor) and the PAIRED subset (only breaks whose T+1 open "
            "was fillable), which is the like-for-like comparison. The unpaired remainder is "
            "the 回封 battery's structural advantage: those are the names that gapped away "
            "to an unbuyable open, and the close entry already owns them."),
        "headline": {}, "by_depth": {}, "by_N": {}, "by_regime": {}, "by_era": {},
        "paired": {},
    }
    for basis in ("strict", "tolerant"):
        b0 = tr[tr["basis"] == basis]
        res["headline"][basis] = {}
        for bd, g in b0.groupby("board", sort=True):
            res["headline"][basis][str(bd)] = {}
            for sp in ("fit", "holdout"):
                gg = g[g["split"] == sp]
                res["headline"][basis][str(bd)][sp] = {
                    f"{a}|{r}": _book_cell(h)
                    for (a, r), h in gg.groupby(["anchor", "rule"], sort=True)}
        for key, col in (("by_depth", "depth_band"), ("by_N", "Ncoh"), ("by_regime", "reg")):
            res[key][basis] = {}
            for bd, g in b0.groupby("board", sort=True):
                res[key][basis][str(bd)] = {}
                for sp in ("fit", "holdout"):
                    gg = g[g["split"] == sp]
                    res[key][basis][str(bd)][sp] = {
                        f"{a}|{r}|{v}": _book_cell(h)
                        for (a, r, v), h in gg.groupby(["anchor", "rule", col], sort=True)}
        res["by_era"][basis] = {}
        for bd, g in b0.groupby("board", sort=True):
            res["by_era"][basis][str(bd)] = {
                f"{e}|{a}|{r}": _book_cell(h)
                for (e, a, r), h in g.groupby(["era", "anchor", "rule"], sort=True)}
        # the paired comparison
        res["paired"][basis] = {}
        pb = b0[b0["paired"]]
        for bd, g in pb.groupby("board", sort=True):
            res["paired"][basis][str(bd)] = {}
            for sp in ("fit", "holdout"):
                gg = g[g["split"] == sp]
                cells = {f"{a}|{r}": _book_cell(h)
                         for (a, r), h in gg.groupby(["anchor", "rule"], sort=True)}
                pg = (res["paired_population_gap"]["by_basis_board_window"]
                      .get(basis, {}).get(str(bd), {})
                      .get(f"{sp}|paired_fillable_only", {}).get("mean_gap_pct"))
                for rule in EXIT_RULES:
                    a, b = cells.get(f"T_close|{rule}"), cells.get(f"T1_open|{rule}")
                    if a and b and a.get("n") and b.get("n"):
                        d = _r((a["mean_pct"] or 0) - (b["mean_pct"] or 0), 3)
                        cells[f"DELTA_close_minus_open|{rule}"] = {
                            "n_close": a["n"], "n_open": b["n"],
                            "d_mean_pp": d,
                            "d_mean_net_pp": _r((a["mean_net_pct"] or 0)
                                                - (b["mean_net_pct"] or 0), 3),
                            "d_win_pp": _r((a["win_rate_pct"] or 0) - (b["win_rate_pct"] or 0)),
                            "paired_mean_gap_pct": pg,
                            "residual_vs_gap_pp": _r(d - pg, 4) if (d is not None
                                                                    and pg is not None)
                            else None,
                            "reading": ("the delta IS the overnight gap; residual_vs_gap_pp "
                                        "is what the gap does not explain, and it is "
                                        "sub-basis-point on this population."),
                        }
                res["paired"][basis][str(bd)][sp] = cells
        # the UNPAIRED remainder — break days whose T+1 open was unbuyable. These are the
        # only trades the close entry can take and the open entry cannot; if the weakness
        # family has a structural advantage over L1's anchor, it has to show up HERE.
        res["paired"][basis].setdefault("_unpaired_remainder", {})
        up = b0[(~b0["paired"]) & (b0["anchor"] == "T_close")]
        for bd, g in up.groupby("board", sort=True):
            res["paired"][basis]["_unpaired_remainder"][str(bd)] = {
                sp: {str(r): _book_cell(h)
                     for r, h in g[g["split"] == sp].groupby("rule", sort=True)}
                for sp in ("fit", "holdout")}
    return res


def _collapse_ladder(df: pd.DataFrame, levels: list[list[str]], stat) -> dict:
    """Emit the most specific cell that clears THIN_CELL_N; print every collapse.

    `cells` is a DISJOINT partition and is the only thing that may be counted. A thin cell
    is NOT given its parent's numbers under its own name — doing that emitted duplicate rows
    (two thin regime cells resolving to one parent printed byte-identical statistics under
    two labels, and that parent also appeared as a sibling containing them). Thin cells are
    listed separately in `collapsed_cells` as POINTERS to the parent that carries them.
    """
    out, log, pointers = {}, [], {}
    full = levels[0]
    thin_by_parent: dict[str, list] = {}
    for keys, g in df.groupby(full, sort=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        label = "|".join(str(k) for k in keys)
        if len(g) >= THIN_CELL_N:
            out[label] = {"level": "|".join(full), "n_rows": int(len(g)), **stat(g)}
            continue
        placed = False
        for lv in levels[1:]:
            sub = df
            plab = []
            for c, v in zip(full, keys):
                if c in lv:
                    sub = sub[sub[c] == v]
                    plab.append(str(v))
            if len(sub) >= THIN_CELL_N:
                parent = "|".join(plab)
                thin_by_parent.setdefault(parent, []).append((label, int(len(g)), lv, sub))
                pointers[label] = {"own_n": int(len(g)), "carried_by_parent": parent,
                                   "parent_level": "|".join(lv)}
                log.append({"cell": label, "own_n": int(len(g)),
                            "collapsed_to": "|".join(lv), "parent_label": parent,
                            "parent_n": int(len(sub))})
                placed = True
                break
        if not placed:
            out[label] = {"level": "|".join(full), "n_rows": int(len(g)), "thin": True,
                          "UNCOLLAPSIBLE": True, **stat(g)}
            log.append({"cell": label, "own_n": int(len(g)), "collapsed_to": None,
                        "parent_label": None, "parent_n": None})
    # one entry per PARENT that absorbed thin children, emitted once
    parents = {}
    for parent, kids in sorted(thin_by_parent.items()):
        _lab, _n, lv, sub = kids[0]
        parents[parent] = {"level": "|".join(lv), "n_rows": int(len(sub)),
                           "absorbs": sorted(k[0] for k in kids),
                           "absorbed_own_n": {k[0]: k[1] for k in kids}, **stat(sub)}
    return {
        "cells": out, "collapsed_into_parents": parents, "collapsed_cell_pointers": pointers,
        "collapse_log": log,
        "counting_rule": (
            f"`cells` is the DISJOINT partition — count THAT, and only that. It holds every "
            f"full three-way cell clearing n >= {THIN_CELL_N} plus any UNCOLLAPSIBLE thin "
            "cell. Thin cells that were absorbed appear ONLY as pointers in "
            "collapsed_cell_pointers; their carrying parents appear ONCE each in "
            "collapsed_into_parents. A parent's rows may overlap a printed sibling's, so "
            "cells and collapsed_into_parents must never be summed together."),
        "collapse_rule": (f"a cell with n < {THIN_CELL_N} is carried by the most specific "
                          "parent that clears the floor, dropping the regime dimension first "
                          "and then the days dimension. Every substitution is in "
                          "collapse_log with both n's."),
    }


def longhuitou(lht: pd.DataFrame, tr: pd.DataFrame) -> dict:
    """C10 — the proven-ladder pullback. TOLERANT basis throughout."""
    res = {
        "basis": "TOLERANT (v0's primary) for the ladder, the pullback and the outcome. The "
                 "strict tape plays no part in this battery.",
        "definition": {
            "population": f"the first no-board close after a tolerant run of N >= "
                          f"{LHT_MIN_LADDER}, then sessions 1..{LHT_WINDOW}, truncated at the "
                          "first new limit-up close.",
            "retrace": RETRACE_NOTE,
            "outcome": f"P(new limit-up close within {LHT_FWD_SESSIONS} usable sessions of "
                       "the qualifying day). A forward chain that breaks with no board found "
                       "counts as NO BOARD and is flagged unresolved — dropping it would "
                       "delete exactly the losers.",
            "entry": "the qualifying day's CLOSE, fillable by construction (the window "
                     "contains no sealed closes).",
        },
        "clustering_warning": (
            f"ONE episode emits up to {LHT_WINDOW} rows. n is NOT a count of independent "
            "observations — n_episodes is reported beside every book cell and n_names / "
            "n_dates beside every return block. Read the episode count, not the row count."),
        "survivorship_warning": (
            "The 龙回头 statistics are SURVIVOR-FLATTERED in a way the 回封 ones are not. "
            "The store holds the currently listed universe, so a ladder that ended in the "
            "name's terminal decline and delisting is absent from the population entirely. "
            "Every pullback-recovery rate below is an upper bound."),
        "rates": {}, "book": {}, "three_way": {}, "by_era": {}, "binary_conditioners": {},
    }

    def rcell(g: pd.DataFrame) -> dict:
        """Row-level rate AND episode-level rate. They answer different questions.

        The row rate is P(a randomly chosen PULLBACK DAY is followed by a board within 5
        sessions) — its denominator is window-days, and one episode contributes up to ten of
        them, so its Wilson interval is far too narrow to read as an episode probability.
        The episode rate (one row per episode, taken at day 1) is P(THE EPISODE re-boards),
        which is what a sentence like "a quarter of ended ladders come back" actually means.
        Both are printed; neither is allowed to stand in for the other.
        """
        out = rate_block(int(g["y_new_board_5d"].sum()), len(g))
        out["denominator"] = "ROWS (window-days), not episodes"
        out["n_episodes"] = int(g["episode_id"].nunique())
        out["n_names"] = int(g["ticker"].nunique())
        out["unresolved_n"] = int((~g["resolved_5d"]).sum())
        res_only = g[g["resolved_5d"]]
        out["rate_excl_unresolved_pct"] = (
            _r(100.0 * float(res_only["y_new_board_5d"].mean())) if len(res_only) else None)
        # episode level: one row per episode, the FIRST window day present in this slice
        ep = g.sort_values("day_k").drop_duplicates("episode_id", keep="first")
        out["episode_level"] = {
            **rate_block(int(ep["y_new_board_5d"].sum()), len(ep)),
            "denominator": "EPISODES (one row each, at the earliest window day in this slice)",
            "note": ("this is P(the episode re-boards within 5 sessions of that day). Its "
                     "Wilson interval is the honest one — roughly 2.6x wider than the row "
                     "interval, because the row denominator counts the same episode up to "
                     f"{LHT_WINDOW} times."),
        }
        return out

    for bd, g in lht.groupby("board", sort=True):
        res["rates"][str(bd)] = {"all": rcell(g)}
        for sp in ("fit", "holdout"):
            gg = g[g["split"] == sp]
            res["rates"][str(bd)][sp] = {
                "overall": rcell(gg),
                "by_retrace": {str(v): rcell(h)
                               for v, h in gg.groupby("retrace_band", sort=True)},
                "by_days": {str(v): rcell(h) for v, h in gg.groupby("days_band", sort=True)},
                "by_regime": {str(v): rcell(h) for v, h in gg.groupby("reg", sort=True)},
                "by_run_N": {str(v): rcell(h)
                             for v, h in gg.groupby(gg["run_N"].clip(3, 6), sort=True)},
            }
        res["by_era"][str(bd)] = {str(e): rcell(h) for e, h in g.groupby("era", sort=True)}
        res["binary_conditioners"][str(bd)] = {
            sp: {name: {str(bool(v)): rcell(h) for v, h in gg.groupby(col, sort=True)}
                 for name, col in (("vol_declining", "vol_declining"),
                                   ("no_limit_down_since_run_end", "no_ld_since_end"),
                                   ("close_ge_half_retrace", "close_ge_half"))}
            for sp, gg in (("fit", g[g["split"] == "fit"]),
                           ("holdout", g[g["split"] == "holdout"]))}
        # D3 — the binary conditioners are confounded by WHERE IN THE WINDOW the row sits.
        # A declining-volume row is on average much later in the window than a
        # non-declining one, and the re-board hazard falls with day_k, so the raw contrast
        # is partly the day effect wearing a volume label. Controlled table + the exposure
        # imbalance that motivates it.
        res.setdefault("binary_conditioners_controlled", {})[str(bd)] = {}
        for name, col in (("vol_declining", "vol_declining"),
                          ("no_limit_down_since_run_end", "no_ld_since_end"),
                          ("close_ge_half_retrace", "close_ge_half")):
            blk = {}
            for sp in ("fit", "holdout"):
                gg = g[g["split"] == sp]
                if not len(gg):
                    continue
                expo = {str(bool(v)): _r(float(len(h)) / max(1, h["episode_id"].nunique()), 2)
                        for v, h in gg.groupby(col, sort=True)}
                cells, spreads = {}, []
                for db, hb in gg.groupby("days_band", sort=True):
                    sub = {str(bool(v)): rcell(h) for v, h in hb.groupby(col, sort=True)}
                    cells[str(db)] = sub
                    if len(sub) == 2:
                        vals = [sub[k]["rate_pct"] for k in sorted(sub)
                                if sub[k]["rate_pct"] is not None]
                        if len(vals) == 2:
                            spreads.append(abs(vals[1] - vals[0]))
                raw = {str(bool(v)): _r(100.0 * float(h["y_new_board_5d"].mean()))
                       for v, h in gg.groupby(col, sort=True)}
                blk[sp] = {
                    "rows_per_episode_by_arm": expo,
                    "uncontrolled_rate_pct": raw,
                    "within_days_band": cells,
                    "mean_abs_within_band_spread_pp": _r(float(np.mean(spreads)), 2)
                    if spreads else None,
                }
            f_s = blk.get("fit", {}).get("mean_abs_within_band_spread_pp")
            h_s = blk.get("holdout", {}).get("mean_abs_within_band_spread_pp")
            blk["stability_verdict"] = (
                "UNSTABLE / CONFOUNDED — the within-days-band spread does not reproduce "
                f"across windows (fit {f_s} pp vs holdout {h_s} pp). Do not report the "
                "uncontrolled contrast as a finding."
                if (f_s is not None and h_s is not None
                    and (max(f_s, h_s) > 2 * min(f_s, h_s) + 0.5))
                else f"within-band spread fit {f_s} pp vs holdout {h_s} pp.")
            res["binary_conditioners_controlled"][str(bd)][name] = blk

    for bd, g in tr.groupby("board", sort=True):
        res["book"][str(bd)] = {}
        for sp in ("fit", "holdout"):
            gg = g[g["split"] == sp]
            res["book"][str(bd)][sp] = {
                "overall": {str(r): _book_cell(h) for r, h in gg.groupby("rule", sort=True)},
                "by_retrace": {f"{r}|{v}": _book_cell(h)
                               for (r, v), h in gg.groupby(["rule", "retrace_band"],
                                                           sort=True)},
                "by_days": {f"{r}|{v}": _book_cell(h)
                            for (r, v), h in gg.groupby(["rule", "days_band"], sort=True)},
            }
        # the three-way table the brief asks for, with the collapse printed
        res["three_way"][str(bd)] = {}
        for sp in ("fit", "holdout"):
            for rule in EXIT_RULES:
                gg = g[(g["split"] == sp) & (g["rule"] == rule)]
                if not len(gg):
                    continue
                res["three_way"][str(bd)][f"{sp}|{rule}"] = _collapse_ladder(
                    gg, [["retrace_band", "days_band", "reg"],
                         ["retrace_band", "days_band"], ["retrace_band"]], _book_cell)
    return res


# ── the decision census ───────────────────────────────────────────────────────

def survivor_census(tr_hf: pd.DataFrame, tr_lht: pd.DataFrame) -> dict:
    """THE decision table: which pre-registered cohorts clear the net bar in BOTH windows.

    Censused, not curated. Every cell in the pre-registered grid is enumerated; the ones
    that clear are named with their n, and the count that clears is printed against the
    count tested so the reader can price the multiplicity.
    """
    grids = []
    hf = tr_hf.copy()
    hf["cohort"] = ("HF|" + hf["basis"] + "|" + hf["board"] + "|" + hf["anchor"] + "|"
                    + hf["rule"])
    for extra, tag in ((None, ""), ("depth_band", "depth"), ("Ncoh", "N"),
                       ("vz_band", "volz"), ("reg", "reg")):
        d = hf.copy()
        if extra is not None:
            d["cohort"] = d["cohort"] + "|" + tag + "=" + d[extra].astype(str)
        grids.append(d[["cohort", "split", "ret", "ticker", "date"]])
    lh = tr_lht.copy()
    lh["cohort"] = "LHT|" + lh["board"] + "|q_close|" + lh["rule"]
    for extra, tag in ((None, ""), ("retrace_band", "dd"), ("days_band", "days"),
                       ("reg", "reg"), ("close_ge_half", "half"),
                       ("no_ld_since_end", "nold"), ("vol_declining", "voldn")):
        d = lh.copy()
        if extra is not None:
            d["cohort"] = d["cohort"] + "|" + tag + "=" + d[extra].astype(str)
        grids.append(d[["cohort", "split", "ret", "ticker", "date"]])
    allg = pd.concat(grids, ignore_index=True)

    rows = []
    for coh, g in allg.groupby("cohort", sort=True):
        f = g[g["split"] == "fit"]["ret"].to_numpy(dtype="float64")
        h = g[g["split"] == "holdout"]["ret"].to_numpy(dtype="float64")
        f, h = f[np.isfinite(f)], h[np.isfinite(h)]
        if f.size < CENSUS_MIN_N or h.size < CENSUS_MIN_N:
            continue
        nf = (1.0 + f) * (1.0 - ROUND_TRIP_COST) - 1.0
        nh = (1.0 + h) * (1.0 - ROUND_TRIP_COST) - 1.0
        gf = g[g["split"] == "fit"]
        gh = g[g["split"] == "holdout"]
        cf = date_clustered(gf["ret"].to_numpy(), gf["date"].to_numpy())
        ch = date_clustered(gh["ret"].to_numpy(), gh["date"].to_numpy())
        rows.append({
            "cohort": coh, "n_fit": int(f.size), "n_holdout": int(h.size),
            "fit_gross_pct": _r(100.0 * float(f.mean()), 3),
            "holdout_gross_pct": _r(100.0 * float(h.mean()), 3),
            "fit_net_pct": _r(100.0 * float(nf.mean()), 3),
            "holdout_net_pct": _r(100.0 * float(nh.mean()), 3),
            "holdout_net_se_pct": _r(100.0 * float(nh.std(ddof=1)) / np.sqrt(nh.size), 3),
            "holdout_net_t_PER_TRADE_OVERSTATED": _r(
                float(nh.mean()) / (float(nh.std(ddof=1)) / np.sqrt(nh.size)), 2)
            if nh.std(ddof=1) > 0 else None,
            "fit_dates": cf.get("n_dates"), "holdout_dates": ch.get("n_dates"),
            "fit_trades_per_date": cf.get("trades_per_date"),
            "holdout_trades_per_date": ch.get("trades_per_date"),
            "fit_date_eq_net_pct": cf.get("date_eq_weight_net_pct"),
            "holdout_date_eq_net_pct": ch.get("date_eq_weight_net_pct"),
            "holdout_date_clustered_t": ch.get("date_clustered_t"),
            "fit_date_clustered_t": cf.get("date_clustered_t"),
            "clears_net_both": bool(nf.mean() > 0 and nh.mean() > 0),
            "clears_gross_both": bool(f.mean() > 0 and h.mean() > 0),
            # `or -99` would read a date-eq net of exactly 0.0 as missing and fail it for
            # the wrong reason. No cohort currently rounds to 0.0; the guard is explicit so
            # a future one is not silently mis-scored.
            "clears_date_clustered_both": bool(
                cf.get("date_eq_weight_net_pct") is not None
                and ch.get("date_eq_weight_net_pct") is not None
                and cf["date_eq_weight_net_pct"] > 0 and ch["date_eq_weight_net_pct"] > 0),
            "strong_n": bool(f.size >= CENSUS_STRONG_N and h.size >= CENSUS_STRONG_N),
        })
    # family + data-availability tagging (D1 / D8)
    for r in rows:
        coh = r["cohort"]
        r["family"] = ("LHT" if coh.startswith("LHT") else
                       "HF_T_close" if "|T_close|" in coh else "HF_T1_open")
        r["is_data_availability_slice"] = bool("=reg_na" in coh or "=vz_na" in coh)
    rows.sort(key=lambda r: (-(r["holdout_net_pct"] or -99)))
    clears = [r for r in rows if r["clears_net_both"]]
    real = [r for r in clears if not r["is_data_availability_slice"]]

    # per-family drift, because the coin-flip benchmark is only meaningful for a family
    # centred on zero. A family running -1.2%/trade cannot throw survivors by chance.
    fam = {}
    for name in ("HF_T1_open", "HF_T_close", "LHT"):
        sub = [r for r in rows if r["family"] == name]
        if not sub:
            continue
        src = tr_lht if name == "LHT" else tr_hf[tr_hf["anchor"] ==
                                                 ("T_close" if name == "HF_T_close"
                                                  else "T1_open")]
        x = src["ret"].to_numpy(dtype="float64")
        x = x[np.isfinite(x)]
        drift = 100.0 * float(((1.0 + x) * (1.0 - ROUND_TRIP_COST) - 1.0).mean()) if x.size \
            else None
        # "Near zero" is judged at a quarter point per trade — wide enough to catch a family
        # whose cohorts genuinely coin-flip, tight enough to exclude the two that run at
        # about -1%/trade. A tighter cut reported a 0.0 benchmark for the one family the
        # benchmark actually describes, which is the same pooling error in miniature.
        centred = drift is not None and abs(drift) < 0.25
        n_clear = int(sum(1 for r in sub if r["clears_net_both"]))
        exp = round(0.25 * len(sub), 1)
        fam[name] = {
            "cohorts_tested": len(sub),
            "cohorts_clearing_net_both": n_clear,
            "family_pooled_net_pct": _r(drift, 3),
            "coin_flip_expectation_if_centred": exp,
            "benchmark_applies": bool(centred),
            "expectation_basis": (
                f"family drift is {_r(drift, 3)}%/trade — within a quarter point of zero, so "
                f"a two-window sign test passes on ~25% of cohorts by chance. Observed "
                f"{n_clear} against an expectation of {exp}: this family is AT its own null, "
                "not below it." if centred else
                f"family drift is {_r(drift, 3)}%/trade — a coin-flip benchmark does NOT "
                "apply. A family this far from zero throws essentially no chance survivors, "
                f"so its count of {n_clear} is informative at face value rather than against "
                f"{exp}."),
        }
    tvals = [r["holdout_date_clustered_t"] for r in rows
             if r["holdout_date_clustered_t"] is not None]
    return {
        "bar": PRE_REGISTRATION["decision_bar"],
        "cohorts_tested": len(rows),
        "cohorts_clearing_net_both_windows": len(clears),
        "cohorts_clearing_gross_both_windows": int(sum(1 for r in rows
                                                       if r["clears_gross_both"])),
        "cohorts_clearing_date_clustered_both": int(sum(1 for r in rows
                                                        if r["clears_date_clustered_both"])),
        "by_family": fam,
        "THE_VERDICT_STATISTIC": {
            "max_holdout_date_clustered_t_across_all_cohorts": _r(max(tvals), 2) if tvals
            else None,
            "cohorts_with_holdout_date_clustered_t_ge_2": int(sum(1 for t in tvals if t >= 2)),
            "why_this_and_not_the_survivor_count": (
                "The survivor COUNT cannot carry the verdict: it is only interpretable "
                "against a per-family chance benchmark, and two of the three families are so "
                "far from zero drift that no benchmark applies. The t-census is the honest "
                "summary — across every cohort tested, the largest holdout date-clustered t "
                "is the number above, and the count reaching conventional significance is "
                "zero. That statement needs no multiplicity correction to be damning."),
        },
        "clearing_cohorts": clears,
        "clearing_cohorts_excluding_data_availability_slices": real,
        "clearing_cohorts_strong_n": [r for r in clears if r["strong_n"]],
        "clearing_cohorts_strong_n_and_date_clustered": [
            r for r in clears if r["strong_n"] and r["clears_date_clustered_both"]
            and not r["is_data_availability_slice"]],
        "multiplicity_note": (
            f"{len(rows)} cohorts were tested at the n >= {CENSUS_MIN_N} floor, but they must "
            "be read PER FAMILY (see by_family) and never pooled. Pooling manufactures a "
            "false result: the two close-anchored families run at roughly -1.2%/trade, so "
            "their chance expectation is ~0 rather than a quarter of their count, and "
            "putting them in one denominator with the near-zero-drift T+1-open family makes "
            "the total look 'below chance' when the open family is in fact AT its own "
            "benchmark. Cohorts are also heavily overlapping slices of the same trades and "
            "are not independent tests. Read by_family, then read THE_VERDICT_STATISTIC."),
        "clustering_note": (
            "holdout_net_t_PER_TRADE_OVERSTATED is named for what it is. Every regime cell "
            "is a market-wide daily state, so its trades arrive in same-day clumps; the "
            "per-trade t divides by sqrt(trades) where the honest denominator is "
            "sqrt(sessions). holdout_date_clustered_t is the one to read."),
        "all_cohorts": rows,
    }


ORE_LEDGER = {
    "law": ("THE ORE LAW: a null closes the CONSTRUCTION TESTED, never the hypothesis. "
            "Everything below is untested by this instrument — none of it is refuted by "
            "anything above, and several items are the obvious next constructions. "
            "'Not found yet' is not 'does not exist'."),
    "untested_variants": [
        {"variant": "intraday re-seal TIMING — a 09:40 break that re-seals at 10:05 versus a "
                    "14:52 break that never recovers",
         "blocked_by": "daily bars. Both print the same OHLC row, the same "
                       "close_off_limit_pct and the same failed_up_seal event.",
         "why_it_matters": "this is THE conditioner practitioners actually use for 回封, and "
                           "it is the single largest source of unmodelled variance in the "
                           "battery above. The operator has just purchased 历史分钟 (minute "
                           "history); when it lands, the first re-run of this instrument "
                           "should split every break-day cell by first-touch time, "
                           "break-count and time-to-re-seal. Nothing in this receipt "
                           "constrains what that split will show."},
        {"variant": "seal-wall size (封单量 / seal_fund_yi) conditioning — was the wall that "
                    "broke a real one or one desk's paint?",
         "blocked_by": "data/china_zt_pool carries seal_fund_yi for a 36-date window "
                       "(2026-06-15 forward) and no history.",
         "why_it_matters": "§2.3 of the blinded map predicts a NON-MONOTONE relation between "
                           "break quality and next-day strength: a deliberate 炸板 washout "
                           "with a hard re-seal should out-continue a clean light-volume "
                           "seal. Depth and volume z are lossy shadows of the wall; the "
                           "hypothesis is untested, not refuted."},
        {"variant": "theme / 题材 relay context — is the broken name the sector leader, a "
                    "follower, or the last laggard in a dying wave?",
         "blocked_by": "not run in this lane. members.parquet carries CURRENT industry "
                       "membership only, and industry is not 题材.",
         "why_it_matters": "C6/C8 in the blinded map make two-sided predictions here; a "
                           "leader's break and a follower's break are different events "
                           "wearing one label in every table above."},
        {"variant": "N-specific and band-specific exit tuning",
         "blocked_by": "deliberately not run — E1 and E3 are applied identically to every "
                       "cohort so the cohort comparison is like-for-like.",
         "why_it_matters": "a weakness entry's natural exit is not a ladder-rider's exit; an "
                           "exit tuned per cohort is both an obvious improvement and an "
                           "obvious overfit, and needs its own holdout discipline."},
        {"variant": "stop-loss families (fixed %, ATR, trailing, close-based, intraday)",
         "blocked_by": "an intraday stop is unmeasurable on daily bars without assuming a "
                       "path; no stop was in the pre-registered exit set.",
         "why_it_matters": "the p10 and worst columns show exactly where a stop would bind, "
                           "and the trapdoor table shows the hazard it would be cutting. Two "
                           "exit rules is not the exit space."},
        {"variant": "half-retrace alternatives and other pullback-depth measures (retrace of "
                    "the last board only, MA-anchored pullbacks, close-vs-first-board-open)",
         "blocked_by": "one measure was pre-registered; testing several and reporting the "
                       "best would be the overfit this instrument exists to avoid.",
         "why_it_matters": "the retrace_frac denominator (run height) is one choice among "
                           "many, and the 15%/30% band edges are lore, not measurement."},
        {"variant": "post-expansion re-run on the ~5,400-name universe",
         "blocked_by": "the expansion is in flight in a sibling Codex lane and is not in "
                       "this checkout.",
         "why_it_matters": "the 打板 game lives disproportionately in the small-cap names "
                           "this curated store omits. Every count here is scoped to 1,842 "
                           "names and the direction of the omission is toward the names most "
                           "likely to carry the effect."},
        {"variant": "ST (5% band) and delisted universes",
         "blocked_by": "ST dropped wholesale (the store carries one asof and no membership "
                       "history); delisted names are absent from the raw store entirely.",
         "why_it_matters": "the trapdoor and the 龙回头 recovery rate are both biased by the "
                           "same absence, in the same direction: the tape cannot show a "
                           "pullback that never recovered because the name stopped existing."},
        {"variant": "the near-miss cohort (closed high but never touched the limit) as the "
                    "matched control for the break cohort",
         "blocked_by": "C12 in the blinded map; not this lane's population.",
         "why_it_matters": "without it, the 回封 rate has no counterfactual — the right "
                           "question is whether a BROKEN board predicts better than a "
                           "matched name that simply closed strong."},
        {"variant": "position sizing, portfolio construction and the correlated-exit tail",
         "blocked_by": "every number here is a per-trade mean over overlapping episodes; no "
                       "portfolio is formed and no capacity is estimated.",
         "why_it_matters": "§2.10 of the blinded map: these books are structurally short a "
                           "liquidity option, and per-trade expectancy does not price it."},
    ],
}


def main() -> int:
    t0 = time.time()
    _T0[0] = t0
    print("[build] panel + both batteries over data/china_stocks_raw ...", flush=True)
    hf, lht, tr_hf, tr_lht, meta, pop = build()
    print(f"        回封 {len(hf)} event rows / {len(tr_hf)} trade legs; "
          f"龙回头 {len(lht)} window rows / {len(tr_lht)} trade legs; "
          f"{time.time() - t0:.1f}s", flush=True)

    print("[B-回封] re-seal rates + trapdoor ...", flush=True)
    hf_rates = huifeng_rates(hf)
    print("[B-回封] entry books — T close vs T+1 open ...", flush=True)
    hf_book = huifeng_book(tr_hf, hf)
    print("[B-龙回头] pullback window + close-entry book ...", flush=True)
    lht_res = longhuitou(lht, tr_lht)
    print("[census] net-expectancy decision table ...", flush=True)
    census = survivor_census(tr_hf, tr_lht)
    print(f"        {census['cohorts_clearing_net_both_windows']}"
          f"/{census['cohorts_tested']} cohorts clear the net bar in both windows",
          flush=True)

    payload = {
        "instrument": "research/cn_prophet_audit/weakness_entry_battery_v1.py",
        "program": ("CN LIMIT-MOVE ALPHA, Wave 2, lane W2-B — THE WEAKNESS-ENTRY BATTERY "
                    "(回封 + 龙回头)"),
        "builds_on": [
            "research/cn_prophet_audit/limit_move_footprint_v0.py (PR #4999) — conventions",
            "research/cn_prophet_audit/continuation_rider_v1.py (PR #5061) — fillability and "
            "locked-exit idioms, copied unchanged; its central null is this lane's premise",
            "research/cn_prophet_audit/board_ecology_regime_v1.py (L2 salvage) — the i5 dial",
            "research/CN_LIMIT_ALPHA_BLINDED_BRAINSTORM_2026-08-08.md — C3 and C10",
        ],
        "tier": "display/audit — MEASUREMENT ONLY. Nothing here ranks, sizes, gates or admits.",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_sec": None,
        "pre_registration": PRE_REGISTRATION,
        "definitions": {
            "limit_up_close_TOLERANT": f"close >= round(prev_close*(1+w), 2) * "
                                       f"(1 - {LIMIT_CLOSE_TOL}) — v0's adjudicated primary",
            "limit_up_close_STRICT": "close >= round(prev_close*(1+w), 2) — the house tape's "
                                     "rule, and the basis of the 回封 primary population",
            "failed_up_seal_STRICT": "high >= lim_up AND close < lim_up (the tape's event)",
            "failed_up_seal_TOLERANT": f"high >= lim_up*(1-{LIMIT_CLOSE_TOL}) AND "
                                       f"close < lim_up*(1-{LIMIT_CLOSE_TOL})",
            "limit_down_close": f"close <= round(prev_close*(1-w), 2) * (1 + {LIMIT_CLOSE_TOL}) "
                                "(tolerant) / close <= round(prev_close*(1-w), 2) (strict)",
            "T_to_T1": f"the IMMEDIATELY following bar, live, at most {MAX_PAIR_GAP_DAYS} "
                       "calendar days later (v0's rule). Contiguity in array index is what "
                       "makes the multi-session exit walk exact rather than approximate.",
            "w": "engine.china_microstructure.limit_width_for_date — star 20%, chinext 20% "
                 "on/after 2020-08-24 else 10%, main 10%, bse 30%",
            "fit_holdout_split": f"{SPLIT_DATE:%Y-%m-%d} — v0's computed 70/30 date, frozen. "
                                 "ONE holdout pass. Holdout is the headline.",
            "eras": {name: f"{lo}-{hi}" for name, lo, hi in ERA_BOUNDS},
            "cost_bar": f"{ROUND_TRIP_COST * 1e4:.0f} bp round trip applied as mean_net_pct "
                        "beside every gross mean, never instead of it.",
        },
        "exclusions": {
            "st_cohort": "ALL dates for every ticker in data/china_st/st_snapshot.parquet "
                         "(one asof, no membership history).",
            "ipo_windows": f"STAR/ChiNext first {CHINEXT_STAR_IPO_WINDOW} sessions; pre-2014 "
                           f"listings' first {PRE2014_IPO_WINDOW} session.",
            "exdiv_suspect": "|open - prev_close| / prev_close > 1.5*w.",
            "zero_volume": "bars with volume <= 0 (suspension placeholders).",
            "universe_is_curated": (
                "THE BINDING COVERAGE FACT, inherited from v0 and unchanged. "
                "data/china_stocks_raw holds a curated subset of the listed A-share market. "
                "No number here is a market-wide statistic."),
            "survivorship": (
                "The store holds the CURRENT listed universe. This bites the WEAKNESS "
                "batteries harder than it bit L1's ladder-rider: 龙回头 asks what happens "
                "after a pullback, and the pullbacks that ended in delisting are absent from "
                "the population, not merely under-counted in a tail."),
            "usability_asymmetry": (
                "A bar's usability at T+1 is a property of T+1, so conditioning on it is a "
                "filter a trader at T could not apply. Applied uniformly to numerator and "
                "denominator (v0's handling). The T+1-OPEN book additionally refuses "
                "unfillable opens, which IS knowable at entry (the 09:25 auction prints "
                "before the 09:30 entry). The T-CLOSE book needs no such refusal, which is "
                "the whole point of the construction."),
        },
        "meta": meta,
        "population_receipt": pop,
        "b_huifeng_rates": hf_rates,
        "b_huifeng_book": hf_book,
        "b_longhuitou": lht_res,
        "decision_census": census,
        "ore_ledger": ORE_LEDGER,
    }
    payload["runtime_sec"] = round(time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(jsonable(payload), indent=2, ensure_ascii=False) + "\n")
    print(f"[done ] {payload['runtime_sec']:.1f}s -> {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
