"""engine/risk_envelope.py — the Grey Deer PURE composer for `mastermind.risk_envelope/v1`.

Contract: `research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md`
§5.2.  Commission: `research/grey_deer/commissions/GD-2_SETTLED_ENVELOPE_COMMISSION_2026-08-19.md`.

WHAT THIS MODULE IS
-------------------
Mastermind must answer three *different* questions without blending them:

  1. measured state   — what slow trend/regime is still present?
  2. transition hazard — is a specific mechanism becoming dangerous or spreading?
  3. capital policy    — what bounded actions are currently permitted?

A slow Risk-on state may coexist with a broken leadership cohort.  That is not
disagreement to hide behind an average; it is the exact transition the program exists
to detect.  This composer therefore **selects and carries** source-native states; it
never averages them, never fuses them into a new number, and never lets one organ's
calm reading cancel another organ's damage reading.

PURITY (frozen constraint, commission §0.1)
-------------------------------------------
`compose_envelope()` and everything it calls are pure: no file/network I/O, no
environment reads, and **no clock reads**.  Every instant the envelope carries is
passed in by the caller (`observed_at`, `produced_at`, `stale_after`).  A settled
builder supplies them from the session it is baking; a test supplies frozen ones and
gets byte-identical output.  `tests/test_risk_envelope.py` pins this by scanning this
module's own source for clock and I/O calls.

BIRTH AUTHORITY — DESCRIPTIVE ONLY (Sol ruling 2026-08-19)
-----------------------------------------------------------
Every authority boolean is hard-false and `policy_actions_require_individual_authority`
is hard-true.  `hazard_stage` may only take a *descriptive* value observed from settled
same-session evidence:

    NONE | FRAGILE | TRANSMITTING | BREAKDOWN | null

`ARMED` and `TRIGGERING` are anticipatory claims — they assert something is *about to*
happen — and are reserved for separately promoted experts.  This composer can never
emit them; `_STAGE_VOCABULARY` is the closed set and `assert_v0_stage()` is the guard.

THE NULL LAW (frozen constraint, commission §0.3)
--------------------------------------------------
`null` means *not lawfully knowable with current coverage*.  It is not `NONE` and it is
not `0`:

  * ``null``  — a required hazard source is missing or stale.  We decline to answer.
  * ``NONE``  — required coverage is fresh AND every fresh source reports no hazard.
  * ``0``     — a legitimate numeric reading that happens to be zero.

Stale or missing inputs may only *shrink confidence* or *null the stage*.  They may
never cast a calm vote — a source we cannot read is not a source telling us things are
fine.  This is enforced structurally: stale/missing reads are dropped from the evidence
set before the stage is selected, and dropping a required one nulls the stage outright.

NO BLENDING
-----------
The stage is the **maximum severity any single fresh source justifies** — a selection
over an ordinal, never a mean.  Two sources at FRAGILE do not make BREAKDOWN, and one
calm source does not pull a BREAKDOWN source down to FRAGILE.  `coherence` records the
disagreement explicitly instead of dissolving it.

EXCLUSIONS
----------
`engine/risk_state.py` is frozen legacy.  Its fused score must never enter this
composer's arithmetic, and a regression test asserts this module never imports or
names it.  No new weighted risk number is minted anywhere in this file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "SCHEMA",
    "DEFINITION_ID",
    "SourceRead",
    "compose_envelope",
    "assert_v0_stage",
    "STAGE_VOCABULARY",
    "MEASURED_VOCABULARY",
    "DATA_STATE_VOCABULARY",
    "COHERENCE_VOCABULARY",
    "POSTURE_VOCABULARY",
    "canonical_json",
]

SCHEMA = "mastermind.risk_envelope/v1"
DEFINITION_ID = "grey-deer-v1-2026-08-19"

# ── frozen vocabularies ────────────────────────────────────────────────────────
# V0 descriptive stages only.  ARMED / TRIGGERING are anticipatory and are NOT here
# by construction (Sol birth-authority ruling); adding them is a contract change that
# needs a new definition_id and a promoted expert behind it.
STAGE_VOCABULARY: tuple[str, ...] = ("NONE", "FRAGILE", "TRANSMITTING", "BREAKDOWN")
# Ordinal severity used ONLY for max-selection.  These are ranks, never arithmetic
# inputs — nothing in this module adds, averages or weights them.
_STAGE_RANK: dict[str, int] = {"NONE": 0, "FRAGILE": 1, "TRANSMITTING": 2, "BREAKDOWN": 3}

MEASURED_VOCABULARY: tuple[str, ...] = ("RISK_ON", "MIXED", "RISK_OFF")
DATA_STATE_VOCABULARY: tuple[str, ...] = ("FRESH", "PARTIAL", "DEGRADED", "STALE", "UNKNOWN")
COHERENCE_VOCABULARY: tuple[str, ...] = ("ALIGNED", "MIXED", "CONTRADICTORY")
REPAIR_VOCABULARY: tuple[str, ...] = ("NONE", "IMPULSE", "BROADENING", "CONFIRMED", "FAILED")
POSTURE_VOCABULARY: tuple[str, ...] = (
    "NORMAL", "SELECTIVE", "PROTECTIVE", "DEFENSIVE_ONLY", "NO_NEW_RISK", "EMERGENCY",
)

# Roles a source may play.  A source declares what question it answers; the composer
# never re-purposes a source across roles.
ROLE_MEASURED = "measured_state"
ROLE_HAZARD = "hazard_evidence"
ROLE_CONTEXT = "context"
ROLES: tuple[str, ...] = (ROLE_MEASURED, ROLE_HAZARD, ROLE_CONTEXT)


class EnvelopeContractError(ValueError):
    """Raised when a caller hands the composer something the contract forbids."""


def assert_v0_stage(stage: str | None) -> str | None:
    """Return `stage` if it is a lawful V0 descriptive stage, else raise.

    The guard exists so a future edit that reaches for ARMED/TRIGGERING fails loudly at
    the contract boundary instead of quietly shipping an anticipatory claim under a
    descriptive-only authority.
    """
    if stage is None:
        return None
    if stage not in STAGE_VOCABULARY:
        raise EnvelopeContractError(
            f"hazard stage {stage!r} is not a V0 descriptive stage; "
            f"lawful values are {STAGE_VOCABULARY} or None. "
            "ARMED/TRIGGERING are anticipatory and reserved for promoted experts."
        )
    return stage


@dataclass(frozen=True)
class SourceRead:
    """One organ's SOURCE-NATIVE read, carried verbatim.

    The composer never recomputes a source.  `state` and `score` are exactly what the
    producing organ published; `hazard_stage` is the source's own descriptive mapping
    into the V0 vocabulary (supplied by the adapter that knows that organ, never
    inferred here from a score threshold).

    Fields
    ------
    source_id : stable id, also the synapse artifact id where one exists.
    role      : which of the three questions this source answers.
    state     : the organ's native state string, verbatim (e.g. 'RISK_ON', 'BROKEN',
                'calm').  Carried into provenance unchanged.
    score     : the organ's native score, verbatim.  `0` is a real reading; `None`
                means the organ published no score.
    as_of     : the source's OWN clock.  Sources settle at different times; that is
                why they can disagree, so each keeps its own stamp.
    stale     : the source's own staleness verdict, when it publishes one.
    present   : False when the artifact was missing entirely.
    required  : True when the stage is not lawfully knowable without this source.
    hazard_stage : this source's descriptive V0 stage contribution, or None.
    detail    : extra source-native fields carried for the evidence drawer.  Never
                read as arithmetic.
    """

    source_id: str
    role: str
    state: str | None = None
    score: float | int | None = None
    as_of: str | None = None
    stale: bool = False
    present: bool = True
    required: bool = False
    hazard_stage: str | None = None
    label_en: str | None = None
    label_zh: str | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise EnvelopeContractError(f"unknown source role {self.role!r}; expected one of {ROLES}")
        assert_v0_stage(self.hazard_stage)

    @property
    def usable(self) -> bool:
        """True when this read may cast a vote at all.

        A missing or stale source is NOT evidence of calm — it is an absence of
        evidence.  Excluding it here is the structural half of the null law; the other
        half is that excluding a *required* source nulls the stage.
        """
        return bool(self.present) and not self.stale

    def coverage_state(self) -> str:
        if not self.present:
            return "MISSING"
        if self.stale:
            return "STALE"
        return "FRESH"


_ROLE_ORDER: dict[str, int] = {ROLE_MEASURED: 0, ROLE_HAZARD: 1, ROLE_CONTEXT: 2}


def _sorted(sources: Iterable[SourceRead]) -> list[SourceRead]:
    """Deterministic order: role first, then source_id.

    Every downstream structure is built from this list, which is what makes the
    composer source-order invariant — callers may pass sources in any order and get
    byte-identical output.  Ordering by ROLE first (rather than by id alone) means
    the provenance list reads in the same order as the three answers it explains,
    so an evidence drawer can render it straight through without re-sorting.
    """
    return sorted(sources, key=lambda s: (_ROLE_ORDER[s.role], s.source_id))


def canonical_json(payload: Any) -> str:
    """Stable serialization: sorted keys, tight separators, UTF-8 preserved.

    Used for both the content-addressed `bundle_id` and the on-disk artifact, so the
    committed file and the hashed payload agree by construction.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _measured_state(sources: Sequence[SourceRead]) -> dict[str, Any]:
    """Carry the measured-state organ through VERBATIM.

    Frozen constraint: the Market State value is preserved exactly.  No rounding, no
    rescaling, no clamping, no blending with any other organ.  If the organ is missing
    or stale the verdict is null — a stale trend read may not stand in for a fresh one.
    """
    reads = [s for s in _sorted(sources) if s.role == ROLE_MEASURED]
    if not reads:
        return {
            "source_artifact": None, "verdict": None, "score": None,
            "role": "slow_confirmed_trend", "as_of": None, "usable": False,
        }
    src = reads[0]
    usable = src.usable
    return {
        "source_artifact": src.source_id,
        # verbatim or null — never a substituted default
        "verdict": src.state if usable else None,
        "score": src.score if usable else None,
        "role": "slow_confirmed_trend",
        "as_of": src.as_of,
        "usable": usable,
    }


def _data_state(sources: Sequence[SourceRead]) -> str:
    """Grade the *coverage*, not the market.

    data_state is orthogonal to severity (freeze §2.1): a market can be BREAKDOWN and
    FRESH, or NONE and DEGRADED.  It answers only "how well could we see today".
    """
    ordered = _sorted(sources)
    if not ordered:
        return "UNKNOWN"
    required = [s for s in ordered if s.required]
    if any(not s.present for s in required):
        return "UNKNOWN"          # a required organ did not publish at all
    if all(not s.present for s in ordered):
        return "UNKNOWN"
    required_stale = [s for s in required if s.stale]
    if required_stale:
        # every required source stale = we are reading yesterday's market
        return "STALE" if len(required_stale) == len(required) else "DEGRADED"
    optional_bad = [s for s in ordered if not s.required and (s.stale or not s.present)]
    return "PARTIAL" if optional_bad else "FRESH"


def _hazard_summary(sources: Sequence[SourceRead]) -> dict[str, Any]:
    """Select the descriptive hazard stage. Selection over an ordinal — never a mean.

    Rules, in order:
      1. A required hazard source that is missing or stale  → stage null (not knowable).
      2. No usable hazard source at all                     → stage null.
      3. Otherwise the stage is the MAX severity any single usable source justifies.
         A calm source never reduces a damaged source's reading; two FRAGILE sources
         never compound to TRANSMITTING.
      4. NONE is emitted only under rule 3 with fresh required coverage — i.e. it is a
         positive "we looked and found nothing", never a fallback.
    """
    hazard = [s for s in _sorted(sources) if s.role == ROLE_HAZARD]
    required_unusable = [s for s in hazard if s.required and not s.usable]
    usable = [s for s in hazard if s.usable and s.hazard_stage is not None]

    if required_unusable:
        return {
            "stage": None,
            "stage_reason": "required_coverage_unavailable",
            "unreadable_sources": [s.source_id for s in required_unusable],
            "contributing_sources": [s.source_id for s in usable],
            "primary_episode_id": None,
            "active_episode_count": 0,
            "stage_since": None,
            "display_only": True,
        }
    if not usable:
        return {
            "stage": None,
            "stage_reason": "no_usable_hazard_evidence",
            "unreadable_sources": [s.source_id for s in hazard if not s.usable],
            "contributing_sources": [],
            "primary_episode_id": None,
            "active_episode_count": 0,
            "stage_since": None,
            "display_only": True,
        }

    lead = max(usable, key=lambda s: (_STAGE_RANK[s.hazard_stage or "NONE"], s.source_id))
    stage = assert_v0_stage(lead.hazard_stage)
    # stage_since comes from the leading source's own clock when it publishes one —
    # the composer never invents a transition timestamp.
    stage_since = None
    if stage != "NONE":
        stage_since = lead.detail.get("state_since") or lead.as_of
    return {
        "stage": stage,
        "stage_reason": "observed_settled_evidence",
        "unreadable_sources": [s.source_id for s in hazard if not s.usable],
        "contributing_sources": [s.source_id for s in usable],
        # V0 mints no episodes: the Risk Envelope owns no forward ledger (freeze §4).
        "primary_episode_id": None,
        "active_episode_count": 0,
        "stage_since": stage_since,
        "display_only": True,
    }


def _contradictions(
    sources: Sequence[SourceRead], measured: Mapping[str, Any], stage: str | None
) -> list[dict[str, Any]]:
    """Name every disagreement explicitly, so the UI can show it instead of hiding it.

    Two kinds are recorded:
      * trend_vs_hazard — the slow trend says risk-on while a hazard organ reports
        damage.  This is the GD-1 2026-08-18 case and the reason the program exists.
      * hazard_split    — two hazard organs looking at the same session disagree about
        whether anything is wrong.
    """
    out: list[dict[str, Any]] = []
    hazard = [s for s in _sorted(sources) if s.role == ROLE_HAZARD and s.usable]

    if measured.get("verdict") == "RISK_ON" and stage in ("FRAGILE", "TRANSMITTING", "BREAKDOWN"):
        for s in hazard:
            if (s.hazard_stage or "NONE") != "NONE":
                out.append({
                    "kind": "trend_vs_hazard",
                    "left": measured.get("source_artifact"),
                    "left_state": measured.get("verdict"),
                    "right": s.source_id,
                    "right_state": s.state,
                })

    damaged = [s for s in hazard if (s.hazard_stage or "NONE") != "NONE"]
    calm = [s for s in hazard if (s.hazard_stage or "NONE") == "NONE"]
    for d in damaged:
        for c in calm:
            out.append({
                "kind": "hazard_split",
                "left": d.source_id,
                "left_state": d.state,
                "right": c.source_id,
                "right_state": c.state,
            })
    return out


def _coherence(
    sources: Sequence[SourceRead],
    measured: Mapping[str, Any],
    hazard: Mapping[str, Any],
    data_state: str,
) -> dict[str, Any]:
    """Do the answers agree?  A structural verdict — NOT a severity and NOT a score.

    CONTRADICTORY  the answers point opposite ways (trend intact, mechanism broken).
    MIXED          we cannot claim alignment: the stage is unreadable, coverage is
                   degraded, or hazard organs disagree with each other only.
    ALIGNED        every usable answer points the same way.

    coherence carries no hue of its own on the surface: under the reserved-hue law
    (MASTER_PRODUCT_DESIGN_SYSTEM_V1 §1) hue means direction, health, wayfinding,
    epistemic tier or lock — never "agreement".  The UI encodes this structurally.
    """
    stage = hazard.get("stage")
    contradictions = _contradictions(sources, measured, stage)
    has_trend_conflict = any(c["kind"] == "trend_vs_hazard" for c in contradictions)

    if has_trend_conflict:
        state = "CONTRADICTORY"
    elif stage is None or data_state in ("DEGRADED", "STALE", "UNKNOWN") or contradictions:
        state = "MIXED"
    elif not measured.get("usable"):
        state = "MIXED"
    else:
        state = "ALIGNED"

    return {
        "state": state,
        "contradictions": contradictions,
        "contradiction_count": len(contradictions),
        "display_only": True,
    }


def _coverage(sources: Sequence[SourceRead]) -> dict[str, Any]:
    ordered = _sorted(sources)
    return {
        "required": [s.source_id for s in ordered if s.required],
        "optional": [s.source_id for s in ordered if not s.required],
        "fresh": [s.source_id for s in ordered if s.coverage_state() == "FRESH"],
        "stale": [s.source_id for s in ordered if s.coverage_state() == "STALE"],
        "missing": [s.source_id for s in ordered if s.coverage_state() == "MISSING"],
        "source_count": len(ordered),
    }


def _freshness(sources: Sequence[SourceRead], source_session: str | None) -> dict[str, Any]:
    """Per-source clocks, carried separately.

    Three separate truths need three separate clocks: collapsing them to one page
    timestamp is what makes a stale organ look like a current one.
    """
    ordered = _sorted(sources)
    per_source = {
        s.source_id: {
            "as_of": s.as_of,
            "state": s.coverage_state(),
            "matches_session": (s.as_of == source_session) if (s.as_of and source_session) else None,
        }
        for s in ordered
    }
    off_session = sorted(
        sid for sid, v in per_source.items() if v["matches_session"] is False
    )
    return {
        "source_session": source_session,
        "per_source": per_source,
        "off_session_sources": off_session,
        "all_on_session": not off_session and bool(per_source),
    }


def _provenance(sources: Sequence[SourceRead]) -> dict[str, Any]:
    return {
        "sources": [
            {
                "source_id": s.source_id,
                "role": s.role,
                "state": s.state,
                "score": s.score,
                "as_of": s.as_of,
                "coverage": s.coverage_state(),
                "required": s.required,
                "hazard_stage": s.hazard_stage,
                "label_en": s.label_en,
                "label_zh": s.label_zh,
                "detail": dict(sorted(s.detail.items())),
            }
            for s in _sorted(sources)
        ],
        "composer": "engine/risk_envelope.py",
        "excludes": [
            # Named exclusion, kept as a machine-readable receipt: the legacy fused
            # score is frozen and must never re-enter a composed answer.
            "engine/risk_state.py (frozen legacy fused score — excluded by contract)",
        ],
    }


def _authority() -> dict[str, bool]:
    """Birth authority: descriptive only.  Every boolean hard-false, by construction."""
    return {
        "envelope_may_rank": False,
        "envelope_may_gate": False,
        "envelope_may_size": False,
        "envelope_may_execute": False,
        "policy_actions_require_individual_authority": True,
    }


def compose_envelope(
    *,
    sources: Sequence[SourceRead],
    market: str,
    source_session: str | None,
    observed_at: str,
    produced_at: str,
    as_of: str | None = None,
    stale_after: str | None = None,
    revision: str = "settled",
    definition_id: str = DEFINITION_ID,
    correction: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose one `mastermind.risk_envelope/v1` envelope.  PURE.

    Every instant is an argument: this function reads no clock and touches no disk.
    Given the same `sources` (in any order) and the same instants it returns a
    byte-identical structure.

    `bundle_id` content-addresses the SEMANTIC payload only — the states, evidence,
    coverage and clocks of the sources — deliberately excluding `observed_at` and
    `produced_at`.  Re-baking the same settled session therefore yields the same
    bundle_id even though the produced-at instant moved, which is what lets a consumer
    tell "the answer changed" apart from "the builder ran again".
    """
    if revision not in ("settled", "live_provisional", "corrected"):
        raise EnvelopeContractError(f"unknown revision {revision!r}")

    ordered = _sorted(sources)
    seen: set[str] = set()
    for s in ordered:
        if s.source_id in seen:
            raise EnvelopeContractError(f"duplicate source_id {s.source_id!r}")
        seen.add(s.source_id)

    measured = _measured_state(ordered)
    data_state = _data_state(ordered)
    hazard = _hazard_summary(ordered)
    coherence = _coherence(ordered, measured, hazard, data_state)

    semantic: dict[str, Any] = {
        "schema": SCHEMA,
        "definition_id": definition_id,
        "market": market,
        "revision": revision,
        "source_session": source_session,
        "as_of": as_of if as_of is not None else source_session,
        "measured_state": measured,
        "hazard_summary": hazard,
        # V0 mints no episodes and no policies.  These are not "empty because the
        # builder failed" — they are empty because no episode store and no registered
        # policy object exists yet, and inventing either here would be a new ledger.
        "episodes": [],
        "policies": [],
        "policy_summary": {
            "posture": "NORMAL",
            "active_policy_ids": [],
            "policy_count": 0,
            # NORMAL here is the display projection of ZERO policies, not a judgement
            # that conditions are normal.  Nothing is being restricted because nothing
            # has the authority to restrict.
            "basis": "zero_active_policies",
            "display_only": True,
        },
        "data_state": data_state,
        # V0 tracks no repair lifecycle (needs an episode store — out of scope).
        "repair_state": None,
        "coherence": coherence,
        "coverage": _coverage(ordered),
        "freshness": _freshness(ordered, source_session),
        "correction": dict(correction) if correction else None,
        "provenance": _provenance(ordered),
        "authority": _authority(),
    }

    bundle_id = hashlib.sha256(canonical_json(semantic).encode("utf-8")).hexdigest()[:16]

    envelope = dict(semantic)
    envelope["bundle_id"] = bundle_id
    envelope["observed_at"] = observed_at
    envelope["produced_at"] = produced_at
    envelope["stale_after"] = stale_after
    return envelope
