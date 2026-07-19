"""scripts.build_movers_page — render the free daily movers page + og:image card.

Reads site/marketdata/sp500_heatmap.json and site/marketdata/themes_heatmap.json
via engine.marketing.movers_source.
Writes site/movers.html and site/og/movers.png.

Usage:
    python -m scripts.build_movers_page
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# CTA URL
# ─────────────────────────────────────────────────────────────────────────────

def _cta_url() -> str:
    # Tagged trial CTA via the D07 Funnel link builder (#3052); untagged fallback
    # keeps the page fail-soft if links.py is ever absent.
    try:
        from engine.marketing.links import canonical_link

        return canonical_link(
            "free_tools", "movers", "cta",
            base_url="https://app.mastermind-x.com/", utm_source="site",
        )
    except Exception:
        return "https://app.mastermind-x.com/"


# ─────────────────────────────────────────────────────────────────────────────
# build_context — pure function, testable
# ─────────────────────────────────────────────────────────────────────────────

def build_context(data: dict | None) -> dict:
    """Build the Jinja context dict from the movers source data.

    Missing/empty data returns an empty-state context (page still renders).
    """
    tf = "1D"

    if data is None:
        return {
            "asof": None,
            "tf": tf,
            "cta_url": _cta_url(),
            "gainers": [],
            "losers": [],
            "themes": [],
        }

    from engine.marketing.movers_source import top_movers, theme_lists  # noqa: PLC0415

    asof = data.get("asof")

    movers = top_movers(data, tf=tf, n=8)
    gainers_raw = movers.get("gainers") or []
    losers_raw = movers.get("losers") or []

    # Map to template shape: {ticker, name, pct, sector}
    gainers = [
        {"ticker": m.get("ticker", ""), "name": m.get("name", ""),
         "pct": m.get("pct", 0.0), "sector": m.get("sector", "")}
        for m in gainers_raw
    ]
    losers = [
        {"ticker": m.get("ticker", ""), "name": m.get("name", ""),
         "pct": m.get("pct", 0.0), "sector": m.get("sector", "")}
        for m in losers_raw
    ]

    themes_raw = theme_lists(data, tf=tf, n=8)
    # Map theme members to {ticker, pct}; theme display string in theme key
    themes = []
    for th in themes_raw[:6]:
        members = [{"ticker": m.get("ticker", ""), "pct": m.get("pct", 0.0)}
                   for m in (th.get("members") or [])]
        themes.append({
            "theme": th.get("theme", ""),
            "direction": th.get("direction", "up"),
            "agg_pct": th.get("agg_pct", 0.0),
            "members": members,
        })

    return {
        "asof": asof,
        "tf": tf,
        "cta_url": _cta_url(),
        "gainers": gainers,
        "losers": losers,
        "themes": themes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# render_html — pure Jinja render
# ─────────────────────────────────────────────────────────────────────────────

def render_html(root: Path, ctx: dict) -> str:
    """Render movers.html.j2 with the given context. Pure."""
    from jinja2 import Environment, FileSystemLoader
    from engine import i18n  # noqa: PLC0415

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=True,
    )
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    tpl = env.get_template("movers.html.j2")
    return tpl.render(**ctx)


# ─────────────────────────────────────────────────────────────────────────────
# render — I/O entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def render(root: Path) -> None:
    """Load movers data, build context, write page and share card."""
    t0 = time.perf_counter()

    # Load movers data (fail-soft)
    from engine.marketing.movers_source import load_movers  # noqa: PLC0415
    data: dict | None = None
    try:
        data = load_movers(root)
    except Exception:  # noqa: BLE001
        pass

    ctx = build_context(data)

    # Render HTML
    html = render_html(root, ctx)

    from lib.pages import write_page  # noqa: PLC0415
    write_page(root / "site" / "movers.html", html)

    # Share card (only when we have movers data)
    gainers = ctx.get("gainers") or []
    losers = ctx.get("losers") or []
    asof = ctx.get("asof")

    if (gainers or losers) and asof:
        try:
            from engine.marketing.share_cards import render_movers_card, save_card  # noqa: PLC0415
            # Top 5 for the card
            top5_gainers = gainers[:5]
            top5_losers = losers[:5]
            img = render_movers_card(
                asof=asof,
                gainers=top5_gainers,
                losers=top5_losers,
            )
            card_out = root / "site" / "og" / "movers.png"
            save_card(img, card_out)
        except Exception:  # noqa: BLE001
            pass  # card failure is non-fatal; page was already written

    elapsed = time.perf_counter() - t0
    print(f"[movers_page] page+card in {elapsed:.1f}s (gainers={len(gainers)}, losers={len(losers)})")


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    try:
        render(_ROOT)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=movers_page::{exc}")
        sys.exit(0)


if __name__ == "__main__":
    main()
