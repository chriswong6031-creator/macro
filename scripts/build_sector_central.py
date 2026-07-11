"""Build the US Sector Central Intelligence dashboard -> site/sector_central.html.

The consolidation hub: engine.sector_central fuses the cycle map + the VALIDATED absolute-trend
drawdown gate + the macro regime posture + the (audited) momentum / heat / crowding CONTEXT into
one per-sector conviction read with a reasoning trace. This script emits the data JS
(window.SECTOR_CENTRAL), the raw JSON, runs the self-grader (append today's calls + grade matured
ones), and renders the page. It links + embeds the four sub-dashboards it sits above (Sector
Cycles overlay + Sector Heatmap scorecard embedded; Thematic Baskets + Narrative Rotation linked).

Additive — any failure logs and returns 0 so it never breaks the rest of the build.
Run: python -m scripts.build_sector_central
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_sector_central")


def _fmt_money_mn(v: float | None) -> str:
    """$ millions -> human string: 1234 -> +$1.2B, -87 -> -$87M, None -> —."""
    import math
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    sign = "+" if v >= 0 else "−"
    a = abs(v)
    if a >= 1000:
        return f"{sign}${a / 1000:.1f}B"
    return f"{sign}${a:.0f}M"


def _flows_section_html() -> str | None:
    """Server-rendered 'Where sector-ETF money is flowing' board: a multi-window
    (1D/3D/1W/2W/1M) flow heatmap across the 11 sector SPDRs, sorted by the widest
    window, with a net-of-complex row. Replaces the day-by-day grid that used to
    live on us_stocks.html. Returns None until flow history exists."""
    from collectors.sponsors import sector_flow_periods
    from engine.i18n import t
    from engine.playbook import SECTOR_NAMES
    data = sector_flow_periods()
    if not data or not data.get("rows"):
        return None
    labels = data["labels"]
    rows = data["rows"]
    net = data["net"]
    # per-window max-abs for the heat tint (the net row is excluded so one big
    # complex-wide window doesn't wash every cell out)
    maxabs = {lbl: max((abs(r["vals"].get(lbl) or 0.0) for r in rows), default=0.0)
              for lbl in labels}
    widest = labels[-1]
    rows = sorted(rows, key=lambda r: -(r["vals"].get(widest) or 0.0))

    def cell(v: float | None, lbl: str) -> str:
        if v is None:
            return "<td class='scf-c muted'>—</td>"
        cls = "pos" if v >= 0 else "neg"
        m = maxabs.get(lbl) or 0.0
        inten = min(1.0, abs(v) / m) if m else 0.0
        var = "--up" if v >= 0 else "--down"
        bg = (f"background:color-mix(in srgb, var({var}) "
              f"{6 + inten * 46:.0f}%, transparent)") if inten > 0.02 else ""
        return f"<td class='scf-c {cls}' style='{bg}'>{_fmt_money_mn(v)}</td>"

    head = "<th class='scf-s'>" + str(t("sector", "板块")) + "</th>" + "".join(
        f"<th class='scf-c'>{lbl}</th>" for lbl in labels)
    body = []
    for r in rows:
        name = SECTOR_NAMES.get(r["ticker"], r["ticker"])
        label = (f"<b>{r['ticker']}</b> <span class='muted'>"
                 f"{t(name, name)}</span>")
        body.append("<tr><td class='scf-s'>" + label + "</td>"
                    + "".join(cell(r["vals"].get(lbl), lbl) for lbl in labels)
                    + "</tr>")
    net_cells = "".join(cell(net.get(lbl), lbl) for lbl in labels)
    body.append("<tr class='scf-net'><td class='scf-s'><b>"
                + str(t("Net · 11 sector ETFs", "净额 · 11 个板块 ETF"))
                + "</b></td>" + net_cells + "</tr>")
    note = t(
        f"As of {data['asof']} · net creation/redemption flow (ΔShares × NAV) "
        f"summed over each window · positive = money in. Windows cap at the "
        f"{data['depth']} trading days collected so far (history builds from "
        f"June 2026), so the wider windows can coincide until more accrues. "
        f"Display-only.",
        f"截至 {data['asof']} · 各时间窗内份额申购／赎回净额（份额变动 × 资产净值）"
        f"求和 · 正值 = 资金流入。各窗口取目前已采集的 {data['depth']} 个交易日"
        f"（历史自 2026 年 6 月起累积），故在数据充足前较宽的窗口可能重合。仅作展示。")
    return (
        "<div class='scc-section-h' id='sc-flows'>"
        "<h2><span class='l-en'>Where sector-ETF money is flowing</span>"
        "<span class='l-zh'>板块 ETF 资金流向何处</span></h2>"
        "<span class='scc-section-sub'><span class='l-en'>Multi-day "
        "creation/redemption flow across the 11 sector SPDRs — read the rotation, "
        "not the daily noise</span><span class='l-zh'>覆盖 11 个板块 SPDR 的多日"
        "申购／赎回资金流 — 看轮动趋势，而非单日噪声</span></span></div>"
        "<div class='scf-wrap'><table class='scf'><thead><tr>" + head
        + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
        "<p class='muted sm' style='margin:8px 2px 0'>" + str(note) + "</p></div>")


def main() -> int:
    root = config.ROOT
    site = root / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)

    try:
        from engine import sector_central as cc
        data = cc.compute()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.exception("sector_central engine failed: %s", e)
        return 0
    if not data or not data.get("sectors"):
        log.warning("sector_central: no data — skipping")
        return 0

    # self-grader: append today's calls (PIT) + grade matured ones; attach the scorecard
    try:
        from engine import sector_central_grader as cg
        n_logged = cg.append_central_log(data)
        data["grader"] = cg.grade()
    except Exception as e:  # noqa: BLE001
        n_logged = 0
        log.warning("sector_central: grader failed: %s", e)
        data["grader"] = {"available": False, "note": "grader error"}

    payload = "window.SECTOR_CENTRAL=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n"
    (site / "sector_central_data.js").write_text(payload, encoding="utf-8")
    fdir = site / "sectordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "sector_central.json").write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=False)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    try:
        flows_html = _flows_section_html()
    except Exception as e:  # noqa: BLE001 — additive embed, never fatal
        log.warning("sector_central: flow board failed (%s)", e)
        flows_html = None
    try:
        html = env.get_template("sector_central.html.j2").render(flows_html=flows_html)
        write_page(site / "sector_central.html", html, encoding="utf-8")
    except Exception as e:  # noqa: BLE001 — a template error must NOT abort the daily engine job
        # The CI step that runs this is a bare `run:` (its claim "the builder returns 0 on any
        # failure" is only true if main() never raises), so an unguarded render here aborts the
        # whole engine job → no commit → stale site (this exact `t`-undefined crash, #624→#643).
        # Degrade: keep the last-good committed sector_central.html (the fresh data JS/JSON written
        # above still drive the page's runtime content) and return 0 so the rest of the build ships.
        log.exception("sector_central: page render failed (%s) — keeping last-good HTML", e)
        return 0

    # the page embeds the cycle-map overlay (window.SECTOR_CYCLES) + the heatmap scorecard →
    # ensure their shared assets are present. The cycles DATA (sector_cycles_data.js) is written
    # by build_sector_cycles, which must run before this; we copy the page assets and warn if
    # required runtime files are absent.
    import shutil
    for asset in ("sector_cycles.css", "sector_cycles.js"):
        src = root / "templates" / asset
        if src.exists():
            shutil.copy2(src, site / asset)
    for need in ("sector_cycles_data.js", "sector_cycles_narr_data.js",
                 "sector_cycles_dna_data.js", "mm_charts.js", "cycle.css"):
        if not (site / need).exists():
            log.warning("sector_central: %s missing — embedded cycle chart needs "
                        "build_sector_cycles (+ build_cycle) to run first", need)
    if not (site / "heatmap.js").exists():
        log.warning("sector_central: heatmap.js missing — embedded heatmap scorecard needs "
                    "build_site to run first")

    log.info("built site/sector_central.html (%d sectors, %d baskets, %d calls logged, grader=%s)",
             len(data["sectors"]), len(data.get("baskets", [])), n_logged,
             (data.get("grader") or {}).get("available"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
