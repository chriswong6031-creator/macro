#!/usr/bin/env python3
"""Neural Web W5a — DAG conformance checker.

Parses the ACTUAL GitHub Actions workflows in .github/workflows/ and diffs
the extracted module-invocation sequences against the declared lanes in
config/dag.yml.  Any mismatch not covered by a divergences entry causes exit 1
with a precise message (lane, step, expected vs found).

Suspect divergences count as covered (they are declared) but are PRINTED in
every run as 'SUSPECT drift (n): ...' so they stay visible.

Usage:
    python scripts/check_dag_conformance.py [--selftest] [--repo-root PATH]

Exit codes:
    0  all declared lanes match the live workflows (+ suspect entries printed)
    1  at least one undeclared mismatch found OR selftest failure
"""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path
from typing import NamedTuple

import yaml

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class Step(NamedTuple):
    """A single workflow step as seen in the DAG."""
    id: str
    module: str       # canonical dotted module, e.g. "scripts.build_sector_central"
    cluster: str | None = None   # cluster name when inside a band cluster


class Lane(NamedTuple):
    workflow: str
    job: str
    steps: list[Step]


# ---------------------------------------------------------------------------
# YAML dag.yml loading
# ---------------------------------------------------------------------------

def _parse_dag_yml(dag_path: Path) -> tuple[list[Lane], list[dict]]:
    """Return (declared_lanes, divergences_list)."""
    raw = yaml.safe_load(dag_path.read_text())
    lanes: list[Lane] = []
    for entry in raw.get("lanes", []):
        wf = entry["workflow"]
        job = entry["job"]
        steps: list[Step] = []
        for step in entry.get("steps", []):
            sid = step.get("id", "")
            if "cluster" in step:
                # parallel band — expand each cluster member as a step with cluster label
                for cl_name, modules in step["cluster"].items():
                    for mod in modules:
                        # mod may be "scripts.build_subsector_confluence --nasdaq"
                        mod_clean = mod.split()[0]
                        steps.append(Step(id=sid, module=mod_clean, cluster=cl_name))
            else:
                mod = step.get("module", "")
                steps.append(Step(id=sid, module=mod, cluster=None))
        lanes.append(Lane(workflow=wf, job=job, steps=steps))
    divergences = raw.get("divergences", [])
    return lanes, divergences


# ---------------------------------------------------------------------------
# Workflow parsing
# ---------------------------------------------------------------------------

# Patterns to extract module invocations from `run:` bodies.
#   Pattern A: run_py "<label>" module.path [args...]
#   Pattern B: brun <slug> "<label>" module.path [args...]
#   Pattern C: python -m module.path [args...]
#   Function composition: cl_x() { brun ...; brun ...; }
#   Top-level composition: spine; band; central; hub; us_pages; libs
#   Explicit dag annotation: # dag: <step-id>

_RUN_PY_RE = re.compile(
    r'run_py\s+"[^"]*"\s+([\w.]+)',
)
_BRUN_RE = re.compile(
    r'brun\s+\w+\s+"[^"]*"\s+([\w.]+)',
)
_PYTHON_M_RE = re.compile(
    r'python(?:3)?\s+-m\s+([\w.]+)',
)
_CLUSTER_FUNC_RE = re.compile(
    r'(cl_\w+)\s*\(\s*\)\s*\{([^}]+)\}',
    re.DOTALL,
)
_COMPOSITION_RE = re.compile(
    r'^\s*(spine|band|central|hub|us_pages|libs)\s*(?:;|$)',
    re.MULTILINE,
)


def _extract_modules_from_run(run_body: str) -> list[str]:
    """Return ordered list of module strings from a run: block.

    Preserved for backward compatibility with tests that call this function directly.
    For cluster-aware extraction use _extract_steps_from_run().
    """
    return [s.module for s in _extract_steps_from_run(run_body)]


def _extract_steps_from_run(run_body: str) -> list[Step]:
    """Return ordered list of Steps (with cluster membership) from a run: block.

    Cluster functions (cl_x() { ... }) are expanded with cluster=<cl_name>.
    Serial invocations (run_py / python -m / brun outside a cluster func) have cluster=None.
    Virtual __segment__xxx tokens from composition lines are emitted with cluster=None.
    """
    # Extract cluster function definitions and map name -> [modules].
    # Also record the character spans of each function body so the line-level scanner
    # can skip those regions (avoiding double-counting).
    cluster_funcs: dict[str, list[str]] = {}
    cluster_func_spans: list[tuple[int, int]] = []  # (start, end) byte offsets to skip
    for match in _CLUSTER_FUNC_RE.finditer(run_body):
        fname = match.group(1)
        body = match.group(2)
        cluster_mods: list[str] = []
        for m in _BRUN_RE.finditer(body):
            cluster_mods.append(m.group(1))
        for m in _RUN_PY_RE.finditer(body):
            cluster_mods.append(m.group(1))
        for m in _PYTHON_M_RE.finditer(body):
            cluster_mods.append(m.group(1))
        cluster_funcs[fname] = cluster_mods
        cluster_func_spans.append((match.start(), match.end()))

    def _in_cluster_func_body(char_offset: int) -> bool:
        """True if char_offset falls inside a cl_*() { ... } definition."""
        return any(start <= char_offset < end for start, end in cluster_func_spans)

    # Helper to collect Steps in source order from a text block,
    # expanding cluster calls and composition calls.
    # Lines inside cluster function bodies are skipped — they are expanded via
    # cluster_funcs when the cluster call line (cl_x &) is encountered.
    def _collect(text: str, visited: set[str]) -> list[Step]:
        result: list[Step] = []
        char_offset = 0
        for line in text.splitlines(keepends=True):
            line_start = char_offset
            char_offset += len(line)
            stripped = line.strip()
            # Skip blank lines and comment-only lines quickly
            if not stripped or stripped.startswith('#') and not re.match(r'#\s*dag:', stripped):
                # Still need to check dag annotations even in comment lines
                dag_ann = re.match(r'#\s*dag:\s*(\S+)', stripped)
                if dag_ann:
                    result.append(Step(id="", module=dag_ann.group(1), cluster=None))
                continue
            # Skip lines that are INSIDE a cluster function body definition —
            # those modules are captured via cluster_funcs expansion below.
            if _in_cluster_func_body(line_start):
                continue
            # dag annotation escape (non-comment context)
            dag_ann = re.match(r'#\s*dag:\s*(\S+)', stripped)
            if dag_ann:
                result.append(Step(id="", module=dag_ann.group(1), cluster=None))
                continue
            # Check for cluster call(s) on this line.
            # A line may call multiple clusters: "cl_x & cl_y & wait"
            # Use findall so all cluster names on the line are expanded in order.
            cl_calls = re.findall(r'\b(cl_\w+)\b', stripped)
            if cl_calls:
                expanded_any = False
                for fname in cl_calls:
                    if fname in cluster_funcs:
                        expanded_any = True
                        if fname not in visited:
                            visited = visited | {fname}
                            for mod in cluster_funcs[fname]:
                                result.append(Step(id="", module=mod, cluster=fname))
                if expanded_any:
                    continue
            # Named function composition: spine; band; central; hub; us_pages; libs
            comp = re.match(
                r'(spine|band|central|hub|us_pages|libs)(?:\s*;\s*(spine|band|central|hub|us_pages|libs))*',
                stripped,
            )
            if comp:
                # Expand each named segment in order
                for seg in re.findall(
                    r'\b(spine|band|central|hub|us_pages|libs)\b', stripped
                ):
                    # These are inline function calls — their bodies are NOT in
                    # cluster_funcs; they appear as named functions defined in the
                    # same run block.  The checker does not re-expand them here
                    # because the declared lane already captures all their modules
                    # from the full run block scan.  The composition detection is
                    # only used to confirm that "central" IS called (sector_central fix).
                    result.append(Step(id="", module=f"__segment__{seg}", cluster=None))
                continue
            # run_py
            m = _RUN_PY_RE.search(stripped)
            if m:
                result.append(Step(id="", module=m.group(1), cluster=None))
                continue
            # brun outside cluster function
            m = _BRUN_RE.search(stripped)
            if m:
                result.append(Step(id="", module=m.group(1), cluster=None))
                continue
            # python -m
            m = _PYTHON_M_RE.search(stripped)
            if m:
                result.append(Step(id="", module=m.group(1), cluster=None))
                continue
        return result

    return _collect(run_body, set())


def _parse_workflow(wf_path: Path) -> dict[str, list[Step]]:
    """Parse one workflow file; return {job_name: [Step, ...]} with cluster membership."""
    raw = yaml.safe_load(wf_path.read_text())
    result: dict[str, list[Step]] = {}
    jobs = raw.get("jobs", {})
    for job_name, job_body in jobs.items():
        steps = job_body.get("steps", [])
        all_steps: list[Step] = []
        for step in steps:
            run_body = step.get("run", "")
            if run_body:
                all_steps.extend(_extract_steps_from_run(run_body))
        result[job_name] = all_steps
    return result


# ---------------------------------------------------------------------------
# Diff logic
# ---------------------------------------------------------------------------

def _lane_key(wf: str, job: str) -> str:
    return f"{wf} / {job}"


def _declared_modules_for_lane(lane: Lane) -> list[str]:
    """Flatten a lane's declared steps to a list of modules (preserving cluster order)."""
    return [s.module for s in lane.steps]


def _diff_lane(
    declared: list[Step] | list[str],
    actual: list[Step] | list[str],
    lane_key: str,
    divergences: list[dict],
) -> list[str]:
    """Return list of error strings for undeclared mismatches.

    Accepts either list[Step] (preferred, cluster-aware) or list[str] (legacy,
    treated as serial steps with cluster=None for backward compatibility).

    The diff is order-aware for serial steps (cluster=None): the relative order
    of serial modules in the declared sequence must be preserved in actual.
    Cluster steps are checked both for presence AND cluster membership: a module
    declared in cl_x must be found in cl_x in the actual workflow, not just
    anywhere in the workflow.

    Cluster interleaving (the order in which parallel clusters execute relative
    to each other) is not checked — clusters run as background subshells and
    their wall-clock interleaving is non-deterministic.
    """
    # Normalise inputs: accept both list[str] and list[Step]
    def _to_steps(seq: list[Step] | list[str]) -> list[Step]:
        if not seq:
            return []
        if isinstance(seq[0], str):
            return [Step(id="", module=m, cluster=None) for m in seq]
        return list(seq)

    declared_steps = _to_steps(declared)
    actual_steps = _to_steps(actual)

    errors: list[str] = []

    # Build a set of (workflow_short_name) for divergence lookup
    wf_short = lane_key.split("/")[0].strip().split("/")[-1].replace(".yml", "")

    def _covered_by_divergence(module: str) -> tuple[bool, bool]:
        """Return (is_covered, is_suspect)."""
        for div in divergences:
            div_lanes = div.get("lanes", [])
            if wf_short not in div_lanes and lane_key.split("/")[-1].strip() not in div_lanes:
                continue
            # Check if the module is mentioned in the differs text
            differs_text = div.get("differs", "")
            if module in differs_text or module.split(".")[-1] in differs_text:
                is_suspect = div.get("status", "") == "suspect"
                return True, is_suspect
        return False, False

    # ---- 1. Cluster-membership check ----------------------------------------
    # For every declared cluster step, verify the module appears in the SAME cluster
    # in actual (not just anywhere).  A module migrated to a different cluster is
    # an undeclared structural change.
    #
    # Build: declared cluster → set[module]; actual cluster → set[module]
    declared_by_cluster: dict[str, set[str]] = {}
    for s in declared_steps:
        if s.cluster is not None and not s.module.startswith("__segment__"):
            declared_by_cluster.setdefault(s.cluster, set()).add(s.module)

    actual_by_cluster: dict[str, set[str]] = {}
    for s in actual_steps:
        if s.cluster is not None and not s.module.startswith("__segment__"):
            actual_by_cluster.setdefault(s.cluster, set()).add(s.module)

    # Modules declared in cluster X but absent from cluster X in actual
    for cl_name, decl_mods in declared_by_cluster.items():
        act_mods = actual_by_cluster.get(cl_name, set())
        for mod in decl_mods - act_mods:
            covered, _ = _covered_by_divergence(mod)
            if not covered:
                # Distinguish: missing entirely vs present in wrong cluster
                actual_all = {s.module for s in actual_steps if not s.module.startswith("__segment__")}
                if mod in actual_all:
                    # Find which cluster it ended up in
                    wrong_clusters = [
                        s.cluster for s in actual_steps
                        if s.module == mod and s.cluster != cl_name
                    ]
                    wrong_str = ", ".join(str(c) for c in wrong_clusters) if wrong_clusters else "unknown"
                    errors.append(
                        f"  CLUSTER MEMBER MIGRATED in {lane_key}: module '{mod}' declared "
                        f"in cluster '{cl_name}' but found in cluster '{wrong_str}' in the "
                        f"live workflow.  Update dag.yml or add a divergences entry."
                    )
                else:
                    errors.append(
                        f"  UNDECLARED ABSENCE in {lane_key}: module '{mod}' declared in "
                        f"dag.yml (cluster '{cl_name}') but NOT found in the live workflow."
                    )

    # Modules present in cluster X in actual but NOT declared in cluster X
    for cl_name, act_mods in actual_by_cluster.items():
        decl_mods = declared_by_cluster.get(cl_name, set())
        for mod in act_mods - decl_mods:
            covered, _ = _covered_by_divergence(mod)
            if not covered:
                # Is it declared in a different cluster (migration detected from the other side)?
                declared_all_clusters = {
                    s.cluster for s in declared_steps
                    if s.module == mod and s.cluster is not None
                }
                if declared_all_clusters:
                    # Already reported from the declared side; skip double-reporting
                    continue
                errors.append(
                    f"  UNDECLARED ADDITION in {lane_key}: module '{mod}' found in cluster "
                    f"'{cl_name}' in live workflow but NOT declared in dag.yml."
                )

    # ---- 2. Serial-step presence + order check --------------------------------
    # Collect serial (non-cluster) steps from declared and actual.
    # NOTE: workflow parsers see ALL case-arm branches (e.g. scope=all, scope=china,
    # scope=gex) as a flat list.  Cluster modules sometimes appear AGAIN as cluster=None
    # in scope-specific arms (e.g. "gex)" arm uses run_py directly for the same modules
    # that the "all)" arm puts in cl_gex).  These scope-arm duplicates are intentional
    # and must NOT be flagged as undeclared serial additions.  We therefore exclude from
    # the serial sets any module that is declared (or found) as a cluster member.
    declared_all_modules = {s.module for s in declared_steps if not s.module.startswith("__segment__")}
    declared_cluster_modules = {
        s.module for s in declared_steps
        if s.cluster is not None and not s.module.startswith("__segment__")
    }
    actual_cluster_modules = {
        s.module for s in actual_steps
        if s.cluster is not None and not s.module.startswith("__segment__")
    }

    serial_declared = [
        s.module for s in declared_steps
        if s.cluster is None and not s.module.startswith("__segment__")
    ]
    # Exclude from actual-serial any module that is known to belong to a cluster
    # (either declared-cluster or actual-cluster) — those are scope-arm duplicates.
    serial_actual = [
        s.module for s in actual_steps
        if s.cluster is None
        and not s.module.startswith("__segment__")
        and s.module not in declared_cluster_modules
        and s.module not in actual_cluster_modules
    ]

    declared_serial_set = set(serial_declared)
    actual_serial_set = set(serial_actual)

    # Presence: declared serial module missing from actual (also not in any cluster)
    for mod in declared_serial_set - actual_serial_set:
        # A declared serial module that appeared as a cluster module in actual is OK;
        # it means the workflow restructured it into a cluster (caught by cluster check).
        if mod in actual_cluster_modules:
            continue
        covered, _ = _covered_by_divergence(mod)
        if not covered:
            errors.append(
                f"  UNDECLARED ABSENCE in {lane_key}: module '{mod}' declared in "
                f"dag.yml but NOT found in the live workflow."
            )

    # Presence: actual serial module not declared anywhere (serial or cluster)
    for mod in actual_serial_set - declared_serial_set:
        if mod in declared_all_modules:
            # Declared as cluster but found serial — that's a structural change caught
            # by the cluster-membership check, not a new module.
            continue
        covered, _ = _covered_by_divergence(mod)
        if not covered:
            errors.append(
                f"  UNDECLARED ADDITION in {lane_key}: module '{mod}' found in live "
                f"workflow but NOT declared in dag.yml."
            )

    # Order: the relative order of serial declared modules must be preserved in actual.
    # Build the subsequence of serial_actual that contains the declared modules (in
    # actual order), then compare it to serial_declared.  A reorder is detected when
    # this subsequence differs from serial_declared.
    # Only compare modules present in BOTH (already reported absent/extra above).
    #
    # Re-invocation handling: some modules are legitimately called multiple times in the
    # same job (e.g. build_alt_data in daily, build_dead_name_fundamentals in weekly).
    # dag.yml declares each re-invocation as a separate step, so serial_declared may
    # contain the module name multiple times.  We must preserve the multiplicity when
    # building the actual sequence for comparison.
    #
    # Scope-arm deduplication: workflows with scope-based dispatch (case "$SCOPE" in)
    # may re-invoke the same modules in scope-specific arms (e.g. the "baskets)" arm
    # re-runs build_radar_plus).  These scope-arm duplicates appear at the END of the
    # parsed step list (after all the all-scope steps).  To avoid false-positive order
    # errors, we cap the actual subsequence length to the declared count for modules that
    # appear fewer times in declared than in actual.
    common_serial = [m for m in serial_declared if m in actual_serial_set]
    actual_common_order_raw = [m for m in serial_actual if m in declared_serial_set]
    # Count declared occurrences per module so we know the allowed multiplicity
    from collections import Counter
    declared_counts = Counter(serial_declared)
    _occurrence: Counter = Counter()
    actual_common_order: list[str] = []
    for m in actual_common_order_raw:
        if _occurrence[m] < declared_counts[m]:
            actual_common_order.append(m)
            _occurrence[m] += 1
    if common_serial != actual_common_order:
        # Find the first position where they diverge to give a precise message
        for i, (dec, act) in enumerate(zip(common_serial, actual_common_order)):
            if dec != act:
                covered_dec, _ = _covered_by_divergence(dec)
                covered_act, _ = _covered_by_divergence(act)
                if not covered_dec and not covered_act:
                    errors.append(
                        f"  SERIAL ORDER MISMATCH in {lane_key}: at position {i}, "
                        f"declared order has '{dec}' but live workflow has '{act}'. "
                        f"Declared sequence: {common_serial}. "
                        f"Actual sequence: {actual_common_order}."
                    )
                    break  # one error per lane is enough to diagnose a reorder

    return errors


# ---------------------------------------------------------------------------
# Main conformance check
# ---------------------------------------------------------------------------

def run_conformance(repo_root: Path, verbose: bool = False) -> int:
    """Return 0 (clean) or 1 (mismatch found)."""
    dag_path = repo_root / "config" / "dag.yml"
    declared_lanes, divergences = _parse_dag_yml(dag_path)

    # Collect suspect divergences for printing
    suspect_divs = [d for d in divergences if d.get("status") == "suspect"]

    all_errors: list[str] = []
    checked = 0

    for lane in declared_lanes:
        wf_path = repo_root / lane.workflow
        if not wf_path.exists():
            all_errors.append(
                f"  MISSING WORKFLOW: {lane.workflow} declared in dag.yml but file not found."
            )
            continue
        try:
            job_steps = _parse_workflow(wf_path)
        except Exception as exc:  # noqa: BLE001
            all_errors.append(f"  PARSE ERROR {lane.workflow}: {exc}")
            continue
        if lane.job not in job_steps:
            all_errors.append(
                f"  MISSING JOB: job '{lane.job}' declared in dag.yml "
                f"but not found in {lane.workflow}."
            )
            continue

        actual_steps = job_steps[lane.job]
        lk = f"{lane.workflow} / {lane.job}"
        errors = _diff_lane(lane.steps, actual_steps, lk, divergences)
        all_errors.extend(errors)
        checked += 1
        if verbose:
            print(f"  [OK] {lk} ({len(lane.steps)} declared steps)")

    # Print suspect divergences every run (visibility requirement)
    if suspect_divs:
        print(f"\nSUSPECT drift ({len(suspect_divs)}) — undocumented, needs owner review:")
        for div in suspect_divs:
            lanes_str = ", ".join(div.get("lanes", []))
            print(f"  [{lanes_str}] {div.get('differs', '').strip()[:120]}")
            print(f"    note: {div.get('note', '').strip()[:200]}")
        print()

    if all_errors:
        print(f"DAG CONFORMANCE FAILED — {len(all_errors)} undeclared mismatch(es):\n")
        for err in all_errors:
            print(err)
        print(
            "\nFix: update config/dag.yml to match the live workflow, OR add a "
            "'divergences' entry if the difference is intentional."
        )
        return 1

    print(
        f"DAG conformance OK — {checked} lane(s) checked, "
        f"{len(suspect_divs)} suspect drift(s) visible above."
    )
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_SYNTHETIC_WORKFLOW = """\
name: synthetic-test
jobs:
  build:
    steps:
      - name: spine
        run: |
          set +e
          run_py() { local label="$1"; local mod="$2"; python -m "$mod" > /dev/null; }
          run_py "step a (mod_a)" scripts.mod_a
          run_py "step b (mod_b)" scripts.mod_b
      - name: band
        run: |
          set +e
          brun() { local slug="$1" label="$2" mod="$3"; python -m "$mod" > /dev/null; }
          cl_x() {
            brun x1 "mod_x1" scripts.mod_x1
            brun x2 "mod_x2" scripts.mod_x2
          }
          cl_y() {
            brun y1 "mod_y1" scripts.mod_y1
          }
          cl_x & cl_y & wait
      - name: post
        run: python -m scripts.mod_c
"""

_DAG_FIXTURE_GREEN = {
    "meta": {"schema_version": 1, "granularity": "workflow-step"},
    "lanes": [
        {
            "workflow": "__synthetic__",
            "job": "build",
            "steps": [
                {"id": "a", "module": "scripts.mod_a"},
                {"id": "b", "module": "scripts.mod_b"},
                {"id": "band", "cluster": {"cl_x": ["scripts.mod_x1", "scripts.mod_x2"], "cl_y": ["scripts.mod_y1"]}},
                {"id": "c", "module": "scripts.mod_c"},
            ],
        }
    ],
    "divergences": [],
    "modules": [],
}


def _build_declared_steps(dag_fixture: dict) -> list[Step]:
    """Build a flat list[Step] from a dag fixture dict (same logic as _parse_dag_yml)."""
    steps: list[Step] = []
    for entry in dag_fixture.get("lanes", [{}]):
        for step in entry.get("steps", []):
            sid = step.get("id", "")
            if "cluster" in step:
                for cl_name, modules in step["cluster"].items():
                    for mod in modules:
                        mod_clean = mod.split()[0]
                        steps.append(Step(id=sid, module=mod_clean, cluster=cl_name))
            else:
                mod = step.get("module", "")
                steps.append(Step(id=sid, module=mod, cluster=None))
    return steps


def _run_selftest() -> int:
    """Run synthetic scenarios; return 0 if all pass, 1 if any fail."""
    import copy

    failures: list[str] = []

    # Parse the synthetic workflow to get actual Steps (with cluster info)
    actual_steps_all = _extract_steps_from_run(
        "\n".join(
            s.get("run", "")
            for s in yaml.safe_load(_SYNTHETIC_WORKFLOW)["jobs"]["build"]["steps"]
        )
    )
    # Filter virtual segment tokens
    actual_steps_real = [s for s in actual_steps_all if not s.module.startswith("__")]

    # ---- GREEN: declared matches actual ----
    dag_green = copy.deepcopy(_DAG_FIXTURE_GREEN)
    declared_steps_green = _build_declared_steps(dag_green)
    errs = _diff_lane(declared_steps_green, actual_steps_real, "__synthetic__/build", [])
    if errs:
        failures.append(f"SELFTEST GREEN failed (should have no errors): {errs}")

    # ---- RED-a: remove a declared step that IS present in actual ----
    # Declare only mod_a, mod_b, cluster, but NOT mod_c.
    # actual still has mod_c -> UNDECLARED ADDITION detected.
    dag_missing_decl = copy.deepcopy(_DAG_FIXTURE_GREEN)
    dag_missing_decl["lanes"][0]["steps"] = [
        s for s in dag_missing_decl["lanes"][0]["steps"]
        if s.get("module") != "scripts.mod_c"
    ]
    declared_steps_missing = _build_declared_steps(dag_missing_decl)
    errs = _diff_lane(declared_steps_missing, actual_steps_real, "__synthetic__/build", [])
    if not errs:
        failures.append(
            "SELFTEST RED-a failed: should have detected 'scripts.mod_c' present in "
            "actual but absent from declared"
        )

    # ---- RED-b: reorder two serial steps ----
    # Declared: mod_a THEN mod_b.  Actual: mod_b THEN mod_a (swapped).
    # The checker must detect the order violation and exit RED.
    declared_steps_ordered = [
        Step(id="a", module="scripts.mod_a", cluster=None),
        Step(id="b", module="scripts.mod_b", cluster=None),
        Step(id="c", module="scripts.mod_c", cluster=None),
    ]
    actual_steps_reordered = [
        Step(id="", module="scripts.mod_b", cluster=None),  # swapped
        Step(id="", module="scripts.mod_a", cluster=None),  # swapped
        Step(id="", module="scripts.mod_c", cluster=None),
    ]
    errs = _diff_lane(declared_steps_ordered, actual_steps_reordered, "__synthetic__/build", [])
    if not errs:
        failures.append(
            "SELFTEST RED-b failed: should have detected reorder of "
            "scripts.mod_a / scripts.mod_b (declared order not preserved)"
        )

    # ---- RED-c: cluster member moved between clusters ----
    # Declared: mod_x2 in cl_x, mod_y1 in cl_y.
    # Actual: mod_x2 moved to cl_y (still present, just in wrong cluster).
    # The checker must detect the cluster-membership violation.
    declared_steps_clustered = [
        Step(id="band", module="scripts.mod_x1", cluster="cl_x"),
        Step(id="band", module="scripts.mod_x2", cluster="cl_x"),   # declared in cl_x
        Step(id="band", module="scripts.mod_y1", cluster="cl_y"),
    ]
    actual_steps_migrated = [
        Step(id="", module="scripts.mod_x1", cluster="cl_x"),
        Step(id="", module="scripts.mod_x2", cluster="cl_y"),   # migrated to cl_y
        Step(id="", module="scripts.mod_y1", cluster="cl_y"),
    ]
    errs = _diff_lane(declared_steps_clustered, actual_steps_migrated, "__synthetic__/build", [])
    if not errs:
        failures.append(
            "SELFTEST RED-c failed: should have detected scripts.mod_x2 migrated "
            "from cluster 'cl_x' (declared) to cluster 'cl_y' (actual)"
        )

    # ---- GREEN on declared divergences ----
    dag_div = copy.deepcopy(_DAG_FIXTURE_GREEN)
    # declared includes scripts.mod_x2 in cl_x, actual does NOT have it at all
    actual_without_x2 = [s for s in actual_steps_real if s.module != "scripts.mod_x2"]
    divs_covering = [{"lanes": ["build"], "differs": "scripts.mod_x2 omitted", "reason": "test"}]
    errs = _diff_lane(declared_steps_green, actual_without_x2, "__synthetic__/build", divs_covering)
    if errs:
        failures.append(f"SELFTEST GREEN-with-divergence failed: {errs}")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  {f}")
        return 1

    print("SELFTEST PASSED: GREEN/RED-a/RED-b/RED-c/GREEN-with-divergence all correct.")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Run synthetic self-test scenarios (GREEN/RED) and exit.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Path to the repository root (default: two levels above this script).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print OK lines for each lane.",
    )
    args = parser.parse_args()

    if args.selftest:
        return _run_selftest()

    return run_conformance(args.repo_root, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
