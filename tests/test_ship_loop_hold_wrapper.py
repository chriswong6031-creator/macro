"""Regression tests for the narrow HOLD-FOR-SOL Stop-hook terminal state."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = ROOT / "scripts" / "ship_loop_hold_wrapper.py"
SPEC = importlib.util.spec_from_file_location("ship_loop_hold_wrapper", WRAPPER_PATH)
assert SPEC and SPEC.loader
WRAPPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WRAPPER)


HEAD = "a" * 40


def _pull(**overrides):
    # Mirrors PR #6138's real body shape: the protocol fields are inline on one
    # Markdown line, not one field per line.
    pull = {
        "number": 6138,
        "title": "HOLD-FOR-SOL · records: authority closure",
        "body": (
            "## HOLD-FOR-SOL — DO NOT MERGE\n\n"
            "**Authority:** Sol P1-0R authority-closure directive 2026-08-20. "
            "**Release condition:** Sol review approval. Until then this hold binds "
            "every merge path — do not arm merge-on-green; do not merge; do not mark ready."
        ),
        "draft": True,
        "labels": [],
        "auto_merge": None,
        "head": {"sha": HEAD},
        "comments_url": "https://api.github.test/comments",
    }
    pull.update(overrides)
    return pull


def _comments():
    # Mirrors PR #6138's real hold comment shape: Authority and Release condition
    # are both inline in one sentence.
    return [
        {
            "body": (
                "HOLD-FOR-SOL (session claude/biocatalyst-p1-0r-authority-closure): "
                "merge barrier per DEC:SOL-HOLD-IS-A-MERGE-BARRIER. Authority: Sol "
                "P1-0R authority-closure directive 2026-08-20. Release condition: "
                "Sol review approval. Do not arm merge-on-green; do not merge; do not mark ready."
            )
        }
    ]


def test_exact_sol_hold_protocol_is_recognized():
    pull = _pull()
    comments = _comments()
    assert WRAPPER._hold_protocol_is_complete(pull, comments)
    combined = WRAPPER._plain(pull["body"] + "\n" + comments[0]["body"])
    assert "Sol P1-0R" in WRAPPER._field(combined, "Authority")
    assert "Sol review approval" in WRAPPER._field(combined, "Release condition")


@pytest.mark.parametrize(
    "mutation",
    [
        {"draft": False},
        {"labels": [{"name": "merge-on-green"}]},
        {"auto_merge": {"merge_method": "SQUASH"}},
        {"title": "please hold this for later"},
        {"body": "HOLD-FOR-SOL. Do not merge. Authority: session. Release condition: session."},
        {"body": "HOLD-FOR-SOL. Do not merge. Authority: Sol. Release condition: CI green."},
    ],
)
def test_incomplete_or_unsafe_hold_fails_closed(mutation):
    assert not WRAPPER._hold_protocol_is_complete(_pull(**mutation), [])


def test_markdown_protocol_fields_are_not_required_to_be_plain_text():
    """Line-oriented Markdown remains valid alongside #6138's inline field form."""
    pull = _pull(
        body=(
            "# HOLD-FOR-SOL — DO NOT MERGE\n"
            "**Authority:** Sol CEO review directive\n"
            "**Release condition:** Sol approval after review\n"
        )
    )
    assert WRAPPER._hold_protocol_is_complete(pull, [])


def _fake_guard(tmp_path: Path, *, state=None, split=None, pull=None):
    open_pull = pull or _pull()
    split_result = split or ([], [], ["ci-gate", "fences"])
    calls = {"open_pull": 0, "checks": 0}

    def _open_pull(*_args):
        calls["open_pull"] += 1
        return open_pull

    def _head_check_runs(*_args):
        calls["checks"] += 1
        return [object()]

    guard = SimpleNamespace(
        _repo_root=lambda _payload: tmp_path,
        _state_path=lambda _root, _payload: tmp_path / "state.json",
        _load=lambda _path: state if state is not None else {"last_blocker": "unmerged"},
        _github_slug=lambda _root: ("mastermindx-market-intelligence", "macro"),
        _open_pull=_open_pull,
        _get_json=lambda _url: _comments(),
        _head_check_runs=_head_check_runs,
        _split_head_runs=lambda _runs: split_result,
    )
    return guard, calls


def _stub_clean_pushed_git(monkeypatch, branch="claude/biocatalyst-p1-0r-authority-closure"):
    def fake_git(_root, *args, **_kwargs):
        if args == ("branch", "--show-current"):
            return branch
        if args == ("rev-parse", "HEAD"):
            return HEAD
        if args == ("rev-parse", "--abbrev-ref", "@{upstream}"):
            return f"origin/{branch}"
        if args[:2] == ("rev-list", "--count"):
            return "0"
        if args == ("status", "--porcelain=v1", "--untracked-files=all"):
            return ""
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(WRAPPER, "_git", fake_git)


def test_lawful_concluded_green_hold_becomes_parked(monkeypatch, tmp_path):
    _stub_clean_pushed_git(monkeypatch)
    guard, calls = _fake_guard(tmp_path)

    parked = WRAPPER._parked_hold(guard, {"hook_event_name": "Stop"})

    assert parked == {
        "number": 6138,
        "branch": "claude/biocatalyst-p1-0r-authority-closure",
        "head": HEAD,
        "passed": ["ci-gate", "fences"],
    }
    assert calls == {"open_pull": 1, "checks": 1}


def test_lawful_sol_authority_branch_parks_after_unsafe_branch(monkeypatch, tmp_path):
    """PR #6207 class: a ratified Sol hold must not loop forever on branch law."""
    branch = "sol/chairman-tushare-compliance-override-2026-08-21"
    _stub_clean_pushed_git(monkeypatch, branch=branch)
    guard, calls = _fake_guard(tmp_path, state={"last_blocker": "unsafe_branch"})

    parked = WRAPPER._parked_hold(guard, {"hook_event_name": "Stop"})

    assert parked == {
        "number": 6138,
        "branch": branch,
        "head": HEAD,
        "passed": ["ci-gate", "fences"],
    }
    assert calls == {"open_pull": 1, "checks": 1}


def test_unsafe_branch_hold_exception_is_sol_namespace_only(monkeypatch, tmp_path):
    """The PARKED exception must not undo the codex/* branch-law incident repair."""
    _stub_clean_pushed_git(monkeypatch, branch="codex/forbidden-delivery")
    guard, calls = _fake_guard(tmp_path, state={"last_blocker": "unsafe_branch"})

    assert WRAPPER._parked_hold(guard, {"hook_event_name": "Stop"}) is None
    assert calls == {"open_pull": 0, "checks": 0}


def test_red_or_pending_hold_does_not_park(monkeypatch, tmp_path):
    _stub_clean_pushed_git(monkeypatch)
    red_guard, _ = _fake_guard(tmp_path, split=(["ci-pack-1 (failure)"], [], ["fences"]))
    assert WRAPPER._parked_hold(red_guard, {"hook_event_name": "Stop"}) is None

    pending_guard, _ = _fake_guard(tmp_path, split=([], ["ci-gate"], ["fences"]))
    assert WRAPPER._parked_hold(pending_guard, {"hook_event_name": "Stop"}) is None


def test_dirty_or_not_exactly_pushed_hold_does_not_park(monkeypatch, tmp_path):
    guard, _ = _fake_guard(tmp_path)

    def dirty_git(_root, *args, **_kwargs):
        if args == ("branch", "--show-current"):
            return "claude/feature"
        if args == ("rev-parse", "HEAD"):
            return HEAD
        if args == ("rev-parse", "--abbrev-ref", "@{upstream}"):
            return "origin/claude/feature"
        if args[:2] == ("rev-list", "--count"):
            return "0"
        if args == ("status", "--porcelain=v1", "--untracked-files=all"):
            return " M changed.py"
        raise AssertionError(args)

    monkeypatch.setattr(WRAPPER, "_git", dirty_git)
    assert WRAPPER._parked_hold(guard, {"hook_event_name": "Stop"}) is None


def test_hold_probe_spends_no_github_quota_before_terminal_candidate_blocker(monkeypatch, tmp_path):
    guard, calls = _fake_guard(tmp_path, state={"last_blocker": "render_pending"})
    monkeypatch.setattr(
        WRAPPER,
        "_git",
        lambda *_a, **_k: pytest.fail("non-terminal blocker must not even inspect the branch"),
    )

    assert WRAPPER._parked_hold(guard, {"hook_event_name": "Stop"}) is None
    assert calls == {"open_pull": 0, "checks": 0}


def _settings_document() -> dict:
    """Read exact-head settings even when the fast fence omits `.claude/` on disk."""
    path = ROOT / ".claude" / "settings.json"
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        proc = subprocess.run(
            ("git", "show", "HEAD:.claude/settings.json"),
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        text = proc.stdout
    return json.loads(text)


def test_stop_hook_routes_through_wrapper_but_keeps_original_guard_as_delegate():
    settings = _settings_document()
    stop_hooks = [
        hook
        for entry in settings["hooks"]["Stop"]
        for hook in entry["hooks"]
    ]
    assert len(stop_hooks) == 1
    stop = stop_hooks[0]
    assert "scripts/ship_loop_hold_wrapper.py" in stop["command"]
    assert ".claude/hooks/ship_loop_guard.py" in stop["command"]
    # The delegate's pathological git-status budget fits below the 540s wall main
    # currently grants the Stop hook; this adapter must preserve that newer budget.
    assert int(stop["timeout"]) >= 540

    session_hooks = [
        hook
        for entry in settings["hooks"]["SessionStart"]
        for hook in entry["hooks"]
    ]
    assert any("ship_loop_guard.py" in hook.get("command", "") for hook in session_hooks)
