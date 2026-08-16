"""engine/entry_radar/entry_events.py — the append-only `mastermind.entry_event.v1` store.

WHAT THIS IS (contract §18 A1.2.1, §13)
--------------------------------------
The addressable, append-only record of every entry event Radar has *observed* —
Terminal's recorded expert families today, Radar's own detector families from
PR-3.  Episodes (§13) reference ``event_id``; nothing here scores, ranks, or
gates anything.

APPEND-ONLY IS STRUCTURAL, NOT EDITORIAL.  ``EntryEventStore`` has no update,
no delete, no remove, and no pop — of any kind, under any name.  A re-read that
produces identical content is idempotent; a re-read that produces DIFFERENT
content under the same ``event_id`` raises ``AppendOnlyViolation`` rather than
overwriting, because a store that silently accepts the second version cannot
answer "what did we know on the day".

NO FLATTENING (contract §18 A1.2)
---------------------------------
``FORBIDDEN_FAMILY_KEYS`` refuses the collapse this program exists to prevent:
no ``entry_signal`` boolean, no generic ``buy``/``candidate``/``golden_oracle``
bucket, and — deliberately — no ``early`` / ``starter`` / ``re_entry`` either.
Those last three are the operator's UI labels (A4.3 resolves them: "STARTER" is
the alerts/UI rendering of BUY/REBUY with quality ``block``/``pending``,
"RE-ENTRY" is RECLAIM/``reclaim`` or ``block_repair`` — and the UI list missed a
third live RECLAIM family entirely).  **The producer's enum wins over the UI
label**, always: a store keyed on labels inherits the label's blind spots.

AUTHORITY IS ALL-FALSE, AT CONSTRUCTION (contract §2)
-----------------------------------------------------
Every event carries the DRL display-tier block and the constructor REFUSES a
truthy value in it.  ``scored_authority`` records what the *emitter* said about
its own scoring (Terminal's ``scored: false``) — a recorded fact about someone
else's artifact, never a grant to Radar.

FIELD ORIGIN (contract §18 A1.2.1)
----------------------------------
Every event says, per field, whether the value came from the emitter verbatim,
was derived by Radar, or is absent from the artifact.  The third value matters
most: A4.5 forbids reconstructing a ``known_ts`` for the bare-date-string
``early_dots`` side channel, so those events say ``artifact_absent`` and mean it.
A reconstructed ``known_ts`` there would be the §3.2 fallback recomputation
smuggled in as provenance.

WRITE DISCIPLINE (contract §7.3)
--------------------------------
This module writes NO ``data/`` path and holds no durable writer at all.  W2 is
an in-memory + JSONL-string store; the nightly reconciler of PR-5 is the only
durable ``data/`` writer and is gated by
``engine/ledger_lane.py::nightly_advance_enabled()`` — which is why nothing here
imports ``ledger_lane``: a module that cannot reach the gate cannot bypass it.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field, fields
from typing import Any, Iterable, Mapping

from engine.entry_radar.contracts import AUTHORITY_BLOCK

SCHEMA_ENTRY_EVENT = "mastermind.entry_event.v1"

#: Radar's OWN producer id — W3's Radar-native families are emitted by this
#: package, not read from an artifact, and the distinction must be visible on the
#: event.  ``producer`` is what tells a later reader whether a row is Terminal's
#: observation or Radar's own.
RADAR_PRODUCER = "radar.entry_radar"

#: Radar's native signal era.  Rides the event ADDRESS (``compute_event_id``), so
#: a future Radar era can never pool with this one by accident.
RADAR_SIGNAL_ERA = "radar_w3_a5"

#: The spec-era fence for every Radar-native family (contract §18 A5.8).  These
#: families did NOT exist live before W3/W4, and the honest receipt is an ERA, not
#: a manufactured live-emission date: a dated value here would let a consumer read
#: "no radar_1d_turn events in 2019" as a fact about the market.
RADAR_SPEC_ERA_FENCE = "2026-08-14 contract §18 A5"

#: FROZEN — the exact six C2 variants of contract §18 A5.3, in the amendment's
#: order.  Defined HERE, at the schema root, and re-exported as
#: ``challengers.C2_VARIANTS`` so the enum has exactly one source: a subtype set
#: and a variant list that can drift are two facts pretending to be one.
RADAR_1D_TURN_SUBTYPES: tuple[str, ...] = (
    "c2a_kd_cross",
    "c2b_k_slope",
    "c2c_higher_k_low",
    "c2d_hist_trough",
    "c2e_hist_curvature",
    "c2f_rebound_atr",
)

RADAR_1D_LIVE_WASHOUT_SUBTYPE = "live_k_lt_20"
RADAR_4H_RECOVERY_SUBTYPE = "confirmed_4h_hist_trough"

#: FROZEN — minted from emitter receipts at contract §18 A4.3 (the first six),
#: extended by contract §18 A5.8 (the last three, Radar-native).  ``grey_dot`` is
#: the raw anticipation dot (§3.1 mask); the two ``washout_*`` keys are the
#: BOTTOM_WATCH subtypes; the three ``oracle_*`` keys are the keeper/reclaim
#: verdict streams, whose ``subtype`` is the emitter's own quality string
#: verbatim; the three ``radar_*`` keys are C1/C2/C3.
#:
#: C4 IS ABSENT ON PURPOSE.  ``C4_MTF_TURN@1`` is registered
#: ``role=stratification_only`` and gets no family at all, so it cannot address an
#: event — `DNR:KILL-WASHOUT-TURN` enforced by schema rather than by convention.
#: C5 mints nothing either: it REFERENCES the preserved Terminal watch events
#: (A5.6) instead of duplicating the market observation under a second id.
FAMILY_KEYS: tuple[str, ...] = (
    "grey_dot",
    "washout_early_watch",
    "washout_trigger_watch",
    "oracle_buy",
    "oracle_rebuy",
    "oracle_reclaim",
    "radar_1d_live_washout",
    "radar_1d_turn",
    "radar_1d_4h_recovery",
)

#: The Radar-native families and their closed subtype sets (§18 A5.8).
RADAR_NATIVE_SUBTYPES: dict[str, frozenset[str]] = {
    "radar_1d_live_washout": frozenset({RADAR_1D_LIVE_WASHOUT_SUBTYPE}),
    "radar_1d_turn": frozenset(RADAR_1D_TURN_SUBTYPES),
    "radar_1d_4h_recovery": frozenset({RADAR_4H_RECOVERY_SUBTYPE}),
}

RADAR_NATIVE_FAMILIES: tuple[str, ...] = tuple(RADAR_NATIVE_SUBTYPES)

#: THE list of detectors that may never emit.  Held HERE — at the schema root,
#: where every event door already passes — so there is exactly one of it:
#: ``challengers.assert_can_fire`` consumes this tuple rather than keeping a
#: second copy derived from its own spec blocks.
#:
#: W3-7: family-level refusal was not enough.  ``C4_MTF_TURN@1`` under a LAWFUL
#: family (``radar_1d_turn``) walked straight through both the builder and the
#: direct ``EntryEvent`` constructor, so the `DNR:KILL-WASHOUT-TURN` fence held
#: only for the one shape nobody would try.  The refusal is now on the
#: ``detector_id``, at construction, where no door can route around it.
STRATIFICATION_ONLY_DETECTOR_IDS: tuple[str, ...] = ("C4_MTF_TURN@1",)

#: FROZEN — the collapses A1.2 forbids.  The first four are flattenings (a
#: family that dissolves the distinction it was recorded to preserve); the last
#: three are UI labels masquerading as producer enums (A4.3).
FORBIDDEN_FAMILY_KEYS: frozenset[str] = frozenset({
    "entry_signal",
    "buy",
    "candidate",
    "golden_oracle",
    "early",
    "starter",
    "re_entry",
})

#: Emitter quality strings per oracle family (A4.3).  Held as data so a future
#: quality arriving on the tape fails LOUDLY here rather than landing untyped.
ORACLE_SUBTYPES: dict[str, frozenset[str]] = {
    "oracle_buy": frozenset({
        "take", "block", "pending", "override_take", "reclaim_override_take",
        "regime_blocked",
    }),
    "oracle_rebuy": frozenset({
        "take", "block", "pending", "override_take", "reclaim_override_take",
        "regime_blocked",
    }),
    "oracle_reclaim": frozenset({"reclaim", "block_repair", "stop_sweep_reclaim"}),
}

WATCH_SUBTYPES: dict[str, str] = {
    "washout_early_watch": "early_dot",
    "washout_trigger_watch": "blocked_trigger",
}

#: FROZEN — what KIND of first-availability a receipt states.  A bare string is
#: ambiguous in a way that matters: "2026-08-11" for the watch families dates the
#: birth of the ARTIFACT CHANNEL (the family was computable long before), while
#: "2026-07-16" for `reclaim` dates a SCORED PROMOTION (it was emitted
#: display-tier before that), and "pre_fence" is not a date at all.  A consumer
#: that cannot tell those apart will read one as the other.
FIRST_AVAILABLE_KINDS: frozenset[str] = frozenset({
    "artifact_channel_birth",   # the emitted channel began; the mask is older
    "quality_string_birth",     # the quality STRING began; the phenomenon is older
    "scored_promotion",         # emitted earlier, promoted to scored on this date
    "era_fence",                # bounded by an era, not by a calendar date
    "unrecorded",               # A4.3 minted no receipt — absence, recorded
})

#: Kinds whose ``value`` STARTS with an ISO date, so a ``signal_ts`` can be
#: compared against it.  ``era_fence`` and ``unrecorded`` are deliberately absent:
#: an era is not a date, and an absent receipt cannot bound anything.
DATED_FIRST_AVAILABLE_KINDS: frozenset[str] = frozenset({
    "artifact_channel_birth", "quality_string_birth", "scored_promotion",
})

#: The honest landing for a (family, subtype) whose receipt was NOT minted at
#: A4.3.  Absence of a receipt is recorded as absence — never silently promoted
#: to ``pre_fence``, which would invent history for a family we never dated.
FIRST_AVAILABLE_UNRECORDED: dict[str, Any] = {"kind": "unrecorded", "value": None}

#: FROZEN — contract §18 A4.3 + `research/live_entry_radar/W2_G0_PARITY_RECEIPTS.md`
#: §6, keyed by ``(family, subtype)``.  Without this field a downstream program
#: reads STRUCTURAL ABSENCE as negative evidence: the amber-EARLY family has zero
#: history before Terminal `935389d4` (#392, 2026-08-11), so "no watch events in
#: 2019" is a fact about the emitter, not about the market.
FAMILY_FIRST_AVAILABLE: dict[tuple[str, str | None], dict[str, Any]] = {
    # Artifact channel born with #392 `935389d4` (2026-08-11).  The grey MASK is
    # older and Class R from bars (§6) — this dates the ARTIFACT, not the mask.
    ("grey_dot", None): {"kind": "artifact_channel_birth", "value": "2026-08-11"},
    ("washout_early_watch", "early_dot"): {"kind": "artifact_channel_birth",
                                           "value": "2026-08-11"},
    ("washout_trigger_watch", "blocked_trigger"): {"kind": "artifact_channel_birth",
                                                   "value": "2026-08-11"},
    # Keeper verdicts predate the era fence; `SIGNAL_ERA_PRE` slices exist in the
    # wild, which is exactly why pooling across eras is refused at ingest.
    ("oracle_buy", "take"): {"kind": "era_fence", "value": "pre_fence"},
    ("oracle_buy", "block"): {"kind": "era_fence", "value": "pre_fence"},
    ("oracle_buy", "pending"): {"kind": "era_fence", "value": "pre_fence"},
    ("oracle_rebuy", "take"): {"kind": "era_fence", "value": "pre_fence"},
    ("oracle_rebuy", "block"): {"kind": "era_fence", "value": "pre_fence"},
    ("oracle_rebuy", "pending"): {"kind": "era_fence", "value": "pre_fence"},
    # The QUALITY STRING is born with HK-O1 (#365, `7e49bade`, 2026-08-08:
    # `BLOCKED_QUALITY = "regime_blocked"` at contracts.py:70).  The PHENOMENON
    # (regime-vetoed fires) predates it — pre-HK-O1 slices render those fires as
    # unlabeled BUY/REBUY markers, so absence of the string before 2026-08-08 is
    # a fact about the emitter, not about the regime.
    ("oracle_buy", "regime_blocked"): {"kind": "quality_string_birth",
                                       "value": "2026-08-08 (HK-O1 #365, 7e49bade)"},
    ("oracle_rebuy", "regime_blocked"): {"kind": "quality_string_birth",
                                         "value": "2026-08-08 (HK-O1 #365, 7e49bade)"},
    # Prospective-only families: gate-state dependent, zero invented history.
    ("oracle_buy", "override_take"): {"kind": "era_fence",
                                      "value": "gc_v2_wo1 (07244dff)"},
    ("oracle_rebuy", "override_take"): {"kind": "era_fence",
                                        "value": "gc_v2_wo1 (07244dff)"},
    ("oracle_buy", "reclaim_override_take"): {"kind": "era_fence",
                                              "value": "gc_v2_wo2 (e152fd85)"},
    ("oracle_rebuy", "reclaim_override_take"): {"kind": "era_fence",
                                                "value": "gc_v2_wo2 (e152fd85)"},
    ("oracle_reclaim", "reclaim"): {"kind": "scored_promotion", "value": "2026-07-16"},
    ("oracle_reclaim", "block_repair"): {"kind": "scored_promotion",
                                         "value": "2026-07-16"},
    ("oracle_reclaim", "stop_sweep_reclaim"): {"kind": "unrecorded", "value": None},
    # Radar-native families (§18 A5.8).  An ERA FENCE, never a date: these
    # families have no live history before W3/W4 and inventing one would let a
    # consumer read Radar's own birth as market evidence.  ``era_fence`` is
    # undated by construction, so `is_pre_channel_reconstruction` correctly
    # refuses to put any of these events on the wrong side of a line nobody drew.
    ("radar_1d_live_washout", RADAR_1D_LIVE_WASHOUT_SUBTYPE): {
        "kind": "era_fence", "value": RADAR_SPEC_ERA_FENCE},
    ("radar_1d_4h_recovery", RADAR_4H_RECOVERY_SUBTYPE): {
        "kind": "era_fence", "value": RADAR_SPEC_ERA_FENCE},
    **{("radar_1d_turn", _variant): {"kind": "era_fence", "value": RADAR_SPEC_ERA_FENCE}
       for _variant in RADAR_1D_TURN_SUBTYPES},
}

FIELD_ORIGINS: frozenset[str] = frozenset({
    "emitter_verbatim", "radar_derived", "artifact_absent",
})

BAR_STATES: frozenset[str] = frozenset({"confirmed", "provisional"})

#: FROZEN, with their SUBJECT CONVENTIONS — an edge is directional and the
#: direction is the fact.  Both are stated here, at the definition, because an
#: edge read backwards inverts what happened:
#:
#:   ``promoted_by``          source = the promoted WATCH event
#:                            target = the origin GREY_DOT event
#:                            ("this watch is the promotion of that dot")
#:   ``dedup_suppressed_by``  source = the suppressed GREY_DOT event
#:                            target = the suppressing BLOCKED_TRIGGER watch
#:                            ("this dot's marker yields to that trigger")
EDGE_RELATIONS: frozenset[str] = frozenset({"promoted_by", "dedup_suppressed_by"})

EDGE_LINK_BASES: frozenset[str] = frozenset({"ts_join_synthesized", "emitter_recorded"})

#: Finality bases (A4.1/F6c + A4.5).  Recorded on every event so a consumer can
#: tell the emitter's own clock from Radar's conservative session bound.
FINALITY_KNOWN_TS = "known_ts_settled(known_ts<as_of)"
#: The side-channel base; ``g0_adapter`` appends ``[<ruler>]`` because a session
#: count is only meaningful with the calendar that produced it named.
FINALITY_SIDE_CHANNEL = "side_channel_conservative_bound(ts+3s<=as_of)"
FINALITY_NO_CLOCK = "no_known_ts(artifact_absent)"

#: A 1D-LIVE Radar observation.  The OBSERVATION is immutable — it happened at
#: that instant on the data knowable then — but the BAR it read is provisional
#: until the session closes, and ``final`` is a claim about the bar.  Marking a
#: live fire ``final`` would tell a consumer the daily value behind it can no
#: longer move, which is the one thing that is certainly untrue intraday.
FINALITY_LIVE_PROVISIONAL = "live_provisional_daily_bar(1D LIVE; settles at session close)"

#: FROZEN key order for serialisation.  ``event_id`` first because it is the
#: address every episode joins on.
EVENT_FIELDS: tuple[str, ...] = (
    "event_id",
    "producer",
    "detector_id",
    "ticker",
    "family",
    "subtype",
    "stage",
    "quality",
    "context",
    "signal_ts",
    "signal_known_ts",
    "source_identity",
    "scored_authority",
    "family_first_available",
    "pre_channel_reconstruction",
    "family_era",
    "field_origin",
    "bar_state",
    "final",
    "finality_basis",
    "authority",
)

EDGE_FIELDS: tuple[str, ...] = (
    "relation",
    "source_event_id",
    "target_event_id",
    "link_basis",
    "known_lossy",
    "provenance",
)


class EntryEventError(ValueError):
    """A record that violates the `mastermind.entry_event.v1` contract."""


class AppendOnlyViolation(EntryEventError):
    """Same address, different content.  The store never overwrites."""


class EdgeEndpointMissing(EntryEventError):
    """An edge naming an event the store has never seen."""


def canonical_json(payload: Any) -> str:
    """Deterministic JSON — the hashing and content-comparison form."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sha16(payload: Any) -> str:
    """First 16 hex of sha256 over the canonical JSON — the house short identity."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


#: The emitter-recorded field that separates two same-bar events of one family.
#: Terminal puts ``anchor_ts`` (the structure-stop anchor being reclaimed) on
#: ``stop_sweep_reclaim`` and on nothing else — so this is the EMITTER's own
#: discriminator, read from the record it already writes, never a Radar-minted
#: sequence number.
DISCRIMINATOR_CONTEXT_KEY = "anchor_ts"


def event_discriminator(context: Mapping[str, Any] | None) -> str | None:
    """The emitter's own same-bar discriminator, or None when it records none."""
    if not context:
        return None
    got = context.get(DISCRIMINATOR_CONTEXT_KEY)
    return None if got is None else str(got)


def compute_event_id(*, producer: str, family: str, subtype: str | None, ticker: str,
                     signal_ts: str, signal_era: str | None,
                     discriminator: str | None = None) -> str:
    """Deterministic event address — sha256 over the identity tuple, 16 hex.

    ``signal_era`` rides the address on purpose: the same producer emitting the
    same bar under a different era is a DIFFERENT observation, and pooling the
    two is precisely what the era fence exists to prevent.

    SAME-BAR DISCRIMINATOR — RESOLVED 2026-08-14 (orchestrator adjudication).
    Measured on the committed NVDA fixture: 2000-09-15, 2007-10-31 and
    2016-06-30 each carry TWO ``stop_sweep_reclaim`` events, identical in
    ``type``/``quality``/``ts`` and differing in ``anchor_ts`` (plus
    ``stop_level``/``sweep_low``/``quality_reason``) — two different
    structure-stop anchors reclaimed on one bar.  The six-part tuple could not
    address them apart.  Resolution: the EMITTER's own ``anchor_ts`` joins the
    address as a seventh component.  It is OMITTED from the hashed payload when
    ``None``, so every event the emitter does not discriminate keeps a
    byte-identical address to the six-part form — measured: 176 of NFLX's 217
    ids unchanged, and exactly the 41 ``stop_sweep_reclaim`` ids moved.

    RESIDUAL LAW, unchanged: same address + different content STILL refuses
    loudly (``AppendOnlyViolation``).  Two events the emitter itself cannot tell
    apart are a data-integrity error in the artifact, never something to merge —
    widening the address is how a REAL distinction gets recorded, not a licence
    to absorb an unreal one.
    """
    payload = [producer, family, subtype, ticker, signal_ts, signal_era]
    if discriminator is not None:
        payload.append(discriminator)
    return sha16(payload)


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """`(source_hash, signal_era, detector_spec_hash)` — a STRUCT, never one string.

    A1.2.1 names the struct explicitly.  One opaque identity string cannot answer
    "same spec, different era?" — which is the only question that decides whether
    two events may be pooled.
    """

    source_hash: str | None = None
    signal_era: str | None = None
    detector_spec_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_hash": self.source_hash,
            "signal_era": self.signal_era,
            "detector_spec_hash": self.detector_spec_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SourceIdentity:
        raw = raw or {}
        unknown = set(raw) - {"source_hash", "signal_era", "detector_spec_hash"}
        if unknown:
            raise EntryEventError(f"unknown source_identity field(s) {sorted(unknown)}")
        return cls(**raw)


@dataclass(frozen=True, slots=True, kw_only=True)
class EntryEvent:
    """One recorded entry event.  Field list per contract §18 A1.2.1.

    ``stage`` is present and is ``None`` for every event this adapter mints: the
    `mastermind.indicator/v1` signal stream carries NO stage field anywhere
    (A4.3), and the honest value for a field the emitter does not have is absent,
    never synthesised.  The field exists for emitters that DO carry one.
    """

    producer: str
    ticker: str
    family: str
    signal_ts: str
    source_identity: SourceIdentity
    field_origin: dict[str, str]
    bar_state: str
    final: bool
    finality_basis: str
    subtype: str | None = None
    detector_id: str | None = None
    stage: str | None = None
    quality: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    signal_known_ts: str | None = None
    scored_authority: bool | None = None
    family_first_available: dict[str, Any] | None = None
    pre_channel_reconstruction: bool | None = None
    family_era: str | None = None
    authority: dict[str, bool] = field(default_factory=lambda: dict(AUTHORITY_BLOCK))
    event_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", copy.deepcopy(dict(self.context)))
        object.__setattr__(self, "field_origin", dict(self.field_origin))
        object.__setattr__(self, "authority", dict(self.authority))
        if self.family_first_available is None:
            object.__setattr__(self, "family_first_available",
                               family_first_available(self.family, self.subtype))
        else:
            if not isinstance(self.family_first_available, Mapping):
                raise EntryEventError(
                    f"family_first_available {self.family_first_available!r} is not a "
                    f"{{kind, value}} struct; a bare string cannot say WHETHER the "
                    f"date is a channel birth, a quality-string birth or a scored "
                    f"promotion")
            object.__setattr__(self, "family_first_available",
                               dict(self.family_first_available))
        # Always derived FROM the recorded struct, so the pair cannot disagree.
        derived_pre = is_pre_channel_reconstruction(self.signal_ts,
                                                    self.family_first_available)
        if self.pre_channel_reconstruction is None:
            object.__setattr__(self, "pre_channel_reconstruction", derived_pre)
        elif bool(self.pre_channel_reconstruction) != derived_pre:
            raise EntryEventError(
                f"pre_channel_reconstruction {self.pre_channel_reconstruction!r} "
                f"disagrees with signal_ts {self.signal_ts} against "
                f"{self.family_first_available!r} (expected {derived_pre!r})")
        self._validate()
        # The discriminator is read from the event's OWN recorded context, so a
        # serialised event re-derives the identical address on the way back in.
        derived = compute_event_id(
            producer=self.producer, family=self.family, subtype=self.subtype,
            ticker=self.ticker, signal_ts=self.signal_ts,
            signal_era=self.source_identity.signal_era,
            discriminator=event_discriminator(self.context))
        if self.event_id is None:
            object.__setattr__(self, "event_id", derived)
        elif self.event_id != derived:
            raise EntryEventError(
                f"event_id {self.event_id!r} does not match the identity tuple "
                f"(expected {derived!r}) — the address is derived, never asserted")

    # -- validation -------------------------------------------------------
    def _validate(self) -> None:
        if self.family in FORBIDDEN_FAMILY_KEYS:
            raise EntryEventError(
                f"family {self.family!r} is a forbidden flattening/UI-label key "
                f"({sorted(FORBIDDEN_FAMILY_KEYS)}); the producer's enum wins over "
                f"the UI label and no generic entry bucket may exist (A1.2)")
        if self.family not in FAMILY_KEYS:
            raise EntryEventError(f"family {self.family!r} not in the minted set "
                                  f"{list(FAMILY_KEYS)} (A4.3 — families are minted "
                                  f"from emitter receipts, never invented)")
        if self.family in ORACLE_SUBTYPES:
            if self.subtype not in ORACLE_SUBTYPES[self.family]:
                raise EntryEventError(
                    f"{self.family} subtype {self.subtype!r} is not an emitter quality "
                    f"({sorted(ORACLE_SUBTYPES[self.family])})")
        if self.family in WATCH_SUBTYPES and self.subtype != WATCH_SUBTYPES[self.family]:
            raise EntryEventError(f"{self.family} requires subtype "
                                  f"{WATCH_SUBTYPES[self.family]!r}, got {self.subtype!r}")
        if self.family in RADAR_NATIVE_SUBTYPES:
            if self.detector_id in STRATIFICATION_ONLY_DETECTOR_IDS:
                raise EntryEventError(
                    f"detector_id {self.detector_id!r} is registered "
                    f"role=stratification_only and may never address an event — not "
                    f"even under a lawful family like {self.family!r}.  Its features "
                    f"stratify C2 episodes in later analysis; an arming interaction is "
                    f"DNR:KILL-WASHOUT-TURN's construction re-cut at a new grain "
                    f"(contract §18 A5.5)")
            allowed = RADAR_NATIVE_SUBTYPES[self.family]
            if self.subtype not in allowed:
                raise EntryEventError(
                    f"{self.family} subtype {self.subtype!r} is not a registered W3 "
                    f"mechanism ({sorted(allowed)}); the C2 variant family is exactly "
                    f"six and a seventh is a contract amendment, not a new string "
                    f"(contract §18 A5.3/A5.8)")
        if not str(self.producer or "").strip():
            raise EntryEventError("producer is required — an event with no producer "
                                  "has no provenance and cannot be graded later")
        if not str(self.ticker or "").strip():
            raise EntryEventError("ticker is required")
        if not str(self.signal_ts or "").strip():
            raise EntryEventError("signal_ts is required")
        if self.bar_state not in BAR_STATES:
            raise EntryEventError(f"bar_state {self.bar_state!r} not in {sorted(BAR_STATES)}")
        if self.final and self.bar_state != "confirmed":
            raise EntryEventError(f"final event {self.signal_ts} carries bar_state "
                                  f"{self.bar_state!r}; final implies confirmed")
        if not self.final and self.bar_state != "provisional":
            raise EntryEventError(f"non-final event {self.signal_ts} carries bar_state "
                                  f"{self.bar_state!r}; not-final implies provisional "
                                  f"(A4.1/F6c — consumers must not read it as settled)")
        if not str(self.finality_basis or "").strip():
            raise EntryEventError("finality_basis is required — a finality claim with no "
                                  "stated basis cannot be audited")
        bad_origin = {k: v for k, v in self.field_origin.items() if v not in FIELD_ORIGINS}
        if bad_origin:
            raise EntryEventError(f"field_origin values {bad_origin} not in "
                                  f"{sorted(FIELD_ORIGINS)}")
        receipt = self.family_first_available or {}
        if set(receipt) != {"kind", "value"}:
            raise EntryEventError(
                f"family_first_available {receipt!r} is not a "
                f"{{kind, value}} struct; a bare string cannot say WHETHER the date "
                f"is a channel birth, a quality-string birth or a scored promotion")
        if receipt["kind"] not in FIRST_AVAILABLE_KINDS:
            raise EntryEventError(f"family_first_available kind {receipt['kind']!r} not "
                                  f"in {sorted(FIRST_AVAILABLE_KINDS)}")
        self._validate_authority()

    def _validate_authority(self) -> None:
        if set(self.authority) != set(AUTHORITY_BLOCK):
            raise EntryEventError(
                f"authority block keys {sorted(self.authority)} != "
                f"{sorted(AUTHORITY_BLOCK)} — the display-tier block is exact")
        granted = sorted(k for k, v in self.authority.items() if v)
        if granted:
            raise EntryEventError(
                f"entry event for {self.ticker} claims authority {granted}; every "
                f"`mastermind.entry_event.v1` record is display/research tier and its "
                f"authority block is all-false (contract §2)")

    # -- serialisation ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form.  Key order and key set are exactly ``EVENT_FIELDS``."""
        out: dict[str, Any] = {}
        for name in EVENT_FIELDS:
            val = getattr(self, name)
            if isinstance(val, SourceIdentity):
                val = val.to_dict()
            elif isinstance(val, dict):
                val = copy.deepcopy(val)
            out[name] = val
        return out

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EntryEvent:
        unknown = set(raw) - set(EVENT_FIELDS)
        if unknown:
            raise EntryEventError(f"unknown entry_event field(s) {sorted(unknown)} — the "
                                  f"v1 field list is frozen at {list(EVENT_FIELDS)}")
        kwargs = {k: raw[k] for k in EVENT_FIELDS if k in raw}
        kwargs["source_identity"] = SourceIdentity.from_dict(kwargs.get("source_identity"))
        return cls(**kwargs)  # type: ignore[arg-type]

    @property
    def content_key(self) -> str:
        """Canonical content, for the append-only same-address/different-content test."""
        return canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class EventEdge:
    """A typed promotion / de-dup link.  An OBJECT, never a scalar field.

    A1.2.1 requires the typed form: ``promoted_by`` and ``dedup_suppressed_by``
    are different facts with different recoverability, and ``link_basis`` says
    whether the emitter RECORDED the link or Radar SYNTHESISED it by ts-join.
    The artifact carries no link field at all, so every edge this package mints
    today is ``ts_join_synthesized`` and says so.
    """

    relation: str
    source_event_id: str
    target_event_id: str
    link_basis: str
    known_lossy: bool = False
    provenance: str = ""

    def __post_init__(self) -> None:
        if self.relation not in EDGE_RELATIONS:
            raise EntryEventError(f"edge relation {self.relation!r} not in "
                                  f"{sorted(EDGE_RELATIONS)}")
        if self.link_basis not in EDGE_LINK_BASES:
            raise EntryEventError(f"edge link_basis {self.link_basis!r} not in "
                                  f"{sorted(EDGE_LINK_BASES)}")
        if not self.source_event_id or not self.target_event_id:
            raise EntryEventError("an edge needs both endpoints")
        if self.source_event_id == self.target_event_id:
            raise EntryEventError(f"self-edge on {self.source_event_id} is not a link")

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.relation, self.source_event_id, self.target_event_id)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in EDGE_FIELDS}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EventEdge:
        unknown = set(raw) - set(EDGE_FIELDS)
        if unknown:
            raise EntryEventError(f"unknown edge field(s) {sorted(unknown)} — the v1 "
                                  f"field list is frozen at {list(EDGE_FIELDS)}")
        return cls(**{k: raw[k] for k in EDGE_FIELDS if k in raw})  # type: ignore[arg-type]

    @property
    def content_key(self) -> str:
        return canonical_json(self.to_dict())


def family_first_available(family: str, subtype: str | None) -> dict[str, Any]:
    """First-availability receipt for a ``(family, subtype)`` — always a struct.

    Never guesses.  A quality with no minted receipt lands on
    ``FIRST_AVAILABLE_UNRECORDED`` (``kind="unrecorded"``, ``value=None``) rather
    than borrowing a sibling's ``pre_fence``, which would invent history for a
    family nobody dated.  ``stop_sweep_reclaim`` is the live example on this
    panel; a quality the emitter has not shipped yet is the synthetic one.

    Returns a COPY: the table is frozen data and a caller mutating its own event
    must not be able to rewrite the receipt for every other event of that family.
    """
    return dict(FAMILY_FIRST_AVAILABLE.get((family, subtype),
                                           FIRST_AVAILABLE_UNRECORDED))


def first_available_date(first_available: Mapping[str, Any] | None) -> str | None:
    """The ISO date a receipt bounds, or None when the kind does not carry one."""
    if not first_available:
        return None
    if first_available.get("kind") not in DATED_FIRST_AVAILABLE_KINDS:
        return None
    value = first_available.get("value")
    if not value:
        return None
    return str(value)[:10]


def is_pre_channel_reconstruction(signal_ts: str,
                                  first_available: Mapping[str, Any] | None) -> bool:
    """True when this event PREDATES its own family's first availability.

    Receipts §6 promises that "earlier reconstructions are ``radar_derived``,
    never emitter history".  This makes that promise mechanical instead of
    editorial: a `washout_early_watch` at 2004-07-30 is not something Terminal
    emitted in 2004 — the channel was born 2026-08-11 (#392) — it is the current
    emitter run backwards over history.  A consumer that cannot see the flag will
    read those rows as contemporaneous emitter history and date the family wrong.

    False for undated kinds (``era_fence``, ``unrecorded``): an era is not a date
    and an absent receipt bounds nothing, so neither can put an event on the
    wrong side of a line that was never drawn.
    """
    bound = first_available_date(first_available)
    if bound is None:
        return False
    return str(signal_ts) < bound


def radar_field_origin() -> dict[str, str]:
    """Per-field provenance for a Radar-NATIVE event: every field ``radar_derived``.

    There is no emitter to be verbatim about.  Radar computed the oscillator,
    Radar chose the family, Radar stamped the clock — so claiming
    ``emitter_verbatim`` anywhere here would attribute Radar's own work to
    somebody else (contract §18 A5.8: "all new Radar-native event fields are
    ``radar_derived``").
    """
    return {name: "radar_derived" for name in EVENT_FIELDS}


def build_radar_native_event(*, detector_id: str, detector_spec_hash: str,
                             ticker: str, family: str, subtype: str,
                             signal_ts: str, market_session: str, bar_state: str,
                             context: Mapping[str, Any] | None = None,
                             signal_known_ts: str | None = None,
                             finality_basis: str | None = None) -> EntryEvent:
    """One Radar-native `mastermind.entry_event.v1` record (C1 / C2 / C3).

    THE DOOR C4 CANNOT WALK THROUGH.  ``family`` must be one of the three A5.8
    Radar-native keys; ``C4_MTF_TURN@1`` has none, so the stratification family
    cannot mint an event even if some future caller forgets the explicit refusal
    in ``challengers.assert_can_fire``.  Two independent fences, one law.

    ``final`` is DERIVED from ``bar_state`` rather than accepted from the caller —
    the two can never disagree, and a live provisional fire cannot be labelled
    settled by a caller in a hurry.  A confirmed-bar family must STATE its
    finality basis: "confirmed" with no stated basis is an unauditable claim.
    """
    if family not in RADAR_NATIVE_SUBTYPES:
        raise EntryEventError(
            f"family {family!r} is not a Radar-native family "
            f"({list(RADAR_NATIVE_FAMILIES)}); C4 is registered "
            f"role=stratification_only and has no family at all, so it cannot address "
            f"an event (contract §18 A5.5/A5.8, DNR:KILL-WASHOUT-TURN)")
    if detector_id in STRATIFICATION_ONLY_DETECTOR_IDS:
        raise EntryEventError(
            f"detector_id {detector_id!r} is registered role=stratification_only and "
            f"may never mint an event, whatever family it names "
            f"(contract §18 A5.5, DNR:KILL-WASHOUT-TURN)")
    if bar_state not in BAR_STATES:
        raise EntryEventError(f"bar_state {bar_state!r} not in {sorted(BAR_STATES)}")
    final = bar_state == "confirmed"
    if final and not str(finality_basis or "").strip():
        raise EntryEventError(
            f"{family}/{subtype} claims a CONFIRMED bar with no finality_basis; a "
            f"finality claim with no stated basis cannot be audited")
    basis = finality_basis or FINALITY_LIVE_PROVISIONAL
    payload = dict(context or {})
    payload.setdefault("market_session", market_session)
    return EntryEvent(
        producer=RADAR_PRODUCER,
        detector_id=detector_id,
        ticker=ticker,
        family=family,
        subtype=subtype,
        stage=None,
        quality=None,
        context=payload,
        signal_ts=signal_ts,
        signal_known_ts=signal_known_ts,
        source_identity=SourceIdentity(source_hash=None,
                                       signal_era=RADAR_SIGNAL_ERA,
                                       detector_spec_hash=detector_spec_hash),
        # Radar IS the emitter here, and Radar does not score: this records
        # Radar's own honest statement about its own artifact, not a grant.
        scored_authority=False,
        family_era=RADAR_SIGNAL_ERA,
        field_origin=radar_field_origin(),
        bar_state=bar_state,
        final=final,
        finality_basis=basis,
    )


class EntryEventStore:
    """Append-only store of events + typed edges.

    THERE IS NO MUTATION API.  No update, no delete, no remove, no pop, no
    clear — the absence is asserted by a ``dir()`` sweep in
    ``tests/test_entry_radar_events.py`` so it cannot be re-added by accident.

    NOT A DURABLE WRITER.  W2 holds events in memory and serialises to a JSONL
    *string*; nothing here opens a file, and no ``data/`` path appears in this
    module.  PR-5's nightly reconciler owns durability behind
    ``ledger_lane.nightly_advance_enabled()``.
    """

    def __init__(self) -> None:
        self._events: dict[str, EntryEvent] = {}
        self._edges: dict[tuple[str, str, str], EventEdge] = {}

    # -- append-only door --------------------------------------------------
    def append(self, event: EntryEvent) -> EntryEvent:
        """Record an event.  Idempotent on identical content; never overwrites."""
        if not isinstance(event, EntryEvent):
            raise EntryEventError(f"append expects an EntryEvent, got {type(event).__name__}")
        assert event.event_id is not None  # set in __post_init__
        seen = self._events.get(event.event_id)
        if seen is None:
            self._events[event.event_id] = event
            return event
        if seen.content_key != event.content_key:
            raise AppendOnlyViolation(
                f"event_id {event.event_id} ({event.ticker} {event.family}/"
                f"{event.subtype} {event.signal_ts}) already recorded with different "
                f"content; an append-only store never overwrites.  Either the "
                f"emitter drew a distinction this address cannot express (widen it — "
                f"see {DISCRIMINATOR_CONTEXT_KEY!r}), or a field that varies with the "
                f"SLICE VINTAGE has leaked into event content and belongs on the "
                f"per-slice report instead")
        return seen

    def add_edge(self, edge: EventEdge) -> EventEdge:
        """Record a typed edge.  Both endpoints must already exist."""
        if not isinstance(edge, EventEdge):
            raise EntryEventError(f"add_edge expects an EventEdge, got {type(edge).__name__}")
        for endpoint in (edge.source_event_id, edge.target_event_id):
            if endpoint not in self._events:
                raise EdgeEndpointMissing(
                    f"edge {edge.relation} names event {endpoint} which this store has "
                    f"never recorded; an edge to nowhere is not provenance")
        seen = self._edges.get(edge.identity)
        if seen is None:
            self._edges[edge.identity] = edge
            return edge
        if seen.content_key != edge.content_key:
            raise AppendOnlyViolation(
                f"edge {edge.identity} already recorded with different content")
        return seen

    def extend(self, events: Iterable[EntryEvent]) -> list[EntryEvent]:
        """Append many.  Same rules, no batch escape hatch."""
        return [self.append(e) for e in events]

    # -- reads -------------------------------------------------------------
    def events(self) -> tuple[EntryEvent, ...]:
        """A copy, in insertion order.  Mutating the result cannot reach the store."""
        return tuple(copy.deepcopy(e) for e in self._events.values())

    def edges(self) -> tuple[EventEdge, ...]:
        return tuple(self._edges.values())

    def get(self, event_id: str) -> EntryEvent | None:
        got = self._events.get(event_id)
        return copy.deepcopy(got) if got is not None else None

    def __contains__(self, event_id: object) -> bool:
        return event_id in self._events

    def __len__(self) -> int:
        return len(self._events)

    # -- serialisation -----------------------------------------------------
    def to_jsonl(self) -> str:
        """One record per line: events in insertion order, then edges."""
        lines = [
            canonical_json({"schema": SCHEMA_ENTRY_EVENT, "record": "event",
                            "payload": e.to_dict()})
            for e in self._events.values()
        ]
        lines += [
            canonical_json({"schema": SCHEMA_ENTRY_EVENT, "record": "edge",
                            "payload": g.to_dict()})
            for g in self._edges.values()
        ]
        return "\n".join(lines)

    @classmethod
    def from_jsonl(cls, text: str) -> EntryEventStore:
        store = cls()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("schema") != SCHEMA_ENTRY_EVENT:
                raise EntryEventError(f"line {lineno}: schema {row.get('schema')!r} is not "
                                      f"{SCHEMA_ENTRY_EVENT}")
            kind = row.get("record")
            if kind == "event":
                store.append(EntryEvent.from_dict(row["payload"]))
            elif kind == "edge":
                store.add_edge(EventEdge.from_dict(row["payload"]))
            else:
                raise EntryEventError(f"line {lineno}: unknown record kind {kind!r}")
        return store


def event_dataclass_fields() -> tuple[str, ...]:
    """The dataclass's own field order — asserted to cover ``EVENT_FIELDS``."""
    return tuple(f.name for f in fields(EntryEvent))
