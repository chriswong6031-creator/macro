#!/usr/bin/env python3
"""Idempotent Stripe object bootstrap for the monetization billing spine (MNZ W2).

Reads the pricing catalog from ``config/plans.yml`` and creates — or reconciles, on
re-run — the matching Stripe objects:

  * 2 Products (Essential, Pro), tagged ``metadata.mnz_product`` so we can find them again.
    A product key that has been RENAMED carries its history in the catalog's
    ``legacy_product_keys``; the live Product is then adopted (metadata re-tagged, display
    name updated) rather than duplicated — see ``_ensure_product``.
  * 4 recurring Prices addressed by stable ``lookup_key`` (portable across test/live),
    so application code never hardcodes environment-specific price IDs.
  * Limited-offer Coupons + PromotionCodes whose real Stripe redemption count powers
    customer-facing inventory (no simulated scarcity). The PromotionCode owns the
    first-acquisition cap; the Coupon remains reusable for grandfathered customers.
  * 3 Entitlement Features (Stripe Entitlements, GA), attached to their products.

Idempotency: every object is looked up before creation and reused when found; a re-run
is a no-op that just re-prints the summary. A price whose amount/interval drifted from
config is re-created and the lookup_key is *transferred* onto the new price.

Usage:
    STRIPE_SECRET_KEY=sk_test_... python scripts/stripe_bootstrap.py
    STRIPE_SECRET_KEY=sk_test_... python scripts/stripe_bootstrap.py --dry-run

Safety: refuses a live key (``sk_live_``) unless ``--allow-live`` is passed. The secret
key is read from the environment only — never a file, never a CLI arg.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required (pip install pyyaml)")

try:
    import stripe
except ImportError:  # pragma: no cover
    sys.exit("The stripe SDK is required (pip install 'stripe>=11,<13')")

CATALOG_PATH = Path(__file__).resolve().parents[1] / "config" / "plans.yml"
PRODUCT_METADATA_KEY = "mnz_product"


def _load_catalog() -> dict:
    with CATALOG_PATH.open() as fh:
        cat = yaml.safe_load(fh)
    if cat.get("schema") != "plans_catalog.v1":
        sys.exit(f"unexpected catalog schema: {cat.get('schema')!r}")
    return cat


# --------------------------------------------------------------------------- #
# Entitlement features
# --------------------------------------------------------------------------- #
def _ensure_feature(key: str, name: str, dry: bool) -> str | None:
    existing = stripe.entitlements.Feature.list(lookup_key=key, limit=1).data
    if existing:
        feat = existing[0]
        print(f"  feature  {key:<24} reuse   {feat.id}")
        return feat.id
    if dry:
        print(f"  feature  {key:<24} CREATE  (dry-run)")
        return None
    feat = stripe.entitlements.Feature.create(name=name, lookup_key=key)
    print(f"  feature  {key:<24} create  {feat.id}")
    return feat.id


# --------------------------------------------------------------------------- #
# Products (found by metadata tag) + feature attachment
# --------------------------------------------------------------------------- #
def _legacy_product_keys(cat: dict, pkey: str) -> list[str]:
    """Former ``products`` keys for ``pkey``, from the catalog's ``legacy_product_keys``.

    Read through one function so ``main`` and the tests resolve it identically — and so a
    catalog that LOSES the entry degrades to "no history" in exactly one place.
    """
    entry = (cat.get("legacy_product_keys") or {}).get(pkey) or []
    return [str(k).strip() for k in entry if str(k).strip()]


def _ensure_product(pkey: str, prod_spec: dict, legacy_keys: list[str], dry: bool) -> str | None:
    """Find-or-create the Stripe Product for catalog key ``pkey``.

    Three outcomes, in strict precedence order:

    ``reuse``
        A Product already tagged ``metadata.mnz_product == pkey``. Nothing is written. A
        direct tag WINS over a legacy one no matter which order Stripe lists them in, which
        is what makes the migration below idempotent: the second run takes this path.
    ``reuse-legacy``
        No direct tag, but a Product tagged with one of ``legacy_keys`` — the same object
        under its pre-rename key. It is ADOPTED: the metadata tag moves to ``pkey`` and the
        display name is updated. This is deliberately a modify, not a create. Every live
        subscription, price, entitlement feature and portal entry hangs off that Product id;
        creating a second one would strand all of them, and Stripe shows ``name`` on
        Checkout, invoices and the customer portal, so this modify is also the only way a
        renamed product's new name ever reaches a paying customer.
    ``CREATE``
        Neither matched — a genuinely new product (or a fresh environment).
    """
    legacy = {k for k in legacy_keys if k and k != pkey}
    legacy_hit = None
    for prod in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        tag = (prod.metadata or {}).get(PRODUCT_METADATA_KEY)
        if tag == pkey:
            print(f"  product  {pkey:<24} reuse   {prod.id}")
            return prod.id
        if legacy_hit is None and tag in legacy:
            legacy_hit = prod
    name = prod_spec["name"]
    if legacy_hit is not None:
        suffix = "  [dry-run]" if dry else ""
        print(f"  product  {pkey:<24} reuse-legacy {legacy_hit.id} "
              f"(migrating metadata+name){suffix}")
        if not dry:
            stripe.Product.modify(
                legacy_hit.id, metadata={PRODUCT_METADATA_KEY: pkey}, name=name)
        # The object EXISTS either way, so a dry run reports its real id — the price and
        # portal lines below then reconcile against the product they will actually touch.
        return legacy_hit.id
    if dry:
        print(f"  product  {pkey:<24} CREATE  (dry-run)")
        return None
    prod = stripe.Product.create(name=name, metadata={PRODUCT_METADATA_KEY: pkey})
    print(f"  product  {pkey:<24} create  {prod.id}")
    return prod.id


def _attach_features(product_id: str | None, feature_ids: list[str | None], dry: bool) -> None:
    if not product_id or dry:
        return
    attached = {
        pf.entitlement_feature.id if hasattr(pf.entitlement_feature, "id") else pf.entitlement_feature
        for pf in stripe.Product.list_features(product_id, limit=100).auto_paging_iter()
    }
    for fid in feature_ids:
        if not fid or fid in attached:
            continue
        stripe.Product.create_feature(product_id, entitlement_feature=fid)
        print(f"           attach feature {fid} -> product {product_id}")


# --------------------------------------------------------------------------- #
# Prices (addressed by stable lookup_key)
# --------------------------------------------------------------------------- #
def _ensure_price(product_id: str | None, spec: dict, currency: str, dry: bool) -> str | None:
    lookup_key = spec["lookup_key"]
    amount = int(spec["unit_amount"])
    interval = spec["interval"]
    existing = stripe.Price.list(lookup_keys=[lookup_key], active=True, limit=1).data
    if existing:
        pr = existing[0]
        same = (
            pr.unit_amount == amount
            and pr.currency == currency
            and (pr.recurring or {}).get("interval") == interval
        )
        if same:
            print(f"  price    {lookup_key:<24} reuse   {pr.id}  ({amount/100:.2f} {currency}/{interval})")
            return pr.id
        print(f"  price    {lookup_key:<24} DRIFT   {pr.id} != config; re-creating")
    if dry:
        print(f"  price    {lookup_key:<24} CREATE  (dry-run)")
        return None
    pr = stripe.Price.create(
        product=product_id,
        currency=currency,
        unit_amount=amount,
        recurring={"interval": interval},
        lookup_key=lookup_key,
        transfer_lookup_key=True,  # steal the key from a drifted price if one holds it
    )
    print(f"  price    {lookup_key:<24} create  {pr.id}  ({amount/100:.2f} {currency}/{interval})")
    return pr.id


# --------------------------------------------------------------------------- #
# Limited offers (uncapped Coupon + capped PromotionCode)
# --------------------------------------------------------------------------- #
def _promo_coupon_id(promo) -> str | None:
    """Read both pre-Basil `coupon` and Basil `promotion.coupon` response shapes."""
    coupon = getattr(promo, "coupon", None)
    if coupon:
        return coupon.id if hasattr(coupon, "id") else coupon
    promotion = getattr(promo, "promotion", None) or {}
    coupon = promotion.get("coupon") if hasattr(promotion, "get") else None
    return coupon.id if hasattr(coupon, "id") else coupon


def _ensure_offer(
    offer_key: str,
    spec: dict,
    product_id: str | None,
    regular_amount: int,
    currency: str,
    dry: bool,
) -> tuple[str | None, str | None]:
    """Create/reuse an uncapped Coupon and its capped customer-facing PromotionCode."""
    if not product_id:
        print(f"  offer    {offer_key:<24} SKIP    (product unresolved)")
        return None, None
    offer_amount = int(spec["unit_amount"])
    amount_off = regular_amount - offer_amount
    cap = int(spec["max_redemptions"])
    if amount_off <= 0:
        sys.exit(f"offer {offer_key}: unit_amount must be below the regular annual price")

    coupon_id = spec["coupon_id"]
    try:
        coupon = stripe.Coupon.retrieve(coupon_id)
    except stripe.error.InvalidRequestError:
        coupon = None
    if coupon:
        applies = getattr(coupon, "applies_to", None) or {}
        products = list(applies.get("products") or []) if hasattr(applies, "get") else []
        metadata = getattr(coupon, "metadata", None) or {}
        owned = metadata.get("mnz_offer") == offer_key if hasattr(metadata, "get") else False
        # stripe-python 12 / API 2024-06-20 accepts applies_to on create but some
        # accounts omit it from Coupon.retrieve. Treat an omitted scope as
        # unverifiable—not drift—only when our ownership metadata and every
        # immutable financial term still match. A returned scope must contain the
        # intended product.
        scope_matches = not products or product_id in products
        same = (
            coupon.amount_off == amount_off
            and coupon.currency == currency
            and coupon.duration == spec.get("duration", "forever")
            and coupon.max_redemptions is None
            and owned
            and scope_matches
        )
        if not same:
            sys.exit(
                f"offer {offer_key}: coupon {coupon_id} drifted; coupons are immutable, "
                "choose a new coupon_id after reviewing the live subscriptions")
        print(f"  coupon   {offer_key:<24} reuse   {coupon.id}  (-{amount_off/100:.2f} {currency})")
    elif dry:
        print(f"  coupon   {offer_key:<24} CREATE  (dry-run, -{amount_off/100:.2f} {currency})")
        coupon = None
    else:
        coupon = stripe.Coupon.create(
            id=coupon_id,
            name=spec["name"],
            amount_off=amount_off,
            currency=currency,
            duration=spec.get("duration", "forever"),
            applies_to={"products": [product_id]},
            metadata={"mnz_offer": offer_key},
        )
        print(f"  coupon   {offer_key:<24} create  {coupon.id}  (-{amount_off/100:.2f} {currency})")

    code = spec["promotion_code"]
    existing = stripe.PromotionCode.list(code=code, limit=10).data
    promo = existing[0] if existing else None
    if promo:
        same = (
            _promo_coupon_id(promo) == coupon_id
            and promo.max_redemptions == cap
            and bool(promo.active)
        )
        if not same:
            sys.exit(
                f"offer {offer_key}: promotion code {code} drifted; choose a new code "
                "rather than silently changing a customer-visible offer")
        print(f"  promo    {offer_key:<24} reuse   {promo.id}  "
              f"({promo.times_redeemed}/{cap} redeemed)")
    elif dry:
        print(f"  promo    {offer_key:<24} CREATE  (dry-run, cap={cap})")
        promo = None
    else:
        # stripe-python <13 uses the 2024-06-20 API shape (`coupon=`). The app's
        # dependency is intentionally pinned there; Basil's `promotion={...}` shape
        # can replace this when the SDK pin is upgraded in a reviewed migration.
        promo = stripe.PromotionCode.create(
            coupon=coupon_id,
            code=code,
            max_redemptions=cap,
            metadata={"mnz_offer": offer_key},
        )
        print(f"  promo    {offer_key:<24} create  {promo.id}  (0/{cap} redeemed)")
    return (coupon.id if coupon else None, promo.id if promo else None)


def _retire_promotion_codes(codes: list[str], current_code: str, dry: bool) -> None:
    """Deactivate superseded acquisition codes without touching existing discounts."""
    for code in codes:
        if not code or code == current_code:
            continue
        promos = stripe.PromotionCode.list(code=code, limit=10).data
        for promo in promos:
            if not bool(promo.active):
                print(f"  promo    {code:<24} retired {promo.id}")
                continue
            if dry:
                print(f"  promo    {code:<24} RETIRE  {promo.id} (dry-run)")
                continue
            stripe.PromotionCode.modify(promo.id, active=False)
            print(f"  promo    {code:<24} retire  {promo.id}")


# --------------------------------------------------------------------------- #
# Customer Portal configuration
# --------------------------------------------------------------------------- #
# The portal is where a customer updates a card, cancels, or DOWNGRADES — everything
# /api/billing/upgrade deliberately refuses (its matrix is strictly upward). It used to be
# configured by hand, and the 2026-07-25 go-live audit found it carrying
# `subscription_update.proration_behavior = "none"`: a customer switching plans there would
# have been charged full freight with NO credit for time they had already paid for, while
# the identical move through /api/billing/upgrade credits it. That is now set here.
#
# READ-BACK CAVEAT worth knowing before you "verify" this: Stripe **validates**
# features.subscription_update.products on write (a bogus product id is rejected) but does
# **not** echo the field back on any current API version — it is absent from the response
# on 2024-06-20 through 2025-08-27.basil alike. So the API cannot tell you which products
# a portal configuration allows, and a `products: null` read is NOT evidence that none are
# configured. Verify plan switching BEHAVIOURALLY instead: open a portal session and load
# .../subscriptions/<sub>/update — it lists the sellable plans plus a Monthly/Yearly toggle.
#
# Configuring it HERE (rather than by clicking) makes it idempotent, reviewable, and
# reproducible against the live account with the same command as the products/prices —
# and removes the ambiguity the unreadable field would otherwise leave.
#
# PRORATION_BEHAVIOR note: "create_prorations" writes the credit/charge lines onto the
# NEXT invoice instead of billing them on the spot. That is the right default for a
# self-serve surface where the customer confirms without ever being shown an amount — the
# credit arithmetic is identical to the in-app lane, only the collection moment differs.
# Set it to "always_invoice" if you want portal switches to charge immediately, exactly
# like /api/billing/upgrade does.
PORTAL_PRORATION_BEHAVIOR = "create_prorations"


def _ensure_portal_configuration(products: dict[str, list[str]], dry: bool) -> str | None:
    """Create or update the DEFAULT customer-portal configuration from the catalog.

    `products` maps product_id -> [price_id, ...] (its monthly + annual prices), which is
    the shape Stripe wants for features.subscription_update.products.
    """
    entries = [{"product": pid, "prices": prices} for pid, prices in products.items() if pid and prices]
    if not entries:
        print("  portal   (skipped — no products/prices resolved)")
        return None

    features = {
        "subscription_update": {
            "enabled": True,
            "default_allowed_updates": ["price"],
            "proration_behavior": PORTAL_PRORATION_BEHAVIOR,
            "products": entries,
        },
        # at_period_end: a cancelling customer keeps what they already paid for.
        "subscription_cancel": {"enabled": True, "mode": "at_period_end",
                                "proration_behavior": "none"},
        "payment_method_update": {"enabled": True},
        "invoice_history": {"enabled": True},
        "customer_update": {"enabled": True, "allowed_updates": ["email", "address", "tax_id"]},
    }

    existing = [c for c in stripe.billing_portal.Configuration.list(limit=20).auto_paging_iter()
                if c.is_default]
    if dry:
        verb = "UPDATE" if existing else "CREATE"
        print(f"  portal   default config       {verb}  (dry-run) "
              f"[{len(entries)} products, proration={PORTAL_PRORATION_BEHAVIOR}]")
        return None
    if existing:
        cfg = stripe.billing_portal.Configuration.modify(existing[0].id, features=features)
        print(f"  portal   default config       update  {cfg.id} "
              f"[{len(entries)} products, proration={PORTAL_PRORATION_BEHAVIOR}]")
    else:
        cfg = stripe.billing_portal.Configuration.create(features=features)
        print(f"  portal   default config       create  {cfg.id} "
              f"[{len(entries)} products, proration={PORTAL_PRORATION_BEHAVIOR}]")
    return cfg.id


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print planned actions; create nothing")
    ap.add_argument("--allow-live", action="store_true", help="permit a live (sk_live_) key")
    args = ap.parse_args()

    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        sys.exit("STRIPE_SECRET_KEY not set in the environment")
    if key.startswith("sk_live_") and not args.allow_live:
        sys.exit("refusing a LIVE key without --allow-live (W-LEGAL gates live-mode)")
    stripe.api_key = key
    mode = "LIVE" if key.startswith("sk_live_") else "TEST"

    cat = _load_catalog()
    currency = cat.get("currency", "usd")
    print(f"Stripe bootstrap — {mode} mode  ({'dry-run' if args.dry_run else 'apply'})")
    print(f"catalog: {CATALOG_PATH}")

    print("features:")
    feat_ids = {f["key"]: _ensure_feature(f["key"], f["name"], args.dry_run) for f in cat["features"]}

    print("products + prices:")
    summary: list[tuple[str, str, str | None]] = []
    portal_products: dict[str, list[str]] = {}
    product_ids: dict[str, str | None] = {}
    for pkey, prod in cat["products"].items():
        pid = _ensure_product(pkey, prod, _legacy_product_keys(cat, pkey), args.dry_run)
        product_ids[pkey] = pid
        _attach_features(pid, [feat_ids.get(f) for f in prod.get("features", [])], args.dry_run)
        for interval_name, pspec in prod["prices"].items():
            price_id = _ensure_price(pid, pspec, currency, args.dry_run)
            summary.append((f"{pkey}/{interval_name}", pspec["lookup_key"], price_id))
            if pid and price_id:
                portal_products.setdefault(pid, []).append(price_id)

    print("limited offers:")
    for offer_key, offer_spec in (cat.get("offers") or {}).items():
        tier = offer_spec["tier"]
        product_key, product = next(
            (key, value) for key, value in cat["products"].items() if value["tier"] == tier)
        current = product["prices"][offer_spec["interval"]]
        base_spec = {
            "lookup_key": offer_spec.get("base_lookup_key", current["lookup_key"]),
            "unit_amount": int(offer_spec.get("base_unit_amount", current["unit_amount"])),
            "interval": current["interval"],
        }
        # Reconcile the immutable offer anchor independently so a fresh Stripe environment can
        # still reproduce a founder's exact total after future public rack-price changes.
        _ensure_price(product_ids.get(product_key), base_spec, currency, args.dry_run)
        regular = int(base_spec["unit_amount"])
        _ensure_offer(
            offer_key, offer_spec, product_ids.get(product_key), regular, currency, args.dry_run)
        _retire_promotion_codes(
            list(offer_spec.get("retire_promotion_codes") or []),
            offer_spec["promotion_code"],
            args.dry_run,
        )

    print("customer portal:")
    _ensure_portal_configuration(portal_products, args.dry_run)

    print("\nsummary (application code addresses prices by lookup_key, not id):")
    for label, lk, pid in summary:
        print(f"  {label:<20} lookup_key={lk:<18} id={pid or '(dry-run)'}")
    print("\ndone. Re-running is safe (idempotent).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
