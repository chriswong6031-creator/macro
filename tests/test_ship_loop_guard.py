"""Regression tests for the tracked Claude completion guard."""

from __future__ import annotations

import email.message
import importlib.util
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = ROOT / ".claude" / "hooks" / "ship_loop_guard.py"
SPEC = importlib.util.spec_from_file_location("ship_loop_guard", HOOK_PATH)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "kept.txt").write_text("baseline\n", encoding="utf-8")
    _git(repo, "add", "kept.txt")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_fingerprint_ignores_unchanged_baseline_dirt(tmp_path):
    repo = _repo(tmp_path)
    (repo / "kept.txt").write_text("pre-existing\n", encoding="utf-8")
    baseline = GUARD._fingerprint(repo)
    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == []


def test_fingerprint_detects_session_edit_on_dirty_baseline(tmp_path):
    repo = _repo(tmp_path)
    (repo / "kept.txt").write_text("pre-existing\n", encoding="utf-8")
    baseline = GUARD._fingerprint(repo)
    (repo / "kept.txt").write_text("session edit\n", encoding="utf-8")
    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == ["kept.txt"]


def test_fingerprint_detects_new_and_deleted_paths(tmp_path):
    repo = _repo(tmp_path)
    baseline = GUARD._fingerprint(repo)
    (repo / "new.txt").write_text("new\n", encoding="utf-8")
    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == ["new.txt"]
    (repo / "new.txt").unlink()
    (repo / "kept.txt").unlink()
    assert GUARD._changed_since_baseline(baseline, GUARD._fingerprint(repo)) == ["kept.txt"]


def test_github_slug_accepts_https_and_ssh(monkeypatch, tmp_path):
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        GUARD, "_run", lambda *_args, **_kwargs: "https://github.com/acme/widgets.git"
    )
    assert GUARD._github_slug(repo) == ("acme", "widgets")
    monkeypatch.setattr(GUARD, "_run", lambda *_args, **_kwargs: "git@github.com:acme/widgets.git")
    assert GUARD._github_slug(repo) == ("acme", "widgets")


def test_find_commit_handles_nested_health_payload():
    payload = {"ok": True, "deployment": {"revision": "a" * 40}}
    assert GUARD._find_commit(payload) == "a" * 40


def _commit(repo: Path, rel: str, body: str, message: str) -> str:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def test_needs_render_only_when_the_merge_itself_touched_render_inputs(tmp_path):
    """The render precondition must match render.yml's push path filter.

    render.yml's push trigger only fires on templates/** + scripts/build_*.py, so
    a merge that touched neither never queues a render of its own, and demanding
    one is an unsatisfiable block rather than a real gap. (_render_status may now
    also accept a later main descendant's render — that widens what SATISFIES the
    requirement, not which merges carry one.)
    """
    repo = _repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    # A CONCURRENT session's template merge lands first — this is what used to
    # poison the session-range basis for every later unrelated merge.
    _commit(repo, "templates/index.html", "<p>other session</p>\n", "other: hero")
    mine = _commit(repo, ".github/workflows/ci.yml", "on: push\n", "ci: wire a test")

    assert GUARD._needs_render(repo, mine, start_head, mine) is False, (
        "a ci.yml-only merge must not require a render it can never have"
    )
    # And the session range genuinely does contain templates/ — proving the
    # False above comes from correct scoping, not from an empty diff.
    session_range = _git(repo, "diff", "--name-only", start_head, mine).splitlines()
    assert "templates/index.html" in session_range


def test_needs_render_still_fires_on_a_real_template_or_builder_merge(tmp_path):
    """The fix must not weaken the gate for merges that DO render."""
    repo = _repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    tmpl = _commit(repo, "templates/macro.html.j2", "{{ x }}\n", "feat: template")
    assert GUARD._needs_render(repo, tmpl, start_head, tmpl) is True

    builder = _commit(repo, "scripts/build_thing.py", "print(1)\n", "feat: builder")
    assert GUARD._needs_render(repo, builder, start_head, builder) is True

    # A sibling script that is not a build_* entrypoint must not trigger one.
    other = _commit(repo, "scripts/check_thing.py", "print(2)\n", "chore: checker")
    assert GUARD._needs_render(repo, other, start_head, other) is False


@pytest.fixture(autouse=True)
def _clear_token_cache(monkeypatch):
    """The token is memoised per process; tests must not inherit each other's."""
    monkeypatch.setattr(GUARD, "_TOKEN_CACHE", None, raising=False)
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(key, raising=False)


def _fake_gh(returncode: int, stdout: str, calls: list):
    def runner(args, **kwargs):
        calls.append(tuple(args))
        return subprocess.CompletedProcess(args, returncode, stdout, "")

    return runner


def test_token_falls_back_to_the_gh_cli_when_no_env_var_is_set(monkeypatch):
    """The whole bug: Claude sessions set no token, so the guard ran anonymous at 60/hour."""
    calls: list = []
    monkeypatch.setattr(GUARD.subprocess, "run", _fake_gh(0, "gho_fromcli\n", calls))
    assert GUARD._github_token() == "gho_fromcli"
    assert calls and calls[0][:3] == ("gh", "auth", "token")


def test_token_prefers_the_environment_over_the_cli(monkeypatch):
    calls: list = []
    monkeypatch.setenv("GH_TOKEN", "from-env")
    monkeypatch.setattr(GUARD.subprocess, "run", _fake_gh(0, "from-cli", calls))
    assert GUARD._github_token() == "from-env"
    assert calls == [], "an env token must not spawn the CLI"


def test_token_is_cached_for_the_process(monkeypatch):
    """A Stop evaluation makes four API calls; it must not shell out four times."""
    calls: list = []
    monkeypatch.setattr(GUARD.subprocess, "run", _fake_gh(0, "gho_cached", calls))
    assert GUARD._github_token() == GUARD._github_token() == GUARD._github_token()
    assert len(calls) == 1


@pytest.mark.parametrize(
    "runner",
    [
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("gh not installed")),
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("gh", 5)),
        lambda args, **k: subprocess.CompletedProcess(args, 1, "", "not logged in"),
    ],
)
def test_token_degrades_to_anonymous_when_the_cli_cannot_help(monkeypatch, runner):
    """A missing, hung, or logged-out gh must degrade — never break the hook."""
    monkeypatch.setattr(GUARD.subprocess, "run", runner)
    assert GUARD._github_token() == ""


def _capture_requests(monkeypatch) -> list:
    sent: list = []

    def fake_urlopen(request, *args, **kwargs):
        sent.append(request)
        raise urllib.error.URLError("captured")

    monkeypatch.setattr(GUARD.urllib.request, "urlopen", fake_urlopen)
    return sent


def test_the_github_token_is_never_sent_to_the_live_health_host(monkeypatch):
    """_get_json serves both GitHub and production health.

    Authenticating unconditionally would hand a repo-scoped credential to an
    unrelated host on every Stop evaluation — harmless only while no token
    existed, which is exactly the state the CLI fallback ends.
    """
    monkeypatch.setattr(GUARD.subprocess, "run", _fake_gh(0, "gho_secret", []))
    sent = _capture_requests(monkeypatch)

    for url in (f"https://{GUARD.GITHUB_API_HOST}/repos/a/b/pulls", GUARD.LIVE_HEALTH_URL):
        with pytest.raises(Exception):
            GUARD._get_json(url)

    by_host = {request.host: request for request in sent}
    assert by_host[GUARD.GITHUB_API_HOST].get_header("Authorization") == "Bearer gho_secret"
    live_host = urllib.parse.urlsplit(GUARD.LIVE_HEALTH_URL).hostname
    assert by_host[live_host].get_header("Authorization") is None
    assert "gho_secret" not in json.dumps(dict(by_host[live_host].header_items()))


def _http_error(code: int, reason: str, **headers) -> urllib.error.HTTPError:
    message = email.message.Message()
    for key, value in headers.items():
        message[key.replace("_", "-")] = value
    return urllib.error.HTTPError("https://api.github.com/x", code, reason, message, None)


def test_spent_quota_is_reported_as_rate_limited_not_unreachable(monkeypatch):
    """`HTTP Error 403: rate limit exceeded` read as a repo/network fault it never was."""
    # Pin the anonymous case: an unpinned token would consult the real `gh` and
    # make this assertion depend on whether the host happens to be logged in.
    monkeypatch.setattr(GUARD, "_TOKEN_CACHE", "", raising=False)
    error = GUARD._http_failure(
        _http_error(
            403,
            "rate limit exceeded",
            X_RateLimit_Remaining="0",
            X_RateLimit_Limit="60",
            X_RateLimit_Reset="1785010477",
        )
    )
    assert isinstance(error, GUARD.RateLimited)
    assert GUARD._github_block_code(error) == "github_rate_limited"
    assert "quota" in str(error).lower()
    assert "UNAUTHENTICATED" in str(error), "must name the fix when running anonymous"


def test_an_authenticated_quota_message_does_not_tell_you_to_log_in(monkeypatch):
    monkeypatch.setattr(GUARD, "_TOKEN_CACHE", "already-authenticated", raising=False)
    error = GUARD._http_failure(
        _http_error(403, "rate limit exceeded", X_RateLimit_Remaining="0", X_RateLimit_Limit="5000")
    )
    assert isinstance(error, GUARD.RateLimited)
    assert "gh auth login" not in str(error)


@pytest.mark.parametrize(
    "error",
    [
        _http_error(404, "Not Found"),
        _http_error(500, "Server Error"),
        _http_error(403, "Forbidden", X_RateLimit_Remaining="55"),
        urllib.error.HTTPError("u", 403, "rate limit exceeded", None, None),
    ],
)
def test_genuine_failures_stay_github_unreachable(error):
    """Only an actually-spent quota reclassifies; everything else keeps the old code."""
    failure = GUARD._http_failure(error)
    assert not isinstance(failure, GUARD.RateLimited)
    assert GUARD._github_block_code(failure) == "github_unreachable"


def test_rate_limited_has_the_same_escape_class_as_the_blocker_it_split_from():
    assert "github_rate_limited" in GUARD.EXTERNAL_BLOCKERS
    assert "github_unreachable" in GUARD.EXTERNAL_BLOCKERS


def test_check_ci_still_blocks_on_a_red_check(monkeypatch):
    """The authentication work must not soften the gate it exists to evaluate."""
    monkeypatch.setattr(
        GUARD,
        "_get_json",
        lambda _url: {
            "check_runs": [
                {"name": "ci", "status": "completed", "conclusion": "failure"},
                {"name": "lint", "status": "completed", "conclusion": "success"},
            ]
        },
    )
    ok, reason = GUARD._check_ci("acme", "widgets", "d" * 40)
    assert ok is False
    assert reason.startswith("Failing"), "_stop keys the ci_failed code off this prefix"
    assert "ci (failure)" in reason


def test_check_ci_passes_only_when_every_real_check_is_green(monkeypatch):
    monkeypatch.setattr(
        GUARD,
        "_get_json",
        lambda _url: {
            "check_runs": [
                {"name": "ci", "status": "completed", "conclusion": "success"},
                {"name": "Workers Builds: macro", "status": "completed", "conclusion": "failure"},
            ]
        },
    )
    assert GUARD._check_ci("acme", "widgets", "e" * 40) == (True, "")

    monkeypatch.setattr(
        GUARD, "_get_json", lambda _url: {"check_runs": [{"name": "ci", "status": "in_progress"}]}
    )
    ok, reason = GUARD._check_ci("acme", "widgets", "f" * 40)
    assert ok is False and reason.startswith("CI still running")

    monkeypatch.setattr(GUARD, "_get_json", lambda _url: {"check_runs": []})
    assert GUARD._check_ci("acme", "widgets", "0" * 40)[0] is False


_RENDER_ENDPOINT = "actions/workflows/render.yml/runs"
_MERGED_AT = "2026-07-26T06:11:36Z"


def _merge_train(tmp_path: Path) -> tuple[Path, str, str, str]:
    """A real repo shaped like a merge train: parent -> merge -> a later merge.

    Ancestry is decided by git itself, so these are genuine 40-char shas rather
    than strings that only look related.
    """
    repo = _repo(tmp_path)
    parent = _git(repo, "rev-parse", "HEAD")
    merge = _commit(repo, "templates/mine.html", "<p>mine</p>\n", "feat: my merge")
    descendant = _commit(repo, "templates/later.html", "<p>later</p>\n", "feat: a later merge")
    return repo, parent, merge, descendant


def _render_run(run_id: int, head_sha: str, event: str, created_at: str, status: str, conclusion=None):
    return {
        "id": run_id,
        "head_sha": head_sha,
        "head_branch": "main",
        "event": event,
        "created_at": created_at,
        "status": status,
        "conclusion": conclusion,
    }


def _fake_render_api(monkeypatch, *, exact: list, branch: list) -> list:
    """Serve the two render listings by query string and record every URL fetched."""
    urls: list = []

    def fake_get_json(url: str):
        urls.append(url)
        assert _RENDER_ENDPOINT in url, f"unexpected endpoint: {url}"
        if "head_sha=" in url:
            return {"workflow_runs": exact}
        assert "branch=main" in url, f"neither an exact-sha nor a main listing: {url}"
        return {"workflow_runs": branch}

    monkeypatch.setattr(GUARD, "_get_json", fake_get_json)
    return urls


def test_render_status_accepts_the_exact_sha_success_in_one_call(monkeypatch, tmp_path):
    """The common case must stay a single API call — the descendant scan is a fallback."""
    repo, _parent, merge, _descendant = _merge_train(tmp_path)
    urls = _fake_render_api(
        monkeypatch,
        exact=[_render_run(1, merge, "push", "2026-07-26T06:11:38Z", "completed", "success")],
        branch=[_render_run(2, merge, "push", "2026-07-26T06:11:38Z", "completed", "failure")],
    )
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT) == ("success", "")
    assert len(urls) == 1 and "head_sha=" in urls[0], "the branch listing must not be fetched"


def test_a_superseded_train_member_is_covered_by_a_later_descendant_render(monkeypatch, tmp_path):
    """THE regression. render.yml coalesces, so exact-sha-only was unsatisfiable.

    2026-07-26 merge train: PR #3572 merged as b4449443590 and its push render
    30190635141 was superseded-cancelled seconds later by a newer merge queuing
    its own run (`cancel-in-progress: false` supersedes the PENDING run, not the
    running one). Descendant run 30193723520 then concluded success at
    8f5cfe12a66 — whose scope union already covered b4449443590 — yet the guard
    demanded a dedicated run at the merge sha that could never exist, forcing a
    manual ~50-minute rerun.
    """
    repo, _parent, merge, descendant = _merge_train(tmp_path)
    urls = _fake_render_api(
        monkeypatch,
        exact=[
            _render_run(30190635141, merge, "push", "2026-07-26T06:11:38Z", "completed", "cancelled")
        ],
        branch=[
            _render_run(
                30193723520, descendant, "push", "2026-07-26T07:57:25Z", "completed", "success"
            )
        ],
    )
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT) == ("success", "")
    assert len(urls) == 2, "the descendant scan costs exactly one extra call"


def test_an_in_flight_descendant_render_holds_the_verdict_at_pending(monkeypatch, tmp_path):
    """A running render may still deliver coverage; that is pending, never failed."""
    repo, _parent, merge, descendant = _merge_train(tmp_path)
    _fake_render_api(
        monkeypatch,
        exact=[_render_run(1, merge, "push", "2026-07-26T06:11:38Z", "completed", "cancelled")],
        branch=[
            _render_run(2, descendant, "push", "2026-07-26T07:57:25Z", "in_progress")
        ],
    )
    status, detail = GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT)
    assert status == "pending"
    assert "in_progress" in detail


def test_a_failed_descendant_render_blocks_and_a_pre_merge_success_cannot_rescue_it(
    monkeypatch, tmp_path
):
    """Coverage needs a DESCENDANT: a green re-run of pre-merge history rendered a tree
    that never contained this merge, even though it ran after the merge landed."""
    repo, parent, merge, descendant = _merge_train(tmp_path)
    _fake_render_api(
        monkeypatch,
        exact=[_render_run(1, merge, "push", "2026-07-26T06:11:38Z", "completed", "cancelled")],
        branch=[
            _render_run(2, descendant, "push", "2026-07-26T07:57:25Z", "completed", "failure"),
            _render_run(3, parent, "push", "2026-07-26T08:10:00Z", "completed", "success"),
        ],
    )
    status, detail = GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT)
    assert status == "failed", "a success on the merge's PARENT is not coverage"
    assert "failure" in detail and "descendant" in detail
    assert "gh run rerun 2" in detail, "the remediation must name the concluded run"


def test_only_a_push_lane_render_after_the_merge_can_cover_it(monkeypatch, tmp_path):
    """The event set and the created-at floor both have to hold, or coverage is fiction."""
    repo, _parent, merge, descendant = _merge_train(tmp_path)
    superseded = [
        _render_run(1, merge, "push", "2026-07-26T06:11:38Z", "completed", "cancelled")
    ]

    # A nightly `schedule` run is not the push lane this merge queued into.
    _fake_render_api(
        monkeypatch,
        exact=superseded,
        branch=[
            _render_run(2, descendant, "schedule", "2026-07-26T07:57:25Z", "completed", "success")
        ],
    )
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT)[0] == "failed"

    # Belt-and-braces: a run created BEFORE the merge cannot have carried it.
    _fake_render_api(
        monkeypatch,
        exact=superseded,
        branch=[
            _render_run(3, descendant, "push", "2026-07-26T05:00:00Z", "completed", "success")
        ],
    )
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT)[0] == "failed"

    # Same sha, on the lane and inside the window: a manual dispatch does cover it.
    _fake_render_api(
        monkeypatch,
        exact=superseded,
        branch=[
            _render_run(
                4, descendant, "workflow_dispatch", "2026-07-26T07:57:25Z", "completed", "success"
            )
        ],
    )
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT) == ("success", "")


def test_no_render_run_at_all_is_still_the_just_merged_race(monkeypatch, tmp_path):
    """Nothing has started yet must stay pending — the widened scan must not turn it red."""
    repo, _parent, merge, _descendant = _merge_train(tmp_path)
    _fake_render_api(monkeypatch, exact=[], branch=[])
    assert GUARD._render_status(repo, "acme", "widgets", merge, _MERGED_AT) == (
        "pending",
        "The required render workflow has not started yet.",
    )


def _session_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A repo with committed session work on a feature branch, plus its guard state."""
    repo = _repo(tmp_path)
    start_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-b", "claude/feature")
    _commit(repo, "work.txt", "session work\n", "feat: session work")
    state_path = tmp_path / "state.json"
    GUARD._save(
        state_path,
        {
            "root": str(repo),
            "start_head": start_head,
            "baseline": GUARD._fingerprint(repo),
            "last_blocker": "",
            "blocker_count": 0,
        },
    )
    return repo, state_path


def _stop_verdict(monkeypatch, capsys, repo, state_path, *, merged_pr, ci=(True, "")):
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: merged_pr)
    monkeypatch.setattr(GUARD, "_check_ci", lambda *_a: ci)
    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})
    out = capsys.readouterr().out.strip()
    if not out:
        return None
    # Reason reads "SHIP LOOP <code>: <detail>" — the code sits before the colon.
    return json.loads(out)["reason"].split(":", 1)[0].split()[-1]


_MERGED_PR = {"merged_at": "2026-07-25T22:18:56Z", "head": {"sha": "a" * 40}, "merge_commit_sha": "b" * 40}


def test_a_merged_branch_deleted_on_merge_is_not_reported_as_unpushed(
    monkeypatch, tmp_path, capsys
):
    """The completed end state must not read as the state before any push.

    GitHub auto-deletes the head branch on merge, which drops `@{upstream}`. The
    guard used to block `unpushed` right there, before ever looking up the merged
    pull request — an unsatisfiable verdict on finished work, since the branch is
    merged and recreating it would be wrong.
    """
    repo, state_path = _session_repo(tmp_path)
    assert "fatal" in subprocess.run(
        ("git", "rev-parse", "--abbrev-ref", "@{upstream}"),
        cwd=repo, text=True, capture_output=True,
    ).stderr, "precondition: this repo has no upstream"

    # CI is failed purely to stop the chain at a code that proves we got past the
    # upstream gate; ci_failed lives strictly after it.
    verdict = _stop_verdict(
        monkeypatch, capsys, repo, state_path,
        merged_pr=_MERGED_PR, ci=(False, "Failing CI: build (failure)"),
    )
    assert verdict == "ci_failed", f"expected to reach the CI gate, got {verdict}"


def test_no_upstream_and_no_merged_pr_is_still_unpushed(monkeypatch, tmp_path, capsys):
    """The deferral must not lose the real unpushed case."""
    repo, state_path = _session_repo(tmp_path)
    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=None)
    assert verdict == "unpushed"


def test_pushed_but_unmerged_still_blocks_as_unmerged(monkeypatch, tmp_path, capsys):
    repo, state_path = _session_repo(tmp_path)
    bare = tmp_path / "origin.git"
    subprocess.run(("git", "init", "--bare", str(bare)), check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "claude/feature")
    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=None)
    assert verdict == "unmerged"


def test_unpushed_commits_still_block_when_an_upstream_exists(monkeypatch, tmp_path, capsys):
    """The ahead-count check must keep firing; only its guard clause moved."""
    repo, state_path = _session_repo(tmp_path)
    bare = tmp_path / "origin.git"
    subprocess.run(("git", "init", "--bare", str(bare)), check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "claude/feature")
    _commit(repo, "more.txt", "later\n", "feat: not pushed")
    GUARD._save(
        state_path,
        {**json.loads(state_path.read_text(encoding="utf-8")), "baseline": GUARD._fingerprint(repo)},
    )
    verdict = _stop_verdict(monkeypatch, capsys, repo, state_path, merged_pr=_MERGED_PR)
    assert verdict == "unpushed"


def test_settings_wire_session_start_and_stop():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hooks = settings["hooks"]
    assert "SessionStart" in hooks
    assert "Stop" in hooks
    commands = json.dumps(hooks)
    assert "ship_loop_guard.py" in commands


def test_ui_contract_separates_scores_from_axis_labels():
    source = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    assert "container: risk-dialog / inline-size" in source
    assert 'class="rkc-mood-score"' in source
    assert 'class="rkc-mood-axis rsx-axis-labels"' in source
    assert "rkc-mood-flag" not in source
    assert "@container risk-dialog (max-width:520px)" in source
