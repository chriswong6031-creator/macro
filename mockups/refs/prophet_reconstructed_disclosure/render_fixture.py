#!/usr/bin/env python3
"""Regenerate the reconstructed-plan disclosure reference shots.

    python3 mockups/refs/prophet_reconstructed_disclosure/render_fixture.py [outdir]

research/PROPHET_OUTAGE_BACKFILL_2026_08.md §0.10. Renders
``templates/_prophet_receipts.html.j2`` against a SYNTHETIC published index — 2 plans
stamped ``origination_mode: "outage_backfill_2026_08_09"`` and 2 live ones — in both
themes and both languages, plus the zero-reconstructed control that must render exactly
what the board renders today.

WHY A FIXTURE AND NOT THE LIVE ARTIFACT. Zero reconstructed plans exist yet, so the live
index cannot show this state at all; and pinning tonight's real tickers would be a
scheduled red the moment the board turns over (the house's append-only-store trap).

Needs playwright for the PNGs; without it the HTML is still written and can be opened
by hand. The page shell here is a stand-in for the board panel — the shelf partial and
its own CSS are the real thing, imported from templates/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from engine.prophet_bridge import is_reconstructed, refusal_receipts  # noqa: E402

# ── synthetic published index: 2 reconstructed + 2 live, all open ────────────────────
PLANS = [
    {"id": "AVGO-BULL-20260809", "asset": "AVGO", "closed": False,
     "recorded_at": "2026-08-09", "origination_mode": "outage_backfill_2026_08_09",
     "backfill_executed_at": "2026-08-11"},
    {"id": "TSM-BULL-20260809", "asset": "TSM", "closed": False,
     "recorded_at": "2026-08-09", "origination_mode": "outage_backfill_2026_08_09",
     "backfill_executed_at": "2026-08-11"},
    {"id": "GPCR-BULL-20260604", "asset": "GPCR", "closed": False,
     "recorded_at": "2026-08-08"},
    {"id": "NBIS-BULL-20260731", "asset": "NBIS", "closed": False,
     "recorded_at": "2026-08-10", "origination_mode": None},
]

# ── synthetic us_standouts buy lane so the shelf has groups to draw under ─────────────
STANDOUTS = {"buy": [
    {"ticker": t, "name": n, "dir": "up", "entry_signal": {"status": s},
     "conviction": {"band": b}, "signal": {"tier_cascade": "T1"},
     "prophet": {"score": sc}}
    for t, n, s, b, sc in (
        ("AVGO", "Broadcom", "buy_now", "high", 91.2),
        ("TSM", "Taiwan Semiconductor", "buy_now", "high", 88.4),
        ("GPCR", "Structure Therapeutics", "buy_now", "high", 90.5),
        ("MU", "Micron Technology", "extended", "high", 77.0),
        ("ANET", "Arista Networks", "buy_soon", "high", 71.5),
        ("CRWD", "CrowdStrike", "await_confluence", "high", 66.1),
        ("PLTR", "Palantir", "topping", "high", 61.0),
        ("SNOW", "Snowflake", "avoid", "high", 55.4),
    )]}

PAGE = """<!doctype html><html lang="en" data-theme="{theme}" data-lang="{lang}"><head>
<meta charset="utf-8"><title>reconstructed disclosure — {theme}/{lang}</title>
<style>
:root{{--bg:#0d1017;--panel:#141922;--text:#e6ebf2;--muted:#8b95a6;--line:#232a36;
  --pv-wait:#e0a458;--pv-buy:#3fbf7f}}
html[data-theme="light"]{{--bg:#e8ebf1;--panel:#fff;--text:#161a20;--muted:#5d6675;
  --line:#d5dae2}}
body{{background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,
  "Segoe UI",Roboto,"Helvetica Neue",sans-serif;margin:0;padding:26px}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:16px 18px;max-width:760px}}
html[data-theme="light"] .panel{{box-shadow:0 1px 3px rgba(16,22,34,.09)}}
[data-tip-en]{{cursor:help}}
html[data-lang="en"] .l-zh,html[data-lang="zh"] .l-en{{display:none}}
.cap{{font:600 11px/1.4 ui-monospace,Menlo,monospace;color:var(--muted);
  letter-spacing:.06em;text-transform:uppercase;margin:0 0 10px}}
</style>{css}</head><body>
<p class="cap">{theme} · {lang} · {label}</p>
<div class="panel"><div style="font-size:12px;color:var(--muted);margin-bottom:6px">
&nbsp;… prophet board cards render above …</div>{shelf}</div></body></html>"""


def main() -> int:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    env.filters["min"] = lambda seq: min(seq)
    from engine import i18n  # noqa: PLC0415 — same import site as build_site.py
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    pvr = env.get_template("_prophet_receipts.html.j2").module
    css = str(pvr.pvr_css())

    OUT.mkdir(parents=True, exist_ok=True)
    pages: list[Path] = []
    open_plans = [p for p in PLANS if not p.get("closed")]
    for mode, label in (("with", "2 reconstructed + 2 live"),
                        ("control_zero", "0 reconstructed (control)")):
        recon = [p for p in open_plans if is_reconstructed(p)] if mode == "with" else []
        cx = refusal_receipts(STANDOUTS, [p["asset"] for p in open_plans],
                              reconstructed_plans=recon)
        if mode == "with":
            print(json.dumps(cx["reconstructed"], ensure_ascii=False, indent=1))
        else:
            assert "reconstructed" not in cx, "control must carry no disclosure key"
        shelf = str(pvr.pvr_shelf(cx))
        for theme in ("dark", "light"):
            for lang in ("en", "zh"):
                if mode == "control_zero" and lang == "zh":
                    continue
                stem = f"{theme}_{lang}" if mode == "with" else f"{mode}_{theme}_{lang}"
                page = OUT / f"{stem}.html"
                page.write_text(PAGE.format(theme=theme, lang=lang, css=css,
                                            shelf=shelf, label=label), encoding="utf-8")
                pages.append(page)

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        print(f"wrote {len(pages)} HTML page(s); playwright absent — no PNGs")
        return 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 820, "height": 480},
                              device_scale_factor=2)
        for page in pages:
            pg.goto(page.as_uri())
            pg.evaluate("document.querySelectorAll('details').forEach(d=>d.open=true)")
            pg.wait_for_timeout(120)
            pg.screenshot(path=str(page.with_suffix(".png")), full_page=True)
            # Collapsed = the shelf's DEFAULT state, so the evidence also shows what a
            # reader lands on before asking for the detail.
            if page.stem in ("dark_en", "light_en"):
                pg.evaluate(
                    "document.querySelectorAll('details').forEach(d=>d.open=false)")
                pg.wait_for_timeout(80)
                pg.screenshot(path=str(OUT / f"{page.stem}_collapsed.png"),
                              full_page=True)
        browser.close()
    for page in pages:
        page.unlink()
    print(f"wrote {len(pages)} shot(s) + 2 collapsed into {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
