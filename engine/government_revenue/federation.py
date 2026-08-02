"""Authority-safe federation helpers for Government Revenue consumers.

These selectors may annotate candidates that another engine already admitted.
They cannot create, rank, gate, size, or escalate a candidate.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .freshness import effective_freshness


_FORBIDDEN_AUTHORITY = (
    "can_rank",
    "can_size",
    "can_gate",
    "can_originate_signal",
    "can_add_candidates",
    "can_escalate",
)


def _display_only_authority(value: Any) -> bool:
    """Require the complete typed authority fence, not merely no literal ``True``."""

    return (
        isinstance(value, dict)
        and value.get("tier") == "display"
        and value.get("context_only") is True
        and all(value.get(key) is False for key in _FORBIDDEN_AUTHORITY)
    )


def _nonempty_strings(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    rows = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return rows if len(rows) == len(value) else None


def reviewed_award_change_context(
    payload: dict[str, Any],
    ticker: str,
    cutoff: Any | None,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return current, receipt-bound award changes with reviewed issuer paths.

    Unmapped or rule-derived events remain visible on the governed workbench but
    do not cross into Prophet or Neural Web ticker context.
    """

    evaluated = effective_freshness(payload, reference=cutoff)
    if str(evaluated.get("award_events") or "").lower() != "ok":
        return []
    workspace = payload.get("procurement_workspace") or {}
    if workspace.get("schema_version") != "government_procurement_workspace.v2":
        return []
    symbol = str(ticker or "").strip().upper()
    if not symbol or limit <= 0:
        return []

    cutoff_at: pd.Timestamp | None = None
    if cutoff is not None:
        try:
            cutoff_at = pd.Timestamp(cutoff)
            cutoff_at = (
                cutoff_at.tz_localize("UTC")
                if cutoff_at.tzinfo is None
                else cutoff_at.tz_convert("UTC")
            )
        except (TypeError, ValueError, OverflowError):
            return []

    result: list[dict[str, Any]] = []
    for event in workspace.get("events") or []:
        if not isinstance(event, dict) or event.get("kind") != "award_change":
            continue
        if not _display_only_authority(event.get("authority")):
            continue
        change = event.get("change")
        if not isinstance(change, dict):
            continue
        known_at = change.get("known_at")
        try:
            event_known = pd.Timestamp(known_at)
            event_known = (
                event_known.tz_localize("UTC")
                if event_known.tzinfo is None
                else event_known.tz_convert("UTC")
            )
        except (TypeError, ValueError, OverflowError):
            continue
        if cutoff_at is not None and event_known > cutoff_at:
            continue
        evidence = event.get("evidence")
        if (
            not isinstance(evidence, dict)
            or evidence.get("mapping_class") != "reviewed"
            or not isinstance(evidence.get("receipts"), list)
            or not evidence.get("receipts")
            or not all(isinstance(receipt, dict) for receipt in evidence["receipts"])
        ):
            continue
        impact = next(
            (
                item for item in event.get("listed_company_impacts") or []
                if isinstance(item, dict)
                and str(item.get("ticker") or "").upper() == symbol
                and item.get("relation_semantic") == "reviewed"
                and item.get("resolution_state") in {"confirmed", "reviewed"}
                and _nonempty_strings(item.get("evidence_refs")) is not None
                and isinstance(item.get("ownership_path"), list)
                and item.get("ownership_path")
                and all(isinstance(edge, dict) for edge in item["ownership_path"])
            ),
            None,
        )
        if impact is None:
            continue
        award = event.get("award_change")
        if not isinstance(award, dict) or award.get("source_rail") not in {
            "usaspending_award_snapshot",
            "usaspending_award_action",
        }:
            continue
        primary_amount = next(
            (
                item for item in event.get("amounts") or []
                if isinstance(item, dict) and item.get("id") == event.get("primary_amount_id")
            ),
            None,
        )
        result.append({
            "event_id": event.get("event_id"),
            "event_type": award.get("event_type") or change.get("type"),
            "title": event.get("title_original"),
            "known_at": known_at,
            "effective_at": change.get("effective_at"),
            "award_key": award.get("award_key"),
            "piid": award.get("piid"),
            "action_id": award.get("action_id"),
            "recipient_name": award.get("recipient_name"),
            "source_rail": award.get("source_rail"),
            "primary_amount": primary_amount,
            "issuer_link": {
                "relation_semantic": "reviewed",
                "resolution_state": impact.get("resolution_state"),
                "confidence": impact.get("confidence"),
                "materiality": impact.get("materiality"),
                "evidence_refs": (_nonempty_strings(impact.get("evidence_refs")) or [])[:6],
            },
            "allowed_behavior": "annotate_only",
        })
        if len(result) >= limit:
            break
    return result


__all__ = ["reviewed_award_change_context"]
