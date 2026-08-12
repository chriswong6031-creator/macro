"""Runner-routing policy: trusted CI self-hosted, untrusted heads never.

Operator charter 2026-08-12. Two different things are pinned here and they fail
for different reasons:

  * BEHAVIOUR of scripts/check_runner_policy.py — proven by mutation. Each
    negative fixture is a passing tree with exactly one property broken, so a
    guard that quietly stopped resolving `runs-on` (or stopped reading the
    registry at all) cannot read green.
  * The ROUTING ITSELF — the exact ci-pack expression, the fork fallbacks, the
    merge-control sweeper, and the absence of `pull_request_target`. These are
    what an unrelated edit is most likely to erode, and they are cheap to state
    exactly. A guard is not a substitute for pinning the answer: the guard would
    happily accept ci-pack going fully hosted again, provided someone added a
    registry entry for it.

The one property NOT provable from this repository is the security outcome on
GitHub's side (fork-PR approval policy, runner group scoping). Those are
operator settings verified live 2026-08-12 and recorded in
research/CI_SELFHOSTED_MIGRATION_WAVE1.md §1.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "check_runner_policy.py"
REGISTRY = ROOT / ".github" / "runner-policy.yml"
WORKFLOWS = ROOT / ".github" / "workflows"

# The exact ci-pack routing expression. Redefined here rather than imported from
# tests/test_ci_pack.py on purpose: importing one test module into another makes
# a collection error in either one silently take out both, and both files must
# pin this literal against the live workflow anyway — so a drift reds twice,
# which is the intended noise.
CI_PACK_RUNS_ON = (
    "${{ (github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name != github.repository) && "
    "'ubuntu-latest' || inputs.runner_pool == 'hosted' && 'ubuntu-latest' || "
    "fromJSON('[\"self-hosted\",\"Linux\",\"X64\",\"render-linux\"]') }}"
)

SELF_HOSTED_CI_POOL = ["self-hosted", "Linux", "X64", "render-linux"]
MERGE_CONTROL_POOL = ["self-hosted", "macOS", "ARM64", "merge-control"]


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


# ── the guard's own behaviour ────────────────────────────────────────────────

def test_guard_selftest_passes() -> None:
    result = _run("--selftest")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SELFTEST OK" in result.stdout


def test_live_tree_satisfies_the_policy() -> None:
    """Every hosted-resolvable job in this repository is registered."""
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr


def _fixture_tree(tmp_path: Path, workflows: dict[str, str], registry: str) -> tuple[str, str]:
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    for name, text in workflows.items():
        (wf_dir / name).write_text(text)
    reg = tmp_path / ".github" / "runner-policy.yml"
    reg.write_text(registry)
    return str(wf_dir), str(reg)


BASE_REGISTRY = """\
schema: runner_policy.v1
default: self-hosted
hosted_labels:
  - ubuntu-latest
hosted_exceptions: []
"""

HOSTED_JOB = (
    "on:\n  workflow_dispatch:\n"
    "jobs:\n  orchestrate:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
)


def test_unregistered_hosted_job_fails(tmp_path: Path) -> None:
    wf_dir, reg = _fixture_tree(tmp_path, {"stray.yml": HOSTED_JOB}, BASE_REGISTRY)
    result = _run("--workflows-dir", wf_dir, "--registry", reg)
    assert result.returncode == 1
    assert "R1" in result.stdout
    assert "orchestrate" in result.stdout


def test_registering_that_same_job_makes_it_pass(tmp_path: Path) -> None:
    """The negative above must fail for the REGISTRY reason, not incidentally."""
    registry = BASE_REGISTRY.replace(
        "hosted_exceptions: []",
        "hosted_exceptions:\n"
        "  - workflow: .github/workflows/stray.yml\n"
        "    job: orchestrate\n"
        "    class: cheap-orchestration\n"
        "    reason: fixture\n",
    )
    wf_dir, reg = _fixture_tree(tmp_path, {"stray.yml": HOSTED_JOB}, registry)
    result = _run("--workflows-dir", wf_dir, "--registry", reg)
    assert result.returncode == 0, result.stdout + result.stderr


def test_self_hosted_pr_job_without_same_repo_guard_fails(tmp_path: Path) -> None:
    unguarded = (
        "on:\n  pull_request:\n"
        "jobs:\n  packs:\n    runs-on: [self-hosted, Linux, X64, render-linux]\n"
        "    steps:\n      - run: true\n"
    )
    wf_dir, reg = _fixture_tree(tmp_path, {"leak.yml": unguarded}, BASE_REGISTRY)
    result = _run("--workflows-dir", wf_dir, "--registry", reg)
    assert result.returncode == 1
    assert "R2" in result.stdout

    # Same tree, same-repo guard added to the job `if:` — must pass.
    guarded = unguarded.replace(
        "  packs:\n",
        "  packs:\n"
        "    if: github.event.pull_request.head.repo.full_name == github.repository\n",
    )
    wf_dir, reg = _fixture_tree(tmp_path / "guarded", {"leak.yml": guarded}, BASE_REGISTRY)
    assert _run("--workflows-dir", wf_dir, "--registry", reg).returncode == 0


def test_pull_request_target_fails_and_cannot_be_registered(tmp_path: Path) -> None:
    risky = (
        "on:\n  pull_request_target:\n"
        "jobs:\n  risky:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
    )
    registry = BASE_REGISTRY.replace(
        "hosted_exceptions: []",
        "hosted_exceptions:\n"
        "  - workflow: .github/workflows/prt.yml\n"
        "    job: risky\n"
        "    class: recovery\n"
        "    reason: an entry must not excuse pull_request_target\n",
    )
    wf_dir, reg = _fixture_tree(tmp_path, {"prt.yml": risky}, registry)
    result = _run("--workflows-dir", wf_dir, "--registry", reg)
    assert result.returncode == 1
    assert "R3" in result.stdout


def test_opaque_runs_on_expression_needs_an_entry(tmp_path: Path) -> None:
    """`${{ inputs.runner || 'render-linux' }}` names no hosted label and no
    `self-hosted` literal, so it is undecidable — and undecidable must fail
    closed rather than be assumed self-hosted."""
    opaque = (
        "on:\n  workflow_dispatch:\n"
        "jobs:\n  render:\n"
        "    runs-on: ${{ github.event.inputs.runner || 'render-linux' }}\n"
        "    steps:\n      - run: true\n"
    )
    wf_dir, reg = _fixture_tree(tmp_path, {"opaque.yml": opaque}, BASE_REGISTRY)
    result = _run("--workflows-dir", wf_dir, "--registry", reg)
    assert result.returncode == 1
    assert "OPAQUE" in result.stdout


# ── the routing itself ───────────────────────────────────────────────────────

def test_ci_pack_carries_the_exact_trusted_routing_expression() -> None:
    pack = _yaml(WORKFLOWS / "ci.yml")["jobs"]["ci-pack"]
    assert pack["runs-on"] == CI_PACK_RUNS_ON, (
        "the ci-pack routing expression is the whole Wave-1 security boundary in "
        "YAML form; changing it is an operator decision, not an edit"
    )
    # Semantic halves, so a reformat that keeps the string equal but loses a
    # branch still reds on something readable.
    assert (
        "github.event.pull_request.head.repo.full_name != github.repository"
        in pack["runs-on"]
    )
    assert "fromJSON('[\"self-hosted\",\"Linux\",\"X64\",\"render-linux\"]')" in pack["runs-on"]
    assert pack["runs-on"].count("'ubuntu-latest'") == 2


def test_fence_pack_is_self_hosted_and_fork_fallbacks_are_not() -> None:
    fences = _yaml(WORKFLOWS / "fences.yml")
    assert fences["jobs"]["fence-pack"]["runs-on"] == SELF_HOSTED_CI_POOL
    for job_id in ("fork-self-mod-fence", "fork-capability-broker", "fork-grader-manifest"):
        job = fences["jobs"][job_id]
        assert job["runs-on"] == "ubuntu-latest", (
            f"{job_id} takes the UNTRUSTED head — it must never resolve to the "
            f"persistent home fleet"
        )
        assert "head.repo.full_name != github.repository" in job["if"]


def test_merge_on_green_keeps_its_dedicated_control_runner() -> None:
    """The sweeper is deliberately NOT co-resident with the CI packs.

    2026-08-09's starvation (main's four packs took the whole render-linux pool
    and the sweeper with it) is the reason max-parallel exists on ci-pack again;
    it stays survivable only while the sweeper lives somewhere else.
    """
    sweep = _yaml(WORKFLOWS / "merge-on-green.yml")["jobs"]["sweep"]
    assert sweep["runs-on"] == MERGE_CONTROL_POOL


def test_no_workflow_uses_pull_request_target() -> None:
    offenders = []
    for path in sorted(WORKFLOWS.iterdir()):
        if path.suffix not in (".yml", ".yaml"):
            continue
        doc = yaml.safe_load(path.read_text())
        if not isinstance(doc, dict):
            continue
        triggers = doc.get("on", doc.get(True))
        names = triggers if isinstance(triggers, (dict, list)) else [triggers]
        if any("pull_request_target" in str(name) for name in names):
            offenders.append(path.name)
    assert offenders == [], (
        f"pull_request_target runs a contributor-controlled head with a writable "
        f"base-repo token; with persistent self-hosted runners on a PUBLIC repo it "
        f"is unconditionally forbidden: {offenders}"
    )


def test_registry_shape_is_intact() -> None:
    registry = _yaml(REGISTRY)
    assert registry["default"] == "self-hosted"
    assert "ubuntu-latest" in registry["hosted_labels"]
    classes = {"fork-fallback", "recovery", "cheap-orchestration", "pending-migration"}
    for entry in registry["hosted_exceptions"]:
        assert set(entry) >= {"workflow", "job", "class", "reason"}
        assert entry["class"] in classes, entry
        assert (ROOT / entry["workflow"]).exists(), entry
    # The Wave-2 worklist must exist and be visible; an empty pending-migration
    # list would mean either the migration finished (it has not) or someone
    # reclassified the debt as justification.
    pending = [e for e in registry["hosted_exceptions"] if e["class"] == "pending-migration"]
    assert len(pending) >= 40, "Wave-2 debt list looks truncated"


@pytest.mark.parametrize(
    "job_id", ["ci-plan", "ci-gate"],
)
def test_cheap_orchestration_jobs_stay_hosted_and_registered(job_id: str) -> None:
    """Wave 1 leaves the serial head/tail hosted ON PURPOSE — but only as a
    REGISTERED exception, so it shows up on the Wave-2 worklist instead of
    quietly becoming the new normal."""
    assert _yaml(WORKFLOWS / "ci.yml")["jobs"][job_id]["runs-on"] == "ubuntu-latest"
    entries = [
        e
        for e in _yaml(REGISTRY)["hosted_exceptions"]
        if e["workflow"] == ".github/workflows/ci.yml" and e["job"] == job_id
    ]
    assert entries, f"{job_id} is hosted but unregistered"
    assert all(e["class"] == "cheap-orchestration" for e in entries)
