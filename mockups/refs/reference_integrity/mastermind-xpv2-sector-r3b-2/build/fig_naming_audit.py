#!/usr/bin/env python3
"""B2-05 — binding figure-naming census for every `.r3-fig` in the candidate.

Closes VTC1-001 (blocker), MAC1-001 and PRC1R-002, which are three readings of
one mechanism: `.r3-cols` was the ONLY carrier of a figure column's name, it is
`aria-hidden="true"` at every width, and `@media (max-width:640px)` switches it
off — so the name reached no assistive-technology user anywhere and no sighted
user on a phone. Sixteen of eighteen figures had no accessible name at any
width, and R3B1-13's commissioned "Conviction / 综合把握" was present only above
the breakpoint.

What this script asserts, per (width x language) cell, over ALL SIX views:

  1 · CENSUS. The `.r3-fig` population is counted and must be NONZERO and must
      equal EXPECTED_FIG_CENSUS. A naming check that passes over an empty
      selector set is the exact failure class COMMISSION.md §"Verification
      hardening" forbids ("No check may pass over an empty selector set without
      a nonzero census assertion").
  2 · ACCESSIBLE NAME AT EVERY WIDTH. Every figure that carries a VALUE carries
      a name node (`.r3-figlab` / `.r3-vh` / `aria-label`) whose language-
      resolved text is non-empty — at 1440 and 390 and 320 alike.
  3 · VISIBLE NAME AT <=640. Where the `.r3-cols` legend is switched off, every
      PAINTED valued figure also paints its name. This is the half a purely
      accessible fix leaves open (MAC1-001's own note) and the half VTC1-001
      blocked on.
  4 · NO DOUBLE LABEL ABOVE THE BREAKPOINT. At 1440 the legend is visible and
      does the visual naming, so no figure may paint its own caption. Desktop
      composition is unchanged, and this is what proves it.
  5 · THE LABEL IS THE COLUMN'S OWN WORD. Overview's inline label is compared to
      the rendered `.r3-colfig[data-r3b2="01"]` header itself — Lane A's B2-01
      customer term for `theme_intel.themes[].score`. One producer path may not
      acquire a second, softer synonym on the way to a phone.
  6 · THE TWO COMMISSIONED PROOFS. Overview action rows render "Strength 76" /
      "强度 76" and Confluence picks render "Conviction 0.60" / "综合把握 0.60"
      (and 0.54) as PAINTED text at 320 and 390, in EN and ZH.

An EMPTY `.r3-fig` (Overview sector rows carry no blended score — ledger #7) is
counted, reported by name, and NOT required to carry a label: a caption over
nothing is a name for a value that does not exist. The count of empty cells is
asserted against EXPECTED_EMPTY so this exemption can never silently widen.

Playwright/Chromium is required (see README_BUILD.md); `verify_reference.py`
check (m) consumes the committed `fig_naming_audit.json` rather than re-running
the browser.

Usage:
    <playwright-python> fig_naming_audit.py [--json OUT.json] [--verbose]
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
LANGS = ["en", "zh"]
WIDTHS = [1440, 390, 320]
MOBILE_MAX = 640          # the breakpoint `.r3-cols` disappears at (shell.html)

# Frozen fixture => frozen population. 18 is the count the R3B.1 Visual/Taste
# critic independently arrived at ("of 18 .r3-fig elements only the 2 in
# cf-picks carry the .r3-vh name twin"); 15 on Overview (11 valued theme rows +
# 4 valueless sector rows) and 3 on Confluence (1 entry tier + 2 picks).
EXPECTED_FIG_CENSUS = 18
EXPECTED_EMPTY = 4

# The commissioned proofs, per language: (view, label, values that must appear
# under that label as painted text at 320 and 390).
PROOFS = {
    "en": [("overview", "Strength", ["76"]), ("confluence", "Conviction", ["0.60", "0.54"])],
    "zh": [("overview", "强度", ["76"]), ("confluence", "综合把握", ["0.60", "0.54"])],
}

MEASURE_JS = r"""
(view) => {
  /* language-resolved text: the artifact ships EN and ZH twins side by side and
     hides one with `display:none`, so `textContent` is never what a reader (or
     a screen reader) gets. This walks only the branch the current language
     actually resolves to. */
  const visText = (root) => {
    let out = '';
    const walk = (n) => {
      for (const c of n.childNodes) {
        if (c.nodeType === 3) { out += c.textContent; continue; }
        if (c.nodeType !== 1) continue;
        if (getComputedStyle(c).display === 'none') continue;
        walk(c);
      }
    };
    walk(root);
    return out.replace(/\s+/g, ' ').trim();
  };
  const painted = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    /* the `.r3-vh` / clipped presentation is a 1x1 box: not painted. */
    return r.width > 2 && r.height > 2;
  };

  const host = document.querySelector('.si-view.on');
  const figs = [];
  if (host) {
    host.querySelectorAll('.r3-fig').forEach((f) => {
      const labs = [...f.querySelectorAll('.r3-figlab, .r3-vh')];
      const nameText = labs.map(visText).join(' ').replace(/\s+/g, ' ').trim();
      const namePainted = labs.some(painted);
      const paintedNameText = labs.filter(painted).map(visText).join(' ').replace(/\s+/g, ' ').trim();
      /* value = everything the figure says that is NOT its own name */
      const clone = f.cloneNode(true);
      /* mirror the language resolution onto the clone before stripping names */
      const src = [...f.querySelectorAll('*')], dst = [...clone.querySelectorAll('*')];
      src.forEach((s, i) => { if (getComputedStyle(s).display === 'none') dst[i].remove(); });
      clone.querySelectorAll('.r3-figlab, .r3-vh').forEach((n) => n.remove());
      const valueText = (clone.textContent || '').replace(/\s+/g, ' ').trim();
      figs.push({
        view: view,
        value: valueText,
        name: nameText,
        aria: f.getAttribute('aria-label'),
        name_painted: namePainted,
        painted_name_text: paintedNameText,
        fig_painted: painted(f),
        carriers: labs.length,
      });
    });
  }

  /* the column header Lane A's B2-01 owns, language-resolved, `<em>` (the
     secondary "20d vs market" line) excluded — the primary customer term only. */
  let headerLabel = null;
  const hdr = document.querySelector('[data-view="overview"] .r3-colfig[data-r3b2="01"]');
  if (hdr) {
    const clone = hdr.cloneNode(true);
    const src = [...hdr.querySelectorAll('*')], dst = [...clone.querySelectorAll('*')];
    src.forEach((s, i) => { if (getComputedStyle(s).display === 'none') dst[i].remove(); });
    clone.querySelectorAll('em').forEach((n) => n.remove());
    headerLabel = (clone.textContent || '').replace(/\s+/g, ' ').trim();
  }

  const legend = document.querySelector('.si-view.on .r3-cols');
  return {
    figs: figs,
    header_label: headerLabel,
    legend_present: !!legend,
    legend_display: legend ? getComputedStyle(legend).display : null,
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(BUILD / "fig_naming_audit.json"))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not CANDIDATE.exists():
        print(f"[fig] missing candidate: {CANDIDATE}", file=sys.stderr)
        return 2

    url = CANDIDATE.as_uri()
    cells: list[dict] = []
    findings: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for width in WIDTHS:
            for lang in LANGS:
                # FRESH CONTEXT PER CELL: a page.screenshot() in one cell poisons
                # setDeviceMetricsOverride for the rest of the session, so every
                # measurement cell gets its own context (README_BUILD.md).
                ctx = browser.new_context(
                    viewport={"width": width, "height": 900},
                    is_mobile=width < 768,
                    has_touch=width < 768,
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

                figs: list[dict] = []
                header_label = None
                for view in VIEWS:
                    page.evaluate(
                        "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
                        "if(b)b.click();else location.hash='#'+v;}",
                        view,
                    )
                    page.wait_for_timeout(650)
                    r = page.evaluate(MEASURE_JS, view)
                    figs.extend(r["figs"])
                    if r["header_label"]:
                        header_label = r["header_label"]
                ctx.close()

                valued = [f for f in figs if f["value"]]
                empty = [f for f in figs if not f["value"]]
                unnamed = [f for f in valued if not (f["name"] or f["aria"])]
                mobile = width <= MOBILE_MAX
                naked_visible = [
                    f for f in valued if mobile and f["fig_painted"] and not f["name_painted"]
                ]
                double_labelled = [
                    f for f in valued if not mobile and f["name_painted"]
                ]
                # 5 · the inline label is the column header's own word
                ov_labels = sorted({f["name"] for f in valued
                                    if f["view"] == "overview" and f["name"]})
                label_mismatch = [
                    n for n in ov_labels
                    if header_label and not n.startswith(header_label)
                ]

                # 6 · the two commissioned proofs (mobile widths only)
                proofs: list[dict] = []
                if mobile:
                    for view, label, values in PROOFS[lang]:
                        for val in values:
                            hit = any(
                                f["view"] == view
                                and f["fig_painted"]
                                and f["painted_name_text"].startswith(label)
                                and f["value"].startswith(val)
                                for f in figs
                            )
                            proofs.append({"view": view, "label": label, "value": val, "pass": hit})

                cell = {
                    "width": width,
                    "lang": lang,
                    "census": len(figs),
                    "valued": len(valued),
                    "empty": len(empty),
                    "unnamed": [f["value"] for f in unnamed],
                    "naked_visible": [f["value"] for f in naked_visible],
                    "double_labelled": [f["value"] for f in double_labelled],
                    "header_label": header_label,
                    "overview_inline_labels": ov_labels,
                    "label_mismatch": label_mismatch,
                    "proofs": proofs,
                }
                cell_fail: list[str] = []
                if cell["census"] != EXPECTED_FIG_CENSUS:
                    cell_fail.append(f"census {cell['census']} != expected {EXPECTED_FIG_CENSUS}")
                if cell["census"] == 0:
                    cell_fail.append("zero .r3-fig found (empty selector set)")
                if cell["empty"] != EXPECTED_EMPTY:
                    cell_fail.append(f"valueless figures {cell['empty']} != expected {EXPECTED_EMPTY}")
                if unnamed:
                    cell_fail.append(f"{len(unnamed)} valued figure(s) with no accessible name")
                if naked_visible:
                    cell_fail.append(f"{len(naked_visible)} painted figure(s) with no visible name at <={MOBILE_MAX}")
                if double_labelled:
                    cell_fail.append(f"{len(double_labelled)} figure(s) painting a caption above the breakpoint")
                if label_mismatch:
                    cell_fail.append(f"inline label(s) {label_mismatch} != column header {header_label!r}")
                for p in proofs:
                    if not p["pass"]:
                        cell_fail.append(f"proof failed: {p['label']} {p['value']} on {p['view']}")
                cell["failures"] = cell_fail
                cells.append(cell)
                if cell_fail:
                    findings.append({"width": width, "lang": lang, "failures": cell_fail})
                if args.verbose:
                    print(f"[fig] {width}/{lang}: census={cell['census']} valued={cell['valued']} "
                          f"empty={cell['empty']} failures={len(cell_fail)}")

        browser.close()

    total_census = sum(c["census"] for c in cells)
    ok = bool(cells) and total_census > 0 and not findings
    out = {
        "schema": "mastermind.r3b2.fig_naming_audit.v1",
        "candidate": CANDIDATE.name,
        "expected_census_per_cell": EXPECTED_FIG_CENSUS,
        "expected_empty_per_cell": EXPECTED_EMPTY,
        "mobile_breakpoint_px": MOBILE_MAX,
        "cells": cells,
        "failing_cells": findings,
        "pass": ok,
    }
    Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[fig] {len(cells)} cells swept ({'x'.join(str(w) for w in WIDTHS)} x EN/ZH, six views each)")
    print(f"[fig] .r3-fig census: {total_census} total, {EXPECTED_FIG_CENSUS} per cell "
          f"({EXPECTED_EMPTY} valueless by construction)")
    print(f"[fig] valued figures with no accessible name: "
          f"{sum(len(c['unnamed']) for c in cells)}")
    print(f"[fig] painted figures with no visible name at <={MOBILE_MAX}: "
          f"{sum(len(c['naked_visible']) for c in cells)}")
    print(f"[fig] figures double-labelled above the breakpoint: "
          f"{sum(len(c['double_labelled']) for c in cells)}")
    print(f"[fig] commissioned visible-label proofs: "
          f"{sum(1 for c in cells for p in c['proofs'] if p['pass'])}/"
          f"{sum(len(c['proofs']) for c in cells)} passing")
    print(f"[fig] cells failing: {len(findings)}/{len(cells)}")
    print(f"[fig] json → {args.json}")
    for f in findings:
        print(f"[fig] FAIL {f['width']}/{f['lang']}: " + "; ".join(f["failures"]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
