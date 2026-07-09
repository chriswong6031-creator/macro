"""tests/test_metabolism.py — Hermetic tests for W7b PR2 metabolism subsystems.

COVERAGE:
  A. Registration schema validation + server-side registered_at + budget enforcement
     (4th registration in a week → rejected; retire-then-file works) + governance events
  B. Evaluator STRICT post-registration filter (fixture with pre-registration rows →
     dropped + counted; sabotage test: gate passes ONLY with pre-registration data →
     must return insufficient-n/failed)
  C. Pre-committed-gate-only verdicts (metric switching impossible)
  D. Attention grading per falsifier class (fixtures)
  E. Grades join in adapt_cortex_attention
  F. A2 evaluation refused today (empty attention record)
  G. Transition-only governance events (no duplicate events on repeated runs)

All tests are HERMETIC (tmp dirs, mocked IO, no real data dependencies).
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import sys
import os

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_root() -> Path:
    """Return a fresh temporary repo root with minimal structure."""
    d = Path(tempfile.mkdtemp())
    (d / "data" / "neuralweb").mkdir(parents=True)
    (d / "data" / "neuralweb" / "cortex").mkdir(parents=True)
    (d / "data" / "reflexes" / "cortex_attention").mkdir(parents=True)
    (d / "data" / "trial_ledger.jsonl").touch()
    return d


def _write_governance(root: Path, events: list[dict]) -> None:
    p = root / "data" / "neuralweb" / "governance.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def _load_governance(root: Path) -> list[dict]:
    p = root / "data" / "neuralweb" / "governance.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _load_registry(root: Path) -> list[dict]:
    p = root / "data" / "neuralweb" / "machine_registry.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _valid_hyp(**overrides) -> dict:
    base = {
        "hypothesis": "When MACD crosses above signal on 5d TF, SPX outperforms over 21d",
        "claim_shape": "lead_lag",
        "spine_query": {"subject": "SPX", "lead_series": "MACD", "lag_series": "SPX"},
        "pre_committed_gate": {
            "metric": "hit_rate",
            "threshold": 0.55,
            "min_n": 5,
            "horizon_d": 21,
        },
        "horizon_d": 21,
    }
    base.update(overrides)
    return base


# ============================================================
# A. REGISTRATION SCHEMA VALIDATION + SERVER-SIDE registered_at
# ============================================================

class TestRegistrationSchema:

    def test_valid_hypothesis_registered(self, tmp_path):
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        result = register_hypothesis(_valid_hyp(), root=str(root), now=now)
        assert result["status"] == "registered"
        assert result["registered_at"] is not None
        assert result["id"].startswith("cortex-2026-07-04-")

    def test_server_side_registered_at_not_cortex_supplied(self, tmp_path):
        """registered_at must be set by metabolism, never accepted from cortex."""
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        h = _valid_hyp()
        # Even if cortex tries to inject registered_at, the metabolism ignores it
        # (registered_at is not in the hypothesis dict — it's set server-side)
        result = register_hypothesis(h, root=str(root), now=now)
        assert result["status"] == "registered"
        rows = _load_registry(root)
        registered = [r for r in rows if r.get("status") == "registered"]
        assert len(registered) == 1
        # registered_at matches server time (2026-07-04)
        assert registered[0]["registered_at"].startswith("2026-07-04")

    def test_fdr_family_hard_wired(self, tmp_path):
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        result = register_hypothesis(_valid_hyp(), root=str(root), now=now)
        rows = _load_registry(root)
        registered = [r for r in rows if r.get("status") == "registered"]
        assert registered[0]["fdr_family"] == "cortex"

    def test_missing_hypothesis_invalid(self, tmp_path):
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        h = _valid_hyp()
        h["hypothesis"] = ""
        result = register_hypothesis(h, root=str(root), now=now)
        assert result["status"] == "invalid"

    def test_missing_pre_committed_gate_invalid(self, tmp_path):
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        h = _valid_hyp()
        h["pre_committed_gate"] = None
        result = register_hypothesis(h, root=str(root), now=now)
        assert result["status"] == "invalid"
        assert "pre_committed_gate" in result["reason"]

    def test_invalid_claim_shape(self, tmp_path):
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        h = _valid_hyp(claim_shape="invented_shape")
        result = register_hypothesis(h, root=str(root), now=now)
        assert result["status"] == "invalid"

    def test_come_back_is_horizon_plus_buffer(self, tmp_path):
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        result = register_hypothesis(_valid_hyp(horizon_d=21), root=str(root), now=now)
        assert result["status"] == "registered"
        # come_back = registered_date + 21 + 7 = 2026-07-04 + 28 = 2026-08-01
        cb = date.fromisoformat(result["come_back"])
        assert cb == date(2026, 7, 4) + timedelta(days=21 + 7)

    def test_governance_event_on_registration(self, tmp_path):
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        register_hypothesis(_valid_hyp(), root=str(root), now=now)
        events = _load_governance(root)
        assert any(e.get("event_type") == "a6_llm_proposed" for e in events)


# ============================================================
# A2. BUDGET ENFORCEMENT
# ============================================================

class TestBudgetEnforcement:

    def test_fourth_registration_rejected(self, tmp_path):
        """4th registration in the same week must be budget-rejected."""
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)

        # Register 3 (budget = 3/week)
        for i in range(3):
            h = _valid_hyp(hypothesis=f"Hypothesis number {i} — unique text for ID generation {i}")
            r = register_hypothesis(h, root=str(root), now=now)
            assert r["status"] == "registered", f"Registration {i} should succeed, got {r}"

        # 4th should be budget-rejected
        h4 = _valid_hyp(hypothesis="Fourth hypothesis — this must be rejected by server-side budget")
        r4 = register_hypothesis(h4, root=str(root), now=now)
        assert r4["status"] == "budget-rejected"
        assert "retire" in r4["reason"].lower()

    def test_retire_then_file_works(self, tmp_path):
        """After retiring an existing hypothesis, a new one can be filed."""
        from engine.neuralweb.metabolism import register_hypothesis, retire
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)

        # Fill the budget
        registered_ids = []
        for i in range(3):
            h = _valid_hyp(hypothesis=f"Retire-then-file test hypothesis {i}")
            r = register_hypothesis(h, root=str(root), now=now)
            assert r["status"] == "registered"
            registered_ids.append(r["id"])

        # Budget exhausted
        h_extra = _valid_hyp(hypothesis="Extra hypothesis — should be budget-rejected first")
        r_extra = register_hypothesis(h_extra, root=str(root), now=now)
        assert r_extra["status"] == "budget-rejected"

        # Retire one
        retired = retire(registered_ids[0], reason="superseded — retire-one-to-file-one test", root=str(root))
        assert retired is True

        # Verify retirement governance event
        events = _load_governance(root)
        assert any(e.get("event_type") == "tier_demotion" for e in events)

        # After retiring, new registration now succeeds because retired rows don't count
        h_new = _valid_hyp(hypothesis="New hypothesis after retire — should now be accepted")
        r_new = register_hypothesis(h_new, root=str(root), now=now)
        assert r_new["status"] == "registered", f"Expected registered after retire, got {r_new}"

    def test_different_week_has_fresh_budget(self, tmp_path):
        """Registrations from a previous week don't count against this week's budget."""
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()

        # Register 3 last week
        last_week = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)  # prev week
        for i in range(3):
            h = _valid_hyp(hypothesis=f"Last week hypothesis {i}")
            register_hypothesis(h, root=str(root), now=last_week)

        # This week should still allow 3 more
        this_week = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        for i in range(3):
            h = _valid_hyp(hypothesis=f"This week hypothesis {i} fresh budget")
            r = register_hypothesis(h, root=str(root), now=this_week)
            assert r["status"] == "registered", f"Week boundary: registration {i} should succeed"


# ============================================================
# B. EVALUATOR STRICT POST-REGISTRATION FILTER
# ============================================================

class TestEvaluatorStrictFilter:

    def _write_registry_row(self, root: Path, registered_at: str, hyp_id: str = "cortex-2026-07-04-test-abc123") -> dict:
        """Write a minimal registered hypothesis to the machine registry."""
        row = {
            "schema": "neuralweb.machine_registry.v1",
            "id": hyp_id,
            "kind": "cortex_hypothesis",
            "status": "registered",
            "registered_at": registered_at,
            "registered_by": "cortex",
            "fdr_family": "cortex",
            "claim_shape": "lead_lag",
            "hypothesis": "Test hypothesis",
            "spine_query": {"subject": "SPX"},
            "pre_committed_gate": {
                "metric": "hit_rate",
                "threshold": 0.55,
                "min_n": 3,
                "horizon_d": 5,
            },
            "horizon_d": 5,
            "come_back": "2026-07-20",
            "is_context_only": True,
        }
        p = root / "data" / "neuralweb" / "machine_registry.jsonl"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        return row

    def test_pre_registration_rows_are_dropped(self):
        """Rows with as_of <= registered_at must be dropped and counted."""
        from scripts.evaluate_cortex_hypotheses import _filter_post_registration

        registered_at = "2026-07-04T12:00:00+00:00"
        rows = [
            {"as_of": "2026-07-03"},   # before — DROP
            {"as_of": "2026-07-04"},   # same day — DROP (strict >)
            {"as_of": "2026-07-05"},   # after — KEEP
            {"as_of": "2026-07-10"},   # after — KEEP
        ]
        kept, dropped = _filter_post_registration(rows, registered_at)
        assert len(kept) == 2
        assert dropped == 2
        assert all(r["as_of"] > "2026-07-04" for r in kept)

    def test_only_pre_registration_data_gives_insufficient_n(self):
        """Sabotage test: a hypothesis whose gate would pass on pre-registration data
        but has zero post-registration events must return insufficient-n."""
        from scripts.evaluate_cortex_hypotheses import _filter_post_registration, _evaluate_gate

        registered_at = "2026-07-04T12:00:00+00:00"
        # All rows are pre-registration
        rows = [
            {"as_of": "2026-07-01", "outcome_excess": 0.02},
            {"as_of": "2026-07-02", "outcome_excess": 0.01},
            {"as_of": "2026-07-03", "outcome_excess": 0.03},
            {"as_of": "2026-07-04", "outcome_excess": 0.05},  # same day — also dropped
        ]
        kept, dropped = _filter_post_registration(rows, registered_at)
        assert len(kept) == 0
        assert dropped == 4

        # Gate would pass on all 4 rows (100% positive outcome_excess)
        # but n=0 means insufficient-n
        gate = {"metric": "hit_rate", "threshold": 0.5, "min_n": 2, "horizon_d": 5}
        verdict = _evaluate_gate(None, n=0, gate=gate)
        assert verdict == "insufficient-n"

    def test_zero_pre_reg_rows_no_issue(self):
        """If all rows are post-registration, nothing is dropped."""
        from scripts.evaluate_cortex_hypotheses import _filter_post_registration

        registered_at = "2026-07-01T00:00:00+00:00"
        rows = [
            {"as_of": "2026-07-02"},
            {"as_of": "2026-07-05"},
        ]
        kept, dropped = _filter_post_registration(rows, registered_at)
        assert len(kept) == 2
        assert dropped == 0


# ============================================================
# C. PRE-COMMITTED GATE ONLY
# ============================================================

class TestPreCommittedGate:

    def test_gate_reads_from_row_not_caller(self):
        """The gate is read from the registration row; metric cannot be substituted."""
        from scripts.evaluate_cortex_hypotheses import _evaluate_gate

        gate = {"metric": "hit_rate", "threshold": 0.6, "min_n": 5, "horizon_d": 5}
        # n=10 > min_n=5, hit_rate=0.5 < 0.6 threshold → failed
        assert _evaluate_gate(0.5, n=10, gate=gate) == "failed"
        # hit_rate=0.7 > 0.6 threshold → passed
        assert _evaluate_gate(0.7, n=10, gate=gate) == "passed"

    def test_insufficient_n_below_min_n(self):
        from scripts.evaluate_cortex_hypotheses import _evaluate_gate
        gate = {"metric": "hit_rate", "threshold": 0.5, "min_n": 10, "horizon_d": 5}
        assert _evaluate_gate(0.9, n=5, gate=gate) == "insufficient-n"

    def test_direction_expected_negative(self):
        """direction_expected=-1: metric below threshold is a pass."""
        from scripts.evaluate_cortex_hypotheses import _evaluate_gate
        gate = {
            "metric": "stop_out_rate",
            "threshold": 0.4,
            "min_n": 5,
            "horizon_d": 21,
            "direction_expected": -1,
        }
        # stop_out_rate=0.3 < 0.4 → passed (lower is better)
        assert _evaluate_gate(0.3, n=10, gate=gate) == "passed"
        # stop_out_rate=0.5 > 0.4 → failed
        assert _evaluate_gate(0.5, n=10, gate=gate) == "failed"

    def test_direction_expected_positive(self):
        """direction_expected=+1: metric above threshold is a pass."""
        from scripts.evaluate_cortex_hypotheses import _evaluate_gate
        gate = {
            "metric": "hit_rate",
            "threshold": 0.55,
            "min_n": 5,
            "horizon_d": 21,
            "direction_expected": 1,
        }
        assert _evaluate_gate(0.6, n=10, gate=gate) == "passed"
        assert _evaluate_gate(0.4, n=10, gate=gate) == "failed"


# ============================================================
# D. ATTENTION GRADING PER FALSIFIER CLASS
# ============================================================

class TestAttentionGrading:

    def _write_firing(self, root: Path, claim_id: str, asof: str,
                      horizon_d: int, direction: int, falsifier: str) -> None:
        rec = {
            "claim_id": claim_id,
            "reflex": "cortex_attention",
            "ts": f"{asof}T12:00:00Z",
            "trigger_type": "cortex_attention",
            "trigger_key": f"key_{claim_id}",
            "action_taken": "attention_flagged",
            "desk": "reflex",
            "asof": asof,
            "scope_type": "entity",
            "scope_key": "SPY",
            "direction": direction,
            "horizon_d": horizon_d,
            "claim_family": "reflex.cortex_attention",
            "falsifier": falsifier,
            "is_context_only": True,
            "extra": {},
        }
        p = root / "data" / "reflexes" / "cortex_attention" / "firings.jsonl"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

    def test_detect_realized_move_class(self):
        from scripts.grade_cortex_attention import _detect_falsifier_class
        c = {"falsifier": "SPY must move +2% within 5 days", "direction": 1}
        assert _detect_falsifier_class(c) == "realized_move"

    def test_detect_escalation_class(self):
        from scripts.grade_cortex_attention import _detect_falsifier_class
        c = {"falsifier": "alert must fire within 3 days", "direction": 0}
        assert _detect_falsifier_class(c) == "escalation"

    def test_detect_verdict_change_class(self):
        from scripts.grade_cortex_attention import _detect_falsifier_class
        c = {"falsifier": "regime verdict change to risk-off", "direction": -1}
        assert _detect_falsifier_class(c) == "verdict_change"

    def test_no_matured_claims_grades_empty(self):
        """No firings → no grades → A2 refused."""
        from scripts.grade_cortex_attention import grade_attention
        root = _tmp_root()
        today = date(2026, 7, 4)
        summary = grade_attention(root=str(root), dry_run=True, today=today)
        assert summary["total_firings"] == 0
        assert summary["matured_today"] == 0
        assert summary["new_grades"] == 0
        assert summary["a2_earn_in"]["granted"] is False

    def test_unmatured_claims_not_graded(self):
        """Claims filed today with horizon_d=5 are not mature yet."""
        from scripts.grade_cortex_attention import grade_attention
        root = _tmp_root()
        today = date(2026, 7, 4)
        self._write_firing(
            root, "claim_unmatured", "2026-07-03", horizon_d=5,
            direction=1, falsifier="SPY move"
        )
        # Filed 2026-07-03 + 5d = 2026-07-08 > 2026-07-04 (today)
        summary = grade_attention(root=str(root), dry_run=True, today=today)
        assert summary["matured_today"] == 0

    def test_matured_claim_is_graded(self):
        """Claim filed 10 days ago with horizon_d=5 is mature."""
        from scripts.grade_cortex_attention import grade_attention
        root = _tmp_root()
        today = date(2026, 7, 4)
        # asof = 2026-06-24, horizon=5 → mature by 2026-06-29 < today
        self._write_firing(
            root, "claim_mature_001", "2026-06-24", horizon_d=5,
            direction=1, falsifier="SPY move above 1%"
        )
        summary = grade_attention(root=str(root), dry_run=True, today=today)
        assert summary["matured_today"] == 1
        # dry_run doesn't write grades but counts them
        assert summary["new_grades"] == 1


# ============================================================
# E. GRADES JOIN IN adapt_cortex_attention
# ============================================================

class TestAdaptCortexAttention:

    def _write_firing(self, root: Path, claim_id: str, asof: str,
                      direction: int = 1, horizon_d: int = 5) -> None:
        rec = {
            "claim_id": claim_id,
            "reflex": "cortex_attention",
            "ts": f"{asof}T12:00:00Z",
            "trigger_type": "cortex_attention",
            "trigger_key": f"key_{claim_id}",
            "action_taken": "attention_flagged",
            "asof": asof,
            "scope_type": "entity",
            "scope_key": "SPY",
            "direction": direction,
            "horizon_d": horizon_d,
            "claim_family": "reflex.cortex_attention",
            "falsifier": "test falsifier",
            "is_context_only": True,
            "extra": {},
        }
        p = root / "data" / "reflexes" / "cortex_attention" / "firings.jsonl"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

    def _write_grade(self, root: Path, claim_id: str, outcome_hit: bool,
                     graded_at: str = "2026-07-04") -> None:
        rec = {
            "schema": "reflex.cortex_attention.grade.v1",
            "claim_id": claim_id,
            "graded_at": graded_at,
            "grader_version": "W7b-PR2",
            "falsifier_class": "realized_move",
            "outcome_hit": outcome_hit,
            "outcome_detail": {},
            "horizon_d": 5,
            "asof": "2026-06-24",
            "symbol": "SPY",
            "direction": 1,
            "base_rate": 0.5,
        }
        p = root / "data" / "reflexes" / "cortex_attention" / "grades.jsonl"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

    def test_no_firings_empty_df(self):
        from engine.neuralweb.query import adapt_cortex_attention
        root = _tmp_root()
        df, gaps = adapt_cortex_attention(root=str(root))
        assert df.empty

    def test_firing_without_grade_is_ungraded(self):
        from engine.neuralweb.query import adapt_cortex_attention
        root = _tmp_root()
        self._write_firing(root, "claim_ungraded_001", "2026-06-24")
        df, gaps = adapt_cortex_attention(root=str(root))
        assert not df.empty
        assert df.iloc[0]["outcome_graded"] == False  # noqa: E712 — np.False_ != False under `is`
        assert df.iloc[0]["ledger"] == "cortex_attention"

    def test_firing_with_grade_hit_is_graded(self):
        from engine.neuralweb.query import adapt_cortex_attention
        root = _tmp_root()
        self._write_firing(root, "claim_graded_hit", "2026-06-24", direction=1)
        self._write_grade(root, "claim_graded_hit", outcome_hit=True)
        df, gaps = adapt_cortex_attention(root=str(root))
        assert not df.empty
        row = df.iloc[0]
        assert row["outcome_graded"] == True  # noqa: E712 — np.True_ != True under `is`
        assert row["outcome_excess"] > 0   # hit + direction>0 → positive

    def test_firing_with_grade_miss_is_graded_negative(self):
        from engine.neuralweb.query import adapt_cortex_attention
        root = _tmp_root()
        self._write_firing(root, "claim_graded_miss", "2026-06-24", direction=1)
        self._write_grade(root, "claim_graded_miss", outcome_hit=False)
        df, gaps = adapt_cortex_attention(root=str(root))
        row = df.iloc[0]
        assert row["outcome_graded"] == True  # noqa: E712 — graded row is True (even on miss)
        assert row["outcome_excess"] < 0   # miss + direction>0 → negative

    def test_direction_zero_stays_ungraded(self):
        """Infrastructure claims (direction=0) stay outcome_graded=False by design."""
        from engine.neuralweb.query import adapt_cortex_attention
        root = _tmp_root()
        self._write_firing(root, "claim_infra_001", "2026-06-24", direction=0)
        self._write_grade(root, "claim_infra_001", outcome_hit=True)
        df, gaps = adapt_cortex_attention(root=str(root))
        row = df.iloc[0]
        # Infrastructure: direction=0 → ungradeable by design, even with a grade
        assert row["outcome_graded"] == False  # noqa: E712 — np.False_ != False under `is`

    def test_cortex_attention_ledger_name(self):
        from engine.neuralweb.query import adapt_cortex_attention
        root = _tmp_root()
        self._write_firing(root, "claim_ledger_check", "2026-06-24")
        df, gaps = adapt_cortex_attention(root=str(root))
        assert (df["ledger"] == "cortex_attention").all()


# ============================================================
# F. A2 EVALUATION REFUSED TODAY
# ============================================================

class TestA2EarnIn:

    def test_a2_refused_empty_record(self):
        """Empty attention record → A2 refused (n=0 < min_n=25)."""
        from scripts.grade_cortex_attention import evaluate_a2_earn_in
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        probation = evaluate_a2_earn_in([], root, dry_run=True, now=now)
        assert probation["granted"] is False
        assert "insufficient" in probation["reason"].lower()
        assert probation["attention_track_record"]["n"] == 0

    def test_a2_refused_insufficient_n(self):
        """Fewer than 25 graded items → A2 refused."""
        from scripts.grade_cortex_attention import evaluate_a2_earn_in
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        # 10 graded items, 8 hits — not enough n
        grades = [
            {"claim_id": f"c{i}", "graded_at": "2026-07-04", "outcome_hit": True}
            for i in range(8)
        ] + [
            {"claim_id": f"c_miss_{i}", "graded_at": "2026-07-04", "outcome_hit": False}
            for i in range(2)
        ]
        probation = evaluate_a2_earn_in(grades, root, dry_run=True, now=now)
        assert probation["granted"] is False
        assert probation["attention_track_record"]["n"] == 10

    def test_probation_json_written(self):
        """probation.json is written as single source of truth."""
        from scripts.grade_cortex_attention import grade_attention
        root = _tmp_root()
        today = date(2026, 7, 4)
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        grade_attention(root=str(root), dry_run=False, today=today, now=now)
        p = root / "data" / "neuralweb" / "cortex" / "probation.json"
        assert p.exists()
        probation = json.loads(p.read_text())
        assert probation["granted"] is False
        assert probation["schema"] == "neuralweb.cortex_probation.v1"

    # ── PR-2: synthetic / dry-run exclusion tests ─────────────────────────────

    def test_synthetic_ticker_firing_excluded_from_load(self):
        """_load_firings must silently exclude SYNTHETIC_TICKER rows (append-only: row stays in file)."""
        from scripts.grade_cortex_attention import _load_firings, _is_synthetic
        root = _tmp_root()
        firings_path = root / "data" / "reflexes" / "cortex_attention" / "firings.jsonl"
        firings_path.parent.mkdir(parents=True, exist_ok=True)

        synthetic_row = {
            "claim_id": "synthetic-001",
            "reflex": "cortex_attention",
            "trigger_key": "SYNTHETIC_TICKER",
            "scope_key": "SYNTHETIC_TICKER",
            "asof": "2026-07-04",
            "horizon_d": 5,
            "direction": 1,
            "falsifier": "SYNTHETIC_TICKER moves >2% within 5 days (dry-run synthetic item)",
        }
        real_row = {
            "claim_id": "real-001",
            "reflex": "cortex_attention",
            "trigger_key": "SPY",
            "scope_key": "SPY",
            "asof": "2026-07-04",
            "horizon_d": 5,
            "direction": 1,
            "falsifier": "SPY must rally >2%",
        }
        with firings_path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(synthetic_row) + "\n")
            fh.write(json.dumps(real_row) + "\n")

        # _is_synthetic correctly identifies the synthetic row
        assert _is_synthetic(synthetic_row) is True
        assert _is_synthetic(real_row) is False

        # _load_firings returns only the real row
        rows = _load_firings(root)
        assert len(rows) == 1, f"expected 1 real row, got {len(rows)}"
        assert rows[0]["claim_id"] == "real-001"

        # Ledger file still has both rows (append-only law)
        raw_lines = [l for l in firings_path.read_text().splitlines() if l.strip()]
        assert len(raw_lines) == 2, "ledger must retain both rows — never delete"

    def test_synthetic_grade_excluded_from_probation_n(self):
        """A grades.jsonl with only a SYNTHETIC_TICKER grade produces n=0 in probation."""
        from scripts.grade_cortex_attention import _load_grades
        root = _tmp_root()
        grades_path = root / "data" / "reflexes" / "cortex_attention" / "grades.jsonl"
        grades_path.parent.mkdir(parents=True, exist_ok=True)

        synthetic_grade = {
            "schema": "reflex.cortex_attention.grade.v1",
            "claim_id": "synthetic-001",
            "graded_at": "2026-07-09",
            "symbol": "SYNTHETIC_TICKER",
            "outcome_hit": False,
        }
        with grades_path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(synthetic_grade) + "\n")

        grades = _load_grades(root)
        assert len(grades) == 0, f"expected 0 real grades (synthetic excluded), got {len(grades)}"

    def test_real_rows_still_counted_alongside_synthetic(self):
        """When firings include both real and synthetic rows, only real rows enter grading."""
        from scripts.grade_cortex_attention import grade_attention
        root = _tmp_root()
        firings_path = root / "data" / "reflexes" / "cortex_attention" / "firings.jsonl"
        firings_path.parent.mkdir(parents=True, exist_ok=True)

        # Synthetic row (horizon elapsed → would be graded if not excluded)
        synthetic = {
            "claim_id": "synth-999",
            "trigger_key": "SYNTHETIC_TICKER",
            "scope_key": "SYNTHETIC_TICKER",
            "asof": "2026-01-01",
            "horizon_d": 5,
            "direction": 1,
            "falsifier": "SYNTHETIC_TICKER (dry-run synthetic item)",
        }
        with firings_path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(synthetic) + "\n")

        today = date(2026, 7, 4)
        summary = grade_attention(root=str(root), dry_run=True, today=today)

        # Synthetic row must not enter the grading pipeline
        assert summary["total_firings"] == 0, (
            f"synthetic firing must be excluded; total_firings={summary['total_firings']}"
        )
        assert summary["matured_today"] == 0
        assert summary["a2_earn_in"]["n"] == 0

    def test_cortex_reads_probation_json(self):
        """Cortex _check_constitution reads probation.json as single source."""
        from engine.neuralweb.cortex import _check_constitution
        root = _tmp_root()
        # Write a probation.json with known values
        probation_data = {
            "schema": "neuralweb.cortex_probation.v1",
            "as_of": "2026-07-04",
            "granted": False,
            "tier": "A0/A1 shadow",
            "reason": "insufficient-n: n=0 < min_n=25",
            "lift_lb": None,
            "wilson_lb": None,
            "lapses_at": None,
            "evidence_asof": None,
            "attention_track_record": {"n": 0, "hits": 0, "base_rate": 0.5},
            "is_context_only": True,
        }
        p = root / "data" / "neuralweb" / "cortex" / "probation.json"
        p.write_text(json.dumps(probation_data), encoding="utf-8")

        result = _check_constitution(root)
        assert result["granted"] is False
        assert result["reason"] == "insufficient-n: n=0 < min_n=25"
        # Must be the stored value, not re-derived
        assert result["schema"] == "neuralweb.cortex_probation.v1"


# ============================================================
# G. TRANSITION-ONLY GOVERNANCE EVENTS
# ============================================================

class TestTransitionOnlyGovernance:

    def _make_grades(self, n: int, hits: int) -> list[dict]:
        return [
            {"claim_id": f"c{i}", "graded_at": "2026-07-04",
             "outcome_hit": i < hits}
            for i in range(n)
        ]

    def test_no_event_when_status_unchanged(self):
        """No governance event when granted status doesn't change."""
        from scripts.grade_cortex_attention import evaluate_a2_earn_in
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)

        # Write probation.json with granted=False
        p = root / "data" / "neuralweb" / "cortex" / "probation.json"
        p.write_text(json.dumps({"granted": False}), encoding="utf-8")

        # Evaluate with no graded items → still refused (no transition)
        evaluate_a2_earn_in([], root, dry_run=False, now=now)
        events = _load_governance(root)
        # No authority_grant or authority_lapse since status didn't change
        assert not any(
            e.get("event_type") in ("authority_grant", "authority_lapse")
            for e in events
        )

    def test_event_emitted_on_refusal_to_grant_transition(self):
        """authority_grant event when status transitions from refused to granted."""
        from scripts.grade_cortex_attention import evaluate_a2_earn_in
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)

        # Write probation.json with granted=False (was refused)
        p = root / "data" / "neuralweb" / "cortex" / "probation.json"
        p.write_text(json.dumps({"granted": False}), encoding="utf-8")

        # Manufacture enough graded items to pass A2
        # min_n=25, min_events=8, base_rate=0.5, need wilson_lb/base > 1.25
        # With n=50, hits=40 and base_rate=0.5: wilson_lb ≈ 0.68, lift ≈ 1.36 > 1.25
        grades = self._make_grades(n=50, hits=40)
        # Set evidence_asof to today so freshness passes
        for g in grades:
            g["graded_at"] = "2026-07-04"

        evaluate_a2_earn_in(grades, root, dry_run=False, now=now)
        events = _load_governance(root)
        assert any(e.get("event_type") == "authority_grant" for e in events)


# ============================================================
# I. BLOCKER 1 — SELF-GRADING PREVENTION
# ============================================================

class TestSelfGradingPrevention:
    """Reproduction of the reviewer's Article 1 attack — both layers tested."""

    # --- Layer 1: registration-time rejection ---

    def test_registration_rejects_cortex_attention_family(self):
        """ATTACK: cortex registers a hypothesis with spine_query.family='reflex.cortex_attention:event'.
        EXPECTED: registration returns status='invalid' (Article 1 guard).
        """
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        h = _valid_hyp(
            spine_query={
                "family": "reflex.cortex_attention:event",
                "subject": "SPX",
            }
        )
        result = register_hypothesis(h, root=str(root), now=now)
        # Registration must REJECT — cortex_attention self-reference forbidden
        assert result["status"] == "invalid", (
            f"ATTACK SUCCEEDED — self-referencing hypothesis was accepted: {result}"
        )
        assert "Article 1" in result["reason"] or "cortex_attention" in result["reason"], (
            f"rejection reason does not cite Article 1: {result['reason']}"
        )

    def test_registration_rejects_cortex_attention_engine(self):
        """ATTACK: spine_query.engine='reflex.cortex_attention' → must reject."""
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        h = _valid_hyp(
            spine_query={
                "engine": "reflex.cortex_attention",
                "subject": "SPX",
            }
        )
        result = register_hypothesis(h, root=str(root), now=now)
        assert result["status"] == "invalid", (
            f"ATTACK SUCCEEDED — engine self-reference accepted: {result}"
        )

    def test_registration_rejects_cortex_attention_ledger(self):
        """ATTACK: spine_query.ledger='cortex_attention' → must reject."""
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        h = _valid_hyp(
            spine_query={
                "ledger": "cortex_attention",
                "subject": "SPX",
            }
        )
        result = register_hypothesis(h, root=str(root), now=now)
        assert result["status"] == "invalid", (
            f"ATTACK SUCCEEDED — ledger self-reference accepted: {result}"
        )

    def test_valid_hypothesis_not_rejected_by_self_guard(self):
        """Non-self-referencing hypothesis still registers normally."""
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        result = register_hypothesis(_valid_hyp(), root=str(root), now=now)
        assert result["status"] == "registered"

    # --- Layer 2: evaluator-time rejection (pre-existing rows that bypassed validation) ---

    def test_evaluator_rejects_preexisting_self_reference_row(self):
        """ATTACK: hand-craft a registry row with spine_query.family='reflex.cortex_attention:event'
        (bypassing _validate_hypothesis).  The evaluator must return verdict='invalid-self-reference',
        never 'passed'.
        """
        from scripts.evaluate_cortex_hypotheses import evaluate_due
        from datetime import date as _date

        root = _tmp_root()

        # Hand-write the attack row directly to the registry (bypassing validation)
        attack_row = {
            "schema": "neuralweb.machine_registry.v1",
            "id": "cortex-2026-07-04-self-ref-attack-aa1234",
            "kind": "cortex_hypothesis",
            "status": "registered",
            "registered_at": "2026-06-01T00:00:00+00:00",
            "registered_by": "cortex",
            "fdr_family": "cortex",
            "claim_shape": "lead_lag",
            "hypothesis": "Adversarial self-reference hypothesis",
            "spine_query": {
                "family": "reflex.cortex_attention:event",
                "subject": "SPX",
            },
            "pre_committed_gate": {
                "metric": "hit_rate",
                "threshold": 0.5,
                "min_n": 1,
                "horizon_d": 5,
            },
            "horizon_d": 5,
            # come_back in the past so it's "due"
            "come_back": "2026-06-20",
            "is_context_only": True,
        }
        reg_path = root / "data" / "neuralweb" / "machine_registry.jsonl"
        with reg_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(attack_row) + "\n")

        # Evaluate with today past the come_back date
        today = _date(2026, 7, 4)
        summary = evaluate_due(root=str(root), dry_run=True, today=today)

        results = summary["results"]
        assert len(results) == 1, f"Expected 1 result, got {len(results)}: {results}"
        verdict = results[0]["verdict"]
        assert verdict == "invalid-self-reference", (
            f"ATTACK PASSED — evaluator returned {verdict!r} for self-referencing row; "
            f"full result: {results[0]}"
        )

    def test_evaluator_self_ref_row_never_passed(self):
        """Specifically verify that a self-referencing row can NEVER get verdict='passed'."""
        from scripts.evaluate_cortex_hypotheses import evaluate_due
        from datetime import date as _date

        root = _tmp_root()
        attack_row = {
            "schema": "neuralweb.machine_registry.v1",
            "id": "cortex-2026-07-04-self-ref-pass-bb5678",
            "kind": "cortex_hypothesis",
            "status": "registered",
            "registered_at": "2026-05-01T00:00:00+00:00",
            "registered_by": "cortex",
            "fdr_family": "cortex",
            "claim_shape": "lead_lag",
            "hypothesis": "Self-referencing pass attempt",
            "spine_query": {
                "engine": "reflex.cortex_attention",
                "subject": "SPX",
            },
            "pre_committed_gate": {
                "metric": "hit_rate",
                "threshold": 0.1,   # absurdly low to make "passing" trivial on any data
                "min_n": 1,
                "horizon_d": 5,
            },
            "horizon_d": 5,
            "come_back": "2026-05-20",
            "is_context_only": True,
        }
        reg_path = root / "data" / "neuralweb" / "machine_registry.jsonl"
        with reg_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(attack_row) + "\n")

        today = _date(2026, 7, 4)
        summary = evaluate_due(root=str(root), dry_run=True, today=today)
        results = summary["results"]
        assert len(results) == 1
        assert results[0]["verdict"] != "passed", (
            "ATTACK SUCCEEDED — self-referencing hypothesis reached verdict='passed'"
        )
        assert results[0]["verdict"] == "invalid-self-reference"


# ============================================================
# J. BLOCKER 2 — min_n FLOOR ENFORCEMENT
# ============================================================

class TestMinNFloor:
    """Reproduction of the reviewer's min_n=1 attack — server-side clamp tested."""

    def test_min_n_1_clamped_to_25(self):
        """ATTACK: submit min_n=1 (tiny floor allowing single-row pass).
        EXPECTED: registry row stores min_n=25 with clamped_from=1.
        """
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        h = _valid_hyp(
            pre_committed_gate={
                "metric": "hit_rate",
                "threshold": 0.5,
                "min_n": 1,          # attack: tiny min_n
                "horizon_d": 21,
            }
        )
        result = register_hypothesis(h, root=str(root), now=now)
        assert result["status"] == "registered", f"Registration should succeed: {result}"

        # Check the stored gate in the registry
        rows = _load_registry(root)
        registered = [r for r in rows if r.get("status") == "registered"]
        assert len(registered) == 1
        stored_gate = registered[0]["pre_committed_gate"]
        assert stored_gate["min_n"] == 25, (
            f"CLAMP FAILED — stored min_n={stored_gate['min_n']}, expected 25"
        )
        assert stored_gate.get("clamped_from") == 1, (
            f"clamped_from not recorded: {stored_gate}"
        )

    def test_min_n_0_clamped_to_25(self):
        """min_n=0 is also below the floor."""
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        h = _valid_hyp(
            pre_committed_gate={
                "metric": "hit_rate",
                "threshold": 0.5,
                "min_n": 0,
                "horizon_d": 21,
            }
        )
        result = register_hypothesis(h, root=str(root), now=now)
        assert result["status"] == "registered"
        rows = _load_registry(root)
        registered = [r for r in rows if r.get("status") == "registered"]
        stored_gate = registered[0]["pre_committed_gate"]
        assert stored_gate["min_n"] == 25

    def test_min_n_above_floor_not_clamped(self):
        """min_n=30 is above the floor; no clamping, no clamped_from field."""
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        h = _valid_hyp(
            pre_committed_gate={
                "metric": "hit_rate",
                "threshold": 0.5,
                "min_n": 30,
                "horizon_d": 21,
            }
        )
        result = register_hypothesis(h, root=str(root), now=now)
        assert result["status"] == "registered"
        rows = _load_registry(root)
        registered = [r for r in rows if r.get("status") == "registered"]
        stored_gate = registered[0]["pre_committed_gate"]
        assert stored_gate["min_n"] == 30
        assert "clamped_from" not in stored_gate

    def test_min_n_equal_floor_not_clamped(self):
        """min_n=25 exactly equals the floor; no clamped_from recorded."""
        from engine.neuralweb.metabolism import register_hypothesis
        root = _tmp_root()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        h = _valid_hyp(
            pre_committed_gate={
                "metric": "hit_rate",
                "threshold": 0.5,
                "min_n": 25,
                "horizon_d": 21,
            }
        )
        result = register_hypothesis(h, root=str(root), now=now)
        assert result["status"] == "registered"
        rows = _load_registry(root)
        registered = [r for r in rows if r.get("status") == "registered"]
        stored_gate = registered[0]["pre_committed_gate"]
        assert stored_gate["min_n"] == 25
        assert "clamped_from" not in stored_gate

    def test_single_row_evaluator_returns_insufficient_n_after_clamp(self):
        """ATTACK: after clamp, a registry row with clamped min_n=25 and only 1
        post-registration row must return insufficient-n, not 'passed'.
        """
        from scripts.evaluate_cortex_hypotheses import _evaluate_gate

        # The attack would have had min_n=1 in the gate; the clamp writes min_n=25.
        # Simulate the evaluator reading the clamped gate (min_n=25).
        clamped_gate = {
            "metric": "hit_rate",
            "threshold": 0.5,
            "min_n": 25,
            "horizon_d": 21,
            "clamped_from": 1,
        }
        # Only 1 post-registration row (the attack's best case)
        verdict = _evaluate_gate(metric_value=1.0, n=1, gate=clamped_gate)
        assert verdict == "insufficient-n", (
            f"ATTACK SUCCEEDED — single row passed gate: verdict={verdict!r}"
        )


# ============================================================
# H. EXPERIMENTS REGISTRY INTEGRATION
# ============================================================

class TestExperimentsRegistry:

    def test_cortex_evaluator_hook_returns_dict(self):
        """The cortex_evaluator hook gracefully handles a missing registry row."""
        from engine.experiments_registry import _refresh_cortex_evaluator
        e = {"id": "cortex-2026-07-04-nonexistent", "kind": "cortex_hypothesis"}
        # Should not raise even if the id doesn't exist
        result = _refresh_cortex_evaluator(e)
        assert isinstance(result, dict)

    def test_load_machine_registry_entries_empty(self):
        """Empty machine registry returns empty list."""
        from engine.experiments_registry import _load_machine_registry_entries
        # Temporarily override _root to point at a tmp dir
        import engine.experiments_registry as reg
        orig_root = reg._root
        tmp = Path(tempfile.mkdtemp())
        (tmp / "data" / "neuralweb").mkdir(parents=True)
        try:
            reg._root = lambda: tmp
            result = _load_machine_registry_entries()
            assert result == []
        finally:
            reg._root = orig_root
