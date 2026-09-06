"""scripts/build_sanctions_map.py — renders templates/sanctions_map.html.j2
from engine.sanctions_map.build() and writes site/sanctions_map.html plus
data/sanctions_map/latest.json. Display-only, leaf builder (same posture as
scripts/build_spr.py)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402
from engine import sanctions_map  # noqa: E402
from engine.i18n import t, td, tr  # noqa: E402

LATEST_JSON = Path("data/sanctions_map/latest.json")
WORLDMAP_TEMPLATE = Path("templates/_worldmap_base.html.j2")


def _all_iso3(path: Path = WORLDMAP_TEMPLATE) -> set:
    """Every ISO3 the base map SVG draws a path for -- lets unresolved
    OFAC coverage be painted unknown across the whole known country
    set, not just the countries we managed to resolve."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return set()
    return set(re.findall(r'data-iso3="([A-Z]{3})"', text))


def build() -> dict:
    vm = sanctions_map.build()
    LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    LATEST_JSON.write_text(json.dumps(vm, indent=2, default=str), encoding="utf-8")

    rungs = sanctions_map.rungs_for(vm, _all_iso3())

    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td, t=t)
    html = env.get_template("sanctions_map.html.j2").render(vm=vm, rungs=rungs)

    site = config.ROOT / config.load()["storage"]["site_dir"]
    write_page(site / "sanctions_map.html", html)
    return vm


if __name__ == "__main__":
    build()
