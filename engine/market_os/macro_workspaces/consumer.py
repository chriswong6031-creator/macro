"""Bounded machine consumer for the Macro workspace snapshot (F01 / R1A).

The architecture (section 11.3) requires at least one real, non-UI consumer of
the snapshot before/with launch, so the projection contract never becomes an
unused frontend schema. This module is that consumer: a self-contained,
read-only current-state summary emitter that

* reads a published ``latest.json`` (or an in-memory snapshot);
* validates it against the closed contract (``contract.validate``);
* on ANY malformed / unsupported / hash-mismatched / stale input becomes
  ABSENT / INERT and returns a visible audit receipt (never a decision, never a
  neutral default);
* on good input exposes only owner-approved summary fields, with authority all
  false.

It imports nothing but the shared ``contract`` module and the standard library
- no raw producer code, no owner engine module, no pandas, no cross-repo import,
no Neural Web / Brain owner file is touched to wire it. A separate owner (Neural
Web world-state / Brain context) may CALL this function; wiring that call lives
in the owner's package, not here, and is out of R1A scope.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from engine.market_os.macro_workspaces import contract

# Freshness states a bounded machine consumer may treat as usable. Anything
# worse makes the consumer inert rather than passing degraded macro state on.
_USABLE_FRESHNESS = {"CURRENT", "LATE_WITHIN_TOLERANCE"}

_AUTHORITY = {
    "can_rank": False, "can_gate": False, "can_size": False,
    "can_originate_signal": False, "can_execute": False, "class": "context_only",
}


def _inert(reason_code: str, detail: str, *, snapshot: Mapping[str, Any] | None = None) -> dict:
    """An ABSENT/INERT receipt: visible audit, no summary, no authority."""
    gen = (snapshot or {}).get("generation") if isinstance(snapshot, Mapping) else None
    return {
        "state": "INERT",
        "active": False,
        "summary": None,
        "authority": dict(_AUTHORITY),
        "audit": {
            "consumer": "engine.market_os.macro_workspaces.consumer",
            "reason_code": reason_code,
            "detail": detail,
            "contract_ok": False,
            "generation_id": (gen or {}).get("generation_id") if isinstance(gen, Mapping) else None,
            "content_sha256": (gen or {}).get("content_sha256") if isinstance(gen, Mapping) else None,
        },
    }


def summarize(snapshot: Any, *, allow_stale: bool = False) -> dict:
    """Return an ACTIVE owner-approved summary, or an INERT audit receipt.

    INERT when: not an object, unknown/unsupported contract, schema violation,
    content_sha256 mismatch, or (unless ``allow_stale``) an availability state
    outside {CURRENT, LATE_WITHIN_TOLERANCE}.
    """
    ok, reason = contract.check(snapshot)
    if not ok:
        return _inert("CONTRACT_INVALID", reason or "contract validation failed",
                      snapshot=snapshot if isinstance(snapshot, Mapping) else None)

    availability = snapshot["availability"]
    fresh = availability["state"]
    if not allow_stale and fresh not in _USABLE_FRESHNESS:
        return _inert("STALE_OR_DEGRADED", f"availability.state={fresh}", snapshot=snapshot)

    headline = snapshot["headline"]
    contradiction = availability["contradiction"]
    gen = snapshot["generation"]
    summary = {
        "workspace": snapshot["workspace"]["id"],
        "region": snapshot["region"]["code"],
        "state_id": headline["state_id"],
        "state_label_en": headline["state_label"]["en"],
        "funding_pressure": headline["quadrant"]["x"],
        "balance_sheet_support": headline["quadrant"]["y"],
        "one_month_vector": {
            "dx": headline["one_month_vector"]["dx"],
            "dy": headline["one_month_vector"]["dy"],
            "status": headline["one_month_vector"]["status"],
        },
        "effective_date": headline["effective_date"],
        "freshness": fresh,
        "coverage_ratio": availability["coverage_ratio"],
        "contradiction_present": contradiction["present"],
        "contradiction_kind": contradiction["kind"],
        "method_version": headline["method_version"],
    }
    return {
        "state": "ACTIVE",
        "active": True,
        "summary": summary,
        "authority": dict(_AUTHORITY),
        "audit": {
            "consumer": "engine.market_os.macro_workspaces.consumer",
            "reason_code": "OK",
            "detail": "snapshot validated against mastermind.macro_workspace_snapshot.v1",
            "contract_ok": True,
            "generation_id": gen["generation_id"],
            "content_sha256": gen["content_sha256"],
        },
    }


def summarize_from_path(path: Path | str, *, allow_stale: bool = False) -> dict:
    """Load a published snapshot and summarize it. Unreadable / non-JSON input
    yields an INERT receipt (never raises)."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return _inert("SNAPSHOT_UNREADABLE", f"{type(exc).__name__}: {exc}")
    try:
        snapshot = json.loads(raw)
    except (ValueError, TypeError) as exc:
        return _inert("SNAPSHOT_NOT_JSON", f"{type(exc).__name__}: {exc}")
    return summarize(snapshot, allow_stale=allow_stale)
