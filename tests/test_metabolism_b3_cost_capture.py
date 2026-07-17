"""tests/test_metabolism_b3_cost_capture.py — B3 real token/cost capture wire tests.

COVERAGE:
  PROPOSE     real usage captured in proposal achievement rows + budget ledger + ai_costs
  PROPOSE     fallback to _EST_TOKENS_PER_CALL when usage absent
  ADJUDICATE  real usage captured in verdict achievement rows (via resolve aggregation)
  ADJUDICATE  _append_achievements_verdicts with usage_meta writes tokens/est_cost_usd
  BUILD       _parse_cli_usage parses CLI JSON envelope (success path + fallback)
  BUILD       _append_achievements_build with usage_meta writes tokens/est_cost_usd
  BUDGET      record_spend with usd>0 arms the $25 circuit breaker (usd_spent > 0)
  AI_COSTS    record_usage writes a row; round-trip via read_usage
  ACHIEVEMENTS _merge_proposals_view surfaces propose_tokens, adjudicate_tokens, build_tokens
  ACHIEVEMENTS backward compatibility — rows without cost fields still parse cleanly

All tests are HERMETIC (tmp_path, synthetic fixtures, no network, no real LLM calls).
MM_DATA_GUARD tripwire: all writers receive root=tmp_path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── helpers ───────────────────────────────────────────────────────────────────

def _write_journal(tmp_path: Path, cycle_id: str, data: dict) -> None:
    jdir = tmp_path / "data" / "metabolism" / "journal"
    jdir.mkdir(parents=True, exist_ok=True)
    (jdir / f"{cycle_id}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_journal(tmp_path: Path, cycle_id: str) -> dict:
    from scripts.metabolism_journal import _read_journal as _rj  # noqa: PLC0415
    return _rj(cycle_id, tmp_path)


def _default_journal_data(cycle_id: str) -> dict:
    return {
        "schema": "metabolism.journal.v1",
        "cycle_id": cycle_id,
        "stage": "propose",
        "status": "running",
        "auth_ok": True,
        "artifacts": [],
        "next_stage": None,
        "ts": "2026-07-16T10:00:00+00:00",
        "stages": {},
        "achievements": {"proposals": [], "verdicts": [], "builds": []},
    }


# ── PROPOSE: _append_achievements_proposals with usage_meta ──────────────────

class TestProposeUsageMeta:
    """_append_achievements_proposals writes optional tokens/est_cost_usd."""

    def test_cost_fields_written_when_usage_meta_present(self, tmp_path: Path) -> None:
        from scripts.metabolism_propose import _append_achievements_proposals  # noqa: PLC0415
        cycle_id = "cycle-2026-07-16-b3prop"
        docket = {
            "lobe": "til",
            "_usage_meta": {
                "input_tokens": 8000,
                "output_tokens": 2000,
                "est_cost_usd": 0.045,
            },
            "proposals": [
                {"proposal_id": "p-b3-001", "lobe": "til", "kind": "study",
                 "tier": "T1", "title": "Test proposal with cost"},
            ],
        }
        _append_achievements_proposals(cycle_id, docket, root=tmp_path)
        j = _read_journal(tmp_path, cycle_id)
        props = j["achievements"]["proposals"]
        assert len(props) == 1
        p = props[0]
        assert "tokens" in p, "tokens field should be present when usage_meta provided"
        assert p["tokens"] == 10000, f"expected 10000 (8000+2000), got {p['tokens']}"
        assert "est_cost_usd" in p, "est_cost_usd should be present when usage_meta provided"
        assert abs(p["est_cost_usd"] - 0.045) < 1e-9

    def test_cost_fields_absent_when_no_usage_meta(self, tmp_path: Path) -> None:
        from scripts.metabolism_propose import _append_achievements_proposals  # noqa: PLC0415
        cycle_id = "cycle-2026-07-16-b3nousage"
        docket = {
            "lobe": "til",
            "proposals": [
                {"proposal_id": "p-b3-002", "lobe": "til", "kind": "study",
                 "tier": "T1", "title": "Test proposal without cost"},
            ],
        }
        _append_achievements_proposals(cycle_id, docket, root=tmp_path)
        j = _read_journal(tmp_path, cycle_id)
        props = j["achievements"]["proposals"]
        assert len(props) == 1
        p = props[0]
        # required fields must be present
        for f in ("id", "lobe", "kind", "tier", "title", "proposed_at"):
            assert f in p
        # optional cost fields must NOT be present (absent, not None)
        assert "tokens" not in p
        assert "est_cost_usd" not in p

    def test_backward_compatible_required_fields_still_present(self, tmp_path: Path) -> None:
        from scripts.metabolism_propose import _append_achievements_proposals  # noqa: PLC0415
        cycle_id = "cycle-2026-07-16-b3compat"
        docket = {
            "lobe": "til",
            "_usage_meta": {"input_tokens": 5000, "output_tokens": 1500, "est_cost_usd": 0.02},
            "proposals": [
                {"proposal_id": "p-b3-003", "lobe": "til", "kind": "test",
                 "tier": "T0", "title": "Compat test"},
            ],
        }
        _append_achievements_proposals(cycle_id, docket, root=tmp_path)
        j = _read_journal(tmp_path, cycle_id)
        p = j["achievements"]["proposals"][0]
        # FROZEN required fields must still be present
        for f in ("id", "lobe", "kind", "tier", "title", "proposed_at"):
            assert f in p, f"required field missing after B3: {f}"


# ── ADJUDICATE: _append_achievements_verdicts with usage_meta ─────────────────

class TestAdjudicateUsageMeta:
    """_append_achievements_verdicts (resolve role) writes optional tokens/est_cost_usd."""

    def _make_docket(self, tmp_path: Path, cycle_id: str, pid: str) -> Path:
        ddir = tmp_path / "data" / "metabolism" / "dockets"
        ddir.mkdir(parents=True, exist_ok=True)
        dp = ddir / f"{cycle_id}.json"
        dp.write_text(json.dumps({
            "cycle_id": cycle_id,
            "lobe": "til",
            "proposals": [
                {"proposal_id": pid, "lobe": "til", "kind": "study",
                 "tier": "T1", "title": "Test"},
            ],
        }), encoding="utf-8")
        return dp

    def test_verdict_gets_cost_fields_when_usage_meta_provided(self, tmp_path: Path) -> None:
        from scripts.metabolism_adjudicate import _append_achievements_verdicts  # noqa: PLC0415
        from scripts.metabolism_journal import _default_journal, _write_journal as _wj  # noqa: PLC0415

        cycle_id = "cycle-2026-07-16-b3adj"
        pid = "p-adj-001"
        dp = self._make_docket(tmp_path, cycle_id, pid)

        j = _default_journal(cycle_id)
        j["achievements"] = {
            "proposals": [
                {"id": pid, "lobe": "til", "kind": "study", "tier": "T1",
                 "title": "Test", "proposed_at": "2026-07-16T09:00:00+00:00"},
            ],
            "verdicts": [],
        }
        jdir = tmp_path / "data" / "metabolism" / "journal"
        jdir.mkdir(parents=True, exist_ok=True)
        (jdir / f"{cycle_id}.json").write_text(json.dumps(j), encoding="utf-8")

        usage_meta = {"tokens": 15000, "est_cost_usd": 0.072}
        _append_achievements_verdicts(cycle_id, dp, "resolve", [], root=tmp_path,
                                      usage_meta=usage_meta)

        j2 = _read_journal(tmp_path, cycle_id)
        verdicts = j2["achievements"]["verdicts"]
        assert len(verdicts) >= 1
        v = next((x for x in verdicts if x["id"] == pid), None)
        assert v is not None, "verdict for pid not found"
        assert "tokens" in v, "tokens should be present when usage_meta provided"
        assert v["tokens"] == 15000
        assert "est_cost_usd" in v, "est_cost_usd should be present"
        assert abs(v["est_cost_usd"] - 0.072) < 1e-9

    def test_verdict_cost_fields_absent_when_no_usage_meta(self, tmp_path: Path) -> None:
        from scripts.metabolism_adjudicate import _append_achievements_verdicts  # noqa: PLC0415
        from scripts.metabolism_journal import _default_journal  # noqa: PLC0415

        cycle_id = "cycle-2026-07-16-b3adjnone"
        pid = "p-adj-002"
        dp = self._make_docket(tmp_path, cycle_id, pid)

        j = _default_journal(cycle_id)
        j["achievements"] = {
            "proposals": [
                {"id": pid, "lobe": "til", "kind": "study", "tier": "T1",
                 "title": "Test", "proposed_at": "2026-07-16T09:00:00+00:00"},
            ],
            "verdicts": [],
        }
        jdir = tmp_path / "data" / "metabolism" / "journal"
        jdir.mkdir(parents=True, exist_ok=True)
        (jdir / f"{cycle_id}.json").write_text(json.dumps(j), encoding="utf-8")

        _append_achievements_verdicts(cycle_id, dp, "resolve", [], root=tmp_path,
                                      usage_meta=None)

        j2 = _read_journal(tmp_path, cycle_id)
        verdicts = j2["achievements"]["verdicts"]
        assert len(verdicts) >= 1
        v = next((x for x in verdicts if x["id"] == pid), None)
        assert v is not None
        # required fields present
        for f in ("id", "decision", "reason_plain", "adjudicated_at"):
            assert f in v, f"required field missing: {f}"
        # optional fields absent
        assert "tokens" not in v
        assert "est_cost_usd" not in v

    def test_verdict_cost_from_input_output_tokens(self, tmp_path: Path) -> None:
        """usage_meta with input_tokens+output_tokens → tokens = sum."""
        from scripts.metabolism_adjudicate import _append_achievements_verdicts  # noqa: PLC0415
        from scripts.metabolism_journal import _default_journal  # noqa: PLC0415

        cycle_id = "cycle-2026-07-16-b3adjio"
        pid = "p-adj-003"
        dp = self._make_docket(tmp_path, cycle_id, pid)

        j = _default_journal(cycle_id)
        j["achievements"] = {
            "proposals": [
                {"id": pid, "lobe": "til", "kind": "study", "tier": "T1",
                 "title": "Test", "proposed_at": "2026-07-16T09:00:00+00:00"},
            ],
            "verdicts": [],
        }
        jdir = tmp_path / "data" / "metabolism" / "journal"
        jdir.mkdir(parents=True, exist_ok=True)
        (jdir / f"{cycle_id}.json").write_text(json.dumps(j), encoding="utf-8")

        # Pass input+output tokens (not pre-summed tokens key)
        usage_meta = {"input_tokens": 12000, "output_tokens": 3000, "est_cost_usd": 0.06}
        _append_achievements_verdicts(cycle_id, dp, "resolve", [], root=tmp_path,
                                      usage_meta=usage_meta)

        j2 = _read_journal(tmp_path, cycle_id)
        v = next((x for x in j2["achievements"]["verdicts"] if x["id"] == pid), None)
        assert v is not None
        assert v["tokens"] == 15000, f"expected 15000 (12000+3000), got {v.get('tokens')}"


# ── BUILD: _parse_cli_usage ────────────────────────────────────────────────────

class TestParseCLIUsage:
    """_parse_cli_usage correctly extracts cost/usage from CLI JSON stdout."""

    def test_parses_full_envelope(self) -> None:
        from scripts.metabolism_build import _parse_cli_usage  # noqa: PLC0415
        stdout = json.dumps({
            "total_cost_usd": 0.123,
            "usage": {
                "input_tokens": 5000,
                "output_tokens": 1500,
                "cache_read_input_tokens": 200,
                "cache_creation_input_tokens": 50,
            },
        })
        result = _parse_cli_usage(stdout)
        assert result["total_cost_usd"] == pytest.approx(0.123)
        assert result["input_tokens"] == 5000
        assert result["output_tokens"] == 1500
        assert result["cache_read_tokens"] == 200
        assert result["cache_creation_tokens"] == 50

    def test_returns_empty_on_non_json(self) -> None:
        from scripts.metabolism_build import _parse_cli_usage  # noqa: PLC0415
        result = _parse_cli_usage("Building... done")
        assert result == {}

    def test_returns_empty_on_empty_string(self) -> None:
        from scripts.metabolism_build import _parse_cli_usage  # noqa: PLC0415
        assert _parse_cli_usage("") == {}

    def test_partial_envelope_no_usage(self) -> None:
        """total_cost_usd present but no usage sub-object."""
        from scripts.metabolism_build import _parse_cli_usage  # noqa: PLC0415
        result = _parse_cli_usage(json.dumps({"total_cost_usd": 0.05}))
        assert result["total_cost_usd"] == pytest.approx(0.05)
        assert "input_tokens" not in result

    def test_never_raises_on_malformed_json(self) -> None:
        from scripts.metabolism_build import _parse_cli_usage  # noqa: PLC0415
        result = _parse_cli_usage("{broken json[")
        assert isinstance(result, dict)
        assert result == {}


# ── BUILD: _append_achievements_build with usage_meta ─────────────────────────

class TestBuildAchievementsUsageMeta:
    """_append_achievements_build writes optional tokens/est_cost_usd."""

    def test_cost_fields_written_when_usage_meta_provided(self, tmp_path: Path) -> None:
        from scripts.metabolism_build import _append_achievements_build  # noqa: PLC0415

        cycle_id = "cycle-2026-07-16-b3build"
        pid = "p-build-001"
        usage_meta = {"tokens": 60000, "est_cost_usd": 0.30}
        _append_achievements_build(
            cycle_id, pid,
            status="pr_opened",
            pr_number=2601,
            pr_url="https://github.com/owner/repo/pull/2601",
            usage_meta=usage_meta,
            root=tmp_path,
        )
        j = _read_journal(tmp_path, cycle_id)
        builds = j["achievements"]["builds"]
        assert len(builds) == 1
        b = builds[0]
        assert b["id"] == pid
        assert b["status"] == "pr_opened"
        assert "tokens" in b, "tokens should be written when usage_meta provided"
        assert b["tokens"] == 60000
        assert "est_cost_usd" in b
        assert abs(b["est_cost_usd"] - 0.30) < 1e-9

    def test_cost_fields_absent_when_no_usage_meta(self, tmp_path: Path) -> None:
        from scripts.metabolism_build import _append_achievements_build  # noqa: PLC0415

        cycle_id = "cycle-2026-07-16-b3buildno"
        pid = "p-build-002"
        _append_achievements_build(
            cycle_id, pid,
            status="build_failed",
            root=tmp_path,
        )
        j = _read_journal(tmp_path, cycle_id)
        b = j["achievements"]["builds"][0]
        # required fields present
        assert b["id"] == pid
        assert b["status"] == "build_failed"
        assert "built_at" in b
        # optional fields absent
        assert "tokens" not in b
        assert "est_cost_usd" not in b

    def test_idempotent_no_duplicate(self, tmp_path: Path) -> None:
        from scripts.metabolism_build import _append_achievements_build  # noqa: PLC0415

        cycle_id = "cycle-2026-07-16-b3buildidem"
        pid = "p-build-003"
        _append_achievements_build(cycle_id, pid, status="pr_opened",
                                    usage_meta={"tokens": 50000, "est_cost_usd": 0.25},
                                    root=tmp_path)
        _append_achievements_build(cycle_id, pid, status="pr_opened",
                                    usage_meta={"tokens": 50000, "est_cost_usd": 0.25},
                                    root=tmp_path)
        j = _read_journal(tmp_path, cycle_id)
        assert len(j["achievements"]["builds"]) == 1, "idempotency violated"


# ── BUDGET: usd>0 arms the circuit breaker ────────────────────────────────────

class TestBudgetCircuitBreaker:
    """record_spend with real usd value advances usd_spent (arms the $25 cap)."""

    def test_usd_spent_advances_on_real_cost(self, tmp_path: Path) -> None:
        from scripts.metabolism_budget import record_spend, init_cycle  # noqa: PLC0415

        cycle_id = "cycle-2026-07-16-b3budget"
        init_cycle(cycle_id, root=tmp_path)
        result = record_spend(
            cycle_id, "propose",
            tokens=10000,
            usd=0.048,
            note="propose real cost test",
            root=tmp_path,
        )
        assert result.get("ok") is True
        ledger = result["ledger"]
        assert ledger["usd_spent"] == pytest.approx(0.048), \
            f"usd_spent should be 0.048 after real cost record; got {ledger['usd_spent']}"
        assert ledger["token_spent"] == 10000

    def test_over_cap_fires_when_cost_exceeds_limit(self, tmp_path: Path) -> None:
        """over_cap=True when cumulative usd > usd_cap ($25)."""
        from scripts.metabolism_budget import record_spend, init_cycle, _write_ledger  # noqa: PLC0415

        cycle_id = "cycle-2026-07-16-b3overcap"
        ledger = init_cycle(cycle_id, root=tmp_path)

        # Pre-seed ledger with 24.99 already spent using _write_ledger
        ledger["usd_spent"] = 24.99
        _write_ledger(ledger, root=tmp_path)

        result = record_spend(
            cycle_id, "adjudicate",
            tokens=5000,
            usd=0.05,  # total becomes 25.04 > 25.00 cap
            root=tmp_path,
        )
        assert result.get("over_cap") is True, \
            f"expected over_cap=True when usd_spent > usd_cap; got {result}"

    def test_zero_usd_does_not_advance_cap(self, tmp_path: Path) -> None:
        """Fallback path (usd=0) does not advance usd_spent — cap stays unarmed."""
        from scripts.metabolism_budget import record_spend, init_cycle  # noqa: PLC0415

        cycle_id = "cycle-2026-07-16-b3zerousd"
        init_cycle(cycle_id, root=tmp_path)
        result = record_spend(cycle_id, "propose", tokens=30000, usd=0.0, root=tmp_path)
        assert result["ledger"]["usd_spent"] == pytest.approx(0.0)


# ── AI_COSTS: record_usage → read_usage round-trip ───────────────────────────

class TestAiCostsRoundTrip:
    """lib.ai_costs.record_usage writes a row; lib.ai_costs.read_usage retrieves it."""

    def test_record_and_read_round_trip(self, tmp_path: Path) -> None:
        from lib.ai_costs import record_usage, read_usage  # noqa: PLC0415

        ok = record_usage(
            lane="metabolism-propose",
            provider="claude_oauth",
            model="claude-opus-4-8",
            key_id="cap-test-001",
            input_tokens=8000,
            output_tokens=2000,
            cache_read_tokens=500,
            cache_creation_tokens=100,
            cost_basis="subscription",
            cycle_id="cycle-2026-07-16-b3aic",
            stage="propose",
            note="b3 test row",
            est_cost_usd=0.048,
            root=tmp_path,
        )
        assert ok is True, "record_usage should return True on success"

        rows = read_usage(root=tmp_path)
        assert len(rows) == 1
        row = rows[0]
        assert row["lane"] == "metabolism-propose"
        assert row["provider"] == "claude_oauth"
        assert row["model"] == "claude-opus-4-8"
        assert row["input_tokens"] == 8000
        assert row["output_tokens"] == 2000
        assert row.get("est_cost_usd") == pytest.approx(0.048)

    def test_never_raises_on_bad_root(self) -> None:
        """record_usage must not raise even on an unwritable path."""
        from lib.ai_costs import record_usage  # noqa: PLC0415
        # Pass a path that can't be written (file instead of dir)
        bad_root = Path("/nonexistent/totally/bad/path/abc123")
        result = record_usage(
            lane="test", provider="test",
            input_tokens=0, output_tokens=0,
            root=bad_root,
        )
        # NEVER-RAISE contract: must return False (not raise)
        assert result is False

    def test_record_usage_build_lane(self, tmp_path: Path) -> None:
        """Build lane uses claude_cli provider."""
        from lib.ai_costs import record_usage, read_usage  # noqa: PLC0415

        record_usage(
            lane="metabolism-build",
            provider="claude_cli",
            model="claude-sonnet-4-6",
            key_id="cap-build-001",
            input_tokens=0,
            output_tokens=0,
            cost_basis="estimated",
            cycle_id="cycle-test",
            stage="build",
            est_cost_usd=None,
            root=tmp_path,
        )
        rows = read_usage(root=tmp_path)
        assert len(rows) == 1
        assert rows[0]["provider"] == "claude_cli"


# ── ACHIEVEMENTS: _merge_proposals_view surfaces cost fields ─────────────────

class TestMergeProposalsView:
    """_merge_proposals_view correctly surfaces propose/adjudicate/build cost fields."""

    def test_propose_cost_surfaced(self) -> None:
        from admin.metabolism_achievements import _merge_proposals_view  # noqa: PLC0415

        proposals = [
            {"id": "p1", "lobe": "til", "kind": "study", "tier": "T1",
             "title": "Test", "proposed_at": "2026-07-16T09:00:00+00:00",
             "tokens": 10000, "est_cost_usd": 0.045},
        ]
        verdicts: list[dict] = []
        builds: list[dict] = []
        merged = _merge_proposals_view(proposals, verdicts, builds)
        assert len(merged) == 1
        m = merged[0]
        assert m.get("propose_tokens") == 10000
        assert m.get("propose_est_cost_usd") == pytest.approx(0.045)

    def test_adjudicate_cost_surfaced(self) -> None:
        from admin.metabolism_achievements import _merge_proposals_view  # noqa: PLC0415

        proposals = [
            {"id": "p1", "lobe": "til", "kind": "study", "tier": "T1",
             "title": "Test", "proposed_at": "2026-07-16T09:00:00+00:00"},
        ]
        verdicts = [
            {"id": "p1", "decision": "authorized", "reason_plain": "ok",
             "adjudicated_at": "2026-07-16T10:00:00+00:00",
             "tokens": 15000, "est_cost_usd": 0.072},
        ]
        builds: list[dict] = []
        merged = _merge_proposals_view(proposals, verdicts, builds)
        m = merged[0]
        assert m.get("adjudicate_tokens") == 15000
        assert m.get("adjudicate_est_cost_usd") == pytest.approx(0.072)

    def test_build_cost_surfaced(self) -> None:
        from admin.metabolism_achievements import _merge_proposals_view  # noqa: PLC0415

        proposals = [
            {"id": "p1", "lobe": "til", "kind": "study", "tier": "T1",
             "title": "Test", "proposed_at": "2026-07-16T09:00:00+00:00"},
        ]
        verdicts = [
            {"id": "p1", "decision": "authorized", "reason_plain": "ok",
             "adjudicated_at": "2026-07-16T10:00:00+00:00"},
        ]
        builds = [
            {"id": "p1", "status": "pr_opened", "built_at": "2026-07-16T11:00:00+00:00",
             "tokens": 60000, "est_cost_usd": 0.30},
        ]
        merged = _merge_proposals_view(proposals, verdicts, builds)
        m = merged[0]
        assert m.get("build_tokens") == 60000
        assert m.get("build_est_cost_usd") == pytest.approx(0.30)

    def test_backward_compat_no_cost_fields(self) -> None:
        """Old journal rows without cost fields don't add None keys to merged view."""
        from admin.metabolism_achievements import _merge_proposals_view  # noqa: PLC0415

        proposals = [
            {"id": "p1", "lobe": "til", "kind": "study", "tier": "T1",
             "title": "Old row", "proposed_at": "2026-07-16T09:00:00+00:00"},
        ]
        verdicts = [
            {"id": "p1", "decision": "denied", "reason_plain": "blocked",
             "adjudicated_at": "2026-07-16T10:00:00+00:00"},
        ]
        builds: list[dict] = []
        merged = _merge_proposals_view(proposals, verdicts, builds)
        m = merged[0]
        # Required fields present
        assert m["id"] == "p1"
        assert m["decision"] == "denied"
        # Cost fields ABSENT (not None — the key shouldn't exist)
        assert "propose_tokens" not in m
        assert "propose_est_cost_usd" not in m
        assert "adjudicate_tokens" not in m
        assert "adjudicate_est_cost_usd" not in m
        assert "build_tokens" not in m
        assert "build_est_cost_usd" not in m

    def test_multiple_builds_cost_aggregated(self) -> None:
        """Build cost is summed across multiple build rows for the same proposal."""
        from admin.metabolism_achievements import _merge_proposals_view  # noqa: PLC0415

        proposals = [
            {"id": "p1", "lobe": "til", "kind": "study", "tier": "T1",
             "title": "Test", "proposed_at": "2026-07-16T09:00:00+00:00"},
        ]
        verdicts = [
            {"id": "p1", "decision": "authorized", "reason_plain": "ok",
             "adjudicated_at": "2026-07-16T10:00:00+00:00"},
        ]
        # Two build rows for same pid (e.g. remediation rebuild)
        builds = [
            {"id": "p1", "status": "pr_opened", "built_at": "2026-07-16T11:00:00+00:00",
             "tokens": 60000, "est_cost_usd": 0.30},
            {"id": "p1", "status": "pr_opened", "built_at": "2026-07-16T12:00:00+00:00",
             "tokens": 40000, "est_cost_usd": 0.20},
        ]
        merged = _merge_proposals_view(proposals, verdicts, builds)
        m = merged[0]
        assert m.get("build_tokens") == 100000
        assert m.get("build_est_cost_usd") == pytest.approx(0.50)


# ── ACHIEVEMENTS: full achievements() with cost fields ────────────────────────

class TestAchievementsFullCostRoundTrip:
    """End-to-end: journal with cost fields → achievements() surfaces them."""

    def test_achievements_surfaces_propose_cost(self, tmp_path: Path) -> None:
        from admin.metabolism_achievements import achievements  # noqa: PLC0415

        jdir = tmp_path / "data" / "metabolism" / "journal"
        jdir.mkdir(parents=True, exist_ok=True)
        cycle_id = "cycle-2026-07-16-b3e2e"
        j = {
            "schema": "metabolism.journal.v1",
            "cycle_id": cycle_id,
            "stage": "build",
            "status": "done",
            "ts": "2026-07-16T10:00:00+00:00",
            "stages": {},
            "achievements": {
                "proposals": [
                    {"id": "p1", "lobe": "til", "kind": "study", "tier": "T1",
                     "title": "Cost-tracked proposal",
                     "proposed_at": "2026-07-16T09:00:00+00:00",
                     "tokens": 10000, "est_cost_usd": 0.045},
                ],
                "verdicts": [
                    {"id": "p1", "decision": "authorized",
                     "reason_plain": "authorized by orchestrator and adversary",
                     "adjudicated_at": "2026-07-16T10:00:00+00:00",
                     "tokens": 15000, "est_cost_usd": 0.072},
                ],
                "builds": [
                    {"id": "p1", "status": "pr_opened",
                     "built_at": "2026-07-16T11:00:00+00:00",
                     "pr_number": 2601,
                     "pr_url": "https://github.com/owner/repo/pull/2601",
                     "tokens": 60000, "est_cost_usd": 0.30},
                ],
            },
        }
        (jdir / f"{cycle_id}.json").write_text(json.dumps(j, indent=2), encoding="utf-8")

        result = achievements(root=tmp_path)
        assert len(result["cycles"]) == 1
        c = result["cycles"][0]
        assert len(c["proposals"]) == 1
        m = c["proposals"][0]
        assert m.get("propose_tokens") == 10000
        assert m.get("propose_est_cost_usd") == pytest.approx(0.045)
        assert m.get("adjudicate_tokens") == 15000
        assert m.get("adjudicate_est_cost_usd") == pytest.approx(0.072)
        assert m.get("build_tokens") == 60000
        assert m.get("build_est_cost_usd") == pytest.approx(0.30)
