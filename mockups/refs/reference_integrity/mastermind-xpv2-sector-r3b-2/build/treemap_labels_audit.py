#!/usr/bin/env python3
"""B2-06 + B2-07 — painted-label collision and mobile-interaction census for the
candidate-owned market-heat treemap (`views/money.html`, `#heatmap-scorecard`).

Two findings share this component and one measurement rig:

  VTC1-002 (B2-06) — sector/group labels overlap at 320 and 390.
      "Communication Services" paints 143.7px inside a 100.3px-wide section and
      lands on top of "Healthcare" (measured overlapX 38.4px at 320, 17.3px at
      390). R3B1-09's `fitHeatLabels()` gated the TICKER labels by painted width
      and left the section headers on the inherited character-count estimate
      (`nm.length*perCh + 66`). This script measures PAINTED BOXES — the union of
      each label's client rects — never a character count, and asserts that no
      two of them intersect. A box property cannot answer this: `.hm-sechd` is
      absolutely positioned with `left:0;right:0` inside its section and its
      text overflows visibly, so the element's own rect is the SECTION's width
      and reports no collision at all.

  VTC1-003 / MAC1-003 (B2-07) — the ~500 tiles must not be required individual
      tap targets at <=640. The disposition taken is the critic's own smallest
      remedy: below the breakpoint the map is context visualization and the two
      large Browse/List escape hatches lead. This script asserts (a) the treemap
      contains ZERO interactive descendants, (b) tiles compute
      `pointer-events:none` at <=640, so it is a stated rule rather than an
      accident of there being no handler today, and (c) both hatches are painted
      ABOVE the map at <=640 and BELOW it above the breakpoint — the same
      information reachable in the same view, led by the control that can
      actually be tapped.

Every census is asserted NONZERO before any "no failures" result is reported
(COMMISSION.md §"Verification hardening": no check may pass over an empty
selector set). A cell where the treemap failed to mount is a FAILING cell, not
a quiet zero.

Usage:
    <playwright-python> treemap_labels_audit.py [--json OUT.json] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BUILD = Path(__file__).resolve().parent
CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"

# 320/390 are the commissioned collision widths; 820 rides along as the nearest
# width above the interaction breakpoint, which is what makes assertion (c)
# discriminating in both directions.
CELLS = [(320, True), (390, True), (820, False)]
LANGS = ["en", "zh"]
THEMES = ["dark", "light"]
MOBILE_MAX = 640
TOUCH_FLOOR = 24.0        # WCAG 2.2 SC 2.5.8 minimum; the house floor is 44
OVERLAP_TOL = 0.5         # sub-pixel tolerance, same as fitHeatLabels()'s own

MEASURE_JS = r"""
() => {
  const box = document.getElementById('heatmap-scorecard');
  if (!box) return {error: 'no #heatmap-scorecard'};
  const paintedBox = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return null;
    const r = document.createRange(); r.selectNodeContents(el);
    const rects = r.getClientRects();
    let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    for (const q of rects) {
      if (q.width <= 0 || q.height <= 0) continue;
      x1 = Math.min(x1, q.left); y1 = Math.min(y1, q.top);
      x2 = Math.max(x2, q.right); y2 = Math.max(y2, q.bottom);
    }
    if (x1 === Infinity) return null;
    return {x: +x1.toFixed(2), y: +y1.toFixed(2), r: +x2.toFixed(2), b: +y2.toFixed(2)};
  };
  const visText = (el) => {
    let out = '';
    const walk = (n) => { for (const c of n.childNodes) {
      if (c.nodeType === 3) { out += c.textContent; continue; }
      if (c.nodeType !== 1) continue;
      if (getComputedStyle(c).display === 'none') continue;
      walk(c);
    } };
    walk(el); return out.replace(/\s+/g, ' ').trim();
  };

  /* `owner` is the label's own tile or section header. Two labels inside ONE
     owner are stacked by that owner's own flex column, and their LINE boxes
     touch by the half-leading Chromium includes in a Range rect (measured 1.4px
     between `.sym` and its own `.pc`) while the glyphs never do. That is the
     component laying itself out, not a collision, so same-owner pairs are
     recorded separately and never charged. Cross-owner contact is the defect
     VTC1-002 named: two independent names sharing one run of pixels. */
  const labels = [];
  let owner = 0;
  box.querySelectorAll('.hm-sechd').forEach((hd) => {
    if (getComputedStyle(hd).display === 'none') return;
    owner++;
    for (const c of hd.children) {
      if (getComputedStyle(c).display === 'none') continue;
      const pb = paintedBox(c);
      if (!pb) continue;
      labels.push({kind: c.className === 'agg' ? 'sector_agg' : 'sector_name',
                   text: visText(c), box: pb, owner: 'sec' + owner});
    }
  });
  let tileN = 0;
  box.querySelectorAll('.hm-t').forEach((t) => {
    tileN++;
    const sym = t.querySelector('.sym'), pc = t.querySelector('.pc');
    if (sym) { const pb = paintedBox(sym);
      if (pb) labels.push({kind: 'ticker', text: visText(sym), box: pb, owner: 't' + tileN}); }
    if (pc) { const pb = paintedBox(pc);
      if (pb) labels.push({kind: 'ticker_pc', text: visText(pc), box: pb, owner: 't' + tileN}); }
  });

  const overlaps = [], intra = [];
  for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
    const a = labels[i].box, b = labels[j].box;
    const ox = Math.min(a.r, b.r) - Math.max(a.x, b.x);
    const oy = Math.min(a.b, b.b) - Math.max(a.y, b.y);
    if (!(ox > TOL && oy > TOL)) continue;
    const rec = {
      a: labels[i].kind + ':' + labels[i].text, b: labels[j].kind + ':' + labels[j].text,
      overlap_x: +ox.toFixed(1), overlap_y: +oy.toFixed(1)};
    (labels[i].owner === labels[j].owner ? intra : overlaps).push(rec);
  }

  /* the tile population and its interaction surface */
  const tiles = [...box.querySelectorAll('.hm-t')];
  const interactive = [...box.querySelectorAll(
    'a,button,summary,select,input,textarea,[tabindex],[role="link"],[role="button"],[onclick]')];
  const subFloor = interactive.map((el) => {
    const r = el.getBoundingClientRect();
    return {tag: el.tagName, w: +r.width.toFixed(1), h: +r.height.toFixed(1)};
  }).filter((m) => m.w < FLOOR || m.h < FLOOR);
  const tilePE = tiles.length ? getComputedStyle(tiles[0]).pointerEvents : null;
  const tileTabbable = tiles.filter((t) => t.hasAttribute('tabindex')).length;

  const mapRect = box.getBoundingClientRect();
  const hatches = ['hm-alt', 'hm-names'].map((id) => {
    const d = document.getElementById(id);
    if (!d) return {id: id, present: false};
    const s = d.querySelector('summary');
    const sr = s.getBoundingClientRect();
    return {id: id, present: true, text: visText(s),
            y: +d.getBoundingClientRect().top.toFixed(1),
            summary_w: +sr.width.toFixed(1), summary_h: +sr.height.toFixed(1)};
  });

  return {
    labels: labels.length,
    sector_names: labels.filter((l) => l.kind === 'sector_name').length,
    tickers: labels.filter((l) => l.kind === 'ticker').length,
    overlaps: overlaps,
    intra_owner_line_box_contacts: intra.length,
    tiles: tiles.length,
    tile_pointer_events: tilePE,
    tile_tabbable: tileTabbable,
    interactive_in_map: interactive.length,
    sub_floor_interactive: subFloor,
    map_top: +mapRect.top.toFixed(1),
    map_height: +mapRect.height.toFixed(1),
    hatches: hatches,
    role: box.getAttribute('role'),
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(BUILD / "treemap_labels_audit.json"))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not CANDIDATE.exists():
        print(f"[tm] missing candidate: {CANDIDATE}", file=sys.stderr)
        return 2

    js = MEASURE_JS.replace("TOL", str(OVERLAP_TOL)).replace("FLOOR", str(TOUCH_FLOOR))
    url = CANDIDATE.as_uri()
    cells: list[dict] = []
    findings: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for width, is_mobile in CELLS:
            for lang in LANGS:
                for theme in THEMES:
                    ctx = browser.new_context(
                        viewport={"width": width, "height": 900},
                        is_mobile=width < 768,
                        has_touch=width < 768,
                    )
                    page = ctx.new_page()
                    page.goto(url, wait_until="load")
                    page.wait_for_timeout(1200)
                    page.evaluate(
                        "(t)=>document.documentElement.setAttribute('data-theme',t)", theme)
                    page.evaluate(
                        "(l)=>{ if(window.REF&&REF.setLang) REF.setLang(l);"
                        " else { document.documentElement.setAttribute('data-lang',l);"
                        " document.dispatchEvent(new CustomEvent('langchange')); } }",
                        lang,
                    )
                    page.wait_for_timeout(400)
                    page.evaluate(
                        "()=>{var b=document.querySelector('.si-view-btn[data-view=\"money\"]');"
                        "if(b)b.click();else location.hash='#money';}")
                    page.wait_for_timeout(1100)
                    r = page.evaluate(js)
                    ctx.close()

                    fails: list[str] = []
                    if r.get("error"):
                        fails.append(r["error"])
                        r = {"labels": 0, "overlaps": [], "tiles": 0}
                    # ── nonzero censuses ──────────────────────────────────
                    if r.get("tiles", 0) <= 0:
                        fails.append("tile census is zero (treemap did not mount)")
                    if r.get("labels", 0) <= 0:
                        fails.append("painted-label census is zero (empty selector set)")
                    if r.get("sector_names", 0) <= 0:
                        fails.append("sector-name census is zero (empty selector set)")
                    # ── B2-06 ─────────────────────────────────────────────
                    if r.get("overlaps"):
                        fails.append(f"{len(r['overlaps'])} painted label overlap(s)")
                    # ── B2-07 ─────────────────────────────────────────────
                    if r.get("interactive_in_map", 0) != 0:
                        fails.append(f"{r['interactive_in_map']} interactive element(s) inside the treemap")
                    if r.get("sub_floor_interactive"):
                        fails.append(f"{len(r['sub_floor_interactive'])} interactive element(s) under the "
                                     f"{TOUCH_FLOOR}px target floor inside the treemap")
                    if r.get("tile_tabbable", 0) != 0:
                        fails.append(f"{r['tile_tabbable']} tile(s) in the tab order")
                    if is_mobile and r.get("tile_pointer_events") != "none":
                        fails.append(f"tiles compute pointer-events={r.get('tile_pointer_events')!r} "
                                     f"at <={MOBILE_MAX} (expected 'none')")
                    hatches = r.get("hatches", [])
                    if len(hatches) != 2 or not all(h.get("present") for h in hatches):
                        fails.append("both Browse/List escape hatches must be present")
                    else:
                        for h in hatches:
                            if h["summary_h"] < 44.0:
                                fails.append(f"{h['id']} summary {h['summary_h']}px < 44px floor")
                            if is_mobile and h["y"] >= r["map_top"]:
                                fails.append(f"{h['id']} does not lead the map at <={MOBILE_MAX} "
                                             f"(hatch y={h['y']} vs map y={r['map_top']})")
                            if not is_mobile and h["y"] <= r["map_top"]:
                                fails.append(f"{h['id']} moved above the map above the breakpoint "
                                             f"(desktop composition must be unchanged)")

                    cell = {
                        "width": width, "lang": lang, "theme": theme,
                        "mobile": is_mobile,
                        "tiles": r.get("tiles"),
                        "painted_labels": r.get("labels"),
                        "sector_names": r.get("sector_names"),
                        "tickers": r.get("tickers"),
                        "overlaps": r.get("overlaps", []),
                        "intra_owner_line_box_contacts": r.get("intra_owner_line_box_contacts", 0),
                        "interactive_in_map": r.get("interactive_in_map"),
                        "sub_floor_interactive": r.get("sub_floor_interactive", []),
                        "tile_pointer_events": r.get("tile_pointer_events"),
                        "map_role": r.get("role"),
                        "map_top": r.get("map_top"),
                        "hatches": hatches,
                        "failures": fails,
                    }
                    cells.append(cell)
                    if fails:
                        findings.append({"width": width, "lang": lang, "theme": theme,
                                         "failures": fails})
                    if args.verbose:
                        print(f"[tm] {width}/{lang}/{theme}: tiles={cell['tiles']} "
                              f"labels={cell['painted_labels']} overlaps={len(cell['overlaps'])} "
                              f"failures={len(fails)}")
        browser.close()

    total_labels = sum(c["painted_labels"] or 0 for c in cells)
    total_tiles = sum(c["tiles"] or 0 for c in cells)
    ok = bool(cells) and total_labels > 0 and total_tiles > 0 and not findings
    out = {
        "schema": "mastermind.r3b2.treemap_labels_audit.v1",
        "candidate": CANDIDATE.name,
        "overlap_tolerance_px": OVERLAP_TOL,
        "touch_floor_px": TOUCH_FLOOR,
        "mobile_breakpoint_px": MOBILE_MAX,
        "cells": cells,
        "failing_cells": findings,
        "pass": ok,
    }
    Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[tm] {len(cells)} cells swept "
          f"({'/'.join(str(w) for w, _m in CELLS)} x EN/ZH x dark/light)")
    print(f"[tm] tile census: {total_tiles} across cells "
          f"(min {min((c['tiles'] or 0) for c in cells)} per cell)")
    print(f"[tm] painted-label census: {total_labels} "
          f"(sector names {sum(c['sector_names'] or 0 for c in cells)}, "
          f"tickers {sum(c['tickers'] or 0 for c in cells)})")
    print(f"[tm] painted label overlaps (cross-owner, blocking): "
          f"{sum(len(c['overlaps']) for c in cells)}")
    print(f"[tm] same-owner line-box contacts (a tile's own ticker/percent stack, "
          f"reported not charged): {sum(c['intra_owner_line_box_contacts'] for c in cells)}")
    print(f"[tm] interactive elements inside the treemap: "
          f"{sum(c['interactive_in_map'] or 0 for c in cells)}")
    print(f"[tm] interactive elements under the {TOUCH_FLOOR}px floor inside the treemap: "
          f"{sum(len(c['sub_floor_interactive']) for c in cells)}")
    print(f"[tm] cells failing: {len(findings)}/{len(cells)}")
    print(f"[tm] json → {args.json}")
    for f in findings:
        print(f"[tm] FAIL {f['width']}/{f['lang']}/{f['theme']}: " + "; ".join(f["failures"]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
