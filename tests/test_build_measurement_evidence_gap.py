"""tests/test_build_measurement_evidence_gap.py — Evidence-Gap panel builder tests (PR-A1).

Tests:
1. build_grading_closure: correct starvation logic on synthetic fixture.
2. build_grading_closure: absent-file-safe (returns {available: False}).
3. build_trial_budgets: groupby family, latest_ts, n counts.
4. build_trial_budgets: absent-file-safe.
5. build_rule_experiments: collapses lifecycle rows; pooled_sum correct.
6. build_rule_experiments: absent-file-safe.
7. build_qledger_reliability: correct row extraction and §0.5.8 caveat present.
8. build_qledger_reliability: absent-file-safe.
9. No "validated" / "已验证" in any new function output (BC-2).

House rules:
- Synthetic fixture files only — no real data writes.
- No git operations; no parquet appends.
- Pure stdlib + json; no scipy, sklearn, statsmodels.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Import the functions under test.  We patch the module-level path constants
# using monkeypatch so each test can supply its own synthetic file.
import scripts.build_measurement as bm  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 1 & 2. build_grading_closure
# ---------------------------------------------------------------------------

GRADING_CLOSURE_FIXTURE = {
    "schema": "grading_closure.v1",
    "generated_at": "2026-07-06T04:38:22Z",
    "n_ledgers": 4,
    "n_closed": 1,
    "n_grader_starved": 2,
    "n_log_only": 1,
    "ledgers": [
        # CLOSED: grader wired, n_graded > 0
        {
            "key": "ledger_closed",
            "path": "data/x/closed.parquet",
            "storage": "present",
            "grader_wired": "Y:scripts/grade_x.py",
            "n_logged": 100,
            "n_graded": 95,
            "last_graded_at": "2026-07-05T10:00:00Z",
            "verdict": "CLOSED",
        },
        # TIME-STARVED: grader wired, n_graded == 0
        {
            "key": "ledger_time_starved",
            "path": "data/x/time.parquet",
            "storage": "present",
            "grader_wired": "Y:engine/y.py",
            "n_logged": 5,
            "n_graded": 0,
            "last_graded_at": None,
            "verdict": "GRADER-STARVED",
        },
        # BUILD-STARVED: grader NOT wired, n_graded == 0
        {
            "key": "ledger_build_starved",
            "path": "data/x/build.parquet",
            "storage": "present",
            "grader_wired": "N",
            "n_logged": 26,
            "n_graded": 0,
            "last_graded_at": None,
            "verdict": "LOG-ONLY",
        },
        # Another TIME-STARVED with a known maturity note
        {
            "key": "oracle_forward_ledger",
            "path": "data/oracle/forward_ledger.jsonl",
            "storage": "present",
            "grader_wired": "Y:scripts/oracle_nightly.py",
            "n_logged": 173,
            "n_graded": 0,
            "last_graded_at": None,
            "verdict": "GRADER-STARVED",
        },
    ],
}


def test_grading_closure_starvation_logic(monkeypatch, tmp_path):
    fixture_path = tmp_path / "governance" / "grading_closure.json"
    _write_json(fixture_path, GRADING_CLOSURE_FIXTURE)
    monkeypatch.setattr(bm, "GRADING_CLOSURE_PATH", fixture_path)

    result = bm.build_grading_closure()

    assert result["available"] is True
    assert result["n_ledgers"] == 4

    rows_by_key = {r["key"]: r for r in result["rows"]}

    # CLOSED ledger
    closed = rows_by_key["ledger_closed"]
    assert closed["starvation_type"] == "closed"
    assert "closed" in closed["starvation"]

    # TIME-STARVED ledger (grader wired, n_graded=0)
    time_row = rows_by_key["ledger_time_starved"]
    assert time_row["starvation_type"] == "time"
    assert "time-starved" in time_row["starvation"].lower()

    # BUILD-STARVED ledger (grader_wired == 'N')
    build_row = rows_by_key["ledger_build_starved"]
    assert build_row["starvation_type"] == "build"
    assert "needs grader" in build_row["starvation"].lower()

    # oracle_forward_ledger — TIME-STARVED with maturity note from _MATURITY_NOTES
    oracle_row = rows_by_key["oracle_forward_ledger"]
    assert oracle_row["starvation_type"] == "time"
    assert "2026-07-30" in oracle_row["starvation"]


def test_grading_closure_absent_safe(monkeypatch, tmp_path):
    monkeypatch.setattr(bm, "GRADING_CLOSURE_PATH", tmp_path / "does_not_exist.json")
    result = bm.build_grading_closure()
    assert result["available"] is False


# ---------------------------------------------------------------------------
# 3 & 4. build_trial_budgets
# ---------------------------------------------------------------------------

TRIAL_LEDGER_ROWS = [
    {"ts": "2026-06-21T10:36:05.703638+00:00", "family": "incremental_ic:mom_12_1", "config_hash": "aaa"},
    {"ts": "2026-06-22T10:36:05.703638+00:00", "family": "incremental_ic:mom_12_1", "config_hash": "bbb"},
    {"ts": "2026-06-21T10:36:07.148583+00:00", "family": "incremental_ic:near_52w_high", "config_hash": "ccc"},
    {"ts": "2026-07-01T10:00:00+00:00", "family": "replay", "config_hash": "ddd"},
]


def test_trial_budgets_groupby(monkeypatch, tmp_path):
    fixture_path = tmp_path / "trial_ledger.jsonl"
    _write_jsonl(fixture_path, TRIAL_LEDGER_ROWS)
    monkeypatch.setattr(bm, "TRIAL_LEDGER_PATH", fixture_path)

    result = bm.build_trial_budgets()

    assert result["available"] is True
    assert result["n_total"] == 4
    assert result["n_families"] == 3

    rows_by_family = {r["family"]: r for r in result["rows"]}

    mom_row = rows_by_family["incremental_ic:mom_12_1"]
    assert mom_row["n_rows"] == 2
    # Latest ts should be the later date
    assert mom_row["latest_ts"] == "2026-06-22T10:36:05.703638+00:00"

    high_row = rows_by_family["incremental_ic:near_52w_high"]
    assert high_row["n_rows"] == 1

    replay_row = rows_by_family["replay"]
    assert replay_row["n_rows"] == 1


def test_trial_budgets_absent_safe(monkeypatch, tmp_path):
    monkeypatch.setattr(bm, "TRIAL_LEDGER_PATH", tmp_path / "missing.jsonl")
    result = bm.build_trial_budgets()
    assert result["available"] is False


# ---------------------------------------------------------------------------
# 5 & 6. build_rule_experiments
# ---------------------------------------------------------------------------

REGISTRY_ROWS = [
    # First registration
    {
        "exp_id": "exp_alpha",
        "registered_at": "2026-07-06T05:31:35Z",
        "question": "Does waiting 5 bars reduce regret? " + "x" * 250,  # long question
        "declared_budget": 10,
        "status": "registered",
    },
    # Status update for same exp_id
    {
        "exp_id": "exp_alpha",
        "registered_at": "2026-07-06T05:31:35Z",
        "status_updated_at": "2026-07-06T06:00:00Z",
        "status": "executed",
        "run_at": "2026-07-06T05:59:00Z",
    },
    # Another experiment
    {
        "exp_id": "exp_beta",
        "registered_at": "2026-07-06T07:00:00Z",
        "question": "Short question",
        "declared_budget": 6,
        "status": "registered",
    },
]


def test_rule_experiments_collapses_lifecycle(monkeypatch, tmp_path):
    fixture_path = tmp_path / "rule_experiments" / "registry.jsonl"
    _write_jsonl(fixture_path, REGISTRY_ROWS)
    monkeypatch.setattr(bm, "RULE_EXPERIMENTS_PATH", fixture_path)

    result = bm.build_rule_experiments()

    assert result["available"] is True
    # Only 2 unique exp_ids even though 3 rows
    assert result["n_experiments"] == 2
    # Pooled SUM = 10 + 6 = 16
    assert result["pooled_declared_budget_sum"] == 16

    rows_by_id = {r["exp_id"]: r for r in result["rows"]}

    # Latest status for exp_alpha should be 'executed'
    assert rows_by_id["exp_alpha"]["status"] == "executed"
    # Question truncated at 200 chars + "…"
    q = rows_by_id["exp_alpha"]["question"]
    assert len(q) <= 201  # 200 + "…"
    assert q.endswith("…")

    # exp_beta: short question unchanged
    assert rows_by_id["exp_beta"]["question"] == "Short question"
    assert rows_by_id["exp_beta"]["declared_budget"] == 6


def test_rule_experiments_absent_safe(monkeypatch, tmp_path):
    monkeypatch.setattr(bm, "RULE_EXPERIMENTS_PATH", tmp_path / "missing.jsonl")
    result = bm.build_rule_experiments()
    assert result["available"] is False


# ---------------------------------------------------------------------------
# 7 & 8. build_qledger_reliability
# ---------------------------------------------------------------------------

TRACK_RECORD_FIXTURE = {
    "generated_at": "2026-07-05T11:12:30Z",
    "grade_horizons": [5, 21, 63],
    "graded_min_dates": 25,
    "by_desk": {},
    "by_family": {
        "altdata": {
            "5": {
                "n_obs": 94,
                "n_dates": 5,
                "hit_rate": 0.56383,
                "excess_mean": 0.004928,
                "wilson_ci_low": 0.463027,
                "state": "ACCRUING",
            }
        },
        "radar": {
            "5": {
                "n_obs": 1014,
                "n_dates": 7,
                "hit_rate": 0.540434,
                "excess_mean": 0.008928,
                "wilson_ci_low": 0.509664,
                "state": "ACCRUING",
            }
        },
        "policy": {
            "5": {
                "n_obs": 7,
                "n_dates": 2,
                "hit_rate": None,
                "excess_mean": None,
                "wilson_ci_low": None,
                "state": "ACCRUING",
            }
        },
    },
}


def test_qledger_reliability_rows(monkeypatch, tmp_path):
    fixture_path = tmp_path / "qledger" / "track_record.json"
    _write_json(fixture_path, TRACK_RECORD_FIXTURE)
    monkeypatch.setattr(bm, "QLEDGER_TRACK_RECORD_PATH", fixture_path)

    result = bm.build_qledger_reliability()

    assert result["available"] is True
    assert result["graded_min_dates"] == 25
    assert result["max_n_dates"] == 7  # radar has n_dates=7
    assert result["n_families"] == 3
    assert len(result["rows"]) == 3

    rows_by_fam = {r["family"]: r for r in result["rows"]}

    altdata_row = rows_by_fam["altdata"]
    assert altdata_row["n_obs"] == 94
    assert altdata_row["n_dates"] == 5
    assert altdata_row["hit_rate_pct"] == "56.4%"
    assert altdata_row["wilson_ci_low_str"] == "0.4630"
    # n_dates_note present for §0.5.8
    assert "5" in altdata_row["n_dates_note"]
    assert "25" in altdata_row["n_dates_note"]

    # Policy has null hit_rate
    policy_row = rows_by_fam["policy"]
    assert policy_row["hit_rate_pct"] == "—"
    assert policy_row["wilson_ci_low_str"] == "—"


def test_qledger_reliability_caveat_present(monkeypatch, tmp_path):
    """§0.5.8: CI caveat must mention overlapping n_obs and n_dates."""
    fixture_path = tmp_path / "qledger" / "track_record.json"
    _write_json(fixture_path, TRACK_RECORD_FIXTURE)
    monkeypatch.setattr(bm, "QLEDGER_TRACK_RECORD_PATH", fixture_path)

    result = bm.build_qledger_reliability()

    caveat_en = result["ci_caveat_en"]
    assert "overlapping" in caveat_en.lower()
    assert "n_dates" in caveat_en
    assert "n_obs" in caveat_en

    caveat_zh = result["ci_caveat_zh"]
    assert "n_dates" in caveat_zh
    assert "n_obs" in caveat_zh


def test_qledger_reliability_absent_safe(monkeypatch, tmp_path):
    monkeypatch.setattr(bm, "QLEDGER_TRACK_RECORD_PATH", tmp_path / "missing.json")
    result = bm.build_qledger_reliability()
    assert result["available"] is False


# ---------------------------------------------------------------------------
# 9. BC-2: no "validated" / "已验证" in any new function output
# ---------------------------------------------------------------------------

def test_no_validated_in_output(monkeypatch, tmp_path):
    """None of the new functions may produce the word 'validated' (BC-2 / CI-enforced)."""
    # Grading closure
    fixture_path = tmp_path / "governance" / "grading_closure.json"
    _write_json(fixture_path, GRADING_CLOSURE_FIXTURE)
    monkeypatch.setattr(bm, "GRADING_CLOSURE_PATH", fixture_path)
    gc = bm.build_grading_closure()
    gc_text = json.dumps(gc).lower()
    assert "validated" not in gc_text, "build_grading_closure output contains 'validated'"

    # Trial budgets
    tl_path = tmp_path / "trial_ledger.jsonl"
    _write_jsonl(tl_path, TRIAL_LEDGER_ROWS)
    monkeypatch.setattr(bm, "TRIAL_LEDGER_PATH", tl_path)
    tb = bm.build_trial_budgets()
    tb_text = json.dumps(tb).lower()
    assert "validated" not in tb_text, "build_trial_budgets output contains 'validated'"

    # Rule experiments
    re_path = tmp_path / "rule_experiments" / "registry.jsonl"
    _write_jsonl(re_path, REGISTRY_ROWS)
    monkeypatch.setattr(bm, "RULE_EXPERIMENTS_PATH", re_path)
    re_out = bm.build_rule_experiments()
    re_text = json.dumps(re_out).lower()
    assert "validated" not in re_text, "build_rule_experiments output contains 'validated'"

    # qledger reliability
    ql_path = tmp_path / "qledger" / "track_record.json"
    _write_json(ql_path, TRACK_RECORD_FIXTURE)
    monkeypatch.setattr(bm, "QLEDGER_TRACK_RECORD_PATH", ql_path)
    ql = bm.build_qledger_reliability()
    ql_text = json.dumps(ql).lower()
    assert "validated" not in ql_text, "build_qledger_reliability output contains 'validated'"
