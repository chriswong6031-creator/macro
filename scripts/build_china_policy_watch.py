"""Build the standalone China Central Bank & Government Policy Watch page.

Assembles the PBoC stance/corridor + NBS prints + official policy tape + curated intel,
renders site/china_policy_watch.html, and writes data/china_policy/latest.json (the
machine-readable hub contract the intel bus + future China Mastermind read). Callable
standalone (`python -m scripts.build_china_policy_watch`) and importable (build()).
CONTEXT-ONLY · never raises into the site build. See research/CHINA_INTEL_POWERHOUSE.md §3.
"""
from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import config
from lib.pages import write_page

log = logging.getLogger(__name__)

ASSETS = ("theme.css", "theme.js")


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def build() -> dict | None:
    from engine import china_policy_watch as pw

    vm = pw.snapshot()
    pw.write_latest(vm)        # data/china_policy/latest.json (for the intel bus)

    site = _site_dir()
    site.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    html = env.get_template("china_policy_watch.html.j2").render(pw=vm)
    write_page(site / "china_policy_watch.html", html)
    for a in ASSETS:
        src = config.ROOT / "templates" / a
        if src.exists() and not (site / a).exists():
            (site / a).write_text(src.read_text())
    log.info("wrote %s/china_policy_watch.html (%d KB)", site, len(html) // 1024)
    return vm


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
