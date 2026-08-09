"""US Prophet v1 — board priority score, stage buckets, featured flag, theme linkage.

Architecture mirrors :mod:`engine.china_board_rank` (``cn_prophet_v2``): frozen
constants, pure functions, an artifact-disclosed ``ranking`` block, and no pandas
dependency in the scoring path.  The score is a **transparent priority heuristic,
not a calibrated return forecast** — it orders names that the confluence admission
gate has already admitted; it never decides who is on the board.

Three US-specific departures from the CN module are deliberate and evidenced:

1. ``edge`` (25 pts) replaces CN's ``reversal_member`` leg and is the **residual-alpha
   percentile inside the current buy pool**.  ``research/US_BOARD_MEASUREMENT.md``
   measured residual alpha as the only positive-IC leg at every horizon (§3), while
   the *published* board order — which was conviction/``composite_z`` ordering — was
   anti-predictive at the top (P@1 0.20 as published vs 0.60 re-ordered by alpha;
   ``corr(board_position, excess_5d) = +0.07``; top-5 lift −13.7 points vs the board's
   own base rate, §1).  Its ruling is "order by edge, gate by timing, never the
   reverse".  Accordingly **conviction / composite_z carry ZERO score authority here**
   (see :data:`ZERO_SCORE_AUTHORITY`) and the percentile is transformed
   ``clip01((pctile − 0.25) / 0.75)`` so the bottom quartile of alpha earns nothing.
2. ``runway`` (10 pts) reads the own-history extension z (``ext_z``) rather than CN's
   fuel/extension blend, because that is the extension evidence the US builder
   attaches to a board row.  **This leg read 0 on every row of the 07-31 board, and
   that was a BUILDER WIRING defect, not a property of the leg.**
   ``build_stock_library`` fed :func:`engine.extension.extension_signals` one close
   panel holding both 5-sessions-a-week equities and 24/7 crypto; that panel is indexed
   on the union of the two calendars, and ``extension_signals`` reads a single global
   ``.iloc[-1]``.  So on any build whose newest date was not an equity session — every
   weekend, every market holiday — the last row was crypto-only, every equity's
   ``ext_z`` came back NaN, and no board row carried the leg's input.  Splitting that
   panel by calendar restores it (68/71 of the same buy lane score non-zero, and the
   attainable range returns to 0–100 from the 0–90 the dead leg imposed).  *The 0–100
   range survives ANTICIPATION v1 unchanged: the flat entry leg pays
   :data:`ENTRY_NEUTRAL_VALUE` = 1.0, which is deliberate — see the WHY block on that
   constant.  Flat is not dead: the leg still scores non-zero on every admissible row
   and still separates admissible from non-admissible, it simply declines to order
   within.*

   Do not re-freeze a number here.  Every ``ranking`` block carries
   :func:`component_coverage`, computed from the rows actually scored, so the LIVE
   receipt — not this docstring — is what tells a reader whether the leg is carrying
   information on a given board.  No formula change was made in either era: a null is a
   fact to disclose, not a reason to re-tune (house epistemics — the gauntlet gates
   PROMOTION, not building).
3. Timing decides **grouping** (the stage bucket), never the within-bucket order —
   the same measurement found the timing leg net-negative to sort by (§3, Study 2).

Nothing outside :data:`SCORE_WEIGHTS` may add points.  Theme membership, sector turn,
narrative, the legacy setup score, fundamental quality, low volatility, risk sizing,
smart money, insider prints, SUE, and options/GEX are **context chips only**.

Fail-closed rule, inherited from CN: unknown evidence never earns best-case points.
A row with no extension reading scores 0 on ``runway`` (it is not assumed "not
extended"), and a row with an unknown entry status buckets to ``setting_up``, never to
``live``.

FAIL-CLOSED IS ABOUT POINTS, NOT ABOUT THE LANE (ANTICIPATION v1, 2026-08-08).  From
2026-08-06 an unknown ``ext_z`` also VETOED ``featured``, and on 2026-08-06 that turned
one upstream data gap into a dark board: the equity close panel's newest row carried 6
of 3,034 members, ``extension_signals`` takes a single global ``.iloc[-1]``, so all 69
buy rows came back ``ext_z`` None and the featured lane published 0 of 69.  A veto that
converts an input outage into "we have nothing for you" is a bigger error than the one
it was written to prevent.  An unknown reading is now DISCLOSED rather than vetoing:
the row is featured-eligible and carries ``ext_unknown: true``, the artifact prints the
unknown count, and a majority-unknown board raises a ``::warning``.  A KNOWN reading
past the parabolic line still blocks, exactly as before — the veto still fires on
evidence, it just no longer fires on absence.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


BOARD_DEFINITION = "us_prophet_v1"

FEATURED_CAP = 12
SECTOR_CAP = 4
RAN_CAP = 12
RAN_TICKS_MIN = 3
RAN_TICKS_MAX = 15

# ext_z at or above this is fully extended (mirrors engine.extension.PARABOLIC_Z —
# do not tune here).  ext_z <= 0 is "not extended"; the leg is linear between.
#
# BOUNDARY CONVENTION (intended, not incidental): the SCORE leg is CLOSED at the top —
# ``runway_value`` clips, so ext_z == 2.0 earns 0 runway (>= is the effective test).
# The FEATURED veto is OPEN AT THE BOUNDARY — ``featured_shortfalls`` flags "extended"
# only on ``ext_z > EXT_Z_FULL``, so a row sitting exactly ON the parabolic line is
# still featurable.  The asymmetry is deliberate: scoring is a continuous dial where the
# endpoint must saturate (2.0 and 2.5 are both "no room left"), while featuring is a
# discrete veto, and a veto fires on evidence that is PAST the line, never on evidence
# that merely reaches it — the same fail-open-on-the-boundary rule the tier freshness
# window uses (``ticks <= FEATURED_MAX_TICKS`` qualifies at exactly 2).
#
# OPEN AT THE BOUNDARY IS NOT OPEN ON ABSENCE (B3, 2026-08-06).  A row with NO ext_z
# reading is not "at the line", it is unmeasured.  B3 answered that by BLOCKING it from
# featured (``ext_z_unknown``); ANTICIPATION v1 (2026-08-08) answers it by DISCLOSING it
# (``ext_unknown``) — see the module docstring for why the block was the worse of the
# two errors.  The scoring leg is unchanged either way: an unmeasured row still earns 0
# runway, because that is a points question and points are where fail-closed belongs.
EXT_Z_FULL = 2.0

# A board whose extension reading is unknown on more than this share of its scored rows
# is not a board with a few gaps, it is a board whose extension input is out — the
# 2026-08-06 shape (69/69).  Above this line the pass raises a ``::warning`` so the
# outage is visible in the Actions summary instead of only inside the artifact.
EXT_UNKNOWN_ALARM_FRACTION = 0.5

# WHICH BOARDS CAN HAVE AN EXTENSION OUTAGE AT ALL.  The alarm above asks "did tonight's
# extension input go out?", and only a market that HAS one can answer it.  This module
# is shared: ``engine.hk_board_rank`` delegates ``score_rows``/``ranking_block`` here,
# and HK has never had an ``ext_z`` wiring — nothing sets it in
# ``scripts/build_hk_library.py`` or ``engine/hk_board_rank.py``, and no row of any
# committed HK artifact carries one.  Unscoped, the alarm therefore fired on HK at
# 100% every single night, with remediation text naming a US equity close panel HK does
# not build.  A warning that is always on is not a warning; it teaches readers to skip
# the annotation that matters on the night the US panel really does go dark.
#
# HK's gap is not thereby hidden — it is DISCLOSED, which is the honest form for a
# permanent known absence rather than an outage: ``ext_unknown`` on every row,
# ``ext_unknown_coverage`` on the ranking block, and the featured copy on the board
# saying so (``tests/test_hk_board_ui.py`` pins all three).  Add a market to this set
# when it WIRES an extension reading, never merely because it renders a board.
EXTENSION_PANEL_MARKETS = frozenset((BOARD_DEFINITION,))

# Featured freshness window (mirrors engine.confluence_tiers.FRESH_TICKS).
FEATURED_MAX_TICKS = 2

# Theme linkage (display-tier context; zero score authority).
THEME_TOP_N = 8
THEME_IN_FAVOUR_RECOS = frozenset(("accumulate", "enter"))
# A theme whose bull run is this young "only just confirmed" — the sector-clock /
# stock-clock desync case (a name's cross looks stale while its theme just turned).
THEME_CONFIRMED_MAX_BULL_DAYS = 7
# GICS pseudo-baskets: the card already prints the sector, so a sector chip is noise.
THEME_ID_EXCLUDE_PREFIX = "us_sector_"

SCORE_WEIGHTS = {
    "signal": 30.0,
    "entry": 25.0,
    "edge": 25.0,
    "runway": 10.0,
    "quality": 10.0,
}

# THE SELECTION REGIME this board is running — NOT a version stamp on the constants
# below.  Stamped into every ``ranking`` block so a forward-ledger row can be read
# against the regime that produced it instead of against whatever the constants say the
# day someone opens the artifact.
#
# WHAT BUMPS IT, AND WHY THE ANSWER IS NOT "ANY EDIT" (orchestrator ruling 2026-08-09).
# An earlier draft said to bump this "whenever the ladder or the featured set moves".
# That made the revision rule below UNSATISFIABLE, and the trap is worth naming because
# it is easy to re-introduce: the rule asks for n >= 50 graded marks per cell at H=63
# on episodes stamped with THIS era, and H=63 needs ~3 months to mature — so if the era
# resets every time the map is touched, the episode pool resets with it and the count
# can never reach 50.  A pre-registration whose own clock is restarted by the act of
# revising is not a gate, it is a permanent no.
#
# So: this names WHAT THE BOARD IS SELECTING FOR — the population and the admission
# gate that decide which names become episodes — and it survives a revision of how
# those names are VALUED or ORDERED.  Re-valuing the entry ladder, or widening the
# featured entry set (both of which this era did), leaves the episodes comparable and
# the stamp unchanged.  Bump it only when the selected population itself changes:
# a new admission gate, a different universe, a different lane definition.
SELECTION_ERA = "anticipation-v1-2026-08-08"

# Frozen definition inputs, not fitted coefficients.  The tier cascade and
# entry-status VOCABULARIES are shared with engine.china_board_rank; the VALUES are
# this board's own.
#
# ANTICIPATION v1 (2026-08-08) — THE ADMISSIBLE STATUSES ARE FLAT, ON PURPOSE.
#
# How this landed here.  A2 was first written PATIENCE-FIRST, adopting CN v3's ladder
# outright (``bounce_wait 1.0 … buy_soon 0.35``, ``engine/china_board_rank.py:96-112``)
# on the strength of the parity anatomy — CN's live board is 24/24 patience statuses
# where the US admitted set was 27/27 action statuses, and the US board already carries
# the bounce_wait cohort.  That ordering never reached main.  The §6.6 US
# re-measurement's first run came back ADVERSE to it, on the US board's own graded
# episodes.
#
# THE NUMBERS ARE QUOTED IN FULL BELOW, ON PURPOSE.  The write-up lands in a SEPARATE
# PR (``research/prophet_us_audit/US_STATUS_REMEASUREMENT_2026-08-08.md``, #4988, which
# merges BEFORE this one), so on this branch that path does not resolve.  A map whose
# only stated reason is a pointer to a file the reader cannot open is an unevidenced
# map; these five lines are the load-bearing result, and they are here so this change
# can be judged on its own:
#
#   * buy lane, H=5, both cells above the 20-mark floor: ``bounce_wait`` 54.9% loser
#     (n=153, median excess −0.96%) vs ``buy_now`` 39.0% (n=95, +1.05%).  That is CN's
#     ordering read backwards, by 15.9 points of loser rate.
#   * H=10 keeps the direction: ``bounce_wait`` 65.4% (n=52).
#   * the watch lane repeats it on an independently selected population:
#     ``bounce_wait`` 55.3% (n=76) / 55.9% (n=34).
#   * AND THE NULL THAT OUTWEIGHS ALL OF IT: ``bounce_wait`` has ZERO graded marks at
#     H=21 in any lane, out of 345 episodes, and H=63 has never matured for any status.
#     The patience thesis's claim is "these names need time"; the horizons that would
#     test it carry no US observations at all (the W7 horizon map charters basing at
#     H=63).
#   * WINDOW CONFOUND (found 2026-08-09 by the per-cell vintage fields #4988 added):
#     the buy-lane ``bounce_wait`` cohort spans only 8 board dates, all from
#     2026-07-17 on, while ``buy_now`` spans all 18 dates from 2026-06-18 — different
#     tape, not just different maturity.  The Wilson intervals stay disjoint
#     ([0.470, 0.626] vs [0.298, 0.490]) so the gap survives on its own terms, but the
#     headline is weaker evidence than its point estimates read.  An ordering the
#     record cannot cleanly test is a STRONGER case for the flat leg, not a weaker one.
#
# So the short ruler refutes the CN ordering in this window, and the RIGHT ruler is
# unmeasured.  Neither patience-first nor chase-first is defensible as a ranking claim
# today, and the map must not encode a claim the evidence cannot carry in EITHER
# direction.  The five admissible statuses therefore share ONE value: the entry leg
# still separates admissible from non-admissible, and says nothing whatever about the
# order among them.  A flat leg cannot mis-rank.
#
# THE PRE-REGISTERED REVISION RULE (§6.6's chartered form).  A status ORDERING may be
# re-introduced among these five only when all three hold:
#   1. measured at the status's CHARTERED HORIZON (H=21/H=63 for the patience statuses,
#      not the 5-session ruler that is mostly reading the tape);
#   2. n >= 50 graded marks per cell;
#   3. sign-stable across two half-splits of the window, on episodes drawn from ONE
#      selection regime — ``selection_era: anticipation-v1-2026-08-08`` — so the split
#      is a split of time and not of two different boards.
# Anything less re-opens the same argument with the same absent data.
#
# THE ERA IS THE REGIME, NOT THE MAP VERSION, and clause 3 depends on that: see the WHY
# block on :data:`SELECTION_ERA`.  A revision that passes this rule changes these VALUES
# and does NOT bump the era, so the episodes it was measured on stay in the pool and the
# next revision can be measured against a longer window rather than a reset one.  Read
# the other way round — era bumped on every map edit — clause 2 could never be reached
# at H=63 and this rule would be a permanent refusal wearing a gate's clothes.
# ``tests/test_us_board_rank.py::TestEntryLeg`` pins the flatness, so a re-introduced
# ordering has to go through this rule rather than through an edit.
#
# WHY THE FLAT VALUE IS 1.0 (operator ruling 2026-08-08).  Flat is flat at any value —
# neutrality is a property of the five being EQUAL, not of what they equal — so the
# level is chosen for what it does to everything downstream of the score, not for what
# it claims.  It was briefly 0.75 on the reasoning that the top of the leg should be
# left unclaimed; that reasoning is about the leg in isolation and loses to two effects
# outside it:
#
#   (a) CROSS-ERA SCORE COMPARABILITY.  0.75 subtracts a flat 6.25 points from every
#       ``buy_now`` row and 3.75 from every ``partial`` row versus the pre-era map.
#       Era-stamped or not, a track record whose scores all step down overnight reads
#       as a change in the names when nothing about them moved — the drop carries no
#       information, only noise.  At 1.0 the attainable range stays 0–100.
#   (b) HIDDEN FIXED THRESHOLDS.  Any consumer holding an ABSOLUTE score floor — a
#       featured requirement, a caution-mode conviction floor, a downstream chip
#       cutoff — would have seen the confirmation class silently deflated under it.
#       A leg-level constant must not move rows across thresholds it cannot see.
#
# Measured effect at 1.0, against the pre-era trend-tape map (25-point leg):
#   buy_now 1.0 -> 1.0 = ZERO delta (byte-identical score) · partial 0.9 -> 1.0 = +2.5
#   · hold 0.65 -> 1.0 = +8.75 · wait_pullback 0.55 -> 1.0 = +11.25 · bounce_wait
#   0.35 -> 1.0 = +16.25.
# So no admissible row's score FALLS: the confirmation class holds station and only the
# previously-underranked patience rows lift to meet it.  AND NOTHING DEFLATES EITHER —
# not one status, admissible or not.
#
# NO REFUSED-CLASS VALUE MOVES (orchestrator ruling 2026-08-09).  A draft of this
# change also cut ``buy_soon`` 0.8 -> 0.35, on the ground that CN's table puts it at
# the bottom.  That was withdrawn, for the reason this whole module argues: CN's status
# VALUES are CN-measured and the §6.6 US re-measurement refuted their transfer at H=5
# and H=10.  A US demotion cannot borrow authority from the one ledger that refused it.
# ``buy_soon`` is also not among the five statuses §6.6 ranges over, so it falls under
# that ruling's "refused-class values unchanged" clause and keeps its trend-tape 0.8.
# Moving it would need its own US measurement, through the revision rule above.
#
# The non-admissible values are therefore ALL unchanged from the trend-tape era and are
# NOT part of this ruling: ``buy_soon`` 0.8, ``later`` 0.55, ``await``/
# ``await_confluence`` 0.45, ``watch`` 0.4, and the zeros.  ``extended`` stays 0.0
# where CN keeps 0.3 — the US ``ran`` shelf owns that state and re-valuing it is its
# own ruling.
_SIGNAL_BASE = {"T2": 1.0, "T1": 0.9, "T3": 0.7}

# The one value every admissible status carries.  Named so the flatness is a fact the
# map is BUILT from rather than a coincidence a reader has to notice.  The LEVEL is a
# downstream-safety choice (see the WHY block above); the EQUALITY is the ruling.
ENTRY_NEUTRAL_VALUE = 1.0

# The five statuses the entry leg refuses to order.  Identical to
# :data:`_FEATURED_ENTRY_STATUSES` today and pinned as such by a test — but kept as its
# own constant, because "which statuses may be featured" and "which statuses the
# evidence cannot rank" are two different questions that happen to share an answer.
ENTRY_NEUTRAL_STATUSES = (
    "bounce_wait", "wait_pullback", "hold", "buy_now", "partial",
)

_ENTRY_VALUE = {
    # --- admissible: FLAT, pending the revision rule above -------------------
    "bounce_wait": ENTRY_NEUTRAL_VALUE,
    "wait_pullback": ENTRY_NEUTRAL_VALUE,
    "hold": ENTRY_NEUTRAL_VALUE,
    "buy_now": ENTRY_NEUTRAL_VALUE,
    "partial": ENTRY_NEUTRAL_VALUE,
    # --- not admissible: unchanged, and not part of the §6.6 ruling -----------
    "buy_soon": 0.8,
    "later": 0.55,
    "await": 0.45,
    "await_confluence": 0.45,
    "watch": 0.4,
    "extended": 0.0,
    "topping": 0.0,
    "blocked": 0.0,
    "exit": 0.0,
    "avoid": 0.0,
}

# Stage buckets — timing is the WHEN-gate and owns grouping, never order.
STAGE_LIVE = "live"
STAGE_SETTING_UP = "setting_up"
STAGE_RAN = "ran"
STAGE_BASING = "basing"
STAGE_BLOCKED = "blocked"
# `basing` sits between `ran` and `blocked`: nothing to act on (so it is below every
# actionable bucket), but it is NOT the stand-aside verdict `blocked` carries — the
# cycle read says this name is working on a low, which is a state worth watching.
STAGE_ORDER = (STAGE_LIVE, STAGE_SETTING_UP, STAGE_RAN, STAGE_BASING, STAGE_BLOCKED)
_STAGE_RANK = {name: index for index, name in enumerate(STAGE_ORDER)}

_LIVE_STATUSES = frozenset(("buy_now", "partial", "buy_soon"))
_SETTING_UP_STATUSES = frozenset(("await_confluence", "bounce_wait", "watch"))
_RAN_STATUSES = frozenset(("extended", "topping", "hold"))
_BLOCKED_STATUSES = frozenset(("blocked", "exit", "avoid"))

# The cycle ladder's basing state (engine.cycles.STATE_DISPLAY).  The internal KEY is
# the match target — it is the field the calibration JSON and every ladder consumer
# already agree on — with the display label as the fallback rung for a row that
# carries only what the template renders.  Both spellings are matched because
# `engine.setups.setup_score` stamps `state` AND `label` on a board row, while some
# enrichment paths carry the label alone.
BOTTOM_WATCH_STATE = "BOTTOM WATCH"
_BOTTOM_WATCH_LABELS = frozenset(("NEARING A LOW",))

STAGE_LABELS = {
    STAGE_LIVE: {"en": "Live now", "zh": "现在可操作"},
    STAGE_SETTING_UP: {"en": "Setting up", "zh": "形成中"},
    STAGE_RAN: {"en": "Ran — don't chase", "zh": "已启动 — 勿追"},
    STAGE_BASING: {"en": "Basing", "zh": "筑底中"},
    STAGE_BLOCKED: {"en": "Blocked", "zh": "受阻"},
}

# ANTICIPATION v1 (2026-08-08) — the featured shelf admits the PATIENCE statuses.
# CN's set verbatim (``engine/china_board_rank.py:116-118``); the same v1-provisional
# caveat as the ladder above applies.
#
# STAGED, NOT YET LIVE — READ THIS BEFORE CONCLUDING THE WIDENING DID ANYTHING.
# ``featured_shortfalls`` vetoes any row whose stage is not ``live``, and
# ``stage_for`` routes bounce_wait/wait_pullback to ``setting_up`` and hold to
# ``ran``.  So the three statuses added here clear the ENTRY-STATUS veto and are then
# stopped by ``stage_not_live`` — today this widening changes no featured flag on any
# board.  That is deliberate: relaxing the stage gate moves rows onto a rendered
# shelf whose own label says "Setting up" / "Ran — don't chase", which is a surface
# contradiction a rank module does not get to resolve alone.  CN has no stage gate on
# featuring at all (``china_board_rank._featured_shortfalls``) — that is the
# structural difference, and closing it is the follow-up.
# ``tests/test_us_board_rank.py::TestFeaturedEntryStatuses`` pins BOTH halves: the
# widened set, and the fact that it is currently inert.  That test goes red when the
# stage gate is relaxed, which is exactly when someone should be reading this comment.
_FEATURED_ENTRY_STATUSES = frozenset(
    ("bounce_wait", "wait_pullback", "hold", "buy_now", "partial")
)
_FEATURED_TIERS = frozenset(("T1", "T2", "T3"))

ZERO_SCORE_AUTHORITY = (
    "conviction_composite",
    "setup",
    "sector_turn",
    "narrative",
    "quality_factor",
    "low_vol",
    "risk_sizing",
    "smartmoney",
    "insider",
    "sue",
    "options_gex",
    "theme",
    # Blow-off (terminal) risk context — engine/roc_blowoff, stamped onto rows as
    # ``blowoff``.  A measured RISK read, never a rank input: it earns no points, vetoes
    # no featuring and changes no stage.  tests/test_roc_blowoff.py pins byte-identity
    # of score_rows() output with the field present vs absent.
    "blowoff_risk",
)

SCORE_KIND = "transparent priority heuristic; not a calibrated return forecast"


# --------------------------------------------------------------------------- #
# small pure helpers
# --------------------------------------------------------------------------- #
def _clip01(value: Any) -> float:
    """Return a finite float clipped to ``[0, 1]``; malformed values become zero."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def _finite_float(value: Any) -> float | None:
    """Return ``value`` as a finite float, or ``None`` (NaN/inf/garbage all fail)."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _finite_int(value: Any) -> int | None:
    """Integer coercion that keeps ``0`` — a same-day cross is the FRESHEST signal.

    ``ticks``, ``bars_to_cross`` and ``days_since_signal`` are all legitimately ``0``.
    Every caller must therefore test ``is not None`` rather than truthiness; writing
    ``(v.get("ticks") or 99) <= 2`` silently un-features exactly the freshest rows.
    """
    number = _finite_float(value)
    return int(number) if number is not None else None


def _as_date(value: Any) -> str | None:
    """Normalise common date values without making the ranking depend on pandas."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else (text or None)


def _status_of(entry: Mapping[str, Any] | None) -> str:
    return str((entry or {}).get("status") or "").strip().lower()


def _notice(title: str, message: str) -> None:
    """Emit a GitHub Actions notice.

    A bare ``print`` with ``flush=True`` is load-bearing (house law): every builder
    here logs through a prefixing formatter, so ``log.info("::notice ...")`` emits
    ``INFO ::notice ...`` and GitHub silently drops the annotation.  stdout is
    block-buffered when piped in CI, hence the flush.
    """
    print(f"::notice title={title}::{message}", flush=True)


def _warning(title: str, message: str) -> None:
    """Emit a GitHub Actions warning.

    Same house law as :func:`_notice`: a BARE ``print`` starting the line, never a
    logger (a prefixing formatter turns ``::warning`` into ``WARNING ::warning`` and
    GitHub drops it silently), and ``flush=True`` because stdout is block-buffered
    when piped in CI.
    """
    print(f"::warning title={title}::{message}", flush=True)


# --------------------------------------------------------------------------- #
# score legs
# --------------------------------------------------------------------------- #
def signal_value(verdict: Mapping[str, Any] | None) -> float:
    """Confluence-tier freshness value in ``[0, 1]`` (CN's frozen map).

    Base ``{T2: 1.0, T1: 0.9, T3: 0.7}`` (the operator re-ranked T2 above T1 on
    2026-07-06); a provisional verdict loses 0.1; a cross that is 2 ticks old is
    decayed 15%.  Any other tier — including ``T4`` and a cleared ``None`` — is 0.

    KNOWN NON-MONOTONE FRESHNESS (documented, NOT fixed this round).  The decay fires
    on ``ticks == 2`` exactly, so the leg reads 1.00 / 1.00 / 0.85 / 1.00 for ticks
    0 / 1 / 2 / 3: a 3-tick-old cross scores HIGHER than a 2-tick-old one.  The shape
    is inherited verbatim from :mod:`engine.china_board_rank` (the two boards speak one
    scoring language by charter), and it is only reachable at ticks >= 3, which the
    featured gate already excludes as ``ticks_stale``.  Any repair is a re-tune of a
    FROZEN shared constant, so it belongs in a measured change to both boards at once —
    not in a one-sided edit here.  Left as-is deliberately; do not "fix" it in passing.
    """
    verdict = verdict or {}
    value = _SIGNAL_BASE.get(str(verdict.get("tier_cascade")), 0.0)
    if verdict.get("provisional"):
        value = max(0.0, value - 0.1)
    ticks = _finite_int(verdict.get("ticks"))
    if ticks is not None and ticks == 2:
        value *= 0.85
    return _clip01(value)


def entry_value(entry: Mapping[str, Any] | None) -> float:
    """Entry-window value in ``[0, 1]`` — CN's ``_ENTRY_VALUE`` map verbatim."""
    return _ENTRY_VALUE.get(_status_of(entry), 0.0)


def selection_value(row: Mapping[str, Any]) -> Any:
    """The US board's selection-axis reading: residual alpha, straight off the row.

    Factored out (2026-08-02, hk_prophet_v1 port) so a sibling board can point the
    ``edge`` leg at ITS OWN selection axis without copying the percentile machinery.
    The leg's charter is "the selection axis" — the quantity a market's measurement
    found positive-IC — and only the US spells that ``row["alpha"]``.  On the HK
    board the same charter resolves to the fused ``hk_edge`` z; see
    :func:`engine.hk_board_rank.selection_value`.
    """
    return row.get("alpha")


def alpha_percentiles(
    rows: Sequence[Mapping[str, Any]],
    *,
    value_of: Callable[[Mapping[str, Any]], Any] | None = None,
) -> dict[int, float | None]:
    """Row-index → selection-axis percentile inside the supplied pool.

    Rank 1 is the highest reading; percentile 1.0 is the top of the pool and 0.0 the
    bottom.  Ties break on ticker so the percentile is reproducible for identical
    inputs.  Rows with no finite reading are excluded from the pool (they neither
    occupy a rank nor distort the spread) and map to ``None`` — the fail-closed
    outcome is zero points, not a mid-pool default.

    ``value_of`` reads each row's selection axis and defaults to
    :func:`selection_value` (``row["alpha"]``), so the US call site is unchanged.
    The percentile CONSTRUCTION is what the two boards share; the field it reads is
    the market parameter.

    A pool of ONE also maps to ``None``.  A percentile is a CROSS-SECTIONAL reading,
    and a cross-section of one has none: the single row is simultaneously the top and
    the bottom of its own pool, so any number here is an artifact of the degenerate
    pool rather than evidence about the name.  Awarding it 1.0 handed the full 25-point
    ``edge`` leg to a row that had out-ranked nothing.  ``None`` earns 0 by the same
    fail-closed rule that governs an unknown alpha — unknown evidence never earns
    best-case points.
    """
    read = value_of or selection_value
    ranked: list[tuple[int, str, float]] = []
    for index, row in enumerate(rows):
        alpha = _finite_float(read(row))
        if alpha is None:
            continue
        ranked.append((index, str(row.get("ticker") or ""), alpha))

    out: dict[int, float | None] = {index: None for index in range(len(rows))}
    count = len(ranked)
    if count < 2:                    # empty pool, or a degenerate pool of one
        return out
    ranked.sort(key=lambda item: (-item[2], item[1]))
    for rank, (index, _ticker, _alpha) in enumerate(ranked, start=1):
        percentile = 1.0 - (rank - 1) / (count - 1)
        out[index] = round(_clip01(percentile), 6)
    return out


def edge_value(percentile: float | None) -> float:
    """Transform an alpha percentile so the bottom quartile of the pool earns zero.

    ``clip01((pctile − 0.25) / 0.75)``.  The measurement found the alpha edge real but
    tail-concentrated — a floor that deletes the bottom quartile, not a fine ranker.
    """
    if percentile is None:
        return 0.0
    return _clip01((_clip01(percentile) - 0.25) / 0.75)


def runway_value(row: Mapping[str, Any]) -> float:
    """Room-to-run value in ``[0, 1]`` = ``1 − extension``.

    ``ext_z >= EXT_Z_FULL`` is fully extended (0 runway), ``ext_z <= 0`` is not
    extended (full runway), linear in between; an ``antichase_shadow_blocked`` row is
    treated as fully extended.  **Unknown extension evidence earns 0**, never the
    best case — CN's fail-closed rule.

    HISTORY: this leg read 0 on 71/71 rows of the 07-31 board.  That was a builder
    wiring defect — ``build_stock_library`` mixed the equity and 24/7 crypto calendars
    in the single close panel it handed ``extension_signals``, so on any non-session
    build date every equity's ``ext_z`` was NaN and the input never reached a row (see
    the module docstring).  With the panel split by calendar the same lane scores 68/71.

    Do not restate a coverage number here, in either direction:
    :func:`component_coverage` recomputes the nonzero count from the rows actually
    scored on every build, so the live receipt is the disclosure and cannot go stale
    the way this docstring's successive "very few board rows" and "this leg is DEAD"
    wordings both did.
    """
    if row.get("antichase_shadow_blocked") is True:
        return 0.0
    ext_z = _finite_float(row.get("ext_z"))
    if ext_z is None:
        return 0.0
    return _clip01(1.0 - _clip01(ext_z / EXT_Z_FULL))


def quality_value(row: Mapping[str, Any]) -> float:
    """Bottom-quality value in ``[0, 1]`` — CN's ``_bottom_quality_value`` logic."""
    coiled = row.get("coiled") or {}
    if coiled.get("star"):
        return 1.0
    if coiled.get("coiled"):
        return 0.8
    if coiled.get("washout_ctx") or row.get("washout_ctx"):
        return 0.4
    return 0.0


# --------------------------------------------------------------------------- #
# stage bucketing
# --------------------------------------------------------------------------- #
def is_downtrend(row: Mapping[str, Any]) -> bool:
    """True when the row is a DOWNTREND name (masterplan §3.1's second blocked clause).

    Two independent readings, either of which is sufficient: the cycle ladder's own
    ``dir == "down"``, or its ``DOWNTREND`` headline label (``engine.cycles`` stamps
    both on a DECLINE row).  The label match is on the leading token because
    ``build_stock_library._enforce_blocked_buy_invariant`` may suffix it — the shipped
    07-31 board carries ``"UPTREND (blocked)"``-style labels, so an equality test would
    read a suffixed DOWNTREND as unknown.
    """
    if str(row.get("dir") or "").strip().lower() == "down":
        return True
    label = str(row.get("label") or "").strip().upper()
    for opener in ("(", "（"):        # ASCII " (blocked)" and its zh "（受阻）" twin
        label = label.split(opener)[0]
    return label.strip() == "DOWNTREND"


def is_bottom_watch(row: Mapping[str, Any]) -> bool:
    """True when the cycle ladder reads this row as BOTTOM WATCH — the basing state.

    BOTTOM WATCH carries ``dir == "down"`` (``engine.cycles.STATE_DISPLAY``) because
    price is still falling, so :func:`is_downtrend` answers True for it as well.  That
    is why this test has to run FIRST wherever the two are consulted together: the two
    predicates overlap, and the more specific one has to win.

    The internal ``state`` key is the primary rung — it is what the calibration JSON
    and every other ladder consumer key on, and it does not move when display copy is
    rewritten.  The display label is a fallback for rows carrying only what the
    template renders, matched on the leading token because
    ``build_stock_library._enforce_blocked_buy_invariant`` may suffix it (the shipped
    board carries ``"NEARING A LOW (blocked)"``-style labels — 7 of the 41 buy-lane
    BOTTOM WATCH rows in the 2026-06-30..07-31 ledger did).

    DECLINE and ROLLING OVER are NOT basing: they are the falling-knife and the
    topping roll, and they keep routing to ``blocked``.
    """
    if str(row.get("state") or "").strip().upper() == BOTTOM_WATCH_STATE:
        return True
    label = str(row.get("label") or "").strip().upper()
    for opener in ("(", "（"):        # ASCII " (blocked)" and its zh "（受阻）" twin
        label = label.split(opener)[0]
    return label.strip() in _BOTTOM_WATCH_LABELS


def stage_for(row: Mapping[str, Any], entry: Mapping[str, Any] | None = None, *,
              bottom_watch_stage: str = STAGE_BLOCKED) -> str:
    """Bucket a row into ``live`` / ``setting_up`` / ``ran`` / ``basing`` / ``blocked``.

    ``bottom_watch_stage`` names the bucket the ladder's BOTTOM WATCH state routes to.
    The default is ``STAGE_BLOCKED`` — the behaviour every caller had before the basing
    shelf existed — so a board that has not built the shelf keeps its rendering
    byte-identical; the US board opts in by passing ``STAGE_BASING`` (see
    :func:`score_rows`).  It is a PARAMETER rather than a flag day because the shelf is
    a rendered surface: routing rows to a bucket a template does not know about would
    drop them below the blocked shelf via the catch-all, which is strictly worse than
    where they sit today.  DISPLAY-TIER ONLY — this function decides grouping, never
    membership, never score, never who is featured.

    WHY BOTTOM WATCH NEEDED ITS OWN BUCKET (D18, missed-ignitions audit).  BOTTOM WATCH
    is ``dir == "down"``, so the DOWNTREND clause below swallowed it: the one ladder
    state that names a name working on a low was invisible-by-construction, filed under
    "stand aside" beside the falling knives.  Measured on the board's own ledger
    (``data/us_board_ledger/snapshots.jsonl``, 2026-06-30..07-31): 41 buy-lane rows
    across 13 of 17 board days, every one of them routed to ``blocked``.  That clause
    was an unmeasured implementation choice, not a pre-registered rule (census verdict),
    and the split changes only which shelf a row renders under.

    Blocked wins over everything.  Masterplan §3.1 defines the bucket as
    ``{blocked, exit, avoid} OR label DOWNTREND``, and the DOWNTREND clause is
    UNCONDITIONAL: a name the cycle read calls a downtrend is blocked whatever its
    entry status claims.  The two clauses are independent evidence, and the entry
    status does not get to overrule the trend — a ``bounce_wait`` on a falling name is
    exactly the "catch the knife" row the stage buckets exist to demote.  (This engine
    previously applied the DOWNTREND clause only to rows with NO entry status at all,
    which silently let a downtrending ``bounce_wait`` render in ``setting_up``, above
    the blocked bucket.  ``tests/test_us_board_priority_ui.py::_stage_of`` — the
    rendered-HTML contract — has asserted the unconditional rule all along, so the
    engine was the side that disagreed with the spec AND with its own UI.)

    A missing or unrecognised status buckets to ``setting_up`` — an unknown timing
    state is never advertised as live.
    """
    status = _status_of(entry if entry is not None else row.get("entry_signal"))
    if status in _BLOCKED_STATUSES:
        return STAGE_BLOCKED
    # BEFORE the DOWNTREND clause, and deliberately AFTER the entry-status one: an
    # explicit blocked/exit/avoid entry verdict is a decision about this name, and it
    # outranks the cycle read exactly as it does for every other state.
    if is_bottom_watch(row):
        return bottom_watch_stage
    if is_downtrend(row):
        return STAGE_BLOCKED
    if status in _LIVE_STATUSES:
        return STAGE_LIVE
    if status in _RAN_STATUSES:
        return STAGE_RAN
    if status in _SETTING_UP_STATUSES:
        return STAGE_SETTING_UP
    return STAGE_SETTING_UP


def stage_rank(stage: str) -> int:
    """Sort position of a stage bucket (unknown stages sort last, deterministically)."""
    return _STAGE_RANK.get(stage, len(STAGE_ORDER))


# --------------------------------------------------------------------------- #
# freshness
# --------------------------------------------------------------------------- #
def signal_asof(row: Mapping[str, Any], verdict: Mapping[str, Any] | None = None) -> str | None:
    """The signal's own session date (verdict first, then the row's compact signal)."""
    if verdict:
        stamped = _as_date(verdict.get("asof"))
        if stamped:
            return stamped
    return _as_date((row.get("signal") or {}).get("asof"))


def days_since_signal(sig_asof: Any, board_asof: Any) -> int | None:
    """Calendar days between the signal session and the board session.

    ``0`` means the signal fired on the board's own session — the freshest possible
    value, and the reason every consumer must test ``is not None`` before comparing.
    Returns ``None`` when either date is unknown or unparseable.  A negative value is
    returned as-is rather than clamped: a signal stamped after the board session is a
    data fault that should stay visible.
    """
    left = _as_date(sig_asof)
    right = _as_date(board_asof)
    if not left or not right:
        return None
    try:
        return (date.fromisoformat(right) - date.fromisoformat(left)).days
    except ValueError:
        return None


BASIS_SESSIONS = "sessions"
BASIS_CALENDAR = "calendar"


def signal_age(
    verdict: Mapping[str, Any] | None,
    sig_asof: Any,
    board_asof: Any,
) -> tuple[int | None, str | None]:
    """``(days_since_signal, basis)`` — the SESSION count when one is known.

    ``days_since_signal`` is read as a SESSION count by the shared consumer
    (``templates/stocktable.js``: ``FRESH_DAYS = 2`` gates the NEW dot and the
    fresh-only filter), so this resolver prefers the session answer and DISCLOSES the
    basis whenever it has to fall back.

    * ``sessions`` — the verdict's session count since the §7 buy marker.  Preferred
      source is ``fresh_bars_knowable`` (``engine.signal_gate._knowable_bars``), which
      counts from the session the marker's 3D bucket CLOSED on; ``fresh_bars`` (counted
      from the bucket's OPEN label, ``engine.signal_gate._bars_since``) is the fallback
      for a verdict built before the knowable field existed or where the anchor was not
      derivable.  The two differ by up to two sessions, always in the same direction:
      the OPEN label predates its own bucket's close, so ``fresh_bars`` reports a signal
      as older than it was ever knowable.  Measured on the committed 2026-08-06 board:
      APH and FCX published ``days_since_signal 4`` against a knowable age of 2, which is
      outside ``templates/stocktable.js``'s ``FRESH_DAYS = 2`` — the fresh-only filter was
      dropping the freshest turns on the board.  ``fresh_bars`` itself is UNCHANGED: it
      gates eligibility and FRESH_TICKS across five boards, and re-anchoring it is a
      semantic change owing a blast-radius report (``research/
      SQ_BUCKET_LABEL_AS_DATE_FINDINGS_2026-08-07.md`` §4).
    * ``calendar`` — the plain date difference, used only when no marker-anchored
      session count exists.

    The two are NOT interchangeable and the gap is not small.  The calendar leg
    measures the distance from ``signal.asof``, which is the ticker's LAST CLOSE BAR
    (``engine.signal_quality.analyze`` stamps ``str(idx[-1].date())``), not the date
    the signal fired: on the committed 07-31 board NUE reads ``signal.asof
    2026-07-31`` while its own last marker fired ``2026-06-16``.  Calendar-only would
    therefore report that 45-day-old signal as 0 days and light the NEW dot on nearly
    every row.  ``fresh_bars`` measures the marker, which is what the field's name and
    its consumer both mean.

    Emitting the basis rather than silently switching units is the point: the same
    field carries calendar days on the CN/CA boards (days since first board
    appearance), so a consumer reading across boards must be able to see which
    question this number answers.  Returns ``(None, None)`` when neither is available —
    an unknown age is a null to print, never a zero.
    """
    for field in ("fresh_bars_knowable", "fresh_bars"):
        bars = _finite_int((verdict or {}).get(field))
        if bars is not None and bars >= 0:
            return bars, BASIS_SESSIONS
    days = days_since_signal(sig_asof, board_asof)
    if days is None:
        return None, None
    return days, BASIS_CALENDAR


# --------------------------------------------------------------------------- #
# featured
# --------------------------------------------------------------------------- #
def ext_unknown(row: Mapping[str, Any]) -> bool:
    """True when this row carries no usable extension reading.

    One predicate, three consumers — the featured disclosure flag, the artifact count
    and the outage alarm — so "unknown" cannot mean three slightly different things.
    NaN counts as unknown: the 2026-07-31 defect delivered a float that is not a
    number, and a float that is not a number is not evidence.
    """
    return _finite_float(row.get("ext_z")) is None


def featured_shortfalls(
    row: Mapping[str, Any],
    *,
    verdict: Mapping[str, Any] | None = None,
    entry: Mapping[str, Any] | None = None,
    in_blackout: bool | None = None,
    alpha_of: Callable[[Mapping[str, Any]], Any] | None = None,
    extra: Callable[[Mapping[str, Any]], Iterable[str]] | None = None,
) -> list[str]:
    """Every reason this row may not be featured (empty list = it qualifies).

    Featured is a **flag plus an order**, never a population change: a row that fails
    here stays on the buy lane exactly where its stage and score put it.

    ``alpha_of`` names the selection axis the ``alpha_below_floor`` test reads
    (default :func:`selection_value`); ``extra`` contributes market-specific
    shortfalls — the HK board adds a 63-day-turnover floor there.  Both default to
    the US behaviour, so this signature change is invisible to the US call sites.
    An ``extra`` that raises is NOT swallowed: a liquidity gate that fails open is
    the failure mode a featured flag can least afford.
    """
    reasons: list[str] = []
    verdict = verdict if verdict is not None else (row.get("signal") or {})
    entry = entry if entry is not None else (row.get("entry_signal") or {})

    # No ``bottom_watch_stage`` here on purpose: this asks one question — "is this row
    # LIVE" — and both answers the parameter can produce (``basing``/``blocked``) are
    # not, so the featured flag is provably invariant to the basing split.  Threading
    # the parameter would add a second place the split could drift without changing a
    # single verdict.
    if stage_for(row, entry) != STAGE_LIVE:
        reasons.append("stage_not_live")
    status = _status_of(entry)
    if status not in _FEATURED_ENTRY_STATUSES:
        reasons.append(f"entry_status_{status or 'unknown'}")

    tier = str(verdict.get("tier_cascade") or "")
    if tier not in _FEATURED_TIERS:
        reasons.append(f"tier_{tier or 'unknown'}")

    # ticks == 0 is a same-day cross — the best case.  Explicit None check, never
    # `or`: truthiness would reject 0 and un-feature the freshest rows on the board.
    ticks = _finite_int(verdict.get("ticks"))
    if ticks is None:
        reasons.append("ticks_unknown")
    elif ticks > FEATURED_MAX_TICKS:
        reasons.append("ticks_stale")

    if verdict.get("provisional"):
        reasons.append("provisional")

    if row.get("antichase_shadow_blocked") is True:
        reasons.append("antichase_blocked")

    # ANTICIPATION v1 2026-08-08 — an unknown extension is DISCLOSED, not vetoed.
    # B3 (2026-08-06) made an unknown reading a featured veto on the reasoning that a
    # veto whose input is dark cannot be said to have passed.  That reasoning is right
    # about the EVIDENCE and wrong about the REMEDY: on 2026-08-06 the equity close
    # panel's newest row held 6 of 3,034 members, `extension_signals` reads one global
    # `.iloc[-1]`, every one of the 69 buy rows came back None, and the veto published
    # a featured lane of 0 — an upstream data gap rendered as "nothing to show you".
    # The board now says what it knows and flags what it does not: the row is eligible
    # and `score_rows` stamps `ext_unknown` on it, `ranking_block` prints the count,
    # and a majority-unknown board raises a ::warning.  A KNOWN reading past the line
    # still blocks — the veto fires on evidence, never on absence.  The SCORE leg is
    # untouched: an unmeasured row still earns 0 runway.
    ext_z = _finite_float(row.get("ext_z"))
    if ext_z is not None and ext_z > EXT_Z_FULL:
        reasons.append("extended")

    alpha = _finite_float((alpha_of or selection_value)(row))
    if alpha is None:
        reasons.append("alpha_unknown")
    elif alpha < 0:
        reasons.append("alpha_below_floor")

    blackout = in_blackout
    if blackout is None:
        blackout = (row.get("earnings_soon") or {}).get("in_blackout")
    if blackout is True:
        reasons.append("earnings_blackout")

    if extra is not None:
        reasons.extend(str(reason) for reason in (extra(row) or ()))

    return reasons


# --------------------------------------------------------------------------- #
# the scoring pass
# --------------------------------------------------------------------------- #
def score_rows(
    rows: Iterable[dict],
    *,
    verdict_by: Mapping[str, Mapping[str, Any]] | None = None,
    entry_by: Mapping[str, Mapping[str, Any]] | None = None,
    blackout_by: Mapping[str, bool] | None = None,
    board_asof: Any = None,
    featured_cap: int = FEATURED_CAP,
    sector_cap: int = SECTOR_CAP,
    definition: str = BOARD_DEFINITION,
    alpha_of: Callable[[Mapping[str, Any]], Any] | None = None,
    featured_extra: Callable[[Mapping[str, Any]], Iterable[str]] | None = None,
    bottom_watch_stage: str = STAGE_BLOCKED,
) -> list[dict]:
    """Score, stage, feature and order a buy pool.

    Rows are stamped **in place** and returned in board order — the US builder shares
    one row object across lanes and enrichment passes, so copying here would strand
    every later mutation.  Membership is untouched: this function adds fields and
    decides ORDER, never who is on the board.

    Sort key: ``(stage_rank, −score, ticker)``.  ``score_rank`` is the pool rank by
    that key and ``display_rank`` the rendered position; today they are equal, and
    they are kept separate so a future lane split cannot silently conflate them.

    ``definition`` stamps ``prophet.version`` (``hk_prophet_v1`` reuses this whole
    pass), ``alpha_of`` names the selection axis the ``edge`` leg reads, and
    ``featured_extra`` adds market-specific featured vetoes.  All three default to
    the US answer — the arithmetic, the weights and the stage map are SHARED, and
    only the field names are market parameters.

    ``bottom_watch_stage`` is the one exception to that "US answer by default" rule
    and it is deliberate: it defaults to ``STAGE_BLOCKED``, the pre-basing behaviour,
    so a board whose template has no basing shelf keeps rendering byte-identically.
    The US builder passes ``STAGE_BASING``; see :func:`stage_for`.  It moves rows
    between DISPLAY buckets and nothing else — membership, score, order-within-bucket
    and the featured flag are all computed the same way either way.
    """
    pool = list(rows)
    board_date = _as_date(board_asof)
    percentiles = alpha_percentiles(pool, value_of=alpha_of)

    for index, row in enumerate(pool):
        ticker = str(row.get("ticker") or "")
        verdict = (verdict_by or {}).get(ticker) or row.get("signal") or {}
        entry = (entry_by or {}).get(ticker) or row.get("entry_signal") or {}

        values = {
            "signal": signal_value(verdict),
            "entry": entry_value(entry),
            "edge": edge_value(percentiles.get(index)),
            "runway": runway_value(row),
            "quality": quality_value(row),
        }
        points = {
            name: round(SCORE_WEIGHTS[name] * value, 4)
            for name, value in values.items()
        }
        score = max(0.0, min(100.0, sum(points.values())))

        row["stage"] = stage_for(row, entry, bottom_watch_stage=bottom_watch_stage)
        row["prophet"] = {
            "version": definition,
            "score": round(score, 1),
            "components": {name: round(value, 6) for name, value in values.items()},
            "points": points,
            "alpha_percentile": percentiles.get(index),
            "zero_score_authority": list(ZERO_SCORE_AUTHORITY),
        }
        # No top-level ``score`` key: rows already carry ``alpha``, ``setup`` and the
        # conviction score legs, and a fourth bare "score" would be unreadable.
        # ``prophet.score`` is the display/sort authority; the legacy fields stay.
        sig_date = signal_asof(row, verdict)
        row["signal_asof"] = sig_date
        age, basis = signal_age(verdict, sig_date, board_date)
        row["days_since_signal"] = age
        row["days_since_signal_basis"] = basis
        row["new"] = bool(sig_date and board_date and sig_date == board_date)

        shortfalls = featured_shortfalls(
            row,
            verdict=verdict,
            entry=entry,
            in_blackout=(blackout_by or {}).get(ticker),
            alpha_of=alpha_of,
            extra=featured_extra,
        )
        row["_featured_shortfalls"] = shortfalls
        row["featured"] = False
        # Per-row extension disclosure (ANTICIPATION v1).  Stamped on EVERY row as a
        # bool, never only when true: a missing key would read as "old build" and a
        # false is a fact the same way a zero in `stage_counts` is.
        row["ext_unknown"] = ext_unknown(row)

    _warn_on_dark_extension(pool, definition=definition)

    pool.sort(
        key=lambda row: (
            stage_rank(str(row.get("stage") or "")),
            -float((row.get("prophet") or {}).get("score") or 0.0),
            str(row.get("ticker") or ""),
        )
    )

    featured_n = 0
    sector_counts: dict[str, int] = defaultdict(int)
    for rank, row in enumerate(pool, start=1):
        row["score_rank"] = rank
        row["display_rank"] = rank
        shortfalls = row.pop("_featured_shortfalls", ["not_evaluated"])
        if shortfalls:
            row["featured_blocked_by"] = shortfalls
            continue
        sector = str(row.get("sector") or "—")
        if featured_n >= max(0, int(featured_cap)):
            row["featured_blocked_by"] = ["featured_cap"]
        elif sector_counts[sector] >= max(0, int(sector_cap)):
            row["featured_blocked_by"] = ["sector_cap"]
        else:
            featured_n += 1
            sector_counts[sector] += 1
            row["featured"] = True
            row.pop("featured_blocked_by", None)
    return pool


def ext_unknown_coverage(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """``{"unknown": k, "n": total, "featured_with_unknown": m}`` over scored rows.

    The disclosure that replaces the information ``featured_blocked_unknown_extension``
    used to carry.  That key still ships and is still recomputed, but from 2026-08-08
    an unknown reading no longer blocks, so it reads 0 on every board — accurate, and
    for exactly that reason no longer able to tell a reader whether the extension input
    is alive.  This is the number that can: ``unknown`` counts the rows with no reading
    and ``featured_with_unknown`` counts how many of them the shelf published anyway.

    ``ext_unknown`` is read off the stamped row when present so this agrees with the
    flag the artifact shipped, and falls back to the predicate for rows scored by an
    older pass.
    """
    out = {"unknown": 0, "n": 0, "featured_with_unknown": 0}
    for row in rows:
        out["n"] += 1
        flag = row.get("ext_unknown")
        unknown = bool(flag) if isinstance(flag, bool) else ext_unknown(row)
        if unknown:
            out["unknown"] += 1
            if row.get("featured"):
                out["featured_with_unknown"] += 1
    return out


def _warn_on_dark_extension(
    rows: Sequence[Mapping[str, Any]], *, definition: str = BOARD_DEFINITION
) -> None:
    """Raise a ``::warning`` when the extension input is out on most of the board.

    Since 2026-08-08 an unknown ``ext_z`` no longer darkens the featured lane, so the
    lane going empty is no longer the alarm it used to be — this is.  Fired from the
    scoring pass so it lands in the builder's own Actions step, and phrased with the
    numbers rather than a hedge.

    OUTAGE, NOT ABSENCE.  Scoped to :data:`EXTENSION_PANEL_MARKETS`: a board that has no
    extension wiring cannot have an extension outage, and firing here on every HK build
    said only that HK is HK, in US remediation words.  See that constant for why the
    honest treatment of a permanent absence is the artifact disclosure instead.
    """
    if definition not in EXTENSION_PANEL_MARKETS:
        return
    total = len(rows)
    if not total:
        return
    unknown = sum(1 for row in rows if ext_unknown(row))
    if unknown <= EXT_UNKNOWN_ALARM_FRACTION * total:
        return
    _warning(
        "featured-ext-z-unknown",
        f"{definition}: extension reading unknown on {unknown}/{total} scored rows "
        f"({unknown / total:.0%}) — the featured lane is publishing rows whose "
        "chase-risk check has no input (ext_unknown: true). Check the extension "
        "panel's newest row: a partial price advance leaves a sparse last session and "
        "extension_signals reads one global .iloc[-1].",
    )


def component_coverage(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Per-leg ``{"nonzero": k, "n": total}`` over the rows actually scored.

    The score's own coverage receipt, RECOMPUTED on every build so it can never drift
    from the board it describes (a hardcoded number outlives its recompute — this is
    the disclosure, not a comment about one night's data).

    A leg with ``nonzero == 0`` is dead: it subtracts the same points from every row,
    so it cannot change the ORDER, but it also carries no information and it caps the
    attainable score below 100.  ``runway`` read ``{"nonzero": 0, "n": 71}`` on the
    07-31 board because a builder wiring defect kept ``ext_z`` off every row (module
    docstring §2); the same lane reads ``{"nonzero": 68, "n": 71}`` once the extension
    panel is split by calendar.  Printed rather than hidden, and printed as a NUMBER
    rather than a hedge — display-tier disclosure is exactly what the epistemics law
    asks of a null, and recomputing it is what keeps the claim true in both eras.

    Every leg in :data:`SCORE_WEIGHTS` is reported, present or not: a bucket missing
    from this dict would read as "not measured", which is a different claim from
    "measured zero".
    """
    out = {name: {"nonzero": 0, "n": 0} for name in SCORE_WEIGHTS}
    for row in rows:
        components = (row.get("prophet") or {}).get("components") or {}
        for name in SCORE_WEIGHTS:
            value = _finite_float(components.get(name))
            if value is None:            # leg not scored on this row — not a zero
                continue
            out[name]["n"] += 1
            if value != 0.0:
                out[name]["nonzero"] += 1
    return out


def stage_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Per-stage row counts, every bucket present (a zero is a fact, not an absence)."""
    counts = {stage: 0 for stage in STAGE_ORDER}
    for row in rows:
        stage = str(row.get("stage") or "")
        if stage in counts:
            counts[stage] += 1
    return counts


EDGE_READS_US = "residual alpha percentile inside this buy pool"

# The entry leg's PROVENANCE, and it is not the same sentence on every board.
#
# WHOSE MEASUREMENT IS THIS (audit finding, 2026-08-09).  `engine.hk_board_rank`
# delegates both `score_rows` and `ranking_block` here, so HK ships this module's entry
# map and this module's receipt verbatim.  Written as one string, that receipt told an
# HK reader that the HK entry leg is flat because a US re-measurement over US episodes
# read adverse — attributing to the HK board a measurement that was never run on it.
# The ladder really is inherited; what must not be inherited is the CLAIM to have
# measured it.  So the shared FACT (what the leg does) is one string and the
# ATTRIBUTION (whose evidence set it) is another, chosen by `definition`.
_ENTRY_BASIS_PROVENANCE_OWN = (
    f"{SELECTION_ERA}: the §6.6 US re-measurement read ADVERSE to the CN ordering at "
    "H=5 and H=10 and has no marks at all at H=21/H=63, so no ordering is claimed in "
    "either direction."
)
_ENTRY_BASIS_PROVENANCE_INHERITED = (
    f"{SELECTION_ERA}: this ladder is the US board's, flattened by the §6.6 US "
    "re-measurement (ADVERSE to the CN ordering at H=5 and H=10; no marks at all at "
    "H=21/H=63). This board INHERITS it structurally, by sharing the ranking module — "
    "no equivalent re-measurement has been run on this market's own episodes, and none "
    "is claimed here."
)


def ranking_block(
    rows: Iterable[Mapping[str, Any]],
    *,
    featured_cap: int = FEATURED_CAP,
    sector_cap: int = SECTOR_CAP,
    theme_asof: Any = None,
    definition: str = BOARD_DEFINITION,
    edge_reads: str = EDGE_READS_US,
    featured_requirements_extra: Sequence[str] = (),
) -> dict[str, Any]:
    """The artifact-disclosed ``ranking`` block — the score's own receipt.

    Everything a reader needs to reproduce the order is printed here: the weights,
    what each leg reads, the featured requirements, the explicit list of inputs that
    carry no score authority at all — and ``component_coverage``, the measured nonzero
    count per leg, so a leg that is dead on this board is visible in the artifact
    instead of inferable only from the weight table.

    ``definition`` / ``edge_reads`` / ``featured_requirements_extra`` are the market
    parameters (hk_prophet_v1 reuses this receipt verbatim apart from those three).
    The weights, the formula bases and the zero-authority list are SHARED — a
    sibling board that disclosed different weights would not be the same score.
    """
    scored = list(rows)
    counts = stage_counts(scored)
    # The ladder is shared; the evidence that set it is not.  A sibling market gets the
    # inherited-structurally wording, never the US re-measurement as its own basis.
    entry_provenance = (
        _ENTRY_BASIS_PROVENANCE_OWN if definition == BOARD_DEFINITION
        else _ENTRY_BASIS_PROVENANCE_INHERITED
    )
    return {
        "definition": definition,
        # Which SELECTION rule produced this board — the entry ladder and the featured
        # entry set.  Printed so a forward-ledger row is readable against the rule it
        # was made under rather than against today's constants.
        "selection_era": SELECTION_ERA,
        "score_kind": SCORE_KIND,
        "weights": dict(SCORE_WEIGHTS),
        "formula_points": [
            {"component": "signal", "points": SCORE_WEIGHTS["signal"],
             "reads": "confluence tier + freshness",
             "basis": "tier base T2 1.0 / T1 0.9 / T3 0.7; provisional −0.1; "
                      "cross 2 ticks old ×0.85"},
            {"component": "entry", "points": SCORE_WEIGHTS["entry"],
             "reads": "entry_signal.status",
             # Was "frozen status map, shared with the China board" — untrue since the
             # 2026-08-04 fork.  The VOCABULARY is shared; the VALUES are the US
             # board's own, and what they now say is that the order is UNKNOWN.  The
             # provenance clause is market-scoped (see above the function): a sibling
             # board inherits the ladder, never the measurement.
             "basis": "admissible statuses share one flat value ("
                      + " = ".join(ENTRY_NEUTRAL_STATUSES)
                      + f" = {ENTRY_NEUTRAL_VALUE}); the leg separates admissible from "
                      "non-admissible (buy_soon 0.8 · later 0.55 · await 0.45 · watch "
                      "0.4 · extended/topping/blocked/exit/avoid 0.0) and orders "
                      "nothing within the admissible set. Status vocabulary shared "
                      "with the China board, values are the US board's own. "
                      + entry_provenance
                      + " The flat level is 1.0, which keeps the attainable range at "
                      "0-100 and leaves confirmation-class scores unchanged against "
                      "the pre-era map; only the previously-underranked patience rows "
                      "lift"},
            {"component": "edge", "points": SCORE_WEIGHTS["edge"],
             "reads": edge_reads,
             "basis": "clip01((pctile − 0.25) / 0.75) — bottom quartile earns 0"},
            {"component": "runway", "points": SCORE_WEIGHTS["runway"],
             "reads": "own-history extension z (ext_z) / anti-chase flag",
             "basis": "1 − clip01(ext_z / 2.0); unknown extension earns 0"},
            {"component": "quality", "points": SCORE_WEIGHTS["quality"],
             "reads": "coiled / washout context",
             "basis": "coiled star 1.0 · coiled 0.8 · washout context 0.4"},
        ],
        # Measured nonzero coverage per leg, recomputed from `scored` every build —
        # never a frozen number. `runway` read {"nonzero": 0, "n": 71} while the
        # builder's extension panel mixed the equity and crypto calendars, and
        # {"nonzero": 68, "n": 71} on the same lane once it was split; the receipt
        # tracked both without an edit here, which is the whole point of recomputing it.
        "component_coverage": component_coverage(scored),
        "sort_key": "stage bucket, then priority score desc, then ticker",
        "stage_order": list(STAGE_ORDER),
        "stage_labels": {stage: dict(STAGE_LABELS[stage]) for stage in STAGE_ORDER},
        "stage_counts": counts,
        "featured_cap": max(0, int(featured_cap)),
        "sector_cap": max(0, int(sector_cap)),
        "featured_count": sum(1 for row in scored if row.get("featured")),
        # B3 disclosure, kept and still recomputed — how many rows the featured flag
        # refused for lack of an extension reading.  Since ANTICIPATION v1 (2026-08-08)
        # an unknown reading does not refuse anything, so on a current board this reads
        # 0.  That is ACCURATE and it is also no longer informative, which is why
        # `ext_unknown_coverage` sits directly below it: the count of rows with no
        # reading, and how many of them were featured anyway, is the fact a reader
        # needs.  The key stays so an artifact from either era can be read the same way
        # and so a re-introduced veto shows up here instead of silently.
        "featured_blocked_unknown_extension": sum(
            1 for row in scored
            if "ext_z_unknown" in (row.get("featured_blocked_by") or ())
        ),
        # The live extension-coverage receipt (ANTICIPATION v1), recomputed every
        # build.  `unknown == n` is the 2026-08-06 shape: the extension input is out
        # and every featured row's chase-risk check is running blind.
        "ext_unknown_coverage": ext_unknown_coverage(scored),
        "featured_requirements": [
            "stage is live",
            # Both lines are true and they bind together: the ladder admits the
            # patience statuses, the stage gate above still only passes `live`, and
            # `stage_for` routes bounce_wait/wait_pullback to `setting_up` and hold to
            # `ran`.  Printed as the pair rather than as one tidy sentence because a
            # reader comparing this board to CN's needs to see which of the two gates
            # is the binding one.
            "entry status is one of "
            + ", ".join(sorted(_FEATURED_ENTRY_STATUSES))
            + " (the patience statuses are admitted by the ladder but not yet by the "
              "stage gate above, so today only buy_now and partial can reach the "
              "shelf)",
            "confluence tier T1, T2 or T3",
            f"cross no older than {FEATURED_MAX_TICKS} ticks (a same-day cross, "
            "ticks 0, qualifies)",
            "verdict not provisional",
            "no anti-chase flag, and no extension reading ABOVE the parabolic line "
            f"(ext_z <= {EXT_Z_FULL}); an unknown reading qualifies and is disclosed "
            "on the row as ext_unknown rather than blocking the lane",
            "residual alpha at or above zero",
            "outside the earnings blackout window",
            f"at most {int(sector_cap)} per sector, {int(featured_cap)} on the board",
            *[str(item) for item in featured_requirements_extra],
        ],
        "zero_score_authority": list(ZERO_SCORE_AUTHORITY),
        "membership_note": "featured is a flag and an order — the buy lane's "
                           "membership is decided by the confluence admission gate "
                           "alone and is unchanged by this ranking",
        "theme_asof": _as_date(theme_asof),
    }


# --------------------------------------------------------------------------- #
# total-return momentum (the leaders lane's rank key)
# --------------------------------------------------------------------------- #
LEADERS_MOMENTUM_SESSIONS = 63    # ~3 months — the lane's own chartered window


def total_return_z(
    closes_by: Mapping[str, Sequence[Any]],
    *,
    sessions: int = LEADERS_MOMENTUM_SESSIONS,
) -> dict[str, float]:
    """Cross-sectional z-score of trailing TOTAL return over ``sessions`` sessions.

    This is the leaders lane's rank key, and it is deliberately NOT residual alpha
    and NOT the composite's ``momentum`` leg. Measured 2026-08-02 on the live board:
    ``corr(alpha, composite.legs.momentum) = 0.984`` — that leg is fed by
    ``alpha_pt[t]["alpha"]`` (scripts/build_stock_library.py, composite assembly), so
    ranking by it would be the residual-alpha rule under a new name, and the software
    cohort would stay invisible exactly as before. Trailing total return over the same
    universe correlates ``+0.37`` with residual alpha — a different quantity, which is
    the whole point: residual strips beta, and a theme rally is mostly beta.

    Window: 63 sessions, no skip-month. The classic 12-1 academic convention is the
    wrong instrument here (measured: it puts MSFT at the 13th percentile and PLTR at
    the 15th while the software theme was leading, because it deletes precisely the
    recent leg that names current leadership). 63 sessions is also this lane's own
    chartered universe — it was created on the 2026-07-28 finding that "of the top-100
    3-month runners, 2 passed the confluence gate".

    ``closes_by`` maps ticker to an oldest-first close sequence; only the last
    ``sessions + 1`` values are read, so callers should pass a tail, not a history.
    Names with too little history, a non-positive base price, or a degenerate
    cross-section are omitted — an absent reading is a skipped row, never a zero.
    """
    window = max(1, int(sessions))
    returns: dict[str, float] = {}
    for ticker, closes in (closes_by or {}).items():
        values = [v for v in (_finite_float(c) for c in (closes or [])) if v is not None]
        if len(values) < window + 1:
            continue
        base = values[-(window + 1)]
        if base <= 0:
            continue
        returns[str(ticker)] = values[-1] / base - 1.0

    if len(returns) < 2:
        return {}
    mean = sum(returns.values()) / len(returns)
    variance = sum((v - mean) ** 2 for v in returns.values()) / len(returns)
    sd = math.sqrt(variance)
    if not math.isfinite(sd) or sd <= 0:
        return {}
    return {ticker: round((value - mean) / sd, 4) for ticker, value in returns.items()}


# --------------------------------------------------------------------------- #
# theme linkage (display-tier context chips; zero score authority)
# --------------------------------------------------------------------------- #
def _default_data_dir() -> Path:
    try:  # pragma: no cover — trivial import shim
        from lib import config as _config

        return _config.data_dir()
    except Exception:  # noqa: BLE001 — engine modules must import standalone
        return Path(__file__).resolve().parents[1] / "data"


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001 — absent/unreadable/malformed all degrade the same
        return None


def load_theme_context(
    data_dir: Path | str | None = None,
    *,
    latest_path: Path | str | None = None,
    membership_path: Path | str | None = None,
    top_n: int = THEME_TOP_N,
) -> dict[str, Any]:
    """Load the in-favour theme map from the nightly baskets engine.

    Selection: drop the ``us_sector_*`` GICS pseudo-baskets (the card already prints
    the sector), keep themes whose ``reco`` is ``accumulate`` or ``enter``, order by
    the baskets engine's own ``rank`` and take the first ``top_n``.  A ticker that
    belongs to several in-favour themes is chipped with the highest-ranked one.
    Members carrying a ``removed`` date are dropped.

    Returns ``{"as_of", "themes", "by_ticker"}``.  Fail-soft by contract: a missing or
    malformed file yields empty structures plus one ``::notice`` line — a theme chip
    is context, and its absence must never fail a build.
    """
    root = Path(data_dir) if data_dir is not None else _default_data_dir()
    latest = Path(latest_path) if latest_path is not None else root / "baskets" / "latest.json"
    membership = (
        Path(membership_path) if membership_path is not None
        else root / "baskets" / "membership.json"
    )
    empty: dict[str, Any] = {"as_of": None, "themes": [], "by_ticker": {}}

    latest_doc = _read_json(latest)
    membership_doc = _read_json(membership)
    if not isinstance(latest_doc, Mapping) or not isinstance(membership_doc, Mapping):
        _notice("us_board_theme", "baskets snapshot unreadable — board ships without "
                                  "theme chips")
        return empty

    themes_raw = latest_doc.get("themes")
    baskets = membership_doc.get("baskets")
    if not isinstance(themes_raw, list) or not isinstance(baskets, Mapping):
        _notice("us_board_theme", "baskets snapshot malformed — board ships without "
                                  "theme chips")
        return empty

    in_favour: list[dict[str, Any]] = []
    for entry in themes_raw:
        if not isinstance(entry, Mapping):
            continue
        theme_id = str(entry.get("id") or "")
        if not theme_id or theme_id.startswith(THEME_ID_EXCLUDE_PREFIX):
            continue
        reco = str(entry.get("reco") or "").strip().lower()
        if reco not in THEME_IN_FAVOUR_RECOS:
            continue
        rank = _finite_int(entry.get("rank"))
        if rank is None:
            continue
        basket = baskets.get(theme_id)
        basket = basket if isinstance(basket, Mapping) else {}
        in_favour.append({
            "id": theme_id,
            "name": basket.get("name") or entry.get("name") or theme_id,
            "name_zh": basket.get("name_zh"),
            "rank": rank,
            "reco": reco,
            "bull_days": _finite_int(entry.get("bull_days")),
            "clean_entry": bool(entry.get("clean_entry")),
        })

    in_favour.sort(key=lambda theme: (theme["rank"], theme["id"]))
    in_favour = in_favour[: max(0, int(top_n))]
    if not in_favour:
        _notice("us_board_theme", "no in-favour themes in the baskets snapshot — "
                                  "board ships without theme chips")
        return {"as_of": _as_date(latest_doc.get("as_of")), "themes": [], "by_ticker": {}}

    by_ticker: dict[str, dict[str, Any]] = {}
    tickers_by_theme: dict[str, list[str]] = {}
    for theme in in_favour:
        basket = baskets.get(theme["id"])
        members = (basket or {}).get("members") if isinstance(basket, Mapping) else None
        owned: list[str] = []
        for member in members or []:
            if not isinstance(member, Mapping):
                continue
            if member.get("removed") is not None:
                continue
            ticker = str(member.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            owned.append(ticker)
            # Highest-ranked theme wins; in_favour is already rank-ordered.
            by_ticker.setdefault(ticker, dict(theme))
        tickers_by_theme[theme["id"]] = sorted(set(owned))

    for theme in in_favour:
        theme["tickers"] = tickers_by_theme.get(theme["id"], [])

    return {
        "as_of": _as_date(latest_doc.get("as_of")),
        "themes": in_favour,
        "by_ticker": by_ticker,
    }


def load_theme_map(
    data_dir: Path | str | None = None,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """Ticker → in-favour theme chip (see :func:`load_theme_context`)."""
    return load_theme_context(data_dir, **kwargs)["by_ticker"]


def theme_confirmed(theme: Mapping[str, Any] | None) -> bool:
    """True when the chipped theme's bull run is younger than the confirm window.

    The sector-clock / stock-clock desync read: a name whose own cross fired days ago
    looks stale, while the theme it belongs to only just turned.  Display-tier context
    only — it never enters the priority score and never changes admission.
    """
    bull_days = _finite_int((theme or {}).get("bull_days"))
    return bull_days is not None and bull_days <= THEME_CONFIRMED_MAX_BULL_DAYS


def stamp_themes(
    rows: Iterable[dict],
    theme_by: Mapping[str, Mapping[str, Any]] | None,
    *,
    confirmed_flag: bool = False,
) -> int:
    """Stamp ``row["theme"]`` from the ticker map; return how many rows were chipped."""
    if not theme_by:
        return 0
    stamped = 0
    for row in rows:
        theme = theme_by.get(str(row.get("ticker") or "").strip().upper())
        if not theme:
            continue
        row["theme"] = dict(theme)
        if confirmed_flag and theme_confirmed(theme):
            row["theme_confirmed"] = True
        stamped += 1
    return stamped


# --------------------------------------------------------------------------- #
# ran lane — names whose cross already fired, trend still intact
# --------------------------------------------------------------------------- #
RAN_LABEL = "RAN"
RAN_LABEL_ZH = "已启动"

# How a ran row's cross age was anchored.  Emitted on every ran row (`anchor`) so a
# consumer can tell an exact marker-dated age from a session-count reconstruction.
ANCHOR_MARKER = "marker"
ANCHOR_APPROX = "approx"
# ...and how its MOVE was anchored, when the caller supplies a `move_read`.  The date
# and the age stay the marker's under all three words; `confirm` says only that the
# move was measured from the close at which the marker's label first became knowable,
# which is the only anchor `signal_quality._buy_filter` permits a forward return to
# use.  See :func:`build_ran_rows`.
ANCHOR_CONFIRM = "confirm"
RAN_THEME_LINE = "Theme just confirmed — watch for the next entry"
RAN_THEME_LINE_ZH = "主题刚确认 — 关注下一个买点"


def ran_admits(verdict: Mapping[str, Any] | None, row: Mapping[str, Any] | None = None,
               *, ticks_min: int = RAN_TICKS_MIN, ticks_max: int = RAN_TICKS_MAX,
               require_above200: bool = True) -> bool:
    """Ran-lane admission: the cross has lapsed but the trend is provably intact.

    ``eligible is False`` (the gate no longer admits it) ∧ ``ticks`` inside the window
    ∧ ``above200`` ∧ ``weekly_bull`` ∧ the row is not marked down.  The ``is True``
    tests are deliberate: a ``None`` (unanalysed) trend must never read as intact.

    ``require_above200`` (keyword-only, DEFAULT True = unchanged US/CN behaviour)
    exists for the same reason ``signal_quality._buy_filter``'s ``reclaim_veto`` does,
    and it is the SECOND door the same impossible condition walked through. A name
    recovering from a 30-50% drawdown is BELOW its 200-day average by construction —
    that is what a deep drawdown IS — so requiring ``above200`` here excluded exactly
    the washout-bounce names this lane exists to show. Measured on the first
    hk_prophet_v2 board (2026-08-03): 1810.HK, 9988.HK, 2318.HK, 1093.HK and 0867.HK
    left the vetoed lane correctly (they are no longer blocked) and then landed on NO
    lane at all, because every lane that could have caught them tests ``above200``.
    With it False the lane still requires ``weekly_bull`` and not-marked-down, so the
    row is never claimed to be in an intact long-term uptrend — only that its cross
    fired, it has moved since, and the weekly structure is pointing up. The default
    stays True because the US/CN lanes were measured with it.
    """
    verdict = verdict or {}
    if verdict.get("eligible") is not False:
        return False
    ticks = _finite_int(verdict.get("ticks"))
    if ticks is None or not (int(ticks_min) <= ticks <= int(ticks_max)):
        return False
    if require_above200 and verdict.get("above200") is not True:
        return False
    if verdict.get("weekly_bull") is not True:
        return False
    if str((row or {}).get("dir") or "").strip().lower() == "down":
        return False
    return True


def cross_read(
    dates: Sequence[Any],
    closes: Sequence[Any],
    *,
    cross_date: Any = None,
    sessions_back: int | None = None,
) -> dict[str, Any] | None:
    """Move-since-the-cross read: ``{cross_date, sessions_since, pct_since, anchor}``.

    Two anchors, both on the DAILY session grid, and the read says which one it used:

    * ``anchor == "marker"`` — the last session at or before ``cross_date``, the
      signal's own §7 buy-marker date.  The China ran-lane idiom and the exact answer.
    * ``anchor == "approx"`` — ``sessions_back`` sessions before the last close, used
      when no marker date resolves inside the supplied series.

    ``sessions_back`` MUST be a count of daily SESSIONS.  Callers pass the verdict's
    ``fresh_bars`` (``engine.signal_gate._bars_since`` — daily bars strictly after the
    marker).  Passing ``ticks`` instead is the B3 defect this signature exists to
    prevent: ticks are counted on the signal's NATIVE higher-timeframe grid (one 3D
    tick ≈ 3 sessions), so ``sessions_back=ticks`` makes ``sessions_since == ticks`` —
    a ~3x understatement of the age, and it mis-anchors ``pct_since`` onto the wrong
    bar as well.  Measured on the 235-name local store: the marker path returns 29 / 40
    / 23 sessions where ticks read 11 / 15 / 9.

    Returns ``None`` when the supplied series cannot produce a reading at all — no
    anchor resolves inside it, it is too short, or the anchor bar's price is not
    positive.  That is a statement about THESE CLOSES, not about the row: the caller
    decides whether an anchor exists (see :func:`_anchor_only_read`) and drops the row
    only when the AGE would have to be invented — a missing row beats a wrong number,
    but a null move is a disclosed null and gets printed.
    """
    values: list[float] = []
    stamps: list[str | None] = []
    for stamp, close in zip(dates, closes):
        number = _finite_float(close)
        if number is None:
            continue
        values.append(number)
        stamps.append(_as_date(stamp))
    if len(values) < 2:
        return None

    anchor: int | None = None
    kind = ANCHOR_MARKER
    anchor_date = _as_date(cross_date)
    if anchor_date:
        for index in range(len(stamps) - 1, -1, -1):
            stamp = stamps[index]
            if stamp is not None and stamp <= anchor_date:
                anchor = index
                break
    if anchor is None:
        kind = ANCHOR_APPROX
        back = _finite_int(sessions_back)
        if back is None or back < 0:
            return None
        anchor = len(values) - 1 - back
        if anchor < 0:
            return None

    price_at_cross = values[anchor]
    spot = values[-1]
    if price_at_cross <= 0:
        return None
    return {
        "cross_date": stamps[anchor],
        "sessions_since": len(values) - 1 - anchor,
        # pct_since is measured from the SAME bar the age is measured from, on both
        # paths — the age and the move must never describe different anchors.
        "pct_since": round((spot / price_at_cross - 1.0) * 100.0, 1),
        "anchor": kind,
    }


def _anchor_only_read(cross_date: Any, fresh_bars: Any) -> dict[str, Any]:
    """The cross read a row can still give with NO usable close series: age, no move.

    ``fresh_bars`` is counted on the daily grid inside :mod:`engine.signal_gate`, so
    the AGE never needed this lane's copy of the closes — only ``pct_since`` did.  A
    row with a real anchor and no prices therefore keeps its age and its anchor and
    prints ``pct_since: None``.

    That null is a DISCLOSED null (house epistemics: print it, don't hide the row),
    and it is a different thing from a wrong age — which is why the drop in
    :func:`build_ran_rows` keys on whether an anchor SOURCE exists and never on
    whether prices arrived.
    """
    stamp = _as_date(cross_date)
    bars = _finite_int(fresh_bars)
    return {
        "cross_date": stamp,
        "sessions_since": bars if (bars is not None and bars >= 0) else None,
        "pct_since": None,
        # fresh_bars is measured FROM the buy marker, so an age that came from it is
        # marker-anchored whenever we also hold the marker's date.
        "anchor": ANCHOR_MARKER if stamp else ANCHOR_APPROX,
    }


def build_ran_rows(
    verdict_by: Mapping[str, Mapping[str, Any]],
    *,
    meta_by: Mapping[str, Mapping[str, Any]] | None = None,
    close_of: Callable[[str], tuple[Sequence[Any], Sequence[Any]] | None] | None = None,
    exclude: Iterable[str] = (),
    theme_by: Mapping[str, Mapping[str, Any]] | None = None,
    board_asof: Any = None,
    cap: int | None = RAN_CAP,
    ticks_min: int = RAN_TICKS_MIN,
    ticks_max: int = RAN_TICKS_MAX,
    move_read: Callable[[Any, Any], Mapping[str, Any] | None] | None = None,
    require_above200: bool = True,
) -> list[dict]:
    """Build the ran lane: crossed days ago, trend intact, no entry claim attached.

    "TREND INTACT" IS POLICY-DEPENDENT.  Under the default it means ``above200`` ∧
    ``weekly_bull``; a board passing ``require_above200=False`` (HK, 2026-08-04) keeps
    the weekly leg only — see :func:`ran_admits` for why, and note that the lane's
    user-facing copy claims nothing stronger than "the move already started" either
    way, so the relaxed policy introduces no surface claim the rows cannot support.

    These are DISPLAY-TIER context rows.  They carry no ``entry_signal``, no
    conviction claim and no priority score — the honest read is "the move already
    started; wait for the next entry", which is why they cannot outrank a live row.

    FAIL-CLOSED AGE (B3, 2026-08-02).  The row's AGE is the thing that must never be
    invented.  The anchor is the §7 buy-marker date, falling back to the verdict's
    ``fresh_bars`` session count; the previous fallback was the raw ``ticks`` count,
    which made ``sessions_since == ticks`` — the age understated ~3x (measured: 29/40/23
    true sessions shown as 11/15/9) — and it anchored ``pct_since`` on the wrong bar
    with it.  A row with NEITHER a marker date NOR a usable ``fresh_bars`` is DROPPED,
    because any age it could show would be fabricated: measured on the 235-name local
    store, 25 of 55 ran admits (45%) carry a sell/cut as their last marker and so have
    no cross date at all.  Every emitted row therefore carries ``anchor`` ∈
    {``marker``, ``approx``} and an age that is either exact or absent — never wrong.

    A missing PRICE SERIES is a different question and does not drop the row.  The age
    lives in the verdict, not in this lane's closes, so such a row still states when
    the cross fired and prints ``pct_since: None`` — a disclosed null, per the house
    rule that nulls are printed rather than hidden.

    Order: theme-confirmed rows first (their theme only just turned, so the desync is
    the point), then the freshest cross, then the largest move since it fired.

    ``move_read(series, marker_date) -> {pct_since, measured_from} | None`` REPLACES
    the move — and only the move; the date, the age and the drop rules are untouched.
    It exists because ``cross_read``'s marker anchor is the one
    ``signal_quality._buy_filter`` forbids for a forward return: ``marker['date']`` is
    a 3B bucket's LEFT edge whose label reads two buckets forward, so it precedes the
    close at which the signal was knowable by ~8 sessions and sits at the trough that
    created it.  MEASURED on the HK ran lane, 2026-07-31: every one of the 12 displayed
    rows overstated, mean +8.09pp, worst 3690.HK at +29.2% against +10.9% from the
    confirmation close.  The hook rather than an unconditional change because the move
    is also the lane's third sort key — re-anchoring after the sort would order and
    truncate the lane by a number it no longer prints — and because the US board's
    identical exposure has not been measured yet, so it keeps the old read and the old
    row shape byte-for-byte until it has.  Passing it adds ``measured_from``; omitting
    it changes nothing.  ⚠ THE US BOARD STILL CARRIES THIS DEFECT.
    """
    skip = {str(t or "").strip().upper() for t in exclude}
    meta_by = meta_by or {}
    rows: list[dict] = []
    dropped_no_anchor = 0

    for ticker, verdict in (verdict_by or {}).items():
        key = str(ticker or "").strip().upper()
        if not key or key in skip:
            continue
        meta = meta_by.get(ticker) or meta_by.get(key) or {}
        if not ran_admits(verdict, meta, ticks_min=ticks_min, ticks_max=ticks_max,
                          require_above200=require_above200):
            continue

        ticks = _finite_int((verdict or {}).get("ticks"))
        marker = (verdict or {}).get("last") or {}
        marker_date = (marker.get("date")
                       if marker.get("type") in ("buy", "rebuy") else None)
        # fresh_bars, NOT ticks: the session count on the DAILY grid the closes series
        # is indexed by.  ticks live on the signal's native 2D/3D grid (~3 sessions
        # each), which is what made the old fallback understate the age ~3x.
        fresh = _finite_int((verdict or {}).get("fresh_bars"))
        if fresh is not None and fresh < 0:
            fresh = None
        if not _as_date(marker_date) and fresh is None:
            # No anchor SOURCE at all — the age would have to be invented. Fail closed.
            dropped_no_anchor += 1
            continue

        series = close_of(ticker) if close_of is not None else None
        read: dict[str, Any] | None = None
        if series is not None:
            dates, closes = series
            read = cross_read(dates, closes, cross_date=marker_date,
                              sessions_back=fresh)
        if read is None:
            # Anchored, but these closes cannot measure the move (absent, too short,
            # or the anchor bar falls outside the tail we hold). Age yes, move null.
            read = _anchor_only_read(marker_date, fresh)

        theme = (theme_by or {}).get(key)
        sig_date = signal_asof(meta, verdict)
        move = None
        if move_read is not None and read["anchor"] == ANCHOR_MARKER:
            move = move_read(series, marker_date)
        row: dict[str, Any] = {
            "ticker": key,
            "name": meta.get("name") or key,
            "sector": meta.get("sector"),
            "price": meta.get("price"),
            "ticks": ticks,
            "cross_date": read["cross_date"],
            "sessions_since": read["sessions_since"],
            "pct_since": (move["pct_since"] if move else
                          None if move_read is not None else read["pct_since"]),
            "anchor": (ANCHOR_CONFIRM if move else read["anchor"]),
            "stage": STAGE_RAN,
            "lane": "ran",
            "label": RAN_LABEL,
            "label_zh": RAN_LABEL_ZH,
            "signal_asof": sig_date,
        }
        # Same session-first resolver the buy lane uses, so one field means one thing
        # across both arrays of the artifact.
        row["days_since_signal"], row["days_since_signal_basis"] = signal_age(
            verdict, sig_date, board_asof)
        if move_read is not None:
            # Only the boards that asked for a confirmation read carry the field, so
            # the US row shape is unchanged for every consumer that did not.
            row["measured_from"] = move["measured_from"] if move else None
        if meta.get("spark_svg"):
            row["spark_svg"] = meta["spark_svg"]
        if theme:
            row["theme"] = dict(theme)
            if theme_confirmed(theme):
                row["theme_confirmed"] = True
                row["theme_note"] = RAN_THEME_LINE
                row["theme_note_zh"] = RAN_THEME_LINE_ZH
        rows.append(row)

    if dropped_no_anchor:
        _notice("us_board_ran_anchor",
                f"{dropped_no_anchor} ran-lane admit(s) dropped — no buy-marker date "
                f"and no fresh_bars, so the cross age is unknowable; a missing row "
                f"beats a wrong age ({len(rows)} row(s) kept)")

    rows.sort(
        key=lambda row: (
            0 if row.get("theme_confirmed") else 1,
            row.get("ticks") if row.get("ticks") is not None else 10**6,
            -(row.get("pct_since") if row.get("pct_since") is not None else -10.0**6),
            row["ticker"],
        )
    )
    # cap=None means UNCAPPED — the caller intends to apply its own selection to the
    # full admitted set (engine.hk_board_rank._cohort_first does exactly this, because
    # a plain freshest-first truncation drops the very names a reader came to check).
    if cap is None:
        return rows
    return rows[: max(0, int(cap))]
