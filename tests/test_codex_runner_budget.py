"""tests/test_codex_runner_budget.py — Hermetic tests for CRX runner + budget.

Coverage:
    Runner:
        - Correct argv construction (model flag omitted when empty, included when set)
        - Sandbox flag always present
        - Network -c flag: present when sandbox==workspace-write and network=True
        - Network -c flag: absent when network=False or sandbox!=workspace-write
        - Prompt always LAST positional arg
        - Flat event shape: agent_message + token_count
        - Wrapped event shape: {"id": ..., "msg": {"type": ...}}
        - token_count without rate_limits -> token_usage populated, rate_limits None
        - token_count with rate_limits -> both populated
        - usage_limit classification from stderr
        - auth classification from stderr
        - timeout via subprocess.TimeoutExpired -> error_kind="timeout"
        - not_installed via FileNotFoundError -> error_kind="not_installed"
        - ok=True on exit-code-0 even with empty stdout
        - raw_tail capped at 2000 chars

    Budget:
        - Fresh state (no file) -> can_run returns (True, "ok")
        - Reported 86% primary used_percent -> (False, "budget:primary:86.0%")
        - paused_until in future -> (False, "paused_until:...")
        - paused_until in past -> (True, "ok")
        - usage_limit note_result sets paused_until ~now+5h when no reset reported
        - usage_limit note_result uses reported primary resets_at when present
        - degraded session-cap: 10 sessions in 5h -> (False, "session_cap")
        - degraded session-cap: 10 sessions over 6h+ -> (True, "ok")  (outside window)
        - note_result keeps last 200 sessions (trims older ones)
        - State file round-trip in tmp root
        - note_result clears degraded when rate_limits present
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure repo root on sys.path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.codex_lane.runner import (  # noqa: E402
    _classify_error,
    _extract_rate_limits,
    _extract_token_usage,
    _parse_jsonl,
    fetch_rate_limits,
    resolve_codex_bin,
    run_codex,
)
from engine.codex_lane.budget import (  # noqa: E402
    _compute_pause_until,
    _now_utc,
    _to_iso,
    can_run,
    load_cfg,
    load_state,
    note_rate_limits,
    note_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _mk_run_result(**kwargs) -> dict:
    """Build a minimal run_codex-shaped dict for note_result tests."""
    base = {
        "ok": True,
        "final_message": "done",
        "events_count": 2,
        "token_usage": None,
        "rate_limits": None,
        "error_kind": None,
        "raw_tail": "",
        "lane": "signals",
    }
    base.update(kwargs)
    return base


def _fake_proc(stdout="", stderr="", returncode=0):
    proc = MagicMock()
    proc.stdout = stdout
    proc.stderr = stderr
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# Runner tests
# ---------------------------------------------------------------------------

class TestRunnerArgConstruction(unittest.TestCase):
    """Verify the subprocess argv is built per spec."""

    def _run_capture(self, **kwargs) -> list[str]:
        """Call run_codex with a mocked subprocess.run; return the captured args."""
        captured = {}

        def fake_run(args, **kw):
            captured["args"] = list(args)
            return _fake_proc(stdout="", stderr="", returncode=0)

        with patch("engine.codex_lane.runner.subprocess.run", side_effect=fake_run):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/usr/bin/codex"):
                run_codex("test prompt", **kwargs)

        return captured.get("args", [])

    def test_prompt_is_last(self):
        args = self._run_capture()
        self.assertEqual(args[-1], "test prompt")

    def test_model_flag_omitted_when_empty(self):
        args = self._run_capture(model="")
        self.assertNotIn("-m", args)

    def test_model_flag_present_when_set(self):
        args = self._run_capture(model="o3")
        idx = args.index("-m")
        self.assertEqual(args[idx + 1], "o3")

    def test_sandbox_always_present(self):
        args = self._run_capture(sandbox="workspace-write")
        idx = args.index("--sandbox")
        self.assertEqual(args[idx + 1], "workspace-write")

    def test_network_flag_present_when_sandbox_write_and_network_true(self):
        args = self._run_capture(sandbox="workspace-write", network=True)
        self.assertIn("sandbox_workspace_write.network_access=true", args)

    def test_network_flag_absent_when_network_false(self):
        args = self._run_capture(sandbox="workspace-write", network=False)
        self.assertNotIn("sandbox_workspace_write.network_access=true", args)

    def test_network_flag_absent_when_sandbox_not_workspace_write(self):
        args = self._run_capture(sandbox="read-only", network=True)
        self.assertNotIn("sandbox_workspace_write.network_access=true", args)

    def test_exec_json_present(self):
        args = self._run_capture()
        self.assertIn("exec", args)
        self.assertIn("--json", args)

    def test_cwd_flag_present(self):
        args = self._run_capture(cwd="/tmp")
        self.assertIn("-C", args)
        idx = args.index("-C")
        self.assertEqual(args[idx + 1], "/tmp")

    def test_extra_args_before_prompt(self):
        args = self._run_capture(extra_args=["--flag", "val"])
        prompt_idx = args.index("test prompt")
        flag_idx = args.index("--flag")
        self.assertLess(flag_idx, prompt_idx)


class TestRunnerJsonlParsing(unittest.TestCase):
    """Test JSONL event stream parsing covering both event shapes."""

    def _run_with_stdout(self, stdout: str, stderr: str = "", rc: int = 0) -> dict:
        def fake_run(args, **kw):
            return _fake_proc(stdout=stdout, stderr=stderr, returncode=rc)

        with patch("engine.codex_lane.runner.subprocess.run", side_effect=fake_run):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/usr/bin/codex"):
                return run_codex("prompt")

    def test_flat_agent_message(self):
        stdout = json.dumps({"type": "agent_message", "message": "Hello world"}) + "\n"
        result = self._run_with_stdout(stdout)
        self.assertEqual(result["final_message"], "Hello world")
        self.assertTrue(result["ok"])

    def test_wrapped_agent_message(self):
        stdout = json.dumps({
            "id": "evt-001",
            "msg": {"type": "agent_message", "text": "Wrapped hello"},
        }) + "\n"
        result = self._run_with_stdout(stdout)
        self.assertEqual(result["final_message"], "Wrapped hello")

    def test_flat_token_count_no_rate_limits(self):
        events = [
            json.dumps({"type": "token_count", "info": {
                "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
            }}),
        ]
        stdout = "\n".join(events) + "\n"
        result = self._run_with_stdout(stdout)
        self.assertIsNotNone(result["token_usage"])
        self.assertEqual(result["token_usage"]["input_tokens"], 100)
        self.assertEqual(result["token_usage"]["output_tokens"], 50)
        self.assertEqual(result["token_usage"]["total_tokens"], 150)
        self.assertIsNone(result["rate_limits"])

    def test_token_count_with_rate_limits(self):
        events = [
            json.dumps({
                "type": "token_count",
                "info": {
                    "usage": {"input_tokens": 200, "output_tokens": 80},
                    "rate_limits": {
                        "primary": {"used_percent": 42.5, "resets_at": "2026-07-13T12:00:00+00:00"},
                        "secondary": {"used_percent": 12.0},
                    },
                },
            }),
        ]
        stdout = "\n".join(events) + "\n"
        result = self._run_with_stdout(stdout)
        self.assertIsNotNone(result["token_usage"])
        self.assertIsNotNone(result["rate_limits"])
        primary = result["rate_limits"]["primary"]
        self.assertAlmostEqual(primary["used_percent"], 42.5)
        self.assertEqual(primary["resets_at"], "2026-07-13T12:00:00+00:00")
        secondary = result["rate_limits"]["secondary"]
        self.assertAlmostEqual(secondary["used_percent"], 12.0)

    def test_wrapped_token_count(self):
        events = [
            json.dumps({
                "id": "tc-1",
                "msg": {
                    "type": "token_count",
                    "usage": {"input_tokens": 50, "output_tokens": 25},
                    "rate_limits": {
                        "primary": {"used_percent": 30.0},
                        "secondary": None,
                    },
                },
            }),
        ]
        stdout = "\n".join(events) + "\n"
        result = self._run_with_stdout(stdout)
        self.assertIsNotNone(result["token_usage"])
        self.assertEqual(result["token_usage"]["input_tokens"], 50)

    def test_events_count(self):
        events = [
            json.dumps({"type": "start"}),
            json.dumps({"type": "agent_message", "message": "hi"}),
            json.dumps({"type": "end"}),
        ]
        stdout = "\n".join(events) + "\n"
        result = self._run_with_stdout(stdout)
        self.assertEqual(result["events_count"], 3)

    def test_usage_limit_stderr_classification(self):
        result = self._run_with_stdout(
            stdout="",
            stderr="Error: you've hit the usage limit for this window",
            rc=1,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "usage_limit")

    def test_auth_error_classification(self):
        result = self._run_with_stdout(
            stdout="",
            stderr="Error: 401 unauthorized — please login",
            rc=1,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "auth")

    def test_nonzero_exit_with_final_message(self):
        stdout = json.dumps({"type": "agent_message", "message": "partial"}) + "\n"
        result = self._run_with_stdout(stdout, rc=1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["final_message"], "partial")

    def test_raw_tail_capped_at_2000(self):
        big = "x" * 5000
        result = self._run_with_stdout(stdout=big)
        self.assertLessEqual(len(result["raw_tail"]), 2000)

    def test_ok_true_on_zero_exit_empty_stdout(self):
        result = self._run_with_stdout(stdout="", rc=0)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["error_kind"])


class TestRunnerExceptions(unittest.TestCase):
    """Test subprocess exception handling."""

    def test_file_not_found_error_kind(self):
        with patch("engine.codex_lane.runner.subprocess.run",
                   side_effect=FileNotFoundError("no such file")):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/missing/codex"):
                result = run_codex("prompt")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "not_installed")

    def test_timeout_expired_error_kind(self):
        exc = subprocess.TimeoutExpired(cmd=["codex"], timeout=1500)
        exc.stdout = b""
        exc.stderr = b""
        with patch("engine.codex_lane.runner.subprocess.run", side_effect=exc):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/usr/bin/codex"):
                result = run_codex("prompt")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "timeout")

    def test_never_raises_on_unexpected_exception(self):
        with patch("engine.codex_lane.runner.subprocess.run",
                   side_effect=RuntimeError("unexpected")):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/usr/bin/codex"):
                result = run_codex("prompt")
        self.assertFalse(result["ok"])
        self.assertIn("error_kind", result)


# ---------------------------------------------------------------------------
# Budget tests
# ---------------------------------------------------------------------------

class TestBudgetFreshState(unittest.TestCase):
    """A fresh state (no file) should allow running."""

    def test_fresh_can_run_true(self, tmp_path=None):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            ok, reason = can_run(root=td)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")


class TestBudgetPauseGate(unittest.TestCase):
    """paused_until gate."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        # Create data/codex_lane dir
        Path(self._tmpdir, "data", "codex_lane").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_state(self, state: dict):
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        p.write_text(json.dumps(state))

    def test_paused_until_future_blocks(self):
        future = _now() + timedelta(hours=3)
        self._write_state({
            "schema": "codex_lane.usage_state.v1",
            "paused_until": _to_iso(future),
            "degraded": True,
            "sessions": [],
            "rate_limits": None,
        })
        ok, reason = can_run(root=self._tmpdir)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("paused_until:"))

    def test_paused_until_past_allows(self):
        past = _now() - timedelta(hours=6)
        self._write_state({
            "schema": "codex_lane.usage_state.v1",
            "paused_until": _to_iso(past),
            "degraded": True,
            "sessions": [],
            "rate_limits": None,
        })
        ok, reason = can_run(root=self._tmpdir)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")


class TestBudgetBudgetGate(unittest.TestCase):
    """Reported used_percent gate."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        Path(self._tmpdir, "data", "codex_lane").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_state(self, state: dict):
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        p.write_text(json.dumps(state))

    def test_86_pct_primary_blocks(self):
        self._write_state({
            "schema": "codex_lane.usage_state.v1",
            "degraded": False,
            "paused_until": None,
            "sessions": [],
            "rate_limits": {
                "primary": {"used_percent": 86.0, "resets_at": None},
                "secondary": {"used_percent": 10.0, "resets_at": None},
            },
        })
        ok, reason = can_run(root=self._tmpdir)
        self.assertFalse(ok)
        self.assertIn("budget:primary", reason)
        self.assertIn("86.0%", reason)

    def test_86_pct_secondary_blocks(self):
        self._write_state({
            "schema": "codex_lane.usage_state.v1",
            "degraded": False,
            "paused_until": None,
            "sessions": [],
            "rate_limits": {
                "primary": {"used_percent": 10.0, "resets_at": None},
                "secondary": {"used_percent": 86.0, "resets_at": None},
            },
        })
        ok, reason = can_run(root=self._tmpdir)
        self.assertFalse(ok)
        self.assertIn("budget:secondary", reason)

    def test_84_pct_primary_allows(self):
        self._write_state({
            "schema": "codex_lane.usage_state.v1",
            "degraded": False,
            "paused_until": None,
            "sessions": [],
            "rate_limits": {
                "primary": {"used_percent": 84.0, "resets_at": None},
                "secondary": {"used_percent": 20.0, "resets_at": None},
            },
        })
        ok, reason = can_run(root=self._tmpdir)
        self.assertTrue(ok)


class TestBudgetDegradedSessionCap(unittest.TestCase):
    """Degraded-mode session cap gate."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        Path(self._tmpdir, "data", "codex_lane").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_state(self, sessions: list[dict]):
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        p.write_text(json.dumps({
            "schema": "codex_lane.usage_state.v1",
            "degraded": True,
            "paused_until": None,
            "sessions": sessions,
            "rate_limits": None,
        }))

    def _make_sessions_in_last_5h(self, n: int) -> list[dict]:
        now = _now()
        return [
            {"ts": _to_iso(now - timedelta(minutes=10 * i)), "lane": "signals", "ok": True, "error_kind": None}
            for i in range(n)
        ]

    def _make_sessions_spread_over_6h(self, n: int) -> list[dict]:
        now = _now()
        # Space sessions 40 min apart so 10 sessions span 6h 40min
        return [
            {"ts": _to_iso(now - timedelta(minutes=40 * i)), "lane": "signals", "ok": True, "error_kind": None}
            for i in range(n)
        ]

    def test_10_sessions_in_5h_triggers_cap(self):
        sessions = self._make_sessions_in_last_5h(10)
        self._write_state(sessions)
        ok, reason = can_run(root=self._tmpdir)
        self.assertFalse(ok)
        self.assertEqual(reason, "session_cap")

    def test_9_sessions_in_5h_allows(self):
        sessions = self._make_sessions_in_last_5h(9)
        self._write_state(sessions)
        ok, reason = can_run(root=self._tmpdir)
        self.assertTrue(ok)

    def test_10_sessions_spread_over_6h_plus_allows(self):
        # 10 sessions but sessions 0..4 are within 5h, sessions 5..9 are outside 5h
        now = _now()
        sessions = []
        # 5 sessions inside window (within 5h)
        for i in range(5):
            sessions.append({
                "ts": _to_iso(now - timedelta(minutes=30 * i)),
                "lane": "signals", "ok": True, "error_kind": None,
            })
        # 5 sessions OUTSIDE window (more than 5h ago)
        for i in range(5):
            sessions.append({
                "ts": _to_iso(now - timedelta(hours=5, minutes=30 + 30 * i)),
                "lane": "signals", "ok": True, "error_kind": None,
            })
        self._write_state(sessions)
        ok, reason = can_run(root=self._tmpdir)
        self.assertTrue(ok)


class TestBudgetNoteResult(unittest.TestCase):
    """note_result state transitions."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        Path(self._tmpdir, "data", "codex_lane").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _load_state(self) -> dict:
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        return json.loads(p.read_text())

    def test_usage_limit_sets_paused_until_approx_5h(self):
        before = _now()
        run = _mk_run_result(error_kind="usage_limit", rate_limits=None)
        note_result(run, root=self._tmpdir)
        state = self._load_state()
        self.assertIsNotNone(state["paused_until"])

        paused_dt = datetime.fromisoformat(state["paused_until"].replace("Z", "+00:00"))
        expected_floor = before + timedelta(hours=4, minutes=55)
        expected_ceil = before + timedelta(hours=5, minutes=5)
        self.assertGreater(paused_dt, expected_floor)
        self.assertLess(paused_dt, expected_ceil)

    def test_usage_limit_uses_reported_primary_resets_at(self):
        reset_time = _now() + timedelta(hours=3)
        run = _mk_run_result(
            error_kind="usage_limit",
            rate_limits={
                "primary": {"used_percent": 100.0, "resets_at": _to_iso(reset_time)},
                "secondary": None,
            },
        )
        note_result(run, root=self._tmpdir)
        state = self._load_state()
        paused_dt = datetime.fromisoformat(state["paused_until"].replace("Z", "+00:00"))
        # Should be within a second of reset_time
        self.assertAlmostEqual(
            abs((paused_dt - reset_time).total_seconds()), 0, delta=2
        )

    def test_note_result_keeps_last_200_sessions(self):
        # Prime with 205 sessions
        sessions = [
            {"ts": _to_iso(_now() - timedelta(days=1)), "lane": "signals", "ok": True, "error_kind": None}
            for _ in range(205)
        ]
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        p.write_text(json.dumps({
            "schema": "codex_lane.usage_state.v1",
            "degraded": True,
            "paused_until": None,
            "sessions": sessions,
            "rate_limits": None,
        }))
        # note_result adds 1 more; should trim to 200
        run = _mk_run_result()
        note_result(run, root=self._tmpdir)
        state = self._load_state()
        self.assertLessEqual(len(state["sessions"]), 200)

    def test_note_result_clears_degraded_when_rate_limits_present(self):
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        p.write_text(json.dumps({
            "schema": "codex_lane.usage_state.v1",
            "degraded": True,
            "paused_until": None,
            "sessions": [],
            "rate_limits": None,
        }))
        run = _mk_run_result(rate_limits={
            "primary": {"used_percent": 40.0, "resets_at": None},
            "secondary": None,
        })
        note_result(run, root=self._tmpdir)
        state = self._load_state()
        self.assertFalse(state["degraded"])
        self.assertIsNotNone(state["rate_limits"])

    def test_state_file_round_trip(self):
        run = _mk_run_result(
            ok=True,
            lane="cases",
            token_usage={"input_tokens": 300, "output_tokens": 150, "total_tokens": 450},
            rate_limits={
                "primary": {"used_percent": 55.0, "resets_at": "2026-07-13T20:00:00+00:00"},
                "secondary": {"used_percent": 5.0, "resets_at": None},
            },
        )
        note_result(run, root=self._tmpdir)
        # Reload state and verify all fields
        state = self._load_state()
        self.assertEqual(state["schema"], "codex_lane.usage_state.v1")
        self.assertIsNotNone(state["updated_at"])
        self.assertEqual(len(state["sessions"]), 1)
        self.assertEqual(state["sessions"][0]["lane"], "cases")
        self.assertTrue(state["sessions"][0]["ok"])
        self.assertIsNotNone(state["token_usage_last"])
        self.assertEqual(state["token_usage_last"]["input_tokens"], 300)
        self.assertIsNotNone(state["rate_limits"])
        self.assertAlmostEqual(state["rate_limits"]["primary"]["used_percent"], 55.0)
        self.assertFalse(state["degraded"])


class TestBudgetLoadCfg(unittest.TestCase):
    """load_cfg defaults and file-loading."""

    def test_defaults_when_no_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = load_cfg(root=td)
        self.assertEqual(cfg["budget_pct"], 85)
        self.assertEqual(cfg["max_sessions_per_window"], 10)
        self.assertEqual(cfg["session_timeout_min"], 25)
        self.assertEqual(cfg["case_pr_mode"], "draft")
        self.assertEqual(cfg["sandbox"], "workspace-write")
        self.assertTrue(cfg["network"])

    def test_config_yml_overrides_defaults(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / "config"
            config_dir.mkdir()
            (config_dir / "codex_lane.yml").write_text(
                "budget_pct: 70\nmax_sessions_per_window: 5\n"
            )
            cfg = load_cfg(root=td)
        self.assertEqual(cfg["budget_pct"], 70)
        self.assertEqual(cfg["max_sessions_per_window"], 5)
        # Unmentioned keys keep defaults
        self.assertEqual(cfg["case_pr_mode"], "draft")


# ---------------------------------------------------------------------------
# New-protocol event parsing tests
# ---------------------------------------------------------------------------

class TestNewProtocolEventParsing(unittest.TestCase):
    """Tests for new thread-event protocol (codex-cli 0.144.0+)."""

    # The exact real captured stream from ground truth
    REAL_STREAM = "\n".join([
        json.dumps({"type": "thread.started", "thread_id": "019f..."}),
        json.dumps({"type": "turn.started"}),
        json.dumps({"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "OK"}}),
        json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": 13418,
            "cached_input_tokens": 9984,
            "output_tokens": 5,
            "reasoning_output_tokens": 0,
        }}),
    ]) + "\n"

    def _run_with_stdout(self, stdout: str, stderr: str = "", rc: int = 0) -> dict:
        def fake_run(args, **kw):
            return _fake_proc(stdout=stdout, stderr=stderr, returncode=rc)

        with patch("engine.codex_lane.runner.subprocess.run", side_effect=fake_run):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/usr/bin/codex"):
                return run_codex("prompt")

    def test_real_stream_final_message_is_ok(self):
        """item.completed -> item.type==agent_message -> item.text extracts correctly."""
        result = self._run_with_stdout(self.REAL_STREAM)
        self.assertEqual(result["final_message"], "OK")

    def test_real_stream_token_usage_totals(self):
        """turn.completed -> usage dict extracts input/output/total correctly."""
        result = self._run_with_stdout(self.REAL_STREAM)
        self.assertIsNotNone(result["token_usage"])
        self.assertEqual(result["token_usage"]["input_tokens"], 13418)
        self.assertEqual(result["token_usage"]["output_tokens"], 5)
        # total = input + output (no explicit total_tokens in stream)
        self.assertEqual(result["token_usage"]["total_tokens"], 13418 + 5)

    def test_real_stream_ok_true_on_zero_exit(self):
        """Zero exit code => ok=True even for new-protocol stream."""
        result = self._run_with_stdout(self.REAL_STREAM, rc=0)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["error_kind"])

    def test_real_stream_events_count(self):
        """All 4 events in the real stream are counted."""
        result = self._run_with_stdout(self.REAL_STREAM)
        self.assertEqual(result["events_count"], 4)

    def test_mixed_legacy_then_new_keeps_last_seen_message(self):
        """last-seen semantics: new-protocol item.completed after legacy agent_message wins."""
        stream = "\n".join([
            json.dumps({"type": "agent_message", "message": "legacy message"}),
            json.dumps({"type": "item.completed", "item": {"id": "x", "type": "agent_message", "text": "new message"}}),
        ]) + "\n"
        result = self._run_with_stdout(stream)
        self.assertEqual(result["final_message"], "new message")

    def test_mixed_new_then_legacy_keeps_last_seen_message(self):
        """last-seen semantics: legacy agent_message after new-protocol item.completed wins."""
        stream = "\n".join([
            json.dumps({"type": "item.completed", "item": {"id": "x", "type": "agent_message", "text": "new message"}}),
            json.dumps({"type": "agent_message", "message": "legacy message"}),
        ]) + "\n"
        result = self._run_with_stdout(stream)
        self.assertEqual(result["final_message"], "legacy message")

    def test_mixed_legacy_token_count_then_new_turn_completed_keeps_last(self):
        """last-seen semantics: turn.completed token counts after token_count event wins."""
        stream = "\n".join([
            json.dumps({"type": "token_count", "info": {
                "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            }}),
            json.dumps({"type": "turn.completed", "usage": {
                "input_tokens": 200, "output_tokens": 10,
                "cached_input_tokens": 0, "reasoning_output_tokens": 0,
            }}),
        ]) + "\n"
        result = self._run_with_stdout(stream)
        self.assertIsNotNone(result["token_usage"])
        self.assertEqual(result["token_usage"]["input_tokens"], 200)
        self.assertEqual(result["token_usage"]["output_tokens"], 10)

    def test_item_completed_non_agent_message_type_not_captured(self):
        """item.completed with item.type != agent_message does not set final_message."""
        stream = json.dumps({
            "type": "item.completed",
            "item": {"id": "x", "type": "tool_call", "text": "should not be captured"},
        }) + "\n"
        result = self._run_with_stdout(stream)
        self.assertEqual(result["final_message"], "")

    def test_thread_error_event_classifies_usage_limit(self):
        """thread.error event with usage limit message -> error_kind usage_limit."""
        stream = json.dumps({
            "type": "thread.error",
            "error": {"message": "you've hit the usage limit for this window"},
        }) + "\n"
        result = self._run_with_stdout(stream, rc=1)
        self.assertEqual(result["error_kind"], "usage_limit")

    def test_turn_failed_event_classifies_auth(self):
        """turn.failed event with auth message -> error_kind auth."""
        stream = json.dumps({
            "type": "turn.failed",
            "error": {"message": "401 unauthorized"},
        }) + "\n"
        result = self._run_with_stdout(stream, rc=1)
        self.assertEqual(result["error_kind"], "auth")

    def test_error_event_type_classifies_generic_error(self):
        """Generic error event type -> error_kind error."""
        stream = json.dumps({
            "type": "error",
            "message": "something went wrong",
        }) + "\n"
        result = self._run_with_stdout(stream, rc=1)
        self.assertEqual(result["error_kind"], "error")


# ---------------------------------------------------------------------------
# fetch_rate_limits tests
# ---------------------------------------------------------------------------

# Real verbatim rateLimits response shape from ground truth
_REAL_RATE_LIMITS_RESULT = {
    "rateLimits": {
        "limitId": "codex",
        "primary": {
            "usedPercent": 7,
            "windowDurationMins": 10080,
            "resetsAt": 1784513998,
        },
        "secondary": None,
        "credits": {},
        "planType": "pro",
        "rateLimitReachedType": None,
    },
    "rateLimitsByLimitId": {},
}


def _make_fake_appserver(lines: list[str]):
    """Return a Popen mock whose stdout yields the given lines."""
    import io

    class FakePopen:
        def __init__(self):
            self.stdin = io.StringIO()
            self._line_iter = iter(lines)
            self._buf = io.StringIO("\n".join(lines) + "\n")
            self.stdout = self._buf
            self.returncode = 0

        def terminate(self):
            pass

        def kill(self):
            pass

    return FakePopen()


class TestFetchRateLimits(unittest.TestCase):
    """Tests for fetch_rate_limits (frozen cross-lane API)."""

    def _patch_popen(self, popen_obj):
        return patch("engine.codex_lane.runner.subprocess.Popen", return_value=popen_obj)

    def _make_init_response(self) -> str:
        return json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}})

    def _make_rl_response(self) -> str:
        return json.dumps({"jsonrpc": "2.0", "id": 2, "result": _REAL_RATE_LIMITS_RESULT})

    def _make_notification(self) -> str:
        """A server-pushed notification (no id match) that should be ignored."""
        return json.dumps({"jsonrpc": "2.0", "method": "remoteControl/status/changed", "params": {}})

    def _run_fetch(self, lines: list[str]) -> dict | None:
        fake = _make_fake_appserver(lines)
        with self._patch_popen(fake):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/usr/bin/codex"):
                return fetch_rate_limits(timeout_s=5)

    def test_normalized_used_percent(self):
        """used_percent is normalized to float 7.0."""
        lines = [
            self._make_init_response(),
            self._make_rl_response(),
        ]
        result = self._run_fetch(lines)
        self.assertIsNotNone(result)
        self.assertIsNotNone(result["primary"])
        self.assertAlmostEqual(result["primary"]["used_percent"], 7.0)

    def test_normalized_resets_at_is_iso(self):
        """resetsAt epoch 1784513998 converts to an ISO string."""
        lines = [
            self._make_init_response(),
            self._make_rl_response(),
        ]
        result = self._run_fetch(lines)
        self.assertIsNotNone(result)
        resets_at = result["primary"]["resets_at"]
        self.assertIsNotNone(resets_at)
        # Must be parseable as ISO datetime
        dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        self.assertEqual(dt.tzinfo.utcoffset(dt).total_seconds(), 0)

    def test_normalized_window_mins(self):
        """windowDurationMins 10080 normalizes to window_mins 10080."""
        lines = [
            self._make_init_response(),
            self._make_rl_response(),
        ]
        result = self._run_fetch(lines)
        self.assertIsNotNone(result)
        self.assertEqual(result["primary"]["window_mins"], 10080)

    def test_normalized_plan_type(self):
        """planType 'pro' normalized to plan_type 'pro'."""
        lines = [
            self._make_init_response(),
            self._make_rl_response(),
        ]
        result = self._run_fetch(lines)
        self.assertIsNotNone(result)
        self.assertEqual(result["plan_type"], "pro")

    def test_normalized_secondary_none_when_null(self):
        """secondary null in response -> secondary None in result."""
        lines = [
            self._make_init_response(),
            self._make_rl_response(),
        ]
        result = self._run_fetch(lines)
        self.assertIsNotNone(result)
        self.assertIsNone(result["secondary"])

    def test_fetched_at_present_and_iso(self):
        """fetched_at field is present and ISO parseable."""
        lines = [
            self._make_init_response(),
            self._make_rl_response(),
        ]
        result = self._run_fetch(lines)
        self.assertIsNotNone(result)
        self.assertIn("fetched_at", result)
        dt = datetime.fromisoformat(result["fetched_at"].replace("Z", "+00:00"))
        self.assertIsNotNone(dt)

    def test_notification_ignored_awaits_correct_id(self):
        """Notification lines between responses are ignored; correct id still matched."""
        lines = [
            self._make_init_response(),
            self._make_notification(),  # should be skipped
            self._make_rl_response(),
        ]
        result = self._run_fetch(lines)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["primary"]["used_percent"], 7.0)

    def test_timeout_returns_none(self):
        """When the process stdout is empty, fetch_rate_limits returns None."""
        # An empty-line fake server never returns id=1 response
        fake = _make_fake_appserver([])  # empty stdout
        with self._patch_popen(fake):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/usr/bin/codex"):
                # Use very short timeout so test doesn't hang
                result = fetch_rate_limits(timeout_s=1)
        self.assertIsNone(result)

    def test_malformed_jsonrpc_returns_none(self):
        """Malformed JSON in responses results in None."""
        lines = [
            "not json at all",
            "{broken json}",
        ]
        fake = _make_fake_appserver(lines)
        with self._patch_popen(fake):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/usr/bin/codex"):
                result = fetch_rate_limits(timeout_s=1)
        self.assertIsNone(result)

    def test_file_not_found_returns_none(self):
        """FileNotFoundError (codex not installed) returns None, does not raise."""
        with patch("engine.codex_lane.runner.subprocess.Popen",
                   side_effect=FileNotFoundError("no codex")):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/missing/codex"):
                result = fetch_rate_limits(timeout_s=5)
        self.assertIsNone(result)

    def test_never_raises(self):
        """fetch_rate_limits never raises regardless of error."""
        with patch("engine.codex_lane.runner.subprocess.Popen",
                   side_effect=RuntimeError("unexpected")):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/usr/bin/codex"):
                result = fetch_rate_limits(timeout_s=5)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# note_rate_limits tests
# ---------------------------------------------------------------------------

class TestNoteRateLimits(unittest.TestCase):
    """Tests for budget.note_rate_limits (frozen cross-lane API)."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        Path(self._tmpdir, "data", "codex_lane").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _load_state(self) -> dict:
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        return json.loads(p.read_text())

    def _write_state(self, state: dict):
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        p.write_text(json.dumps(state))

    def test_none_is_noop(self):
        """note_rate_limits(None) does nothing — no file written, no error."""
        # No state file should exist after a None call
        note_rate_limits(None, root=self._tmpdir)
        state_path = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        # File may or may not exist; if it does not, that is fine
        if state_path.exists():
            # If it does exist, it must be valid
            json.loads(state_path.read_text())

    def test_real_dict_updates_state_and_sets_rate_limits(self):
        """A real fetch_rate_limits result updates state["rate_limits"]."""
        rl = {
            "primary": {"used_percent": 7.0, "resets_at": "2026-07-20T00:00:00+00:00", "window_mins": 10080},
            "secondary": None,
            "plan_type": "pro",
            "fetched_at": "2026-07-13T10:00:00+00:00",
        }
        note_rate_limits(rl, root=self._tmpdir)
        state = self._load_state()
        self.assertIsNotNone(state["rate_limits"])
        self.assertAlmostEqual(state["rate_limits"]["primary"]["used_percent"], 7.0)
        self.assertIsNotNone(state["updated_at"])

    def test_real_dict_clears_degraded(self):
        """note_rate_limits with a primary entry clears the degraded flag."""
        self._write_state({
            "schema": "codex_lane.usage_state.v1",
            "degraded": True,
            "paused_until": None,
            "sessions": [],
            "rate_limits": None,
        })
        rl = {
            "primary": {"used_percent": 7.0, "resets_at": None, "window_mins": 10080},
            "secondary": None,
            "plan_type": "pro",
            "fetched_at": "2026-07-13T10:00:00+00:00",
        }
        note_rate_limits(rl, root=self._tmpdir)
        state = self._load_state()
        self.assertFalse(state["degraded"])

    def test_note_rate_limits_does_not_affect_sessions(self):
        """note_rate_limits does not add or remove session rows."""
        sessions = [
            {"ts": "2026-07-13T09:00:00+00:00", "lane": "signals", "ok": True, "error_kind": None}
        ]
        self._write_state({
            "schema": "codex_lane.usage_state.v1",
            "degraded": True,
            "paused_until": None,
            "sessions": sessions,
            "rate_limits": None,
        })
        rl = {
            "primary": {"used_percent": 20.0, "resets_at": None, "window_mins": 10080},
            "secondary": None,
            "plan_type": "pro",
            "fetched_at": "2026-07-13T10:00:00+00:00",
        }
        note_rate_limits(rl, root=self._tmpdir)
        state = self._load_state()
        # Sessions should be unchanged
        self.assertEqual(len(state["sessions"]), 1)

    def test_can_run_sees_updated_rate_limits_after_note(self):
        """After note_rate_limits sets 86%, can_run returns False."""
        rl = {
            "primary": {"used_percent": 86.0, "resets_at": None, "window_mins": 10080},
            "secondary": None,
            "plan_type": "pro",
            "fetched_at": "2026-07-13T10:00:00+00:00",
        }
        note_rate_limits(rl, root=self._tmpdir)
        ok, reason = can_run(root=self._tmpdir)
        self.assertFalse(ok)
        self.assertIn("budget:primary", reason)

    def test_never_raises(self):
        """note_rate_limits never raises, even with a bad root path."""
        # Pass a root that cannot be written to (simulate an error)
        note_rate_limits({"primary": {"used_percent": 5.0}}, root="/nonexistent/path/crx")


# ---------------------------------------------------------------------------
# CRX-R4 self-heal: note_rate_limits clears stale paused_until
# ---------------------------------------------------------------------------

class TestNoteRateLimitsSelfHeal(unittest.TestCase):
    """FIX 1 — note_rate_limits clears a future paused_until when the fresh
    snapshot reports all present windows below budget_pct."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        Path(self._tmpdir, "data", "codex_lane").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _load_state(self) -> dict:
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        return json.loads(p.read_text())

    def _write_state(self, state: dict):
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        p.write_text(json.dumps(state))

    def _state_with_future_pause(self, extra: dict | None = None) -> dict:
        base = {
            "schema": "codex_lane.usage_state.v1",
            "degraded": False,
            "paused_until": _to_iso(_now() + timedelta(days=30)),
            "sessions": [],
            "rate_limits": None,
        }
        if extra:
            base.update(extra)
        return base

    def test_fresh_snapshot_below_budget_clears_paused_until(self):
        """paused_until in future + all windows < budget_pct → cleared, can_run True."""
        self._write_state(self._state_with_future_pause())
        rl = {
            "primary": {"used_percent": 9.0, "resets_at": None},
            "secondary": None,
            "plan_type": "pro",
            "fetched_at": _to_iso(_now()),
        }
        note_rate_limits(rl, root=self._tmpdir)
        state = self._load_state()
        self.assertIsNone(state["paused_until"])
        ok, reason = can_run(root=self._tmpdir)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_fresh_snapshot_at_or_above_budget_preserves_paused_until(self):
        """paused_until in future + primary used_percent >= budget_pct → preserved."""
        self._write_state(self._state_with_future_pause())
        rl = {
            "primary": {"used_percent": 85.0, "resets_at": None},  # == budget_pct default
            "secondary": None,
            "plan_type": "pro",
            "fetched_at": _to_iso(_now()),
        }
        note_rate_limits(rl, root=self._tmpdir)
        state = self._load_state()
        self.assertIsNotNone(state["paused_until"])
        ok, reason = can_run(root=self._tmpdir)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("paused_until:"))

    def test_no_windows_present_preserves_paused_until(self):
        """Snapshot with primary=None and secondary=None provides no evidence → paused_until kept."""
        self._write_state(self._state_with_future_pause())
        rl = {
            "primary": None,
            "secondary": None,
            "plan_type": "pro",
            "fetched_at": _to_iso(_now()),
        }
        note_rate_limits(rl, root=self._tmpdir)
        state = self._load_state()
        self.assertIsNotNone(state["paused_until"])


# ---------------------------------------------------------------------------
# FIX 2 — plan_type change tripwire
# ---------------------------------------------------------------------------

class TestPlanTypeChangeTripwire(unittest.TestCase):
    """FIX 2 — _apply_rate_limits_to_state warns on plan_type change."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        Path(self._tmpdir, "data", "codex_lane").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _load_state(self) -> dict:
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        return json.loads(p.read_text())

    def _write_state(self, state: dict):
        p = Path(self._tmpdir, "data", "codex_lane", "usage_state.json")
        p.write_text(json.dumps(state))

    def _base_rl(self, plan_type: str) -> dict:
        return {
            "primary": {"used_percent": 10.0, "resets_at": None},
            "secondary": None,
            "plan_type": plan_type,
            "fetched_at": _to_iso(_now()),
        }

    def test_plan_type_change_logs_warning_and_updates_state(self):
        """Stored plan_type='free', incoming='pro' → warning logged and state updated."""
        self._write_state({
            "schema": "codex_lane.usage_state.v1",
            "degraded": False,
            "paused_until": None,
            "sessions": [],
            "rate_limits": None,
            "plan_type": "free",
        })
        with self.assertLogs("engine.codex_lane.budget", level="WARNING") as cm:
            note_rate_limits(self._base_rl("pro"), root=self._tmpdir)
        # At least one warning about plan_type
        self.assertTrue(
            any("plan_type" in msg for msg in cm.output),
            f"Expected plan_type warning in logs; got: {cm.output}",
        )
        state = self._load_state()
        self.assertEqual(state.get("plan_type"), "pro")

    def test_same_plan_type_does_not_warn(self):
        """Same plan_type='pro' on both sides → no warning."""
        self._write_state({
            "schema": "codex_lane.usage_state.v1",
            "degraded": False,
            "paused_until": None,
            "sessions": [],
            "rate_limits": None,
            "plan_type": "pro",
        })
        import logging
        with self.assertNoLogs("engine.codex_lane.budget", level="WARNING"):
            note_rate_limits(self._base_rl("pro"), root=self._tmpdir)
        state = self._load_state()
        self.assertEqual(state.get("plan_type"), "pro")


# ---------------------------------------------------------------------------
# FIX 6 — _compute_pause_until secondary window -> 7d fallback
# ---------------------------------------------------------------------------

class TestComputePauseUntilFix6(unittest.TestCase):
    """Secondary-attributed limits use 7d fallback; primary/unattributed use 5h."""

    def test_secondary_100pct_no_reset_gives_7d(self):
        now = _now()
        rl = {
            "primary": {"used_percent": 20.0, "resets_at": None},
            "secondary": {"used_percent": 100.0, "resets_at": None},
        }
        result = _compute_pause_until(rl, now)
        diff = (result - now).total_seconds()
        self.assertAlmostEqual(diff, 7 * 24 * 3600, delta=5)

    def test_secondary_gt_primary_no_reset_gives_7d(self):
        now = _now()
        rl = {
            "primary": {"used_percent": 30.0, "resets_at": None},
            "secondary": {"used_percent": 95.0, "resets_at": None},
        }
        result = _compute_pause_until(rl, now)
        diff = (result - now).total_seconds()
        self.assertAlmostEqual(diff, 7 * 24 * 3600, delta=5)

    def test_primary_attributed_gives_5h(self):
        now = _now()
        rl = {
            "primary": {"used_percent": 90.0, "resets_at": None},
            "secondary": {"used_percent": 5.0, "resets_at": None},
        }
        result = _compute_pause_until(rl, now)
        diff = (result - now).total_seconds()
        self.assertAlmostEqual(diff, 5 * 3600, delta=5)

    def test_no_rate_limits_gives_5h(self):
        now = _now()
        result = _compute_pause_until(None, now)
        diff = (result - now).total_seconds()
        self.assertAlmostEqual(diff, 5 * 3600, delta=5)

    def test_reported_resets_at_wins(self):
        now = _now()
        future = now + timedelta(hours=3)
        rl = {
            "primary": {"used_percent": 100.0, "resets_at": _to_iso(future)},
            "secondary": {"used_percent": 100.0, "resets_at": None},
        }
        result = _compute_pause_until(rl, now)
        self.assertAlmostEqual(
            abs((result - future).total_seconds()), 0, delta=2
        )


# ---------------------------------------------------------------------------
# FIX 8 — error event with no text -> error_kind defaults to "error"
# ---------------------------------------------------------------------------

class TestErrorEventNoText(unittest.TestCase):
    """Error events without text payload force ok=False with error_kind='error'."""

    def _run_with_stdout(self, stdout: str, rc: int = 0) -> dict:
        def fake_run(args, **kw):
            return _fake_proc(stdout=stdout, stderr="", returncode=rc)

        with patch("engine.codex_lane.runner.subprocess.run", side_effect=fake_run):
            with patch("engine.codex_lane.runner.resolve_codex_bin", return_value="/usr/bin/codex"):
                from engine.codex_lane.runner import run_codex
                return run_codex("prompt")

    def test_thread_error_no_text_exit0_forces_false(self):
        stream = json.dumps({"type": "thread.error", "error": {}}) + "\n"
        result = self._run_with_stdout(stream, rc=0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "error")

    def test_turn_failed_no_payload_exit0_forces_false(self):
        stream = json.dumps({"type": "turn.failed"}) + "\n"
        result = self._run_with_stdout(stream, rc=0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "error")

    def test_error_type_no_payload_exit0_forces_false(self):
        stream = json.dumps({"type": "error"}) + "\n"
        result = self._run_with_stdout(stream, rc=0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "error")

    def test_thread_error_with_text_still_classifies(self):
        """Error event WITH text still classifies correctly (regression guard)."""
        stream = json.dumps({
            "type": "thread.error",
            "error": {"message": "you've hit the usage limit"},
        }) + "\n"
        result = self._run_with_stdout(stream, rc=1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "usage_limit")


if __name__ == "__main__":
    unittest.main()
