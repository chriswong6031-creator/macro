"""engine/entry_radar/c5_adapter.py — C5, the Terminal Bottom Watch (W3, §18 A5.6).

BOUNDARY (contract §2), stated before anything else
---------------------------------------------------
This module is an INTERPRETER of events W2 already preserved.  It computes no
oscillator, ports no washout machinery, and opens no artifact: there is no second
production Bottom Watch implementation in this repo, by design.
``engine/washout_turn.py`` and ``engine/mtf_upturn.py`` are adjacent display
organs at a different grain and are neither imported nor modified here (house
precedent ``engine/washout_turn.py:1-5``).

WHAT C5 IS (§18 A5.6)
----------------------
The DETECTOR reading of the two preserved watch families —
``washout_early_watch``/``early_dot`` and ``washout_trigger_watch``/
``blocked_trigger``.  Three laws bind, and all three are about not damaging the
record C5 reads:

  1. **Reference, never mutate.**  A C5 reading/episode carries the watch event's
     ``event_id`` in ``evidence_refs``.  It never writes a ``detector_id`` back
     into that event, never edits it, and never mints a second event for the same
     market observation — a duplicate would double-count the observation in every
     later population read, and the append-only store would not notice because the
     two rows would carry different addresses.
  2. **Knowability is ``signal_known_ts``, never ``signal_ts``.**  A BOTTOM_WATCH
     event's ``ts`` is the 3D bar's OPEN date and can precede its own knowability
     by up to two sessions (§3.1's measured backdating: NVDA 2026-01-21 → known
     01-23).  A C5 candidate dated at ``signal_ts`` would claim a decision the
     data could not have supported yet.
  3. **``blocked_trigger`` takes precedence on a shared bar.**  That is the
     emitter's own de-duplication rule (§3.4), so when both watches land on one
     bar the trigger is the C5 candidate and the dot is recorded as superseded —
     recorded, not dropped, because "there was also a dot" is a fact about the
     bar.

WHAT IS DELIBERATELY NOT BUILT
-------------------------------
No locked-spec recomputation of the washout mask.  A5.6 permits a research-only
exact fallback for parity/PIT work "explicitly ``radar_derived``"; W3 does not
need one (the preserved events ARE the population), and building an unused
recomputation path is how a second production implementation is born.  The pinned
upstream commit and the exact formulas ride ``C5_SPEC`` so a future parity harness
inherits the pin instead of re-deriving it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from engine.entry_radar.challengers import ChallengerError, DetectorEpisode, lifecycle
from engine.entry_radar.entry_events import (
    WATCH_SUBTYPES,
    EntryEvent,
    EntryEventStore,
    sha16,
)
from engine.entry_radar.readings import DetectorReading

C5_DETECTOR_ID = "C5_BOTTOM_WATCH@1"
C5_VERSION = 1
C5_GRAIN = "1D_artifact"
C5_BAR_FAMILY = "terminal_3D_listing_anchored"

#: The two preserved watch families, in PRECEDENCE order — trigger first.
C5_SUBTYPE_PRECEDENCE: tuple[str, ...] = ("blocked_trigger", "early_dot")

#: Subtype -> family, read from the W2 map so the two cannot drift.
C5_FAMILIES: dict[str, str] = {v: k for k, v in WATCH_SUBTYPES.items()}


class C5Error(ChallengerError):
    """A malformed C5 input."""


C5_SPEC: dict[str, Any] = {
    "detector_id": C5_DETECTOR_ID,
    "version": C5_VERSION,
    "grain": C5_GRAIN,
    "bar_family": C5_BAR_FAMILY,
    "authority_source": "contract §18 A5.6 (2026-08-14 pre-outcome lock)",
    "upstream_pin": ("charting-app signal_layer/confluence_v2.py @ "
                     "82cb8cbf799fc3a91c9bee0f11a4db718fde68eb"),
    "implementation": ("interpretation of the two preserved W2 watch families; no second "
                       "production Bottom Watch implementation exists"),
    "families": {"washout_early_watch": "early_dot",
                 "washout_trigger_watch": "blocked_trigger"},
    "constants": {"DD_LOOKBACK_3D": 84, "DD_MIN": -0.35, "MO_DWELL_MIN": 3,
                  "OS_WINDOW": 8},
    "formula_drawdown": "close3 / rolling_max(close3, 84, min_periods=20) - 1",
    "formula_monthly_dwell": ("prior-closed monthly StochRSI-D < 20 consecutive dwell "
                              "(>= 3 months)"),
    "formula_recent_os": "rolling_min(3D_D, 8, min_periods=1) < 20",
    "formula_washed": ("bear_block AND ((drawdown <= -0.35) OR (monthly_dwell >= 3)) AND "
                       "recent_os"),
    "formula_raw_buy": "CB OR revBuy",
    "formula_blocked_trigger": "raw_buy AND washed",
    "candidate_population": "(early_dot OR blocked_trigger) AND washed",
    "precedence": "blocked_trigger takes precedence over early_dot on a shared bar",
    "knowability": ("the watch event's signal_known_ts — NEVER its 3D-open signal_ts "
                    "(A5.6)"),
    "mutation_law": ("references the preserved event_id as evidence; never mutates that "
                     "event, never injects a detector_id into it after the fact, never "
                     "duplicates the underlying market observation"),
    "fallback": ("any research-only exact fallback reproduces the pinned formula and "
                 "stays explicitly radar_derived; pre-channel reconstruction stays "
                 "governed by A4.7"),
}


def c5_spec_hash() -> str:
    """Stable 16-hex identity of C5's frozen spec block."""
    return sha16(C5_SPEC)


@dataclass(frozen=True, slots=True)
class C5Candidate:
    """One C5 candidate, addressed by the preserved watch event it interprets."""

    ticker: str
    subtype: str
    family: str
    signal_ts: str
    #: THE decision clock.  ``None`` when the emitter recorded none — which makes
    #: the candidate UNAVAILABLE, never a candidate dated at ``signal_ts``.
    signal_known_ts: str | None
    event_id: str
    final: bool
    #: Watch events on the SAME BAR that lost the precedence contest.  Recorded,
    #: never dropped: "a dot also fired here" is a fact about the bar.
    superseded_event_ids: tuple[str, ...] = ()

    @property
    def knowable(self) -> bool:
        return bool(self.signal_known_ts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "subtype": self.subtype,
            "family": self.family,
            "signal_ts": self.signal_ts,
            "signal_known_ts": self.signal_known_ts,
            "event_id": self.event_id,
            "final": self.final,
            "superseded_event_ids": list(self.superseded_event_ids),
        }


def watch_events(events: Iterable[EntryEvent]) -> tuple[EntryEvent, ...]:
    """The BOTTOM_WATCH events, in emitter order.  Nothing else is C5's business."""
    return tuple(e for e in events if e.family in WATCH_SUBTYPES)


def c5_candidates(events: Iterable[EntryEvent]) -> tuple[C5Candidate, ...]:
    """One candidate per (ticker, bar), with ``blocked_trigger`` winning a shared bar.

    The precedence contest is decided PER BAR, and the loser's ``event_id`` rides
    the winner as ``superseded_event_ids``.  Note what is NOT done: no event is
    edited, no event is removed, and no new event is minted — the contest changes
    which watch C5 calls its candidate, not what the ledger says happened.
    """
    by_bar: dict[tuple[str, str], list[EntryEvent]] = {}
    for event in watch_events(events):
        by_bar.setdefault((event.ticker, event.signal_ts), []).append(event)

    out: list[C5Candidate] = []
    for (ticker, signal_ts), group in sorted(by_bar.items()):
        ranked = sorted(group, key=lambda e: C5_SUBTYPE_PRECEDENCE.index(
            str(e.subtype)) if str(e.subtype) in C5_SUBTYPE_PRECEDENCE else 99)
        winner = ranked[0]
        if str(winner.subtype) not in C5_SUBTYPE_PRECEDENCE:
            raise C5Error(f"{ticker} {signal_ts}: watch subtype {winner.subtype!r} is "
                          f"outside the C5 precedence order {C5_SUBTYPE_PRECEDENCE}")
        out.append(C5Candidate(
            ticker=ticker, subtype=str(winner.subtype), family=winner.family,
            signal_ts=signal_ts,
            signal_known_ts=winner.signal_known_ts,
            event_id=str(winner.event_id), final=bool(winner.final),
            superseded_event_ids=tuple(str(e.event_id) for e in ranked[1:])))
    return tuple(out)


def c5_reading(candidate: C5Candidate, *, observed_at: str | None = None,
               ) -> DetectorReading:
    """One C5 reading.

    ``observed_at`` defaults to the candidate's KNOWABILITY, not to its
    ``signal_ts``: the reading is dated when Radar could first have made it.  A
    candidate the emitter gave no ``known_ts`` is ``unavailable`` with
    ``condition_met=None`` — a watch we cannot date is not a watch that did not
    happen.
    """
    if not candidate.knowable:
        return DetectorReading(
            ticker=candidate.ticker, detector_id=C5_DETECTOR_ID,
            detector_version=C5_VERSION, detector_spec_hash=c5_spec_hash(),
            variant=candidate.subtype,
            observed_at=observed_at or candidate.signal_ts,
            market_session=candidate.signal_ts,
            availability="unavailable",
            source_bar_time=candidate.signal_ts, source_bar_known_at=None,
            bar_state="provisional", data_vintage=None,
            features={"subtype": candidate.subtype, "family": candidate.family,
                      "knowability_basis": "signal_known_ts (absent)"},
            condition_met=None,
            evidence_refs=(candidate.event_id,) + candidate.superseded_event_ids)
    return DetectorReading(
        ticker=candidate.ticker, detector_id=C5_DETECTOR_ID,
        detector_version=C5_VERSION, detector_spec_hash=c5_spec_hash(),
        variant=candidate.subtype,
        observed_at=observed_at or str(candidate.signal_known_ts),
        market_session=str(candidate.signal_known_ts),
        availability="confirmed" if candidate.final else "provisional",
        source_bar_time=candidate.signal_ts,
        source_bar_known_at=str(candidate.signal_known_ts),
        bar_state="confirmed" if candidate.final else "provisional",
        data_vintage=None,
        features={"subtype": candidate.subtype, "family": candidate.family,
                  "knowability_basis": "signal_known_ts",
                  "superseded_on_bar": list(candidate.superseded_event_ids)},
        condition_met=True,
        evidence_refs=(candidate.event_id,) + candidate.superseded_event_ids)


def superseded_reading(candidate: C5Candidate, event: EntryEvent) -> DetectorReading:
    """The reading for a watch that LOST the same-bar precedence contest.

    ``condition_met=False`` and not ``None``: the observation existed and was
    evaluated — it lost to the emitter's own de-duplication rule.  Recording it
    unavailable would erase an evaluated fact; recording nothing would erase the
    dot entirely.
    """
    known = event.signal_known_ts
    return DetectorReading(
        ticker=event.ticker, detector_id=C5_DETECTOR_ID,
        detector_version=C5_VERSION, detector_spec_hash=c5_spec_hash(),
        variant=str(event.subtype),
        observed_at=str(known or event.signal_ts),
        market_session=str(known or event.signal_ts),
        availability="confirmed" if event.final else "provisional",
        source_bar_time=event.signal_ts, source_bar_known_at=known,
        bar_state="confirmed" if event.final else "provisional",
        data_vintage=None,
        features={"subtype": str(event.subtype), "family": event.family,
                  "knowability_basis": "signal_known_ts",
                  "superseded_by_event_id": candidate.event_id,
                  "precedence_rule": "blocked_trigger takes precedence on a shared bar"},
        condition_met=False,
        evidence_refs=(str(event.event_id), candidate.event_id))


@dataclass(frozen=True, slots=True)
class C5Run:
    """Candidates, readings and episodes from one C5 interpretation."""

    candidates: tuple[C5Candidate, ...]
    readings: tuple[DetectorReading, ...]
    episodes: tuple[DetectorEpisode, ...] = ()
    minted_events: tuple[EntryEvent, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)


def run_c5(source: EntryEventStore | Sequence[EntryEvent]) -> C5Run:
    """Interpret a preserved event population as C5.

    ``minted_events`` is EMPTY and always will be: C5 reuses the Terminal watch
    events rather than minting new ones (§18 A5.8).  The field exists so a caller
    can assert the emptiness rather than infer it from a missing attribute.
    """
    events = tuple(source.events()) if isinstance(source, EntryEventStore) else tuple(source)
    by_id = {str(e.event_id): e for e in events}
    candidates = c5_candidates(events)
    readings: list[DetectorReading] = []
    episodes: list[DetectorEpisode] = []
    lc = lifecycle()

    for candidate in candidates:
        reading = c5_reading(candidate)
        readings.append(reading)
        for lost in candidate.superseded_event_ids:
            readings.append(superseded_reading(candidate, by_id[lost]))
        if not candidate.knowable:
            continue
        episode = DetectorEpisode(ticker=candidate.ticker,
                                  detector_id=C5_DETECTOR_ID,
                                  variant=candidate.subtype)
        at = str(candidate.signal_known_ts)
        episode.transition(lc.DetectorState.ARMED, at=at,
                           reason="preserved Terminal bottom-watch event, knowable at "
                                  "its own signal_known_ts (A5.6)",
                           evidence_refs=(candidate.event_id,))
        episode.first_armed_at = at
        episode.candidate_at = at
        episode.last_observed_at = at
        episode.event_ids.append(candidate.event_id)
        episode.transition(lc.DetectorState.CANDIDATE, at=at,
                           reason="(early_dot OR blocked_trigger) AND washed — the "
                                  "emitter's own candidate population (§3.4)",
                           evidence_refs=(candidate.event_id,))
        episodes.append(episode)

    counts = {
        "watch_events": len(watch_events(events)),
        "candidates": len(candidates),
        "blocked_trigger": sum(1 for c in candidates if c.subtype == "blocked_trigger"),
        "early_dot": sum(1 for c in candidates if c.subtype == "early_dot"),
        "superseded": sum(len(c.superseded_event_ids) for c in candidates),
        "unknowable": sum(1 for c in candidates if not c.knowable),
        "minted_events": 0,
    }
    return C5Run(candidates=candidates, readings=tuple(readings),
                 episodes=tuple(episodes), minted_events=(), counts=counts)
