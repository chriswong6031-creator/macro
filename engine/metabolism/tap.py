"""engine.metabolism.tap — T2 tap card builder (V2-D §5).

Every T2 ask is ONE clear decision with a recommended default.
On timeout, a CONSERVATIVE default from an IMMUTABLE safe-defaults table fires.
No wall of options (operator wants minimal work).

IMMUTABLE safe-defaults table: conservative defaults that fire on timeout.
The loop cannot change these defaults (they live in code, not in config that
the loop authors). Only human PRs may modify the safe-defaults table.

NEVER-RAISE CONTRACT: all functions return safe fallbacks on any error.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.tap_card.v1"

# ── IMMUTABLE safe-defaults table ─────────────────────────────────────────────
# Conservative defaults that fire on timeout.  The loop NEVER overrides these.
# Only human-authored PRs may modify this table.
#
# Format: {tap_kind: {recommended_default: str, timeout_default: str, note: str}}
_SAFE_DEFAULTS: dict[str, dict[str, str]] = {
    # Lobe lifecycle decisions
    "promote_lobe": {
        "recommended_default": "defer",
        "timeout_default": "defer",
        "note": "Conservative: no promotion without operator explicit approval.",
    },
    "demote_lobe": {
        "recommended_default": "hold",
        "timeout_default": "hold",
        "note": "Conservative: ambiguous misses hold per R-V2-10 (regime-aware).",
    },
    "authorize_build": {
        "recommended_default": "review_later",
        "timeout_default": "review_later",
        "note": "Conservative: no auto-authorization of new builds.",
    },
    "raise_roster_cap": {
        "recommended_default": "hold",
        "timeout_default": "hold",
        "note": "Conservative: roster cap changes require explicit operator input.",
    },
    "arm_loop": {
        "recommended_default": "stay_paused",
        "timeout_default": "stay_paused",
        "note": "Conservative: AUTONOMY_PAUSED stays until operator explicitly arms.",
    },
    "revert_plan": {
        "recommended_default": "hold_for_review",
        "timeout_default": "hold_for_review",
        "note": "Conservative: revert plans held until operator reviews triage.",
    },
    "budget_override": {
        "recommended_default": "deny",
        "timeout_default": "deny",
        "note": "Conservative: budget overrides denied by default.",
    },
    # Generic fallback for unknown tap kinds
    "_default": {
        "recommended_default": "defer",
        "timeout_default": "defer",
        "note": "Conservative generic default: defer and review.",
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_tap_card(
    headline: str,
    why_now: str,
    tap_kind: str = "_default",
    options: list[dict[str, str]] | None = None,
    deadline: str | None = None,
    recommended_default: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a T2 tap card — ONE clear decision for the operator.

    Parameters
    ----------
    headline : str
        Short plain-English headline for what the operator must decide.
    why_now : str
        One sentence explaining why this needs attention now.
    tap_kind : str
        The category of decision (used for safe-defaults table lookup).
    options : list[dict] | None
        At most 3 options, each {label: str, value: str, note: str}.
        If more than 3 are provided, only the first 3 are kept.
    deadline : str | None
        ISO date by which the operator should decide.
    recommended_default : str | None
        If not provided, looked up from the safe-defaults table.
    context : dict | None
        Additional context (proposal_id, cycle_id, etc.) — display only.

    Returns
    -------
    dict — tap card (schema metabolism.tap_card.v1).  NEVER raises.
    """
    try:
        safe = _SAFE_DEFAULTS.get(tap_kind) or _SAFE_DEFAULTS["_default"]
        timeout_default = safe["timeout_default"]
        rec = recommended_default or safe["recommended_default"]

        # Cap options at 3 (operator wants minimal work — no wall of options)
        if options and len(options) > 3:
            log.warning("tap.build_tap_card: trimming options from %d to 3", len(options))
            options = options[:3]

        card: dict[str, Any] = {
            "schema": SCHEMA,
            "ts": _now_iso(),
            "headline": headline,
            "why_now": why_now,
            "tap_kind": tap_kind,
            "recommended_default": rec,
            "options": options or [],
            "deadline": deadline,
            "auto_action_on_timeout": {
                "action": timeout_default,
                "note": (
                    f"Conservative default fires on timeout: '{timeout_default}'. "
                    f"{safe['note']} "
                    f"This default is immutable (loop cannot relax it)."
                ),
            },
            "authority": {
                "is_context_only": True,
                "display_only": True,
                "not_a_signal": True,
                "tier": "T2",
                "note": "Tap card is display-only. The operator's decision is the action.",
            },
            "context": context or {},
        }
        return card

    except Exception as exc:  # noqa: BLE001
        log.warning("tap.build_tap_card: %s", exc)
        return {
            "schema": SCHEMA,
            "ts": _now_iso(),
            "headline": headline,
            "why_now": why_now,
            "tap_kind": tap_kind,
            "recommended_default": "defer",
            "options": [],
            "deadline": None,
            "auto_action_on_timeout": {"action": "defer", "note": "Conservative fallback."},
            "authority": {"is_context_only": True, "display_only": True, "tier": "T2"},
            "context": {},
        }


def get_safe_default(tap_kind: str) -> str:
    """Return the safe timeout default for a given tap_kind.  NEVER raises."""
    try:
        return _SAFE_DEFAULTS.get(tap_kind, _SAFE_DEFAULTS["_default"])["timeout_default"]
    except Exception:  # noqa: BLE001
        return "defer"


def write_tap_card(
    card: dict[str, Any],
    root: Path | None = None,
    filename: str | None = None,
) -> Path | None:
    """Write a tap card to data/metabolism/tap/<filename>.json atomically.

    Returns the path written, or None on error.  NEVER raises.
    """
    try:
        if root is None:
            root = Path(__file__).resolve().parent.parent.parent
        tap_dir = Path(root) / "data" / "metabolism" / "tap"
        tap_dir.mkdir(parents=True, exist_ok=True)
        name = filename or f"tap_{card.get('ts', _now_iso()).replace(':', '').replace('+', '')}.json"
        out_path = tap_dir / name
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")
        tmp.replace(out_path)
        return out_path
    except Exception as exc:  # noqa: BLE001
        log.warning("tap.write_tap_card: %s", exc)
        return None
