"""Build the Mastermind snapshot page -> site/mastermind.html.

ONE static page that renders a daily snapshot of the LOCAL Mastermind AI paper-trading
desk. The data (site/mastermind/mastermind_snapshot.json) is NOT produced here — it is
pushed out-of-band, twice a day, by the local Mastermind server (it commits the JSON to
this repo's site/mastermind/ via its vendor/macro symlink, since the cloud build can't
reach localhost). templates/mastermind.js fetches + renders that JSON client-side,
bilingually, degrading to a "snapshot pending" state when it is absent.

This builder therefore does NO data work and is order-independent. Returns 0 on ANY error
so it can never break the rest of the site build.

Usage: python -m scripts.build_mastermind
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_mastermind")

# Shared nav/theme assets + the page's own renderer. The snapshot JSON is produced by
# the local Mastermind server, not here.
ASSETS = ("theme.css", "theme.js", "mastermind.js")


def main() -> int:
    try:
        site = Path(config.load()["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)

        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)

        as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        html = env.get_template("mastermind.html.j2").render(as_of=as_of)
        (site / "mastermind.html").write_text(html)

        for a in ASSETS:
            src = Path(config.ROOT) / "templates" / a
            if src.exists():
                (site / a).write_text(src.read_text())
        log.info("wrote %s/mastermind.html (%d KB)", site, len(html) // 1024)
    except Exception as e:  # noqa: BLE001 — additive, must never break the site build
        log.error("Mastermind page build failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
