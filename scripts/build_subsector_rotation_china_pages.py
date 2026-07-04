"""Per-subsector DETAIL pages for the China Subsector Rotation desk.

The China twin of scripts/build_subsector_rotation_pages.py — reuses the SAME template
(templates/subsector_rotation_detail.html.j2) and helpers, but reads the China feed and
points member links at the A-share analyzer (china_lookup.html#<TICKER>). One page per
reliable 同花顺 concept at site/rotation_china/<key>.html.

    python -m scripts.build_subsector_rotation_china_pages
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import config
from lib.pages import write_page
from scripts.build_subsector_rotation_pages import QUAD, QUADX, PERF_ROWS, _fmt_pc, _lede

log = logging.getLogger("build_subsector_rotation_china_pages")


def build(site: Path | None = None) -> int:
    site = site or (config.ROOT / config.load()["storage"]["site_dir"])
    src = site / "marketdata" / "subsector_rotation_china.json"
    if not src.exists():
        log.warning("subsector_rotation_china.json missing — skipped detail pages")
        return 0
    data = json.loads(src.read_text())
    subs = data.get("subsectors") or []
    n_total = len(subs)

    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals["fmt_pc"] = _fmt_pc
    tmpl = env.get_template("subsector_rotation_detail.html.j2")

    out_dir = site / "rotation_china"
    out_dir.mkdir(parents=True, exist_ok=True)

    n = 0
    for sub in subs:
        q = sub.get("quadrant") or "lagging"
        qd, qx = QUAD.get(q, QUAD["lagging"]), QUADX.get(q, QUADX["lagging"])
        members = sorted((sub.get("members") or []),
                         key=lambda m: (m.get("1M") if m.get("1M") is not None else -1e9), reverse=True)[:30]
        lede_en, lede_zh = _lede(sub)
        html = tmpl.render(
            sub=sub, n_total=n_total, members=members, perf_rows=PERF_ROWS,
            q_cls=qd[2], q_en=qd[0], q_zh=qd[1], qx_en=qx[0], qx_zh=qx[1],
            lede_en=lede_en, lede_zh=lede_zh,
            # China parameterization of the shared template
            stock_base="china_lookup.html#", back_href="subsector_rotation_china.html",
            back_en="China Subsector Rotation map", back_zh="中国子行业轮动图",
        )
        write_page(out_dir / f"{sub['key']}.html", html)
        n += 1
    log.info("wrote %d China subsector detail pages -> %s", n, out_dir)
    return n


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
