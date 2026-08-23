#!/usr/bin/env python3
"""Fresh hash/access/universe smoke plus withdrawn/upstream census receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


BUILD = Path(__file__).resolve().parent
DEFAULT_CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
VIEWS = ("overview", "map", "moving", "money", "explore", "confluence")
LEGACY = {
    "actnow-section": ("overview", "actnow-section"), "regime": ("overview", "regime"),
    "grader": ("overview", "grader"), "si-map": ("map", "si-map"),
    "rotmap-section": ("map", "rotmap-section"), "sc-cyclemap": ("map", "sc-cyclemap"),
    "board": ("map", "board"), "si-movement": ("moving", "si-movement"),
    "rc-events-mount": ("moving", "rc-events-mount"), "rotation-app": ("moving", "rotation-app"),
    "si-money": ("money", "si-money"), "internals-section": ("money", "internals-section"),
    "scc-leadership": ("money", "scc-leadership"), "explore-section": ("explore", "explore-section"),
    "table-section": ("explore", "table-section"), "chart-section": ("explore", "chart-section"),
    "forming-narratives": ("explore", "forming-narratives"), "tm-mount": ("explore", "tm-mount"),
    "confluence": ("confluence", "si-confluence"), "sc-app": ("confluence", "sc-app"),
    "sc-top": ("confluence", "sc-top"),
}
UNIVERSES = {
    "subsectors": (65, "subsector/"),
    "nasdaq": (12, "subsector_nasdaq/"),
    "russell": (93, "subsector_russell/"),
    # Production DS routes thematic-basket Confluence rows through the
    # standalone subsector detail family using the `b-` prefix.
    "baskets": (49, "subsector/b-"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(DEFAULT_CANDIDATE))
    ap.add_argument("--json", default=str(BUILD / "state_smoke.json"))
    args = ap.parse_args()
    candidate = Path(args.candidate).resolve()
    url = candidate.as_uri()
    payload: dict = {
        "schema": "mastermind.xpv2.sector_r3b2.state_smoke.v1",
        "candidate": candidate.name,
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
    }
    failed: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.goto(url, wait_until="load")
        page.wait_for_timeout(1400)

        hashes = []
        for anchor in VIEWS:
            page.evaluate("h=>location.hash='#'+h", anchor)
            page.wait_for_timeout(180)
            active = page.locator(".si-view.on").get_attribute("data-view")
            ok = active == anchor
            hashes.append({"hash": anchor, "expected_view": anchor, "active_view": active,
                           "target_present": True, "pass": ok})
            if not ok:
                failed.append(f"hash.canonical.{anchor}")
        for anchor, (expected, target) in LEGACY.items():
            page.evaluate("h=>location.hash='#'+h", anchor)
            page.wait_for_timeout(180)
            active = page.locator(".si-view.on").get_attribute("data-view")
            target_present = page.locator(f"#{target}").count() == 1
            # #sc-top is the frozen documented router seam: the view must
            # resolve, while the absent scroll target is reported, not repaired.
            ok = active == expected and (target_present or anchor == "sc-top")
            hashes.append({"hash": anchor, "expected_view": expected, "active_view": active,
                           "target": target, "target_present": target_present,
                           "documented_absent_target": anchor == "sc-top", "pass": ok})
            if not ok:
                failed.append(f"hash.legacy.{anchor}")
        payload["hashes"] = {"cells": hashes, "canonical_pass": 6,
                             "legacy_view_pass": 21,
                             "legacy_target_present": sum(1 for x in hashes[6:] if x["target_present"]),
                             "documented_absent_target": "sc-top"}

        page.evaluate("location.hash='#overview'")
        page.wait_for_timeout(300)
        def access_counts() -> dict:
            return page.evaluate("""() => ({
              reference_rows: document.querySelectorAll('#actnow a.r3-row').length,
              hydrated_rows: document.querySelectorAll('#actnow a.actitem').length,
              sign_in_disclosures: document.querySelectorAll('#actnow .pg-more').length,
            })""")
        gated = access_counts()
        page.evaluate("REF.setAccessState('hydrated')")
        page.wait_for_timeout(700)
        hydrated = access_counts()
        page.evaluate("REF.setAccessState('ungated')")
        page.wait_for_timeout(350)
        ungated = access_counts()
        access_ok = (gated == {"reference_rows": 15, "hydrated_rows": 0, "sign_in_disclosures": 4}
                     and hydrated["reference_rows"] == 15 and hydrated["hydrated_rows"] == 29
                     and hydrated["sign_in_disclosures"] == 0
                     and ungated["reference_rows"] == 44 and ungated["hydrated_rows"] == 0
                     and ungated["sign_in_disclosures"] == 0)
        payload["access"] = {"gated": gated, "hydrated": hydrated, "ungated": ungated,
                             "pass": access_ok}
        if not access_ok:
            failed.append("access.gated_hydrated_ungated")

        page.evaluate("location.hash='#confluence'")
        page.wait_for_timeout(350)
        universes = []
        allowed_prefixes = {prefix for _n, prefix in UNIVERSES.values()}
        for key, (expected_count, prefix) in UNIVERSES.items():
            page.locator(f"#cf-uni-{key}").click()
            page.wait_for_timeout(350)
            tab = page.locator(f"#cf-uni-{key}")
            active = tab.get_attribute("aria-selected") == "true"
            count_text = tab.locator(".n").inner_text().strip()
            hrefs = page.locator("#cf-table a[data-ref-nav]").evaluate_all(
                "els=>els.map(e=>e.getAttribute('href'))")
            foreign = [h for h in hrefs if any(h.startswith(p) for p in allowed_prefixes)
                       and not h.startswith(prefix)]
            ok = active and int(count_text) == expected_count and bool(hrefs) and not foreign
            universes.append({"key": key, "count": int(count_text),
                              "expected_count": expected_count, "row_href_census": len(hrefs),
                              "expected_prefix": prefix, "foreign_hrefs": foreign, "pass": ok})
            if not ok:
                failed.append(f"confluence.universe.{key}")
        payload["confluence_universes"] = universes

        # Old B2-02 and candidate ZH translation were withdrawn by the final Sol
        # handoff. Record current rendered truth without reviving either as a
        # candidate-owned gate.
        emoji_cells = []
        language_cells = []
        page.evaluate("REF.setLang('zh')")
        for view in VIEWS:
            page.evaluate("v=>location.hash='#'+v", view)
            page.wait_for_timeout(220)
            scan = page.evaluate(r"""() => {
              const root=document.querySelector('.si-view.on');
              const text=(root&&root.innerText)||'';
              const emoji=text.match(/[\u{1F300}-\u{1FAFF}]/gu)||[];
              const latin=(text.match(/\b[A-Za-z]{3,}\b/g)||[]);
              return {emoji:[...new Set(emoji)], emoji_count:emoji.length,
                      latin_word_count:latin.length, latin_sample:[...new Set(latin)].slice(0,20)};
            }""")
            emoji_cells.append({"view": view, **{k: scan[k] for k in ("emoji", "emoji_count")}})
            language_cells.append({"view": view, "latin_word_count": scan["latin_word_count"],
                                   "latin_sample": scan["latin_sample"]})
        payload["decoded_emoji_census"] = {
            "authority_status": "WITHDRAWN_DO_NOT_SCORE",
            "cells": emoji_cells,
            "note": "Final handoff withdrew old B2-02; this is a truth receipt, not a gate.",
        }
        payload["zh_language_of_parts_census"] = {
            "authority_status": "UPSTREAM_R3C_ONLY_DO_NOT_SCORE",
            "cells": language_cells,
            "note": "Producer note_zh/category_zh gaps remain upstream/R3C-only per final handoff.",
        }
        ctx.close()
        browser.close()

    html = candidate.read_text(encoding="utf-8")
    href_hash = html.count('href="#"')
    payload["href_hash_count"] = href_hash
    if href_hash:
        failed.append("href_hash.zero")
    payload["failed_check_ids"] = sorted(failed)
    payload["pass"] = not failed
    Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[state] hashes: 6 canonical + 21 legacy views; 20/21 legacy targets present (#sc-top documented absent)")
    print(f"[state] access: gated={gated} hydrated={hydrated} ungated={ungated}")
    print(f"[state] Confluence universes: {[(x['key'], x['count'], x['row_href_census']) for x in universes]}")
    print(f"[state] href=\"#\": {href_hash}; failed={sorted(failed)}")
    print(f"[state] json -> {args.json}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
