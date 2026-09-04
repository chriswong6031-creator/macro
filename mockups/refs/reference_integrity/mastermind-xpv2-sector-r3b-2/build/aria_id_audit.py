#!/usr/bin/env python3
"""R3B1-12 — duplicate-ID and ARIA-reference audit for the R3B.1 candidate.

Two gates, both document-wide and both run against the RENDERED DOM rather than
the static bytes, because most of this artifact's ARIA is minted by its view
partials at runtime:

  * every `id` in the document is unique;
  * every IDREF in `aria-controls` / `aria-labelledby` / `aria-describedby` /
    `aria-owns` / `aria-flowto` / `aria-errormessage` / `for` / `form`
    resolves to exactly one element.

Both are evaluated in EN and ZH and after a view repaint, because language and
view changes re-render most of the ARIA-bearing markup: an audit taken only on
the boot view in one language cannot see an id minted by the other five.

Usage:
    <playwright-python> aria_id_audit.py [--json OUT.json]
Exit 0 when both gates are clean, 1 otherwise.
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

AUDIT_JS = r"""
() => {
  const IDREF_SINGLE = ['aria-activedescendant', 'aria-errormessage', 'form'];
  const IDREF_LIST = ['aria-controls', 'aria-labelledby', 'aria-describedby',
                      'aria-owns', 'aria-flowto', 'aria-details', 'for'];
  // duplicate ids
  const counts = {};
  document.querySelectorAll('[id]').forEach(el => {
    const v = el.id;
    if (!v) return;
    counts[v] = (counts[v] || 0) + 1;
  });
  const dupes = Object.entries(counts).filter(([, n]) => n > 1)
    .map(([id, n]) => ({ id, count: n }));

  // aria references
  const broken = [];
  const resolved = [];
  const all = IDREF_SINGLE.concat(IDREF_LIST);
  document.querySelectorAll('*').forEach(el => {
    for (const attr of all) {
      if (!el.hasAttribute(attr)) continue;
      const raw = (el.getAttribute(attr) || '').trim();
      if (!raw) continue;
      // `for`/`form` only carry IDREFs on the elements that define them
      if (attr === 'for' && !['label', 'output'].includes(el.tagName.toLowerCase())) continue;
      const ids = IDREF_LIST.includes(attr) ? raw.split(/\s+/) : [raw];
      for (const id of ids) {
        if (!id) continue;
        const n = document.querySelectorAll('[id="' + CSS.escape(id) + '"]').length;
        const rec = { attr, id, matches: n, on: el.tagName.toLowerCase() + '.' + (el.className || '').toString().slice(0, 40) };
        if (n === 1) resolved.push(rec); else broken.push(rec);
      }
    }
  });
  return { total_ids: document.querySelectorAll('[id]').length, dupes, broken,
           resolved_count: resolved.length, resolved };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(BUILD / "lane_crops_b" / "aria_id_audit.json"))
    args = ap.parse_args()

    if not CANDIDATE.exists():
        print(f"[aria-id] missing candidate: {CANDIDATE}", file=sys.stderr)
        return 2

    url = CANDIDATE.as_uri()
    report = []
    bad = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for lang in LANGS:
            ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = ctx.new_page()
            page.goto(url, wait_until="load")
            page.wait_for_timeout(1200)
            page.evaluate(
                "(l)=>{ if(window.REF&&REF.setLang) REF.setLang(l);"
                " else { document.documentElement.setAttribute('data-lang',l);"
                " document.dispatchEvent(new CustomEvent('langchange')); } }",
                lang,
            )
            page.wait_for_timeout(400)
            # touch every view so lazily-mounted ARIA exists before the audit
            for view in VIEWS:
                page.evaluate(
                    "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
                    "if(b)b.click();else location.hash='#'+v;}",
                    view,
                )
                page.wait_for_timeout(500)
            res = page.evaluate(AUDIT_JS)
            res["lang"] = lang
            report.append(res)
            n_dupe = len(res["dupes"])
            n_broken = len(res["broken"])
            bad += n_dupe + n_broken
            print(f"[aria-id] lang={lang}: {res['total_ids']} ids, "
                  f"{n_dupe} duplicated, {res['resolved_count']} ARIA/label references resolved, "
                  f"{n_broken} unresolved")
            for d in res["dupes"]:
                print(f"    DUPLICATE id={d['id']!r} x{d['count']}")
            for b in res["broken"]:
                print(f"    UNRESOLVED {b['attr']}={b['id']!r} -> {b['matches']} match(es)  on {b['on']}")
            ctx.close()
        browser.close()

    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[aria-id] json → {out}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
