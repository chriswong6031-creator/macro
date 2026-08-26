"""Regression tests for the narrow HOLD-FOR-SOL Stop-hook state adapter."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import threading
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


# ── PARKED narrates once, then the latch keeps wake turns silent (#6379) ─────


def _ledger_guard(tmp_path: Path, *, split=None, pull="default", state_extra=None):
    """A fake guard whose per-session ledger is a REAL file, as in production.

    ``pull=None`` models a closed/merged PR (probe finds nothing); any other
    value overrides the default lawful hold PR.
    """
    state_path = tmp_path / "state.json"
    state = {"last_blocker": "unmerged"}
    state.update(state_extra or {})
    state_path.write_text(json.dumps(state), encoding="utf-8")
    open_pull = _pull() if pull == "default" else pull
    split_result = split or ([], [], ["ci-gate", "fences"])
    calls = {"open_pull": 0, "checks": 0}
    ledger_lock = threading.Lock()

    def _open_pull(*_args):
        calls["open_pull"] += 1
        return open_pull

    def _head_check_runs(*_args):
        calls["checks"] += 1
        return [object()]

    def _load(path):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except OSError:
            return None

    def _save(path, value):
        Path(path).write_text(json.dumps(value), encoding="utf-8")

    def _update_ledger(path, mutate):
        with ledger_lock:
            latest = _load(path)
            if not isinstance(latest, dict):
                return None
            result = mutate(latest)
            _save(path, latest)
            return result

    guard = SimpleNamespace(
        _repo_root=lambda _payload: tmp_path,
        _state_path=lambda _root, _payload: state_path,
        _load=_load,
        _save=_save,
        _update_ledger=_update_ledger,
        _github_slug=lambda _root: ("mastermindx-market-intelligence", "macro"),
        _open_pull=_open_pull,
        _get_json=lambda _url: _comments(),
        _head_check_runs=_head_check_runs,
        _split_head_runs=lambda _runs: split_result,
    )
    return guard, state_path, calls


def test_first_parked_stop_narrates_once_then_the_latch_silences_wakes(monkeypatch, tmp_path):
    """The first lawful PARKED is the one hook-level terminal report.

    Five later Stop observations that re-derive the identical hold return the
    wrapper's deterministic ``silent`` action. This proves suppression at the
    hook contract; the client/model-turn lifecycle remains outside this test's
    authority. Every observation still re-runs the full mechanical probe.
    """
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, calls = _ledger_guard(tmp_path)

    first = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})
    assert first is not None and first["action"] == "emit"
    message = first["value"]["systemMessage"]
    assert message.startswith("SHIP LOOP PARKED")
    assert "ONE terminal report" in message
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["parked_latch"] == f"parked:6138:{HEAD}"

    unchanged = [
        WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})
        for _ in range(5)
    ]
    assert unchanged == [{"action": "silent"}] * 5
    # Quiescence is narration-only: the hold was mechanically revalidated.
    assert calls["open_pull"] == 6 and calls["checks"] == 6


def test_parked_latch_writer_preserves_a_concurrent_watcher_reservation(
    monkeypatch, tmp_path
):
    """The hold probe can spend seconds on GitHub after reading the ledger.
    If PreToolUse reserves a watcher meanwhile, the later PARKED latch write
    must transact against the latest state instead of erasing that watcher.
    """
    guard, state_path, _ = _ledger_guard(tmp_path)
    probe_started = threading.Event()
    watcher_written = threading.Event()
    results = []

    def paused_probe(_guard, _payload):
        probe_started.set()
        assert watcher_written.wait(timeout=10)
        return {
            "number": 6138,
            "branch": "claude/held",
            "head": HEAD,
            "candidate_kind": "ordinary_unmerged",
            "source_blocker": "unmerged",
            "status": "parked",
            "red": [],
            "pending": [],
            "passed": ["ci-gate", "fences"],
        }

    monkeypatch.setattr(WRAPPER, "_hold_probe", paused_probe)

    writer = threading.Thread(
        target=lambda: results.append(
            WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})
        )
    )
    writer.start()
    assert probe_started.wait(timeout=10)
    latest = json.loads(state_path.read_text(encoding="utf-8"))
    latest["ship_watcher"] = {
        "digest": "d" * 12,
        "fragment": "gh run watch 1 --exit-status",
        "head": HEAD,
        "created": 1.0,
    }
    state_path.write_text(json.dumps(latest), encoding="utf-8")
    watcher_written.set()
    writer.join(timeout=10)
    assert not writer.is_alive()
    assert results and results[0]["action"] == "emit"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["parked_latch"] == f"parked:6138:{HEAD}"
    assert state["ship_watcher"]["fragment"] == "gh run watch 1 --exit-status"


def test_nonparked_probe_clears_a_latch_added_while_the_probe_was_in_flight(
    monkeypatch, tmp_path
):
    """The clear decision must be made from the locked latest ledger too.

    A stale pre-probe snapshot with no latch must not cause the wrapper to miss
    a latch written during the GitHub query after the probe positively answers
    that the hold is no longer PARKED. The concurrent watcher stays intact.
    """
    guard, state_path, _ = _ledger_guard(tmp_path)
    probe_started = threading.Event()
    latch_written = threading.Event()
    results = []

    def paused_nonparked_probe(_guard, _payload):
        probe_started.set()
        assert latch_written.wait(timeout=10)
        return None

    monkeypatch.setattr(WRAPPER, "_hold_probe", paused_nonparked_probe)
    writer = threading.Thread(
        target=lambda: results.append(
            WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})
        )
    )
    writer.start()
    assert probe_started.wait(timeout=10)
    latest = json.loads(state_path.read_text(encoding="utf-8"))
    latest["parked_latch"] = f"parked:6138:{HEAD}"
    latest["ship_watcher"] = {
        "digest": "d" * 12,
        "fragment": "gh run watch 1 --exit-status",
        "head": HEAD,
        "created": 1.0,
    }
    state_path.write_text(json.dumps(latest), encoding="utf-8")
    latch_written.set()
    writer.join(timeout=10)
    assert not writer.is_alive()
    assert results == [None]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "parked_latch" not in state
    assert state["ship_watcher"]["fragment"] == "gh run watch 1 --exit-status"


def test_github_outage_never_silences_and_never_clears_the_latch(monkeypatch, tmp_path):
    """An unanswerable GitHub layer DELEGATES (red-team F1/F2): the canonical
    guard files its own escapeable outage block — an outage cannot prove the
    hold is still in force, so it may not silence a Stop. The latch is kept
    (no evidence of change) so a later answerable parked probe is silent."""
    _stub_clean_pushed_git(monkeypatch)

    def broken_open_pull(*_args):
        raise RuntimeError("api.github.com unreachable")

    guard, state_path, _ = _ledger_guard(
        tmp_path, state_extra={"parked_latch": f"parked:6138:{HEAD}"}
    )
    guard._open_pull = broken_open_pull
    assert WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"}) is None
    assert json.loads(state_path.read_text(encoding="utf-8"))["parked_latch"]


def test_outage_blocker_mutation_cannot_make_the_same_parked_hold_narrate_again(
    monkeypatch, tmp_path
):
    """Exercise the whole incident sequence, not only its final snapshot:
    PARKED -> outage delegate -> canonical blocker mutation -> two recovered
    Stops. Transport ambiguity cannot turn one unchanged hold into a fresh
    terminal narration."""
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, calls = _ledger_guard(
        tmp_path,
        state_extra={
            "last_blocker": "unmerged",
            "parked_latch": f"parked:6138:{HEAD}",
        },
    )

    original_open = guard._open_pull
    guard._open_pull = lambda *_args: (_ for _ in ()).throw(
        RuntimeError("api.github.com unreachable")
    )
    assert WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"}) is None
    assert json.loads(state_path.read_text(encoding="utf-8"))["parked_latch"]

    # This is the canonical delegate's real side effect during the outage.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["last_blocker"] = "github_unreachable"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    guard._open_pull = original_open

    first = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})
    second = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})
    assert first == second == {"action": "silent"}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["parked_latch"] == f"parked:6138:{HEAD}"
    assert calls == {"open_pull": 2, "checks": 2}


def test_local_probe_failure_reads_as_not_a_candidate_and_clears_the_latch(
    monkeypatch, tmp_path
):
    """The F1 incident shape: Sol merges the held PR, the branch is pruned, and
    `@{upstream}` stops resolving. That is a LOCAL failure — the probe answers
    None, the stale latch is cleared, and the Stop delegates to the canonical
    guard, whose merged-PR lookup then owns CI/render/live verification."""

    def pruned_git(_root, *args, **_kwargs):
        if args == ("branch", "--show-current"):
            return "claude/biocatalyst-p1-0r-authority-closure"
        if args == ("rev-parse", "HEAD"):
            return HEAD
        if args == ("rev-parse", "--abbrev-ref", "@{upstream}"):
            raise RuntimeError("fatal: no upstream configured (branch pruned after merge)")
        raise AssertionError(args)

    monkeypatch.setattr(WRAPPER, "_git", pruned_git)
    guard, state_path, calls = _ledger_guard(
        tmp_path, state_extra={"parked_latch": f"parked:6138:{HEAD}"}
    )
    assert WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"}) is None
    assert "parked_latch" not in json.loads(state_path.read_text(encoding="utf-8"))
    assert calls == {"open_pull": 0, "checks": 0}


def test_a_released_or_closed_hold_clears_the_latch_and_resumes_ordinary_law(
    monkeypatch, tmp_path
):
    """Sol releasing the hold (un-drafting, retitling, or merging/closing the
    PR) is a genuinely new state: the old PARKED latch must not suppress the
    ordinary completion chain (acceptance: 'Hold release ... resumes')."""
    _stub_clean_pushed_git(monkeypatch)
    for released_pull in (_pull(draft=False), None):
        guard, state_path, _ = _ledger_guard(
            tmp_path,
            pull=released_pull,
            state_extra={"parked_latch": f"parked:6138:{HEAD}"},
        )
        assert WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"}) is None
        assert "parked_latch" not in json.loads(state_path.read_text(encoding="utf-8"))


def test_a_red_check_after_park_clears_the_latch_and_keeps_the_sol_hold_block(
    monkeypatch, tmp_path
):
    branch = "sol/chairman-tushare-compliance-override-2026-08-21"
    _stub_clean_pushed_git(monkeypatch, branch=branch)
    guard, state_path, _ = _ledger_guard(
        tmp_path,
        split=(["ci-pack-1 (failure)"], [], ["fences"]),
        state_extra={"parked_latch": f"parked:6138:{HEAD}"},
    )
    verdict = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})
    assert verdict is not None and verdict["action"] == "emit"
    assert "HOLD-FOR-SOL CHECKS RED" in verdict["value"]["reason"]
    assert "parked_latch" not in json.loads(state_path.read_text(encoding="utf-8"))


def test_ordinary_sessions_still_delegate_with_no_latch_side_effects(monkeypatch, tmp_path):
    """Negative control: a non-hold session's Stop is byte-identical to before —
    delegate, no latch written, no extra GitHub spend."""
    guard, state_path, calls = _ledger_guard(tmp_path, state_extra={"last_blocker": "render_pending"})

    def branch_only(_root, *args, **_kwargs):
        if args == ("branch", "--show-current"):
            return "claude/ordinary-feature"
        pytest.fail(f"non-candidate blocker must not inspect further git state: {args}")

    monkeypatch.setattr(WRAPPER, "_git", branch_only)
    assert WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"}) is None
    assert "parked_latch" not in json.loads(state_path.read_text(encoding="utf-8"))
    assert calls == {"open_pull": 0, "checks": 0}
