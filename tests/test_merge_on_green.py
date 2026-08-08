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


@pytest.fixture(autouse=True)
def _no_unstubbed_http(monkeypatch):
    """No test in this pack may reach api.github.com.

    Added 2026-08-07, because the budget work introduced two NEW network entry
    points into `main()` — `core_rate_limit` and `main_clean_check_names` — and both
    swallow their own errors by design (fail-open and fail-closed respectively). A
    test that forgot to stub them would therefore still PASS, silently making a real
    HTTP call, taking a 30-second timeout on an offline runner, and asserting about a
    code path it never exercised. A test that needs HTTP overrides this with its own
    `monkeypatch.setattr(MOG, "_request", ...)`, which lands after this fixture.
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
    # `main_clean_check_names` deliberately gets NO default: it swallows every error
    # by design, so the refusing `_request` above already gives it its neutral
    # fail-closed answer (the empty set) without a real call — and leaving the real
    # function in place keeps the tests that exercise it exercising it.
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
    aborts — so the install is a step, not a hope, and it must precede the sweep."""
    steps = _workflow()["jobs"]["sweep"]["steps"]
    runs = [str(step.get("run") or "") for step in steps]
    installs = [index for index, run in enumerate(runs) if "pip install" in run and "pyyaml" in run]
    sweeps = [index for index, run in enumerate(runs) if "scripts/merge_on_green.py" in run]
    assert installs and sweeps, f"expected an install step and a sweep step, got {runs}"
    assert installs[0] < sweeps[0], "the parser must be installed before the sweep runs"


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


# A check run is dated now, because a green that cannot be dated cannot be trusted
# (#4583). Everything in this file that is not ABOUT the date uses these two stamps:
# the proof is computed at 12:00Z and the one main commit on the timeline landed at
# 09:00Z, comfortably before it, so `stale_for` answers "main has not moved".
PROOF_STARTED_AT = "2026-08-05T12:00:00Z"
BEFORE_THE_PROOF = "2026-08-05T09:00:00Z"


def _run(
    name: str,
    status: str = "completed",
    conclusion=None,
    started_at: str | None = PROOF_STARTED_AT,
) -> dict:
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "started_at": started_at,
    }


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
    monkeypatch.setattr(MOG, "main_clean_check_names", lambda *_a: set())
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

    The fixed overhead is ~12, NOT the ~6 this arithmetic originally used: since
    #4854, `main_clean_check_names` walks main newest->oldest until it finds a commit
    that published checks (measured 5 back, so ~7 calls) instead of reading the tip
    once. So a capped pass costs ~12 + 25 = ~37, sustainable up to floor(1000/37) =
    27 sweeps/hour. The worst hour ever observed was 28, which overshoots by ~4% —
    absorbed by RATE_LIMIT_RESERVE, which stops the pass mid-sweep rather than
    letting it 403. Compare the uncapped cost that caused the outage: ~121/sweep.
    """
    fixed = 12
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
        "acme/widgets", _pull(), "read", "write", _freshness(), {"ci-pack-3"}
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
        "acme/widgets", _pull(), "read", "write", _freshness(), {"ci-pack-3"}
    )
    assert verdict == "blocked"
    assert not any(call[1].endswith("/update-branch") for call in calls), \
        "a genuine red must never be refreshed"


def test_an_unreadable_main_blocks_exactly_as_before(monkeypatch, capsys):
    """Fail-closed: no knowledge of main is never permission to refresh."""
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-3", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=202)
    verdict = MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(), set()
    )
    assert verdict == "blocked"
    assert not any(call[1].endswith("/update-branch") for call in calls)


def test_a_head_already_current_falls_through_and_cannot_loop(monkeypatch, capsys):
    """update-branch answers 422 when there is nothing to fast-forward.

    That is precisely the case where the red must be the pull request's own, so the
    call falls through to `merge-blocked`. This is what makes the branch
    self-terminating — a PR can never be refreshed twice for the same red.
    """
    pages = {1: {"total_count": 1, "check_runs": [_run("ci-pack-3", conclusion="failure")]}}
    calls = _fake_api(monkeypatch, check_pages=pages, update_status=422)
    verdict = MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _freshness(), {"ci-pack-3"}
    )
    assert verdict == "blocked"
    assert any(call[1].endswith("/update-branch") for call in calls), "it tried"
    assert any(
        call[0] == "POST" and call[1].endswith("/labels") for call in calls
    ), "and then blocked exactly as before"


def _commits(*shas):
    return [{"sha": sha} for sha in shas]


def test_main_clean_check_names_is_fail_closed_on_an_unreadable_main(monkeypatch):
    """Any error walking main yields an EMPTY set — never a permissive one."""
    def boom(method, url, token, payload=None):
        if "/commits?" in url:
            return 500, {}
        return 200, {}

    monkeypatch.setattr(MOG, "_request", boom)
    assert MOG.main_clean_check_names("acme/widgets", "read") == set()


def test_main_clean_check_names_walks_past_commits_that_published_no_checks(monkeypatch):
    """The tip is usually a `[skip ci]` wire tick or a research_vault catalog.

    Measured 2026-08-07: NINE of main's last fourteen commits carried no check runs
    at all and the tip had none either, with the newest proved commit five back.
    Reading only the tip returned a set with no packs in it, which would have left
    the base-inherited-red refresh inert while looking like it worked.

    The fake HONOURS `per_page`, which is what makes this test pin MAIN_PROOF_WALK
    itself rather than only the loop around it. A stub that returns three commits no
    matter what was asked for stays green with `per_page=1` — i.e. with the walk
    degenerated back to a tip read, the exact regression this test is named for.
    """
    checks = {
        "b" * 40: {  # the proved commit, two back
            "total_count": 2,
            "check_runs": [
                _run("ci-pack-0", conclusion="success"),
                _run("ci-pack-1", conclusion="failure"),
            ],
        }
    }

    def fake(method, url, token, payload=None):
        if "/commits?" in url:
            asked = int(url.rsplit("per_page=", 1)[1].split("&")[0])
            assert asked >= 3, (
                f"the walk asked for {asked} commit(s); it must reach past the "
                "check-less tip commits this repo pushes every few minutes"
            )
            return 200, _commits("a" * 40, "c" * 40, "b" * 40)[:asked]
        if "/check-runs" in url:
            sha = url.split("/commits/")[1].split("/")[0]
            page = int(url.rsplit("page=", 1)[1].split("&")[0])
            if page > 1:
                return 200, {"total_count": 0, "check_runs": []}
            return 200, checks.get(sha, {"total_count": 0, "check_runs": []})
        return 200, {}

    monkeypatch.setattr(MOG, "_request", fake)
    # walks past the two check-less commits and answers from the proved one alone
    assert MOG.main_clean_check_names("acme/widgets", "read") == {"ci-pack-0"}


def test_main_clean_check_names_walks_past_commits_that_publish_only_ambient_checks(
        monkeypatch):
    """The regression that made the whole refresh path inert (2026-08-08).

    `test_..._walks_past_commits_that_published_no_checks` above covers a tip carrying
    NOTHING. The real tip carries SOMETHING ELSE. Measured on main `483242ab4b0` with
    main fully green four packs deep only five commits back, the tip's completed
    non-spurious checks were exactly `sweep` and `Supabase Preview` — every wire tick
    and research_vault catalog carries its own per-push workflows. Stopping at the
    first commit with ANY non-spurious check therefore answered `{sweep}`, which can
    never be a superset of a pack red, so `bad_names <= main_clean` was false for
    every armed PR forever: `0 main commit(s) classified`, 21 left merge-blocked.

    Pins that an ambient-only commit does not end the walk.
    """
    checks = {
        "a" * 40: {  # the nightly tip: real checks, but no packs
            "total_count": 2,
            "check_runs": [
                _run("sweep", conclusion="success"),
                _run("Supabase Preview", conclusion="failure"),
            ],
        },
        "b" * 40: {  # the commit that actually ran ci.yml
            "total_count": 2,
            "check_runs": [
                _run("ci-pack-0", conclusion="success"),
                _run("ci-pack-1", conclusion="success"),
            ],
        },
    }

    def fake(method, url, token, payload=None):
        if "/commits?" in url:
            asked = int(url.rsplit("per_page=", 1)[1].split("&")[0])
            return 200, _commits("a" * 40, "b" * 40)[:asked]
        if "/check-runs" in url:
            sha = url.split("/commits/")[1].split("/")[0]
            page = int(url.rsplit("page=", 1)[1].split("&")[0])
            if page > 1:
                return 200, {"total_count": 0, "check_runs": []}
            return 200, checks.get(sha, {"total_count": 0, "check_runs": []})
        return 200, {}

    monkeypatch.setattr(MOG, "_request", fake)
    clean = MOG.main_clean_check_names("acme/widgets", "read")
    # the packs are reachable — this is the assertion the old code failed
    assert {"ci-pack-0", "ci-pack-1"} <= clean
    # the ambient commit is still folded in newest-first: sweep passed, Supabase did not
    assert "sweep" in clean and "Supabase Preview" not in clean


def test_a_fresher_pack_failure_beats_an_older_pass_for_the_same_name(monkeypatch):
    """Newest-wins per NAME is what makes walking past the tip safe.

    The no-union rule exists so "a check that passed four commits ago" cannot excuse
    "a red the very next commit introduced". Walking further could reintroduce exactly
    that if an older CLEAN conclusion were allowed to overwrite a newer bad one — so
    pin the ordering directly, with the failure NEWER than the pass.
    """
    checks = {
        "a" * 40: {"total_count": 1, "check_runs": [_run("sweep", conclusion="success")]},
        "b" * 40: {  # newer of the two ci runs: ci-pack-2 is RED here
            "total_count": 2,
            "check_runs": [
                _run("ci-pack-2", conclusion="failure"),
                _run("ci-pack-3", conclusion="success"),
            ],
        },
        "c" * 40: {  # older: ci-pack-2 was green, and must NOT rescue it
            "total_count": 1,
            "check_runs": [_run("ci-pack-2", conclusion="success")],
        },
    }

    def fake(method, url, token, payload=None):
        if "/commits?" in url:
            asked = int(url.rsplit("per_page=", 1)[1].split("&")[0])
            return 200, _commits("a" * 40, "b" * 40, "c" * 40)[:asked]
        if "/check-runs" in url:
            sha = url.split("/commits/")[1].split("/")[0]
            page = int(url.rsplit("page=", 1)[1].split("&")[0])
            if page > 1:
                return 200, {"total_count": 0, "check_runs": []}
            return 200, checks.get(sha, {"total_count": 0, "check_runs": []})
        return 200, {}

    monkeypatch.setattr(MOG, "_request", fake)
    clean = MOG.main_clean_check_names("acme/widgets", "read")
    assert "ci-pack-2" not in clean, "an older pass rescued a newer failure"
    assert {"ci-pack-3", "sweep"} <= clean


def test_main_clean_check_names_answers_from_one_commit_never_a_union(monkeypatch):
    """A union would let a pass four commits ago excuse a red introduced since."""
    checks = {
        "a" * 40: {"total_count": 1, "check_runs": [_run("ci-pack-0", conclusion="failure")]},
        "b" * 40: {"total_count": 1, "check_runs": [_run("ci-pack-0", conclusion="success")]},
    }

    def fake(method, url, token, payload=None):
        if "/commits?" in url:
            return 200, _commits("a" * 40, "b" * 40)
        if "/check-runs" in url:
            sha = url.split("/commits/")[1].split("/")[0]
            page = int(url.rsplit("page=", 1)[1].split("&")[0])
            if page > 1:
                return 200, {"total_count": 0, "check_runs": []}
            return 200, checks.get(sha, {"total_count": 0, "check_runs": []})
        return 200, {}

    monkeypatch.setattr(MOG, "_request", fake)
    # newest PROVED commit is red on ci-pack-0 -> it is NOT clean, and the older
    # commit's success must not rescue it
    assert MOG.main_clean_check_names("acme/widgets", "read") == set()


def test_main_clean_check_names_ignores_the_spurious_check_and_pending_runs(monkeypatch):
    """Only CONCLUDED, non-spurious, clean names may widen what a red PR can do."""
    def fake(method, url, token, payload=None):
        if "/commits?" in url:
            return 200, _commits("a" * 40)
        if "/check-runs" in url:
            page = int(url.rsplit("page=", 1)[1].split("&")[0])
            if page > 1:
                return 200, {"total_count": 0, "check_runs": []}
            return 200, {
                "total_count": 4,
                "check_runs": [
                    _run("ci-pack-0", conclusion="success"),
                    _run("Workers Builds: macro", conclusion="success"),
                    _run("ci-pack-1", status="in_progress", conclusion=None),
                    _run("ci-pack-2", conclusion="failure"),
                ],
            }
        return 200, {}

    monkeypatch.setattr(MOG, "_request", fake)
    assert MOG.main_clean_check_names("acme/widgets", "read") == {"ci-pack-0"}


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
            {"ci-pack-3"},
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
            {"ci-pack-3"},
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
        {"ci-pack-3"},
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
        set(),
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
                {"ci-pack-3"},
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
