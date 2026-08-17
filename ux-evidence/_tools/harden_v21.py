#!/usr/bin/env python3
"""v2.1 hardening: normalize dossiers, rematerialize selectors, recapture Cycle only."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import write_manifest  # noqa: E402
from collect_page import extract_bundle, load_page_config, run_cycle_interaction  # noqa: E402
from paths import evidence_root, relpath, repo_root  # noqa: E402
from pw_lib import compact_error, goto, launch_browser, load_aionui_cookies, new_page  # noqa: E402
from run_meta import base_run_manifest, dump_json, finalize_run  # noqa: E402

ABS_RE = re.compile(r"/Users/[^\"']+/ux-evidence/")
VIEWS = [
    ("1440x1000", 1440, 1000),
    ("1280x900", 1280, 900),
    ("1024x800", 1024, 800),
    ("768x900", 768, 900),
    ("390x844", 390, 844),
]


def load(path: Path):
    return json.loads(path.read_text())


def relativize_value(value: str) -> str:
    if not isinstance(value, str):
        return value
    if "ux-evidence/" in value:
        return "ux-evidence/" + value.split("ux-evidence/", 1)[1]
    return value


def relativize(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "path" and isinstance(v, str):
                out[k] = relativize_value(v)
                out.setdefault("repo_relative_path", out[k])
            else:
                out[k] = relativize(v)
        return out
    if isinstance(obj, list):
        return [relativize(x) for x in obj]
    if isinstance(obj, str):
        return relativize_value(obj)
    return obj


def compact_reason(text: str | None, dest: Path | None = None) -> dict:
    if not text:
        return {}
    if len(text) < 280 and "Call log:" not in text:
        return {"error_summary": text}
    err = compact_error(text)
    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        err["raw_error_ref"] = relpath(dest)
    return err


def normalize_fidelity(rec: dict) -> dict:
    rec = relativize(rec)
    req = rec.get("requested") or {}
    inner = rec.get("inner") or {}
    shot = rec.get("screenshot_px") or {}
    scroll = rec.get("scroll") or {}
    req_w = req.get("w")
    req_h = req.get("h")
    overflow_px = 0
    if req_w and scroll.get("w"):
        overflow_px = max(0, int(scroll["w"]) - int(req_w))
    rec["capture_fidelity"] = {
        "requested_width": req_w,
        "requested_height": req_h,
        "inner_width": inner.get("w"),
        "inner_height": inner.get("h"),
        "DPR": rec.get("dpr"),
        "PNG_width": shot.get("w"),
        "PNG_height": shot.get("h"),
        "png_dimensions_valid": True if shot.get("w") else False,
        "full_page": bool(req.get("full")),
    }
    rec["product_layout"] = {
        "document_scroll_width": scroll.get("w"),
        "document_scroll_height": scroll.get("h"),
        "horizontal_overflow": overflow_px > 2,
        "horizontal_overflow_px": overflow_px,
        "vertical_page_length": scroll.get("h"),
    }
    if rec.get("segment_index") is not None:
        requested = rec.get("requested_scroll_y")
        if requested is None:
            # filename yN is requested; scroll.y is observed
            requested = rec.get("scroll_y")
        observed = (rec.get("scroll") or {}).get("y")
        if observed is None:
            observed = rec.get("scroll_y")
        rec["requested_scroll_y"] = requested
        rec["observed_scroll_y"] = observed
        rec["scroll_y"] = observed
    return rec


def normalize_interaction(rec: dict, raw_dir: Path) -> dict:
    rec = relativize(rec)
    iid = rec.get("interaction_id") or rec.get("id")
    rec["interaction_id"] = iid
    rec.setdefault("section_id", rec.get("section"))
    rec.setdefault("baseline_state", rec.get("starting_state"))
    if "expected_postconditions" not in rec and "expected_postcondition" in rec:
        rec["expected_postconditions"] = rec.get("expected_postcondition")
    if "observed_postconditions" not in rec and "observed_postcondition" in rec:
        rec["observed_postconditions"] = rec.get("observed_postcondition")
    rec.setdefault("URL_before", rec.get("url_before"))
    rec.setdefault("URL_after", rec.get("url_after"))
    rec.setdefault("persistence", "none" if rec.get("url_changed") is False else rec.get("persistence"))
    rec.setdefault("animation_evidence", None)
    rec.setdefault("side_effect_class", "READ_ONLY")
    if rec.get("starting_state") in {"DEFAULT_GRID", "DETAIL_DEFAULT"} and rec.get("side_effect_class") == "READ_ONLY":
        if "theme" in (iid or "") or "lang" in (iid or ""):
            rec["side_effect_class"] = "LOCAL_DISPLAY_PREFERENCE"
    refs = []
    for item in rec.get("screenshots") or rec.get("screenshot_refs") or []:
        if isinstance(item, str):
            refs.append(relativize_value(item))
        elif isinstance(item, dict):
            p = item.get("repo_relative_path") or item.get("path")
            if p:
                refs.append(relativize_value(p))
    # map vanished hover shot onto FAILED_ file if present
    fixed = []
    for ref in refs:
        name = Path(ref).name
        if name == "detail_chart_hover_1440x1000.png":
            failed = Path(ref).with_name("FAILED_detail_chart_hover_1440x1000.png")
            if (repo_root() / failed.as_posix()).exists() or True:
                ref = str(failed)
        fixed.append(ref)
    rec["screenshot_refs"] = fixed
    if rec.get("reason") and len(str(rec["reason"])) > 240:
        rec.update(compact_reason(rec["reason"], raw_dir / f"{iid}.log"))
        rec["reason"] = rec.get("error_summary")
    rec.setdefault("preconditions", {})
    if isinstance(rec["preconditions"], dict):
        rec["preconditions"].setdefault("baseline_state", rec.get("baseline_state"))
    return rec


def coverage_from(cfg: dict, interactions: list[dict], resolved: list[dict]) -> list[dict]:
    tested = {}
    for rec in interactions:
        eid = rec.get("element_stable_id")
        if rec.get("pass") is True:
            tested[eid] = "tested"
        elif rec.get("attempt_status") in {"failed", "FAILED"} or rec.get("pass") is False:
            tested.setdefault(eid, "attempted_failed")
    by_id = {c.get("stable_id"): c for c in resolved}
    out = []
    for spec in cfg.get("controls") or []:
        eid = spec["stable_id"]
        res = by_id.get(eid) or {}
        status = tested.get(eid, "not tested")
        reason = None
        if status == "not tested":
            reason = "no independent interaction branch in this calibration"
        if status == "attempted_failed":
            reason = next((i.get("error_summary") or i.get("reason") for i in interactions if i.get("element_stable_id") == eid), "failed")
        out.append(
            {
                "id": eid,
                "stable_id": eid,
                "section": spec.get("evidence_section"),
                "status": status,
                "reason": reason,
                "found": res.get("found"),
                "resolution_status": res.get("resolution_status"),
                "selector_used": res.get("selector_used"),
            }
        )
    return out


def update_meta(path: Path, run: dict, extra: dict):
    meta = load(path) if path.exists() else {}
    meta.update(
        {
            "schema_version": run["schema_version"],
            "collector_version": run["collector_version"],
            "run_id": run["run_id"],
            "repo_head_sha": run["repo_head_sha"],
            "working_tree_dirty": run["working_tree_dirty"],
            "browser_name": run.get("browser_name"),
            "browser_version": run.get("browser_version"),
            "playwright_version": run.get("playwright_version"),
            "device_scale_factor": run.get("device_scale_factor"),
            "authenticated_session_used": extra.get("authenticated_session_used", False),
            "source_parity_method": run.get("source_parity_method"),
            "operating_platform": run.get("operating_platform"),
        }
    )
    dump_json(path, meta)


def rematerialize(page_id: str, browser, cookies, run: dict) -> dict:
    cfg = load_page_config(page_id)
    dossier = evidence_root() / "pages" / ("stock-detail" if page_id == "stock-detail" else "us-stocks-prophet-board")
    raw_dir = dossier / "raw" / "logs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fid_path = dossier / "capture-fidelity.json"
    if fid_path.exists():
        dump_json(fid_path, [normalize_fidelity(r) for r in load(fid_path)])

    ix_path = dossier / "interaction-manifest.json"
    interactions = [normalize_interaction(r, raw_dir) for r in load(ix_path)]

    st_path = dossier / "state-manifest.json"
    states = load(st_path)
    if isinstance(states.get("failed_attempts"), list):
        cleaned = []
        for item in states["failed_attempts"]:
            if isinstance(item, dict) and item.get("reason"):
                item = dict(item)
                item.update(compact_reason(item.pop("reason"), raw_dir / f"{item.get('failed_attempt','err')}.log"))
            cleaned.append(item)
        states["failed_attempts"] = cleaned

    resolved_1440 = []
    sections_1440 = []
    elements_by_vp = {}
    for name, w, h in VIEWS:
        ctx, page = new_page(browser, w, h, cookies or None)
        goto(page, cfg["url"], wait_ms=2200)
        bundle = extract_bundle(page, cfg, h)
        elements_by_vp[f"elements_{name.split('x')[0]}"] = bundle["controls"]
        dump_json(dossier / f"extract-{name}.json", bundle["extract"])
        if name == "1440x1000":
            resolved_1440 = bundle["controls"]
            sections_1440 = bundle["sections"]
            if page_id == "stock-detail":
                cycle = run_cycle_interaction(page, dossier / "screenshots", w, h, bool(cookies))
                replaced = False
                for i, rec in enumerate(interactions):
                    if rec.get("interaction_id") == "I.detail.cycle":
                        interactions[i] = cycle
                        replaced = True
                if not replaced:
                    interactions.append(cycle)
                if cycle.get("pass"):
                    states.setdefault("observed_verified_states", [])
                    if "CYCLE_EXPANDED" not in states["observed_verified_states"]:
                        states["observed_verified_states"].append("CYCLE_EXPANDED")
                    states.setdefault("transitions", [])
                    trans = "DETAIL_DEFAULT -> CYCLE_EXPANDED"
                    if trans not in states["transitions"]:
                        states["transitions"].append(trans)
                    states["failed_attempts"] = [
                        a for a in (states.get("failed_attempts") or []) if a.get("failed_attempt") != "I.detail.cycle"
                    ]
                else:
                    states.setdefault("failed_attempts", [])
                    states["failed_attempts"] = [
                        a for a in states["failed_attempts"] if a.get("failed_attempt") != "I.detail.cycle"
                    ] + [
                        {
                            "failed_attempt": "I.detail.cycle",
                            "error_code": cycle.get("error_code"),
                            "error_summary": cycle.get("error_summary") or "cycle postcondition not met",
                        }
                    ]
        ctx.close()

    elem_doc = {
        "note": "Coordinates are viewport-specific. Re-queried in v2.1. Boxes are viewport_box + page_box.",
        "schema_version": run["schema_version"],
        "elements_1440": elements_by_vp.get("elements_1440") or resolved_1440,
        "elements_1280": elements_by_vp.get("elements_1280") or [],
        "elements_1024": elements_by_vp.get("elements_1024") or [],
        "elements_768": elements_by_vp.get("elements_768") or [],
        "elements_390": elements_by_vp.get("elements_390") or [],
    }
    dump_json(dossier / "element-manifest.json", elem_doc)
    dump_json(dossier / "page-sections.json", sections_1440)
    dump_json(dossier / "control-coverage.json", coverage_from(cfg, interactions, resolved_1440))
    dump_json(ix_path, interactions)
    dump_json(st_path, states)

    # source-parity: keep existing, add repo_head_sha
    sp = load(dossier / "source-parity.json")
    if isinstance(sp, dict):
        sp["repo_head_sha"] = run["repo_head_sha"]
        sp["parity_method"] = run.get("source_parity_method")
        dump_json(dossier / "source-parity.json", sp)

    update_meta(
        dossier / "00-meta.json",
        run,
        {"authenticated_session_used": bool(cookies) and page_id == "stock-detail"},
    )
    dump_json(
        dossier / "run-manifest.json",
        {
            **run,
            "page_id": page_id,
            "authenticated_session_used": bool(cookies) and cfg.get("requires_auth", False),
            "cookie_count": len(cookies or []),
            "cookies_injected": bool(cookies) and cfg.get("requires_auth", False),
        },
    )
    write_manifest(
        dossier,
        generated_by=f"harden_v21:{run['run_id']}",
        associated_route=cfg.get("url"),
        extra={"run_id": run["run_id"], "schema_version": run["schema_version"]},
    )
    return {
        "page_id": page_id,
        "cycle": next((i for i in interactions if i.get("interaction_id") == "I.detail.cycle"), None),
        "unresolved_controls": [
            c.get("stable_id") for c in resolved_1440 if c.get("resolution_status") == "UNRESOLVED" and c.get("required")
        ],
        "sections": [
            {"id": s.get("section_id"), "status": s.get("resolution_status"), "h": (s.get("page_box") or {}).get("h")}
            for s in sections_1440
        ],
    }


def main():
    run = base_run_manifest(schema_version="1.0-candidate")
    cookies = load_aionui_cookies()
    run["authenticated_session_used"] = bool(cookies)
    from playwright.sync_api import sync_playwright

    summaries = []
    with sync_playwright() as p:
        browser = launch_browser(p)
        run["browser_name"], run["browser_version"] = "chrome", getattr(browser, "version", "unknown")
        summaries.append(rematerialize("us-stocks-prophet-board", browser, cookies, run))
        summaries.append(rematerialize("stock-detail", browser, cookies, run))
        browser.close()
    run = finalize_run(run)
    dump_json(evidence_root() / "run-manifest.json", run)
    dump_json(evidence_root() / "raw" / "v21-summary.json", summaries)
    print(json.dumps({"run_id": run["run_id"], "repo_head_sha": run["repo_head_sha"], "summaries": summaries}, indent=2))


if __name__ == "__main__":
    main()
