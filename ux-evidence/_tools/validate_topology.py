#!/usr/bin/env python3
"""Phase 0.1 topology integrity validator. Prints TOPOLOGY MACHINE GATE: PASS|FAIL."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import sha256_file  # noqa: E402
from paths import evidence_root, repo_root  # noqa: E402
from secrets import scan_tree  # noqa: E402
from topology_lib import ROUTE_CLASSES  # noqa: E402

TOPOLOGY_VERSIONS = {"1.1-candidate"}
REQUIRED = [
    "REVIEW_START_HERE.md",
    "VALIDATION.md",
    "run-manifest.json",
    "artifact-manifest.json",
    "route-family-registry.json",
    "route-family-registry.md",
    "route-instance-inventory.json",
    "source-route-reconciliation.md",
    "navigation-tree.json",
    "navigation-tree.md",
    "navigation-graph.json",
    "navigation-graph.md",
    "surface-inventory.json",
    "surface-inventory.md",
    "capability-inventory.json",
    "capability-map-draft.md",
    "workflow-edges.json",
    "workflow-map-draft.md",
    "terminology-map.json",
    "terminology-map.md",
    "consolidation-history-observations.md",
    "topology-observations.md",
]


class Report:
    def __init__(self, target: str):
        self.target = target
        self.p0: list[str] = []

    def fail(self, msg: str):
        self.p0.append(msg)

    @property
    def ok(self) -> bool:
        return not self.p0


def load(path: Path, report: Report):
    if not path.exists():
        report.fail(f"missing {path.name}")
        return None
    try:
        return json.loads(path.read_text())
    except Exception as e:
        report.fail(f"JSON parse failed {path.name}: {e}")
        return None


def schema_defs():
    raw = json.loads((evidence_root() / "_schema" / "product-topology.schema.json").read_text())
    return raw, raw.get("$defs") or {}


def validate_items(items, defn_name, defs, report, label):
    schema = {"$defs": defs, **defs[defn_name]}
    for i, item in enumerate(items or []):
        try:
            jsonschema.validate(item, schema)
        except jsonschema.ValidationError as e:
            report.fail(f"{label}[{i}] schema: {e.message}")


def validate_topology(folder: Path) -> Report:
    report = Report(str(folder))
    for name in REQUIRED:
        if not (folder / name).exists():
            report.fail(f"missing required artifact {name}")

    run = load(folder / "run-manifest.json", report) or {}
    topo_ver = run.get("topology_schema_version") or run.get("schema_version")
    if topo_ver not in TOPOLOGY_VERSIONS:
        report.fail(f"unsupported topology schema {topo_ver!r}")
    sha = run.get("repo_head_sha") or run.get("collector_version")
    if not sha or len(str(sha)) != 40:
        report.fail("missing exact 40-char SHA")
    if run.get("canonical") is not False:
        if run.get("working_tree_dirty") is True:
            report.fail("canonical run has working_tree_dirty=true")

    _, defs = schema_defs()
    fam_doc = load(folder / "route-family-registry.json", report) or {}
    inst_doc = load(folder / "route-instance-inventory.json", report) or {}
    surf_doc = load(folder / "surface-inventory.json", report) or {}
    cap_doc = load(folder / "capability-inventory.json", report) or {}
    edge_doc = load(folder / "workflow-edges.json", report) or {}
    nav_doc = load(folder / "navigation-tree.json", report) or {}

    families = fam_doc.get("route_families") if isinstance(fam_doc, dict) else fam_doc
    instances = inst_doc.get("route_instances") if isinstance(inst_doc, dict) else inst_doc
    surfaces = surf_doc.get("surfaces") if isinstance(surf_doc, dict) else surf_doc
    caps = cap_doc.get("capabilities") if isinstance(cap_doc, dict) else cap_doc
    edges = edge_doc.get("edges") if isinstance(edge_doc, dict) else edge_doc
    workflows = (edge_doc.get("workflows") if isinstance(edge_doc, dict) else None) or []
    nav_edges = nav_doc.get("edges") if isinstance(nav_doc, dict) else nav_doc

    validate_items(families, "route_family", defs, report, "route_family")
    validate_items(instances, "route_instance", defs, report, "route_instance")
    validate_items(surfaces, "surface", defs, report, "surface")
    validate_items(caps, "capability", defs, report, "capability")
    validate_items(edges, "workflow_edge", defs, report, "workflow_edge")
    validate_items(workflows, "workflow", defs, report, "workflow")
    validate_items(nav_edges, "navigation_edge", defs, report, "navigation_edge")

    fam_ids = [f.get("route_family_id") for f in (families or []) if f.get("route_family_id")]
    if len(fam_ids) != len(set(fam_ids)):
        report.fail("duplicate route_family_id")
    fam_set = set(fam_ids)
    inst_ids = [r.get("route_id") for r in (instances or []) if r.get("route_id")]
    if len(inst_ids) != len(set(inst_ids)):
        report.fail("duplicate route_id")

    # collision check: unrelated URL hosts/paths under one family
    by_fam = {}
    for r in instances or []:
        fid = r.get("route_family_id")
        if fid not in fam_set:
            report.fail(f"instance {r.get('route_id')} references unknown family {fid}")
        if r.get("route_class") not in ROUTE_CLASSES:
            report.fail(f"invalid route_class on {r.get('route_id')}")
        by_fam.setdefault(fid, []).append(r)
        tgt = r.get("canonical_target")
        if tgt and not isinstance(tgt, str):
            report.fail(f"unresolved canonical target on {r.get('route_id')}")

    # family pattern conflict: same family, wildly different URL hosts
    for fid, recs in by_fam.items():
        hosts = set()
        for r in recs:
            u = r.get("requested_url") or ""
            if u.startswith("http"):
                hosts.add(u.split("/")[2])
        if len(hosts) > 1:
            report.fail(f"unrelated instances collided under family {fid}: {sorted(hosts)}")

    surf_ids = [s.get("surface_id") for s in (surfaces or []) if s.get("surface_id")]
    if len(surf_ids) != len(set(surf_ids)):
        report.fail("duplicate surface_id")
    surf_set = set(surf_ids)
    inst_set = set(inst_ids)
    for s in surfaces or []:
        if s.get("route_family_id") not in fam_set:
            report.fail(f"surface {s.get('surface_id')} unknown family {s.get('route_family_id')}")
        rid = s.get("representative_route_id")
        if rid and rid not in inst_set and rid != "R.shell.global":
            report.fail(f"surface {s.get('surface_id')} unknown representative route {rid}")
        box = s.get("page_box") or {}
        if s.get("geometry_status") == "RESOLVED" and box:
            if (box.get("w") or 0) < 0 or (box.get("h") or 0) < 0:
                report.fail(f"impossible geometry on {s.get('surface_id')}")

    cap_ids = [c.get("capability_id") for c in (caps or []) if c.get("capability_id")]
    if len(cap_ids) != len(set(cap_ids)):
        report.fail("duplicate capability_id")
    cap_set = set(cap_ids)
    for c in caps or []:
        if not c.get("evidence_refs"):
            report.fail(f"capability {c.get('capability_id')} has no evidence refs")
        for sid in c.get("supporting_surface_ids") or []:
            if sid not in surf_set:
                report.fail(f"capability {c.get('capability_id')} unknown surface {sid}")
        for fid in c.get("supporting_route_family_ids") or []:
            if fid not in fam_set:
                report.fail(f"capability {c.get('capability_id')} unknown family {fid}")
        if c.get("evidence_status") in {"OBSERVED_BROWSER", "OBSERVED_SOURCE", "OBSERVED_BOTH"}:
            if not c.get("evidence_refs"):
                report.fail(f"OBSERVED capability {c.get('capability_id')} lacks evidence")

    wf_ids = [w.get("workflow_id") for w in workflows if w.get("workflow_id")]
    if len(wf_ids) != len(set(wf_ids)):
        report.fail("duplicate workflow_id")
    for w in workflows:
        refs = []
        for step in w.get("ordered_steps") or []:
            if isinstance(step, dict):
                refs.extend([step.get("surface_id"), step.get("route_family_id"), step.get("capability_id")])
            elif isinstance(step, str):
                refs.append(step)
        for ref in refs:
            if not ref:
                continue
            if ref.startswith("SUR.") and ref not in surf_set:
                report.fail(f"workflow {w.get('workflow_id')} unknown surface {ref}")
            if ref.startswith("RF.") and ref not in fam_set:
                report.fail(f"workflow {w.get('workflow_id')} unknown family {ref}")
            if ref.startswith("C.") and ref not in cap_set:
                report.fail(f"workflow {w.get('workflow_id')} unknown capability {ref}")
        if w.get("evidence_status") in {"OBSERVED_BROWSER", "OBSERVED_BOTH"} and not w.get("evidence_refs"):
            report.fail(f"OBSERVED workflow {w.get('workflow_id')} has no observed evidence")
        # inferred must stay inferred
        if w.get("inferred") and w.get("evidence_status") != "INFERRED":
            report.fail(f"inferred workflow {w.get('workflow_id')} missing INFERRED status")

    for e in nav_edges or []:
        path = e.get("nav_path")
        if not isinstance(path, list) or not path:
            report.fail("malformed navigation hierarchy")
        dest = e.get("destination")
        if not dest:
            report.fail("nav destination unresolved")
        if e.get("link_class") is None and e.get("edge_type") is None:
            report.fail("nav edge missing classification")

    for r in instances or []:
        acc = r.get("access_status")
        obs = r.get("access_observations") or []
        if acc == "ANONYMOUS_ACCESSIBLE":
            anon = [o for o in obs if o.get("session_kind") == "anonymous_session"]
            if not anon:
                report.fail(f"{r.get('route_id')} labeled ANONYMOUS without anonymous evidence")

    # artifacts
    art = load(folder / "artifact-manifest.json", report)
    root = repo_root()
    if isinstance(art, dict):
        for item in art.get("artifacts") or []:
            rel = item.get("repo_relative_path")
            if not rel:
                continue
            full = root / rel
            if not full.exists():
                report.fail(f"artifact missing {rel}")
            elif sha256_file(full) != item.get("sha256"):
                report.fail(f"artifact hash mismatch {rel}")

    # screenshot refs from instances
    for r in instances or []:
        refs = r.get("screenshot_refs") or {}
        if isinstance(refs, dict):
            for vp, ref in refs.items():
                if not ref:
                    continue
                full = root / ref if not str(ref).startswith("/") else Path(ref)
                if not full.exists():
                    alt = folder / "screenshots" / Path(str(ref)).name
                    if not alt.exists():
                        report.fail(f"missing screenshot {ref}")

    leaks = scan_tree(folder)
    if leaks:
        report.fail(f"secret-scan {len(leaks)}: {leaks[0].get('code')}")

    # metric reconciliation
    declared = (inst_doc.get("metrics") if isinstance(inst_doc, dict) else None) or fam_doc.get("metrics") or {}
    computed = {
        "route_families": len(families or []),
        "route_instances": len(instances or []),
        "surfaces": len(surfaces or []),
        "capabilities": len(caps or []),
        "workflow_edges": len(edges or []),
        "workflows": len(workflows),
    }
    class_counts = Counter((f.get("route_class") for f in (families or [])))
    computed.update({f"class_{k}": v for k, v in class_counts.items()})
    for key, val in declared.items():
        if key in computed and declared[key] != computed[key]:
            report.fail(f"metric mismatch {key}: declared {declared[key]} computed {computed[key]}")

    return report


def format_report(report: Report) -> str:
    if report.ok:
        return f"TOPOLOGY MACHINE GATE: PASS\n{report.target}"
    lines = ["TOPOLOGY MACHINE GATE: FAIL", report.target]
    for msg in report.p0:
        lines.append(f"P0: {msg}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(evidence_root() / "00-product-map"))
    args = ap.parse_args(argv)
    report = validate_topology(Path(args.path))
    print(format_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
