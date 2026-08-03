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

from typing import Any, Callable, Iterable, Mapping, Sequence

from engine import us_board_rank as _ubr
from engine.us_board_rank import (  # noqa: F401 — shared vocabulary, re-exported by design
    ANCHOR_APPROX,
    ANCHOR_MARKER,
    BASIS_CALENDAR,
    BASIS_SESSIONS,
    SCORE_KIND,
    SCORE_WEIGHTS,
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

BOARD_DEFINITION = "hk_prophet_v1"

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
# Marker qualities that mean "a buy signal fired and the gate refused it".
_VETOED_QUALITIES = frozenset(("block",))
_BUY_MARKERS = frozenset(("buy", "rebuy"))

# Plain-word reason copy.  The verdict's own `reason` strings are internal
# vocabulary ("counter-trend, no 200-reclaim/hold"); the glance tier gets these
# instead, and the raw string rides along as `reason_raw` for the detail view.
VETO_REASON_COPY: dict[str, dict[str, str]] = {
    "counter-trend, no 200-reclaim/hold": {
        "en": "Price never held above its 200-day average after the signal",
        "zh": "信号出现后股价未能站稳 200 日均线之上",
    },
    "failed reclaim-and-hold": {
        "en": "Reclaimed the 200-day average, then lost it again",
        "zh": "曾收复 200 日均线，但随后再度失守",
    },
    "veto: bearish divergence": {
        "en": "Momentum was already fading as the signal fired",
        "zh": "信号出现时动能已在衰减",
    },
}
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
    ``adv63``.  An absent or unreadable turnover yields ``adv_unknown`` — featured is
    a PROMOTION, and unknown evidence never earns the best case.
    """
    lookup = adv_by or {}

    def _extra(row: Mapping[str, Any]) -> list[str]:
        ticker = str(row.get("ticker") or "").strip()
        adv = _finite_float(lookup.get(ticker))
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
) -> list[dict]:
    """Score, stage, feature and order the HK buy pool.

    Delegates wholesale to :func:`engine.us_board_rank.score_rows` with the HK
    definition stamp, the HK selection axis and the HK turnover veto.  Rows are
    stamped in place and returned in ``(stage, −score, ticker)`` order.

    MEMBERSHIP IS UNTOUCHED — byte-identically so.  The caller hands this function
    the pool the confluence cascade already admitted, in whatever order; this
    function adds fields and re-orders.  It never adds, drops or re-filters a row.
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
) -> list[dict]:
    """Build the HK ran lane — the shared implementation, plus the cohort chip.

    The B3 anchor discipline is INHERITED VERBATIM, not re-implemented: the age
    anchors on the §7 buy-marker date, falls back to the verdict's ``fresh_bars``
    (daily-grid sessions), and a row with NEITHER is DROPPED rather than shown with
    an age derived from ``ticks`` — ticks live on the signal's native 2D/3D grid, so
    that fallback understated the age roughly threefold and mis-anchored the move
    with it.  A missing PRICE SERIES is a different question and keeps the row, with
    ``pct_since: null`` disclosed.  Every emitted row carries ``anchor`` ∈
    {``marker``, ``approx``}.
    """
    rows = _ubr.build_ran_rows(
        verdict_by,
        meta_by=meta_by,
        close_of=close_of,
        exclude=exclude,
        theme_by=theme_by,
        board_asof=board_asof,
        cap=cap,
        ticks_min=ticks_min,
        ticks_max=ticks_max,
    )
    members = _cohort_set(cohort)
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


# --------------------------------------------------------------------------- #
# vetoed lane (G1 / G6) — the entry gate's own receipt
# --------------------------------------------------------------------------- #
def veto_admits(
    verdict: Mapping[str, Any] | None,
    row: Mapping[str, Any] | None = None,
) -> bool:
    """True when a buy signal FIRED on this name and the entry gate refused it.

    ``eligible is not True`` (it is not on the buy lane) ∧ the last marker is a
    ``buy``/``rebuy`` ∧ that marker's quality is ``block`` ∧ the weekly trend is
    still bull ∧ the row is not marked down.

    The weekly-bull test is what keeps this lane from becoming a list of everything
    the gate ever rejected: a blocked signal on a name whose weekly trend has since
    rolled over is a veto that was RIGHT, and it is not news.  ``is True`` again —
    an unanalysed weekly must not read as bull.
    """
    verdict = verdict or {}
    if verdict.get("eligible") is True:
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

    NO ENTRY CLAIM.  These rows carry no ``entry_signal``, no priority score and no
    conviction call.  ``pct_since`` here is not a missed profit — it is the distance
    the name travelled while the board stayed out, printed so the gate can be judged.
    """
    skip = {str(t or "").strip().upper() for t in exclude}
    members = _cohort_set(cohort)
    chip = leadership_chip(leadership)
    meta_by = meta_by or {}

    cohort_rows: list[dict] = []
    other_rows: list[dict] = []
    dropped_no_anchor = 0
    dropped_stale = 0

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
            "pct_since": read["pct_since"],
            "anchor": read["anchor"],
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
