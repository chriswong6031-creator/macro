#!/usr/bin/env python3
"""Enforce the public-repository Wave B/C runner-routing boundary.

Ordinary PR CI, plan/gate, and fences remain hosted. Only explicit dispatch-only
diagnostics may reach the new PC/M1 labels. Existing production self-hosted lanes are
left untouched; this guard owns the new migration labels and the fork boundary.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


CUSTOM_LABELS = {
    "ci-linux",
    "ci-linux-canary",
    "m1-nightly",
    "m1-theta",
    "m1-light",
}
HOSTED = "ubuntu-latest"


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str


def load_yaml(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a mapping")
    return document


def triggers(document: dict) -> set[str]:
    raw = document.get("on", document.get(True, {}))
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {str(item) for item in raw}
    if isinstance(raw, dict):
        return {str(item) for item in raw}
    return set()


def runs_on_text(job: dict) -> str:
    value = job.get("runs-on", "")
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def same_repo_guard(job: dict) -> bool:
    text = runs_on_text(job) + " " + str(job.get("if", ""))
    return "head.repo.full_name == github.repository" in text


def evaluate(root: Path, registry_path: Path, workflows_dir: Path) -> list[Finding]:
    registry = load_yaml(registry_path)
    findings: list[Finding] = []
    if registry.get("schema") != "runner_policy.v2":
        findings.append(Finding("R0", "runner policy schema must be runner_policy.v2"))
    if registry.get("phase") != "wave-bc-canary":
        findings.append(Finding("R0", "runner policy must describe Wave B/C canary phase"))
    if registry.get("repository_visibility") != "public":
        findings.append(Finding("R0", "repository visibility boundary must remain public"))
    expected_scenarios = {
        "same_repo_ordinary_pr": "github-hosted",
        "fork_pr": "github-hosted",
        "trusted_dispatch_canary": "pc-ci-canary",
    }
    if registry.get("scenario_routes") != expected_scenarios:
        findings.append(Finding("R1", "synthetic trust-routing scenarios drifted"))

    documents: dict[str, dict] = {}
    for path in sorted(workflows_dir.glob("*.y*ml")):
        relative = str(path.relative_to(root))
        try:
            document = load_yaml(path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            findings.append(Finding("R0", f"{relative}: cannot parse workflow: {exc}"))
            continue
        documents[relative] = document
        workflow_triggers = triggers(document)
        if "pull_request_target" in workflow_triggers:
            findings.append(Finding("R2", f"{relative}: pull_request_target is forbidden"))
        for job_id, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict) or "runs-on" not in job:
                continue
            text = runs_on_text(job)
            custom = {label for label in CUSTOM_LABELS if label in text}
            if custom and "pull_request" in workflow_triggers and not same_repo_guard(job):
                findings.append(
                    Finding(
                        "R3",
                        f"{relative}:{job_id} exposes a migration label to pull_request without a same-repo guard",
                    )
                )

    for route in registry.get("protected_hosted_routes") or []:
        workflow = route.get("workflow")
        document = documents.get(workflow)
        if document is None:
            findings.append(Finding("R4", f"protected workflow missing: {workflow}"))
            continue
        for job_id in route.get("jobs") or []:
            job = (document.get("jobs") or {}).get(job_id)
            if not isinstance(job, dict) or job.get("runs-on") != HOSTED:
                findings.append(
                    Finding("R4", f"{workflow}:{job_id} must remain {HOSTED}")
                )

    allowed_custom: set[tuple[str, str]] = set()
    for route in registry.get("custom_routes") or []:
        workflow = str(route.get("workflow"))
        job_id = str(route.get("job"))
        allowed_custom.add((workflow, job_id))
        document = documents.get(workflow)
        if document is None:
            findings.append(Finding("R5", f"custom-route workflow missing: {workflow}"))
            continue
        if triggers(document) != {route.get("event")}:
            findings.append(
                Finding("R5", f"{workflow}:{job_id} must be dispatch-only")
            )
        job = (document.get("jobs") or {}).get(job_id)
        if not isinstance(job, dict):
            findings.append(Finding("R5", f"custom-route job missing: {workflow}:{job_id}"))
            continue
        text = runs_on_text(job)
        for label in route.get("labels") or []:
            if str(label) not in text:
                findings.append(
                    Finding("R5", f"{workflow}:{job_id} lost required label {label}")
                )
        if any(str(label).startswith("m1-") for label in route.get("labels") or []):
            broad = {"macstudio", "macstudio-light", "theta-m1", "codex", "render-heavy"}
            leaked = {label for label in broad if label in text}
            if leaked:
                findings.append(
                    Finding(
                        "R8",
                        f"{workflow}:{job_id} leaked generic M1 production label(s): {sorted(leaked)}",
                    )
                )

    for workflow, document in documents.items():
        for job_id, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            text = runs_on_text(job)
            if any(label in text for label in CUSTOM_LABELS):
                if (workflow, str(job_id)) not in allowed_custom:
                    findings.append(
                        Finding("R6", f"unregistered migration-label consumer: {workflow}:{job_id}")
                    )

    topology = registry.get("pool_topology") or {}
    for name, pool in topology.items():
        labels = set(pool.get("labels") or [])
        forbidden = set(pool.get("forbidden_labels") or [])
        overlap = labels & forbidden
        if overlap:
            findings.append(
                Finding("R7", f"pool {name} contains forbidden label(s): {sorted(overlap)}")
            )
    ci_labels = set((topology.get("pc-ci") or {}).get("labels") or [])
    render_labels = set((topology.get("pc-render") or {}).get("labels") or [])
    if (ci_labels & render_labels) - {"self-hosted"}:
        findings.append(Finding("R7", "PC CI and render pools overlap beyond self-hosted"))
    if (topology.get("pc-ci") or {}).get("slots") != 3:
        findings.append(Finding("R7", "PC CI topology must reserve exactly three slots"))
    if (topology.get("pc-render") or {}).get("slots") != 1:
        findings.append(Finding("R7", "PC render topology must reserve exactly one slot"))
    m1 = topology.get("m1-theta-canary") or {}
    broad = {"macstudio", "macstudio-light", "theta-m1", "codex", "render-heavy"}
    if set(m1.get("labels") or []) & broad:
        findings.append(Finding("R8", "M1 canary topology leaked a generic production label"))

    canary = documents.get(".github/workflows/selfhosted-ci-canary.yml") or {}
    selfhosted_job = (canary.get("jobs") or {}).get("selfhosted-pack") or {}
    steps = selfhosted_job.get("steps") or []
    names = [str(step.get("name", "")) for step in steps if isinstance(step, dict)]
    prewarm_positions = [
        i for i, name in enumerate(names) if name.startswith("prewarm exact base")
    ]
    checkout_positions = [i for i, step in enumerate(steps) if isinstance(step, dict) and step.get("uses") == "actions/checkout@v4"]
    if not prewarm_positions or not checkout_positions or prewarm_positions[0] >= checkout_positions[0]:
        findings.append(Finding("R9", "self-hosted canary must prewarm before actions/checkout"))
    rendered_steps = str(steps)
    if "/usr/local/libexec/mastermind-ci-prewarm" not in rendered_steps:
        findings.append(Finding("R9", "self-hosted canary is not bound to the host prewarm"))
    if "cache-negative-control" not in (canary.get("jobs") or {}):
        findings.append(Finding("R9", "cache-disabled negative-control job is missing"))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--workflows-dir", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    registry = args.registry or root / ".github" / "runner-policy.yml"
    workflows = args.workflows_dir or root / ".github" / "workflows"
    findings = evaluate(root, registry.resolve(), workflows.resolve())
    for finding in findings:
        print(f"::error title=runner-policy-{finding.rule}::{finding.message}", flush=True)
    if findings:
        print(f"FAIL: {len(findings)} runner-policy finding(s)")
        return 1
    print("OK: Wave B/C runner routing is hosted-by-default and canary-only self-hosted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
