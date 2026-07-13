"""tests/test_metabolism_budget_gate.py — Hermetic tests for V11 budget-gate.

COVERAGE:
  HEADERS   header name parsing variants (utilization/used, %-suffix, 5h/7d/weekly)
  EST       est fallback only when budget configured; absent config = None
  UNKNOWNS  never disarm on pure unknowns; unknown = eligible
  VERDICTS  all three modes: 5h_max, weekly_max, manual
            5h_exhausted_waiting_reset; manual blocked only when ALL known >=90
  STATUS    write_status file shape (schema, ts, per_key, verdicts)
  CLI       one-line JSON + exit 0 even on garbage mode input
  THROTTLE  pace_loops_per_window: V11 vocab, legacy compat, invalid

All tests are HERMETIC (tmp_path roots, synthetic fixtures or monkeypatched
usage_snapshot; no real network or filesystem reads).
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Fixture helpers ────────────────────────────────────────────────────────────

_BUDGET_CFG_V11 = textwrap.dedent("""\
schema: metabolism_budget.v1
gate_policy:
  fivehour_done_pct: 80
  weekly_done_pct: 80
  weekly_key_stop_pct: 85
  manual_floor_pct: 90
  est_budget_5h_tokens: null
  est_budget_weekly_tokens: null
  duration_noop_floor_s: 300
""")

_BUDGET_CFG_WITH_EST = textwrap.dedent("""\
schema: metabolism_budget.v1
gate_policy:
  fivehour_done_pct: 80
  weekly_done_pct: 80
  weekly_key_stop_pct: 85
  manual_floor_pct: 90
  est_budget_5h_tokens: 1000000
  est_budget_weekly_tokens: 5000000
  duration_noop_floor_s: 300
""")


def _make_root(tmp_path: Path, cfg_text: str = _BUDGET_CFG_V11) -> Path:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "data" / "metabolism").mkdir(parents=True)
    (root / "config" / "metabolism_budget.yml").write_text(cfg_text, encoding="utf-8")
    return root


def _write_usage_ledger(root: Path, rows: list[dict]) -> None:
    p = root / "data" / "metabolism" / "key_usage.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _snapshot_row(
    key_id: str,
    *,
    present: bool = True,
    enabled: bool = True,
    headers: dict | None = None,
    window_5h_est_tokens: int = 0,
    weekly_est_tokens: int = 0,
) -> dict[str, Any]:
    return {
        "key_id": key_id,
        "present": present,
        "enabled": enabled,
        "cooling": False,
        "cool_kind": None,
        "reset_hint": None,
        "window_5h_est_tokens": window_5h_est_tokens,
        "weekly_est_tokens": weekly_est_tokens,
        "window_5h_sessions": 0,
        "weekly_sessions": 0,
        "last_outcome": None,
        "last_ts": None,
        "ratelimit_headers": headers or {},
        "headers_ts": None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# HEADER PARSING VARIANTS
# ══════════════════════════════════════════════════════════════════════════════

class TestHeaderParsing:
    """_parse_headers handles all naming variants generically."""

    def _parse(self, headers: dict) -> dict:
        from engine.metabolism.budget_gate import _parse_headers  # noqa: PLC0415
        return _parse_headers(headers)

    def test_5h_utilization_integer(self) -> None:
        h = {"anthropic-ratelimit-5h-utilization": "42"}
        r = self._parse(h)
        assert r["pct_5h"] == pytest.approx(42.0)
        assert r["pct_weekly"] is None

    def test_5h_used_percent_suffix(self) -> None:
        h = {"anthropic-ratelimit-5h-used-pct": "75%"}
        r = self._parse(h)
        assert r["pct_5h"] == pytest.approx(75.0)

    def test_fivehour_variant(self) -> None:
        h = {"anthropic-ratelimit-five-hour-utilization": "60"}
        r = self._parse(h)
        assert r["pct_5h"] == pytest.approx(60.0)

    def test_7d_weekly(self) -> None:
        h = {"anthropic-ratelimit-7d-utilization": "50"}
        r = self._parse(h)
        assert r["pct_weekly"] == pytest.approx(50.0)
        assert r["pct_5h"] is None

    def test_weekly_variant(self) -> None:
        h = {"anthropic-ratelimit-weekly-used": "33%"}
        r = self._parse(h)
        assert r["pct_weekly"] == pytest.approx(33.0)

    def test_seven_day_variant(self) -> None:
        h = {"anthropic-ratelimit-seven-day-utilization": "10"}
        r = self._parse(h)
        assert r["pct_weekly"] == pytest.approx(10.0)

    def test_reset_5h_captured(self) -> None:
        h = {"anthropic-ratelimit-5h-reset": "2026-07-13T12:00:00Z"}
        r = self._parse(h)
        assert r["reset_5h"] == "2026-07-13T12:00:00Z"

    def test_reset_weekly_captured(self) -> None:
        h = {"anthropic-ratelimit-weekly-reset": "2026-07-20T00:00:00Z"}
        r = self._parse(h)
        assert r["reset_weekly"] == "2026-07-20T00:00:00Z"

    def test_both_windows_parsed_together(self) -> None:
        h = {
            "anthropic-ratelimit-5h-utilization": "55",
            "anthropic-ratelimit-7d-utilization": "80%",
        }
        r = self._parse(h)
        assert r["pct_5h"] == pytest.approx(55.0)
        assert r["pct_weekly"] == pytest.approx(80.0)

    def test_non_anthropic_headers_ignored(self) -> None:
        h = {
            "content-type": "application/json",
            "x-custom-5h-limit": "99",
        }
        r = self._parse(h)
        assert r["pct_5h"] is None
        assert r["pct_weekly"] is None

    def test_empty_headers(self) -> None:
        r = self._parse({})
        assert r["pct_5h"] is None
        assert r["pct_weekly"] is None

    def test_unparseable_value(self) -> None:
        h = {"anthropic-ratelimit-5h-utilization": "not-a-number"}
        r = self._parse(h)
        assert r["pct_5h"] is None

    def test_zero_utilization(self) -> None:
        h = {"anthropic-ratelimit-5h-utilization": "0"}
        r = self._parse(h)
        assert r["pct_5h"] == pytest.approx(0.0)


# ══════════════════════════════════════════════════════════════════════════════
# EST FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

class TestEstFallback:
    """est fallback applies only when est_budget_*_tokens is configured non-null."""

    def test_no_budget_config_stays_none(self, tmp_path: Path) -> None:
        """Without est_budget config, pct stays None even with est_tokens."""
        root = _make_root(tmp_path, _BUDGET_CFG_V11)
        snap = [_snapshot_row("claude_code_oauth_1", window_5h_est_tokens=500_000, weekly_est_tokens=2_000_000)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import key_budget  # noqa: PLC0415
            kb = key_budget("claude_code_oauth_1", root)
        assert kb["pct_5h"] is None
        assert kb["src_5h"] is None
        assert kb["pct_weekly"] is None
        assert kb["src_weekly"] is None

    def test_est_budget_gives_pct(self, tmp_path: Path) -> None:
        """With est_budget configured, est tokens / budget = pct."""
        root = _make_root(tmp_path, _BUDGET_CFG_WITH_EST)
        snap = [_snapshot_row("claude_code_oauth_1", window_5h_est_tokens=500_000, weekly_est_tokens=2_500_000)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import key_budget  # noqa: PLC0415
            kb = key_budget("claude_code_oauth_1", root)
        # 500k / 1M = 50%
        assert kb["pct_5h"] == pytest.approx(50.0)
        assert kb["src_5h"] == "est"
        # 2.5M / 5M = 50%
        assert kb["pct_weekly"] == pytest.approx(50.0)
        assert kb["src_weekly"] == "est"

    def test_reported_takes_priority_over_est(self, tmp_path: Path) -> None:
        """When headers present, reported wins over est."""
        root = _make_root(tmp_path, _BUDGET_CFG_WITH_EST)
        headers = {"anthropic-ratelimit-5h-utilization": "70"}
        snap = [_snapshot_row("claude_code_oauth_1", headers=headers, window_5h_est_tokens=900_000)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import key_budget  # noqa: PLC0415
            kb = key_budget("claude_code_oauth_1", root)
        assert kb["pct_5h"] == pytest.approx(70.0)
        assert kb["src_5h"] == "reported"

    def test_missing_snapshot_row_est_fallback(self, tmp_path: Path) -> None:
        """Key absent from snapshot: est fallback with 0 tokens gives 0%."""
        root = _make_root(tmp_path, _BUDGET_CFG_WITH_EST)
        snap: list = []  # no rows
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import key_budget  # noqa: PLC0415
            kb = key_budget("claude_code_oauth_1", root)
        assert kb["pct_5h"] == pytest.approx(0.0)
        assert kb["src_5h"] == "est"


# ══════════════════════════════════════════════════════════════════════════════
# GATE VERDICTS — 5h_max
# ══════════════════════════════════════════════════════════════════════════════

class TestGateVerdict5hMax:

    def test_eligible_when_pct_below_threshold(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        headers = {"anthropic-ratelimit-5h-utilization": "50"}
        snap = [_snapshot_row("claude_code_oauth_1", headers=headers)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("5h_max", root)
        assert "claude_code_oauth_1" in v["eligible_keys"]
        assert not v["all_done"]

    def test_not_eligible_when_at_threshold(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        headers = {"anthropic-ratelimit-5h-utilization": "80"}
        snap = [_snapshot_row("claude_code_oauth_1", headers=headers)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("5h_max", root)
        assert "claude_code_oauth_1" not in v["eligible_keys"]
        assert v["all_done"]

    def test_unknown_pct_makes_eligible(self, tmp_path: Path) -> None:
        """A key with unknown pct (no headers, no est budget) is always eligible."""
        root = _make_root(tmp_path)
        snap = [_snapshot_row("claude_code_oauth_1")]  # no headers
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("5h_max", root)
        assert "claude_code_oauth_1" in v["eligible_keys"]
        assert not v["all_done"]

    def test_never_disarm_on_pure_unknowns(self, tmp_path: Path) -> None:
        """all_done must be False when NO key has a known pct."""
        root = _make_root(tmp_path)
        snap = [
            _snapshot_row("claude_code_oauth_1"),
            _snapshot_row("claude_code_oauth_2"),
        ]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("5h_max", root)
        assert not v["all_done"]
        assert v["reason"] == "unknown_usage"

    def test_all_done_when_all_known_at_threshold(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        snap = [
            _snapshot_row("k1", headers={"anthropic-ratelimit-5h-utilization": "85"}),
            _snapshot_row("k2", headers={"anthropic-ratelimit-5h-utilization": "90"}),
        ]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("5h_max", root)
        assert v["all_done"]
        assert v["eligible_keys"] == []

    def test_mixed_known_unknown_not_all_done(self, tmp_path: Path) -> None:
        """One key known >=80, one unknown -> eligible (not done)."""
        root = _make_root(tmp_path)
        snap = [
            _snapshot_row("k1", headers={"anthropic-ratelimit-5h-utilization": "85"}),
            _snapshot_row("k2"),  # unknown
        ]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("5h_max", root)
        assert not v["all_done"]
        assert "k2" in v["eligible_keys"]


# ══════════════════════════════════════════════════════════════════════════════
# GATE VERDICTS — weekly_max
# ══════════════════════════════════════════════════════════════════════════════

class TestGateVerdictWeeklyMax:

    def test_eligible_when_both_below_threshold(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        headers = {
            "anthropic-ratelimit-5h-utilization": "50",
            "anthropic-ratelimit-7d-utilization": "40",
        }
        snap = [_snapshot_row("k1", headers=headers)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("weekly_max", root)
        assert "k1" in v["eligible_keys"]
        assert not v["all_done"]

    def test_5h_exhausted_waiting_reset_reason(self, tmp_path: Path) -> None:
        """5h >=80% but weekly <80% -> 5h_exhausted_waiting_reset."""
        root = _make_root(tmp_path)
        headers = {
            "anthropic-ratelimit-5h-utilization": "82",
            "anthropic-ratelimit-7d-utilization": "60",
        }
        snap = [_snapshot_row("k1", headers=headers)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("weekly_max", root)
        assert v["reason"] == "5h_exhausted_waiting_reset"
        assert not v["all_done"]
        assert "k1" not in v["eligible_keys"]

    def test_all_done_weekly(self, tmp_path: Path) -> None:
        """All keys known weekly >=80% -> all_done."""
        root = _make_root(tmp_path)
        snap = [
            _snapshot_row("k1", headers={"anthropic-ratelimit-7d-utilization": "80"}),
            _snapshot_row("k2", headers={"anthropic-ratelimit-7d-utilization": "92"}),
        ]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("weekly_max", root)
        assert v["all_done"]

    def test_per_key_weekly_stop_at_85(self, tmp_path: Path) -> None:
        """Key at weekly >=85% is removed from eligible even if 5h is fine."""
        root = _make_root(tmp_path)
        headers = {
            "anthropic-ratelimit-5h-utilization": "20",
            "anthropic-ratelimit-7d-utilization": "87",
        }
        snap = [_snapshot_row("k1", headers=headers)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("weekly_max", root)
        assert "k1" not in v["eligible_keys"]


# ══════════════════════════════════════════════════════════════════════════════
# GATE VERDICTS — manual
# ══════════════════════════════════════════════════════════════════════════════

class TestGateVerdictManual:

    def test_not_blocked_below_floor(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        headers = {"anthropic-ratelimit-7d-utilization": "70"}
        snap = [_snapshot_row("k1", headers=headers)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("manual", root)
        assert not v["blocked"]

    def test_blocked_when_all_known_at_floor(self, tmp_path: Path) -> None:
        """All keys known >=90% weekly -> blocked."""
        root = _make_root(tmp_path)
        snap = [
            _snapshot_row("k1", headers={"anthropic-ratelimit-7d-utilization": "91"}),
            _snapshot_row("k2", headers={"anthropic-ratelimit-7d-utilization": "95"}),
        ]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("manual", root)
        assert v["blocked"]

    def test_not_blocked_when_one_unknown(self, tmp_path: Path) -> None:
        """Any unknown keeps manual open."""
        root = _make_root(tmp_path)
        snap = [
            _snapshot_row("k1", headers={"anthropic-ratelimit-7d-utilization": "95"}),
            _snapshot_row("k2"),  # unknown
        ]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("manual", root)
        assert not v["blocked"]
        assert "k2" in v["eligible_keys"]

    def test_not_blocked_all_unknown(self, tmp_path: Path) -> None:
        """All unknown -> not blocked."""
        root = _make_root(tmp_path)
        snap = [_snapshot_row("k1"), _snapshot_row("k2")]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("manual", root)
        assert not v["blocked"]

    def test_no_keys_not_blocked(self, tmp_path: Path) -> None:
        """No enabled keys -> not blocked (nothing to block on)."""
        root = _make_root(tmp_path)
        snap: list = []
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("manual", root)
        assert not v["blocked"]

    def test_exactly_at_floor_is_blocked(self, tmp_path: Path) -> None:
        """At exactly manual_floor_pct (90) is blocked."""
        root = _make_root(tmp_path)
        snap = [_snapshot_row("k1", headers={"anthropic-ratelimit-7d-utilization": "90"})]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("manual", root)
        assert v["blocked"]


# ══════════════════════════════════════════════════════════════════════════════
# WRITE_STATUS — file shape
# ══════════════════════════════════════════════════════════════════════════════

class TestWriteStatus:

    def test_file_written_with_correct_schema(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        snap = [_snapshot_row("k1", headers={"anthropic-ratelimit-5h-utilization": "30"})]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import write_status  # noqa: PLC0415
            path_str = write_status(root)

        path = Path(path_str)
        assert path.exists(), "write_status should create the file"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["schema"] == "metab_budget_status.v1"
        assert "ts" in data
        assert "per_key" in data
        assert "verdicts" in data

    def test_verdicts_has_all_three_modes(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        snap: list = []
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import write_status  # noqa: PLC0415
            path_str = write_status(root)

        data = json.loads(Path(path_str).read_text(encoding="utf-8"))
        assert set(data["verdicts"].keys()) == {"5h_max", "weekly_max", "manual"}

    def test_verdict_shape_per_mode(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        snap = [_snapshot_row("k1")]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import write_status  # noqa: PLC0415
            path_str = write_status(root)

        data = json.loads(Path(path_str).read_text(encoding="utf-8"))
        for mode, v in data["verdicts"].items():
            assert "eligible_keys" in v, f"{mode} missing eligible_keys"
            assert "all_done" in v, f"{mode} missing all_done"
            assert "blocked" in v, f"{mode} missing blocked"
            assert "reason" in v, f"{mode} missing reason"

    def test_never_raises_on_missing_data_dir(self, tmp_path: Path) -> None:
        """write_status should fail soft and return the intended path."""
        root = tmp_path / "empty_repo"
        root.mkdir()
        # No config, no data dir
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=[]):
            from engine.metabolism.budget_gate import write_status  # noqa: PLC0415
            path_str = write_status(root)
        assert path_str  # returns a path even on error


# ══════════════════════════════════════════════════════════════════════════════
# CLI — one-line JSON, exit 0 always
# ══════════════════════════════════════════════════════════════════════════════

class TestCLI:
    """CLI must print exactly one line of valid JSON and always exit 0."""

    def _run_cli(self, *args: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, "-m", "engine.metabolism.budget_gate", *args],
            capture_output=True,
            text=True,
            cwd=str(_ROOT),
        )
        return result.returncode, result.stdout.strip()

    def test_manual_mode_prints_one_json_line(self) -> None:
        rc, out = self._run_cli("--mode", "manual")
        assert rc == 0, f"non-zero exit: {rc}"
        lines = [l for l in out.splitlines() if l.strip()]
        assert len(lines) == 1, f"expected 1 line, got {len(lines)}: {out!r}"
        data = json.loads(lines[0])
        assert data["mode"] == "manual"

    def test_5h_max_mode_exits_zero(self) -> None:
        rc, out = self._run_cli("--mode", "5h_max")
        assert rc == 0

    def test_weekly_max_mode_exits_zero(self) -> None:
        rc, out = self._run_cli("--mode", "weekly_max")
        assert rc == 0

    def test_garbage_mode_exits_zero(self) -> None:
        """Even on unknown mode, CLI must exit 0 and print one JSON line."""
        rc, out = self._run_cli("--mode", "not_a_real_mode")
        assert rc == 0
        lines = [l for l in out.splitlines() if l.strip()]
        assert len(lines) >= 1
        # Must be valid JSON
        json.loads(lines[0])

    def test_no_mode_arg_exits_zero(self) -> None:
        """Default mode (manual) runs without error."""
        rc, out = self._run_cli()
        assert rc == 0
        lines = [l for l in out.splitlines() if l.strip()]
        assert len(lines) == 1
        json.loads(lines[0])


# ══════════════════════════════════════════════════════════════════════════════
# THROTTLE — pace_loops_per_window
# ══════════════════════════════════════════════════════════════════════════════

class TestPaceLoopsPerWindow:
    """pace_loops_per_window: V11 vocab + legacy compat + invalid."""

    def test_v11_low(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "low")
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        assert pace_loops_per_window() == 1

    def test_v11_medium(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "medium")
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        assert pace_loops_per_window() == 2

    def test_v11_high(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "high")
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        assert pace_loops_per_window() == 3

    def test_v11_max(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "max")
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        assert pace_loops_per_window() == 4

    def test_legacy_single(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "single")
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        assert pace_loops_per_window() == 1

    def test_legacy_2x(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "2x")
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        assert pace_loops_per_window() == 2

    def test_legacy_4x(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "4x")
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        assert pace_loops_per_window() == 3

    def test_absent_env_returns_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("METAB_PACE", raising=False)
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        assert pace_loops_per_window() == 1


# ══════════════════════════════════════════════════════════════════════════════
# FIX 8 — 5h_max weekly-floor exclusion
# ══════════════════════════════════════════════════════════════════════════════

class TestGateVerdict5hMaxWeeklyFloorExclusion:
    """5h_max must exclude keys whose KNOWN pct_weekly >= manual_floor_pct (90%).
    Unknown pct_weekly does not exclude (fail-open).
    """

    def test_known_weekly_above_floor_excluded_in_5h_max(self, tmp_path: Path) -> None:
        """Key with pct_5h=10 but known pct_weekly=95 is NOT eligible in 5h_max."""
        root = _make_root(tmp_path)
        headers = {
            "anthropic-ratelimit-5h-utilization": "10",
            "anthropic-ratelimit-7d-utilization": "95",
        }
        snap = [_snapshot_row("k1", headers=headers)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("5h_max", root)
        assert "k1" not in v["eligible_keys"], (
            "Key with pct_weekly=95 (>= manual_floor=90) must be excluded from "
            "5h_max eligible set regardless of its 5h utilisation"
        )

    def test_unknown_weekly_stays_eligible_in_5h_max(self, tmp_path: Path) -> None:
        """Key with pct_5h=10 and unknown pct_weekly remains eligible in 5h_max (fail-open)."""
        root = _make_root(tmp_path)
        headers = {"anthropic-ratelimit-5h-utilization": "10"}
        snap = [_snapshot_row("k1", headers=headers)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("5h_max", root)
        assert "k1" in v["eligible_keys"], (
            "Key with unknown pct_weekly must remain eligible in 5h_max (fail-open)"
        )

    def test_exactly_at_floor_excluded(self, tmp_path: Path) -> None:
        """Key at exactly manual_floor_pct (90) is excluded from 5h_max."""
        root = _make_root(tmp_path)
        headers = {
            "anthropic-ratelimit-5h-utilization": "20",
            "anthropic-ratelimit-7d-utilization": "90",
        }
        snap = [_snapshot_row("k1", headers=headers)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("5h_max", root)
        assert "k1" not in v["eligible_keys"], (
            "Key at exactly manual_floor_pct=90 must be excluded from 5h_max"
        )

    def test_below_floor_eligible_in_5h_max(self, tmp_path: Path) -> None:
        """Key with pct_weekly=70 (< 90 floor) stays eligible in 5h_max."""
        root = _make_root(tmp_path)
        headers = {
            "anthropic-ratelimit-5h-utilization": "10",
            "anthropic-ratelimit-7d-utilization": "70",
        }
        snap = [_snapshot_row("k1", headers=headers)]
        with patch("engine.neuralweb.key_pool.usage_snapshot", return_value=snap):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            v = gate_verdict("5h_max", root)
        assert "k1" in v["eligible_keys"]

    def test_invalid_env_returns_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "overdrive")
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        assert pace_loops_per_window() == 1

    def test_explicit_arg_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "single")
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        assert pace_loops_per_window("high") == 3

    def test_never_raises_on_garbage_arg(self) -> None:
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        result = pace_loops_per_window("turbo-warp")
        assert isinstance(result, int)
        assert result == 1

    def test_all_v11_vocab_covered(self) -> None:
        from engine.metabolism.throttle import pace_loops_per_window, _PACE_LOOPS  # noqa: PLC0415
        for v in ("low", "medium", "high", "max"):
            assert v in _PACE_LOOPS, f"{v!r} missing from _PACE_LOOPS"

    def test_ladder_is_strictly_increasing(self) -> None:
        from engine.metabolism.throttle import pace_loops_per_window  # noqa: PLC0415
        vals = [pace_loops_per_window(v) for v in ("low", "medium", "high", "max")]
        for i in range(len(vals) - 1):
            assert vals[i] < vals[i + 1], f"ladder not strictly increasing at position {i}"


# ══════════════════════════════════════════════════════════════════════════════
# NEVER-RAISE CONTRACT
# ══════════════════════════════════════════════════════════════════════════════

class TestNeverRaise:

    def test_gate_verdict_never_raises_on_snapshot_failure(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        with patch("engine.neuralweb.key_pool.usage_snapshot", side_effect=RuntimeError("boom")):
            from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
            # Should not raise
            for mode in ("5h_max", "weekly_max", "manual"):
                v = gate_verdict(mode, root)
                assert isinstance(v, dict)

    def test_key_budget_never_raises_on_snapshot_failure(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        with patch("engine.neuralweb.key_pool.usage_snapshot", side_effect=RuntimeError("boom")):
            from engine.metabolism.budget_gate import key_budget  # noqa: PLC0415
            kb = key_budget("claude_code_oauth_1", root)
        assert isinstance(kb, dict)
        assert kb["pct_5h"] is None

    def test_write_status_never_raises(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        with patch("engine.neuralweb.key_pool.usage_snapshot", side_effect=RuntimeError("boom")):
            from engine.metabolism.budget_gate import write_status  # noqa: PLC0415
            path_str = write_status(root)
        assert isinstance(path_str, str)

    def test_load_budget_cfg_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        root = tmp_path / "norepo"
        root.mkdir()
        from engine.metabolism.budget_gate import load_budget_cfg, _DEFAULTS  # noqa: PLC0415
        cfg = load_budget_cfg(root)
        assert cfg["fivehour_done_pct"] == _DEFAULTS["fivehour_done_pct"]
        assert cfg["manual_floor_pct"] == _DEFAULTS["manual_floor_pct"]


# ══════════════════════════════════════════════════════════════════════════════
# LOAD_BUDGET_CFG
# ══════════════════════════════════════════════════════════════════════════════

class TestLoadBudgetCfg:

    def test_defaults_from_file(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        from engine.metabolism.budget_gate import load_budget_cfg  # noqa: PLC0415
        cfg = load_budget_cfg(root)
        assert cfg["fivehour_done_pct"] == 80
        assert cfg["weekly_done_pct"] == 80
        assert cfg["weekly_key_stop_pct"] == 85
        assert cfg["manual_floor_pct"] == 90
        assert cfg["est_budget_5h_tokens"] is None
        assert cfg["est_budget_weekly_tokens"] is None
        assert cfg["duration_noop_floor_s"] == 300

    def test_operator_override(self, tmp_path: Path) -> None:
        custom_cfg = textwrap.dedent("""\
        schema: metabolism_budget.v1
        gate_policy:
          fivehour_done_pct: 70
          weekly_done_pct: 75
          weekly_key_stop_pct: 80
          manual_floor_pct: 85
          est_budget_5h_tokens: null
          est_budget_weekly_tokens: null
          duration_noop_floor_s: 600
        """)
        root = _make_root(tmp_path, custom_cfg)
        from engine.metabolism.budget_gate import load_budget_cfg  # noqa: PLC0415
        cfg = load_budget_cfg(root)
        assert cfg["fivehour_done_pct"] == 70
        assert cfg["manual_floor_pct"] == 85
        assert cfg["duration_noop_floor_s"] == 600
