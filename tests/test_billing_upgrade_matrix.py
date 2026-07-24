"""Unit tests for the pure upgrade-matrix helpers + interval-carrying reducer in app/billing.py.

No network, no Stripe, no Supabase — these exercise pure functions against config/plans.yml's
tier_rank ([free, insider, pro]). The matrix law (operator order): from any (tier, interval) the
only legal moves step UP on the tier axis (never below the current tier), step UP on the interval
axis (monthly < annual, never annual -> monthly), and must actually change the plan. That is exactly
five reachable transitions; everything else is a downgrade or a no-op.

  billing._upgrade_allowed — the 5 allowed lanes + the representative denials.
  billing._entitlement_from_state — plan_interval carried for active/trialing, None for free.

Run:
    python -m pytest tests/test_billing_upgrade_matrix.py -v
"""
from __future__ import annotations

import pytest

from app import billing


# --------------------------------------------------------------------------- #
# _upgrade_allowed — the matrix law
# --------------------------------------------------------------------------- #
# Every legal move the operator specified: insider·m -> {insider·a, pro·m, pro·a},
# pro·m -> pro·a, insider·a -> pro·a. These five, and only these five.
_ALLOWED = [
    ("insider", "monthly", "insider", "annual"),
    ("insider", "monthly", "pro", "monthly"),
    ("insider", "monthly", "pro", "annual"),
    ("pro", "monthly", "pro", "annual"),
    ("insider", "annual", "pro", "annual"),
]

# Representative denials: tier step-down, interval step-down, the top plan (pro·annual) has nowhere
# to go, and every same-plan no-op.
_DENIED = [
    ("pro", "monthly", "insider", "monthly"),     # tier down
    ("pro", "annual", "insider", "annual"),       # tier down (annual)
    ("insider", "annual", "insider", "monthly"),  # interval down
    ("pro", "annual", "pro", "monthly"),          # interval down
    ("insider", "annual", "pro", "monthly"),      # tier up but interval down -> net not allowed
    ("pro", "annual", "pro", "annual"),           # top plan, no-op
    ("pro", "annual", "insider", "monthly"),      # pro·annual -> anything lower
    ("insider", "monthly", "insider", "monthly"), # same plan
    ("pro", "monthly", "pro", "monthly"),         # same plan
]


@pytest.mark.parametrize("cur_t,cur_i,tgt_t,tgt_i", _ALLOWED)
def test_upgrade_allowed_lanes(cur_t, cur_i, tgt_t, tgt_i):
    assert billing._upgrade_allowed(cur_t, cur_i, tgt_t, tgt_i) is True


@pytest.mark.parametrize("cur_t,cur_i,tgt_t,tgt_i", _DENIED)
def test_upgrade_denied_lanes(cur_t, cur_i, tgt_t, tgt_i):
    assert billing._upgrade_allowed(cur_t, cur_i, tgt_t, tgt_i) is False


def test_upgrade_allowed_is_total_over_the_grid():
    # Exhaustive cross-check: over the full 4x4 grid, exactly the five _ALLOWED pairs are True.
    plans = [("insider", "monthly"), ("insider", "annual"), ("pro", "monthly"), ("pro", "annual")]
    allowed = {
        (ct, ci, tt, ti)
        for ct, ci in plans for tt, ti in plans
        if billing._upgrade_allowed(ct, ci, tt, ti)
    }
    assert allowed == set(_ALLOWED)


def test_upgrade_garbage_pair_fails_closed():
    # Unknown tier/interval ranks -1; the >= only holds against itself, which the no-op clause
    # then rejects -> a garbage pair is never a legal upgrade.
    assert billing._upgrade_allowed("bogus", "weekly", "bogus", "weekly") is False
    assert billing._upgrade_allowed("insider", "monthly", "bogus", "annual") is False


# --------------------------------------------------------------------------- #
# _upgrade_denial — the honest 409 detail
# --------------------------------------------------------------------------- #
def test_denial_message_names_the_current_plan_on_noop():
    assert billing._upgrade_denial("pro", "annual", "pro", "annual") == "already on pro annual"
    assert billing._upgrade_denial("insider", "monthly", "insider", "monthly") == "already on insider monthly"


def test_denial_message_flags_downgrades():
    msg = billing._upgrade_denial("pro", "annual", "insider", "monthly")
    assert "downgrade" in msg.lower()
    assert "pro annual" in msg  # names the current plan


# --------------------------------------------------------------------------- #
# _entitlement_from_state — plan_interval carry
# --------------------------------------------------------------------------- #
def test_reducer_carries_interval_for_active_sub():
    r = billing._entitlement_from_state(
        [{"status": "active", "current_period_end": 1900000000, "tier": "pro", "interval": "annual"}],
        [],
    )
    assert r["tier"] == "pro" and r["plan_interval"] == "annual"


def test_reducer_carries_interval_for_trialing_sub():
    r = billing._entitlement_from_state(
        [{"status": "trialing", "current_period_end": 1, "tier": "insider", "interval": "monthly"}],
        [],
    )
    assert r["status"] == "trialing" and r["plan_interval"] == "monthly"


def test_reducer_carries_best_subs_interval_across_multiple():
    # highest-ranked entitling sub wins on tier AND on interval — the reducer reports the chosen sub.
    r = billing._entitlement_from_state(
        [
            {"status": "active", "current_period_end": 1, "tier": "insider", "interval": "monthly"},
            {"status": "active", "current_period_end": 1, "tier": "pro", "interval": "annual"},
        ],
        [],
    )
    assert r["tier"] == "pro" and r["plan_interval"] == "annual"


def test_reducer_interval_none_when_free_no_sub():
    assert billing._entitlement_from_state([], [])["plan_interval"] is None


def test_reducer_interval_none_when_only_canceled():
    r = billing._entitlement_from_state(
        [{"status": "canceled", "current_period_end": 5, "tier": "pro", "interval": "annual"}], []
    )
    assert r["tier"] == "free" and r["plan_interval"] is None


def test_reducer_tolerates_sub_without_interval_key():
    # _compute_entitlement always sets "interval", but the reducer is pure — a caller (or an old
    # fixture) omitting the key must not KeyError; missing -> None.
    r = billing._entitlement_from_state(
        [{"status": "active", "current_period_end": 1, "tier": "insider"}], []
    )
    assert r["tier"] == "insider" and r["plan_interval"] is None
