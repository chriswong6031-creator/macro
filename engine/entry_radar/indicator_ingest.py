"""engine/entry_radar/indicator_ingest.py — governed `mastermind.indicator/v1` consumption.

WHAT THIS IS (contract §3.2 primary path)
-----------------------------------------
Radar consumes the versioned Terminal artifact.  It computes NO indicator: there
is no RSI here, no StochRSI, no MACD, no session grid — the emitter already did
that and this module's whole job is to carry its output across the boundary
without losing anything.  Anything that starts computing an oscillator has left
W2's scope and belongs in the §3.2 locked-spec fallback, which is not this file.

THREE GATES, ALL FAIL-CLOSED
----------------------------
``freshness_gate``   §3.2's mandatory staleness hard-gate.  STALE is a REFUSAL
                     state, not a warning: the census once read a 5-week-stale
                     store and reported it as current.
``identity_gate``    ``(source_hash, signal_era)`` pinning — the strategy-spec
                     pin.  A slice from another spec or another era is LANE-STALE
                     and is refused, never silently pooled.
``pre-fence``        a slice with NO ``signal_era`` is pre-fence and is refused
                     by default.  The emitter's own comment forbids pooling
                     fenced with pre-fence emission; ``allow_pre_fence=True``
                     admits it and records ``SIGNAL_ERA_PRE`` on every event, so
                     the pooling stays visible downstream instead of invisible.

`as_of` IS NOT THE FEED END (contract §18 A4.2)
-----------------------------------------------
``contracts.indicator_contract`` derives ``as_of`` from ``bars[-1]``, and those
are 3D-bar OPEN dates; the slim slice drops ``bars`` entirely, so no exact
feed-end field survives.  Bounds: ``feed_end ∈ [as_of, as_of + 2 sessions]``.
The accessor is therefore named ``feed_end_lower_bound`` and never ``feed_end``
— the error direction is fail-closed (a slice can only be FRESHER than its
``as_of`` suggests) and a reader who thinks it has the feed end will eventually
mark a provisional event final.

VERBATIM OR NOTHING (contract §18 A1.2/A1.2.3)
----------------------------------------------
The emitter's ``type``/``subtype``/``quality`` strings are preserved exactly, and
the complete raw signal dict rides in ``context`` unrenamed and unflattened.
``scored`` is recorded as ``scored_authority`` — a fact about the emitter's own
claim, never a grant.  SELL (``basis="structure_stop"``) and the ARM/CONFIRM
``warnings`` channel are exit-side (A4.3): they are NOT entry-event families, so
they are excluded and COUNTED — an exclusion nobody counts is a silent drop.

WRITE DISCIPLINE (contract §7.3): no ``data/`` path, no durable writer, no
``ledger_lane`` import.  PR-5 owns durability.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

from engine.entry_radar.entry_events import (
    FINALITY_KNOWN_TS,
    FINALITY_NO_CLOCK,
    EntryEvent,
    EntryEventStore,
    SourceIdentity,
)

SCHEMA_INDICATOR = "mastermind.indicator/v1"

#: The producer key stamped on every event minted from this artifact family.
TERMINAL_PRODUCER = "terminal.confluence_v2"

#: Recorded era for a slice that carries none.  Never pooled with a fenced era.
SIGNAL_ERA_PRE = "SIGNAL_ERA_PRE"

# --- PINNED IDENTITY -------------------------------------------------------
# Frozen in CODE, deliberately not read from the fixture at runtime: a gate that
# loads its own expected value from the artifact it is gating cannot fail.  The
# values are the ones receipted in `tests/fixtures/entry_radar/provenance.json`
# and `research/live_entry_radar/W2_G0_PARITY_RECEIPTS.md` §3 (signal layer =
# charting-app origin/master @ 82cb8cbf).
EXPECTED_SIGNAL_ERA = "gc_v2_wo2"
EXPECTED_SOURCE_HASH = (
    "sha256:f27a407bea861a2217477beb98c398abc62845d2bcc38d331d4963c06471986d"
)

#: The `early_dots` side channel is capped by the emitter (§3.2 / A4.4).
SIDE_CHANNEL_CAP = 40

#: The ARM/CONFIRM `warnings` channel is capped by the emitter too.  An exclusion
#: COUNT taken off a capped channel is a floor, not a total — "40 warnings
#: excluded" from a slice sitting exactly at the cap means "at least 40", and a
#: consumer that reads it as a total has silently mis-sized the exit-side stream.
WARNINGS_CAP = 40

#: §3.2's staleness gate scale.  Overridable per call; never silently absent.
DEFAULT_MAX_AGE_SESSIONS = 5

#: A4.3 type → family.  SELL is absent ON PURPOSE (exit-side, not a family).
TYPE_TO_FAMILY: dict[str, str] = {
    "BUY": "oracle_buy",
    "REBUY": "oracle_rebuy",
    "RECLAIM": "oracle_reclaim",
}

#: A4.3 BOTTOM_WATCH subtype → family.
WATCH_SUBTYPE_TO_FAMILY: dict[str, str] = {
    "early_dot": "washout_early_watch",
    "blocked_trigger": "washout_trigger_watch",
}

EXIT_SIDE_TYPES: frozenset[str] = frozenset({"SELL"})

#: Default ingest surface.  ``grey_dot`` is deliberately NOT here: the G0
#: population is a UNION of two channels and only ``g0_adapter`` may mint it.
INGEST_FAMILIES: tuple[str, ...] = (
    "washout_early_watch",
    "washout_trigger_watch",
    "oracle_buy",
    "oracle_rebuy",
    "oracle_reclaim",
)

class IndicatorSliceError(ValueError):
    """A slice that is not a well-formed `mastermind.indicator/v1` document."""


class StaleFeedRefusal(IndicatorSliceError):
    """The §3.2 freshness hard-gate refused the slice as too old."""


class FutureDatedSlice(IndicatorSliceError):
    """The slice's ``as_of`` postdates the reference clock — corrupt, not fresh."""


class IdentityMismatch(IndicatorSliceError):
    """`(source_hash, signal_era)` does not match the pinned spec — LANE-STALE."""


class PreFenceEraRefusal(IndicatorSliceError):
    """A pre-fence slice may not be pooled with fenced emission."""


class CalendarUnanswerable(IndicatorSliceError):
    """A session calendar is present but cannot answer — refuse, never substitute."""


# ---------------------------------------------------------------------------
# session arithmetic — nyse where importable, business days otherwise, SAID
# ---------------------------------------------------------------------------

CALENDAR_NYSE = "nyse_calendar"
CALENDAR_BUSINESS_DAYS = "business_day_fallback"

#: The module path that earns the ``nyse_calendar`` claim.  Identity, not duck
#: typing: an object that merely has a ``sessions_between`` attribute is not the
#: NYSE calendar, and a basis string is a claim about WHICH ruler measured a
#: number.  Anything else must call itself what it is.
_NYSE_MODULE_NAME = "lib.nyse_calendar"


def _nyse():
    try:  # pragma: no cover - import availability is environment-dependent
        from lib import nyse_calendar
    except Exception:
        return None
    return nyse_calendar


def calendar_basis(calendar: Any | None = None) -> str:
    """Which session ruler measured a number.  Verified, never assumed.

    Only claims ``nyse_calendar`` when the object verifiably IS it — module
    identity, or an explicit ``BASIS_NAME`` the object declares about itself.
    A stub handed in by a test is not the NYSE calendar and must not be able to
    borrow its name by having the right method.
    """
    cal = calendar if calendar is not None else _nyse()
    if cal is None:
        return CALENDAR_BUSINESS_DAYS
    declared = getattr(cal, "BASIS_NAME", None)
    if declared:
        return str(declared)
    if getattr(cal, "__name__", "") == _NYSE_MODULE_NAME:
        return CALENDAR_NYSE
    return f"unverified_calendar({getattr(cal, '__name__', type(cal).__name__)})"


def _business_days_between(older: date, newer: date) -> int:
    if newer <= older:
        return 0
    n, cursor = 0, older + timedelta(days=1)
    while cursor <= newer:
        if cursor.weekday() < 5:
            n += 1
        cursor += timedelta(days=1)
    return n


def sessions_apart(older: date, newer: date, *, calendar: Any | None = None) -> int:
    """Session steps from ``older`` to ``newer``; 0 when inverted or equal.

    Deliberately total (never ``None``): this feeds a staleness verdict, and a
    ``None`` age here would have to be rendered as either "fresh" or "stale"
    somewhere downstream, silently.
    """
    cal = calendar if calendar is not None else _nyse()
    if newer <= older:
        return 0
    if cal is not None:
        return max(0, len(cal.sessions_between(older, newer)) - 1)
    return _business_days_between(older, newer)


def sessions_forward(start: date, n: int, *, calendar: Any | None = None) -> date:
    """The date ``n`` sessions after ``start``.  NO silent mid-computation fallback.

    When a session calendar is present but cannot answer — ``start`` is not a
    session, or the lookup returns ``None`` — this RAISES.  Substituting business
    days there would mix two rulers inside one number while the recorded basis
    still named the calendar, which is the failure mode the basis string exists
    to prevent.  The business-day path is reached only when the calendar module is
    genuinely unavailable, and the basis says so.
    """
    cal = calendar if calendar is not None else _nyse()
    if cal is not None:
        got = cal.session_n_forward(start, n)
        if got is None:
            raise CalendarUnanswerable(
                f"{calendar_basis(cal)} cannot step {n} sessions forward from "
                f"{start.isoformat()} (not a session, or beyond its horizon); "
                f"refusing to substitute business days inside a calendar-based "
                f"computation")
        return got
    cursor, stepped = start, 0
    while stepped < n:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            stepped += 1
    return cursor


# ---------------------------------------------------------------------------
# the slice
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class IndicatorSlice:
    """One `mastermind.indicator/v1` document, unflattened.

    ``signals`` holds the RAW event dicts verbatim — no renaming, no key
    projection, no per-type normalisation.  Everything typed downstream is a
    PROJECTION of these dicts, so a field this package has not thought about yet
    is still carried rather than lost.
    """

    symbol: str
    as_of: date
    signal_era: str
    pre_fence: bool
    source_hash: str | None
    params: dict[str, Any]
    early_dots: tuple[str, ...]
    n_warnings: int
    warnings_oldest_ts: str | None
    signals: tuple[dict[str, Any], ...]
    state: dict[str, Any] = field(default_factory=dict)
    bar_quality: Any = None
    meta: dict[str, Any] = field(default_factory=dict)
    timeframe: str | None = None
    origin: str = ""

    def signals_of_type(self, kind: str) -> tuple[dict[str, Any], ...]:
        return tuple(s for s in self.signals if s.get("type") == kind)

    @property
    def bottom_watches(self) -> tuple[dict[str, Any], ...]:
        return self.signals_of_type("BOTTOM_WATCH")


def load_slice(path_or_dict: str | Path | Mapping[str, Any]) -> IndicatorSlice:
    """Read a slice from a path or an already-parsed mapping.

    Accepts the production SLIM shape ``{"indicator": <doc>}`` and a bare doc.
    The unwrap keys on the inner document's own ``schema`` field — the doc also
    carries an ``indicator`` block (engine/params/source_hash) which has none, so
    the two never confuse each other.
    """
    origin = ""
    if isinstance(path_or_dict, (str, Path)):
        origin = str(path_or_dict)
        raw = json.loads(Path(path_or_dict).read_text(encoding="utf-8"))
    else:
        raw = dict(path_or_dict)
    if not isinstance(raw, dict):
        raise IndicatorSliceError(f"slice must be a JSON object, got {type(raw).__name__}")

    doc = raw
    inner = raw.get("indicator")
    if isinstance(inner, dict) and inner.get("schema") == SCHEMA_INDICATOR:
        doc = inner
    if doc.get("schema") != SCHEMA_INDICATOR:
        raise IndicatorSliceError(
            f"schema {doc.get('schema')!r} is not {SCHEMA_INDICATOR!r}; Radar consumes the "
            f"versioned artifact and nothing else")

    block = doc.get("indicator") or {}
    if not isinstance(block, dict):
        block = {}

    era_raw = doc.get("signal_era")
    pre_fence = not str(era_raw or "").strip()
    signal_era = SIGNAL_ERA_PRE if pre_fence else str(era_raw)

    as_of_raw = doc.get("as_of")
    as_of = _as_date(as_of_raw)
    if as_of is None:
        raise IndicatorSliceError(f"as_of {as_of_raw!r} is not an ISO date/datetime")

    signals = doc.get("signals") or []
    if not isinstance(signals, list):
        raise IndicatorSliceError("signals must be a list of raw event objects")
    early = doc.get("early_dots") or []
    if not isinstance(early, list):
        raise IndicatorSliceError("early_dots must be a list of date strings")
    warnings = doc.get("warnings") or []

    return IndicatorSlice(
        symbol=str(doc.get("symbol") or "").strip().upper(),
        as_of=as_of,
        signal_era=signal_era,
        pre_fence=pre_fence,
        source_hash=block.get("source_hash"),
        params=dict(block.get("params") or {}),
        early_dots=tuple(str(d) for d in early),
        n_warnings=len(warnings),
        warnings_oldest_ts=min((str(w.get("ts")) for w in warnings
                                if isinstance(w, dict) and w.get("ts")), default=None),
        signals=tuple(dict(s) for s in signals),
        state=dict(doc.get("state") or {}),
        bar_quality=doc.get("bar_quality"),
        meta=dict(doc.get("meta") or {}),
        timeframe=doc.get("timeframe"),
        origin=origin,
    )


def _as_date(raw: Any) -> date | None:
    if isinstance(raw, date):
        return raw
    if raw is None:
        return None
    txt = str(raw).strip()
    if not txt:
        return None
    try:
        return date.fromisoformat(txt[:10])
    except ValueError:
        return None


def feed_end_lower_bound(slice_: IndicatorSlice) -> date:
    """A4.2: ``as_of`` is the last 3D bar's OPEN date, a LOWER bound on feed_end.

    Named for what it is.  ``feed_end ∈ [as_of, as_of + 2 sessions]`` and the
    exact value survives only where ``bars`` ride the doc (flagship shape).
    """
    return slice_.as_of


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FreshnessVerdict:
    """§3.2's staleness verdict, with the ruler it used written down.

    ``age_sessions_upper_bound`` is measured from ``feed_end_lower_bound`` — from
    the EARLIEST feed end the slice could have (A4.2) — so it UPPER-bounds the
    slice's true age.  Read the two verdicts accordingly:

      FRESH  definitely fresh.  The true feed end is at or after the bound, so
             the real age can only be smaller than the number reported.
      STALE  may overshoot by at most the A4.2 two-session slack.

    That asymmetry is the fail-closed direction: the gate can refuse a slice that
    was marginally acceptable, and can never admit one that was genuinely stale.
    """

    verdict: str
    feed_end_lower_bound: date
    age_sessions_upper_bound: int
    basis: str

    @property
    def stale(self) -> bool:
        return self.verdict == "STALE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "feed_end_lower_bound": self.feed_end_lower_bound.isoformat(),
            "age_sessions_upper_bound": self.age_sessions_upper_bound,
            "basis": self.basis,
        }


def freshness_gate(slice_: IndicatorSlice, *, as_of_reference_date: date,
                   max_age_sessions: int = DEFAULT_MAX_AGE_SESSIONS,
                   calendar: Any | None = None) -> FreshnessVerdict:
    """FRESH / STALE against a stated reference date.  Never silently absent.

    A slice whose ``as_of`` POSTDATES the reference raises ``FutureDatedSlice``
    rather than clamping to age 0.  Both readings of that state are refusals:
    either the artifact is corrupt, or the clock this gate was handed is wrong —
    and "fresh" is the one answer that is certainly unsafe, because it is what a
    zero-age clamp would return for an artifact dated arbitrarily far ahead.
    """
    lower = feed_end_lower_bound(slice_)
    if lower > as_of_reference_date:
        raise FutureDatedSlice(
            f"{slice_.symbol or '<no symbol>'} slice as_of {lower.isoformat()} "
            f"postdates the reference date {as_of_reference_date.isoformat()}; a "
            f"future-dated artifact is corrupt or the reference clock is wrong — "
            f"refused rather than clamped to FRESH")
    basis = calendar_basis(calendar)
    age = sessions_apart(lower, as_of_reference_date, calendar=calendar)
    verdict = "STALE" if age > max_age_sessions else "FRESH"
    return FreshnessVerdict(verdict=verdict, feed_end_lower_bound=lower,
                            age_sessions_upper_bound=age,
                            basis=f"{basis}; max_age_sessions={max_age_sessions}; "
                                  f"reference={as_of_reference_date.isoformat()}")


def identity_gate(slice_: IndicatorSlice, *,
                  expected_source_hash: str | None = EXPECTED_SOURCE_HASH,
                  expected_signal_era: str | None = EXPECTED_SIGNAL_ERA) -> None:
    """Pin ``(source_hash, signal_era)``.  Raises ``IdentityMismatch`` on drift.

    This is the strategy-spec pin: a slice produced by a different spec revision,
    or under a different era fence, describes a different emitter.  Pooling it
    with pinned emission is the LANE-STALE failure the gate exists to refuse.
    """
    problems: list[str] = []
    if expected_source_hash is not None and slice_.source_hash != expected_source_hash:
        problems.append(f"source_hash {slice_.source_hash!r} != {expected_source_hash!r}")
    if expected_signal_era is not None and slice_.signal_era != expected_signal_era:
        problems.append(f"signal_era {slice_.signal_era!r} != {expected_signal_era!r}")
    if problems:
        raise IdentityMismatch(
            f"{slice_.symbol or '<no symbol>'} slice identity mismatch: "
            f"{'; '.join(problems)} — LANE-STALE, refused rather than pooled")


# ---------------------------------------------------------------------------
# side channel geometry (A4.4) — an ARTIFACT fact, shared by every consumer
# ---------------------------------------------------------------------------

def side_channel_cap_window_start(slice_: IndicatorSlice) -> str | None:
    """Oldest date the ``early_dots`` channel can still speak about, or None.

    ``None`` means the channel is UNCAPPED in this slice (fewer than the cap's
    worth of dots survive), so its silence about a date is informative for the
    whole history.  When it is capped, silence before this date says nothing.
    """
    if not slice_.early_dots:
        return None
    if len(slice_.early_dots) < SIDE_CHANNEL_CAP:
        return None
    return min(slice_.early_dots)


def unknowable_pre_cap_dates(slice_: IndicatorSlice) -> tuple[str, ...]:
    """blocked_trigger bars whose dot-coincidence THIS SLICE cannot answer for.

    A4.4 narrowed A1.1's blanket known-lossy claim: inside the cap window the
    channel's silence PROVES no dot fired (NFLX 2026-02-20); outside it the
    absence is a cap artifact, and saying "no dot" there would render missing
    knowledge as a negative observation.

    THIS IS A PROPERTY OF THE (event, SLICE VINTAGE) PAIR, NOT OF THE EVENT.  The
    cap window slides every time the emitter adds a dot, so the same bar is
    unknowable in one slice and provable in the next.  It therefore belongs on the
    per-slice REPORT and must never ride event ``context``: a vintage-varying
    field inside event content means the same ``event_id`` carries two bodies
    across two reads, and the append-only store would refuse the second — turning
    a routine re-ingest of an older vintage into a mid-slice crash.
    """
    cap_start = side_channel_cap_window_start(slice_)
    if cap_start is None:
        return ()
    side = set(slice_.early_dots)
    return tuple(sorted(
        ts for ts in (str(w.get("ts") or "") for w in slice_.bottom_watches
                      if w.get("subtype") == "blocked_trigger")
        if ts not in side and ts < cap_start))


# ---------------------------------------------------------------------------
# event construction (shared by this module and g0_adapter)
# ---------------------------------------------------------------------------

def slice_identity(slice_: IndicatorSlice, *,
                   detector_spec_hash: str | None = None) -> SourceIdentity:
    return SourceIdentity(source_hash=slice_.source_hash,
                          signal_era=slice_.signal_era,
                          detector_spec_hash=detector_spec_hash)


def finality_from_known_ts(known_ts: str | None, lower_bound: date) -> tuple[bool, str, str]:
    """A4.1/F6c: ``final ⟺ known_ts < feed_end_lower_bound``.

    Conservative on purpose.  An event whose ``known_ts`` EQUALS the artifact edge
    is provisional and may vanish on settle, and an event whose ``known_ts`` is
    AFTER the edge has not settled either — both land not-final.
    """
    parsed = _as_date(known_ts)
    if parsed is None:
        return (False, "provisional", FINALITY_NO_CLOCK)
    final = parsed < lower_bound
    return (final, "confirmed" if final else "provisional", FINALITY_KNOWN_TS)


def signal_field_origin(raw: Mapping[str, Any], *, pre_fence: bool = False,
                        subtype_lifted_from_quality: bool = False,
                        extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Per-field provenance for an event minted from a raw signal dict.

    Two honesty rules the obvious version gets wrong:

    * A PRE-FENCE slice carries no ``signal_era`` at all.  ``SIGNAL_ERA_PRE`` is
      RADAR's sentinel for that absence, so ``family_era`` and ``source_identity``
      are ``artifact_absent`` there — marking them ``emitter_verbatim`` would
      attribute Radar's own placeholder to the emitter.
    * For the oracle families ``subtype`` is LIFTED from ``quality`` by Radar's
      mapping.  The VALUE is the emitter's string and its verbatim-ness is already
      recorded on ``quality``; the decision to put it in the ``subtype`` slot is
      Radar's, so that field is ``radar_derived``.
    """
    era_origin = "artifact_absent" if pre_fence else "emitter_verbatim"
    if subtype_lifted_from_quality:
        subtype_origin = "radar_derived"
    elif "subtype" in raw:
        subtype_origin = "emitter_verbatim"
    else:
        subtype_origin = "artifact_absent"
    origin = {
        "event_id": "radar_derived",
        "producer": "radar_derived",
        "detector_id": "radar_derived",
        "ticker": "emitter_verbatim",
        "family": "radar_derived",
        "subtype": subtype_origin,
        # A4.3: no `stage` field exists anywhere in the indicator/v1 signal stream.
        "stage": "artifact_absent",
        "quality": "emitter_verbatim" if "quality" in raw else "artifact_absent",
        "context": "emitter_verbatim",
        "signal_ts": "emitter_verbatim",
        "signal_known_ts": "emitter_verbatim" if raw.get("known_ts") else "artifact_absent",
        "source_identity": era_origin,
        "scored_authority": "emitter_verbatim" if "scored" in raw else "artifact_absent",
        "family_first_available": "radar_derived",
        "pre_channel_reconstruction": "radar_derived",
        "family_era": era_origin,
        "bar_state": "radar_derived",
        "final": "radar_derived",
        "finality_basis": "radar_derived",
        "authority": "radar_derived",
    }
    origin.update(extra or {})
    return origin


def build_signal_event(slice_: IndicatorSlice, raw: Mapping[str, Any], *, family: str,
                       subtype: str | None, lower_bound: date,
                       subtype_lifted_from_quality: bool = False,
                       origin_extra: Mapping[str, str] | None = None) -> EntryEvent:
    """One EntryEvent from one raw signal dict.  The context is the WHOLE dict.

    Carrying the complete raw record (not a chosen subset) is the no-flattening
    law made cheap: a key this package has never heard of still arrives at the
    consumer, and the typed fields above it are visibly projections of it.

    It also carries the same-bar discriminator for free: ``raw["anchor_ts"]``
    rides ``context`` verbatim, and ``EntryEvent`` reads it from there when it
    derives the address (``entry_events.event_discriminator``).  So the address
    is a function of the event's own recorded content — a serialised event
    re-derives the identical id, with no side-channel field to keep in sync.
    """
    # Context is the raw record and NOTHING ELSE.  A Radar-derived key added here
    # would have to be constant across every vintage the event can appear in, or
    # it changes content at a fixed address (B1) — so nothing is added here.
    context: dict[str, Any] = dict(raw)
    origin: dict[str, str] = dict(origin_extra or {})

    known_ts = raw.get("known_ts")
    final, bar_state, basis = finality_from_known_ts(known_ts, lower_bound)
    return EntryEvent(
        producer=TERMINAL_PRODUCER,
        detector_id=None,  # recorded family, not an arena detector (A1.2.4)
        ticker=slice_.symbol,
        family=family,
        subtype=subtype,
        stage=None,
        quality=raw.get("quality"),
        context=context,
        signal_ts=str(raw.get("ts") or ""),
        signal_known_ts=str(known_ts) if known_ts else None,
        source_identity=slice_identity(slice_),
        scored_authority=raw.get("scored") if "scored" in raw else None,
        family_era=slice_.signal_era,
        field_origin=signal_field_origin(
            raw, pre_fence=slice_.pre_fence,
            subtype_lifted_from_quality=subtype_lifted_from_quality, extra=origin),
        bar_state=bar_state,
        final=final,
        finality_basis=basis,
    )


def build_watch_event(slice_: IndicatorSlice, raw: Mapping[str, Any], *,
                      lower_bound: date) -> EntryEvent:
    """A BOTTOM_WATCH event, identical whichever door mints it."""
    subtype = str(raw.get("subtype") or "")
    family = WATCH_SUBTYPE_TO_FAMILY.get(subtype)
    if family is None:
        raise IndicatorSliceError(
            f"BOTTOM_WATCH subtype {subtype!r} is not a minted family "
            f"({sorted(WATCH_SUBTYPE_TO_FAMILY)}); families are minted from receipts "
            f"(A4.3), so an unknown subtype is a receipt gap, not a default")
    # No cap-window marker rides this event: dot-coincidence knowability is a
    # property of the SLICE VINTAGE, and it is reported per slice instead
    # (`unknowable_pre_cap_dates`, IngestReport/G0Report `unknowable_pre_cap`).
    return build_signal_event(slice_, raw, family=family, subtype=subtype,
                              lower_bound=lower_bound)


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class IngestReport:
    """What one ingest did, INCLUDING what it refused to carry."""

    symbol: str
    signal_era: str
    source_hash: str | None
    pre_fence: bool
    freshness: FreshnessVerdict
    n_signals: int
    event_ids: tuple[str, ...] = ()
    by_family: dict[str, int] = field(default_factory=dict)
    excluded_exit_side: dict[str, int] = field(default_factory=dict)
    excluded_family_filter: int = 0
    excluded_unknown_type: dict[str, int] = field(default_factory=dict)
    #: M5 — the warnings channel is emitter-CAPPED, so its exclusion count is a
    #: floor.  Kept beside the plain int rather than inside it, so
    #: ``excluded_exit_side`` stays a dict[str, int] a caller can sum.
    excluded_warnings_detail: dict[str, Any] = field(default_factory=dict)
    #: B1 — blocked_trigger bars this SLICE VINTAGE cannot answer dot-coincidence
    #: for.  Per-slice, never per-event: the cap window slides.
    unknowable_pre_cap: tuple[str, ...] = ()

    @property
    def n_ingested(self) -> int:
        return len(self.event_ids)

    @property
    def n_excluded_exit_side(self) -> int:
        return sum(self.excluded_exit_side.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "signal_era": self.signal_era,
            "source_hash": self.source_hash,
            "pre_fence": self.pre_fence,
            "freshness": self.freshness.to_dict(),
            "n_signals": self.n_signals,
            "n_ingested": self.n_ingested,
            "by_family": dict(self.by_family),
            "excluded_exit_side": dict(self.excluded_exit_side),
            "excluded_family_filter": self.excluded_family_filter,
            "excluded_unknown_type": dict(self.excluded_unknown_type),
            "excluded_warnings_detail": dict(self.excluded_warnings_detail),
            "unknowable_pre_cap": list(self.unknowable_pre_cap),
        }


def ingest_slice(slice_: IndicatorSlice, store: EntryEventStore, *,
                 as_of_reference_date: date,
                 families: Iterable[str] = INGEST_FAMILIES,
                 max_age_sessions: int = DEFAULT_MAX_AGE_SESSIONS,
                 allow_stale: bool = False,
                 allow_pre_fence: bool = False,
                 calendar: Any | None = None) -> IngestReport:
    """Convert the signal stream into entry events, preserving everything.

    ``as_of_reference_date`` is REQUIRED: a freshness verdict with no stated
    clock is not a verdict.  ``allow_stale=True`` is the historical-replay door —
    it admits an aged slice, and finality STILL derives from that slice's own
    ``as_of``, so replayed events cannot be marked settled by a later clock.
    """
    wanted = tuple(families)
    unknown_family = [f for f in wanted if f not in INGEST_FAMILIES]
    if unknown_family:
        raise IndicatorSliceError(f"families {unknown_family} are not ingestable here "
                                  f"({list(INGEST_FAMILIES)}); grey_dot is minted only by "
                                  f"g0_adapter, from the two-channel union")

    freshness = freshness_gate(slice_, as_of_reference_date=as_of_reference_date,
                               max_age_sessions=max_age_sessions, calendar=calendar)
    if freshness.stale and not allow_stale:
        raise StaleFeedRefusal(
            f"{slice_.symbol} slice is STALE: feed_end_lower_bound "
            f"{freshness.feed_end_lower_bound.isoformat()} is at most "
            f"{freshness.age_sessions_upper_bound} "
            f"sessions behind {as_of_reference_date.isoformat()} "
            f"(max {max_age_sessions}; {freshness.basis}) — pass allow_stale=True only for "
            f"historical replay")
    if slice_.pre_fence and not allow_pre_fence:
        raise PreFenceEraRefusal(
            f"{slice_.symbol} slice carries no signal_era (pre-fence emission); pooling "
            f"pre-fence with fenced emission is forbidden by the emitter's own rule — "
            f"pass allow_pre_fence=True to ingest it with era {SIGNAL_ERA_PRE!r} recorded")

    lower = freshness.feed_end_lower_bound
    built: list[EntryEvent] = []
    by_family: dict[str, int] = {}
    exit_side: dict[str, int] = {}
    unknown_type: dict[str, int] = {}
    warnings_detail: dict[str, Any] = {}
    filtered = 0

    if slice_.n_warnings:
        # ARM/CONFIRM warnings are exit-side too (A4.3): excluded, never dropped
        # silently.  A count is the difference between a boundary and a leak.
        exit_side["warnings"] = slice_.n_warnings
        warnings_detail = {
            "counted": slice_.n_warnings,
            "cap_bound": slice_.n_warnings >= WARNINGS_CAP,
            "oldest": slice_.warnings_oldest_ts,
        }

    # PHASE 1 — build and validate the WHOLE slice.  A malformed signal halfway
    # through must not leave the store holding the first half of a slice it then
    # refused: an append-only store cannot roll that back afterwards.
    for raw in slice_.signals:
        kind = str(raw.get("type") or "")
        if kind in EXIT_SIDE_TYPES:
            exit_side[kind] = exit_side.get(kind, 0) + 1
            continue
        if kind == "BOTTOM_WATCH":
            subtype = str(raw.get("subtype") or "")
            family = WATCH_SUBTYPE_TO_FAMILY.get(subtype)
            if family is None:
                unknown_type[f"BOTTOM_WATCH/{subtype}"] = (
                    unknown_type.get(f"BOTTOM_WATCH/{subtype}", 0) + 1)
                continue
            if family not in wanted:
                filtered += 1
                continue
            event = build_watch_event(slice_, raw, lower_bound=lower)
        else:
            family = TYPE_TO_FAMILY.get(kind)
            if family is None:
                unknown_type[kind or "<no type>"] = unknown_type.get(kind or "<no type>", 0) + 1
                continue
            if family not in wanted:
                filtered += 1
                continue
            # A4.3: the oracle families' subtype IS the emitter's quality string.
            event = build_signal_event(slice_, raw, family=family,
                                       subtype=raw.get("quality"), lower_bound=lower,
                                       subtype_lifted_from_quality=True)
        built.append(event)
        key = f"{event.family}/{event.subtype}"
        by_family[key] = by_family.get(key, 0) + 1

    # PHASE 2 — commit.  Every event validated above; only address collisions can
    # still refuse here, and those are the genuine data-integrity signal.
    event_ids = [str(store.append(event).event_id) for event in built]

    return IngestReport(
        symbol=slice_.symbol,
        signal_era=slice_.signal_era,
        source_hash=slice_.source_hash,
        pre_fence=slice_.pre_fence,
        freshness=freshness,
        n_signals=len(slice_.signals),
        event_ids=tuple(event_ids),
        by_family=by_family,
        excluded_exit_side=exit_side,
        excluded_family_filter=filtered,
        excluded_unknown_type=unknown_type,
        excluded_warnings_detail=warnings_detail,
        unknowable_pre_cap=unknowable_pre_cap_dates(slice_),
    )
