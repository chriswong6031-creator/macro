"""Smoke tests for admin modules that have zero coverage elsewhere.

Parametrized import smoke covers every admin/*.py (excluding __main__).
Behaviour smoke covers modules with a clear read-only panel/summary/status
function that takes no required args — each is called against a tmp_path
fixture root to confirm fail-open contract (returns dict, does not raise,
artifacts absent → graceful degradation).

Import-only modules (why):
  - analytics_first_party : all data functions hit Supabase network
  - umami                 : data functions hit Umami Cloud API
  - ga4                   : data functions drive Google Analytics Data API
  - gitops                : status() shells out to git (subprocess)
  - github_config         : all write helpers hit GitHub Contents API
  - uptime_board          : probe_all() opens real HTTP sockets
  - system                : snapshot() reads /proc (Linux-only; degrades on macOS, ok)
  - services              : status() shells out to systemctl (Linux-only)

Behaviour smoke modules:
  - causal_lab        : panel() always ok=True, artifact-absent graceful
  - experiments       : panel() degrades (ok=False) without registry; ok=True when present
  - vector_override   : panel() degrades (ok=False) without artifact
  - users             : status() always returns a dict without hitting the network
  - analytics_first_party : status() always returns a dict without hitting the network
  - umami             : status() always returns a dict without hitting the network
  - ga4               : status() always returns a dict without hitting the network
  - actions           : append_action() writes to tmp_path, never raises
  - nw_lobe_descriptions : module exposes LOBE_DESCRIPTIONS dict (structural check)
  - paths             : ROOT / DATA / SITE / STATIC are Path objects
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

# Ensure the repo root is importable as a package root.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# ---------------------------------------------------------------------------
# Derive module list dynamically from admin/*.py (exclude __main__)
# ---------------------------------------------------------------------------

_ADMIN_DIR = _REPO / "admin"
_ALL_ADMIN_MODULES = sorted(
    f"admin.{p.stem}"
    for p in _ADMIN_DIR.glob("*.py")
    if p.stem not in ("__init__", "__main__", "__pycache__")
)

# ---------------------------------------------------------------------------
# 1. Parametrized import smoke
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("modname", _ALL_ADMIN_MODULES)
def test_import_smoke(modname: str) -> None:
    """Every admin/*.py must be importable without raising."""
    mod = importlib.import_module(modname)
    assert mod is not None


# ---------------------------------------------------------------------------
# 2. Helpers — path patching following test_admin_neural_web.py pattern
# ---------------------------------------------------------------------------

def _patch_causal_paths(mod, root: Path) -> dict:
    site = root / "site"
    data = root / "data"
    saved = {}
    patches = {
        "_LAB_PRIMARY":  site / "neuralwebdata" / "causal_lab_state.json",
        "_LAB_FALLBACK": data / "neuralweb" / "causal_lab_state.json",
        "_EDGES":        data / "neuralweb" / "causal_edges.jsonl",
        "_NULLS":        data / "neuralweb" / "causal_nulls.jsonl",
        "_MECHANISMS":   data / "neuralweb" / "causal_mechanisms.jsonl",
        "_AUDIT":        data / "neuralweb" / "causal_confluence_audit.json",
    }
    for attr, val in patches.items():
        saved[attr] = getattr(mod, attr)
        setattr(mod, attr, val)
    return saved


def _restore(mod, saved: dict) -> None:
    for attr, val in saved.items():
        setattr(mod, attr, val)


# ---------------------------------------------------------------------------
# 3. causal_lab behaviour smoke
# ---------------------------------------------------------------------------

class TestCausalLab:
    """panel() is always ok=True; fails-open when artifacts are absent."""

    def test_panel_absent_artifacts(self, tmp_path: Path) -> None:
        from admin import causal_lab
        saved = _patch_causal_paths(causal_lab, tmp_path)
        try:
            result = causal_lab.panel()
        finally:
            _restore(causal_lab, saved)
        assert isinstance(result, dict)
        assert result["ok"] is True
        # Fail-open contract: required top-level keys present even with no files
        for key in ("funnel", "latest_edges", "n_nulls", "is_context_only"):
            assert key in result, f"Missing key {key!r} in absent-artifact panel"

    def test_panel_with_primary_artifact(self, tmp_path: Path) -> None:
        from admin import causal_lab

        # Write a minimal causal_lab_state.json to the primary path
        primary = tmp_path / "site" / "neuralwebdata"
        primary.mkdir(parents=True)
        state = {
            "asof": "2026-07-17T00:00:00Z",
            "funnel": {"edges_by_verdict": {"screened": 2}, "total_edges": 2,
                       "nulls_count": 0, "mechanisms_by_status": {}, "total_mechanisms": 0},
            "causal_scan": {"cumulative_width": 5, "description": "test"},
            "frontier": {"total_cells": 10, "cells_by_state": {}, "target_families": [], "environments": []},
            "surprise_queue": {"size": 0, "stalest_source": "", "stalest_source_asof": ""},
            "llm_lane": {"status": "armed", "description": ""},
        }
        (primary / "causal_lab_state.json").write_text(json.dumps(state))

        saved = _patch_causal_paths(causal_lab, tmp_path)
        try:
            result = causal_lab.panel()
        finally:
            _restore(causal_lab, saved)

        assert result["ok"] is True
        assert result.get("error") is None or "not yet" not in result.get("error", "")

    def test_panel_never_raises(self, tmp_path: Path) -> None:
        from admin import causal_lab

        # Write a corrupt JSON file — panel must degrade, not raise
        primary = tmp_path / "site" / "neuralwebdata"
        primary.mkdir(parents=True)
        (primary / "causal_lab_state.json").write_text("{invalid json")

        saved = _patch_causal_paths(causal_lab, tmp_path)
        try:
            result = causal_lab.panel()
        finally:
            _restore(causal_lab, saved)

        assert isinstance(result, dict)
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# 4. experiments behaviour smoke
# ---------------------------------------------------------------------------

class TestExperiments:
    """panel() degrades (ok=False) without registry; ok=True when registry present."""

    def _patch(self, mod, root: Path) -> dict:
        site = root / "site"
        saved = {"_REGISTRY": mod._REGISTRY}
        mod._REGISTRY = site / "marketdata" / "experiments.json"
        return saved

    def test_panel_absent_registry(self, tmp_path: Path) -> None:
        from admin import experiments
        saved = self._patch(experiments, tmp_path)
        try:
            result = experiments.panel()
        finally:
            _restore(experiments, saved)
        assert isinstance(result, dict)
        # No registry → ok=False with a reason (fail-open but clearly degraded)
        assert result["ok"] is False
        assert "reason" in result

    def test_panel_with_registry(self, tmp_path: Path) -> None:
        from admin import experiments

        registry_dir = tmp_path / "site" / "marketdata"
        registry_dir.mkdir(parents=True)
        reg = {
            "as_of": "2026-07-17",
            "generated_at": "2026-07-17T00:00:00Z",
            "experiments": [
                {
                    "id": "exp-1",
                    "name": "Test experiment",
                    "status": "accruing",
                    "kind": "causal",
                    "priority": "high",
                    "come_back_on": "2026-09-01",
                    "ready": False,
                },
            ],
        }
        (registry_dir / "experiments.json").write_text(json.dumps(reg))

        saved = self._patch(experiments, tmp_path)
        try:
            result = experiments.panel()
        finally:
            _restore(experiments, saved)

        assert isinstance(result, dict)
        assert result["ok"] is True
        assert result["n"] == 1
        assert "experiments" in result
        assert "by_status" in result
        assert "ready_count" in result


# ---------------------------------------------------------------------------
# 5. vector_override behaviour smoke
# ---------------------------------------------------------------------------

class TestVectorOverride:
    """panel() degrades (ok=False) without artifact; ok=True when file present."""

    def _patch(self, mod, root: Path) -> dict:
        data = root / "data"
        saved = {"_ARTIFACT": mod._ARTIFACT, "_REENTRY": mod._REENTRY}
        mod._ARTIFACT = data / "vector" / "override_shadow.json"
        mod._REENTRY  = data / "vector" / "reentry_status.json"
        return saved

    def test_panel_absent_artifact(self, tmp_path: Path) -> None:
        from admin import vector_override
        saved = self._patch(vector_override, tmp_path)
        try:
            result = vector_override.panel()
        finally:
            _restore(vector_override, saved)
        assert isinstance(result, dict)
        assert result["ok"] is False
        assert "reason" in result

    def test_panel_with_artifact(self, tmp_path: Path) -> None:
        from admin import vector_override

        vec_dir = tmp_path / "data" / "vector"
        vec_dir.mkdir(parents=True)
        payload = {
            "generated_at": "2026-07-17 00:00",
            "n": 3,
            "pivot_mae": 0.04,
            "amplitude_dampening": 0.8,
        }
        (vec_dir / "override_shadow.json").write_text(json.dumps(payload))

        saved = self._patch(vector_override, tmp_path)
        try:
            result = vector_override.panel()
        finally:
            _restore(vector_override, saved)

        assert isinstance(result, dict)
        assert result["ok"] is True
        assert "age_hours" in result


# ---------------------------------------------------------------------------
# 6. users.status() — network-free dict
# ---------------------------------------------------------------------------

class TestUsers:
    """status() returns a configured/unconfigured dict without touching the network."""

    def test_status_shape(self) -> None:
        from admin import users
        result = users.status()
        assert isinstance(result, dict)
        assert "configured" in result
        assert "project_ref" in result
        assert "setup_steps" in result
        assert isinstance(result["setup_steps"], list)

    def test_status_no_pat_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
        from admin import users, settings
        monkeypatch.setattr(settings, "supabase_pat", lambda: None)
        result = users.status()
        assert result["configured"] is False
        assert result["reason"] is not None


# ---------------------------------------------------------------------------
# 7. analytics_first_party.status() — network-free dict
# ---------------------------------------------------------------------------

class TestAnalyticsFirstParty:
    """status() returns configured/unconfigured dict without touching the network."""

    def test_status_shape(self) -> None:
        from admin import analytics_first_party as afp
        result = afp.status()
        assert isinstance(result, dict)
        assert "configured" in result
        assert "project_ref" in result
        assert "setup_steps" in result
        assert isinstance(result["setup_steps"], list)

    def test_status_no_pat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from admin import analytics_first_party as afp, settings
        monkeypatch.setattr(settings, "supabase_pat", lambda: None)
        result = afp.status()
        assert result["configured"] is False


# ---------------------------------------------------------------------------
# 8. umami.status() — network-free dict
# ---------------------------------------------------------------------------

class TestUmami:
    """status() returns configured/unconfigured dict without touching the network."""

    def test_status_shape(self) -> None:
        from admin import umami
        result = umami.status()
        assert isinstance(result, dict)
        assert "configured" in result
        assert "tag_installed" in result
        assert "setup_steps" in result
        assert isinstance(result["setup_steps"], list)

    def test_status_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from admin import umami, settings
        monkeypatch.setattr(settings, "umami_api_key", lambda: None)
        result = umami.status()
        assert result["configured"] is False


# ---------------------------------------------------------------------------
# 9. ga4.status() — network-free dict
# ---------------------------------------------------------------------------

class TestGa4:
    """status() returns a dict; never touches the network (library check only)."""

    def test_status_shape(self) -> None:
        from admin import ga4
        result = ga4.status()
        assert isinstance(result, dict)
        assert "configured" in result
        assert "measurement_id" in result
        assert result["measurement_id"] == "G-BZTZ9W1BBB"
        assert "setup_steps" in result

    def test_status_no_creds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GA4_PROPERTY_ID", raising=False)
        monkeypatch.delenv("GA4_SA_JSON", raising=False)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        from admin import ga4
        result = ga4.status()
        assert result["configured"] is False


# ---------------------------------------------------------------------------
# 10. gitops.status() — import-only (shells out to git)
# ---------------------------------------------------------------------------

def test_gitops_import_smoke() -> None:
    """gitops imports cleanly; status() is not called here (subprocess)."""
    from admin import gitops  # noqa: F401
    assert hasattr(gitops, "status")
    assert callable(gitops.status)


# ---------------------------------------------------------------------------
# 11. uptime_board.probe_all() — import-only (opens real HTTP sockets)
# ---------------------------------------------------------------------------

def test_uptime_board_import_smoke() -> None:
    """uptime_board imports cleanly; TARGETS list is non-empty."""
    from admin import uptime_board
    assert isinstance(uptime_board.TARGETS, list)
    assert len(uptime_board.TARGETS) > 0
    # Each target is a 3-tuple (label, url, expected_status|None)
    for label, url, expected in uptime_board.TARGETS:
        assert isinstance(label, str) and label
        assert url.startswith("https://")


# ---------------------------------------------------------------------------
# 12. system.snapshot() — degrades on non-Linux without raising
# ---------------------------------------------------------------------------

def test_system_snapshot_never_raises() -> None:
    """snapshot() returns a dict with 'available' on any platform."""
    from admin import system
    result = system.snapshot()
    assert isinstance(result, dict)
    assert "available" in result
    # cpu and disk are always present (os-independent)
    assert "cpu" in result
    assert "disk" in result


# ---------------------------------------------------------------------------
# 13. services.status() — degrades gracefully without systemctl
# ---------------------------------------------------------------------------

def test_services_status_degrades_without_systemctl() -> None:
    """status() returns {available: False} when systemctl is absent."""
    from admin import services
    result = services.status()
    assert isinstance(result, dict)
    assert "available" in result
    if not result["available"]:
        assert "services" in result  # empty list provided
        assert result["services"] == []


# ---------------------------------------------------------------------------
# 14. actions.append_action() — writes to monkeypatched path, never raises
# ---------------------------------------------------------------------------

class TestActions:
    """append_action writes to the ledger and never raises on missing dir."""

    def _patch_ledger(self, mod, ledger_path: Path) -> None:
        mod._ledger_path = lambda: ledger_path

    def test_append_valid_action(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from admin import actions
        ledger = tmp_path / "data" / "operator" / "action_ledger.jsonl"
        monkeypatch.setattr(actions, "_ledger_path", lambda: ledger)

        row = actions.append_action(
            surface="exp-123",
            action="acted",
            direction_note="test note",
        )
        assert isinstance(row, dict)
        assert row["actor"] == "operator"
        assert row["action"] == "acted"
        assert row["surface"] == "exp-123"
        assert "ts" in row
        assert ledger.exists()
        written = [json.loads(line) for line in ledger.read_text().splitlines()]
        assert len(written) == 1
        assert written[0]["direction_note"] == "test note"

    def test_append_never_raises_on_bad_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from admin import actions

        def bad_path():
            return Path("/this/path/does/not/exist/action_ledger.jsonl")

        monkeypatch.setattr(actions, "_ledger_path", bad_path)
        # Must not raise — log-and-drop contract
        row = actions.append_action("surf", "dismissed", "note")
        assert isinstance(row, dict)

    def test_note_is_capped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from admin import actions
        ledger = tmp_path / "action_ledger.jsonl"
        monkeypatch.setattr(actions, "_ledger_path", lambda: ledger)

        long_note = "x" * 500
        row = actions.append_action("surf", "dismissed", long_note)
        assert len(row["direction_note"]) <= actions.NOTE_MAX_CHARS


# ---------------------------------------------------------------------------
# 15. nw_lobe_descriptions structural check
# ---------------------------------------------------------------------------

def test_nw_lobe_descriptions_structure() -> None:
    """LOBE_DESCRIPTIONS is a non-empty dict; every entry has short + full + src_fp."""
    from admin import nw_lobe_descriptions as nld
    assert isinstance(nld.LOBE_DESCRIPTIONS, dict)
    assert len(nld.LOBE_DESCRIPTIONS) > 0
    for lobe_id, desc in nld.LOBE_DESCRIPTIONS.items():
        assert "short" in desc, f"{lobe_id}: missing 'short'"
        assert "full"  in desc, f"{lobe_id}: missing 'full'"
        assert "src_fp" in desc, f"{lobe_id}: missing 'src_fp'"


# ---------------------------------------------------------------------------
# 16. paths module structural check
# ---------------------------------------------------------------------------

def test_paths_module() -> None:
    """admin.paths exposes ROOT / DATA / SITE / STATIC as Path objects."""
    from admin import paths
    for attr in ("ROOT", "DATA", "SITE", "STATIC"):
        val = getattr(paths, attr)
        assert isinstance(val, Path), f"admin.paths.{attr} is not a Path"


# ---------------------------------------------------------------------------
# 17. github_config import-only (all helpers hit GitHub API)
# ---------------------------------------------------------------------------

def test_github_config_import_smoke() -> None:
    """github_config imports cleanly; available() returns bool without network."""
    from admin import github_config
    # available() depends on token + repo — may be True or False in CI
    result = github_config.available()
    assert isinstance(result, bool)
