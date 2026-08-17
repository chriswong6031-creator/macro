#!/usr/bin/env python3
"""Generic page collector. Config-driven; no workstation paths."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import abs_from_repo, evidence_root, relpath  # noqa: E402
from pw_lib import (  # noqa: E402
    assert_and_shot,
    compact_error,
    extract,
    extract_sections,
    goto,
    launch_browser,
    load_aionui_cookies,
    new_page,
    resolve_targets,
    viewport_metrics,
)
from run_meta import dump_json  # noqa: E402
from selector_contract import as_resolve_spec  # noqa: E402


def load_page_config(page_id: str) -> dict:
    path = evidence_root() / "_config" / "pages" / f"{page_id}.json"
    return json.loads(path.read_text())


def dossier_path(cfg: dict) -> Path:
    return abs_from_repo(cfg["dossier_relpath"])


def extract_bundle(page, cfg: dict, viewport_h: int) -> dict:
    controls = resolve_targets(page, cfg.get("controls") or [])
    for c in controls:
        c.setdefault("id", c.get("stable_id"))
        c.setdefault("selector", c.get("selector_used") or c.get("selector_requested"))
        c.setdefault("section", c.get("evidence_section"))
    sections = extract_sections(page, cfg.get("sections") or [], viewport_h)
    ext = extract(page, cfg.get("controls") or [])
    return {"controls": controls, "sections": sections, "extract": ext}


def run_cycle_interaction(page, shots: Path, w: int, h: int, cookies_used: bool) -> dict:
    url_before = page.url
    rec = {
        "interaction_id": "I.detail.cycle",
        "element_stable_id": "E.detail.cycle.summary",
        "section_id": "S.detail.cycle",
        "preconditions": {
            "url": url_before,
            "baseline_state": "DETAIL_DEFAULT",
            "cookies_injected": cookies_used,
            "fresh_baseline": True,
        },
        "baseline_state": "DETAIL_DEFAULT",
        "action": {"type": "click", "target": "details.sv-deep > summary"},
        "expected_postconditions": {"open": True, "expr": "details.sv-deep.open === true"},
        "URL_before": url_before,
        "side_effect_class": "READ_ONLY",
        "screenshot_refs": [],
        "animation_evidence": None,
        "persistence": "none",
    }
    targets = resolve_targets(
        page,
        [
            {
                "stable_id": "E.detail.cycle",
                "selector_strategy": {"type": "css", "value": "details.sv-deep"},
                "expected_cardinality": 1,
            },
            {
                "stable_id": "E.detail.cycle.summary",
                "selector_strategy": {"type": "css", "value": "details.sv-deep > summary"},
                "expected_cardinality": 1,
            },
        ],
    )
    summary = next((t for t in targets if t["stable_id"] == "E.detail.cycle.summary"), None)
    if not summary or summary.get("resolution_status") != "RESOLVED":
        rec.update(
            {
                "pass": False,
                "attempt_status": "failed",
                "resulting_state": None,
                "observed_postconditions": {
                    "open": False,
                    "resolution": summary,
                },
                "error_code": "UNRESOLVED",
                "error_summary": "details.sv-deep > summary did not resolve uniquely",
            }
        )
        return rec
    try:
        loc = page.locator("details.sv-deep > summary")
        loc.scroll_into_view_if_needed()
        page.evaluate(
            """() => {
              const el = document.querySelector('details.sv-deep > summary');
              if (!el) return;
              el.scrollIntoView({block: 'center', inline: 'nearest'});
            }"""
        )
        page.wait_for_timeout(200)
        loc.click(timeout=8000)
        page.wait_for_timeout(400)
        observed = page.evaluate(
            """() => {
              const d = document.querySelector('details.sv-deep');
              return {
                found: !!d,
                open: !!(d && d.open),
                match_count: document.querySelectorAll('details.sv-deep').length,
                summary_text: d && d.querySelector('summary')
                  ? (d.querySelector('summary').innerText || '').trim().slice(0, 160)
                  : null
              };
            }"""
        )
        rec["observed_postconditions"] = observed
        rec["URL_after"] = page.url
        rec["url_changed"] = rec["URL_after"] != url_before
        if observed.get("open") is True:
            dest = shots / f"CYCLE_EXPANDED_{w}x{h}.png"
            shot = assert_and_shot(page, dest, w, h)
            rec["screenshot_refs"] = [shot.get("repo_relative_path") or relpath(dest)]
            rec["pass"] = True
            rec["attempt_status"] = "passed"
            rec["resulting_state"] = "CYCLE_EXPANDED"
        else:
            dest = shots / f"FAILED_CYCLE_EXPANDED_{w}x{h}.png"
            shot = assert_and_shot(page, dest, w, h)
            rec["screenshot_refs"] = [shot.get("repo_relative_path") or relpath(dest)]
            rec["pass"] = False
            rec["attempt_status"] = "failed"
            rec["resulting_state"] = None
            rec["error_code"] = "POSTCONDITION"
            rec["error_summary"] = "details.sv-deep.open !== true after click"
    except Exception as e:
        err = compact_error(e)
        rec.update(err)
        rec["pass"] = False
        rec["attempt_status"] = "failed"
        rec["resulting_state"] = None
        rec["observed_postconditions"] = {"open": False, "exception": err["error_summary"]}
        try:
            dest = shots / f"FAILED_CYCLE_EXPANDED_{w}x{h}.png"
            shot = assert_and_shot(page, dest, w, h)
            rec["screenshot_refs"] = [shot.get("repo_relative_path") or relpath(dest)]
        except Exception:
            pass
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", required=True)
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=1000)
    ap.add_argument("--cycle-only", action="store_true")
    args = ap.parse_args()
    cfg = load_page_config(args.page)
    cookies = load_aionui_cookies() if cfg.get("requires_auth") else []
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch_browser(p)
        ctx, page = new_page(browser, args.width, args.height, cookies or None)
        goto(page, cfg["url"])
        dossier = dossier_path(cfg)
        shots = dossier / "screenshots"
        if args.cycle_only:
            rec = run_cycle_interaction(page, shots, args.width, args.height, bool(cookies))
            dump_json(dossier / "raw" / "cycle-interaction.json", rec)
            print(json.dumps({k: rec.get(k) for k in ("pass", "attempt_status", "resulting_state", "error_summary")}, indent=2))
        else:
            bundle = extract_bundle(page, cfg, args.height)
            dump_json(dossier / f"extract-{args.width}x{args.height}.json", bundle["extract"])
            print("controls", len(bundle["controls"]), "sections", len(bundle["sections"]))
        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
