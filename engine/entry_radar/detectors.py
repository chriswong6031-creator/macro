"""engine/entry_radar/detectors.py — detector identity + lifecycle types (W2 scope).

WHAT IS HERE
------------
Two things, and deliberately nothing else:

  ``DetectorSpec`` / ``DETECTORS``   a detector's frozen identity — id, version,
                                     grain, bar family, spec constants, and the
                                     ``spec_hash`` those constants imply.
  lifecycle types                    the §13 machine states, the legal
                                     transitions between them, and a validator.

WHAT IS NOT HERE, ON PURPOSE
----------------------------
No evaluator loop and no episode store.  Running detectors against a live tape is
PR-4; the durable episode ledger (`mastermind.live_entry_episode.v1`) is PR-5 and
is the only lane allowed to write ``data/``.  A framework that grows an evaluator
before its detectors are specified acquires exactly one detector's shape.

EXACTLY ONE SPEC IS REGISTERED.  ``G0_GREY_DOT@1`` — the champion, whose spec
block and hash live in ``g0_adapter`` (the code that implements it), so the
registry cannot drift from the implementation: the registered hash IS
``g0_adapter.g0_spec_hash()``, asserted in the W2 guard suite.

RESERVED IDS CARRY NO SPEC.  ``C1..C5`` and ``F1`` are named here so two lanes
cannot mint the same id, and ``get_spec`` on one raises ``NotYetSpecified``
rather than returning a plausible default.  PR-3 locks their constants; a
detector whose spec is a placeholder is a detector whose ``spec_hash`` means
nothing, and ``spec_hash`` is what makes a result attributable later.

LIFECYCLE ≠ PRIORITY (contract §13).  ``detector_state`` is independent of any
score: a priority move from 91 to 63 changes no lifecycle fact.  Nothing in this
module reads or emits a score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from engine.entry_radar.entry_events import EntryEventError, sha16
from engine.entry_radar.g0_adapter import (
    G0_BAR_FAMILY,
    G0_DETECTOR_ID,
    G0_GRAIN,
    G0_SPEC,
    G0_VERSION,
    g0_spec_hash,
)


class DetectorError(EntryEventError):
    """A malformed or unknown detector identity."""


class NotYetSpecified(DetectorError):
    """A reserved detector id with no locked spec.  PR-3 territory."""


class IllegalTransition(DetectorError):
    """A lifecycle transition the §13 machine does not allow."""


@dataclass(frozen=True, slots=True)
class DetectorSpec:
    """A detector's frozen identity.  ``spec_hash`` is derived, never asserted.

    The hash covers ``spec`` alone — the constants that decide what the detector
    FIRES on.  Renaming a detector or bumping its packaging must not change the
    identity of results already attributed to those constants; changing a
    constant must.
    """

    detector_id: str
    version: int
    grain: str
    bar_family: str
    spec: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.detector_id or "").strip():
            raise DetectorError("detector_id is required")
        if int(self.version) < 1:
            raise DetectorError(f"{self.detector_id}: version must be >= 1")
        if not self.spec:
            raise DetectorError(f"{self.detector_id}: a spec with no constants hashes to a "
                                f"constant — an unspecified detector must be RESERVED, "
                                f"never registered")

    @property
    def spec_hash(self) -> str:
        """sha256 over the canonical JSON of ``spec``, first 16 hex.  Stable per run."""
        return sha16(self.spec)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector_id": self.detector_id,
            "version": self.version,
            "grain": self.grain,
            "bar_family": self.bar_family,
            "spec_hash": self.spec_hash,
            "spec": dict(self.spec),
        }


G0_SPEC_RECORD = DetectorSpec(
    detector_id=G0_DETECTOR_ID,
    version=G0_VERSION,
    grain=G0_GRAIN,
    bar_family=G0_BAR_FAMILY,
    spec=G0_SPEC,
)

#: The registry.  Exactly one entry in W2.
DETECTORS: dict[str, DetectorSpec] = {G0_SPEC_RECORD.detector_id: G0_SPEC_RECORD}

#: Names only — no specs, no constants, no defaults (PR-3 locks them).
RESERVED_DETECTOR_IDS: tuple[str, ...] = (
    "C1_1D_LIVE_WASHOUT",
    "C2_1D_TURN",
    "C3_1D_4H_RECOVERY",
    "C4_MTF_TURN",
    "C5_BOTTOM_WATCH",
    "F1_FUSION",
)


def get_spec(detector_id: str) -> DetectorSpec:
    """The registered spec, or a refusal that names WHY it is missing."""
    got = DETECTORS.get(detector_id)
    if got is not None:
        return got
    if detector_id in RESERVED_DETECTOR_IDS:
        raise NotYetSpecified(
            f"{detector_id} is a RESERVED id with no locked spec — PR-3 locks its "
            f"constants.  A placeholder spec would produce a spec_hash that means "
            f"nothing, and spec_hash is what makes a result attributable later")
    raise DetectorError(f"unknown detector_id {detector_id!r}; registered "
                        f"{sorted(DETECTORS)}, reserved {list(RESERVED_DETECTOR_IDS)}")


# ---------------------------------------------------------------------------
# lifecycle (contract §13)
# ---------------------------------------------------------------------------

class DetectorState(str, Enum):
    """Machine lifecycle per ``(ticker, detector)``.  History-preserving.

    User-facing simplification is Probing / Pre-candidate / Candidate — the
    machine keeps the full set, because a candidate that left today's board still
    exists in the ledger forever.
    """

    PROBING = "PROBING"
    ARMED = "ARMED"
    TURNING = "TURNING"
    CANDIDATE = "CANDIDATE"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    RESOLVED = "RESOLVED"


TERMINAL_STATES: frozenset[DetectorState] = frozenset({
    DetectorState.INVALIDATED, DetectorState.EXPIRED, DetectorState.RESOLVED,
})

#: FROZEN — §13.  Terminal states have NO exits: a resolved episode that could be
#: re-armed in place would silently rewrite its own history.
ALLOWED_TRANSITIONS: dict[DetectorState, frozenset[DetectorState]] = {
    DetectorState.PROBING: frozenset({DetectorState.ARMED}),
    DetectorState.ARMED: frozenset({
        DetectorState.TURNING, DetectorState.CANDIDATE, DetectorState.EXPIRED,
        DetectorState.PROBING,
    }),
    DetectorState.TURNING: frozenset({
        DetectorState.CANDIDATE, DetectorState.INVALIDATED, DetectorState.EXPIRED,
        DetectorState.ARMED,
    }),
    DetectorState.CANDIDATE: frozenset({
        DetectorState.INVALIDATED, DetectorState.EXPIRED, DetectorState.RESOLVED,
    }),
    DetectorState.INVALIDATED: frozenset(),
    DetectorState.EXPIRED: frozenset(),
    DetectorState.RESOLVED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class TransitionRecord:
    """One lifecycle move, with the evidence that justified it.

    ``evidence_refs`` holds ``event_id``s (§13): a state change with no event
    behind it is an assertion, and an append-only ledger of assertions is not a
    ledger.
    """

    ticker: str
    detector_id: str
    from_state: DetectorState
    to_state: DetectorState
    at: str
    reason: str = ""
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_transition(self.from_state, self.to_state)
        if not str(self.ticker or "").strip():
            raise DetectorError("transition requires a ticker")
        if not str(self.at or "").strip():
            raise DetectorError("transition requires a timestamp")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "detector_id": self.detector_id,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "at": self.at,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
        }


def validate_transition(from_state: DetectorState, to_state: DetectorState) -> None:
    """Raise ``IllegalTransition`` unless §13 allows the move."""
    if from_state not in ALLOWED_TRANSITIONS:
        raise IllegalTransition(f"unknown state {from_state!r}")
    if to_state not in ALLOWED_TRANSITIONS:
        raise IllegalTransition(f"unknown state {to_state!r}")
    allowed = ALLOWED_TRANSITIONS[from_state]
    if to_state not in allowed:
        detail = ("it is TERMINAL" if from_state in TERMINAL_STATES
                  else f"legal exits are {sorted(s.value for s in allowed)}")
        raise IllegalTransition(
            f"{from_state.value} → {to_state.value} is not a §13 transition: {detail}")


def assert_g0_registry_matches_implementation() -> None:
    """The registered G0 hash IS the implementation's hash, or this raises.

    A registry that can disagree with the code it describes is a second source of
    truth for the same fact.
    """
    registered = DETECTORS[G0_DETECTOR_ID].spec_hash
    implemented = g0_spec_hash()
    if registered != implemented:
        raise DetectorError(
            f"G0 spec_hash drift: registry {registered} != g0_adapter {implemented}")
