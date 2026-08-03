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


def test_the_workflow_parses_and_runs_on_a_ten_minute_schedule():
    parsed = _workflow()
    triggers = _triggers(parsed)
    crons = [entry.get("cron") for entry in (triggers.get("schedule") or [])]
    assert "*/10 * * * *" in crons, f"expected a 10-minute sweep, got {crons}"
    assert "workflow_dispatch" in triggers, "an operator must be able to force a sweep"


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
    assert permissions["contents"] == "write", "needed to squash-merge and delete the head ref"
    assert permissions["pull-requests"] == "write", "needed for merge-blocked + the comment"
    concurrency = parsed["concurrency"]
    assert concurrency["group"] == "merge-on-green"
    assert concurrency["cancel-in-progress"] is False, "a mid-merge sweep must finish"


def test_the_sweep_step_invokes_the_tracked_script_with_the_token_fallback():
    """The PAT is load-bearing: a GITHUB_TOKEN merge does not fire push-triggered
    workflows, so render.yml would never see a sweeper merge. The fallback keeps
    the lane working (degraded) when the PAT is absent."""
    step = _sweep_step(_workflow())
    env = step["env"]
    assert env["GH_REPO"] == "${{ github.repository }}"
    assert env["READ_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    assert env["MERGE_TOKEN"] == "${{ secrets.ADMIN_GH_TOKEN || secrets.GITHUB_TOKEN }}"


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


def _fake_api(monkeypatch, *, check_pages, merge_status=200, update_status=422):
    """Route every `_request` call by method+URL and record what was sent.

    `update_status` defaults to 422 — GitHub's "I cannot fast-forward this"
    answer — so a test that does not opt in keeps the old behaviour: a refused
    merge falls through to `merge-blocked`.
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


def test_one_bad_pull_request_does_not_fail_the_sweep(monkeypatch, capsys):
    """Individual outcomes are annotations, not job failures — a red PR must not
    stop the sweep from merging the clean ones behind it."""
    monkeypatch.setenv("GH_REPO", "acme/widgets")
    monkeypatch.setenv("READ_TOKEN", "read")
    monkeypatch.setenv("MERGE_TOKEN", "write")
    monkeypatch.setattr(MOG, "labeled_pulls", lambda *_a: [_pull(1), _pull(2)])

    def flaky(_repo, pull, *_a):
        if pull["number"] == 1:
            raise RuntimeError("transient")
        return "merged"

    monkeypatch.setattr(MOG, "sweep_pull", flaky)
    assert MOG.main() == 0
    assert "::warning" in capsys.readouterr().out


def test_a_missing_repository_is_a_real_failure(monkeypatch, capsys):
    monkeypatch.delenv("GH_REPO", raising=False)
    assert MOG.main() == 1
    assert "::error" in capsys.readouterr().out
