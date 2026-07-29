"""tests/_xgw6_helpers.py — shared fixtures for the XG-W6 suites.

Only one thing lives here, and it is the thing both suites need: a reply-queue
item carrying a REAL critic stamp. The stamp is produced by
``reply_critics.stamp`` over a full roster rather than hand-written, because
``reply_queue.validate_critic_stamp`` refuses a partial or forged one — a helper
that hand-rolled the dict would be testing against a stamp the store rejects.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_queue as rq  # noqa: E402

NOW = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)
PARENT = "Hyperscaler capex keeps climbing but credit spreads are widening."
DRAFT = (
    "IG spreads widened 12.5% this week while capex guidance held.\n\n"
    "The price move is the reaction. Credit is the test."
)


def pass_stamp() -> dict:
    """A stamp from a full critic roster — the only shape the store admits."""
    return rc.stamp({
        "verdict": "pass",
        "rejected_by": [],
        "critics": [{"critic": name, "verdict": "pass", "reasons": []}
                    for name in rc.CRITICS],
    })


def make_reply_item(*, account: str = "kelly",
                    thread: str = "1900000000000000001",
                    draft: str = DRAFT, tier: str = "relationship",
                    now: datetime = NOW, ttl_min: int = 45) -> dict:
    return rq.make_item(
        account=account,
        target_url=f"https://x.com/somequant/status/{thread}",
        parent_author="somequant",
        parent_excerpt=PARENT,
        draft=draft,
        tier=tier,
        score=0.8,
        score_components={"author_tier": 0.26},
        critics=pass_stamp(),
        ttl_min=ttl_min,
        now=now,
    )
