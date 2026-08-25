#!/usr/bin/env python3
"""R3B1-09 — severe-zoom reflow sweep for the Sector Central R3B.1 candidate.

Commissioned matrix: all six views x physical viewport widths {320, 390, 768,
820} x {EN, ZH} at 200% browser zoom — 48 cells. 200% zoom on a W-physical
device is modelled the way the fresh Mobile/Accessibility critic modelled it:
a W/2 CSS layout viewport at device_scale_factor 2, so the layout engine sees
exactly the reflow width a real 200% zoom produces.

THREE GATES, all of which must read zero:

  1. document overflow — `documentElement.scrollWidth > clientWidth`.
  2. painted semantic clipping — for every text leaf, the PAINTED text runs
     (Range.getClientRects(), not the element box, and not scrollWidth) are
     compared against every ancestor that actually hides overflow. This is the
     gate scrollWidth cannot see: `.mny-verdict` reported healthy page-level
     geometry while the final leaf of "Volatility: calm" painted 3.3px past an
     `overflow:hidden` edge, and a scrollWidth-only sweep called that clean.
     `overflow:auto/scroll` ancestors are NOT clipping — their content is
     reachable — so only `hidden`/`clip` count.
  3. clipped primary controls — every focusable control's box must survive the
     same test, so no link, button or input is cut in half at reflow width.

Method notes that are load-bearing:
  * `page.screenshot()` permanently breaks CDP Emulation.setDeviceMetricsOverride
    for the rest of that browser session, so a sweep that shot crops mid-loop
    would silently measure later cells at the wrong width. This sweep takes NO
    screenshots and sets the viewport at CONTEXT creation rather than through a
    CDP override, so neither failure mode can occur; crops are captured by a
    separate pass.
  * `.r3-vh` is the artifact's visually-hidden utility — clipped by design, and
    real content for assistive technology. It is excluded by name, not by luck.

Usage:
    <playwright-python> zoom_sweep.py [--json OUT.json] [--verbose]
Exit 0 when all three gates read zero across all 48 cells, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BUILD = Path(__file__).resolve().parent
CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"

VIEWS = ["overview", "map", "moving", "money", "explore", "confluence"]
PHYSICAL_WIDTHS = [320, 390, 768, 820]
ZOOM = 2  # 200%
LANGS = ["en", "zh"]
# subpixel tolerance: font metrics and fractional grid tracks routinely put a
# painted run a few hundredths of a pixel past a border box. The defect this
# gate exists to catch measured 3.3px.
TOL = 1.0

MEASURE_JS = r"""
([view, tol]) => {
  const root = document.querySelector('.si-view[data-view="' + view + '"]');
  const res = { docOverflow: 0, clippedText: [], clippedControls: [], measured: 0 };
  const de = document.documentElement;
  res.docOverflow = Math.max(0, de.scrollWidth - de.clientWidth);

  if (!root) { res.missing = true; return res; }

  /* Ancestors that genuinely HIDE content, resolved PER AXIS.
     Reachability, not the presence of an `overflow:hidden` somewhere above, is
     what decides whether meaning was lost. The walk therefore stops on an axis
     the moment it meets a SCROLL PORT (`auto`/`scroll`): content inside one is
     reachable by scrolling, and the outer card's `overflow:hidden` — which
     exists to clip a 14px border-radius — never gets a chance to hide it.
     Ignoring that produced 1,722 false findings on a first run of this sweep:
     every wide table inside `.r3-tblbox{overflow-x:auto}` and the whole
     `.scf-wrap` flow table were charged against the rounded card enclosing them. */
  function clippers(el) {
    const out = [];
    let a = el.parentElement;
    let liveX = true, liveY = true;
    while (a && a !== document.documentElement && (liveX || liveY)) {
      const cs = getComputedStyle(a);
      const ox = cs.overflowX, oy = cs.overflowY;
      const scrollX = ox === 'auto' || ox === 'scroll';
      const scrollY = oy === 'auto' || oy === 'scroll';
      const hx = liveX && (ox === 'hidden' || ox === 'clip');
      const hy = liveY && (oy === 'hidden' || oy === 'clip');
      if (hx || hy) out.push({ el: a, hx, hy, r: a.getBoundingClientRect() });
      if (scrollX) liveX = false;
      if (scrollY) liveY = false;
      a = a.parentElement;
    }
    return out;
  }

  /* Content the reader has not asked for yet is not content that was taken away.
     A closed <details>, a `max-height:0` phone collapse and a
     `content-visibility:hidden` subtree all park real content out of layout on
     purpose, behind a control the reader can operate; charging their geometry
     as "clipped meaning" would mean every accordion in the artifact fails a
     reflow gate. `checkVisibility` answers all three in one call; the explicit
     closed-<details> and visibility guards keep the test honest on engines whose
     `checkVisibility` predates the content-visibility flag. */
  function parked(el) {
    if (el.closest('details:not([open])')) return true;
    if (el.checkVisibility && !el.checkVisibility({
      contentVisibilityAuto: true, opacityProperty: false, visibilityProperty: true
    })) return true;
    let a = el;
    while (a && a !== document.documentElement) {
      const cs = getComputedStyle(a);
      if (cs.visibility === 'hidden' || cs.contentVisibility === 'hidden') return true;
      if (parseFloat(cs.maxHeight) === 0) return true;
      a = a.parentElement;
    }
    return false;
  }

  function label(el) {
    return el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).trim().split(/\s+/).slice(0,3).join('.') : '');
  }

  function overflowAgainst(box, cl) {
    let d = 0;
    if (cl.hx) d = Math.max(d, box.right - cl.r.right, cl.r.left - box.left);
    if (cl.hy) d = Math.max(d, box.bottom - cl.r.bottom, cl.r.top - box.top);
    return d;
  }

  // ── gate 2: painted text runs vs hiding ancestors ────────────────────────
  const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    const txt = (n.textContent || '').trim();
    if (!txt) continue;
    const el = n.parentElement;
    if (!el) continue;
    if (el.closest('.r3-vh')) continue;               // visually-hidden by design
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (parked(el)) continue;
    const cls = clippers(el);
    if (!cls.length) continue;
    const range = document.createRange();
    range.selectNodeContents(n);
    const rects = range.getClientRects();
    if (!rects.length) continue;
    res.measured++;
    for (const box of rects) {
      if (box.width < 0.5 && box.height < 0.5) continue;
      for (const cl of cls) {
        const d = overflowAgainst(box, cl);
        if (d > tol) {
          res.clippedText.push({
            text: txt.slice(0, 48), on: label(el), clipper: label(cl.el),
            px: Math.round(d * 10) / 10,
          });
        }
      }
    }
  }

  // ── gate 3: focusable controls ───────────────────────────────────────────
  root.querySelectorAll('a[href], button, input, select, textarea, summary, [tabindex]').forEach(el => {
    if (el.closest('.r3-vh')) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return;
    if (parked(el)) return;
    const box = el.getBoundingClientRect();
    if (box.width < 1 && box.height < 1) return;
    for (const cl of clippers(el)) {
      const d = overflowAgainst(box, cl);
      if (d > tol) {
        res.clippedControls.push({
          name: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40),
          on: label(el), clipper: label(cl.el), px: Math.round(d * 10) / 10,
        });
      }
    }
  });

  // de-duplicate identical findings (a wrapped run repeats its own message)
  const uniq = a => { const s = new Set(), o = []; for (const x of a) { const k = JSON.stringify(x); if (!s.has(k)) { s.add(k); o.push(x); } } return o; };
  res.clippedText = uniq(res.clippedText);
  res.clippedControls = uniq(res.clippedControls);
  return res;
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(BUILD / "lane_crops_b" / "zoom_sweep.json"))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not CANDIDATE.exists():
        print(f"[zoom] missing candidate: {CANDIDATE}", file=sys.stderr)
        return 2

    url = CANDIDATE.as_uri()
    cells = []
    bad_cells = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for phys in PHYSICAL_WIDTHS:
            css_w = phys // ZOOM
            css_h = 900 // ZOOM if phys < 768 else 1000 // ZOOM
            for lang in LANGS:
                ctx = browser.new_context(
                    viewport={"width": css_w, "height": css_h},
                    device_scale_factor=ZOOM,
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
                for view in VIEWS:
                    page.evaluate(
                        "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
                        "if(b)b.click();else location.hash='#'+v;}",
                        view,
                    )
                    page.wait_for_timeout(700)
                    r = page.evaluate(MEASURE_JS, [view, TOL])
                    cell = {
                        "physical": phys, "css_width": css_w, "zoom": "200%",
                        "lang": lang, "view": view,
                        "doc_overflow_px": r["docOverflow"],
                        "clipped_text": r["clippedText"],
                        "clipped_controls": r["clippedControls"],
                        "text_runs_checked": r["measured"],
                    }
                    ok = (cell["doc_overflow_px"] == 0
                          and not cell["clipped_text"]
                          and not cell["clipped_controls"])
                    cell["pass"] = ok
                    if not ok:
                        bad_cells += 1
                        print(f"  FAIL {phys}px/200% {lang}/{view}: "
                              f"doc_overflow={cell['doc_overflow_px']}px "
                              f"clipped_text={len(cell['clipped_text'])} "
                              f"clipped_controls={len(cell['clipped_controls'])}")
                        for t in cell["clipped_text"][:6]:
                            print(f"      TEXT  +{t['px']}px  {t['text']!r} in {t['on']} clipped by {t['clipper']}")
                        for c in cell["clipped_controls"][:6]:
                            print(f"      CTRL  +{c['px']}px  {c['name']!r} ({c['on']}) clipped by {c['clipper']}")
                    elif args.verbose:
                        print(f"  ok   {phys}px/200% {lang}/{view}  "
                              f"({cell['text_runs_checked']} clipped-ancestor text runs checked)")
                    cells.append(cell)
                ctx.close()
        browser.close()

    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cells, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[zoom] {len(cells)} cells swept "
          f"({len(VIEWS)} views x {len(PHYSICAL_WIDTHS)} widths x {len(LANGS)} languages, 200%)")
    print(f"[zoom] document overflow: {sum(1 for c in cells if c['doc_overflow_px'] > 0)} cell(s)")
    print(f"[zoom] painted semantic clipping: {sum(len(c['clipped_text']) for c in cells)} finding(s)")
    print(f"[zoom] clipped primary controls: {sum(len(c['clipped_controls']) for c in cells)} finding(s)")
    print(f"[zoom] cells failing: {bad_cells}/{len(cells)}")
    print(f"[zoom] json → {out}")
    return 0 if bad_cells == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
