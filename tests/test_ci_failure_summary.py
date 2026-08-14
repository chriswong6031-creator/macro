"""Focused contract tests for the standalone CI failure summary utility.

The utility must never infer causation from a pack number or from a shared job
label.  Its caller supplies explicit failure-origin evidence; this suite pins the
strict input boundary, category precedence, supersession behavior, and the one
top-level logical failure a developer should see first.

Run: python3 -m pytest -q tests/test_ci_failure_summary.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ci_failure_summary as SUMMARY  # noqa: E402


def _failure(
    job: str | None,
    kind: str,
    detail: str | None = None,
    *,
    base_reproduced: bool | None = None,
) -> dict[str, object]:
    return {
        "logical_job_id": job,
        "kind": kind,
        "base_reproduced": base_reproduced,
        "detail": detail,
    }


def _pack(
    index: int,
    outcome: str = "success",
    failures: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {"pack": index, "outcome": outcome, "failures": failures or []}


def _evidence(
    *,
    planner_outcome: str = "success",
    planner_detail: str | None = None,
    superseded: bool = False,
    packs: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema": SUMMARY.INPUT_SCHEMA,
        "superseded": superseded,
        "planner": {"outcome": planner_outcome, "detail": planner_detail},
        "packs": packs or [],
    }


def test_mixed_failures_keep_every_class_but_promote_the_pr_failure() -> None:
    document = _evidence(
        packs=[
            _pack(
                0,
                "failure",
                [
                    _failure(
                        "base-red",
                        "logical",
                        "fails on main",
                        base_reproduced=True,
                    )
                ],
            ),
            _pack(
                1,
                "failure",
                [
                    _failure(
                        "workflow-yaml",
                        "logical",
                        "new suite is unwired",
                        base_reproduced=False,
                    )
                ],
            ),
            _pack(2, "timed_out", [_failure(None, "infrastructure")]),
            _pack(
                3,
                "failure",
                [_failure("settle-race", "flaky", "rate not measured")],
            ),
        ]
    )

    summary = SUMMARY.classify_evidence(document)

    assert summary["status"] == "failure"
    assert summary["primary_category"] == "pr_caused"
    assert summary["first_actionable_failure"] == {
        "category": "pr_caused",
        "logical_job_id": "workflow-yaml",
        "pack": 1,
        "detail": "new suite is unwired",
    }
    assert summary["category_counts"] == {
        "pr_caused": 1,
        "inherited_base": 1,
        "infrastructure": 1,
        "flaky_unknown": 1,
        "superseded": 0,
        "planner_config": 0,
    }
    assert summary["pack_outcomes"] == {"failure": 3, "timed_out": 1}


def test_one_logical_job_can_carry_both_base_and_pr_failure_evidence() -> None:
    """A shared job label is not attribution; mixed causes must remain representable."""
    summary = SUMMARY.classify_evidence(
        _evidence(
            packs=[
                _pack(
                    4,
                    "failure",
                    [
                        _failure(
                            "multi-suite-job",
                            "logical",
                            "old test",
                            base_reproduced=True,
                        ),
                        _failure(
                            "multi-suite-job",
                            "logical",
                            "new test",
                            base_reproduced=False,
                        ),
                    ],
                )
            ]
        )
    )
    assert summary["category_counts"]["inherited_base"] == 1
    assert summary["category_counts"]["pr_caused"] == 1
    assert summary["first_actionable_failure"]["logical_job_id"] == "multi-suite-job"
    assert summary["first_actionable_failure"]["category"] == "pr_caused"


def test_infrastructure_without_a_logical_job_is_failure_but_not_actionable() -> None:
    summary = SUMMARY.classify_evidence(
        _evidence(
            packs=[
                _pack(
                    2,
                    "startup_failure",
                    [_failure(None, "infrastructure", "runner never started")],
                )
            ]
        )
    )
    assert summary["primary_category"] == "infrastructure"
    assert summary["first_actionable_failure"] is None
    assert summary["failures"][0]["pack"] == 2


@pytest.mark.parametrize("kind", ["flaky", "unknown"])
def test_named_flaky_unknown_failure_is_prominent_when_it_is_the_only_job(
    kind: str,
) -> None:
    summary = SUMMARY.classify_evidence(
        _evidence(
            packs=[
                _pack(
                    1,
                    "failure",
                    [_failure("browser-race", kind)],
                )
            ]
        )
    )
    assert summary["primary_category"] == "flaky_unknown"
    assert summary["first_actionable_failure"]["logical_job_id"] == "browser-race"


def test_planner_failure_is_configuration_and_packs_cannot_claim_results() -> None:
    summary = SUMMARY.classify_evidence(
        _evidence(planner_outcome="failure", planner_detail="manifest is invalid")
    )
    assert summary["primary_category"] == "planner_config"
    assert summary["first_actionable_failure"] is None
    assert summary["failures"] == [
        {
            "category": "planner_config",
            "logical_job_id": None,
            "pack": None,
            "detail": "manifest is invalid",
        }
    ]


def test_superseded_cancellation_outranks_partial_failure_evidence() -> None:
    summary = SUMMARY.classify_evidence(
        _evidence(
            superseded=True,
            packs=[
                _pack(
                    0,
                    "failure",
                    [
                        _failure(
                            "old-head-red",
                            "logical",
                            base_reproduced=False,
                        )
                    ],
                ),
                _pack(1, "cancelled"),
            ],
        )
    )
    assert summary["primary_category"] == "superseded"
    assert summary["category_counts"]["pr_caused"] == 0
    assert summary["category_counts"]["superseded"] == 1
    assert summary["first_actionable_failure"] is None
    assert summary["failures"][0]["pack"] == 1


def test_successful_no_work_plan_emits_a_clear_summary() -> None:
    summary = SUMMARY.classify_evidence(_evidence())
    assert summary == {
        "schema": SUMMARY.OUTPUT_SCHEMA,
        "status": "clear",
        "primary_category": None,
        "first_actionable_failure": None,
        "category_counts": {category: 0 for category in SUMMARY.CATEGORIES},
        "planner_outcome": "success",
        "pack_outcomes": {},
        "failures": [],
    }


@pytest.mark.parametrize(
    "mutate,error",
    [
        (
            lambda value: value.update(schema="ci.failure_evidence.v0"),
            "evidence schema",
        ),
        (
            lambda value: value.update(unexpected=True),
            "unexpected unexpected",
        ),
        (
            lambda value: value.update(superseded="false"),
            "must be a boolean",
        ),
        (
            lambda value: value["planner"].update(outcome="in_progress"),
            "terminal outcome",
        ),
        (
            lambda value: value.update(
                packs=[_pack(0), _pack(0)]
            ),
            "appears more than once",
        ),
        (
            lambda value: value.update(
                packs=[
                    _pack(
                        0,
                        "success",
                        [_failure("job", "logical", base_reproduced=False)],
                    )
                ]
            ),
            "cannot carry failures",
        ),
        (
            lambda value: value.update(packs=[_pack(0, "failure")]),
            "requires failure evidence",
        ),
        (
            lambda value: value.update(
                packs=[
                    _pack(
                        0,
                        "failure",
                        [_failure(None, "logical", base_reproduced=False)],
                    )
                ]
            ),
            "requires a logical_job_id",
        ),
        (
            lambda value: value.update(
                packs=[_pack(0, "failure", [_failure("job", "logical")])]
            ),
            "requires boolean base_reproduced",
        ),
        (
            lambda value: value.update(
                packs=[
                    _pack(
                        0,
                        "failure",
                        [_failure(None, "infrastructure", base_reproduced=False)],
                    )
                ]
            ),
            "must set base_reproduced to null",
        ),
        (
            lambda value: value.update(
                packs=[
                    _pack(
                        0,
                        "failure",
                        [_failure("same-job", "logical", base_reproduced=False)],
                    ),
                    _pack(
                        1,
                        "failure",
                        [_failure("same-job", "logical", base_reproduced=True)],
                    ),
                ]
            ),
            "appears in packs 0 and 1",
        ),
        (
            lambda value: value.update(
                planner={"outcome": "failure", "detail": None},
                packs=[_pack(0)],
            ),
            "packs must be empty",
        ),
        (
            lambda value: value.update(superseded=True),
            "requires a cancelled or stale",
        ),
    ],
)
def test_contradictory_evidence_fails_closed(mutate, error: str) -> None:
    document = _evidence()
    mutate(document)
    with pytest.raises(SUMMARY.EvidenceError, match=error):
        SUMMARY.classify_evidence(document)


def test_duplicate_failure_record_is_rejected_but_mixed_origin_is_not() -> None:
    failure = _failure(
        "job-a", "logical", "same assertion", base_reproduced=False
    )
    with pytest.raises(SUMMARY.EvidenceError, match="duplicate failure evidence"):
        SUMMARY.classify_evidence(
            _evidence(packs=[_pack(0, "failure", [failure, dict(failure)])])
        )


def test_malformed_json_emits_one_red_machine_summary_and_exit_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = tmp_path / "bad.json"
    evidence.write_text('{"schema":', encoding="utf-8")

    assert SUMMARY.main(["--input", str(evidence)]) == 2

    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 1
    assert captured.err == ""
    summary = json.loads(lines[0])
    assert summary["schema"] == SUMMARY.OUTPUT_SCHEMA
    assert summary["status"] == "failure"
    assert summary["primary_category"] == "planner_config"
    assert summary["category_counts"]["planner_config"] == 1
    assert "not valid JSON" in summary["failures"][0]["detail"]


def test_cli_reads_stdin_and_emits_exactly_one_compact_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.dumps(
        _evidence(
            packs=[
                _pack(
                    0,
                    "failure",
                    [
                        _failure(
                            "workflow-yaml",
                            "logical",
                            "line one\nline two",
                            base_reproduced=False,
                        )
                    ],
                )
            ]
        )
    )
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: raw})())

    assert SUMMARY.main(["--input", "-"]) == 0

    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 1
    assert "\n" not in lines[0]
    parsed = json.loads(lines[0])
    assert parsed["first_actionable_failure"]["logical_job_id"] == "workflow-yaml"
    assert parsed["first_actionable_failure"]["detail"] == "line one line two"


def test_missing_input_file_fails_closed_without_a_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert SUMMARY.main(["--input", str(tmp_path / "missing.json")]) == 2
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["primary_category"] == "planner_config"
    assert "cannot read evidence" in summary["failures"][0]["detail"]
    assert captured.err == ""
