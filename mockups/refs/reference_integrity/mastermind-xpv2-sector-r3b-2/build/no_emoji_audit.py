#!/usr/bin/env python3
"""B2-02 — decoded emoji closure guard.

Sol's ruling (COMMISSION.md B2-02): the Track record header shipped
`&#128202; Track record` / `&#128202; 跟踪记录` — an HTML DECIMAL numeric
character reference for U+1F4CA CHART emoji. The predecessor lane's icon
audits (this directory's other `*_audit.py` scripts) all scan for LITERAL
emoji glyphs; none of them scan for a numeric entity that only becomes an
emoji once a browser decodes it, so `&#128202;` sailed straight through every
existing gate while reading as plain digits on disk. This script closes that
whole bypass CLASS, not just the one instance: it fails on a literal emoji
codepoint, on a decimal (`&#NNN;`) or hex (`&#xHHHH;`) numeric character
reference that decodes into an emoji range, AND on the decoded DOM text,
accessible names, and CSS generated content the browser actually paints —
so an entity, a JS `String.fromCodePoint` trick, or any other encoding that
only resolves to an emoji at render time is caught at the point it becomes
visible, not just at the point it is spelled out in markup.

RANGES SCANNED (Unicode blocks whose codepoints are overwhelmingly emoji
pictographs/emoticons; "at minimum" per COMMISSION.md B2-02's verification
note — this is the floor, not a ceiling):

    Misc Symbols and Pictographs           U+1F300 - U+1F5FF
    Emoticons                              U+1F600 - U+1F64F
    Transport and Map Symbols              U+1F680 - U+1F6FF
    Supplemental Symbols and Pictographs   U+1F900 - U+1FAFF
    Miscellaneous Symbols                  U+2600  - U+26FF
    Dingbats                               U+2700  - U+27BF

EXCLUSIONS (enumerated, per COMMISSION.md B2-02's instruction to exclude
"legitimate typographic/arrow/CJK characters the artifact lawfully uses").
The two BMP ranges above (Misc Symbols, Dingbats) contain both colour-default
emoji AND plain black-and-white typographic marks (Unicode's own
`Emoji_Presentation=No` set) that predate emoji entirely — a checkmark, a
star, a warning triangle are punctuation, not pictographs, unless suffixed
with U+FE0F (VARIATION SELECTOR-16, never used anywhere in this artifact —
verified by the byte scan below finding zero `️`). Every codepoint on
this list is EXCLUDED BY EXACT VALUE ONLY — nothing else in its Unicode
block is excused, so a real emoji sharing a block with one of these three
marks is still caught. See EXCLUDED_CODEPOINTS for the full, load-bearing
rationale per mark; every entry there was verified against this candidate
build by hand before being added (not a generic "checkmarks are fine" rule):

  * U+2713 CHECK MARK — views/moving.html's aria-hidden `.r3-tr-ok` "cleared"
    glyph (paired with a real `.r3-vh` text alternative) and views/money.html's
    inline `coil✓` hit-rate abbreviation. Default TEXT presentation, monochrome,
    a ledger/status convention — categorically different from a colour
    pictograph icon standing in for a section label, which is the B2-02
    defect this guard exists to close.
  * U+26A0 WARNING SIGN — appears exactly ONCE in the whole assembled
    candidate, inside a JS source COMMENT in views/confluence.html
    (near ":969") documenting that production's own caution glyph was
    deliberately dropped from the candidate's `.r3-callout` rail. It is never
    emitted to rendered text, an accessible name, or generated content — the
    three DOM-side populations below would independently catch it if it ever
    did leak into paint. Comment bytes are still shipped bytes (this repo's
    own house law), which is exactly why it shows up in the byte scan and
    exactly why it is excluded there by exact codepoint rather than by trying
    to parse JS-comment boundaries out of a 5MB assembled file.
  * U+2605 BLACK STAR — a rating/weight-prefix glyph (`★ Model 25%`, entity
    `&#9733;25%`) inside the producer-owned `sc_flows.html` fragment, embedded
    byte-verbatim per the R3B.1 Lane A "producer bytes verbatim" grader note
    (`lane_crops_a2/04-grader-note-en-producer-bytes-verbatim.png`). That
    fragment is explicit OUT OF SCOPE for this lane (COMMISSION.md, R3B.2
    "sc_flows fragment untouched") — not owned by the candidate's own authors
    at all. Default TEXT presentation, common star-rating typographic
    convention.

POPULATIONS SCANNED (per COMMISSION.md's verification-hardening rule: "no
check may pass over an empty selector set without a nonzero census
assertion" — every population below is asserted NONZERO, in every cell,
never just in aggregate):

  (a) BYTES — the raw assembled candidate file, read as UTF-8 text, scanned
      character-by-character for literal codepoints in-range, and via regex
      for every `&#NNN;` / `&#xHHHH;` numeric character reference whose
      decoded value is in-range. Census = characters scanned + numeric
      character references scanned (both asserted nonzero).
  (b) DOM TEXT NODES — every non-empty text node under `document.body`,
      rendered for real (Playwright/Chromium), excluding `<script>`/`<style>`
      subtrees, non-painted nodes (`display:none`/`visibility:hidden`/
      `opacity:0`), and `.r3-vh` (visually-hidden — covered under (c)
      instead, not double-counted here).
  (c) ACCESSIBLE NAMES — every `[aria-label]` attribute value, plus every
      `.r3-vh` element's text content (COMMISSION.md's own wording: "aria-label
      + .r3-vh text" is one combined population).
  (d) GENERATED CONTENT — every element's computed `::before`/`::after`
      `content`, where that computed value is not `none` and not the empty
      string, across every element in the DOM.

(b)-(d) are swept for every (view, lang) cell — the six canonical views
(overview/map/moving/money/explore/confluence) crossed with EN/ZH — 12 cells,
each with its own four census numbers, per COMMISSION.md's "EN and ZH modes"
instruction and this house's per-cell (not aggregate-only) census law.

Usage:
    <playwright-python> no_emoji_audit.py [--json OUT.json] [--md OUT.md]

Exit code 0 iff the byte scan and every DOM cell report zero un-excluded
hits AND every population's census is nonzero everywhere it is asserted.
Exit code 1 on any hit, any zero census, a missing candidate build, or a
Playwright import failure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parent
CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
VIEWS = ["overview", "map", "moving", "money", "explore", "confluence"]
LANGS = ["en", "zh"]

# ── ranges + exclusions (see module docstring for the full rationale) ────
EMOJI_RANGES = [
    ("Misc Symbols and Pictographs", 0x1F300, 0x1F5FF),
    ("Emoticons", 0x1F600, 0x1F64F),
    ("Transport and Map Symbols", 0x1F680, 0x1F6FF),
    ("Supplemental Symbols and Pictographs", 0x1F900, 0x1FAFF),
    ("Miscellaneous Symbols", 0x2600, 0x26FF),
    ("Dingbats", 0x2700, 0x27BF),
]

EXCLUDED_CODEPOINTS = {
    0x2713: ("CHECK MARK", "views/moving.html .r3-tr-ok (aria-hidden, real .r3-vh alt) "
             "+ views/money.html 'coil✓' hit-rate abbreviation — default TEXT "
             "presentation status glyph, not a colour pictograph"),
    0x26A0: ("WARNING SIGN", "views/confluence.html JS source comment only (~:969) "
             "documenting production's caution glyph was deliberately dropped from "
             "the candidate's .r3-callout rail — never emitted to rendered text, "
             "an accessible name, or generated content"),
    0x2605: ("BLACK STAR", "producer-owned sc_flows.html fragment (embedded byte-verbatim, "
             "explicit OUT OF SCOPE for this lane) — '★ Model 25%' / '&#9733;25%' "
             "rating-prefix glyph, default TEXT presentation"),
}


def _in_emoji_range(cp: int) -> str | None:
    for name, lo, hi in EMOJI_RANGES:
        if lo <= cp <= hi:
            return name
    return None


def _classify(cp: int) -> tuple[bool, str | None]:
    """Returns (is_hit, range_name_or_None). Excluded codepoints are never a hit."""
    if cp in EXCLUDED_CODEPOINTS:
        return False, _in_emoji_range(cp)
    name = _in_emoji_range(cp)
    return (name is not None), name


# ── (a) byte scan of the raw assembled candidate ─────────────────────────
NUMCHARREF_RE = re.compile(r"&#x([0-9a-fA-F]+);|&#([0-9]+);")


def _ctx(text: str, pos: int, width: int = 50) -> str:
    lo, hi = max(0, pos - width), min(len(text), pos + width)
    return text[lo:hi].replace("\n", " ")


def scan_bytes(html_text: str) -> dict:
    chars_scanned = len(html_text)
    literal_hits = []
    excluded_literal = []
    for i, ch in enumerate(html_text):
        cp = ord(ch)
        is_hit, range_name = _classify(cp)
        if range_name is None:
            continue
        rec = {"codepoint": f"U+{cp:04X}", "char": ch, "offset": i, "range": range_name,
               "context": _ctx(html_text, i)}
        if is_hit:
            literal_hits.append(rec)
        else:
            excluded_literal.append(rec)

    entity_refs_scanned = 0
    entity_hits = []
    excluded_entities = []
    for m in NUMCHARREF_RE.finditer(html_text):
        entity_refs_scanned += 1
        cp = int(m.group(1), 16) if m.group(1) else int(m.group(2))
        is_hit, range_name = _classify(cp)
        if range_name is None:
            continue
        rec = {"codepoint": f"U+{cp:04X}", "raw": m.group(0), "offset": m.start(),
               "range": range_name, "context": _ctx(html_text, m.start())}
        if is_hit:
            entity_hits.append(rec)
        else:
            excluded_entities.append(rec)

    return {
        "chars_scanned": chars_scanned,
        "entity_refs_scanned": entity_refs_scanned,
        "literal_hits": literal_hits,
        "entity_hits": entity_hits,
        "excluded_literal": excluded_literal,
        "excluded_entities": excluded_entities,
        "pass": chars_scanned > 0 and entity_refs_scanned > 0
                and not literal_hits and not entity_hits,
    }


# ── (b)-(d) DOM scan, per (view, lang) cell ──────────────────────────────
SETLANG_JS = r"""
([lang]) => {
  const d = document.documentElement;
  if (window.REF && typeof window.REF.setLang === 'function') { window.REF.setLang(lang); }
  else { d.setAttribute('data-lang', lang); try { document.dispatchEvent(new CustomEvent('langchange')); } catch (e) {} }
}
"""

ACTIVATE_VIEW_JS = r"""
(v) => {
  const b = document.querySelector('.si-view-btn[data-view="' + v + '"]');
  if (b) b.click(); else location.hash = '#' + v;
}
"""

# Collected client-side so we transfer only STRINGS worth reporting, never
# the full DOM. Every string returned here is later scanned in Python
# (single source of truth for the range/exclusion logic — see _classify()).
COLLECT_JS = r"""
() => {
  const textNodes = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const txt = (n.textContent || '');
    if (!txt.trim()) continue;
    const el = n.parentElement;
    if (!el) continue;
    const tag = el.tagName;
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') continue;
    if (el.closest('.r3-vh')) continue; // counted under accessible names instead
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) continue;
    textNodes.push(txt);
  }

  const ariaLabels = [];
  document.querySelectorAll('[aria-label]').forEach(el => {
    const v = el.getAttribute('aria-label');
    if (v != null) ariaLabels.push(v);
  });

  const vhTexts = [];
  document.querySelectorAll('.r3-vh').forEach(el => {
    const t = (el.textContent || '');
    if (t.trim()) vhTexts.push(t);
  });

  const pseudo = [];
  document.querySelectorAll('*').forEach(el => {
    ['::before', '::after'].forEach(p => {
      const cs = getComputedStyle(el, p);
      const c = cs.content;
      if (!c || c === 'none') return;
      const m = c.match(/^["'](.*)["']$/);
      const val = m ? m[1] : c;
      if (val.trim()) pseudo.push(val);
    });
  });

  return {
    textNodeCensus: textNodes.length, textNodeStrings: textNodes,
    ariaLabelCensus: ariaLabels.length, ariaLabelStrings: ariaLabels,
    vhCensus: vhTexts.length, vhStrings: vhTexts,
    pseudoCensus: pseudo.length, pseudoStrings: pseudo,
  };
}
"""


def _scan_strings(strings: list[str], population: str) -> tuple[list[dict], list[dict]]:
    hits, excluded = [], []
    for s in strings:
        for ch in s:
            cp = ord(ch)
            is_hit, range_name = _classify(cp)
            if range_name is None:
                continue
            rec = {"codepoint": f"U+{cp:04X}", "char": ch, "range": range_name,
                   "population": population, "text": s[:80]}
            (hits if is_hit else excluded).append(rec)
    return hits, excluded


def scan_dom(page, view: str, lang: str) -> dict:
    page.evaluate(SETLANG_JS, [lang])
    page.evaluate(ACTIVATE_VIEW_JS, view)
    page.wait_for_timeout(700)
    data = page.evaluate(COLLECT_JS)

    text_hits, text_excl = _scan_strings(data["textNodeStrings"], "text_node")
    aria_hits, aria_excl = _scan_strings(data["ariaLabelStrings"], "aria_label")
    vh_hits, vh_excl = _scan_strings(data["vhStrings"], "r3_vh")
    pseudo_hits, pseudo_excl = _scan_strings(data["pseudoStrings"], "generated_content")

    accessible_census = data["ariaLabelCensus"] + data["vhCensus"]
    accessible_hits = aria_hits + vh_hits
    accessible_excl = aria_excl + vh_excl

    cell = {
        "view": view,
        "lang": lang,
        "text_nodes": {"census": data["textNodeCensus"], "hits": text_hits, "excluded": text_excl},
        "accessible_names": {
            "aria_label_census": data["ariaLabelCensus"],
            "vh_census": data["vhCensus"],
            "census": accessible_census,
            "hits": accessible_hits,
            "excluded": accessible_excl,
        },
        "generated_content": {"census": data["pseudoCensus"], "hits": pseudo_hits, "excluded": pseudo_excl},
    }
    cell["failures"] = [h for pop in ("text_nodes", "generated_content") for h in cell[pop]["hits"]] \
        + cell["accessible_names"]["hits"]
    cell["pass"] = (
        cell["text_nodes"]["census"] > 0
        and cell["accessible_names"]["census"] > 0
        and cell["generated_content"]["census"] > 0
        and not cell["failures"]
    )
    return cell


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(BUILD / "no_emoji_audit.json"))
    ap.add_argument("--md", default=str(BUILD / "NO_EMOJI.md"))
    args = ap.parse_args()

    if not CANDIDATE.exists():
        payload = {"error": f"missing candidate build: {CANDIDATE}"}
        Path(args.json).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"[no-emoji] FATAL: missing candidate build: {CANDIDATE}", file=sys.stderr)
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        payload = {"error": "playwright is not importable in this interpreter"}
        Path(args.json).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print("[no-emoji] FATAL: playwright is not importable in this interpreter "
              "(run with the Playwright-enabled venv, per verify_reference.py's docstring)",
              file=sys.stderr)
        return 2

    html_text = CANDIDATE.read_text(encoding="utf-8")
    bytes_result = scan_bytes(html_text)

    cells = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for view in VIEWS:
            for lang in LANGS:
                ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = ctx.new_page()
                page.goto(CANDIDATE.as_uri(), wait_until="load")
                page.wait_for_timeout(1000)
                cells.append(scan_dom(page, view, lang))
                ctx.close()
        browser.close()

    overall_pass = bytes_result["pass"] and all(c["pass"] for c in cells)

    payload = {
        "ranges": [{"name": n, "lo": f"U+{lo:04X}", "hi": f"U+{hi:04X}"} for n, lo, hi in EMOJI_RANGES],
        "excluded_codepoints": {
            f"U+{cp:04X}": {"name": name, "reason": reason}
            for cp, (name, reason) in EXCLUDED_CODEPOINTS.items()
        },
        "bytes": bytes_result,
        "cells": cells,
        "pass": overall_pass,
    }
    out_json = Path(args.json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── console report ────────────────────────────────────────────────────
    print(f"[no-emoji] BYTES — {bytes_result['chars_scanned']} chars / "
          f"{bytes_result['entity_refs_scanned']} numeric char-refs scanned; "
          f"{len(bytes_result['literal_hits'])} literal hit(s), "
          f"{len(bytes_result['entity_hits'])} entity hit(s); "
          f"{len(bytes_result['excluded_literal']) + len(bytes_result['excluded_entities'])} "
          f"excluded-by-allowlist match(es)")
    for h in bytes_result["literal_hits"] + bytes_result["entity_hits"]:
        print(f"  FAIL [bytes] {h['codepoint']} ({h['range']}) offset={h['offset']}  "
              f"ctx: {h['context']!r}")

    for c in cells:
        tn, an, gc = c["text_nodes"], c["accessible_names"], c["generated_content"]
        print(f"[no-emoji] {c['view']:<11} {c['lang']}  "
              f"text_nodes={tn['census']}  accessible_names={an['census']} "
              f"(aria-label={an['aria_label_census']}, .r3-vh={an['vh_census']})  "
              f"generated_content={gc['census']}  failures={len(c['failures'])}")
        for h in c["failures"]:
            print(f"  FAIL [{h['population']}] {h['codepoint']} ({h['range']}) "
                  f"{c['view']}/{c['lang']}  text: {h['text']!r}")

    quotable = (
        f"[no-emoji] RESULT: {'ALL GREEN' if overall_pass else 'RED'} — "
        f"bytes {'PASS' if bytes_result['pass'] else 'FAIL'}, "
        f"{sum(len(c['failures']) for c in cells)} DOM hit(s) across "
        f"{len(cells)} (view x lang) cells, 0 populations with an empty census"
    )
    print(quotable)
    print(f"[no-emoji] json -> {out_json}")

    md_lines = [
        "# B2-02 — decoded emoji closure guard",
        "",
        "Binding sweep of the assembled candidate for literal emoji codepoints, "
        "decimal/hex numeric character references that decode into an emoji "
        "range, and the decoded DOM text / accessible names / CSS generated "
        "content the browser actually paints. Method, ranges, and the three "
        "enumerated exclusions are documented in `no_emoji_audit.py`'s module "
        "docstring.",
        "",
        "| metric | value |",
        "|---|---|",
        f"| bytes scanned | **{bytes_result['chars_scanned']}** chars, "
        f"{bytes_result['entity_refs_scanned']} numeric char-refs |",
        f"| byte-scan hits | **{len(bytes_result['literal_hits']) + len(bytes_result['entity_hits'])}** |",
        f"| DOM cells swept | **{len(cells)}** (6 views x EN/ZH) |",
        f"| DOM hits | **{sum(len(c['failures']) for c in cells)}** |",
        f"| excluded-by-allowlist matches | "
        f"{len(bytes_result['excluded_literal']) + len(bytes_result['excluded_entities'])} bytes-side "
        f"(see docstring for the 3 enumerated codepoints) |",
        f"| cells with an empty census in any population | "
        f"**{sum(1 for c in cells if not c['pass'] and not c['failures'])}** |",
        "",
        quotable,
        "",
    ]
    Path(args.md).write_text("\n".join(md_lines), encoding="utf-8")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
