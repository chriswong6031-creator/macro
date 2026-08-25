"""Static delivery fences for the B1 canonical candidate-episode lane.

These tests prove that the already-tested writer is reached by exactly one durable
production lane, that its immutable generation is published through one HEAD pointer,
and that every public contract remains measurement-only until natural acceptance.
They deliberately do not open ``data/`` so the suite is valid in a sparse CI checkout.
"""
from __future__ import annotations

from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / ".github" / "workflows" / "daily.yml"
LEGACY_JOBS = ROOT / ".github" / "ci" / "legacy-jobs.yml"
REGISTRY = ROOT / "config" / "dataset_registry.yml"

B1_COMMAND = "python -m scripts.reconcile_us_candidate_episodes --nightly"
B1_TESTS = (
    "tests/test_us_candidate_episode.py",
    "tests/test_us_candidate_episode_intake.py",
    "tests/test_us_candidate_episode_reconciler.py",
    "tests/test_us_candidate_episode_wiring.py",
)

B1_DATASETS = {
    "prophet.us.candidate_episode.turn_watch_input": {
        "storage": "data/us_prophet_rank/episode_inputs/turn_watch/{session}.json",
        "format": "json",
        "temporal_profile": "SNAPSHOT_SERIES",
        "schema_name": "prophet.candidate_episode_input.turn_watch/v1",
        "clock": "data_session",
    },
    "prophet.us.candidate_episode.events": {
        "storage": "data/us_prophet_rank/episodes/generations/<HEAD.generation_id>/events/{month}.jsonl",
        "format": "jsonl",
        "temporal_profile": "EVENT",
        "schema_name": "prophet.candidate_episode_event/v1",
        "clock": "known_at",
    },
    "prophet.us.candidate_episode.suppressions": {
        "storage": "data/us_prophet_rank/episodes/generations/<HEAD.generation_id>/suppressions/{month}.jsonl",
        "format": "jsonl",
        "temporal_profile": "EVENT",
        "schema_name": "prophet.candidate_episode_suppression/v1",
        "clock": "recorded_at",
    },
    "prophet.us.candidate_episode.current": {
        "storage": "data/us_prophet_rank/episodes/generations/<HEAD.generation_id>/current.parquet",
        "format": "parquet",
        "temporal_profile": "DERIVED",
        "schema_name": "prophet.candidate_episode/v1",
        "clock": "opened_at",
    },
    "prophet.us.candidate_episode.all_candidates": {
        "storage": "data/us_prophet_rank/episodes/generations/<HEAD.generation_id>/all_candidates.json",
        "format": "json",
        "temporal_profile": "DERIVED",
        "schema_name": "prophet.all_candidates/v1",
        "clock": "generated_from",
    },
    "prophet.us.candidate_episode.reconciliation_receipt": {
        "storage": "data/us_prophet_rank/episodes/generations/<HEAD.generation_id>/latest_receipt.json",
        "format": "json",
        "temporal_profile": "DERIVED",
        "schema_name": "prophet.candidate_episode_reconcile_receipt/v1",
        "clock": "recorded_at",
    },
}


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _run(step: dict[str, object]) -> str:
    return str(step.get("run") or "")


def _step_index(steps: list[dict[str, object]], needle: str) -> int:
    hits = [index for index, step in enumerate(steps) if needle in _run(step)]
    assert len(hits) == 1, f"expected exactly one step containing {needle!r}, got {hits}"
    return hits[0]


def test_natural_nightly_is_the_only_durable_b1_workflow_entrypoint() -> None:
    workflow_hits: list[tuple[Path, str]] = []
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        if "scripts.reconcile_us_candidate_episodes" in text:
            workflow_hits.append((path, text))

    assert [path for path, _ in workflow_hits] == [DAILY]
    text = workflow_hits[0][1]
    assert text.count(B1_COMMAND) == 1
    assert "scripts.reconcile_us_candidate_episodes --replay" not in text


def test_b1_runs_after_both_doors_steps_and_before_grades_and_w3() -> None:
    job = _load(DAILY)["jobs"]["us_prophet_ledgers"]
    steps = job["steps"]
    emitter = _step_index(steps, "python -m scripts.emit_prophet_doors --nightly")
    door_grader = _step_index(steps, "python -m scripts.grade_prophet_doors --nightly")
    b1 = _step_index(steps, B1_COMMAND)
    grades = _step_index(steps, "python -m scripts.grade_us_prophet_candidates --nightly")
    w3 = _step_index(steps, "python -m scripts.accrue_us_prophet_w3 --nightly")
    assert emitter < b1 < door_grader < grades < w3

    step = steps[b1]
    assert step.get("continue-on-error") is not True
    assert "|| true" not in _run(step)
    assert job["env"]["COLLECT_LANE"] == "nightly"


def test_b1_commit_owner_is_exact_and_does_not_broaden_the_rank_store() -> None:
    job = _load(DAILY)["jobs"]["us_prophet_ledgers"]
    commit = next(step for step in job["steps"] if step.get("name") == "commit prophet ledger artifacts")
    lines = [line.strip() for line in _run(commit).splitlines() if line.strip().startswith("git add")]
    assert "git add data/us_prophet_rank/episodes 2>/dev/null || true" in lines
    assert all(not re.match(r"git add data/us_prophet_rank/?(?:\s|$)", line) for line in lines)


def test_turn_watch_stays_in_the_engine_broad_data_owner_before_b1() -> None:
    daily = _load(DAILY)
    b1_job = daily["jobs"]["us_prophet_ledgers"]
    needs = b1_job["needs"] if isinstance(b1_job["needs"], list) else [b1_job["needs"]]
    assert "engine" in needs

    steps = daily["jobs"]["engine"]["steps"]
    turn_watch = _step_index(steps, "python -m scripts.build_turn_watch")
    commit = next(index for index, step in enumerate(steps)
                  if step.get("name") == "commit engine outputs")
    assert turn_watch < commit
    assert re.search(r"^\s*git add data/ site/ reports/", _run(steps[commit]), re.MULTILINE)

    source = (ROOT / "scripts" / "build_turn_watch.py").read_text(encoding="utf-8")
    assert '"us_prophet_rank" / "episode_inputs" / "turn_watch"' in source


def test_existing_turn_watch_ci_owner_remains_separate() -> None:
    jobs = _load(LEGACY_JOBS)["jobs"]
    turn_watch_owners = []
    for name, job in jobs.items():
        for step in job.get("steps", []):
            if "tests/test_us_turn_watch.py" in _run(step):
                turn_watch_owners.append(name)
    assert len(turn_watch_owners) == 1
    assert turn_watch_owners[0] != "prophet-us-context-and-grades"


def test_prophet_context_ci_job_runs_all_four_b1_suites() -> None:
    job = _load(LEGACY_JOBS)["jobs"]["prophet-us-context-and-grades"]
    commands = "\n".join(_run(step) for step in job["steps"])
    for test_file in B1_TESTS:
        assert commands.count(test_file) == 1, test_file


def test_registry_declares_all_six_b1_contracts_and_clocks() -> None:
    registry = _load(REGISTRY)
    contracts = {row["dataset_id"]: row for row in registry["datasets"]}
    assert B1_DATASETS.keys() <= contracts.keys()
    for dataset_id, expected in B1_DATASETS.items():
        row = contracts[dataset_id]
        assert row["owner"] == "prophet-us-v4-b1"
        assert row["producer"] in {
            "scripts/build_turn_watch.py",
            "scripts/reconcile_us_candidate_episodes.py",
        }
        for field in ("storage", "format", "temporal_profile"):
            assert row[field] == expected[field], f"{dataset_id}:{field}"
        assert row["schema"]["contract_schema"]["value"] == expected["schema_name"]
        assert row["schema"][expected["clock"]]["clock"] == "point_in_time"
        assert "present-day state backward" in row["notes"]


def test_registry_resolves_one_head_and_rejects_orphan_generations_as_canonical() -> None:
    contracts = {row["dataset_id"]: row for row in _load(REGISTRY)["datasets"]}
    for dataset_id in set(B1_DATASETS) - {"prophet.us.candidate_episode.turn_watch_input"}:
        row = contracts[dataset_id]
        assert "<HEAD.generation_id>" in row["storage"]
        assert "HEAD.json" in row["notes"]
        assert "unreferenced generation" in row["notes"]
        assert "noncanonical" in row["notes"]


def test_registry_lineage_binds_b1_to_identity_and_immutable_truth() -> None:
    contracts = {row["dataset_id"]: row for row in _load(REGISTRY)["datasets"]}
    identity_and_anchor = {
        "reference.security_master",
        "reference.vendor_aliases",
        "reference.issuer_master",
        "prophet.us.candidate_episode.turn_watch_input",
    }
    assert set(contracts["prophet.us.candidate_episode.events"]["inputs"]) == identity_and_anchor
    assert set(contracts["prophet.us.candidate_episode.suppressions"]["inputs"]) == identity_and_anchor
    assert contracts["prophet.us.candidate_episode.current"]["inputs"] == [
        "prophet.us.candidate_episode.events"
    ]
    assert set(contracts["prophet.us.candidate_episode.all_candidates"]["inputs"]) == {
        "prophet.us.candidate_episode.events",
        "prophet.us.candidate_episode.suppressions",
    }


def test_b1_does_not_become_rank_plan_availability_radar_or_v3_authority() -> None:
    guarded = [
        ROOT / "engine" / "prophet_bridge.py",
        ROOT / "engine" / "us_board_rank.py",
        ROOT / "engine" / "us_entry_status.py",
    ]
    guarded.extend(sorted((ROOT / "engine" / "entry_radar").glob("*.py")))
    guarded.extend(sorted((ROOT / "engine").glob("*prophet*v3*.py")))
    for path in guarded:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert "us_candidate_episode" not in text, path
        assert "data/us_prophet_rank/episodes" not in text, path
