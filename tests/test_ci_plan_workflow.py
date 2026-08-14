"""Wave B workflow structure: `ci-plan` plans once, `ci-pack` executes it, `ci-gate` adjudicates.

WHAT CHANGED AND WHY THIS SUITE EXISTS.  Until 2026-08-11 `ci.yml` carried one job
with a literal `matrix: pack: [0..11]`, and all twelve packs re-derived the same
selection independently.  The matrix is now emitted by a new `ci-plan` job, which
means two properties that used to be structurally impossible are now merely
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
    return _step_running(_job("ci-pack"), "--execute")


def _gate_script() -> str:
    steps = _job("ci-gate")["steps"]
    assert len(steps) == 1, f"ci-gate should adjudicate in one step, found {len(steps)}"
    return str(steps[0]["run"])


def _run_gate(
    *, plan: str, pack: str, has_work: str, plan_sha: str = "pinnedsha"
) -> subprocess.CompletedProcess[str]:
    """Execute ci-gate's adjudication script with the `needs` context it would see."""
    return subprocess.run(
        ["bash", "-c", _gate_script()],
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PLAN_RESULT": plan,
            "PACK_RESULT": pack,
            "HAS_WORK": has_work,
            "PLAN_REASON": "pinned by tests/test_ci_plan_workflow.py",
            "PLAN_SHA": plan_sha,
            "GITHUB_STEP_SUMMARY": os.devnull,
        },
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )


def _ci_class(result: subprocess.CompletedProcess[str]) -> str:
    """The one CI_CLASS= token the gate printed, or '' if it printed none/many."""
    tokens = [
        line.split("=", 1)[1]
        for line in result.stdout.splitlines()
        if line.startswith("CI_CLASS=")
    ]
    return tokens[0] if len(tokens) == 1 else ""


# ─── ci-plan ────────────────────────────────────────────────────────────────────


def test_ci_plan_job_exists_and_publishes_all_six_outputs() -> None:
    """`ci-pack` and `ci-gate` read these outputs by name.

    Drop or rename one and the consumer expression silently evaluates to the empty
    string: `matrix` breaks `fromJSON` outright, but `has_work` empty means the pack
    gate is never `'true'` so the ENTIRE matrix is skipped on every PR, and
    `plan_sha` empty just unpins the parity check.  Two of those three failures are
    green-looking. `changed_files` empty makes every pack re-diff a shallow clone
    and fail-safe-widen to the full suite. `plan_document` empty silently demotes
    every pack from the consume-the-plan fast path back to a full ~106s
    re-inference each — green-looking again, and the 2026-08-14 incident's ×12
    overhead quietly returns.
    """
    job = _job("ci-plan")
    assert job["outputs"] == {
        "matrix": "${{ steps.plan.outputs.matrix }}",
        "has_work": "${{ steps.plan.outputs.has_work }}",
        "plan_sha": "${{ steps.plan.outputs.plan_sha }}",
        "reason": "${{ steps.plan.outputs.reason }}",
        "changed_files": "${{ steps.plan.outputs.changed_files }}",
        "plan_document": "${{ steps.plan.outputs.plan_document }}",
    }


def test_ci_plan_is_fenced_against_closed_events() -> None:
    """A closed PR needs only the workflow-level concurrency side effect.

    Without the fence a merged-close event would allocate a planning runner whose
    only product is a check nobody reads, and — worse — `ci-gate` is fenced the same
    way, so the two conditions must agree or a close publishes half the graph.
    """
    assert _job("ci-plan")["if"] == "github.event.action != 'closed'"


def test_ci_plan_checks_out_depth_one_and_diffs_via_the_files_api() -> None:
    """The planner's diff is METADATA, not history (2026-08-14 incident).

    `fetch-depth: 0` here cost 7-8 minutes of history fetch per plan (run
    31763116872) purely so `git diff` could reach the base SHA. The diff now
    arrives from the PR files API into `CI_CHANGED_FILES_JSON`, which
    `resolve_changed_files` prefers over git. Three regressions this pins:
    reintroducing the deep fetch (the latency returns), dropping the diff step
    (every PR silently widens to the full suite — green-looking), and running
    the diff step without a token (same silent widen).
    """
    job = _job("ci-plan")
    checkouts = [s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert len(checkouts) == 1, f"ci-plan should check out exactly once, found {len(checkouts)}"
    assert checkouts[0]["with"]["fetch-depth"] == 1
    diff_steps = [s for s in job["steps"] if "ci_plan_changed_files.py" in str(s.get("run", ""))]
    assert len(diff_steps) == 1, "ci-plan must resolve the diff from the files API exactly once"
    diff = diff_steps[0]
    assert diff.get("if") == "github.event_name == 'pull_request'"
    assert diff["env"]["GH_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    assert diff["env"]["CI_PR_NUMBER"] == "${{ github.event.pull_request.number }}"
    assert "CI_CHANGED_FILES_JSON" in str(diff["run"])


def test_ci_plan_scope_cache_is_exact_match_only() -> None:
    """The scope map may be cached, never approximated.

    `restore-keys` on this cache would hand the planner a map derived from a
    DIFFERENT tree; the in-file identity check guards only the manifest's job
    set, not tree freshness, so a prefix restore could silently mis-scope every
    PR that follows. Exact hit or honest recomputation are the only two states.
    """
    job = _job("ci-plan")
    caches = [s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/cache@")]
    assert len(caches) == 1, "ci-plan should restore exactly one scope-map cache"
    assert "restore-keys" not in caches[0]["with"]
    assert "steps.scope-key.outputs.key" in caches[0]["with"]["key"]
    run = _plan_step()["run"]
    assert "--scope-cache .ci-plan-cache/scope-map.json" in run


def test_ci_plan_preflight_guards_run_after_the_plan_and_before_any_pack() -> None:
    """Structural defects must refuse the fanout in minutes (2026-08-14).

    Run 31763116872 took 67 minutes to surface `tests/test_prophet_lifecycle_state.py`
    wired into no workflow — a fact `audit_unrun_tests` proves in seconds. These
    steps live in `ci-plan` AFTER the plan step (so a preflight red still leaves
    the plan outputs published for diagnosis) and gate `ci-pack` through the
    job-level `needs`, so no pack can launch past a structural red. Dropping any
    one of them reopens its late-failure class silently.
    """
    steps = _job("ci-plan")["steps"]
    runs = [str(s.get("run", "")) for s in steps]
    plan_index = next(i for i, r in enumerate(runs) if "--plan-only" in r)
    for needle in (
        "scripts/check_workflow_yaml.py .github/workflows",
        "scripts/audit_unrun_tests.py",
        "scripts/check_ci_trigger_closure.py",
        "scripts/check_conflict_markers.py",
    ):
        matches = [i for i, r in enumerate(runs) if needle in r]
        assert matches, f"ci-plan preflight lost its {needle} guard"
        assert all(i > plan_index for i in matches), (
            f"{needle} must run AFTER the plan step so a preflight red still "
            "publishes the plan outputs"
        )
    conflict_step = next(s for s in steps if "check_conflict_markers.py" in str(s.get("run", "")))
    assert "env.CI_CHANGED_FILES_JSON != 'null'" in str(conflict_step.get("if", "")), (
        "the conflict-marker preflight must skip when the diff widened to null — "
        "a depth-1 clone cannot serve its git fallback and an infra widen must "
        "not read as a content red"
    )


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
    assert "--emit-plan-json -" in run
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
    for job_name, step in (("ci-plan", _plan_step()), ("ci-pack", _pack_step())):
        assert "--changed-from" not in step["run"], (
            f"{job_name} names --changed-from literally; it must arrive via $CI_SCOPE_ARG"
        )
        scope_arg = step["env"]["CI_SCOPE_ARG"]
        assert "github.event_name == 'pull_request'" in scope_arg
        assert scope_arg.rstrip().endswith("|| '' }}"), (
            f"{job_name}'s CI_SCOPE_ARG must fall back to the empty string on non-PR events"
        )


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
    env = _pack_step()["env"]
    plan_sha_arg = env["PLAN_SHA_ARG"]
    assert "needs.ci-plan.outputs.plan_sha" in plan_sha_arg
    assert "format('--expect-plan-sha {0}'" in plan_sha_arg
    assert plan_sha_arg.rstrip().endswith("|| '' }}"), (
        "an empty plan_sha must word-split away, not emit a valueless --expect-plan-sha"
    )
    assert " $PLAN_SHA_ARG " in f" {_pack_step()['run']} ", "the argument must be unquoted so it can vanish"
    assert env["CI_CHANGED_FILES_JSON"] == "${{ needs.ci-plan.outputs.changed_files }}"
    assert "CI_CHANGED_FILES_JSON" not in _pack_step()["run"], (
        "the changed-file list must travel via env, not the folded command line"
    )


def test_ci_pack_consumes_the_published_plan_and_falls_back_when_absent() -> None:
    """Packs EXECUTE the published plan; re-derivation is the fallback, not the norm.

    The materialize step turns `plan_document` into a file plus `--plan-json` in
    `$PLAN_JSON_ARG`, and writes an EMPTY `PLAN_JSON_ARG` when ci-plan published
    nothing — the argument must then word-split away so the pack self-plans
    (the fail-safe path). Three silent regressions this pins: dropping the
    materialize step (every pack quietly pays the ~106s re-inference again),
    quoting the argument (an empty positional kills argparse on the fallback
    path), and materializing from anything other than the job output (a pack
    could execute a plan for a different head).
    """
    job = _job("ci-pack")
    materialize = [s for s in job["steps"] if "ci-plan-document.json" in str(s.get("run", ""))]
    assert len(materialize) == 1, "ci-pack must materialize the published plan exactly once"
    step = materialize[0]
    assert step["env"]["PLAN_DOCUMENT"] == "${{ needs.ci-plan.outputs.plan_document }}"
    body = str(step["run"])
    assert "PLAN_JSON_ARG=--plan-json" in body
    assert "PLAN_JSON_ARG=" in body.replace("PLAN_JSON_ARG=--plan-json", "", 1), (
        "the materialize step must also write the EMPTY fallback assignment"
    )
    run = _pack_step()["run"]
    assert " $PLAN_JSON_ARG " in f" {run} ", "the plan-json argument must ride unquoted"
    assert '"$PLAN_JSON_ARG"' not in run and "'$PLAN_JSON_ARG'" not in run


def test_pack_shell_arguments_stay_unquoted_so_an_empty_value_disappears() -> None:
    """Quoting either env-built argument turns "absent" into an empty positional word.

    `"$CI_SCOPE_ARG"` on a workflow_dispatch would hand `run_ci_pack.py` an empty
    string as a positional argument instead of handing it nothing — argparse then
    errors, and main's baseline (the audit backstop) dies before it plans.
    """
    for job_name, step in (("ci-plan", _plan_step()), ("ci-pack", _pack_step())):
        run = step["run"]
        for var in ("$CI_SCOPE_ARG", "$PLAN_SHA_ARG"):
            if var not in run:
                continue
            assert f'"{var}"' not in run, f"{job_name} quotes {var}; it must word-split away when empty"
            assert f"'{var}'" not in run, f"{job_name} quotes {var}; it must word-split away when empty"


def test_folded_pack_commands_fold_to_one_line_and_carry_no_comment_marker() -> None:
    """The two folded-scalar traps this repo has already been bitten by.

    A `#` inside a `run: >-` scalar deletes the rest of the command, and a
    continuation line at a DIFFERENT indent keeps its newline instead of folding to a
    space — which once split one command into two and ran `--execute` as its own
    shell line.  Both produce a workflow that parses cleanly and does the wrong
    thing, so the only detector is the folded RESULT: exactly one line, no `#`.
    """
    for job_name, step in (("ci-plan", _plan_step()), ("ci-pack", _pack_step())):
        run = str(step["run"]).strip()
        assert "\n" not in run, f"{job_name}'s command did not fold to one line: {run!r}"
        assert "#" not in run, f"{job_name}'s folded command contains a `#`, which truncates it"


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


def test_ci_gate_classifies_every_terminal_shape_exactly_once() -> None:
    """Phase-10 contract (2026-08-14 incident): one CI_CLASS= line per run.

    The classification is what lets a developer — and the merge controller —
    learn "what KIND of failure" from the run page instead of thirty minutes of
    pack logs. Each terminal shape must emit exactly one machine-readable line
    with the agreed class token; zero lines silently re-opens the
    read-the-logs era and two lines makes the parse ambiguous, so `_ci_class`
    returns '' for both defects.

      * plan red + published sha  -> structural-preflight (the plan step
        succeeded and published, so the red is a preflight guard)
      * plan red + no sha         -> planner-infra
      * no-work                   -> no-work
      * pack cancelled            -> superseded (proves nothing, but is not a
        content failure — the sweeper must not mark the PR merge-blocked on it)
      * pack failure/skipped      -> pack-failure
      * all green                 -> pass
    """
    cases = [
        (dict(plan="failure", pack="skipped", has_work="true"), "structural-preflight"),
        (dict(plan="failure", pack="skipped", has_work="true", plan_sha=""), "planner-infra"),
        (dict(plan="success", pack="skipped", has_work="false"), "no-work"),
        (dict(plan="success", pack="cancelled", has_work="true"), "superseded"),
        (dict(plan="success", pack="failure", has_work="true"), "pack-failure"),
        (dict(plan="success", pack="skipped", has_work="true"), "pack-failure"),
        (dict(plan="success", pack="success", has_work="true"), "pass"),
    ]
    for kwargs, expected in cases:
        proc = _run_gate(**kwargs)
        assert _ci_class(proc) == expected, (
            f"gate context {kwargs} classified as {_ci_class(proc)!r}, "
            f"expected {expected!r}:\n{proc.stdout}"
        )
