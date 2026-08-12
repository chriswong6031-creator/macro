#!/usr/bin/env python3
"""Guard: trusted CI runs SELF-HOSTED; every GitHub-hosted job is a registered exception.

Operator charter 2026-08-12 ("Mastermind GitHub CI Cost + Flow Migration"). The
default inverted: routine trusted CI consumes self-hosted compute, and hosted
compute must be written down in ``.github/runner-policy.yml`` with a class and a
reason. Design doc: research/CI_SELFHOSTED_MIGRATION_WAVE1.md.

WHY A GUARD AND NOT A CONVENTION. A job that drifts back to ``ubuntu-latest``
still passes every other check in this repository — the drift is invisible
precisely because nothing breaks. And the cost is invisible too, today: measured
month-to-date 2026-08, this repo metered 267,066 Actions Linux minutes at
$1,602.40 gross and paid $0.00, because a PUBLIC repository is fully discounted.
The moment visibility flips (the operator's stated intent) the same volume is
~$130+/day. So this file exists to hold a migration in place across the months
where nothing appears to be at stake.

The SECURITY half is not about money at all and is the half that must never be
relaxed: this repository is public, the self-hosted fleet is four runner slots on
one physical machine in the operator's home, and a ``pull_request`` from a fork
carries attacker-authored code. A fork head that lands on a persistent runner is
arbitrary code execution against the whole fleet's workspace, caches and network.

RULES (all fail-closed):

  R1  Any job that CAN resolve to a hosted label must have a registry entry.
      "Can resolve" includes OPAQUE ``runs-on`` — an expression carrying neither
      a hosted label literal nor ``self-hosted`` (e.g. ``${{ inputs.runner ||
      'render-linux' }}``) is undecidable, and inability to prove a job is
      self-hosted is not evidence that it is.

  R2  Any job that CAN resolve to self-hosted, in a workflow with a
      ``pull_request`` trigger, must carry a same-repo guard: either the
      ``head.repo.full_name != github.repository`` fork branch inside its
      ``runs-on`` expression (ci.yml's ``ci-pack``), or
      ``head.repo.full_name == github.repository`` in the job's ``if:``
      (fences.yml's ``fence-pack``). Without one, a fork PR executes on the home
      fleet.

  R3  ``pull_request_target`` is forbidden outright, with NO registry override.
      It runs with a writable token in the BASE repo's context against a
      contributor-controlled head; combined with self-hosted runners it is the
      single worst shape available. There is no entry that makes it acceptable.

  R4  A registry entry that matches no job on disk is a WARNING (stale debt), not
      an error — deleting a workflow must not red the guard that guarded it.

Usage:
    python3 scripts/check_runner_policy.py [--workflows-dir DIR] [--registry PATH]
    python3 scripts/check_runner_policy.py --selftest

Exit codes: 0 clean; 1 violations; 2 internal error (unreadable registry/dir).

ANNOTATION LAW (repo-wide, tests/test_gh_annotation_line_start.py): every
GitHub annotation below is a bare ``print("::error title=runner-policy::...",
flush=True)`` starting the line. A logger's prefix ("ERROR ::error …") makes
GitHub drop the annotation silently, which has shipped dead five times here.
``flush`` is load-bearing: stdout is block-buffered when piped in CI.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_REGISTRY = ".github/runner-policy.yml"
DEFAULT_WORKFLOWS_DIR = ".github/workflows"

# A hosted runner label GitHub provides. Kept as a pattern as well as a list so a
# future `ubuntu-26.04` is caught the day it appears, not the day someone
# remembers to extend the registry.
HOSTED_LABEL_RE = re.compile(r"^(ubuntu|macos|windows)-", re.IGNORECASE)
# The same family, matched INSIDE an expression string where the label appears as
# a quoted literal (`... && 'ubuntu-latest' || ...`).
HOSTED_LITERAL_RE = re.compile(r"\b(ubuntu|macos|windows)-[a-z0-9._-]+", re.IGNORECASE)

FORK_GUARD_IN_RUNS_ON = "github.event.pull_request.head.repo.full_name != github.repository"
SAME_REPO_GUARD_IN_IF = "head.repo.full_name == github.repository"


def _annotate(level: str, message: str) -> None:
    """Emit one GitHub annotation. Bare print at line start — never via logging."""
    print(f"::{level} title=runner-policy::{message}", flush=True)


# ── runs-on resolution ────────────────────────────────────────────────────────

@dataclass
class Resolution:
    """What a job's ``runs-on`` can resolve to. Both flags may be true at once."""

    can_hosted: bool = False
    can_self_hosted: bool = False
    opaque: bool = False
    detail: str = ""

    @property
    def needs_registry(self) -> bool:
        # Opaque counts as hosted-capable: fail closed (see R1).
        return self.can_hosted or self.opaque

    @property
    def maybe_self_hosted(self) -> bool:
        # Opaque counts as self-hosted-capable too: fail closed (see R2).
        return self.can_self_hosted or self.opaque


def _is_hosted_label(value: str) -> bool:
    return bool(HOSTED_LABEL_RE.match(value.strip()))


def resolve_runs_on(runs_on: object, hosted_labels: set[str]) -> Resolution:
    """Classify one ``runs-on`` value.

    Four shapes occur in this repository:
      * static string   — ``ubuntu-latest`` / ``self-hosted``
      * static list     — ``[self-hosted, Linux, X64, render-linux]``, possibly
                          with an expression ELEMENT (render.yml's
                          ``[self-hosted, "${{ inputs.runner || 'render-heavy' }}"]``)
      * expression      — the whole value is ``${{ ... }}``
      * mapping         — ``{group: ..., labels: [...]}`` (runner groups)
    """
    if runs_on is None:
        return Resolution(opaque=True, detail="missing runs-on")

    if isinstance(runs_on, dict):
        labels = runs_on.get("labels") or []
        if isinstance(labels, str):
            labels = [labels]
        return resolve_runs_on(list(labels), hosted_labels)

    if isinstance(runs_on, list):
        res = Resolution(detail=f"list {runs_on}")
        for element in runs_on:
            text = str(element)
            if "${{" in text:
                # An expression ELEMENT never removes the static `self-hosted`
                # sibling, so it cannot make the job hosted on its own; it only
                # picks which self-hosted pool. Note it, do not fail on it.
                continue
            if text.strip() == "self-hosted":
                res.can_self_hosted = True
            elif _is_hosted_label(text) or text.strip() in hosted_labels:
                res.can_hosted = True
        if not (res.can_hosted or res.can_self_hosted):
            res.opaque = True
        return res

    text = str(runs_on)
    if "${{" in text:
        res = Resolution(detail=f"expression {' '.join(text.split())[:160]}")
        res.can_self_hosted = "self-hosted" in text
        res.can_hosted = bool(HOSTED_LITERAL_RE.search(text)) or any(
            label in text for label in hosted_labels
        )
        if not (res.can_hosted or res.can_self_hosted):
            res.opaque = True
        return res

    stripped = text.strip()
    if _is_hosted_label(stripped) or stripped in hosted_labels:
        return Resolution(can_hosted=True, detail=stripped)
    if stripped == "self-hosted":
        return Resolution(can_self_hosted=True, detail=stripped)
    return Resolution(opaque=True, detail=stripped)


# ── workflow walking ──────────────────────────────────────────────────────────

@dataclass
class JobRecord:
    workflow: str  # repo-relative path
    job_id: str
    resolution: Resolution
    job_if: str
    triggers: set[str] = field(default_factory=set)


def _triggers(doc: dict) -> set[str]:
    """Trigger names. PyYAML (YAML 1.1) reads the bare key ``on`` as boolean True."""
    on = doc.get("on", doc.get(True))
    if isinstance(on, dict):
        return {str(key) for key in on}
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return {str(item) for item in on}
    return set()


def collect_jobs(
    workflows_dir: Path, root: Path, hosted_labels: set[str]
) -> tuple[list[JobRecord], list[str]]:
    """Return (job records, hard findings raised while reading)."""
    findings: list[str] = []
    records: list[JobRecord] = []
    files = sorted(p for p in workflows_dir.iterdir() if p.suffix in (".yml", ".yaml"))
    for path in files:
        try:
            doc = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            # Parse failures are ops.workflow_yaml_parses' job, not this guard's.
            # Skipping keeps ONE red per defect instead of two, and that guard is
            # wired in the same CI job as this one.
            findings.append(f"{path}: unreadable ({str(exc).splitlines()[0]}) — skipped")
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict):
            continue
        rel = str(path.relative_to(root))
        triggers = _triggers(doc)
        for job_id, job in doc["jobs"].items():
            if not isinstance(job, dict):
                continue
            if "runs-on" not in job and "uses" in job:
                # A reusable-workflow CALL declares no runner; the callee owns it.
                # Local callees under .github/workflows are walked directly, so
                # skipping here loses no coverage.
                continue
            records.append(
                JobRecord(
                    workflow=rel,
                    job_id=str(job_id),
                    resolution=resolve_runs_on(job.get("runs-on"), hosted_labels),
                    job_if=" ".join(str(job.get("if", "")).split()),
                    triggers=triggers,
                )
            )
    return records, findings


# ── rules ─────────────────────────────────────────────────────────────────────

def evaluate(
    records: list[JobRecord], registry: dict
) -> tuple[list[str], list[str]]:
    """Apply R1-R4. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    entries = registry.get("hosted_exceptions") or []
    registered: dict[tuple[str, str], list[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"registry: entry is {type(entry).__name__}, expected a mapping")
            continue
        for field_name in ("workflow", "job", "class", "reason"):
            if not entry.get(field_name):
                errors.append(
                    f"registry: entry {entry!r} is missing required field '{field_name}'"
                )
        key = (str(entry.get("workflow", "")), str(entry.get("job", "")))
        registered.setdefault(key, []).append(str(entry.get("class", "")))

    seen_keys: set[tuple[str, str]] = set()
    for rec in records:
        key = (rec.workflow, rec.job_id)
        seen_keys.add(key)

        # R3 — pull_request_target, no override.
        if "pull_request_target" in rec.triggers:
            errors.append(
                f"{rec.workflow}: job '{rec.job_id}' lives in a workflow with a "
                f"`pull_request_target` trigger. That runs a contributor-controlled "
                f"head in the BASE repo's context with a writable token; on a public "
                f"repo with persistent self-hosted runners there is no registry entry "
                f"that makes it acceptable (R3)."
            )

        # R1 — hosted (or undecidable) needs an entry.
        if rec.resolution.needs_registry and key not in registered:
            shape = "OPAQUE" if rec.resolution.opaque else "hosted"
            errors.append(
                f"{rec.workflow}: job '{rec.job_id}' can resolve to a {shape} runner "
                f"(runs-on: {rec.resolution.detail}) but has no entry in the runner "
                f"policy registry. Add a {{workflow, job, class, reason}} entry, or "
                f"route it to self-hosted labels (R1)."
            )

        # R2 — self-hosted-capable in a PR-triggered workflow needs a trust gate.
        if rec.resolution.maybe_self_hosted and "pull_request" in rec.triggers:
            guarded = (
                FORK_GUARD_IN_RUNS_ON in rec.resolution.detail
                or SAME_REPO_GUARD_IN_IF in rec.job_if
            )
            if not guarded:
                errors.append(
                    f"{rec.workflow}: job '{rec.job_id}' can run on a self-hosted "
                    f"runner and its workflow has a `pull_request` trigger, but it "
                    f"carries no same-repo guard. A fork PR would execute untrusted "
                    f"code on the persistent home fleet. Add "
                    f"`{FORK_GUARD_IN_RUNS_ON}` to the runs-on expression or "
                    f"`{SAME_REPO_GUARD_IN_IF}` to the job's `if:` (R2)."
                )

    # R4 — stale entries are debt, not breakage.
    for key in sorted(registered):
        if key not in seen_keys:
            warnings.append(
                f"registry entry {key[0]}/{key[1]} matches no job on disk — stale "
                f"exception, remove it (R4)"
            )

    return errors, warnings


# ── driver ────────────────────────────────────────────────────────────────────

def run_check(
    workflows_dir: Path, registry_path: Path, root: Path, emit: bool = True
) -> int:
    try:
        registry = yaml.safe_load(registry_path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        if emit:
            _annotate("error", f"cannot read registry {registry_path}: {exc}")
        print(f"FAIL: cannot read registry {registry_path}: {exc}")
        return 2
    if not isinstance(registry, dict):
        if emit:
            _annotate("error", f"registry {registry_path} is not a mapping")
        print(f"FAIL: registry {registry_path} is not a mapping")
        return 2
    if not workflows_dir.is_dir():
        if emit:
            _annotate("error", f"{workflows_dir} is not a directory")
        print(f"FAIL: {workflows_dir} is not a directory")
        return 2

    default_policy = str(registry.get("default", "")).strip()
    if default_policy != "self-hosted":
        if emit:
            _annotate(
                "error",
                f"registry default is '{default_policy}', expected 'self-hosted' — "
                f"flipping the default is an operator decision, not a maintenance edit",
            )
        print(f"FAIL: registry default is '{default_policy}', expected 'self-hosted'")
        return 1

    hosted_labels = {str(label) for label in (registry.get("hosted_labels") or [])}
    records, read_findings = collect_jobs(workflows_dir, root, hosted_labels)
    errors, warnings = evaluate(records, registry)
    errors = read_findings + errors

    for line in warnings:
        if emit:
            _annotate("warning", line)
        print(f"WARN: {line}")
    for line in errors:
        if emit:
            _annotate("error", line)
        print(f"FAIL: {line}")

    hosted = sum(1 for r in records if r.resolution.can_hosted)
    selfh = sum(1 for r in records if r.resolution.can_self_hosted)
    opaque = sum(1 for r in records if r.resolution.opaque)
    print(
        f"\n{len(records)} job(s) across {len(set(r.workflow for r in records))} "
        f"workflow file(s): {hosted} hosted-resolvable, {selfh} self-hosted-resolvable, "
        f"{opaque} opaque; {len(registry.get('hosted_exceptions') or [])} registered "
        f"exception(s)."
    )
    if errors:
        print(f"{len(errors)} violation(s).")
        return 1
    print("OK: every hosted-resolvable job is registered; no untrusted head can "
          "reach a self-hosted runner.")
    return 0


# ── selftest ──────────────────────────────────────────────────────────────────

SELFTEST_REGISTRY = """\
schema: runner_policy.v1
default: self-hosted
hosted_labels:
  - ubuntu-latest
hosted_exceptions:
  - workflow: .github/workflows/registered.yml
    job: hosted-job
    class: cheap-orchestration
    reason: synthetic fixture
  - workflow: .github/workflows/dynamic.yml
    job: ci-pack
    class: fork-fallback
    reason: synthetic fixture — the fork branch of the routing expression
"""

SELFTEST_WORKFLOWS: dict[str, str] = {
    # PASS — hosted but registered.
    "registered.yml": (
        "name: registered\n"
        "on:\n  workflow_dispatch:\n"
        "jobs:\n  hosted-job:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
    ),
    # PASS — the real ci-pack shape: fork -> hosted, recovery -> hosted, else
    # self-hosted, guarded inside the expression itself.
    "dynamic.yml": (
        "name: dynamic\n"
        "on:\n  pull_request:\n  workflow_dispatch:\n"
        "jobs:\n  ci-pack:\n"
        "    runs-on: ${{ (github.event_name == 'pull_request' && "
        "github.event.pull_request.head.repo.full_name != github.repository) && "
        "'ubuntu-latest' || inputs.runner_pool == 'hosted' && 'ubuntu-latest' || "
        "fromJSON('[\"self-hosted\",\"Linux\",\"X64\",\"render-linux\"]') }}\n"
        "    steps:\n      - run: true\n"
    ),
    # PASS — static self-hosted list in a PR workflow, guarded by the job `if:`.
    "guarded.yml": (
        "name: guarded\n"
        "on:\n  pull_request:\n  push:\n"
        "jobs:\n  fence-pack:\n"
        "    if: github.event_name != 'pull_request' || "
        "github.event.pull_request.head.repo.full_name == github.repository\n"
        "    runs-on: [self-hosted, Linux, X64, render-linux]\n"
        "    steps:\n      - run: true\n"
    ),
    # R1 FAIL — hosted, unregistered.
    "r1.yml": (
        "name: r1\n"
        "on:\n  workflow_dispatch:\n"
        "jobs:\n  stray:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
    ),
    # R2 FAIL — self-hosted in a PR workflow with no same-repo guard.
    "r2.yml": (
        "name: r2\n"
        "on:\n  pull_request:\n"
        "jobs:\n  unguarded:\n    runs-on: [self-hosted, render-linux]\n"
        "    steps:\n      - run: true\n"
    ),
    # R3 FAIL — pull_request_target, no override exists.
    "r3.yml": (
        "name: r3\n"
        "on:\n  pull_request_target:\n"
        "jobs:\n  risky:\n    runs-on: [self-hosted, render-linux]\n"
        "    if: github.event.pull_request.head.repo.full_name == github.repository\n"
        "    steps:\n      - run: true\n"
    ),
}


def _quiet_check(wf_dir: Path, registry: Path, root: Path) -> tuple[int, str]:
    """Run one fixture case with its output captured.

    The cases below deliberately FAIL, and a guard whose selftest prints six
    real-looking FAIL blocks into a green Actions log trains readers to ignore
    the word. Captured output is replayed only for a case that misbehaves.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = run_check(wf_dir, registry, root, emit=False)
    return code, buffer.getvalue()


def _write_fixtures(tmp: Path, names: list[str]) -> tuple[Path, Path]:
    wf_dir = tmp / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (wf_dir / name).write_text(SELFTEST_WORKFLOWS[name])
    registry = tmp / ".github" / "runner-policy.yml"
    registry.write_text(SELFTEST_REGISTRY)
    return wf_dir, registry


def selftest() -> int:
    """Synthetic fixtures only — the real tree is never read.

    Each case is a MUTATION of the passing shape, so a guard that stopped
    detecting anything cannot read green here. Annotations are suppressed
    (``emit=False``) so the deliberate failures below do not decorate a real
    Actions run with red annotations that describe fixtures.
    """
    cases: list[tuple[str, list[str], int]] = [
        ("registered hosted job passes", ["registered.yml"], 0),
        ("ci-pack-shaped dynamic expression passes", ["dynamic.yml"], 0),
        ("if:-guarded self-hosted fence passes", ["guarded.yml"], 0),
        ("R1 unregistered hosted job fails", ["r1.yml"], 1),
        ("R2 unguarded self-hosted PR job fails", ["r2.yml"], 1),
        ("R3 pull_request_target fails", ["r3.yml"], 1),
    ]
    failures = 0
    for label, names, want in cases:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            wf_dir, registry = _write_fixtures(tmp, names)
            got, output = _quiet_check(wf_dir, registry, tmp)
        if got != want:
            print(f"SELFTEST FAIL: {label} — expected exit {want}, got {got}\n{output}")
            failures += 1

    # R3 must not be satisfiable by a registry entry. Prove it by registering the
    # offending job and requiring the failure to persist.
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        wf_dir, registry = _write_fixtures(tmp, ["r3.yml"])
        registry.write_text(
            SELFTEST_REGISTRY
            + "  - workflow: .github/workflows/r3.yml\n"
            "    job: risky\n"
            "    class: recovery\n"
            "    reason: an entry must NOT excuse pull_request_target\n"
        )
        got, output = _quiet_check(wf_dir, registry, tmp)
        if got != 1:
            print(f"SELFTEST FAIL: a registry entry excused pull_request_target (R3)\n{output}")
            failures += 1

    # A flipped default must fail even when every job is registered.
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        wf_dir, registry = _write_fixtures(tmp, ["registered.yml"])
        registry.write_text(SELFTEST_REGISTRY.replace("default: self-hosted", "default: hosted"))
        got, output = _quiet_check(wf_dir, registry, tmp)
        if got != 1:
            print(f"SELFTEST FAIL: a non-self-hosted registry default was accepted\n{output}")
            failures += 1

    if failures:
        print(f"SELFTEST FAIL: {failures} case(s).")
        return 1
    print("SELFTEST OK: 8 cases (3 pass shapes, R1/R2/R3 mutations, R3 non-override, default pin).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--workflows-dir", default=None)
    parser.add_argument("--registry", default=None)
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    root = Path(__file__).resolve().parents[1]
    workflows_dir = Path(args.workflows_dir) if args.workflows_dir else root / DEFAULT_WORKFLOWS_DIR
    registry_path = Path(args.registry) if args.registry else root / DEFAULT_REGISTRY
    base = root
    if args.workflows_dir:
        # An override points at a fixture tree; report paths relative to ITS root
        # (…/.github/workflows -> two parents up) so messages stay readable.
        base = workflows_dir.resolve().parents[1]
    return run_check(workflows_dir, registry_path, base)


if __name__ == "__main__":
    raise SystemExit(main())
