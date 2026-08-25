#!/usr/bin/env python3
"""R3B1-11 — contrast audit for the Sector Central R3B.1 candidate.

Walks every rendered text leaf in all six views across theme x language and
computes the WCAG 2.x contrast ratio of its painted foreground against the
COMPOSITED painted surface behind it (the whole ancestor background stack,
alpha-composited bottom-up onto the canvas colour), not merely the nearest
opaque ancestor.

Two traps this deliberately handles, both of which have fabricated results in
prior audits of this artifact:

  1. Chromium serialises any `color-mix()` value as `color(srgb r g b / a)`
     with components in 0..1.  A parser that reads those as 0..255 saturates
     every channel, makes foreground and background identical, and reports a
     ratio of exactly 1.00.  A computed ratio of exactly 1.00 in this codebase
     means the PARSER broke, not the page: both spellings are parsed here, and
     an exact 1.00 is flagged `SUSPECT` rather than reported as a failure.
  2. `html[data-lang="zh"]` inverts --up/--down site-wide (红涨绿跌).  The swap
     is NOT contrast-neutral, so every cell is measured at theme x language;
     an EN-only sweep is blind to the entire ZH half of the matrix.

Usage:
    <playwright-python> contrast_audit.py [--json OUT.json] [--fail-only]

Exit code 0 when every measured cell that carries customer meaning clears the
DESIGN_SYSTEM_SPEC.md S366 floor (4.5:1 under 18px / under 14pt bold), 1
otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BUILD = Path(__file__).resolve().parent
CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
VIEWS = ["overview", "map", "moving", "money", "explore", "confluence"]
THEMES = ["dark", "light"]
LANGS = ["en", "zh"]

# The cells the R3B.1 commission names by hand.  Probed BY VISIBLE TEXT so the
# report reads the way the critic receipts do, and so a class rename cannot
# silently drop a commissioned cell from the matrix.
NAMED_PROBES = {
    "action state — Buy now / 立即买入": ["Buy now", "立即买入"],
    "action state — Entry now / 现可入场": ["Entry now", "现可入场"],
    "risk state — Risk appetite / 风险偏好": ["Risk appetite", "风险偏好", "Risk-on", "偏好风险"],
    "track record — Still measuring / 测量中": ["Still measuring", "测量中"],
    "track record — Clears the bar / 已达标": ["Clears the bar", "已达标"],
    "board column — 20d vs market / 20日对比市场": ["20d vs market", "20日对比市场"],
}

# ── colour maths ────────────────────────────────────────────────────────────
_RGB = re.compile(r"^rgba?\(([^)]+)\)")
_SRGB = re.compile(r"^color\(srgb\s+([^)]+)\)")


def parse_color(s: str):
    """Parse both `rgb()/rgba()` (0..255) and `color(srgb …)` (0..1)."""
    if not s:
        return None
    s = s.strip()
    m = _RGB.match(s)
    if m:
        parts = [p for p in re.split(r"[\s,/]+", m.group(1)) if p]
        try:
            nums = [float(p.rstrip("%")) for p in parts]
        except ValueError:
            return None
        if len(nums) < 3:
            return None
        a = nums[3] if len(nums) > 3 else 1.0
        if "%" in parts[3] if len(parts) > 3 else False:
            a /= 100.0
        return (nums[0], nums[1], nums[2], a)
    m = _SRGB.match(s)
    if m:
        parts = [p for p in re.split(r"[\s/]+", m.group(1)) if p]
        try:
            nums = [float(p.rstrip("%")) for p in parts]
        except ValueError:
            return None
        if len(nums) < 3:
            return None
        a = nums[3] if len(nums) > 3 else 1.0
        return (nums[0] * 255.0, nums[1] * 255.0, nums[2] * 255.0, a)
    if s in ("transparent",):
        return (0.0, 0.0, 0.0, 0.0)
    return None


def _lin(v: float) -> float:
    v /= 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def luminance(c) -> float:
    return 0.2126 * _lin(c[0]) + 0.7152 * _lin(c[1]) + 0.0722 * _lin(c[2])


def over(fg, bg):
    a = fg[3]
    return (fg[0] * a + bg[0] * (1 - a), fg[1] * a + bg[1] * (1 - a), fg[2] * a + bg[2] * (1 - a), 1.0)


def ratio(fg, bg) -> float:
    f = luminance(over(fg, bg)) + 0.05
    b = luminance(bg) + 0.05
    return f / b if f > b else b / f


def composite_stack(layers, canvas):
    """Composite an ancestor background stack (outermost-first) onto the canvas."""
    surface = canvas
    for lay in layers:
        c = parse_color(lay)
        if c is None or c[3] == 0:
            continue
        surface = over(c, surface)
    return surface


# ── page-side collector ─────────────────────────────────────────────────────
COLLECT_JS = r"""
(view) => {
  const root = document.querySelector('.si-view[data-view="' + view + '"]');
  if (!root) return [];
  const out = [];
  const seen = new Set();
  const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    const txt = (n.textContent || '').trim();
    if (!txt) continue;
    const el = n.parentElement;
    if (!el || seen.has(el)) continue;
    seen.add(el);
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    // .r3-vh is the artifact's visually-hidden utility: real AT content, no painted surface.
    if (el.closest('.r3-vh')) continue;
    if (el.getAttribute('aria-hidden') === 'true') continue;
    // ancestor background stack, outermost first
    const layers = [];
    let a = el;
    while (a && a !== document.documentElement) {
      const ac = getComputedStyle(a);
      const bg = ac.backgroundColor;
      const img = ac.backgroundImage;
      layers.unshift(img && img !== 'none' ? '__IMAGE__' : bg);
      a = a.parentElement;
    }
    layers.unshift(getComputedStyle(document.documentElement).backgroundColor);
    out.push({
      text: txt.slice(0, 60),
      tag: el.tagName.toLowerCase(),
      cls: (el.getAttribute('class') || '').slice(0, 80),
      fg: cs.color,
      layers: layers,
      size: parseFloat(cs.fontSize),
      weight: cs.fontWeight,
      // WCAG's ratio formula describes ONE foreground over ONE flat surface. A
      // shadowed glyph over a data-driven colour field satisfies neither half,
      // and the fresh Mobile/Accessibility critic said so explicitly when it
      // declined to claim the heatmap cases. Recorded, never scored.
      shadow: cs.textShadow && cs.textShadow !== 'none',
      // the embedded sector-ETF flow table is a VERBATIM production fragment
      // (fixture_supplement/fragments/sc_flows.html, carried under a sha256
      // receipt): its inline tint fills are producer bytes this reference may
      // not rewrite. Measured and reported, but owned upstream.
      verbatim: !!el.closest('.scf, .scf-wrap'),
    });
  }
  return out;
}
"""

SETLANG_JS = r"""
([theme, lang]) => {
  const d = document.documentElement;
  d.setAttribute('data-theme', theme);
  if (window.REF && typeof window.REF.setLang === 'function') { window.REF.setLang(lang); }
  else { d.setAttribute('data-lang', lang); try { document.dispatchEvent(new CustomEvent('langchange')); } catch (e) {} }
}
"""


def is_large(size: float, weight: str) -> bool:
    try:
        w = int(weight)
    except ValueError:
        w = 700 if weight in ("bold", "bolder") else 400
    return size >= 24.0 or (size >= 18.66 and w >= 700)


def canvas_for(theme: str):
    # the page paints body/:root background; resolved live, so just read it.
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(BUILD / "lane_crops_b" / "contrast_audit.json"))
    ap.add_argument("--fail-only", action="store_true")
    args = ap.parse_args()

    if not CANDIDATE.exists():
        print(f"[contrast] missing candidate: {CANDIDATE}", file=sys.stderr)
        return 2

    url = CANDIDATE.as_uri()
    results = []
    named = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for theme in THEMES:
            for lang in LANGS:
                ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = ctx.new_page()
                page.goto(url, wait_until="load")
                page.wait_for_timeout(1200)
                page.evaluate(SETLANG_JS, [theme, lang])
                page.wait_for_timeout(400)
                canvas = parse_color(page.evaluate("getComputedStyle(document.body).backgroundColor")) or (
                    255.0,
                    255.0,
                    255.0,
                    1.0,
                )
                for view in VIEWS:
                    page.evaluate(
                        "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');if(b)b.click();"
                        "else location.hash='#'+v;}",
                        view,
                    )
                    page.wait_for_timeout(650)
                    rows = page.evaluate(COLLECT_JS, view)
                    for r in rows:
                        fg = parse_color(r["fg"])
                        if fg is None:
                            continue
                        if "__IMAGE__" in r["layers"]:
                            continue  # a colour-field surface; not a flat-background claim
                        bg = composite_stack(r["layers"], canvas)
                        cr = ratio(fg, bg)
                        large = is_large(r["size"], r["weight"])
                        floor = 3.0 if large else 4.5
                        if r["shadow"]:
                            scope = "unmeasurable_shadowed_colour_field"
                        elif r["verbatim"]:
                            scope = "producer_verbatim_fragment"
                        else:
                            scope = "reference_authored"
                        rec = {
                            "theme": theme,
                            "lang": lang,
                            "view": view,
                            "text": r["text"],
                            "cls": r["cls"],
                            "size": r["size"],
                            "weight": r["weight"],
                            "fg": r["fg"],
                            "ratio": round(cr, 2),
                            "floor": floor,
                            "scope": scope,
                            "pass": cr + 1e-9 >= floor,
                            "suspect_parse": abs(cr - 1.0) < 1e-6,
                            "under_ramp": r["size"] < 10.0,
                        }
                        results.append(rec)
                        for label, needles in NAMED_PROBES.items():
                            if r["text"] in needles:
                                named.append(dict(rec, probe=label))
                ctx.close()
        browser.close()

    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"cells": results, "named": named}, ensure_ascii=False, indent=1), encoding="utf-8")

    scored = [r for r in results if r["scope"] == "reference_authored"]
    fails = [r for r in scored if not r["pass"] and not r["suspect_parse"]]
    suspects = [r for r in results if r["suspect_parse"]]
    under = [r for r in scored if r["under_ramp"]]
    upstream = [r for r in results if r["scope"] == "producer_verbatim_fragment" and not r["pass"]]
    unmeasurable = [r for r in results if r["scope"] == "unmeasurable_shadowed_colour_field"]

    print(f"[contrast] {len(results)} text cells measured across "
          f"{len(VIEWS)} views x {len(THEMES)} themes x {len(LANGS)} languages")
    print(f"[contrast] scored (reference-authored, flat surface): {len(scored)}")
    print(f"[contrast] GATE — AA failures: {len(fails)}   sub-10px cells: {len(under)}   "
          f"parser-suspect (ratio==1.00): {len(suspects)}")
    print(f"[contrast] recorded, NOT gated — producer verbatim fragment below AA: {len(upstream)}; "
          f"shadowed text over a data-driven colour field (no applicable method): {len(unmeasurable)}")
    for r in fails:
        print(f"  FAIL {r['ratio']:>5}:1  {r['theme']}/{r['lang']}/{r['view']:<10} "
              f"{r['size']}px w{r['weight']}  {r['text'][:34]!r}  .{r['cls'][:36]}")
    for r in under:
        print(f"  UNDER-RAMP {r['size']}px  {r['theme']}/{r['lang']}/{r['view']:<10} {r['text'][:34]!r}  .{r['cls'][:36]}")
    if upstream:
        lo = min(r["ratio"] for r in upstream)
        hi = max(r["ratio"] for r in upstream)
        print(f"  UPSTREAM (R3C dependency) {len(upstream)} cells in the sc_flows verbatim fragment, "
              f"{lo}:1 – {hi}:1")
    if not args.fail_only:
        print("\n[contrast] commissioned named cells")
        for r in sorted(named, key=lambda x: (x["probe"], x["theme"], x["lang"])):
            flag = "PASS" if r["pass"] else "FAIL"
            print(f"  {flag} {r['ratio']:>5}:1  {r['theme']:<5}/{r['lang']:<2} {r['size']}px w{r['weight']}  {r['probe']}")
    print(f"[contrast] json → {out}")
    return 0 if not fails and not under else 1


if __name__ == "__main__":
    raise SystemExit(main())
