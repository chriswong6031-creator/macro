"""engine/entry_radar/challengers.py — C1 / C2 / C4, pure construction (W3, §18 A5).

BOUNDARY (contract §2), stated before anything else
---------------------------------------------------
``engine/washout_turn.py`` is the per-name **WEEKLY** washout-turn watch organ and
``engine/mtf_upturn.py`` is the TS-R3 multi-timeframe upturn organ (K-of-N legs,
registered expected-NULL).  Both are ADJACENT display organs at a different GRAIN
(weekly / multi-week) inside a different PRODUCT (watch vocabulary, not an episode
ledger).  C1/C2 live at **1D-LIVE motion** grain on a 5-minute sampled path and
C4 is a **stratification-only** 2D/3D feature set; they produce episodes,
candidates and provenance.  Name similarity is not identity.  Neither organ is
imported here, neither is modified by this lane, and the house precedent for
stating the distinction in the docstring is ``engine/washout_turn.py:1-5``.

WHAT IS HERE
------------
Three constructions and their frozen spec blocks:

  ``C1_1D_LIVE_WASHOUT@1``  the arm IS the candidate (§4's frozen promotion law)
  ``C2_1D_TURN@1``          exactly six single-feature turn variants
  ``C4_MTF_TURN@1``         stratification features that CANNOT fire

plus the A5.1 provisional-daily reconstruction they all read.

WHAT IS NOT HERE, ON PURPOSE
----------------------------
No network, no env lookup, no filesystem, no clock.  Every input is passed in.
The live evaluator is PR-4; the durable ledger is PR-5 and is the only lane that
may ever write.  A pure module cannot leak a durable write, and this one owns no
function that could open one.

No outcome of any kind.  No forward return, no MFE/MAE, no false-start, no hit
rate, no top-k, no "best variant".  W3 predates the first read by construction
(§18 A5.0), and the six variants are six recorded experts — never a ranked list.

C4 CANNOT FIRE — AND THAT IS STRUCTURAL (`DNR:KILL-WASHOUT-TURN`)
------------------------------------------------------------------
The killed construction is *higher-timeframe washout DEPTH used as arming
authority*.  Radar's fence is not a convention: C4 has **no entry-event family**
(`entry_events.FAMILY_KEYS` mints none — A5.8), so it cannot address an event;
:func:`assert_can_fire` refuses its detector id; and ``C4State`` exposes no arm,
candidate, promote or fire API at all.  Depth is context, recorded beside the
turn booleans and never inside them.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from engine import session_anchor
from engine.entry_radar import indicator_core as ic
from engine.entry_radar.contracts import iso
from engine.entry_radar.entry_events import (
    RADAR_1D_LIVE_WASHOUT_SUBTYPE,
    RADAR_1D_TURN_SUBTYPES,
    STRATIFICATION_ONLY_DETECTOR_IDS,
    EntryEvent,
    EntryEventError,
    build_radar_native_event,
    sha16,
)
from engine.entry_radar.readings import DetectorReading
from engine.session_digest import session_window_et

# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------

C1_DETECTOR_ID = "C1_1D_LIVE_WASHOUT@1"
C1_VERSION = 1
C1_GRAIN = "1D_live"
C1_BAR_FAMILY = "provisional_daily_5min_sampled"

C2_DETECTOR_ID = "C2_1D_TURN@1"
C2_VERSION = 1
C2_GRAIN = "1D_live"
C2_BAR_FAMILY = "provisional_daily_5min_sampled"

C4_DETECTOR_ID = "C4_MTF_TURN@1"
C4_VERSION = 1
C4_GRAIN = "2D_3D_absolute_anchor"
C4_BAR_FAMILY = "radar_absolute_session_bucket"

#: The 5-minute decision cadence (§7).  Named because it rides C1's spec hash:
#: a detector re-cut at a different cadence is a different detector.
SAMPLE_INTERVAL_MINUTES = 5

#: A minute aggregate covering ``[t, t+1m)`` is knowable at ``t + 60s`` and not
#: one second earlier.  This is THE point-in-time primitive of the whole live
#: reconstruction: every leak in a live-oscillator replay is some version of
#: reading a bar before it closed.
MINUTE_BAR_SECONDS = 60

#: C2f's ATR multiple (§18 A5.3).  A firing-relevant constant — it rides the hash.
C2F_ATR_MULTIPLE = 0.5

#: C4's higher-timeframe washout window, in NATIVE bars of that grain (§18 A5.5).
MTF_OS_WINDOW = 8

#: §10 episode hygiene, frozen: re-arm after an episode ends requires confirmed
#: 1D K above the floor on two consecutive sessions, or 15 elapsed sessions —
#: whichever comes first.  Defined here, above the spec blocks, because C1_SPEC
#: carries all three BY VALUE (W3-4).
REARM_K_FLOOR = 50
REARM_K_SESSIONS = 2
REARM_MAX_SESSIONS = 15

#: C4's grains.  Two and three sessions on the ABSOLUTE anchor — never G0's
#: per-symbol listing-anchored grid and never a calendar business-day bin.
MTF_GRAINS: tuple[int, ...] = (2, 3)

#: Radar's OWN absolute-anchor era string (§4 indicator-core law (d), §18 A5.5).
#: Distinct from ``engine/confluence_tiers``'s ``abs-session-2026-08-06`` so a
#: Radar bucket can never be pooled with a cascade bucket by accident.
RADAR_MTF_ANCHOR_ERA = "radar-abs-session-2026-08-14"

#: Price-basis markers.  A basis MISMATCH is an availability fact, never a False.
BASIS_ADJUSTED = "adjusted"
BASIS_RAW = "raw"

#: The six registered C2 variants, in the amendment's order.  FROZEN: no seventh
#: variant, no combination, no "2 of 6" (§18 A5.3).  RE-EXPORTED, not restated —
#: the enum's one source is ``entry_events.RADAR_1D_TURN_SUBTYPES``, so the
#: detector's variant list and the event schema's subtype set cannot drift apart.
C2_VARIANTS: tuple[str, ...] = RADAR_1D_TURN_SUBTYPES

C2_PRIMARY_VARIANT = "c2a_kd_cross"


class ChallengerError(EntryEventError):
    """A malformed challenger input or an illegal challenger operation."""


class StratificationOnly(ChallengerError):
    """A detector registered ``role=stratification_only`` was asked to fire.

    `DNR:KILL-WASHOUT-TURN` made mechanical.  C4's features exist to STRATIFY C2
    episodes in later analysis; an arming interaction of the form
    ``turn AND recent_washout -> candidate`` is the killed construction re-cut at
    a new grain and is refused here rather than merely discouraged.
    """


# ---------------------------------------------------------------------------
# frozen spec blocks — the hash of each IS that detector's identity
# ---------------------------------------------------------------------------

C1_SPEC: dict[str, Any] = {
    "detector_id": C1_DETECTOR_ID,
    "version": C1_VERSION,
    "grain": C1_GRAIN,
    "bar_family": C1_BAR_FAMILY,
    "authority_source": "contract §18 A5.2 (2026-08-14 pre-outcome lock)",
    "arm_condition": "K_T < 20",
    "arm_input": ("canonical StochRSI %K over confirmed closes through D-1 plus the "
                  "A5.1 provisional close observed at T"),
    "oversold_threshold": ic.OVERSOLD,
    "indicator_core": ic.INDICATOR_CORE,
    "promotion_rule": ("candidate_at == first_armed_at == observed_at — for the "
                       "highest-recall lane the ARM is the candidate (§4 frozen)"),
    "candidates_per_episode": 1,
    "later_observations": ("path observations, never a second candidate every five "
                           "minutes (A5.2)"),
    "depth_requirement": ("none — no zero print is required and no depth is rewarded; "
                          "K=1 and K=19 satisfy the same arm condition (§4)"),
    "sampling_law": ("session-open-anchored intervals; the value of an interval is the "
                     "LAST minute-aggregate close in it (A5.1)"),
    "interval_minutes": SAMPLE_INTERVAL_MINUTES,
    "minute_knowability": ("a minute aggregate is knowable at bar_start + "
                           "minute_bar_seconds; observation T admits only bars knowable "
                           "<= T"),
    # W3-4: BY VALUE.  The knowability offset decides WHICH bars an observation
    # may read, so shortening it would change what fires without moving the hash.
    "minute_bar_seconds": MINUTE_BAR_SECONDS,
    # W3-1: a tape and a daily frame on different adjustment bases cannot be
    # concatenated — the seam alone fabricates a move, and a fabricated move
    # fabricates a cross.  The whole observation refuses.
    "price_basis_law": ("the intraday tape's basis must equal the confirmed daily "
                        "basis; on disagreement the ENTIRE observation is unavailable "
                        "and every predicate is null (§5 price-basis row)"),
    # W3-5: `stale` is in the §5 vocabulary and must be reachable.
    "freshness_law": ("the confirmed history must run up to the reference session "
                      "immediately preceding the evaluated session; an older feed is "
                      "`stale` with condition_met null, never a measured non-fire "
                      "(§7 stale demotion, #5555)"),
    "provisional_close_rule": ("append-not-replace — the latest sampled close <= T is "
                               "APPENDED as the current session's provisional daily "
                               "close; no prior confirmed close is ever replaced (§7.1)"),
    "confirmed_history": ("adjusted daily closes through the PRIOR session only; the "
                          "current session's final close is unknowable intraday (§5)"),
    "session_scope": "RTH only; extended-hours prints never enter the path (§7)",
    "confirmed_mirror": ("the confirmed-daily recipe is a reading STATE of this same "
                         "mechanism; no C1_CONFIRMED arena detector is minted (A5.2)"),
    # W3-4: numbers BY VALUE from the module constants, never hand-typed into
    # prose.  A prose "15 sessions" beside a constant of 20 is a spec that lies
    # with a stable hash.
    "rearm_law": {
        "rule": ("§10 episode hygiene only — confirmed K above the floor on N "
                 "consecutive sessions, or max_sessions elapsed, whichever first"),
        "confirmed_k_floor": REARM_K_FLOOR,
        "consecutive_sessions": REARM_K_SESSIONS,
        "max_sessions": REARM_MAX_SESSIONS,
    },
}

C2_SPEC: dict[str, Any] = {
    "detector_id": C2_DETECTOR_ID,
    "version": C2_VERSION,
    "grain": C2_GRAIN,
    "bar_family": C2_BAR_FAMILY,
    "authority_source": "contract §18 A5.3 (2026-08-14 pre-outcome lock)",
    "base": "a strict subset of C1 episodes",
    "eligibility": ("eligible from the underlying C1 episode's FIRST ARM, inside the same "
                    "nonterminal C1 episode"),
    "current_oversold_requirement": ("NONE — the washout is the episode history and the "
                                     "turn is the event; a variant may fire after K has "
                                     "recovered above 20 (A5.3)"),
    "pre_arm_rule": "no variant fires before its C1 arm",
    "variant_count": 6,
    "variants": {
        "c2a_kd_cross": "K_T > D_T AND K_prev <= D_prev",
        "c2b_k_slope": "K_T > K_prev (strict; equality does not fire)",
        "c2c_higher_k_low": (
            "causal pivot — a local K low at observation j is knowable only at j+1 via "
            "K[j-1] > K[j] AND K[j+1] >= K[j]; fires when the newly-confirmed pivot low "
            "is strictly greater than the preceding confirmed K pivot low in the same C1 "
            "episode.  No centered window; no pivot needing samples beyond the confirming "
            "observation"),
        "c2d_hist_trough": "H_T > H_prev AND H_prev <= H_prev2",
        "c2e_hist_curvature": ("H_T - 2*H_prev + H_prev2 > 0 (may lawfully fire before "
                               "c2d — curvature can turn positive while slope is still "
                               "negative; intentional)"),
        # W3-13: the non-positive-ATR refusal was implemented and unstated.  A
        # zero or negative ATR makes the threshold meaningless (every rebound
        # clears it), so the variant is unavailable rather than trivially true.
        "c2f_rebound_atr": ("last_sampled_price_T - running_sampled_low_T >= "
                            "0.5 * ATR_prior_confirmed; a non-positive "
                            "prior-confirmed ATR => unavailable, never a trivial pass"),
    },
    "primary_variant": C2_PRIMARY_VARIANT,
    "combination_rule": ("NONE — no seventh variant, no combination detector, no '2 of 6', "
                         "no hand-weighted composite; six mechanistically distinct experts "
                         "are never deduped into one generic C2 fire (A5.3)"),
    "histogram_definition": "RSI-MACD line minus signal; never a price MACD",
    "rebound_atr_multiple": C2F_ATR_MULTIPLE,
    "rebound_low_law": ("running_sampled_low = the minimum 5-minute SAMPLED last-price "
                        "observation from today's RTH open through T — never a raw "
                        "one-minute low (§7.1 frozen replay rule)"),
    "atr_law": ("true-range Wilder ATR(14) frozen from the PRIOR confirmed daily session; "
                "never today's eventual EOD high/low/close; no close-proxy fallback"),
    "basis_law": ("numerator and ATR on the same adjusted basis; basis disagreement or a "
                  "missing ATR makes the variant UNAVAILABLE, never False"),
    "prev_definition": ("_prev is the immediately preceding LAWFUL observation for that "
                        "variant's own inputs"),
    # W3-4: c2f reads the sampled path directly, so the sampling grid and the
    # minute-knowability offset are firing-relevant for C2 and ride ITS hash too.
    "sampling": {
        "interval_minutes": SAMPLE_INTERVAL_MINUTES,
        "minute_bar_seconds": MINUTE_BAR_SECONDS,
        "law": ("session-open-anchored intervals; running_sampled_low is the minimum "
                "over the sampled path, never over the raw minute lows"),
    },
    # W3-8: pre-arm is an EVALUATED non-fire, not a missing input.  The episode
    # clause of the C2 condition is known-False, so the conjunction is False
    # without running the turn sub-predicate — which stays UNCALLED so the c2c
    # pivot ledger holds only in-episode pivots.
    "pre_arm_encoding": ("condition_met False with features.eligible False; the turn "
                         "sub-predicate is never evaluated.  An UNAVAILABLE or STALE "
                         "input dominates and yields null"),
    # W3-1 / W3-5: the same two refusals C1 carries, restated where C2 reads them.
    "price_basis_law": ("tape basis must equal the confirmed daily basis; on "
                        "disagreement every variant is unavailable and null"),
    "freshness_law": ("a confirmed history older than the reference session "
                      "immediately preceding the evaluated session is `stale` and "
                      "yields null, never a measured non-fire"),
    "indicator_core": ic.INDICATOR_CORE,
    "candidates_per_episode_per_variant": 1,
}

C4_SPEC: dict[str, Any] = {
    "detector_id": C4_DETECTOR_ID,
    "version": C4_VERSION,
    "grain": C4_GRAIN,
    "bar_family": C4_BAR_FAMILY,
    "authority_source": "contract §18 A5.5 (2026-08-14 pre-outcome lock)",
    "role": "stratification_only",
    "can_fire": False,
    "firing_fence": ("DNR:KILL-WASHOUT-TURN — no expression of the form "
                     "`turn AND recent_washout -> candidate` exists anywhere; C4 has no "
                     "entry-event family and no lifecycle transition (A5.5/A5.8)"),
    "base_population": "the primary C2a candidate base only",
    "anchor": "engine.session_anchor.session_positions(idx) // n (ABSOLUTE session calendar)",
    "anchor_era": RADAR_MTF_ANCHOR_ERA,
    "anchor_rejected": ("never G0's per-symbol listing-anchored 3D grid, never Terminal's "
                        "calendar 2B grid, never canon.resample_sessions' first-series-bar "
                        "phase, never a calendar business-day resample"),
    "grains": list(MTF_GRAINS),
    "bucket_value": "the last confirmed daily close inside the bucket",
    "turn_primitive": ("strict canonical StochRSI K x D bullish cross on the grain's own "
                       "close series: K > D AND K_prev <= D_prev"),
    "turn_depth_requirement": "none — no oversold depth is baked into the turn booleans",
    "recent_os": "rolling_min(D, 8 native bars) < 20, recorded SEPARATELY per grain",
    "recent_os_window": MTF_OS_WINDOW,
    "recovery_count": ("1 + int(d2.turn) + int(d3.turn) — descriptive stratification, not "
                       "a score and not a monotone bullish bonus"),
    "confirmed_bar_law": ("registered features use only 2D/3D buckets lawfully CONFIRMED "
                          "at the C2 candidate timestamp; a partial bucket appears only as "
                          "separate provisional debug context and never rewrites the "
                          "snapshot attached to an earlier C2 event"),
    "indicator_core": ic.INDICATOR_CORE,
}


def c1_spec_hash() -> str:
    """Stable 16-hex identity of C1's frozen spec block."""
    return sha16(C1_SPEC)


def c2_spec_hash() -> str:
    return sha16(C2_SPEC)


def c4_spec_hash() -> str:
    return sha16(C4_SPEC)


#: Detector ids that may never emit.  CONSUMED from ``entry_events``, not derived
#: here (W3-7): the event doors and the lifecycle doors must refuse the same set,
#: and two derivations of "the same set" is how one of them ends up shorter.
#: ``tests/test_entry_radar_w3_c4.py`` pins that every spec declaring
#: ``role=stratification_only`` appears in it, and nothing else does.
STRATIFICATION_ONLY_IDS: frozenset[str] = frozenset(STRATIFICATION_ONLY_DETECTOR_IDS)


def assert_can_fire(detector_id: str) -> None:
    """Raise ``StratificationOnly`` for a detector that may never emit.

    Called on every path that could produce a candidate — lifecycle transition
    here, event construction in ``entry_events`` — off ONE list, so a detector
    cannot be fenced at one door and open at another.
    """
    if detector_id in STRATIFICATION_ONLY_IDS:
        raise StratificationOnly(
            f"{detector_id} is registered role=stratification_only and is structurally "
            f"unable to emit a candidate event or a lifecycle transition: its features "
            f"stratify C2 episodes in later analysis and nothing else.  An arming "
            f"interaction of the form `turn AND recent_washout -> candidate` is "
            f"DNR:KILL-WASHOUT-TURN's interaction form re-cut at a new grain and would "
            f"require a pre-declared registration re-opening that kill by name with the "
            f"NC-2 proximity arm (contract §4, §18 A5.5)")


# ---------------------------------------------------------------------------
# §13 lifecycle, reached through a deferred import
# ---------------------------------------------------------------------------

_LIFECYCLE: Any = None


def lifecycle() -> Any:
    """The ``detectors`` module, imported on first use.

    IMPORT DIRECTION IS THE REASON, not laziness.  ``detectors`` is the REGISTRY
    and it imports the frozen spec blocks FROM this module — the ``g0_adapter``
    pattern, where the registry reads the implementation so the two cannot drift.
    A module-level import back would close that into a cycle.  Deferring it keeps
    the dependency one-way without the alternative, which is a second copy of the
    §13 state machine living here.
    """
    global _LIFECYCLE
    if _LIFECYCLE is None:
        from engine.entry_radar import detectors as _detectors
        _LIFECYCLE = _detectors
    return _LIFECYCLE


@dataclass
class DetectorEpisode:
    """One in-memory episode trace for one ``(ticker, detector_id)``.

    Not a store.  Not durable.  §10's "one live episode per (ticker, detector_id)"
    made mechanical: :meth:`transition` validates every move against
    ``detectors.ALLOWED_TRANSITIONS``, and a terminal episode has no exits at all,
    because an episode that could be re-armed in place would silently rewrite its
    own history.
    """

    ticker: str
    detector_id: str
    state: Any = None
    variant: str | None = None
    first_armed_at: str | None = None
    candidate_at: str | None = None
    last_observed_at: str | None = None
    transitions: list[Any] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    #: ``event_id -> signal_ts`` for everything this episode minted.  Kept so a
    #: consumer can answer "did this event EXIST yet?" without re-reading the event
    #: store — the question :func:`lawful_evidence_refs` asks on every reading.
    event_ts: dict[str, str] = field(default_factory=dict)
    fires: list[str] = field(default_factory=list)

    def record_event(self, event_id: str, signal_ts: str) -> None:
        """Append an event this episode minted, with the clock it was minted at."""
        self.event_ids.append(event_id)
        self.event_ts[event_id] = signal_ts

    def __post_init__(self) -> None:
        assert_can_fire(self.detector_id)
        if self.state is None:
            self.state = lifecycle().DetectorState.PROBING

    @property
    def terminal(self) -> bool:
        return self.state in lifecycle().TERMINAL_STATES

    def transition(self, to_state: Any, *, at: str, reason: str = "",
                   evidence_refs: Sequence[str] = ()) -> Any:
        """Move the machine, recording the evidence that justified the move."""
        assert_can_fire(self.detector_id)
        lc = lifecycle()
        record = lc.TransitionRecord(
            ticker=self.ticker, detector_id=self.detector_id, from_state=self.state,
            to_state=to_state, at=at, reason=reason,
            evidence_refs=tuple(evidence_refs))
        self.state = to_state
        self.transitions.append(record)
        return record

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "detector_id": self.detector_id,
            "variant": self.variant,
            "state": self.state.value,
            "first_armed_at": self.first_armed_at,
            "candidate_at": self.candidate_at,
            "last_observed_at": self.last_observed_at,
            "transitions": [t.to_dict() for t in self.transitions],
            "event_ids": list(self.event_ids),
            "event_ts": dict(self.event_ts),
            "fires": list(self.fires),
        }


def lawful_evidence_refs(episode: DetectorEpisode | None,
                         observed_at: str) -> tuple[str, ...]:
    """Evidence an observation at ``observed_at`` could actually have cited.

    W3-3.  Every C2 reading used to carry the C1 episode's event ids, INCLUDING
    readings dated hours before that event existed — a forward citation inside the
    record whose whole purpose is to say what was knowable when.  An event with no
    recorded clock is excluded rather than assumed old: fail-closed, because the
    failure this fixes was a citation nobody had checked.
    """
    if episode is None:
        return ()
    return tuple(eid for eid in episode.event_ids
                 if (episode.event_ts.get(eid) or "") != ""
                 and episode.event_ts[eid] <= observed_at)


def rearm_eligible(confirmed_k_since_end: Sequence[float | None],
                   sessions_elapsed: int) -> bool:
    """§10's frozen re-arm rule, as a pure predicate.

    A ``None`` K is UNAVAILABLE and breaks the consecutive run rather than
    counting as a pass — the run is evidence of recovery, and a missing reading
    is not evidence of anything.
    """
    if int(sessions_elapsed) >= REARM_MAX_SESSIONS:
        return True
    run = 0
    for value in confirmed_k_since_end:
        if value is not None and float(value) > REARM_K_FLOOR:
            run += 1
            if run >= REARM_K_SESSIONS:
                return True
        else:
            run = 0
    return False


# ---------------------------------------------------------------------------
# A5.1 — inputs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MinuteBar:
    """One minute aggregate.  ``start`` is the bar's OPEN instant, tz-aware."""

    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if self.start.tzinfo is None:
            raise ChallengerError(f"minute bar at {self.start} is naive; a session "
                                  f"boundary cannot be decided without a timezone")

    @property
    def knowable_at(self) -> datetime:
        """``start + 60s`` — a minute bar is knowable when it CLOSES, not when it opens."""
        return self.start + timedelta(seconds=MINUTE_BAR_SECONDS)


@dataclass(frozen=True, slots=True)
class SessionTape:
    """One session's minute aggregates, with the basis they were fetched on."""

    session: date
    minutes: tuple[MinuteBar, ...] = ()
    price_basis: str = BASIS_ADJUSTED
    vintage: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "minutes", tuple(self.minutes))


@dataclass(frozen=True, slots=True)
class DailyHistory:
    """Confirmed daily OHLC, plus the basis it was collected on.

    ``confirmed_through`` is the §5 knowability law made structural: a 1D
    CONFIRMED value is knowable at the NEXT session open, so while session D is
    open the confirmed history ends at D−1.  The cut happens HERE, once, and every
    W3 consumer reads through it — so "the historical parquet already has today's
    close" can never become "the detector saw today's close".
    """

    frame: pd.DataFrame
    price_basis: str = BASIS_ADJUSTED
    vintage: str = ""

    def __post_init__(self) -> None:
        frame = self.frame
        if not isinstance(frame, pd.DataFrame):
            raise ChallengerError("DailyHistory.frame must be a DataFrame")
        missing = [c for c in ("high", "low", "close") if c not in frame.columns]
        if missing:
            raise ChallengerError(f"DailyHistory.frame is missing column(s) {missing}")
        idx = pd.DatetimeIndex(frame.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        idx = idx.normalize()
        # W3-12.  A duplicated session silently doubles a bar inside every
        # rolling window — the RSI denominator, the StochRSI extremes and the ATR
        # all shift, and nothing downstream can see why.  A frame handed in out of
        # order is the same defect wearing a different hat: sorting it would hide
        # that the caller's idea of "the last bar" and ours disagree.
        if idx.has_duplicates:
            dupes = sorted({str(d.date()) for d in idx[idx.duplicated()]})
            raise ChallengerError(
                f"DailyHistory index carries duplicate session(s) {dupes}; a doubled "
                f"bar shifts every rolling window and no consumer can see it")
        if not idx.is_monotonic_increasing:
            raise ChallengerError(
                "DailyHistory index is not monotonically increasing; pass the frame in "
                "session order — silently sorting it would hide that the caller's "
                "'last bar' and this module's disagree")
        object.__setattr__(self, "frame", frame.set_axis(idx))

    def confirmed_through(self, session: date) -> pd.DataFrame:
        """Rows STRICTLY BEFORE ``session`` — nothing from the open session leaks."""
        cut = pd.Timestamp(session).normalize()
        return self.frame.loc[self.frame.index < cut]


def prior_reference_session(session: date, *, market: str = "US") -> date | None:
    """The reference session immediately preceding ``session``, or None before the epoch.

    Read from ``engine.session_anchor.reference_sessions`` — the same absolute
    calendar C4's buckets ride — so "yesterday" is a calendar fact rather than a
    property of whatever rows the caller happened to load.
    """
    reference = session_anchor.reference_sessions(market)
    position = int(reference.searchsorted(pd.Timestamp(session).normalize(),
                                          side="left"))
    if position <= 0:
        return None
    return reference[position - 1].date()


def freshness_state(last_confirmed: date | None, session: date, *,
                    market: str = "US") -> str:
    """``confirmed`` | ``stale`` | ``unavailable`` for a confirmed-history cut.

    W3-5.  ``stale`` is in the §5 vocabulary and was unreachable: a three-month-old
    daily feed produced a `confirmed` reading and a measured non-fire, which is
    exactly the stale-frame failure #5555's law exists to stop.  The test is
    CONTINUITY against the reference calendar — the history must reach the session
    immediately before the one being evaluated.  Anything OLDER is stale; a feed
    carrying an extra non-session row is not (it is not older, merely odd).
    """
    if last_confirmed is None:
        return "unavailable"
    required = prior_reference_session(session, market=market)
    if required is None:
        return "confirmed"
    return "stale" if last_confirmed < required else "confirmed"


@dataclass(frozen=True, slots=True)
class SampledPoint:
    """One 5-minute observation of the sampled path."""

    observed_at: datetime
    interval_start: datetime
    sampled_close: float | None
    interval_had_bar: bool
    running_sampled_low: float | None
    #: DIAGNOSTIC ONLY, and never read by any variant.  Minute-granularity lows
    #: are <= sampled lows, so a rebound variant fed this value would fire earlier
    #: and more often than the live lane could ever have observed (§7.1).  It is
    #: carried so the gap is MEASURABLE, not so it can be used.
    running_minute_low: float | None


@dataclass(frozen=True, slots=True)
class Observation:
    """One point-in-time evaluation state — the substrate every C1/C2 reading reads."""

    ticker: str
    observed_at: str
    market_session: str
    interval_start: str
    availability: str
    bar_state: str
    sampled_close: float | None
    running_sampled_low: float | None
    running_minute_low: float | None
    k: float | None
    d: float | None
    hist: float | None
    source_bar_time: str | None
    source_bar_known_at: str | None
    data_vintage: str | None
    #: The INTRADAY tape's basis and the CONFIRMED DAILY frame's basis, kept as a
    #: pair (W3-1).  One of them alone cannot be audited: the whole question is
    #: whether the two halves of the concatenated series agree.
    price_basis: str
    daily_price_basis: str
    atr_prior_confirmed: float | None
    atr_basis: str | None
    confirmed_bars: int
    #: ``confirmed`` | ``stale`` | ``unavailable`` for the confirmed history behind
    #: this observation (W3-5).  Recorded separately from ``availability`` because
    #: "the feed is three months old" and "no print yet today" are different facts.
    history_freshness: str = "confirmed"

    @property
    def oversold(self) -> bool | None:
        """``K_T < 20``, or None when K is unavailable.  Never False on a gap."""
        return None if self.k is None else bool(self.k < ic.OVERSOLD)


def rth_minutes(tape: SessionTape) -> tuple[MinuteBar, ...]:
    """Minutes fully inside the session's RTH window (§7 — extended hours excluded).

    A bar is admitted iff it OPENS at/after the session open and CLOSES at/before
    the session close.  The 15:59 bar (closing exactly at 16:00) is inside; the
    16:00 bar is not, and neither is any premarket print.
    """
    open_dt, close_dt = session_window_et(tape.session)
    return tuple(m for m in sorted(tape.minutes, key=lambda b: b.start)
                 if m.start >= open_dt and m.knowable_at <= close_dt)


def sample_session_path(tape: SessionTape, *,
                        interval_minutes: int = SAMPLE_INTERVAL_MINUTES,
                        ) -> tuple[SampledPoint, ...]:
    """A5.1 steps 3–6: the session-open-anchored 5-minute sampled path.

    One observation per completed interval, at the interval's effective end.  The
    value is the last minute-aggregate CLOSE knowable by that instant — carried
    forward across an interval with no prints, because "no trade" is not "no
    price".  ``running_sampled_low`` is the minimum over the SAMPLED path, which
    is the only low the future live lane could have seen.
    """
    if int(interval_minutes) <= 0:
        raise ChallengerError("interval_minutes must be positive")
    open_dt, close_dt = session_window_et(tape.session)
    minutes = rth_minutes(tape)
    out: list[SampledPoint] = []
    running_low: float | None = None
    running_minute_low: float | None = None
    cursor = open_dt
    while cursor < close_dt:
        end = min(cursor + timedelta(minutes=int(interval_minutes)), close_dt)
        lawful = [m for m in minutes if m.knowable_at <= end]
        value = lawful[-1].close if lawful else None
        had_bar = bool(lawful) and lawful[-1].start >= cursor
        if value is not None:
            running_low = value if running_low is None else min(running_low, value)
        if lawful:
            low = min(m.low for m in lawful)
            running_minute_low = low if running_minute_low is None else min(
                running_minute_low, low)
        out.append(SampledPoint(observed_at=end, interval_start=cursor,
                                sampled_close=value, interval_had_bar=had_bar,
                                running_sampled_low=running_low,
                                running_minute_low=running_minute_low))
        cursor = end
    return tuple(out)


def utc_iso(ts: datetime) -> str:
    return iso(ts.astimezone(timezone.utc)) or ""


def build_observation_path(*, ticker: str, daily: DailyHistory,
                           tapes: Sequence[SessionTape],
                           interval_minutes: int = SAMPLE_INTERVAL_MINUTES,
                           ) -> tuple[Observation, ...]:
    """A5.1 end-to-end: confirmed closes + one appended provisional close per T.

    Step 7 is the load-bearing one — the sampled value is **APPENDED** as the
    current session's bar and no prior confirmed close is replaced (§7.1's
    measured append-not-replace law).  Step 8's consequence is that the ATR a live
    variant normalises by is frozen from the prior confirmed session: it is
    computed here, on the CUT frame, so today's eventual high and low are never
    even loaded.
    """
    observations: list[Observation] = []
    for tape in sorted(tapes, key=lambda t: t.session):
        confirmed = daily.confirmed_through(tape.session)
        closes = confirmed["close"].astype(float)
        base_index = pd.DatetimeIndex(confirmed.index)
        session_ts = pd.Timestamp(tape.session).normalize()
        atr_series = ic.atr14(confirmed["high"], confirmed["low"], confirmed["close"])
        atr_prior = ic.last_finite(atr_series)
        # W3-1.  The basis check gated only the ATR fields; the OSCILLATOR was
        # computed on `confirmed daily closes + a sampled close from the other
        # basis`, so the seam between the two halves fabricated a move — and a
        # fabricated move fabricates a cross and mints a candidate.  A disagreeing
        # basis now voids the whole observation, exactly as c2f already refused.
        basis_agrees = daily.price_basis == tape.price_basis
        atr_basis = (f"wilder_atr{ic.ATR_LEN}_true_range_prior_confirmed"
                     f"[{daily.price_basis}]" if atr_prior is not None else None)
        vintage = tape.vintage or daily.vintage or None
        last_confirmed = (base_index[-1].date() if len(base_index) else None)
        freshness = freshness_state(last_confirmed, tape.session)

        def _record(point: SampledPoint, *, availability: str,
                    sampled: float | None, k: float | None, d: float | None,
                    hist: float | None) -> Observation:
            return Observation(
                ticker=ticker, observed_at=utc_iso(point.observed_at),
                market_session=tape.session.isoformat(),
                interval_start=utc_iso(point.interval_start),
                availability=availability, bar_state="provisional",
                sampled_close=sampled,
                running_sampled_low=(point.running_sampled_low
                                     if sampled is not None else None),
                running_minute_low=point.running_minute_low,
                k=k, d=d, hist=hist,
                source_bar_time=(session_ts.date().isoformat()
                                 if sampled is not None else None),
                source_bar_known_at=None,
                data_vintage=vintage, price_basis=tape.price_basis,
                daily_price_basis=daily.price_basis,
                atr_prior_confirmed=atr_prior if basis_agrees else None,
                atr_basis=atr_basis if basis_agrees else None,
                confirmed_bars=int(len(closes)),
                history_freshness=freshness)

        for point in sample_session_path(tape, interval_minutes=interval_minutes):
            if not basis_agrees or point.sampled_close is None or len(closes) == 0:
                observations.append(_record(
                    point, availability="unavailable",
                    sampled=(point.sampled_close if basis_agrees else None),
                    k=None, d=None, hist=None))
                continue
            if freshness != "confirmed":
                # A STALE history is not computed on at all: a %K derived from a
                # three-month-old base is a current-looking number about an old
                # world, and the safest place for it is nowhere.
                observations.append(_record(
                    point, availability=freshness, sampled=point.sampled_close,
                    k=None, d=None, hist=None))
                continue

            series = pd.Series(
                np.append(closes.to_numpy(dtype=float), float(point.sampled_close)),
                index=base_index.append(pd.DatetimeIndex([session_ts])))
            k_series, d_series = ic.stoch_rsi_kd(series)
            hist_series = ic.rsi_macd_hist(series)
            k_val = ic.last_finite(k_series)
            observations.append(_record(
                point, availability="unavailable" if k_val is None else "provisional",
                sampled=point.sampled_close, k=k_val,
                d=ic.last_finite(d_series), hist=ic.last_finite(hist_series)))
    return tuple(observations)


# ---------------------------------------------------------------------------
# C1 — the arm IS the candidate
# ---------------------------------------------------------------------------

#: Availability states that can carry no verdict at all (§18 A5.0 + W3-5).
NULL_AVAILABILITY: frozenset[str] = frozenset({"unavailable", "stale"})


def c1_reading(obs: Observation) -> DetectorReading:
    """One C1 reading.  ``condition_met`` is None on an unavailable OR stale input."""
    available = obs.k is not None and obs.availability not in NULL_AVAILABILITY
    return DetectorReading(
        ticker=obs.ticker,
        detector_id=C1_DETECTOR_ID,
        detector_version=C1_VERSION,
        detector_spec_hash=c1_spec_hash(),
        variant=None,
        observed_at=obs.observed_at,
        market_session=obs.market_session,
        availability=obs.availability,
        source_bar_time=obs.source_bar_time,
        source_bar_known_at=obs.source_bar_known_at,
        bar_state=obs.bar_state,
        data_vintage=obs.data_vintage,
        features={
            "k": obs.k,
            "d": obs.d,
            "oversold_threshold": ic.OVERSOLD,
            "sampled_close": obs.sampled_close,
            "confirmed_bars": obs.confirmed_bars,
            # W3-1: the PAIR, so a reader can audit the seam rather than trust it.
            "price_basis": obs.price_basis,
            "daily_price_basis": obs.daily_price_basis,
            # W3-5: why the availability says what it says.
            "history_freshness": obs.history_freshness,
        },
        condition_met=(None if not available else bool(obs.k < ic.OVERSOLD)),
    )


@dataclass(frozen=True, slots=True)
class C1Run:
    """What one pass of C1 over an observation path produced."""

    readings: tuple[DetectorReading, ...]
    episodes: tuple[DetectorEpisode, ...]
    events: tuple[EntryEvent, ...]

    @property
    def episode(self) -> DetectorEpisode | None:
        return self.episodes[0] if self.episodes else None


def run_c1(path: Sequence[Observation]) -> C1Run:
    """Evaluate C1 across an observation path.

    ONE candidate per episode (A5.2).  The first ``K < 20`` arms AND promotes at
    the same instant — ``candidate_at == first_armed_at == observed_at`` — and
    every later oversold observation is a path observation, not a second
    candidate.

    WHAT ``episodes`` IS NOT (W3-10).  It is a per-PATH trace, not a §10 episode
    ledger: a single pass produces at most one episode BY CONSTRUCTION, because
    nothing here can terminate the live one and §10 forbids a second while it is
    nonterminal.  The clocks that END an episode — CANDIDATE resolving at H,
    ARMED/TURNING expiring at 15 sessions, and the re-arm eligibility that follows
    — belong to the live evaluator (PR-4) and the nightly reconciler (PR-5).
    :func:`rearm_eligible` is the exported primitive they will wire; W3 ships the
    predicate, not the clock, because a clock with no ledger behind it would be a
    second source of truth for when an episode ended.
    """
    readings: list[DetectorReading] = []
    episodes: list[DetectorEpisode] = []
    events: list[EntryEvent] = []
    live: DetectorEpisode | None = None
    lc = lifecycle()

    for obs in path:
        reading = c1_reading(obs)
        readings.append(reading)
        if live is not None:
            live.last_observed_at = obs.observed_at
        if reading.condition_met is not True:
            continue
        if live is not None:
            live.fires.append(obs.observed_at)
            continue
        live = DetectorEpisode(ticker=obs.ticker, detector_id=C1_DETECTOR_ID)
        live.transition(lc.DetectorState.ARMED, at=obs.observed_at,
                        reason="1D LIVE StochRSI K < 20 (A5.2 arm condition)")
        event = build_radar_native_event(
            detector_id=C1_DETECTOR_ID,
            detector_spec_hash=c1_spec_hash(),
            ticker=obs.ticker,
            family="radar_1d_live_washout",
            subtype=RADAR_1D_LIVE_WASHOUT_SUBTYPE,
            signal_ts=obs.observed_at,
            # W3-15: a 1D-LIVE observation is knowable exactly at its own
            # observation instant — that is what "live" means.  Finality is
            # unchanged (the BAR behind it is still provisional until the close).
            signal_known_ts=obs.observed_at,
            market_session=obs.market_session,
            bar_state=obs.bar_state,
            context={"k": obs.k, "d": obs.d, "sampled_close": obs.sampled_close,
                     "market_session": obs.market_session,
                     "oversold_threshold": ic.OVERSOLD})
        events.append(event)
        live.record_event(str(event.event_id), obs.observed_at)
        live.fires.append(obs.observed_at)
        live.first_armed_at = obs.observed_at
        live.candidate_at = obs.observed_at
        live.last_observed_at = obs.observed_at
        live.transition(lc.DetectorState.CANDIDATE, at=obs.observed_at,
                        reason="candidate_at == first_armed_at (§4 frozen promotion law)",
                        evidence_refs=(str(event.event_id),))
        episodes.append(live)
    return C1Run(readings=tuple(readings), episodes=tuple(episodes),
                 events=tuple(events))


# ---------------------------------------------------------------------------
# C2 — exactly six single-feature turn mechanisms
# ---------------------------------------------------------------------------

@dataclass
class _C2State:
    """The per-variant memory C2 needs, kept explicit rather than derived.

    ``kd`` is a list of PAIRS, not two parallel lists.  %D warms up two bars after
    %K, so parallel lists would silently desync at the start of a short history
    and ``c2a`` would compare today's K against a D from a different observation —
    a cross that never happened.
    """

    kd: list[tuple[float, float]] = field(default_factory=list)
    k: list[float] = field(default_factory=list)
    hist: list[float] = field(default_factory=list)
    pivots: list[float] = field(default_factory=list)

    def remember(self, obs: Observation) -> None:
        """Advance the memory with THIS observation's lawful values only."""
        if obs.k is not None and obs.d is not None:
            self.kd.append((obs.k, obs.d))
        if obs.k is not None:
            self.k.append(obs.k)
        if obs.hist is not None:
            self.hist.append(obs.hist)


def _eval_c2a(state: _C2State, obs: Observation) -> bool | None:
    if obs.k is None or obs.d is None or not state.kd:
        return None
    prev_k, prev_d = state.kd[-1]
    return bool(obs.k > obs.d and prev_k <= prev_d)


def _eval_c2b(state: _C2State, obs: Observation) -> bool | None:
    if obs.k is None or not state.k:
        return None
    return bool(obs.k > state.k[-1])


def _eval_c2c(state: _C2State, obs: Observation) -> bool | None:
    """Causal pivot — a low at j is confirmed only by the observation at j+1.

    ADVANCES ``state.pivots`` as it evaluates, because confirming a pivot IS the
    evaluation: the pivot ledger is the mechanism, not a cache of it.  It is
    therefore called exactly once per observation, by :func:`run_c2`, and only
    when the observation is eligible — so the ledger holds in-episode pivots and
    nothing else.
    """
    if obs.k is None or len(state.k) < 2:
        return None
    prev, prev2 = state.k[-1], state.k[-2]
    if not (prev2 > prev and obs.k >= prev):
        return False
    fired = bool(state.pivots and prev > state.pivots[-1])
    state.pivots.append(prev)
    return fired


def _eval_c2d(state: _C2State, obs: Observation) -> bool | None:
    if obs.hist is None or len(state.hist) < 2:
        return None
    return bool(obs.hist > state.hist[-1] and state.hist[-1] <= state.hist[-2])


def _eval_c2e(state: _C2State, obs: Observation) -> bool | None:
    if obs.hist is None or len(state.hist) < 2:
        return None
    return bool(obs.hist - 2.0 * state.hist[-1] + state.hist[-2] > 0.0)


def _eval_c2f(state: _C2State, obs: Observation) -> bool | None:
    """Rebound in ATR units off the SAMPLED session low.

    Unavailable — never False — when the prior-confirmed ATR is missing or the
    intraday basis disagrees with the daily basis.  A rebound measured in units
    we could not compute is not a non-rebound.
    """
    if (obs.sampled_close is None or obs.running_sampled_low is None
            or obs.atr_prior_confirmed is None or obs.atr_basis is None):
        return None
    if obs.atr_prior_confirmed <= 0:
        return None
    return bool(obs.sampled_close - obs.running_sampled_low
                >= C2F_ATR_MULTIPLE * obs.atr_prior_confirmed)


#: The six mechanisms, by registered key.  A dict so the set is enumerable and a
#: seventh entry is a visible diff rather than a quiet extra branch.
C2_EVALUATORS = {
    "c2a_kd_cross": _eval_c2a,
    "c2b_k_slope": _eval_c2b,
    "c2c_higher_k_low": _eval_c2c,
    "c2d_hist_trough": _eval_c2d,
    "c2e_hist_curvature": _eval_c2e,
    "c2f_rebound_atr": _eval_c2f,
}


def _c2_features(obs: Observation, variant: str, *, eligible: bool) -> dict[str, Any]:
    base: dict[str, Any] = {
        "k": obs.k, "d": obs.d, "hist": obs.hist,
        "sampled_close": obs.sampled_close,
        "price_basis": obs.price_basis,
        "daily_price_basis": obs.daily_price_basis,
        "history_freshness": obs.history_freshness,
        # W3-8: C3 already encoded the same situation this way.  One vocabulary
        # across the two detectors, so a consumer counting non-fires does not have
        # to know which detector wrote the row.
        "eligible": eligible,
        "pre_arm": not eligible,
    }
    if variant == "c2f_rebound_atr":
        base["running_sampled_low"] = obs.running_sampled_low
        base["atr14_prior_confirmed"] = obs.atr_prior_confirmed
        base["atr_multiple"] = C2F_ATR_MULTIPLE
        base["rebound"] = (None if (obs.sampled_close is None
                                    or obs.running_sampled_low is None)
                           else obs.sampled_close - obs.running_sampled_low)
    return base


@dataclass(frozen=True, slots=True)
class C2Run:
    """Readings, per-variant episodes and events from one C2 pass."""

    readings: tuple[DetectorReading, ...]
    episodes: tuple[DetectorEpisode, ...]
    events: tuple[EntryEvent, ...]
    fires: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def variant_episode(self, variant: str) -> DetectorEpisode | None:
        for episode in self.episodes:
            if episode.variant == variant:
                return episode
        return None


def run_c2(path: Sequence[Observation], c1_episode: DetectorEpisode | None, *,
           evaluators: Mapping[str, Any] | None = None) -> C2Run:
    """Evaluate the six C2 variants inside one C1 episode.

    ELIGIBILITY (A5.3) is the whole subtlety: a variant is eligible from the C1
    episode's FIRST ARM onward and carries **no current-K<20 requirement** — the
    washout is the episode's history and the turn is the event, so a variant may
    lawfully fire after K has recovered above 20 provided the C1 episode is still
    nonterminal.  Nothing fires before the arm.

    Per-variant memory holds only that variant's OWN lawful observations, so
    ``_prev`` means "the previous observation at which THIS mechanism could be
    evaluated" — a variant still inside its indicator's warm-up does not consume a
    predecessor it never had.

    PRE-ARM IS AN EVALUATED NON-FIRE (W3-8).  C2's condition is "inside a
    nonterminal C1 episode AND the turn"; before the arm the first conjunct is
    known-FALSE, so the conjunction is False and the turn sub-predicate is never
    run — which is also what keeps the c2c pivot ledger holding in-episode pivots
    only.  An unavailable or stale INPUT still dominates and yields null: not
    knowing beats knowing the answer is no.

    THE RETURNED EPISODES ARE A PER-PATH TRACE, NOT A LEDGER (W3-10) — see
    :func:`run_c1`; §10's termination and re-arm clocks are PR-4/PR-5's.
    """
    evaluators = dict(evaluators or C2_EVALUATORS)
    readings: list[DetectorReading] = []
    episodes: list[DetectorEpisode] = []
    events: list[EntryEvent] = []
    fires: dict[str, list[str]] = {v: [] for v in evaluators}
    state = {v: _C2State() for v in evaluators}
    promoted: dict[str, DetectorEpisode] = {}
    lc = lifecycle()

    armed_at = c1_episode.first_armed_at if c1_episode is not None else None
    for obs in path:
        eligible = armed_at is not None and obs.observed_at >= armed_at
        input_ok = obs.availability not in NULL_AVAILABILITY
        for variant, evaluate in evaluators.items():
            vstate = state[variant]
            if not input_ok:
                verdict, availability = None, obs.availability
            elif not eligible:
                # The episode clause is known-False; the turn stays UNCALLED.
                verdict, availability = False, obs.availability
            else:
                verdict = evaluate(vstate, obs)
                availability = obs.availability if verdict is not None \
                    else "unavailable"
            readings.append(DetectorReading(
                ticker=obs.ticker,
                detector_id=C2_DETECTOR_ID,
                detector_version=C2_VERSION,
                detector_spec_hash=c2_spec_hash(),
                variant=variant,
                observed_at=obs.observed_at,
                market_session=obs.market_session,
                availability=availability,
                source_bar_time=obs.source_bar_time,
                source_bar_known_at=obs.source_bar_known_at,
                bar_state=obs.bar_state,
                data_vintage=obs.data_vintage,
                features=_c2_features(obs, variant, eligible=eligible),
                condition_met=verdict,
                evidence_refs=lawful_evidence_refs(c1_episode, obs.observed_at),
            ))
            if verdict is True:
                fires[variant].append(obs.observed_at)
                if variant not in promoted:
                    episode = DetectorEpisode(ticker=obs.ticker,
                                              detector_id=C2_DETECTOR_ID,
                                              variant=variant)
                    episode.transition(lc.DetectorState.ARMED, at=obs.observed_at,
                                       reason=f"{variant} eligible inside the C1 episode")
                    event = build_radar_native_event(
                        detector_id=C2_DETECTOR_ID,
                        detector_spec_hash=c2_spec_hash(),
                        ticker=obs.ticker,
                        family="radar_1d_turn",
                        subtype=variant,
                        signal_ts=obs.observed_at,
                        # W3-15: knowable at the observation instant (see run_c1).
                        signal_known_ts=obs.observed_at,
                        market_session=obs.market_session,
                        bar_state=obs.bar_state,
                        context={"variant": variant, "k": obs.k, "d": obs.d,
                                 "hist": obs.hist,
                                 "market_session": obs.market_session,
                                 "sampled_close": obs.sampled_close})
                    events.append(event)
                    episode.record_event(str(event.event_id), obs.observed_at)
                    episode.first_armed_at = obs.observed_at
                    episode.candidate_at = obs.observed_at
                    episode.transition(lc.DetectorState.CANDIDATE, at=obs.observed_at,
                                       reason=f"{variant} turn observed (A5.3)",
                                       evidence_refs=(str(event.event_id),))
                    promoted[variant] = episode
                    episodes.append(episode)
                promoted[variant].fires.append(obs.observed_at)
                promoted[variant].last_observed_at = obs.observed_at
            # Memory advances only on a LAWFUL observation for this variant.
            vstate.remember(obs)
    return C2Run(readings=tuple(readings), episodes=tuple(episodes),
                 events=tuple(events),
                 fires={v: tuple(ts) for v, ts in fires.items()})


# ---------------------------------------------------------------------------
# C4 — stratification features on the absolute session anchor.  CANNOT FIRE.
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MtfBucket:
    """One 2D/3D bucket on the ABSOLUTE session anchor."""

    bucket_id: int
    last_session: str
    close: float
    sessions: int
    confirmed: bool


def mtf_buckets(confirmed: pd.DataFrame | pd.Series, n: int, *,
                market: str = "US") -> tuple[MtfBucket, ...]:
    """Bucket confirmed daily closes by ABSOLUTE session position.

    ``bucket = session_positions(index) // n`` — a function of ``(reference, date)``
    alone, so any two callers holding any two windows of the same name agree
    bar-for-bar.  ``canon.resample_sessions`` counts from the CALLER'S first bar
    and re-phases when leading sessions are dropped; that phase dependence is the
    exact defect the absolute anchor exists to remove, and
    ``tests/test_entry_radar_w3_c4.py`` pins both sides of it.

    A bucket is CONFIRMED only once its whole window has elapsed in confirmed
    time: the reference session at position ``(bucket+1)*n − 1`` must be at or
    before the last confirmed session.  A trailing partial bucket is returned with
    ``confirmed=False`` and is debug context, never a registered feature.
    """
    if int(n) < 1:
        raise ChallengerError("bucket width must be >= 1")
    closes = (confirmed["close"] if isinstance(confirmed, pd.DataFrame) else confirmed)
    closes = pd.to_numeric(closes, errors="coerce").dropna()
    if closes.empty:
        return ()
    index = pd.DatetimeIndex(closes.index).normalize()
    positions = session_anchor.session_positions(index, market)
    reference = session_anchor.reference_sessions(market)
    last_confirmed = index[-1]

    buckets: dict[int, list[Any]] = {}
    for pos, when, value in zip(positions, index, closes.to_numpy(dtype=float)):
        buckets.setdefault(int(pos) // int(n), []).append((when, float(value)))

    out: list[MtfBucket] = []
    for bucket_id in sorted(buckets):
        rows = buckets[bucket_id]
        end_pos = (bucket_id + 1) * int(n) - 1
        if 0 <= end_pos < len(reference):
            confirmed_bucket = bool(reference[end_pos] <= last_confirmed)
        else:
            confirmed_bucket = False
        out.append(MtfBucket(bucket_id=bucket_id,
                             last_session=rows[-1][0].date().isoformat(),
                             close=rows[-1][1], sessions=len(rows),
                             confirmed=confirmed_bucket))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class MtfGrainState:
    """One grain's turn boolean and its SEPARATELY recorded washout context.

    ``turn`` carries no depth requirement and ``recent_washout`` carries no
    arming power.  They are two facts kept two facts on purpose: fusing them is
    `DNR:KILL-WASHOUT-TURN`'s interaction form.
    """

    grain: int
    availability: str
    turn: bool | None = None
    recent_washout: bool | None = None
    bucket_last_session: str | None = None
    confirmed_buckets: int = 0
    k: float | None = None
    d: float | None = None


def _grain_state(confirmed: pd.DataFrame, n: int, *, market: str) -> tuple[
        MtfGrainState, dict[str, Any]]:
    buckets = mtf_buckets(confirmed, n, market=market)
    settled = [b for b in buckets if b.confirmed]
    partial = [b for b in buckets if not b.confirmed]
    debug = {"partial_buckets": [b.last_session for b in partial],
             "total_buckets": len(buckets)}
    if len(settled) < 2:
        return MtfGrainState(grain=n, availability="unavailable",
                             confirmed_buckets=len(settled)), debug
    series = pd.Series([b.close for b in settled],
                       index=pd.DatetimeIndex([b.last_session for b in settled]))
    k_series, d_series = ic.stoch_rsi_kd(series)
    pair = ic.finite_tail(k_series, 2)
    dpair = ic.finite_tail(d_series, 2)
    if pair is None or dpair is None:
        return MtfGrainState(grain=n, availability="unavailable",
                             confirmed_buckets=len(settled),
                             bucket_last_session=settled[-1].last_session), debug
    turn = bool(pair[1] > dpair[1] and pair[0] <= dpair[0])
    os_window = d_series.rolling(MTF_OS_WINDOW).min()
    os_value = ic.last_finite(os_window)
    recent = None if os_value is None else bool(os_value < ic.OVERSOLD)
    return MtfGrainState(grain=n, availability="confirmed", turn=turn,
                         recent_washout=recent,
                         bucket_last_session=settled[-1].last_session,
                         confirmed_buckets=len(settled),
                         k=pair[1], d=dpair[1]), debug


@dataclass(frozen=True, slots=True)
class C4State:
    """C4's raw state.  There is deliberately NO arm/candidate/promote/fire API.

    `DNR:KILL-WASHOUT-TURN` is enforced by SHAPE here: this object cannot be asked
    to transition, cannot address an entry event (C4 has no family), and every
    firing door in the package calls :func:`assert_can_fire` first.  The
    ``recovery_count`` is a description of how many grains turned — never a score,
    never a monotone bullish bonus.
    """

    ticker: str
    detector_id: str
    market_session: str
    anchor_era: str
    base_variant: str
    d2: MtfGrainState
    d3: MtfGrainState
    recovery_count: int | None
    provisional_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "detector_id": self.detector_id,
            "market_session": self.market_session,
            "anchor_era": self.anchor_era,
            "base_variant": self.base_variant,
            "role": "stratification_only",
            "d2": {"grain": self.d2.grain, "availability": self.d2.availability,
                   "turn": self.d2.turn, "recent_washout": self.d2.recent_washout,
                   "bucket_last_session": self.d2.bucket_last_session,
                   "confirmed_buckets": self.d2.confirmed_buckets},
            "d3": {"grain": self.d3.grain, "availability": self.d3.availability,
                   "turn": self.d3.turn, "recent_washout": self.d3.recent_washout,
                   "bucket_last_session": self.d3.bucket_last_session,
                   "confirmed_buckets": self.d3.confirmed_buckets},
            "recovery_count": self.recovery_count,
            "provisional_context": copy.deepcopy(self.provisional_context),
        }


def c4_snapshot(*, ticker: str, daily: DailyHistory, market_session: date | str,
                market: str = "US",
                base_variant: str = C2_PRIMARY_VARIANT) -> C4State:
    """C4 features as of a C2a candidate timestamp.

    Registered features read ONLY buckets lawfully confirmed at that moment, so a
    higher-timeframe bucket that completes later can never rewrite the snapshot
    attached to an earlier C2 event (A5.5's confirmed-bar law).  The trailing
    partial bucket rides ``provisional_context`` — visible, separate, and outside
    the registered value.
    """
    if base_variant != C2_PRIMARY_VARIANT:
        raise ChallengerError(
            f"C4 is computed on the primary C2a base only, got {base_variant!r} "
            f"(A5.5: the registered stratification population is C2a)")
    session = (market_session if isinstance(market_session, date)
               else date.fromisoformat(str(market_session)[:10]))
    confirmed = daily.confirmed_through(session)
    index = pd.DatetimeIndex(confirmed.index)
    freshness = freshness_state(index[-1].date() if len(index) else None, session,
                                market=market)
    if freshness != "confirmed":
        # W3-5.  A stratification snapshot computed on an aged frame would read as
        # a current higher-timeframe state; the registered features are withheld
        # and the reason is recorded, rather than published with an asterisk.
        blank = {n: MtfGrainState(grain=n, availability=freshness) for n in MTF_GRAINS}
        return C4State(
            ticker=ticker, detector_id=C4_DETECTOR_ID,
            market_session=session.isoformat(), anchor_era=RADAR_MTF_ANCHOR_ERA,
            base_variant=base_variant, d2=blank[2], d3=blank[3], recovery_count=None,
            provisional_context={"history_freshness": freshness,
                                 "note": "confirmed history does not reach the prior "
                                         "reference session; features withheld"})
    d2, debug2 = _grain_state(confirmed, 2, market=market)
    d3, debug3 = _grain_state(confirmed, 3, market=market)
    if d2.turn is None or d3.turn is None:
        recovery = None
    else:
        recovery = 1 + int(d2.turn) + int(d3.turn)
    return C4State(
        ticker=ticker, detector_id=C4_DETECTOR_ID,
        market_session=session.isoformat(), anchor_era=RADAR_MTF_ANCHOR_ERA,
        base_variant=base_variant, d2=d2, d3=d3, recovery_count=recovery,
        provisional_context={"d2": debug2, "d3": debug3,
                             "history_freshness": freshness,
                             "note": "partial buckets are debug context, never registered"})


def c4_reading(state: C4State, *, observed_at: str) -> DetectorReading:
    """C4's stratification reading.  ``condition_met`` is ALWAYS None.

    C4 has no condition to meet: it does not fire, so there is nothing for a
    boolean to be about.  Recording ``False`` here would invite a downstream
    reader to treat the absence of a turn as a measured non-fire of a detector
    that cannot fire at all.
    """
    grains = (state.d2.availability, state.d3.availability)
    available = grains == ("confirmed", "confirmed")
    # W3-5: a stale frame is reported STALE, not merely unavailable — the two are
    # different provenance facts and only one of them is fixable by waiting.
    degraded = "stale" if "stale" in grains else "unavailable"
    return DetectorReading(
        ticker=state.ticker,
        detector_id=C4_DETECTOR_ID,
        detector_version=C4_VERSION,
        detector_spec_hash=c4_spec_hash(),
        variant=None,
        observed_at=observed_at,
        market_session=state.market_session,
        availability="confirmed" if available else degraded,
        source_bar_time=state.d3.bucket_last_session or state.d2.bucket_last_session,
        source_bar_known_at=state.d3.bucket_last_session or state.d2.bucket_last_session,
        bar_state="confirmed",
        data_vintage=None,
        features={
            "role": "stratification_only",
            "anchor_era": state.anchor_era,
            "base_variant": state.base_variant,
            "d2_turn": state.d2.turn,
            "d2_recent_washout": state.d2.recent_washout,
            "d3_turn": state.d3.turn,
            "d3_recent_washout": state.d3.recent_washout,
            "recovery_count": state.recovery_count,
        },
        condition_met=None,
    )


def c4_firing_doors() -> tuple[str, ...]:
    """Every door in this package that could produce a C4 candidate.

    Enumerated so ``tests/test_entry_radar_w3_c4.py`` can prove each one refuses,
    rather than proving that the doors someone remembered refuse.
    """
    return ("assert_can_fire", "DetectorEpisode.__post_init__",
            "DetectorEpisode.transition", "build_radar_native_event(family=...)")
