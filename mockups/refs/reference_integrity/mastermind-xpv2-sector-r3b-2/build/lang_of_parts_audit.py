#!/usr/bin/env python3
"""B2-04 — language-of-parts audit for the R3B.2 candidate.

WHAT IT ASSERTS
---------------
Under the inherited Chinese document language (`<html lang="zh-CN" data-lang="zh">`)
no **visible** text node may carry substantial unmarked Latin prose. A Chinese
reader must never be handed an English paragraph dressed as Chinese.

"Substantial Latin prose" is defined here as a single visible text node holding
at least `--min-words` (default 8) Latin-script word tokens, of which at least
`--min-lower` (default 5) are lowercase running words of 3+ letters. That shape
is a *sentence*. It is deliberately NOT "any Latin character": the product's
Chinese surfaces legitimately carry short Latin fragments, and flagging those
would make the audit useless rather than strict.

ALLOWLIST — what is lawful Latin under ZH, and why
--------------------------------------------------
1. `[lang="en"]` subtrees and anything inside them. This is the escape hatch
   B2-04 itself sanctions: raw source-language bytes that cannot lawfully be
   projected stay English *and say so*. The audit still requires the marker to
   be explicit in the markup — an unmarked paragraph is a finding.
2. `.l-en` twins. They exist in the DOM at all times but `html[data-lang="zh"]
   .l-en{display:none}` hides them, so they are never *visible* text and the
   visibility filter removes them before any counting happens.
3. `#ref-harness` — the reference's own QA harness overlay (viewport/theme/lang
   controls, hydrate log). It is instrument chrome, not product UI, and it is
   English-only by construction. Excluded by container, and the exclusion is
   named here rather than hidden in a regex.
4. Tickers, acronyms, units and numbers survive the *word shape* test rather
   than a word list: `NEM`, `SPY`, `XLE`, `T1`, `20d`, `+11.5%`, `2026-08-06`
   and `SPDR` are uppercase / numeric / mixed tokens, so they never count
   toward the lowercase-running-word requirement. A handful of lowercase
   fragments that are genuinely identifiers rather than prose (`vs`, `d`, `bp`,
   `etf`, `spy`) are listed in LOWER_STOP below.
5. Producer proper nouns (theme, subsector, sector and company names such as
   `Gold Miners`, `Non-AI Software`) are Latin under ZH because the producer
   emits no `*_zh` twin for them. They are capitalised names, not prose, and a
   name node cannot reach 5 lowercase running words.

The audit renders every one of the six views (an unactivated view paints no
DOM), asserts a NONZERO census of scanned visible nodes — a scanner that walks
an empty selector set must fail loudly rather than report a clean sheet — and
exits nonzero on any finding.

Usage:
    <playwright-python> lang_of_parts_audit.py [--candidate PATH]
                                               [--out lane_crops_a2/LANG_OF_PARTS.txt]
Exit 0 when the census is nonzero and there are no findings, 1 otherwise.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BUILD = Path(__file__).resolve().parent
CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
VIEWS = ["overview", "map", "moving", "money", "explore", "confluence"]

# lowercase tokens that are identifiers/units rather than running words
LOWER_STOP = {
    "vs", "etf", "spy", "spx", "qqq", "bp", "bps", "yoy", "mom", "ytd",
    "eps", "pe", "usd", "cny", "hkd", "aum", "ic", "rsi", "macd", "ai",
}

WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
LOWER_WORD = re.compile(r"^[a-z][a-z'’\-]{2,}$")

# Collect every visible text node under ZH, with a compact path for the report.
COLLECT_JS = r"""
() => {
  const out = [];
  const skipTag = new Set(['SCRIPT','STYLE','TEMPLATE','NOSCRIPT','TITLE']);
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const raw = n.nodeValue;
    if (!raw || !raw.trim()) continue;
    const p = n.parentElement;
    if (!p || skipTag.has(p.tagName)) continue;
    if (p.closest('#ref-harness')) continue;          // instrument chrome, not product UI
    if (p.closest('[lang="en"]')) continue;           // sanctioned source-language marker
    if (typeof p.checkVisibility === 'function') {
      if (!p.checkVisibility({checkOpacity:true, checkVisibilityCSS:true})) continue;
    } else if (!p.offsetParent && p.tagName !== 'BODY') continue;
    const cs = getComputedStyle(p);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    // visually-hidden accessible-name spans are still *read* text: keep them.
    const view = p.closest('.si-view');
    out.push({
      text: raw.trim().replace(/\s+/g, ' '),
      view: view ? (view.getAttribute('data-view') || '?') : 'shell',
      tag: p.tagName.toLowerCase(),
      cls: (p.getAttribute('class') || '').slice(0, 60),
    });
  }
  return out;
}
"""


def latin_shape(text: str) -> tuple[int, int]:
    words = WORD.findall(text)
    lower = [w for w in words if LOWER_WORD.match(w) and w.lower() not in LOWER_STOP]
    return len(words), len(lower)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(CANDIDATE))
    ap.add_argument("--out", default=str(BUILD / "lane_crops_a2" / "LANG_OF_PARTS.txt"))
    ap.add_argument("--min-words", type=int, default=8)
    ap.add_argument("--min-lower", type=int, default=5)
    args = ap.parse_args()

    cand = Path(args.candidate)
    lines: list[str] = [f"candidate: {cand}",
                        f"rule: a visible text node under zh-CN with >={args.min_words} Latin word "
                        f"tokens AND >={args.min_lower} lowercase running words is a finding",
                        ""]
    findings: list[dict] = []
    census = 0
    seen: set[str] = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.goto(cand.as_uri(), wait_until="load")
        page.wait_for_timeout(1300)
        page.click("#ref-harness-head")
        page.select_option("#ref-lang", "zh")
        page.wait_for_timeout(600)
        doc_lang = page.evaluate("()=>document.documentElement.lang")
        lines.append(f"document language under audit: {doc_lang!r}")
        if doc_lang != "zh-CN":
            lines.append("[FAIL] the audit did not reach zh-CN; nothing below is meaningful")
            print("\n".join(lines))
            return 1

        for v in VIEWS:
            page.evaluate(
                "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
                "if(b)b.click();else location.hash='#'+v;}", v)
            page.wait_for_timeout(700)
            # open every collapsed disclosure so folded copy is scanned too
            page.evaluate("()=>{document.querySelectorAll('details').forEach(function(d){d.open=true;});}")
            page.wait_for_timeout(250)
            nodes = page.evaluate(COLLECT_JS)
            census += len(nodes)
            for nd in nodes:
                total, lower = latin_shape(nd["text"])
                if total >= args.min_words and lower >= args.min_lower:
                    key = nd["text"][:160]
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append({**nd, "words": total, "lower": lower})
        ctx.close()
        browser.close()

    lines.append(f"visible text nodes scanned (six views, disclosures opened): {census}")
    if census == 0:
        lines.append("[FAIL] census is ZERO — the scanner walked an empty selector set")
        lines.append("RESULT: FAIL")
        text = "\n".join(lines)
        print(text)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        return 1

    lines.append(f"findings: {len(findings)}")
    lines.append("")
    for f in findings:
        lines.append(f"[FINDING] view={f['view']} <{f['tag']} class=\"{f['cls']}\"> "
                     f"latin_words={f['words']} lowercase_running={f['lower']}")
        lines.append(f"          {f['text'][:300]}")
    ok = not findings and census > 0
    lines.append("")
    lines.append(f"RESULT: {'PASS' if ok else 'FAIL'}")
    text = "\n".join(lines)
    print(text)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"\n[lang-of-parts] → {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
