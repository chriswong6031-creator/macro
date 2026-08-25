#!/usr/bin/env python3
"""B2-01 — producer-path -> customer-label map audit for the R3B.2 candidate.

Sol FINAL CONTINUATION HANDOFF §5, B2-01: "one producer measure, one customer
term." `theme_intel.themes[].score` must read exactly **Strength / 强度** on
EVERY surface that paints it, and nowhere else under a second, softer synonym
("Score / 评分" — production's own :2991 wording, and R3B1-06's withdrawn
carve-out). The two genuinely DIFFERENT producer measures that happen to share
the English word "Conviction" — `conviction.score` (Overview trace card) and
`double_gated.double_buy[].combined_score` (Confluence picks) — keep their own
distinct labels (Conviction / 信心, Conviction / 综合把握 respectively) and are
censused here too, so a future edit cannot silently collapse THOSE onto
Strength either.

Labels are resolved from the PAINTED (rendered, language-resolved) DOM, never
from static source grep: this build deliberately keeps retired strings
("Score / 评分") alive in shipped source comments as an audit trail (Lane A
warning), so a grep-based guard would false-positive on comment text that no
customer ever sees.

Six known sites bound to `theme_intel.themes[].score`:
  1. overview action-board legend   — `.r3-colfig[data-r3b1="11"][data-r3b2="01"]`
  2. overview action-board row caption — `.r3-figlab[data-r3b2="05"]` (Overview)
  3. map text-equivalent table header — `th[data-r3b1="06"]`
  4. map scatter tooltip             — `#r3-map-tip` (after hover)
  5. map selected-object dt          — 3rd `dt` in `#r3-map-detail dl` (after click)
  6. map text-equivalent table caption — `caption.r3-vh` (must NOT say "score"/"评分")

Two known DIFFERENT-producer sites, censused for the opposite invariant (they
must NOT collapse onto Strength):
  7. overview trace-card fact        — `.si-trace-k` == "Conviction"/"信心"
  8. confluence picks column         — header + row caption == "Conviction"/"综合把握"

Usage:
    <playwright-python> label_map_audit.py [--json OUT.json]
Exit 0 iff all six Strength/强度 sites read exactly that term (nonzero census)
and both distinct-producer sites are present with their own distinct term.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BUILD = Path(__file__).resolve().parent
CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"

TERM = {"en": "Strength", "zh": "强度"}
BAD_TERM = {"en": "score", "zh": "评分"}  # the withdrawn synonym — must appear nowhere in these sites
CONVICTION_OVERVIEW = {"en": "Conviction", "zh": "信心"}
CONVICTION_CONFLUENCE = {"en": "Conviction", "zh": "综合把握"}

VIS_TEXT_DECL = r"""
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
"""

MEASURE_OVERVIEW_JS = r"""
() => {
""" + VIS_TEXT_DECL + r"""
  var legend = document.querySelector('[data-view="overview"] .r3-colfig[data-r3b1="11"][data-r3b2="01"]');
  var legendText = null;
  if (legend) {
    var clone = legend.cloneNode(true);
    var src = [...legend.querySelectorAll('*')], dst = [...clone.querySelectorAll('*')];
    src.forEach((s, i) => { if (getComputedStyle(s).display === 'none') dst[i].remove(); });
    clone.querySelectorAll('em').forEach(function(n){ n.remove(); });
    legendText = visText(clone);
  }
  var rowCaptions = [...document.querySelectorAll('[data-view="overview"] .r3-fig .r3-figlab[data-r3b2="05"]')]
    .map(function(el){ return visText(el); })
    .filter(function(t){ return t.length > 0; });
  return { legendText: legendText, rowCaptions: rowCaptions };
}
"""

MEASURE_MAP_STATIC_JS = r"""
() => {
""" + VIS_TEXT_DECL + r"""
  var th = document.querySelector('[data-view="map"] th[data-r3b1="06"]');
  var thText = th ? visText(th) : null;
  var cap = document.querySelector('[data-view="map"] caption.r3-vh');
  var capText = cap ? visText(cap) : null;
  return { thText: thText, capText: capText };
}
"""

TOOLTIP_JS = r"""
() => {
""" + VIS_TEXT_DECL + r"""
  var tip = document.querySelector('#r3-map-tip');
  return tip ? visText(tip) : null;
}
"""

DETAIL_JS = r"""
() => {
""" + VIS_TEXT_DECL + r"""
  var dl = document.querySelector('#r3-map-detail .r3-selstats');
  if (!dl) return { dts: [], site5: null };
  var dts = [...dl.querySelectorAll('dt')].map(function(el){ return visText(el); });
  return { dts: dts, site5: dts.length > 2 ? dts[2] : null };
}
"""

TRACE_JS = r"""
() => {
""" + VIS_TEXT_DECL + r"""
  var trace = document.querySelector('.si-trace');
  if (!trace) return null;
  var ks = [...trace.querySelectorAll('.si-trace-k')].map(function(el){ return visText(el); });
  var vs = [...trace.querySelectorAll('.si-trace-v')].map(function(el){ return visText(el); });
  return { keys: ks, values: vs };
}
"""

CONFLUENCE_JS = r"""
() => {
""" + VIS_TEXT_DECL + r"""
  var colsHost = document.querySelector('[data-view="confluence"] .r3-cols[data-r3b1="13"]');
  var hdr = colsHost ? colsHost.querySelectorAll(':scope > span')[1] : null;
  var hdrText = hdr ? visText(hdr) : null;
  var rowLabels = [...document.querySelectorAll('[data-view="confluence"] #cf-picks .r3-fig .r3-figlab[data-r3b2="05"]')]
    .map(function(el){ return visText(el); })
    .filter(function(t){ return t.length > 0; });
  return { hdrText: hdrText, rowLabels: rowLabels };
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


def _click_view(page, view: str) -> None:
    page.evaluate(
        "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
        "if(b)b.click();else location.hash='#'+v;}",
        view,
    )
    page.wait_for_timeout(650)


def measure_lang(page, url: str, lang: str, verbose: bool) -> dict:
    _goto_and_setlang(page, url, lang)

    # ── sites 1-2: overview ──────────────────────────────────────────────
    _click_view(page, "overview")
    ov = page.evaluate(MEASURE_OVERVIEW_JS)

    # ── sites 3, 6: map static text ──────────────────────────────────────
    _click_view(page, "map")
    map_static = page.evaluate(MEASURE_MAP_STATIC_JS)

    # ── site 4: scatter tooltip (hover a dot) ────────────────────────────
    dot = page.query_selector("circle.r3-dot")
    tip_text = None
    if dot:
        dot.hover()
        page.wait_for_timeout(300)
        tip_text = page.evaluate(TOOLTIP_JS)

    # ── site 5: selected-object dt (click a dot) ─────────────────────────
    detail = {"dts": [], "site5": None}
    if dot:
        dot.click()
        page.wait_for_timeout(300)
        detail = page.evaluate(DETAIL_JS)

    # ── site 7: overview trace card (Conviction / 信心), best-effort ─────
    _click_view(page, "overview")
    trace = None
    rows = page.query_selector_all("#actnow a.rvx-trow")
    for i in range(min(len(rows), 8)):
        r = page.query_selector_all("#actnow a.rvx-trow")
        if i >= len(r):
            break
        r[i].click()
        page.wait_for_timeout(250)
        t = page.evaluate(TRACE_JS)
        if t and any(k.lower().startswith("conviction") or "信心" in k for k in t["keys"]):
            trace = t
            break

    # ── site 8: confluence picks (Conviction / 综合把握) ─────────────────
    _click_view(page, "confluence")
    page.wait_for_timeout(300)
    confluence = page.evaluate(CONFLUENCE_JS)

    result = {
        "lang": lang,
        "legend": ov["legendText"],
        "row_captions": ov["rowCaptions"],
        "texteq_th": map_static["thText"],
        "vh_caption": map_static["capText"],
        "scatter_tooltip": tip_text,
        "selected_dts": detail["dts"],
        "selected_dt_site5": detail["site5"],
        "trace_conviction": trace,
        "confluence_header": confluence["hdrText"],
        "confluence_row_labels": confluence["rowLabels"],
    }
    if verbose:
        print(f"[label-map] {lang}: {json.dumps(result, ensure_ascii=False)}")
    return result


def evaluate_cell(cell: dict) -> list[str]:
    """Return a list of failure strings, each naming the failing site."""
    lang = cell["lang"]
    term = TERM[lang]
    bad = BAD_TERM[lang]
    fails: list[str] = []

    # site 1: legend
    if not cell["legend"]:
        fails.append(f"[{lang}] site1 overview-legend: EMPTY (zero census)")
    elif cell["legend"] != term:
        fails.append(f"[{lang}] site1 overview-legend: got {cell['legend']!r}, want {term!r}")

    # site 2: row captions — nonzero census, every one exactly the term
    if not cell["row_captions"]:
        fails.append(f"[{lang}] site2 overview-row-caption: EMPTY (zero census)")
    else:
        bad_rows = [t for t in cell["row_captions"] if t != term]
        if bad_rows:
            fails.append(f"[{lang}] site2 overview-row-caption: bad values {bad_rows!r}, want all {term!r}")

    # site 3: map text-equiv th
    if not cell["texteq_th"]:
        fails.append(f"[{lang}] site3 map-texteq-th: EMPTY (zero census)")
    elif cell["texteq_th"] != term:
        fails.append(f"[{lang}] site3 map-texteq-th: got {cell['texteq_th']!r}, want {term!r}")

    # site 4: scatter tooltip — contains the term, not the bad synonym
    if not cell["scatter_tooltip"]:
        fails.append(f"[{lang}] site4 map-scatter-tooltip: EMPTY (zero census)")
    else:
        low = cell["scatter_tooltip"].lower() if lang == "en" else cell["scatter_tooltip"]
        needle = term.lower() if lang == "en" else term
        badneedle = bad.lower() if lang == "en" else bad
        if needle not in low:
            fails.append(f"[{lang}] site4 map-scatter-tooltip: {cell['scatter_tooltip']!r} missing {term!r}")
        if badneedle in low:
            fails.append(f"[{lang}] site4 map-scatter-tooltip: {cell['scatter_tooltip']!r} contains withdrawn synonym {bad!r}")

    # site 5: selected-object dt (3rd dt in the dl)
    if not cell["selected_dt_site5"]:
        fails.append(f"[{lang}] site5 map-selected-dt: EMPTY (zero census)")
    elif cell["selected_dt_site5"] != term:
        fails.append(f"[{lang}] site5 map-selected-dt: got {cell['selected_dt_site5']!r}, want {term!r}")

    # site 6: vh caption — must mention the term and not the withdrawn synonym
    if not cell["vh_caption"]:
        fails.append(f"[{lang}] site6 map-vh-caption: EMPTY (zero census)")
    else:
        low = cell["vh_caption"].lower() if lang == "en" else cell["vh_caption"]
        needle = term.lower() if lang == "en" else term
        badneedle = bad.lower() if lang == "en" else bad
        if needle not in low:
            fails.append(f"[{lang}] site6 map-vh-caption: {cell['vh_caption']!r} missing {term!r}")
        if badneedle in low:
            fails.append(f"[{lang}] site6 map-vh-caption: {cell['vh_caption']!r} contains withdrawn synonym {bad!r}")

    # site 7: distinct producer — Overview trace card Conviction / 信心
    conv_term = CONVICTION_OVERVIEW[lang]
    if not cell["trace_conviction"]:
        fails.append(f"[{lang}] site7 overview-trace-conviction: EMPTY (zero census — no basket with conviction.score found)")
    else:
        keys = cell["trace_conviction"]["keys"]
        if conv_term not in keys:
            fails.append(f"[{lang}] site7 overview-trace-conviction: keys {keys!r} missing {conv_term!r}")

    # site 8: distinct producer — Confluence picks Conviction / 综合把握
    conv2_term = CONVICTION_CONFLUENCE[lang]
    if not cell["confluence_header"]:
        fails.append(f"[{lang}] site8 confluence-picks-header: EMPTY (zero census)")
    elif cell["confluence_header"] != conv2_term:
        fails.append(f"[{lang}] site8 confluence-picks-header: got {cell['confluence_header']!r}, want {conv2_term!r}")
    if not cell["confluence_row_labels"]:
        fails.append(f"[{lang}] site8 confluence-picks-row: EMPTY (zero census)")
    else:
        bad_rows = [t for t in cell["confluence_row_labels"] if t != conv2_term]
        if bad_rows:
            fails.append(f"[{lang}] site8 confluence-picks-row: bad values {bad_rows!r}, want all {conv2_term!r}")

    return fails


def run_audit(candidate: Path, verbose: bool = False) -> tuple[bool, dict]:
    url = candidate.as_uri()
    cells = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for lang in ("en", "zh"):
            ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = ctx.new_page()
            cell = measure_lang(page, url, lang, verbose)
            cell["failures"] = evaluate_cell(cell)
            cells.append(cell)
            ctx.close()
        browser.close()

    ok = bool(cells) and all(not c["failures"] for c in cells)
    report = {
        "schema": "mastermind.r3b2.label_map_audit.v1",
        "candidate": candidate.name,
        "term": TERM,
        "cells": cells,
        "pass": ok,
    }
    return ok, report


# ── mutation proof (item 1, mission §5 B2-01) ────────────────────────────────
# "flip ONE same-path occurrence back to Score / 评分 -> the guard must produce
# a UNIQUE red naming the site." Target: the map selected-object dt (site 5) —
# a byte-unique anchor in the built candidate (verified: html.count(target)==1).
MUTATE_TARGET = "+'<dt>'+L('Strength','强度')+'</dt><dd class=\"tnum\">'+d.score+'</dd>'"
MUTATE_REPLACEMENT = "+'<dt>'+L('Score','评分')+'</dt><dd class=\"tnum\">'+d.score+'</dd>'"


def run_mutation(candidate: Path, out_md: Path, verbose: bool) -> bool:
    import tempfile

    html = candidate.read_text(encoding="utf-8")
    n = html.count(MUTATE_TARGET)
    if n != 1:
        print(f"[label-map-mutate] FAIL: expected exactly 1 occurrence of the site-5 dt "
              f"anchor, found {n} — mutation is not well-targeted", file=sys.stderr)
        return False
    mutated = html.replace(MUTATE_TARGET, MUTATE_REPLACEMENT, 1)
    assert mutated != html

    with tempfile.TemporaryDirectory(prefix="r3b2_label_map_mutation_") as tmp:
        mutated_path = Path(tmp) / "mutated_candidate.html"
        mutated_path.write_text(mutated, encoding="utf-8")

        print("=== baseline: pristine candidate must be fully GREEN ===")
        base_ok, base_report = run_audit(candidate, verbose)
        base_fail_count = sum(len(c["failures"]) for c in base_report["cells"])
        print(f"[{'PASS' if base_ok else 'FAIL'}] pristine baseline green — "
              f"{base_fail_count} failing assertion(s)")

        print("\n=== mutation: site5 map-selected-dt Strength -> Score ===")
        mut_ok, mut_report = run_audit(mutated_path, verbose)
        all_fails = [f for c in mut_report["cells"] for f in c["failures"]]
        # every fail line must name site5 and ONLY site5 (unique kill — no
        # collateral damage to the other 7 sites)
        non_site5 = [f for f in all_fails if "site5" not in f]
        site5_fails = [f for f in all_fails if "site5" in f]
        unique_kill = bool(site5_fails) and not non_site5 and not mut_ok
        print(f"[{'PASS' if unique_kill else 'FAIL'}] mutation produced a unique red naming site5 — "
              f"site5 fails: {site5_fails}; collateral (non-site5) fails: {non_site5}")

    ok = base_ok and unique_kill
    lines = [
        "# B2-01 label_map_audit.py — mutation proof\n",
        "Mutation target: the map selected-object dt (site 5) — the ONLY byte-unique "
        "occurrence of `L('Strength','强度')` immediately followed by "
        "`</dt><dd class=\"tnum\">'+d.score+'</dd>'` in the built candidate. Applied to "
        "an in-memory COPY inside a throwaway temp directory; the real proposal file "
        "is never touched.\n",
        f"**Pristine baseline green:** {'YES' if base_ok else 'NO — SEE ABOVE'} "
        f"({base_fail_count} failing assertions)\n",
        f"**Mutation produced a unique red naming only site5:** {'YES' if unique_kill else 'NO'}\n",
        "\n## Mutated-copy failing assertions\n",
    ]
    for f in all_fails:
        lines.append(f"- {f}\n")
    if not all_fails:
        lines.append("(none — BUG: mutation was not detected)\n")
    out_md.write_text("".join(lines), encoding="utf-8")
    print(f"\n[label-map-mutate] report -> {out_md}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(CANDIDATE))
    ap.add_argument("--json", default=str(BUILD / "label_map_audit.json"))
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--mutate", action="store_true",
                     help="run the B2-01 unique-kill mutation proof instead of the plain audit")
    ap.add_argument("--mutate-out", default=str(BUILD / "B2_01_LABEL_MAP_MUTATION.md"))
    args = ap.parse_args()

    candidate = Path(args.candidate)
    if not candidate.exists():
        print(f"[label-map] missing candidate: {candidate}", file=sys.stderr)
        return 2

    if args.mutate:
        ok = run_mutation(candidate, Path(args.mutate_out), args.verbose)
        return 0 if ok else 1

    ok, report = run_audit(candidate, args.verbose)
    Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for cell in report["cells"]:
        lang = cell["lang"]
        print(f"[label-map] {lang}: site1={cell['legend']!r} site2={cell['row_captions']!r} "
              f"site3={cell['texteq_th']!r} site4={cell['scatter_tooltip']!r} "
              f"site5={cell['selected_dt_site5']!r} site6={(cell['vh_caption'] or '')[:60]!r} "
              f"site7={cell['trace_conviction']!r} site8_hdr={cell['confluence_header']!r} "
              f"site8_row={cell['confluence_row_labels']!r}")
        for f in cell["failures"]:
            print(f"[label-map] FAIL {f}")

    n_fail = sum(len(c["failures"]) for c in report["cells"])
    print(f"[label-map] {len(report['cells'])} cells (en/zh), {n_fail} failing assertion(s)")
    print(f"[label-map] json → {args.json}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
