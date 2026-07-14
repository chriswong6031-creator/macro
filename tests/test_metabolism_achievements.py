"""tests/test_metabolism_achievements.py — Achievements observability wire contracts.

COVERAGE:
  JOURNAL   achievements key schema in cycle journal files (frozen cross-builder contract)
            propose / adjudicate / build records shape + field constraints
  COMPOSER  admin.metabolism_achievements — hermetic unit tests for rollup functions
  ENRICHMENT scripts/metabolism_propose._append_achievements_proposals
             scripts/metabolism_adjudicate._screen_reason_to_plain
             scripts/metabolism_adjudicate._append_achievements_verdicts
  WORKFLOW  metabolism-cycle.yml carries CLAUDE_CODE_OAUTH_TOKEN_1..7 near budget_gate
            key-pool-probe.yml write-budget-status step carries TOKEN env block
            metabolism-dream.yml carries DIGEST step wired to scripts.metabolism_digest
            propose / adjudicate / build workflows carry narrow-commit journal-to-main step
  DIGEST    scripts/metabolism_digest CLI exit-0 contract (--dry-run; NEVER-RAISE)

All tests are HERMETIC (tmp_path, synthetic fixtures, no network, no real workflow runs).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    """Load a YAML file; fail the test on any parse error."""
    import yaml  # noqa: PLC0415
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _workflow(name: str) -> dict:
    p = _ROOT / ".github" / "workflows" / name
    assert p.exists(), f"workflow file not found: {p}"
    return _load_yaml(p)


# ── JOURNAL: achievements key schema ─────────────────────────────────────────

class TestAchievementsJournalSchema:
    """Frozen cross-builder contract: journal file shape for achievements enrichment.

    The achievements key is written by propose/adjudicate/build into the cycle journal.
    GET /api/metabolism/achievements reads these files from main.
    This test validates shape expectations without requiring actual script runs.
    """

    def _make_journal(self, tmp_path: Path, cycle_id: str = "cycle-2026-07-13-0001") -> dict:
        """Build a synthetic journal file with achievements populated (happy path)."""
        j: dict[str, Any] = {
            "schema": "metabolism.journal.v1",
            "cycle_id": cycle_id,
            "stage": "build",
            "status": "done",
            "auth_ok": True,
            "artifacts": [],
            "next_stage": None,
            "ts": "2026-07-13T10:00:00+00:00",
            "stages": {},
            "achievements": {
                "proposals": [
                    {
                        "id": "til-001",
                        "lobe": "til",
                        "kind": "study",
                        "tier": "display",
                        "title": "A" * 80,  # within 120-char limit
                        "proposed_at": "2026-07-13T09:45:00+00:00",
                    }
                ],
                "verdicts": [
                    {
                        "id": "til-001",
                        "decision": "denied",
                        "reason_plain": "collides with a standing kill ruling (DO_NOT_REBUILD)",
                        "adjudicated_at": "2026-07-13T10:15:00+00:00",
                    }
                ],
                "builds": [],
            },
        }
        p = tmp_path / "journal" / f"{cycle_id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(j, indent=2), encoding="utf-8")
        return j

    def test_achievements_key_present(self, tmp_path: Path) -> None:
        j = self._make_journal(tmp_path)
        assert "achievements" in j

    def test_proposals_fields(self, tmp_path: Path) -> None:
        j = self._make_journal(tmp_path)
        props = j["achievements"]["proposals"]
        assert len(props) == 1
        p = props[0]
        for field in ("id", "lobe", "kind", "tier", "title", "proposed_at"):
            assert field in p, f"missing field: {field}"
        assert len(p["title"]) <= 120, "title must be <=120 chars"

    def test_verdicts_fields(self, tmp_path: Path) -> None:
        j = self._make_journal(tmp_path)
        verts = j["achievements"]["verdicts"]
        assert len(verts) == 1
        v = verts[0]
        for field in ("id", "decision", "reason_plain", "adjudicated_at"):
            assert field in v, f"missing field: {field}"
        assert v["decision"] in {"authorized", "denied", "never_ruled"}, \
            f"invalid decision: {v['decision']}"
        assert len(v["reason_plain"]) <= 160, "reason_plain must be <=160 chars"

    def test_builds_field_present(self, tmp_path: Path) -> None:
        j = self._make_journal(tmp_path)
        assert "builds" in j["achievements"]
        assert isinstance(j["achievements"]["builds"], list)

    def test_builds_schema_when_populated(self, tmp_path: Path) -> None:
        """When a build record exists it must carry required fields."""
        j = self._make_journal(tmp_path)
        j["achievements"]["builds"] = [
            {
                "id": "til-001",
                "status": "pr_opened",
                "pr_number": 2501,
                "pr_url": "https://github.com/owner/repo/pull/2501",
                "built_at": "2026-07-13T10:45:00+00:00",
            }
        ]
        b = j["achievements"]["builds"][0]
        assert b["status"] in {"pr_opened", "build_failed", "skipped"}
        assert "id" in b

    def test_journal_file_roundtrip(self, tmp_path: Path) -> None:
        """Journal file written by _make_journal must be valid JSON and round-trip."""
        cycle_id = "cycle-2026-07-13-test"
        self._make_journal(tmp_path, cycle_id)
        p = tmp_path / "journal" / f"{cycle_id}.json"
        loaded = json.loads(p.read_text(encoding="utf-8"))
        assert loaded["cycle_id"] == cycle_id
        assert "achievements" in loaded

    def test_empty_achievements_is_valid(self, tmp_path: Path) -> None:
        """All three lists can be empty (e.g. rate-limited cycle)."""
        j = self._make_journal(tmp_path)
        j["achievements"]["proposals"] = []
        j["achievements"]["verdicts"] = []
        j["achievements"]["builds"] = []
        # must remain valid (no schema violation)
        assert j["achievements"]["proposals"] == []
        assert j["achievements"]["verdicts"] == []
        assert j["achievements"]["builds"] == []


# ── WORKFLOW: TOKEN_1..7 near budget_gate calls ───────────────────────────────

class TestMetabCycleEnvFix:
    """metabolism-cycle.yml must expose TOKEN_1..7 to every budget_gate call."""

    def _cycle_wf(self) -> dict:
        return _workflow("metabolism-cycle.yml")

    def _step_env_keys(self, step: dict) -> set[str]:
        return set((step.get("env") or {}).keys())

    def _find_steps_with_budget_gate(self, wf: dict) -> list[dict]:
        steps = []
        for job in (wf.get("jobs") or {}).values():
            for s in (job.get("steps") or []):
                run_text = s.get("run", "")
                if "budget_gate" in run_text:
                    steps.append(s)
        return steps

    def test_cycle_yaml_parses(self) -> None:
        wf = self._cycle_wf()
        assert "jobs" in wf

    def test_budget_gate_steps_have_token_env(self) -> None:
        wf = self._cycle_wf()
        steps = self._find_steps_with_budget_gate(wf)
        assert steps, "no steps with budget_gate found in metabolism-cycle.yml"
        for step in steps:
            env_keys = self._step_env_keys(step)
            for n in range(1, 8):
                key = f"CLAUDE_CODE_OAUTH_TOKEN_{n}"
                assert key in env_keys, \
                    f"step '{step.get('name', '?')}' missing {key}"


class TestKeyPoolProbeEnvFix:
    """key-pool-probe.yml write-budget-status step must carry TOKEN_1..7."""

    def _probe_wf(self) -> dict:
        return _workflow("key-pool-probe.yml")

    def test_probe_yaml_parses(self) -> None:
        wf = self._probe_wf()
        assert "jobs" in wf

    def test_write_status_step_has_token_env(self) -> None:
        wf = self._probe_wf()
        steps: list[dict] = []
        for job in (wf.get("jobs") or {}).values():
            steps.extend(job.get("steps") or [])

        budget_status_steps = [
            s for s in steps
            if "budget" in (s.get("name") or "").lower()
            and "status" in (s.get("name") or "").lower()
        ]
        assert budget_status_steps, "write budget status step not found in key-pool-probe.yml"

        step = budget_status_steps[0]
        env_keys = set((step.get("env") or {}).keys())
        for n in range(1, 8):
            key = f"CLAUDE_CODE_OAUTH_TOKEN_{n}"
            assert key in env_keys, \
                f"key-pool-probe write-status step missing {key}"


# ── WORKFLOW: digest step wired in dream ─────────────────────────────────────

class TestDreamDigestWiring:
    """metabolism-dream.yml must contain a DIGEST step calling scripts.metabolism_digest."""

    def test_dream_yaml_parses(self) -> None:
        wf = _workflow("metabolism-dream.yml")
        assert "jobs" in wf

    def test_digest_step_exists(self) -> None:
        wf = _workflow("metabolism-dream.yml")
        steps: list[dict] = []
        for job in (wf.get("jobs") or {}).values():
            steps.extend(job.get("steps") or [])

        digest_steps = [
            s for s in steps
            if "metabolism_digest" in (s.get("run") or "")
        ]
        assert digest_steps, \
            "no step calling scripts.metabolism_digest found in metabolism-dream.yml"

    def test_digest_step_continue_on_error(self) -> None:
        wf = _workflow("metabolism-dream.yml")
        steps: list[dict] = []
        for job in (wf.get("jobs") or {}).values():
            steps.extend(job.get("steps") or [])

        digest_steps = [
            s for s in steps
            if "metabolism_digest" in (s.get("run") or "")
        ]
        assert digest_steps
        step = digest_steps[0]
        assert step.get("continue-on-error") is True, \
            "DIGEST step must have continue-on-error: true (fail-soft)"

    def test_digest_commit_step_exists(self) -> None:
        """A separate commit step for digest artifacts must follow the digest run step."""
        wf = _workflow("metabolism-dream.yml")
        steps: list[dict] = []
        for job in (wf.get("jobs") or {}).values():
            steps.extend(job.get("steps") or [])

        # Must have a step that adds data/metabolism/digest/
        commit_steps = [
            s for s in steps
            if "digest" in (s.get("run") or "").lower()
            and "git add" in (s.get("run") or "")
        ]
        assert commit_steps, \
            "no commit step for digest artifacts found in metabolism-dream.yml"


# ── WORKFLOW: journal narrow-commit to main in propose/adjudicate/build ───────

class TestJournalNarrowCommit:
    """propose / adjudicate / build must each carry a narrow-commit journal-to-main step."""

    @pytest.mark.parametrize("wf_name,lane", [
        ("metabolism-propose.yml", "propose"),
        ("metabolism-adjudicate.yml", "adjudicate"),
        ("metabolism-build.yml", "build"),
    ])
    def test_wf_parses(self, wf_name: str, lane: str) -> None:
        wf = _workflow(wf_name)
        assert "jobs" in wf

    @pytest.mark.parametrize("wf_name,lane", [
        ("metabolism-propose.yml", "propose"),
        ("metabolism-adjudicate.yml", "adjudicate"),
        ("metabolism-build.yml", "build"),
    ])
    def test_journal_main_commit_step(self, wf_name: str, lane: str) -> None:
        wf = _workflow(wf_name)
        steps: list[dict] = []
        for job in (wf.get("jobs") or {}).values():
            steps.extend(job.get("steps") or [])

        # Must have a step that (a) adds data/metabolism/journal and (b) pushes to main
        journal_main_steps = [
            s for s in steps
            if "journal" in (s.get("run") or "").lower()
            and "HEAD:main" in (s.get("run") or "")
        ]
        assert journal_main_steps, \
            f"{wf_name}: no narrow-commit-journal-to-main step found " \
            f"(must git add data/metabolism/journal + push origin HEAD:main)"

    @pytest.mark.parametrize("wf_name,lane", [
        ("metabolism-propose.yml", "propose"),
        ("metabolism-adjudicate.yml", "adjudicate"),
        ("metabolism-build.yml", "build"),
    ])
    def test_journal_main_commit_skip_ci(self, wf_name: str, lane: str) -> None:
        wf = _workflow(wf_name)
        steps: list[dict] = []
        for job in (wf.get("jobs") or {}).values():
            steps.extend(job.get("steps") or [])

        journal_main_steps = [
            s for s in steps
            if "journal" in (s.get("run") or "").lower()
            and "HEAD:main" in (s.get("run") or "")
        ]
        assert journal_main_steps
        # The commit message must include [skip ci] to avoid CI loop
        step = journal_main_steps[0]
        assert "skip ci" in (step.get("run") or "").lower(), \
            f"{wf_name} journal-to-main commit must include [skip ci] in commit message"


# ── DIGEST: CLI exit-0 contract ───────────────────────────────────────────────

class TestDigestCLIContract:
    """scripts/metabolism_digest --dry-run must exit 0 regardless of data presence."""

    def test_dry_run_exits_zero(self, tmp_path: Path) -> None:
        """--dry-run on an empty root must exit 0 (NEVER-RAISE contract)."""
        result = subprocess.run(
            [sys.executable, "-m", "scripts.metabolism_digest", "--dry-run",
             "--root", str(tmp_path), "--no-notify"],
            capture_output=True,
            text=True,
            cwd=str(_ROOT),
        )
        assert result.returncode == 0, \
            f"metabolism_digest --dry-run failed:\n{result.stdout}\n{result.stderr}"

    def test_dry_run_produces_headings(self, tmp_path: Path) -> None:
        """--dry-run output must contain the four canonical one-pager headings."""
        result = subprocess.run(
            [sys.executable, "-m", "scripts.metabolism_digest", "--dry-run",
             "--root", str(tmp_path), "--no-notify"],
            capture_output=True,
            text=True,
            cwd=str(_ROOT),
        )
        assert result.returncode == 0
        combined = result.stdout + result.stderr
        for heading in ("What got better", "What's slipping",
                        "What I'm about to do", "What needs your tap"):
            assert heading in combined, f"one-pager heading missing: {heading!r}"


# ── COMPOSER: admin.metabolism_achievements unit tests ────────────────────────

def _make_journal_file(
    jdir: Path,
    cycle_id: str,
    *,
    achievements: dict | None = None,
    stages: dict | None = None,
    status: str = "done",
    stage: str = "build",
) -> None:
    """Write a synthetic journal file to jdir."""
    j: dict[str, Any] = {
        "schema": "metabolism.journal.v1",
        "cycle_id": cycle_id,
        "stage": stage,
        "status": status,
        "ts": "2026-07-13T10:00:00+00:00",
        "stages": stages or {},
    }
    if achievements is not None:
        j["achievements"] = achievements
    (jdir / f"{cycle_id}.json").write_text(json.dumps(j, indent=2), encoding="utf-8")


class TestComposerAchievements:
    """Unit tests for admin.metabolism_achievements.achievements()."""

    def _jdir(self, root: Path) -> Path:
        d = root / "data" / "metabolism" / "journal"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_never_raises_on_empty_root(self, tmp_path: Path) -> None:
        from admin.metabolism_achievements import achievements  # noqa: PLC0415
        result = achievements(limit_cycles=5, root=tmp_path)
        assert isinstance(result, dict)
        assert "cycles" in result
        assert "generated_at" in result

    def test_never_raises_on_missing_journal_dir(self, tmp_path: Path) -> None:
        from admin.metabolism_achievements import achievements  # noqa: PLC0415
        # No journal dir — should return empty cycles
        result = achievements(root=tmp_path)
        assert result["cycles"] == []

    def test_empty_achievements_key(self, tmp_path: Path) -> None:
        """Old journal without achievements key → proposals/verdicts/builds all empty."""
        from admin.metabolism_achievements import achievements  # noqa: PLC0415
        jdir = self._jdir(tmp_path)
        _make_journal_file(
            jdir, "cycle-2026-07-13-old",
            stages={"propose": {"status": "done", "note": "docket 1 proposal(s)"}},
        )
        result = achievements(root=tmp_path)
        assert len(result["cycles"]) == 1
        c = result["cycles"][0]
        assert c["proposals"] == []
        assert c["lobes"] == {}

    def test_with_achievements_key(self, tmp_path: Path) -> None:
        """Journal with achievements key → proposals, verdicts, lobe rollup correct."""
        from admin.metabolism_achievements import achievements  # noqa: PLC0415
        jdir = self._jdir(tmp_path)
        _make_journal_file(
            jdir, "cycle-2026-07-13-full",
            achievements={
                "proposals": [
                    {"id": "p1", "lobe": "til", "kind": "study", "tier": "T1",
                     "title": "Test proposal", "proposed_at": "2026-07-13T09:45:00+00:00"},
                ],
                "verdicts": [
                    {"id": "p1", "decision": "denied",
                     "reason_plain": "collides with a standing kill ruling (DO_NOT_REBUILD)",
                     "adjudicated_at": "2026-07-13T10:15:00+00:00"},
                ],
                "builds": [],
            },
        )
        result = achievements(root=tmp_path)
        assert len(result["cycles"]) == 1
        c = result["cycles"][0]
        assert c["cycle_id"] == "cycle-2026-07-13-full"
        assert len(c["proposals"]) == 1
        assert c["proposals"][0]["decision"] == "denied"
        assert c["lobes"]["til"]["proposed"] == 1
        assert c["lobes"]["til"]["denied"] == 1
        assert c["lobes"]["til"]["authorized"] == 0
        assert c["lobes"]["til"]["never_ruled"] == 0

    def test_malformed_journal_skipped(self, tmp_path: Path) -> None:
        from admin.metabolism_achievements import achievements  # noqa: PLC0415
        jdir = self._jdir(tmp_path)
        (jdir / "cycle-2026-07-13-bad.json").write_text("{not valid json")
        result = achievements(root=tmp_path)
        assert result["cycles"] == []

    def test_headline_rate_limited(self, tmp_path: Path) -> None:
        from admin.metabolism_achievements import achievements  # noqa: PLC0415
        jdir = self._jdir(tmp_path)
        _make_journal_file(
            jdir, "cycle-2026-07-13-rl",
            status="noop_paused",
            stage="agenda",
            stages={"agenda": {"status": "noop_paused", "note": "rate_limited_all: all keys cooling"}},
            achievements={"proposals": [], "verdicts": [], "builds": []},
        )
        result = achievements(root=tmp_path)
        assert len(result["cycles"]) == 1
        c = result["cycles"][0]
        hl = c["headline_plain"].lower()
        assert "rate" in hl or "key" in hl, f"expected rate-limited in headline: {c['headline_plain']}"

    def test_headline_never_adjudicated(self, tmp_path: Path) -> None:
        from admin.metabolism_achievements import achievements  # noqa: PLC0415
        jdir = self._jdir(tmp_path)
        _make_journal_file(
            jdir, "cycle-2026-07-13-na",
            achievements={
                "proposals": [
                    {"id": "p1", "lobe": "til", "kind": "study", "tier": "T1",
                     "title": "Never adjudicated", "proposed_at": "2026-07-13T09:45:00+00:00"},
                ],
                "verdicts": [
                    {"id": "p1", "decision": "never_ruled",
                     "reason_plain": "adjudication did not reach this docket",
                     "adjudicated_at": "2026-07-13T10:00:00+00:00"},
                ],
                "builds": [],
            },
        )
        result = achievements(root=tmp_path)
        c = result["cycles"][0]
        hl = c["headline_plain"]
        assert "never adjudicated" in hl.lower() or "never_adjudicated" in hl.lower(), \
            f"expected 'never adjudicated' in headline: {hl}"

    def test_headline_authorized_pr_opened(self, tmp_path: Path) -> None:
        from admin.metabolism_achievements import achievements  # noqa: PLC0415
        jdir = self._jdir(tmp_path)
        _make_journal_file(
            jdir, "cycle-2026-07-13-auth",
            achievements={
                "proposals": [
                    {"id": "p1", "lobe": "til", "kind": "test", "tier": "T0",
                     "title": "A great test", "proposed_at": "2026-07-13T09:45:00+00:00"},
                ],
                "verdicts": [
                    {"id": "p1", "decision": "authorized",
                     "reason_plain": "authorized by orchestrator and adversary",
                     "adjudicated_at": "2026-07-13T10:00:00+00:00"},
                ],
                "builds": [
                    {"id": "p1", "status": "pr_opened", "pr_number": 2501,
                     "pr_url": "https://github.com/owner/repo/pull/2501",
                     "built_at": "2026-07-13T11:00:00+00:00"},
                ],
            },
        )
        result = achievements(root=tmp_path)
        c = result["cycles"][0]
        hl = c["headline_plain"]
        assert "authorized" in hl.lower() or "pr opened" in hl.lower(), \
            f"expected authorized+PR in headline: {hl}"
        assert c["lobes"]["til"]["authorized"] == 1
        assert len(c["lobes"]["til"]["prs"]) == 1

    def test_absent_dirs_ok(self, tmp_path: Path) -> None:
        """No data/ directory at all — must not raise."""
        from admin.metabolism_achievements import achievements  # noqa: PLC0415
        result = achievements(root=tmp_path)
        assert result["cycles"] == []


class TestVerdictPlainWordMapping:
    """Unit tests for _screen_reason_to_plain verb mapping."""

    def test_do_not_rebuild(self) -> None:
        from scripts.metabolism_adjudicate import _screen_reason_to_plain  # noqa: PLC0415
        r = _screen_reason_to_plain("collides with a DO_NOT_REBUILD kill", "deny", True, False)
        assert "standing kill" in r or "DO_NOT_REBUILD" in r

    def test_active_build_map(self) -> None:
        from scripts.metabolism_adjudicate import _screen_reason_to_plain  # noqa: PLC0415
        r = _screen_reason_to_plain("collides with an ACTIVE_BUILD_MAP open lane", "deny", True, False)
        assert "open PR" in r or "ACTIVE_BUILD_MAP" in r

    def test_adversary_veto(self) -> None:
        from scripts.metabolism_adjudicate import _screen_reason_to_plain  # noqa: PLC0415
        r = _screen_reason_to_plain("no_collision", "deny", True, True)
        assert "adversary" in r.lower()

    def test_llm_deny_screen_approve(self) -> None:
        from scripts.metabolism_adjudicate import _screen_reason_to_plain  # noqa: PLC0415
        r = _screen_reason_to_plain("no_collision", "deny", False, True)
        assert "model" in r.lower() or "denied" in r.lower()

    def test_authorized(self) -> None:
        from scripts.metabolism_adjudicate import _screen_reason_to_plain  # noqa: PLC0415
        r = _screen_reason_to_plain("no_collision", "grant", False, True)
        assert "authorized" in r.lower()

    def test_never_raises_on_none(self) -> None:
        from scripts.metabolism_adjudicate import _screen_reason_to_plain  # noqa: PLC0415
        r = _screen_reason_to_plain("", "", False, False)
        assert isinstance(r, str)

    def test_no_case_law_collision_is_not_denial(self) -> None:
        """FIX 3: the APPROVE sentinel 'no case-law collision' must NOT map to a denial phrase.

        engine/metabolism/adjudicate.py:196 returns {"allow": True, "reason": "no case-law collision"}
        when the screen passes.  Old substring-sniff matched 'collision' and incorrectly
        reported a screen denial.  The fix uses screen_allow=True (the boolean) directly.
        """
        from scripts.metabolism_adjudicate import _screen_reason_to_plain  # noqa: PLC0415
        # VERBATIM engine string (engine/metabolism/adjudicate.py:196).
        r = _screen_reason_to_plain(
            "no case-law collision",  # screen_reason — the APPROVE sentinel
            "grant",                  # orch_decision
            False,                    # adv_veto
            True,                     # has_llm_opinion
            screen_allow=True,        # the boolean that drives the mapper in FIX 3
        )
        # Must NOT contain any denial phrase.
        assert "safety screen denied" not in r, \
            f"APPROVE sentinel was incorrectly mapped to denial: {r!r}"
        assert "denied" not in r.lower() or "safety screen" not in r.lower(), \
            f"APPROVE sentinel was incorrectly mapped to denial: {r!r}"
        # Should map to "authorized".
        assert "authorized" in r.lower(), \
            f"expected 'authorized' for grant+screen_allow=True, got: {r!r}"


class TestProposeEnrichment:
    """Unit tests for _append_achievements_proposals."""

    def test_append_proposals(self, tmp_path: Path) -> None:
        from scripts.metabolism_propose import _append_achievements_proposals  # noqa: PLC0415
        from scripts.metabolism_journal import _read_journal  # noqa: PLC0415
        cycle_id = "cycle-2026-07-13-proptest"
        docket = {
            "lobe": "til",
            "proposals": [
                {"proposal_id": "p-abc", "lobe": "til", "kind": "study",
                 "tier": "T1", "title": "X" * 150},  # title > 120 → truncated
                {"proposal_id": "p-def", "lobe": "til", "kind": "test",
                 "tier": "T0", "title": "Short"},
            ],
        }
        _append_achievements_proposals(cycle_id, docket, root=tmp_path)
        j = _read_journal(cycle_id, tmp_path)
        props = j["achievements"]["proposals"]
        assert len(props) == 2
        assert all(len(p["title"]) <= 120 for p in props), "title must be <=120 chars"
        assert props[0]["id"] == "p-abc"
        assert props[1]["id"] == "p-def"

    def test_idempotent(self, tmp_path: Path) -> None:
        """Calling twice does not duplicate rows."""
        from scripts.metabolism_propose import _append_achievements_proposals  # noqa: PLC0415
        from scripts.metabolism_journal import _read_journal  # noqa: PLC0415
        cycle_id = "cycle-2026-07-13-idem"
        docket = {
            "lobe": "til",
            "proposals": [{"proposal_id": "p-idem", "lobe": "til", "kind": "test",
                            "tier": "T0", "title": "Test"}],
        }
        _append_achievements_proposals(cycle_id, docket, root=tmp_path)
        _append_achievements_proposals(cycle_id, docket, root=tmp_path)
        j = _read_journal(cycle_id, tmp_path)
        assert len(j["achievements"]["proposals"]) == 1, "idempotency violated"

    def test_empty_docket_noop(self, tmp_path: Path) -> None:
        """Empty proposals list → no journal file created."""
        from scripts.metabolism_propose import _append_achievements_proposals  # noqa: PLC0415
        cycle_id = "cycle-2026-07-13-empty"
        _append_achievements_proposals(cycle_id, {"proposals": []}, root=tmp_path)
        jdir = tmp_path / "data" / "metabolism" / "journal"
        assert not (jdir / f"{cycle_id}.json").exists()

    def test_never_raises_on_bad_docket(self, tmp_path: Path) -> None:
        """Malformed docket dict → no exception."""
        from scripts.metabolism_propose import _append_achievements_proposals  # noqa: PLC0415
        _append_achievements_proposals("cycle-bad", None, root=tmp_path)  # type: ignore[arg-type]


class TestNeverRuledDerivation:
    """Tests for never_ruled verdict generation in adjudicate enrichment."""

    def test_never_ruled_in_achievements_verdicts(self, tmp_path: Path) -> None:
        """Proposals in achievements.proposals with no governance rows → decision=never_ruled."""
        from scripts.metabolism_journal import _read_journal, _write_journal, _default_journal  # noqa: PLC0415
        from scripts.metabolism_adjudicate import _append_achievements_verdicts  # noqa: PLC0415

        cycle_id = "cycle-2026-07-13-nr"
        docket_dir = tmp_path / "data" / "metabolism" / "dockets"
        docket_dir.mkdir(parents=True)
        docket = {
            "cycle_id": cycle_id,
            "lobe": "til",
            "proposals": [
                {"proposal_id": "p-nr1", "lobe": "til", "kind": "study",
                 "tier": "T1", "title": "Proposal never ruled"},
            ],
        }
        dp = docket_dir / f"{cycle_id}.json"
        dp.write_text(json.dumps(docket))

        # Write journal with proposals but no verdicts
        j = _default_journal(cycle_id)
        j["achievements"] = {
            "proposals": [
                {"id": "p-nr1", "lobe": "til", "kind": "study", "tier": "T1",
                 "title": "Proposal never ruled", "proposed_at": "2026-07-13T09:45:00+00:00"},
            ],
            "verdicts": [],
        }
        # Override journal dir
        jdir = tmp_path / "data" / "metabolism" / "journal"
        jdir.mkdir(parents=True, exist_ok=True)
        (jdir / f"{cycle_id}.json").write_text(json.dumps(j))

        # Call resolve role — governance dir is absent so _derive_verdict_plain
        # falls back gracefully; p-nr1 has no governance rows → never_ruled
        _append_achievements_verdicts(cycle_id, dp, "resolve", [], root=tmp_path)

        j2 = _read_journal(cycle_id, tmp_path)
        verdicts = j2["achievements"]["verdicts"]
        # FIX 6: no governance rows → decision MUST be "never_ruled" (not "denied").
        assert len(verdicts) >= 1, "expected at least one verdict"
        v = next((v for v in verdicts if v["id"] == "p-nr1"), None)
        assert v is not None, "p-nr1 verdict not found"
        assert v["decision"] == "never_ruled", (
            f"expected never_ruled for no-rows case, got: {v['decision']!r}"
        )
        assert len(v["reason_plain"]) <= 160
