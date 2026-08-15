"""engine/entry_radar/readings.py — `mastermind.entry_detector_reading.v1`.

WHAT THIS IS (contract §18 A5.0)
--------------------------------
The ONE ephemeral record C1–C4 evaluate through.  It is a **computation
contract**, not an evidence store: a reading says what a detector saw at one
timestamp, on which bar, with what availability, and whether its condition was
met.  Episodes and events are elsewhere (`entry_events.py`, §13); outcomes are
PR-5's and exist nowhere in W3.

NO PERSISTENCE OF ANY KIND.  No file, no SQLite, no R2, no ``data/`` writer, no
ledger, no cache.  A reading is produced, read, and discarded.  W3's whole
durable footprint is zero, and the cheapest way to guarantee that is for the
record type itself to own no writer.

THE NULL LAW, MADE STRUCTURAL (§18 A5.0)
-----------------------------------------
``unavailable`` ≠ ``False``.  A missing bar is not evidence that a detector did
not fire, and a store that writes ``condition_met=False`` for an input it never
had will later be counted as a measured non-fire.  So the constructor REFUSES
``condition_met`` other than ``None`` when ``availability == "unavailable"``.
The three-valued field is the whole point of the record.

AUTHORITY IS ALL-FALSE, AT CONSTRUCTION (contract §2)
------------------------------------------------------
Every reading carries the DRL display-tier block and the constructor refuses a
truthy value in it.  A reading cannot rank, size, gate, originate a signal, or
escalate — it can only describe.

NO DETECTOR SCORE (§18 A5.0, §9)
---------------------------------
``features`` may not carry a key that reads as a strength number.  W3 outputs
mechanisms, features, state, provenance and availability; the hand-authored
0–100 number is PR-6/PR-7 territory and its absence here is enforced by
``BANNED_FEATURE_TOKENS`` rather than by good intentions.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field, fields
from typing import Any, Mapping

from engine.entry_radar.contracts import AUTHORITY_BLOCK, AVAILABILITY_STATES
from engine.entry_radar.entry_events import BAR_STATES, canonical_json

SCHEMA_DETECTOR_READING = "mastermind.entry_detector_reading.v1"

#: FROZEN — contract §18 A5.0, in the amendment's own order.
READING_FIELDS: tuple[str, ...] = (
    "schema",
    "ticker",
    "detector_id",
    "detector_version",
    "detector_spec_hash",
    "variant",
    "observed_at",
    "market_session",
    "availability",
    "source_bar_time",
    "source_bar_known_at",
    "bar_state",
    "data_vintage",
    "features",
    "condition_met",
    "evidence_refs",
    "authority",
)

#: Availability states that REQUIRE ``condition_met=None``.  ``stale`` joined
#: ``unavailable`` at W3-5: both describe an input that cannot support a current
#: verdict, and the difference between them (we could not look / we looked at an
#: old world) is a provenance fact, not a licence to publish a boolean.
_NULL_REQUIRED_AVAILABILITY: frozenset[str] = frozenset({"unavailable", "stale"})

#: Substrings a ``features`` key may never contain.  Narrower than
#: ``contracts.BANNED_RECORD_TOKENS`` on purpose: a reading legitimately carries
#: counts and levels (``recovery_count``, ``k``, ``running_sampled_low``); what it
#: may never carry is a number asserting how GOOD the setup is.
BANNED_FEATURE_TOKENS: tuple[str, ...] = (
    "score", "points", "strength", "grade", "conviction", "probability",
    "priority", "opportunity",
)


class ReadingError(ValueError):
    """A record that violates `mastermind.entry_detector_reading.v1`."""


@dataclass(frozen=True, slots=True, kw_only=True)
class DetectorReading:
    """One detector's point-in-time reading.  Field list per §18 A5.0.

    ``variant`` is ``None`` for single-mechanism detectors and the registered
    variant key for C2 — the six variants are six mechanistically distinct
    experts and are never deduped into one generic "C2 read" (§18 A5.3).

    ``source_bar_time`` / ``source_bar_known_at`` are the §5 pair: WHICH bar the
    value came from, and WHEN that bar became knowable.  They are different
    questions and a detector that records only the first cannot be leak-tested.
    """

    ticker: str
    detector_id: str
    detector_version: int
    detector_spec_hash: str
    observed_at: str
    market_session: str
    availability: str
    bar_state: str
    variant: str | None = None
    source_bar_time: str | None = None
    source_bar_known_at: str | None = None
    data_vintage: str | None = None
    features: dict[str, Any] = field(default_factory=dict)
    condition_met: bool | None = None
    evidence_refs: tuple[str, ...] = ()
    authority: dict[str, bool] = field(default_factory=lambda: dict(AUTHORITY_BLOCK))

    schema: str = SCHEMA_DETECTOR_READING

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", copy.deepcopy(dict(self.features)))
        object.__setattr__(self, "authority", dict(self.authority))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        self._validate()

    def _validate(self) -> None:
        if self.schema != SCHEMA_DETECTOR_READING:
            raise ReadingError(f"schema {self.schema!r} is not {SCHEMA_DETECTOR_READING!r}")
        for name in ("ticker", "detector_id", "detector_spec_hash", "observed_at",
                     "market_session"):
            if not str(getattr(self, name) or "").strip():
                raise ReadingError(f"{name} is required on every reading")
        if int(self.detector_version) < 1:
            raise ReadingError(f"{self.detector_id}: detector_version must be >= 1")
        if self.availability not in AVAILABILITY_STATES:
            raise ReadingError(f"availability {self.availability!r} not in "
                               f"{sorted(AVAILABILITY_STATES)} — §5 vocabulary is closed")
        if self.bar_state not in BAR_STATES:
            raise ReadingError(f"bar_state {self.bar_state!r} not in {sorted(BAR_STATES)}")
        if self.condition_met not in (True, False, None):
            raise ReadingError(f"condition_met {self.condition_met!r} is not tri-state "
                               f"(True | False | None)")
        # --- the null law (§18 A5.0), structural ---
        #
        # W3-5 widened this from `unavailable` to `unavailable | stale`.  Same
        # rationale, one step further: a STALE input is a real reading of an old
        # world, and a verdict computed from it would be a current-sounding claim
        # about a tape nobody has seen since.  §7 demotes stale inputs visibly and
        # #5555's law forbids acting off a stale frame — so stale carries no
        # boolean at all rather than a boolean with an asterisk.
        if self.availability in _NULL_REQUIRED_AVAILABILITY and \
                self.condition_met is not None:
            raise ReadingError(
                f"{self.detector_id}{'/' + self.variant if self.variant else ''} for "
                f"{self.ticker} at {self.observed_at} reports condition_met="
                f"{self.condition_met!r} on an {self.availability.upper()} input; "
                f"`{self.availability}` is not `false` — a missing or aged bar is not "
                f"evidence the detector did not fire (contract §18 A5.0 null law, §7 "
                f"stale demotion)")
        bad = sorted(k for k in self.features
                     if any(tok in str(k).lower() for tok in BANNED_FEATURE_TOKENS))
        if bad:
            raise ReadingError(
                f"feature key(s) {bad} read as a strength/priority number; W3 outputs "
                f"mechanisms, features, state and availability — the hand-authored "
                f"0-100 number is PR-6/PR-7 territory (contract §18 A5.0)")
        self._validate_authority()

    def _validate_authority(self) -> None:
        if set(self.authority) != set(AUTHORITY_BLOCK):
            raise ReadingError(
                f"authority block keys {sorted(self.authority)} != "
                f"{sorted(AUTHORITY_BLOCK)} — the display-tier block is exact")
        granted = sorted(k for k, v in self.authority.items() if v)
        if granted:
            raise ReadingError(
                f"reading for {self.ticker} claims authority {granted}; every "
                f"`{SCHEMA_DETECTOR_READING}` record is display/research tier and its "
                f"authority block is all-false (contract §2)")

    # -- serialisation ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form.  Key order and key set are exactly ``READING_FIELDS``."""
        out: dict[str, Any] = {}
        for name in READING_FIELDS:
            value = getattr(self, name)
            if isinstance(value, dict):
                value = copy.deepcopy(value)
            elif isinstance(value, tuple):
                value = list(value)
            out[name] = value
        return out

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> DetectorReading:
        unknown = set(raw) - set(READING_FIELDS)
        if unknown:
            raise ReadingError(f"unknown reading field(s) {sorted(unknown)} — the v1 "
                               f"field list is frozen at {list(READING_FIELDS)}")
        kwargs = {k: raw[k] for k in READING_FIELDS if k in raw}
        if "evidence_refs" in kwargs and kwargs["evidence_refs"] is not None:
            kwargs["evidence_refs"] = tuple(kwargs["evidence_refs"])
        return cls(**kwargs)  # type: ignore[arg-type]

    @property
    def canonical(self) -> str:
        """Deterministic JSON — the byte-comparison form every PIT test diffs."""
        return canonical_json(self.to_dict())


def reading_dataclass_fields() -> tuple[str, ...]:
    """The dataclass's own field names — asserted to cover ``READING_FIELDS``."""
    return tuple(f.name for f in fields(DetectorReading))


def canonical_readings(readings: Any) -> str:
    """Canonical JSON for an ordered collection of readings.

    Used by every PIT mutation test: "byte-identical" is only a meaningful claim
    against a canonical serialisation, and a test that compares repr() would pass
    through a dict-ordering change that a consumer would see.
    """
    return json.dumps([json.loads(r.canonical) for r in readings],
                      sort_keys=True, separators=(",", ":"))
