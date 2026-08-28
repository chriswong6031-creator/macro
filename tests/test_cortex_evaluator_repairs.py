"""Pins the five cortex-evaluator wiring repairs from the 2026-08-26 experiments audit.

Each test names the defect it prevents and, where the audit measured one, the
receipt.  research/EXPERIMENTS_AUDIT_2026_08_26.md §3 (W1-W6).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from engine.neuralweb import metabolism as M
from scripts import evaluate_cortex_hypotheses as E
from scripts import quarterly_cortex_fdr as F


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _registry_row(**over):
    row = {
        "schema": "neuralweb.machine_registry.v1",
        "id": "cortex-2026-08-26-test-hypothesis",
        "kind": "cortex_hypothesis",
        "status": "registered",
        "registered_at": "2026-08-01T00:00:00+00:00",
        "registered_by": "cortex",
        "fdr_family": "cortex",
        "claim_shape": "conditional_regime",
        "hypothesis": "test",
        "spine_query": {"subject": "SPY"},
        "pre_committed_gate": {
            "metric": "hit_rate", "threshold": 0.55, "min_n": 25,
            "horizon_d": 21, "direction_expected": 1,
        },
        "horizon_d": 21,
        "come_back": "2026-08-29",
    }
    row.update(over)
    return row


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    return tmp_path


def _write_registry(root: Path, rows: list[dict]) -> None:
    p = root / "data" / "neuralweb" / "machine_registry.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _rows(root: Path) -> list[dict]:
    p = root / "data" / "neuralweb" / "machine_registry.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# W3 — gate semantics
# ---------------------------------------------------------------------------

class TestW3GateSemantics:
    def test_h2_negative_hit_rate_threshold_is_invalid_gate_not_failed(self):
        """H2: `hit_rate <= -0.05`.  A hit rate is never negative.

        This reported 'failed' on 2026-08-04 (metric_value 0.5771), which reads
        as evidence against the hypothesis.  It is evidence against the gate.
        """
        verdict, detail = E._validate_gate({
            "metric": "hit_rate", "threshold": -0.05,
            "min_n": 25, "direction_expected": -1,
        })
        assert verdict == "invalid-gate"
        assert "structurally unpassable" in detail["gate_error"]

    def test_h3_above_one_hit_rate_threshold_is_invalid_gate(self):
        """H3: `hit_rate >= 1.01`.  A hit rate never exceeds 1."""
        verdict, detail = E._validate_gate({
            "metric": "hit_rate", "threshold": 1.01,
            "min_n": 25, "direction_expected": 1,
        })
        assert verdict == "invalid-gate"
        assert detail["attainable_range"] == [0.0, 1.0]

    def test_unknown_metric_is_never_silently_graded_as_hit_rate(self):
        """The defect behind every 2026-08 registration.

        `median_credit_sensitive_lead_days` and six siblings are not computed
        anywhere; the old code fell through to `hits / n` and emitted a verdict
        about a metric nobody measured.
        """
        verdict, detail = E._validate_gate({
            "metric": "median_credit_sensitive_lead_days", "threshold": 3,
            "min_n": 25, "direction_expected": 1,
        })
        assert verdict == "uncomputable-metric"
        assert "hit_rate" in detail["supported_metrics"]

    def test_gate_every_sample_passes_is_invalid(self):
        verdict, _ = E._validate_gate({
            "metric": "hit_rate", "threshold": 0.0,
            "min_n": 25, "direction_expected": 1,
        })
        assert verdict == "invalid-gate"

    def test_a_well_formed_gate_validates(self):
        verdict, detail = E._validate_gate({
            "metric": "hit_rate_difference", "threshold": 0.05,
            "min_n": 25, "direction_expected": 1,
        })
        assert verdict is None
        assert detail["metric_space"] == "contrast"

    def test_evaluator_metric_table_matches_the_registration_contract(self):
        """The enum must not drift between where it is enforced and where it is computed."""
        assert set(E._METRIC_SPEC) == set(M.SUPPORTED_GATE_METRICS)
        for metric, spec in E._METRIC_SPEC.items():
            assert (spec["lo"], spec["hi"]) == M.METRIC_BOUNDS[metric]

    def test_registration_rejects_an_ungradeable_metric(self):
        errors = M._validate_hypothesis({
            "hypothesis": "x", "claim_shape": "lead_lag", "horizon_d": 21,
            "spine_query": {"subject": "SPY"},
            "pre_committed_gate": {
                "metric": "q2_persistence_rate_difference", "threshold": -0.1,
                "min_n": 30, "horizon_d": 21,
            },
        })
        assert any("not gradeable" in e for e in errors)

    def test_registration_rejects_a_structurally_unpassable_threshold(self):
        errors = M._validate_hypothesis({
            "hypothesis": "x", "claim_shape": "conditional_regime", "horizon_d": 21,
            "spine_query": {"subject": "SPY"},
            "pre_committed_gate": {
                "metric": "hit_rate", "threshold": -0.05,
                "min_n": 25, "horizon_d": 21,
            },
        })
        assert any("structurally unpassable" in e for e in errors)


# ---------------------------------------------------------------------------
# W2 — feature conditions and the contrast group
# ---------------------------------------------------------------------------

class TestW2FeatureConditions:
    def test_unresolvable_feature_refuses_to_grade(self, root: Path):
        """The audit's headline: H2 and H3 returned byte-identical results.

        With no panel available the feature cannot be applied, and grading the
        unfiltered population would score a different hypothesis than the one
        registered.
        """
        mask, detail = E._resolve_feature_mask(
            {"feature": "high_alibi_flag"},
            [{"symbol": "AAPL", "as_of": "2026-08-10"}],
            root,
        )
        assert mask is None
        assert "factor panel unavailable" in detail["feature_error"]

    def test_feature_absent_from_the_panel_is_named_not_guessed(self, root: Path):
        panel_dir = root / "data" / "factordata" / "panel" / "2026-08"
        panel_dir.mkdir(parents=True)
        pd.DataFrame({
            "ticker": ["AAPL"], "date": ["2026-08-10"], "twin_bleed_flag": [True],
        }).to_parquet(panel_dir / "panel.parquet")

        mask, detail = E._resolve_feature_mask(
            {"feature": "decay_flag"},
            [{"symbol": "AAPL", "as_of": "2026-08-10"}],
            root,
        )
        assert mask is None
        assert "not a factor-panel column" in detail["feature_error"]
        assert "feature_expr" in detail["remediation"]

    def test_a_resolvable_feature_splits_treatment_from_control(self, root: Path):
        panel_dir = root / "data" / "factordata" / "panel" / "2026-08"
        panel_dir.mkdir(parents=True)
        pd.DataFrame({
            "ticker": ["AAPL", "MSFT", "NVDA"],
            "date": ["2026-08-10"] * 3,
            "twin_bleed_flag": [True, False, True],
        }).to_parquet(panel_dir / "panel.parquet")

        rows = [
            {"symbol": "AAPL", "as_of": "2026-08-10"},
            {"symbol": "MSFT", "as_of": "2026-08-10"},
            {"symbol": "NVDA", "as_of": "2026-08-10"},
        ]
        mask, detail = E._resolve_feature_mask({"feature": "twin_bleed_flag"}, rows, root)
        assert mask == [True, False, True]
        assert detail["treatment_n"] == 2
        assert detail["control_n"] == 1

    def test_two_different_features_cannot_produce_identical_groups(self, root: Path):
        """Directly pins the H2/H3 receipt: different features, different samples."""
        panel_dir = root / "data" / "factordata" / "panel" / "2026-08"
        panel_dir.mkdir(parents=True)
        pd.DataFrame({
            "ticker": ["AAPL", "MSFT"],
            "date": ["2026-08-10"] * 2,
            "twin_bleed_flag": [True, False],
            "twin_fallback": [False, True],
        }).to_parquet(panel_dir / "panel.parquet")

        rows = [{"symbol": "AAPL", "as_of": "2026-08-10"},
                {"symbol": "MSFT", "as_of": "2026-08-10"}]
        m1, _ = E._resolve_feature_mask({"feature": "twin_bleed_flag"}, rows, root)
        m2, _ = E._resolve_feature_mask({"feature": "twin_fallback"}, rows, root)
        assert m1 != m2

    def test_contrast_metric_without_a_control_is_not_an_absolute(self):
        value, detail = E._compute_metric(
            "hit_rate_difference",
            [{"outcome_excess": 0.1}, {"outcome_excess": -0.1}],
            None,
        )
        assert value is None
        assert "control" in detail["contrast_error"]

    def test_hit_rate_difference_is_treatment_minus_control(self):
        treat = [{"outcome_excess": 1.0}] * 3 + [{"outcome_excess": -1.0}]
        control = [{"outcome_excess": 1.0}] + [{"outcome_excess": -1.0}] * 3
        value, detail = E._compute_metric("hit_rate_difference", treat, control)
        assert value == pytest.approx(0.75 - 0.25)
        assert detail["p_value"] is not None


# ---------------------------------------------------------------------------
# W5 — Path B
# ---------------------------------------------------------------------------

class TestW5PathB:
    def test_signal_callable_accepts_the_harness_contract(self):
        """The actual cause of wf_n_names=0 — NOT the price-panel join.

        walk_forward calls `signal_fn(daily, high, low)` positionally.  The old
        closure was `signal_fn(close, **_kwargs)`, so every call raised
        TypeError, which walk_forward swallowed per-ticker into `dropped`.  H1
        and H4 recorded wf_n_names=0 on n=25,824 and n=33,930 with the panel
        loading fine.
        """
        from research.signal_engine.walk_forward import walk_forward

        idx = pd.bdate_range("2015-01-01", periods=600)
        df = pd.DataFrame({"close": pd.Series(range(1, 601), dtype=float).values}, index=idx)
        df.index.name = "TEST"

        fired = []

        def signal_fn(close, high=None, low=None):
            fired.append(str(getattr(close.index, "name", "") or ""))
            out = pd.Series(False, index=close.index)
            out.iloc[100] = True
            return out

        res = walk_forward(signal_fn, {"TEST": df}, family="cortex",
                           metric="stop_out_rate", n_trials=None,
                           run_id="test-arity", log=False)
        assert res["n_names"] == 1, f"names dropped: {res['dropped']}"
        assert fired and fired[0] == "TEST", (
            "the ticker must reach the signal callable; df['close'].name is the "
            "literal 'close', so identity travels on index.name"
        )

    def test_price_panel_tags_each_frame_with_its_ticker(self, root: Path):
        yahoo = root / "data" / "yahoo"
        yahoo.mkdir(parents=True)
        idx = pd.bdate_range("2015-01-01", periods=500)
        pd.DataFrame({"close": range(500)}, index=idx).to_parquet(yahoo / "AAPL.parquet")

        panel, diag = E._load_price_panel(root, ["AAPL", "NOPE"])
        assert panel["AAPL"].index.name == "AAPL"
        assert diag["panel_admitted"] == 1
        assert diag["panel_missing"] == 1

    def test_thin_and_missing_names_are_counted_not_silent(self, root: Path):
        yahoo = root / "data" / "yahoo"
        yahoo.mkdir(parents=True)
        idx = pd.bdate_range("2024-01-01", periods=10)
        pd.DataFrame({"close": range(10)}, index=idx).to_parquet(yahoo / "THIN.parquet")

        _, diag = E._load_price_panel(root, ["THIN"])
        assert diag["panel_thin"] == 1
        assert diag["panel_admitted"] == 0

    def test_pooled_stop_out_rate_is_trade_weighted_and_a_fraction(self):
        by_ticker = {
            "A": {"treat": {"full": {"stop_out_rate": 50.0, "n_trades": 10}}},
            "B": {"treat": {"full": {"stop_out_rate": 100.0, "n_trades": 30}}},
        }
        rate, trades = E._pooled_stop_out_rate(by_ticker)
        # (50*10 + 100*30) / 40 = 87.5 percent -> 0.875 fraction
        assert rate == pytest.approx(0.875)
        assert trades == 40

    def test_pooled_read_targets_a_key_that_exists(self):
        """The old code read wf_result['pooled']['stop_out_rate'] — no such key.

        `pooled[view]` is a percentile distribution, so the read returned None
        even when the harness had run: a second, independent reason Path B could
        never produce a verdict.
        """
        assert E._pooled_stop_out_rate({}, "treat") == (None, 0)


# ---------------------------------------------------------------------------
# W6 — metabolism
# ---------------------------------------------------------------------------

class TestW6Metabolism:
    def test_evaluation_records_provenance_not_just_status(self, root: Path):
        _write_registry(root, [_registry_row()])
        assert M.record_evaluation(
            "cortex-2026-08-26-test-hypothesis", "failed", str(root),
            metric_value=0.42, n=1234, detail={"metric": "hit_rate"},
        )
        latest = M.load_by_id("cortex-2026-08-26-test-hypothesis", str(root))
        assert latest["status"] == "failed"
        assert latest["metric_value"] == 0.42
        assert latest["evaluation_n"] == 1234
        assert latest["evaluated_at"]
        assert latest["supersedes_status"] == "registered"

    def test_status_write_appends_and_never_mutates_a_sibling_row(self, root: Path):
        """The un-retiring bug.

        _update_row_status rewrote the file with no `break`, stamping the new
        status onto EVERY row sharing the id.  Against the audit's appended
        'retired' rows for H1/H4/Q1 that would have silently un-retired them on
        the next nightly.
        """
        rid = "cortex-2026-08-26-test-hypothesis"
        _write_registry(root, [
            _registry_row(status="insufficient-n"),
            _registry_row(status="retired", retired_note="audit 2026-08-26"),
        ])
        M.record_evaluation(rid, "failed", str(root), n=10)

        rows = _rows(root)
        assert len(rows) == 3, "must APPEND a superseding row"
        assert rows[1]["status"] == "retired", "the retirement row must be untouched"
        assert rows[1]["retired_note"] == "audit 2026-08-26"

    def test_insufficient_n_advances_come_back_instead_of_dying(self, root: Path):
        """W6's headline: insufficient-n was terminal in fact, accruing in presentation."""
        rid = "cortex-2026-08-26-test-hypothesis"
        _write_registry(root, [_registry_row(come_back="2026-08-29")])
        M.record_evaluation(rid, "insufficient-n", str(root), n=3,
                            today=date(2026, 8, 29))
        latest = M.load_by_id(rid, str(root))
        assert latest["come_back"] == "2026-09-26"   # 2026-08-29 + 21 + 7
        assert latest["status"] == "insufficient-n"
        assert M.load_due(root=str(root), today=date(2026, 9, 26)), (
            "an insufficient-n hypothesis must come back once evidence accrues"
        )

    def test_terminal_verdict_clears_come_back(self, root: Path):
        rid = "cortex-2026-08-26-test-hypothesis"
        _write_registry(root, [_registry_row()])
        M.record_evaluation(rid, "failed", str(root), n=100)
        assert M.load_by_id(rid, str(root))["come_back"] is None
        assert M.load_due(root=str(root), today=date(2030, 1, 1)) == []

    def test_rearm_budget_is_finite(self, root: Path):
        rid = "cortex-2026-08-26-test-hypothesis"
        _write_registry(root, [_registry_row()])
        for _ in range(M.MAX_EVALUATION_ATTEMPTS):
            M.record_evaluation(rid, "insufficient-n", str(root), n=1,
                                today=date(2026, 8, 29))
        latest = M.load_by_id(rid, str(root))
        assert latest["status"] == "expired-insufficient-n"
        assert latest["come_back"] is None

    def test_load_due_honours_last_write_wins(self, root: Path):
        """A retired hypothesis must not resurface from its superseded row."""
        _write_registry(root, [
            _registry_row(status="registered", come_back="2026-08-01"),
            _registry_row(status="retired", come_back=None),
        ])
        assert M.load_due(root=str(root), today=date(2026, 12, 1)) == []

    def test_counters_collapse_last_write_wins(self, root: Path):
        """Raw scanning counted H1/H4/Q1 as open after the audit retired them."""
        _write_registry(root, [
            _registry_row(status="insufficient-n"),
            _registry_row(status="retired"),
        ])
        assert M._count_open_hypotheses(str(root)) == 0

    def test_reevaluation_does_not_consume_the_weekly_budget(self, root: Path):
        from datetime import datetime, timezone
        rid = "cortex-2026-08-26-test-hypothesis"
        now = datetime(2026, 8, 26, tzinfo=timezone.utc)
        _write_registry(root, [_registry_row(registered_at=now.isoformat())])
        before = M._count_week_registrations(str(root), now)
        M.record_evaluation(rid, "insufficient-n", str(root), n=1, today=now.date())
        assert M._count_week_registrations(str(root), now) == before


# ---------------------------------------------------------------------------
# W1 — the quarterly FDR batch
# ---------------------------------------------------------------------------

class TestW1FdrBatch:
    def test_benjamini_hochberg_is_the_standard_step_up(self):
        # Classic worked example: m=4, q=0.10.
        assert F.benjamini_hochberg([0.005, 0.02, 0.4, 0.9], 0.10) == [True, True, False, False]
        assert F.benjamini_hochberg([], 0.10) == []
        assert F.benjamini_hochberg([0.9], 0.10) == [False]

    def test_bh_mask_returns_in_input_order(self):
        assert F.benjamini_hochberg([0.9, 0.001], 0.10) == [False, True]

    def test_a_pre_repair_verdict_can_never_be_promoted(self):
        """H5's standing 'passed' is a W7b-PR2 artifact and must be fenced."""
        ok, reason, _ = F.assess_eligibility({
            "evaluation_detail": {"p_value": 0.01, "gate_informative": True,
                                  "episode_n": 40, "evaluator_version": "W7b-PR2"},
        })
        assert not ok
        assert "instrument artifact" in reason

    def test_a_verdict_with_no_p_value_is_fenced(self):
        ok, reason, _ = F.assess_eligibility({
            "evaluation_detail": {"gate_informative": True, "episode_n": 40,
                                  "evaluator_version": "W7b-PR3"},
        })
        assert not ok
        assert "p_value" in reason

    def test_an_uninformative_gate_is_fenced(self):
        ok, reason, _ = F.assess_eligibility({
            "evaluation_detail": {"p_value": 0.001, "gate_informative": False,
                                  "episode_n": 40, "evaluator_version": "W7b-PR3"},
        })
        assert not ok
        assert "base rate" in reason

    def test_unmeasurable_informativeness_is_fenced_not_assumed_good(self):
        ok, _, _ = F.assess_eligibility({
            "evaluation_detail": {"p_value": 0.001, "gate_informative": None,
                                  "episode_n": 40, "evaluator_version": "W7b-PR3"},
        })
        assert not ok

    def test_row_count_does_not_substitute_for_episodes(self):
        ok, reason, _ = F.assess_eligibility({
            "evaluation_detail": {"p_value": 0.001, "gate_informative": True,
                                  "episode_n": 3, "evaluator_version": "W7b-PR3"},
        })
        assert not ok
        assert "episode_n" in reason

    def test_a_fully_eligible_verdict_reaches_the_pool(self):
        ok, reason, facts = F.assess_eligibility({
            "evaluation_detail": {"p_value": 0.001, "gate_informative": True,
                                  "episode_n": 40, "evaluator_version": "W7b-PR3"},
        })
        assert ok and reason is None
        assert facts["p_value"] == 0.001

    def test_batch_lists_every_fenced_candidate_with_a_reason(self, root: Path):
        _write_registry(root, [_registry_row(
            status="passed", evaluated_at="2026-08-26T00:00:00+00:00",
            evaluation_detail={"evaluator_version": "W7b-PR2"},
        )])
        art = F.run_batch(root=root, quarter="2026Q3", dry_run=True)
        assert art["n_candidates"] == 1
        assert art["n_eligible"] == 0
        assert art["n_survivors"] == 0
        assert art["ineligible"][0]["ineligible_reason"]

    def test_batch_promotes_nothing_by_construction(self, root: Path):
        _write_registry(root, [_registry_row(
            status="passed", evaluated_at="2026-08-26T00:00:00+00:00",
            metric_value=0.3,
            evaluation_detail={"evaluator_version": "W7b-PR3", "p_value": 0.0001,
                               "gate_informative": True, "episode_n": 40},
        )])
        art = F.run_batch(root=root, quarter="2026Q3", dry_run=True)
        assert art["n_survivors"] == 1
        assert "necessary" in art["promotion_note"].lower()
        # No authority field anywhere in the artifact.
        assert "authority" not in json.dumps(art).lower().replace(
            art["promotion_note"].lower(), ""
        )


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------

def test_evaluator_never_emits_a_pass_from_an_unapplied_query(root: Path):
    """The integration guarantee the audit asked for.

    Every registered hypothesis whose query or gate cannot be honoured must
    return an instrument verdict, never 'passed' or 'failed'.
    """
    _write_registry(root, [
        _registry_row(id="a", spine_query={"feature": "high_alibi_flag"},
                      pre_committed_gate={"metric": "hit_rate", "threshold": -0.05,
                                          "min_n": 25, "horizon_d": 21,
                                          "direction_expected": -1}),
        _registry_row(id="b", pre_committed_gate={"metric": "made_up_metric",
                                                  "threshold": 1, "min_n": 25,
                                                  "horizon_d": 21}),
    ])
    summary = E.evaluate_due(root=root, dry_run=True, today=date(2026, 8, 29))
    verdicts = {r["id"]: r["verdict"] for r in summary["results"]}
    assert verdicts["a"] == "invalid-gate"
    assert verdicts["b"] == "uncomputable-metric"
    assert not (set(verdicts.values()) & {"passed", "failed"})
