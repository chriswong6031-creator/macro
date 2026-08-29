"""Regression tests for the narrow HOLD-FOR-SOL Stop-hook state adapter."""

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
    """The already-looping #6207 state becomes PARKED without a rename."""
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


def test_lawful_sol_authority_branch_parks_before_first_unsafe_branch(monkeypatch, tmp_path):
    """A green Sol hold must never need one false unsafe_branch message first."""
    branch = "sol/chairman-tushare-compliance-override-2026-08-21"
    _stub_clean_pushed_git(monkeypatch, branch=branch)
    guard, calls = _fake_guard(tmp_path, state={"last_blocker": ""})

    probe = WRAPPER._hold_probe(guard, {"hook_event_name": "Stop"})

    assert probe is not None
    assert probe["candidate_kind"] == "sol_authority"
    assert probe["source_blocker"] == ""
    assert probe["status"] == "parked"
    assert probe["branch"] == branch
    assert calls == {"open_pull": 1, "checks": 1}


def test_unsafe_branch_hold_exception_is_sol_namespace_only(monkeypatch, tmp_path):
    """The HOLD adapter must not undo the codex/* branch-law incident repair."""
    _stub_clean_pushed_git(monkeypatch, branch="codex/forbidden-delivery")
    guard, calls = _fake_guard(tmp_path, state={"last_blocker": "unsafe_branch"})

    assert WRAPPER._hold_probe(guard, {"hook_event_name": "Stop"}) is None
    assert calls == {"open_pull": 0, "checks": 0}


def test_red_or_pending_claude_hold_does_not_park(monkeypatch, tmp_path):
    """Ordinary claude/* behavior stays delegated until the hold is fully green."""
    _stub_clean_pushed_git(monkeypatch)
    red_guard, _ = _fake_guard(tmp_path, split=(["ci-pack-1 (failure)"], [], ["fences"]))
    assert WRAPPER._parked_hold(red_guard, {"hook_event_name": "Stop"}) is None

    pending_guard, _ = _fake_guard(tmp_path, split=([], ["ci-gate"], ["fences"]))
    assert WRAPPER._parked_hold(pending_guard, {"hook_event_name": "Stop"}) is None


def test_pending_sol_hold_waits_before_first_unsafe_branch_remediation(monkeypatch, tmp_path):
    """The #6207 pre-green state must wait before any destructive branch advice."""
    branch = "sol/chairman-tushare-compliance-override-2026-08-21"
    _stub_clean_pushed_git(monkeypatch, branch=branch)
    guard, calls = _fake_guard(
        tmp_path,
        state={"last_blocker": ""},
        split=([], ["ci-pack-4", "ci-gate"], ["fences"]),
    )

    probe = WRAPPER._hold_probe(guard, {"hook_event_name": "Stop"})
    assert probe is not None and probe["status"] == "pending"
    assert probe["candidate_kind"] == "sol_authority"
    block = WRAPPER._hold_block(probe)
    assert block is not None and block["decision"] == "block"
    reason = block["reason"].lower()
    assert "hold-for-sol waiting" in reason
    assert "do not rename" in reason
    assert "wait for the existing check watcher only" in reason
    assert "unsafe_branch" not in reason
    assert calls == {"open_pull": 1, "checks": 1}


def test_red_sol_hold_repairs_check_without_branch_remediation(monkeypatch, tmp_path):
    """A real red remains a block, but the red—not the Sol branch—is the action."""
    branch = "sol/chairman-tushare-compliance-override-2026-08-21"
    _stub_clean_pushed_git(monkeypatch, branch=branch)
    guard, _ = _fake_guard(
        tmp_path,
        state={"last_blocker": "unsafe_branch"},
        split=(["ci-pack-1 (failure)"], [], ["fences"]),
    )

    probe = WRAPPER._hold_probe(guard, {"hook_event_name": "Stop"})
    assert probe is not None and probe["status"] == "red"
    block = WRAPPER._hold_block(probe)
    assert block is not None and block["decision"] == "block"
    reason = block["reason"].lower()
    assert "hold-for-sol checks red" in reason
    assert "repair the failing check" in reason
    assert "do not rename" in reason
    assert "unsafe_branch" not in reason


def test_pending_ordinary_claude_hold_waits_instead_of_demanding_a_forbidden_merge(monkeypatch, tmp_path):
    """The PR #6608 incident: a lawful claude/* hold got merge advice for 121 blocks.

    Before this repair `_hold_block` returned None for every non-`sol/*` branch, so an
    ordinary held PR fell through to the canonical guard's `unmerged` message telling
    the session to squash-merge and deploy — an action DEC:SOL-HOLD-IS-A-MERGE-BARRIER
    forbids for that exact PR. Pin the wait message, and pin that it is still a block.
    """
    _stub_clean_pushed_git(monkeypatch)
    guard, calls = _fake_guard(
        tmp_path,
        state={"last_blocker": "unmerged"},
        split=([], ["trusted-ci / trusted-executor-pack-10"], ["ci-authority", "fences"]),
    )

    probe = WRAPPER._hold_probe(guard, {"hook_event_name": "Stop"})
    assert probe is not None and probe["status"] == "pending"
    assert probe["candidate_kind"] == "ordinary_unmerged"

    block = WRAPPER._hold_block(probe)
    assert block is not None
    # Still a block: this repair corrects the advice, never the permission.
    assert block["decision"] == "block"
    reason = block["reason"].lower()
    assert "hold-for-sol waiting" in reason
    assert "trusted-executor-pack-10" in reason
    assert "wait for the existing check watcher only" in reason
    # The exact instructions the old fall-through wrongly produced must be absent.
    assert "squash-merge" not in reason
    assert "render/deploy" not in reason
    # And the two failure modes the incident actually produced.
    assert "do not re-poll" in reason
    assert "ship loop blocked" in reason
    assert calls == {"open_pull": 1, "checks": 1}


def test_red_ordinary_claude_hold_repairs_the_check_and_never_merges(monkeypatch, tmp_path):
    """A red on a held claude/* PR points at the check, not at merging or renaming."""
    _stub_clean_pushed_git(monkeypatch)
    guard, _ = _fake_guard(
        tmp_path,
        state={"last_blocker": "unmerged"},
        split=(["ci-pack-3 (failure)"], [], ["fences"]),
    )

    probe = WRAPPER._hold_probe(guard, {"hook_event_name": "Stop"})
    assert probe is not None and probe["status"] == "red"
    assert probe["candidate_kind"] == "ordinary_unmerged"

    block = WRAPPER._hold_block(probe)
    assert block is not None and block["decision"] == "block"
    reason = block["reason"].lower()
    assert "hold-for-sol checks red" in reason
    assert "ci-pack-3" in reason
    assert "must not merge" in reason
    assert "squash-merge" not in reason


def test_hold_block_still_refuses_branches_outside_the_two_sanctioned_namespaces(monkeypatch, tmp_path):
    """The codex/* branch-law repair must survive this widening."""
    # A probe shape that would otherwise qualify, but on a forbidden namespace.
    for kind, branch in (("ordinary_unmerged", "codex/forbidden"), ("sol_authority", "claude/not-sol")):
        assert (
            WRAPPER._hold_block(
                {
                    "candidate_kind": kind,
                    "branch": branch,
                    "number": 1,
                    "head": HEAD,
                    "status": "pending",
                    "pending": ["ci-gate"],
                    "red": [],
                }
            )
            is None
        )


def test_green_ordinary_hold_still_parks_and_pending_still_never_parks(monkeypatch, tmp_path):
    """Guard the permission boundary this repair must not move."""
    _stub_clean_pushed_git(monkeypatch)

    green, _ = _fake_guard(tmp_path, state={"last_blocker": "unmerged"})
    assert WRAPPER._parked_hold(green, {"hook_event_name": "Stop"}) is not None

    pending, _ = _fake_guard(
        tmp_path, state={"last_blocker": "unmerged"}, split=([], ["ci-gate"], ["fences"])
    )
    assert WRAPPER._parked_hold(pending, {"hook_event_name": "Stop"}) is None

    red, _ = _fake_guard(
        tmp_path, state={"last_blocker": "unmerged"}, split=(["ci-gate (failure)"], [], ["fences"])
    )
    assert WRAPPER._parked_hold(red, {"hook_event_name": "Stop"}) is None


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


def test_hold_probe_spends_no_github_quota_outside_candidate_branches(monkeypatch, tmp_path):
    """Normal blockers pay one local branch read but no GitHub hold probes."""
    guard, calls = _fake_guard(tmp_path, state={"last_blocker": "render_pending"})

    def branch_only(_root, *args, **_kwargs):
        if args == ("branch", "--show-current"):
            return "claude/ordinary-feature"
        pytest.fail(f"non-candidate blocker must not inspect further git state: {args}")

    monkeypatch.setattr(WRAPPER, "_git", branch_only)
    assert WRAPPER._hold_probe(guard, {"hook_event_name": "Stop"}) is None
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
