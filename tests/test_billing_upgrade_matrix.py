"""Unit tests for the pure upgrade-matrix helpers + interval-carrying reducer in app/billing.py.

No network, no Stripe, no Supabase — these exercise pure functions against config/plans.yml's
tier_rank ([free, essential, pro]). The matrix law (operator order): from any (tier, interval) the
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
# Every legal move the operator specified: essential·m -> {essential·a, pro·m, pro·a},
# pro·m -> pro·a, essential·a -> pro·a. These five, and only these five.
_ALLOWED = [
    ("essential", "monthly", "essential", "annual"),
    ("essential", "monthly", "pro", "monthly"),
    ("essential", "monthly", "pro", "annual"),
    ("pro", "monthly", "pro", "annual"),
    ("essential", "annual", "pro", "annual"),
]

# Representative denials: tier step-down, interval step-down, the top plan (pro·annual) has nowhere
# to go, and every same-plan no-op.
_DENIED = [
    ("pro", "monthly", "essential", "monthly"),       # tier down
    ("pro", "annual", "essential", "annual"),         # tier down (annual)
    ("essential", "annual", "essential", "monthly"),  # interval down
    ("pro", "annual", "pro", "monthly"),              # interval down
    ("essential", "annual", "pro", "monthly"),        # tier up but interval down -> net not allowed
    ("pro", "annual", "pro", "annual"),               # top plan, no-op
    ("pro", "annual", "essential", "monthly"),        # pro·annual -> anything lower
    ("essential", "monthly", "essential", "monthly"), # same plan
    ("pro", "monthly", "pro", "monthly"),             # same plan
]


@pytest.mark.parametrize("cur_t,cur_i,tgt_t,tgt_i", _ALLOWED)
def test_upgrade_allowed_lanes(cur_t, cur_i, tgt_t, tgt_i):
    assert billing._upgrade_allowed(cur_t, cur_i, tgt_t, tgt_i) is True


@pytest.mark.parametrize("cur_t,cur_i,tgt_t,tgt_i", _DENIED)
def test_upgrade_denied_lanes(cur_t, cur_i, tgt_t, tgt_i):
    assert billing._upgrade_allowed(cur_t, cur_i, tgt_t, tgt_i) is False


def test_upgrade_allowed_is_total_over_the_grid():
    # Exhaustive cross-check: over the full 4x4 grid, exactly the five _ALLOWED pairs are True.
    plans = [("essential", "monthly"), ("essential", "annual"), ("pro", "monthly"), ("pro", "annual")]
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
    assert billing._upgrade_allowed("essential", "monthly", "bogus", "annual") is False


# --------------------------------------------------------------------------- #
# _upgrade_denial — the honest 409 detail
# --------------------------------------------------------------------------- #
def test_denial_message_names_the_current_plan_on_noop():
    assert billing._upgrade_denial("pro", "annual", "pro", "annual") == "already on pro annual"
    assert billing._upgrade_denial("essential", "monthly", "essential", "monthly") == "already on essential monthly"


def test_denial_message_flags_downgrades():
    msg = billing._upgrade_denial("pro", "annual", "essential", "monthly")
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
        [{"status": "trialing", "current_period_end": 1, "tier": "essential", "interval": "monthly"}],
        [],
    )
    assert r["status"] == "trialing" and r["plan_interval"] == "monthly"


def test_reducer_carries_best_subs_interval_across_multiple():
    # highest-ranked entitling sub wins on tier AND on interval — the reducer reports the chosen sub.
    r = billing._entitlement_from_state(
        [
            {"status": "active", "current_period_end": 1, "tier": "essential", "interval": "monthly"},
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
        [{"status": "active", "current_period_end": 1, "tier": "essential"}], []
    )
    assert r["tier"] == "essential" and r["plan_interval"] is None


# --------------------------------------------------------------------------- #
# The 'insider' alias (rename migration, Phase 2 — the direction REVERSED).
#
# Phase 1 resolved essential -> insider. The catalog now sells `essential`, so the alias
# points the other way and the old value is PERMANENT inbound: pre-rename entitlement rows
# are never back-filled, and theme.js / onboard.js / tier_preview.js ship `immutable` with
# a far-future max-age, so a warm cache keeps sending `insider` indefinitely. A row wearing
# the old spelling must behave EXACTLY like the canonical one, on both axes of the matrix.
# --------------------------------------------------------------------------- #
def test_normalize_tier_is_identity_on_canonical_values():
    """Everything the catalog actually sells passes through untouched."""
    for t in ("free", "essential", "pro", "unlimited"):
        assert tiers.normalize_tier(t) == t


def test_normalize_tier_maps_the_pre_rename_value_to_the_wire_value():
    assert tiers.normalize_tier("insider") == "essential"
    assert tiers.normalize_tier("  INSIDER  ") == "essential"


def test_normalize_tier_leaves_an_unknown_string_for_the_callers_enum():
    """It widens what is ACCEPTED; it never decides what is VALID."""
    assert tiers.normalize_tier("bogus") == "bogus"
    assert tiers.normalize_tier(None) == ""


def test_the_live_catalog_declares_the_completed_rename():
    """The premise the alias rests on: plans.yml flipped the wire value AND kept the history."""
    catalog = yaml.safe_load((ROOT / "config" / "plans.yml").read_text())
    essential = catalog["products"]["essential"]
    assert essential["tier"] == "essential", "Phase 2 flips the stored value"
    assert essential["name"] == "Essential"
    assert "insider" not in catalog["products"], "the old product key is gone from products"
    assert catalog["legacy_product_keys"]["essential"] == ["insider"], (
        "the alias and the Stripe bootstrap read the SAME migration record")


def test_the_alias_is_DERIVED_from_the_catalog_not_a_hand_kept_list(tmp_path, monkeypatch):
    """Rename the product in a throwaway catalog and the alias must follow it.

    Asserting `normalize_tier('insider') == 'essential'` against the real catalog proves
    nothing about derivation — the static floor alone would satisfy it. This drives BOTH
    catalog paths (legacy_product_keys and the display name) with strings the floor has
    never heard of.
    """
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "plans.yml").write_text(yaml.safe_dump({
        "products": {"essential": {"tier": "essential", "name": "Desk Pass"},
                     "pro": {"tier": "pro", "name": "Pro"}},
        "legacy_product_keys": {"essential": ["scout"]},
        "tier_rank": ["free", "essential", "pro"],
    }))
    monkeypatch.setattr(tiers, "ROOT", tmp_path)
    tiers.reset_cache()
    try:
        assert tiers.normalize_tier("scout") == "essential", "legacy_product_keys drives it"
        assert tiers.normalize_tier("desk pass") == "essential", "the display name does too"
        assert tiers.normalize_tier("Desk Pass") == "essential"
        # the static floor survives alongside whatever the catalog adds
        assert tiers.normalize_tier("insider") == "essential"
    finally:
        monkeypatch.undo()
        tiers.reset_cache()
    assert tiers.normalize_tier("scout") == "scout", "the real catalog is back"


def test_a_display_name_can_never_shadow_another_products_wire_value(tmp_path, monkeypatch):
    """A catalog naming one product after another product's TIER must not reroute it —
    the one way a display rename could become a real entitlement bug."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "plans.yml").write_text(yaml.safe_dump({
        "products": {"essential": {"tier": "essential", "name": "Pro"},
                     "pro": {"tier": "pro", "name": "Pro Plus"}},
        "tier_rank": ["free", "essential", "pro"],
    }))
    monkeypatch.setattr(tiers, "ROOT", tmp_path)
    tiers.reset_cache()
    try:
        assert tiers.normalize_tier("pro") == "pro", "'pro' must never resolve to 'essential'"
        assert tiers.normalize_tier("free") == "free"
    finally:
        tiers.reset_cache()


def test_a_catalog_that_still_SELLS_the_old_value_overrules_the_static_floor(tmp_path, monkeypatch):
    """The floor points at the post-flip world; a pre-flip catalog must win over it.

    Reversing the alias direction made the floor itself capable of shadowing a canonical
    tier — pointed at a catalog that still sells `insider`, a bare floor would resolve a
    paying member's own tier to one that catalog does not offer.
    """
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "plans.yml").write_text(yaml.safe_dump({
        "products": {"insider": {"tier": "insider", "name": "Essential"},
                     "pro": {"tier": "pro", "name": "Pro"}},
        "tier_rank": ["free", "insider", "pro"],
    }))
    monkeypatch.setattr(tiers, "ROOT", tmp_path)
    tiers.reset_cache()
    try:
        assert tiers.normalize_tier("insider") == "insider", "a sold tier is never an alias"
        assert tiers.normalize_tier("essential") == "insider", "and the name still resolves"
    finally:
        tiers.reset_cache()


def test_an_unreadable_catalog_degrades_to_the_static_floor(tmp_path, monkeypatch):
    """normalize_tier runs inside request paths; it may never raise on a bad catalog."""
    monkeypatch.setattr(tiers, "ROOT", tmp_path)   # no config/plans.yml at all
    tiers.reset_cache()
    try:
        assert tiers.normalize_tier("insider") == "essential"
        assert tiers.normalize_tier("pro") == "pro"
    finally:
        tiers.reset_cache()


@pytest.mark.parametrize("cur_t,cur_i,tgt_t,tgt_i", _ALLOWED + _DENIED)
def test_pre_rename_rows_walk_the_matrix_exactly_like_the_canonical_ones(cur_t, cur_i, tgt_t, tgt_i):
    """Substituting the alias on EITHER axis changes no verdict, anywhere on the grid."""
    canonical = billing._upgrade_allowed(cur_t, cur_i, tgt_t, tgt_i)
    alias = {"essential": "insider"}
    assert billing._upgrade_allowed(alias.get(cur_t, cur_t), cur_i, tgt_t, tgt_i) is canonical
    assert billing._upgrade_allowed(cur_t, cur_i, alias.get(tgt_t, tgt_t), tgt_i) is canonical
    assert billing._upgrade_allowed(
        alias.get(cur_t, cur_t), cur_i, alias.get(tgt_t, tgt_t), tgt_i) is canonical


def test_an_unnormalized_alias_would_make_a_downgrade_look_legal():
    """The specific bug the normalize-inside-_upgrade_allowed hop prevents.

    An alias ranks -1 like any unknown string, so an un-normalized current tier of
    'insider' out-ranks nothing: pro -> insider would read as an UPGRADE. This asserts the
    ranking that produces that, so the test fails if someone drops the hop.
    """
    rank = billing._tier_rank()
    assert "insider" not in rank, "the retired value must not re-enter the ordering"
    assert billing._upgrade_allowed("insider", "annual", "essential", "annual") is False
    assert billing._upgrade_allowed("pro", "annual", "insider", "annual") is False


def test_upgrade_target_enum_is_catalog_driven_not_a_literal():
    """/upgrade used to hardcode a tier tuple while checkout sold from the catalog."""
    assert billing._product_tiers() == {
        str(p["tier"]) for p in billing._catalog()["products"].values()}
    assert "free" not in billing._product_tiers()
