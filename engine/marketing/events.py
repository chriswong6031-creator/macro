"""engine.marketing.events — Growth event taxonomy + spine.

GROWTH_EVENTS is the full instrumented event-name list from docket §12.1.A.
Every event needs campaign, publication, partner, and experiment context.
"""
from __future__ import annotations

from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Full taxonomy (docket §12.1.A)
# ─────────────────────────────────────────────────────────────────────────────

GROWTH_EVENTS: list[str] = [
    "landing_view",
    "public_object_view",
    "source_opened",
    "dossier_generated",
    "why_moving_run",
    "share_generated",
    "share_opened",
    "embed_view",
    "bot_command",
    "creator_asset_used",
    "account_created",
    "watchlist_saved",
    "preview_started",
    "first_value_reached",
    "second_session_value",
    "alert_opened",
    "report_viewed",
    "checkout_started",
    "subscription_created",
    "invoice_paid",
    "renewal",
    "cancel_requested",
    "cancellation",
    "refund",
    "chargeback",
    "referral_created",
    "referral_converted",
]


# ─────────────────────────────────────────────────────────────────────────────
# Spine
# ─────────────────────────────────────────────────────────────────────────────

def spine() -> dict[str, Any]:
    """Return the event-spine state dict.

    In seed state all observed counts are zero.
    """
    return {
        "instrumented": list(GROWTH_EVENTS),
        "observed": 0,
        "schema_version": 1,
    }
