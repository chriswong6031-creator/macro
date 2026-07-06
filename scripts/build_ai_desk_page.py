"""Build the AI Desk page -> site/ai_desk.html.

A static page that surfaces the accountable analyst desk written by engine/ai_desk.py
(site/ai_desk.json): the falsifiable conditional leans, each with its dissent +
falsifier + check-by date, the desk's own track record (from the Phase-C scorer), and
what the analyst panel argued. templates/ai_desk.js fetches the JSON and renders it
client-side, bilingually — so this builder does NO data work and is order-independent.
Returns 0 on ANY error so it can never break the rest of the site build.

Usage: python -m scripts.build_ai_desk_page   (run anytime; e.g. after engine.ai_desk)
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, site_assets  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_ai_desk_page")

# theme (vars + l-en/l-zh + nav) + theme.js (theme/lang/search wiring) + the renderer.
# The ai_desk.json is produced by engine.ai_desk and fetched in the browser, not here.
ASSETS = ("theme.css", "theme.js", "ai_desk.js")


def main() -> int:
    try:
        site = Path(config.load()["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)

        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)

        as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        html = env.get_template("ai_desk.html.j2").render(as_of=as_of)
        write_page(site / "ai_desk.html", html)

        for a in ASSETS:
            srcf = Path(config.ROOT) / "templates" / a
            if srcf.exists():
                site_assets.copy_asset(a, srcf, site)
        log.info("wrote %s/ai_desk.html (%d KB)", site, len(html) // 1024)
    except Exception as e:  # noqa: BLE001 — additive, must never break the site build
        log.error("AI desk page build failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
