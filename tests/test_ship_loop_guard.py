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


_CI_RUNS_ENDPOINT = "actions/workflows/ci.yml/runs"
_CI_HEAD_SHA = "a" * 40
_CI_MERGE_SHA = "b" * 40
_CI_HEAD_BRANCH = "claude/wizardly-leavitt"
_CI_MERGED_AT = "2026-07-26T13:10:00Z"
# The observed 2026-07-26 12:50-13:03Z window: concurrent sibling pull requests.
_SIB_A = ("c" * 40, "claude/vector-dsr")
_SIB_B = ("d" * 40, "claude/w2-support")
_SIB_C = ("e" * 40, "claude/gracious-moser")
_PRE_MERGE = "2026-07-26T13:03:00Z"
_ALSO_PRE_MERGE = "2026-07-26T12:51:00Z"
_OLDEST_PRE_MERGE = "2026-07-26T12:50:00Z"
_POST_MERGE = "2026-07-26T13:20:00Z"
# Check-suite ids pair a sibling's workflow run with the check runs it published.
# The A value is the real suite observed on the 2026-07-26 replay.
_SUITE_A = 81_847_430_333
_SUITE_B = 81_847_430_444
_SUITE_C = 81_847_430_555


def _check_run(
    name: str,
    conclusion,
    started_at: str = _PRE_MERGE,
    status: str = "completed",
    suite=None,
):
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "started_at": started_at,
        "check_suite": {"id": suite},
    }


def _head_page(*runs, total_count=None) -> dict:
    """One page of the merged head's check-run listing."""
    return {
        "total_count": len(runs) if total_count is None else total_count,
        "check_runs": list(runs),
    }


def _pr_ci_run(
    run_id: int, sibling: tuple[str, str], started: str, conclusion="failure", suite=None
) -> dict:
    sha, branch = sibling
    return {
        "id": run_id,
        "head_sha": sha,
        "head_branch": branch,
        "event": "pull_request",
        "status": "completed",
        "conclusion": conclusion,
        "run_started_at": started,
        "created_at": started,
        "check_suite_id": suite,
    }


def _main_ci_run(run_id: int, head_sha: str, conclusion="success", status="completed") -> dict:
    return {
        "id": run_id,
        "head_sha": head_sha,
        "head_branch": "main",
        "event": "workflow_dispatch",
        "status": status,
        "conclusion": conclusion,
        "run_started_at": "2026-07-26T13:40:00Z",
        "created_at": "2026-07-26T13:40:00Z",
    }


def _fake_ci_api(monkeypatch, *, head_pages, main_runs=(), pr_runs=(), sibling_runs=None) -> list:
    """Serve every `_check_ci` endpoint by URL and record what was fetched.

    Both commit listings share a path shape, so the head's own listing is
    identified by the `page=` parameter only it carries. An unrouted URL asserts
    rather than returning a plausible empty payload — a silently-served endpoint
    would make the cheapness claims below unfalsifiable.
    """
    urls: list = []
    siblings = dict(sibling_runs or {})

    def fake_get_json(url: str):
        urls.append(url)
        parts = urllib.parse.urlsplit(url)
        params = urllib.parse.parse_qs(parts.query)
        if "/check-runs" in parts.path:
            if "page" in params:
                return head_pages[int(params["page"][0])]
            sha = parts.path.split("/commits/", 1)[1].split("/")[0]
            return {"check_runs": list(siblings.get(sha, ()))}
        assert _CI_RUNS_ENDPOINT in parts.path, f"unexpected endpoint: {url}"
        if params.get("branch") == ["main"]:
            return {"workflow_runs": list(main_runs)}
        assert params.get("event") == ["pull_request"], f"unrouted ci.yml listing: {url}"
        return {"workflow_runs": list(pr_runs)}

    monkeypatch.setattr(GUARD, "_get_json", fake_get_json)
    return urls


def _ci_verdict(
    repo: Path,
    *,
    head_sha: str = _CI_HEAD_SHA,
    merge_sha: str = _CI_MERGE_SHA,
    merged_at: str = _CI_MERGED_AT,
    head_branch: str = _CI_HEAD_BRANCH,
):
    return GUARD._check_ci(repo, "acme", "widgets", head_sha, merge_sha, merged_at, head_branch)


def _param(url: str, key: str):
    """One query parameter, parsed. Substring matching would read `page` out of `per_page`."""
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get(key, [None])[0]


def _probe_urls(urls: list) -> list:
    """The per-sibling-head check-run probes: commit listings that are not the head's."""
    return [url for url in urls if "/check-runs" in url and _param(url, "page") is None]


def test_check_ci_still_blocks_on_a_red_check(monkeypatch, tmp_path):
    """The authentication work must not soften the gate it exists to evaluate."""
    repo = _repo(tmp_path)
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci", "failure"), _check_run("lint", "success"))},
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False
    assert reason.startswith("Failing"), "_stop keys the ci_failed code off this prefix"
    assert "ci (failure)" in reason


def test_check_ci_passes_only_when_every_real_check_is_green(monkeypatch, tmp_path):
    repo = _repo(tmp_path)
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(
                _check_run("ci", "success"),
                _check_run("Workers Builds: macro", "failure"),
            )
        },
    )
    assert _ci_verdict(repo) == (True, "")
    assert len(urls) == 1, "a green head is judged without gathering any evidence"

    urls = _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci", None, status="in_progress"))},
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("CI still running")
    assert len(urls) == 1

    urls = _fake_ci_api(monkeypatch, head_pages={1: _head_page()})
    assert _ci_verdict(repo)[0] is False
    assert len(urls) == 1


def test_check_ci_green_path_fetches_only_the_head_listing(monkeypatch, tmp_path):
    """The common case must stay a single API call — evidence is only gathered for a red."""
    repo = _repo(tmp_path)
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(
                _check_run("ci-pack-1", "success"),
                _check_run("nav-gap", "success"),
                _check_run("legacy-member", "skipped"),
            )
        },
    )
    # The lazy origin/main refresh lives inside the evidence phase, so a green head
    # must not spawn git either — the gate stays as cheap as it was.
    monkeypatch.setattr(
        GUARD, "_run", lambda *args, **_kwargs: pytest.fail(f"green path shelled out: {args[1:]}")
    )
    assert _ci_verdict(repo) == (True, "")
    assert len(urls) == 1 and "/check-runs" in urls[0] and _param(urls[0], "page") == "1"


def test_check_ci_paginates_past_the_first_hundred_check_runs(monkeypatch, tmp_path):
    """THE fail-open regression: one `per_page=100` call hid the tail of a 101-run head.

    PR #3629's merged head carries 101 check runs. A red sitting at position 101
    was never fetched, so the gate passed work it had not looked at — the one
    direction this guard may never fail.
    """
    repo = _repo(tmp_path)
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={
            1: {
                "total_count": 101,
                "check_runs": [_check_run(f"pure-{index}", "success") for index in range(100)],
            },
            2: {"total_count": 101, "check_runs": [_check_run("ci-pack-1", "failure")]},
        },
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")
    assert "ci-pack-1 (failure)" in reason
    pages = [_param(url, "page") for url in urls if "/check-runs" in url]
    assert pages == ["1", "2"], "both pages, each exactly once"


def test_a_base_side_red_confirmed_on_two_independent_heads_is_excluded_and_named(
    monkeypatch, tmp_path
):
    """THE defect. A red the PR inherited from the base can never clear itself.

    2026-07-26: the chronicle gate-1 staleness window (heal owned by the still-open
    PR #3634) pinned merged PR #3629's `ci-pack-1`. `gh run rerun` replays the
    frozen `refs/pull/N/merge` tree, and a follow-up PR is impossible once the fix
    is on main, so the session was pushed into `SHIP LOOP BLOCKED:` over work that
    was green. Two independent concurrent heads failing the SAME name before the
    merge is the evidence that the cause was never ours — and the pass must name
    the checks it ignored and the heads it read.
    """
    repo = _repo(tmp_path)
    sib_a_sha, sib_a_branch = _SIB_A
    sib_b_sha, sib_b_branch = _SIB_B
    sib_c_sha, sib_c_branch = _SIB_C
    # Our own red started at _PRE_MERGE, so proximity ranks A, then B, then C.
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(
                _check_run("ci-pack-1", "failure", _PRE_MERGE),
                _check_run("nav-gap", "success"),
            )
        },
        pr_runs=(
            _pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),
            _pr_ci_run(30_200_000_302, _SIB_B, _ALSO_PRE_MERGE, suite=_SUITE_B),
            _pr_ci_run(30_200_000_303, _SIB_C, _OLDEST_PRE_MERGE, suite=_SUITE_C),
        ),
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "failure", _PRE_MERGE, suite=_SUITE_A),),
            sib_b_sha: (_check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE, suite=_SUITE_B),),
            sib_c_sha: (_check_run("ci-pack-1", "failure", _OLDEST_PRE_MERGE, suite=_SUITE_C),),
        },
    )
    ok, note = _ci_verdict(repo)
    assert ok is True
    assert "Ignored base-side CI" in note and "ci-pack-1" in note
    assert sib_a_sha[:7] in note and sib_b_sha[:7] in note
    assert sib_a_branch in note and sib_b_branch in note
    assert not note.startswith("Failing"), "_stop must not read a pass note as a block"
    assert not note.startswith("CI still")
    # The bar is two, so the third (furthest) candidate is never probed.
    assert len(_probe_urls(urls)) == 2 and sib_c_branch not in note


def test_probes_run_in_proximity_order_to_our_own_red(monkeypatch, tmp_path):
    """THE live-replay failure: newest-first missed a true base-side red entirely.

    2026-07-26, merged_at 13:24:17Z, our `ci-pack-1` red started 12:06:25Z. A
    13:14-13:22Z burst of other sessions' pushes filled the newest candidate slots
    and every one of them had `ci-pack-1` GREEN — their runs failed on other checks
    — so the guard returned a plain "Failing CI: ci-pack-1" while six of seven heads
    in the 11:59-12:17Z band around our own red carried the same red. The real
    confirmations sat at listing positions ~9 and ~12, out of reach of any modest
    cap. This class of defect is a temporal STRIPE in the base vintage, so the
    probative siblings are the ones that ran nearest OUR failing check, and
    proximity ordering is also immune to a newer burst crowding the listing.
    """
    repo = _repo(tmp_path)
    merged_at = "2026-07-26T13:24:17Z"
    # Nine newer candidates: more than the probe cap, exactly as in the field.
    burst = tuple(
        (
            str(index) * 40,
            f"claude/burst-{index}",
            f"2026-07-26T13:{22 - index}:00Z",
            810 + index,
        )
        for index in range(1, 10)
    )
    near = (
        ("f" * 40, "claude/outbox", "2026-07-26T12:07:08Z", 826),
        ("0" * 40, "claude/cool-allen", "2026-07-26T12:04:51Z", 827),
    )
    sibling_runs = {
        sha: (_check_run("ci-pack-1", "success", started, suite=suite),)
        for sha, _branch, started, suite in burst
    }
    sibling_runs.update(
        {
            sha: (_check_run("ci-pack-1", "failure", started, suite=suite),)
            for sha, _branch, started, suite in near
        }
    )
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure", "2026-07-26T12:06:25Z"))},
        pr_runs=tuple(
            _pr_ci_run(900 + index, (sha, branch), started, suite=suite)
            for index, (sha, branch, started, suite) in enumerate(burst + near)
        ),
        sibling_runs=sibling_runs,
    )
    ok, note = _ci_verdict(repo, merged_at=merged_at)
    assert ok is True and "Ignored base-side CI" in note
    probes = _probe_urls(urls)
    assert len(probes) == 2, "the two nearest heads meet the bar; the burst is never probed"
    assert all(any(sha in url for sha, *_rest in near) for url in probes)
    assert all(branch in note for _sha, branch, *_rest in near)


def test_a_branchs_older_red_head_survives_its_newer_green_head(monkeypatch, tmp_path):
    """Per-branch keep-newest discarded valid evidence on the live replay.

    w2-support-page's newer 13:22 head had dodged the stripe (`ci-pack-1` green),
    and per-branch dedupe let that newer head silently delete the branch's own
    12:51 red. An older head's red is still proof the base was sick without our
    content, so candidates are keyed by HEAD SHA and both heads stay in play.
    """
    repo = _repo(tmp_path)
    dodging = ("8" * 40, "claude/w2-support-page")
    striped = ("9" * 40, "claude/w2-support-page")
    other = ("7" * 40, "claude/w1-china")
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure", "2026-07-26T12:55:00Z"))},
        pr_runs=(
            _pr_ci_run(931, dodging, "2026-07-26T13:08:00Z", suite=931),
            _pr_ci_run(932, striped, _ALSO_PRE_MERGE, suite=932),
            _pr_ci_run(933, other, "2026-07-26T12:57:00Z", suite=933),
        ),
        sibling_runs={
            dodging[0]: (_check_run("ci-pack-1", "success", "2026-07-26T13:08:00Z", suite=931),),
            striped[0]: (_check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE, suite=932),),
            other[0]: (_check_run("ci-pack-1", "failure", "2026-07-26T12:57:00Z", suite=933),),
        },
    )
    ok, note = _ci_verdict(repo)
    assert ok is True and "Ignored base-side CI" in note
    assert striped[0][:7] in note and other[0][:7] in note
    assert dodging[0][:7] not in note, "the green head is not the evidence"


def test_two_heads_of_one_branch_confirm_only_once(monkeypatch, tmp_path):
    """Sha-dedupe widens the candidate set; the BAR still counts distinct BRANCHES.

    Keeping every head is what stops a newer dodging head from erasing an older
    head's red — but one branch is one independent observation however many of its
    heads carry the stripe.
    """
    repo = _repo(tmp_path)
    solo_new, solo_old = ("8" * 40, "claude/solo"), ("9" * 40, "claude/solo")
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure", _PRE_MERGE))},
        pr_runs=(
            _pr_ci_run(941, solo_new, "2026-07-26T13:02:00Z", suite=941),
            _pr_ci_run(942, solo_old, _ALSO_PRE_MERGE, suite=942),
        ),
        sibling_runs={
            solo_new[0]: (_check_run("ci-pack-1", "failure", "2026-07-26T13:02:00Z", suite=941),),
            solo_old[0]: (_check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE, suite=942),),
        },
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")


def test_a_lone_sibling_confirmation_stays_ci_failed(monkeypatch, tmp_path):
    """One sibling sharing a pack name is coincidence, not a shared cause.

    `ci-pack-1` fronts many jobs and member granularity does not exist (pack
    members are `if: false` definitions that publish `skipped`), so a single
    same-named red proves nothing. Two distinct branches is the bar.
    """
    repo = _repo(tmp_path)
    sib_a_sha, _ = _SIB_A
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=(_pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),),
        sibling_runs={sib_a_sha: (_check_run("ci-pack-1", "failure", _PRE_MERGE, suite=_SUITE_A),)},
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")
    assert "ci-pack-1 (failure)" in reason


def test_sibling_reds_after_the_merge_cannot_classify(monkeypatch, tmp_path):
    """Evidence has to come from a PRE-MERGE run — but the CHECK's clock proves nothing.

    An open pull request's merge ref recomputes against the moving base, so a
    sibling run created after our merge landed may have OUR content as its cause,
    and its red is not evidence. What does NOT follow is judging the second hop by
    time: `github.sha` is frozen at event time, so a check run's `started_at`
    measures queue latency. Under runner contention a pre-merge run's `ci-pack-1`
    job started at 13:25:04, after a 13:24:17 merge, while still testing the
    pre-merge tree. The check suite is the real linkage — a rerun replaces check
    runs inside the same suite, a fresh post-merge event mints a new one.
    """
    repo = _repo(tmp_path)
    sib_a_sha, _ = _SIB_A
    sib_b_sha, _ = _SIB_B

    # Hop 1: the sibling RUNS are post-merge, so nothing about them is evidence.
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=(
            _pr_ci_run(30_200_000_301, _SIB_A, _POST_MERGE, suite=_SUITE_A),
            _pr_ci_run(30_200_000_302, _SIB_B, _POST_MERGE, suite=_SUITE_B),
        ),
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "failure", _PRE_MERGE, suite=_SUITE_A),),
            sib_b_sha: (_check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE, suite=_SUITE_B),),
        },
    )
    assert _ci_verdict(repo)[0] is False

    in_window_runs = (
        _pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),
        _pr_ci_run(30_200_000_302, _SIB_B, _ALSO_PRE_MERGE, suite=_SUITE_B),
    )

    # Hop 2, negative: the reds belong to a DIFFERENT suite on the same heads — a
    # fresh post-merge pull_request event, which our content could have caused.
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=in_window_runs,
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "failure", _POST_MERGE, suite=_SUITE_A + 1),),
            sib_b_sha: (_check_run("ci-pack-1", "failure", _POST_MERGE, suite=_SUITE_B + 1),),
        },
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")

    # Hop 2, fail-closed: no suite id at all on the check runs.
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=in_window_runs,
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "failure", _PRE_MERGE),),
            sib_b_sha: (_check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE),),
        },
    )
    assert _ci_verdict(repo)[0] is False

    # Hop 2, positive twin: the SAME late-started reds confirm once their suite
    # matches the pre-merge run — the timestamp was never the evidence.
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=in_window_runs,
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "failure", _POST_MERGE, suite=_SUITE_A),),
            sib_b_sha: (_check_run("ci-pack-1", "failure", _POST_MERGE, suite=_SUITE_B),),
        },
    )
    ok, note = _ci_verdict(repo)
    assert ok is True and "Ignored base-side CI" in note


def test_own_branch_runs_are_not_independent_evidence(monkeypatch, tmp_path):
    """Independence is structural: a distinct branch, on a sha that is not ours.

    Our own pull request's earlier attempts carry the same red for the same
    reason, so counting them would let a PR confirm its own innocence.
    """
    repo = _repo(tmp_path)
    ours_again = ("f" * 40, _CI_HEAD_BRANCH)
    same_sha_other_branch = (_CI_HEAD_SHA, "claude/mirror-of-ours")
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=(
            _pr_ci_run(30_200_000_301, ours_again, _PRE_MERGE),
            _pr_ci_run(30_200_000_302, same_sha_other_branch, _ALSO_PRE_MERGE),
        ),
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")
    assert _probe_urls(urls) == [], "neither run should have been worth probing"


def test_sibling_run_failures_with_a_green_pack_are_not_evidence(monkeypatch, tmp_path):
    """The observed window's actual shape: most sibling run-failures are the sibling's own bug.

    2026-07-26 12:50-13:03Z: gracious-moser, brain-symmetric and brain-consistency
    all concluded `failure` at the RUN level while their `ci-pack-1` check was
    GREEN. Only vector-dsr 13:03 and w2-support 12:51 carried a red `ci-pack-1`.
    So a run conclusion is never evidence — only a per-head probe of the same NAME.
    """
    repo = _repo(tmp_path)
    sib_a_sha, _ = _SIB_A
    sib_b_sha, _ = _SIB_B
    sib_c_sha, _ = _SIB_C
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        pr_runs=(
            _pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),
            _pr_ci_run(30_200_000_302, _SIB_B, _ALSO_PRE_MERGE, suite=_SUITE_B),
            _pr_ci_run(30_200_000_303, _SIB_C, _OLDEST_PRE_MERGE, suite=_SUITE_C),
        ),
        sibling_runs={
            sib_a_sha: (_check_run("ci-pack-1", "success", _PRE_MERGE, suite=_SUITE_A),),
            sib_b_sha: (_check_run("ci-pack-1", "success", _ALSO_PRE_MERGE, suite=_SUITE_B),),
            sib_c_sha: (_check_run("ci-pack-1", "success", _OLDEST_PRE_MERGE, suite=_SUITE_C),),
        },
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")
    assert len(_probe_urls(urls)) == 3, "each candidate head is probed by name, once"


def test_a_dispatched_green_ci_run_on_a_main_descendant_clears_every_red(monkeypatch, tmp_path):
    """The operator's unblock lever, and the only evidence strong enough for any conclusion.

    ci.yml triggers on `pull_request` + `workflow_dispatch` only, so main commits
    carry no ci.yml runs at all — dispatching one on main once the base-side cause
    is healed is how a pinned session clears. A descendant's tree contains the
    merge, so a full green run there proves the merged content passes and every bad
    conclusion goes with it, `cancelled` included.
    """
    repo, _parent, merge, descendant = _merge_train(tmp_path)
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(
                _check_run("ci-pack-1", "failure"),
                _check_run("tier-gate", "cancelled"),
            )
        },
        main_runs=(_main_ci_run(30_200_000_401, descendant),),
    )
    ok, note = _ci_verdict(repo, merge_sha=merge)
    assert ok is True
    assert "30200000401" in note and descendant[:12] in note
    assert "tier-gate (cancelled)" in note, "content-green clears conclusions E2 never could"
    assert not note.startswith("Failing")
    assert not any(_param(url, "event") == "pull_request" for url in urls), "E1 short-circuits E2"


def test_a_green_main_run_on_a_non_descendant_cannot_clear(monkeypatch, tmp_path):
    """Real git decides ancestry: a green run on the merge's PARENT rendered a tree without it."""
    repo, parent, merge, _descendant = _merge_train(tmp_path)
    _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("ci-pack-1", "failure"))},
        main_runs=(_main_ci_run(30_200_000_401, parent),),
    )
    ok, reason = _ci_verdict(repo, merge_sha=merge)
    assert ok is False and reason.startswith("Failing")
    assert "ci-pack-1 (failure)" in reason


def test_partial_exclusion_still_blocks_and_names_both_sides(monkeypatch, tmp_path):
    """Exclusion is per check name. One inherited red does not launder our own."""
    repo = _repo(tmp_path)
    sib_a_sha, _ = _SIB_A
    sib_b_sha, _ = _SIB_B
    _fake_ci_api(
        monkeypatch,
        head_pages={
            1: _head_page(_check_run("ci-pack-1", "failure"), _check_run("own-check", "failure"))
        },
        pr_runs=(
            _pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),
            _pr_ci_run(30_200_000_302, _SIB_B, _ALSO_PRE_MERGE, suite=_SUITE_B),
        ),
        sibling_runs={
            sib_a_sha: (
                _check_run("ci-pack-1", "failure", _PRE_MERGE, suite=_SUITE_A),
                _check_run("own-check", "success", _PRE_MERGE, suite=_SUITE_A),
            ),
            sib_b_sha: (
                _check_run("ci-pack-1", "failure", _ALSO_PRE_MERGE, suite=_SUITE_B),
                _check_run("own-check", "success", _ALSO_PRE_MERGE, suite=_SUITE_B),
            ),
        },
    )
    ok, message = _ci_verdict(repo)
    assert ok is False and message.startswith("Failing CI:")
    assert "own-check (failure)" in message
    assert "Ignored as base-side" in message and "ci-pack-1" in message
    assert "ci-pack-1 (failure). These run against" not in message, (
        "the excluded name must not be listed as a red we own"
    )


def test_non_failure_head_conclusions_are_not_base_side_excludable(monkeypatch, tmp_path):
    """A `cancelled` check on a merged head is genuinely rerunnable, so it stays ours.

    Rerunning replays the frozen merge ref, which is fatal for a base-side FAILURE
    but perfectly capable of greening a cancellation. Only content-green evidence
    clears those, never a sibling argument.
    """
    repo = _repo(tmp_path)
    sib_a_sha, _ = _SIB_A
    sib_b_sha, _ = _SIB_B
    urls = _fake_ci_api(
        monkeypatch,
        head_pages={1: _head_page(_check_run("tier-gate", "cancelled"))},
        pr_runs=(
            _pr_ci_run(30_200_000_301, _SIB_A, _PRE_MERGE, suite=_SUITE_A),
            _pr_ci_run(30_200_000_302, _SIB_B, _ALSO_PRE_MERGE, suite=_SUITE_B),
        ),
        sibling_runs={
            sib_a_sha: (_check_run("tier-gate", "failure", _PRE_MERGE, suite=_SUITE_A),),
            sib_b_sha: (_check_run("tier-gate", "failure", _ALSO_PRE_MERGE, suite=_SUITE_B),),
        },
    )
    ok, reason = _ci_verdict(repo)
    assert ok is False and reason.startswith("Failing")
    assert "tier-gate (cancelled)" in reason
    assert not any(_param(url, "event") == "pull_request" for url in urls), (
        "with nothing eligible, the sibling listing is not even worth fetching"
    )
    assert _probe_urls(urls) == []


def test_evidence_api_errors_fail_closed_to_the_original_red(monkeypatch, tmp_path):
    """A broken evidence phase must keep the red, never reclassify or swallow it."""
    repo = _repo(tmp_path)

    def fake_get_json(url: str):
        if _CI_RUNS_ENDPOINT in url:
            raise RuntimeError("workflow listing exploded")
        return _head_page(_check_run("ci-pack-1", "failure"))

    monkeypatch.setattr(GUARD, "_get_json", fake_get_json)
    ok, message = _ci_verdict(repo)
    assert ok is False and message.startswith("Failing")
    assert "ci-pack-1 (failure)" in message
    assert "evidence unavailable" in message.lower()
    assert "Ignored" not in message


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


def _stub_remote_git(monkeypatch) -> None:
    """Let the two remote-dependent git calls pass in a fixture repo with no origin.

    Only `git fetch` and `merge-base --is-ancestor` are faked; rev-parse, branch,
    rev-list and diff still run for real against the fixture, so the parts of
    `_stop` under test are not stubbed out from under it.
    """
    real_run = GUARD._run

    def router(root, *args, **kwargs):
        if args[:2] == ("git", "fetch") or args[:3] == ("git", "merge-base", "--is-ancestor"):
            return ""
        return real_run(root, *args, **kwargs)

    monkeypatch.setattr(GUARD, "_run", router)


def test_stop_emits_the_exclusion_note_as_a_system_message(monkeypatch, tmp_path, capsys):
    """A pass that rests on excluded reds must be auditable, not silent.

    The CI gate can now clear a red it judged base-side, on named evidence. That
    judgement is exactly what an operator has to be able to challenge afterwards,
    so `_stop` prints it on the way through instead of swallowing it — and still
    lets the session stop.
    """
    repo, state_path = _session_repo(tmp_path)
    note = (
        "Ignored base-side CI: ci-pack-1 (failure) — the same check failed on 2 independent "
        "concurrent PR head(s) (ccccccc@claude/vector-dsr, ddddddd@claude/w2-support) before "
        "this merge."
    )
    monkeypatch.setattr(GUARD, "_github_slug", lambda _root: ("acme", "widgets"))
    monkeypatch.setattr(GUARD, "_latest_merged_pr", lambda *_a: _MERGED_PR)
    monkeypatch.setattr(GUARD, "_check_ci", lambda *_a, **_k: (True, note))
    monkeypatch.setattr(GUARD, "_needs_render", lambda *_a: False)
    monkeypatch.setattr(
        GUARD, "_get_json", lambda _url: {"commit": _git(repo, "rev-parse", "HEAD")}
    )
    _stub_remote_git(monkeypatch)

    GUARD._stop(repo, state_path, {"hook_event_name": "Stop"})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert any(note in str(line.get("systemMessage") or "") for line in lines), lines
    assert not any(line.get("decision") == "block" for line in lines), lines


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
