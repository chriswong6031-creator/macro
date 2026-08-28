#!/usr/bin/env python3
"""Decoded-output no-emoji audit for the R3B.2 six-view reference.

The provisional freeze carried ``&#128202;`` in the Moving track-record
heading. A raw-source search that does not decode HTML entities can miss that
defect, so this guard deliberately checks every observable representation:

* literal Extended_Pictographic Unicode in the six candidate-owned view
  partials after comments are removed;
* decimal and hexadecimal numeric HTML entities after decoding;
* rendered DOM text in every view, in EN and ZH;
* Chromium-computed accessible names in every view, in EN and ZH; and
* observable ``::before`` / ``::after`` generated content.

The browser's Unicode ``Extended_Pictographic`` property is the classifier.
That avoids treating ordinary CJK text, arrows, stars, check marks, box-drawing
characters, or punctuation as emoji. Embedded frozen producer payloads are not
reclassified as candidate-authored source; if any such bytes become observable,
the live DOM/accessible-name passes still audit them. The detector self-tests literal, decimal,
and hexadecimal encodings of the chart emoji before it audits governed bytes.

Usage:
    <playwright-python> decoded_emoji_audit.py [--json OUT.json]
    <playwright-python> decoded_emoji_audit.py --mutate

Exit 0 iff the pristine candidate has a nonzero 12-cell rendered census and no
decoded emoji. ``--mutate`` reinserts ``&#128202;`` into a temporary candidate
copy and proves that the only semantic owner that reds is the Moving
track-record heading. Governed files are never changed by the mutation.
"""
from __future__ import annotations

import argparse
import html as html_module
import json
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BUILD = Path(__file__).resolve().parent
CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
VIEWS = ["overview", "map", "moving", "money", "explore", "confluence"]
LANGS = ["en", "zh"]
VIEW_SOURCES = [BUILD / "views" / f"{view}.html" for view in VIEWS]

NUMERIC_ENTITY_RE = re.compile(r"&#(?P<hex>[xX])?(?P<digits>[0-9A-Fa-f]+);?")
TRACK_RECORD_TERMS = ("Track record", "跟踪记录")

CLASSIFY_CHARS_JS = r"""
(chars) => chars.filter(function(ch){
  return /\p{Extended_Pictographic}/u.test(ch);
})
"""

DOM_AUDIT_JS = r"""
(view) => {
  const emoji = /\p{Extended_Pictographic}/gu;
  const root = document.querySelector('.si-view[data-view="' + view + '"]');
  if (!root) return {error: 'missing view root', view: view};

  function chars(text) {
    return [...new Set((String(text || '').match(emoji) || []))];
  }
  function ownerFor(node, text) {
    const el = node && node.nodeType === Node.ELEMENT_NODE ? node : node && node.parentElement;
    if (el && el.closest('.r3-tr-hd')) return 'moving.track_record_heading';
    if (view === 'moving' && (text.includes('Track record') || text.includes('跟踪记录'))) {
      return 'moving.track_record_heading';
    }
    return 'view.' + view;
  }
  function descriptor(el) {
    if (!el) return null;
    const id = el.id ? '#' + el.id : '';
    const cls = el.classList && el.classList.length
      ? '.' + [...el.classList].slice(0, 3).join('.') : '';
    return el.tagName.toLowerCase() + id + cls;
  }

  const textHits = [];
  let nonemptyTextNodes = 0;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const parent = node.parentElement;
    if (!parent || parent.closest('script,style,template,noscript')) continue;
    let painted = true;
    for (let el = parent; el && el !== root.parentElement; el = el.parentElement) {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') { painted = false; break; }
    }
    if (!painted) continue;
    const text = (node.textContent || '').replace(/\s+/g, ' ').trim();
    if (!text) continue;
    nonemptyTextNodes += 1;
    const hitChars = chars(text);
    if (hitChars.length) {
      textHits.push({
        owner: ownerFor(node, text),
        element: descriptor(node.parentElement),
        chars: hitChars,
        text: text.slice(0, 220),
      });
    }
  }

  const pseudoHits = [];
  let pseudoObserved = 0;
  for (const el of [root, ...root.querySelectorAll('*')]) {
    for (const pseudo of ['::before', '::after']) {
      const content = getComputedStyle(el, pseudo).content;
      if (!content || content === 'none' || content === 'normal' || content === '""') continue;
      pseudoObserved += 1;
      const hitChars = chars(content);
      if (hitChars.length) {
        pseudoHits.push({
          owner: ownerFor(el, content),
          element: descriptor(el),
          pseudo: pseudo,
          chars: hitChars,
          content: content.slice(0, 220),
        });
      }
    }
  }

  return {
    view: view,
    elementCensus: 1 + root.querySelectorAll('*').length,
    nonemptyTextNodes: nonemptyTextNodes,
    pseudoObserved: pseudoObserved,
    textHits: textHits,
    pseudoHits: pseudoHits,
  };
}
"""

AX_CLASSIFY_JS = r"""
(names) => names.map(function(name){
  return [...new Set((String(name || '').match(/\p{Extended_Pictographic}/gu) || []))];
})
"""


def semantic_owner(text: str, source_hint: str) -> str:
    if any(term in text for term in TRACK_RECORD_TERMS):
        return "moving.track_record_heading"
    if "moving" in source_hint:
        return "view.moving"
    return f"source.{source_hint}"


def line_context(text: str, offset: int, width: int = 100) -> str:
    start = max(0, offset - width)
    end = min(len(text), offset + width)
    return text[start:end].replace("\n", " ").strip()


def classify_chars(page: Page, chars: list[str]) -> set[str]:
    if not chars:
        return set()
    return set(page.evaluate(CLASSIFY_CHARS_JS, chars))


def detector_self_test(page: Page) -> dict:
    encodings = {
        "literal_unicode": "📊",
        "decimal_numeric_entity": html_module.unescape("&#128202;"),
        "hex_numeric_entity": html_module.unescape("&#x1F4CA;"),
    }
    detected = classify_chars(page, list(encodings.values()))
    rows = {name: value in detected for name, value in encodings.items()}
    return {"rows": rows, "pass": all(rows.values())}


def source_audit(page: Page, candidate: Path) -> tuple[dict, list[dict]]:
    paths = [("candidate", candidate)] + [(f"view.{p.stem}", p) for p in VIEW_SOURCES]
    loaded: list[tuple[str, Path, str]] = []
    distinct_non_ascii: set[str] = set()
    for label, path in paths:
        text = path.read_text(encoding="utf-8")
        loaded.append((label, path, text))
        if label.startswith("view."):
            # Source authorship is the six view partials. The assembled candidate
            # also embeds verbatim frozen producer payloads; those are audited if
            # they render, but are not silently reassigned to this reference.
            authored = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
            authored = re.sub(r"/\*.*?\*/", "", authored, flags=re.DOTALL)
            distinct_non_ascii.update(ch for ch in authored if ord(ch) > 127)

    literal_emoji = classify_chars(page, sorted(distinct_non_ascii))
    findings: list[dict] = []
    decimal_entities = 0
    hex_entities = 0
    literal_non_ascii_occurrences = 0

    for label, path, text in loaded:
        authored = text
        if label.startswith("view."):
            authored = re.sub(r"<!--.*?-->", "", authored, flags=re.DOTALL)
            authored = re.sub(r"/\*.*?\*/", "", authored, flags=re.DOTALL)
            literal_non_ascii_occurrences += sum(1 for ch in authored if ord(ch) > 127)
        for match in NUMERIC_ENTITY_RE.finditer(text):
            is_hex = bool(match.group("hex"))
            try:
                codepoint = int(match.group("digits"), 16 if is_hex else 10)
                decoded = chr(codepoint)
            except (ValueError, OverflowError):
                continue
            if is_hex:
                hex_entities += 1
            else:
                decimal_entities += 1
            if decoded in classify_chars(page, [decoded]):
                context = line_context(text, match.start())
                findings.append({
                    "axis": "hex_numeric_entity" if is_hex else "decimal_numeric_entity",
                    "owner": semantic_owner(context, label),
                    "source": label,
                    "path": str(path),
                    "line": text.count("\n", 0, match.start()) + 1,
                    "encoded": match.group(0),
                    "decoded": decoded,
                    "context": context,
                })

        # Literal pictographs are checked in candidate-owned view source only.
        # Numeric entities are checked in both the assembled candidate and view
        # source because the exact regression lived in both representations.
        if not label.startswith("view."):
            continue
        for ch in literal_emoji:
            start = 0
            while True:
                offset = authored.find(ch, start)
                if offset < 0:
                    break
                context = line_context(authored, offset)
                findings.append({
                    "axis": "literal_unicode",
                    "owner": semantic_owner(context, label),
                    "source": label,
                    "path": str(path),
                    "line": authored.count("\n", 0, offset) + 1,
                    "char": ch,
                    "codepoint": f"U+{ord(ch):04X}",
                    "context": context,
                })
                start = offset + len(ch)

    census = {
        "files": len(loaded),
        "bytes": sum(len(text.encode("utf-8")) for _label, _path, text in loaded),
        "literal_non_ascii_occurrences": literal_non_ascii_occurrences,
        "literal_distinct_non_ascii": len(distinct_non_ascii),
        "literal_source_files": len(VIEW_SOURCES),
        "decimal_numeric_entities": decimal_entities,
        "hex_numeric_entities": hex_entities,
    }
    return census, findings


def goto_and_set_language(page: Page, url: str, lang: str) -> None:
    page.goto(url, wait_until="load")
    page.wait_for_timeout(1200)
    page.evaluate(
        "(l)=>{ if(window.REF&&REF.setLang) REF.setLang(l);"
        " else { document.documentElement.setAttribute('data-lang',l);"
        " document.documentElement.setAttribute('lang',l==='zh'?'zh-CN':'en');"
        " document.dispatchEvent(new CustomEvent('langchange')); } }",
        lang,
    )
    page.wait_for_timeout(400)


def click_view(page: Page, view: str) -> None:
    page.evaluate(
        "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
        "if(b)b.click();else location.hash='#'+v;}",
        view,
    )
    page.wait_for_timeout(700)


def accessible_name_audit(page: Page, view: str) -> tuple[int, list[dict]]:
    session = page.context.new_cdp_session(page)
    try:
        tree = session.send("Accessibility.getFullAXTree")
    finally:
        session.detach()
    names = []
    for node in tree.get("nodes", []):
        value = (node.get("name") or {}).get("value")
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    hit_chars = page.evaluate(AX_CLASSIFY_JS, names) if names else []
    hits = []
    for name, chars in zip(names, hit_chars):
        if not chars:
            continue
        owner = semantic_owner(name, f"view.{view}")
        hits.append({
            "owner": owner,
            "name": name[:220],
            "chars": chars,
        })
    return len(names), hits


def render_audit(browser, candidate: Path) -> tuple[list[dict], list[dict]]:
    cells: list[dict] = []
    findings: list[dict] = []
    url = candidate.as_uri()
    for lang in LANGS:
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        goto_and_set_language(page, url, lang)
        for view in VIEWS:
            click_view(page, view)
            dom = page.evaluate(DOM_AUDIT_JS, view)
            ax_census, ax_hits = accessible_name_audit(page, view)
            cell_findings = []
            for row in dom.get("textHits", []):
                cell_findings.append({"axis": "rendered_dom_text", **row})
            for row in dom.get("pseudoHits", []):
                cell_findings.append({"axis": "generated_pseudo_content", **row})
            for row in ax_hits:
                cell_findings.append({"axis": "accessible_name", **row})
            for row in cell_findings:
                row.update({"lang": lang, "view": view})
            findings.extend(cell_findings)
            cells.append({
                "lang": lang,
                "view": view,
                "element_census": dom.get("elementCensus", 0),
                "dom_text_node_census": dom.get("nonemptyTextNodes", 0),
                "accessible_name_census": ax_census,
                "observable_pseudo_content_census": dom.get("pseudoObserved", 0),
                "violation_count": len(cell_findings),
            })
        context.close()
    return cells, findings


def run_audit(candidate: Path) -> tuple[bool, dict]:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        probe = browser.new_page()
        self_test = detector_self_test(probe)
        source_census, source_findings = source_audit(probe, candidate)
        probe.close()
        cells, render_findings = render_audit(browser, candidate)
        browser.close()

    findings = source_findings + render_findings
    expected_cells = {(lang, view) for lang in LANGS for view in VIEWS}
    got_cells = {(cell["lang"], cell["view"]) for cell in cells}
    nonzero = (
        source_census["files"] == 7
        and source_census["bytes"] > 0
        and source_census["literal_non_ascii_occurrences"] > 0
        and source_census["decimal_numeric_entities"] > 0
        and got_cells == expected_cells
        and all(cell["element_census"] > 0 for cell in cells)
        and all(cell["dom_text_node_census"] > 0 for cell in cells)
        and all(cell["accessible_name_census"] > 0 for cell in cells)
    )
    ok = self_test["pass"] and nonzero and not findings
    report = {
        "schema": "mastermind.r3b2.decoded_emoji_audit.v1",
        "candidate": candidate.name,
        "classifier": "ECMAScript Unicode property Extended_Pictographic",
        "detector_self_test": self_test,
        "source_census": source_census,
        "cells": cells,
        "expected_render_cells": len(expected_cells),
        "nonzero_census": nonzero,
        "violations": findings,
        "violation_owners": sorted({row["owner"] for row in findings}),
        "pass": ok,
    }
    return ok, report


MUTATE_TARGET = "L('Track record','跟踪记录')"
MUTATE_REPLACEMENT = "L('&#128202; Track record','&#128202; 跟踪记录')"


def run_mutation(candidate: Path, out_md: Path) -> bool:
    html = candidate.read_text(encoding="utf-8")
    count = html.count(MUTATE_TARGET)
    if count != 1:
        print(
            f"[decoded-emoji-mutate] FAIL: expected one Moving track-record anchor, found {count}",
            file=sys.stderr,
        )
        return False
    mutated = html.replace(MUTATE_TARGET, MUTATE_REPLACEMENT, 1)
    with tempfile.TemporaryDirectory(prefix="r3b2_decoded_emoji_mutation_") as tmp:
        mutated_path = Path(tmp) / "mutated_candidate.html"
        mutated_path.write_text(mutated, encoding="utf-8")
        print("=== baseline: pristine candidate must be fully GREEN ===")
        base_ok, base_report = run_audit(candidate)
        print(
            f"[{'PASS' if base_ok else 'FAIL'}] pristine baseline green — "
            f"{len(base_report['violations'])} violation(s), "
            f"{len(base_report['cells'])} rendered cells"
        )

        print("\n=== mutation: reinsert &#128202; in Moving track-record heading ===")
        mut_ok, mut_report = run_audit(mutated_path)

    violations = mut_report["violations"]
    owners = set(mut_report["violation_owners"])
    axes = Counter(row["axis"] for row in violations)
    rendered_langs = {
        row.get("lang") for row in violations
        if row["axis"] == "rendered_dom_text" and row.get("view") == "moving"
    }
    ax_langs = {
        row.get("lang") for row in violations
        if row["axis"] == "accessible_name" and row.get("view") == "moving"
    }
    unique_red = (
        not mut_ok
        and owners == {"moving.track_record_heading"}
        and axes["decimal_numeric_entity"] > 0
        and rendered_langs == set(LANGS)
        and ax_langs == set(LANGS)
    )
    ok = base_ok and unique_red

    lines = [
        "# decoded_emoji_audit.py — mutation proof\n",
        "\nThe mutation reinserts `&#128202;` only in an in-memory copy of the "
        "Moving `Track record / 跟踪记录` heading. The governed source and proposal "
        "are never changed.\n",
        f"\n**Pristine baseline green:** {'YES' if base_ok else 'NO'} "
        f"({len(base_report['violations'])} violations; "
        f"{len(base_report['cells'])}/12 rendered cells)\n",
        f"\n**Mutation produced one semantic-owner red:** {'YES' if unique_red else 'NO'}\n",
        f"\n**Violation owners:** `{sorted(owners)}`\n",
        f"\n**Axis counts:** `{dict(sorted(axes.items()))}`\n",
        f"\n**Rendered DOM languages hit:** `{sorted(rendered_langs)}`\n",
        f"\n**Accessible-name languages hit:** `{sorted(ax_langs)}`\n",
        "\n## Mutated-copy violations\n",
    ]
    for row in violations:
        detail = row.get("encoded") or row.get("char") or row.get("chars")
        location = ":".join(str(v) for v in (row.get("lang"), row.get("view")) if v)
        lines.append(
            f"- `{row['axis']}` owner `{row['owner']}`"
            f"{f' at {location}' if location else ''}: `{detail}`\n"
        )
    if not violations:
        lines.append("- (none — BUG: mutation was not detected)\n")
    out_md.write_text("".join(lines), encoding="utf-8")

    print(
        f"[{'PASS' if unique_red else 'FAIL'}] mutation unique red — owners={sorted(owners)} "
        f"axes={dict(sorted(axes.items()))} DOM_langs={sorted(rendered_langs)} "
        f"AX_langs={sorted(ax_langs)}"
    )
    print(f"[decoded-emoji-mutate] report -> {out_md}")
    return ok


def print_report(report: dict, json_path: Path) -> None:
    census = report["source_census"]
    print(
        "[decoded-emoji] source census: "
        f"files={census['files']} bytes={census['bytes']} "
        f"literal_non_ascii={census['literal_non_ascii_occurrences']} "
        f"decimal_entities={census['decimal_numeric_entities']} "
        f"hex_entities={census['hex_numeric_entities']}"
    )
    print(
        f"[decoded-emoji] detector self-test: {report['detector_self_test']['rows']} "
        f"pass={report['detector_self_test']['pass']}"
    )
    for cell in report["cells"]:
        print(
            f"[decoded-emoji] {cell['lang']}/{cell['view']}: "
            f"elements={cell['element_census']} dom_text={cell['dom_text_node_census']} "
            f"ax_names={cell['accessible_name_census']} "
            f"pseudo={cell['observable_pseudo_content_census']} "
            f"violations={cell['violation_count']}"
        )
    for row in report["violations"]:
        print(f"[decoded-emoji] FAIL {json.dumps(row, ensure_ascii=False)}")
    print(
        f"[decoded-emoji] RESULT: {'ALL GREEN' if report['pass'] else 'RED'} — "
        f"{len(report['cells'])}/12 cells, {len(report['violations'])} violation(s), "
        f"owners={report['violation_owners']}"
    )
    print(f"[decoded-emoji] json -> {json_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(CANDIDATE))
    ap.add_argument("--json", default=str(BUILD / "decoded_emoji_audit.json"))
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument(
        "--mutate-out",
        default=str(BUILD / "DECODED_EMOJI_MUTATION.md"),
    )
    args = ap.parse_args()

    candidate = Path(args.candidate)
    if not candidate.exists():
        print(f"[decoded-emoji] missing candidate: {candidate}", file=sys.stderr)
        return 2
    if args.mutate:
        return 0 if run_mutation(candidate, Path(args.mutate_out)) else 1

    ok, report = run_audit(candidate)
    json_path = Path(args.json)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print_report(report, json_path)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
