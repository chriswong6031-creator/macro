"""Offline contract test for Stripe Product resolution across a catalog RENAME.

`scripts/stripe_bootstrap.py` finds a Product by ``metadata.mnz_product = <config/plans.yml
products key>``. Renaming that key (insider -> essential, Phase 2 of the tier rename) would
leave the LIVE Product unfindable and make the next bootstrap CREATE a second one, orphaning
the prices, entitlement features, portal configuration and every existing subscription that
hangs off the original id. ``legacy_product_keys`` in the catalog is the record that stops
that: the old Product is ADOPTED — metadata re-tagged, display name updated in place — which
is also how the new name ("Essential") reaches Checkout, invoices and the customer portal.

What is pinned here:
  * the three ``_ensure_product`` outcomes and their PRECEDENCE — a direct tag beats a legacy
    tag beats CREATE, whatever order Stripe lists the products in (that precedence is the
    idempotency: a second run takes the direct path and writes nothing);
  * the adoption is a ``Product.modify``, never a ``Product.create``;
  * the dry run reports the real product id and writes nothing;
  * the catalog still CARRIES the migration record — with the fallback removed, the same
    scenario falls through to CREATE (the mutation check, run as a test rather than by hand).

Run:
    python -m pytest tests/test_stripe_bootstrap_products.py -v
"""
from __future__ import annotations

import copy
import types
from pathlib import Path

import pytest
import yaml

from scripts import stripe_bootstrap as bootstrap

ROOT = Path(__file__).resolve().parents[1]

SPEC = {"name": "Essential", "tier": "essential"}


def _catalog() -> dict:
    with (ROOT / "config" / "plans.yml").open() as fh:
        return yaml.safe_load(fh)


def _product(pid: str, tag: str | None, name: str = "old name"):
    return types.SimpleNamespace(
        id=pid, name=name, metadata=({"mnz_product": tag} if tag else {}))


class _FakeProducts:
    """Minimal stand-in for ``stripe.Product`` recording every write."""

    def __init__(self, listed):
        self.listed = list(listed)
        self.modified: list[tuple[str, dict]] = []
        self.created: list[dict] = []

    # stripe.Product.list(...).auto_paging_iter()
    def list(self, **kwargs):
        return types.SimpleNamespace(auto_paging_iter=lambda: iter(self.listed))

    def modify(self, pid, **kwargs):
        self.modified.append((pid, kwargs))
        return _product(pid, kwargs.get("metadata", {}).get("mnz_product"),
                        kwargs.get("name", ""))

    def create(self, **kwargs):
        self.created.append(kwargs)
        return _product("prod_new", kwargs.get("metadata", {}).get("mnz_product"),
                        kwargs.get("name", ""))


@pytest.fixture
def products(monkeypatch):
    """Install a fake ``stripe`` whose Product surface the test controls."""
    def _install(listed):
        fake_products = _FakeProducts(listed)
        monkeypatch.setattr(
            bootstrap, "stripe", types.SimpleNamespace(Product=fake_products))
        return fake_products
    return _install


# --------------------------------------------------------------------------- #
# the three outcomes
# --------------------------------------------------------------------------- #
def test_legacy_tagged_product_is_adopted_in_place(products, capsys):
    """The live Product keeps its id; only its metadata tag and name move."""
    fake = products([_product("prod_live", "insider", name="Insider")])

    pid = bootstrap._ensure_product("essential", SPEC, ["insider"], False)

    assert pid == "prod_live", "the existing Stripe object must be reused, not replaced"
    assert fake.created == [], "adopting a renamed product must never CREATE a second one"
    assert fake.modified == [
        ("prod_live", {"metadata": {"mnz_product": "essential"}, "name": "Essential"}),
    ], "adoption re-tags the metadata AND updates the customer-visible name"
    out = capsys.readouterr().out
    assert "reuse-legacy prod_live (migrating metadata+name)" in out
    assert "[dry-run]" not in out


def test_direct_tag_wins_over_a_legacy_tag_whatever_the_listing_order(products, capsys):
    """The idempotency pin: a second run finds its own tag and writes nothing.

    The legacy-tagged product is listed FIRST on purpose — precedence must come from the
    tag, not from Stripe's ordering, or a stale duplicate could win the race.
    """
    fake = products([
        _product("prod_stale", "insider", name="Insider"),
        _product("prod_live", "essential", name="Essential"),
    ])

    pid = bootstrap._ensure_product("essential", SPEC, ["insider"], False)

    assert pid == "prod_live"
    assert fake.modified == [] and fake.created == []
    out = capsys.readouterr().out
    assert "reuse   prod_live" in out
    assert "reuse-legacy" not in out


def test_create_only_when_no_tag_matches(products, capsys):
    fake = products([_product("prod_other", "pro", name="Pro")])

    pid = bootstrap._ensure_product("essential", SPEC, ["insider"], False)

    assert pid == "prod_new"
    assert fake.modified == []
    assert fake.created == [
        {"name": "Essential", "metadata": {"mnz_product": "essential"}}]
    assert "create  prod_new" in capsys.readouterr().out


def test_dry_run_reports_the_live_id_and_writes_nothing(products, capsys):
    """A dry run must name the object it WOULD adopt, so the operator can check the id."""
    fake = products([_product("prod_live", "insider", name="Insider")])

    pid = bootstrap._ensure_product("essential", SPEC, ["insider"], True)

    assert pid == "prod_live", "the product exists — the price/portal lines below need its id"
    assert fake.modified == [] and fake.created == []
    out = capsys.readouterr().out
    assert "reuse-legacy prod_live (migrating metadata+name)" in out
    assert "[dry-run]" in out


def test_dry_run_create_path_still_returns_none(products, capsys):
    products([])
    assert bootstrap._ensure_product("essential", SPEC, ["insider"], True) is None
    assert "CREATE  (dry-run)" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# the catalog half — the record the fallback reads
# --------------------------------------------------------------------------- #
def test_the_live_catalog_adopts_the_pre_rename_essential_product(products, capsys):
    """End to end off the REAL catalog — the wiring `main()` uses, not a hand-fed list.

    This is the test the mutation check breaks: with `legacy_product_keys` deleted from
    config/plans.yml the same live Product falls through to CREATE and this goes red.
    """
    cat = _catalog()
    spec = cat["products"]["essential"]
    fake = products([_product("prod_live", "insider", name="Insider")])

    pid = bootstrap._ensure_product(
        "essential", spec, bootstrap._legacy_product_keys(cat, "essential"), False)

    assert pid == "prod_live", "the pre-rename Stripe Product must be adopted"
    assert fake.created == [], "a CREATE here orphans every live Essential subscription"
    assert fake.modified == [
        ("prod_live", {"metadata": {"mnz_product": "essential"}, "name": "Essential"})]
    assert "reuse-legacy prod_live (migrating metadata+name)" in capsys.readouterr().out


def test_catalog_records_the_essential_product_key_history():
    cat = _catalog()
    assert bootstrap._legacy_product_keys(cat, "essential") == ["insider"], (
        "config/plans.yml legacy_product_keys must keep the pre-rename product key — "
        "without it the next bootstrap creates a SECOND Stripe Product")
    assert bootstrap._legacy_product_keys(cat, "pro") == [], "pro was never renamed"


def test_catalog_keeps_every_retired_essential_price_key():
    """Legacy lookup keys are PERMANENT: dropping one downgrades its subscribers to free.

    ``insider_2026_v2_*`` are the pair that matters most — they were the LIVE prices on the
    day of the rename, so every paying Essential subscriber sits on one of them.
    """
    legacy = list(_catalog()["products"]["essential"]["legacy_lookup_keys"])
    for key in ("insider_monthly", "insider_annual",
                "insider_2026_monthly", "insider_2026_annual",
                "insider_2026_v2_monthly", "insider_2026_v2_annual"):
        assert key in legacy, f"{key} must stay mapped or its subscriptions resolve to free"


def test_without_the_legacy_record_the_live_product_would_be_duplicated(products):
    """Mutation check: delete ``legacy_product_keys`` and the SAME scenario CREATEs.

    This is what proves the fallback is load-bearing rather than decorative — the adoption
    tests above would still pass against a hardcoded list.
    """
    mutated = copy.deepcopy(_catalog())
    mutated.pop("legacy_product_keys", None)
    assert bootstrap._legacy_product_keys(mutated, "essential") == []

    fake = products([_product("prod_live", "insider", name="Insider")])
    pid = bootstrap._ensure_product(
        "essential", SPEC, bootstrap._legacy_product_keys(mutated, "essential"), False)

    assert pid == "prod_new" and fake.created, (
        "with no legacy record the bootstrap orphans the live product — which is exactly "
        "why config/plans.yml must carry it")
