"""engine.metabolism.roster_governor — Roster-budget governor (V2-C, R-V2-7).

Enforces max_active_nonscored_lobes and max_probation_lobes from
config/metabolism_budget.yml (IMMUTABLE).

When the charter queue would exceed the cap, the loop does NOT silently block.
Instead it emits a digest ASK tap card so the operator can raise the cap.

Enforcement point: applier.consume_charter_proposals (charter ONBOARDING into
the PROPOSE gauntlet) — wired 2026-08-04 (roster-cap reconciliation memo,
research/ROSTER_CAP_RECONCILIATION_2026-08-04.md).  Before that date this
module had no production caller and the roster crossed its cap silently via
session PRs.

NEVER-RAISE CONTRACT: all functions return safe defaults on any error.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.roster_governor.v1"

_DEFAULT_MAX_ACTIVE = 66   # fallback if budget.yml unreadable
_DEFAULT_MAX_PROBATION = 5


def _resolve_root(root: str | Path | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _load_budget(root: Path) -> dict:
    """Load metabolism_budget.yml; return {} on any error (NEVER-RAISE)."""
    try:
        import yaml  # noqa: PLC0415
        p = root / "config" / "metabolism_budget.yml"
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        return raw or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("roster_governor._load_budget: %s", exc)
        return {}


def check_charter_budget(
    proposed_lobe_id: str,
    proposed_lifecycle_state: str = "probation",
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Check whether adding a new charter would exceed the roster cap.

    If the cap would be exceeded, emits a digest ASK tap card (via tap.py)
    so the operator can raise the cap.  NEVER silently blocks.

    The ACTIVE cap is checked for every charter proposal regardless of its
    proposed lifecycle state (a newborn needs an active slot eventually, and
    the ADJUDICATE genesis screen denies on the same roster-count predicate
    at genesis time — R-V6-3a).  The PROBATION cap is checked only for
    proposals arriving in 'probation' state.

    Parameters
    ----------
    proposed_lobe_id : str
        The lobe being proposed for charter.
    proposed_lifecycle_state : str
        The lifecycle state of the proposed lobe ('probation' is typical
        for a new charter proposal).
    root : str | Path | None

    Returns
    -------
    dict with keys:
        ok               : bool — True if within budget
        cap_exceeded     : bool
        current_active   : int
        max_active       : int
        current_probation: int
        max_probation    : int
        digest_ask_emitted : bool
        reason           : str

    NEVER raises.
    """
    result: dict[str, Any] = {
        "ok": True,
        "cap_exceeded": False,
        "current_active": 0,
        "max_active": _DEFAULT_MAX_ACTIVE,
        "current_probation": 0,
        "max_probation": _DEFAULT_MAX_PROBATION,
        "digest_ask_emitted": False,
        "reason": "",
    }
    try:
        r = _resolve_root(root)
        budget = _load_budget(r)

        max_active = int(budget.get("max_active_nonscored_lobes", _DEFAULT_MAX_ACTIVE))
        max_probation = int(budget.get("max_probation_lobes", _DEFAULT_MAX_PROBATION))
        result["max_active"] = max_active
        result["max_probation"] = max_probation

        # Load current charter counts
        from engine.metabolism.lobe_registry import load as load_charters  # noqa: PLC0415
        charter_result = load_charters(r)
        charters = charter_result.get("charters", {})

        current_active = sum(
            1 for c in charters.values()
            if c.get("lifecycle_state") == "active"
            and c.get("tier") in ("display", "shadow", "confirmer")
        )
        current_probation = sum(
            1 for c in charters.values()
            if c.get("lifecycle_state") == "probation"
        )
        result["current_active"] = current_active
        result["current_probation"] = current_probation

        # Check caps.
        # R-V6-3a ALIGNMENT (2026-08-04 reconciliation): the ACTIVE-roster cap
        # fires for ANY charter proposal once the active roster is at/over cap,
        # not only for proposals that arrive already-active.  The genesis
        # screen (adjudicate._genesis_screen) hard-denies genesis on
        # current_active >= max_active regardless of the proposal's lifecycle
        # state, so the operator ASK must fire on the same predicate — the old
        # state-conditioned branch was unreachable for the genesis flow, whose
        # proposals arrive as 'proposed'/'probation'.
        exceeded_active = current_active >= max_active
        exceeded_probation = (
            proposed_lifecycle_state == "probation"
            and current_probation >= max_probation
        )

        if exceeded_active or exceeded_probation:
            result["ok"] = False
            result["cap_exceeded"] = True
            cap_type = "active" if exceeded_active else "probation"
            current_n = current_active if exceeded_active else current_probation
            max_n = max_active if exceeded_active else max_probation
            result["reason"] = (
                f"roster cap exceeded for {cap_type}: "
                f"current={current_n} >= max={max_n}. "
                f"Proposed lobe {proposed_lobe_id!r} cannot be chartered without "
                f"operator raising max_{cap_type}_nonscored_lobes in "
                f"config/metabolism_budget.yml (IMMUTABLE — requires T2 operator tap)."
            )
            # Emit digest ASK (NEVER silently block)
            result["digest_ask_emitted"] = _emit_cap_digest_ask(
                proposed_lobe_id=proposed_lobe_id,
                cap_type=cap_type,
                current_n=current_n,
                max_n=max_n,
                root=r,
            )
        else:
            result["reason"] = (
                f"within budget: active={current_active}/{max_active} "
                f"probation={current_probation}/{max_probation}"
            )

    except Exception as exc:  # noqa: BLE001
        log.warning("roster_governor.check_charter_budget: %s", exc)
        result["reason"] = f"unexpected error: {exc}"

    return result


def _emit_cap_digest_ask(
    proposed_lobe_id: str,
    cap_type: str,
    current_n: int,
    max_n: int,
    root: Path,
) -> bool:
    """Emit a digest ASK tap card for the operator.  NEVER raises."""
    try:
        from engine.metabolism.tap import build_tap_card, write_tap_card  # noqa: PLC0415
        card = build_tap_card(
            headline=f"Roster cap hit — operator must raise cap to charter {proposed_lobe_id!r}",
            why_now=(
                f"The {cap_type} roster cap ({current_n}/{max_n}) is full. "
                f"A new lobe {proposed_lobe_id!r} cannot be chartered until "
                f"max_{cap_type}_nonscored_lobes is raised in "
                f"config/metabolism_budget.yml (IMMUTABLE — requires a T2 operator-tap PR)."
            ),
            tap_kind="raise_roster_cap",
            options=[
                {
                    "label": "Raise cap by 3",
                    "value": f"raise_cap_{cap_type}_by_3",
                    "note": f"Edit metabolism_budget.yml max_{cap_type}_nonscored_lobes += 3",
                },
                {
                    "label": "Hold",
                    "value": "hold",
                    "note": "Do not charter the new lobe; revisit next cycle.",
                },
            ],
            context={
                "proposed_lobe_id": proposed_lobe_id,
                "cap_type": cap_type,
                "current_n": current_n,
                "max_n": max_n,
            },
        )
        # Stable filename: one standing card per cap_type, overwritten on each
        # re-check — nightly onboarding must not spam a new timestamped card
        # per cycle while the cap stays exceeded.
        write_tap_card(card, root=root, filename=f"tap_roster_cap_{cap_type}.json")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("roster_governor._emit_cap_digest_ask: %s", exc)
        # Fallback: write a simple governance event
        try:
            from engine.neuralweb.governance import append_event  # noqa: PLC0415
            append_event(
                event_type="metabolism_adjudication",
                target=f"roster_cap/{proposed_lobe_id}",
                article=None,
                authored_by="roster_governor",
                evidence={
                    "cap_type": cap_type,
                    "current_n": current_n,
                    "max_n": max_n,
                    "ask": (
                        f"Operator: raise max_{cap_type}_nonscored_lobes "
                        f"in config/metabolism_budget.yml to charter {proposed_lobe_id!r}."
                    ),
                },
                note=f"Roster cap ASK: {proposed_lobe_id!r} cannot be chartered without cap raise",
                root=root,
            )
        except Exception:  # noqa: BLE001
            pass
        return False
