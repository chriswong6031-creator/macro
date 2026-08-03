"""DEV-ONLY fast re-render of flow_leaders.html from the last-built leaders.json.

Mirrors the render step inside scripts/build_flow_leaders.build() (same minimal
Jinja env). Since W1.6-B the template is a payload-free redirect stub, so this
is a plain sub-second re-render convenience for iterating on the stub markup.

Usage:  python -m scripts._dev_render_flow_leaders
Writes: site/flow_leaders.html   (the real output path — nightly re-renders it)
NOT on the daily/commit path; build_flow_leaders remains the source of truth.
"""
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402


def main() -> int:
    # W1.6-B: flow_leaders.html is a payload-free redirect stub — the template
    # takes no context, so this helper is now a plain re-render convenience.
    site = config.ROOT / config.load()["storage"]["site_dir"]
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    tpl = env.get_template("flow_leaders.html.j2")
    out = site / "flow_leaders.html"
    write_page(out, tpl.render())
    print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB) — redirect stub")
    return 0


if __name__ == "__main__":
    sys.exit(main())
