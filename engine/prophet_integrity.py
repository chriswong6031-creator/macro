"""Append-only correction projection for Prophet trade plans.

The plan JSON files are publication records.  They are deliberately never rewritten
when a later audit proves that one of their date fields meant something different.
Corrections live in ``data/prophet/plan_corrections.jsonl`` and are applied only to an
in-memory *effective* projection used by management, grading and the index.

One row corrects one field on one plan.  The original value must still match the raw
plan, so a stale or mis-targeted correction fails closed instead of silently moving a
different record.  Plan identity fields can never be corrected: historical IDs remain
stable even when the date embedded in an old ID was semantically misnamed.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


PLAN_CORRECTION_SCHEMA = "prophet.plan_correction/v1"
PLAN_CORRECTIONS_FILENAME = "plan_corrections.jsonl"
LEDGER_CORRECTION_SCHEMA = "prophet.ledger_correction/v1"
LEDGER_CORRECTIONS_FILENAME = "ledger_corrections.jsonl"
LEDGER_QUARANTINE_SCHEMA = "prophet.ledger_quarantine/v1"
LEDGER_QUARANTINE_FILENAME = "ledger_quarantine.json"

# A reconstructed plan was produced by the bounded outage-replay lane rather than by
# the live nightly publisher.  This predicate lives in the stdlib-only integrity
# module so lightweight readers (especially the minimal marketing CI environment) can
# enforce the provenance boundary without importing prophet_bridge and its pandas
# execution stack.
RECONSTRUCTED_ORIGINATION_PREFIX = "outage_backfill"


def is_reconstructed(row: Mapping[str, Any] | None) -> bool:
    """Return whether *row* was reconstructed after an outage."""
    if not isinstance(row, Mapping):
        return False
    mode = row.get("origination_mode")
    return isinstance(mode, str) and mode.startswith(
        RECONSTRUCTED_ORIGINATION_PREFIX
    )

# Identity and geometry are publication facts.  A date audit may add/correct clocks and
# integrity disposition, but it may not turn an old plan into a different trade.
CORRECTABLE_FIELDS = frozenset({
    "formation_date",
    "signal_date",
    "confirmed_date",
    "source_marker_date",
    "signal_tier",
    "signal_date_basis",
    "recorded_at",
    "price_basis_date",
    "entry_date",
    "integrity_status",
    "integrity_reason",
})
DATE_FIELDS = frozenset({
    "formation_date",
    "signal_date",
    "confirmed_date",
    "source_marker_date",
    "recorded_at",
    "price_basis_date",
    "entry_date",
})
LEDGER_CORRECTABLE_FIELDS = frozenset({
    "formation_date",
    "signal_date",
    "confirmed_date",
    "source_marker_date",
    "signal_tier",
    "signal_date_basis",
    "recorded_at",
    "price_basis_date",
    "entry_date",
    "integrity_status",
    "integrity_reason",
})
QUARANTINED = "quarantined"
INTEGRITY_STATUSES = frozenset({
    "audited_current",
    "audited_mixed_vintage",
    QUARANTINED,
})
SIGNAL_TIERS = frozenset({"T1", "T2", "T3", "T4"})
SIGNAL_DATE_BASES = frozenset({
    "tier_event_date",
    "tier_observation",
    "legacy_formation_alias",
})


class PlanCorrectionError(ValueError):
    """A correction ledger is malformed, ambiguous, or targets the wrong raw fact."""


def effective_public_plan_date(plan: Mapping[str, Any]) -> str | None:
    """Return the strict family-native date safe for public freshness/markers.

    A legacy ``signal_date`` is often the immutable formation anchor embedded in
    the plan id, not a live call date. Public readers must therefore never fall back
    across date families: fired T1/T2 rows use their event date, T3 uses its
    observation date, and audited legacy rows use the evidenced entry-price session.
    Missing/unknown families return ``None`` so a public claim is withheld rather
    than guessed.
    """
    if not isinstance(plan, Mapping):
        return None
    basis = plan.get("signal_date_basis")
    if basis == "tier_event_date":
        value = plan.get("signal_date")
    elif basis == "tier_observation":
        value = plan.get("observed_date")
    elif basis == "legacy_formation_alias":
        value = plan.get("price_basis_date") or plan.get("entry_date")
    else:
        return None
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return value if parsed.isoformat() == value else None


@dataclass(frozen=True)
class CorrectionProjection:
    """Effective plan view plus a machine-readable application receipt."""

    plans: dict[str, dict[str, Any]]
    applied_by_plan: dict[str, tuple[str, ...]]
    quarantined_ids: frozenset[str]


@dataclass(frozen=True)
class LedgerCorrectionProjection:
    """Effective ledger rows plus correction application provenance."""

    rows: tuple[dict[str, Any], ...]
    applied_by_id: dict[str, tuple[str, ...]]
    quarantined_ids: frozenset[str]


def load_effective_plans(repo_root: str | Path) -> CorrectionProjection:
    """Canonical corrected plan view for readers outside the nightly publisher."""
    root = Path(repo_root)
    raw: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "site/prophet/plans").glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PlanCorrectionError(f"unreadable plan publication {path}: {exc}") from exc
        if row.get("schema") == "prophet.trade_plan/v1" and row.get("id"):
            raw[str(row["id"])] = row
    corrections = load_plan_corrections(
        root / "data/prophet" / PLAN_CORRECTIONS_FILENAME
    )
    return apply_plan_corrections(raw, corrections)


def load_effective_ledger(repo_root: str | Path) -> LedgerCorrectionProjection:
    """Canonical corrected forward-ledger view; raw JSONL remains untouched."""
    root = Path(repo_root)
    path = root / "data/prophet/ledger.jsonl"
    raw: list[dict[str, Any]] = []
    if path.exists():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise PlanCorrectionError(
                    f"invalid prophet ledger JSON on line {lineno}"
                ) from exc
            if not isinstance(row, dict):
                raise PlanCorrectionError(
                    f"prophet ledger line {lineno} is not an object"
                )
            raw.append(row)
    corrections = load_ledger_corrections(
        root / "data/prophet" / LEDGER_CORRECTIONS_FILENAME
    )
    projection = apply_ledger_corrections(raw, corrections)
    legacy_quarantines = load_ledger_quarantined_ids(
        root / "data/prophet" / LEDGER_QUARANTINE_FILENAME
    )
    return LedgerCorrectionProjection(
        rows=projection.rows,
        applied_by_id=projection.applied_by_id,
        quarantined_ids=frozenset(
            set(projection.quarantined_ids) | set(legacy_quarantines)
        ),
    )


def load_ledger_quarantined_ids(path: str | Path) -> frozenset[str]:
    """Strictly load the pre-correction ledger exclusion receipt.

    This receipt predates ``ledger_corrections.jsonl`` and remains authoritative for
    outcomes proven to have been graded before their plans existed. Returning an empty
    set on malformed input would silently rehabilitate those rows, so canonical readers
    fail closed. Absence alone means the repository predates the receipt and is valid.
    """
    p = Path(path)
    if not p.exists():
        return frozenset()
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanCorrectionError(f"unreadable ledger quarantine {p}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise PlanCorrectionError("ledger quarantine must be an object")
    if payload.get("schema") != LEDGER_QUARANTINE_SCHEMA:
        raise PlanCorrectionError("unknown ledger quarantine schema")
    rows = payload.get("quarantined")
    if not isinstance(rows, list):
        raise PlanCorrectionError("ledger quarantine rows must be a list")
    declared = payload.get("count")
    if not isinstance(declared, int) or isinstance(declared, bool) or declared != len(rows):
        raise PlanCorrectionError(
            "ledger quarantine count must equal the number of rows"
        )
    ids: set[str] = set()
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise PlanCorrectionError(
                f"ledger quarantine row {position} must be an object"
            )
        plan_id = row.get("id")
        reason = row.get("reason")
        if (
            not isinstance(plan_id, str)
            or not plan_id.strip()
            or plan_id != plan_id.strip()
        ):
            raise PlanCorrectionError(
                f"ledger quarantine row {position} requires a canonical id"
            )
        if not isinstance(reason, str) or not reason.strip():
            raise PlanCorrectionError(
                f"ledger quarantine row {position} requires a reason"
            )
        if plan_id in ids:
            raise PlanCorrectionError(
                f"ledger quarantine contains duplicate id: {plan_id}"
            )
        ids.add(plan_id)
    return frozenset(ids)


def _iso_date(value: Any, *, label: str, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str):
        raise PlanCorrectionError(f"{label} must be an ISO date string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise PlanCorrectionError(f"{label} is not an ISO date: {value!r}") from exc
    if parsed.isoformat() != value:
        raise PlanCorrectionError(f"{label} must be canonical YYYY-MM-DD: {value!r}")


def validate_plan_correction(row: Mapping[str, Any], *, line: int | None = None) -> None:
    prefix = f"line {line}: " if line is not None else ""
    if row.get("schema") != PLAN_CORRECTION_SCHEMA:
        raise PlanCorrectionError(prefix + "unknown correction schema")
    for key in ("id", "corrects_id", "field", "basis", "corrected_at"):
        if not isinstance(row.get(key), str) or not str(row.get(key)).strip():
            raise PlanCorrectionError(prefix + f"{key} is required")
    field = str(row["field"])
    if field not in CORRECTABLE_FIELDS:
        raise PlanCorrectionError(prefix + f"field is not correctable: {field}")
    if "old_value" not in row or "new_value" not in row:
        raise PlanCorrectionError(prefix + "old_value and new_value are required")
    _iso_date(row["corrected_at"], label=prefix + "corrected_at")
    if field in DATE_FIELDS:
        _iso_date(
            row["new_value"],
            label=prefix + f"new_value for {field}",
            nullable=field == "confirmed_date",
        )
        if row["old_value"] is not None:
            _iso_date(row["old_value"], label=prefix + f"old_value for {field}")
    elif field == "integrity_status":
        if (
            not isinstance(row["new_value"], str)
            or row["new_value"] not in INTEGRITY_STATUSES
        ):
            raise PlanCorrectionError(
                prefix + f"unknown integrity_status: {row['new_value']!r}"
            )
    elif field == "integrity_reason" and (
        not isinstance(row["new_value"], str) or not row["new_value"].strip()
    ):
        raise PlanCorrectionError(prefix + "integrity_reason must be a non-empty string")
    elif field == "signal_tier":
        if not isinstance(row["new_value"], str) or row["new_value"] not in SIGNAL_TIERS:
            raise PlanCorrectionError(
                prefix + f"unknown signal_tier: {row['new_value']!r}"
            )
    elif field == "signal_date_basis":
        if (
            not isinstance(row["new_value"], str)
            or row["new_value"] not in SIGNAL_DATE_BASES
        ):
            raise PlanCorrectionError(
                prefix + f"unknown signal_date_basis: {row['new_value']!r}"
            )
    evidence = row.get("evidence")
    if not isinstance(evidence, Mapping) or not evidence:
        raise PlanCorrectionError(prefix + "evidence must be a non-empty object")


def validate_ledger_correction(
    row: Mapping[str, Any], *, line: int | None = None
) -> None:
    """Validate one append-only ledger correction row."""
    prefix = f"line {line}: " if line is not None else ""
    if row.get("schema") != LEDGER_CORRECTION_SCHEMA:
        raise PlanCorrectionError(prefix + "unknown ledger correction schema")
    for key in ("id", "corrects_id", "field", "basis", "corrected_at"):
        if not isinstance(row.get(key), str) or not str(row.get(key)).strip():
            raise PlanCorrectionError(prefix + f"{key} is required")
    field = str(row["field"])
    if field not in LEDGER_CORRECTABLE_FIELDS:
        raise PlanCorrectionError(prefix + f"ledger field is not correctable: {field}")
    if "old_value" not in row or "new_value" not in row:
        raise PlanCorrectionError(prefix + "old_value and new_value are required")
    _iso_date(row["corrected_at"], label=prefix + "corrected_at")
    if field in DATE_FIELDS:
        _iso_date(
            row["new_value"],
            label=prefix + f"new_value for {field}",
            nullable=field == "confirmed_date",
        )
        if row["old_value"] is not None:
            _iso_date(row["old_value"], label=prefix + f"old_value for {field}")
    elif field == "integrity_status":
        if (
            not isinstance(row["new_value"], str)
            or row["new_value"] not in INTEGRITY_STATUSES
        ):
            raise PlanCorrectionError(
                prefix + f"unknown integrity_status: {row['new_value']!r}"
            )
    elif field == "integrity_reason" and (
        not isinstance(row["new_value"], str) or not row["new_value"].strip()
    ):
        raise PlanCorrectionError(prefix + "integrity_reason must be a non-empty string")
    elif field == "signal_tier":
        if not isinstance(row["new_value"], str) or row["new_value"] not in SIGNAL_TIERS:
            raise PlanCorrectionError(
                prefix + f"unknown signal_tier: {row['new_value']!r}"
            )
    elif field == "signal_date_basis":
        if (
            not isinstance(row["new_value"], str)
            or row["new_value"] not in SIGNAL_DATE_BASES
        ):
            raise PlanCorrectionError(
                prefix + f"unknown signal_date_basis: {row['new_value']!r}"
            )
    evidence = row.get("evidence")
    if not isinstance(evidence, Mapping) or not evidence:
        raise PlanCorrectionError(prefix + "evidence must be a non-empty object")


def _load_correction_rows(
    path: str | Path,
    *,
    validator: Any,
) -> list[dict[str, Any]]:
    """Shared strict JSONL reader for plan and ledger correction stores."""
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    targets: set[tuple[str, str]] = set()
    with p.open(encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text or text.startswith("#"):
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise PlanCorrectionError(f"line {lineno}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise PlanCorrectionError(f"line {lineno}: correction must be an object")
            validator(row, line=lineno)
            correction_id = str(row["id"])
            target = (str(row["corrects_id"]), str(row["field"]))
            if correction_id in ids:
                raise PlanCorrectionError(
                    f"line {lineno}: duplicate correction id {correction_id}"
                )
            if target in targets:
                raise PlanCorrectionError(
                    f"line {lineno}: duplicate correction target {target[0]}.{target[1]}"
                )
            ids.add(correction_id)
            targets.add(target)
            rows.append(row)
    return rows


def load_plan_corrections(path: str | Path) -> list[dict[str, Any]]:
    """Read and validate the append-only JSONL ledger.

    Blank lines and ``#`` comments are accepted.  Duplicate row IDs and duplicate
    ``(corrects_id, field)`` targets are rejected: a correction cannot silently revise
    another correction.  If a future fact changes again it needs an explicit v2
    supersession contract, not last-write-wins behavior hidden in file order.
    """
    return _load_correction_rows(path, validator=validate_plan_correction)


def load_ledger_corrections(path: str | Path) -> list[dict[str, Any]]:
    """Read and validate the append-only forward-ledger correction store."""
    return _load_correction_rows(path, validator=validate_ledger_correction)


def _validated_sequence(
    corrections: Iterable[Mapping[str, Any]],
    *,
    validator: Any,
) -> list[Mapping[str, Any]]:
    """Validate an arbitrary in-memory sequence as strictly as the JSONL loader."""
    rows = list(corrections)
    ids: set[str] = set()
    targets: set[tuple[str, str]] = set()
    for position, row in enumerate(rows, start=1):
        validator(row, line=position)
        correction_id = str(row["id"])
        target = (str(row["corrects_id"]), str(row["field"]))
        if correction_id in ids:
            raise PlanCorrectionError(f"duplicate correction id {correction_id}")
        if target in targets:
            raise PlanCorrectionError(
                f"duplicate correction target {target[0]}.{target[1]}"
            )
        ids.add(correction_id)
        targets.add(target)
    return rows


def _validate_effective_chronology(row: Mapping[str, Any], *, label: str) -> None:
    """Reject a correction projection that creates impossible temporal ordering."""
    parsed: dict[str, date] = {}
    for field in DATE_FIELDS:
        value = row.get(field)
        if value is None:
            continue
        try:
            parsed[field] = date.fromisoformat(str(value))
        except ValueError as exc:
            raise PlanCorrectionError(f"{label}.{field} is not an ISO date") from exc
    price_basis = parsed.get("price_basis_date")
    entry = parsed.get("entry_date")
    recorded = parsed.get("recorded_at")
    signal = parsed.get("signal_date")
    confirmed = parsed.get("confirmed_date")
    formation = parsed.get("formation_date")
    if price_basis and recorded and price_basis > recorded:
        raise PlanCorrectionError(f"{label}: price_basis_date postdates recorded_at")
    if entry and price_basis and entry != price_basis:
        raise PlanCorrectionError(f"{label}: entry_date must equal price_basis_date")
    if formation and signal and formation > signal:
        raise PlanCorrectionError(f"{label}: formation_date postdates signal_date")
    if signal and confirmed and signal > confirmed:
        raise PlanCorrectionError(f"{label}: signal_date postdates confirmed_date")
    if confirmed and recorded and confirmed > recorded:
        raise PlanCorrectionError(f"{label}: confirmed_date postdates recorded_at")
    if row.get("integrity_status") == QUARANTINED and not str(
        row.get("integrity_reason") or ""
    ).strip():
        raise PlanCorrectionError(f"{label}: quarantined disposition requires a reason")


def apply_plan_corrections(
    plans: Mapping[str, Mapping[str, Any]],
    corrections: Iterable[Mapping[str, Any]],
) -> CorrectionProjection:
    """Return an effective copy of ``plans`` with validated corrections applied.

    Raw input dictionaries are never mutated.  Every correction's ``old_value`` is
    compared with the raw publication record, not a previously corrected projection.
    That makes an overlay reproducible and catches accidental edits to the source plan.
    """
    raw = {str(plan_id): dict(plan) for plan_id, plan in plans.items()}
    effective = {plan_id: deepcopy(plan) for plan_id, plan in raw.items()}
    applied: dict[str, list[str]] = {}

    correction_rows = _validated_sequence(
        corrections, validator=validate_plan_correction
    )
    for row in correction_rows:
        plan_id = str(row["corrects_id"])
        if plan_id not in raw:
            raise PlanCorrectionError(f"correction targets absent plan: {plan_id}")
        field = str(row["field"])
        published = raw[plan_id].get(field)
        if published != row.get("old_value"):
            raise PlanCorrectionError(
                f"{row['id']}: old_value mismatch for {plan_id}.{field}: "
                f"ledger={row.get('old_value')!r}, published={published!r}"
            )
        effective[plan_id][field] = deepcopy(row.get("new_value"))
        applied.setdefault(plan_id, []).append(str(row["id"]))

    for plan_id in applied:
        _validate_effective_chronology(effective[plan_id], label=f"plan {plan_id}")

    quarantined = frozenset(
        plan_id
        for plan_id, plan in effective.items()
        if plan.get("integrity_status") == QUARANTINED
    )
    return CorrectionProjection(
        plans=effective,
        applied_by_plan={k: tuple(v) for k, v in applied.items()},
        quarantined_ids=quarantined,
    )


def apply_ledger_corrections(
    rows: Iterable[Mapping[str, Any]],
    corrections: Iterable[Mapping[str, Any]],
) -> LedgerCorrectionProjection:
    """Apply date/disposition corrections to an in-memory ledger projection.

    The source ``ledger.jsonl`` stays byte-for-byte append-only.  Prophet writes at most
    one terminal row per plan ID; duplicate raw IDs fail closed because a correction
    would otherwise be ambiguous about which close event it targeted.
    """
    raw_rows = [dict(row) for row in rows]
    positions: dict[str, int] = {}
    for index, row in enumerate(raw_rows):
        plan_id = str(row.get("id") or "")
        if not plan_id:
            continue
        if plan_id in positions:
            raise PlanCorrectionError(f"ledger contains duplicate terminal id: {plan_id}")
        positions[plan_id] = index
    effective = [deepcopy(row) for row in raw_rows]
    applied: dict[str, list[str]] = {}

    correction_rows = _validated_sequence(
        corrections, validator=validate_ledger_correction
    )
    for row in correction_rows:
        plan_id = str(row["corrects_id"])
        if plan_id not in positions:
            raise PlanCorrectionError(f"ledger correction targets absent row: {plan_id}")
        field = str(row["field"])
        raw = raw_rows[positions[plan_id]]
        if raw.get(field) != row.get("old_value"):
            raise PlanCorrectionError(
                f"{row['id']}: old_value mismatch for ledger {plan_id}.{field}: "
                f"ledger={row.get('old_value')!r}, published={raw.get(field)!r}"
            )
        effective[positions[plan_id]][field] = deepcopy(row.get("new_value"))
        applied.setdefault(plan_id, []).append(str(row["id"]))

    for plan_id in applied:
        _validate_effective_chronology(
            effective[positions[plan_id]], label=f"ledger {plan_id}"
        )

    quarantined = frozenset(
        str(row.get("id"))
        for row in effective
        if row.get("integrity_status") == QUARANTINED and row.get("id")
    )
    return LedgerCorrectionProjection(
        rows=tuple(effective),
        applied_by_id={key: tuple(value) for key, value in applied.items()},
        quarantined_ids=quarantined,
    )
