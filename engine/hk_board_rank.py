"""HK Prophet v1 — the US priority engine, parameterised for the Hong Kong board.

Program: ``research/HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md`` (gates G1-G8).
Machinery: :mod:`engine.us_board_rank` (``us_prophet_v1``).  This module holds the
HK PARAMETERS and the two-and-a-half HK-specific lanes; it does not re-implement
the score.  Weights, the tier/entry maps, the stage buckets, the featured cascade,
the percentile transform, the freshness resolver and the ran-lane anchor discipline
are all IMPORTED, so the two boards cannot silently drift apart — a re-tune of
``SCORE_WEIGHTS`` moves both, which is the point (one scoring language, two markets).

WHAT IS ACTUALLY DIFFERENT HERE, and why:

1. ``edge`` reads the FUSED HK EDGE, not ``row["alpha"]``.  The leg's charter is
   "the selection axis" — the quantity a market's own measurement found
   positive-IC.  The US spells that ``alpha`` (residual alpha).  HK does not: the
   HK board's selection axis is ``edge_z``, the regime-weighted fusion of southbound
   flow, A/H value and beta-neutral relative strength (``engine.hk_stock_signals.hk_edge``,
   landed in the ``stock_score`` selection slot by the builder).  ``row["alpha"]`` on
   an HK row is a DIFFERENT quantity — the raw trailing-3-month total-return z — and
   it is what the LEADERS lane ranks on.  Pointing ``edge`` at it would collapse the
   buy lane and the leaders lane onto one number and delete the distinction G2 exists
   to draw.  See :func:`selection_value`.

2. ``featured`` carries a TURNOVER floor (:data:`FEATURED_MIN_ADV_HKD`).  The US
   board inherits its liquidity hygiene upstream; the HK universe spans a 250x
   turnover range (measured 2026-07-31 across the 158 names carrying a reading:
   5th percentile HK$7.3m/day, median HK$248m), so a promotion flag with no
   turnover test can feature a name a reader cannot get filled in.  Fail-closed:
   an unknown turnover is ``adv_unknown``, never a pass.

3. Three lanes the US board keeps in its builder or does not have at all live here
   as tested functions: :func:`build_leaders_rows` (G2), :func:`build_ran_rows`
   (G3, a thin HK wrapper over the shared implementation) and
   :func:`build_vetoed_rows` (G1/G6 — see below).

THE VETOED LANE, and why it exists (read before deleting it).  MEASURED on the
committed 2026-07-31 close panel: of the seven names the operator named as missing,
a FAITHFUL port of the US lanes surfaces exactly TWO (9618.HK in leaders+ran,
3690.HK in ran).  The other five are not borderline — they sit 10-26% BELOW their
own 200-day averages and 29-52% off their 52-week highs, so every intact-trend gate
rejects them correctly.  They are nonetheless the names a reader looks for, and each
one carries a signal the board FIRED and then BLOCKED: ``last.quality == "block"``,
reason ``"counter-trend, no 200-reclaim/hold"``.  The vetoed lane prints exactly
that — the blocked marker, how long the veto has stood, and what the name did since —
which is the masterplan's G6 instruction ("ship display-tier relief first: make
blocked names VISIBLE with the blocking reason named") and, bluntly, the veto's own
receipt.  It is the lane that shows what the board MISSED, so it must not be quietly
dropped when it reads badly; that is when it is doing its job.

FENCES.
* ``hk_leadership`` is DISPLAY-TIER (HKRV-R5).  Its cohort may boost the LEADERS
  lane's order and chip any lane, and it orders the vetoed lane.  It never touches
  rank, size or gate on the GRADED buy lane — :func:`score_rows` cannot see it.
* Nothing here changes MEMBERSHIP of the buy lane.  The confluence cascade is still
  the only admission gate; this module adds fields and decides ORDER.
* The 200-day veto itself is NOT touched.  G6 routes any change to it through a
  pre-registered measurement, and a lane that made blocked names visible by loosening
  the gate that blocked them would have measured nothing.
"""
from __future__ import annotations

from statistics import median as _median
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

from engine import us_board_rank as _ubr
from engine.us_board_rank import (  # noqa: F401 — shared vocabulary, re-exported by design
    ANCHOR_APPROX,
    ANCHOR_CONFIRM,
    ANCHOR_MARKER,
    BASIS_CALENDAR,
    BASIS_SESSIONS,
    SCORE_KIND,
    SCORE_WEIGHTS,
    STAGE_BASING,
    STAGE_BLOCKED,
    STAGE_LABELS,
    STAGE_LIVE,
    STAGE_ORDER,
    STAGE_RAN,
    STAGE_SETTING_UP,
    ZERO_SCORE_AUTHORITY,
    component_coverage,
    cross_read,
    days_since_signal,
    entry_value,
    is_downtrend,
    ran_admits,
    signal_age,
    signal_asof,
    signal_value,
    stage_counts,
    stage_for,
    stage_rank,
    stamp_themes,
    total_return_z,
)
from engine.us_board_rank import _as_date, _finite_float, _finite_int, _notice

# v2 (operator ruling 2026-08-03): ADMISSION changed — HK stopped requiring the 2-bar
# 200-day reclaim (`signal_gate.gate(..., reclaim_veto=False)`; see
# engine.signal_quality._buy_filter for why that leg was unsatisfiable-by-construction on
# this tape). An admission change makes v1 and v2 two different products, so the stamp
# moves and the ledger scopes to the newest definition — exactly the fence that keeps the
# v1 forward record readable instead of silently pooled with a board that admits more.
BOARD_DEFINITION = "hk_prophet_v2"

# Board shape.  Caps are HK's own (masterplan §0 G4): a 156-name universe against
# the US 1579, so the same 12/4 pair is a proportionally much wider net here.
FEATURED_CAP = 12
SECTOR_CAP = 4
RAN_CAP = 12
RAN_TICKS_MIN = _ubr.RAN_TICKS_MIN
RAN_TICKS_MAX = _ubr.RAN_TICKS_MAX

# Featured turnover floor: 63-day average dollar turnover, HK$.  Not a fitted
# number — it is the conventional institutional "can I get filled" line, and it
# clears the untradeable tail without pruning the board (measured 2026-07-31:
# 143 of the 158 names carrying a reading sit above it).
FEATURED_MIN_ADV_HKD = 30_000_000.0

# ---- leaders lane (G2) ----------------------------------------------------- #
LEADERS_CAP = 15
LEADERS_OFF_HIGH_FLOOR = -20.0
LEADERS_MOMENTUM_SESSIONS = _ubr.LEADERS_MOMENTUM_SESSIONS   # 63 — one quarter
# Rank credit for membership of the mega-cap cohort the leadership organ tracks.
# Same 0.5 the US lane gives a top-8 in-favour basket, and the same authority:
# a DISPLAY lane's tiebreak, never a score and never an admission.
LEADERSHIP_BOOST = 0.5
LEADERS_STANCE = "watch — don't chase"
LEADERS_STANCE_ZH = "观察 — 不要追高"

# ---- ran lane (G3) --------------------------------------------------------- #
# The shared lane stamps `label` RAN and buckets to the "Ran — don't chase" stage;
# what it does not carry is a STANCE — the plain-word "so what do I do" line G1
# requires on every surfaced name.  Added here rather than in the shared module so
# the US board's row shape is untouched.
RAN_STANCE = "the move already started — wait for the next entry"
RAN_STANCE_ZH = "行情已经启动 — 等待下一个买点"

# ---- vetoed lane (G1 / G6) ------------------------------------------------- #
VETOED_CAP = 12
# One quarter of sessions — the same window the momentum leg reads.  A veto that
# has stood longer than a quarter is no longer news about the current tape.
VETOED_MAX_SESSIONS = 63
VETOED_STANCE = "blocked — the board did not act on this"
VETOED_STANCE_ZH = "受阻 — 看板未据此操作"
VETOED_LABEL = "BLOCKED"
VETOED_LABEL_ZH = "受阻"
# `ANCHOR_CONFIRM` is imported from the shared vocabulary above: it is the third
# anchor word, and the only one either HK lane's MOVE may carry.  `marker` and
# `approx` keep their meaning exactly — they describe the DATE and the AGE, which are
# still the marker's — but a row anchored on either prints no move at all.  See
# :func:`build_vetoed_rows`; the split is what makes a marker-anchored `pct_since`
# unreachable from these lanes rather than merely discouraged.
# Marker qualities that mean "a buy signal fired and the gate refused it".
_VETOED_QUALITIES = frozenset(("block",))
_BUY_MARKERS = frozenset(("buy", "rebuy"))

# Plain-word reason copy.  The verdict's own `reason` strings are internal
# vocabulary ("counter-trend, no 200-reclaim/hold"); the glance tier gets these
# instead, and the raw string rides along as `reason_raw` for the detail view.
#
# ONLY BLOCK REASONS BELONG IN THIS MAP.  :func:`veto_reason_copy` is called from
# exactly one place — :func:`build_vetoed_rows`, which admits ``quality == "block"``
# only — so a key for a take/pending reason would be unreachable copy that no
# surface can render, and a test asserting its wording would be pinning dead code.
# The complete block set `_buy_filter` can emit is the four keys below.
#
# WHY TWO KEYS SHARE ONE SENTENCE.  Read `engine.signal_quality._confirm_legs`: both
# "failed next-bar hold" (the hk_prophet_v2 counter-trend branch, reclaim_veto=False)
# and the legacy "failed reclaim-and-hold" (the FINAL branch, reached whenever the name
# is NOT both below-200 and weekly-down) resolve on ONE test — ``held = c.iloc[i+1] >
# c.iloc[i]`` on the 3D signal frame.  Neither evaluates a 200-day reclaim at all,
# so the same sentence is the whole truth for both.
#
# ⚠ "failed reclaim-and-hold" WAS A MISLEADING ENGINE STRING — and as of 2026-08-04 the
# engine no longer emits it.  It used to render as "Reclaimed the 200-day average, then
# lost it again", narrating a 200-day round trip its branch never measured, on a name
# that may never have been near its 200-day line.  The copy was fixed first (2026-08-03)
# and the literal deliberately left alone, because renaming it changes US/CN §7 marker
# bytes to fix a copy defect.  `research/cn_prophet_audit/CN_RECLAIM_HOLD_AUDIT.md`
# §10/§11 then MEASURED the cost of leaving it: 1,094 blocks in the audit year named a
# reclaim that never ran, and 002155.SZ — 5.2% ABOVE its 200-day mean at its buy bar —
# was misread by two separate investigations because of it.  The main branch now emits
# `HOLD_FAIL`, the literal that was already correct for the identical one-test outcome.
#
# THE KEY STAYS ANYWAY.  Rows stamped before that change still carry the old string in
# the PIT candidate stores, the graded ledgers and already-rendered signal files, and
# this map is what turns a stored reason into a sentence.  Deleting the key would blank
# the copy on every historical vetoed row.  It is a RETIRED key, not a dead one.
#
# UNITS: the confirmation bar is a 3-DAY bar, not a session — `signal_frame`
# resamples to "3B" before the filter reads i+1.  The copy says "3-day bar" for
# that reason; "the next session" would be the same species of small false narrative
# this entry exists to remove.
_NEXT_BAR_HOLD_COPY = {
    "en": "The next 3-day bar closed lower, so the entry never confirmed",
    "zh": "信号后的下一根 3 日K线收低，入场未获确认",
}
VETO_REASON_COPY: dict[str, dict[str, str]] = {
    # Both legs ran and both refused: no reclaim AND no hold.  The only shape that
    # still earns the legacy sentence — 58.0% of the rows that used to carry it.
    "counter-trend, no 200-reclaim/hold": {
        "en": "Price never held above its 200-day average after the signal",
        "zh": "信号出现后股价未能站稳 200 日均线之上",
    },
    # The other two shapes of the same branch, split out 2026-08-04 so a reader is told
    # WHICH leg refused.  40.2% of the legacy rows are these — the ones a reclaim-rule
    # change would actually relieve — and 1.8% are the inverse.
    "counter-trend, held but no 200-reclaim": {
        "en": "The 3-day bar after the signal held, but price never reclaimed its "
              "200-day average",
        "zh": "信号后的 3 日K线守住，但股价始终未收复 200 日均线",
    },
    "counter-trend, reclaimed 200 but no next-bar hold": {
        "en": "Price reclaimed its 200-day average, but the next 3-day bar closed lower",
        "zh": "股价收复 200 日均线，但下一根 3 日K线收低",
    },
    # The reason `reclaim_veto=False` (hk_prophet_v2) made common.  Without this
    # entry the rows fell through to VETO_REASON_FALLBACK: 10 of the 12 vetoed rows
    # on the first v2 board rendered the contentless "The entry gate refused this
    # signal", which tells a reader nothing at all.  It is now ALSO what the main
    # branch emits, so one sentence covers every hold-only block on every market.
    "failed next-bar hold": dict(_NEXT_BAR_HOLD_COPY),
    "failed reclaim-and-hold": dict(_NEXT_BAR_HOLD_COPY),   # RETIRED — historical rows
    "veto: bearish divergence": {
        "en": "Momentum was already fading as the signal fired",
        "zh": "信号出现时动能已在衰减",
    },
}

# Keys the engine NO LONGER EMITS but stored rows still carry.  A vetoed row is rendered
# from whatever reason was stamped on it, so a retired key must keep its sentence or every
# historical row loses its copy — while an UNRETIRED key that the engine cannot emit is a
# dead entry whose wording no surface can show.  Declaring the difference here is what lets
# the reachability guard keep catching the second case
# (tests/test_hk_v2_reason_copy_and_ran_lane.py).  Add a key here ONLY with the commit that
# stops the engine emitting it.
RETIRED_VETO_REASONS = frozenset({
    # Retired 2026-08-04: the main branch tests the next-bar hold alone and now says so.
    # research/cn_prophet_audit/CN_RECLAIM_HOLD_AUDIT.md §11 — 1,094 blocks carried this
    # string for a reclaim test that never ran.
    "failed reclaim-and-hold",
})
VETO_REASON_FALLBACK = {
    "en": "The entry gate refused this signal",
    "zh": "入场闸门未放行该信号",
}


# --------------------------------------------------------------------------- #
# the HK selection axis
# --------------------------------------------------------------------------- #
def selection_value(row: Mapping[str, Any]) -> Any:
    """The HK board's selection-axis reading for the ``edge`` leg.

    Resolution order, and every step is the SAME quantity seen from a different
    place rather than a widening fallback:

    1. ``edge_z`` — the fused ``hk_edge`` z the builder stamps on the row.
    2. ``conviction.axes.selection.z`` — where the conviction profile publishes the
       very same number (verified equal on the live 2026-07-31 board: 0.13/0.55/
       0.84/1.11 on both paths for every row checked).  Read second so a row that
       carries the profile but lost the flat field still scores.
    3. ``alpha`` — the trailing-3-month total-return z, used ONLY when no HK-native
       leg resolved at all.  This is the builder's own documented fallback
       (``sel_z = ed.get("z") if ed.get("z") is not None else e["alpha"]``), so
       reading it here keeps the leg consistent with the axis it is scoring.

    Returns ``None`` when nothing resolves — and ``None`` earns zero, never a
    mid-pool default (the shared fail-closed rule).
    """
    edge_z = _finite_float(row.get("edge_z"))
    if edge_z is not None:
        return edge_z
    axes = ((row.get("conviction") or {}).get("axes") or {})
    axis_z = _finite_float((axes.get("selection") or {}).get("z"))
    if axis_z is not None:
        return axis_z
    return _finite_float(row.get("alpha"))


def laggards_key(row: Mapping[str, Any]) -> float:
    """The laggards sort key — the SELECTION axis alone (G5).

    THE DEFECT THIS REPLACES (measured on the committed 2026-07-31 board): laggards
    were ordered by ``conviction.composite_z``, a DISPLAY roll-up that averages the
    selection axis together with the ENTRY axis.  Entry z is an extension/timing
    read, so a name that has already run scores deeply negative on it — and a name
    that has run BECAUSE its selection edge is working is exactly the name the
    composite then buries.  Four of the six shipped laggards had a POSITIVE
    selection reading: 3690.HK (Meituan) selection +0.55 / entry −1.25, ranked 4th
    WORST of 156 in the middle of a +44% run; 9618.HK +0.84 / −1.68; 0992.HK
    +1.11 / −2.36; 0019.HK +0.53 / −2.88.

    "Laggard" is a claim about the SELECTION axis — this name's edge is weak — and
    nothing else.  Reading the axis directly makes a Meituan-shaped row (selection
    above zero, entry far below) structurally unable to enter the lane, because the
    entry axis is no longer part of the key at any weight.

    An unresolvable selection axis sorts LAST (``+inf``), not first: an unknown edge
    is not evidence of a weak one, and fail-closed here means "do not accuse".
    """
    value = _finite_float(selection_value(row))
    return value if value is not None else float("inf")


def featured_shortfalls_extra(
    adv_by: Mapping[str, Any] | None = None,
    *,
    min_adv: float = FEATURED_MIN_ADV_HKD,
) -> Callable[[Mapping[str, Any]], list[str]]:
    """Build the HK-specific featured veto: a 63-day dollar-turnover floor.

    Reads ``adv_by[ticker]`` first (the builder's ``_adv63_map``), then the row's own
    turnover.  An absent or unreadable turnover yields ``adv_unknown`` — featured is
    a PROMOTION, and unknown evidence never earns the best case.

    THE ROW-LEVEL KEY IS ``_adv63``, not ``adv63``.  The builder stamps
    ``e["_adv63"] = adv63.get(...)`` (scripts/build_hk_library.py, the ripe-list
    tiebreak), so the old ``row.get("adv63")`` fallback could never fire on a
    production row — it read a key nothing writes, and every map miss went straight
    to ``adv_unknown`` while a perfectly good number sat on the row.  Both spellings
    are accepted now; the map stays primary.
    """
    lookup = adv_by or {}

    def _extra(row: Mapping[str, Any]) -> list[str]:
        ticker = str(row.get("ticker") or "").strip()
        adv = _finite_float(lookup.get(ticker))
        if adv is None:
            adv = _finite_float(row.get("_adv63"))
        if adv is None:
            adv = _finite_float(row.get("adv63"))
        if adv is None:
            return ["adv_unknown"]
        if adv < float(min_adv):
            return ["adv_below_floor"]
        return []

    return _extra


# --------------------------------------------------------------------------- #
# the scoring pass (shared machinery, HK parameters)
# --------------------------------------------------------------------------- #
def score_rows(
    rows: Iterable[dict],
    *,
    verdict_by: Mapping[str, Mapping[str, Any]] | None = None,
    entry_by: Mapping[str, Mapping[str, Any]] | None = None,
    blackout_by: Mapping[str, bool] | None = None,
    adv_by: Mapping[str, Any] | None = None,
    board_asof: Any = None,
    featured_cap: int = FEATURED_CAP,
    sector_cap: int = SECTOR_CAP,
    bottom_watch_stage: str = _ubr.STAGE_BLOCKED,
) -> list[dict]:
    """Score, stage, feature and order the HK buy pool.

    Delegates wholesale to :func:`engine.us_board_rank.score_rows` with the HK
    definition stamp, the HK selection axis and the HK turnover veto.  Rows are
    stamped in place and returned in ``(stage, −score, ticker)`` order.

    MEMBERSHIP IS UNTOUCHED — byte-identically so.  The caller hands this function
    the pool the confluence cascade already admitted, in whatever order; this
    function adds fields and re-orders.  It never adds, drops or re-filters a row.

    ``bottom_watch_stage`` names the bucket the cycle ladder's BOTTOM WATCH state
    routes to.  It defaults to ``STAGE_BLOCKED`` — the behaviour every caller had
    before the basing shelf existed — so a board whose template has no basing shelf
    keeps rendering byte-identically; the HK builder passes ``STAGE_BASING`` (see
    :func:`engine.us_board_rank.stage_for`).  DISPLAY-TIER ONLY: it decides which
    shelf a row renders under, never membership, never score, never who is featured.

    THE HK TRUTH, so nobody reads this as a population claim.  The HK pool is
    CASCADE-GATED — ``scripts/build_hk_library.py`` hands this function only the
    names ``hk_cascade_eligible`` admitted — so a pre-signal BOTTOM WATCH row is
    structurally rare here in a way it is not on the US board: MEASURED ZERO across
    all 14 committed board snapshots (2026-07-20..08-04).  The parameter exists so
    the HK surface speaks the same five-bucket language as the US one, and so the day
    the cycle ladder and the confluence cascade DO disagree, the row lands on a
    labelled shelf instead of falling through the template's catch-all — which
    renders an unknown stage LAST, below Blocked, the worst place for it.
    """
    return _ubr.score_rows(
        rows,
        verdict_by=verdict_by,
        entry_by=entry_by,
        blackout_by=blackout_by,
        board_asof=board_asof,
        featured_cap=featured_cap,
        sector_cap=sector_cap,
        definition=BOARD_DEFINITION,
        alpha_of=selection_value,
        featured_extra=featured_shortfalls_extra(adv_by),
        bottom_watch_stage=bottom_watch_stage,
    )


def ranking_block(
    rows: Iterable[Mapping[str, Any]],
    *,
    featured_cap: int = FEATURED_CAP,
    sector_cap: int = SECTOR_CAP,
    theme_asof: Any = None,
    min_adv: float = FEATURED_MIN_ADV_HKD,
) -> dict[str, Any]:
    """The artifact-disclosed ``ranking`` receipt for the HK board."""
    block = _ubr.ranking_block(
        rows,
        featured_cap=featured_cap,
        sector_cap=sector_cap,
        theme_asof=theme_asof,
        definition=BOARD_DEFINITION,
        edge_reads="fused HK edge percentile inside this buy pool "
                   "(southbound flow · A/H value · beta-neutral relative strength)",
        featured_requirements_extra=[
            f"63-day average turnover at or above HK${int(min_adv):,} "
            "(an unknown turnover does not qualify)",
        ],
    )
    # The HK board's own disclosure: which lanes are graded and which are context.
    block["display_tier_lanes"] = list(DISPLAY_TIER_LANES)
    block["leadership_authority"] = (
        "the mega-cap leadership cohort orders and chips the display lanes only — "
        "it carries no rank, size or gate authority on the buy lane"
    )
    return block


# Lanes that carry NO entry claim and no priority score.  Named in the artifact so
# a consumer cannot mistake a context strip for a graded call.
DISPLAY_TIER_LANES = ("leaders", "ran", "vetoed")


# --------------------------------------------------------------------------- #
# leadership cohort context (display-tier; HKRV-R5)
# --------------------------------------------------------------------------- #
def leadership_chip(leadership: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The cohort chip payload attached to a cohort member's row.

    ``leadership`` is the ``engine.hk_leadership.compute`` snapshot the builder
    already holds.  Returns ``None`` when the organ did not run — a chip is context,
    and its absence must never fail a lane.
    """
    if not isinstance(leadership, Mapping):
        return None
    state = str(leadership.get("state") or "").strip()
    if not state:
        return None
    cohesion = _finite_float(leadership.get("cohesion_now"))
    breadth = _finite_float(leadership.get("broad_breadth_pct"))
    participating = state == "leaders_participating"
    return {
        "id": "hk_leadership",
        "name": "Mega-cap cohort",
        "name_zh": "大型股群体",
        "state": state,
        # Plain words at the glance tier; the raw state string stays for the detail
        # view.  "leaders_participating" is an internal slug and never renders.
        "state_en": ("Mega-caps moving together" if participating
                     else "Mega-caps not moving together"),
        "state_zh": ("大型股同步走强" if participating else "大型股尚未同步"),
        "cohesion_now": cohesion,
        "broad_breadth_pct": breadth,
        "breadth_confirming": bool(leadership.get("breadth_confirming")),
        "display_only": True,
    }


def stamp_leadership_chips(
    rows: Iterable[MutableMapping[str, Any]],
    leadership: Mapping[str, Any] | None,
    *,
    cohort: Iterable[str] | None = None,
) -> int:
    """Attach the cohort chip to every row whose ticker is in the cohort.

    THE BUY CARDS WERE THE ONLY SURFACE MISSING IT.  ``build_leaders_rows`` chips a
    cohort member on the strip, and the card template already reads ``leadership``
    first — but nothing stamped it on the buy rows, so a mega-cap that made the buy
    lane lost the very context the strip prints two sections lower for the same name.

    Display-only, by charter: the chip carries no rank, size or gate authority on the
    graded lane (masterplan §3's hk_leadership fence).  Returns the number of rows
    chipped; zero when the organ did not run, which must never fail a render.
    """
    chip = leadership_chip(leadership)
    if not chip:
        return 0
    members = _cohort_set(cohort)
    n = 0
    for row in rows:
        if str(row.get("ticker") or "").strip().upper() in members:
            row["leadership"] = dict(chip)
            row["in_leadership_cohort"] = True
            n += 1
    return n


def leadership_cohort(cohort: Iterable[str] | None = None) -> set[str]:
    """The mega-cap cohort as an upper-cased ticker set (default = the organ's own).

    Public because the builder needs the same membership test the lanes use in order
    to chip a cohort member that reached the BUY cards — one definition of the
    cohort, read from one place.
    """
    return _cohort_set(cohort)


def _cohort_set(cohort: Iterable[str] | None) -> set[str]:
    if cohort is None:
        try:  # pragma: no cover — import shim; the organ is always present in-tree
            from engine.hk_leadership import DEFAULT_COHORT

            cohort = DEFAULT_COHORT
        except Exception:  # noqa: BLE001 — a missing organ must not fail a lane
            cohort = ()
    return {str(t or "").strip().upper() for t in cohort if str(t or "").strip()}


# --------------------------------------------------------------------------- #
# leaders lane (G2)
# --------------------------------------------------------------------------- #
def build_leaders_rows(
    momentum_by: Mapping[str, Any],
    *,
    verdict_by: Mapping[str, Mapping[str, Any]] | None = None,
    meta_by: Mapping[str, Mapping[str, Any]] | None = None,
    exclude: Iterable[str] = (),
    cohort: Iterable[str] | None = None,
    leadership: Mapping[str, Any] | None = None,
    board_asof: Any = None,
    cap: int = LEADERS_CAP,
    off_high_floor: float = LEADERS_OFF_HIGH_FLOOR,
    boost: float = LEADERSHIP_BOOST,
    dedup_name: Callable[[Any], str | None] | None = None,
) -> list[dict]:
    """Build the HK leaders strip: market leadership the fresh-cross gate cannot admit.

    RANK KEY is the cross-sectional z of trailing 3-month TOTAL return
    (:func:`engine.us_board_rank.total_return_z`), NOT the selection axis.  The US
    lane learned this the expensive way: residual/beta-neutral readings strip out
    precisely the common move that makes a cohort a cohort, so an edge-ranked
    "leaders" strip cannot show a theme rally.  HK has the same hazard in a sharper
    form — ``edge_z``'s beta-neutral leg is explicitly beta-stripped.

    ADMISSION is an intact trend, and every test is ``is True`` on purpose: a
    ``None`` (unanalysed) name must never read as intact.  ``above200`` ∧
    ``weekly_bull`` from the confluence verdict, ``dir != "down"``, a momentum
    reading, and price within ``off_high_floor``% of the 52-week high.

    THE OFF-HIGH FLOOR IS DELIBERATELY NOT RELAXED FOR HK, and the number is worth
    defending because it is the gate that keeps five of the seven named mega-caps
    out of this lane.  Measured on the 2026-07-31 panel: 71 of 157 HK names clear
    −20%, so the floor is not structurally unreachable here — it is doing exactly
    its job.  The names it rejects sit 29-52% off their highs after a multi-year
    drawdown; calling them "leaders" because they bounced for five weeks would be
    the strip lying about what leadership means.  They surface in
    :func:`build_vetoed_rows` instead, with the reason named.

    DISPLAY-TIER: no entry claim, no priority score, stance "watch — don't chase".
    Cohort membership adds ``boost`` to the rank key and attaches the chip — a
    tiebreak on a context lane, which is the lawful use of a display-fenced organ.
    """
    skip = {str(t or "").strip().upper() for t in exclude}
    members = _cohort_set(cohort)
    chip = leadership_chip(leadership)
    meta_by = meta_by or {}
    verdict_by = verdict_by or {}

    picked: list[tuple[float, float, str, dict]] = []
    for ticker, raw_momentum in (momentum_by or {}).items():
        key = str(ticker or "").strip().upper()
        if not key or key in skip:
            continue
        momentum = _finite_float(raw_momentum)
        if momentum is None:
            continue
        verdict = verdict_by.get(ticker) or verdict_by.get(key) or {}
        if verdict.get("above200") is not True or verdict.get("weekly_bull") is not True:
            continue
        meta = meta_by.get(ticker) or meta_by.get(key) or {}
        if str(meta.get("dir") or "").strip().lower() == "down":
            continue
        off_high = _finite_float(meta.get("off_high"))
        if off_high is None or off_high < float(off_high_floor):
            continue      # unknown distance-from-high fails closed
        in_cohort = key in members
        rank_key = momentum + (float(boost) if in_cohort else 0.0)
        picked.append((rank_key, momentum, key, dict(meta)))

    picked.sort(key=lambda item: (-item[0], -item[1], item[2]))

    seen_names: set[str] = set()
    rows: list[dict] = []
    for rank_key, momentum, key, meta in picked:
        # Dual-class / H-share dedup: 0700.HK and a second line of the same issuer
        # must not both occupy the strip.  The caller supplies the normaliser it
        # already uses elsewhere; without one the dedup is simply skipped.
        if dedup_name is not None:
            normalised = dedup_name(meta.get("name"))
            if normalised and normalised in seen_names:
                continue
            if normalised:
                seen_names.add(normalised)
        verdict = verdict_by.get(key) or {}
        sig_date = signal_asof(meta, verdict)
        row: dict[str, Any] = {
            "ticker": key,
            "name": meta.get("name") or key,
            "name_zh": meta.get("name_zh"),
            "sector": meta.get("sector"),
            "price": meta.get("price"),
            "off_high": _finite_float(meta.get("off_high")),
            "momentum_z": round(momentum, 4),
            "rank_key": round(rank_key, 4),
            "in_leadership_cohort": key in members,
            "lane": "leader",
            "stage": None,          # display strip — it does not occupy a stage bucket
            "stance": LEADERS_STANCE,
            "stance_zh": LEADERS_STANCE_ZH,
            "display_only": True,
            "signal_asof": sig_date,
        }
        row["days_since_signal"], row["days_since_signal_basis"] = signal_age(
            verdict, sig_date, board_asof)
        if meta.get("spark_svg"):
            row["spark_svg"] = meta["spark_svg"]
        if key in members and chip:
            row["leadership"] = dict(chip)
        rows.append(row)
        if len(rows) >= max(0, int(cap)):
            break
    return rows


# --------------------------------------------------------------------------- #
# ran lane (G3)
# --------------------------------------------------------------------------- #
def build_ran_rows(
    verdict_by: Mapping[str, Mapping[str, Any]],
    *,
    meta_by: Mapping[str, Mapping[str, Any]] | None = None,
    close_of: Callable[[str], tuple[Sequence[Any], Sequence[Any]] | None] | None = None,
    exclude: Iterable[str] = (),
    theme_by: Mapping[str, Mapping[str, Any]] | None = None,
    cohort: Iterable[str] | None = None,
    leadership: Mapping[str, Any] | None = None,
    board_asof: Any = None,
    cap: int = RAN_CAP,
    ticks_min: int = RAN_TICKS_MIN,
    ticks_max: int = RAN_TICKS_MAX,
    require_above200: bool = True,
) -> list[dict]:
    """Build the HK ran lane — the shared implementation, plus the cohort chip.

    The B3 anchor discipline is INHERITED VERBATIM, not re-implemented: the age
    anchors on the §7 buy-marker date, falls back to the verdict's ``fresh_bars``
    (daily-grid sessions), and a row with NEITHER is DROPPED rather than shown with
    an age derived from ``ticks`` — ticks live on the signal's native 2D/3D grid, so
    that fallback understated the age roughly threefold and mis-anchored the move
    with it.  A missing PRICE SERIES is a different question and keeps the row, with
    ``pct_since: null`` disclosed.

    THE MOVE IS CONFIRMATION-ANCHORED (2026-08-03), via the shared builder's
    ``move_read`` hook so the lane is also ORDERED and truncated by the number it
    prints.  The audit that produced the vetoed lane's fix found the identical defect
    here — same ``cross_read(..., cross_date=marker_date)`` call, same forbidden
    anchor — and it was not smaller: MEASURED 2026-07-31, all 12 displayed rows
    overstated, mean +8.09pp against the vetoed lane's +8.40pp.  So ``anchor`` here has
    the same three words: ``confirm`` (move from the confirmation close, date and age
    still the marker's), ``marker`` and ``approx`` (both print no move at all).
    """
    members = _cohort_set(cohort)
    # Build UNCAPPED, then apply the cap cohort-first (see _cohort_first): with the
    # above200 door open the lane is ~5x oversubscribed and a plain freshest-first
    # truncation drops every mega-cap a reader would come here to check.
    rows = _ubr.build_ran_rows(
        verdict_by,
        meta_by=meta_by,
        close_of=close_of,
        exclude=exclude,
        theme_by=theme_by,
        board_asof=board_asof,
        cap=None,
        ticks_min=ticks_min,
        ticks_max=ticks_max,
        move_read=confirmation_move,
        require_above200=require_above200,
    )
    rows = _cohort_first(rows, members, cap)
    chip = leadership_chip(leadership)
    for row in rows:
        in_cohort = str(row.get("ticker") or "").strip().upper() in members
        row["in_leadership_cohort"] = in_cohort
        row["display_only"] = True
        row["stance"] = RAN_STANCE
        row["stance_zh"] = RAN_STANCE_ZH
        if in_cohort and chip:
            row["leadership"] = dict(chip)
    return rows


def _cohort_first(rows: list[dict], members: set[str], cap: int) -> list[dict]:
    """Cohort members keep their slot; the rest fill what is left, order preserved.

    THE CAP, NOT THE TREND TEST, IS WHAT HID THE MEGA-CAPS.  Opening the ran lane's
    ``above200`` door (so a name recovering from a deep drawdown can appear at all)
    takes HK admits from 13 to **64** for **12** slots, and the lane sorts
    freshest-cross-first — so every name the operator named lands at rank 14-56 and
    is cut, INCLUDING 3690.HK, which the stricter lane had been showing.  Measured on
    the committed panel 2026-08-04: opening the door alone surfaces NONE of them and
    evicts the one that was already there, which is a strictly worse board.

    This is the rule :func:`build_vetoed_rows` already applies, for the same reason:
    a lane whose job is "what the board did not act on" is worthless if the names a
    reader is asking about are exactly the ones the cap drops.  It admits NOBODY new
    — every row here already passed ``ran_admits`` — it only decides who keeps a seat
    when the lane is oversubscribed.  Cohort membership is the ONE display-tier
    priority (HKRV-R5: hk_leadership never touches rank, size or gate on the graded
    buy lane; this is a display strip and carries no entry claim).
    """
    if cap is None or len(rows) <= cap:
        return rows
    keep = [r for r in rows if str(r.get("ticker") or "").strip().upper() in members]
    rest = [r for r in rows if str(r.get("ticker") or "").strip().upper() not in members]
    return (keep + rest)[:cap] if len(keep) <= cap else keep[:cap]


# --------------------------------------------------------------------------- #
# vetoed lane (G1 / G6) — the entry gate's own receipt
# --------------------------------------------------------------------------- #
def veto_admits(
    verdict: Mapping[str, Any] | None,
    row: Mapping[str, Any] | None = None,
) -> bool:
    """True when a buy signal FIRED on this name and the entry gate refused it.

    ``eligible is False`` (the cascade RAN and said no) ∧ the last marker is a
    ``buy``/``rebuy`` ∧ that marker's quality is ``block`` ∧ the weekly trend is
    still bull ∧ the row is not marked down.

    EVERY TEST IS FAIL-CLOSED, INCLUDING THIS ONE.  It began as ``eligible is not
    True``, which admitted an unevaluated ``None`` — a name the cascade never
    reached would then have been printed as "the gate refused it", which is a claim
    about a decision that was never made.  A lane whose whole purpose is to hold the
    gate to account cannot itself invent gate decisions, so ``None`` is OUT and the
    asymmetry with the other tests is gone: no leg here reads an unknown as a fact.

    The weekly-bull test is what keeps this lane from becoming a list of everything
    the gate ever rejected: a blocked signal on a name whose weekly trend has since
    rolled over is a veto that was RIGHT, and it is not news.  ``is True`` again —
    an unanalysed weekly must not read as bull.
    """
    verdict = verdict or {}
    if verdict.get("eligible") is not False:
        return False
    if verdict.get("weekly_bull") is not True:
        return False
    marker = verdict.get("last") or {}
    if str(marker.get("type") or "").strip().lower() not in _BUY_MARKERS:
        return False
    if str(marker.get("quality") or "").strip().lower() not in _VETOED_QUALITIES:
        return False
    if str((row or {}).get("dir") or "").strip().lower() == "down":
        return False
    return True


def veto_reason_copy(reason: Any) -> dict[str, str]:
    """Plain-word bilingual copy for a verdict's internal ``reason`` string."""
    key = str(reason or "").strip().lower()
    return dict(VETO_REASON_COPY.get(key, VETO_REASON_FALLBACK))


def confirmation_move(
    series: tuple[Sequence[Any], Sequence[Any]] | None,
    marker_date: Any,
) -> dict[str, Any] | None:
    """``{pct_since, measured_from}`` measured from the CONFIRMATION close, or None.

    The honest forward read off a blocked §7 marker.  ``marker['date']`` is the 3B
    bucket's left edge and the label at that bucket reads two buckets forward, so it
    precedes the first close at which the block was knowable by ~8 daily sessions —
    and it sits at the trough that CREATED the signal.  ``engine.signal_quality``
    owns that geometry (:func:`~engine.signal_quality.confirmation_date`) and this
    just spends it on the lane's own closes.

    Returns None on every path where the anchor is not exactly the confirmation
    session, so the caller prints a disclosed null instead of a number measured from
    a bar nobody could have traded on.  pandas is imported lazily: the rest of this
    module and :mod:`engine.us_board_rank` are pure stdlib, and a lane helper should
    not change what importing the ranker costs.
    """
    if not series:
        return None
    dates, closes = series
    try:
        import pandas as pd

        from engine.signal_quality import confirmation_date
    except ImportError:                                  # pragma: no cover
        return None
    try:
        index = pd.to_datetime(list(dates), errors="coerce")
        values = pd.to_numeric(pd.Series(list(closes)), errors="coerce")
    except (TypeError, ValueError):
        return None
    if len(index) != len(values) or len(index) < 2:
        return None
    daily = pd.Series(values.to_numpy(), index=index).sort_index()
    daily = daily[~daily.index.duplicated(keep="last")]
    daily = daily[daily.index.notna()]
    confirmed = confirmation_date(daily, marker_date)
    if confirmed is None:
        return None
    stamp = str(confirmed.date())
    read = cross_read(dates, closes, cross_date=stamp)
    # FAIL CLOSED ON A NEAR MISS.  cross_read anchors on the last session AT OR BEFORE
    # the date it is given, so a confirmation date that is not itself a session in
    # THESE closes would silently slide the anchor backwards — back toward the marker,
    # which is the direction of the overstatement being fixed.  Only an exact landing
    # is a confirmation read; anything else is a null.
    if read is None or read.get("cross_date") != stamp:
        return None
    return {"pct_since": read["pct_since"], "measured_from": stamp}


def build_vetoed_rows(
    verdict_by: Mapping[str, Mapping[str, Any]],
    *,
    meta_by: Mapping[str, Mapping[str, Any]] | None = None,
    close_of: Callable[[str], tuple[Sequence[Any], Sequence[Any]] | None] | None = None,
    exclude: Iterable[str] = (),
    cohort: Iterable[str] | None = None,
    leadership: Mapping[str, Any] | None = None,
    board_asof: Any = None,
    cap: int = VETOED_CAP,
    max_sessions: int = VETOED_MAX_SESSIONS,
) -> list[dict]:
    """Build the vetoed lane: signals the entry gate blocked, and what happened since.

    G6's display-tier relief, and the answer to "where is the name I was looking
    for".  MEASURED on the committed 2026-07-31 panel: 48 names qualify, and five of
    the seven mega-caps the operator named are among them — each blocked on the same
    ``counter-trend, no 200-reclaim/hold`` reason, one of them (1024.HK) on a single
    marker that has now stood for 59 sessions.

    SELECTION.  Cohort members are emitted UNCONDITIONALLY — they are the names a
    reader goes looking for, and truncating them to make room for a bigger number
    would defeat the lane.  The remaining slots go to the largest move since the
    blocked marker.  Ordering inside each group is move-desc.

    ANCHOR DISCIPLINE is the ran lane's, for the same reason: a row whose age cannot
    be anchored to a marker date or a ``fresh_bars`` session count is DROPPED, never
    shown with an invented age.  ``max_sessions`` bounds staleness — a veto older
    than a quarter is no longer news about this tape.

    THE MOVE IS ANCHORED ON THE CONFIRMATION CLOSE, NOT THE MARKER (2026-08-03).  It
    used to read ``cross_read(..., cross_date=marker_date)``, which is the anchor
    ``signal_quality._buy_filter`` explicitly forbids: the marker date is the 3B
    bucket's LEFT EDGE and the label there reads two buckets forward, so it precedes
    the first close at which the block was knowable by ~8 daily sessions — and it sits
    at the trough that CREATED the signal.  MEASURED across this lane's own 48-54 name
    population (2026-07-31 and 2026-08-03 as-of dates): +7.16pp of mean overstatement.
    Xiaomi (1810.HK) printed +20.1% here; from the confirmation close the same span is
    +1.7%, and +15.9% to its peak.  That is not a rounding error, it is the pre-signal
    move, and a lane whose whole job is to hold the gate to account cannot be the one
    surface on the page that flatters its own numbers.

    So ``anchor`` now has three words and they split the row's two facts:
    ``confirm`` (date + age from the marker, move from the confirmation close),
    ``marker`` (date + age exact, move NOT derivable), ``approx`` (no marker date at
    all — age counted back from recent bars, move not derivable).  ``pct_since`` is
    non-null ONLY under ``confirm``, which is what makes a marker-anchored move
    unreachable from here rather than merely discouraged.  The age deliberately stays
    on the marker: "this block has stood for N sessions" is a claim about the block,
    and ``max_sessions`` keeps measuring the same thing it always did.

    NO ENTRY CLAIM.  These rows carry no ``entry_signal``, no priority score and no
    conviction call.  ``pct_since`` here is not a missed profit — it is the distance
    the name travelled while the board stayed out, printed so the gate can be judged.
    Because the lane ranks by that move and then truncates to ``cap``, every row also
    carries ``population`` / ``population_measured`` / ``population_median_pct`` so
    the displayed set can never be read as the whole story.
    """
    skip = {str(t or "").strip().upper() for t in exclude}
    members = _cohort_set(cohort)
    chip = leadership_chip(leadership)
    meta_by = meta_by or {}

    cohort_rows: list[dict] = []
    other_rows: list[dict] = []
    dropped_no_anchor = 0
    dropped_stale = 0
    no_confirmed_move = 0

    for ticker, verdict in (verdict_by or {}).items():
        key = str(ticker or "").strip().upper()
        if not key or key in skip:
            continue
        meta = meta_by.get(ticker) or meta_by.get(key) or {}
        if not veto_admits(verdict, meta):
            continue

        marker = (verdict or {}).get("last") or {}
        marker_date = marker.get("date")
        fresh = _finite_int((verdict or {}).get("fresh_bars"))
        if fresh is not None and fresh < 0:
            fresh = None
        if not _as_date(marker_date) and fresh is None:
            dropped_no_anchor += 1          # the age would have to be invented
            continue

        series = close_of(ticker) if close_of is not None else None
        read: dict[str, Any] | None = None
        if series is not None:
            dates, closes = series
            read = cross_read(dates, closes, cross_date=marker_date, sessions_back=fresh)
        if read is None:
            read = _ubr._anchor_only_read(marker_date, fresh)

        sessions = read.get("sessions_since")
        if sessions is not None and sessions > int(max_sessions):
            dropped_stale += 1
            continue

        # THE MOVE IS CONFIRMATION-ANCHORED OR IT IS NULL.  `read` still supplies the
        # DATE and the AGE — those are the marker's, and the marker date is the honest
        # answer to "when was this blocked" — but its `pct_since` is measured from the
        # marker bar and is forbidden here, so it is dropped on the floor rather than
        # carried forward.  Only an exact confirmation read can put a number on this
        # row; every other path prints the disclosed null.
        move = confirmation_move(series, marker_date) if _as_date(marker_date) else None
        if move is None:
            no_confirmed_move += 1
        copy = veto_reason_copy(marker.get("reason"))
        in_cohort = key in members
        row: dict[str, Any] = {
            "ticker": key,
            "name": meta.get("name") or key,
            "name_zh": meta.get("name_zh"),
            "sector": meta.get("sector"),
            "price": meta.get("price"),
            "signal_date": read["cross_date"],
            "sessions_since": sessions,
            "pct_since": move["pct_since"] if move else None,
            "measured_from": move["measured_from"] if move else None,
            "anchor": ANCHOR_CONFIRM if move else read["anchor"],
            "blocked_reason_en": copy["en"],
            "blocked_reason_zh": copy["zh"],
            # The engine's own wording, kept for the detail view and for anyone
            # auditing which veto fired.  Never the glance-tier string.
            "reason_raw": marker.get("reason"),
            "in_leadership_cohort": in_cohort,
            "lane": "vetoed",
            "stage": STAGE_BLOCKED,
            "label": VETOED_LABEL,
            "label_zh": VETOED_LABEL_ZH,
            "stance": VETOED_STANCE,
            "stance_zh": VETOED_STANCE_ZH,
            "display_only": True,
        }
        if meta.get("spark_svg"):
            row["spark_svg"] = meta["spark_svg"]
        if in_cohort and chip:
            row["leadership"] = dict(chip)
        (cohort_rows if in_cohort else other_rows).append(row)

    def _move_desc(row: Mapping[str, Any]) -> tuple[float, str]:
        move = _finite_float(row.get("pct_since"))
        # A null move sorts last within its group but is NOT dropped — the age is
        # the anchored fact, and the move is a disclosed null.
        return (-(move if move is not None else -1e6), str(row.get("ticker") or ""))

    cohort_rows.sort(key=_move_desc)
    other_rows.sort(key=_move_desc)

    if dropped_no_anchor:
        _notice("hk_board_vetoed_anchor",
                f"{dropped_no_anchor} vetoed-lane admit(s) dropped — no buy-marker "
                f"date and no fresh_bars, so the signal age is unknowable; a missing "
                f"row beats a wrong age")
    if dropped_stale:
        _notice("hk_board_vetoed_stale",
                f"{dropped_stale} vetoed-lane admit(s) dropped — the block has stood "
                f"longer than {int(max_sessions)} sessions, past this lane's window")
    if no_confirmed_move:
        _notice("hk_board_vetoed_unconfirmed",
                f"{no_confirmed_move} vetoed-lane row(s) print pct_since: null — the "
                f"confirmation close the move must be measured from could not be "
                f"derived (series too short, marker off this series' 3B grid, or the "
                f"block is still inside its own confirmation window)")

    # THE POPULATION, STAMPED ON EVERY ROW IT DESCRIBES.  This lane RANKS BY THE MOVE
    # and then truncates, so the rows that survive are the winners of the very quantity
    # they print — read without the population behind them, twelve big green numbers
    # are a P&L claim the lane never made.  The median is the middle of the WHOLE
    # admitted set, on the same confirmation anchor as the displayed rows, and
    # `population_measured` is its denominator: medianing the measurable subset while
    # printing the full count would quietly drop the disclosed nulls out of the base.
    population = cohort_rows + other_rows
    measured = sorted(m for m in (_finite_float(r.get("pct_since")) for r in population)
                      if m is not None)
    stats = {
        "population": len(population),
        "population_measured": len(measured),
        "population_median_pct": (round(_median(measured), 1) if measured else None),
    }
    for row in population:
        row.update(stats)

    room = max(0, int(cap) - len(cohort_rows))
    return cohort_rows + other_rows[:room]


def lane_counts(
    *,
    buy: Sequence[Mapping[str, Any]] = (),
    leaders: Sequence[Mapping[str, Any]] = (),
    ran: Sequence[Mapping[str, Any]] = (),
    vetoed: Sequence[Mapping[str, Any]] = (),
    watch: Sequence[Mapping[str, Any]] = (),
    laggards: Sequence[Mapping[str, Any]] = (),
    featured: int = 0,
) -> dict[str, int]:
    """Per-lane counts for the artifact's ``lane_counts`` block.

    The stage buckets count BUY rows and sum to ``len(buy)``; the lane arrays are
    counted separately so no number here has to be inferred from another.
    ``featured`` is the flagged subset of the ``live`` stage, not a lane.
    """
    counts = dict(stage_counts(buy))
    counts.update({
        "buy": len(buy),
        "leaders_lane": len(leaders),
        "ran_lane": len(ran),
        "vetoed_lane": len(vetoed),
        "watch": len(watch),
        "laggards": len(laggards),
        "featured": int(featured),
    })
    return counts
