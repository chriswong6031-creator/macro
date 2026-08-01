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

from pathlib import Path

import pytest
import yaml

from app import billing
from lib import tiers

ROOT = Path(__file__).resolve().parents[1]


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


# --------------------------------------------------------------------------- #
# The 'essential' alias (rename migration, Phase 1) — an aliased row must behave
# EXACTLY like the canonical one it stands for, on both axes of the matrix.
# --------------------------------------------------------------------------- #
def test_normalize_tier_is_identity_on_canonical_values():
    """The whole safety argument for arming this: nothing that exists today moves."""
    for t in ("free", "insider", "pro", "unlimited"):
        assert tiers.normalize_tier(t) == t


def test_normalize_tier_maps_essential_to_the_wire_value():
    assert tiers.normalize_tier("essential") == "insider"
    assert tiers.normalize_tier("  ESSENTIAL  ") == "insider"


def test_normalize_tier_leaves_an_unknown_string_for_the_callers_enum():
    """It widens what is ACCEPTED; it never decides what is VALID."""
    assert tiers.normalize_tier("bogus") == "bogus"
    assert tiers.normalize_tier(None) == ""


def test_the_live_catalog_still_declares_the_display_rename():
    """The premise the alias rests on: plans.yml renamed the NAME, not the wire value."""
    catalog = yaml.safe_load((ROOT / "config" / "plans.yml").read_text())
    insider = catalog["products"]["insider"]
    assert insider["tier"] == "insider", "Phase 1 must not flip the stored value"
    assert insider["name"] == "Essential"
    assert tiers.normalize_tier(insider["name"]) == insider["tier"]


def test_the_alias_is_DERIVED_from_the_catalog_not_a_hand_kept_list(tmp_path, monkeypatch):
    """Rename the product in a throwaway catalog and the alias must follow it.

    Asserting `normalize_tier('essential') == 'insider'` against the real catalog proves
    nothing about derivation — the static floor alone would satisfy it. This drives the
    catalog path with a name the floor has never heard of.
    """
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "plans.yml").write_text(yaml.safe_dump({
        "products": {"insider": {"tier": "insider", "name": "Desk Pass"},
                     "pro": {"tier": "pro", "name": "Pro"}},
        "tier_rank": ["free", "insider", "pro"],
    }))
    monkeypatch.setattr(tiers, "ROOT", tmp_path)
    tiers.reset_cache()
    try:
        assert tiers.normalize_tier("desk pass") == "insider"
        assert tiers.normalize_tier("Desk Pass") == "insider"
        # the static floor survives alongside whatever the catalog adds
        assert tiers.normalize_tier("essential") == "insider"
    finally:
        monkeypatch.undo()
        tiers.reset_cache()
    assert tiers.normalize_tier("desk pass") == "desk pass", "the real catalog is back"


def test_a_display_name_can_never_shadow_another_products_wire_value(tmp_path, monkeypatch):
    """A catalog naming one product after another product's TIER must not reroute it —
    the one way a display rename could become a real entitlement bug."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "plans.yml").write_text(yaml.safe_dump({
        "products": {"insider": {"tier": "insider", "name": "Pro"},
                     "pro": {"tier": "pro", "name": "Pro Plus"}},
        "tier_rank": ["free", "insider", "pro"],
    }))
    monkeypatch.setattr(tiers, "ROOT", tmp_path)
    tiers.reset_cache()
    try:
        assert tiers.normalize_tier("pro") == "pro", "'pro' must never resolve to 'insider'"
        assert tiers.normalize_tier("free") == "free"
    finally:
        tiers.reset_cache()


def test_an_unreadable_catalog_degrades_to_the_static_floor(tmp_path, monkeypatch):
    """normalize_tier runs inside request paths; it may never raise on a bad catalog."""
    monkeypatch.setattr(tiers, "ROOT", tmp_path)   # no config/plans.yml at all
    tiers.reset_cache()
    try:
        assert tiers.normalize_tier("essential") == "insider"
        assert tiers.normalize_tier("pro") == "pro"
    finally:
        tiers.reset_cache()


@pytest.mark.parametrize("cur_t,cur_i,tgt_t,tgt_i", _ALLOWED + _DENIED)
def test_essential_rows_walk_the_matrix_exactly_like_insider(cur_t, cur_i, tgt_t, tgt_i):
    """Substituting the alias on EITHER axis changes no verdict, anywhere on the grid."""
    canonical = billing._upgrade_allowed(cur_t, cur_i, tgt_t, tgt_i)
    alias = {"insider": "essential"}
    assert billing._upgrade_allowed(alias.get(cur_t, cur_t), cur_i, tgt_t, tgt_i) is canonical
    assert billing._upgrade_allowed(cur_t, cur_i, alias.get(tgt_t, tgt_t), tgt_i) is canonical
    assert billing._upgrade_allowed(
        alias.get(cur_t, cur_t), cur_i, alias.get(tgt_t, tgt_t), tgt_i) is canonical


def test_an_unnormalized_alias_would_make_a_downgrade_look_legal():
    """The specific bug the normalize-inside-_upgrade_allowed hop prevents.

    An alias ranks -1 like any unknown string, so an un-normalized current tier of
    'essential' out-ranks nothing: pro -> essential would read as an UPGRADE. This asserts
    the ranking that produces that, so the test fails if someone drops the hop.
    """
    rank = billing._tier_rank()
    assert "essential" not in rank, "Phase 2 changes this test, not this behaviour"
    assert billing._upgrade_allowed("essential", "annual", "insider", "annual") is False
    assert billing._upgrade_allowed("pro", "annual", "essential", "annual") is False


def test_upgrade_target_enum_is_catalog_driven_not_a_literal():
    """/upgrade used to hardcode ('insider','pro') while checkout sold from the catalog."""
    assert billing._product_tiers() == {
        str(p["tier"]) for p in billing._catalog()["products"].values()}
    assert "free" not in billing._product_tiers()
