"""Build the consolidated AI Daily Brief page -> site/aibrief.html.

ONE static page that surfaces the three EXISTING AI briefs written by
engine/master_brain.py (site/master_brief.json, site/china_brief.json,
site/btc_brief.json — one shared schema). Three toggle tabs (Macro / China & HK /
Bitcoin) flip three .ai-brief[data-brief-src] panels that templates/aibrief.js
fetches + renders client-side, bilingually. This builder therefore does NO data
work and is order-independent — the JSONs are fetched in the browser, not at build
time. Returns 0 on ANY error so it can never break the rest of the site build.

Usage: python -m scripts.build_aibrief   (run anytime; e.g. after master_brain)
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
log = logging.getLogger("build_aibrief")

# Only the assets the shared nav + the briefs need: theme (vars + l-en/l-zh toggle
# CSS + nav styling), theme.js (wires theme/lang/search), aibrief.js (renders the
# three panels). The lens JSONs are produced by engine.master_brain, not here.
ASSETS = ("theme.css", "theme.js", "aibrief.js")


def main() -> int:
    try:
        site = Path(config.load()["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)

        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)

        as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        html = env.get_template("aibrief.html.j2").render(as_of=as_of)
        (site / "aibrief.html").write_text(html)

        for a in ASSETS:
            src = Path(config.ROOT) / "templates" / a
            if src.exists():
                (site / a).write_text(src.read_text())
        log.info("wrote %s/aibrief.html (%d KB)", site, len(html) // 1024)
    except Exception as e:  # noqa: BLE001 — additive, must never break the site build
        log.error("AI brief page build failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
