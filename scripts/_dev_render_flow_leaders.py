"""DEV-ONLY fast re-render of flow_leaders.html from the last-built leaders.json.

Mirrors the render step inside scripts/build_flow_leaders.build() (same minimal
Jinja env) but reads the already-built site/flowleaders/leaders.json instead of
recomputing the payload from the data stores. Lets us iterate on the template /
CSS in well under a second without running the full builder.

Usage:  python -m scripts._dev_render_flow_leaders
Writes: site/flow_leaders.html   (the real output path — nightly re-renders it)
NOT on the daily/commit path; build_flow_leaders remains the source of truth.
"""
import json
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    payload_path = site / "flowleaders" / "leaders.json"
    if not payload_path.exists():
        print(f"no payload at {payload_path} — run build_flow_leaders first", file=sys.stderr)
        return 1
    payload = json.loads(payload_path.read_text())

    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    tpl = env.get_template("flow_leaders.html.j2")
    out = site / "flow_leaders.html"
    write_page(out, tpl.render(flow_leaders=payload))
    print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB) from {payload_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
