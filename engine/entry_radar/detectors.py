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

SIX SPECS ARE REGISTERED (W2's champion + W3's five challengers).  Every spec
block and its hash live in the module that IMPLEMENTS the detector — ``g0_adapter``
for G0, ``challengers`` for C1/C2/C4, ``four_hour`` for C3, ``c5_adapter`` for C5 —
so the registry cannot drift from the code it describes: each registered hash IS
that module's own ``*_spec_hash()``, asserted by
``assert_registry_matches_implementations``.  The import direction is one-way
(registry reads implementation), which is why ``challengers`` reaches the §13
lifecycle through a deferred import rather than a module-level one.

ONE RESERVED ID REMAINS.  ``F1_FUSION`` is named here so two lanes cannot mint it,
and ``get_spec("F1_FUSION")`` raises ``NotYetSpecified`` rather than returning a
plausible default.  §4 is explicit that F1 is **not in V1** and is registered only
after individual detector results exist — a fusion detector specified before its
inputs have been measured is champion by definition, which is exactly what the
contract forbids.  A detector whose spec is a placeholder is a detector whose
``spec_hash`` means nothing, and ``spec_hash`` is what makes a result attributable
later.

C4 IS REGISTERED AND CANNOT FIRE.  ``C4_MTF_TURN@1`` carries
``role=stratification_only`` in its spec; it has no entry-event family and
``challengers.assert_can_fire`` refuses it.  Registration records its identity for
later stratification; it grants nothing (`DNR:KILL-WASHOUT-TURN`).

LIFECYCLE ≠ PRIORITY (contract §13).  ``detector_state`` is independent of any
score: a priority move from 91 to 63 changes no lifecycle fact.  Nothing in this
module reads or emits a score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from engine.entry_radar.c5_adapter import (
    C5_BAR_FAMILY,
    C5_DETECTOR_ID,
    C5_GRAIN,
    C5_SPEC,
    C5_VERSION,
    c5_spec_hash,
)
from engine.entry_radar.challengers import (
    C1_BAR_FAMILY,
    C1_DETECTOR_ID,
    C1_GRAIN,
    C1_SPEC,
    C1_VERSION,
    C2_BAR_FAMILY,
    C2_DETECTOR_ID,
    C2_GRAIN,
    C2_SPEC,
    C2_VERSION,
    C4_BAR_FAMILY,
    C4_DETECTOR_ID,
    C4_GRAIN,
    C4_SPEC,
    C4_VERSION,
    c1_spec_hash,
    c2_spec_hash,
    c4_spec_hash,
)
from engine.entry_radar.entry_events import EntryEventError, sha16
from engine.entry_radar.four_hour import (
    C3_BAR_FAMILY,
    C3_DETECTOR_ID,
    C3_GRAIN,
    C3_SPEC,
    C3_VERSION,
    c3_spec_hash,
)
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

C1_SPEC_RECORD = DetectorSpec(detector_id=C1_DETECTOR_ID, version=C1_VERSION,
                              grain=C1_GRAIN, bar_family=C1_BAR_FAMILY, spec=C1_SPEC)
C2_SPEC_RECORD = DetectorSpec(detector_id=C2_DETECTOR_ID, version=C2_VERSION,
                              grain=C2_GRAIN, bar_family=C2_BAR_FAMILY, spec=C2_SPEC)
C3_SPEC_RECORD = DetectorSpec(detector_id=C3_DETECTOR_ID, version=C3_VERSION,
                              grain=C3_GRAIN, bar_family=C3_BAR_FAMILY, spec=C3_SPEC)
C4_SPEC_RECORD = DetectorSpec(detector_id=C4_DETECTOR_ID, version=C4_VERSION,
                              grain=C4_GRAIN, bar_family=C4_BAR_FAMILY, spec=C4_SPEC)
C5_SPEC_RECORD = DetectorSpec(detector_id=C5_DETECTOR_ID, version=C5_VERSION,
                              grain=C5_GRAIN, bar_family=C5_BAR_FAMILY, spec=C5_SPEC)

#: The registry.  Champion + the five W3 challengers.
DETECTORS: dict[str, DetectorSpec] = {
    record.detector_id: record for record in (
        G0_SPEC_RECORD, C1_SPEC_RECORD, C2_SPEC_RECORD, C3_SPEC_RECORD,
        C4_SPEC_RECORD, C5_SPEC_RECORD,
    )
}

#: Name only — no spec, no constants, no defaults.  §4: F1 is NOT in V1 and is
#: registered only after individual detector results exist.
RESERVED_DETECTOR_IDS: tuple[str, ...] = ("F1_FUSION",)

#: Registered id -> the ``*_spec_hash()`` of the module that implements it.  Held
#: as data so ``assert_registry_matches_implementations`` cannot go vacuous by
#: forgetting a detector: the check iterates the REGISTRY and demands an entry
#: here for every member.
IMPLEMENTATION_HASHES = {
    G0_DETECTOR_ID: g0_spec_hash,
    C1_DETECTOR_ID: c1_spec_hash,
    C2_DETECTOR_ID: c2_spec_hash,
    C3_DETECTOR_ID: c3_spec_hash,
    C4_DETECTOR_ID: c4_spec_hash,
    C5_DETECTOR_ID: c5_spec_hash,
}

#: Detectors registered ``role=stratification_only`` — read from the SPEC blocks,
#: never restated, so the registry's view and the implementation's fence agree by
#: construction (`DNR:KILL-WASHOUT-TURN`, contract §18 A5.5).
STRATIFICATION_ONLY: tuple[str, ...] = tuple(
    sorted(did for did, record in DETECTORS.items()
           if record.spec.get("role") == "stratification_only"))


def get_spec(detector_id: str) -> DetectorSpec:
    """The registered spec, or a refusal that names WHY it is missing."""
    got = DETECTORS.get(detector_id)
    if got is not None:
        return got
    if detector_id in RESERVED_DETECTOR_IDS:
        raise NotYetSpecified(
            f"{detector_id} is a RESERVED id with no locked spec.  §4: F1 is NOT in "
            f"V1 — it is registered only after G0/C1/C2/C3/C5 have independent-"
            f"information results, and never champion by definition.  A placeholder "
            f"spec would produce a spec_hash that means nothing, and spec_hash is "
            f"what makes a result attributable later")
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


def assert_registry_matches_implementations() -> None:
    """EVERY registered detector's hash IS its implementing module's hash.

    Iterates the REGISTRY, not the hash table, so adding a detector without
    wiring its ``*_spec_hash()`` is a loud failure rather than a silent gap — the
    shape a "check the ones we remembered" guard degrades into.
    """
    for detector_id, record in sorted(DETECTORS.items()):
        implementation = IMPLEMENTATION_HASHES.get(detector_id)
        if implementation is None:
            raise DetectorError(
                f"{detector_id} is registered but names no implementing "
                f"*_spec_hash(); a registry entry nobody can cross-check is a second "
                f"source of truth for the detector's identity")
        if record.spec_hash != implementation():
            raise DetectorError(
                f"{detector_id} spec_hash drift: registry {record.spec_hash} != "
                f"implementation {implementation()}")
