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

    _render_status looks for a `push` render run whose head_sha IS the merge sha,
    and render.yml only fires on templates/** + scripts/build_*.py. A merge that
    touched neither can never have such a run, so demanding one is an
    unsatisfiable block rather than a real gap.
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
    """A Stop evaluation makes three API calls; it must not shell out three times."""
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
