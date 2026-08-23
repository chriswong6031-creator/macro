#!/usr/bin/env python3
"""B2-10 + B2-11 (+ MAC1-002, PRC1R-001) — mobile geometry assertions the other
two Lane B audits do not cover.

  B2-10 / VTC1-006 — THE RAMP DIES WITH THE ROW IT MEASURES.
      `.r3-spread` is a five-segment proportional bar whose only claim to
      legibility is that each segment sits under the ledge cell it belongs to.
      Below 767px `shell.html` re-lays the ledge 2-up (1-up under 360) and the
      strip stops mapping to anything. This asserts the RELATION, not a
      hard-coded breakpoint: wherever the ledge is not a five-track row, the
      ramp must not be painted; wherever it IS a five-track row, the ramp must
      be painted. A media query copied into the audit would pass even if the
      layout query moved; the relation cannot.

  B2-11 / VTC1-007 — THE RECEIPT BELONGS TO THE WHOLE STATEMENT.
      The Overview hero's receipt must sit AFTER the final wrapped line of the
      sentence it governs, and inside that sentence's own content box. Measured
      as geometry, not as CSS: the control's box must be on the last painted
      line box or below it, and may not start left of the paragraph's content
      edge. The predecessor failed this at 320 ZH, where the sentence filled its
      line and the control's `margin-inline-start:-13px` put it at x=-1 — off
      the stage, detached from the statement. Swept at 320/390 EN/ZH at 100% AND
      at 200% browser zoom (the house method: a W-physical device at 200% lays
      out at W/2 CSS px with device_scale_factor 2 — see zoom_sweep.py).

  MAC1-002 — the ZH `收起` control measured 39.0 x 44.0: `min-height` alone let
      the target shrink with the STRING. Every painted `.r3-textbtn` is measured
      on BOTH axes, in both languages, with the disclosures toggled so the
      shorter toggled labels are actually in the DOM. The census of ZH `收起`
      instances is asserted nonzero — an all-EN sweep cannot see this defect and
      must not be able to report it green.

  PRC1R-001 — the `[data-r3b1="02"]` receipt drives `#r3-receipt` with
      `aria-expanded` and no `aria-controls`, while its three R3B1-08 siblings
      name the same node. `aria_id_audit.py` cannot see this by construction —
      it audits references that exist, never references that are missing — so it
      is asserted here.

Usage:
    <playwright-python> mobile_geometry_audit.py [--json OUT.json] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BUILD = Path(__file__).resolve().parent
CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"

LANGS = ["en", "zh"]
# (physical width, zoom). 1440 rides along so the desktop half of every relation
# is asserted too — a suppression that also fires on the desk is a regression.
CELLS = [(1440, 1), (390, 1), (320, 1), (390, 2), (320, 2)]
TARGET_FLOOR = 44.0
VIEWS = ["overview", "map", "moving", "money", "explore", "confluence"]

RAMP_JS = r"""
() => {
  const sp = document.querySelector('[data-view="confluence"] .r3-spread[data-r3b2="10"]');
  const lg = document.getElementById('cf-ledge');
  if (!sp || !lg) return {error: 'ramp or ledge missing'};
  const tracks = getComputedStyle(lg).gridTemplateColumns.trim().split(/\s+/).filter(Boolean).length;
  const cs = getComputedStyle(sp);
  const r = sp.getBoundingClientRect();
  return {
    tracks: tracks,
    cells: lg.querySelectorAll('.r3-ledge-cell').length,
    ramp_display: cs.display,
    ramp_painted: cs.display !== 'none' && r.width > 0 && r.height > 0,
    ramp_segments: sp.children.length,
  };
}
"""

RECEIPT_JS = r"""
() => {
  const p = document.querySelector('[data-view="overview"] .r3-ov-season[data-r3b2="11"]');
  if (!p) return {error: 'no [data-r3b2="11"] receipt host'};
  const btn = p.querySelector('.r3-rcpt');
  if (!btn) return {error: 'receipt host carries no control'};
  /* the painted TEXT line boxes of the statement, the control excluded */
  const lines = [];
  const walk = (n) => {
    for (const c of n.childNodes) {
      if (c === btn) continue;
      if (c.nodeType === 3) {
        if (!c.textContent.trim()) continue;
        const r = document.createRange(); r.selectNodeContents(c);
        for (const q of r.getClientRects()) if (q.width > 0 && q.height > 0)
          lines.push({x: q.left, y: q.top, r: q.right, b: q.bottom});
        continue;
      }
      if (c.nodeType !== 1 || c.contains(btn)) continue;
      if (getComputedStyle(c).display === 'none') continue;
      const r = document.createRange(); r.selectNodeContents(c);
      for (const q of r.getClientRects()) if (q.width > 0 && q.height > 0)
        lines.push({x: q.left, y: q.top, r: q.right, b: q.bottom});
    }
  };
  walk(p);
  lines.sort((a, z) => (a.y - z.y) || (a.x - z.x));
  const br = btn.getBoundingClientRect();
  const pcs = getComputedStyle(p);
  const prect = p.getBoundingClientRect();
  const contentLeft = prect.left + parseFloat(pcs.paddingLeft || 0) + parseFloat(pcs.borderLeftWidth || 0);
  const last = lines.length ? lines[lines.length - 1] : null;
  const mid = br.top + br.height / 2;
  return {
    line_count: lines.length,
    last_line: last ? {x: +last.x.toFixed(1), y: +last.y.toFixed(1), b: +last.b.toFixed(1)} : null,
    btn: {x: +br.left.toFixed(1), y: +br.top.toFixed(1),
          w: +br.width.toFixed(1), h: +br.height.toFixed(1)},
    content_left: +contentLeft.toFixed(1),
    doc_width: document.documentElement.clientWidth,
    ink_mid_y: +mid.toFixed(1),
    /* "flows with the text", measured on the INK rather than on the hit box.
       The control is a 44x44 target wearing a centred 16px ring, pulled by
       `margin:-14px` so it does not inflate the line it sits in — so its BOX
       always straddles the neighbouring line box by 14px and box-top is not the
       question. Its ring centre is the box's midline. It passes if that ring
       sits ON the last painted line of the statement, or IMMEDIATELY after it —
       within one control-height, which is what separates "the next line of this
       sentence" from "somewhere else on the page". */
    on_last_line: last ? (mid >= last.y - 2 && mid <= last.b + 2) : false,
    after_last_line: last ? (mid >= last.b - 2 && mid <= last.b + br.height) : false,
    inside_content_box: br.left >= contentLeft - 3,
    inside_viewport: br.left >= -0.5 && br.right <= document.documentElement.clientWidth + 0.5,
  };
}
"""

TEXTBTN_JS = r"""
() => {
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
  const host = document.querySelector('.si-view.on');
  if (!host) return [];
  return [...host.querySelectorAll('.r3-textbtn')].filter((b) => {
    const cs = getComputedStyle(b);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && !b.hasAttribute('hidden');
  }).map((b) => {
    const r = b.getBoundingClientRect();
    return {text: visText(b), w: +r.width.toFixed(1), h: +r.height.toFixed(1)};
  }).filter((m) => m.w > 0 && m.h > 0);
}
"""

TOGGLE_JS = r"""
() => {
  const host = document.querySelector('.si-view.on');
  if (!host) return 0;
  const btns = [...host.querySelectorAll('.r3-textbtn')].filter((b) => {
    const cs = getComputedStyle(b);
    return cs.display !== 'none' && !b.hasAttribute('hidden') && b.getBoundingClientRect().width > 0;
  });
  btns.forEach((b) => b.click());
  return btns.length;
}
"""

ARIA_JS = r"""
() => {
  const b = document.querySelector('[data-r3b1="02"] button.r3-rcpt');
  const panel = document.getElementById('r3-receipt');
  const siblings = [...document.querySelectorAll('[aria-controls="r3-receipt"]')].length;
  return {
    present: !!b,
    aria_controls: b ? b.getAttribute('aria-controls') : null,
    aria_expanded: b ? b.getAttribute('aria-expanded') : null,
    panel_present: !!panel,
    controls_r3_receipt_count: siblings,
  };
}
"""


def activate(page, view: str) -> None:
    page.evaluate(
        "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
        "if(b)b.click();else location.hash='#'+v;}", view)
    page.wait_for_timeout(650)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(BUILD / "mobile_geometry_audit.json"))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not CANDIDATE.exists():
        print(f"[geo] missing candidate: {CANDIDATE}", file=sys.stderr)
        return 2

    url = CANDIDATE.as_uri()
    cells: list[dict] = []
    findings: list[dict] = []
    zh_shou_qi_seen = 0
    aria_checked = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for phys, zoom in CELLS:
            css_w = phys // zoom
            for lang in LANGS:
                ctx = browser.new_context(
                    viewport={"width": css_w, "height": 900 // zoom},
                    device_scale_factor=zoom,
                    is_mobile=phys < 768,
                    has_touch=phys < 768,
                )
                page = ctx.new_page()
                page.goto(url, wait_until="load")
                page.wait_for_timeout(1300)
                page.evaluate(
                    "(l)=>{ if(window.REF&&REF.setLang) REF.setLang(l);"
                    " else { document.documentElement.setAttribute('data-lang',l);"
                    " document.dispatchEvent(new CustomEvent('langchange')); } }",
                    lang,
                )
                page.wait_for_timeout(450)

                fails: list[str] = []

                # ── B2-11 · the Overview hero receipt ────────────────────
                activate(page, "overview")
                rc = page.evaluate(RECEIPT_JS)
                if rc.get("error"):
                    fails.append(f"receipt: {rc['error']}")
                else:
                    if rc["line_count"] <= 0:
                        fails.append("receipt host has zero painted text lines (empty selector set)")
                    if not (rc["on_last_line"] or rc["after_last_line"]):
                        fails.append(
                            f"receipt is not on/after the final wrapped line "
                            f"(btn y={rc['btn']['y']}, last line {rc['last_line']})")
                    if not rc["inside_content_box"]:
                        fails.append(
                            f"receipt starts left of its own statement "
                            f"(x={rc['btn']['x']} vs content edge {rc['content_left']})")
                    if not rc["inside_viewport"]:
                        fails.append(f"receipt is clipped by the viewport (x={rc['btn']['x']})")

                # ── B2-10 · the ramp vs the row it measures ──────────────
                activate(page, "confluence")
                rp = page.evaluate(RAMP_JS)
                if rp.get("error"):
                    fails.append(f"ramp: {rp['error']}")
                else:
                    if rp["cells"] <= 0:
                        fails.append("ledge cell census is zero (empty selector set)")
                    if rp["ramp_segments"] <= 0:
                        fails.append("ramp segment census is zero (empty selector set)")
                    stacked = rp["tracks"] < 5
                    if stacked and rp["ramp_painted"]:
                        fails.append(f"ramp is painted while the ledge is {rp['tracks']}-up "
                                     "(it no longer maps to the cells)")
                    if not stacked and not rp["ramp_painted"]:
                        fails.append("ramp is suppressed while the ledge is still a five-track row "
                                     "(desktop must be unchanged)")

                # ── MAC1-002 · every text button, both axes, toggled ─────
                small: list[dict] = []
                btn_census = 0
                for view in VIEWS:
                    activate(page, view)
                    page.evaluate(TOGGLE_JS)
                    page.wait_for_timeout(500)
                    for m in page.evaluate(TEXTBTN_JS):
                        btn_census += 1
                        if lang == "zh" and "收起" in m["text"]:
                            zh_shou_qi_seen += 1
                        if m["w"] < TARGET_FLOOR or m["h"] < TARGET_FLOOR:
                            small.append({"view": view, **m})
                if btn_census <= 0:
                    fails.append(".r3-textbtn census is zero (empty selector set)")
                if small:
                    fails.append(f"{len(small)} .r3-textbtn under the {TARGET_FLOOR}px floor: "
                                 + "; ".join(f"{s['text']!r} {s['w']}x{s['h']} ({s['view']})"
                                             for s in small[:4]))

                # ── PRC1R-001 · one disclosure target, one wiring ────────
                # Run AFTER the six-view sweep: the three R3B1-08 sibling
                # controls are painted when the Moving view is first activated,
                # so a count taken from a cold Overview would see only this one
                # and would charge a defect that does not exist.
                ar = page.evaluate(ARIA_JS)
                aria_checked += 1
                if not ar["present"]:
                    fails.append("PRC1R-001: [data-r3b1=\"02\"] receipt control not found")
                elif ar["aria_controls"] != "r3-receipt":
                    fails.append(f"PRC1R-001: aria-controls={ar['aria_controls']!r}, expected 'r3-receipt'")
                elif not ar["panel_present"]:
                    fails.append("PRC1R-001: #r3-receipt panel missing")
                elif ar["controls_r3_receipt_count"] < 4:
                    fails.append(f"PRC1R-001: only {ar['controls_r3_receipt_count']} control(s) name "
                                 "#r3-receipt; the three R3B1-08 siblings plus this one is 4")
                ctx.close()

                cell = {
                    "physical_width": phys, "css_width": css_w,
                    "zoom": f"{zoom * 100}%", "lang": lang,
                    "receipt": rc, "ramp": rp, "aria": ar,
                    "textbtn_census": btn_census,
                    "textbtn_under_floor": small,
                    "failures": fails,
                }
                cells.append(cell)
                if fails:
                    findings.append({"width": phys, "zoom": f"{zoom * 100}%",
                                     "lang": lang, "failures": fails})
                if args.verbose:
                    print(f"[geo] {phys}@{zoom * 100}%/{lang}: "
                          f"ledge={rp.get('tracks')}-up ramp_painted={rp.get('ramp_painted')} "
                          f"receipt_ok={rc.get('on_last_line') or rc.get('after_last_line')} "
                          f"textbtns={btn_census} failures={len(fails)}")
        browser.close()

    # MAC1-002 is a LANGUAGE-conditional defect: a sweep that never rendered the
    # ZH string it names cannot report on it.
    if zh_shou_qi_seen == 0:
        findings.append({"width": 0, "zoom": "-", "lang": "zh",
                         "failures": ["MAC1-002: zero ZH 收起 controls measured — "
                                      "the named control was never rendered, so this "
                                      "sweep cannot report on it"]})

    ok = bool(cells) and not findings
    out = {
        "schema": "mastermind.r3b2.mobile_geometry_audit.v1",
        "candidate": CANDIDATE.name,
        "target_floor_px": TARGET_FLOOR,
        "zh_shou_qi_controls_measured": zh_shou_qi_seen,
        "aria_cells_checked": aria_checked,
        "cells": cells,
        "failing_cells": findings,
        "pass": ok,
    }
    Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[geo] {len(cells)} cells swept "
          f"({'/'.join(f'{w}@{z*100}%' for w, z in CELLS)} x EN/ZH)")
    print(f"[geo] B2-10 ramp: painted in "
          f"{sum(1 for c in cells if c['ramp'].get('ramp_painted'))} cell(s), suppressed in "
          f"{sum(1 for c in cells if not c['ramp'].get('ramp_painted'))} "
          f"(five-track ledge in {sum(1 for c in cells if c['ramp'].get('tracks') == 5)})")
    print(f"[geo] B2-11 receipt on/after the final wrapped line: "
          f"{sum(1 for c in cells if c['receipt'].get('on_last_line') or c['receipt'].get('after_last_line'))}"
          f"/{len(cells)} cells; inside its own content box: "
          f"{sum(1 for c in cells if c['receipt'].get('inside_content_box'))}/{len(cells)}")
    print(f"[geo] MAC1-002 .r3-textbtn measured: {sum(c['textbtn_census'] for c in cells)} "
          f"({zh_shou_qi_seen} ZH 收起), under the {TARGET_FLOOR}px floor: "
          f"{sum(len(c['textbtn_under_floor']) for c in cells)}")
    print(f"[geo] PRC1R-001 aria-controls=\"r3-receipt\" on [data-r3b1=\"02\"]: "
          f"{sum(1 for c in cells if c['aria'].get('aria_controls') == 'r3-receipt')}/{len(cells)} cells")
    print(f"[geo] cells failing: {len(findings)}/{len(cells)}")
    print(f"[geo] json → {args.json}")
    for f in findings:
        print(f"[geo] FAIL {f['width']}@{f['zoom']}/{f['lang']}: " + "; ".join(f["failures"]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
