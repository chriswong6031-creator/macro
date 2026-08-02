"""engine/session_digest.py — OIP E1 session digest core (the Terminal→EOD bridge).

WHAT: turns the intraday options plane's archived per-minute stamps for one root into a
settled, replayable session record (`options_session.v1`).  Pure functions only — every
input is passed in, nothing here opens a socket, reads a store, or writes a file.  The I/O
shell is `scripts/build_session_digest.py`.

WHY IT IS PURE: the digest's whole promise is *deterministic and replayable* — the same
archives in must produce the same record out, forever.  That is only testable when the
derivations have no ambient state, so the R2 reads, the store reads, the ledger append and
the lane gate all live in the builder.

AUTHORITY: display-tier, descriptive, no direction claims.  Every event is a fact with a
receipt (the level or the z it was measured against); nothing here ranks, sizes, gates,
scores, or fuses.  Shape tags and event types are machine keys and ALWAYS travel with a
plain-word EN/ZH twin, because a surface may only ever print the twin (house design law:
no internal enums, slugs, study ids or bare statistics in visible copy).

WHAT IS AVAILABLE, AND WHAT IS NOT (honesty contract):
  * The per-root archive (`live_flow/surface/{ROOT}/{DATE}/`) carries, per stamp, a
    net-premium-by-strike column and that stamp's spot.  `netprem` is
    ``call premium traded − put premium traded`` per strike, and BOTH legs are GROSS
    (`scripts/build_flow_surface.net_prem_by_strike` reads `root_strikes`, whose
    `call_prem`/`put_prem` accumulate `_prem`, not `_signed_prem` — see
    `engine/live_flow._accumulate_tide`).  It is therefore NOT the tide's signed
    `ncp`/`npp`.  The digest calls its per-root series `net` and says so in `arc_method`;
    the Appendix-B `ncp`/`npp` keys are carried but stay null until a per-root SIGNED
    minute series is archived.  Mislabelling a gross difference as a signed net premium
    would be a fabricated number, so it is not done.
  * The market tide archives (`live_flow/tide/{DATE}.json`, `live_flow/dte_tide/{DATE}.json`)
    are MARKET-WIDE, not per-root.  Anything derived from them carries `scope: "market"`.
  * Intraday walls/flip ride the archive only once the greek tap is armed (the surface
    frame's `walls` key, Lane G).  Until then wall/flip levels come from the EOD
    `gex_state` payload with its vintage printed, and intraday-derived walls stay null.

Sources for the thresholds: the Terminal's evaluator parity module
`charting-app terminal/lib/optionsAlerts.ts` (read as a REFERENCE — never imported; the
two repos ship separately and a cross-repo import would couple their deploys).  Each
constant below names the evaluator it mirrors and the default it copies.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable, Sequence
from zoneinfo import ZoneInfo

SCHEMA = "options_session.v1"

# Stdlib zoneinfo — repo convention (engine/options_flow.py, scripts/build_flow_surface.py).
ET = ZoneInfo("America/New_York")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Constants — one block, each citing the Terminal evaluator it mirrors
# ═══════════════════════════════════════════════════════════════════════════════

#: Gamma-flip dead-band, in PERCENT of the flip level.  Mirrors
#: `optionsAlerts.evalGammaFlipCross` (`cond.band_pct`, default 0.05): a side change is
#: only accepted once spot has cleared the flip by more than this fraction of a percent,
#: so dead-band jitter can never manufacture a crossing.  First observation ARMS the side
#: and never counts as a cross.
FLIP_BAND_PCT = 0.05

#: Wall-proximity band, in PERCENT of the wall level.  Mirrors
#: `optionsAlerts.evalWallProximity` (`cond.within_pct`, default 0.25).  Fires on ENTER
#: only (outside → inside); the first observation arms, so a session that opens already
#: parked at the wall does not book a touch at 09:30.
WALL_WITHIN_PCT = 0.25

#: Trailing window, in stamps, for the premium-pace check.  Mirrors
#: `optionsAlerts.evalPremiumBurst` (`cond.window_min`, default 10).  Named in STAMPS
#: rather than minutes because the archive's cadence is whatever the poller ran at
#: (`idx.cadenceSec`) — a 10-stamp window at 5-minute cadence is 50 minutes of tape, and
#: pretending otherwise would put a wrong number in a receipt.
BURST_WINDOW_STAMPS = 10

#: EFFECT SIZE, in per-observation baseline sigmas, at which the premium-pace check books a
#: burst.  This is the quantity `optionsAlerts.evalPremiumBurst` actually thresholds at 2 —
#: `(window mean − baseline mean) / baseline sigma` — so keeping the cut at 2.0 preserves the
#: Terminal's intent AND the operating point this lane validated on a replay (the designed
#: mid-day burst measures 3.86 sigma).  It is deliberately NOT called a z: an effect size is a
#: scale-free difference in means, not a standardized test statistic, and the receipt names
#: both separately so neither can be misread as the other.
BURST_EFFECT_SIGMA = 2.0

#: Minimum baseline increments before a burst can be booked.  The statistic divides by the
#: BASELINE's sigma, which is unbounded from below — three quiet opening stamps would make any
#: fourth stamp a 40-sigma event.  10 keeps the earliest bookable burst honest.
BURST_MIN_BASELINE = 10


def _burst_t_floor(effect: float = BURST_EFFECT_SIGMA,
                   window: int = BURST_WINDOW_STAMPS,
                   baseline: int = BURST_MIN_BASELINE) -> float:
    """The two-sample t that `effect` sigmas produce at the smallest baseline the family accepts.

    DERIVED, not typed: the earlier hardcoded 4.47 sat 0.0021 BELOW the true 4.472136, so the
    floor was a hair looser than the value it claimed to be, and any edit to the window or the
    minimum baseline would have silently decoupled the two.  Computing it keeps the three
    constants in one relationship.
    """
    return effect * math.sqrt(1.0 / (1.0 / max(1, window) + 1.0 / max(1, baseline)))


#: Significance floor on the honest TWO-SAMPLE statistic (the #217 idiom: the difference in means
#: over `baseline_sigma · sqrt(1/w + 1/baseline_n)`).  The effect gate above is the interpretable
#: cut; this floor exists so a THIN baseline cannot manufacture one.  Pinned to the strictness at
#: the earliest bookable moment (see `_burst_t_floor`), so the test is never LOOSER than it is
#: there, while later in the session — where t for the same effect climbs toward 6.2 — the
#: interpretable effect gate is what binds.  A fixed t with no effect gate would drift the other
#: way: the same t would mean a 0.9-sigma effect by the close.
BURST_T_MIN = _burst_t_floor()

#: Re-arm margin for the burst family, in effect sigmas below BURST_EFFECT_SIGMA.  A single
#: sustained pace change ramps the effect across the cut and books twice without it (measured),
#: and the session ledger counts both — one acceleration must be one row's worth of event.  The
#: mirrored-semantics argument does not protect this family: its denominator already diverges
#: from the Terminal's by design, so matching its re-arm behaviour buys nothing.
BURST_REARM_SIGMA = 0.5

#: 0DTE share of tracked net premium, in PERCENT, at which a spike is booked.  Mirrors
#: `optionsAlerts.eval0dteShare` (`cond.share_pct`, default 55).  Market-wide only — the
#: dated `dte_tide` archive has no per-root split.
ZERO_DTE_SHARE_PCT = 55.0

#: Share of a stamp's gross net-premium magnitude carried by the heaviest strike band, in
#: PERCENT, at which a "hot pocket" is booked.  DIGEST-ORIGINAL: the Terminal ships four
#: evaluator families (`opt_gamma_flip`, `opt_wall_touch`, `opt_premium_burst`,
#: `opt_0dte_spike`) and has NO hot-pocket evaluator, so there is nothing to mirror.  The
#: ENTER-only + arming semantics are copied from `evalWallProximity` so the two behave the
#: same way; the threshold is a house choice, documented here as such.
POCKET_SHARE_PCT = 35.0

#: Re-arm margin for the pocket family, in percentage POINTS below POCKET_SHARE_PCT.  A share
#: parked on the threshold otherwise books an event every other stamp as it jitters across
#: (seen at 35.0/35.2 in the first live replay), which would turn one finding into five.  Only
#: the digest-original family gets this: the four mirrored families keep the Terminal's exact
#: semantics so the two implementations stay comparable.
POCKET_REARM_PCT = 3.0

#: Strikes either side of the peak that count as one pocket (band width 2*k+1).  Adjacent
#: strikes are one position in practice, so a single-strike share would under-read a real
#: concentration and over-fire on a wide, thin grid.
POCKET_BAND_STRIKES = 1

#: Floor on a stamp's RUNNING total gross magnitude before a pocket can be booked, in dollars
#: of premium.  The first stamps of a session carry a handful of trades, where one contract is
#: trivially 100% of the column; without a floor the digest would book a pocket every morning.
#:
#: DOCUMENTED CHOICE, and it is deliberately near-vacuous on the index roots the archive covers
#: today: SPY clears $250k of traded premium within the first minute or two, so on SPY/QQQ/IWM
#: this floor only ever suppresses the very first stamp or two.  That is the intent.  The
#: alternative — a floor scaled to be "meaningful" for an index — would silently disable the
#: family on the smaller roots `surface_top_n` can add, which is the failure that matters: a
#: threshold tuned for SPY is a threshold that never fires for anything else.  A per-root
#: scaled floor needs a per-root premium baseline this lane does not accrue, so the honest
#: version is an absolute floor whose only job is rejecting a literally-empty column, plus the
#: share and level printed on every event so a reader can judge scale themselves.
POCKET_MIN_TOTAL = 250_000.0

#: Arc downsample ceiling (Appendix B: "↓sampled").  The arc is a shape for a surface to
#: draw, not a tape — ~80 points renders cleanly at any width and keeps the payload small.
ARC_MAX_POINTS = 80

#: Regular NYSE cash session in ET WALL-CLOCK.  Held as clock times and localized onto the
#: session date, never as a UTC offset: a UTC-pinned window silently shifts by an hour at
#: every DST boundary (the class that broke the marketing radar's window).
SESSION_OPEN_ET = time(9, 30)
SESSION_CLOSE_ET = time(16, 0)
#: Early-close sessions end at 13:00 ET.  `lib/nyse_calendar` deliberately does not model
#: these (its docstring says so), and this list exists ONLY so a 1pm session does not read
#: as a half-empty tape.  It touches nothing but the `coverage.expected` denominator: get
#: it wrong and a coverage ratio is off, never a datum.
EARLY_CLOSE_ET = time(13, 0)

#: Minimum arc points before a shape tag is anything but "insufficient".
ARC_MIN_POINTS_FOR_SHAPE = 6

#: Share of the day's cumulative strike-level MAGNITUDE that the aggregate net path ever
#: reached, below which the path counts as flat.  Both numbers come from the same frame and
#: the same stamp, so the ratio is scale-free without needing a dollar floor (a dollar floor
#: would be wrong for one root the moment a second root joined the archive).
SHAPE_FLAT_FRAC = 0.10
#: Retrace off the day's extreme (as a fraction of that extreme) that makes a reversal.
SHAPE_REVERSAL_FRAC = 0.50
#: Signed direction changes (each worth >= this fraction of the peak) that make a
#: two-sided path.
SHAPE_SWING_FRAC = 0.25
#: Share of the day's closing |net| accumulated in the last third that makes a late build.
SHAPE_LATE_FRAC = 0.60


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Session window (exchange-calendar-derived, DST-safe)
# ═══════════════════════════════════════════════════════════════════════════════

def is_early_close(d: date) -> bool:
    """True for the three recurring NYSE 1pm ET closes.

    Friday after Thanksgiving (4th Thursday of November + 1), 24 December, and 3 July.

    A NON-SESSION date is never an early close, and that guard is load-bearing rather than
    defensive: when 4 July falls on a Saturday the NYSE observes the holiday on Friday 3 July
    with a FULL closure, so the bare month/day rule called it a half day when it is not a
    trading day at all (2026 is exactly that year — `nyse_calendar.holidays(2026)` carries
    2026-07-03).  Delegating session-ness to the calendar fixes the whole family of such
    collisions instead of special-casing one.

    Coverage-denominator only (see EARLY_CLOSE_ET) — this never gates, filters or labels a
    datum, so an error here costs a ratio, never a number.
    """
    from lib import nyse_calendar          # local import: keeps the module import graph flat
    if not nyse_calendar.is_session(d):
        return False
    if d.month == 12 and d.day == 24:
        return True
    if d.month == 7 and d.day == 3:
        return True
    if d.month == 11:
        # 4th Thursday = first Thursday + 21 days.
        first = date(d.year, 11, 1)
        first_thu = first + timedelta(days=(3 - first.weekday()) % 7)
        return d == first_thu + timedelta(days=22)
    return False


def session_window_et(session_date: str | date) -> tuple[datetime, datetime]:
    """(open, close) as ET-aware datetimes for a session date.

    Built by localizing ET wall-clock times onto the date, so the window is correct on both
    sides of every DST boundary.  Raises ValueError on an unparseable date rather than
    guessing a window.
    """
    d = _as_date(session_date)
    close_t = EARLY_CLOSE_ET if is_early_close(d) else SESSION_CLOSE_ET
    return (datetime.combine(d, SESSION_OPEN_ET, tzinfo=ET),
            datetime.combine(d, close_t, tzinfo=ET))


def expected_stamps(session_date: str | date, cadence_sec: int) -> int:
    """Cadence-aligned marks in the session window, inclusive of both ends.

    Returns 0 for a non-positive cadence (an index that lies about its cadence must not
    manufacture a denominator).
    """
    try:
        cad = int(cadence_sec)
    except (TypeError, ValueError):
        return 0
    if cad <= 0:
        return 0
    open_dt, close_dt = session_window_et(session_date)
    span = (close_dt - open_dt).total_seconds()
    if span <= 0:
        return 0
    return int(span // cad) + 1


def _as_date(v: str | date) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.fromisoformat(str(v)[:10]).date()


def session_window_label(session_date: str | date) -> str:
    """"09:30–16:00 ET" / "09:30–13:00 ET" — the window the coverage ratio was measured on."""
    open_dt, close_dt = session_window_et(session_date)
    return f"{open_dt:%H:%M}–{close_dt:%H:%M} ET"


# ── clock-label normalization (the archived labels cannot be taken on trust) ──────

#: Label families, which differ in how much the digest may assume about their clock.
#:   "surface" — `scripts/build_flow_surface.stamp_hhmm` receives an AWARE UTC datetime and
#:               calls `.astimezone(ET)`, so its stamps are exchange time BY CONSTRUCTION.
#:   "tide"    — `engine/live_flow._minute_key` localizes a NAIVE exchange timestamp as UTC,
#:               so this family carries the defect.
CLOCK_FAMILY_SURFACE = "surface"
CLOCK_FAMILY_TIDE = "tide"

#: Residual deficit (minutes) below which no timezone correction is even considered.  A late
#: poller start produces a POSITIVE residual and must never be "corrected".
CLOCK_RESIDUAL_MIN_DEFICIT = 30


@dataclass(frozen=True)
class ClockRead:
    offset_min: int
    ambiguous: bool
    labels_outside: int
    fitting: tuple[int, ...]
    residual_median_min: float | None
    note_en: str
    note_zh: str

    @property
    def trusted(self) -> bool:
        """False → the clock could not be pinned, so nothing time-stamped may be emitted."""
        return not self.ambiguous


def defect_offset_minutes(session_date: str | date) -> int:
    """The exact minutes `_minute_key` shifts a label on this session date.

    The defect localizes a naive ET timestamp as UTC and converts back to ET, so the error is
    precisely the ET↔UTC offset ON THAT DATE — 240 minutes under EDT, 300 under EST.  The
    exchange calendar already knows which, so the candidate set is TWO values (0 or this one),
    never a guess between 4 and 5 hours.  That is what lets a truncated SKEWED session resolve:
    with only one non-zero candidate there is nothing to be ambiguous between.
    """
    open_dt, _ = session_window_et(session_date)
    off = open_dt.utcoffset()
    return int(-off.total_seconds() // 60) if off else 0


def clock_candidates(session_date: str | date) -> tuple[int, ...]:
    """(0, defect offset) — the only two clocks an archived label can be on."""
    return (0, defect_offset_minutes(session_date))


def clock_read(
    session_date: str | date,
    labels: Sequence[str],
    *,
    cadence_sec: int | None = None,
    family: str = CLOCK_FAMILY_TIDE,
) -> ClockRead:
    """Pin the archive's clock onto exchange time using EVERY label, not just the earliest.

    WHY THIS EXISTS: `engine/live_flow._minute_key` localizes NAIVE exchange timestamps as UTC
    before converting to ET, so the tide/dte minute labels run a whole timezone offset early —
    a real 09:30–16:00 session is labelled 05:30–11:59.  The series itself is correct and
    monotone; only the labels lie.  (Surface stamps are NOT affected: they come from an aware
    UTC datetime through `stamp_hhmm`'s `astimezone(ET)`.  The correction runs over both anyway
    and is a no-op wherever the labels are already right.)

    HOW: score each of the two candidates (0, or this date's defect offset) by how many labels
    it would place OUTSIDE the session window, and take the one that fits.  Using the
    distribution rather than one label is what makes it robust — an earliest-label rule breaks
    on a single off-grid print.  Two measured failures of that earlier rule, both now covered:
      * a 09:25 ET print (before the open) made the rule "correct" a clean session;
      * a skewed session whose last label sat 3 minutes past the close at the configured
        cadence made the rule refuse a correction the whole session needed, silently stamping
        every event 4 hours early.

    THE `surface` FAMILY IS DISPOSITIVE AT ZERO.  `stamp_hhmm` converts an AWARE UTC datetime
    with `.astimezone(ET)`, so a surface label cannot carry the defect.  Whenever 0 fits, 0 is
    the answer and the read is trusted — no ambiguity verdict.  This is not a convenience: the
    two-candidate scoring alone declared a CLEAN truncated session ambiguous (09:30–11:00 fits
    at 0, and also at +240 as 13:30–15:00), which dropped every event for a poller that died at
    11:00 ET.  The defect is one-directional — localize-as-UTC only ever shifts labels EARLIER —
    so for a family that cannot be skewed, a fit at 0 settles it.  If 0 does NOT fit, something
    unmodelled is wrong and the general path below still applies, ambiguity included.

    AMBIGUITY IS DECLARED, NOT GUESSED AWAY, for the `tide` family: when both candidates fit,
    the read is marked ambiguous and `trusted` goes False, and the caller must suppress
    time-stamped output rather than pick a story.  A candidate is still reported so the arc
    (whose shape does not depend on the offset) can be drawn.

    THE RESIDUAL RECEIPT: `residual_median_min` is the median of `label − (open + i·cadence)`
    across the labels — a diagnostic, reported so a reader can see what the clock looked like,
    and used for one assertion: a deficit beyond CLOCK_RESIDUAL_MIN_DEFICIT must round to a
    whole hour matching a candidate, or the read is ambiguous.  It is NOT the selection
    mechanism, because gaps in the tape shift index positions and would bias it.

    KNOWN CONFLATION, stated rather than papered over: a tide archive whose SKEWED labels
    happen to land wholly inside the window is indistinguishable from a clean late start.
    Measured example — labels 10:00–12:00 fit at 0 (a clean late morning) and at +240 (a skewed
    record of 14:00–16:00), so the read reports itself ambiguous instead of choosing.  It takes
    a real start at or after roughly 13:30 to produce that.

    SELF-DISARMING: once `_minute_key` is repaired every label is exchange time, candidate 0 is
    the unique fit, and this function stops touching anything.
    """
    candidates = clock_candidates(session_date)
    mins = [m for m in (_stamp_minutes(x) for x in labels) if m is not None]
    if not mins:
        return ClockRead(0, False, 0, (0,), None, "", "")

    open_dt, close_dt = session_window_et(session_date)
    open_min = open_dt.hour * 60 + open_dt.minute
    close_min = close_dt.hour * 60 + close_dt.minute

    outside = {c: sum(1 for m in mins if not (open_min <= m + c <= close_min))
               for c in candidates}
    fitting = tuple(c for c in candidates if outside[c] == 0)

    # The residual receipt is computed on EVERY path, including the surface fast path below: it is
    # a diagnostic a reader is entitled to see even when the decision did not need it.
    cad_min = max(1, int((cadence_sec or 0) // 60)) if cadence_sec else None
    residual: float | None = None
    if cad_min:
        res = sorted(m - (open_min + i * cad_min) for i, m in enumerate(mins))
        mid = len(res) // 2
        residual = float(res[mid] if len(res) % 2 else (res[mid - 1] + res[mid]) / 2.0)
        residual = round(residual, 1)

    if family == CLOCK_FAMILY_SURFACE and 0 in fitting:
        return ClockRead(0, False, 0, fitting, residual, "", "")

    def anchor_pick(cands: Sequence[int]) -> int:
        return min(cands, key=lambda c: (abs((mins[0] + c) - open_min), c))

    if len(fitting) == 1:
        offset, ambiguous, n_out = fitting[0], False, 0
    elif len(fitting) > 1:
        offset, ambiguous, n_out = anchor_pick(fitting), True, 0
    else:
        ranked = sorted(candidates, key=lambda c: (outside[c], c))
        best = ranked[0]
        offset, n_out = best, outside[best]
        ambiguous = len(ranked) > 1 and outside[ranked[1]] == outside[best]

    # Whole-hour assertion on the residual deficit (diagnostic → ambiguity, never selection).
    if residual is not None and residual <= -CLOCK_RESIDUAL_MIN_DEFICIT:
        implied = int(round(-residual / 60.0)) * 60
        if implied not in candidates:
            ambiguous = True

    if ambiguous:
        en = ("the archived clock could not be matched to exchange time with confidence, so "
              "nothing in this record is stamped with a time")
        zh = "存档时间无法可靠对应交易所时间，因此本记录不标注具体时点"
    elif offset:
        en = ("the archived clock labels ran early by a whole timezone offset and were "
              "corrected onto exchange time before anything was stamped")
        zh = "存档的时间标签整体偏早一个时区，已校正为交易所时间后再标注"
    else:
        en = zh = ""
    return ClockRead(offset, ambiguous, n_out, fitting, residual, en, zh)


def shift_label(label: str | None, offset_min: int) -> str:
    """'HH:MM'/'HHMM' + offset minutes → 'HH:MM'.  Unparseable labels pass through unchanged."""
    if not label:
        return ""
    if not offset_min:
        return _hhcolonmm(label)
    m = _stamp_minutes(label)
    if m is None:
        return _hhcolonmm(label)
    m = (m + int(offset_min)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Unit discipline (the ×100 class — asserted at ingestion, never inferred)
# ═══════════════════════════════════════════════════════════════════════════════

class UnitError(ValueError):
    """A value arrived in the wrong unit (fraction where a percent was promised, or vice
    versa).  Raised at the ingestion seam so a wrong scale cannot travel into a payload."""


def pct_from_fraction(x: float | None, *, field: str) -> float | None:
    """0..1 fraction → 0..100 percent.  Rejects anything already percent-scaled.

    The surface frame's greek `coverage` is a FRACTION; gex_state's `dist_to_flip_pct` and
    `stability_pct` are PERCENTS; the Terminal's 0DTE `share` is a PERCENT.  Every seam is
    asserted rather than sniffed, because a silently doubled scale is exactly the defect
    that shipped twice in this estate.
    """
    if x is None:
        return None
    v = float(x)
    if not math.isfinite(v):
        return None
    if v < 0.0 or v > 1.0:
        raise UnitError(
            f"{field}={v!r} is outside 0..1 — expected a fraction, got a percent?")
    return round(v * 100.0, 2)


def require_pct(x: float | None, *, field: str, hard_max: float = 1000.0) -> float | None:
    """Pass through a value that must already be percent-scaled; None stays None.

    `hard_max` is deliberately loose (a real percent can exceed 100 — a share cannot, but a
    distance can).  The guard catches an order-of-magnitude slip, not a tight range.
    """
    if x is None:
        return None
    v = float(x)
    if not math.isfinite(v):
        return None
    if abs(v) > hard_max:
        raise UnitError(f"{field}={v!r} exceeds {hard_max} — percent/fraction mix-up?")
    return v


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Arc — per-root net-premium path from the archived netprem grid
# ═══════════════════════════════════════════════════════════════════════════════

ARC_METHOD = (
    "net = sum over strikes of (call premium traded - put premium traded), cumulative "
    "through the session, from the archived per-minute net-premium grid. Both legs are "
    "gross traded premium, so this is NOT the tide's direction-signed net call/put "
    "premium; ncp/npp stay null until a per-root signed minute series is archived."
)


def column_net(frame: dict, metric: str = "netprem") -> list[float]:
    """Per-stamp totals of a surface grid: sum down each column.

    grids[metric] is [levelIdx][timeIdx] (scripts/build_flow_surface.append_stamp), so a
    column is one stamp across every strike.  A ragged grid is summed over the cells that
    exist rather than raising — the frame's own validator owns dimension policy, and a
    digest that crashed on one bad column would lose the whole session.
    """
    grid = ((frame or {}).get("grids") or {}).get(metric) or []
    n_cols = len((frame or {}).get("time_steps") or [])
    if n_cols == 0:
        n_cols = max((len(r) for r in grid if isinstance(r, list)), default=0)
    out = [0.0] * n_cols
    for row in grid:
        if not isinstance(row, list):
            continue
        for j, v in enumerate(row[:n_cols]):
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if math.isfinite(fv):
                out[j] += fv
    return out


def column_gross(frame: dict, metric: str = "netprem") -> list[float]:
    """Per-stamp sum of |cell| down each column — the column's total magnitude.

    Used as the pocket-share denominator: a net total can sit near zero while two large
    opposite-signed strikes dominate, and dividing by the net would fabricate a share
    above 100%.
    """
    grid = ((frame or {}).get("grids") or {}).get(metric) or []
    n_cols = len((frame or {}).get("time_steps") or [])
    if n_cols == 0:
        n_cols = max((len(r) for r in grid if isinstance(r, list)), default=0)
    out = [0.0] * n_cols
    for row in grid:
        if not isinstance(row, list):
            continue
        for j, v in enumerate(row[:n_cols]):
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if math.isfinite(fv):
                out[j] += abs(fv)
    return out


def downsample(rows: Sequence[Any], max_points: int = ARC_MAX_POINTS) -> list[Any]:
    """Even-stride downsample that ALWAYS keeps the first and last rows.

    Endpoints are load-bearing: the last arc point is the settled close, and dropping it
    would make the payload disagree with the record's own `net_close`.
    """
    n = len(rows)
    if max_points <= 0 or n <= max_points:
        return list(rows)
    if max_points == 1:
        return [rows[-1]]
    step = (n - 1) / (max_points - 1)
    idx = sorted({min(n - 1, int(round(i * step))) for i in range(max_points)})
    if idx and idx[0] != 0:
        idx.insert(0, 0)
    if idx and idx[-1] != n - 1:
        idx.append(n - 1)
    return [rows[i] for i in idx]


def build_arc(frame: dict, *, max_points: int = ARC_MAX_POINTS,
              times: Sequence[str] | None = None) -> tuple[list[dict], list[float]]:
    """(downsampled arc rows, full per-stamp net series).

    Arc rows carry the Appendix-B keys `t`/`ncp`/`npp` plus the honest `net`; ncp/npp are
    null because the archived per-root series has no signed call/put split (see module
    docstring).  Printing them as nulls rather than omitting them is the compliant form —
    a consumer written against the sketch reads None, not a KeyError, and the gap is
    visible instead of silent.

    `times` overrides the frame's own labels, so the caller can hand in the clock-corrected
    axis rather than the archive's raw one.
    """
    times = ([str(t) for t in times] if times is not None
             else [str(t) for t in ((frame or {}).get("time_steps") or [])])
    nets = column_net(frame)
    rows = [{"t": times[i] if i < len(times) else "",
             "net": round(nets[i], 0),
             "ncp": None,
             "npp": None}
            for i in range(len(nets))]
    return downsample(rows, max_points), nets


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Arc shape tag (descriptive, direction-free, receipts attached)
# ═══════════════════════════════════════════════════════════════════════════════

#: Shape tag → plain-word EN/ZH twin.  The tag is a machine key; a surface prints the twin.
#: No tag names a direction, an outcome, or a study.
#:
#: Every twin is a bare PREDICATE, never its own subject: every caller composes these by
#: prefixing "Premium " / "权利金" (e.g. templates/options.html.j2's filmstripSentence()).
#: "flat" and "insufficient" used to embed "premium"/"权利金" themselves, which produced a
#: doubled subject once composed ("Premium premium barely moved all day.",
#: "权利金全天权利金几乎没有变化。") — the OIP W1 B3 regression. Keep this invariant when
#: editing: no twin may itself contain "premium" (EN, case-insensitive) or "权利金" (ZH).
SHAPE_WORDS: dict[str, tuple[str, str]] = {
    "insufficient": ("left too little tape to describe the day", "当日记录过少，无法描述走势"),
    "flat": ("barely moved all day", "全天几乎没有变化"),
    "one_way": ("built steadily in one direction and stayed", "全天单向累积并维持"),
    "reversal": ("built one way, then gave most of it back", "先单向累积，之后大部分回吐"),
    "two_sided": ("pushed back and forth more than once", "多次来回推动"),
    "late_build": ("quiet most of the day, then built late", "全天平静，尾盘才开始累积"),
}


@dataclass(frozen=True)
class ArcShape:
    tag: str
    en: str
    zh: str
    receipts: dict


def classify_arc(nets: Sequence[float], gross_close: float | None = None) -> ArcShape:
    """Tag the day's net-premium path by SHAPE only, with the numbers used attached.

    Order matters and is fixed so the tag is deterministic: insufficient → flat → reversal
    → two_sided → late_build → one_way.  Nothing here claims a direction: the sign of the
    close is carried separately as a raw number, and no tag is scored, ranked or combined
    with another series (the posture-never-fused law).

    `gross_close` is the same frame's final-column MAGNITUDE total (`column_gross`), used
    only for the flat test — "barely moved" is an absolute statement, and the day's own
    churn is the only honest denominator available in the same document at the same stamp.
    Omit it and the flat test is simply skipped (nulls, not guesses).
    """
    # Minor, flagged not fixed (PR #4123 adversarial review round 2): this gate is
    # intentionally independent of coverage.minutes — `nets` (this function's own
    # input) and the minute-stamp index behind coverage_block()'s `minutes` are
    # two different axes of the same session (the M9 doctrine two screens up in
    # this file: "which axis each figure was measured on... both numbers are
    # printed rather than one standing in for the other"), so a session with
    # decently-covered minutes can still land here if its net-premium ARC
    # specifically carried too few usable points. That combination can render a
    # coverage sentence ("covers most of the session") beside this tag's own
    # words ("left too little tape to describe the day") without one gating the
    # other. The receipt that explains the apparent contradiction already ships
    # on the very next line (`{"points": n}`, in `arc_receipts` on the record,
    # unslimmed all the way to site/session/<T>.json per
    # scripts/build_session_digest.py's write_record/write_latest) — a surface
    # that wants to reconcile the two sentences for a reader should read
    # `arc_receipts.points` rather than treat coverage.minutes as a stand-in for
    # arc density. Not reconciled here: doing so by gating this tag on
    # coverage.minutes would change behavior for real (already shipped, already
    # byte-pinned by tests/test_session_digest.py and the filmstrip sentence
    # tests in tests/test_build_options_command.py) sessions without a
    # measurement of how often the two axes actually diverge in practice.
    vals = [float(v) for v in nets if v is not None and math.isfinite(float(v))]
    n = len(vals)
    if n < ARC_MIN_POINTS_FOR_SHAPE:
        return ArcShape("insufficient", *SHAPE_WORDS["insufficient"], {"points": n})

    peak = max(abs(v) for v in vals)
    close = vals[-1]
    receipts: dict[str, Any] = {
        "points": n,
        "peak_abs": round(peak, 0),
        "close": round(close, 0),
    }
    if peak <= 0:
        return ArcShape("flat", *SHAPE_WORDS["flat"], receipts)

    # Flat: the aggregate path never reached a meaningful share of the strike-level churn.
    receipts["close_over_peak"] = round(abs(close) / peak, 3)
    g = _num(gross_close)
    if g is not None and g > 0:
        receipts["peak_over_gross"] = round(peak / g, 4)
        if peak / g <= SHAPE_FLAT_FRAC:
            return ArcShape("flat", *SHAPE_WORDS["flat"], receipts)

    # Reversal: the extreme was reached, then most of it was given back by the close.
    extreme = max(vals, key=abs)
    retrace = (abs(extreme) - abs(close)) / abs(extreme) if extreme else 0.0
    receipts["retrace_off_extreme"] = round(retrace, 3)
    if retrace >= SHAPE_REVERSAL_FRAC:
        return ArcShape("reversal", *SHAPE_WORDS["reversal"], receipts)

    # Two-sided: repeated direction changes, each worth a real slice of the peak.
    swings = _significant_swings(vals, peak * SHAPE_SWING_FRAC)
    receipts["significant_swings"] = swings
    if swings >= 2:
        return ArcShape("two_sided", *SHAPE_WORDS["two_sided"], receipts)

    # Late build: most of the closing magnitude arrived in the final third.
    third = max(1, n // 3)
    at_two_thirds = vals[n - third - 1] if n - third - 1 >= 0 else vals[0]
    late = (abs(close) - abs(at_two_thirds)) / abs(close) if close else 0.0
    receipts["late_third_share"] = round(late, 3)
    if late >= SHAPE_LATE_FRAC:
        return ArcShape("late_build", *SHAPE_WORDS["late_build"], receipts)

    return ArcShape("one_way", *SHAPE_WORDS["one_way"], receipts)


def _significant_swings(vals: Sequence[float], min_move: float) -> int:
    """Direction changes in a series where each leg moves at least `min_move`.

    A zig-zag counter with a hysteresis floor: without the floor, cadence noise would count
    dozens of "swings" in a quiet tape.
    """
    if min_move <= 0 or len(vals) < 3:
        return 0
    swings = 0
    direction = 0          # +1 rising, -1 falling, 0 unset
    anchor = vals[0]
    for v in vals[1:]:
        move = v - anchor
        if abs(move) < min_move:
            continue
        d = 1 if move > 0 else -1
        if direction != 0 and d != direction:
            swings += 1
        direction = d
        anchor = v
    return swings


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Event families
# ═══════════════════════════════════════════════════════════════════════════════

#: Event type → plain-word EN/ZH twin.  `{}` slots are filled with numbers only, so a
#: surface never has to render a machine key.
EVENT_WORDS: dict[str, tuple[str, str]] = {
    "flip_cross": ("price crossed the gamma flip level",
                   "价格穿越 gamma 翻转价位"),
    "call_wall_touch": ("price came up to the call wall",
                        "价格触及看涨墙价位"),
    "put_wall_touch": ("price came down to the put wall",
                       "价格触及看跌墙价位"),
    "premium_burst": ("premium changed hands faster than the rest of the day",
                      "权利金成交节奏明显快于当天其余时段"),
    "hot_pocket": ("the day's premium so far was concentrated in one strike area",
                   "当日累计权利金集中在某一行权价区域"),
    "zero_dte_spike": ("most of the day's premium so far was in same-day expiries",
                       "当日累计权利金大部分集中在当日到期合约"),
}


#: Keys an event owns.  A receipt may not use them — `t` is the event's TIME, and a burst
#: receipt passing `t=<statistic>` silently overwrote it (caught by a replay test asserting the
#: stamp was still in the time axis).  Hence the reserved list and the raise: a shadowing field
#: is a programming error, not something to resolve by last-writer-wins.
_EVENT_RESERVED = ("t", "type", "label_en", "label_zh")


def _event(stamp: str, etype: str, **extra) -> dict:
    """Build one event: `t` is the corrected timestamp, plus the receipt fields for its family."""
    en, zh = EVENT_WORDS[etype]
    ev = {"t": stamp, "type": etype, "label_en": en, "label_zh": zh}
    for k, v in extra.items():
        if k in _EVENT_RESERVED:
            raise ValueError(
                f"receipt field {k!r} would shadow an event's own key {_EVENT_RESERVED}")
        if v is not None:
            ev[k] = v
    return ev


@dataclass(frozen=True)
class FlipRead:
    events: list[dict]
    crosses: int
    last_side: str | None
    side_at_open: str | None


def flip_crossings(
    times: Sequence[str],
    spots: Sequence[float | None],
    flip: float | None,
    *,
    band_pct: float = FLIP_BAND_PCT,
    level_vintage: str | None = None,
) -> FlipRead:
    """Gamma-flip crossings for spot over the archived stamps.

    Port of `optionsAlerts.evalGammaFlipCross` run forward: the first observation ARMS a
    side without firing, and a side change is only confirmed once spot has cleared the flip
    by more than `band_pct` percent of the flip.  Missing spots are skipped, not
    interpolated — a gap in the tape is a gap, not a straight line.

    The armed side is returned as `side_at_open` rather than discarded: a session that spent
    the whole day on one side of the flip books ZERO crossing events, and without the
    standing side that reads identically to "we had no level" — which is the honesty hole
    ENTER-only semantics open up if nobody prints the state they armed against.
    """
    if flip is None or not math.isfinite(float(flip)) or float(flip) <= 0:
        return FlipRead([], 0, None, None)
    flip_f = float(flip)
    events: list[dict] = []
    confirmed: str | None = None
    armed: str | None = None
    for i, sp in enumerate(spots):
        spot = _num(sp)
        if spot is None:
            continue
        raw = "above" if spot >= flip_f else "below"
        beyond = (abs(spot - flip_f) / flip_f) * 100.0 > band_pct
        if confirmed is None:
            confirmed = armed = raw              # arm; never fires
            continue
        if raw != confirmed and beyond:
            t = times[i] if i < len(times) else ""
            events.append(_event(t, "flip_cross", level=round(flip_f, 2), side=raw,
                                 spot=round(spot, 2), level_vintage=level_vintage))
            confirmed = raw
    return FlipRead(events, len(events), confirmed, armed)


@dataclass(frozen=True)
class WallRead:
    events: list[dict]
    inside_at_open: dict          # {"call": bool|None, "put": bool|None}
    closest_pct: dict             # {"call": float|None, "put": float|None}


def wall_touches(
    times: Sequence[str],
    spots: Sequence[float | None],
    *,
    call_wall: float | None,
    put_wall: float | None,
    within_pct: float = WALL_WITHIN_PCT,
    level_vintage: str | None = None,
) -> WallRead:
    """Wall-proximity ENTER events for the call and put wall.

    Port of `optionsAlerts.evalWallProximity`: distance is |spot − wall| / wall in percent,
    an event books only on an outside→inside transition, and the first observation arms (a
    session that opens inside the band books nothing at the open).

    `inside_at_open` and `closest_pct` are returned alongside for the same reason the flip
    read returns its armed side: zero touch events must not be readable as "price was never
    near a wall" when the truth may be "it started there" or "it got within 0.30%".
    """
    events: list[dict] = []
    inside_at_open: dict[str, bool | None] = {"call": None, "put": None}
    closest: dict[str, float | None] = {"call": None, "put": None}
    for side, wall in (("call", call_wall), ("put", put_wall)):
        w = _num(wall)
        if w is None or w == 0:
            continue
        etype = "call_wall_touch" if side == "call" else "put_wall_touch"
        prior_inside: bool | None = None
        for i, sp in enumerate(spots):
            spot = _num(sp)
            if spot is None:
                continue
            dist_pct = (abs(spot - w) / abs(w)) * 100.0
            if closest[side] is None or dist_pct < closest[side]:
                closest[side] = round(dist_pct, 3)
            inside = dist_pct <= within_pct
            if prior_inside is None:
                inside_at_open[side] = inside    # arm; never fires
            elif inside and prior_inside is False:
                t = times[i] if i < len(times) else ""
                events.append(_event(t, etype, level=round(w, 2), side=side,
                                     spot=round(spot, 2), dist_pct=round(dist_pct, 3),
                                     level_vintage=level_vintage))
            prior_inside = inside
    events.sort(key=lambda e: (e["t"], e["type"]))
    return WallRead(events, inside_at_open, closest)


@dataclass(frozen=True)
class SlopeStats:
    recent_mean: float
    mean: float
    std: float
    z: float
    n: int


def slope_stats(cumulative: Sequence[float], window: int) -> SlopeStats:
    """Trailing-window increment mean vs the session's own increment distribution.

    Port of `optionsAlerts.sessionSlopeStats`: the series is CUMULATIVE, so the honest
    slope is the per-stamp delta; sigma is the POPULATION sigma of those deltas (matching
    the TS, which divides by n).  A flat tape (std == 0) yields a non-finite z, which the
    caller must treat as "no read", never as zero.
    """
    vals = [float(v) for v in cumulative]
    deltas = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
    n = len(deltas)
    if n == 0:
        return SlopeStats(math.nan, math.nan, math.nan, math.nan, 0)
    mean = sum(deltas) / n
    var = sum((d - mean) ** 2 for d in deltas) / n
    std = math.sqrt(var)
    w = max(1, min(int(window), n))
    recent = deltas[n - w:]
    recent_mean = sum(recent) / len(recent)
    z = math.nan if std == 0 else (recent_mean - mean) / std
    return SlopeStats(recent_mean, mean, std, z, n)


@dataclass(frozen=True)
class BurstStat:
    effect_sigma: float      # (window mean − baseline mean) / baseline sigma — scale-free
    t: float                 # honest two-sample statistic (the #217 idiom)
    window_n: int
    baseline_n: int

    @property
    def fires(self) -> bool:
        return (math.isfinite(self.effect_sigma) and math.isfinite(self.t)
                and abs(self.effect_sigma) >= BURST_EFFECT_SIGMA and abs(self.t) >= BURST_T_MIN)


def window_vs_baseline(
    cumulative: Sequence[float],
    window: int,
    *,
    min_baseline: int = BURST_MIN_BASELINE,
) -> BurstStat:
    """Trailing increments vs the increments BEFORE them — effect size AND a real test statistic.

    TWO NUMBERS, BOTH NAMED HONESTLY.  `effect_sigma` is the difference in means over the
    baseline's per-observation sigma: scale-free, interpretable, and the quantity the Terminal's
    evaluator actually thresholds at 2.  `t` is the two-sample statistic for that same
    difference — same numerator, but divided by the standard error of a difference of means,
    `baseline_sigma · sqrt(1/w + 1/baseline_n)`.  They differ by `sqrt(w·b/(w+b))`, which runs
    2.24x at a 10-increment baseline and 3.08x by the close, so publishing one under the other's
    name would misstate the strength of every event by a factor that drifts through the session.
    Nothing here is called `z` unless it is standardized.

    NAMED DIVERGENCE from `optionsAlerts.sessionSlopeStats`, which scores the trailing window
    against a distribution that INCLUDES that window.  A sample inside its own reference caps
    the attainable ratio at sqrt((n-w)/w), so a 10-stamp window cannot reach 2 until n >= 50
    increments — at the archive's 5-minute cadence no burst of any violence could be booked
    before roughly 13:40 ET, and the family would be structurally dead for two thirds of every
    session.  Measured, not assumed: a replay with a 6x mid-day burst booked zero events under
    the ported formula.  `slope_stats` keeps that formula for the parity pin.

    Population sigma is retained (the TS convention).  A zero-variance baseline yields non-finite
    values, which the caller must read as "no read", never as zero.
    """
    vals = [float(v) for v in cumulative]
    deltas = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
    w = max(1, int(window))
    if len(deltas) < w + max(1, int(min_baseline)):
        return BurstStat(math.nan, math.nan, w, max(0, len(deltas) - w))
    base, win = deltas[: len(deltas) - w], deltas[len(deltas) - w:]
    b_n = len(base)
    b_mean = sum(base) / b_n
    b_std = math.sqrt(sum((d - b_mean) ** 2 for d in base) / b_n)
    if b_std == 0:
        return BurstStat(math.nan, math.nan, w, b_n)
    diff = (sum(win) / len(win)) - b_mean
    effect = diff / b_std
    t = diff / (b_std * math.sqrt(1.0 / len(win) + 1.0 / b_n))
    return BurstStat(effect, t, len(win), b_n)


def premium_bursts(
    times: Sequence[str],
    cumulative: Sequence[float],
    *,
    window: int = BURST_WINDOW_STAMPS,
    effect_thresh: float = BURST_EFFECT_SIGMA,
    min_baseline: int = BURST_MIN_BASELINE,
    rearm_sigma: float = BURST_REARM_SIGMA,
) -> list[dict]:
    """Premium-pace events: trailing increments against the earlier tape.

    Replayed forward — at each stamp the stats see only the tape realized SO FAR, never the
    whole day.  That is not an optimisation: letting the close inform a 10:15 event would make
    the record unreplayable against what was knowable at 10:15.

    Fires when BOTH gates clear: the interpretable effect size reaches `effect_thresh` sigmas
    AND the honest two-sample statistic clears BURST_T_MIN (so a thin baseline cannot mint an
    event).  One event books per contiguous run, and the run re-arms only once the effect drops
    `rearm_sigma` BELOW the cut — a ramp that oscillates across the line is one acceleration,
    not several.  A stretch with no read (flat baseline, too little tape) re-arms, so a later
    genuine run is never swallowed by an earlier one.

    The receipt carries `effect_sigma` and `t_stat` as separate fields because they differ by a
    session-drifting factor — see `window_vs_baseline`.  APPENDIX-B DEVIATION, deliberate: the
    contract sketch names an optional `z` on events, and this family publishes neither a `z` nor
    a bare `t`.  Not `z`, because the quantity IS a two-sample t and a field named `z` holding a
    t would misstate every event's strength by `sqrt(w·b/(w+b))`.  Not `t`, because an event's
    `t` is its TIMESTAMP — see _EVENT_RESERVED.
    """
    vals = [float(v) for v in cumulative]
    events: list[dict] = []
    fired = False
    for i in range(len(vals)):
        st = window_vs_baseline(vals[: i + 1], window, min_baseline=min_baseline)
        if not math.isfinite(st.effect_sigma):
            fired = False                     # no read: re-arm
            continue
        if fired and abs(st.effect_sigma) < effect_thresh - rearm_sigma:
            fired = False                     # dropped clear of the line: re-arm
        if not fired and abs(st.effect_sigma) >= effect_thresh and abs(st.t) >= BURST_T_MIN:
            events.append(_event(times[i] if i < len(times) else "", "premium_burst",
                                 effect_sigma=round(st.effect_sigma, 2),
                                 t_stat=round(st.t, 2),
                                 window_stamps=st.window_n,
                                 baseline_stamps=st.baseline_n))
            fired = True
    return events


@dataclass(frozen=True)
class PocketRead:
    events: list[dict]
    peak_share: float | None
    peak_at: str | None
    peak_level: float | None
    share_at_open: float | None
    share_at_open_t: str | None


def hot_pockets(
    frame: dict,
    *,
    share_pct: float = POCKET_SHARE_PCT,
    band: int = POCKET_BAND_STRIKES,
    min_total: float = POCKET_MIN_TOTAL,
    rearm_pct: float = POCKET_REARM_PCT,
    times: Sequence[str] | None = None,
) -> PocketRead:
    """Strike-concentration ENTER events from the archived net-premium grid.

    DIGEST-ORIGINAL (no Terminal evaluator exists — see POCKET_SHARE_PCT).  For each stamp:
    take the contiguous band of `2*band+1` strikes with the largest summed |net premium|,
    divide by the column's total |net premium|, and book an event when that share enters
    the threshold from below.  Denominator is the magnitude sum, never the signed net,
    because two large opposite-signed strikes can net to nearly zero and would fabricate a
    share above 100%.  Columns under `min_total` are skipped, not treated as 0% — the
    opening handful of trades is not a concentration finding.

    Hysteresis: once fired, the family re-arms only after the share drops `rearm_pct` points
    BELOW the threshold, so a share sitting on the line books one finding rather than five.

    The peak share and the share at the first evaluated stamp are returned alongside the
    events, for the same reason the flip and wall reads return their armed state: a session
    that was ALREADY concentrated when the tape starts books no ENTER event, and an empty
    event list must not be readable as "premium was never bunched up".
    """
    levels = [float(x) for x in ((frame or {}).get("price_levels") or [])]
    times = ([str(t) for t in times] if times is not None
             else [str(t) for t in ((frame or {}).get("time_steps") or [])])
    grid = ((frame or {}).get("grids") or {}).get("netprem") or []
    if not levels or not grid:
        return PocketRead([], None, None, None, None, None)
    n_cols = len(times) or max((len(r) for r in grid if isinstance(r, list)), default=0)
    totals = column_gross(frame)
    events: list[dict] = []
    fired = False
    seen_any = False
    width = 2 * int(band) + 1
    peak_share: float | None = None
    peak_at: str | None = None
    peak_level: float | None = None
    open_share: float | None = None
    open_at: str | None = None
    for j in range(n_cols):
        total = totals[j] if j < len(totals) else 0.0
        if total < min_total:
            continue                  # a thin column tells us nothing either way
        col: list[float] = []
        for li in range(len(levels)):
            row = grid[li] if li < len(grid) and isinstance(grid[li], list) else []
            cell = 0.0
            if j < len(row):
                v = _num(row[j])
                cell = abs(v) if v is not None else 0.0
            col.append(cell)
        best_sum, best_center = 0.0, None
        for li in range(len(col)):
            lo, hi = max(0, li - int(band)), min(len(col), li + int(band) + 1)
            s = sum(col[lo:hi])
            if s > best_sum:
                best_sum, best_center = s, li
        share = (best_sum / total) * 100.0 if total > 0 else 0.0
        lvl = round(levels[best_center], 2) if best_center is not None else None
        if peak_share is None or share > peak_share:
            peak_share, peak_at, peak_level = share, (times[j] if j < len(times) else ""), lvl
        inside = share >= share_pct
        if not seen_any:
            # First real reading ARMS: a session already concentrated when the tape starts
            # books no event (there is no moment of entry to stamp), and the standing share
            # is reported instead.
            seen_any = True
            open_share = round(share, 1)
            open_at = times[j] if j < len(times) else ""
            fired = inside
            continue
        if fired and share < share_pct - rearm_pct:
            fired = False                       # dropped clear of the line: re-arm
        if inside and not fired and lvl is not None:
            events.append(_event(times[j] if j < len(times) else "", "hot_pocket",
                                 level=lvl, share=round(share, 1), band_strikes=width))
            fired = True
    return PocketRead(events,
                      round(peak_share, 1) if peak_share is not None else None,
                      peak_at, peak_level, open_share, open_at)


def zero_dte_read(
    dte_doc: dict | None,
    *,
    session_date: str,
    share_pct: float = ZERO_DTE_SHARE_PCT,
    cadence_sec: int | None = None,
) -> tuple[dict, list[dict]]:
    """(zero_dte block, spike events) from the dated `dte_tide` archive.

    Port of `optionsAlerts.eval0dteShare`'s share arithmetic — |ncp| + |npp| of the "0d"
    bucket over every bucket's magnitude AT THE SAME STAMP — replayed across the archived
    stamps to find the session peak.  Same-session and same-stamp are both enforced: the
    archive's `asof` date must match the session (else the block is nulled with a plain-word
    note, the mixed-asof guard) and only stamps present in EVERY bucket are used (a ratio
    across two different clock readings is a fabricated ratio).

    MARKET-WIDE: the dated dte archive has no per-root split, so the block carries
    `scope: "market"` and every consumer must print that.
    """
    null = {
        "peak_share": None, "at": None, "scope": "market",
        "note_en": "same-day-expiry share is not in the record for this session",
        "note_zh": "本交易日没有当日到期占比的记录",
    }
    if not isinstance(dte_doc, dict):
        return null, []
    buckets = dte_doc.get("buckets")
    if not isinstance(buckets, dict):
        return null, []
    asof = str(dte_doc.get("asof") or "")
    if asof[:10] and asof[:10] != str(session_date)[:10]:
        return {**null,
                "note_en": "the same-day-expiry record on file is from another session, "
                           "so it is not used here",
                "note_zh": "在档的当日到期记录来自其他交易日，因此未采用"}, []

    # Only NON-EMPTY buckets take part in the cross-section.  `build_dte_tide_current` emits a
    # key for all five DTE buckets and leaves the untraded ones as `[]`, so intersecting stamp
    # sets across every declared key made ONE empty bucket veto the entire session — a day with
    # real tape reported "no same-day-expiry split" because, say, nothing traded 8-30 days out.
    # An empty bucket contributes zero magnitude, which is right; it must not also contribute a
    # veto.  Found by routing the fixtures through the real writer (the hand-written fixture had
    # populated all five and could not see this).
    keys = [k for k, v in buckets.items() if isinstance(v, list) and v]
    if "0d" not in keys:
        return null, []
    stamp_sets = [{str(r.get("t")) for r in buckets[k] if isinstance(r, dict)} for k in keys]
    common = set.intersection(*stamp_sets) if stamp_sets else set()
    common.discard("None")
    if not common:
        return null, []

    def mag_at(rows: Iterable[dict], stamp: str) -> float:
        for r in rows:
            if isinstance(r, dict) and str(r.get("t")) == stamp:
                out = 0.0
                for leg in ("ncp", "npp"):
                    try:
                        v = float(r.get(leg))
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(v):
                        out += abs(v)
                return out
        return 0.0

    # The dte archive's minute labels carry the `_minute_key` timezone defect, so every stamp
    # this block emits is corrected onto ET.  The cross-bucket alignment above uses the RAW
    # labels (they are internally consistent) — only what leaves the block is corrected.
    ordered = sorted(common)
    ck = clock_read(session_date, ordered, cadence_sec=cadence_sec,
                    family=CLOCK_FAMILY_TIDE)
    offset = ck.offset_min

    peak_share, peak_at = None, None
    open_share, open_at = None, None
    events: list[dict] = []
    prior_inside: bool | None = None
    for stamp in ordered:
        total = sum(mag_at(buckets[k], stamp) for k in keys)
        if total <= 0:
            # A stamp with no tape carries NO information about the share, so the arming state
            # is PRESERVED across it.  Resetting here (as this did) made a mid-session dead
            # minute re-arm the family, so a genuine 10% -> 90% entry immediately after it was
            # swallowed as "first observation", and share_at_open was overwritten with a
            # mid-session value.  Skip the stamp; do not forget what came before it.
            continue
        share = require_pct((mag_at(buckets["0d"], stamp) / total) * 100.0,
                            field="zero_dte_share_pct", hard_max=100.0)
        if share is None:
            continue
        if peak_share is None or share > peak_share:
            peak_share, peak_at = share, stamp
        inside = share >= share_pct
        if prior_inside is None:
            # First stamp with ACTUAL tape (zero-total stamps above never reach here), so the
            # reported opening share is a real reading rather than an empty minute.
            open_share, open_at = round(share, 1), stamp
        elif inside and prior_inside is False:
            events.append(_event(shift_label(stamp, offset), "zero_dte_spike",
                                 share=round(share, 1)))
        prior_inside = inside

    # N2: the tide clock governs THIS block.  When it cannot be pinned, the magnitudes still
    # publish (a share is not a moment) but every stamp goes null and the spike events — which
    # are nothing but stamps — are dropped, with the reason in plain words.
    if not ck.trusted:
        events = []
        peak_at = open_at = None

    # N7: how much of the session the cross-section actually rested on.  The empty-bucket veto is
    # fixed, but a bucket carrying 1 stamp out of 196 still collapses the intersection to that one
    # stamp — a "session peak" measured on a single minute.  Printing both numbers makes that
    # visible instead of leaving a reader to assume the peak spans the day.
    longest = max((len(buckets[k]) for k in keys), default=0)
    thin = bool(longest) and len(ordered) < max(2, longest // 2)

    block = {
        "peak_share": round(peak_share, 1) if peak_share is not None else None,
        "at": shift_label(peak_at, offset) if peak_at else None,
        "stamps_used": len(ordered),
        "stamps_in_longest_bucket": longest,
        "clock_offset_min": offset,
        "clock_ambiguous": bool(ck.ambiguous),
        # Standing state at the first stamp that carried tape: a day already over the threshold
        # when the tape starts books no ENTER event, and without this the peak and the empty
        # event list together read as a contradiction.  The stamp is printed so a reader can see
        # WHEN "the open" actually was — it is the first non-empty minute, not necessarily 09:30.
        "share_at_open": open_share,
        "share_at_open_t": shift_label(open_at, offset) if open_at else None,
        "threshold_pct": share_pct,
        "buckets_used": len(keys),
        "scope": "market",
        "note_en": "share of the whole market's running premium total, not this one name",
        "note_zh": "为全市场累计口径，并非该单一标的",
    }
    if ck.ambiguous:
        block["clock_note_en"] = (
            "the tape's own clock could not be matched to exchange time, so this share is "
            "reported without a time of day")
        block["clock_note_zh"] = "成交记录的时间无法对应交易所时间，因此该比重不标注具体时点"
    if thin:
        block["thin_note_en"] = (
            f"measured on {len(ordered)} minute(s) where the fullest expiry bucket has "
            f"{longest} — the buckets only overlap for part of the session")
        block["thin_note_zh"] = (
            f"仅基于 {len(ordered)} 分钟计算，而最完整的到期分组有 {longest} 分钟 —— "
            "各分组仅在部分时段重叠")
    return block, events


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Walls (open vs close) + migration
# ═══════════════════════════════════════════════════════════════════════════════

def wall_block(
    *,
    open_walls: dict | None,
    close_walls: dict | None,
    open_source: str | None,
    close_source: str | None,
) -> dict:
    """`{open:{call,put}, close:{call,put}, migrated}` with sources and a plain-word note.

    `migrated` is None — never False — when either end is unknown: "we could not compare"
    and "the walls did not move" are different facts, and collapsing them into False is the
    quiet lie this estate keeps finding.
    """
    def leg(w: dict | None) -> dict:
        w = w or {}
        return {"call": _num(w.get("call")), "put": _num(w.get("put"))}

    o, c = leg(open_walls), leg(close_walls)
    known = all(v is not None for v in (o["call"], o["put"], c["call"], c["put"]))
    migrated = None if not known else (o["call"] != c["call"] or o["put"] != c["put"])
    if migrated is True:
        en = "the heaviest call and put strikes are not where they were at the open"
        zh = "最重的看涨与看跌行权价与开盘时已不同"
    elif migrated is False:
        en = "the heaviest call and put strikes finished where they started"
        zh = "最重的看涨与看跌行权价收盘时与开盘时一致"
    else:
        en = "not enough of the record to compare the open and the close"
        zh = "记录不足，无法比较开盘与收盘"
    return {
        "open": {**o, "source": open_source},
        "close": {**c, "source": close_source},
        "migrated": migrated,
        "note_en": en,
        "note_zh": zh,
    }


def _num(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Coverage (plain words, nulls printed)
# ═══════════════════════════════════════════════════════════════════════════════

def coverage_block(
    *,
    session_date: str,
    cadence_sec: int,
    stamps: Sequence[str],
    read_stamps: Sequence[str] | None = None,
    clock: "ClockRead | None" = None,
    arc_minutes: int | None = None,
    axis_gap: int = 0,
    events_dropped_clock: int = 0,
    events_dropped_window: int = 0,
    missing_en: Sequence[str] = (),
    missing_zh: Sequence[str] = (),
) -> dict:
    """`{minutes, expected, gaps, ...}` plus a plain-word quality twin.

    `minutes` counts the stamps whose OBJECT was actually read, not the stamps the index
    promised.  The dated archives' indexes are best-effort — a session can be listed while
    its PUT failed — so counting the promise would overstate coverage exactly where the tape
    is thinnest.  `promised` and `absent_objects` carry the difference in the open.

    `expected` = cadence-aligned marks in the session window; `gaps` = cadence slots MISSING
    BETWEEN the first and last stamp read — the honest "the tape dropped out mid-session"
    number, kept apart from a session that simply started late or stopped early (which shows
    up as minutes < expected instead).  Both are computed on RAW labels: a constant clock
    offset cancels in a difference, so the arithmetic is unaffected by the label defect, while
    the `first`/`last` labels reported are corrected.
    """
    ck = clock or ClockRead(0, False, 0, (0,), None, "", "")
    clock_offset_min = ck.offset_min
    promised = sorted(str(s) for s in stamps if str(s))
    seen = ([str(s) for s in read_stamps if str(s)] if read_stamps is not None else promised)
    seen = sorted(seen)
    minutes = len(seen)
    expected = expected_stamps(session_date, cadence_sec)
    gaps = 0
    if minutes >= 2 and cadence_sec and int(cadence_sec) > 0:
        first, last = _stamp_minutes(seen[0]), _stamp_minutes(seen[-1])
        if first is not None and last is not None and last >= first:
            span_slots = int(((last - first) * 60) // int(cadence_sec)) + 1
            gaps = max(0, span_slots - minutes)
    absent = max(0, len(promised) - minutes)
    ratio = (minutes / expected) if expected else None
    # Sentence-case at the source: this is a standalone, sentence-initial disclosure
    # everywhere it is consumed (filmstripSentence's minutes===0 branch, its own
    # `cov.quality_en || '<fallback>'` ternary, lib/illus.py's null figure). The
    # fallback constants those call sites carry are already capitalized ("No intraday
    # record for this session"); leaving the real, common-case string lowercase made
    # the SAME sentence render two different ways depending on which path fired.
    if minutes == 0:
        en = "No intraday record for this session"
        zh = "本交易日没有盘中记录"
    elif ratio is not None and ratio >= 0.95 and gaps == 0:
        en = "The intraday record covers the whole session"
        zh = "盘中记录覆盖了整个交易时段"
    elif ratio is not None and ratio >= 0.70:
        en = "The intraday record covers most of the session"
        zh = "盘中记录覆盖了大部分交易时段"
    else:
        en = "The intraday record covers only part of the session"
        zh = "盘中记录仅覆盖部分交易时段"
    out = {
        "minutes": minutes,
        "expected": expected,
        "gaps": gaps,
        "promised": len(promised),
        "absent_objects": absent,
        "first": shift_label(seen[0], clock_offset_min) if seen else None,
        "last": shift_label(seen[-1], clock_offset_min) if seen else None,
        "cadence_sec": int(cadence_sec) if cadence_sec else None,
        "session_window_et": session_window_label(session_date),
        "clock_offset_min": int(clock_offset_min),
        "clock_ambiguous": bool(ck.ambiguous),
        "clock_residual_median_min": ck.residual_median_min,
        "clock_labels_outside_window": int(ck.labels_outside),
        # M9: which axis each figure was measured on.  The premium totals come from the newest
        # READABLE snapshot; the events and the counts above come from the stamp index.  When a
        # walk-back makes those differ, both numbers are printed rather than one standing in for
        # the other.
        "premium_total_minutes": int(arc_minutes) if arc_minutes is not None else None,
        "premium_total_axis_gap": int(axis_gap),
        "events_dropped_clock": int(events_dropped_clock),
        "events_dropped_window": int(events_dropped_window),
        "quality_en": en,
        "quality_zh": zh,
        "missing_en": list(missing_en),
        "missing_zh": list(missing_zh),
    }
    if ck.note_en:
        out["clock_note_en"], out["clock_note_zh"] = ck.note_en, ck.note_zh
    if absent:
        out["absent_note_en"] = (
            f"{absent} minute stamp(s) the record lists could not be read back, so they are "
            "not counted as covered")
        out["absent_note_zh"] = f"记录中列出的 {absent} 个分钟档无法读回，因此未计入覆盖"
    return out


def _label_in_session(label: object, session_date: str | date) -> bool:
    """True when a corrected 'HH:MM' label lies inside the session window.

    The digest's own invariant, enforced AFTER the clock shift rather than assumed: a label the
    correction pushed to 17:05 is not a session event, however plausible it looked before.
    Unparseable labels fail closed (dropped) — an event with no readable time has no receipt.
    """
    m = _stamp_minutes(label) if label else None
    if m is None:
        return False
    open_dt, close_dt = session_window_et(session_date)
    return (open_dt.hour * 60 + open_dt.minute) <= m <= (close_dt.hour * 60 + close_dt.minute)


def _stamp_minutes(stamp: str) -> int | None:
    """'HHMM' or 'HH:MM' → minutes since midnight ET.  None when unparseable."""
    s = str(stamp).replace(":", "")
    if len(s) != 4 or not s.isdigit():
        return None
    h, m = int(s[:2]), int(s[2:])
    if h > 23 or m > 59:
        return None
    return h * 60 + m


# ═══════════════════════════════════════════════════════════════════════════════
# 9. The record
# ═══════════════════════════════════════════════════════════════════════════════

def build_session_record(
    *,
    root: str,
    session_date: str,
    asof: str,
    frame: dict | None,
    stamps: Sequence[str],
    cadence_sec: int,
    spots_by_stamp: dict[str, float | None] | None = None,
    read_stamps: Sequence[str] | None = None,
    open_frame_walls: dict | None = None,
    close_frame_walls: dict | None = None,
    levels: dict | None = None,
    dte_doc: dict | None = None,
    tide_doc: dict | None = None,
    inputs: dict | None = None,
    arc_max_points: int = ARC_MAX_POINTS,
) -> dict:
    """Assemble the `options_session.v1` record for one root and one session.

    Every derivation is deterministic in its arguments — replaying the same archives
    reproduces this dict byte for byte apart from `asof`.

    `levels` is the EOD reference map (`flip`, `call_wall`, `put_wall`, `vintage`, `source`)
    read from the gex_state payload; its vintage is printed because the map a surface shows
    beside an intraday crossing may be the CLOSE's map rather than the one that stood during
    the session, and the reader is entitled to know which.
    """
    root = str(root).upper()
    frame = frame or {}
    raw_times = [str(t) for t in (frame.get("time_steps") or [])]
    # m3: derive from SORTED stamps so a re-ordered index cannot scramble the spot path or the
    # event axis (coverage_block already sorts; these did not).
    stamp_list = sorted(str(s) for s in stamps)

    # One clock read for this root's archive, over EVERY label (the surface frame's time_steps
    # and the index's stamps are the same clock).  A no-op when the labels are already exchange
    # time — see clock_read.
    ck = clock_read(session_date, stamp_list or raw_times, cadence_sec=cadence_sec,
                    family=CLOCK_FAMILY_SURFACE)
    offset = ck.offset_min
    times = [shift_label(t, offset) for t in raw_times]

    arc, nets = build_arc(frame, max_points=arc_max_points, times=times)
    gross = column_gross(frame)
    shape = classify_arc(nets, gross[-1] if gross else None)

    lv = dict(levels or {})
    flip_level = _num(lv.get("flip"))
    call_wall = _num(lv.get("call_wall"))
    put_wall = _num(lv.get("put_wall"))
    vintage = str(lv.get("vintage") or "")[:10] or None
    levels_same_session = bool(vintage) and vintage == str(session_date)[:10]

    # B2: a level map from ANOTHER session must not silently become the yardstick for THIS
    # session's crossings.  The record already refuses to print a foreign map as this session's
    # close; scoring events against it anyway would put that same rejected number inside every
    # receipt.  So the two level-dependent families are evaluated ONLY on a same-session map,
    # and their absence is disclosed in plain words like every other gap.
    level_ok = levels_same_session and (flip_level is not None or call_wall is not None
                                        or put_wall is not None)

    # Spot path: one entry per archived stamp, in stamp order.  An absent stamp stays None
    # and the evaluators skip it — a gap in the tape is a gap, never an interpolation.
    spots_map = spots_by_stamp or {}
    spots: list[float | None] = [_num(spots_map.get(s)) for s in stamp_list]
    ev_times = [shift_label(s, offset) for s in stamp_list]

    if level_ok:
        fr = flip_crossings(ev_times, spots, flip_level, level_vintage=vintage)
        wr = wall_touches(ev_times, spots, call_wall=call_wall, put_wall=put_wall,
                          level_vintage=vintage)
    else:
        fr = FlipRead([], 0, None, None)
        wr = WallRead([], {"call": None, "put": None}, {"call": None, "put": None})
    burst_events = premium_bursts(times, nets)
    pk = hot_pockets(frame, times=times)
    zero_dte, dte_events = zero_dte_read(dte_doc, session_date=session_date,
                                         cadence_sec=cadence_sec)

    # M1/M2: nothing time-stamped may ship when the clock could not be pinned, and any event
    # whose corrected label lands outside the session window is dropped rather than published at
    # an impossible time.  Both are counted so the drop is visible, never silent.
    #
    # The surface clock governs the surface-derived families ONLY.  `zero_dte_read` runs its own
    # clock read over the tide archive's own labels and has already suppressed its own events if
    # that read was untrusted — a surface archive nobody can date must not delete a tide finding
    # that was perfectly datable, and vice versa.
    surface_events = fr.events + wr.events + burst_events + pk.events
    events_dropped_clock = 0
    if not ck.trusted:
        events_dropped_clock, surface_events = len(surface_events), []
    events = sorted(surface_events + dte_events,
                    key=lambda e: (str(e.get("t") or ""), str(e.get("type"))))
    kept = [e for e in events if _label_in_session(e.get("t"), session_date)]
    events_dropped_window = len(events) - len(kept)
    events = kept

    counts: dict[str, int] = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1

    # N2: every time-derived fact is now read back OUT of the final events list, so a row of this
    # record can never disagree with itself.  A dropped crossing that still left `crosses: 1`
    # beside an empty event list — and `flip_crosses=1` beside `events_flip_cross=0` in the
    # ledger — was exactly that contradiction, frozen into a schema.  When a family loses events
    # its standing-state fields go null too: publishing "it ended above the flip" while
    # withholding the crossing that got it there is the same half-truth in a different field.
    kept_flip = [e for e in events if e["type"] == "flip_cross"]
    kept_wall = [e for e in events if e["type"] in ("call_wall_touch", "put_wall_touch")]
    flip_lost = len(fr.events) - len(kept_flip)
    wall_lost = len(wr.events) - len(kept_wall)
    flip_crosses = len(kept_flip)
    flip_last_side = None if flip_lost else fr.last_side
    flip_side_at_open = None if flip_lost else fr.side_at_open
    wall_inside_at_open = ({"call": None, "put": None} if wall_lost else wr.inside_at_open)

    market = _market_block(tide_doc, root=root, session_date=session_date,
                           cadence_sec=cadence_sec)

    missing_en: list[str] = []
    missing_zh: list[str] = []
    if not any(v is not None for v in spots):
        missing_en.append("price path through the session (level crossings not derivable)")
        missing_zh.append("盘中价格轨迹（无法推导价位穿越）")
    elif not level_ok:
        # B2: the families were switched off deliberately, and that is a different fact from
        # "nothing happened" — say which one it is.
        missing_en.append(
            "gamma-flip crossings and wall touches, because the only level map on file is not "
            "from this session")
        missing_zh.append("gamma 翻转穿越与墙位触及：在档价位结构图并非本交易日")
    if _walls_from_frame(open_frame_walls) is None and _walls_from_frame(close_frame_walls) is None:
        missing_en.append("intraday wall levels (option greeks are not in the archive yet)")
        missing_zh.append("盘中墙位（存档尚未包含期权希腊值）")
    if zero_dte.get("peak_share") is None:
        missing_en.append("same-day-expiry share for this session")
        missing_zh.append("本交易日的当日到期占比")
    # A tide document that exists but belongs to another session is just as absent for this
    # record's purposes, and must be disclosed the same way — not silently dropped.
    if market is None:
        missing_en.append("market-wide tape record for this session")
        missing_zh.append("本交易日的全市场成交记录")
    if events_dropped_clock:
        missing_en.append(
            f"the timing of {events_dropped_clock} noted moment(s), because the archived clock "
            "could not be matched to exchange time")
        missing_zh.append(f"{events_dropped_clock} 个时点的时间信息：存档时间无法对应交易所时间")
    if events_dropped_window:
        missing_en.append(
            f"{events_dropped_window} noted moment(s) that fell outside trading hours once the "
            "clock was corrected")
        missing_zh.append(f"{events_dropped_window} 个校正后落在交易时段之外的时点")
    # M9: the arc/pace/pocket figures come from the frame that loaded, which after a walk-back
    # covers fewer minutes than the stamp index the events and coverage were measured on.
    axis_gap = max(0, len(stamp_list) - len(raw_times)) if raw_times else 0
    if axis_gap:
        missing_en.append(
            f"the last {axis_gap} minute(s) from the premium totals: the newest readable "
            "snapshot stops short of the last minute on record")
        missing_zh.append(f"权利金合计缺少最后 {axis_gap} 分钟：最新可读快照未覆盖记录中的最后一分钟")

    # Close walls: the intraday archive first; the EOD map only when its vintage IS this
    # session (a map from another date is not this session's close, and saying so would be
    # the mixed-asof defect wearing a wall's clothes).
    eod_walls = ({"call": call_wall, "put": put_wall}
                 if (levels_same_session and (call_wall is not None or put_wall is not None))
                 else None)
    walls = wall_block(
        open_walls=_walls_from_frame(open_frame_walls),
        close_walls=_walls_from_frame(close_frame_walls) or eod_walls,
        open_source=("intraday archive" if _walls_from_frame(open_frame_walls) else None),
        close_source=("intraday archive" if _walls_from_frame(close_frame_walls)
                      else (lv.get("source") if eod_walls else None)),
    )
    walls["inside_at_open"] = wall_inside_at_open
    # closest_pct is a pure extremum over the price walk and asserts no moment, so it survives a
    # drop; inside_at_open is an "at the open" claim and does not.
    walls["closest_pct"] = wr.closest_pct
    walls["within_pct"] = WALL_WITHIN_PCT
    # Greek coverage is the honest qualifier on any intraday wall: the archive's `coverage`
    # is a FRACTION, and pct_from_fraction asserts that at the seam rather than trusting it
    # (the x100 class has shipped twice in this estate).
    walls["greek_coverage_pct"] = pct_from_fraction(
        _num(((frame.get("coverage") or {}) if isinstance(frame, dict) else {}).get("greeks")),
        field="surface_frame.coverage.greeks")

    # m1: never interpolate a bare `None` into copy — a reader seeing "the close of None" learns
    # nothing and it reads as a bug.  Each branch below states the actual situation instead.
    if flip_level is None:
        flip_note_en = "no gamma flip level on file for this session"
        flip_note_zh = "本交易日没有在档的 gamma 翻转价位"
    elif not vintage:
        flip_note_en = ("the gamma flip level on file carries no date, so crossings are not "
                        "read against it")
        flip_note_zh = "在档的 gamma 翻转价位没有日期，因此不用于判断穿越"
    elif levels_same_session:
        flip_note_en = ("the gamma flip level is this session's own closing map, so "
                        "crossings are read against where the day finished")
        flip_note_zh = "gamma 翻转价位取自本交易日收盘结构图，穿越以收盘价位为参照"
    else:
        flip_note_en = (f"the gamma flip level on file is from the close of {vintage}, another "
                        "session, so crossings are not read against it")
        flip_note_zh = f"在档的 gamma 翻转价位取自 {vintage}（其他交易日），因此不用于判断穿越"
    flip_block = {
        # N2: derived from the FINAL events list, never from the pre-drop walk.
        "crosses": int(flip_crosses),
        "last_side": flip_last_side,
        "side_at_open": flip_side_at_open,
        "level": flip_level,
        "level_vintage": vintage,
        "level_is_this_session": levels_same_session,
        "band_pct": FLIP_BAND_PCT,
        "note_en": flip_note_en,
        "note_zh": flip_note_zh,
    }

    return {
        "schema": SCHEMA,
        "root": root,
        "session_date": str(session_date),
        "asof": asof,
        "arc": arc,
        "arc_points_full": len(nets),
        "arc_method": ARC_METHOD,
        "net_close": round(nets[-1], 0) if nets else None,
        "arc_shape": shape.tag,
        "arc_shape_en": shape.en,
        "arc_shape_zh": shape.zh,
        "arc_receipts": shape.receipts,
        "events": events,
        "event_counts": counts,
        "zero_dte": zero_dte,
        "pockets": {
            "peak_share": pk.peak_share,
            "at": pk.peak_at,
            "level": pk.peak_level,
            "share_at_open": pk.share_at_open,
            "share_at_open_t": pk.share_at_open_t,
            "threshold_pct": POCKET_SHARE_PCT,
            "band_strikes": 2 * POCKET_BAND_STRIKES + 1,
            "note_en": "the largest share of the day's running premium total that sat in "
                       "any three neighbouring strikes",
            "note_zh": "当日累计权利金中，相邻三个行权价所占的最高比重",
        },
        "walls": walls,
        "flip": flip_block,
        "levels": {
            "flip": flip_level,
            "call_wall": call_wall,
            "put_wall": put_wall,
            "spot_close": _num(lv.get("spot")),
            "vintage": lv.get("vintage"),
            "source": lv.get("source"),
            "basis_en": "levels read from the end-of-day options map, not from the "
                        "intraday tape",
            "basis_zh": "价位取自收盘期权结构图，而非盘中成交",
        },
        "market": market,
        "coverage": coverage_block(
            session_date=session_date, cadence_sec=cadence_sec, stamps=stamps,
            read_stamps=read_stamps, clock=ck,
            arc_minutes=len(raw_times), axis_gap=axis_gap,
            events_dropped_clock=events_dropped_clock,
            events_dropped_window=events_dropped_window,
            missing_en=missing_en, missing_zh=missing_zh),
        "inputs": inputs or {},
        "authority_tier": "display",
        "reliability": {
            "note_en": "a descriptive record of what the tape and the level map did — "
                       "no forecast, no ranking, no direction call",
            "note_zh": "仅为成交与价位结构的记录性描述 — 不含预测、排名或方向判断",
        },
    }


def _walls_from_frame(w: dict | None) -> dict | None:
    """Surface-frame walls (`{flip, callWall, putWall}`) → `{call, put}`; None when absent."""
    if not isinstance(w, dict):
        return None
    call, put = _num(w.get("callWall")), _num(w.get("putWall"))
    if call is None and put is None:
        return None
    return {"call": call, "put": put}


def _hhcolonmm(stamp: str) -> str:
    """'HHMM' → 'HH:MM'; an already-colonized or unparseable stamp passes through."""
    s = str(stamp)
    if ":" in s:
        return s
    return f"{s[:2]}:{s[2:]}" if len(s) == 4 and s.isdigit() else s


def _market_block(tide_doc: dict | None, *, root: str, session_date: str,
                  cadence_sec: int | None = None) -> dict | None:
    """Market-wide context from the dated tide archive, or None when it is another session.

    Only two facts are lifted: the market's closing cumulative signed call/put premium and
    this root's own line in `top_net_impact`.  Nothing is divided across the two documents
    (the surface archive and the tide are different pipelines with different as-ofs, and a
    ratio across them would be a mixed-asof ratio).
    """
    if not isinstance(tide_doc, dict):
        return None
    doc_date = str(tide_doc.get("session_date") or "")[:10]
    if doc_date and doc_date != str(session_date)[:10]:
        return None
    minutes = tide_doc.get("minutes")
    close = None
    offset = 0
    if isinstance(minutes, list) and minutes:
        labels = [str(m.get("t") or "") for m in minutes if isinstance(m, dict)]
        if labels:
            offset = clock_read(session_date, labels, cadence_sec=cadence_sec,
                                family=CLOCK_FAMILY_TIDE).offset_min
        last = minutes[-1] if isinstance(minutes[-1], dict) else {}
        close = {"t": shift_label(last.get("t"), offset),
                 "ncp": _num(last.get("ncp")),
                 "npp": _num(last.get("npp"))}
    root_line = None
    for r in (tide_doc.get("top_net_impact") or []):
        if isinstance(r, dict) and str(r.get("root", "")).upper() == root:
            root_line = {"net_prem_soft": _num(r.get("net_prem_soft")),
                         "gross": _num(r.get("gross"))}
            break
    return {
        "scope": "market",
        "session_date": doc_date or str(session_date),
        "clock_offset_min": offset,
        "close": close,
        "this_root_in_market_top": root_line,
        "note_en": "market-wide signed tape totals; the sign is a soft read, not confirmed "
                   "against the quote",
        "note_zh": "全市场带方向的成交合计；方向为弱读数，未经报价确认",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Ledger row (one per date × root)
# ═══════════════════════════════════════════════════════════════════════════════

LEDGER_COLUMNS = [
    "date", "root", "arc_shape", "net_close", "arc_points",
    "events_total", "events_flip_cross", "events_call_wall_touch",
    "events_put_wall_touch", "events_premium_burst", "events_hot_pocket",
    "events_zero_dte_spike",
    "zero_dte_peak_share", "zero_dte_peak_at",
    "wall_call_open", "wall_put_open", "wall_call_close", "wall_put_close",
    "wall_migrated", "flip_crosses", "flip_last_side", "flip_level",
    # B2: the vintage and source of the level map every flip/wall figure in this row was
    # measured against, and whether it belonged to this session at all.  Without these a reader
    # cannot tell a genuine zero-crossing day from a day whose levels were unusable — and the
    # schema is being fixed BEFORE any row exists, because a ledger column added after rows
    # accrue leaves every historical row permanently null.
    "levels_vintage", "levels_source", "levels_is_this_session",
    "coverage_minutes", "coverage_expected", "coverage_gaps",
    "coverage_absent_objects", "clock_offset_min", "clock_ambiguous",
    "schema", "asof",
]


def ledger_row(record: dict) -> dict:
    """The one flat row this session contributes to `data/options_session/ledger.parquet`.

    Column order is pinned by LEDGER_COLUMNS so a re-run cannot silently reshape the store.
    Every count is derived from the record, so the ledger can never disagree with the
    payload it was built from.
    """
    counts = record.get("event_counts") or {}
    walls = record.get("walls") or {}
    w_open = walls.get("open") or {}
    w_close = walls.get("close") or {}
    flip = record.get("flip") or {}
    zdte = record.get("zero_dte") or {}
    cov = record.get("coverage") or {}
    events = record.get("events") or []
    return {
        "date": record.get("session_date"),
        "root": record.get("root"),
        "arc_shape": record.get("arc_shape"),
        "net_close": record.get("net_close"),
        "arc_points": record.get("arc_points_full"),
        "events_total": len(events),
        "events_flip_cross": int(counts.get("flip_cross", 0)),
        "events_call_wall_touch": int(counts.get("call_wall_touch", 0)),
        "events_put_wall_touch": int(counts.get("put_wall_touch", 0)),
        "events_premium_burst": int(counts.get("premium_burst", 0)),
        "events_hot_pocket": int(counts.get("hot_pocket", 0)),
        "events_zero_dte_spike": int(counts.get("zero_dte_spike", 0)),
        "zero_dte_peak_share": zdte.get("peak_share"),
        "zero_dte_peak_at": zdte.get("at"),
        "wall_call_open": w_open.get("call"),
        "wall_put_open": w_open.get("put"),
        "wall_call_close": w_close.get("call"),
        "wall_put_close": w_close.get("put"),
        "wall_migrated": walls.get("migrated"),
        "flip_crosses": flip.get("crosses"),
        "flip_last_side": flip.get("last_side"),
        "flip_level": flip.get("level"),
        "levels_vintage": (record.get("levels") or {}).get("vintage"),
        "levels_source": (record.get("levels") or {}).get("source"),
        "levels_is_this_session": flip.get("level_is_this_session"),
        "coverage_minutes": cov.get("minutes"),
        "coverage_expected": cov.get("expected"),
        "coverage_gaps": cov.get("gaps"),
        "coverage_absent_objects": cov.get("absent_objects"),
        "clock_offset_min": cov.get("clock_offset_min"),
        "clock_ambiguous": cov.get("clock_ambiguous"),
        "schema": record.get("schema"),
        "asof": record.get("asof"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Public aliases for the builder shell
# ═══════════════════════════════════════════════════════════════════════════════
# The derivations above keep their terse private names for readability inside the module;
# these are the names the I/O shell (scripts/build_session_digest.py) and the tests use, so
# no caller reaches through an underscore.

as_session_date = _as_date
as_float = _num
walls_from_frame = _walls_from_frame
hhcolonmm = _hhcolonmm
