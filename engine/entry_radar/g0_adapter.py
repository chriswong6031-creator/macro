"""engine/entry_radar/g0_adapter.py — champion G0, the Terminal grey anticipation dot.

BOUNDARY (contract §2), stated before anything else
---------------------------------------------------
This module is the ARTIFACT CONSUMER for Terminal's raw grey dot at
**1D-artifact grain**: it reads `mastermind.indicator/v1` and mints events.  It
is NOT a re-implementation and it computes no oscillator.

``engine/washout_turn.py`` (the WEEKLY washout-turn watch organ) and
``engine/mtf_upturn.py`` (the TS-R3 multi-timeframe upturn organ) are ADJACENT
display organs at a different grain and a different product — weekly / multi-week
watch vocabulary, not Radar's 1D live episode ledger.  Name similarity is not
identity.  Neither is imported here, neither is modified by this lane, and the
house precedent for the distinction is stated at ``engine/washout_turn.py:1-5``.
``engine/entry_signal.py`` and the gate chain are likewise never imported: Radar
reads artifacts, never gate code.

WHAT G0 IS (contract §3.1, frozen by §18 A1.1)
----------------------------------------------
The §3.1 mask, with no spec change.  Its POPULATION from an artifact is a UNION
of two channels, because the artifact's ``early_dots`` field carries only
*unpromoted* dots:

    population = early_dots ∪ {w.ts for w in bottom_watches if subtype == "early_dot"}

Reading ``early_dots`` alone silently loses exactly the deep-washout cohort —
3 of NFLX's 12 dots ≥2025 — which is the whole reason A1.1 pinned the union as an
F2 assertion.  The washout-promoted amber EARLY marker stays a DISTINCT recorded
family (A1.2); the union recovers the dot, it does not merge the families.

KNOWN_TS HONESTY (contract §18 A4.5)
------------------------------------
The ``early_dots`` channel is bare date strings — no type, no price, no quality,
no ``known_ts``.  This adapter does NOT recompute ``known_ts`` for side-channel
dots: that would be the §3.2 fallback reimplementation smuggled in as
provenance.  It records ``signal_known_ts = None`` with ``field_origin
artifact_absent`` and derives finality from a conservative session bound.
Watch-borne dots carry the emitter's ``known_ts`` verbatim.  The true
side-channel ``known_ts`` values measured at fixture generation live in
``research/live_entry_radar/W2_G0_PARITY_RECEIPTS.md`` §5 as generation receipts
only — deliberately not injected into events.

NO SYNTHESIS PATH.  G0 events enter from a slice or not at all: there is no
backfill API, no "seed from a date list", no historical reconstruction door.
Prospective-only families must have zero invented rows, and the cheapest way to
guarantee that is to own no function that could mint one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from engine.entry_radar.entry_events import (
    FINALITY_SIDE_CHANNEL,
    EntryEvent,
    EntryEventStore,
    EntryEventError,
    EventEdge,
    sha16,
)
from engine.entry_radar.indicator_ingest import (
    TERMINAL_PRODUCER,
    IndicatorSlice,
    build_watch_event,
    calendar_basis,
    feed_end_lower_bound,
    finality_from_known_ts,
    sessions_forward,
    side_channel_cap_window_start,
    slice_identity,
    unknowable_pre_cap_dates,
)

G0_DETECTOR_ID = "G0_GREY_DOT@1"
G0_VERSION = 1
G0_GRAIN = "1D_artifact"
G0_BAR_FAMILY = "terminal_3D_listing_anchored"

#: Sessions a side-channel dot's bar must be behind the feed's lower bound before
#: Radar will call it settled.  Three: the 3D bar is up to 2 sessions wide and
#: `known_ts` is its close session, so `ts + 3` clears the widest lawful gap.
G0_SETTLE_SESSIONS = 3

#: FROZEN spec block.  The hash of THIS dict is the detector's spec identity, so
#: editing any value below changes `g0_spec_hash()` and breaks the pinned literal
#: in `tests/test_entry_radar_w2_guards.py` — which is the point: a spec change
#: must never be silent.
G0_SPEC: dict[str, Any] = {
    "detector_id": G0_DETECTOR_ID,
    "version": G0_VERSION,
    "grain": G0_GRAIN,
    "bar_family": G0_BAR_FAMILY,
    "population_rule": "early_dots UNION bottom_watches[subtype==early_dot].ts",
    "population_authority": "contract §18 A1.1 (frozen)",
    "finality_side_channel": "ts + 3 sessions <= feed_end_lower_bound",
    "finality_known_ts": "known_ts < feed_end_lower_bound",
    "feed_end_semantics": "as_of is the last 3D bar OPEN date; lower bound on feed_end (A4.2)",
    "known_ts_side_channel": "artifact_absent — never recomputed (A4.5)",
    "era_pin": "gc_v2_wo2",
    "source": "charting-app signal_layer.confluence_v2 @ origin/master 82cb8cbf",
    "spec_change_policy": "no spec change; §3.1 mask exactly",
}

SIDE_CHANNEL = "side_channel"
WATCH_PROMOTED = "watch_promoted"
BOTH_CHANNELS = "both"

PROMOTION_PROVENANCE = "A1.1 union ts-join"
DEDUP_PROVENANCE = "A4.4 same-bar specimen; side channel retains the date"


class G0IntegrityError(EntryEventError):
    """The artifact contradicts the emitter's own de-duplication rule."""


def g0_spec_hash() -> str:
    """Stable 16-hex identity of the frozen spec block.  Same value every run."""
    return sha16(G0_SPEC)


#: FROZEN — what the SAME SLICE says about washout context on a dot's bar.  A
#: boolean here was wrong in a way that lost the emitter's own evidence: a
#: `blocked_trigger` watch on a dot's bar means the washout machinery DID fire on
#: that bar (it triggered and was blocked), so "washed = False" contradicted the
#: artifact.  Specimens: NFLX 2026-07-28 and 2018-12-26, TSLA 2022-06-22.
WASHOUT_EVIDENCE = ("promoted", "blocked_trigger_same_bar", "no_watch_on_bar")

PROMOTED = "promoted"
BLOCKED_TRIGGER_SAME_BAR = "blocked_trigger_same_bar"
NO_WATCH_ON_BAR = "no_watch_on_bar"


@dataclass(frozen=True, slots=True)
class G0Dot:
    """One dot in the reconstructed G0 population, with the channel it came from.

    ``source_channel`` says WHERE Radar found the dot; ``washout_evidence`` says
    what the emitter recorded about washout on that bar.  They are different
    questions and a dot can be side-channel-borne AND washed.
    """

    ts: str
    source_channel: str
    known_ts: str | None = None
    washout_evidence: str = NO_WATCH_ON_BAR


@dataclass(frozen=True, slots=True)
class G0Report:
    """What the adapter minted, per channel, with the edges it could synthesise."""

    symbol: str
    detector_id: str
    spec_hash: str
    feed_end_lower_bound: date
    cap_window_start: str | None
    dots: tuple[G0Dot, ...] = ()
    grey_event_ids: tuple[str, ...] = ()
    watch_event_ids: tuple[str, ...] = ()
    edges: tuple[EventEdge, ...] = ()
    unknowable_pre_cap: tuple[str, ...] = ()
    provably_no_dot: tuple[str, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "detector_id": self.detector_id,
            "spec_hash": self.spec_hash,
            "feed_end_lower_bound": self.feed_end_lower_bound.isoformat(),
            "cap_window_start": self.cap_window_start,
            "n_dots": len(self.dots),
            "grey_event_ids": list(self.grey_event_ids),
            "watch_event_ids": list(self.watch_event_ids),
            "edges": [e.to_dict() for e in self.edges],
            "unknowable_pre_cap": list(self.unknowable_pre_cap),
            "provably_no_dot": list(self.provably_no_dot),
            "counts": dict(self.counts),
        }


def g0_population(slice_: IndicatorSlice) -> list[G0Dot]:
    """The A1.1 union, ascending by ``ts``.

    Raises ``G0IntegrityError`` when a date appears in BOTH channels.  The
    emitter suppresses promoted dots from the side channel (``confluence_v2.py``
    ``promoted_dot_dates`` → ``unpromoted_early_dots``), so ``both`` is not a case
    to merge — it is evidence the suppression changed, and a union that quietly
    de-duplicated it would double-count the next time it did not.
    """
    side = set(slice_.early_dots)
    promoted: dict[str, dict[str, Any]] = {}
    for watch in slice_.bottom_watches:
        if watch.get("subtype") != "early_dot":
            continue
        promoted[str(watch.get("ts") or "")] = dict(watch)

    overlap = sorted(side & set(promoted))
    if overlap:
        raise G0IntegrityError(
            f"{slice_.symbol}: {overlap} appear in BOTH the early_dots side channel and "
            f"the early_dot watch stream; the emitter removes promoted dots from the side "
            f"channel, so this artifact contradicts its own de-duplication rule and the "
            f"union cannot be trusted to count each dot once")

    # Washout evidence reads EVERY BOTTOM_WATCH on the bar, not just promotions:
    # a blocked_trigger on a retained dot's bar is the emitter saying the washout
    # machinery fired there and was blocked.
    blocked_bars = {str(w.get("ts") or "") for w in slice_.bottom_watches
                    if w.get("subtype") == "blocked_trigger"}

    dots = [G0Dot(ts=ts, source_channel=SIDE_CHANNEL, known_ts=None,
                  washout_evidence=(BLOCKED_TRIGGER_SAME_BAR if ts in blocked_bars
                                    else NO_WATCH_ON_BAR))
            for ts in side]
    dots += [G0Dot(ts=ts, source_channel=WATCH_PROMOTED,
                   known_ts=str(raw.get("known_ts")) if raw.get("known_ts") else None,
                   washout_evidence=PROMOTED)
             for ts, raw in promoted.items()]
    return sorted(dots, key=lambda d: d.ts)


def _grey_field_origin(dot: G0Dot) -> dict[str, str]:
    watch_borne = dot.source_channel == WATCH_PROMOTED
    return {
        "event_id": "radar_derived",
        "producer": "radar_derived",
        "detector_id": "radar_derived",
        "ticker": "emitter_verbatim",
        "family": "radar_derived",
        # The side channel carries no type, no price, no quality (A1.2.1).
        "subtype": "artifact_absent",
        "stage": "artifact_absent",
        "quality": "artifact_absent",
        "context": "radar_derived",
        "signal_ts": "emitter_verbatim",
        # A4.5 — the honesty assertion.  Never "radar_derived": Radar did not
        # derive it, Radar declined to.
        "signal_known_ts": "emitter_verbatim" if watch_borne else "artifact_absent",
        "source_identity": "emitter_verbatim",
        "scored_authority": "artifact_absent",
        "family_first_available": "radar_derived",
        "family_era": "emitter_verbatim",
        "bar_state": "radar_derived",
        "final": "radar_derived",
        "finality_basis": "radar_derived",
        "authority": "radar_derived",
    }


def build_grey_dot_event(slice_: IndicatorSlice, dot: G0Dot, *, lower_bound: date,
                         calendar: Any | None = None) -> EntryEvent:
    """One ``grey_dot`` event.  Finality depends on which channel carried it."""
    if dot.source_channel == WATCH_PROMOTED:
        final, bar_state, basis = finality_from_known_ts(dot.known_ts, lower_bound)
    else:
        settle = sessions_forward(date.fromisoformat(dot.ts), G0_SETTLE_SESSIONS,
                                  calendar=calendar)
        final = settle <= lower_bound
        bar_state = "confirmed" if final else "provisional"
        # WHICH ruler produced the +3 is part of the claim.  Two events with the
        # same basis string measured on different calendars are not comparable,
        # and the fallback ruler drifts from NYSE across every holiday.
        basis = f"{FINALITY_SIDE_CHANNEL}[{calendar_basis(calendar)}]"
    return EntryEvent(
        producer=TERMINAL_PRODUCER,
        detector_id=G0_DETECTOR_ID,
        ticker=slice_.symbol,
        family="grey_dot",
        subtype=None,
        stage=None,
        quality=None,
        context={"source_channel": dot.source_channel,
                 "washout_evidence": dot.washout_evidence},
        signal_ts=dot.ts,
        signal_known_ts=dot.known_ts,
        source_identity=slice_identity(slice_, detector_spec_hash=g0_spec_hash()),
        scored_authority=None,
        family_era=slice_.signal_era,
        field_origin=_grey_field_origin(dot),
        bar_state=bar_state,
        final=final,
        finality_basis=basis,
    )


def g0_events(slice_: IndicatorSlice, store: EntryEventStore, *,
              calendar: Any | None = None) -> G0Report:
    """Mint the G0 population plus every watch event and typed edge it implies.

    Freshness/identity are the INGEST door's gates (``indicator_ingest``); this
    function is a projection of a slice already admitted.  What it cannot get
    wrong regardless is finality, which derives only from the slice's own
    ``as_of`` — a replayed slice can never be marked settled by a later clock.
    """
    lower = feed_end_lower_bound(slice_)
    cap_start = side_channel_cap_window_start(slice_)
    side = set(slice_.early_dots)

    # PHASE 1 — build and validate everything.  Nothing reaches the store until
    # the whole slice is known good: an append-only store cannot be rolled back,
    # so a half-ingested slice is a permanent lie about what we read.
    dots = g0_population(slice_)
    grey_by_ts: dict[str, EntryEvent] = {
        dot.ts: build_grey_dot_event(slice_, dot, lower_bound=lower, calendar=calendar)
        for dot in dots
    }
    watch_by_key: dict[tuple[str, str], EntryEvent] = {
        (str(raw.get("subtype") or ""), str(raw.get("ts") or "")):
            build_watch_event(slice_, raw, lower_bound=lower)
        for raw in slice_.bottom_watches
    }

    edges: list[EventEdge] = []
    provable_absence: list[str] = []
    unknowable = list(unknowable_pre_cap_dates(slice_))

    for dot in dots:
        if dot.source_channel != WATCH_PROMOTED:
            continue
        watch = watch_by_key.get(("early_dot", dot.ts))
        if watch is None:  # unreachable: the dot came FROM that watch
            raise G0IntegrityError(f"{slice_.symbol}: promoted dot {dot.ts} has no watch event")
        edge = EventEdge(
            relation="promoted_by",
            source_event_id=str(watch.event_id),
            target_event_id=str(grey_by_ts[dot.ts].event_id),
            link_basis="ts_join_synthesized",
            known_lossy=False,
            provenance=PROMOTION_PROVENANCE)
        edges.append(edge)

    for raw in slice_.bottom_watches:
        if raw.get("subtype") != "blocked_trigger":
            continue
        ts = str(raw.get("ts") or "")
        watch = watch_by_key[("blocked_trigger", ts)]
        if ts in side:
            # A4.4 live specimen: the raw dot AND the blocked trigger fired on one
            # bar, and the side channel RETAINED the date (suppression removes only
            # `early_dot` promotions), so the link is ts-join-synthesizable in-cap.
            edge = EventEdge(
                relation="dedup_suppressed_by",
                source_event_id=str(grey_by_ts[ts].event_id),
                target_event_id=str(watch.event_id),
                link_basis="ts_join_synthesized",
                known_lossy=False,
                provenance=DEDUP_PROVENANCE)
            edges.append(edge)
        elif cap_start is not None and ts < cap_start:
            # Outside the cap the channel's silence says nothing.  Reported on the
            # SLICE (`unknowable_pre_cap`), never stamped on the event: the cap
            # window slides between vintages and event content may not (B1).
            continue
        else:
            # In-cap and absent from the channel ⇒ provably no dot fired.  The
            # complementary negative (NFLX 2026-02-20); no edge, and correctly
            # excluded from the G0 population.
            provable_absence.append(ts)

    # PHASE 2 — commit.  Events first (edges validate their endpoints against the
    # store), then edges.
    for event in list(grey_by_ts.values()) + list(watch_by_key.values()):
        store.append(event)
    for edge in edges:
        store.add_edge(edge)

    counts = {
        "dots_total": len(dots),
        "dots_side_channel": sum(1 for d in dots if d.source_channel == SIDE_CHANNEL),
        "dots_watch_promoted": sum(1 for d in dots if d.source_channel == WATCH_PROMOTED),
        "dots_final": sum(1 for ts in grey_by_ts if grey_by_ts[ts].final),
        "watch_events": len(watch_by_key),
        "edges_promoted_by": sum(1 for e in edges if e.relation == "promoted_by"),
        "edges_dedup_suppressed_by": sum(1 for e in edges
                                         if e.relation == "dedup_suppressed_by"),
    }
    return G0Report(
        symbol=slice_.symbol,
        detector_id=G0_DETECTOR_ID,
        spec_hash=g0_spec_hash(),
        feed_end_lower_bound=lower,
        cap_window_start=cap_start,
        dots=tuple(dots),
        grey_event_ids=tuple(str(grey_by_ts[d.ts].event_id) for d in dots),
        watch_event_ids=tuple(str(e.event_id) for e in watch_by_key.values()),
        edges=tuple(edges),
        unknowable_pre_cap=tuple(sorted(unknowable)),
        provably_no_dot=tuple(sorted(provable_absence)),
        counts=counts,
    )
