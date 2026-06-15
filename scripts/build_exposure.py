"""Build the Factor-Exposure Radar page -> site/exposure.html.

Standalone like build_crossasset.py. Reads engine/factor_exposure (per-ticker
causal multi-factor betas over the library universe) and renders, for each
observable factor, the names most loaded on it — the exposure analogue of the
factor-RANK leaderboards on factors.html — plus a few example baskets decomposed
to expose the hidden one-way bet. EXPOSURE, not a forecast (see
reports/factor-exposure-sanity.md). UI only — never recomputes validation.

Usage: python -m scripts.build_exposure
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import factor_exposure as fe  # noqa: E402
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_exposure")

# Illustrative baskets to demonstrate the hidden one-way bet (equal-weight). Names
# absent from the universe are silently skipped by book_exposure.
BASKETS = [
    # all five are really one crypto bet — the textbook hidden one-way bet
    {"name": "Crypto-miner basket", "name_zh": "加密矿工组合",
     "tickers": ["MARA", "RIOT", "CLSK", "COIN", "MSTR"]},
    # the honest twist: a megacap "AI basket" is, beyond market beta, NOT a
    # concentrated semis bet — it reads as market + a mild large-cap tilt
    {"name": "Popular AI megacaps", "name_zh": "热门 AI 大盘股",
     "tickers": ["NVDA", "MSFT", "GOOGL", "META", "AMZN", "AVGO", "AMD"]},
]


def main() -> int:
    fac = fe.factor_returns()
    if fac.empty or "market" not in fac.columns:
        log.warning("factor proxies unavailable — skipping exposure page")
        return 0
    cfg = fe._cfg()
    from scripts.build_stock_library import universe

    expo: dict[str, dict] = {}
    names: dict[str, str] = {}
    for t, c, _h, nm, _sec in universe():
        e = fe.exposure(c.pct_change(fill_method=None), fac, cfg)
        if e:
            expo[t] = e
            names[t] = nm or t
    if not expo:
        log.warning("no names modelled — skipping exposure page")
        return 0
    log.info("modelled %d names on %d factors", len(expo), len(fac.columns))

    rad = fe.radar(expo, top=12, sig_t=float(cfg["sig_t"]))
    for k in rad:
        for r in rad[k]:
            r["name"] = names.get(r["ticker"], r["ticker"])

    factor_keys = [k for k in fe.FACTORS if k != "market"]
    factor_labels = {k: (fe.FACTORS[k][4], fe.FACTORS[k][5]) for k in fe.FACTORS}

    books = []
    for b in BASKETS:
        agg = fe.book_exposure({t: 1.0 for t in b["tickers"]}, expo)
        if agg:
            agg["label"] = (factor_labels.get(agg["dominant"], ("", ""))[0]
                            if agg["dominant"] else None)
            agg["label_zh"] = (factor_labels.get(agg["dominant"], ("", ""))[1]
                               if agg["dominant"] else None)
            books.append({"meta": b, "agg": agg,
                          "held": [t for t in b["tickers"] if t in expo]})

    asof = max((e["asof"] for e in expo.values()), default=None)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    from engine.i18n import td, tr
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    html = env.get_template("exposure.html.j2").render(
        as_of=asof, built=built, radar=rad, factor_keys=factor_keys,
        factor_labels=factor_labels, books=books, n_modelled=len(expo),
        n_factors=len(fac.columns))
    site = config.ROOT / config.load()["storage"]["site_dir"]
    (site / "exposure.html").write_text(html)
    log.info("wrote %s/exposure.html (%d KB)", site, len(html) // 1024)

    outdir = config.data_dir() / "exposure"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "latest.json").write_text(json.dumps(
        {"date": asof, "n": len(expo),
         "radar": {k: [{"t": r["ticker"], "b": r["beta"]} for r in rad[k][:6]] for k in rad}},
        indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
