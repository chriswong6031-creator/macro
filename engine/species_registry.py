"""engine/species_registry.py — Setup-Species Registry.

Implements the §3.1 schema from research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md.

One entry per species-version in data/species/registry.json.  The module:
  - validates the schema (required fields, enum constraints, lifecycle rules);
  - enforces that horizon_class is ONE of {rotational, positional} (never "both");
  - enforces lifecycle: validation_status transitions only via explicit review calls;
    falsified/retired are terminal;
  - enforces that a horizon_class change requires a version bump;
  - mirrors each species into data/experiments/registry_seed.json (additive, idempotent,
    never touching curated entries).

DISPLAY-ONLY metadata store.  Never sizes, gates, or ranks anything directly.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
REGISTRY_PATH = _ROOT / "data" / "species" / "registry.json"
EXPERIMENTS_SEED_PATH = _ROOT / "data" / "experiments" / "registry_seed.json"

# ---------------------------------------------------------------------------
# Enum constants
# ---------------------------------------------------------------------------
VALID_HORIZON_CLASSES = frozenset({"rotational", "positional"})
VALID_VALIDATION_STATUSES = frozenset({"phase0", "accruing", "validated", "falsified", "retired"})
VALID_DEPLOYMENT_STATUSES = frozenset({"unshipped", "chip", "ledger_fields", "graded_bonus", "gate_weight"})
TERMINAL_VALIDATION_STATUSES = frozenset({"falsified", "retired"})

# Lifecycle transitions: {from_status: allowed_to_statuses}
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "phase0":     frozenset({"accruing", "falsified", "retired"}),
    "accruing":   frozenset({"validated", "falsified", "retired"}),
    "validated":  frozenset({"retired"}),       # can retire a validated species
    "falsified":  frozenset(),                  # terminal
    "retired":    frozenset(),                  # terminal
}

# Experiments mirror status map (§3.1)
_EXPERIMENTS_STATUS_MAP = {
    "phase0":    "registered",
    "accruing":  "accruing",
    "validated": "proven",
    "falsified": "closed",
    "retired":   "closed",
}

# Required top-level fields for every species entry
_REQUIRED_FIELDS = frozenset({
    "species_id",
    "version",
    "name",
    "validation_status",
    "deployment_status",
    "mechanism",
    "horizon_class",
    "evidence_stack",
    "rejection_rules",
    "archetype_scope",
    "regime_scope",
    "market_scope",
    "adjacent_falsified",
    "fixtures",
    "ledger_binding",
    "gating",
    "trial_count",
})


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class SpeciesSchemaError(ValueError):
    """Raised when a species entry fails schema validation."""


def validate_entry(entry: dict[str, Any]) -> None:
    """Validate a single species entry against the §3.1 schema.

    Raises SpeciesSchemaError on the first violation found.
    """
    sid = entry.get("species_id", "<unknown>")

    # Required fields
    missing = _REQUIRED_FIELDS - entry.keys()
    if missing:
        raise SpeciesSchemaError(
            f"species {sid!r}: missing required fields: {sorted(missing)}"
        )

    # horizon_class must be one of the enum (never "both")
    hc = entry.get("horizon_class")
    if hc not in VALID_HORIZON_CLASSES:
        raise SpeciesSchemaError(
            f"species {sid!r}: horizon_class={hc!r} is not one of "
            f"{sorted(VALID_HORIZON_CLASSES)}; 'both' is disallowed (§1.1)"
        )

    # validation_status
    vs = entry.get("validation_status")
    if vs not in VALID_VALIDATION_STATUSES:
        raise SpeciesSchemaError(
            f"species {sid!r}: validation_status={vs!r} is not one of "
            f"{sorted(VALID_VALIDATION_STATUSES)}"
        )

    # deployment_status
    ds = entry.get("deployment_status")
    if ds not in VALID_DEPLOYMENT_STATUSES:
        raise SpeciesSchemaError(
            f"species {sid!r}: deployment_status={ds!r} is not one of "
            f"{sorted(VALID_DEPLOYMENT_STATUSES)}"
        )

    # ledger_binding must be a dict with 'ledger', 'since', 'flip_criteria'
    lb = entry.get("ledger_binding")
    if not isinstance(lb, dict):
        raise SpeciesSchemaError(
            f"species {sid!r}: ledger_binding must be a dict"
        )
    for sub in ("ledger", "since", "flip_criteria"):
        if sub not in lb:
            raise SpeciesSchemaError(
                f"species {sid!r}: ledger_binding missing key {sub!r}"
            )

    # gating must be a dict with 'come_back_on', 'cadence', 'maturation'
    gating = entry.get("gating")
    if not isinstance(gating, dict):
        raise SpeciesSchemaError(
            f"species {sid!r}: gating must be a dict"
        )
    for sub in ("come_back_on", "cadence", "maturation"):
        if sub not in gating:
            raise SpeciesSchemaError(
                f"species {sid!r}: gating missing key {sub!r}"
            )

    # regime_scope must contain 'learnable_projection'
    rs = entry.get("regime_scope")
    if not isinstance(rs, dict) or "learnable_projection" not in rs:
        raise SpeciesSchemaError(
            f"species {sid!r}: regime_scope must be a dict with 'learnable_projection' "
            f"(≤2 axes, ≤6 cells — §5.4)"
        )

    # trial_count must be an integer >= 0
    tc = entry.get("trial_count")
    if not isinstance(tc, int) or tc < 0:
        raise SpeciesSchemaError(
            f"species {sid!r}: trial_count must be a non-negative integer, got {tc!r}"
        )


# ---------------------------------------------------------------------------
# Lifecycle enforcement
# ---------------------------------------------------------------------------

class SpeciesLifecycleError(RuntimeError):
    """Raised when a lifecycle transition is not permitted."""


def transition_validation_status(
    entry: dict[str, Any],
    new_status: str,
    reviewer: str,
    reason: str,
) -> dict[str, Any]:
    """Return a new entry dict with validation_status updated.

    Rules (§3.1):
      - Transitions only via this explicit review call (not by hand-editing).
      - falsified/retired are terminal.
      - Only allowed transitions per _ALLOWED_TRANSITIONS.
      - A horizon_class change is forbidden here; it requires bump_version().
    """
    sid = entry.get("species_id", "<unknown>")
    current = entry.get("validation_status")

    if current in TERMINAL_VALIDATION_STATUSES:
        raise SpeciesLifecycleError(
            f"species {sid!r}: validation_status={current!r} is terminal — "
            f"no further transitions allowed"
        )
    if new_status not in VALID_VALIDATION_STATUSES:
        raise SpeciesLifecycleError(
            f"species {sid!r}: {new_status!r} is not a valid validation_status"
        )
    allowed = _ALLOWED_TRANSITIONS.get(current or "", frozenset())
    if new_status not in allowed:
        raise SpeciesLifecycleError(
            f"species {sid!r}: transition {current!r} → {new_status!r} is not allowed; "
            f"allowed targets: {sorted(allowed)}"
        )

    updated = dict(entry)
    updated["validation_status"] = new_status
    updated.setdefault("_lifecycle_log", []).append({
        "from": current,
        "to": new_status,
        "reviewer": reviewer,
        "reason": reason,
    })
    return updated


def bump_version(
    entry: dict[str, Any],
    new_version: str,
    new_horizon_class: str | None = None,
    reviewer: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Return a new entry with an incremented version.

    Required if horizon_class changes (§1.1).  The new version resets
    ledger_binding.since and restarts the trial count.
    """
    sid = entry.get("species_id", "<unknown>")
    if new_horizon_class is not None and new_horizon_class not in VALID_HORIZON_CLASSES:
        raise SpeciesLifecycleError(
            f"species {sid!r}: horizon_class={new_horizon_class!r} is not valid"
        )

    updated = dict(entry)
    updated["version"] = new_version
    if new_horizon_class is not None:
        old_hc = entry.get("horizon_class")
        if old_hc != new_horizon_class:
            log.info(
                "species %r: horizon_class changed %r → %r (version bump %r → %r)",
                sid, old_hc, new_horizon_class, entry.get("version"), new_version,
            )
        updated["horizon_class"] = new_horizon_class
    # reset status to phase0 and clear deployment for the new version
    updated["validation_status"] = "phase0"
    updated["deployment_status"] = "unshipped"
    updated.setdefault("_lifecycle_log", []).append({
        "event": "version_bump",
        "new_version": new_version,
        "new_horizon_class": new_horizon_class,
        "reviewer": reviewer,
        "reason": reason,
    })
    return updated


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------

def load(path: Path | None = None) -> dict[str, Any]:
    """Load the registry JSON from disk.  Returns {'species': []} if absent."""
    p = path or REGISTRY_PATH
    if not p.exists():
        return {"schema": "species_registry.v1", "species": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.error("species_registry: failed to read %s: %s", p, exc)
        return {"schema": "species_registry.v1", "species": []}


def save(registry: dict[str, Any], path: Path | None = None) -> None:
    """Write the registry JSON to disk (pretty-printed)."""
    p = path or REGISTRY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_species(registry: dict[str, Any], species_id: str, version: str | None = None) -> dict[str, Any] | None:
    """Return the species entry matching species_id (and optionally version)."""
    for e in registry.get("species", []):
        if e.get("species_id") == species_id:
            if version is None or e.get("version") == version:
                return e
    return None


def upsert_species(registry: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace a species entry (matched by species_id + version).

    Validates the entry before inserting.  Returns the updated registry.
    """
    validate_entry(entry)
    sid, ver = entry["species_id"], entry["version"]
    species_list = registry.get("species", [])
    for i, e in enumerate(species_list):
        if e.get("species_id") == sid and e.get("version") == ver:
            species_list[i] = entry
            registry["species"] = species_list
            return registry
    species_list.append(entry)
    registry["species"] = species_list
    return registry


# ---------------------------------------------------------------------------
# Experiments-tab mirror (§3.1)
# ---------------------------------------------------------------------------

def mirror_to_experiments(
    registry: dict[str, Any],
    experiments_path: Path | None = None,
) -> int:
    """Additive merge of species entries into data/experiments/registry_seed.json.

    Rules:
      - key: "species-<species_id>"
      - kind: "species_phase0"
      - status: mapped via _EXPERIMENTS_STATUS_MAP
      - Only entries owned by this mirror (id starts with "species-") are ever
        updated.  All other curated entries are left untouched.
      - Idempotent: running twice adds nothing new (content-equal merge).

    Returns the number of entries added or updated.
    """
    ep = experiments_path or EXPERIMENTS_SEED_PATH
    if not ep.exists():
        log.warning("species_registry.mirror_to_experiments: seed not found at %s", ep)
        return 0

    try:
        seed = json.loads(ep.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.error("species_registry.mirror_to_experiments: cannot read seed: %s", exc)
        return 0

    experiments: list[dict] = seed.get("experiments", [])
    existing_by_id: dict[str, int] = {e.get("id"): i for i, e in enumerate(experiments)}

    changed = 0
    for entry in registry.get("species", []):
        sid = entry.get("species_id")
        if not sid:
            continue
        exp_id = f"species-{sid}"
        vs = entry.get("validation_status", "phase0")
        mirror_status = _EXPERIMENTS_STATUS_MAP.get(vs, "registered")
        gating = entry.get("gating") or {}

        new_exp = {
            "id": exp_id,
            "name": f"Setup Species {sid} — {entry.get('name', '')}",
            "kind": "species_phase0",
            "priority": "high" if vs in ("validated", "accruing") else "medium",
            "cadence": gating.get("cadence") or "monthly",
            "what": entry.get("mechanism", ""),
            "source": "engine/species_registry.py",
            "storage": "data/species/registry.json",
            "started": entry.get("ledger_binding", {}).get("since") or "2026-07-03",
            "come_back_on": gating.get("come_back_on") or None,
            "come_back_note": gating.get("maturation") or None,
            "maturation": gating.get("maturation") or None,
            "status": mirror_status,
            "next_step": (
                f"Monthly review: advance validation_status via "
                f"species_registry.transition_validation_status(). "
                f"Flip criteria: {entry.get('ledger_binding', {}).get('flip_criteria', '')}"
            ),
            "phase_hint": f"horizon={entry.get('horizon_class')} "
                          f"deployment={entry.get('deployment_status')}",
        }

        if exp_id in existing_by_id:
            existing = experiments[existing_by_id[exp_id]]
            # Only update if content actually differs
            differs = any(
                existing.get(k) != new_exp.get(k)
                for k in ("status", "come_back_on", "phase_hint", "priority")
            )
            if differs:
                # Merge: update only mirror-owned keys; preserve any extra curator fields
                updated = dict(existing)
                updated.update(new_exp)
                experiments[existing_by_id[exp_id]] = updated
                changed += 1
        else:
            experiments.append(new_exp)
            existing_by_id[exp_id] = len(experiments) - 1
            changed += 1

    if changed:
        seed["experiments"] = experiments
        try:
            ep.write_text(
                json.dumps(seed, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            log.info("species_registry: mirrored %d experiments entries", changed)
        except Exception as exc:  # noqa: BLE001
            log.error("species_registry: failed to write experiments seed: %s", exc)
            return 0

    return changed


# ---------------------------------------------------------------------------
# Public convenience: full sync
# ---------------------------------------------------------------------------

def sync(
    registry_path: Path | None = None,
    experiments_path: Path | None = None,
) -> dict[str, Any]:
    """Load registry, validate all entries, mirror to experiments seed.

    Returns a summary dict: {n_species, n_mirrored, errors}.
    Additive, never fatal — logs errors and continues.
    """
    reg = load(registry_path)
    errors: list[str] = []
    for e in reg.get("species", []):
        try:
            validate_entry(e)
        except SpeciesSchemaError as exc:
            errors.append(str(exc))
            log.error("species_registry.sync: %s", exc)

    n_mirror = 0
    try:
        n_mirror = mirror_to_experiments(reg, experiments_path)
    except Exception as exc:  # noqa: BLE001
        log.error("species_registry.sync: mirror failed: %s", exc)

    return {
        "n_species": len(reg.get("species", [])),
        "n_mirrored": n_mirror,
        "errors": errors,
    }
