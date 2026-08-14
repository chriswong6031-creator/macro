"""Wave B workflow structure: `ci-plan` plans once, `ci-pack` executes it, `ci-gate` adjudicates.

WHAT CHANGED AND WHY THIS SUITE EXISTS.  Until 2026-08-11 `ci.yml` carried one job
with a literal `matrix: pack: [0..11]`, and all twelve packs re-derived the same
selection independently.  The matrix and an identity-bound plan artifact are now
emitted by a new `ci-plan` job and consumed verbatim by each pack, which means two
properties that used to be structurally impossible are now merely
conventional — and a convention in a 4,000-line YAML file is not a guard:

  * A PR may publish a SUBSET of `ci-pack-0..11`, so "all twelve are green" is no
    longer a question anything downstream can ask.  `ci-gate` is the one name that
    concludes on every non-closed event, and `scripts/merge_on_green.py` requires an
    AFFIRMATIVE success on the head — absence of red is not a pass (#4779).  Delete
    `ci-gate`, or let its no-work branch rot, and a proven-no-work PR reads
    `unproven` and never merges.  Nothing about that failure is visible in a diff.
  * The plan is computed from a diff, so WHICH commit it diffs against is now
    load-bearing.  `github.event.pull_request.base.sha` is immutable; every branch
    NAME (`github.head_ref`, `github.base_ref`, `github.ref_name`) resolves at run
    time, so main moving under a long-running PR would silently change what was
    selected while the packs kept verifying a plan hash for a diff nobody reviewed.
    Swapping one for the other is a one-token edit that stays green forever.

The `ci-gate` tests EXECUTE the adjudication script under `bash` rather than reading
it, because the whole point of that job is its exit code.  A test that only greps for
the string `exit 1` passes just as happily when the branch above it returns early.

Run: python3 -m pytest tests/test_ci_plan_workflow.py -q
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

PACK_COUNT = 12
IMMUTABLE_BASE = "github.event.pull_request.base.sha"
IMMUTABLE_MERGE_GROUP_BASE = "github.event.merge_group.base_sha"
# Every one of these resolves to a moving branch tip at run time.  They are the
# plausible-looking substitutions for the immutable base SHA above, which is exactly
# what makes them dangerous: the workflow keeps running and the plan quietly drifts.
MUTABLE_REFS = ("github.head_ref", "github.base_ref", "github.ref_name", "github.ref")


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _job(name: str) -> dict[str, Any]:
    jobs = _workflow()["jobs"]
    assert name in jobs, f"ci.yml declares no `{name}` job (jobs: {sorted(jobs)})"
    return jobs[name]


def _step_running(job: dict[str, Any], needle: str) -> dict[str, Any]:
    """The one step in `job` whose `run:` scalar mentions `needle`."""
    matches = [s for s in job["steps"] if needle in str(s.get("run", ""))]
    assert len(matches) == 1, f"expected exactly one step running {needle!r}, got {len(matches)}"
    return matches[0]


def _plan_step() -> dict[str, Any]:
    return _step_running(_job("ci-plan"), "--plan-only")


def _pack_step() -> dict[str, Any]:
    return _step_running(_job("ci-pack"), "--consume-plan-json")


def _fallback_pack_step() -> dict[str, Any]:
    return _step_running(_job("ci-pack"), "--pack-count 12")


def _preflight_step() -> dict[str, Any]:
    return _step_running(_job("ci-plan"), "ci_structural_preflight.py")


def _scope_index_step() -> dict[str, Any]:
    return _step_running(_job("ci-plan"), "ci_committed_scope_index.py verify")


def _step_using(job: dict[str, Any], action: str) -> dict[str, Any]:
    matches = [step for step in job["steps"] if str(step.get("uses", "")).startswith(action)]
    assert len(matches) == 1, f"expected exactly one {action!r} step, got {len(matches)}"
    return matches[0]


def _gate_script() -> str:
    matches = [
        step for step in _job("ci-gate")["steps"]
        if step.get("name") == "adjudicate CI result"
    ]
    assert len(matches) == 1, f"ci-gate must have one adjudication step, found {len(matches)}"
    return str(matches[0]["run"])


def _run_gate(
    *, plan: str, pack: str, has_work: str, summary: str = "success"
) -> subprocess.CompletedProcess[str]:
    """Execute ci-gate's adjudication script with the `needs` context it would see."""
    return subprocess.run(
        ["bash", "-c", _gate_script()],
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PLAN_RESULT": plan,
            "PACK_RESULT": pack,
            "SUMMARY_RESULT": summary,
            "HAS_WORK": has_work,
            "PLAN_REASON": "pinned by tests/test_ci_plan_workflow.py",
        },
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )


# ─── ci-plan ────────────────────────────────────────────────────────────────────


def test_ci_plan_job_exists_and_publishes_all_required_outputs() -> None:
    """`ci-pack` and `ci-gate` read these outputs by name.

    Drop or rename one and the consumer expression silently evaluates to the empty
    string: `matrix` breaks `fromJSON` outright, but `has_work` empty means the pack
    gate is never `'true'` so the ENTIRE matrix is skipped on every PR, and
    `plan_sha` empty prevents a pack from validating the artifact. Two of those
    three failures can otherwise look green. `changed_files` remains a durable
    diagnostic receipt even though packs no longer re-plan from it.
    """
    job = _job("ci-plan")
    assert job["outputs"] == {
        "matrix": "${{ steps.plan.outputs.matrix }}",
        "has_work": "${{ steps.plan.outputs.has_work }}",
        "plan_sha": "${{ steps.plan.outputs.plan_sha }}",
        "reason": "${{ steps.plan.outputs.reason }}",
        "changed_files": "${{ steps.plan.outputs.changed_files }}",
        "plan_artifact_name": "${{ steps.plan_artifact.outputs.name }}",
    }


def test_ci_plan_is_fenced_against_closed_events() -> None:
    """A closed PR needs only the workflow-level concurrency side effect.

    Without the fence a merged-close event would allocate a planning runner whose
    only product is a check nobody reads, and — worse — `ci-gate` is fenced the same
    way, so the two conditions must agree or a close publishes half the graph.
    """
    assert _job("ci-plan")["if"] == "github.event.action != 'closed'"


def test_ci_plan_uses_an_exact_blobless_sparse_checkout() -> None:
    """Planner metadata must not materialize the repository's four-gigabyte tree."""
    job = _job("ci-plan")
    assert not any(
        str(step.get("uses", "")).startswith("actions/checkout@")
        for step in job["steps"]
    ), "actions/checkout filter overrides sparse patterns and would expand the tree"
    checkout = next(
        step for step in job["steps"]
        if step.get("name") == "metadata-only sparse checkout of the immutable event"
    )
    run = checkout["run"]
    assert "git sparse-checkout set .github scripts" in run
    assert '--filter=blob:none --depth=2 origin "$GITHUB_REF"' in run
    assert 'fetched_sha="$(git rev-parse FETCH_HEAD)"' in run
    assert '"$fetched_sha" != "$GITHUB_SHA"' in run
    assert 'git checkout --detach "$GITHUB_SHA"' in run


def test_ci_plan_caps_dynamic_pr_workers_but_keeps_twelve_as_the_full_suite_ceiling() -> None:
    """Only the planner chooses worker count; main retains the twelve-lane audit."""
    run = _plan_step()["run"]
    assert f"--pack-count {PACK_COUNT}" in run
    assert "--dynamic-pack-count" in run
    assert "--scope-index .github/ci/scope-index.json" in run


def test_ci_pack_admission_is_two_per_pr_four_per_serial_merge_group() -> None:
    admission = str(_job("ci-pack")["strategy"]["max-parallel"])
    assert "github.event_name == 'workflow_dispatch'" in admission
    assert "github.event_name == 'merge_group'" in admission
    assert "&& 12 ||" in admission
    assert "&& 4 || 2" in admission


def test_ci_plan_emits_the_plan_file_and_the_github_outputs() -> None:
    """Planning must be plan-only and publish both independent trust channels.

    `--plan-only` without `--github-output` publishes nothing, so `ci-pack` skips on
    an empty `has_work` and the PR proves nothing. The plan body must go to a file,
    while its SHA travels separately through `$GITHUB_OUTPUT`.
    """
    run = _plan_step()["run"]
    assert "--plan-only" in run
    assert '--github-output "$GITHUB_OUTPUT"' in run
    assert '--emit-plan-json "$RUNNER_TEMP/ci-plan.json"' in run
    assert "--execute" not in run, "the planning job must never execute legacy jobs"

    upload = _step_using(_job("ci-plan"), "actions/upload-artifact@")
    producer = next(
        step for step in _job("ci-plan")["steps"]
        if step.get("id") == "plan_artifact"
    )
    assert "GITHUB_RUN_ID" in producer["run"]
    assert "GITHUB_RUN_ATTEMPT" in producer["run"]
    assert producer["if"] == "steps.plan.outputs.plan_sha != ''"
    assert upload["uses"].endswith("ea165f8d65b6e75b540449e92b4886f43607fa02")
    assert upload["with"]["path"] == "${{ runner.temp }}/ci-plan.json"
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == 7
    assert upload["with"]["name"] == "${{ steps.plan_artifact.outputs.name }}"
    assert upload["if"] == "steps.plan.outputs.plan_sha != ''"
    assert _job("ci-plan")["steps"].index(upload) > _job("ci-plan")["steps"].index(_plan_step())


def test_structural_preflight_runs_before_expensive_plan_and_uses_exact_paths() -> None:
    job = _job("ci-plan")
    steps = job["steps"]
    preflight = _preflight_step()
    assert steps.index(preflight) < steps.index(_plan_step())
    assert '--changed-paths-file "$CI_CHANGED_PATHS_FILE"' in preflight["run"]

    assert not any(
        str(step.get("uses", "")).startswith("actions/github-script@")
        for step in steps
    ), "a live PR-files query can race the event head checked out by this run"

    materialize = next(
        step
        for step in steps
        if step.get("name") == "materialize immutable changed-path decision"
    )
    body = str(materialize["run"])
    assert "CI_CHANGED_FILES_JSON" in body
    assert "PR_BASE_SHA" in materialize["env"]
    assert "MERGE_GROUP_BASE_SHA" in materialize["env"]
    assert body.count("changed_files(base)") == 2


def test_committed_scope_index_is_verified_before_preflight_and_planning() -> None:
    steps = _job("ci-plan")["steps"]
    verify = _scope_index_step()
    assert "--manifest .github/ci/legacy-jobs.yml" in verify["run"]
    assert "--index .github/ci/scope-index.json" in verify["run"]
    assert steps.index(verify) < steps.index(_preflight_step())
    assert steps.index(verify) < steps.index(_plan_step())


def test_ci_plan_scope_arg_uses_the_immutable_pull_request_base_sha() -> None:
    """The diff base must be the immutable base SHA, never a branch name.

    `github.head_ref` / `github.base_ref` resolve to a moving tip: main advances
    under a long-running PR, the selected job set changes without a new commit, and
    the packs keep verifying a plan hash for a diff no reviewer ever saw.  The
    workflow stays green through the whole drift, which is why this is a test and not
    a comment.
    """
    scope_arg = _plan_step()["env"]["CI_SCOPE_ARG"]
    assert IMMUTABLE_BASE in scope_arg
    for mutable in MUTABLE_REFS:
        assert mutable not in scope_arg, f"ci-plan's diff base must not depend on {mutable}"


def test_planner_and_pack_checkouts_are_pinned_to_the_event_sha() -> None:
    planner = next(
        step for step in _job("ci-plan")["steps"]
        if step.get("name") == "metadata-only sparse checkout of the immutable event"
    )
    assert "$GITHUB_SHA" in planner["run"]
    pack_checkout = _step_using(_job("ci-pack"), "actions/checkout@")
    assert pack_checkout["with"]["ref"] == "${{ github.sha }}"


def test_ci_plan_handles_native_merge_group_with_immutable_base_sha() -> None:
    workflow = _workflow()
    triggers = workflow.get("on") or workflow.get(True)
    assert triggers["merge_group"]["types"] == ["checks_requested"]
    planner_base = _plan_step()["env"]["CI_SCOPE_ARG"]
    pack_base = _pack_step()["env"]["PLAN_BASE_SHA_ARG"]
    assert "github.event_name == 'merge_group'" in planner_base
    assert "github.event_name == 'merge_group'" in pack_base
    assert IMMUTABLE_MERGE_GROUP_BASE in planner_base
    assert IMMUTABLE_MERGE_GROUP_BASE in pack_base


def test_workflow_dispatch_passes_no_changed_from_so_main_stays_full_suite() -> None:
    """Main's baseline is the audit backstop and must run the complete manifest.

    `--changed-from` may reach the planner ONLY through `$CI_SCOPE_ARG`, which is
    conditioned on PR/merge-group events and collapses to `''` otherwise. The pack
    similarly omits `--expect-base-sha` on the complete-main plan.
    """
    planner = _plan_step()
    assert "--changed-from" not in planner["run"]
    scope_arg = planner["env"]["CI_SCOPE_ARG"]
    assert "github.event_name == 'pull_request'" in scope_arg
    assert scope_arg.rstrip().endswith("|| '' }}")

    pack = _pack_step()
    assert "--changed-from" not in pack["run"]
    assert "--expect-base-sha" not in pack["run"]
    base_arg = pack["env"]["PLAN_BASE_SHA_ARG"]
    assert "github.event_name == 'pull_request'" in base_arg
    assert base_arg.rstrip().endswith("|| '' }}")


# ─── ci-pack ────────────────────────────────────────────────────────────────────


def test_ci_pack_needs_ci_plan() -> None:
    """Without the dependency the matrix expression has no producer.

    `needs.ci-plan.outputs.matrix` evaluates to empty when `ci-plan` is not a
    declared dependency, `fromJSON` then fails at workflow parse time, and the run
    dies before a single check is published.
    """
    needs = _job("ci-pack")["needs"]
    assert needs == "ci-plan" or needs == ["ci-plan"]


def test_ci_pack_matrix_comes_from_the_plan_and_no_static_pack_list_remains() -> None:
    """The matrix must be the plan's, not a literal — and the two must not coexist.

    A leftover `pack: [0..11]` next to the expression would pin the matrix back to
    twelve while every other part of Wave B behaved as though selection were live:
    the plan would narrow, the packs would not, and the divergence would surface only
    as wasted runners.  This reads the PARSED YAML, so the prose in the surrounding
    comment blocks (which still cites the old literal as history) cannot satisfy it.
    """
    strategy = _job("ci-pack")["strategy"]
    matrix = strategy["matrix"]
    assert isinstance(matrix, str), f"ci-pack's matrix must be an expression, got {type(matrix).__name__}"
    assert "fromJSON(needs.ci-plan.outputs.matrix)" in matrix
    assert strategy["fail-fast"] is False


def test_ci_pack_is_gated_on_an_affirmative_has_work() -> None:
    """The gate must be an explicit `== 'true'`, and the closed fence must survive.

    `has_work` is a STRING output: a truthiness test would treat the literal
    `'false'` as true, and dropping the clause entirely would launch every pack the
    plan proved unnecessary.  Dropping the `!= 'closed'` half instead re-opens the
    2026-07-28 merged-close cancellation class this workflow already paid for once.
    """
    condition = _job("ci-pack")["if"]
    assert "needs.ci-plan.outputs.has_work == 'true'" in condition
    assert "github.event.action != 'closed'" in condition


def test_ci_pack_downloads_and_consumes_the_exact_planner_artifact() -> None:
    """Packs execute assignments; they never infer, diff, or partition again."""
    download = _step_using(_job("ci-pack"), "actions/download-artifact@")
    upload = _step_using(_job("ci-plan"), "actions/upload-artifact@")
    assert download["uses"].endswith("d3f86a106a0bac45b974a628896c90dbdf5c8093")
    assert download["with"]["name"] == "${{ needs.ci-plan.outputs.plan_artifact_name }}"
    assert "github.run_attempt" not in download["with"]["name"]
    assert download["with"]["path"] == "${{ runner.temp }}/ci-pack-plan"
    assert download["if"] == "needs.ci-plan.outputs.plan_sha != ''"
    run = _pack_step()["run"]
    assert '--consume-plan-json "$RUNNER_TEMP/ci-pack-plan/ci-plan.json"' in run
    assert "--pack-count" not in run
    assert "--changed-from" not in run
    assert "--dynamic-pack-count" not in run


def test_ci_pack_pins_plan_sha_head_and_event_base_and_never_runs_unpinned() -> None:
    """Every consumed artifact is bound to independent immutable identities."""
    env = _pack_step()["env"]
    assert env["EXPECTED_PLAN_SHA"] == "${{ needs.ci-plan.outputs.plan_sha }}"
    run = _pack_step()["run"]
    assert '--expect-plan-sha "$EXPECTED_PLAN_SHA"' in run
    assert '--expect-head-sha "$GITHUB_SHA"' in run
    assert "$PLAN_BASE_SHA_ARG" in run
    assert "CI_CHANGED_FILES_JSON" not in env
    assert "CI_SCOPE_ARG" not in env


def test_ci_pack_falls_back_explicitly_to_full_suite_when_planning_cannot_publish() -> None:
    fallback = _fallback_pack_step()
    assert fallback["if"] == "needs.ci-plan.outputs.plan_sha == ''"
    run = fallback["run"]
    assert "--pack-count 12" in run
    assert "--consume-plan-json" not in run
    assert "--changed-from" not in run
    assert "--expect-plan-sha" not in run
    assert "--execute" in run


def test_pack_shell_arguments_stay_unquoted_so_an_empty_value_disappears() -> None:
    """Quoting either env-built argument turns "absent" into an empty positional word.

    `"$CI_SCOPE_ARG"` on a workflow_dispatch would hand `run_ci_pack.py` an empty
    string as a positional argument instead of handing it nothing — argparse then
    errors, and main's baseline (the audit backstop) dies before it plans.
    """
    for job_name, step, variable in (
        ("ci-plan", _plan_step(), "$CI_SCOPE_ARG"),
        ("ci-pack", _pack_step(), "$PLAN_BASE_SHA_ARG"),
    ):
        run = step["run"]
        assert f'"{variable}"' not in run, f"{job_name} quotes {variable}; it must vanish when empty"
        assert f"'{variable}'" not in run, f"{job_name} quotes {variable}; it must vanish when empty"


def test_plan_command_folds_but_pack_execution_is_pipefail_logged() -> None:
    """The two folded-scalar traps this repo has already been bitten by.

    A `#` inside a `run: >-` scalar deletes the rest of the command, and a
    continuation line at a DIFFERENT indent keeps its newline instead of folding to a
    space — which once split one command into two and ran `--execute` as its own
    shell line.  Both produce a workflow that parses cleanly and does the wrong
    thing, so the only detector is the folded RESULT: exactly one line, no `#`.
    """
    plan = str(_plan_step()["run"]).strip()
    assert "\n" not in plan, f"ci-plan's command did not fold to one line: {plan!r}"
    assert "#" not in plan, "ci-plan's folded command contains a `#`, which truncates it"

    for job_name, step in (
        ("ci-pack", _pack_step()),
        ("ci-pack fallback", _fallback_pack_step()),
    ):
        run = str(step["run"])
        assert "set -euo pipefail" in run
        assert '2>&1 | tee "$RUNNER_TEMP/ci-pack.log"' in run


def test_ci_pack_publishes_one_strict_terminal_record_per_matrix_child() -> None:
    job = _job("ci-pack")
    collect = next(
        step for step in job["steps"]
        if step.get("name") == "materialize this pack's terminal evidence"
    )
    publish = next(
        step for step in job["steps"]
        if step.get("name") == "publish this pack's terminal evidence"
    )
    assert collect["if"] == "always()"
    assert collect["env"]["PACK_OUTCOME"] == "${{ job.status }}"
    assert "ci_collect_pack_evidence.py pack" in collect["run"]
    assert '--log "$RUNNER_TEMP/ci-pack.log"' in collect["run"]
    assert publish["if"] == "always()"
    assert publish["uses"].endswith("ea165f8d65b6e75b540449e92b4886f43607fa02")
    assert publish["with"]["name"] == "ci-pack-evidence-${{ github.run_id }}-${{ matrix.pack }}"
    assert publish["with"]["overwrite"] is True
    assert publish["with"]["retention-days"] == 7


def test_ci_pack_reuses_only_pip_downloads_under_a_manifest_bound_key() -> None:
    """Download reuse is safe; mutable cross-job virtualenv reuse is not."""
    cache = next(
        step for step in _job("ci-pack")["steps"]
        if step.get("name") == "restore deterministic pip download cache"
    )
    assert cache["uses"] == "actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830"
    assert cache["with"]["path"] == "~/.cache/pip"
    assert "hashFiles('.github/ci/legacy-jobs.yml')" in cache["with"]["key"]
    assert cache["with"]["restore-keys"].strip().endswith("-py312-ci-pack-pip-")


# ─── ci-gate ────────────────────────────────────────────────────────────────────


def test_ci_gate_exists_needs_both_jobs_and_always_runs() -> None:
    """`ci-gate` is the only check name that concludes on every non-closed event.

    It must depend on BOTH jobs (a `needs` on `ci-plan` alone would let it conclude
    green while packs were still running) and it must be `always()`, because the
    situation it exists for — a skipped or failed `ci-pack` — is precisely the one
    where a default-conditioned job would not run at all and publish nothing.
    """
    job = _job("ci-gate")
    assert sorted(job["needs"]) == ["ci-pack", "ci-plan"]
    assert job["if"].startswith("always()")


def test_ci_gate_assembles_and_publishes_machine_readable_failure_evidence() -> None:
    job = _job("ci-gate")
    download = next(
        step for step in job["steps"]
        if step.get("name") == "download terminal pack evidence"
    )
    classify = next(step for step in job["steps"] if step.get("id") == "failure_summary")
    publish = next(
        step for step in job["steps"]
        if step.get("name") == "publish machine-readable CI outcome"
    )
    assert download["uses"].endswith("d3f86a106a0bac45b974a628896c90dbdf5c8093")
    assert download["continue-on-error"] is True
    assert download["with"]["pattern"] == "ci-pack-evidence-${{ github.run_id }}-*"
    assert download["with"]["merge-multiple"] is True
    assert "ci_collect_pack_evidence.py run" in classify["run"]
    assert "ci_failure_summary.py" in classify["run"]
    assert "needs.ci-plan.result == 'success'" in classify["env"]["EXPECTED_MATRIX_JSON"]
    assert '{"include":[]}' in classify["env"]["EXPECTED_MATRIX_JSON"]
    assert publish["uses"].endswith("ea165f8d65b6e75b540449e92b4886f43607fa02")
    assert publish["with"]["overwrite"] is True
    assert publish["with"]["retention-days"] == 7


def test_ci_gate_fails_when_failure_evidence_cannot_be_classified() -> None:
    proc = _run_gate(
        plan="success", pack="success", has_work="true", summary="failure"
    )
    assert proc.returncode == 1
    assert "failure evidence could not be classified" in proc.stdout


def test_ci_gate_is_fenced_against_closed_events() -> None:
    """`always()` alone would publish a RED `ci-gate` on every merged close.

    On a `closed` event `ci-plan` is fenced off and therefore SKIPPED, so
    `PLAN_RESULT` is `skipped`, the first branch exits 1, and every merged PR in the
    repository carries a red aggregate — which would block the merge-on-green
    sweeper fleet-wide.  The fence is load-bearing, not symmetry.
    """
    assert _job("ci-gate")["if"] == "always() && github.event.action != 'closed'"
    assert _run_gate(plan="skipped", pack="skipped", has_work="").returncode == 1, (
        "a skipped plan must be treated as failure — which is exactly why the fence is required"
    )


def test_ci_gate_fails_when_planning_did_not_succeed() -> None:
    """No plan means no proof, in every non-success shape.

    `failure` is obvious; `skipped` and `cancelled` are the ones that matter, because
    a naive `= "failure"` comparison passes them and publishes a green aggregate for
    a run in which nothing whatsoever was decided.
    """
    for result in ("failure", "skipped", "cancelled"):
        proc = _run_gate(plan=result, pack="success", has_work="true")
        assert proc.returncode == 1, f"ci-gate accepted plan result {result!r}"
        assert "::error title=ci-gate::" in proc.stdout


def test_ci_gate_passes_on_a_proven_no_work_plan() -> None:
    """A proven-no-work PR must publish an AFFIRMATIVE success, or it never merges.

    `scripts/merge_on_green.py:decide_verdict` requires a real success on the head —
    absence of red is not a pass (#4779).  With `ci-pack` skipped, `ci-gate` is the
    only check that can supply one.  Delete this branch (or the whole job) and every
    no-work PR reads `unproven` and sits armed forever.
    """
    proc = _run_gate(plan="success", pack="skipped", has_work="false")
    assert proc.returncode == 0, f"ci-gate refused a proven no-work plan: {proc.stdout}\n{proc.stderr}"
    assert "::notice title=ci-gate::" in proc.stdout


def test_ci_gate_no_work_shortcut_is_unreachable_without_a_successful_plan() -> None:
    """`has_work=false` may only be believed when the planner actually concluded.

    Reorder the branches so the no-work check runs first and a CRASHED planner —
    whose `has_work` output is the empty string, not `false` — is one typo away from
    exiting 0 on a run that tested nothing.  Ordering is the invariant; this pins it.
    """
    for result in ("failure", "skipped", "cancelled"):
        assert _run_gate(plan=result, pack="skipped", has_work="false").returncode == 1


def test_ci_gate_fails_when_a_selected_pack_did_not_succeed() -> None:
    """When the plan says there IS work, the packs' verdict is the gate's verdict.

    Every non-success shape must red: `failure` for a genuine break, and
    `skipped`/`cancelled` because a matrix that never ran proves nothing — treating
    either as a pass reproduces #4779 inside the aggregate that exists to prevent it.

    `cancelled` is a workflow cancel (new SHA), not fail-fast wiping siblings:
    the pack matrix is `fail-fast: false` so one red pack cannot destroy the
    other eleven proofs. ci-gate still must not pass a cancelled matrix.
    """
    for result in ("failure", "cancelled", "skipped"):
        proc = _run_gate(plan="success", pack=result, has_work="true")
        assert proc.returncode == 1, f"ci-gate accepted pack result {result!r} on a work-bearing plan"
        assert "::error title=ci-gate::" in proc.stdout


def test_ci_gate_passes_when_the_selected_packs_all_succeeded() -> None:
    """The green path, so the tests above cannot be satisfied by a gate that always fails.

    An adjudicator that reds unconditionally would pass every negative test in this
    file and block every PR in the repository.
    """
    proc = _run_gate(plan="success", pack="success", has_work="true")
    assert proc.returncode == 0, f"ci-gate refused a fully green run: {proc.stdout}\n{proc.stderr}"
