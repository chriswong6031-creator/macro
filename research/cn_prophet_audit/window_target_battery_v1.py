#!/usr/bin/env python3
"""window_target_battery_v1.py — CN LIMIT-MOVE ALPHA, Wave 3 A: THE WINDOW-TARGET BATTERY.

WHAT THIS IS
    A MEASUREMENT instrument, display/audit tier.  It re-targets the OUTCOME of the whole
    limit-move program.  Wave 1 (limit_move_footprint_v0.py, continuation_rider_v1.py) and
    Wave 2 asked one question — does the name close limit-up again TOMORROW — and answered
    it twice: the ladder P(board T+1 | 连板 N) is well-ordered and large, and the T+1 opening
    auction prices it away completely (every naive open-entry book negative, anti-monotone in
    the very cohorts the ladder ranks best).

    That is a null about BOARDS.  The operator's charter never asked for boards:

        "Do not lock into 10%-every-day rigidity: the target is the trajectory of rerating
         windows (6% one day, 8% the next, a board here and there)."

    A board is the unfillable spike of a rerating window.  The 6-8% days are its buyable
    flesh.  Neither had ever been an outcome class in this program.  So THE DECISION QUESTION
    of this lane is exactly one line:

        the T+1 auction prices tomorrow's BOARD — does it also price the WINDOW?

    FOUR outcome families, every threshold scaled by w, the name-day's own limit width, so a
    10% main-board name and a 20% ChiNext name are never compared on a raw percentage:

      O1  BIG-DAY          next-session close-to-close return in [0.6w, the tolerant limit),
                           i.e. the 6-8%-style day that is NOT a board.  Its sibling
                           P(return >= 0.6w INCLUDING boards) is printed beside it so the
                           decomposition big-day + board is visible rather than implied.
      O2  WINDOW-CUM       cumulative close-to-close return over H in {3,5,10} sessions
                           >= {0.8w, 1.5w, 2.5w}.  The window an entrant actually holds.
      O3  WINDOW-PEAK      max drawup (max high in the window / entry-reference close - 1)
                           >= the same thresholds.  "Was there a sellable moment."  The gap
                           O3 - O2 is the part of the window that lives in a peak you cannot
                           schedule.
      O4  NEAR-MISS (C12)  the blinded discontinuity map: days closing in [0.85w, the
                           tolerant limit) whose HIGH never touched the limit price, matched
                           against sealed closes within (board, era, prior ladder N, f3
                           quintile).  Attention-vs-supply is NOT decomposed and is NOT
                           claimed; this is a matched comparison of a bundled difference.

    THE BOOK is the decision table: four pre-registered signals, entries at the T+1 open and
    ONLY where that open is fillable (L1's censor, copied), fixed-H exits at H in {3,5,10}
    sessions' opens with L1's locked-exit rolls.  Plus the O3-framing book — what a window
    contains if you could sell into its best open after a 1.5w drawup — carried as an UPPER
    BOUND and a capacity measurement, never as a strategy, with the implementable
    first-open-after-trigger sibling printed beside it so the foresight premium is a number.

WHAT IT IS NOT
    Not a promotion, not a gate, not a ranker, not a signal, not a claim that any cell is
    tradeable.  Nothing here sizes, ranks, admits or scores anything.  No LLM is involved.
    THE ORE LAW binds: a null on one construction closes THAT CONSTRUCTION and nothing else.
    The ORE LEDGER in the receipt is the list of what was not tested.

CONVENTIONS — REUSED FROM v0 / L1 VERBATIM, NOT REINVENTED
    Board + limit width: engine.china_microstructure._board_from_ticker /
    limit_width_for_date (imported).  PRIMARY limit-up close: v0's adjudicated TOLERANT test
    ``close >= round(prev_close*(1+w), 2) * (1 - 0.002)``.  Exclusions (IPO window, bad
    prev_close, ex-div open jump, zero volume), the <=10-calendar-day pair rule, the
    2021-11-26 fit/holdout split, Wilson intervals, THIN labelling at n<20 and the
    never-pool-boards rule are v0's and are unchanged.  The fillability censor, the
    locked-exit roll and the date-clustered standard error are L1's / W2-B's, copied.

    ONE convention is TIGHTENED, disclosed: ChiNext is never pooled across 2020-08-24 (the
    10% -> 20% band step), so the board key here is {main, star, chinext_10pct_pre2020,
    chinext_20pct_post2020}.  The raw board label survives only inside the v0 parity gate,
    which must reproduce v0's published pooled-ChiNext ladder.

Run from repo root:  TZ=UTC python3 research/cn_prophet_audit/window_target_battery_v1.py
Outputs (frozen, committed):
    research/cn_prophet_audit/WINDOW_TARGET_BATTERY_V1_2026-08-09.json
    research/cn_prophet_audit/WINDOW_TARGET_BATTERY_V1_2026-08-09.md  (hand-written from it)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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
OUT_JSON = AUDIT / "WINDOW_TARGET_BATTERY_V1_2026-08-09.json"

# The L2 regime dial lives on an unmerged sibling lane.  Read it from git by PINNED BLOB
# rather than from a scratch file: a pinned SHA is reproducible, cannot be edited under the
# run, and leaves no untracked artifact in this worktree.  In-tree wins if the lane merged.
DIAL_INTREE = AUDIT / "board_ecology_series_v1.parquet"
DIAL_GIT_REFS = [
    "b1348fe6a320fdd2479650a6dfc13dd977adf933",      # claude/cn-limit-w1-regime-salvage @ build
    "origin/claude/cn-limit-w1-regime-salvage",
]
DIAL_GIT_PATH = "research/cn_prophet_audit/board_ecology_series_v1.parquet"

# ── frozen parameters (v0's / L1's / W2-B's unless marked NEW) ────────────────

WINDOW_START = LIMIT_TAPE_START_DATE            # 2011-01-01
WINDOW_END = pd.Timestamp("2026-08-07")         # last bar in the raw store at build time

LIMIT_CLOSE_TOL = 0.002                         # v0's adjudicated tolerance (PRIMARY)
MAX_PAIR_GAP_DAYS = 10                          # T -> T+1 within 10 calendar days
THIN_CELL_N = 20                                # cells below this n are labelled THIN
SPLIT_DATE = pd.Timestamp("2021-11-26")         # v0's computed 70/30 date, frozen

ROLL_CAP_SESSIONS = 10                          # locked-exit roll cap (L1)
ROUND_TRIP_COST = 0.0015                        # 0.10% stamp duty (sell) + ~0.025% each way

# NEW — the window target itself.
HORIZONS = (3, 5, 10)                           # sessions, measured from the close of T
CUM_THRESHOLDS = (0.8, 1.5, 2.5)                # multiples of w
BIGDAY_FRAC = 0.6                               # O1 floor, multiple of w
NEARMISS_FRAC = 0.85                            # O4 near-miss floor, multiple of w
PEAK_TRIGGER_FRAC = 1.5                         # the O3-framing book's drawup trigger

N_COHORT_CAP = 3                                # ladder cohorts are {1, 2, 3+}
N_QUINTILES = 5                                 # C12 matching bins on f3
TOP_DECILE_Q = 0.90                             # feature "top decile" cut, fit window only
REGIME_TERCILES = (1.0 / 3.0, 2.0 / 3.0)        # i5 dial cut points, fit window only

BOOK_MIN_DATES = 30                             # decision-bar floor, per window
BOOK_T_BAR = 2.0                                # decision-bar date-clustered t

CORRUPTION_CUT = pd.Timestamp("2019-01-02")     # lookahead experiment cut
CORRUPTION_SAMPLE = 40                          # tickers in the corruption experiment

ERA_BOUNDS = [
    ("e1_2011_14", 2011, 2014), ("e2_2015_mania", 2015, 2015),
    ("e3_2016_18_crackdown", 2016, 2018), ("e4_2019_21_revival", 2019, 2021),
    ("e5_2022_23_grind", 2022, 2023), ("e6_2024_26_current", 2024, 2026),
]

# v0's pre-registered feature set, SIX of the eight.  f2 (turnover ratio) needs shares
# outstanding, which this store does not carry; f5 (near-limit-prev) is this instrument's own
# population B one bar earlier and would be a near-tautology as a conditioner on it.
FEATURES = OrderedDict([
    ("f1_vol_z20", "volume z-score of the T bar vs its own prior 20 bars"),
    ("f3_runup_5", "5-session run-up: close[T] / close[T-5] - 1"),
    ("f4_sector_heat", "same-day sector limit-up count at T, leave-one-out"),
    ("f6_gap_pct", "gap at the T open: open[T] / close[T-1] - 1"),
    ("f7_dist_52w_low", "distance from the 52w low: close[T] / min(low, 252 bars) - 1"),
    ("f8_consec_up_days", "consecutive up-close days ending at T"),
])

FEATURE_TIMING_NOTE = (
    "v0's Stage-3 convention measures the feature set at T-1 and predicts the event at T. "
    "This instrument keeps that offset EXACTLY and shifts the whole frame forward by one bar: "
    "the features are read at T, the conditioning bar, and the outcome window is T+1..T+H. "
    "The feature DEFINITIONS are v0's, unchanged, evaluated at their own bar. So a feature is "
    "always measured on the last close before the first outcome bar, in both studies."
)

SIGNALS = OrderedDict([
    ("S1_f3_top_decile_x_regime_hot",
     "board day at T with f3_runup_5 in the fit-window top decile AND the i5 regime dial in "
     "the fit-window top tercile — momentum in a hot tape"),
    ("S2_first_board_N1",
     "board day at T with 连板 N == 1 — the first-board rung, the ladder's own entry"),
    ("S3_big_day_nonboard",
     "NON-board day at T whose close-to-close return is >= 0.6w — the operator's sub-limit "
     "big day, used as an ENTRY trigger rather than only as an outcome"),
    ("S4_near_miss_untouched",
     "NON-board day at T with return >= 0.85w whose HIGH never reached the limit price — the "
     "C12 population, nested inside S3 by construction"),
])

SIGNAL_NESTING_NOTE = (
    "S4 is a strict SUBSET of S3 (>= 0.85w and untouched implies >= 0.6w and non-board), and "
    "S1 is a subset of the board population S2 draws from. The four signals are NOT four "
    "independent tests and are never counted as such in the multiplicity block."
)

EXIT_NOTE = (
    "FIXED-H exit only. Entry at the open of T+1; the position is exposed over exactly the "
    "outcome window T+1..T+H and is sold at the OPEN of the next session after it (T+H+1), "
    "which is L1's E3 time stop with TIME_STOP_SESSIONS = H. No signal exit (L1's E1/E2) is "
    "run here: this lane's question is what the WINDOW contains, and a board-fail exit would "
    "answer the Wave-1 question again."
)

LOCKED_EXIT_NOTE = (
    "LOCKED-EXIT HONESTY (L1's, copied verbatim). A scheduled exit bar whose OPEN is at or "
    "below that bar's limit-down price (open <= lim_dn * (1 + 0.002)) cannot be sold at the "
    f"open — the book is one-sided. The exit rolls to the next usable bar's open, up to "
    f"{ROLL_CAP_SESSIONS} sessions; if the chain breaks or the cap is exhausted the position "
    "is closed at the last available CLOSE and flagged forced_close. Roll rate and the mean "
    "extra loss the roll cost are reported per cell."
)

FILL_CENSOR_NOTE = (
    "FILLABILITY CENSOR (L1's, copied). An entry is taken only where open[T+1] < "
    "limit_price[T+1] * (1 - 0.002). A 一字 open is refused, not modelled as a fill. The "
    "refused share is reported per signal as the entry-availability receipt, because for the "
    "board population it is exactly the continuation you cannot buy."
)

OVERLAP_CHOICE = "cluster_by_start_date"
OVERLAP_NOTE = (
    "WINDOW OVERLAP — ONE treatment, pre-registered. Windows from the same name on "
    "consecutive board days overlap; a 10-session window shares up to 9 bars with its "
    "neighbour. The two admissible treatments are (a) restrict to non-overlapping window "
    "starts or (b) keep every start and cluster the inference by START DATE. This lane "
    "chooses (b). Reason: (a) would delete the ladder — consecutive board days ARE the "
    "ladder — and the ladder is the object under study, so the non-overlapping population "
    "would answer a different question. Consequence, accepted and disclosed: every rate cell "
    "prints n, n_dates and n_names and the row n is NOT an independent-observation count; "
    "every expectancy in the book collapses to per-start-date means BEFORE any t is formed, "
    "so the reported t counts SESSIONS. An OVERLAP RECEIPT quantifies the structure (share of "
    "rows whose H=10 window overlaps another row of the same name, and the mean number of "
    "same-name overlapping starts) rather than leaving it as prose."
)

DECISION_BAR = (
    f"A (signal, H, board) cell CLEARS only if its DATE-EQUAL-WEIGHTED net expectancy (after "
    f"a {ROUND_TRIP_COST * 1e4:.0f} bp round trip) is positive AND its date-clustered t is "
    f">= {BOOK_T_BAR} in BOTH the fit and the holdout window, with n_dates >= "
    f"{BOOK_MIN_DATES} in each. Anything else is a null FOR THAT CONSTRUCTION."
)

PRE_REGISTRATION = {
    "registered_before_any_number_was_read": True,
    "decision_question": ("The T+1 auction prices tomorrow's BOARD (Wave 1/2 null). Does it "
                          "also price the WINDOW?"),
    "split": f"{SPLIT_DATE:%Y-%m-%d} — v0's computed 70/30 date, reused as a frozen constant. "
             "ONE holdout pass. Every threshold, band edge, exit rule, cost bar, cell floor "
             "and signal below was fixed before the first run.",
    "outcome_family": {
        "O1_big_day": "return[T+1] >= 0.6w AND NOT a tolerant limit-up close at T+1. The "
                      "upper edge is the tolerant limit FLAG, not a return threshold, so "
                      "big-day and board partition the >= 0.6w class exactly.",
        "O1_sibling": "P(return[T+1] >= 0.6w including boards) — printed beside O1 so the "
                      "decomposition is visible.",
        "O2_window_cum": "close[T+H]/close[T] - 1 >= theta*w, H in {3,5,10}, theta in "
                         "{0.8,1.5,2.5}.",
        "O3_window_peak": "max(high[T+1..T+H])/close[T] - 1 >= theta*w, same grid.",
        "O4_near_miss_C12": "population B (close in [0.85w, tolerant limit), high never at "
                            "the limit price) vs population A (sealed closes), matched within "
                            "(board key, split, prior ladder N cohort, f3 quintile). "
                            "Attention-vs-supply is NOT decomposed; the difference is BUNDLED "
                            "and is labelled so.",
        "entry_reference_close": "close[T] for every outcome, including the O3 drawup trigger.",
    },
    "conditioning": {
        "features": list(FEATURES),
        "timing": FEATURE_TIMING_NOTE,
        "ladder_N": "tolerant 连板 count at T (boards); for the non-board populations the "
                    "ladder is 0 by construction, so C12 matches on PRIOR N — the tolerant "
                    "board streak ending at T-1, capped at 3+ — which is the only reading "
                    "under which a near-miss and a sealed close can share a cell.",
        "regime": "i5_realized_continuation_ma5 at T (L2 board-ecology dial), tercile cuts "
                  "computed on the FIT window per raw board.",
        "era": "fit/holdout at the split date, plus the 6-era harness.",
        "cuts": "EVERY quantile cut (feature deciles, f3 quintiles, regime terciles) is "
                "computed on FIT-WINDOW rows only and applied unchanged to the holdout, and "
                "on TOLERANT-basis rows only — no strict-union population is ever pooled to "
                "form a cut.",
        "na_levels": "A row whose feature is NaN (rolling warm-up, missing sector) lands in an "
                     "explicit *_NA level flagged data_availability_slice. Those levels are "
                     "DATA-AVAILABILITY SLICES, never conditioners, and never carry a lift.",
    },
    "the_book": {
        "signals": dict(SIGNALS),
        "nesting": SIGNAL_NESTING_NOTE,
        "entry": "open of T+1, fillable only",
        "exits": EXIT_NOTE,
        "locked_exit": LOCKED_EXIT_NOTE,
        "decision_bar": DECISION_BAR,
        "o3_framing_book": (
            "Same entries. Hold to the first bar in T+1..T+H whose HIGH reaches "
            f"(1 + {PEAK_TRIGGER_FRAC}w) x close[T]; sell into (i) the BEST fillable open in "
            "the remainder of the window — an UPPER BOUND requiring foresight, a capacity "
            "measurement of what the window contains, NOT a strategy — and (ii) the FIRST "
            "open after the trigger, which is implementable and is printed beside it so the "
            "foresight premium is a number. Untriggered entries take the fixed-H exit."),
    },
    "overlap_treatment": {"choice": OVERLAP_CHOICE, "note": OVERLAP_NOTE},
    "honesty_gates": [
        "date-clustered t beside per-trade stats on every book cell; the per-trade t is never "
        "printed alone and never carries a claim",
        "row / date / name / episode denominators printed separately, never conflated",
        "no below-chance or coin-flip inference ACROSS families — multiplicity is stated "
        "per family with its expected false-positive count",
        "*_NA levels are labelled data-availability slices",
        "basis-pure cuts (tolerant only)",
        "corruption-experiment lookahead check on the conditioning arrays",
        "vintage stamp + back-adjusted store-basis note",
        "incomplete forward windows dropped from their own denominator and COUNTED",
    ],
}


# ── small helpers (v0's / L1's / W2-B's, copied) ──────────────────────────────

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
    """Per-trade return distribution. NOT an inference block — see date_clustered."""
    x = np.asarray(rets, dtype="float64")
    fin = np.isfinite(x)
    x = x[fin]
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
        "mean_net_pct": _r(100.0 * float(((1.0 + x) * (1.0 - ROUND_TRIP_COST) - 1.0).mean()), 3),
        "median_net_pct": _r(100.0 * float(np.median((1.0 + x) * (1.0 - ROUND_TRIP_COST)
                                                     - 1.0)), 3),
        "p10_pct": _r(100.0 * float(np.percentile(x, 10)), 3),
        "p90_pct": _r(100.0 * float(np.percentile(x, 90)), 3),
        "worst_pct": _r(100.0 * float(x.min()), 3),
        "best_pct": _r(100.0 * float(x.max()), 3),
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


def date_clustered(rets: np.ndarray, dates: np.ndarray) -> dict:
    """Date-clustered net expectancy — the only honest standard error for these books.

    W2-B's function, copied.  Trades are not independent: a theme wave puts dozens of names
    on one session behind one market-wide open, and this lane's overlapping windows put the
    SAME name in several rows.  Collapsing each START DATE to its own mean net return first
    makes the reported t count sessions.  The point estimate also changes meaning,
    deliberately: date-equal weighting is what a book that cannot take unlimited same-day
    positions actually earns.
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


def era_of(year: int) -> str:
    for name, lo, hi in ERA_BOUNDS:
        if lo <= year <= hi:
            return name
    return "e0_out_of_range"


# ── STAGE 0 — universe, sector map, regime dial ──────────────────────────────

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
        "caveat": ("CURRENT sector membership applied to 15 years of history — sector "
                   "reclassification is not reconstructible from this store. f4 inherits "
                   "that limitation whole (v0's caveat, unchanged)."),
    }


def _git(*args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                           timeout=60)
        return r.stdout.strip() or "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def load_regime_dial() -> tuple[pd.DataFrame | None, dict]:
    """L2's board-ecology series; i5_realized_continuation_ma5 is the regime dial.

    LOOKAHEAD CHECK, not assumed (W2-A's finding, re-verified mechanically here).  The
    producer indexes i5 by the TARGET date — the session the continuation PRINTED on — so
    i5[D] counts names that were limit-up on their previous usable bar and closed limit-up on
    D.  Every input to that number is on the tape by D's close, and ma5 is a TRAILING rolling
    mean ending at D.  The dial at T is therefore known at T's close and joining it to an
    event at T is not a lookahead.  The check below re-derives the ma5 from the raw column
    and confirms the window is trailing (a forward window would disagree).
    """
    src, path, tmp = None, None, None
    if DIAL_INTREE.exists():
        path, src = DIAL_INTREE, "in-tree (the salvage lane merged)"
    else:
        for ref in DIAL_GIT_REFS:
            try:
                r = subprocess.run(["git", "cat-file", "-p", f"{ref}:{DIAL_GIT_PATH}"],
                                   cwd=REPO, capture_output=True, timeout=120)
            except Exception:  # noqa: BLE001
                continue
            if r.returncode == 0 and r.stdout:
                tmp = Path(tempfile.mkstemp(suffix=".parquet")[1])
                tmp.write_bytes(r.stdout)
                path = tmp
                src = (f"git blob {ref}:{DIAL_GIT_PATH} — branch "
                       "claude/cn-limit-w1-regime-salvage, NOT committed by this lane and "
                       "NOT written into this worktree")
                break
    if path is None:
        return None, {"available": False,
                      "note": ("board_ecology_series_v1.parquet unreachable (not in tree and "
                               "no pinned blob) — every i5 regime cell in this file is NULL "
                               "and S1 has no regime leg. Reported, not patched.")}
    d = pd.read_parquet(path)
    if tmp is not None:
        tmp.unlink(missing_ok=True)
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
        mdf = float(np.abs(fwd.to_numpy()[bothf] - got.to_numpy()[bothf]).max()) \
            if bothf.any() else float("nan")
        checks.append({"board": str(board), "rows": int(len(g)),
                       "max_abs_diff_vs_TRAILING_ma5": _r(md, 9),
                       "max_abs_diff_vs_FORWARD_ma5": _r(mdf, 6)})
    ok = all((c["max_abs_diff_vs_TRAILING_ma5"] or 0.0) < 1e-9 for c in checks)
    return d[["date", "board", "i5_realized_continuation",
              "i5_realized_continuation_ma5", "i5_pairs_n"]], {
        "available": True,
        "source": src,
        "dial": "i5_realized_continuation_ma5, per (date, raw board)",
        "basis": ("TOLERANT — the producer's limit_up flag is v0's tolerant rule, so the dial "
                  "is a tolerant-basis conditioner applied to a tolerant-basis population."),
        "join_key": ("(date, RAW board) — the dial is produced per raw board, so ChiNext's "
                     "pre/post-2020 split keys share one dial value on a given date. The "
                     "SPLIT is enforced on the population, not on the dial."),
        "lookahead_check": {
            "claim": "the dial at T is known at T's close",
            "mechanical": checks,
            "verdict": ("PASS — reproduces the TRAILING window to float precision and "
                        "disagrees with a forward window." if ok else
                        "FAIL — the ma5 does not reproduce a trailing window; do not read "
                        "any regime cell below."),
        },
        "terciles": ("cut points computed on the FIT window only, per raw board, then applied "
                     "unchanged to the holdout."),
    }


# ── per-ticker arrays (L1's _ticker_arrays + this lane's window machinery) ────

def _ticker_arrays(df: pd.DataFrame, board: str) -> dict | None:
    """Full-history arrays for one ticker: prices, limits, exclusions, 连板, features."""
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
        ret = c / pc - 1.0

    in_win = np.asarray((idx >= WINDOW_START) & (idx <= WINDOW_END), dtype=bool)
    live = in_win & ~excl

    lu = live & np.isfinite(lim_up) & (c >= lim_up * (1.0 - LIMIT_CLOSE_TOL))
    ld = live & np.isfinite(lim_dn) & (c <= lim_dn * (1.0 + LIMIT_CLOSE_TOL))
    lianban = streak_lengths(lu)
    prior_N = np.r_[np.int32(0), lianban[:-1]]           # streak ENDING at T-1

    # the high never reached the limit price — the C12 "untouched" test
    touched = np.isfinite(h) & np.isfinite(lim_up) & (h >= lim_up * (1.0 - LIMIT_CLOSE_TOL))

    days = idx.to_numpy().astype("datetime64[D]").astype(np.int64)

    # v0's pre-registered features, evaluated at their own bar (f4 is cross-sectional and is
    # attached after the panel exists).
    s_vol = pd.Series(vol)
    base_mu = s_vol.shift(1).rolling(20, min_periods=15).mean().to_numpy()
    base_sd = s_vol.shift(1).rolling(20, min_periods=15).std(ddof=0).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = np.where(base_sd > 0, (vol - base_mu) / base_sd, np.nan)
        f3 = c / np.roll(c, 5) - 1.0
        f6 = o / pc - 1.0
        low252 = pd.Series(lo).rolling(252, min_periods=120).min().to_numpy()
        f7 = np.where(low252 > 0, c / low252 - 1.0, np.nan)
    f3[:5] = np.nan
    f8 = streak_lengths(np.r_[False, c[1:] > c[:-1]])

    return {
        "idx": idx, "o": o, "h": h, "lo": lo, "c": c, "pc": pc, "width": width,
        "lim_up": lim_up, "lim_dn": lim_dn, "live": live, "in_win": in_win,
        "lu": lu, "ld": ld, "ret": ret, "touched": touched,
        "lianban": lianban, "prior_N": prior_N, "days": days, "n": n,
        "f1": f1, "f3": f3, "f6": f6, "f7": f7, "f8": f8,
        "excl_stats": {
            "ipo_excluded": int((ipo_mask & in_win).sum()),
            "exdiv_excluded": int((exdiv & in_win).sum()),
            "zero_volume_excluded": int((zero_vol & in_win).sum()),
            "bars_in_window": int(in_win.sum()),
            "live_bars_in_window": int(live.sum()),
        },
    }


def _forward_windows(A: dict) -> dict:
    """Vectorised forward-window outcomes. No Python loop touches a price here.

    A usable successor chain is contiguous in ARRAY index (v0's pair rule makes the successor
    always i+1), so an H-session window from i is available exactly when the next H steps are
    all usable.  run_fwd[i] is the number of consecutive usable steps starting at i, computed
    by reversing v0's streak helper — the same object the entry book walks one bar at a time.
    """
    n, live, days, c, h = A["n"], A["live"], A["days"], A["c"], A["h"]
    step = np.zeros(n, dtype=bool)
    if n > 1:
        step[:-1] = live[1:] & ((days[1:] - days[:-1]) <= MAX_PAIR_GAP_DAYS)
    run_fwd = streak_lengths(step[::-1])[::-1]

    o = A["o"]
    out = {"step_ok": step, "run_fwd": run_fwd}
    for H in HORIZONS:
        with np.errstate(invalid="ignore", divide="ignore"):
            cum = np.r_[c[H:], np.full(H, np.nan)] / c - 1.0
            rm = pd.Series(h).rolling(H).max().to_numpy()
            peak = np.r_[rm[H:], np.full(H, np.nan)] / c - 1.0
            # the BENCHMARK leg: the identical trade — buy the open of T+1, sell the open of
            # T+H+1 — on every bar, so a signal's expectancy can be read against what the
            # SAME board key returned on the SAME sessions. Needs H+1 usable steps, one more
            # than the outcome window, because the exit bar sits past the window's last bar.
            oo = np.r_[o[H + 1:], np.full(H + 1, np.nan)] / np.r_[o[1:], np.nan] - 1.0
        ok = run_fwd >= H
        out[f"cum_{H}"] = np.where(ok, cum, np.nan)
        out[f"peak_{H}"] = np.where(ok, peak, np.nan)
        out[f"win_ok_{H}"] = ok
        out[f"oo_{H}"] = np.where(run_fwd >= H + 1, oo, np.nan)
    return out


ROW_COLS = ["date", "ticker", "board", "bkey", "is_board", "is_bigday", "is_nearmiss",
            "N", "prior_N", "w", "ret_T", "y_ok", "y_lu", "y_ld", "r1",
            "unfillable_open", "entry_open", "close_T",
            "o1_bigday", "o1_incl", "f1_vol_z20", "f3_runup_5", "f6_gap_pct",
            "f7_dist_52w_low", "f8_consec_up_days"]


BKEYS = ["main", "star", "chinext_10pct_pre2020", "chinext_20pct_post2020"]
BENCH_DAY0 = int(WINDOW_START.to_datetime64().astype("datetime64[D]").astype(np.int64))
BENCH_DAYS = int(WINDOW_END.to_datetime64().astype("datetime64[D]").astype(np.int64)) \
    - BENCH_DAY0 + 2


def _bkey(board: str, dates: pd.DatetimeIndex) -> np.ndarray:
    """Board key. ChiNext is NEVER pooled across the 2020-08-24 band step."""
    if board != "chinext":
        return np.full(len(dates), board, dtype=object)
    pre = dates.to_numpy() < CHINEXT_WIDE_DATE.to_datetime64()
    return np.where(pre, "chinext_10pct_pre2020", "chinext_20pct_post2020").astype(object)


def _bkey_code(board: str, idx: pd.DatetimeIndex) -> np.ndarray:
    if board == "main":
        return np.zeros(len(idx), dtype=np.int8)
    if board == "star":
        return np.ones(len(idx), dtype=np.int8)
    pre = idx.to_numpy() < CHINEXT_WIDE_DATE.to_datetime64()
    return np.where(pre, np.int8(2), np.int8(3))


def process_ticker(ticker: str, A: dict, board: str,
                   bench_acc: dict | None = None) -> tuple[pd.DataFrame | None, dict]:
    """Conditioning + outcome rows for one ticker's populations A (boards), B, C."""
    W = _forward_windows(A)
    live, lu, ld, c, o, w = A["live"], A["lu"], A["ld"], A["c"], A["o"], A["width"]
    ret, touched, lim_up = A["ret"], A["touched"], A["lim_up"]
    n = A["n"]

    nxt = lambda a, fill: np.r_[a[1:], fill]  # noqa: E731 — one-line shift, used 6x below
    y_ok = W["step_ok"]
    nxt_o, nxt_c = nxt(o, np.nan), nxt(c, np.nan)
    nxt_lu, nxt_ld = nxt(lu, False), nxt(ld, False)
    nxt_lim_up = nxt(lim_up, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        r1 = nxt_c / c - 1.0
    unfill = np.isfinite(nxt_o) & np.isfinite(nxt_lim_up) & (
        nxt_o >= nxt_lim_up * (1.0 - LIMIT_CLOSE_TOL))

    # THE BENCHMARK ACCUMULATOR — every live bar of every name whose T+1 open was fillable,
    # summed per (session, board key). This is the control the whole book is read against:
    # a positive expectancy on a board that drifted up is not an edge, it is the board.
    if bench_acc is not None:
        code = _bkey_code(board, A["idx"])
        di = A["days"] - BENCH_DAY0
        base_ok = live & ~unfill & (di >= 0) & (di < BENCH_DAYS)
        for H in HORIZONS:
            v = W[f"oo_{H}"]
            m = base_ok & np.isfinite(v)
            if not bool(m.any()):
                continue
            for kcode in range(len(BKEYS)):
                mm = m & (code == kcode)
                if not bool(mm.any()):
                    continue
                np.add.at(bench_acc["sum"][kcode][H], di[mm], v[mm])
                np.add.at(bench_acc["cnt"][kcode][H], di[mm], 1)

    is_board = live & lu
    is_bigday = live & ~lu & np.isfinite(ret) & (ret >= BIGDAY_FRAC * w)
    is_nearmiss = is_bigday & (ret >= NEARMISS_FRAC * w) & ~touched
    sel = np.where(is_board | is_bigday)[0]
    stats = {"rows_board": int(is_board.sum()), "rows_bigday": int(is_bigday.sum()),
             "rows_nearmiss": int(is_nearmiss.sum())}
    if sel.size == 0:
        return None, stats

    idx = A["idx"]
    dates = idx[sel]
    with np.errstate(invalid="ignore"):
        o1_incl = y_ok & np.isfinite(r1) & (r1 >= BIGDAY_FRAC * w)
    o1_big = o1_incl & ~nxt_lu

    frame = {
        "date": dates, "ticker": ticker, "board": board, "bkey": _bkey(board, dates),
        "is_board": is_board[sel], "is_bigday": is_bigday[sel],
        "is_nearmiss": is_nearmiss[sel],
        "N": A["lianban"][sel].astype(np.int16), "prior_N": A["prior_N"][sel].astype(np.int16),
        "w": w[sel].astype(np.float32), "ret_T": ret[sel].astype(np.float32),
        "y_ok": y_ok[sel], "y_lu": (nxt_lu & y_ok)[sel], "y_ld": (nxt_ld & y_ok)[sel],
        "r1": np.where(y_ok, r1, np.nan)[sel].astype(np.float32),
        "unfillable_open": (unfill & y_ok)[sel],
        "entry_open": nxt_o[sel].astype(np.float64),
        "close_T": c[sel].astype(np.float64),
        "o1_bigday": o1_big[sel], "o1_incl": o1_incl[sel],
        "f1_vol_z20": A["f1"][sel].astype(np.float32),
        "f3_runup_5": A["f3"][sel].astype(np.float32),
        "f6_gap_pct": A["f6"][sel].astype(np.float32),
        "f7_dist_52w_low": A["f7"][sel].astype(np.float32),
        "f8_consec_up_days": A["f8"][sel].astype(np.int16),
        "bar_i": sel.astype(np.int32),
    }
    for H in HORIZONS:
        frame[f"win_ok_{H}"] = W[f"win_ok_{H}"][sel]
        frame[f"cum_{H}"] = W[f"cum_{H}"][sel].astype(np.float32)
        frame[f"peak_{H}"] = W[f"peak_{H}"][sel].astype(np.float32)
    stats["n_bars"] = n
    return pd.DataFrame(frame), stats


# ── the entry book (L1's machinery, fixed-H only) ─────────────────────────────

TRADE_COLS = ["date", "ticker", "bkey", "signal", "H", "variant", "entry_px", "exit_px",
              "ret", "hold_sessions", "rolls", "forced_close", "roll_extra_loss",
              "triggered"]


def _make_walkers(A: dict):
    n, live, days = A["n"], A["live"], A["days"]
    o, c, lim_dn = A["o"], A["c"], A["lim_dn"]

    def usable_next(i: int) -> int:
        j = i + 1
        if j >= n or not bool(live[j]) or days[j] - days[i] > MAX_PAIR_GAP_DAYS:
            return -1
        return j

    def sellable(b: int) -> bool:
        """A bar whose OPEN is at/below the limit-down price cannot be sold into."""
        return not (bool(np.isfinite(lim_dn[b]))
                    and o[b] <= lim_dn[b] * (1.0 + LIMIT_CLOSE_TOL))

    def resolve_exit(b_sched: int, fallback_bar: int):
        """Scheduled exit bar -> realised (price, bar, rolls, forced, scheduled_open)."""
        if b_sched < 0:
            return float(c[fallback_bar]), fallback_bar, 0, True, np.nan
        sched_open = float(o[b_sched])
        rolls, b = 0, b_sched
        while not sellable(b):
            if rolls >= ROLL_CAP_SESSIONS:
                return float(c[b]), b, rolls, True, sched_open
            nb = usable_next(b)
            rolls += 1
            if nb < 0:
                return float(c[b]), b, rolls, True, sched_open
            b = nb
        return float(o[b]), b, rolls, False, sched_open

    def advance(start: int, k: int) -> tuple[int, bool]:
        cur, ok = start, True
        for _ in range(k):
            nb = usable_next(cur)
            if nb < 0:
                ok = False
                break
            cur = nb
        return cur, ok

    return usable_next, resolve_exit, advance


def book_trades(ticker: str, A: dict, rows: pd.DataFrame) -> list[tuple]:
    """Fixed-H book + the O3-framing (peak-capacity) book for one ticker's signal rows.

    `rows` carries one row per (bar, signal) already selected upstream, so the signal
    definitions live in ONE place and this function only prices them.
    """
    usable_next, resolve_exit, advance = _make_walkers(A)
    o, c, h, w = A["o"], A["c"], A["h"], A["width"]
    out = []
    for rec in rows.itertuples(index=False):
        t = int(rec.bar_i)
        e = t + 1
        entry_px = float(o[e])
        if not np.isfinite(entry_px) or entry_px <= 0:
            continue
        close_T = float(c[t])
        trig_px = close_T * (1.0 + PEAK_TRIGGER_FRAC * float(w[t]))
        for H in HORIZONS:
            # (1) fixed-H exit: hold T+1..T+H, sell the open of T+H+1 (L1's E3 with k=H)
            cur, ok = advance(e, H)
            b_sched = cur if ok else -1
            px, b_exit, rolls, forced, sched = resolve_exit(b_sched, cur)
            extra = (px / sched - 1.0) if (rolls > 0 and np.isfinite(sched) and sched > 0) \
                else np.nan
            out.append((rec.date, ticker, rec.bkey, rec.signal, H, "fixedH", entry_px, px,
                        px / entry_px - 1.0, int(b_exit - e + 1), rolls,
                        bool(forced or not ok), extra, False))

            # (2) the O3-framing book: first bar in the window whose HIGH reaches 1.5w above
            #     close[T], then sell into the best / first fillable open after it.
            j, b, steps = -1, e, 0
            while steps < H:
                if np.isfinite(h[b]) and h[b] >= trig_px:
                    j = b
                    break
                nb = usable_next(b)
                if nb < 0:
                    break
                b, steps = nb, steps + 1
            if j < 0:
                # no trigger: the peak book falls back to the fixed-H exit, same trade
                out.append((rec.date, ticker, rec.bkey, rec.signal, H, "peak_best", entry_px,
                            px, px / entry_px - 1.0, int(b_exit - e + 1), rolls,
                            bool(forced or not ok), extra, False))
                out.append((rec.date, ticker, rec.bkey, rec.signal, H, "peak_first", entry_px,
                            px, px / entry_px - 1.0, int(b_exit - e + 1), rolls,
                            bool(forced or not ok), extra, False))
                continue
            # candidate exits: opens of the bars after the trigger, out to the fixed-H exit
            # bar e+H (= T+H+1) inclusive.  The chain is contiguous in index, so the number of
            # candidate bars is exactly (e + H) - j.  Never longer: the peak book must not be
            # allowed to hold one session past the fixed-H book it is compared against.
            cands, cur2 = [], j
            remaining = H - (j - e)
            for _ in range(max(0, remaining)):
                nb = usable_next(cur2)
                if nb < 0:
                    break
                cur2 = nb
                cands.append(cur2)
            fillable = [b2 for b2 in cands if not (
                np.isfinite(A["lim_dn"][b2])
                and o[b2] <= A["lim_dn"][b2] * (1.0 + LIMIT_CLOSE_TOL))]
            if not fillable:
                fb = cands[-1] if cands else j
                out.append((rec.date, ticker, rec.bkey, rec.signal, H, "peak_best", entry_px,
                            float(c[fb]), float(c[fb]) / entry_px - 1.0, int(fb - e + 1), 0,
                            True, np.nan, True))
                out.append((rec.date, ticker, rec.bkey, rec.signal, H, "peak_first", entry_px,
                            float(c[fb]), float(c[fb]) / entry_px - 1.0, int(fb - e + 1), 0,
                            True, np.nan, True))
                continue
            b_best = max(fillable, key=lambda b2: o[b2])
            b_first = fillable[0]
            for label, b2 in (("peak_best", b_best), ("peak_first", b_first)):
                out.append((rec.date, ticker, rec.bkey, rec.signal, H, label, entry_px,
                            float(o[b2]), float(o[b2]) / entry_px - 1.0, int(b2 - e + 1), 0,
                            False, np.nan, True))
    return out


# ── panel build ───────────────────────────────────────────────────────────────

_T0 = [time.time()]


def build(verbose: bool = True):
    st_set, st_note = load_st_cohort()
    sector_map, sector_meta = load_sector_map()
    files = sorted((DATA / "china_stocks_raw").glob("*.parquet"))

    agg = {"ipo_excluded": 0, "exdiv_excluded": 0, "zero_volume_excluded": 0,
           "bars_in_window": 0, "live_bars_in_window": 0}
    uncond = {}
    boards_seen, kept, skipped_st, skipped_thin = {}, 0, 0, 0
    frames = []
    popstats = {"rows_board": 0, "rows_bigday": 0, "rows_nearmiss": 0}
    bench_acc = {
        "sum": [{H: np.zeros(BENCH_DAYS, dtype=np.float64) for H in HORIZONS}
                for _ in BKEYS],
        "cnt": [{H: np.zeros(BENCH_DAYS, dtype=np.int64) for H in HORIZONS} for _ in BKEYS],
    }

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

        # unconditional next-bar limit-up rate, accumulated as scalars (v0/L1's receipt)
        live, days = A["live"], A["days"]
        y_ok_all = np.r_[live[1:], False] & np.r_[(days[1:] - days[:-1]) <= MAX_PAIR_GAP_DAYS,
                                                  False]
        usable = live & y_ok_all
        slot = uncond.setdefault(board, [0, 0])
        slot[0] += int(usable.sum())
        slot[1] += int((usable & np.r_[A["lu"][1:], False]).sum())

        rows, st = process_ticker(ticker, A, board, bench_acc)
        for k in popstats:
            popstats[k] += st[k]
        # NOTE: `A` is deliberately NOT retained. Holding every ticker's full-history arrays
        # would cost ~2.6 GB; the entry book re-reads the parquet for the names that actually
        # carry a signal row, which is one extra pass and no memory.
        if rows is not None and len(rows):
            frames.append(rows)
        if verbose and (i + 1) % 400 == 0:
            print(f"          ... {i + 1}/{len(files)} files "
                  f"({time.time() - _T0[0]:.0f}s)", flush=True)

    bench_rows = []
    for kcode, bk in enumerate(BKEYS):
        for H in HORIZONS:
            cnt = bench_acc["cnt"][kcode][H]
            m = cnt > 0
            if not bool(m.any()):
                continue
            di = np.where(m)[0]
            bench_rows.append(pd.DataFrame({
                "date": pd.to_datetime(di + BENCH_DAY0, unit="D"),
                "bkey": bk, "H": H,
                "bench_gross": bench_acc["sum"][kcode][H][m] / cnt[m],
                "bench_names": cnt[m]}))
    bench = pd.concat(bench_rows, ignore_index=True)
    bench["bench_net"] = (1.0 + bench["bench_gross"]) * (1.0 - ROUND_TRIP_COST) - 1.0

    rows = pd.concat(frames, ignore_index=True)
    rows["sector"] = rows["ticker"].map(sector_map).fillna("UNKNOWN")
    rows["year"] = rows["date"].dt.year.astype(np.int16)
    rows["era6"] = [era_of(int(y)) for y in rows["year"].to_numpy()]
    rows["split"] = np.where(rows["date"] < SPLIT_DATE, "fit", "holdout")
    rows["Ncoh"] = np.minimum(rows["N"].to_numpy(), N_COHORT_CAP).astype(np.int8)
    rows["prior_Ncoh"] = np.minimum(rows["prior_N"].to_numpy(), N_COHORT_CAP).astype(np.int8)

    # f4 — cohort heat, LEAVE-ONE-OUT (v0's definition).  The heat map is built from the
    # BOARD rows, which are every live tolerant limit-up day in the window, so it is exactly
    # v0's per-(date, sector) limit-up count.  A board row subtracts itself; a non-board row
    # does not (it contributed nothing to the count).
    boards_only = rows[rows["is_board"]]
    heat = boards_only.groupby(["date", "sector"], observed=True).size()
    key = pd.MultiIndex.from_arrays([rows["date"], rows["sector"]])
    tot = heat.reindex(key).to_numpy(dtype="float64")
    tot = np.where(np.isfinite(tot), tot, 0.0)
    rows["f4_sector_heat"] = (tot - rows["is_board"].to_numpy().astype(np.float64)
                              ).astype(np.float32)
    rows.loc[rows["sector"] == "UNKNOWN", "f4_sector_heat"] = np.nan

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
                100.0 * len(zt_names & raw_names) / max(1, len(zt_names)), 1)})

    meta = {
        "raw_store": ("data/china_stocks_raw — v0's and L1's basis. L1's price_basis_audit "
                      "measured this store as BACK-ADJUSTED, not nominal as v0's header says: "
                      "closes sit on the 0.01 tick from each name's last corporate action "
                      "forward and are scaled before it. Adjustment PRESERVES returns, so "
                      "every return, gap, cumulative window and drawup in this file is "
                      "unaffected; only the round-to-tick step in the limit PRICE is, and "
                      "v0's 0.002 tolerance is the cushion that absorbs it."),
        "files_found": len(files), "tickers_kept": kept,
        "tickers_skipped_st": skipped_st,
        "tickers_skipped_thin_or_unreadable": skipped_thin,
        "board_counts": boards_seen, "st_cohort": st_note, "sector_map": sector_meta,
        "window": [WINDOW_START.strftime("%Y-%m-%d"), WINDOW_END.strftime("%Y-%m-%d")],
        "excluded_bars": agg, "universe_gap": gapmeta,
        "returned": "rows only — per-ticker arrays are rebuilt on demand by the book pass",
        "population_rows": {
            "A_board_days": popstats["rows_board"],
            "C_big_day_nonboard": popstats["rows_bigday"],
            "B_near_miss_untouched": popstats["rows_nearmiss"],
            "note": "B is a strict subset of C. Rows kept = A union C.",
        },
        "unconditional_next_bar_limit_up": {
            b: {"usable_ticker_days": int(v[0]), "next_bar_limit_up": int(v[1]),
                "rate_pct": _r(100.0 * v[1] / v[0]) if v[0] else None}
            for b, v in sorted(uncond.items())},
        "bkey_note": ("ChiNext is split at 2020-08-24 (CHINEXT_WIDE_DATE) into "
                      "chinext_10pct_pre2020 / chinext_20pct_post2020 and is never pooled "
                      "across the band step. The raw board label survives only in the v0 "
                      "parity gate, which must reproduce v0's published pooled ladder."),
    }
    return rows, bench, meta


# ── v0 parity gate ────────────────────────────────────────────────────────────

V0_PUBLISHED_LADDER = {
    "main":    {1: (38290, 16.50), 2: (6257, 36.61), 3: (2254, 45.52),
                4: (1019, 54.37), 5: (547, 66.91), 6: (360, 72.78)},
    "chinext": {1: (6587, 16.76), 2: (1094, 39.12), 3: (423, 52.48),
                4: (219, 63.47), 5: (137, 78.83), 6: (105, 76.19)},
    "star":    {1: (773, 10.09), 2: (77, 12.99), 3: (10, 50.00)},
}
V0_PUBLISHED_UNCONDITIONAL = {"main": 1.27, "chinext": 1.14, "star": 0.32}
V0_PARITY_RATE_TOL_PP = 0.02


def v0_ladder_parity(rows: pd.DataFrame, meta: dict) -> dict:
    """Re-derive v0's Stage-2 ladder and pin it against v0's PUBLISHED numbers.

    The only check that this instrument stands on the same panel the adjudicated v0 study
    stood on.  Uses the RAW board label deliberately — v0 pooled ChiNext across the band
    step, and a parity gate must reproduce the reference, not improve it.
    """
    u = rows[rows["is_board"] & rows["y_ok"]]
    out, worst_rate, worst_n = [], 0.0, 0
    for board, cells in V0_PUBLISHED_LADDER.items():
        g = u[u["board"] == board]
        for N, (pub_n, pub_rate) in sorted(cells.items()):
            cell = g[g["N"] == N]
            n, k = len(cell), int(cell["y_lu"].sum())
            rate = 100.0 * k / n if n else float("nan")
            d_rate = abs(rate - pub_rate) if n else float("nan")
            out.append({"board": board, "N": N, "published_n": pub_n, "measured_n": n,
                        "delta_n": n - pub_n, "published_rate_pct": pub_rate,
                        "measured_rate_pct": _r(rate), "delta_rate_pp": _r(d_rate, 4),
                        "match": bool(n == pub_n and np.isfinite(d_rate)
                                      and d_rate <= V0_PARITY_RATE_TOL_PP)})
            if np.isfinite(d_rate):
                worst_rate = max(worst_rate, d_rate)
            worst_n = max(worst_n, abs(n - pub_n))
    unc = [{"board": b, "published_rate_pct": p,
            "measured_rate_pct": meta["unconditional_next_bar_limit_up"].get(b, {})
            .get("rate_pct")}
           for b, p in V0_PUBLISHED_UNCONDITIONAL.items()]
    return {
        "reference": ("research/cn_prophet_audit/LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.md "
                      "STAGE 2 (branch claude/cn-limit-footprint-v0)"),
        "cells": out, "cells_matched": int(sum(1 for r in out if r["match"])),
        "cells_total": len(out), "max_abs_delta_n": int(worst_n),
        "max_abs_delta_rate_pp": _r(worst_rate, 4), "unconditional": unc,
        "verdict": ("PASS — every published ladder cell reproduced exactly (n) and to "
                    "published precision (rate)." if all(r["match"] for r in out) else
                    "MISMATCH — see cells; do not read anything below until resolved."),
    }


# ── the corruption experiment (lookahead check on the conditioning arrays) ────

def corruption_experiment(files: list[Path], st_set: frozenset[str]) -> dict:
    """Corrupt every bar AFTER a cut, recompute, assert the pre-cut arrays are identical.

    A conditioning array that reads the future cannot survive this: if any feature, streak or
    trigger flag at a bar <= the cut moves when bars after the cut are replaced with garbage,
    it was looking forward.  Equality is asserted BITWISE on the float arrays (np.array_equal
    with equal_nan), not to a tolerance — a lookahead does not produce a small error.
    """
    picks = [p for p in files if p.stem not in st_set]
    step = max(1, len(picks) // CORRUPTION_SAMPLE)
    picks = picks[::step][:CORRUPTION_SAMPLE]
    # The three population flags are not compared directly — they are pure functions of
    # (live, lu, ret, touched, width), and width is a date-only lookup — so those FIVE inputs
    # are what the experiment pins.  Naming them honestly is the point: a receipt that claims
    # to have tested `is_nearmiss` when it tested `touched` is the kind of thing this file
    # exists to avoid.
    checked = {k: 0 for k in ("f1_vol_z20", "f3_runup_5", "f6_gap_pct", "f7_dist_52w_low",
                              "f8_consec_up_days", "lianban", "prior_N",
                              "live_mask", "lu_flag__drives_is_board", "ret__drives_is_bigday",
                              "touched__drives_is_nearmiss", "width")}
    mismatches, names = [], 0
    rng = np.random.default_rng(20260809)
    for p in picks:
        board = _board_from_ticker(p.stem)
        df = pd.read_parquet(p).sort_index()
        A = _ticker_arrays(df, board)
        if A is None:
            continue
        idx = pd.to_datetime(df.index)
        after = np.asarray(idx > CORRUPTION_CUT)
        if not after.any() or bool(after.all()):
            continue
        bad = df.copy()
        mult = rng.uniform(2.0, 9.0, size=int(after.sum()))
        for col in ("open", "high", "low", "close"):
            bad.loc[after, col] = bad.loc[after, col].to_numpy() * mult
        bad.loc[after, "volume"] = bad.loc[after, "volume"].to_numpy() * 37.0 + 11.0
        B = _ticker_arrays(bad, board)
        pre = ~after
        names += 1

        def cmp(name, a, b):
            ok = np.array_equal(np.asarray(a)[pre], np.asarray(b)[pre], equal_nan=True) \
                if np.asarray(a).dtype.kind == "f" else \
                np.array_equal(np.asarray(a)[pre], np.asarray(b)[pre])
            checked[name] += int(pre.sum())
            if not ok and len(mismatches) < 5:
                mismatches.append({"ticker": p.stem, "array": name})

        for f, key in (("f1", "f1_vol_z20"), ("f3", "f3_runup_5"), ("f6", "f6_gap_pct"),
                       ("f7", "f7_dist_52w_low"), ("f8", "f8_consec_up_days")):
            cmp(key, A[f], B[f])
        cmp("lianban", A["lianban"], B["lianban"])
        cmp("prior_N", A["prior_N"], B["prior_N"])
        for key, arr in (("live_mask", "live"), ("lu_flag__drives_is_board", "lu"),
                         ("ret__drives_is_bigday", "ret"),
                         ("touched__drives_is_nearmiss", "touched"), ("width", "width")):
            cmp(key, A[arr], B[arr])
    return {
        "design": ("Every bar strictly after "
                   f"{CORRUPTION_CUT:%Y-%m-%d} is replaced with garbage (OHLC x U(2,9), "
                   "volume x37+11) and the conditioning arrays are recomputed. Values at bars "
                   "<= the cut must be BITWISE identical (np.array_equal, equal_nan). "
                   "A tolerance is not used: a lookahead is not a rounding error."),
        "tickers_tested": names, "values_compared": checked,
        "mismatches": mismatches,
        "flag_note": ("is_board / is_bigday / is_nearmiss are pure functions of "
                      "(live, lu, ret, touched, width); those five inputs are what is pinned, "
                      "which is why they are named that way above."),
        "verdict": ("PASS — no conditioning array at or before the cut moved when the future "
                    "was destroyed." if not mismatches else
                    "FAIL — a conditioning array reads forward; see mismatches."),
        "f4_note": ("f4_sector_heat is cross-sectional and cannot be tested per ticker. It is "
                    "covered by the separate same-date check in "
                    "lookahead_checks.f4_date_locality, which drops every row after the cut "
                    "from the panel and re-derives the heat map."),
        "i5_note": ("The i5 regime dial's trailing-window property is checked mechanically in "
                    "regime_dial.lookahead_check (W2-B's check, re-run here)."),
    }


def f4_date_locality(rows: pd.DataFrame) -> dict:
    """f4 is a same-date groupby, so dropping the future must not move a past value."""
    pre = rows[rows["date"] <= CORRUPTION_CUT]
    b = pre[pre["is_board"]]
    heat = b.groupby(["date", "sector"], observed=True).size()
    key = pd.MultiIndex.from_arrays([pre["date"], pre["sector"]])
    tot = heat.reindex(key).to_numpy(dtype="float64")
    tot = np.where(np.isfinite(tot), tot, 0.0)
    recomputed = (tot - pre["is_board"].to_numpy().astype(np.float64)).astype(np.float32)
    recomputed = np.where(pre["sector"].to_numpy() == "UNKNOWN", np.nan, recomputed)
    got = pre["f4_sector_heat"].to_numpy()
    ok = np.array_equal(recomputed, got, equal_nan=True)
    return {"rows_compared": int(len(pre)),
            "identical_after_dropping_every_bar_after_the_cut": bool(ok),
            "verdict": "PASS" if ok else "FAIL — f4 is not date-local"}


# ── outcome tables ────────────────────────────────────────────────────────────

def _outcome_cells(g: pd.DataFrame) -> dict:
    """Every outcome class for one population slice, each with its OWN denominator."""
    out = {}
    u = g[g["y_ok"]]
    out["P_board_T1"] = rate_block(int(u["y_lu"].sum()), len(u))
    out["O1_big_day_nonboard"] = rate_block(int(u["o1_bigday"].sum()), len(u))
    out["O1_incl_boards"] = rate_block(int(u["o1_incl"].sum()), len(u))
    out["P_limit_down_T1"] = rate_block(int(u["y_ld"].sum()), len(u))
    for H in HORIZONS:
        ok = g[g[f"win_ok_{H}"]]
        w = ok["w"].to_numpy(dtype="float64")
        cum = ok[f"cum_{H}"].to_numpy(dtype="float64")
        peak = ok[f"peak_{H}"].to_numpy(dtype="float64")
        for th in CUM_THRESHOLDS:
            out[f"O2_cum_H{H}_{th:g}w"] = rate_block(int((cum >= th * w).sum()), len(ok))
            out[f"O3_peak_H{H}_{th:g}w"] = rate_block(int((peak >= th * w).sum()), len(ok))
        out[f"window_H{H}_truncated_rows"] = int(len(g) - len(ok))
        if len(ok):
            out[f"median_cum_H{H}_in_w"] = _r(float(np.median(cum / w)), 3)
            out[f"median_peak_H{H}_in_w"] = _r(float(np.median(peak / w)), 3)
    out["n_rows"] = int(len(g))
    out["n_dates"] = int(g["date"].nunique())
    out["n_names"] = int(g["ticker"].nunique())
    return out


def _fit_cut(series: pd.Series, split: pd.Series, q: float) -> float:
    v = series[(split == "fit").to_numpy()].dropna()
    return float(v.quantile(q)) if len(v) else float("nan")


def attach_conditioners(rows: pd.DataFrame, dial: pd.DataFrame | None) -> dict:
    """Feature top-decile flags + regime terciles, all cut on the FIT window only."""
    receipt = {"top_decile_q": TOP_DECILE_Q, "cuts": [], "regime": {}}
    for feat in FEATURES:
        col = f"{feat}__lvl"
        rows[col] = "mid_or_low"
        for bk, g in rows.groupby("bkey", sort=True):
            cut = _fit_cut(g[feat], g["split"], TOP_DECILE_Q)
            m = g.index[(g[feat].to_numpy() >= cut) if np.isfinite(cut)
                        else np.zeros(len(g), dtype=bool)]
            rows.loc[m, col] = "top_decile"
            na = g.index[~np.isfinite(g[feat].to_numpy(dtype="float64"))]
            rows.loc[na, col] = f"{feat}_NA"
            gg = rows.loc[g.index, col]
            receipt["cuts"].append({
                "feature": feat, "bkey": bk, "fit_cut_value": _r(cut, 6),
                "realised_top_decile_share_pct": _r(100.0 * float((gg == "top_decile").mean())),
                "NA_share_pct": _r(100.0 * float((gg == f"{feat}_NA").mean())),
                "tie_note": ("share can exceed 10% when the feature is heavily tied at the "
                             "cut (v0's value-quantile correction: ties share a bucket rather "
                             "than being split across quantiles)"),
            })
    rows["regime_lvl"] = "regime_NA"
    if dial is not None:
        d = dial.rename(columns={"i5_realized_continuation_ma5": "i5"})
        # one row per (date, board) or the left join would DUPLICATE panel rows silently
        d = d.drop_duplicates(subset=["date", "board"], keep="first")
        merged = rows.merge(d[["date", "board", "i5"]], on=["date", "board"], how="left")
        assert len(merged) == len(rows), "regime dial join changed the row count"
        rows["i5"] = merged["i5"].to_numpy()
        for b, g in rows.groupby("board", sort=True):
            fit = g.loc[(g["split"] == "fit").to_numpy(), "i5"].dropna()
            if len(fit) < 100:
                continue
            lo, hi = float(fit.quantile(REGIME_TERCILES[0])), float(fit.quantile(
                REGIME_TERCILES[1]))
            v = g["i5"].to_numpy(dtype="float64")
            lvl = np.where(~np.isfinite(v), "regime_NA",
                           np.where(v <= lo, "regime_cold",
                                    np.where(v <= hi, "regime_mid", "regime_hot")))
            rows.loc[g.index, "regime_lvl"] = lvl
            receipt["regime"][b] = {
                "fit_tercile_cuts": [_r(lo, 5), _r(hi, 5)],
                "NA_share_pct": _r(100.0 * float((lvl == "regime_NA").mean())),
            }
    receipt["NA_note"] = ("Every *_NA level is a DATA-AVAILABILITY SLICE (rolling warm-up, "
                          "missing sector map, dial not yet warm), never a conditioner. No "
                          "lift is ever computed against an NA level.")
    return receipt


def outcome_tables(rows: pd.DataFrame) -> dict:
    """P(outcome) by ladder N / feature top decile / regime / era, per board key, fit vs holdout."""
    res = {"population": "A — every live tolerant limit-up close (board day) at T",
           "by_ladder_N": [], "by_feature": [], "by_regime": [], "by_era6": []}
    A = rows[rows["is_board"]]
    for bk, gb in A.groupby("bkey", sort=True):
        for split in ("fit", "holdout"):
            g = gb[gb["split"] == split]
            if not len(g):
                continue
            rec = {"bkey": bk, "split": split, "level": "ALL"}
            rec.update(_outcome_cells(g))
            res["by_ladder_N"].append(rec)
            for Nc in sorted(g["Ncoh"].unique().tolist()):
                cell = g[g["Ncoh"] == Nc]
                rec = {"bkey": bk, "split": split,
                       "level": f"N={Nc}+" if Nc == N_COHORT_CAP else f"N={Nc}"}
                rec.update(_outcome_cells(cell))
                res["by_ladder_N"].append(rec)
            for feat in FEATURES:
                for lvl, cell in g.groupby(f"{feat}__lvl", sort=True):
                    rec = {"bkey": bk, "split": split, "feature": feat, "level": lvl,
                           "data_availability_slice": bool(lvl.endswith("_NA"))}
                    rec.update(_outcome_cells(cell))
                    res["by_feature"].append(rec)
            for lvl, cell in g.groupby("regime_lvl", sort=True):
                rec = {"bkey": bk, "split": split, "level": lvl,
                       "data_availability_slice": bool(lvl == "regime_NA")}
                rec.update(_outcome_cells(cell))
                res["by_regime"].append(rec)
        for e6, cell in gb.groupby("era6", sort=True):
            rec = {"bkey": bk, "era": e6}
            rec.update(_outcome_cells(cell))
            res["by_era6"].append(rec)
    return res


HEADLINE_OUTCOMES = ["P_board_T1", "O1_big_day_nonboard", "O2_cum_H5_1.5w",
                     "O3_peak_H5_1.5w", "O2_cum_H10_2.5w", "O3_peak_H10_2.5w"]


def feature_lift(res: dict) -> dict:
    """Top-decile lift, board outcome vs window outcomes, fit AND holdout, side by side.

    The comparison the lane exists to make: the SAME feature, the SAME rows, the SAME cut —
    does it rank the board better than it ranks the buyable window, or the other way round?
    A feature whose holdout lift disagrees in SIGN with its fit lift is printed UNSTABLE and
    is never averaged (v0's rule, kept).
    """
    idx = {}
    for r in res["by_feature"]:
        idx[(r["bkey"], r["split"], r.get("feature"), r["level"])] = r
    out = []
    bkeys = sorted({r["bkey"] for r in res["by_feature"]})
    for bk in bkeys:
        for feat in FEATURES:
            rec = {"bkey": bk, "feature": feat}
            stable = {}
            for oc in HEADLINE_OUTCOMES:
                lifts = {}
                for split in ("fit", "holdout"):
                    top = idx.get((bk, split, feat, "top_decile"))
                    rest = idx.get((bk, split, feat, "mid_or_low"))
                    if not top or not rest:
                        continue
                    tr, rr = top[oc]["rate_pct"], rest[oc]["rate_pct"]
                    lifts[split] = {
                        "top_rate_pct": tr, "rest_rate_pct": rr,
                        "lift_x": _r(tr / rr, 3) if (tr is not None and rr) else None,
                        "top_n": top[oc]["n"], "rest_n": rest[oc]["n"],
                    }
                if lifts:
                    f = (lifts.get("fit") or {}).get("lift_x")
                    h = (lifts.get("holdout") or {}).get("lift_x")
                    lifts["stable_sign"] = bool(
                        f is not None and h is not None and (f - 1.0) * (h - 1.0) > 0)
                    stable[oc] = lifts
            rec["outcomes"] = stable
            out.append(rec)
    return {
        "definition": ("lift_x = P(outcome | feature in the fit-window top decile) / "
                       "P(outcome | rest). NA levels are excluded from both legs."),
        "reading": ("The decision comparison: a lift that is large for P_board_T1 and ~1 for "
                    "O1/O2 says the feature ranks the unbuyable spike and nothing else."),
        "rows": out,
    }


def o3_minus_o2(res: dict) -> dict:
    """How much of the window lives in a peak you cannot schedule."""
    out = []
    for r in res["by_ladder_N"]:
        if r["level"] != "ALL":
            continue
        rec = {"bkey": r["bkey"], "split": r["split"]}
        for H in HORIZONS:
            for th in CUM_THRESHOLDS:
                a = r[f"O3_peak_H{H}_{th:g}w"]["rate_pct"]
                b = r[f"O2_cum_H{H}_{th:g}w"]["rate_pct"]
                rec[f"H{H}_{th:g}w"] = {
                    "peak_pct": a, "close_pct": b,
                    "gap_pp": _r(a - b) if (a is not None and b is not None) else None,
                    "close_share_of_peak_pct": _r(100.0 * b / a) if (a and b is not None)
                    else None,
                }
        out.append(rec)
    return {
        "definition": ("O3 counts windows whose max HIGH reached theta*w above close[T]; O2 "
                       "counts windows whose CLOSE at T+H was still there. The gap is the "
                       "share of qualifying windows that gave the move back before the "
                       "scheduled exit — the part of a rerating window that is a peak, not a "
                       "level."),
        "rows": out,
    }


# ── C12 — the near-miss matched comparison ───────────────────────────────────

C12_OUTCOMES = ["P_board_T1", "O1_big_day_nonboard", "O1_incl_boards", "P_limit_down_T1",
                "O2_cum_H5_0.8w", "O2_cum_H5_1.5w", "O2_cum_H5_2.5w",
                "O3_peak_H5_0.8w", "O3_peak_H5_1.5w", "O3_peak_H5_2.5w"]


def c12_matched(rows: pd.DataFrame) -> dict:
    """Near-miss (untouched) vs sealed close, matched on (bkey, split, prior N, f3 quintile).

    NOT a decomposition.  A near-miss and a seal differ in attention AND in supply at the
    limit AND in whatever made one of them stop short; this compares the BUNDLE.  The
    standardised column re-weights the sealed population to the near-miss population's own
    cell distribution, which is the whole content of "matched" here.
    """
    pop = rows[rows["is_board"] | rows["is_nearmiss"]].copy()
    pop["pop"] = np.where(pop["is_board"].to_numpy(), "A_sealed", "B_near_miss_untouched")
    # f3 quintile edges: FIT window, per bkey, on the POOLED matched population so both arms
    # are binned by identical edges (a per-arm cut would make the cells non-comparable).
    pop["f3_q"] = "f3_NA"
    edges = []
    for bk, g in pop.groupby("bkey", sort=True):
        fit = g.loc[(g["split"] == "fit").to_numpy(), "f3_runup_5"].dropna()
        if len(fit) < 200:
            continue
        qs = [float(fit.quantile(q)) for q in (0.2, 0.4, 0.6, 0.8)]
        v = g["f3_runup_5"].to_numpy(dtype="float64")
        lab = np.full(len(g), "f3_NA", dtype=object)
        fin = np.isfinite(v)
        lab[fin] = np.digitize(v[fin], qs).astype(str)
        pop.loc[g.index, "f3_q"] = lab
        edges.append({"bkey": bk, "fit_quintile_edges": [_r(x, 5) for x in qs]})

    rows_out, agg = [], []
    for (bk, split), g in pop.groupby(["bkey", "split"], sort=True):
        gb = g[g["f3_q"] != "f3_NA"]
        cells = gb.groupby(["prior_Ncoh", "f3_q"], sort=True)
        weights, per_cell = {}, {}
        for cellkey, cg in cells:
            a = cg[cg["pop"] == "A_sealed"]
            b = cg[cg["pop"] == "B_near_miss_untouched"]
            if not len(a) or not len(b):
                continue
            weights[cellkey] = len(b)
            per_cell[cellkey] = (_outcome_cells(a), _outcome_cells(b), len(a), len(b))
        tot_w = sum(weights.values())
        rec = {"bkey": bk, "split": split, "matched_cells": len(per_cell),
               "near_miss_rows_in_support": tot_w,
               "near_miss_rows_total": int((gb["pop"] == "B_near_miss_untouched").sum()),
               "sealed_rows_in_support": int(sum(v[2] for v in per_cell.values())),
               "outcomes": {}}
        for oc in C12_OUTCOMES:
            num_a = num_b = 0.0
            wsum = 0.0
            for ck, (ca, cb, _na, _nb) in per_cell.items():
                ra, rb = ca[oc]["rate_pct"], cb[oc]["rate_pct"]
                if ra is None or rb is None:
                    continue
                wgt = weights[ck]
                num_a += wgt * ra
                num_b += wgt * rb
                wsum += wgt
            if wsum <= 0:
                continue
            a_std, b_std = num_a / wsum, num_b / wsum
            rec["outcomes"][oc] = {
                "near_miss_pct": _r(b_std), "sealed_standardised_pct": _r(a_std),
                "delta_pp": _r(b_std - a_std),
                "ratio_x": _r(b_std / a_std, 3) if a_std else None,
                "weight_rows": int(wsum),
            }
        agg.append(rec)
        for ck, (ca, cb, na, nb) in sorted(per_cell.items(), key=lambda kv: str(kv[0])):
            rows_out.append({
                "bkey": bk, "split": split, "prior_N": int(ck[0]), "f3_quintile": ck[1],
                "n_sealed": na, "n_near_miss": nb,
                "thin": bool(min(na, nb) < THIN_CELL_N),
                "near_miss": {oc: cb[oc]["rate_pct"] for oc in C12_OUTCOMES},
                "sealed": {oc: ca[oc]["rate_pct"] for oc in C12_OUTCOMES},
            })
    return {
        "definition": {
            "population_B": ("close[T]/close[T-1] - 1 >= 0.85w AND high[T] < "
                             "limit_price[T]*(1-0.002) — a big day that NEVER touched the "
                             "board. The untouched test is what makes this a discontinuity "
                             "probe rather than a failed-seal study; the failed-seal cohort "
                             "is W2-B's and is deliberately not duplicated here."),
            "population_A": "every live tolerant limit-up close (the seal).",
            "matching": ("exact cells on (bkey, split, prior ladder N cohort, f3 quintile). "
                         "prior N — the tolerant board streak ending at T-1 — is used because "
                         "a near-miss has no ladder of its own; matching on the event-day N "
                         "would have no overlapping support at all. Quintile edges are cut on "
                         "the FIT window of the POOLED matched population, per bkey, so both "
                         "arms share identical edges."),
            "standardisation": ("the sealed arm is re-weighted to the near-miss arm's own cell "
                                "distribution; cells where either arm is empty are dropped "
                                "from both and the surviving support is printed."),
            "NOT_claimed": ("This is a BUNDLED difference. Attention, supply at the limit, "
                            "and whatever stopped the name short are not separated and this "
                            "lane does not claim to separate them."),
        },
        "f3_quintile_edges": edges,
        "standardised": agg,
        "per_cell": rows_out,
    }


# ── the book ──────────────────────────────────────────────────────────────────

def select_signal_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per (bar, signal). The signal definitions live HERE and nowhere else."""
    out = []
    base = rows[rows["y_ok"] & ~rows["unfillable_open"]]
    s1 = base[base["is_board"] & (base["f3_runup_5__lvl"] == "top_decile")
              & (base["regime_lvl"] == "regime_hot")].copy()
    s1["signal"] = "S1_f3_top_decile_x_regime_hot"
    out.append(s1)
    s2 = base[base["is_board"] & (base["N"] == 1)].copy()
    s2["signal"] = "S2_first_board_N1"
    out.append(s2)
    s3 = base[base["is_bigday"]].copy()
    s3["signal"] = "S3_big_day_nonboard"
    out.append(s3)
    s4 = base[base["is_nearmiss"]].copy()
    s4["signal"] = "S4_near_miss_untouched"
    out.append(s4)
    return pd.concat(out, ignore_index=True)


def entry_availability(rows: pd.DataFrame) -> dict:
    """How many of each signal's days offered a fillable T+1 open at all (L1's receipt)."""
    out = []
    defs = {
        "S1_f3_top_decile_x_regime_hot": lambda d: d["is_board"] & (
            d["f3_runup_5__lvl"] == "top_decile") & (d["regime_lvl"] == "regime_hot"),
        "S2_first_board_N1": lambda d: d["is_board"] & (d["N"] == 1),
        "S3_big_day_nonboard": lambda d: d["is_bigday"],
        "S4_near_miss_untouched": lambda d: d["is_nearmiss"],
    }
    u = rows[rows["y_ok"]]
    for sig, fn in defs.items():
        g = u[fn(u).to_numpy()]
        for bk, gb in g.groupby("bkey", sort=True):
            out.append({
                "signal": sig, "bkey": bk, "signal_days": len(gb),
                "fillable_T1_open": int((~gb["unfillable_open"]).sum()),
                "entry_availability_pct": _r(100.0 * float((~gb["unfillable_open"]).mean())),
                "refused_unfillable": int(gb["unfillable_open"].sum()),
                "n_dates": int(gb["date"].nunique()), "n_names": int(gb["ticker"].nunique()),
            })
    return {"note": FILL_CENSOR_NOTE, "rows": out}


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
    if bool(g["triggered"].any()):
        out["peak_trigger_rate_pct"] = _r(100.0 * float(g["triggered"].mean()))
    return out


BENCH_NOTE = (
    "THE BENCHMARK LEG (an addition by this lane, beyond the brief's letter, disclosed as "
    "such). A positive expectancy is not an edge if the board it was earned on drifted up. "
    "The control is the IDENTICAL trade — buy the open of T+1, sell the open of T+H+1, same "
    "fillability censor — taken on EVERY live name of the SAME board key, aggregated per "
    "session. excess_net is the date-equal-weighted (signal mean net - universe mean net) on "
    "the sessions the signal actually fired, and excess_t is its date-clustered t. It is "
    "computed ONLY for the fixedH variant, where the holding bars are exactly the benchmark's; "
    "the peak variants exit early by construction and have no bar-matched control, so theirs "
    "is left null rather than approximated."
)


def bench_excess(g: pd.DataFrame, bench: pd.DataFrame, H: int, bkey: str) -> dict:
    """Date-clustered excess of one book cell over the same-session universe return."""
    b = bench[(bench["H"] == H) & (bench["bkey"] == bkey)].set_index("date")["bench_net"]
    x = g["ret"].to_numpy(dtype="float64")
    fin = np.isfinite(x)
    if not fin.any():
        return {}
    net = (1.0 + x[fin]) * (1.0 - ROUND_TRIP_COST) - 1.0
    dm = pd.Series(net).groupby(np.asarray(g["date"])[fin]).mean()
    bm = b.reindex(dm.index)
    ok = bm.notna().to_numpy()
    if ok.sum() < 2:
        return {"excess_dates": int(ok.sum())}
    ex = dm.to_numpy()[ok] - bm.to_numpy()[ok]
    se = float(ex.std(ddof=1)) / np.sqrt(ex.size)
    return {
        "excess_dates": int(ex.size),
        "bench_net_pct_on_signal_dates": _r(100.0 * float(bm.to_numpy()[ok].mean()), 3),
        "excess_net_pct": _r(100.0 * float(ex.mean()), 3),
        "excess_t": _r(float(ex.mean()) / se, 2) if se > 0 else None,
        "dates_missing_benchmark": int((~ok).sum()),
    }


def the_book(trades: pd.DataFrame, bench: pd.DataFrame) -> dict:
    res = {"entry": FILL_CENSOR_NOTE, "exits": EXIT_NOTE, "locked_exit": LOCKED_EXIT_NOTE,
           "decision_bar": DECISION_BAR, "overlap": OVERLAP_NOTE,
           "cost_note": (f"Headline per-trade stats are gross; mean_net_pct and every "
                         f"date-clustered number apply a flat "
                         f"{ROUND_TRIP_COST * 1e4:.0f} bp round trip. SLIPPAGE IS NOT "
                         f"MODELLED — fills are assumed at the printed open, which is "
                         f"optimistic for exactly these names."),
           "rows": [], "verdict": {}}
    res["benchmark"] = BENCH_NOTE
    for (sig, H, var, bk, split), g in trades.groupby(
            ["signal", "H", "variant", "bkey", "split"], sort=True):
        rec = {"signal": sig, "H": int(H), "variant": var, "bkey": bk, "split": split}
        rec.update(_book_cell(g))
        if var == "fixedH":
            rec.update(bench_excess(g, bench, int(H), bk))
        res["rows"].append(rec)
    # the decision bar, applied
    idx = {(r["signal"], r["H"], r["variant"], r["bkey"], r["split"]): r for r in res["rows"]}
    clears = []
    for (sig, H, var, bk, split) in list(idx):
        if split != "fit":
            continue
        f = idx[(sig, H, var, bk, "fit")]
        h = idx.get((sig, H, var, bk, "holdout"))
        if h is None:
            continue
        okf = (f.get("date_eq_weight_net_pct") or -1) > 0 and \
              (f.get("date_clustered_t") or -9) >= BOOK_T_BAR and \
              f.get("n_dates", 0) >= BOOK_MIN_DATES
        okh = (h.get("date_eq_weight_net_pct") or -1) > 0 and \
              (h.get("date_clustered_t") or -9) >= BOOK_T_BAR and \
              h.get("n_dates", 0) >= BOOK_MIN_DATES
        exf, exh = f.get("excess_net_pct"), h.get("excess_net_pct")
        eft, eht = f.get("excess_t"), h.get("excess_t")
        clears.append({"signal": sig, "H": int(H), "variant": var, "bkey": bk,
                       "fit_net_pct": f.get("date_eq_weight_net_pct"),
                       "fit_t": f.get("date_clustered_t"), "fit_dates": f.get("n_dates"),
                       "fit_mean_per_trade_net_pct": f.get("mean_net_pct"),
                       "holdout_net_pct": h.get("date_eq_weight_net_pct"),
                       "holdout_t": h.get("date_clustered_t"),
                       "holdout_dates": h.get("n_dates"),
                       "holdout_mean_per_trade_net_pct": h.get("mean_net_pct"),
                       "fit_excess_net_pct": exf, "fit_excess_t": eft,
                       "holdout_excess_net_pct": exh, "holdout_excess_t": eht,
                       "CLEARS": bool(okf and okh),
                       "CLEARS_vs_BENCHMARK": bool(
                           okf and okh and exf is not None and exh is not None
                           and exf > 0 and exh > 0 and (eft or -9) >= BOOK_T_BAR
                           and (eht or -9) >= BOOK_T_BAR),
                       "positive_on_BOTH_weightings": bool(
                           okf and okh
                           and (f.get("mean_net_pct") or -1) > 0
                           and (h.get("mean_net_pct") or -1) > 0)})
    res["verdict"] = {
        "cells_evaluated": len(clears),
        "cells_clearing": int(sum(1 for c in clears if c["CLEARS"])),
        "cells_clearing_vs_benchmark": int(sum(1 for c in clears
                                               if c["CLEARS_vs_BENCHMARK"])),
        "post_hoc_disclosure": (
            "CLEARS is the PRE-REGISTERED bar and is reported unchanged. "
            "CLEARS_vs_BENCHMARK and positive_on_BOTH_weightings are POST-HOC controls added "
            "AFTER the first run, when the pre-registered bar admitted cells whose per-trade "
            "mean was negative while their date-equal-weighted mean was positive, and whose "
            "board key drifted up over the sample. They are labelled post-hoc rather than "
            "folded into the bar, because moving a pre-registered bar after seeing the "
            "results is the exact failure this design exists to prevent. Read CLEARS as the "
            "registered result and the two controls as what survives scrutiny."),
        "clearing": [c for c in clears if c["CLEARS"]],
        "all_cells": clears,
    }
    return res


def overlap_receipt(sig_rows: pd.DataFrame) -> dict:
    """Quantify the overlap the pre-registered treatment (b) accepts."""
    out = []
    HMAX = max(HORIZONS)
    for sig, g in sig_rows.groupby("signal", sort=True):
        g = g.sort_values(["ticker", "date"])
        d = g.groupby("ticker")["date"].diff().dt.days.to_numpy()
        prev_within = np.isfinite(d) & (d <= HMAX * 2)   # calendar proxy for HMAX sessions
        out.append({
            "signal": sig, "rows": int(len(g)), "n_names": int(g["ticker"].nunique()),
            "n_dates": int(g["date"].nunique()),
            "rows_whose_H10_window_overlaps_a_prior_row_of_the_same_name_pct":
                _r(100.0 * float(prev_within.mean())),
            "mean_rows_per_name": _r(float(len(g)) / max(1, g["ticker"].nunique()), 2),
            "mean_rows_per_date": _r(float(len(g)) / max(1, g["date"].nunique()), 2),
        })
    return {"choice": OVERLAP_CHOICE, "note": OVERLAP_NOTE,
            "calendar_proxy_note": ("overlap is measured on CALENDAR days (<= 20) as a "
                                    "conservative proxy for 10 SESSIONS, so this share is an "
                                    "upper bound on the true session overlap."),
            "rows": out}


def multiplicity(res_tables: dict, book: dict, c12: dict) -> dict:
    """Per-family cell counts and the false-positive expectation. Never pooled across families."""
    fam = {
        "outcome_rate_tables": sum(len(res_tables[k]) for k in
                                   ("by_ladder_N", "by_feature", "by_regime", "by_era6")),
        "book_cells_decision_bar": book["verdict"]["cells_evaluated"],
        "c12_standardised_comparisons": sum(len(r["outcomes"]) for r in c12["standardised"]),
    }
    return {
        "counts_by_family": fam,
        "rule": ("Multiplicity is stated and read PER FAMILY. No inference is ever made by "
                 "comparing a cell in one family against the chance rate of another, and no "
                 "'below chance therefore informative' reading is taken anywhere in this "
                 "file — a below-chance cell in a family this size is the expected shape of "
                 "noise, not a short signal."),
        "expected_false_positives_at_5pct": {k: _r(0.05 * v, 1) for k, v in fam.items()},
        "book_note": (f"The book's decision bar is a TWO-WINDOW bar (positive net and t >= "
                      f"{BOOK_T_BAR} in fit AND holdout), so its per-cell false-positive rate "
                      f"is far below 5%; the count above is the raw cell count, printed so "
                      f"the search size is visible rather than the bar's strength assumed."),
        "signal_nesting": SIGNAL_NESTING_NOTE,
    }


# ── vintage + ore ledger ──────────────────────────────────────────────────────

def vintage_receipt(files_found: int, kept: int) -> dict:
    return {
        "base_sha": _git("merge-base", "HEAD", "origin/main"),
        "data_store_sha": _git("log", "-1", "--format=%H", "--", "data/china_stocks_raw"),
        "build_head_sha": _git("rev-parse", "HEAD"),
        "sha_note": ("base_sha (this branch's point off main) and data_store_sha (the last "
                     "commit touching the input store) are the stable vintage identity. "
                     "build_head_sha is whatever HEAD the run happened on and BY CONSTRUCTION "
                     "pre-dates the commit that carries this file — it differs on any re-run "
                     "after commit, and that is not a reproducibility failure."),
        "raw_store_names": files_found,
        "names_kept_after_st_exclusion": kept,
        "store_basis": ("BACK-ADJUSTED (L1's measured correction to v0's 'nominal' header). "
                        "Adjustment preserves RETURNS, so every window return here is "
                        "unaffected; only the round-to-tick limit PRICE is, and v0's 0.002 "
                        "tolerance is the cushion for it."),
        "expansion_status": ("PRE-EXPANSION. This checkout's data/china_stocks_raw holds a "
                             "curated survivors-only subset of the listed A-share market. A "
                             "sibling Codex lane is expanding the universe; that expansion is "
                             "NOT in this store and every count, rate and expectancy below is "
                             "scoped to the smaller universe."),
        "survivorship": ("SURVIVORS ONLY. Delisted names are absent, so every down-tail here "
                         "— the limit-down rate, the worst trade, the forced-close loss — "
                         "reads BETTER than the truth."),
        "collectors_untouched": ("This lane touched no collector, no Tushare surface, no "
                                 "universe store and no engine data wiring."),
    }


ORE_LEDGER = [
    {"ore": "other signal families on the window target",
     "why": ("Four signals were pre-registered and priced. Volume-shape, sector-cohort "
             "breadth, gap-band (L1's C1 conditioner), 龙回头 pullback state (W2-B's) and "
             "the failed-seal cohort are all untested AGAINST THIS OUTCOME."),
     "cost": "one lane"},
    {"ore": "H beyond 10 sessions",
     "why": ("The charter's 'trajectory of rerating windows' has no stated length. H=20/30 "
             "and a first-target-hit clock (time-to-1.5w) are untested."),
     "cost": "one lane, same instrument"},
    {"ore": "intraday window exits",
     "why": ("The O3-vs-O2 gap is measured on DAILY bars, so every peak here is a daily high "
             "and the exit is an open. Minute bars (incoming per v0's Stage-4 data-gap list) "
             "would turn the capacity upper bound into a real exit policy."),
     "cost": "collector-dependent"},
    {"ore": "stop-loss and trail overlays",
     "why": "Every book here is entry + fixed-H exit. No stop, no trail, no scale-out.",
     "cost": "one lane"},
    {"ore": "window outcomes on the failed-seal cohort (W2-B's 13,871 events)",
     "why": ("W2-B measured that cohort against tomorrow's board. Its WINDOW outcomes — the "
             "same O1/O2/O3 family — have never been measured."),
     "cost": "one lane, both instruments already exist"},
    {"ore": "zt_pool-universe replication",
     "why": ("The zt_pool scrape names limit-up stocks this curated store does not hold. "
             "Replicating the window rates on that universe is the cheapest external check."),
     "cost": "small"},
    {"ore": "soft-label model integration (L3 ore #10)",
     "why": ("The window outcome is a graded target, not a binary one — cum/w is a natural "
             "regression label and this lane thresholded it into rates. A soft-label model on "
             "cum/w and peak/w is untested."),
     "cost": "one lane"},
    {"ore": "per-name effects",
     "why": ("Every table pools names within a board key. Whether the window edge is a "
             "property of a handful of repeat names is measured only as top5_name_share, "
             "never as a per-name panel."),
     "cost": "one lane"},
    {"ore": "post-expansion re-run",
     "why": ("Survivors-only, pre-expansion. Every rate here is measured on names that lived. "
             "Re-running post-expansion is the first thing to do."),
     "cost": "re-run, no new code"},
    {"ore": "entry anchors other than the T+1 open",
     "why": ("W2-B showed the T-close anchor exists and is fillable for weakness populations. "
             "The big-day and near-miss signals here could be entered at the T CLOSE — "
             "untested in this lane."),
     "cost": "small, W2-B's machinery"},
]


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    t0 = time.time()
    _T0[0] = t0
    print("[1/8] building panel + populations ...", flush=True)
    rows, bench, meta = build()
    print(f"      rows={len(rows):,}  ({time.time() - t0:.0f}s)", flush=True)

    print("[2/8] v0 parity gate ...", flush=True)
    parity = v0_ladder_parity(rows, meta)
    print(f"      {parity['verdict'][:60]}", flush=True)

    print("[3/8] regime dial + conditioners ...", flush=True)
    dial, dial_meta = load_regime_dial()
    cut_receipt = attach_conditioners(rows, dial)

    print("[4/8] lookahead checks ...", flush=True)
    st_set, _ = load_st_cohort()
    files = sorted((DATA / "china_stocks_raw").glob("*.parquet"))
    corruption = corruption_experiment(files, st_set)
    f4chk = f4_date_locality(rows)
    print(f"      {corruption['verdict'][:50]} / f4 {f4chk['verdict']}", flush=True)

    print("[5/8] outcome tables ...", flush=True)
    tables = outcome_tables(rows)
    lift = feature_lift(tables)
    gap = o3_minus_o2(tables)

    print("[6/8] C12 matched near-miss ...", flush=True)
    c12 = c12_matched(rows)

    print("[7/8] the book ...", flush=True)
    sig_rows = select_signal_rows(rows)
    trade_rows, missing = [], 0
    for ticker, g in sig_rows.groupby("ticker", sort=True):
        p = DATA / "china_stocks_raw" / f"{ticker}.parquet"
        if not p.exists():
            missing += 1
            continue
        A = _ticker_arrays(pd.read_parquet(p), _board_from_ticker(ticker))
        if A is None:
            missing += 1
            continue
        trade_rows.extend(book_trades(ticker, A, g))
    if missing:
        print(f"::warning title=window-battery-missing-name::{missing} signal names could "
              f"not be re-read for the entry book", flush=True)
    trades = pd.DataFrame(trade_rows, columns=TRADE_COLS)
    trades["date"] = pd.to_datetime(trades["date"])
    trades["split"] = np.where(trades["date"] < SPLIT_DATE, "fit", "holdout")
    book = the_book(trades, bench)
    avail = entry_availability(rows)
    overlap = overlap_receipt(sig_rows)
    bench_summary = {
        "definition": BENCH_NOTE,
        "levels": [
            {"bkey": bk, "H": int(H), "split": sp, "sessions": int(len(g)),
             "mean_names_per_session": _r(float(g["bench_names"].mean()), 1),
             "universe_mean_net_pct": _r(100.0 * float(g["bench_net"].mean()), 3)}
            for (bk, H, sp), g in bench.assign(
                split=np.where(bench["date"] < SPLIT_DATE, "fit", "holdout")).groupby(
                    ["bkey", "H", "split"], sort=True)],
    }
    print(f"      trades={len(trades):,}  clearing cells="
          f"{book['verdict']['cells_clearing']}  vs-benchmark="
          f"{book['verdict']['cells_clearing_vs_benchmark']}", flush=True)

    print("[8/8] writing ...", flush=True)
    payload = {
        "instrument": "window_target_battery_v1",
        "wave": "CN LIMIT-MOVE ALPHA — Wave 3 A (THE WINDOW-TARGET BATTERY)",
        "tier": "display / audit — not a promotion, not a gate, not a ranker",
        "generated_utc": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runtime_sec": None,
        "pre_registration": PRE_REGISTRATION,
        "vintage": vintage_receipt(meta["files_found"], meta["tickers_kept"]),
        "coverage": meta,
        "v0_parity_gate": parity,
        "regime_dial": dial_meta,
        "conditioner_cuts": cut_receipt,
        "lookahead_checks": {"corruption_experiment": corruption, "f4_date_locality": f4chk},
        "outcome_tables": tables,
        "feature_lift_board_vs_window": lift,
        "o3_minus_o2_gap": gap,
        "c12_near_miss_matched": c12,
        "entry_availability": avail,
        "benchmark_leg": bench_summary,
        "the_book": book,
        "overlap_receipt": overlap,
        "multiplicity": multiplicity(tables, book, c12),
        "ore_ledger": ORE_LEDGER,
        "what_this_does_not_establish": [
            "No cell here is a promotion, a gate, a ranker or a signal. Display tier.",
            "The window outcomes are measured on DAILY bars: every peak is a daily high and "
            "every exit is an open. Nothing here says an intraday exit is available.",
            "The O3-framing 'best open' book requires foresight and is an UPPER BOUND, not a "
            "strategy. The first-open sibling beside it is the implementable version.",
            "C12 compares a BUNDLE. Attention, supply at the limit and the cause of stopping "
            "short are not separated.",
            "Survivors-only, pre-expansion universe: every down-tail reads better than truth.",
            "Slippage is not modelled and fills are assumed at the printed open.",
            "The benchmark leg controls for the board key's own drift on the signal's own "
            "sessions. It does NOT control for size, liquidity, sector or volatility "
            "exposure: a cell that beats the universe mean may still be paid for by carrying "
            "more risk than the universe carries.",
            "A null on any construction here closes THAT construction only — see the ORE "
            "LEDGER for the search space this lane did not touch.",
        ],
    }
    payload["runtime_sec"] = round(time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=False) + "\n")
    print(f"      wrote {OUT_JSON.relative_to(REPO)} "
          f"({OUT_JSON.stat().st_size / 1e6:.2f} MB, {payload['runtime_sec']}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
