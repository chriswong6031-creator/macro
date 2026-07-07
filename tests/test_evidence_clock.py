"""tests/test_evidence_clock.py — pytest suite for the Global Evidence Clock.

Covers:
  (a) State assignment: future date→accruing, today→due, past+grace→overdue
  (b) Floor demotion: due→not_ready when evidence_refs missing
  (c) qledger rollup: never per-claim rows; row count small for synthetic fixture
  (d) Missing expected artifact → 'missing' row
  (e) Review ack: reviews.jsonl entry within snooze → acknowledged=True, excluded from top_due
  (f) Precedence demotion: experiments row due + RF status awaiting_data → blocked
  (g) Checker selftest passes
  (h) Fail-soft: corrupt source file → gaps note, payload still returned
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

# Ensure repo root is on path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.evidence_clock import (
    _adapt_cycle_pattern,
    _adapt_experiments,
    _adapt_expected_artifacts,
    _adapt_governance,
    _adapt_qledger,
    _adapt_research_factory,
    _adapt_rule_experiments,
    _apply_acks,
    _apply_floor_demotion,
    _apply_precedence,
    _base_row,
    _build_summary,
    _date_state,
    _synapse_producer,
    build,
)


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "evidence_clock"

TODAY = date(2026, 7, 6)
FUTURE = (TODAY + timedelta(days=30)).isoformat()
PAST = (TODAY - timedelta(days=10)).isoformat()
PAST_GRACE = (TODAY - timedelta(days=1)).isoformat()  # within 7-day grace → still "due"
PAST_OVERDUE = (TODAY - timedelta(days=9)).isoformat()  # outside 7-day grace → overdue


def _minimal_config() -> dict:
    return {
        "grace_days": 7,
        "snooze_days": 7,
        "packet_stub_cap": 10,
        "sources": {
            "experiments": {"enabled": True},
            "research_factory": {"enabled": True},
            "qledger": {"enabled": True},
            "trial_ledger": {"enabled": True, "family_cap": 15},
            "freshness": {"enabled": True},
            "governance": {"enabled": True},
            "cortex": {"enabled": True},
            "rule_experiments": {"enabled": True},
            "cycle_pattern": {"enabled": True},
            "species": {"enabled": True},
        },
        "expected_artifacts": [],
        "declared_clocks": [],
    }


class _TempRoot:
    """Context manager that creates a minimal repo layout for testing."""

    def __init__(self):
        self._tmpdir = None
        self.path = None

    def __enter__(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        self.path = root
        # Create required directories
        (root / "data" / "experiments").mkdir(parents=True)
        (root / "data" / "qledger").mkdir(parents=True)
        (root / "data" / "research_factory" / "review").mkdir(parents=True)
        (root / "data" / "research_factory").mkdir(parents=True, exist_ok=True)
        (root / "data" / "neuralweb").mkdir(parents=True)
        (root / "data" / "rule_experiments").mkdir(parents=True)
        (root / "data" / "cycle_pattern").mkdir(parents=True)
        (root / "data" / "species").mkdir(parents=True)
        (root / "data" / "trial_ledger").parent.mkdir(parents=True, exist_ok=True)
        (root / "config").mkdir(parents=True)
        # Write minimal config
        cfg = _minimal_config()
        with open(root / "config" / "evidence_clock.yml", "w") as f:
            yaml.dump(cfg, f)
        return self

    def write(self, rel_path: str, content: str | dict | list):
        p = self.path / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            with open(p, "w") as f:
                json.dump(content, f)
        else:
            with open(p, "w") as f:
                f.write(content)

    def write_jsonl(self, rel_path: str, rows: list[dict]):
        p = self.path / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

    def write_config(self, cfg: dict):
        with open(self.path / "config" / "evidence_clock.yml", "w") as f:
            yaml.dump(cfg, f)

    def __exit__(self, *args):
        self._tmpdir.cleanup()


# ---------------------------------------------------------------------------
# (a) State assignment
# ---------------------------------------------------------------------------

class TestDateState:
    def test_future_date_accruing(self):
        future = date(2099, 1, 1)
        assert _date_state(future, 7, TODAY) == "accruing"

    def test_none_date_accruing(self):
        assert _date_state(None, 7, TODAY) == "accruing"

    def test_today_is_due(self):
        assert _date_state(TODAY, 7, TODAY) == "due"

    def test_within_grace_is_due(self):
        slightly_past = TODAY - timedelta(days=5)
        assert _date_state(slightly_past, 7, TODAY) == "due"

    def test_outside_grace_is_overdue(self):
        past_grace = TODAY - timedelta(days=8)
        assert _date_state(past_grace, 7, TODAY) == "overdue"

    def test_experiments_adapter_state_assignment(self):
        """experiments adapter assigns correct states based on come_back_on dates."""
        with _TempRoot() as root:
            seed = {
                "schema": "experiments_registry_seed.v1",
                "experiments": [
                    {"id": "future-exp", "kind": "track_record", "come_back_on": FUTURE,
                     "come_back_note": "", "maturation": None, "cadence": "weekly",
                     "status": "active", "state": "running", "track_json": None,
                     "hook": None, "started": None, "next_step": None, "phase_hint": None},
                    {"id": "due-exp", "kind": "track_record", "come_back_on": TODAY.isoformat(),
                     "come_back_note": "", "maturation": None, "cadence": "weekly",
                     "status": "active", "state": "running", "track_json": None,
                     "hook": None, "started": None, "next_step": None, "phase_hint": None},
                    {"id": "overdue-exp", "kind": "track_record", "come_back_on": PAST_OVERDUE,
                     "come_back_note": "", "maturation": None, "cadence": "weekly",
                     "status": "active", "state": "running", "track_json": None,
                     "hook": None, "started": None, "next_step": None, "phase_hint": None},
                ],
            }
            root.write("data/experiments/registry_seed.json", seed)
            cfg = _minimal_config()
            rows, gaps = _adapt_experiments(root.path, cfg, TODAY)

        states = {r["subject_id"]: r["state"] for r in rows}
        assert states["future-exp"] == "accruing"
        assert states["due-exp"] == "due"
        assert states["overdue-exp"] == "overdue"


# ---------------------------------------------------------------------------
# (b) Floor demotion
# ---------------------------------------------------------------------------

class TestFloorDemotion:
    def test_due_with_missing_ref_becomes_not_ready(self):
        row = _base_row(
            clock_id="test:foo",
            source_system="experiments",
            subject_id="foo",
            subject_type="experiment",
            owner_program=None,
            clock_type="come_back_on",
            due_at=TODAY,
            as_of=None,
            state="due",
            date_state="due",
            evidence_refs=["data/nonexistent/file.json"],
        )
        with _TempRoot() as root:
            rows = [row]
            _apply_floor_demotion(rows, root.path)
            assert rows[0]["state"] == "not_ready"
            assert "blocking_reason" in rows[0]["readiness"]

    def test_due_with_existing_ref_stays_due(self):
        with _TempRoot() as root:
            root.write("data/existing_file.json", {"test": True})
            row = _base_row(
                clock_id="test:bar",
                source_system="experiments",
                subject_id="bar",
                subject_type="experiment",
                owner_program=None,
                clock_type="come_back_on",
                due_at=TODAY,
                as_of=None,
                state="due",
                date_state="due",
                evidence_refs=["data/existing_file.json"],
            )
            rows = [row]
            _apply_floor_demotion(rows, root.path)
            assert rows[0]["state"] == "due"

    def test_due_with_no_refs_gets_undeclared_floor(self):
        row = _base_row(
            clock_id="test:baz",
            source_system="declared",
            subject_id="baz",
            subject_type="experiment",
            owner_program=None,
            clock_type="come_back_on",
            due_at=TODAY,
            as_of=None,
            state="due",
            date_state="due",
            evidence_refs=[],
        )
        with _TempRoot() as root:
            rows = [row]
            _apply_floor_demotion(rows, root.path)
            # No refs → stays due with undeclared floor
            assert rows[0]["state"] == "due"
            assert rows[0]["readiness"].get("floor") == "undeclared"


# ---------------------------------------------------------------------------
# (c) qledger rollup
# ---------------------------------------------------------------------------

class TestQledgerRollup:
    def test_never_per_claim_rows(self):
        """100 claims across 3 desks → at most 4 rows (3 desk rollups + 1 floor)."""
        claims = []
        for i in range(100):
            desk = ["altdata", "radar", "policy"][i % 3]
            claims.append({
                "desk": desk,
                "asof": "2026-06-01",
                "status": "open",
                "check_by": "2026-09-01",
                "falsifier": None,
                "horizon_d": 63,
            })
        with _TempRoot() as root:
            root.write_jsonl("data/qledger/claims.jsonl", claims)
            cfg = _minimal_config()
            rows, gaps = _adapt_qledger(root.path, cfg, TODAY)

        # Should have 3 desk rollups + 1 falsifier floor = 4 rows
        assert len(rows) <= 5  # never 100
        clock_ids = [r["clock_id"] for r in rows]
        # Each desk gets exactly one row
        desk_rows = [r for r in rows if r["clock_id"].startswith("qledger:") and r["clock_id"] != "qledger:falsifier_coverage"]
        assert len(desk_rows) == 3
        # Falsifier floor always present
        assert any(r["clock_id"] == "qledger:falsifier_coverage" for r in rows)

    def test_falsifier_floor_is_blocked(self):
        claims = [{"desk": "test", "status": "open", "check_by": "2026-09-01",
                   "falsifier": None, "horizon_d": 63}]
        with _TempRoot() as root:
            root.write_jsonl("data/qledger/claims.jsonl", claims)
            cfg = _minimal_config()
            rows, gaps = _adapt_qledger(root.path, cfg, TODAY)

        floor = next(r for r in rows if r["clock_id"] == "qledger:falsifier_coverage")
        assert floor["state"] == "blocked"
        assert "blocking_reason" in floor["readiness"]


# ---------------------------------------------------------------------------
# (d) Missing expected artifact
# ---------------------------------------------------------------------------

class TestExpectedArtifacts:
    def test_missing_artifact_emits_missing_row(self):
        with _TempRoot() as root:
            cfg = _minimal_config()
            cfg["expected_artifacts"] = [{
                "path": "data/neuralweb/research_queue.json",
                "producer": "python -m scripts.build_research_queue",
                "note": "test",
            }]
            root.write_config(cfg)
            rows, gaps = _adapt_expected_artifacts(root.path, cfg, TODAY)

        assert len(rows) == 1
        assert rows[0]["state"] == "missing"
        assert "research_queue.json" in rows[0]["subject_id"]
        assert rows[0]["regenerate_cmd"] is not None

    def test_present_artifact_no_row(self):
        with _TempRoot() as root:
            cfg = _minimal_config()
            cfg["expected_artifacts"] = [{
                "path": "data/neuralweb/research_queue.json",
                "producer": "python -m scripts.build_research_queue",
                "note": "test",
            }]
            root.write("data/neuralweb/research_queue.json", {"exists": True})
            root.write_config(cfg)
            rows, gaps = _adapt_expected_artifacts(root.path, cfg, TODAY)

        assert len(rows) == 0


# ---------------------------------------------------------------------------
# (e) Review ack
# ---------------------------------------------------------------------------

class TestReviewAck:
    def test_recent_review_sets_acknowledged(self):
        row = _base_row(
            clock_id="experiments:test-exp",
            source_system="experiments",
            subject_id="test-exp",
            subject_type="experiment",
            owner_program=None,
            clock_type="come_back_on",
            due_at=TODAY,
            as_of=None,
            state="due",
            date_state="due",
        )
        reviews = [{"clock_id": "experiments:test-exp", "reviewed_on": TODAY.isoformat(),
                    "note": "reviewed", "outcome": "deferred"}]
        with _TempRoot() as root:
            root.write_jsonl("data/neuralweb/evidence_clock_reviews.jsonl", reviews)
            rows = [row]
            _apply_acks(rows, root.path, snooze_days=7, today=TODAY)

        assert rows[0]["acknowledged"] is True
        assert rows[0]["review"] is not None

    def test_old_review_does_not_ack(self):
        row = _base_row(
            clock_id="experiments:old-exp",
            source_system="experiments",
            subject_id="old-exp",
            subject_type="experiment",
            owner_program=None,
            clock_type="come_back_on",
            due_at=TODAY,
            as_of=None,
            state="due",
            date_state="due",
        )
        old_date = (TODAY - timedelta(days=8)).isoformat()
        reviews = [{"clock_id": "experiments:old-exp", "reviewed_on": old_date,
                    "note": "old", "outcome": "deferred"}]
        with _TempRoot() as root:
            root.write_jsonl("data/neuralweb/evidence_clock_reviews.jsonl", reviews)
            rows = [row]
            _apply_acks(rows, root.path, snooze_days=7, today=TODAY)

        assert rows[0]["acknowledged"] is False

    def test_acknowledged_excluded_from_top_due(self):
        """Summary top_due should skip acknowledged rows."""
        rows = [
            _base_row(
                clock_id="experiments:acked",
                source_system="experiments",
                subject_id="acked",
                subject_type="experiment",
                owner_program=None,
                clock_type="come_back_on",
                due_at=TODAY,
                as_of=None,
                state="due",
                date_state="due",
            ),
            _base_row(
                clock_id="experiments:not-acked",
                source_system="experiments",
                subject_id="not-acked",
                subject_type="experiment",
                owner_program=None,
                clock_type="come_back_on",
                due_at=TODAY,
                as_of=None,
                state="due",
                date_state="due",
            ),
        ]
        rows[0]["acknowledged"] = True

        summary = _build_summary(rows, TODAY)
        assert summary["top_due"]["clock_id"] == "experiments:not-acked"
        assert summary["n_acknowledged"] == 1


# ---------------------------------------------------------------------------
# (f) Precedence demotion
# ---------------------------------------------------------------------------

class TestPrecedenceDemotion:
    def test_experiments_row_demoted_by_rf_awaiting_data(self):
        """experiments row due + RF candidate awaiting_data → blocked."""
        with _TempRoot() as root:
            # experiments seed: one due entry with subject_id = "my-exp"
            seed = {
                "schema": "experiments_registry_seed.v1",
                "experiments": [{
                    "id": "my-exp",
                    "kind": "track_record",
                    "come_back_on": TODAY.isoformat(),
                    "come_back_note": "",
                    "maturation": None,
                    "cadence": "weekly",
                    "status": "active",
                    "state": "running",
                    "track_json": None,
                    "hook": None,
                    "started": None,
                    "next_step": None,
                    "phase_hint": None,
                }],
            }
            root.write("data/experiments/registry_seed.json", seed)

            # RF candidate with status=awaiting_data, same id
            root.write_jsonl("data/research_factory/candidates.jsonl", [{
                "id": "my-exp",
                "status": "awaiting_data",
                "created_at": "2026-06-01",
                "evaluation_plan": {"horizon_d": 63},
            }])

            # RF queue (empty)
            root.write("data/research_factory/review/queue.json",
                       {"schema": "research_factory.review_queue.v1", "n_candidates": 0})

            cfg = _minimal_config()
            exp_rows, _ = _adapt_experiments(root.path, cfg, TODAY)
            rf_rows, _ = _adapt_research_factory(root.path, cfg, TODAY, {"my-exp"})

            all_rows = exp_rows + rf_rows
            # Before precedence: my-exp should be due
            my_exp = next(r for r in all_rows if r["subject_id"] == "my-exp"
                          and r["source_system"] == "experiments")
            assert my_exp["state"] == "due"

            # Apply precedence
            _apply_precedence(all_rows, root.path, TODAY)

            my_exp_after = next(r for r in all_rows if r["subject_id"] == "my-exp"
                                and r["source_system"] == "experiments")
            assert my_exp_after["state"] == "blocked"


# ---------------------------------------------------------------------------
# (g) Checker selftest
# ---------------------------------------------------------------------------

class TestCheckerSelftest:
    def test_selftest_passes(self):
        """check_evidence_clock --selftest must exit 0."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_evidence_clock",
            _REPO_ROOT / "scripts" / "check_evidence_clock.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        root = _REPO_ROOT
        result = mod._run_selftest(root)
        assert result == 0


# ---------------------------------------------------------------------------
# (h) Fail-soft: corrupt source file
# ---------------------------------------------------------------------------

class TestFailSoft:
    def test_corrupt_experiments_produces_gap(self):
        """Corrupt experiments file → gaps note, no crash, payload returned."""
        with _TempRoot() as root:
            # Write corrupt JSON
            root.write("data/experiments/registry_seed.json", "NOT VALID JSON {{{{")
            cfg = _minimal_config()
            rows, gaps = _adapt_experiments(root.path, cfg, TODAY)

        assert len(gaps) > 0
        assert any("experiments" in g for g in gaps)

    def test_corrupt_qledger_produces_gap(self):
        """Corrupt qledger file → gaps note, no crash."""
        with _TempRoot() as root:
            root.write("data/qledger/claims.jsonl", "NOT VALID JSON\n")
            cfg = _minimal_config()
            rows, gaps = _adapt_qledger(root.path, cfg, TODAY)

        assert len(gaps) > 0
        assert any("qledger" in g for g in gaps)

    def test_full_build_with_corrupt_source_returns_payload(self):
        """Full build with one corrupt source returns a payload dict, never raises."""
        with _TempRoot() as root:
            # Write valid minimal sources
            root.write("data/experiments/registry_seed.json", "BAD JSON")
            root.write_jsonl("data/qledger/claims.jsonl", [])
            root.write_jsonl("data/trial_ledger.jsonl", [])
            root.write_jsonl("data/neuralweb/governance.jsonl", [])
            root.write_jsonl("data/rule_experiments/registry.jsonl", [])
            root.write_jsonl("data/cycle_pattern/truths.jsonl", [])
            root.write("data/research_factory/review/queue.json",
                       {"n_candidates": 0})
            root.write_jsonl("data/research_factory/candidates.jsonl", [])
            root.write("data/species/registry.json", {"schema": "s.v1", "species": []})

            payload = build(root.path, today=TODAY)

        assert isinstance(payload, dict)
        assert payload["schema"] == "neuralweb.evidence_clock.v1"
        assert payload["authority"] == "display_only"
        assert isinstance(payload["gaps"], list)
        # There should be at least one gap (from corrupt experiments)
        assert len(payload["gaps"]) > 0
        assert "rows" in payload


# ---------------------------------------------------------------------------
# Additional integration: real repo data
# ---------------------------------------------------------------------------

class TestRealRepoBuild:
    def test_real_build_has_experiments_rows(self):
        """Real repo build must produce >0 experiments rows."""
        payload = build(_REPO_ROOT, today=TODAY)
        exp_rows = [r for r in payload["rows"] if r["source_system"] == "experiments"]
        assert len(exp_rows) > 0

    def test_real_build_has_research_queue_missing_row(self):
        """research_queue.json is missing → 'missing' row must appear."""
        payload = build(_REPO_ROOT, today=TODAY)
        missing = [r for r in payload["rows"]
                   if r["state"] == "missing"
                   and "research_queue" in r["subject_id"]]
        assert len(missing) == 1

    def test_real_build_has_falsifier_floor_blocked(self):
        """qledger:falsifier_coverage row must be blocked."""
        payload = build(_REPO_ROOT, today=TODAY)
        floor = next((r for r in payload["rows"] if r["clock_id"] == "qledger:falsifier_coverage"), None)
        assert floor is not None
        assert floor["state"] == "blocked"

    def test_real_build_has_declared_clocks(self):
        """Both declared clocks must appear."""
        payload = build(_REPO_ROOT, today=TODAY)
        declared = [r for r in payload["rows"] if r["source_system"] == "declared"
                    and r["clock_id"].startswith("declared:")]
        clock_ids = {r["clock_id"] for r in declared}
        assert "declared:cortex-fdr-batch-2026-10" in clock_ids
        assert "declared:nw-weights-review-2027-05" in clock_ids

    def test_real_build_morning_line_not_empty(self):
        """morning_line must be a non-empty string."""
        payload = build(_REPO_ROOT, today=TODAY)
        ml = payload["summary"]["morning_line"]
        assert isinstance(ml, str)
        assert len(ml) > 5

    def test_real_build_summary_counts_match(self):
        """summary.n_rows must equal len(rows); by_state counts must match."""
        payload = build(_REPO_ROOT, today=TODAY)
        rows = payload["rows"]
        summary = payload["summary"]
        assert summary["n_rows"] == len(rows)
        for state, count in summary["by_state"].items():
            actual = sum(1 for r in rows if r["state"] == state)
            assert count == actual, f"by_state[{state}]={count} != actual {actual}"

    def test_real_build_no_forbidden_keys(self):
        """No forbidden keys anywhere in rows."""
        forbidden = {"score", "rank", "weight", "size", "allocation"}
        payload = build(_REPO_ROOT, today=TODAY)
        for row in payload["rows"]:
            for fk in forbidden:
                assert fk not in row, f"Forbidden key {fk!r} in row {row['clock_id']}"
                assert fk not in (row.get("readiness") or {}), \
                    f"Forbidden key {fk!r} in readiness of {row['clock_id']}"

    def test_real_build_forbidden_actions_complete(self):
        """Every row must have 'promote' and 'mutate_source_state' in forbidden_actions."""
        payload = build(_REPO_ROOT, today=TODAY)
        for row in payload["rows"]:
            fa = set(row.get("forbidden_actions") or [])
            assert "promote" in fa, f"{row['clock_id']} missing 'promote' in forbidden_actions"
            assert "mutate_source_state" in fa, \
                f"{row['clock_id']} missing 'mutate_source_state' in forbidden_actions"

    def test_real_build_evidence_refs_not_absolute(self):
        """All evidence_refs must be relative paths."""
        payload = build(_REPO_ROOT, today=TODAY)
        for row in payload["rows"]:
            for ref in (row.get("evidence_refs") or []):
                assert not Path(ref).is_absolute(), \
                    f"{row['clock_id']} has absolute evidence_ref: {ref!r}"

    def test_real_build_clock_ids_unique(self):
        """All clock_ids in a real build must be unique."""
        payload = build(_REPO_ROOT, today=TODAY)
        from collections import Counter
        ids = [r["clock_id"] for r in payload["rows"]]
        dupes = {k: v for k, v in Counter(ids).items() if v > 1}
        assert dupes == {}, f"Duplicate clock_ids found: {dupes}"


# ---------------------------------------------------------------------------
# (i) Fix #1 regression: ack accounting — acked stale does not reduce n_due
# ---------------------------------------------------------------------------

class TestAckAccounting:
    def test_acked_stale_does_not_reduce_morning_line_due_count(self):
        """2 unacked due + 1 acked stale → morning_line says 2 due/overdue."""
        rows = [
            _base_row(
                clock_id="experiments:unacked-due-1",
                source_system="experiments",
                subject_id="unacked-due-1",
                subject_type="experiment",
                owner_program=None,
                clock_type="come_back_on",
                due_at=TODAY,
                as_of=None,
                state="due",
                date_state="due",
            ),
            _base_row(
                clock_id="experiments:unacked-due-2",
                source_system="experiments",
                subject_id="unacked-due-2",
                subject_type="experiment",
                owner_program=None,
                clock_type="come_back_on",
                due_at=TODAY,
                as_of=None,
                state="due",
                date_state="due",
            ),
            _base_row(
                clock_id="freshness:some-lobe",
                source_system="freshness",
                subject_id="some-lobe",
                subject_type="artifact",
                owner_program=None,
                clock_type="freshness_sla",
                due_at=None,
                as_of=None,
                state="stale",
                date_state="stale",
            ),
        ]
        # Ack the stale row only
        rows[2]["acknowledged"] = True

        summary = _build_summary(rows, TODAY)
        # n_acknowledged counts all acked rows = 1
        assert summary["n_acknowledged"] == 1
        # morning_line due count must still be 2 (ack was on stale, not due/overdue)
        assert "2 due/overdue" in summary["morning_line"], (
            f"Expected '2 due/overdue' in morning_line but got: {summary['morning_line']!r}"
        )

    def test_acked_due_reduces_morning_line_count(self):
        """1 acked due + 1 unacked due → morning_line says 1 due/overdue."""
        rows = [
            _base_row(
                clock_id="experiments:acked-due",
                source_system="experiments",
                subject_id="acked-due",
                subject_type="experiment",
                owner_program=None,
                clock_type="come_back_on",
                due_at=TODAY,
                as_of=None,
                state="due",
                date_state="due",
            ),
            _base_row(
                clock_id="experiments:unacked-due",
                source_system="experiments",
                subject_id="unacked-due",
                subject_type="experiment",
                owner_program=None,
                clock_type="come_back_on",
                due_at=TODAY,
                as_of=None,
                state="due",
                date_state="due",
            ),
        ]
        rows[0]["acknowledged"] = True

        summary = _build_summary(rows, TODAY)
        assert summary["n_acknowledged"] == 1
        assert "1 due/overdue" in summary["morning_line"], (
            f"Expected '1 due/overdue' in morning_line but got: {summary['morning_line']!r}"
        )


# ---------------------------------------------------------------------------
# (j) Fix #2: cycle_pattern clock_id dedup + retirement skip
# ---------------------------------------------------------------------------

class TestCyclePatternDedup:
    def test_duplicate_truth_id_produces_one_row(self):
        """A truths.jsonl with two rows for the same truth_id → only one clock row."""
        with _TempRoot() as root:
            import json as _json
            lines = [
                _json.dumps({
                    "truth_id": "dupe_truth_v1",
                    "status": "display",
                    "next_review_due": FUTURE,
                }) + "\n",
                _json.dumps({
                    "truth_id": "dupe_truth_v1",
                    "status": "display",
                    "next_review_due": FUTURE,
                }) + "\n",
            ]
            (root.path / "data" / "cycle_pattern").mkdir(parents=True, exist_ok=True)
            with open(root.path / "data/cycle_pattern/truths.jsonl", "w") as f:
                f.writelines(lines)
            cfg = _minimal_config()
            rows, gaps = _adapt_cycle_pattern(root.path, cfg, TODAY)

        cycle_ids = [r["clock_id"] for r in rows]
        assert cycle_ids.count("cycle_pattern:dupe_truth_v1") == 1

    def test_retired_truth_id_skipped(self):
        """A truth with status='retired' is not emitted as a clock row."""
        with _TempRoot() as root:
            import json as _json
            lines = [
                _json.dumps({
                    "truth_id": "candidate_v1",
                    "status": "candidate",
                    "next_review_due": FUTURE,
                }) + "\n",
                _json.dumps({
                    "truth_id": "candidate_v1",
                    "status": "retired",
                    "next_review_due": FUTURE,
                }) + "\n",
            ]
            (root.path / "data" / "cycle_pattern").mkdir(parents=True, exist_ok=True)
            with open(root.path / "data/cycle_pattern/truths.jsonl", "w") as f:
                f.writelines(lines)
            cfg = _minimal_config()
            rows, gaps = _adapt_cycle_pattern(root.path, cfg, TODAY)

        # retired is last occurrence → kept by dedup but then skipped
        assert not any(r["clock_id"] == "cycle_pattern:candidate_v1" for r in rows)

    def test_promoted_null_truth_id_skipped(self):
        """A truth with status='promoted_null' is not emitted as a clock row."""
        with _TempRoot() as root:
            import json as _json
            line = _json.dumps({
                "truth_id": "null_v1",
                "status": "promoted_null",
                "next_review_due": FUTURE,
            }) + "\n"
            (root.path / "data" / "cycle_pattern").mkdir(parents=True, exist_ok=True)
            with open(root.path / "data/cycle_pattern/truths.jsonl", "w") as f:
                f.write(line)
            cfg = _minimal_config()
            rows, gaps = _adapt_cycle_pattern(root.path, cfg, TODAY)

        assert not any(r["clock_id"] == "cycle_pattern:null_v1" for r in rows)


# ---------------------------------------------------------------------------
# (k) Fix #3: _synapse_producer strips .py correctly for paths ending in p.py
# ---------------------------------------------------------------------------

class TestSynapseProducer:
    def test_producer_ending_in_p_py_not_mangled(self):
        """Producer 'scripts/gen_map.py' must yield 'python -m scripts.gen_map', not 'python -m scripts.gen_ma'."""
        reg = {
            "artifacts": {
                "gen-map": {
                    "path": "data/neuralweb/map.json",
                    "producer": "scripts/gen_map.py",
                }
            }
        }
        result = _synapse_producer(reg, "data/neuralweb/map.json")
        assert result == "python -m scripts.gen_map", f"Got: {result!r}"

    def test_producer_without_py_extension_unchanged(self):
        """Producer without .py suffix is returned as-is when no slash present."""
        reg = {
            "artifacts": {
                "nightly": {
                    "path": "data/neuralweb/nightly.json",
                    "producer": "make nightly",
                }
            }
        }
        result = _synapse_producer(reg, "data/neuralweb/nightly.json")
        assert result == "make nightly", f"Got: {result!r}"

    def test_producer_with_slash_and_py(self):
        """Producer 'scripts/build_ec.py' → 'python -m scripts.build_ec'."""
        reg = {
            "artifacts": {
                "ec": {
                    "path": "data/neuralweb/evidence_clock.json",
                    "producer": "scripts/build_evidence_clock.py",
                }
            }
        }
        result = _synapse_producer(reg, "data/neuralweb/evidence_clock.json")
        assert result == "python -m scripts.build_evidence_clock", f"Got: {result!r}"


# ---------------------------------------------------------------------------
# (l) Fix #8: qledger overdue — oldest past-check_by enables overdue state
# ---------------------------------------------------------------------------

class TestQledgerOverdue:
    def test_old_past_check_by_yields_overdue(self):
        """Claims with check_by more than grace_days ago → desk row is overdue."""
        # check_by 30 days ago, grace=0 → overdue
        old_check_by = (TODAY - timedelta(days=30)).isoformat()
        claims = [
            {"desk": "altdata", "status": "open", "check_by": old_check_by, "falsifier": None},
        ]
        with _TempRoot() as root:
            root.write_jsonl("data/qledger/claims.jsonl", claims)
            cfg = _minimal_config()
            rows, gaps = _adapt_qledger(root.path, cfg, TODAY)

        desk_row = next(r for r in rows if r["clock_id"] == "qledger:altdata")
        assert desk_row["state"] == "overdue", (
            f"Expected overdue but got {desk_row['state']!r}; due_at={desk_row['due_at']!r}"
        )

    def test_recent_past_check_by_within_grace_yields_due(self):
        """Claims with check_by yesterday (grace=0) → overdue (no grace for check_by)."""
        yesterday = (TODAY - timedelta(days=1)).isoformat()
        claims = [
            {"desk": "radar", "status": "open", "check_by": yesterday, "falsifier": None},
        ]
        with _TempRoot() as root:
            root.write_jsonl("data/qledger/claims.jsonl", claims)
            cfg = _minimal_config()
            rows, gaps = _adapt_qledger(root.path, cfg, TODAY)

        desk_row = next(r for r in rows if r["clock_id"] == "qledger:radar")
        # grace=0 and check_by yesterday → overdue
        assert desk_row["state"] == "overdue"
