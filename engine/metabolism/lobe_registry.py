"""engine.metabolism.lobe_registry — Lobe charter registry loader (V2-C, R-V2-7).

Loads config/lobe_charters.yml and validates it against synapse.yml.
The tier field in each charter is CI-MIRRORED from synapse — this module
asserts that charter.tier == synapse.tier and flags any mismatch as an
error (flagged, not raised — NEVER-RAISE contract).

Design rules:
  - NEVER-RAISE: every public function returns safe defaults on any error.
  - The lobe roster is derived from health.py's _is_nw_scope logic applied
    to synapse.yml — no hand-list, no second source of truth.
  - The tier field in lobe_charters.yml is a READ MIRROR from synapse.yml.
    A mismatch means either synapse or the charter was edited independently;
    both are flagged as tier_mismatch errors in the validation result.
  - lifecycle_state transitions are governed by lifecycle.py.
  - This module only loads + validates; it does not write.

Schema: lobe_charters.v1
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "lobe_charters.v1"

# Valid lifecycle states (lifecycle.py is the authority on transitions)
VALID_LIFECYCLE_STATES = frozenset({
    "proposed",
    "probation",
    "active",
    "demoted",
    "retired",
})

# Valid tier values (mirrors synapse.yml meta.tier_vocabulary)
VALID_TIERS = frozenset({
    "display",
    "shadow",
    "confirmer",
    "scored",
    "infrastructure",
})


# ── Scope-selection helper (mirrors health.py _is_nw_scope exactly) ──────────

def _is_nw_scope(art_id: str, art: dict) -> bool:
    """Return True if this synapse artifact is in the NW health scope.

    Mirrors engine.neuralweb.health._is_nw_scope exactly — one derivation,
    no second source of truth.
    """
    op = art.get("owner_program", "")
    path = art.get("path", "")
    ec = art.get("external_consumers") or []
    return (
        op == "neural-web"
        or path.startswith("data/neuralweb/")
        or path.startswith("site/neuralwebdata/")
        or "mastermind:context" in ec
    )


# ── File loaders ──────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict | None:
    """Load a YAML file; return None on any error (NEVER-RAISE)."""
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("lobe_registry: failed to load %s: %s", path, exc)
        return None


def _resolve_root(root: str | Path | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


# ── Public API ────────────────────────────────────────────────────────────────

def load(root: str | Path | None = None) -> dict[str, Any]:
    """Load the lobe charter registry from config/lobe_charters.yml.

    Returns
    -------
    dict with keys:
        schema          : str  — schema identifier
        ok              : bool — True if loaded without errors
        errors          : list[str] — non-fatal load/validation errors
        charters        : dict[lobe_id, charter_dict]
        count           : int — number of charters loaded
        tier_mismatches : list[str] — lobe_ids where charter.tier != synapse.tier

    NEVER raises.
    """
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "ok": False,
        "errors": [],
        "charters": {},
        "count": 0,
        "tier_mismatches": [],
    }
    try:
        r = _resolve_root(root)
        charter_path = r / "config" / "lobe_charters.yml"
        raw = _load_yaml(charter_path)
        if raw is None:
            result["errors"].append("config/lobe_charters.yml missing or unreadable")
            return result

        if raw.get("schema") != SCHEMA:
            result["errors"].append(
                f"unexpected schema: {raw.get('schema')!r}; expected {SCHEMA!r}"
            )

        charters = raw.get("charters") or {}
        if not isinstance(charters, dict):
            result["errors"].append("charters field is not a dict")
            return result

        # Validate each charter entry
        for lobe_id, charter in charters.items():
            if not isinstance(charter, dict):
                result["errors"].append(f"{lobe_id}: charter is not a dict")
                continue
            tier = charter.get("tier")
            ls = charter.get("lifecycle_state")
            if tier not in VALID_TIERS:
                result["errors"].append(f"{lobe_id}: invalid tier {tier!r}")
            if ls not in VALID_LIFECYCLE_STATES:
                result["errors"].append(f"{lobe_id}: invalid lifecycle_state {ls!r}")
            if charter.get("lobe_id") != lobe_id:
                result["errors"].append(
                    f"{lobe_id}: lobe_id field {charter.get('lobe_id')!r} != key"
                )

        result["charters"] = charters
        result["count"] = len(charters)
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001
        log.warning("lobe_registry.load: unexpected error: %s", exc)
        result["errors"].append(f"unexpected error: {exc}")

    return result


def validate_tier_mirror(
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Assert charter.tier == synapse.tier for every charter entry.

    Returns a validation result dict:
        ok              : bool
        tier_mismatches : list[dict] — {lobe_id, charter_tier, synapse_tier}
        errors          : list[str]  — load failures
        synapse_lobe_count : int     — NW-scope lobes found in synapse.yml
        charter_count   : int        — charters found in lobe_charters.yml

    NEVER raises.
    """
    result: dict[str, Any] = {
        "ok": False,
        "tier_mismatches": [],
        "errors": [],
        "synapse_lobe_count": 0,
        "charter_count": 0,
    }
    try:
        r = _resolve_root(root)
        # Load synapse.yml
        synapse_raw = _load_yaml(r / "config" / "synapse.yml")
        if synapse_raw is None:
            result["errors"].append("config/synapse.yml missing or unreadable")
            return result
        synapse_arts = synapse_raw.get("artifacts") or {}

        # Derive NW-scope lobe → tier map from synapse (same logic as health.py)
        synapse_tier: dict[str, str] = {
            art_id: art.get("tier", "display")
            for art_id, art in synapse_arts.items()
            if _is_nw_scope(art_id, art)
        }
        result["synapse_lobe_count"] = len(synapse_tier)

        # Load charters
        charter_result = load(root)
        if charter_result["errors"]:
            result["errors"].extend(charter_result["errors"])
        charters = charter_result["charters"]
        result["charter_count"] = len(charters)

        # Compare tiers
        mismatches = []
        for lobe_id, charter in charters.items():
            c_tier = charter.get("tier")
            s_tier = synapse_tier.get(lobe_id)
            if s_tier is None:
                # Charter entry for a lobe not in synapse NW-scope — flag but don't fail
                result["errors"].append(
                    f"{lobe_id}: in charter but not in synapse NW-scope"
                )
                continue
            if c_tier != s_tier:
                mismatches.append({
                    "lobe_id": lobe_id,
                    "charter_tier": c_tier,
                    "synapse_tier": s_tier,
                })
                log.warning(
                    "lobe_registry: tier mismatch for %s: charter=%r synapse=%r",
                    lobe_id, c_tier, s_tier,
                )

        result["tier_mismatches"] = mismatches
        result["ok"] = len(mismatches) == 0 and not result["errors"]
    except Exception as exc:  # noqa: BLE001
        log.warning("lobe_registry.validate_tier_mirror: unexpected error: %s", exc)
        result["errors"].append(f"unexpected error: {exc}")

    return result


def probation_count(root: str | Path | None = None) -> int:
    """Return the number of lobes currently in 'probation'. 0 on error (NEVER-RAISE).
    Used by the anti-cascade demotion cap."""
    try:
        charter_result = load(root)
        return sum(1 for c in charter_result["charters"].values()
                   if c.get("lifecycle_state") == "probation")
    except Exception as exc:  # noqa: BLE001
        log.warning("lobe_registry.probation_count: error: %s", exc)
        return 0


def active_nonscored_count(root: str | Path | None = None) -> int:
    """Return the number of active non-scored (display+shadow+confirmer) lobes.

    Used by the roster-budget governor.  Returns 0 on any error (NEVER-RAISE).
    """
    try:
        charter_result = load(root)
        count = 0
        for charter in charter_result["charters"].values():
            if (
                charter.get("lifecycle_state") == "active"
                and charter.get("tier") in ("display", "shadow", "confirmer")
            ):
                count += 1
        return count
    except Exception as exc:  # noqa: BLE001
        log.warning("lobe_registry.active_nonscored_count: error: %s", exc)
        return 0
