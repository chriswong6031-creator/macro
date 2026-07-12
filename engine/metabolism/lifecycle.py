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


# ── Genesis accountability clock ─────────────────────────────────────────────

def _load_genesis_accountability_days(root: Path) -> int:
    """Load genesis_accountability_days from config/metabolism_budget.yml.

    Defaults to 45 if the key is absent (W2 may not have landed yet).
    NEVER raises.
    """
    default = 45
    try:
        import yaml  # noqa: PLC0415
        p = root / "config" / "metabolism_budget.yml"
        if not p.exists():
            return default
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return int(data.get("genesis_accountability_days", default))
    except Exception as exc:  # noqa: BLE001
        log.warning("lifecycle._load_genesis_accountability_days: %s — default %d", exc, default)
        return default


def _find_probation_start(lobe_id: str, root: Path) -> "datetime | None":
    """Find when a lobe entered probation from the governance ledger.

    Scans data/neuralweb/governance.jsonl for metabolism_adjudication events
    where target == lobe_id and evidence.to_state == "probation".
    Returns the earliest such event's ts as a datetime, or None if not found.

    NEVER raises.
    """
    try:
        from engine.neuralweb.governance import load_events  # noqa: PLC0415
        events = load_events(root=root, event_type="metabolism_adjudication", target=lobe_id)
        candidates: list[datetime] = []
        for ev in events:
            ev_target = str(ev.get("target") or "")
            if ev_target != lobe_id:
                continue
            evidence = ev.get("evidence") or {}
            if str(evidence.get("to_state") or "") == "probation":
                ts_raw = str(ev.get("ts") or "")
                try:
                    dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    candidates.append(dt)
                except Exception:  # noqa: BLE001
                    pass
        if candidates:
            return min(candidates)  # earliest probation entry
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("lifecycle._find_probation_start(%s): %s", lobe_id, exc)
        return None


def _has_matured_contracts(lobe_id: str, root: Path) -> bool:
    """Return True if the lobe has at least one matured (graded) verify record.

    Scans data/metabolism/verify/*.json for records naming this lobe.
    A graded NULL counts as matured (context-accrual law — only SILENCE trips
    the clock, not honest nulls).  UNVERIFIABLE counts too — it is a graded
    outcome (the result was checked; the answer was unverifiable, which is
    honest; it is NOT silence).

    NEVER raises.
    """
    try:
        verify_dir = root / "data" / "metabolism" / "verify"
        if not verify_dir.exists():
            return False
        for vf in sorted(verify_dir.glob("*.json")):
            try:
                record = json.loads(vf.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            # A PENDING record is NOT matured — the contract was registered but
            # not yet graded. Counting it as matured would let a lobe dodge the
            # accountability clock forever (#2341 review). Only a graded record
            # (any outcome incl. honest UNVERIFIABLE/null) counts.
            outcome = str((record.get("realized") or {}).get("outcome") or "").upper()
            classification = str((record.get("triage") or {}).get("classification") or "").lower()
            if outcome == "PENDING" or classification == "pending":
                continue
            # Match this lobe: record.lobe, nested contract.lobe (the shape real
            # verify records actually emit), then a cycle_id EXACT-suffix guard
            # (avoid a substring false-positive across unrelated cycle ids).
            record_lobe = str(record.get("lobe") or "").strip()
            contract_lobe = str(
                (record.get("contract") or {}).get("lobe") or ""
            ).strip()
            if lobe_id in (record_lobe, contract_lobe):
                return True
            cycle_field = str(record.get("cycle_id") or "")
            if cycle_field == lobe_id or cycle_field.endswith(f"-{lobe_id}"):
                return True
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("lifecycle._has_matured_contracts(%s): %s", lobe_id, exc)
        return False


def sweep_genesis_accountability(
    root: "str | Path | None" = None,
    today: "str | None" = None,
) -> list[dict[str, Any]]:
    """Sweep probation lobes against the genesis accountability clock (R-V6-6).

    For each charter with lifecycle_state=="probation":
      - If (today - probation_start) > genesis_accountability_days AND
        the lobe has ZERO matured contracts → emit a demotion docket item
        (probation → demoted) if that edge is allowed, otherwise emit the
        docket item directly.
      - Honest nulls DO NOT trip the clock; only silence does.
      - Probation start = earliest governance event for proposed→probation.
        If unrecoverable, fail-open (no demotion) with a logged warning.

    Returns a list of result dicts (one per checked lobe).
    NEVER raises.  The sweep must not break verify.
    """
    results: list[dict[str, Any]] = []

    try:
        r = Path(root) if root is not None else Path(__file__).resolve().parent.parent.parent
        today_date: "datetime.date | None" = None
        try:
            from datetime import date as date_cls  # noqa: PLC0415
            if today:
                today_date = datetime.fromisoformat(today).date()
            else:
                today_date = datetime.now(timezone.utc).date()
        except Exception as exc:  # noqa: BLE001
            log.warning("lifecycle.sweep_genesis_accountability: bad today=%r: %s — skip", today, exc)
            return results

        accountability_days = _load_genesis_accountability_days(r)

        # Load charters
        try:
            import yaml  # noqa: PLC0415
            charters_path = r / "config" / "lobe_charters.yml"
            if not charters_path.exists():
                log.info("lifecycle.sweep_genesis_accountability: no lobe_charters.yml — skip")
                return results
            data = yaml.safe_load(charters_path.read_text(encoding="utf-8")) or {}
            charters = data.get("charters") or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("lifecycle.sweep_genesis_accountability: cannot load charters: %s", exc)
            return results

        for lobe_id, charter in charters.items():
            lobe_result: dict[str, Any] = {
                "lobe_id": lobe_id,
                "action": "skipped",
                "reason": "",
            }
            try:
                lc_state = (charter or {}).get("lifecycle_state") or ""
                if lc_state != "probation":
                    continue

                # Find probation start
                start_dt = _find_probation_start(lobe_id, r)
                if start_dt is None:
                    lobe_result.update({
                        "action": "skipped_no_start",
                        "reason": (
                            f"lobe {lobe_id!r}: no governance record of probation start — "
                            "fail-open (no demotion). Add a governance event when probation "
                            "is conferred."
                        ),
                    })
                    log.warning("lifecycle.sweep_genesis_accountability: %s", lobe_result["reason"])
                    results.append(lobe_result)
                    continue

                start_date = start_dt.date() if hasattr(start_dt, "date") else today_date
                days_elapsed = (today_date - start_date).days

                if days_elapsed <= accountability_days:
                    lobe_result.update({
                        "action": "within_deadline",
                        "reason": (
                            f"{days_elapsed}/{accountability_days} days since probation "
                            f"(started {start_date})"
                        ),
                        "days_elapsed": days_elapsed,
                        "days_remaining": accountability_days - days_elapsed,
                    })
                    results.append(lobe_result)
                    continue

                # Past deadline — check for matured contracts
                has_contracts = _has_matured_contracts(lobe_id, r)
                if has_contracts:
                    lobe_result.update({
                        "action": "has_contracts_no_demotion",
                        "reason": (
                            f"{lobe_id!r}: {days_elapsed} days since probation "
                            f"(>{accountability_days}) but has matured contracts — "
                            "context-accrual law: graded nulls are not silence; clock holds."
                        ),
                        "days_elapsed": days_elapsed,
                    })
                    results.append(lobe_result)
                    continue

                # Zero matured contracts + past deadline → demotion docket
                reason_str = (
                    f"genesis accountability clock tripped: {days_elapsed} days since "
                    f"probation start ({start_date}) exceeds limit of "
                    f"{accountability_days} days with zero matured contracts. "
                    f"Only SILENCE trips the clock — honest nulls would have been accepted. "
                    f"Operator-visible demotion proposal emitted (R-V6-6)."
                )

                # Check if probation→demoted is an allowed edge
                edge_allowed = ("probation", "demoted") in _ALLOWED_EDGES

                if edge_allowed:
                    tr = transition(
                        from_state="probation",
                        to_state="demoted",
                        lobe_id=lobe_id,
                        reason=reason_str,
                        tier="display",
                        root=r,
                        emit=True,
                    )
                    lobe_result.update({
                        "action": "demotion_proposed",
                        "reason": reason_str,
                        "transition_allowed": tr.get("allowed"),
                        "transition_result": tr,
                        "days_elapsed": days_elapsed,
                    })
                    if tr.get("allowed"):
                        log.warning(
                            "lifecycle.sweep_genesis_accountability: DEMOTION PROPOSED for %r "
                            "(%d days, 0 matured contracts)",
                            lobe_id, days_elapsed,
                        )
                    else:
                        log.warning(
                            "lifecycle.sweep_genesis_accountability: demotion edge refused for %r: %s",
                            lobe_id, tr.get("reason"),
                        )
                else:
                    # Edge not in table — emit docket directly (never silent)
                    docket_written = _write_docket_item(
                        lobe_id=lobe_id,
                        from_state="probation",
                        to_state="demoted",
                        edge_meta={
                            "t_level": "T1",
                            "de_escalation": True,
                            "description": (
                                "Genesis accountability clock: probation→demoted docket "
                                "(edge added by sweep when not in main table)"
                            ),
                        },
                        reason=reason_str,
                        root=r,
                    )
                    lobe_result.update({
                        "action": "demotion_docket_direct",
                        "reason": reason_str,
                        "docket_written": docket_written,
                        "days_elapsed": days_elapsed,
                    })
                    log.warning(
                        "lifecycle.sweep_genesis_accountability: direct docket for %r "
                        "(%d days, 0 matured contracts, edge not in table)",
                        lobe_id, days_elapsed,
                    )

            except Exception as exc:  # noqa: BLE001
                lobe_result.update({
                    "action": "error",
                    "reason": f"per-lobe error: {exc}",
                })
                log.warning("lifecycle.sweep_genesis_accountability[%s]: %s", lobe_id, exc)

            results.append(lobe_result)

    except Exception as exc:  # noqa: BLE001
        log.warning("lifecycle.sweep_genesis_accountability: outer error: %s", exc)

    return results
