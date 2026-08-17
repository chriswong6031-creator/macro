"""engine/entry_radar/live_ledger.py — the RUNTIME episode ledger (W4, §13).

WHAT THIS IS, AND WHAT IT IS EMPHATICALLY NOT
----------------------------------------------
Operational state for the live lane: which episodes are open, which transitions
and events have already been admitted, which names are inside a §10 re-arm
window.  It lives under an INJECTED ``state_dir`` (production:
``/var/lib/macro-live/state/entry_radar``).

It is **not** the durable evidence store.  ``data/entry_radar/**`` stays
unwritten — no ``data/`` path literal appears in this file — and W5's nightly
reconciler remains the only writer of durable evidence (§7.3 single-writer law).
Losing this file costs a re-derivation, never a fact.

APPEND-ONLY, AND FALSE STARTS ARE PRESERVED (§0, contract §13, P-10)
---------------------------------------------------------------------
Once a transition existed it is never erased.  A TERMINAL episode's record may
never change again — :meth:`LiveEpisodeLedger.commit` compares canonical forms
and raises rather than accept a rewrite — and compaction MOVES old terminal
episodes to a monthly archive, it never deletes them.  "A candidate that left
today's board still exists in the ledger forever" is the §13 sentence this class
implements.

SPOOL BEFORE CONSUME, MADE STRUCTURAL (§0, design §2 step 8)
--------------------------------------------------------------
:meth:`LiveEpisodeLedger.commit` REQUIRES the spool receipt as an argument.  It
cannot be called by a caller who has not spooled, and the only way past it is the
explicit ``unspooled_ok=True`` test hook — a keyword nobody types by accident.
A spool failure therefore withholds the transitions from the ledger AND from the
payload, and the next pass re-derives and retries (idempotent addresses make the
retry safe).

THE CLOCK OVERLAY READS NO PRICE (§0 W4/W5 firewall, PIT-W4-20)
----------------------------------------------------------------
:func:`apply_session_clocks` runs BOTH of §10's episode-ending clocks:

  * CANDIDATE → RESOLVED at H = 10 sessions, stamped at the resolving session's
    CLOSE instant;
  * ARMED/TURNING (no candidate) → EXPIRED at ``C3_ARM_EXPIRY_SESSIONS`` = 15
    sessions, stamped at the EXPIRING session's OPEN instant — ``run_c3``'s own
    convention (W3-2), because the open is the first instant at which the clock
    had run out.

Both are counted on ``engine.session_anchor.reference_sessions`` — the same
absolute calendar every Radar bucket rides — and stamped from
``engine.session_digest.session_window_et``.  It is CALENDAR ARITHMETIC ONLY: no
forward return, no MFE/MAE, no price of any kind enters that path.  RESOLVED and
EXPIRED are lifecycle bookkeeping needed for the §10 re-arm rule; grading is
W5's and does not exist here.

INVALIDATED HAS NO PRODUCER IN W4 — DELIBERATELY
--------------------------------------------------
``INVALIDATED`` stays a legal §13 state and nothing in this module can mint it.
The frozen contract defines no intraday invalidation rule, so inventing one
(a stop, a level, a "structure broke") would be a firing-semantic change
requiring the §18 A5.0 correction protocol and a CEO ruling — not a W4 mechanism
choice.  The absence is the honest state, and it is stated here rather than left
for a reader to notice.

NO SCORES ON THE DURABLE RECORD (§18 A5.0, §9)
----------------------------------------------
``detector_score``, ``research_priority`` and ``opportunity_score`` are §13
fields and they are ``None`` on the ledger, always — a non-None value is REFUSED
at construction.  W6 publishes Research Priority on the live *payload* only
(ephemeral; a corrected frame recomputes current Priority and does not rewrite
this store).  Opportunity Score remains W7.  A placeholder number in an
append-only store is a number somebody later cites.
"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from engine import session_anchor
from engine.entry_radar import challengers as ch
from engine.entry_radar import detectors as dt
from engine.entry_radar.contracts import iso
from engine.entry_radar.entry_events import EntryEventError, canonical_json, sha16
from engine.entry_radar.four_hour import C3_ARM_EXPIRY_SESSIONS
from engine.entry_radar.readings import BANNED_FEATURE_TOKENS
from engine.entry_radar.spool import NominationSpool, spool_key
from engine.session_digest import session_window_et

SCHEMA_LIVE_EPISODE = "mastermind.live_entry_episode.v1"
SCHEMA_LIVE_LEDGER = "entry_radar.live_ledger/v1"
SCHEMA_ENTRY_RADAR_EVENTS = "entry_radar.events/v1"

#: The W1 spool mechanism's SECOND prefix.  Not a second queue: same class, same
#: backends, same one-object-per-pass key shape (``spool.py`` module docstring).
EVENT_SPOOL_PREFIX = "live_flow/entry_radar_events"

#: The pack lane's pass id.  Rides the spool key so a pack-pass object and an RTH
#: pass object written in the same second cannot overwrite each other.
PACK_PASS_ID = "entry_radar_pack"

#: §10, frozen: "CANDIDATE resolves at H", primary H = 10 trading sessions.
RESOLVE_HORIZON_SESSIONS = 10

# §10's OTHER episode-ending clock — ARMED/TURNING without a candidate expires
# at 15 sessions — is IMPORTED above as ``C3_ARM_EXPIRY_SESSIONS``, never
# re-minted here.  The number is firing-relevant and rides ``C3_SPEC`` BY VALUE
# (W3-4), so a second literal in this file would be a constant that can drift
# away from the hash that publishes it.  See :func:`apply_session_clocks`.

#: Terminal episodes older than this many sessions move to a monthly archive.
#: NEVER deleted — false-start preservation (P-10) is the whole point of the
#: archive existing instead of a prune.
COMPACTION_SESSIONS = 40

#: §13 VERBATIM, in the contract's own order.  ``tests`` pins this tuple against
#: the amendment text, so a field cannot be quietly added to or dropped from the
#: episode contract.
EPISODE_CONTRACT_FIELDS: tuple[str, ...] = (
    "episode_id", "ticker", "detector_id", "detector_version", "detector_spec_hash",
    "state", "first_armed_at", "candidate_at", "last_observed_at", "market_session",
    "bar_availability", "feature_snapshot", "universe_admission", "lobe_nominations",
    "price_at_signal", "risk_geometry", "detector_score", "research_priority",
    "opportunity_score", "data_quality", "freshness", "evidence_refs",
)

#: The stored record = ``schema`` + §13 + ``variant``.  THE ONE EXTENSION, stated
#: rather than smuggled: W3 shipped C2's episode unit as (ticker, detector,
#: VARIANT) (JC2, §18 A5.3 — six mechanistically distinct experts are never
#: deduped into one generic "C2 fired"), so the unit key must appear in the record
#: that carries it.  An episode whose own identity tuple is not in its record
#: cannot be addressed, and the alternative — hiding the variant inside
#: ``feature_snapshot`` — would make the identity look like a feature.
EPISODE_FIELDS: tuple[str, ...] = ("schema",) + EPISODE_CONTRACT_FIELDS + ("variant",)

#: §13 fields that are ``None`` in W4 and refused otherwise (W6/W7 territory).
NULL_ONLY_FIELDS: tuple[str, ...] = (
    "detector_score", "research_priority", "opportunity_score")

#: Sub-dicts whose KEYS are swept for strength-number tokens.  Scoped, for the
#: same reason ``contracts.assert_no_score_fields`` exempts the nomination
#: subtree: §13's OWN field names include ``research_priority`` and
#: ``opportunity_score``, so a blanket sweep over the record would refuse the
#: contract itself.  The frozen field list governs the top level; the token sweep
#: governs the free-form blocks, which are where a score would actually appear.
_SWEPT_BLOCKS: tuple[str, ...] = ("feature_snapshot", "risk_geometry",
                                  "bar_availability", "freshness")

_LEDGER_FILE = "episodes.json"
_ARCHIVE_PREFIX = "episodes_archive_"


class LedgerError(EntryEventError):
    """A malformed ledger record or an illegal ledger operation."""


class TerminalEpisodeMutation(LedgerError):
    """An attempt to change a TERMINAL episode's record.  Append-only law."""


class SpoolReceiptRequired(LedgerError):
    """``commit`` was called without the spool receipt.  Spool-before-consume."""


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------

def compute_episode_id(*, ticker: str, detector_id: str, variant: str | None,
                       first_armed_at: str | None) -> str:
    """Stable sha16 over ``(ticker | detector_id | variant | first_armed_at)``.

    ``first_armed_at`` is IN the address on purpose: a lawful §10 re-arm after a
    terminal episode is a NEW episode, and an address that omitted the arm clock
    would silently re-open the old one — the exact history rewrite
    ``ALLOWED_TRANSITIONS`` refuses at the state-machine level.
    """
    return sha16([str(ticker), str(detector_id), variant, first_armed_at])


def episode_key(ticker: str, detector_id: str, variant: str | None) -> tuple[str, str, str]:
    """The §10 / JC2 episode UNIT — variant included for C2, empty otherwise."""
    return (str(ticker), str(detector_id), str(variant or ""))


def transition_address(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str]:
    """The dedup address of one transition.  Deterministic from its content."""
    return (str(row.get("ticker") or ""), str(row.get("detector_id") or ""),
            str(row.get("variant") or ""), str(row.get("from_state") or ""),
            str(row.get("to_state") or ""), str(row.get("at") or ""))


def _suppression_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    """The identity of ONE suppression fact — the unit, its session, its instant.

    ``reason``/``detail`` are deliberately outside it: they describe WHY the same
    would-be arm was refused, and a re-derivation that reaches the same refusal
    by the same rule is the same fact, not a second one.
    """
    return (str(row.get("ticker") or ""), str(row.get("detector_id") or ""),
            str(row.get("variant") or ""), str(row.get("session") or ""),
            str(row.get("would_have_armed_at") or ""))


# ---------------------------------------------------------------------------
# the episode record
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class LiveEpisode:
    """One `mastermind.live_entry_episode.v1` record (§13), plus ``variant``."""

    episode_id: str
    ticker: str
    detector_id: str
    detector_version: int
    detector_spec_hash: str
    state: str
    market_session: str
    variant: str | None = None
    first_armed_at: str | None = None
    candidate_at: str | None = None
    last_observed_at: str | None = None
    bar_availability: dict[str, Any] = field(default_factory=dict)
    feature_snapshot: dict[str, Any] = field(default_factory=dict)
    universe_admission: dict[str, Any] = field(default_factory=dict)
    lobe_nominations: tuple[dict[str, Any], ...] = ()
    price_at_signal: float | None = None
    risk_geometry: dict[str, Any] = field(default_factory=dict)
    detector_score: None = None
    research_priority: None = None
    opportunity_score: None = None
    data_quality: str = "ok"
    freshness: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    schema: str = SCHEMA_LIVE_EPISODE

    def __post_init__(self) -> None:
        for name in ("bar_availability", "feature_snapshot", "universe_admission",
                     "risk_geometry", "freshness"):
            object.__setattr__(self, name, copy.deepcopy(dict(getattr(self, name))))
        object.__setattr__(self, "lobe_nominations",
                           tuple(copy.deepcopy(dict(n)) for n in self.lobe_nominations))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        self._validate()

    def _validate(self) -> None:
        if self.schema != SCHEMA_LIVE_EPISODE:
            raise LedgerError(f"schema {self.schema!r} is not {SCHEMA_LIVE_EPISODE!r}")
        for name in ("episode_id", "ticker", "detector_id", "detector_spec_hash",
                     "state", "market_session"):
            if not str(getattr(self, name) or "").strip():
                raise LedgerError(f"{name} is required on every episode record")
        if int(self.detector_version) < 1:
            raise LedgerError(f"{self.detector_id}: detector_version must be >= 1")
        try:
            dt.DetectorState(self.state)
        except ValueError as exc:
            raise LedgerError(
                f"state {self.state!r} is not a §13 lifecycle state "
                f"({sorted(s.value for s in dt.DetectorState)})") from exc
        ch.assert_can_fire(self.detector_id)
        for name in NULL_ONLY_FIELDS:
            if getattr(self, name) is not None:
                raise LedgerError(
                    f"{self.detector_id} episode for {self.ticker} carries "
                    f"{name}={getattr(self, name)!r}; W6/W7 territory — the durable "
                    f"ledger records lifecycle, provenance and availability. W6 "
                    f"Research Priority is ephemeral on the live payload; W7 is "
                    f"not this store (contract §18 A5.0, §9, §13)")
        for block in _SWEPT_BLOCKS:
            bad = sorted(k for k in getattr(self, block)
                         if any(tok in str(k).lower() for tok in BANNED_FEATURE_TOKENS))
            if bad:
                raise LedgerError(
                    f"{block} key(s) {bad} read as a strength/priority number; W4 "
                    f"outputs mechanisms, state, provenance and availability only "
                    f"(contract §18 A5.0)")

    @property
    def terminal(self) -> bool:
        return dt.DetectorState(self.state) in dt.TERMINAL_STATES

    @property
    def key(self) -> tuple[str, str, str]:
        return episode_key(self.ticker, self.detector_id, self.variant)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form.  Key order and key set are exactly ``EPISODE_FIELDS``."""
        out: dict[str, Any] = {}
        for name in EPISODE_FIELDS:
            value = getattr(self, name)
            if isinstance(value, dict):
                value = copy.deepcopy(value)
            elif isinstance(value, tuple):
                value = [copy.deepcopy(v) for v in value]
            out[name] = value
        return out

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> LiveEpisode:
        unknown = set(raw) - set(EPISODE_FIELDS)
        if unknown:
            raise LedgerError(f"unknown episode field(s) {sorted(unknown)} — the "
                              f"record shape is frozen at {list(EPISODE_FIELDS)}")
        kwargs = {k: raw[k] for k in EPISODE_FIELDS if k in raw}
        for seq in ("evidence_refs", "lobe_nominations"):
            if kwargs.get(seq) is not None:
                kwargs[seq] = tuple(kwargs[seq])
        return cls(**kwargs)  # type: ignore[arg-type]

    @property
    def canonical(self) -> str:
        """Deterministic JSON — the byte form the append-only guard compares."""
        return canonical_json(self.to_dict())

    def replace(self, **changes: Any) -> LiveEpisode:
        current = self.to_dict()
        current.update(changes)
        return LiveEpisode.from_dict(current)


# ---------------------------------------------------------------------------
# the pending delta
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PendingDelta:
    """What one pass WOULD admit — computed, spooled, and only then committed."""

    ticker: str
    as_of_session: str
    pass_id: str
    events: tuple[dict[str, Any], ...] = ()
    transitions: tuple[dict[str, Any], ...] = ()
    episodes: tuple[dict[str, Any], ...] = ()
    #: Episode ids whose incoming trace was IGNORED because the stored record is
    #: already terminal.  Reported, never silent — see
    #: :meth:`LiveEpisodeLedger.apply_run`.
    superseded: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not (self.events or self.transitions or self.episodes)

    def to_dict(self) -> dict[str, Any]:
        return {"ticker": self.ticker, "as_of_session": self.as_of_session,
                "pass_id": self.pass_id,
                "events": [copy.deepcopy(e) for e in self.events],
                "transitions": [copy.deepcopy(t) for t in self.transitions],
                "episodes": [copy.deepcopy(e) for e in self.episodes],
                "superseded": list(self.superseded)}


def merge_deltas(deltas: Sequence[PendingDelta], *, as_of_session: str,
                 pass_id: str, ticker: str = "*") -> PendingDelta:
    """One pass-wide delta from many per-name ones, deduped by address.

    The spool writes ONE object per pass (the W1 key shape), so the pass needs
    one delta; merging here rather than at the call site keeps the dedup rule in
    exactly one place.
    """
    events: dict[str, dict[str, Any]] = {}
    transitions: dict[tuple[str, ...], dict[str, Any]] = {}
    episodes: dict[str, dict[str, Any]] = {}
    superseded: set[str] = set()
    for delta in deltas:
        for event in delta.events:
            events.setdefault(str(event.get("event_id")), event)
        for row in delta.transitions:
            transitions.setdefault(transition_address(row), row)
        for episode in delta.episodes:
            episodes[str(episode.get("episode_id"))] = episode
        superseded |= set(delta.superseded)
    return PendingDelta(
        ticker=ticker, as_of_session=as_of_session, pass_id=pass_id,
        events=tuple(events[k] for k in sorted(events)),
        transitions=tuple(transitions[k] for k in sorted(transitions)),
        episodes=tuple(episodes[k] for k in sorted(episodes)),
        superseded=tuple(sorted(superseded)))


# ---------------------------------------------------------------------------
# the ledger
# ---------------------------------------------------------------------------

class LiveEpisodeLedger:
    """Runtime episode state for the live lane.  Atomic writes, append-only law.

    NO WALL CLOCK.  Every session and instant is passed in; the ledger records the
    last session it was advanced to and nothing about when the process ran.
    """

    def __init__(self, state_dir: Path | str | None = None) -> None:
        self.state_dir = Path(state_dir) if state_dir is not None else None
        self._episodes: dict[str, LiveEpisode] = {}
        self._events: dict[str, dict[str, Any]] = {}
        self._transitions: list[dict[str, Any]] = []
        self._transition_addrs: set[tuple[str, ...]] = set()
        self._rearm: dict[str, dict[str, Any]] = {}
        self._suppressions: list[dict[str, Any]] = []
        self.last_session: str | None = None

    # -- reads -------------------------------------------------------------
    @property
    def episodes(self) -> tuple[LiveEpisode, ...]:
        return tuple(self._episodes[k] for k in sorted(self._episodes))

    @property
    def transitions(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(t) for t in self._transitions)

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(self._events[k]) for k in sorted(self._events))

    @property
    def suppressions(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(s) for s in self._suppressions)

    @property
    def rearm(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._rearm)

    def get(self, episode_id: str) -> LiveEpisode | None:
        return self._episodes.get(episode_id)

    def live_episode(self, ticker: str, detector_id: str,
                     variant: str | None = None) -> LiveEpisode | None:
        """The NONTERMINAL episode for a unit, or None.  §10: at most one."""
        key = episode_key(ticker, detector_id, variant)
        for episode in self.episodes:
            if episode.key == key and not episode.terminal:
                return episode
        return None

    def episodes_for(self, ticker: str, detector_id: str) -> tuple[LiveEpisode, ...]:
        """Every episode of a (ticker, detector), across ALL C2 variants."""
        return tuple(e for e in self.episodes
                     if e.ticker == ticker and e.detector_id == detector_id)

    def unit_episodes(self, ticker: str, detector_id: str,
                      variant: str | None = None) -> tuple[LiveEpisode, ...]:
        """Every episode of ONE §10/JC2 unit — variant included for C2.

        Distinct from :meth:`episodes_for` on purpose.  The re-arm MEASUREMENT is
        per (ticker, detector) — §10's rule is stated about the name's confirmed
        K, not about which of C2's six experts fired — but the QUESTION "has this
        unit had an episode at all?" is per unit, or a terminated ``c2a`` would
        gate the first-ever ``c2b`` arm on a window ``c2b`` was never in.
        """
        key = episode_key(ticker, detector_id, variant)
        return tuple(e for e in self.episodes if e.key == key)

    # -- the diff ----------------------------------------------------------
    def apply_run(self, *, ticker: str, as_of_session: str, runs: Sequence[Any],
                  pass_id: str, context: Mapping[str, Any] | None = None,
                  ) -> PendingDelta:
        """Diff W3 run outputs against the ledger.  PURE — nothing is applied.

        ``runs`` are :class:`challengers.C1Run` / :class:`challengers.C2Run` /
        :class:`four_hour.C3Run` objects (duck-typed on ``episodes``/``events``).
        Everything is addressed deterministically — events by ``event_id``,
        transitions by ``(ticker, detector_id, variant, from, to, at)``, episodes
        by ``episode_id`` — so re-running the SAME inputs yields an EMPTY delta.
        That idempotency is the whole restart-safety story: a mid-session restart
        re-derives from the journal and admits nothing twice.

        A TERMINAL episode is never updated from a run trace, and that is not a
        raise.  ``run_c1``/``run_c2``/``run_c3`` are stateless replays of a path:
        an episode the CLOCK OVERLAY resolved at H is still re-produced as
        CANDIDATE by every later replay over the same journal, and raising there
        would wedge the name on every pass for a fact the ledger already knows.
        The trace is IGNORED and its ``episode_id`` is reported in
        ``PendingDelta.superseded`` — visible, never silent.  The enforcing door
        stays :meth:`commit`, where an explicit delta carrying a changed terminal
        record still raises: a diff is advisory, an admission is not.
        """
        ctx = dict(context or {})
        new_events: dict[str, dict[str, Any]] = {}
        new_transitions: list[dict[str, Any]] = []
        seen_addrs: set[tuple[str, ...]] = set()
        new_episodes: dict[str, dict[str, Any]] = {}
        superseded: list[str] = []

        for run in runs or ():
            events_by_id = {}
            for event in getattr(run, "events", ()) or ():
                row = event.to_dict()
                events_by_id[str(row.get("event_id"))] = row
                if str(row.get("event_id")) not in self._events:
                    new_events.setdefault(str(row.get("event_id")), row)

            for episode in getattr(run, "episodes", ()) or ():
                record = self._episode_record(
                    episode, ticker=ticker, as_of_session=as_of_session,
                    events_by_id=events_by_id, context=ctx,
                    run_session=getattr(run, "armed_session", None))
                stored = self._episodes.get(record.episode_id)
                if stored is not None and stored.terminal:
                    if stored.canonical != record.canonical:
                        superseded.append(record.episode_id)
                elif stored is None or stored.canonical != record.canonical:
                    new_episodes[record.episode_id] = record.to_dict()

                for transition in getattr(episode, "transitions", ()) or ():
                    row = self._transition_row(transition, variant=episode.variant,
                                               pass_id=pass_id)
                    address = transition_address(row)
                    if address in self._transition_addrs or address in seen_addrs:
                        continue
                    seen_addrs.add(address)
                    new_transitions.append(row)

        return PendingDelta(
            ticker=ticker, as_of_session=as_of_session, pass_id=pass_id,
            events=tuple(new_events[k] for k in sorted(new_events)),
            transitions=tuple(new_transitions),
            episodes=tuple(new_episodes[k] for k in sorted(new_episodes)),
            superseded=tuple(sorted(set(superseded))))

    def _transition_row(self, transition: Any, *, variant: str | None,
                        pass_id: str) -> dict[str, Any]:
        row = transition.to_dict()
        row["variant"] = variant
        row["pass_id"] = pass_id
        return row

    def _episode_record(self, episode: Any, *, ticker: str, as_of_session: str,
                        events_by_id: Mapping[str, Mapping[str, Any]],
                        context: Mapping[str, Any],
                        run_session: str | None) -> LiveEpisode:
        """Build the §13 record for one in-memory W3 episode trace.

        ``market_session`` resolution order, most authoritative first:

          1. the episode's first minted event's own ``context.market_session``
             (the emitter's stamp — C1/C2/C3 candidates always have one);
          2. the run's arm session (``C3Run.armed_session``, for an episode that
             armed without minting an event);
          3. the date prefix of ``candidate_at``/``first_armed_at`` — C5's clock
             IS a session (``signal_known_ts``), and U.S. RTH lies wholly inside
             one UTC date, so the prefix cannot cross a session boundary;
          4. the pass session.

        Never derived by mapping an arbitrary instant onto a calendar: that
        guesses at the boundary, and the emitter's own stamp cannot.
        """
        variant = getattr(episode, "variant", None)
        first_armed_at = getattr(episode, "first_armed_at", None)
        detector_id = str(episode.detector_id)
        spec = dt.get_spec(detector_id)

        market_session = None
        for event_id in getattr(episode, "event_ids", ()) or ():
            row = events_by_id.get(str(event_id))
            if row:
                market_session = (row.get("context") or {}).get("market_session")
                break
        if not market_session:
            market_session = run_session
        if not market_session:
            stamp = getattr(episode, "candidate_at", None) or first_armed_at
            market_session = str(stamp)[:10] if stamp else None
        market_session = str(market_session or as_of_session)

        state = episode.state.value if hasattr(episode.state, "value") \
            else str(episode.state)
        return LiveEpisode(
            episode_id=compute_episode_id(ticker=ticker, detector_id=detector_id,
                                          variant=variant,
                                          first_armed_at=first_armed_at),
            ticker=ticker, detector_id=detector_id, detector_version=spec.version,
            detector_spec_hash=spec.spec_hash, state=state, variant=variant,
            first_armed_at=first_armed_at,
            candidate_at=getattr(episode, "candidate_at", None),
            last_observed_at=getattr(episode, "last_observed_at", None),
            market_session=market_session,
            bar_availability=dict(context.get("bar_availability") or {}),
            feature_snapshot=dict(context.get("feature_snapshot") or {}),
            universe_admission=dict(context.get("universe_admission") or {}),
            lobe_nominations=tuple(context.get("lobe_nominations") or ()),
            price_at_signal=context.get("price_at_signal"),
            risk_geometry=dict(context.get("risk_geometry") or {}),
            data_quality=str(context.get("data_quality") or "ok"),
            freshness=dict(context.get("freshness") or {}),
            evidence_refs=tuple(str(e) for e in
                                (getattr(episode, "event_ids", ()) or ())))

    # -- the commit door ---------------------------------------------------
    def commit(self, delta: PendingDelta, *, spool_receipt: str | None,
               unspooled_ok: bool = False) -> PendingDelta:
        """Admit a delta.  The SPOOL RECEIPT IS A REQUIRED ARGUMENT (§0).

        ``unspooled_ok=True`` is the only bypass and exists for tests that
        exercise the ledger without a spool sink.  Making the receipt positional-
        by-keyword rather than optional is the point: a caller cannot forget to
        spool, they can only decide out loud not to.
        """
        if not str(spool_receipt or "").strip() and not unspooled_ok:
            raise SpoolReceiptRequired(
                f"commit of {len(delta.transitions)} transition(s) / "
                f"{len(delta.events)} event(s) for {delta.ticker} refused: no spool "
                f"receipt.  Spool-before-consume (§0) — a transition that is not "
                f"durable before it is admitted is a false start nobody can "
                f"reconstruct; the ephemeral producers behind it have no vintage to "
                f"replay (contract §5, ephemeral-producers row)")
        receipt = str(spool_receipt or "") or None

        for row in delta.episodes:
            record = LiveEpisode.from_dict(row)
            stored = self._episodes.get(record.episode_id)
            if stored is not None and stored.terminal \
                    and stored.canonical != record.canonical:
                raise TerminalEpisodeMutation(
                    f"episode {record.episode_id} is {stored.state}; a terminal "
                    f"episode's record may never change again")
            became_terminal = record.terminal and (stored is None or not stored.terminal)
            self._episodes[record.episode_id] = record
            if became_terminal:
                # The §10 re-arm clock starts the moment the episode ENDS, and it
                # RESTARTS if a later episode of the same (ticker, detector) ends
                # again — the window is measured from the most recent ending, not
                # from the first one ever.  Opening the block here also keeps
                # "just terminated, nothing measured yet" (a window that is
                # legitimately open) distinguishable from "terminated before this
                # ledger existed" (unmeasurable history, which fails closed).
                self._open_rearm_block(record.ticker, record.detector_id,
                                       session=str(delta.as_of_session or ""),
                                       reset=True)

        for row in delta.events:
            event_id = str(row.get("event_id") or "")
            if not event_id:
                raise LedgerError("an event with no event_id cannot be addressed")
            admitted = copy.deepcopy(row)
            admitted["spool_key"] = receipt
            stored_event = self._events.get(event_id)
            if stored_event is None:
                self._events[event_id] = admitted
                continue
            # Same address, different content — the ``EntryEventStore`` law, held
            # here too: an append-only store never overwrites, and the answer to
            # a real distinction the address cannot express is to WIDEN the
            # address, never to absorb one record into the other.  ``spool_key``
            # is excluded: it records WHICH pass made the event durable, not what
            # the event says.
            if canonical_json({k: v for k, v in stored_event.items()
                               if k != "spool_key"}) != \
                    canonical_json({k: v for k, v in admitted.items()
                                    if k != "spool_key"}):
                raise LedgerError(
                    f"event_id {event_id} is already recorded with DIFFERENT content; "
                    f"an append-only ledger never overwrites (contract §13, "
                    f"entry_events.AppendOnlyViolation)")

        for row in delta.transitions:
            address = transition_address(row)
            if address in self._transition_addrs:
                continue
            admitted = copy.deepcopy(row)
            admitted["spool_key"] = receipt
            self._transitions.append(admitted)
            self._transition_addrs.add(address)

        if delta.as_of_session:
            if self.last_session is None or str(delta.as_of_session) > self.last_session:
                self.last_session = str(delta.as_of_session)
        return delta

    # -- §10 re-arm --------------------------------------------------------
    def _rearm_key(self, ticker: str, detector_id: str) -> str:
        return f"{ticker}|{detector_id}"

    def _open_rearm_block(self, ticker: str, detector_id: str, *, session: str,
                          reset: bool = False) -> dict[str, Any]:
        """Start (or restart) a name's confirmed-K ledger at an episode's ending."""
        key = self._rearm_key(ticker, detector_id)
        if reset or key not in self._rearm:
            self._rearm[key] = {"ticker": ticker, "detector_id": detector_id,
                                "ended_session": session, "last_session": session,
                                "confirmed_k": [], "sessions_elapsed": 0}
        return self._rearm[key]

    def arm_allowed(self, ticker: str, detector_id: str, *, variant: str | None = None,
                    session: str | None = None,
                    would_have_armed_at: str | None = None) -> tuple[bool, str]:
        """May this (ticker, detector) arm right now, and WHY (§10 hygiene)?

        Records a ``suppressed_by_rearm`` note whenever the answer is False AND
        the caller supplied the instant it would have armed at — §11's control-pool
        flag.  A would-be arm inside an ineligible window is never silently
        dropped: the control pool needs the names the rule suppressed, not just
        the ones it let through.
        """
        live = self.live_episode(ticker, detector_id, variant)
        if live is not None:
            return self._refuse(ticker, detector_id, variant, session,
                                would_have_armed_at, "live_episode_open",
                                f"a nonterminal {live.state} episode already exists "
                                f"(§10: one live episode per unit)")
        if not self.unit_episodes(ticker, detector_id, variant):
            return True, "no_prior_episode"
        block = self._rearm.get(self._rearm_key(ticker, detector_id))
        if block is None:
            # Terminal history with no re-arm block: the episode ended before the
            # overlay ran.  Fail CLOSED — an unmeasured recovery is not a recovery.
            return self._refuse(ticker, detector_id, variant, session,
                                would_have_armed_at, "rearm_unmeasured",
                                "the prior episode terminated with no confirmed-K "
                                "ledger; §10 eligibility cannot be evidenced")
        if ch.rearm_eligible(block.get("confirmed_k") or [],
                             int(block.get("sessions_elapsed") or 0)):
            return True, "rearm_eligible"
        return self._refuse(
            ticker, detector_id, variant, session, would_have_armed_at,
            "rearm_window_open",
            f"§10 re-arm not yet earned: confirmed K > {ch.REARM_K_FLOOR} on "
            f"{ch.REARM_K_SESSIONS} consecutive sessions, or "
            f"{ch.REARM_MAX_SESSIONS} sessions elapsed "
            f"(elapsed {block.get('sessions_elapsed')})")

    def _refuse(self, ticker: str, detector_id: str, variant: str | None,
                session: str | None, would_have_armed_at: str | None,
                reason: str, detail: str) -> tuple[bool, str]:
        """Record the §11 note ONCE per suppressed unit-instant, then refuse.

        IDEMPOTENT on ``(ticker, detector_id, variant, session,
        would_have_armed_at)``.  ``arm_allowed`` is consulted on every pass of a
        stateless replay, so an un-deduped append wrote one identical row per
        pass: at ~78 passes a session one suppressed name ended the day with 78
        copies in ``episodes.json``, the row count grew quadratically in
        sessions x suppressed names, ``compact()`` never touched them and
        ``_ledger_hash`` covers only ``episodes`` — so the growth was invisible to
        the content signal, and any §11 control-pool count built from the field
        was inflated by exactly the pass number.  One would-be arm is ONE
        suppression fact; recording it twice does not make it truer.
        """
        if would_have_armed_at:
            row = {"ticker": ticker, "detector_id": detector_id, "variant": variant,
                   "session": session, "would_have_armed_at": would_have_armed_at,
                   "reason": reason, "detail": detail}
            if _suppression_key(row) not in {_suppression_key(s)
                                             for s in self._suppressions}:
                self._suppressions.append(row)
        return False, reason

    def advance_rearm(self, *, as_of_session: str, confirmed_k_by_name: Mapping[str, Any],
                      ) -> dict[str, dict[str, Any]]:
        """Append this session's confirmed K to every terminated unit's ledger.

        Keyed per (ticker, detector) — NOT per C2 variant — because §10 states the
        rule about the NAME's confirmed K, not about which expert fired.  The
        block is reset by :meth:`commit` each time an episode of that name ends,
        so the measurement always runs from the most recent ending.

        Idempotent by ``last_session``: replaying the same session appends
        nothing, so a re-run of the pack lane cannot inflate a consecutive run
        into eligibility that never happened.
        """
        touched: dict[str, dict[str, Any]] = {}
        units: set[tuple[str, str]] = set()
        for episode in self.episodes:
            if episode.terminal:
                units.add((episode.ticker, episode.detector_id))
        for ticker, detector_id in sorted(units):
            key = self._rearm_key(ticker, detector_id)
            if key not in self._rearm:
                # Backstop only: a ledger written before the block existed, or an
                # episode that terminated outside ``commit``.  ``commit`` is the
                # normal opener (see ``_open_rearm_block``).
                touched[key] = dict(self._open_rearm_block(
                    ticker, detector_id, session=str(as_of_session)))
                continue
            block = self._rearm[key]
            if str(as_of_session) <= str(block.get("last_session") or ""):
                continue
            value = confirmed_k_by_name.get(ticker)
            block["confirmed_k"] = list(block.get("confirmed_k") or []) + [
                None if value is None else float(value)]
            block["sessions_elapsed"] = int(block.get("sessions_elapsed") or 0) + 1
            block["last_session"] = str(as_of_session)
            touched[key] = dict(block)
        return touched

    # -- compaction (never deletion) ---------------------------------------
    def compact(self, *, as_of_session: str, max_sessions: int = COMPACTION_SESSIONS,
                market: str = "US") -> dict[str, Any]:
        """Move old TERMINAL episodes to a monthly archive.  Nothing is deleted.

        The cut is measured on the reference calendar from each episode's own
        ``market_session``, so the retention is in SESSIONS (what the lifecycle is
        counted in) rather than in days.
        """
        moved: dict[str, list[dict[str, Any]]] = {}
        for episode in self.episodes:
            if not episode.terminal:
                continue
            elapsed = sessions_elapsed(episode.market_session, as_of_session,
                                       market=market)
            if elapsed is None or elapsed <= int(max_sessions):
                continue
            month = str(episode.market_session)[:7].replace("-", "")
            moved.setdefault(month, []).append(episode.to_dict())
            self._episodes.pop(episode.episode_id, None)

        written: dict[str, int] = {}
        for month, rows in sorted(moved.items()):
            written[month] = len(rows)
            if self.state_dir is None:
                continue
            path = self.state_dir / f"{_ARCHIVE_PREFIX}{month}.json"
            existing: list[dict[str, Any]] = []
            try:
                existing = json.loads(path.read_text(encoding="utf-8")).get("episodes") or []
            except (OSError, ValueError):
                existing = []
            by_id = {str(r.get("episode_id")): r for r in existing}
            for row in rows:
                by_id[str(row.get("episode_id"))] = row
            _atomic_write_json(path, {"schema": SCHEMA_LIVE_LEDGER,
                                      "archive_month": month,
                                      "episodes": [by_id[k] for k in sorted(by_id)]})
        return {"archived": written, "remaining": len(self._episodes)}

    def archived_episodes(self) -> tuple[dict[str, Any], ...]:
        """Every archived record on disk, newest month last.  Read-only."""
        if self.state_dir is None or not self.state_dir.is_dir():
            return ()
        out: list[dict[str, Any]] = []
        for path in sorted(self.state_dir.glob(f"{_ARCHIVE_PREFIX}*.json")):
            try:
                out.extend(json.loads(path.read_text(encoding="utf-8")).get("episodes") or [])
            except (OSError, ValueError):
                continue
        return tuple(out)

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_LIVE_LEDGER,
            "last_session": self.last_session,
            "episodes": [e.to_dict() for e in self.episodes],
            "events": [copy.deepcopy(self._events[k]) for k in sorted(self._events)],
            "transitions": [copy.deepcopy(t) for t in self._transitions],
            "rearm": copy.deepcopy(self._rearm),
            "suppressions": [copy.deepcopy(s) for s in self._suppressions],
        }

    def save(self) -> Path | None:
        """Atomic-rename write of ``episodes.json``.  None when no state dir."""
        if self.state_dir is None:
            return None
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / _LEDGER_FILE
        _atomic_write_json(path, self.to_dict())
        return path

    @classmethod
    def load(cls, state_dir: Path | str | None) -> LiveEpisodeLedger:
        """Read ``episodes.json``, or an empty ledger when there is none."""
        ledger = cls(state_dir)
        if state_dir is None:
            return ledger
        path = Path(state_dir) / _LEDGER_FILE
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ledger
        ledger.last_session = raw.get("last_session")
        for row in raw.get("episodes") or ():
            record = LiveEpisode.from_dict(row)
            ledger._episodes[record.episode_id] = record
        for row in raw.get("events") or ():
            ledger._events[str(row.get("event_id"))] = dict(row)
        for row in raw.get("transitions") or ():
            ledger._transitions.append(dict(row))
            ledger._transition_addrs.add(transition_address(row))
        ledger._rearm = dict(raw.get("rearm") or {})
        ledger._suppressions = [dict(s) for s in raw.get("suppressions") or ()]
        return ledger


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """mkstemp + ``os.replace`` — a reader never sees a half-written ledger."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(body)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# the session clock overlay — CALENDAR ARITHMETIC ONLY
# ---------------------------------------------------------------------------

def _as_session(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def sessions_elapsed(earlier: Any, later: Any, *, market: str = "US") -> int | None:
    """Reference sessions strictly after ``earlier`` up to and including ``later``.

    Counted on ``engine.session_anchor.reference_sessions`` — the SAME absolute
    calendar W3's buckets and freshness ride — so "ten sessions later" is a
    calendar fact, not a property of whichever rows a store happened to hold.
    Returns None when either end is off the calendar's edge.
    """
    reference = session_anchor.reference_sessions(market)
    a = int(reference.searchsorted(pd.Timestamp(_as_session(earlier)).normalize(),
                                   side="left"))
    b = int(reference.searchsorted(pd.Timestamp(_as_session(later)).normalize(),
                                   side="left"))
    if a >= len(reference) or b >= len(reference):
        return None
    return b - a


def session_at_offset(session: Any, offset: int, *, market: str = "US") -> date | None:
    """The reference session ``offset`` places after ``session``, or None."""
    reference = session_anchor.reference_sessions(market)
    position = int(reference.searchsorted(pd.Timestamp(_as_session(session)).normalize(),
                                          side="left"))
    target = position + int(offset)
    if target < 0 or target >= len(reference):
        return None
    return reference[target].date()


def session_close_instant(session: Any) -> str:
    """The session's CLOSE instant as a UTC ISO stamp (early closes included)."""
    _open_dt, close_dt = session_window_et(_as_session(session))
    return iso(close_dt.astimezone(timezone.utc)) or ""


def session_open_instant(session: Any) -> str:
    """The session's OPEN instant as a UTC ISO stamp — ``run_c3``'s arm/expiry stamp.

    The expiry half of :func:`apply_session_clocks` stamps here rather than at the
    close because W3-2 stamps there: "at THIS session's open, because that is the
    first instant at which the clock had run out" (``four_hour.run_c3``).  Two
    enforcement points for one frozen rule must agree on the instant, or the same
    episode expires at two different times depending on which lane saw it first.
    """
    open_dt, _close_dt = session_window_et(_as_session(session))
    return iso(open_dt.astimezone(timezone.utc)) or ""


def apply_session_clocks(ledger: LiveEpisodeLedger, *, as_of_session: str,
                         confirmed_k_by_name: Mapping[str, Any] | None = None,
                         market: str = "US", pass_id: str = PACK_PASS_ID,
                         ) -> PendingDelta:
    """Session-boundary lifecycle work, run in the PACK builder (design §2).

    Three jobs, in this order:

    (i)   **CANDIDATE → RESOLVED at H = 10 sessions** (§10).  Counted on the
          reference calendar from the episode's own ``market_session`` and
          stamped at the RESOLVING session's close instant — the first instant at
          which the clock had run out.  NO PRICE IS READ ON THIS PATH.
          ``sessions``, ``session_window_et`` and the episode's own stamps are the
          only inputs, which is what keeps RESOLVED a lifecycle fact rather than
          a grade (W4/W5 firewall, PIT-W4-20).

    (ii)  **ARMED/TURNING → EXPIRED at 15 sessions** (§10, W4R-M8).  An episode
          that armed and never promoted to CANDIDATE expires once
          ``C3_ARM_EXPIRY_SESSIONS`` reference sessions have elapsed since its
          own arm session, stamped at the EXPIRING session's OPEN instant.  Same
          calendar, same no-price law as (i).

    (iii) **§10 re-arm bookkeeping** for units whose episode has ALREADY
          terminated: this session's confirmed K (from the pack) is appended to
          the unit's ledger and the elapsed counter advances, so
          :meth:`LiveEpisodeLedger.arm_allowed` can answer from evidence rather
          than from a guess.  Applied immediately — it is derived state with no
          downstream event, idempotent by session, and it only ever reads episodes
          that were terminal before this pass began.

    Both the RESOLVED and the EXPIRED transitions ride the returned
    :class:`PendingDelta` through the SAME spool-then-commit path as every other
    transition, and :meth:`LiveEpisodeLedger.commit`'s terminal hook opens the
    unit's §10 re-arm window for either one.  ``INVALIDATED`` gets no producer
    here (see the module docstring).
    """
    confirmed_k = dict(confirmed_k_by_name or {})
    transitions: list[dict[str, Any]] = []
    episodes: dict[str, dict[str, Any]] = {}
    candidate_state = dt.DetectorState.CANDIDATE

    # (i) CANDIDATE resolves at H.
    for episode in ledger.episodes:
        if episode.state != candidate_state.value or not episode.candidate_at:
            continue
        elapsed = sessions_elapsed(episode.market_session, as_of_session, market=market)
        if elapsed is None or elapsed < RESOLVE_HORIZON_SESSIONS:
            continue
        resolving = session_at_offset(episode.market_session, RESOLVE_HORIZON_SESSIONS,
                                      market=market)
        if resolving is None:
            continue
        at = session_close_instant(resolving)
        dt.validate_transition(candidate_state, dt.DetectorState.RESOLVED)
        transitions.append({
            "ticker": episode.ticker, "detector_id": episode.detector_id,
            "variant": episode.variant,
            "from_state": candidate_state.value,
            "to_state": dt.DetectorState.RESOLVED.value,
            "at": at,
            "reason": (f"§10 lifecycle — CANDIDATE resolves at H="
                       f"{RESOLVE_HORIZON_SESSIONS} sessions (calendar arithmetic; no "
                       f"outcome is attached, grading is W5's)"),
            "evidence_refs": list(episode.evidence_refs),
            "pass_id": pass_id,
        })
        episodes[episode.episode_id] = episode.replace(
            state=dt.DetectorState.RESOLVED.value,
            last_observed_at=at).to_dict()

    # (ii) ARMED/TURNING with no candidate EXPIRES at C3_ARM_EXPIRY_SESSIONS.
    #
    # WHY THE OVERLAY IS A SECOND LAWFUL ENFORCEMENT POINT (W4R-M8).  §10's
    # expiry is frozen contract law and ``run_c3`` already enforces it — but
    # ``run_c3`` is a STATELESS REPLAY that counts the clock by POSITION within
    # the sessions it walks, and an episode's identity is
    # ``compute_episode_id(ticker, detector, variant, first_armed_at)``.  So the
    # replay's clock only ever reaches episodes its OWN walk mints: a ledger
    # episode armed outside the (clamped, M8) walk window is never matched by any
    # replay, stays ARMED forever, and blocks its unit's re-arm through
    # ``live_episode_open`` indefinitely.  Enforcing the same frozen rule here
    # closes that gap with CALENDAR ARITHMETIC ONLY — no price, no bar, no
    # detector semantics change; the arm rule, the turn rule and the 15 itself
    # are untouched, and the 15 is IMPORTED from the spec that publishes it
    # rather than re-typed.
    expirable = {dt.DetectorState.ARMED.value, dt.DetectorState.TURNING.value}
    for episode in ledger.episodes:
        if episode.state not in expirable or episode.candidate_at:
            continue
        if not episode.first_armed_at:
            # Fail CLOSED, and deliberately: an ARMED record with no recorded arm
            # instant has no clock to run, and inventing an anchor (the pass
            # session, ``market_session``) would expire episodes on a date the
            # arm never happened.  Unreachable through ``_episode_record`` —
            # ``first_armed_at`` is in the episode ADDRESS — so this is a guard,
            # not a branch the pack lane takes.
            continue
        armed_session = _as_session(episode.first_armed_at)
        elapsed = sessions_elapsed(armed_session, as_of_session, market=market)
        if elapsed is None or elapsed < C3_ARM_EXPIRY_SESSIONS:
            continue
        expiring = session_at_offset(armed_session, C3_ARM_EXPIRY_SESSIONS,
                                     market=market)
        if expiring is None:
            continue
        # ``run_c3``'s convention, held exactly: stamped at THIS session's OPEN,
        # because that is the first instant at which the clock had run out.
        at = session_open_instant(expiring)
        from_state = dt.DetectorState(episode.state)
        dt.validate_transition(from_state, dt.DetectorState.EXPIRED)
        transitions.append({
            "ticker": episode.ticker, "detector_id": episode.detector_id,
            "variant": episode.variant,
            "from_state": from_state.value,
            "to_state": dt.DetectorState.EXPIRED.value,
            "at": at,
            "reason": (f"§10 episode hygiene — {from_state.value} with no candidate "
                       f"for {C3_ARM_EXPIRY_SESSIONS} sessions (calendar arithmetic; "
                       f"the replay's own clock cannot reach an episode armed "
                       f"outside its window)"),
            "evidence_refs": list(episode.evidence_refs),
            "pass_id": pass_id,
        })
        episodes[episode.episode_id] = episode.replace(
            state=dt.DetectorState.EXPIRED.value,
            last_observed_at=at).to_dict()

    ledger.advance_rearm(as_of_session=as_of_session, confirmed_k_by_name=confirmed_k)
    return PendingDelta(
        ticker="*", as_of_session=str(as_of_session), pass_id=pass_id,
        events=(), transitions=tuple(transitions),
        episodes=tuple(episodes[k] for k in sorted(episodes)))


# ---------------------------------------------------------------------------
# the event spool — the W1 mechanism, second prefix, NOT a second queue
# ---------------------------------------------------------------------------

class EventSpool(NominationSpool):
    """:class:`spool.NominationSpool` at the EVENTS prefix.

    Same class, same backends (R2 first, ``$ENTRY_RADAR_SPOOL_DIR`` fallback),
    same ``ENTRY_RADAR_NO_PUBLISH`` refusal, same one-object-per-pass key shape —
    only the prefix and the payload differ.  Subclassing rather than adding a
    second queue is the design's own instruction (§2 step 8): a second queue is a
    second thing to lose events in.
    """

    def __init__(self, *, s3: Any = None, local_dir: Path | None = None,
                 prefix: str = EVENT_SPOOL_PREFIX) -> None:
        super().__init__(s3=s3, local_dir=local_dir, prefix=prefix)

    def append_pass(self, payload: Mapping[str, Any], *, session: str, stamp: str,
                    pass_id: str) -> str | None:
        """Spool ONE pass object.  Returns the key written, or None on failure."""
        key = spool_key(session, stamp, prefix=self.prefix, pass_id=pass_id)
        return key if self._put(key, dict(payload)) else None


def build_event_payload(delta: PendingDelta, *, pass_ts: str, pack_as_of: str,
                        pack_hash: str, health: Mapping[str, Any] | None = None,
                        ) -> dict[str, Any]:
    """The `entry_radar.events/v1` spool payload for one pass.

    Carries the PACK IDENTITY alongside the transitions: a spooled transition
    whose pack cannot be named later is a transition nobody can re-derive, and
    ``pack_hash`` is what pins the substrate it was computed on.
    """
    return {
        "schema": SCHEMA_ENTRY_RADAR_EVENTS,
        "pass_ts": pass_ts,
        "pass_id": delta.pass_id,
        "pack": {"as_of": pack_as_of, "pack_hash": pack_hash},
        "transitions": [copy.deepcopy(t) for t in delta.transitions],
        "events": [copy.deepcopy(e) for e in delta.events],
        "health": dict(health or {}),
    }


def spool_then_commit(ledger: LiveEpisodeLedger, delta: PendingDelta, *,
                      spool: EventSpool | None, pass_ts: str, session: str,
                      stamp: str, pack_as_of: str, pack_hash: str,
                      health: Mapping[str, Any] | None = None,
                      unspooled_ok: bool = False) -> tuple[str | None, bool]:
    """Spool the pass, then commit it — in that order, or not at all.

    Returns ``(spool_key, committed)``.  A delta with nothing in it spools
    nothing and commits nothing (the W1 one-object-per-pass-WITH-events rule) and
    is reported as committed, because there was nothing to withhold.
    """
    if delta.empty:
        return None, True
    receipt: str | None = None
    if spool is not None:
        receipt = spool.append_pass(
            build_event_payload(delta, pass_ts=pass_ts, pack_as_of=pack_as_of,
                                pack_hash=pack_hash, health=health),
            session=session, stamp=stamp, pass_id=delta.pass_id)
        if receipt is None:
            return None, False
    elif not unspooled_ok:
        raise SpoolReceiptRequired(
            "spool_then_commit was given no spool and no explicit unspooled_ok — "
            "a pass that cannot spool must withhold its transitions, not admit them")
    ledger.commit(delta, spool_receipt=receipt, unspooled_ok=unspooled_ok)
    return receipt, True


def iter_episode_dicts(episodes: Iterable[LiveEpisode]) -> list[dict[str, Any]]:
    """Serialise a run of episodes.  A helper, so callers do not re-implement it."""
    return [e.to_dict() for e in episodes]
