#!/usr/bin/env python3
"""Enforce the public-repository Wave B/C runner-routing boundary.

Ordinary PR CI, plan/gate, and fences remain hosted. Only explicit dispatch-only
diagnostics may reach the new PC/M1 labels. Existing production self-hosted lanes are
left untouched; this guard owns the new migration labels and the fork boundary.

It also owns the label-DECLARATION boundary (rules R11/R12, added 2026-08-17): every
literal ``runs-on`` label in every workflow must be declared in
``.github/runner-policy.yml``'s ``label_registry``, and a label whose registry entry
is ``orphaned`` may not be used by a scheduled workflow without a dated
``scheduled_use_waiver``. See the registry's own header comment for why — a runner
label lives only in GitHub's runners-API state, so deregistering a host silently
orphans every label it carried, and a cron job queued on a dead label can hold its
concurrency group hostage for 24h (research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md).
"""

from __future__ import annotations

import argparse
import json
import re
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
TRUSTED_PULL_REQUEST_TARGET = ".github/workflows/ci-authority.yml"
TRUSTED_AUTHORITY_CHECKOUT = (
    "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
)
TRUSTED_AUTHORITY_CHECKOUT_WITH = {
    "ref": "${{ github.event.repository.default_branch }}",
    "fetch-depth": 1,
    "sparse-checkout": "scripts",
    "persist-credentials": False,
}
FORBIDDEN_CANDIDATE_CHECKOUT_FRAGMENTS = (
    "pull_request.head",
    "merge_group.head",
    "github.sha",
)
RUNTIME_WORKFLOWS = {
    "mastermindx-market-intelligence/macro/.github/workflows/selfhosted-ci-canary.yml@refs/heads/main",
    "mastermindx-market-intelligence/macro/.github/workflows/m1-runner-canary.yml@refs/heads/main",
    "mastermindx-market-intelligence/macro/.github/workflows/engine-render.yml@refs/heads/main",
    "mastermindx-market-intelligence/macro/.github/workflows/render.yml@refs/heads/main",
    "mastermindx-market-intelligence/macro/.github/workflows/trusted-ci-executor.yml@refs/heads/main",
}
LABEL_REGISTRY_VALID_STATUS = {"live", "github-hosted", "offline", "orphaned"}
# Every single-quoted literal inside a `${{ }}` expression. Never matches a bare
# identifier like `github.event.inputs.runner` — those are unquoted operands, so
# they never contribute a (bogus) label.
_QUOTED_LITERAL_RE = re.compile(r"'([^']*)'")
# A quoted literal that is the RHS of a `==`/`!=` comparison (e.g. the `'1'` in
# `inputs.slots == '1'`) — stripped before label extraction. It IS single-quoted,
# so a bare quote scan would otherwise invent a phantom label out of it; it is
# never itself a candidate runs-on value, unlike the literal(s) on the other side
# of the `&&`/`||` it gates.
_COMPARISON_LITERAL_RE = re.compile(r"(?:==|!=)\s*'[^']*'")


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
    if isinstance(value, dict):
        return " ".join(
            str(item)
            for item in (value.get("group", ""), value.get("labels", ""))
        )
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _labels_from_scalar(text: str) -> set[str]:
    """The literal runner label(s) one ``runs-on`` scalar (or list entry) names.

    A plain string (``ubuntu-latest``) is the label itself. A ``${{ }}``
    expression is scanned for every single-quoted string literal — never the
    unquoted operands around it, so ``github.event.inputs.runner`` in
    ``github.event.inputs.runner || 'render-heavy'`` contributes nothing while
    ``'render-heavy'`` contributes the label. A quoted literal that itself
    round-trips through JSON as a list — the ``fromJSON('["a","b"]')`` shape —
    is expanded to its elements instead of being kept as one opaque string.
    """
    if "${{" not in text:
        literal = text.strip()
        return {literal} if literal else set()
    scannable = _COMPARISON_LITERAL_RE.sub("", text)
    labels: set[str] = set()
    for match in _QUOTED_LITERAL_RE.findall(scannable):
        parsed = None
        try:
            parsed = json.loads(match)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            labels |= {str(item) for item in parsed if isinstance(item, str)}
        elif match:
            labels.add(match)
    return labels


def runs_on_labels(job: dict) -> set[str]:
    """The set of LITERAL runner labels a job's ``runs-on`` resolves to.

    Handles a plain string, a list of plain strings, a list whose entries are
    themselves ``${{ }}`` expressions (render.yml's
    ``[self-hosted, ${{ github.event.inputs.runner || 'render-heavy' }}]``
    shape), and a top-level expression such as engine-render.yml's
    ``${{ github.event.inputs.runner || 'render-linux' }}`` or
    selfhosted-ci-canary.yml's
    ``${{ fromJSON('["self-hosted","ci-linux-canary"]') }}``. Non-literal
    operands never appear in the result — see ``_labels_from_scalar``.
    """
    value = job.get("runs-on")
    if isinstance(value, str):
        return _labels_from_scalar(value)
    if isinstance(value, list):
        labels: set[str] = set()
        for item in value:
            labels |= _labels_from_scalar(str(item))
        return labels
    if isinstance(value, dict):
        labels = value.get("labels")
        if isinstance(labels, list):
            found: set[str] = set()
            for item in labels:
                found |= _labels_from_scalar(str(item))
            return found
        return _labels_from_scalar(str(labels or ""))
    return set()


def needs_names(job: dict) -> set[str]:
    raw = job.get("needs", [])
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {str(item) for item in raw}
    return set()


def reaches_trust_gate(jobs: dict, job_id: str, seen: set[str] | None = None) -> bool:
    if job_id == "trust-gate":
        return True
    seen = set() if seen is None else seen
    if job_id in seen:
        return False
    seen.add(job_id)
    job = jobs.get(job_id)
    if not isinstance(job, dict):
        return False
    return any(reaches_trust_gate(jobs, name, seen) for name in needs_names(job))


def _authority_controller_r2_findings(relative: str, document: dict) -> list[Finding]:
    """R2: pull_request_target is forbidden except the trusted-base controller.

    ``ci-authority.yml`` may use ``pull_request_target`` only while it remains a
    default-branch controller that never materializes candidate code. Any other
    file, or this file after losing those pins, is still R2. That is not a
    general allowlist: a second ``pull_request_target`` workflow, or this one
    checking out the PR head, still fails the same rule.
    """
    if relative != TRUSTED_PULL_REQUEST_TARGET:
        return [Finding("R2", f"{relative}: pull_request_target is forbidden")]

    findings: list[Finding] = []
    if "pull_request" in triggers(document):
        findings.append(
            Finding(
                "R2",
                f"{relative}: trusted controller must not also trigger on pull_request",
            )
        )
    if document.get("permissions") != {}:
        findings.append(
            Finding(
                "R2",
                f"{relative}: trusted controller must declare empty workflow permissions",
            )
        )
    jobs = document.get("jobs") or {}
    if set(jobs) != {"ci-authority"}:
        findings.append(
            Finding(
                "R2",
                f"{relative}: trusted controller must contain only job ci-authority",
            )
        )
        return findings
    job = jobs["ci-authority"]
    if not isinstance(job, dict):
        findings.append(Finding("R2", f"{relative}: ci-authority job must be a mapping"))
        return findings
    if "uses" in job:
        findings.append(
            Finding(
                "R2",
                f"{relative}: trusted controller may not delegate to a reusable workflow",
            )
        )
    if job.get("runs-on") != HOSTED:
        findings.append(
            Finding(
                "R2",
                f"{relative}: trusted controller must remain exactly {HOSTED}",
            )
        )
    steps = [step for step in (job.get("steps") or []) if isinstance(step, dict)]
    checkouts = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    if len(checkouts) != 1:
        findings.append(
            Finding("R2", f"{relative}: trusted controller must have exactly one checkout")
        )
        return findings
    checkout = checkouts[0]
    if checkout.get("uses") != TRUSTED_AUTHORITY_CHECKOUT:
        findings.append(
            Finding("R2", f"{relative}: trusted controller checkout must stay pinned")
        )
    if checkout.get("with") != TRUSTED_AUTHORITY_CHECKOUT_WITH:
        findings.append(
            Finding(
                "R2",
                f"{relative}: trusted controller must checkout only the default branch without credentials",
            )
        )
    checkout_text = yaml.safe_dump(checkout)
    if any(fragment in checkout_text for fragment in FORBIDDEN_CANDIDATE_CHECKOUT_FRAGMENTS):
        findings.append(
            Finding(
                "R2",
                f"{relative}: trusted controller must not materialize candidate code",
            )
        )
    return findings


def _label_registry_hygiene_findings(label_registry: dict) -> list[Finding]:
    """R11 hygiene: every registry entry is a well-formed, self-consistent mapping."""
    findings: list[Finding] = []
    for label, entry in label_registry.items():
        if not isinstance(entry, dict):
            findings.append(
                Finding("R11", f"label_registry entry {label!r} must be a mapping")
            )
            continue
        status = entry.get("status")
        if status not in LABEL_REGISTRY_VALID_STATUS:
            findings.append(
                Finding(
                    "R11",
                    f"label_registry entry {label!r} has invalid status {status!r}",
                )
            )
        carried_by = entry.get("carried_by")
        if not isinstance(carried_by, list):
            findings.append(
                Finding(
                    "R11",
                    f"label_registry entry {label!r} must declare a carried_by list",
                )
            )
            continue
        if status in ("live", "offline") and not carried_by:
            findings.append(
                Finding(
                    "R11",
                    f"label_registry entry {label!r} status {status!r} must declare a non-empty carried_by",
                )
            )
        if status in ("github-hosted", "orphaned") and carried_by:
            findings.append(
                Finding(
                    "R11",
                    f"label_registry entry {label!r} status {status!r} must declare an empty carried_by",
                )
            )
    return findings


def _label_registry_findings(registry: dict, documents: dict[str, dict]) -> list[Finding]:
    """R11 (every used label is declared) + R12 (no scheduled use of an orphan)."""
    label_registry = registry.get("label_registry") or {}
    findings = _label_registry_hygiene_findings(label_registry)
    for relative, document in documents.items():
        has_schedule = "schedule" in triggers(document)
        for job_id, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for label in runs_on_labels(job):
                entry = label_registry.get(label)
                if entry is None:
                    findings.append(
                        Finding(
                            "R11",
                            f"{relative}:{job_id} uses unregistered runner label {label!r} — add it to .github/runner-policy.yml label_registry",
                        )
                    )
                    continue
                if not has_schedule or not isinstance(entry, dict):
                    continue
                if entry.get("status") != "orphaned":
                    continue
                waiver = entry.get("scheduled_use_waiver")
                waived = (
                    isinstance(waiver, dict)
                    and bool(waiver.get("reason"))
                    and bool(waiver.get("since"))
                )
                if not waived:
                    findings.append(
                        Finding(
                            "R12",
                            f"{relative}:{job_id} schedules onto orphaned label {label!r} — a queued job on a dead label can hold its cron concurrency group for 24h",
                        )
                    )
    return findings


def evaluate(root: Path, registry_path: Path, workflows_dir: Path) -> list[Finding]:
    registry = load_yaml(registry_path)
    findings: list[Finding] = []
    if registry.get("schema") != "runner_policy.v2":
        findings.append(Finding("R0", "runner policy schema must be runner_policy.v2"))
    if registry.get("phase") != "p3a-inert-trusted-executor":
        findings.append(Finding("R0", "runner policy must describe the P3A inert executor phase"))
    if registry.get("repository_visibility") != "public":
        findings.append(Finding("R0", "repository visibility boundary must remain public"))
    expected_scenarios = {
        "same_repo_ordinary_pr": "github-hosted",
        "fork_pr": "github-hosted",
        "trusted_dispatch_canary": "pc-ci-canary",
        "trusted_executor_dispatch": "pc-ci",
    }
    if registry.get("scenario_routes") != expected_scenarios:
        findings.append(Finding("R1", "synthetic trust-routing scenarios drifted"))
    runtime_group = registry.get("runtime_runner_group") or {}
    if (
        runtime_group.get("name") != "macro-home-canary"
        or runtime_group.get("repository") != "mastermindx-market-intelligence/macro"
        or runtime_group.get("allows_public_repositories") is not True
        or runtime_group.get("restricted_to_workflows") is not True
        or set(runtime_group.get("selected_workflows") or []) != RUNTIME_WORKFLOWS
    ):
        findings.append(
            Finding("R1", "server-side macro-home-canary runner-group policy drifted")
        )

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
            findings.extend(_authority_controller_r2_findings(relative, document))
        for job_id, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            if "pull_request" in workflow_triggers:
                if "uses" in job:
                    findings.append(
                        Finding(
                            "R3",
                            f"{relative}:{job_id} may not delegate to a reusable workflow on pull_request during Wave B/C",
                        )
                    )
                elif job.get("runs-on") != HOSTED:
                    findings.append(
                        Finding(
                            "R3",
                            f"{relative}:{job_id} must remain exactly {HOSTED} on pull_request during Wave B/C",
                        )
                    )

    findings.extend(_label_registry_findings(registry, documents))

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
        jobs = document.get("jobs") or {}
        trust = jobs.get("trust-gate")
        trust_text = str(trust)
        if (
            not isinstance(trust, dict)
            or trust.get("runs-on") != HOSTED
            or "refs/heads/main" not in trust_text
            or "github.ref" not in trust_text
            or not reaches_trust_gate(jobs, job_id)
        ):
            findings.append(
                Finding("R5", f"{workflow}:{job_id} is not downstream of the hosted main trust-gate")
            )
        job = jobs.get(job_id)
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

    trusted_route = registry.get("trusted_executor_route") or {}
    expected_trusted_route = {
        "workflow": ".github/workflows/trusted-ci-executor.yml",
        "job": "trusted-pack",
        "group": "macro-home-canary",
        "labels": ["ci-linux"],
        "production_enabled": False,
    }
    if trusted_route != expected_trusted_route:
        findings.append(
            Finding("R13", "P3A trusted executor declaration drifted or enabled production early")
        )
    trusted_workflow = str(trusted_route.get("workflow", ""))
    trusted_job_id = str(trusted_route.get("job", ""))
    if trusted_workflow and trusted_job_id:
        allowed_custom.add((trusted_workflow, trusted_job_id))
    trusted_document = documents.get(trusted_workflow)
    if trusted_document is None:
        findings.append(Finding("R13", "P3A trusted executor workflow is missing"))
    else:
        trusted_jobs = trusted_document.get("jobs") or {}
        trust_gate = trusted_jobs.get("trust-gate") or {}
        plan_job = trusted_jobs.get("plan") or {}
        trusted_job = trusted_jobs.get(trusted_job_id) or {}
        trigger_config = trusted_document.get(
            "on", trusted_document.get(True, {})
        )
        exact_inputs = {"pr_number"}
        trigger_inputs_are_exact = (
            isinstance(trigger_config, dict)
            and all(
                isinstance(trigger_config.get(event), dict)
                and set((trigger_config[event].get("inputs") or {})) == exact_inputs
                for event in ("workflow_call", "workflow_dispatch")
            )
        )
        trust_steps = trust_gate.get("steps") or []
        gate_step = next(
            (
                step
                for step in trust_steps
                if isinstance(step, dict)
                and step.get("name") == "keep P3A dispatch-provable and production-inert"
            ),
            {},
        )
        gate_lines = {
            line.strip() for line in str(gate_step.get("run", "")).splitlines()
        }
        gate_env_is_exact = gate_step.get("env") == {
            "EVENT_NAME": "${{ github.event_name }}",
            "TRUSTED_REF": "${{ github.ref }}",
            "TRUSTED_WORKFLOW_REF": "${{ github.workflow_ref }}",
            "PR_NUMBER": "${{ inputs.pr_number }}",
        }
        executable_refusals_are_exact = {
            'test "$EVENT_NAME" = workflow_dispatch || {',
            'test "$TRUSTED_REF" = refs/heads/main || {',
            (
                'test "$TRUSTED_WORKFLOW_REF" = mastermindx-market-intelligence/'
                "macro/.github/workflows/trusted-ci-executor.yml@refs/heads/main || {"
            ),
        } <= gate_lines
        if triggers(trusted_document) != {"workflow_call", "workflow_dispatch"}:
            findings.append(Finding("R13", "P3A executor triggers must stay call-capable and dispatch-provable"))
        if not trigger_inputs_are_exact:
            findings.append(Finding("R13", "P3A executor may accept only the pr_number input"))
        if (
            trust_gate.get("runs-on") != HOSTED
            or not gate_env_is_exact
            or not executable_refusals_are_exact
            or plan_job.get("runs-on") != HOSTED
            or plan_job.get("needs") != "trust-gate"
        ):
            findings.append(Finding("R13", "P3A hosted trust and planner boundary drifted"))
        if (
            not isinstance(trusted_job, dict)
            or trusted_job.get("needs") != "plan"
            or trusted_job.get("runs-on")
            != {"group": "macro-home-canary", "labels": "ci-linux"}
        ):
            findings.append(Finding("R13", "P3A trusted pack lost its selected group and exact label"))
        ci_document = documents.get(".github/workflows/ci.yml") or {}
        if "trusted-ci-executor.yml" in str(ci_document):
            findings.append(Finding("R13", "P3A must not route production ci.yml through the executor"))

    runner_group_name = str(runtime_group.get("name", ""))
    runner_group_consumers = {
        (workflow, str(job_id))
        for workflow, document in documents.items()
        for job_id, job in (document.get("jobs") or {}).items()
        if isinstance(job, dict)
        and isinstance(job.get("runs-on"), dict)
        and job["runs-on"].get("group") == runner_group_name
    }
    expected_group_consumers = {(trusted_workflow, trusted_job_id)}
    if runner_group_consumers != expected_group_consumers:
        findings.append(
            Finding(
                "R13",
                "P3A runner-group consumer set must be exactly "
                f"{sorted(expected_group_consumers)}; found {sorted(runner_group_consumers)}",
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
    materialize_positions = [
        i
        for i, step in enumerate(steps)
        if isinstance(step, dict)
        and str(step.get("name", "")).startswith("materialize exact candidate")
    ]
    if (
        not prewarm_positions
        or not materialize_positions
        or prewarm_positions[0] >= materialize_positions[0]
    ):
        findings.append(
            Finding(
                "R9",
                "self-hosted canary must prewarm before candidate materialization",
            )
        )
    rendered_steps = str(steps)
    if "/usr/local/libexec/mastermind-ci-prewarm" not in rendered_steps:
        findings.append(Finding("R9", "self-hosted canary is not bound to the host prewarm"))
    if any(
        step.get("uses") == "actions/checkout@v4"
        for step in steps
        if isinstance(step, dict)
    ):
        findings.append(
            Finding(
                "R9",
                "self-hosted canary may not use no-negotiation actions/checkout",
            )
        )
    required_materialization = (
        "fetch.negotiationAlgorithm=skipping",
        "--filter=blob:none --depth=1",
        'origin "$TESTED_SHA"',
        "GIT_TERMINAL_PROMPT=0",
        "GIT_ASKPASS=/bin/false",
        "credential.helper=",
        "git config --get-regexp '^http\\..*\\.extraheader$'",
    )
    materialization = (
        str(steps[materialize_positions[0]].get("run", ""))
        if materialize_positions
        else ""
    )
    credential_guard = materialization.find("git config --get-regexp")
    fetch_command = materialization.find("git -c credential.helper=")
    if (
        any(token not in materialization for token in required_materialization)
        or credential_guard < 0
        or fetch_command < 0
        or credential_guard >= fetch_command
    ):
        findings.append(
            Finding(
                "R9",
                "self-hosted candidate fetch is not negotiated, exact-SHA, and credential-free",
            )
        )
    contamination_steps = (
        ((canary.get("jobs") or {}).get("contamination-probe") or {}).get("steps")
        or []
    )
    detach = next(
        (
            step
            for step in contamination_steps
            if isinstance(step, dict)
            and str(step.get("name", "")).startswith("detach the second")
        ),
        {},
    )
    if (
        (detach.get("env") or {}).get("GIT_NO_LAZY_FETCH") != "1"
        or "git fetch" in str(detach.get("run", ""))
        or any(
            isinstance(step, dict) and step.get("uses") == "actions/checkout@v4"
            for step in contamination_steps
        )
    ):
        findings.append(
            Finding("R9", "contamination probe must detach cache-only and fail closed")
        )
    if "cache-negative-control" not in (canary.get("jobs") or {}):
        findings.append(Finding("R9", "cache-disabled negative-control job is missing"))
    for job_id, job in (canary.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for index, step in enumerate(job.get("steps") or []):
            if not isinstance(step, dict) or step.get("uses") != "actions/checkout@v4":
                continue
            if (step.get("with") or {}).get("persist-credentials") is not False:
                findings.append(
                    Finding(
                        "R10",
                        f"self-hosted-ci-canary.yml:{job_id}:step-{index} must disable checkout credential persistence",
                    )
                )
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
    print("OK: P3A runner routing is hosted-by-default with an inert main-selected executor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
