"""Replay-budget accounting consistency — registry (SUM basis) vs trial ledger.

Guards the 2026-07-06 reconciliation (data/rule_experiments/RECONCILIATION_2026-07-06.md):

1. register_experiment is idempotent on byte-identical content — a duplicate
   'registered' row is never appended and never burns a ledger row; a content
   AMENDMENT (e.g. disp_gate_1 adding base_cohort_predicates) still appends.
2. replay_ledger_budgets derives per-exp_id budgets from the ledger with max()
   collapse, so run-churn duplicates (wait_grid_v1) cannot make the pooled SUM
   ambiguous.
3. reconcile_replay_accounting flags the exit_grid_v1 failure class — an
   experiment registered in the registry with no surviving ledger row.
4. The REAL repo files agree: ledger-derived SUM == registry SUM, per-exp
   budgets match, and the ledger max()-basis DSR floor equals the largest
   registered budget (15 per NW_FINAL3_LOBES §7).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.rule_experiments import (
    load_experiment,
    pooled_replay_trial_count,
    reconcile_replay_accounting,
    register_experiment,
    registration_content_hash,
    replay_ledger_budgets,
)
from engine.trial_ledger import TrialLedger

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_REGISTRY = REPO_ROOT / "data" / "rule_experiments" / "registry.jsonl"
REAL_LEDGER = REPO_ROOT / "data" / "trial_ledger.jsonl"

# Frozen historical budgets per NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN §7.
# These are facts about already-run experiments; they change only via an
# explicit amendment registration, which a reviewer should see in this file.
CANONICAL_BUDGETS = {
    "exit_grid_v1": 15,
    "wait_grid_v1": 10,
    "disp_gate_1": 6,
    "trim_grid_v1": 6,
}


def _register(registry_path, ledger_path, exp_id="dedup-test", **overrides):
    kwargs = dict(
        exp_id=exp_id,
        question="Does the guard hold? (grid=2)",
        spec_hashes=["a" * 64, "b" * 64],
        declared_budget=2,
        verdict_criteria="descriptive-only",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )
    kwargs.update(overrides)
    return register_experiment(**kwargs)


def _lines(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


class TestRegistrationDedupGuard:
    def test_identical_reregistration_is_noop(self, tmp_path):
        registry = tmp_path / "registry.jsonl"
        ledger = tmp_path / "trial_ledger.jsonl"
        first = _register(registry, ledger)
        second = _register(registry, ledger)

        registered_rows = [r for r in _lines(registry) if "declared_budget" in r]
        assert len(registered_rows) == 1, "identical re-registration appended a duplicate row"
        ledger_rows = [r for r in _lines(ledger) if r.get("kind") == "declared_budget"]
        assert len(ledger_rows) == 1, "identical re-registration burned a second ledger row"
        # The no-op path returns the merged existing entry
        assert second["exp_id"] == first["exp_id"]
        assert second["declared_budget"] == 2

    def test_amended_reregistration_appends(self, tmp_path):
        registry = tmp_path / "registry.jsonl"
        ledger = tmp_path / "trial_ledger.jsonl"
        _register(registry, ledger)
        # disp_gate_1 pattern: same grid, amended with base_cohort_predicates
        _register(
            registry, ledger,
            base_cohort_predicates=[["eq", "verdict_grade", True]],
        )

        registered_rows = [r for r in _lines(registry) if "declared_budget" in r]
        assert len(registered_rows) == 2, "content amendment must still append"
        merged = load_experiment("dedup-test", registry)
        assert merged["base_cohort_predicates"] == [["eq", "verdict_grade", True]]
        # SUM basis dedups by exp_id, so the amendment does not double-count
        assert pooled_replay_trial_count(registry) == 2

    def test_content_hash_treats_absent_fields_as_defaults(self):
        old_style = {
            "exp_id": "x",
            "question": "q",
            "spec_hashes": ["b" * 64, "a" * 64],
            "n_floor": 300,
            "declared_budget": 2,
            "verdict_criteria": "descriptive-only",
            "derived_from_surface": None,
        }
        new_style = dict(
            old_style,
            spec_hashes=["a" * 64, "b" * 64],
            needed_merge_columns=[],
            base_cohort_predicates=[],
            status="registered",
            registered_at="2026-07-06T00:00:00+00:00",
        )
        assert registration_content_hash(old_style) == registration_content_hash(new_style)


class TestLedgerDerivation:
    def test_duplicate_ledger_rows_collapse_via_max(self, tmp_path):
        ledger = tmp_path / "trial_ledger.jsonl"
        led = TrialLedger(ledger, family="replay")
        # wait_grid_v1 pattern: same exp, same n, reworded question truncation
        led.log_declared_budget(10, reason="exp_id=wait_x; question='what does waiting cost or save — how do entry ou'")
        led.log_declared_budget(10, reason="exp_id=wait_x; question='what does waiting cost or save'")
        led.log_declared_budget(6, reason="exp_id=other_y; question='q'")
        # non-replay families are out of scope
        led.log_declared_budget(99, family="vector", reason="not a replay row")

        budgets, unattributed = replay_ledger_budgets(ledger)
        assert budgets == {"wait_x": 10, "other_y": 6}
        assert unattributed == []

    def test_unstamped_replay_row_is_flagged(self, tmp_path):
        ledger = tmp_path / "trial_ledger.jsonl"
        led = TrialLedger(ledger, family="replay")
        led.log_declared_budget(4, reason="no exp stamp here")
        budgets, unattributed = replay_ledger_budgets(ledger)
        assert budgets == {}
        assert unattributed == ["no exp stamp here"]

    def test_missing_ledger_row_breaks_consistency(self, tmp_path):
        # exit_grid_v1 failure class: registered in registry, ledger row lost
        registry = tmp_path / "registry.jsonl"
        ledger = tmp_path / "trial_ledger.jsonl"
        _register(registry, ledger, exp_id="kept")
        _register(registry, ledger, exp_id="lost", spec_hashes=["c" * 64], declared_budget=1)
        kept_rows = [
            json.dumps(r) for r in _lines(ledger)
            if "exp_id=lost;" not in (r.get("reason") or "")
        ]
        ledger.write_text("\n".join(kept_rows) + "\n")

        rec = reconcile_replay_accounting(registry, ledger)
        assert not rec["consistent"]
        assert rec["mismatches"] == {"lost": {"registry": 1, "ledger": None}}


@pytest.mark.skipif(
    not (REAL_REGISTRY.exists() and REAL_LEDGER.exists()),
    reason="repo data files not present in this checkout",
)
class TestRealFilesConsistent:
    def test_registry_and_ledger_agree(self):
        rec = reconcile_replay_accounting(REAL_REGISTRY, REAL_LEDGER)
        assert rec["unattributed_ledger_rows"] == [], (
            "replay ledger rows without an exp_id= stamp make the pooled SUM ambiguous"
        )
        assert rec["mismatches"] == {}, (
            f"registry/ledger budget drift: {rec['mismatches']} — every registration "
            "must leave exactly one attributable ledger budget; see "
            "data/rule_experiments/RECONCILIATION_2026-07-06.md for the repair pattern"
        )
        assert rec["consistent"]
        assert rec["ledger_sum"] == rec["registry_sum"]
        assert rec["registry_sum"] == pooled_replay_trial_count(REAL_REGISTRY)

    def test_canonical_budgets_per_final3_section7(self):
        rec = reconcile_replay_accounting(REAL_REGISTRY, REAL_LEDGER)
        for exp_id, budget in CANONICAL_BUDGETS.items():
            assert rec["registry_budgets"].get(exp_id) == budget, (
                f"{exp_id}: registry budget {rec['registry_budgets'].get(exp_id)} "
                f"!= §7 canonical {budget}"
            )
        assert rec["registry_sum"] >= sum(CANONICAL_BUDGETS.values())

    def test_dsr_floor_is_largest_registered_budget(self):
        rec = reconcile_replay_accounting(REAL_REGISTRY, REAL_LEDGER)
        assert rec["ledger_max_floor"] == max(rec["registry_budgets"].values())
        led = TrialLedger(REAL_LEDGER)
        assert led.declared_budget("replay") == rec["ledger_max_floor"]
        assert led.declared_budget("replay") >= 15, (
            "exit_grid_v1's 15-cell grid is the current largest budget; a floor "
            "below 15 means its ledger row went missing again"
        )
