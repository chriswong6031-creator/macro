"""Contract + decision tests for the merge-on-green sweeper.

The sweeper is the account-side substitute for branch protection (operator ruling
2026-07-28): a session arms its pull request with the `merge-on-green` label and
stops instead of sitting 20-60 minutes as a CI hostage, and this lane performs the
merge once every check has CONCLUDED clean.

Two things are pinned here. The WORKFLOW contract, because the sweep is worthless
if it is scheduled wrong, queued behind the render lane, or handed a token that
cannot merge. And the DECISION, factored into a pure function over a check-run
list so the four outcomes are provable without a network.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
from pathlib import Path

import pytest
import yaml

import scripts.merge_on_green as MOG


ROOT = Path(__file__).resolve().parents[1]
REAL_IN_FLIGHT_PR_PROOFS = MOG.in_flight_pr_proofs
REAL_PREPARE_REFRESH_LEASE = MOG.prepare_refresh_lease
REAL_SERIALIZED_REFRESH_AUTHORITY = MOG.serialized_refresh_authority
REAL_ENSURE_SELF_WAKE = MOG.ensure_self_wake
REAL_LEASE_RECONCILE_PASS = MOG.lease_reconcile_pass
WORKFLOW = ROOT / ".github" / "workflows" / "merge-on-green.yml"
BASELINE_WORKFLOW = ROOT / ".github" / "workflows" / "integration-baseline.yml"
DEPLOY_SECRETS_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-api-secrets.yml"


@pytest.fixture(autouse=True)
def _no_unstubbed_http(monkeypatch):
    """No test in this pack may reach api.github.com.

    Added 2026-08-07, because the budget work introduced two NEW network entry
    points into `main()` — `core_rate_limit` and (then) main's clean-check lookup — and
    both swallow their own errors by design (fail-open and fail-closed respectively). A
    test that forgot to stub them would therefore still PASS, silently making a real
    HTTP call, taking a 30-second timeout on an offline runner, and asserting about a
    code path it never exercised. A test that needs HTTP overrides this with its own
    `monkeypatch.setattr(MOG, "_request", ...)`, which lands after this fixture.

    The 2026-08-08 proof rework replaced that function with `main_proof` and added
    `ensure_main_baseline`, both of which swallow everything for the same reason —
    so the guard below is now covering three self-silencing entry points, not two.
    """

    def refuse(method, url, *_a, **_k):
        raise AssertionError(
            f"unstubbed HTTP {method} {url} — stub MOG._request (or the helper that "
            "calls it) rather than letting a test reach the network"
        )

    monkeypatch.setattr(MOG, "_request", refuse)
    # `core_rate_limit` propagates its caller's exceptions, so without a neutral
    # default every pre-budget `main()` test would die on the guard above rather than
    # on what it is about. A healthy budget is the pre-2026-08-07 behaviour; tests
    # that are ABOUT the budget override this.
    #
    # `main_proof` deliberately gets NO default: it swallows every error by design, so
    # the refusing `_request` above already gives it its neutral fail-closed answer (an
    # empty proof) without a real call — and leaving the real function in place keeps
    # the tests that exercise it exercising it.
    monkeypatch.setattr(MOG, "core_rate_limit", lambda _token: (1000, 1000))
    # The repo-wide Actions census is another main()-only read. Healthy/idle is the
    # neutral default; tests about global refresh backpressure override it.
    monkeypatch.setattr(MOG, "in_flight_pr_proofs", lambda *_a: 0)
    monkeypatch.setattr(MOG, "serialized_refresh_authority", lambda *_a: True)
    monkeypatch.setattr(
        MOG,
        "prepare_refresh_lease",
        lambda repo, read, write, pulls: (
            MOG.RefreshLease(repo, read, write),
            pulls,
        ),
    )
    monkeypatch.setattr(MOG, "ensure_self_wake", lambda *_a, **_k: "stubbed")
    monkeypatch.delenv("CURRENT_RUN_ID", raising=False)


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(parsed: dict) -> dict:
    """`on:` parses as the YAML 1.1 boolean True unless quoted."""
    return parsed.get("on", parsed.get(True)) or {}


def _sweep_step(parsed: dict) -> dict:
    for step in parsed["jobs"]["sweep"]["steps"]:
        if "scripts/merge_on_green.py" in str(step.get("run") or ""):
            return step
    raise AssertionError("no step invokes scripts/merge_on_green.py")


def test_the_workflow_is_event_driven_with_a_ten_minute_recovery_schedule():
    parsed = _workflow()
    triggers = _triggers(parsed)
    crons = [entry.get("cron") for entry in (triggers.get("schedule") or [])]
    assert "*/10 * * * *" in crons, f"expected a 10-minute sweep, got {crons}"
    assert "workflow_dispatch" in triggers, "an operator must be able to force a sweep"
    workflow_run = triggers.get("workflow_run") or {}
    assert set(workflow_run.get("workflows") or []) == {
        "ci",
        "fences",
        "integration-baseline",
    }
    assert workflow_run.get("types") == ["completed"]


def test_the_sweep_never_queues_behind_the_workload_it_arbitrates():
    """Keep the control plane on the one runner reserved for the arbiter.

    On 2026-08-11 the hosted pool was pinned at 180/180 with 91 jobs queued while
    mac-builder-4 sat online and idle. Its unique label is the isolation boundary;
    shared workload labels would merely move the priority inversion.
    """
    job = _workflow()["jobs"]["sweep"]
    labels = json.dumps(job["runs-on"])
    assert job["runs-on"] == ["self-hosted", "macOS", "ARM64", "merge-control"]
    assert "merge-control" in labels
    assert "render-linux" not in labels
    assert "render-heavy" not in labels
    assert "macstudio" not in labels
    assert "parked" not in labels
    assert int(job["timeout-minutes"]) == 15


def test_the_dedicated_sweep_keeps_a_minimal_runner_contract():
    """The dedicated route needs only the runner's Python and network.

    The integration-baseline job has its own routing/setup-python contract; adding a
    setup step to this lightweight sweep must fail here rather than silently making the
    control plane slower or stateful.
    """
    steps = _workflow()["jobs"]["sweep"]["steps"]
    used = [str(step.get("uses") or "") for step in steps]
    assert not [entry for entry in used if entry.startswith("actions/setup-python")], (
        f"the sweep must stay runner-agnostic; found {used}"
    )


def test_no_bare_self_hosted_job_can_steal_the_merge_control_runner():
    """No literal self-hosted route may also match mac-builder-4's full label set."""
    parsed = yaml.safe_load(DEPLOY_SECRETS_WORKFLOW.read_text(encoding="utf-8"))
    assert parsed["jobs"]["deploy"]["runs-on"] == ["self-hosted", "macstudio-light"]
    controller_labels = {"self-hosted", "macOS", "ARM64", "parked", "merge-control"}
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        for name, job in (payload.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            route = job.get("runs-on")
            labels = {route} if isinstance(route, str) else set(route or [])
            if "self-hosted" not in labels or not labels <= controller_labels:
                continue
            assert (path.name, name) == ("merge-on-green.yml", "sweep"), (
                f"{path.name}:{name} route {route!r} can steal merge-control"
            )


def test_the_workflow_can_actually_merge_and_label():
    parsed = _workflow()
    permissions = parsed["permissions"]
    # `actions` was `read` — enough for the circuit breaker and the proof lookup, but
    # not enough to ORDER the proof. ci.yml has no `push` trigger, so main is proven
    # only by a dispatch; with `read` that dispatch could only ever come from a human,
    # and it was measured 12 hours late while 48 pull requests sat armed (2026-08-08).
    assert permissions["actions"] == "write", (
        "needed to read the baseline/proof runs AND to dispatch ci.yml on main"
    )
    assert permissions["contents"] == "write", "needed to squash-merge and update the head"
    assert permissions["pull-requests"] == "write", "needed for merge-blocked + the comment"
    assert permissions["issues"] == "write", "needed for the durable refresh-lease label"
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "no `push` trigger" in source, (
        "the reason `actions` is write must stay in the file — it is not obvious, and "
        "an editor tidying it back to `read` silently re-breaks the refresh path"
    )


def test_concurrency_coalesces_full_sweeps_without_swallowing_red_markers():
    """The 2026-08-06 livelock, repaired without losing #5291 markers.

    A workflow-wide constant group serialized a 25-107 minute hosted queue wait,
    so triggers arriving every ~50 seconds replaced the only pending run: 98
    cancelled and 0 successful. The group is safe only at job scope on the
    dedicated runner, and failure wakeups must be keyed by head SHA because each
    bounded pass marks exactly one failed head.

    Full sweeps are level-triggered and therefore share `sweep`; duplicates for
    one failed head may coalesce, but different failed heads cannot.
    """
    parsed = _workflow()
    assert "concurrency" not in parsed, "workflow-level grouping repeats the old livelock"
    concurrency = parsed["jobs"]["sweep"]["concurrency"]
    group = str(concurrency["group"])
    assert concurrency["cancel-in-progress"] is False
    assert "workflow_run.conclusion == 'failure'" in group
    assert "workflow_run.head_sha" in group and "mark-{0}" in group
    assert "&& 'sweep'" in group
    assert "|| 'lease-reconcile'" in group
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "livelock" in source.lower(), "the postmortem must stay in the file"
    assert "25-107 minutes" in source and "dedicated runner" in source


def test_the_sweep_wakes_for_merge_mark_or_bounded_lease_reconciliation():
    """The event gate admits every conclusion but routes it to bounded work.

    A skipped job costs no runner, no queue slot and no minutes. Only a green
    triggering run can make a PR mergeable (ci's last
    100 completed runs: 51 failure, 25 cancelled, 18 skipped, 6 success).

    `failure` is admitted TOO, since 2026-08-11 (PR #5291), and not for merging: it
    runs the bounded `mark_only_pass`. The old gate's stated reason for dropping reds
    was that it "fails SAFE — a red PR simply stays armed and unmerged", which
    assumed nothing else touches the label while the red is unmarked. #5291's red
    concluded at 02:05:18Z, a session stripped `merge-on-green` at 02:13:34Z leaving
    no marker at all, and the 02:13:41Z sweep could no longer SEE the pull request —
    a label-filtered sweeper cannot mark what is not labeled, so the marker could
    never arrive. The window has to be closed from the failure side.

    `cancelled` and `skipped` are admitted only for an O(1) durable-lease cleanup;
    they never mark a red and never walk/refresh/merge the backlog.

    `schedule` and `workflow_dispatch` must never be gated away — the cron is the
    recovery net for third-party checks, and an operator must always be able to
    force a sweep.
    """
    gate = " ".join(str(_workflow()["jobs"]["sweep"]["if"]).split())
    assert "github.event_name != 'workflow_run'" in gate, (
        "the cron and workflow_dispatch must bypass the conclusion filter entirely"
    )
    assert "workflow_run.conclusion != ''" in gate
    group = str(_workflow()["jobs"]["sweep"]["concurrency"]["group"])
    assert "conclusion == 'failure'" in group and "mark-{0}" in group
    assert "conclusion == 'success'" in group and "'sweep'" in group
    assert "'lease-reconcile'" in group


def test_the_sweep_step_invokes_the_tracked_script_with_the_token_fallback():
    """The PAT is load-bearing: a GITHUB_TOKEN merge does not fire push-triggered
    workflows, so render.yml would never see a sweeper merge. The fallback keeps
    the lane working (degraded) when the PAT is absent."""
    step = _sweep_step(_workflow())
    env = step["env"]
    assert env["GH_REPO"] == "${{ github.repository }}"
    assert env["READ_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    assert env["MERGE_TOKEN"] == "${{ secrets.ADMIN_GH_TOKEN || secrets.GITHUB_TOKEN }}"


def test_the_sweeper_sparse_checks_out_only_what_it_reads():
    """A ~53k-file checkout cost ~100 s before the first API call. The list is now
    three entries, and `.github/workflows` is one of them BECAUSE the tested-surface
    gate reads the path filters out of it — if that entry is dropped the sweep aborts
    on every run instead of merging on undated greens, but it still aborts, so the
    entry is part of the lane's contract."""
    checkout = _workflow()["jobs"]["sweep"]["steps"][0]
    assert checkout["uses"] == "actions/checkout@v4"
    options = checkout["with"]
    assert options["filter"] == "blob:none"
    wanted = set(str(options["sparse-checkout"]).split())
    assert wanted == {
        "scripts/merge_on_green.py",
        "scripts/gh_path_filter.py",
        ".github/workflows",
    }
    assert options["sparse-checkout-cone-mode"] is False


def test_the_sweeper_installs_the_yaml_parser_before_it_sweeps():
    """The gate parses `on.pull_request.paths` out of the checked-out workflows. If
    PyYAML is merely ASSUMED present and the runner image drops it, every sweep
    aborts — so the install is a step, not a hope, and it must precede the sweep.

    The import-first fallback remains useful on hosted image updates, but this test no
    longer encodes self-hosted PEP-668 behavior as part of the runner contract.
    """
    steps = _workflow()["jobs"]["sweep"]["steps"]
    runs = [str(step.get("run") or "") for step in steps]
    installs = [index for index, run in enumerate(runs) if "pip install" in run and "pyyaml" in run]
    sweeps = [index for index, run in enumerate(runs) if "scripts/merge_on_green.py" in run]
    assert installs and sweeps, f"expected an install step and a sweep step, got {runs}"
    assert installs[0] < sweeps[0], "the parser must be installed before the sweep runs"
    install = runs[installs[0]]
    assert "import yaml" in install, "skip the install when the runner already has it"
    assert "python3 -m pip install" in install


def test_the_main_baseline_is_fast_bounded_and_runs_the_merge_train_contract():
    parsed = yaml.safe_load(BASELINE_WORKFLOW.read_text(encoding="utf-8"))
    triggers = _triggers(parsed)
    assert "push" in triggers and triggers["push"]["branches"] == ["main"]
    job = parsed["jobs"]["baseline"]
    runs_on = " ".join(str(job["runs-on"]).split())
    assert "render-linux" in runs_on
    assert "ubuntu-latest" in runs_on
    assert int(job["timeout-minutes"]) == 30
    source = BASELINE_WORKFLOW.read_text(encoding="utf-8")
    assert "60k tracked paths" in source
    assert "former 12-minute" in source
    assert "tests/test_merge_on_green.py" in source
    assert "scripts/check_skip_only_suites.py" in source


def test_the_workflow_records_why_the_pat_matters():
    """This rationale is the thing a future editor would otherwise delete."""
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "#3889" in source, "the --auto-merges-instantly finding must stay cited"
    assert "push-triggered" in source
    assert "3-minute pull" in source or "3-min" in source


# --- the decision, as a pure function -----------------------------------------


# Check timestamps still date red-vs-main-baseline evidence. Freshness no longer
# infers a proof base from them: the exact pull_request base SHA is authoritative.
PROOF_STARTED_AT = "2026-08-05T12:00:00Z"
BEFORE_THE_PROOF = "2026-08-05T09:00:00Z"
PROOF_BASE_SHA = "0" * 40
DEFAULT_MAIN_SHA = f"{1:040d}"
EXACT_HEAD_SHA = "a" * 40
# When a head's checks CONCLUDED, and when main was subsequently proven green. The
# base-inherited-red refresh needs main's proof to POSTDATE the failures it excuses —
# a green main from BEFORE the head ran says nothing about the head's red — so every
# fixture here carries both instants rather than only the check's start.
CHECKS_CONCLUDED_AT = "2026-08-05T12:30:00Z"
MAIN_PROVED_AT = "2026-08-05T18:00:00Z"
MAIN_PROVED_BEFORE_THE_CHECKS = "2026-08-05T10:00:00Z"


def _run(
    name: str,
    status: str = "completed",
    conclusion=None,
    started_at: str | None = PROOF_STARTED_AT,
    completed_at: str | None = CHECKS_CONCLUDED_AT,
    *,
    base_sha: str = PROOF_BASE_SHA,
    head_sha: str = EXACT_HEAD_SHA,
    pr_numbers: tuple[int, ...] = (4242,),
    app_slug: str = "github-actions",
    include_proof_metadata: bool = True,
) -> dict:
    run = {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "started_at": started_at,
        "completed_at": completed_at,
        "head_sha": head_sha,
        "app": {"slug": app_slug},
    }
    run["pull_requests"] = (
        [
            {
                "number": number,
                "head": {"sha": head_sha},
                "base": {"sha": base_sha},
            }
            for number in pr_numbers
        ]
        if include_proof_metadata
        else []
    )
    return run


def _required_proof_runs(*, conclusion: str = "success") -> list[dict]:
    return [
        _run(name, conclusion=conclusion)
        for name in sorted(MOG.REQUIRED_CI_ANCHORS | {MOG.REQUIRED_FENCE_ANCHOR})
    ]


def _proof(
    *names: str,
    proved_at: str | None = MAIN_PROVED_AT,
    head_sha: str = "f" * 40,
    source: str = "ci.yml@ffffffffffff",
) -> "MOG.MainProof":
    """A `MainProof` whose default instant POSTDATES `_run`'s default conclusion.

    So a test that only cares about the NAME comparison keeps the pre-timestamp
    outcome, and a test that is about the timestamp says so by passing `proved_at`.
    """
    return MOG.MainProof(
        frozenset(names), MOG._parse_dt(proved_at), head_sha, source
    )


def _gates(patterns=("engine/**", "scripts/*.py", "tests/**")) -> list[dict]:
    return [{"workflow": "ci.yml", "patterns": list(patterns)}]


def _freshness(commits=((BEFORE_THE_PROOF, ["data/nightly.json"]),), **kwargs):
    """A `ProofFreshness` with its reads pre-seeded — no network, no monkeypatching.

    `commits` is `[(diagnostic timestamp, [changed files]), ...]`; freshness itself
    uses only their generated SHA order. A synthetic exact proof base is appended by
    default so tests classify the supplied commits without inferring time.
    """
    gates = kwargs.pop("gates", None) or _gates()
    pull_files = kwargs.pop("pull_files", None)
    repo = kwargs.pop("repo", "acme/widgets")
    include_proof_base = kwargs.pop("include_proof_base", True)
    assert not kwargs, kwargs
    parsed = [
        {"sha": f"{index + 1:040d}"} for index, (_iso, _files) in enumerate(commits)
    ]
    if include_proof_base:
        parsed.append({"sha": PROOF_BASE_SHA})
    fresh = MOG.ProofFreshness(repo, "read", gates, parsed)
    for entry, (_iso, files) in zip(parsed, commits):
        fresh._commit_files[entry["sha"]] = (list(files), False)
    for number, names in (pull_files or {}).items():
        fresh._pr_files[number] = None if names is None else list(names)
    return fresh


def test_a_pending_check_means_wait():
    """A pending check is not a pass — the whole point of the merge-on-CONCLUDED law."""
    verdict, names = MOG.decide_verdict(
        [_run("ci-pack-1", conclusion="success"), _run("ci-pack-2", "in_progress")]
    )
    assert verdict == "pending"
    assert names == ["ci-pack-2"]


def test_pending_outranks_a_red_so_the_comment_is_never_burned_on_a_race():
    """Labeling merge-blocked while checks still run would be premature, and the
    explanatory comment is one-shot."""
    verdict, _names = MOG.decide_verdict(
        [_run("ci-pack-1", conclusion="failure"), _run("ci-pack-2", "queued")]
    )
    assert verdict == "pending"


def test_a_spurious_only_red_is_still_mergeable():
    """`Workers Builds: macro` is the known-spurious X this repo has always ignored."""
    verdict, names = MOG.decide_verdict(
        [
            _run("ci-pack-1", conclusion="success"),
            _run("nav-gap", conclusion="skipped"),
            _run("Workers Builds: macro", conclusion="failure"),
        ]
    )
    assert verdict == "clean" and names == []


def test_a_genuine_red_is_blocked_and_named():
    verdict, names = MOG.decide_verdict(
        [_run("ci-pack-1", conclusion="failure"), _run("tier-gate", conclusion="timed_out")]
    )
    assert verdict == "blocked"
    assert "ci-pack-1 (failure)" in names and "tier-gate (timed_out)" in names


def test_a_head_with_no_check_runs_is_never_merged():
    """A paths-filtered docs-only PR is genuinely unproven — it needs a human."""
    assert MOG.decide_verdict([]) == ("unproven", [])


def test_a_head_carrying_only_the_spurious_check_is_also_unproven():
    """The count is taken AFTER the spurious filter on purpose: a literal
    zero-check-runs rule would merge this shape, which nothing has proven."""
    assert MOG.decide_verdict([_run("Workers Builds: macro", conclusion="failure")]) == (
        "unproven",
        [],
    )


def test_the_4779_shape_is_unproven_not_clean():
    """PR #4779's exact head, measured 2026-08-06 during the Actions major outage.

    The `pull_request` webhook was dropped, so ci.yml scheduled NO run and the head
    carried only these two checks. The spurious filter knows the Cloudflare X but
    not `Supabase Preview`, so `considered` was non-empty and the `unproven` branch
    above never fired; nothing was pending, and `skipped` is in CLEAN_CONCLUSIONS,
    so `bad` was empty. This returned `clean` and the sweeper would have
    squash-merged a head with ZERO CI evidence.
    """
    assert MOG.decide_verdict(
        [
            {"name": "Supabase Preview", "status": "completed", "conclusion": "skipped"},
            {"name": "Workers Builds: macro", "status": "completed", "conclusion": "failure"},
        ]
    ) == ("unproven", [])


def test_an_all_skipped_head_is_unproven_whatever_the_integration_is_called():
    """The rule is an affirmative pass, NOT a longer list of names to ignore.

    Widening `is_spurious_check` would have fixed #4779 and lost to the next
    integration someone installs, so no third-party name appears here.
    """
    assert MOG.decide_verdict(
        [_run("Some Future Preview", conclusion="skipped"), _run("inert", conclusion="neutral")]
    ) == ("unproven", [])


def test_one_success_beside_a_skipped_pack_still_merges():
    """The boundary the affirmative-pass rule must not cross.

    An ordinary path-filtered PR — one pack ran and passed, another skipped on its
    `paths:` filter — is genuinely proven and must stay mergeable. `skipped` keeps
    its place in CLEAN_CONCLUSIONS; it just no longer PROVES anything by itself.
    """
    assert MOG.decide_verdict(
        [_run("ci-pack-1", conclusion="success"), _run("ci-pack-2", conclusion="skipped")]
    ) == ("clean", [])


def test_a_pending_pack_beside_a_skip_waits_rather_than_reading_unproven():
    """Ordering: the affirmative-pass rule sits BELOW the pending branch.

    Above it, a head whose real packs are merely still running would be annotated
    "nothing proves it — the sweeper will never merge it", which is both wrong and
    a noisy notice on every sweep of a perfectly healthy PR.
    """
    verdict, names = MOG.decide_verdict(
        [_run("Supabase Preview", conclusion="skipped"), _run("ci-pack-1", "in_progress")]
    )
    assert verdict == "pending"
    assert names == ["ci-pack-1"]


def test_a_red_beside_a_skip_is_still_named_as_blocked():
    """Ordering: the affirmative-pass rule sits BELOW the blocked branch too.

    This head has no success either, but reporting it as `unproven` would swallow
    the red — `blocked` names the offender and posts the explanatory comment.
    """
    verdict, names = MOG.decide_verdict(
        [_run("Supabase Preview", conclusion="skipped"), _run("ci-pack-1", conclusion="failure")]
    )
    assert verdict == "blocked"
    assert names == ["ci-pack-1 (failure)"]


# --- the DYNAMIC pack matrix (Wave B) -----------------------------------------
#
# ci.yml stopped launching a fixed `ci-pack-0..11` on every head. `ci-plan` now
# computes the pack plan once and publishes a matrix; `ci-pack` carries
# `needs.ci-plan.outputs.has_work == 'true'` on top of its old `action != 'closed'`
# fence, so a PR may publish ANY SUBSET of the twelve pack names — including none at
# all — while main's `workflow_dispatch` baseline passes no `--changed-from` and so
# still publishes all twelve. `ci-gate` is the one name published on every non-closed
# event, and it is what makes the whole thing safe here.
#
# This shifted the ground under `decide_verdict` WITHOUT changing a line of it: the
# function has always been name-agnostic, so nothing in it enumerates pack names or
# counts them. That is precisely why these pins exist. The dangerous edit is not one
# that breaks a pack name; it is a future "the sweeper should require the full pack
# set" hardening, which would read as a tightening and would silently make every
# path-scoped PR permanently unmergeable. The six shapes below are the whole
# interface the sweeper now depends on, asserted against the pure function.


def test_a_no_work_pr_head_is_proven_by_the_plan_and_the_gate():
    """The shape Wave B invented: a PR the planner proved needs NO pack work.

    `ci-plan` succeeds, proves the changed paths own no legacy job, and emits
    `has_work=false`; `ci-pack` never launches (GitHub reports the skipped matrix
    job); `ci-gate` takes the no-work exit-0 branch and succeeds. Two real successes,
    so the affirmative-pass rule (#4779) is satisfied by `ci-plan`/`ci-gate` rather
    than by a pack — which is the entire reason `ci-gate` is required to publish on
    every non-closed event. Were it allowed to be absent, this head would carry one
    success and one skip today and could be argued down to `unproven` tomorrow, and
    the no-work PR — the fast path the whole conversion exists to create — would be
    the one shape that can never merge.
    """
    assert MOG.decide_verdict(
        [
            _run("ci-plan", conclusion="success"),
            _run("ci-pack", conclusion="skipped"),
            _run("ci-gate", conclusion="success"),
        ]
    ) == ("clean", [])


def test_a_head_carrying_only_the_plan_and_the_gate_is_clean():
    """The same no-work PR when GitHub publishes no check for the skipped matrix.

    A `strategy.matrix` that resolves to zero entries does not always leave a named
    `ci-pack` check behind — an `if:`-gated job with an empty matrix can simply not
    appear. So the no-work head must read `clean` on the two names alone, with no
    third check to lean on. Split from the test above deliberately: if the verdict
    ever came to depend on a skipped pack being PRESENT, that test would still pass
    and this one would red, which is the correct place for the failure to land.
    """
    assert MOG.decide_verdict(
        [_run("ci-plan", conclusion="success"), _run("ci-gate", conclusion="success")]
    ) == ("clean", [])


def test_a_selected_pack_red_blocks_and_names_the_pack_and_the_gate():
    """A red in the dynamic matrix must stay a red, and stay DIAGNOSABLE.

    `ci-gate` aggregates — it reports `failure` whenever any selected pack did not
    succeed — but aggregation must not cost the per-pack name. `merge-blocked`'s
    one-shot comment quotes this list, and "ci-gate (failure)" alone would tell the
    session nothing about WHICH pack to look at, on a workflow whose packs are
    rebalanced by weight and therefore not stable across commits (`ci-pack-N` is not
    a stable job identity). Directive §6.8: prefer ADDING `ci-gate` to the proof
    interpretation over deleting the per-pack diagnostics.
    """
    verdict, names = MOG.decide_verdict(
        [
            _run("ci-plan", conclusion="success"),
            _run("ci-pack-5", conclusion="success"),
            _run("ci-pack-9", conclusion="failure"),
            _run("ci-gate", conclusion="failure"),
        ]
    )
    assert verdict == "blocked"
    assert "ci-pack-9 (failure)" in names, "the failing pack must stay nameable"
    assert "ci-gate (failure)" in names, "the aggregate must stay visible too"


def test_a_subset_of_packs_is_clean_because_an_unselected_pack_is_not_missing():
    """The load-bearing consequence: a name that never launched is not a gap.

    Under the static matrix every head carried all twelve packs, so "absent" and
    "unproven" were never distinguishable and nothing had to decide between them.
    Under the dynamic matrix a scoped PR publishes only the packs its changed paths
    selected — here `ci-pack-3` and `ci-pack-7` — and the other ten names exist
    nowhere on the head. `decide_verdict` reads the runs that ARE there and holds no
    expected-name list, so this reads `clean`. A future "require the full set" rule
    would invert that into a permanent block on every scoped PR while looking, in
    review, like a tightening of the merge gate.
    """
    assert MOG.decide_verdict(
        [
            _run("ci-plan", conclusion="success"),
            _run("ci-pack-3", conclusion="success"),
            _run("ci-pack-7", conclusion="success"),
            _run("ci-gate", conclusion="success"),
        ]
    ) == ("clean", [])


def test_a_skipped_plan_and_gate_is_unproven_not_clean():
    """#4779 survives the conversion: `skipped` is still not a pass.

    The new names do not get a pass the old ones never had. A `closed` event skips
    every job in ci.yml, and an outage or a dropped webhook can leave the same
    shape — two named checks, both `skipped`, neither one evidence of anything. The
    spurious filter does not know `ci-plan` or `ci-gate`, so `considered` is
    non-empty and the zero-checks branch never fires; nothing is pending; `skipped`
    is in CLEAN_CONCLUSIONS so `bad` is empty. Only the affirmative-pass rule stands
    between this head and a squash-merge on zero CI evidence — which is exactly the
    outcome #4779 measured. Deleting that rule makes THIS test red.
    """
    assert MOG.decide_verdict(
        [_run("ci-plan", conclusion="skipped"), _run("ci-gate", conclusion="skipped")]
    ) == ("unproven", [])


@pytest.mark.parametrize("conclusion", ["cancelled", "stale"])
def test_superseded_checks_are_incomplete_never_accused(conclusion):
    assert MOG.decide_verdict(
        [_run("ci-pack-0", conclusion=conclusion)]
    ) == ("incomplete", ["ci-pack-0"])


@pytest.mark.parametrize("conclusion", ["cancelled", "stale", "skipped", "neutral"])
def test_non_success_proof_anchors_are_incomplete_not_red(conclusion):
    runs = _required_proof_runs()
    runs[0]["conclusion"] = conclusion
    verdict, names = MOG.proof_anchor_verdict(runs)
    assert verdict == "incomplete"
    assert runs[0]["name"] in names


# --- the sweep itself, with HTTP mocked ---------------------------------------


def _fake_api(
    monkeypatch,
    *,
    check_pages,
    merge_status=200,
    update_status=422,
    update_message="merge conflict between base and head",
    pull_payload=None,
    pull_status=200,
    main_commits=((BEFORE_THE_PROOF, ["data/nightly.json"]),),
    pr_files=("engine/signal_quality.py",),
    compare_files=None,
    compare_status=200,
    compare_base_sha=None,
    compare_merge_base_sha=None,
    pull_read_sequence=None,
):
    """Route every `_request` call by method+URL and record what was sent.

    `update_status` defaults to 422 — GitHub's "I cannot fast-forward this"
    answer — so a test that does not opt in keeps the old behaviour: a refused
    merge falls through to `merge-blocked`.

    `pull_payload` is what a re-read of the pull request itself returns. It
    defaults to `{}` — an open, unmerged pull request — so the `already_settled`
    guard stays inert for every test that is not about the concurrent-sweep race.

    `main_commits` / `pr_files` feed the tested-surface gate through the SAME
    `_request` seam production uses, so `ProofFreshness.build`, `files_of` and
    `pull_files` are exercised rather than stubbed. The synthetic proof-base SHA is
    listed immediately behind them; the default commit is a pipeline bake, so a test
    that is not about staleness keeps the neutral outcome.

    `compare_files` / `compare_status` answer the pre-merge live `base...head`
    compare (the clobbered-head invariant). The default MIRRORS `pr_files` — a
    live diff carrying the same real changes as the pull request's files view —
    so every test that is not about the invariant keeps its old outcome; a
    clobbered/empty head is staged with `compare_files=()`. The invariant judges
    the compare ALONE (the files view recomputes against a clobbered head, so a
    live-vs-view disagreement never occurs in practice — measured 2026-08-09).
    """
    calls: list[tuple[str, str, dict | None]] = []
    shas = [f"{index + 1:040d}" for index, _ in enumerate(main_commits)]
    pull_reads = 0
    # Most sweep tests are about a gate *after* repository proof admission and
    # historically used one representative pack.  Production now requires the
    # complete ci/fences anchor set; fill that neutral prerequisite here while
    # dedicated proof-anchor tests call the pure helpers directly.
    normalized_pages = {}
    for page, raw in check_pages.items():
        answer = dict(raw)
        runs = [dict(run) for run in (answer.get("check_runs") or [])]
        template = next(
            (run for run in runs if str(run.get("name") or "").startswith("ci-pack-")),
            None,
        )
        if template is not None:
            present = {str(run.get("name") or "") for run in runs}
            for name in sorted(MOG.REQUIRED_CI_ANCHORS | {MOG.REQUIRED_FENCE_ANCHOR}):
                if name in present:
                    continue
                anchor = dict(template)
                anchor.update(
                    {"name": name, "status": "completed", "conclusion": "success"}
                )
                runs.append(anchor)
        answer["check_runs"] = runs
        answer["total_count"] = max(int(answer.get("total_count") or 0), len(runs))
        normalized_pages[page] = answer

    def fake_request(method, url, token, payload=None):
        nonlocal pull_reads
        calls.append((method, url, payload))
        if "/check-runs" in url:
            page = int(url.rsplit("page=", 1)[1].split("&")[0])
            return 200, normalized_pages.get(
                page, {"total_count": 0, "check_runs": []}
            )
        if "/compare/" in url:
            if compare_status >= 400:
                return compare_status, {"message": "Server Error"}
            names = pr_files if compare_files is None else compare_files
            base_sha = compare_base_sha if compare_base_sha is not None else shas[0]
            answer = {
                "base_commit": {"sha": base_sha},
                "files": [{"filename": name} for name in names],
            }
            if compare_merge_base_sha is not None:
                answer["merge_base_commit"] = {"sha": compare_merge_base_sha}
            return 200, answer
        if "/commits?" in url:
            return 200, [
                {"sha": sha, "commit": {"committer": {"date": iso}}}
                for sha, (iso, _files) in zip(shas, main_commits)
            ] + [
                {
                    "sha": PROOF_BASE_SHA,
                    "commit": {"committer": {"date": "1970-01-01T00:00:00Z"}},
                }
            ]
        if "/commits/" in url:
            sha = url.rsplit("/", 1)[1]
            files = dict(
                zip(shas, [names for _iso, names in main_commits])
            ).get(sha, [] if sha == PROOF_BASE_SHA else None)
            if files is None:
                raise AssertionError(url)
            return 200, {"files": [{"filename": name} for name in files]}
        if method == "GET" and "/git/ref/heads/main" in url:
            return 200, {"object": {"sha": shas[0]}}
        if url.endswith("/update-branch"):
            if update_status in {200, 202}:
                return update_status, {"message": "Updating pull request branch."}
            return update_status, {"message": update_message}
        if url.endswith("/merge"):
            if merge_status == 200:
                return 200, {"sha": "c" * 40, "merged": True}
            return merge_status, {"message": "Pull Request is not mergeable"}
        if method == "GET" and "/files?" in url and "/pulls/" in url:
            page = int(url.rsplit("page=", 1)[1].split("&")[0])
            if page > 1:
                return 200, []
            return 200, [{"filename": name} for name in pr_files]
        if method == "GET" and "/pulls/" in url:
            pull_reads += 1
            if pull_read_sequence:
                seq_status, seq_payload = pull_read_sequence[
                    min(pull_reads - 1, len(pull_read_sequence) - 1)
                ]
                if seq_status >= 400:
                    return seq_status, seq_payload
                number = int(url.rstrip("/").rsplit("/", 1)[1])
                live = _pull(number)
                live.update({"state": "open", "draft": False, "merged": False})
                live.update(dict(seq_payload or {}))
                return seq_status, live
            if pull_status >= 400:
                return pull_status, None
            number = int(url.rstrip("/").rsplit("/", 1)[1])
            live = _pull(number)
            live.update({"state": "open", "draft": False, "merged": False})
            live.update(dict(pull_payload or {}))
            return pull_status, live
        return 200, {}

    monkeypatch.setattr(MOG, "_request", fake_request)
    return calls


def _pull(number=4242, labels=("merge-on-green",)) -> dict:
    return {
        "number": number,
        "state": "open",
        "draft": False,
        "head": {
            "sha": "a" * 40,
            "ref": "claude/feature",
            "repo": {"full_name": "acme/widgets"},
        },
        "base": {"ref": "main"},
        "labels": [{"name": name} for name in labels],
    }


def _authorized_budget(max_refreshes=MOG.MAX_REFRESHES_PER_SWEEP):
    budget = MOG.SweepBudget("read", max_refreshes=max_refreshes)
    budget.refresh_authorized = True
    return budget


def test_a_clean_pull_request_is_squash_merged(monkeypatch, capsys):
    calls = _fake_api(
        monkeypatch,
        check_pages={1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}},
    )
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "merged"
    merges = [call for call in calls if call[1].endswith("/merge")]
    assert len(merges) == 1
    assert merges[0][0] == "PUT" and merges[0][2] == {
        "merge_method": "squash",
        "sha": "a" * 40,
    }, "the merge must pin the exact head whose checks were judged"
    # The controller deliberately does not delete a branch by name after merging:
    # a fork/shared-name race could erase an unrelated base-repository ref.
    assert not any("git/refs/heads" in call[1] for call in calls)


def test_main_moving_after_the_freshness_snapshot_defers_the_merge(
    monkeypatch, capsys
):
    """The merge API's SHA fence covers the head, not the base branch."""
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [_run("ci-pack-1", conclusion="success")],
            }
        },
        compare_base_sha="b" * 40,
    )
    verdict = MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness()
    )
    assert verdict == "main-moved"
    assert not [call for call in calls if call[1].endswith("/merge")]
    out = capsys.readouterr().out
    assert "main moved from freshness snapshot" in out
    assert "left armed for a fresh snapshot" in out


def test_a_missing_live_base_sha_fails_closed_before_merge(monkeypatch):
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [_run("ci-pack-1", conclusion="success")],
            }
        },
        compare_base_sha="",
    )
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness()
    ) == "error"
    assert not [call for call in calls if call[1].endswith("/merge")]


@pytest.mark.parametrize("cleanup_name", ["clear_blocked"])
def test_post_merge_cleanup_failure_cannot_hide_the_accepted_merge(
    monkeypatch, capsys, cleanup_name
):
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [_run("ci-pack-1", conclusion="success")],
            }
        },
    )

    def fail_cleanup(*_a, **_k):
        raise ConnectionError("cleanup link dropped")

    monkeypatch.setattr(MOG, cleanup_name, fail_cleanup)
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness()
    ) == "merged"
    assert len([call for call in calls if call[1].endswith("/merge")]) == 1
    assert "Merge remains successful" in capsys.readouterr().out


def test_an_ambiguous_merge_response_rereads_the_pr_and_consumes_the_snapshot(
    monkeypatch, capsys
):
    def fake_request(method, url, token, payload=None):
        if "/check-runs" in url:
            return 200, {
                "total_count": 13,
                "check_runs": _required_proof_runs(),
            }
        if "/compare/" in url:
            return 200, {
                "base_commit": {"sha": DEFAULT_MAIN_SHA},
                "files": [{"filename": "engine/signal_quality.py"}],
            }
        if method == "GET" and "/git/ref/heads/main" in url:
            return 200, {"object": {"sha": DEFAULT_MAIN_SHA}}
        if method == "PUT" and url.endswith("/merge"):
            raise ConnectionError("response body truncated after write")
        if method == "GET" and url.endswith("/pulls/4242"):
            fake_request.pull_reads += 1
            if fake_request.pull_reads == 1:
                return 200, _pull()
            return 200, {"state": "closed", "merged": True}
        return 200, {}

    fake_request.pull_reads = 0

    monkeypatch.setattr(MOG, "_request", fake_request)
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness()
    ) == "already-merged"
    assert "already merged" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("pull_status", "pull_payload", "expected"),
    [
        (200, {"state": "closed", "merged": True}, "already-merged"),
        (200, {"state": "open", "merged": False}, "merge-unknown"),
        (503, None, "merge-unknown"),
    ],
)
def test_a_server_error_after_merge_is_ambiguous_and_consumes_the_snapshot(
    monkeypatch, capsys, pull_status, pull_payload, expected
):
    """A gateway can answer 5xx after GitHub accepted the irreversible write."""
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [_run("ci-pack-1", conclusion="success")],
            }
        },
        merge_status=502,
        pull_read_sequence=[(200, {}), (pull_status, pull_payload)],
    )
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness()
    ) == expected
    assert len([call for call in calls if call[1].endswith("/merge")]) == 1
    out = capsys.readouterr().out
    assert "ambiguous" in out and "snapshot" in out


def test_a_pending_pull_request_writes_nothing(monkeypatch, capsys):
    calls = _fake_api(
        monkeypatch,
        check_pages={1: {"total_count": 1, "check_runs": [_run("ci-pack-1", "in_progress")]}},
    )
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "pending"
    assert [call for call in calls if call[0] != "GET"] == [], "waiting must be side-effect free"


def test_a_red_pull_request_is_labeled_and_commented_exactly_once(monkeypatch, capsys):
    """The sweep runs every 10 minutes; commenting on every pass would post ~144
    comments a day. The comment rides ONLY the label transition."""
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages)
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "blocked"
    posts = [call for call in calls if call[0] == "POST"]
    assert any(call[1].endswith("/labels") for call in posts)
    comments = [call for call in posts if call[1].endswith("/comments")]
    assert len(comments) == 1
    assert "ci-pack-1 (failure)" in comments[0][2]["body"]

    # Second pass, with the label already present: no label call, no comment.
    calls = _fake_api(
        monkeypatch,
        check_pages=pages,
        pull_payload={
            "labels": [
                {"name": MOG.MERGE_ON_GREEN_LABEL},
                {"name": MOG.MERGE_BLOCKED_LABEL},
            ]
        },
    )
    already = _pull(labels=("merge-on-green", "merge-blocked"))
    assert MOG.sweep_pull("acme/widgets", already, "read", "write", _freshness()) == "blocked"
    assert [call for call in calls if call[0] == "POST"] == [], "must never re-comment"


def test_an_unproven_head_is_never_merged_and_says_so(monkeypatch, capsys):
    calls = _fake_api(monkeypatch, check_pages={1: {"total_count": 0, "check_runs": []}})
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "unproven"
    assert [call for call in calls if call[0] != "GET"] == []
    out = capsys.readouterr().out
    assert "::notice" in out and "manually" in out


def test_a_real_conflict_is_reported_as_merge_blocked(monkeypatch, capsys):
    """Clean checks, refused merge, and GitHub cannot fast-forward it either: a
    genuine content conflict, which needs a human rather than a retry loop."""
    calls = _fake_api(
        monkeypatch,
        check_pages={1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}},
        merge_status=409,
        update_status=422,
    )
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(),
        budget=_authorized_budget(),
    ) == "conflict"
    assert any(call[1].endswith("/update-branch") for call in calls), (
        "the sweeper must TRY to clear a stale base before labelling it blocked"
    )
    comments = [call for call in calls if call[0] == "POST" and call[1].endswith("/comments")]
    assert len(comments) == 1 and "not mergeable" in comments[0][2]["body"]
    assert "REAL content conflict" in comments[0][2]["body"], (
        "the comment must say the stale-base case was already ruled out"
    )


def test_a_head_that_moves_during_update_is_retried_not_called_a_conflict(
    monkeypatch, capsys
):
    """A 422 with a different live head means the expected-SHA fence worked."""
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [_run("ci-pack-1", conclusion="success")],
            }
        },
        merge_status=409,
        update_status=422,
        pull_payload={"state": "open", "head": {"sha": "b" * 40}},
    )
    pull = _pull(labels=("merge-on-green", "merge-blocked"))
    assert MOG.sweep_pull(
        "acme/widgets", pull, "read", "write", _freshness()
    ) == "head-moved"
    assert not [call for call in calls if call[0] == "POST"], (
        "the new head must not inherit a stale conflict label or comment"
    )
    assert any(
        call[0] == "DELETE" and "labels/merge-blocked" in call[1] for call in calls
    ), "a stale blocker must be cleared when another updater advances the head"
    assert "authorization changed (head-moved)" in capsys.readouterr().out


def test_the_definitive_expected_SHA_mismatch_wins_over_a_failed_reread(monkeypatch):
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [_run("ci-pack-1", conclusion="success")],
            }
        },
        merge_status=409,
        update_status=422,
        update_message="expected head sha didn't match current head ref",
        # pre-merge authorization + refused-merge settlement + pre-update
        # authorization all see the still-open judged head; the definitive 422
        # message itself then proves the expected-SHA race.
        pull_read_sequence=[(200, {}), (200, {}), (200, {})],
    )
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(),
        budget=_authorized_budget(),
    ) == "head-moved"
    assert not [call for call in calls if call[0] == "POST"]


def test_an_update_API_failure_is_retried_not_called_a_content_conflict(monkeypatch):
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [_run("ci-pack-1", conclusion="success")],
            }
        },
        merge_status=409,
        update_status=500,
        update_message="Server Error",
    )
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(),
        budget=_authorized_budget(),
    ) == "update-retry"
    assert not [call for call in calls if call[0] == "POST"]


def test_an_unknown_422_on_the_same_head_is_retried_not_called_a_conflict(monkeypatch):
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [_run("ci-pack-1", conclusion="success")],
            }
        },
        merge_status=409,
        update_status=422,
        update_message="Validation Failed",
        pull_payload={
            "state": "open",
            "head": {"sha": "a" * 40},
            "mergeable_state": "unknown",
        },
    )
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(),
        budget=_authorized_budget(),
    ) == "update-retry"
    assert not [call for call in calls if call[0] == "POST"]


def test_a_pull_request_another_sweep_already_merged_is_never_labeled_blocked(
    monkeypatch, capsys
):
    """The race the removed concurrency group was supposed to prevent — and the
    only place overlapping sweeps are actually unsafe.

    Full sweeps now coalesce on a dedicated runner, but pre-deploy/out-of-band runs
    can still race. Two actors can therefore both judge PR #4242 clean; one wins
    the squash merge and the other is answered 405/409 by GitHub — the SAME status
    a stale base or a real conflict produces.

    Without `already_settled`, the loser reads that as a conflict: it calls
    update-branch (422 on a merged PR), then labels a SUCCESSFULLY MERGED pull
    request `merge-blocked` and comments "not merging" on it. Because
    `mark_blocked` posts its comment only on the label transition, that false
    comment is the one that sticks. This is the labeled-but-unmerged hazard the
    old comment warned about, wearing the opposite face.
    """
    calls = _fake_api(
        monkeypatch,
        check_pages={1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}},
        merge_status=405,
        update_status=422,
        pull_payload={"merged": True, "state": "closed"},
    )
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "already-merged"

    assert not any(call[1].endswith("/update-branch") for call in calls), (
        "a merged pull request must never be handed to update-branch"
    )
    posts = [call for call in calls if call[0] == "POST"]
    assert not any(call[1].endswith("/labels") for call in posts), (
        "labelling a merged pull request `merge-blocked` is the exact hazard"
    )
    assert not any(call[1].endswith("/comments") for call in posts), (
        "and the one-shot comment would make the falsehood permanent"
    )
    # A `::` annotation is dropped by GitHub unless it STARTS its line (house law),
    # so this is asserted per line rather than on the whole stream — the sweeper also
    # prints the tested-surface verdict that let this pull request reach the merge.
    assert any(
        line.startswith("::notice") and "authorization changed" in line
        for line in capsys.readouterr().out.splitlines()
    )


def test_the_concurrent_sweep_guard_fails_closed_on_an_unreadable_pull_request(
    monkeypatch, capsys
):
    """A guard that cannot read must not invent an answer. When the re-read fails,
    the sweeper falls back to exactly the behaviour that shipped before the guard
    existed — noisier, but it can never merge anything or bury a real conflict."""

    calls = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url))
        if "/check-runs" in url:
            return 200, {
                "total_count": 13,
                "check_runs": _required_proof_runs(),
            }
        if "/compare/" in url:
            # A live diff that agrees with the PR view, so the clobbered-head
            # invariant passes and the test stays about the settled-guard read.
            return 200, {
                "base_commit": {"sha": DEFAULT_MAIN_SHA},
                "files": [{"filename": "engine/signal_quality.py"}],
            }
        if url.endswith("/merge"):
            return 409, {"message": "Pull Request is not mergeable"}
        if url.endswith("/update-branch"):
            return 422, {"message": "merge conflict between base and head"}
        if method == "GET" and "/pulls/" in url:
            return 502, None  # GitHub blipped
        return 200, {}

    monkeypatch.setattr(MOG, "_request", fake_request)
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness()
    ) == "authorization-unreadable"
    assert not [call for call in calls if call[0] != "GET"]


def test_a_stale_base_is_updated_instead_of_blocked(monkeypatch, capsys):
    """The treadmill fix.

    main takes ~19 commits in 3 hours and a pack run takes ~30 minutes, so a pull
    request routinely goes green and is stale before its own proof finishes. That
    used to end in `merge-blocked` and wait for a human to rebase by hand — which
    is how a one-hour-old pull request becomes a three-day-old one. The sweeper
    now merges main into the head itself.
    """
    calls = _fake_api(
        monkeypatch,
        check_pages={1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}},
        merge_status=409,
        update_status=202,
    )
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(),
        budget=_authorized_budget(),
    ) == "updated"

    updates = [call for call in calls if call[1].endswith("/update-branch")]
    assert len(updates) == 1 and updates[0][0] == "PUT"
    assert updates[0][2] == {"expected_head_sha": "a" * 40}, (
        "update-branch must pin the head it judged, or it can clobber a head that "
        "moved again between the check read and this call"
    )

    # Nothing may merge on this pass: the updated head is unproven until its
    # fresh checks conclude.
    assert [c for c in calls if c[1].endswith("/merge") and c[0] == "PUT"][1:] == []
    posts = [call for call in calls if call[0] == "POST"]
    assert not any(call[1].endswith("/comments") for call in posts), "no comment on progress"
    assert not any(call[1].endswith("/labels") for call in posts), "must not label blocked"


def test_an_updated_branch_clears_a_stale_merge_blocked_label(monkeypatch, capsys):
    """A branch that is moving again must not keep wearing `merge-blocked` from an
    earlier pass, or the label stops meaning anything."""
    calls = _fake_api(
        monkeypatch,
        check_pages={1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}},
        merge_status=409,
        update_status=202,
        pull_payload={
            "labels": [
                {"name": MOG.MERGE_ON_GREEN_LABEL},
                {"name": MOG.MERGE_BLOCKED_LABEL},
            ]
        },
    )
    already = _pull(labels=("merge-on-green", "merge-blocked"))
    assert MOG.sweep_pull(
        "acme/widgets", already, "read", "write", _freshness(),
        budget=_authorized_budget(),
    ) == "updated"
    assert any(
        call[0] == "DELETE" and "labels/merge-blocked" in call[1] for call in calls
    ), "the stale merge-blocked label must be dropped once the branch moves again"


@pytest.mark.parametrize(
    "pr_files",
    [
        # The MEASURED post-clobber shape: GitHub recomputes the PR's files view
        # against the clobbered head, so it reads 0 files too. An earlier draft of
        # the invariant keyed on "live diff empty while the files view still names
        # files" — this parameter is the proof that shape is vacuous, pinned so
        # nobody reintroduces the comparison.
        (),
        # And a lagging/stale files view changes nothing: the refusal must not
        # depend on the PR view in either direction.
        ("engine/cn_limit_alpha.py", "tests/test_cn_limit_alpha.py"),
    ],
    ids=["files-view-recomputed-to-zero", "files-view-lagging"],
)
def test_an_armed_head_with_an_empty_live_diff_is_refused_whatever_the_pr_view_says(
    monkeypatch, capsys, pr_files
):
    """The 2026-08-09 phantom merges (#5055 #5061 #5078 #5091), pinned.

    Four armed heads sat through a day of update-branch/refresh cycles and came
    out clobbered to content-identical-with-main (#5055's head at merge,
    6f9a7f63bfb, contained none of its files). Their checks were honestly green —
    they tested main's own content — so the sweeper squash-merged EMPTY diffs
    (455130e4faa e7564f0fc7b db48f1d6aa9 0ae4270c76a) and the PRs read MERGED
    while zero files landed. The recovery lane measured that GitHub's own files
    view had recomputed to 0 files for every one of them, so the refusal is
    UNCONDITIONAL on the live diff's emptiness: no legitimate armed pull request
    has an empty diff — merging one records MERGED while delivering nothing.
    Refuse, label, explain once, name the head SHA — never merge.
    """
    calls = _fake_api(
        monkeypatch,
        check_pages={1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}},
        compare_files=(),
        pr_files=pr_files,
    )
    verdict = MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness())
    assert verdict == "empty-diff"
    assert not any(call[0] == "PUT" and call[1].endswith("/merge") for call in calls), (
        "the squash merge must never be issued on an empty diff — an empty merge "
        "that reads MERGED is the incident itself, not a near miss"
    )
    posts = [call for call in calls if call[0] == "POST"]
    assert any(call[1].endswith("/labels") for call in posts), "must label merge-blocked"
    comments = [call for call in posts if call[1].endswith("/comments")]
    assert len(comments) == 1
    body = comments[0][2]["body"]
    assert "a" * 40 in body, (
        "the comment must name the head SHA at refusal time — it is how the owner "
        "finds the good pre-clobber commit to restore"
    )
    assert "CLOBBERED" in body and "not merging" in body
    assert "close it" in body, (
        "and it must route the genuinely-empty/superseded shape to CLOSE, because "
        "the sweeper cannot tell that apart from a clobber and must not pretend to"
    )


def test_the_empty_diff_refusal_comments_exactly_once(monkeypatch, capsys):
    """A clobbered head stays clobbered until a human restores it, and the sweep
    runs every ~10 minutes — commenting per pass would post ~144 comments a day.
    The comment rides ONLY the label transition, like every other refusal."""
    staged = dict(
        check_pages={1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}},
        compare_files=(),
        pr_files=(),
    )
    calls = _fake_api(
        monkeypatch,
        **staged,
        pull_payload={
            "labels": [
                {"name": MOG.MERGE_ON_GREEN_LABEL},
                {"name": MOG.MERGE_BLOCKED_LABEL},
            ]
        },
    )
    already = _pull(labels=("merge-on-green", "merge-blocked"))
    assert (
        MOG.sweep_pull("acme/widgets", already, "read", "write", _freshness())
        == "empty-diff"
    )
    assert [call for call in calls if call[0] == "POST"] == [], "must never re-comment"
    assert any(
        line.startswith("::warning") and "No new marker" in line
        for line in capsys.readouterr().out.splitlines()
    ), (
        "the log line moved off 'Already labeled merge-blocked' (2026-08-11): "
        "`mark_blocked` now returns False for a FAILED write as well as for an "
        "already-labeled pull request, so this line may no longer claim to know "
        "which of the two happened — the write failure emits its own `::error`"
    )


def test_a_non_empty_live_diff_keeps_the_existing_merge_path(monkeypatch, capsys):
    """The other half of the matrix: an armed pull request whose live diff carries
    real changes merges exactly as before — the invariant is one extra read, never
    a behaviour change for healthy work. (Every `_fake_api` merge test also proves
    this by construction: the compare default mirrors `pr_files`.)"""
    calls = _fake_api(
        monkeypatch,
        check_pages={1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}},
        compare_files=("engine/cn_limit_alpha.py",),
    )
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "merged"
    merges = [call for call in calls if call[0] == "PUT" and call[1].endswith("/merge")]
    assert len(merges) == 1
    assert [call for call in calls if call[0] == "POST"] == [], "no label, no comment"


def test_an_unreadable_live_compare_fails_closed_without_accusing(monkeypatch, capsys):
    """A broken read must never become permission to merge — but a blip is not
    evidence of a clobber either, and `mark_blocked`'s comment is one-shot, so a
    false accusation would be the one that sticks. Armed, unlabeled, retried."""
    calls = _fake_api(
        monkeypatch,
        check_pages={1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}},
        compare_status=502,
    )
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "error"
    assert not any(call[0] == "PUT" and call[1].endswith("/merge") for call in calls), (
        "no merge on partial information"
    )
    assert [call for call in calls if call[0] == "POST"] == [], "and no accusation"
    assert any(
        line.startswith("::warning") and "clobbered-head invariant cannot run" in line
        for line in capsys.readouterr().out.splitlines()
    )


def test_the_check_listing_pages_past_the_first_hundred(monkeypatch, capsys):
    """The guard's fail-closed rule, mirrored: PR #3629's head carried 101 runs, so
    a single per_page=100 call could hide a red on page two."""
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 101,
                "check_runs": [_run(f"pure-{index}", conclusion="success") for index in range(100)],
            },
            2: {"total_count": 101, "check_runs": [_run("ci-pack-1", conclusion="failure")]},
        },
    )
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "blocked"
    pages = [call[1] for call in calls if "/check-runs" in call[1]]
    assert len(pages) == 2, "both pages must be fetched"


def test_annotations_start_the_line(capsys):
    """House law: a `::warning` that does not START the line is silently dropped by
    GitHub, so it must never go through a logger."""
    MOG._annotate("warning", "merge-on-green", "something to say")
    for line in capsys.readouterr().out.splitlines():
        if line.strip():
            assert line.startswith("::"), line


def test_labeled_pulls_filters_client_side(monkeypatch):
    """The pulls endpoint has no label parameter; the filter must not be forgotten."""
    def fake_request(method, url, token, payload=None):
        return 200, [_pull(1), _pull(2, labels=("enhancement",)), _pull(3)]

    monkeypatch.setattr(MOG, "_request", fake_request)
    assert [pull["number"] for pull in MOG.labeled_pulls("acme/widgets", "t")] == [1, 3]


def test_integration_baseline_accepts_a_green_ancestor_of_data_only_main(monkeypatch):
    baseline_sha = "b" * 40
    main_sha = "c" * 40

    def fake_request(method, url, token, payload=None):
        if "/actions/workflows/" in url:
            return 200, {
                "workflow_runs": [{
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": baseline_sha,
                    "html_url": "https://example.test/run/1",
                    "created_at": _baseline_stamp(0.1),
                }]
            }
        if "/git/ref/heads/main" in url:
            return 200, {"object": {"sha": main_sha}}
        if "/compare/" in url:
            return 200, {"status": "ahead"}
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", fake_request)
    state, detail = MOG.integration_baseline_state("acme/widgets", "read")
    assert state == "green"
    assert baseline_sha[:12] in detail


@pytest.mark.parametrize(
    ("status", "conclusion", "expected"),
    [
        # An in-flight run ALONE is `unproven`, not `pending`: with nothing concluded
        # in the window there is no evidence about main in either direction. This case
        # asserted `pending` until 2026-08-08. The rename matters because `pending` used
        # to mean "a run is in flight, so everything halts" — the rule that produced a
        # 100% block rate against a green main (see the in-flight tests below). Both
        # states are non-green and both still fail closed.
        ("in_progress", None, "unproven"),
        ("completed", "failure", "red"),
        # A lone cancelled run proves nothing either way: it is a superseded run,
        # not a broken main. Still non-green, so it still fails closed.
        ("completed", "cancelled", "unproven"),
    ],
)
def test_integration_baseline_fail_closes_non_green_runs(
    monkeypatch, status, conclusion, expected
):
    sha = "d" * 40

    def fake_request(method, url, token, payload=None):
        if "/actions/workflows/" in url:
            return 200, {
                "workflow_runs": [{
                    "status": status,
                    "conclusion": conclusion,
                    "head_sha": sha,
                    "html_url": "https://example.test/run/2",
                    "created_at": _baseline_stamp(0.1),
                }]
            }
        if "/git/ref/heads/main" in url:
            return 200, {"object": {"sha": sha}}
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", fake_request)
    assert MOG.integration_baseline_state("acme/widgets", "read")[0] == expected


def _baseline_runs(monkeypatch, runs, main_sha):
    """Serve `runs` newest-first from the workflow-runs endpoint."""
    calls = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url, payload))
        if "/actions/workflows/" in url:
            asked = int(url.rsplit("per_page=", 1)[1].split("&")[0])
            return 200, {"workflow_runs": runs[:asked]}
        if "/git/ref/heads/main" in url:
            return 200, {"object": {"sha": main_sha}}
        if "/compare/" in url:
            return 200, {"status": "ahead"}
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", fake_request)
    return calls


def _baseline_stamp(hours_old: float) -> str:
    """A GitHub-shaped `created_at` that many hours before now.

    RELATIVE to the wall clock on purpose: `BASELINE_MAX_AGE_HOURS` is measured
    against `datetime.now`, so a frozen literal would silently age past the bound and
    turn every green-expecting test in this file red at some future date.
    """
    when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_old)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _baseline_run(conclusion, sha, status="completed", hours_old: float = 0.1):
    return {
        "status": status,
        "conclusion": conclusion,
        "head_sha": sha,
        "html_url": f"https://example.test/run/{conclusion}",
        "created_at": _baseline_stamp(hours_old),
    }


def test_a_superseded_cancelled_run_does_not_latch_the_breaker(monkeypatch):
    """The 2026-08-05 outage: `integration-baseline.yml` cancels itself on every
    push to main (cancel-in-progress), so the newest run is routinely `cancelled`.
    Reading only that run held 49 armed PRs behind a red breaker for 8.5h while
    main was in fact green. The walk must fall through to the concluded proof."""
    green = "e" * 40
    _baseline_runs(
        monkeypatch,
        [_baseline_run("cancelled", "f" * 40), _baseline_run("cancelled", "0" * 40), _baseline_run("success", green)],
        main_sha=green,
    )
    state, detail = MOG.integration_baseline_state("acme/widgets", "read")
    assert state == "green"
    assert green[:12] in detail


def test_baseline_walk_reaches_a_fresh_green_below_twenty_five_noise_runs(
    monkeypatch,
):
    """The 20-run window made queue churn indistinguishable from no proof.

    The fixture honours ``per_page`` so this fails if either the named lookback or
    the request regresses below the observed 25 cancelled/in-flight prefix. The
    listing remains one bounded request; ancestry and freshness are still decided
    from the first non-cancelled run that actually concluded.
    """
    green = "7" * 40
    noise = [
        _baseline_run(
            "cancelled" if index % 2 == 0 else None,
            f"{index % 16:x}" * 40,
            status="completed" if index % 2 == 0 else "queued",
        )
        for index in range(25)
    ]
    calls = _baseline_runs(
        monkeypatch,
        [*noise, _baseline_run("success", green, hours_old=0.25)],
        main_sha=green,
    )

    state, detail = MOG.integration_baseline_state("acme/widgets", "read")

    assert state == "green"
    assert green[:12] in detail
    listings = [
        url
        for method, url, _payload in calls
        if method == "GET" and "/actions/workflows/" in url and "/runs?" in url
    ]
    assert len(listings) == 1, "the 100-run lookback must stay one bounded API request"
    assert f"per_page={MOG.INTEGRATION_BASELINE_RUN_LOOKBACK}" in listings[0]
    assert MOG.INTEGRATION_BASELINE_RUN_LOOKBACK == 100


def test_falling_through_cancelled_runs_still_stops_at_a_real_red(monkeypatch):
    """Fail-closed: skipping superseded runs must not skip a genuine failure."""
    sha = "a" * 40
    _baseline_runs(
        monkeypatch,
        [_baseline_run("cancelled", "b" * 40), _baseline_run("failure", sha), _baseline_run("success", "c" * 40)],
        main_sha=sha,
    )
    assert MOG.integration_baseline_state("acme/widgets", "read")[0] == "red"


def test_an_all_cancelled_window_is_unproven_not_green(monkeypatch):
    sha = "d" * 40
    _baseline_runs(
        monkeypatch, [_baseline_run("cancelled", sha), _baseline_run("cancelled", "e" * 40)], main_sha=sha
    )
    state, detail = MOG.integration_baseline_state("acme/widgets", "read")
    assert state == "unproven"
    assert "cancelled" in detail


@pytest.mark.parametrize(
    "in_flight", ["queued", "in_progress", "requested", "waiting", "pending"]
)
def test_an_in_flight_newest_run_does_not_block_a_concluded_green(monkeypatch, in_flight):
    """Replaces `test_an_in_flight_newest_run_outranks_an_older_green`, which asserted
    the exact defect this pins against (2026-08-08).

    The old rule read `runs[0]`'s status first and returned `pending` whenever it was
    not `completed`. That is the same category error #4638 fixed for `cancelled`: a run
    that has NOT CONCLUDED is no information. A concluded green is positive evidence
    about a real SHA; a queued run is the absence of evidence, and halting on absence
    is not fail-closed, it is fail-blind.

    Measured with main GREEN: the newest concluded baseline was `success` at 05:00:51Z
    with a `queued` run (05:31Z, waiting 75+ min on a saturated hosted pool) and a
    `pending` one (06:45Z) stacked on top, so the breaker said `pending`. Each of the
    last 8 successful sweeps then ended `25 baseline-blocked, 71 cap-deferred` — ZERO
    pull requests evaluated — for 8 merges in 24h against 43 PRs created.
    `integration-baseline.yml` fires on every source push to main and the wire/nightly
    lanes push every few minutes, so a baseline is almost always in flight: the old rule
    made "blocked" the steady state rather than the exception.
    """
    green = "a" * 40
    _baseline_runs(
        monkeypatch,
        [
            _baseline_run(None, "f" * 40, status=in_flight),
            _baseline_run("success", green),
        ],
        main_sha=green,
    )
    state, detail = MOG.integration_baseline_state("acme/widgets", "read")
    assert state == "green", f"an in-flight ({in_flight}) run must not outrank a green"
    assert green[:12] in detail, "the detail must name the run that was actually decided on"


@pytest.mark.parametrize("in_flight", ["queued", "in_progress"])
def test_an_in_flight_run_can_never_launder_a_red(monkeypatch, in_flight):
    """Fail-closed, unchanged: falling through an unconcluded run must stop at the
    newest run that DID conclude, even when a green sits behind it. A pending baseline
    is not a reason to merge across a broken main."""
    red = "b" * 40
    _baseline_runs(
        monkeypatch,
        [
            _baseline_run(None, "c" * 40, status=in_flight),
            _baseline_run("failure", red),
            _baseline_run("success", "d" * 40),
        ],
        main_sha=red,
    )
    state, detail = MOG.integration_baseline_state("acme/widgets", "read")
    assert state == "red"
    assert red[:12] in detail


def test_a_green_older_than_the_freshness_bound_is_not_green(monkeypatch):
    """The bound that keeps the fix above honest. Skipping in-flight runs means the
    walk can reach arbitrarily far back, and "main was proven six hours and two hundred
    commits ago" is a different claim from "main is proven". Past
    `BASELINE_MAX_AGE_HOURS` the proof yields `pending` — WITH ITS AGE, so the sweep log
    distinguishes this cause from every other non-green state."""
    sha = "e" * 40
    _baseline_runs(
        monkeypatch,
        [_baseline_run("success", sha, hours_old=MOG.BASELINE_MAX_AGE_HOURS + 0.5)],
        main_sha=sha,
    )
    state, detail = MOG.integration_baseline_state("acme/widgets", "read")
    assert state == "pending"
    assert "old" in detail and str(MOG.BASELINE_MAX_AGE_HOURS) in detail, detail

    _baseline_runs(
        monkeypatch,
        [_baseline_run("success", sha, hours_old=MOG.BASELINE_MAX_AGE_HOURS - 0.5)],
        main_sha=sha,
    )
    assert MOG.integration_baseline_state("acme/widgets", "read")[0] == "green", (
        "a proof INSIDE the bound must still merge — the bound is a staleness cap, "
        "not a second reason to block"
    )


def test_an_undated_green_baseline_fails_closed(monkeypatch):
    """A proof whose freshness cannot be established has not been shown fresh. Three
    timestamp fields are tried before it comes to this, so reaching it means the API
    contract changed — which must show up as a named, diagnosable pause rather than as
    merges authorised on an unknown date."""
    sha = "0" * 40
    undated = _baseline_run("success", sha)
    undated.pop("created_at")
    _baseline_runs(monkeypatch, [undated], main_sha=sha)
    state, detail = MOG.integration_baseline_state("acme/widgets", "read")
    assert state == "pending"
    assert "dated" in detail, detail


@pytest.mark.parametrize("field", ["created_at", "run_started_at", "updated_at"])
def test_any_of_the_three_run_stamps_can_date_a_baseline(monkeypatch, field):
    """The fallbacks are the reason a renamed field cannot re-halt this lane."""
    sha = "1" * 40
    run = _baseline_run("success", sha)
    run.pop("created_at")
    run[field] = _baseline_stamp(0.5)
    _baseline_runs(monkeypatch, [run], main_sha=sha)
    assert MOG.integration_baseline_state("acme/widgets", "read")[0] == "green"


def test_a_window_with_nothing_concluded_is_unproven_and_says_what_it_saw(monkeypatch):
    """The in-flight fall-through must not invent a proof out of runs that have none.
    The detail separates in-flight from cancelled because they are different diagnoses:
    the first is a saturated queue, the second is concurrency superseding proofs."""
    sha = "2" * 40
    _baseline_runs(
        monkeypatch,
        [
            _baseline_run(None, sha, status="queued"),
            _baseline_run(None, "3" * 40, status="in_progress"),
            _baseline_run("cancelled", "4" * 40),
        ],
        main_sha=sha,
    )
    state, detail = MOG.integration_baseline_state("acme/widgets", "read")
    assert state == "unproven"
    assert "2 still in flight" in detail and "1 cancelled" in detail, detail


def test_an_unreadable_baseline_listing_still_raises(monkeypatch):
    """Unchanged property: the breaker reads its own state or it says so. Being
    permissive about in-flight runs must never become permissiveness about a listing
    the sweeper could not read at all — `main()` turns this raise into an aborted
    sweep, which is the fail-closed direction."""
    monkeypatch.setattr(
        MOG, "_request", lambda *_a, **_k: (500, {"message": "Server Error"})
    )
    with pytest.raises(RuntimeError, match="integration-baseline listing failed"):
        MOG.integration_baseline_state("acme/widgets", "read")


def test_the_ancestry_check_still_applies_to_the_run_the_walk_chose(monkeypatch):
    """Unchanged property, re-pinned against the new walk: a green from an abandoned
    history is not evidence about current main, and skipping in-flight runs must not
    become a way to reach one."""
    def fake_request(method, url, token, payload=None):
        if "/actions/workflows/" in url:
            return 200, {
                "workflow_runs": [
                    _baseline_run(None, "5" * 40, status="queued"),
                    _baseline_run("success", "6" * 40),
                ]
            }
        if "/git/ref/heads/main" in url:
            return 200, {"object": {"sha": "7" * 40}}
        if "/compare/" in url:
            return 200, {"status": "diverged"}
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", fake_request)
    state, detail = MOG.integration_baseline_state("acme/widgets", "read")
    assert state == "unproven"
    assert "ancestral" in detail


def test_one_bad_pull_request_does_not_fail_the_sweep(monkeypatch, capsys):
    """Individual outcomes are annotations, not job failures — a red PR must not
    stop the sweep from merging the clean ones behind it."""
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setenv("MERGE_TOKEN", "write")
    monkeypatch.setattr(MOG, "labeled_pulls", lambda *_a: [_pull(1), _pull(2)])
    monkeypatch.setattr(MOG, "integration_baseline_state", lambda *_a: ("green", "ok"))
    monkeypatch.setattr(MOG.ProofFreshness, "build", classmethod(lambda *_a, **_k: _freshness()))

    attempts = 0

    def flaky(_repo, pull, *_a):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient")
        return "merged"

    monkeypatch.setattr(MOG, "sweep_pull", flaky)
    assert MOG.main() == 0
    assert "::warning" in capsys.readouterr().out


def test_a_red_main_blocks_ordinary_pulls_and_allows_one_explicit_repair(
    monkeypatch, capsys
):
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setenv("MERGE_TOKEN", "write")
    ordinary = _pull(1)
    repair_one = _pull(2, labels=("merge-on-green", "main-red-repair"))
    repair_two = _pull(3, labels=("merge-on-green", "main-red-repair"))
    monkeypatch.setattr(MOG, "labeled_pulls", lambda *_a: [ordinary, repair_one, repair_two])
    monkeypatch.setattr(
        MOG, "integration_baseline_state", lambda *_a: ("red", "failure at run")
    )
    monkeypatch.setattr(MOG.ProofFreshness, "build", classmethod(lambda *_a, **_k: _freshness()))
    swept: list[int] = []

    def record(_repo, pull, *_a):
        swept.append(pull["number"])
        return "merged"

    monkeypatch.setattr(MOG, "sweep_pull", record)
    assert MOG.main() == 0
    # The invariant is the COUNT, not the identity. Which of two armed repairs wins
    # the slot is now decided by the anti-starvation rotation (see the companion
    # test below); pinning #2 here pinned nothing but GitHub's listing order.
    assert len(swept) == 1, "a broken baseline admits exactly one explicit repair per pass"
    assert swept[0] in {2, 3}, "and the one it admits must be a labelled repair"
    out = capsys.readouterr().out
    assert "circuit breaker" in out and "2 snapshot-deferred" in out


def test_two_armed_repairs_take_turns_instead_of_one_starving_the_other():
    """A repair that is permanently red must not hold the single repair slot forever.

    Before the rotation the slot went to whichever repair GitHub's listing happened
    to return first, every sweep, so a second repair could wait indefinitely behind a
    first one that could never merge — a deadlock inside the deadlock's own escape
    hatch.
    """
    repairs = [
        _pull(number, labels=("merge-on-green", "main-red-repair")) for number in (2, 3)
    ]
    others = [_pull(number) for number in range(10, 40)]
    first_choice = {
        MOG.sweep_order(others + repairs, now=bucket * MOG.ROTATION_BUCKET_SECONDS)[0][
            "number"
        ]
        for bucket in range(12)
    }
    assert first_choice == {2, 3}, (
        f"only {first_choice} ever won the repair slot across 12 rotations"
    )


def test_an_unavailable_baseline_aborts_without_touching_pulls(monkeypatch, capsys):
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setattr(MOG, "labeled_pulls", lambda *_a: [_pull(1)])

    def unavailable(*_a):
        raise RuntimeError("API down")

    monkeypatch.setattr(MOG, "integration_baseline_state", unavailable)
    monkeypatch.setattr(
        MOG,
        "sweep_pull",
        lambda *_a: pytest.fail("no pull may be touched without baseline evidence"),
    )
    assert MOG.main() == 1
    assert "Could not establish" in capsys.readouterr().out


def test_a_missing_repository_is_a_real_failure(monkeypatch, capsys):
    monkeypatch.delenv("GH_REPO", raising=False)
    assert MOG.main() == 1
    assert "::error" in capsys.readouterr().out


# --- the tested-surface gate: a green that outlived its base (#4583) -----------
#
# The literal file lists of the two commits, so the reconstruction is the incident
# and not a paraphrase of it:
#   9aca28d248c  #4583  changed engine/signal_quality.py's CT_* constants
#   a10f126b4dc  #4607  added the guard that pins a copy of them, 2h44m later
#
# Both lists are file NAMES. They go to the fake API as `main_commits=` and
# `pr_files=` and are matched against ci.yml's path patterns; nothing here is ever
# opened, and editing any of these files cannot change what this suite asserts.
# check_ci_trigger_closure.py resolves path literals, so without the marker below it
# reads them as this suite's subjects and demands a trigger entry for each — which
# #4733 supplied for two of them, arming the full 4-pack CI run on every edit to a
# decision packet no test reads. This suite's subject matter IS path filtering, so
# the collision is permanent, not a one-off.
# ci-trigger-closure: data
INCIDENT_4583_FILES = [
    "engine/china_board_rank.py",
    "engine/china_prophet_shadow.py",
    "engine/hk_board_rank.py",
    "engine/signal_gate.py",
    "engine/signal_quality.py",
    "research/signal_engine/SCHEMA.json",
    "scripts/validate_signals.py",
    "site/chart.js",
    "tests/test_china_prophet_shadow.py",
    "tests/test_gate_reasons_exhaustive.py",
    "tests/test_hk_reclaim_veto_policy.py",
    "tests/test_hk_v2_reason_copy_and_ran_lane.py",
    "tests/test_validate_signals.py",
]
# ci-trigger-closure: data — same as above: names of what #4607 touched, never read
INCIDENT_4607_FILES = [
    ".github/ci/legacy-jobs.yml",
    ".github/workflows/ci.yml",
    "config/theme_crosswalk.yml",
    "data/baskets/membership.json",
    "research/prophet_us_audit/RECLAIM_VETO_PACKET_2026-08-05.md",
    "research/prophet_us_audit/reclaim_veto_packet.py",
    "research/prophet_us_audit/reclaim_veto_packet_results_2026-08-05.json",
    "scripts/fetch_basket_extras.py",
    "templates/baskets.html.j2",
    "tests/test_company_theme_exposure.py",
    "tests/test_us_reclaim_veto_packet.py",
]
PROVEN_AT_0742 = "2026-08-05T07:42:00Z"
MAIN_MOVED_AT_1026 = "2026-08-05T10:26:00Z"


def test_the_4583_reconstruction_never_merges_a_proof_main_has_moved_past(
    monkeypatch, capsys
):
    """THE incident, end to end, through the real `.github/workflows` path filters.

    #4583's head was proven at 07:42Z. At 10:26Z #4607 merged
    tests/test_us_reclaim_veto_packet.py — a guard pinning a copy of the constants
    #4583 was changing — onto main. At 22:51Z #4583 merged on the 07:42 green and
    main went red for 18 other pull requests.

    The green was HONEST: that guard was not in the tree the 07:42 run tested. So no
    check-reading fix could ever have caught this. The sweeper must decline the merge
    and hand the head back to CI.
    """
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [
                    _run(
                        "ci-pack-1",
                        conclusion="success",
                        started_at=PROVEN_AT_0742,
                    )
                ],
            }
        },
        main_commits=[(MAIN_MOVED_AT_1026, INCIDENT_4607_FILES)],
        pr_files=INCIDENT_4583_FILES,
        update_status=202,
    )
    freshness = MOG.ProofFreshness.build("acme/widgets", "read")

    assert (
        MOG.sweep_pull(
            "acme/widgets", _pull(), "read", "write", freshness,
            budget=_authorized_budget(),
        ) == "re-proving"
    )
    assert not any(
        call[0] == "PUT" and call[1].endswith("/merge") for call in calls
    ), "the merge must never even be attempted on a proof main has moved past"
    assert any(call[1].endswith("/update-branch") for call in calls), (
        "the sanctioned remedy is to merge main into the head and let CI re-prove it"
    )
    out = capsys.readouterr().out
    assert any(
        line.startswith("::notice") and "proof is stale" in line
        for line in out.splitlines()
    )


def test_the_reconstruction_fires_on_the_surface_alone_not_just_the_ci_shortcut():
    """#4607 also edited ci.yml, which re-proves every pull request by itself. Strip
    those two files out and the SURFACE rule must still fire on its own, or the
    reconstruction above would be proving the shortcut rather than the mechanism.

    The overlap is `scripts/*.py`: #4583 changed scripts/validate_signals.py and
    #4607 changed scripts/fetch_basket_extras.py, both selected by the same entry of
    ci.yml's real filter.
    """
    without_ci = [
        name for name in INCIDENT_4607_FILES if not name.startswith(".github/")
    ]
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, without_ci)],
        gates=MOG.load_pr_gates(),
        pull_files={4242: INCIDENT_4583_FILES},
    )
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert stale, reason
    assert "scripts/*.py" in reason, reason


def test_main_moving_outside_the_surface_still_merges_on_the_existing_green(
    monkeypatch, capsys
):
    """The whole point of the CHOSEN option, and the test that proves this is not the
    strict up-to-date-with-main rule the operator rejected.

    main takes real source commits while the pull request waits. None of them is
    inside its tested surface, so the existing green still says what it said and the
    merge goes through untouched.
    """
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [
                    _run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)
                ],
            }
        },
        main_commits=[
            (MAIN_MOVED_AT_1026, ["collectors/biocatalyst/trials.py"]),
            ("2026-08-05T09:10:00Z", ["content/press/2026-08-05-note.md"]),
        ],
        pr_files=["engine/signal_quality.py", "tests/test_validate_signals.py"],
    )
    freshness = MOG.ProofFreshness.build("acme/widgets", "read")

    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", freshness) == "merged"
    assert not any(call[1].endswith("/update-branch") for call in calls), (
        "re-proving a pull request main did not touch is the rejected strict option"
    )
    assert "none inside this pull request's tested surface" in capsys.readouterr().out


def test_an_unfiltered_workflow_does_not_make_every_surface_everything():
    """fences.yml declares no `paths:`, so it runs on every pull request and says
    NOTHING about which files affect its verdict. Reading that silence as "every
    file" would re-prove every pull request on every main commit — strict, by the
    back door. It contributes no entries."""
    gates = [{"workflow": "fences.yml", "patterns": None}, {"workflow": "ci.yml", "patterns": ["engine/**"]}]
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, ["collectors/fred.py"])],
        gates=gates,
        pull_files={4242: ["engine/signal_quality.py"]},
    )
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert not stale, reason


def test_a_workflow_start_catchall_does_not_make_every_surface_everything():
    """``ci.yml`` starts for ``**`` so a new root cannot bypass the selector.

    That routing catch-all is not job ownership.  Known files still use the
    narrower entries beside it, otherwise every main commit intersects every PR
    and the sweeper returns to strict update-branch livelock.
    """
    gates = [
        {
            "workflow": "ci.yml",
            "patterns": ["engine/**", "collectors/**"],
            "start_only_patterns": ["**"],
        }
    ]
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, ["collectors/fred.py"])],
        gates=gates,
        pull_files={4242: ["engine/signal_quality.py"]},
    )
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert not stale, reason


def test_a_new_root_seen_only_by_the_start_catchall_is_re_proven():
    """Unknown ownership is fail-closed even though ``**`` is start-only."""
    gates = [
        {
            "workflow": "ci.yml",
            "patterns": ["engine/**"],
            "start_only_patterns": ["**"],
        }
    ]
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, ["brand_new_root/subject.py"])],
        gates=gates,
        pull_files={4242: ["engine/signal_quality.py"]},
    )
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert stale
    assert "start catch-all" in reason and "no specific" in reason


def test_a_pipeline_bake_is_not_an_edit():
    """82% of main's commits here are render.yml re-baking `site/` or the nightly
    advancing `data/`. Counting them puts a hit inside 96% of 35-minute windows and
    livelocks any pull request that touches `site/` (18-26 re-prove cycles), which is
    the strict option wearing a filter."""
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, ["site/stocks/index.html", "data/research_vault/catalog.json"])],
        gates=[{"workflow": "ci.yml", "patterns": ["site/**", "data/**"]}],
        pull_files={4242: ["site/chart.js"]},
    )
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert not stale, reason


def test_one_source_file_defeats_the_pipeline_bake_exclusion():
    """The classifier is CONJUNCTIVE on purpose: it answers "was this whole commit a
    bake", never "ignore the baked files in this commit". One hand-edited file and
    the commit is judged normally."""
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, ["site/stocks/index.html", "engine/signal_quality.py"])],
        gates=[{"workflow": "ci.yml", "patterns": ["site/**", "engine/**"]}],
        pull_files={4242: ["engine/signal_gate.py"]},
    )
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert stale and "engine/**" in reason, reason


def test_a_commit_changing_the_check_definitions_re_proves_every_pull_request():
    """A legacy-jobs.yml edit changes WHAT would run. No pull request's
    existing green describes those checks, whatever its own footprint is — note the
    footprint here shares nothing with the commit."""
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, [".github/ci/legacy-jobs.yml"])],
        gates=[{"workflow": "ci.yml", "patterns": ["engine/**"]}],
        pull_files={4242: ["engine/signal_quality.py"]},
    )
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert stale and "check definitions" in reason, reason


def test_an_exact_proof_base_does_not_reprove_its_own_definition_commit(
    monkeypatch,
):
    """The production 2026-08-11 treadmill, reduced to its exact invariant.

    ``update-branch`` merged a check-definition commit into the PR head and fresh
    checks passed with that commit recorded as the pull-request event's exact base.
    Commit identity, not a widened job-start timestamp, must end the old loop.
    """
    freshness = _freshness(
        commits=[
            ("2026-08-05T10:26:00Z", [".github/ci/legacy-jobs.yml"]),
        ],
        gates=[{"workflow": "ci.yml", "patterns": ["engine/**"]}],
        pull_files={4242: ["engine/signal_quality.py"]},
    )
    included = freshness.commits[0]["sha"]
    monkeypatch.setattr(
        MOG,
        "_request",
        lambda *_a, **_k: pytest.fail("exact proof-base metadata needs no ancestry read"),
    )
    stale, reason = freshness.stale_for(
        _pull(),
        [
            _run(
                "ci-pack-1",
                conclusion="success",
                started_at="2026-08-05T10:40:00Z",
                base_sha=included,
            )
        ],
    )
    assert not stale, reason
    assert "exact checked proof base is the frozen main tip" in reason
    assert freshness.commit_file_reads == 0


def test_only_main_commits_newer_than_the_heads_merge_base_are_classified(
    monkeypatch,
):
    """An included base is not permission to ignore main commits after it."""
    freshness = _freshness(
        commits=[
            ("2026-08-05T10:50:00Z", [".github/ci/legacy-jobs.yml"]),
            ("2026-08-05T10:26:00Z", ["data/nightly.json"]),
        ],
        gates=[{"workflow": "ci.yml", "patterns": ["engine/**"]}],
        pull_files={4242: ["engine/signal_quality.py"]},
    )
    included = freshness.commits[1]["sha"]
    monkeypatch.setattr(
        MOG,
        "_request",
        lambda *_a, **_k: (200, {"merge_base_commit": {"sha": included}}),
    )
    classified: list[str] = []
    real_files_of = freshness.files_of
    freshness.files_of = (  # type: ignore[method-assign]
        lambda sha: classified.append(sha) or real_files_of(sha)
    )
    stale, reason = freshness.stale_for(
        _pull(),
        [
            _run(
                "ci-pack-1",
                conclusion="success",
                started_at="2026-08-05T10:40:00Z",
                base_sha=included,
            )
        ],
    )
    assert stale and "check definitions" in reason, reason
    assert classified == [freshness.commits[0]["sha"]], (
        "the included base is trimmed, while only the newer definition is classified"
    )


def test_unreadable_ancestry_without_exact_proof_base_defers_without_mutation(
    monkeypatch, capsys
):
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [
                    _run(
                        "ci-pack-1",
                        conclusion="success",
                        include_proof_metadata=False,
                    )
                ],
            }
        },
        main_commits=[
            ("2026-08-05T10:26:00Z", [".github/ci/legacy-jobs.yml"]),
        ],
        compare_status=502,
        update_status=202,
    )
    built = MOG.ProofFreshness.build("acme/widgets", "read")
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", built
    ) == "freshness-deferred"
    assert not [call for call in calls if call[0] != "GET"]
    assert "Left armed without update-branch" in capsys.readouterr().out


def test_inconsistent_exact_proof_bases_use_the_oldest_conservatively(
    monkeypatch, capsys
):
    first = DEFAULT_MAIN_SHA
    second = f"{2:040d}"
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 2,
                "check_runs": [
                    _run("ci-pack-1", conclusion="success", base_sha=first),
                    _run("fence-pack", conclusion="success", base_sha=second),
                ],
            }
        },
        main_commits=[
            ("2026-08-05T10:50:00Z", ["engine/new.py"]),
            ("2026-08-05T10:26:00Z", ["engine/old.py"]),
        ],
        update_status=202,
    )
    freshness = MOG.ProofFreshness.build("acme/widgets", "read")
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", freshness,
        budget=_authorized_budget(),
    ) == "re-proving"
    assert any(call[1].endswith("/update-branch") for call in calls)


def test_mixed_visible_and_out_of_window_proof_bases_are_indeterminate():
    freshness = _freshness(
        commits=((BEFORE_THE_PROOF, ["engine/new.py"]),)
    )
    runs = _required_proof_runs()
    runs[0]["pull_requests"][0]["base"]["sha"] = "f" * 40
    base, detail = freshness.exact_proof_base(_pull(), runs)
    assert base is None
    assert "outside the frozen main window" in detail


@pytest.mark.parametrize(
    "run",
    [
        _run("ci-pack-1", conclusion="success", pr_numbers=(9999,)),
        _run("ci-pack-1", conclusion="success", head_sha="b" * 40),
    ],
    ids=["wrong-pr-number", "wrong-head-sha"],
)
def test_proof_base_metadata_must_match_the_current_pr_and_exact_head(
    monkeypatch, run
):
    calls = _fake_api(
        monkeypatch,
        check_pages={1: {"total_count": 1, "check_runs": [run]}},
        compare_status=502,
        update_status=202,
    )
    freshness = MOG.ProofFreshness.build("acme/widgets", "read")
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", freshness
    ) == "freshness-deferred"
    assert not [call for call in calls if call[0] != "GET"]


def test_missing_proof_metadata_may_accept_only_full_snapshot_ancestry(monkeypatch):
    freshness = _freshness(
        commits=[
            ("2026-08-05T10:26:00Z", [".github/ci/legacy-jobs.yml"]),
        ]
    )
    tip = freshness.snapshot_tip
    monkeypatch.setattr(
        MOG,
        "_request",
        lambda *_a, **_k: (200, {"merge_base_commit": {"sha": tip}}),
    )
    stale, reason = freshness.stale_for(
        _pull(),
        [
            _run(
                "ci-pack-1",
                conclusion="success",
                include_proof_metadata=False,
            )
        ],
    )
    assert stale is False, reason
    assert "contains the frozen main tip" in reason


@pytest.mark.parametrize("workflow", ["ci.yml", "fences.yml"])
def test_a_PR_workflow_definition_re_proves_every_pull_request(workflow):
    """Only workflows that actually publish PR proof are global definitions."""
    gates = [
        {"workflow": "ci.yml", "patterns": ["engine/**"]},
        {"workflow": "fences.yml", "patterns": None},
    ]
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, [f".github/workflows/{workflow}"])],
        gates=gates,
        pull_files={4242: ["engine/signal_quality.py"]},
    )
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert stale and "check definitions" in reason, reason


def test_removing_a_proof_workflows_PR_trigger_still_invalidates_old_proof():
    """Post-change discovery alone cannot see a trigger the commit just removed."""
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, [".github/workflows/fences.yml"])],
        # Simulate fences.yml no longer appearing in post-change load_pr_gates().
        gates=[{"workflow": "ci.yml", "patterns": ["engine/**"]}],
        pull_files={4242: ["engine/signal_quality.py"]},
    )
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert stale and "check definitions" in reason, reason


@pytest.mark.parametrize(
    "workflow",
    ["deploy-api-secrets.yml", "render.yml", "merge-on-green.yml", "daily.yml"],
)
def test_a_non_PR_workflow_edit_does_not_globally_invalidate_green_proof(workflow):
    """Dispatch/render/control edits do not alter the checks a PR already passed."""
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, [f".github/workflows/{workflow}"])],
        gates=[{"workflow": "ci.yml", "patterns": ["engine/**"]}],
        pull_files={4242: ["engine/signal_quality.py"]},
    )
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert not stale, reason


@pytest.mark.parametrize(
    "case,runs,kwargs,expected_in_reason",
    [
        (
            "a footprint that cannot be read",
            [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)],
            {"pull_files": {4242: None}},
            "could not be established",
        ),
        (
            "a footprint that matches no entry of any gate",
            [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)],
            {"pull_files": {4242: ["notes/whatever.txt"]}},
            "could not be established",
        ),
    ],
)
def test_a_surface_that_cannot_be_determined_is_re_proven(
    case, runs, kwargs, expected_in_reason
):
    """FAIL CLOSED, the whole reason this gate is worth having.

    A definition of "tested surface" that silently resolves to the empty set turns
    this into a no-op that REVIEWS as protection. Every way of not knowing therefore
    lands on re-prove, including the empty footprint — a pull request whose files
    match no path entry is not "outside every surface", it is unclassified.
    """
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, ["engine/signal_quality.py"])], **kwargs
    )
    stale, reason = freshness.stale_for(_pull(), runs)
    assert stale, f"{case}: {reason}"
    assert expected_in_reason in reason, f"{case}: {reason}"


def test_exact_proof_base_makes_job_start_timestamps_non_authoritative():
    """Queue timestamps may be absent or skewed; the event's base SHA is exact."""
    freshness = _freshness()
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=None)]
    )
    assert stale is False, reason


def test_a_proof_older_than_the_whole_visible_timeline_is_re_proven():
    """#4583's own shape: 15 hours old, far beyond the ~8 hours one listing call
    buys. What main did in between cannot be established, so it is not asserted."""
    commits = [
        (f"2026-08-05T{12 - (index // 12):02d}:{(index * 5) % 60:02d}:00Z", ["docs/x.md"])
        for index in range(MOG.MAIN_TIMELINE_PAGE)
    ]
    freshness = _freshness(
        commits=commits,
        pull_files={4242: ["engine/signal_quality.py"]},
        include_proof_base=False,
    )
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at="2026-08-04T07:42:00Z")]
    )
    assert stale and "predates or is outside" in reason, reason


def test_too_many_commits_to_classify_is_re_proven_without_reading_any():
    """The cap protects the shared API quota. It must therefore be checked BEFORE any
    per-commit read, or a pathological pull request spends the budget and then gets
    re-proven anyway."""
    commits = [
        (f"2026-08-05T{13 + (index // 30):02d}:{index % 60:02d}:00Z", ["docs/x.md"])
        for index in range(MOG.MAIN_COMMIT_FILE_CAP + 5)
    ]
    freshness = _freshness(commits=commits, pull_files={4242: ["engine/signal_quality.py"]})
    freshness._commit_files.clear()  # force a real read if one is attempted
    calls: list[str] = []
    freshness.files_of = lambda sha: calls.append(sha) or ([], False)  # type: ignore[method-assign]
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert stale and "more than the" in reason, reason
    assert calls == [], "the cap must be enforced before any commit is fetched"


def test_an_unreadable_main_commit_is_re_proven(monkeypatch):
    freshness = _freshness(
        commits=[(MAIN_MOVED_AT_1026, ["engine/signal_quality.py"])],
        pull_files={4242: ["engine/signal_quality.py"]},
    )
    freshness._commit_files.clear()
    monkeypatch.setattr(MOG, "_request", lambda *_a, **_k: (502, None))
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert stale and "could not be read" in reason, reason


def test_a_truncated_commit_file_list_is_re_proven():
    """GitHub caps a commit's `files` at 300. A truncated list could hide the one
    source file that makes the commit not-a-bake, so it is never used to clear one."""
    freshness = _freshness(commits=[(MAIN_MOVED_AT_1026, ["site/a.html"])])
    sha = freshness.commits[0]["sha"]
    freshness._commit_files[sha] = (["site/a.html"], True)
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert stale and "too many files" in reason, reason


def test_a_truncated_pipeline_bake_is_proven_by_complete_root_trees(monkeypatch):
    """A 9,000-file nightly is exactly where the REST ``files`` cap used to turn
    the bake exclusion off and livelock every green PR. Root tree IDs prove the
    complete boundary without enumerating those 9,000 descendants."""
    sha, parent = "a" * 40, "b" * 40
    current_tree, parent_tree = "c" * 40, "d" * 40
    freshness = MOG.ProofFreshness(
        "acme/widgets",
        "read",
        [{"workflow": "ci.yml", "patterns": ["data/**", "site/**"]}],
        [
            {"sha": sha},
            {"sha": PROOF_BASE_SHA},
        ],
    )
    freshness._pr_files[4242] = ["site/chart.js"]

    stable_engine = {"path": "engine", "type": "tree", "mode": "040000", "sha": "e" * 40}
    stable_tests = {"path": "tests", "type": "tree", "mode": "040000", "sha": "f" * 40}
    old_data = {"path": "data", "type": "tree", "mode": "040000", "sha": "1" * 40}
    new_data = {"path": "data", "type": "tree", "mode": "040000", "sha": "2" * 40}
    stable_site = {"path": "site", "type": "tree", "mode": "040000", "sha": "3" * 40}

    def fake_request(method, url, token, payload=None):
        assert method == "GET" and token == "read" and payload is None
        if url.endswith(f"/commits/{sha}") and "/git/" not in url:
            return 200, {
                "commit": {"tree": {"sha": current_tree}},
                "parents": [{"sha": parent}],
                "files": [{"filename": f"data/file-{index}.json"} for index in range(300)],
            }
        if url.endswith(f"/git/commits/{parent}"):
            return 200, {"tree": {"sha": parent_tree}}
        if url.endswith(f"/git/trees/{current_tree}"):
            return 200, {
                "truncated": False,
                "tree": [new_data, stable_site, stable_engine, stable_tests],
            }
        if url.endswith(f"/git/trees/{parent_tree}"):
            return 200, {
                "truncated": False,
                "tree": [old_data, stable_site, stable_engine, stable_tests],
            }
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", fake_request)
    files, truncated = freshness.files_of(sha)
    assert files == ["data/__bulk_pipeline_tree__"]
    assert not truncated
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)]
    )
    assert not stale, reason


def test_a_truncated_commit_with_any_changed_source_root_stays_fail_closed(monkeypatch):
    """Root-tree proof is conjunctive: one changed source subtree defeats it even
    when all 300 visible file rows happen to be under ``data/``."""
    sha, parent = "a" * 40, "b" * 40
    current_tree, parent_tree = "c" * 40, "d" * 40
    freshness = MOG.ProofFreshness(
        "acme/widgets",
        "read",
        _gates(),
        [{"sha": sha}],
    )

    def entry(path, object_sha):
        return {"path": path, "type": "tree", "mode": "040000", "sha": object_sha}

    def fake_request(method, url, token, payload=None):
        if url.endswith(f"/commits/{sha}") and "/git/" not in url:
            return 200, {
                "commit": {"tree": {"sha": current_tree}},
                "parents": [{"sha": parent}],
                "files": [{"filename": f"data/file-{index}.json"} for index in range(300)],
            }
        if url.endswith(f"/git/commits/{parent}"):
            return 200, {"tree": {"sha": parent_tree}}
        if url.endswith(f"/git/trees/{current_tree}"):
            return 200, {
                "truncated": False,
                "tree": [entry("data", "2" * 40), entry("engine", "4" * 40)],
            }
        if url.endswith(f"/git/trees/{parent_tree}"):
            return 200, {
                "truncated": False,
                "tree": [entry("data", "1" * 40), entry("engine", "3" * 40)],
            }
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", fake_request)
    files, truncated = freshness.files_of(sha)
    assert len(files) == 300
    assert truncated, "the hidden engine change must defeat the pipeline-bake proof"


def test_a_raising_surface_check_can_never_become_permission_to_merge(monkeypatch, capsys):
    """A broken read defers; mutating the branch cannot repair control-plane state."""
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}
        },
        update_status=202,
    )

    class Exploding:
        def stale_for(self, *_a):
            raise ZeroDivisionError("boom")

    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", Exploding()
    ) == "freshness-deferred"
    assert not [call for call in calls if call[0] != "GET"]
    assert "without update-branch" in capsys.readouterr().out


def test_a_stale_proof_that_cannot_be_updated_is_labeled_and_explained_once(
    monkeypatch, capsys
):
    """update-branch declining means a real content conflict, which no number of
    sweeps fixes. That gets the label and exactly one comment — and the comment must
    say why, or the next reader assumes a red check."""
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [
                    _run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)
                ],
            }
        },
        main_commits=[(MAIN_MOVED_AT_1026, [".github/workflows/ci.yml"])],
        update_status=422,
    )
    freshness = MOG.ProofFreshness.build("acme/widgets", "read")
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", freshness,
        budget=_authorized_budget(),
    ) == "conflict"
    comments = [c for c in calls if c[0] == "POST" and c[1].endswith("/comments")]
    assert len(comments) == 1
    body = comments[0][2]["body"]
    assert "#4583" in body and "proof is no longer trustworthy" in body


def test_sweep_pull_has_no_default_freshness():
    """A default would let a caller that forgot to build the gate merge on undated
    greens forever — a no-op that reviews as protection. Required parameter, so the
    mistake is a TypeError at the call site."""
    import inspect

    parameter = inspect.signature(MOG.sweep_pull).parameters["freshness"]
    assert parameter.default is inspect.Parameter.empty


def test_build_refuses_a_workflow_set_that_cannot_scope_anything(tmp_path):
    """Three ways the surface can come out empty, all of them refused. An empty
    surface derived from nothing is exactly the shape this gate exists to prevent."""
    empty = tmp_path / "none"
    empty.mkdir()
    with pytest.raises(RuntimeError, match="no on.pull_request workflow"):
        MOG.load_pr_gates(empty)

    unfiltered = tmp_path / "unfiltered"
    unfiltered.mkdir()
    (unfiltered / "fences.yml").write_text("on:\n  pull_request:\njobs: {}\n")
    with pytest.raises(RuntimeError, match="declares a paths filter"):
        MOG.load_pr_gates(unfiltered)

    catchall_only = tmp_path / "catchall-only"
    catchall_only.mkdir()
    (catchall_only / "ci.yml").write_text(
        'on:\n  pull_request:\n    paths:\n      - "**"\njobs: {}\n'
    )
    with pytest.raises(RuntimeError, match="specific non-catch-all entry"):
        MOG.load_pr_gates(catchall_only)

    negated = tmp_path / "negated"
    negated.mkdir()
    (negated / "ci.yml").write_text(
        'on:\n  pull_request:\n    paths:\n      - "engine/**"\n      - "!engine/legacy/**"\njobs: {}\n'
    )
    with pytest.raises(RuntimeError, match="negation"):
        MOG.load_pr_gates(negated)


def test_build_refuses_an_empty_main_history(monkeypatch):
    """An empty commit list would hand every pull request a free "main never moved".
    It is unreachable against a real repository, so it is an error, not a shortcut."""
    monkeypatch.setattr(MOG, "_request", lambda *_a, **_k: (200, []))
    with pytest.raises(RuntimeError, match="came back empty"):
        MOG.ProofFreshness.build("acme/widgets", "read")


def test_an_unbuildable_gate_aborts_the_sweep_instead_of_re_proving_everything(
    monkeypatch, capsys
):
    """Fail closed, but at the right grain. A broken sweeper is one bug, not 60 stale
    proofs, and re-proving 60 pull requests would burn a CI run each to answer a
    question the sweep never managed to ask. Nothing merges either way."""
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setattr(MOG, "labeled_pulls", lambda *_a: [_pull(1)])
    monkeypatch.setattr(MOG, "integration_baseline_state", lambda *_a: ("green", "ok"))

    def broken(*_a, **_k):
        raise RuntimeError("sparse-checkout dropped .github/workflows")

    monkeypatch.setattr(MOG.ProofFreshness, "build", classmethod(broken))
    monkeypatch.setattr(
        MOG, "sweep_pull", lambda *_a: pytest.fail("no pull may be touched")
    )
    assert MOG.main() == 1
    # The annotation must START its line (house law, tests/test_gh_annotation_line_start.py)
    # — asserted per-line rather than on the first byte of stdout, because the sweep
    # legitimately logs its API budget before it gets this far.
    assert any(
        line.startswith("::error") and "tested-surface gate" in line
        for line in capsys.readouterr().out.splitlines()
    )


def test_the_commit_classification_is_shared_across_pull_requests(monkeypatch):
    """The API-cost constraint, pinned. The sweep runs every ~10 minutes against a
    shared quota pool, so "main's commits since T" is computed once and reused: three
    pull requests over the same window must cost three commit reads, not nine."""
    window = [
        ("2026-08-05T11:00:00Z", ["collectors/a.py"]),
        ("2026-08-05T10:30:00Z", ["collectors/b.py"]),
        ("2026-08-05T10:00:00Z", ["collectors/c.py"]),
    ]
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [
                    _run(
                        "ci-pack-1",
                        conclusion="success",
                        started_at=PROVEN_AT_0742,
                        pr_numbers=(1, 2, 3),
                    )
                ],
            }
        },
        main_commits=window,
        pr_files=["engine/signal_quality.py"],
    )
    freshness = MOG.ProofFreshness.build("acme/widgets", "read")
    for number in (1, 2, 3):
        assert (
            MOG.sweep_pull("acme/widgets", _pull(number), "read", "write", freshness)
            == "merged"
        )
    assert freshness.commit_file_reads == len(window)
    commit_reads = [
        call for call in calls if "/commits/" in call[1] and "/check-runs" not in call[1]
    ]
    assert len(commit_reads) == len(window), commit_reads


def test_github_glob_semantics_not_fnmatch():
    """`fnmatch` lets a single `*` cross `/`, so it calls `scripts/ci/deep.py` covered
    by `scripts/*.py` — GitHub does not. The wrongness is directional: it
    UNDER-reports exactly the nested modules most likely to be missing an entry, so
    a surface built on it would quietly shrink."""
    from scripts.gh_path_filter import matched, matching_patterns

    assert matched("scripts/x.py", ["scripts/*.py"])
    assert not matched("scripts/ci/deep.py", ["scripts/*.py"])
    assert matched("engine/sub/deep.py", ["engine/**"])
    assert not matched("engineering/other.py", ["engine/**"])
    assert matched("a/b.py", ["a/b.py"]) and not matched("a/b.py", ["a/c.py"])
    assert matched("anything/at/all.py", None), "no filter means the workflow always runs"
    # Every entry, not just the first: engine/signal_quality.py is listed explicitly
    # AND swept by engine/**, and an intersection must not depend on list order.
    assert matching_patterns(
        "engine/signal_quality.py", ["engine/signal_quality.py", "tests/**", "engine/**"]
    ) == ["engine/signal_quality.py", "engine/**"]


def test_the_module_records_that_4583_was_not_a_path_filter_gap():
    """#4645's commit message blames a ci.yml path-filter gap. It was not one: at
    #4583's own merge commit `engine/signal_quality.py` was covered twice in
    `on.pull_request.paths`. The correction has to live where the next reader looks,
    or the wrong diagnosis gets fixed again."""
    source = (ROOT / "scripts" / "merge_on_green.py").read_text(encoding="utf-8")
    assert "#4645" in source and "was not one" in source
    assert "9aca28d248c" in source, "the merge commit is the receipt for the claim"


def test_re_proving_never_labels_a_pull_request_a_concurrent_sweep_just_merged(
    monkeypatch, capsys
):
    """#4647's hazard, arriving through the new door.

    Pre-deploy/out-of-band sweeps can race even though current full sweeps coalesce.
    Two actors can both judge this pull request clean AND stale. One of them re-proves
    or merges it; the other's
    `update-branch` is answered 422 — because the pull request is MERGED, not because
    it conflicts — and labelling that `merge-blocked` with the one-shot "not merging"
    comment makes a falsehood permanent on a successfully merged PR.

    The staleness path must ask the same question the refused-merge path asks.
    """
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [
                    _run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)
                ],
            }
        },
        main_commits=[(MAIN_MOVED_AT_1026, [".github/workflows/ci.yml"])],
        update_status=422,
        pull_payload={"merged": True, "state": "closed"},
    )
    freshness = MOG.ProofFreshness.build("acme/widgets", "read")
    assert (
        MOG.sweep_pull("acme/widgets", _pull(), "read", "write", freshness)
        == "already-merged"
    )
    posts = [call for call in calls if call[0] == "POST"]
    assert not any(call[1].endswith("/labels") for call in posts), (
        "labelling a merged pull request `merge-blocked` is the exact hazard"
    )
    assert not any(call[1].endswith("/comments") for call in posts), (
        "and the one-shot comment would make the falsehood permanent"
    )
    assert any(
        line.startswith("::notice") and "already-merged" in line
        for line in capsys.readouterr().out.splitlines()
    )


def test_re_proving_leaves_a_concurrently_advanced_head_unblocked(monkeypatch):
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": 1,
                "check_runs": [
                    _run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)
                ],
            }
        },
        main_commits=[(MAIN_MOVED_AT_1026, [".github/workflows/ci.yml"])],
        update_status=422,
        pull_payload={"state": "open", "head": {"sha": "b" * 40}},
    )
    freshness = MOG.ProofFreshness.build("acme/widgets", "read")
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", freshness
    ) == "head-moved"
    assert not [call for call in calls if call[0] == "POST"]


# --- the API budget: the deadlock that killed this lane ------------------------
#
# Measured 2026-08-07. READ_TOKEN is the job's own GITHUB_TOKEN, whose Actions
# quota is 1,000 requests/hour PER REPOSITORY. Sweep 31148157570 evaluated 93 armed
# pull requests for ~121 calls in 82 seconds; the workflow_run trigger produced
# 23-28 non-skipped sweeps in the 02Z hour. 28 x 121 = ~3,400 calls against a
# 1,000/hr bucket, so the bucket emptied, every later sweep 403'd on its FIRST call,
# and because sweeps kept firing they kept eating each hourly refill. Continuous
# failure 03:34Z-04:38Z, recovery at 04:39Z — one clean hourly window, which is the
# primary-quota signature rather than a secondary/burst throttle.
#
# A big backlog makes each sweep expensive -> the token starves -> nothing merges ->
# the backlog stays big. These tests pin the three places that loop is now cut.


def _main_harness(
    monkeypatch,
    pulls,
    *,
    readings=(1000,),
    limit=1000,
    verdict="pending",
):
    """Run `main()` with everything but the budget and the ordering stubbed out.

    `readings` is what successive `core_rate_limit` polls return (remaining), the
    first being the preflight. The last value repeats forever.
    """
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setenv("MERGE_TOKEN", "write")
    monkeypatch.delenv("TRIGGER_HEAD_SHA", raising=False)
    # A `failure` value here would route `main()` into `mark_only_pass` and no
    # full-sweep test would run the code it is about. Cleared rather than assumed
    # absent: this pack runs inside Actions jobs, where env is ambient.
    monkeypatch.delenv("TRIGGER_CONCLUSION", raising=False)
    polls: list[int] = []

    def fake_limit(_token):
        index = min(len(polls), len(readings) - 1)
        polls.append(index)
        return readings[index], limit

    monkeypatch.setattr(MOG, "core_rate_limit", fake_limit)
    monkeypatch.setattr(MOG, "labeled_pulls", lambda *_a: list(pulls))
    monkeypatch.setattr(MOG, "integration_baseline_state", lambda *_a: ("green", "ok"))
    monkeypatch.setattr(
        MOG.ProofFreshness, "build", classmethod(lambda _cls, *_a, **_k: _freshness())
    )
    monkeypatch.setattr(MOG, "main_proof", lambda *_a: _proof())
    monkeypatch.setattr(MOG, "ensure_main_baseline", lambda *_a: "stubbed")
    seen: list[int] = []

    def fake_sweep(_repo, pull, *_rest):
        seen.append(pull["number"])
        return verdict

    monkeypatch.setattr(MOG, "sweep_pull", fake_sweep)
    return seen


def test_repo_wide_proof_census_sums_every_active_actions_state(monkeypatch):
    counts = {
        "queued": 3,
        "in_progress": 4,
        "pending": 1,
        "requested": 2,
        "waiting": 5,
    }
    seen: list[str] = []

    def fake_request(method, url, token, payload=None):
        assert method == "GET" and token == "read" and payload is None
        for run_status, count in counts.items():
            if f"status={run_status}" in url:
                seen.append(run_status)
                return 200, {"total_count": count, "workflow_runs": []}
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", fake_request)
    assert REAL_IN_FLIGHT_PR_PROOFS("acme/widgets", "read") == sum(counts.values())
    assert set(seen) == set(MOG.ACTIVE_PR_PROOF_STATUSES)


@pytest.mark.parametrize(
    "status,payload",
    [
        (502, None),
        (200, {}),
        (200, {"total_count": "7"}),
        (200, {"total_count": -1}),
    ],
)
def test_an_unreadable_proof_census_never_claims_zero_load(
    monkeypatch, status, payload
):
    monkeypatch.setattr(MOG, "_request", lambda *_a, **_k: (status, payload))
    assert REAL_IN_FLIGHT_PR_PROOFS("acme/widgets", "read") is None


def test_refresh_mutation_authority_is_the_in_progress_serialized_main_workflow(
    monkeypatch,
):
    def fake_request(method, url, token, payload=None):
        assert method == "GET" and url.endswith("/actions/runs/123")
        assert token == "read" and payload is None
        return 200, {
            "id": 123,
            "status": "in_progress",
            "path": ".github/workflows/merge-on-green.yml",
            "head_branch": "main",
            "event": "workflow_run",
            "repository": {"full_name": "acme/widgets"},
        }

    monkeypatch.setattr(MOG, "_request", fake_request)
    assert REAL_SERIALIZED_REFRESH_AUTHORITY(
        "acme/widgets", "read", "123", "success"
    )
    assert not REAL_SERIALIZED_REFRESH_AUTHORITY(
        "acme/widgets", "read", "123", "failure"
    )
    assert not REAL_SERIALIZED_REFRESH_AUTHORITY(
        "acme/widgets", "read", "not-a-run", "success"
    )


def test_refresh_budget_refuses_branch_writes_without_serialized_authority(
    monkeypatch,
):
    calls: list[tuple[str, str]] = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url))
        if method == "GET" and url.endswith("/pulls/1"):
            return 200, _pull(1)
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    budget = MOG.SweepBudget("read", max_refreshes=1)
    assert MOG.attempt_update_branch(
        "acme/widgets", _pull(1), "write", budget, "stale"
    ) == "refresh-deferred"
    assert not [call for call in calls if call[0] == "PUT"]


@pytest.mark.parametrize(
    "active,expected_allowance",
    [
        (0, MOG.MAX_IN_FLIGHT_PR_PROOFS),
        (MOG.MAX_IN_FLIGHT_PR_PROOFS - 1, 1),
        (MOG.MAX_IN_FLIGHT_PR_PROOFS, MOG.HIGH_LOAD_FAIR_REFRESHES),
        (34, MOG.HIGH_LOAD_FAIR_REFRESHES),
        (None, 0),
    ],
)
def test_repo_wide_active_proofs_clamp_update_branch_capacity(
    monkeypatch, capsys, active, expected_allowance
):
    _main_harness(monkeypatch, [_pull(1)])
    monkeypatch.setattr(MOG, "in_flight_pr_proofs", lambda *_a: active)
    allowances: list[int] = []

    def inspect_budget(
        _repo, _pull_payload, _read, _write, _fresh, _proof, budget, _blocked
    ):
        allowances.append(budget.max_refreshes)
        return "pending"

    monkeypatch.setattr(MOG, "sweep_pull", inspect_budget)
    assert MOG.main() == 0
    assert allowances == [expected_allowance]
    out = capsys.readouterr().out
    assert "PR proof load:" in out
    if active is None:
        assert "new refreshes paused" in out
    else:
        assert f"{active} indexed pull-request ci run(s)" in out


def test_every_update_branch_call_is_behind_the_refresh_admission_gateway():
    tree = ast.parse(
        (ROOT / "scripts" / "merge_on_green.py").read_text(encoding="utf-8")
    )
    owners = []
    for function in [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]:
        for call in [node for node in ast.walk(function) if isinstance(node, ast.Call)]:
            if isinstance(call.func, ast.Name) and call.func.id == "update_branch":
                owners.append(function.name)
    assert owners == ["attempt_update_branch"], (
        "all three refresh reasons must claim capacity/the durable lease before the "
        f"CI-producing write; direct callers found in {owners}"
    )


@pytest.mark.parametrize(
    "owner_visible_in_filtered_index",
    (True, False),
    ids=("indexed-owner", "direct-read-before-index-catches-up"),
)
def test_high_load_refresh_claims_one_durable_lease_before_one_update(
    monkeypatch, owner_visible_in_filtered_index
):
    calls: list[tuple[str, str]] = []
    claimed = [False]
    generation_description = [MOG.REFRESH_LEASE_DESCRIPTION]

    def fake_request(method, url, token, payload=None):
        calls.append((method, url))
        if method == "GET" and url.endswith("/pulls/1"):
            labels = (MOG.MERGE_ON_GREEN_LABEL,) + (
                (MOG.REFRESH_LEASE_LABEL,) if claimed[0] else ()
            )
            return 200, _pull(1, labels=labels)
        if method == "GET" and url.endswith("/pulls/2"):
            return 200, _pull(2)
        if method == "GET" and "/labels/" in url:
            return 200, {
                "name": MOG.REFRESH_LEASE_LABEL,
                "description": generation_description[0],
            }
        if method == "PATCH" and "/labels/" in url:
            generation_description[0] = payload["description"]
            claimed[0] = True
            return 200, payload
        if method == "POST" and url.endswith("/issues/1/labels"):
            return 200, [{"name": MOG.REFRESH_LEASE_LABEL}]
        if method == "GET" and url.endswith("/issues/1"):
            return 200, {
                "number": 1,
                "labels": [
                    {"name": MOG.MERGE_ON_GREEN_LABEL},
                    {"name": MOG.REFRESH_LEASE_LABEL},
                ],
            }
        if method == "GET" and "/issues?" in url:
            indexed = [
                {
                    "number": 1,
                    "pull_request": {"url": "pr"},
                    "labels": [
                        {"name": MOG.MERGE_ON_GREEN_LABEL},
                        {"name": MOG.REFRESH_LEASE_LABEL},
                    ],
                }
            ]
            return 200, indexed if owner_visible_in_filtered_index else []
        if method == "PUT" and url.endswith("/pulls/1/update-branch"):
            return 202, {"message": "Updating"}
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    lease = MOG.RefreshLease("acme/widgets", "read", "write")
    budget = MOG.SweepBudget("read", max_refreshes=1)
    budget.refresh_authorized = True
    budget.max_refreshes = 1
    budget.requires_refresh_lease = True
    budget.refresh_lease = lease
    first = _pull(1)
    second = _pull(2)
    assert MOG.attempt_update_branch(
        "acme/widgets", first, "write", budget, "stale"
    ) == "updated"
    assert MOG.attempt_update_branch(
        "acme/widgets", second, "write", budget, "stale"
    ) == "refresh-deferred"
    generation_index = next(
        index for index, call in enumerate(calls) if call[0] == "PATCH" and "/labels/" in call[1]
    )
    update_index = next(
        index for index, call in enumerate(calls) if call[0] == "PUT" and call[1].endswith("/update-branch")
    )
    assert generation_index < update_index
    assert len([call for call in calls if call[0] == "PUT"]) == 1
    assert lease.owner_number == 1
    assert lease.owns(first)


def test_refresh_lease_record_round_trips_exact_owner_head_and_time():
    record = MOG.refresh_lease_record(
        41, "A" * 40, "2026-08-12T01:02:03Z", "1a2b3c4d5e6f"
    )
    assert len(record) <= 100
    assert MOG.parse_refresh_lease_record(record) == (
        41,
        "a" * 40,
        "2026-08-12T01:02:03Z",
        "1a2b3c4d5e6f",
    )
    assert MOG.parse_refresh_lease_record(MOG.REFRESH_LEASE_DESCRIPTION) is None


def test_refresh_lease_generation_ids_are_unique_even_within_one_second(monkeypatch):
    ids = iter(("000000000001", "000000000002"))
    monkeypatch.setattr(MOG.secrets, "token_hex", lambda _bytes: next(ids))
    first = MOG.refresh_lease_record(1, "a" * 40, "2026-08-12T01:02:03Z")
    second = MOG.refresh_lease_record(1, "a" * 40, "2026-08-12T01:02:03Z")
    assert first != second
    assert len(first) <= 100 and len(second) <= 100


def test_future_lease_clock_expires_instead_of_wedging_forever():
    lease = MOG.RefreshLease(
        "acme/widgets",
        "read",
        "write",
        owner_number=1,
        owner_updated_at="2099-01-01T00:00:00Z",
        generation_head_sha="a" * 40,
        generation_id="1a2b3c4d5e6f",
    )
    assert lease.owner_is_old(now=1_786_000_000)


def test_settled_leased_generation_releases_before_a_second_refresh(monkeypatch):
    """One lease buys one new-head proof, not indefinite ownership until merge."""
    calls = _fake_api(
        monkeypatch,
        check_pages={
            1: {
                "total_count": len(_required_proof_runs()),
                "check_runs": _required_proof_runs(),
            }
        },
        main_commits=((BEFORE_THE_PROOF, [".github/ci/legacy-jobs.yml"]),),
        pull_payload={
            "labels": [
                {"name": MOG.MERGE_ON_GREEN_LABEL},
                {"name": MOG.REFRESH_LEASE_LABEL},
            ]
        },
    )
    pull = _pull(
        4242,
        labels=(MOG.MERGE_ON_GREEN_LABEL, MOG.REFRESH_LEASE_LABEL),
    )
    lease = MOG.RefreshLease(
        "acme/widgets",
        "read",
        "write",
        owner_number=4242,
        owner_updated_at="2026-08-12T01:00:00Z",
        generation_head_sha="b" * 40,
        generation_id="1a2b3c4d5e6f",
    )
    budget = MOG.SweepBudget("read", max_refreshes=1)
    budget.max_refreshes = 1
    budget.requires_refresh_lease = True
    budget.refresh_lease = lease

    original_request = MOG._request

    def generation_aware_request(method, url, token, payload=None):
        if method == "GET" and "/labels/" in url:
            return 200, {
                "name": MOG.REFRESH_LEASE_LABEL,
                "description": MOG.refresh_lease_record(
                    4242, "b" * 40, "2026-08-12T01:00:00Z"
                    , "1a2b3c4d5e6f"
                ),
            }
        return original_request(method, url, token, payload)

    monkeypatch.setattr(MOG, "_request", generation_aware_request)

    verdict = MOG.sweep_pull(
        "acme/widgets", pull, "read", "write", _freshness(
            commits=((BEFORE_THE_PROOF, [".github/ci/legacy-jobs.yml"]),)
        ), budget=budget
    )

    assert verdict == "lease-rotation-deferred"
    assert not [call for call in calls if call[1].endswith("/update-branch")]
    assert 4242 in lease.released_numbers
    assert not lease.claim(pull), "the same sweep cannot reacquire a settled generation"
    assert any(
        call[0] == "DELETE" and MOG.REFRESH_LEASE_LABEL in call[1]
        for call in calls
    )


def test_low_load_refresh_does_not_create_a_controller_lease(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url))
        if method == "GET" and url.endswith("/pulls/1"):
            return 200, _pull(1)
        assert method == "PUT" and url.endswith("/update-branch")
        return 202, {"message": "Updating"}

    monkeypatch.setattr(MOG, "_request", fake_request)
    budget = MOG.SweepBudget("read", max_refreshes=2)
    budget.refresh_authorized = True
    assert MOG.attempt_update_branch(
        "acme/widgets", _pull(1), "write", budget, "stale"
    ) == "updated"
    assert calls == [
        ("GET", f"{MOG.GITHUB_API}/repos/acme/widgets/pulls/1"),
        ("PUT", f"{MOG.GITHUB_API}/repos/acme/widgets/pulls/1/update-branch"),
    ]


def test_ambiguous_lease_claim_never_updates_or_tries_a_second_owner(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url))
        if method == "GET" and url.endswith("/pulls/1"):
            return 200, _pull(1)
        if method == "GET" and url.endswith("/pulls/2"):
            return 200, _pull(2)
        if method == "GET" and "/labels/" in url:
            return 200, {
                "name": MOG.REFRESH_LEASE_LABEL,
                "description": MOG.REFRESH_LEASE_DESCRIPTION,
            }
        if method == "PATCH" and "/labels/" in url:
            return 500, None
        if method == "POST" and url.endswith("/issues/1/labels"):
            raise ConnectionError("response lost")
        if method == "GET" and url.endswith("/issues/1"):
            return 200, {"labels": []}
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    lease = MOG.RefreshLease("acme/widgets", "read", "write")
    budget = MOG.SweepBudget("read", max_refreshes=1)
    budget.refresh_authorized = True
    budget.max_refreshes = 1
    budget.requires_refresh_lease = True
    budget.refresh_lease = lease
    assert MOG.attempt_update_branch(
        "acme/widgets", _pull(1), "write", budget, "stale"
    ) == "refresh-deferred"
    assert MOG.attempt_update_branch(
        "acme/widgets", _pull(2), "write", budget, "stale"
    ) == "refresh-deferred"
    assert not [call for call in calls if call[0] == "PUT"]
    assert len([call for call in calls if call[0] == "PATCH"]) == 1


def test_lease_owner_outside_pull_page_is_fetched_and_promoted(monkeypatch):
    issue = {
        "number": 999,
        "updated_at": "2026-08-12T01:00:00Z",
        "pull_request": {"url": "pr"},
        "labels": [
            {"name": MOG.MERGE_ON_GREEN_LABEL},
            {"name": MOG.REFRESH_LEASE_LABEL},
        ],
    }
    owner = _pull(999, labels=(MOG.MERGE_ON_GREEN_LABEL, MOG.REFRESH_LEASE_LABEL))

    def fake_request(method, url, token, payload=None):
        if "/issues?" in url:
            return 200, [issue]
        if method == "GET" and "/labels/" in url:
            return 200, {
                "description": MOG.refresh_lease_record(
                    999, "b" * 40, "2026-08-12T01:00:00Z", "1a2b3c4d5e6f"
                )
            }
        if method == "GET" and url.endswith("/pulls/999"):
            return 200, {**owner, "state": "open"}
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    lease, pulls = REAL_PREPARE_REFRESH_LEASE(
        "acme/widgets", "read", "write", [_pull(1)]
    )
    assert lease.readable and lease.owner_number == 999
    assert pulls[0]["number"] == 999
    ordered = MOG.sweep_order(
        pulls, refresh_lease_number=999, trigger_head_sha="a" * 40, cap=1, now=0
    )
    assert ordered[0]["number"] == 999


def test_generation_register_recovers_an_owner_missing_from_the_label_index(
    monkeypatch,
):
    owner = {
        **_pull(
            999,
            labels=(MOG.MERGE_ON_GREEN_LABEL, MOG.REFRESH_LEASE_LABEL),
        ),
        "state": "open",
    }
    generation = MOG.refresh_lease_record(
        999, "b" * 40, "2026-08-12T01:00:00Z", "1a2b3c4d5e6f"
    )

    def fake_request(method, url, token, payload=None):
        if method == "GET" and "/issues?" in url:
            return 200, []
        if method == "GET" and "/labels/" in url:
            return 200, {"description": generation}
        if method == "GET" and url.endswith("/issues/999"):
            return 200, {
                "number": 999,
                "state": "open",
                "pull_request": {"url": "pr"},
                "labels": owner["labels"],
            }
        if method == "GET" and url.endswith("/pulls/999"):
            return 200, owner
        if method == "GET" and url.endswith("/issues/999/events?per_page=100"):
            return 200, []
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    lease, pulls = REAL_PREPARE_REFRESH_LEASE(
        "acme/widgets", "read", "write", [_pull(1)]
    )
    assert lease.readable and lease.owner_number == 999
    assert lease.generation_record == (
        999,
        "b" * 40,
        "2026-08-12T01:00:00Z",
        "1a2b3c4d5e6f",
    )
    assert pulls[0]["number"] == 999


def test_unindexed_generation_owner_with_malformed_direct_issue_fails_closed(
    monkeypatch,
):
    generation = MOG.refresh_lease_record(
        999, "b" * 40, "2026-08-12T01:00:00Z", "1a2b3c4d5e6f"
    )

    def fake_request(method, url, token, payload=None):
        if method == "GET" and "/issues?" in url:
            return 200, []
        if method == "GET" and "/labels/" in url:
            return 200, {"description": generation}
        if method == "GET" and url.endswith("/issues/999"):
            return 200, {}
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    lease, pulls = REAL_PREPARE_REFRESH_LEASE(
        "acme/widgets", "read", "write", [_pull(1)]
    )
    assert not lease.readable and lease.owner_number is None
    assert pulls == [_pull(1)]


def test_multiple_refresh_owners_fail_closed_without_deleting_either(monkeypatch, capsys):
    issues = [
        {
            "number": number,
            "pull_request": {"url": "pr"},
            "labels": [
                {"name": MOG.MERGE_ON_GREEN_LABEL},
                {"name": MOG.REFRESH_LEASE_LABEL},
            ],
        }
        for number in (1, 2)
    ]
    def fake_request(method, url, *_a, **_k):
        if method == "GET" and "/issues?" in url:
            return 200, issues
        if method == "GET" and "/labels/" in url:
            return 200, {
                "description": MOG.refresh_lease_record(
                    2, "b" * 40, "2026-08-12T01:00:00Z", "1a2b3c4d5e6f"
                )
            }
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    monkeypatch.setattr(
        MOG.time,
        "time",
        lambda: dt.datetime(2026, 8, 12, 1, 30, tzinfo=dt.timezone.utc).timestamp(),
    )
    lease, _ = REAL_PREPARE_REFRESH_LEASE(
        "acme/widgets", "read", "write", [_pull(1), _pull(2)]
    )
    assert not lease.readable and lease.owner_number is None
    assert "Multiple refresh owners exist" in capsys.readouterr().out


def test_expired_duplicate_refresh_owners_are_cleaned_and_lane_recovers(
    monkeypatch, capsys
):
    issues = [
        {
            "number": number,
            "pull_request": {"url": "pr"},
            "labels": [
                {"name": MOG.MERGE_ON_GREEN_LABEL},
                {"name": MOG.REFRESH_LEASE_LABEL},
            ],
        }
        for number in (1, 2)
    ]
    deletes: list[int] = []

    def fake_request(method, url, *_a, **_k):
        if method == "GET" and "/issues?" in url:
            return 200, issues
        if method == "GET" and "/labels/" in url:
            return 200, {
                "description": MOG.refresh_lease_record(
                    2, "b" * 40, "2026-08-12T01:00:00Z", "1a2b3c4d5e6f"
                )
            }
        if method == "DELETE" and "/issues/" in url:
            deletes.append(int(url.split("/issues/", 1)[1].split("/", 1)[0]))
            return 204, None
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    monkeypatch.setattr(
        MOG.time,
        "time",
        lambda: dt.datetime(2026, 8, 12, 4, 1, tzinfo=dt.timezone.utc).timestamp(),
    )
    pulls = [
        _pull(1, labels=(MOG.MERGE_ON_GREEN_LABEL, MOG.REFRESH_LEASE_LABEL)),
        _pull(2, labels=(MOG.MERGE_ON_GREEN_LABEL, MOG.REFRESH_LEASE_LABEL)),
    ]
    lease, cleaned_pulls = REAL_PREPARE_REFRESH_LEASE(
        "acme/widgets", "read", "write", pulls
    )
    assert lease.readable and lease.owner_number is None
    assert sorted(deletes) == [1, 2]
    assert all(MOG.REFRESH_LEASE_LABEL not in MOG.label_names(p) for p in cleaned_pulls)
    assert "Expired duplicate-owner quarantine" in capsys.readouterr().out


def _dispatch_run(run_id, status, created_at):
    return {"id": run_id, "status": status, "created_at": created_at}


def test_self_wake_coalesces_with_a_different_pending_dispatch(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url))
        return 200, {
            "workflow_runs": [
                _dispatch_run(99, "queued", "2026-08-12T01:00:00Z")
            ]
        }

    monkeypatch.setattr(MOG, "_request", fake_request)
    assert REAL_ENSURE_SELF_WAKE(
        "acme/widgets", "read", "write", "42", "main moved"
    ).startswith("coalesced")
    assert not [call for call in calls if call[0] == "POST"]


def test_self_wake_ignores_current_run_observes_cooldown_and_dispatches_once(
    monkeypatch,
):
    calls: list[tuple[str, str]] = []
    clock = [
        dt.datetime(2026, 8, 12, 1, 0, 30, tzinfo=dt.timezone.utc).timestamp()
    ]
    sleeps: list[float] = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url))
        if method == "GET":
            return 200, {
                "workflow_runs": [
                    _dispatch_run(42, "in_progress", "2026-08-12T01:00:00Z")
                ]
            }
        assert method == "POST" and url.endswith("/dispatches")
        return 204, None

    monkeypatch.setattr(MOG, "_request", fake_request)
    monkeypatch.setattr(MOG.time, "time", lambda: clock[0])

    def advance(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(MOG.time, "sleep", advance)
    assert REAL_ENSURE_SELF_WAKE(
        "acme/widgets", "read", "write", "42", "merge consumed snapshot"
    ) == "dispatched"
    assert len(sleeps) == 1 and 0 < sleeps[0] <= MOG.SELF_WAKE_MIN_INTERVAL_SECONDS
    assert len([call for call in calls if call[0] == "POST"]) == 1


def test_self_wake_unreadable_census_attempts_a_bounded_dispatch(monkeypatch):
    calls: list[str] = []

    def fake_request(method, url, token, payload=None):
        calls.append(method)
        return 502, None

    monkeypatch.setattr(MOG, "_request", fake_request)
    monkeypatch.setattr(MOG.time, "sleep", lambda _seconds: None)
    assert REAL_ENSURE_SELF_WAKE(
        "acme/widgets", "read", "write", "42", "main moved"
    ) == "dispatch-unconfirmed"
    assert calls == ["GET", "POST"]


@pytest.mark.parametrize("terminal", ["merged", "already-merged", "main-moved", "merge-unknown"])
def test_terminal_snapshot_verdict_requests_exactly_one_successor(
    monkeypatch, terminal
):
    _main_harness(monkeypatch, [_pull(1), _pull(2)], verdict=terminal)
    wakes: list[str] = []
    monkeypatch.setattr(
        MOG,
        "ensure_self_wake",
        lambda _r, _read, _write, _run, reason: wakes.append(reason) or "dispatched",
    )
    assert MOG.main() == 0
    assert len(wakes) == 1 and terminal in wakes[0]


def test_cancelled_leased_proof_releases_and_self_wakes_without_sweeping(
    monkeypatch,
):
    issue = {
        "number": 7,
        "updated_at": "2026-08-12T00:59:00Z",
        "pull_request": {"url": "pr"},
        "labels": [
            {"name": MOG.MERGE_ON_GREEN_LABEL},
            {"name": MOG.REFRESH_LEASE_LABEL},
        ],
    }
    pull = _pull(7, labels=(MOG.MERGE_ON_GREEN_LABEL, MOG.REFRESH_LEASE_LABEL))
    calls: list[tuple[str, str]] = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url))
        if "/issues?" in url:
            return 200, [issue]
        if method == "GET" and url.endswith("/pulls/7"):
            return 200, {**pull, "state": "open"}
        if "/check-runs?" in url:
            return 200, {
                "total_count": 1,
                "check_runs": [_run("ci-pack-1", conclusion="cancelled")],
            }
        if method == "DELETE" and "/labels/" in url:
            return 204, None
        raise AssertionError(f"special reconciliation must not call {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    wakes: list[str] = []
    monkeypatch.setattr(
        MOG,
        "ensure_self_wake",
        lambda *_a: wakes.append("wake") or "dispatched",
    )
    assert (
        REAL_LEASE_RECONCILE_PASS(
            "acme/widgets",
            "read",
            "write",
            "a" * 40,
            "cancelled",
            "42",
            "2026-08-12T01:00:00Z",
        )
        == 0
    )
    assert len(calls) == 1 and "/issues?" in calls[0][1]
    assert not [
        call
        for call in calls
        if call[1].endswith("/merge") or call[1].endswith("/update-branch")
    ]
    assert wakes == ["wake"]


def test_cancelled_leased_proof_with_pending_successor_retains_the_lease(
    monkeypatch,
):
    issue = {
        "number": 7,
        "updated_at": "2026-08-12T00:59:00Z",
        "pull_request": {"url": "pr"},
        "labels": [
            {"name": MOG.MERGE_ON_GREEN_LABEL},
            {"name": MOG.REFRESH_LEASE_LABEL},
        ],
    }
    pull = _pull(7, labels=(MOG.MERGE_ON_GREEN_LABEL, MOG.REFRESH_LEASE_LABEL))
    calls: list[tuple[str, str]] = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url))
        if "/issues?" in url:
            return 200, [issue]
        if method == "GET" and url.endswith("/pulls/7"):
            return 200, {**pull, "state": "open"}
        if "/check-runs?" in url:
            return 200, {
                "total_count": 1,
                "check_runs": [_run("ci-pack-1", status="in_progress")],
            }
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    assert (
        REAL_LEASE_RECONCILE_PASS(
            "acme/widgets",
            "read",
            "write",
            "a" * 40,
            "cancelled",
            "42",
            "2026-08-12T01:00:00Z",
        )
        == 0
    )
    assert not [call for call in calls if call[0] != "GET"]


def test_old_cancelled_event_cannot_release_a_newly_claimed_same_head_lease(
    monkeypatch,
):
    issue = {
        "number": 7,
        "updated_at": "2026-08-12T01:01:00Z",
        "pull_request": {"url": "pr"},
        "labels": [
            {"name": MOG.MERGE_ON_GREEN_LABEL},
            {"name": MOG.REFRESH_LEASE_LABEL},
        ],
    }
    pull = _pull(7, labels=(MOG.MERGE_ON_GREEN_LABEL, MOG.REFRESH_LEASE_LABEL))
    calls: list[tuple[str, str]] = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url))
        if "/issues?" in url:
            return 200, [issue]
        if method == "GET" and url.endswith("/pulls/7"):
            return 200, {**pull, "state": "open"}
        raise AssertionError(f"the pre-lease event must stop before checks: {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    assert (
        REAL_LEASE_RECONCILE_PASS(
            "acme/widgets",
            "read",
            "write",
            "a" * 40,
            "cancelled",
            "42",
            "2026-08-12T01:00:00Z",
        )
        == 0
    )
    assert not [call for call in calls if call[0] != "GET"]


@pytest.mark.parametrize(
    "terminal_verdict", ["merged", "already-merged", "main-moved", "merge-unknown"]
)
def test_a_terminal_verdict_consumes_the_immutable_main_snapshot(
    monkeypatch, capsys, terminal_verdict
):
    seen = _main_harness(
        monkeypatch, [_pull(1), _pull(2), _pull(3)], verdict=terminal_verdict
    )
    assert MOG.main() == 0
    assert len(seen) == 1, (
        "a second PR must be judged only after a new sweep rebuilds main freshness"
    )
    out = capsys.readouterr().out
    assert "immutable main freshness snapshot" in out
    assert "snapshot-deferred" in out


def test_a_starved_sweep_defers_with_a_notice_instead_of_going_red(monkeypatch, capsys):
    """(1) The preflight. `GET /rate_limit` does not count against the core budget,
    so asking "can I afford this" is free — and a sweep that cannot afford a useful
    pass must NOT spend its one call discovering that with a 403.

    Exit 0, deliberately. 17 consecutive red runs is how this outage buried its own
    diagnosis: a red here is indistinguishable from a genuinely broken sweeper, and
    it masks the real failures this lane also reports.
    """

    def forbidden(*_a, **_k):
        pytest.fail("a starved sweep must not spend a single call on the backlog")

    monkeypatch.setattr(MOG, "labeled_pulls", forbidden)
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setattr(
        MOG, "core_rate_limit", lambda _t: (MOG.RATE_LIMIT_FLOOR - 1, 1000)
    )
    wakes: list[str] = []
    monkeypatch.setattr(
        MOG,
        "ensure_self_wake",
        lambda *_a: wakes.append("wake") or "dispatched",
    )
    assert MOG.main() == 0, "a quota deferral is not a broken sweep"
    assert wakes == [], "a starved sweep must not recursively amplify itself"
    assert any(
        line.startswith("::notice") and "deferred" in line.lower()
        for line in capsys.readouterr().out.splitlines()
    ), "the no-op must be logged, never silent"


def test_a_healthy_budget_still_sweeps(monkeypatch):
    """The preflight must not be a lock. At the floor exactly, the sweep proceeds."""
    seen = _main_harness(monkeypatch, [_pull(1)], readings=(MOG.RATE_LIMIT_FLOOR,))
    assert MOG.main() == 0
    assert seen == [1]


def test_an_unreadable_rate_limit_fails_OPEN_and_still_sweeps(monkeypatch):
    """The one deliberately fail-OPEN gate in this file.

    Every fail-CLOSED gate here protects a merge; this one protects only a budget,
    and a budget check that wedges the lane whenever GitHub hiccups would be a worse
    outage than the one it prevents. The 403 handling on the real calls is the
    backstop.
    """
    seen = _main_harness(monkeypatch, [_pull(1)])
    monkeypatch.setattr(MOG, "core_rate_limit", lambda _t: None)
    assert MOG.main() == 0
    assert seen == [1]


def test_an_unreadable_rate_limit_uses_the_known_safe_25_pull_fallback(monkeypatch):
    armed = [_pull(number) for number in range(1, MOG.FALLBACK_PULL_CAP + 9)]
    seen = _main_harness(monkeypatch, armed)
    monkeypatch.setattr(MOG, "core_rate_limit", lambda _t: None)
    assert MOG.main() == 0
    assert len(seen) == MOG.FALLBACK_PULL_CAP


def test_the_per_sweep_cap_bounds_the_work_and_names_what_it_deferred(
    monkeypatch, capsys
):
    """(2) The cap. NO SILENT CAPS — a sweep that quietly evaluated a quarter of the
    backlog would look identical in the log to one that evaluated all of it, and that
    difference is the entire reason the lane stopped working."""
    armed = [_pull(number) for number in range(1, MOG.FALLBACK_PULL_CAP + 8)]
    seen = _main_harness(monkeypatch, armed)
    assert MOG.main() == 0

    assert len(seen) == MOG.FALLBACK_PULL_CAP, (
        f"expected at most {MOG.FALLBACK_PULL_CAP} pull requests per sweep, "
        f"got {len(seen)}"
    )
    expected = MOG.sweep_order(armed, cap=MOG.FALLBACK_PULL_CAP)
    assert seen == [pull["number"] for pull in expected[: MOG.FALLBACK_PULL_CAP]]

    deferred = sorted(pull["number"] for pull in expected[MOG.FALLBACK_PULL_CAP :])
    notices = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::notice") and "Per-sweep cap" in line
    ]
    assert notices, "the cap must announce itself"
    assert f"{MOG.FALLBACK_PULL_CAP} of {len(armed)}" in notices[0]
    assert "observed core limit is 1000" in notices[0]
    for number in deferred[:3]:
        assert f"#{number}" in notices[0], f"deferred #{number} must be named"


def test_the_live_enterprise_quota_expands_the_window_to_100(monkeypatch, capsys):
    armed = [_pull(number) for number in range(1, 94)]
    seen = _main_harness(monkeypatch, armed, readings=(14_904,), limit=15_000)
    assert MOG.main() == 0
    assert MOG.pull_cap_for_limit(15_000) == MOG.MAX_PULL_CAP == 100
    assert len(seen) == len(armed), "the measured 29-PR deferral must be gone"
    assert "Per-sweep cap" not in capsys.readouterr().out


def test_the_sweep_stops_cleanly_when_the_budget_runs_out_mid_pass(monkeypatch, capsys):
    """(3) Spend the budget as you go, not only at the start.

    Other lanes read main with the same per-repository GITHUB_TOKEN bucket, so a
    budget that was healthy at preflight can be gone thirty seconds later. Dying
    half-way through on a 403 spends calls the NEXT sweep needed — the loop that
    made this outage self-sustaining.
    """
    armed = [_pull(number) for number in range(1, MOG.FALLBACK_PULL_CAP + 1)]
    # Poll 0 is the preflight, poll 1 is pull request index 0, poll 2 is index
    # BUDGET_RECHECK_EVERY — and by then the budget is gone.
    seen = _main_harness(
        monkeypatch, armed, readings=(1000, 1000, MOG.RATE_LIMIT_RESERVE - 1)
    )
    assert MOG.main() == 0, "running out of budget is not a broken sweep"
    assert len(seen) == MOG.BUDGET_RECHECK_EVERY, (
        "the sweep must stop at the recheck that saw the budget gone, "
        f"got {len(seen)} pull requests"
    )
    out = capsys.readouterr().out
    assert any(
        line.startswith("::warning") and "Stopping after" in line
        for line in out.splitlines()
    ), "a truncated sweep must say so"
    assert "budget-deferred" in out, "and must account for what it did not reach"


def test_a_rate_limited_listing_defers_the_sweep_rather_than_reddening_it(
    monkeypatch, capsys
):
    """The exact 2026-08-07 failure: `labeled_pulls` 403s on call #1.

    That produced `##[error]Could not list pull requests: ... HTTP 403` on 17
    consecutive runs. It is a deferral, not a fault.
    """
    _main_harness(monkeypatch, [_pull(1)])

    def starved(*_a, **_k):
        raise MOG.RateLimited("HTTP 403: primary API quota reached")

    monkeypatch.setattr(MOG, "labeled_pulls", starved)
    assert MOG.main() == 0
    assert any(
        line.startswith("::warning") and "deferred" in line.lower()
        for line in capsys.readouterr().out.splitlines()
    )


def test_a_403_that_is_NOT_a_rate_limit_still_fails_the_run_loudly(monkeypatch, capsys):
    """The fail-closed half of the classifier.

    A 403 with no rate-limit evidence is far more likely a permissions regression.
    Downgrading that to "deferred, exit 0" would hide a genuinely broken lane behind
    a notice — worse than the outage this whole section documents.
    """
    _main_harness(monkeypatch, [_pull(1)])

    def forbidden(*_a, **_k):
        raise MOG._read_failed(
            403, {"message": "Resource not accessible"}, "listing failed"
        )

    monkeypatch.setattr(MOG, "labeled_pulls", forbidden)
    assert MOG.main() == 1
    assert any(
        line.startswith("::error") and "Resource not accessible" in line
        for line in capsys.readouterr().out.splitlines()
    ), "GitHub's own message must reach the log, not a bare status code"


# --- classifying the 403 -------------------------------------------------------
#
# For the whole outage the operator saw `pull-request listing failed: HTTP 403`,
# which reads identically whether the quota is gone, a burst tripped a SECONDARY
# limit, or the token lost a scope. `_request` discarded the body and the headers,
# which are the only place that evidence ever arrives.


def test_an_exhausted_primary_quota_is_recognised_from_the_headers():
    refusal = MOG.rate_limit_refusal(
        403,
        {"message": "API rate limit exceeded for installation ID 1."},
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Limit": "1000"},
    )
    assert isinstance(refusal, MOG.RateLimited)
    assert refusal.secondary is False
    assert "0 of 1000 requests left" in str(refusal)


def test_a_secondary_burst_limit_is_recognised_and_reports_its_retry_after():
    """Named separately because the remedy differs: a secondary limit is about
    request RATE, which a per-sweep cap alone would not fix."""
    refusal = MOG.rate_limit_refusal(
        403,
        {"message": "You have exceeded a secondary rate limit."},
        {"Retry-After": "60"},
    )
    assert isinstance(refusal, MOG.RateLimited)
    assert refusal.secondary is True and refusal.retry_after == 60
    assert "secondary (burst) rate limit" in str(refusal)


def test_a_403_with_no_rate_limit_evidence_is_not_classified_as_one():
    """Positive evidence only. A permissions 403 must stay a hard error."""
    assert (
        MOG.rate_limit_refusal(403, {"message": "Resource not accessible by integration"})
        is None
    )
    assert MOG.rate_limit_refusal(403, None, {"x-ratelimit-remaining": "412"}) is None
    assert MOG.rate_limit_refusal(404, {"message": "Not Found"}) is None


def test_a_rate_limited_read_raises_RateLimited_not_a_bare_runtime_error():
    """`_read_failed` is the single funnel, so the distinction holds everywhere."""
    assert isinstance(
        MOG._read_failed(
            429, {"message": "You have exceeded a secondary rate limit."}, "x"
        ),
        MOG.RateLimited,
    )
    plain = MOG._read_failed(500, {"message": "Server Error"}, "check-run listing failed")
    assert type(plain) is RuntimeError
    assert str(plain) == "check-run listing failed: HTTP 500 (Server Error)"


# --- the order: fair, and useful ----------------------------------------------


def test_the_rotation_reaches_every_pull_request_so_none_can_be_starved():
    """A cap without rotation is a permanent exclusion for the tail of the backlog.

    This script keeps NO state between runs — that property is load-bearing for the
    overlapping-sweep safety argument — so the wall clock is the cursor. The window
    start advances by `cap` each bucket, which tiles the whole ring.
    """
    armed = [_pull(number) for number in range(1, 94)]  # the measured backlog
    cap = MOG.FALLBACK_PULL_CAP
    buckets = -(-len(armed) // cap)  # ceil
    reached: set[int] = set()
    for bucket in range(buckets):
        window = MOG.sweep_order(
            armed,
            now=bucket * MOG.ROTATION_BUCKET_SECONDS,
            cap=cap,
        )
        reached.update(pull["number"] for pull in window[:cap])
    assert reached == {pull["number"] for pull in armed}, (
        f"{len(armed) - len(reached)} pull request(s) were starved across "
        f"{buckets} rotations"
    )


def test_a_main_red_repair_pull_request_is_never_deferred_by_the_cap():
    """The circuit breaker admits exactly ONE repair per sweep when main is red, so
    a repair pushed outside the cap defers the whole repo with it."""
    armed = [_pull(number) for number in range(1, 94)]
    repair = _pull(500, labels=("merge-on-green", "main-red-repair"))
    for bucket in range(12):
        window = MOG.sweep_order(
            armed + [repair], now=bucket * MOG.ROTATION_BUCKET_SECONDS
        )
        assert window[0]["number"] == 500, (
            f"the repair fell to position {[p['number'] for p in window].index(500)}"
        )


def test_the_pull_request_the_trigger_woke_us_for_is_swept_first():
    """`workflow_run` fires because some run went green; that run's own pull request
    is the likeliest merge in the backlog. Putting it first is what stops the cap
    from adding latency to the case the trigger exists to serve."""
    armed = [_pull(number) for number in range(1, 94)]
    hot = _pull(777)
    hot["head"]["sha"] = "f" * 40
    ordered = MOG.sweep_order(armed + [hot], trigger_head_sha="F" * 40, now=0)
    assert ordered[0]["number"] == 777, "case-insensitively, and ahead of the rotation"


def test_the_trigger_head_never_outranks_a_main_red_repair():
    armed = [_pull(1)]
    hot = _pull(777)
    hot["head"]["sha"] = "f" * 40
    repair = _pull(500, labels=("merge-on-green", "main-red-repair"))
    ordered = MOG.sweep_order(armed + [hot, repair], trigger_head_sha="f" * 40, now=0)
    assert [pull["number"] for pull in ordered[:2]] == [500, 777]


def test_the_workflow_hands_the_sweeper_its_triggering_head():
    step = _sweep_step(_workflow())
    assert step["env"]["TRIGGER_HEAD_SHA"] == "${{ github.event.workflow_run.head_sha }}"


def test_the_workflow_hands_the_sweeper_the_triggering_CONCLUSION_too():
    """The mark-only routing lives in the script, not in a second `if:`.

    The job gate decides whether the runner starts; `TRIGGER_CONCLUSION` decides what
    the run DOES. Keeping the branch in Python is what makes it testable at all —
    a workflow-level branch is only provable by observing production.
    """
    step = _sweep_step(_workflow())
    assert step["env"]["TRIGGER_CONCLUSION"] == (
        "${{ github.event.workflow_run.conclusion }}"
    )
    assert step["env"]["CURRENT_RUN_ID"] == "${{ github.run_id }}"


def test_the_dynamic_cap_preserves_the_proven_budget_share():
    """The old 25/1,000 policy scales with the quota and stays bounded at 100.

    The fixed ceiling includes paginated discovery, main proof/baseline reads, the
    repo-wide workflow census, durable lease state, and the maximum 50 main commits
    whose files the freshness classifier may inspect. The per-pull ceiling includes
    five check pages, five PR-file pages, live authorization, ancestry, and lease
    fences. These are pessimistic admission numbers, not typical measured spend.
    Enterprise gives this repository 15,000;
    the 100 ceiling drains the whole current backlog, while a partly spent bucket
    shrinks the window to the work it can actually fund.
    """
    fixed = MOG.FULL_SWEEP_FIXED_REQUESTS
    assert 2 * len(MOG.MAIN_PROOF_WORKFLOWS) + 3 + len(
        MOG.ACTIVE_PR_PROOF_STATUSES
    ) <= fixed, (
        "main_proof + ensure_main_baseline must stay inside the fixed overhead this "
        "floor was sized for"
    )
    # The per-pull ceiling includes proof identity, live compare, lease bookkeeping,
    # check runs, files, merge, settled and update-branch in the refused worst case.
    assert MOG.pull_cap_for_limit(None) == MOG.FALLBACK_PULL_CAP == 25
    assert MOG.pull_cap_for_limit(1_000) == 25
    assert MOG.pull_cap_for_limit(5_000) == MOG.MAX_PULL_CAP
    assert MOG.pull_cap_for_limit(15_000) == MOG.MAX_PULL_CAP == 100

    worst_case = (
        fixed
        + MOG.FALLBACK_PULL_CAP * MOG.MAX_REQUESTS_PER_PULL
        + MOG.MAX_REFRESHES_PER_SWEEP
    )
    assert MOG.RATE_LIMIT_FLOOR >= worst_case * 0.9, (
        f"floor {MOG.RATE_LIMIT_FLOOR} cannot fund a {MOG.FALLBACK_PULL_CAP}-PR pass"
    )
    assert MOG.RATE_LIMIT_FLOOR < 1000, "a floor at the whole bucket never opens"
    assert MOG.RATE_LIMIT_RESERVE < MOG.RATE_LIMIT_FLOOR

    assert MOG.pull_cap_for_budget(14_904, 15_000) == MOG.MAX_PULL_CAP
    assert MOG.pull_cap_for_budget(600, 15_000) == 20
    affordable_cost = (
        MOG.FULL_SWEEP_FIXED_REQUESTS
        + 20 * MOG.MAX_REQUESTS_PER_PULL
        + MOG.MAX_REFRESHES_PER_SWEEP
        + MOG.RATE_LIMIT_RESERVE
    )
    assert affordable_cost <= 600, "the shrunken window must fit the remaining bucket"
    assert MOG.MARK_ONLY_RATE_LIMIT_FLOOR < MOG.RATE_LIMIT_FLOOR


# --- base-inherited reds: the thing that regenerated the backlog ---------------
#
# Every time main went red, every armed PR inherited the failure, and `sweep_pull`
# returned at `blocked` BEFORE reaching the staleness path — so nothing ever
# re-tested them once main was healed. Measured 2026-08-07: of 100 armed PRs,
# ci-pack-2 was red on 62 and ci-pack-3 on 62, both already repaired on main by
# #4752 and #4767. Fleet-wide IDENTICAL failures are a stale base, not 62 bugs.
# They drained only when a human ran `update-branch` on each one by hand.


def test_a_red_inherited_from_a_since_healed_main_is_refreshed_not_blocked(
    monkeypatch, capsys
):
    """The whole point: every failing check green on main => refresh, don't block."""
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-3", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    verdict = MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(),
        _proof("ci-pack-3"), _authorized_budget(),
    )
    assert verdict == "rebased"
    assert any(call[1].endswith("/update-branch") for call in calls), \
        "must fast-forward the stale head"
    posts = [call for call in calls if call[0] == "POST"]
    assert not [c for c in posts if c[1].endswith("/labels")], \
        "a base-inherited red must NOT be labeled merge-blocked"
    assert not [c for c in posts if c[1].endswith("/comments")], \
        "and must NOT burn the one-shot comment"


def test_a_red_main_does_not_share_is_still_blocked(monkeypatch, capsys):
    """The narrowness that keeps this safe.

    One failing check that is NOT clean on main means the red is (or may be) this
    pull request's own, so the unchanged blocking path must run. Refreshing here
    would rebase a genuine regression out of sight.
    """
    pages = {
        1: {
            "total_count": 2,
            "check_runs": [
                _run("ci-pack-3", conclusion="failure"),
                _run("ci-pack-9", conclusion="failure"),
            ],
        }
    }
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    verdict = MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(),
        _proof("ci-pack-3"), _authorized_budget(),
    )
    assert verdict == "blocked"
    assert not any(call[1].endswith("/update-branch") for call in calls), \
        "a genuine red must never be refreshed"


def test_an_unreadable_main_blocks_exactly_as_before(monkeypatch, capsys):
    """Fail-closed: no knowledge of main is never permission to refresh."""
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-3", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    verdict = MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(), _proof()
    )
    assert verdict == "blocked"
    assert not any(call[1].endswith("/update-branch") for call in calls)


def test_a_head_already_current_falls_through_and_cannot_loop(monkeypatch, capsys):
    """update-branch answers 422 when there is nothing to fast-forward.

    That is precisely the case where the red must be the pull request's own, so the
    call falls through to `merge-blocked` — pinned unchanged.

    The STATED REASON has changed, though, and the old one is now repudiated in the
    source. This 422 was once offered as proof that the branch was self-terminating —
    "a PR can never be refreshed twice for the same red". That argument assumes a
    STATIC main. main takes ~24 commits per 2 hours here, so a head stops being
    "already current" within minutes and the 422 stops arriving. What actually
    terminates the branch is `proof_postdates_failures`: a refresh makes the pull
    request's checks newer than main's proof, so it cannot qualify again until main is
    genuinely re-proven. This case is the narrow one where GitHub happens to refuse
    too, not the mechanism.
    """
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-3", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=422)
    verdict = MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(),
        _proof("ci-pack-3"), _authorized_budget(),
    )
    assert verdict == "blocked"
    assert any(call[1].endswith("/update-branch") for call in calls), "it tried"
    assert any(
        call[0] == "POST" and call[1].endswith("/labels") for call in calls
    ), "and then blocked exactly as before"


def test_an_inherited_red_does_not_block_a_head_another_updater_advanced(monkeypatch):
    pages = {
        1: {
            "total_count": 1,
            "check_runs": [_run("ci-pack-3", conclusion="failure")],
        }
    }
    calls = _fake_api(
        monkeypatch,
        check_pages=pages,
        update_status=422,
        pull_payload={"state": "open", "head": {"sha": "b" * 40}},
    )
    verdict = MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(), _proof("ci-pack-3")
    )
    assert verdict == "head-moved"
    assert not [call for call in calls if call[0] == "POST"]


# --- main's proof: resolved from WORKFLOW RUNS, never from a commit walk -------
#
# The refresh above can only fire if the sweeper knows what main currently proves, and
# for its first fortnight it never did. It asked by walking main's last 20 commits for
# one that published `ci-pack-*`, and on this repository that walk CANNOT succeed:
#
#   * ci.yml has no `push` trigger (`on:` is pull_request + workflow_dispatch), so main
#     is proven only by a manual `gh workflow run ci.yml --ref main`, a couple of times
#     a day at best;
#   * the nightly and wire lanes push ~24 `[skip ci]` / path-filtered commits to main
#     per 2 HOURS, publishing ambient checks (`sweep`, `wire`, `immune`, `monitor`, ...)
#     and never a pack.
#
# So the 20-commit window spanned ~100 minutes while main's newest real proof sat 117
# COMMITS / 12 HOURS back. Run live 2026-08-08 the walk returned 18 ambient names and
# ZERO packs, while 31 armed pull requests were blocked on `ci-pack-2` and 29 on
# `ci-pack-3` — all four packs `success` on main's newest ci.yml run (4b61c11a16f8).
# 48 armed pull requests, ~40 also `merge-blocked`, audited by a human every morning.
#
# PR #4968 fixed a different halt condition in the same walk and kept the fixed commit
# budget, so it worked the day it landed and decayed back. These tests pin the property
# that has no window to outgrow: the proof comes from the workflow RUN.


CI_RUN_ID = 31253226496
FENCES_RUN_ID = 31276100400


def _ago(**delta):
    """An ISO-8601 `Z` stamp that many units before now, for the age/interval gates."""
    return (
        (dt.datetime.now(dt.timezone.utc) - dt.timedelta(**delta))
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _wf_run(
    run_id,
    head_sha="c" * 40,
    conclusion="success",
    status="completed",
    created_at=None,
):
    return {
        "id": run_id,
        "head_sha": head_sha,
        "status": status,
        "conclusion": conclusion,
        # The baseline interval gate reads this, so it defaults well outside the floor;
        # a test about the floor passes its own.
        "created_at": created_at or _ago(hours=6),
        "html_url": f"https://example.invalid/{run_id}",
    }


def _job(name, conclusion="success", completed_at=MAIN_PROVED_AT, status="completed"):
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "completed_at": completed_at,
    }


def _proof_api(
    monkeypatch,
    *,
    runs=None,
    jobs=None,
    run_status=None,
    jobs_status=None,
    dispatch_status=204,
    runs_payload=None,
    on_dispatch=None,
):
    """Route the calls `main_proof` makes, plus `ensure_main_baseline`'s.

    `runs` maps workflow file name -> the `workflow_runs` list; `jobs` maps run id ->
    the `jobs` list. `run_status` / `jobs_status` inject an HTTP failure for one
    workflow / run, and `runs_payload` replaces the whole body (for malformed shapes).
    `on_dispatch` is called after a successful dispatch so a test can model what
    GitHub does next — a new run appearing, or that run concluding.

    FOUR PROPERTIES ARE LOAD-BEARING, every one of them added after a mutant survived
    or a reviewer found a shape this could not express.

    The run listing HONOURS `per_page`, so a walk degenerated back to a single newest
    run is visible here rather than hidden by a fake that always returns everything —
    the same trap the old commit-walk fake had to close. It also honours the `status=`
    FILTER, out of one pool of runs: the shipped code queries the newest run at ANY
    status, and an earlier revision queried `status=in_progress` then `status=queued`,
    so a fake that ignored the parameter would let either shape read as correct against
    fixtures written for the other. An unknown run id answers with a NAMED phantom job
    instead of nothing, so a fail-closed path that silently fabricated a run would
    produce a name the assertions can see; without it "returned no names" passed for
    the wrong reason. And a `/commits?` call raises: the proof must never walk main's
    history again, and a test that let it silently do so would be pinning the very
    mechanism this replaced.
    """
    calls: list[tuple[str, str, dict | None]] = []
    pool = {name: list(entries) for name, entries in (runs or {}).items()}

    def fake(method, url, token, payload=None):
        calls.append((method, url, payload))
        if "/commits" in url:
            raise AssertionError(
                "main_proof walked main's commits — that window is exactly what "
                "cannot keep up with ~24 commits/2h against a 12-hour-old proof"
            )
        if "/actions/workflows/" in url and "/runs?" in url:
            workflow = url.split("/actions/workflows/")[1].split("/runs?")[0]
            state = url.rsplit("status=", 1)[1].split("&")[0] if "status=" in url else ""
            asked = int(url.rsplit("per_page=", 1)[1].split("&")[0])
            code = (run_status or {}).get(workflow)
            if code is not None:
                return code, {"message": "no"}
            if runs_payload is not None:
                return 200, runs_payload
            entries = pool.get(workflow, [])
            if state:
                # `status=completed` is GitHub's own alias for "has a conclusion",
                # which INCLUDES cancelled — the whole reason for MAIN_PROOF_RUN_WALK.
                entries = [
                    run for run in entries
                    if str(run.get("status") or "") == state
                ]
            return 200, {"workflow_runs": entries[:asked]}
        if "/actions/runs/" in url and "/jobs" in url:
            run_id = int(url.split("/actions/runs/")[1].split("/jobs")[0])
            code = (jobs_status or {}).get(run_id)
            if code is not None:
                return code, {"message": "no"}
            return 200, {
                "jobs": list((jobs or {}).get(run_id, [_job("phantom-pack")]))
            }
        if url.endswith("/dispatches"):
            if dispatch_status in {201, 204} and on_dispatch is not None:
                on_dispatch(pool, jobs)
            return dispatch_status, None
        raise AssertionError(f"unexpected call {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake)
    return calls


def _both_workflows(ci_jobs, fence_jobs=(("fence-pack", "success"),)):
    """The two-workflow shape `main_proof` reads, as (runs, jobs) fakes."""
    runs = {
        "ci.yml": [_wf_run(CI_RUN_ID)],
        "fences.yml": [_wf_run(FENCES_RUN_ID, head_sha="d" * 40)],
    }
    jobs = {
        CI_RUN_ID: [_job(name, conclusion) for name, conclusion in ci_jobs],
        FENCES_RUN_ID: [_job(name, conclusion) for name, conclusion in fence_jobs],
    }
    return runs, jobs


def test_main_proof_reads_the_packs_off_a_run_no_commit_window_could_reach(
    monkeypatch, capsys
):
    """THE regression test. The proving commit is 117 commits back; the walk is gone.

    Measured 2026-08-08 against this repository: main's newest completed ci.yml run was
    4b61c11a16f8 at 11:20:04Z with all four packs `success`, and it sat 117 commits /
    12 hours behind main's tip because the wire lanes push every few minutes. The old
    20-commit walk returned `['audit','cycle','enrich','flash-crash','harvest','health',
    'heartbeat','immune','ingest','initialize-journal','monitor','project','publish',
    'research-loop','shock','snapshot','sweep','wire']` — eighteen ambient names and not
    one pack — so `bad_names <= main_clean` was false for all 60 pack-red pull requests
    forever.

    The fake here REFUSES `/commits`, so this cannot pass by walking further; and the
    second half asserts the consequence rather than the lookup, because the lookup being
    right is only interesting if a base-inherited red actually gets refreshed.
    """
    runs, jobs = _both_workflows(
        [("ci-pack-0", "success"), ("ci-pack-1", "success"),
         ("ci-pack-2", "success"), ("ci-pack-3", "success")]
    )
    _proof_api(monkeypatch, runs=runs, jobs=jobs)

    proof = MOG.main_proof("acme/widgets", "read")
    assert {"ci-pack-0", "ci-pack-1", "ci-pack-2", "ci-pack-3"} <= proof.clean_names
    assert proof.head_sha == "c" * 40, "the anchor workflow supplies the reported sha"
    assert proof.proved_at is not None

    # …and the refresh it exists to enable actually fires.
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-2", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    assert MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(), proof,
        _authorized_budget(),
    ) == "rebased"
    assert any(call[1].endswith("/update-branch") for call in calls)


def test_the_dynamic_matrix_does_not_weaken_mains_full_baseline(monkeypatch):
    """Main's dispatch still proves all twelve packs, plus the two new names.

    The dynamic matrix narrows what a PULL REQUEST publishes; it must not narrow
    what MAIN proves, because main's clean set is the only thing that can excuse a
    base-inherited red (`bad_names <= proof.clean_names`). The mechanism that keeps
    them separate lives in ci.yml — a `workflow_dispatch` on main passes no
    `--changed-from`, so the planner has no changed-file set, widens to the full
    suite by the fail-safe rule, and emits all twelve indices — but the property
    worth pinning HERE is that the sweeper side collects whatever the run published,
    verbatim and without a name list of its own. `_run_clean_jobs` reads the job
    names straight off the API, so `ci-plan` and `ci-gate` join the proof for free
    and a pack red on a PR still finds its excuse.

    A narrowed baseline is the silent version of the 2026-08-08 backlog: main proves
    fewer names, `bad_names <= clean_names` stops holding, and the armed PRs stop
    draining — with a green main and nothing in the sweep log to explain it.
    """
    packs = [(f"ci-pack-{index}", "success") for index in range(12)]
    runs, jobs = _both_workflows(
        [("ci-plan", "success"), *packs, ("ci-gate", "success")]
    )
    _proof_api(monkeypatch, runs=runs, jobs=jobs)

    proof = MOG.main_proof("acme/widgets", "read")
    expected = {f"ci-pack-{index}" for index in range(12)} | {"ci-plan", "ci-gate"}
    assert expected <= proof.clean_names, (
        "main's full baseline must still prove every pack name a scoped PR can go "
        f"red on; missing {sorted(expected - proof.clean_names)}"
    )
    assert len(expected) == 14
    assert proof.proved_at is not None, "an undatable proof cannot excuse anything"


def test_every_proof_workflow_names_a_file_that_actually_exists():
    """A renamed workflow would make this silently inert AND arm the dispatch loop.

    `main_proof` fails closed on a 404, which is right — but the failure is invisible
    at review time and permanent at run time: the proof goes empty and UNDATED forever,
    which is precisely the state that turned the baseline dispatcher into a loop. The
    file names are a contract with the repository, so pin them against the disk.
    """
    for workflow in MOG.MAIN_PROOF_WORKFLOWS:
        assert (ROOT / ".github" / "workflows" / workflow).is_file(), (
            f"MAIN_PROOF_WORKFLOWS names {workflow}, which does not exist — main would "
            "be unprovable and every base-inherited red would block forever"
        )
    assert MOG.MAIN_BASELINE_WORKFLOW in MOG.MAIN_PROOF_WORKFLOWS, (
        "the dispatched baseline must be one of the workflows the proof is read from, "
        "or the sweeper would order a run whose result it never looks at"
    )
    dispatched = yaml.safe_load(
        (ROOT / ".github" / "workflows" / MOG.MAIN_BASELINE_WORKFLOW).read_text()
    )
    assert "workflow_dispatch" in _triggers(dispatched), (
        f"{MOG.MAIN_BASELINE_WORKFLOW} must accept workflow_dispatch — that is the "
        "only way main is ever proven, since it has no push trigger"
    )


def test_main_proof_costs_four_requests_not_a_twenty_commit_walk(monkeypatch):
    """Cheaper as well as correct, against the quota that starved this lane.

    READ_TOKEN is 1,000 requests/hour PER REPOSITORY, shared by every concurrent sweep;
    on 2026-08-07 the bucket emptied and every later sweep 403'd on its first call. Two
    workflows x (newest run + its jobs) is a fixed 4, where the walk spent up to 20.
    """
    runs, jobs = _both_workflows([("ci-pack-0", "success")])
    calls = _proof_api(monkeypatch, runs=runs, jobs=jobs)
    MOG.main_proof("acme/widgets", "read")
    assert len(calls) == 2 * len(MOG.MAIN_PROOF_WORKFLOWS), [c[1] for c in calls]
    assert len(calls) < 20


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"run_status": {"ci.yml": 403}}, id="403-on-the-run-listing"),
        pytest.param({"run_status": {"ci.yml": 404}}, id="404-on-the-run-listing"),
        pytest.param({"jobs_status": {CI_RUN_ID: 500}}, id="500-on-the-jobs-listing"),
        pytest.param({"runs_payload": {"workflow_runs": []}}, id="no-run-at-all"),
        pytest.param({"runs_payload": ["not", "a", "dict"]}, id="malformed-payload"),
        pytest.param({"runs_payload": {"workflow_runs": [{"nope": 1}]}}, id="run-without-id"),
    ],
)
def test_main_proof_fails_closed_and_never_raises(monkeypatch, kwargs):
    """Not knowing what main proves is never permission to refresh anything.

    An empty `clean_names` can never be a superset of a non-empty failing set, so every
    one of these falls through to the unchanged `merge-blocked` path. And none of them
    may RAISE: this is a diagnostic, and a diagnostic that fails a sweep takes the
    merges down with it.
    """
    runs, jobs = _both_workflows([("ci-pack-0", "success")])
    _proof_api(monkeypatch, runs=runs, jobs=jobs, **kwargs)
    proof = MOG.main_proof("acme/widgets", "read")
    assert proof.clean_names == frozenset()
    assert proof.proved_at is None
    assert proof.source, "a fail-closed proof must still say WHY it is empty"
    # And WHY must be specific. A rate-limited read, a permissions regression and a
    # genuinely absent run all used to render as "has no concluded run on main" — this
    # whole PR exists because a mechanism was inert AND its log could not say why.
    injected = {**kwargs.get("run_status", {}), **kwargs.get("jobs_status", {})}
    for code in injected.values():
        assert str(code) in proof.source, (
            f"HTTP {code} must reach the sweep log, not be flattened into "
            f"{proof.source!r}"
        )
    assert "no clean" not in proof.source, (
        "an unreadable run must never be reported as a run that proved nothing — "
        "those have opposite causes and opposite fixes"
    )


def test_main_proof_fails_closed_when_the_lookup_itself_explodes(monkeypatch):
    """Including on an exception the fake shapes above cannot produce."""

    def boom(*_a, **_k):
        raise ValueError("kaboom")

    monkeypatch.setattr(MOG, "_request", boom)
    proof = MOG.main_proof("acme/widgets", "read")
    assert proof.clean_names == frozenset() and proof.proved_at is None
    assert "kaboom" in proof.source


def test_a_half_readable_proof_is_no_proof(monkeypatch):
    """fences.yml unreadable must not leave ci.yml's names standing.

    `fence-pack` is a refreshable red like any pack, so a proof missing the fences half
    would excuse a fences failure with evidence that says nothing about fences.
    """
    runs, jobs = _both_workflows([("ci-pack-0", "success")])
    _proof_api(monkeypatch, runs=runs, jobs=jobs, run_status={"fences.yml": 500})
    assert MOG.main_proof("acme/widgets", "read").clean_names == frozenset()


def test_the_proof_unions_both_workflows_and_dates_itself_by_the_OLDER(monkeypatch):
    """fences.yml runs on every push to main; ci.yml is dispatched by hand.

    So the fences half is minutes old and the ci half can be half a day old. Taking the
    NEWER instant would date the ci evidence by the fences evidence and launder a stale
    proof — the same mistake as letting one fresh component re-date a stale sibling.
    A proof is as fresh as its stalest component.
    """
    runs, jobs = _both_workflows(
        [("ci-pack-0", "success"), ("ci-pack-1", "success")],
        fence_jobs=(("fence-pack", "success"),),
    )
    jobs[CI_RUN_ID] = [
        _job("ci-pack-0", completed_at="2026-08-08T11:20:03Z"),
        _job("ci-pack-1", completed_at="2026-08-08T11:11:40Z"),
    ]
    jobs[FENCES_RUN_ID] = [_job("fence-pack", completed_at="2026-08-08T20:13:21Z")]
    _proof_api(monkeypatch, runs=runs, jobs=jobs)

    proof = MOG.main_proof("acme/widgets", "read")
    assert proof.clean_names == frozenset({"ci-pack-0", "ci-pack-1", "fence-pack"})
    assert proof.proved_at == MOG._parse_dt("2026-08-08T11:20:03Z"), (
        "the proof took the fences instant and laundered a 9-hour-old ci proof"
    )
    assert "ci.yml@" in proof.source and "fences.yml@" in proof.source


def test_a_cancelled_newest_run_does_not_zero_the_proof(monkeypatch):
    """`status=completed` includes `cancelled`, and fences.yml cancels constantly.

    It runs on every push to main under `cancel-in-progress: true`, so on a branch
    taking ~24 commits per 2 hours a large minority of its runs are superseded rather
    than judged — measured 2026-08-08, 2 of the newest 8. A `per_page=1` read would
    land on one about a quarter of the time and, fail-closed, zero the entire proof:
    an intermittently inert mechanism, which is worse to diagnose than a dead one.
    This file has already paid for that lesson once — `integration_baseline_state`
    latched the breaker red for 8.5 hours on a cancelled newest run.
    """
    runs, jobs = _both_workflows([("ci-pack-0", "success")])
    runs["fences.yml"] = [
        _wf_run(999, conclusion="cancelled"),
        _wf_run(FENCES_RUN_ID, head_sha="d" * 40),
    ]
    jobs[999] = [_job("fence-pack", "cancelled", completed_at=None)]
    _proof_api(monkeypatch, runs=runs, jobs=jobs)
    assert "fence-pack" in MOG.main_proof("acme/widgets", "read").clean_names, (
        "the walk must reach past the superseded run; MAIN_PROOF_RUN_WALK is what "
        "keeps a `per_page=1` read from zeroing the proof a quarter of the time"
    )


def test_the_proof_is_per_JOB_so_a_red_run_still_proves_its_green_packs(monkeypatch):
    """A run whose overall conclusion is `failure` still proves the packs that passed.

    This is most of why the jobs endpoint is read at all: main with `ci-pack-2` green
    and `ci-pack-3` red must refresh the pull requests red on 2 and keep blocking the
    ones red on 3. A run-level conclusion cannot express that.
    """
    runs, jobs = _both_workflows(
        [("ci-pack-2", "success"), ("ci-pack-3", "failure")]
    )
    runs["ci.yml"] = [_wf_run(CI_RUN_ID, conclusion="failure")]
    _proof_api(monkeypatch, runs=runs, jobs=jobs)
    clean = MOG.main_proof("acme/widgets", "read").clean_names
    assert "ci-pack-2" in clean and "ci-pack-3" not in clean


def test_a_SKIPPED_job_on_main_is_not_proof_that_main_is_green(monkeypatch):
    """AN ABSENCE OF FAILURE IS NOT A PASS — #4779, applied where it was still missing.

    This test previously asserted the opposite, and the earlier reasoning was that
    `main_proof` should mirror `CLEAN_CONCLUSIONS`. That was wrong, and the constant's
    OWN comment says why: membership there means "did not fail" and NEVER "passed",
    with `decide_verdict` supplying a separate affirmative-pass requirement. There is
    no such backstop here. `clean_names` IS the assertion "main is green on this name",
    and it is spent excusing that name's red on a pull request — so a job that did not
    run cannot be in it, and `PROOF_CLEAN_CONCLUSIONS` is deliberately `{"success"}`.

    `CLEAN_CONCLUSIONS` itself must NOT be narrowed to match: a path-filtered pack that
    skips on a PR head is a real clean result there.

    It is not exploitable today, and only by accident: GitHub reports fences.yml's
    fork-fallback jobs under their UNEVALUATED `name:` expression, so their `skipped`
    conclusions cannot collide with a real check name. The first statically-named
    conditional or path-filtered job added to ci.yml or fences.yml would end that.
    """
    runs, jobs = _both_workflows([("ci-pack-0", "success")])
    jobs[CI_RUN_ID] = [
        _job("ci-pack-0", "success"),
        _job("Workers Builds: macro", "success"),
        _job("ci-pack-1", None, status="in_progress", completed_at=None),
        _job("ci-pack-2", "failure"),
        _job("ci-pack-4", "skipped"),
        _job("ci-pack-5", "neutral"),
    ]
    _proof_api(monkeypatch, runs=runs, jobs=jobs)
    clean = MOG.main_proof("acme/widgets", "read").clean_names
    assert "ci-pack-4" not in clean, (
        "a job that was SKIPPED on main produced no verdict; treating it as proof "
        "would excuse a pull request's red on a check that never ran"
    )
    assert "ci-pack-5" not in clean, "nor does `neutral` affirmatively pass"
    assert clean == frozenset({"ci-pack-0", "fence-pack"})
    assert MOG.CLEAN_CONCLUSIONS >= {"success", "neutral", "skipped"}, (
        "decide_verdict still needs the wider set — a path-filtered pack that skips "
        "on a PR head is a real clean result there"
    )


def test_an_undatable_clean_job_makes_the_whole_proof_undatable(monkeypatch):
    """The instant is the loop guard, so it may never be optimistically inferred.

    Dating the proof by the jobs that DID carry a stamp would let a refresh claim main
    was healed after a failure on evidence that does not say when it was computed.
    """
    runs, jobs = _both_workflows([("ci-pack-0", "success"), ("ci-pack-1", "success")])
    jobs[CI_RUN_ID] = [
        _job("ci-pack-0", completed_at=MAIN_PROVED_AT),
        _job("ci-pack-1", completed_at="not-a-timestamp"),
    ]
    _proof_api(monkeypatch, runs=runs, jobs=jobs)
    proof = MOG.main_proof("acme/widgets", "read")
    assert proof.proved_at is None
    assert "ci-pack-0" in proof.clean_names, "the NAMES are still usable; the date is not"
    # …and the summary must say both, separately. Collapsing an undated proof to
    # "none" is how the dispatch-loop incident reported "never proven" about a main
    # that had just been proven red: the names and the date fail independently.
    described = proof.describe()
    assert "undated" in described and "clean name" in described, described


# --- the timestamp rule: a proof that predates the red does not excuse it -------


def test_a_base_inherited_red_is_refreshed_when_main_was_proven_AFTER_it(
    monkeypatch, capsys
):
    """The whole point, stated in time as well as in names."""
    pages = {
        1: {
            "total_count": 1,
            "check_runs": [
                _run("ci-pack-3", conclusion="failure", completed_at=CHECKS_CONCLUDED_AT)
            ],
        }
    }
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    verdict = MOG.sweep_pull(
        "acme/widgets",
        _pull(),
        "read",
        "write",
        _freshness(),
        _proof("ci-pack-3", proved_at=MAIN_PROVED_AT),
        _authorized_budget(),
    )
    assert verdict == "rebased"
    assert any(call[1].endswith("/update-branch") for call in calls)


def test_a_proof_that_PREDATES_the_red_never_refreshes_it(monkeypatch, capsys):
    """The correctness half AND the loop guard, in one shape.

    Correctness: "your red checks are all green on main" only means "main was healed
    since you ran" if the healing proof is NEWER than the red. A main proven green
    BEFORE this head ran is evidence the red is the pull request's OWN, and refreshing
    it rebases a genuine regression out of sight.

    Loop guard: the old comment argued no loop was possible because `update-branch`
    answers 422 on an already-current head. That assumes a STATIC main. main takes ~24
    commits per 2 hours here, so a head is never "already current" for long and a PR
    that came back red on the same pack would be refreshed again on the next sweep — 4
    hosted packs x ~60 pull requests per round, indefinitely, on a pool that takes
    30-34 minutes per run. With this rule a refresh makes the checks newer than the
    proof, so nothing can be refreshed twice until main is genuinely re-proven.
    """
    pages = {
        1: {
            "total_count": 1,
            "check_runs": [
                _run("ci-pack-3", conclusion="failure", completed_at=CHECKS_CONCLUDED_AT)
            ],
        }
    }
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    verdict = MOG.sweep_pull(
        "acme/widgets",
        _pull(),
        "read",
        "write",
        _freshness(),
        _proof("ci-pack-3", proved_at=MAIN_PROVED_BEFORE_THE_CHECKS),
    )
    assert verdict == "blocked", "a green main from BEFORE the red does not excuse it"
    assert not any(call[1].endswith("/update-branch") for call in calls)


def test_a_stale_proof_says_so_in_a_greppable_line(monkeypatch, capsys):
    """"the proof is too old" and "this red is yours" are indistinguishable in the
    `merge-blocked` comment, and mistaking the first for the second is the audit that
    cost a human every morning. The log must separate them by name."""
    pages = {
        1: {
            "total_count": 1,
            "check_runs": [
                _run("ci-pack-3", conclusion="failure", completed_at=CHECKS_CONCLUDED_AT)
            ],
        }
    }
    _fake_api(monkeypatch, check_pages=pages, update_status=202)
    MOG.sweep_pull(
        "acme/widgets",
        _pull(),
        "read",
        "write",
        _freshness(),
        _proof("ci-pack-3", proved_at=MAIN_PROVED_BEFORE_THE_CHECKS),
    )
    out = capsys.readouterr().out
    assert "main-proof-too-old" in out, "the diagnosis needs a stable grep token"
    assert MAIN_PROVED_BEFORE_THE_CHECKS[:19] in out, "name main's instant"
    assert CHECKS_CONCLUDED_AT[:19] in out, "and the checks' instant"


def test_an_undated_failing_check_blocks_rather_than_refreshing(monkeypatch):
    """Fail closed on the timestamp exactly as on the names.

    A failing check with no usable `completed_at` cannot be shown to predate main's
    proof, and "cannot be shown" is never "may be refreshed".
    """
    pages = {
        1: {
            "total_count": 2,
            "check_runs": [
                _run("ci-pack-3", conclusion="failure", completed_at=CHECKS_CONCLUDED_AT),
                _run("ci-pack-2", conclusion="failure", completed_at=None),
            ],
        }
    }
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    verdict = MOG.sweep_pull(
        "acme/widgets",
        _pull(),
        "read",
        "write",
        _freshness(),
        _proof("ci-pack-2", "ci-pack-3", proved_at=MAIN_PROVED_AT),
    )
    assert verdict == "blocked"
    assert not any(call[1].endswith("/update-branch") for call in calls)


def test_an_undated_MAIN_proof_blocks_rather_than_refreshing(monkeypatch):
    """The other half of the same rule: an undatable proof postdates nothing."""
    pages = {
        1: {
            "total_count": 1,
            "check_runs": [
                _run("ci-pack-3", conclusion="failure", completed_at=CHECKS_CONCLUDED_AT)
            ],
        }
    }
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    verdict = MOG.sweep_pull(
        "acme/widgets",
        _pull(),
        "read",
        "write",
        _freshness(),
        _proof("ci-pack-3", proved_at=None),
    )
    assert verdict == "blocked"
    assert not any(call[1].endswith("/update-branch") for call in calls)


def test_a_blocked_pull_request_records_what_it_was_blocked_ON(monkeypatch):
    """`sweep_pull` fills the out-parameter `ensure_main_baseline` decides on.

    Pinned separately from the wiring test below, which stubs `sweep_pull` and so
    cannot see this half. Without the recording, `blocked_names` is always empty and
    condition (2) never holds: the sweeper would never order a baseline no matter how
    stale its proof or how large its backlog — inert in exactly the way this whole
    repair is about.
    """
    pages = {
        1: {
            "total_count": 2,
            "check_runs": [
                _run("ci-pack-3", conclusion="failure"),
                _run("ci-pack-9", conclusion="failure"),
            ],
        }
    }
    _fake_api(monkeypatch, check_pages=pages, update_status=422)
    recorded: set[str] = set()
    verdict = MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(), _proof(), None, recorded
    )
    assert verdict == "blocked"
    assert recorded == {"ci-pack-3", "ci-pack-9"}


def test_proof_postdates_failures_is_pure_and_fail_closed():
    """The comparison on its own, without a sweep around it."""
    failing = [_run("ci-pack-3", conclusion="failure", completed_at=CHECKS_CONCLUDED_AT)]
    assert MOG.proof_postdates_failures(_proof(proved_at=MAIN_PROVED_AT), failing)
    assert not MOG.proof_postdates_failures(
        _proof(proved_at=MAIN_PROVED_BEFORE_THE_CHECKS), failing
    )
    assert not MOG.proof_postdates_failures(_proof(proved_at=None), failing)
    assert not MOG.proof_postdates_failures(_proof(proved_at=CHECKS_CONCLUDED_AT), failing), (
        "an exactly-simultaneous proof is not evidence the red was healed"
    )
    assert not MOG.proof_postdates_failures(_proof(proved_at=MAIN_PROVED_AT), []), (
        "nothing failing is nothing to excuse"
    )
    assert not MOG.proof_postdates_failures(
        _proof(proved_at=MAIN_PROVED_AT),
        [_run("ci-pack-3", conclusion="failure", completed_at="")],
    )


# --- the sweeper orders the baseline its own refresh depends on ----------------
#
# Parts A and B are only as good as the freshness of main's proof, and until now that
# proof existed only when a human ran `gh workflow run ci.yml --ref main`. ci.yml has no
# `push` trigger, so nothing else re-proves main at all: measured 2026-08-08 the newest
# proof was 12 hours old while 48 pull requests sat armed. Repairing the lookup without
# repairing the supply would have fixed the mechanism and kept the daily audit.


def _aged_proof(hours, *names):
    """A proof `hours` old (None = undated)."""
    when = None if hours is None else dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    return MOG.MainProof(frozenset(names or ("ci-pack-0",)), when, "a" * 40, "test")


def _dispatched(calls):
    return [call for call in calls if call[0] == "POST" and call[1].endswith("/dispatches")]


def _baseline_api(monkeypatch, newest=None, **kwargs):
    """`_proof_api` with only the dispatch target's run list, for the gate tests.

    `newest` is the newest ci.yml run on main — the ONE thing the shipped gate reads.
    Default: concluded, and created well outside the interval floor, so a test that is
    not about the gate gets a dispatch.
    """
    runs = {"ci.yml": [] if newest is False else [newest or _wf_run(1)]}
    return _proof_api(monkeypatch, runs=runs, **kwargs)


def test_a_stale_proof_that_cost_the_sweep_something_orders_a_baseline(
    monkeypatch, capsys
):
    calls = _baseline_api(monkeypatch)
    outcome = MOG.ensure_main_baseline(
        "acme/widgets", _aged_proof(12), {"ci-pack-2", "ci-pack-3"}, "write"
    )
    assert outcome == "dispatched"
    posted = _dispatched(calls)
    assert len(posted) == 1, calls
    assert posted[0][1].endswith(f"/workflows/{MOG.MAIN_BASELINE_WORKFLOW}/dispatches")
    assert posted[0][2] == {"ref": "main"}
    assert any(
        line.startswith("::notice") and "Dispatched" in line
        for line in capsys.readouterr().out.splitlines()
    ), "an order this lane places must be visible in the Actions summary"


def test_an_undated_proof_also_orders_a_baseline_and_never_calls_it_never_proven(
    monkeypatch, capsys
):
    """An undated proof still orders one — but the notice must not invent a cause.

    "never proven" was printed on a main that HAD been proven, and proven RED; an
    operator reading that goes looking for a missing dispatch instead of a broken main.
    The proof's own `source` is what distinguishes the two, so it has to be in the line.
    """
    _baseline_api(monkeypatch)
    proof = MOG.MainProof(frozenset(), None, "a" * 40, "ci.yml@abcdef (RED: nothing passed)")
    assert MOG.ensure_main_baseline(
        "acme/widgets", proof, {"ci-pack-2"}, "write"
    ) == "dispatched"
    notice = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("::notice")
    ]
    assert notice and "never proven" not in notice[0], notice
    assert "RED: nothing passed" in notice[0], "the log must carry the actual cause"


def test_a_fresh_proof_orders_nothing(monkeypatch):
    """A ci.yml run takes 30-34 minutes, so the age gate must not fire on a proof that
    is merely mid-flight — and a repository whose main is proven is not a problem."""
    calls = _baseline_api(monkeypatch)
    outcome = MOG.ensure_main_baseline(
        "acme/widgets", _aged_proof(MOG.MAIN_PROOF_MAX_AGE_HOURS - 0.5), {"ci-pack-2"}, "write"
    )
    assert outcome.startswith("not needed")
    assert not calls, "a fresh proof must not spend a single call"


def test_an_idle_sweep_orders_nothing_however_old_the_proof_is(monkeypatch):
    """Condition 2. Staleness only matters if it COST something this pass; otherwise a
    quiet repository would dispatch a 30-minute pack run every two minutes forever."""
    calls = _baseline_api(monkeypatch)
    outcome = MOG.ensure_main_baseline("acme/widgets", _aged_proof(99), set(), "write")
    assert outcome.startswith("not needed")
    assert not calls


@pytest.mark.parametrize("state", ["in_progress", "queued", "requested", "waiting", "pending"])
def test_a_baseline_that_has_not_CONCLUDED_is_never_stampeded(monkeypatch, state):
    """THE anti-stampede guard, and it gates on the newest run's status whatever that
    status is called.

    The earlier revision asked two questions — `status=in_progress` then
    `status=queued` — which left `requested`, `waiting` and `pending` unchecked, cost
    two calls, and was still a read-then-write race. One "what is the newest run doing"
    query covers every state GitHub has, present and future.
    """
    calls = _baseline_api(monkeypatch, newest=_wf_run(1, status=state, conclusion=None))
    outcome = MOG.ensure_main_baseline(
        "acme/widgets", _aged_proof(12), {"ci-pack-2"}, "write"
    )
    assert outcome == f"skipped (the newest baseline is {state})"
    assert not _dispatched(calls)


def test_a_baseline_ordered_inside_the_interval_floor_is_not_re_ordered(monkeypatch):
    """The bound that survives the race the status check cannot win.

    Current full sweeps coalesce, but pre-deploy/out-of-band actors can still all
    read "nothing in flight" and dispatch.
    Until 2026-08-09 that was catastrophic — ci.yml cancelled newest-wins on every
    ref, so the SECOND dispatch on main CANCELLED THE FIRST (31148430602 /
    31151246743, 53 minutes apart; then the 2026-08-09 cascade where no main proof
    could conclude at all). #5136 keeps a dispatch's in-flight proof uncancellable,
    so the racing loser only overwrites the queued pending slot — still a discarded
    queue position and spent quota, which this floor bounds.

    It also covers the window where a dispatch has succeeded but its run is not yet
    visible in the API — which the status check, reading only visible runs, cannot.
    """
    calls = _baseline_api(monkeypatch, newest=_wf_run(1, created_at=_ago(minutes=5)))
    outcome = MOG.ensure_main_baseline(
        "acme/widgets", _aged_proof(12), {"ci-pack-2"}, "write"
    )
    assert outcome.startswith("skipped (a baseline was ordered 5 min ago"), outcome
    assert not _dispatched(calls)


def test_a_baseline_older_than_the_interval_floor_may_be_re_ordered(monkeypatch):
    """The floor is a bound, not a latch — it must open again."""
    calls = _baseline_api(
        monkeypatch,
        newest=_wf_run(1, created_at=_ago(minutes=MOG.MAIN_BASELINE_MIN_INTERVAL_MINUTES + 1)),
    )
    assert MOG.ensure_main_baseline(
        "acme/widgets", _aged_proof(12), {"ci-pack-2"}, "write"
    ) == "dispatched"
    assert _dispatched(calls)


def test_the_interval_gate_reads_one_call_not_two(monkeypatch):
    """Against the READ/MERGE budget, and against the two-query race it replaced."""
    calls = _baseline_api(monkeypatch)
    MOG.ensure_main_baseline("acme/widgets", _aged_proof(12), {"ci-pack-2"}, "write")
    gets = [call for call in calls if call[0] == "GET"]
    assert len(gets) == 1, [call[1] for call in gets]
    assert "status=" not in gets[0][1], (
        "the gate must see the newest run whatever its status — a status-filtered "
        "query cannot distinguish `requested` from `nothing running`"
    )


@pytest.mark.parametrize(
    "kwargs, why",
    [
        ({"run_status": {"ci.yml": 403}}, "an unreadable listing"),
        ({"newest": _wf_run(1, created_at=None) | {"created_at": "not-a-date"}},
         "an undatable newest run"),
    ],
)
def test_an_unreadable_baseline_state_does_not_dispatch(monkeypatch, kwargs, why):
    """Fail toward NOT stampeding: one sweep of latency costs ~2 minutes, and the
    interval is the only bound on the dispatch rate — unenforceable means refuse."""
    calls = _baseline_api(monkeypatch, **kwargs)
    outcome = MOG.ensure_main_baseline(
        "acme/widgets", _aged_proof(12), {"ci-pack-2"}, "write"
    )
    assert outcome.startswith("skipped"), why
    assert not _dispatched(calls)


def test_a_repository_with_no_baseline_run_at_all_still_dispatches(monkeypatch):
    """The gate must not deadlock a repo that has never run one."""
    calls = _baseline_api(monkeypatch, newest=False)
    assert MOG.ensure_main_baseline(
        "acme/widgets", _aged_proof(None), {"ci-pack-2"}, "write"
    ) == "dispatched"
    assert _dispatched(calls)


def test_a_failed_dispatch_is_logged_and_never_fatal(monkeypatch, capsys):
    """A sweep that merged pull requests correctly must not go red because it could not
    order a baseline."""
    _baseline_api(monkeypatch, dispatch_status=422)
    outcome = MOG.ensure_main_baseline(
        "acme/widgets", _aged_proof(12), {"ci-pack-2"}, "write"
    )
    assert outcome == "dispatch failed (HTTP 422)"
    assert any(
        line.startswith("::warning") for line in capsys.readouterr().out.splitlines()
    )


def test_an_all_red_main_cannot_loop_the_dispatcher(monkeypatch):
    """THE BLOCKER, reproduced end to end: a red main used to order baselines forever.

    An earlier revision let `_run_clean_jobs` return `None` for two different facts —
    "I could not read this run" and "I read it and every job failed" — and `main_proof`
    dated both `None`. `MainProof.age_hours` was then None, so the
    `age <= MAIN_PROOF_MAX_AGE_HOURS` gate could not fire; every sweep with a blocked
    pull request dispatched, the run came back red, and the next sweep dispatched
    again. Measured against the live shape of run 31220410022 (all four packs
    `failure`), 10 dispatches in 10 consecutive sweeps — and 4 of the newest 10 main
    ci.yml runs were `failure`, so this is the ordinary state of a red main, not a
    corner. Steady state ~164 hosted jobs/day against an intended ceiling of 8.

    The model here is the production steady state, which is what makes it a loop rather
    than a one-off: each dispatch produces a run that CONCLUDES RED, so nothing is ever
    "in flight" by the time the next sweep looks, and the newest run is always freshly
    created. Both repairs are load-bearing under it — the proof is now DATED by an
    all-red run (so the age gate closes it) and MAIN_BASELINE_MIN_INTERVAL_MINUTES
    bounds the rate even if it were not.

    Asserts the BOUND across the whole window, not which sweep won it: a test that
    pinned "sweep 1 dispatched" would go green on an implementation that dispatched on
    sweep 7 instead, and the invariant that matters is the total.
    """
    sweeps = 10
    red_jobs = [
        _job(f"ci-pack-{index}", "failure", completed_at=_ago(hours=12)) for index in range(4)
    ]
    runs = {
        "ci.yml": [_wf_run(CI_RUN_ID, conclusion="failure", created_at=_ago(hours=12))],
        "fences.yml": [_wf_run(FENCES_RUN_ID, head_sha="d" * 40, created_at=_ago(hours=12))],
    }
    jobs = {
        CI_RUN_ID: red_jobs,
        FENCES_RUN_ID: [_job("fence-pack", "success", completed_at=_ago(hours=12))],
    }

    def concluded_red(pool, job_table):
        # What GitHub actually does next on a repository whose main is broken: the
        # ordered baseline runs, fails, and is the newest COMPLETED run again.
        pool["ci.yml"] = [
            _wf_run(CI_RUN_ID, conclusion="failure", created_at=_ago(seconds=1))
        ]
        job_table[CI_RUN_ID] = [
            _job(f"ci-pack-{index}", "failure", completed_at=_ago(seconds=1))
            for index in range(4)
        ]

    calls = _proof_api(monkeypatch, runs=runs, jobs=jobs, on_dispatch=concluded_red)
    for _ in range(sweeps):
        proof = MOG.main_proof("acme/widgets", "read")
        MOG.ensure_main_baseline("acme/widgets", proof, {"ci-pack-2"}, "write")

    ordered = len(_dispatched(calls))
    assert ordered <= 1, (
        f"a red main ordered {ordered} baselines in {sweeps} sweeps; at this rate the "
        "sweeper re-proves a main it has already proven red, forever"
    )


def test_an_all_red_baseline_is_dated_but_proves_nothing(monkeypatch):
    """The two halves of the blocker's fix, asserted separately.

    Empty `clean_names` is the CORRECT answer for a red main — nothing may be refreshed
    against it. A `None` date is not: main WAS proven, and pretending otherwise is what
    unbounded the dispatcher. Only an unreadable run may be undated.
    """
    runs, jobs = _both_workflows([(f"ci-pack-{index}", "failure") for index in range(4)])
    jobs[CI_RUN_ID] = [
        _job(f"ci-pack-{index}", "failure", completed_at="2026-08-07T22:06:43Z")
        for index in range(4)
    ]
    # fences is the fresher half, so the union's instant is the ci one — which only
    # exists at all because an all-red run is still dated.
    jobs[FENCES_RUN_ID] = [_job("fence-pack", "success", completed_at="2026-08-08T20:13:21Z")]
    _proof_api(monkeypatch, runs=runs, jobs=jobs)
    proof = MOG.main_proof("acme/widgets", "read")
    assert not any(name.startswith("ci-pack") for name in proof.clean_names), (
        "a failed pack must never be proof"
    )
    assert proof.proved_at is not None, (
        "an all-red baseline is PROVEN — dating it None makes the age gate unfireable"
    )
    assert proof.proved_at == MOG._parse_dt("2026-08-07T22:06:43Z")
    assert "RED" in proof.source, "and the log must say which workflow was red"
    # The other workflow's genuine green survives: a red ci.yml is information about
    # ci.yml, not a reason to discard fences.yml's verdict.
    assert "fence-pack" in proof.clean_names


def test_a_raising_dispatch_is_swallowed(monkeypatch, capsys):
    def boom(*_a, **_k):
        raise ConnectionError("no route")

    monkeypatch.setattr(MOG, "_request", boom)
    assert MOG.ensure_main_baseline(
        "acme/widgets", _aged_proof(12), {"ci-pack-2"}, "write"
    ) == "dispatch error"


def test_the_sweep_orders_the_baseline_AFTER_it_learns_what_it_could_not_answer(
    monkeypatch, capsys
):
    """Wired into `main()` once per sweep, and positioned after the pull-request pass.

    Called BEFORE the pass it would always see an empty `blocked_names` and could never
    dispatch — the mechanism would be inert in a way that reviews as working, which is
    precisely the failure mode this whole PR is about.
    """
    seen: dict[str, object] = {}

    def fake_sweep(_repo, pull, _read, _write, _fresh, _proof=None, _budget=None,
                   blocked=None):
        if blocked is not None:
            blocked.add("ci-pack-2")
        return "blocked"

    def fake_baseline(_repo, _proof, blocked_names, _token):
        seen["blocked"] = set(blocked_names)
        seen["calls"] = seen.get("calls", 0) + 1
        return "dispatched"

    _main_harness(monkeypatch, [_pull(1), _pull(2)])
    monkeypatch.setattr(MOG, "sweep_pull", fake_sweep)
    monkeypatch.setattr(MOG, "ensure_main_baseline", fake_baseline)
    assert MOG.main() == 0
    assert seen["calls"] == 1, "once per sweep, not once per pull request"
    assert seen["blocked"] == {"ci-pack-2"}, (
        "the dispatch decision must see what the sweep was unable to answer"
    )
    summary = [
        line for line in capsys.readouterr().out.splitlines()
        if line.startswith("merge-on-green sweep complete")
    ]
    assert summary and "baseline: dispatched" in summary[0], (
        "the new state must be visible in the sweep summary"
    )
    assert "main proof:" in summary[0]


# --- the two halves interact: refreshes cost budget AND CI runs ---------------


def test_the_refresh_budget_is_capped_because_each_one_launches_a_ci_run(
    monkeypatch, capsys
):
    """Uncapped, the first sweep after the base-inherited-red fix shipped would have
    queued 84 pack runs onto an already-saturated pool from a single sweep — and
    spent 84 write calls out of a 1,000/hr bucket doing it."""
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-3", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    budget = MOG.SweepBudget("read", max_refreshes=2)
    budget.refresh_authorized = True

    verdicts = [
        MOG.sweep_pull(
            "acme/widgets",
            _pull(number),
            "read",
            "write",
            _freshness(),
            _proof("ci-pack-3"),
            budget,
        )
        for number in (1, 2, 3, 4)
    ]
    assert verdicts == ["rebased", "rebased", "refresh-deferred", "refresh-deferred"]
    assert len([c for c in calls if c[1].endswith("/update-branch")]) == 2
    assert budget.refreshes_used == 2


def test_the_DEFAULT_budget_caps_refreshes_at_the_constant(monkeypatch):
    """The cap that actually ships is the DEFAULT one, and `main()` builds its budget
    with no `max_refreshes` argument.

    Pinned separately because every other test in this section passes an explicit
    `max_refreshes=`, so raising the default to something absurd would leave all of
    them green while the shipped sweeper refreshed the whole backlog in one pass —
    which is the exact 84-CI-runs-from-one-sweep failure this cap exists to prevent.
    """
    assert MOG.SweepBudget("read").max_refreshes == MOG.MAX_REFRESHES_PER_SWEEP

    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-3", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    budget = MOG.SweepBudget("read")
    budget.refresh_authorized = True
    verdicts = [
        MOG.sweep_pull(
            "acme/widgets",
            _pull(number),
            "read",
            "write",
            _freshness(),
            _proof("ci-pack-3"),
            budget,
        )
        # deliberately more armed pull requests than the cap, as in the real backlog
        for number in range(1, MOG.MAX_REFRESHES_PER_SWEEP + 6)
    ]
    refreshed = [c for c in calls if c[1].endswith("/update-branch")]
    assert len(refreshed) == MOG.MAX_REFRESHES_PER_SWEEP, (
        f"a default sweep launched {len(refreshed)} CI runs; the cap is "
        f"{MOG.MAX_REFRESHES_PER_SWEEP}"
    )
    assert verdicts.count("refresh-deferred") == 5


def test_a_refresh_deferred_pull_request_is_never_labeled_or_accused(
    monkeypatch, capsys
):
    """It did nothing wrong — this sweep merely ran out of slots. `mark_blocked`'s
    comment is one-shot, so a false accusation here is the one that sticks."""
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-3", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    verdict = MOG.sweep_pull(
        "acme/widgets",
        _pull(),
        "read",
        "write",
        _freshness(),
        _proof("ci-pack-3"),
        MOG.SweepBudget("read", max_refreshes=0),
    )
    assert verdict == "refresh-deferred"
    posts = [call for call in calls if call[0] == "POST"]
    assert not [c for c in posts if c[1].endswith("/labels")]
    assert not [c for c in posts if c[1].endswith("/comments")]
    assert not [c for c in calls if c[1].endswith("/update-branch")]
    assert any(
        line.startswith("::notice")
        and "effective `update-branch` attempt(s)" in line
        for line in capsys.readouterr().out.splitlines()
    ), "the deferral must be logged, never silent"


def test_a_stale_proof_refresh_also_draws_on_the_capped_slots(monkeypatch, capsys):
    """The clean-but-stale path calls `update-branch` too, and it is the same
    saturated pool. A cap that bounded only one of the two callers would not bound
    the CI runs at all."""
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}}
    calls = _fake_api(
        monkeypatch,
        check_pages=pages,
        update_status=202,
        # main took a source commit AFTER the proof, inside the PR's surface.
        main_commits=(("2026-08-05T13:00:00Z", ["engine/signal_quality.py"]),),
    )
    verdict = MOG.sweep_pull(
        "acme/widgets",
        _pull(),
        "read",
        "write",
        _freshness(commits=(("2026-08-05T13:00:00Z", ["engine/signal_quality.py"]),)),
        _proof(),
        MOG.SweepBudget("read", max_refreshes=0),
    )
    assert verdict == "refresh-deferred"
    assert not [c for c in calls if c[1].endswith("/update-branch")]
    assert not [c for c in calls if c[0] == "POST" and c[1].endswith("/labels")], (
        "a stale proof with no slot left must not be blamed for a conflict"
    )


def test_update_branch_is_fail_closed_when_no_serialized_budget_is_passed(
    monkeypatch, capsys
):
    """An imported/out-of-band caller cannot bypass workflow serialization."""
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-3", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    assert MOG.sweep_pull(
        "acme/widgets",
        _pull(1),
        "read",
        "write",
        _freshness(),
        _proof("ci-pack-3"),
    ) == "refresh-deferred"
    assert not [c for c in calls if c[1].endswith("/update-branch")]
    assert "no serialized sweep budget" in capsys.readouterr().out


# ── the breaker's upstream: a proof that never concludes reads as `pending` ────
#
# merge_on_green short-circuits on integration-baseline BEFORE it looks at any pull
# request, and a never-concluding newest run reads as `pending`, which blocks ordinary
# merges. So the sweeper's throughput depends on a workflow it does not own.
#
# 2026-08-07: integration-baseline.yml carried `cancel-in-progress: true`, which cancels
# the RUNNING proof and not merely superseded pending ones. Source pushes land every 1-2
# minutes during a merge drain and the hosted queue sat 100-180 deep, so every run was
# killed before it acquired a runner: measured over ~3h the last 60 runs were 59
# cancelled + 1 running, ZERO success, newest success 5h stale. The sweeper reported
# "11 baseline-blocked" against a main that was green. The armed backlog could not drain
# because the proof that main is drainable was being cancelled by the drain's own pushes.
#
# `false` still coalesces — GitHub allows one pending run per group, so a newer push
# still supersedes an older PENDING proof — but the run holding a runner gets to finish.

import yaml as _yaml  # noqa: E402

_BASELINE_WF = ROOT / ".github" / "workflows" / "integration-baseline.yml"


def test_the_baseline_proof_is_allowed_to_finish():
    """cancel-in-progress must stay false or the breaker can never open under load.

    Not a style preference. With `true`, a repo that pushes source faster than it can
    acquire a runner never produces a concluded proof at all, and `pending` blocks every
    ordinary merge — the sweeper stalls on a green main.
    """
    doc = _yaml.safe_load(_BASELINE_WF.read_text())
    conc = doc.get("concurrency") or {}
    assert conc.get("group") == "integration-baseline-main", \
        "the baseline must stay in one coalescing group"
    assert conc.get("cancel-in-progress") is False, (
        "integration-baseline.yml has cancel-in-progress back on. That cancels the RUNNING "
        "proof, not just superseded pending ones — measured 2026-08-07, it produced 59 "
        "cancelled runs and zero successes in 3h while merge-on-green reported "
        "'11 baseline-blocked' against a green main. If a newer proof must win, supersede "
        "the PENDING one (which the group already does); do not kill the one on a runner."
    )


def test_the_baseline_main_push_escapes_the_hosted_queue_only_on_main():
    """Route every main proof to render-linux without moving off-main runs.

    The exact expression is a mutation pin: changing the ref guard, labels, or hosted
    fallback fails before the truth-table below can disguise the altered workflow.
    """
    job = _yaml.safe_load(_BASELINE_WF.read_text(encoding="utf-8"))["jobs"]["baseline"]
    runs_on = " ".join(str(job["runs-on"]).split())
    assert runs_on == (
        "${{ github.ref == 'refs/heads/main' && "
        "fromJSON('[\"self-hosted\",\"render-linux\"]') || 'ubuntu-latest' }}"
    )

    def routed_runner(event_name: str, ref: str):
        del event_name
        if ref == "refs/heads/main":
            return ["self-hosted", "render-linux"]
        return "ubuntu-latest"

    expected = {
        ("push", "refs/heads/main"): ["self-hosted", "render-linux"],
        ("workflow_dispatch", "refs/heads/main"): ["self-hosted", "render-linux"],
        ("workflow_dispatch", "refs/heads/operator-check"): "ubuntu-latest",
        ("push", "refs/heads/not-main"): "ubuntu-latest",
    }
    assert {
        context: routed_runner(*context)
        for context in expected
    } == expected
    assert "macstudio" not in runs_on
    assert int(job["timeout-minutes"]) == 30


def test_the_self_hosted_baseline_clears_sparse_checkout_before_checkout():
    """A reused render-linux workspace must be made complete before checkout@v4."""
    job = _yaml.safe_load(_BASELINE_WF.read_text(encoding="utf-8"))["jobs"]["baseline"]
    steps = job["steps"]
    checkout_index = next(
        index
        for index, step in enumerate(steps)
        if str(step.get("uses") or "").startswith("actions/checkout@")
    )
    cleanup = [
        (index, step)
        for index, step in enumerate(steps)
        if "sparse-checkout disable" in str(step.get("run") or "")
    ]
    assert len(cleanup) == 1, "expected exactly one sparse-checkout cleanup guard"
    cleanup_index, cleanup_step = cleanup[0]
    assert cleanup_index < checkout_index, "cleanup must run before actions/checkout"
    assert cleanup_step["if"] == "runner.environment == 'self-hosted'"
    assert cleanup_step["shell"] == "bash"
    cleanup_script = str(cleanup_step["run"])
    assert 'if [ -d "${{ github.workspace }}/.git" ]; then' in cleanup_script
    assert (
        'git -C "${{ github.workspace }}" sparse-checkout disable || true'
        in cleanup_script
    )
    assert (
        'git -C "${{ github.workspace }}" config --unset-all core.sparseCheckout || true'
        in cleanup_script
    )


# --- the sweeper orders the SOURCE baseline the freshness bound consumes -------
#
# `BASELINE_MAX_AGE_HOURS` shipped in the same change as the in-flight fix, and on its
# own it is the SAME defect in a quieter form: a gate that halts on the absence of
# evidence with no way to produce any. `integration-baseline.yml` does have a `push`
# trigger, but its `paths:` filter excludes data/site publisher commits — so only SOURCE
# pushes re-prove main, and the only source pushes to main are merges. A green that ages
# out therefore blocks merges, which stops the pushes, which keeps it aged out. The
# escapes were a human running `gh workflow run integration-baseline.yml --ref main` and
# the single `main-red-repair` slot. So the sweeper orders it.


def _source_api(monkeypatch, runs, **kwargs):
    """`_proof_api` pointed at the baseline workflow's run list."""
    return _proof_api(
        monkeypatch, runs={"integration-baseline.yml": list(runs)}, **kwargs
    )


def _source_dispatches(calls):
    """POSTs that ordered a SOURCE baseline — never ci.yml's."""
    return [call for call in _dispatched(calls) if "integration-baseline.yml" in call[1]]


def _stale_green(hours=None):
    """A concluded green baseline past the freshness bound."""
    return _wf_run(
        9001,
        conclusion="success",
        created_at=_ago(hours=hours or MOG.BASELINE_MAX_AGE_HOURS + 3),
    )


def test_a_stale_green_orders_a_fresh_source_baseline(monkeypatch, capsys):
    """THE completion. Without this the freshness bound is a one-way door."""
    calls = _source_api(monkeypatch, [_stale_green()])
    assert MOG.ensure_integration_baseline("acme/widgets", "write", "pending") == "dispatched"
    posts = _source_dispatches(calls)
    assert len(posts) == 1, f"expected exactly one dispatch, got {posts}"
    assert posts[0][2] == {"ref": "main"}, "the baseline must be ordered on main"
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines and all(line.startswith("::") for line in lines), lines
    assert any(line.startswith("::notice") for line in lines), (
        "the sweep log must say what was ordered and why"
    )


@pytest.mark.parametrize(
    "in_flight", ["queued", "in_progress", "requested", "waiting", "pending"]
)
def test_a_baseline_already_in_flight_is_never_stampeded(monkeypatch, in_flight):
    """The half a `status=in_progress` + `status=queued` pair would miss. Ordering a
    second proof while one is coming is not merely wasteful here: the group keeps ONE
    pending run, so under the 75-94 minute hosted queue the replacement starts its wait
    over."""
    calls = _source_api(
        monkeypatch,
        [
            _wf_run(9100, status=in_flight, conclusion=None, created_at=_ago(minutes=1)),
            _stale_green(),
        ],
    )
    result = MOG.ensure_integration_baseline("acme/widgets", "write", "pending")
    assert result == f"skipped (a baseline is already {in_flight})"
    assert _source_dispatches(calls) == []


def test_a_baseline_ordered_inside_the_floor_is_not_re_ordered(monkeypatch):
    """The bound the in-flight check cannot see: a run that has already concluded (here,
    superseded) but is newer than the floor means one was ordered too recently."""
    calls = _source_api(
        monkeypatch,
        [
            _wf_run(9101, conclusion="cancelled", created_at=_ago(minutes=5)),
            _stale_green(),
        ],
    )
    result = MOG.ensure_integration_baseline("acme/widgets", "write", "pending")
    assert "inside the" in result and "floor" in result, result
    assert _source_dispatches(calls) == []


def test_a_run_outside_the_floor_may_be_re_ordered(monkeypatch):
    """The floor is a rate bound, not a second deadlock — it has to expire."""
    calls = _source_api(
        monkeypatch,
        [
            _wf_run(
                9102,
                conclusion="cancelled",
                created_at=_ago(minutes=MOG.INTEGRATION_BASELINE_MIN_INTERVAL_MINUTES + 5),
            ),
            _stale_green(),
        ],
    )
    assert MOG.ensure_integration_baseline("acme/widgets", "write", "pending") == "dispatched"
    assert len(_source_dispatches(calls)) == 1


@pytest.mark.parametrize("state", ["red", "unproven", "green"])
def test_only_a_pending_breaker_orders_a_baseline(monkeypatch, state):
    """`red` is the important one: main is broken, and a fresh baseline would faithfully
    re-prove the same red — spending a hosted run to learn nothing, on the pool whose
    saturation caused all of this. `unproven` means nothing concluded to BE stale, and
    `green` needs nothing. None of them may even spend the READ."""
    calls = _source_api(monkeypatch, [_stale_green()])
    result = MOG.ensure_integration_baseline("acme/widgets", "write", state)
    assert result == f"not needed (breaker is {state})"
    assert calls == [], f"a non-pending breaker must cost no API call, spent {calls}"


def test_a_read_failure_aborts_the_sweep_before_any_baseline_is_ordered(
    monkeypatch, capsys
):
    """A read failure raises out of `integration_baseline_state`, so `main()` returns 1
    before the dispatcher exists — the fail-closed direction. Pinned at sweep level
    because that is where the ordering between the two is decided."""
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setenv("MERGE_TOKEN", "write")
    monkeypatch.setattr(MOG, "labeled_pulls", lambda *_a: [_pull(1)])
    calls = _source_api(monkeypatch, [_stale_green()])

    def unavailable(*_a):
        raise RuntimeError("API down")

    monkeypatch.setattr(MOG, "integration_baseline_state", unavailable)
    monkeypatch.setattr(
        MOG, "sweep_pull", lambda *_a: pytest.fail("no pull may be touched")
    )
    assert MOG.main() == 1
    assert "Could not establish" in capsys.readouterr().out
    assert _source_dispatches(calls) == []


@pytest.mark.parametrize(
    ("runs", "expected"),
    [
        ([], "not needed (no concluded baseline to be stale)"),
        (
            [_wf_run(9103, status="queued", conclusion=None, created_at=_ago(minutes=1))],
            "not needed (no concluded baseline to be stale)",
        ),
        (
            [_wf_run(9104, conclusion="failure", created_at=_ago(hours=9))],
            "not needed (the newest concluded baseline is not green)",
        ),
        (
            [_wf_run(9105, conclusion="success", created_at=_ago(hours=1))],
            "not needed (the proof is 1.0h old)",
        ),
    ],
)
def test_the_stale_reason_is_re_derived_from_the_runs(monkeypatch, runs, expected):
    """`pending` is necessary but not sufficient. The reason is re-derived from the run
    list rather than parsed back out of the state's display string — the lesson
    `failing_check_names` records: display strings are for humans, decisions are made
    from data. A `pending` that is NOT the stale-green case must not dispatch."""
    calls = _source_api(monkeypatch, runs)
    # The one-hour fixture is created at collection time, while this 200-test
    # module takes several minutes to reach this assertion on hosted runners.
    # Pin the formatter input: this case is about deriving the reason from the
    # concluded run list, not about wall-clock progress during the test process.
    if expected == "not needed (the proof is 1.0h old)":
        monkeypatch.setattr(MOG, "_baseline_age_hours", lambda _run: 1.0)
    assert MOG.ensure_integration_baseline("acme/widgets", "write", "pending") == expected
    assert _source_dispatches(calls) == []


def test_an_undatable_green_does_not_dispatch(monkeypatch):
    """Age unknown is not age exceeded. `integration_baseline_state` also reports
    `pending` for an undatable green, and dispatching on it would turn one unparseable
    timestamp into a dispatch every sweep, forever."""
    undated = _wf_run(9106, conclusion="success")
    for field in ("created_at", "run_started_at", "updated_at"):
        undated.pop(field, None)
    calls = _source_api(monkeypatch, [undated])
    result = MOG.ensure_integration_baseline("acme/widgets", "write", "pending")
    assert result == "skipped (the newest concluded baseline has no usable timestamp)"
    assert _source_dispatches(calls) == []


def test_an_unreadable_run_list_skips_rather_than_dispatching(monkeypatch):
    """Fail-closed in the cheap direction: an unreadable answer is treated as
    'something is running', which costs one sweep of latency instead of a stampede."""
    calls = _source_api(
        monkeypatch, [_stale_green()], run_status={"integration-baseline.yml": 403}
    )
    result = MOG.ensure_integration_baseline("acme/widgets", "write", "pending")
    assert result == "skipped (could not read the baseline runs: HTTP 403)"
    assert _source_dispatches(calls) == []


def test_a_failed_dispatch_is_logged_and_the_sweep_continues(monkeypatch, capsys):
    """Ordering a baseline must never fail a sweep that merged pull requests
    correctly."""
    _source_api(monkeypatch, [_stale_green()], dispatch_status=500)
    assert (
        MOG.ensure_integration_baseline("acme/widgets", "write", "pending")
        == "dispatch failed (HTTP 500)"
    )
    out = capsys.readouterr().out
    assert "::warning" in out
    assert all(line.startswith("::") for line in out.splitlines() if line.strip())


def test_a_dispatch_that_raises_never_escapes(monkeypatch, capsys):
    """The bare `except` is deliberate and this is what pins it — a transport error on
    the POST is not a reason for a green sweep to go red."""

    def boom(method, url, token, payload=None):
        if method == "POST":
            raise RuntimeError("socket died")
        return 200, {"workflow_runs": [_stale_green()]}

    monkeypatch.setattr(MOG, "_request", boom)
    assert (
        MOG.ensure_integration_baseline("acme/widgets", "write", "pending")
        == "dispatch error"
    )
    assert "::warning" in capsys.readouterr().out


def test_repeated_sweeps_order_at_most_one_baseline_per_interval(monkeypatch):
    """THE ANTI-DEADLOCK PROPERTY, asserted as a COUNT over many sweeps.

    Not "the third sweep dispatches" or "the first one wins" — #4845's scar is exactly
    that shape: a test that pinned WHICH armed repair got the scarce slot silently
    converted "one at a time" into "the same one forever", and the identity assertion
    passed throughout. The invariant here is the RATE: however many times the sweeper
    wakes while a green is stale — and it wakes on every completed proof workflow plus a
    10-minute cron — it orders at most one baseline per interval.

    The fake models what GitHub actually does after a 204: the run exists immediately,
    `queued`, and every later sweep sees it.
    """

    def on_dispatch(pool, _jobs):
        pool["integration-baseline.yml"].insert(
            0,
            _wf_run(9200, status="queued", conclusion=None, created_at=_ago(seconds=1)),
        )

    calls = _source_api(monkeypatch, [_stale_green()], on_dispatch=on_dispatch)
    results = [
        MOG.ensure_integration_baseline("acme/widgets", "write", "pending")
        for _ in range(8)
    ]
    assert len(_source_dispatches(calls)) == 1, (
        f"8 sweeps ordered {len(_source_dispatches(calls))} baselines: {results}"
    )
    assert results.count("dispatched") == 1
    assert set(results[1:]) == {"skipped (a baseline is already queued)"}, (
        "every later sweep must skip for the IN-FLIGHT reason — skipping because it "
        "forgot the green was stale would be the same bug with a passing test"
    )


def test_the_dispatch_does_not_unblock_the_sweep_that_ordered_it(monkeypatch, capsys):
    """Ordering evidence is not the same as having it. The sweep that dispatches must
    still refuse ordinary merges — the next one judges them against the result."""
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setenv("MERGE_TOKEN", "write")
    monkeypatch.setattr(MOG, "labeled_pulls", lambda *_a: [_pull(1), _pull(2)])
    monkeypatch.setattr(
        MOG,
        "integration_baseline_state",
        lambda *_a: ("pending", "newest concluded baseline is 9.0h old"),
    )
    monkeypatch.setattr(MOG.ProofFreshness, "build", classmethod(lambda *_a, **_k: _freshness()))
    monkeypatch.setattr(MOG, "main_proof", lambda *_a: _proof("ci-pack-1"))
    monkeypatch.setattr(MOG, "ensure_main_baseline", lambda *_a, **_k: "stubbed")
    monkeypatch.setattr(
        MOG,
        "sweep_pull",
        lambda *_a: pytest.fail("nothing ordinary may merge while the breaker is pending"),
    )
    calls = _source_api(monkeypatch, [_stale_green()])
    assert MOG.main() == 0
    out = capsys.readouterr().out
    assert len(_source_dispatches(calls)) == 1
    assert "2 baseline-blocked" in out, out
    assert "source-baseline: dispatched" in out, (
        "the summary must record the dispatch, so a suppressed one is diagnosable"
    )


# --- a red must ALWAYS leave a marker (PR #5291, 2026-08-11) -------------------
#
# The incident, from the label timeline and the run logs:
#
#   01:23:45Z  #5291 armed with `merge-on-green`
#   02:05:18Z  ci run 31449929887 concludes FAILURE on head 9ce3c2ef
#   02:13:32Z  a codex session execs `gh pr edit 5291 --remove-label merge-on-green`
#   02:13:34Z  the arm label is gone. No `merge-blocked`. No comment. No marker.
#   02:13:41Z  sweep 31451725301 lists the armed PRs — #5291 is already invisible
#   02:20:52Z  a builder re-arms it
#   02:21:36Z  the same session strips it again, still with no marker
#   02:32:52Z  a human admin-merges it by hand
#
# Two sweeper-side properties made the silent window possible, and both are pinned
# below. The `if:` gate skipped failure wake-ups, so the marker could only ride the
# ~0.5/hr cron or the next green anywhere in the repository — and once the arm label
# came off, a label-filtered sweep could never see the pull request again, so the
# marker could not arrive at all. And `mark_blocked` treated a failed label POST as
# a reason to skip the COMMENT too, which turns one unlucky HTTP status into a
# refusal that exists only in a run log.
#
# The disarm itself is not the sweeper's to prevent — `scripts/merge_on_green.py`
# has no code path that removes `merge-on-green`. That half is a fleet law, and it
# lives in CLAUDE.md and AGENTS.md.


def _label_api(monkeypatch, *, label_status=200, comment_status=200):
    """Route ONLY the two write endpoints `mark_blocked` uses, and record them."""
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/labels"):
            if label_status >= 400:
                return label_status, {"message": "Resource not accessible"}
            return label_status, [{"name": MOG.MERGE_BLOCKED_LABEL}]
        if url.endswith("/comments"):
            if comment_status >= 400:
                return comment_status, {"message": "Server Error"}
            return comment_status, {"id": 1}
        raise AssertionError(f"mark_blocked made an unexpected call: {method} {url}")

    monkeypatch.setattr(MOG, "_request", fake_request)
    return calls


def _errors(capsys) -> list[str]:
    return [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error")
    ]


def test_a_failed_label_write_still_posts_the_explanation(monkeypatch, capsys):
    """The 403 that used to make a refusal invisible.

    `mark_blocked` warned into the run log and returned WITHOUT commenting, so the
    pull request carried no label, no comment, and no evidence that the sweeper had
    ever looked at it. The label and the comment are two independent ways of saying
    the same thing: losing one is a reason to lean harder on the other.
    """
    calls = _label_api(monkeypatch, label_status=403)
    landed = MOG.mark_blocked("acme/widgets", _pull(), "why not", "write")
    comments = [call for call in calls if call[1].endswith("/comments")]
    assert len(comments) == 1, "the explanation must be posted even when the label 403s"
    assert comments[0][2] == {"body": "why not"}
    assert landed is True, "a comment IS a marker — the caller must not report silence"
    errors = _errors(capsys)
    assert errors, "a lost marker write is an ERROR, not a warning"
    assert all(line.startswith("::error") for line in errors), (
        "GH annotation law: the `::` token starts the line (bare print, never a logger)"
    )
    assert any("403" in line for line in errors), "the status must be diagnosable"


def test_a_failed_comment_write_is_an_error_too(monkeypatch, capsys):
    """The other half. The label landed, so a marker exists and the return says so —
    but the explanation is the part that tells the owner WHY, and losing it silently
    is how a `merge-blocked` label becomes a mystery."""
    calls = _label_api(monkeypatch, comment_status=500)
    landed = MOG.mark_blocked("acme/widgets", _pull(), "why not", "write")
    assert landed is True, "the label landed, so a marker did land"
    assert any(call[1].endswith("/labels") for call in calls)
    errors = _errors(capsys)
    assert any("500" in line for line in errors), errors


def test_a_refusal_that_could_not_be_written_at_all_says_exactly_that(
    monkeypatch, capsys
):
    """Both writes gone. This is the one case where the run log IS the only record,
    so it must say so in as many words rather than reporting a routine no-op."""
    _label_api(monkeypatch, label_status=403, comment_status=500)
    assert MOG.mark_blocked("acme/widgets", _pull(), "why not", "write") is False
    assert any("NO visible marker" in line for line in _errors(capsys))


def test_the_red_comment_forbids_a_SILENT_takeover(monkeypatch):
    """The copy used to end at "or remove `merge-on-green` to take it manual." — an
    instruction to do the exact thing that made #5291 invisible, with no mention of
    the marker that keeps it visible. One helper, so the full sweep and the mark-only
    pass cannot drift apart on the law they teach."""
    body = MOG.red_check_comment(["ci-pack-2 (failure)"])
    assert "take it manual" in body, "the option itself is legitimate and stays"
    assert "silently" in body.lower()
    assert "#5291" in body
    assert MOG.MERGE_BLOCKED_LABEL in body, "it must name the marker to leave"

    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-2", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages)
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "blocked"
    posted = [
        call for call in calls if call[0] == "POST" and call[1].endswith("/comments")
    ]
    assert len(posted) == 1 and posted[0][2]["body"] == MOG.red_check_comment(
        ["ci-pack-2 (failure)"]
    ), "the full sweep must post the SHARED copy, not a second hand-maintained one"


def _mark_only(monkeypatch, pulls, *, check_pages, proof=None, head="a" * 40):
    """`mark_only_pass` with the listing stubbed and every request routed+recorded."""
    calls = _fake_api(monkeypatch, check_pages=check_pages)
    monkeypatch.setattr(MOG, "labeled_pulls", lambda *_a: list(pulls))
    if proof is not None:
        monkeypatch.setattr(MOG, "main_proof", lambda *_a: proof)
    return calls, MOG.mark_only_pass("acme/widgets", "read", "write", head)


def test_the_mark_only_pass_marks_a_genuine_red_and_does_nothing_else(
    monkeypatch, capsys
):
    """What the failure wake-up is FOR: the marker, within seconds of the red.

    And nothing else. This pass runs on ~26 wake-ups an hour against a 1,000/hr
    per-repository READ_TOKEN bucket, so a merge, an `update-branch` or a baseline
    dispatch here would re-create the 2026-08-07 starvation the `if:` gate was
    written to prevent.
    """
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-2", conclusion="failure")]}}
    calls, code = _mark_only(
        monkeypatch,
        [_pull(5291)],
        check_pages=pages,
        proof=_proof("ci-pack-9"),  # main proves something else — the red is its own
    )
    assert code == 0, "a red pull request is the lane working, not a broken sweeper"

    posts = [call for call in calls if call[0] == "POST"]
    labels = [call for call in posts if call[1].endswith("/labels")]
    comments = [call for call in posts if call[1].endswith("/comments")]
    assert len(labels) == 1 and labels[0][2] == {"labels": [MOG.MERGE_BLOCKED_LABEL]}
    assert len(comments) == 1 and "ci-pack-2 (failure)" in comments[0][2]["body"]

    for endpoint in ("/merge", "/update-branch", "/dispatches"):
        assert not [call for call in calls if call[1].endswith(endpoint)], (
            f"the mark-only pass must never call {endpoint}"
        )
    assert not [call for call in calls if call[0] == "DELETE"], (
        "it never clears a label either — clearing is the full sweep's call"
    )
    out = capsys.readouterr().out
    assert any(
        line.startswith("merge-on-green mark-only pass:") for line in out.splitlines()
    ), "the pass must leave one greppable summary line"


def test_a_red_on_a_SUPERSEDED_head_marks_nothing(monkeypatch, capsys):
    """A PUSH SUPERSEDES ITS OWN RED.

    The failed run belongs to the head it ran on. If the branch has moved since, the
    armed pull request now sits at a head no check has judged, and marking it would
    accuse the successor of its ancestor's failure. Its own runs will conclude and
    wake their own pass.
    """
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-2", conclusion="failure")]}}
    calls, code = _mark_only(
        monkeypatch, [_pull(5291)], check_pages=pages, head="b" * 40
    )
    assert code == 0
    assert [call for call in calls if call[0] != "GET"] == [], (
        "no armed pull request at the trigger head means zero writes"
    )
    assert calls == [], "and not even a check-run read — the listing already answered"
    assert "SUPERSEDES" in capsys.readouterr().out


def test_a_base_inherited_red_is_left_for_the_full_sweep(monkeypatch, capsys):
    """The one-shot comment must not be burned on a fleet-wide stale base.

    Every failing check being clean on main is the base-inherited signature, and
    deciding it needs `proof_postdates_failures`, a refresh slot and an
    `update-branch` — all of which are the full sweep's, none of which this pass may
    spend. Marking on the name overlap alone would post the false-accusation comment
    on every armed head during a main-red episode (measured shape: 84 of 93), and a
    one-shot comment cannot be taken back.
    """
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-3", conclusion="failure")]}}
    calls, code = _mark_only(
        monkeypatch, [_pull(5291)], check_pages=pages, proof=_proof("ci-pack-3")
    )
    assert code == 0
    assert [call for call in calls if call[0] != "GET"] == [], (
        "an inherited red must not be labeled or commented by this pass"
    )
    out = capsys.readouterr().out
    assert "Deferred to the full sweep" in out, out


@pytest.mark.parametrize(
    "runs, why",
    [
        ([("ci-pack-2", "in_progress", None)], "a rerun may still green the head"),
        ([("ci-pack-2", "completed", "success")], "the head is green; nothing to mark"),
        ([("Workers Builds: macro", "completed", "failure")], "spurious-only is unproven"),
    ],
)
def test_the_mark_only_pass_marks_nothing_but_a_settled_red(
    monkeypatch, capsys, runs, why
):
    """One failed RUN is not a red HEAD. `decide_verdict` is the same authority the
    full sweep uses, and only its `blocked` answer may write."""
    pages = {
        1: {
            "total_count": len(runs),
            "check_runs": [
                _run(name, status, conclusion=conclusion) for name, status, conclusion in runs
            ],
        }
    }
    calls, code = _mark_only(monkeypatch, [_pull(5291)], check_pages=pages)
    assert code == 0
    assert [call for call in calls if call[0] != "GET"] == [], why
    capsys.readouterr()


def test_a_rate_limited_mark_only_pass_defers_instead_of_reddening(monkeypatch, capsys):
    """Same law as the sweep: a lane that correctly declined to run is not a fault,
    and 17 red runs is how the 2026-08-07 outage buried its own diagnosis."""

    def starved(*_a, **_k):
        raise MOG.RateLimited("only 0 of 1000 core API requests remain")

    monkeypatch.setattr(MOG, "labeled_pulls", starved)
    assert MOG.mark_only_pass("acme/widgets", "read", "write", "a" * 40) == 0
    assert any(
        line.startswith("::warning") and "deferred" in line.lower()
        for line in capsys.readouterr().out.splitlines()
    )


def test_a_failure_wake_up_runs_the_mark_only_pass_and_never_the_full_sweep(
    monkeypatch, capsys
):
    """The routing, end to end through `main()`.

    A red cannot make anything mergeable and failure wake-ups outnumber the greens
    ~5:1, so falling through into a full sweep would put the READ_TOKEN bucket back
    where 2026-08-07 found it.
    """
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setenv("MERGE_TOKEN", "write")
    monkeypatch.setenv("TRIGGER_HEAD_SHA", "9ce3c2ef" + "0" * 32)
    monkeypatch.setenv("TRIGGER_CONCLUSION", "failure")
    monkeypatch.setattr(
        MOG,
        "core_rate_limit",
        lambda _token: (MOG.MARK_ONLY_RATE_LIMIT_FLOOR, 15_000),
    )
    monkeypatch.setattr(
        MOG,
        "labeled_pulls",
        lambda *_a: pytest.fail("the full sweep must not list the backlog on a red"),
    )
    monkeypatch.setattr(
        MOG, "sweep_pull", lambda *_a, **_k: pytest.fail("a red wake-up never sweeps")
    )
    seen: list[tuple] = []

    def fake_mark(repo, read_token, merge_token, head, budget=None):
        seen.append((repo, head, budget is not None))
        return 0

    monkeypatch.setattr(MOG, "mark_only_pass", fake_mark)
    assert MOG.main() == 0
    assert seen == [("acme/widgets", "9ce3c2ef" + "0" * 32, True)], (
        "the pass gets the trigger head AND the preflighted budget"
    )
    capsys.readouterr()


@pytest.mark.parametrize("conclusion", ["success", ""])
def test_success_and_non_workflow_events_run_the_full_sweep(monkeypatch, conclusion):
    """Cron/workflow_dispatch supply empty; success is the full workflow-run path."""
    seen = _main_harness(monkeypatch, [_pull(1)])
    monkeypatch.setenv("TRIGGER_CONCLUSION", conclusion)
    monkeypatch.setattr(
        MOG,
        "mark_only_pass",
        lambda *_a, **_k: pytest.fail(f"{conclusion!r} must not route to the marker"),
    )
    assert MOG.main() == 0
    assert seen == [1]


@pytest.mark.parametrize("conclusion", ["cancelled", "skipped", "neutral", "timed_out"])
def test_non_success_conclusions_route_only_to_lease_reconciliation(
    monkeypatch, conclusion
):
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setenv("MERGE_TOKEN", "write")
    monkeypatch.setenv("TRIGGER_HEAD_SHA", "a" * 40)
    monkeypatch.setenv("TRIGGER_CONCLUSION", conclusion)
    monkeypatch.setattr(
        MOG,
        "core_rate_limit",
        lambda _token: (MOG.MARK_ONLY_RATE_LIMIT_FLOOR, 15_000),
    )
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(
        MOG,
        "lease_reconcile_pass",
        lambda _r, _read, _write, head, result, _run: seen.append(
            (head, result)
        )
        or 0,
    )
    monkeypatch.setattr(
        MOG, "labeled_pulls", lambda *_a: pytest.fail("reconcile is never a full sweep")
    )
    assert MOG.main() == 0
    assert seen == [("a" * 40, conclusion)]


def test_the_mark_only_pass_never_removes_the_arm_label(monkeypatch):
    """The sweeper is not the disarmer, and nothing here may become one.

    #5291's arm label was removed by a session, not by this lane — `merge_on_green.py`
    contains no code path that removes `merge-on-green`, and this pins that as a
    property of the source rather than of one execution. The other half of the repair
    is a fleet law (CLAUDE.md / AGENTS.md): a disarm must leave a marker.
    """
    source = (ROOT / "scripts" / "merge_on_green.py").read_text(encoding="utf-8")
    # Parsed, not grepped line by line: every `_request` here spans several lines, so
    # a "DELETE and labels on one line" scan would pass vacuously — including on the
    # very code it is supposed to forbid.
    deletes = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "_request"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "DELETE"
    ]
    assert deletes, "the scan found no DELETE at all — it has stopped being a check"
    for node in deletes:
        url = ast.unparse(node.args[1])
        assert "MERGE_ON_GREEN_LABEL" not in url, (
            f"the sweeper must never remove the arm label: {url}"
        )
    for doc in ("CLAUDE.md", "AGENTS.md"):
        law = (ROOT / doc).read_text(encoding="utf-8")
        assert "#5291" in law, f"{doc} must carry the no-silent-disarm law"
        assert "remove-label merge-on-green" in law, (
            f"{doc} must name the exact command that caused it"
        )
