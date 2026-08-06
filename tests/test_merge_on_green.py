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

import json
from pathlib import Path

import pytest
import yaml

import scripts.merge_on_green as MOG


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "merge-on-green.yml"
BASELINE_WORKFLOW = ROOT / ".github" / "workflows" / "integration-baseline.yml"


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


def test_the_sweep_is_github_hosted_and_bounded():
    """OFF the mac pool on purpose: a merge sweep queued behind a 67-minute render
    would defeat its own purpose."""
    job = _workflow()["jobs"]["sweep"]
    assert job["runs-on"] == "ubuntu-latest"
    assert "self-hosted" not in json.dumps(job["runs-on"])
    assert int(job["timeout-minutes"]) == 15


def test_the_workflow_can_actually_merge_and_label():
    parsed = _workflow()
    permissions = parsed["permissions"]
    assert permissions["actions"] == "read", "needed for the main-baseline circuit breaker"
    assert permissions["contents"] == "write", "needed to squash-merge and delete the head ref"
    assert permissions["pull-requests"] == "write", "needed for merge-blocked + the comment"


def test_no_concurrency_group_may_serialise_this_lane():
    """The 2026-08-06 livelock. Do not reintroduce `concurrency:` here.

    `group: merge-on-green` + `cancel-in-progress: false` was chosen so a
    mid-merge sweep could finish. It achieved the opposite: `cancel-in-progress:
    false` protects only an IN-PROGRESS run, GitHub keeps exactly ONE pending run
    per group and cancels it on every new arrival, and the pending state includes
    the wait for a runner. `ci` and `fences` share `ubuntu-latest` with this job
    (48 and 34 queued against 8 and 1 running when this was measured), so the
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


def test_the_sweeper_sparse_checks_out_only_its_script():
    checkout = _workflow()["jobs"]["sweep"]["steps"][0]
    assert checkout["uses"] == "actions/checkout@v4"
    options = checkout["with"]
    assert options["filter"] == "blob:none"
    assert options["sparse-checkout"] == "scripts/merge_on_green.py"
    assert options["sparse-checkout-cone-mode"] is False


def test_the_main_baseline_is_fast_bounded_and_runs_the_merge_train_contract():
    parsed = yaml.safe_load(BASELINE_WORKFLOW.read_text(encoding="utf-8"))
    triggers = _triggers(parsed)
    assert "push" in triggers and triggers["push"]["branches"] == ["main"]
    job = parsed["jobs"]["baseline"]
    assert job["runs-on"] == "ubuntu-latest"
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


def _run(name: str, status: str = "completed", conclusion=None) -> dict:
    return {"name": name, "status": status, "conclusion": conclusion}


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


# --- the sweep itself, with HTTP mocked ---------------------------------------


def _fake_api(
    monkeypatch, *, check_pages, merge_status=200, update_status=422, pull_payload=None
):
    """Route every `_request` call by method+URL and record what was sent.

    `update_status` defaults to 422 — GitHub's "I cannot fast-forward this"
    answer — so a test that does not opt in keeps the old behaviour: a refused
    merge falls through to `merge-blocked`.

    `pull_payload` is what a re-read of the pull request itself returns. It
    defaults to `{}` — an open, unmerged pull request — so the `already_settled`
    guard stays inert for every test that is not about the concurrent-sweep race.
    """
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(method, url, token, payload=None):
        calls.append((method, url, payload))
        if "/check-runs" in url:
            page = int(url.rsplit("page=", 1)[1].split("&")[0])
            return 200, check_pages.get(page, {"total_count": 0, "check_runs": []})
        if url.endswith("/update-branch"):
            if update_status in {200, 202}:
                return update_status, {"message": "Updating pull request branch."}
            return update_status, {"message": "merge conflict between base and head"}
        if url.endswith("/merge"):
            if merge_status == 200:
                return 200, {"sha": "c" * 40, "merged": True}
            return merge_status, {"message": "Pull Request is not mergeable"}
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
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write") == "merged"
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
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write") == "pending"
    assert [call for call in calls if call[0] != "GET"] == [], "waiting must be side-effect free"


def test_a_red_pull_request_is_labeled_and_commented_exactly_once(monkeypatch, capsys):
    """The sweep runs every 10 minutes; commenting on every pass would post ~144
    comments a day. The comment rides ONLY the label transition."""
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-1", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages)
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write") == "blocked"
    posts = [call for call in calls if call[0] == "POST"]
    assert any(call[1].endswith("/labels") for call in posts)
    comments = [call for call in posts if call[1].endswith("/comments")]
    assert len(comments) == 1
    assert "ci-pack-1 (failure)" in comments[0][2]["body"]

    # Second pass, with the label already present: no label call, no comment.
    calls = _fake_api(monkeypatch, check_pages=pages)
    already = _pull(labels=("merge-on-green", "merge-blocked"))
    assert MOG.sweep_pull("acme/widgets", already, "read", "write") == "blocked"
    assert [call for call in calls if call[0] == "POST"] == [], "must never re-comment"


def test_an_unproven_head_is_never_merged_and_says_so(monkeypatch, capsys):
    calls = _fake_api(monkeypatch, check_pages={1: {"total_count": 0, "check_runs": []}})
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write") == "unproven"
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
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write") == "conflict"
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
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write") == "already-merged"

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
    out = capsys.readouterr().out
    assert out.startswith("::notice") and "concurrent sweep" in out


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
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write") == "conflict"


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
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write") == "updated"

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
    assert MOG.sweep_pull("acme/widgets", already, "read", "write") == "updated"
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
    assert MOG.sweep_pull("acme/widgets", _pull(), "read", "write") == "blocked"
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
        ("in_progress", None, "pending"),
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
                }]
            }
        if "/git/ref/heads/main" in url:
            return 200, {"object": {"sha": sha}}
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", fake_request)
    assert MOG.integration_baseline_state("acme/widgets", "read")[0] == expected


def _baseline_runs(monkeypatch, runs, main_sha):
    """Serve `runs` newest-first from the workflow-runs endpoint."""

    def fake_request(method, url, token, payload=None):
        if "/actions/workflows/" in url:
            return 200, {"workflow_runs": runs}
        if "/git/ref/heads/main" in url:
            return 200, {"object": {"sha": main_sha}}
        if "/compare/" in url:
            return 200, {"status": "ahead"}
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", fake_request)


def _baseline_run(conclusion, sha, status="completed"):
    return {
        "status": status,
        "conclusion": conclusion,
        "head_sha": sha,
        "html_url": f"https://example.test/run/{conclusion}",
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


def test_an_in_flight_newest_run_outranks_an_older_green(monkeypatch):
    """A baseline still running is pending — an older green cannot vouch for the
    commit it has not finished testing."""
    sha = "f" * 40
    _baseline_runs(
        monkeypatch,
        [_baseline_run(None, sha, status="in_progress"), _baseline_run("success", "a" * 40)],
        main_sha=sha,
    )
    assert MOG.integration_baseline_state("acme/widgets", "read")[0] == "pending"


def test_one_bad_pull_request_does_not_fail_the_sweep(monkeypatch, capsys):
    """Individual outcomes are annotations, not job failures — a red PR must not
    stop the sweep from merging the clean ones behind it."""
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setenv("MERGE_TOKEN", "write")
    monkeypatch.setattr(MOG, "labeled_pulls", lambda *_a: [_pull(1), _pull(2)])
    monkeypatch.setattr(MOG, "integration_baseline_state", lambda *_a: ("green", "ok"))

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
    swept: list[int] = []

    def record(_repo, pull, *_a):
        swept.append(pull["number"])
        return "merged"

    monkeypatch.setattr(MOG, "sweep_pull", record)
    assert MOG.main() == 0
    assert swept == [2], "a broken baseline admits exactly one explicit repair per pass"
    out = capsys.readouterr().out
    assert "circuit breaker" in out and "2 baseline-blocked" in out


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
