#!/usr/bin/env python3
"""B2-13 — methodology-receipt `aria-controls` census for the R3B.2 candidate.

Sol FINAL CONTINUATION HANDOFF §5, B2-13 (PRC1R-001): every control that owns
`aria-expanded`/`aria-collapsed` state for the ONE shared `div#r3-receipt`
disclosure panel must name it via `aria-controls="r3-receipt"`. Plain
`aria-expanded` with no `aria-controls` is not invalid ARIA, so
`aria_id_audit.py` (R3B1-12's duplicate-ID / broken-IDREF sweep) cannot see
it — it audits references that EXIST, never references that are MISSING.
This guard closes that exact blind spot.

Document-wide, RENDERED DOM (not static source grep — most of this artifact's
controls are minted by view partials at runtime), across every view and both
languages:

  1. CENSUS every `[aria-expanded]` control in the built candidate — asserted
     NONZERO (a check that passes over an empty selector set is the failure
     class this program forbids).
  2. Of those, the subset that drives the SHARED `#r3-receipt` panel — the
     `[data-r3b1="02"]` Overview caveat button plus the three `[data-r3b1="08"]`
     Moving controls — is censused separately and expected to be exactly 4;
     every one of them must carry `aria-controls="r3-receipt"`, and the target
     `#r3-receipt` element must exist exactly once in the document.

Usage:
    <playwright-python> aria_receipt_audit.py [--json OUT.json]
Exit 0 iff both hold, across every view, in both EN and ZH.
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

EXPECTED_SHARED_PANEL_CONTROLS = 4  # [data-r3b1="02"] x1 + [data-r3b1="08"] x3
RECEIPT_ID = "r3-receipt"

AUDIT_JS = r"""
() => {
  var all = [...document.querySelectorAll('[aria-expanded]')];
  var census = all.length;
  // the "02" marker sits on the WRAPPING <p data-r3b1="02"> (the button
  // itself carries no data-r3b1), while the "08" marker sits directly on
  // each <button data-r3b1="08">; a control drives the shared panel if it
  // (or an ancestor) carries either marker.
  var shared = all.filter(function(el){
    return el.getAttribute('data-r3b1') === '08' || !!el.closest('[data-r3b1="02"]');
  });
  var sharedRows = shared.map(function(el){
    var marker = el.getAttribute('data-r3b1') || (el.closest('[data-r3b1="02"]') ? '02' : null);
    return {
      marker: marker,
      cls: (el.getAttribute('class') || '').slice(0, 60),
      ariaControls: el.getAttribute('aria-controls'),
    };
  });
  var panelCount = document.querySelectorAll('#' + CSS.escape('r3-receipt')).length;
  return { census: census, sharedCensus: shared.length, sharedRows: sharedRows, panelCount: panelCount };
}
"""


def _goto_and_setlang(page, url: str, lang: str) -> None:
    page.goto(url, wait_until="load")
    page.wait_for_timeout(1200)
    page.evaluate(
        "(l)=>{ if(window.REF&&REF.setLang) REF.setLang(l);"
        " else { document.documentElement.setAttribute('data-lang',l);"
        " document.dispatchEvent(new CustomEvent('langchange')); } }",
        lang,
    )
    page.wait_for_timeout(400)


def evaluate_cell(lang: str, m: dict) -> list[str]:
    fails: list[str] = []
    if not m["census"]:
        fails.append(f"[{lang}] aria-expanded-census: EMPTY (zero [aria-expanded] controls found)")
    if m["sharedCensus"] != EXPECTED_SHARED_PANEL_CONTROLS:
        fails.append(f"[{lang}] shared-panel-census: {m['sharedCensus']} != expected "
                     f"{EXPECTED_SHARED_PANEL_CONTROLS} — rows={m['sharedRows']}")
    bad = [r for r in m["sharedRows"] if r["ariaControls"] != RECEIPT_ID]
    if bad:
        fails.append(f"[{lang}] shared-panel-wiring: {len(bad)} control(s) missing "
                     f"aria-controls=\"{RECEIPT_ID}\": {bad}")
    if m["panelCount"] != 1:
        fails.append(f"[{lang}] shared-panel-target: #r3-receipt found {m['panelCount']} times, want 1")
    return fails


def run_audit(candidate: Path) -> tuple[bool, dict]:
    url = candidate.as_uri()
    cells = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for lang in LANGS:
            ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = ctx.new_page()
            _goto_and_setlang(page, url, lang)
            # touch every view so lazily-mounted controls (Moving's r3-tr-help
            # buttons render only once a trace record body is painted) exist
            # before the census runs.
            for view in VIEWS:
                page.evaluate(
                    "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
                    "if(b)b.click();else location.hash='#'+v;}",
                    view,
                )
                page.wait_for_timeout(600)
            m = page.evaluate(AUDIT_JS)
            fails = evaluate_cell(lang, m)
            cells.append({"lang": lang, "measure": m, "failures": fails})
            ctx.close()
        browser.close()

    ok = bool(cells) and all(not c["failures"] for c in cells)
    report = {
        "schema": "mastermind.r3b2.aria_receipt_audit.v1",
        "candidate": candidate.name,
        "expected_shared_panel_controls": EXPECTED_SHARED_PANEL_CONTROLS,
        "receipt_id": RECEIPT_ID,
        "cells": cells,
        "pass": ok,
    }
    return ok, report


# ── mutation proof: strip aria-controls from the [data-r3b1="02"] button ────
MUTATE_TARGET = "' aria-controls=\"r3-receipt\"'"


def run_mutation(candidate: Path, out_md: Path) -> bool:
    import tempfile

    html = candidate.read_text(encoding="utf-8")
    n = html.count(MUTATE_TARGET)
    if n != 1:
        print(f"[aria-receipt-mutate] FAIL: expected exactly 1 occurrence of the literal "
              f"aria-controls anchor (the [data-r3b1=\"02\"] button), found {n}", file=sys.stderr)
        return False
    mutated = html.replace(MUTATE_TARGET, "''", 1)
    assert mutated != html

    with tempfile.TemporaryDirectory(prefix="r3b2_aria_receipt_mutation_") as tmp:
        mutated_path = Path(tmp) / "mutated_candidate.html"
        mutated_path.write_text(mutated, encoding="utf-8")

        print("=== baseline: pristine candidate must be fully GREEN ===")
        base_ok, base_report = run_audit(candidate)
        base_fail_count = sum(len(c["failures"]) for c in base_report["cells"])
        print(f"[{'PASS' if base_ok else 'FAIL'}] pristine baseline green — "
              f"{base_fail_count} failing assertion(s)")

        print("\n=== mutation: strip aria-controls from the [data-r3b1=\"02\"] button ===")
        mut_ok, mut_report = run_audit(mutated_path)
        all_fails = [f for c in mut_report["cells"] for f in c["failures"]]
        wiring_fails = [f for f in all_fails if "shared-panel-wiring" in f]
        collateral = [f for f in all_fails
                      if "shared-panel-wiring" not in f
                      and "aria-expanded-census" not in f]  # census stays nonzero (control still exists)
        unique_kill = bool(wiring_fails) and not collateral and not mut_ok

    ok = base_ok and unique_kill
    lines = [
        "# B2-13 aria_receipt_audit.py — mutation proof\n",
        "Mutation target: the literal `aria-controls=\"r3-receipt\"` on the "
        "`[data-r3b1=\"02\"]` Overview methodology button — the ONLY literal (non-"
        "variable-built) occurrence in the built candidate. Applied to an in-memory "
        "COPY inside a throwaway temp directory; the real proposal file is never "
        "touched.\n",
        f"**Pristine baseline green:** {'YES' if base_ok else 'NO — SEE ABOVE'} "
        f"({base_fail_count} failing assertions)\n",
        f"**Mutation produced a unique red (shared-panel-wiring only):** "
        f"{'YES' if unique_kill else 'NO'}\n",
        "\n## Mutated-copy failing assertions\n",
    ]
    for f in all_fails:
        lines.append(f"- {f}\n")
    if not all_fails:
        lines.append("(none — BUG: mutation was not detected)\n")
    out_md.write_text("".join(lines), encoding="utf-8")
    print(f"\n[aria-receipt-mutate] report -> {out_md}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(CANDIDATE))
    ap.add_argument("--json", default=str(BUILD / "aria_receipt_audit.json"))
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--mutate-out", default=str(BUILD / "B2_13_ARIA_RECEIPT_MUTATION.md"))
    args = ap.parse_args()

    candidate = Path(args.candidate)
    if not candidate.exists():
        print(f"[aria-receipt] missing candidate: {candidate}", file=sys.stderr)
        return 2

    if args.mutate:
        ok = run_mutation(candidate, Path(args.mutate_out))
        return 0 if ok else 1

    ok, report = run_audit(candidate)
    Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for cell in report["cells"]:
        m = cell["measure"]
        print(f"[aria-receipt] {cell['lang']}: census={m['census']} shared_census={m['sharedCensus']} "
              f"panel_count={m['panelCount']} rows={m['sharedRows']}")
        for f in cell["failures"]:
            print(f"[aria-receipt] FAIL {f}")

    n_fail = sum(len(c["failures"]) for c in report["cells"])
    print(f"[aria-receipt] {len(report['cells'])} cells (en/zh), {n_fail} failing assertion(s)")
    print(f"[aria-receipt] json → {args.json}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
