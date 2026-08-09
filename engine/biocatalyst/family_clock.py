"""BC-M0a family clock activation: evaluate each entry gate, open only what holds.

The M0a policy (``config/biocatalyst_outcome_family_policy.yml``) declares nine
outcome families and, for each, an ENTRY GATE.  This module evaluates those
gates from evidence and records the answer as an append-only receipt through the
BC-O1a writer, so the activation itself is evidence rather than a hand-asserted
boolean in a YAML file.

Two rules give the evaluation its teeth:

* It owns exactly the two preconditions it can evaluate from evidence —
  ``o1b_outcome_writer`` (the writer contract and record kind exist) and
  ``eligible_source_registration`` (every source the gate names is registered
  and production-ingest-allowed).  It both clears and raises those two.
  ``frozen_policy_version`` and ``eligible_identity_contract`` are a FLOOR: the
  frozen policy declares them, this module has no evidence that would clear
  them, and so it never does.
* It re-derives source eligibility on every run, so a family whose required
  sources are not production-ingest-allowed CANNOT be opened by editing the
  policy file.  A gate that says "satisfied" over an ineligible source is a
  fabricated clock, and a clock that accrues nothing is worse than a closed one:
  it would later be read as evidence of accrual that never happened.  A family
  that names NO source is not evidence of eligibility either; its declared state
  stands.

Opening a clock means recording that a family accrues FROM NOW, bound to a
frozen policy version and to that policy's exact bytes.  It never means writing
history: there is no backfill path here, and the store refuses an accrual start
earlier than the instant the clock was opened.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from engine.biocatalyst.operational_store import (
    AppendReceipt,
    OperationalStore,
    RECORD_KINDS,
)
from engine.sector_intelligence.contracts import ContractRegistry


FAMILY_CLOCK_ACTIVATION_CONTRACT_ID = "biocatalyst_family_clock_activation.v1"
FAMILY_CLOCK_ACTIVATION_RECORD_KIND = "family_clock_activation"

# The writer the M0a policy names as every family's precondition.
O1B_WRITER_CONTRACT_ID = "biocatalyst_outcome_record.v1"
O1B_WRITER_RECORD_KIND = "outcome_observation"

FAMILY_POLICY_PATH = Path("config") / "biocatalyst_outcome_family_policy.yml"
SOURCE_REGISTRY_PATH = Path("config") / "biocatalyst_sources.yml"

PRECONDITIONS: tuple[str, ...] = (
    "frozen_policy_version",
    "eligible_source_registration",
    "eligible_identity_contract",
    "o1b_outcome_writer",
)

WRITER_ABSENT_BLOCKER = "o1b_outcome_writer_absent"
INELIGIBLE_SOURCE_BLOCKER = "required_source_not_production_ingest_allowed"

CLOCK_OPENED = "opened"
CLOCK_CLOSED = "closed"


class FamilyClockError(RuntimeError):
    """A deliberately bounded family-clock failure code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class FamilyClockDecision:
    """The evaluated entry-gate state of one outcome family."""

    family_id: str
    clock_state: str
    satisfied_preconditions: tuple[str, ...]
    unsatisfied_preconditions: tuple[str, ...]
    blockers: tuple[str, ...]
    ineligible_source_ids: tuple[str, ...]

    @property
    def opened(self) -> bool:
        return self.clock_state == CLOCK_OPENED


def o1b_writer_is_available(*, repo_root: Path | str | None = None) -> bool:
    """Return True only when the O1b outcome writer genuinely exists.

    Both halves are required: the writer contract is registered AND the store
    has a home for an outcome.  A contract with no record kind is a document,
    not a writer.
    """

    if O1B_WRITER_RECORD_KIND not in RECORD_KINDS:
        return False
    return O1B_WRITER_CONTRACT_ID in ContractRegistry(repo_root).contract_ids


def load_yaml_document(path: Path | str) -> tuple[dict[str, Any], str]:
    """Return one YAML document and the SHA-256 of its exact bytes."""

    raw = Path(path).read_bytes()
    document = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(document, dict):
        raise FamilyClockError("FAMILY_CLOCK_DOCUMENT_INVALID")
    return document, sha256(raw).hexdigest()


def source_is_eligible(source_id: Any, sources: Mapping[str, Any]) -> bool:
    """Return True only for a registered, production-ingest-allowed source.

    An unknown source id is ineligible: the registry is the authority, and a
    source it does not carry has no reviewed rights state at all.
    """

    registration = sources.get(source_id) if isinstance(source_id, str) else None
    if not isinstance(registration, Mapping):
        return False
    return registration.get("production_ingest_allowed") is True


def evaluate_family_clock(
    family_id: str,
    family: Mapping[str, Any],
    sources: Mapping[str, Any],
    *,
    writer_available: bool,
) -> FamilyClockDecision:
    """Evaluate one family's entry gate honestly, from evidence."""

    gate = family.get("entry_gate")
    if not isinstance(gate, Mapping):
        raise FamilyClockError("FAMILY_CLOCK_GATE_MISSING")
    required = tuple(gate.get("required_preconditions") or ())
    if not required:
        raise FamilyClockError("FAMILY_CLOCK_GATE_MISSING")

    unsatisfied = set(gate.get("unsatisfied_preconditions") or ())
    blockers = set(gate.get("blockers") or ())

    # Evidence 1 — the O1b writer.  The only precondition this evaluator may
    # discharge, and only on positive evidence.
    if writer_available:
        unsatisfied.discard("o1b_outcome_writer")
        blockers.discard(WRITER_ABSENT_BLOCKER)
    elif "o1b_outcome_writer" in required:
        unsatisfied.add("o1b_outcome_writer")
        blockers.add(WRITER_ABSENT_BLOCKER)

    # Evidence 2 — source eligibility, recomputed from the registry on every
    # run.  A gate hand-edited to look clear cannot open a family whose sources
    # cannot be read; a family with NO named source is not evidence of
    # eligibility either, so its declared state stands.
    required_source_ids = tuple(gate.get("required_source_ids") or ())
    ineligible = tuple(
        sorted(
            str(source_id)
            for source_id in required_source_ids
            if not source_is_eligible(source_id, sources)
        )
    )
    if ineligible:
        unsatisfied.add("eligible_source_registration")
        blockers.add(INELIGIBLE_SOURCE_BLOCKER)
    elif required_source_ids:
        unsatisfied.discard("eligible_source_registration")
        blockers.discard(INELIGIBLE_SOURCE_BLOCKER)

    unsatisfied &= set(required)
    satisfied = tuple(name for name in required if name not in unsatisfied)
    clock_state = CLOCK_OPENED if not unsatisfied and not blockers else CLOCK_CLOSED
    return FamilyClockDecision(
        family_id=family_id,
        clock_state=clock_state,
        satisfied_preconditions=satisfied,
        unsatisfied_preconditions=tuple(sorted(unsatisfied)),
        blockers=tuple(sorted(blockers)),
        ineligible_source_ids=ineligible,
    )


def evaluate_family_clocks(
    policy: Mapping[str, Any],
    sources: Mapping[str, Any],
    *,
    writer_available: bool,
) -> tuple[FamilyClockDecision, ...]:
    """Evaluate every declared family, in a deterministic order."""

    families = policy.get("families")
    if not isinstance(families, Mapping) or not families:
        raise FamilyClockError("FAMILY_CLOCK_POLICY_INVALID")
    return tuple(
        evaluate_family_clock(
            family_id, families[family_id], sources, writer_available=writer_available
        )
        for family_id in sorted(families)
    )


def build_activation_payload(
    decision: FamilyClockDecision,
    *,
    policy_version: str,
    policy_sha256: str,
    evaluated_at: str,
    accrual_start_known_at: str | None = None,
) -> dict[str, Any]:
    """Build one activation-receipt payload for one evaluated family.

    An open clock accrues from ``accrual_start_known_at``, which defaults to the
    evaluation instant and may never precede it.  A closed clock records no
    start at all, because it accrues nothing.
    """

    if decision.opened:
        started: str | None = (
            accrual_start_known_at if accrual_start_known_at is not None else evaluated_at
        )
    else:
        started = None
    return {
        "contract_id": FAMILY_CLOCK_ACTIVATION_CONTRACT_ID,
        "schema_version": "1.0.0",
        "family_id": decision.family_id,
        "policy_version": policy_version,
        "policy_sha256": policy_sha256,
        "clock_state": decision.clock_state,
        "evaluated_at": evaluated_at,
        "accrual_start_known_at": started,
        "satisfied_preconditions": list(decision.satisfied_preconditions),
        "unsatisfied_preconditions": list(decision.unsatisfied_preconditions),
        "blockers": list(decision.blockers),
        "ineligible_source_ids": list(decision.ineligible_source_ids),
        "backfill": "forbidden_no_history_recorded",
        "authority": "facts_and_context_only",
    }


def activation_idempotency_key(
    decision: FamilyClockDecision, *, policy_version: str, evaluated_at: str
) -> str:
    """One evaluation, one key: same policy + same day + same family = one record."""

    day = evaluated_at[:10].replace("-", "")
    return f"bcm0a:clock:{policy_version}:{day}:{decision.family_id}"


def record_family_clock_activations(
    store: OperationalStore,
    decisions: Sequence[FamilyClockDecision],
    *,
    policy_version: str,
    policy_sha256: str,
    evaluated_at: str,
    recorded_at: str | None = None,
    accrual_start_known_at: str | None = None,
) -> tuple[AppendReceipt, ...]:
    """Append one activation receipt per evaluated family through the O1a writer.

    Re-running the same evaluation is a no-op returning the same content
    addresses; a DIFFERENT answer under the same policy version and day fails
    closed rather than quietly replacing the earlier receipt.
    """

    receipts: list[AppendReceipt] = []
    for decision in decisions:
        payload = build_activation_payload(
            decision,
            policy_version=policy_version,
            policy_sha256=policy_sha256,
            evaluated_at=evaluated_at,
            accrual_start_known_at=accrual_start_known_at,
        )
        receipts.append(
            store.append(
                FAMILY_CLOCK_ACTIVATION_RECORD_KIND,
                payload,
                idempotency_key=activation_idempotency_key(
                    decision, policy_version=policy_version, evaluated_at=evaluated_at
                ),
                recorded_at=recorded_at,
            )
        )
    return tuple(receipts)
