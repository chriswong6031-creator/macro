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
      acquire a second, softer synonym on the way to a phone. The DELTA's label
      is compared the same way against that header's own `<em>` second line.
  6 · THE COMMISSIONED PROOFS. Overview action rows render "Strength 76" /
      "强度 76" and "20d vs market +27.2%" / "20日对比市场 +27.2%", and Confluence
      picks render "Conviction 0.60" / "综合把握 0.60" (and 0.54), as PAINTED text
      at 320 and 390, in EN and ZH.
  7 · THE SECOND FIGURE IN THE CELL (B2-05, Sol strengthening). An Overview
      action-board cell holds TWO figures — the Strength score and the 20-day
      delta — inside ONE `.r3-fig`, so checks 2-4 above, which resolve per
      `.r3-fig`, are satisfied by the score's label alone and CANNOT see whether
      the delta is named. The delta population is therefore censused and checked
      in its own right: nonzero census, an accessible name at every width, a
      PAINTED name at <=640, and NO painted caption at 1440 (where the legend's
      `<em>` does the naming and desktop composition must be unchanged).

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

# B2-05 (Sol strengthening) — the SECOND figure inside an Overview action cell.
# Frozen fixture => frozen population: every `.r3-fig` that carries a Strength
# score also carries a `perf_20d_rel`, so the delta count is the valued-theme-row
# count (11 of the 15 Overview figures; the 4 sector rows carry neither).
EXPECTED_DELTA_CENSUS = 11

# The commissioned proofs, per language: (view, label, values that must appear
# under that label as painted text at 320 and 390).
PROOFS = {
    "en": [("overview", "Strength", ["76"]), ("confluence", "Conviction", ["0.60", "0.54"])],
    "zh": [("overview", "强度", ["76"]), ("confluence", "综合把握", ["0.60", "0.54"])],
}

# B2-05's own named meaning, verbatim from the Sol closure set: the phrase a
# customer must be able to READ on a phone, not merely hear. Matched against the
# delta's full language-resolved text (label + value), so a label that drifts,
# abbreviates, or stops being painted all fail the same assertion.
DELTA_PHRASE = {"en": "20d vs market +27.2%", "zh": "20日对比市场 +27.2%"}

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

  /* B2-05 (Sol strengthening) — the SECOND figure in an Overview action cell.
     `.r3-delta` lives INSIDE a `.r3-fig`, so the census above cannot see it: the
     cell already has a painted name (the Strength caption) whether or not the
     delta has one of its own. It is measured here as a figure in its own right.
     `phrase` is the whole language-resolved cell text of the delta — its own
     label plus its own value — which is exactly the customer meaning the closure
     set names ("20d vs market +27.2%"). CSS `text-transform` and the `::before`
     interpuncts are presentation and never appear here, so the assertion binds
     the authored string, not the painted casing. */
  const deltas = [];
  if (host) {
    host.querySelectorAll('.r3-fig .r3-delta').forEach((d) => {
      const labs = [...d.querySelectorAll('.r3-figlab, .r3-vh')];
      const clone = d.cloneNode(true);
      const src = [...d.querySelectorAll('*')], dst = [...clone.querySelectorAll('*')];
      src.forEach((s, i) => { if (getComputedStyle(s).display === 'none') dst[i].remove(); });
      clone.querySelectorAll('.r3-figlab, .r3-vh').forEach((n) => n.remove());
      deltas.push({
        view: view,
        phrase: visText(d),
        value: (clone.textContent || '').replace(/\s+/g, ' ').trim(),
        name: labs.map(visText).join(' ').replace(/\s+/g, ' ').trim(),
        name_painted: labs.some(painted),
        aria: d.getAttribute('aria-label'),
        painted: painted(d),
        carriers: labs.length,
      });
    });
  }

  /* the column header Lane A's B2-01 owns, language-resolved, `<em>` (the
     secondary "20d vs market" line) excluded — the primary customer term only. */
  let headerLabel = null;
  let headerUnit = null;
  const hdr = document.querySelector('[data-view="overview"] .r3-colfig[data-r3b2="01"]');
  if (hdr) {
    const clone = hdr.cloneNode(true);
    const src = [...hdr.querySelectorAll('*')], dst = [...clone.querySelectorAll('*')];
    src.forEach((s, i) => { if (getComputedStyle(s).display === 'none') dst[i].remove(); });
    clone.querySelectorAll('em').forEach((n) => n.remove());
    headerLabel = (clone.textContent || '').replace(/\s+/g, ' ').trim();
    /* the SAME header's `<em>` second line — the word the delta's own inline
       label must be, for the same reason the score's must be `headerLabel`. */
    const em = hdr.querySelector('em');
    if (em) headerUnit = visText(em);
  }

  const legend = document.querySelector('.si-view.on .r3-cols');
  return {
    figs: figs,
    deltas: deltas,
    header_label: headerLabel,
    header_unit: headerUnit,
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
                deltas: list[dict] = []
                header_label = None
                header_unit = None
                for view in VIEWS:
                    page.evaluate(
                        "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
                        "if(b)b.click();else location.hash='#'+v;}",
                        view,
                    )
                    page.wait_for_timeout(650)
                    r = page.evaluate(MEASURE_JS, view)
                    figs.extend(r["figs"])
                    deltas.extend(r["deltas"])
                    if r["header_label"]:
                        header_label = r["header_label"]
                    if r["header_unit"]:
                        header_unit = r["header_unit"]
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

                # 7 · the second figure in the cell — censused and judged alone
                d_unnamed = [d for d in deltas if not (d["name"] or d["aria"])]
                d_naked = [d for d in deltas if mobile and d["painted"] and not d["name_painted"]]
                d_double = [d for d in deltas if not mobile and d["name_painted"]]
                d_labels = sorted({d["name"] for d in deltas if d["name"]})
                d_label_mismatch = [
                    n for n in d_labels if header_unit and n != header_unit
                ]

                # 6 · the commissioned proofs (mobile widths only)
                proofs: list[dict] = []
                if mobile:
                    # `name_painted` is load-bearing here and not redundant with
                    # check 7: `phrase` is the language-resolved text, and a
                    # `.r3-vh` carrier is clipped, NOT `display:none`, so its
                    # words still land in `phrase`. Without this conjunct the
                    # proof would pass on the exact disposition Sol overrode —
                    # a name the customer can only hear.
                    proofs.append({
                        "view": "overview",
                        "label": "delta-phrase",
                        "value": DELTA_PHRASE[lang],
                        "pass": any(d["painted"] and d["name_painted"]
                                    and d["phrase"] == DELTA_PHRASE[lang]
                                    for d in deltas),
                    })
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
                    "delta_census": len(deltas),
                    "delta_painted": sum(1 for d in deltas if d["painted"]),
                    "delta_unnamed": [d["value"] for d in d_unnamed],
                    "delta_naked_visible": [d["value"] for d in d_naked],
                    "delta_double_labelled": [d["value"] for d in d_double],
                    "header_unit": header_unit,
                    "delta_inline_labels": d_labels,
                    "delta_label_mismatch": d_label_mismatch,
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
                if cell["delta_census"] != EXPECTED_DELTA_CENSUS:
                    cell_fail.append(
                        f"delta census {cell['delta_census']} != expected {EXPECTED_DELTA_CENSUS}")
                if cell["delta_census"] == 0:
                    cell_fail.append("zero .r3-delta found (empty selector set)")
                if d_unnamed:
                    cell_fail.append(f"{len(d_unnamed)} delta figure(s) with no accessible name")
                if d_naked:
                    cell_fail.append(
                        f"{len(d_naked)} painted delta(s) with no visible name at <={MOBILE_MAX}")
                if d_double:
                    cell_fail.append(
                        f"{len(d_double)} delta(s) painting a caption above the breakpoint")
                if d_label_mismatch:
                    cell_fail.append(
                        f"delta label(s) {d_label_mismatch} != header unit line {header_unit!r}")
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
        "expected_delta_census_per_cell": EXPECTED_DELTA_CENSUS,
        "delta_phrase": DELTA_PHRASE,
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
    print(f"[fig] .r3-delta census (2nd figure per Overview cell): "
          f"{sum(c['delta_census'] for c in cells)} total, {EXPECTED_DELTA_CENSUS} per cell")
    print(f"[fig] deltas with no accessible name: "
          f"{sum(len(c['delta_unnamed']) for c in cells)}  ·  "
          f"painted deltas with no visible name at <={MOBILE_MAX}: "
          f"{sum(len(c['delta_naked_visible']) for c in cells)}  ·  "
          f"deltas double-labelled above the breakpoint: "
          f"{sum(len(c['delta_double_labelled']) for c in cells)}")
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
