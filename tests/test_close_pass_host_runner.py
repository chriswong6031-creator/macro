"""tests/test_close_pass_host_runner.py — the close pass's host-native PRIMARY clock.

The lane this guards is ``scripts/close_pass_host_runner.py``, fired by
``com.macro.closepass`` at 13:00 local (PT) = 16:00 ET in both DST regimes. It
replaced GitHub cron as the product clock because cron measured 27 minutes of
schedule drift plus a 95-minute queue wait on 2026-08-14 and published the board
at ~19:20 ET against a 16:15 ET target.

WHAT IS PINNED HERE, and why each one is a defect somebody could actually ship:

  SINGLE INSTANCE   a manual kickstart over a running pass must EXIT CLEAN, not
                    race the same worktree with a second reset --hard.
  FAST EXIT         a holiday costs one interpreter start — no fetch, no venv,
                    no publish. The saving is the point; the ordering is the test.
  DEGRADE           ``engine.close_pass.massive_close`` (PR-A) may not exist in
                    the checkout. Absent means publish NOW, never wait forever.
  THE WAIT          every branch PROCEEDS. This function chooses when, never
                    whether, which is what makes being wrong survivable.
  RECEIPT           the run's only durable trace. A killed lane and a lane that
                    never fired leave the same evidence — nothing — so the
                    receipt is the instrument that tells them apart.
  DISCARD           the ``--heal`` prefetch dirties data/; the nightly is the
                    sole writer of record (G0.2, DNR:KILL-INTRADAY-CHRONICLE).
  BUDGET            a wedged pass is killed and REPORTED, never left holding the
                    lock into the nightly.

CLOCK. Every wall-clock decision is driven through an injected ``now_fn`` and an
injected ``sleep_fn``, so nothing here becomes a scheduled red at 16:05 ET.

NOTE ON THE OTHER SUITE. ``tests/test_close_pass_lane.py`` bans ``subprocess``
and ``git `` inside the four publish-path modules it reads. This runner is not
one of them and must not be added: running git IS its job — it is the half that
prepares a fresh checkout so the publish-path modules never have to.

Run: python3 -m pytest tests/test_close_pass_host_runner.py -q
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.close_pass_host_runner as R  # noqa: E402

RUNNER_SRC = (ROOT / "scripts" / "close_pass_host_runner.py").read_text(encoding="utf-8")

#: 2026-08-14 is a Friday and a full NYSE session; 20:00:05Z is 16:00:05 ET under
#: EDT — five seconds after the launchd firing and five before the wait arms.
FIRED = dt.datetime(2026, 8, 14, 20, 0, 5, tzinfo=dt.timezone.utc)
SESSION = "2026-08-14"


# ─────────────────────────────────────────────────────────────────────────────
# Doubles
# ─────────────────────────────────────────────────────────────────────────────
class Sh:
    """Records every command the runner would run, and answers with a script.

    ONE seam for the whole lane: the runner routes git, the venv, the probes,
    the heal and the publish through ``_sh``, so a test can read the entire
    conversation without a real repository or a real interpreter.
    """

    def __init__(self) -> None:
        self.calls: list = []
        self._rules: list = []

    def on(self, needle: str, result: R.ShResult) -> "Sh":
        self._rules.append((needle, result))
        return self

    def __call__(self, argv, **kw) -> R.ShResult:
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        joined = " ".join(argv)
        for needle, result in self._rules:
            if needle in joined:
                return result
        return R.ShResult(0, "", False)

    def joined(self) -> list:
        return [" ".join(c) for c in self.calls]

    def index_of(self, needle: str) -> int:
        for i, line in enumerate(self.joined()):
            if needle in line:
                return i
        raise AssertionError(f"{needle!r} never ran; ran: {self.joined()}")

    def ran(self, needle: str) -> bool:
        return any(needle in line for line in self.joined())


class Clock:
    """A wall clock that only moves when the code under test sleeps."""

    def __init__(self, start: dt.datetime) -> None:
        self.now = start
        self.slept: list = []

    def now_fn(self) -> dt.datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now = self.now + dt.timedelta(seconds=seconds)


def probe_script(states):
    """A probe that walks ``states`` and then repeats the last one forever."""
    box = {"i": 0}

    def _probe() -> dict:
        i = min(box["i"], len(states) - 1)
        box["i"] += 1
        return states[i]

    return _probe


def probe_never_settles():
    """A tape that keeps moving — a fresh digest on every single read.

    Written as its own generator rather than a long scripted list because the
    deadline branch is only reachable when NOTHING ever repeats: a script that
    runs out and repeats its last entry settles by accident, which is exactly
    how this parametrisation first passed the wrong assertion.
    """
    box = {"i": 0}

    def _probe() -> dict:
        box["i"] += 1
        return {"status": "snapshot", "digest": f"d{box['i']}"}

    return _probe


def session_answer(session):
    body = json.dumps({"session": session})
    return R.ShResult(0, f"some import chatter\n{body}\n", False)


@pytest.fixture
def host(monkeypatch, tmp_path):
    """A runnable lane whose every path is under tmp_path."""
    primary = tmp_path / "primary"
    lane = primary / ".claude" / "worktrees" / "closepass-host-lane"
    support = tmp_path / "support"
    venv = tmp_path / "venv"
    (lane / "scripts").mkdir(parents=True)
    # origin/main's OWN copy of the runner, which is what prepare_lane's reset
    # leaves behind and therefore the reference every run grades its executing
    # bootstrap against. Byte-identical here, so the default lane is a lane with
    # NO drift and every drift test has to create the condition explicitly.
    (lane / "scripts" / R.RUNNER_BASENAME).write_bytes(
        (ROOT / "scripts" / R.RUNNER_BASENAME).read_bytes())
    (lane / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    (lane / "requirements.txt").write_text("pandas==2.2.2\n", encoding="utf-8")
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    (primary / ".env").write_text(
        "R2_ENDPOINT=https://example.invalid\n"
        "R2_ACCESS_KEY_ID=aaaa\n"
        "R2_SECRET_ACCESS_KEY=s3cr3t-never-logged\n"
        "COLLECT_LANE=nightly\n", encoding="utf-8")

    monkeypatch.setenv("CLOSE_PASS_HOST_PRIMARY", str(primary))
    monkeypatch.setenv("CLOSE_PASS_HOST_LANE", str(lane))
    monkeypatch.setenv("CLOSE_PASS_HOST_SUPPORT", str(support))
    monkeypatch.setenv("CLOSE_PASS_HOST_VENV", str(venv))
    monkeypatch.setenv("CLOSE_PASS_HOST_LOGS", str(tmp_path / "logs"))
    monkeypatch.delenv("CLOSE_PASS_HOST_NOW", raising=False)

    class Host:
        def __init__(self) -> None:
            self.primary = primary
            self.lane = lane
            self.support = support
            self.venv = venv
            self.sh = Sh()
            self.sh.on("nyse_calendar", session_answer(SESSION))
            self.sh.on("rev-parse HEAD", R.ShResult(0, "a" * 40 + "\n", False))
            self.clock = Clock(FIRED)
            self.elapsed = [0.0]

        def monotonic(self) -> float:
            return self.elapsed[0]

        def run(self, *, now=FIRED, dry_run=True, now_fn=None) -> int:
            return R.run(now=now, dry_run=dry_run, sh=self.sh,
                         sleep_fn=self.clock.sleep, clock=self.monotonic,
                         now_fn=now_fn or self.clock.now_fn)

        def receipt(self, session=SESSION) -> dict:
            path = support / "runs" / f"{session}.json"
            return json.loads(path.read_text(encoding="utf-8"))

    return Host()


# ─────────────────────────────────────────────────────────────────────────────
# Single instance
# ─────────────────────────────────────────────────────────────────────────────
def test_a_second_invocation_exits_clean_instead_of_racing_the_first(host, capsys):
    """launchd will happily fire a job that a manual kickstart is still running.

    Two passes sharing one worktree would `reset --hard` under each other's feet
    mid-publish, so the second must stand down — and it must do so with exit 0,
    because a working lane that is merely busy is not a fault and must not red.
    """
    lock_path = host.support / "runner.lock"
    first = R.acquire_lock(lock_path)
    assert first is not None
    try:
        assert R.acquire_lock(lock_path) is None
        assert R.main([]) == 0
    finally:
        R.release_lock(first)

    notices = [ln for ln in capsys.readouterr().out.splitlines() if "::notice" in ln]
    assert notices and notices[-1].startswith("::notice title=close-pass-host::")
    assert "holds the lock" in notices[-1]
    # And the pass itself never started: no receipt, so nothing can later read
    # this as a session the primary covered.
    assert not (host.support / "runs").exists()

    # The lock is genuinely released, not merely dropped on the floor.
    again = R.acquire_lock(lock_path)
    assert again is not None
    R.release_lock(again)


# ─────────────────────────────────────────────────────────────────────────────
# The fast non-session exit
# ─────────────────────────────────────────────────────────────────────────────
def test_a_holiday_costs_one_interpreter_start_and_nothing_else(host, capsys):
    """The ordering IS the feature. ~9 full-day closures a year, and on each of
    them this lane must not fetch, must not pip, must not heal and must not
    publish — the whole saving evaporates if the session question is asked after
    the checkout is prepared instead of before."""
    host.sh = Sh().on("nyse_calendar", session_answer(None))
    assert host.run() == 0
    assert not host.sh.ran("fetch"), host.sh.joined()
    assert not host.sh.ran("reset --hard")
    assert not host.sh.ran("close_pass_publish")
    assert not host.sh.ran("check_price_store_freshness")
    assert "::notice title=close-pass-host::" in capsys.readouterr().out
    # The receipt still lands: "we looked, it was a holiday" is a fact worth
    # keeping, and it is what distinguishes a holiday from a dead launchd agent.
    assert host.receipt("no-session")["outcome"] == "not_a_session"


def test_an_unreadable_session_probe_proceeds_rather_than_skipping_the_day(host):
    """FAIL-OPEN, deliberately. The probe is an optimisation; the AUTHORITY is
    close_pass_publish.session_date, which runs from fresh code a minute later
    and no-ops on a non-session day by itself. A probe that could VETO the run
    would be a second definition of "when is the market open" — and the one
    that fails closed on its own bug."""
    host.sh = Sh().on("nyse_calendar", R.ShResult(1, "ImportError", False))
    host.sh.on("rev-parse HEAD", R.ShResult(0, "b" * 40 + "\n", False))
    assert host.run() == 0
    assert host.sh.ran("close_pass_publish")
    assert host.receipt()["session"] == SESSION


def test_the_session_question_is_asked_of_the_checkout_not_reimplemented():
    """lib.nyse_calendar is the single definition, and the runner asks it by
    running it inside the lane. A holiday table copied into this file is a
    second calendar to forget to update."""
    assert "from lib.nyse_calendar import is_session" in R._SESSION_SNIPPET
    code = ast.unparse(ast.parse(RUNNER_SRC))
    for invented in ("Thanksgiving", "Juneteenth", "ONE_OFF_CLOSURES", "weekday() <"):
        assert invented not in code, invented


# ─────────────────────────────────────────────────────────────────────────────
# The lane checkout
# ─────────────────────────────────────────────────────────────────────────────
def test_the_lane_worktree_is_created_locked_and_full(host, tmp_path):
    """Two properties in one command, and both are load-bearing.

    --lock keeps the fleet worktree GC off a production lane
    (research/WORKTREE_GC_POLICY.md keeps anything locked). FULL is the point of
    creating it with raw git at all: session worktrees are minted sparse by
    .claude/hooks/worktree_create_sparse.py and omit data/, and a lane whose
    data/ was omitted would publish a board with no prices in it.
    """
    fresh = tmp_path / "primary" / ".claude" / "worktrees" / "gone"
    sh = Sh().on("rev-parse HEAD", R.ShResult(0, "c" * 40 + "\n", False))
    state = R.prepare_lane(host.primary, fresh, sh=sh)
    assert state["ok"] and state["code_sha"] == "c" * 40
    add = sh.joined()[sh.index_of("worktree add")]
    assert "--lock" in add and "--reason" in add and "--detach" in add
    assert str(fresh) in add and "origin/main" in add
    # Nothing asks for a sparse profile, and nothing may: the sparse hook never
    # sees a raw-git worktree, which is exactly why this one is whole.
    assert not sh.ran("sparse-checkout")
    # ...and the per-run clean spares the committed store it was created for.
    clean = sh.joined()[sh.index_of("clean -fdq -e")]
    assert "-e /data" in clean


def test_a_failed_fetch_publishes_anyway_and_says_so_in_the_receipt(host, capsys):
    """The asymmetry that makes `code_stale` worth having: a day-old checkout
    still produces a correct board, so a network blip must not cost the session.
    What it must not do is pass unnoticed — a week of quietly stale runs behind
    a green log is the failure this flag exists to prevent."""
    host.sh.on("fetch origin main", R.ShResult(1, "could not resolve host", False))
    assert host.run() == 0
    assert host.sh.ran("close_pass_publish")
    receipt = host.receipt()
    assert receipt["code_stale"] is True
    assert receipt["code_sha"] == "a" * 40
    assert any("::warning" in ln and "code_stale" in ln
               for ln in capsys.readouterr().out.splitlines())


def test_a_failed_reset_refuses_rather_than_running_unknown_code(host, capsys):
    """The other side of the same asymmetry. After a failed reset the working
    tree is in an unknown state, so "which code ran" has no answer at all — and
    answering that is the entire job of the receipt this run would otherwise
    write."""
    host.sh.on("reset --hard", R.ShResult(1, "index.lock exists", False))
    assert host.run() == 1
    assert not host.sh.ran("close_pass_publish")
    assert host.receipt("no-session")["outcome"] == "lane_unprepared"
    assert any("::error" in ln for ln in capsys.readouterr().out.splitlines())


def test_a_tcc_denial_names_the_one_time_grant_that_fixes_it(host):
    """macOS shields ~/Documents from background jobs and launchd gets no
    consent prompt, just "Operation not permitted". A log that only says
    "refused" sends the operator hunting; this one names the exact setting."""
    sh = Sh().on("rev-parse --git-dir",
                 R.ShResult(128, "fatal: ... Operation not permitted", False))
    state = R.prepare_lane(host.primary, host.lane, sh=sh)
    assert state["ok"] is False
    assert "Full Disk Access" in state["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# The close wait — every branch proceeds; the outcome records WHICH
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("make_probe,expected", [
    # A finalized grouped read is the strongest answer there is: publish now.
    (lambda: probe_script([{"status": "final", "n": 1660}]), "grouped_final"),
    # Two identical snapshots — the tape stopped moving.
    (lambda: probe_script([{"status": "snapshot", "digest": "d1"},
                           {"status": "snapshot", "digest": "d1"}]), "stable_snapshot"),
    # PR-A absent: there is nothing to wait ON, so waiting would be twelve
    # minutes of sleeping for no information.
    (lambda: probe_script([{"status": "unavailable", "detail": "no module"}]),
     "module_absent"),
    # A probe that cannot read will not start reading inside twelve minutes.
    (lambda: probe_script([{"status": "error"}]), "probe_error"),
    # An answer this runner does not understand is not an excuse to hold.
    (lambda: probe_script([{"status": "in-flight"}]), "probe_unreadable"),
    # Still moving at 16:12 ET: publish degraded. The pass skips and COUNTS any
    # name without today's bar, so coverage falls visibly and truth does not.
    (probe_never_settles, "deadline"),
], ids=["grouped_final", "stable_snapshot", "module_absent", "probe_error",
        "probe_unreadable", "deadline"])
def test_the_close_wait_decision_table(make_probe, expected):
    clock = Clock(FIRED)
    outcome, polls = R.wait_for_close(probe=make_probe(),
                                      now_fn=clock.now_fn, sleep_fn=clock.sleep)
    assert outcome == expected
    assert outcome in R.WAIT_OUTCOMES
    assert polls >= 1
    # Whatever happened, the hold is bounded by the ET deadline and nothing else.
    assert clock.now.astimezone(R.ET).time() <= R.WAIT_DEADLINE_ET


def test_the_wait_arms_at_the_close_and_never_before_it():
    """The launchd firing lands ~10 s before the window. The first probe waits
    for it rather than burning a guaranteed miss on a close that has not printed."""
    clock = Clock(FIRED)                       # 16:00:05 ET
    R.wait_for_close(probe=probe_script([{"status": "final"}]),
                     now_fn=clock.now_fn, sleep_fn=clock.sleep)
    assert clock.slept and clock.slept[0] == pytest.approx(5.0, abs=0.01)
    assert clock.now.astimezone(R.ET).time() >= R.WAIT_START_ET


def test_a_manual_replay_hours_early_does_not_sleep_until_the_close():
    """An operator kickstart at 10:00 ET must publish, not hold for six hours.
    Anything further out than the arming lead skips the wait outright."""
    clock = Clock(dt.datetime(2026, 8, 14, 14, 0, tzinfo=dt.timezone.utc))  # 10:00 ET
    outcome, polls = R.wait_for_close(probe=probe_script([{"status": "final"}]),
                                      now_fn=clock.now_fn, sleep_fn=clock.sleep)
    assert (outcome, polls) == ("outside_window", 0)
    assert clock.slept == []


def test_a_late_firing_publishes_immediately_instead_of_waiting_for_tomorrow():
    """The drift this whole lane exists to answer can also hit launchd (a sleeping
    Mac, a long previous run). Past the deadline there is nothing left to wait
    for, and the board is already late."""
    clock = Clock(dt.datetime(2026, 8, 14, 21, 30, tzinfo=dt.timezone.utc))  # 17:30 ET
    assert R.wait_for_close(probe=probe_script([{"status": "final"}]),
                            now_fn=clock.now_fn,
                            sleep_fn=clock.sleep) == ("past_deadline", 0)
    assert clock.slept == []


def test_two_empty_reads_are_not_a_stable_snapshot():
    """`None == None` would call a vendor returning nothing "stable" and publish
    into a hole. Stability is only ever claimed on a digest the probe actually
    produced."""
    clock = Clock(FIRED)
    outcome, _ = R.wait_for_close(
        probe=probe_script([{"status": "snapshot"}, {"status": "snapshot"}]),
        now_fn=clock.now_fn, sleep_fn=clock.sleep)
    assert outcome == "deadline"


def test_an_error_run_is_broken_by_a_good_read(host):
    """The error budget counts CONSECUTIVE failures. A vendor blip followed by
    two stable reads must still publish on the strong answer, not on the budget."""
    clock = Clock(FIRED)
    outcome, _ = R.wait_for_close(
        probe=probe_script([{"status": "error"}, {"status": "error"},
                            {"status": "snapshot", "digest": "d"},
                            {"status": "error"}, {"status": "error"},
                            {"status": "snapshot", "digest": "d"},
                            {"status": "snapshot", "digest": "d"}]),
        now_fn=clock.now_fn, sleep_fn=clock.sleep)
    assert outcome == "stable_snapshot"


def test_the_window_is_the_close_plus_twelve_minutes():
    assert R.WAIT_START_ET == dt.time(16, 0, 10)
    assert R.WAIT_DEADLINE_ET == dt.time(16, 12, 0)
    assert R.PROBE_ERROR_BUDGET == 3
    assert 20 <= R.POLL_SPACING_S <= 30


# ─────────────────────────────────────────────────────────────────────────────
# The probe half — duck-typed over a sibling PR that has not merged
# ─────────────────────────────────────────────────────────────────────────────
class FakeMassive:
    def __init__(self, result=None, hook=None) -> None:
        self._result = result
        if hook is not None:
            self.close_probe = hook

    def fetch_session_closes(self, session):
        return self._result


def test_an_absent_massive_close_reports_unavailable_rather_than_failing(
        monkeypatch, capsys):
    """The absence is SIMULATED now. This test was written while PR-A was in
    flight and leaned on the module's real absence; #5746 merged 2026-08-15 and
    the lean broke in CI the same hour (status came back 'error' — present
    module, no API key — not 'unavailable'). The CONTRACT outlives the sibling:
    a sparse checkout, a revert, or a future package split must still skip the
    wait rather than traceback, so the import failure is forced explicitly.

    BOTH import paths are severed, and the second is the one that bit in CI:
    ``from engine.close_pass import massive_close`` consults ``sys.modules``
    only when the parent package does not already carry the submodule as an
    ATTRIBUTE — and the massive_close suite runs earlier in this very CI step,
    so the attribute is set and a sys.modules-only patch tests nothing. The
    attribute is removed too, making the simulation order-independent."""
    import sys as _sys
    import engine.close_pass as _pkg
    monkeypatch.setitem(_sys.modules, "engine.close_pass.massive_close", None)
    monkeypatch.delattr(_pkg, "massive_close", raising=False)
    assert R.probe_close_main(SESSION) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["status"] == "unavailable"
    assert "massive_close" in payload["detail"] or "None" in payload["detail"] \
        or "import" in payload["detail"].lower()


@pytest.mark.parametrize("result,expected", [
    ({"AAA": 1.0, "BBB": 2.0}, "snapshot"),
    (({"AAA": 1.0}, True), "final"),
    (({"AAA": 1.0}, False), "snapshot"),
    ({"closes": {"AAA": 1.0}, "finalized": True}, "final"),
    ({"closes": {"AAA": 1.0}, "is_final": False}, "snapshot"),
])
def test_the_adapter_reads_the_shapes_pr_a_might_ship(result, expected):
    payload = R._probe_payload(FakeMassive(result), SESSION)
    assert payload["status"] == expected
    assert payload["n"] == 1 or payload["n"] == 2
    assert payload["digest"]


def test_an_unrecognised_module_degrades_instead_of_guessing():
    """The fail-safe direction, by construction: a surface this adapter does not
    recognise reports `unavailable`, the wait is skipped, and the pass publishes
    immediately — today's behaviour exactly. It never invents a close, never
    blocks, and never touches the board."""
    class Nothing:
        pass

    assert R._probe_payload(Nothing(), SESSION)["status"] == "unavailable"
    assert R._probe_payload(FakeMassive("not a mapping"), SESSION)["status"] == "unavailable"


def test_an_explicit_hook_wins_over_the_duck_typing():
    """If PR-A (or a successor) offers a real probe, it is authoritative — the
    adapter's guesses are the fallback, not the contract."""
    payload = R._probe_payload(
        FakeMassive(hook=lambda s: {"status": "final", "n": 7, "via": "hook"}), SESSION)
    assert payload == {"status": "final", "n": 7, "via": "hook"}


def test_the_digest_moves_only_when_a_close_moves():
    assert R._digest({"AAA": 1.0, "BBB": 2.0}) == R._digest({"BBB": 2.0, "AAA": 1.0})
    assert R._digest({"AAA": 1.0}) != R._digest({"AAA": 1.01})


def test_the_probe_runs_inside_the_lane_with_the_lanes_interpreter(host):
    """The outer runner is executed by /usr/bin/python3 under launchd and has no
    third-party packages at all, so the half that imports pandas has to be a
    subprocess in the checkout. Same file, different copy — see the module
    docstring."""
    sh = Sh().on("--probe-close",
                 R.ShResult(0, json.dumps({"status": "final"}), False))
    assert R.probe_close(host.lane, host.venv / "bin" / "python", {}, SESSION,
                         sh=sh)["status"] == "final"
    argv = sh.calls[0]
    assert argv[1:] == ["-m", "scripts.close_pass_host_runner",
                        "--probe-close", "--session", SESSION]
    assert argv[0] == str(host.venv / "bin" / "python")


def test_an_unparseable_probe_answer_is_an_error_not_a_go(host):
    sh = Sh().on("--probe-close", R.ShResult(1, "Traceback (most recent call last)", False))
    assert R.probe_close(host.lane, Path("py"), {}, SESSION, sh=sh)["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# The environment handed to the pass
# ─────────────────────────────────────────────────────────────────────────────
def test_the_lane_contract_is_forced_over_whatever_the_env_file_says(host, monkeypatch):
    """Three overrides, none of them a preference:

    CLOSE_PASS_SERVED_PATH="" — R2 only; the VPS owns the served copy.
    RENDER_NO_DRIP=1          — the closing-bell idiom.
    COLLECT_LANE unset        — every engine ledger writer self-gates on it, and
                                unset is how a non-ledger lane says so. Popped
                                LAST, so neither the host .env (which sets it
                                here) nor the ambient environment can smuggle it
                                back in.
    """
    monkeypatch.setenv("COLLECT_LANE", "closing-bell")
    env = R.build_env(host.primary)
    assert env["CLOSE_PASS_SERVED_PATH"] == ""
    assert env["RENDER_NO_DRIP"] == "1"
    assert "COLLECT_LANE" not in env
    assert env["R2_ENDPOINT"] == "https://example.invalid"


def test_a_secret_never_reaches_the_log(host, capsys):
    """The launchd log is a plain file on a shared host and the plist itself is
    world-readable. The lane may say HOW MANY keys it loaded and WHICH ones are
    missing; it may never say what any of them are."""
    R.build_env(host.primary)
    out = capsys.readouterr().out
    assert "s3cr3t-never-logged" not in out
    assert "4 key(s)" in out


def test_a_missing_r2_credential_is_named_before_the_twenty_minute_pass(host, capsys):
    (host.primary / ".env").write_text("R2_ENDPOINT=https://example.invalid\n",
                                       encoding="utf-8")
    R.build_env(host.primary, base={})
    warn = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert warn and "R2_ACCESS_KEY_ID" in warn[0] and "R2_SECRET_ACCESS_KEY" in warn[0]


# ─────────────────────────────────────────────────────────────────────────────
# The pass, the discard, the budget, the receipt
# ─────────────────────────────────────────────────────────────────────────────
def test_the_prefetch_writes_are_discarded_after_the_pass_not_before(host):
    """Order is the contract, exactly as close-pass.yml's own discard step pins
    it: the heal refreshes data/yahoo/*.parquet and the nightly is the sole
    writer of record, so the undo has to come after the thing that made the
    mess. A discard placed earlier reads as a fix and changes nothing."""
    assert host.run() == 0
    heal = host.sh.index_of("check_price_store_freshness --heal")
    publish = host.sh.index_of("close_pass_publish")
    checkout = host.sh.index_of("checkout -- data/")
    clean = host.sh.index_of("clean -fdq data/")
    assert heal < publish < checkout < clean


def test_a_failed_pass_still_leaves_the_lane_clean(host):
    """A failed publish leaves exactly the same dirt a successful one does, and
    the next run's `reset --hard` would carry it into whatever it does next."""
    host.sh.on("close_pass_publish", R.ShResult(3, "", False))
    assert host.run() == 1
    assert host.sh.ran("checkout -- data/") and host.sh.ran("clean -fdq data/")
    assert host.receipt()["outcome"] == "publish_failed"


def test_a_wedged_pass_is_killed_and_the_run_reports_it(host, capsys):
    """A pass still running at 17:30 ET has already missed the point of being
    early, and one holding the lock into the nightly is worse than one that
    failed. The kill is reported as an ::error and the run exits 1 — the GitHub
    backstop is still standing behind it."""
    host.sh.on("close_pass_publish", R.ShResult(124, "", True))
    assert host.run() == 1
    errors = [ln for ln in capsys.readouterr().out.splitlines() if "::error" in ln]
    assert errors and errors[0].startswith("::error title=close-pass-host::")
    assert "wall-clock budget" in errors[0]
    receipt = host.receipt()
    assert receipt["outcome"] == "publish_timeout" and receipt["publish_rc"] == 124
    # Killed or not, the lane is left clean.
    assert host.sh.ran("clean -fdq data/")


def test_a_failed_heal_degrades_coverage_and_never_the_run(host, capsys):
    """"A partial heal degrades coverage, never truth" is a property of the PASS
    (it requires TODAY's bar per name and skips-and-counts the rest), so the
    prefetch is best-effort here for the same reason it is
    `continue-on-error: true` in the workflow."""
    host.sh.on("check_price_store_freshness", R.ShResult(1, "", False))
    assert host.run() == 0
    assert host.sh.ran("close_pass_publish")
    assert host.receipt()["heal_rc"] == 1
    assert any("::warning" in ln and "prefetch" in ln
               for ln in capsys.readouterr().out.splitlines())


def test_a_dry_run_reaches_the_publisher_with_the_flag_and_skips_the_wait(host):
    """--dry-run is the acceptance path: it exercises the lock, the checkout,
    the venv and the env, and stops exactly where publishing would begin. It
    does not hold twelve minutes for closes it is not going to use."""
    assert host.run(dry_run=True) == 0
    publish = host.sh.joined()[host.sh.index_of("close_pass_publish")]
    assert publish.endswith("--dry-run")
    receipt = host.receipt()
    assert receipt["dry_run"] is True
    assert receipt["close_wait_outcome"] == "skipped_dry_run"
    assert not host.sh.ran("--probe-close")


def test_a_replay_clock_reaches_the_publisher_too(host, monkeypatch):
    """--now is the replay/acceptance lever, and it has to reach the PASS: a
    runner that replays 2026-08-14 while the publisher stamps today would
    publish today's date over last Friday's closes."""
    monkeypatch.setenv("CLOSE_PASS_HOST_NOW", "2026-08-14T20:00:00Z")
    assert host.run() == 0
    publish = host.sh.joined()[host.sh.index_of("close_pass_publish")]
    assert "--now 2026-08-14T20:00:00Z" in publish


def test_the_receipt_is_the_runs_only_durable_trace_and_carries_the_lot(host):
    """A killed run and a run that never fired leave the same evidence, which is
    nothing — so the receipt is the instrument that tells them apart, and every
    field below is one an operator would otherwise have to guess."""
    assert host.run(dry_run=False, now_fn=lambda: FIRED) == 0
    receipt = host.receipt()
    assert receipt["schema"] == R.RECEIPT_SCHEMA
    assert set(receipt) == {
        "schema", "session", "fired_at", "close_wait_outcome", "close_wait_polls",
        "publish_rc", "heal_rc", "code_sha", "code_stale", "duration_sec",
        "log_tail", "lane", "dry_run", "bootstrap", "outcome"}
    assert receipt["session"] == SESSION
    assert receipt["fired_at"].startswith("2026-08-14T20:00:05")
    assert receipt["publish_rc"] == 0 and receipt["outcome"] == "published"
    assert receipt["code_stale"] is False and len(receipt["code_sha"]) == 40
    assert receipt["log_tail"].endswith("launchd.out.log")
    assert receipt["lane"] == str(host.lane)
    # The bootstrap block is THIS file's vintage, code_sha is the lane's HEAD.
    # Different questions — the installer freezes one and origin/main moves the
    # other — so a receipt carrying only one cannot show drift at all.
    assert receipt["bootstrap"]["file_sha256"] != receipt["code_sha"]


def test_the_bootstrap_and_the_lane_vintage_can_never_be_read_as_the_same_thing(host):
    """THE NAMES ARE THE FIX, not a cosmetic.

    The receipt this replaces carried ``runner_sha: "cde03d71de97"`` beside
    ``code_sha: "af416e4a1066..."`` — a sha256 PREFIX and a git COMMIT, rendered
    as two indistinguishable hex strings, which is how a snapshot three days
    stale produced a receipt that read as perfect (2026-08-18, PR #5862). So:
    every content digest inside the block says ``file_sha256`` and carries its
    full 64 hex; the git commit stays a 40-hex ``code_sha`` outside it; and the
    two never share a namespace.
    """
    assert host.run() == 0
    receipt = host.receipt()
    boot = receipt["bootstrap"]
    assert len(receipt["code_sha"]) == 40
    for key in ("file_sha256", "installed_file_sha256", "main_file_sha256"):
        assert key in boot, key
        assert boot[key] == "" or len(boot[key]) == 64, (key, boot[key])
    # No bare ``*_sha`` key may exist inside the block, and code_sha may not leak
    # into it: either would restore the exact ambiguity this replaced.
    assert not [k for k in boot if k.endswith("_sha")]
    assert "code_sha" not in boot
    # ...and the identity is answerable without git: the executing file's own
    # bytes and mtime, which is what a stale snapshot has and a fresh one does not.
    assert boot["path"].endswith(R.RUNNER_BASENAME)
    assert dt.datetime.fromisoformat(boot["mtime"]).tzinfo is not None


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap drift — "merged" is not "deployed", and the receipt must know it
#
# THE WIRING IS WHAT IS PINNED HERE, not a helper. Every assertion below runs the
# real ``R.run`` and reads the real receipt or the real stdout, because the defect
# this closes was a CALL SITE defect: ``prepare_lane`` rendered a timeout as
# ``repr('')`` while every helper it used behaved correctly, and a helper-only
# test would have stayed green through it.
# ─────────────────────────────────────────────────────────────────────────────
def _drift_the_lane(host, *, behind: int = 2) -> None:
    """origin/main has moved past the executing bootstrap. Scripts the two git
    metadata answers the vintage walk asks for, and nothing else."""
    (host.lane / "scripts" / R.RUNNER_BASENAME).write_bytes(
        b"# origin/main has moved on since this snapshot was installed\n")
    mine = "b" * 40
    newer = [f"{i:040d}" for i in range(1, behind + 1)]
    host.sh.on("hash-object", R.ShResult(0, mine + "\n", False))
    lines = []
    for i, blob in enumerate(newer + [mine]):
        lines.append(f"{i:040d}")
        lines.append(f":100755 100755 {'0' * 40} {blob} M\tscripts/{R.RUNNER_BASENAME}")
    host.sh.on("--raw", R.ShResult(0, "\n".join(lines) + "\n", False))


def test_a_bootstrap_that_matches_origin_main_costs_no_git_at_all(host, capsys):
    """The healthy path is the common path and must be free.

    The reference is a file the lane's own ``reset --hard origin/main`` already
    put on disk, so agreement is one read and a digest compare — no subprocess.
    The vintage walk is diagnosis and is paid ONLY once a mismatch is proven,
    which is what keeps this affordable inside a 16:00 ET wait window.
    """
    assert host.run() == 0
    boot = host.receipt()["bootstrap"]
    assert boot["matches_main"] is True and boot["commits_behind"] == 0
    assert boot["file_sha256"] == boot["main_file_sha256"]
    assert not host.sh.ran("hash-object")
    assert not host.sh.ran("--raw")
    out = capsys.readouterr().out
    assert "no drift" in out
    assert "BOOTSTRAP DRIFT" not in out


def test_a_drifted_bootstrap_fails_loudly_names_the_remedy_and_still_publishes(
        host, capsys):
    """DISCLOSED, NEVER HEALED — and never at the cost of the session.

    Self-updating would defeat the freeze the installer exists to provide, so the
    entire remedy this lane owns is an annotation carrying the exact command. A
    drifted snapshot that can still publish a board must still publish it: losing
    the evening would be a worse outcome than the stale plumbing that caused it.
    """
    _drift_the_lane(host, behind=2)
    assert host.run() == 0                       # the board is NOT sacrificed
    receipt = host.receipt()
    assert receipt["outcome"] == "published" and receipt["publish_rc"] == 0
    boot = receipt["bootstrap"]
    assert boot["matches_main"] is False and boot["commits_behind"] == 2
    assert boot["file_sha256"] != boot["main_file_sha256"]

    errors = [ln for ln in capsys.readouterr().out.splitlines()
              if ln.startswith("::error")]
    drift = [ln for ln in errors if "BOOTSTRAP DRIFT" in ln]
    assert len(drift) == 1, errors
    line = drift[0]
    # The annotation must start the line, or GitHub drops it (house guard
    # tests/test_gh_annotation_line_start.py) and launchd's log reads as prose.
    assert line.startswith("::error title=close-pass-host::")
    # THE WIRING: the emitted line quotes the receipt's own numbers. A message
    # built from anything else can drift from the record it is explaining.
    assert boot["file_sha256"][:12] in line
    assert boot["main_file_sha256"][:12] in line
    assert "2 commit(s) behind" in line
    assert "bash scripts/install_closepass_launchd.sh" in line
    assert "MERGING DOES NOT DEPLOY THIS FILE" in line


def test_an_unknown_distance_is_reported_as_unknown_and_never_as_zero(host, capsys):
    """A vintage the walk cannot place is ``None``, not 0.

    ``commits_behind: 0`` is the same value a CLEAN bootstrap carries. A failed
    walk that answered 0 would render as "up to date" in every consumer of this
    receipt while the digests beside it disagreed.
    """
    (host.lane / "scripts" / R.RUNNER_BASENAME).write_bytes(b"# moved on\n")
    host.sh.on("hash-object", R.ShResult(1, "", False))
    assert host.run() == 0
    boot = host.receipt()["bootstrap"]
    assert boot["matches_main"] is False and boot["commits_behind"] is None
    assert "an unknown distance behind" in capsys.readouterr().out


def test_a_matching_bootstrap_is_not_certified_against_a_STALE_reference(host, capsys):
    """Fail-closed on the CLAIM, exactly as ``code_stale`` already is.

    When the fetch fails the lane holds YESTERDAY's origin/main, so
    "byte-identical to the reference" is not "byte-identical to main". A detector
    that certified here would go quiet precisely on the nights it cannot see —
    the blind kind. It reports UNVERIFIED, which is not a pass and not a failure.
    """
    host.sh.on("fetch origin main", R.ShResult(1, "network down", False))
    assert host.run() == 0
    boot = host.receipt()["bootstrap"]
    assert host.receipt()["code_stale"] is True
    assert boot["matches_main"] is None          # NOT True
    assert boot["file_sha256"] == boot["main_file_sha256"]
    out = capsys.readouterr().out
    assert "::warning" in out and "UNVERIFIED" in out
    assert "BOOTSTRAP DRIFT" not in out


def test_an_unprepared_lane_still_records_which_bootstrap_refused(
        host, capsys, no_backoff):
    """The 2026-08-17 receipt could not answer this, and the answer mattered.

    That evening refused at ``lane_unprepared`` and its receipt named a lane it
    never prepared and a bootstrap it never identified — while a stale snapshot
    was a live candidate cause of the refusal. Identity is therefore filled at
    receipt construction, before anything can fail, and the fail-closed refusal
    itself is unchanged: rc 1, outcome ``lane_unprepared``, nothing published.
    """
    host.sh.on("rev-parse --git-dir", R.ShResult(124, "", True))
    assert host.run() == 1
    receipt = host.receipt(session="no-session")
    assert receipt["outcome"] == "lane_unprepared"
    assert not host.sh.ran("close_pass_publish")
    boot = receipt["bootstrap"]
    assert len(boot["file_sha256"]) == 64 and boot["mtime"]
    assert boot["path"].endswith(R.RUNNER_BASENAME)
    # Nothing was compared, so nothing is claimed — and it says which it is.
    assert boot["matches_main"] is None and boot["main_file_sha256"] == ""
    out = capsys.readouterr().out
    assert "UNVERIFIED" in out
    # ...and #5862's timeout-aware detail is still there, unweakened.
    assert "timed out after 30s" in out


def test_the_runner_never_deploys_itself(host):
    """The freeze is the feature; a self-updating bootstrap would delete it.

    ``install_closepass_launchd.sh`` copies this file ON PURPOSE so a mid-day
    push to main cannot change what the clock executes mid-session. The drift
    check exists to DISCLOSE the cost of that choice, never to quietly undo it.
    """
    assert "shutil" not in ast.unparse(ast.parse(RUNNER_SRC))
    # It may READ the installed snapshot to identify it; it may not write there.
    # Every write site in the file, by line — the receipt and the requirements
    # stamp — and neither may name this file or the installed path.
    writes = [ln for ln in RUNNER_SRC.splitlines()
              if "write_text(" in ln or "write_bytes(" in ln]
    assert writes, "the receipt writer vanished — this guard would pass vacuously"
    for line in writes:
        assert R.RUNNER_BASENAME not in line and "installed" not in line, line


def test_the_receipt_is_local_telemetry_and_never_touches_data_or_git(host):
    """G0.2 and DNR:KILL-INTRADAY-CHRONICLE: this lane advances no ledger. The
    receipt lives under Application Support precisely so it can never be
    mistaken for one."""
    assert host.run() == 0
    written = host.support / "runs" / f"{SESSION}.json"
    assert written.is_file()
    assert "Application Support" in str(R.SUPPORT_DEFAULT)
    assert not (host.lane / "data").exists()
    code = ast.unparse(ast.parse(RUNNER_SRC))
    # The only data/ paths this file may name are the two discard commands.
    assert code.count("'data/'") == 2, code.count("'data/'")
    # And no git verb that could reach main exists anywhere in it. The lane
    # holds no credential for a push and would have nothing to say if it did:
    # the nightly is the sole advancer of every forward ledger. ('add' is not
    # on this list because the file legitimately runs `worktree add`; the verbs
    # below have no such innocent form.)
    for verb in ("'commit'", "'push'", "'tag'", "'stash'"):
        assert verb not in code, verb


def test_receipts_do_not_accumulate_forever(host, tmp_path):
    runs = host.support / "runs"
    runs.mkdir(parents=True)
    for i in range(R.RECEIPT_KEEP + 20):
        (runs / f"2020-01-{i:03d}.json").write_text("{}", encoding="utf-8")
    R.write_receipt(host.support, {"session": SESSION})
    assert len(list(runs.glob("*.json"))) == R.RECEIPT_KEEP


# ─────────────────────────────────────────────────────────────────────────────
# The venv
# ─────────────────────────────────────────────────────────────────────────────
def test_pip_runs_only_when_requirements_actually_moved(host):
    """Cold install is minutes; this lane has a twelve-minute window it would
    rather spend waiting for the closes. Same hash, no pip at all."""
    sh = Sh()
    assert R.ensure_venv(host.lane, venv=host.venv, support=host.support, sh=sh)
    assert sh.ran("pip install --quiet -r")           # first time: the file is new
    again = Sh()
    R.ensure_venv(host.lane, venv=host.venv, support=host.support, sh=again)
    assert not again.ran("pip install"), again.joined()

    (host.lane / "requirements.txt").write_text("pandas==2.9.9\n", encoding="utf-8")
    moved = Sh()
    R.ensure_venv(host.lane, venv=host.venv, support=host.support, sh=moved)
    assert moved.ran("pip install --quiet -r")


def test_a_failed_pip_does_not_latch_a_lie(host):
    """The stamp is written only after a SUCCESSFUL install, so a failure
    retries next run instead of recording an install that never happened."""
    sh = Sh().on("pip install --quiet -r", R.ShResult(1, "network down", False))
    R.ensure_venv(host.lane, venv=host.venv, support=host.support, sh=sh)
    assert not (host.support / "requirements.sha256").exists()


# ─────────────────────────────────────────────────────────────────────────────
# House laws
# ─────────────────────────────────────────────────────────────────────────────
def test_every_annotation_is_a_bare_print_that_starts_the_line():
    """The house law (tests/test_gh_annotation_line_start.py, #3587's sweep of 69
    sites): through a logger an annotation becomes `WARNING ::warning …` and is
    silently dropped. This lane logs to a launchd file rather than an Actions
    summary, but the form is the same and the failure would be the same — an
    alarm that reviews as an alarm, runs clean, and produces nothing."""
    tree = ast.parse(RUNNER_SRC)
    seen = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        literals = [n.value for n in ast.walk(node)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        if not any(tag in "".join(literals)
                   for tag in ("::warning", "::notice", "::error")):
            continue
        seen += 1
        assert getattr(node.func, "id", None) == "print", ast.dump(node)[:120]
        assert literals[0].startswith("::"), literals[0]
        assert any(kw.arg == "flush" for kw in node.keywords)
    assert seen >= 3


def test_the_outer_runner_imports_nothing_outside_the_stdlib():
    """It is executed by the system /usr/bin/python3 under launchd, which has no
    site-packages and no repo on sys.path. A pandas import at module scope would
    make the primary clock fail at import — silently, because a launchd job that
    dies has no build log anybody reads."""
    stdlib = {"argparse", "datetime", "fcntl", "hashlib", "json", "os", "signal",
              "subprocess", "sys", "time", "pathlib", "typing", "zoneinfo",
              "__future__"}
    for node in ast.parse(RUNNER_SRC).body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in stdlib, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] in stdlib, node.module
    # The ONE repo import in the file is inside the probe half, which runs in
    # the lane with the lane's interpreter — never at module scope.
    probe = RUNNER_SRC.split("def probe_close_main(")[1]
    assert "from engine.close_pass import massive_close" in probe


def test_the_runner_never_dispatches_or_cancels_anything():
    """A host clock that could dispatch a workflow would be a second dispatcher
    (the fleet has one: scripts/prophet_rescue.py, bounded to two attempts a
    night), and a cancel is invisible to every staleness instrument we own —
    a killed bake and a bake that never fired leave the same trace."""
    code = ast.unparse(ast.parse(RUNNER_SRC))
    for banned in ("gh workflow run", "workflow_dispatch", "run cancel",
                   "force-cancel", "actions/runs"):
        assert banned not in code, banned


# ─────────────────────────────────────────────────────────────────────────────
# Probe hardening — 2026-08-17 W-ACCEPT day 1
#
# The launchd clock fired dead on time (20:00:06Z = 16:00 ET) and the session
# still lost its board: `git rev-parse --git-dir` blocked past GIT_TIMEOUT_S
# while the Studio ran the CN asia job plus a render, `_sh` returned rc=124 with
# EMPTY captured output, and prepare_lane rendered that as
#   primary checkout unreadable: ''
# — a message indistinguishable from a corrupt repository, for what was only a
# busy disk. Probing the same command by hand afterwards answered in 0.018s.
# ─────────────────────────────────────────────────────────────────────────────
class FlakySh(Sh):
    """Answers a needle differently on each successive call.

    The base double is needle->one-result, which cannot express "times out, then
    succeeds" — the exact shape a retry has to be tested against.
    """

    def __init__(self, needle: str, results: list) -> None:
        super().__init__()
        self._needle = needle
        self._queue = list(results)
        self.probe_calls = 0

    def __call__(self, argv, **kw) -> R.ShResult:
        argv = [str(a) for a in argv]
        joined = " ".join(argv)
        if self._needle in joined:
            self.probe_calls += 1
            self.calls.append(argv)
            if self._queue:
                return self._queue.pop(0)
            return R.ShResult(0, "", False)
        return super().__call__(argv, **kw)


@pytest.fixture()
def no_backoff(monkeypatch):
    """Backoff is real seconds in production and dead weight in a test."""
    monkeypatch.setattr(R.time, "sleep", lambda _s: None)


def test_a_timed_out_probe_is_retried_instead_of_costing_the_session(host, no_backoff):
    """A contention spike must not cost an acceptance day.

    One stalled metadata read is not evidence about the repository, so the run
    asks again rather than refusing on it.
    """
    sh = FlakySh("rev-parse --git-dir", [
        R.ShResult(124, "", True),          # the 2026-08-17 stall
        R.ShResult(0, ".git\n", False),     # the box frees up
    ])
    sh.on("rev-parse HEAD", R.ShResult(0, "d" * 40 + "\n", False))
    state = R.prepare_lane(host.primary, host.lane, sh=sh)
    assert state["ok"], state["detail"]
    assert sh.probe_calls == 2


def test_a_deterministic_probe_failure_is_not_retried(host):
    """Retrying a real fault burns the wait window for nothing.

    A corrupt repo, a missing path and a TCC denial all answer identically on
    every attempt, so only `timed_out` earns a second look.
    """
    sh = FlakySh("rev-parse --git-dir", [
        R.ShResult(1, "fatal: not a git repository", False),
        R.ShResult(0, ".git\n", False),     # never reached
    ])
    state = R.prepare_lane(host.primary, host.lane, sh=sh)
    assert not state["ok"]
    assert sh.probe_calls == 1
    assert "not a git repository" in state["detail"]


def test_an_exhausted_probe_names_the_timeout_rather_than_an_empty_string(host, no_backoff):
    """The regression this hardening exists for, pinned at the WIRING.

    Testing the retry helper alone would still pass while prepare_lane kept
    formatting `repr('')` — which is precisely what shipped. So assert on the
    message prepare_lane actually emits.
    """
    sh = FlakySh("rev-parse --git-dir",
                 [R.ShResult(124, "", True)] * R.GIT_PROBE_ATTEMPTS)
    state = R.prepare_lane(host.primary, host.lane, sh=sh)
    assert not state["ok"]
    assert sh.probe_calls == R.GIT_PROBE_ATTEMPTS
    assert "timed out" in state["detail"]
    assert "host contention" in state["detail"]
    assert "unreadable: ''" not in state["detail"]


def test_the_probe_timeout_is_short_enough_to_retry_inside_the_wait_window(host):
    """Budget, not taste: prepare_lane runs AFTER the 16:00 ET fire and must be
    done before WAIT_DEADLINE_ET (16:12). Three attempts at GIT_TIMEOUT_S would
    be 9 minutes and blow the deadline the retry is meant to protect."""
    worst = R.GIT_PROBE_TIMEOUT_S * R.GIT_PROBE_ATTEMPTS + sum(R.GIT_PROBE_BACKOFF_S)
    assert worst < 3 * 60
    assert R.GIT_PROBE_TIMEOUT_S < R.GIT_TIMEOUT_S
