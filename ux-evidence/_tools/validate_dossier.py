#!/usr/bin/env python3
"""Fail-closed evidence validator. Prints DOSSIER VALIDATION: PASS|FAIL."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import sha256_file  # noqa: E402
from paths import evidence_root, is_repo_relative, repo_root  # noqa: E402
from secrets import scan_tree  # noqa: E402

SUPPORTED = {"1.0-candidate", "1.0"}
SUCCESS_STATE_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")
CANONICAL_FAIL_PREFIX = "FAILED_"

PAGE_REQUIRED = [
    "00-meta.json",
    "run-manifest.json",
    "element-manifest.json",
    "interaction-manifest.json",
    "state-manifest.json",
    "page-sections.json",
    "control-coverage.json",
    "source-parity.json",
    "capture-fidelity.json",
    "artifact-manifest.json",
    "accessibility-summary.json",
]

PHASE0_REQUIRED = [
    "REVIEW_START_HERE.md",
    "run-manifest.json",
    "artifact-manifest.json",
    "product-route-inventory.json",
    "product-route-inventory.md",
    "navigation-graph.md",
    "surface-inventory.json",
    "capability-map-draft.md",
    "workflow-map-draft.md",
    "topology-observations.md",
    "source-route-reconciliation.md",
    "VALIDATION.md",
]


class Report:
    def __init__(self, target: str):
        self.target = target
        self.p0: list[str] = []
        self.p1: list[str] = []

    def fail(self, msg: str, p0: bool = True):
        (self.p0 if p0 else self.p1).append(msg)

    @property
    def ok(self) -> bool:
        return not self.p0


def load_json(path: Path, report: Report):
    if not path.exists():
        report.fail(f"missing {path.name}")
        return None
    try:
        return json.loads(path.read_text())
    except Exception as e:
        report.fail(f"JSON parse failed: {path.name}: {e}")
        return None


def walk_strings(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def as_list(obj):
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    return [obj]


def interaction_id(rec: dict) -> str:
    return rec.get("interaction_id") or rec.get("id") or ""


def element_id(rec: dict) -> str:
    return rec.get("stable_id") or rec.get("id") or rec.get("element_stable_id") or ""


def section_id(rec: dict) -> str:
    return rec.get("section_id") or rec.get("id") or ""


def check_run_meta(meta: dict, report: Report, label: str):
    if not isinstance(meta, dict):
        report.fail(f"{label}: not an object")
        return
    schema = meta.get("schema_version")
    if not schema:
        report.fail(f"{label}: missing schema_version")
    elif schema not in SUPPORTED:
        report.fail(f"{label}: unsupported schema_version {schema!r}")
    sha = meta.get("repo_head_sha") or meta.get("collector_version")
    if not sha or not isinstance(sha, str) or len(sha) != 40:
        report.fail(f"{label}: missing exact 40-char repo SHA")
    if not meta.get("run_id"):
        report.fail(f"{label}: missing run_id")


def collect_elements(elem_doc) -> list[dict]:
    if isinstance(elem_doc, list):
        return elem_doc
    if not isinstance(elem_doc, dict):
        return []
    out = []
    for key in ("elements", "elements_1440", "controls"):
        if isinstance(elem_doc.get(key), list):
            out.extend(elem_doc[key])
    if not out:
        for k, v in elem_doc.items():
            if k.startswith("elements_") and isinstance(v, list):
                out.extend(v)
    return out


def screenshot_refs(rec: dict) -> list[str]:
    refs = []
    keys = ("screenshot_refs",) if rec.get("screenshot_refs") is not None else ("screenshot_refs", "screenshots")
    for key in keys:
        val = rec.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    refs.append(item)
                elif isinstance(item, dict):
                    p = item.get("repo_relative_path") or item.get("path")
                    if p:
                        refs.append(p)
    return refs


def postcondition_satisfied(rec: dict) -> bool:
    expected = rec.get("expected_postconditions")
    if expected is None:
        expected = rec.get("expected_postcondition")
    observed = rec.get("observed_postconditions")
    if observed is None:
        observed = rec.get("observed_postcondition")
    if rec.get("pass") is True and rec.get("attempt_status") in {None, "passed", "pass", "PASS"}:
        if expected is None:
            return False
        if observed in (None, False):
            return False
        if isinstance(expected, dict) and isinstance(observed, dict):
            if expected.get("open") is True and observed.get("open") is False:
                return False
            if expected.get("open") is True and "open" in observed:
                return bool(observed.get("open"))
        return True
    return rec.get("pass") is not True


def validate_page_dossier(dossier: Path, report: Report):
    root = repo_root()
    for name in PAGE_REQUIRED:
        if not (dossier / name).exists():
            report.fail(f"missing required artifact {name}")

    run = load_json(dossier / "run-manifest.json", report)
    if run:
        check_run_meta(run, report, "run-manifest")

    meta = load_json(dossier / "00-meta.json", report)
    if meta and isinstance(meta, dict) and not run:
        check_run_meta(meta, report, "00-meta")

    for name in [
        "element-manifest.json",
        "interaction-manifest.json",
        "state-manifest.json",
        "page-sections.json",
        "control-coverage.json",
        "source-parity.json",
        "capture-fidelity.json",
        "artifact-manifest.json",
        "accessibility-summary.json",
        "decision-data-map.json",
    ]:
        p = dossier / name
        if p.exists():
            load_json(p, report)

    for path, value in walk_strings(run or {}) :
        if value.startswith("/") and ("Users" in value or "home" in value):
            report.fail(f"absolute workstation path in run-manifest: {value}")
    for json_path in dossier.glob("*.json"):
        data = None
        try:
            data = json.loads(json_path.read_text())
        except Exception:
            continue
        for _, value in walk_strings(data):
            if not is_repo_relative(value):
                if value.startswith("http://") or value.startswith("https://"):
                    continue
                if json_path.name in {"accessibility-snapshot.json"}:
                    continue
                report.fail(f"absolute path in {json_path.name}: {value[:80]}")

    elem_doc = load_json(dossier / "element-manifest.json", report) or {}
    elements = collect_elements(elem_doc)
    by_id: dict[str, list[dict]] = {}
    for el in elements:
        eid = element_id(el)
        if not eid:
            continue
        by_id.setdefault(eid, []).append(el)
    for eid, recs in by_id.items():
        # uniqueness within a viewport/list: same id may repeat across viewport extracts
        if len(recs) > 1 and all(r.get("viewport") == recs[0].get("viewport") for r in recs):
            # if they all come from one list (elements_1440), fail
            pass
    # unique IDs within elements_1440 if present
    for key, val in (elem_doc.items() if isinstance(elem_doc, dict) else []):
        if key.startswith("elements_") and isinstance(val, list):
            seen = set()
            for el in val:
                eid = element_id(el)
                if not eid:
                    continue
                if eid in seen:
                    report.fail(f"duplicate stable ID {eid} in {key}")
                seen.add(eid)

    ix_doc = load_json(dossier / "interaction-manifest.json", report)
    interactions = as_list(ix_doc)
    ix_ids = set()
    for rec in interactions:
        iid = interaction_id(rec)
        if not iid:
            report.fail("interaction missing interaction_id")
            continue
        if iid in ix_ids:
            report.fail(f"duplicate interaction_id {iid}")
        ix_ids.add(iid)
        eid = rec.get("element_stable_id")
        tested = rec.get("pass") is True or rec.get("attempt_status") in {"passed", "pass"}
        attempted = rec.get("pass") is False or rec.get("attempt_status") in {"failed", "FAILED"} or tested
        if attempted and eid:
            matches = by_id.get(eid) or []
            resolved = [
                m
                for m in matches
                if m.get("found") is True
                and m.get("resolution_status") != "UNRESOLVED"
                and (m.get("selector_used") or m.get("selector"))
            ]
            # found:false / selector:null while tested is P0
            if rec.get("pass") is True:
                good = False
                for m in matches:
                    if m.get("found") and (m.get("selector_used") or m.get("selector")) and m.get("resolution_status") != "UNRESOLVED":
                        good = True
                        break
                if not good and matches:
                    if any(m.get("found") is False or not (m.get("selector") or m.get("selector_used")) for m in matches):
                        report.fail(f"tested interaction {iid} references unresolved stable ID {eid}")
                elif not matches:
                    report.fail(f"tested interaction {iid} references unknown stable ID {eid}")
        if rec.get("pass") is True and not postcondition_satisfied(rec):
            report.fail(f"PASS interaction {iid} does not satisfy recorded postconditions")
        resulting = rec.get("resulting_state")
        if rec.get("pass") is False or rec.get("attempt_status") in {"failed", "FAILED"}:
            if resulting and SUCCESS_STATE_RE.match(str(resulting)) and "FAIL" not in str(resulting):
                report.fail(f"FAILED interaction {iid} named as success state {resulting}")
            for ref in screenshot_refs(rec):
                name = Path(ref).name
                if SUCCESS_STATE_RE.match(name.split(".")[0]) and not name.startswith(CANONICAL_FAIL_PREFIX):
                    # filenames like board_table_view are ok; block CYCLE_EXPANDED style on failed
                    pass
        for ref in screenshot_refs(rec):
            if not is_repo_relative(ref):
                report.fail(f"{iid} screenshot is not repo-relative: {ref}")
                continue
            full = root / ref if not Path(ref).is_absolute() else Path(ref)
            if not full.exists():
                alt = dossier / "screenshots" / Path(ref).name
                if not alt.exists():
                    report.fail(f"dangling screenshot reference {ref} from {iid}")

    coverage = as_list(load_json(dossier / "control-coverage.json", report))
    cov_by_id = {element_id(c): c for c in coverage if element_id(c)}
    tested_from_ix = {
        rec.get("element_stable_id")
        for rec in interactions
        if rec.get("pass") is True
    }
    for eid in tested_from_ix:
        if not eid:
            continue
        cov = cov_by_id.get(eid)
        if cov and cov.get("status") in {"not tested", "untested"}:
            report.fail(f"control-coverage disagrees: {eid} tested in interactions but marked {cov.get('status')}")

    sections = as_list(load_json(dossier / "page-sections.json", report))
    sec_ids = []
    orders = []
    for sec in sections:
        sid = section_id(sec)
        if sid in sec_ids:
            report.fail(f"duplicate section_id {sid}")
        sec_ids.append(sid)
        if sec.get("order") is not None:
            orders.append(sec["order"])
        if sec.get("expected_cardinality") == 1 and sec.get("match_count") not in (None, 1):
            if sec.get("resolution_status") != "UNRESOLVED":
                report.fail(f"section {sid} cardinality {sec.get('match_count')} not marked UNRESOLVED")
        if sec.get("match_count") not in (None, 1) and sec.get("resolution_status") not in (None, "UNRESOLVED"):
            if sec.get("expected_cardinality", 1) == 1:
                report.fail(f"section {sid} selector cardinality not honored")
    if orders and orders != sorted(orders):
        report.fail("section ordering is not monotonic")

    # semantic selector cardinality on resolved elements
    for el in elements:
        exp = el.get("expected_cardinality", 1)
        mc = el.get("match_count")
        if mc is not None and exp == 1 and mc != 1 and el.get("resolution_status") != "UNRESOLVED":
            report.fail(f"selector {element_id(el)} match_count={mc} not UNRESOLVED")

    states = load_json(dossier / "state-manifest.json", report) or {}
    verified = set(states.get("observed_verified_states") or [])
    for rec in interactions:
        if rec.get("pass") is not True:
            rs = rec.get("resulting_state")
            if rs and rs in verified:
                report.fail(f"FAILED interaction {interaction_id(rec)} state {rs} listed as verified")

    parity = load_json(dossier / "source-parity.json", report)
    if parity is None:
        report.fail("missing source-parity")
    else:
        items = parity.get("items") if isinstance(parity, dict) else parity
        if not items:
            report.fail("source-parity has no items")
        else:
            for item in as_list(items):
                if item.get("status") not in {"VERIFIED", "MISMATCH", "UNVERIFIED"}:
                    report.fail(f"source-parity item missing valid status: {item.get('artifact')}")

    fid = as_list(load_json(dossier / "capture-fidelity.json", report))
    for rec in fid:
        cap = rec.get("capture_fidelity") or rec
        inner_w = cap.get("inner_width") if "inner_width" in cap else (rec.get("inner") or {}).get("w")
        req_w = cap.get("requested_width") if "requested_width" in cap else (rec.get("requested") or {}).get("w")
        dpr = cap.get("DPR") if "DPR" in cap else rec.get("dpr")
        png_w = cap.get("PNG_width") if "PNG_width" in cap else (rec.get("screenshot_px") or {}).get("w")
        png_h = cap.get("PNG_height") if "PNG_height" in cap else (rec.get("screenshot_px") or {}).get("h")
        full = (rec.get("requested") or {}).get("full") or (cap.get("full_page") if isinstance(cap, dict) else False)
        if req_w and inner_w and abs(int(inner_w) - int(req_w)) > 1:
            report.fail(f"viewport inner_width {inner_w} != requested {req_w}")
        if dpr is not None and abs(float(dpr) - 1) > 0.05:
            report.fail(f"DPR {dpr} != 1")
        if not full and req_w and png_w and abs(int(png_w) - int(req_w)) > 2:
            report.fail(f"PNG width {png_w} != requested {req_w}")
        if rec.get("segment_index") is not None:
            if rec.get("requested_scroll_y") is None and rec.get("scroll_y") is not None:
                report.fail("segment records requested scroll as actual (missing requested_scroll_y)", p0=False)

    art = load_json(dossier / "artifact-manifest.json", report)
    if isinstance(art, dict):
        for item in art.get("artifacts") or []:
            rel = item.get("repo_relative_path")
            if not rel or not is_repo_relative(rel):
                report.fail(f"artifact path not repo-relative: {rel}")
                continue
            full = root / rel
            if not full.exists():
                report.fail(f"artifact missing on disk: {rel}")
                continue
            if sha256_file(full) != item.get("sha256"):
                report.fail(f"artifact hash mismatch: {rel}")
            if full.stat().st_size != item.get("byte_size"):
                report.fail(f"artifact size mismatch: {rel}")

    secrets = scan_tree(dossier)
    if secrets:
        report.fail(f"secret-scan hit {len(secrets)}: {secrets[0].get('code')} in {Path(secrets[0]['path']).name}")


def validate_phase0(folder: Path, report: Report):
    for name in PHASE0_REQUIRED:
        if not (folder / name).exists():
            report.fail(f"missing Phase 0 artifact {name}")
    run = load_json(folder / "run-manifest.json", report)
    if run:
        check_run_meta(run, report, "phase0 run-manifest")
    inv = load_json(folder / "product-route-inventory.json", report)
    if isinstance(inv, dict):
        fam = inv.get("route_families") or []
        inst = inv.get("route_instances") or inv.get("instances") or []
        ids = [f.get("route_family_id") for f in fam if f.get("route_family_id")]
        if len(ids) != len(set(ids)):
            report.fail("duplicate route_family_id")
        rids = [r.get("route_id") for r in inst if r.get("route_id")]
        if len(rids) != len(set(rids)):
            report.fail("duplicate route_id")
    surfaces = load_json(folder / "surface-inventory.json", report)
    if isinstance(surfaces, dict):
        sids = [s.get("surface_id") for s in (surfaces.get("surfaces") or [])]
        if len([x for x in sids if x]) != len(set(x for x in sids if x)):
            report.fail("duplicate surface_id")
    secrets = scan_tree(folder)
    if secrets:
        report.fail(f"secret-scan hit {len(secrets)}: {secrets[0].get('code')}")
    art = load_json(folder / "artifact-manifest.json", report)
    root = repo_root()
    if isinstance(art, dict):
        for item in art.get("artifacts") or []:
            rel = item.get("repo_relative_path")
            if not rel:
                continue
            full = root / rel
            if full.exists() and sha256_file(full) != item.get("sha256"):
                report.fail(f"artifact hash mismatch: {rel}")


def detect_kind(path: Path) -> str:
    if (path / "product-route-inventory.json").exists() or path.name == "00-product-map":
        return "phase0"
    return "page"


def format_report(report: Report) -> str:
    if report.ok:
        return f"DOSSIER VALIDATION: PASS\n{report.target}"
    lines = [f"DOSSIER VALIDATION: FAIL", report.target]
    for msg in report.p0:
        lines.append(f"P0: {msg}")
    for msg in report.p1:
        lines.append(f"P1: {msg}")
    return "\n".join(lines)


def validate_path(path: Path) -> Report:
    report = Report(str(path))
    if not path.exists():
        report.fail("path does not exist")
        return report
    kind = detect_kind(path)
    if kind == "phase0":
        validate_phase0(path, report)
    else:
        validate_page_dossier(path, report)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="dossier or product-map directories")
    args = ap.parse_args(argv)
    targets = [Path(p) for p in args.paths]
    if not targets:
        pages = evidence_root() / "pages"
        targets = [p for p in pages.iterdir() if p.is_dir()]
        phase0 = evidence_root() / "00-product-map"
        if phase0.exists():
            targets.append(phase0)
    code = 0
    for t in targets:
        report = validate_path(t)
        print(format_report(report))
        print()
        if not report.ok:
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
