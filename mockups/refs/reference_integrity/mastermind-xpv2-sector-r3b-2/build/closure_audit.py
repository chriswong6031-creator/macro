#!/usr/bin/env python3
"""Freeze-critical semantic guard for R3B.2 B2-01/B2-12/B2-13/B2-15.

This audit runs against the assembled candidate, not the source partials. It
asserts non-zero rendered populations, language-resolved customer terms,
producer-derived qualification scope, and the shared receipt relationship.
Every assertion has a stable check id so the mutation suite can prove that an
independent omission produces an independent red.

Usage:
    <playwright-python> closure_audit.py [--candidate HTML] [--json OUT.json]
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
LANGS = ("en", "zh")


MEASURE_JS = r"""
async (lang) => {
  const visText = (root) => {
    if (!root) return '';
    let out = '';
    const walk = (n) => { for (const c of n.childNodes) {
      if (c.nodeType === 3) { out += c.textContent; continue; }
      if (c.nodeType !== 1 || getComputedStyle(c).display === 'none') continue;
      walk(c);
    }};
    walk(root); return out.replace(/\s+/g, ' ').trim();
  };
  const activate = (view) => {
    const b = document.querySelector('.si-view-btn[data-view="'+view+'"]');
    if (b) b.click(); else location.hash = '#'+view;
  };
  const settle = () => new Promise((resolve) => setTimeout(resolve, 250));
  const pure = (el, drop) => {
    if (!el) return '';
    const clone = el.cloneNode(true);
    const src = [...el.querySelectorAll('*')], dst = [...clone.querySelectorAll('*')];
    src.forEach((s, i) => { if (getComputedStyle(s).display === 'none') dst[i].remove(); });
    if (drop) clone.querySelectorAll(drop).forEach((n) => n.remove());
    return (clone.textContent || '').replace(/\s+/g, ' ').trim();
  };

  activate('overview');
  await settle();
  const ovHeader = pure(document.querySelector('[data-view="overview"] .r3-colfig[data-r3b2="01"]'), 'em');
  const ovInline = [...document.querySelectorAll('[data-view="overview"] [data-fig-kind="strength"]')]
    .map(visText);

  activate('map');
  await settle();
  const mapHeader = visText(document.querySelector('[data-view="map"] th[data-r3b1="06"]'));
  const detailTerms = [...document.querySelectorAll('#r3-map-detail dt')].map(visText);
  const dot = document.querySelector('#rvx-rmap circle.r3-dot');
  if (dot) dot.dispatchEvent(new MouseEvent('mouseenter', {bubbles:true, clientX:240, clientY:180}));
  const mapTip = visText(document.getElementById('r3-map-tip'));

  activate('confluence');
  await settle();
  const coverage = visText(document.querySelector('#cf-foot [data-r3b1="07"]'));
  const lowMarkers = [...document.querySelectorAll('[data-view="confluence"] [data-r3b2="12"]')];
  const lowLabels = lowMarkers.map((m) => visText(m.nextElementSibling));

  activate('moving');
  await settle();
  const target = document.getElementById('r3-receipt');
  const overviewControl = document.querySelector('[data-view="overview"] [data-r3b1="02"] button.r3-rcpt');
  const movingControls = [...document.querySelectorAll('[data-view="moving"] [data-r3b1="08"][aria-controls="r3-receipt"]')];
  const allTargetControls = [...document.querySelectorAll('[aria-controls="r3-receipt"]')];

  activate('money');
  await settle();
  const qual = document.querySelector('[data-view="money"] .lead-tr-qual[data-r3b2="15"]');
  const h21 = document.querySelector('[data-view="money"] .lead-tr-h21');
  const clauses = qual ? [...qual.querySelectorAll('.lead-tr-cl')].map(visText) : [];
  const qr = qual ? qual.getBoundingClientRect() : null;
  const hr = h21 ? h21.getBoundingClientRect() : null;
  const hcs = h21 ? getComputedStyle(h21) : null;
  let tr = null;
  try {
    tr = REF.parseJSON(REF.registry['marketdata/index_leadership.json']).track_record;
  } catch (_) {}

  return {
    lang,
    b2_01: {overview_header: ovHeader, overview_inline: ovInline,
            map_header: mapHeader, map_detail_terms: detailTerms, map_tip: mapTip},
    b2_12: {coverage, low_marker_census: lowMarkers.length, low_labels: lowLabels},
    b2_13: {
      target_present: !!target,
      target_id: target ? target.id : null,
      overview_control_present: !!overviewControl,
      overview_aria_controls: overviewControl ? overviewControl.getAttribute('aria-controls') : null,
      moving_control_census: movingControls.length,
      all_target_control_census: allTargetControls.length,
      all_target_ids: [...new Set(allTargetControls.map((b) => b.getAttribute('aria-controls')))],
    },
    b2_15: {
      fixture: tr ? {is_context_only: tr.is_context_only, proven: tr.proven} : null,
      qualification_present: !!qual,
      qualification_text: visText(qual),
      clauses,
      h21_present: !!h21,
      h21_text: visText(h21),
      qualification_top: qr ? +qr.top.toFixed(1) : null,
      h21_top: hr ? +hr.top.toFixed(1) : null,
      h21_border_top_px: hcs ? parseFloat(hcs.borderTopWidth || '0') : null,
      h21_flex_basis: hcs ? hcs.flexBasis : null,
    },
  };
}
"""


def evaluate_cell(measure: dict) -> tuple[list[dict], list[str]]:
    lang = measure["lang"]
    strength = "Strength" if lang == "en" else "强度"
    low = "Low confidence" if lang == "en" else "低置信度"
    coverage_thin = "48 are too thin to time" if lang == "en" else "48 个数据过于稀疏"
    q_expected = (
        ["Context only", "evidence proven at 5d", "never sizes decisions"]
        if lang == "en"
        else ["仅为背景", "仅 5 日周期有实测证据", "从不用于仓位决策"]
    )
    h21_token = "21d" if lang == "en" else "21日"
    checks: list[dict] = []

    def add(check_id: str, ok: bool, detail: str) -> None:
        checks.append({"id": check_id, "pass": bool(ok), "detail": detail})

    b1 = measure["b2_01"]
    add("b2_01.overview_header", b1["overview_header"] == strength,
        f"got={b1['overview_header']!r}, expected={strength!r}")
    add("b2_01.overview_inline_census",
        len(b1["overview_inline"]) == 11 and set(b1["overview_inline"]) == {strength},
        f"census={len(b1['overview_inline'])}, labels={sorted(set(b1['overview_inline']))}")
    add("b2_01.map_header", b1["map_header"] == strength,
        f"got={b1['map_header']!r}, expected={strength!r}")
    add("b2_01.map_detail", strength in b1["map_detail_terms"],
        f"terms={b1['map_detail_terms']}")
    add("b2_01.map_tooltip", f"{strength} " in b1["map_tip"],
        f"tooltip={b1['map_tip']!r}")
    second = "Score" if lang == "en" else "评分"
    joined = " | ".join([b1["overview_header"], *b1["overview_inline"], b1["map_header"],
                           *b1["map_detail_terms"], b1["map_tip"]])
    add("b2_01.one_path_one_term", second not in joined,
        f"forbidden second term {second!r} absent={second not in joined}")

    b12 = measure["b2_12"]
    add("b2_12.coverage_fact", coverage_thin in b12["coverage"],
        f"coverage={b12['coverage']!r}")
    add("b2_12.low_confidence_census",
        b12["low_marker_census"] > 0 and len(b12["low_labels"]) == b12["low_marker_census"],
        f"markers={b12['low_marker_census']}, labels={len(b12['low_labels'])}")
    add("b2_12.low_confidence_term",
        b12["low_marker_census"] > 0 and set(b12["low_labels"]) == {low},
        f"labels={sorted(set(b12['low_labels']))}")
    add("b2_12.distinct_authority_terms",
        low not in b12["coverage"] and "Thin data" not in b12["low_labels"]
        and "数据稀疏" not in b12["low_labels"],
        "coverage omission and in-table reliability retain distinct terms")

    b13 = measure["b2_13"]
    add("b2_13.shared_target", b13["target_present"] and b13["target_id"] == "r3-receipt",
        f"target_present={b13['target_present']}, id={b13['target_id']!r}")
    add("b2_13.overview_control",
        b13["overview_control_present"] and b13["overview_aria_controls"] == "r3-receipt",
        f"present={b13['overview_control_present']}, controls={b13['overview_aria_controls']!r}")
    add("b2_13.moving_controls", b13["moving_control_census"] == 3,
        f"moving controls={b13['moving_control_census']}, expected=3")
    add("b2_13.exact_shared_control_census",
        b13["all_target_control_census"] == 4 and b13["all_target_ids"] == ["r3-receipt"],
        f"all controls={b13['all_target_control_census']}, targets={b13['all_target_ids']}")

    b15 = measure["b2_15"]
    fixture = b15["fixture"] or {}
    proven = fixture.get("proven") or {}
    proven_true = sorted(k for k, v in proven.items() if v is True)
    add("b2_15.producer_scope",
        fixture.get("is_context_only") is True and proven_true == ["5"] and proven.get("21") is False,
        f"fixture={fixture}")
    add("b2_15.qualification_present", b15["qualification_present"],
        f"present={b15['qualification_present']}")
    add("b2_15.localized_clauses", b15["clauses"] == q_expected,
        f"clauses={b15['clauses']}, expected={q_expected}")
    add("b2_15.qualification_excludes_21d", h21_token not in b15["qualification_text"],
        f"qualification={b15['qualification_text']!r}")
    add("b2_15.explicit_21d_line", b15["h21_present"] and h21_token in b15["h21_text"],
        f"h21={b15['h21_text']!r}")
    add("b2_15.visual_separation",
        b15["qualification_top"] is not None and b15["h21_top"] is not None
        and b15["h21_top"] > b15["qualification_top"]
        and (b15["h21_border_top_px"] or 0) >= 1 and b15["h21_flex_basis"] == "100%",
        f"qual_top={b15['qualification_top']}, h21_top={b15['h21_top']}, "
        f"border={b15['h21_border_top_px']}, flex_basis={b15['h21_flex_basis']}")

    failed = sorted(c["id"] for c in checks if not c["pass"])
    return checks, failed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(DEFAULT_CANDIDATE))
    ap.add_argument("--json", default=str(BUILD / "closure_audit.json"))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    candidate = Path(args.candidate).resolve()
    if not candidate.exists():
        print(f"[closure] missing candidate: {candidate}", file=sys.stderr)
        return 2

    cells: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for lang in LANGS:
            ctx = browser.new_context(viewport={"width": 1440, "height": 1100})
            page = ctx.new_page()
            page.goto(candidate.as_uri(), wait_until="load")
            page.wait_for_timeout(1400)
            page.evaluate(
                "(l)=>{ if(window.REF&&REF.setLang) REF.setLang(l);"
                " else {document.documentElement.setAttribute('data-lang',l);"
                " document.dispatchEvent(new CustomEvent('langchange'));}}", lang)
            page.wait_for_timeout(700)
            measure = page.evaluate(MEASURE_JS, lang)
            checks, failed = evaluate_cell(measure)
            cells.append({"lang": lang, "measure": measure, "checks": checks,
                          "failed_check_ids": failed, "pass": not failed})
            if args.verbose:
                print(f"[closure] {lang}: {len(checks)-len(failed)}/{len(checks)} checks passed")
                for check in checks:
                    if not check["pass"]:
                        print(f"[closure] FAIL {lang}/{check['id']}: {check['detail']}")
            ctx.close()
        browser.close()

    failed = sorted({check_id for cell in cells for check_id in cell["failed_check_ids"]})
    out = {
        "schema": "mastermind.xpv2.sector_r3b2.closure_audit.v1",
        "candidate": candidate.name,
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "cells": cells,
        "failed_check_ids": failed,
        "pass": bool(cells) and not failed,
    }
    Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(len(cell["checks"]) for cell in cells)
    failed_n = sum(len(cell["failed_check_ids"]) for cell in cells)
    print(f"[closure] {total-failed_n}/{total} rendered semantic checks passed across EN/ZH")
    print(f"[closure] failed check ids: {failed}")
    print(f"[closure] json -> {args.json}")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
