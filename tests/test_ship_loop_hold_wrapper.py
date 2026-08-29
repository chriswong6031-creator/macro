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


# ── One PARKED receipt and the shared V2 pending-wait ledger ────────────────


def _ledger_guard(
    tmp_path: Path,
    *,
    split=None,
    pull="default",
    state_extra=None,
    enter_quiescence=False,
    fast_quiescence=False,
):
    """A fake guard with the same single transactional ledger as production."""
    state_path = tmp_path / "state.json"
    state = {"last_blocker": "unmerged"}
    state.update(state_extra or {})
    state_path.write_text(json.dumps(state), encoding="utf-8")
    open_pull = _pull() if pull == "default" else pull
    split_result = split or ([], [], ["ci-plan", "contract-delta", "fence-pack"])
    calls = {
        "open_pull": 0,
        "checks": 0,
        "fast": 0,
        "enter": 0,
        "clear": 0,
    }
    ledger_lock = threading.Lock()
    entered = []

    def _open_pull(*_args):
        calls["open_pull"] += 1
        return open_pull

    def _head_check_runs(*_args):
        calls["checks"] += 1
        return [{"name": "fixture"}]

    def _load(path):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except OSError:
            return None

    def _save(path, value):
        Path(path).write_text(json.dumps(value), encoding="utf-8")

    def _update_ledger(path, mutate, **_kwargs):
        with ledger_lock:
            latest = _load(path)
            if not isinstance(latest, dict):
                return None
            result = mutate(latest)
            _save(path, latest)
            return result

    def _fast(_root, _path, _state):
        calls["fast"] += 1
        return fast_quiescence

    def _enter(path, latest, **kwargs):
        calls["enter"] += 1
        entered.append(kwargs)
        if enter_quiescence:
            latest["ci_quiescence"] = {
                "mode": "hold",
                "head": kwargs["head"],
            }
            _save(path, latest)
        return enter_quiescence

    def _clear(path, latest):
        calls["clear"] += 1
        latest.pop("ci_quiescence", None)
        _save(path, latest)

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
        _ci_quiescence_fast_path=_fast,
        _enter_ci_quiescence=_enter,
        _ci_quiescence_clear=_clear,
        _ci_checks_fingerprint=lambda _runs: "c" * 16,
        _ci_authority_fingerprint=lambda _pull, **_kwargs: "a" * 16,
    )
    return guard, state_path, calls, entered


def _install_material_router(guard, state_path: Path):
    routed = []

    def event_route(kind, *, pr, head, checks):
        owner = (
            "#6351/main-integrity"
            if kind in {"inherited_main", "infrastructure", "missing_evidence"}
            else "release/Sol"
        )
        return {"kind": kind, "owner": owner, "pr": pr, "head": head, "checks": checks}

    def receipt(
        _path,
        _state,
        quiescence,
        route,
        *,
        checks_fingerprint,
        authority_fingerprint,
    ):
        routed.append(route)

        def latch(latest):
            current = latest["ci_quiescence"]
            assert current is not quiescence or current == quiescence
            current["phase"] = "routed"
            current["route"] = route["owner"]
            current["checks_fingerprint"] = checks_fingerprint
            current["authority_fingerprint"] = authority_fingerprint

        guard._update_ledger(state_path, latch)
        return True

    guard._ci_event_route = event_route
    guard._ci_material_receipt = receipt
    return routed


def test_first_parked_stop_narrates_once_then_identical_stops_are_silent(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, calls, _entered = _ledger_guard(tmp_path)

    first = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})
    assert first is not None and first["action"] == "emit"
    assert first["value"]["systemMessage"].startswith("SHIP LOOP PARKED")
    assert json.loads(state_path.read_text())["parked_latch"] == (
        f"parked:6138:{HEAD}"
    )

    repeats = [
        WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})
        for _ in range(5)
    ]
    assert repeats == [{"action": "silent"}] * 5
    assert calls["open_pull"] == 6 and calls["checks"] == 6


def test_pending_hold_without_a_live_watcher_preserves_6626_waiting_block(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, _path, calls, _entered = _ledger_guard(
        tmp_path,
        split=(
            [],
            ["trusted-ci / trusted-executor-pack-10"],
            ["ci-plan", "contract-delta", "fence-pack"],
        ),
    )

    verdict = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})

    assert verdict is not None and verdict["action"] == "emit"
    assert "HOLD-FOR-SOL WAITING" in verdict["value"]["reason"]
    assert calls["enter"] == 1


def test_pending_hold_with_one_live_watcher_uses_shared_ci_quiescence(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, calls, entered = _ledger_guard(
        tmp_path,
        split=(
            [],
            ["trusted-ci / trusted-executor-pack-10"],
            ["ci-plan", "contract-delta", "fence-pack"],
        ),
        enter_quiescence=True,
    )

    verdict = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})

    assert verdict == {"action": "silent"}
    assert calls["enter"] == 1
    assert entered[0]["mode"] == "hold"
    assert entered[0]["number"] == 6138 and entered[0]["head"] == HEAD
    assert json.loads(state_path.read_text())["ci_quiescence"]["mode"] == "hold"


def test_identical_pending_hold_hits_local_quiescence_before_any_github_probe(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, _path, calls, _entered = _ledger_guard(
        tmp_path,
        state_extra={"ci_quiescence": {"mode": "hold", "head": HEAD}},
        fast_quiescence=True,
    )

    verdict = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})

    assert verdict == {"action": "silent"}
    assert calls["fast"] == 1
    assert calls["open_pull"] == 0 and calls["checks"] == 0


def test_red_hold_clears_old_quiescence_and_keeps_6626_checks_red_block(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, calls, _entered = _ledger_guard(
        tmp_path,
        split=(["ci-pack-3 (failure)"], [], ["fence-pack"]),
        state_extra={"ci_quiescence": {"mode": "hold", "head": HEAD}},
    )

    verdict = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})

    assert verdict is not None and verdict["action"] == "emit"
    assert "HOLD-FOR-SOL CHECKS RED" in verdict["value"]["reason"]
    assert calls["clear"] == 1
    assert "ci_quiescence" not in json.loads(state_path.read_text())


def test_dead_watcher_with_still_pending_hold_routes_missing_evidence_once(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, _calls, _entered = _ledger_guard(
        tmp_path,
        split=(
            [],
            ["trusted-ci / trusted-executor-pack-10"],
            ["ci-plan", "contract-delta", "fence-pack"],
        ),
        state_extra={"ci_quiescence": {"mode": "hold", "head": HEAD}},
    )
    routed = _install_material_router(guard, state_path)

    verdict = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})

    assert verdict == {"action": "silent"}
    assert [route["kind"] for route in routed] == ["missing_evidence"]
    assert routed[0]["owner"] == "#6351/main-integrity"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["ci_quiescence"]["phase"] == "routed"


def test_infrastructure_red_hold_routes_away_from_product_builder(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, calls, _entered = _ledger_guard(
        tmp_path,
        split=(["trusted-ci admission (timed_out)"], [], ["fence-pack"]),
        state_extra={"ci_quiescence": {"mode": "hold", "head": HEAD}},
    )
    guard._red_pairs = lambda _runs: [("trusted-ci admission", "timed_out")]
    guard._ci_infrastructure_red = lambda pairs: pairs == [
        ("trusted-ci admission", "timed_out")
    ]
    routed = _install_material_router(guard, state_path)

    verdict = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})

    assert verdict == {"action": "silent"}
    assert [route["kind"] for route in routed] == ["infrastructure"]
    assert routed[0]["owner"] == "#6351/main-integrity"
    assert calls["clear"] == 0


def test_inherited_main_red_hold_routes_away_only_with_complete_base_proof(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, calls, _entered = _ledger_guard(
        tmp_path,
        split=(["ci-pack-3 (failure)"], [], ["fence-pack"]),
        state_extra={"ci_quiescence": {"mode": "hold", "head": HEAD}},
    )
    guard._red_pairs = lambda _runs: [("ci-pack-3", "failure")]
    guard._ci_infrastructure_red = lambda _pairs: False
    guard._is_non_binding_check = lambda _name: False
    guard._started_stamp = lambda _run, *_fields: "2026-08-29T00:00:00Z"
    guard._base_side_pre_merge = lambda *_args: (
        {"ci-pack-3": "red on main's exact proof"},
        [],
    )
    routed = _install_material_router(guard, state_path)

    verdict = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})

    assert verdict == {"action": "silent"}
    assert [route["kind"] for route in routed] == ["inherited_main"]
    assert routed[0]["owner"] == "#6351/main-integrity"
    assert calls["clear"] == 0


def test_inherited_main_rerun_generations_do_not_look_like_two_distinct_reds(
    monkeypatch, tmp_path
):
    """Two check-run generations with one job name share one base-side proof."""
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, _calls, _entered = _ledger_guard(
        tmp_path,
        split=(
            ["ci-pack-3 (failure)", "ci-pack-3 (failure)"],
            [],
            ["fence-pack"],
        ),
        state_extra={"ci_quiescence": {"mode": "hold", "head": HEAD}},
    )
    guard._red_pairs = lambda _runs: [
        ("ci-pack-3", "failure"),
        ("ci-pack-3", "failure"),
    ]
    guard._ci_infrastructure_red = lambda _pairs: False
    guard._is_non_binding_check = lambda _name: False
    guard._started_stamp = lambda _run, *_fields: "2026-08-29T00:00:00Z"
    guard._base_side_pre_merge = lambda *_args: (
        {"ci-pack-3": "red on main's exact proof"},
        [],
    )
    routed = _install_material_router(guard, state_path)

    verdict = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})

    assert verdict == {"action": "silent"}
    assert [route["kind"] for route in routed] == ["inherited_main"]


def test_green_after_pending_quiescence_clears_wait_then_parks_once(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, calls, _entered = _ledger_guard(
        tmp_path,
        state_extra={"ci_quiescence": {"mode": "hold", "head": HEAD}},
    )

    verdict = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})

    assert verdict is not None and verdict["action"] == "emit"
    assert verdict["value"]["systemMessage"].startswith("SHIP LOOP PARKED")
    state = json.loads(state_path.read_text())
    assert "ci_quiescence" not in state
    assert state["parked_latch"] == f"parked:6138:{HEAD}"
    assert calls["clear"] == 1


def test_parked_latch_transaction_preserves_concurrent_watcher(
    monkeypatch, tmp_path
):
    guard, state_path, _calls, _entered = _ledger_guard(tmp_path)
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
            "passed": ["ci-plan", "contract-delta", "fence-pack"],
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
        "fragment": "gh pr checks 6138 --watch --interval 60",
        "head": HEAD,
        "created": 1.0,
    }
    state_path.write_text(json.dumps(latest), encoding="utf-8")
    watcher_written.set()
    writer.join(timeout=10)

    assert not writer.is_alive()
    assert results and results[0]["action"] == "emit"
    final = json.loads(state_path.read_text(encoding="utf-8"))
    assert final["parked_latch"] == f"parked:6138:{HEAD}"
    assert final["ship_watcher"]["fragment"].startswith("gh pr checks")


def test_nonparked_probe_clears_concurrent_latch_without_erasing_watcher(
    monkeypatch, tmp_path
):
    guard, state_path, _calls, _entered = _ledger_guard(tmp_path)
    probe_started = threading.Event()
    latch_written = threading.Event()
    results = []

    def paused_nonparked(_guard, _payload):
        probe_started.set()
        assert latch_written.wait(timeout=10)
        return None

    monkeypatch.setattr(WRAPPER, "_hold_probe", paused_nonparked)
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
        "fragment": "gh pr checks 6138 --watch --interval 60",
        "head": HEAD,
        "created": 1.0,
    }
    state_path.write_text(json.dumps(latest), encoding="utf-8")
    latch_written.set()
    writer.join(timeout=10)

    assert not writer.is_alive()
    assert results == [None]
    final = json.loads(state_path.read_text(encoding="utf-8"))
    assert "parked_latch" not in final
    assert final["ship_watcher"]["fragment"].startswith("gh pr checks")


def test_github_outage_delegates_without_clearing_parked_latch(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, _calls, _entered = _ledger_guard(
        tmp_path, state_extra={"parked_latch": f"parked:6138:{HEAD}"}
    )
    guard._open_pull = lambda *_args: (_ for _ in ()).throw(
        RuntimeError("api.github.com unreachable")
    )

    assert WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"}) is None
    assert json.loads(state_path.read_text(encoding="utf-8"))["parked_latch"]


@pytest.mark.parametrize(
    "state_extra",
    [
        {"parked_latch": f"parked:6138:{HEAD}"},
        {
            "ci_quiescence": {
                "mode": "hold",
                "head": HEAD,
                "phase": "waiting",
            }
        },
    ],
)
def test_local_git_unanswerability_preserves_existing_hold_state(
    monkeypatch, tmp_path, state_extra
):
    guard, state_path, _calls, _entered = _ledger_guard(
        tmp_path, state_extra=state_extra
    )

    def failing_git(_root, *args, **_kwargs):
        if args == ("branch", "--show-current"):
            return "claude/biocatalyst-p1-0r-authority-closure"
        raise RuntimeError("local git state unanswerable")

    monkeypatch.setattr(WRAPPER, "_git", failing_git)

    assert WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"}) is None
    final = json.loads(state_path.read_text(encoding="utf-8"))
    for key, value in state_extra.items():
        assert final[key] == value


def test_ordinary_quiescence_is_never_cleared_by_the_hold_wrapper(
    monkeypatch, tmp_path
):
    state_extra = {
        "ci_quiescence": {
            "version": "ci_quiescence.v1",
            "mode": "ordinary",
            "head": HEAD,
            "phase": "waiting",
        }
    }
    guard, state_path, _calls, _entered = _ledger_guard(
        tmp_path, state_extra=state_extra, fast_quiescence=False
    )
    monkeypatch.setattr(WRAPPER, "_hold_probe", lambda *_a, **_kw: None)

    assert WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"}) is None
    assert json.loads(state_path.read_text(encoding="utf-8"))["ci_quiescence"] == (
        state_extra["ci_quiescence"]
    )


def test_hold_probe_uses_paginated_comments_including_page_two(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, _calls = _fake_guard(tmp_path)
    pages = [
        [{"id": index, "body": "ordinary discussion"} for index in range(100)],
        _comments(),
    ]
    guard._bounded_github_list = lambda _url: [item for page in pages for item in page]
    guard._get_json = lambda _url: (_ for _ in ()).throw(
        AssertionError("single-page authority read is forbidden")
    )

    probe = WRAPPER._hold_probe(guard, {"hook_event_name": "Stop"})

    assert probe is not None
    assert any("Release condition" in item["body"] for item in probe["comments"])


def test_hold_probe_constructs_comments_endpoint_when_pull_omits_it(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    pull = _pull()
    pull.pop("comments_url", None)
    guard, _state_path, _calls, _entered = _ledger_guard(tmp_path, pull=pull)
    loaded = []

    def bounded(url):
        loaded.append(url)
        if url.endswith("/issues/6138/comments"):
            return _comments()
        if url.endswith("/pulls/6138/reviews"):
            return []
        raise AssertionError(url)

    guard._bounded_github_list = bounded
    guard._get_json = lambda _url: (_ for _ in ()).throw(
        AssertionError("single-page fallback is forbidden")
    )

    probe = WRAPPER._hold_probe(guard, {"hook_event_name": "Stop"})

    assert probe is not None
    assert loaded == [
        "https://api.github.com/repos/mastermindx-market-intelligence/macro/issues/6138/comments",
        "https://api.github.com/repos/mastermindx-market-intelligence/macro/pulls/6138/reviews",
    ]


def test_outage_blocker_mutation_does_not_renarrate_same_parked_hold(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    guard, state_path, calls, _entered = _ledger_guard(
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

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["last_blocker"] = "github_unreachable"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    guard._open_pull = original_open

    first = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})
    second = WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"})
    assert first == second == {"action": "silent"}
    assert calls["open_pull"] == 2 and calls["checks"] == 2


def test_released_or_closed_hold_clears_latch_and_delegates(
    monkeypatch, tmp_path
):
    _stub_clean_pushed_git(monkeypatch)
    for released_pull in (_pull(draft=False), None):
        guard, state_path, _calls, _entered = _ledger_guard(
            tmp_path,
            pull=released_pull,
            state_extra={"parked_latch": f"parked:6138:{HEAD}"},
        )
        assert WRAPPER._handle_stop(guard, {"hook_event_name": "Stop"}) is None
        assert "parked_latch" not in json.loads(
            state_path.read_text(encoding="utf-8")
        )
