"""Build the standalone China Alternative-Data desk page + machine-readable emits.

Runs the per-ticker convergence kernel + the honest signal-lab scorecard, renders
site/china_altdata.html, and emits site/chinaaltdata/{by_ticker,mastermind,feed}.json
(the mastermind.json is the context lens the intel bus + future China Mastermind read).
Callable standalone + importable (build()). CONTEXT-ONLY · never raises.
See research/CHINA_INTEL_POWERHOUSE.md §2.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import config

log = logging.getLogger(__name__)

ASSETS = ("theme.css", "theme.js")


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def build() -> dict | None:
    from engine import china_altdata as ad
    from engine import china_signal_lab as lab

    bt = ad.by_ticker()
    mm = ad.mastermind(bt)
    scorecard = lab.build_china_scorecard()

    site = _site_dir()
    site.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    html = env.get_template("china_altdata.html.j2").render(ad=bt, lab=scorecard, mm=mm)
    (site / "china_altdata.html").write_text(html)
    for a in ASSETS:
        src = config.ROOT / "templates" / a
        if src.exists() and not (site / a).exists():
            (site / a).write_text(src.read_text())
    log.info("wrote %s/china_altdata.html (%d KB)", site, len(html) // 1024)

    out = site / "chinaaltdata"
    out.mkdir(parents=True, exist_ok=True)
    (out / "by_ticker.json").write_text(
        json.dumps(bt or {}, ensure_ascii=False, separators=(",", ":"), default=str))
    (out / "mastermind.json").write_text(
        json.dumps(mm, ensure_ascii=False, separators=(",", ":"), default=str))
    (out / "feed.json").write_text(
        json.dumps(scorecard, ensure_ascii=False, separators=(",", ":"), default=str))
    log.info("wrote %s/chinaaltdata/{by_ticker,mastermind,feed}.json", site)
    return bt


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
