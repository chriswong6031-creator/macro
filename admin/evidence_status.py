"""Pure A1 evidence-disposition derivation for the existing Intelligence OS view.

This module owns no evidence. It accepts one canonical T1 cell, its T4 output-health
records, and an optional read from an already-existing owner provider. The result is a
display projection only: no score, promotion, persistence, model judgement, or file IO.
"""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


EVIDENCE_STATUS_ORDER: tuple[str, ...] = (
    "Validated",
    "Accruing",
    "Ungraded by design",
    "Degraded",
    "Disproven",
)

_TERMINAL_STATES = frozenset({"falsified", "retired"})
_UNTRUSTWORTHY_HEALTH = frozenset({"degraded", "stale", "unavailable"})
_PROVIDER_BLIND = frozenset({"could_not_look", "unreadable", "partial", "error"})
_LEGACY_CLOCK = "legacy_calendar_unstamped"


def _dedupe(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def qledger_family_for_cell(
    cell: Mapping[str, Any], adapter_families: Sequence[str]
) -> str | None:
    """Resolve an existing qledger owner binding without an engine-name registry.

    Direct T1 qledger bindings carry their desk explicitly. The three P3 adapters own
    their family vocabulary; an owner-native T1 ledger joins only when its immediate
    directory name exactly matches one of those existing family names. No fuzzy producer,
    owner-program, or path-substring matching is admitted.
    """
    ledger = str(cell.get("ledger") or "")
    ledger_evidence = cell.get("ledger_evidence") or {}
    desk = (
        str(ledger_evidence.get("desk") or "").strip()
        if isinstance(ledger_evidence, Mapping)
        else ""
    )
    if ledger.startswith("qledger:") and desk and ledger == f"qledger:{desk}":
        return desk

    if not ledger or ledger == "none" or ledger.startswith("qledger:"):
        return None
    candidate = PurePosixPath(ledger).parent.name
    allowed = {str(family) for family in adapter_families}
    return candidate if candidate in allowed else None


def _clock_market(clock_basis: Any) -> str | None:
    text = str(clock_basis or "")
    parts = text.split(":")
    if len(parts) == 3 and parts[0] == "explicit_unit_v1":
        return parts[2] or None
    return None


def _provider_readiness(provider: Mapping[str, Any] | None) -> dict[str, dict]:
    if not isinstance(provider, Mapping):
        return {}
    raw = provider.get("readiness") or {}
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(horizon): dict(row)
        for horizon, row in raw.items()
        if isinstance(row, Mapping) and not str(horizon).startswith("_")
    }


def _declared_horizon(cell: Mapping[str, Any], provider: Mapping[str, Any] | None) -> int | None:
    clock = provider.get("clock_start") if isinstance(provider, Mapping) else None
    if isinstance(clock, Mapping):
        try:
            value = int(clock.get("declared_horizon_d"))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass

    declared = cell.get("declared_horizon") or {}
    raw = declared.get("horizon_d") if isinstance(declared, Mapping) else None
    values = raw if isinstance(raw, (list, tuple, set)) else [raw]
    parsed: list[int] = []
    for value in values:
        try:
            value_i = int(value)
        except (TypeError, ValueError):
            continue
        if value_i > 0:
            parsed.append(value_i)
    return max(parsed) if parsed else None


def _ruler_row(
    readiness: Mapping[str, Mapping[str, Any]], declared_horizon: int | None
) -> tuple[str | None, Mapping[str, Any] | None]:
    candidates: list[tuple[int, str, Mapping[str, Any]]] = []
    for key, row in readiness.items():
        try:
            horizon = int(key)
        except (TypeError, ValueError):
            continue
        if declared_horizon is None or horizon <= declared_horizon:
            candidates.append((horizon, key, row))
    if not candidates:
        return None, None
    _horizon, key, row = max(candidates, key=lambda item: item[0])
    return key, row


def _basis_context(readiness: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    available: set[str] = set()
    selected: dict[str, Any] = {}
    evidence_bases: dict[str, Any] = {}
    pooling_refused = False
    mixed_explicit = False

    for horizon, row in readiness.items():
        basis = row.get("clock_basis")
        if basis:
            selected[horizon] = basis
            available.add(str(basis))
        if row.get("evidence_basis") is not None:
            evidence_bases[horizon] = row.get("evidence_basis")

        row_bases: set[str] = set()
        by_basis = row.get("by_clock_basis") or {}
        if isinstance(by_basis, Mapping):
            row_bases.update(str(k) for k in by_basis)
        prior = row.get("clock_prior_n_dates") or {}
        if isinstance(prior, Mapping):
            row_bases.update(str(k) for k in prior)
        raw_bases = row.get("clock_bases") or []
        if isinstance(raw_bases, (list, tuple, set)):
            row_bases.update(str(k) for k in raw_bases)
        available.update(row_bases)

        explicit = {b for b in row_bases if b != _LEGACY_CLOCK}
        row_refused = bool(row.get("pooling_refused")) or (
            row.get("clock_basis") is None and len(explicit) >= 2
        )
        pooling_refused = pooling_refused or row_refused
        mixed_explicit = mixed_explicit or (
            row.get("clock_basis") is None and len(explicit) >= 2
        )

    return {
        "clock_basis_by_horizon": selected,
        "evidence_basis_by_horizon": evidence_bases,
        "pooling_refused": pooling_refused,
        "mixed_explicit": mixed_explicit,
        "available_clock_bases": sorted(available),
    }


def _maturity_context(
    cell: Mapping[str, Any], readiness: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    keys = (
        "n_dates",
        "needed",
        "ready",
        "approaching",
        "projected_ready_date",
    )
    return {
        "validation_state": cell.get("validation_state"),
        "rungs": {
            horizon: {key: row.get(key) for key in keys}
            for horizon, row in sorted(readiness.items())
        },
    }


def _coverage_context(readiness: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    keys = (
        "control_coverage",
        "n_cohort_dates",
        "n_controlled_dates",
        "n_cohort_rows",
        "n_controlled_rows",
        "n_control_refused_rows",
        "n_control_refused_dates",
        "cohort_rowless",
    )
    return {
        "by_horizon": {
            horizon: {key: row.get(key) for key in keys}
            for horizon, row in sorted(readiness.items())
            if any(row.get(key) is not None for key in keys)
        }
    }


def derive_evidence_status(
    cell: Mapping[str, Any],
    outputs: Sequence[Mapping[str, Any]],
    provider: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive one truthful A1 display disposition from existing owner facts."""
    reasons: list[str] = []
    refs: list[Any] = []

    raw_refs = cell.get("evidence_ref")
    if isinstance(raw_refs, (list, tuple, set)):
        refs.extend(raw_refs)
    elif raw_refs:
        refs.append(raw_refs)
    ledger = cell.get("ledger")
    if ledger and ledger != "none":
        refs.append(f"ledger:{ledger}")

    validation = str(cell.get("validation_state") or "")
    validation_evidence = cell.get("validation_state_evidence") or {}
    if isinstance(validation_evidence, Mapping):
        for bound in validation_evidence.get("bound_species") or []:
            if isinstance(bound, Mapping) and bound.get("species_id"):
                refs.append(f"species:{bound['species_id']}")
        if validation_evidence.get("dnr_key"):
            refs.append(validation_evidence.get("dnr_key"))

    readiness = _provider_readiness(provider)
    basis = _basis_context(readiness)
    declared_horizon = _declared_horizon(cell, provider)
    ruler_key, ruler_row = _ruler_row(readiness, declared_horizon)

    clock_start = provider.get("clock_start") if isinstance(provider, Mapping) else None
    if isinstance(clock_start, Mapping):
        family = clock_start.get("claim_family") or provider.get("family")
        started = clock_start.get("first_prospective_registration_utc")
        if family and started:
            refs.append(f"qledger-clock:{family}:{started}")
        if clock_start.get("git_sha"):
            refs.append(f"git:{clock_start['git_sha']}")

    health_blocked = False
    if not outputs:
        health_blocked = True
        reasons.append("health_no_outputs")
    for output in outputs:
        state = output.get("state")
        assessment = output.get("assessment_status")
        if state in _UNTRUSTWORTHY_HEALTH:
            health_blocked = True
            reasons.append(f"health_{state}")
        elif state not in (None, "healthy"):
            health_blocked = True
            reasons.append("health_unknown_state")
        if assessment == "could_not_look":
            health_blocked = True
            reasons.append("health_blind")

    provider_read = (
        str(provider.get("read_status") or "ok") if isinstance(provider, Mapping) else None
    )
    provider_blocked = provider_read in _PROVIDER_BLIND
    if provider_blocked:
        reasons.append("evidence_provider_unreadable")

    mixed_basis = bool(basis.pop("mixed_explicit"))
    if mixed_basis:
        reasons.append("mixed_clock_basis_refused")

    selected_ready = None if ruler_row is None else bool(ruler_row.get("ready"))
    immature = ruler_row is not None and not selected_ready
    if immature and not mixed_basis:
        reasons.append("insufficient_maturity")

    if isinstance(provider, Mapping) and provider.get("kind") == "qledger":
        binding = str(provider.get("binding") or "")
        if binding.startswith("adapter:") and not isinstance(clock_start, Mapping):
            reasons.append("evidence_clock_not_started")
            immature = True
        elif not readiness:
            reasons.append("evidence_not_started")
            immature = True

    output_class = cell.get("output_class")
    if output_class is None:
        reasons.append("output_class_null")

    semantic_ungraded = (
        cell.get("graded_by_design") == "no — descriptive"
        and bool(str(cell.get("graded_by_design_source") or "").strip())
    )

    if validation in _TERMINAL_STATES:
        status = "Disproven"
        reasons.insert(0, f"owner_terminal_{validation}")
    elif health_blocked or provider_blocked:
        status = "Degraded"
    elif mixed_basis or immature:
        status = "Accruing"
    elif output_class is not None and validation == "validated":
        status = "Validated"
        reasons.append("owner_validated")
    elif semantic_ungraded:
        status = "Ungraded by design"
        reasons.append("t1_semantic_ungraded")
    else:
        status = "Accruing"
        reasons.append(
            f"owner_lifecycle_{validation}" if validation else "owner_lifecycle_unknown"
        )

    qledger_clock = None
    if isinstance(clock_start, Mapping):
        qledger_clock = {
            "horizon_d": clock_start.get("declared_horizon_d"),
            "horizon_unit": clock_start.get("horizon_unit"),
            "clock_market": _clock_market(
                None if ruler_row is None else ruler_row.get("clock_basis")
            ),
        }

    provider_summary = {
        "kind": (
            provider.get("kind") if isinstance(provider, Mapping) else "t1_owner_native"
        ),
        "binding": provider.get("binding") if isinstance(provider, Mapping) else None,
        "family": provider.get("family") if isinstance(provider, Mapping) else None,
        "read_status": provider_read or "ok",
    }

    return {
        "evidence_status": status,
        "evidence_reason_codes": _dedupe(reasons),
        "evidence_refs": _dedupe(refs),
        "evidence_provider": provider_summary,
        "evidence_ruler": {
            "declared_horizon": cell.get("declared_horizon"),
            "selected_qledger_rung": ruler_key,
            "qledger_clock": qledger_clock,
        },
        "evidence_basis": basis,
        "evidence_maturity": _maturity_context(cell, readiness),
        "evidence_coverage": _coverage_context(readiness),
    }


def build_ceo_view(engine_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """All five evidence bands, ordered by the frozen evidence-strength contract."""
    grouped: dict[str, list[str]] = {status: [] for status in EVIDENCE_STATUS_ORDER}
    for row in engine_rows:
        status = str(row.get("evidence_status") or "")
        if status not in grouped:
            status = "Degraded"
        grouped[status].append(str(row.get("engine_id") or ""))
    return [
        {
            "evidence_status": status,
            "n_engines": len(grouped[status]),
            "engine_ids": sorted(grouped[status]),
        }
        for status in EVIDENCE_STATUS_ORDER
    ]
