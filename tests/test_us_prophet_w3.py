"""Adversarial tests for the W3 prospective evidence ledger (PR-3C).

Measurement plumbing only. These tests pin pairing, idempotency, fail-closed
conflicts, structural-receipt serialization, and zero authority. They do not
compute or assert C1-vs-shadow IC, delta, p-values, or a leader.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd
import pytest

from engine import us_board_rank as ubr
from engine import us_prophet_fusion as fus
from engine import us_prophet_grades as upg
from engine import us_prophet_w3 as w3

REPO = Path(__file__).resolve().parents[1]


def _cand(**overrides) -> dict:
    row = {
        "stamp_date": "2026-08-18",
        "ticker": "AAA",
        "board_definition": w3.CANONICAL_BOARD,
        "selection_era": "anticipation-v1",
        "anchor_era": "abs-session-2026-08-06",
        "stage": "live",
        "lane": "buy",
        "prophet_score": 41.2,
        "score_rank": 1,
        "prophet_shadow_definition": w3.SHADOW_DEFINITION,
        "prophet_shadow_score": 38.0,
        "prophet_shadow_score_rank": 3,
    }
    row.update(overrides)
    return row


def _grade(**overrides) -> dict:
    row = {
        "stamp_date": "2026-08-18",
        "ticker": "AAA",
        "board_definition": w3.CANONICAL_BOARD,
        "horizon": 10,
        "excess_spy": 0.0123,
        "fill_date": "2026-08-19",
        "mark_date": "2026-09-02",
        "graded_asof": "2026-09-02",
        "bench": "SPY",
    }
    row.update(overrides)
    return row


def _receipt() -> dict:
    return {
        "schema": w3.STRUCTURAL_SCHEMA,
        "canonical_observation": True,
        "admitted_frozen": ["alpha", "off_high"],
        "full_model_rank_matches_published": True,
        "families_present": ["F2_MOMENTUM_EXTENSION", "F8_ATTENTION_CROWDING"],
        "families_absent": [{"family": "F4_POSITIONING", "reason": "no surviving member"}],
        "lofo": [
            {
                "family": "F2_MOMENTUM_EXTENSION",
                "rows_carrying": 12,
                "distinct_values": 8,
                "modal_value": 0.5,
                "modal_share": 0.25,
                "dispersion": 0.11,
                "mean_abs_rank_displacement": 1.5,
                "max_abs_rank_displacement": 4,
                "rows_moved": 6,
                "top30_churn": 2,
            },
            {
                "family": "F8_ATTENTION_CROWDING",
                "rows_carrying": 12,
                "distinct_values": 2,
                "modal_value": 1.0,
                "modal_share": 0.9,
                "dispersion": 0.01,
                "mean_abs_rank_displacement": 0.2,
                "max_abs_rank_displacement": 1,
                "rows_moved": 2,
                "top30_churn": 0,
            },
        ],
        "census": [
            {
                "member": "alpha",
                "family": "F2_MOMENTUM_EXTENSION",
                "status": "voting",
                "coverage": 1.0,
                "distinct_values": 8,
                "variation_share": 1.0,
                "thresholds": {
                    "presence_floor": 0.80,
                    "min_distinct_values": 2,
                    "min_variation_share": 0.50,
                },
                "reason": "admitted and not collapsed",
                "source": "board.alpha",
                "staleness_basis": None,
            },
            {
                "member": "news_burst",
                "family": "F8_ATTENTION_CROWDING",
                "status": "vote_inert",
                "coverage": 1.0,
                "distinct_values": 1,
                "variation_share": 0.0,
                "thresholds": {
                    "presence_floor": 0.80,
                    "min_distinct_values": 2,
                    "min_variation_share": 0.50,
                },
                "reason": "vote_inert",
                "source": "board.news_burst",
                "staleness_basis": None,
            },
        ],
    }


def _accrue(tmp_path, monkeypatch, candidates, grades, receipt=None, **kwargs):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    structural = None
    if receipt is not None:
        stamps = sorted({str(r["stamp_date"])[:10] for r in candidates})
        structural = {stamp: receipt for stamp in stamps}
    return w3.accrue(
        root=tmp_path,
        candidates=pd.DataFrame(candidates),
        grades=pd.DataFrame(grades),
        structural_by_stamp=structural if structural is not None else {},
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# pairing
# --------------------------------------------------------------------------- #

class TestPairedPopulation:

    def test_canonical_plus_shadow_writes_one_observation(self, tmp_path, monkeypatch):
        doc = _accrue(tmp_path, monkeypatch, [_cand()], [_grade()], _receipt())
        paired = w3.load_paired(tmp_path)
        assert len(paired) == 1
        row = paired.iloc[0]
        assert row["ticker"] == "AAA"
        assert row["board_definition"] == w3.CANONICAL_BOARD
        assert row["prophet_shadow_definition"] == w3.SHADOW_DEFINITION
        assert row["horizon"] == 10
        assert row["excess_spy"] == pytest.approx(0.0123)
        assert doc["n_paired_rows"] == 1

    def test_one_grade_row_serves_both_rank_columns(self, tmp_path, monkeypatch):
        rows, _ = w3.build_paired_rows(pd.DataFrame([_cand()]), pd.DataFrame([_grade()]))
        assert len(rows) == 1
        assert rows[0]["score_rank"] == 1
        assert rows[0]["prophet_shadow_score_rank"] == 3
        assert rows[0]["excess_spy"] == pytest.approx(0.0123)
        assert rows[0]["benchmark"] == "SPY"

    def test_fallback_produces_no_paired_race_row(self, tmp_path, monkeypatch):
        doc = _accrue(
            tmp_path, monkeypatch,
            [_cand(board_definition=w3.FALLBACK_DEFINITION,
                   prophet_shadow_definition=None,
                   prophet_shadow_score=None,
                   prophet_shadow_score_rank=None)],
            [_grade(board_definition=w3.FALLBACK_DEFINITION)],
            None,
        )
        assert w3.load_paired(tmp_path).empty
        assert doc["n_paired_rows"] == 0
        assert doc["sessions"][0]["liveness"] == w3.LIVENESS_DEGRADED

    def test_null_shadow_produces_no_paired_row(self):
        rows, doc = w3.build_paired_rows(
            pd.DataFrame([_cand(prophet_shadow_score=None,
                                prophet_shadow_score_rank=None)]),
            pd.DataFrame([_grade()]),
        )
        assert rows == []
        assert doc["excluded_null_shadow"] == 1

    def test_off_board_row_produces_no_paired_row(self):
        rows, doc = w3.build_paired_rows(
            pd.DataFrame([_cand(lane="not_on_board")]),
            pd.DataFrame([_grade()]),
        )
        assert rows == []
        assert doc["excluded_off_board"] == 1

    def test_retired_v2_board_is_excluded(self):
        rows, doc = w3.build_paired_rows(
            pd.DataFrame([_cand(board_definition="us_prophet_v2")]),
            pd.DataFrame([_grade(board_definition="us_prophet_v2")]),
        )
        assert rows == []
        assert doc["excluded_fallback"] == 1

    def test_unmatured_h10_remains_pending_not_zero(self, tmp_path, monkeypatch):
        doc = _accrue(tmp_path, monkeypatch, [_cand()], [], _receipt())
        paired = w3.load_paired(tmp_path)
        assert len(paired) == 1
        assert pd.isna(paired.iloc[0]["excess_spy"]) or paired.iloc[0]["excess_spy"] is None
        assert paired.iloc[0]["excess_spy"] != 0
        assert doc["sessions"][0]["liveness"] == w3.LIVENESS_UNMATURED
        assert doc["paired_qualify"]["n_pending"] == 1


# --------------------------------------------------------------------------- #
# idempotency / conflict / gaps
# --------------------------------------------------------------------------- #

class TestAppendOnlyLaws:

    def test_same_session_retry_does_not_increase_observation_count(
            self, tmp_path, monkeypatch):
        _accrue(tmp_path, monkeypatch, [_cand()], [_grade()], _receipt())
        _accrue(tmp_path, monkeypatch, [_cand()], [_grade()], _receipt())
        assert len(w3.load_paired(tmp_path)) == 1
        assert len(w3.load_family(tmp_path)) == 3  # 2 lofo + 1 abstaining
        assert len(w3.load_coverage(tmp_path)) == 2

    def test_conflicting_duplicate_payload_fails_closed(self, tmp_path, monkeypatch):
        _accrue(tmp_path, monkeypatch, [_cand()], [_grade()], _receipt())
        with pytest.raises(w3.W3ConflictError) as exc:
            _accrue(tmp_path, monkeypatch,
                    [_cand(prophet_score=99.0, score_rank=7)],
                    [_grade()], _receipt())
        assert exc.value.existing_fp != exc.value.incoming_fp
        assert len(w3.load_paired(tmp_path)) == 1
        assert w3.load_paired(tmp_path).iloc[0]["score_rank"] == 1

    def test_maturation_fills_pending_outcome_without_new_observation(
            self, tmp_path, monkeypatch):
        _accrue(tmp_path, monkeypatch, [_cand()], [], _receipt())
        assert pd.isna(w3.load_paired(tmp_path).iloc[0]["excess_spy"])
        doc = _accrue(tmp_path, monkeypatch, [_cand()], [_grade()], _receipt())
        paired = w3.load_paired(tmp_path)
        assert len(paired) == 1
        assert paired.iloc[0]["excess_spy"] == pytest.approx(0.0123)
        assert doc["paired"]["matured"] == 1
        assert doc["sessions"][0]["liveness"] == w3.LIVENESS_PAIRED_ACCRUED

    def test_conflicting_frozen_outcome_fails_closed(self, tmp_path, monkeypatch):
        _accrue(tmp_path, monkeypatch, [_cand()], [_grade()], _receipt())
        with pytest.raises(w3.W3ConflictError):
            _accrue(tmp_path, monkeypatch, [_cand()],
                    [_grade(excess_spy=0.99)], _receipt())

    def test_pages_reconstructed_input_cannot_enter(self):
        with pytest.raises(w3.W3IntegrityError):
            w3.build_paired_rows(
                pd.DataFrame([_cand(source="pages")]),
                pd.DataFrame([_grade()]),
            )
        with pytest.raises(w3.W3IntegrityError):
            w3.build_paired_rows(
                pd.DataFrame([_cand(source="reconstructed")]),
                pd.DataFrame([_grade()]),
            )
        with pytest.raises(w3.W3IntegrityError):
            w3.accrue(require_stamp="https://example.com/board.json")

    def test_missing_session_remains_a_gap(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        with pytest.raises(w3.W3IntegrityError):
            w3.accrue(
                root=tmp_path,
                candidates=pd.DataFrame([_cand()]),
                grades=pd.DataFrame([_grade()]),
                structural_by_stamp={},
                require_stamp="2026-08-17",
            )
        paired = w3.load_paired(tmp_path)
        if not paired.empty:
            assert "2026-08-17" not in set(paired["stamp_date"].astype(str))
        sessions = w3.sessions_by_stamp(tmp_path)
        assert sessions["2026-08-17"]["liveness"] == w3.LIVENESS_MISSING
        assert w3.status_path(tmp_path).exists()
        assert w3.sessions_path(tmp_path).exists()

    def test_candidate_row_order_permutation_does_not_change_output(self):
        a = [_cand(ticker="AAA", score_rank=1, prophet_shadow_score_rank=2),
             _cand(ticker="BBB", score_rank=2, prophet_shadow_score_rank=1)]
        grades = [_grade(ticker="AAA"), _grade(ticker="BBB")]
        forward, _ = w3.build_paired_rows(pd.DataFrame(a), pd.DataFrame(grades))
        backward, _ = w3.build_paired_rows(pd.DataFrame(list(reversed(a))),
                                           pd.DataFrame(list(reversed(grades))))
        assert [r["ticker"] for r in forward] == [r["ticker"] for r in backward]
        assert [r["identity_fingerprint"] for r in forward] == [
            r["identity_fingerprint"] for r in backward]

    def test_historical_part_is_not_silently_rewritten(self, tmp_path, monkeypatch):
        _accrue(tmp_path, monkeypatch, [_cand(stamp_date="2026-08-18")],
                [_grade(stamp_date="2026-08-18")], _receipt())
        first = w3._part_path("paired", "2026-08-18", tmp_path).read_bytes()
        _accrue(tmp_path, monkeypatch,
                [_cand(stamp_date="2026-08-19", ticker="BBB")],
                [_grade(stamp_date="2026-08-19", ticker="BBB")],
                _receipt())
        assert w3._part_path("paired", "2026-08-18", tmp_path).read_bytes() == first
        assert len(w3.load_paired(tmp_path)) == 2


# --------------------------------------------------------------------------- #
# structural serialization — no LOFO recompute
# --------------------------------------------------------------------------- #

class TestStructuralPersistence:

    def test_family_and_coverage_reproduce_receipt_values(self, tmp_path, monkeypatch):
        receipt = _receipt()
        _accrue(tmp_path, monkeypatch, [_cand()], [_grade()], receipt)
        family = w3.load_family(tmp_path).set_index("family")
        f2 = family.loc["F2_MOMENTUM_EXTENSION"]
        assert bool(f2["active"]) is True
        assert f2["mean_abs_rank_delta"] == pytest.approx(1.5)
        assert f2["max_abs_rank_delta"] == 4
        assert f2["rows_moved"] == 6
        assert f2["top30_churn"] == 2
        assert f2["rows_contributing"] == 12
        assert f2["structural_schema"] == w3.STRUCTURAL_SCHEMA
        absent = family.loc["F4_POSITIONING"]
        assert bool(absent["abstaining"]) is True
        assert pd.isna(absent["mean_abs_rank_delta"])
        coverage = w3.load_coverage(tmp_path).set_index("member")
        assert coverage.loc["alpha"]["status"] == "voting"
        assert coverage.loc["news_burst"]["status"] == "vote_inert"
        assert coverage.loc["alpha"]["coverage"] == pytest.approx(1.0)

    def test_writer_does_not_call_lofo(self, tmp_path, monkeypatch):
        called = {"n": 0}

        def _boom(*_a, **_k):
            called["n"] += 1
            raise AssertionError("LOFO must not be recomputed in the ledger writer")

        monkeypatch.setattr(fus, "diagnose_structure", _boom)
        monkeypatch.setattr(fus, "fuse_board", _boom)
        _accrue(tmp_path, monkeypatch, [_cand()], [_grade()], _receipt())
        assert called["n"] == 0
        assert not w3.load_family(tmp_path).empty

    def test_outcome_injection_cannot_alter_structural_rows(self):
        receipt = _receipt()
        dirty = dict(receipt)
        dirty["lofo"] = [dict(item, excess_spy=99.0, ic=0.8, leader="AAA")
                         for item in receipt["lofo"]]
        # Injecting unused keys on the receipt must not change serialized identity
        # of the known LOFO fields. Extra keys are ignored.
        a = w3.family_rows_from_receipt("2026-08-18", receipt)
        b = w3.family_rows_from_receipt("2026-08-18", dirty)
        assert [w3.fingerprint(r, w3.FAMILY_IDENTITY) for r in a] == [
            w3.fingerprint(r, w3.FAMILY_IDENTITY) for r in b]

    def test_unknown_structural_schema_fails_closed(self):
        with pytest.raises(w3.W3SchemaError):
            w3.family_rows_from_receipt("2026-08-18", {"schema": "nope", "lofo": []})

    def test_duplicate_incompatible_grades_fail_closed(self):
        with pytest.raises(w3.W3IntegrityError):
            w3.build_paired_rows(
                pd.DataFrame([_cand()]),
                pd.DataFrame([_grade(excess_spy=0.1), _grade(excess_spy=0.2)]),
            )

    def test_board_definition_mismatch_fails_closed(self):
        with pytest.raises(w3.W3IntegrityError):
            w3.build_paired_rows(
                pd.DataFrame([_cand()]),
                pd.DataFrame([_grade(board_definition="us_prophet_v2")]),
            )


# --------------------------------------------------------------------------- #
# one grader, no second scorer, nightly gate, zero authority
# --------------------------------------------------------------------------- #

class TestOneGraderAndZeroAuthority:

    def test_no_second_grader_or_scorer_is_imported(self):
        source = (REPO / "engine" / "us_prophet_w3.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert "engine.grading" not in imported
        assert "engine.us_board_rank" not in imported
        assert "engine.us_prophet_fusion" not in imported
        assert "engine.prophet_bridge" not in imported
        text = source
        assert "forward_metrics" not in text
        assert "diagnose_structure" not in text
        assert "fuse_board" not in text
        assert "score_rows" not in text
        assert "load_grades" in text

    def test_load_grades_is_the_only_outcome_ruler(self, tmp_path, monkeypatch):
        seen = {"n": 0}
        real = upg.load_grades

        def _wrap(*args, **kwargs):
            seen["n"] += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(upg, "load_grades", _wrap)
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        w3.accrue(
            root=tmp_path,
            candidates=pd.DataFrame([_cand()]),
            grades=None,
            structural_by_stamp={"2026-08-18": _receipt()},
        )
        assert seen["n"] == 1

    def test_nightly_lane_guard(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        rows, _ = w3.build_paired_rows(pd.DataFrame([_cand()]), pd.DataFrame([_grade()]))
        assert w3.append_paired(rows, tmp_path)["written"] == 0
        assert not list((tmp_path / "data").rglob("*"))
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        assert w3.append_paired(rows, tmp_path)["written"] == 1

    def test_w3_cannot_import_rank_gate_featured_plan_authority(self):
        source = (REPO / "engine" / "us_prophet_w3.py").read_text(encoding="utf-8")
        for token in ("us_board_rank", "prophet_bridge", "FEATURED_CAP",
                      "SELECTION_ERA", "score_rows", "select_candidates"):
            assert token not in source

    def test_live_rank_consumers_do_not_import_w3(self):
        offenders = []
        for rel in (
            "engine/us_board_rank.py",
            "engine/us_prophet_fusion.py",
            "engine/prophet_bridge.py",
            "engine/us_candidate_lanes.py",
            "scripts/build_stock_library.py",
        ):
            text = (REPO / rel).read_text(encoding="utf-8", errors="ignore")
            if "us_prophet_w3" in text or "us_prophet_rank/w3" in text:
                offenders.append(rel)
        assert not offenders

    def test_no_engine_side_w3_persistent_write(self):
        for rel in ("engine/us_board_rank.py", "engine/us_prophet_fusion.py"):
            text = (REPO / rel).read_text(encoding="utf-8")
            assert "us_prophet_rank/w3" not in text
            assert "us_prophet_w3" not in text

    def test_definition_literals_match_the_ranker(self):
        assert w3.CANONICAL_BOARD == ubr.BOARD_DEFINITION
        assert w3.SHADOW_DEFINITION == ubr.SHADOW_DEFINITION
        assert w3.FALLBACK_DEFINITION == ubr.FALLBACK_DEFINITION
        assert w3.STRUCTURAL_SCHEMA == fus.W3_DIAGNOSTICS_SCHEMA

    def test_no_production_c1_constants_changed(self):
        # PR-3C must not retune floors or bump the selection era.
        assert ubr.SELECTION_ERA
        assert fus.PRESENCE_FLOOR == 0.50
        assert fus.VARIANCE_MIN_DISTINCT == 2


class TestWorkflowWiring:

    def test_accrual_is_in_us_prophet_ledgers_after_grades_before_commit(self):
        import yaml
        daily = yaml.safe_load(
            (REPO / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
        job = daily["jobs"]["us_prophet_ledgers"]
        runs = [str(s.get("run") or "") for s in job["steps"]]
        grade_i = next(i for i, r in enumerate(runs)
                       if "python -m scripts.grade_us_prophet_candidates --nightly" in r)
        w3_i = next(i for i, r in enumerate(runs)
                    if "python -m scripts.accrue_us_prophet_w3 --nightly" in r)
        commit_i = next(i for i, s in enumerate(job["steps"])
                        if "git add" in str(s.get("run") or "")
                        and "git commit" in str(s.get("run") or ""))
        # Order vs the miss-audit step is already pinned by the off-engine-lane
        # suite. This file must not name that module: it is ops telemetry with
        # zero authority and no new callers.
        assert grade_i < w3_i < commit_i
        assert "--require-board-as-of" in runs[w3_i]
        commit = str(job["steps"][commit_i]["run"])
        assert "data/us_prophet_rank/w3" in commit
        assert (job.get("env") or {}).get("COLLECT_LANE") == "nightly"

    def test_dag_declares_the_same_order(self):
        import yaml
        dag = yaml.safe_load((REPO / "config/dag.yml").read_text(encoding="utf-8"))
        lane = next(item for item in dag["lanes"]
                    if item.get("job") == "us_prophet_ledgers")
        modules = [s.get("module") for s in lane["steps"]]
        assert modules.index("scripts.grade_us_prophet_candidates") < \
            modules.index("scripts.accrue_us_prophet_w3")
        w3_step = next(s for s in lane["steps"]
                       if s.get("module") == "scripts.accrue_us_prophet_w3")
        assert "--require-board-as-of" in (w3_step.get("args") or [])


def _write_board(tmp_path, as_of="2026-08-18", receipt=None, definition="us_prophet_v3"):
    payload = {
        "as_of": as_of,
        "board_definition": definition,
        "ranking": {
            "definition": definition,
            "fusion": {},
        },
    }
    if receipt is not None:
        payload["ranking"]["fusion"]["w3_structural"] = receipt
    path = tmp_path / "site" / "factordata" / "us_standouts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# PR-3D: durable missing-session, provenance fence, lawful status
# --------------------------------------------------------------------------- #

class TestDurableMissingSession:

    def test_expected_stamp_absent_persists_session_missing_and_fails_visible(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        with pytest.raises(w3.W3IntegrityError) as exc:
            w3.accrue(
                root=tmp_path,
                candidates=pd.DataFrame(),
                grades=pd.DataFrame(),
                structural_by_stamp={},
                require_stamp="2026-08-17",
            )
        assert "2026-08-17" in str(exc.value)
        assert w3.load_paired(tmp_path).empty
        assert w3.load_family(tmp_path).empty
        assert w3.load_coverage(tmp_path).empty
        rec = w3.sessions_by_stamp(tmp_path)["2026-08-17"]
        assert rec["liveness"] == w3.LIVENESS_MISSING
        assert rec["terminal"] is True
        assert w3.status_path(tmp_path).exists()
        status = json.loads(w3.status_path(tmp_path).read_text(encoding="utf-8"))
        assert status["n_missing"] == 1
        assert status["missing_sessions"][0]["stamp_date"] == "2026-08-17"

    def test_gap_receipt_survives_nonzero_exit(self, tmp_path, monkeypatch):
        """The always-run commit can stage the gap even though the step failed."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        with pytest.raises(w3.W3IntegrityError):
            w3.accrue(
                root=tmp_path,
                candidates=pd.DataFrame(),
                grades=pd.DataFrame(),
                structural_by_stamp={},
                require_stamp="2026-08-15",
            )
        staged = {
            w3.sessions_path(tmp_path).relative_to(tmp_path).as_posix(),
            w3.status_path(tmp_path).relative_to(tmp_path).as_posix(),
        }
        assert staged <= {
            p.relative_to(tmp_path).as_posix()
            for p in (tmp_path / "data").rglob("*") if p.is_file()
        }


class TestProvenanceFence:

    def test_session_missing_then_reconstructed_payload_does_not_upgrade(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        with pytest.raises(w3.W3IntegrityError):
            w3.accrue(
                root=tmp_path,
                candidates=pd.DataFrame(),
                grades=pd.DataFrame(),
                structural_by_stamp={},
                require_stamp="2026-08-17",
            )
        n_before = w3.build_status_surface(tmp_path)["paired_sessions_accrued"]
        doc = w3.accrue(
            root=tmp_path,
            candidates=pd.DataFrame([_cand(stamp_date="2026-08-17")]),
            grades=pd.DataFrame([_grade(stamp_date="2026-08-17")]),
            structural_by_stamp={"2026-08-17": _receipt()},
            require_stamp="2026-08-17",
        )
        assert "2026-08-17" in doc["reconstruction_refused"]
        assert w3.load_paired(tmp_path).empty
        assert w3.sessions_by_stamp(tmp_path)["2026-08-17"]["liveness"] == w3.LIVENESS_MISSING
        assert w3.build_status_surface(tmp_path)["paired_sessions_accrued"] == n_before
        assert w3.build_status_surface(tmp_path)["matured_h10_sessions"] == 0

    def test_degraded_then_canonical_replay_does_not_upgrade(
            self, tmp_path, monkeypatch):
        _accrue(
            tmp_path, monkeypatch,
            [_cand(board_definition=w3.FALLBACK_DEFINITION,
                   prophet_shadow_definition=None,
                   prophet_shadow_score=None,
                   prophet_shadow_score_rank=None)],
            [_grade(board_definition=w3.FALLBACK_DEFINITION)],
            None,
        )
        assert w3.sessions_by_stamp(tmp_path)["2026-08-18"]["liveness"] == w3.LIVENESS_DEGRADED
        doc = _accrue(tmp_path, monkeypatch, [_cand()], [_grade()], _receipt())
        assert "2026-08-18" in doc["reconstruction_refused"]
        assert w3.load_paired(tmp_path).empty
        assert w3.sessions_by_stamp(tmp_path)["2026-08-18"]["liveness"] == w3.LIVENESS_DEGRADED

    def test_unmatured_to_matured_is_allowed(self, tmp_path, monkeypatch):
        _accrue(tmp_path, monkeypatch, [_cand()], [], _receipt())
        assert w3.sessions_by_stamp(tmp_path)["2026-08-18"]["liveness"] == w3.LIVENESS_UNMATURED
        doc = _accrue(tmp_path, monkeypatch, [_cand()], [_grade()], _receipt())
        assert w3.sessions_by_stamp(tmp_path)["2026-08-18"]["liveness"] == w3.LIVENESS_PAIRED_ACCRUED
        assert len(w3.load_paired(tmp_path)) == 1
        assert doc["sessions_written"]["matured"] == 1

    def test_commit_utc_date_is_not_the_observation_identity(
            self, tmp_path, monkeypatch):
        import datetime as dt
        monkeypatch.setenv("COLLECT_LANE", "nightly")

        class _FrozenDate(dt.date):
            @classmethod
            def today(cls):
                return cls(2099, 1, 1)

        class _FrozenDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2099, 1, 1, 12, 0, 0, tzinfo=tz)

            @classmethod
            def utcnow(cls):
                return cls(2099, 1, 1, 12, 0, 0)

        monkeypatch.setattr(dt, "date", _FrozenDate)
        monkeypatch.setattr(dt, "datetime", _FrozenDateTime)
        doc = _accrue(
            tmp_path, monkeypatch,
            [_cand(stamp_date="2026-08-14")],
            [_grade(stamp_date="2026-08-14")],
            _receipt(),
        )
        paired = w3.load_paired(tmp_path)
        assert list(paired["stamp_date"].astype(str)) == ["2026-08-14"]
        assert "2099-01-01" not in json.dumps(doc, default=str)
        assert w3.sessions_by_stamp(tmp_path)["2026-08-14"]["stamp_date"] == "2026-08-14"

    def test_pages_only_board_without_candidates_is_not_a_w3_session(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        _write_board(tmp_path, as_of="2026-08-16", receipt=_receipt())
        with pytest.raises(w3.W3IntegrityError):
            w3.accrue(
                root=tmp_path,
                candidates=pd.DataFrame(),
                grades=pd.DataFrame(),
                structural_by_stamp=None,
                require_board_as_of=True,
            )
        assert w3.load_paired(tmp_path).empty
        rec = w3.sessions_by_stamp(tmp_path)["2026-08-16"]
        assert rec["liveness"] == w3.LIVENESS_MISSING


class TestStructuralFailClosed:

    def test_structural_receipt_absent_for_valid_pair_fails_and_names(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        with pytest.raises(w3.W3IntegrityError) as exc:
            w3.accrue(
                root=tmp_path,
                candidates=pd.DataFrame([_cand()]),
                grades=pd.DataFrame([_grade()]),
                structural_by_stamp={},
                require_stamp="2026-08-18",
            )
        assert "structural receipt absent" in str(exc.value)
        assert w3.load_family(tmp_path).empty
        assert w3.load_coverage(tmp_path).empty
        # Paired race rows may persist; family/coverage must not be fabricated.
        paired = w3.load_paired(tmp_path)
        assert len(paired) == 1

    def test_board_as_of_mismatch_with_required_stamp_fails_closed(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        _write_board(tmp_path, as_of="2026-08-17", receipt=_receipt())
        with pytest.raises(w3.W3IntegrityError) as exc:
            w3.accrue(
                root=tmp_path,
                candidates=pd.DataFrame([_cand(stamp_date="2026-08-18")]),
                grades=pd.DataFrame([_grade(stamp_date="2026-08-18")]),
                structural_by_stamp={"2026-08-18": _receipt()},
                require_stamp="2026-08-18",
            )
        assert "as_of" in str(exc.value) and "mismatches" in str(exc.value)

    def test_same_stamp_board_candidate_structural_agree(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        _write_board(tmp_path, as_of="2026-08-18", receipt=_receipt())
        doc = w3.accrue(
            root=tmp_path,
            candidates=pd.DataFrame([_cand()]),
            grades=pd.DataFrame([_grade()]),
            structural_by_stamp=None,
            require_board_as_of=True,
        )
        assert doc["board_as_of"] == "2026-08-18"
        assert doc["require_stamp"] == "2026-08-18"
        assert doc["sessions"][0]["stamp_date"] == "2026-08-18"
        assert doc["sessions"][0]["structural_schema"] == w3.STRUCTURAL_SCHEMA
        assert len(w3.load_family(tmp_path)) >= 1
        assert len(w3.load_coverage(tmp_path)) >= 1


class TestLawfulStatusSurface:

    def test_missing_store_is_not_commissioned(self, tmp_path):
        payload = w3.build_status_surface(tmp_path)
        assert payload["commissioned"] is False
        text = w3.render_status_text(payload)
        assert "NOT COMMISSIONED" in text
        assert "no false green" in text.lower() or "not commissioned" in text.lower()
        for token in w3.FORBIDDEN_STATUS_TOKENS:
            assert token.lower() not in text.lower()

    def test_status_emits_accrual_not_comparison(self, tmp_path, monkeypatch):
        _accrue(tmp_path, monkeypatch, [_cand()], [], _receipt())
        payload = w3.build_status_surface(tmp_path)
        assert payload["commissioned"] is True
        assert payload["paired_sessions_accrued"] == 1
        assert payload["matured_h10_sessions"] == 0
        assert payload["first_eligible_paired_stamp"] == "2026-08-18"
        assert payload["latest_session"]["liveness"] == w3.LIVENESS_UNMATURED
        assert "PENDING" in payload["first_lawful_comparison_read"]
        assert payload["honest_n_floor"] == 20
        assert payload["authority"] == "measurement only / none"
        dumped = json.dumps(payload)
        for token in w3.FORBIDDEN_STATUS_TOKENS:
            assert token.lower() not in dumped.lower()
        text = w3.render_status_text(payload)
        for token in w3.FORBIDDEN_STATUS_TOKENS:
            assert token.lower() not in text.lower()

    def test_no_comparison_code_in_w3_modules(self):
        blobs = []
        for rel in ("engine/us_prophet_w3.py",
                    "scripts/accrue_us_prophet_w3.py",
                    "scripts/report_us_prophet_w3.py"):
            blobs.append((rel, (REPO / rel).read_text(encoding="utf-8")))
        banned_calls = (
            "spearmanr", "newey_west", "def compute_w3", "rank_ic(",
            "top30_alpha",
        )
        for rel, text in blobs:
            for token in banned_calls:
                assert token not in text, f"{rel} contains comparison token {token!r}"

    def test_cli_report_reads_store_without_nightly_lane(self, tmp_path, monkeypatch):
        _accrue(tmp_path, monkeypatch, [_cand()], [], _receipt())
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        payload = w3.build_status_surface(tmp_path)
        assert payload["commissioned"] is True
        from scripts import report_us_prophet_w3 as report
        # The reporter must not write.
        before = list((tmp_path / "data").rglob("*"))
        text = w3.render_status_text(payload)
        assert "paired sessions accrued" in text
        assert list((tmp_path / "data").rglob("*")) == before
        assert hasattr(report, "main")
