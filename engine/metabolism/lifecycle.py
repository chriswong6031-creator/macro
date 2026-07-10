"""
SAFETY (the real load-bearing property): transition() NEVER writes a synapse
tier anywhere — it only appends governance events + docket proposals under
data/metabolism/. Promotion to scored/authority is impossible for the loop; it can
only PROPOSE, and the gauntlet + operator T2 tap gate any real change. The tier=
runtime guard is defense-in-depth on top of that structural fact.
engine.metabolism.lifecycle — Lobe lifecycle state machine (V2-C, R-V2-3).

THE FENCE: a pure deterministic allowed-transition table.  Every transition
edge is tagged by its T-level (T1 = display-tier autonomous; T2 = requires
gauntlet + operator).

CRITICAL SAFETY PROPERTY
------------------------
This module CANNOT emit any transition edge whose destination:
    (a) raises a synapse tier to confirmer | scored
    (b) adds a scored_path_surface
    (c) flips a mastermind_context authority switch

Any such "promotion" edge → transition() returns {allowed: False,
reason: 'promotion to scored/authority is T2+gauntlet+operator (R-V2-3)'}.

Demotion (active→probation, probation→demoted, demoted→retired) is ALWAYS
de-escalation and T1-safe.

Emitting an allowed transition:
    1. Writes a lifecycle governance event via governance.append_event()
       (neuralweb.governance.v1, NEVER-RAISE).
    2. Writes a lifecycle docket item for the normal PROPOSE→ADJUDICATE
       gauntlet — it NEVER directly edits synapse.yml or mastermind_context.
    3. Screens against DO_NOT_REBUILD.md + ACTIVE_BUILD_MAP.md (for
       proposed→probation and probation→active only).

NEVER-RAISE CONTRACT: all public functions return safe defaults on any error.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.lifecycle.v1"

# ── Tier hierarchy (ordered lowest→highest) ───────────────────────────────────

_TIER_ORDER = ["display", "shadow", "confirmer", "scored", "infrastructure"]

# Tiers that require T2 + gauntlet + operator to reach
_PROMOTION_TIERS = frozenset({"confirmer", "scored"})

# ── Lifecycle state machine ────────────────────────────────────────────────────
#
# Allowed edges: (from_state, to_state) → {t_level, de_escalation, description}
#
# T1 = autonomous two-key (display-tier); T2 = T2 + gauntlet + operator.
# De-escalation edges are ALWAYS T1-safe.
# Promotion-to-scored edges are PROHIBITED at the Python level (see transition()).

_ALLOWED_EDGES: dict[tuple[str, str], dict[str, Any]] = {
    # ── Onboarding ────────────────────────────────────────────────────────────
    ("proposed", "probation"): {
        "t_level": "T1",
        "de_escalation": False,
        "description": (
            "New lobe enters probation for initial fitness assessment. "
            "Requires DO_NOT_REBUILD + ACTIVE_BUILD_MAP collision screen."
        ),
        "requires_collision_screen": True,
    },
    ("probation", "active"): {
        "t_level": "T1",
        "de_escalation": False,
        "description": (
            "Lobe promoted from probation to active after fitness floor passed. "
            "Requires DO_NOT_REBUILD + ACTIVE_BUILD_MAP collision screen."
        ),
        "requires_collision_screen": True,
    },
    # ── De-escalation (demotion) — always T1-safe ─────────────────────────────
    ("active", "probation"): {
        "t_level": "T1",
        "de_escalation": True,
        "description": (
            "Active lobe placed on probation after N consecutive logic-breach failures "
            "(circuit_breaker_trip=3). Excludes health.py missing/degraded/stale. "
            "Regime-aware; requires adversary non-veto on all-inputs-absent."
        ),
    },
    ("probation", "demoted"): {
        "t_level": "T1",
        "de_escalation": True,
        "description": (
            "Probation lobe demoted after additional logic-breach failures (+M). "
            "Excludes health.py missing/degraded/stale. Regime-aware."
        ),
    },
    ("demoted", "retired"): {
        "t_level": "T1",
        "de_escalation": True,
        "description": (
            "Demoted lobe retired. Appends a DO_NOT_REBUILD row as a docket item. "
            "Operator-gated (adversary non-veto required). INERT: emits proposal only."
        ),
    },
    # ── Rehabilitation ────────────────────────────────────────────────────────
    ("probation", "proposed"): {
        "t_level": "T1",
        "de_escalation": False,
        "description": "Probation lobe reset to proposed for revamp (operator-initiated).",
    },
    ("demoted", "proposed"): {
        "t_level": "T1",
        "de_escalation": False,
        "description": "Demoted lobe reset to proposed for full revamp (operator-initiated).",
    },
    # ── Direct operator retire from active ────────────────────────────────────
    ("active", "retired"): {
        "t_level": "T1",
        "de_escalation": True,
        "description": (
            "Operator directly retires an active lobe (e.g., scope change). "
            "Appends a DO_NOT_REBUILD row as a docket item."
        ),
    },
}

# ── FORBIDDEN EDGES (tier-raising) ────────────────────────────────────────────
#
# Any edge that would raise a synapse tier to confirmer|scored, add a
# scored_path_surface, or flip a mastermind_context authority switch is
# REFUSED.  These are detected structurally in transition() below — not by
# an allow-list, but by inspecting what the destination tier implies.
#
# This set exists only for documentation; it is NOT the enforcement mechanism.
# The enforcement is in transition() itself.
_FORBIDDEN_TIER_DESTINATIONS: frozenset[str] = frozenset({
    "confirmer",
    "scored",
})

_REFUSAL_REASON = (
    "promotion to scored/authority is T2+gauntlet+operator (R-V2-3); "
    "lifecycle.py cannot emit this edge autonomously"
)


# ── Collision screen ──────────────────────────────────────────────────────────

def _collision_screen(lobe_id: str, root: Path) -> list[str]:
    """Screen lobe_id against DO_NOT_REBUILD.md + ACTIVE_BUILD_MAP.md.

    Returns a list of collision strings (empty = no collision).
    NEVER raises.
    """
    hits: list[str] = []
    try:
        dnr = root / "research" / "DO_NOT_REBUILD.md"
        if dnr.exists():
            text = dnr.read_text(encoding="utf-8", errors="replace")
            if lobe_id in text:
                hits.append(f"DO_NOT_REBUILD: {lobe_id!r} found in kill registry")
    except Exception as exc:  # noqa: BLE001
        log.warning("lifecycle._collision_screen: DO_NOT_REBUILD check error: %s", exc)

    try:
        abm = root / "docs" / "ACTIVE_BUILD_MAP.md"
        if abm.exists():
            text = abm.read_text(encoding="utf-8", errors="replace")
            if lobe_id in text:
                hits.append(f"ACTIVE_BUILD_MAP: {lobe_id!r} found in active-build map")
    except Exception as exc:  # noqa: BLE001
        log.warning("lifecycle._collision_screen: ACTIVE_BUILD_MAP check error: %s", exc)

    return hits


# ── Governance event emission ─────────────────────────────────────────────────

def _emit_lifecycle_event(
    lobe_id: str,
    from_state: str,
    to_state: str,
    edge_meta: dict,
    reason: str,
    root: Path,
    extra: dict | None = None,
) -> bool:
    """Append a lifecycle governance event.  NEVER raises.

    Reuses engine.neuralweb.governance.append_event (NEVER-RAISE).
    """
    try:
        from engine.neuralweb.governance import append_event  # noqa: PLC0415
        return append_event(
            event_type="metabolism_adjudication",
            target=lobe_id,
            article=None,
            authored_by="lifecycle.py",
            evidence={
                "from_state": from_state,
                "to_state": to_state,
                "t_level": edge_meta.get("t_level"),
                "de_escalation": edge_meta.get("de_escalation"),
                "reason": reason,
                **(extra or {}),
            },
            root=root,
            note=f"lifecycle: {from_state}→{to_state} for {lobe_id}",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("lifecycle._emit_lifecycle_event: governance error: %s", exc)
        return False


# ── Docket item emission ──────────────────────────────────────────────────────

def _write_docket_item(
    lobe_id: str,
    from_state: str,
    to_state: str,
    edge_meta: dict,
    reason: str,
    root: Path,
) -> bool:
    """Write a lifecycle docket item for the PROPOSE→ADJUDICATE gauntlet.

    This is the ONLY way lifecycle state changes reach the charter registry —
    through the normal gauntlet, never by direct edit.  NEVER raises.
    """
    try:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        docket_dir = root / "data" / "metabolism" / "lifecycle_docket"
        docket_dir.mkdir(parents=True, exist_ok=True)
        slug = lobe_id.replace("/", "_")
        fname = f"{ts[:10]}_{slug}_{from_state}_to_{to_state}.json"
        item = {
            "schema": "metabolism.lifecycle_docket.v1",
            "ts": ts,
            "lobe_id": lobe_id,
            "from_state": from_state,
            "to_state": to_state,
            "t_level": edge_meta.get("t_level"),
            "de_escalation": edge_meta.get("de_escalation"),
            "description": edge_meta.get("description"),
            "reason": reason,
            "authority": {
                "is_context_only": True,
                "display_only": True,
                "not_a_signal": True,
                "note": (
                    "This docket item is a PROPOSAL for the gauntlet. "
                    "It does not change any synapse tier or mastermind authority. "
                    "lifecycle.py cannot emit tier-raising edges (R-V2-3)."
                ),
            },
        }
        (docket_dir / fname).write_text(
            json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("lifecycle._write_docket_item: error: %s", exc)
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def transition(
    from_state: str,
    to_state: str,
    lobe_id: str,
    *,
    reason: str = "",
    tier: str = "display",
    scored_path_surface: bool = False,
    mastermind_authority: bool = False,
    root: str | Path | None = None,
    emit: bool = True,
) -> dict[str, Any]:
    """Evaluate a lifecycle transition request and optionally emit it.

    THE FENCE:
        - Any destination that raises synapse tier to confirmer|scored
          is REFUSED.
        - Any edge that adds a scored_path_surface is REFUSED.
        - Any edge that flips a mastermind_context authority switch is REFUSED.
        - Only edges in the allowed-transition table may proceed.
        - De-escalation edges are T1-safe.
        - Onboarding edges require a collision screen.

    Parameters
    ----------
    from_state : str
        Current lifecycle_state of the lobe.
    to_state : str
        Requested next lifecycle_state.
    lobe_id : str
        The synapse artifact ID for this lobe.
    reason : str
        Human-readable rationale for this transition request.
    tier : str
        Current synapse tier of the lobe.  Used to detect implicit
        tier-raising attempts (a lobe transitioning to 'active' while
        requesting a tier change to confirmer/scored).
    scored_path_surface : bool
        If True, the transition request includes adding a scored_path_surface.
        ALWAYS REFUSED.
    mastermind_authority : bool
        If True, the transition request includes flipping a mastermind_context
        authority switch.  ALWAYS REFUSED.
    root : str | Path | None
        Project root (None = production paths).
    emit : bool
        If True (default) and the transition is allowed, emit governance event
        + docket item.  Set False in tests that want the decision without I/O.

    Returns
    -------
    dict with keys:
        allowed   : bool
        tier      : str   — the resolved tier (unchanged; lifecycle.py cannot alter tier)
        reason    : str   — approval or refusal reason
        t_level   : str | None
        de_escalation : bool | None
        edge      : tuple[str, str] | None
        collision_hits : list[str]  — only present when a collision screen ran
        events_emitted : bool
        docket_item_written : bool

    NEVER raises.
    """
    result: dict[str, Any] = {
        "allowed": False,
        "tier": tier,
        "reason": "",
        "t_level": None,
        "de_escalation": None,
        "edge": None,
        "events_emitted": False,
        "docket_item_written": False,
    }
    try:
        r = Path(root) if root is not None else Path(__file__).resolve().parent.parent.parent

        # ── Hard fence: scored_path_surface ──────────────────────────────────
        if scored_path_surface:
            result["reason"] = (
                "adding a scored_path_surface is prohibited: "
                + _REFUSAL_REASON
            )
            log.warning("lifecycle.transition: REFUSED (scored_path_surface) for %s", lobe_id)
            return result

        # ── Hard fence: mastermind authority ─────────────────────────────────
        if mastermind_authority:
            result["reason"] = (
                "flipping a mastermind_context authority switch is prohibited: "
                + _REFUSAL_REASON
            )
            log.warning("lifecycle.transition: REFUSED (mastermind_authority) for %s", lobe_id)
            return result

        # ── Hard fence: tier-raising destination ─────────────────────────────
        # The tier parameter reflects what the caller is requesting the lobe's
        # synapse tier to become.  If it is a promotion tier, refuse.
        if tier in _FORBIDDEN_TIER_DESTINATIONS:
            result["reason"] = _REFUSAL_REASON
            log.warning(
                "lifecycle.transition: REFUSED (tier=%r, promotion) for %s", tier, lobe_id
            )
            return result

        # ── Allowed-transition table lookup ───────────────────────────────────
        edge_key = (from_state, to_state)
        edge_meta = _ALLOWED_EDGES.get(edge_key)
        if edge_meta is None:
            result["reason"] = (
                f"edge {from_state!r}→{to_state!r} is not in the allowed-transition table"
            )
            return result

        result["edge"] = edge_key
        result["t_level"] = edge_meta["t_level"]
        result["de_escalation"] = edge_meta.get("de_escalation", False)

        # ── Collision screen for onboarding edges ─────────────────────────────
        if edge_meta.get("requires_collision_screen"):
            hits = _collision_screen(lobe_id, r)
            result["collision_hits"] = hits
            if hits:
                result["reason"] = (
                    f"collision screen blocked transition: {'; '.join(hits)}"
                )
                return result

        # ── Transition is allowed ─────────────────────────────────────────────
        result["allowed"] = True
        final_reason = reason or edge_meta["description"]
        result["reason"] = final_reason

        if emit:
            result["events_emitted"] = _emit_lifecycle_event(
                lobe_id, from_state, to_state, edge_meta, final_reason, r
            )
            result["docket_item_written"] = _write_docket_item(
                lobe_id, from_state, to_state, edge_meta, final_reason, r
            )

    except Exception as exc:  # noqa: BLE001
        log.warning("lifecycle.transition: unexpected error: %s", exc)
        result["reason"] = f"unexpected error: {exc}"

    return result


def allowed_edges() -> list[dict[str, Any]]:
    """Return the full allowed-transition table as a list of dicts.

    Useful for tests and documentation.  NEVER raises.
    """
    return [
        {
            "from_state": fs,
            "to_state": ts,
            **meta,
        }
        for (fs, ts), meta in _ALLOWED_EDGES.items()
    ]


def is_de_escalation(from_state: str, to_state: str) -> bool:
    """Return True if this edge is a de-escalation (demotion) edge.

    NEVER raises.
    """
    try:
        edge_key = (from_state, to_state)
        meta = _ALLOWED_EDGES.get(edge_key)
        if meta is None:
            return False
        return bool(meta.get("de_escalation", False))
    except Exception:  # noqa: BLE001
        return False
