#!/usr/bin/env python3
"""CN LIMIT-MOVE ALPHA — W-P0: the washout/confluence-conditional FIRST-BOARD onset study.

    TZ=UTC python3 research/cn_prophet_audit/washout_onset_w1.py

DISPLAY / AUDIT TIER.  Nothing here ranks, sizes, gates or admits anything.  This is a
state-conditioning measurement: does a name sitting in a washout / momentum-confluence /
accumulation state print its FIRST limit-up board (ladder 0 -> 1) over the next H sessions
more often than the unconditional cold-universe base rate, and can the v0 feature battery
RANK the eventual boarders inside such a state?

===============================================================================
PRE-REGISTRATION — every choice below was fixed BEFORE the first number was read.
Anything changed after a number was seen is recorded in AMENDMENTS at the bottom of this
block, with its reason.  There are no silent edits.
===============================================================================

WHY THIS STUDY EXISTS (masterplan sec.10.1, operator 2026-08-10).  The program's shipped
onset model is LADDER-CONDITIONED (N>=1) and every kill so far is an ENTRY-family kill on
post-ignition cohorts.  The operator's actual thesis — pre-first-board onset out of
washout/basing states, with confluence and accumulation footprints as the conditioners —
had NEVER been run and has NEVER failed.  This instrument runs it.

MECHANISM HYPOTHESIS ON RECORD (operator, distilled): (a) sector-wide washout reversion;
(b) deliberate hammer-down into negative sentiment -> insider/institutional accumulation
below intrinsic value -> news release -> rapid repricing.  The accumulation phase should
leave footprints in volume / momentum / chip structure BEFORE the board.  The mechanism
story is CONJUNCTIVE, so the conjunction cells (S6) are the thesis, not the marginals.

HONEST PRIORS, STATED BEFORE THE RUN:
  * the unconditional first-board rate is LOW (v0 measured ~1.27%/session for boards of
    every kind; a ladder-0 cold-start board is rarer still), so absolute rates are small
    everywhere and LIFT is the readable quantity;
  * washout states are LONG — a name can sit 40% under its 250-session high for years — so
    the conditioned populations are large and any MARGINAL lift is expected to be MODEST.
    The conjunctions are where the mechanism predicts concentration;
  * a null on any single state closes THAT CONSTRUCTION ONLY (ORE LAW, masterplan sec.2).
    "Not found yet" is not "does not exist"; the ore ledger names what was NOT tested;
  * this is state-conditioning research.  NO ENTRY BOOK IS IMPLIED and no expectancy is
    quoted, so fillability twins are not required here.  Should any implied-entry return
    ever be quoted off this instrument it must first be re-priced open-anchored per W3-C.

-------------------------------------------------------------------------------
1. UNIVERSE AND BASIS
-------------------------------------------------------------------------------
Store: data/china_stocks_raw/*.parquet — the CURATED 1,842-name slice.  ST/*ST names are
excluded wholesale (v0's choice, not relitigated).  Board from ticker prefix.

BASIS NOTE (L1's measured correction to v0's header): this store is BACK-ADJUSTED, not
nominal.  Adjustment preserves RETURNS, so every indicator, drawdown, moving average,
volume z-score and window return below is unaffected.  Only the round-to-tick limit PRICE
is affected, and v0's adjudicated 0.2% tolerance is the cushion for exactly that.  This is
the masterplan's trap #1 and the reason a back-adjusted basis is FINE for this study.

LIVE-BAR LAW (v0's, unchanged): a bar is LIVE only when it has a finite positive previous
close, sits outside the IPO exclusion window for its board era, is not an ex-dividend jump
(|open - prevclose| / prevclose > 1.5x the band), and has VOLUME > 0.  china_stocks_raw
encodes 停牌 suspensions as ZERO-VOLUME STALE-PRICE PLACEHOLDER ROWS, not missing rows
(W3-C's review MAJOR found 133,781 in-window).  Every conditioning bar, every outcome bar
and every step of every forward chain here is live-gated.

SURVIVORSHIP + COVERAGE CAVEAT (reconciliation sec.4, stamped on EVERY table):
  the 1,842-name store is 35.37% of active SH/SZ names, 0 of 329 BSE names, median cached
  cap 187.7 yi against 37.85 yi for the omitted names, and only 36.09% of canonicalised
  zt-pool names.  EVERY NUMBER HERE IS A LARGE-CAP-SLICE STATISTIC ON SURVIVORS.
  Extrapolation to small caps is FORBIDDEN language in this receipt; the small-cap
  question is a sampling-gap prior, never proven alpha.

-------------------------------------------------------------------------------
2. BOARDS — NEVER POOLED (sec.0 gate 2)
-------------------------------------------------------------------------------
  main       SH 60x / SZ 000x 001x 002x 003x        +-10%
  chinext10  SZ 300x 301x  BEFORE   2020-08-24      +-10%
  chinext20  SZ 300x 301x  ON/AFTER 2020-08-24      +-20%
  star       SH 688x                                +-20%
The ChiNext 2020-08-24 band transition splits ChiNext into two POPULATIONS that are never
pooled with each other or with anything else.

-------------------------------------------------------------------------------
3. ERAS (house ERA_BOUNDS; 2015 is its own stress era, never averaged into a neighbour)
-------------------------------------------------------------------------------
  e1_2011_14 . e2_2015_mania . e3_2016_18_crackdown . e4_2019_21_revival
  e5_2022_23_grind . e6_2024_26_current

-------------------------------------------------------------------------------
4. SPLIT (reconciliation ledger sec.7 — the frozen split, adopted verbatim)
-------------------------------------------------------------------------------
  train        2011-01-01 -> 2019-12-31
  calibration  2020-01-01 -> 2023-12-31
  locked test  2024-01-02 -> 2026-06-12
  audit        2026-06-15 -> 2026-08-07   (vendor-rich window; reported separately)
Headline reporting collapses train+calibration into FIT and reports the locked test as
HOLDOUT, with the per-split tables printed beside them.

EMBARGO — DISCLOSED EXTENSION OF THE MANDATED PURGE.  The ledger mandates 10-session
purges at split boundaries.  A 10-session purge CANNOT cover a 20-session outcome window:
a conditioning bar 15 sessions before a boundary has an H=20 outcome that lands inside the
next split.  The mandated 10 is therefore kept as the FLOOR and widened to
EMBARGO_SESSIONS = max(10, max(H)) = 20 sessions dropped from the END of each split,
applied uniformly across H so the H=5/10/20 tables share one split column and stay
comparable.  This is an extension, disclosed, not a substitution; the mandated-10 arm is
printed as a sensitivity in `embargo_sensitivity`.

-------------------------------------------------------------------------------
5. THE CONDITIONING UNIVERSE — "COLD" BARS ONLY
-------------------------------------------------------------------------------
A conditioning bar T is eligible when it is LIVE and the name has had NO tolerant limit-up
close in the last K = 20 bars INCLUDING T.  This is what makes the outcome a genuine
0 -> 1 IGNITION rather than a re-board: a state measured one bar after a board would
predict continuation, which is a DIFFERENT physical object (W3-A) and is already priced by
the program's ladder work.

LEMMA (asserted, not assumed — verify check `cold_universe_implies_ladder_zero`): for
K = 20 and H <= 20, the FIRST tolerant board inside T+1..T+H on a bar cold at T is
necessarily a ladder-0 board.  Its own prior-20 window T+j-20..T+j-1 is the union of a
sub-window of T-19..T (clean by coldness) and T+1..T+j-1 (clean because the board is the
FIRST in the window).  The check recomputes the ladder count at every realised first-board
bar and FAILS if any is non-zero.

-------------------------------------------------------------------------------
6. OUTCOME CLASSES — PER BOARD, NEVER POOLED (W3-A target-class law)
-------------------------------------------------------------------------------
(a) FIRST BOARD within H: any tolerant limit-up close in T+1..T+H.
    Tolerant limit-up close = close >= round(prev_close * (1 + w), 2) * (1 - 0.002) —
    v0's adjudicated PRIMARY definition (median marginal event sits at exactly 100.000% of
    the band; 99.79% lianban agreement with the independent vendor pool vs 91.1% strict).

(b) The BLAST-OFF WINDOW class beside it (W3-A's rerating windows), per board:
      cum_H  = close[T+H] / close[T] - 1              >= {0.8w, 1.5w}
      peak_H = max(high[T+1..T+H]) / close[T] - 1     >= {0.8w, 1.5w}
    w is the board's OWN band, so the thresholds are 8%/15% on a +-10% board and 16%/30%
    on a +-20% board: band-relative by construction, which is what makes the classes
    comparable across boards WITHOUT pooling them.
    peak_* is a FORESIGHT UPPER BOUND (W3-A: half to 60% of threshold-touching windows
    give the touch back before any scheduled exit).  It is labelled as such everywhere and
    is never described as attainable.

H in {5, 10, 20} sessions.

CLOSURE-TOLERANT FORWARD CHAIN — W3-A amendment A1's lesson, paid once and NOT re-paid.
v0's 10-CALENDAR-DAY T->T+1 pair rule, reused as a forward-chain STEP rule, truncates every
open window market-wide at any exchange closure longer than 10 days (CNY, National Day;
W3-A measured 7 such closures, 44,022 truncated trades, 6.55% of rows at H=10, and that
truncated tail was the whole of that receipt's first-draft flagship illusion).  This
instrument PRE-REGISTERS the widened step rule MAX_STEP_GAP_DAYS = 21 calendar days, which
tolerates the longest observed CN closure, and prints the recovered-row receipt
(`closure_receipt`) showing exactly what the 10-day rule would have discarded.  A window is
scored only when the whole H-step chain is live and inside the gap rule.

-------------------------------------------------------------------------------
7. CONDITIONING STATES — all measured AT T, all observable at T's close
-------------------------------------------------------------------------------
S1  MOMENTUM CONFLUENCE on 2-day and 3-day bars, SEPARATELY.

    THE DEFINITIONS ARE NOT THIS STUDY'S TO INVENT.  They are transcribed from the Terminal
    product repo (/Users/chriswong/Documents/Cluade/charting-app), whose production path is
    `signal_layer/confluence.py` (the "GOLDEN ORACLE") + `signal_layer/confluence_v2.py`
    ("GC v2").  Testing THEIR construction is the point of the study.  Parameters, the bar
    aggregation rule, the firing conditions and their source file paths are pinned in
    CONFLUENCE_SPEC / CONFLUENCE_PROVENANCE below and reproduced in the receipt.

    NO-LOOKAHEAD / AVAILABILITY RULE — the one place this study deliberately reads their
    frame more strictly than their labels do.  `_3d_groups` LABELS each 3D bar by its OPEN
    date but computes it from the closes through its CLOSE session, so the open-date label
    is NOT an availability timestamp.  Every 3D quantity here is stamped available on its
    bar's CLOSE SESSION (their `close_dates`), which is the leak-free reading of their own
    frame and matches the discipline their own research module states explicitly
    (`research/master_indicator_fusion_lab.py`: "those labels denote bucket starts, so they
    are not suitable as availability timestamps").  Using the open-date label as the
    availability stamp would be a 2-session lookahead.  Same rule for the 2D legs, which is
    exactly what production's own `tf()` helper does with its `kmax` known-date series.

S2  WASHOUT DEPTH.  dd250 = close[T] / max(high, 250 bars) - 1, banded
      d0_gt_m20 . d1_m20_m35 . d2_m35_m50 . d3_le_m50
    plus DURATION-IN-DRAWDOWN = sessions since the name last printed a new 250-session
    high, banded  t0_le20 . t1_20_60 . t2_60_120 . t3_gt120.

S3  UNDER-200MA STATE.  close[T] < SMA(close, 200), plus the SESSIONS-BELOW streak, banded
      b0_above . b1_1_20 . b2_21_60 . b3_61_120 . b4_gt120.

S4  SECTOR-WIDE WASHOUT BREADTH.  Share of the name's sector members (data/china_search/
    members.parquet) whose dd250 sits at or below -35% (headline) and -20% (secondary) on
    the same date, LEAVE-ONE-OUT so the state measures the SECTOR and not the name.
    Banded  s0_le20 . s1_20_40 . s2_40_60 . s3_gt60 (per cent of members).
    CURRENT-MEMBERSHIP CAVEAT, stamped on every S4 cell: the sector map is TODAY's
    membership applied to 15 years of history.  Sector reclassification is not
    reconstructible from this store, so S4 measures breadth within today's sector
    definition and within this curated slice.

S5  BASE / ACCUMULATION FOOTPRINTS.
    S5a  vol-z20 during a LOW-VOLATILITY BASE.  base_flag = the name's own 20-bar realised
         volatility sits in the bottom third of its own trailing 250-bar distribution;
         vol-z20 is v0's f1, banded  v0_le0 . v1_0_1 . v2_1_2 . v3_gt2.
    S5b  cyq_perf WIN-RATE level and trajectory, from data/tushare/chips_hist.parquet (an
         ACCRUING store).  level banded  w0_le20 . w1_20_50 . w2_50_80 . w3_gt80;
         trajectory = winner[T] - winner[T - 20 sessions], banded
         g0_le_m10 . g1_m10_0 . g2_0_10 . g3_gt10.
         Band labels spell out their own boundaries: `_leY` is x <= Y, `_gtY` is
         x > Y (see _band; S4's ratio-of-small-integers makes boundary ties common).
         COVERAGE IS PRINTED HONESTLY AND IS THE POINT: this store begins long after the
         train and calibration splits, so S5b CANNOT appear in the headline era tables and
         is reported in its own coverage-bounded block, THIN-labelled throughout.
    The cyq_chips 筹码分布 concentration deepening the operator named is NOT yet possible —
    that history does not exist in this checkout.  Recorded in the ore ledger, not faked.

S6  PRE-REGISTERED CONJUNCTIONS (the mechanism is conjunctive):
      S1 x S2 . S1 x S3 . S1 x S5a . S2 x S4.

-------------------------------------------------------------------------------
8. QUESTIONS, IN ORDER
-------------------------------------------------------------------------------
Q1  Base-rate LIFT tables: P(first board within H | state) against the unconditional
    cold-universe rate, per BOARD x ERA x SPLIT, Wilson 95% intervals, a DATE-CLUSTERED t
    beside the per-row (IID) t, n printed on every cell.
Q2  The WINDOW-class twin of every Q1 table (cum and peak, both thresholds).
Q3  The PROPHET-SHAPED RANKING question.  Among names IN STATE on a date, does the v0
    feature battery (f1_vol_z20, f3_runup_5, f4_sector_heat, f7_dist_52w_low,
    f8_consec_up_days) rank the eventual boarders?  Day-weighted top-K precision,
    K in {1, 3, 5}, against RANDOM-WITHIN-STATE (in expectation the state's own per-date
    base rate).  BOTH rank directions are pre-registered and BOTH are printed — v0's
    top-bucket directions were measured on LADDER-CONDITIONED cohorts and a sign flip
    inside a washout state would be a FINDING, so choosing the winning direction post hoc
    is forbidden and the multiplicity is counted.
    STATE SELECTION, pre-registered so it cannot be shopped: the ranking arm runs on (i)
    the product's own position state `s1_3d_long`, and (ii) the S6 conjunction with the
    highest FIT-window first-board lift — selected on FIT ONLY and then applied to the
    holdout untouched.
Q4  Survivorship sanity note stamped on every table (sec.1).

-------------------------------------------------------------------------------
9. INFERENCE STANDARD (sec.0 gates 5/7 and the sec.6.4 NULL-HEADLINE STANDARD, binding on
   every receipt from W3-B onward)
-------------------------------------------------------------------------------
  * Wilson 95% on every rate.  THIN label at n < 20 for rate cells; the ranking arm needs
    MIN_FIT_CORE_POS = 150 positives in the fit core before it is modelled at all.
  * Every AFFIRMATIVE magnitude — not just the nulls — carries a DATE-CLUSTERED t and a
    SESSION BOOTSTRAP (dates resampled with replacement, B = 2000, seeded) before it may be
    called supported.  No affirmative claim rests on an IID interval alone.
  * Every affirmative headline cell additionally carries a PERMUTATION NULL with an
    ERA-PRESERVING arm beside the global one.  The permutation is exact and in closed form:
    hypergeometric resampling of the state-label allocation inside each block IS the
    permutation distribution of that label, not an approximation of it.
       perm_global   one block: the whole board x split cold universe
       perm_era      blocks: era          (the ERA-PRESERVING ARM, mandated)
       perm_date     blocks: trading date (strongest — preserves era AND the
                     cross-sectional composition of every session)
    N_PERM = 2000 draws, seeded.  The null MEAN and SD are printed beside every p-value so
    no single draw is ever quoted against an unstated null spread (W3-B's review MAJOR).
  * S7 LAW: every verify predicate is keyed to a series that CAN move.  The verify battery
    asserts on measured quantities and each check records a MUTATION PROBE — the same
    predicate re-evaluated on a deliberately corrupted copy of its own input — proving the
    check is capable of failing.  A check that cannot fail is a defect, not a pass.
  * Multiplicity is counted and printed.  Nothing is corrected away; the count IS the
    disclosure.

-------------------------------------------------------------------------------
10. DETERMINISM
-------------------------------------------------------------------------------
Run as `TZ=UTC python3 research/cn_prophet_audit/washout_onset_w1.py` from the repo root.
No wall-clock, no runtime and no hostname enter the JSON: two consecutive runs at the same
commit produce BYTE-IDENTICAL output.  All resampling is seeded (SEED = 20260810).  Store
vintage (git SHAs, row counts, the event-tape identity) is stamped in `vintage`.

-------------------------------------------------------------------------------
AMENDMENTS (post-first-number changes; "none" means the pre-registration held)
-------------------------------------------------------------------------------
A1  VERIFY-ONLY, no measurement changed.  On the first run the `split_embargo_covers_max
    _horizon` predicate read its session universe off the `cold` frame, which is ALREADY
    split-filtered — so "sessions after the last kept date" was 0 by construction for every
    split and the predicate was keyed to a series that COULD NOT MOVE.  It reported FALSE
    (0 < 20) rather than a false PASS, which is how it surfaced.  The universe now comes
    from the unfiltered panel.  This is the S7 class the sec.9 law names; it is recorded
    here rather than silently corrected.  No table, rate, lift, null or ranking number in
    this receipt is affected — the embargo itself was always applied in `assign_splits`;
    only its AUDIT was blind.
A2  ADDED AFTER SEEING THE RAW LIFTS, and declared here because that is what the protocol
    requires.  Two CONTROLS were added, neither of which can create an affirmative result:
    (a) `volatility_matched_control` — the washout states are affirmative, and a deeply
        drawn-down name is a MORE VOLATILE name, so the raw lift cannot separate
        "board-specific ignition" from "this name moves a lot".  The control standardises
        the non-state rate over (date x the name's OWN realised-vol decile) strata and
        re-weights to the state's composition.  It can only pull a lift TOWARD 1.
    (b) `lift_relative_to_this_null` on every permutation arm — the date-preserving null
        mean came back at ~1.40, NOT 1.0, because the washout states sit on dates whose
        board rate is already elevated.  Quoting a raw lift against an implicit null of 1
        when the measured null is 1.40 is exactly the W3-B review MAJOR, so the ratio to
        each arm's own null mean is now printed beside the p-value.
    Both are strictly-subtractive disclosures on numbers that were already computed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

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
    _board_from_ticker,
    limit_width_for_date,
)

DATA = REPO / "data"
OUT_DIR = REPO / "research" / "cn_prophet_audit"
OUT_JSON = OUT_DIR / "WASHOUT_ONSET_W1_2026-08-10.json"

RAW_DIR = DATA / "china_stocks_raw"
MEMBERS_P = DATA / "china_search" / "members.parquet"
CHIPS_P = DATA / "tushare" / "chips_hist.parquet"
EVENTS_P = DATA / "china_microstructure" / "limit_events.parquet"
ST_P = DATA / "china_st" / "st_snapshot.parquet"

_MISSING = (
    "MISSING INPUT STORE: {path}\n"
    "This instrument reads the git-tracked CN data planes and vendors no copies.\n"
    "If this checkout is a SPARSE worktree, data/ is simply not checked out — heal with:\n"
    "  git sparse-checkout disable\n"
    "If a plane is genuinely absent, recover it from its authoring branch (all of these\n"
    "are git-tracked, so `git show <ref>:<path> > <path>` works):\n"
    "  git fetch origin claude/cn-limit-phantom-recovery claude/cn-limit-w1-dataheal\n"
    "  git show origin/claude/cn-limit-phantom-recovery:"
    "data/china_microstructure/limit_events.parquet"
    " > data/china_microstructure/limit_events.parquet\n"
    "  git show origin/claude/cn-limit-phantom-recovery:"
    "data/china_microstructure/limit_tape.parquet"
    " > data/china_microstructure/limit_tape.parquet\n"
    "(or simply run this on a checkout of main, where every plane above is tracked)."
)

for _p in (RAW_DIR, MEMBERS_P):
    if not _p.exists():
        raise SystemExit(_MISSING.format(path=_p))

# ── FROZEN PARAMETERS ─────────────────────────────────────────────────────────

SEED = 20260810

WINDOW_START = LIMIT_TAPE_START_DATE                 # 2011-01-01
WINDOW_END = pd.Timestamp("2026-08-07")              # the ledger's audit-window end

LIMIT_CLOSE_TOL = 0.002                              # v0's adjudicated PRIMARY tolerance
MAX_STEP_GAP_DAYS = 21                               # NEW — closure-tolerant chain (sec.6)
LEGACY_STEP_GAP_DAYS = 10                            # v0's rule, kept only for the receipt

COLD_LOOKBACK_K = 20                                 # bars with no board, INCLUDING T
HORIZONS = (5, 10, 20)
WINDOW_MULTS = (0.8, 1.5)                            # multiples of the board's own band

PURGE_SESSIONS_MANDATED = 10                         # reconciliation ledger sec.7
EMBARGO_SESSIONS = max(PURGE_SESSIONS_MANDATED, max(HORIZONS))    # = 20, disclosed sec.4

THIN_CELL_N = 20
MIN_FIT_CORE_POS = 150
TOP_K = (1, 3, 5)

N_PERM = 2000
N_BOOT = 2000

DD_LOOKBACK, DD_MINP = 250, 200
MA_LEN, MA_MINP = 200, 150
RV_LEN, RV_RANK_LOOKBACK, RV_BASE_Q = 20, 250, 1.0 / 3.0
VOLZ_LEN, VOLZ_MINP = 20, 15
LOW252, LOW252_MINP = 252, 120
CHIP_TRAJ_LAG = 20

SPLITS = OrderedDict([
    ("train", (pd.Timestamp("2011-01-01"), pd.Timestamp("2019-12-31"))),
    ("calibration", (pd.Timestamp("2020-01-01"), pd.Timestamp("2023-12-31"))),
    ("test", (pd.Timestamp("2024-01-02"), pd.Timestamp("2026-06-12"))),
    ("audit", (pd.Timestamp("2026-06-15"), pd.Timestamp("2026-08-07"))),
])
FIT_SPLITS = ("train", "calibration")
HOLDOUT_SPLIT = "test"

ERA_BOUNDS = [
    ("e1_2011_14", 2011, 2014), ("e2_2015_mania", 2015, 2015),
    ("e3_2016_18_crackdown", 2016, 2018), ("e4_2019_21_revival", 2019, 2021),
    ("e5_2022_23_grind", 2022, 2023), ("e6_2024_26_current", 2024, 2026),
]

RANK_FEATURES = OrderedDict([
    ("f1_vol_z20", "volume z-score of bar T vs its own prior 20 bars"),
    ("f3_runup_5", "5-session run-up: close[T] / close[T-5] - 1"),
    ("f4_sector_heat", "same-day sector limit-up count at T, leave-one-out"),
    ("f7_dist_52w_low", "distance from the 52w low: close[T] / min(low, 252 bars) - 1"),
    ("f8_consec_up_days", "consecutive up-close days ending at T"),
])

SURVIVORSHIP_STAMP = (
    "LARGE-CAP SLICE, SURVIVORS ONLY. The 1,842 curated names are 35.37% of active SH/SZ, "
    "0 of 329 BSE, median cached cap 187.7 yi vs 37.85 yi omitted, and 36.09% of "
    "canonicalised zt-pool names. Delisted names are absent, so every rate here is "
    "measured on names that lived. NOTHING in this file supports extrapolation to small "
    "caps; that remains a sampling-gap prior, never proven alpha."
)

TIER_STAMP = ("display / audit tier — not a promotion, not a gate, not a ranker, not a "
              "sizing input; no entry book is implied and no expectancy is quoted")

# ── S1 — THE TERMINAL'S OWN CONFLUENCE DEFINITION, TRANSCRIBED ────────────────
# Extracted from the charting-app (Terminal) production path.  Parameters, the bar
# aggregation rule and the firing conditions are THEIRS.  This study replicates and does
# not tune them.  The "Pine default inputs (the live configuration)" comment sits directly
# above these constants in their source.

RSI_LEN, FAST_LEN, BASE_LEN, SIG_LEN = 14, 14, 60, 5
STOCH_RSI_LEN, STOCH_LEN, SMOOTH_K, SMOOTH_D = 14, 14, 3, 3
OB, OS = 80, 20
CONF_W = 8
BUY_RSI_MAX = 65
EXT_RSI = 70
REV_BARS = 3
MIN_3D_BARS = 90                    # their compute_signals warm-up gate
CB_RECENT_BARS_3D = 2               # THIS study's state form: bars_since(CB) <= 2 (3D bars)

CONFLUENCE_SPEC = {
    "source_repo": "/Users/chriswong/Documents/Cluade/charting-app",
    "product_name": "Golden Oracle / 黄金神谕",
    "indicator_id": "confluence_rsimacd_stochrsi_mtf",
    "engine_tag": "python:signal_layer.confluence_v2@v2",
    "production_files": [
        "signal_layer/confluence.py   (the oracle: params, 3D grouping, CB/CS)",
        "signal_layer/confluence_v2.py (GC v2: 2D legs, anticipation dot, ARM/CONFIRM)",
        "signal_layer/contracts.py    (FLAGSHIP_PARAMS, engine tag, unified signals)",
    ],
    "parameters": {
        "RSI_LEN": RSI_LEN, "FAST_LEN": FAST_LEN, "BASE_LEN": BASE_LEN, "SIG_LEN": SIG_LEN,
        "STOCH_RSI_LEN": STOCH_RSI_LEN, "STOCH_LEN": STOCH_LEN,
        "SMOOTH_K": SMOOTH_K, "SMOOTH_D": SMOOTH_D,
        "OB": OB, "OS": OS, "CONF_W": CONF_W, "BUY_RSI_MAX": BUY_RSI_MAX,
        "EXT_RSI": EXT_RSI, "REV_BARS": REV_BARS, "MIN_3D_BARS": MIN_3D_BARS,
        "macd_kind": "RSI-BASED — EMA(RSI,14) - EMA(RSI,60), signal EMA(macd,5)",
        "stoch_kind": "stochastic OF the RSI(14) over a 14-bar window, %K=SMA3, %D=SMA3",
        "rsi_smoothing": "Wilder RMA, SMA-SEEDED (Pine ta.rma), not plain ewm",
        "ema_smoothing": "Pine ta.ema == ewm(adjust=False), seeded on the first valid value",
        "primary_timeframe": "3D (three TRADING SESSIONS)",
        "mtf_confirm": "1W (calendar W-FRI resample), prior fully-closed weekly bar",
    },
    "aggregation_rule_3d": {
        "kind": "SESSION-GROUPED, NOT a calendar resample",
        "anchor": "the symbol's FIRST listed session (IPO); bar_anchor = 0 on full history",
        "phase": "opens[0]=True; opens[1:] = ((arange(n)+bar_anchor)[:-1] % 3 == 0) — so a "
                 "bar closes whenever the global session index is divisible by 3",
        "label": "the bar's OPEN date (TradingView's bar timestamp)",
        "ohlc": "CLOSE-ONLY. No open/high/low/volume is aggregated at all; the bar's value "
                "is the LAST session's close. Their design goal, so CN/HK names with "
                "daily closes only get the full surface.",
        "their_own_warning": "pandas resample('3B') is WRONG — it buckets by the Mon-Fri "
                             "calendar and mis-splits real sessions around every holiday. "
                             "On NVDA that moved ~80% of signal dates.",
        "this_study": "bar_anchor = 0, because china_stocks_raw carries each name's FULL "
                      "history from its listing session, which is their documented "
                      "full-history contract.",
    },
    "aggregation_rule_2d": {
        "kind": "CALENDAR business-day resample — close.resample('2B').last()",
        "where": "confluence_v2.early_dots (line ~369) and confluence_v2._arm_event_daily "
                 "tf(close, 2) (line ~406)",
        "label": "the bucket START (left edge); the KNOWN date is the last real session in "
                 "the bucket (their tf() helper's kmax series)",
        "known_defect_stamped": "This is the SAME class of phasing bug their own 3D "
                                "docstring calls WRONG: a holiday inside the pair "
                                "mis-splits which real sessions share a 2D bar. Their "
                                "research module (research/master_indicator_fusion_lab.py, "
                                "session_bars()) prototypes an IPO-phased 2D fix that is "
                                "NOT wired into signal_layer/. This study replicates "
                                "PRODUCTION, defect included, because testing THEIR live "
                                "construction is the point. The session-phased 2D variant "
                                "is logged as ORE, not silently substituted.",
        "load_bearing": "the 2D bear-cross leg is the sole source of the shipped unified "
                        "SELL marker via contracts._extract_signals, so 2D is production, "
                        "not a cosmetic side channel.",
    },
    "firing_conditions": {
        "CB_buy_3d": "macd_bull & recent_b1 & confirm_bull & buy_regime_ok, where "
                     "macd_bull = crossover(macd, sig); recent_b1 = bars_since(crossover"
                     "(k,d)) <= 8; confirm_bull = w_bull_on3 | (d.rolling(8).min() < 20); "
                     "buy_regime_ok = rsi14 < 65",
        "CS_sell_3d": "macd_bear & recent_s1 & confirm_bear & recent_extended, where "
                      "confirm_bear = w_bear_on3 | (d.rolling(8).max() > 80); "
                      "recent_extended = (k.rolling(8).max() >= 80) | "
                      "(rsi14.rolling(8).max() >= 70)",
        "revBuy": "macd_bull & (bars_since(CS) <= 3)   [fast-reversal re-buy]",
        "revSell": "macd_bear & (bars_since(CB) <= 3)  [dropped as a scored exit in v2]",
        "v2_traded_stream": "enter = (CB | revBuy) & ~bear_block ; exit = CS & ~strong_bull",
        "anticipation_dot": "3D stoch bull cross AND 3D d.rolling(8).min() < 20 (from "
                            "oversold) AND the 2D RSI-MACD histogram RISING, mapped onto "
                            "3D rows by each bar's CLOSE session date",
    },
    "deviations_from_production_declared": [
        "AVAILABILITY STAMP: every 3D/2D quantity is stamped on its bar's CLOSE session "
        "(their close_dates / tf() kmax), never on the OPEN-date label. Using the label "
        "would be a 2-session lookahead. This is stricter than their frame's index and is "
        "the same discipline their own research module states.",
        "v2 bear_block / strong_bull filters are OMITTED from the position-state form. "
        "bear_block is 2W-derived and their own docstring says 2W 'only feeds the "
        "fixed=True backtest's bear_block, never live CB/CS'. Logged as ore.",
        "The 2D BULLISH macd cross is a MIRROR of their production BEAR leg. Production "
        "only uses the bear direction (for the SELL marker), so the bullish mirror is "
        "THIS STUDY'S construction and is labelled as such — it is NOT presented as one "
        "of their definitions.",
        "china_stocks_raw carries zero-volume stale-price suspension placeholders. The "
        "confluence transcription is CLOSE-ONLY and volume-blind exactly as production is, "
        "so those rows enter the session grouping the way any daily close feed would. The "
        "suspension-aware variant is logged as ore. Note the CONDITIONING and OUTCOME bars "
        "are still live-gated — only the indicator's own input is production-faithful.",
    ],
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _r(x, nd=4):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if np.isfinite(x) else None


def streak_lengths(flags) -> np.ndarray:
    """Run length of consecutive True ending at each position (v0's helper, vectorised)."""
    f = np.asarray(flags, dtype=bool)
    n = f.size
    if n == 0:
        return np.zeros(0, dtype=np.int32)
    pos = np.arange(n, dtype=np.int64)
    reset = np.maximum.accumulate(np.where(~f, pos + 1, 0))
    return np.where(f, pos + 1 - reset, 0).astype(np.int32)


def bars_since_np(cond) -> np.ndarray:
    """Bars since `cond` was last True (0 on a True bar, NaN before the first) — their rule."""
    c = np.asarray(cond, dtype=bool)
    n = c.size
    pos = np.arange(n, dtype=np.int64)
    last = np.maximum.accumulate(np.where(c, pos, -1))
    return np.where(last >= 0, (pos - last).astype(np.float64), np.nan)


def wilson(k: int, n: int, z: float = 1.96):
    if n <= 0:
        return None
    p = k / n
    den = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [_r(100.0 * (centre - half) / den, 4), _r(100.0 * (centre + half) / den, 4)]


def jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        f = float(obj)
        return f if np.isfinite(f) else None
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


def era_of(year: int) -> str:
    for name, lo, hi in ERA_BOUNDS:
        if lo <= year <= hi:
            return name
    return "e0_out_of_range"


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "UNAVAILABLE"


# ── the Terminal's indicator math, transcribed ────────────────────────────────

def _rma_reference(a: np.ndarray, n: int) -> np.ndarray:
    """LITERAL transcription of their `_rma` loop. Kept as the parity reference only."""
    out = np.full(a.shape, np.nan)
    fin = np.flatnonzero(np.isfinite(a))
    if fin.size < n:
        return out
    start = fin[0]
    seed = start + n - 1
    out[seed] = np.mean(a[start:seed + 1])
    alpha = 1.0 / n
    for t in range(seed + 1, a.size):
        out[t] = alpha * a[t] + (1.0 - alpha) * out[t - 1]
    return out


def _rma(a: np.ndarray, n: int) -> np.ndarray:
    """Wilder RMA, SMA-seeded — their `_rma`, vectorised.

    Their recursion is exactly ewm(alpha=1/n, adjust=False) once the SMA seed is planted
    as the first valid observation, because ewm(adjust=False) initialises on the first
    valid value and then recurses identically.  `verify.terminal_rma_parity` asserts this
    against `_rma_reference` on sampled real series and carries a mutation probe.
    """
    out = np.full(a.shape, np.nan)
    fin = np.flatnonzero(np.isfinite(a))
    if fin.size < n:
        return out
    start = fin[0]
    seed = start + n - 1
    if seed >= a.size:
        return out
    b = a.astype(np.float64).copy()
    b[:seed] = np.nan
    b[seed] = np.mean(a[start:seed + 1])
    return pd.Series(b).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def t_rsi(close: np.ndarray, n: int = RSI_LEN) -> np.ndarray:
    """Their `rsi`: RMA of gains over RMA of losses, with the Pine down==0 -> 100 mask."""
    d = np.diff(close, prepend=np.nan)
    up = np.where(np.isfinite(d), np.clip(d, 0, None), np.nan)
    dn = np.where(np.isfinite(d), -np.clip(d, None, 0), np.nan)
    ru, rd = _rma(up, n), _rma(dn, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        rs = np.where(rd != 0, ru / rd, np.nan)
        out = 100.0 - 100.0 / (1.0 + rs)
    return np.where(rd == 0, 100.0, out)


def t_ema(a: np.ndarray, span: int) -> np.ndarray:
    """Their `ema`: Pine ta.ema == ewm(adjust=False), NO min_periods."""
    return pd.Series(a).ewm(span=span, adjust=False).mean().to_numpy()


def t_rsi_macd(close: np.ndarray):
    """Their `rsi_macd`: the Pine RSI-based MACD."""
    r = t_rsi(close, RSI_LEN)
    line = t_ema(r, FAST_LEN) - t_ema(r, BASE_LEN)
    return line, t_ema(line, SIG_LEN)


def t_stoch_rsi_kd(close: np.ndarray):
    """Their `stoch_rsi_kd`: stochastic OF the RSI, then %K/%D smoothing."""
    r = pd.Series(t_rsi(close, STOCH_RSI_LEN))
    lo = r.rolling(STOCH_LEN).min()
    hi = r.rolling(STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100.0
    k = rawk.rolling(SMOOTH_K).mean()
    d = k.rolling(SMOOTH_D).mean()
    return k.to_numpy(), d.to_numpy()


def t_crossover(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = np.asarray(a, float), np.asarray(b, float)
    pa, pb = np.r_[np.nan, a[:-1]], np.r_[np.nan, b[:-1]]
    return (a > b) & (pa <= pb)


def t_crossunder(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = np.asarray(a, float), np.asarray(b, float)
    pa, pb = np.r_[np.nan, a[:-1]], np.r_[np.nan, b[:-1]]
    return (a < b) & (pa >= pb)


def _roll(a: np.ndarray, w: int, how: str) -> np.ndarray:
    s = pd.Series(a).rolling(w)
    return (s.min() if how == "min" else s.max()).to_numpy()


def three_d_groups(n: int, bar_anchor: int = 0):
    """Their `_3d_groups` phase, on positions. Returns (open_pos, close_pos)."""
    if n == 0:
        e = np.zeros(0, dtype=np.int64)
        return e, e
    gi = np.arange(n, dtype=np.int64) + int(bar_anchor)
    opens = np.empty(n, dtype=bool)
    opens[0] = True
    opens[1:] = (gi[:-1] % 3 == 0)
    open_pos = np.flatnonzero(opens)
    close_pos = np.append(open_pos[1:] - 1, n - 1)
    return open_pos, close_pos


def project_by_close(close_pos: np.ndarray, series: np.ndarray, n: int) -> np.ndarray:
    """Map an aggregated STATE onto daily positions with no lookahead.

    Daily bar T carries the value of the most recent aggregated bar that CLOSED at or
    before T.  Bars preceding the first closed aggregated bar are NaN.
    """
    out = np.full(n, np.nan, dtype=np.float64)
    if close_pos.size == 0:
        return out
    pos = np.searchsorted(close_pos, np.arange(n), side="right") - 1
    ok = pos >= 0
    out[ok] = np.asarray(series, dtype=np.float64)[pos[ok]]
    return out


def event_on_close(close_pos: np.ndarray, flags: np.ndarray, n: int) -> np.ndarray:
    """Stamp an aggregated EVENT on the daily bar where it became known (its close)."""
    out = np.zeros(n, dtype=bool)
    if close_pos.size:
        f = np.asarray(flags, dtype=bool)
        out[close_pos[f]] = True
    return out


# ── STAGE 0 — stores ──────────────────────────────────────────────────────────

def load_st_cohort():
    if not ST_P.exists():
        return frozenset(), "st_snapshot.parquet MISSING — no ST exclusion applied"
    df = pd.read_parquet(ST_P)
    tick = frozenset(df["ticker"].astype(str).tolist())
    return tick, f"n={len(tick)} tickers, asof {sorted(set(df['asof'].astype(str)))}"


def load_sector_map():
    df = pd.read_parquet(MEMBERS_P)
    m = {str(k): str(v) for k, v in df["sector"].items()}
    return m, {
        "source": "data/china_search/members.parquet",
        "n_tickers": len(m),
        "n_sectors": int(df["sector"].nunique()),
        "caveat": ("CURRENT sector membership applied to 15 years of history — sector "
                   "reclassification is not reconstructible from this store. S4 breadth "
                   "and f4 sector heat therefore measure TODAY's sector definition, "
                   "within THIS curated universe, not the sector as constituted in 2013."),
    }


def load_chips():
    """cyq_perf win-rate history (an ACCRUING store). Coverage is printed, never assumed."""
    if not CHIPS_P.exists():
        return None, {"source": str(CHIPS_P), "status": "MISSING — S5b not measured"}
    df = pd.read_parquet(CHIPS_P)
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d")
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    df["winner_traj20"] = df.groupby("ticker", observed=True)["winner"].diff(CHIP_TRAJ_LAG)
    meta = {
        "source": "data/tushare/chips_hist.parquet",
        "rows": int(len(df)),
        "tickers": int(df["ticker"].nunique()),
        "coverage_first": df["date"].min().strftime("%Y-%m-%d"),
        "coverage_last": df["date"].max().strftime("%Y-%m-%d"),
        "sessions": int(df["date"].nunique()),
        "accruing_store_note": (
            "This store BEGINS well after the train and calibration splits. S5b therefore "
            "CANNOT appear in the headline era tables and is reported only in its own "
            "coverage-bounded block, THIN-labelled. Its window overlaps the LOCKED TEST "
            "and AUDIT splits only, so nothing in S5b has an out-of-sample arm at all — "
            "it is hypothesis-generating, not evidence."),
        "trajectory_note": (f"winner_traj20 = winner - winner.shift({CHIP_TRAJ_LAG}) on the "
                            "store's OWN session axis per ticker; a gap in the store makes "
                            "the lag longer than 20 real sessions and those rows are kept "
                            "with the caveat rather than dropped."),
    }
    return df, meta


def tape_receipt():
    """The house event tape — used ONLY as an independent cross-check, never as input."""
    if not EVENTS_P.exists():
        return {"status": "MISSING", "path": str(EVENTS_P.relative_to(REPO))}
    e = pd.read_parquet(EVENTS_P)
    up = e[e["event"] == "sealed_up"]
    return {
        "path": "data/china_microstructure/limit_events.parquet",
        "rows": int(len(e)),
        "sealed_up_rows": int(len(up)),
        "tickers": int(e["ticker"].nunique()),
        "date_range": [str(e["date"].min().date()), str(e["date"].max().date())],
        "store_commit": _git("log", "-1", "--format=%H", "--",
                             "data/china_microstructure/limit_events.parquet"),
        "vintage_ruling": (
            "VINTAGE STAMPED HONESTLY. The reconciliation ledger sec.3 describes a healed "
            "tape at 71,463 events (#5059's heal) and a Codex tape at 71,692. NEITHER is "
            "the tape present on main at this commit: main carries the legacy store plus "
            "nightly appends, measured above. The named recovery branch "
            "claude/cn-limit-phantom-recovery carries the 60,428-row legacy store, not the "
            "heal. This instrument therefore does NOT consume the tape as input at all — "
            "it re-derives every event from china_stocks_raw with v0's tolerant detector "
            "(the same basis every W1-W3 receipt used) and reports the tape only as an "
            "independent parity cross-check, so no tape-vintage ambiguity can move a "
            "single number in this file. sec.11.1 (vintage is part of construction "
            "identity) is satisfied by construction rather than by assertion."),
        "strict_vs_tolerant": (
            "The tape's sealed_up is the STRICT basis; this study's PRIMARY definition is "
            "v0's adjudicated TOLERANT one (0.2% cushion), so the two counts are expected "
            "to differ and their ratio is reported, not asserted equal."),
    }


# ── STAGE 1 — per-ticker computation ──────────────────────────────────────────

def board_keys(board: str, idx: pd.DatetimeIndex) -> np.ndarray:
    if board != "chinext":
        return np.full(len(idx), board, dtype=object)
    wide = idx.to_numpy() >= CHINEXT_WIDE_DATE.to_datetime64()
    return np.where(wide, "chinext20", "chinext10").astype(object)


def confluence_states(close: np.ndarray, idx: pd.DatetimeIndex) -> dict:
    """The Terminal's Golden Oracle states, projected onto daily positions, no lookahead."""
    n = len(close)
    out = {key: np.zeros(n, dtype=bool) for key in
           ("s1_3d_cb", "s1_3d_cb_recent", "s1_3d_long", "s1_2d_rising",
            "s1_dot", "s1_dot_recent")}
    out["s1_warm"] = np.zeros(n, dtype=bool)

    fin = np.flatnonzero(np.isfinite(close))
    if fin.size < 3 * MIN_3D_BARS:
        return out
    c = close[fin]
    cidx = idx[fin]
    m = c.size

    open_pos, close_pos = three_d_groups(m, 0)          # their bar_anchor=0 contract
    if open_pos.size < MIN_3D_BARS:
        return out
    s3 = c[close_pos]
    close_dates = cidx[close_pos]

    macd, sig = t_rsi_macd(s3)
    k, d = t_stoch_rsi_kd(s3)
    r14 = t_rsi(s3, RSI_LEN)

    stoch_bull, stoch_bear = t_crossover(k, d), t_crossunder(k, d)
    macd_bull, macd_bear = t_crossover(macd, sig), t_crossunder(macd, sig)

    # weekly (1W) confirm gate — their session-aligned, leak-free mapping
    wk = pd.Series(c, index=cidx).resample("W-FRI").last().dropna()
    if len(wk):
        wmacd, wsig = t_rsi_macd(wk.to_numpy())
        wk_bull, wk_bear = (wmacd >= wsig), (wmacd <= wsig)
        wpos = wk.index.searchsorted(close_dates, side="left") - 1
        wok = wpos >= 0
        wci = np.clip(wpos, 0, len(wk_bull) - 1)
        w_bull_on3 = wok & wk_bull[wci]
        w_bear_on3 = wok & wk_bear[wci]
    else:
        w_bull_on3 = w_bear_on3 = np.zeros(open_pos.size, dtype=bool)

    b1_from_os = _roll(d, CONF_W, "min") < OS
    s1_from_ob = _roll(d, CONF_W, "max") > OB
    recent_b1 = bars_since_np(stoch_bull) <= CONF_W
    recent_s1 = bars_since_np(stoch_bear) <= CONF_W
    confirm_bull = w_bull_on3 | np.nan_to_num(b1_from_os, nan=0.0).astype(bool)
    confirm_bear = w_bear_on3 | np.nan_to_num(s1_from_ob, nan=0.0).astype(bool)
    buy_regime_ok = r14 < BUY_RSI_MAX
    recent_extended = (_roll(k, CONF_W, "max") >= OB) | (_roll(r14, CONF_W, "max") >= EXT_RSI)

    cb = macd_bull & recent_b1 & confirm_bull & buy_regime_ok
    cs = macd_bear & recent_s1 & confirm_bear & np.nan_to_num(
        recent_extended, nan=0.0).astype(bool)
    rev_buy = macd_bull & (bars_since_np(cs) <= REV_BARS)

    valid = np.isfinite(macd) & np.isfinite(sig) & np.isfinite(k) & np.isfinite(d) \
        & np.isfinite(r14)
    cb, cs, rev_buy = cb & valid, cs & valid, rev_buy & valid

    # v2 traded stream, as a POSITION STATE. enter = CB | revBuy, exit = CS.
    # On a bar carrying both, the exit wins (last_enter == last_exit -> not long).
    j = np.arange(open_pos.size, dtype=np.int64)
    enter = cb | rev_buy
    last_in = np.maximum.accumulate(np.where(enter, j, -1))
    last_out = np.maximum.accumulate(np.where(cs, j, -1))
    long_state = last_in > last_out

    # ---- 2D legs (production's CALENDAR resample, defect included by design) ----
    sc = pd.Series(c, index=cidx)
    sm = sc.resample("2B").last().dropna()
    rising2 = np.zeros(len(sm), dtype=bool)
    if len(sm) > 2:
        m2, s2 = t_rsi_macd(sm.to_numpy())
        hist2 = m2 - s2
        rising2 = np.r_[False, hist2[1:] > hist2[:-1]]
        rising2 = np.where(np.isfinite(np.r_[np.nan, hist2[:-1]]) & np.isfinite(hist2),
                           rising2, False)
    # (a) production's own mapping onto 3D rows: bucket-START searchsorted
    if len(sm):
        wp = sm.index.searchsorted(pd.DatetimeIndex(close_dates), side="right") - 1
        wok2 = wp >= 0
        rising_on3 = wok2 & rising2[np.clip(wp, 0, len(rising2) - 1)]
    else:
        rising_on3 = np.zeros(open_pos.size, dtype=bool)
    dot = stoch_bull & np.nan_to_num(b1_from_os, nan=0.0).astype(bool) & rising_on3 & valid

    # (b) availability-corrected standalone 2D state: map by the bucket's KNOWN date
    #     (the last REAL session in the bucket) — production's own tf() kmax discipline.
    if len(sm):
        kmax = sc.index.to_series().resample("2B").max().reindex(sm.index).dropna()
        known_pos = np.searchsorted(cidx.to_numpy(),
                                    pd.DatetimeIndex(kmax.to_numpy()).to_numpy(), "left")
        r2 = rising2[: len(kmax)]
        d2 = np.full(m, np.nan)
        ok = known_pos < m
        d2[known_pos[ok]] = r2[ok].astype(float)
        s1_2d_daily = pd.Series(d2).ffill().fillna(0.0).to_numpy().astype(bool)
    else:
        s1_2d_daily = np.zeros(m, dtype=bool)

    # ---- project 3D quantities onto the daily axis by CLOSE session (availability) ----
    cb_recent_3d = bars_since_np(cb) <= CB_RECENT_BARS_3D
    dot_recent_3d = bars_since_np(dot) <= CB_RECENT_BARS_3D

    def _daily_state(flags):
        v = project_by_close(close_pos, np.asarray(flags, float), m)
        return np.nan_to_num(v, nan=0.0).astype(bool)

    res_c = {
        "s1_3d_cb": event_on_close(close_pos, cb, m),
        "s1_3d_cb_recent": _daily_state(cb_recent_3d),
        "s1_3d_long": _daily_state(long_state),
        "s1_2d_rising": s1_2d_daily,
        "s1_dot": event_on_close(close_pos, dot, m),
        "s1_dot_recent": _daily_state(dot_recent_3d),
        "s1_warm": _daily_state(np.ones(open_pos.size, dtype=bool)),
    }
    for key, arr in res_c.items():
        full = np.zeros(n, dtype=bool)
        full[fin] = arr
        out[key] = full
    return out


def process_ticker(ticker: str, df: pd.DataFrame, board: str):
    if df is None or len(df) < 400:
        return None, {"skipped_short": 1}
    df = df.sort_index()
    idx = pd.DatetimeIndex(df.index)
    close = df["close"].to_numpy(dtype=np.float64)
    high = df["high"].to_numpy(dtype=np.float64)
    low = df["low"].to_numpy(dtype=np.float64)
    open_ = df["open"].to_numpy(dtype=np.float64)
    vol = df["volume"].to_numpy(dtype=np.float64)
    n = close.size

    pc = np.r_[np.nan, close[:-1]]

    if board == "chinext":
        width = np.where(idx.to_numpy() >= CHINEXT_WIDE_DATE.to_datetime64(),
                         limit_width_for_date("chinext", CHINEXT_WIDE_DATE),
                         limit_width_for_date(
                             "chinext", CHINEXT_WIDE_DATE - pd.Timedelta(days=1)))
    else:
        width = np.full(n, limit_width_for_date(board, WINDOW_END))
    width = width.astype(np.float64)

    excl = np.zeros(n, dtype=bool)
    ipo_window = CHINEXT_STAR_IPO_WINDOW if board in ("star", "chinext") else (
        PRE2014_IPO_WINDOW if idx.min() < IPO_PRE2014_DATE else 0)
    if ipo_window:
        excl[:ipo_window] = True
    excl |= ~np.isfinite(pc) | (pc <= 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        open_move = np.abs(open_ - pc) / pc
    excl |= np.isfinite(open_move) & (open_move > width * 1.5) & ~excl
    excl |= np.isfinite(vol) & (vol <= 0) & ~excl

    in_win = np.asarray((idx >= WINDOW_START) & (idx <= WINDOW_END), dtype=bool)
    live = ~excl & np.isfinite(close) & (close > 0)

    with np.errstate(invalid="ignore"):
        lim_up = np.round(pc * (1.0 + width), 2)
    lu = live & np.isfinite(lim_up) & (close >= lim_up * (1.0 - LIMIT_CLOSE_TOL))

    boards_in_k = pd.Series(lu.astype(np.float64)).rolling(
        COLD_LOOKBACK_K, min_periods=COLD_LOOKBACK_K).sum().to_numpy()
    cold = live & np.isfinite(boards_in_k) & (boards_in_k == 0)

    days = idx.to_numpy().astype("datetime64[D]").astype(np.int64)
    gaps = np.r_[np.diff(days), np.iinfo(np.int32).max]
    step = np.zeros(n, dtype=bool)
    step_legacy = np.zeros(n, dtype=bool)
    if n > 1:
        step[:-1] = live[1:] & (gaps[:-1] <= MAX_STEP_GAP_DAYS)
        step_legacy[:-1] = live[1:] & (gaps[:-1] <= LEGACY_STEP_GAP_DAYS)
    run_fwd = streak_lengths(step[::-1])[::-1]
    run_fwd_legacy = streak_lengths(step_legacy[::-1])[::-1]

    BIG = np.iinfo(np.int32).max
    lu_pos = np.flatnonzero(lu)
    pos = np.arange(n)
    if lu_pos.size == 0:
        dist_next = np.full(n, BIG, dtype=np.int64)
    else:
        nxt = np.searchsorted(lu_pos, pos, side="right")
        dist_next = np.where(nxt < lu_pos.size,
                             lu_pos[np.clip(nxt, 0, lu_pos.size - 1)] - pos, BIG)

    # ---- states ----
    s_close, s_high, s_low = pd.Series(close), pd.Series(high), pd.Series(low)
    hi250 = s_high.rolling(DD_LOOKBACK, min_periods=DD_MINP).max().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        dd250 = np.where(hi250 > 0, close / hi250 - 1.0, np.nan)
    at_high = np.isfinite(hi250) & (high >= hi250 * (1.0 - 1e-12))
    dd_dur = streak_lengths(~at_high & np.isfinite(hi250))

    ma200 = s_close.rolling(MA_LEN, min_periods=MA_MINP).mean().to_numpy()
    under_ma = np.isfinite(ma200) & (close < ma200)
    below_streak = streak_lengths(under_ma)

    with np.errstate(invalid="ignore", divide="ignore"):
        logret = np.r_[np.nan, np.log(close[1:] / close[:-1])]
    rv20 = pd.Series(logret).rolling(RV_LEN, min_periods=RV_LEN).std(ddof=1)
    rv_rank = rv20.rolling(RV_RANK_LOOKBACK, min_periods=DD_MINP).rank(pct=True).to_numpy()

    s_vol = pd.Series(vol)
    mu = s_vol.shift(1).rolling(VOLZ_LEN, min_periods=VOLZ_MINP).mean().to_numpy()
    sd = s_vol.shift(1).rolling(VOLZ_LEN, min_periods=VOLZ_MINP).std(ddof=0).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = np.where(sd > 0, (vol - mu) / sd, np.nan)
        f3 = close / np.r_[np.full(5, np.nan), close[:-5]] - 1.0
        low252 = s_low.rolling(LOW252, min_periods=LOW252_MINP).min().to_numpy()
        f7 = np.where(low252 > 0, close / low252 - 1.0, np.nan)
    f8 = streak_lengths(np.r_[False, close[1:] > close[:-1]]).astype(np.float32)

    conf = confluence_states(close, idx)

    # ---- outcomes ----
    cols = {}
    for H in HORIZONS:
        ok = run_fwd >= H
        cols[f"win_ok_{H}"] = ok
        cols[f"fb_{H}"] = ok & (dist_next <= H)
        with np.errstate(invalid="ignore", divide="ignore"):
            cum = np.r_[close[H:], np.full(H, np.nan)] / close - 1.0
            rmax = s_high.rolling(H).max().to_numpy()
            peak = np.r_[rmax[H:], np.full(H, np.nan)] / close - 1.0
        cols[f"cum_{H}"] = np.where(ok, cum, np.nan).astype(np.float32)
        cols[f"peak_{H}"] = np.where(ok, peak, np.nan).astype(np.float32)
        cols[f"win_ok_legacy_{H}"] = run_fwd_legacy >= H

    keep = in_win & live
    if not keep.any():
        return None, {"skipped_empty": 1}

    out = pd.DataFrame({
        "date": idx[keep],
        "ticker": ticker,
        "board_key": board_keys(board, idx)[keep],
        "w": width[keep].astype(np.float32),
        "lu": lu[keep],
        "cold": cold[keep],
        "dd250": dd250[keep].astype(np.float32),
        "dd_dur": dd_dur[keep].astype(np.int32),
        "under_ma": under_ma[keep],
        "below_streak": below_streak[keep].astype(np.int32),
        "rv_rank": rv_rank[keep].astype(np.float32),
        "f1_vol_z20": f1[keep].astype(np.float32),
        "f3_runup_5": f3[keep].astype(np.float32),
        "f7_dist_52w_low": f7[keep].astype(np.float32),
        "f8_consec_up_days": f8[keep],
    })
    for key, arr in conf.items():
        out[key] = arr[keep]
    for key, arr in cols.items():
        out[key] = arr[keep] if arr.dtype != np.float32 else arr[keep]
    stats = {
        "bars_in_window": int(keep.sum()),
        "lu_events": int((lu & keep).sum()),
        "cold_bars": int((cold & keep).sum()),
    }
    return out, stats


def build_panel():
    st_set, st_note = load_st_cohort()
    sector_map, sector_meta = load_sector_map()
    files = sorted(RAW_DIR.glob("*.parquet"))
    frames, agg = [], {"bars_in_window": 0, "lu_events": 0, "cold_bars": 0}
    kept = skipped_st = skipped_thin = 0
    boards_seen: dict[str, int] = {}
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
        out, stats = process_ticker(ticker, df, board)
        if out is None or out.empty:
            skipped_thin += 1
            continue
        for k in agg:
            agg[k] += stats.get(k, 0)
        boards_seen[board] = boards_seen.get(board, 0) + 1
        frames.append(out)
        kept += 1
    panel = pd.concat(frames, ignore_index=True)
    panel["sector"] = panel["ticker"].map(sector_map).fillna("UNKNOWN")
    meta = {
        "raw_store": "data/china_stocks_raw (back-adjusted OHLCV — see BASIS NOTE)",
        "files_found": len(files), "tickers_kept": kept,
        "tickers_skipped_st": skipped_st, "tickers_skipped_thin_or_unreadable": skipped_thin,
        "board_counts": boards_seen, "st_cohort": st_note, "sector_map": sector_meta,
        "window": [WINDOW_START.strftime("%Y-%m-%d"), WINDOW_END.strftime("%Y-%m-%d")],
        "live_bars": int(agg["bars_in_window"]),
        "tolerant_limit_up_closes": int(agg["lu_events"]),
        "cold_bars": int(agg["cold_bars"]),
        "board_key_counts": {str(k): int(v) for k, v in
                             panel["board_key"].value_counts().items()},
        "survivorship": SURVIVORSHIP_STAMP,
    }
    return panel, meta


# ── STAGE 2 — panel-level conditioners, splits, bands ─────────────────────────

def assign_splits(dates: pd.Series, embargo: int) -> tuple[pd.Series, dict]:
    """Split label per row, with the last `embargo` SESSIONS of each split dropped."""
    sess = np.array(sorted(pd.unique(dates)))
    lab = pd.Series(pd.NA, index=range(len(sess)), dtype="object")
    receipt = {}
    for name, (lo, hi) in SPLITS.items():
        inside = np.flatnonzero((sess >= lo.to_datetime64()) & (sess <= hi.to_datetime64()))
        keep = inside[:-embargo] if inside.size > embargo else np.array([], dtype=int)
        lab.iloc[keep] = name
        receipt[name] = {
            "sessions_in_range": int(inside.size), "sessions_kept": int(keep.size),
            "sessions_embargoed": int(inside.size - keep.size),
            "first_kept": str(pd.Timestamp(sess[keep[0]]).date()) if keep.size else None,
            "last_kept": str(pd.Timestamp(sess[keep[-1]]).date()) if keep.size else None,
        }
    m = pd.Series(lab.to_numpy(), index=pd.DatetimeIndex(sess))
    return dates.map(m), receipt


def _band(x, edges, labels, na="na"):
    """Left-open / right-closed banding: labels[i] holds for edges[i] < x <= edges[i+1].

    LABEL CONVENTION, stated because it is load-bearing: a band named `..._leY` is
    "x <= Y" and one named `..._gtY` is "x > Y".  This is not pedantry — S4's breadth is a
    ratio of SMALL INTEGER member counts, so exact ties at a boundary (3 of 5 members = 60.0%)
    are common rather than measure-zero, and a label reading "ge60" on a band that actually
    starts strictly above 60 would misdescribe a populated cell.  Numeric boundaries are
    unchanged from the pre-registration; only the names spell them out.
    """
    out = np.full(len(x), na, dtype=object)
    v = np.asarray(x, dtype=np.float64)
    fin = np.isfinite(v)
    for i, lab in enumerate(labels):
        lo, hi = edges[i], edges[i + 1]
        out[fin & (v > lo) & (v <= hi)] = lab
    return out


def attach_conditioners(panel: pd.DataFrame, chips):
    """Panel-level states (f4 heat, S4 breadth), splits, eras, bands, chips join."""
    meta = {}
    panel["year"] = panel["date"].dt.year.astype(np.int16)
    panel["era"] = panel["year"].map(era_of).astype("category")

    # f4 — sector limit-up heat at T, leave-one-out (v0's definition)
    grp = panel.groupby(["date", "sector"], observed=True)["lu"].transform("sum")
    panel["f4_sector_heat"] = (grp.to_numpy() - panel["lu"].to_numpy()).astype(np.float32)
    panel.loc[panel["sector"] == "UNKNOWN", "f4_sector_heat"] = np.nan

    # S4 — sector washout breadth, leave-one-out, per (date, sector)
    for tag, cut in (("35", -0.35), ("20", -0.20)):
        deep = (panel["dd250"].to_numpy() <= cut) & np.isfinite(panel["dd250"].to_numpy())
        panel["_deep"] = deep
        panel["_meas"] = np.isfinite(panel["dd250"].to_numpy())
        g = panel.groupby(["date", "sector"], observed=True)
        s_deep = g["_deep"].transform("sum").to_numpy()
        s_meas = g["_meas"].transform("sum").to_numpy()
        den = s_meas - panel["_meas"].to_numpy().astype(np.int64)
        num = s_deep - deep.astype(np.int64)
        with np.errstate(invalid="ignore", divide="ignore"):
            share = np.where(den > 0, 100.0 * num / den, np.nan)
        share = np.where(panel["sector"].to_numpy() == "UNKNOWN", np.nan, share)
        panel[f"sect_deep{tag}_pct"] = share.astype(np.float32)
    panel.drop(columns=["_deep", "_meas"], inplace=True)
    meta["sector_coverage_pct"] = _r(100.0 * float((panel["sector"] != "UNKNOWN").mean()), 2)

    split, split_receipt = assign_splits(panel["date"], EMBARGO_SESSIONS)
    panel["split"] = split
    meta["split_receipt"] = split_receipt
    split10, split10_receipt = assign_splits(panel["date"], PURGE_SESSIONS_MANDATED)
    panel["split_mandated10"] = split10
    meta["split_receipt_mandated10"] = split10_receipt

    # bands
    panel["dd_band"] = _band(panel["dd250"], [-np.inf, -0.50, -0.35, -0.20, np.inf],
                             ["d3_le_m50", "d2_m35_m50", "d1_m20_m35", "d0_gt_m20"])
    panel["dur_band"] = _band(panel["dd_dur"], [-np.inf, 20, 60, 120, np.inf],
                              ["t0_le20", "t1_20_60", "t2_60_120", "t3_gt120"])
    below = panel["below_streak"].to_numpy()
    panel["below_band"] = np.select(
        [below == 0, below <= 20, below <= 60, below <= 120],
        ["b0_above", "b1_1_20", "b2_21_60", "b3_61_120"], default="b4_gt120")
    panel["sect35_band"] = _band(panel["sect_deep35_pct"], [-np.inf, 20, 40, 60, np.inf],
                                 ["s0_le20", "s1_20_40", "s2_40_60", "s3_gt60"])
    panel["volz_band"] = _band(panel["f1_vol_z20"], [-np.inf, 0, 1, 2, np.inf],
                               ["v0_le0", "v1_0_1", "v2_1_2", "v3_gt2"])
    panel["base_flag"] = (panel["rv_rank"].to_numpy() <= RV_BASE_Q) & \
        np.isfinite(panel["rv_rank"].to_numpy())

    # S5b — chips join (coverage-bounded)
    if chips is not None:
        c = chips[["ticker", "date", "winner", "winner_traj20"]]
        panel = panel.merge(c, on=["ticker", "date"], how="left")
        panel["win_band"] = _band(panel["winner"], [-np.inf, 20, 50, 80, np.inf],
                                  ["w0_le20", "w1_20_50", "w2_50_80", "w3_gt80"])
        panel["traj_band"] = _band(panel["winner_traj20"], [-np.inf, -10, 0, 10, np.inf],
                                   ["g0_le_m10", "g1_m10_0", "g2_0_10", "g3_gt10"])
        meta["chips_join"] = {
            "rows_with_winner": int(panel["winner"].notna().sum()),
            "share_of_panel_pct": _r(100.0 * float(panel["winner"].notna().mean()), 3),
        }
    else:
        panel["win_band"] = "na"
        panel["traj_band"] = "na"
        meta["chips_join"] = {"status": "chips store MISSING — S5b not measured"}
    return panel, meta


def build_state_masks(cold: pd.DataFrame) -> "OrderedDict[str, np.ndarray]":
    """Every pre-registered conditioning state as a boolean mask. Families are tagged."""
    S: "OrderedDict[str, np.ndarray]" = OrderedDict()
    for c in ("s1_3d_cb_recent", "s1_3d_long", "s1_2d_rising", "s1_dot_recent"):
        S[f"S1|{c}"] = cold[c].to_numpy(bool)
    for col, fam in (("dd_band", "S2depth"), ("dur_band", "S2dur"),
                     ("below_band", "S3"), ("sect35_band", "S4"),
                     ("volz_band", "S5a_volz")):
        vals = cold[col].to_numpy()
        for lab in sorted({v for v in pd.unique(vals) if v != "na"}):
            S[f"{fam}|{lab}"] = (vals == lab)
    base = cold["base_flag"].to_numpy(bool)
    S["S5a|base_lowvol"] = base
    vz = cold["volz_band"].to_numpy()
    for lab in ("v0_le0", "v1_0_1", "v2_1_2", "v3_gt2"):
        S[f"S5a|base_x_{lab}"] = base & (vz == lab)
    # S6 — the pre-registered conjunctions (the mechanism is conjunctive)
    long_ = cold["s1_3d_long"].to_numpy(bool)
    dd = cold["dd_band"].to_numpy()
    bb = cold["below_band"].to_numpy()
    for lab in ("d3_le_m50", "d2_m35_m50", "d1_m20_m35", "d0_gt_m20"):
        S[f"S6|S1xS2_long_x_{lab}"] = long_ & (dd == lab)
    for lab in ("b0_above", "b1_1_20", "b2_21_60", "b3_61_120", "b4_gt120"):
        S[f"S6|S1xS3_long_x_{lab}"] = long_ & (bb == lab)
    for lab in ("v0_le0", "v1_0_1", "v2_1_2", "v3_gt2"):
        S[f"S6|S1xS5_long_base_x_{lab}"] = long_ & base & (vz == lab)
    sb = cold["sect35_band"].to_numpy()
    for dlab in ("d3_le_m50", "d2_m35_m50", "d1_m20_m35", "d0_gt_m20"):
        for slab in ("s0_le20", "s1_20_40", "s2_40_60", "s3_gt60"):
            S[f"S6|S2xS4_{dlab}_x_{slab}"] = (dd == dlab) & (sb == slab)
    return S


def build_s5b_masks(cold: pd.DataFrame) -> "OrderedDict[str, np.ndarray]":
    S: "OrderedDict[str, np.ndarray]" = OrderedDict()
    for col, fam in (("win_band", "S5b_level"), ("traj_band", "S5b_traj")):
        vals = cold[col].to_numpy()
        for lab in sorted({v for v in pd.unique(vals) if v != "na"}):
            S[f"{fam}|{lab}"] = (vals == lab)
    return S


# ── STAGE 3 — cells, intervals, nulls ─────────────────────────────────────────

def _tt(x: np.ndarray):
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size < 2:
        return None, int(x.size)
    se = float(x.std(ddof=1)) / np.sqrt(x.size)
    return (float(x.mean()) / se if se > 0 else None), int(x.size)


def cell(codes: np.ndarray, nd: int, y: np.ndarray, s: np.ndarray) -> dict:
    """One rate cell: state vs the unconditional cold universe of the SAME subset."""
    n_s = np.bincount(codes[s], minlength=nd)
    k_s = np.bincount(codes[s & y], minlength=nd)
    n_a = np.bincount(codes, minlength=nd)
    k_a = np.bincount(codes[y], minlength=nd)
    n_r, k_r = n_a - n_s, k_a - k_s
    N_s, K_s, N_a, K_a = int(n_s.sum()), int(k_s.sum()), int(n_a.sum()), int(k_a.sum())
    N_r, K_r = N_a - N_s, K_a - K_s
    if N_s == 0 or N_a == 0:
        return {"n_state": N_s, "n_universe": N_a, "status": "EMPTY"}
    p_s, p_a = K_s / N_s, K_a / N_a
    p_r = (K_r / N_r) if N_r > 0 else None
    both = (n_s > 0) & (n_r > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        dd = np.where(both, k_s / np.maximum(n_s, 1) - k_r / np.maximum(n_r, 1), np.nan)
    clu_t, n_dates_both = _tt(dd[both])
    iid_t = None
    if p_r is not None and N_r > 0:
        v = p_s * (1 - p_s) / N_s + p_r * (1 - p_r) / N_r
        iid_t = _r((p_s - p_r) / np.sqrt(v), 3) if v > 0 else None
    return {
        "n_state": N_s, "k_state": K_s, "rate_state_pct": _r(100 * p_s, 4),
        "wilson95_pct": wilson(K_s, N_s),
        "n_universe": N_a, "k_universe": K_a, "rate_universe_pct": _r(100 * p_a, 4),
        "rate_rest_pct": _r(100 * p_r, 4) if p_r is not None else None,
        "lift_vs_universe": _r(p_s / p_a, 3) if p_a > 0 else None,
        "iid_t_state_vs_rest": iid_t,
        "date_clustered_t": _r(clu_t, 3), "n_dates_clustered": n_dates_both,
        "n_dates_state": int((n_s > 0).sum()),
        "thin": bool(N_s < THIN_CELL_N),
        "_pd": (n_s, k_s, n_a, k_a),
    }


def null_battery(c: dict, era_codes: np.ndarray, codes: np.ndarray, nd: int,
                 s: np.ndarray, y: np.ndarray, rng) -> dict:
    """Exact permutation nulls (3 arms) + a session bootstrap. sec.6.4 standard."""
    n_s, k_s, n_a, k_a = c["_pd"]
    N_s, K_a, N_a = int(n_s.sum()), int(k_a.sum()), int(n_a.sum())
    p_a = K_a / N_a
    obs_lift = (int(k_s.sum()) / N_s) / p_a if p_a > 0 and N_s else None
    out = {"observed_lift": _r(obs_lift, 3)}

    def _arm(ngood, nbad, nsample):
        ng = np.asarray(ngood, dtype=np.int64)
        nb = np.asarray(nbad, dtype=np.int64)
        ns = np.asarray(nsample, dtype=np.int64)
        keep = ns > 0
        if not keep.any():
            return None
        draws = rng.hypergeometric(ng[keep], nb[keep], ns[keep], size=(N_PERM, int(keep.sum())))
        k_star = draws.sum(axis=1)
        lift_star = (k_star / N_s) / p_a
        p_one = float((lift_star >= obs_lift).mean())
        nm = float(lift_star.mean())
        sd = float(lift_star.std(ddof=1))
        return {"null_mean_lift": _r(nm, 4), "null_sd_lift": _r(sd, 4),
                "p_one_sided_ge_observed": _r(p_one, 4),
                "p_two_sided": _r(float((np.abs(lift_star - 1.0) >=
                                         abs(obs_lift - 1.0)).mean()), 4),
                # The quantity that matters when the null mean is NOT 1: how much of the
                # raw lift the block structure alone already explains, and what is left.
                "lift_relative_to_this_null": _r(obs_lift / nm, 3) if nm > 0 else None,
                "z_vs_null": _r((obs_lift - nm) / sd, 2) if sd > 0 else None,
                "draws": N_PERM}

    out["perm_global"] = _arm([K_a], [N_a - K_a], [N_s])
    ne_a = np.bincount(era_codes, minlength=int(era_codes.max()) + 1)
    ke_a = np.bincount(era_codes[y], minlength=ne_a.size)
    ne_s = np.bincount(era_codes[s], minlength=ne_a.size)
    out["perm_era_preserving"] = _arm(ke_a, ne_a - ke_a, ne_s)
    out["perm_date_preserving"] = _arm(k_a, n_a - k_a, n_s)

    live = np.flatnonzero(n_a > 0)
    idx = rng.integers(0, live.size, size=(N_BOOT, live.size))
    ks, ns_ = k_s[live][idx].sum(1), n_s[live][idx].sum(1)
    ka, na = k_a[live][idx].sum(1), n_a[live][idx].sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        lb = np.where((ns_ > 0) & (na > 0) & (ka > 0), (ks / ns_) / (ka / na), np.nan)
    lb = lb[np.isfinite(lb)]
    out["session_bootstrap"] = {
        "B": N_BOOT, "n_dates_resampled": int(live.size),
        "lift_ci95": [_r(float(np.percentile(lb, 2.5)), 3),
                      _r(float(np.percentile(lb, 97.5)), 3)] if lb.size else None,
        "share_of_draws_lift_le_1": _r(float((lb <= 1.0).mean()), 4) if lb.size else None,
    }
    return out


def volatility_matched(cold, O, state_masks, board, split, oname, sname) -> dict | None:
    """AMENDMENT A2 — the control that decides the interpretation of an affirmative lift.

    A deeply drawn-down name is a MORE VOLATILE name, and a more volatile name prints more
    large moves of every kind.  The date-clustered t already holds the SESSION fixed; this
    holds the name's OWN realised-volatility decile fixed as well, by direct
    standardisation: the expected rate is the non-state rate inside each (date x own-vol
    decile) stratum, re-weighted to the STATE's stratum composition.  A state whose lift is
    volatility is standardised back toward 1; a state carrying board-specific information
    keeps its excess.  This control can only WEAKEN an affirmative claim, never create one.
    """
    smask = state_masks.get(sname)
    if smask is None:
        return None
    y_all, mask_all, _H, _fam = O[oname]
    ii = split_index(cold, board, split)
    ii = ii[mask_all[ii]]
    if ii.size == 0:
        return None
    rv = cold["rv_rank"].to_numpy(np.float64)[ii]
    fin = np.isfinite(rv)
    dec = np.full(rv.size, 10, dtype=np.int64)          # stratum 10 == "vol unmeasurable"
    dec[fin] = np.minimum((np.nan_to_num(rv, nan=0.0)[fin] * 10).astype(np.int64), 9)
    dcodes, duniq = pd.factorize(cold["date"].to_numpy()[ii], sort=True)
    strat = dcodes.astype(np.int64) * 11 + dec
    scodes, _su = pd.factorize(strat, sort=True)
    ns = _su.size if hasattr(_su, "size") else len(_su)
    y, s = y_all[ii], smask[ii]
    n_s = np.bincount(scodes[s], minlength=ns)
    k_s = np.bincount(scodes[s & y], minlength=ns)
    n_a = np.bincount(scodes, minlength=ns)
    k_a = np.bincount(scodes[y], minlength=ns)
    n_r, k_r = n_a - n_s, k_a - k_s
    use = (n_s > 0) & (n_r > 0)
    if not use.any():
        return {"status": "NO_MATCHABLE_STRATUM"}
    W = n_s[use].astype(np.float64)
    obs = float(k_s[use].sum()) / float(W.sum())
    exp = float((W * (k_r[use] / n_r[use])).sum() / W.sum())
    raw_universe = float(k_a.sum()) / float(n_a.sum()) if n_a.sum() else np.nan
    return {
        "board": board, "split": split, "outcome": oname, "state": sname,
        "strata": "date x the name's OWN 20-bar realised-vol decile within its trailing 250",
        "n_state_matched": int(W.sum()),
        "state_rows_dropped_unmatchable": int(n_s.sum() - W.sum()),
        "observed_state_rate_pct": _r(100 * obs, 4),
        "expected_rate_pct_vol_and_date_matched": _r(100 * exp, 4),
        "matched_lift": _r(obs / exp, 3) if exp > 0 else None,
        "unmatched_lift_vs_universe": _r(obs / raw_universe, 3) if raw_universe > 0 else None,
    }


def confluence_transcription_sanity(cold: pd.DataFrame, boards) -> dict:
    """Is the transcribed oracle a WORKING signal on CN names at all?

    This exists because a null on a signal one may have mis-implemented is not a null.  If
    the Golden Oracle's long state carries no forward tilt whatsoever on this universe,
    then S1's first-board null is INSEPARABLE from "their construction does not transfer to
    CN names", and that is a different statement from "momentum confluence does not precede
    a first board".  The distinction is stated rather than quietly collapsed.

    Deliberately a RATE, not an expectancy: P(10-session cumulative return > 0 | state)
    against the same probability off-state.  Nothing here is a return anyone could earn and
    no book is implied — it is a diagnostic on the transcription.
    """
    out = {"why": (
        "A null on a possibly mis-transcribed signal is not a null. This measures whether "
        "the transcribed oracle has ANY forward tilt on CN names, so the S1 first-board "
        "null can be read as 'this construction does not select first boards' rather than "
        "silently meaning 'the transcription is broken' or 'the oracle does not transfer'."),
        "measure": "P(10-session cumulative return > 0) on-state vs off-state, fit window",
        "not_an_expectancy": ("a directional RATE, not a return; no book, no fills, no "
                              "expectancy is implied or quoted"),
        "rows": []}
    cum = cold["cum_10"].to_numpy(np.float64)
    ok = cold["win_ok_10"].to_numpy(bool) & np.isfinite(cum)
    up = cum > 0
    for board in boards:
        ii = split_index(cold, board, "fit")
        ii = ii[ok[ii]]
        if ii.size == 0:
            continue
        for sname in ("S1|s1_3d_long", "S1|s1_3d_cb_recent", "S1|s1_2d_rising",
                      "S1|s1_dot_recent"):
            s = state_mask_or_none(cold, sname)
            if s is None:
                continue
            sv, uv = s[ii], up[ii]
            n_s = int(sv.sum())
            n_r = int((~sv).sum())
            if n_s == 0 or n_r == 0:
                continue
            p_s = float(uv[sv].mean())
            p_r = float(uv[~sv].mean())
            out["rows"].append({
                "board": board, "state": sname, "n_state": n_s,
                "state_share_pct": _r(100.0 * n_s / (n_s + n_r), 2),
                "p_up_on_state_pct": _r(100 * p_s, 3),
                "p_up_off_state_pct": _r(100 * p_r, 3),
                "edge_pp": _r(100 * (p_s - p_r), 3),
            })
    edges = [r["edge_pp"] for r in out["rows"] if r["edge_pp"] is not None]
    out["max_abs_edge_pp"] = _r(max((abs(e) for e in edges), default=0.0), 3)
    return out


_STATE_CACHE: dict = {}


def state_mask_or_none(cold, sname):
    key = id(cold)
    if _STATE_CACHE.get("key") != key:
        _STATE_CACHE.clear()
        _STATE_CACHE["key"] = key
        _STATE_CACHE["masks"] = build_state_masks(cold)
    return _STATE_CACHE["masks"].get(sname)


def outcome_defs(cold: pd.DataFrame) -> "OrderedDict[str, tuple]":
    """(name -> (y, mask, H, family)) for every pre-registered outcome class."""
    w = cold["w"].to_numpy(np.float64)
    O: "OrderedDict[str, tuple]" = OrderedDict()
    for H in HORIZONS:
        ok = cold[f"win_ok_{H}"].to_numpy(bool)
        O[f"first_board_H{H}"] = (cold[f"fb_{H}"].to_numpy(bool), ok, H, "first_board")
        cum = cold[f"cum_{H}"].to_numpy(np.float64)
        peak = cold[f"peak_{H}"].to_numpy(np.float64)
        for mult in WINDOW_MULTS:
            tag = str(mult).replace(".", "p")
            O[f"cum_{tag}w_H{H}"] = (cum >= mult * w, ok & np.isfinite(cum), H, "window_cum")
            O[f"peak_{tag}w_H{H}"] = (peak >= mult * w, ok & np.isfinite(peak), H,
                                      "window_peak_FORESIGHT_UPPER_BOUND")
    return O


def split_index(cold: pd.DataFrame, board: str, split: str) -> np.ndarray:
    sp = cold["split"].to_numpy()
    bk = cold["board_key"].to_numpy()
    sel = (bk == board) & (np.isin(sp, FIT_SPLITS) if split == "fit" else (sp == split))
    return np.flatnonzero(sel)


def build_tables(cold, state_masks, O, boards, splits_to_report, era: bool = False,
                 outcome_filter=None) -> list[dict]:
    dates = cold["date"].to_numpy()
    eras = cold["era"].astype(str).to_numpy()
    rows = []
    for board in boards:
        for split in splits_to_report:
            base_ii = split_index(cold, board, split)
            if base_ii.size == 0:
                continue
            era_groups = ([("all", base_ii)] if not era else
                          [(e, base_ii[eras[base_ii] == e])
                           for e in sorted(set(eras[base_ii]))])
            for era_name, ii0 in era_groups:
                if ii0.size == 0:
                    continue
                for oname, (y_all, mask_all, H, fam) in O.items():
                    if outcome_filter and oname not in outcome_filter:
                        continue
                    ii = ii0[mask_all[ii0]]
                    if ii.size == 0:
                        continue
                    codes, uniq = pd.factorize(dates[ii], sort=True)
                    nd = uniq.size
                    y = y_all[ii]
                    n_a = np.bincount(codes, minlength=nd)
                    k_a = np.bincount(codes[y], minlength=nd)
                    N_a, K_a = int(n_a.sum()), int(k_a.sum())
                    for sname, smask in state_masks.items():
                        s = smask[ii]
                        N_s = int(s.sum())
                        if N_s == 0:
                            continue
                        c = cell(codes, nd, y, s)
                        c.pop("_pd", None)
                        c.update({"board": board, "split": split, "era": era_name,
                                  "outcome": oname, "outcome_family": fam, "H": H,
                                  "state": sname, "state_family": sname.split("|")[0]})
                        rows.append(c)
                    _ = (N_a, K_a)
    return rows


def topk_precision(codes, nd, y, f, K, desc: bool) -> dict:
    keep = np.isfinite(f)
    if not keep.any():
        return {"status": "NO_FINITE_FEATURE"}
    c2, y2, f2 = codes[keep], y[keep], f[keep]
    key = -f2 if desc else f2
    order = np.lexsort((key, c2))
    cs = c2[order]
    counts = np.bincount(cs, minlength=nd)
    starts = np.r_[0, np.cumsum(counts)[:-1]]
    rank = np.arange(cs.size) - starts[cs]
    top = rank < K
    eligible = counts >= K
    sel = top & eligible[cs]
    if not sel.any():
        return {"status": "NO_ELIGIBLE_DATE"}
    ys = y2[order]
    n_top = np.bincount(cs[sel], minlength=nd)
    k_top = np.bincount(cs[sel][ys[sel]], minlength=nd)
    n_all = np.bincount(cs, minlength=nd)
    k_all = np.bincount(cs[ys], minlength=nd)
    d = np.flatnonzero(eligible & (n_top > 0))
    prec = k_top[d] / n_top[d]
    base = k_all[d] / n_all[d]
    t, ndates = _tt(prec - base)
    return {
        "K": K, "direction": "desc" if desc else "asc",
        "n_dates_eligible": int(d.size),
        "day_weighted_precision_pct": _r(100.0 * float(prec.mean()), 4),
        "day_weighted_random_within_state_pct": _r(100.0 * float(base.mean()), 4),
        "precision_lift": _r(float(prec.mean() / base.mean()), 3) if base.mean() > 0 else None,
        "date_clustered_t_vs_random": _r(t, 3), "n_dates_clustered": ndates,
        "rows_dropped_nan_feature": int((~keep).sum()),
        "positives_in_state": int(y2.sum()),
    }


def ranking_arm(cold, state_masks, tables, boards) -> dict:
    """Q3 — the Prophet-shaped ranking preview, on PRE-REGISTERED state selection."""
    dates = cold["date"].to_numpy()
    O = outcome_defs(cold)
    out = {"selection_rule": (
        "States are NOT shopped. Arm (i) is the product's own position state "
        "s1_3d_long. Arm (ii) is the S6 conjunction with the highest FIT-window "
        "first_board_H10 lift for that board, chosen on FIT ONLY (n >= THIN and "
        f">= {MIN_FIT_CORE_POS} fit positives required) and then applied to the holdout "
        "untouched. Both rank directions are printed for every feature; choosing the "
        "winning direction post hoc is forbidden and the multiplicity is counted."),
        "arms": []}
    fit_rows = [r for r in tables if r["split"] == "fit" and r["era"] == "all"
                and r["outcome"] == "first_board_H10"]
    for board in boards:
        cand = [r for r in fit_rows
                if r["board"] == board and r["state_family"] == "S6"
                and not r.get("thin", True) and r.get("k_state", 0) >= MIN_FIT_CORE_POS
                and r.get("lift_vs_universe") is not None]
        best = max(cand, key=lambda r: r["lift_vs_universe"]) if cand else None
        chosen = [("product_state", "S1|s1_3d_long")]
        if best:
            chosen.append(("best_fit_conjunction", best["state"]))
        for arm_label, sname in chosen:
            if sname not in state_masks:
                continue
            smask = state_masks[sname]
            entry = {"board": board, "arm": arm_label, "state": sname,
                     "fit_selection_lift": _r(best["lift_vs_universe"], 3)
                     if best and arm_label == "best_fit_conjunction" else None,
                     "cells": []}
            for split in ("fit", "test"):
                ii0 = split_index(cold, board, split)
                if ii0.size == 0:
                    continue
                for oname in ("first_board_H10", "first_board_H20"):
                    y_all, mask_all, H, _fam = O[oname]
                    ii = ii0[mask_all[ii0] & smask[ii0]]
                    if ii.size == 0:
                        continue
                    codes, uniq = pd.factorize(dates[ii], sort=True)
                    nd, y = uniq.size, y_all[ii]
                    npos = int(y.sum())
                    thin = npos < MIN_FIT_CORE_POS
                    for feat in RANK_FEATURES:
                        f = cold[feat].to_numpy(np.float64)[ii]
                        for K in TOP_K:
                            for desc in (True, False):
                                r = topk_precision(codes, nd, y, f, K, desc)
                                if r.get("status"):
                                    continue
                                r.update({"split": split, "outcome": oname,
                                          "feature": feat, "n_state_rows": int(ii.size),
                                          "positives": npos,
                                          "thin_below_fit_core_floor": bool(thin)})
                                entry["cells"].append(r)
            out["arms"].append(entry)
    return out


# ── STAGE 4 — verify battery (S7 law: every predicate keyed to a series that CAN move) ──

def verify_battery(cold: pd.DataFrame, panel_meta: dict, rng) -> dict:
    checks = []

    def add(name, passed, detail, mutation):
        checks.append({"check": name, "pass": bool(passed), "detail": detail,
                       "mutation_probe": mutation})

    # 1. RMA parity against a literal transcription of the Terminal's own loop.
    worst = 0.0
    for tk in ("000001.SZ", "300363.SZ", "600519.SS"):
        p = RAW_DIR / f"{tk}.parquet"
        if not p.exists():
            continue
        c = pd.read_parquet(p)["close"].to_numpy(np.float64)
        d = np.diff(c, prepend=np.nan)
        for a in (np.where(np.isfinite(d), np.clip(d, 0, None), np.nan),
                  np.where(np.isfinite(d), -np.clip(d, None, 0), np.nan)):
            worst = max(worst, float(np.nanmax(np.abs(_rma(a, RSI_LEN) -
                                                      _rma_reference(a, RSI_LEN)))))
    probe = np.r_[np.nan, rng.normal(size=400) ** 2]
    mutated = _rma(probe, RSI_LEN).copy()
    mutated[200] += 1e-3
    add("terminal_rma_parity", worst < 1e-9,
        {"max_abs_diff_vs_their_loop": worst,
         "why": "the vectorised Wilder RMA must equal their SMA-seeded recursion exactly"},
        {"perturbed_one_element_by_1e-3": True,
         "check_would_fail": bool(float(np.nanmax(np.abs(
             mutated - _rma_reference(probe, RSI_LEN)))) > 1e-9)})

    # 2. Cold universe implies a LADDER-ZERO first board (the sec.5 lemma, asserted).
    bad = tested = 0
    sample = sorted(RAW_DIR.glob("*.parquet"))[::97][:20]
    for p in sample:
        board = _board_from_ticker(p.stem)
        try:
            df = pd.read_parquet(p).sort_index()
        except Exception:  # noqa: BLE001
            continue
        out, _ = process_ticker(p.stem, df, board)
        if out is None:
            continue
        lu = out["lu"].to_numpy(bool)
        prior = pd.Series(lu.astype(float)).shift(1).rolling(
            COLD_LOOKBACK_K, min_periods=1).sum().to_numpy()
        coldm = out["cold"].to_numpy(bool)
        okm = out["win_ok_20"].to_numpy(bool)
        fb = out["fb_20"].to_numpy(bool)
        pos = np.flatnonzero(coldm & okm & fb)
        lu_pos = np.flatnonzero(lu)
        for i in pos:
            j = lu_pos[np.searchsorted(lu_pos, i, side="right")]
            tested += 1
            if prior[j] and prior[j] > 0:
                bad += 1
    add("cold_universe_implies_ladder_zero", bad == 0,
        {"first_boards_checked": tested, "violations": bad, "K": COLD_LOOKBACK_K,
         "H": 20, "tickers_sampled": len(sample),
         "why": "a state measured on a cold bar must predict an IGNITION, not a re-board"},
        {"if_K_were_shortened_below_H": "the lemma's union argument breaks and this check "
                                        "reports violations — it is keyed to the realised "
                                        "ladder count at every first board, a series that "
                                        "moves whenever the cold rule changes",
         "series_can_move": bool(tested > 0)})

    # 3. No-lookahead: corrupting the FUTURE must not move any state at/before the cut;
    #    corrupting the PAST must move them (the probe that proves the check can fail).
    p = RAW_DIR / "000001.SZ.parquet"
    fut_max = past_max = None
    if p.exists():
        df = pd.read_parquet(p).sort_index()
        cut = pd.Timestamp("2019-01-02")
        base, _ = process_ticker("000001.SZ", df, "main")
        d2 = df.copy()
        d2.loc[d2.index > cut, ["open", "high", "low", "close"]] *= 1.35
        fut, _ = process_ticker("000001.SZ", d2, "main")
        d3 = df.copy()
        d3.loc[d3.index <= cut, ["open", "high", "low", "close"]] *= 1.35
        pas, _ = process_ticker("000001.SZ", d3, "main")
        cols = ["s1_3d_cb", "s1_3d_long", "s1_2d_rising", "s1_dot", "dd250", "under_ma"]
        pre = base["date"] <= cut
        fut_max = int(sum(int((base.loc[pre, c].to_numpy() !=
                               fut.loc[pre, c].to_numpy()).sum()) for c in cols))
        past_max = int(sum(int((base.loc[pre, c].to_numpy() !=
                                pas.loc[pre, c].to_numpy()).sum()) for c in cols))
    add("no_lookahead_state_construction", fut_max == 0,
        {"pre_cut_rows_changed_by_future_corruption": fut_max,
         "cut": "2019-01-02", "prices_scaled_by": 1.35,
         "why": "every confluence and washout state must be computable at T's close"},
        {"pre_cut_rows_changed_by_PAST_corruption": past_max,
         "check_can_see_a_failure": bool(past_max and past_max > 0)})

    # 4. The closure-tolerant chain actually recovers rows the 10-day rule discarded.
    rec = {}
    for H in HORIZONS:
        a = int(cold[f"win_ok_{H}"].sum())
        b = int((cold[f"win_ok_{H}"] & cold[f"win_ok_legacy_{H}"]).sum())
        rec[f"H{H}"] = {"windows_scored_21d_rule": a, "also_scored_10d_rule": b,
                        "recovered_rows": a - b,
                        "recovered_pct_of_scored": _r(100.0 * (a - b) / max(a, 1), 3)}
    add("closure_tolerant_chain_recovers_rows",
        all(v["recovered_rows"] >= 0 for v in rec.values()), rec,
        {"direction_is_forced": "the 21-day rule is a superset of the 10-day rule, so "
                                "recovered_rows < 0 is impossible unless the chain is "
                                "miswired — that is exactly the failure this detects",
         "series_can_move": bool(any(v["recovered_rows"] > 0 for v in rec.values()))})

    # 5. Outcome completeness parity — no first board is scored on an incomplete window.
    viol = int(sum(int((cold[f"fb_{H}"] & ~cold[f"win_ok_{H}"]).sum()) for H in HORIZONS))
    add("outcome_requires_complete_window", viol == 0,
        {"rows_with_outcome_but_no_window": viol},
        {"series_can_move": True,
         "why_it_can_fail": "fb_H and win_ok_H are computed from different arrays "
                            "(dist_next_lu vs run_fwd); a sign error in either shows here"})

    # 6. Embargo — no retained conditioning date sits inside a split's final H sessions.
    #    S7: the session universe MUST come from the UNFILTERED panel. Reading it off
    #    `cold` (already split-filtered) made this predicate structurally unable to fail —
    #    the defect this check exists to catch. Caught by its own mutation probe on the
    #    first run and fixed; recorded in the receipt's AMENDMENTS.
    all_sessions = np.asarray(panel_meta["_all_sessions"])
    sp = cold[["date", "split"]].dropna().drop_duplicates()
    gaps = {}
    for name, (lo, hi) in SPLITS.items():
        kept = sp.loc[sp["split"] == name, "date"]
        if kept.empty:
            continue
        inrange = all_sessions[(all_sessions >= lo.to_datetime64())
                               & (all_sessions <= hi.to_datetime64())]
        gaps[name] = {"sessions_in_range": int(inrange.size),
                      "sessions_after_last_kept": int((inrange > kept.max()).sum())}
    add("split_embargo_covers_max_horizon",
        all(v["sessions_after_last_kept"] >= EMBARGO_SESSIONS for v in gaps.values()),
        {"per_split": gaps, "embargo_sessions": EMBARGO_SESSIONS,
         "mandated_floor": PURGE_SESSIONS_MANDATED, "max_horizon": max(HORIZONS)},
        {"series_can_move": True,
         "why_it_can_fail": "shrinking EMBARGO_SESSIONS below max(H) makes this report a "
                            "shortfall for every split",
         "defect_this_check_already_caught": (
             "On the first run this predicate read its session universe off `cold`, which "
             "is ALREADY split-filtered, so sessions_after_last_kept was 0 by construction "
             "for every split and the check could not fail. It reported FALSE (0 < 20) "
             "rather than a false PASS, which is how the defect surfaced. The universe now "
             "comes from the unfiltered panel — an S7-class fix, recorded not hidden.")})

    # 7. Transcription non-degeneracy: the oracle's states must be neither empty nor
    #    always-on, and CB must actually fire. A degenerate transcription would produce a
    #    lift of exactly 1.0 and be misread as a signal null.
    deg = []
    for c in ("s1_3d_cb", "s1_3d_cb_recent", "s1_3d_long", "s1_2d_rising", "s1_dot"):
        sh = float(cold[c].mean())
        deg.append({"state": c, "share_pct": _r(100 * sh, 3),
                    "degenerate": bool(sh <= 0.001 or sh >= 0.999)})
    add("confluence_transcription_non_degenerate",
        all(not x["degenerate"] for x in deg),
        {"shares": deg, "warm_share_pct": _r(100 * float(cold["s1_warm"].mean()), 3),
         "why": ("an empty or always-on state produces a lift of exactly 1.0 and would be "
                 "misread as a SIGNAL null when it is a TRANSCRIPTION defect")},
        {"series_can_move": True,
         "why_it_can_fail": ("breaking the 3D grouping, the warm-up gate or the weekly "
                             "join collapses these shares to 0 or 1 and this fires")})

    # 8. S7 — the conditioned rate series must be capable of MOVING across states.
    v = cold.groupby("dd_band", observed=True)["fb_10"].mean()
    spread = float(v.max() - v.min()) if len(v) > 1 else 0.0
    add("conditioned_rate_series_can_move", spread > 0,
        {"dd_band_first_board_H10_rate_spread_pct": _r(100 * spread, 4),
         "bands": {str(k): _r(100 * float(x), 4) for k, x in v.items()},
         "why": "a verify predicate keyed to a constant series cannot fail; this proves "
                "the conditioning axis is live before any lift is read off it"},
        {"series_can_move": bool(spread > 0)})

    return {"checks": checks,
            "all_pass": all(c["pass"] for c in checks),
            "s7_note": ("Every check above records a MUTATION PROBE — the same predicate "
                        "re-evaluated on a deliberately corrupted input, or the structural "
                        "reason the underlying series can move. A check that cannot fail "
                        "is a defect, not a pass."),
            "panel_rows": int(panel_meta.get("live_bars", 0))}


# ── STAGE 5 — nulls on the affirmative set, sensitivity, ore ──────────────────

NULL_TRIGGER_LIFT = 1.25
NULL_MAX_CELLS = 60
NULL_MIN_CELLS = 10


def null_for_row(cold, O, state_masks, row, rng) -> dict | None:
    smask = state_masks.get(row["state"])
    if smask is None:
        return None
    y_all, mask_all, _H, _fam = O[row["outcome"]]
    ii0 = split_index(cold, row["board"], row["split"])
    if row["era"] != "all":
        ii0 = ii0[cold["era"].astype(str).to_numpy()[ii0] == row["era"]]
    ii = ii0[mask_all[ii0]]
    if ii.size == 0:
        return None
    codes, uniq = pd.factorize(cold["date"].to_numpy()[ii], sort=True)
    ecodes, _eu = pd.factorize(cold["era"].astype(str).to_numpy()[ii], sort=True)
    y, s = y_all[ii], smask[ii]
    c = cell(codes, uniq.size, y, s)
    if c.get("status") == "EMPTY":
        return None
    nb = null_battery(c, ecodes, codes, uniq.size, s, y, rng)
    nb.update({k: row[k] for k in ("board", "split", "era", "outcome", "state", "H")})
    nb["n_state"] = c["n_state"]
    nb["rate_state_pct"] = c["rate_state_pct"]
    nb["rate_universe_pct"] = c["rate_universe_pct"]
    nb["date_clustered_t"] = c["date_clustered_t"]
    return nb


HEADLINE_STATES = ("S2depth|d3_le_m50", "S2depth|d2_m35_m50", "S4|s3_gt60",
                   "S6|S2xS4_d3_le_m50_x_s3_gt60", "S6|S2xS4_d2_m35_m50_x_s3_gt60",
                   "S6|S1xS2_long_x_d3_le_m50", "S5a_volz|v3_gt2", "S5a|base_x_v3_gt2",
                   "S1|s1_3d_long", "S1|s1_3d_cb_recent", "S3|b4_gt120")


def select_affirmative(tables, boards) -> list[dict]:
    """The null set is STRATIFIED so the receipt cannot quote a cell it did not null.

    A flat top-N-by-lift selection lets one board's window-class cells crowd out every
    first-board cell — which is exactly what happened on the first pass and would have left
    the headline first-board magnitudes unpriced. Selection is therefore per
    (board x outcome family), and every state named in HEADLINE_STATES is force-included at
    the first-board horizons for every board, whatever its lift. A cell being SELECTED says
    nothing about it being affirmative; it says the receipt is allowed to quote it.
    """
    hold = [r for r in tables if r["split"] == HOLDOUT_SPLIT and r["era"] == "all"
            and not r.get("thin", True) and r.get("lift_vs_universe") is not None]
    sel, keys = [], set()

    def _take(r):
        k = (r["board"], r["outcome"], r["state"])
        if k not in keys:
            keys.add(k)
            sel.append(r)

    for r in hold:
        if r["state"] in HEADLINE_STATES and r["outcome"].startswith("first_board"):
            _take(r)
    per_stratum = max(NULL_MIN_CELLS, NULL_MAX_CELLS // max(len(boards), 1) // 2)
    for board in boards:
        for fam in ("first_board", "window_cum", "window_peak_FORESIGHT_UPPER_BOUND"):
            g = [r for r in hold if r["board"] == board and r["outcome_family"] == fam]
            g.sort(key=lambda r: -r["lift_vs_universe"])
            for r in g[:per_stratum]:
                _take(r)
    twins = [r for r in tables if r["split"] == "fit" and r["era"] == "all"
             and (r["board"], r["outcome"], r["state"]) in keys]
    return sel + twins


ORE_LEDGER = [
    {"ore": "PRICE-LEVEL / TICK-GRANULARITY interaction with the tolerant limit rule "
            "(the named artifact risk for THIS receipt's own headline)",
     "why": ("The headline state is DEEP DRAWDOWN, which is also a LOW PRICE state, and "
             "the PRIMARY event definition rounds the limit price to 0.01 and then allows "
             "a 0.2% cushion. At a 2.00 price the 0.01 tick is 0.5% of price — larger than "
             "the cushion — so the tolerant rule's effective width is not constant across "
             "the price range, and the store is BACK-ADJUSTED so its printed price is not "
             "the traded price at all. This cannot be settled on this basis. It is settled "
             "by the exact-cent plane (reconciliation sec.5's integer-cent taxonomy + "
             "stk_limit joins), where the limit is a legal price rather than a rounded "
             "one. Until then the washout headline carries this as a NAMED, UNQUANTIFIED "
             "artifact risk — not a caveat in general, this specific one."),
     "cost": "blocked on the exact-cent plane; re-run is free once it lands"},
    {"ore": "a PIT market-cap / price-level stratified arm",
     "why": ("The volatility-matched control holds date and own-vol decile fixed but NOT "
             "size, price level or liquidity. Deep-drawdown names skew small and cheap "
             "within this large-cap slice, and the artifact above rides the same axis. "
             "PIT cap by board (never current cap) is the honest stratifier and it is not "
             "built here."),
     "cost": "one lane, blocked on a PIT cap store"},
    {"ore": "the session-phased 2D bar (their own research fix)",
     "why": ("Production's 2D legs use calendar resample('2B'), which mis-splits real "
             "sessions around every CN holiday — the exact defect class their 3D docstring "
             "calls WRONG. charting-app/research/master_indicator_fusion_lab.py already "
             "prototypes the IPO-phased session_bars() fix but it is NOT wired into "
             "signal_layer/. Re-running S1's 2D arms on the corrected phase is a pure "
             "re-run and may move every 2D number here."),
     "cost": "one lane, no new code in the Terminal repo"},
    {"ore": "confluence parameter relaxations",
     "why": ("Every parameter is the Terminal's live configuration (RSI 14, MACD 14/60/5, "
             "StochRSI 14/14/3/3, OB/OS 80/20, CONF_W 8, BUY_RSI_MAX 65). None of the "
             "neighbourhood was scanned. A state that is null at their settings can be "
             "alive one parameter over, and a state alive ONLY at their settings is a "
             "fragility finding — neither is decidable from this file."),
     "cost": "one lane, same instrument"},
    {"ore": "other momentum families entirely",
     "why": ("Only the Golden Oracle was tested. The Terminal also ships Trend Waves and "
             "Pulse families (named in their research harness); classical MACD on price, "
             "ADX, Bollinger squeeze, Donchian and volume-profile bases are all untouched."),
     "cost": "one lane per family"},
    {"ore": "the v2 filters omitted from the position state",
     "why": ("bear_block (2W-derived) and strong_bull were left out of s1_3d_long. Their "
             "own docstring says 2W only feeds the fixed=True backtest, but the GC v2 "
             "traded stream does carry them and the state population would shrink."),
     "cost": "trivial, once the 2W parity is transcribed"},
    {"ore": "other timeframes for the confluence",
     "why": "Only 2D and 3D were charted. 1D, 5D, weekly and the monthly investor-cycle "
            "RSI-MACD gate their code also computes are untested as onset conditioners.",
     "cost": "one lane"},
    {"ore": "washout depth measured against other rulers",
     "why": ("dd250 uses a 250-session rolling HIGH of the daily high. Distance from an "
             "all-time high, from a 500-session high, from a sector-relative high, and "
             "drawdown measured on closes rather than highs are all untested; so are "
             "non-uniform band edges and a continuous (unbanded) treatment."),
     "cost": "small"},
    {"ore": "under-MA variants",
     "why": ("Only the 200-session SMA and the sessions-below streak were charted. The "
             "50/100/250 MAs, EMA versions, MA slope, price-to-MA DISTANCE (rather than "
             "the binary side), and MA stacking order are untested."),
     "cost": "small"},
    {"ore": "sector breadth beyond the -35%/-20% share",
     "why": ("S4 is a member-share of a fixed depth cut on CURRENT membership. Median "
             "sector drawdown, sector breadth MOMENTUM (share improving), THS 题材 "
             "concept membership rather than the coarse sector map, and index-relative "
             "breadth are all untested — and the current-membership caveat can only be "
             "retired by a point-in-time membership store that does not exist here."),
     "cost": "one lane; blocked on PIT membership for the caveat"},
    {"ore": "accumulation footprints beyond vol-z in a low-vol base",
     "why": ("S5a is one construction. Volume DRY-UP (falling vol-z through the base), "
             "up-day/down-day volume asymmetry, range compression (NR7/inside-bar "
             "clusters), the count of quiet sessions, and OBV-style accumulation lines "
             "are untested. v0's f2 turnover ratio remains impossible: no CN store here "
             "carries shares outstanding per date."),
     "cost": "one lane"},
    {"ore": "chip-distribution deepening (the operator's named instrument)",
     "why": ("S5b uses cyq_perf `winner` only, and its history starts 2025-05-26 — after "
             "train AND calibration, so it has NO out-of-sample arm in this split at all. "
             "The 筹码分布 concentration measures the operator actually named (cyq_chips "
             "percentile spread, concentration ratio, the shift of the main chip peak "
             "toward the current price) need a cyq_chips HISTORY that does not exist in "
             "this checkout. Nothing about the accumulation mechanism is decided until "
             "that store accrues."),
     "cost": "blocked on the accruing store; re-run is free once it lands"},
    {"ore": "LHB (龙虎榜) and news conditioning",
     "why": ("The mechanism hypothesis is news-release-after-accumulation, and NOTHING in "
             "this file observes news, announcements, 特停/inquiry letters, 减持 filings, "
             "or LHB seat composition. The blinded brainstorm's LHB-absence-as-signal and "
             "the regulatory metagame are both untested against first-board onset."),
     "cost": "collector-dependent"},
    {"ore": "theme-relay and cross-band telemetry states",
     "why": ("C6 theme relay with degrading follower quality, C15's ChiNext-20% names as "
             "shadow-price oracles for main-board siblings, and leader-death contagion "
             "are all ONSET-side constructions this lane did not chart."),
     "cost": "one lane; theme relay blocked on THS concept mapping"},
    {"ore": "the outcome class itself",
     "why": ("First board and the two window thresholds at H in {5,10,20} are four "
             "target shapes. Time-to-first-board as a survival target, the 20% board on "
             "ChiNext/STAR as a distinct class, multi-board runs from a cold start, and "
             "the soft-label cum/w regression are untested."),
     "cost": "one lane"},
    {"ore": "the cold-window length K",
     "why": ("K = 20 defines 'cold'. K = 5, 60 and 120 define different populations — a "
             "name 6 sessions after a board is a different object from one 6 months after "
             "— and the sensitivity of every lift here to K is unmeasured."),
     "cost": "trivial re-run"},
    {"ore": "per-name and size/liquidity effects",
     "why": ("Every cell pools names inside a board key. Whether any lift is a property of "
             "a handful of repeat names, or of a size/liquidity stratum, is unmeasured — "
             "and PIT market cap by board (never current cap) is the honest stratifier."),
     "cost": "one lane"},
    {"ore": "full-universe re-run (F3)",
     "why": ("Survivors-only, 35.37% of active SH/SZ, 0 BSE. The reconciliation ledger "
             "makes the full-A exact-cent re-measurement THE gate to anything beyond "
             "display tier. Every number here inherits that bound."),
     "cost": "re-run, no new code"},
    {"ore": "suspension-aware confluence input",
     "why": ("The transcription is close-only and volume-blind exactly as production is, "
             "so zero-volume stale-price 停牌 placeholders enter the 3D session grouping. "
             "A suspension-aware feed would re-phase every 3D bar after a long halt."),
     "cost": "small"},
    {"ore": "an entry book on any surviving state",
     "why": ("This lane deliberately quotes NO expectancy. W3-C's law stands: every paper "
             "cell must be re-priced open-anchored before it means anything, and the "
             "auction has removed the fills in every family measured so far."),
     "cost": "one lane, W3-C's machinery already exists"},
]


def build_md(payload: dict) -> str:
    """Receipt prose is written by hand in the .md; this emits the machine-checkable core."""
    return json.dumps({"see": str(OUT_JSON.name)}, indent=2)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    rng = np.random.default_rng(SEED)
    print("[1/8] building panel from china_stocks_raw ...", flush=True)
    panel, pmeta = build_panel()
    print(f"      live bars={pmeta['live_bars']:,}  tolerant boards="
          f"{pmeta['tolerant_limit_up_closes']:,}  cold bars={pmeta['cold_bars']:,}",
          flush=True)

    print("[2/8] attaching panel-level conditioners ...", flush=True)
    chips, chips_meta = load_chips()
    panel, cmeta = attach_conditioners(panel, chips)
    pmeta["_all_sessions"] = np.array(sorted(pd.unique(panel["date"])))
    cold = panel[panel["cold"].to_numpy() & panel["split"].notna().to_numpy()].reset_index(
        drop=True)
    print(f"      cold+split rows={len(cold):,}", flush=True)

    print("[3/8] building state masks and outcome classes ...", flush=True)
    states = build_state_masks(cold)
    s5b = build_s5b_masks(cold)
    O = outcome_defs(cold)
    boards = [b for b in ("main", "chinext10", "chinext20", "star")
              if (cold["board_key"] == b).any()]
    print(f"      states={len(states)} (+{len(s5b)} S5b)  outcomes={len(O)}  "
          f"boards={boards}", flush=True)

    print("[4/8] Q1/Q2 rate tables (board x split x state x H x outcome) ...", flush=True)
    tables = build_tables(cold, states, O, boards, ("fit", "test", "audit"))
    print(f"      cells={len(tables):,}", flush=True)

    print("[5/8] era tables + S5b coverage-bounded block ...", flush=True)
    era_focus = {"first_board_H10", "peak_1p5w_H10"}
    era_tables = build_tables(cold, states, O, boards, ("fit", "test"), era=True,
                              outcome_filter=era_focus)
    s5b_tables = build_tables(cold, s5b, O, boards, ("test", "audit"),
                              outcome_filter={"first_board_H10", "first_board_H20",
                                              "peak_1p5w_H10"})
    print(f"      era cells={len(era_tables):,}  S5b cells={len(s5b_tables):,}", flush=True)

    print("[6/8] Q3 ranking arm ...", flush=True)
    ranking = ranking_arm(cold, states, tables, boards)
    print(f"      arms={len(ranking['arms'])}", flush=True)

    print("[7/8] nulls on the affirmative set + verify battery ...", flush=True)
    affirm = select_affirmative(tables, boards)
    nulls = []
    for row in affirm:
        nb = null_for_row(cold, O, states, row, rng)
        if nb:
            nulls.append(nb)
    verify = verify_battery(cold, pmeta, rng)
    print(f"      null cells={len(nulls)}  verify all_pass={verify['all_pass']}", flush=True)

    # AMENDMENT A2 — the volatility-matched control on every headline state.
    head_states = list(HEADLINE_STATES)
    vm = []
    for board in boards:
        for split in ("fit", "test"):
            for oname in ("first_board_H10", "first_board_H20", "peak_1p5w_H10",
                          "cum_1p5w_H10"):
                for sname in head_states:
                    r = volatility_matched(cold, O, states, board, split, oname, sname)
                    if r and not r.get("status"):
                        vm.append(r)
    print(f"      volatility-matched cells={len(vm)}", flush=True)
    sanity = confluence_transcription_sanity(cold, boards)
    print(f"      confluence sanity max|edge| = "
          f"{sanity['max_abs_edge_pp']} pp", flush=True)

    # embargo sensitivity — the mandated-10 arm beside the disclosed max(H) arm
    cold10 = panel[panel["cold"].to_numpy() &
                   panel["split_mandated10"].notna().to_numpy()].copy()
    cold10["split"] = cold10["split_mandated10"]
    cold10 = cold10.reset_index(drop=True)
    st10 = build_state_masks(cold10)
    t10 = build_tables(cold10, st10, outcome_defs(cold10), boards, (HOLDOUT_SPLIT,),
                       outcome_filter={"first_board_H10"})
    m20 = {(r["board"], r["state"]): r["lift_vs_universe"] for r in tables
           if r["split"] == HOLDOUT_SPLIT and r["era"] == "all"
           and r["outcome"] == "first_board_H10"}
    diffs = [abs(r["lift_vs_universe"] - m20[(r["board"], r["state"])])
             for r in t10 if (r["board"], r["state"]) in m20
             and r["lift_vs_universe"] is not None
             and m20[(r["board"], r["state"])] is not None]
    embargo_sens = {
        "arm_a_disclosed_embargo_sessions": EMBARGO_SESSIONS,
        "arm_b_ledger_mandated_purge_sessions": PURGE_SESSIONS_MANDATED,
        "cells_compared": len(diffs),
        "max_abs_lift_difference": _r(max(diffs), 4) if diffs else None,
        "median_abs_lift_difference": _r(float(np.median(diffs)), 4) if diffs else None,
        "reading": ("The mandated 10-session purge cannot cover an H=20 outcome window, "
                    "so the headline uses max(10, max H) = 20. This arm prints what the "
                    "mandated purge alone would have produced on the holdout first-board "
                    "table so the extension is auditable rather than asserted."),
    }

    print("[8/8] writing ...", flush=True)
    pmeta.pop("_all_sessions", None)
    multiplicity = {
        "q1_q2_cells": len(tables), "era_cells": len(era_tables),
        "s5b_cells": len(s5b_tables),
        "ranking_cells": sum(len(a["cells"]) for a in ranking["arms"]),
        "null_cells": len(nulls),
        "states_charted": len(states), "outcomes_charted": len(O),
        "rank_directions_printed": 2,
        "note": ("Nothing is corrected away; the COUNT is the disclosure. Both rank "
                 "directions are printed for every feature precisely so that a "
                 "post-hoc direction choice is visible as multiplicity rather than "
                 "hidden as a result. Read any single cell against these counts."),
    }
    payload = {
        "instrument": "washout_onset_w1",
        "wave": "CN LIMIT-MOVE ALPHA — W-P0: washout/confluence-conditional FIRST-BOARD "
                "onset (masterplan sec.10.1, the program's original thesis)",
        "tier": TIER_STAMP,
        "status_honesty": ("This study had NEVER been run before 2026-08-10 and has NEVER "
                           "failed. Every prior kill in this program is an ENTRY-family "
                           "kill on POST-IGNITION cohorts; the shipped onset model is "
                           "ladder-conditioned (N >= 1). Nothing here re-litigates those."),
        "pre_registration_lives_in": "the module docstring of washout_onset_w1.py",
        "vintage": {
            "base_sha": _git("merge-base", "HEAD", "origin/main"),
            "build_head_sha": _git("rev-parse", "HEAD"),
            "raw_store_commit": _git("log", "-1", "--format=%H", "--",
                                     "data/china_stocks_raw"),
            "members_commit": _git("log", "-1", "--format=%H", "--",
                                   "data/china_search/members.parquet"),
            "chips_commit": _git("log", "-1", "--format=%H", "--",
                                 "data/tushare/chips_hist.parquet"),
            "seed": SEED,
            "determinism": ("no wall-clock, runtime or hostname enters this JSON; two "
                            "consecutive TZ=UTC runs at the same commit are byte-identical"),
            "store_basis": ("BACK-ADJUSTED (L1's measured correction to v0's 'nominal' "
                            "header). Adjustment preserves RETURNS, so indicators, "
                            "drawdowns, MAs, volume z-scores and window returns are "
                            "unaffected; only the round-to-tick limit PRICE is, and v0's "
                            "0.002 tolerance is the cushion for exactly that."),
            "event_tape_cross_check": tape_receipt(),
        },
        "confluence_definition_pin": CONFLUENCE_SPEC,
        "coverage": {**pmeta, **cmeta, "chips_store": chips_meta,
                     "cold_rows_analysed": int(len(cold))},
        "split_and_embargo": {
            "splits": {k: [v[0].strftime("%Y-%m-%d"), v[1].strftime("%Y-%m-%d")]
                       for k, v in SPLITS.items()},
            "source": "reconciliation ledger sec.7 (the frozen split, adopted verbatim)",
            "embargo_sensitivity": embargo_sens,
        },
        "q1_first_board_and_q2_window_class": tables,
        "era_tables": era_tables,
        "s5b_chip_coverage_bounded": {
            "cells": s5b_tables,
            "reading": ("S5b's store begins 2025-05-26, INSIDE the locked test window and "
                        "after train and calibration. These cells therefore have NO "
                        "out-of-sample arm and are hypothesis-generating only. Read them "
                        "as coverage disclosure, never as evidence."),
        },
        "q3_prophet_shaped_ranking": ranking,
        "null_headline_battery": {
            "standard": ("masterplan sec.6.4 — an affirmative magnitude gets an "
                         "era-preserving permutation null AND a session bootstrap before "
                         "it may be called supported. Null mean and SD are printed beside "
                         "every p-value so no single draw is quoted against an unstated "
                         "null spread."),
            "selection": (f"holdout cells, era=all, n >= {THIN_CELL_N}, lift >= "
                          f"{NULL_TRIGGER_LIFT}, capped at {NULL_MAX_CELLS} by descending "
                          f"lift; if fewer than {NULL_MIN_CELLS} clear the trigger the top "
                          f"{NULL_MIN_CELLS} by lift are added so the receipt always "
                          "prices its own ceiling. Fit twins of every selected cell are "
                          "included."),
            "cells": nulls,
        },
        "volatility_matched_control": {
            "why": ("AMENDMENT A2. A deeply drawn-down name is a MORE VOLATILE name and a "
                    "more volatile name prints more large moves of EVERY kind, so a raw "
                    "washout lift cannot distinguish 'board-specific ignition' from "
                    "'this name moves a lot'. The date-clustered t already holds the "
                    "SESSION fixed; this additionally holds the name's OWN realised-vol "
                    "decile fixed by direct standardisation. It can only WEAKEN an "
                    "affirmative claim, never create one, which is why adding it after "
                    "seeing the raw lifts is a control and not a search."),
            "cells": vm,
        },
        "confluence_transcription_sanity": sanity,
        "verify_battery": verify,
        "multiplicity": multiplicity,
        "survivorship_stamp": SURVIVORSHIP_STAMP,
        "ore_ledger": ORE_LEDGER,
        "what_this_does_not_establish": [
            "No cell here is a promotion, a gate, a ranker or a sizing input. Display tier.",
            "No entry book is implied and NO expectancy is quoted. Any implied-entry "
            "return read off this file must first be re-priced open-anchored per W3-C, "
            "whose measured law is that the T+1 auction removes the fills.",
            "peak_* outcomes are a FORESIGHT UPPER BOUND: W3-A measured that half to 60% "
            "of threshold-touching windows give the touch back before any scheduled exit.",
            "S4 breadth and f4 sector heat use CURRENT sector membership applied to 15 "
            "years of history; neither is a point-in-time sector statistic.",
            "S5b (chips) has no out-of-sample arm at all — its store starts inside the "
            "locked test window.",
            "Survivors-only, large-cap slice: 35.37% of active SH/SZ names, 0 of 329 BSE. "
            "Nothing here supports a claim about small caps in either direction.",
            "A null on any state closes THAT CONSTRUCTION ONLY. The ore ledger names the "
            "search space this lane did not touch; 'not found yet' is not 'does not exist'.",
            "The confluence definitions are the Terminal's LIVE configuration. Their "
            "parameter neighbourhood was not scanned, so nothing here separates 'this "
            "construction is null' from 'this construction is null AT THESE SETTINGS'.",
        ],
    }
    # Provenance-stability guard (A4): every path-vintage stamp must be reachable from the
    # build head, else the checkout moved mid-run and the stamps are polluted — refuse to
    # write. (Run 1 of the final pair stamped a chips_commit unreachable from HEAD.)
    _head = payload["vintage"]["build_head_sha"]
    for _k in ("raw_store_commit", "members_commit", "chips_commit"):
        _c = payload["vintage"][_k]
        if _c != "UNAVAILABLE" and subprocess.run(
                ["git", "merge-base", "--is-ancestor", _c, _head],
                cwd=REPO, capture_output=True).returncode != 0:
            raise SystemExit(
                f"vintage stamp {_k}={_c} is not an ancestor of build head {_head} — "
                "checkout moved mid-run; refusing to write polluted provenance")
    OUT_JSON.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=False) + "\n")
    print(f"      wrote {OUT_JSON.relative_to(REPO)} "
          f"({OUT_JSON.stat().st_size / 1e6:.2f} MB)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
