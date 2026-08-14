"""Focused tests for strict packed-CI evidence collection.

Run: python3 -m pytest -q tests/test_ci_collect_pack_evidence.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ci_collect_pack_evidence as COLLECTOR  # noqa: E402
from scripts import ci_failure_summary as SUMMARY  # noqa: E402


def _record(
    pack: int,
    outcome: str = "success",
    failures: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {"pack": pack, "outcome": outcome, "failures": failures or []}


def _failure(
    job: str | None,
    kind: str = "unknown",
    detail: str | None = None,
) -> dict[str, object]:
    return {
        "logical_job_id": job,
        "kind": kind,
        "base_reproduced": None,
        "detail": detail,
    }


def _matrix(*packs: int) -> str:
    return json.dumps({"include": [{"pack": pack} for pack in packs]})


def _write_record(directory: Path, name: str, record: object) -> None:
    (directory / name).write_text(json.dumps(record), encoding="utf-8")


def test_pack_marker_emits_sorted_unknown_logical_failures() -> None:
    record = COLLECTOR.collect_pack_record(
        3,
        "failure",
        'setup\nCI_PACK_FAILED_JOBS=["z-job","a-job"]\nteardown\n',
    )

    assert record == _record(
        3,
        "failure",
        [_failure("a-job"), _failure("z-job")],
    )


def test_success_requires_one_empty_marker() -> None:
    assert COLLECTOR.collect_pack_record(
        0, "success", "CI_PACK_FAILED_JOBS=[]\n"
    ) == _record(0)
    with pytest.raises(COLLECTOR.CollectorError, match="requires exactly one"):
        COLLECTOR.collect_pack_record(0, "success", "ordinary output\n")


@pytest.mark.parametrize("log", ["", "CI_PACK_FAILED_JOBS=[]\n"])
def test_failed_pack_without_logical_ids_becomes_infrastructure(log: str) -> None:
    record = COLLECTOR.collect_pack_record(2, "failure", log)

    assert record["pack"] == 2
    assert record["outcome"] == "failure"
    assert record["failures"][0]["logical_job_id"] is None
    assert record["failures"][0]["kind"] == "infrastructure"
    assert record["failures"][0]["base_reproduced"] is None


def test_missing_log_path_is_empty_for_non_clear_outcome_only(tmp_path: Path) -> None:
    missing = tmp_path / "pack-never-started.log"

    assert COLLECTOR.main(
        ["pack", "--pack-index", "4", "--outcome", "failure", "--log", str(missing)]
    ) == 0
    with pytest.raises(COLLECTOR.CollectorError, match="does not exist"):
        COLLECTOR._read_pack_log(str(missing), "success")


@pytest.mark.parametrize(
    "log,error",
    [
        (
            "CI_PACK_FAILED_JOBS=[]\nCI_PACK_FAILED_JOBS=[]\n",
            "more than one",
        ),
        ("CI_PACK_FAILED_JOBS={}", "must be a JSON array"),
        ("CI_PACK_FAILED_JOBS=[", "not valid JSON"),
        ("CI_PACK_FAILED_JOBS=[1]", "must be a logical job id string"),
        ("CI_PACK_FAILED_JOBS=[\"same\",\"same\"]", "duplicate logical job"),
    ],
)
def test_malformed_or_ambiguous_markers_fail_closed(log: str, error: str) -> None:
    with pytest.raises(COLLECTOR.CollectorError, match=error):
        COLLECTOR.collect_pack_record(0, "failure", log)


def test_clear_outcome_cannot_claim_failed_logical_ids() -> None:
    with pytest.raises(COLLECTOR.CollectorError, match="cannot carry failures"):
        COLLECTOR.collect_pack_record(
            0, "success", 'CI_PACK_FAILED_JOBS=["job-a"]\n'
        )


def test_run_reconciles_records_and_synthesizes_missing_startup_failure(
    tmp_path: Path,
) -> None:
    _write_record(tmp_path, "pack-2.json", _record(2))
    _write_record(
        tmp_path,
        "pack-0.json",
        _record(0, "failure", [_failure("job-a")]),
    )

    evidence = COLLECTOR.collect_run_evidence(
        "success", _matrix(2, 0, 1), tmp_path
    )

    assert evidence["schema"] == SUMMARY.INPUT_SCHEMA
    assert [pack["pack"] for pack in evidence["packs"]] == [0, 1, 2]
    missing = evidence["packs"][1]
    assert missing == _record(
        1,
        "startup_failure",
        [_failure(None, "infrastructure", COLLECTOR.MISSING_ARTIFACT_DETAIL)],
    )
    assert SUMMARY.validate_evidence(evidence)["packs"][1]["outcome"] == "startup_failure"


def test_run_rejects_duplicate_pack_artifacts(tmp_path: Path) -> None:
    _write_record(tmp_path, "first.json", _record(0))
    _write_record(tmp_path, "second.json", _record(0))
    with pytest.raises(COLLECTOR.CollectorError, match="more than one record"):
        COLLECTOR.collect_run_evidence("success", _matrix(0), tmp_path)


def test_run_rejects_out_of_matrix_pack(tmp_path: Path) -> None:
    _write_record(tmp_path, "unexpected.json", _record(9))
    with pytest.raises(COLLECTOR.CollectorError, match="outside the expected matrix"):
        COLLECTOR.collect_run_evidence("success", _matrix(0), tmp_path)


@pytest.mark.parametrize(
    "value,error",
    [
        ({"pack": 0, "outcome": "success"}, "fields are invalid"),
        (_record(0, "failure"), "requires failure evidence"),
        ("not an object", "must be an object"),
    ],
)
def test_run_rejects_malformed_pack_records(
    tmp_path: Path, value: object, error: str
) -> None:
    _write_record(tmp_path, "bad.json", value)
    with pytest.raises(COLLECTOR.CollectorError, match=error):
        COLLECTOR.collect_run_evidence("success", _matrix(0), tmp_path)


@pytest.mark.parametrize(
    "matrix,error",
    [
        ('{"include":', "not valid JSON"),
        ('{"include":[],"extra":true}', "exactly the field"),
        ('{"include":{}}', "must be a list"),
        ('{"include":[{"pack":0},{"pack":0}]}', "duplicate pack"),
        ('{"include":[{"pack":true}]}', "non-negative integer"),
        ('{"include":[{"pack":0,"other":1}]}', "exactly the field"),
    ],
)
def test_expected_matrix_is_strict(matrix: str, error: str) -> None:
    with pytest.raises(COLLECTOR.CollectorError, match=error):
        COLLECTOR.parse_expected_matrix(matrix)


def test_failed_planner_accepts_only_an_empty_pack_matrix(tmp_path: Path) -> None:
    evidence = COLLECTOR.collect_run_evidence(
        "failure",
        _matrix(),
        tmp_path,
        planner_detail="manifest invalid",
    )
    assert evidence["planner"] == {
        "outcome": "failure",
        "detail": "manifest invalid",
    }
    assert evidence["packs"] == []

    with pytest.raises(COLLECTOR.CollectorError, match="packs must be empty"):
        COLLECTOR.collect_run_evidence("failure", _matrix(0), tmp_path)


def test_cli_emits_one_compact_deterministic_json_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = tmp_path / "pack.log"
    log.write_text('CI_PACK_FAILED_JOBS=["z","a"]\n', encoding="utf-8")

    args = [
        "pack",
        "--pack-index",
        "5",
        "--outcome",
        "failure",
        "--log",
        str(log),
    ]
    assert COLLECTOR.main(args) == 0
    first = capsys.readouterr()
    assert COLLECTOR.main(args) == 0
    second = capsys.readouterr()

    assert first.err == second.err == ""
    assert first.out == second.out
    assert len(first.out.splitlines()) == 1
    assert " " not in first.out
    assert json.loads(first.out)["failures"][0]["logical_job_id"] == "a"


def test_run_cli_failure_has_no_partial_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_record(tmp_path, "bad.json", {"bad": True})

    assert COLLECTOR.main(
        [
            "run",
            "--planner-outcome",
            "success",
            "--expected-matrix-json",
            _matrix(0),
            "--records-dir",
            str(tmp_path),
        ]
    ) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ci evidence collector:")


def test_missing_records_directory_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(COLLECTOR.CollectorError, match="does not exist"):
        COLLECTOR.collect_run_evidence(
            "success", _matrix(), tmp_path / "missing"
        )
