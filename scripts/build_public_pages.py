"""Render the data-free public pages without invoking the market-data builders.

This is the fast path for help, pricing, support, and unsubscribe changes.  The full
``scripts.build_site`` entry point reads parquet stores and rebuilds thousands of
market pages; these three pages need only committed configuration and templates.

Usage: python -m scripts.build_public_pages
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from lib import config  # noqa: E402
from lib.chat_allowance import chat_allowance_view_model  # noqa: E402
from lib.glossary import glossary_view_model  # noqa: E402
from lib.help_directory import help_directory_view_model  # noqa: E402
from lib.pages import write_page  # noqa: E402

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
        "essential": tier_vm("essential"),
        "pro": tier_vm("pro"),
        "founding": founding,
        "terminal_indicators": catalog.get("terminal_indicators", {}),
        # See the same key in scripts/build_site._plans_view_model — both entry points
        # render the SAME template, so both must hand it the same contract (MNZ-R13).
        "chat_quotas": chat_allowance_view_model(),
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

    # Help itself is fail-closed, but it is additive: source drift must not keep
    # pricing, support, or unsubscribe from rendering. Defer its failure until
    # those independent pages land, exactly as the plans path does below.
    help_error: Exception | None = None
    help_vm: dict | None = None
    try:
        help_vm = help_directory_view_model(config.ROOT)
        write_page(
            site / "help.html",
            env.get_template("help.html.j2").render(
                generated_utc=generated,
                **help_vm,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — re-raised after the other pages land
        help_error = exc
        print(
            "::error title=help-source::help page NOT rebuilt — "
            f"{str(exc).splitlines()[0] if str(exc) else type(exc).__name__}",
            flush=True,
        )

    glossary_error: Exception | None = None
    glossary_vm: dict | None = None
    try:
        glossary_vm = glossary_view_model(config.ROOT)
        write_page(
            site / "glossary.html",
            env.get_template("glossary.html.j2").render(
                generated_utc=generated,
                **glossary_vm,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — re-raised after the other pages land
        glossary_error = exc
        print(
            "::error title=glossary-source::glossary page NOT rebuilt — "
            f"{str(exc).splitlines()[0] if str(exc) else type(exc).__name__}",
            flush=True,
        )

    # The plans page is the only remaining page that reads mutable product config. A malformed
    # config/brain.yml or config/plans.yml must not take support.html, unsubscribe.html and
    # the asset re-stamp down with it — scripts/ci/public_render.sh runs under `set -e`, so
    # an unguarded raise here aborts the entire publish. Defer the failure instead: render
    # everything that CAN be rendered, annotate, and exit non-zero at the end.
    plans_error: Exception | None = None
    try:
        vm = plans_view_model()
        # See the same splat in scripts/build_site.build_plans_page — one contract, one
        # place, so a new view-model key cannot reach one renderer and miss another.
        plans = env.get_template("plans.html.j2").render(generated_utc=generated, **vm)
        write_page(site / "plans.html", plans)
    except Exception as exc:  # noqa: BLE001 — re-raised after the other pages land
        plans_error = exc
        # Annotations must START the line and bypass the logger (CLAUDE.md). First line
        # only: a yaml ScannerError is multi-line and GitHub keeps just the first, which
        # would drop the file/line that says WHERE.
        print(f"::error title=plans-config::plans page NOT rebuilt, stale bytes retained — "
              f"{str(exc).splitlines()[0] if str(exc) else type(exc).__name__}", flush=True)
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
    if help_error is not None:
        raise help_error
    if glossary_error is not None:
        raise glossary_error
    if plans_error is not None:
        raise plans_error
    assert help_vm is not None
    assert glossary_vm is not None
    log.info(
        "wrote public pages (help=%s links · glossary=%s terms · Essential $%s/$%s · Pro $%s/$%s · Founding $%s/year)",
        len(help_vm["entries"]),
        glossary_vm["term_count"],
        vm["essential"]["monthly_pm"],
        vm["essential"]["annual_pm"],
        vm["pro"]["monthly_pm"],
        vm["pro"]["annual_pm"],
        vm["founding"]["annual_total"] if vm["founding"] else "off",
    )


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
