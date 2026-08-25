#!/usr/bin/env python3
"""B2-12 — `thin` vs reliability semantic-collision guard for the R3B.2 candidate.

Sol FINAL CONTINUATION HANDOFF §5, B2-12: `coverage.n_thin == 48` (the
GATE-DROPPED count, omitted from `subsectors[]` entirely — R3B1-07's coverage
sentence) and `subsectors[].reliability == "low"` (an IN-TABLE flag on rows
that DID pass the gate) are two different producer paths and may not collapse
onto one customer term (DA1-02). The low-reliability chip keeps its own term,
**Low confidence / 低置信度**; the word "thin"/"稀疏" is reserved for the
coverage sentence alone.

Three assertions, all resolved from the PAINTED (rendered, language-resolved)
Confluence DOM, never from source grep:

  1. Every `.r3-thin[data-r3b2="12"]` chip's paired accessible name
     (`.r3-vh` sibling) reads exactly "Low confidence" / "低置信度". Census
     asserted NONZERO — a check that passes over an empty selector set is the
     failure class this program forbids.
  2. The R3B1-07 coverage sentence (`[data-r3b1="07"]`) still carries its
     exact 48-omitted semantics: the gate-dropped count (48) and the
     "too thin to time and are omitted from the timed table" / native ZH
     clause, unchanged.
  3. The word "thin"/"稀疏" appears ONLY inside that one coverage-sentence
     container on the Confluence view — nowhere else in the painted text,
     in particular not on the reliability chip.

Usage:
    <playwright-python> thin_reliability_audit.py [--json OUT.json]
Exit 0 iff all three hold in both EN and ZH.
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

CHIP_TERM = {"en": "Low confidence", "zh": "低置信度"}
THIN_WORD = {"en": "thin", "zh": "稀疏"}
EXPECTED_N_THIN = 48
COVERAGE_CLAUSE = {
    "en": "are too thin to time and are omitted from the timed table",
    "zh": "无法计时，未列入下方计时表",
}

MEASURE_JS = r"""
() => {
  function visText(root){
    var out = '';
    function walk(n){
      for (var i = 0; i < n.childNodes.length; i++){
        var c = n.childNodes[i];
        if (c.nodeType === 3){ out += c.textContent; continue; }
        if (c.nodeType !== 1) continue;
        if (getComputedStyle(c).display === 'none') continue;
        walk(c);
      }
    }
    walk(root);
    return out.replace(/\s+/g, ' ').trim();
  }
  var host = document.querySelector('.si-view[data-view="confluence"]');
  if (!host) return null;

  // 1 · every reliability chip's accessible name
  var chips = [...host.querySelectorAll('.r3-thin[data-r3b2="12"]')];
  var chipNames = chips.map(function(dot){
    var vh = dot.nextElementSibling;
    return (vh && vh.classList.contains('r3-vh')) ? visText(vh) : null;
  });

  // 2 · the R3B1-07 coverage sentence
  var covHost = host.querySelector('[data-r3b1="07"]');
  var covText = covHost ? visText(covHost) : null;

  // 3 · every painted text node in the confluence view, for the "thin"/稀疏
  //     word census (excluding aria-hidden and .r3-vh -clipped nodes are
  //     INCLUDED here deliberately -- .r3-vh IS the chip's accessible name
  //     carrier and must be swept too, so a reintroduced "Thin data" chip
  //     cannot hide behind visual clipping).
  var walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
  var hits = [];
  var n;
  while ((n = walker.nextNode())) {
    var txt = (n.textContent || '').trim();
    if (!txt) continue;
    var el = n.parentElement;
    if (!el) continue;
    var cs = getComputedStyle(el);
    if (cs.display === 'none') continue;
    if (el.getAttribute('aria-hidden') === 'true') continue;
    hits.push({ text: txt, cls: (el.getAttribute('class') || ''), inCoverage: !!el.closest('[data-r3b1="07"]') });
  }
  return { chipNames: chipNames, chipCensus: chips.length, covText: covText, textNodes: hits };
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
    page.evaluate(
        "()=>{var b=document.querySelector('.si-view-btn[data-view=\"confluence\"]');"
        "if(b)b.click();else location.hash='#confluence';}"
    )
    page.wait_for_timeout(700)


def evaluate_cell(lang: str, m: dict) -> list[str]:
    fails: list[str] = []
    term = CHIP_TERM[lang]
    thin = THIN_WORD[lang]

    # 1 · chip census + accessible name
    if not m["chipCensus"]:
        fails.append(f"[{lang}] chip-census: EMPTY (zero .r3-thin[data-r3b2=\"12\"] found)")
    else:
        bad = [n for n in m["chipNames"] if n != term]
        if bad:
            fails.append(f"[{lang}] chip-name: bad values {bad!r}, want all {term!r} "
                         f"({len(m['chipNames'])} chips)")

    # 2 · coverage sentence semantics
    if not m["covText"]:
        fails.append(f"[{lang}] coverage-sentence: EMPTY (zero census — [data-r3b1=\"07\"] not found/empty)")
    else:
        if str(EXPECTED_N_THIN) not in m["covText"]:
            fails.append(f"[{lang}] coverage-sentence: missing count {EXPECTED_N_THIN!r} in {m['covText']!r}")
        clause = COVERAGE_CLAUSE[lang]
        if clause not in m["covText"]:
            fails.append(f"[{lang}] coverage-sentence: missing clause {clause!r} in {m['covText']!r}")

    # 3 · "thin"/"稀疏" appears ONLY inside the coverage-sentence container
    outside = []
    inside_count = 0
    for node in m["textNodes"]:
        text = node["text"]
        hay = text.lower() if lang == "en" else text
        needle = thin.lower() if lang == "en" else thin
        if needle in hay:
            if node["inCoverage"]:
                inside_count += 1
            else:
                outside.append(node)
    if inside_count == 0:
        fails.append(f"[{lang}] thin-word-census: EMPTY — {thin!r} not found even inside the coverage sentence")
    if outside:
        fails.append(f"[{lang}] thin-word-collision: {thin!r} painted OUTSIDE the coverage sentence: "
                     f"{[(n['text'][:60], n['cls'][:40]) for n in outside]}")

    return fails


def run_audit(candidate: Path) -> tuple[bool, dict]:
    url = candidate.as_uri()
    cells = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for lang in ("en", "zh"):
            ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = ctx.new_page()
            _goto_and_setlang(page, url, lang)
            m = page.evaluate(MEASURE_JS)
            fails = evaluate_cell(lang, m) if m else [f"[{lang}] confluence view not found"]
            cells.append({"lang": lang, "measure": m, "failures": fails})
            ctx.close()
        browser.close()

    ok = bool(cells) and all(not c["failures"] for c in cells) and all(c["measure"] for c in cells)
    report = {
        "schema": "mastermind.r3b2.thin_reliability_audit.v1",
        "candidate": candidate.name,
        "chip_term": CHIP_TERM,
        "thin_word": THIN_WORD,
        "expected_n_thin": EXPECTED_N_THIN,
        "cells": cells,
        "pass": ok,
    }
    return ok, report


# ── mutation proof: restore "Thin data" on the reliability chip ─────────────
MUTATE_TARGET = "L('Low confidence', '低置信度')"
MUTATE_REPLACEMENT = "L('Thin data \\u2014 read with caution', '\\u6570\\u636e\\u7a00\\u758f \\u2014 \\u8bf7\\u8c28\\u614e\\u89e3\\u8bfb')"


def run_mutation(candidate: Path, out_md: Path) -> bool:
    import tempfile

    html = candidate.read_text(encoding="utf-8")
    n = html.count(MUTATE_TARGET)
    if n != 1:
        print(f"[thin-mutate] FAIL: expected exactly 1 occurrence of the chip-label anchor, "
              f"found {n}", file=sys.stderr)
        return False
    mutated = html.replace(MUTATE_TARGET, MUTATE_REPLACEMENT, 1)
    assert mutated != html

    with tempfile.TemporaryDirectory(prefix="r3b2_thin_mutation_") as tmp:
        mutated_path = Path(tmp) / "mutated_candidate.html"
        mutated_path.write_text(mutated, encoding="utf-8")

        print("=== baseline: pristine candidate must be fully GREEN ===")
        base_ok, base_report = run_audit(candidate)
        base_fail_count = sum(len(c["failures"]) for c in base_report["cells"])
        print(f"[{'PASS' if base_ok else 'FAIL'}] pristine baseline green — "
              f"{base_fail_count} failing assertion(s)")

        print("\n=== mutation: restore 'Thin data' on the reliability chip ===")
        mut_ok, mut_report = run_audit(mutated_path)
        all_fails = [f for c in mut_report["cells"] for f in c["failures"]]
        # every fail must be a chip-name or thin-word-collision fail (the two
        # assertions this exact mutation should trip); zero collateral on the
        # coverage-sentence assertion, which the mutation never touches.
        collateral = [f for f in all_fails if "coverage-sentence:" in f]
        relevant = [f for f in all_fails if "chip-name" in f or "thin-word-collision" in f]
        unique_kill = bool(relevant) and not collateral and not mut_ok

    ok = base_ok and unique_kill
    lines = [
        "# B2-12 thin_reliability_audit.py — mutation proof\n",
        "Mutation target: `L('Low confidence', '低置信度')` — the ONLY occurrence in the "
        "built candidate — restored to the withdrawn `Thin data \\u2014 read with caution / "
        "数据稀疏 \\u2014 请谨慎解读` chip label. Applied to an in-memory COPY inside a "
        "throwaway temp directory; the real proposal file is never touched.\n",
        f"**Pristine baseline green:** {'YES' if base_ok else 'NO — SEE ABOVE'} "
        f"({base_fail_count} failing assertions)\n",
        f"**Mutation produced a unique red (chip-name / thin-word-collision only, "
        f"zero coverage-sentence collateral):** {'YES' if unique_kill else 'NO'}\n",
        "\n## Mutated-copy failing assertions\n",
    ]
    for f in all_fails:
        lines.append(f"- {f}\n")
    if not all_fails:
        lines.append("(none — BUG: mutation was not detected)\n")
    out_md.write_text("".join(lines), encoding="utf-8")
    print(f"\n[thin-mutate] report -> {out_md}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(CANDIDATE))
    ap.add_argument("--json", default=str(BUILD / "thin_reliability_audit.json"))
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--mutate-out", default=str(BUILD / "B2_12_THIN_RELIABILITY_MUTATION.md"))
    args = ap.parse_args()

    candidate = Path(args.candidate)
    if not candidate.exists():
        print(f"[thin] missing candidate: {candidate}", file=sys.stderr)
        return 2

    if args.mutate:
        ok = run_mutation(candidate, Path(args.mutate_out))
        return 0 if ok else 1

    ok, report = run_audit(candidate)
    Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for cell in report["cells"]:
        m = cell["measure"] or {}
        print(f"[thin] {cell['lang']}: chip_census={m.get('chipCensus')} "
              f"chip_names={m.get('chipNames')} cov_text={(m.get('covText') or '')[:90]!r}")
        for f in cell["failures"]:
            print(f"[thin] FAIL {f}")

    n_fail = sum(len(c["failures"]) for c in report["cells"])
    print(f"[thin] {len(report['cells'])} cells (en/zh), {n_fail} failing assertion(s)")
    print(f"[thin] json → {args.json}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
