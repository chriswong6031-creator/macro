"""Regression tests for the tracked Claude completion guard."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


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


# ---------------------------------------------------------------------------
# GitHub credential resolution
#
# 2026-07-25: the guard died on `HTTP Error 403: rate limit exceeded` and reported
# "github_unreachable" on every turn — while PR #3534 was already MERGED on main.
# Claude Code hooks inherit neither GH_TOKEN nor GITHUB_TOKEN, so every request went
# out anonymous against the 60/hr per-host quota, which a busy session burns in
# minutes. The guard now falls back to `gh auth token` (5000/hr), host-gated so the
# credential can only ever reach api.github.com.
# ---------------------------------------------------------------------------


def test_env_token_wins_over_the_gh_cli(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "env-token")
    monkeypatch.setattr(GUARD, "_GH_TOKEN_CACHE", None)
    assert GUARD._token_from_env() == "env-token"

    monkeypatch.delenv("GH_TOKEN")
    monkeypatch.setenv("GITHUB_TOKEN", "other-token")
    assert GUARD._token_from_env() == "other-token"


def test_falls_back_to_gh_auth_token_when_the_env_is_empty(monkeypatch):
    """The whole point: hooks get no token in the environment."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(GUARD, "_GH_TOKEN_CACHE", None)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="gho_fromcli\n", stderr="")

    monkeypatch.setattr(GUARD.subprocess, "run", fake_run)
    assert GUARD._token_from_env() == "gho_fromcli"
    assert calls == [["gh", "auth", "token"]]

    # cached — a second call must not re-exec gh
    assert GUARD._token_from_env() == "gho_fromcli"
    assert len(calls) == 1


def test_a_host_without_gh_degrades_to_anonymous_without_raising(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(GUARD, "_GH_TOKEN_CACHE", None)

    def boom(cmd, **kwargs):
        raise FileNotFoundError("gh not installed")

    monkeypatch.setattr(GUARD.subprocess, "run", boom)
    assert GUARD._token_from_env() == ""
    # and the failed exec is cached, not retried per request
    assert GUARD._GH_TOKEN_CACHE == [""]


def test_gh_auth_failure_degrades_to_anonymous(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(GUARD, "_GH_TOKEN_CACHE", None)
    monkeypatch.setattr(
        GUARD.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not logged in"),
    )
    assert GUARD._token_from_env() == ""


def test_the_token_only_ever_reaches_api_github_com(monkeypatch):
    """Host-gated, not prefix-gated: a caller that follows a link out of a payload
    must not hand the credential to another origin."""
    monkeypatch.setenv("GH_TOKEN", "secret-token")
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout=None):
        seen[request.full_url] = request.headers
        return FakeResponse()

    monkeypatch.setattr(GUARD.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(GUARD.json, "load", lambda _fh: {})

    GUARD._get_json("https://api.github.com/repos/o/r/pulls")
    GUARD._get_json("https://evil.example.com/repos/o/r/pulls")
    GUARD._get_json("https://api.github.com.evil.example.com/x")
    GUARD._get_json("https://raw.githubusercontent.com/o/r/main/x")

    def has_auth(url: str) -> bool:
        return any(k.lower() == "authorization" for k in seen[url])

    assert has_auth("https://api.github.com/repos/o/r/pulls")
    assert not has_auth("https://evil.example.com/repos/o/r/pulls")
    assert not has_auth("https://api.github.com.evil.example.com/x")
    assert not has_auth("https://raw.githubusercontent.com/o/r/main/x")
