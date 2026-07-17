"""
engine.neuralweb.synapse — Signal-bus registry loader and integrity validator.

W0 passive layer: loads config/synapse.yml, validates structural integrity,
and provides artifact-lookup helpers. No envelope stamping, no read-gate.

Public API
----------
load_registry(root=None) -> dict
    Load and cache config/synapse.yml. `root` defaults to the repo root
    (two levels above this file). Returns the raw parsed YAML dict.

validate_registry(reg) -> list[str]
    Validate a parsed registry dict. Returns a list of human-readable
    violation strings (empty list = clean). Never prints; pure function.

artifacts_by_owner(reg, owner_program) -> dict
    Return {artifact_id: entry} for all artifacts matching `owner_program`.

artifact_for_path(reg, path) -> tuple[str, dict] | None
    Return (artifact_id, entry) for the first artifact whose `path` matches
    `path` exactly, or None if not found.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_FORMATS = {"json", "parquet", "jsonl", "js", "other"}
_VALID_CADENCES = {
    "daily-engine", "collect", "asia-close", "intraday", "weekly", "on-demand",
    "nightly-cortex", "nightly-factor-panel",
    "theta-ops-nightly",  # theta-ops launchd lane (Mac ops host, not GHA)
}
_VALID_STORAGES = {"git", "r2", "gitignored-local", "git+r2"}
_VALID_ASOF_FIELDS = {"asof", "as_of", "date", "generated_utc", "authored", "null"}
_VALID_TIERS = {"display", "shadow", "confirmer", "scored", "infrastructure"}
_VALID_WEIGHTS = {"measured", "hand", "none"}
_VALID_HORIZON_ROLES = {"tactical_entry", "hold_thesis", "dual", "context"}

_REQUIRED_META_KEYS = {"schema_version", "description", "tier_vocabulary",
                       "article2_surfaces"}
_REQUIRED_ARTIFACT_KEYS = {
    "path", "format", "producer", "owner_program", "cadence", "storage",
    "asof_field", "freshness_sla_hours", "schema", "tier", "horizon_role",
}

# Repo-relative paths that contain placeholders (like <SYM>) — skip existence check.
_PLACEHOLDER_RE = re.compile(r"<[A-Z_]+>")


def _repo_root() -> Path:
    """Return the repository root (two levels above this file: engine/neuralweb/synapse.py)."""
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Registry loader (cached)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_registry_cached(registry_path: str) -> dict:
    with open(registry_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_registry(root: str | Path | None = None) -> dict:
    """Load config/synapse.yml relative to `root` (defaults to repo root).

    Cached per resolved path — subsequent calls in the same process are free.
    Returns the raw parsed YAML dict.
    """
    r = Path(root) if root is not None else _repo_root()
    registry_path = r / "config" / "synapse.yml"
    if not registry_path.exists():
        raise FileNotFoundError(f"synapse.yml not found at {registry_path}")
    return _load_registry_cached(str(registry_path))


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_registry(reg: dict, root: str | Path | None = None) -> list[str]:
    """Validate a parsed registry dict.

    Parameters
    ----------
    reg : dict
        Parsed YAML from load_registry().
    root : path-like, optional
        Repo root used for producer existence checks. Defaults to the repo root
        inferred from this file's location.

    Returns
    -------
    list[str]
        Human-readable violation strings. Empty list means clean.
        Never raises; never prints.
    """
    violations: list[str] = []
    r = Path(root) if root is not None else _repo_root()

    # ------------------------------------------------------------------
    # 1. Meta block
    # ------------------------------------------------------------------
    meta = reg.get("meta") or {}
    if not isinstance(meta, dict):
        violations.append("meta block is missing or not a dict")
        return violations  # fatal: can't continue meaningfully

    if meta.get("schema_version") != 1:
        violations.append(
            f"meta.schema_version must be 1, got {meta.get('schema_version')!r}"
        )

    for key in _REQUIRED_META_KEYS:
        if key not in meta:
            violations.append(f"meta is missing required key: {key!r}")

    # ------------------------------------------------------------------
    # 2. Artifacts block
    # ------------------------------------------------------------------
    artifacts: Any = reg.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        violations.append("artifacts block is missing or not a dict")
        return violations

    seen_paths: dict[str, str] = {}  # path -> artifact_id (dup check)

    for artifact_id, entry in artifacts.items():
        if not isinstance(entry, dict):
            violations.append(f"{artifact_id}: entry is not a dict")
            continue

        prefix = f"{artifact_id}"

        # 2a. Required fields present
        for key in _REQUIRED_ARTIFACT_KEYS:
            if key not in entry:
                violations.append(f"{prefix}: missing required field {key!r}")

        # 2b. Enum: format
        fmt = entry.get("format")
        if fmt is not None and fmt not in _VALID_FORMATS:
            violations.append(
                f"{prefix}: format {fmt!r} not in {sorted(_VALID_FORMATS)}"
            )

        # 2c. Enum: cadence
        cadence = entry.get("cadence")
        if cadence is not None and cadence not in _VALID_CADENCES:
            violations.append(
                f"{prefix}: cadence {cadence!r} not in {sorted(_VALID_CADENCES)}"
            )

        # 2d. Enum: storage
        storage = entry.get("storage")
        if storage is not None and storage not in _VALID_STORAGES:
            violations.append(
                f"{prefix}: storage {storage!r} not in {sorted(_VALID_STORAGES)}"
            )

        # 2e. Enum: asof_field (allow any string or the sentinel "null")
        asof = entry.get("asof_field")
        # asof_field: any string is fine (artifact-specific field name), but
        # the literal Python None (YAML null) is also valid — means no asof.
        # We accept any string value; no enum restriction beyond the schema.

        # 2f. Enum: tier
        tier = entry.get("tier")
        if tier is not None and tier not in _VALID_TIERS:
            violations.append(
                f"{prefix}: tier {tier!r} not in {sorted(_VALID_TIERS)}"
            )

        # 2f2. Enum: horizon_role (LH-R1 firewall — required on every artifact)
        horizon_role = entry.get("horizon_role")
        if horizon_role is None:
            violations.append(
                f"{prefix}: missing required field 'horizon_role' "
                f"(must be one of {sorted(_VALID_HORIZON_ROLES)})"
            )
        elif horizon_role not in _VALID_HORIZON_ROLES:
            violations.append(
                f"{prefix}: horizon_role {horizon_role!r} not in "
                f"{sorted(_VALID_HORIZON_ROLES)}"
            )
        # dual requires a justification note
        elif horizon_role == "dual" and not entry.get("notes"):
            violations.append(
                f"{prefix}: horizon_role='dual' requires a notes field "
                f"justifying the separate calibrations"
            )

        # 2g. Enum: weights
        weights = entry.get("weights", "none")
        if weights not in _VALID_WEIGHTS:
            violations.append(
                f"{prefix}: weights {weights!r} not in {sorted(_VALID_WEIGHTS)}"
            )

        # 2h. freshness_sla_hours must be a positive int
        sla = entry.get("freshness_sla_hours")
        if sla is not None and (not isinstance(sla, int) or sla <= 0):
            violations.append(
                f"{prefix}: freshness_sla_hours must be a positive int, got {sla!r}"
            )

        # 2i. Producer file exists (skip patterns with placeholders, skip r2/gitignored-local)
        producer = entry.get("producer", "")
        if producer and not _PLACEHOLDER_RE.search(producer):
            # Strip any trailing inline comment / line reference (e.g. "engine/foo.py:123")
            producer_path = producer.split(":")[0].strip()
            storage_val = entry.get("storage", "")
            if storage_val not in ("r2",):  # r2 artifacts live offsite
                candidate = r / producer_path
                if not candidate.exists():
                    violations.append(
                        f"{prefix}: producer file not found: {producer_path!r}"
                    )

        # 2j. Unique paths (dedupe overlaps are a census error)
        path = entry.get("path", "")
        if path:
            if path in seen_paths:
                violations.append(
                    f"{prefix}: duplicate path {path!r} (already used by {seen_paths[path]!r})"
                )
            else:
                seen_paths[path] = artifact_id

        # 2k. scored/confirmer tier requires qual_ladder_ref OR notes explaining evidence
        if tier in ("scored", "confirmer"):
            has_ref = bool(entry.get("qual_ladder_ref"))
            has_notes = bool(entry.get("notes"))
            if not has_ref and not has_notes:
                violations.append(
                    f"{prefix}: tier={tier!r} requires qual_ladder_ref or notes "
                    f"explaining the gauntlet evidence (Article 3 honesty)"
                )

        # 2l. weights='hand' requires notes naming the debt
        if weights == "hand" and not entry.get("notes"):
            violations.append(
                f"{prefix}: weights='hand' requires a notes field naming the weight debt"
            )

        # 2m. known_extra_writers non-empty requires notes
        extra_writers = entry.get("known_extra_writers") or []
        if extra_writers and not entry.get("notes"):
            violations.append(
                f"{prefix}: known_extra_writers is non-empty but notes is missing "
                f"(rot must be explained)"
            )

    return violations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def artifacts_by_owner(reg: dict, owner_program: str) -> dict[str, dict]:
    """Return {artifact_id: entry} for all artifacts matching `owner_program`.

    Matching is case-insensitive substring match (e.g. 'oracle' matches
    'oracle', 'sector-pulse / oracle', 'oracle/sector-pulse').
    """
    owner_lower = owner_program.lower()
    return {
        aid: entry
        for aid, entry in (reg.get("artifacts") or {}).items()
        if isinstance(entry, dict)
        and owner_lower in (entry.get("owner_program") or "").lower()
    }


def artifact_for_path(reg: dict, path: str) -> tuple[str, dict] | None:
    """Return (artifact_id, entry) for the artifact whose `path` equals `path`.

    Returns None if not found. Path matching is exact (case-sensitive).
    """
    for aid, entry in (reg.get("artifacts") or {}).items():
        if isinstance(entry, dict) and entry.get("path") == path:
            return (aid, entry)
    return None
