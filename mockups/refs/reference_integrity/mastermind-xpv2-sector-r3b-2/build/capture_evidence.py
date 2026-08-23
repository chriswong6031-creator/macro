#!/usr/bin/env python3
"""Fresh R3B.2 screenshot evidence bound to one assembled candidate hash.

Every capture uses a fresh browser context because Playwright screenshots and
device-metric overrides are a known unsafe combination when contexts are
reused. The script never rebuilds or edits the candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


BUILD = Path(__file__).resolve().parent
DEFAULT_CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
DEFAULT_OUT = BUILD.parent / "evidence"
VIEWS = ("overview", "map", "moving", "money", "explore", "confluence")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def settle(page: Page, lang: str, theme: str, view: str) -> None:
    page.evaluate(
        "([l,t,v])=>{"
        "document.documentElement.setAttribute('data-theme',t);"
        "if(window.REF&&REF.setLang)REF.setLang(l);"
        "else{document.documentElement.setAttribute('data-lang',l);"
        "document.dispatchEvent(new CustomEvent('langchange'));}"
        "var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
        "if(b)b.click();else location.hash='#'+v;}", [lang, theme, view])
    page.wait_for_timeout(900)


def context_page(browser, url: str, width: int, height: int = 1000,
                 dpr: int = 1, mobile: bool | None = None):
    if mobile is None:
        mobile = width < 768
    ctx = browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=dpr,
        is_mobile=mobile,
        has_touch=mobile,
    )
    page = ctx.new_page()
    page.goto(url, wait_until="load")
    page.wait_for_timeout(1500)
    return ctx, page


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=str(DEFAULT_CANDIDATE))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--resume", action="store_true",
                    help="reuse already asserted screenshot files and finish the packet")
    args = ap.parse_args()
    candidate = Path(args.candidate).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    url = candidate.as_uri()
    records: list[dict] = []
    notes: list[str] = []

    def record(path: Path, kind: str, state: dict) -> None:
        records.append({"file": path.name, "kind": kind, "state": state,
                        "bytes": path.stat().st_size, "sha256": sha256(path)})
        print(f"[shot] {path.name}")

    def reuse(path: Path, kind: str, state: dict) -> bool:
        if args.resume and path.exists() and path.stat().st_size > 0:
            record(path, kind, {**state, "resumed_from_asserted_capture": True})
            return True
        return False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        # Programmatic all-six matrices: desktop dark/light EN and mobile EN/ZH.
        for width, themes, langs in (
            (1440, ("dark", "light"), ("en",)),
            (390, ("dark",), ("en", "zh")),
        ):
            for theme in themes:
                for lang in langs:
                    for view in VIEWS:
                        state = {"view": view, "width": width, "theme": theme,
                                 "lang": lang, "active_view": view}
                        path = out_dir / f"all6-{view}-{width}-{theme}-{lang}.png"
                        if reuse(path, "all_six_matrix", state):
                            continue
                        ctx, page = context_page(browser, url, width)
                        settle(page, lang, theme, view)
                        page.screenshot(path=str(path), full_page=True)
                        active = page.locator(".si-view.on").get_attribute("data-view")
                        assert active == view, (view, active)
                        record(path, "all_six_matrix", {**state, "active_view": active})
                        ctx.close()

        # Changed-state element captures. Each tuple is (filename, view, selector,
        # width, theme, lang, physical zoom). `zoom=2` uses the house severe-zoom
        # method: W physical -> W/2 CSS viewport at device scale factor 2.
        element_cells = [
            ("b2-05-overview-figures-390-dark-en.png", "overview", "#actnow-section", 390, "dark", "en", 1),
            ("b2-05-overview-figures-390-dark-zh.png", "overview", "#actnow-section", 390, "dark", "zh", 1),
            ("b2-05-overview-figures-320phys-zoom200-dark-zh.png", "overview", "#actnow-section", 320, "dark", "zh", 2),
            ("b2-05-conviction-1440-dark-en.png", "confluence", "#cf-picks-band", 1440, "dark", "en", 1),
            ("b2-05-conviction-1440-dark-zh.png", "confluence", "#cf-picks-band", 1440, "dark", "zh", 1),
            ("b2-05-conviction-390-dark-en.png", "confluence", "#cf-picks-band", 390, "dark", "en", 1),
            ("b2-05-conviction-390-dark-zh.png", "confluence", "#cf-picks-band", 390, "dark", "zh", 1),
            ("b2-05-conviction-320-dark-en.png", "confluence", "#cf-picks-band", 320, "dark", "en", 1),
            ("b2-05-conviction-320-dark-zh.png", "confluence", "#cf-picks-band", 320, "dark", "zh", 1),
            ("b2-08-map-rank-scope-390-dark-en.png", "map", "[data-view='map'] th[data-r3b2='08']", 390, "dark", "en", 1),
            ("b2-08-map-rank-scope-390-dark-zh.png", "map", "[data-view='map'] th[data-r3b2='08']", 390, "dark", "zh", 1),
            ("b2-09-moving-recent-wrong-1440-light-en.png", "moving", "[data-r3b2='09']", 1440, "light", "en", 1),
            ("b2-09-moving-recent-wrong-1440-light-zh.png", "moving", "[data-r3b2='09']", 1440, "light", "zh", 1),
            ("b2-11-headline-receipt-390-dark-en.png", "overview", "[data-r3b2='11']", 390, "dark", "en", 1),
            ("b2-11-headline-receipt-390-dark-zh.png", "overview", "[data-r3b2='11']", 390, "dark", "zh", 1),
            ("b2-11-headline-receipt-320-dark-en.png", "overview", "[data-r3b2='11']", 320, "dark", "en", 1),
            ("b2-11-headline-receipt-320-dark-zh.png", "overview", "[data-r3b2='11']", 320, "dark", "zh", 1),
            ("b2-15-money-context-1440-dark-en.png", "money", ".lead-foot", 1440, "dark", "en", 1),
            ("b2-15-money-context-1440-dark-zh.png", "money", ".lead-foot", 1440, "dark", "zh", 1),
            ("b2-15-money-context-390-dark-en.png", "money", ".lead-foot", 390, "dark", "en", 1),
            ("b2-15-money-context-390-dark-zh.png", "money", ".lead-foot", 390, "dark", "zh", 1),
        ]
        for filename, view, selector, physical, theme, lang, zoom in element_cells:
            state = {"view": view, "selector": selector, "physical_width": physical,
                     "zoom": zoom, "theme": theme, "lang": lang}
            path = out_dir / filename
            if reuse(path, "changed_state", state):
                continue
            css_width = physical // zoom
            ctx, page = context_page(browser, url, css_width, max(480, 1000 // zoom),
                                     dpr=zoom, mobile=physical < 768)
            settle(page, lang, theme, view)
            if zoom > 1:
                page.locator("#ref-harness").evaluate("el=>el.style.display='none'")
            loc = page.locator(selector).first
            assert loc.count() == 1 and loc.is_visible(), f"missing/hidden {filename}: {selector}"
            loc.screenshot(path=str(path))
            record(path, "changed_state", state)
            ctx.close()

        # Money colour-field matrix. These are visual evidence only: the
        # shadowed glyph/colour-field contrast axis remains explicitly UNMEASURED.
        for physical in (320, 390, 820):
            for theme in ("dark", "light"):
                for lang in ("en", "zh"):
                    state = {"view": "money", "width": physical, "theme": theme,
                             "lang": lang, "tile_census": "asserted_nonzero_in_capture",
                             "contrast_axis": "UNMEASURED"}
                    path = out_dir / f"money-heatmap-{physical}-{theme}-{lang}.png"
                    if reuse(path, "heatmap_matrix_unmeasured_axis", state):
                        continue
                    ctx, page = context_page(browser, url, physical, 900)
                    settle(page, lang, theme, "money")
                    heat = page.locator("#heatmap-scorecard")
                    assert heat.is_visible() and heat.locator(".hm-t").count() > 0
                    heat.screenshot(path=str(path))
                    record(path, "heatmap_matrix_unmeasured_axis",
                           {"view": "money", "width": physical, "theme": theme,
                            "lang": lang, "tile_census": heat.locator(".hm-t").count(),
                            "contrast_axis": "UNMEASURED"})
                    ctx.close()

        # Browse/List escape hatch opened at both collision-stress widths.
        for width, lang in ((320, "en"), (390, "zh")):
            state = {"view": "money", "width": width, "lang": lang,
                     "rows": "asserted_nonzero_in_capture"}
            path = out_dir / f"money-browse-names-{width}-dark-{lang}.png"
            if reuse(path, "browse_list_escape_hatch", state):
                continue
            ctx, page = context_page(browser, url, width, 900)
            settle(page, lang, "dark", "money")
            details = page.locator("#hm-names")
            details.evaluate("el=>el.open=true")
            page.wait_for_timeout(350)
            rows = details.locator("tbody tr").count()
            assert rows > 0
            details.screenshot(path=str(path))
            record(path, "browse_list_escape_hatch",
                   {"view": "money", "width": width, "lang": lang, "rows": rows})
            ctx.close()

        # The Moving grader note in ZH, and the shared receipt opened from the
        # B2-13 Overview control.
        path = out_dir / "moving-grader-note-390-dark-zh.png"
        state = {"view": "moving", "width": 390, "lang": "zh"}
        if not reuse(path, "grader_note_zh", state):
            ctx, page = context_page(browser, url, 390, 900)
            settle(page, "zh", "dark", "moving")
            note = page.locator(".r3-tr-note").first
            assert note.is_visible()
            note.screenshot(path=str(path))
            record(path, "grader_note_zh", state)
            ctx.close()

        ctx, page = context_page(browser, url, 390, 900)
        settle(page, "en", "dark", "overview")
        control = page.locator("[data-r3b1='02'] button.r3-rcpt")
        assert control.get_attribute("aria-controls") == "r3-receipt"
        control.click()
        page.wait_for_timeout(300)
        panel = page.locator("#r3-receipt")
        assert panel.count() == 1
        path = out_dir / "b2-13-shared-receipt-control-390-dark-en.png"
        control.locator("xpath=..").screenshot(path=str(path))
        record(path, "shared_receipt_control",
               {"view": "overview", "width": 390, "lang": "en",
                "aria_controls": control.get_attribute("aria-controls"),
                "target_present": panel.count() == 1,
                "target_visible_after_click": panel.is_visible(),
                "aria_expanded_after_click": control.get_attribute("aria-expanded")})
        ctx.close()

        browser.close()

    # Programmatic receipt for the screenshots themselves.
    payload = {
        "schema": "mastermind.xpv2.sector_r3b2.capture_manifest.v1",
        "candidate": candidate.name,
        "candidate_sha256": sha256(candidate),
        "capture_count": len(records),
        "screenshots": sorted(records, key=lambda r: r["file"]),
        "heatmap_colour_field_axis": "UNMEASURED",
        "notes": notes,
    }
    manifest = out_dir / "capture_manifest.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[capture] {len(records)} screenshots; candidate sha256={payload['candidate_sha256']}")
    print(f"[capture] manifest -> {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
