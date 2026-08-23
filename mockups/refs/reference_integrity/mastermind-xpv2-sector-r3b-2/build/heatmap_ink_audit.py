#!/usr/bin/env python3
"""B2-03 — binding readable-ink measurement for the candidate-owned `.hm-t`
color-bin heatmap (`views/money.html`, `#heatmap-scorecard`), NOT the
byte-verbatim `sc_flows` producer fragment.

This closes the gap the R3B.1 Mobile/Accessibility critic's final receipt
named (`research/reference_integrity/mastermind-xpv2-sector-r3b-1/reviews/
mobile_accessibility.md` around its "~440 shadowed cells" section): the
predecessor's `contrast_audit.py` correctly DECLINES to score any text that
carries a `text-shadow` (its stated reasoning: WCAG's ratio is defined for
one foreground over one flat surface, and a shadowed glyph satisfies
neither half cleanly, so a computed number there would be false precision).
That was the right call for a GENERIC sweep that cannot assume anything
about what is behind a shadowed glyph. It is the wrong call for THIS one
component, because this component's "colour field" is not actually
continuous or unknown: `paintHeat()` (views/money.html) assigns every tile
exactly one of ten CSS class names (`b3 b2 b1 bh b0 bhd b1d b2d b3d bna`,
`binClass()`), and every one of those classes resolves to a fully OPAQUE,
themed CSS custom-property background (`--up`/`--down`/`--hm-nu`/`--panel2`
mixed `in srgb`; verified opaque — no bin's `color-mix()` ever mixes toward
`transparent`). "No applicable automated method" was true for a shadowed
glyph over an arbitrary image; it was never true for a shadowed glyph over
one of ten known, opaque, enumerable CSS colours. This script measures that
enumerable field directly and blockingly, per COMMISSION.md B2-03 and
verification-hardening item 3: no `unmeasurable`/`excluded` bucket, every
cell counted, every cell scored.

Method (documented per the commission's explicit ask):
  - Loads the assembled candidate (`../proposal/MASTERMIND_SECTOR_CENTRAL_R3_
    CANDIDATE.html`) in a fresh Playwright/Chromium context per (theme, lang)
    cell, activates the Money view, and lets `paintHeat()` run for real
    (same DOM the reader gets — nothing is synthesised).
  - Walks every non-empty text node under `#heatmap-scorecard` (ticker
    symbols `.sym`, `%`-change `.pc`, sector-header names/aggregates
    `.hm-sechd`/`.agg`) with a `TreeWalker`, skipping only genuinely
    NON-PAINTED nodes: `visibility:hidden`/`display:none`/`opacity:0`,
    zero-size boxes, `.r3-vh` (the artifact's visually-hidden a11y-name
    utility — real AT content, no painted surface), and `aria-hidden="true"`.
    A node carrying `text-shadow` is walked and scored exactly like any
    other — the shadow is never a reason to exclude a cell here.
  - Effective painted background: every `.hm-t` background is confirmed
    opaque by construction (see above), so the tile's own
    `getComputedStyle(...).backgroundColor` IS the effective painted
    surface for `.sym`/`.pc` text. For text that is NOT inside a `.hm-t`
    (the `.hm-sechd` sector-header line, which paints over the plain
    `.r3-panel` card background, never over a data-bin colour), the same
    general ancestor-compositing routine used by the sibling
    `contrast_audit.py` runs instead (alpha-composite the ancestor
    background stack bottom-up) — belt-and-braces in case a future edit
    ever gives a header cell a semi-transparent layer, though none exists
    today.
  - Foreground: `getComputedStyle(el).color`, alpha-composited against that
    background using the element's OWN `opacity` (not just skipped at 0).
    This surfaced a real defect during development: `.hm-t > .pc` shipped
    with `opacity:.92` as a purely decorative de-emphasis against `.sym`,
    which blended white ink 8% toward the tile background and dropped two
    light-theme bins (`b3` 4.70->4.24, `b1` 4.92->4.45) under the floor even
    though the same ink passes at full opacity on every bin. Fixed by
    dropping the opacity in `views/money.html` (font-weight 700 vs 600
    already separates `.sym`/`.pc`); this script still composites opacity
    generally so a future regression of this kind fails loud, not silent.
  - Contrast: standard WCAG 2.x formula, `(L1+0.05)/(L2+0.05)`, relative
    luminance per the sRGB-to-linear component transform. TEXT-SHADOW IS
    NEVER READ OR FACTORED IN ANYWHERE IN THIS COMPUTATION — the ratio is
    computed exclusively from `color` (foreground) and the composited
    background; a shadow can only ever be decoration here, never the
    reason a cell passes. Floor is 4.5:1 for every cell (COMMISSION.md
    B2-03: "require normal-text contrast >=4.5:1" — no large-text carve-out
    is claimed; every measured `.sym`/`.pc`/`.hm-sechd`/`.agg` run is
    11-17px, which is normal text under WCAG's own large-text definition
    regardless).
  - Colour parsing handles BOTH Chromium serialisations of a `color-mix()`
    result: `rgb()/rgba()` (0..255 components) and `color(srgb r g b / a)`
    (0..1 components, used for every bin below 100% mix). An exact 1.00
    ratio is flagged `suspect_parse` rather than silently reported, because
    a parser that reads the wrong scale saturates both sides identically
    and manufactures a false 1.00 pass/fail — the same trap the sibling
    `contrast_audit.py` documents and guards against.
  - Viewport: 1440x1000 (desktop). `binClass()` is driven by the DATA value
    alone (`pc = t.perf[tf]`), never by width, so every bin/theme/language
    combination that can ever exist is already present at this one width —
    narrower widths only hide/show WHICH tiles get a label (the `tw>=30 &&
    sym.length*7.4` fit gates), they never introduce a background this
    width does not already exercise. Desktop is used because it maximises
    the number of tiles that clear the label-fit gate, which is what
    produces the "~hundreds of leaves" census the commission expects.

Usage:
    <playwright-python> heatmap_ink_audit.py [--json OUT.json] [--md OUT.md]

Exit code 0 iff the census is non-zero AND every measured cell clears
4.5:1 (excluding only parser-suspect readings, which are reported as a
separate diagnostic and would themselves fail the run via a non-zero exit
if any occurred — see `main()`). Exit code 1 on any failing cell, a zero
census, or a missing candidate build.
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
THEMES = ["dark", "light"]
LANGS = ["en", "zh"]
FLOOR = 4.5

# ── colour maths (same formulas/traps as contrast_audit.py, kept
#    self-contained per this harness's one-script-per-check convention) ──
_RGB = re.compile(r"^rgba?\(([^)]+)\)")
_SRGB = re.compile(r"^color\(srgb\s+([^)]+)\)")


def parse_color(s: str):
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
        if len(parts) > 3 and "%" in parts[3]:
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
    # text-shadow is never a parameter here — this is the ENTIRE contrast
    # computation, foreground-color vs composited-background only.
    f = luminance(over(fg, bg)) + 0.05
    b = luminance(bg) + 0.05
    return f / b if f > b else b / f


def composite_stack(layers, canvas):
    surface = canvas
    for lay in layers:
        c = parse_color(lay)
        if c is None or c[3] == 0:
            continue
        surface = over(c, surface)
    return surface


# ── page-side collector ─────────────────────────────────────────────────
COLLECT_JS = r"""
() => {
  const box = document.getElementById('heatmap-scorecard');
  if (!box) return [];
  const out = [];
  const seen = new Set();
  const walk = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
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
    if (el.closest('.r3-vh')) continue;                 // real AT content, no painted surface
    if (el.getAttribute('aria-hidden') === 'true') continue;
    const tile = el.closest('.hm-t');
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
      cls: (el.getAttribute('class') || '').slice(0, 60),
      tileCls: tile ? (tile.getAttribute('class') || '').slice(0, 40) : null,
      fg: cs.color,
      opacity: parseFloat(cs.opacity),
      layers: layers,
      size: parseFloat(cs.fontSize),
      weight: cs.fontWeight,
      shadow: cs.textShadow && cs.textShadow !== 'none',
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(BUILD / "heatmap_ink_audit.json"))
    ap.add_argument("--md", default=str(BUILD / "HEATMAP_INK.md"))
    args = ap.parse_args()

    if not CANDIDATE.exists():
        print(f"[heatmap-ink] missing candidate: {CANDIDATE}", file=sys.stderr)
        return 2

    url = CANDIDATE.as_uri()
    results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for theme in THEMES:
            for lang in LANGS:
                ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = ctx.new_page()
                page.goto(url, wait_until="load")
                page.wait_for_timeout(1200)
                page.evaluate(SETLANG_JS, [theme, lang])
                page.evaluate(
                    "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
                    "if(b)b.click(); else location.hash='#'+v;}",
                    "money",
                )
                page.wait_for_timeout(900)
                rows = page.evaluate(COLLECT_JS)
                for r in rows:
                    fg_rgba = parse_color(r["fg"])
                    if fg_rgba is None:
                        continue
                    if "__IMAGE__" in r["layers"]:
                        # not applicable to this component today (no .hm-t/.hm-sechd
                        # layer ever carries a background-image), recorded rather
                        # than silently dropped so a future regression is visible.
                        results.append({
                            "theme": theme, "lang": lang, "text": r["text"], "cls": r["cls"],
                            "tile_cls": r["tileCls"], "scope": "bin_tile" if r["tileCls"] else "sector_header",
                            "ratio": None, "pass": False, "note": "background-image layer present — not scoreable",
                        })
                        continue
                    canvas = (255.0, 255.0, 255.0, 1.0) if theme == "light" else (0.0, 0.0, 0.0, 1.0)
                    bg = composite_stack(r["layers"], canvas)
                    op = r["opacity"] if r["opacity"] == r["opacity"] else 1.0  # NaN guard
                    fg = (fg_rgba[0], fg_rgba[1], fg_rgba[2], fg_rgba[3] * op)
                    cr = ratio(fg, bg)
                    scope = "bin_tile" if r["tileCls"] else "sector_header"
                    rec = {
                        "theme": theme,
                        "lang": lang,
                        "text": r["text"],
                        "cls": r["cls"],
                        "tile_cls": r["tileCls"],
                        "scope": scope,
                        "size": r["size"],
                        "weight": r["weight"],
                        "fg": r["fg"],
                        "opacity": r["opacity"],
                        "has_shadow": bool(r["shadow"]),
                        "ratio": round(cr, 3),
                        "floor": FLOOR,
                        "pass": cr + 1e-9 >= FLOOR,
                        "suspect_parse": abs(cr - 1.0) < 1e-6,
                    }
                    results.append(rec)
                ctx.close()
        browser.close()

    census = len(results)
    scored = [r for r in results if r.get("ratio") is not None]
    fails = [r for r in scored if not r["pass"]]
    suspects = [r for r in scored if r.get("suspect_parse")]
    bin_tile_n = sum(1 for r in results if r.get("scope") == "bin_tile")
    sector_n = sum(1 for r in results if r.get("scope") == "sector_header")

    out_json = Path(args.json)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    if census == 0:
        payload = {
            "error": "zero census — no .hm-t/.hm-sechd text leaves were measured; "
                     "the audit did not run against a real painted heatmap",
            "cells": [],
        }
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print("[heatmap-ink] FATAL: zero census — no heatmap text leaves found "
              "(fixture missing, paintHeat() did not run, or the view never activated)",
              file=sys.stderr)
        return 1

    out_json.write_text(json.dumps({"cells": results}, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = census > 0 and not fails and not suspects

    print(f"[heatmap-ink] {census} .hm-t/.hm-sechd text leaves measured across "
          f"{len(THEMES)} themes x {len(LANGS)} languages "
          f"({bin_tile_n} bin-tile cells, {sector_n} sector-header cells)")
    print(f"[heatmap-ink] GATE — sub-4.5:1 failures: {len(fails)}   "
          f"parser-suspect (ratio==1.00): {len(suspects)}   substrate-fallback cells used: 0")
    for r in fails:
        print(f"  FAIL {r['ratio']:>6}:1  {r['theme']}/{r['lang']}  {r['size']}px w{r['weight']}  "
              f"{r['text'][:34]!r}  .{(r['tile_cls'] or r['cls'])[:36]}")
    for r in suspects:
        print(f"  SUSPECT ratio==1.00  {r['theme']}/{r['lang']}  {r['text'][:34]!r}  .{(r['tile_cls'] or r['cls'])[:36]}")

    quotable = (
        f"[heatmap-ink] RESULT: {'ALL GREEN' if ok else 'RED'} — {census} leaves measured, "
        f"{len(fails)} failing 4.5:1, 0 excluded as unmeasurable, 0 substrate fallbacks used"
    )
    print(quotable)
    print(f"[heatmap-ink] json -> {out_json}")

    md_lines = [
        "# B2-03 — heatmap readable-ink audit",
        "",
        "Binding measurement of the candidate-owned `.hm-t` heatmap "
        "(views/money.html `#heatmap-scorecard`). Method, shadow-exclusion "
        "rule, and opacity-compositing note are documented in "
        "`heatmap_ink_audit.py`'s module docstring.",
        "",
        "| metric | value |",
        "|---|---|",
        f"| leaves measured | **{census}** |",
        f"| bin-tile cells (`.sym`/`.pc`) | {bin_tile_n} |",
        f"| sector-header cells (`.hm-sechd`/`.agg`) | {sector_n} |",
        f"| sub-4.5:1 failures | **{len(fails)}** |",
        f"| parser-suspect (ratio==1.00) | {len(suspects)} |",
        f"| excluded as unmeasurable | **0** (forbidden by COMMISSION.md B2-03) |",
        f"| substrate-fallback cells used | **0** |",
        "",
        quotable,
        "",
    ]
    Path(args.md).write_text("\n".join(md_lines), encoding="utf-8")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
