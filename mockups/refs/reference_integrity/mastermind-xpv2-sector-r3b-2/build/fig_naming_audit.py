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
import hashlib
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BUILD = Path(__file__).resolve().parent
DEFAULT_CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"

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
    "en": {
        "strength": ("Strength", ["76"]),
        "delta": ("20d vs market", ["+27.2%"]),
        "entry": ("Entry tier", ["T1"]),
        "conviction": ("Conviction", ["0.60", "0.54"]),
    },
    "zh": {
        "strength": ("强度", ["76"]),
        "delta": ("20日对比市场", ["+27.2%"]),
        "entry": ("入场层级", ["T1"]),
        "conviction": ("综合把握", ["0.60", "0.54"]),
    },
}

# The frozen fixture yields eleven valued Overview theme figures, one
# Confluence entry-tier figure and two Confluence conviction figures. Every
# Overview theme figure owns TWO independently named measurements: Strength and
# 20d-vs-market. A guard must census both, not let one name stand in for both.
EXPECTED_KIND_CENSUS = {
    "strength": 11,
    "delta": 11,
    "entry": 1,
    "conviction": 2,
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
  const labelInstances = [];
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

    host.querySelectorAll('.r3-figlab[data-fig-kind]').forEach((lab) => {
      const kind = lab.getAttribute('data-fig-kind');
      const carrier = kind === 'delta' ? lab.closest('.r3-delta') : lab.closest('.r3-fig');
      let valueText = '';
      if (carrier) {
        const clone = carrier.cloneNode(true);
        const src = [...carrier.querySelectorAll('*')], dst = [...clone.querySelectorAll('*')];
        src.forEach((s, i) => { if (getComputedStyle(s).display === 'none') dst[i].remove(); });
        clone.querySelectorAll('.r3-figlab, .r3-vh').forEach((n) => n.remove());
        /* Strength and delta share one `.r3-fig`; the delta owns its own nested
           carrier, so remove that child when deriving the Strength value. */
        if (kind === 'strength') clone.querySelectorAll('.r3-delta').forEach((n) => n.remove());
        valueText = (clone.textContent || '').replace(/\s+/g, ' ').trim();
      }
      labelInstances.push({
        kind: kind,
        label: visText(lab),
        value: valueText,
        label_painted: painted(lab),
        carrier_painted: carrier ? painted(carrier) : false,
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
    label_instances: labelInstances,
    header_label: headerLabel,
    legend_present: !!legend,
    legend_display: legend ? getComputedStyle(legend).display : null,
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(DEFAULT_CANDIDATE))
    ap.add_argument("--json", default=str(BUILD / "fig_naming_audit.json"))
    ap.add_argument("--widths", default=",".join(str(w) for w in WIDTHS),
                    help="comma-separated test widths; defaults to full binding sweep")
    ap.add_argument("--langs", default=",".join(LANGS),
                    help="comma-separated languages; defaults to EN/ZH")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    widths = [int(w) for w in args.widths.split(",") if w.strip()]
    langs = [lang.strip() for lang in args.langs.split(",") if lang.strip()]
    if not widths or any(w not in WIDTHS for w in widths):
        ap.error(f"--widths must be a nonempty subset of {WIDTHS}")
    if not langs or any(lang not in LANGS for lang in langs):
        ap.error(f"--langs must be a nonempty subset of {LANGS}")

    candidate = Path(args.candidate).resolve()
    if not candidate.exists():
        print(f"[fig] missing candidate: {candidate}", file=sys.stderr)
        return 2

    url = candidate.as_uri()
    cells: list[dict] = []
    findings: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for width in widths:
            for lang in langs:
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
                label_instances: list[dict] = []
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
                    label_instances.extend(r["label_instances"])
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

                # 6 · the four independently guarded figure classes.
                proofs: list[dict] = []
                kind_checks: dict[str, dict] = {}
                for kind, expected_count in EXPECTED_KIND_CENSUS.items():
                    label, values = PROOFS[lang][kind]
                    instances = [i for i in label_instances if i["kind"] == kind]
                    proof_rows = []
                    for val in values:
                        hit = any(i["label"] == label and i["value"].startswith(val)
                                  and i["carrier_painted"] for i in instances)
                        proof_rows.append({"label": label, "value": val, "pass": hit})
                        proofs.append({"kind": kind, "label": label, "value": val, "pass": hit})
                    kind_checks[kind] = {
                        "expected_census": expected_count,
                        "census": len(instances),
                        "expected_label": label,
                        "labels": sorted({i["label"] for i in instances}),
                        "painted_labels": sum(1 for i in instances if i["label_painted"]),
                        "painted_carriers": sum(1 for i in instances if i["carrier_painted"]),
                        "proofs": proof_rows,
                    }

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
                    "kind_checks": kind_checks,
                }
                cell_fail: list[str] = []
                failed_check_ids: list[str] = []
                def fail(check_id: str, detail: str) -> None:
                    failed_check_ids.append(check_id)
                    cell_fail.append(detail)
                if cell["census"] != EXPECTED_FIG_CENSUS:
                    fail("b2_05.figure.census", f"census {cell['census']} != expected {EXPECTED_FIG_CENSUS}")
                if cell["census"] == 0:
                    fail("b2_05.figure.nonzero", "zero .r3-fig found (empty selector set)")
                if cell["empty"] != EXPECTED_EMPTY:
                    fail("b2_05.figure.empty_census", f"valueless figures {cell['empty']} != expected {EXPECTED_EMPTY}")
                if unnamed:
                    fail("b2_05.figure.accessible_name", f"{len(unnamed)} valued figure(s) with no accessible name")
                if naked_visible:
                    fail("b2_05.figure.mobile_visible", f"{len(naked_visible)} painted figure(s) with no visible name at <={MOBILE_MAX}")
                if double_labelled:
                    fail("b2_05.figure.desktop_single", f"{len(double_labelled)} figure(s) painting a caption above the breakpoint")
                if label_mismatch:
                    fail("b2_05.strength.header_identity", f"inline label(s) {label_mismatch} != column header {header_label!r}")
                for kind, kc in kind_checks.items():
                    if kc["census"] != kc["expected_census"] or kc["census"] == 0:
                        fail(f"b2_05.{kind}.census",
                             f"{kind} label census {kc['census']} != expected {kc['expected_census']}")
                    if kc["labels"] != [kc["expected_label"]]:
                        fail(f"b2_05.{kind}.label",
                             f"{kind} labels {kc['labels']} != {kc['expected_label']!r}")
                    # Collapsed/folded rows are intentionally not painted. At
                    # mobile every PAINTED carrier must paint its label; above
                    # the breakpoint the shared column legend paints it instead.
                    expected_painted = kc["painted_carriers"] if mobile else 0
                    if kc["painted_labels"] != expected_painted:
                        phase = "mobile_visible" if mobile else "desktop_hidden"
                        fail(f"b2_05.{kind}.{phase}",
                             f"{kind} painted labels {kc['painted_labels']} != {expected_painted}")
                    if any(not p["pass"] for p in kc["proofs"]):
                        fail(f"b2_05.{kind}.proof",
                             f"{kind} exact value proof failed: {kc['proofs']}")
                cell["failed_check_ids"] = sorted(set(failed_check_ids))
                cell["failures"] = cell_fail
                cells.append(cell)
                if cell_fail:
                    findings.append({"width": width, "lang": lang,
                                     "failed_check_ids": cell["failed_check_ids"],
                                     "failures": cell_fail})
                if args.verbose:
                    print(f"[fig] {width}/{lang}: census={cell['census']} valued={cell['valued']} "
                          f"empty={cell['empty']} failures={len(cell_fail)}")

        browser.close()

    total_census = sum(c["census"] for c in cells)
    ok = bool(cells) and total_census > 0 and not findings
    out = {
        "schema": "mastermind.r3b2.fig_naming_audit.v1",
        "candidate": candidate.name,
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "expected_census_per_cell": EXPECTED_FIG_CENSUS,
        "expected_empty_per_cell": EXPECTED_EMPTY,
        "expected_kind_census_per_cell": EXPECTED_KIND_CENSUS,
        "mobile_breakpoint_px": MOBILE_MAX,
        "cells": cells,
        "failing_cells": findings,
        "failed_check_ids": sorted({i for f in findings for i in f["failed_check_ids"]}),
        "pass": ok,
    }
    Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[fig] {len(cells)} cells swept ({'x'.join(str(w) for w in widths)} x "
          f"{'/'.join(lang.upper() for lang in langs)}, six views each)")
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
