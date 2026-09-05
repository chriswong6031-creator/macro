"""Regression tests for the narrow HOLD-FOR-SOL Stop-hook state adapter."""

from __future__ import annotations

import importlib.util
import json
import re
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


# --------------------------------------------------------------------------------------
# PARKED message: the ship/merge attempt is terminal; the worker<->Sol dialogue is not.
#
# Operation macro-hold-dialogue-separation-20260901-sol-001. Repository law described
# PARKED as "terminal for the current session" at four source-law sites and once here at
# runtime. That is true of the ship/merge attempt and false of the reciprocal child
# dialogue, so a lawful held worker read it as an order to close the dialogue as well and
# went silent on Sol — which Mastermind docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md forbids
# ("silence is never a terminal receipt"). These tests pin the separation, and pin that it
# is a MESSAGE correction only: parked still requires every binding check concluded green,
# and merge/Ready/auto-merge/render/deploy/retry stay forbidden.
# --------------------------------------------------------------------------------------


PARKED_PROBE = {
    "number": 6608,
    "branch": "claude/biocatalyst-p1-0r-authority-closure",
    "head": HEAD,
    "candidate_kind": "ordinary_unmerged",
    "source_blocker": "unmerged",
    "status": "parked",
    "red": [],
    "pending": [],
    "passed": ["ci-gate", "fences"],
}


def _parked_text() -> str:
    message = WRAPPER._parked_message(PARKED_PROBE)
    assert set(message) == {"systemMessage"}, "PARKED stays a systemMessage, not a decision"
    return message["systemMessage"]


def test_parked_message_separates_ship_terminal_from_dialogue_terminal():
    text = _parked_text()
    lowered = text.lower()

    assert "SHIP LOOP PARKED" in text
    assert "not SHIPPED" in text
    assert "dialogue remains nonterminal" in text
    assert "only explicit Sol STOP" in text
    assert "same child" in text
    assert "same carrier" in text
    # What is actually terminal, stated positively.
    assert "terminal for the current ship/merge attempt" in text
    # The exact conflation this repair removes must not come back in any phrasing.
    for banned in (
        "terminal for the current session",
        "the session is terminal",
        "this session is terminal",
        "the child is terminal",
        "the worker is terminal",
        "the dialogue is terminal",
    ):
        assert banned not in lowered, f"re-conflates ship attempt with dialogue: {banned!r}"
    # "Just wait for Sol" is not a continuation path; the law requires a real receipt.
    assert "wait for sol" not in lowered


def test_parked_message_requires_truthful_continuation_receipt_before_yield():
    text = _parked_text()
    lowered = text.lower()

    # Both alternatives must be offered, so a worker with no watcher has a truthful
    # option other than disappearing.
    assert "WATCH_ARMED" in text
    assert "WATCH_UNAVAILABLE" in text
    # The posted return is a precondition of yielding, not an afterthought.
    assert "exact-carrier" in lowered
    assert "RESULT" in text
    assert "HOLD-FOR-SOL" in text
    # The hook is non-authoritative: it may state the obligation, never claim it is met.
    for banned in (
        "watcher is armed",
        "watcher has been armed",
        "a watcher was armed",
        "your watcher is armed",
        "watch_armed receipt exists",
    ):
        assert banned not in lowered, f"hook must not claim watcher state: {banned!r}"


def test_parked_message_claims_no_slack_state_and_creates_no_successor():
    """The wrapper is a message surface, not a control plane."""
    text = _parked_text()
    lowered = text.lower()

    # It cannot see Slack, so it must never report or infer Slack state.
    assert "slack" not in lowered
    assert re.search(r"\bC0B[A-Z0-9]{6,}\b", text) is None, "no channel/carrier id may be invented"
    assert "http://" not in lowered and "https://" not in lowered
    # It elects no Sol and mints no next unit of work.
    assert "@" not in text
    for banned in ("successor", "new session", "next wave", "spawn"):
        assert banned not in lowered, f"hook must not create a successor: {banned!r}"


def test_parked_message_still_forbids_every_release_action():
    """The permission boundary this repair must not move."""
    text = _parked_text()
    lowered = text.lower()

    # "mark ready", not bare "ready" — the latter is satisfied by the word "already".
    for forbidden_action in ("merge", "mark ready", "auto-merge", "render", "deploy", "retry"):
        assert forbidden_action in lowered, f"{forbidden_action!r} must still be named as forbidden"
    assert "forbidden" in lowered
    # Green-check evidence is still reported, so PARKED cannot be read as a bare assertion.
    assert "ci-gate" in text and "fences" in text


def test_parked_message_is_pure_and_needs_no_probe_or_network(monkeypatch):
    """`_parked_message` composes text only; eligibility stays in `_hold_probe`."""

    def explode(*_args, **_kwargs):
        raise AssertionError("_parked_message must not touch git, GitHub, or the filesystem")

    monkeypatch.setattr(WRAPPER, "_git", explode)
    monkeypatch.setattr(WRAPPER.subprocess, "run", explode)
    assert "SHIP LOOP PARKED" in WRAPPER._parked_message(PARKED_PROBE)["systemMessage"]


def test_main_parked_branch_emits_exactly_the_composed_message(monkeypatch, tmp_path, capsys):
    """`main()` must print the helper's message, not a second divergent copy."""
    _stub_clean_pushed_git(monkeypatch)
    guard, _ = _fake_guard(tmp_path)
    monkeypatch.setattr(WRAPPER, "_load_guard", lambda _path: guard)
    monkeypatch.setattr(
        WRAPPER,
        "_read_payload",
        lambda: ({"hook_event_name": "Stop", "cwd": str(tmp_path)}, b"{}"),
    )
    monkeypatch.setattr(
        WRAPPER, "_relay", lambda *_a, **_k: pytest.fail("a lawful green hold must not delegate")
    )

    WRAPPER.main()

    emitted = json.loads(capsys.readouterr().out)
    probe = WRAPPER._hold_probe(guard, {"hook_event_name": "Stop"})
    assert emitted == WRAPPER._parked_message(probe)


# --------------------------------------------------------------------------------------
# Source-law parity. Five files carry this rule; a future edit to one must not silently
# re-open the conflation in another.
# --------------------------------------------------------------------------------------


PARITY_FILES = (
    "CLAUDE.md",
    "AGENTS.md",
    "agentos/decisions/DEC-SOL-HOLD-IS-A-MERGE-BARRIER.md",
    "agentos/decisions/DEC-SESSION-LENGTH-IS-NOT-A-COST-CONTROL.md",
    "agentos/decisions/DEC-HOLD-PARKS-SHIP-NOT-DIALOGUE.md",
    # Sixth law surface. The Cursor rule is a separate ENFORCEMENT surface, so it went
    # on carrying the conflation ("End the session after one concise evidence report")
    # while the other five were corrected — and it does not contain the banned phrase
    # verbatim, so the ban alone would never have caught it. A worker on that surface
    # would still have been told to close the dialogue at PARKED.
    ".cursor/rules/ship-loop-terminal-states.mdc",
)

PARITY_TOKENS = (
    "terminal for the current ship/merge attempt",
    "dialogue remains nonterminal",
    "explicit same-carrier Sol STOP",
)


def _source_law_text(relative: str) -> str:
    """Return the file with whitespace normalized to single spaces.

    Parity is a claim about meaning, not layout. Without this, a token that happens to
    straddle a Markdown line wrap reads as absent — and, far worse, the banned phrase
    would evade its own check simply by being re-wrapped across two lines.
    """
    return " ".join(_source_law_raw(relative).split())


def _source_law_raw(relative: str) -> str:
    path = ROOT / relative
    if path.exists():
        return path.read_text(encoding="utf-8")
    proc = subprocess.run(
        ("git", "show", f"HEAD:{relative}"),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, f"{relative} unreadable: {proc.stderr}"
    return proc.stdout


@pytest.mark.parametrize("relative", PARITY_FILES)
def test_source_law_agrees_ship_attempt_is_not_the_reciprocal_dialogue(relative):
    text = _source_law_text(relative)
    for token in PARITY_TOKENS:
        assert token in text, f"{relative} is missing the parity token {token!r}"


@pytest.mark.parametrize("relative", PARITY_FILES)
def test_source_law_never_calls_parked_session_terminal(relative):
    lowered = _source_law_text(relative).lower()
    assert "terminal for the current session" not in lowered, (
        f"{relative} still conflates the ship attempt with the child dialogue"
    )


def test_source_law_keeps_hold_a_hard_merge_barrier():
    """Parity must never be achieved by weakening the barrier."""
    decision = _source_law_text("agentos/decisions/DEC-HOLD-PARKS-SHIP-NOT-DIALOGUE.md")
    lowered = decision.lower()
    assert "merge barrier" in lowered
    assert "not shipped" in lowered
    # The green requirement is the gate that makes PARKED lawful at all.
    assert "concluded green" in lowered


def test_cursor_rule_no_longer_orders_the_session_closed_at_parked():
    """The tenth-path falsifier: the banned phrase alone could not catch this one.

    `.cursor/rules/ship-loop-terminal-states.mdc` never contained the literal string
    `terminal for the current session`; it encoded the same conflation as an
    instruction — "End the session after one concise evidence report" — so the parity
    ban passed it while a Cursor-surface worker was still told to close the dialogue.
    Pin the instruction's absence, not just the phrase's.
    """
    lowered = _source_law_text(".cursor/rules/ship-loop-terminal-states.mdc").lower()

    for banned in ("end the session", "end your session", "stop the session"):
        assert banned not in lowered, f"the Cursor rule still closes the session: {banned!r}"
    # The prohibitions this surface already carried must survive the correction.
    for kept in ("do not merge", "mark ready", "arm automation", "poll/retry"):
        assert kept in lowered, f"tenth-path edit dropped an existing prohibition: {kept!r}"
    # Law text is never evidence that a watcher exists.
    assert "never establishes that any watcher" in lowered
