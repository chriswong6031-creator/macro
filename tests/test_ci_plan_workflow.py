"""Wave B workflow structure: `ci-plan` plans once, `ci-pack` executes it, `ci-gate` adjudicates.

WHAT CHANGED AND WHY THIS SUITE EXISTS.  Until 2026-08-11 `ci.yml` carried one job
with a literal `matrix: pack: [0..11]`, and all twelve packs re-derived the same
selection independently.  The matrix is now emitted by a new `ci-plan` job, which
means two properties that used to be structurally impossible are now merely
conventional — and a convention in a 4,000-line YAML file is not a guard:

  * A PR may publish a SUBSET of `ci-pack-0..11`, so "all twelve are green" is no
    longer a question anything downstream can ask.  `ci-gate` is the one name that
    concludes on every proof-producing event, and `scripts/merge_on_green.py` requires an
    AFFIRMATIVE success on the head — absence of red is not a pass (#4779).  Delete
    `ci-gate`, or let its no-work branch rot, and a proven-no-work PR reads
    `unproven` and never merges.  Nothing about that failure is visible in a diff.
  * The plan is computed from a diff, so WHICH commit it diffs against is now
    load-bearing. The tested base is parent 1 of the exact synthetic merge commit;
    parent 2 must equal the signed event head. Every branch NAME
    (`github.head_ref`, `github.base_ref`, `github.ref_name`) resolves at run time,
    while event base metadata can be stale by runner pickup. Substituting either
    would let the plan describe a different diff than the tested merge tree.

The `ci-gate` tests EXECUTE the adjudication script under `bash` rather than reading
it, because the whole point of that job is its exit code.  A test that only greps for
the string `exit 1` passes just as happily when the branch above it returns early.

Run: python3 -m pytest tests/test_ci_plan_workflow.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

PACK_COUNT = 12
IMMUTABLE_BASE = "steps.identity.outputs.tested_base_sha"
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
    matches = [step for step in _job("ci-pack")["steps"] if step.get("id") == "execute_semantic_pack"]
    assert len(matches) == 1
    return matches[0]


def _gate_step(name: str) -> dict[str, Any]:
    matches = [step for step in _job("ci-gate")["steps"] if step.get("name") == name]
    assert len(matches) == 1, f"expected one ci-gate step named {name!r}"
    return matches[0]


# ─── ci-plan ────────────────────────────────────────────────────────────────────


def test_ci_plan_job_exists_and_publishes_bounded_identity_outputs() -> None:
    """`ci-pack` and `ci-gate` read these outputs by name.

    Drop or rename one and the consumer expression silently evaluates to the empty
    string: `matrix` breaks `fromJSON` outright, but `has_work` empty means the pack
    gate is never `'true'` so the ENTIRE matrix is skipped on every PR, and
    `plan_sha` empty just unpins the parity check.  Two of those three failures are
    green-looking.

    `changed_files` is NOT among them any more (2026-08-14). Every job output
    becomes an `env:` string in the consuming job, execve caps a single one at
    131,072 bytes on Linux (MAX_ARG_STRLEN), and that list measured 350,264
    bytes on PR #5578 — all twelve packs died at launch with "Argument list too
    long" before running a test (run 31775693780). The list now travels as the
    `ci-changed-files` artifact and only its 64-character digest rides here;
    adding a seventh output that scales with the diff would reopen the hole
    under a new name.
    """
    job = _job("ci-plan")
    assert job["outputs"] == {
        "matrix": "${{ steps.plan.outputs.matrix }}",
        "has_work": "${{ steps.plan.outputs.has_work }}",
        "plan_sha": "${{ steps.plan.outputs.plan_sha }}",
        "reason": "${{ steps.plan.outputs.reason }}",
        "changed_files_sha256": "${{ steps.plan.outputs.changed_files_sha256 }}",
        "changed_files_count": "${{ steps.plan.outputs.changed_files_count }}",
        "plan_artifact_name": "${{ steps.identity.outputs.plan_artifact_name }}",
        "tested_tree_sha": "${{ steps.identity.outputs.tested_tree_sha }}",
        "subject_head_sha": "${{ steps.identity.outputs.subject_head_sha }}",
        "tested_base_sha": "${{ steps.identity.outputs.tested_base_sha }}",
        "semantic_role": "${{ steps.identity.outputs.semantic_role }}",
    }


def test_closed_lifecycle_events_cannot_enter_semantic_ci_concurrency() -> None:
    """Out-of-order close delivery must be unable to replace a live proof slot.

    GitHub replaces the pending member of a concurrency group even when
    cancel-in-progress is false. The correctness boundary is therefore the trigger:
    `closed` must not schedule this workflow at all. Open/sync/reopen remain the only
    PR lifecycle events that can occupy the PR-number group.
    """
    workflow = _workflow()
    triggers = workflow.get("on") or workflow.get(True)
    pull_request = triggers["pull_request"]
    assert pull_request["types"] == ["opened", "synchronize", "reopened"]
    assert "closed" not in pull_request["types"]
    assert workflow["concurrency"] == {
        "group": "ci-${{ github.event.pull_request.number || github.ref }}",
        "cancel-in-progress": "${{ github.event_name != 'workflow_dispatch' }}",
    }
    assert "if" not in _job("ci-plan")


def test_ci_plan_checks_out_full_history_for_the_base_diff() -> None:
    """The planner diffs against synthetic-merge parent 1, which a shallow clone may lack.

    Drop `fetch-depth: 0` and the diff fails, the planner widens to the full suite by
    law (fail-SAFE), and every PR runs everything while the plan still reports
    success.  The regression costs the entire feature and reds nothing.
    """
    checkouts = [s for s in _job("ci-plan")["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert len(checkouts) == 1, f"ci-plan should check out exactly once, found {len(checkouts)}"
    assert checkouts[0]["with"]["fetch-depth"] == 0


def test_ci_plan_sparse_profile_omits_only_the_measured_heavy_trees() -> None:
    """W3 contains working-tree bytes without narrowing unknown future roots.

    The include-all first row is load-bearing: a newly tracked top-level surface
    materializes by default and therefore cannot become selection-dark merely
    because this profile predates it. The four negative rows are the mechanical
    census result; ci-pack's independent full checkout is pinned elsewhere.
    """
    checkout = next(
        step
        for step in _job("ci-plan")["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["sparse-checkout-cone-mode"] is False
    assert checkout["with"]["sparse-checkout"].splitlines() == [
        "/*",
        "!/data/",
        "!/site/",
        "!/mockups/",
        "!/verify_shots/",
    ]


def test_ci_plan_builds_and_consumes_one_bounded_exact_tree_path_handle() -> None:
    """Sparse absence never answers repository absence.

    The path population stays in a runner-temp file, not an output or env value;
    both producer and consumer bind it to the identity step's immutable tree.
    """
    job = _job("ci-plan")
    steps = job["steps"]
    inventory = _step_running(job, "--write-tracked-paths")
    plan = _plan_step()
    handle = "$RUNNER_TEMP/ci-tracked-paths/tracked-paths.v1"
    assert "scripts/ci_scope_dependencies.py" in inventory["run"]
    assert f'--write-tracked-paths "{handle}"' in inventory["run"]
    assert (
        '--tested-tree-sha "${{ steps.identity.outputs.tested_tree_sha }}"'
        in inventory["run"]
    )
    assert f'--tracked-paths-file "{handle}"' in plan["run"]
    assert steps.index(inventory) < steps.index(plan)
    assert all(
        "TRACKED_PATH" not in key
        for step in steps
        for key in step.get("env", {})
    ), "only the bounded file path may cross into the planner command"


def test_ci_plan_passes_pack_count_twelve() -> None:
    """The partition arithmetic is fixed at twelve and must match `ci-pack` exactly.

    A plan built for a different `--pack-count` produces a different partition AND a
    different plan hash, so every pack would refuse on `--expect-plan-sha` — a
    fleet-wide red whose cause is one number in a folded scalar.
    """
    assert f"--pack-count {PACK_COUNT}" in _plan_step()["run"]


def test_ci_plan_emits_the_plan_and_the_github_outputs() -> None:
    """Planning must be plan-ONLY, must write `$GITHUB_OUTPUT`, and must log the plan.

    `--plan-only` without `--github-output` publishes nothing, so `ci-pack` skips on
    an empty `has_work` and the PR proves nothing.  `--emit-plan-json -` is the
    house `KEY=<json>` receipt line: without it a disputed selection cannot be
    reconstructed from the run log after the fact.
    """
    run = _plan_step()["run"]
    assert "--plan-only" in run
    assert '--github-output "$GITHUB_OUTPUT"' in run
    assert '--emit-plan-json "$RUNNER_TEMP/ci-semantic-plan/ci-plan.json"' in run
    for flag in (
        "--workflow-run-id",
        "--workflow-name",
        "--event",
        "--role",
        "--tested-tree-sha",
        "--subject-head-sha",
        "--base-sha",
    ):
        assert flag in run
    assert "--execute" not in run, "the planning job must never execute legacy jobs"


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


def test_workflow_dispatch_passes_no_changed_from_so_main_stays_full_suite() -> None:
    """Main's baseline is the audit backstop and must run the complete manifest.

    `--changed-from` may reach the planner ONLY through `$CI_SCOPE_ARG`, which is
    conditioned on `github.event_name == 'pull_request'` and collapses to `''`
    otherwise.  Hard-code the flag into either run scalar and main's dispatch starts
    selecting — the one run that is supposed to prove everything proves a subset.
    """
    step = _plan_step()
    assert "--changed-from" not in step["run"]
    scope_arg = step["env"]["CI_SCOPE_ARG"]
    assert "github.event_name == 'pull_request'" in scope_arg
    assert scope_arg.rstrip().endswith("|| '' }}")
    assert "CI_SCOPE_ARG" not in _pack_step().get("env", {})
    assert "--changed-from" not in _pack_step()["run"]


def test_workflow_dispatch_can_pin_the_exact_observed_main_sha() -> None:
    """The semantic main producer must not race a moving `main` branch.

    GitHub accepts a branch name for workflow_dispatch, not a commit SHA.  The
    controller therefore sends the observed SHA as an input and the immutable
    checkout refuses if `main` resolved to anything else before the run began.
    """
    workflow = _workflow()
    triggers = workflow.get("on", workflow.get(True))
    dispatch = triggers["workflow_dispatch"]
    assert dispatch["inputs"]["expected_sha"] == {
        "description": "Exact main SHA the semantic baseline request observed",
        "required": False,
        "type": "string",
    }
    identity = next(
        step for step in _job("ci-plan")["steps"] if step.get("id") == "identity"
    )
    assert identity["env"]["EXPECTED_DISPATCH_SHA"] == "${{ inputs.expected_sha || '' }}"
    run = identity["run"]
    assert '"$GITHUB_SHA" != "$EXPECTED_DISPATCH_SHA"' in run
    assert "^[0-9a-f]{40}$" in run


# ─── ci-pack ────────────────────────────────────────────────────────────────────


def test_ci_pack_needs_the_hosted_plan_and_main_owned_trusted_execution() -> None:
    """The matrix needs its planner and same-repo relays need the trusted result.

    `needs.ci-plan.outputs.matrix` evaluates to empty when `ci-plan` is not a
    declared dependency, `fromJSON` then fails at workflow parse time, and the run
    dies before a single check is published.  The `trusted-ci` dependency is what
    prevents a same-repository relay from publishing before the PC pack concludes.
    """
    assert _job("ci-pack")["needs"] == ["ci-plan", "trusted-ci"]


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
    """The gate must be an explicit `== 'true'`.

    `has_work` is a STRING output: a truthiness test would treat the literal
    `'false'` as true, and dropping the clause entirely would launch every pack the
    plan proved unnecessary. Closed events are excluded at the workflow trigger and
    must not be smuggled back as an implicit cancellation mechanism.
    """
    condition = _job("ci-pack")["if"]
    assert condition == (
        "always() && needs.ci-plan.result == 'success' && "
        "needs.ci-plan.outputs.has_work == 'true' && "
        "(github.event.pull_request.head.repo.full_name != github.repository || "
        "needs.trusted-ci.result == 'success')"
    )


def test_ci_pack_passes_pack_count_twelve() -> None:
    """Execution must partition identically to the plan, or `--expect-plan-sha` reds.

    The pack index it receives is meaningless without the same denominator: pack 3
    of 12 and pack 3 of 8 are different job sets drawn from the same manifest.
    """
    assert f"--pack-count {PACK_COUNT}" in _pack_step()["run"]


def test_ci_pack_pins_the_plan_hash_and_unpins_itself_when_there_is_none() -> None:
    """Plan/execution parity is checked when there IS a plan, and never blocks when there is not.

    `--expect-plan-sha` is what catches a pack that would have executed a different
    partition than the one `ci-plan` published.  It has to disappear entirely on the
    planner's fail-safe path (empty `plan_sha`), because a bare `--expect-plan-sha`
    with no value would consume `--execute` as its argument and turn a planning
    hiccup into twelve red packs.
    """
    step = _pack_step()
    fork_guard = "github.event.pull_request.head.repo.full_name != github.repository"
    assert step["if"] == f"{fork_guard} && needs.ci-plan.outputs.plan_sha != ''"
    assert step["env"]["EXPECTED_PLAN_SHA"] == "${{ needs.ci-plan.outputs.plan_sha }}"
    assert '--expect-plan-sha "$EXPECTED_PLAN_SHA"' in step["run"]
    fallback = next(
        item for item in _job("ci-pack")["steps"] if item.get("name") == "fail-safe full suite when no authoritative plan was produced"
    )
    assert fallback["if"] == f"{fork_guard} && needs.ci-plan.outputs.plan_sha == ''"
    assert "--expect-plan-sha" not in fallback["run"]


def test_pack_shell_arguments_stay_unquoted_so_an_empty_value_disappears() -> None:
    """Quoting either env-built argument turns "absent" into an empty positional word.

    `"$CI_SCOPE_ARG"` on a workflow_dispatch would hand `run_ci_pack.py` an empty
    string as a positional argument instead of handing it nothing — argparse then
    errors, and main's baseline (the audit backstop) dies before it plans.
    """
    run = _plan_step()["run"]
    assert '"$CI_SCOPE_ARG"' not in run
    assert "'$CI_SCOPE_ARG'" not in run


def test_folded_pack_commands_fold_to_one_line_and_carry_no_comment_marker() -> None:
    """The two folded-scalar traps this repo has already been bitten by.

    A `#` inside a `run: >-` scalar deletes the rest of the command, and a
    continuation line at a DIFFERENT indent keeps its newline instead of folding to a
    space — which once split one command into two and ran `--execute` as its own
    shell line.  Both produce a workflow that parses cleanly and does the wrong
    thing, so the only detector is the folded RESULT: exactly one line, no `#`.
    """
    run = str(_plan_step()["run"]).strip()
    assert "\n" not in run
    assert "#" not in run
    pack_run = str(_pack_step()["run"])
    assert "set -euo pipefail" in pack_run
    assert "--plan-json" in pack_run and "--emit-semantic-fragment" in pack_run


# ─── ci-gate ────────────────────────────────────────────────────────────────────


def test_ci_gate_exists_needs_both_jobs_and_always_runs() -> None:
    """`ci-gate` is the only check name that concludes on every workflow event.

    It must depend on ci-plan and ci-pack (a `needs` on `ci-plan` alone would let
    it conclude green while packs were still running) and it must be `always()`,
    because the situation it exists for — a skipped or failed `ci-pack` — is
    precisely the one where a default-conditioned job would not run at all and
    publish nothing.

    `contract-delta` (2026-08-19) joined the `needs` list for the same reason:
    its own verdict must be able to fail ci-gate, which GitHub Actions requires
    a `needs` edge for. It does not change the reasoning above — it is fenced to
    `pull_request` events on its own `if:` and reads `skipped` as OK (see
    scripts/check_contract_delta.py and the "enforce contract-delta verdict"
    step below), so it never turns a proven-no-work or non-PR run red.
    """
    job = _job("ci-gate")
    assert sorted(job["needs"]) == ["ci-pack", "ci-plan", "contract-delta"]
    assert job["if"].startswith("always()")


def test_ci_gate_always_runs_for_every_triggered_event() -> None:
    """Lifecycle exclusion belongs to the trigger, not job-level dead branches."""
    assert _job("ci-gate")["if"] == "always()"
    assert _gate_step("reconcile complete semantic evidence")["continue-on-error"] is True


def test_ci_gate_fails_when_planning_did_not_succeed() -> None:
    """No plan means no proof, in every non-success shape.

    `failure` is obvious; `skipped` and `cancelled` are the ones that matter, because
    a naive `= "failure"` comparison passes them and publishes a green aggregate for
    a run in which nothing whatsoever was decided.
    """
    reconcile = _gate_step("reconcile complete semantic evidence")
    assert reconcile["env"]["PLAN_RESULT"] == "${{ needs.ci-plan.result }}"
    assert '--planner-outcome "$PLAN_RESULT"' in reconcile["run"]
    # Identity is bound before planning. If the plan artifact itself is missing
    # or malformed, ci-gate still publishes a structurally valid, provenance-
    # bound failure artifact instead of an unbound JSON tombstone.
    assert reconcile["env"]["FALLBACK_RUN_ID"] == "${{ github.run_id }}"
    assert reconcile["env"]["FALLBACK_ROLE"] == "${{ needs.ci-plan.outputs.semantic_role }}"
    for flag in (
        "--fallback-workflow-run-id",
        "--fallback-workflow",
        "--fallback-event",
        "--fallback-role",
        "--fallback-tested-tree-sha",
        "--fallback-subject-head-sha",
        "--fallback-base-sha",
    ):
        assert flag in reconcile["run"]
    enforce = _gate_step("enforce semantic verdict")
    assert "steps.semantic_reconcile.outcome" in enforce["env"]["RECONCILE_OUTCOME"]
    assert '[ "$RECONCILE_OUTCOME" != "success" ]' in enforce["run"]


def test_ci_gate_passes_on_a_proven_no_work_plan() -> None:
    """A proven-no-work PR must publish an AFFIRMATIVE success, or it never merges.

    `scripts/merge_on_green.py:decide_verdict` requires a real success on the head —
    absence of red is not a pass (#4779).  With `ci-pack` skipped, `ci-gate` is the
    only check that can supply one.  Delete this branch (or the whole job) and every
    no-work PR reads `unproven` and sits armed forever.
    """
    reconcile = _gate_step("reconcile complete semantic evidence")
    assert "HAS_WORK" not in reconcile.get("env", {})
    # Empty expected semantic inventory is reconciled by the same shared law;
    # there is no separate shell shortcut capable of green-lighting a bad plan.
    assert "ci_semantic_proof.py reconcile" in reconcile["run"]


def test_ci_gate_no_work_shortcut_is_unreachable_without_a_successful_plan() -> None:
    """`has_work=false` may only be believed when the planner actually concluded.

    Reorder the branches so the no-work check runs first and a CRASHED planner —
    whose `has_work` output is the empty string, not `false` — is one typo away from
    exiting 0 on a run that tested nothing.  Ordering is the invariant; this pins it.
    """
    text = str(_gate_step("reconcile complete semantic evidence")["run"])
    assert "has_work" not in text.lower()
    assert "--planner-outcome" in text


def test_ci_gate_uses_complete_fragments_not_native_pack_conclusion() -> None:
    """When the plan says there IS work, the packs' verdict is the gate's verdict.

    Every non-success shape must red: `failure` for a genuine break, and
    `skipped`/`cancelled` because a matrix that never ran proves nothing — treating
    either as a pass reproduces #4779 inside the aggregate that exists to prevent it.

    `cancelled` is a workflow cancel (new SHA), not fail-fast wiping siblings:
    the pack matrix is `fail-fast: false` so one red pack cannot destroy the
    other eleven proofs. ci-gate still must not pass a cancelled matrix.
    """
    reconcile = _gate_step("reconcile complete semantic evidence")
    assert "PACK_RESULT" not in reconcile.get("env", {})
    assert "needs.ci-pack.result" not in str(reconcile)
    download = _gate_step("download every raw semantic pack fragment")
    assert download["with"]["pattern"] == "ci-semantic-pack-${{ github.run_id }}-*"
    assert download["with"]["merge-multiple"] is True


def test_ci_gate_always_publishes_one_overwritten_final_artifact() -> None:
    """The green path, so the tests above cannot be satisfied by a gate that always fails.

    An adjudicator that reds unconditionally would pass every negative test in this
    file and block every PR in the repository.
    """
    upload = _gate_step("publish final semantic evidence")
    assert upload["if"] == "always()"
    assert upload["with"]["name"] == "ci-semantic-evidence-${{ github.run_id }}"
    assert upload["with"]["path"].endswith("/ci-semantic-evidence.json")
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["overwrite"] is True


# ─── the 2026-08-14 E2BIG transport (run 31775693780) ───────────────────────────


def _artifact_step(job: str, action: str, name: str) -> dict[str, Any]:
    """The one step in `job` using `action` for the artifact called `name`."""
    matches = [
        step
        for step in _job(job)["steps"]
        if str(step.get("uses", "")).startswith(action)
        and str(step.get("with", {}).get("name", "")) == name
    ]
    assert len(matches) == 1, (
        f"{job} must use {action} for {name!r} exactly once, found {len(matches)}"
    )
    return matches[0]


def test_the_changed_file_list_never_travels_through_the_process_environment() -> None:
    """The 2026-08-14 E2BIG, pinned as an ABSENCE (run 31775693780).

    PR #5578 carried a handful of files. Every one of its twelve packs died
    before running a test:

        An error occurred trying to start process '/usr/bin/bash' ...
        Argument list too long

    The planner had diffed against the PR's opening base SHA while main moved 45
    commits / 8,581 paths underneath it, attributed the whole drift to the PR,
    and rode the resulting list into the pack step's `env:` through a job
    output: 350,264 bytes against execve's 131,072-byte MAX_ARG_STRLEN.

    Two names are therefore forbidden in this file outright. `env:` and
    `$GITHUB_ENV` are the same hazard — both end up in a later process's
    environment — so "it is only an env var, not a command line" is not a
    defence: execve counts them together. What IS allowed to cross is a PATH.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "CI_CHANGED_FILES_JSON" not in text, (
        "the inline list must not reappear in ci.yml under any name — it is the "
        "350,264-byte string that killed all twelve packs at launch"
    )
    # Assembled by concatenation, the same idiom `check_conflict_markers` uses
    # for its own markers: the retired expression must not appear verbatim in
    # this file either, or a repo-wide `git grep` for it can never come back
    # clean and the absence stops being checkable from outside this test.
    retired_output = "outputs." + "changed_files "
    assert retired_output not in text.replace("}", " "), (
        "a job output becomes an `env:` string in the consuming job; that is "
        "exactly how the list reached the pack step's environment"
    )
    exports = [
        line.strip()
        for line in text.splitlines()
        if "CI_CHANGED_FILES_FILE=" in line
    ]
    assert len(exports) == 1, (
        f"ci-pack must export the handle exactly once (found {len(exports)}: {exports})"
    )
    assert "GITHUB_ENV" in exports[0]
    assert "changed-files.json" in exports[0], (
        "the handle must name the downloaded file, so run_ci_pack and every "
        "child guard resolve the same bytes"
    )


def test_ci_plan_publishes_the_changed_file_list_as_an_artifact() -> None:
    """The artifact IS the transport, and both ends must fail closed.

    Three regressions this pins, each of which leaves a green-looking workflow:

      * The upload going conditional. `run_ci_pack.py` writes the file on BOTH
        exits of the plan step — the resolved list on success, `null` on the
        planner-fallback path that swallows its exception and exits 0 — so
        "a pack is running" implies "this artifact exists", and that implication
        is what lets the pack-side download be a hard failure.
      * `if-no-files-found` drifting off `error`. The default is `warn`: a
        missing file would publish an empty artifact, every pack would download
        nothing, and the scope of the run becomes a value nobody chose.
      * The `--emit-changed-files` flag disappearing from the plan command, or
        naming a path the upload does not publish.
    """
    run = str(_plan_step()["run"])
    assert (
        '--emit-changed-files "$RUNNER_TEMP/ci-changed-files/changed-files.json"' in run
    )
    upload = _artifact_step("ci-plan", "actions/upload-artifact@", "ci-changed-files")
    assert "if" not in upload, (
        "the upload must be unconditional — the planner-fallback path publishes "
        "no plan sha but its packs still need the list"
    )
    assert upload["with"]["path"] == (
        "${{ runner.temp }}/ci-changed-files/changed-files.json"
    )
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == 14
    steps = _job("ci-plan")["steps"]
    assert steps.index(upload) > steps.index(_plan_step()), (
        "the list is written BY the plan step; uploading before it publishes nothing"
    )


def test_ci_pack_downloads_the_list_and_exports_only_its_path() -> None:
    """A path crosses; the list never does. Order is load-bearing.

    The download and the handle export must both precede the pack command, or
    `run_ci_pack.py` resolves an absent handle, widens to a `git diff` its
    fetch-depth-1 checkout cannot answer, and — because `changed_files_sha256`
    is inside the hashed plan payload — refuses on `--expect-plan-sha` instead
    of running anything. Failing closed is correct; failing closed on EVERY PR
    is an outage.
    """
    steps = _job("ci-pack")["steps"]
    download = _artifact_step(
        "ci-pack", "actions/download-artifact@", "ci-changed-files"
    )
    assert download["with"]["path"] == "${{ runner.temp }}/ci-changed-files"
    assert download["if"] == (
        "github.event.pull_request.head.repo.full_name != github.repository"
    ), (
        "only the hosted fork executor downloads this artifact; same-repository "
        "packs relay the main-owned trusted fragment instead"
    )
    export = next(
        step for step in steps if "CI_CHANGED_FILES_FILE=" in str(step.get("run", ""))
    )
    assert steps.index(download) < steps.index(export) < steps.index(_pack_step())
    assert "CI_CHANGED_FILES_FILE" not in _pack_step().get("env", {}), (
        "the pack step must inherit the handle from $GITHUB_ENV, not re-declare "
        "it — one writer keeps the two jobs naming the same bytes"
    )
