"""Build the International comparative dashboard -> site/intl.html (macro) +
site/intl_stocks.html (stocks) + site/intl_stock.html (per-stock search shell).

Standalone like scripts/build_canada.py — shares only the parquet store. Recomputes
the per-country regimes (live == backtest), assembles the cross-country comparison,
the pooled standouts and the flagged sector-rotation board, and renders the dark,
bilingual templates/intl.html.j2 (rendered twice via a `mode` flag). Returns 0 on
ANY engine error so it can never break the macro / vector site builds.

Usage: python -m scripts.build_intl   (run after build_site, before build_vector)
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_intl")

ASSETS = ("theme.css", "theme.js", "mtf.js", "chart_i18n.js", "charts.js",
          "tablesort.js", "stockdata.js", "stockview.js")

# quad colour keys (match the .q-Qn CSS) — uniform with the other verticals
QUAD_MEANING = {
    "Goldilocks": ("growth ↑ inflation ↓ — risk-on, duration & quality favoured",
                   "增长 ↑ 通胀 ↓ — 偏好风险、久期与质量"),
    "Reflation": ("growth ↑ inflation ↑ — cyclicals, value & commodities favoured",
                  "增长 ↑ 通胀 ↑ — 偏好周期、价值与大宗"),
    "Stagflation": ("growth ↓ inflation ↑ — defensives, energy & real assets",
                    "增长 ↓ 通胀 ↑ — 偏好防御、能源与实物资产"),
    "Growth-scare": ("growth ↓ inflation ↓ — bonds & defensives over equities",
                     "增长 ↓ 通胀 ↓ — 债券与防御优于股票"),
}


def main() -> int:
    try:
        from engine.intl_run import run
        latest = run()
    except Exception as e:  # noqa: BLE001 — never break the site build
        log.error("intl engine failed (%s); skipping intl page", e)
        return 0

    # ---- cross-market performance / rotation / rates desks (display-only) ------
    try:                                                # inline SVG sparkline renderer
        from scripts.build_intl_library import _spark_svg
    except Exception:  # noqa: BLE001 — sparklines are decorative; never break the build
        def _spark_svg(*_a, **_k):
            return ""
    perf, rates = None, None
    try:
        from engine import intl_performance
        perf = intl_performance.performance_panel(records=latest["records"])
        for b in (perf.get("leaderboard") or []):
            h = next((b["returns"][k] for k in ("12m", "6m", "3m", "ytd", "1m")
                      if k in b["returns"]), None)
            col = ("var(--up)" if (h and h["usd"] >= 0) else "var(--down)")
            b["spark_svg"] = _spark_svg(b.get("spark") or [], color=col, w=200, h=40)
    except Exception as e:  # noqa: BLE001 — additive, never break the build
        log.error("intl performance panel failed (%s)", e)
    try:
        from engine import intl_rates
        rates = intl_rates.rates_desk(latest["records"])
        for r in (rates.get("rows") or []):
            # neutral accent — the spark plots the 10y *yield* path (not a price
            # direction), so up/down semantics would misread (a rising yield line
            # tinted "down")
            r["spark_svg"] = _spark_svg(r.get("spark") or [], color="var(--link)", w=130, h=34)
        an = rates.get("anchor") or {}
        an["spark_svg"] = _spark_svg(an.get("spark") or [], color="var(--link)", w=200, h=40)
        liq = rates.get("liquidity")
        if liq:
            liq["spark_svg"] = _spark_svg(liq.get("spark") or [],
                                          color=("var(--down)" if liq.get("draining") else "var(--up)"),
                                          w=200, h=40)
    except Exception as e:  # noqa: BLE001
        log.error("intl rates desk failed (%s)", e)

    try:
        from engine import intl_stocks
        closes, members = intl_stocks.panel()
        alpha = None
        try:
            alpha = intl_stocks.compute_intl_alpha(closes, members)
        except Exception as e:  # noqa: BLE001 — additive
            log.error("intl alpha failed (%s)", e)
        board = []
        try:
            board = intl_stocks.sector_board()
        except Exception as e:  # noqa: BLE001
            log.error("intl sector board failed (%s)", e)

        # per-stock library + pooled standouts shortlist
        setups = None
        try:
            from scripts import build_intl_library
            setups = build_intl_library.main(alpha=alpha)
        except Exception as e:  # noqa: BLE001 — additive
            log.error("intl stock library failed (%s)", e)

        for r in latest["records"]:
            r["quad_meaning"] = QUAD_MEANING.get(r.get("quad_name"))

        vm = {
            "latest": latest,
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "records": latest["records"],
            "summary": latest["summary"],
            "rankings": latest.get("rankings", {}),
            "heatmap": latest.get("heatmap", []),
            "periphery": latest.get("periphery"),
            "sector_board": board,
            "setups": setups,
            "perf": perf,
            "rates": rates,
        }

        site = Path(config.load()["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)
        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)

        tmpl = env.get_template("intl.html.j2")
        write_page(site / "intl.html", tmpl.render(**vm, mode="macro"))
        write_page(site / "intl_stocks.html", tmpl.render(**vm, mode="stocks"))
        log.info("wrote intl.html + intl_stocks.html (%d economies, %d standouts)",
                 vm["summary"]["n"], len((setups or {}).get("buy") or []))

        # per-stock search shell
        try:
            from engine.cycles import STATE_DISPLAY
            shell = env.get_template("intl_stock.html.j2").render(
                state_display_json=json.dumps(STATE_DISPLAY, default=str), generated_utc=vm["built"])
            write_page(site / "intl_stock.html", shell)
        except Exception as e:  # noqa: BLE001 — search additive
            log.error("intl stock shell render failed (%s)", e)

        for a in ASSETS:
            src = Path(config.ROOT) / "templates" / a
            if src.exists():
                (site / a).write_text(src.read_text())

        # landing-hub card stat (presence-gated by the .html existing)
        s = vm["summary"]
        idir = config.data_dir() / "intl"
        idir.mkdir(parents=True, exist_ok=True)
        (idir / "hub.json").write_text(json.dumps({
            "date": latest.get("date", ""),
            "label": f"{s['n']} economies · {s['dominant_quad']}",
            "recession_watch": s.get("recession_watch", 0)}, indent=2))
    except Exception as e:  # noqa: BLE001
        log.error("intl page render failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
