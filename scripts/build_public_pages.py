"""Render the data-free public pages without invoking the market-data builders.

This is the fast path for pricing, support, and unsubscribe changes.  The full
``scripts.build_site`` entry point reads parquet stores and rebuilds thousands of
market pages; these three pages need only committed configuration and templates.

Usage: python -m scripts.build_public_pages
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import yaml
from jinja2 import Environment, FileSystemLoader

from lib import config
from lib.pages import write_page

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_public_pages")


def plans_view_model() -> dict:
    """Return the pricing view-model derived from ``config/plans.yml``."""
    catalog = yaml.safe_load((config.ROOT / "config" / "plans.yml").read_text())
    products = catalog.get("products", {})

    def tier_vm(key: str) -> dict | None:
        prod = products.get(key)
        if not prod:
            return None
        prices = prod.get("prices", {})
        monthly_cents = int(prices.get("monthly", {}).get("unit_amount", 0))
        annual_cents = int(prices.get("annual", {}).get("unit_amount", 0))
        monthly_pm = round(monthly_cents / 100)
        annual_pm = round(annual_cents / 12 / 100)
        save_pct = (
            round((monthly_cents - annual_cents / 12) / monthly_cents * 100)
            if monthly_cents
            else 0
        )
        return {
            "tier": prod.get("tier", key),
            "name": prod.get("name", key.title()),
            "trial_days": int(prod.get("trial_days", 0)),
            "monthly_pm": monthly_pm,
            "annual_pm": annual_pm,
            "annual_total": round(annual_cents / 100),
            "save_pct": save_pct,
            "monthly_cents": monthly_cents,
            "annual_cents": annual_cents,
        }

    offer = (catalog.get("offers") or {}).get("founding_pro")
    founding = None
    if offer:
        regular = next(
            product["prices"][offer["interval"]]["unit_amount"]
            for product in products.values()
            if product["tier"] == offer["tier"]
        )
        offer_cents = int(offer["unit_amount"])
        founding = {
            "key": "founding_pro",
            "name": offer["name"],
            "tier": offer["tier"],
            "interval": offer["interval"],
            "annual_cents": offer_cents,
            "annual_pm": round(offer_cents / 12 / 100),
            "annual_total": round(offer_cents / 100),
            "regular_annual_pm": round(int(regular) / 12 / 100),
            "discount_pct": round(
                (int(regular) - offer_cents) / int(regular) * 100
            ),
            "discount_amount": round((int(regular) - offer_cents) / 100),
            "cap": int(offer["max_redemptions"]),
            "public_count_threshold": int(
                offer.get("public_count_threshold", 0)
            ),
        }

    return {
        "currency": catalog.get("currency", "usd"),
        "insider": tier_vm("insider"),
        "pro": tier_vm("pro"),
        "founding": founding,
        "terminal_indicators": catalog.get("terminal_indicators", {}),
    }


def build(site=None) -> None:
    """Render all public Jinja pages from committed inputs."""
    site = site or config.site_dir()
    site.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(config.ROOT / "templates"),
        autoescape=True,
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    vm = plans_view_model()

    plans = env.get_template("plans.html.j2").render(
        generated_utc=generated,
        currency=vm["currency"],
        insider=vm["insider"],
        pro=vm["pro"],
        founding=vm["founding"],
        terminal_indicators=vm["terminal_indicators"],
    )
    write_page(site / "plans.html", plans)
    write_page(
        site / "support.html",
        env.get_template("support.html.j2").render(generated_utc=generated),
    )
    write_page(
        site / "unsubscribe.html",
        env.get_template("unsubscribe.html.j2").render(
            generated_utc=generated
        ),
    )
    log.info(
        "wrote public pages (Insider $%s/$%s · Pro $%s/$%s · Founding $%s/year)",
        vm["insider"]["monthly_pm"],
        vm["insider"]["annual_pm"],
        vm["pro"]["monthly_pm"],
        vm["pro"]["annual_pm"],
        vm["founding"]["annual_total"] if vm["founding"] else "off",
    )


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
