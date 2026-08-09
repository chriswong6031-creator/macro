#!/usr/bin/env python3
"""continuation_regime_merge_v1.py — CN LIMIT-MOVE ALPHA, Wave 3 / lane W3-B.

THE ONE QUESTION
    Wave 1 lane L1 measured that the naive fillability-honest next-open continuation rider
    LOSES everywhere, and loses ANTI-monotonically: the cells with the highest P(next board)
    have the worst open-to-close.  The T+1 auction prices the public conditioners.

    Wave 2 lane W2-A then measured two structural facts about the board-ecology regime dial
    i5_realized_continuation_ma5: it is a LEVEL instrument and never a RANKER (it is constant
    within a date, so it cannot reorder names), and its effect is STRONGEST ON THE N=1 RUNG
    (fit/holdout continuation multiplier 1.670x).  W2-A's adjudication therefore named the
    L1 CONTINUATION-SIDE REGIME MERGE the largest measured remaining effect in the program:
    the dial says WHEN the game pays, and L1's rider is the thing that has to be paid.

    This file merges them and asks, on one pre-registered pass:

        does any (board x ladder-rung x dial-tercile) cell make the FILLABLE next-open
        rider net-positive, with a date-clustered t >= 2.0, in BOTH the fit and the
        holdout window?

HONEST PRIOR, STATED BEFORE THE FIRST NUMBER
    The dial is PUBLIC INFORMATION.  Every participant can count yesterday's boards and
    yesterday's continuations; the 5-session mean of the realised continuation rate is not a
    private read, it is the thing 打板 desks talk about all day.  Wave 1's null family says
    the T+1 auction prices exactly this class of public conditioner, and the anti-monotone
    expectancy says it prices it with the sign pointed at the naive taker.  THE LIKELY
    OUTCOME OF THIS LANE IS THAT THE AUCTION PRICES THE REGIME TOO.  A clean, well-measured
    null IS the deliverable.  Nothing here is tortured until a cell turns positive: the
    t-census across ALL cells is the headline statement (W2-B's convention), not the best
    surviving cell.

TIER
    Display / audit.  MEASUREMENT ONLY.  Nothing here promotes, ranks for size, gates,
    admits, scores or reaches a live surface.  No LLM is involved at any point.  Under the
    ORE LAW a null closes ONLY the constructions actually tested; the ORE LEDGER at the
    bottom enumerates the neighbouring constructions that remain open.

WHAT IS REUSED VERBATIM (imported, not re-implemented)
    continuation_rider_v1.py (Wave 1 L1) supplies the panel: the universe and exclusions, the
    tolerant PRIMARY limit-up definition, the 连板 streak, the <=10-calendar-day T->T+1 pair
    rule, the gap bands, the locked-exit roll, the Wilson helper, the cost convention and the
    v0 ladder parity gate.  Its own process_ticker() is run alongside this lane's book as a
    PARITY LEG, so this file is shown to be standing on L1's panel before any of its findings
    are read.
    board_ecology_series_v1.parquet (Wave 1 L2) supplies the dial AS COMMITTED.  It is never
    recomputed here — recomputing it would silently fork the definition under test — but it
    IS independently re-derived from this lane's own panel as a lookahead gate (G4).
    The fit/holdout/fit-core boundaries are W2-A's, frozen as constants and re-derived as a
    gate; this lane does not invent a split.

TWO DELIBERATE AMENDMENTS TO L1's BOOK, BOTH DISCLOSED AND BOTH GATED
    (1) CLOSURE-TOLERANT FORWARD CHAIN.  L1 (and W3-A) reused v0's 10-calendar-day PAIR rule
        as the forward-chain STEP rule, so a CNY or National-Day closure truncates every open
        position market-wide at once; W3-A receipted that as the root cause of its first-draft
        flagship illusion (WINDOW_TARGET_BATTERY_V1_2026-08-09.md, amendment A1).  This lane
        does not re-pay it.  The step rule here is: the name's immediately next live bar is
        admissible if the calendar gap is <= 10 days OR NO MARKET SESSION FELL BETWEEN THE TWO
        BARS.  The second clause is exactly "the exchange was shut", read off the trading
        calendar rather than assumed; a name-specific suspension (sessions the name missed
        while the market traded) is still refused, as before.  The T->T+1 pairing that defines
        the EVENT and its label is left at v0's 10-day rule untouched, so the ladder parity
        gate still reproduces v0's published cells exactly.
    (2) COMPLETE-WINDOW BOOK.  A trade whose chain cannot reach a real exit bar is EXCLUDED
        from the priced book and reported in its own block, never pooled into a headline
        (W3-A's amendment A1, adopted here from the first run rather than after review).

Run from repo root:  TZ=UTC python3 research/cn_prophet_audit/continuation_regime_merge_v1.py
Output written by this script (frozen, committed):
    research/cn_prophet_audit/CONTINUATION_REGIME_MERGE_V1_2026-08-09.json
The receipt CONTINUATION_REGIME_MERGE_V1_2026-08-09.md beside it is HAND-WRITTEN from that
JSON (the house pattern) and is NOT emitted by main(); every number in it is quoted from the
frozen file.

AMENDMENTS AFTER THE FIRST RUN — see AMENDMENTS_AFTER_FIRST_RUN below.  A commissioned
adversarial review found the primary null reproduced exactly and every defect in the
AFFIRMATIVE framing; the amendments replace a one-draw permutation control with a 200-draw
one plus an era-preserving arm, put session-clustered inference on the affirmative shares,
turn the lookahead leg into a check that can fail, and widen two gates from samples to full
coverage.
"""
from __future__ import annotations

import importlib.util
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

DATA = REPO / "data"
OUT_DIR = REPO / "research" / "cn_prophet_audit"
OUT_JSON = OUT_DIR / "CONTINUATION_REGIME_MERGE_V1_2026-08-09.json"

RIDER_PY = OUT_DIR / "continuation_rider_v1.py"
ECOLOGY_PARQUET = OUT_DIR / "board_ecology_series_v1.parquet"
LIMIT_EVENTS = DATA / "china_microstructure" / "limit_events.parquet"
LIMIT_TAPE = DATA / "china_microstructure" / "limit_tape.parquet"
ZT_POOL = DATA / "china_zt_pool" / "pool.parquet"

# Every dependency rides an armed PR that has not reached main yet.  A missing one is a loud,
# named error with its own recovery line — never a silent fallback, because a fallback would
# quietly change what "the rider" or "the regime" means.  This self-heals once the PRs merge.
_DEPS = [
    (RIDER_PY, "claude/cn-limit-w1-rider",
     "research/cn_prophet_audit/continuation_rider_v1.py"),
    (ECOLOGY_PARQUET, "claude/cn-limit-w1-regime-salvage",
     "research/cn_prophet_audit/board_ecology_series_v1.parquet"),
    (LIMIT_EVENTS, "claude/cn-limit-w1-dataheal",
     "data/china_microstructure/limit_events.parquet"),
    (LIMIT_TAPE, "claude/cn-limit-w1-dataheal",
     "data/china_microstructure/limit_tape.parquet"),
    (ZT_POOL, "claude/cn-limit-w1-dataheal",
     "data/china_zt_pool/pool.parquet"),
]
_MISSING = (
    "MISSING WAVE-1 DEPENDENCY: {path}\n"
    "This lane MERGES Wave-1 artifacts and deliberately does not vendor copies of them.\n"
    "Fetch it from its authoring branch:\n"
    "  git fetch origin {branch}\n"
    "  git show origin/{branch}:{rel} > {rel}\n"
    "(or simply run this after the Wave-1 PRs have merged to main)."
)
for _p, _b, _rel in _DEPS:
    if not _p.exists():
        raise SystemExit(_MISSING.format(path=_p, branch=_b, rel=_rel))

_spec = importlib.util.spec_from_file_location("continuation_rider_v1", RIDER_PY)
rider = importlib.util.module_from_spec(_spec)
sys.modules["continuation_rider_v1"] = rider
_spec.loader.exec_module(rider)  # safe: continuation_rider_v1 guards its main() on __main__

# names taken from L1 rather than re-decided
wilson = rider.wilson
jsonable = rider.jsonable
_r = rider._r
rate_block = rider.rate_block
LIMIT_CLOSE_TOL = rider.LIMIT_CLOSE_TOL
MAX_PAIR_GAP_DAYS = rider.MAX_PAIR_GAP_DAYS
ROLL_CAP_SESSIONS = rider.ROLL_CAP_SESSIONS
ROUND_TRIP_COST = rider.ROUND_TRIP_COST
TIME_STOP_SESSIONS = rider.TIME_STOP_SESSIONS
MAX_HOLD_SESSIONS = rider.MAX_HOLD_SESSIONS
THIN_CELL_N = rider.THIN_CELL_N
N_COHORT_CAP = rider.N_COHORT_CAP
LOCKED_EXIT_NOTE = rider.LOCKED_EXIT_NOTE
EXIT_RULES = rider.EXIT_RULES
RULES = ("E1_board_fail", "E2_first_down_close", "E3_time_stop_T4")


# ── frozen parameters — PRE-REGISTERED, written before the first run ──────────

MODEL_VERSION = "continuation_regime_merge_v1"

REGIME_COL = "i5_realized_continuation_ma5"
REGIME_RAW_COL = "i5_realized_continuation"
N_STRATA = 3                     # terciles.  No collapse ladder: a thin cell is SKIPPED, not
UNKNOWN_STRATUM = 9              # re-cut, because re-cutting after seeing a thin count is the
STRATUM_LABELS = {0: "T1_cold", 1: "T2_mid", 2: "T3_hot",
                  UNKNOWN_STRATUM: "UNKNOWN_no_print"}

# THE DECISION BAR — fixed before any number was computed.
BOOK_T_BAR = 2.0                 # date-clustered t, required in BOTH windows
BOOK_MIN_DATES = 30              # W3-A's floor, per window
MIN_FIT_CORE_POSITIVES = 150     # W2-A's floor.  NOT LOWERED AFTER SEEING DATA — W2-A held
                                 # this exact line against STAR at 137 and this lane inherits
                                 # both the number and the discipline.
HEADLINE_CELL = {"board": "main", "rung": "N1", "stratum": "T3_hot",
                 "rule": "E3_time_stop_T4"}

DECISION_BAR = (
    f"A (board x rung x dial-tercile x exit-rule) cell CLEARS only if its DATE-EQUAL-WEIGHTED "
    f"NET expectancy (after a {ROUND_TRIP_COST * 1e4:.0f} bp round trip) is positive AND its "
    f"date-clustered t is >= {BOOK_T_BAR}, in BOTH the fit and the holdout window, with "
    f"n_dates >= {BOOK_MIN_DATES} in each, inside a cell family carrying at least "
    f"{MIN_FIT_CORE_POSITIVES} fit-core continuation positives.  Anything else is a NULL FOR "
    f"THAT CONSTRUCTION and for no other."
)

# W2-A's splits, FROZEN from REGIME_CALIBRATION_V2_2026-08-09.json.  Re-derived below as a
# gate; a mismatch is printed loudly rather than absorbed.  Inventing a new split here would
# make this lane non-comparable with the receipt whose finding it is following up.
BOARD_SPLITS = {
    "main": {"split_rule": "global", "era_start": "2011-01-04",
             "calib_start": "2020-04-09", "split_date": "2021-11-26",
             "published_fit_dates": 2646, "published_holdout_dates": 1135},
    "chinext": {"split_rule": "chinext_wide_era", "era_start": "2020-08-24",
                "calib_start": "2024-03-08", "split_date": "2024-10-25",
                "published_fit_dates": 1007, "published_holdout_dates": 433},
    "star": {"split_rule": "star_listing_era", "era_start": "2019-07-29",
             "calib_start": "2023-09-25", "split_date": "2024-07-01",
             "published_fit_dates": 1190, "published_holdout_dates": 510},
}
FIT_FRACTION = 0.70
SPLIT_PROVENANCE = (
    "W2-A regime_calibration_v2.py / REGIME_CALIBRATION_V2_2026-08-09.json, section `splits`. "
    "main = v0's global 70/30 date split; chinext = re-split inside the +-20% wide-band era "
    "(never pooled across 2020-08-24); star = re-split inside its listing era (W2-A's "
    "pre-registered L3-ORE-#3 change).  fit_core = [era_start, calib_start); fit_calib = "
    "[calib_start, split_date); the fit WINDOW used for cuts and for the fit-side book is "
    "[era_start, split_date) — core plus calib — because this lane fits no calibration map "
    "and therefore has no reason to hold the calib slice out.  The FLOOR is measured on "
    "fit_core alone so that '150 fit-core positives' means here exactly what it meant in W2-A."
)

# L1's PUBLISHED book numbers (CONTINUATION_RIDER_V1_2026-08-08.json, c2_entry_book.by_era,
# board=main, N_cohort=ALL, band=ALL).  This lane re-derives them from L1's own code on the
# same store; a mismatch means the panel moved and nothing below can be read.
L1_PARITY_TARGETS = {
    "limit_up_days": 60298,
    "limit_up_days_with_usable_next_bar": 59657,
    "entries_fillable": 51486,
    "main_book": {
        "fit": {"E1_board_fail": (27888, -0.431), "E2_first_down_close": (27888, -0.589),
                "E3_time_stop_T4": (27888, -0.277)},
        "holdout": {"E1_board_fail": (15428, -0.384), "E2_first_down_close": (15428, -0.341),
                    "E3_time_stop_T4": (15428, -0.209)},
    },
}
L1_PARITY_TOL_PCT = 0.002   # published to 3dp

# Store-vintage stamp.  Printed AND gated: a re-run against a different store must say so.
VINTAGE = {
    "curated_universe_names": 1842,
    "healed_limit_events_rows": 71463,
    "raw_store": "data/china_stocks_raw",
    "note": ("THE PRE-EXPANSION CURATED SLICE.  1,842 names of a ~5,400-name market, "
             "survivors-only, 1 ST name.  A sibling lane is expanding the store toward the "
             "full universe including ST and DELISTED names; falsifier F3 (the ladder itself "
             "may be a survivorship artifact) hangs over every number in this file.  A "
             "post-expansion re-run is NOT a refinement of these numbers, it is a different "
             "universe, and the two receipts must be compared as such."),
}

# The corruption experiment.  THREE arms, because one of them has almost no power and saying
# so is the point (S7 class: a check that cannot see failure is not a check).
CORRUPTION_ARMS = {
    "corrupt_lag1": ("the dial series shifted +1 trading session, so a trade at T reads the "
                     "dial printed at T-1.  THE PRE-REGISTERED ARM.  Its power is WEAK BY "
                     "CONSTRUCTION and measured rather than assumed: the dial is a 5-session "
                     "backward mean, so consecutive values share four of five inputs and the "
                     "lag-1 autocorrelation printed below is near 1.  Attenuation, not death, "
                     "is the honest expectation here."),
    "corrupt_lead1": ("the dial series shifted -1 trading session, so a trade at T reads the "
                      "dial printed at T+1 — an ACTUAL lookahead.  AMENDMENT A3 re-classes "
                      "this as a POSITIVE CONTROL rather than a null control, because i5 at "
                      "T+1 is computed FROM the T->T+1 continuation outcomes: the dial dated "
                      "T+1 literally counts how many of T's boarders boarded again at T+1, "
                      "which is the outcome the book is trading.  It MUST strengthen the "
                      "movable statistics.  A lookahead arm that did NOT strengthen them "
                      "would mean the join is not reading dates at all."),
}
PERM_SEED = 20260809
N_PERM_DRAWS = 200            # amendment A1 — was ONE draw
PERM_NULL_SEED = 20260811
RUNGS = ("N1", "N2", "N3plus")
BOOT_B = 1000                 # amendment A4 — session cluster bootstrap resamples
BOOT_SEED = 20260810
PERM_ARM_SUPERSEDED = (
    "The single-draw `corrupt_perm` arm of the first run is REMOVED and superseded by "
    "`permutation_nulls`, which draws the same null "
    f"{N_PERM_DRAWS} times under two schemes and publishes mean/SD/p. One draw quoted to two "
    "decimals was the defect; see that section's note."
)

AMENDMENTS_AFTER_FIRST_RUN = [
    {"id": "A1", "trigger": "commissioned adversarial review, MAJOR",
     "change": ("The destruction control was ONE global permutation draw and its quoted "
                "'0.40 pp collapse' was a single sample stated to two decimals (the review "
                "measured the null at -0.12 +- 5.06 pp over 20 draws — a coin flip). Replaced "
                f"by {N_PERM_DRAWS} draws under TWO schemes, global and era-preserving "
                "within-year, publishing null mean/SD and a two-sided permutation p for every "
                "affirmative statistic."),
     "effect_on_the_verdict": ("None on the primary null. It materially WEAKENS the "
                               "receipt's own flagship magnitude claim: against the "
                               "era-preserving null the -16.74 pp availability spread is not "
                               "significant, so most of it is era composition.")},
    {"id": "A2", "trigger": "commissioned adversarial review, MAJOR",
     "change": ("The affirmative sections now lead with the ORDERING result, which survives "
                "both nulls, instead of the -16.74 pp magnitude, which does not. Every "
                "magnitude is banded with its permutation p.")},
    {"id": "A3", "trigger": "commissioned adversarial review, MAJOR (S7 class)",
     "change": ("The lookahead verdict keyed only on a maximum over 21 uniformly negative "
                "cells, which cannot rise — a check that could not fail. It now keys on the "
                "two series that move under a shifted dial, and the lookahead arm is "
                "re-classed as a POSITIVE control that MUST strengthen them, because i5 dated "
                "T+1 is computed from the T->T+1 outcome.")},
    {"id": "A4", "trigger": "commissioned adversarial review, MAJOR",
     "change": ("The affirmative shares — availability, fillability tax, mean gap — were the "
                "only quantities in the receipt not clustered, carrying IID Wilson bands of "
                "+-1.7 pp against a permutation-null SD of 5-8 pp. They now carry a session "
                f"cluster bootstrap ({BOOT_B} resamples, seed {BOOT_SEED}), and the hot-cold "
                "spreads a two-sample session bootstrap.")},
    {"id": "A5", "trigger": "commissioned adversarial review, prose defects",
     "change": ("Three false MD claims corrected against this file's own tables (the "
                "per-trade-t direction, the sign-stability of the broken lead across exit "
                "rules, and the count of run-stamp fields), and the script header no longer "
                "claims main() writes the MD.")},
    {"id": "A6", "trigger": "commissioned adversarial review, gate coverage",
     "change": ("Lookahead gates G1 and G3 sampled 177 and 600 of 9,277 sessions while the "
                "receipt claimed the legs PASSED outright. Both now run at FULL coverage.")},
    {"id": "A7", "trigger": "commissioned adversarial review, labelling",
     "change": ("The incomplete-window count inside the sealed-only closure parity block was "
                "a both-cohort total. Split into sealed / broken / total with a note on which "
                "denominator it is commensurable with.")},
]

PREREGISTRATION = {
    "registered_before_any_number_was_read": True,
    "honest_prior": (
        "The dial is public information and Wave 1 established that the T+1 auction prices "
        "public conditioners — with the sign pointed at the naive taker (the highest-"
        "probability gap cell had the WORST open-to-close, -1.009%). The expected outcome of "
        "this lane is therefore a NULL: the auction prices the regime too. A clean, "
        "well-measured null is the deliverable. No cell is tortured to find a positive."),
    "primary_question": (
        "Does any (board x ladder-rung x dial-tercile) cell make the FILLABLE next-open rider "
        "net-positive with a date-clustered t >= 2 in BOTH the fit and the holdout window?"),
    "headline_cell_declared_in_advance": HEADLINE_CELL,
    "why_that_cell": (
        "W2-A measured the dial strongest on the N=1 rung (1.670x fit/holdout continuation "
        "multiplier) and main is the only board whose dial is non-degenerate and whose "
        "fit-core positives clear the floor. Top tercile is the direction the dial is "
        "supposed to help in. E3 (the unconditional T+4 time stop) is the primary exit "
        "because it is the only rule whose horizon does not depend on the outcome, so it is "
        "the one rule that compares like-for-like across cohorts and strata."),
    "secondary_a": (
        "Does W2-B's broken-board T+1-open lead over the sealed cohort (+0.15pp, sign-stable "
        "cells demoted by date-clustering but not zero) CONCENTRATE in dial-high states? "
        "Measured as a paired, same-session, matched-prior-rung lead, date-clustered."),
    "secondary_b": (
        "Does the dial level shift the FILLABLE SHARE itself? If dial-high states make next "
        "opens LESS fillable, the auction is pricing the regime by rationing access and the "
        "paper edge is being auctioned away before any return is measured. Reported as a "
        "fillable-share x dial-tercile table per board."),
    "decision_bar": DECISION_BAR,
    "dial": {
        "variable": REGIME_COL,
        "value_used": ("the dial printed at the FEATURE date T (the board day), per board — "
                       "a backward 5-session mean ENDING at T, so it is on the tape at T's "
                       "close and decidable before the T+1 auction the book enters at."),
        "cuts": ("terciles of the dial over the board's OWN FIT-WINDOW SESSIONS (dates, not "
                 "rows — a row-weighted quantile would let cross-sectional size decide where "
                 "'hot' starts), applied unchanged to the holdout. Realised out-of-sample "
                 "masses are PRINTED, never assumed: W3-A measured that frozen quantile cuts "
                 "are not their nominal quantiles out of sample."),
        "no_collapse_ladder": ("A tercile that misses the fit-core floor is SKIPPED and "
                               "printed, never re-cut to halves. Re-cutting after seeing a "
                               "thin count would be a post-hoc cut."),
        "unknown_stratum": ("A session where the board printed no continuation pairs at all "
                            "carries its own stratum. The absence IS the cold state; it is "
                            "not a hole to be patched."),
    },
    "pooling": ("NEVER across boards. ChiNext is modelled inside the >=2020-08-24 wide-band "
                "era only. Strict and tolerant bases are never unioned to form a cut."),
    "the_book": {
        "entry": ("the T+1 OPEN, and only where that open is FILLABLE — below the tolerant "
                  "limit price. A 一字 open is refused, never bought at a price that never "
                  "traded."),
        "exit_rules": EXIT_RULES,
        "locked_exit": LOCKED_EXIT_NOTE,
        "costs": (f"Headline per-trade means are GROSS; every date-clustered number and every "
                  f"mean_net_pct applies a flat {ROUND_TRIP_COST * 1e4:.0f} bp round trip "
                  f"(0.10% stamp duty sell-side + ~0.025% commission each way). SLIPPAGE IS "
                  f"NOT MODELLED — fills are assumed at the printed open, which is optimistic "
                  f"for exactly these names."),
    },
    "fillability": ("Every entry is at the T+1 OPEN and only where that open is fillable "
                    "(below the tolerant limit price). Every continuation/return number "
                    "carries its fillable-conditional twin. Locked exits ROLL; a scheduled "
                    "exit bar that opens at or below its own limit-down price cannot be sold."),
    "censoring": ("COMPLETE-WINDOW BOOK. A trade whose forward chain cannot reach a real exit "
                  "bar is excluded from the priced book and reported separately."),
    "corruption_experiment": CORRUPTION_ARMS,
    "what_a_null_would_close": (
        "ONLY the constructions enumerated here: the fillable next-open rider under E1/E2/E3, "
        "conditioned on the i5_realized_continuation_ma5 LEVEL in fit-window terciles, on the "
        "{1, 2, 3+} rungs, per board, plus the two secondary questions as specified. It would "
        "close nothing about the dial as a continuous covariate, its slope, cross-board "
        "spillover, its interaction with any other entry family, or any horizon or entry "
        "moment not listed. See the ORE LEDGER."),
}


# ── helpers this lane adds (inference + tabulation) ──────────────────────────

def net_of(x: np.ndarray) -> np.ndarray:
    return (1.0 + x) * (1.0 - ROUND_TRIP_COST) - 1.0


def per_trade_t(x: np.ndarray) -> float | None:
    """Per-trade t on NET returns. Printed BESIDE the clustered t, never instead of it."""
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    if x.size < 2:
        return None
    n = net_of(x)
    sd = float(n.std(ddof=1))
    if sd <= 0:
        return None
    return float(n.mean()) / (sd / np.sqrt(n.size))


def date_clustered(rets: np.ndarray, dates: np.ndarray) -> dict:
    """Date-clustered net expectancy — W2-B's function, copied, and the only honest SE here.

    Limit-move trades are not independent: a theme wave puts dozens of names on one session
    behind one market-wide open.  Collapsing each ENTRY-SIGNAL DATE to its own mean net return
    before forming a t makes the reported t count SESSIONS.  The point estimate changes
    meaning deliberately: date-equal weighting is what a book that cannot take unlimited
    same-day positions actually earns.
    """
    x = np.asarray(rets, dtype="float64")
    fin = np.isfinite(x)
    x = x[fin]
    if x.size == 0:
        return {"n_dates": 0}
    dm = pd.Series(net_of(x)).groupby(np.asarray(dates)[fin]).mean().to_numpy()
    k = int(dm.size)
    out = {"n_dates": k, "date_eq_weight_net_pct": _r(100.0 * float(dm.mean()), 3),
           "trades_per_date": _r(float(x.size) / k, 2)}
    if k > 1:
        se = float(dm.std(ddof=1)) / np.sqrt(k)
        out["date_clustered_se_pct"] = _r(100.0 * se, 3)
        out["date_clustered_t"] = _r(float(dm.mean()) / se, 2) if se > 0 else None
    out["per_trade_t"] = _r(per_trade_t(x), 2)
    return out


def paired_date_lead(a_ret: np.ndarray, a_dt: np.ndarray,
                     b_ret: np.ndarray, b_dt: np.ndarray) -> dict:
    """Date-clustered lead of arm A over arm B on the sessions BOTH arms traded.

    A pooled difference of two unpaired means would be dominated by the sessions only one arm
    is present on, which is a composition difference wearing a cohort difference's clothes.
    """
    fa, fb = np.isfinite(a_ret), np.isfinite(b_ret)
    if not fa.any() or not fb.any():
        return {"paired_dates": 0, "status": "NOT TESTABLE — an arm is empty"}
    am = pd.Series(net_of(np.asarray(a_ret)[fa])).groupby(np.asarray(a_dt)[fa]).mean()
    bm = pd.Series(net_of(np.asarray(b_ret)[fb])).groupby(np.asarray(b_dt)[fb]).mean()
    idx = am.index.intersection(bm.index)
    if len(idx) < 2:
        return {"paired_dates": int(len(idx)),
                "status": "NOT TESTABLE — fewer than 2 shared sessions"}
    d = am.reindex(idx).to_numpy() - bm.reindex(idx).to_numpy()
    se = float(d.std(ddof=1)) / np.sqrt(d.size)
    return {
        "paired_dates": int(d.size),
        "arm_a_net_pct_on_paired_dates": _r(100.0 * float(am.reindex(idx).mean()), 3),
        "arm_b_net_pct_on_paired_dates": _r(100.0 * float(bm.reindex(idx).mean()), 3),
        "lead_pp": _r(100.0 * float(d.mean()), 3),
        "lead_date_clustered_t": _r(float(d.mean()) / se, 2) if se > 0 else None,
        "a_only_dates": int(len(am.index.difference(bm.index))),
        "b_only_dates": int(len(bm.index.difference(am.index))),
    }


def book_cell(g: pd.DataFrame) -> dict:
    out = rider.ret_block(g["ret"].to_numpy(), g["ticker"].to_numpy(), g["date"].to_numpy())
    out.update(date_clustered(g["ret"].to_numpy(), g["date"].to_numpy()))
    n = max(1, len(g))
    out["rolled_exit_pct"] = _r(100.0 * float((g["rolls"] > 0).sum()) / n)
    out["roll_forced_close_pct"] = _r(100.0 * float(g["forced_close"].sum()) / n)
    ex = g.loc[g["rolls"] > 0, "roll_extra_loss"].to_numpy(dtype="float64")
    ex = ex[np.isfinite(ex)]
    out["rolled_mean_extra_loss_pct"] = _r(100.0 * float(ex.mean()), 3) if ex.size else None
    out["rolled_worst_extra_loss_pct"] = _r(100.0 * float(ex.min()), 3) if ex.size else None
    out["mean_hold_sessions"] = _r(float(g["hold_sessions"].mean()))
    # sensitivity: drop the trades whose exit was a roll-cap mark rather than a real open
    ok = g[~g["forced_close"].astype(bool)]
    if len(ok) and len(ok) != len(g):
        out["ex_rollforced_date_eq_weight_net_pct"] = date_clustered(
            ok["ret"].to_numpy(), ok["date"].to_numpy()).get("date_eq_weight_net_pct")
    return out


def clears_bar(f: dict | None, h: dict | None) -> bool:
    if not f or not h:
        return False
    for s in (f, h):
        if (s.get("date_eq_weight_net_pct") or -1.0) <= 0:
            return False
        if (s.get("date_clustered_t") or -9.0) < BOOK_T_BAR:
            return False
        if s.get("n_dates", 0) < BOOK_MIN_DATES:
            return False
    return True


# ── STAGE 0 — the dial series, the trading calendar, the lookahead audit ─────

def head_sha() -> str:
    """The checkout's HEAD — the store vintage stamp.  A run-stamp field, like generated_utc."""
    try:
        import subprocess
        r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=30, check=False)
        return r.stdout.strip() or "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def _daykey(s) -> np.ndarray:
    """Calendar-day integer key.  Immune to the ns/ms unit mismatch between the two stores."""
    return pd.Series(s).to_numpy(dtype="datetime64[D]").astype(np.int64)


def load_dial() -> tuple[pd.DataFrame, np.ndarray, dict]:
    ser = pd.read_parquet(ECOLOGY_PARQUET)
    ser["date"] = pd.to_datetime(ser["date"])
    ser = ser[["date", "board", REGIME_COL, REGIME_RAW_COL, "i5_pairs_n", "i5_k"]]
    ser = ser.sort_values(["board", "date"]).reset_index(drop=True)

    # THE TRADING CALENDAR.  The ecology series carries one row per (board, session) over the
    # whole window, so the union of its dates IS the exchange calendar; the closure-tolerant
    # chain reads it rather than guessing a calendar-day cap.  Cross-checked against the house
    # daily tape below so the calendar is not taken from a single artifact.
    cal = np.unique(_daykey(ser["date"]))

    tape = pd.read_parquet(LIMIT_TAPE)
    tape_days = np.unique(_daykey(pd.to_datetime(tape["date"])))
    both = np.intersect1d(cal, tape_days)
    meta = {
        "source": "research/cn_prophet_audit/board_ecology_series_v1.parquet",
        "provenance": ("Wave-1 lane L2, branch claude/cn-limit-w1-regime-salvage. Taken AS "
                       "COMMITTED and never recomputed here — recomputing it would silently "
                       "fork the definition this lane exists to condition on. It IS "
                       "independently re-derived from this lane's own panel as gate G4."),
        "rows": int(len(ser)),
        "boards": sorted(ser["board"].astype(str).unique().tolist()),
        "regime_variable": REGIME_COL,
        "trading_calendar": {
            "sessions": int(cal.size),
            "first": str(np.datetime64(int(cal[0]), "D")),
            "last": str(np.datetime64(int(cal[-1]), "D")),
            "cross_check_source": "data/china_microstructure/limit_tape.parquet (house daily "
                                  "aggregate, independent build)",
            "tape_sessions": int(tape_days.size),
            "sessions_in_both": int(both.size),
            "sessions_only_in_ecology": int(cal.size - both.size),
            "sessions_only_in_tape": int(tape_days.size - both.size),
        },
        "coverage_by_board": [],
    }
    for b, g in ser.groupby("board", sort=True):
        nn = int(g[REGIME_COL].notna().sum())
        meta["coverage_by_board"].append({
            "board": str(b), "sessions": int(len(g)),
            "first_session": g["date"].min().strftime("%Y-%m-%d"),
            "last_session": g["date"].max().strftime("%Y-%m-%d"),
            "regime_non_null": nn,
            "regime_non_null_pct": _r(100.0 * nn / max(1, len(g))),
        })
    # the lag-1 autocorrelation that CALIBRATES the pre-registered corruption arm's power
    ac = {}
    for b, g in ser.groupby("board", sort=True):
        v = g[REGIME_COL].to_numpy(dtype="float64")
        m = np.isfinite(v[:-1]) & np.isfinite(v[1:])
        ac[str(b)] = _r(float(np.corrcoef(v[:-1][m], v[1:][m])[0, 1]), 4) if m.sum() > 2 else None
    meta["dial_lag1_autocorrelation"] = ac
    return ser, cal, meta


def audit_lookahead(ser: pd.DataFrame, panel_pairs: pd.DataFrame,
                    joined: dict[tuple[str, int], float]) -> dict:
    """W2-A's four-gate lookahead audit, REPLICATED against THIS lane's own frame.

    "The dial at T is computable at T's close by construction" is an argument, not evidence.
    Each leg is measured here on this lane's join, not inherited from the sibling receipt.
    """
    out = {"definition_note": (
        "i5_realized_continuation at date d = k/n over pairs whose NEXT USABLE BAR IS d and "
        "whose prior bar was a limit-up close. Every input bar is at or before d, so the value "
        "is on the tape at d's close. _ma5 is a backward rolling mean over the <=5 sessions "
        "ENDING at d, inclusive.")}
    sb = {str(b): g.sort_values("date").reset_index(drop=True)
          for b, g in ser.groupby("board", sort=True)}

    g1_ok, g1_rows, g2_diff, g2_n, g2_by = True, [], 0, 0, {}
    for b in sorted(sb):
        s = sb[b]
        vals = s[REGIME_COL].to_numpy(dtype="float64")
        dks = _daykey(s["date"])
        bd_n = bd_diff = 0
        for i in range(0, len(s) - 1):      # FULL COVERAGE (amendment A6)
            v_t, v_t1 = vals[i], vals[i + 1]
            g2_n += 1
            bd_n += 1
            if np.isfinite(v_t) and np.isfinite(v_t1) and abs(v_t - v_t1) > 1e-12:
                g2_diff += 1
                bd_diff += 1
            gv = joined.get((b, int(dks[i])))
            if gv is None:
                continue
            same = ((not np.isfinite(gv) and not np.isfinite(v_t))
                    or (np.isfinite(gv) and np.isfinite(v_t) and abs(gv - v_t) < 1e-12))
            g1_ok = g1_ok and same
            if len(g1_rows) < 6 and i >= len(s) - 3:
                g1_rows.append({
                    "board": b, "feature_date_T": s["date"].iloc[i].strftime("%Y-%m-%d"),
                    "series_at_T": None if not np.isfinite(v_t) else round(float(v_t), 6),
                    "series_at_T_plus_1": (None if not np.isfinite(v_t1)
                                           else round(float(v_t1), 6)),
                    "value_joined_onto_this_lane_rows": (None if not np.isfinite(gv)
                                                         else round(float(gv), 6)),
                    "joined_equals_T": bool(same)})
        g2_by[b] = {"sessions_compared": bd_n, "sessions_where_T_and_T1_differ": bd_diff,
                    "share_pct": _r(100.0 * bd_diff / max(1, bd_n)),
                    "verdict": ("HAS POWER" if bd_diff > 0.5 * max(1, bd_n) else
                                "WEAK ON THIS BOARD — the dial repeats its own value too often "
                                "for a one-session shift to be visible to G1 here")}
    out["G1_join_alignment"] = {
        "gate": "the value joined onto a trade equals the series value at that trade's OWN "
                "feature date T",
        "coverage": ("EVERY (board, session) in the dial series, not a sample (amendment A6 — "
                     "the first run checked only the last 60 sessions per board, 177 of 9,277, "
                     "while the receipt claimed the leg PASSED outright)"),
        "board_sessions_checked": g2_n, "all_match": bool(g1_ok),
        "worked_example_rows": g1_rows}
    out["G2_check_has_power"] = {
        "gate": "i5(T) != i5(T+1) on a material share of sessions, so a T+1 join would show up",
        "sessions_compared": g2_n, "sessions_where_T_and_T1_differ": g2_diff,
        "share_pct": _r(100.0 * g2_diff / max(1, g2_n)), "by_board": g2_by,
        "READ_PER_BOARD": ("The POOLED share understates G1's power on main (whose dial moves "
                           "nearly every session) and overstates it on the sparse boards, "
                           "which print long runs of the same value — frequently 0.0 — "
                           "because they go days with no continuation pairs at all. G3 and G4 "
                           "do not share that weakness.")}

    g3_bad, g3_checked, g3_rows = 0, 0, []
    for b in sorted(sb):
        s = sb[b]
        raw = s[REGIME_RAW_COL].to_numpy(dtype="float64")
        ma = s[REGIME_COL].to_numpy(dtype="float64")
        for i in range(0, len(s)):          # FULL COVERAGE (amendment A6)
            w = raw[max(0, i - 4):i + 1]
            w = w[np.isfinite(w)]
            exp = float(w.mean()) if w.size >= 3 else np.nan
            got = ma[i]
            g3_checked += 1
            ok = ((not np.isfinite(exp) and not np.isfinite(got))
                  or (np.isfinite(exp) and np.isfinite(got) and abs(exp - got) < 1e-9))
            g3_bad += 0 if ok else 1
            if len(g3_rows) < 3 and np.isfinite(got):
                g3_rows.append({"board": b, "date": s.loc[i, "date"].strftime("%Y-%m-%d"),
                                "recomputed_backward_ma5": round(exp, 6),
                                "parquet_ma5": round(float(got), 6)})
    out["G3_backward_window"] = {
        "gate": "ma5(T) == mean of the series' own raw i5 over the <=5 sessions ENDING at T; "
                "a forward or centred window fails here",
        "coverage": ("EVERY session in the dial series, not a sample (amendment A6 — the first "
                     "run checked the last 200 sessions per board, 600 of 9,277)"),
        "sessions_checked": g3_checked, "mismatches": g3_bad,
        "all_match": bool(g3_bad == 0), "worked_example_rows": g3_rows}

    rec = panel_pairs.groupby(["board", "target_dk"], observed=True)["y"].agg(
        k="sum", n="size").reset_index()
    rec["i5_recomputed"] = np.where(rec["n"] > 0, rec["k"] / rec["n"], np.nan)
    right = pd.DataFrame({"board": ser["board"].astype(str).to_numpy(),
                          "target_dk": _daykey(ser["date"]),
                          "i5_parquet": ser[REGIME_RAW_COL].to_numpy(dtype="float64"),
                          "n_parquet": ser["i5_pairs_n"].to_numpy(dtype="float64")})
    cmp = rec.merge(right, on=["board", "target_dk"], how="inner")
    d = np.abs(cmp["i5_recomputed"].to_numpy(dtype="float64")
               - cmp["i5_parquet"].to_numpy(dtype="float64"))
    dn = np.abs(cmp["n"].to_numpy(dtype="float64")
                - cmp["n_parquet"].to_numpy(dtype="float64"))
    fin = np.isfinite(d)
    out["G4_independent_recompute"] = {
        "gate": ("i5(T) recomputed from THIS lane's panel, using L2's exact definition, "
                 "matches the committed parquet on every (board, date) key both carry. This "
                 "gates the DEFINITION as well as the join."),
        "keys_compared": int(len(cmp)),
        "dates_with_a_finite_rate_on_both_sides": int(fin.sum()),
        "max_abs_rate_diff": (_r(float(np.nanmax(d[fin])), 9) if bool(fin.any()) else None),
        "max_abs_pair_count_diff": (_r(float(np.nanmax(dn)), 6) if dn.size else None),
        "all_match": bool(len(cmp) > 0 and bool(fin.any())
                          and float(np.nanmax(d[fin])) < 1e-9 and float(np.nanmax(dn)) < 1e-9),
    }
    out["verdict"] = ("PASS — no lookahead detected on any leg" if all(
        out[k].get("all_match") for k in
        ("G1_join_alignment", "G3_backward_window", "G4_independent_recompute"))
        else "SEE GATES — at least one leg did not match; nothing below may be read")
    return out


# ── STAGE 1 — the panel and the two books ────────────────────────────────────

TRADE_COLS = ["date", "ticker", "board", "cohort", "rung", "prior_rung", "rule",
              "entry_px", "exit_px", "ret", "hold_sessions", "rolls", "forced_close",
              "roll_extra_loss", "complete_window", "gap"]

CLOSURE_NOTE = (
    "CLOSURE-TOLERANT FORWARD CHAIN. The step from a bar to the name's immediately next LIVE "
    "bar is admissible when the calendar gap is <= "
    f"{MAX_PAIR_GAP_DAYS} days OR when NO MARKET SESSION fell between the two bars — read off "
    "the exchange calendar, not assumed from a calendar-day cap. The second clause is exactly "
    "'the exchange was shut'; a name-specific suspension (sessions the name missed while the "
    "market traded) is still refused. W3-A receipted the alternative — reusing v0's 10-day "
    "PAIR rule as the forward STEP rule — as the root cause of a market-wide CNY/National-Day "
    "truncation whose truncated tail averaged +11.03% net at 100% force-closed and produced "
    "its whole first-draft flagship. This lane does not re-pay that. The T->T+1 PAIRING that "
    "defines an event and its label is left at the 10-day rule untouched, so the v0 ladder "
    "parity gate still reproduces v0's published cells exactly."
)


def _make_walkers(A: dict, cal: np.ndarray, counters: dict):
    n, live, days = A["n"], A["live"], A["days"]
    o, c, lim_dn = A["o"], A["c"], A["lim_dn"]

    def usable_next(i: int) -> int:
        j = i + 1
        if j >= n or not bool(live[j]):
            return -1
        gapd = int(days[j] - days[i])
        if gapd <= MAX_PAIR_GAP_DAYS:
            return j
        lo = int(np.searchsorted(cal, days[i], side="right"))
        hi = int(np.searchsorted(cal, days[j], side="left"))
        if hi - lo == 0:            # the exchange was shut for the whole interval
            counters["closure_steps_admitted"] += 1
            counters["closure_max_gap_days"] = max(counters["closure_max_gap_days"], gapd)
            return j
        counters["suspension_steps_refused"] += 1
        return -1

    def sellable(b: int) -> bool:
        return not (bool(np.isfinite(lim_dn[b])) and o[b] <= lim_dn[b] * (1.0 + LIMIT_CLOSE_TOL))

    def resolve_exit(b_sched: int, fallback_bar: int):
        """Scheduled exit bar -> (price, bar, rolls, roll_forced, scheduled_open, complete)."""
        if b_sched < 0:
            return float(c[fallback_bar]), fallback_bar, 0, True, np.nan, False
        sched_open = float(o[b_sched])
        rolls, b = 0, b_sched
        while not sellable(b):
            if rolls >= ROLL_CAP_SESSIONS:
                return float(c[b]), b, rolls, True, sched_open, True
            nb = usable_next(b)
            rolls += 1
            if nb < 0:
                return float(c[b]), b, rolls, True, sched_open, False
            b = nb
        return float(o[b]), b, rolls, False, sched_open, True

    return usable_next, resolve_exit


def book_trades(ticker: str, A: dict, board: str, cal: np.ndarray,
                counters: dict) -> list[tuple]:
    """Both cohorts' open-anchored, fillability-honest, complete-window entry books.

    SEALED  — the name closed at the tolerant limit at T (L1's cohort, verbatim entries).
    BROKEN  — the name TOUCHED the limit intraday at T and closed below it (the failed-seal /
              炸板 cohort of the event-taxonomy ruling).  Derived from THIS panel on the
              tolerant basis rather than read off the house tape, for two measured reasons:
              the tape's `lianban_count` is hardcoded 0 on failed_up_seal rows (W2-B's
              silent-null trap), and strict/tolerant event overlap is only 42.7% of the union,
              so a tape-sourced cohort would mix bases with the sealed arm it is compared to.
              The tape count is carried as a coverage cross-check instead.
    """
    live, lu, c, o, h = A["live"], A["lu"], A["c"], A["o"], A["h"]
    lim_up, days, lianban = A["lim_up"], A["days"], A["lianban"]
    usable_next, resolve_exit = _make_walkers(A, cal, counters)

    gap_next = np.r_[np.diff(days), np.iinfo(np.int64).max]
    y_ok = (gap_next <= MAX_PAIR_GAP_DAYS) & np.r_[live[1:], False]   # v0's PAIR rule, kept
    nxt_o = np.r_[o[1:], np.nan]
    nxt_lim_up = np.r_[lim_up[1:], np.nan]
    unfill = np.isfinite(nxt_o) & np.isfinite(nxt_lim_up) & (
        nxt_o >= nxt_lim_up * (1.0 - LIMIT_CLOSE_TOL))
    with np.errstate(invalid="ignore", divide="ignore"):
        gap = nxt_o / c - 1.0
    touch_own = np.isfinite(h) & np.isfinite(lim_up) & (h >= lim_up * (1.0 - LIMIT_CLOSE_TOL))
    broken = live & touch_own & ~lu
    prior_lb = np.r_[0, lianban[:-1]]

    counters["sealed_days"] += int((live & lu).sum())
    counters["broken_days"] += int(broken.sum())

    sel = np.where((live & lu) | broken)[0]
    if sel.size == 0:
        return []
    idx = A["idx"]
    out = []
    for t in sel:
        if not bool(y_ok[t]) or bool(unfill[t]):
            continue
        e = t + 1
        entry_px = float(o[e])
        if not np.isfinite(entry_px) or entry_px <= 0:
            continue
        cohort = "sealed" if bool(lu[t]) else "broken"
        rung = int(min(int(lianban[t]), N_COHORT_CAP))
        prung = int(min(int(prior_lb[t]), N_COHORT_CAP))
        dt = idx[t]
        g = float(gap[t]) if np.isfinite(gap[t]) else np.nan
        for rule in RULES:
            if rule == "E3_time_stop_T4":
                cur, ok_walk = e, True
                for _ in range(TIME_STOP_SESSIONS):
                    nb = usable_next(cur)
                    if nb < 0:
                        ok_walk = False
                        break
                    cur = nb
                b_sched = cur if ok_walk else -1
                fallback = cur
            else:
                cur, steps, ran_out = e, 0, False
                while True:
                    cont = bool(lu[cur]) if rule == "E1_board_fail" else bool(c[cur] >= o[cur])
                    if not cont:
                        break
                    nb = usable_next(cur)
                    if nb < 0 or steps >= MAX_HOLD_SESSIONS:
                        ran_out = True
                        break
                    cur, steps = nb, steps + 1
                b_sched = -1 if ran_out else usable_next(cur)
                fallback = cur
            px, b_exit, rolls, roll_forced, sched, complete = resolve_exit(b_sched, fallback)
            extra = (px / sched - 1.0) if (rolls > 0 and np.isfinite(sched) and sched > 0) \
                else np.nan
            out.append((dt, ticker, board, cohort, rung, prung, rule, entry_px, px,
                        px / entry_px - 1.0, int(b_exit - e), rolls, bool(roll_forced),
                        extra, bool(complete), g))
    return out


def build(verbose: bool = True):
    """One pass over the store: L1's events + L1's own book (parity leg) + this lane's book."""
    t0 = time.time()
    st_set, st_note = rider.load_st_cohort()
    files = sorted((DATA / "china_stocks_raw").glob("*.parquet"))
    ser, cal, dial_meta = load_dial()

    counters = {"closure_steps_admitted": 0, "suspension_steps_refused": 0,
                "closure_max_gap_days": 0, "sealed_days": 0, "broken_days": 0}
    ev_frames, my_rows, l1_rows = [], [], []
    pair_rows = []          # for G4: (board, target session, was the next bar a board too)
    uncond: dict[str, list[int]] = {}
    # per-board "this session carried at least one usable ticker-day" flags, indexed against
    # the trading calendar.  This is the date set W2-A's splits were derived on; the split gate
    # needs it, and accumulating it as a boolean OR is far cheaper than a set of timestamps.
    ud = {b: np.zeros(cal.size, dtype=bool) for b in ("main", "chinext", "star")}
    kept = skipped_st = skipped_thin = 0
    for i, p in enumerate(files):
        ticker = p.stem
        if ticker in st_set:
            skipped_st += 1
            continue
        board = rider._board_from_ticker(ticker)
        try:
            df = pd.read_parquet(p)
        except Exception:  # noqa: BLE001
            skipped_thin += 1
            continue
        A = rider._ticker_arrays(df, board)
        if A is None:
            skipped_thin += 1
            continue
        kept += 1
        # unconditional next-bar limit-up rate, accumulated as scalars (L1's method) so the
        # v0 ladder parity gate carries its unconditional leg rather than an empty block.
        lv, dy = A["live"], A["days"]
        gnx = np.r_[np.diff(dy), np.iinfo(np.int64).max]
        usable = lv & (gnx <= MAX_PAIR_GAP_DAYS) & np.r_[lv[1:], False]
        slot = uncond.setdefault(board, [0, 0])
        slot[0] += int(usable.sum())
        slot[1] += int((usable & np.r_[A["lu"][1:], False]).sum())
        if board in ud and bool(usable.any()):
            dd = dy[usable]
            pos = np.searchsorted(cal, dd)
            keep = pos < cal.size
            pos, dd = pos[keep], dd[keep]
            ud[board][pos[cal[pos] == dd]] = True
        ev, l1_trades = rider.process_ticker(ticker, A, board)
        if ev is not None and len(ev):
            ev_frames.append(ev)
            u = ev[ev["y_ok"]]
            if len(u):
                # a G4 pair is keyed on the TARGET bar, which is the bar after T
                nxt_days = A["days"][np.searchsorted(A["days"], _daykey(u["date"])) + 1]
                pair_rows.append(pd.DataFrame({
                    "board": board, "target_dk": nxt_days,
                    "y": u["y_limit_up"].to_numpy(dtype="int64")}))
        if l1_trades:
            l1_rows.extend(l1_trades)
        my_rows.extend(book_trades(ticker, A, board, cal, counters))
        if verbose and (i + 1) % 500 == 0:
            print(f"          ... {i + 1}/{len(files)} files ({time.time() - t0:.0f}s)",
                  flush=True)

    events = pd.concat(ev_frames, ignore_index=True)
    trades = pd.DataFrame(my_rows, columns=TRADE_COLS)
    l1 = pd.DataFrame(l1_rows, columns=rider.TRADE_COLS)
    pairs = pd.concat(pair_rows, ignore_index=True) if pair_rows else pd.DataFrame(
        columns=["board", "target_dk", "y"])

    for f in (events, trades, l1):
        f["year"] = f["date"].dt.year.astype(np.int16)
    l1["era"] = np.where(l1["date"] < rider.SPLIT_DATE, "fit", "holdout")

    meta = {
        "files_found": len(files), "tickers_kept": kept, "tickers_skipped_st": skipped_st,
        "tickers_skipped_thin_or_unreadable": skipped_thin,
        "st_cohort": st_note,
        "limit_up_days": int(len(events)),
        "limit_up_days_with_usable_next_bar": int(events["y_ok"].sum()),
        "entries_fillable": int(len(l1) // max(1, len(RULES))),
        "sealed_board_days": counters["sealed_days"],
        "broken_board_days_touch_and_fail": counters["broken_days"],
        "this_lane_entries": int(len(trades) // max(1, len(RULES))),
        "unconditional_next_bar_limit_up": {
            b: {"usable_ticker_days": v[0], "next_bar_limit_up": v[1],
                "rate_pct": _r(100.0 * v[1] / v[0]) if v[0] else None}
            for b, v in sorted(uncond.items())},
        "forward_chain": {
            "note": CLOSURE_NOTE,
            "steps_admitted_only_because_the_exchange_was_shut":
                counters["closure_steps_admitted"],
            "longest_such_gap_days": counters["closure_max_gap_days"],
            "steps_refused_as_name_specific_suspensions":
                counters["suspension_steps_refused"],
        },
    }
    usable_dates = {b: cal[v] for b, v in sorted(ud.items())}
    usable_dates["GLOBAL"] = cal[np.logical_or.reduce(list(ud.values()))]
    return (events, trades, l1, pairs, ser, cal, dial_meta, meta, usable_dates,
            time.time() - t0)


# ── STAGE 1b — parity gates ──────────────────────────────────────────────────

def l1_parity(meta: dict, l1: pd.DataFrame) -> dict:
    rows = []
    worst = 0.0
    for era in ("fit", "holdout"):
        g = l1[(l1["board"] == "main") & (l1["era"] == era)]
        for rule, (pub_n, pub_mean) in sorted(L1_PARITY_TARGETS["main_book"][era].items()):
            cell = g[g["rule"] == rule]
            x = cell["ret"].to_numpy(dtype="float64")
            x = x[np.isfinite(x)]
            m = 100.0 * float(x.mean()) if x.size else float("nan")
            d = abs(m - pub_mean) if np.isfinite(m) else float("nan")
            worst = max(worst, d if np.isfinite(d) else 0.0)
            rows.append({"era": era, "rule": rule, "published_n": pub_n,
                         "measured_n": int(x.size), "delta_n": int(x.size) - pub_n,
                         "published_mean_pct": pub_mean, "measured_mean_pct": _r(m, 3),
                         "delta_pp": _r(d, 4),
                         "match": bool(int(x.size) == pub_n and np.isfinite(d)
                                       and d <= L1_PARITY_TOL_PCT)})
    counts = [{"field": k, "published": v, "measured": meta.get(k),
               "match": bool(meta.get(k) == v)}
              for k, v in sorted(L1_PARITY_TARGETS.items()) if k != "main_book"]
    counts_ok = all(c["match"] for c in counts)
    rows_ok = all(r["match"] for r in rows)
    return {
        "reference": ("research/cn_prophet_audit/CONTINUATION_RIDER_V1_2026-08-08.json "
                      "(PR #5061, branch claude/cn-limit-w1-rider), meta + "
                      "c2_entry_book.by_era for board=main, N_cohort=ALL, band=ALL"),
        "why": ("L1's own process_ticker is RUN here, not paraphrased, so this gate proves "
                "this lane is standing on L1's panel before any of its own findings are read. "
                "It is a comparison against PUBLISHED, adversarially-reviewed output rather "
                "than a self-comparison."),
        "panel_counts": counts, "main_book_cells": rows,
        "verdict": ("PASS — L1's panel and its published book both reproduce exactly"
                    if (counts_ok and rows_ok) else
                    "MISMATCH — do not read anything below until resolved"),
    }


def closure_parity(l1: pd.DataFrame, trades: pd.DataFrame) -> dict:
    """What the closure-tolerant chain actually CHANGED, trade by trade, against L1's book.

    The amendment is only honest if its footprint is measured rather than asserted.  Every
    L1 trade must appear here with the same entry; the difference set is exactly the trades
    whose holding chain crossed a market closure.
    """
    a = l1[["date", "ticker", "rule", "entry_px", "ret", "forced_close"]].copy()
    b = trades[trades["cohort"] == "sealed"][
        ["date", "ticker", "rule", "entry_px", "ret", "forced_close",
         "complete_window"]].copy()
    m = a.merge(b, on=["date", "ticker", "rule"], how="outer", suffixes=("_l1", "_w3"),
                indicator=True)
    both = m[m["_merge"] == "both"]
    same_entry = np.isclose(both["entry_px_l1"].to_numpy(dtype="float64"),
                            both["entry_px_w3"].to_numpy(dtype="float64"),
                            rtol=0, atol=1e-9)
    dr = np.abs(both["ret_l1"].to_numpy(dtype="float64")
                - both["ret_w3"].to_numpy(dtype="float64"))
    moved = both[dr > 1e-12]
    healed = moved[moved["forced_close_l1"].astype(bool)
                   & ~moved["forced_close_w3"].astype(bool)]
    return {
        "l1_trades": int(len(a)), "this_lane_sealed_trades": int(len(b)),
        "matched_on_(date,ticker,rule)": int(len(both)),
        "only_in_l1": int((m["_merge"] == "left_only").sum()),
        "only_here": int((m["_merge"] == "right_only").sum()),
        "entry_price_identical_on_matched": int(same_entry.sum()),
        "trades_whose_return_moved": int(len(moved)),
        "of_which_l1_had_force_closed_and_this_lane_exits_normally": int(len(healed)),
        "share_of_trades_moved_pct": _r(100.0 * len(moved) / max(1, len(both)), 4),
        "reading": ("The two books are the same book except on chains that crossed an "
                    "exchange closure. Every moved trade is a window L1 truncated at a "
                    "mark-to-market close and this lane carries to a real open."),
        # Amendment A7: this block is SEALED-ONLY (it compares against L1, which has no broken
        # cohort), so a both-cohort incomplete count sitting inside it invited the reader to
        # divide it by a sealed denominator.  Split and labelled.
        "incomplete_windows_excluded_from_the_priced_book": {
            "sealed_cohort_this_block's_population": int(
                (~trades[trades["cohort"] == "sealed"]["complete_window"].astype(bool)).sum()),
            "broken_cohort_not_in_this_block": int(
                (~trades[trades["cohort"] == "broken"]["complete_window"].astype(bool)).sum()),
            "both_cohorts_total": int((~trades["complete_window"].astype(bool)).sum()),
            "note": ("Only the sealed count is commensurable with l1_trades / "
                     "this_lane_sealed_trades above; the broken cohort has no L1 counterpart."),
        },
    }


def split_gate(usable_dates: dict[str, np.ndarray]) -> dict:
    """Re-derive W2-A's splits from this lane's PANEL date set and compare to the frozen ones.

    The date set has to be the same object W2-A split: the dates on which SOME name had a
    usable ticker-day (a live bar with a usable successor), NOT the dates that happen to carry
    a limit-up event.  The event-date set is a strict subset and re-deriving 70% of it lands
    somewhere else entirely, which would make this gate report a drift that is really its own
    mis-specification.
    """
    rows = []
    for board in ("GLOBAL", "chinext", "star"):
        s = BOARD_SPLITS["main" if board == "GLOBAL" else board]
        d = np.sort(usable_dates["GLOBAL" if board == "GLOBAL" else board])
        d = d[d >= int(_daykey([pd.Timestamp(s["era_start"])])[0])]
        i = int(len(d) * FIT_FRACTION)
        got = str(np.datetime64(int(d[i]), "D")) if len(d) > i else None
        rows.append({
            "board": ("GLOBAL (all boards pooled; main uses it)" if board == "GLOBAL"
                      else board),
            "frozen_split_date": s["split_date"], "rederived_split_date": got,
            "match": bool(got == s["split_date"]),
            "published_fit_dates": s["published_fit_dates"], "rederived_fit_dates": int(i),
            "published_holdout_dates": s["published_holdout_dates"],
            "rederived_holdout_dates": int(len(d) - i),
            "usable_panel_dates": int(len(d))})
    return {
        "frozen": BOARD_SPLITS, "provenance": SPLIT_PROVENANCE, "rederivation": rows,
        "why_frozen_wins": ("The FROZEN dates are used regardless of the re-derivation, "
                            "because a split re-derived from THIS lane's row set would land "
                            "somewhere slightly different and make this receipt "
                            "non-comparable with the one whose finding it follows up. The "
                            "re-derivation is a gate on drift, not a source."),
        "verdict": ("PASS — every re-derived boundary lands on the frozen one, with W2-A's "
                    "published fit/holdout date counts reproduced"
                    if all(r["match"] for r in rows) else
                    "DRIFT — a re-derived boundary differs; the FROZEN dates are still used "
                    "and the difference is printed here rather than absorbed"),
    }


# ── STAGE 2 — the dial join, the terciles, the corruption arms ───────────────

def dial_frames(ser: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """One (board, daykey) -> dial value frame per arm.  Cuts are refit per arm downstream.

    The single-draw `corrupt_perm` arm is gone (amendment A1); permutation lives in
    permutation_nulls() as a distribution over N_PERM_DRAWS draws under two schemes.
    """
    out = {}
    for arm in ("true", "corrupt_lag1", "corrupt_lead1"):
        parts = []
        for b, g in ser.groupby("board", sort=True):
            g = g.sort_values("date").reset_index(drop=True)
            v = g[REGIME_COL].to_numpy(dtype="float64").copy()
            if arm == "corrupt_lag1":
                v = np.r_[np.nan, v[:-1]]
            elif arm == "corrupt_lead1":
                v = np.r_[v[1:], np.nan]
            parts.append(pd.DataFrame({"board": str(b), "dk": _daykey(g["date"]), "dial": v}))
        out[arm] = pd.concat(parts, ignore_index=True)
    return out


def attach_dial(frame: pd.DataFrame, dial: pd.DataFrame) -> np.ndarray:
    left = pd.DataFrame({"board": frame["board"].astype(str).to_numpy(),
                         "dk": _daykey(frame["date"])})
    return left.merge(dial, on=["board", "dk"], how="left",
                      validate="many_to_one")["dial"].to_numpy(dtype="float64")


def tercile_edges(dial: pd.DataFrame, board: str, era_start: pd.Timestamp,
                  split_date: pd.Timestamp) -> list[float]:
    """Quantile edges over the board's OWN FIT-WINDOW SESSIONS (dates, not rows)."""
    lo, hi = int(_daykey([era_start])[0]), int(_daykey([split_date])[0])
    g = dial[(dial["board"] == board) & (dial["dk"] >= lo) & (dial["dk"] < hi)]
    v = g["dial"].to_numpy(dtype="float64")
    v = v[np.isfinite(v)]
    if v.size < 30:
        return []
    qs = np.linspace(0.0, 1.0, N_STRATA + 1)[1:-1]
    return [float(x) for x in np.unique(np.quantile(v, qs))]


def assign_stratum(vals: np.ndarray, edges: list[float]) -> np.ndarray:
    out = np.full(vals.shape, UNKNOWN_STRATUM, dtype=np.int16)
    fin = np.isfinite(vals)
    if edges:
        out[fin] = np.searchsorted(np.asarray(edges, dtype="float64"),
                                   vals[fin], side="right").astype(np.int16)
    else:
        out[fin] = 0
    return out


def label_frame(frame: pd.DataFrame, dial: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Attach dial, split label and stratum label, per board, with all cuts fit-window-only."""
    f = frame.copy()
    f["dial"] = attach_dial(f, dial)
    f["split"] = ""
    f["stratum"] = UNKNOWN_STRATUM
    f["in_fit_core"] = False
    info = {}
    keep = np.zeros(len(f), dtype=bool)
    for board, s in sorted(BOARD_SPLITS.items()):
        era, cal_s, sd = (pd.Timestamp(s["era_start"]), pd.Timestamp(s["calib_start"]),
                          pd.Timestamp(s["split_date"]))
        m = (f["board"].astype(str) == board) & (f["date"] >= era)
        if not m.any():
            continue
        keep |= m.to_numpy()
        edges = tercile_edges(dial, board, era, sd)
        st = assign_stratum(f.loc[m, "dial"].to_numpy(dtype="float64"), edges)
        f.loc[m, "stratum"] = st
        f.loc[m, "split"] = np.where(f.loc[m, "date"] < sd, "fit", "holdout")
        f.loc[m, "in_fit_core"] = (f.loc[m, "date"] < cal_s).to_numpy()
        sub = f[m]
        occ = {}
        for name, sl in (("fit", sub[sub["split"] == "fit"]),
                         ("holdout", sub[sub["split"] == "holdout"])):
            tot = max(1, len(sl))
            occ[name] = {STRATUM_LABELS[k]: _r(100.0 * float((sl["stratum"] == k).sum()) / tot,
                                               3)
                         for k in sorted(STRATUM_LABELS)}
        # SESSION masses — the cut's own units.  Printed beside the ROW masses because the two
        # differ structurally and confusing them would misread the cut as broken: the cut is a
        # tercile of SESSIONS, but a hot session carries far more board-days than a cold one,
        # so the ROW mass is skewed toward T3 by construction and not by a bad cut.
        smass = {}
        bd = dial[dial["board"] == board]
        for name, lo, hi in (("fit", int(_daykey([era])[0]), int(_daykey([sd])[0])),
                             ("holdout", int(_daykey([sd])[0]), 10 ** 9)):
            gg = bd[(bd["dk"] >= lo) & (bd["dk"] < hi)]
            st2 = assign_stratum(gg["dial"].to_numpy(dtype="float64"), edges)
            tot = max(1, st2.size)
            smass[name] = {STRATUM_LABELS[k]: _r(100.0 * float((st2 == k).sum()) / tot, 3)
                           for k in sorted(STRATUM_LABELS)}
        known = sub[sub["stratum"] != UNKNOWN_STRATUM]
        biggest = 0.0
        if len(known):
            vc = known["stratum"].value_counts(normalize=True)
            biggest = 100.0 * float(vc.max())
        empty = sorted(STRATUM_LABELS[k] for k in (0, 1, 2)
                       if smass["fit"].get(STRATUM_LABELS[k], 0.0) == 0.0)
        info[board] = {
            "edges_from_fit_window_sessions": [round(e, 6) for e in edges],
            "occupancy_pct_of_SESSIONS_by_split": smass,
            "occupancy_pct_of_rows_by_split": occ,
            "realised_oos_mass_note": (
                "TWO masses are printed and they are different objects. The SESSION masses are "
                "the cut's own units: fit-side terciles are 33/33/33 by construction and the "
                "HOLDOUT session masses are the realised out-of-sample masses of a frozen cut "
                "— they are not 33/33/33 and are not expected to be, because W3-A measured "
                "that a frozen quantile cut is not its nominal quantile out of sample and the "
                "cause is distribution shift, not ties. The ROW masses are skewed toward the "
                "hot stratum even on the fit side BY CONSTRUCTION, because a hot session "
                "carries many more board-days than a cold one; that skew is the dial doing its "
                "job, not a broken cut. Read both before reading any stratum label."),
            "empty_fit_strata": empty,
            "dial_is_degenerate": bool(biggest >= 99.0 or empty),
            "degeneracy_reading": (
                ("DEGENERATE — the fit-window strata " + ", ".join(empty) + " are EMPTY. A "
                 "quantile cut cannot separate a point mass: this board sits at exactly 0.0 "
                 "on more than a third of its sessions (it prints no continuation pairs at "
                 "all), so the lowest edge lands ON zero and every zero session sorts to the "
                 "stratum above it. The surviving strata then wear labels they have not "
                 "earned — the real contrast this board supplies is PRINTED-A-RATE vs "
                 "NO-PAIRS. Every regime result on this board reads as a COVERAGE NULL and "
                 "no family on it clears the fit-core floor anyway.")
                if empty else
                ("DEGENERATE — one stratum holds >=99% of this board's rows that carry a dial "
                 "print, so the dial orders nothing here.")
                if biggest >= 99.0 else
                "The dial separates this board's rows into occupied strata; labels are "
                "meaningful."),
        }
    f = f[keep].copy()
    f["stratum_label"] = f["stratum"].map(STRATUM_LABELS)
    f["rung_label"] = np.where(f["rung"].to_numpy() >= N_COHORT_CAP,
                               f"N{N_COHORT_CAP}plus",
                               "N" + f["rung"].astype(str))
    return f, info


# ── STAGE 3 — the primary table, the t-census, the era tables ────────────────

def family_floor(events_l: pd.DataFrame) -> dict[tuple, dict]:
    """Fit-core continuation positives per (board, rung, stratum) family.

    A "positive" is a realised next-bar limit-up close on a fit-CORE board day in that family —
    the outcome the cell is about, counted on W2-A's fit_core slice so that the 150 floor means
    here exactly what it meant there.  A family under the floor is SKIPPED, never re-cut.
    """
    out = {}
    core = events_l[events_l["in_fit_core"] & events_l["y_ok"]
                    & (events_l["cohort"] == "sealed")]
    for (b, rl, sl), g in core.groupby(["board", "rung_label", "stratum_label"], sort=True):
        pos = int(g["y_limit_up"].sum())
        out[(b, rl, sl)] = {"fit_core_board_days": int(len(g)),
                            "fit_core_continuation_positives": pos,
                            "thin_skip": bool(pos < MIN_FIT_CORE_POSITIVES)}
    return out


def rate_table(events_l: pd.DataFrame) -> list[dict]:
    """P(next board) and its FILLABLE-CONDITIONAL twin, per cell, per split."""
    rows = []
    u = events_l[events_l["y_ok"] & (events_l["cohort"] == "sealed")]
    for (b, rl, sl, sp), g in u.groupby(["board", "rung_label", "stratum_label", "split"],
                                        sort=True):
        n = len(g)
        real = int(g["y_limit_up"].sum())
        unf = int(g["unfillable_open"].sum())
        fill = g[~g["unfillable_open"].astype(bool)]
        rec = {"board": b, "rung": rl, "stratum": sl, "split": sp, "board_days": n,
               "p_next_board": rate_block(real, n),
               "p_unfillable_open": rate_block(unf, n),
               "FILLABILITY_TAX_pct": _r(100.0 * int(
                   (g["y_limit_up"] & g["unfillable_open"]).sum()) / max(1, real)),
               "p_next_board_GIVEN_fillable_entry": rate_block(
                   int(fill["y_limit_up"].sum()), len(fill)),
               "p_limit_down_close": rate_block(int(g["y_limit_down"].sum()), n),
               "n_dates": int(g["date"].nunique()), "n_names": int(g["ticker"].nunique())}
        rows.append(rec)
    return rows


def primary_book(trades_l: pd.DataFrame, floors: dict) -> tuple[list[dict], dict, list[dict]]:
    priced = trades_l[trades_l["complete_window"].astype(bool)
                      & (trades_l["cohort"] == "sealed")]
    trunc = trades_l[~trades_l["complete_window"].astype(bool)
                     & (trades_l["cohort"] == "sealed")]
    rows = []
    for (b, rl, sl, rule, sp), g in priced.groupby(
            ["board", "rung_label", "stratum_label", "rule", "split"], sort=True):
        fam = floors.get((b, rl, sl), {})
        rec = {"board": b, "rung": rl, "stratum": sl, "rule": rule, "split": sp,
               "fit_core_continuation_positives": fam.get(
                   "fit_core_continuation_positives", 0),
               "thin_skip_family": bool(fam.get("thin_skip", True))}
        rec.update(book_cell(g))
        rows.append(rec)
    idx = {(r["board"], r["rung"], r["stratum"], r["rule"], r["split"]): r for r in rows}

    census, clears = [], []
    acc = {"all": {"tf": -99.0, "th": -99.0, "nf": 0, "nh": 0, "nb": 0, "n": 0},
           "non_thin": {"tf": -99.0, "th": -99.0, "nf": 0, "nh": 0, "nb": 0, "n": 0}}
    pairs = sorted({(k[0], k[1], k[2], k[3]) for k in idx})
    for key in pairs:
        f, h = idx.get(key + ("fit",)), idx.get(key + ("holdout",))
        tf = (f or {}).get("date_clustered_t")
        th = (h or {}).get("date_clustered_t")
        thin = bool((f or h or {}).get("thin_skip_family", True))
        for scope in ("all",) if thin else ("all", "non_thin"):
            a = acc[scope]
            a["n"] += 1
            if tf is not None:
                a["tf"] = max(a["tf"], tf)
                a["nf"] += int(tf >= BOOK_T_BAR)
            if th is not None:
                a["th"] = max(a["th"], th)
                a["nh"] += int(th >= BOOK_T_BAR)
            if tf is not None and th is not None and tf >= BOOK_T_BAR and th >= BOOK_T_BAR:
                a["nb"] += 1
        census.append({"board": key[0], "rung": key[1], "stratum": key[2], "rule": key[3],
                       "fit_t": tf, "holdout_t": th,
                       "fit_net_pct": (f or {}).get("date_eq_weight_net_pct"),
                       "holdout_net_pct": (h or {}).get("date_eq_weight_net_pct"),
                       "thin_skip_family": thin})
        if clears_bar(f, h) and not thin:
            clears.append({"board": key[0], "rung": key[1], "stratum": key[2], "rule": key[3],
                           "fit_net_pct": f.get("date_eq_weight_net_pct"),
                           "fit_t": tf, "holdout_net_pct": h.get("date_eq_weight_net_pct"),
                           "holdout_t": th})

    # THE NEGATIVE SIDE, counted rather than described.  A null that is merely "not positive"
    # and a null that is SIGNIFICANTLY NEGATIVE IN BOTH WINDOWS are different findings, and
    # the second one is what this lane found; it would be dishonest to leave it as prose.
    nt = [c for c in census if not c["thin_skip_family"]]
    both_neg = [c for c in nt if (c["fit_net_pct"] or 0) < 0 and (c["holdout_net_pct"] or 0) < 0]
    both_sig = [c for c in nt if (c["fit_t"] is not None and c["holdout_t"] is not None
                                  and c["fit_t"] <= -BOOK_T_BAR and c["holdout_t"] <= -BOOK_T_BAR)]
    neg_census = {
        "non_thin_cells": len(nt),
        "cells_net_negative_in_BOTH_windows": len(both_neg),
        "cells_with_t_at_or_BELOW_minus_bar_in_BOTH_windows": len(both_sig),
        "reading": ("This is the shape of the result. The pre-registered question asked "
                    "whether any cell turns net-POSITIVE; the answer is none. What the same "
                    "grid also shows is that the losses are not noise around zero — they are "
                    "date-clustered-significant in both windows in most non-thin cells, which "
                    "is a stronger statement than 'no edge found'."),
    }

    def _c(scope: str) -> dict:
        a = acc[scope]
        return {"cells": a["n"],
                "max_fit_date_clustered_t": _r(a["tf"], 2) if a["tf"] > -99 else None,
                "max_holdout_date_clustered_t": _r(a["th"], 2) if a["th"] > -99 else None,
                "max_date_clustered_t_either_window":
                    _r(max(a["tf"], a["th"]), 2) if max(a["tf"], a["th"]) > -99 else None,
                "cells_with_fit_t_at_or_above_bar": a["nf"],
                "cells_with_holdout_t_at_or_above_bar": a["nh"],
                "cells_with_t_at_or_above_bar_in_BOTH_windows": a["nb"]}
    verdict = {
        "cells_total": len(census),
        "t_census_all_cells": _c("all"),
        "t_census_non_thin_families_only": _c("non_thin"),
        "READ_THE_NON_THIN_CENSUS": (
            "The all-cells census includes families below the "
            f"{MIN_FIT_CORE_POSITIVES}-fit-core-positive floor, where a two-session cell can "
            "print an enormous t off nothing. Those families were declared THIN-SKIP before "
            "the data was seen and cannot clear the decision bar; the non-thin census is the "
            "number to read, and the all-cells census is printed beside it so the skip is "
            "auditable rather than invisible."),
        "cells_clearing_the_FULL_decision_bar": len(clears),
        "clears": clears,
        "negative_side_census": neg_census,
        "T_CENSUS_IS_THE_STATEMENT": (
            "The headline is this census, not the best surviving cell. With this many cells "
            "examined, a handful of one-sided survivors is the coin-flip expectation; what "
            "carries information is the maximum date-clustered t reached across ALL of them "
            "and how many clear in BOTH windows."),
    }
    trunc_rows = []
    for (b, rl, sl, rule, sp), g in trunc.groupby(
            ["board", "rung_label", "stratum_label", "rule", "split"], sort=True):
        rec = {"board": b, "rung": rl, "stratum": sl, "rule": rule, "split": sp,
               "EXCLUDED_FROM_THE_PRICED_BOOK": True, "n": int(len(g))}
        rec.update(rider.ret_block(g["ret"].to_numpy(), g["ticker"].to_numpy(),
                                   g["date"].to_numpy()))
        trunc_rows.append(rec)
    return rows, verdict, trunc_rows


def dial_orderings(rates: list[dict], rows: list[dict], floors: dict) -> dict:
    """Does the dial order PROBABILITY and EXPECTANCY in the same direction?

    This is the structural question underneath the primary null, and it is computed rather
    than narrated: for each (board, rung, split) the cold->mid->hot sequence of P(next board),
    of the FILLABLE-CONDITIONAL P, and of the E3 date-equal-weighted net expectancy.
    """
    ri = {(r["board"], r["rung"], r["stratum"], r["split"]): r for r in rates}
    bi = {(r["board"], r["rung"], r["stratum"], r["rule"], r["split"]): r for r in rows}
    out, agree = [], {"prob_up": 0, "exp_down": 0, "both": 0, "n": 0}
    for (b, rl, sp) in sorted({(r["board"], r["rung"], r["split"]) for r in rates}):
        if any(floors.get((b, rl, s), {}).get("thin_skip", True)
               for s in ("T1_cold", "T2_mid", "T3_hot")):
            continue
        seq = [ri.get((b, rl, s, sp)) for s in ("T1_cold", "T2_mid", "T3_hot")]
        bk = [bi.get((b, rl, s, HEADLINE_CELL["rule"], sp))
              for s in ("T1_cold", "T2_mid", "T3_hot")]
        if any(x is None for x in seq) or any(x is None for x in bk):
            continue
        p = [x["p_next_board"]["rate_pct"] for x in seq]
        pf = [x["p_next_board_GIVEN_fillable_entry"]["rate_pct"] for x in seq]
        e = [x["date_eq_weight_net_pct"] for x in bk]
        pu = bool(p[0] <= p[1] <= p[2])
        ed = bool(e[0] >= e[1] >= e[2])
        agree["n"] += 1
        agree["prob_up"] += int(pu)
        agree["exp_down"] += int(ed)
        agree["both"] += int(pu and ed)
        out.append({
            "board": b, "rung": rl, "split": sp,
            "p_next_board_pct_cold_mid_hot": p,
            "p_next_board_rises_with_the_dial": pu,
            "p_next_board_GIVEN_fillable_pct_cold_mid_hot": pf,
            "raw_hot_minus_cold_pp": _r(p[2] - p[0], 3),
            "fillable_hot_minus_cold_pp": _r(pf[2] - pf[0], 3),
            "spread_surviving_fillability_pct": (
                _r(100.0 * (pf[2] - pf[0]) / (p[2] - p[0]), 1) if (p[2] - p[0]) else None),
            "E3_date_eq_net_pct_cold_mid_hot": e,
            "expectancy_falls_as_the_dial_rises": ed,
        })
    return {
        "question": ("The dial is a LEVEL instrument (W2-A). Does the level it raises — "
                     "P(continuation) — travel in the same direction as what a taker earns?"),
        "rows": out,
        "summary": dict(agree, reading=(
            f"P(next board) rises with the dial in {agree['prob_up']} of {agree['n']} "
            f"(board x rung x window) cells; the E3 net expectancy FALLS as the dial rises in "
            f"{agree['exp_down']} of {agree['n']}; both hold together in {agree['both']}. "
            "Where both hold, the dial is a correct probability instrument pointed at a "
            "wrong-signed payoff — which is Wave 1's anti-monotone finding reproduced on the "
            "regime axis rather than the gap axis.")),
        "spread_note": ("spread_surviving_fillability_pct is the share of the raw cold->hot "
                        "probability spread that survives conditioning on a buyable open. It "
                        "is the price of admission expressed as a fraction of the edge."),
    }


def era_tables(trades_l: pd.DataFrame, floors: dict) -> dict:
    """Yearly sign tables.  Full detail for the headline family; sign summary for every cell."""
    priced = trades_l[trades_l["complete_window"].astype(bool)
                      & (trades_l["cohort"] == "sealed")]
    hl = priced[(priced["board"] == HEADLINE_CELL["board"])
                & (priced["rung_label"] == HEADLINE_CELL["rung"])
                & (priced["rule"] == HEADLINE_CELL["rule"])]
    detail = []
    for (sl, y), g in hl.groupby(["stratum_label", "year"], sort=True):
        d = date_clustered(g["ret"].to_numpy(), g["date"].to_numpy())
        detail.append({"stratum": sl, "year": int(y), "n": int(len(g)),
                       "n_dates": d.get("n_dates"),
                       "date_eq_weight_net_pct": d.get("date_eq_weight_net_pct"),
                       "sign": ("+" if (d.get("date_eq_weight_net_pct") or 0) > 0 else "-")})
    summary = []
    for (b, rl, sl, rule), g in priced.groupby(
            ["board", "rung_label", "stratum_label", "rule"], sort=True):
        yr = g.groupby("year", sort=True).apply(
            lambda x: date_clustered(x["ret"].to_numpy(),
                                     x["date"].to_numpy()).get("date_eq_weight_net_pct"),
            include_groups=False)
        v = yr.dropna().to_numpy(dtype="float64")
        summary.append({"board": b, "rung": rl, "stratum": sl, "rule": rule,
                        "years": int(v.size), "years_positive": int((v > 0).sum()),
                        "years_positive_pct": _r(100.0 * (v > 0).sum() / max(1, v.size)),
                        "thin_skip_family": bool(
                            floors.get((b, rl, sl), {}).get("thin_skip", True))})
    return {"note": ("Era tables are mandatory here because the era swing dominates every "
                     "per-name feature in this program: main limit-ups were 18.6% concentrated "
                     "in 2015 and first->second board swings ran 7.93%->24.18% by year."),
            "headline_family_by_year": detail, "sign_summary_all_cells": summary}


# ── STAGE 4 — secondary (a): the broken-board lead, by dial state ────────────

def broken_vs_sealed(trades_l: pd.DataFrame, floors: dict) -> dict:
    """Paired, same-session, matched-PRIOR-rung lead of the broken cohort over the sealed one.

    Matching on PRIOR rung is the only reading under which the two cohorts share a cell: a
    first break and a first board both enter the day carrying no ladder, and the tolerant
    ladder count at T is 0 for a break by construction.  Pairing on the SESSION removes the
    composition difference — breaks and seals do not occur on the same days in the same
    proportions — which would otherwise arrive wearing a cohort difference's clothes.
    """
    priced = trades_l[trades_l["complete_window"].astype(bool)]
    rows = []
    for (b, sl, pr, rule, sp), g in priced.groupby(
            ["board", "stratum_label", "prior_rung", "rule", "split"], sort=True):
        a = g[g["cohort"] == "broken"]
        s = g[g["cohort"] == "sealed"]
        if not len(a) or not len(s):
            continue
        rec = {"board": b, "stratum": sl, "prior_rung": f"P{int(pr)}", "rule": rule,
               "split": sp, "broken_n": int(len(a)), "sealed_n": int(len(s)),
               "broken_thin": bool(len(a) < THIN_CELL_N)}
        rec.update(paired_date_lead(a["ret"].to_numpy(), a["date"].to_numpy(),
                                    s["ret"].to_numpy(), s["date"].to_numpy()))
        rec["below_paired_date_floor"] = bool(rec.get("paired_dates", 0) < BOOK_MIN_DATES)
        rows.append(rec)
    # does the lead CONCENTRATE in dial-high states?  compare T3_hot against T1_cold on the
    # pre-registered primary rule, per board/prior-rung/split.  Both arms' ABSOLUTE levels
    # travel with the lead, because a lead over a losing arm is not a positive book and the
    # single easiest way to misread this table is to read the lead alone.
    conc = []
    idx = {(r["board"], r["stratum"], r["prior_rung"], r["rule"], r["split"]): r
           for r in rows}
    for (b, pr, rule, sp) in sorted({(r["board"], r["prior_rung"], r["rule"], r["split"])
                                     for r in rows}):
        hot = idx.get((b, "T3_hot", pr, rule, sp))
        cold = idx.get((b, "T1_cold", pr, rule, sp))
        if not hot or not cold:
            continue
        lh, lc = hot.get("lead_pp"), cold.get("lead_pp")
        conc.append({"board": b, "prior_rung": pr, "rule": rule, "split": sp,
                     "lead_pp_T3_hot": lh, "t_T3_hot": hot.get("lead_date_clustered_t"),
                     "broken_net_pct_T3_hot": hot.get("arm_a_net_pct_on_paired_dates"),
                     "sealed_net_pct_T3_hot": hot.get("arm_b_net_pct_on_paired_dates"),
                     "lead_pp_T1_cold": lc, "t_T1_cold": cold.get("lead_date_clustered_t"),
                     "broken_net_pct_T1_cold": cold.get("arm_a_net_pct_on_paired_dates"),
                     "sealed_net_pct_T1_cold": cold.get("arm_b_net_pct_on_paired_dates"),
                     "hot_minus_cold_pp": (_r(lh - lc, 3)
                                           if (lh is not None and lc is not None) else None),
                     "below_paired_date_floor": bool(hot["below_paired_date_floor"]
                                                     or cold["below_paired_date_floor"])})
    qual = [r for r in rows if not r["below_paired_date_floor"]]
    max_t = max([abs(r.get("lead_date_clustered_t") or 0.0) for r in rows], default=0.0)
    max_tq = max([abs(r.get("lead_date_clustered_t") or 0.0) for r in qual], default=0.0)
    n_pos_broken = sum(1 for r in qual
                       if (r.get("arm_a_net_pct_on_paired_dates") or -1.0) > 0)

    # The broken arm's OWN book against the SAME decision bar.  NOT pre-registered — it is a
    # descriptive readout forced by the lead table, because a receipt that reports "the broken
    # arm is net-positive in N cells" and then never says whether any of them survives a
    # two-window t bar is burying its own most interesting number.  Labelled, censused, and
    # never promoted.
    own = {}
    for (b, sl, pr, rule, sp), g in priced[priced["cohort"] == "broken"].groupby(
            ["board", "stratum_label", "prior_rung", "rule", "split"], sort=True):
        own[(b, sl, f"P{int(pr)}", rule, sp)] = date_clustered(
            g["ret"].to_numpy(), g["date"].to_numpy())
    own_rows, own_clears = [], []
    own_max = -99.0
    for k in sorted({k[:4] for k in own}):
        f, h = own.get(k + ("fit",)), own.get(k + ("holdout",))
        tf, th = (f or {}).get("date_clustered_t"), (h or {}).get("date_clustered_t")
        for t in (tf, th):
            if t is not None:
                own_max = max(own_max, t)
        rec = {"board": k[0], "stratum": k[1], "prior_rung": k[2], "rule": k[3],
               "fit_net_pct": (f or {}).get("date_eq_weight_net_pct"), "fit_t": tf,
               "fit_dates": (f or {}).get("n_dates"),
               "holdout_net_pct": (h or {}).get("date_eq_weight_net_pct"), "holdout_t": th,
               "holdout_dates": (h or {}).get("n_dates")}
        own_rows.append(rec)
        if clears_bar(f, h):
            own_clears.append(rec)
    broken_own = {
        "STATUS": ("DESCRIPTIVE, NOT PRE-REGISTERED. This lane pre-registered the LEAD, not "
                   "the broken arm's own book. These cells are reported because the lead "
                   "table produced them, and they carry the full multiplicity of the cell "
                   "grid with no pre-registered hypothesis behind any single one. Nothing "
                   "here is a finding; it is the number a reader would otherwise have to "
                   "guess at."),
        "decision_bar": DECISION_BAR,
        "cells": own_rows,
        "max_date_clustered_t_either_window": _r(own_max, 2) if own_max > -99 else None,
        "cells_clearing_the_bar_in_BOTH_windows": len(own_clears),
        "clears": own_clears,
    }
    return {
        "question": PREREGISTRATION["secondary_a"],
        "cohorts": {
            "sealed": "closed at the tolerant limit at T (L1's entry cohort)",
            "broken": ("TOUCHED the limit intraday at T and closed below it — the failed-seal "
                       "/ 炸板 class of the event-taxonomy ruling, derived from THIS panel on "
                       "the tolerant basis so both arms share one definition"),
        },
        "matching": ("PRIOR rung (the tolerant board streak ending at T-1, capped at 3+), "
                     "same board, same dial tercile, same exit rule, same split, and paired "
                     "on the SESSION."),
        "primary_rule": HEADLINE_CELL["rule"],
        "paired_date_floor": BOOK_MIN_DATES,
        "A_LEAD_IS_NOT_A_BOOK": (
            "Every number in this section is a RELATIVE quantity: how much less the broken "
            "cohort loses than the sealed one on the same sessions. Both arms' absolute "
            "date-clustered nets travel beside every lead precisely so this cannot be misread. "
            "cells_where_the_broken_arm_is_itself_net_positive below is the count that would "
            "matter for a book, and it is reported on cells clearing the "
            f"{BOOK_MIN_DATES}-paired-session floor only."),
        "cells": rows, "concentration_hot_vs_cold": conc,
        "max_abs_lead_date_clustered_t_ALL_cells": _r(max_t, 2),
        "max_abs_lead_date_clustered_t_above_the_paired_date_floor": _r(max_tq, 2),
        "cells_above_the_paired_date_floor": len(qual),
        "cells_where_the_broken_arm_is_itself_net_positive": n_pos_broken,
        "broken_arm_own_book_descriptive": broken_own,
    }


# ── STAGE 5 — secondary (b): is the AUCTION pricing the regime? ──────────────

CLUSTER_NOTE = (
    "AMENDMENT A4. The affirmative quantities in this section — entry availability, the "
    "fillability tax, the mean open gap — were the only numbers in the receipt NOT clustered: "
    "they were pooled board-day shares carrying IID Wilson bands of about +-1.7 pp, while the "
    "permutation null for the same statistic has an SD of 5-8 pp. An IID band on a quantity "
    "whose real sampling unit is the SESSION understates its uncertainty by roughly the square "
    "root of the trades-per-session count, and every affirmative claim in this receipt rests "
    "on these numbers. They now carry a SESSION CLUSTER BOOTSTRAP "
    f"({BOOT_B} resamples of whole sessions, seed {BOOT_SEED}) beside the pooled point "
    "estimate, and the hot-minus-cold spreads carry a two-sample session bootstrap. The IID "
    "Wilson band is kept beside it so the size of the correction is visible rather than "
    "silently applied."
)
DISJOINT_NOTE = (
    "The dial is CONSTANT WITHIN A DATE (W2-A: it is a level instrument, never a ranker), so a "
    "session belongs to exactly one tercile and the hot and cold arms are DISJOINT session "
    "sets. That is why the spread is a two-sample bootstrap over independent session sets "
    "rather than a paired one, and it is also why no amount of within-date resampling can "
    "narrow it: the comparison lives entirely between sessions."
)


def _sess_ratio(k_s: np.ndarray, n_s: np.ndarray, rng, b: int = BOOT_B) -> dict:
    """Pooled ratio K/N with a session cluster bootstrap. k_s/n_s are PER-SESSION totals."""
    K, N = float(k_s.sum()), float(n_s.sum())
    out = {"sessions": int(k_s.size), "pooled_pct": _r(100.0 * K / N, 3) if N > 0 else None}
    if k_s.size < 2 or N <= 0:
        out["session_bootstrap"] = "NOT TESTABLE — fewer than 2 sessions"
        return out
    idx = rng.integers(0, k_s.size, size=(b, k_s.size))
    bn = n_s[idx].sum(axis=1)
    r = np.where(bn > 0, k_s[idx].sum(axis=1) / np.where(bn > 0, bn, 1.0), np.nan)
    r = r[np.isfinite(r)]
    out["session_cluster_se_pp"] = _r(100.0 * float(r.std(ddof=1)), 3)
    out["session_boot_ci95_pct"] = [_r(100.0 * float(np.percentile(r, 2.5)), 3),
                                    _r(100.0 * float(np.percentile(r, 97.5)), 3)]
    return out


def _sess_spread(kh, nh, kc, nc, rng, b: int = BOOT_B) -> dict:
    """Hot-minus-cold spread over two DISJOINT session sets, two-sample cluster bootstrap."""
    if kh.size < 2 or kc.size < 2 or nh.sum() <= 0 or nc.sum() <= 0:
        return {"status": "NOT TESTABLE — an arm has fewer than 2 sessions"}
    point = 100.0 * (kh.sum() / nh.sum() - kc.sum() / nc.sum())
    ih = rng.integers(0, kh.size, size=(b, kh.size))
    ic = rng.integers(0, kc.size, size=(b, kc.size))
    bnh, bnc = nh[ih].sum(axis=1), nc[ic].sum(axis=1)
    d = 100.0 * (kh[ih].sum(axis=1) / np.where(bnh > 0, bnh, 1.0)
                 - kc[ic].sum(axis=1) / np.where(bnc > 0, bnc, 1.0))
    d = d[np.isfinite(d)]
    sd = float(d.std(ddof=1))
    return {"spread_pp": _r(point, 3),
            "session_cluster_se_pp": _r(sd, 3),
            "session_cluster_t": _r(point / sd, 2) if sd > 0 else None,
            "session_boot_ci95_pp": [_r(float(np.percentile(d, 2.5)), 3),
                                     _r(float(np.percentile(d, 97.5)), 3)],
            "hot_sessions": int(kh.size), "cold_sessions": int(kc.size)}


def _per_session(g: pd.DataFrame, kind: str) -> tuple[np.ndarray, np.ndarray]:
    """Per-session (numerator, denominator) totals for one affirmative quantity."""
    dk = pd.Series(_daykey(g["date"]), index=g.index)
    if kind == "avail":
        k = (~g["unfillable_open"].astype(bool)).astype(float)
        n = pd.Series(1.0, index=g.index)
    elif kind == "tax":
        k = (g["y_limit_up"] & g["unfillable_open"]).astype(float)
        n = g["y_limit_up"].astype(float)
    elif kind == "pnext":
        # P(next board) is an affirmative quantity too, and it was carrying only an IID
        # Wilson band; same defect class as A4 named for availability, so it is clustered here.
        k = g["y_limit_up"].astype(float)
        n = pd.Series(1.0, index=g.index)
    else:                                    # mean gap
        v = g["gap"].to_numpy(dtype="float64")
        ok = np.isfinite(v)
        k = pd.Series(np.where(ok, v, 0.0), index=g.index)
        n = pd.Series(ok.astype(float), index=g.index)
    a = pd.DataFrame({"dk": dk, "k": k, "n": n}).groupby("dk", sort=True).sum()
    a = a[a["n"] > 0]
    return a["k"].to_numpy(dtype="float64"), a["n"].to_numpy(dtype="float64")


def fillable_share_by_dial(events_l: pd.DataFrame) -> dict:
    """Fillable share x dial tercile, per board and per rung.

    If dial-high states make the next open LESS fillable, the auction is rationing access in
    exactly the states the dial says are good, and the paper edge is auctioned away before a
    single return is measured.  This is the mechanism question behind the primary null.
    """
    rng = np.random.default_rng(BOOT_SEED)
    u = events_l[events_l["y_ok"] & (events_l["cohort"] == "sealed")]
    rows, sess = [], {}
    for (b, rl, sl, sp), g in u.groupby(["board", "rung_label", "stratum_label", "split"],
                                        sort=True):
        n = len(g)
        unf = int(g["unfillable_open"].sum())
        real = int(g["y_limit_up"].sum())
        real_unf = int((g["y_limit_up"] & g["unfillable_open"]).sum())
        sess[(b, rl, sl, sp)] = {k: _per_session(g, k)
                                 for k in ("avail", "tax", "gap", "pnext")}
        rows.append({
            "board": b, "rung": rl, "stratum": sl, "split": sp, "board_days": n,
            "entry_availability_pct": _r(100.0 * (n - unf) / max(1, n)),
            "entry_availability_wilson95_pct_IID_for_comparison": [
                _r(100.0 * x) for x in (wilson(n - unf, n) or (float("nan"),) * 2)],
            "entry_availability_session_clustered":
                _sess_ratio(*sess[(b, rl, sl, sp)]["avail"], rng),
            "FILLABILITY_TAX_pct": _r(100.0 * real_unf / max(1, real)),
            "fillability_tax_session_clustered":
                _sess_ratio(*sess[(b, rl, sl, sp)]["tax"], rng),
            "realised_next_boards": real, "of_which_unfillable_open": real_unf,
            "mean_gap_pct": _r(100.0 * float(np.nanmean(g["gap"].to_numpy(dtype="float64")))
                               , 3) if n else None,
            # _sess_ratio already scales by 100, and the gap numerator is a fraction, so its
            # pooled_pct IS the mean gap in percent.
            "mean_gap_session_clustered": _sess_ratio(*sess[(b, rl, sl, sp)]["gap"], rng),
        })
    spread = []
    idx = {(r["board"], r["rung"], r["stratum"], r["split"]): r for r in rows}
    for (b, rl, sp) in sorted({(r["board"], r["rung"], r["split"]) for r in rows}):
        hot, cold = idx.get((b, rl, "T3_hot", sp)), idx.get((b, rl, "T1_cold", sp))
        if not hot or not cold:
            continue
        sh, sc = sess[(b, rl, "T3_hot", sp)], sess[(b, rl, "T1_cold", sp)]
        spread.append({
            "board": b, "rung": rl, "split": sp,
            "entry_availability_pct_T3_hot": hot["entry_availability_pct"],
            "entry_availability_pct_T1_cold": cold["entry_availability_pct"],
            "hot_minus_cold_pp": _r(hot["entry_availability_pct"]
                                    - cold["entry_availability_pct"], 3),
            "availability_spread_session_clustered":
                _sess_spread(*sh["avail"], *sc["avail"], rng),
            "fillability_tax_pct_T3_hot": hot["FILLABILITY_TAX_pct"],
            "fillability_tax_pct_T1_cold": cold["FILLABILITY_TAX_pct"],
            "tax_hot_minus_cold_pp": _r(hot["FILLABILITY_TAX_pct"]
                                        - cold["FILLABILITY_TAX_pct"], 3),
            "tax_spread_session_clustered": _sess_spread(*sh["tax"], *sc["tax"], rng),
            "gap_spread_session_clustered": _sess_spread(*sh["gap"], *sc["gap"], rng),
            "p_next_board_spread_session_clustered":
                _sess_spread(*sh["pnext"], *sc["pnext"], rng),
        })
    # Is availability MONOTONE DECREASING in the dial?  Computed, not eyeballed.
    mono = []
    for (b, rl, sp) in sorted({(r["board"], r["rung"], r["split"]) for r in rows}):
        seq = [idx.get((b, rl, s, sp)) for s in ("T1_cold", "T2_mid", "T3_hot")]
        if any(x is None for x in seq):
            continue
        av = [x["entry_availability_pct"] for x in seq]
        gp = [x["mean_gap_pct"] for x in seq]
        mono.append({
            "board": b, "rung": rl, "split": sp,
            "entry_availability_pct_cold_mid_hot": av,
            "availability_monotone_decreasing": bool(av[0] >= av[1] >= av[2]),
            "mean_gap_pct_cold_mid_hot": gp,
            "gap_monotone_increasing": bool(
                all(x is not None for x in gp) and gp[0] <= gp[1] <= gp[2]),
            "board_days_cold_mid_hot": [x["board_days"] for x in seq],
        })
    nm = [m for m in mono if m["board"] == "main"]
    av_ok = sum(1 for m in nm if m["availability_monotone_decreasing"])
    gp_ok = sum(1 for m in nm if m["gap_monotone_increasing"])
    msp = [s for s in spread if s["board"] == "main"]
    sig = sum(1 for s in msp
              if abs((s["availability_spread_session_clustered"] or {}).get(
                  "session_cluster_t") or 0.0) >= 2.0)
    return {"question": PREREGISTRATION["secondary_b"],
            "inference_note": CLUSTER_NOTE, "disjointness": DISJOINT_NOTE,
            "cells": rows,
            "hot_vs_cold_spread": spread, "monotonicity": mono,
            "main_availability_monotone_cells": f"{av_ok}/{len(nm)}",
            "main_gap_monotone_cells": f"{gp_ok}/{len(nm)}",
            "main_availability_spreads_with_session_clustered_abs_t_ge_2":
                f"{sig}/{len(msp)}",
            "verdict": (
                f"THE ORDERING IS THE FINDING; THE MAGNITUDES ARE NOT. On main, entry "
                f"availability falls monotonically in the dial on {av_ok} of {len(nm)} "
                f"(rung x window) cells and the mean open gap rises monotonically with it on "
                f"{gp_ok} of {len(nm)} — the hotter the regime, the more of the next-day "
                f"supply is locked away at the open and the more you pay for what is left. "
                f"The SIZE of that effect is far less certain than the direction: only "
                f"{sig} of {len(msp)} hot-minus-cold availability spreads reach a "
                f"session-clustered |t| of 2, and the permutation_nulls section shows most of "
                f"them do not survive an era-preserving null either. AMENDMENT A2 — the first "
                f"run led with the -16.74 pp holdout magnitude, which is the weakest number "
                f"here, not the strongest."
                if (av_ok == len(nm) and len(nm)) else
                "SEE THE TABLE — availability is not monotone on every main cell; read "
                "monotonicity row by row rather than as a single statement")}


# ── STAGE 5b — PERMUTATION NULLS (amendment A1) ──────────────────────────────

PERM_NULL_NOTE = (
    "AMENDMENT A1. The first run's destruction control was ONE global permutation draw, and "
    "its headline — 'permuting the dial collapses the availability spread from 16.74 pp to "
    "0.40 pp' — was a single sample from a distribution quoted to two decimal places. The "
    "review drew it 20 times and measured a null of -0.12 +- 5.06 pp: 0.40 pp was a coin "
    f"flip, not a collapse. It is replaced here by {N_PERM_DRAWS} draws under TWO nulls, with "
    "the null mean, SD and a two-sided permutation p published for every true statistic.\n"
    "  GLOBAL   — dial values shuffled across all of the board's sessions. Destroys the date "
    "correspondence AND the era structure, so it is the wrong yardstick for a magnitude: any "
    "statistic that is partly era composition will look enormous against it.\n"
    "  WITHIN-YEAR — dial values shuffled only WITHIN each calendar year (an era-preserving "
    "block permutation). Each year keeps its own dial distribution and each stratum keeps its "
    "year composition, so what survives is within-year signal ONLY. This is the honest null "
    "for a magnitude claim, and it is the one the review used to show that most of the -16.74 "
    "pp flagship spread is era composition rather than regime.\n"
    "Both nulls are reported for every statistic. Where they disagree, the WITHIN-YEAR null "
    "governs the magnitude claim and the GLOBAL null governs only the 'is the date "
    "correspondence load-bearing at all' question."
)


def _perm_setup(ev: pd.DataFrame, ser: pd.DataFrame, board: str) -> dict | None:
    """Compact arrays for fast re-labelling of one board under a permuted dial."""
    s = BOARD_SPLITS[board]
    era_dk = int(_daykey([pd.Timestamp(s["era_start"])])[0])
    split_dk = int(_daykey([pd.Timestamp(s["split_date"])])[0])
    sb = ser[ser["board"].astype(str) == board].sort_values("date").reset_index(drop=True)
    sdk = _daykey(sb["date"])
    sval = sb[REGIME_COL].to_numpy(dtype="float64")
    syear = sb["date"].dt.year.to_numpy()
    g = ev[(ev["board"].astype(str) == board) & ev["y_ok"]]
    if not len(g):
        return None
    rdk = _daykey(g["date"])
    keep = rdk >= era_dk
    g, rdk = g[keep], rdk[keep]
    pos = np.searchsorted(sdk, rdk)
    ok = (pos < sdk.size)
    pos = np.where(ok, pos, 0)
    ok &= (sdk[pos] == rdk)
    if not ok.all():
        g, rdk, pos = g[ok], rdk[ok], pos[ok]
    return {
        "sdk": sdk, "sval": sval, "syear": syear,
        "sfit": (sdk >= era_dk) & (sdk < split_dk),
        "ridx": pos, "rfit": rdk < split_dk,
        "rrung": np.searchsorted(np.array(RUNGS), g["rung_label"].to_numpy().astype(str)),
        "runf": g["unfillable_open"].to_numpy(dtype=bool),
        "ry": g["y_limit_up"].to_numpy(dtype=bool),
    }


def _perm_stats(P: dict, sval: np.ndarray) -> dict:
    """The affirmative statistics, recomputed from one dial vector.  Cuts refit per draw."""
    v = sval[P["sfit"]]
    v = v[np.isfinite(v)]
    edges = ([float(x) for x in np.unique(np.quantile(v, [1 / 3, 2 / 3]))]
             if v.size >= 30 else [])
    st = assign_stratum(sval[P["ridx"]], edges)
    out, viol = {}, 0
    for ri, rl in enumerate(RUNGS):
        for sp, m0 in (("fit", P["rfit"]), ("holdout", ~P["rfit"])):
            m = m0 & (P["rrung"] == ri)
            av, pb, ns = [], [], []
            for k in (0, 1, 2):
                mm = m & (st == k)
                n = int(mm.sum())
                ns.append(n)
                av.append(100.0 * float((~P["runf"][mm]).sum()) / n if n else np.nan)
                pb.append(100.0 * float(P["ry"][mm].sum()) / n if n else np.nan)
            key = f"{rl}|{sp}"
            out[key] = {"avail_spread": av[2] - av[0], "p_spread": pb[2] - pb[0],
                        "avail_monotone": bool(np.all(np.isfinite(av))
                                               and av[0] >= av[1] >= av[2]),
                        "min_cell_n": int(min(ns))}
            if not out[key]["avail_monotone"]:
                viol += 1
    out["_violations"] = viol
    return out


def permutation_nulls(ev: pd.DataFrame, ser: pd.DataFrame, board: str = "main") -> dict:
    """Two permutation nulls x N draws for every affirmative statistic on `board`.

    Restricted to main deliberately: it is the only board whose dial is non-degenerate and
    whose families clear the fit-core floor, so it is the only board carrying an affirmative
    claim that a null could refute.  ChiNext and STAR are coverage nulls either way.
    """
    P = _perm_setup(ev, ser, board)
    if P is None:
        return {"status": f"NOT TESTABLE — no usable {board} rows"}
    true = _perm_stats(P, P["sval"])
    rng = np.random.default_rng(PERM_NULL_SEED)
    yrs = P["syear"]
    blocks = [np.where(yrs == y)[0] for y in np.unique(yrs)]
    draws = {"global": [], "within_year": []}
    for _ in range(N_PERM_DRAWS):
        draws["global"].append(_perm_stats(P, P["sval"][rng.permutation(P["sval"].size)]))
        w = P["sval"].copy()
        for bl in blocks:                      # era-preserving block permutation
            w[bl] = w[bl][rng.permutation(bl.size)]
        draws["within_year"].append(_perm_stats(P, w))

    def summarise(key: str, field: str) -> dict:
        t = true[key][field]
        rec = {"true": _r(t, 3)}
        for arm in ("global", "within_year"):
            x = np.array([d[key][field] for d in draws[arm]], dtype="float64")
            x = x[np.isfinite(x)]
            if x.size < 2 or not np.isfinite(t):
                rec[arm] = {"status": "NOT TESTABLE"}
                continue
            ge = int((np.abs(x) >= abs(t)).sum())
            rec[arm] = {
                "null_mean_pp": _r(float(x.mean()), 3),
                "null_sd_pp": _r(float(x.std(ddof=1)), 3),
                "draws": int(x.size),
                "draws_at_or_beyond_abs_true": ge,
                "two_sided_p": _r((1.0 + ge) / (x.size + 1.0), 4),
                "z_vs_null": _r((t - float(x.mean())) / float(x.std(ddof=1)), 2)
                if float(x.std(ddof=1)) > 0 else None,
            }
        return rec

    stats = {}
    for rl in RUNGS:
        for sp in ("fit", "holdout"):
            k = f"{rl}|{sp}"
            stats[k] = {"availability_spread_pp": summarise(k, "avail_spread"),
                        "p_next_board_spread_pp": summarise(k, "p_spread"),
                        "min_cell_board_days": true[k]["min_cell_n"]}
    # THE ORDERING statistic — the one the review found robust.  Under each null, how often
    # does a shuffled dial reproduce the true monotone-availability ordering across all 6
    # (rung x window) cells?
    order = {"true_monotone_cells": 6 - true["_violations"], "cells": 6,
             "true_violations": true["_violations"]}
    for arm in ("global", "within_year"):
        v = np.array([d["_violations"] for d in draws[arm]])
        order[arm] = {
            "draws": int(v.size),
            "draws_with_violations_at_or_below_true": int((v <= true["_violations"]).sum()),
            "one_sided_p": _r((1.0 + int((v <= true["_violations"]).sum())) / (v.size + 1.0), 4),
            "null_mean_violations": _r(float(v.mean()), 2),
            "null_sd_violations": _r(float(v.std(ddof=1)), 2) if v.size > 1 else None,
        }
    return {"note": PERM_NULL_NOTE, "board": board, "draws_per_arm": N_PERM_DRAWS,
            "seed": PERM_NULL_SEED, "statistics": stats, "ordering": order}


# ── STAGE 6 — the corruption experiment ──────────────────────────────────────

def corruption_summary(events: pd.DataFrame, trades: pd.DataFrame,
                       dials: dict[str, pd.DataFrame]) -> dict:
    """Re-run every dial-conditioned effect under each SHIFTED alignment.

    The pre-registered lag-1 arm is reported WITH its measured power: shifting a 5-session
    backward mean by one session leaves four of five inputs in place, so attenuation rather
    than death is the honest expectation and a surviving effect there is not evidence of a
    broken index.  Permutation is no longer an arm here — see permutation_nulls().
    """
    out = {"arms": CORRUPTION_ARMS, "permutation_arm_superseded": PERM_ARM_SUPERSEDED,
           "results": {}}
    for arm in ("true", "corrupt_lag1", "corrupt_lead1"):
        el, _ = label_frame(events, dials[arm])
        tl, _ = label_frame(trades, dials[arm])
        floors = family_floor(el)
        _rows, verdict, _t = primary_book(tl, floors)
        hl = [c for c in verdict["clears"]
              if (c["board"], c["rung"], c["stratum"], c["rule"])
              == (HEADLINE_CELL["board"], HEADLINE_CELL["rung"], HEADLINE_CELL["stratum"],
                  HEADLINE_CELL["rule"])]
        fb = fillable_share_by_dial(el)
        sp = [s for s in fb["hot_vs_cold_spread"]
              if s["board"] == HEADLINE_CELL["board"] and s["rung"] == HEADLINE_CELL["rung"]]
        bl = broken_vs_sealed(tl, floors)
        out["results"][arm] = {
            "max_date_clustered_t_all_cells":
                verdict["t_census_all_cells"]["max_date_clustered_t_either_window"],
            "max_date_clustered_t_non_thin_families":
                verdict["t_census_non_thin_families_only"][
                    "max_date_clustered_t_either_window"],
            "non_thin_cells": verdict["t_census_non_thin_families_only"]["cells"],
            "cells_clearing_the_FULL_decision_bar":
                verdict["cells_clearing_the_FULL_decision_bar"],
            "headline_cell_clears": bool(hl),
            "headline_family_entry_availability_hot_minus_cold_pp": sp,
            "availability_spread_abs_pp_max": _r(max(
                [abs(s["hot_minus_cold_pp"]) for s in sp] or [0.0]), 3),
            "max_abs_broken_lead_t_above_paired_date_floor":
                bl["max_abs_lead_date_clustered_t_above_the_paired_date_floor"],
        }
    tr = out["results"]["true"]
    lead = out["results"]["corrupt_lead1"]
    # AMENDMENT A3 — the first run's lookahead predicate keyed ONLY on
    # max_date_clustered_t_non_thin_families: a maximum over 21 uniformly NEGATIVE cells, which
    # a lookahead cannot push above the bar, so the check could not fail and its PASS carried
    # no information (the S7 class W3-A named — verify that a check can SEE failure).  The
    # predicate now keys on the two series that actually MOVE under a shifted dial.
    movable = [
        ("availability_spread_abs_pp_max", tr["availability_spread_abs_pp_max"],
         lead["availability_spread_abs_pp_max"]),
        ("max_abs_broken_lead_t_above_paired_date_floor",
         tr["max_abs_broken_lead_t_above_paired_date_floor"],
         lead["max_abs_broken_lead_t_above_paired_date_floor"]),
    ]
    moved = [{"series": k, "true": t, "lookahead": l,
              "strengthens_under_lookahead": bool((l or 0) > (t or 0))}
             for k, t, l in movable]
    n_moved = sum(1 for m in moved if m["strengthens_under_lookahead"])
    out["reading"] = {
        "lookahead_is_a_POSITIVE_control_not_a_null_control": (
            "i5 at T+1 is computed FROM the T->T+1 continuation outcomes — the dial dated T+1 "
            "counts how many of T's boarders boarded again at T+1, which IS the outcome this "
            "book trades. A T+1-dated dial therefore MUST strengthen any statistic that can "
            "move, and the honest reading of this arm is 'the positive control fired', not "
            "'nothing happened'. An arm that changed nothing would mean the join is not "
            "reading dates at all."),
        "movable_series": moved,
        "lookahead_direction": (
            f"PASS — the positive control fires on {n_moved} of {len(moved)} movable series "
            "(availability spread and broken-lead max t both rise under a T+1-dated dial, "
            "which is the expected benign signature described above), and the true alignment "
            "is measurably distinguishable from it."
            if n_moved == len(moved) else
            f"SEE NUMBERS — the lookahead arm strengthens only {n_moved} of {len(moved)} "
            "movable series. A T+1-dated dial that does NOT strengthen these is evidence the "
            "join is not date-sensitive, which would invalidate every dial-conditioned number "
            "in this file."),
        "why_the_t_census_is_NOT_in_this_predicate": (
            "max_date_clustered_t_non_thin_families is a maximum over 21 cells that are "
            "uniformly negative under every arm. It cannot rise above the decision bar no "
            "matter what the dial does, so keying a lookahead verdict on it produces a PASS "
            "that carries no information. It is still printed, as a descriptive series."),
        "destruction_control_moved": (
            "The destruction control is no longer an arm here: one permutation draw quoted to "
            "two decimals was the first run's MAJOR defect. See `permutation_nulls` for the "
            f"{N_PERM_DRAWS}-draw distributions under a global and an era-preserving scheme, "
            "with a permutation p for every affirmative statistic."),
        "power_caveat": (
            "The lag-1 arm's power is bounded by the dial's own lag-1 autocorrelation, printed "
            "in dial_series.dial_lag1_autocorrelation (~0.92 on every board). Where that is "
            "near 1 the lag-1 arm cannot distinguish a correct index from a one-session-late "
            "one. It is reported as a measured limitation, not as a clean bill of health."),
        "why_all_cells_maxima_are_not_comparable_across_arms": (
            "max_date_clustered_t_all_cells moves wildly between arms because re-cutting the "
            "dial re-populates the THIN families, where a two-session cell can print any t at "
            "all. The comparable series are the non-thin maximum and the availability spread."),
    }
    return out


def adjudicate_affirmative(perm: dict, fillable: dict) -> dict:
    """AMENDMENT A2 — which affirmative claims survive BOTH the era-preserving permutation
    null and session-clustered inference, and which are direction-only.

    The primary result of this lane is a NULL and is unaffected by any of this. What this
    block governs is the small set of AFFIRMATIVE statements the receipt also makes, which
    the first run stated at full strength on IID bands and one permutation draw.
    """
    ALPHA = 0.05
    sp = {(s["rung"], s["split"]): s for s in fillable["hot_vs_cold_spread"]
          if s["board"] == "main"}
    rows = []
    for rl in RUNGS:
        for w in ("fit", "holdout"):
            k = f"{rl}|{w}"
            st = perm.get("statistics", {}).get(k, {})
            for field, label in (("availability_spread_pp", "entry availability hot-cold"),
                                 ("p_next_board_spread_pp", "P(next board) hot-cold")):
                f = st.get(field, {})
                wy = f.get("within_year", {})
                gl = f.get("global", {})
                cl = None
                if (rl, w) in sp:
                    ck = ("availability_spread_session_clustered"
                          if field == "availability_spread_pp"
                          else "p_next_board_spread_session_clustered")
                    cl = (sp[(rl, w)].get(ck) or {}).get("session_cluster_t")
                p_wy = wy.get("two_sided_p")
                ok_perm = p_wy is not None and p_wy <= ALPHA
                ok_clu = cl is None or abs(cl) >= BOOK_T_BAR
                rows.append({
                    "statistic": label, "rung": rl, "window": w, "true": f.get("true"),
                    "global_null_p": gl.get("two_sided_p"),
                    "within_year_null_p": p_wy,
                    "session_clustered_t": cl,
                    "SURVIVES_era_preserving_null": bool(ok_perm),
                    "SURVIVES_session_clustering": bool(ok_clu),
                    "MAGNITUDE_SUPPORTED": bool(ok_perm and ok_clu),
                })
    surv = [r for r in rows if r["MAGNITUDE_SUPPORTED"]]
    order = perm.get("ordering", {})
    return {
        "why_this_block_exists": (
            "The first run stated its affirmative magnitudes against IID Wilson bands and a "
            "SINGLE permutation draw. Both instruments were too weak for the claims resting "
            "on them. This block re-adjudicates every affirmative magnitude against the "
            "era-preserving permutation null AND session-clustered inference, and separates "
            "what survives from what is direction-only."),
        "bar": (f"a magnitude is SUPPORTED only if its two-sided permutation p under the "
                f"ERA-PRESERVING (within-year) null is <= {ALPHA} AND its session-clustered "
                f"|t| is >= {BOOK_T_BAR}. The global-shuffle p is printed but does NOT confer "
                "support: it destroys era structure, so it flatters any statistic that is "
                "partly era composition."),
        "rows": rows,
        "magnitudes_supported": len(surv),
        "magnitudes_tested": len(rows),
        "the_ordering_result": {
            "statistic": ("availability falls monotonically across cold->mid->hot on all 6 "
                          "main (rung x window) cells"),
            "true_violations": order.get("true_violations"),
            "global_null": order.get("global"),
            "within_year_null": order.get("within_year"),
            "verdict": (
                "SUPPORTED UNDER BOTH NULLS — this is the robust affirmative finding of the "
                "lane. A shuffled dial reproduces the full monotone ordering essentially "
                "never (null mean "
                f"{(order.get('within_year') or {}).get('null_mean_violations')} violations "
                "under the era-preserving scheme), while the true dial produces zero."
                if (order.get("true_violations") == 0
                    and ((order.get("within_year") or {}).get("one_sided_p") or 1.0) <= ALPHA
                    and ((order.get("global") or {}).get("one_sided_p") or 1.0) <= ALPHA)
                else "SEE THE NUMBERS — the ordering does not clear both nulls"),
        },
        "headline_reading": (
            "DIRECTION SURVIVES, MAGNITUDE LARGELY DOES NOT. The monotone ordering clears both "
            "nulls and the P(next board) spread clears the era-preserving null in both "
            "windows. The availability MAGNITUDES mostly do not: in particular the first "
            "run's flagship -16.74 pp holdout spread has an era-preserving permutation p of "
            "about 0.07 and a session-clustered t of about -1.7, so most of it is era "
            "composition and thin-holdout noise rather than regime. The receipt now leads "
            "with the ordering and bands every magnitude."),
    }


# ── ORE LEDGER ───────────────────────────────────────────────────────────────

ORE_LEDGER = {
    "law": ("A null closes ONLY the construction tested. 'Not found yet' is not 'does not "
            "exist'. Everything below was NOT tested by this lane and remains open ore."),
    "closed_by_this_lane_if_the_result_is_null": [
        "the fillable next-open rider under E1/E2/E3, conditioned on the i5 dial LEVEL in "
        "fit-window terciles, on the {1, 2, 3+} rungs, per board, in the two-window "
        "pre-registered form specified above — and nothing else",
        "the broken-vs-sealed T+1-open lead as a dial-tercile-conditioned, prior-rung-matched, "
        "session-paired quantity, on the same three exit rules",
    ],
    "untested_variants": [
        {"id": "OM1", "construction": "the dial as a CONTINUOUS covariate rather than a "
         "tercile cut", "why_it_matters": "terciles throw away the dial's own shape; W2-A's "
         "1.670x N=1 multiplier was measured on strata, and a continuous form could be "
         "monotone where the cut is not"},
        {"id": "OM2", "construction": "the dial's SLOPE / derivative (is the regime warming or "
         "cooling), not its level", "why_it_matters": "W2-A established the dial is a LEVEL "
         "instrument for ranking purposes; nothing has tested whether the CHANGE in level "
         "times entries, which is a different physical claim (退潮 is a transition, not a "
         "state)"},
        {"id": "OM3", "construction": "CROSS-BOARD dial spillover — main's dial conditioning "
         "ChiNext entries and vice versa", "why_it_matters": "the ecology is one crowd across "
         "three boards; a board's own dial may be the wrong instrument for its own names"},
        {"id": "OM4", "construction": "dial x ENTRY-FAMILY interactions beyond the next-open "
         "rider: 回封 re-entries, 龙回头 pullbacks, half-way (半路) entries",
         "why_it_matters": "W2-B priced those families UNCONDITIONALLY; the dial has never met "
         "them, and they are the families whose fills are guaranteed by construction"},
        {"id": "OM5", "construction": "rungs N>=2 as separate strata rather than a 3+ cohort, "
         "and the N>=4 ladder where the published rates are highest",
         "why_it_matters": "the fillability tax is worst exactly there (main N>=3: 75.0% "
         "unbuyable), so the cells are thin, but thin is not tested"},
        {"id": "OM6", "construction": "the other five L2 ecology instruments (i1 first-board "
         "count, i3 高标 height, i4 炸板 rate, i6 near-limit count) as conditioners, alone or "
         "in confluence with i5", "why_it_matters": "L2 measured i5 as the only ERA-NEUTRAL "
         "dial, which is a different property from being the only USEFUL one; a factor that is "
         "null standalone is retained as a confluence input"},
        {"id": "OM7", "construction": "within-series RANKS of the dial rather than its level "
         "(L2's own prescription for the breadth family)", "why_it_matters": "if the level "
         "drifts across eras the tercile edges drift with it; a rolling within-series rank is "
         "the era-neutral form and was not tested here"},
        {"id": "OM8", "construction": "horizons beyond E1/E2/E3 — H in {5, 10} holds, and the "
         "peak/window targets W3-A measured", "why_it_matters": "W3-A's foresight premium "
         "(+2.03% at H=10 holdout, t 3.55) says the window contains more than daily-scheduled "
         "exits collect; none of it has been dial-conditioned"},
        {"id": "OM9", "construction": "intraday entry moments — first-seal time, the 9:25 "
         "auction snapshot, intraday pullback entries", "why_it_matters": "L1's g4 cell has "
         "mean -1.009% against median +0.372%: a left-tail shape a daily bar cannot cut. The "
         "operator's minute-bar purchase unlocks this and it is the program's sized target"},
        {"id": "OM10", "construction": "the dial computed on the VENDOR pool universe rather "
         "than the curated slice", "why_it_matters": "vendor-pool undercount is median 2.748x "
         "and UNSTABLE (IQR/median 0.53), so the dial's LEVEL — the thing the terciles cut on "
         "— is a curated-universe quantity and its edges may not survive expansion"},
        {"id": "OM11", "construction": "the full-universe (F3) re-run of everything here",
         "why_it_matters": "every number in this file is a 1,842-name, survivors-only, "
         "1-ST-name statistic. F3 is the standing threat to the ladder itself, not just to "
         "this lane"},
        {"id": "OM12", "construction": "DOW / fermentation x dial crosses",
         "why_it_matters": "L1 measured weekend fermentation as real in probability (+4.48 pp) "
         "and FULLY MEDIATED by the gap; whether the mediation itself is regime-dependent is "
         "untested"},
        {"id": "OM13", "construction": "size / float / turnover normalisation of the cohort",
         "why_it_matters": "no share counts exist anywhere in the CN stores yet (v0's f2 "
         "NULL); the 盘前股本 purchase repairs it and every cell here is size-blind"},
        {"id": "OM14", "construction": "a dial-conditioned SIZING rule rather than a "
         "dial-conditioned ENTRY filter", "why_it_matters": "the charter's S4 shape is a "
         "regime gate over the whole book — 'how much' is a different question from 'whether', "
         "and a level instrument is a natural sizing input even where it is a null filter"},
        {"id": "OM15", "construction": "the ST cohort and its 5% band",
         "why_it_matters": "excluded wholesale on every date because data/china_st carries one "
         "asof and no membership history; the ST history purchase repairs it"},
    ],
    "known_defects_inherited_and_not_repaired_here": [
        "the T->T+1 PAIRING rule remains v0's 10-calendar-day rule, so a board day whose next "
        "session sits across a long closure is not an EVENT at all. Only the forward EXIT "
        "chain was made closure-tolerant. Repairing the pairing rule would move every outcome "
        "denominator v0's parity gate verifies as exact, so it is disclosed, counted and left.",
        "roll-cap exhaustion still prices an exit at a CLOSE rather than an open. The cell "
        "block prints the roll rate, the mean extra loss and a sensitivity with those trades "
        "dropped, which bounds it from both sides.",
        "slippage is not modelled; fills are assumed at the printed open, which is optimistic "
        "for exactly these names.",
    ],
}

WHAT_THIS_DOES_NOT_ESTABLISH = [
    "That the dial is useless. It establishes what the dial does or does not do to ONE entry "
    "family at ONE resolution. W2-A's 1.670x N=1 continuation multiplier is a fact about "
    "PROBABILITY and is untouched by anything here; this lane asks only whether that "
    "probability structure survives being paid for at the T+1 auction.",
    "That any cell here is tradeable. Nothing ranks, sizes, gates or admits. No forward ledger "
    "row is emitted by this file.",
    "Anything about the full ~5,400-name universe, ST names, or delisted names.",
    "Anything about intraday entries, which is where L1's median-vs-mean left-tail shape says "
    "the remaining measurable structure lives.",
]


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    t0 = time.time()
    print("[1/8] building panel (L1 events + L1 parity book + this lane's book) ...",
          flush=True)
    (events, trades, l1, pairs, ser, cal, dial_meta, meta, usable_dates,
     build_sec) = build()

    print("[2/8] parity gates ...", flush=True)
    gates = {
        "v0_ladder": rider.v0_ladder_parity(events, meta),
        "l1_panel_and_book": l1_parity(meta, l1),
        "closure_tolerant_chain_footprint": closure_parity(l1, trades),
        "splits": split_gate(usable_dates),
    }

    print("[3/8] dial join + lookahead audit ...", flush=True)
    dials = dial_frames(ser)
    ev_true = events.copy()
    ev_true["cohort"] = "sealed"
    ev_true["rung"] = np.minimum(ev_true["N"].to_numpy(), N_COHORT_CAP).astype(np.int16)
    ev_true["prior_rung"] = np.maximum(ev_true["rung"].to_numpy() - 1, 0).astype(np.int16)
    ev_l, strata_info = label_frame(ev_true, dials["true"])
    tr_l, _ = label_frame(trades, dials["true"])
    joined = {(str(b), int(k)): float(v) for b, k, v in zip(
        ev_l["board"].astype(str).to_numpy(), _daykey(ev_l["date"]),
        ev_l["dial"].to_numpy(dtype="float64"))}
    lookahead = audit_lookahead(ser, pairs, joined)

    print("[4/8] primary cells + t-census + era tables ...", flush=True)
    floors = family_floor(ev_l)
    rows, verdict, trunc = primary_book(tr_l, floors)
    eras = era_tables(tr_l, floors)
    rates = rate_table(ev_l)
    orderings = dial_orderings(rates, rows, floors)
    hl_key = (HEADLINE_CELL["board"], HEADLINE_CELL["rung"], HEADLINE_CELL["stratum"],
              HEADLINE_CELL["rule"])
    headline = {sp: next((r for r in rows if (r["board"], r["rung"], r["stratum"], r["rule"],
                                              r["split"]) == hl_key + (sp,)), None)
                for sp in ("fit", "holdout")}

    print("[5/8] secondary (a) broken-vs-sealed by dial state ...", flush=True)
    broken = broken_vs_sealed(tr_l, floors)

    print("[6/8] secondary (b) fillable share x dial ...", flush=True)
    fillable = fillable_share_by_dial(ev_l)

    print(f"[7/8] permutation nulls ({N_PERM_DRAWS} draws x 2 schemes) ...", flush=True)
    perm_nulls = permutation_nulls(ev_l, ser, board="main")

    print("[8/8] corruption experiment (shifted-dial arms) ...", flush=True)
    corruption = corruption_summary(ev_true, trades, dials)

    ev_tape = pd.read_parquet(LIMIT_EVENTS)
    zt = pd.read_parquet(ZT_POOL)
    raw_names = {p.stem for p in (DATA / "china_stocks_raw").glob("*.parquet")}
    zt_names = set(zt["ticker"].astype(str))
    coverage = {
        "price_basis": ("data/china_stocks_raw — v0's store. NOT the adjusted twin, which "
                        "would fabricate limit misses. L1 measured that this store is itself "
                        "BACK-ADJUSTED rather than nominal; adjustment preserves returns, so "
                        "every gap, open-to-close and trade return here is unaffected."),
        "store_vintage": dict(VINTAGE, checkout_head_sha=head_sha(),
                              raw_store_files=len(raw_names),
                              vintage_matches_stamp=bool(
                                  len(raw_names) == VINTAGE["curated_universe_names"]
                                  and len(ev_tape) == VINTAGE["healed_limit_events_rows"])),
        "healed_event_tape": {
            "source": "data/china_microstructure/limit_events.parquet (L0 heal, PR #5059)",
            "rows": int(len(ev_tape)),
            "by_event": {str(k): int(v) for k, v in
                         sorted(ev_tape["event"].value_counts().to_dict().items())},
            "cross_check_this_lane_broken_days": meta["broken_board_days_touch_and_fail"],
            "cross_check_note": (
                "The tape's failed_up_seal count and this lane's touch-and-fail count are NOT "
                "expected to be equal and are printed side by side rather than reconciled: "
                "the tape is a strict-basis artifact whose lianban_count is hardcoded 0 on "
                "failed_up_seal rows (W2-B's silent-null trap), and strict/tolerant event "
                "overlap is only 42.7% of their union. This lane derives its broken cohort "
                "from its own tolerant panel so both arms of the comparison share one basis."),
        },
        "universe_gap": {
            "raw_store_names": len(raw_names),
            "zt_pool_names": len(zt_names),
            "zt_pool_names_present_in_raw": len(zt_names & raw_names),
            "zt_pool_names_present_pct": _r(
                100.0 * len(zt_names & raw_names) / max(1, len(zt_names)), 1),
            "zt_pool_dates": int(zt["date"].nunique()),
        },
        "exclusions": meta,
    }

    out = {
        "instrument": MODEL_VERSION,
        "program": ("CN LIMIT-MOVE ALPHA — Wave 3 lane W3-B, the L1 continuation-side regime "
                    "merge. Masterplan research/CN_LIMIT_ALPHA_MASTERPLAN_BY_FABLE.md §6.2 "
                    "named this the program's largest measured remaining effect."),
        "merges": {
            "L1_rider": "research/cn_prophet_audit/continuation_rider_v1.py (PR #5061)",
            "L2_dial": "research/cn_prophet_audit/board_ecology_series_v1.parquet (PR #5078)",
            "W2A_splits": "research/cn_prophet_audit/regime_calibration_v2.py (PR #5093)",
            "L0_heals": "data/china_microstructure + data/china_zt_pool (PR #5059)",
        },
        "tier": ("DISPLAY / AUDIT. Measurement only. Nothing promotes, ranks, sizes, gates or "
                 "admits. No LLM is involved. The gauntlet applies at authority promotion, "
                 "which this artifact does not seek."),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_sec": None,          # filled below; a RUN-STAMP field, see determinism note
        "determinism": (
            "TZ=UTC python3 research/cn_prophet_audit/continuation_regime_merge_v1.py run "
            "twice produces byte-identical JSON except THREE stamp fields: `generated_utc`, "
            "`runtime_sec`, and `coverage_receipt.store_vintage.checkout_head_sha` "
            "(amendment A5 — the first run's note said 'two', omitting the HEAD sha; it is "
            "stable across two runs in one checkout but is a stamp, not a finding, and moves "
            "with the checkout). All randomness is seeded: the permutation nulls at "
            f"{PERM_NULL_SEED} and the session cluster bootstrap at {BOOT_SEED}."),
        "amendments_after_first_run": AMENDMENTS_AFTER_FIRST_RUN,
        "preregistration": PREREGISTRATION,
        "coverage_receipt": coverage,
        "dial_series": dial_meta,
        "gates": gates,
        "lookahead_audit": lookahead,
        "regime_strata": strata_info,
        "cell_family_floor": {
            "floor": MIN_FIT_CORE_POSITIVES,
            "definition": ("fit-CORE realised next-bar limit-up closes in the (board, rung, "
                           "dial-tercile) family. W2-A's floor and W2-A's fit_core slice, "
                           "inherited unchanged so the number means the same thing."),
            "discipline": ("NOT LOWERED AFTER SEEING DATA. W2-A held this exact line against "
                           "STAR at 137 positives and skipped the board rather than move it."),
            "families": [{"board": k[0], "rung": k[1], "stratum": k[2], **v}
                         for k, v in sorted(floors.items())],
        },
        "primary": {
            "question": PREREGISTRATION["primary_question"],
            "decision_bar": DECISION_BAR,
            "headline_cell": {"declared_in_advance": HEADLINE_CELL, "result": headline},
            "rate_table": rates,
            "dial_orderings_probability_vs_expectancy": orderings,
            "book_cells": rows,
            "truncated_windows_excluded_from_the_priced_book": trunc,
            "verdict": verdict,
        },
        "era_tables": eras,
        "secondary_a_broken_board_lead_by_dial_state": broken,
        "secondary_b_fillable_share_by_dial_state": fillable,
        "permutation_nulls": perm_nulls,
        "affirmative_claims_adjudicated": adjudicate_affirmative(perm_nulls, fillable),
        "corruption_experiment": corruption,
        "what_this_does_NOT_establish": WHAT_THIS_DOES_NOT_ESTABLISH,
        "ore_ledger": ORE_LEDGER,
    }
    out["runtime_sec"] = round(time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(jsonable(out), indent=1, ensure_ascii=False,
                                   sort_keys=False) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT_JSON.relative_to(REPO)}  ({time.time() - t0:.1f}s, "
          f"build {build_sec:.1f}s)", flush=True)
    print(f"  v0 ladder parity      : {gates['v0_ladder']['verdict'][:60]}", flush=True)
    print(f"  L1 panel/book parity  : {gates['l1_panel_and_book']['verdict'][:60]}", flush=True)
    print(f"  lookahead             : {lookahead['verdict'][:60]}", flush=True)
    print(f"  cells clearing the bar: {verdict['cells_clearing_the_FULL_decision_bar']} "
          f"of {verdict['cells_total']}  (non-thin max dc-t "
          f"{verdict['t_census_non_thin_families_only']['max_date_clustered_t_either_window']}"
          f" over {verdict['t_census_non_thin_families_only']['cells']} cells)", flush=True)
    adj = out["affirmative_claims_adjudicated"]
    print(f"  affirmative magnitudes: {adj['magnitudes_supported']} of "
          f"{adj['magnitudes_tested']} survive the era-preserving null + clustering",
          flush=True)
    print(f"  ordering result       : "
          f"{adj['the_ordering_result']['verdict'][:58]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
