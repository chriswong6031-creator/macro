"""Narrow W1-A composability fixtures over typed resolver envelopes.

These helpers deliberately do not parse natural language, read owner artifacts,
or define a general query language.  They consume resolver output verbatim so
cross-consumer semantic drift is testable before any later consumer wave.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import DatapointContractError, VALUE_SCHEMA, thaw


PARITY_KEYS = (
    "registry_digest",
    "field_id",
    "entity",
    "value",
    "status",
    "unit",
    "observed_at",
    "effective_at",
    "as_of",
    "fact_fingerprint",
)


def _validate_fixture_envelopes(envelopes: Sequence[Mapping[str, Any]]) -> None:
    if not envelopes:
        raise DatapointContractError("fixture consumer requires at least one envelope")
    for envelope in envelopes:
        if envelope.get("schema") != VALUE_SCHEMA:
            raise DatapointContractError("fixture consumer accepts datapoint_value.v1 only")


def parity_projection(envelopes: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Return the exact fact surface shared by direct/query/Brain fixtures."""
    _validate_fixture_envelopes(envelopes)
    projected: list[dict[str, Any]] = []
    for envelope in envelopes:
        row = {key: thaw(envelope[key]) for key in PARITY_KEYS}
        row["source_id"] = envelope["source"]["source_id"]
        row["quality_state"] = envelope["quality"]["state"]
        projected.append(row)
    return tuple(projected)


def evaluate_stage_momentum_fixture(
    envelopes: Sequence[Mapping[str, Any]],
    *,
    stage: int = 2,
    minimum_return_3m_pct: float = 15.0,
) -> dict[str, Any]:
    """Evaluate the one commissioned fixture predicate, not a query kernel."""
    _validate_fixture_envelopes(envelopes)
    if len(envelopes) != 2:
        raise DatapointContractError(
            "stage/momentum fixture requires exactly two non-duplicate envelopes"
        )
    field_ids = [str(row["field_id"]) for row in envelopes]
    if len(set(field_ids)) != len(field_ids):
        raise DatapointContractError("stage/momentum fixture rejects duplicate fields")
    by_field = {str(row["field_id"]): row for row in envelopes}
    if set(by_field) != {"stage.current", "market.return.3m"}:
        raise DatapointContractError(
            "stage/momentum fixture requires exactly stage.current and market.return.3m"
        )
    stage_row = by_field["stage.current"]
    return_row = by_field["market.return.3m"]
    if stage_row["entity"] != return_row["entity"]:
        raise DatapointContractError("fixture fields must address the same canonical entity")
    if stage_row["unit"] != "stage_code" or return_row["unit"] != "percent":
        raise DatapointContractError("fixture refuses unit drift")
    available = stage_row["status"] == return_row["status"] == "available"
    matched = bool(
        available
        and stage_row["value"] == stage
        and return_row["value"] >= minimum_return_3m_pct
    )
    return {
        "fixture": "stage_momentum.v1",
        "matched": matched,
        "facts": list(parity_projection(envelopes)),
    }


def build_brain_fact_packet(envelopes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a model-visible test packet from subscriber-projected facts only."""
    _validate_fixture_envelopes(envelopes)
    facts: list[dict[str, Any]] = []
    for envelope in envelopes:
        if envelope.get("audience") != "subscriber":
            raise DatapointContractError("Brain fixture accepts subscriber projection only")
        if envelope.get("status") == "rights_blocked" and envelope.get("value") is not None:
            raise DatapointContractError("rights-blocked value may not enter a Brain packet")
        facts.append(
            {
                **{key: thaw(envelope[key]) for key in PARITY_KEYS},
                "reason_code": envelope["reason_code"],
                "freshness": thaw(envelope["freshness"]),
                "source": thaw(envelope["source"]),
                "provenance": thaw(envelope["provenance"]),
                "quality_state": envelope["quality"]["state"],
            }
        )
    return {
        "schema": "intelligence_workspace.brain_fact_fixture.v1",
        "instruction": "Relay these typed facts; do not originate or recompute numeric values.",
        "facts": facts,
    }
