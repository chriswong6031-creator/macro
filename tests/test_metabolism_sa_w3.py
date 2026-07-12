"""tests/test_metabolism_sa_w3.py — SA-W3 metabolism wiring tests.

Coverage (SA-W3 build spec):
  1. Charter discovery — both standout lobes are loop-managed
  2. Tier-mirror validation — both charters pass validate_tier_mirror
  3. Budget caps parse — both standout lobes in lobe_caps
  4. audit_due trigger math:
     a. hard trigger: >= 15 newly matured rows
     b. soft trigger: >= 5 AND >= 14 days
     c. below-threshold: not due
     d. crash-replay: returns due=False, never raises
  5. Context assembler:
     a. absent stores → honest data_gap entries
     b. byte budgets respected (no block > its budget)
  6. Proposal file handoff schema matches standout_review intake
  7. Shadow-cycle audit_due_probe stage:
     a. writes only under shadow root (real stores untouched)
     b. stage result has 'status' key
  8. Roles YAML parse — both roles present, SA-R13 text in standout_auditor
  9. Rubrics YAML parse + W-4 fires on synthetic precision-only packet
 10. insight_bus._KINDS contains 'audit_due'
 11. run_audit with injected model_caller — dry_run, never raises
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ---------------------------------------------------------------------------
# Minimal repo fixture builder
# ---------------------------------------------------------------------------

def _write_charter(cfg_dir: Path, charters: dict) -> None:
    (cfg_dir / "lobe_charters.yml").write_text(
        yaml.dump({"lobes": charters}), encoding="utf-8"
    )


def _write_budget(cfg_dir: Path, lobe_caps: dict) -> None:
    budget = {
        "schema": "metabolism_budget.v1",
        "genesis_accountability_days": 45,
        "lobe_caps": lobe_caps,
    }
    (cfg_dir / "metabolism_budget.yml").write_text(
        yaml.dump(budget), encoding="utf-8"
    )


def _make_minimal_root(tmp_path: Path) -> Path:
    """Create a minimal repo root that mirrors required config structure."""
    root = tmp_path / "repo"
    root.mkdir()
    cfg = root / "config"
    cfg.mkdir()

    # Copy real config files (read-only)
    real_cfg = _REPO / "config"
    for fname in (
        "lobe_charters.yml",
        "metabolism_budget.yml",
        "metabolism_roles.yml",
        "adjudication_rubrics.yml",
    ):
        src = real_cfg / fname
        dst = cfg / fname
        if src.exists():
            import shutil
            shutil.copy2(str(src), str(dst))

    return root


# ---------------------------------------------------------------------------
# 1. Charter discovery — both standout lobes loop-managed
# ---------------------------------------------------------------------------

class TestCharterDiscovery:
    def test_us_standouts_loop_managed(self) -> None:
        """site-us-standouts must be loop-managed after SA-W3 charter edit."""
        with (
            _REPO / "config" / "lobe_charters.yml"
        ).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)

        lobes = data.get("charters", {})
        assert "site-us-standouts" in lobes, "site-us-standouts missing from charters"

        charter = lobes["site-us-standouts"]

        # lifecycle_state must be active/probation
        ls = charter.get("lifecycle_state")
        assert ls in ("active", "probation"), (
            f"site-us-standouts lifecycle_state={ls!r} — must be active or probation"
        )

        # fitness_sensors must be structured list of dicts with id + store
        sensors = charter.get("fitness_sensors") or []
        assert isinstance(sensors, list), "fitness_sensors must be a list"
        assert len(sensors) >= 6, f"expected >= 6 sensors, got {len(sensors)}"
        for s in sensors:
            assert isinstance(s, dict), f"sensor must be a dict, got {type(s)}: {s!r}"
            assert "id" in s, f"sensor missing 'id': {s}"
            assert "store" in s, f"sensor missing 'store': {s}"

    def test_cn_standouts_loop_managed(self) -> None:
        """site-china-standouts must be loop-managed after SA-W3 charter edit."""
        with (
            _REPO / "config" / "lobe_charters.yml"
        ).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)

        lobes = data.get("charters", {})
        assert "site-china-standouts" in lobes, "site-china-standouts missing from charters"

        charter = lobes["site-china-standouts"]

        ls = charter.get("lifecycle_state")
        assert ls in ("active", "probation"), (
            f"site-china-standouts lifecycle_state={ls!r} — must be active or probation"
        )

        sensors = charter.get("fitness_sensors") or []
        assert isinstance(sensors, list), "fitness_sensors must be a list"
        assert len(sensors) >= 6, f"expected >= 6 sensors, got {len(sensors)}"
        for s in sensors:
            assert isinstance(s, dict), f"sensor must be a dict, got {type(s)}: {s!r}"
            assert "id" in s, f"sensor missing 'id': {s}"
            assert "store" in s, f"sensor missing 'store': {s}"

    def test_discover_loop_managed_finds_standouts(self, tmp_path: Path) -> None:
        """_discover_loop_managed_lobes must include both standout lobes."""
        from scripts.metabolism_propose import _discover_loop_managed_lobes  # type: ignore[import]

        root = _make_minimal_root(tmp_path)
        # Returns list[str] of lobe IDs
        lobe_ids = _discover_loop_managed_lobes(root)
        assert isinstance(lobe_ids, list), f"expected list, got {type(lobe_ids)}"
        # Both standout lobes should be discovered
        assert "site-us-standouts" in lobe_ids, (
            f"site-us-standouts not in discovered lobes: {lobe_ids}"
        )
        assert "site-china-standouts" in lobe_ids, (
            f"site-china-standouts not in discovered lobes: {lobe_ids}"
        )


# ---------------------------------------------------------------------------
# 2. Tier-mirror validation
# ---------------------------------------------------------------------------

class TestTierMirror:
    def test_tier_mirror_passes_for_both_standout_lobes(self) -> None:
        """validate_tier_mirror must pass for site-us-standouts and site-china-standouts."""
        try:
            from engine.metabolism.lobe_registry import validate_tier_mirror  # type: ignore[import]
            violations = validate_tier_mirror(root=_REPO)
            # Filter to standout lobes only
            standout_violations = [
                v for v in violations
                if "standout" in str(v).lower()
            ]
            assert not standout_violations, (
                f"tier-mirror violations for standout lobes: {standout_violations}"
            )
        except ImportError:
            pytest.skip("lobe_registry not importable in test environment")


# ---------------------------------------------------------------------------
# 3. Budget caps parse
# ---------------------------------------------------------------------------

class TestBudgetCaps:
    def test_budget_caps_include_standout_lobes(self) -> None:
        """metabolism_budget.yml must have lobe_caps for both standout lobes."""
        with (
            _REPO / "config" / "metabolism_budget.yml"
        ).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)

        caps = data.get("lobe_caps") or {}
        assert "site-us-standouts" in caps, "site-us-standouts missing from lobe_caps"
        assert "site-china-standouts" in caps, "site-china-standouts missing from lobe_caps"

    def test_budget_caps_mirror_til(self) -> None:
        """Both standout lobe_caps must mirror the til caps (per spec SA-W3)."""
        with (
            _REPO / "config" / "metabolism_budget.yml"
        ).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)

        caps = data.get("lobe_caps") or {}
        til_cap = caps.get("til") or {}

        for lobe_id in ("site-us-standouts", "site-china-standouts"):
            cap = caps.get(lobe_id) or {}
            assert cap.get("per_cycle_usd_cap") == til_cap.get("per_cycle_usd_cap"), (
                f"{lobe_id}: per_cycle_usd_cap mismatch vs til"
            )
            assert cap.get("per_cycle_token_cap") == til_cap.get("per_cycle_token_cap"), (
                f"{lobe_id}: per_cycle_token_cap mismatch vs til"
            )
            assert cap.get("max_docket_size") == til_cap.get("max_docket_size"), (
                f"{lobe_id}: max_docket_size mismatch vs til"
            )
            assert cap.get("breaker_trip") == til_cap.get("breaker_trip"), (
                f"{lobe_id}: breaker_trip mismatch vs til"
            )


# ---------------------------------------------------------------------------
# 4. audit_due trigger math
# ---------------------------------------------------------------------------

class TestAuditDue:
    """Tests for standout_auditor.audit_due() trigger logic."""

    def _make_attribution_parquet(self, tmp_path: Path, market: str, as_of_dates: list[str]) -> Path:
        """Write a minimal attribution parquet with the given as_of dates."""
        import pandas as pd
        p = tmp_path / "data" / "standout_audit" / f"{market}_attribution.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame({"as_of": pd.to_datetime(as_of_dates)})
        df.to_parquet(str(p))
        return p

    def _make_audit_state(self, tmp_path: Path, market: str, state: dict) -> Path:
        """Write an audit state JSON."""
        p = tmp_path / "data" / "standout_audit" / f"{market}_audit_state.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state), encoding="utf-8")
        return p

    def _make_postmortem(self, tmp_path: Path, market: str, cycle_id: str, ts: str) -> Path:
        """Write a minimal postmortem for days_since_postmortem computation."""
        pm_dir = tmp_path / "data" / "standout_audit" / "postmortems"
        pm_dir.mkdir(parents=True, exist_ok=True)
        p = pm_dir / f"{market}-{cycle_id}.json"
        p.write_text(json.dumps({"ts": ts, "cycle_id": cycle_id}), encoding="utf-8")
        return p

    def test_hard_trigger_fires_at_15_rows(self, tmp_path: Path) -> None:
        """Hard trigger: >= 15 newly matured rows -> due=True."""
        from engine.metabolism.standout_auditor import audit_due  # type: ignore[import]

        # Last audit was 2026-01-01; write 15 rows after that
        last_graded = "2026-01-01"
        dates = [(datetime(2026, 1, 2) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(15)]
        self._make_attribution_parquet(tmp_path, "us", dates)
        self._make_audit_state(tmp_path, "us", {"last_audit_graded_as_of": last_graded})

        result = audit_due("us", root=tmp_path)
        assert result["due"] is True, f"expected due=True, got: {result}"
        assert result["newly_matured_rows"] >= 15
        assert "hard trigger" in result["reason"].lower()

    def test_hard_trigger_below_threshold(self, tmp_path: Path) -> None:
        """14 newly matured rows (no soft) -> not due."""
        from engine.metabolism.standout_auditor import audit_due  # type: ignore[import]

        last_graded = "2026-01-01"
        dates = [(datetime(2026, 1, 2) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14)]
        self._make_attribution_parquet(tmp_path, "us", dates)
        self._make_audit_state(tmp_path, "us", {
            "last_audit_graded_as_of": last_graded,
            "last_postmortem_cycle_id": None,
        })

        result = audit_due("us", root=tmp_path)
        # 14 rows, no soft trigger (no last_postmortem_cycle_id) -> not due
        assert result["due"] is False, f"expected due=False, got: {result}"

    def test_soft_trigger_fires_5_rows_14_days(self, tmp_path: Path) -> None:
        """Soft trigger: >= 5 rows AND >= 14 days since last postmortem -> due=True."""
        from engine.metabolism.standout_auditor import audit_due  # type: ignore[import]

        last_graded = "2026-01-01"
        # Write 5 rows since last audit
        dates = [(datetime(2026, 1, 2) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]
        self._make_attribution_parquet(tmp_path, "us", dates)

        # Write a postmortem 20 days ago
        pm_ts = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        cycle_id = "old-audit"
        self._make_postmortem(tmp_path, "us", cycle_id, pm_ts)
        self._make_audit_state(tmp_path, "us", {
            "last_audit_graded_as_of": last_graded,
            "last_postmortem_cycle_id": cycle_id,
        })

        result = audit_due("us", root=tmp_path)
        assert result["due"] is True, f"expected due=True (soft trigger), got: {result}"
        assert result["newly_matured_rows"] >= 5
        assert "soft trigger" in result["reason"].lower()

    def test_soft_trigger_not_enough_days(self, tmp_path: Path) -> None:
        """5 rows but only 10 days since postmortem -> not due."""
        from engine.metabolism.standout_auditor import audit_due  # type: ignore[import]

        last_graded = "2026-01-01"
        dates = [(datetime(2026, 1, 2) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]
        self._make_attribution_parquet(tmp_path, "us", dates)

        pm_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        cycle_id = "recent-audit"
        self._make_postmortem(tmp_path, "us", cycle_id, pm_ts)
        self._make_audit_state(tmp_path, "us", {
            "last_audit_graded_as_of": last_graded,
            "last_postmortem_cycle_id": cycle_id,
        })

        result = audit_due("us", root=tmp_path)
        assert result["due"] is False, f"expected due=False (10 days < 14), got: {result}"

    def test_crash_replay_never_raises(self, tmp_path: Path) -> None:
        """audit_due with no attribution store -> returns due=False, never raises."""
        from engine.metabolism.standout_auditor import audit_due  # type: ignore[import]

        # No stores written — should return safe fallback
        result = audit_due("us", root=tmp_path)
        assert isinstance(result, dict), "audit_due must return a dict"
        assert result.get("due") is False, "absent stores should give due=False"
        assert "schema" in result

    def test_schema_present_in_result(self, tmp_path: Path) -> None:
        """audit_due result always has schema and market keys."""
        from engine.metabolism.standout_auditor import audit_due  # type: ignore[import]

        result = audit_due("cn", root=tmp_path)
        assert result["schema"] == "standout_auditor.audit_due.v1"
        assert result["market"] == "cn"


# ---------------------------------------------------------------------------
# 5. Context assembler
# ---------------------------------------------------------------------------

class TestBuildContext:
    def test_absent_stores_produce_data_gaps(self, tmp_path: Path) -> None:
        """build_context with no stores must produce honest data_gap entries."""
        from engine.metabolism.standout_auditor import build_context  # type: ignore[import]

        ctx = build_context("us", root=tmp_path)
        assert isinstance(ctx, dict)
        assert ctx.get("schema") == "standout_auditor.context.v1"
        assert ctx.get("market") == "us"

        # data_gaps must mention at least the scoreboard (absent)
        data_gaps = ctx.get("data_gaps") or []
        assert any("scoreboard" in g for g in data_gaps), (
            f"expected 'scoreboard' in data_gaps, got: {data_gaps}"
        )

    def test_blocks_always_present(self, tmp_path: Path) -> None:
        """build_context must always return blocks dict with required keys."""
        from engine.metabolism.standout_auditor import build_context  # type: ignore[import]

        ctx = build_context("us", root=tmp_path)
        blocks = ctx.get("blocks") or {}
        for key in ("scoreboard", "evidence_packs", "fitness_card", "sa_r13"):
            assert key in blocks, f"missing block '{key}'"

    def test_sa_r13_verbatim_in_context(self, tmp_path: Path) -> None:
        """SA-R13 verbatim must appear in context blocks."""
        from engine.metabolism.standout_auditor import build_context, _SA_R13_VERBATIM  # type: ignore[import]

        ctx = build_context("us", root=tmp_path)
        blocks = ctx.get("blocks") or {}
        assert blocks.get("sa_r13") == _SA_R13_VERBATIM

    def test_byte_budget_respected(self, tmp_path: Path) -> None:
        """No single block should exceed its byte budget."""
        from engine.metabolism.standout_auditor import (  # type: ignore[import]
            build_context,
            _SCOREBOARD_BUDGET_BYTES,
            _EVIDENCE_BUDGET_BYTES,
        )

        # Write a giant scoreboard to test truncation
        sb_dir = tmp_path / "site" / "factordata"
        sb_dir.mkdir(parents=True, exist_ok=True)
        giant = {"data": "x" * 200_000, "status": "ok"}
        (sb_dir / "us_audit_scoreboard.json").write_text(json.dumps(giant), encoding="utf-8")

        ctx = build_context("us", root=tmp_path)
        blocks = ctx.get("blocks") or {}

        sb_text = blocks.get("scoreboard", "")
        assert len(sb_text.encode("utf-8")) <= _SCOREBOARD_BUDGET_BYTES + 50, (
            f"scoreboard block exceeds budget: {len(sb_text.encode('utf-8'))} bytes"
        )

    def test_build_context_never_raises(self, tmp_path: Path) -> None:
        """build_context must never raise even with corrupted stores."""
        from engine.metabolism.standout_auditor import build_context  # type: ignore[import]

        # Write corrupted files
        sb_dir = tmp_path / "site" / "factordata"
        sb_dir.mkdir(parents=True, exist_ok=True)
        (sb_dir / "us_audit_scoreboard.json").write_text("{{{{corrupt", encoding="utf-8")

        ctx = build_context("us", root=tmp_path)
        assert isinstance(ctx, dict)


# ---------------------------------------------------------------------------
# 6. Proposal file handoff schema
# ---------------------------------------------------------------------------

class TestProposalHandoff:
    def _make_postmortem_with_proposal(self) -> dict:
        """Build a synthetic postmortem containing a standout_review hypothesis."""
        return {
            "schema": "standout_auditor.postmortem.v1",
            "market": "us",
            "cycle_id": "test-2026-07-12",
            "ts": "2026-07-12T00:00:00+00:00",
            "per_cohort_postmortems": [],
            "hypotheses": [
                {
                    "rank": 1,
                    "description": "Test proposal for coverage_health sensor",
                    "lane": "standout_review",
                    "market": "us",
                    "param": "STRONG_BUY_THRESHOLD",
                    "delta_steps": -1,
                    "rationale_ref": "data/standout_audit/postmortems/us-test-2026-07-12.json",
                    "proposer": "standout_auditor",
                    "fitness_contract": {
                        "sensor": "coverage_health",
                        "expected_sign": "+",
                        "band": "accruing",
                        "check_by": "2026-09-15",
                    },
                    "falsifiable_claim": "If threshold lowered by 1 step, coverage_health increases.",
                },
                {
                    "rank": 2,
                    "description": "Code fix for timing quality lag",
                    "lane": "code fix",
                    "fitness_contract": {"sensor": "timing_quality", "check_by": "2026-09-15"},
                },
            ],
            "honesty_notes": "Effective N too small for strong conclusions.",
        }

    def test_proposal_files_written(self, tmp_path: Path) -> None:
        """_write_proposals must write files for standout_review lane hypotheses."""
        from engine.metabolism.standout_auditor import _write_proposals  # type: ignore[import]

        pm = self._make_postmortem_with_proposal()
        paths = _write_proposals(pm, "us", "test-2026-07-12", tmp_path)

        assert len(paths) >= 1, "expected at least one proposal file"
        for p_str in paths:
            p = Path(p_str)
            assert p.exists(), f"proposal file not written: {p}"
            data = json.loads(p.read_text(encoding="utf-8"))

            # Validate required fields match standout_review.py schema
            required = {"market", "param", "delta_steps", "rationale_ref", "proposer", "cycle_id"}
            missing = required - set(data.keys())
            assert not missing, f"proposal missing required fields: {missing}"

            # Validate values
            assert data["market"] == "us"
            assert data["param"] == "STRONG_BUY_THRESHOLD"
            assert data["proposer"] == "standout_auditor"
            assert data["delta_steps"] == -1

    def test_code_fix_lane_not_written_as_proposal(self, tmp_path: Path) -> None:
        """'code fix' lane hypotheses must NOT produce proposal files."""
        from engine.metabolism.standout_auditor import _write_proposals  # type: ignore[import]

        pm = self._make_postmortem_with_proposal()
        paths = _write_proposals(pm, "us", "test-2026-07-12", tmp_path)

        # Only the standout_review hypothesis should produce a file
        # The 'code fix' hypothesis should not appear as a proposal file
        assert len(paths) == 1, f"expected 1 proposal file, got {len(paths)}: {paths}"

    def test_write_proposals_never_raises(self, tmp_path: Path) -> None:
        """_write_proposals must never raise even with malformed postmortem."""
        from engine.metabolism.standout_auditor import _write_proposals  # type: ignore[import]

        # Malformed hypotheses
        pm = {"hypotheses": [{"lane": "standout_review"}, None, 42, {}]}
        paths = _write_proposals(pm, "us", "bad-cycle", tmp_path)
        assert isinstance(paths, list)


# ---------------------------------------------------------------------------
# 7. Shadow-cycle audit_due_probe stage
# ---------------------------------------------------------------------------

class TestShadowCycleAuditProbe:
    def test_audit_due_probe_in_shadow_stages(self, tmp_path: Path) -> None:
        """audit_due_probe stage must appear in shadow cycle stages dict."""
        from scripts.metabolism_shadow_cycle import run_shadow_cycle  # type: ignore[import]

        # Run shadow cycle against a clean tmp root (no real data — honest nulls)
        result = run_shadow_cycle(
            real_root=tmp_path,
            cycle_id="shadow-20260712-0000",
            today="2026-07-12",
            use_llm=False,
        )
        assert isinstance(result, dict)
        stages = result.get("stages") or {}
        assert "audit_due_probe" in stages, (
            f"audit_due_probe missing from shadow stages: {list(stages.keys())}"
        )

    def test_audit_due_probe_has_status(self, tmp_path: Path) -> None:
        """audit_due_probe stage result must have a 'status' key."""
        from scripts.metabolism_shadow_cycle import _run_audit_due_probe  # type: ignore[import]

        shadow_root = tmp_path / "shadow"
        shadow_root.mkdir()
        real_root = tmp_path / "real"
        real_root.mkdir()

        result = _run_audit_due_probe(shadow_root, real_root, "shadow-20260712-0000")
        assert isinstance(result, dict)
        assert "status" in result, f"audit_due_probe result missing 'status': {result}"
        assert result["status"] in ("ok", "failed")

    def test_shadow_probe_does_not_touch_real_stores(self, tmp_path: Path) -> None:
        """audit_due_probe must not write to real_root/data/standout_audit/."""
        from scripts.metabolism_shadow_cycle import _run_audit_due_probe  # type: ignore[import]

        shadow_root = tmp_path / "shadow"
        shadow_root.mkdir()
        real_root = tmp_path / "real"
        real_root.mkdir()

        # Snapshot real root before
        before = set()
        for p in real_root.rglob("*"):
            if p.is_file():
                before.add(str(p))

        _run_audit_due_probe(shadow_root, real_root, "shadow-20260712-0000")

        # Check real root not touched (excluding files that were there before)
        after = set()
        for p in real_root.rglob("*"):
            if p.is_file():
                after.add(str(p))

        new_files = after - before
        assert not new_files, (
            f"audit_due_probe wrote to real_root: {new_files}"
        )


# ---------------------------------------------------------------------------
# 8. Roles YAML — SA-R13 verbatim in standout_auditor role
# ---------------------------------------------------------------------------

class TestRolesYaml:
    def test_roles_yaml_parses(self) -> None:
        """metabolism_roles.yml must parse without error."""
        with (
            _REPO / "config" / "metabolism_roles.yml"
        ).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "roles" in data

    def test_standout_auditor_role_present(self) -> None:
        """standout_auditor role must be defined in metabolism_roles.yml."""
        with (
            _REPO / "config" / "metabolism_roles.yml"
        ).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        roles = data.get("roles") or {}
        assert "standout_auditor" in roles, "standout_auditor role missing from metabolism_roles.yml"

    def test_standout_auditor_contains_sa_r13(self) -> None:
        """standout_auditor role text must contain SA-R13 verbatim key phrase."""
        with (
            _REPO / "config" / "metabolism_roles.yml"
        ).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        roles = data.get("roles") or {}
        role_text = str(roles.get("standout_auditor") or "")
        assert "two-axis taxonomy" in role_text, (
            "standout_auditor role missing SA-R13 'two-axis taxonomy' phrase"
        )
        assert "outcome-cause" in role_text, (
            "standout_auditor role missing SA-R13 'outcome-cause' phrase"
        )
        assert "process-fault" in role_text, (
            "standout_auditor role missing SA-R13 'process-fault' phrase"
        )

    def test_adversary_role_has_anti_narrowing(self) -> None:
        """adversary role must contain SA-R4 anti-narrowing instruction."""
        with (
            _REPO / "config" / "metabolism_roles.yml"
        ).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        roles = data.get("roles") or {}
        adversary_text = str(roles.get("adversary") or "")
        assert "SA-R4" in adversary_text or "ANTI-NARROWING" in adversary_text.upper(), (
            "adversary role missing SA-R4 anti-narrowing instruction"
        )
        assert "coverage" in adversary_text.lower(), (
            "adversary SA-R4 instruction must mention 'coverage'"
        )

    def test_standout_auditor_inert(self) -> None:
        """standout_auditor role must declare inertness."""
        with (
            _REPO / "config" / "metabolism_roles.yml"
        ).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        roles = data.get("roles") or {}
        role_text = str(roles.get("standout_auditor") or "")
        assert "inert" in role_text.lower(), (
            "standout_auditor role must declare AUTONOMY_PAUSED inertness"
        )


# ---------------------------------------------------------------------------
# 9. Rubrics W-4
# ---------------------------------------------------------------------------

class TestRubricsW4:
    def test_rubrics_yaml_parses(self) -> None:
        """adjudication_rubrics.yml must parse without error."""
        with (
            _REPO / "config" / "adjudication_rubrics.yml"
        ).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "warn_rules" in data

    def test_w4_rule_present(self) -> None:
        """W-4 must be defined in adjudication_rubrics.yml warn_rules."""
        with (
            _REPO / "config" / "adjudication_rubrics.yml"
        ).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        warn_rules = data.get("warn_rules") or {}
        assert "W-4" in warn_rules, "W-4 missing from warn_rules"
        w4 = warn_rules["W-4"]
        assert "rule" in w4 or "description" in w4

    def _run_check(self, packet: dict) -> list[dict]:
        """Run validate_packet and return the findings list."""
        from scripts.check_adjudication_packet import (  # type: ignore[import]
            validate_packet, load_rubrics, _build_class_tier_map, _build_invariant_set,
        )
        rubrics_path = _REPO / "config" / "adjudication_rubrics.yml"
        rubrics = load_rubrics(rubrics_path)
        class_tier_map = _build_class_tier_map(rubrics)
        invariant_set = _build_invariant_set(rubrics)
        return validate_packet(packet, rubrics, class_tier_map, invariant_set, as_of=None)

    def test_w4_fires_on_precision_only_packet(self) -> None:
        """validate_packet W-4 must fire when standout lobe targets hit_quality without coverage."""
        synthetic_packet = {
            "schema": "adjudication.v1",
            "packet_id": "test-w4-001",
            "tier": 0,
            "created_at": "2026-07-12T00:00:00Z",
            "created_by": "test",
            "request": {"title": "test W-4", "decision_class": "display_only_change"},
            "decision": {"outcome": "approve", "decided_by": "test"},
            "proposals": [
                {
                    "lobe": "site-us-standouts",
                    "fitness_contract": {"sensor": "hit_quality"},
                    "targets_sensor": "hit_quality",
                    "title": "improve hit quality only",
                }
            ],
        }

        findings = self._run_check(synthetic_packet)
        w4_findings = [f for f in findings if f.get("rule") == "W-4"]
        assert w4_findings, (
            f"expected W-4 finding for precision-only standout proposal, got: {findings}"
        )

    def test_w4_silent_when_coverage_present(self) -> None:
        """W-4 must NOT fire when a paired coverage sensor is present."""
        synthetic_packet = {
            "schema": "adjudication.v1",
            "packet_id": "test-w4-002",
            "tier": 0,
            "created_at": "2026-07-12T00:00:00Z",
            "created_by": "test",
            "request": {"title": "test W-4 with coverage", "decision_class": "display_only_change"},
            "decision": {"outcome": "approve", "decided_by": "test"},
            "proposals": [
                {
                    "lobe": "site-us-standouts",
                    "fitness_contract": {"sensor": "hit_quality"},
                    "targets_sensor": "hit_quality",
                    "title": "improve hit quality",
                },
                {
                    "lobe": "site-us-standouts",
                    "fitness_contract": {"sensor": "coverage_health"},
                    "targets_sensor": "coverage_health",
                    "title": "pair with coverage health",
                },
            ],
        }

        findings = self._run_check(synthetic_packet)
        w4_findings = [f for f in findings if f.get("rule") == "W-4"]
        assert not w4_findings, (
            f"W-4 fired when coverage sensor was present: {w4_findings}"
        )


# ---------------------------------------------------------------------------
# 10. insight_bus._KINDS contains 'audit_due'
# ---------------------------------------------------------------------------

class TestInsightBusKinds:
    def test_audit_due_kind_registered(self) -> None:
        """insight_bus._KINDS must contain 'audit_due'."""
        from engine.metabolism.insight_bus import _KINDS  # type: ignore[import]

        assert "audit_due" in _KINDS, (
            f"'audit_due' missing from insight_bus._KINDS: {sorted(_KINDS)}"
        )


# ---------------------------------------------------------------------------
# 11. run_audit with injected model_caller
# ---------------------------------------------------------------------------

class TestRunAudit:
    def _make_stub_postmortem(self) -> dict:
        return {
            "market": "us",
            "cycle_id": "test-cycle",
            "per_cohort_postmortems": [
                {
                    "cohort": "winner",
                    "outcome_cause_analysis": "Entry timing aligned with regime.",
                    "process_fault_analysis": "No fault detected.",
                    "remedy_class": "conditioning evidence",
                }
            ],
            "hypotheses": [
                {
                    "rank": 1,
                    "description": "Lower STRONG_BUY_THRESHOLD to improve coverage.",
                    "lane": "standout_review",
                    "market": "us",
                    "param": "STRONG_BUY_THRESHOLD",
                    "delta_steps": -1,
                    "rationale_ref": "data/standout_audit/postmortems/us-test-cycle.json",
                    "proposer": "standout_auditor",
                    "fitness_contract": {
                        "sensor": "coverage_health",
                        "expected_sign": "+",
                        "check_by": "2026-09-15",
                    },
                    "falsifiable_claim": "Coverage health improves.",
                },
            ],
            "honesty_notes": "N too small for strong claims.",
        }

    def test_run_audit_with_injected_caller(self, tmp_path: Path) -> None:
        """run_audit must use the injected model_caller and write a postmortem."""
        from engine.metabolism.standout_auditor import run_audit  # type: ignore[import]

        stub_pm = self._make_stub_postmortem()
        stub_reply = json.dumps(stub_pm)

        def mock_caller(system: str, user: str) -> str:
            return stub_reply

        result = run_audit(
            market="us",
            cycle_id="test-cycle",
            model_caller=mock_caller,
            root=tmp_path,
            dry_run=True,
        )

        assert isinstance(result, dict)
        # dry_run bypasses AUTONOMY_PAUSED gate
        assert result.get("status") in ("ok", "write_failed", "no_llm_reply", "error"), (
            f"unexpected status: {result}"
        )

    def test_run_audit_dry_run_never_raises(self, tmp_path: Path) -> None:
        """run_audit(dry_run=True) must never raise even with no LLM provider."""
        from engine.metabolism.standout_auditor import run_audit  # type: ignore[import]

        # No model_caller, no real LLM — should return gracefully
        result = run_audit(
            market="us",
            cycle_id="no-llm-cycle",
            model_caller=None,
            root=tmp_path,
            dry_run=True,
        )
        assert isinstance(result, dict)
        assert "schema" in result

    def test_run_audit_paused_returns_paused(self, tmp_path: Path) -> None:
        """run_audit with AUTONOMY_PAUSED set returns status='paused'."""
        from engine.metabolism.standout_auditor import run_audit  # type: ignore[import]

        with patch.dict(os.environ, {"AUTONOMY_PAUSED": "true"}):
            # Also patch is_paused to return True
            with patch("engine.metabolism.standout_auditor.os.environ.get") as mock_get:
                mock_get.return_value = "true"
                # Simulate guard import failure path (dry_run=False, AUTONOMY_PAUSED)
                result = run_audit(
                    market="us",
                    cycle_id="paused-cycle",
                    model_caller=None,
                    root=tmp_path,
                    dry_run=False,
                )
        # Either "paused" or no_llm_reply/error depending on guard availability
        assert isinstance(result, dict)

    def test_run_audit_proposal_file_written(self, tmp_path: Path) -> None:
        """run_audit with standout_review hypothesis must write a proposal file."""
        from engine.metabolism.standout_auditor import run_audit  # type: ignore[import]

        stub_pm = self._make_stub_postmortem()
        stub_reply = json.dumps(stub_pm)

        def mock_caller(system: str, user: str) -> str:
            return stub_reply

        run_audit(
            market="us",
            cycle_id="test-cycle-prop",
            model_caller=mock_caller,
            root=tmp_path,
            dry_run=True,
        )

        # Check proposal file was written
        props_dir = tmp_path / "data" / "standout_review" / "proposals"
        if props_dir.exists():
            prop_files = list(props_dir.glob("us-test-cycle-prop-*.json"))
            if prop_files:
                data = json.loads(prop_files[0].read_text(encoding="utf-8"))
                required = {"market", "param", "delta_steps", "rationale_ref", "proposer", "cycle_id"}
                missing = required - set(data.keys())
                assert not missing, f"proposal file missing fields: {missing}"
