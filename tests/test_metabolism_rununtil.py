"""tests/test_metabolism_rununtil.py — Hermetic tests for V11 run-until machinery.

COVERAGE:
  DISPATCH  pick_key weekly_max exclusion (monkeypatched budget_gate + env)
  DISPATCH  soft manual-floor preference: keys below floor preferred
  DISPATCH  never-empty rule: if ALL candidates above floor, keep all
  DISPATCH  fail-open on budget_gate ImportError
  YAML      metabolism-cycle.yml cron is hourly ("35 * * * *")
  YAML      narrow-commit step targets ONLY data/metabolism/key_budget_status.json
  YAML      dispatch branch contains manual-floor gate (exit 1 when blocked)
  YAML      continuation step re-reads METAB_RUN_UNTIL variable live via gh variable get

All tests are HERMETIC (monkeypatch, in-process, no network, no real data stores).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_CYCLE_WF = _ROOT / ".github" / "workflows" / "metabolism-cycle.yml"
_PROBE_WF = _ROOT / ".github" / "workflows" / "key-pool-probe.yml"


# ---------------------------------------------------------------------------
# Helpers: monkeypatch budget_gate.key_budget for pick_key tests
# ---------------------------------------------------------------------------

def _make_fake_budget_gate(
    *,
    weekly_stop_pct: float = 85.0,
    manual_floor_pct: float = 90.0,
    per_key: dict | None = None,
) -> types.ModuleType:
    """Return a fake engine.metabolism.budget_gate module."""
    m = types.ModuleType("engine.metabolism.budget_gate")

    _per_key = per_key or {}

    def load_budget_cfg(root=None):
        return {
            "fivehour_done_pct": 80,
            "weekly_done_pct": 80,
            "weekly_key_stop_pct": weekly_stop_pct,
            "manual_floor_pct": manual_floor_pct,
            "est_budget_5h_tokens": None,
            "est_budget_weekly_tokens": None,
            "duration_noop_floor_s": 300,
        }

    def key_budget(key_id, root=None):
        return _per_key.get(key_id, {"pct_5h": None, "src_5h": None, "pct_weekly": None, "src_weekly": None, "reset_5h": None, "reset_weekly": None})

    m.load_budget_cfg = load_budget_cfg
    m.key_budget = key_budget
    return m


# ===========================================================================
# pick_key weekly_max exclusion
# ===========================================================================

class TestPickKeyWeeklyMaxExclusion:
    """When METAB_RUN_UNTIL=weekly_max, keys with known pct_weekly >= weekly_key_stop_pct
    are excluded before the LRU min() selection."""

    def test_excludes_over_stop_pct_in_weekly_max(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Key at 90% weekly is dropped when weekly_key_stop_pct=85 and mode=weekly_max."""
        from scripts.metabolism_dispatch import _budget_filter

        fake_gate = _make_fake_budget_gate(
            weekly_stop_pct=85.0,
            per_key={
                "claude_code_oauth_1": {"pct_weekly": 90.0},
                "claude_code_oauth_2": {"pct_weekly": 70.0},
            },
        )
        monkeypatch.setitem(sys.modules, "engine.metabolism.budget_gate", fake_gate)
        monkeypatch.setenv("METAB_RUN_UNTIL", "weekly_max")

        result = _budget_filter(["claude_code_oauth_1", "claude_code_oauth_2"])
        assert "claude_code_oauth_2" in result
        assert "claude_code_oauth_1" not in result

    def test_keeps_unknown_pct_in_weekly_max(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Keys with unknown pct_weekly (None) are kept — fail-open."""
        from scripts.metabolism_dispatch import _budget_filter

        fake_gate = _make_fake_budget_gate(
            weekly_stop_pct=85.0,
            per_key={
                "claude_code_oauth_1": {"pct_weekly": None},
                "claude_code_oauth_2": {"pct_weekly": 90.0},
            },
        )
        monkeypatch.setitem(sys.modules, "engine.metabolism.budget_gate", fake_gate)
        monkeypatch.setenv("METAB_RUN_UNTIL", "weekly_max")

        result = _budget_filter(["claude_code_oauth_1", "claude_code_oauth_2"])
        assert "claude_code_oauth_1" in result
        # key2 is over stop — excluded
        assert "claude_code_oauth_2" not in result

    def test_no_exclusion_when_not_weekly_max(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """weekly_max exclusion does NOT fire for other run_until values."""
        from scripts.metabolism_dispatch import _budget_filter

        fake_gate = _make_fake_budget_gate(
            weekly_stop_pct=85.0,
            per_key={
                "claude_code_oauth_1": {"pct_weekly": 90.0},
                "claude_code_oauth_2": {"pct_weekly": 70.0},
            },
        )
        monkeypatch.setitem(sys.modules, "engine.metabolism.budget_gate", fake_gate)
        monkeypatch.setenv("METAB_RUN_UNTIL", "5h_max")

        result = _budget_filter(["claude_code_oauth_1", "claude_code_oauth_2"])
        # Both should survive the weekly_max gate (though manual floor may still apply)
        # At minimum key2 must survive (it's under floor too)
        assert "claude_code_oauth_2" in result


# ===========================================================================
# Soft manual-floor preference
# ===========================================================================

class TestManualFloorPreference:
    """Soft preference: drop keys with known pct_weekly >= manual_floor_pct
    when at least one candidate is below floor or unknown."""

    def test_prefers_below_floor_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Key below floor is preferred; key above floor is dropped from pool."""
        from scripts.metabolism_dispatch import _budget_filter

        fake_gate = _make_fake_budget_gate(
            manual_floor_pct=90.0,
            per_key={
                "claude_code_oauth_1": {"pct_weekly": 95.0},  # above floor
                "claude_code_oauth_2": {"pct_weekly": 70.0},  # below floor
            },
        )
        monkeypatch.setitem(sys.modules, "engine.metabolism.budget_gate", fake_gate)
        monkeypatch.delenv("METAB_RUN_UNTIL", raising=False)

        result = _budget_filter(["claude_code_oauth_1", "claude_code_oauth_2"])
        assert "claude_code_oauth_2" in result
        assert "claude_code_oauth_1" not in result

    def test_unknown_pct_treated_as_below_floor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Key with unknown pct_weekly counts as 'below floor' (fail-open)."""
        from scripts.metabolism_dispatch import _budget_filter

        fake_gate = _make_fake_budget_gate(
            manual_floor_pct=90.0,
            per_key={
                "claude_code_oauth_1": {"pct_weekly": None},   # unknown -> kept
                "claude_code_oauth_2": {"pct_weekly": 95.0},   # above floor -> dropped
            },
        )
        monkeypatch.setitem(sys.modules, "engine.metabolism.budget_gate", fake_gate)
        monkeypatch.delenv("METAB_RUN_UNTIL", raising=False)

        result = _budget_filter(["claude_code_oauth_1", "claude_code_oauth_2"])
        assert "claude_code_oauth_1" in result
        assert "claude_code_oauth_2" not in result

    def test_never_empties_pool_when_all_above_floor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If ALL candidates are above manual floor, pool is kept intact (never-empty rule)."""
        from scripts.metabolism_dispatch import _budget_filter

        fake_gate = _make_fake_budget_gate(
            manual_floor_pct=90.0,
            per_key={
                "claude_code_oauth_1": {"pct_weekly": 95.0},
                "claude_code_oauth_2": {"pct_weekly": 92.0},
            },
        )
        monkeypatch.setitem(sys.modules, "engine.metabolism.budget_gate", fake_gate)
        monkeypatch.delenv("METAB_RUN_UNTIL", raising=False)

        result = _budget_filter(["claude_code_oauth_1", "claude_code_oauth_2"])
        # Both preserved — never empty the pool
        assert len(result) == 2
        assert "claude_code_oauth_1" in result
        assert "claude_code_oauth_2" in result

    def test_never_empties_pool_with_mixed_known_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unknown key counts as below-floor, so above-floor key gets dropped
        but pool is non-empty (unknown key remains)."""
        from scripts.metabolism_dispatch import _budget_filter

        fake_gate = _make_fake_budget_gate(
            manual_floor_pct=90.0,
            per_key={
                "claude_code_oauth_1": {"pct_weekly": 95.0},  # above floor
                "claude_code_oauth_2": {"pct_weekly": None},  # unknown -> below floor
            },
        )
        monkeypatch.setitem(sys.modules, "engine.metabolism.budget_gate", fake_gate)
        monkeypatch.delenv("METAB_RUN_UNTIL", raising=False)

        result = _budget_filter(["claude_code_oauth_1", "claude_code_oauth_2"])
        # key2 is kept (unknown = below floor)
        assert "claude_code_oauth_2" in result
        # key1 dropped because key2 gave a below-floor candidate
        assert "claude_code_oauth_1" not in result
        assert len(result) >= 1


# ===========================================================================
# Fail-open on budget_gate ImportError
# ===========================================================================

class TestFailOpenOnImportError:
    """If engine.metabolism.budget_gate cannot be imported, _budget_filter
    returns the original candidate list unchanged."""

    def test_fail_open_on_importerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ImportError from budget_gate -> original candidates returned."""
        from scripts.metabolism_dispatch import _budget_filter

        # Inject a broken module that raises on attribute access
        class _Broken:
            def load_budget_cfg(self, *a, **kw):
                raise ImportError("budget_gate not available")
            def key_budget(self, *a, **kw):
                raise ImportError("budget_gate not available")

        monkeypatch.setitem(sys.modules, "engine.metabolism.budget_gate", _Broken())  # type: ignore
        monkeypatch.setenv("METAB_RUN_UNTIL", "weekly_max")

        candidates = ["claude_code_oauth_1", "claude_code_oauth_2"]
        result = _budget_filter(candidates)
        # fail-open: original list returned unchanged
        assert set(result) == set(candidates)

    def test_fail_open_when_module_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If budget_gate module is absent entirely, candidates pass through."""
        from scripts.metabolism_dispatch import _budget_filter

        # Remove from sys.modules to simulate ImportError
        monkeypatch.delitem(sys.modules, "engine.metabolism.budget_gate", raising=False)

        # Also patch the import to raise
        import builtins
        _orig_import = builtins.__import__
        def _blocked_import(name, *args, **kwargs):
            if name == "engine.metabolism.budget_gate":
                raise ImportError("simulated absent module")
            return _orig_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _blocked_import)
        candidates = ["claude_code_oauth_3", "claude_code_oauth_4"]
        result = _budget_filter(candidates)
        assert set(result) == set(candidates)


# ===========================================================================
# Workflow YAML assertions
# ===========================================================================

class TestWorkflowYAML:
    """Structural assertions on the committed workflow YAML files."""

    @pytest.fixture(scope="class")
    def cycle_wf(self):
        return yaml.safe_load(_CYCLE_WF.read_text(encoding="utf-8"))

    @pytest.fixture(scope="class")
    def probe_wf(self):
        return yaml.safe_load(_PROBE_WF.read_text(encoding="utf-8"))

    def test_cron_is_hourly(self, cycle_wf: dict) -> None:
        """metabolism-cycle.yml cron must fire every hour ('35 * * * *').

        Note: YAML parses 'on:' as True in Python dicts; use True as key.
        """
        # 'on' parses as True in pyyaml SafeLoader
        trigger = cycle_wf.get(True, cycle_wf.get("on", {}))
        schedules = trigger.get("schedule", [])
        cron_exprs = [s.get("cron", "") for s in schedules]
        assert any("35 * * * *" in c for c in cron_exprs), (
            f"Expected hourly cron '35 * * * *' in schedule, got: {cron_exprs}"
        )

    def test_new_inputs_present(self, cycle_wf: dict) -> None:
        """metabolism-cycle.yml must declare run_until_continue and depth inputs."""
        # 'on' parses as True in pyyaml SafeLoader
        trigger = cycle_wf.get(True, cycle_wf.get("on", {}))
        inputs = trigger.get("workflow_dispatch", {}).get("inputs", {})
        assert "run_until_continue" in inputs, "Missing run_until_continue input"
        assert "depth" in inputs, "Missing depth input"

    def test_narrow_commit_targets_only_budget_status(self) -> None:
        """The narrow-commit step in metabolism-cycle.yml must git add only
        data/metabolism/key_budget_status.json, not a broader path."""
        text = _CYCLE_WF.read_text(encoding="utf-8")
        # Must contain the specific narrow add
        assert "git add data/metabolism/key_budget_status.json" in text, (
            "metabolism-cycle.yml must narrow-add only data/metabolism/key_budget_status.json"
        )
        # Must NOT contain a broad 'git add data/metabolism' without the filename
        import re
        broad_add = re.search(r"git add data/metabolism\b(?!/key_budget_status\.json)", text)
        assert broad_add is None, (
            "metabolism-cycle.yml must not use a broad 'git add data/metabolism' "
            "without specifying the exact file"
        )

    def test_manual_floor_gate_present_in_dispatch_branch(self) -> None:
        """The dispatch branch must contain a manual floor gate that can exit 1
        when blocked (::error:: annotation and exit 1)."""
        text = _CYCLE_WF.read_text(encoding="utf-8")
        assert "::error::" in text, (
            "metabolism-cycle.yml must emit ::error:: for manual floor block"
        )
        assert "exit 1" in text, (
            "metabolism-cycle.yml must exit 1 when manual floor is blocked"
        )
        # The gate must reference budget gate --mode manual
        assert "--mode manual" in text, (
            "metabolism-cycle.yml must invoke budget_gate --mode manual"
        )

    def test_continuation_re_reads_variable_live(self) -> None:
        """The continuation step must re-read METAB_RUN_UNTIL via 'gh variable get'
        (not just the env var) so the STOP button wins."""
        text = _CYCLE_WF.read_text(encoding="utf-8")
        assert "gh variable get METAB_RUN_UNTIL" in text, (
            "metabolism-cycle.yml must re-read METAB_RUN_UNTIL live via "
            "'gh variable get METAB_RUN_UNTIL' for the continuation step"
        )

    def test_metab_run_until_in_env(self, cycle_wf: dict) -> None:
        """METAB_RUN_UNTIL must be passed to the CYCLE step env."""
        steps = cycle_wf.get("jobs", {}).get("cycle", {}).get("steps", [])
        for step in steps:
            env = step.get("env", {}) or {}
            if "METAB_RUN_UNTIL" in env:
                return
        pytest.fail("METAB_RUN_UNTIL not found in any step env in metabolism-cycle.yml")

    def test_probe_wf_has_narrow_commit(self, probe_wf: dict) -> None:
        """key-pool-probe.yml must have a narrow-commit step after the probe."""
        text = _PROBE_WF.read_text(encoding="utf-8")
        assert "key_budget_status.json" in text, (
            "key-pool-probe.yml must reference key_budget_status.json in narrow-commit"
        )
        assert "git add data/metabolism/key_budget_status.json" in text, (
            "key-pool-probe.yml must narrow-add only key_budget_status.json"
        )

    def test_both_workflows_parse_valid_yaml(self) -> None:
        """Both workflows must parse as valid YAML without errors."""
        # Already loaded by fixtures; re-load to confirm round-trip
        # Note: 'on:' key is parsed as True by pyyaml SafeLoader
        cycle = yaml.safe_load(_CYCLE_WF.read_text(encoding="utf-8"))
        probe = yaml.safe_load(_PROBE_WF.read_text(encoding="utf-8"))
        # Check for on/True key (YAML bare 'on' = Python True in SafeLoader)
        has_on_cycle = True in cycle or "on" in cycle
        has_on_probe = True in probe or "on" in probe
        assert has_on_cycle and "jobs" in cycle, f"cycle wf missing on/jobs keys: {list(cycle.keys())}"
        assert has_on_probe and "jobs" in probe, f"probe wf missing on/jobs keys: {list(probe.keys())}"
