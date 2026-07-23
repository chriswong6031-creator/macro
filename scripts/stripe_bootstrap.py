#!/usr/bin/env python3
"""Idempotent Stripe object bootstrap for the monetization billing spine (MNZ W2).

Reads the pricing catalog from ``config/plans.yml`` and creates — or reconciles, on
re-run — the matching Stripe objects:

  * 2 Products (Insider, Pro), tagged ``metadata.mnz_product`` so we can find them again.
  * 4 recurring Prices addressed by stable ``lookup_key`` (portable across test/live),
    so application code never hardcodes environment-specific price IDs.
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
def _ensure_product(pkey: str, name: str, dry: bool) -> str | None:
    for prod in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        if (prod.metadata or {}).get(PRODUCT_METADATA_KEY) == pkey:
            print(f"  product  {pkey:<24} reuse   {prod.id}")
            return prod.id
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
    for pkey, prod in cat["products"].items():
        pid = _ensure_product(pkey, prod["name"], args.dry_run)
        _attach_features(pid, [feat_ids.get(f) for f in prod.get("features", [])], args.dry_run)
        for interval_name, pspec in prod["prices"].items():
            price_id = _ensure_price(pid, pspec, currency, args.dry_run)
            summary.append((f"{pkey}/{interval_name}", pspec["lookup_key"], price_id))

    print("\nsummary (application code addresses prices by lookup_key, not id):")
    for label, lk, pid in summary:
        print(f"  {label:<20} lookup_key={lk:<18} id={pid or '(dry-run)'}")
    print("\ndone. Re-running is safe (idempotent).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
