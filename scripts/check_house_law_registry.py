#!/usr/bin/env python3
"""Meta-guard: verifies config/house_law_checks.yml is complete and honest.

This script is the registry keeper. It enforces five passes:

  A. SCHEMA   — every entry has required fields; severity in vocab; selftest_exempt_reason
                present when needed; ci_wiring non-empty unless severity allows empty.
  B. CENSUS   — every scripts/check_*.py in the repo appears as some entry's check_script.
                An unregistered check_*.py is a HARD FAIL — new guards cannot merge until
                registered. Also: any check_script path that doesn't exist on disk is HARD.
  C. WIRING   — for each ci_wiring item with lane != hook: the workflow file exists,
                contains the named job under jobs:, and the job's steps mention the
                check_script basename (or the notes invocation string when check_script is null).
  D. SELFTEST TRUTH — selftest:true requires the script text to contain "selftest" or "self-test".
                selftest:false with a script that DOES advertise a selftest flag is stale.
  E. RATCHET  — expired ratchet dates emit GitHub ::warning:: annotations; exit stays 0.

Usage:
    python3 scripts/check_house_law_registry.py            # passes A-E; exit 1 on any HARD
    python3 scripts/check_house_law_registry.py --selftest # synthetic assertions; exit 0/1
    python3 scripts/check_house_law_registry.py --emit-docs [PATH]  # regenerate docs
    python3 scripts/check_house_law_registry.py --emit-json PATH    # dump normalized JSON

Exit codes:
    0  all checks passed (warnings may have been printed)
    1  one or more HARD findings, or selftest failure

Known limits of this meta-guard:
  - Census only auto-covers scripts/check_*.py — guard-shaped pytest files and harness
    hooks are voluntary entries; adding them is required but not mechanically enforced.
  - Wiring check is textual (job steps mention the script basename), not execution-order-aware.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

# ── Constants ────────────────────────────────────────────────────────────────

REGISTRY_PATH = "config/house_law_checks.yml"
DEFAULT_DOCS_PATH = "docs/HOUSE_LAW_CI_GUARD_SUITE.md"

VALID_SEVERITIES = {
    "hard",
    "hard_for_protected_paths",
    "warn",
    "manual",
    "discipline",
    "known_spurious",
}

# Severities that are allowed to have empty ci_wiring
EMPTY_WIRING_OK = {"manual", "discipline", "known_spurious"}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_registry(root: Path) -> dict[str, Any]:
    path = root / REGISTRY_PATH
    with open(path) as f:
        data = yaml.safe_load(f)
    return data


def _load_workflow_jobs(workflow_path: Path) -> dict[str, str]:
    """Return {job_key: concatenated run-command text} from a workflow YAML.

    PyYAML parses the workflow's `on:` key as boolean True — harmless here,
    since we only read the `jobs:` section. Only each step's `run:` body is
    kept for matching: a script named in a step *name* or comment must not
    satisfy the wiring pass — the guarantee is "invoked", not "mentioned".
    """
    with open(workflow_path) as f:
        raw = f.read()

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return {}

    if not isinstance(data, dict):
        return {}

    jobs = data.get("jobs", {})
    if not isinstance(jobs, dict):
        return {}

    result: dict[str, str] = {}
    for job_key, job_val in jobs.items():
        if not isinstance(job_val, dict):
            result[str(job_key)] = ""
            continue
        steps = job_val.get("steps", [])
        run_bodies = [
            str(step.get("run", ""))
            for step in steps
            if isinstance(step, dict)
        ]
        result[str(job_key)] = "\n".join(body for body in run_bodies if body)
    return result


# ── Pass A: Schema ────────────────────────────────────────────────────────────

def pass_a_schema(checks: list[dict], findings: list[str]) -> None:
    """Validate schema of every registry entry."""
    seen_ids: set[str] = set()

    for i, entry in enumerate(checks):
        law_id = entry.get("law_id", f"<entry[{i}]>")
        prefix = f"SCHEMA [{law_id}]"

        # Required fields
        for field in ("law_id", "summary", "source_ref", "severity", "selftest",
                      "owner_program"):
            if field not in entry:
                findings.append(f"{prefix}: missing required field '{field}'")

        # law_id uniqueness
        if law_id in seen_ids:
            findings.append(f"SCHEMA: duplicate law_id '{law_id}'")
        seen_ids.add(law_id)

        # severity vocab
        sev = entry.get("severity", "")
        if sev not in VALID_SEVERITIES:
            findings.append(f"{prefix}: severity '{sev}' not in vocab "
                            f"{sorted(VALID_SEVERITIES)}")

        # selftest_exempt_reason required when check_script non-null and selftest false
        check_script = entry.get("check_script")
        selftest = entry.get("selftest", None)
        if check_script is not None and selftest is False:
            if not entry.get("selftest_exempt_reason"):
                findings.append(
                    f"{prefix}: check_script is set and selftest=false but "
                    f"selftest_exempt_reason is missing or empty"
                )

        # ci_wiring must be non-empty unless severity allows it or all lanes are hook
        ci_wiring = entry.get("ci_wiring", [])
        if not isinstance(ci_wiring, list):
            findings.append(f"{prefix}: ci_wiring must be a list")
            continue

        if ci_wiring:
            non_hook_wiring = [w for w in ci_wiring if w.get("lane") != "hook"]
            all_hook = len(non_hook_wiring) == 0
        else:
            all_hook = False

        if not ci_wiring and sev not in EMPTY_WIRING_OK and not all_hook:
            findings.append(
                f"{prefix}: ci_wiring is empty but severity '{sev}' requires wiring "
                f"(only {sorted(EMPTY_WIRING_OK)} may have empty ci_wiring)"
            )


# ── Pass B: Census ────────────────────────────────────────────────────────────

def pass_b_census(checks: list[dict], root: Path, findings: list[str]) -> None:
    """Every scripts/check_*.py must appear as some entry's check_script."""
    # Build set of registered check_scripts
    registered: set[str] = set()
    for entry in checks:
        cs = entry.get("check_script")
        if cs:
            registered.add(cs)

    # Find all check_*.py on disk
    on_disk = sorted(
        str(p.relative_to(root))
        for p in root.glob("scripts/check_*.py")
        if p.is_file()
    )

    for script_rel in on_disk:
        if script_rel not in registered:
            findings.append(
                f"CENSUS: scripts/{Path(script_rel).name} exists on disk but is not "
                f"registered in the house-law registry — add an entry in "
                f"{REGISTRY_PATH} before merging"
            )

    # Also: any check_script path that doesn't exist on disk
    for entry in checks:
        cs = entry.get("check_script")
        law_id = entry.get("law_id", "?")
        if cs is None:
            continue
        # Skip hook paths (not under scripts/)
        if not cs.startswith("scripts/"):
            continue
        cs_path = root / cs
        if not cs_path.exists():
            findings.append(
                f"CENSUS [{law_id}]: check_script '{cs}' does not exist on disk"
            )


# ── Pass C: Wiring ────────────────────────────────────────────────────────────

def pass_c_wiring(checks: list[dict], root: Path, findings: list[str]) -> None:
    """For each non-hook ci_wiring item: workflow exists, job exists, steps mention script."""
    # Cache workflow job maps
    wf_cache: dict[str, dict[str, str]] = {}

    for entry in checks:
        law_id = entry.get("law_id", "?")
        ci_wiring = entry.get("ci_wiring", [])
        check_script = entry.get("check_script")
        notes = entry.get("notes") or ""

        for wiring in ci_wiring:
            lane = wiring.get("lane", "")
            if lane == "hook":
                continue  # hook wiring is out-of-band; skip

            workflow_rel = wiring.get("workflow", "")
            job_key = wiring.get("job", "")

            # Workflow must exist
            wf_path = root / workflow_rel
            if not wf_path.exists():
                findings.append(
                    f"WIRING [{law_id}]: workflow '{workflow_rel}' does not exist on disk"
                )
                continue

            # Load job map (cached)
            if workflow_rel not in wf_cache:
                wf_cache[workflow_rel] = _load_workflow_jobs(wf_path)
            job_map = wf_cache[workflow_rel]

            # Job must exist
            if job_key not in job_map:
                findings.append(
                    f"WIRING [{law_id}]: job '{job_key}' not found in {workflow_rel} "
                    f"(found: {sorted(job_map.keys())})"
                )
                continue

            # Steps must mention the script (or notes invocation string for null scripts)
            steps_text = job_map[job_key]

            if check_script is not None:
                needle = Path(check_script).name  # e.g. "check_validated_claims.py"
                # Strip .py for broader matching (some steps call as module)
                needle_stem = Path(check_script).stem  # e.g. "check_validated_claims"
                # Test-file guards (tests/*.py) must be named explicitly in the job's
                # pytest invocation — a broad "pytest tests/..." match would let a
                # registered ratchet silently drop out of CI (that exact gap existed
                # for test_no_literal_ntrials.py before this registry landed).
                if needle not in steps_text and needle_stem not in steps_text:
                    findings.append(
                        f"WIRING [{law_id}]: job '{job_key}' in {workflow_rel} does not "
                        f"mention '{needle}' in its steps"
                    )
            else:
                # check_script is null — look for notes invocation string
                # For cycles.ontology_js_sync, match "gen_ontology_js"
                invocation_match = re.search(r'`([^`]+)`', notes)
                if invocation_match:
                    invocation = invocation_match.group(1)
                    # Extract module name from invocation like "python3 -m scripts.gen_ontology_js --check"
                    module_parts = invocation.split()
                    # Find the module/script name
                    needle = None
                    for part in module_parts:
                        if "gen_" in part or "check_" in part or "build_" in part:
                            needle = part.split(".")[-1]  # last part of module path
                            break
                    if needle and needle not in steps_text:
                        findings.append(
                            f"WIRING [{law_id}]: job '{job_key}' in {workflow_rel} does not "
                            f"mention '{needle}' in its steps (null check_script; checked notes)"
                        )


# ── Pass D: Selftest Truth ────────────────────────────────────────────────────

def pass_d_selftest_truth(checks: list[dict], root: Path, findings: list[str]) -> None:
    """selftest:true requires script to contain 'selftest' or 'self-test'."""
    for entry in checks:
        law_id = entry.get("law_id", "?")
        check_script = entry.get("check_script")
        selftest = entry.get("selftest", None)

        if check_script is None:
            continue
        if not check_script.startswith("scripts/"):
            continue

        script_path = root / check_script
        if not script_path.exists():
            continue  # already caught by census

        script_text = script_path.read_text(errors="replace")
        has_selftest_flag = "selftest" in script_text or "self-test" in script_text

        if selftest is True and not has_selftest_flag:
            findings.append(
                f"SELFTEST [{law_id}]: selftest=true but '{check_script}' contains no "
                f"'selftest'/'self-test' text — stale claim"
            )
        if selftest is False and has_selftest_flag:
            findings.append(
                f"SELFTEST [{law_id}]: selftest=false but '{check_script}' advertises "
                f"a selftest flag — update the registry entry to selftest=true"
            )


# ── Pass E: Ratchet Expiry ────────────────────────────────────────────────────

def pass_e_ratchet_expiry(checks: list[dict]) -> None:
    """Warn (exit-0) on expired ratchets."""
    today = date.today()
    for entry in checks:
        law_id = entry.get("law_id", "?")
        ratchet = entry.get("ratchet")
        if not ratchet or not isinstance(ratchet, dict):
            continue
        ratchet_date_str = ratchet.get("date")
        action = ratchet.get("action", "")
        if not ratchet_date_str:
            continue
        try:
            ratchet_date = datetime.strptime(str(ratchet_date_str), "%Y-%m-%d").date()
        except ValueError:
            print(f"::warning:: RATCHET [{law_id}]: could not parse ratchet.date "
                  f"'{ratchet_date_str}'")
            continue
        if ratchet_date < today:
            print(f"::warning:: RATCHET [{law_id}]: ratchet expired "
                  f"{ratchet_date_str} — action required: {action}")


# ── Doc generation ────────────────────────────────────────────────────────────

_SEV_ORDER = [
    "hard",
    "hard_for_protected_paths",
    "warn",
    "manual",
    "discipline",
    "known_spurious",
]

_SEV_DESC = {
    "hard": (
        "Any finding causes CI to exit 1 — the PR cannot merge."
    ),
    "hard_for_protected_paths": (
        "Protected modules (Article-2 money-path: alert_triage / board_ordering / "
        "top_setups) fail CI on any finding. Other modules emit a warning but do not "
        "block the merge."
    ),
    "warn": (
        "Visible warning printed to the CI log. Does not block the merge. Every warn "
        "entry must carry a ratchet date (when it flips to hard) or a permanent reason "
        "in notes."
    ),
    "manual": (
        "Run-by-hand tool — not wired into CI. Requires a manual reason (e.g. API key "
        "needed, or pre-deploy check). Document when to run it in the notes field."
    ),
    "discipline": (
        "Law exists and is enforced, but not mechanically checkable by a static script. "
        "Enforcement is by architecture, code review, and program rulings."
    ),
    "known_spurious": (
        "A known external false-red that must NOT block merges. Document the source and "
        "why it cannot be fixed."
    ),
}

_ADD_GUARD_STEPS = """
## How to add a new guard

When you create `scripts/check_new_boundary.py`, you must complete these steps before
the PR can merge (the meta-guard blocks unregistered check_*.py files):

1. **Write the script** — follow the existing guard style: explicit exit codes, a brief
   docstring, and a `--selftest` flag if the check can self-verify.

2. **Add a registry entry** in `config/house_law_checks.yml` using the frozen schema
   (`schema: house_law_checks.v1`). Fill in every required field:
   - `law_id` — unique, kebab/snake slug like `domain.thing`
   - `summary` — one sentence explaining what is enforced and why it matters
   - `source_ref` — list of paths or doc references
   - `severity` — one of the vocab values in the table below
   - `check_script` — path to your script (e.g. `scripts/check_new_boundary.py`)
   - `ci_wiring` — list of `{workflow, job, lane}` entries (required unless severity is
     `manual`, `discipline`, or `known_spurious`)
   - `selftest` — `true` if the script contains a `--selftest` flag, `false` otherwise
   - `selftest_exempt_reason` — required when `check_script` is non-null and `selftest: false`
   - `owner_program` — which program owns this law
   - `known_limits` — list any static-analysis blind spots honestly

3. **Wire the CI job** — add a step to the appropriate `ci_wiring` workflow/job that calls
   your script. Match the style of neighboring guard steps (same runner, checkout, pip
   install pattern). If you need a new job, append it to ci.yml without reordering or
   reformatting existing jobs.

4. **Run the meta-guard locally** to verify:
   ```
   python3 scripts/check_house_law_registry.py --selftest
   python3 scripts/check_house_law_registry.py
   ```

5. **Severity downgrades or entry removals** require an operator/Fable ruling recorded
   in the PR. You cannot simply remove or downgrade an entry without that ruling.
"""


def _entry_ci_summary(entry: dict) -> str:
    wiring = entry.get("ci_wiring", [])
    if not wiring:
        return "—"
    parts = []
    for w in wiring:
        wf = Path(w.get("workflow", "")).name
        job = w.get("job", "")
        lane = w.get("lane", "")
        parts.append(f"`{wf}/{job}` ({lane})")
    return ", ".join(parts)


def emit_docs(checks: list[dict], out_path: Path, updated: str = "") -> None:
    """Regenerate the docs file deterministically."""
    # Sort checks by severity order, then law_id within severity
    sev_rank = {s: i for i, s in enumerate(_SEV_ORDER)}

    def sort_key(e: dict):
        sev = e.get("severity", "discipline")
        return (sev_rank.get(sev, 99), e.get("law_id", ""))

    sorted_checks = sorted(checks, key=sort_key)

    lines: list[str] = []
    regen_cmd = "python3 scripts/check_house_law_registry.py --emit-docs"
    lines.append(
        f"<!-- AUTO-GENERATED — do not edit by hand. "
        f"Source: config/house_law_checks.yml. "
        f"Regen: `{regen_cmd}` -->"
    )
    lines.append("")
    lines.append("# House Law CI Guard Suite")
    lines.append("")
    lines.append(
        "This document is the single reference for every house law, whether and how it "
        "is mechanically enforced, which CI job runs it, and what its known blind spots "
        "are. It is generated from `config/house_law_checks.yml` by "
        "`scripts/check_house_law_registry.py --emit-docs`. **Do not edit this file "
        "directly** — edit the YAML and regenerate."
    )
    lines.append("")
    lines.append(
        "The registry exists so that no one needs to guess: which guard covers this law, "
        "does it run on PRs or only in nightly, is a finding fatal or just a warning, "
        "what does it miss. Everything is in one place."
    )
    lines.append("")
    lines.append(_ADD_GUARD_STEPS)
    lines.append("")
    lines.append("## Severity vocabulary")
    lines.append("")
    lines.append("| Severity | Meaning |")
    lines.append("|---|---|")
    for sev in _SEV_ORDER:
        lines.append(f"| `{sev}` | {_SEV_DESC[sev]} |")
    lines.append("")

    # One table per severity group
    by_sev: dict[str, list[dict]] = {}
    for entry in sorted_checks:
        sev = entry.get("severity", "discipline")
        by_sev.setdefault(sev, []).append(entry)

    for sev in _SEV_ORDER:
        group = by_sev.get(sev, [])
        if not group:
            continue
        lines.append(f"## {sev.replace('_', ' ').title()} laws")
        lines.append("")
        lines.append(
            "| Law ID | Summary | Enforced by | CI wiring | Selftest | "
            "Allowlist | Ratchet | Known limits |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for entry in group:
            law_id = entry.get("law_id", "")
            summary = (entry.get("summary") or "").strip().replace("\n", " ")
            cs = entry.get("check_script") or "—"
            cs_fmt = f"`{cs}`" if cs != "—" else "—"
            ci_sum = _entry_ci_summary(entry)
            selftest = "yes" if entry.get("selftest") else "no"
            allowlist = entry.get("allowlist") or "—"
            ratchet = entry.get("ratchet")
            ratchet_str = ratchet["date"] if ratchet else "—"
            limits = entry.get("known_limits") or []
            limits_str = "; ".join(str(l).strip() for l in limits) if limits else "—"
            lines.append(
                f"| `{law_id}` | {summary} | {cs_fmt} | {ci_sum} | "
                f"{selftest} | {allowlist} | {ratchet_str} | {limits_str} |"
            )
        lines.append("")

    # Known-spurious section (even if already in the table above)
    lines.append("## Known-spurious CI statuses")
    lines.append("")
    lines.append(
        "These checks are recorded in the registry to document known external "
        "false-reds. They must never block merges."
    )
    lines.append("")
    spurious = [e for e in sorted_checks if e.get("severity") == "known_spurious"]
    if spurious:
        for entry in spurious:
            lines.append(f"- **{entry.get('law_id')}**: {(entry.get('notes') or '').strip()}")
    else:
        lines.append("_(none currently registered)_")
    lines.append("")

    # Registry ownership section
    lines.append("## Registry ownership")
    lines.append("")
    lines.append(
        "Any agent adding a new `scripts/check_*.py` must register it in "
        "`config/house_law_checks.yml` before the PR can merge. The meta-guard "
        "(`scripts/check_house_law_registry.py`) runs in CI and blocks merges of "
        "unregistered guard scripts."
    )
    lines.append("")
    lines.append(
        "Severity DOWNGRADES (e.g. hard → warn) or entry REMOVALS require an explicit "
        "operator/Fable ruling recorded in the PR description. Removing an entry "
        "without a ruling is a process violation."
    )
    lines.append("")
    # Stamp with the registry's own `updated:` field, NOT the wall clock — the
    # CI docs-drift step runs `--emit-docs && git diff --exit-code`, so any
    # non-deterministic byte here would red every PR from the next day onward.
    lines.append(
        f"_Generated from `config/house_law_checks.yml` (updated {updated}) "
        f"by `{regen_cmd}`._"
    )
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))


# ── JSON emission ─────────────────────────────────────────────────────────────

def emit_json(checks: list[dict], out_path: Path) -> None:
    """Dump normalized registry JSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(checks, indent=2, default=str))


# ── Selftest ──────────────────────────────────────────────────────────────────

def run_selftest(root: Path) -> int:
    """Build synthetic registry + fake script tree and assert the passes catch violations."""
    import traceback

    print("Running selftest...")
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="house_law_selftest_") as tmpdir:
        tmp = Path(tmpdir)

        # Create fake scripts/
        scripts_dir = tmp / "scripts"
        scripts_dir.mkdir()

        # Registered script — has selftest
        (scripts_dir / "check_registered.py").write_text(
            "# --selftest\ndef main(): pass\n"
        )
        # UNREGISTERED script — should be caught by census
        (scripts_dir / "check_unregistered.py").write_text("# no selftest\n")

        # Create a fake workflow
        workflows_dir = tmp / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        (workflows_dir / "ci.yml").write_text(
            "name: ci\non:\n  push:\njobs:\n  my-job:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - name: run check_registered\n"
            "        run: python3 scripts/check_registered.py\n"
        )

        # Fake registry with several violations
        fake_registry = {
            "schema": "house_law_checks.v1",
            "updated": "2026-07-06",
            "checks": [
                # Good entry — should pass
                {
                    "law_id": "test.good",
                    "summary": "A good entry",
                    "source_ref": ["scripts/check_registered.py"],
                    "severity": "hard",
                    "check_script": "scripts/check_registered.py",
                    "ci_wiring": [
                        {"workflow": ".github/workflows/ci.yml",
                         "job": "my-job",
                         "lane": "pr_ci"}
                    ],
                    "selftest": True,
                    "allowlist": None,
                    "ratchet": None,
                    "known_limits": [],
                    "owner_program": "test",
                },
                # Bad severity — should be caught by pass A
                {
                    "law_id": "test.bad_severity",
                    "summary": "Bad severity",
                    "source_ref": [],
                    "severity": "totally_wrong",
                    "check_script": None,
                    "ci_wiring": [],
                    "selftest": False,
                    "allowlist": None,
                    "ratchet": None,
                    "known_limits": [],
                    "owner_program": "test",
                },
                # Missing wiring — should be caught by pass A (hard severity, empty wiring)
                {
                    "law_id": "test.missing_wiring",
                    "summary": "Missing wiring",
                    "source_ref": [],
                    "severity": "hard",
                    "check_script": None,
                    "ci_wiring": [],
                    "selftest": False,
                    "allowlist": None,
                    "ratchet": None,
                    "known_limits": [],
                    "owner_program": "test",
                },
                # Stale selftest claim — selftest=true but script has no selftest text
                {
                    "law_id": "test.stale_selftest",
                    "summary": "Stale selftest claim",
                    "source_ref": [],
                    "severity": "discipline",
                    "check_script": "scripts/check_registered.py",
                    # check_registered.py DOES have selftest text — so this is actually correct.
                    # We need a script WITHOUT selftest to test stale.
                    # Let's use a different approach: create a no-selftest script and mark it true.
                    "ci_wiring": [],
                    "selftest": False,  # but script HAS selftest → should be caught
                    "selftest_exempt_reason": None,  # missing exempt reason for non-null script
                    "allowlist": None,
                    "ratchet": None,
                    "known_limits": [],
                    "owner_program": "test",
                },
                # Expired ratchet — should emit warning
                {
                    "law_id": "test.expired_ratchet",
                    "summary": "Expired ratchet",
                    "source_ref": [],
                    "severity": "discipline",
                    "check_script": None,
                    "ci_wiring": [],
                    "selftest": False,
                    "allowlist": None,
                    "ratchet": {"date": "2020-01-01", "action": "do something"},
                    "known_limits": [],
                    "owner_program": "test",
                },
            ]
        }

        # Write fake registry
        registry_path = tmp / "config" / "house_law_checks.yml"
        registry_path.parent.mkdir()
        with open(registry_path, "w") as f:
            yaml.dump(fake_registry, f)

        checks = fake_registry["checks"]

        # Pass A: schema
        a_findings: list[str] = []
        pass_a_schema(checks, a_findings)
        bad_sev = [f for f in a_findings if "totally_wrong" in f]
        if not bad_sev:
            failures.append("Pass A did not catch bad severity 'totally_wrong'")
        missing_wiring = [f for f in a_findings if "test.missing_wiring" in f and "ci_wiring" in f]
        if not missing_wiring:
            failures.append("Pass A did not catch missing ci_wiring on hard severity")

        # Pass B: census — should catch check_unregistered.py
        b_findings: list[str] = []
        pass_b_census(checks, tmp, b_findings)
        unregistered_caught = any("check_unregistered" in f for f in b_findings)
        if not unregistered_caught:
            failures.append("Pass B did not catch check_unregistered.py as unregistered script")

        # Pass D: selftest truth — test.stale_selftest has selftest=false but script HAS selftest
        # check_registered.py has "selftest" text, and test.stale_selftest marks it false
        d_findings: list[str] = []
        pass_d_selftest_truth(checks, tmp, d_findings)
        stale_caught = any("test.stale_selftest" in f for f in d_findings)
        if not stale_caught:
            failures.append(
                "Pass D did not catch stale selftest claim "
                "(selftest=false but script has selftest text)"
            )

        # Pass E: ratchet expiry — test.expired_ratchet has date 2020-01-01
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            pass_e_ratchet_expiry(checks)
        ratchet_output = buf.getvalue()
        if "test.expired_ratchet" not in ratchet_output:
            failures.append("Pass E did not emit warning for expired ratchet test.expired_ratchet")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("selftest OK")
    return 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Meta-guard: verifies house-law registry completeness and honesty."
    )
    ap.add_argument("--selftest", action="store_true",
                    help="Run synthetic selftest; exit 0 on pass, 1 on failure.")
    ap.add_argument("--emit-docs", nargs="?", const=DEFAULT_DOCS_PATH, metavar="PATH",
                    help=f"Regenerate docs file (default: {DEFAULT_DOCS_PATH})")
    ap.add_argument("--emit-json", metavar="PATH",
                    help="Dump normalized registry JSON to PATH")
    ap.add_argument("--root", default=None, metavar="PATH",
                    help="Repository root (default: auto-detected from script location)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else _repo_root()

    if args.selftest:
        return run_selftest(root)

    # Load registry
    try:
        registry = _load_registry(root)
    except Exception as e:
        print(f"HARD: could not load {REGISTRY_PATH}: {e}")
        return 1

    if registry.get("schema") != "house_law_checks.v1":
        print(f"HARD: registry schema must be 'house_law_checks.v1', "
              f"got '{registry.get('schema')}'")
        return 1

    checks = registry.get("checks", [])
    if not isinstance(checks, list):
        print("HARD: 'checks' must be a list")
        return 1

    findings: list[str] = []

    # Run all passes
    pass_a_schema(checks, findings)
    pass_b_census(checks, root, findings)
    pass_c_wiring(checks, root, findings)
    pass_d_selftest_truth(checks, root, findings)
    pass_e_ratchet_expiry(checks)  # warnings only, no hard findings

    # Emit docs if requested
    if args.emit_docs is not None:
        out_path = root / args.emit_docs
        emit_docs(checks, out_path, updated=str(registry.get("updated", "")))
        print(f"docs emitted to {out_path}")

    # Emit JSON if requested
    if args.emit_json:
        out_path = Path(args.emit_json)
        emit_json(checks, out_path)
        print(f"JSON emitted to {out_path}")

    if findings:
        for f in findings:
            print(f"HARD: {f}")
        return 1

    # Summary stats
    n_total = len(checks)
    ci_wired = sum(
        1 for e in checks
        if e.get("ci_wiring") and any(w.get("lane") != "hook" for w in e["ci_wiring"])
    )
    discipline_only = sum(
        1 for e in checks
        if e.get("severity") in ("discipline", "known_spurious")
    )

    print(
        f"house-law registry OK — {n_total} laws, "
        f"{ci_wired} enforced in CI, "
        f"{discipline_only} discipline/spurious-only"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
