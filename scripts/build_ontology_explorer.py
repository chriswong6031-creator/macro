"""Build the F04-X1 WTI Live Trace public shell -> site/ontology.html.

Feature-owned builder, deliberately standalone. It does NOT extend
`scripts/build_site.py`: that file is owned by an open sibling carrier, and a
new page is not a reason to contend for a shared hunk when a small script can
own itself.

The one rule this builder must never break is that it reads NOTHING from
`data/transmission/`. The page it writes is served publicly and cached, so a
current value rendered into it at build time would be a premium reading
published to a public CDN. Current values reach the researcher only through the
authenticated API, at request time, in the browser.

Usage: python -m scripts.build_ontology_explorer
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_ontology_explorer")

TEMPLATE = "ontology.html.j2"
PAGE = "ontology.html"
#: non-.j2 assets that ship byte-identically to site/ (paired plain-copy law)
PAIRED_ASSETS = ("ontology.css", "ontology.js")


def main() -> int:
    root = config.ROOT
    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=True)
    html = env.get_template(TEMPLATE).render(nav_prefix="")

    site = root / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)
    write_page(site / PAGE, html)

    for name in PAIRED_ASSETS:
        source, target = root / "templates" / name, site / name
        if not source.exists():
            log.error("paired asset missing: templates/%s", name)
            return 0
        if not target.exists() or target.read_bytes() != source.read_bytes():
            target.write_bytes(source.read_bytes())
            log.info("synced %s", name)

    log.info("wrote %s/%s (%d KB)", site, PAGE, len(html) // 1024)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
