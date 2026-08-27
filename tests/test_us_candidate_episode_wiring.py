"""Static delivery fences for the B1 canonical candidate-episode lane.

These tests prove that the already-tested writer is reached by exactly one durable
production lane, that its immutable generation is published through one HEAD pointer,
and that every public contract remains measurement-only until natural acceptance.
They deliberately do not open ``data/`` so the suite is valid in a sparse CI checkout.
"""
from __future__ import annotations

from pathlib import Path
import re

import pytest
import yaml

from scripts.workflow_run_source import resolve_run_source


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

UPSTREAM_DATASETS = {
    "prophet.us.context_vector.candidates": {
        "owner": "prophet-us-context-vector",
        "producer": "engine/us_context_vector.py::append_candidates",
        "storage": "data/us_prophet_rank/candidates/{month}.parquet",
        "status": "PRODUCED",
        "schema_name": "us_prophet_rank.candidates/v1",
    },
    "prophet.us.doors.flags": {
        "owner": "WS:PROPHET-US-ENTRY-TIMING",
        "producer": "scripts/emit_prophet_doors.py",
        "storage": "data/prophet_doors/flags.jsonl",
        "status": "PRODUCED",
        "schema_name": "prophet_doors/v1",
    },
    "entry_radar.forward_events": {
        "owner": "WS:LIVE-ENTRY-RADAR",
        "producer": "scripts/reconcile_entry_radar.py",
        "storage": "data/entry_radar/forward.parquet",
        "status": "PROPOSED",
    },
}

FORBIDDEN_B1_AUTHORITY_TOKENS = (
    "us_candidate_episode",
    "data/us_prophet_rank/episodes",
)


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _run(step: dict[str, object]) -> str:
    # 512KB-cap diet: some bodies live in scripts/ci/ — resolve the effective
    # source so step-body assertions keep seeing what the step actually runs.
    return resolve_run_source(str(step.get("run") or ""), ROOT)


def _step_index(steps: list[dict[str, object]], needle: str) -> int:
    hits = [index for index, step in enumerate(steps) if needle in _run(step)]
    assert len(hits) == 1, f"expected exactly one step containing {needle!r}, got {hits}"
    return hits[0]


def _workflow_triggers(workflow: dict[str, object]) -> dict[str, object]:
    # PyYAML 1.1 resolves the unquoted GitHub Actions key ``on`` as boolean true.
    triggers = workflow.get("on") or workflow.get(True)
    assert isinstance(triggers, dict)
    return triggers


def _assert_no_b1_authority(paths: list[Path]) -> None:
    assert paths, "authority fence resolved no source files"
    for path in paths:
        assert path.is_file(), f"authority owner missing from scan: {path}"
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_B1_AUTHORITY_TOKENS:
            assert token not in text, f"{path}: acquired B1 authority token {token!r}"


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


def test_manual_daily_dispatch_exists_but_cannot_reach_the_b1_writer() -> None:
    workflow = _load(DAILY)
    triggers = _workflow_triggers(workflow)
    assert "workflow_dispatch" in triggers

    job = workflow["jobs"]["us_prophet_ledgers"]
    b1_step = job["steps"][_step_index(job["steps"], B1_COMMAND)]
    assert b1_step["if"] == "always() && github.event_name == 'schedule'"


def test_every_declared_daily_cron_can_reach_the_schedule_only_b1_step() -> None:
    workflow = _load(DAILY)
    schedules = _workflow_triggers(workflow)["schedule"]
    assert isinstance(schedules, list) and schedules
    assert all(isinstance(row.get("cron"), str) and row["cron"] for row in schedules)

    job = workflow["jobs"]["us_prophet_ledgers"]
    b1_step = job["steps"][_step_index(job["steps"], B1_COMMAND)]
    condition = str(b1_step["if"])
    assert condition == "always() && github.event_name == 'schedule'"
    assert "github.event.schedule" not in condition
    assert job["if"] == "always() && needs.et_gate.outputs.run != 'false'"


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


def test_registry_declares_two_produced_upstreams_and_one_proposed_radar_input() -> None:
    contracts = {row["dataset_id"]: row for row in _load(REGISTRY)["datasets"]}
    assert UPSTREAM_DATASETS.keys() <= contracts.keys()
    for dataset_id, expected in UPSTREAM_DATASETS.items():
        row = contracts[dataset_id]
        for field in ("owner", "producer", "storage", "status"):
            assert row[field] == expected[field], f"{dataset_id}:{field}"
    for dataset_id in (
        "prophet.us.context_vector.candidates",
        "prophet.us.doors.flags",
    ):
        row = contracts[dataset_id]
        assert row["schema"]["contract_schema"]["value"] == UPSTREAM_DATASETS[dataset_id]["schema_name"]

    radar = contracts["entry_radar.forward_events"]
    assert "identity" not in radar
    assert "contract_schema" not in radar["schema"]
    notes = radar["notes"]
    assert "mastermind.entry_event.v1 is source provenance only" in notes
    assert "event_id when present" in notes
    assert "ticker|detector_id|decision_session" in notes
    assert "nonempty episode_address relation" in notes
    assert "WS:LIVE-ENTRY-RADAR must freeze and validate" in notes
    assert "exact immutable event_id" in notes
    assert "PRODUCED" in notes


def test_every_b1_identity_column_exists_in_its_declared_schema_or_grain() -> None:
    contracts = {row["dataset_id"]: row for row in _load(REGISTRY)["datasets"]}
    for dataset_id in B1_DATASETS:
        row = contracts[dataset_id]
        identity = row.get("identity")
        if not identity:
            continue
        id_column = identity["id_column"]
        assert id_column in set(row["grain"]) | set(row["schema"]), dataset_id
    assert contracts["prophet.us.candidate_episode.events"]["identity"] == {
        "id_column": "event_id",
        "id_type": "content_address",
    }


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
        "prophet.us.context_vector.candidates",
        "prophet.us.doors.flags",
        "entry_radar.forward_events",
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
    canonical_owners = [
        ROOT / "engine" / "prophet_bridge.py",
        ROOT / "engine" / "us_board_rank.py",
        ROOT / "engine" / "us_prophet_fusion.py",
        ROOT / "engine" / "entry_signal.py",
        ROOT / "engine" / "prophet_live" / "live_states.py",
    ]
    assert all(path.is_file() for path in canonical_owners)

    radar = sorted((ROOT / "engine" / "entry_radar").rglob("*.py"))
    assert radar and any(path.parent != ROOT / "engine" / "entry_radar" for path in radar)

    scripts = sorted((ROOT / "scripts").rglob("*.py"))
    assert scripts
    plan_selection = []
    for path in scripts:
        if path == ROOT / "scripts" / "reconcile_us_candidate_episodes.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "originate_plans(" in text or "select_candidates(" in text:
            plan_selection.append(path)
    assert plan_selection
    assert ROOT / "scripts" / "build_prophet.py" in plan_selection

    _assert_no_b1_authority(sorted(set(canonical_owners + radar + plan_selection)))


@pytest.mark.parametrize(
    "relative",
    ("engine/entry_radar/producers/future.py", "engine/us_prophet_fusion.py"),
)
def test_authority_fence_refutes_nested_radar_and_v3_owner_leaks(
    tmp_path: Path, relative: str
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("from engine import us_candidate_episode\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="acquired B1 authority token"):
        _assert_no_b1_authority([path])
