"""Build the China Sector Intelligence page -> site/sector_central_china.html.

The merged China hub (2026-08 consolidation; masterplan
research/CHINA_SECTOR_INTELLIGENCE_CONSOLIDATION_MASTERPLAN_BY_FABLE.md): the gated
conviction board + cycle map (engine.china_sector_central, window.SECTOR_CENTRAL), the
theme-context verdict hero (read from theme_context_cn.json, written by build_baskets_china),
the whole-market rotation app + events rail (shared subsector_rotation.js via SR_CFG), and
the basket explorer (client-rendered from chinabasketdata/baskets.json). This script emits
the data JS, the raw JSON, runs the self-grader, and renders the merged page.
baskets_china.html and subsector_rotation_china.html are redirect stubs into this page.

Additive — any failure logs and returns 0 so it never breaks the rest of the China build.
Run: python -m scripts.build_china_sector_central
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
log = logging.getLogger("build_china_sector_central")


def main() -> int:
    root = config.ROOT
    site = root / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)

    try:
        from engine import china_sector_central as cc
        data = cc.compute()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.exception("china_sector_central engine failed: %s", e)
        return 0
    if not data or not data.get("sectors"):
        log.warning("china_sector_central: no data — skipping")
        return 0

    # self-grader: append today's calls (PIT) + grade matured ones; attach the scorecard
    try:
        from engine import china_sector_central_grader as cg
        n_logged = cg.append_central_log(data)
        data["grader"] = cg.grade()
    except Exception as e:  # noqa: BLE001
        n_logged = 0
        log.warning("china_sector_central: grader failed: %s", e)
        data["grader"] = {"available": False, "note": "grader error"}

    # Validated sleeve-size chip (W6-CN Fix 1) — thread risk_radar_intl gross_factor into the
    # sector central JSON header. Display chip only; regime sizes sleeves, never vetoes names.
    try:
        from engine.risk_radar_intl import cn_sleeve_chip
        data["sleeve_chip"] = cn_sleeve_chip()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china_sector_central: sleeve chip failed (%s)", e)

    payload = "window.SECTOR_CENTRAL=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n"
    (site / "sector_central_china_data.js").write_text(payload, encoding="utf-8")
    fdir = site / "chinasectordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "sector_central.json").write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    # autoescape=True since the China SI consolidation: the merged template carries the
    # baskets_china-descended organs (theme-context hero, FactorWatch sections), which were
    # authored under autoescape=True — same flip the US builder made in #4237.
    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)

    # Theme-context hero (server-rendered, same organ the old baskets_china page had).
    # Reader pattern, not a new artifact: engine.theme_context.write_context (called by
    # build_baskets_china, which runs earlier in both asia-close.yml and daily.yml's
    # cl_china) owns site/basketdata/theme_context_cn.json; we read it fail-soft — an
    # absent/corrupt file just renders the plain-header fallback branch.
    theme_context = None
    try:
        _tc_path = site / "basketdata" / "theme_context_cn.json"
        if _tc_path.exists():
            theme_context = json.loads(_tc_path.read_text())
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china_sector_central: theme_context read failed (%s) — plain hero", e)

    # Sleeve summary stats for the Reversal Sleeve card (moved here from build_baskets_china
    # with the card itself; same committed sources, same fail-soft posture).
    sleeve_stats = None
    try:
        _sleeve_json = site / "factordata" / "cn_reversal_sleeve.json"
        if _sleeve_json.exists():
            _sd = json.loads(_sleeve_json.read_text())
            _sf = (_sd.get("sizing") or {}).get("sleeve_factor")
            _nm = _sd.get("n_members")
            if _sf is not None and _nm is not None:
                sleeve_stats = {"n_members": int(_nm), "sleeve_factor": float(_sf)}
                _rd = (_sd.get("rederive_stats") or {}).get("primary") or {}
                _full = _rd.get("full") or {}
                if _full.get("sharpe") is not None:
                    sleeve_stats["sharpe"] = float(_full["sharpe"])
                if _full.get("n") is not None:
                    sleeve_stats["n_rebalances"] = int(_full["n"])
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.debug("china_sector_central: sleeve stats load skipped (%s)", e)

    from datetime import datetime, timezone
    html = env.get_template("sector_central_china.html.j2").render(
        theme_context=theme_context,
        sleeve_stats=sleeve_stats,
        generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    write_page(site / "sector_central_china.html", html, encoding="utf-8")

    # the page embeds the cycle-map overlay → ensure its shared assets are present. The China
    # cycles DATA (sector_cycles_china_data.js) is written by build_china_sector_cycles, which
    # runs before this in daily.yml's cl_china; we copy the page assets and warn if data is absent.
    import shutil
    for asset in ("product-nav-icons.css", "dashboard-icons.css", "dashboard-icons.js",
                  "sector_cycles.css", "sector_cycles.js",
                  # SI Workspace shell: hash router, per-view lazy mount, view reads.
                  "si_workspace_china.js"):
        src = root / "templates" / asset
        if src.exists():
            shutil.copy2(src, site / asset)
    for need in ("sector_cycles_china_data.js", "sector_cycles_china_series_data.js",
                 "sector_cycles_china_narr_data.js", "sector_cycles_china_dna_data.js",
                 "mm_charts.js", "cycle.css"):
        if not (site / need).exists():
            log.warning("china_sector_central: %s missing — embedded cycle chart needs "
                        "build_china_sector_cycles (+ build_cycle) to run first", need)
    # merged-page organs shipped by other builders (baskets_cn copies the first three; the
    # US lane owns the shared rotation renderer) — warn-if-absent, same posture as above
    for need in ("lightweight-charts.js", "baskets_desk.js", "forming_narratives.js",
                 "subsector_rotation.js"):
        if not (site / need).exists():
            log.warning("china_sector_central: %s missing — the merged page's baskets/rotation "
                        "organs need build_baskets_china / the US site build to have run", need)

    log.info("built site/sector_central_china.html (%d sectors, %d baskets, %d calls logged, grader=%s)",
             len(data["sectors"]), len(data.get("baskets", [])), n_logged,
             (data.get("grader") or {}).get("available"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
