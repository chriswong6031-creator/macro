"""engine/entry_radar/live_eval.py — the 5-minute RTH pass (W4 design §2).

WHAT THIS MODULE IS
-------------------
One bounded, PURE evaluation cycle: session window → pack gate → quote intake →
price-basis audit → journal append → observation construction → the UNMODIFIED
W3 evaluators → ledger diff → spool-before-commit → payload + health receipt.

Everything volatile is INJECTED — ``now``, the quote book, the pack, the state
directory, the ledger, the spool sink and the C3 minute reader.  The module
opens no socket, reads no clock and names no vendor.  That is what makes the
whole cycle replayable from a fixture and what keeps the PIT battery honest: a
mutation test can only prove "nothing after T influenced the reading at T" if T
is a value the test chooses rather than a value the module reads.

THE EVALUATOR IS STRUCTURALLY UNABLE TO READ TOMORROW
-----------------------------------------------------
There is no store access here at all.  The confirmed daily substrate arrives
frozen in the nightly pack (``live_pack.LivePack.substrate``), today's tape is
built ONLY from journaled quote points, and prior sessions' observations are
replayed from the journal VERBATIM rather than recomputed against a newer pack.
An eventual EOD bar, a corrected close, a next-session row — none of them are on
any read path this module owns.  ``data/`` is never opened, let alone written.

THE ONE DERIVED CONSTRUCTION, AND ITS PIN (W4 design §1)
---------------------------------------------------------
:func:`challengers.build_observation_path` recomputes the whole oscillator chain
per sampled point, which is exact but O(points²) per session across the probe
set.  :class:`IncrementalObservationBuilder` computes the per-session preamble
ONCE and takes each already-JOURNALED interval verbatim, so a pass costs one
chain evaluation per interval that closed since the previous pass — normally
exactly one — instead of one per interval since the open.

THE JOURNAL IS THE MEMO, and it has to be: the lane is a systemd ONESHOT, one
process per pass, so an in-memory memo on a builder constructed per name per
pass is empty on arrival and the cost is O(intervals-since-open) every time
(measured by the two-pass call-count regression below).  Today's derived
observations are therefore appended to the session journal beside the quote
points — append-only, frozen at write, pinned to the same ``pack_hash`` — and a
pass computes the chain ONLY for intervals with no journaled observation.  That
is lawful rather than merely cheap: an interval is emitted only once its END has
passed, and the journal refuses a point that would land inside an already-
sampled interval, so a journaled observation can never be contradicted by a
later tick.  Recomputing it would be re-deriving a published reading.

It is byte-identical BY CONSTRUCTION, not by inspection: the preamble is the
same expression list, the chain is the same two ``indicator_core`` calls on the
same appended series, and the availability/basis/freshness decisions are the
same branch.  ``tests/test_entry_radar_w4_live.py`` pins that claim against
``build_observation_path`` over the fixture corpus (PIT-W4-16) — including gaps,
stale history, basis mismatch and early closes — because a construction that is
merely believed identical is a second implementation waiting to drift.

THE BASIS AUDIT RUNS BEFORE THE ENGINE (W3-1 carried forward)
---------------------------------------------------------------
The pack's ``as_of_close`` is an ADJUSTED store close; the feed's ``prevClose``
is a RAW prior-session close.  When they disagree past tolerance the two halves
of the concatenated series describe different scales, and the seam between them
FABRICATES a move — which fabricates a cross, which mints a candidate.  So the
audit happens before any observation exists for that name: a mismatched name
gets no tape, no observation, no reading with a verdict, and a receipt carrying
both closes and the gap.  Nothing is ever re-based into compliance.  A name the
feed gave no ``prevClose`` for is UNVERIFIED, not verified: it still evaluates
(absence is not disagreement — §5's row is about a gap past tolerance) and the
health block counts it separately so a feed that stops publishing ``prevClose``
cannot look like a healthy zero-mismatch pass.

FAIL CLOSED, AND SAY WHICH DOOR CLOSED
---------------------------------------
Four whole-cycle refusals — ``killed``, ``out_of_window``, ``stale_pack``,
``proof_failed`` — publish a payload in which every probe name is
``unavailable``, ZERO transitions exist and NOTHING is spooled.  Per-name
refusals — ``basis_mismatch``, ``pack_integrity``, ``no_quote``,
``stale_quote``, ``no_substrate`` — dark exactly one name while the rest of the
pass proceeds.  Every one of them is a named reason on the row and a counter in
the health block, because "no events this pass" has to be distinguishable from
"nothing could be evaluated this pass".

NULL LAW.  ``unavailable`` and ``stale`` are never ``False``.  A refused name
carries ``condition_met=None`` and no episode; it never carries a measured
non-fire.  See ``challengers.NULL_AVAILABILITY``.

W4/W5 FIREWALL.  Nothing here inspects a forward return, computes MFE/MAE,
grades a detector or compares two of them.  RESOLVED-at-H is calendar
bookkeeping and lives in the pack builder's clock overlay, not on this path.
:data:`FORBIDDEN_KEY_TOKENS` (minus :data:`FIREWALL_EXEMPT_KEYS`) below is the
mechanical statement of that boundary — a blacklist of forward-knowledge SHAPES
rather than a whitelist of key names, for the reason given at its own docstring —
and ``tests/test_entry_radar_w4_liveness.py`` enforces it over every emitted key.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass, field, fields, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from engine.entry_radar import challengers as ch
from engine.entry_radar import four_hour as fh
from engine.entry_radar import indicator_core as ic
from engine.entry_radar import live_ledger as ll
from engine.entry_radar import live_pack as lp
from engine.entry_radar import research_priority as rp
from engine.entry_radar.c5_adapter import C5_DETECTOR_ID
from engine.entry_radar.g0_adapter import G0_DETECTOR_ID
from engine.entry_radar.entry_events import EntryEventError, canonical_json
from engine.entry_radar.readings import canonical_readings
from engine.session_digest import session_window_et

#: The pass identity carried on every transition, spool object and payload.
PASS_ID = "entry_radar_live"

SCHEMA_LIVE_PAYLOAD = "entry_radar.live/v1"
SCHEMA_JOURNAL = "entry_radar.journal/v1"

#: Kill switches.  The env var is the operator's stand-down without a unit edit;
#: the file is the stand-down for a host with no way to change the environment.
KILL_ENV = "ENTRY_RADAR_LIVE_DISABLED"
KILL_FILE = "KILL"

#: Minutes past the exchange close during which a pass still evaluates.  The
#: timer fires on a UTC grid and the last interval of the session ends AT the
#: close, so a pass landing seconds later must still be able to record it.
WINDOW_END_GRACE_MIN = 10.0

#: Added to the artifact's DECLARED feed delay to get a per-name quote-age
#: budget.  Only this half is about OUR cadence — the vendor's contractual delay
#: is already in the quote's own timestamp before this lane has done anything.
#: Tightening it toward the cadence produces an all-dark artifact that looks
#: exactly like a healthy lane (the prophet-live lesson, quoted deliberately).
QUOTE_SLACK_MIN = 10.0

#: Quote ``basis`` values that are a CARRY, not a print made today.  §3b: a
#: ``prev``/``day`` row republishes a prior close, so admitting one as today's
#: sampled price would append yesterday's number as today's provisional bar.
CARRIED_QUOTE_BASES: frozenset[str] = frozenset({"prev", "day"})

#: FALLBACK band around a solved threshold inside which the oracle and the pack
#: are allowed to disagree.  The band that actually applies is the SOLUTION's own
#: ``rel_tolerance`` (:func:`_boundary_band`), because that is the precision the
#: level was bisected to and it self-heals if the solver's precision moves; this
#: constant is only reached for a solution that carries none.
#:
#: It points at ``BISECTION_REL_TOLERANCE`` (1e-6) and NOT at ``PROOF_EPSILON_REL``
#: (1e-4, the proof battery's straddle offset — a different quantity entirely).
#: The old pointing made the band 100x the solver's precision: on a $100 name the
#: justified band is +/-$0.0001 and the implemented one was +/-$0.01, so a genuine
#: pack/oracle disagreement inside 1bp of the level reported ``boundary_band``
#: instead of ``disagree`` and no ``pack_integrity`` refusal fired.
CROSS_CHECK_EPSILON_REL = lp.BISECTION_REL_TOLERANCE

#: Sessions of 4H history the C3 reader fetches BEFORE an episode's arm session.
#: Derived, not guessed: ``four_hour.first_lawful_turn_index`` needs 87 buckets
#: before ``four_hour_turn`` is evaluable at all, and an RTH session yields two
#: 240-minute buckets, so 60 sessions is ~120 buckets — past the warm-up with
#: margin for holidays and empty buckets.  Pinned mechanically in
#: ``tests/test_entry_radar_w4_c3_reader.py`` so the indicator cannot outgrow it
#: silently.
C3_WARMUP_SESSIONS = 60

#: Names whose C3 lane may FETCH in one pass.  A cold name costs one request per
#: warm-up session (measured on the synthetic corpus: 61 requests for one name,
#: 122 for two), so an unbounded pass over a washed cohort cannot finish inside a
#: 5-minute cadence at any pacing — and the unit's ``TimeoutStartSec`` would
#: SIGTERM it mid-window, which loses the work rather than deferring it.
#:
#: The bound is not a haircut on the signal: a completed session is cached
#: permanently, so a deferred name is fully warm within a few passes and steady
#: state costs ONE request per name per pass (today's tail).  The budget is spent
#: on names with an OPEN C3 episode first — a live episode must never stall
#: behind a newly-washed one — and the deferral is COUNTED in the health receipt
#: rather than looking like a name with no 4H turn.
C3_MAX_NAMES_PER_PASS = 25

#: ``health.inputs.c3_reader`` counters the PASS keeps itself, and which a
#: reader's own counters must therefore never overwrite.  ``errors`` is the
#: load-bearing one: the reader counts only transport raises, the pass counts
#: every fault that cost it a session.
PASS_OWNED_C3_STATS: frozenset[str] = frozenset({"fetched_n", "errors",
                                                 "deferred_n", "incomplete_n"})

#: Health states.  ``proof_failed`` is carried separately from ``stale_pack``
#: even though both refuse the whole cycle: a pack whose inversion proof failed
#: is a DIFFERENT operational fault from a pack built for the wrong session, and
#: collapsing them would send an operator to the wrong lane.
HEALTH_STATES: tuple[str, ...] = ("live", "degraded", "stale_pack", "proof_failed",
                                  "out_of_window", "killed", "failed")

#: Whole-cycle refusals: every name unavailable, zero transitions, zero spool.
CYCLE_REFUSALS: frozenset[str] = frozenset({"killed", "out_of_window", "stale_pack",
                                            "proof_failed", "failed"})

#: Per-name refusal reasons.  Enumerated so the payload cannot invent one and so
#: the liveness battery can assert every branch is reachable.
#:
#: Not all of them dark the NAME.  ``journal_refused_point`` and
#: ``c3_incomplete_window`` refuse a POINT and a LANE respectively while the rest
#: of the name evaluates honestly, which is why ``health.dark`` counts these
#: reasons across every row rather than across dark rows only — a counter that
#: could never leave zero is worse than no counter.
NAME_REFUSALS: tuple[str, ...] = ("no_substrate", "no_quote", "stale_quote",
                                  "carried_quote", "premarket_quote",
                                  "basis_mismatch", "pack_integrity",
                                  "journal_refused", "journal_refused_point",
                                  "c3_incomplete_window", "challenger_error",
                                  "c3_error", "ledger_error", "evaluator_error")

#: A raised exception's per-name reason, MOST SPECIFIC FIRST, keyed by class NAME
#: rather than by class object.  Two reasons for the spelling: ``VendorMinutesError``
#: lives in ``vendor_minutes``, and this module must not import the concrete
#: reader (the evaluator takes an INJECTED one — that is the whole seam); and a
#: future reader's own error class is classified by whatever it subclasses
#: without this table having to know it exists.
#:
#: The classes are siblings, NOT subclasses of each other: ``LiveEvalError`` and
#: ``ChallengerError`` are both ``EntryEventError``, ``C3Error`` is a
#: ``ChallengerError``, ``VendorMinutesError`` is a ``C3Error`` and ``LedgerError``
#: is a third ``EntryEventError``.  Catching only ``LiveEvalError`` — which is what
#: this module used to do — let every one of the others kill the whole pass.
#:
#: ORDER IS SIGNIFICANT — ``error_reason`` walks it and takes the first class name
#: present in the exception's MRO, so the SPECIFIC entries come first.
#: ``JournalRefused`` before ``LiveEvalError`` is the load-bearing pair: mapping
#: every ``LiveEvalError`` to ``journal_refused`` was correct while the journal
#: pin was the only one, and became a lie the moment the off-diagonal
#: tape-session guard raised the same base class — a BUILDER bug would have been
#: reported on the row as a journal refusal, sending a reader to the state dir to
#: look for a file that is perfectly fine.
NAME_ERROR_REASONS: tuple[tuple[str, str], ...] = (
    ("JournalRefused", "journal_refused"),
    ("LiveEvalError", "evaluator_error"),
    ("VendorMinutesError", "c3_error"),
    ("C3Error", "c3_error"),
    ("ChallengerError", "challenger_error"),
    ("LedgerError", "ledger_error"),
)

#: Payload keys that carry NO forward knowledge, enumerated (W4/W5 firewall).
#: A key that would require knowing what happened AFTER an observation was
#: knowable belongs to W5 and must never appear here.  The liveness suite walks
#: every emitted key in the pack, journal, ledger, spool and payload against
#: :data:`FORBIDDEN_KEY_TOKENS` rather than against this list, because a
#: whitelist of key NAMES ages badly while a blacklist of forward-knowledge
#: SHAPES does not.
FORBIDDEN_KEY_TOKENS: tuple[str, ...] = (
    "forward", "mfe", "mae", "hit_rate", "hitrate", "grade", "graded", "outcome",
    "return_", "_return", "pnl", "win_rate", "winrate", "realized", "realised",
    "payoff", "edge_", "sharpe", "accuracy", "precision_at", "rank", "score",
    "probability", "prob_", "confidence", "validated",
)

#: Keys that are lawful despite LOOKING like forward knowledge, each with the
#: reason.  An exemption list is the honest way to run a token sweep: without it
#: the sweep is tuned until it passes, which is how a firewall stops catching
#: anything.  Every entry is a field whose VALUE is structurally constant — an
#: all-false authority declaration, or a §13 slot the ledger refuses to fill
#: (``live_ledger.NULL_ONLY_FIELDS``).
#:
#: Only SOME of these currently match a token in :data:`FORBIDDEN_KEY_TOKENS`
#: (``can_rank``→``rank``; ``scored_authority``/``detector_score``/
#: ``opportunity_score``→``score``).  The rest are INERT today and are kept on
#: purpose: they are the sibling fields of the load-bearing ones, so if a token
#: is ever widened to ``size``/``gate``/``escalate``/``priority`` they would be
#: flagged together — and an exemption added in that moment, under pressure to
#: make the sweep pass, would be an exemption nobody reviewed.  Listing them now
#: makes that widening visible instead.  ``test_entry_radar_w4_liveness.py`` pins
#: the split in BOTH directions: a new exemption matching nothing reds as dead
#: weight, and an inert one becoming load-bearing reds as a widened token.
FIREWALL_EXEMPT_KEYS: dict[str, str] = {
    "can_rank": "authority block — declared FALSE on every artifact (contract §2)",
    "can_size": "authority block — declared FALSE on every artifact (contract §2)",
    "can_gate": "authority block — declared FALSE on every artifact (contract §2)",
    "can_originate_signal": "authority block — declared FALSE (contract §2)",
    "can_escalate": "authority block — declared FALSE (contract §2)",
    "scored_authority": "the authority block's own name, all-false by construction",
    "detector_score": "§13 slot, pinned None — live_ledger.NULL_ONLY_FIELDS refuses "
                      "a value",
    "research_priority": "W6 RP1 payload object — attention ordinal, not an outcome score",
    "opportunity_score": "§13 slot, pinned None — W7 territory",
}

ET = None  # resolved lazily in _et() so the module imports without zoneinfo cost


class LiveEvalError(EntryEventError):
    """A refusal on the live pass.  Never raised for an INPUT being absent."""


class JournalRefused(LiveEvalError):
    """The SESSION JOURNAL refused this name — a cross-pack pin or a bad row.

    Split out of :class:`LiveEvalError` so the per-name reason can name the
    journal specifically.  Everything else this module raises is a defect in the
    caller or in this file, and calling that ``journal_refused`` sends an
    operator to the state dir to inspect a file that is not the problem.
    """


def error_reason(exc: BaseException) -> str:
    """The per-name reason for a raised ``exc``, from its own class chain.

    Walks the MRO so a subclass is classified by the nearest declared ancestor,
    and falls back to ``evaluator_error`` — the honest answer for a class this
    module has never heard of.  The class NAME is recorded beside the reason at
    every call site, because "something raised" and "a ``KeyError`` raised" are
    different amounts of information and only one of them is actionable.
    """
    names = {cls.__name__ for cls in type(exc).__mro__}
    for candidate, reason in NAME_ERROR_REASONS:
        if candidate in names:
            return reason
    return "evaluator_error"


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LiveEvalConfig:
    """Every tunable on the pass, in one injectable record.

    Defaults are the shipped ones; a caller overrides rather than patching a
    module global, so two passes in the same process cannot disagree about the
    gates they applied.
    """

    quote_slack_min: float = QUOTE_SLACK_MIN
    basis_tolerance_pct: float = lp.BASIS_TOLERANCE_PCT
    interval_minutes: int = ch.SAMPLE_INTERVAL_MINUTES
    window_end_grace_min: float = WINDOW_END_GRACE_MIN
    cross_check_epsilon_rel: float = CROSS_CHECK_EPSILON_REL
    c3_warmup_sessions: int = C3_WARMUP_SESSIONS
    c3_max_names_per_pass: int = C3_MAX_NAMES_PER_PASS
    c3_enabled: bool = True
    pass_id: str = PASS_ID


# ---------------------------------------------------------------------------
# session window — the shape of live_states.in_window, re-implemented
# ---------------------------------------------------------------------------

def _et():
    """``America/New_York``.  Imported lazily; the module is used off-VPS too."""
    global ET
    if ET is None:
        from zoneinfo import ZoneInfo  # noqa: PLC0415
        ET = ZoneInfo("America/New_York")
    return ET


def in_window(now: datetime, *, grace_min: float = WINDOW_END_GRACE_MIN,
              ) -> tuple[bool, str, date | None]:
    """``(inside, reason, session)`` for the pass instant.

    RE-IMPLEMENTED, not imported.  ``engine/prophet_live/live_states.in_window``
    answers the same question, and Radar deliberately imports nothing from that
    package (the W1 leaf-discipline precedent): a shared import would make a
    Prophet change a Radar change, and the two programs' windows are allowed to
    diverge.  What IS shared is the source of truth underneath — the NYSE
    calendar and ``session_digest.session_window_et`` — so "when is the market
    open" still has exactly one definition in the estate.

    The grace is on the CLOSE side only.  The session's last sampled interval
    ends AT the close, and a timer firing on a UTC grid lands seconds later; an
    ungraced window would drop the most informative interval of the day.  There
    is no open-side grace, because a pre-open pass has nothing lawful to read.
    """
    from lib.nyse_calendar import is_session  # noqa: PLC0415
    et = now.astimezone(_et())
    session = et.date()
    if not is_session(session):
        return False, "not_a_session", None
    open_dt, close_dt = session_window_et(session)
    if et < open_dt:
        return False, "pre_open", session
    if et > close_dt + timedelta(minutes=float(grace_min)):
        return False, "post_close", session
    return True, "in_window", session


def interval_bounds(session: date, now: datetime, *,
                    interval_minutes: int = ch.SAMPLE_INTERVAL_MINUTES,
                    ) -> tuple[datetime, datetime] | None:
    """The sampled interval ``now`` falls in, in ET, or None outside the session.

    The grid is SESSION-OPEN-ANCHORED, exactly as ``sample_session_path`` builds
    it — deriving it a second way from the wall clock is how two components end
    up disagreeing about which interval a print belongs to.
    """
    open_dt, close_dt = session_window_et(session)
    et = now.astimezone(_et())
    if et < open_dt:
        return None
    width = timedelta(minutes=int(interval_minutes))
    elapsed = et - open_dt
    index = int(elapsed // width)
    start = open_dt + index * width
    if start >= close_dt:
        return None
    return start, min(start + width, close_dt)


# ---------------------------------------------------------------------------
# quote intake
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class QuotePoint:
    """One name's reading of the shared quote snapshot, with WHY it is usable.

    ``state`` is the enumerated verdict, never a bare bool: "there is no row for
    this name", "the row carries yesterday's close", "the print is from the
    premarket" and "the print is older than the budget" are four different facts
    and a consumer that sees only ``usable=False`` cannot tell a coverage hole
    from a stale feed.
    """

    ticker: str
    state: str
    price: float | None = None
    ts: datetime | None = None
    basis: str | None = None
    source: str | None = None
    prev_close: float | None = None
    age_min: float | None = None
    max_age_min: float | None = None

    @property
    def usable(self) -> bool:
        return self.state == "ok" and self.price is not None and self.ts is not None

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "price": self.price,
                "ts": _iso(self.ts), "basis": self.basis, "source": self.source,
                "prev_close": self.prev_close, "age_min": self.age_min,
                "max_age_min": self.max_age_min}


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _quote_ts(row: Mapping[str, Any]) -> datetime | None:
    """The quote's own timestamp.  Milliseconds since epoch per §3b."""
    raw = row.get("ts")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    if not np.isfinite(value):
        return None
    # A bare seconds value would land in 1970; the artifact contract is ms.
    return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)


def _float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def read_quote(ticker: str, row: Mapping[str, Any] | None, *, now: datetime,
               session: date, max_age_min: float) -> QuotePoint:
    """One name's quote, gated by the four §2-step-4 rules, in order.

    The ORDER is the disclosure.  A carried ``prev`` row that is also 40 minutes
    old is reported as ``carried_quote``, because re-basing the age budget for a
    price that was never a live print would be measuring the wrong thing.
    """
    if not isinstance(row, Mapping) or not row:
        return QuotePoint(ticker=ticker, state="no_quote", max_age_min=max_age_min)
    basis = str(row.get("basis") or "").strip().lower() or None
    source = str(row.get("source") or "").strip() or None
    prev_close = _float(row.get("prevClose") if "prevClose" in row
                        else row.get("prev_close"))
    price = _float(row.get("price"))
    ts = _quote_ts(row)
    common = {"ticker": ticker, "basis": basis, "source": source,
              "prev_close": prev_close, "max_age_min": max_age_min}
    if basis in CARRIED_QUOTE_BASES:
        # §3b: a stale carry, never live.  Admitting it would append the PRIOR
        # session's close as today's provisional bar — a fabricated flat day.
        return QuotePoint(state="carried_quote", price=price, ts=ts, **common)
    if price is None or ts is None:
        return QuotePoint(state="no_quote", price=price, ts=ts, **common)
    open_dt, _close_dt = session_window_et(session)
    if ts.astimezone(_et()) < open_dt:
        # §7 excludes extended hours.  A premarket print is not a session print,
        # and the sampled path is anchored at the open.
        return QuotePoint(state="premarket_quote", price=price, ts=ts, **common)
    age = (now - ts).total_seconds() / 60.0
    if age > float(max_age_min):
        return QuotePoint(state="stale_quote", price=price, ts=ts, age_min=age, **common)
    return QuotePoint(state="ok", price=price, ts=ts, age_min=age, **common)


def quote_budget(meta: Mapping[str, Any] | None, *,
                 slack_min: float = QUOTE_SLACK_MIN) -> float:
    """``meta.delayed_min + slack``.  DERIVED, exactly as prophet-live derives it.

    The vendor's contractual delay is already inside every quote's timestamp
    before this lane has run, so a budget tighter than the declared delay cannot
    be met at any polling speed and darks the whole universe.
    """
    declared = 0.0
    if isinstance(meta, Mapping):
        for key in ("delayed_min", "delayMin", "feed_delay_min"):
            got = _float(meta.get(key))
            if got is not None:
                declared = max(declared, got)
    return float(declared) + float(slack_min)


# ---------------------------------------------------------------------------
# the journal — append-only, pinned to the pack that produced it
# ---------------------------------------------------------------------------

_OBS_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(ch.Observation))


def observation_to_dict(obs: ch.Observation) -> dict[str, Any]:
    """JSON-safe form.  Key set is exactly the dataclass's own field list."""
    return {name: getattr(obs, name) for name in _OBS_FIELDS}


def observation_from_dict(raw: Mapping[str, Any]) -> ch.Observation:
    """Rebuild an observation from a journal row, refusing an unknown field.

    An unknown key means the journal was written by a DIFFERENT version of the
    observation record, and silently dropping it would replay a prior session
    through a shape the detectors were never evaluated on.
    """
    unknown = set(raw) - set(_OBS_FIELDS)
    if unknown:
        raise JournalRefused(
            f"journal observation carries unknown field(s) {sorted(unknown)}; the "
            f"W4 record is {list(_OBS_FIELDS)} — a replayed session must be the "
            f"shape the detectors evaluated, not a superset of it")
    return ch.Observation(**{k: raw[k] for k in _OBS_FIELDS if k in raw})


@dataclass
class JournalRecord:
    """One (session, ticker) journal file.  Append-only within the session."""

    session: str
    ticker: str
    pack_as_of: str
    pack_hash: str
    price_basis: str
    points: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    refused: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA_JOURNAL, "session": self.session,
                "ticker": self.ticker, "pack_as_of": self.pack_as_of,
                "pack_hash": self.pack_hash, "price_basis": self.price_basis,
                "points": [dict(p) for p in self.points],
                "observations": [dict(o) for o in self.observations],
                "refused": [dict(r) for r in self.refused]}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> JournalRecord:
        return cls(session=str(raw.get("session") or ""),
                   ticker=str(raw.get("ticker") or ""),
                   pack_as_of=str(raw.get("pack_as_of") or ""),
                   pack_hash=str(raw.get("pack_hash") or ""),
                   price_basis=str(raw.get("price_basis") or ch.BASIS_ADJUSTED),
                   points=[dict(p) for p in raw.get("points") or ()],
                   observations=[dict(o) for o in raw.get("observations") or ()],
                   refused=[dict(r) for r in raw.get("refused") or ()])

    def last_ts(self) -> datetime | None:
        for row in reversed(self.points):
            parsed = _parse_iso(row.get("ts"))
            if parsed is not None:
                return parsed
        return None

    def tape(self, session: date) -> ch.SessionTape:
        """Today's tape, built ONLY from journaled points.

        Each point becomes a one-minute bar at its vendor timestamp FLOORED to
        the minute, with ``o=h=l=c=price``.  A snapshot is a point, not a bar:
        inventing a high and a low from one print would hand the rebound
        variants a range that never existed, and ``running_minute_low`` would
        stop being the diagnostic it is documented to be.
        """
        bars: list[ch.MinuteBar] = []
        for row in self.points:
            ts = _parse_iso(row.get("ts"))
            price = _float(row.get("price"))
            if ts is None or price is None:
                continue
            start = ts.astimezone(_et()).replace(second=0, microsecond=0)
            bars.append(ch.MinuteBar(start=start, open=price, high=price,
                                     low=price, close=price, volume=0.0))
        return ch.SessionTape(session=session, minutes=tuple(bars),
                              price_basis=self.price_basis,
                              vintage=f"journal:{self.pack_hash[:12]}" if self.pack_hash
                              else "journal")


def _parse_iso(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class SessionJournal:
    """Per-session per-name quote-point journal (W4 design §2 step 6, §4).

    THREE LAWS, all mechanical:

    * **Append-only within a session.**  A point whose vendor timestamp is not
      strictly after the last journaled one is REFUSED and counted.  Without
      that rule a backdated or duplicated vendor row would land INSIDE an
      already-sampled interval, and ``sample_session_path`` — which admits every
      minute knowable by the interval's end — would silently rewrite a reading
      that had already been published.  A future tick cannot do this (it is not
      knowable at an earlier interval's end), which is why PIT-W4-1 is provable
      by construction; a PAST tick can, which is why it is refused here.
    * **Pinned to the pack.**  Every file records the ``pack_hash`` that produced
      it.  Reading a session's journal under a DIFFERENT pack refuses rather
      than replaying yesterday's prices through today's substrate — that
      re-derivation is exactly the backfill §7.1 forbids.
    * **Prior sessions are replayed VERBATIM.**  The observations a multi-day
      episode needs are the ones that were computed on the session's OWN pack.
      Recomputing them against a pack with one more confirmed bar would move
      every K and D in the episode's history.

    ``state_dir is None`` (no state plane — a dev checkout, a CI runner) degrades
    to an in-memory journal.  The pass still evaluates today; it simply has no
    prior sessions to replay and nothing survives the process.
    """

    def __init__(self, state_dir: Path | str | None) -> None:
        self.state_dir = Path(state_dir) if state_dir is not None else None
        self._memory: dict[tuple[str, str], JournalRecord] = {}

    def root(self) -> Path | None:
        return None if self.state_dir is None else self.state_dir / "journal"

    def path(self, session: str, ticker: str) -> Path | None:
        root = self.root()
        return None if root is None else root / str(session) / f"{_safe(ticker)}.json"

    def read(self, session: str, ticker: str) -> JournalRecord | None:
        key = (str(session), str(ticker))
        if key in self._memory:
            return self._memory[key]
        path = self.path(session, ticker)
        if path is None or not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, Mapping):
            return None
        record = JournalRecord.from_dict(raw)
        self._memory[key] = record
        return record

    def open_session(self, *, session: str, ticker: str, pack_as_of: str,
                     pack_hash: str, price_basis: str) -> JournalRecord:
        """Today's record for this name, refusing a cross-pack re-derivation."""
        existing = self.read(session, ticker)
        if existing is None:
            record = JournalRecord(session=str(session), ticker=str(ticker),
                                   pack_as_of=str(pack_as_of),
                                   pack_hash=str(pack_hash),
                                   price_basis=str(price_basis))
            self._memory[(str(session), str(ticker))] = record
            return record
        if existing.pack_hash and pack_hash and existing.pack_hash != str(pack_hash):
            raise JournalRefused(
                f"{ticker} {session}: journal was written under pack "
                f"{existing.pack_hash[:12]} and this pass carries "
                f"{str(pack_hash)[:12]} — re-deriving a session against a different "
                f"substrate is the backfill §7.1 forbids; the pack builder owns the "
                f"session boundary, not this pass")
        return existing

    def append_point(self, record: JournalRecord, *, ts: datetime, price: float,
                     basis: str | None, source: str | None,
                     basis_audit: Mapping[str, Any] | None) -> bool:
        """Append one quote point.  False when the append-only law refused it."""
        last = record.last_ts()
        if last is not None and ts <= last:
            record.refused.append({
                "ts": _iso(ts), "last_ts": _iso(last),
                "reason": "not_after_last_point",
                "detail": "a vendor timestamp at or before the last journaled point "
                          "would land inside an already-sampled interval and rewrite "
                          "a published reading"})
            return False
        record.points.append({"ts": _iso(ts), "price": float(price), "basis": basis,
                              "source": source,
                              "basis_audit": dict(basis_audit or {})})
        return True

    def freeze_observations(self, record: JournalRecord,
                            observations: Sequence[ch.Observation]) -> int:
        """APPEND today's new observations.  Returns how many were added.

        Append-only, exactly like :meth:`append_point` and for the same reason:
        a journaled observation is the reading that WAS published for that
        interval, and an interval is only ever emitted once its end has passed,
        so a second pass that rewrote it would be re-deriving a published
        reading against a longer tape.  Rows are keyed by ``interval_start``;
        an interval already present is left exactly as it was written and a
        contradicting recomputation is recorded in ``refused`` rather than
        silently winning.
        """
        known = {str(row.get("interval_start")): row for row in record.observations}
        added = 0
        for obs in observations:
            key = str(obs.interval_start)
            row = observation_to_dict(obs)
            existing = known.get(key)
            if existing is None:
                record.observations.append(row)
                known[key] = row
                added += 1
            elif existing != row:
                record.refused.append({
                    "interval_start": key, "reason": "observation_already_journaled",
                    "detail": "an interval's observation is frozen at write; a pass "
                              "that recomputed it differently would rewrite a reading "
                              "that has already been published"})
        record.observations.sort(key=lambda row: str(row.get("interval_start") or ""))
        return added

    def observations_of(self, record: JournalRecord) -> tuple[ch.Observation, ...]:
        """This session's already-journaled observations, rebuilt verbatim."""
        return tuple(observation_from_dict(row) for row in record.observations)

    def replay(self, session: str, ticker: str, *,
               pack_hash: str | None = None) -> tuple[ch.Observation, ...]:
        """A PRIOR session's observations, verbatim.  Never recomputed.

        ``pack_hash`` is deliberately NOT compared here: a prior session was
        lawfully computed under a prior pack, and demanding today's hash would
        refuse every multi-day episode.  The pin that matters is the one in
        :meth:`open_session`, which stops TODAY being re-derived under a
        different substrate.
        """
        record = self.read(session, ticker)
        if record is None:
            return ()
        return tuple(observation_from_dict(row) for row in record.observations)

    def sessions(self, ticker: str) -> list[str]:
        """Journaled sessions for one name, oldest first."""
        root = self.root()
        found: set[str] = {key[0] for key in self._memory if key[1] == str(ticker)}
        if root is not None and root.is_dir():
            for child in root.iterdir():
                if child.is_dir() and (child / f"{_safe(ticker)}.json").is_file():
                    found.add(child.name)
        return sorted(found)

    def flush(self, record: JournalRecord) -> Path | None:
        """Persist one record atomically.  Never raises — the pass owns the tape."""
        path = self.path(record.session, record.ticker)
        if path is None:
            return None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(path, record.to_dict())
            return path
        except OSError:
            return None


def _safe(ticker: str) -> str:
    """A filesystem-safe name.  Tickers carry ``.``/``-``/``^`` in this estate."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(ticker).upper())


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    body = json.dumps(payload, allow_nan=False, separators=(",", ":"),
                      sort_keys=True).encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        tmp = ""
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# incremental observation construction (design §1) — the ONE derived path
# ---------------------------------------------------------------------------

class IncrementalObservationBuilder:
    """One name's session-local observation constructor.

    Mirrors :func:`challengers.build_observation_path`'s per-tape body EXACTLY,
    with the two halves separated by what they depend on:

    * the PREAMBLE (confirmed closes, their index, the prior-confirmed ATR, the
      basis agreement, the history freshness) depends only on the frozen daily
      frame and the session — computed once, in ``__init__``;
    * the CHAIN (``stoch_rsi_kd`` + ``rsi_macd_hist`` on the confirmed closes
      with one appended provisional close) depends only on the sampled close —
      memoised by that float.

    The memo is keyed by the sampled close rather than by the interval, which is
    what makes a carry-forward interval free: ``sample_session_path`` repeats the
    previous value across an interval with no prints, and the repeated value hits
    the same chain result.  It is also why a CHANGED journal point cannot serve a
    stale reading — a different price is a different key.

    THAT MEMO DIES WITH THE PROCESS, so it is not the one that matters.  The lane
    is a oneshot: one process per pass, one builder per name per pass, so
    ``_chain`` is empty on arrival every time and by itself buys only the
    carry-forward dedup WITHIN a pass.  The memo that survives is the session
    JOURNAL, handed to :meth:`observations` as ``journaled``: an interval already
    written there is taken verbatim and no chain runs for it at all.  Both are
    kept — the journal answers "has this interval ever been computed", the price
    memo answers "have I already computed this price in THIS pass".

    Byte-parity with the oracle is asserted, not assumed: see PIT-W4-16.
    """

    def __init__(self, *, ticker: str, daily: ch.DailyHistory, session: date,
                 interval_minutes: int = ch.SAMPLE_INTERVAL_MINUTES) -> None:
        self.ticker = str(ticker)
        self.session = session
        self.interval_minutes = int(interval_minutes)
        self.daily = daily
        confirmed = daily.confirmed_through(session)
        self._closes = confirmed["close"].astype(float)
        self._closes_np = self._closes.to_numpy(dtype=float)
        self._base_index = pd.DatetimeIndex(confirmed.index)
        self._session_ts = pd.Timestamp(session).normalize()
        atr_series = ic.atr14(confirmed["high"], confirmed["low"], confirmed["close"])
        self._atr_prior = ic.last_finite(atr_series)
        self._daily_basis = daily.price_basis
        self._atr_basis = (f"wilder_atr{ic.ATR_LEN}_true_range_prior_confirmed"
                           f"[{daily.price_basis}]" if self._atr_prior is not None
                           else None)
        self._last_confirmed = (self._base_index[-1].date()
                                if len(self._base_index) else None)
        self._freshness = ch.freshness_state(self._last_confirmed, session)
        self._chain: dict[float, tuple[float | None, float | None, float | None]] = {}

    @property
    def confirmed_bars(self) -> int:
        return int(len(self._closes))

    @property
    def history_freshness(self) -> str:
        return self._freshness

    def chain_at(self, price: float) -> tuple[float | None, float | None, float | None]:
        """``(K, D, hist)`` at the appended provisional close.  Memoised."""
        key = float(price)
        cached = self._chain.get(key)
        if cached is not None:
            return cached
        series = pd.Series(np.append(self._closes_np, key),
                           index=self._base_index.append(
                               pd.DatetimeIndex([self._session_ts])))
        k_series, d_series = ic.stoch_rsi_kd(series)
        hist_series = ic.rsi_macd_hist(series)
        out = (ic.last_finite(k_series), ic.last_finite(d_series),
               ic.last_finite(hist_series))
        self._chain[key] = out
        return out

    def observations(self, tape: ch.SessionTape, *,
                     now: datetime | None = None,
                     journaled: Sequence[ch.Observation] | None = None,
                     ) -> tuple[ch.Observation, ...]:
        """This session's observation path from ``tape``, as knowable at ``now``.

        The branch order is ``build_observation_path``'s, line for line: basis
        disagreement or a missing sampled close or an empty confirmed history
        yields ``unavailable``; a stale history yields the freshness state and no
        chain at all; otherwise the chain runs and ``unavailable`` still wins when
        %K did not warm up.

        ``journaled`` is the ALREADY-COMPUTED prefix (design §1, the O(1) claim).
        An interval present there is emitted verbatim and its chain is never
        re-evaluated: it closed on an earlier pass, the journal refuses any point
        that could land inside it, so the only thing a recomputation could do is
        disagree.  ``journaled=None`` — every test of the parity pin, and every
        replay — computes the whole path, which is what keeps PIT-W4-16 a real
        comparison rather than a comparison of a cache with itself.

        THE TAPE'S SESSION MUST BE THE BUILDER'S.  ``confirmed_through`` and every
        emitted ``market_session`` come from ``self.session`` while the sampled
        grid comes from ``tape.session``; handing in a tape from another session
        silently produces a different %K against a different confirmed history
        (measured: 15.25 vs the oracle's 65.46, no error).  The oracle keys both
        halves off ``tape.session``, so the only lawful call is the diagonal.

        ``now`` TRUNCATES THE GRID, and it is the difference between a replay and
        a live pass.  ``sample_session_path`` builds every interval of the
        session and CARRIES the last known value across intervals with no prints
        — correct for a completed session, and a leak mid-session: a 10:02 pass
        would otherwise emit an observation stamped 15:55 with today's 10:00
        price, and C1 could arm at an instant that has not happened.  An interval
        is knowable at its END, so only points with ``observed_at <= now``
        survive.  ``now=None`` treats the session as fully elapsed — the SAME
        contract, spelling and default as ``four_hour.four_hour_buckets``, so the
        two grids cannot drift apart on what "confirmed" means, and the replay
        case stays byte-identical to ``build_observation_path``.
        """
        if tape.session != self.session:
            raise LiveEvalError(
                f"{self.ticker}: tape session {tape.session} is not the builder's "
                f"{self.session} — the confirmed history is cut at the BUILDER's "
                f"session and every reading is stamped with it, so an off-diagonal "
                f"call returns a different %K against a different history with no "
                f"error; build one constructor per session")
        basis_agrees = self._daily_basis == tape.price_basis
        vintage = tape.vintage or self.daily.vintage or None
        known = {str(o.interval_start): o for o in (journaled or ())}
        out: list[ch.Observation] = []
        for point in ch.sample_session_path(tape,
                                            interval_minutes=self.interval_minutes):
            if now is not None and point.observed_at > now:
                break
            already = known.get(ch.utc_iso(point.interval_start))
            if already is not None:
                out.append(already)
                continue
            if not basis_agrees or point.sampled_close is None or len(self._closes) == 0:
                out.append(self._record(
                    point, availability="unavailable", vintage=vintage,
                    tape_basis=tape.price_basis, basis_agrees=basis_agrees,
                    sampled=(point.sampled_close if basis_agrees else None),
                    k=None, d=None, hist=None))
                continue
            if self._freshness != "confirmed":
                out.append(self._record(
                    point, availability=self._freshness, vintage=vintage,
                    tape_basis=tape.price_basis, basis_agrees=basis_agrees,
                    sampled=point.sampled_close, k=None, d=None, hist=None))
                continue
            k_val, d_val, hist_val = self.chain_at(point.sampled_close)
            out.append(self._record(
                point,
                availability="unavailable" if k_val is None else "provisional",
                vintage=vintage, tape_basis=tape.price_basis,
                basis_agrees=basis_agrees, sampled=point.sampled_close,
                k=k_val, d=d_val, hist=hist_val))
        return tuple(out)

    def _record(self, point: ch.SampledPoint, *, availability: str,
                vintage: str | None, tape_basis: str, basis_agrees: bool,
                sampled: float | None, k: float | None, d: float | None,
                hist: float | None) -> ch.Observation:
        return ch.Observation(
            ticker=self.ticker, observed_at=ch.utc_iso(point.observed_at),
            market_session=self.session.isoformat(),
            interval_start=ch.utc_iso(point.interval_start),
            availability=availability, bar_state="provisional",
            sampled_close=sampled,
            running_sampled_low=(point.running_sampled_low if sampled is not None
                                 else None),
            running_minute_low=point.running_minute_low,
            k=k, d=d, hist=hist,
            source_bar_time=(self._session_ts.date().isoformat()
                             if sampled is not None else None),
            source_bar_known_at=None,
            data_vintage=vintage, price_basis=tape_basis,
            daily_price_basis=self._daily_basis,
            atr_prior_confirmed=self._atr_prior if basis_agrees else None,
            atr_basis=self._atr_basis if basis_agrees else None,
            confirmed_bars=int(len(self._closes)),
            history_freshness=self._freshness)


def pack_daily_history(pack: lp.LivePack, ticker: str) -> ch.DailyHistory | None:
    """The frozen substrate as a :class:`challengers.DailyHistory`, or None.

    ``vintage`` names the PACK, not the store: the live lane's provenance for a
    confirmed bar is "the pack of ``as_of``", and pointing at the store would
    claim a read this module never performs.
    """
    frame = pack.substrate.get(str(ticker))
    if frame is None or not len(frame):
        return None
    return ch.DailyHistory(frame=frame, price_basis=pack.price_basis,
                           vintage=f"live_pack:{pack.as_of}")


# ---------------------------------------------------------------------------
# threshold cross-check (PIT-W4-15) — fail closed, never fall back
# ---------------------------------------------------------------------------

def _boundary_band(solution: lp.ThresholdSolution, price: float, *,
                   epsilon_rel: float) -> bool:
    """True when ``price`` sits inside the solver's own precision at the level.

    THE BAND IS THE SOLUTION'S, not a module constant.  ``ThresholdSolution``
    carries the ``rel_tolerance`` its own bisection reached, so reading it here
    keeps the band exactly as wide as the imprecision it exists to forgive and
    self-heals if the solver's precision ever moves.  ``epsilon_rel`` is the
    fallback for a solution that carries none.
    """
    if solution.price is None:
        return False
    tolerance = getattr(solution, "rel_tolerance", None)
    if tolerance is None or not np.isfinite(float(tolerance)):
        tolerance = epsilon_rel
    scale = max(abs(float(solution.price)), 1e-12)
    return abs(float(price) - float(solution.price)) <= float(tolerance) * scale


def substrate_fingerprint(daily: ch.DailyHistory, session: date) -> str | None:
    """The ADJUSTMENT BASIS of one confirmed session, as a short digest.

    Adjusted aggregates are not immutable: a split or a large cash dividend
    retroactively rescales the vendor's whole history, and the nightly pack is
    re-frozen on the new basis while a bucket cache keyed only on
    ``(TICKER, session)`` keeps serving the old one.  The seam between them
    fabricates a move in the 4H histogram, which fabricates a turn — W3-1 in the
    one lane where no basis audit runs.

    So a cached session is stamped with THIS: the pack's own adjusted close for
    that session, on that session's price basis.  It is fixed forever unless the
    basis moves, which is exactly the invalidation signal wanted — a normal
    nightly close appends a bar and moves nothing behind it.  ``None`` when the
    session is outside the frozen substrate (nothing to compare, and the reader
    treats that as uncheckable rather than as agreement).
    """
    from engine.entry_radar.entry_events import sha16  # noqa: PLC0415
    frame = daily.frame
    key = pd.Timestamp(session).normalize()
    if key not in frame.index:
        return None
    close = _float(frame.loc[key, "close"])
    if close is None:
        return None
    return sha16(canonical_json({"basis": daily.price_basis,
                                 "session": session.isoformat(),
                                 "close": round(float(close), 6)}))


def cross_check(pack_name: lp.PackName, obs: ch.Observation, *,
                epsilon_rel: float = CROSS_CHECK_EPSILON_REL) -> dict[str, Any]:
    """Compare the ORACLE's C1/C2a booleans against the pack's solved levels.

    The pack ships levels so the RTH lane never has to re-derive one; this is the
    check that the levels and the oracle still describe the same detector.  A
    disagreement is a ``pack_integrity`` refusal for the name — deliberately NOT
    a fall-back to either answer, because an evaluator that disagrees with its
    own frozen thresholds does not know which of the two is wrong.

    Inside ``epsilon_rel`` of a solved level the two are allowed to differ: the
    level was bisected to a relative tolerance, so at a price that close both
    answers are correct readings of the same boundary.  A degenerate level with
    a constant ``bracket_verdict`` is compared with no band at all (the verdict is
    exact); a degenerate level with no verdict — the ``flat_rsi_nan`` and
    ``non_monotone`` NULLS — is uncheckable and counted as such, never as a pass.
    """
    price = obs.sampled_close
    checks: dict[str, Any] = {}
    verdicts: list[str] = []
    for name, solution, oracle in (
            ("c1", pack_name.c1_arm_price,
             (None if obs.k is None else bool(obs.k < ic.OVERSOLD))),
            ("c2a", pack_name.c2a_cross_price,
             (None if obs.k is None or obs.d is None else bool(obs.k > obs.d)))):
        if price is None or oracle is None or obs.availability in ch.NULL_AVAILABILITY:
            row = {"oracle": oracle, "pack": None, "verdict": "unchecked",
                   "reason": "no_reading"}
        else:
            predicted = solution.holds_at(float(price))
            if predicted is None:
                row = {"oracle": oracle, "pack": None, "verdict": "unchecked",
                       "reason": solution.reason or "no_threshold"}
            elif _boundary_band(solution, float(price), epsilon_rel=epsilon_rel):
                row = {"oracle": oracle, "pack": predicted, "verdict": "boundary_band",
                       "reason": "within the solver's own relative tolerance"}
            elif bool(predicted) == bool(oracle):
                row = {"oracle": oracle, "pack": predicted, "verdict": "agree",
                       "reason": None}
            else:
                row = {"oracle": oracle, "pack": predicted, "verdict": "disagree",
                       "reason": f"pack level {solution.price} says {predicted} at "
                                 f"{price}, the oracle says {oracle}"}
        row["threshold"] = solution.price
        row["no_threshold_exists"] = solution.no_threshold_exists
        checks[name] = row
        verdicts.append(str(row["verdict"]))
    checks["verdict"] = ("disagree" if "disagree" in verdicts
                         else "agree" if "agree" in verdicts else "unchecked")
    return checks


# ---------------------------------------------------------------------------
# the pass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NameResult:
    """One probe name's outcome for one pass.  Payload rows are built from this."""

    ticker: str
    state: str
    reasons: tuple[str, ...] = ()
    quote: QuotePoint | None = None
    basis: dict[str, Any] | None = None
    observations: tuple[ch.Observation, ...] = ()
    runs: tuple[Any, ...] = ()
    cross_check: dict[str, Any] | None = None
    lanes: dict[str, Any] = field(default_factory=dict)
    suppressed: tuple[dict[str, Any], ...] = ()
    #: The quote point the journal REFUSED, when one was refused.  ``quote`` is
    #: then the point the tape actually used, so the row cannot advertise a price
    #: no detector read (H2); this field is where the rejected one is disclosed.
    quote_rejected: dict[str, Any] | None = None

    @property
    def dark(self) -> bool:
        return self.state != "evaluated"

    @property
    def null_reading(self) -> str | None:
        """The latest observation's availability when it is a NULL, else None."""
        latest = self.observations[-1] if self.observations else None
        if latest is None:
            return None
        return (str(latest.availability)
                if latest.availability in ch.NULL_AVAILABILITY else None)


@dataclass(frozen=True, slots=True)
class PassResult:
    """Everything one pass produced.  The script publishes it; tests read it."""

    payload: dict[str, Any]
    health: dict[str, Any]
    delta: ll.PendingDelta | None
    spool_key: str | None
    committed: bool
    exit_code: int
    names: tuple[NameResult, ...] = ()


def _authority_block() -> dict[str, bool]:
    """All-false, always.  The live lane holds no authority of any kind."""
    from engine.entry_radar.readings import AUTHORITY_BLOCK  # noqa: PLC0415
    return {k: False for k in AUTHORITY_BLOCK}


def _heartbeat_path(state_dir: Path | None) -> Path | None:
    return None if state_dir is None else Path(state_dir) / "heartbeat.json"


def _read_heartbeat(state_dir: Path | None) -> dict[str, Any]:
    path = _heartbeat_path(state_dir)
    if path is None or not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def _write_heartbeat(state_dir: Path | None, payload: Mapping[str, Any]) -> None:
    path = _heartbeat_path(state_dir)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(path, dict(payload))
    except OSError:
        return


def killed(state_dir: Path | None, env: Mapping[str, str] | None = None,
           ) -> tuple[bool, str | None]:
    """``(killed, how)``.  Env first, then the kill FILE in the state dir."""
    environ = os.environ if env is None else env
    raw = str(environ.get(KILL_ENV, "") or "").strip().lower()
    if raw not in ("", "0", "false", "no"):
        return True, KILL_ENV
    if state_dir is not None and (Path(state_dir) / KILL_FILE).exists():
        return True, f"{KILL_FILE} file"
    return False, None


def _pass_block(*, now: datetime, session: date | None, state_dir: Path | None,
                interval_minutes: int, evaluated: bool) -> dict[str, Any]:
    """``health.pass`` — sequence, instants, and the NAMED cadence gap.

    ``seq`` IS THE PASS COUNTER and ``evaluated_seq`` the evaluation counter, and
    the two are separated because they answer different questions.  The heartbeat
    is now written on every terminal path including the whole-cycle refusals, so
    "ran 78 times and refused" and "did not run at all" no longer leave the
    identical trace — the failure signature where a killed lane and a lane that
    never fired are indistinguishable.  ``evaluated_seq`` keeps the older, narrower
    reading available for anything that wants "how many passes actually looked".
    """
    beat = _read_heartbeat(state_dir)
    prev_at = _parse_iso(beat.get("at"))
    seq = int(beat.get("seq") or 0) + 1
    evaluated_seq = int(beat.get("evaluated_seq") or 0) + (1 if evaluated else 0)
    gap: int | None = None
    if prev_at is not None:
        elapsed = (now - prev_at).total_seconds() / 60.0
        gap = max(0, int(round(elapsed / float(interval_minutes))) - 1)
    expected_next = None
    if session is not None:
        bounds = interval_bounds(session, now, interval_minutes=interval_minutes)
        if bounds is not None:
            expected_next = ch.utc_iso(bounds[1])
    return {"seq": seq, "evaluated_seq": evaluated_seq, "at": _iso(now),
            "prev_at": _iso(prev_at), "expected_next": expected_next,
            "prev_gap_intervals": gap}


def _beat_from(health: Mapping[str, Any], *, now: datetime,
               session: date | None) -> dict[str, Any]:
    """The heartbeat row for a finished pass, refusal or evaluation alike."""
    block = health.get("pass") or {}
    return {"seq": block.get("seq"), "evaluated_seq": block.get("evaluated_seq"),
            "at": _iso(now), "session": (session.isoformat() if session else None),
            "state": health.get("state")}


def _refusal_payload(*, state: str, reasons: Sequence[str], now: datetime,
                     session: date | None, pack: lp.LivePack | None,
                     tickers: Sequence[str], state_dir: Path | None,
                     config: LiveEvalConfig, quotes_meta: Mapping[str, Any] | None,
                     ledger: ll.LiveEpisodeLedger | None) -> tuple[dict, dict]:
    """A whole-cycle refusal: every name unavailable, zero transitions, zero spool.

    §5's stale-pack row is explicit that this is not a degraded evaluation but
    an ABSENT one — a wrong-session series fabricates crossings, so the honest
    output is "we did not look", stated for every probe name at once.
    """
    health = {
        "state": state,
        "reasons": list(reasons),
        "pass": _pass_block(now=now, session=session, state_dir=state_dir,
                            interval_minutes=config.interval_minutes,
                            evaluated=False),
        "inputs": {
            "quotes": {"asof": (quotes_meta or {}).get("asof"), "age_s": None,
                       "coverage": f"0/{len(tickers)}", "stale_n": 0},
            "pack": {"as_of": (pack.as_of if pack else None),
                     "pack_hash": (pack.pack_hash if pack else None),
                     "fresh": False,
                     "proof_failed": bool(pack.proof_failed) if pack else None},
            "spool": {"ok": None, "key": None, "error": None},
            "c3_reader": {"fetched_n": 0, "cache_hits": 0, "errors": 0, "empty": 0,
                          "deferred_n": 0, "incomplete_n": 0,
                          "reader_fetched_n": 0, "reader_cache_hits": 0,
                          "reader_errors": 0, "reader_empty": 0},
        },
        "basis": {"audited_n": 0, "mismatched_n": 0, "unchecked_n": 0, "refused": []},
        "null_readings": {"reading_unavailable": 0, "reading_stale": 0,
                          "suppressed": 0},
        "dark": {reason: 0 for reason in NAME_REFUSALS},
        "content": {"last_transition_at": None, "events_total": 0,
                    "ledger_hash": _ledger_hash(ledger)},
    }
    payload = {
        "schema": SCHEMA_LIVE_PAYLOAD,
        "asof": _iso(now),
        "session": session.isoformat() if session else None,
        "pack": {"as_of": (pack.as_of if pack else None),
                 "pack_hash": (pack.pack_hash if pack else None)},
        "authority": _authority_block(),
        "names": [{"ticker": t, "state": "unavailable", "reasons": list(reasons),
                   "lanes": {}} for t in sorted(tickers)],
        "transitions": [],
        "events": [],
        "health": health,
        "research_priority": _empty_priority_board(
            computed_at=_iso(now), cycle_state=state, reason="cycle_refused"),
    }
    return payload, health


def _ledger_hash(ledger: ll.LiveEpisodeLedger | None) -> str | None:
    """A content digest over the ledger's episodes — the content-advance signal.

    A green process is not a current one.  ``pass.at`` says the lane ran, the
    quote asof says the input moved, and THIS says the state actually changed;
    all three are needed because any two of them can advance while the third is
    frozen.
    """
    if ledger is None:
        return None
    from engine.entry_radar.entry_events import sha16  # noqa: PLC0415
    return sha16(canonical_json([e.to_dict() for e in ledger.episodes]))


def failure_payload(*, now: datetime, pack: lp.LivePack | None,
                    tickers: Sequence[str] | None = None,
                    state_dir: Path | str | None = None,
                    config: LiveEvalConfig | None = None,
                    quotes: Mapping[str, Any] | None = None,
                    ledger: ll.LiveEpisodeLedger | None = None,
                    error: BaseException | str | None = None,
                    ) -> tuple[dict[str, Any], dict[str, Any]]:
    """The ``failed`` receipt — THE PRODUCER for design §6's evaluator-failure state.

    ``run_pass`` itself never produces ``failed`` and must not: a state machine
    that reports its own crash is reporting from inside the crash.  The producer
    is the ENTRYPOINT's outer handler, which still has a live process, a resolved
    live directory and a probe set, and which publishes this rather than leaving
    the previous artifact in place with its previous ``health.pass.at``.  That
    silence was the whole defect — a persistent per-name fault could burn a full
    session behind a stale-but-whole payload while the process exited 0 and the
    only alarm, the freshness sentinel, is pinned at SESSION grain.

    Shape-identical to the other whole-cycle refusals on purpose: an operator
    reading a failed cycle needs the same fields in the same places.
    """
    cfg = config or LiveEvalConfig()
    probe = list(tickers) if tickers is not None else _probe_tickers(pack)
    detail = (f"{type(error).__name__}: {error}" if isinstance(error, BaseException)
              else str(error or "unspecified"))
    return _refusal_payload(state="failed", reasons=[f"evaluator_failed:{detail}"],
                            now=now, session=None, pack=pack, tickers=probe,
                            state_dir=Path(state_dir) if state_dir is not None else None,
                            config=cfg, quotes_meta=quotes, ledger=ledger)


def run_pass(*, now: datetime, pack: lp.LivePack | None,
             quotes: Mapping[str, Any] | None,
             ledger: ll.LiveEpisodeLedger,
             state_dir: Path | str | None = None,
             spool: ll.EventSpool | None = None,
             intraday_reader: Any = None,
             config: LiveEvalConfig | None = None,
             env: Mapping[str, str] | None = None,
             tickers: Sequence[str] | None = None,
             unspooled_ok: bool = False,
             dry_run: bool = False) -> PassResult:
    """One 5-minute RTH pass.  PURE given its inputs (W4 design §2 steps 1-10).

    ``quotes`` is the loaded quote view in ``live_verify.load_live_quotes`` shape
    — ``{"quotes": {SYM: row}, "asof": ..., "delayed_min"|"feed_delay_min": ...}``.
    The SCRIPT loads it; this function never opens a file for it, which is what
    keeps the whole cycle replayable from a dict.

    ``dry_run`` means WRITE NOTHING TO THE STATE PLANE — no journal flush, no
    heartbeat.  It has to live here rather than in the script: the state dir is
    the evaluator's, so gating only the spool left ``--dry-run`` on the VPS
    appending a point to the live journal and bumping the heartbeat, corrupting
    the next real pass's ``prev_gap_intervals`` and ``seq``.  The pass still
    derives everything, which is the point of a rehearsal.

    THE HEARTBEAT IS WRITTEN ON EVERY TERMINAL PATH, refusals included, and
    carries the state that ended the pass.  Written only on the evaluating path
    it made ``seq`` an EVALUATION counter wearing a pass counter's name, so a
    lane that ran 78 times and refused every one left the same trace as a lane
    that never fired — the exact signature this estate has been burned by.
    """
    cfg = config or LiveEvalConfig()
    root = Path(state_dir) if state_dir is not None else None
    probe = list(tickers) if tickers is not None else _probe_tickers(pack)

    def _refuse(state: str, reasons: Sequence[str], *, session: date | None,
                pack_arg: lp.LivePack | None, exit_code: int) -> PassResult:
        payload, health = _refusal_payload(
            state=state, reasons=list(reasons), now=now, session=session,
            pack=pack_arg, tickers=probe, state_dir=root, config=cfg,
            quotes_meta=quotes, ledger=ledger)
        if not dry_run:
            _write_heartbeat(root, _beat_from(health, now=now, session=session))
        return PassResult(payload=payload, health=health, delta=None, spool_key=None,
                          committed=True, exit_code=exit_code)

    is_killed, how = killed(root, env)
    if is_killed:
        return _refuse("killed", [f"kill_switch:{how}"], session=None,
                       pack_arg=pack, exit_code=0)

    inside, why, session = in_window(now, grace_min=cfg.window_end_grace_min)
    if not inside:
        return _refuse("out_of_window", [why], session=session, pack_arg=pack,
                       exit_code=0)

    if pack is None:
        return _refuse("stale_pack", ["no_pack"], session=session, pack_arg=None,
                       exit_code=5)

    if not lp.pack_is_fresh(pack, now):
        return _refuse("stale_pack", [f"pack_as_of:{pack.as_of}"], session=session,
                       pack_arg=pack, exit_code=5)

    if pack.proof_failed:
        # An evaluator that disagrees with the frozen thresholds must not run
        # (design §1, the nightly inversion-proof battery).
        return _refuse("proof_failed", ["pack_inversion_proof_failed"],
                       session=session, pack_arg=pack, exit_code=5)

    return _evaluate(now=now, session=session, pack=pack, quotes=quotes,
                     ledger=ledger, state_dir=root, spool=spool,
                     intraday_reader=intraday_reader, cfg=cfg, probe=probe,
                     unspooled_ok=unspooled_ok, dry_run=dry_run)


def _probe_tickers(pack: lp.LivePack | None) -> list[str]:
    if pack is None:
        return []
    embedded = (pack.probe_set or {}).get("tickers")
    if isinstance(embedded, (list, tuple)) and embedded:
        return [str(t) for t in embedded]
    return [row.ticker for row in pack.names]


def _evaluate(*, now: datetime, session: date, pack: lp.LivePack,
              quotes: Mapping[str, Any] | None, ledger: ll.LiveEpisodeLedger,
              state_dir: Path | None, spool: ll.EventSpool | None,
              intraday_reader: Any, cfg: LiveEvalConfig, probe: Sequence[str],
              unspooled_ok: bool, dry_run: bool = False) -> PassResult:
    """Steps 4-10.  One name at a time, then one spool object for the pass.

    ONE NAME CANNOT KILL THE PASS.  ``LiveEvalError``, ``ChallengerError``,
    ``C3Error``/``VendorMinutesError`` and ``LedgerError`` are SIBLINGS, so
    catching the first let any of the others end the whole cycle with no payload
    at all — and the entrypoint returned 0, leaving a stale-but-whole artifact.
    Everything a name can raise, including a class this module has never heard
    of, darks that ONE name with a classified reason (:func:`error_reason`) and
    the rest of the probe set is still evaluated.  ``ledger.apply_run`` is inside
    the same protection: it constructs ``LiveEpisode`` records whose validation
    raises, and it sat OUTSIDE the try entirely.
    """
    book = (quotes or {}).get("quotes") if isinstance(quotes, Mapping) else None
    book = book if isinstance(book, Mapping) else {}
    budget = quote_budget(quotes, slack_min=cfg.quote_slack_min)
    journal = SessionJournal(state_dir)
    by_ticker = pack.by_ticker()
    session_iso = session.isoformat()

    c3_names, c3_deferred = _c3_budget(pack, ledger, probe, by_ticker, cfg,
                                       enabled=cfg.c3_enabled
                                       and intraday_reader is not None)
    results: list[NameResult] = []
    deltas: list[ll.PendingDelta] = []
    c3_stats = {"fetched_n": 0, "cache_hits": 0, "errors": 0, "empty": 0,
                "deferred_n": len(c3_deferred), "incomplete_n": 0}
    basis_stats = {"audited_n": 0, "mismatched_n": 0, "unchecked_n": 0,
                   "refused": []}
    stale_quotes = 0
    covered = 0

    for ticker in sorted(probe):
        # THE PROTECTED REGION IS THE WHOLE NAME, not the engine call alone.
        # It used to open just above ``_evaluate_name``, which left
        # ``pack_daily_history`` (a parquet/frame read), ``read_quote`` (a vendor
        # row of unknown shape) and ``basis_audit`` outside it — three places a
        # single malformed name still raised out of ``run_pass`` and killed the
        # pass for every other name.  That is the C2 failure mode with a shorter
        # blast radius, not a fixed one.  ``quote``/``audit`` are pre-bound so the
        # handler can report whatever the name got as far as.
        quote: QuotePoint | None = None
        audit: Mapping[str, Any] | None = None
        try:
            pack_name = by_ticker.get(ticker)
            daily = pack_daily_history(pack, ticker)
            if pack_name is None or daily is None:
                results.append(NameResult(ticker=ticker, state="unavailable",
                                          reasons=("no_substrate",)))
                continue

            quote = read_quote(ticker, book.get(ticker), now=now, session=session,
                               max_age_min=budget)
            if quote.state != "no_quote":
                covered += 1
            if quote.state == "stale_quote":
                stale_quotes += 1

            # STEP 4 BEFORE STEP 5 (design §2 order).  The audit used to run
            # first, which reported ``basis_mismatch`` for a name whose REAL
            # problem was a dead quote lane — and counted a name that never
            # reached the engine in ``audited_n``, so the ``basis_unverified``
            # guard could be satisfied by dark names alone.  A universe-wide
            # quote outage must not read as a universe-wide data-integrity fault.
            if not quote.usable:
                results.append(NameResult(ticker=ticker, state="unavailable",
                                          reasons=(quote.state,), quote=quote))
                continue

            audit = lp.basis_audit(pack_name.as_of_close, quote.prev_close,
                                   tolerance_pct=cfg.basis_tolerance_pct)
            if audit.get("mismatch") is True:
                basis_stats["audited_n"] += 1
                basis_stats["mismatched_n"] += 1
                basis_stats["refused"].append(ticker)
                # THE ENGINE IS NEVER REACHED.  No tape, no observation, no
                # reading with a verdict — and the tape is not re-based into
                # compliance.
                results.append(NameResult(ticker=ticker, state="unavailable",
                                          reasons=("basis_mismatch",), quote=quote,
                                          basis=audit))
                continue
            if audit.get("mismatch") is False:
                basis_stats["audited_n"] += 1
            else:
                basis_stats["unchecked_n"] += 1

            result = _evaluate_name(
                ticker=ticker, now=now, session=session, session_iso=session_iso,
                pack=pack, pack_name=pack_name, daily=daily, quote=quote,
                audit=audit, journal=journal, ledger=ledger, cfg=cfg,
                intraday_reader=(intraday_reader if ticker in c3_names else None),
                c3_deferred=(ticker in c3_deferred), c3_stats=c3_stats)
            delta = None
            if result.runs:
                delta = ledger.apply_run(
                    ticker=ticker, as_of_session=session_iso,
                    runs=list(result.runs), pass_id=cfg.pass_id,
                    context={"pack_as_of": pack.as_of, "pack_hash": pack.pack_hash})
        except Exception as exc:  # noqa: BLE001 — one name, never the pass
            results.append(NameResult(
                ticker=ticker, state="unavailable",
                reasons=(error_reason(exc),), quote=quote, basis=audit,
                lanes={"error": str(exc), "error_class": type(exc).__name__}))
            continue
        results.append(result)
        if delta is not None:
            deltas.append(delta)

    delta = ll.merge_deltas(deltas, as_of_session=session_iso, pass_id=cfg.pass_id) \
        if deltas else ll.PendingDelta(ticker="*", as_of_session=session_iso,
                                       pass_id=cfg.pass_id)

    health = _health(now=now, session=session, pack=pack, quotes=quotes,
                     results=results, ledger=ledger, state_dir=state_dir, cfg=cfg,
                     c3_stats=c3_stats, basis_stats=basis_stats,
                     stale_quotes=stale_quotes, covered=covered, probe=probe,
                     delta=delta)

    # STEP 8 — spool BEFORE commit.  A failure withholds the transitions from
    # both the ledger and the payload; the next pass re-derives and retries, and
    # every address is deterministic so the retry admits nothing twice.
    stamp = now.astimezone(_et()).strftime("%H%M%S")
    spool_key: str | None = None
    committed = True
    spool_error: str | None = None
    if not delta.empty:
        try:
            spool_key, committed = ll.spool_then_commit(
                ledger, delta, spool=spool, pass_ts=_iso(now) or "",
                session=session_iso, stamp=stamp, pack_as_of=pack.as_of,
                pack_hash=pack.pack_hash, health=health,
                unspooled_ok=unspooled_ok)
        except Exception as exc:  # noqa: BLE001 — a sink fault is not a math fault
            spool_key, committed, spool_error = None, False, str(exc)
    health["inputs"]["spool"] = {"ok": committed if not delta.empty else None,
                                 "key": spool_key, "error": spool_error}
    if not committed:
        health["state"] = "degraded"
        if "spool_failed" not in health["reasons"]:
            health["reasons"].append("spool_failed")

    if not dry_run:
        for result in results:
            record = journal.read(session_iso, result.ticker)
            if record is not None:
                journal.flush(record)

    # The content-advance signal is re-read AFTER the commit, so it describes the
    # ledger the payload actually reports.  Taken before, it would be the PREVIOUS
    # pass's hash on every pass that admitted something — a content signal that
    # lags content by one tick is worse than none, because it looks like it works.
    health["content"]["ledger_hash"] = _ledger_hash(ledger)
    payload = _payload(now=now, session=session, pack=pack, results=results,
                       delta=delta, committed=committed, health=health)
    if not dry_run:
        _write_heartbeat(state_dir, _beat_from(health, now=now, session=session))
    exit_code = 4 if not committed else 0
    return PassResult(payload=payload, health=health, delta=delta,
                      spool_key=spool_key, committed=committed,
                      exit_code=exit_code, names=tuple(results))


def _evaluate_name(*, ticker: str, now: datetime, session: date, session_iso: str,
                   pack: lp.LivePack, pack_name: lp.PackName,
                   daily: ch.DailyHistory, quote: QuotePoint,
                   audit: Mapping[str, Any], journal: SessionJournal,
                   ledger: ll.LiveEpisodeLedger, cfg: LiveEvalConfig,
                   intraday_reader: Any, c3_deferred: bool,
                   c3_stats: dict[str, int]) -> NameResult:
    """Steps 6-7 for ONE name: journal, observations, cross-check, evaluators."""
    record = journal.open_session(session=session_iso, ticker=ticker,
                                  pack_as_of=pack.as_of, pack_hash=pack.pack_hash,
                                  price_basis=pack.price_basis)
    assert quote.ts is not None and quote.price is not None  # quote.usable
    reasons: tuple[str, ...] = ()
    quote_rejected: dict[str, Any] | None = None
    last_point = record.points[-1] if record.points else None
    if not journal.append_point(record, ts=quote.ts, price=quote.price,
                                basis=quote.basis, source=quote.source,
                                basis_audit=audit):
        # THE ROW MUST ADVERTISE THE PRICE THE DETECTORS READ.  An append-only
        # refusal is lawful and the pass keeps evaluating — but publishing the
        # REJECTED quote beside an observation built from the kept one is a
        # divergence disclosed nowhere except a journal file on the VPS.
        #
        # An illiquid name republishes the same vendor ``ts`` for many
        # consecutive passes, so refusal is the STEADY STATE there and alarming
        # on it would be noise.  The price delta is what separates the two: same
        # ts and same price is a quiet tape, same ts and a different price is a
        # vendor correction (or the two-file freshest-wins merge flipping source)
        # and that one gets a named reason.
        kept_price = _float((last_point or {}).get("price"))
        if kept_price is None or float(kept_price) != float(quote.price):
            reasons = reasons + ("journal_refused_point",)
            quote_rejected = quote.to_dict()
        kept_ts = _parse_iso((last_point or {}).get("ts"))
        quote = replace(
            quote, price=kept_price, ts=kept_ts,
            basis=(last_point or {}).get("basis"),
            source=(last_point or {}).get("source"),
            age_min=(None if kept_ts is None
                     else round((now - kept_ts).total_seconds() / 60.0, 4)))

    builder = IncrementalObservationBuilder(
        ticker=ticker, daily=daily, session=session,
        interval_minutes=cfg.interval_minutes)
    today = builder.observations(record.tape(session), now=now,
                                 journaled=journal.observations_of(record))
    journal.freeze_observations(record, today)

    latest = today[-1] if today else None
    checks = cross_check(pack_name, latest, epsilon_rel=cfg.cross_check_epsilon_rel) \
        if latest is not None else None
    if checks is not None and checks.get("verdict") == "disagree":
        # FAIL CLOSED.  The pack's levels and the oracle describe the same
        # detector; when they disagree neither is trustworthy for this name.
        return NameResult(ticker=ticker, state="unavailable",
                          reasons=("pack_integrity",), quote=quote, basis=dict(audit),
                          observations=today, cross_check=checks,
                          quote_rejected=quote_rejected)

    path = _episode_path(ticker=ticker, session_iso=session_iso, today=today,
                         journal=journal, ledger=ledger)

    c1_run = ch.run_c1(path)
    suppressed: list[dict[str, Any]] = []
    c1_run, c1_blocked = _gate_arm(ledger, c1_run, ticker=ticker,
                                   detector_id=ch.C1_DETECTOR_ID, variant=None,
                                   session=session_iso, suppressed=suppressed)
    c1_episode = _live_c1_episode(ledger, ticker, c1_run)

    c2_run = ch.run_c2(path, c1_episode)
    c2_run, c2_blocked = _gate_c2(ledger, c2_run, ticker=ticker, session=session_iso,
                                  suppressed=suppressed)

    runs: list[Any] = [c1_run, c2_run]
    lanes: dict[str, Any] = {
        "c1": _lane_rows(c1_run.readings),
        "c2": _lane_rows(c2_run.readings),
    }

    c3_run = None
    c3_blocked = False
    if c3_deferred:
        # Named, never silent: a deferred C3 lane is NOT a name with no 4H turn,
        # and a payload that showed nothing would be indistinguishable from one.
        lanes["c3_deferred"] = {"availability": "unavailable",
                                "reason": "c3_budget_deferred",
                                "detail": "the pass's minute-fetch budget was spent; "
                                          "this name's 4H lane resumes next pass with "
                                          "a warmer bucket cache"}
    elif cfg.c3_enabled and intraday_reader is not None:
        c3_run, missing = _run_c3(ticker=ticker, daily=daily, session=session, now=now,
                                  reader=intraday_reader, ledger=ledger, cfg=cfg,
                                  stats=c3_stats, pack_as_of=pack.as_of)
        if missing:
            # A FETCH FAULT IS MISSING INPUT, NEVER A NON-FIRE.  Dropping the
            # session and running the detector on what survived does not thin the
            # series, it REBUILDS it: ``four_hour_turn`` reads POSITIONAL
            # neighbours, so every histogram point moves and prev2/prev/now can
            # straddle a calendar gap.  The refusal is the null law applied to
            # the 4H leg, and the missing sessions ride the row so the gap is
            # readable rather than inferred from a lower bar count.
            c3_stats["incomplete_n"] += 1
            reasons = reasons + ("c3_incomplete_window",)
            lanes["c3_incomplete"] = {
                "availability": "unavailable", "reason": "c3_incomplete_window",
                "missing_sessions": [str(day) for day in missing],
                "detail": "the episode window is missing at least one session's 4H "
                          "buckets; C3 is evaluated on the COMPLETE contiguous range "
                          "or not at all"}
        if c3_run is not None:
            c3_run, c3_blocked = _gate_arm(ledger, c3_run, ticker=ticker,
                                           detector_id=fh.C3_DETECTOR_ID, variant=None,
                                           session=session_iso, suppressed=suppressed)
            runs.append(c3_run)
            lanes["c3"] = _lane_rows(c3_run.readings)

    c4 = _c4_context(ticker=ticker, daily=daily, c2_run=c2_run)
    if c4 is not None:
        lanes["c4"] = c4
    lanes["nightly"] = _nightly_lanes(pack, ticker)

    state = "evaluated"
    if latest is not None and latest.availability in ch.NULL_AVAILABILITY:
        reasons = reasons + (f"reading_{latest.availability}",)
    if c1_blocked or c2_blocked or c3_blocked:
        # ALL THREE gates, not just C1's.  A C2- or C3-suppressed name used to
        # carry no ``suppressed_by_rearm`` at all, so the only trace of the §10
        # rule biting lived in ``payload["suppressed"]``.
        reasons = reasons + ("suppressed_by_rearm",)
    return NameResult(ticker=ticker, state=state, reasons=reasons, quote=quote,
                      basis=dict(audit), observations=today, runs=tuple(runs),
                      cross_check=checks, lanes=lanes,
                      suppressed=tuple(suppressed), quote_rejected=quote_rejected)


def _episode_path(*, ticker: str, session_iso: str,
                  today: Sequence[ch.Observation], journal: SessionJournal,
                  ledger: ll.LiveEpisodeLedger) -> tuple[ch.Observation, ...]:
    """Today's observations, prefixed by the live C1 episode's prior sessions.

    Prior sessions come from the journal VERBATIM.  Recomputing them against
    today's pack would move every K and D in the episode's history — the
    mechanical no-backfill law (§7.1) applied to the episode window rather than
    to a single reading.
    """
    live = ledger.live_episode(ticker, ch.C1_DETECTOR_ID, None)
    if live is None or not live.first_armed_at:
        return tuple(today)
    armed_session = str(live.first_armed_at)[:10]
    if armed_session >= session_iso:
        return tuple(today)
    prior: list[ch.Observation] = []
    for candidate in journal.sessions(ticker):
        if armed_session <= candidate < session_iso:
            prior.extend(journal.replay(candidate, ticker))
    return tuple(prior) + tuple(today)


def _live_c1_episode(ledger: ll.LiveEpisodeLedger, ticker: str,
                     c1_run: ch.C1Run) -> ch.DetectorEpisode | None:
    """The C1 episode C2 is eligible inside — this pass's, else the ledger's.

    A multi-day episode armed on a prior session is not re-minted by today's
    replay unless the journal reaches back to it, so the ledger's ``ARMED``
    instant is consulted as the fallback.  A TERMINAL stored episode yields
    None: C2 is eligible inside a NONTERMINAL C1 episode only (A5.3).
    """
    if c1_run.episode is not None:
        return c1_run.episode
    stored = ledger.live_episode(ticker, ch.C1_DETECTOR_ID, None)
    if stored is None or not stored.first_armed_at:
        return None
    shadow = ch.DetectorEpisode(ticker=ticker, detector_id=ch.C1_DETECTOR_ID)
    shadow.first_armed_at = stored.first_armed_at
    shadow.candidate_at = stored.candidate_at
    return shadow


def _gate_arm(ledger: ll.LiveEpisodeLedger, run: Any, *, ticker: str,
              detector_id: str, variant: str | None, session: str,
              suppressed: list[dict[str, Any]]) -> tuple[Any, bool]:
    """§10 re-arm, consulted BEFORE a new arm is admitted.

    ``run_c1``/``run_c3`` are stateless replays and will happily re-mint an arm
    the §10 window forbids; the ledger is the only thing that knows the unit's
    history.  A blocked arm keeps its READINGS — the name was evaluated and the
    condition really was met — and loses only the episode and its event, with
    ``arm_allowed`` recording the ``suppressed_by_rearm`` note §11's control pool
    needs.  Dropping the readings too would erase the evidence that the rule bit.
    """
    episodes = tuple(getattr(run, "episodes", ()) or ())
    if not episodes:
        return run, False
    keep = []
    blocked = False
    for episode in episodes:
        stored = ledger.get(ll.compute_episode_id(
            ticker=ticker, detector_id=detector_id, variant=variant,
            first_armed_at=str(episode.first_armed_at or "")))
        if stored is not None:
            keep.append(episode)
            continue
        mark = len(ledger.suppressions)
        allowed, _reason = ledger.arm_allowed(
            ticker, detector_id, variant=variant, session=session,
            would_have_armed_at=str(episode.first_armed_at or ""))
        if allowed:
            keep.append(episode)
        else:
            blocked = True
            suppressed.extend(_suppression_rows(
                ledger, mark, ticker=ticker, detector_id=detector_id, variant=variant,
                would_have_armed_at=str(episode.first_armed_at or "")))
    if len(keep) == len(episodes):
        return run, blocked
    kept_events = {eid for ep in keep for eid in ep.event_ids}
    return replace(run, episodes=tuple(keep),
                   events=tuple(e for e in getattr(run, "events", ()) or ()
                                if str(e.event_id) in kept_events)), blocked


def _gate_c2(ledger: ll.LiveEpisodeLedger, run: ch.C2Run, *, ticker: str,
             session: str, suppressed: list[dict[str, Any]],
             ) -> tuple[ch.C2Run, bool]:
    """The same §10 gate, per VARIANT — the C2 firing unit (JC2).

    Returns ``(run, blocked)`` like :func:`_gate_arm`.  Discarding the flag left a
    C2-suppressed name with no ``suppressed_by_rearm`` on its row at all.
    """
    if not run.episodes:
        return run, False
    keep = []
    blocked = False
    for episode in run.episodes:
        stored = ledger.get(ll.compute_episode_id(
            ticker=ticker, detector_id=ch.C2_DETECTOR_ID, variant=episode.variant,
            first_armed_at=str(episode.first_armed_at or "")))
        if stored is not None:
            keep.append(episode)
            continue
        mark = len(ledger.suppressions)
        allowed, _reason = ledger.arm_allowed(
            ticker, ch.C2_DETECTOR_ID, variant=episode.variant, session=session,
            would_have_armed_at=str(episode.first_armed_at or ""))
        if allowed:
            keep.append(episode)
        else:
            blocked = True
            suppressed.extend(_suppression_rows(
                ledger, mark, ticker=ticker, detector_id=ch.C2_DETECTOR_ID,
                variant=episode.variant,
                would_have_armed_at=str(episode.first_armed_at or "")))
    if len(keep) == len(run.episodes):
        return run, blocked
    kept_events = {eid for ep in keep for eid in ep.event_ids}
    # ``replace`` rather than a field-by-field rebuild (which named readings /
    # episodes / events / fires): ``C2Run`` is frozen+slots, so a field added
    # later would be silently dropped by the hand-written form.  ``_gate_arm``
    # already does it this way.
    return replace(run, episodes=tuple(keep),
                   events=tuple(e for e in run.events
                                if str(e.event_id) in kept_events)), blocked


def _suppression_rows(ledger: ll.LiveEpisodeLedger, mark: int,
                      **identity: Any) -> list[dict[str, Any]]:
    """THE ONE row recording this suppression — at most one, ever.

    ``ledger.suppressions`` is the whole history and the old filter had no pass
    or session scope, so pass *k* collected *k* identical rows: at ~78 passes a
    session one suppressed name ended the day with 78 copies in the payload and
    78 rows in ``episodes.json``, inflating any §11 control-pool count by exactly
    the pass number.  ``_refuse`` is idempotent now, so the row minted by THIS
    call is normally the only one; the fallback to the stored row keeps the
    payload's evidence intact on the passes after the first (a suppressed lane
    must not go quiet just because the ledger already knew), and the ``[:1]``
    holds even against a ledger written before that fix.
    """
    def _match(row: Mapping[str, Any]) -> bool:
        return all(row.get(key) == value for key, value in identity.items())

    rows = ledger.suppressions
    fresh = [row for row in rows[mark:] if _match(row)]
    return fresh[:1] if fresh else [row for row in rows[:mark] if _match(row)][:1]


def _c3_budget(pack: lp.LivePack, ledger: ll.LiveEpisodeLedger,
               probe: Sequence[str], by_ticker: Mapping[str, lp.PackName],
               cfg: LiveEvalConfig, *, enabled: bool,
               ) -> tuple[frozenset[str], frozenset[str]]:
    """``(fetching, deferred)`` — which names may spend a minute request this pass.

    DETERMINISTIC, so two passes over the same state make the same choice and the
    idempotency battery means something.  An OPEN C3 episode outranks a merely
    washed name — a live episode that stalled behind a cohort of new arms would
    miss the very turn it is waiting for — and ties break alphabetically rather
    than by dict order.
    """
    if not enabled:
        return frozenset(), frozenset()
    wanted = [t for t in sorted(probe)
              if t in by_ticker and _c3_wanted(by_ticker[t], ledger, t)]
    if len(wanted) <= int(cfg.c3_max_names_per_pass):
        return frozenset(wanted), frozenset()
    ranked = sorted(
        wanted,
        key=lambda t: (0 if ledger.live_episode(t, fh.C3_DETECTOR_ID, None) is not None
                       else 1, t))
    keep = ranked[:int(cfg.c3_max_names_per_pass)]
    return frozenset(keep), frozenset(ranked[int(cfg.c3_max_names_per_pass):])


def _c3_wanted(pack_name: lp.PackName, ledger: ll.LiveEpisodeLedger,
               ticker: str) -> bool:
    """C3 runs for a washed CONFIRMED daily leg or an open C3 episode.

    Bounded on purpose: the reader is a per-name REST fetch, and a probe set of
    ~1,500 names cannot each pay one every five minutes.  ``confirmed_k`` is the
    pack's frozen daily K, which is exactly the leg ``c3_daily_leg`` will read.
    """
    if ledger.live_episode(ticker, fh.C3_DETECTOR_ID, None) is not None:
        return True
    k = pack_name.confirmed_k
    return k is not None and float(k) < float(ic.OVERSOLD)


def _run_c3(*, ticker: str, daily: ch.DailyHistory, session: date, now: datetime,
            reader: Any, ledger: ll.LiveEpisodeLedger, cfg: LiveEvalConfig,
            stats: dict[str, int], pack_as_of: str,
            ) -> tuple[fh.C3Run | None, tuple[date, ...]]:
    """``(run, missing_sessions)`` for C3 over the episode window.

    ``now`` is handed to :func:`four_hour.four_hour_buckets` so a bucket is
    CONFIRMED only once its effective end has passed — the incomplete-bucket
    refusal (PIT-W4-7) is that argument, not a filter applied afterwards.

    A reader exposing ``buckets(ticker, session, now=)`` is preferred over the
    bare protocol call: that is the cached path, and a completed session served
    from the state dir costs no request at all.  A plain callable — every test
    fixture, and any future reader — still works through the protocol.

    THE WINDOW IS ALL-OR-NOTHING.  ``run_c3`` is handed the COMPLETE contiguous
    session range or it is not called: ``four_hour_turn`` reads positional
    neighbours of the completed-4H series, so a session dropped by a transient
    502 does not thin the series, it rebuilds every point of it and can put a
    calendar gap between prev2/prev/now.  A missing session is missing INPUT and
    the caller reports it as such (``c3_incomplete_window``, availability
    ``unavailable``) — never as a name with no turn.  ``completed_4h_gaps`` cannot
    cover this: it counts buckets that were FETCHED and empty, and a session
    never fetched contributes no bucket at all.

    THE WINDOW START IS CLAMPED to the reader's own bound.  An ARMED C3 episode
    older than ``max_window_sessions − warm-up`` otherwise makes ``assert_window``
    raise on EVERY pass, and C3's arm expiry is internal to ``run_c3`` — so the
    code that would expire the episode is the code that cannot run, and the wedge
    is permanent.  Clamped, the pass survives and ``run_c3``'s own §10 clock
    expires the episode on the shortened window.
    """
    from lib.nyse_calendar import sessions_between  # noqa: PLC0415
    live = ledger.live_episode(ticker, fh.C3_DETECTOR_ID, None)
    anchor = session
    if live is not None and live.first_armed_at:
        try:
            anchor = date.fromisoformat(str(live.first_armed_at)[:10])
        except ValueError:
            anchor = session
    start = _session_back(anchor, int(cfg.c3_warmup_sessions)) or anchor
    bound = getattr(reader, "max_window_sessions", None)
    if bound:
        floor = _session_back(session, max(int(bound) - 1, 0))
        if floor is not None and floor > start:
            start = floor
    bounded = getattr(reader, "assert_window", None)
    if callable(bounded):
        bounded(start, session)
    cached = getattr(reader, "buckets", None)
    window = sessions_between(start, session)
    buckets: list[tuple[date, Sequence[fh.FourHourBucket]]] = []
    missing: list[date] = []
    for day in window:
        try:
            if callable(cached):
                # ``vintage`` is the ADJUSTMENT BASIS this pass expects for that
                # session (H4).  Adjusted minute aggregates are not immutable —
                # a split rescales the vendor's whole history — so a cache keyed
                # on (TICKER, session) alone would serve pre-adjustment closes
                # beside post-adjustment fresh ones across the split boundary.
                rows = cached(ticker, day, now=now,
                              vintage={"pack_as_of": str(pack_as_of),
                                       "substrate_fingerprint":
                                           substrate_fingerprint(daily, day)})
            else:
                tape = reader(ticker, day)
                rows = None if tape is None else fh.four_hour_buckets(tape, now=now)
        except Exception:  # noqa: BLE001 — a reader fault refuses C3, never the pass
            stats["errors"] += 1
            missing.append(day)
            continue
        if not rows:
            missing.append(day)
            continue
        stats["fetched_n"] += 1
        buckets.append((day, rows))
    for key, value in _reader_stats(reader).items():
        # NAMESPACED, never merged over a counter the PASS owns.  The reader's
        # ``errors`` increments only on a TRANSPORT raise, so an aggregation or
        # timezone fault — the ones its own docstring warns about — left it at
        # zero, and the blanket overwrite destroyed the honest local count.  That
        # is what kept ``c3_reader_errors`` from ever reaching the health reasons
        # and the state from ever leaving ``live``.  Counters the pass CANNOT keep
        # (whether a bucket came off disk, whether a response was empty) are the
        # reader's to report and are folded in as well as namespaced.
        stats[f"reader_{key}"] = int(value)
        if key not in PASS_OWNED_C3_STATS:
            stats[key] = int(value)
    if missing or not buckets:
        return None, tuple(missing)
    return fh.run_c3(ticker=ticker, daily=daily, buckets_by_session=buckets), ()


def _reader_stats(reader: Any) -> dict[str, int]:
    """A reader's own counters when it keeps them, else nothing to merge."""
    stats = getattr(reader, "stats", None)
    if not callable(stats):
        return {}
    try:
        return {k: int(v) for k, v in stats().to_dict().items()}
    except Exception:  # noqa: BLE001 — a counter is never worth failing a pass
        return {}


def _session_back(session: date, n: int) -> date | None:
    from lib.nyse_calendar import session_n_back  # noqa: PLC0415
    try:
        return session_n_back(session, int(n))
    except Exception:  # noqa: BLE001
        return None


def _c4_context(*, ticker: str, daily: ch.DailyHistory,
                c2_run: ch.C2Run) -> dict | None:
    """C4 stratification context at a C2a candidate.  Never a firing lane.

    C4 structurally cannot fire (``c4_reading.condition_met`` is always None), so
    this block is CONTEXT on the payload row and nothing else — it produces no
    episode, no event and no transition.

    THE SNAPSHOT IS CUT AT THE CANDIDATE'S OWN SESSION, not at the pass's.
    ``run_c2`` replays the whole episode path every pass and re-mints
    ``candidate_at`` at its ORIGINAL instant, so a multi-day episode's candidate
    can be days older than the pass — and passing the pass session made
    ``confirmed_through`` cut at today, producing a reading stamped in the past
    from bars confirmed after it (measured: candidate 2026-08-11T15:00Z, pass
    session 2026-08-17, bars through 2026-08-14 behind an ``observed_at`` of
    2026-08-11; the lawful cut is 2026-08-10).  That is §0's PIT gate verbatim,
    and it also made the row self-contradicting: ``observed_at`` and
    ``market_session`` named different sessions.  Nothing fires off C4, so no
    decision moved — but a published reading built from post-stamp data is
    exactly what the battery exists to make impossible.
    """
    episode = c2_run.variant_episode(ch.C2_PRIMARY_VARIANT)
    if episode is None or not episode.candidate_at:
        return None
    try:
        candidate_session = date.fromisoformat(str(episode.candidate_at)[:10])
    except ValueError:
        return None
    state = ch.c4_snapshot(ticker=ticker, daily=daily,
                           market_session=candidate_session)
    reading = ch.c4_reading(state, observed_at=str(episode.candidate_at))
    row = reading.to_dict()
    row.pop("authority", None)
    return row


def _nightly_lanes(pack: lp.LivePack, ticker: str) -> dict[str, Any]:
    """G0/C5 confirmed-bar states from the pack manifest, honestly absent.

    §3b: no Terminal slice store exists in production, so these publish
    ``unavailable`` with ``slice_store_unconfigured`` until the artifact plane
    lands.  Reading them off the pack keeps the RTH lane out of that ingest
    entirely.
    """
    lanes = (pack.probe_set or {}).get("nightly_lanes")
    if isinstance(lanes, Mapping):
        row = lanes.get(ticker)
        if isinstance(row, Mapping):
            return dict(row)
    return {"g0": {"availability": "unavailable", "reason": "slice_store_unconfigured"},
            "c5": {"availability": "unavailable", "reason": "slice_store_unconfigured"}}


def _lane_rows(readings: Sequence[Any]) -> list[dict[str, Any]]:
    """The LATEST reading per (detector, variant).  Full fidelity, no flattening.

    One name occupies many lanes at once and they are never deduped into a
    generic entry signal (§18 A5.3 / PIT-W4-12): the key is the variant, so six
    C2 mechanisms stay six rows.
    """
    latest: dict[tuple[str, str | None], Any] = {}
    for reading in readings:
        latest[(reading.detector_id, reading.variant)] = reading
    out = []
    for key in sorted(latest, key=lambda k: (k[0], k[1] or "")):
        row = latest[key].to_dict()
        row.pop("authority", None)
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# health receipt + payload (design §6)
# ---------------------------------------------------------------------------

def _health(*, now: datetime, session: date, pack: lp.LivePack,
            quotes: Mapping[str, Any] | None, results: Sequence[NameResult],
            ledger: ll.LiveEpisodeLedger, state_dir: Path | None,
            cfg: LiveEvalConfig, c3_stats: Mapping[str, int],
            basis_stats: Mapping[str, Any], stale_quotes: int, covered: int,
            probe: Sequence[str], delta: ll.PendingDelta) -> dict[str, Any]:
    """The deterministic, enumerated health block."""
    quote_asof = (quotes or {}).get("asof") if isinstance(quotes, Mapping) else None
    asof_ts = _parse_iso(quote_asof)
    reasons: list[str] = []
    if basis_stats.get("mismatched_n"):
        reasons.append(f"basis_mismatch:{basis_stats['mismatched_n']}")
    if basis_stats.get("audited_n") == 0 and basis_stats.get("unchecked_n"):
        # A feed that stops publishing prevClose produces the same zero-mismatch
        # count as a healthy one.  Saying so is the whole point of the counter.
        reasons.append("basis_unverified")
    if stale_quotes:
        reasons.append(f"stale_quote:{stale_quotes}")
    if covered < len(probe):
        reasons.append(f"quote_coverage:{covered}/{len(probe)}")
    # Every remaining per-name refusal gets a reason too.  Without this a pass in
    # which names darked ONLY on a carried or premarket quote published
    # ``state: degraded`` beside ``reasons: []`` — a receipt that says something
    # is wrong and refuses to say what, which is the exact failure mode §6's
    # enumeration exists to prevent.  ``stale_quote``/``basis_mismatch`` already
    # had their own lines above (they carry counts the others do not), so the
    # sweep skips them rather than double-reporting.
    #
    # COUNTED ACROSS EVERY ROW, not across dark rows only: two of the enumerated
    # refusals (``journal_refused_point``, ``c3_incomplete_window``) refuse a
    # point and a lane while the name still evaluates, so a dark-only count could
    # structurally never leave zero for them.
    dark_counts = {reason: sum(1 for r in results if reason in r.reasons)
                   for reason in NAME_REFUSALS}
    for reason in NAME_REFUSALS:
        if reason in ("stale_quote", "no_quote", "basis_mismatch"):
            continue
        if dark_counts[reason]:
            reasons.append(f"{reason}:{dark_counts[reason]}")
    if c3_stats.get("errors"):
        reasons.append(f"c3_reader_errors:{c3_stats['errors']}")
    if c3_stats.get("deferred_n"):
        reasons.append(f"c3_deferred:{c3_stats['deferred_n']}")

    block = _pass_block(now=now, session=session, state_dir=state_dir,
                        interval_minutes=cfg.interval_minutes, evaluated=True)
    if block.get("prev_gap_intervals"):
        reasons.append(f"cadence_gap:{block['prev_gap_intervals']}")

    # NULL READINGS ARE COUNTED, and an all-null pass is not ``live`` (H1).
    # A name whose substrate went stale is ``state="evaluated"`` with only a
    # per-row reason, so a universe of them produced ``state: live`` beside
    # ``reasons: []`` and ``dark`` all zeroes — zero measurements taken,
    # ``condition_met`` None everywhere, and a receipt with nothing to report.
    # ``dark`` cannot cover it by construction: a null reading is not a dark name.
    evaluated = [r for r in results if not r.dark]
    nulls = {"reading_unavailable": 0, "reading_stale": 0,
             "suppressed": sum(1 for r in evaluated
                               if "suppressed_by_rearm" in r.reasons)}
    null_n = 0
    for row in evaluated:
        availability = row.null_reading
        if availability is None:
            continue
        null_n += 1
        key = f"reading_{availability}"
        nulls[key] = nulls.get(key, 0) + 1
    if evaluated and null_n == len(evaluated):
        reasons.append(f"reading_null:{null_n}/{len(evaluated)}")

    # ``live`` is the NARROW state: something was evaluated, at least one reading
    # was a real measurement, and nothing was withheld.  Everything else in a pass
    # that got past the whole-cycle gates is ``degraded`` — including "every name
    # darked", which is a pass that ran and saw nothing rather than a pass that
    # refused to look, and which the reasons list distinguishes.
    state = ("live" if (evaluated and null_n < len(evaluated) and not reasons)
             else "degraded")
    transitions = list(delta.transitions)
    return {
        "state": state,
        "reasons": reasons,
        "pass": block,
        "inputs": {
            "quotes": {"asof": quote_asof,
                       "age_s": (None if asof_ts is None
                                 else round((now - asof_ts).total_seconds(), 1)),
                       "coverage": f"{covered}/{len(probe)}",
                       "stale_n": int(stale_quotes)},
            "pack": {"as_of": pack.as_of, "pack_hash": pack.pack_hash, "fresh": True,
                     "proof_failed": bool(pack.proof_failed)},
            "spool": {"ok": None, "key": None, "error": None},
            "c3_reader": dict(c3_stats),
        },
        "basis": {"audited_n": int(basis_stats.get("audited_n") or 0),
                  "mismatched_n": int(basis_stats.get("mismatched_n") or 0),
                  "unchecked_n": int(basis_stats.get("unchecked_n") or 0),
                  "refused": sorted(basis_stats.get("refused") or [])},
        "dark": dict(dark_counts),
        "null_readings": nulls,
        "content": {
            "last_transition_at": (max((str(t.get("at") or "") for t in transitions),
                                       default=None) or None),
            "events_total": len(delta.events),
            "ledger_hash": _ledger_hash(ledger),
        },
    }


def _empty_priority_board(*, computed_at: str | None, cycle_state: str,
                          reason: str) -> dict[str, Any]:
    return {
        "schema": rp.SCHEMA,
        "policy_version": rp.POLICY_VERSION,
        "status": rp.STATUS,
        "meaning": rp.MEANING,
        "does_not_claim": list(rp.DOES_NOT_CLAIM),
        "computed_at": computed_at,
        "cycle_state": cycle_state,
        "population_n": 0,
        "episodes": [],
        "abstention": reason,
    }


def _state_name(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _confirmed_closes(pack: lp.LivePack, ticker: str, session: date) -> list[float]:
    daily = pack_daily_history(pack, ticker)
    if daily is None:
        return []
    frame = daily.confirmed_through(session)
    if frame is None or getattr(frame, "empty", True):
        return []
    out: list[float] = []
    for value in frame["close"].tolist():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number and number not in (float("inf"), float("-inf")):
            out.append(number)
    return out


def _priority_inputs(*, session: date, pack: lp.LivePack,
                     results: Sequence[NameResult]) -> list[rp.EpisodeInput]:
    """Developing expert observations for RP1, one row per (ticker, detector, variant)."""
    bench = _confirmed_closes(pack, rp.BENCH_TICKER, session) or None
    by_ticker = pack.by_ticker()
    out: list[rp.EpisodeInput] = []
    for result in results:
        pack_name = by_ticker.get(result.ticker)
        latest = result.observations[-1] if result.observations else None
        atr = (latest.atr_prior_confirmed if latest is not None else None)
        if atr is None and pack_name is not None:
            atr = pack_name.atr14_prior_confirmed
        measures = rp.measures_from_history(
            _confirmed_closes(pack, result.ticker, session),
            atr=atr,
            sampled_close=(None if latest is None else latest.sampled_close),
            running_sampled_low=(None if latest is None else latest.running_sampled_low),
            k=(None if latest is None else latest.k),
            d=(None if latest is None else latest.d),
            hist=(None if latest is None else latest.hist),
            bench_closes=bench,
        )
        availability = latest.availability if latest is not None else "unavailable"
        freshness = latest.history_freshness if latest is not None else "unavailable"
        known_at = latest.observed_at if latest is not None else None
        fingerprint = pack_name.substrate_fingerprint if pack_name is not None else None
        refs_base = tuple(
            r for r in (pack.pack_hash, fingerprint) if r)

        def add(*, detector_id: str, variant: str | None, state: str,
                first_armed_at: str | None, candidate_at: str | None,
                last_observed_at: str | None,
                extra_refs: Sequence[str] = ()) -> None:
            out.append(rp.EpisodeInput(
                ticker=result.ticker,
                detector_id=detector_id,
                variant=variant,
                state=state,
                first_armed_at=first_armed_at,
                candidate_at=candidate_at,
                last_observed_at=last_observed_at,
                known_at=known_at or last_observed_at,
                availability=availability,
                history_freshness=freshness,
                name_state="evaluated" if not result.dark else "unavailable",
                name_reasons=tuple(result.reasons),
                evidence_refs=refs_base + tuple(extra_refs),
                pack_hash=pack.pack_hash,
                substrate_fingerprint=fingerprint,
                measures=measures,
            ))

        for run in result.runs:
            for episode in getattr(run, "episodes", ()) or ():
                if not getattr(episode, "first_armed_at", None):
                    continue
                add(detector_id=str(episode.detector_id),
                    variant=getattr(episode, "variant", None),
                    state=_state_name(episode.state),
                    first_armed_at=episode.first_armed_at,
                    candidate_at=episode.candidate_at,
                    last_observed_at=episode.last_observed_at,
                    extra_refs=tuple(getattr(episode, "event_ids", ()) or ()))
        nightly = (result.lanes or {}).get("nightly") or {}
        for lane_key, detector_id in (("g0", G0_DETECTOR_ID), ("c5", C5_DETECTOR_ID)):
            row = nightly.get(lane_key) if isinstance(nightly, Mapping) else None
            if not isinstance(row, Mapping) or row.get("condition_met") is not True:
                continue
            add(detector_id=detector_id, variant=None,
                state="CANDIDATE",
                first_armed_at=str(row.get("observed_at") or known_at or ""),
                candidate_at=str(row.get("observed_at") or known_at or ""),
                last_observed_at=str(row.get("observed_at") or known_at or ""),
                extra_refs=tuple(row.get("evidence_refs") or ()))
    return out


def _research_priority_board(*, now: datetime, session: date, pack: lp.LivePack,
                             results: Sequence[NameResult],
                             health: Mapping[str, Any]) -> dict[str, Any]:
    """Projection-only RP1 board.  Does not write the episode ledger."""
    cycle_state = str(health.get("state") or "live")
    computed_at = _iso(now)
    inputs = _priority_inputs(session=session, pack=pack, results=results)
    return rp.assign(inputs, computed_at=computed_at, cycle_state=cycle_state)


def _priority_lookup(board: Mapping[str, Any]
                     ) -> dict[str, tuple[dict[str, Any], ...]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in board.get("episodes") or []:
        grouped.setdefault(str(row.get("ticker") or ""), []).append(dict(row))
    return {ticker: tuple(rows) for ticker, rows in grouped.items()}


def _payload(*, now: datetime, session: date, pack: lp.LivePack,
             results: Sequence[NameResult], delta: ll.PendingDelta,
             committed: bool, health: Mapping[str, Any]) -> dict[str, Any]:
    """``live/entry_radar.json``.  Mechanical copy only — nothing is composed.

    A name with ANY non-PROBING lane gets full per-lane detail; a pure-probing
    name gets a compact row.  That split is a size budget, not an editorial one:
    the compact row still names its state, its freshness and its basis receipt,
    so a reader can always tell "nothing happening" from "we could not look".

    Withheld transitions are withheld HERE too (PIT-W4-13): a payload that shows
    a transition the ledger refused to admit would be the second source of truth
    the spool-before-consume law exists to prevent.
    """
    board = _research_priority_board(now=now, session=session, pack=pack,
                                     results=results, health=health)
    lookup = _priority_lookup(board)
    rows = [_payload_row(r, lookup.get(r.ticker, ())) for r in results]
    return {
        "schema": SCHEMA_LIVE_PAYLOAD,
        "asof": _iso(now),
        "session": session.isoformat(),
        "pack": {"as_of": pack.as_of, "pack_hash": pack.pack_hash,
                 "price_basis": pack.price_basis,
                 "spec_hashes": dict(pack.spec_hashes)},
        "authority": _authority_block(),
        "names": rows,
        "transitions": [copy.deepcopy(t) for t in delta.transitions] if committed else [],
        "events": [copy.deepcopy(e) for e in delta.events] if committed else [],
        "suppressed": [dict(s) for r in results for s in r.suppressed],
        "health": dict(health),
        "research_priority": board,
    }


def _payload_row(result: NameResult,
                 priorities: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    row: dict[str, Any] = {
        "ticker": result.ticker,
        "state": "evaluated" if not result.dark else "unavailable",
        "reasons": list(result.reasons),
        # THE QUOTE THE TAPE USED (H2).  When the journal refused the pass's
        # point, ``result.quote`` has already been rewritten to the kept one and
        # the rejected point is published beside it rather than in its place.
        "quote": result.quote.to_dict() if result.quote is not None else None,
        "quote_rejected": (dict(result.quote_rejected)
                           if result.quote_rejected else None),
        "basis_audit": dict(result.basis) if result.basis else None,
    }
    if result.dark:
        row["lanes"] = {}
        if priorities:
            row["research_priority"] = [dict(p) for p in priorities]
        return row
    active = _has_active_lane(result)
    row["cross_check"] = dict(result.cross_check) if result.cross_check else None
    if active:
        row["lanes"] = dict(result.lanes)
        latest = result.observations[-1] if result.observations else None
        row["observation"] = observation_to_dict(latest) if latest is not None else None
    else:
        latest = result.observations[-1] if result.observations else None
        row["lanes"] = {"nightly": dict(result.lanes.get("nightly") or {})}
        row["observation"] = ({"availability": latest.availability,
                               "history_freshness": latest.history_freshness,
                               "k": latest.k, "d": latest.d,
                               "sampled_close": latest.sampled_close,
                               "observed_at": latest.observed_at}
                              if latest is not None else None)
    if priorities:
        row["research_priority"] = [dict(p) for p in priorities]
    return row


def _has_active_lane(result: NameResult) -> bool:
    """True when any detector on this name is past PROBING this pass.

    A SUPPRESSED arm counts, and so does a met condition with no episode behind
    it.  ``_gate_arm`` strips the episode from a blocked arm and keeps the
    READINGS on purpose — "dropping the readings too would erase the evidence
    that the rule bit" — but those readings then died at the artifact boundary,
    because an episode-only test sent the row down the compact branch.  The
    served payload is the ONLY durable trace of a suppressed pass: nothing is
    spooled and nothing is committed.
    """
    if result.suppressed:
        return True
    for run in result.runs:
        for episode in getattr(run, "episodes", ()) or ():
            if episode.first_armed_at:
                return True
        for reading in getattr(run, "readings", ()) or ():
            if getattr(reading, "condition_met", None) is True:
                return True
    return False


# ---------------------------------------------------------------------------
# determinism helpers (PIT-W4-9)
# ---------------------------------------------------------------------------

#: Payload paths that legitimately move between two passes of the SAME cycle.
#: Stripping them is how "the content did not change" becomes a statement a
#: machine can make.  ``state_map`` answers the narrower question (are the per-
#: name STATES identical); this answers the wider one, and the two are separate
#: because a re-run legitimately reports no new transitions while its state map
#: is unchanged — see :func:`state_map`.
VOLATILE_PAYLOAD_PATHS: tuple[tuple[str, ...], ...] = (
    ("asof",),
    ("health", "pass", "at"),
    ("health", "pass", "prev_at"),
    ("health", "pass", "seq"),
    ("health", "pass", "evaluated_seq"),
    ("health", "pass", "prev_gap_intervals"),
    ("health", "inputs", "quotes", "age_s"),
    ("health", "inputs", "spool", "key"),
    # The C3 reader's counters move between two runs of the SAME cycle by
    # design: a warm bucket cache turns ``fetched_n`` into ``cache_hits`` on the
    # second run, so a determinism assertion built on them would flake the day
    # C3 is enabled in that test.  The information is not lost — an error or a
    # deferral is already a NAMED health reason, and those stay in the content.
    ("health", "inputs", "c3_reader"),
)


def stable_content(payload: Mapping[str, Any]) -> str:
    """Canonical JSON of the payload with the volatile stamps removed.

    The cadence-gap reason is dropped along with them: it describes the INTERVAL
    BETWEEN passes, not this pass's content, so a pass that ran late would
    otherwise look like a pass that said something different.
    """
    body = json.loads(json.dumps(payload, allow_nan=False, default=str))
    for path in VOLATILE_PAYLOAD_PATHS:
        node: Any = body
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, Mapping) else None
            if node is None:
                break
        if isinstance(node, dict):
            node.pop(path[-1], None)
    health = body.get("health")
    if isinstance(health, dict) and isinstance(health.get("reasons"), list):
        health["reasons"] = sorted(r for r in health["reasons"]
                                   if not str(r).startswith("cadence_gap:"))
    return canonical_json(body)


def emitted_keys(node: Any) -> set[str]:
    """Every key name reachable in a payload/journal/ledger structure.

    Used by the W5 firewall test: the question is not whether a key looks
    reasonable but whether ANY emitted key would require knowing what happened
    after an observation was knowable.
    """
    out: set[str] = set()
    if isinstance(node, Mapping):
        for key, value in node.items():
            out.add(str(key))
            out |= emitted_keys(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            out |= emitted_keys(item)
    return out


def forward_knowledge_keys(node: Any) -> list[str]:
    """Emitted keys matching a forward-knowledge SHAPE.  Empty is the law.

    :data:`FIREWALL_EXEMPT_KEYS` is subtracted by NAME, never by token, so an
    exemption covers exactly the field it was written for — widening a token to
    silence a false positive would silence the true ones beside it.
    """
    found = []
    for key in sorted(emitted_keys(node)):
        if key in FIREWALL_EXEMPT_KEYS:
            continue
        low = key.lower()
        if any(token in low for token in FORBIDDEN_KEY_TOKENS):
            found.append(key)
    return found


def state_map(payload: Mapping[str, Any]) -> str:
    """Canonical JSON of the payload's per-name STATE, with no volatile stamps.

    PIT-W4-9 asks two things of a same-cycle re-run and they are different
    questions: the state map must be byte-identical (the pass is deterministic)
    and the delta must be EMPTY (nothing is admitted twice).  Comparing whole
    payloads conflates them — the second run legitimately reports no new
    transitions, so a whole-payload equality would fail for the very reason the
    test wanted to see.  This is the first question; ``PassResult.delta.empty``
    is the second.
    """
    body = json.loads(json.dumps(payload.get("names") or [], allow_nan=False,
                                 default=str))
    for row in body:
        quote = row.get("quote") if isinstance(row, Mapping) else None
        if isinstance(quote, dict):
            quote.pop("age_min", None)
            quote.pop("ts", None)
    return canonical_json(body)


__all__ = [
    "C3_WARMUP_SESSIONS", "CARRIED_QUOTE_BASES", "CROSS_CHECK_EPSILON_REL",
    "CYCLE_REFUSALS", "FIREWALL_EXEMPT_KEYS", "FORBIDDEN_KEY_TOKENS",
    "C3_MAX_NAMES_PER_PASS", "HEALTH_STATES", "KILL_ENV", "KILL_FILE",
    "NAME_ERROR_REASONS", "NAME_REFUSALS", "PASS_ID", "QUOTE_SLACK_MIN",
    "SCHEMA_JOURNAL",
    "SCHEMA_LIVE_PAYLOAD", "VOLATILE_PAYLOAD_PATHS", "WINDOW_END_GRACE_MIN",
    "IncrementalObservationBuilder", "JournalRecord", "LiveEvalConfig",
    "JournalRefused", "LiveEvalError", "NameResult", "PassResult", "QuotePoint",
    "SessionJournal",
    "cross_check", "emitted_keys", "error_reason", "failure_payload",
    "forward_knowledge_keys", "in_window",
    "interval_bounds", "killed", "observation_from_dict", "observation_to_dict",
    "pack_daily_history", "quote_budget", "read_quote", "run_pass",
    "stable_content", "state_map", "substrate_fingerprint",
]
