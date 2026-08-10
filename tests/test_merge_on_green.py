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

import datetime as dt
import json
from pathlib import Path

import pytest
import yaml

import scripts.merge_on_green as MOG


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "merge-on-green.yml"
BASELINE_WORKFLOW = ROOT / ".github" / "workflows" / "integration-baseline.yml"


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
    """Keep the control plane on the pool with live spare capacity.

    The 2026-08-08 self-hosted move escaped a capped hosted backlog. Enterprise raised
    that ceiling to 180; on 2026-08-09 hosted usage was 34 while render-linux was 4/4
    busy and sweeps queued. Routing back is the same invariant under the new capacity:
    the merge arbiter must not wait behind render work.
    """
    job = _workflow()["jobs"]["sweep"]
    labels = json.dumps(job["runs-on"])
    assert job["runs-on"] == "ubuntu-latest"
    assert "self-hosted" not in labels
    assert "render-linux" not in labels
    assert "macstudio" not in labels
    assert int(job["timeout-minutes"]) == 15


def test_the_hosted_sweep_keeps_a_minimal_runner_contract():
    """The hosted route needs only the image's Python and network.

    The integration-baseline job has its own routing/setup-python contract; adding a
    setup step to this lightweight sweep must fail here rather than silently making the
    control plane slower or stateful.
    """
    steps = _workflow()["jobs"]["sweep"]["steps"]
    used = [str(step.get("uses") or "") for step in steps]
    assert not [entry for entry in used if entry.startswith("actions/setup-python")], (
        f"the sweep must stay runner-agnostic; found {used}"
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
    assert permissions["contents"] == "write", "needed to squash-merge and delete the head ref"
    assert permissions["pull-requests"] == "write", "needed for merge-blocked + the comment"
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "no `push` trigger" in source, (
        "the reason `actions` is write must stay in the file — it is not obvious, and "
        "an editor tidying it back to `read` silently re-breaks the refresh path"
    )


def test_no_concurrency_group_may_serialise_this_lane():
    """The 2026-08-06 livelock. Do not reintroduce `concurrency:` here.

    `group: merge-on-green` + `cancel-in-progress: false` was chosen so a
    mid-merge sweep could finish. It achieved the opposite: `cancel-in-progress:
    false` protects only an IN-PROGRESS run, GitHub keeps exactly ONE pending run
    per group and cancels it on every new arrival, and the pending state includes
    the wait for a runner. `ci` and `fences` shared the then-capacity-limited hosted
    pool with this job (48 and 34 queued against 8 and 1 running when measured), so the
    group was held for 25-107 minutes by a sweep that had not started, while
    triggers arriving every 50 s destroyed each other in the single pending slot.

    Result over the 100 runs before the fix: 98 cancelled, 0 successful, and 94 of
    those 98 died within 3 seconds of the next run's creation. ~58 PRs sat armed
    and unmerged with nothing to merge them.
    """
    parsed = _workflow()
    assert "concurrency" not in parsed, (
        "a concurrency group here serialises the RUNNER QUEUE, not the sweep — "
        "it livelocked the lane to 0 successes in 100 runs. Runner-minute control "
        "belongs in the job-level `if:` gate, which costs nothing when it skips."
    )
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "livelock" in source.lower(), "the postmortem must stay in the file"
    assert "46 SECONDS" in source or "46 seconds" in source, (
        "the sweep-duration-vs-queue-wait contrast is the whole finding"
    )


def test_the_sweep_only_wakes_for_a_trigger_that_could_unblock_a_merge():
    """Removing the concurrency group means every trigger now produces a run, so
    the runner budget is defended by SKIPPING instead of by cancelling — a skipped
    job costs no runner, no queue slot and no minutes, where a cancelled one cost
    us the sweep. Only a green triggering run can make a PR mergeable (ci's last
    100 completed runs: 51 failure, 25 cancelled, 18 skipped, 6 success), so this
    gate drops ~94% of wake-ups and keeps every actionable one.

    `schedule` and `workflow_dispatch` must never be gated away — the cron is the
    recovery net for third-party checks, and an operator must always be able to
    force a sweep.
    """
    gate = " ".join(str(_workflow()["jobs"]["sweep"]["if"]).split())
    assert "github.event_name != 'workflow_run'" in gate, (
        "the cron and workflow_dispatch must bypass the conclusion filter entirely"
    )
    assert "github.event.workflow_run.conclusion == 'success'" in gate


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
    assert int(job["timeout-minutes"]) == 12
    source = BASELINE_WORKFLOW.read_text(encoding="utf-8")
    assert "tests/test_merge_on_green.py" in source
    assert "scripts/check_skip_only_suites.py" in source


def test_the_workflow_records_why_the_pat_matters():
    """This rationale is the thing a future editor would otherwise delete."""
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "#3889" in source, "the --auto-merges-instantly finding must stay cited"
    assert "push-triggered" in source
    assert "3-minute pull" in source or "3-min" in source


# --- the decision, as a pure function -----------------------------------------


# A check run is dated now, because a green that cannot be dated cannot be trusted
# (#4583). Everything in this file that is not ABOUT the date uses these two stamps:
# the proof is computed at 12:00Z and the one main commit on the timeline landed at
# 09:00Z, comfortably before it, so `stale_for` answers "main has not moved".
PROOF_STARTED_AT = "2026-08-05T12:00:00Z"
BEFORE_THE_PROOF = "2026-08-05T09:00:00Z"
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
) -> dict:
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "started_at": started_at,
        "completed_at": completed_at,
    }


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

    `commits` is `[(iso8601, [changed files]), ...]`. Everything else defaults to a
    main that has taken exactly one commit, before the proof, so the gate answers
    "still current" and the test can be about whatever it is actually about.
    """
    gates = kwargs.pop("gates", None) or _gates()
    pull_files = kwargs.pop("pull_files", None)
    repo = kwargs.pop("repo", "acme/widgets")
    assert not kwargs, kwargs
    parsed = [
        {"sha": f"{index:040d}", "when": MOG._parse_iso(iso)}
        for index, (iso, _files) in enumerate(commits)
    ]
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


# --- the sweep itself, with HTTP mocked ---------------------------------------


def _fake_api(
    monkeypatch,
    *,
    check_pages,
    merge_status=200,
    update_status=422,
    pull_payload=None,
    main_commits=((BEFORE_THE_PROOF, ["data/nightly.json"]),),
    pr_files=("engine/signal_quality.py",),
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
    `pull_files` are exercised rather than stubbed. The defaults describe a main
    that moved only before the proof — no re-prove — so a test that is not about
    staleness keeps its old outcome.
    """
    calls: list[tuple[str, str, dict | None]] = []
    shas = [f"{index:040d}" for index, _ in enumerate(main_commits)]

    def fake_request(method, url, token, payload=None):
        calls.append((method, url, payload))
        if "/check-runs" in url:
            page = int(url.rsplit("page=", 1)[1].split("&")[0])
            return 200, check_pages.get(page, {"total_count": 0, "check_runs": []})
        if "/commits?" in url:
            return 200, [
                {"sha": sha, "commit": {"committer": {"date": iso}}}
                for sha, (iso, _files) in zip(shas, main_commits)
            ]
        if "/commits/" in url:
            sha = url.rsplit("/", 1)[1]
            files = dict(zip(shas, [names for _iso, names in main_commits]))[sha]
            return 200, {"files": [{"filename": name} for name in files]}
        if url.endswith("/update-branch"):
            if update_status in {200, 202}:
                return update_status, {"message": "Updating pull request branch."}
            return update_status, {"message": "merge conflict between base and head"}
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
            return 200, dict(pull_payload or {})
        return 200, {}

    monkeypatch.setattr(MOG, "_request", fake_request)
    return calls


def _pull(number=4242, labels=("merge-on-green",)) -> dict:
    return {
        "number": number,
        "head": {"sha": "a" * 40, "ref": "claude/feature"},
        "labels": [{"name": name} for name in labels],
    }


def test_a_clean_pull_request_is_squash_merged(monkeypatch, capsys):
    calls = _fake_api(
        monkeypatch,
        check_pages={1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="success")]}},
    )
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "merged"
    merges = [call for call in calls if call[1].endswith("/merge")]
    assert len(merges) == 1
    assert merges[0][0] == "PUT" and merges[0][2] == {"merge_method": "squash"}
    # Tidy-up is best-effort but must actually be attempted.
    assert any(call[0] == "DELETE" and "git/refs/heads" in call[1] for call in calls)


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
    calls = _fake_api(monkeypatch, check_pages=pages)
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
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "conflict"
    assert any(call[1].endswith("/update-branch") for call in calls), (
        "the sweeper must TRY to clear a stale base before labelling it blocked"
    )
    comments = [call for call in calls if call[0] == "POST" and call[1].endswith("/comments")]
    assert len(comments) == 1 and "not mergeable" in comments[0][2]["body"]
    assert "REAL content conflict" in comments[0][2]["body"], (
        "the comment must say the stale-base case was already ruled out"
    )


def test_a_pull_request_another_sweep_already_merged_is_never_labeled_blocked(
    monkeypatch, capsys
):
    """The race the removed concurrency group was supposed to prevent — and the
    only place overlapping sweeps are actually unsafe.

    Sweeps may now overlap (the group serialised a 25-107 minute runner queue, not
    the 46-second sweep, and livelocked the lane to 0 successes in 100 runs). Two
    sweeps can therefore both judge PR #4242 clean; one wins the squash merge and
    the other is answered 405/409 by GitHub — the SAME status a stale base or a
    real conflict produces.

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
        line.startswith("::notice") and "concurrent sweep" in line
        for line in capsys.readouterr().out.splitlines()
    )


def test_the_concurrent_sweep_guard_fails_closed_on_an_unreadable_pull_request(
    monkeypatch, capsys
):
    """A guard that cannot read must not invent an answer. When the re-read fails,
    the sweeper falls back to exactly the behaviour that shipped before the guard
    existed — noisier, but it can never merge anything or bury a real conflict."""

    def fake_request(method, url, token, payload=None):
        if "/check-runs" in url:
            return 200, {
                "total_count": 1,
                "check_runs": [_run("ci-pack-1", conclusion="success")],
            }
        if url.endswith("/merge"):
            return 409, {"message": "Pull Request is not mergeable"}
        if url.endswith("/update-branch"):
            return 422, {"message": "merge conflict between base and head"}
        if method == "GET" and "/pulls/" in url:
            return 502, None  # GitHub blipped
        return 200, {}

    monkeypatch.setattr(MOG, "_request", fake_request)
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "conflict"


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
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", _freshness()) == "updated"

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
    )
    already = _pull(labels=("merge-on-green", "merge-blocked"))
    assert MOG.sweep_pull("acme/widgets", already, "read", "write", _freshness()) == "updated"
    assert any(
        call[0] == "DELETE" and "labels/merge-blocked" in call[1] for call in calls
    ), "the stale merge-blocked label must be dropped once the branch moves again"


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

    def flaky(_repo, pull, *_a):
        if pull["number"] == 1:
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
    assert "circuit breaker" in out and "2 baseline-blocked" in out


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
                    _run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)
                ],
            }
        },
        main_commits=[(MAIN_MOVED_AT_1026, INCIDENT_4607_FILES)],
        pr_files=INCIDENT_4583_FILES,
        update_status=202,
    )
    freshness = MOG.ProofFreshness.build("acme/widgets", "read")

    assert (
        MOG.sweep_pull("acme/widgets", _pull(), "read", "write", freshness) == "re-proving"
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
    """A ci.yml / legacy-jobs.yml edit changes WHAT would run. No pull request's
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


def test_the_proof_instant_is_the_oldest_run_not_the_newest():
    """A proof is exactly as fresh as its stalest member. Re-running one failed check
    at T+5h must not re-date the hundred checks from T — reading the newest would let
    a single rerun launder a whole stale proof, which is #4583 in miniature."""
    freshness = _freshness()
    when = freshness.proof_instant(
        [
            _run("ci-pack-1", conclusion="success", started_at="2026-08-05T07:42:00Z"),
            _run("ci-pack-2", conclusion="success", started_at="2026-08-05T18:00:00Z"),
        ]
    )
    expected = MOG._parse_iso("2026-08-05T07:42:00Z") - MOG.PROOF_BASE_SKEW_SECONDS
    assert when == expected

    # And the spurious check is excluded from the dating exactly as it is from the
    # verdict, so a stray Cloudflare run cannot back-date a proof either.
    assert freshness.proof_instant(
        [
            _run("ci-pack-1", conclusion="success", started_at="2026-08-05T07:42:00Z"),
            _run("Workers Builds: macro", conclusion="failure", started_at="2020-01-01T00:00:00Z"),
        ]
    ) == expected


@pytest.mark.parametrize(
    "case,runs,kwargs,expected_in_reason",
    [
        (
            "an undatable proof",
            [_run("ci-pack-1", conclusion="success", started_at=None)],
            {},
            "cannot be dated",
        ),
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


def test_a_proof_older_than_the_whole_visible_timeline_is_re_proven():
    """#4583's own shape: 15 hours old, far beyond the ~8 hours one listing call
    buys. What main did in between cannot be established, so it is not asserted."""
    commits = [
        (f"2026-08-05T{12 - (index // 12):02d}:{(index * 5) % 60:02d}:00Z", ["docs/x.md"])
        for index in range(MOG.MAIN_TIMELINE_PAGE)
    ]
    freshness = _freshness(commits=commits, pull_files={4242: ["engine/signal_quality.py"]})
    stale, reason = freshness.stale_for(
        _pull(), [_run("ci-pack-1", conclusion="success", started_at="2026-08-04T07:42:00Z")]
    )
    assert stale and "predates all" in reason, reason


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


def test_a_raising_surface_check_can_never_become_permission_to_merge(monkeypatch, capsys):
    """The catch-all. Whatever breaks inside the gate, the answer is re-prove."""
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

    assert (
        MOG.sweep_pull("acme/widgets", _pull(), "read", "write", Exploding()) == "re-proving"
    )
    assert not any(call[0] == "PUT" and call[1].endswith("/merge") for call in calls)


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
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write", freshness) == "conflict"
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
                    _run("ci-pack-1", conclusion="success", started_at=PROVEN_AT_0742)
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

    Sweeps overlap by design (the concurrency group serialised the RUNNER QUEUE and
    livelocked the lane to 0 successes in 100 runs). So two sweeps can both judge this
    pull request clean AND stale. One of them re-proves or merges it; the other's
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
        line.startswith("::notice") and "concurrent sweep" in line
        for line in capsys.readouterr().out.splitlines()
    )


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


def _main_harness(monkeypatch, pulls, *, readings=(1000,), verdict="pending"):
    """Run `main()` with everything but the budget and the ordering stubbed out.

    `readings` is what successive `core_rate_limit` polls return (remaining), the
    first being the preflight. The last value repeats forever.
    """
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setenv("MERGE_TOKEN", "write")
    monkeypatch.delenv("TRIGGER_HEAD_SHA", raising=False)
    polls: list[int] = []

    def fake_limit(_token):
        index = min(len(polls), len(readings) - 1)
        polls.append(index)
        return readings[index], 1000

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
    assert MOG.main() == 0, "a quota deferral is not a broken sweep"
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


def test_the_per_sweep_cap_bounds_the_work_and_names_what_it_deferred(
    monkeypatch, capsys
):
    """(2) The cap. NO SILENT CAPS — a sweep that quietly evaluated a quarter of the
    backlog would look identical in the log to one that evaluated all of it, and that
    difference is the entire reason the lane stopped working."""
    armed = [_pull(number) for number in range(1, MOG.MAX_PULLS_PER_SWEEP + 8)]
    seen = _main_harness(monkeypatch, armed)
    assert MOG.main() == 0

    assert len(seen) == MOG.MAX_PULLS_PER_SWEEP, (
        f"expected at most {MOG.MAX_PULLS_PER_SWEEP} pull requests per sweep, "
        f"got {len(seen)}"
    )
    expected = MOG.sweep_order(armed)
    assert seen == [pull["number"] for pull in expected[: MOG.MAX_PULLS_PER_SWEEP]]

    deferred = sorted(pull["number"] for pull in expected[MOG.MAX_PULLS_PER_SWEEP :])
    notices = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::notice") and "Per-sweep cap" in line
    ]
    assert notices, "the cap must announce itself"
    assert f"{MOG.MAX_PULLS_PER_SWEEP} of {len(armed)}" in notices[0]
    for number in deferred[:3]:
        assert f"#{number}" in notices[0], f"deferred #{number} must be named"


def test_the_sweep_stops_cleanly_when_the_budget_runs_out_mid_pass(monkeypatch, capsys):
    """(3) Spend the budget as you go, not only at the start.

    Other lanes read main with the same per-repository GITHUB_TOKEN bucket, so a
    budget that was healthy at preflight can be gone thirty seconds later. Dying
    half-way through on a 403 spends calls the NEXT sweep needed — the loop that
    made this outage self-sustaining.
    """
    armed = [_pull(number) for number in range(1, MOG.MAX_PULLS_PER_SWEEP + 1)]
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
    buckets = -(-len(armed) // MOG.MAX_PULLS_PER_SWEEP)  # ceil
    reached: set[int] = set()
    for bucket in range(buckets):
        window = MOG.sweep_order(armed, now=bucket * MOG.ROTATION_BUCKET_SECONDS)
        reached.update(pull["number"] for pull in window[: MOG.MAX_PULLS_PER_SWEEP])
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


def test_the_budget_floor_can_actually_fund_a_capped_sweep():
    """A floor below what a capped pass costs would defer forever; a cap above what
    the hourly bucket affords would starve the lane again.

    The fixed overhead is ~12, NOT the ~6 this arithmetic originally used. #4854 spent
    the difference walking main newest->oldest for a commit that published checks; the
    2026-08-08 rework spends it on `main_proof` (4: two workflows x newest run + its
    jobs) plus up to 3 for `ensure_main_baseline`'s in-flight polls and dispatch — the
    same order of magnitude, now with a fixed ceiling instead of a walk. So a capped
    pass costs ~12 + 25 = ~37, sustainable up to floor(1000/37) = 27 sweeps/hour. The
    worst hour ever observed was 28, which overshoots by ~4% — absorbed by
    RATE_LIMIT_RESERVE, which stops the pass mid-sweep rather than letting it 403.
    Compare the uncapped cost that caused the outage: ~121/sweep.
    """
    fixed = 12
    assert 2 * len(MOG.MAIN_PROOF_WORKFLOWS) + 3 <= fixed, (
        "main_proof + ensure_main_baseline must stay inside the fixed overhead this "
        "floor was sized for"
    )
    worst_case = fixed + MOG.MAX_PULLS_PER_SWEEP * 5 + MOG.MAX_REFRESHES_PER_SWEEP
    assert MOG.RATE_LIMIT_FLOOR >= worst_case * 0.9, (
        f"floor {MOG.RATE_LIMIT_FLOOR} cannot fund a {MOG.MAX_PULLS_PER_SWEEP}-PR pass"
    )
    assert MOG.RATE_LIMIT_FLOOR < 1000, "a floor at the whole bucket never opens"
    typical = fixed + MOG.MAX_PULLS_PER_SWEEP
    assert typical * 27 <= 1000, (
        f"{MOG.MAX_PULLS_PER_SWEEP} pull requests x 27 sweeps/hour costs "
        f"{typical * 27} of a 1,000/hr budget"
    )
    assert typical * 3 < 121, "the cap must be a real reduction on the measured cost"
    assert MOG.RATE_LIMIT_RESERVE < MOG.RATE_LIMIT_FLOOR


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
        "acme/widgets", _pull(), "read", "write", _freshness(), _proof("ci-pack-3")
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
        "acme/widgets", _pull(), "read", "write", _freshness(), _proof("ci-pack-3")
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
        "acme/widgets", _pull(), "read", "write", _freshness(), _proof("ci-pack-3")
    )
    assert verdict == "blocked"
    assert any(call[1].endswith("/update-branch") for call in calls), "it tried"
    assert any(
        call[0] == "POST" and call[1].endswith("/labels") for call in calls
    ), "and then blocked exactly as before"

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
        "acme/widgets", _pull(), "read", "write", _freshness(), proof
    ) == "rebased"
    assert any(call[1].endswith("/update-branch") for call in calls)


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
    proof — the same mistake `proof_instant` refuses to make when one re-run re-dates a
    hundred stale checks. A proof is as fresh as its stalest component.
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

    Sweeps overlap by design (no `concurrency:` block, and three wake-ups can arrive
    within seconds), so several can all read "nothing in flight" and all dispatch.
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
        line.startswith("::notice") and "update-branch` slots" in line
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


def test_the_refresh_cap_does_not_change_behaviour_when_no_budget_is_passed(
    monkeypatch, capsys
):
    """`budget=None` must reproduce the pre-cap behaviour exactly, so every existing
    caller and test keeps its meaning."""
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-3", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    for number in range(1, 30):
        assert (
            MOG.sweep_pull(
                "acme/widgets",
                _pull(number),
                "read",
                "write",
                _freshness(),
                _proof("ci-pack-3"),
            )
            == "rebased"
        )
    assert len([c for c in calls if c[1].endswith("/update-branch")]) == 29


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
    assert int(job["timeout-minutes"]) == 12


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
