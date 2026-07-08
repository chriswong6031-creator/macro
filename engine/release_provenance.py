"""MRI-R26 — release-forecast provenance and source-coverage module.

Pure, importable, display-only functions. No I/O side effects except reading
the ledger path explicitly passed in. No global state, no scoring, no authority.

AUTHORITY LAW (MRI-R26 / MRI-R2 / MRI-R3): the four coverage flags produced here
are METADATA ONLY. They NEVER gate, score, size, or alter any projection's
point/p10..p90/skew/confidence. An authority test in the test suite enforces this.

DISPLAY-ONLY. Nothing here originates signals, classifications, or positioning
inputs. Fail-open on bad/empty input: functions return sensible defaults, never raise.

Mirrors the style of engine/release_market_context.py (fail-open, type-hinted,
docstringed, pure numpy/pandas).
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Status vocabulary for leg classification (MRI-R26)
_STATUS_PRESENT = "present"
_STATUS_REVISION_OPTIMISTIC = "revision_optimistic"
_STATUS_UNREVISED = "unrevised"
_STATUS_ABSENT = "absent"

# Statuses that count as "covered" (non-prior / non-absent) for weight_coverage
_COVERED_STATUSES = {_STATUS_PRESENT, _STATUS_REVISION_OPTIMISTIC, _STATUS_UNREVISED}
# Statuses that count as NOT ALFRED-vintaged for non_vintaged_share
_NON_VINTAGED_STATUSES = {_STATUS_REVISION_OPTIMISTIC, _STATUS_UNREVISED, _STATUS_ABSENT}


def _classify_leg(
    leg_name: str,
    revision_optimistic_legs: list[str],
    unrevised_legs: list[str],
    absent_legs: list[str],
) -> str:
    """Return the MRI-R26 status string for a single leg.

    Priority: absent > unrevised > revision_optimistic > present.
    A leg may appear in multiple lists (e.g. revision_optimistic and absent if
    the file was missing at runtime); absent wins.
    """
    if leg_name in absent_legs:
        return _STATUS_ABSENT
    if leg_name in unrevised_legs:
        return _STATUS_UNREVISED
    if leg_name in revision_optimistic_legs:
        return _STATUS_REVISION_OPTIMISTIC
    return _STATUS_PRESENT


def _extract_provenance(projection: dict) -> dict[str, Any]:
    """Pull the pit_provenance sub-dict safely; return empty dict on failure."""
    try:
        prov = projection.get("pit_provenance") or {}
        if not isinstance(prov, dict):
            return {}
        return prov
    except Exception:  # noqa: BLE001
        return {}


def _declared_legs(prov: dict[str, Any], features: dict[str, Any]) -> list[str]:
    """Infer the full declared-leg list from provenance lists + feature keys.

    The provenance dict stores partial lists; the union of all three lists plus
    all feature keys (excluding None-absent ones when possible) gives the
    full declared set.
    """
    declared: set[str] = set()
    for key in ("revision_optimistic_legs", "unrevised_legs", "absent_legs"):
        val = prov.get(key)
        if isinstance(val, list):
            declared.update(val)
    # Feature keys are the canonical declared set; absent legs may still be keys
    # with None values — include them.
    declared.update(str(k) for k in features.keys())
    return sorted(declared)


def build_input_snapshot(projection: dict) -> dict:
    """Build an input-snapshot receipt for a projection (MRI-R26).

    Returns a dict with:
      - prediction_id: str (from projection, or derived from release+asof)
      - asof: str (ISO date)
      - features: {name: value} — all feature keys and their values
      - legs: {name: status} — each leg classified as
          present | revision_optimistic | unrevised | absent
      - inputs_hash: str — reused from the projection's existing inputs_hash;
          never recomputed here (MRI-R26 "reuse existing hash").

    Fail-open: returns a minimal dict with error=True on bad input.
    Does NOT write to disk; caller handles persistence.
    """
    if not projection or not isinstance(projection, dict):
        return {"error": True, "reason": "null or non-dict projection"}

    try:
        prov = _extract_provenance(projection)
        rev_opt = prov.get("revision_optimistic_legs") or []
        unrev = prov.get("unrevised_legs") or []
        absent = prov.get("absent_legs") or []

        # Reconstruct the features sub-dict.
        # The projection dict does not store raw feature values directly (they
        # are not surfaced in the output dict; see engine/release_forecast.py).
        # We expose what is available: the provenance leg lists serve as feature
        # proxies. The snapshot captures status per declared leg.
        features: dict[str, Any] = {}
        all_legs = set(rev_opt) | set(unrev) | set(absent)

        # Also harvest any _features key if present (some call sites attach it)
        raw_features = projection.get("_features") or projection.get("features") or {}
        if isinstance(raw_features, dict):
            features.update({str(k): v for k, v in raw_features.items()})

        # Legs from provenance that aren't already in raw_features get None value
        for leg in all_legs:
            if leg not in features:
                features[leg] = None

        legs: dict[str, str] = {}
        for leg in sorted(all_legs | set(features.keys())):
            legs[leg] = _classify_leg(leg, rev_opt, unrev, absent)

        # inputs_hash: reuse from projection; fall back to empty string
        inputs_hash = projection.get("inputs_hash") or ""

        # prediction_id: prefer explicit key, else derive
        prediction_id = projection.get("prediction_id") or ""
        if not prediction_id:
            release = projection.get("release") or projection.get("release_id") or "unknown"
            asof = projection.get("asof") or ""
            prediction_id = f"{release}:{asof}:v1"

        return {
            "prediction_id": prediction_id,
            "asof": projection.get("asof") or "",
            "features": features,
            "legs": legs,
            "inputs_hash": inputs_hash,
        }
    except Exception as exc:  # noqa: BLE001
        log.debug("build_input_snapshot failed: %s", exc)
        return {"error": True, "reason": str(exc)}


def compute_coverage_flags(
    projection: dict,
    ledger_path: str | Path | None,
    weights: dict[str, float] | None = None,
) -> dict:
    """Compute the four MRI-R26 source-coverage flags for a projection.

    Parameters
    ----------
    projection:
        A projection dict as returned by engine.release_forecast.project_release.
        Must contain 'pit_provenance' with leg classification lists.
    ledger_path:
        Path to the forward ledger JSONL file. Used only to count scored rows.
        Accepts None or a missing path (returns model_maturity=0).
    weights:
        Optional block→RI-weight dict (CPI component-bridge case). If provided,
        weight_coverage and fresh_proxy_coverage use these weights; otherwise
        fall back to equal-weight leg fractions.

    Returns
    -------
    dict with keys:
      weight_coverage        float [0,1]: share of weight/legs on non-absent legs
      fresh_proxy_coverage   float [0,1]: share weighted by fresh current-month data
      non_vintaged_share     float [0,1]: share of legs NOT ALFRED-vintaged
      model_maturity         int >= 0:    count of scored ledger rows for this release

    All four are returned even on error (with 0.0 / 0 defaults). Never raises.
    AUTHORITY: these values must not be read back into point/p10..p90/skew/confidence.
    """
    defaults: dict[str, Any] = {
        "weight_coverage": 0.0,
        "fresh_proxy_coverage": 0.0,
        "non_vintaged_share": 0.0,
        "model_maturity": 0,
    }

    if not projection or not isinstance(projection, dict):
        return defaults

    try:
        prov = _extract_provenance(projection)
        rev_opt: list[str] = prov.get("revision_optimistic_legs") or []
        unrev: list[str] = prov.get("unrevised_legs") or []
        absent: list[str] = prov.get("absent_legs") or []

        all_legs = sorted(set(rev_opt) | set(unrev) | set(absent))
        n_total = len(all_legs)

        # ------------------------------------------------------------------ #
        # weight_coverage
        # ------------------------------------------------------------------ #
        if weights and isinstance(weights, dict):
            total_weight = sum(float(v) for v in weights.values() if v is not None)
            if total_weight > 0:
                covered_weight = sum(
                    float(weights.get(leg, 0.0) or 0.0)
                    for leg in all_legs
                    if _classify_leg(leg, rev_opt, unrev, absent) in _COVERED_STATUSES
                )
                weight_coverage = covered_weight / total_weight
            else:
                weight_coverage = 0.0
        else:
            # Equal-weight leg fraction
            if n_total == 0:
                weight_coverage = 0.0
            else:
                n_covered = sum(
                    1
                    for leg in all_legs
                    if _classify_leg(leg, rev_opt, unrev, absent) in _COVERED_STATUSES
                )
                weight_coverage = n_covered / n_total

        # ------------------------------------------------------------------ #
        # fresh_proxy_coverage
        # ------------------------------------------------------------------ #
        # Use explicit fresh_legs list from provenance if provided.
        # Otherwise approximate as present-leg share (documented approximation).
        fresh_legs: list[str] = prov.get("fresh_legs") or []
        _fresh_approximated = len(fresh_legs) == 0  # noqa: SIM108

        if fresh_legs and weights and isinstance(weights, dict):
            total_weight = sum(float(v) for v in weights.values() if v is not None)
            if total_weight > 0:
                fresh_weight = sum(
                    float(weights.get(leg, 0.0) or 0.0)
                    for leg in fresh_legs
                    if leg in all_legs
                )
                fresh_proxy_coverage = fresh_weight / total_weight
            else:
                fresh_proxy_coverage = 0.0
        elif fresh_legs:
            if n_total == 0:
                fresh_proxy_coverage = 0.0
            else:
                n_fresh = sum(1 for leg in fresh_legs if leg in set(all_legs))
                fresh_proxy_coverage = n_fresh / n_total
        else:
            # Approximation: present-leg share as proxy for fresh coverage.
            # Documented per MRI-R26: when pit_provenance carries no fresh_legs
            # list, this is a coarse lower bound (revision_optimistic legs may
            # or may not be fresh for the current reference month).
            if n_total == 0:
                fresh_proxy_coverage = 0.0
            else:
                n_present = sum(
                    1
                    for leg in all_legs
                    if _classify_leg(leg, rev_opt, unrev, absent) == _STATUS_PRESENT
                )
                fresh_proxy_coverage = n_present / n_total

        # ------------------------------------------------------------------ #
        # non_vintaged_share
        # ------------------------------------------------------------------ #
        if n_total == 0:
            non_vintaged_share = 0.0
        else:
            n_non_vintaged = sum(
                1
                for leg in all_legs
                if _classify_leg(leg, rev_opt, unrev, absent) in _NON_VINTAGED_STATUSES
            )
            non_vintaged_share = n_non_vintaged / n_total

        # ------------------------------------------------------------------ #
        # model_maturity — count forward-scored rows from ledger
        # ------------------------------------------------------------------ #
        model_maturity = _count_scored_rows(projection, ledger_path)

        return {
            "weight_coverage": float(weight_coverage),
            "fresh_proxy_coverage": float(fresh_proxy_coverage),
            "non_vintaged_share": float(non_vintaged_share),
            "model_maturity": int(model_maturity),
            # Metadata annotations (not display values; for debugging)
            "_fresh_approximated": bool(_fresh_approximated),
        }

    except Exception as exc:  # noqa: BLE001
        log.debug("compute_coverage_flags failed: %s", exc)
        return defaults


def _count_scored_rows(projection: dict, ledger_path: str | Path | None) -> int:
    """Count forward-scored ledger rows for this projection's release.

    Reads ledger_path (JSONL), counts rows where row_type=='scored' AND
    release matches projection['release']. Returns 0 on any error or missing file.
    Today (2026-07-08) the forward-scored count is 0 for all releases.
    """
    if not ledger_path:
        return 0

    release = projection.get("release") or projection.get("release_id") or ""
    if not release:
        return 0

    try:
        p = Path(ledger_path)
        if not p.exists():
            return 0
        count = 0
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if (isinstance(row, dict)
                            and row.get("row_type") == "scored"
                            and row.get("release") == release):
                        count += 1
                except json.JSONDecodeError:
                    continue
        return count
    except Exception as exc:  # noqa: BLE001
        log.debug("_count_scored_rows failed for %s: %s", ledger_path, exc)
        return 0
